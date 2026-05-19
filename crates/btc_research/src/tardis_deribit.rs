use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{ArrayRef, Float64Builder};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{Datelike, NaiveDate, TimeZone, Utc};
use finance_chain_core::storage::{
    DERIVED_DIR, RAW_DIR, bool_array, custom_part_path, ensure_parent_dir, string_array, u64_array,
    utc_now_string, write_parquet_part, write_schema_metadata,
};
use flate2::read::GzDecoder;
use reqwest::blocking::Client;
use reqwest::header::{AUTHORIZATION, HeaderMap, HeaderValue, USER_AGENT};
use serde::{Deserialize, Serialize};

pub const DEFAULT_TARDIS_DATA_ROOT: &str = "data/tardis/v1";
pub const DEFAULT_TARDIS_RUN_TAG: &str = "20260512_deribit_smoke_v0";
pub const DEFAULT_FROM_DATE: &str = "2025-05-01";
pub const DEFAULT_TO_DATE: &str = "2025-05-02";

const DATASETS_BASE: &str = "https://datasets.tardis.dev/v1";
const OPTIONS_DATASET: &str = "deribit_options_chain";
const INDEX_DATASET: &str = "deribit_derivative_ticker";
const SNAPSHOT_DATASET: &str = "deribit_options_snapshots_5m";
const INDEX_OHLC_DATASET: &str = "deribit_index_ohlc_1m";
const USER_AGENT_VALUE: &str = "finance-chain-tardis-deribit-fetcher/0.1";
pub const DEFAULT_MAX_RETRIES: usize = 5;

#[derive(Debug, Clone)]
pub struct TardisDeribitFetchConfig {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub env_file: PathBuf,
    pub api_key: Option<String>,
    pub from_date: NaiveDate,
    pub to_date: NaiveDate,
    pub underlyings: Vec<String>,
    pub snapshot_interval_min: u64,
    pub index_interval_min: u64,
    pub max_dte: i64,
    pub keep_raw: bool,
    pub delete_raw_after_extract: bool,
    pub force: bool,
    pub dry_run: bool,
    pub run_tag: String,
    pub progress_interval: usize,
    pub max_retries: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TardisDeribitFetchSummary {
    pub run_tag: String,
    pub started_at_utc: String,
    pub finished_at_utc: String,
    pub data_root: String,
    pub from_date: String,
    pub to_date: String,
    pub underlyings: Vec<String>,
    pub dry_run: bool,
    pub days: Vec<TardisDeribitDaySummary>,
    pub outputs: TardisDeribitOutputs,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TardisDeribitOutputs {
    pub completion_json: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TardisDeribitDaySummary {
    pub date: String,
    pub status: String,
    pub options_raw_path: String,
    pub options_raw_bytes: u64,
    pub options_raw_download_status: String,
    pub options_snapshot_parquet: String,
    pub options_snapshot_rows: usize,
    pub options_matched_ticks: u64,
    pub options_total_ticks: u64,
    pub iv_rescaled: bool,
    pub iv_median_positive: Option<f64>,
    pub midnight_fixup_rows_added: usize,
    pub index_raw_paths: Vec<String>,
    pub index_raw_bytes: u64,
    pub index_ohlc_parquet: String,
    pub index_ohlc_rows: usize,
    pub index_total_ticks: u64,
    pub index_matched_ticks: u64,
    pub error: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DownloadStatus {
    Downloaded,
    Skipped,
    Planned,
}

impl DownloadStatus {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Downloaded => "downloaded",
            Self::Skipped => "skipped",
            Self::Planned => "planned",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct OptionKey {
    underlying: String,
    expiry: String,
    strike_micros: i64,
    is_call: bool,
}

#[derive(Debug, Clone)]
struct QuoteState {
    underlying_price: f64,
    bid_price: f64,
    ask_price: f64,
    mark_price: f64,
    mark_iv: f64,
    delta: f64,
}

#[derive(Debug, Clone)]
struct OptionSnapshotRow {
    timestamp_us: u64,
    underlying: String,
    expiry: String,
    strike: f64,
    is_call: bool,
    quote: QuoteState,
}

#[derive(Debug, Default)]
struct OptionSnapshotRows {
    rows: Vec<OptionSnapshotRow>,
}

#[derive(Debug)]
struct OptionExtractResult {
    rows: OptionSnapshotRows,
    matched_ticks: u64,
    total_ticks: u64,
    iv_rescaled: bool,
    iv_median_positive: Option<f64>,
    midnight_fixup_rows_added: usize,
}

#[derive(Debug, Clone)]
struct IndexOhlcRow {
    timestamp_us: u64,
    underlying: String,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
}

#[derive(Debug)]
struct IndexExtractResult {
    rows: Vec<IndexOhlcRow>,
    total_ticks: u64,
    matched_ticks: u64,
}

#[derive(Debug)]
struct ParsedOptionSymbol {
    underlying: String,
    expiry: String,
    strike: f64,
    is_call: bool,
}

#[derive(Debug)]
struct ColumnIndexes {
    symbol: usize,
    timestamp: usize,
    bid_price: usize,
    ask_price: usize,
    mark_price: usize,
    mark_iv: usize,
    underlying_price: usize,
    delta: usize,
}

#[derive(Debug)]
struct IndexColumnIndexes {
    timestamp: usize,
    index_price: usize,
}

pub fn default_from_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_FROM_DATE, "%Y-%m-%d").expect("valid default from date")
}

pub fn default_to_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_TO_DATE, "%Y-%m-%d").expect("valid default to date")
}

pub fn run_tardis_deribit_snapshot_fetch(
    config: &TardisDeribitFetchConfig,
) -> Result<TardisDeribitFetchSummary> {
    validate_config(config)?;
    let started_at_utc = utc_now_string();
    let underlyings = normalized_underlyings(&config.underlyings)?;
    let dates = date_range(config.from_date, config.to_date)?;
    let completion_path = config.date_dir.join(format!(
        "tardis_deribit_fetch_completion_{}.json",
        config.run_tag
    ));

    if config.dry_run {
        let days = dates
            .iter()
            .map(|date| planned_day_summary(config, *date, &underlyings))
            .collect::<Result<Vec<_>>>()?;
        let summary = TardisDeribitFetchSummary {
            run_tag: config.run_tag.clone(),
            started_at_utc,
            finished_at_utc: utc_now_string(),
            data_root: path_string(&config.data_root),
            from_date: config.from_date.to_string(),
            to_date: config.to_date.to_string(),
            underlyings,
            dry_run: true,
            days,
            outputs: TardisDeribitOutputs {
                completion_json: path_string(&completion_path),
            },
        };
        return Ok(summary);
    }

    let api_key = config
        .api_key
        .clone()
        .or_else(|| parse_tardis_api_key_from_file(&config.env_file).ok())
        .ok_or_else(|| anyhow!("TARDIS_API_KEY not found in {}", config.env_file.display()))?;
    let client = Client::builder()
        .timeout(Duration::from_secs(3_600))
        .build()
        .context("failed to build HTTP client")?;
    let mut prev_last_boundary: Option<Vec<OptionSnapshotRow>> = None;
    let mut days = Vec::new();

    for date in dates {
        match process_day(
            config,
            &client,
            &api_key,
            date,
            &underlyings,
            prev_last_boundary.as_ref(),
        ) {
            Ok((summary, last_boundary)) => {
                prev_last_boundary = Some(last_boundary);
                days.push(summary);
            }
            Err(err) => {
                days.push(day_error_summary(config, date, err));
                prev_last_boundary = None;
            }
        }
    }

    let summary = TardisDeribitFetchSummary {
        run_tag: config.run_tag.clone(),
        started_at_utc,
        finished_at_utc: utc_now_string(),
        data_root: path_string(&config.data_root),
        from_date: config.from_date.to_string(),
        to_date: config.to_date.to_string(),
        underlyings,
        dry_run: false,
        days,
        outputs: TardisDeribitOutputs {
            completion_json: path_string(&completion_path),
        },
    };
    write_completion_json(&completion_path, &summary)?;
    Ok(summary)
}

fn process_day(
    config: &TardisDeribitFetchConfig,
    client: &Client,
    api_key: &str,
    date: NaiveDate,
    underlyings: &[String],
    prev_last_boundary: Option<&Vec<OptionSnapshotRow>>,
) -> Result<(TardisDeribitDaySummary, Vec<OptionSnapshotRow>)> {
    let options_raw = options_raw_path(&config.data_root, date);
    let options_url = options_chain_url(date);
    let (options_status, options_bytes) = download_file(
        client,
        &options_url,
        &options_raw,
        api_key,
        config.force,
        config.max_retries,
    )
    .with_context(|| format!("failed to download options chain for {date}"))?;

    let option_extract = extract_options_from_gzip_file(
        &options_raw,
        date,
        underlyings,
        config.snapshot_interval_min,
        config.max_dte,
        prev_last_boundary,
        config.progress_interval,
    )
    .with_context(|| format!("failed to extract options chain for {date}"))?;

    let snapshot_path = options_snapshot_parquet_path(&config.data_root, date, &config.run_tag);
    write_options_snapshot_parquet(
        &snapshot_path,
        &config.data_root,
        &config.run_tag,
        date,
        &option_extract.rows,
    )?;
    let last_boundary_rows =
        last_boundary_rows(&option_extract.rows, date, config.snapshot_interval_min)?;

    let mut index_raw_paths = Vec::new();
    let mut index_raw_bytes = 0_u64;
    let mut index_rows = Vec::new();
    let mut index_total_ticks = 0_u64;
    let mut index_matched_ticks = 0_u64;
    for underlying in underlyings {
        let raw_path = derivative_ticker_raw_path(&config.data_root, date, underlying);
        let url = derivative_ticker_url(date, underlying);
        let (_status, bytes) = download_file(
            client,
            &url,
            &raw_path,
            api_key,
            config.force,
            config.max_retries,
        )
        .with_context(|| format!("failed to download derivative ticker {underlying} for {date}"))?;
        index_raw_bytes += bytes;
        index_raw_paths.push(path_string(&raw_path));
        let mut extracted = extract_index_ohlc_from_gzip_file(
            &raw_path,
            date,
            underlying,
            config.index_interval_min,
        )
        .with_context(|| format!("failed to extract derivative ticker {underlying} for {date}"))?;
        index_total_ticks += extracted.total_ticks;
        index_matched_ticks += extracted.matched_ticks;
        index_rows.append(&mut extracted.rows);
    }
    index_rows.sort_by(|a, b| {
        a.timestamp_us
            .cmp(&b.timestamp_us)
            .then(a.underlying.cmp(&b.underlying))
    });
    let index_path = index_ohlc_parquet_path(&config.data_root, date, &config.run_tag);
    write_index_ohlc_parquet(
        &index_path,
        &config.data_root,
        &config.run_tag,
        date,
        &index_rows,
    )?;

    if config.delete_raw_after_extract || !config.keep_raw {
        remove_file_if_exists(&options_raw)?;
        for path in &index_raw_paths {
            remove_file_if_exists(Path::new(path))?;
        }
    }

    let summary = TardisDeribitDaySummary {
        date: date.to_string(),
        status: "ok".to_string(),
        options_raw_path: path_string(&options_raw),
        options_raw_bytes: options_bytes,
        options_raw_download_status: options_status.as_str().to_string(),
        options_snapshot_parquet: path_string(&snapshot_path),
        options_snapshot_rows: option_extract.rows.rows.len(),
        options_matched_ticks: option_extract.matched_ticks,
        options_total_ticks: option_extract.total_ticks,
        iv_rescaled: option_extract.iv_rescaled,
        iv_median_positive: option_extract.iv_median_positive,
        midnight_fixup_rows_added: option_extract.midnight_fixup_rows_added,
        index_raw_paths,
        index_raw_bytes,
        index_ohlc_parquet: path_string(&index_path),
        index_ohlc_rows: index_rows.len(),
        index_total_ticks,
        index_matched_ticks,
        error: String::new(),
    };
    Ok((summary, last_boundary_rows))
}

fn planned_day_summary(
    config: &TardisDeribitFetchConfig,
    date: NaiveDate,
    underlyings: &[String],
) -> Result<TardisDeribitDaySummary> {
    Ok(TardisDeribitDaySummary {
        date: date.to_string(),
        status: "planned".to_string(),
        options_raw_path: path_string(&options_raw_path(&config.data_root, date)),
        options_raw_bytes: 0,
        options_raw_download_status: DownloadStatus::Planned.as_str().to_string(),
        options_snapshot_parquet: path_string(&options_snapshot_parquet_path(
            &config.data_root,
            date,
            &config.run_tag,
        )),
        options_snapshot_rows: 0,
        options_matched_ticks: 0,
        options_total_ticks: 0,
        iv_rescaled: false,
        iv_median_positive: None,
        midnight_fixup_rows_added: 0,
        index_raw_paths: underlyings
            .iter()
            .map(|underlying| {
                path_string(&derivative_ticker_raw_path(
                    &config.data_root,
                    date,
                    underlying,
                ))
            })
            .collect(),
        index_raw_bytes: 0,
        index_ohlc_parquet: path_string(&index_ohlc_parquet_path(
            &config.data_root,
            date,
            &config.run_tag,
        )),
        index_ohlc_rows: 0,
        index_total_ticks: 0,
        index_matched_ticks: 0,
        error: String::new(),
    })
}

fn day_error_summary(
    config: &TardisDeribitFetchConfig,
    date: NaiveDate,
    err: anyhow::Error,
) -> TardisDeribitDaySummary {
    TardisDeribitDaySummary {
        date: date.to_string(),
        status: "failed".to_string(),
        options_raw_path: path_string(&options_raw_path(&config.data_root, date)),
        options_raw_bytes: 0,
        options_raw_download_status: String::new(),
        options_snapshot_parquet: path_string(&options_snapshot_parquet_path(
            &config.data_root,
            date,
            &config.run_tag,
        )),
        options_snapshot_rows: 0,
        options_matched_ticks: 0,
        options_total_ticks: 0,
        iv_rescaled: false,
        iv_median_positive: None,
        midnight_fixup_rows_added: 0,
        index_raw_paths: Vec::new(),
        index_raw_bytes: 0,
        index_ohlc_parquet: path_string(&index_ohlc_parquet_path(
            &config.data_root,
            date,
            &config.run_tag,
        )),
        index_ohlc_rows: 0,
        index_total_ticks: 0,
        index_matched_ticks: 0,
        error: format!("{err:#}"),
    }
}

fn download_file(
    client: &Client,
    url: &str,
    path: &Path,
    api_key: &str,
    force: bool,
    max_retries: usize,
) -> Result<(DownloadStatus, u64)> {
    if path.exists() && path.metadata()?.len() > 0 && !force {
        return Ok((DownloadStatus::Skipped, path.metadata()?.len()));
    }
    ensure_parent_dir(path)?;
    let temp_path = temp_download_path(path);
    if temp_path.exists() {
        fs::remove_file(&temp_path)
            .with_context(|| format!("failed to remove stale temp {}", temp_path.display()))?;
    }

    let retries = max_retries.max(1);
    let mut last_error = None;
    for attempt in 0..retries {
        if attempt > 0 {
            std::thread::sleep(retry_delay(attempt));
        }
        match try_download_file(client, url, &temp_path, api_key) {
            Ok(bytes) => {
                if path.exists() {
                    fs::remove_file(path)
                        .with_context(|| format!("failed to remove old {}", path.display()))?;
                }
                fs::rename(&temp_path, path).with_context(|| {
                    format!(
                        "failed to move {} to {}",
                        temp_path.display(),
                        path.display()
                    )
                })?;
                return Ok((DownloadStatus::Downloaded, bytes));
            }
            Err(err) => {
                let message = format!("{err:#}");
                let retryable = is_retryable_error(&message);
                let _ = fs::remove_file(&temp_path);
                last_error = Some(err);
                if !retryable {
                    break;
                }
            }
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("download failed for {url}")))
}

fn try_download_file(client: &Client, url: &str, temp_path: &Path, api_key: &str) -> Result<u64> {
    let mut headers = HeaderMap::new();
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {api_key}")).context("invalid Tardis API key")?,
    );
    headers.insert(USER_AGENT, HeaderValue::from_static(USER_AGENT_VALUE));
    let mut response = client
        .get(url)
        .headers(headers)
        .send()
        .with_context(|| format!("request failed {url}"))?;
    let status = response.status();
    if status.is_client_error() {
        bail!("non-retryable HTTP {status} for {url}");
    }
    if !status.is_success() {
        bail!("retryable HTTP {status} for {url}");
    }
    let expected_len = response.content_length();
    let mut file = File::create(temp_path)
        .with_context(|| format!("failed to create {}", temp_path.display()))?;
    let bytes = io::copy(&mut response, &mut file)
        .with_context(|| format!("failed to stream response into {}", temp_path.display()))?;
    if let Some(expected) = expected_len {
        if bytes != expected {
            bail!("truncated download for {url}: got {bytes}, expected {expected}");
        }
    }
    if bytes == 0 {
        bail!("empty download for {url}");
    }
    Ok(bytes)
}

fn extract_options_from_gzip_file(
    path: &Path,
    date: NaiveDate,
    underlyings: &[String],
    interval_min: u64,
    max_dte: i64,
    prev_last_boundary: Option<&Vec<OptionSnapshotRow>>,
    progress_interval: usize,
) -> Result<OptionExtractResult> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    extract_options_from_csv_reader(
        decoder,
        date,
        underlyings,
        interval_min,
        max_dte,
        prev_last_boundary,
        progress_interval,
    )
}

fn extract_options_from_csv_reader<R: Read>(
    reader: R,
    date: NaiveDate,
    underlyings: &[String],
    interval_min: u64,
    max_dte: i64,
    prev_last_boundary: Option<&Vec<OptionSnapshotRow>>,
    progress_interval: usize,
) -> Result<OptionExtractResult> {
    let underlying_set = underlyings.iter().cloned().collect::<BTreeSet<_>>();
    let mut csv_reader = csv::ReaderBuilder::new()
        .has_headers(true)
        .from_reader(reader);
    let headers = csv_reader.headers()?.clone();
    let indexes = option_column_indexes(&headers)?;
    let mut state = BTreeMap::<OptionKey, QuoteState>::new();
    let mut rows = OptionSnapshotRows::default();
    let mut dte_cache = BTreeMap::<String, Option<i64>>::new();
    let mut total_ticks = 0_u64;
    let mut matched_ticks = 0_u64;
    let day_start_us = day_start_us(date);
    let interval_us = interval_min * 60 * 1_000_000;
    let last_boundary_us = day_start_us + 24 * 3_600 * 1_000_000 - interval_us;
    let mut next_boundary_us = day_start_us;

    for record in csv_reader.records() {
        let record = record?;
        total_ticks += 1;
        let symbol = record.get(indexes.symbol).unwrap_or_default();
        let Some(parsed) = parse_option_symbol(symbol) else {
            continue;
        };
        if !underlying_set.contains(&parsed.underlying) {
            continue;
        }
        let dte = cached_dte(&mut dte_cache, &parsed.expiry, date);
        if dte.is_none_or(|value| value < 0 || value > max_dte) {
            continue;
        }
        let timestamp_us = parse_u64_field(&record, indexes.timestamp)?;
        while next_boundary_us <= last_boundary_us && timestamp_us >= next_boundary_us {
            flush_options_boundary(&state, &mut rows, next_boundary_us);
            next_boundary_us += interval_us;
        }
        let quote = clean_quote(QuoteState {
            underlying_price: parse_f64_field(&record, indexes.underlying_price),
            bid_price: parse_f64_field(&record, indexes.bid_price),
            ask_price: parse_f64_field(&record, indexes.ask_price),
            mark_price: parse_f64_field(&record, indexes.mark_price),
            mark_iv: parse_f64_field(&record, indexes.mark_iv),
            delta: parse_f64_field(&record, indexes.delta),
        });
        state.insert(
            OptionKey {
                underlying: parsed.underlying,
                expiry: parsed.expiry,
                strike_micros: strike_key(parsed.strike),
                is_call: parsed.is_call,
            },
            quote,
        );
        matched_ticks += 1;
        if progress_interval > 0 && matched_ticks % progress_interval as u64 == 0 {
            eprintln!(
                "[tardis_deribit] {date} matched={} scanned={}",
                matched_ticks, total_ticks
            );
        }
    }
    while next_boundary_us <= last_boundary_us {
        flush_options_boundary(&state, &mut rows, next_boundary_us);
        next_boundary_us += interval_us;
    }
    if rows.rows.is_empty() {
        bail!("no option snapshot rows produced for {date}");
    }
    let midnight_fixup_rows_added =
        apply_midnight_fixup(&mut rows, date, prev_last_boundary.unwrap_or(&Vec::new()));
    let (iv_rescaled, iv_median_positive) = maybe_rescale_iv(&mut rows);
    Ok(OptionExtractResult {
        rows,
        matched_ticks,
        total_ticks,
        iv_rescaled,
        iv_median_positive,
        midnight_fixup_rows_added,
    })
}

fn flush_options_boundary(
    state: &BTreeMap<OptionKey, QuoteState>,
    rows: &mut OptionSnapshotRows,
    timestamp_us: u64,
) {
    rows.rows.reserve(state.len());
    for (key, quote) in state {
        rows.rows.push(OptionSnapshotRow {
            timestamp_us,
            underlying: key.underlying.clone(),
            expiry: key.expiry.clone(),
            strike: key.strike_micros as f64 / 1_000_000.0,
            is_call: key.is_call,
            quote: quote.clone(),
        });
    }
}

fn apply_midnight_fixup(
    rows: &mut OptionSnapshotRows,
    date: NaiveDate,
    prev_last_boundary: &[OptionSnapshotRow],
) -> usize {
    if prev_last_boundary.is_empty() {
        return 0;
    }
    let midnight = day_start_us(date);
    let mut present = BTreeSet::new();
    for row in rows.rows.iter().filter(|row| row.timestamp_us == midnight) {
        present.insert(row_key(row));
    }
    let mut added = Vec::new();
    for prev in prev_last_boundary {
        if !present.contains(&row_key(prev)) {
            let mut row = prev.clone();
            row.timestamp_us = midnight;
            added.push(row);
        }
    }
    let count = added.len();
    rows.rows.extend(added);
    rows.rows.sort_by(|a, b| {
        a.timestamp_us
            .cmp(&b.timestamp_us)
            .then(a.underlying.cmp(&b.underlying))
            .then(a.expiry.cmp(&b.expiry))
            .then(a.strike.total_cmp(&b.strike))
            .then(a.is_call.cmp(&b.is_call))
    });
    count
}

fn maybe_rescale_iv(rows: &mut OptionSnapshotRows) -> (bool, Option<f64>) {
    let mut values = rows
        .rows
        .iter()
        .map(|row| row.quote.mark_iv)
        .filter(|value| value.is_finite() && *value > 0.0)
        .collect::<Vec<_>>();
    if values.is_empty() {
        return (false, None);
    }
    values.sort_by(|a, b| a.total_cmp(b));
    let median = values[values.len() / 2];
    if median < 2.0 {
        for row in &mut rows.rows {
            if row.quote.mark_iv.is_finite() {
                row.quote.mark_iv *= 100.0;
            }
        }
        (true, Some(median))
    } else {
        (false, Some(median))
    }
}

fn extract_index_ohlc_from_gzip_file(
    path: &Path,
    date: NaiveDate,
    underlying: &str,
    interval_min: u64,
) -> Result<IndexExtractResult> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    extract_index_ohlc_from_csv_reader(decoder, date, underlying, interval_min)
}

fn extract_index_ohlc_from_csv_reader<R: Read>(
    reader: R,
    date: NaiveDate,
    underlying: &str,
    interval_min: u64,
) -> Result<IndexExtractResult> {
    let mut csv_reader = csv::ReaderBuilder::new()
        .has_headers(true)
        .from_reader(reader);
    let headers = csv_reader.headers()?.clone();
    let indexes = index_column_indexes(&headers)?;
    let interval_us = interval_min * 60 * 1_000_000;
    let day_start = day_start_us(date);
    let day_end = day_start + 24 * 3_600 * 1_000_000;
    let mut bars = BTreeMap::<u64, (f64, f64, f64, f64)>::new();
    let mut total_ticks = 0_u64;
    let mut matched_ticks = 0_u64;
    for record in csv_reader.records() {
        let record = record?;
        total_ticks += 1;
        let timestamp_us = parse_u64_field(&record, indexes.timestamp)?;
        if timestamp_us < day_start || timestamp_us >= day_end {
            continue;
        }
        let price = parse_f64_field(&record, indexes.index_price);
        if !price.is_finite() || price <= 0.0 {
            continue;
        }
        let bucket = (timestamp_us / interval_us) * interval_us;
        bars.entry(bucket)
            .and_modify(|bar| {
                bar.1 = bar.1.max(price);
                bar.2 = bar.2.min(price);
                bar.3 = price;
            })
            .or_insert((price, price, price, price));
        matched_ticks += 1;
    }
    let rows = bars
        .into_iter()
        .map(|(timestamp_us, (open, high, low, close))| IndexOhlcRow {
            timestamp_us,
            underlying: underlying.to_string(),
            open,
            high,
            low,
            close,
        })
        .collect::<Vec<_>>();
    Ok(IndexExtractResult {
        rows,
        total_ticks,
        matched_ticks,
    })
}

fn write_options_snapshot_parquet(
    path: &Path,
    data_root: &Path,
    run_tag: &str,
    source_date: NaiveDate,
    rows: &OptionSnapshotRows,
) -> Result<()> {
    let schema = options_snapshot_schema();
    write_schema_metadata(data_root, SNAPSHOT_DATASET, schema.as_ref(), &["dt"])?;
    let timestamp_us = rows
        .rows
        .iter()
        .map(|row| row.timestamp_us)
        .collect::<Vec<_>>();
    let timestamp_utc = rows
        .rows
        .iter()
        .map(|row| utc_from_micros(row.timestamp_us))
        .collect::<Result<Vec<_>>>()?;
    let underlying = rows
        .rows
        .iter()
        .map(|row| row.underlying.clone())
        .collect::<Vec<_>>();
    let expiry = rows
        .rows
        .iter()
        .map(|row| row.expiry.clone())
        .collect::<Vec<_>>();
    let strike = rows.rows.iter().map(|row| row.strike).collect::<Vec<_>>();
    let is_call = rows.rows.iter().map(|row| row.is_call).collect::<Vec<_>>();
    let underlying_price = rows
        .rows
        .iter()
        .map(|row| row.quote.underlying_price)
        .collect::<Vec<_>>();
    let bid_price = rows
        .rows
        .iter()
        .map(|row| row.quote.bid_price)
        .collect::<Vec<_>>();
    let ask_price = rows
        .rows
        .iter()
        .map(|row| row.quote.ask_price)
        .collect::<Vec<_>>();
    let mark_price = rows
        .rows
        .iter()
        .map(|row| row.quote.mark_price)
        .collect::<Vec<_>>();
    let mark_iv = rows
        .rows
        .iter()
        .map(|row| row.quote.mark_iv)
        .collect::<Vec<_>>();
    let delta = rows
        .rows
        .iter()
        .map(|row| row.quote.delta)
        .collect::<Vec<_>>();
    let source_dates = vec![source_date.to_string(); rows.rows.len()];
    let run_tags = vec![run_tag.to_string(); rows.rows.len()];

    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            u64_array(&timestamp_us),
            string_array(&timestamp_utc),
            string_array(&underlying),
            string_array(&expiry),
            f64_values_array(&strike),
            bool_array(&is_call),
            f64_values_array(&underlying_price),
            f64_values_array(&bid_price),
            f64_values_array(&ask_price),
            f64_values_array(&mark_price),
            f64_values_array(&mark_iv),
            f64_values_array(&delta),
            string_array(&source_dates),
            string_array(&run_tags),
        ],
    )?;
    write_parquet_part(path, schema, batch)?;
    Ok(())
}

fn write_index_ohlc_parquet(
    path: &Path,
    data_root: &Path,
    run_tag: &str,
    source_date: NaiveDate,
    rows: &[IndexOhlcRow],
) -> Result<()> {
    let schema = index_ohlc_schema();
    write_schema_metadata(data_root, INDEX_OHLC_DATASET, schema.as_ref(), &["dt"])?;
    let timestamp_us = rows.iter().map(|row| row.timestamp_us).collect::<Vec<_>>();
    let timestamp_utc = rows
        .iter()
        .map(|row| utc_from_micros(row.timestamp_us))
        .collect::<Result<Vec<_>>>()?;
    let underlying = rows
        .iter()
        .map(|row| row.underlying.clone())
        .collect::<Vec<_>>();
    let open = rows.iter().map(|row| row.open).collect::<Vec<_>>();
    let high = rows.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = rows.iter().map(|row| row.low).collect::<Vec<_>>();
    let close = rows.iter().map(|row| row.close).collect::<Vec<_>>();
    let source_dates = vec![source_date.to_string(); rows.len()];
    let run_tags = vec![run_tag.to_string(); rows.len()];
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            u64_array(&timestamp_us),
            string_array(&timestamp_utc),
            string_array(&underlying),
            f64_values_array(&open),
            f64_values_array(&high),
            f64_values_array(&low),
            f64_values_array(&close),
            string_array(&source_dates),
            string_array(&run_tags),
        ],
    )?;
    write_parquet_part(path, schema, batch)?;
    Ok(())
}

fn options_snapshot_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("timestamp_us", DataType::UInt64, false),
        Field::new("timestamp_utc", DataType::Utf8, false),
        Field::new("underlying", DataType::Utf8, false),
        Field::new("expiry", DataType::Utf8, false),
        Field::new("strike", DataType::Float64, false),
        Field::new("is_call", DataType::Boolean, false),
        Field::new("underlying_price", DataType::Float64, false),
        Field::new("bid_price", DataType::Float64, false),
        Field::new("ask_price", DataType::Float64, false),
        Field::new("mark_price", DataType::Float64, false),
        Field::new("mark_iv", DataType::Float64, false),
        Field::new("delta", DataType::Float64, false),
        Field::new("source_date", DataType::Utf8, false),
        Field::new("run_tag", DataType::Utf8, false),
    ]))
}

fn index_ohlc_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("timestamp_us", DataType::UInt64, false),
        Field::new("timestamp_utc", DataType::Utf8, false),
        Field::new("underlying", DataType::Utf8, false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("source_date", DataType::Utf8, false),
        Field::new("run_tag", DataType::Utf8, false),
    ]))
}

fn parse_tardis_api_key_from_file(path: &Path) -> Result<String> {
    let text =
        fs::read_to_string(path).with_context(|| format!("failed to read {}", path.display()))?;
    parse_tardis_api_key_from_str(&text)
}

fn parse_tardis_api_key_from_str(text: &str) -> Result<String> {
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('#') || !trimmed.contains('=') {
            continue;
        }
        let Some((name, value)) = trimmed.split_once('=') else {
            continue;
        };
        if name.trim() == "TARDIS_API_KEY" {
            let key = value
                .trim()
                .trim_matches('"')
                .trim_matches('\'')
                .to_string();
            if key.len() < 20 {
                bail!("TARDIS_API_KEY is present but too short");
            }
            return Ok(key);
        }
    }
    bail!("TARDIS_API_KEY not found")
}

fn parse_option_symbol(symbol: &str) -> Option<ParsedOptionSymbol> {
    let mut parts = symbol.trim().split('-');
    let underlying = parts.next()?.to_ascii_uppercase();
    let expiry = parts.next()?.to_ascii_uppercase();
    let strike = parts.next()?.parse::<f64>().ok()?;
    let side = parts.next()?.trim().to_ascii_uppercase();
    if parts.next().is_some() {
        return None;
    }
    let is_call = match side.as_str() {
        "C" => true,
        "P" => false,
        _ => return None,
    };
    Some(ParsedOptionSymbol {
        underlying,
        expiry,
        strike,
        is_call,
    })
}

fn parse_deribit_expiry(expiry: &str) -> Option<NaiveDate> {
    let value = expiry.trim().to_ascii_uppercase();
    let day_digits = value
        .chars()
        .take_while(|ch| ch.is_ascii_digit())
        .collect::<String>();
    if day_digits.is_empty() || value.len() < day_digits.len() + 5 {
        return None;
    }
    let rest = &value[day_digits.len()..];
    let month = &rest[..3];
    let year = &rest[3..];
    if year.len() != 2 {
        return None;
    }
    let month_num = match month {
        "JAN" => 1,
        "FEB" => 2,
        "MAR" => 3,
        "APR" => 4,
        "MAY" => 5,
        "JUN" => 6,
        "JUL" => 7,
        "AUG" => 8,
        "SEP" => 9,
        "OCT" => 10,
        "NOV" => 11,
        "DEC" => 12,
        _ => return None,
    };
    NaiveDate::from_ymd_opt(
        2000 + year.parse::<i32>().ok()?,
        month_num,
        day_digits.parse::<u32>().ok()?,
    )
}

fn cached_dte(
    cache: &mut BTreeMap<String, Option<i64>>,
    expiry: &str,
    trade_date: NaiveDate,
) -> Option<i64> {
    if let Some(value) = cache.get(expiry) {
        return *value;
    }
    let value =
        parse_deribit_expiry(expiry).map(|date| date.signed_duration_since(trade_date).num_days());
    cache.insert(expiry.to_string(), value);
    value
}

fn clean_quote(mut quote: QuoteState) -> QuoteState {
    if quote.bid_price.is_finite()
        && quote.ask_price.is_finite()
        && quote.bid_price > 0.0
        && quote.ask_price > 0.0
        && quote.ask_price < quote.bid_price
    {
        std::mem::swap(&mut quote.bid_price, &mut quote.ask_price);
    }
    if quote.mark_price.is_finite()
        && quote.bid_price.is_finite()
        && quote.ask_price.is_finite()
        && quote.bid_price > 0.0
        && quote.ask_price > 0.0
    {
        if quote.mark_price < quote.bid_price {
            quote.mark_price = quote.bid_price;
        }
        if quote.mark_price > quote.ask_price {
            quote.mark_price = quote.ask_price;
        }
    }
    quote
}

fn option_column_indexes(headers: &csv::StringRecord) -> Result<ColumnIndexes> {
    Ok(ColumnIndexes {
        symbol: header_index(headers, "symbol")?,
        timestamp: header_index(headers, "timestamp")?,
        bid_price: header_index(headers, "bid_price")?,
        ask_price: header_index(headers, "ask_price")?,
        mark_price: header_index(headers, "mark_price")?,
        mark_iv: header_index(headers, "mark_iv")?,
        underlying_price: header_index(headers, "underlying_price")?,
        delta: header_index(headers, "delta")?,
    })
}

fn index_column_indexes(headers: &csv::StringRecord) -> Result<IndexColumnIndexes> {
    Ok(IndexColumnIndexes {
        timestamp: header_index(headers, "timestamp")?,
        index_price: header_index(headers, "index_price")?,
    })
}

fn header_index(headers: &csv::StringRecord, name: &str) -> Result<usize> {
    headers
        .iter()
        .position(|value| value == name)
        .ok_or_else(|| anyhow!("missing CSV column {name}"))
}

fn parse_u64_field(record: &csv::StringRecord, index: usize) -> Result<u64> {
    record
        .get(index)
        .unwrap_or_default()
        .trim()
        .parse::<u64>()
        .with_context(|| format!("invalid u64 at column {index}"))
}

fn parse_f64_field(record: &csv::StringRecord, index: usize) -> f64 {
    record
        .get(index)
        .unwrap_or_default()
        .trim()
        .parse::<f64>()
        .unwrap_or(f64::NAN)
}

fn last_boundary_rows(
    rows: &OptionSnapshotRows,
    date: NaiveDate,
    interval_min: u64,
) -> Result<Vec<OptionSnapshotRow>> {
    let boundary = day_start_us(date) + 24 * 3_600 * 1_000_000 - interval_min * 60 * 1_000_000;
    let out = rows
        .rows
        .iter()
        .filter(|row| row.timestamp_us == boundary)
        .cloned()
        .collect::<Vec<_>>();
    if out.is_empty() {
        bail!("no last-boundary rows found for {date}");
    }
    Ok(out)
}

fn row_key(row: &OptionSnapshotRow) -> OptionKey {
    OptionKey {
        underlying: row.underlying.clone(),
        expiry: row.expiry.clone(),
        strike_micros: strike_key(row.strike),
        is_call: row.is_call,
    }
}

fn strike_key(strike: f64) -> i64 {
    (strike * 1_000_000.0).round() as i64
}

fn day_start_us(date: NaiveDate) -> u64 {
    date.and_hms_opt(0, 0, 0)
        .expect("valid midnight")
        .and_utc()
        .timestamp_micros() as u64
}

fn utc_from_micros(timestamp_us: u64) -> Result<String> {
    let secs = (timestamp_us / 1_000_000) as i64;
    let nanos = ((timestamp_us % 1_000_000) * 1_000) as u32;
    Ok(Utc
        .timestamp_opt(secs, nanos)
        .single()
        .ok_or_else(|| anyhow!("invalid timestamp_us {timestamp_us}"))?
        .to_rfc3339_opts(chrono::SecondsFormat::Micros, true))
}

fn f64_values_array(values: &[f64]) -> ArrayRef {
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        builder.append_value(*value);
    }
    Arc::new(builder.finish())
}

fn temp_download_path(path: &Path) -> PathBuf {
    PathBuf::from(format!("{}.part", path.display()))
}

fn retry_delay(attempt: usize) -> Duration {
    let seconds = [10, 30, 60, 120, 300][attempt.saturating_sub(1).min(4)];
    Duration::from_secs(seconds)
}

fn is_retryable_error(message: &str) -> bool {
    !message.contains("non-retryable HTTP")
}

fn date_range(from: NaiveDate, to: NaiveDate) -> Result<Vec<NaiveDate>> {
    if from > to {
        bail!("from-date {from} is after to-date {to}");
    }
    let mut out = Vec::new();
    let mut current = from;
    while current <= to {
        out.push(current);
        current = current
            .succ_opt()
            .ok_or_else(|| anyhow!("date overflow after {current}"))?;
    }
    Ok(out)
}

fn normalized_underlyings(values: &[String]) -> Result<Vec<String>> {
    let mut out = Vec::new();
    for value in values {
        let value = value.trim().to_ascii_uppercase();
        if value.is_empty() {
            continue;
        }
        if value != "BTC" && value != "ETH" {
            bail!("unsupported underlying {value}; v0 supports BTC,ETH");
        }
        if !out.contains(&value) {
            out.push(value);
        }
    }
    if out.is_empty() {
        bail!("at least one underlying is required");
    }
    Ok(out)
}

fn validate_config(config: &TardisDeribitFetchConfig) -> Result<()> {
    if config.snapshot_interval_min == 0 {
        bail!("snapshot_interval_min must be > 0");
    }
    if config.index_interval_min == 0 {
        bail!("index_interval_min must be > 0");
    }
    if config.max_dte < 0 {
        bail!("max_dte must be >= 0");
    }
    normalized_underlyings(&config.underlyings)?;
    date_range(config.from_date, config.to_date)?;
    Ok(())
}

fn options_chain_url(date: NaiveDate) -> String {
    format!(
        "{DATASETS_BASE}/deribit/options_chain/{:04}/{:02}/{:02}/OPTIONS.csv.gz",
        date.year(),
        date.month(),
        date.day()
    )
}

fn derivative_ticker_url(date: NaiveDate, underlying: &str) -> String {
    format!(
        "{DATASETS_BASE}/deribit/derivative_ticker/{:04}/{:02}/{:02}/{}-PERPETUAL.csv.gz",
        date.year(),
        date.month(),
        date.day(),
        underlying.to_ascii_uppercase()
    )
}

fn options_raw_path(data_root: &Path, date: NaiveDate) -> PathBuf {
    data_root
        .join(RAW_DIR)
        .join(OPTIONS_DATASET)
        .join(format!("dt={date}"))
        .join("OPTIONS.csv.gz")
}

fn derivative_ticker_raw_path(data_root: &Path, date: NaiveDate, underlying: &str) -> PathBuf {
    data_root
        .join(RAW_DIR)
        .join(INDEX_DATASET)
        .join(format!("dt={date}"))
        .join(format!(
            "{}-PERPETUAL.csv.gz",
            underlying.to_ascii_uppercase()
        ))
}

fn options_snapshot_parquet_path(data_root: &Path, date: NaiveDate, run_tag: &str) -> PathBuf {
    custom_part_path(
        data_root,
        DERIVED_DIR,
        SNAPSHOT_DATASET,
        &date.to_string(),
        &format!("{SNAPSHOT_DATASET}_{run_tag}_{date}"),
    )
}

fn index_ohlc_parquet_path(data_root: &Path, date: NaiveDate, run_tag: &str) -> PathBuf {
    custom_part_path(
        data_root,
        DERIVED_DIR,
        INDEX_OHLC_DATASET,
        &date.to_string(),
        &format!("{INDEX_OHLC_DATASET}_{run_tag}_{date}"),
    )
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn write_completion_json(path: &Path, summary: &TardisDeribitFetchSummary) -> Result<()> {
    ensure_parent_dir(path)?;
    let file =
        File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, summary)
        .with_context(|| format!("failed to write {}", path.display()))
}

fn remove_file_if_exists(path: &Path) -> Result<()> {
    if path.exists() {
        fs::remove_file(path).with_context(|| format!("failed to remove {}", path.display()))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn tardis_api_key_parser_reads_single_line_without_printing_secret() {
        let text = "A=1\nTARDIS_API_KEY=\"TD.abcdefghijklmnopqrstuvwxyz0123456789\"\n";
        let key = parse_tardis_api_key_from_str(text).unwrap();
        assert_eq!(key.len(), 39);
        assert!(key.starts_with("TD."));
    }

    #[test]
    fn deribit_option_symbol_parser_handles_btc_and_eth() {
        let btc = parse_option_symbol("BTC-1MAY25-95000-C").unwrap();
        assert_eq!(btc.underlying, "BTC");
        assert_eq!(btc.expiry, "1MAY25");
        assert_eq!(btc.strike, 95000.0);
        assert!(btc.is_call);

        let eth = parse_option_symbol("ETH-2MAY25-1800-P").unwrap();
        assert_eq!(eth.underlying, "ETH");
        assert_eq!(eth.expiry, "2MAY25");
        assert_eq!(eth.strike, 1800.0);
        assert!(!eth.is_call);
    }

    #[test]
    fn clean_quote_swaps_crossed_market_and_clamps_mark() {
        let quote = clean_quote(QuoteState {
            underlying_price: 100.0,
            bid_price: 2.0,
            ask_price: 1.0,
            mark_price: 3.0,
            mark_iv: 0.6,
            delta: 0.5,
        });
        assert_eq!(quote.bid_price, 1.0);
        assert_eq!(quote.ask_price, 2.0);
        assert_eq!(quote.mark_price, 2.0);
    }

    #[test]
    fn index_ohlc_aggregates_one_minute_bars() {
        let csv = concat!(
            "timestamp,index_price\n",
            "1746057600000000,100\n",
            "1746057610000000,110\n",
            "1746057660000000,105\n"
        );
        let date = NaiveDate::from_ymd_opt(2025, 5, 1).unwrap();
        let result = extract_index_ohlc_from_csv_reader(Cursor::new(csv), date, "BTC", 1).unwrap();
        assert_eq!(result.rows.len(), 2);
        assert_eq!(result.rows[0].open, 100.0);
        assert_eq!(result.rows[0].high, 110.0);
        assert_eq!(result.rows[0].low, 100.0);
        assert_eq!(result.rows[0].close, 110.0);
    }

    #[test]
    fn options_extract_flushes_boundaries_and_rescales_iv() {
        let csv = concat!(
            "symbol,timestamp,bid_price,ask_price,mark_price,mark_iv,underlying_price,delta\n",
            "BTC-1MAY25-95000-C,1746057600000000,1,2,1.5,0.6,95000,0.5\n",
            "BTC-1MAY25-90000-P,1746057900000000,3,2,1,0.7,95000,-0.5\n"
        );
        let date = NaiveDate::from_ymd_opt(2025, 5, 1).unwrap();
        let underlyings = vec!["BTC".to_string()];
        let result =
            extract_options_from_csv_reader(Cursor::new(csv), date, &underlyings, 5, 700, None, 0)
                .unwrap();
        assert!(result.rows.rows.len() >= 2);
        assert!(result.iv_rescaled);
        assert!(result.rows.rows.iter().any(|row| row.quote.mark_iv >= 60.0));
        assert!(
            result
                .rows
                .rows
                .iter()
                .any(|row| row.quote.bid_price == 2.0 && row.quote.ask_price == 3.0)
        );
    }

    #[test]
    fn midnight_fixup_adds_missing_previous_instruments() {
        let date = NaiveDate::from_ymd_opt(2025, 5, 2).unwrap();
        let prev = vec![OptionSnapshotRow {
            timestamp_us: day_start_us(NaiveDate::from_ymd_opt(2025, 5, 1).unwrap())
                + 23 * 3_600 * 1_000_000
                + 55 * 60 * 1_000_000,
            underlying: "BTC".to_string(),
            expiry: "2MAY25".to_string(),
            strike: 100000.0,
            is_call: true,
            quote: QuoteState {
                underlying_price: 99000.0,
                bid_price: 1.0,
                ask_price: 2.0,
                mark_price: 1.5,
                mark_iv: 60.0,
                delta: 0.5,
            },
        }];
        let mut rows = OptionSnapshotRows::default();
        let added = apply_midnight_fixup(&mut rows, date, &prev);
        assert_eq!(added, 1);
        assert_eq!(rows.rows[0].timestamp_us, day_start_us(date));
    }
}

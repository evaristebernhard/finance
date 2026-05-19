use std::collections::{BTreeMap, HashMap, VecDeque};
use std::fs::{self, File};
use std::hash::{Hash, Hasher};
use std::io::{Cursor, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{ArrayRef, Float64Builder};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{Datelike, NaiveDate, SecondsFormat, TimeZone, Utc};
use finance_chain_core::storage::{ensure_parent_dir, string_array, u64_array};
use parquet::arrow::ArrowWriter;
use parquet::file::properties::WriterProperties;
use reqwest::blocking::Client;
use reqwest::header::{ACCEPT, HeaderMap, HeaderValue, USER_AGENT};
use serde::Serialize;
use zip::ZipArchive;

use crate::download::{parse_symbol_list, path_string};

pub const DEFAULT_PRICE_CONTEXT_RUN_TAG: &str = "20260513_bullish_l2_basket_price_v1";
pub const DEFAULT_BINANCE_KLINE_SYMBOLS: &str = concat!(
    "BONKUSDT,BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,",
    "PEPEUSDT,SHIBUSDT,WIFUSDT,SUIUSDT,",
    "APTUSDT,ARBUSDT,OPUSDT,PENGUUSDT"
);

const BINANCE_BASE: &str = "https://data.binance.vision/data/spot/daily/klines";
const USER_AGENT_VALUE: &str = "finance-chain-bonk-price-context/0.1";

#[derive(Debug, Clone)]
pub struct PriceContextConfig {
    pub data_root: PathBuf,
    pub local_kline_dir: PathBuf,
    pub date_dir: PathBuf,
    pub from_date: NaiveDate,
    pub to_date: NaiveDate,
    pub symbols: String,
    pub run_tag: String,
    pub workers: usize,
    pub timeout_seconds: u64,
    pub no_download: bool,
    pub force_download: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct PriceContextOutputs {
    pub price_context_parquet: String,
    pub quality_csv: String,
    pub summary_csv: String,
    pub completion_json: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PriceContextRows {
    pub price_context: usize,
    pub quality: usize,
    pub summary: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct PriceContextSummary {
    pub run_tag: String,
    pub finished_at_utc: String,
    pub elapsed_seconds: f64,
    pub from_date: String,
    pub to_date: String,
    pub symbols: Vec<String>,
    pub outputs: PriceContextOutputs,
    pub rows: PriceContextRows,
    pub raw_fingerprint: PriceRawFingerprint,
}

#[derive(Debug, Clone, Serialize)]
pub struct PriceRawFingerprint {
    pub file_count: usize,
    pub total_bytes: u64,
    pub hash: String,
}

#[derive(Debug, Clone)]
struct OutputPaths {
    price_context_parquet: PathBuf,
    quality_csv: PathBuf,
    summary_csv: PathBuf,
    completion_json: PathBuf,
}

#[derive(Debug, Clone)]
struct KlineJob {
    symbol: String,
    day: NaiveDate,
}

#[derive(Debug)]
struct KlineFileResult {
    quality: PriceQualityRow,
    rows: Vec<BaseKlineRow>,
}

#[derive(Debug, Clone, Serialize)]
struct PriceQualityRow {
    symbol: String,
    asset: String,
    date: String,
    source: String,
    path: String,
    url: String,
    status: String,
    bytes: u64,
    rows: u64,
    timestamp_min_us: Option<u64>,
    timestamp_max_us: Option<u64>,
    duplicate_minutes: u64,
    nonpositive_ohlc_rows: u64,
    negative_volume_rows: u64,
    error: String,
}

#[derive(Debug, Clone)]
struct BaseKlineRow {
    timestamp_us: u64,
    timestamp_utc: String,
    symbol: String,
    asset: String,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    quote_volume: f64,
    trade_count: u64,
    ret_1m_bps: Option<f64>,
    rv_15m_bps: Option<f64>,
    rv_1h_bps: Option<f64>,
    rv_4h_bps: Option<f64>,
    rv_12h_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct PriceContextRow {
    run_tag: String,
    timestamp_us: u64,
    timestamp_utc: String,
    symbol: String,
    asset: String,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    quote_volume: f64,
    trade_count: u64,
    ret_1m_bps: Option<f64>,
    rv_15m_bps: Option<f64>,
    rv_1h_bps: Option<f64>,
    rv_4h_bps: Option<f64>,
    rv_12h_bps: Option<f64>,
    market_return_bps: Option<f64>,
    meme_return_bps: Option<f64>,
    alt_return_bps: Option<f64>,
    sol_return_bps: Option<f64>,
    bonk_return_bps: Option<f64>,
    bonk_rel_market_bps: Option<f64>,
    bonk_rel_meme_bps: Option<f64>,
    bonk_rel_sol_bps: Option<f64>,
    bonk_beta_market_60m: Option<f64>,
    bonk_corr_market_60m: Option<f64>,
    bonk_beta_meme_60m: Option<f64>,
    bonk_corr_meme_60m: Option<f64>,
    bonk_beta_sol_60m: Option<f64>,
    bonk_corr_sol_60m: Option<f64>,
    bonk_beta_market_240m: Option<f64>,
    bonk_corr_market_240m: Option<f64>,
    bonk_beta_meme_240m: Option<f64>,
    bonk_corr_meme_240m: Option<f64>,
    bonk_beta_sol_240m: Option<f64>,
    bonk_corr_sol_240m: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct PriceSummaryRow {
    symbol: String,
    asset: String,
    expected_minutes: u64,
    rows: u64,
    first_timestamp_utc: String,
    last_timestamp_utc: String,
    missing_minutes: u64,
    duplicate_minutes: u64,
    nonpositive_ohlc_rows: u64,
    negative_volume_rows: u64,
    source_files: u64,
    missing_files: u64,
    downloaded_files: u64,
    median_close: Option<f64>,
    median_rv_1h_bps: Option<f64>,
    total_quote_volume: f64,
    total_return_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct MinuteContext {
    market_return_bps: Option<f64>,
    meme_return_bps: Option<f64>,
    alt_return_bps: Option<f64>,
    sol_return_bps: Option<f64>,
    bonk_return_bps: Option<f64>,
    bonk_beta_market_60m: Option<f64>,
    bonk_corr_market_60m: Option<f64>,
    bonk_beta_meme_60m: Option<f64>,
    bonk_corr_meme_60m: Option<f64>,
    bonk_beta_sol_60m: Option<f64>,
    bonk_corr_sol_60m: Option<f64>,
    bonk_beta_market_240m: Option<f64>,
    bonk_corr_market_240m: Option<f64>,
    bonk_beta_meme_240m: Option<f64>,
    bonk_corr_meme_240m: Option<f64>,
    bonk_beta_sol_240m: Option<f64>,
    bonk_corr_sol_240m: Option<f64>,
}

pub fn run_price_context(config: &PriceContextConfig) -> Result<PriceContextSummary> {
    if config.from_date > config.to_date {
        bail!(
            "--from-date {} is after --to-date {}",
            config.from_date,
            config.to_date
        );
    }
    if config.workers == 0 {
        bail!("--workers must be >= 1");
    }
    let started = Instant::now();
    let symbols = parse_symbol_list(&config.symbols);
    if symbols.is_empty() {
        bail!("at least one symbol is required");
    }
    let paths = output_paths(config);
    for path in [
        &paths.price_context_parquet,
        &paths.quality_csv,
        &paths.summary_csv,
        &paths.completion_json,
    ] {
        ensure_parent_dir(path)?;
    }

    let jobs = build_jobs(&symbols, config.from_date, config.to_date);
    eprintln!(
        "[bonk_cex_price_context] process {} symbol-days with {} workers",
        jobs.len(),
        config.workers
    );
    let results = process_jobs(jobs, config)?;
    let mut quality = Vec::with_capacity(results.len());
    let mut rows = Vec::<BaseKlineRow>::new();
    for result in results {
        quality.push(result.quality);
        rows.extend(result.rows);
    }
    quality.sort_by(|a, b| a.symbol.cmp(&b.symbol).then_with(|| a.date.cmp(&b.date)));
    rows.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
    });
    dedup_rows(&mut rows);
    add_returns_and_rv(&mut rows);
    let context = build_context_rows(&config.run_tag, &rows);
    let summary_rows = build_summary(config, &symbols, &context, &quality);

    write_price_context_parquet(&paths.price_context_parquet, &context)?;
    write_csv_atomic(&paths.quality_csv, &quality)?;
    write_csv_atomic(&paths.summary_csv, &summary_rows)?;
    let outputs = PriceContextOutputs {
        price_context_parquet: path_string(&paths.price_context_parquet),
        quality_csv: path_string(&paths.quality_csv),
        summary_csv: path_string(&paths.summary_csv),
        completion_json: path_string(&paths.completion_json),
    };
    let summary = PriceContextSummary {
        run_tag: config.run_tag.clone(),
        finished_at_utc: utc_now_string(),
        elapsed_seconds: started.elapsed().as_secs_f64(),
        from_date: config.from_date.to_string(),
        to_date: config.to_date.to_string(),
        symbols,
        rows: PriceContextRows {
            price_context: context.len(),
            quality: quality.len(),
            summary: summary_rows.len(),
        },
        outputs,
        raw_fingerprint: fingerprint_quality(&quality),
    };
    write_json_atomic(&paths.completion_json, &summary)?;
    Ok(summary)
}

fn process_jobs(jobs: Vec<KlineJob>, config: &PriceContextConfig) -> Result<Vec<KlineFileResult>> {
    let total = jobs.len();
    let queue = Arc::new(Mutex::new(VecDeque::from(jobs)));
    let results = Arc::new(Mutex::new(Vec::new()));
    let client = Arc::new(build_client(config.timeout_seconds)?);
    let workers = total.min(config.workers).max(1);
    let mut handles = Vec::with_capacity(workers);
    for _ in 0..workers {
        let queue = Arc::clone(&queue);
        let results = Arc::clone(&results);
        let client = Arc::clone(&client);
        let config = config.clone();
        handles.push(thread::spawn(move || -> Result<()> {
            loop {
                let job = {
                    let mut guard = queue.lock().unwrap();
                    guard.pop_front()
                };
                let Some(job) = job else {
                    break;
                };
                let result = process_job(&job, &config, &client)
                    .with_context(|| format!("failed to process {} {}", job.symbol, job.day))?;
                eprintln!(
                    "[bonk_cex_price_context] {} {} status={} rows={}",
                    result.quality.date,
                    result.quality.symbol,
                    result.quality.status,
                    result.quality.rows
                );
                results.lock().unwrap().push(result);
            }
            Ok(())
        }));
    }
    for handle in handles {
        handle
            .join()
            .map_err(|_| anyhow!("price context worker panicked"))??;
    }
    let mut guard = results.lock().unwrap();
    Ok(std::mem::take(&mut *guard))
}

fn process_job(
    job: &KlineJob,
    config: &PriceContextConfig,
    client: &Client,
) -> Result<KlineFileResult> {
    let raw_daily = raw_daily_path(&config.data_root, &job.symbol, job.day);
    let (path, source, status, url, error) = resolve_or_download(job, config, client, &raw_daily)?;
    let asset = asset_from_symbol(&job.symbol);
    let mut quality = PriceQualityRow {
        symbol: job.symbol.clone(),
        asset,
        date: job.day.to_string(),
        source,
        path: path
            .as_ref()
            .map(|path| path_string(path.as_path()))
            .unwrap_or_default(),
        url,
        status,
        bytes: path
            .as_ref()
            .and_then(|path| path.metadata().ok().map(|meta| meta.len()))
            .unwrap_or(0),
        rows: 0,
        timestamp_min_us: None,
        timestamp_max_us: None,
        duplicate_minutes: 0,
        nonpositive_ohlc_rows: 0,
        negative_volume_rows: 0,
        error,
    };
    let Some(path) = path else {
        return Ok(KlineFileResult {
            quality,
            rows: Vec::new(),
        });
    };
    let mut rows = Vec::new();
    match read_kline_csv(&path, &job.symbol, job.day) {
        Ok((parsed, stats)) => {
            quality.rows = parsed.len() as u64;
            quality.timestamp_min_us = stats.timestamp_min_us;
            quality.timestamp_max_us = stats.timestamp_max_us;
            quality.duplicate_minutes = stats.duplicate_minutes;
            quality.nonpositive_ohlc_rows = stats.nonpositive_ohlc_rows;
            quality.negative_volume_rows = stats.negative_volume_rows;
            rows = parsed;
        }
        Err(err) => {
            quality.status = "error".to_string();
            quality.error = err.to_string();
        }
    }
    Ok(KlineFileResult { quality, rows })
}

fn resolve_or_download(
    job: &KlineJob,
    config: &PriceContextConfig,
    client: &Client,
    raw_daily: &Path,
) -> Result<(Option<PathBuf>, String, String, String, String)> {
    let url = binance_daily_url(&job.symbol, job.day);
    if !config.force_download {
        if raw_daily.exists() {
            return Ok((
                Some(raw_daily.to_path_buf()),
                "bonk_binance_spot_daily".to_string(),
                "skipped".to_string(),
                url,
                String::new(),
            ));
        }
        let local_daily = config
            .local_kline_dir
            .join(format!("{}-1m-{}.csv", job.symbol, job.day));
        if local_daily.exists() {
            return Ok((
                Some(local_daily),
                "local_binance_daily".to_string(),
                "skipped".to_string(),
                url,
                String::new(),
            ));
        }
        let local_monthly = config.local_kline_dir.join(format!(
            "{}-1m-{:04}-{:02}.csv",
            job.symbol,
            job.day.year(),
            job.day.month()
        ));
        if local_monthly.exists() {
            return Ok((
                Some(local_monthly),
                "local_binance_monthly".to_string(),
                "skipped".to_string(),
                url,
                String::new(),
            ));
        }
    }
    if config.no_download {
        return Ok((
            None,
            "binance_public_daily".to_string(),
            "missing".to_string(),
            url,
            "download disabled".to_string(),
        ));
    }
    match download_binance_daily_csv(client, &url, raw_daily) {
        Ok(()) => Ok((
            Some(raw_daily.to_path_buf()),
            "binance_public_daily".to_string(),
            "downloaded".to_string(),
            url,
            String::new(),
        )),
        Err(DownloadFailure::Missing(message)) => Ok((
            None,
            "binance_public_daily".to_string(),
            "missing".to_string(),
            url,
            message,
        )),
        Err(DownloadFailure::Other(message)) => Ok((
            None,
            "binance_public_daily".to_string(),
            "error".to_string(),
            url,
            message,
        )),
    }
}

#[derive(Debug)]
enum DownloadFailure {
    Missing(String),
    Other(String),
}

fn download_binance_daily_csv(
    client: &Client,
    url: &str,
    path: &Path,
) -> std::result::Result<(), DownloadFailure> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| DownloadFailure::Other(err.to_string()))?;
    }
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static(USER_AGENT_VALUE));
    headers.insert(ACCEPT, HeaderValue::from_static("application/zip,*/*"));
    let response = client
        .get(url)
        .headers(headers)
        .send()
        .map_err(|err| DownloadFailure::Other(err.to_string()))?;
    let status = response.status();
    if status.as_u16() == 404 {
        return Err(DownloadFailure::Missing("HTTP 404".to_string()));
    }
    if !status.is_success() {
        return Err(DownloadFailure::Other(format!("HTTP {status}")));
    }
    let bytes = response
        .bytes()
        .map_err(|err| DownloadFailure::Other(err.to_string()))?;
    let cursor = Cursor::new(bytes);
    let mut archive =
        ZipArchive::new(cursor).map_err(|err| DownloadFailure::Other(err.to_string()))?;
    if archive.is_empty() {
        return Err(DownloadFailure::Other("empty zip archive".to_string()));
    }
    let mut csv_file = archive
        .by_index(0)
        .map_err(|err| DownloadFailure::Other(err.to_string()))?;
    let temp = temp_path_for(path);
    {
        let mut out = File::create(&temp).map_err(|err| DownloadFailure::Other(err.to_string()))?;
        std::io::copy(&mut csv_file, &mut out)
            .map_err(|err| DownloadFailure::Other(err.to_string()))?;
        out.flush()
            .map_err(|err| DownloadFailure::Other(err.to_string()))?;
    }
    replace_file(&temp, path).map_err(|err| DownloadFailure::Other(err.to_string()))?;
    Ok(())
}

#[derive(Debug, Default)]
struct ReadStats {
    timestamp_min_us: Option<u64>,
    timestamp_max_us: Option<u64>,
    duplicate_minutes: u64,
    nonpositive_ohlc_rows: u64,
    negative_volume_rows: u64,
}

fn read_kline_csv(
    path: &Path,
    symbol: &str,
    day: NaiveDate,
) -> Result<(Vec<BaseKlineRow>, ReadStats)> {
    let text =
        fs::read_to_string(path).with_context(|| format!("failed to read {}", path.display()))?;
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(true)
        .from_reader(text.as_bytes());
    let start_us = date_start_us(day)?;
    let end_us = date_start_us(day.succ_opt().ok_or_else(|| anyhow!("date overflow"))?)?;
    let mut seen = BTreeMap::<u64, ()>::new();
    let mut stats = ReadStats::default();
    let mut out = Vec::new();
    for record in reader.records() {
        let record = record.with_context(|| format!("failed to parse {}", path.display()))?;
        if record.len() < 11 {
            continue;
        }
        let Some(ts_raw) = parse_u64(record.get(0).unwrap_or_default()) else {
            continue;
        };
        let Some(timestamp_us) = normalize_epoch_to_us(ts_raw) else {
            continue;
        };
        if timestamp_us < start_us || timestamp_us >= end_us {
            continue;
        }
        if seen.insert(timestamp_us, ()).is_some() {
            stats.duplicate_minutes += 1;
        }
        let open = parse_f64(record.get(1).unwrap_or_default()).unwrap_or(f64::NAN);
        let high = parse_f64(record.get(2).unwrap_or_default()).unwrap_or(f64::NAN);
        let low = parse_f64(record.get(3).unwrap_or_default()).unwrap_or(f64::NAN);
        let close = parse_f64(record.get(4).unwrap_or_default()).unwrap_or(f64::NAN);
        let volume = parse_f64(record.get(5).unwrap_or_default()).unwrap_or(f64::NAN);
        let quote_volume = parse_f64(record.get(7).unwrap_or_default()).unwrap_or(f64::NAN);
        let trade_count = parse_u64(record.get(8).unwrap_or_default()).unwrap_or(0);
        if [open, high, low, close]
            .iter()
            .any(|value| !value.is_finite() || *value <= 0.0)
        {
            stats.nonpositive_ohlc_rows += 1;
        }
        if !volume.is_finite() || volume < 0.0 || !quote_volume.is_finite() || quote_volume < 0.0 {
            stats.negative_volume_rows += 1;
        }
        stats.timestamp_min_us = Some(
            stats
                .timestamp_min_us
                .map_or(timestamp_us, |value| value.min(timestamp_us)),
        );
        stats.timestamp_max_us = Some(
            stats
                .timestamp_max_us
                .map_or(timestamp_us, |value| value.max(timestamp_us)),
        );
        out.push(BaseKlineRow {
            timestamp_us,
            timestamp_utc: utc_from_us(timestamp_us)?,
            symbol: symbol.to_string(),
            asset: asset_from_symbol(symbol),
            open,
            high,
            low,
            close,
            volume,
            quote_volume,
            trade_count,
            ret_1m_bps: None,
            rv_15m_bps: None,
            rv_1h_bps: None,
            rv_4h_bps: None,
            rv_12h_bps: None,
        });
    }
    Ok((out, stats))
}

fn dedup_rows(rows: &mut Vec<BaseKlineRow>) {
    rows.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
    });
    rows.dedup_by(|a, b| a.symbol == b.symbol && a.timestamp_us == b.timestamp_us);
}

fn add_returns_and_rv(rows: &mut [BaseKlineRow]) {
    let mut start = 0usize;
    while start < rows.len() {
        let symbol = rows[start].symbol.clone();
        let mut end = start + 1;
        while end < rows.len() && rows[end].symbol == symbol {
            end += 1;
        }
        let slice = &mut rows[start..end];
        let mut prev_close = None::<f64>;
        for row in slice.iter_mut() {
            row.ret_1m_bps = prev_close.zip(finite(row.close)).and_then(|(prev, close)| {
                if prev > 0.0 && close > 0.0 {
                    finite((close / prev).ln() * 10_000.0)
                } else {
                    None
                }
            });
            if row.close.is_finite() && row.close > 0.0 {
                prev_close = Some(row.close);
            }
        }
        let returns = slice.iter().map(|row| row.ret_1m_bps).collect::<Vec<_>>();
        for idx in 0..slice.len() {
            slice[idx].rv_15m_bps = trailing_rv(&returns, idx, 15);
            slice[idx].rv_1h_bps = trailing_rv(&returns, idx, 60);
            slice[idx].rv_4h_bps = trailing_rv(&returns, idx, 240);
            slice[idx].rv_12h_bps = trailing_rv(&returns, idx, 720);
        }
        start = end;
    }
}

fn build_context_rows(run_tag: &str, rows: &[BaseKlineRow]) -> Vec<PriceContextRow> {
    let mut by_minute_symbol = BTreeMap::<u64, HashMap<String, &BaseKlineRow>>::new();
    for row in rows {
        by_minute_symbol
            .entry(row.timestamp_us)
            .or_default()
            .insert(row.symbol.clone(), row);
    }
    let mut minute_context = BTreeMap::<u64, MinuteContext>::new();
    let mut bonk_series = Vec::<Option<f64>>::new();
    let mut market_series = Vec::<Option<f64>>::new();
    let mut meme_series = Vec::<Option<f64>>::new();
    let mut sol_series = Vec::<Option<f64>>::new();
    let minutes = by_minute_symbol.keys().copied().collect::<Vec<_>>();
    for minute in &minutes {
        let map = by_minute_symbol.get(minute).expect("minute exists");
        let market = average_returns(map, &["BTCUSDT", "ETHUSDT", "SOLUSDT"]);
        let meme = average_returns(map, &["DOGEUSDT", "PEPEUSDT", "SHIBUSDT", "WIFUSDT"]);
        let alt = average_returns(map, &["SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT"]);
        let sol = map.get("SOLUSDT").and_then(|row| row.ret_1m_bps);
        let bonk = map.get("BONKUSDT").and_then(|row| row.ret_1m_bps);
        bonk_series.push(bonk);
        market_series.push(market);
        meme_series.push(meme);
        sol_series.push(sol);
        minute_context.insert(
            *minute,
            MinuteContext {
                market_return_bps: market,
                meme_return_bps: meme,
                alt_return_bps: alt,
                sol_return_bps: sol,
                bonk_return_bps: bonk,
                bonk_beta_market_60m: None,
                bonk_corr_market_60m: None,
                bonk_beta_meme_60m: None,
                bonk_corr_meme_60m: None,
                bonk_beta_sol_60m: None,
                bonk_corr_sol_60m: None,
                bonk_beta_market_240m: None,
                bonk_corr_market_240m: None,
                bonk_beta_meme_240m: None,
                bonk_corr_meme_240m: None,
                bonk_beta_sol_240m: None,
                bonk_corr_sol_240m: None,
            },
        );
    }
    for idx in 0..minutes.len() {
        let market_60 = rolling_beta_corr(&bonk_series, &market_series, idx, 60);
        let meme_60 = rolling_beta_corr(&bonk_series, &meme_series, idx, 60);
        let sol_60 = rolling_beta_corr(&bonk_series, &sol_series, idx, 60);
        let market_240 = rolling_beta_corr(&bonk_series, &market_series, idx, 240);
        let meme_240 = rolling_beta_corr(&bonk_series, &meme_series, idx, 240);
        let sol_240 = rolling_beta_corr(&bonk_series, &sol_series, idx, 240);
        if let Some(ctx) = minute_context.get_mut(&minutes[idx]) {
            ctx.bonk_beta_market_60m = market_60.0;
            ctx.bonk_corr_market_60m = market_60.1;
            ctx.bonk_beta_meme_60m = meme_60.0;
            ctx.bonk_corr_meme_60m = meme_60.1;
            ctx.bonk_beta_sol_60m = sol_60.0;
            ctx.bonk_corr_sol_60m = sol_60.1;
            ctx.bonk_beta_market_240m = market_240.0;
            ctx.bonk_corr_market_240m = market_240.1;
            ctx.bonk_beta_meme_240m = meme_240.0;
            ctx.bonk_corr_meme_240m = meme_240.1;
            ctx.bonk_beta_sol_240m = sol_240.0;
            ctx.bonk_corr_sol_240m = sol_240.1;
        }
    }
    let mut out = Vec::with_capacity(rows.len());
    for row in rows {
        let ctx = minute_context
            .get(&row.timestamp_us)
            .expect("minute context");
        out.push(PriceContextRow {
            run_tag: run_tag.to_string(),
            timestamp_us: row.timestamp_us,
            timestamp_utc: row.timestamp_utc.clone(),
            symbol: row.symbol.clone(),
            asset: row.asset.clone(),
            open: row.open,
            high: row.high,
            low: row.low,
            close: row.close,
            volume: row.volume,
            quote_volume: row.quote_volume,
            trade_count: row.trade_count,
            ret_1m_bps: row.ret_1m_bps,
            rv_15m_bps: row.rv_15m_bps,
            rv_1h_bps: row.rv_1h_bps,
            rv_4h_bps: row.rv_4h_bps,
            rv_12h_bps: row.rv_12h_bps,
            market_return_bps: ctx.market_return_bps,
            meme_return_bps: ctx.meme_return_bps,
            alt_return_bps: ctx.alt_return_bps,
            sol_return_bps: ctx.sol_return_bps,
            bonk_return_bps: ctx.bonk_return_bps,
            bonk_rel_market_bps: ctx
                .bonk_return_bps
                .zip(ctx.market_return_bps)
                .and_then(|(a, b)| finite(a - b)),
            bonk_rel_meme_bps: ctx
                .bonk_return_bps
                .zip(ctx.meme_return_bps)
                .and_then(|(a, b)| finite(a - b)),
            bonk_rel_sol_bps: ctx
                .bonk_return_bps
                .zip(ctx.sol_return_bps)
                .and_then(|(a, b)| finite(a - b)),
            bonk_beta_market_60m: ctx.bonk_beta_market_60m,
            bonk_corr_market_60m: ctx.bonk_corr_market_60m,
            bonk_beta_meme_60m: ctx.bonk_beta_meme_60m,
            bonk_corr_meme_60m: ctx.bonk_corr_meme_60m,
            bonk_beta_sol_60m: ctx.bonk_beta_sol_60m,
            bonk_corr_sol_60m: ctx.bonk_corr_sol_60m,
            bonk_beta_market_240m: ctx.bonk_beta_market_240m,
            bonk_corr_market_240m: ctx.bonk_corr_market_240m,
            bonk_beta_meme_240m: ctx.bonk_beta_meme_240m,
            bonk_corr_meme_240m: ctx.bonk_corr_meme_240m,
            bonk_beta_sol_240m: ctx.bonk_beta_sol_240m,
            bonk_corr_sol_240m: ctx.bonk_corr_sol_240m,
        });
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
    });
    out
}

fn build_summary(
    config: &PriceContextConfig,
    symbols: &[String],
    context: &[PriceContextRow],
    quality: &[PriceQualityRow],
) -> Vec<PriceSummaryRow> {
    let expected_minutes = config
        .to_date
        .signed_duration_since(config.from_date)
        .num_days()
        .saturating_add(1) as u64
        * 1440;
    let mut by_symbol = BTreeMap::<String, Vec<&PriceContextRow>>::new();
    for row in context {
        by_symbol.entry(row.symbol.clone()).or_default().push(row);
    }
    let mut quality_by_symbol = BTreeMap::<String, Vec<&PriceQualityRow>>::new();
    for row in quality {
        quality_by_symbol
            .entry(row.symbol.clone())
            .or_default()
            .push(row);
    }
    let mut out = Vec::new();
    for symbol in symbols {
        let rows = by_symbol.get(symbol).cloned().unwrap_or_default();
        let q = quality_by_symbol.get(symbol).cloned().unwrap_or_default();
        let total_return = rows.first().zip(rows.last()).and_then(|(first, last)| {
            if first.close > 0.0 && last.close > 0.0 {
                finite((last.close / first.close).ln() * 10_000.0)
            } else {
                None
            }
        });
        out.push(PriceSummaryRow {
            symbol: symbol.clone(),
            asset: asset_from_symbol(symbol),
            expected_minutes,
            rows: rows.len() as u64,
            first_timestamp_utc: rows
                .first()
                .map(|row| row.timestamp_utc.clone())
                .unwrap_or_default(),
            last_timestamp_utc: rows
                .last()
                .map(|row| row.timestamp_utc.clone())
                .unwrap_or_default(),
            missing_minutes: expected_minutes.saturating_sub(rows.len() as u64),
            duplicate_minutes: q.iter().map(|row| row.duplicate_minutes).sum(),
            nonpositive_ohlc_rows: q.iter().map(|row| row.nonpositive_ohlc_rows).sum(),
            negative_volume_rows: q.iter().map(|row| row.negative_volume_rows).sum(),
            source_files: q.iter().filter(|row| row.status != "missing").count() as u64,
            missing_files: q.iter().filter(|row| row.status == "missing").count() as u64,
            downloaded_files: q.iter().filter(|row| row.status == "downloaded").count() as u64,
            median_close: median(rows.iter().map(|row| row.close).collect()),
            median_rv_1h_bps: median(rows.iter().filter_map(|row| row.rv_1h_bps).collect()),
            total_quote_volume: rows.iter().filter_map(|row| finite(row.quote_volume)).sum(),
            total_return_bps: total_return,
        });
    }
    out
}

fn write_price_context_parquet(path: &Path, rows: &[PriceContextRow]) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("timestamp_utc", DataType::Utf8, false),
        Field::new("timestamp_us", DataType::UInt64, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("asset", DataType::Utf8, false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("volume", DataType::Float64, false),
        Field::new("quote_volume", DataType::Float64, false),
        Field::new("trade_count", DataType::UInt64, false),
        Field::new("ret_1m_bps", DataType::Float64, true),
        Field::new("rv_15m_bps", DataType::Float64, true),
        Field::new("rv_1h_bps", DataType::Float64, true),
        Field::new("rv_4h_bps", DataType::Float64, true),
        Field::new("rv_12h_bps", DataType::Float64, true),
        Field::new("market_return_bps", DataType::Float64, true),
        Field::new("meme_return_bps", DataType::Float64, true),
        Field::new("alt_return_bps", DataType::Float64, true),
        Field::new("sol_return_bps", DataType::Float64, true),
        Field::new("bonk_return_bps", DataType::Float64, true),
        Field::new("bonk_rel_market_bps", DataType::Float64, true),
        Field::new("bonk_rel_meme_bps", DataType::Float64, true),
        Field::new("bonk_rel_sol_bps", DataType::Float64, true),
        Field::new("bonk_beta_market_60m", DataType::Float64, true),
        Field::new("bonk_corr_market_60m", DataType::Float64, true),
        Field::new("bonk_beta_meme_60m", DataType::Float64, true),
        Field::new("bonk_corr_meme_60m", DataType::Float64, true),
        Field::new("bonk_beta_sol_60m", DataType::Float64, true),
        Field::new("bonk_corr_sol_60m", DataType::Float64, true),
        Field::new("bonk_beta_market_240m", DataType::Float64, true),
        Field::new("bonk_corr_market_240m", DataType::Float64, true),
        Field::new("bonk_beta_meme_240m", DataType::Float64, true),
        Field::new("bonk_corr_meme_240m", DataType::Float64, true),
        Field::new("bonk_beta_sol_240m", DataType::Float64, true),
        Field::new("bonk_corr_sol_240m", DataType::Float64, true),
    ]));
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            str_col(rows, |row| &row.run_tag),
            str_col(rows, |row| &row.timestamp_utc),
            u64_array(&rows.iter().map(|row| row.timestamp_us).collect::<Vec<_>>()),
            str_col(rows, |row| &row.symbol),
            str_col(rows, |row| &row.asset),
            f64_col(rows, |row| row.open),
            f64_col(rows, |row| row.high),
            f64_col(rows, |row| row.low),
            f64_col(rows, |row| row.close),
            f64_col(rows, |row| row.volume),
            f64_col(rows, |row| row.quote_volume),
            u64_array(&rows.iter().map(|row| row.trade_count).collect::<Vec<_>>()),
            opt_f64_col(rows, |row| row.ret_1m_bps),
            opt_f64_col(rows, |row| row.rv_15m_bps),
            opt_f64_col(rows, |row| row.rv_1h_bps),
            opt_f64_col(rows, |row| row.rv_4h_bps),
            opt_f64_col(rows, |row| row.rv_12h_bps),
            opt_f64_col(rows, |row| row.market_return_bps),
            opt_f64_col(rows, |row| row.meme_return_bps),
            opt_f64_col(rows, |row| row.alt_return_bps),
            opt_f64_col(rows, |row| row.sol_return_bps),
            opt_f64_col(rows, |row| row.bonk_return_bps),
            opt_f64_col(rows, |row| row.bonk_rel_market_bps),
            opt_f64_col(rows, |row| row.bonk_rel_meme_bps),
            opt_f64_col(rows, |row| row.bonk_rel_sol_bps),
            opt_f64_col(rows, |row| row.bonk_beta_market_60m),
            opt_f64_col(rows, |row| row.bonk_corr_market_60m),
            opt_f64_col(rows, |row| row.bonk_beta_meme_60m),
            opt_f64_col(rows, |row| row.bonk_corr_meme_60m),
            opt_f64_col(rows, |row| row.bonk_beta_sol_60m),
            opt_f64_col(rows, |row| row.bonk_corr_sol_60m),
            opt_f64_col(rows, |row| row.bonk_beta_market_240m),
            opt_f64_col(rows, |row| row.bonk_corr_market_240m),
            opt_f64_col(rows, |row| row.bonk_beta_meme_240m),
            opt_f64_col(rows, |row| row.bonk_corr_meme_240m),
            opt_f64_col(rows, |row| row.bonk_beta_sol_240m),
            opt_f64_col(rows, |row| row.bonk_corr_sol_240m),
        ],
    )?;
    write_parquet_atomic(path, schema, batch)
}

fn output_paths(config: &PriceContextConfig) -> OutputPaths {
    OutputPaths {
        price_context_parquet: config
            .data_root
            .join("derived")
            .join("bonk_cex_price_context")
            .join(format!("bonk_cex_price_context_{}.parquet", config.run_tag)),
        quality_csv: config.date_dir.join(format!(
            "bonk_v1_cex_price_context_quality_{}.csv",
            config.run_tag
        )),
        summary_csv: config.date_dir.join(format!(
            "bonk_v1_cex_price_context_summary_{}.csv",
            config.run_tag
        )),
        completion_json: config.date_dir.join(format!(
            "bonk_v1_cex_price_context_completion_{}.json",
            config.run_tag
        )),
    }
}

fn build_jobs(symbols: &[String], from_date: NaiveDate, to_date: NaiveDate) -> Vec<KlineJob> {
    let mut jobs = Vec::new();
    let mut day = from_date;
    while day <= to_date {
        for symbol in symbols {
            jobs.push(KlineJob {
                symbol: symbol.clone(),
                day,
            });
        }
        day = day.succ_opt().expect("date overflow");
    }
    jobs
}

fn raw_daily_path(data_root: &Path, symbol: &str, day: NaiveDate) -> PathBuf {
    data_root
        .join("external")
        .join("binance_spot_klines")
        .join(format!("{symbol}-1m-{day}.csv"))
}

fn binance_daily_url(symbol: &str, day: NaiveDate) -> String {
    format!("{BINANCE_BASE}/{symbol}/1m/{symbol}-1m-{day}.zip")
}

fn asset_from_symbol(symbol: &str) -> String {
    symbol
        .strip_suffix("USDT")
        .or_else(|| symbol.strip_suffix("USDC"))
        .unwrap_or(symbol)
        .to_string()
}

fn average_returns(map: &HashMap<String, &BaseKlineRow>, symbols: &[&str]) -> Option<f64> {
    let values = symbols
        .iter()
        .filter_map(|symbol| map.get(*symbol).and_then(|row| row.ret_1m_bps))
        .collect::<Vec<_>>();
    mean(&values)
}

fn trailing_rv(values: &[Option<f64>], idx: usize, window: usize) -> Option<f64> {
    let start = (idx + 1).saturating_sub(window);
    let mut sum_sq = 0.0;
    let mut count = 0usize;
    for value in values
        .iter()
        .take(idx + 1)
        .skip(start)
        .filter_map(|value| *value)
    {
        sum_sq += value * value;
        count += 1;
    }
    if count < window.min(15) {
        None
    } else {
        finite(sum_sq.sqrt())
    }
}

fn rolling_beta_corr(
    y: &[Option<f64>],
    x: &[Option<f64>],
    idx: usize,
    window: usize,
) -> (Option<f64>, Option<f64>) {
    let start = (idx + 1).saturating_sub(window);
    let pairs = (start..=idx)
        .filter_map(|i| y[i].zip(x[i]))
        .filter(|(y, x)| y.is_finite() && x.is_finite())
        .collect::<Vec<_>>();
    if pairs.len() < window.min(30) {
        return (None, None);
    }
    let mean_y = pairs.iter().map(|(y, _)| *y).sum::<f64>() / pairs.len() as f64;
    let mean_x = pairs.iter().map(|(_, x)| *x).sum::<f64>() / pairs.len() as f64;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    for (y, x) in pairs {
        let dy = y - mean_y;
        let dx = x - mean_x;
        cov += dy * dx;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    let beta = if var_x > 0.0 {
        finite(cov / var_x)
    } else {
        None
    };
    let corr = if var_x > 0.0 && var_y > 0.0 {
        finite(cov / (var_x.sqrt() * var_y.sqrt()))
    } else {
        None
    };
    (beta, corr)
}

fn normalize_epoch_to_us(value: u64) -> Option<u64> {
    if value >= 1_000_000_000_000_000_000 {
        Some(value / 1_000)
    } else if value >= 1_000_000_000_000_000 {
        Some(value)
    } else if value >= 1_000_000_000_000 {
        Some(value * 1_000)
    } else if value >= 1_000_000_000 {
        Some(value * 1_000_000)
    } else {
        None
    }
}

fn date_start_us(day: NaiveDate) -> Result<u64> {
    let dt = day
        .and_hms_opt(0, 0, 0)
        .ok_or_else(|| anyhow!("invalid date {day}"))?
        .and_utc();
    Ok(dt.timestamp() as u64 * 1_000_000)
}

fn utc_from_us(timestamp_us: u64) -> Result<String> {
    let secs = (timestamp_us / 1_000_000) as i64;
    Ok(Utc
        .timestamp_opt(secs, 0)
        .single()
        .ok_or_else(|| anyhow!("invalid timestamp_us {timestamp_us}"))?
        .to_rfc3339_opts(SecondsFormat::Secs, true))
}

fn parse_u64(value: &str) -> Option<u64> {
    value.trim().parse::<u64>().ok()
}

fn parse_f64(value: &str) -> Option<f64> {
    value.trim().parse::<f64>().ok().and_then(finite)
}

fn finite(value: f64) -> Option<f64> {
    if value.is_finite() { Some(value) } else { None }
}

fn mean(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        finite(values.iter().sum::<f64>() / values.len() as f64)
    }
}

fn median(mut values: Vec<f64>) -> Option<f64> {
    values.retain(|value| value.is_finite());
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        finite((values[mid - 1] + values[mid]) / 2.0)
    } else {
        finite(values[mid])
    }
}

fn build_client(timeout_seconds: u64) -> Result<Client> {
    Client::builder()
        .timeout(Duration::from_secs(timeout_seconds))
        .build()
        .context("failed to build HTTP client")
}

fn str_col<T, F>(rows: &[T], f: F) -> ArrayRef
where
    F: Fn(&T) -> &String,
{
    string_array(&rows.iter().map(|row| f(row).clone()).collect::<Vec<_>>())
}

fn f64_col<T, F>(rows: &[T], f: F) -> ArrayRef
where
    F: Fn(&T) -> f64,
{
    let mut builder = Float64Builder::with_capacity(rows.len());
    for row in rows {
        builder.append_value(f(row));
    }
    Arc::new(builder.finish())
}

fn opt_f64_col<T, F>(rows: &[T], f: F) -> ArrayRef
where
    F: Fn(&T) -> Option<f64>,
{
    opt_f64_array(&rows.iter().map(f).collect::<Vec<_>>())
}

fn opt_f64_array(values: &[Option<f64>]) -> ArrayRef {
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        match value.and_then(finite) {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

fn write_parquet_atomic(path: &Path, schema: SchemaRef, batch: RecordBatch) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    {
        let file =
            File::create(&temp).with_context(|| format!("failed to create {}", temp.display()))?;
        let props = WriterProperties::builder()
            .set_created_by("cex-l2-price-context".to_string())
            .build();
        let mut writer = ArrowWriter::try_new(file, schema, Some(props))
            .with_context(|| format!("failed to create parquet writer for {}", path.display()))?;
        writer.write(&batch)?;
        writer.close()?;
    }
    replace_file(&temp, path)
}

fn write_csv_atomic<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    {
        let mut writer = csv::Writer::from_path(&temp)?;
        for row in rows {
            writer.serialize(row)?;
        }
        writer.flush()?;
    }
    replace_file(&temp, path)
}

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    {
        let file =
            File::create(&temp).with_context(|| format!("failed to create {}", temp.display()))?;
        serde_json::to_writer_pretty(file, value)?;
    }
    replace_file(&temp, path)
}

fn replace_file(temp: &Path, path: &Path) -> Result<()> {
    const ATTEMPTS: usize = 20;
    for attempt in 0..ATTEMPTS {
        if path.exists() {
            match fs::remove_file(path) {
                Ok(()) => {}
                Err(err) if attempt + 1 < ATTEMPTS => {
                    sleep_replace_retry(attempt);
                    if !temp.exists() {
                        return Err(err)
                            .with_context(|| format!("failed to remove {}", path.display()));
                    }
                    continue;
                }
                Err(err) => {
                    return Err(err)
                        .with_context(|| format!("failed to remove {}", path.display()));
                }
            }
        }
        match fs::rename(temp, path) {
            Ok(()) => return Ok(()),
            Err(_err) if attempt + 1 < ATTEMPTS => {
                sleep_replace_retry(attempt);
                continue;
            }
            Err(err) => {
                return Err(err).with_context(|| {
                    format!("failed to move {} to {}", temp.display(), path.display())
                });
            }
        }
    }
    bail!(
        "failed to replace {} with {} after retries",
        path.display(),
        temp.display()
    )
}

fn sleep_replace_retry(attempt: usize) {
    let millis = 50 * ((attempt as u64 + 1).min(20));
    thread::sleep(Duration::from_millis(millis));
}

fn temp_path_for(path: &Path) -> PathBuf {
    let filename = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("out");
    path.with_file_name(format!(".{filename}.tmp.{}", std::process::id()))
}

fn fingerprint_quality(quality: &[PriceQualityRow]) -> PriceRawFingerprint {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    let mut total_bytes = 0u64;
    let mut file_count = 0usize;
    for row in quality {
        if row.status != "missing" {
            file_count += 1;
            total_bytes = total_bytes.saturating_add(row.bytes);
        }
        row.symbol.hash(&mut hasher);
        row.date.hash(&mut hasher);
        row.path.hash(&mut hasher);
        row.bytes.hash(&mut hasher);
        row.status.hash(&mut hasher);
    }
    PriceRawFingerprint {
        file_count,
        total_bytes,
        hash: format!("{:016x}", hasher.finish()),
    }
}

fn utc_now_string() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn epoch_normalizes_ms_us_ns() {
        assert_eq!(
            normalize_epoch_to_us(1_778_371_200_000),
            Some(1_778_371_200_000_000)
        );
        assert_eq!(
            normalize_epoch_to_us(1_778_371_200_000_000),
            Some(1_778_371_200_000_000)
        );
        assert_eq!(
            normalize_epoch_to_us(1_778_371_200_000_000_000),
            Some(1_778_371_200_000_000)
        );
    }

    #[test]
    fn asset_from_symbol_strips_quote() {
        assert_eq!(asset_from_symbol("BONKUSDT"), "BONK");
        assert_eq!(asset_from_symbol("BTCUSDC"), "BTC");
    }
}

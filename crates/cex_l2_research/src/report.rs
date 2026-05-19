use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet, VecDeque};
use std::fs::{self, File};
use std::hash::{Hash, Hasher};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering as AtomicOrdering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Instant;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{ArrayRef, Float64Builder};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{SecondsFormat, TimeZone, Utc};
use finance_chain_core::storage::{ensure_parent_dir, string_array, u64_array};
use flate2::read::GzDecoder;
use parquet::arrow::ArrowWriter;
use parquet::file::properties::WriterProperties;
use serde::{Deserialize, Serialize};

use crate::download::{parse_symbol_list, path_string};
use crate::price::DEFAULT_PRICE_CONTEXT_RUN_TAG;

const EXCHANGE: &str = "bullish";
const RAW_DATA_TYPES: [&str; 3] = ["book_snapshot_25", "book_ticker", "trades"];
const FACTOR_COLS: [&str; 13] = [
    "spread_bps_median",
    "spread_bps_last",
    "microprice_offset_bps_mean",
    "wobi5_mean",
    "wobi25_mean",
    "depth_imbalance_5_mean",
    "depth_imbalance_25_mean",
    "trade_flow_imbalance",
    "reported_buy_share",
    "trade_notional_quote_sum",
    "book_ticker_count",
    "snapshot_count",
    "trade_count",
];

#[derive(Debug, Clone)]
pub struct BullishL2ReportConfig {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub doc_dir: PathBuf,
    pub run_tag: String,
    pub symbols: String,
    pub label_symbols: String,
    pub horizons_hours: String,
    pub barriers_bps: String,
    pub abnormal_spread_bps: f64,
    pub workers: usize,
    pub progress_interval: usize,
    pub price_context_run_tag: Option<String>,
    pub no_price_context: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct BullishL2ReportOutputs {
    pub l2_state_parquet: String,
    pub covariance_parquet: String,
    pub labels_parquet: String,
    pub quality_csv: String,
    pub summary_csv: String,
    pub factor_tests_csv: String,
    pub stability_csv: String,
    pub completion_json: String,
    pub report_md: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BullishL2ReportRows {
    pub l2_state: usize,
    pub covariance_state: usize,
    pub path_labels: usize,
    pub quality: usize,
    pub summary: usize,
    pub factor_tests: usize,
    pub stability: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct BullishL2ReportSummary {
    pub run_tag: String,
    pub finished_at_utc: String,
    pub elapsed_seconds: f64,
    pub symbols: Vec<String>,
    pub label_symbols: Vec<String>,
    pub outputs: BullishL2ReportOutputs,
    pub rows: BullishL2ReportRows,
    pub raw_fingerprint: RawReportFingerprint,
    pub price_context: PriceContextReportStatus,
}

#[derive(Debug, Clone, Serialize)]
pub struct RawReportFingerprint {
    pub file_count: usize,
    pub total_bytes: u64,
    pub hash: String,
}

#[derive(Debug, Clone)]
struct OutputPaths {
    l2_state_parquet: PathBuf,
    covariance_parquet: PathBuf,
    labels_parquet: PathBuf,
    quality_csv: PathBuf,
    summary_csv: PathBuf,
    factor_tests_csv: PathBuf,
    stability_csv: PathBuf,
    completion_json: PathBuf,
    report_md: PathBuf,
}

#[derive(Debug, Clone, Serialize)]
pub struct PriceContextReportStatus {
    pub status: String,
    pub run_tag: String,
    pub price_context_parquet: String,
    pub summary_csv: String,
    pub completion_json: String,
    pub rows: u64,
    pub summary_rows: usize,
    pub available_symbols: Vec<String>,
    pub missing_symbols: Vec<String>,
    pub market_coverage: Option<f64>,
    pub meme_coverage: Option<f64>,
    pub sol_coverage: Option<f64>,
    pub bonk_return_bps: Option<f64>,
    pub market_return_bps: Option<f64>,
    pub meme_return_bps: Option<f64>,
    pub sol_return_bps: Option<f64>,
    pub bonk_rel_market_bps: Option<f64>,
    pub bonk_rel_meme_bps: Option<f64>,
    pub bonk_rel_sol_bps: Option<f64>,
    pub message: String,
}

#[derive(Debug, Clone)]
struct PriceContextPaths {
    run_tag: String,
    price_context_parquet: PathBuf,
    summary_csv: PathBuf,
    completion_json: PathBuf,
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct PriceContextSummaryCsvRow {
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

fn load_price_context_status(config: &BullishL2ReportConfig) -> Result<PriceContextReportStatus> {
    if config.no_price_context {
        return Ok(empty_price_context_status(
            "disabled",
            config.price_context_run_tag.as_deref().unwrap_or(""),
            "disabled by --no-price-context",
        ));
    }
    let candidates = price_context_candidates(config);
    for paths in &candidates {
        if paths.summary_csv.exists() {
            return summarize_price_context(paths);
        }
    }
    let Some(paths) = candidates.first() else {
        return Ok(empty_price_context_status(
            "missing",
            "",
            "no price context run tag candidate",
        ));
    };
    Ok(PriceContextReportStatus {
        status: "missing".to_string(),
        run_tag: paths.run_tag.clone(),
        price_context_parquet: path_string(&paths.price_context_parquet),
        summary_csv: path_string(&paths.summary_csv),
        completion_json: path_string(&paths.completion_json),
        rows: 0,
        summary_rows: 0,
        available_symbols: Vec::new(),
        missing_symbols: Vec::new(),
        market_coverage: None,
        meme_coverage: None,
        sol_coverage: None,
        bonk_return_bps: None,
        market_return_bps: None,
        meme_return_bps: None,
        sol_return_bps: None,
        bonk_rel_market_bps: None,
        bonk_rel_meme_bps: None,
        bonk_rel_sol_bps: None,
        message: format!("summary CSV not found: {}", paths.summary_csv.display()),
    })
}

fn summarize_price_context(paths: &PriceContextPaths) -> Result<PriceContextReportStatus> {
    let rows = read_price_context_summary_rows(&paths.summary_csv)?;
    let context_rows = read_price_context_completion_rows(&paths.completion_json)
        .unwrap_or_else(|| rows.iter().map(|row| row.rows).sum());
    let available_symbols = rows
        .iter()
        .filter(|row| row.rows > 0)
        .map(|row| row.symbol.clone())
        .collect::<Vec<_>>();
    let missing_symbols = rows
        .iter()
        .filter(|row| row.rows == 0)
        .map(|row| row.symbol.clone())
        .collect::<Vec<_>>();
    let market_coverage = average_price_metric(&rows, &["BTCUSDT", "ETHUSDT", "SOLUSDT"], coverage);
    let meme_coverage = average_price_metric(
        &rows,
        &["DOGEUSDT", "PEPEUSDT", "SHIBUSDT", "WIFUSDT"],
        coverage,
    );
    let sol_coverage = rows
        .iter()
        .find(|row| row.symbol == "SOLUSDT")
        .and_then(coverage);
    let bonk_return_bps = rows
        .iter()
        .find(|row| row.symbol == "BONKUSDT")
        .and_then(|row| row.total_return_bps);
    let market_return_bps =
        average_price_metric(&rows, &["BTCUSDT", "ETHUSDT", "SOLUSDT"], |row| {
            row.total_return_bps
        });
    let meme_return_bps = average_price_metric(
        &rows,
        &["DOGEUSDT", "PEPEUSDT", "SHIBUSDT", "WIFUSDT"],
        |row| row.total_return_bps,
    );
    let sol_return_bps = rows
        .iter()
        .find(|row| row.symbol == "SOLUSDT")
        .and_then(|row| row.total_return_bps);
    let status = if paths.price_context_parquet.exists() && paths.completion_json.exists() {
        "available"
    } else {
        "partial"
    };
    let missing_bits = [
        (!paths.price_context_parquet.exists()).then_some("parquet"),
        (!paths.completion_json.exists()).then_some("completion_json"),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>();
    let message = if missing_bits.is_empty() {
        "price context loaded".to_string()
    } else {
        format!(
            "price context summary loaded; missing {}",
            missing_bits.join(",")
        )
    };
    Ok(PriceContextReportStatus {
        status: status.to_string(),
        run_tag: paths.run_tag.clone(),
        price_context_parquet: path_string(&paths.price_context_parquet),
        summary_csv: path_string(&paths.summary_csv),
        completion_json: path_string(&paths.completion_json),
        rows: context_rows,
        summary_rows: rows.len(),
        available_symbols,
        missing_symbols,
        market_coverage,
        meme_coverage,
        sol_coverage,
        bonk_return_bps,
        market_return_bps,
        meme_return_bps,
        sol_return_bps,
        bonk_rel_market_bps: diff_opt(bonk_return_bps, market_return_bps),
        bonk_rel_meme_bps: diff_opt(bonk_return_bps, meme_return_bps),
        bonk_rel_sol_bps: diff_opt(bonk_return_bps, sol_return_bps),
        message,
    })
}

fn read_price_context_summary_rows(path: &Path) -> Result<Vec<PriceContextSummaryCsvRow>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    let mut rows = Vec::new();
    for row in reader.deserialize() {
        rows.push(row.with_context(|| format!("failed to parse {}", path.display()))?);
    }
    Ok(rows)
}

fn read_price_context_completion_rows(path: &Path) -> Option<u64> {
    let file = File::open(path).ok()?;
    let value: serde_json::Value = serde_json::from_reader(file).ok()?;
    value.pointer("/rows/price_context")?.as_u64()
}

fn price_context_candidates(config: &BullishL2ReportConfig) -> Vec<PriceContextPaths> {
    let mut tags = Vec::<String>::new();
    if let Some(tag) = config.price_context_run_tag.as_ref() {
        tags.push(tag.clone());
    } else {
        tags.push(config.run_tag.clone());
        tags.push(DEFAULT_PRICE_CONTEXT_RUN_TAG.to_string());
    }
    tags.sort();
    tags.dedup();
    tags.into_iter()
        .map(|tag| price_context_paths(config, tag))
        .collect()
}

fn price_context_paths(config: &BullishL2ReportConfig, run_tag: String) -> PriceContextPaths {
    PriceContextPaths {
        price_context_parquet: config
            .data_root
            .join("derived")
            .join("bonk_cex_price_context")
            .join(format!("bonk_cex_price_context_{run_tag}.parquet")),
        summary_csv: config
            .date_dir
            .join(format!("bonk_v1_cex_price_context_summary_{run_tag}.csv")),
        completion_json: config.date_dir.join(format!(
            "bonk_v1_cex_price_context_completion_{run_tag}.json"
        )),
        run_tag,
    }
}

fn empty_price_context_status(
    status: &str,
    run_tag: &str,
    message: &str,
) -> PriceContextReportStatus {
    PriceContextReportStatus {
        status: status.to_string(),
        run_tag: run_tag.to_string(),
        price_context_parquet: String::new(),
        summary_csv: String::new(),
        completion_json: String::new(),
        rows: 0,
        summary_rows: 0,
        available_symbols: Vec::new(),
        missing_symbols: Vec::new(),
        market_coverage: None,
        meme_coverage: None,
        sol_coverage: None,
        bonk_return_bps: None,
        market_return_bps: None,
        meme_return_bps: None,
        sol_return_bps: None,
        bonk_rel_market_bps: None,
        bonk_rel_meme_bps: None,
        bonk_rel_sol_bps: None,
        message: message.to_string(),
    }
}

fn coverage(row: &PriceContextSummaryCsvRow) -> Option<f64> {
    if row.expected_minutes == 0 {
        None
    } else {
        finite(row.rows as f64 / row.expected_minutes as f64)
    }
}

fn average_price_metric(
    rows: &[PriceContextSummaryCsvRow],
    symbols: &[&str],
    value: fn(&PriceContextSummaryCsvRow) -> Option<f64>,
) -> Option<f64> {
    let values = symbols
        .iter()
        .filter_map(|symbol| {
            rows.iter()
                .find(|row| row.symbol == *symbol)
                .and_then(value)
        })
        .collect::<Vec<_>>();
    mean(&values)
}

fn diff_opt(left: Option<f64>, right: Option<f64>) -> Option<f64> {
    left.zip(right)
        .and_then(|(left, right)| finite(left - right))
}

fn join_or_none(values: &[String]) -> String {
    if values.is_empty() {
        "none".to_string()
    } else {
        values.join(",")
    }
}

#[derive(Debug, Clone)]
struct RawJob {
    data_type: String,
    path: PathBuf,
}

#[derive(Debug, Clone, Serialize)]
struct QualityRow {
    data_type: String,
    symbol: String,
    source_date: String,
    path: String,
    bytes: u64,
    status: String,
    rows: u64,
    timestamp_min_us: Option<u64>,
    timestamp_max_us: Option<u64>,
    timestamp_monotonic_violations: u64,
    duplicate_rows_in_chunks: u64,
    empty_price_rows: u64,
    negative_amount_rows: u64,
    abnormal_spread_rows: u64,
    header: String,
    error: String,
}

#[derive(Debug)]
struct ProcessedFile {
    quality: QualityRow,
    ticker: BTreeMap<MinuteKey, TickerAgg>,
    snapshot: BTreeMap<MinuteKey, SnapshotAgg>,
    trades: BTreeMap<MinuteKey, TradeAgg>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
struct MinuteKey {
    symbol: String,
    asset: String,
    minute_us: u64,
}

#[derive(Debug, Clone, Default)]
struct TickerAgg {
    count: u64,
    bid_price_last: Option<f64>,
    ask_price_last: Option<f64>,
    mid_open: Option<f64>,
    mid_high: Option<f64>,
    mid_low: Option<f64>,
    mid_close: Option<f64>,
    mid_token_close: Option<f64>,
    spread_values: Vec<f64>,
    spread_last: Option<f64>,
    bid_notional_values: Vec<f64>,
    ask_notional_values: Vec<f64>,
    micro_offset_sum: f64,
    micro_offset_count: u64,
}

#[derive(Debug, Clone, Default)]
struct SnapshotAgg {
    count: u64,
    spread_values: Vec<f64>,
    wobi5_sum: f64,
    wobi5_count: u64,
    wobi25_sum: f64,
    wobi25_count: u64,
    bid_notional_5_values: Vec<f64>,
    ask_notional_5_values: Vec<f64>,
    bid_notional_25_values: Vec<f64>,
    ask_notional_25_values: Vec<f64>,
    micro_offset_sum: f64,
    micro_offset_count: u64,
}

#[derive(Debug, Clone, Default)]
struct TradeAgg {
    count: u64,
    amount_sum: f64,
    notional_sum: f64,
    reported_buy_amount: f64,
    reported_sell_amount: f64,
    reported_unknown_amount: f64,
    price_per_token_last: Option<f64>,
}

#[derive(Debug, Clone)]
struct StateRow {
    run_tag: String,
    timestamp_utc: String,
    timestamp_us: u64,
    symbol: String,
    asset: String,
    price_unit: String,
    book_ticker_count: u64,
    bid_price_last: Option<f64>,
    ask_price_last: Option<f64>,
    mid_price_per_unit_open: Option<f64>,
    mid_price_per_unit_high: Option<f64>,
    mid_price_per_unit_low: Option<f64>,
    mid_price_per_unit_close: Option<f64>,
    mid_price_per_token_close: Option<f64>,
    spread_bps_median: Option<f64>,
    spread_bps_last: Option<f64>,
    top_depth_bid_notional_median: Option<f64>,
    top_depth_ask_notional_median: Option<f64>,
    microprice_offset_bps_mean: Option<f64>,
    snapshot_count: u64,
    snapshot_spread_bps_median: Option<f64>,
    wobi5_mean: Option<f64>,
    wobi25_mean: Option<f64>,
    depth_imbalance_5_mean: Option<f64>,
    depth_imbalance_25_mean: Option<f64>,
    depth_bid_notional_5_median: Option<f64>,
    depth_ask_notional_5_median: Option<f64>,
    depth_bid_notional_25_median: Option<f64>,
    depth_ask_notional_25_median: Option<f64>,
    snapshot_microprice_offset_bps_mean: Option<f64>,
    trade_count: u64,
    trade_amount_sum: f64,
    trade_notional_quote_sum: f64,
    reported_buy_amount: f64,
    reported_sell_amount: f64,
    reported_unknown_amount: f64,
    trade_price_per_unit_vwap: Option<f64>,
    trade_price_per_token_last: Option<f64>,
    trade_flow_imbalance: Option<f64>,
    reported_buy_share: Option<f64>,
    ret_1m_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct CovarianceRow {
    run_tag: String,
    timestamp_utc: String,
    timestamp_us: u64,
    n_symbols: u64,
    symbols: String,
    avg_corr_60m: Option<f64>,
    first_eigen_share_60m: Option<f64>,
    cross_symbol_abs_ret_mean_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct LabelRow {
    run_tag: String,
    timestamp_utc: String,
    timestamp_us: u64,
    symbol: String,
    asset: String,
    horizon_hours: u64,
    barrier_bps: u64,
    price_per_token: Option<f64>,
    future_return_bps: Option<f64>,
    mfe_up_bps: Option<f64>,
    mae_down_bps: Option<f64>,
    barrier_first_hit: String,
    label_status: String,
}

#[derive(Debug, Clone, Serialize)]
struct SummaryRow {
    symbol: String,
    asset: String,
    state_rows: u64,
    first_timestamp_utc: String,
    last_timestamp_utc: String,
    median_mid_price_per_unit: Option<f64>,
    median_price_per_token: Option<f64>,
    median_spread_bps: Option<f64>,
    total_book_ticker_rows: u64,
    total_snapshot_rows: u64,
    total_trades: u64,
    total_trade_notional_quote: f64,
    raw_files: u64,
    raw_rows: u64,
    raw_error_files: u64,
    raw_empty_files: u64,
    timestamp_monotonic_violations: u64,
    duplicate_rows_in_chunks: u64,
    empty_price_rows: u64,
    negative_amount_rows: u64,
    abnormal_spread_rows: u64,
    valid_label_rows: u64,
    future_missing_rows: u64,
    upper_first_rate: Option<f64>,
    lower_first_rate: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorTestRow {
    symbol: String,
    horizon_hours: u64,
    barrier_bps: u64,
    factor: String,
    bucket: String,
    rows: u64,
    upper_first_rate: Option<f64>,
    lower_first_rate: Option<f64>,
    baseline_upper_first_rate: Option<f64>,
    baseline_lower_first_rate: Option<f64>,
    edge_vs_baseline_upper: Option<f64>,
    median_factor: Option<f64>,
    median_future_return_bps: Option<f64>,
    median_mfe_up_bps: Option<f64>,
    median_mae_down_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct StabilityRow {
    check: String,
    symbol: String,
    horizon_hours: u64,
    barrier_bps: u64,
    factor: String,
    slice: String,
    rows: u64,
    high_bucket_rows: u64,
    upper_first_rate_high: Option<f64>,
    edge_vs_baseline_upper: Option<f64>,
}

#[derive(Debug, Clone)]
struct JoinedRow {
    minute_us: u64,
    state_index: usize,
    barrier_first_hit: String,
    future_return_bps: Option<f64>,
    mfe_up_bps: Option<f64>,
    mae_down_bps: Option<f64>,
}

pub fn run_bullish_l2_report(config: &BullishL2ReportConfig) -> Result<BullishL2ReportSummary> {
    if config.workers == 0 {
        bail!("--workers must be >= 1");
    }
    let started = Instant::now();
    let symbols = parse_symbol_list(&config.symbols);
    let label_symbols = parse_symbol_list(&config.label_symbols);
    let horizons = parse_int_list(&config.horizons_hours)?;
    let barriers = parse_int_list(&config.barriers_bps)?;
    if symbols.is_empty() {
        bail!("at least one symbol is required");
    }
    if label_symbols.is_empty() {
        bail!("at least one label symbol is required");
    }

    let paths = output_paths(config);
    let price_context = load_price_context_status(config)?;
    for path in [
        &paths.l2_state_parquet,
        &paths.covariance_parquet,
        &paths.labels_parquet,
        &paths.quality_csv,
        &paths.summary_csv,
        &paths.factor_tests_csv,
        &paths.stability_csv,
        &paths.completion_json,
        &paths.report_md,
    ] {
        ensure_parent_dir(path)?;
    }

    eprintln!("[bonk_cex_l2_report] scan raw files");
    let jobs = discover_raw_jobs(&config.data_root, &symbols)?;
    if jobs.is_empty() {
        bail!(
            "no Bullish raw CSV.gz files found under {}",
            config.data_root.display()
        );
    }
    eprintln!(
        "[bonk_cex_l2_report] process {} raw files with {} workers",
        jobs.len(),
        config.workers
    );
    let processed = process_raw_jobs(jobs, config)?;
    let mut quality = Vec::new();
    let mut ticker = BTreeMap::<MinuteKey, TickerAgg>::new();
    let mut snapshot = BTreeMap::<MinuteKey, SnapshotAgg>::new();
    let mut trades = BTreeMap::<MinuteKey, TradeAgg>::new();
    for file in processed {
        quality.push(file.quality);
        merge_map(&mut ticker, file.ticker, TickerAgg::merge);
        merge_map(&mut snapshot, file.snapshot, SnapshotAgg::merge);
        merge_map(&mut trades, file.trades, TradeAgg::merge);
    }
    quality.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.data_type.cmp(&b.data_type))
            .then_with(|| a.source_date.cmp(&b.source_date))
            .then_with(|| a.path.cmp(&b.path))
    });
    eprintln!("[bonk_cex_l2_report] build state");
    let mut state = build_state(config, ticker, snapshot, trades)?;
    add_returns(&mut state);
    let label_state = state
        .iter()
        .filter(|row| label_symbols.contains(&row.symbol))
        .cloned()
        .collect::<Vec<_>>();
    eprintln!("[bonk_cex_l2_report] build covariance");
    let covariance = build_covariance_state(&state, &config.run_tag)?;
    eprintln!("[bonk_cex_l2_report] build path labels");
    let labels = build_path_labels(&label_state, &horizons, &barriers, &config.run_tag)?;
    eprintln!("[bonk_cex_l2_report] build diagnostics");
    let summary_rows = build_summary(&label_state, &labels, &quality);
    let factor_tests = build_factor_tests(&label_state, &labels);
    let stability = build_stability_checks(&label_state, &labels);

    eprintln!("[bonk_cex_l2_report] write outputs");
    write_state_parquet(&paths.l2_state_parquet, &state)?;
    write_covariance_parquet(&paths.covariance_parquet, &covariance)?;
    write_labels_parquet(&paths.labels_parquet, &labels)?;
    write_csv_atomic(&paths.quality_csv, &quality)?;
    write_csv_atomic(&paths.summary_csv, &summary_rows)?;
    write_csv_atomic(&paths.factor_tests_csv, &factor_tests)?;
    write_csv_atomic(&paths.stability_csv, &stability)?;

    let outputs = BullishL2ReportOutputs {
        l2_state_parquet: path_string(&paths.l2_state_parquet),
        covariance_parquet: path_string(&paths.covariance_parquet),
        labels_parquet: path_string(&paths.labels_parquet),
        quality_csv: path_string(&paths.quality_csv),
        summary_csv: path_string(&paths.summary_csv),
        factor_tests_csv: path_string(&paths.factor_tests_csv),
        stability_csv: path_string(&paths.stability_csv),
        completion_json: path_string(&paths.completion_json),
        report_md: path_string(&paths.report_md),
    };
    let rows = BullishL2ReportRows {
        l2_state: state.len(),
        covariance_state: covariance.len(),
        path_labels: labels.len(),
        quality: quality.len(),
        summary: summary_rows.len(),
        factor_tests: factor_tests.len(),
        stability: stability.len(),
    };
    let raw_fingerprint = fingerprint_quality(&quality);
    let report_summary = BullishL2ReportSummary {
        run_tag: config.run_tag.clone(),
        finished_at_utc: utc_now_string(),
        elapsed_seconds: started.elapsed().as_secs_f64(),
        symbols,
        label_symbols,
        outputs,
        rows,
        raw_fingerprint,
        price_context,
    };
    write_json_atomic(&paths.completion_json, &report_summary)?;
    render_report(
        &paths,
        &report_summary,
        &state,
        &labels,
        &quality,
        &summary_rows,
        &factor_tests,
        &stability,
        &report_summary.price_context,
        &horizons,
        &barriers,
    )?;
    Ok(report_summary)
}

fn discover_raw_jobs(data_root: &Path, symbols: &[String]) -> Result<Vec<RawJob>> {
    let mut jobs = Vec::new();
    for data_type in RAW_DATA_TYPES {
        let root = data_root
            .join("external")
            .join(format!("{EXCHANGE}_{data_type}"));
        for symbol in symbols {
            let symbol_dir = root.join(format!("symbol={symbol}"));
            if !symbol_dir.exists() {
                continue;
            }
            for dt_entry in fs::read_dir(&symbol_dir)
                .with_context(|| format!("failed to read {}", symbol_dir.display()))?
            {
                let dt_entry =
                    dt_entry.with_context(|| format!("failed to read {}", symbol_dir.display()))?;
                let dt_path = dt_entry.path();
                if !dt_path.is_dir() {
                    continue;
                }
                for file_entry in fs::read_dir(&dt_path)
                    .with_context(|| format!("failed to read {}", dt_path.display()))?
                {
                    let file_entry = file_entry
                        .with_context(|| format!("failed to read {}", dt_path.display()))?;
                    let path = file_entry.path();
                    if path
                        .file_name()
                        .and_then(|value| value.to_str())
                        .is_some_and(|name| name.ends_with(".csv.gz"))
                    {
                        jobs.push(RawJob {
                            data_type: data_type.to_string(),
                            path,
                        });
                    }
                }
            }
        }
    }
    jobs.sort_by(|a, b| {
        a.data_type
            .cmp(&b.data_type)
            .then_with(|| a.path.cmp(&b.path))
    });
    Ok(jobs)
}

fn process_raw_jobs(
    jobs: Vec<RawJob>,
    config: &BullishL2ReportConfig,
) -> Result<Vec<ProcessedFile>> {
    let total = jobs.len();
    let queue = Arc::new(Mutex::new(VecDeque::from(jobs)));
    let results = Arc::new(Mutex::new(Vec::<ProcessedFile>::new()));
    let completed = Arc::new(AtomicUsize::new(0));
    let workers = config.workers.min(total).max(1);
    let mut handles = Vec::with_capacity(workers);
    for _ in 0..workers {
        let queue = Arc::clone(&queue);
        let results = Arc::clone(&results);
        let completed = Arc::clone(&completed);
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
                let result = process_raw_file(&job, config.abnormal_spread_bps)
                    .with_context(|| format!("failed to process {}", job.path.display()))?;
                let done = completed.fetch_add(1, AtomicOrdering::Relaxed) + 1;
                if config.progress_interval > 0
                    && (done == total || done % config.progress_interval == 0)
                {
                    eprintln!("[bonk_cex_l2_report] processed {done}/{total} raw files");
                }
                results.lock().unwrap().push(result);
            }
            Ok(())
        }));
    }
    for handle in handles {
        handle
            .join()
            .map_err(|_| anyhow!("report worker panicked"))??;
    }
    let mut guard = results.lock().unwrap();
    Ok(std::mem::take(&mut *guard))
}

fn process_raw_file(job: &RawJob, abnormal_spread_bps: f64) -> Result<ProcessedFile> {
    let symbol = symbol_from_path(&job.path);
    let source_date = source_date_from_path(&job.path);
    let bytes = job.path.metadata().map(|meta| meta.len()).unwrap_or(0);
    let mut quality = QualityRow {
        data_type: job.data_type.clone(),
        symbol: symbol.clone(),
        source_date,
        path: path_string(&job.path),
        bytes,
        status: "ok".to_string(),
        rows: 0,
        timestamp_min_us: None,
        timestamp_max_us: None,
        timestamp_monotonic_violations: 0,
        duplicate_rows_in_chunks: 0,
        empty_price_rows: 0,
        negative_amount_rows: 0,
        abnormal_spread_rows: 0,
        header: String::new(),
        error: String::new(),
    };
    let file =
        File::open(&job.path).with_context(|| format!("failed to open {}", job.path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut buf = BufReader::new(decoder);
    let mut header_line = String::new();
    let header_bytes = match buf.read_line(&mut header_line) {
        Ok(value) => value,
        Err(err) => {
            quality.status = "error".to_string();
            quality.error = format!("{}: {}", std::any::type_name_of_val(&err), err);
            return Ok(empty_processed(quality));
        }
    };
    if header_bytes == 0 {
        quality.status = "empty".to_string();
        quality.error = "empty gzip payload".to_string();
        return Ok(empty_processed(quality));
    }
    let header = parse_header_line(&header_line)?;
    quality.header = header.join("|");
    let indexes = HeaderIndexes::new(&header);
    let price_indexes = header
        .iter()
        .enumerate()
        .filter_map(|(index, name)| name.to_ascii_lowercase().contains("price").then_some(index))
        .collect::<Vec<_>>();
    let amount_indexes = header
        .iter()
        .enumerate()
        .filter_map(|(index, name)| {
            let lower = name.to_ascii_lowercase();
            (lower.contains("amount")
                || lower.contains("qty")
                || lower.contains("quantity")
                || lower.contains("size"))
            .then_some(index)
        })
        .collect::<Vec<_>>();
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(true)
        .from_reader(buf);
    let mut seen = HashSet::<u64>::new();
    let mut prev_ts = None::<u64>;
    let mut ticker = BTreeMap::<MinuteKey, TickerAgg>::new();
    let mut snapshot = BTreeMap::<MinuteKey, SnapshotAgg>::new();
    let mut trades = BTreeMap::<MinuteKey, TradeAgg>::new();
    for record in reader.records() {
        let record = match record {
            Ok(record) => record,
            Err(err) => {
                quality.status = "error".to_string();
                quality.error = format!("CSV: {err}");
                break;
            }
        };
        if record.is_empty() {
            continue;
        }
        quality.rows += 1;
        let row_hash = hash_record(&record);
        if !seen.insert(row_hash) {
            quality.duplicate_rows_in_chunks += 1;
        }
        let timestamp_us = indexes
            .timestamp
            .and_then(|idx| parse_u64(record.get(idx).unwrap_or_default()));
        if let Some(timestamp_us) = timestamp_us {
            quality.timestamp_min_us = Some(
                quality
                    .timestamp_min_us
                    .map_or(timestamp_us, |value| value.min(timestamp_us)),
            );
            quality.timestamp_max_us = Some(
                quality
                    .timestamp_max_us
                    .map_or(timestamp_us, |value| value.max(timestamp_us)),
            );
            if prev_ts.is_some_and(|prev| timestamp_us < prev) {
                quality.timestamp_monotonic_violations += 1;
            }
            prev_ts = Some(timestamp_us);
        }
        if price_indexes.iter().any(|idx| {
            parse_f64(record.get(*idx).unwrap_or_default()).is_none_or(|value| value <= 0.0)
        }) {
            quality.empty_price_rows += 1;
        }
        if amount_indexes.iter().any(|idx| {
            parse_f64(record.get(*idx).unwrap_or_default()).is_some_and(|value| value < 0.0)
        }) {
            quality.negative_amount_rows += 1;
        }
        if abnormal_spread(&record, &indexes).is_some_and(|spread| spread > abnormal_spread_bps) {
            quality.abnormal_spread_rows += 1;
        }
        let Some(timestamp_us) = timestamp_us else {
            continue;
        };
        let minute_us = floor_to_minute_us(timestamp_us);
        let row_symbol = indexes
            .symbol
            .and_then(|idx| record.get(idx))
            .filter(|value| !value.is_empty())
            .unwrap_or(&symbol)
            .to_ascii_uppercase();
        let key = MinuteKey {
            asset: base_asset(&row_symbol),
            symbol: row_symbol.clone(),
            minute_us,
        };
        match job.data_type.as_str() {
            "book_ticker" => add_ticker_record(&mut ticker, key, &record, &indexes),
            "book_snapshot_25" => add_snapshot_record(&mut snapshot, key, &record, &indexes),
            "trades" => add_trade_record(&mut trades, key, &record, &indexes),
            _ => {}
        }
    }
    if quality.rows == 0 && quality.status == "ok" {
        quality.status = "empty".to_string();
    }
    Ok(ProcessedFile {
        quality,
        ticker,
        snapshot,
        trades,
    })
}

fn empty_processed(quality: QualityRow) -> ProcessedFile {
    ProcessedFile {
        quality,
        ticker: BTreeMap::new(),
        snapshot: BTreeMap::new(),
        trades: BTreeMap::new(),
    }
}

#[derive(Debug)]
struct HeaderIndexes {
    timestamp: Option<usize>,
    symbol: Option<usize>,
    bid_price: Option<usize>,
    ask_price: Option<usize>,
    bid_amount: Option<usize>,
    ask_amount: Option<usize>,
    price: Option<usize>,
    amount: Option<usize>,
    side: Option<usize>,
    snapshot_bid_price: Vec<Option<usize>>,
    snapshot_ask_price: Vec<Option<usize>>,
    snapshot_bid_amount: Vec<Option<usize>>,
    snapshot_ask_amount: Vec<Option<usize>>,
}

impl HeaderIndexes {
    fn new(header: &[String]) -> Self {
        let mut map = HashMap::new();
        for (index, name) in header.iter().enumerate() {
            map.insert(name.to_string(), index);
        }
        let mut out = Self {
            timestamp: map.get("timestamp").copied(),
            symbol: map.get("symbol").copied(),
            bid_price: map
                .get("bid_price")
                .copied()
                .or_else(|| map.get("bids[0].price").copied()),
            ask_price: map
                .get("ask_price")
                .copied()
                .or_else(|| map.get("asks[0].price").copied()),
            bid_amount: map
                .get("bid_amount")
                .copied()
                .or_else(|| map.get("bids[0].amount").copied()),
            ask_amount: map
                .get("ask_amount")
                .copied()
                .or_else(|| map.get("asks[0].amount").copied()),
            price: map.get("price").copied(),
            amount: map.get("amount").copied(),
            side: map.get("side").copied(),
            snapshot_bid_price: Vec::with_capacity(25),
            snapshot_ask_price: Vec::with_capacity(25),
            snapshot_bid_amount: Vec::with_capacity(25),
            snapshot_ask_amount: Vec::with_capacity(25),
        };
        for level in 0..25 {
            out.snapshot_bid_price
                .push(map.get(&format!("bids[{level}].price")).copied());
            out.snapshot_ask_price
                .push(map.get(&format!("asks[{level}].price")).copied());
            out.snapshot_bid_amount
                .push(map.get(&format!("bids[{level}].amount")).copied());
            out.snapshot_ask_amount
                .push(map.get(&format!("asks[{level}].amount")).copied());
        }
        out
    }
}

fn add_ticker_record(
    ticker: &mut BTreeMap<MinuteKey, TickerAgg>,
    key: MinuteKey,
    record: &csv::StringRecord,
    indexes: &HeaderIndexes,
) {
    let bid = indexes
        .bid_price
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let ask = indexes
        .ask_price
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let bid_amount = indexes
        .bid_amount
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let ask_amount = indexes
        .ask_amount
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let scale = price_scale(&key.symbol);
    let agg = ticker.entry(key).or_default();
    agg.count += 1;
    let Some((bid, ask)) = bid.zip(ask) else {
        return;
    };
    let mid = (bid + ask) / 2.0;
    if !mid.is_finite() || mid <= 0.0 {
        return;
    }
    let spread = finite((ask - bid) / mid * 10_000.0);
    let bid_notional = bid_amount.and_then(|amount| finite(bid * amount));
    let ask_notional = ask_amount.and_then(|amount| finite(ask * amount));
    let micro = bid_amount
        .zip(ask_amount)
        .and_then(|(bid_amount, ask_amount)| {
            let denom = bid_amount + ask_amount;
            if denom == 0.0 {
                None
            } else {
                finite(((ask * bid_amount + bid * ask_amount) / denom / mid - 1.0) * 10_000.0)
            }
        });
    agg.add_quote(
        bid,
        ask,
        mid,
        mid / scale,
        spread,
        bid_notional,
        ask_notional,
        micro,
    );
}

fn add_snapshot_record(
    snapshot: &mut BTreeMap<MinuteKey, SnapshotAgg>,
    key: MinuteKey,
    record: &csv::StringRecord,
    indexes: &HeaderIndexes,
) {
    let mut bid_notional_5 = 0.0;
    let mut ask_notional_5 = 0.0;
    let mut bid_notional_25 = 0.0;
    let mut ask_notional_25 = 0.0;
    for level in 0..25 {
        let bid_price = indexes.snapshot_bid_price[level]
            .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
        let ask_price = indexes.snapshot_ask_price[level]
            .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
        let bid_amount = indexes.snapshot_bid_amount[level]
            .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
        let ask_amount = indexes.snapshot_ask_amount[level]
            .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
        let bid_notional = bid_price
            .zip(bid_amount)
            .and_then(|(price, amount)| finite(price * amount))
            .unwrap_or(0.0);
        let ask_notional = ask_price
            .zip(ask_amount)
            .and_then(|(price, amount)| finite(price * amount))
            .unwrap_or(0.0);
        bid_notional_25 += bid_notional;
        ask_notional_25 += ask_notional;
        if level < 5 {
            bid_notional_5 += bid_notional;
            ask_notional_5 += ask_notional;
        }
    }
    let top_bid = indexes.snapshot_bid_price[0]
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let top_ask = indexes.snapshot_ask_price[0]
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let top_bid_amount = indexes.snapshot_bid_amount[0]
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let top_ask_amount = indexes.snapshot_ask_amount[0]
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let spread = top_bid.zip(top_ask).and_then(|(bid, ask)| {
        let mid = (bid + ask) / 2.0;
        finite((ask - bid) / mid * 10_000.0)
    });
    let wobi5 = safe_div(
        bid_notional_5 - ask_notional_5,
        bid_notional_5 + ask_notional_5,
    );
    let wobi25 = safe_div(
        bid_notional_25 - ask_notional_25,
        bid_notional_25 + ask_notional_25,
    );
    let micro = top_bid
        .zip(top_ask)
        .zip(top_bid_amount.zip(top_ask_amount))
        .and_then(|((bid, ask), (bid_amount, ask_amount))| {
            let mid = (bid + ask) / 2.0;
            let denom = bid_amount + ask_amount;
            if denom == 0.0 || mid <= 0.0 {
                None
            } else {
                finite(((ask * bid_amount + bid * ask_amount) / denom / mid - 1.0) * 10_000.0)
            }
        });
    snapshot.entry(key).or_default().add(
        spread,
        wobi5,
        wobi25,
        bid_notional_5,
        ask_notional_5,
        bid_notional_25,
        ask_notional_25,
        micro,
    );
}

fn add_trade_record(
    trades: &mut BTreeMap<MinuteKey, TradeAgg>,
    key: MinuteKey,
    record: &csv::StringRecord,
    indexes: &HeaderIndexes,
) {
    let price = indexes
        .price
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let amount = indexes
        .amount
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let Some((price, amount)) = price.zip(amount) else {
        return;
    };
    let side = indexes
        .side
        .and_then(|idx| record.get(idx))
        .unwrap_or_default()
        .to_ascii_lowercase();
    trades.entry(key.clone()).or_default().add(
        price,
        amount,
        price / price_scale(&key.symbol),
        side.as_str(),
    );
}

impl TickerAgg {
    fn add_quote(
        &mut self,
        bid: f64,
        ask: f64,
        mid: f64,
        mid_token: f64,
        spread: Option<f64>,
        bid_notional: Option<f64>,
        ask_notional: Option<f64>,
        micro_offset: Option<f64>,
    ) {
        self.bid_price_last = Some(bid);
        self.ask_price_last = Some(ask);
        if self.mid_open.is_none() {
            self.mid_open = Some(mid);
        }
        self.mid_high = Some(self.mid_high.map_or(mid, |value| value.max(mid)));
        self.mid_low = Some(self.mid_low.map_or(mid, |value| value.min(mid)));
        self.mid_close = Some(mid);
        self.mid_token_close = Some(mid_token);
        if let Some(value) = spread {
            self.spread_values.push(value);
            self.spread_last = Some(value);
        }
        if let Some(value) = bid_notional {
            self.bid_notional_values.push(value);
        }
        if let Some(value) = ask_notional {
            self.ask_notional_values.push(value);
        }
        if let Some(value) = micro_offset {
            self.micro_offset_sum += value;
            self.micro_offset_count += 1;
        }
    }

    fn merge(&mut self, other: Self) {
        if self.mid_open.is_none() {
            self.mid_open = other.mid_open;
        }
        self.count += other.count;
        self.bid_price_last = other.bid_price_last.or(self.bid_price_last);
        self.ask_price_last = other.ask_price_last.or(self.ask_price_last);
        self.mid_high = max_opt(self.mid_high, other.mid_high);
        self.mid_low = min_opt(self.mid_low, other.mid_low);
        self.mid_close = other.mid_close.or(self.mid_close);
        self.mid_token_close = other.mid_token_close.or(self.mid_token_close);
        self.spread_values.extend(other.spread_values);
        self.spread_last = other.spread_last.or(self.spread_last);
        self.bid_notional_values.extend(other.bid_notional_values);
        self.ask_notional_values.extend(other.ask_notional_values);
        self.micro_offset_sum += other.micro_offset_sum;
        self.micro_offset_count += other.micro_offset_count;
    }
}

impl SnapshotAgg {
    fn add(
        &mut self,
        spread: Option<f64>,
        wobi5: Option<f64>,
        wobi25: Option<f64>,
        bid_notional_5: f64,
        ask_notional_5: f64,
        bid_notional_25: f64,
        ask_notional_25: f64,
        micro_offset: Option<f64>,
    ) {
        self.count += 1;
        if let Some(value) = spread {
            self.spread_values.push(value);
        }
        if let Some(value) = wobi5 {
            self.wobi5_sum += value;
            self.wobi5_count += 1;
        }
        if let Some(value) = wobi25 {
            self.wobi25_sum += value;
            self.wobi25_count += 1;
        }
        self.bid_notional_5_values.push(bid_notional_5);
        self.ask_notional_5_values.push(ask_notional_5);
        self.bid_notional_25_values.push(bid_notional_25);
        self.ask_notional_25_values.push(ask_notional_25);
        if let Some(value) = micro_offset {
            self.micro_offset_sum += value;
            self.micro_offset_count += 1;
        }
    }

    fn merge(&mut self, other: Self) {
        self.count += other.count;
        self.spread_values.extend(other.spread_values);
        self.wobi5_sum += other.wobi5_sum;
        self.wobi5_count += other.wobi5_count;
        self.wobi25_sum += other.wobi25_sum;
        self.wobi25_count += other.wobi25_count;
        self.bid_notional_5_values
            .extend(other.bid_notional_5_values);
        self.ask_notional_5_values
            .extend(other.ask_notional_5_values);
        self.bid_notional_25_values
            .extend(other.bid_notional_25_values);
        self.ask_notional_25_values
            .extend(other.ask_notional_25_values);
        self.micro_offset_sum += other.micro_offset_sum;
        self.micro_offset_count += other.micro_offset_count;
    }
}

impl TradeAgg {
    fn add(&mut self, price: f64, amount: f64, price_per_token: f64, side: &str) {
        self.count += 1;
        self.amount_sum += amount;
        self.notional_sum += price * amount;
        self.price_per_token_last = Some(price_per_token);
        match side {
            "buy" => self.reported_buy_amount += amount,
            "sell" => self.reported_sell_amount += amount,
            _ => self.reported_unknown_amount += amount,
        }
    }

    fn merge(&mut self, other: Self) {
        self.count += other.count;
        self.amount_sum += other.amount_sum;
        self.notional_sum += other.notional_sum;
        self.reported_buy_amount += other.reported_buy_amount;
        self.reported_sell_amount += other.reported_sell_amount;
        self.reported_unknown_amount += other.reported_unknown_amount;
        self.price_per_token_last = other.price_per_token_last.or(self.price_per_token_last);
    }
}

fn build_state(
    config: &BullishL2ReportConfig,
    ticker: BTreeMap<MinuteKey, TickerAgg>,
    snapshot: BTreeMap<MinuteKey, SnapshotAgg>,
    trades: BTreeMap<MinuteKey, TradeAgg>,
) -> Result<Vec<StateRow>> {
    let mut keys = BTreeSet::<MinuteKey>::new();
    keys.extend(ticker.keys().cloned());
    keys.extend(snapshot.keys().cloned());
    keys.extend(trades.keys().cloned());
    let mut rows = Vec::with_capacity(keys.len());
    for key in keys {
        let ticker = ticker.get(&key);
        let snapshot = snapshot.get(&key);
        let trade = trades.get(&key);
        let mut mid_unit_close = ticker.and_then(|agg| agg.mid_close);
        let mut mid_token_close = ticker.and_then(|agg| agg.mid_token_close);
        let trade_vwap = trade.and_then(|agg| safe_div(agg.notional_sum, agg.amount_sum));
        if mid_unit_close.is_none() {
            mid_unit_close = trade_vwap;
            mid_token_close = trade_vwap.map(|value| value / price_scale(&key.symbol));
        }
        let spread_median = ticker
            .and_then(|agg| median(agg.spread_values.clone()))
            .or_else(|| snapshot.and_then(|agg| median(agg.spread_values.clone())));
        let micro_offset = ticker
            .and_then(|agg| mean_from_sum(agg.micro_offset_sum, agg.micro_offset_count))
            .or_else(|| {
                snapshot.and_then(|agg| mean_from_sum(agg.micro_offset_sum, agg.micro_offset_count))
            });
        let (trade_count, trade_amount_sum, trade_notional, buy, sell, unknown, trade_token_last) =
            trade
                .map(|agg| {
                    (
                        agg.count,
                        agg.amount_sum,
                        agg.notional_sum,
                        agg.reported_buy_amount,
                        agg.reported_sell_amount,
                        agg.reported_unknown_amount,
                        agg.price_per_token_last,
                    )
                })
                .unwrap_or((0, 0.0, 0.0, 0.0, 0.0, 0.0, None));
        let denom = buy + sell;
        rows.push(StateRow {
            run_tag: config.run_tag.clone(),
            timestamp_utc: utc_from_us(key.minute_us)?,
            timestamp_us: key.minute_us,
            symbol: key.symbol.clone(),
            asset: key.asset.clone(),
            price_unit: if price_scale(&key.symbol) == 1_000_000.0 {
                "per_1m_base".to_string()
            } else {
                "per_base".to_string()
            },
            book_ticker_count: ticker.map(|agg| agg.count).unwrap_or(0),
            bid_price_last: ticker.and_then(|agg| agg.bid_price_last),
            ask_price_last: ticker.and_then(|agg| agg.ask_price_last),
            mid_price_per_unit_open: ticker.and_then(|agg| agg.mid_open),
            mid_price_per_unit_high: ticker.and_then(|agg| agg.mid_high),
            mid_price_per_unit_low: ticker.and_then(|agg| agg.mid_low),
            mid_price_per_unit_close: mid_unit_close,
            mid_price_per_token_close: mid_token_close,
            spread_bps_median: spread_median,
            spread_bps_last: ticker.and_then(|agg| agg.spread_last),
            top_depth_bid_notional_median: ticker
                .and_then(|agg| median(agg.bid_notional_values.clone())),
            top_depth_ask_notional_median: ticker
                .and_then(|agg| median(agg.ask_notional_values.clone())),
            microprice_offset_bps_mean: micro_offset,
            snapshot_count: snapshot.map(|agg| agg.count).unwrap_or(0),
            snapshot_spread_bps_median: snapshot.and_then(|agg| median(agg.spread_values.clone())),
            wobi5_mean: snapshot.and_then(|agg| mean_from_sum(agg.wobi5_sum, agg.wobi5_count)),
            wobi25_mean: snapshot.and_then(|agg| mean_from_sum(agg.wobi25_sum, agg.wobi25_count)),
            depth_imbalance_5_mean: snapshot
                .and_then(|agg| mean_from_sum(agg.wobi5_sum, agg.wobi5_count)),
            depth_imbalance_25_mean: snapshot
                .and_then(|agg| mean_from_sum(agg.wobi25_sum, agg.wobi25_count)),
            depth_bid_notional_5_median: snapshot
                .and_then(|agg| median(agg.bid_notional_5_values.clone())),
            depth_ask_notional_5_median: snapshot
                .and_then(|agg| median(agg.ask_notional_5_values.clone())),
            depth_bid_notional_25_median: snapshot
                .and_then(|agg| median(agg.bid_notional_25_values.clone())),
            depth_ask_notional_25_median: snapshot
                .and_then(|agg| median(agg.ask_notional_25_values.clone())),
            snapshot_microprice_offset_bps_mean: snapshot
                .and_then(|agg| mean_from_sum(agg.micro_offset_sum, agg.micro_offset_count)),
            trade_count,
            trade_amount_sum,
            trade_notional_quote_sum: trade_notional,
            reported_buy_amount: buy,
            reported_sell_amount: sell,
            reported_unknown_amount: unknown,
            trade_price_per_unit_vwap: trade_vwap,
            trade_price_per_token_last: trade_token_last,
            trade_flow_imbalance: safe_div(buy - sell, denom),
            reported_buy_share: safe_div(buy, denom),
            ret_1m_bps: None,
        });
    }
    rows.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
    });
    Ok(rows)
}

fn add_returns(state: &mut [StateRow]) {
    let mut prev = HashMap::<String, f64>::new();
    for row in state {
        let ret = prev
            .get(&row.symbol)
            .copied()
            .zip(row.mid_price_per_token_close)
            .and_then(|(prev, current)| {
                if prev > 0.0 && current > 0.0 {
                    finite((current / prev).ln() * 10_000.0)
                } else {
                    None
                }
            });
        if let Some(price) = row.mid_price_per_token_close.filter(|value| *value > 0.0) {
            prev.insert(row.symbol.clone(), price);
        }
        row.ret_1m_bps = ret;
    }
}

fn build_covariance_state(state: &[StateRow], run_tag: &str) -> Result<Vec<CovarianceRow>> {
    let mut returns_by_symbol = BTreeMap::<String, BTreeMap<u64, f64>>::new();
    let mut all_minutes = BTreeSet::<u64>::new();
    for row in state {
        all_minutes.insert(row.timestamp_us);
        if let Some(ret_bps) = row.ret_1m_bps {
            returns_by_symbol
                .entry(row.symbol.clone())
                .or_default()
                .insert(row.timestamp_us, ret_bps / 10_000.0);
        }
    }
    let symbols = returns_by_symbol.keys().cloned().collect::<Vec<_>>();
    let minutes = all_minutes.into_iter().collect::<Vec<_>>();
    let mut rows = Vec::with_capacity(minutes.len());
    for (idx, minute) in minutes.iter().copied().enumerate() {
        let start = idx.saturating_sub(59);
        let window_minutes = &minutes[start..=idx];
        let valid_symbols = symbols
            .iter()
            .filter(|symbol| {
                let map = returns_by_symbol.get(*symbol).unwrap();
                window_minutes
                    .iter()
                    .filter(|minute| map.contains_key(minute))
                    .count()
                    >= 20
            })
            .cloned()
            .collect::<Vec<_>>();
        let (avg_corr, eigen_share, cross_abs) = if valid_symbols.len() < 2 {
            (None, None, None)
        } else {
            covariance_metrics(window_minutes, &valid_symbols, &returns_by_symbol)
        };
        rows.push(CovarianceRow {
            run_tag: run_tag.to_string(),
            timestamp_utc: utc_from_us(minute)?,
            timestamp_us: minute,
            n_symbols: valid_symbols.len() as u64,
            symbols: valid_symbols.join(","),
            avg_corr_60m: avg_corr,
            first_eigen_share_60m: eigen_share,
            cross_symbol_abs_ret_mean_bps: cross_abs,
        });
    }
    Ok(rows)
}

fn covariance_metrics(
    window_minutes: &[u64],
    symbols: &[String],
    returns_by_symbol: &BTreeMap<String, BTreeMap<u64, f64>>,
) -> (Option<f64>, Option<f64>, Option<f64>) {
    let mut rows = Vec::<Vec<f64>>::new();
    let mut abs_values = Vec::<f64>::new();
    for minute in window_minutes {
        let mut row = Vec::with_capacity(symbols.len());
        let mut complete = true;
        for symbol in symbols {
            if let Some(value) = returns_by_symbol
                .get(symbol)
                .and_then(|map| map.get(minute))
                .copied()
            {
                row.push(value);
                abs_values.push(value.abs() * 10_000.0);
            } else {
                complete = false;
                break;
            }
        }
        if complete {
            rows.push(row);
        }
    }
    let cross_abs = mean(&abs_values);
    if rows.len() < 20 {
        return (None, None, cross_abs);
    }
    let n = rows.len() as f64;
    let cols = symbols.len();
    let mut means = vec![0.0; cols];
    for row in &rows {
        for col in 0..cols {
            means[col] += row[col];
        }
    }
    for mean in &mut means {
        *mean /= n;
    }
    let mut cov = vec![vec![0.0; cols]; cols];
    for row in &rows {
        for i in 0..cols {
            for j in i..cols {
                cov[i][j] += (row[i] - means[i]) * (row[j] - means[j]);
            }
        }
    }
    let denom = (rows.len().saturating_sub(1)).max(1) as f64;
    for i in 0..cols {
        for j in i..cols {
            cov[i][j] /= denom;
            cov[j][i] = cov[i][j];
        }
    }
    let mut corrs = Vec::new();
    for i in 0..cols {
        for j in (i + 1)..cols {
            let denom = (cov[i][i] * cov[j][j]).sqrt();
            if denom > 0.0 {
                corrs.push(cov[i][j] / denom);
            }
        }
    }
    let trace = (0..cols).map(|i| cov[i][i]).sum::<f64>();
    let eigen_share = if trace > 0.0 {
        finite(power_largest_eigenvalue(&cov) / trace)
    } else {
        None
    };
    (mean(&corrs), eigen_share, cross_abs)
}

fn build_path_labels(
    state: &[StateRow],
    horizons: &[u64],
    barriers: &[u64],
    run_tag: &str,
) -> Result<Vec<LabelRow>> {
    let mut by_symbol = BTreeMap::<String, Vec<&StateRow>>::new();
    for row in state {
        by_symbol.entry(row.symbol.clone()).or_default().push(row);
    }
    let mut labels = Vec::new();
    for (symbol, mut rows) in by_symbol {
        rows.sort_by_key(|row| row.timestamp_us);
        let prices = rows
            .iter()
            .map(|row| row.mid_price_per_token_close)
            .collect::<Vec<_>>();
        for horizon in horizons {
            let horizon_minutes = *horizon as usize * 60;
            let horizon_us = *horizon * 60 * 60 * 1_000_000;
            for barrier in barriers {
                for (idx, row) in rows.iter().enumerate() {
                    let mut status = "ok";
                    let mut outcome = "future_missing".to_string();
                    let mut mfe = None;
                    let mut mae = None;
                    let mut final_return = None;
                    if idx + horizon_minutes >= rows.len()
                        || rows[idx + horizon_minutes]
                            .timestamp_us
                            .saturating_sub(row.timestamp_us)
                            < horizon_us
                    {
                        status = "future_missing";
                    } else if let Some(price0) = prices[idx] {
                        let result = first_hit(
                            price0,
                            &prices[(idx + 1)..=(idx + horizon_minutes)],
                            *barrier as f64,
                        );
                        outcome = result.0;
                        mfe = result.1;
                        mae = result.2;
                        final_return = result.3;
                        if outcome == "future_missing" {
                            status = "future_missing";
                        }
                    } else {
                        status = "future_missing";
                    }
                    labels.push(LabelRow {
                        run_tag: run_tag.to_string(),
                        timestamp_utc: row.timestamp_utc.clone(),
                        timestamp_us: row.timestamp_us,
                        symbol: symbol.clone(),
                        asset: row.asset.clone(),
                        horizon_hours: *horizon,
                        barrier_bps: *barrier,
                        price_per_token: prices[idx],
                        future_return_bps: final_return,
                        mfe_up_bps: mfe,
                        mae_down_bps: mae,
                        barrier_first_hit: outcome,
                        label_status: status.to_string(),
                    });
                }
            }
        }
    }
    Ok(labels)
}

fn first_hit(
    price0: f64,
    future: &[Option<f64>],
    barrier_bps: f64,
) -> (String, Option<f64>, Option<f64>, Option<f64>) {
    if !price0.is_finite() || price0 <= 0.0 || future.is_empty() {
        return ("future_missing".to_string(), None, None, None);
    }
    let mut path = Vec::with_capacity(future.len());
    for price in future {
        path.push(price.and_then(|price| {
            if price > 0.0 {
                finite((price / price0).ln() * 10_000.0)
            } else {
                None
            }
        }));
    }
    if path.iter().all(Option::is_none) {
        return ("future_missing".to_string(), None, None, None);
    }
    let finite_path = path.iter().filter_map(|value| *value).collect::<Vec<_>>();
    let mfe = finite_path.iter().copied().reduce(f64::max);
    let mae = finite_path.iter().copied().reduce(f64::min);
    let final_return = path.last().copied().flatten();
    let up = path
        .iter()
        .position(|value| value.is_some_and(|value| value >= barrier_bps));
    let down = path
        .iter()
        .position(|value| value.is_some_and(|value| value <= -barrier_bps));
    let outcome = match (up, down) {
        (None, None) => "none",
        (Some(_), None) => "upper_first",
        (None, Some(_)) => "lower_first",
        (Some(up), Some(down)) if up == down => "both_or_ambiguous",
        (Some(up), Some(down)) if up < down => "upper_first",
        (Some(_), Some(_)) => "lower_first",
    };
    (outcome.to_string(), mfe, mae, final_return)
}

fn build_summary(
    state: &[StateRow],
    labels: &[LabelRow],
    quality: &[QualityRow],
) -> Vec<SummaryRow> {
    let mut by_symbol = BTreeMap::<String, Vec<&StateRow>>::new();
    for row in state {
        by_symbol.entry(row.symbol.clone()).or_default().push(row);
    }
    let mut quality_by_symbol = BTreeMap::<String, Vec<&QualityRow>>::new();
    for row in quality {
        quality_by_symbol
            .entry(row.symbol.clone())
            .or_default()
            .push(row);
    }
    let mut labels_by_symbol = BTreeMap::<String, Vec<&LabelRow>>::new();
    for row in labels
        .iter()
        .filter(|row| row.horizon_hours == 12 && row.barrier_bps == 100)
    {
        labels_by_symbol
            .entry(row.symbol.clone())
            .or_default()
            .push(row);
    }
    let mut out = Vec::new();
    for (symbol, rows) in by_symbol {
        let quality_rows = quality_by_symbol.get(&symbol).cloned().unwrap_or_default();
        let label_rows = labels_by_symbol.get(&symbol).cloned().unwrap_or_default();
        let upper = label_rows
            .iter()
            .filter(|row| row.barrier_first_hit == "upper_first")
            .count();
        let lower = label_rows
            .iter()
            .filter(|row| row.barrier_first_hit == "lower_first")
            .count();
        out.push(SummaryRow {
            symbol: symbol.clone(),
            asset: rows
                .first()
                .map(|row| row.asset.clone())
                .unwrap_or_default(),
            state_rows: rows.len() as u64,
            first_timestamp_utc: rows
                .first()
                .map(|row| row.timestamp_utc.clone())
                .unwrap_or_default(),
            last_timestamp_utc: rows
                .last()
                .map(|row| row.timestamp_utc.clone())
                .unwrap_or_default(),
            median_mid_price_per_unit: median(
                rows.iter()
                    .filter_map(|row| row.mid_price_per_unit_close)
                    .collect(),
            ),
            median_price_per_token: median(
                rows.iter()
                    .filter_map(|row| row.mid_price_per_token_close)
                    .collect(),
            ),
            median_spread_bps: median(
                rows.iter()
                    .filter_map(|row| row.spread_bps_median)
                    .collect(),
            ),
            total_book_ticker_rows: rows.iter().map(|row| row.book_ticker_count).sum(),
            total_snapshot_rows: rows.iter().map(|row| row.snapshot_count).sum(),
            total_trades: rows.iter().map(|row| row.trade_count).sum(),
            total_trade_notional_quote: rows.iter().map(|row| row.trade_notional_quote_sum).sum(),
            raw_files: quality_rows.len() as u64,
            raw_rows: quality_rows.iter().map(|row| row.rows).sum(),
            raw_error_files: quality_rows
                .iter()
                .filter(|row| row.status == "error")
                .count() as u64,
            raw_empty_files: quality_rows
                .iter()
                .filter(|row| row.status == "empty")
                .count() as u64,
            timestamp_monotonic_violations: quality_rows
                .iter()
                .map(|row| row.timestamp_monotonic_violations)
                .sum(),
            duplicate_rows_in_chunks: quality_rows
                .iter()
                .map(|row| row.duplicate_rows_in_chunks)
                .sum(),
            empty_price_rows: quality_rows.iter().map(|row| row.empty_price_rows).sum(),
            negative_amount_rows: quality_rows
                .iter()
                .map(|row| row.negative_amount_rows)
                .sum(),
            abnormal_spread_rows: quality_rows
                .iter()
                .map(|row| row.abnormal_spread_rows)
                .sum(),
            valid_label_rows: label_rows
                .iter()
                .filter(|row| row.label_status == "ok")
                .count() as u64,
            future_missing_rows: label_rows
                .iter()
                .filter(|row| row.label_status == "future_missing")
                .count() as u64,
            upper_first_rate: safe_div(upper as f64, label_rows.len() as f64),
            lower_first_rate: safe_div(lower as f64, label_rows.len() as f64),
        });
    }
    out
}

fn build_joined_groups(
    state: &[StateRow],
    labels: &[LabelRow],
) -> BTreeMap<(String, u64, u64), Vec<JoinedRow>> {
    let mut state_index = HashMap::<(String, u64), usize>::new();
    for (index, row) in state.iter().enumerate() {
        state_index.insert((row.symbol.clone(), row.timestamp_us), index);
    }
    let mut groups = BTreeMap::<(String, u64, u64), Vec<JoinedRow>>::new();
    for label in labels.iter().filter(|row| row.label_status == "ok") {
        if let Some(index) = state_index
            .get(&(label.symbol.clone(), label.timestamp_us))
            .copied()
        {
            groups
                .entry((label.symbol.clone(), label.horizon_hours, label.barrier_bps))
                .or_default()
                .push(JoinedRow {
                    minute_us: label.timestamp_us,
                    state_index: index,
                    barrier_first_hit: label.barrier_first_hit.clone(),
                    future_return_bps: label.future_return_bps,
                    mfe_up_bps: label.mfe_up_bps,
                    mae_down_bps: label.mae_down_bps,
                });
        }
    }
    groups
}

fn build_factor_tests(state: &[StateRow], labels: &[LabelRow]) -> Vec<FactorTestRow> {
    let groups = build_joined_groups(state, labels);
    let mut rows = Vec::new();
    for ((symbol, horizon, barrier), group) in groups {
        let baseline_upper = rate(
            group.iter().map(|row| row.barrier_first_hit.as_str()),
            "upper_first",
        );
        let baseline_lower = rate(
            group.iter().map(|row| row.barrier_first_hit.as_str()),
            "lower_first",
        );
        for factor in FACTOR_COLS {
            let values = group
                .iter()
                .map(|row| factor_value(&state[row.state_index], factor))
                .collect::<Vec<_>>();
            let buckets = qbucket(&values);
            for bucket_name in ["flat", "high", "low", "mid"] {
                let indexes = buckets
                    .iter()
                    .enumerate()
                    .filter_map(|(index, bucket)| {
                        (bucket.as_deref() == Some(bucket_name)).then_some(index)
                    })
                    .collect::<Vec<_>>();
                if indexes.is_empty() {
                    continue;
                }
                let outcomes = indexes
                    .iter()
                    .map(|idx| group[*idx].barrier_first_hit.as_str())
                    .collect::<Vec<_>>();
                rows.push(FactorTestRow {
                    symbol: symbol.clone(),
                    horizon_hours: horizon,
                    barrier_bps: barrier,
                    factor: factor.to_string(),
                    bucket: bucket_name.to_string(),
                    rows: indexes.len() as u64,
                    upper_first_rate: rate(outcomes.iter().copied(), "upper_first"),
                    lower_first_rate: rate(outcomes.iter().copied(), "lower_first"),
                    baseline_upper_first_rate: baseline_upper,
                    baseline_lower_first_rate: baseline_lower,
                    edge_vs_baseline_upper: rate(outcomes.iter().copied(), "upper_first")
                        .zip(baseline_upper)
                        .and_then(|(a, b)| finite(a - b)),
                    median_factor: median(indexes.iter().filter_map(|idx| values[*idx]).collect()),
                    median_future_return_bps: median(
                        indexes
                            .iter()
                            .filter_map(|idx| group[*idx].future_return_bps)
                            .collect(),
                    ),
                    median_mfe_up_bps: median(
                        indexes
                            .iter()
                            .filter_map(|idx| group[*idx].mfe_up_bps)
                            .collect(),
                    ),
                    median_mae_down_bps: median(
                        indexes
                            .iter()
                            .filter_map(|idx| group[*idx].mae_down_bps)
                            .collect(),
                    ),
                });
            }
        }
    }
    rows
}

fn build_stability_checks(state: &[StateRow], labels: &[LabelRow]) -> Vec<StabilityRow> {
    let groups = build_joined_groups(state, labels);
    let mut rows = Vec::new();
    for ((symbol, horizon, barrier), mut group) in groups {
        group.sort_by_key(|row| row.minute_us);
        let horizon_minutes = horizon * 60;
        for factor in FACTOR_COLS {
            let clean = group
                .iter()
                .filter_map(|row| {
                    factor_value(&state[row.state_index], factor).map(|value| (row.clone(), value))
                })
                .collect::<Vec<_>>();
            let unique = clean
                .iter()
                .map(|(_, value)| value.to_bits())
                .collect::<BTreeSet<_>>();
            if clean.len() < 30 || unique.len() < 3 {
                continue;
            }
            let (high_rows, high_rate, edge) = high_bucket_edge(&clean);
            rows.push(StabilityRow {
                check: "full_sample_reference".to_string(),
                symbol: symbol.clone(),
                horizon_hours: horizon,
                barrier_bps: barrier,
                factor: factor.to_string(),
                slice: "all".to_string(),
                rows: clean.len() as u64,
                high_bucket_rows: high_rows,
                upper_first_rate_high: high_rate,
                edge_vs_baseline_upper: edge,
            });
            let non_overlap = clean
                .iter()
                .step_by(horizon_minutes.max(1) as usize)
                .cloned()
                .collect::<Vec<_>>();
            let (high_rows, high_rate, edge) = high_bucket_edge(&non_overlap);
            rows.push(StabilityRow {
                check: "non_overlap".to_string(),
                symbol: symbol.clone(),
                horizon_hours: horizon,
                barrier_bps: barrier,
                factor: factor.to_string(),
                slice: format!("stride_{}m", horizon_minutes.max(1)),
                rows: non_overlap.len() as u64,
                high_bucket_rows: high_rows,
                upper_first_rate_high: high_rate,
                edge_vs_baseline_upper: edge,
            });
            let shifted = clean
                .iter()
                .enumerate()
                .filter_map(|(index, (row, _))| {
                    index.checked_sub(60).map(|src| (row.clone(), clean[src].1))
                })
                .collect::<Vec<_>>();
            let (high_rows, high_rate, edge) = high_bucket_edge(&shifted);
            rows.push(StabilityRow {
                check: "placebo_shift".to_string(),
                symbol: symbol.clone(),
                horizon_hours: horizon,
                barrier_bps: barrier,
                factor: factor.to_string(),
                slice: "factor_shifted_60m".to_string(),
                rows: shifted.len() as u64,
                high_bucket_rows: high_rows,
                upper_first_rate_high: high_rate,
                edge_vs_baseline_upper: edge,
            });
            let first_min = clean.first().map(|(row, _)| row.minute_us).unwrap_or(0);
            let last_min = clean
                .last()
                .map(|(row, _)| row.minute_us)
                .unwrap_or(first_min);
            let midpoint = first_min + (last_min.saturating_sub(first_min) / 2);
            for (slice, sub) in [
                (
                    "first_half",
                    clean
                        .iter()
                        .filter(|(row, _)| row.minute_us <= midpoint)
                        .cloned()
                        .collect::<Vec<_>>(),
                ),
                (
                    "second_half",
                    clean
                        .iter()
                        .filter(|(row, _)| row.minute_us > midpoint)
                        .cloned()
                        .collect::<Vec<_>>(),
                ),
            ] {
                let (high_rows, high_rate, edge) = high_bucket_edge(&sub);
                rows.push(StabilityRow {
                    check: "forward_split".to_string(),
                    symbol: symbol.clone(),
                    horizon_hours: horizon,
                    barrier_bps: barrier,
                    factor: factor.to_string(),
                    slice: slice.to_string(),
                    rows: sub.len() as u64,
                    high_bucket_rows: high_rows,
                    upper_first_rate_high: high_rate,
                    edge_vs_baseline_upper: edge,
                });
            }
        }
        let upper = rate(
            group.iter().map(|row| row.barrier_first_hit.as_str()),
            "upper_first",
        );
        let lower = rate(
            group.iter().map(|row| row.barrier_first_hit.as_str()),
            "lower_first",
        );
        rows.push(StabilityRow {
            check: "barrier_sensitivity".to_string(),
            symbol,
            horizon_hours: horizon,
            barrier_bps: barrier,
            factor: "baseline".to_string(),
            slice: "all".to_string(),
            rows: group.len() as u64,
            high_bucket_rows: group.len() as u64,
            upper_first_rate_high: upper,
            edge_vs_baseline_upper: lower,
        });
    }
    rows
}

fn high_bucket_edge(clean: &[(JoinedRow, f64)]) -> (u64, Option<f64>, Option<f64>) {
    if clean.is_empty() {
        return (0, None, None);
    }
    let values = clean
        .iter()
        .map(|(_, value)| Some(*value))
        .collect::<Vec<_>>();
    let buckets = qbucket(&values);
    let high = buckets
        .iter()
        .enumerate()
        .filter_map(|(idx, bucket)| (bucket.as_deref() == Some("high")).then_some(idx))
        .collect::<Vec<_>>();
    if high.is_empty() {
        return (0, None, None);
    }
    let baseline = rate(
        clean.iter().map(|(row, _)| row.barrier_first_hit.as_str()),
        "upper_first",
    );
    let high_rate = rate(
        high.iter()
            .map(|idx| clean[*idx].0.barrier_first_hit.as_str()),
        "upper_first",
    );
    let edge = high_rate
        .zip(baseline)
        .and_then(|(high, base)| finite(high - base));
    (high.len() as u64, high_rate, edge)
}

fn qbucket(values: &[Option<f64>]) -> Vec<Option<String>> {
    let mut out = vec![None; values.len()];
    let mut valid = values
        .iter()
        .enumerate()
        .filter_map(|(index, value)| value.and_then(finite).map(|value| (index, value)))
        .collect::<Vec<_>>();
    if valid.is_empty() {
        return out;
    }
    let unique = valid
        .iter()
        .map(|(_, value)| value.to_bits())
        .collect::<BTreeSet<_>>();
    if unique.len() < 3 {
        for (index, _) in valid {
            out[index] = Some("flat".to_string());
        }
        return out;
    }
    valid.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
    let len = valid.len();
    for (position, (index, _)) in valid.into_iter().enumerate() {
        let bucket = match ((position * 3) / len).min(2) {
            0 => "low",
            1 => "mid",
            _ => "high",
        };
        out[index] = Some(bucket.to_string());
    }
    out
}

fn factor_value(row: &StateRow, factor: &str) -> Option<f64> {
    match factor {
        "spread_bps_median" => row.spread_bps_median,
        "spread_bps_last" => row.spread_bps_last,
        "microprice_offset_bps_mean" => row.microprice_offset_bps_mean,
        "wobi5_mean" => row.wobi5_mean,
        "wobi25_mean" => row.wobi25_mean,
        "depth_imbalance_5_mean" => row.depth_imbalance_5_mean,
        "depth_imbalance_25_mean" => row.depth_imbalance_25_mean,
        "trade_flow_imbalance" => row.trade_flow_imbalance,
        "reported_buy_share" => row.reported_buy_share,
        "trade_notional_quote_sum" => Some(row.trade_notional_quote_sum),
        "book_ticker_count" => Some(row.book_ticker_count as f64),
        "snapshot_count" => Some(row.snapshot_count as f64),
        "trade_count" => Some(row.trade_count as f64),
        _ => None,
    }
}

fn write_state_parquet(path: &Path, rows: &[StateRow]) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("timestamp_utc", DataType::Utf8, false),
        Field::new("timestamp_us", DataType::UInt64, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("asset", DataType::Utf8, false),
        Field::new("price_unit", DataType::Utf8, false),
        Field::new("book_ticker_count", DataType::UInt64, false),
        Field::new("bid_price_last", DataType::Float64, true),
        Field::new("ask_price_last", DataType::Float64, true),
        Field::new("mid_price_per_unit_open", DataType::Float64, true),
        Field::new("mid_price_per_unit_high", DataType::Float64, true),
        Field::new("mid_price_per_unit_low", DataType::Float64, true),
        Field::new("mid_price_per_unit_close", DataType::Float64, true),
        Field::new("mid_price_per_token_close", DataType::Float64, true),
        Field::new("spread_bps_median", DataType::Float64, true),
        Field::new("spread_bps_last", DataType::Float64, true),
        Field::new("top_depth_bid_notional_median", DataType::Float64, true),
        Field::new("top_depth_ask_notional_median", DataType::Float64, true),
        Field::new("microprice_offset_bps_mean", DataType::Float64, true),
        Field::new("snapshot_count", DataType::UInt64, false),
        Field::new("snapshot_spread_bps_median", DataType::Float64, true),
        Field::new("wobi5_mean", DataType::Float64, true),
        Field::new("wobi25_mean", DataType::Float64, true),
        Field::new("depth_imbalance_5_mean", DataType::Float64, true),
        Field::new("depth_imbalance_25_mean", DataType::Float64, true),
        Field::new("depth_bid_notional_5_median", DataType::Float64, true),
        Field::new("depth_ask_notional_5_median", DataType::Float64, true),
        Field::new("depth_bid_notional_25_median", DataType::Float64, true),
        Field::new("depth_ask_notional_25_median", DataType::Float64, true),
        Field::new(
            "snapshot_microprice_offset_bps_mean",
            DataType::Float64,
            true,
        ),
        Field::new("trade_count", DataType::UInt64, false),
        Field::new("trade_amount_sum", DataType::Float64, false),
        Field::new("trade_notional_quote_sum", DataType::Float64, false),
        Field::new("reported_buy_amount", DataType::Float64, false),
        Field::new("reported_sell_amount", DataType::Float64, false),
        Field::new("reported_unknown_amount", DataType::Float64, false),
        Field::new("trade_price_per_unit_vwap", DataType::Float64, true),
        Field::new("trade_price_per_token_last", DataType::Float64, true),
        Field::new("trade_flow_imbalance", DataType::Float64, true),
        Field::new("reported_buy_share", DataType::Float64, true),
        Field::new("ret_1m_bps", DataType::Float64, true),
    ]));
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            str_col(rows, |row| &row.run_tag),
            str_col(rows, |row| &row.timestamp_utc),
            u64_array(&rows.iter().map(|row| row.timestamp_us).collect::<Vec<_>>()),
            str_col(rows, |row| &row.symbol),
            str_col(rows, |row| &row.asset),
            str_col(rows, |row| &row.price_unit),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.book_ticker_count)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_col(rows, |row| row.bid_price_last),
            opt_f64_col(rows, |row| row.ask_price_last),
            opt_f64_col(rows, |row| row.mid_price_per_unit_open),
            opt_f64_col(rows, |row| row.mid_price_per_unit_high),
            opt_f64_col(rows, |row| row.mid_price_per_unit_low),
            opt_f64_col(rows, |row| row.mid_price_per_unit_close),
            opt_f64_col(rows, |row| row.mid_price_per_token_close),
            opt_f64_col(rows, |row| row.spread_bps_median),
            opt_f64_col(rows, |row| row.spread_bps_last),
            opt_f64_col(rows, |row| row.top_depth_bid_notional_median),
            opt_f64_col(rows, |row| row.top_depth_ask_notional_median),
            opt_f64_col(rows, |row| row.microprice_offset_bps_mean),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.snapshot_count)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_col(rows, |row| row.snapshot_spread_bps_median),
            opt_f64_col(rows, |row| row.wobi5_mean),
            opt_f64_col(rows, |row| row.wobi25_mean),
            opt_f64_col(rows, |row| row.depth_imbalance_5_mean),
            opt_f64_col(rows, |row| row.depth_imbalance_25_mean),
            opt_f64_col(rows, |row| row.depth_bid_notional_5_median),
            opt_f64_col(rows, |row| row.depth_ask_notional_5_median),
            opt_f64_col(rows, |row| row.depth_bid_notional_25_median),
            opt_f64_col(rows, |row| row.depth_ask_notional_25_median),
            opt_f64_col(rows, |row| row.snapshot_microprice_offset_bps_mean),
            u64_array(&rows.iter().map(|row| row.trade_count).collect::<Vec<_>>()),
            f64_col(rows, |row| row.trade_amount_sum),
            f64_col(rows, |row| row.trade_notional_quote_sum),
            f64_col(rows, |row| row.reported_buy_amount),
            f64_col(rows, |row| row.reported_sell_amount),
            f64_col(rows, |row| row.reported_unknown_amount),
            opt_f64_col(rows, |row| row.trade_price_per_unit_vwap),
            opt_f64_col(rows, |row| row.trade_price_per_token_last),
            opt_f64_col(rows, |row| row.trade_flow_imbalance),
            opt_f64_col(rows, |row| row.reported_buy_share),
            opt_f64_col(rows, |row| row.ret_1m_bps),
        ],
    )?;
    write_parquet_atomic(path, schema, batch)
}

fn write_covariance_parquet(path: &Path, rows: &[CovarianceRow]) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("timestamp_utc", DataType::Utf8, false),
        Field::new("timestamp_us", DataType::UInt64, false),
        Field::new("n_symbols", DataType::UInt64, false),
        Field::new("symbols", DataType::Utf8, false),
        Field::new("avg_corr_60m", DataType::Float64, true),
        Field::new("first_eigen_share_60m", DataType::Float64, true),
        Field::new("cross_symbol_abs_ret_mean_bps", DataType::Float64, true),
    ]));
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            str_col(rows, |row| &row.run_tag),
            str_col(rows, |row| &row.timestamp_utc),
            u64_array(&rows.iter().map(|row| row.timestamp_us).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.n_symbols).collect::<Vec<_>>()),
            str_col(rows, |row| &row.symbols),
            opt_f64_col(rows, |row| row.avg_corr_60m),
            opt_f64_col(rows, |row| row.first_eigen_share_60m),
            opt_f64_col(rows, |row| row.cross_symbol_abs_ret_mean_bps),
        ],
    )?;
    write_parquet_atomic(path, schema, batch)
}

fn write_labels_parquet(path: &Path, rows: &[LabelRow]) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("timestamp_utc", DataType::Utf8, false),
        Field::new("timestamp_us", DataType::UInt64, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("asset", DataType::Utf8, false),
        Field::new("horizon_hours", DataType::UInt64, false),
        Field::new("barrier_bps", DataType::UInt64, false),
        Field::new("price_per_token", DataType::Float64, true),
        Field::new("future_return_bps", DataType::Float64, true),
        Field::new("mfe_up_bps", DataType::Float64, true),
        Field::new("mae_down_bps", DataType::Float64, true),
        Field::new("barrier_first_hit", DataType::Utf8, false),
        Field::new("label_status", DataType::Utf8, false),
    ]));
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            str_col(rows, |row| &row.run_tag),
            str_col(rows, |row| &row.timestamp_utc),
            u64_array(&rows.iter().map(|row| row.timestamp_us).collect::<Vec<_>>()),
            str_col(rows, |row| &row.symbol),
            str_col(rows, |row| &row.asset),
            u64_array(&rows.iter().map(|row| row.horizon_hours).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.barrier_bps).collect::<Vec<_>>()),
            opt_f64_col(rows, |row| row.price_per_token),
            opt_f64_col(rows, |row| row.future_return_bps),
            opt_f64_col(rows, |row| row.mfe_up_bps),
            opt_f64_col(rows, |row| row.mae_down_bps),
            str_col(rows, |row| &row.barrier_first_hit),
            str_col(rows, |row| &row.label_status),
        ],
    )?;
    write_parquet_atomic(path, schema, batch)
}

fn render_report(
    paths: &OutputPaths,
    report_summary: &BullishL2ReportSummary,
    state: &[StateRow],
    _labels: &[LabelRow],
    quality: &[QualityRow],
    summary_rows: &[SummaryRow],
    factor_tests: &[FactorTestRow],
    stability: &[StabilityRow],
    price_context: &PriceContextReportStatus,
    horizons: &[u64],
    barriers: &[u64],
) -> Result<()> {
    let symbols = state
        .iter()
        .map(|row| row.symbol.clone())
        .collect::<BTreeSet<_>>();
    let empty_files = quality.iter().filter(|row| row.status == "empty").count();
    let error_files = quality.iter().filter(|row| row.status == "error").count();
    let mut lines = Vec::new();
    lines.push("# BONK Bullish L2 + CEX Regime 报告 v1".to_string());
    lines.push(String::new());
    lines.push(format!("- `run_tag`: `{}`", report_summary.run_tag));
    lines.push(
        "- 实现：Rust streaming gzip CSV 聚合；Python 脚本保留作 baseline/回滚。".to_string(),
    );
    lines.push("- 数据源：Tardis downloadable CSV，exchange=`bullish`。".to_string());
    lines.push("- 当前版本只使用 `book_snapshot_25`、`book_ticker`、`trades`，没有使用 `incremental_book_L2`。".to_string());
    lines.push("- Bullish `BONK1M*` 价格按每 1M BONK 报价保存，同时派生 `price_per_token = price / 1_000_000`。".to_string());
    lines.push(
        "- `trades.side` 暂记为 exchange-reported side；未在本报告中断言 taker buy/sell 语义。"
            .to_string(),
    );
    lines.push(
        "- 本报告只评价数据质量和现象稳定性入口，不输出交易规则，也不声称 alpha。".to_string(),
    );
    lines.push(format!(
        "- State/covariance symbols: `{}`；summary/factor tests 聚焦 path-labeled symbols。",
        symbols.into_iter().collect::<Vec<_>>().join(",")
    ));
    lines.push(format!(
        "- Rust report elapsed: `{:.2}s`。",
        report_summary.elapsed_seconds
    ));
    lines.push(format!(
        "- Price context status: `{}`；run_tag=`{}`。",
        price_context.status, price_context.run_tag
    ));
    lines.push(String::new());
    lines.push("## 输出文件".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- L2 state parquet: `{}`",
        path_string(&paths.l2_state_parquet)
    ));
    lines.push(format!(
        "- Covariance state parquet: `{}`",
        path_string(&paths.covariance_parquet)
    ));
    lines.push(format!(
        "- Path labels parquet: `{}`",
        path_string(&paths.labels_parquet)
    ));
    lines.push(format!(
        "- Quality CSV: `{}`",
        path_string(&paths.quality_csv)
    ));
    lines.push(format!(
        "- Summary CSV: `{}`",
        path_string(&paths.summary_csv)
    ));
    lines.push(format!(
        "- Factor tests CSV: `{}`",
        path_string(&paths.factor_tests_csv)
    ));
    lines.push(format!(
        "- Stability CSV: `{}`",
        path_string(&paths.stability_csv)
    ));
    if price_context.status == "available" {
        lines.push(format!(
            "- Kline price context parquet: `{}`",
            price_context.price_context_parquet
        ));
        lines.push(format!(
            "- Kline price context summary CSV: `{}`",
            price_context.summary_csv
        ));
    }
    lines.push(String::new());
    lines.push("## 覆盖与质量".to_string());
    lines.push(String::new());
    lines.push("| symbol | state rows | raw files | raw rows | first ts | last ts | median price/1M | median price/token | median spread bps | trades | abnormal spread rows | future missing 12h/100bps |".to_string());
    lines.push("|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|".to_string());
    for row in summary_rows {
        lines.push(format!(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
            row.symbol,
            row.state_rows,
            row.raw_files,
            row.raw_rows,
            row.first_timestamp_utc,
            row.last_timestamp_utc,
            fmt_num(row.median_mid_price_per_unit, 6),
            fmt_num(row.median_price_per_token, 12),
            fmt_num(row.median_spread_bps, 2),
            row.total_trades,
            row.abnormal_spread_rows,
            row.future_missing_rows
        ));
    }
    lines.push(String::new());
    lines.push(format!(
        "- Raw file errors: `{error_files}`；empty raw files: `{empty_files}`。"
    ));
    lines.push(format!(
        "- Label horizons: `{:?}` hours; fixed first-passage barriers: `{:?}` bps。",
        horizons, barriers
    ));
    lines.push("- 最后 H 小时样本会被标成 `future_missing`，避免用不存在的未来路径。".to_string());
    lines.push(String::new());
    lines.push("## Kline Price Context".to_string());
    lines.push(String::new());
    if price_context.status == "available" {
        lines.push("- 价格背景层只使用 Binance public spot 1m kline；它用于 market/meme/SOL 对照，不作为交易规则或 alpha 证据。".to_string());
        lines.push(format!(
            "- Context rows: `{}`；available symbols: `{}`；missing symbols: `{}`。",
            price_context.rows,
            join_or_none(&price_context.available_symbols),
            join_or_none(&price_context.missing_symbols)
        ));
        lines.push("| context | coverage | total return bps | BONK relative bps |".to_string());
        lines.push("|---|---:|---:|---:|".to_string());
        lines.push(format!(
            "| BTC/ETH/SOL market | {} | {} | {} |",
            fmt_pct(price_context.market_coverage),
            fmt_num(price_context.market_return_bps, 2),
            fmt_num(price_context.bonk_rel_market_bps, 2)
        ));
        lines.push(format!(
            "| meme basket | {} | {} | {} |",
            fmt_pct(price_context.meme_coverage),
            fmt_num(price_context.meme_return_bps, 2),
            fmt_num(price_context.bonk_rel_meme_bps, 2)
        ));
        lines.push(format!(
            "| SOL | {} | {} | {} |",
            fmt_pct(price_context.sol_coverage),
            fmt_num(price_context.sol_return_bps, 2),
            fmt_num(price_context.bonk_rel_sol_bps, 2)
        ));
        lines.push(format!(
            "- BONK total return over context window: `{}` bps。",
            fmt_num(price_context.bonk_return_bps, 2)
        ));
    } else {
        lines.push(format!(
            "- Price context unavailable for this run: `{}`. L2 diagnostics were still generated normally.",
            price_context.message
        ));
    }
    lines.push(String::new());
    lines.push("## 因子诊断快读".to_string());
    lines.push(String::new());
    let top = top_factor_rows(factor_tests);
    if top.is_empty() {
        lines.push("- No factor rows produced.".to_string());
    } else {
        lines.push("| symbol | H | factor | high rows | high upper first | baseline upper | edge | median factor |".to_string());
        lines.push("|---|---:|---|---:|---:|---:|---:|---:|".to_string());
        for row in top {
            lines.push(format!(
                "| {} | {}h | `{}` | {} | {} | {} | {} | {} |",
                row.symbol,
                row.horizon_hours,
                row.factor,
                row.rows,
                fmt_pct(row.upper_first_rate),
                fmt_pct(row.baseline_upper_first_rate),
                fmt_pct(row.edge_vs_baseline_upper),
                fmt_num(row.median_factor, 4)
            ));
        }
    }
    lines.push(String::new());
    lines.push("## 稳定性检查入口".to_string());
    lines.push(String::new());
    lines.push("报告和 CSV 已显式输出四类稳定性检查入口：".to_string());
    lines.push(String::new());
    lines.push("- `non_overlap`: 按 horizon stride 抽样，降低重叠标签自相关。".to_string());
    lines.push("- `placebo_shift`: 因子整体滞后 60 分钟后重测，排查伪相关。".to_string());
    lines.push("- `forward_split`: 前半窗口和后半窗口分别计算 high-bucket edge。".to_string());
    lines.push(
        "- `barrier_sensitivity`: 50/100/200/300 bps barrier 的 baseline first-passage 变化。"
            .to_string(),
    );
    lines.push(String::new());
    let checks = stability
        .iter()
        .map(|row| row.check.clone())
        .collect::<BTreeSet<_>>();
    lines.push(format!(
        "- Stability checks present: `{}`。",
        checks.into_iter().collect::<Vec<_>>().join(",")
    ));
    write_text_atomic(&paths.report_md, &lines.join("\n"))
}

fn top_factor_rows(rows: &[FactorTestRow]) -> Vec<&FactorTestRow> {
    let mut filtered = rows
        .iter()
        .filter(|row| {
            row.bucket == "high"
                && row.barrier_bps == 100
                && matches!(row.horizon_hours, 1 | 4 | 12)
        })
        .collect::<Vec<_>>();
    filtered.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.horizon_hours.cmp(&b.horizon_hours))
            .then_with(|| desc_opt_abs(a.edge_vs_baseline_upper, b.edge_vs_baseline_upper))
    });
    let mut out = Vec::new();
    let mut counts = BTreeMap::<(String, u64), usize>::new();
    for row in filtered {
        let key = (row.symbol.clone(), row.horizon_hours);
        let count = counts.entry(key).or_default();
        if *count < 6 {
            out.push(row);
            *count += 1;
        }
    }
    out
}

fn output_paths(config: &BullishL2ReportConfig) -> OutputPaths {
    OutputPaths {
        l2_state_parquet: config
            .data_root
            .join("derived")
            .join("bonk_cex_l2_state")
            .join(format!("bonk_cex_l2_state_{}.parquet", config.run_tag)),
        covariance_parquet: config
            .data_root
            .join("derived")
            .join("bonk_cex_covariance_state")
            .join(format!(
                "bonk_cex_covariance_state_{}.parquet",
                config.run_tag
            )),
        labels_parquet: config
            .data_root
            .join("derived")
            .join("bonk_path_labels")
            .join(format!("bonk_path_labels_{}.parquet", config.run_tag)),
        quality_csv: config
            .date_dir
            .join(format!("bonk_v1_cex_l2_quality_{}.csv", config.run_tag)),
        summary_csv: config
            .date_dir
            .join(format!("bonk_v1_cex_l2_summary_{}.csv", config.run_tag)),
        factor_tests_csv: config.date_dir.join(format!(
            "bonk_v1_cex_l2_factor_tests_{}.csv",
            config.run_tag
        )),
        stability_csv: config
            .date_dir
            .join(format!("bonk_v1_cex_l2_stability_{}.csv", config.run_tag)),
        completion_json: config
            .date_dir
            .join(format!("bonk_v1_cex_l2_completion_{}.json", config.run_tag)),
        report_md: config.doc_dir.join("v1-cex-l2-report.md"),
    }
}

fn parse_int_list(raw: &str) -> Result<Vec<u64>> {
    let mut out = Vec::new();
    for value in raw
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        out.push(
            value
                .parse::<u64>()
                .with_context(|| format!("invalid integer {value}"))?,
        );
    }
    out.sort_unstable();
    out.dedup();
    if out.is_empty() {
        bail!("empty integer list");
    }
    Ok(out)
}

fn parse_header_line(line: &str) -> Result<Vec<String>> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .from_reader(line.as_bytes());
    let record = reader
        .records()
        .next()
        .ok_or_else(|| anyhow!("missing CSV header"))?
        .context("failed to parse CSV header")?;
    Ok(record.iter().map(str::to_string).collect())
}

fn hash_record(record: &csv::StringRecord) -> u64 {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    for field in record {
        field.hash(&mut hasher);
        0xffu8.hash(&mut hasher);
    }
    hasher.finish()
}

fn abnormal_spread(record: &csv::StringRecord, indexes: &HeaderIndexes) -> Option<f64> {
    let bid = indexes
        .bid_price
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    let ask = indexes
        .ask_price
        .and_then(|idx| parse_f64(record.get(idx).unwrap_or_default()));
    bid.zip(ask).and_then(|(bid, ask)| {
        let mid = (bid + ask) / 2.0;
        finite((ask - bid) / mid * 10_000.0)
    })
}

fn merge_map<T, F>(target: &mut BTreeMap<MinuteKey, T>, source: BTreeMap<MinuteKey, T>, merge: F)
where
    F: Fn(&mut T, T),
{
    for (key, value) in source {
        if let Some(existing) = target.get_mut(&key) {
            merge(existing, value);
        } else {
            target.insert(key, value);
        }
    }
}

fn symbol_from_path(path: &Path) -> String {
    for component in path.components() {
        let value = component.as_os_str().to_string_lossy();
        if let Some(symbol) = value.strip_prefix("symbol=") {
            return symbol.to_ascii_uppercase();
        }
    }
    path.file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .replace(".csv", "")
        .to_ascii_uppercase()
}

fn source_date_from_path(path: &Path) -> String {
    for component in path.components() {
        let value = component.as_os_str().to_string_lossy();
        if let Some(dt) = value.strip_prefix("dt=") {
            return dt.to_string();
        }
    }
    String::new()
}

fn base_asset(symbol: &str) -> String {
    let mut value = symbol.to_ascii_uppercase();
    for quote in ["USDC", "USDT", "USD"] {
        if value.ends_with(quote) {
            value.truncate(value.len() - quote.len());
            break;
        }
    }
    if value.ends_with("1M") {
        value.truncate(value.len() - 2);
    }
    value
}

fn price_scale(symbol: &str) -> f64 {
    let mut value = symbol.to_ascii_uppercase();
    for quote in ["USDC", "USDT", "USD"] {
        if value.ends_with(quote) {
            value.truncate(value.len() - quote.len());
            break;
        }
    }
    if value.ends_with("1M") {
        1_000_000.0
    } else {
        1.0
    }
}

fn floor_to_minute_us(timestamp_us: u64) -> u64 {
    timestamp_us / 60_000_000 * 60_000_000
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

fn safe_div(numerator: f64, denominator: f64) -> Option<f64> {
    if denominator == 0.0 || !numerator.is_finite() || !denominator.is_finite() {
        None
    } else {
        finite(numerator / denominator)
    }
}

fn mean(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        finite(values.iter().sum::<f64>() / values.len() as f64)
    }
}

fn mean_from_sum(sum: f64, count: u64) -> Option<f64> {
    if count == 0 {
        None
    } else {
        finite(sum / count as f64)
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

fn max_opt(a: Option<f64>, b: Option<f64>) -> Option<f64> {
    match (a, b) {
        (Some(a), Some(b)) => Some(a.max(b)),
        (Some(a), None) => Some(a),
        (None, Some(b)) => Some(b),
        (None, None) => None,
    }
}

fn min_opt(a: Option<f64>, b: Option<f64>) -> Option<f64> {
    match (a, b) {
        (Some(a), Some(b)) => Some(a.min(b)),
        (Some(a), None) => Some(a),
        (None, Some(b)) => Some(b),
        (None, None) => None,
    }
}

fn rate<'a, I>(values: I, target: &str) -> Option<f64>
where
    I: IntoIterator<Item = &'a str>,
{
    let mut total = 0u64;
    let mut hits = 0u64;
    for value in values {
        total += 1;
        if value == target {
            hits += 1;
        }
    }
    safe_div(hits as f64, total as f64)
}

fn power_largest_eigenvalue(matrix: &[Vec<f64>]) -> f64 {
    let n = matrix.len();
    if n == 0 {
        return 0.0;
    }
    let mut v = vec![1.0 / (n as f64).sqrt(); n];
    for _ in 0..50 {
        let mut next = vec![0.0; n];
        for i in 0..n {
            for j in 0..n {
                next[i] += matrix[i][j] * v[j];
            }
        }
        let norm = next.iter().map(|value| value * value).sum::<f64>().sqrt();
        if norm == 0.0 {
            return 0.0;
        }
        for value in &mut next {
            *value /= norm;
        }
        v = next;
    }
    let mut mv = vec![0.0; n];
    for i in 0..n {
        for j in 0..n {
            mv[i] += matrix[i][j] * v[j];
        }
    }
    v.iter().zip(mv).map(|(a, b)| a * b).sum()
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
            .set_created_by("cex-l2-research".to_string())
            .build();
        let mut writer = ArrowWriter::try_new(file, schema, Some(props))
            .with_context(|| format!("failed to create parquet writer for {}", path.display()))?;
        writer
            .write(&batch)
            .with_context(|| format!("failed to write parquet batch {}", path.display()))?;
        writer
            .close()
            .with_context(|| format!("failed to close parquet writer {}", path.display()))?;
    }
    replace_file(&temp, path)
}

fn write_csv_atomic<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    {
        let mut writer = csv::Writer::from_path(&temp)
            .with_context(|| format!("failed to create {}", temp.display()))?;
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

fn write_text_atomic(path: &Path, text: &str) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    fs::write(&temp, text).with_context(|| format!("failed to write {}", temp.display()))?;
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
    thread::sleep(std::time::Duration::from_millis(millis));
}

fn temp_path_for(path: &Path) -> PathBuf {
    let filename = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("out");
    path.with_file_name(format!(".{filename}.tmp.{}", std::process::id()))
}

fn fingerprint_quality(quality: &[QualityRow]) -> RawReportFingerprint {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    let mut total_bytes = 0u64;
    for row in quality {
        row.path.hash(&mut hasher);
        row.bytes.hash(&mut hasher);
        row.status.hash(&mut hasher);
        total_bytes = total_bytes.saturating_add(row.bytes);
    }
    RawReportFingerprint {
        file_count: quality.len(),
        total_bytes,
        hash: format!("{:016x}", hasher.finish()),
    }
}

fn utc_now_string() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true)
}

fn fmt_num(value: Option<f64>, digits: usize) -> String {
    match value.and_then(finite) {
        Some(value) => format!("{value:.digits$}"),
        None => "n/a".to_string(),
    }
}

fn fmt_pct(value: Option<f64>) -> String {
    match value.and_then(finite) {
        Some(value) => format!("{:.1}%", value * 100.0),
        None => "n/a".to_string(),
    }
}

fn desc_opt_abs(a: Option<f64>, b: Option<f64>) -> std::cmp::Ordering {
    match (a, b) {
        (Some(a), Some(b)) => b.abs().total_cmp(&a.abs()),
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => std::cmp::Ordering::Equal,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_asset_handles_one_m_symbols() {
        assert_eq!(base_asset("BONK1MUSDC"), "BONK");
        assert_eq!(base_asset("BTCUSDC"), "BTC");
    }

    #[test]
    fn qbucket_splits_three_equal_buckets() {
        let values = (0..30).map(|value| Some(value as f64)).collect::<Vec<_>>();
        let buckets = qbucket(&values);
        assert_eq!(
            buckets
                .iter()
                .filter(|value| value.as_deref() == Some("low"))
                .count(),
            10
        );
        assert_eq!(
            buckets
                .iter()
                .filter(|value| value.as_deref() == Some("mid"))
                .count(),
            10
        );
        assert_eq!(
            buckets
                .iter()
                .filter(|value| value.as_deref() == Some("high"))
                .count(),
            10
        );
    }
}

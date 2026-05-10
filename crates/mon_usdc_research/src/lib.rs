use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::AtomicUsize;
use std::thread;
use std::time::UNIX_EPOCH;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{
    Array, ArrayRef, BooleanArray, Float64Array, Float64Builder, StringArray, UInt64Array,
};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, SecondsFormat, Utc};
use finance_chain_core::storage::{
    DERIVED_DIR, RAW_DIR, bool_array, custom_part_path, ensure_parent_dir, f64_array,
    opt_u64_array, parquet_files_under, string_array, u64_array, utc_now_string,
    write_parquet_part, write_schema_metadata,
};
use mon_usdc_collectors::{EVENT_HEADERS_DATASET, POOL_SWAP_LOGS_DATASET, TX_RECEIPTS_DATASET};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::{Deserialize, Serialize};

pub const DEFAULT_DATA_ROOT: &str = "data/mon_usdc/v1";
pub const DEFAULT_RUN_TAG: &str = "20260509";
pub const DEFAULT_PROGRESS_INTERVAL: usize = 1000;

const DERIVED_SCHEMA_VERSION: u32 = 1;
const EVENT_FEATURES_DATASET: &str = "mon_usdc_event_features";
const HOURLY_MARKET_FEATURES_DATASET: &str = "mon_usdc_hourly_market_features";
const MINUTE_PRICE_REFERENCE_DATASET: &str = "mon_usdc_minute_price_reference";
const MANIFEST_DATASET: &str = "_manifests";
const RESEARCH_MANIFEST_FILENAME: &str = "mon_usdc_v1_research_manifest.json";

const HOURLY_HORIZONS: [usize; 5] = [1, 3, 6, 12, 24];
const EVENT_HORIZONS: [(&str, i64); 5] = [
    ("5m", 5 * 60),
    ("15m", 15 * 60),
    ("1h", 60 * 60),
    ("3h", 3 * 60 * 60),
    ("6h", 6 * 60 * 60),
];
const HOURLY_FACTORS: [&str; 9] = [
    "events",
    "quote_volume",
    "log_quote_volume",
    "net_flow_ratio",
    "buy_event_ratio",
    "active_blocks",
    "pools",
    "effective_gas_gwei_mean",
    "receipt_success_rate",
];
const EVENT_FACTORS: [&str; 9] = [
    "is_buy_base",
    "quote_abs",
    "log_quote_abs",
    "base_abs",
    "log_base_abs",
    "gas_used",
    "effective_gas_gwei",
    "same_block_event_count",
    "header_event_log_count",
];

#[derive(Debug, Clone)]
pub struct AnalysisConfig {
    pub data_root: PathBuf,
    pub run_tag: String,
    pub date_dir: PathBuf,
    pub docs_dir: PathBuf,
    pub force_derived: bool,
    pub no_derived_cache: bool,
    pub progress_interval: usize,
}

#[derive(Debug, Serialize)]
pub struct AnalysisSummary {
    pub data_root: String,
    pub run_tag: String,
    pub executable_path: String,
    pub outputs: OutputPaths,
    pub derived_cache: DerivedCacheSummary,
    pub coverage: CoverageSummary,
    pub price_coverage: PriceCoverage,
    pub output_rows: OutputRows,
    pub exclusions: Vec<ExclusionSummaryRow>,
    pub quality_passed: bool,
}

#[derive(Debug, Serialize)]
pub struct OutputPaths {
    pub pool_summary: String,
    pub hourly_market: String,
    pub hourly_factor_tests: String,
    pub event_factor_tests: String,
    pub summary_json: String,
    pub report: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoverageSummary {
    pub raw_swap_rows: u64,
    pub dedup_swap_rows: u64,
    pub clean_swap_rows: u64,
    pub excluded_swaps: u64,
    pub removed_swaps: u64,
    pub duplicate_swaps: u64,
    pub raw_header_rows: u64,
    pub dedup_header_rows: u64,
    pub duplicate_headers: u64,
    pub raw_receipt_rows: u64,
    pub dedup_receipt_rows: u64,
    pub duplicate_receipts: u64,
    pub unique_swap_blocks: u64,
    pub unique_swap_txs: u64,
    pub missing_event_headers: u64,
    pub missing_receipts: u64,
    pub receipt_request_status_errors: u64,
    pub receipt_failure_rows: u64,
    pub clean_start: String,
    pub clean_end: String,
    pub clean_block_min: u64,
    pub clean_block_max: u64,
    pub span_days: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceCoverage {
    pub minute_rows: u64,
    pub minute_observed: u64,
    pub minute_forward_fill: u64,
    pub hourly_rows: u64,
    pub hourly_observed: u64,
    pub hourly_forward_fill: u64,
}

#[derive(Debug, Serialize)]
pub struct OutputRows {
    pub pool_summary: usize,
    pub hourly_market: usize,
    pub hourly_factor_tests: usize,
    pub event_factor_tests: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct DerivedCacheSummary {
    pub schema_version: u32,
    pub status: String,
    pub manifest: String,
    pub raw_fingerprint_hash: String,
    pub raw_file_count: usize,
    pub raw_total_bytes: u64,
    pub event_features_parts: Vec<String>,
    pub hourly_market_features_parts: Vec<String>,
    pub minute_price_reference_parts: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DerivedManifest {
    schema_version: u32,
    generated_at_utc: String,
    raw_inventory: RawInventory,
    event_features: DerivedDatasetManifest,
    hourly_market_features: DerivedDatasetManifest,
    minute_price_reference: DerivedDatasetManifest,
    coverage: CoverageSummary,
    price_coverage: PriceCoverage,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DerivedDatasetManifest {
    dataset: String,
    parts: Vec<String>,
    rows: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RawInventory {
    hash: String,
    file_count: usize,
    total_bytes: u64,
    datasets: Vec<RawDatasetInventory>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RawDatasetInventory {
    dataset: String,
    file_count: usize,
    total_bytes: u64,
    files: Vec<RawFileFingerprint>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RawFileFingerprint {
    relative_path: String,
    bytes: u64,
    modified_unix_nanos: String,
}

#[derive(Debug, Clone)]
struct RawSwap {
    fetched_at_utc: String,
    block_number: u64,
    block_timestamp: u64,
    block_datetime_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    base_symbol: String,
    quote_symbol: String,
    direction: String,
    base_abs: Option<f64>,
    quote_abs: Option<f64>,
    price_quote_per_base: Option<f64>,
    removed: bool,
}

#[derive(Debug, Clone)]
struct RawHeader {
    fetched_at_utc: String,
    block_number: u64,
    block_timestamp: u64,
    block_datetime_utc: String,
    base_fee_per_gas: Option<u64>,
    event_log_count: u64,
}

#[derive(Debug, Clone)]
struct RawReceipt {
    fetched_at_utc: String,
    transaction_hash: String,
    request_status: String,
    transaction_index: Option<u64>,
    receipt_status: Option<u64>,
    gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
}

#[derive(Debug, Clone)]
struct EventRecord {
    block_number: u64,
    timestamp: i64,
    block_datetime_utc: String,
    hour_utc: String,
    minute_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    base_symbol: String,
    quote_symbol: String,
    base_abs: Option<f64>,
    quote_abs: Option<f64>,
    price_quote_per_base: Option<f64>,
    clean_keep: bool,
    clean_exclusion_reason: String,
    is_buy_base: bool,
    is_sell_base: bool,
    buy_base: f64,
    sell_base: f64,
    net_buy_base: f64,
    receipt_request_status: String,
    receipt_status: Option<u64>,
    receipt_gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
    base_fee_per_gas: Option<u64>,
    header_event_log_count: Option<u64>,
    same_block_event_count: u64,
}

#[derive(Default)]
struct BlockEventCount {
    events: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExclusionSummaryRow {
    pub reason: String,
    pub rows: u64,
}

#[derive(Debug, Serialize)]
struct PoolSummaryRow {
    dex_id: String,
    family: String,
    pool_address: String,
    base_symbol: String,
    quote_symbol: String,
    raw_events: u64,
    clean_events: u64,
    excluded_events: u64,
    unique_txs: u64,
    active_blocks: u64,
    buy_events: u64,
    sell_events: u64,
    buy_base: f64,
    sell_base: f64,
    net_buy_base: f64,
    base_volume: f64,
    quote_volume: f64,
    median_price_quote_per_base: Option<f64>,
    first_seen: String,
    last_seen: String,
    receipt_success_rate: Option<f64>,
    gas_used_mean: Option<f64>,
    effective_gas_gwei_mean: Option<f64>,
    quote_volume_share: Option<f64>,
    base_volume_share: Option<f64>,
    net_flow_ratio: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct HourlyMarketRow {
    hour_utc: String,
    events: u64,
    unique_txs: u64,
    pools: u64,
    dexes: u64,
    active_blocks: u64,
    buy_events: u64,
    sell_events: u64,
    buy_base: f64,
    sell_base: f64,
    net_buy_base: f64,
    base_volume: f64,
    quote_volume: f64,
    gas_used_mean: Option<f64>,
    effective_gas_gwei_mean: Option<f64>,
    base_fee_gwei_mean: Option<f64>,
    receipt_success_rate: Option<f64>,
    same_block_event_count_mean: Option<f64>,
    same_block_event_count_max: Option<f64>,
    vwap_quote_per_base_observed: Option<f64>,
    price_quote_per_base: Option<f64>,
    price_fill_method: String,
    buy_event_ratio: f64,
    net_flow_ratio: f64,
    log_quote_volume: f64,
    log_events: f64,
    return_1h: Option<f64>,
    fwd_1h: Option<f64>,
    fwd_3h: Option<f64>,
    fwd_6h: Option<f64>,
    fwd_12h: Option<f64>,
    fwd_24h: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorTestRow {
    factor: String,
    factor_type: String,
    target: String,
    n: u64,
    factor_non_null: u64,
    pearson: Option<f64>,
    spearman: Option<f64>,
    low_bucket: i64,
    high_bucket: i64,
    low_mean: Option<f64>,
    high_mean: Option<f64>,
    high_minus_low: Option<f64>,
    low_positive_rate: Option<f64>,
    high_positive_rate: Option<f64>,
}

#[derive(Default)]
struct MeanStat {
    sum: f64,
    count: u64,
}

impl MeanStat {
    fn add(&mut self, value: Option<f64>) {
        if let Some(value) = value.filter(|value| value.is_finite()) {
            self.sum += value;
            self.count += 1;
        }
    }

    fn mean(&self) -> Option<f64> {
        if self.count == 0 {
            None
        } else {
            finite(self.sum / self.count as f64)
        }
    }
}

#[derive(Default)]
struct PoolAgg {
    dex_id: String,
    family: String,
    pool_address: String,
    base_symbol: String,
    quote_symbol: String,
    raw_events: u64,
    clean_events: u64,
    excluded_events: u64,
    unique_txs: BTreeSet<String>,
    active_blocks: BTreeSet<u64>,
    buy_events: u64,
    sell_events: u64,
    buy_base: f64,
    sell_base: f64,
    net_buy_base: f64,
    base_volume: f64,
    quote_volume: f64,
    prices: Vec<f64>,
    first_seen: Option<String>,
    last_seen: Option<String>,
    receipt_success: MeanStat,
    gas_used: MeanStat,
    effective_gas_gwei: MeanStat,
}

#[derive(Default)]
struct HourAgg {
    events: u64,
    unique_txs: BTreeSet<String>,
    pools: BTreeSet<String>,
    dexes: BTreeSet<String>,
    active_blocks: BTreeSet<u64>,
    buy_events: u64,
    sell_events: u64,
    buy_base: f64,
    sell_base: f64,
    net_buy_base: f64,
    base_volume: f64,
    quote_volume: f64,
    gas_used: MeanStat,
    effective_gas_gwei: MeanStat,
    base_fee_gwei: MeanStat,
    receipt_success: MeanStat,
    same_block_event_count: MeanStat,
    same_block_event_count_max: u64,
}

#[derive(Default, Clone)]
struct MinuteAgg {
    base_volume: f64,
    quote_volume: f64,
    events: u64,
}

#[derive(Debug, Clone)]
struct MinutePricePoint {
    vwap_observed: Option<f64>,
    price: Option<f64>,
    price_fill_method: String,
}

#[derive(Debug, Clone)]
struct MinutePriceRow {
    minute_timestamp: i64,
    minute_utc: String,
    events: u64,
    base_volume: f64,
    quote_volume: f64,
    vwap_observed: Option<f64>,
    price: Option<f64>,
    price_fill_method: String,
}

#[derive(Debug, Clone)]
struct MinutePriceSeries {
    start_minute: i64,
    rows: Vec<MinutePricePoint>,
}

struct DerivedData {
    event_panel: Vec<EventRecord>,
    clean_events: Vec<EventRecord>,
    hourly_market: Vec<HourlyMarketRow>,
    minute_prices: MinutePriceSeries,
    coverage: CoverageSummary,
    price_coverage: PriceCoverage,
    cache_summary: DerivedCacheSummary,
}

#[derive(Clone)]
struct ReadProgress {
    label: Arc<String>,
    total: usize,
    interval: usize,
    completed: Arc<AtomicUsize>,
}

impl ReadProgress {
    fn new(label: &str, total: usize, interval: usize) -> Self {
        Self {
            label: Arc::new(label.to_string()),
            total,
            interval,
            completed: Arc::new(AtomicUsize::new(0)),
        }
    }

    fn tick(&self) {
        let completed = self
            .completed
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed)
            + 1;
        if self.interval > 0 && (completed == self.total || completed % self.interval == 0) {
            eprintln!(
                "[mon_usdc_factor_analysis] {}: {}/{} parquet files",
                self.label, completed, self.total
            );
        }
    }
}

impl MinutePriceSeries {
    fn price_at(&self, minute_ts: i64) -> Option<f64> {
        if minute_ts < self.start_minute {
            return None;
        }
        let index = ((minute_ts - self.start_minute) / 60) as usize;
        self.rows.get(index).and_then(|row| row.price)
    }
}

pub fn run_analysis(config: &AnalysisConfig) -> Result<AnalysisSummary> {
    let outputs = build_output_paths(config);
    std::fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    std::fs::create_dir_all(&config.docs_dir)
        .with_context(|| format!("failed to create {}", config.docs_dir.display()))?;

    log_stage("scan raw file inventory");
    let raw_inventory = scan_raw_inventory(&config.data_root, config.progress_interval)?;
    let derived = load_or_build_derived(config, raw_inventory)?;

    let exclusions = build_exclusion_summary(&derived.event_panel);
    let pool_summary = build_pool_summary(&derived.event_panel);

    log_stage("build hourly panel");
    let hourly_tests = build_hourly_factor_tests(&derived.hourly_market);
    log_stage("build event targets");
    let event_tests = build_event_factor_tests(&derived.clean_events, &derived.minute_prices);

    if pool_summary.is_empty() || derived.hourly_market.is_empty() {
        bail!("analysis produced empty pool/hourly outputs");
    }
    if hourly_tests.is_empty() {
        bail!("analysis produced no hourly factor tests");
    }
    if event_tests.is_empty() {
        bail!("analysis produced no event factor tests");
    }

    write_csv(Path::new(&outputs.pool_summary), &pool_summary)?;
    write_csv(Path::new(&outputs.hourly_market), &derived.hourly_market)?;
    write_csv(Path::new(&outputs.hourly_factor_tests), &hourly_tests)?;
    write_csv(Path::new(&outputs.event_factor_tests), &event_tests)?;

    let coverage = derived.coverage;
    let quality_passed = coverage.missing_event_headers == 0
        && coverage.missing_receipts == 0
        && coverage.receipt_request_status_errors == 0;
    let output_rows = OutputRows {
        pool_summary: pool_summary.len(),
        hourly_market: derived.hourly_market.len(),
        hourly_factor_tests: hourly_tests.len(),
        event_factor_tests: event_tests.len(),
    };

    assert_no_inf(Path::new(&outputs.pool_summary))?;
    assert_no_inf(Path::new(&outputs.hourly_market))?;
    assert_no_inf(Path::new(&outputs.hourly_factor_tests))?;
    assert_no_inf(Path::new(&outputs.event_factor_tests))?;

    let summary = AnalysisSummary {
        data_root: path_string(&config.data_root),
        run_tag: config.run_tag.clone(),
        executable_path: current_executable_path(),
        outputs,
        derived_cache: derived.cache_summary,
        coverage,
        price_coverage: derived.price_coverage,
        output_rows,
        exclusions,
        quality_passed,
    };
    write_json(Path::new(&summary.outputs.summary_json), &summary)?;
    Ok(summary)
}

fn build_output_paths(config: &AnalysisConfig) -> OutputPaths {
    OutputPaths {
        pool_summary: path_string(
            &config
                .date_dir
                .join(format!("mon_usdc_v1_pool_summary_{}.csv", config.run_tag)),
        ),
        hourly_market: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_hourly_market_features_{}.csv",
            config.run_tag
        ))),
        hourly_factor_tests: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_hourly_factor_tests_{}.csv",
            config.run_tag
        ))),
        event_factor_tests: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_event_factor_tests_{}.csv",
            config.run_tag
        ))),
        summary_json: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_factor_analysis_summary_{}.json",
            config.run_tag
        ))),
        report: path_string(
            &config
                .docs_dir
                .join(format!("mon_usdc_v1_factor_analysis_{}.md", config.run_tag)),
        ),
    }
}

fn load_or_build_derived(
    config: &AnalysisConfig,
    raw_inventory: RawInventory,
) -> Result<DerivedData> {
    let manifest_path = research_manifest_path(&config.data_root);
    if config.no_derived_cache {
        eprintln!("[mon_usdc_factor_analysis] manifest cache disabled by --no-derived-cache");
        return build_derived_from_raw(config, raw_inventory, None, "disabled_rebuilt_from_raw");
    }

    if config.force_derived {
        eprintln!("[mon_usdc_factor_analysis] manifest cache ignored by --force-derived");
        return build_derived_from_raw(
            config,
            raw_inventory,
            Some(&manifest_path),
            "forced_rebuilt",
        );
    }

    if let Some(manifest) = load_valid_manifest(&config.data_root, &manifest_path, &raw_inventory)?
    {
        eprintln!(
            "[mon_usdc_factor_analysis] manifest cache hit: {}",
            manifest_path.display()
        );
        log_stage("read derived parquet");
        return read_derived_from_manifest(&config.data_root, raw_inventory, manifest, "hit");
    }

    build_derived_from_raw(config, raw_inventory, Some(&manifest_path), "rebuilt")
}

fn build_derived_from_raw(
    config: &AnalysisConfig,
    raw_inventory: RawInventory,
    manifest_path: Option<&Path>,
    cache_status: &str,
) -> Result<DerivedData> {
    log_stage("read pool_swap_logs");
    let raw_swaps = read_swaps(&config.data_root, config.progress_interval)?;
    log_stage("read event_block_headers");
    let raw_headers = read_headers(&config.data_root, config.progress_interval)?;
    log_stage("read tx_receipts");
    let raw_receipts = read_receipts(&config.data_root, config.progress_interval)?;
    if raw_swaps.is_empty() {
        bail!(
            "no raw swap rows found under {}",
            config
                .data_root
                .join(RAW_DIR)
                .join(POOL_SWAP_LOGS_DATASET)
                .display()
        );
    }

    log_stage("dedup/join event features");
    let (swaps, duplicate_swaps) = dedup_by_latest(
        raw_swaps,
        |row| {
            (
                row.pool_address.clone(),
                row.transaction_hash.clone(),
                row.log_index,
            )
        },
        |row| &row.fetched_at_utc,
    );
    let (headers, duplicate_headers) = dedup_by_latest(
        raw_headers,
        |row| row.block_number,
        |row| &row.fetched_at_utc,
    );
    let (receipts, duplicate_receipts) = dedup_by_latest(
        raw_receipts,
        |row| row.transaction_hash.clone(),
        |row| &row.fetched_at_utc,
    );

    let headers_by_block = headers
        .iter()
        .map(|row| (row.block_number, row.clone()))
        .collect::<HashMap<_, _>>();
    let receipts_by_hash = receipts
        .iter()
        .map(|row| (row.transaction_hash.clone(), row.clone()))
        .collect::<HashMap<_, _>>();

    let event_panel = build_event_panel(&swaps, &headers_by_block, &receipts_by_hash)?;
    let clean_events = clean_events(&event_panel)?;
    let coverage = build_coverage(
        raw_swaps_len(&event_panel, duplicate_swaps),
        &swaps,
        &headers,
        &receipts,
        duplicate_swaps,
        duplicate_headers,
        duplicate_receipts,
        &event_panel,
    )?;
    log_stage("build hourly panel");
    let hourly_market = build_hourly_market(&clean_events)?;
    log_stage("build minute price reference");
    let minute_price_rows = build_minute_price_rows(&clean_events)?;
    let minute_prices = minute_series_from_rows(&minute_price_rows)?;
    let price_coverage = build_price_coverage(&minute_prices, &hourly_market);

    if let Some(manifest_path) = manifest_path {
        log_stage("write derived parquet");
        let manifest = write_derived_cache(
            &config.data_root,
            raw_inventory,
            &event_panel,
            &hourly_market,
            &minute_price_rows,
            coverage,
            price_coverage,
            manifest_path,
        )?;
        log_stage("read derived parquet");
        read_derived_from_manifest(
            &config.data_root,
            manifest.raw_inventory.clone(),
            manifest,
            cache_status,
        )
    } else {
        Ok(DerivedData {
            event_panel,
            clean_events,
            hourly_market,
            minute_prices,
            coverage,
            price_coverage,
            cache_summary: cache_summary_without_manifest(raw_inventory, cache_status),
        })
    }
}

fn read_derived_from_manifest(
    data_root: &Path,
    raw_inventory: RawInventory,
    manifest: DerivedManifest,
    status: &str,
) -> Result<DerivedData> {
    let event_panel = read_event_feature_parts(data_root, &manifest.event_features.parts)?;
    if event_panel.len() != manifest.event_features.rows {
        bail!(
            "derived event_features row count mismatch: manifest={} read={}",
            manifest.event_features.rows,
            event_panel.len()
        );
    }
    let clean_events = clean_events(&event_panel)?;
    let hourly_market =
        read_hourly_market_parts(data_root, &manifest.hourly_market_features.parts)?;
    if hourly_market.len() != manifest.hourly_market_features.rows {
        bail!(
            "derived hourly_market_features row count mismatch: manifest={} read={}",
            manifest.hourly_market_features.rows,
            hourly_market.len()
        );
    }
    let minute_price_rows =
        read_minute_price_reference_parts(data_root, &manifest.minute_price_reference.parts)?;
    if minute_price_rows.len() != manifest.minute_price_reference.rows {
        bail!(
            "derived minute_price_reference row count mismatch: manifest={} read={}",
            manifest.minute_price_reference.rows,
            minute_price_rows.len()
        );
    }
    let minute_prices = minute_series_from_rows(&minute_price_rows)?;

    Ok(DerivedData {
        event_panel,
        clean_events,
        hourly_market,
        minute_prices,
        coverage: manifest.coverage.clone(),
        price_coverage: manifest.price_coverage.clone(),
        cache_summary: cache_summary_from_manifest(data_root, &raw_inventory, &manifest, status),
    })
}

fn clean_events(event_panel: &[EventRecord]) -> Result<Vec<EventRecord>> {
    let clean_events = event_panel
        .iter()
        .filter(|row| row.clean_keep)
        .cloned()
        .collect::<Vec<_>>();
    if clean_events.is_empty() {
        bail!("no clean MON/USDC swap rows after dust/invalid filtering");
    }
    Ok(clean_events)
}

fn read_swaps(data_root: &Path, progress_interval: usize) -> Result<Vec<RawSwap>> {
    read_parallel(
        dataset_files(data_root, POOL_SWAP_LOGS_DATASET)?,
        "read pool_swap_logs",
        progress_interval,
        read_swap_files,
    )
}

fn read_swap_files(files: &[PathBuf]) -> Result<Vec<RawSwap>> {
    let mut rows = Vec::new();
    read_files(files, |batch| {
        let fetched_at_utc = string_column(batch, "fetched_at_utc")?;
        let block_number = u64_column(batch, "block_number")?;
        let block_timestamp = u64_column(batch, "block_timestamp")?;
        let block_datetime_utc = string_column(batch, "block_datetime_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let transaction_index = u64_column(batch, "transaction_index")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let dex_id = string_column(batch, "dex_id")?;
        let family = string_column(batch, "family")?;
        let base_symbol = string_column(batch, "base_symbol")?;
        let quote_symbol = string_column(batch, "quote_symbol")?;
        let direction = string_column(batch, "direction")?;
        let base_abs = string_column(batch, "base_abs")?;
        let quote_abs = string_column(batch, "quote_abs")?;
        let price_quote_per_base = string_column(batch, "price_quote_per_base")?;
        let removed = bool_column(batch, "removed")?;
        for index in 0..batch.num_rows() {
            rows.push(RawSwap {
                fetched_at_utc: string_value(fetched_at_utc, index),
                block_number: u64_value(block_number, index),
                block_timestamp: u64_value(block_timestamp, index),
                block_datetime_utc: string_value(block_datetime_utc, index),
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                transaction_index: u64_value(transaction_index, index),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index).to_ascii_lowercase(),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                base_symbol: string_value(base_symbol, index),
                quote_symbol: string_value(quote_symbol, index),
                direction: string_value(direction, index),
                base_abs: parse_f64_string(base_abs, index),
                quote_abs: parse_f64_string(quote_abs, index),
                price_quote_per_base: parse_f64_string(price_quote_per_base, index),
                removed: bool_value(removed, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_headers(data_root: &Path, progress_interval: usize) -> Result<Vec<RawHeader>> {
    read_parallel(
        dataset_files(data_root, EVENT_HEADERS_DATASET)?,
        "read event_block_headers",
        progress_interval,
        read_header_files,
    )
}

fn read_header_files(files: &[PathBuf]) -> Result<Vec<RawHeader>> {
    let mut rows = Vec::new();
    read_files(files, |batch| {
        let fetched_at_utc = string_column(batch, "fetched_at_utc")?;
        let block_number = u64_column(batch, "block_number")?;
        let block_timestamp = u64_column(batch, "block_timestamp")?;
        let block_datetime_utc = string_column(batch, "block_datetime_utc")?;
        let base_fee_per_gas = u64_column(batch, "base_fee_per_gas")?;
        let event_log_count = u64_column(batch, "event_log_count")?;
        for index in 0..batch.num_rows() {
            rows.push(RawHeader {
                fetched_at_utc: string_value(fetched_at_utc, index),
                block_number: u64_value(block_number, index),
                block_timestamp: u64_value(block_timestamp, index),
                block_datetime_utc: string_value(block_datetime_utc, index),
                base_fee_per_gas: u64_option(base_fee_per_gas, index),
                event_log_count: u64_value(event_log_count, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_receipts(data_root: &Path, progress_interval: usize) -> Result<Vec<RawReceipt>> {
    read_parallel(
        dataset_files(data_root, TX_RECEIPTS_DATASET)?,
        "read tx_receipts",
        progress_interval,
        read_receipt_files,
    )
}

fn read_receipt_files(files: &[PathBuf]) -> Result<Vec<RawReceipt>> {
    let mut rows = Vec::new();
    read_files(files, |batch| {
        let fetched_at_utc = string_column(batch, "fetched_at_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let request_status = string_column(batch, "request_status")?;
        let transaction_index = u64_column(batch, "transaction_index")?;
        let receipt_status = u64_column(batch, "receipt_status")?;
        let gas_used = u64_column(batch, "gas_used")?;
        let effective_gas_price = u64_column(batch, "effective_gas_price")?;
        for index in 0..batch.num_rows() {
            rows.push(RawReceipt {
                fetched_at_utc: string_value(fetched_at_utc, index),
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                request_status: string_value(request_status, index),
                transaction_index: u64_option(transaction_index, index),
                receipt_status: u64_option(receipt_status, index),
                gas_used: u64_option(gas_used, index),
                effective_gas_price: u64_option(effective_gas_price, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn write_derived_cache(
    data_root: &Path,
    raw_inventory: RawInventory,
    event_panel: &[EventRecord],
    hourly_market: &[HourlyMarketRow],
    minute_price_rows: &[MinutePriceRow],
    coverage: CoverageSummary,
    price_coverage: PriceCoverage,
    manifest_path: &Path,
) -> Result<DerivedManifest> {
    let generated_at_utc = utc_now_string();
    let build_id = format!(
        "v{}_{}_{}_{}",
        DERIVED_SCHEMA_VERSION,
        raw_inventory.hash,
        Utc::now().timestamp_micros(),
        std::process::id()
    );

    let event_schema = event_features_schema();
    write_schema_metadata(
        data_root,
        EVENT_FEATURES_DATASET,
        event_schema.as_ref(),
        &["dt"],
    )?;
    let event_batch = event_features_batch(event_schema.clone(), event_panel)?;
    let event_path = custom_part_path(
        data_root,
        DERIVED_DIR,
        EVENT_FEATURES_DATASET,
        "all",
        &format!("{}_{}", EVENT_FEATURES_DATASET, build_id),
    );
    write_parquet_part(&event_path, event_schema, event_batch)?;

    let hourly_schema = hourly_market_schema();
    write_schema_metadata(
        data_root,
        HOURLY_MARKET_FEATURES_DATASET,
        hourly_schema.as_ref(),
        &["dt"],
    )?;
    let hourly_batch = hourly_market_batch(hourly_schema.clone(), hourly_market)?;
    let hourly_path = custom_part_path(
        data_root,
        DERIVED_DIR,
        HOURLY_MARKET_FEATURES_DATASET,
        "all",
        &format!("{}_{}", HOURLY_MARKET_FEATURES_DATASET, build_id),
    );
    write_parquet_part(&hourly_path, hourly_schema, hourly_batch)?;

    let minute_schema = minute_price_reference_schema();
    write_schema_metadata(
        data_root,
        MINUTE_PRICE_REFERENCE_DATASET,
        minute_schema.as_ref(),
        &["dt"],
    )?;
    let minute_batch = minute_price_reference_batch(minute_schema.clone(), minute_price_rows)?;
    let minute_path = custom_part_path(
        data_root,
        DERIVED_DIR,
        MINUTE_PRICE_REFERENCE_DATASET,
        "all",
        &format!("{}_{}", MINUTE_PRICE_REFERENCE_DATASET, build_id),
    );
    write_parquet_part(&minute_path, minute_schema, minute_batch)?;

    let manifest = DerivedManifest {
        schema_version: DERIVED_SCHEMA_VERSION,
        generated_at_utc,
        raw_inventory,
        event_features: DerivedDatasetManifest {
            dataset: EVENT_FEATURES_DATASET.to_string(),
            parts: vec![relative_path_string(data_root, &event_path)],
            rows: event_panel.len(),
        },
        hourly_market_features: DerivedDatasetManifest {
            dataset: HOURLY_MARKET_FEATURES_DATASET.to_string(),
            parts: vec![relative_path_string(data_root, &hourly_path)],
            rows: hourly_market.len(),
        },
        minute_price_reference: DerivedDatasetManifest {
            dataset: MINUTE_PRICE_REFERENCE_DATASET.to_string(),
            parts: vec![relative_path_string(data_root, &minute_path)],
            rows: minute_price_rows.len(),
        },
        coverage,
        price_coverage,
    };
    ensure_parent_dir(manifest_path)?;
    let file = File::create(manifest_path)
        .with_context(|| format!("failed to create {}", manifest_path.display()))?;
    serde_json::to_writer_pretty(file, &manifest)
        .with_context(|| format!("failed to write {}", manifest_path.display()))?;
    Ok(manifest)
}

fn event_features_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("block_number", DataType::UInt64, false),
        Field::new("block_timestamp", DataType::UInt64, false),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("hour_utc", DataType::Utf8, false),
        Field::new("minute_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("base_symbol", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("base_abs", DataType::Float64, true),
        Field::new("quote_abs", DataType::Float64, true),
        Field::new("price_quote_per_base", DataType::Float64, true),
        Field::new("clean_keep", DataType::Boolean, false),
        Field::new("clean_exclusion_reason", DataType::Utf8, false),
        Field::new("is_buy_base", DataType::Boolean, false),
        Field::new("is_sell_base", DataType::Boolean, false),
        Field::new("buy_base", DataType::Float64, false),
        Field::new("sell_base", DataType::Float64, false),
        Field::new("net_buy_base", DataType::Float64, false),
        Field::new("receipt_request_status", DataType::Utf8, false),
        Field::new("receipt_status", DataType::UInt64, true),
        Field::new("receipt_gas_used", DataType::UInt64, true),
        Field::new("effective_gas_price", DataType::UInt64, true),
        Field::new("base_fee_per_gas", DataType::UInt64, true),
        Field::new("header_event_log_count", DataType::UInt64, true),
        Field::new("same_block_event_count", DataType::UInt64, false),
    ]))
}

fn hourly_market_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("hour_utc", DataType::Utf8, false),
        Field::new("events", DataType::UInt64, false),
        Field::new("unique_txs", DataType::UInt64, false),
        Field::new("pools", DataType::UInt64, false),
        Field::new("dexes", DataType::UInt64, false),
        Field::new("active_blocks", DataType::UInt64, false),
        Field::new("buy_events", DataType::UInt64, false),
        Field::new("sell_events", DataType::UInt64, false),
        Field::new("buy_base", DataType::Float64, false),
        Field::new("sell_base", DataType::Float64, false),
        Field::new("net_buy_base", DataType::Float64, false),
        Field::new("base_volume", DataType::Float64, false),
        Field::new("quote_volume", DataType::Float64, false),
        Field::new("gas_used_mean", DataType::Float64, true),
        Field::new("effective_gas_gwei_mean", DataType::Float64, true),
        Field::new("base_fee_gwei_mean", DataType::Float64, true),
        Field::new("receipt_success_rate", DataType::Float64, true),
        Field::new("same_block_event_count_mean", DataType::Float64, true),
        Field::new("same_block_event_count_max", DataType::Float64, true),
        Field::new("vwap_quote_per_base_observed", DataType::Float64, true),
        Field::new("price_quote_per_base", DataType::Float64, true),
        Field::new("price_fill_method", DataType::Utf8, false),
        Field::new("buy_event_ratio", DataType::Float64, false),
        Field::new("net_flow_ratio", DataType::Float64, false),
        Field::new("log_quote_volume", DataType::Float64, false),
        Field::new("log_events", DataType::Float64, false),
        Field::new("return_1h", DataType::Float64, true),
        Field::new("fwd_1h", DataType::Float64, true),
        Field::new("fwd_3h", DataType::Float64, true),
        Field::new("fwd_6h", DataType::Float64, true),
        Field::new("fwd_12h", DataType::Float64, true),
        Field::new("fwd_24h", DataType::Float64, true),
    ]))
}

fn minute_price_reference_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("minute_timestamp", DataType::UInt64, false),
        Field::new("minute_utc", DataType::Utf8, false),
        Field::new("events", DataType::UInt64, false),
        Field::new("base_volume", DataType::Float64, false),
        Field::new("quote_volume", DataType::Float64, false),
        Field::new("vwap_observed", DataType::Float64, true),
        Field::new("price_quote_per_base", DataType::Float64, true),
        Field::new("price_fill_method", DataType::Utf8, false),
    ]))
}

fn event_features_batch(schema: SchemaRef, rows: &[EventRecord]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.timestamp.max(0) as u64)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.block_datetime_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.hour_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.minute_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_index)
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.log_index).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.dex_id.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.family.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.base_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quote_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.base_abs).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.quote_abs).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_quote_per_base)
                    .collect::<Vec<_>>(),
            ),
            bool_array(&rows.iter().map(|row| row.clean_keep).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.clean_exclusion_reason.clone())
                    .collect::<Vec<_>>(),
            ),
            bool_array(&rows.iter().map(|row| row.is_buy_base).collect::<Vec<_>>()),
            bool_array(&rows.iter().map(|row| row.is_sell_base).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.buy_base).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.sell_base).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.net_buy_base).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_status)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_gas_used)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.effective_gas_price)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.base_fee_per_gas)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.header_event_log_count)
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.same_block_event_count)
                    .collect::<Vec<_>>(),
            ),
        ],
    )
    .context("failed to build derived event features record batch")
}

fn hourly_market_batch(schema: SchemaRef, rows: &[HourlyMarketRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.hour_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.events).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.unique_txs).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.pools).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.dexes).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.active_blocks).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.buy_events).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.sell_events).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.buy_base).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.sell_base).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.net_buy_base).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.base_volume).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.quote_volume).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.gas_used_mean).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.effective_gas_gwei_mean)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.base_fee_gwei_mean)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_success_rate)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.same_block_event_count_mean)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.same_block_event_count_max)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.vwap_quote_per_base_observed)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_quote_per_base)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.price_fill_method.clone())
                    .collect::<Vec<_>>(),
            ),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.buy_event_ratio)
                    .collect::<Vec<_>>(),
            ),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.net_flow_ratio)
                    .collect::<Vec<_>>(),
            ),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.log_quote_volume)
                    .collect::<Vec<_>>(),
            ),
            f64_array(&rows.iter().map(|row| row.log_events).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.return_1h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_1h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_3h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_6h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_12h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_24h).collect::<Vec<_>>()),
        ],
    )
    .context("failed to build derived hourly market record batch")
}

fn minute_price_reference_batch(schema: SchemaRef, rows: &[MinutePriceRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.minute_timestamp.max(0) as u64)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.minute_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.events).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.base_volume).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.quote_volume).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.vwap_observed).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.price).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.price_fill_method.clone())
                    .collect::<Vec<_>>(),
            ),
        ],
    )
    .context("failed to build derived minute price reference record batch")
}

fn read_event_feature_parts(data_root: &Path, parts: &[String]) -> Result<Vec<EventRecord>> {
    let files = resolve_manifest_parts(data_root, parts);
    let mut rows = Vec::new();
    read_files(&files, |batch| {
        let block_number = u64_column(batch, "block_number")?;
        let block_timestamp = u64_column(batch, "block_timestamp")?;
        let block_datetime_utc = string_column(batch, "block_datetime_utc")?;
        let hour_utc = string_column(batch, "hour_utc")?;
        let minute_utc = string_column(batch, "minute_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let transaction_index = u64_column(batch, "transaction_index")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let dex_id = string_column(batch, "dex_id")?;
        let family = string_column(batch, "family")?;
        let base_symbol = string_column(batch, "base_symbol")?;
        let quote_symbol = string_column(batch, "quote_symbol")?;
        let base_abs = f64_column(batch, "base_abs")?;
        let quote_abs = f64_column(batch, "quote_abs")?;
        let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
        let clean_keep = bool_column(batch, "clean_keep")?;
        let clean_exclusion_reason = string_column(batch, "clean_exclusion_reason")?;
        let is_buy_base = bool_column(batch, "is_buy_base")?;
        let is_sell_base = bool_column(batch, "is_sell_base")?;
        let buy_base = f64_column(batch, "buy_base")?;
        let sell_base = f64_column(batch, "sell_base")?;
        let net_buy_base = f64_column(batch, "net_buy_base")?;
        let receipt_request_status = string_column(batch, "receipt_request_status")?;
        let receipt_status = u64_column(batch, "receipt_status")?;
        let receipt_gas_used = u64_column(batch, "receipt_gas_used")?;
        let effective_gas_price = u64_column(batch, "effective_gas_price")?;
        let base_fee_per_gas = u64_column(batch, "base_fee_per_gas")?;
        let header_event_log_count = u64_column(batch, "header_event_log_count")?;
        let same_block_event_count = u64_column(batch, "same_block_event_count")?;
        for index in 0..batch.num_rows() {
            rows.push(EventRecord {
                block_number: u64_value(block_number, index),
                timestamp: u64_value(block_timestamp, index) as i64,
                block_datetime_utc: string_value(block_datetime_utc, index),
                hour_utc: string_value(hour_utc, index),
                minute_utc: string_value(minute_utc, index),
                transaction_hash: string_value(transaction_hash, index),
                transaction_index: u64_value(transaction_index, index),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                base_symbol: string_value(base_symbol, index),
                quote_symbol: string_value(quote_symbol, index),
                base_abs: f64_option(base_abs, index),
                quote_abs: f64_option(quote_abs, index),
                price_quote_per_base: f64_option(price_quote_per_base, index),
                clean_keep: bool_value(clean_keep, index),
                clean_exclusion_reason: string_value(clean_exclusion_reason, index),
                is_buy_base: bool_value(is_buy_base, index),
                is_sell_base: bool_value(is_sell_base, index),
                buy_base: f64_value(buy_base, index),
                sell_base: f64_value(sell_base, index),
                net_buy_base: f64_value(net_buy_base, index),
                receipt_request_status: string_value(receipt_request_status, index),
                receipt_status: u64_option(receipt_status, index),
                receipt_gas_used: u64_option(receipt_gas_used, index),
                effective_gas_price: u64_option(effective_gas_price, index),
                base_fee_per_gas: u64_option(base_fee_per_gas, index),
                header_event_log_count: u64_option(header_event_log_count, index),
                same_block_event_count: u64_value(same_block_event_count, index),
            });
        }
        Ok(())
    })?;
    rows.sort_by_key(|row| {
        (
            row.timestamp,
            row.block_number,
            row.transaction_index,
            row.log_index,
            row.pool_address.clone(),
        )
    });
    Ok(rows)
}

fn read_hourly_market_parts(data_root: &Path, parts: &[String]) -> Result<Vec<HourlyMarketRow>> {
    let files = resolve_manifest_parts(data_root, parts);
    let mut rows = Vec::new();
    read_files(&files, |batch| {
        let hour_utc = string_column(batch, "hour_utc")?;
        let events = u64_column(batch, "events")?;
        let unique_txs = u64_column(batch, "unique_txs")?;
        let pools = u64_column(batch, "pools")?;
        let dexes = u64_column(batch, "dexes")?;
        let active_blocks = u64_column(batch, "active_blocks")?;
        let buy_events = u64_column(batch, "buy_events")?;
        let sell_events = u64_column(batch, "sell_events")?;
        let buy_base = f64_column(batch, "buy_base")?;
        let sell_base = f64_column(batch, "sell_base")?;
        let net_buy_base = f64_column(batch, "net_buy_base")?;
        let base_volume = f64_column(batch, "base_volume")?;
        let quote_volume = f64_column(batch, "quote_volume")?;
        let gas_used_mean = f64_column(batch, "gas_used_mean")?;
        let effective_gas_gwei_mean = f64_column(batch, "effective_gas_gwei_mean")?;
        let base_fee_gwei_mean = f64_column(batch, "base_fee_gwei_mean")?;
        let receipt_success_rate = f64_column(batch, "receipt_success_rate")?;
        let same_block_event_count_mean = f64_column(batch, "same_block_event_count_mean")?;
        let same_block_event_count_max = f64_column(batch, "same_block_event_count_max")?;
        let vwap_quote_per_base_observed = f64_column(batch, "vwap_quote_per_base_observed")?;
        let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
        let price_fill_method = string_column(batch, "price_fill_method")?;
        let buy_event_ratio = f64_column(batch, "buy_event_ratio")?;
        let net_flow_ratio = f64_column(batch, "net_flow_ratio")?;
        let log_quote_volume = f64_column(batch, "log_quote_volume")?;
        let log_events = f64_column(batch, "log_events")?;
        let return_1h = f64_column(batch, "return_1h")?;
        let fwd_1h = f64_column(batch, "fwd_1h")?;
        let fwd_3h = f64_column(batch, "fwd_3h")?;
        let fwd_6h = f64_column(batch, "fwd_6h")?;
        let fwd_12h = f64_column(batch, "fwd_12h")?;
        let fwd_24h = f64_column(batch, "fwd_24h")?;
        for index in 0..batch.num_rows() {
            rows.push(HourlyMarketRow {
                hour_utc: string_value(hour_utc, index),
                events: u64_value(events, index),
                unique_txs: u64_value(unique_txs, index),
                pools: u64_value(pools, index),
                dexes: u64_value(dexes, index),
                active_blocks: u64_value(active_blocks, index),
                buy_events: u64_value(buy_events, index),
                sell_events: u64_value(sell_events, index),
                buy_base: f64_value(buy_base, index),
                sell_base: f64_value(sell_base, index),
                net_buy_base: f64_value(net_buy_base, index),
                base_volume: f64_value(base_volume, index),
                quote_volume: f64_value(quote_volume, index),
                gas_used_mean: f64_option(gas_used_mean, index),
                effective_gas_gwei_mean: f64_option(effective_gas_gwei_mean, index),
                base_fee_gwei_mean: f64_option(base_fee_gwei_mean, index),
                receipt_success_rate: f64_option(receipt_success_rate, index),
                same_block_event_count_mean: f64_option(same_block_event_count_mean, index),
                same_block_event_count_max: f64_option(same_block_event_count_max, index),
                vwap_quote_per_base_observed: f64_option(vwap_quote_per_base_observed, index),
                price_quote_per_base: f64_option(price_quote_per_base, index),
                price_fill_method: string_value(price_fill_method, index),
                buy_event_ratio: f64_value(buy_event_ratio, index),
                net_flow_ratio: f64_value(net_flow_ratio, index),
                log_quote_volume: f64_value(log_quote_volume, index),
                log_events: f64_value(log_events, index),
                return_1h: f64_option(return_1h, index),
                fwd_1h: f64_option(fwd_1h, index),
                fwd_3h: f64_option(fwd_3h, index),
                fwd_6h: f64_option(fwd_6h, index),
                fwd_12h: f64_option(fwd_12h, index),
                fwd_24h: f64_option(fwd_24h, index),
            });
        }
        Ok(())
    })?;
    rows.sort_by(|a, b| a.hour_utc.cmp(&b.hour_utc));
    Ok(rows)
}

fn read_minute_price_reference_parts(
    data_root: &Path,
    parts: &[String],
) -> Result<Vec<MinutePriceRow>> {
    let files = resolve_manifest_parts(data_root, parts);
    let mut rows = Vec::new();
    read_files(&files, |batch| {
        let minute_timestamp = u64_column(batch, "minute_timestamp")?;
        let minute_utc = string_column(batch, "minute_utc")?;
        let events = u64_column(batch, "events")?;
        let base_volume = f64_column(batch, "base_volume")?;
        let quote_volume = f64_column(batch, "quote_volume")?;
        let vwap_observed = f64_column(batch, "vwap_observed")?;
        let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
        let price_fill_method = string_column(batch, "price_fill_method")?;
        for index in 0..batch.num_rows() {
            rows.push(MinutePriceRow {
                minute_timestamp: u64_value(minute_timestamp, index) as i64,
                minute_utc: string_value(minute_utc, index),
                events: u64_value(events, index),
                base_volume: f64_value(base_volume, index),
                quote_volume: f64_value(quote_volume, index),
                vwap_observed: f64_option(vwap_observed, index),
                price: f64_option(price_quote_per_base, index),
                price_fill_method: string_value(price_fill_method, index),
            });
        }
        Ok(())
    })?;
    rows.sort_by_key(|row| row.minute_timestamp);
    Ok(rows)
}

fn dataset_files(data_root: &Path, dataset: &str) -> Result<Vec<PathBuf>> {
    let root = data_root.join(RAW_DIR).join(dataset);
    let files = parquet_files_under(&root)?;
    if files.is_empty() {
        bail!("missing or empty raw dataset: {}", root.display());
    }
    Ok(files)
}

fn scan_raw_inventory(data_root: &Path, progress_interval: usize) -> Result<RawInventory> {
    let datasets = [
        POOL_SWAP_LOGS_DATASET,
        EVENT_HEADERS_DATASET,
        TX_RECEIPTS_DATASET,
    ];
    let mut dataset_inventories = Vec::new();
    let mut completed = 0usize;
    for dataset in datasets {
        let files = dataset_files(data_root, dataset)?;
        let mut file_rows = Vec::with_capacity(files.len());
        let mut total_bytes = 0u64;
        for path in files {
            let metadata = fs::metadata(&path)
                .with_context(|| format!("failed to stat {}", path.display()))?;
            let bytes = metadata.len();
            total_bytes += bytes;
            let modified_unix_nanos = metadata
                .modified()
                .ok()
                .and_then(|value| value.duration_since(UNIX_EPOCH).ok())
                .map(|value| value.as_nanos().to_string())
                .unwrap_or_else(|| "0".to_string());
            file_rows.push(RawFileFingerprint {
                relative_path: relative_path_string(data_root, &path),
                bytes,
                modified_unix_nanos,
            });
            completed += 1;
            if progress_interval > 0 && completed % progress_interval == 0 {
                eprintln!(
                    "[mon_usdc_factor_analysis] scan raw file inventory: {} parquet files",
                    completed
                );
            }
        }
        file_rows.sort_by(|a, b| a.relative_path.cmp(&b.relative_path));
        dataset_inventories.push(RawDatasetInventory {
            dataset: dataset.to_string(),
            file_count: file_rows.len(),
            total_bytes,
            files: file_rows,
        });
    }
    let file_count = dataset_inventories
        .iter()
        .map(|dataset| dataset.file_count)
        .sum::<usize>();
    let total_bytes = dataset_inventories
        .iter()
        .map(|dataset| dataset.total_bytes)
        .sum::<u64>();
    let hash = raw_inventory_hash(&dataset_inventories);
    eprintln!(
        "[mon_usdc_factor_analysis] scan raw file inventory: {file_count} files, {total_bytes} bytes, hash={hash}"
    );
    Ok(RawInventory {
        hash,
        file_count,
        total_bytes,
        datasets: dataset_inventories,
    })
}

fn raw_inventory_hash(datasets: &[RawDatasetInventory]) -> String {
    let mut hash = 0xcbf29ce484222325u64;
    hash_bytes(&mut hash, DERIVED_SCHEMA_VERSION.to_string().as_bytes());
    for dataset in datasets {
        hash_bytes(&mut hash, dataset.dataset.as_bytes());
        for file in &dataset.files {
            hash_bytes(&mut hash, file.relative_path.as_bytes());
            hash_bytes(&mut hash, file.bytes.to_string().as_bytes());
            hash_bytes(&mut hash, file.modified_unix_nanos.as_bytes());
        }
    }
    format!("{hash:016x}")
}

fn hash_bytes(hash: &mut u64, bytes: &[u8]) {
    for byte in bytes.iter().copied().chain([0xff]) {
        *hash ^= u64::from(byte);
        *hash = hash.wrapping_mul(0x100000001b3);
    }
}

fn load_valid_manifest(
    data_root: &Path,
    manifest_path: &Path,
    raw_inventory: &RawInventory,
) -> Result<Option<DerivedManifest>> {
    if !manifest_path.exists() {
        eprintln!(
            "[mon_usdc_factor_analysis] manifest cache miss: {} does not exist",
            manifest_path.display()
        );
        return Ok(None);
    }
    let file = File::open(manifest_path)
        .with_context(|| format!("failed to open {}", manifest_path.display()))?;
    let manifest: DerivedManifest = serde_json::from_reader(file)
        .with_context(|| format!("failed to parse {}", manifest_path.display()))?;
    if manifest.schema_version != DERIVED_SCHEMA_VERSION {
        eprintln!(
            "[mon_usdc_factor_analysis] manifest cache miss: schema {} != {}",
            manifest.schema_version, DERIVED_SCHEMA_VERSION
        );
        return Ok(None);
    }
    if manifest.raw_inventory.hash != raw_inventory.hash {
        eprintln!(
            "[mon_usdc_factor_analysis] manifest cache miss: raw hash {} != {}",
            manifest.raw_inventory.hash, raw_inventory.hash
        );
        return Ok(None);
    }
    for path in manifest_expected_paths(&manifest) {
        let path = resolve_data_root_path(data_root, &path);
        if !path.exists() {
            eprintln!(
                "[mon_usdc_factor_analysis] manifest cache miss: derived part missing {}",
                path.display()
            );
            return Ok(None);
        }
    }
    Ok(Some(manifest))
}

fn manifest_expected_paths(manifest: &DerivedManifest) -> Vec<String> {
    manifest
        .event_features
        .parts
        .iter()
        .chain(manifest.hourly_market_features.parts.iter())
        .chain(manifest.minute_price_reference.parts.iter())
        .cloned()
        .collect()
}

fn research_manifest_path(data_root: &Path) -> PathBuf {
    data_root
        .join(DERIVED_DIR)
        .join(MANIFEST_DATASET)
        .join(RESEARCH_MANIFEST_FILENAME)
}

fn read_parallel<T>(
    files: Vec<PathBuf>,
    label: &str,
    progress_interval: usize,
    read_chunk: fn(&[PathBuf]) -> Result<Vec<T>>,
) -> Result<Vec<T>>
where
    T: Send + 'static,
{
    let progress = ReadProgress::new(label, files.len(), progress_interval);
    let workers = std::thread::available_parallelism()
        .map(|value| value.get())
        .unwrap_or(4)
        .clamp(1, 16)
        .min(files.len().max(1));
    if workers <= 1 || files.len() < 128 {
        return read_chunk_with_progress(&files, &progress, read_chunk);
    }

    let chunk_size = files.len().div_ceil(workers);
    let mut handles = Vec::new();
    for chunk in files.chunks(chunk_size) {
        let chunk = chunk.to_vec();
        let progress = progress.clone();
        handles.push(thread::spawn(move || {
            read_chunk_with_progress(&chunk, &progress, read_chunk)
        }));
    }
    let mut rows = Vec::new();
    for handle in handles {
        let mut chunk_rows = handle
            .join()
            .map_err(|_| anyhow!("parquet reader worker panicked"))??;
        rows.append(&mut chunk_rows);
    }
    Ok(rows)
}

fn read_chunk_with_progress<T>(
    files: &[PathBuf],
    progress: &ReadProgress,
    read_chunk: fn(&[PathBuf]) -> Result<Vec<T>>,
) -> Result<Vec<T>> {
    let rows = read_chunk(files)?;
    for _ in files {
        progress.tick();
    }
    Ok(rows)
}

fn read_files<F>(files: &[PathBuf], mut on_batch: F) -> Result<()>
where
    F: FnMut(&RecordBatch) -> Result<()>,
{
    for path in files {
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder
            .with_batch_size(8192)
            .build()
            .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            on_batch(&batch)?;
        }
    }
    Ok(())
}

fn dedup_by_latest<T, K, FK, FF>(rows: Vec<T>, key_fn: FK, fetched_fn: FF) -> (Vec<T>, u64)
where
    K: Ord,
    FK: Fn(&T) -> K,
    FF: Fn(&T) -> &str,
{
    let raw_len = rows.len() as u64;
    let mut by_key = BTreeMap::<K, T>::new();
    for row in rows {
        let key = key_fn(&row);
        let replace = by_key
            .get(&key)
            .map(|existing| fetched_fn(&row) >= fetched_fn(existing))
            .unwrap_or(true);
        if replace {
            by_key.insert(key, row);
        }
    }
    let dedup_len = by_key.len() as u64;
    (by_key.into_values().collect(), raw_len - dedup_len)
}

fn build_event_panel(
    swaps: &[RawSwap],
    headers_by_block: &HashMap<u64, RawHeader>,
    receipts_by_hash: &HashMap<String, RawReceipt>,
) -> Result<Vec<EventRecord>> {
    let mut block_counts = BTreeMap::<u64, BlockEventCount>::new();
    for swap in swaps {
        let entry = block_counts.entry(swap.block_number).or_default();
        entry.events += 1;
    }

    let mut rows = Vec::with_capacity(swaps.len());
    for swap in swaps {
        let header = headers_by_block.get(&swap.block_number);
        let receipt = receipts_by_hash.get(&swap.transaction_hash);
        let timestamp = if swap.block_timestamp > 0 {
            swap.block_timestamp as i64
        } else if let Some(header) = header {
            header.block_timestamp as i64
        } else {
            parse_utc_timestamp(&swap.block_datetime_utc).unwrap_or(0)
        };
        let block_datetime_utc = if !swap.block_datetime_utc.is_empty() {
            swap.block_datetime_utc.clone()
        } else if let Some(header) = header {
            header.block_datetime_utc.clone()
        } else if timestamp > 0 {
            utc_string(timestamp)?
        } else {
            String::new()
        };
        let clean_exclusion_reason = clean_exclusion_reason(swap);
        let clean_keep = clean_exclusion_reason.is_empty();
        let is_buy_base = swap.direction == "buy_base";
        let is_sell_base = swap.direction == "sell_base";
        let base_abs = swap.base_abs.unwrap_or(0.0);
        let buy_base = if is_buy_base { base_abs } else { 0.0 };
        let sell_base = if is_sell_base { base_abs } else { 0.0 };
        let net_buy_base = if is_buy_base {
            base_abs
        } else if is_sell_base {
            -base_abs
        } else {
            0.0
        };
        let block_count = block_counts.get(&swap.block_number);
        rows.push(EventRecord {
            block_number: swap.block_number,
            timestamp,
            block_datetime_utc,
            hour_utc: if timestamp > 0 {
                format_hour(floor_to_hour(timestamp))?
            } else {
                String::new()
            },
            minute_utc: if timestamp > 0 {
                utc_string(floor_to_minute(timestamp))?
            } else {
                String::new()
            },
            transaction_hash: swap.transaction_hash.clone(),
            transaction_index: receipt
                .and_then(|row| row.transaction_index)
                .unwrap_or(swap.transaction_index),
            log_index: swap.log_index,
            pool_address: swap.pool_address.clone(),
            dex_id: swap.dex_id.clone(),
            family: swap.family.clone(),
            base_symbol: swap.base_symbol.clone(),
            quote_symbol: swap.quote_symbol.clone(),
            base_abs: swap.base_abs,
            quote_abs: swap.quote_abs,
            price_quote_per_base: swap.price_quote_per_base,
            clean_keep,
            clean_exclusion_reason,
            is_buy_base,
            is_sell_base,
            buy_base,
            sell_base,
            net_buy_base,
            receipt_request_status: receipt
                .map(|row| row.request_status.clone())
                .unwrap_or_else(|| "missing".to_string()),
            receipt_status: receipt.and_then(|row| row.receipt_status),
            receipt_gas_used: receipt.and_then(|row| row.gas_used),
            effective_gas_price: receipt.and_then(|row| row.effective_gas_price),
            base_fee_per_gas: header.and_then(|row| row.base_fee_per_gas),
            header_event_log_count: header.map(|row| row.event_log_count),
            same_block_event_count: block_count.map(|row| row.events).unwrap_or(1),
        });
    }
    rows.sort_by_key(|row| {
        (
            row.timestamp,
            row.block_number,
            row.transaction_index,
            row.log_index,
            row.pool_address.clone(),
        )
    });
    Ok(rows)
}

fn clean_exclusion_reason(swap: &RawSwap) -> String {
    if swap.removed {
        return "removed".to_string();
    }
    if !positive(swap.base_abs) {
        return "base_abs_nonpositive".to_string();
    }
    if !positive(swap.quote_abs) {
        return "quote_abs_nonpositive".to_string();
    }
    if !positive(swap.price_quote_per_base) {
        return "price_nonpositive".to_string();
    }
    String::new()
}

fn raw_swaps_len(event_panel: &[EventRecord], duplicate_swaps: u64) -> u64 {
    event_panel.len() as u64 + duplicate_swaps
}

fn build_coverage(
    raw_swap_rows: u64,
    swaps: &[RawSwap],
    headers: &[RawHeader],
    receipts: &[RawReceipt],
    duplicate_swaps: u64,
    duplicate_headers: u64,
    duplicate_receipts: u64,
    event_panel: &[EventRecord],
) -> Result<CoverageSummary> {
    let clean = event_panel
        .iter()
        .filter(|row| row.clean_keep)
        .collect::<Vec<_>>();
    let clean_start = clean
        .iter()
        .map(|row| row.timestamp)
        .min()
        .ok_or_else(|| anyhow!("no clean events for coverage"))?;
    let clean_end = clean
        .iter()
        .map(|row| row.timestamp)
        .max()
        .ok_or_else(|| anyhow!("no clean events for coverage"))?;
    let clean_block_min = clean.iter().map(|row| row.block_number).min().unwrap_or(0);
    let clean_block_max = clean.iter().map(|row| row.block_number).max().unwrap_or(0);
    let swap_blocks = swaps
        .iter()
        .map(|row| row.block_number)
        .collect::<BTreeSet<_>>();
    let header_blocks = headers
        .iter()
        .map(|row| row.block_number)
        .collect::<BTreeSet<_>>();
    let swap_txs = swaps
        .iter()
        .map(|row| row.transaction_hash.clone())
        .collect::<BTreeSet<_>>();
    let receipt_txs = receipts
        .iter()
        .map(|row| row.transaction_hash.clone())
        .collect::<BTreeSet<_>>();
    let receipt_request_status_errors = receipts
        .iter()
        .filter(|row| !matches!(row.request_status.as_str(), "ok" | "receipt_only"))
        .count() as u64;
    let receipt_failure_rows = receipts
        .iter()
        .filter(|row| row.receipt_status.is_some_and(|status| status != 1))
        .count() as u64;
    Ok(CoverageSummary {
        raw_swap_rows,
        dedup_swap_rows: swaps.len() as u64,
        clean_swap_rows: clean.len() as u64,
        excluded_swaps: event_panel.iter().filter(|row| !row.clean_keep).count() as u64,
        removed_swaps: swaps.iter().filter(|row| row.removed).count() as u64,
        duplicate_swaps,
        raw_header_rows: headers.len() as u64 + duplicate_headers,
        dedup_header_rows: headers.len() as u64,
        duplicate_headers,
        raw_receipt_rows: receipts.len() as u64 + duplicate_receipts,
        dedup_receipt_rows: receipts.len() as u64,
        duplicate_receipts,
        unique_swap_blocks: swap_blocks.len() as u64,
        unique_swap_txs: swap_txs.len() as u64,
        missing_event_headers: swap_blocks
            .iter()
            .filter(|block| !header_blocks.contains(block))
            .count() as u64,
        missing_receipts: swap_txs
            .iter()
            .filter(|hash| !receipt_txs.contains(*hash))
            .count() as u64,
        receipt_request_status_errors,
        receipt_failure_rows,
        clean_start: utc_string(clean_start)?,
        clean_end: utc_string(clean_end)?,
        clean_block_min,
        clean_block_max,
        span_days: (clean_end - clean_start) as f64 / 86_400.0,
    })
}

fn build_exclusion_summary(event_panel: &[EventRecord]) -> Vec<ExclusionSummaryRow> {
    let mut counts = BTreeMap::<String, u64>::new();
    for row in event_panel.iter().filter(|row| !row.clean_keep) {
        *counts
            .entry(row.clean_exclusion_reason.clone())
            .or_default() += 1;
    }
    let mut rows = counts
        .into_iter()
        .map(|(reason, rows)| ExclusionSummaryRow { reason, rows })
        .collect::<Vec<_>>();
    rows.sort_by(|a, b| b.rows.cmp(&a.rows).then_with(|| a.reason.cmp(&b.reason)));
    rows
}

fn build_pool_summary(event_panel: &[EventRecord]) -> Vec<PoolSummaryRow> {
    let mut by_pool = BTreeMap::<(String, String, String, String, String), PoolAgg>::new();
    for event in event_panel {
        let key = (
            event.dex_id.clone(),
            event.family.clone(),
            event.pool_address.clone(),
            event.base_symbol.clone(),
            event.quote_symbol.clone(),
        );
        let entry = by_pool.entry(key).or_insert_with(|| PoolAgg {
            dex_id: event.dex_id.clone(),
            family: event.family.clone(),
            pool_address: event.pool_address.clone(),
            base_symbol: event.base_symbol.clone(),
            quote_symbol: event.quote_symbol.clone(),
            ..PoolAgg::default()
        });
        entry.raw_events += 1;
        if !event.clean_keep {
            entry.excluded_events += 1;
            continue;
        }
        let base_abs = event.base_abs.unwrap_or(0.0);
        let quote_abs = event.quote_abs.unwrap_or(0.0);
        entry.clean_events += 1;
        entry.unique_txs.insert(event.transaction_hash.clone());
        entry.active_blocks.insert(event.block_number);
        if event.is_buy_base {
            entry.buy_events += 1;
        }
        if event.is_sell_base {
            entry.sell_events += 1;
        }
        entry.buy_base += event.buy_base;
        entry.sell_base += event.sell_base;
        entry.net_buy_base += event.net_buy_base;
        entry.base_volume += base_abs;
        entry.quote_volume += quote_abs;
        if let Some(price) = event.price_quote_per_base.filter(|price| price.is_finite()) {
            entry.prices.push(price);
        }
        if entry
            .first_seen
            .as_ref()
            .map(|value| &event.block_datetime_utc < value)
            .unwrap_or(true)
        {
            entry.first_seen = Some(event.block_datetime_utc.clone());
        }
        if entry
            .last_seen
            .as_ref()
            .map(|value| &event.block_datetime_utc > value)
            .unwrap_or(true)
        {
            entry.last_seen = Some(event.block_datetime_utc.clone());
        }
        entry
            .receipt_success
            .add(event.receipt_status.map(|value| value as f64));
        entry
            .gas_used
            .add(event.receipt_gas_used.map(|value| value as f64));
        entry
            .effective_gas_gwei
            .add(event.effective_gas_price.map(|value| value as f64 / 1e9));
    }
    let mut rows = by_pool
        .into_values()
        .map(|agg| PoolSummaryRow {
            dex_id: agg.dex_id,
            family: agg.family,
            pool_address: agg.pool_address,
            base_symbol: agg.base_symbol,
            quote_symbol: agg.quote_symbol,
            raw_events: agg.raw_events,
            clean_events: agg.clean_events,
            excluded_events: agg.excluded_events,
            unique_txs: agg.unique_txs.len() as u64,
            active_blocks: agg.active_blocks.len() as u64,
            buy_events: agg.buy_events,
            sell_events: agg.sell_events,
            buy_base: agg.buy_base,
            sell_base: agg.sell_base,
            net_buy_base: agg.net_buy_base,
            base_volume: agg.base_volume,
            quote_volume: agg.quote_volume,
            median_price_quote_per_base: median(agg.prices),
            first_seen: agg.first_seen.unwrap_or_default(),
            last_seen: agg.last_seen.unwrap_or_default(),
            receipt_success_rate: agg.receipt_success.mean(),
            gas_used_mean: agg.gas_used.mean(),
            effective_gas_gwei_mean: agg.effective_gas_gwei.mean(),
            quote_volume_share: None,
            base_volume_share: None,
            net_flow_ratio: safe_div(agg.net_buy_base, agg.base_volume),
        })
        .collect::<Vec<_>>();
    let total_quote = rows.iter().map(|row| row.quote_volume).sum::<f64>();
    let total_base = rows.iter().map(|row| row.base_volume).sum::<f64>();
    for row in &mut rows {
        row.quote_volume_share = safe_div(row.quote_volume, total_quote);
        row.base_volume_share = safe_div(row.base_volume, total_base);
    }
    rows.sort_by(|a, b| {
        desc_f64(a.quote_volume, b.quote_volume).then_with(|| b.clean_events.cmp(&a.clean_events))
    });
    rows
}

fn build_hourly_market(clean_events: &[EventRecord]) -> Result<Vec<HourlyMarketRow>> {
    let min_hour = clean_events
        .iter()
        .map(|event| floor_to_hour(event.timestamp))
        .min()
        .ok_or_else(|| anyhow!("empty clean event set"))?;
    let max_hour = clean_events
        .iter()
        .map(|event| floor_to_hour(event.timestamp))
        .max()
        .ok_or_else(|| anyhow!("empty clean event set"))?;
    let mut by_hour = BTreeMap::<i64, HourAgg>::new();
    for event in clean_events {
        if event.timestamp <= 0 {
            bail!(
                "clean event has missing timestamp: {} {}",
                event.transaction_hash,
                event.log_index
            );
        }
        let entry = by_hour.entry(floor_to_hour(event.timestamp)).or_default();
        let base_abs = event.base_abs.unwrap_or(0.0);
        let quote_abs = event.quote_abs.unwrap_or(0.0);
        entry.events += 1;
        entry.unique_txs.insert(event.transaction_hash.clone());
        entry.pools.insert(event.pool_address.clone());
        entry.dexes.insert(event.dex_id.clone());
        entry.active_blocks.insert(event.block_number);
        if event.is_buy_base {
            entry.buy_events += 1;
        }
        if event.is_sell_base {
            entry.sell_events += 1;
        }
        entry.buy_base += event.buy_base;
        entry.sell_base += event.sell_base;
        entry.net_buy_base += event.net_buy_base;
        entry.base_volume += base_abs;
        entry.quote_volume += quote_abs;
        entry
            .gas_used
            .add(event.receipt_gas_used.map(|value| value as f64));
        entry
            .effective_gas_gwei
            .add(event.effective_gas_price.map(|value| value as f64 / 1e9));
        entry
            .base_fee_gwei
            .add(event.base_fee_per_gas.map(|value| value as f64 / 1e9));
        entry
            .receipt_success
            .add(event.receipt_status.map(|value| value as f64));
        entry
            .same_block_event_count
            .add(Some(event.same_block_event_count as f64));
        entry.same_block_event_count_max = entry
            .same_block_event_count_max
            .max(event.same_block_event_count);
    }

    let mut rows = Vec::new();
    let mut observed_prices = Vec::new();
    let mut last_price = None;
    let mut hour = min_hour;
    while hour <= max_hour {
        let agg = by_hour.remove(&hour).unwrap_or_default();
        let observed_price = safe_div(agg.quote_volume, agg.base_volume);
        if observed_price.is_some() {
            last_price = observed_price;
        }
        let price = last_price;
        let events = agg.events;
        let buy_event_ratio = safe_div(agg.buy_events as f64, events as f64).unwrap_or(0.0);
        let net_flow_ratio = safe_div(agg.net_buy_base, agg.base_volume).unwrap_or(0.0);
        observed_prices.push(price);
        rows.push(HourlyMarketRow {
            hour_utc: format_hour(hour)?,
            events,
            unique_txs: agg.unique_txs.len() as u64,
            pools: agg.pools.len() as u64,
            dexes: agg.dexes.len() as u64,
            active_blocks: agg.active_blocks.len() as u64,
            buy_events: agg.buy_events,
            sell_events: agg.sell_events,
            buy_base: agg.buy_base,
            sell_base: agg.sell_base,
            net_buy_base: agg.net_buy_base,
            base_volume: agg.base_volume,
            quote_volume: agg.quote_volume,
            gas_used_mean: agg.gas_used.mean(),
            effective_gas_gwei_mean: agg.effective_gas_gwei.mean(),
            base_fee_gwei_mean: agg.base_fee_gwei.mean(),
            receipt_success_rate: agg.receipt_success.mean(),
            same_block_event_count_mean: agg.same_block_event_count.mean(),
            same_block_event_count_max: if agg.same_block_event_count_max == 0 {
                None
            } else {
                Some(agg.same_block_event_count_max as f64)
            },
            vwap_quote_per_base_observed: observed_price,
            price_quote_per_base: price,
            price_fill_method: if observed_price.is_some() {
                "observed".to_string()
            } else {
                "forward_fill".to_string()
            },
            buy_event_ratio,
            net_flow_ratio,
            log_quote_volume: agg.quote_volume.max(0.0).ln_1p(),
            log_events: (events as f64).ln_1p(),
            return_1h: None,
            fwd_1h: None,
            fwd_3h: None,
            fwd_6h: None,
            fwd_12h: None,
            fwd_24h: None,
        });
        hour += 3600;
    }

    for index in 0..rows.len() {
        rows[index].return_1h = if index == 0 {
            None
        } else {
            forward_return(observed_prices[index - 1], observed_prices[index])
        };
        rows[index].fwd_1h = future_from_prices(&observed_prices, index, 1);
        rows[index].fwd_3h = future_from_prices(&observed_prices, index, 3);
        rows[index].fwd_6h = future_from_prices(&observed_prices, index, 6);
        rows[index].fwd_12h = future_from_prices(&observed_prices, index, 12);
        rows[index].fwd_24h = future_from_prices(&observed_prices, index, 24);
    }
    Ok(rows)
}

fn build_minute_price_rows(clean_events: &[EventRecord]) -> Result<Vec<MinutePriceRow>> {
    let min_minute = clean_events
        .iter()
        .map(|event| floor_to_minute(event.timestamp))
        .min()
        .ok_or_else(|| anyhow!("empty clean event set"))?;
    let max_minute = clean_events
        .iter()
        .map(|event| floor_to_minute(event.timestamp))
        .max()
        .ok_or_else(|| anyhow!("empty clean event set"))?;
    let mut by_minute = BTreeMap::<i64, MinuteAgg>::new();
    for event in clean_events {
        let entry = by_minute
            .entry(floor_to_minute(event.timestamp))
            .or_default();
        entry.events += 1;
        entry.base_volume += event.base_abs.unwrap_or(0.0);
        entry.quote_volume += event.quote_abs.unwrap_or(0.0);
    }
    let mut rows = Vec::new();
    let mut last_price = None;
    let mut minute = min_minute;
    while minute <= max_minute {
        let agg = by_minute.remove(&minute).unwrap_or_default();
        let observed = safe_div(agg.quote_volume, agg.base_volume);
        if observed.is_some() {
            last_price = observed;
        }
        rows.push(MinutePriceRow {
            minute_timestamp: minute,
            minute_utc: utc_string(minute)?,
            events: agg.events,
            base_volume: agg.base_volume,
            quote_volume: agg.quote_volume,
            vwap_observed: observed,
            price: last_price,
            price_fill_method: if observed.is_some() {
                "observed".to_string()
            } else {
                "forward_fill".to_string()
            },
        });
        minute += 60;
    }
    Ok(rows)
}

fn minute_series_from_rows(rows: &[MinutePriceRow]) -> Result<MinutePriceSeries> {
    let start_minute = rows
        .iter()
        .map(|row| row.minute_timestamp)
        .min()
        .ok_or_else(|| anyhow!("empty minute price reference"))?;
    let mut points = Vec::with_capacity(rows.len());
    let mut expected = start_minute;
    for row in rows {
        if row.minute_timestamp != expected {
            bail!(
                "minute price reference has a gap or duplicate at {} expected {}",
                row.minute_timestamp,
                expected
            );
        }
        points.push(MinutePricePoint {
            vwap_observed: row.vwap_observed,
            price: row.price,
            price_fill_method: row.price_fill_method.clone(),
        });
        expected += 60;
    }
    Ok(MinutePriceSeries {
        start_minute,
        rows: points,
    })
}

fn build_price_coverage(
    minute_prices: &MinutePriceSeries,
    hourly_market: &[HourlyMarketRow],
) -> PriceCoverage {
    PriceCoverage {
        minute_rows: minute_prices.rows.len() as u64,
        minute_observed: minute_prices
            .rows
            .iter()
            .filter(|row| row.vwap_observed.is_some())
            .count() as u64,
        minute_forward_fill: minute_prices
            .rows
            .iter()
            .filter(|row| row.price_fill_method == "forward_fill")
            .count() as u64,
        hourly_rows: hourly_market.len() as u64,
        hourly_observed: hourly_market
            .iter()
            .filter(|row| row.vwap_quote_per_base_observed.is_some())
            .count() as u64,
        hourly_forward_fill: hourly_market
            .iter()
            .filter(|row| row.price_fill_method == "forward_fill")
            .count() as u64,
    }
}

fn build_hourly_factor_tests(hourly: &[HourlyMarketRow]) -> Vec<FactorTestRow> {
    let targets = HOURLY_HORIZONS
        .iter()
        .map(|horizon| format!("fwd_{horizon}h"))
        .collect::<Vec<_>>();
    let mut rows = Vec::new();
    for factor in HOURLY_FACTORS {
        let factor_values = hourly
            .iter()
            .map(|row| hourly_factor_value(row, factor))
            .collect::<Vec<_>>();
        for target in &targets {
            let target_values = hourly
                .iter()
                .map(|row| hourly_target_value(row, target))
                .collect::<Vec<_>>();
            if let Some(row) =
                continuous_factor_test(factor, target, &factor_values, &target_values, 30)
            {
                rows.push(row);
            }
        }
    }
    sort_factor_tests(&mut rows);
    rows
}

fn build_event_factor_tests(
    clean_events: &[EventRecord],
    minute_prices: &MinutePriceSeries,
) -> Vec<FactorTestRow> {
    let targets = EVENT_HORIZONS
        .iter()
        .map(|(label, _)| format!("fwd_{label}"))
        .collect::<Vec<_>>();
    let mut target_cache = BTreeMap::<String, Vec<Option<f64>>>::new();
    for (label, seconds) in EVENT_HORIZONS {
        let target = format!("fwd_{label}");
        let values = clean_events
            .iter()
            .map(|event| {
                let current = minute_prices.price_at(floor_to_minute(event.timestamp));
                let future = minute_prices.price_at(floor_to_minute(event.timestamp + seconds));
                forward_return(current, future)
            })
            .collect::<Vec<_>>();
        target_cache.insert(target, values);
    }

    let mut rows = Vec::new();
    for factor in EVENT_FACTORS {
        let factor_values = clean_events
            .iter()
            .map(|event| event_factor_value(event, factor))
            .collect::<Vec<_>>();
        for target in &targets {
            let target_values = target_cache.get(target).expect("target cached");
            let test = if factor == "is_buy_base" {
                binary_factor_test(factor, target, &factor_values, target_values, 500)
            } else {
                continuous_factor_test(factor, target, &factor_values, target_values, 500)
            };
            if let Some(row) = test {
                rows.push(row);
            }
        }
    }
    sort_factor_tests(&mut rows);
    rows
}

fn continuous_factor_test(
    factor: &str,
    target: &str,
    factor_values: &[Option<f64>],
    target_values: &[Option<f64>],
    min_rows: usize,
) -> Option<FactorTestRow> {
    let buckets = qcut_buckets(factor_values, 3);
    let mut factor = factor.to_string();
    let mut target = target.to_string();
    let mut triples = Vec::<(f64, f64, u8)>::new();
    for ((factor_value, target_value), bucket) in
        factor_values.iter().zip(target_values).zip(buckets.iter())
    {
        let Some(factor_value) = factor_value
            .as_ref()
            .copied()
            .filter(|value| value.is_finite())
        else {
            continue;
        };
        let Some(target_value) = target_value
            .as_ref()
            .copied()
            .filter(|value| value.is_finite())
        else {
            continue;
        };
        let Some(bucket) = bucket else {
            continue;
        };
        triples.push((factor_value, target_value, *bucket));
    }
    if triples.len() < min_rows {
        return None;
    }
    let unique = triples
        .iter()
        .map(|(factor, _, _)| factor.to_bits())
        .collect::<BTreeSet<_>>();
    if unique.len() < 2 {
        return None;
    }
    let low_bucket = triples.iter().map(|(_, _, bucket)| *bucket).min()? as i64;
    let high_bucket = triples.iter().map(|(_, _, bucket)| *bucket).max()? as i64;
    let low = triples
        .iter()
        .filter(|(_, _, bucket)| i64::from(*bucket) == low_bucket)
        .map(|(_, target, _)| *target)
        .collect::<Vec<_>>();
    let high = triples
        .iter()
        .filter(|(_, _, bucket)| i64::from(*bucket) == high_bucket)
        .map(|(_, target, _)| *target)
        .collect::<Vec<_>>();
    if low.is_empty() || high.is_empty() {
        return None;
    }
    let factors = triples
        .iter()
        .map(|(factor, _, _)| *factor)
        .collect::<Vec<_>>();
    let targets = triples
        .iter()
        .map(|(_, target, _)| *target)
        .collect::<Vec<_>>();
    Some(FactorTestRow {
        factor: std::mem::take(&mut factor),
        factor_type: "continuous".to_string(),
        target: std::mem::take(&mut target),
        n: triples.len() as u64,
        factor_non_null: triples.len() as u64,
        pearson: pearson(&factors, &targets),
        spearman: spearman(&factors, &targets),
        low_bucket,
        high_bucket,
        low_mean: mean(&low),
        high_mean: mean(&high),
        high_minus_low: mean(&high)
            .zip(mean(&low))
            .and_then(|(high, low)| finite(high - low)),
        low_positive_rate: positive_rate(&low),
        high_positive_rate: positive_rate(&high),
    })
}

fn binary_factor_test(
    factor: &str,
    target: &str,
    factor_values: &[Option<f64>],
    target_values: &[Option<f64>],
    min_rows: usize,
) -> Option<FactorTestRow> {
    let mut pairs = Vec::<(f64, f64)>::new();
    for (factor_value, target_value) in factor_values.iter().zip(target_values) {
        let Some(factor_value) = factor_value
            .as_ref()
            .copied()
            .filter(|value| value.is_finite())
        else {
            continue;
        };
        let Some(target_value) = target_value
            .as_ref()
            .copied()
            .filter(|value| value.is_finite())
        else {
            continue;
        };
        pairs.push((factor_value, target_value));
    }
    if pairs.len() < min_rows {
        return None;
    }
    let unique = pairs
        .iter()
        .map(|(factor, _)| factor.round() as i64)
        .collect::<BTreeSet<_>>();
    if unique.len() < 2 {
        return None;
    }
    let low = pairs
        .iter()
        .filter(|(factor, _)| *factor == 0.0)
        .map(|(_, target)| *target)
        .collect::<Vec<_>>();
    let high = pairs
        .iter()
        .filter(|(factor, _)| *factor == 1.0)
        .map(|(_, target)| *target)
        .collect::<Vec<_>>();
    if low.is_empty() || high.is_empty() {
        return None;
    }
    let factors = pairs.iter().map(|(factor, _)| *factor).collect::<Vec<_>>();
    let targets = pairs.iter().map(|(_, target)| *target).collect::<Vec<_>>();
    Some(FactorTestRow {
        factor: factor.to_string(),
        factor_type: "binary".to_string(),
        target: target.to_string(),
        n: pairs.len() as u64,
        factor_non_null: pairs.len() as u64,
        pearson: pearson(&factors, &targets),
        spearman: spearman(&factors, &targets),
        low_bucket: 0,
        high_bucket: 1,
        low_mean: mean(&low),
        high_mean: mean(&high),
        high_minus_low: mean(&high)
            .zip(mean(&low))
            .and_then(|(high, low)| finite(high - low)),
        low_positive_rate: positive_rate(&low),
        high_positive_rate: positive_rate(&high),
    })
}

fn qcut_buckets(values: &[Option<f64>], buckets: usize) -> Vec<Option<u8>> {
    let mut out = vec![None; values.len()];
    let mut valid = values
        .iter()
        .enumerate()
        .filter_map(|(index, value)| {
            value
                .as_ref()
                .copied()
                .filter(|value| value.is_finite())
                .map(|value| (index, value))
        })
        .collect::<Vec<_>>();
    if valid.len() < 30 || buckets == 0 {
        return out;
    }
    let unique = valid
        .iter()
        .map(|(_, value)| value.to_bits())
        .collect::<BTreeSet<_>>();
    if unique.len() < buckets {
        return out;
    }
    valid.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
    let len = valid.len();
    for (position, (index, _)) in valid.into_iter().enumerate() {
        let bucket = ((position * buckets) / len).min(buckets - 1) as u8;
        out[index] = Some(bucket);
    }
    out
}

fn hourly_factor_value(row: &HourlyMarketRow, factor: &str) -> Option<f64> {
    match factor {
        "events" => Some(row.events as f64),
        "quote_volume" => Some(row.quote_volume),
        "log_quote_volume" => Some(row.log_quote_volume),
        "net_flow_ratio" => Some(row.net_flow_ratio),
        "buy_event_ratio" => Some(row.buy_event_ratio),
        "active_blocks" => Some(row.active_blocks as f64),
        "pools" => Some(row.pools as f64),
        "effective_gas_gwei_mean" => row.effective_gas_gwei_mean,
        "receipt_success_rate" => row.receipt_success_rate,
        _ => None,
    }
}

fn hourly_target_value(row: &HourlyMarketRow, target: &str) -> Option<f64> {
    match target {
        "fwd_1h" => row.fwd_1h,
        "fwd_3h" => row.fwd_3h,
        "fwd_6h" => row.fwd_6h,
        "fwd_12h" => row.fwd_12h,
        "fwd_24h" => row.fwd_24h,
        _ => None,
    }
}

fn event_factor_value(event: &EventRecord, factor: &str) -> Option<f64> {
    match factor {
        "is_buy_base" => Some(if event.is_buy_base { 1.0 } else { 0.0 }),
        "quote_abs" => event.quote_abs,
        "log_quote_abs" => event.quote_abs.map(|value| value.max(0.0).ln_1p()),
        "base_abs" => event.base_abs,
        "log_base_abs" => event.base_abs.map(|value| value.max(0.0).ln_1p()),
        "gas_used" => event.receipt_gas_used.map(|value| value as f64),
        "effective_gas_gwei" => event.effective_gas_price.map(|value| value as f64 / 1e9),
        "same_block_event_count" => Some(event.same_block_event_count as f64),
        "header_event_log_count" => event.header_event_log_count.map(|value| value as f64),
        _ => None,
    }
}

fn sort_factor_tests(rows: &mut [FactorTestRow]) {
    rows.sort_by(|a, b| {
        a.target
            .cmp(&b.target)
            .then_with(|| desc_option_abs_f64(a.spearman, b.spearman))
            .then_with(|| b.n.cmp(&a.n))
    });
}

fn forward_return(current: Option<f64>, future: Option<f64>) -> Option<f64> {
    match (current, future) {
        (Some(current), Some(future))
            if current.is_finite() && future.is_finite() && current != 0.0 =>
        {
            finite(future / current - 1.0)
        }
        _ => None,
    }
}

fn future_from_prices(prices: &[Option<f64>], index: usize, horizon: usize) -> Option<f64> {
    let current = prices.get(index).copied().flatten();
    let future = prices.get(index + horizon).copied().flatten();
    forward_return(current, future)
}

fn pearson(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 2 {
        return None;
    }
    let n = xs.len() as f64;
    let mean_x = xs.iter().sum::<f64>() / n;
    let mean_y = ys.iter().sum::<f64>() / n;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    for (x, y) in xs.iter().zip(ys) {
        let dx = *x - mean_x;
        let dy = *y - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    if var_x <= 0.0 || var_y <= 0.0 {
        None
    } else {
        finite(cov / (var_x.sqrt() * var_y.sqrt()))
    }
}

fn spearman(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 2 {
        return None;
    }
    let xr = average_ranks(xs);
    let yr = average_ranks(ys);
    pearson(&xr, &yr)
}

fn average_ranks(values: &[f64]) -> Vec<f64> {
    let mut indexed = values
        .iter()
        .copied()
        .enumerate()
        .collect::<Vec<(usize, f64)>>();
    indexed.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
    let mut ranks = vec![0.0; values.len()];
    let mut start = 0usize;
    while start < indexed.len() {
        let mut end = start + 1;
        while end < indexed.len() && indexed[end].1 == indexed[start].1 {
            end += 1;
        }
        let rank = (start + 1 + end) as f64 / 2.0;
        for (index, _) in &indexed[start..end] {
            ranks[*index] = rank;
        }
        start = end;
    }
    ranks
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

fn mean(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    finite(values.iter().sum::<f64>() / values.len() as f64)
}

fn positive_rate(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    finite(values.iter().filter(|value| **value > 0.0).count() as f64 / values.len() as f64)
}

fn safe_div(numerator: f64, denominator: f64) -> Option<f64> {
    if !numerator.is_finite() || !denominator.is_finite() || denominator == 0.0 {
        None
    } else {
        finite(numerator / denominator)
    }
}

fn positive(value: Option<f64>) -> bool {
    value.is_some_and(|value| value.is_finite() && value > 0.0)
}

fn finite(value: f64) -> Option<f64> {
    if value.is_finite() { Some(value) } else { None }
}

fn desc_f64(a: f64, b: f64) -> Ordering {
    b.total_cmp(&a)
}

fn desc_option_abs_f64(a: Option<f64>, b: Option<f64>) -> Ordering {
    match (a, b) {
        (Some(a), Some(b)) => b.abs().total_cmp(&a.abs()),
        (Some(_), None) => Ordering::Less,
        (None, Some(_)) => Ordering::Greater,
        (None, None) => Ordering::Equal,
    }
}

fn floor_to_hour(timestamp: i64) -> i64 {
    timestamp - timestamp.rem_euclid(3600)
}

fn floor_to_minute(timestamp: i64) -> i64 {
    timestamp - timestamp.rem_euclid(60)
}

fn format_hour(timestamp: i64) -> Result<String> {
    Ok(DateTime::<Utc>::from_timestamp(timestamp, 0)
        .ok_or_else(|| anyhow!("invalid hour timestamp {timestamp}"))?
        .format("%Y-%m-%dT%H:00:00Z")
        .to_string())
}

fn utc_string(timestamp: i64) -> Result<String> {
    Ok(DateTime::<Utc>::from_timestamp(timestamp, 0)
        .ok_or_else(|| anyhow!("invalid timestamp {timestamp}"))?
        .to_rfc3339_opts(SecondsFormat::Secs, true))
}

fn parse_utc_timestamp(value: &str) -> Option<i64> {
    if value.is_empty() {
        return None;
    }
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|value| value.timestamp())
}

fn cache_summary_from_manifest(
    data_root: &Path,
    raw_inventory: &RawInventory,
    manifest: &DerivedManifest,
    status: &str,
) -> DerivedCacheSummary {
    DerivedCacheSummary {
        schema_version: DERIVED_SCHEMA_VERSION,
        status: status.to_string(),
        manifest: path_string(&research_manifest_path(data_root)),
        raw_fingerprint_hash: raw_inventory.hash.clone(),
        raw_file_count: raw_inventory.file_count,
        raw_total_bytes: raw_inventory.total_bytes,
        event_features_parts: manifest.event_features.parts.clone(),
        hourly_market_features_parts: manifest.hourly_market_features.parts.clone(),
        minute_price_reference_parts: manifest.minute_price_reference.parts.clone(),
    }
}

fn cache_summary_without_manifest(
    raw_inventory: RawInventory,
    status: &str,
) -> DerivedCacheSummary {
    DerivedCacheSummary {
        schema_version: DERIVED_SCHEMA_VERSION,
        status: status.to_string(),
        manifest: String::new(),
        raw_fingerprint_hash: raw_inventory.hash,
        raw_file_count: raw_inventory.file_count,
        raw_total_bytes: raw_inventory.total_bytes,
        event_features_parts: Vec::new(),
        hourly_market_features_parts: Vec::new(),
        minute_price_reference_parts: Vec::new(),
    }
}

fn resolve_manifest_parts(data_root: &Path, parts: &[String]) -> Vec<PathBuf> {
    parts
        .iter()
        .map(|path| resolve_data_root_path(data_root, path))
        .collect()
}

fn resolve_data_root_path(data_root: &Path, value: &str) -> PathBuf {
    let path = PathBuf::from(value);
    if path.is_absolute() {
        path
    } else {
        data_root.join(path)
    }
}

fn relative_path_string(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(path_string)
        .unwrap_or_else(|_| path_string(path))
}

fn log_stage(stage: &str) {
    eprintln!("[mon_usdc_factor_analysis] stage: {stage}");
}

fn current_executable_path() -> String {
    std::env::current_exe()
        .map(|path| path_string(&path))
        .unwrap_or_default()
}

fn write_csv<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    if rows.is_empty() {
        bail!("refusing to write empty CSV {}", path.display());
    }
    ensure_parent_dir(path)?;
    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create {}", path.display()))?;
    for row in rows {
        writer
            .serialize(row)
            .with_context(|| format!("failed to serialize row into {}", path.display()))?;
    }
    writer
        .flush()
        .with_context(|| format!("failed to flush {}", path.display()))
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    ensure_parent_dir(path)?;
    let file =
        File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, value)
        .with_context(|| format!("failed to write {}", path.display()))
}

fn assert_no_inf(path: &Path) -> Result<()> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    for record in reader.records() {
        let record = record.with_context(|| format!("failed reading {}", path.display()))?;
        for field in &record {
            let lower = field.to_ascii_lowercase();
            if lower == "inf" || lower == "-inf" || lower == "infinity" || lower == "-infinity" {
                bail!("{} contains an infinite value", path.display());
            }
        }
    }
    Ok(())
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn string_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| anyhow!("column {name} is not utf8"))
}

fn u64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a UInt64Array> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .ok_or_else(|| anyhow!("column {name} is not uint64"))
}

fn f64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| anyhow!("column {name} is not float64"))
}

fn bool_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a BooleanArray> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<BooleanArray>()
        .ok_or_else(|| anyhow!("column {name} is not boolean"))
}

fn string_value(values: &StringArray, index: usize) -> String {
    if values.is_null(index) {
        String::new()
    } else {
        values.value(index).to_string()
    }
}

fn u64_value(values: &UInt64Array, index: usize) -> u64 {
    if values.is_null(index) {
        0
    } else {
        values.value(index)
    }
}

fn u64_option(values: &UInt64Array, index: usize) -> Option<u64> {
    if values.is_null(index) {
        None
    } else {
        Some(values.value(index))
    }
}

fn f64_value(values: &Float64Array, index: usize) -> f64 {
    if values.is_null(index) {
        0.0
    } else {
        values.value(index)
    }
}

fn f64_option(values: &Float64Array, index: usize) -> Option<f64> {
    if values.is_null(index) {
        None
    } else {
        finite(values.value(index))
    }
}

fn bool_value(values: &BooleanArray, index: usize) -> bool {
    !values.is_null(index) && values.value(index)
}

fn parse_f64_string(values: &StringArray, index: usize) -> Option<f64> {
    if values.is_null(index) {
        return None;
    }
    values.value(index).parse::<f64>().ok().and_then(finite)
}

fn opt_f64_array(values: &[Option<f64>]) -> ArrayRef {
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        match value.as_ref().copied().and_then(finite) {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forward_return_requires_finite_nonzero_current() {
        let value = forward_return(Some(100.0), Some(110.0)).unwrap();
        assert!((value - 0.1).abs() < 1e-12);
        assert_eq!(forward_return(Some(0.0), Some(110.0)), None);
        assert_eq!(forward_return(Some(f64::INFINITY), Some(110.0)), None);
    }

    #[test]
    fn qcut_buckets_splits_valid_values_into_three_groups() {
        let values = (0..30).map(|value| Some(value as f64)).collect::<Vec<_>>();
        let buckets = qcut_buckets(&values, 3);
        assert_eq!(
            buckets.iter().filter(|value| **value == Some(0)).count(),
            10
        );
        assert_eq!(
            buckets.iter().filter(|value| **value == Some(1)).count(),
            10
        );
        assert_eq!(
            buckets.iter().filter(|value| **value == Some(2)).count(),
            10
        );
    }

    #[test]
    fn spearman_tracks_monotonic_relationships() {
        let xs = vec![1.0, 2.0, 3.0, 4.0];
        let ys = vec![10.0, 20.0, 30.0, 40.0];
        let value = spearman(&xs, &ys).unwrap();
        assert!((value - 1.0).abs() < 1e-12);
    }
}

use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::fs::File;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{
    Array, ArrayRef, BooleanArray, Float64Array, Float64Builder, StringArray, UInt64Array,
};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, SecondsFormat, Utc};
use finance_chain_core::storage::{
    DERIVED_DIR, bool_array, custom_part_path, ensure_parent_dir, opt_u64_array,
    parquet_files_under, string_array, u64_array, write_parquet_part, write_schema_metadata,
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::Serialize;

use crate::{DEFAULT_DATA_ROOT, DEFAULT_PROGRESS_INTERVAL};

pub const DEFAULT_FACTOR_SOURCE_RUN_TAG: &str = "20260511_reconstruct_v1";
pub const DEFAULT_FACTOR_SEARCH_RUN_TAG: &str = "20260511_factor_map_v1";

const EXECUTION_FEATURES_DATASET: &str = "mon_usdc_event_execution_features";
const TX_PATH_RECONSTRUCTED_DATASET: &str = "tx_execution_path_labels_reconstructed";
const POOL_STATE_RECONSTRUCTED_DATASET: &str = "pool_state_event_features_reconstructed";
const PHYSICAL_FEATURES_DATASET: &str = "mon_usdc_event_factor_map_physical_features";
const COST_LABELS_DATASET: &str = "mon_usdc_event_factor_map_cost_labels";
const FACTOR_CANDIDATES_DATASET: &str = "mon_usdc_event_factor_map_candidates";
const COST_LABEL_TYPE: &str = "exploratory_proxy";
const DEFAULT_ASSUMED_FEE_BPS_ONE_WAY: f64 = 30.0;
const FEE_SOURCE: &str = "assumed_default_30bps";
const RESEARCH_TIERS: [&str; 2] = ["A_observed", "B_reconstructed"];
const SLIPPAGE_BPS_GRID: [u64; 3] = [0, 25, 100];
const FACTOR_BUCKETS: usize = 5;
const NOTIONAL_BUCKETS: usize = 5;
const TARGET_KIND_MARKET_GROSS: &str = "market_gross";
const TARGET_KIND_SIDE_GROSS: &str = "side_gross";
const TARGET_KIND_NET_DIAGNOSTIC: &str = "net_diagnostic";
const EVALUATION_FAMILY_GROSS_FACTOR_MAP: &str = "gross_factor_map";
const EVALUATION_FAMILY_TRADABILITY_DIAGNOSTIC: &str = "tradability_diagnostic";
const MECHANICAL_NET_LABEL_FACTORS: [&str; 7] = [
    "gas_over_quote_abs",
    "gas_pressure",
    "log1p_quote_abs",
    "sqrt_quote_abs",
    "quote_abs_over_liquidity",
    "quote_abs_over_log_liquidity",
    "liquidity_pressure",
];

const HORIZONS: [(&str, &str); 5] = [
    ("5m", "fwd_return_5m"),
    ("15m", "fwd_return_15m"),
    ("1h", "fwd_return_1h"),
    ("3h", "fwd_return_3h"),
    ("6h", "fwd_return_6h"),
];

const FACTOR_NAMES: [&str; 21] = [
    "log1p_quote_abs",
    "sqrt_quote_abs",
    "signed_quote_flow",
    "signed_quote_flow_over_log_abs",
    "signed_quote_flow_times_log_abs",
    "quote_abs_over_liquidity",
    "liquidity_pressure",
    "flow_over_liquidity",
    "flow_over_sqrt_liquidity",
    "dislocation_over_vol_1h",
    "dislocation_over_vol_6h",
    "dislocation_over_log_quote_abs",
    "age_times_dislocation",
    "gas_over_quote_abs",
    "gas_pressure",
    "quote_abs_over_log_liquidity",
    "crowding",
    "same_block_event_count",
    "pool_quote_hhi",
    "trailing_realized_vol_1h",
    "trailing_realized_vol_6h",
];

#[derive(Debug, Clone)]
pub struct EventFactorSearchConfig {
    pub data_root: PathBuf,
    pub source_run_tag: String,
    pub run_tag: String,
    pub date_dir: PathBuf,
    pub docs_dir: PathBuf,
    pub assumed_fee_bps_one_way: f64,
    pub progress_interval: usize,
    pub eval_workers: usize,
}

impl Default for EventFactorSearchConfig {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_DATA_ROOT),
            source_run_tag: DEFAULT_FACTOR_SOURCE_RUN_TAG.to_string(),
            run_tag: DEFAULT_FACTOR_SEARCH_RUN_TAG.to_string(),
            date_dir: PathBuf::from("date"),
            docs_dir: PathBuf::from("docs"),
            assumed_fee_bps_one_way: DEFAULT_ASSUMED_FEE_BPS_ONE_WAY,
            progress_interval: DEFAULT_PROGRESS_INTERVAL,
            eval_workers: 0,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct EventFactorSearchSummary {
    pub data_root: String,
    pub run_tag: String,
    pub source_run_tag: String,
    pub executable_path: String,
    pub exploratory_only: bool,
    pub gross_factor_map_written: bool,
    pub gross_factor_map_target_kinds: Vec<String>,
    pub tradability_diagnostics_written: bool,
    pub mechanical_net_label_factors: Vec<String>,
    pub source_inputs: SourceInputSummary,
    pub coverage: FactorSearchCoverage,
    pub cost_assumption: CostAssumptionSummary,
    pub cache_reuse: FactorSearchCacheReuse,
    pub requested_eval_workers: usize,
    pub eval_workers: usize,
    pub stage_timings: Vec<StageTimingRow>,
    pub output_rows: FactorSearchOutputRows,
    pub outputs: EventFactorSearchOutputPaths,
}

#[derive(Debug, Serialize)]
pub struct SourceInputSummary {
    pub execution_feature_files: Vec<String>,
    pub tx_path_files: Vec<String>,
    pub pool_state_files: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct FactorSearchCoverage {
    pub execution_rows: u64,
    pub research_sample_rows: u64,
    pub coverage_only_rows: u64,
    pub quality_tier_counts: Vec<CountRow>,
    pub source_run_tag_checked: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct CountRow {
    pub label: String,
    pub rows: u64,
}

#[derive(Debug, Serialize)]
pub struct CostAssumptionSummary {
    pub cost_label_type: String,
    pub assumed_fee_bps_one_way: f64,
    pub fee_source: String,
    pub slippage_bps_grid: Vec<u64>,
    pub net_formula: String,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct FactorSearchCacheReuse {
    pub physical_features: bool,
    pub cost_labels: bool,
    pub factor_candidates: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct StageTimingRow {
    pub stage: String,
    pub elapsed_ms: u64,
    pub reused_cache: bool,
}

#[derive(Debug, Serialize)]
pub struct FactorSearchOutputRows {
    pub physical_features: usize,
    pub cost_labels: usize,
    pub factor_candidates: usize,
    pub expression_summary: usize,
    pub tradability_diagnostics: usize,
    pub factor_role_summary: usize,
    pub stability: usize,
    pub bucket_profiles: usize,
    pub split_summary: usize,
}

#[derive(Debug, Serialize)]
pub struct EventFactorSearchOutputPaths {
    pub physical_features: String,
    pub cost_labels: String,
    pub factor_candidates: String,
    pub expression_summary_csv: String,
    pub tradability_diagnostics_csv: String,
    pub factor_role_summary_csv: String,
    pub stability_csv: String,
    pub bucket_profiles_csv: String,
    pub split_summary_csv: String,
    pub completion_json: String,
    pub report: String,
}

#[derive(Debug, Clone)]
struct ExecutionEventRow {
    block_number: u64,
    timestamp: i64,
    event_time_utc: String,
    date_utc: String,
    hour_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    base_abs: Option<f64>,
    quote_abs: Option<f64>,
    price_quote_per_base: Option<f64>,
    receipt_gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
    base_fee_per_gas: Option<u64>,
    same_block_event_count: u64,
    fwd_return_5m: Option<f64>,
    fwd_return_15m: Option<f64>,
    fwd_return_1h: Option<f64>,
    fwd_return_3h: Option<f64>,
    fwd_return_6h: Option<f64>,
    pool_dislocation_bps: Option<f64>,
    tx_path_source: String,
    tx_path_confidence: String,
    pool_pre_state_age_blocks: Option<u64>,
    trace_path_class: String,
    trace_source: String,
    trace_confidence: String,
    quality_tier: String,
    usable_for_execution_research: bool,
}

#[derive(Debug, Clone)]
struct TxPathRow {
    transaction_hash: String,
    pool_count: u64,
    swap_count: u64,
    tx_path_source: String,
    tx_path_confidence: String,
}

#[derive(Debug, Clone)]
struct PoolStateProxyRow {
    key: EventKey,
    event_state_source: String,
    event_state_confidence: String,
    pre_state_age_blocks: Option<u64>,
    liquidity_pressure: Option<f64>,
}

#[derive(Debug, Clone, Eq)]
struct EventKey {
    block_number: u64,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
}

impl PartialEq for EventKey {
    fn eq(&self, other: &Self) -> bool {
        self.block_number == other.block_number
            && self.transaction_hash == other.transaction_hash
            && self.log_index == other.log_index
            && self.pool_address == other.pool_address
    }
}

impl Hash for EventKey {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.block_number.hash(state);
        self.transaction_hash.hash(state);
        self.log_index.hash(state);
        self.pool_address.hash(state);
    }
}

#[derive(Debug, Clone, Serialize)]
struct PhysicalFeatureRow {
    run_tag: String,
    source_run_tag: String,
    block_number: u64,
    event_time_utc: String,
    date_utc: String,
    hour_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    quality_tier: String,
    research_sample_included: bool,
    base_abs: Option<f64>,
    quote_abs: Option<f64>,
    price_quote_per_base: Option<f64>,
    signed_quote_flow: Option<f64>,
    signed_quote_flow_source: String,
    signed_quote_flow_confidence: String,
    liquidity_pressure: Option<f64>,
    liquidity_pressure_source: String,
    liquidity_pressure_confidence: String,
    gas_pressure: Option<f64>,
    roundtrip_gas_return_proxy: Option<f64>,
    gas_pressure_source: String,
    gas_pressure_confidence: String,
    crowding: Option<f64>,
    crowding_source: String,
    crowding_confidence: String,
    dislocation_return: Option<f64>,
    dislocation_source: String,
    dislocation_confidence: String,
    pool_pre_state_age_blocks: Option<u64>,
    pool_quote_hhi: Option<f64>,
    pool_quote_hhi_source: String,
    pool_quote_hhi_confidence: String,
    trailing_realized_vol_1h: Option<f64>,
    trailing_realized_vol_6h: Option<f64>,
    volatility_source: String,
    volatility_confidence: String,
    tx_pool_count: Option<u64>,
    tx_swap_count: Option<u64>,
    tx_path_source: String,
    tx_path_confidence: String,
    receipt_gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
    base_fee_per_gas: Option<u64>,
    same_block_event_count: u64,
    trace_path_class: String,
    trace_source: String,
    trace_confidence: String,
}

#[derive(Debug, Clone, Serialize)]
struct CostLabelRow {
    run_tag: String,
    source_run_tag: String,
    block_number: u64,
    event_time_utc: String,
    date_utc: String,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    direction: String,
    quality_tier: String,
    cost_label_type: String,
    assumed_fee_bps_one_way: f64,
    fee_source: String,
    roundtrip_gas_return_proxy: Option<f64>,
    roundtrip_gas_source: String,
    market_gross_return_5m: Option<f64>,
    market_gross_return_15m: Option<f64>,
    market_gross_return_1h: Option<f64>,
    market_gross_return_3h: Option<f64>,
    market_gross_return_6h: Option<f64>,
    side_gross_return_5m: Option<f64>,
    side_gross_return_15m: Option<f64>,
    side_gross_return_1h: Option<f64>,
    side_gross_return_3h: Option<f64>,
    side_gross_return_6h: Option<f64>,
    net_return_5m_slip0bps: Option<f64>,
    net_return_5m_slip25bps: Option<f64>,
    net_return_5m_slip100bps: Option<f64>,
    net_return_15m_slip0bps: Option<f64>,
    net_return_15m_slip25bps: Option<f64>,
    net_return_15m_slip100bps: Option<f64>,
    net_return_1h_slip0bps: Option<f64>,
    net_return_1h_slip25bps: Option<f64>,
    net_return_1h_slip100bps: Option<f64>,
    net_return_3h_slip0bps: Option<f64>,
    net_return_3h_slip25bps: Option<f64>,
    net_return_3h_slip100bps: Option<f64>,
    net_return_6h_slip0bps: Option<f64>,
    net_return_6h_slip25bps: Option<f64>,
    net_return_6h_slip100bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorCandidateRow {
    run_tag: String,
    source_run_tag: String,
    block_number: u64,
    event_time_utc: String,
    date_utc: String,
    split: String,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    quality_tier: String,
    volatility_regime: String,
    quote_notional_bucket: String,
    quote_abs: Option<f64>,
    signed_quote_flow: Option<f64>,
    liquidity_proxy: Option<f64>,
    log1p_quote_abs: Option<f64>,
    sqrt_quote_abs: Option<f64>,
    signed_quote_flow_over_log_abs: Option<f64>,
    signed_quote_flow_times_log_abs: Option<f64>,
    quote_abs_over_liquidity: Option<f64>,
    flow_over_liquidity: Option<f64>,
    flow_over_sqrt_liquidity: Option<f64>,
    dislocation_over_vol_1h: Option<f64>,
    dislocation_over_vol_6h: Option<f64>,
    gas_over_quote_abs: Option<f64>,
    quote_abs_over_log_liquidity: Option<f64>,
    age_times_dislocation: Option<f64>,
    dislocation_over_log_quote_abs: Option<f64>,
    liquidity_pressure: Option<f64>,
    gas_pressure: Option<f64>,
    crowding: Option<f64>,
    pool_quote_hhi: Option<f64>,
    trailing_realized_vol_1h: Option<f64>,
    trailing_realized_vol_6h: Option<f64>,
    same_block_event_count: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorExpressionSummaryRow {
    validation_rank: u64,
    factor: String,
    factor_family: String,
    factor_role: String,
    target: String,
    horizon: String,
    target_kind: String,
    evaluation_family: String,
    status: String,
    discovery_n: u64,
    discovery_spearman: Option<f64>,
    discovery_top_minus_bottom: Option<f64>,
    validation_n: u64,
    validation_spearman: Option<f64>,
    validation_top_minus_bottom: Option<f64>,
    forward_n: u64,
    forward_spearman: Option<f64>,
    forward_top_minus_bottom: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorStabilityRow {
    factor: String,
    factor_family: String,
    target: String,
    target_kind: String,
    evaluation_family: String,
    split: String,
    stratum_type: String,
    stratum_value: String,
    n: u64,
    low_bucket_n: u64,
    high_bucket_n: u64,
    low_mean: Option<f64>,
    high_mean: Option<f64>,
    high_minus_low: Option<f64>,
    low_positive_rate: Option<f64>,
    high_positive_rate: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorBucketProfileRow {
    factor: String,
    factor_family: String,
    target: String,
    target_kind: String,
    evaluation_family: String,
    split: String,
    bucket: u64,
    n: u64,
    mean_target: Option<f64>,
    positive_rate: Option<f64>,
    mean_factor: Option<f64>,
    mean_quote_abs: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorSplitSummaryRow {
    split: String,
    quality_tier: String,
    rows: u64,
    unique_dates: u64,
    first_date: String,
    last_date: String,
    quote_abs_sum: f64,
}

#[derive(Debug, Clone, Serialize)]
struct FactorRoleSummaryRow {
    factor: String,
    factor_family: String,
    factor_role: String,
    gross_factor_map_allowed: bool,
    net_return_alpha_allowed: bool,
    tradability_diagnostic_allowed: bool,
    mechanical_net_label_factor: bool,
    rationale: String,
}

#[derive(Debug, Clone)]
struct TargetSpec {
    name: String,
    horizon: String,
    kind: String,
    evaluation_family: String,
}

#[derive(Debug, Clone, Default)]
struct EvalStats {
    n: u64,
    spearman: Option<f64>,
    low_bucket_n: u64,
    high_bucket_n: u64,
    low_mean: Option<f64>,
    high_mean: Option<f64>,
    high_minus_low: Option<f64>,
    low_positive_rate: Option<f64>,
    high_positive_rate: Option<f64>,
}

#[derive(Debug, Clone, Default)]
struct BucketStats {
    n: u64,
    sum_target: f64,
    positive: u64,
    sum_factor: f64,
    sum_quote_abs: f64,
}

impl BucketStats {
    fn add(&mut self, factor: f64, target: f64, quote_abs: Option<f64>) {
        self.n += 1;
        self.sum_target += target;
        self.sum_factor += factor;
        if target > 0.0 {
            self.positive += 1;
        }
        if let Some(quote_abs) = quote_abs.filter(|value| value.is_finite()) {
            self.sum_quote_abs += quote_abs;
        }
    }

    fn mean_target(&self) -> Option<f64> {
        mean_from_sum(self.sum_target, self.n)
    }

    fn positive_rate(&self) -> Option<f64> {
        if self.n == 0 {
            None
        } else {
            finite(self.positive as f64 / self.n as f64)
        }
    }

    fn mean_factor(&self) -> Option<f64> {
        mean_from_sum(self.sum_factor, self.n)
    }

    fn mean_quote_abs(&self) -> Option<f64> {
        mean_from_sum(self.sum_quote_abs, self.n)
    }
}

#[derive(Debug, Clone, Default)]
struct TopBottomAgg {
    low: BucketStats,
    high: BucketStats,
}

impl TopBottomAgg {
    fn add(&mut self, bucket: u8, factor: f64, target: f64, quote_abs: Option<f64>) {
        if bucket == 0 {
            self.low.add(factor, target, quote_abs);
        } else if bucket as usize == FACTOR_BUCKETS - 1 {
            self.high.add(factor, target, quote_abs);
        }
    }

    fn stats(&self) -> EvalStats {
        let low_mean = self.low.mean_target();
        let high_mean = self.high.mean_target();
        EvalStats {
            n: self.low.n + self.high.n,
            spearman: None,
            low_bucket_n: self.low.n,
            high_bucket_n: self.high.n,
            low_mean,
            high_mean,
            high_minus_low: high_mean
                .zip(low_mean)
                .and_then(|(high, low)| finite(high - low)),
            low_positive_rate: self.low.positive_rate(),
            high_positive_rate: self.high.positive_rate(),
        }
    }
}

pub fn run_event_factor_search(
    config: &EventFactorSearchConfig,
) -> Result<EventFactorSearchSummary> {
    if !config.assumed_fee_bps_one_way.is_finite() || config.assumed_fee_bps_one_way < 0.0 {
        bail!("assumed_fee_bps_one_way must be finite and non-negative");
    }
    std::fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    std::fs::create_dir_all(&config.docs_dir)
        .with_context(|| format!("failed to create {}", config.docs_dir.display()))?;

    let eval_workers = resolve_eval_workers(config.eval_workers);
    let mut progress = ProgressReporter::new(config.progress_interval);
    let mut stage_timings = Vec::new();
    let mut cache_reuse = FactorSearchCacheReuse::default();

    progress.begin_stage("read execution source rows", 1_800);
    let stage_start = Instant::now();
    let execution_files = source_run_tag_part_paths(
        &config.data_root,
        EXECUTION_FEATURES_DATASET,
        &config.source_run_tag,
    )?;
    let tx_path_files = source_run_tag_part_paths(
        &config.data_root,
        TX_PATH_RECONSTRUCTED_DATASET,
        &config.source_run_tag,
    )?;
    let pool_state_files = source_run_tag_part_paths(
        &config.data_root,
        POOL_STATE_RECONSTRUCTED_DATASET,
        &config.source_run_tag,
    )?;

    let physical_cache_path = cached_derived_part_path(
        &config.data_root,
        PHYSICAL_FEATURES_DATASET,
        physical_features_schema(),
        &config.run_tag,
    )?;
    let cost_cache_path = cached_derived_part_path(
        &config.data_root,
        COST_LABELS_DATASET,
        cost_labels_schema(),
        &config.run_tag,
    )?;
    let candidate_cache_path = cached_derived_part_path(
        &config.data_root,
        FACTOR_CANDIDATES_DATASET,
        factor_candidates_schema(),
        &config.run_tag,
    )?;

    let need_execution_rows = physical_cache_path.is_none() || cost_cache_path.is_none();
    let need_side_inputs = physical_cache_path.is_none();
    let execution_rows = if need_execution_rows {
        let rows = read_execution_rows(
            &execution_files,
            &config.source_run_tag,
            config.progress_interval,
        )?;
        if rows.is_empty() {
            bail!(
                "no execution rows found for source run tag {}",
                config.source_run_tag
            );
        }
        rows
    } else {
        Vec::new()
    };
    progress.finish_stage();
    stage_timings.push(stage_timing(
        "read execution source rows",
        stage_start,
        !need_execution_rows,
    ));

    progress.begin_stage("read path and pool-state source rows", 900);
    let stage_start = Instant::now();
    let (tx_path_rows, pool_state_rows) = if need_side_inputs {
        (
            read_tx_path_rows(&tx_path_files, &config.source_run_tag)?,
            read_pool_state_rows(&pool_state_files, &config.source_run_tag)?,
        )
    } else {
        (Vec::new(), Vec::new())
    };
    progress.finish_stage();
    stage_timings.push(stage_timing(
        "read path and pool-state source rows",
        stage_start,
        !need_side_inputs,
    ));

    progress.begin_stage("physical features", 1_300);
    let stage_start = Instant::now();
    let physical_rows = if let Some(path) = physical_cache_path.as_ref() {
        cache_reuse.physical_features = true;
        eprintln!(
            "[mon_usdc_event_factor_search] cache hit: {}",
            path.display()
        );
        read_physical_feature_rows(path, &config.run_tag, &config.source_run_tag)?
    } else {
        build_physical_features(
            &execution_rows,
            &tx_path_rows,
            &pool_state_rows,
            &config.run_tag,
            &config.source_run_tag,
        )?
    };
    if physical_rows.is_empty() {
        bail!("physical feature stage produced no rows");
    }
    progress.finish_stage();
    stage_timings.push(stage_timing(
        "physical features",
        stage_start,
        cache_reuse.physical_features,
    ));

    let split_by_date = chronological_split_map(
        physical_rows
            .iter()
            .filter(|row| row.research_sample_included)
            .map(|row| row.date_utc.clone()),
    );
    let quote_thresholds = thresholds_from_physical_split(
        &physical_rows,
        &split_by_date,
        |row| row.quote_abs,
        NOTIONAL_BUCKETS,
    );
    let vol_thresholds = thresholds_from_physical_split(
        &physical_rows,
        &split_by_date,
        |row| row.trailing_realized_vol_1h,
        3,
    );

    progress.begin_stage("cost labels", 900);
    let stage_start = Instant::now();
    let cost_rows = if let Some(path) = cost_cache_path.as_ref() {
        cache_reuse.cost_labels = true;
        eprintln!(
            "[mon_usdc_event_factor_search] cache hit: {}",
            path.display()
        );
        read_cost_label_rows(
            path,
            &config.run_tag,
            &config.source_run_tag,
            config.assumed_fee_bps_one_way,
        )?
    } else {
        if execution_rows.len() != physical_rows.len() {
            bail!(
                "cannot build cost labels from mismatched source/cache rows: execution={} physical={}",
                execution_rows.len(),
                physical_rows.len()
            );
        }
        build_cost_labels(
            &execution_rows,
            &physical_rows,
            &config.run_tag,
            &config.source_run_tag,
            config.assumed_fee_bps_one_way,
        )
    };
    progress.finish_stage();
    stage_timings.push(stage_timing(
        "cost labels",
        stage_start,
        cache_reuse.cost_labels,
    ));

    progress.begin_stage("factor candidates", 900);
    let stage_start = Instant::now();
    let candidate_rows = if let Some(path) = candidate_cache_path.as_ref() {
        cache_reuse.factor_candidates = true;
        eprintln!(
            "[mon_usdc_event_factor_search] cache hit: {}",
            path.display()
        );
        read_factor_candidate_rows(path, &config.run_tag, &config.source_run_tag)?
    } else {
        build_factor_candidates(
            &physical_rows,
            &split_by_date,
            &quote_thresholds,
            &vol_thresholds,
            &config.run_tag,
            &config.source_run_tag,
        )
    };
    progress.finish_stage();
    stage_timings.push(stage_timing(
        "factor candidates",
        stage_start,
        cache_reuse.factor_candidates,
    ));

    if cost_rows.len() != candidate_rows.len() {
        bail!(
            "internal row mismatch: cost labels {} vs factor candidates {}",
            cost_rows.len(),
            candidate_rows.len()
        );
    }

    progress.begin_stage("evaluate factor expressions", 2_600);
    let stage_start = Instant::now();
    let targets = target_specs();
    let (expression_summary, tradability_diagnostics, stability_rows, bucket_profiles) =
        evaluate_factor_candidates(&candidate_rows, &cost_rows, &targets, eval_workers);
    let factor_role_summary = build_factor_role_summary();
    let split_summary = build_split_summary(&candidate_rows);
    if expression_summary.is_empty() {
        bail!("factor map search produced no gross summary rows");
    }
    if tradability_diagnostics.is_empty() {
        bail!("factor expression search produced no tradability diagnostic rows");
    }
    progress.finish_stage();
    stage_timings.push(stage_timing(
        "evaluate factor expressions",
        stage_start,
        false,
    ));

    progress.begin_stage("write outputs", 1_600);
    let stage_start = Instant::now();
    let physical_path = if let Some(path) = physical_cache_path {
        path
    } else {
        write_physical_features_parquet(&config.data_root, &physical_rows, &config.run_tag)?
    };
    let cost_path = if let Some(path) = cost_cache_path {
        path
    } else {
        write_cost_labels_parquet(&config.data_root, &cost_rows, &config.run_tag)?
    };
    let candidate_path = if let Some(path) = candidate_cache_path {
        path
    } else {
        write_factor_candidates_parquet(&config.data_root, &candidate_rows, &config.run_tag)?
    };

    let outputs = build_output_paths(config, &physical_path, &cost_path, &candidate_path);
    write_csv(
        Path::new(&outputs.expression_summary_csv),
        &expression_summary,
    )?;
    write_csv(
        Path::new(&outputs.tradability_diagnostics_csv),
        &tradability_diagnostics,
    )?;
    write_csv(
        Path::new(&outputs.factor_role_summary_csv),
        &factor_role_summary,
    )?;
    write_csv(Path::new(&outputs.stability_csv), &stability_rows)?;
    write_csv(Path::new(&outputs.bucket_profiles_csv), &bucket_profiles)?;
    write_csv(Path::new(&outputs.split_summary_csv), &split_summary)?;
    assert_no_bad_float_text(Path::new(&outputs.expression_summary_csv))?;
    assert_no_bad_float_text(Path::new(&outputs.tradability_diagnostics_csv))?;
    assert_no_bad_float_text(Path::new(&outputs.factor_role_summary_csv))?;
    assert_no_bad_float_text(Path::new(&outputs.stability_csv))?;
    assert_no_bad_float_text(Path::new(&outputs.bucket_profiles_csv))?;
    assert_no_bad_float_text(Path::new(&outputs.split_summary_csv))?;
    progress.finish_stage();
    progress.finish_all();
    stage_timings.push(stage_timing("write outputs", stage_start, false));

    let coverage = build_coverage_from_physical(&physical_rows);
    let summary = EventFactorSearchSummary {
        data_root: path_string(&config.data_root),
        run_tag: config.run_tag.clone(),
        source_run_tag: config.source_run_tag.clone(),
        executable_path: current_executable_path(),
        exploratory_only: true,
        gross_factor_map_written: true,
        gross_factor_map_target_kinds: vec![
            TARGET_KIND_MARKET_GROSS.to_string(),
            TARGET_KIND_SIDE_GROSS.to_string(),
        ],
        tradability_diagnostics_written: true,
        mechanical_net_label_factors: MECHANICAL_NET_LABEL_FACTORS
            .iter()
            .map(|factor| (*factor).to_string())
            .collect(),
        source_inputs: SourceInputSummary {
            execution_feature_files: execution_files
                .iter()
                .map(|path| path_string(path))
                .collect(),
            tx_path_files: tx_path_files.iter().map(|path| path_string(path)).collect(),
            pool_state_files: pool_state_files
                .iter()
                .map(|path| path_string(path))
                .collect(),
        },
        coverage,
        cost_assumption: CostAssumptionSummary {
            cost_label_type: COST_LABEL_TYPE.to_string(),
            assumed_fee_bps_one_way: config.assumed_fee_bps_one_way,
            fee_source: FEE_SOURCE.to_string(),
            slippage_bps_grid: SLIPPAGE_BPS_GRID.to_vec(),
            net_formula:
                "side_gross - 2 * assumed_fee_bps - roundtrip_gas_return_proxy - 2 * slippage_bps"
                    .to_string(),
        },
        cache_reuse,
        requested_eval_workers: config.eval_workers,
        eval_workers,
        stage_timings,
        output_rows: FactorSearchOutputRows {
            physical_features: physical_rows.len(),
            cost_labels: cost_rows.len(),
            factor_candidates: candidate_rows.len(),
            expression_summary: expression_summary.len(),
            tradability_diagnostics: tradability_diagnostics.len(),
            factor_role_summary: factor_role_summary.len(),
            stability: stability_rows.len(),
            bucket_profiles: bucket_profiles.len(),
            split_summary: split_summary.len(),
        },
        outputs,
    };
    write_json(Path::new(&summary.outputs.completion_json), &summary)?;
    write_factor_search_report(&summary, &expression_summary, &tradability_diagnostics)?;
    Ok(summary)
}

fn build_output_paths(
    config: &EventFactorSearchConfig,
    physical_path: &Path,
    cost_path: &Path,
    candidate_path: &Path,
) -> EventFactorSearchOutputPaths {
    EventFactorSearchOutputPaths {
        physical_features: path_string(physical_path),
        cost_labels: path_string(cost_path),
        factor_candidates: path_string(candidate_path),
        expression_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_factor_expression_summary_{}.csv",
            config.run_tag
        ))),
        tradability_diagnostics_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_tradability_diagnostics_{}.csv",
            config.run_tag
        ))),
        factor_role_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_factor_role_summary_{}.csv",
            config.run_tag
        ))),
        stability_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_factor_stability_{}.csv",
            config.run_tag
        ))),
        bucket_profiles_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_factor_bucket_profiles_{}.csv",
            config.run_tag
        ))),
        split_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_factor_split_summary_{}.csv",
            config.run_tag
        ))),
        completion_json: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_factor_search_completion_{}.json",
            config.run_tag
        ))),
        report: path_string(
            &config
                .docs_dir
                .join("markets")
                .join("mon-usdc")
                .join("v1-factor-map.md"),
        ),
    }
}

#[allow(dead_code)]
fn build_coverage(
    execution_rows: &[ExecutionEventRow],
    physical_rows: &[PhysicalFeatureRow],
) -> FactorSearchCoverage {
    let mut counts = BTreeMap::<String, u64>::new();
    for row in execution_rows {
        *counts.entry(row.quality_tier.clone()).or_default() += 1;
    }
    let research_sample_rows = physical_rows
        .iter()
        .filter(|row| row.research_sample_included)
        .count() as u64;
    FactorSearchCoverage {
        execution_rows: execution_rows.len() as u64,
        research_sample_rows,
        coverage_only_rows: execution_rows.len() as u64 - research_sample_rows,
        quality_tier_counts: counts
            .into_iter()
            .map(|(label, rows)| CountRow { label, rows })
            .collect(),
        source_run_tag_checked: true,
    }
}

fn build_coverage_from_physical(physical_rows: &[PhysicalFeatureRow]) -> FactorSearchCoverage {
    let mut counts = BTreeMap::<String, u64>::new();
    for row in physical_rows {
        *counts.entry(row.quality_tier.clone()).or_default() += 1;
    }
    let research_sample_rows = physical_rows
        .iter()
        .filter(|row| row.research_sample_included)
        .count() as u64;
    FactorSearchCoverage {
        execution_rows: physical_rows.len() as u64,
        research_sample_rows,
        coverage_only_rows: physical_rows.len() as u64 - research_sample_rows,
        quality_tier_counts: counts
            .into_iter()
            .map(|(label, rows)| CountRow { label, rows })
            .collect(),
        source_run_tag_checked: true,
    }
}

fn resolve_eval_workers(requested: usize) -> usize {
    if requested > 0 {
        return requested;
    }
    thread::available_parallelism()
        .map(|cores| cores.get().clamp(1, 2))
        .unwrap_or(1)
}

fn stage_timing(stage: &str, started: Instant, reused_cache: bool) -> StageTimingRow {
    StageTimingRow {
        stage: stage.to_string(),
        elapsed_ms: started.elapsed().as_millis().min(u64::MAX as u128) as u64,
        reused_cache,
    }
}

struct ProgressReporter {
    started: Instant,
    total_units: u64,
    completed_units: u64,
    stage_base_units: u64,
    stage_units: u64,
    stage_name: String,
    progress_interval: usize,
    last_percent_x100: u64,
}

impl ProgressReporter {
    fn new(progress_interval: usize) -> Self {
        Self {
            started: Instant::now(),
            total_units: 10_000,
            completed_units: 0,
            stage_base_units: 0,
            stage_units: 0,
            stage_name: "starting".to_string(),
            progress_interval,
            last_percent_x100: 0,
        }
    }

    fn begin_stage(&mut self, stage_name: &str, stage_units: u64) {
        self.stage_base_units = self.completed_units;
        self.stage_units = stage_units;
        self.stage_name = stage_name.to_string();
        self.emit();
    }

    fn finish_stage(&mut self) {
        self.completed_units = (self.stage_base_units + self.stage_units).min(self.total_units);
        self.emit();
    }

    #[allow(dead_code)]
    fn set_stage_progress(&mut self, done: u64, total: u64) {
        if total == 0 {
            return;
        }
        let stage_done = self.stage_units.saturating_mul(done.min(total)) / total;
        let next = (self.stage_base_units + stage_done).min(self.total_units);
        if next >= self.completed_units {
            self.completed_units = next;
        }
        if self.progress_interval == 0 || done == total || done % self.progress_interval as u64 == 0
        {
            self.emit();
        }
    }

    fn finish_all(&mut self) {
        self.stage_name = "complete".to_string();
        self.completed_units = self.total_units;
        self.emit();
    }

    fn percent_x100(&self) -> u64 {
        self.completed_units.saturating_mul(10_000) / self.total_units.max(1)
    }

    fn emit(&mut self) {
        let percent_x100 = self.percent_x100().max(self.last_percent_x100);
        self.last_percent_x100 = percent_x100;
        let percent = percent_x100 as f64 / 100.0;
        let elapsed = self.started.elapsed();
        let eta = if self.completed_units == 0 || self.completed_units >= self.total_units {
            Duration::ZERO
        } else {
            let elapsed_secs = elapsed.as_secs_f64();
            let remaining = elapsed_secs * (self.total_units - self.completed_units) as f64
                / self.completed_units as f64;
            Duration::from_secs_f64(remaining.max(0.0))
        };
        eprintln!(
            "[mon_usdc_event_factor_search] progress={percent:.2}% stage=\"{}\" units={}/{} elapsed={} eta={}",
            self.stage_name,
            self.completed_units,
            self.total_units,
            format_duration(elapsed),
            format_duration(eta)
        );
    }
}

fn format_duration(duration: Duration) -> String {
    let secs = duration.as_secs();
    let hours = secs / 3600;
    let minutes = (secs % 3600) / 60;
    let seconds = secs % 60;
    format!("{hours:02}:{minutes:02}:{seconds:02}")
}

fn build_physical_features(
    execution_rows: &[ExecutionEventRow],
    tx_path_rows: &[TxPathRow],
    pool_state_rows: &[PoolStateProxyRow],
    run_tag: &str,
    source_run_tag: &str,
) -> Result<Vec<PhysicalFeatureRow>> {
    let tx_by_hash = tx_path_rows
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();
    let pool_state_by_key = pool_state_rows
        .iter()
        .map(|row| (row.key.clone(), row))
        .collect::<HashMap<_, _>>();
    let pool_hhi_by_hour = hourly_pool_quote_hhi(execution_rows);
    let vol_by_minute = minute_realized_volatility(execution_rows);

    let mut rows = Vec::with_capacity(execution_rows.len());
    for event in execution_rows {
        let key = EventKey {
            block_number: event.block_number,
            transaction_hash: event.transaction_hash.clone(),
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
        };
        let tx = tx_by_hash.get(&event.transaction_hash).copied();
        let state = pool_state_by_key.get(&key).copied();
        let minute = floor_to_minute(event.timestamp);
        let vol = vol_by_minute.get(&minute).copied().unwrap_or((None, None));
        let signed_quote_flow = signed_quote_flow(&event.direction, event.quote_abs);
        let (gas_pressure, roundtrip_gas_return_proxy) = gas_return_proxies(
            event.receipt_gas_used,
            event.effective_gas_price,
            event.price_quote_per_base,
            event.quote_abs,
        );
        let gas_available = gas_pressure.is_some();
        let liquidity_pressure = state.and_then(|row| row.liquidity_pressure);
        let liquidity_source = if liquidity_pressure.is_some() {
            state
                .map(|row| row.event_state_source.clone())
                .unwrap_or_else(|| "unavailable".to_string())
        } else {
            "unavailable".to_string()
        };
        let liquidity_confidence = if liquidity_pressure.is_some() {
            state
                .map(|row| row.event_state_confidence.clone())
                .unwrap_or_else(|| "none".to_string())
        } else {
            "none".to_string()
        };
        let research_sample_included =
            research_sample_included(&event.quality_tier) && event.usable_for_execution_research;

        rows.push(PhysicalFeatureRow {
            run_tag: run_tag.to_string(),
            source_run_tag: source_run_tag.to_string(),
            block_number: event.block_number,
            event_time_utc: event.event_time_utc.clone(),
            date_utc: event.date_utc.clone(),
            hour_utc: event.hour_utc.clone(),
            transaction_hash: event.transaction_hash.clone(),
            transaction_index: event.transaction_index,
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
            dex_id: event.dex_id.clone(),
            family: event.family.clone(),
            direction: event.direction.clone(),
            quality_tier: event.quality_tier.clone(),
            research_sample_included,
            base_abs: event.base_abs,
            quote_abs: event.quote_abs,
            price_quote_per_base: event.price_quote_per_base,
            signed_quote_flow,
            signed_quote_flow_source: "event_execution_direction_quote_abs".to_string(),
            signed_quote_flow_confidence: if signed_quote_flow.is_some() {
                "high".to_string()
            } else {
                "none".to_string()
            },
            liquidity_pressure,
            liquidity_pressure_source: liquidity_source,
            liquidity_pressure_confidence: liquidity_confidence,
            gas_pressure,
            roundtrip_gas_return_proxy,
            gas_pressure_source: if gas_available {
                "receipt_gas_price_quote_proxy".to_string()
            } else {
                "unavailable".to_string()
            },
            gas_pressure_confidence: if gas_available {
                "medium".to_string()
            } else {
                "none".to_string()
            },
            crowding: finite(event.same_block_event_count as f64),
            crowding_source: "event_block_same_block_count".to_string(),
            crowding_confidence: "high".to_string(),
            dislocation_return: event
                .pool_dislocation_bps
                .and_then(|value| finite(value / 10_000.0)),
            dislocation_source: if event.pool_dislocation_bps.is_some() {
                "cross_pool_dislocation_proxy".to_string()
            } else {
                "unavailable".to_string()
            },
            dislocation_confidence: if event.pool_dislocation_bps.is_some() {
                "medium".to_string()
            } else {
                "none".to_string()
            },
            pool_pre_state_age_blocks: state
                .and_then(|row| row.pre_state_age_blocks)
                .or(event.pool_pre_state_age_blocks),
            pool_quote_hhi: pool_hhi_by_hour.get(&event.hour_utc).copied().flatten(),
            pool_quote_hhi_source: "hourly_event_pool_quote_distribution".to_string(),
            pool_quote_hhi_confidence: "high".to_string(),
            trailing_realized_vol_1h: vol.0,
            trailing_realized_vol_6h: vol.1,
            volatility_source: "minute_vwap_from_execution_events".to_string(),
            volatility_confidence: if vol.0.is_some() || vol.1.is_some() {
                "medium".to_string()
            } else {
                "none".to_string()
            },
            tx_pool_count: tx.map(|row| row.pool_count),
            tx_swap_count: tx.map(|row| row.swap_count),
            tx_path_source: tx
                .map(|row| row.tx_path_source.clone())
                .unwrap_or_else(|| event.tx_path_source.clone()),
            tx_path_confidence: tx
                .map(|row| row.tx_path_confidence.clone())
                .unwrap_or_else(|| event.tx_path_confidence.clone()),
            receipt_gas_used: event.receipt_gas_used,
            effective_gas_price: event.effective_gas_price,
            base_fee_per_gas: event.base_fee_per_gas,
            same_block_event_count: event.same_block_event_count,
            trace_path_class: event.trace_path_class.clone(),
            trace_source: event.trace_source.clone(),
            trace_confidence: event.trace_confidence.clone(),
        });
    }
    Ok(rows)
}

fn build_cost_labels(
    execution_rows: &[ExecutionEventRow],
    physical_rows: &[PhysicalFeatureRow],
    run_tag: &str,
    source_run_tag: &str,
    assumed_fee_bps_one_way: f64,
) -> Vec<CostLabelRow> {
    let mut rows = Vec::new();
    for (event, physical) in execution_rows.iter().zip(physical_rows) {
        if !physical.research_sample_included {
            continue;
        }
        let market_5m = market_gross_return(event.fwd_return_5m);
        let market_15m = market_gross_return(event.fwd_return_15m);
        let market_1h = market_gross_return(event.fwd_return_1h);
        let market_3h = market_gross_return(event.fwd_return_3h);
        let market_6h = market_gross_return(event.fwd_return_6h);
        let gross_5m = side_gross_return(&event.direction, event.fwd_return_5m);
        let gross_15m = side_gross_return(&event.direction, event.fwd_return_15m);
        let gross_1h = side_gross_return(&event.direction, event.fwd_return_1h);
        let gross_3h = side_gross_return(&event.direction, event.fwd_return_3h);
        let gross_6h = side_gross_return(&event.direction, event.fwd_return_6h);
        let gas = physical.roundtrip_gas_return_proxy;
        rows.push(CostLabelRow {
            run_tag: run_tag.to_string(),
            source_run_tag: source_run_tag.to_string(),
            block_number: event.block_number,
            event_time_utc: event.event_time_utc.clone(),
            date_utc: event.date_utc.clone(),
            transaction_hash: event.transaction_hash.clone(),
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
            direction: event.direction.clone(),
            quality_tier: event.quality_tier.clone(),
            cost_label_type: COST_LABEL_TYPE.to_string(),
            assumed_fee_bps_one_way,
            fee_source: FEE_SOURCE.to_string(),
            roundtrip_gas_return_proxy: gas,
            roundtrip_gas_source: if gas.is_some() {
                "receipt_gas_price_quote_proxy".to_string()
            } else {
                "unavailable".to_string()
            },
            market_gross_return_5m: market_5m,
            market_gross_return_15m: market_15m,
            market_gross_return_1h: market_1h,
            market_gross_return_3h: market_3h,
            market_gross_return_6h: market_6h,
            side_gross_return_5m: gross_5m,
            side_gross_return_15m: gross_15m,
            side_gross_return_1h: gross_1h,
            side_gross_return_3h: gross_3h,
            side_gross_return_6h: gross_6h,
            net_return_5m_slip0bps: net_label(gross_5m, assumed_fee_bps_one_way, gas, 0.0),
            net_return_5m_slip25bps: net_label(gross_5m, assumed_fee_bps_one_way, gas, 25.0),
            net_return_5m_slip100bps: net_label(gross_5m, assumed_fee_bps_one_way, gas, 100.0),
            net_return_15m_slip0bps: net_label(gross_15m, assumed_fee_bps_one_way, gas, 0.0),
            net_return_15m_slip25bps: net_label(gross_15m, assumed_fee_bps_one_way, gas, 25.0),
            net_return_15m_slip100bps: net_label(gross_15m, assumed_fee_bps_one_way, gas, 100.0),
            net_return_1h_slip0bps: net_label(gross_1h, assumed_fee_bps_one_way, gas, 0.0),
            net_return_1h_slip25bps: net_label(gross_1h, assumed_fee_bps_one_way, gas, 25.0),
            net_return_1h_slip100bps: net_label(gross_1h, assumed_fee_bps_one_way, gas, 100.0),
            net_return_3h_slip0bps: net_label(gross_3h, assumed_fee_bps_one_way, gas, 0.0),
            net_return_3h_slip25bps: net_label(gross_3h, assumed_fee_bps_one_way, gas, 25.0),
            net_return_3h_slip100bps: net_label(gross_3h, assumed_fee_bps_one_way, gas, 100.0),
            net_return_6h_slip0bps: net_label(gross_6h, assumed_fee_bps_one_way, gas, 0.0),
            net_return_6h_slip25bps: net_label(gross_6h, assumed_fee_bps_one_way, gas, 25.0),
            net_return_6h_slip100bps: net_label(gross_6h, assumed_fee_bps_one_way, gas, 100.0),
        });
    }
    rows
}

fn build_factor_candidates(
    physical_rows: &[PhysicalFeatureRow],
    split_by_date: &BTreeMap<String, String>,
    quote_thresholds: &[f64],
    vol_thresholds: &[f64],
    run_tag: &str,
    source_run_tag: &str,
) -> Vec<FactorCandidateRow> {
    let mut rows = Vec::new();
    for row in physical_rows {
        if !row.research_sample_included {
            continue;
        }
        let split = split_by_date
            .get(&row.date_utc)
            .cloned()
            .unwrap_or_else(|| "unassigned".to_string());
        let liquidity_proxy = infer_liquidity_proxy(row.quote_abs, row.liquidity_pressure);
        let log_quote = row.quote_abs.and_then(log1p_positive);
        let signed_flow = row.signed_quote_flow;
        let dislocation = row.dislocation_return;
        let age = row.pool_pre_state_age_blocks.map(|value| value as f64);
        rows.push(FactorCandidateRow {
            run_tag: run_tag.to_string(),
            source_run_tag: source_run_tag.to_string(),
            block_number: row.block_number,
            event_time_utc: row.event_time_utc.clone(),
            date_utc: row.date_utc.clone(),
            split,
            transaction_hash: row.transaction_hash.clone(),
            log_index: row.log_index,
            pool_address: row.pool_address.clone(),
            dex_id: row.dex_id.clone(),
            family: row.family.clone(),
            direction: row.direction.clone(),
            quality_tier: row.quality_tier.clone(),
            volatility_regime: volatility_regime(row.trailing_realized_vol_1h, vol_thresholds),
            quote_notional_bucket: notional_bucket(row.quote_abs, quote_thresholds),
            quote_abs: row.quote_abs,
            signed_quote_flow: signed_flow,
            liquidity_proxy,
            log1p_quote_abs: log_quote,
            sqrt_quote_abs: row.quote_abs.and_then(sqrt_positive),
            signed_quote_flow_over_log_abs: signed_flow
                .zip(log_quote)
                .and_then(|(flow, log_abs)| safe_div(flow, log_abs)),
            signed_quote_flow_times_log_abs: signed_flow
                .zip(log_quote)
                .and_then(|(flow, log_abs)| finite(flow * log_abs)),
            quote_abs_over_liquidity: row.liquidity_pressure,
            flow_over_liquidity: signed_flow
                .zip(liquidity_proxy)
                .and_then(|(flow, liquidity)| safe_div(flow, liquidity)),
            flow_over_sqrt_liquidity: signed_flow
                .zip(liquidity_proxy.and_then(sqrt_positive))
                .and_then(|(flow, sqrt_liquidity)| safe_div(flow, sqrt_liquidity)),
            dislocation_over_vol_1h: dislocation
                .zip(row.trailing_realized_vol_1h)
                .and_then(|(dislocation, vol)| safe_div(dislocation, vol)),
            dislocation_over_vol_6h: dislocation
                .zip(row.trailing_realized_vol_6h)
                .and_then(|(dislocation, vol)| safe_div(dislocation, vol)),
            gas_over_quote_abs: row.gas_pressure,
            quote_abs_over_log_liquidity: row
                .quote_abs
                .zip(liquidity_proxy.and_then(log1p_positive))
                .and_then(|(quote_abs, log_liquidity)| safe_div(quote_abs, log_liquidity)),
            age_times_dislocation: age
                .zip(dislocation)
                .and_then(|(age, dislocation)| finite(age * dislocation)),
            dislocation_over_log_quote_abs: dislocation
                .zip(log_quote)
                .and_then(|(dislocation, log_abs)| safe_div(dislocation, log_abs)),
            liquidity_pressure: row.liquidity_pressure,
            gas_pressure: row.gas_pressure,
            crowding: row.crowding,
            pool_quote_hhi: row.pool_quote_hhi,
            trailing_realized_vol_1h: row.trailing_realized_vol_1h,
            trailing_realized_vol_6h: row.trailing_realized_vol_6h,
            same_block_event_count: finite(row.same_block_event_count as f64),
        });
    }
    rows
}

fn evaluate_factor_candidates(
    candidates: &[FactorCandidateRow],
    costs: &[CostLabelRow],
    targets: &[TargetSpec],
    eval_workers: usize,
) -> (
    Vec<FactorExpressionSummaryRow>,
    Vec<FactorExpressionSummaryRow>,
    Vec<FactorStabilityRow>,
    Vec<FactorBucketProfileRow>,
) {
    let target_values_by_name = targets
        .iter()
        .map(|target| {
            (
                target.name.clone(),
                costs
                    .iter()
                    .map(|row| target_value(row, &target.name))
                    .collect::<Vec<_>>(),
            )
        })
        .collect::<HashMap<_, _>>();

    let workers = eval_workers.max(1).min(FACTOR_NAMES.len());
    let chunk_size = (FACTOR_NAMES.len() + workers - 1) / workers;
    let outputs = if workers == 1 {
        vec![evaluate_factor_chunk(
            &FACTOR_NAMES,
            candidates,
            targets,
            &target_values_by_name,
        )]
    } else {
        thread::scope(|scope| {
            let mut handles = Vec::new();
            for chunk in FACTOR_NAMES.chunks(chunk_size) {
                handles.push(scope.spawn({
                    let target_values_by_name = &target_values_by_name;
                    move || evaluate_factor_chunk(chunk, candidates, targets, target_values_by_name)
                }));
            }
            handles
                .into_iter()
                .map(|handle| handle.join().expect("factor evaluation worker panicked"))
                .collect::<Vec<_>>()
        })
    };

    let mut gross_summary_rows = Vec::<FactorExpressionSummaryRow>::new();
    let mut diagnostic_rows = Vec::<FactorExpressionSummaryRow>::new();
    let mut stability_rows = Vec::<FactorStabilityRow>::new();
    let mut bucket_rows = Vec::<FactorBucketProfileRow>::new();
    for output in outputs {
        gross_summary_rows.extend(output.gross_summary_rows);
        diagnostic_rows.extend(output.diagnostic_rows);
        stability_rows.extend(output.stability_rows);
        bucket_rows.extend(output.bucket_rows);
    }

    sort_factor_summary_rows(&mut gross_summary_rows);
    sort_factor_summary_rows(&mut diagnostic_rows);
    (
        gross_summary_rows,
        diagnostic_rows,
        stability_rows,
        bucket_rows,
    )
}

#[derive(Debug, Default)]
struct WorkerEvalOutput {
    gross_summary_rows: Vec<FactorExpressionSummaryRow>,
    diagnostic_rows: Vec<FactorExpressionSummaryRow>,
    stability_rows: Vec<FactorStabilityRow>,
    bucket_rows: Vec<FactorBucketProfileRow>,
}

fn evaluate_factor_chunk(
    factors: &[&str],
    candidates: &[FactorCandidateRow],
    targets: &[TargetSpec],
    target_values_by_name: &HashMap<String, Vec<Option<f64>>>,
) -> WorkerEvalOutput {
    let mut output = WorkerEvalOutput::default();
    for factor in factors {
        let factor_values = candidates
            .iter()
            .map(|row| factor_value(row, factor))
            .collect::<Vec<_>>();
        let discovery_values = candidates
            .iter()
            .zip(&factor_values)
            .filter_map(|(row, value)| {
                if row.split == "discovery" {
                    *value
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        let thresholds = quantile_thresholds(discovery_values, FACTOR_BUCKETS);
        if thresholds.len() + 1 < FACTOR_BUCKETS {
            continue;
        }
        let factor_buckets = factor_values
            .iter()
            .map(|value| value.and_then(|value| bucket_for_value(value, &thresholds)))
            .collect::<Vec<_>>();

        for target in targets {
            if !factor_enabled_for_evaluation_family(factor, &target.evaluation_family) {
                continue;
            }
            let target_values = target_values_by_name
                .get(&target.name)
                .expect("target values were precomputed");
            let evaluated = evaluate_factor_target_once(
                candidates,
                &factor_values,
                &factor_buckets,
                target_values,
                factor,
                &target.name,
                &target.kind,
                &target.evaluation_family,
            );
            let discovery = evaluated.discovery;
            let validation = evaluated.validation;
            let forward = evaluated.forward;
            if discovery.n < 100 || validation.n < 100 {
                continue;
            }
            let status = validation_status(&discovery, &validation, &forward);
            let summary_row = FactorExpressionSummaryRow {
                validation_rank: 0,
                factor: factor.to_string(),
                factor_family: factor_family(factor).to_string(),
                factor_role: factor_role(factor).to_string(),
                target: target.name.clone(),
                horizon: target.horizon.clone(),
                target_kind: target.kind.clone(),
                evaluation_family: target.evaluation_family.clone(),
                status,
                discovery_n: discovery.n,
                discovery_spearman: discovery.spearman,
                discovery_top_minus_bottom: discovery.high_minus_low,
                validation_n: validation.n,
                validation_spearman: validation.spearman,
                validation_top_minus_bottom: validation.high_minus_low,
                forward_n: forward.n,
                forward_spearman: forward.spearman,
                forward_top_minus_bottom: forward.high_minus_low,
            };
            if target.evaluation_family == EVALUATION_FAMILY_GROSS_FACTOR_MAP {
                output.gross_summary_rows.push(summary_row);
            } else {
                output.diagnostic_rows.push(summary_row);
            }
            output.bucket_rows.extend(evaluated.bucket_rows);
            output.stability_rows.extend(evaluated.stability_rows);
        }
    }
    output
}

#[derive(Debug, Default)]
struct SplitEvalAgg {
    xs: Vec<f64>,
    ys: Vec<f64>,
    top_bottom: TopBottomAgg,
}

impl SplitEvalAgg {
    fn add(&mut self, factor: f64, target: f64, bucket: Option<u8>, quote_abs: Option<f64>) {
        self.xs.push(factor);
        self.ys.push(target);
        if let Some(bucket) = bucket {
            self.top_bottom.add(bucket, factor, target, quote_abs);
        }
    }

    fn stats(self) -> EvalStats {
        let mut stats = self.top_bottom.stats();
        stats.n = self.xs.len() as u64;
        stats.spearman = sampled_spearman(&self.xs, &self.ys, 200_000);
        stats
    }
}

#[derive(Debug, Default)]
struct FactorTargetEvaluation {
    discovery: EvalStats,
    validation: EvalStats,
    forward: EvalStats,
    stability_rows: Vec<FactorStabilityRow>,
    bucket_rows: Vec<FactorBucketProfileRow>,
}

fn evaluate_factor_target_once(
    candidates: &[FactorCandidateRow],
    factor_values: &[Option<f64>],
    factor_buckets: &[Option<u8>],
    target_values: &[Option<f64>],
    factor: &str,
    target: &str,
    target_kind: &str,
    evaluation_family: &str,
) -> FactorTargetEvaluation {
    let mut by_split = BTreeMap::<String, SplitEvalAgg>::new();
    let mut bucket_by_key = BTreeMap::<(String, u8), BucketStats>::new();
    let mut stability_by_key = BTreeMap::<(String, String, String), TopBottomAgg>::new();

    for ((row, factor_value), (bucket, target_value)) in candidates
        .iter()
        .zip(factor_values)
        .zip(factor_buckets.iter().zip(target_values))
    {
        let Some(factor_value) = factor_value.filter(|value| value.is_finite()) else {
            continue;
        };
        let Some(target_value) = target_value.filter(|value| value.is_finite()) else {
            continue;
        };
        by_split.entry(row.split.clone()).or_default().add(
            factor_value,
            target_value,
            *bucket,
            row.quote_abs,
        );
        let Some(bucket) = bucket else {
            continue;
        };
        bucket_by_key
            .entry((row.split.clone(), *bucket))
            .or_default()
            .add(factor_value, target_value, row.quote_abs);
        for (stratum_type, stratum_value) in [
            ("quality_tier", row.quality_tier.as_str()),
            ("pool", row.pool_address.as_str()),
            ("date", row.date_utc.as_str()),
            ("volatility_regime", row.volatility_regime.as_str()),
            ("quote_notional_bucket", row.quote_notional_bucket.as_str()),
        ] {
            stability_by_key
                .entry((
                    row.split.clone(),
                    stratum_type.to_string(),
                    stratum_value.to_string(),
                ))
                .or_default()
                .add(*bucket, factor_value, target_value, row.quote_abs);
        }
    }

    let bucket_rows = bucket_by_key
        .into_iter()
        .filter_map(|((split, bucket), stats)| {
            if stats.n < 30 {
                return None;
            }
            Some(FactorBucketProfileRow {
                factor: factor.to_string(),
                factor_family: factor_family(factor).to_string(),
                target: target.to_string(),
                target_kind: target_kind.to_string(),
                evaluation_family: evaluation_family.to_string(),
                split,
                bucket: bucket as u64,
                n: stats.n,
                mean_target: stats.mean_target(),
                positive_rate: stats.positive_rate(),
                mean_factor: stats.mean_factor(),
                mean_quote_abs: stats.mean_quote_abs(),
            })
        })
        .collect::<Vec<_>>();

    let stability_rows = stability_by_key
        .into_iter()
        .filter_map(|((split, stratum_type, stratum_value), agg)| {
            let stats = agg.stats();
            if stats.n < 30 || stats.low_bucket_n == 0 || stats.high_bucket_n == 0 {
                return None;
            }
            Some(FactorStabilityRow {
                factor: factor.to_string(),
                factor_family: factor_family(factor).to_string(),
                target: target.to_string(),
                target_kind: target_kind.to_string(),
                evaluation_family: evaluation_family.to_string(),
                split,
                stratum_type,
                stratum_value,
                n: stats.n,
                low_bucket_n: stats.low_bucket_n,
                high_bucket_n: stats.high_bucket_n,
                low_mean: stats.low_mean,
                high_mean: stats.high_mean,
                high_minus_low: stats.high_minus_low,
                low_positive_rate: stats.low_positive_rate,
                high_positive_rate: stats.high_positive_rate,
            })
        })
        .collect::<Vec<_>>();

    FactorTargetEvaluation {
        discovery: by_split.remove("discovery").unwrap_or_default().stats(),
        validation: by_split.remove("validation").unwrap_or_default().stats(),
        forward: by_split.remove("forward").unwrap_or_default().stats(),
        stability_rows,
        bucket_rows,
    }
}

fn factor_enabled_for_evaluation_family(factor: &str, evaluation_family: &str) -> bool {
    match evaluation_family {
        EVALUATION_FAMILY_GROSS_FACTOR_MAP => true,
        EVALUATION_FAMILY_TRADABILITY_DIAGNOSTIC => is_mechanical_net_label_factor(factor),
        _ => false,
    }
}

fn is_mechanical_net_label_factor(factor: &str) -> bool {
    MECHANICAL_NET_LABEL_FACTORS.contains(&factor)
}

fn sort_factor_summary_rows(rows: &mut [FactorExpressionSummaryRow]) {
    rows.sort_by(|a, b| {
        desc_option_abs_f64(a.validation_spearman, b.validation_spearman)
            .then_with(|| {
                desc_option_abs_f64(a.validation_top_minus_bottom, b.validation_top_minus_bottom)
            })
            .then_with(|| b.validation_n.cmp(&a.validation_n))
            .then_with(|| a.factor.cmp(&b.factor))
            .then_with(|| a.target.cmp(&b.target))
    });
    for (index, row) in rows.iter_mut().enumerate() {
        row.validation_rank = index as u64 + 1;
    }
}

#[cfg(test)]
fn evaluate_factor_candidates_slow(
    candidates: &[FactorCandidateRow],
    costs: &[CostLabelRow],
    targets: &[TargetSpec],
) -> (
    Vec<FactorExpressionSummaryRow>,
    Vec<FactorExpressionSummaryRow>,
    Vec<FactorStabilityRow>,
    Vec<FactorBucketProfileRow>,
) {
    let mut gross_summary_rows = Vec::<FactorExpressionSummaryRow>::new();
    let mut diagnostic_rows = Vec::<FactorExpressionSummaryRow>::new();
    let mut stability_rows = Vec::<FactorStabilityRow>::new();
    let mut bucket_rows = Vec::<FactorBucketProfileRow>::new();
    let target_values_by_name = targets
        .iter()
        .map(|target| {
            (
                target.name.clone(),
                costs
                    .iter()
                    .map(|row| target_value(row, &target.name))
                    .collect::<Vec<_>>(),
            )
        })
        .collect::<HashMap<_, _>>();

    for factor in FACTOR_NAMES {
        let factor_values = candidates
            .iter()
            .map(|row| factor_value(row, factor))
            .collect::<Vec<_>>();
        let discovery_values = candidates
            .iter()
            .zip(&factor_values)
            .filter_map(|(row, value)| {
                if row.split == "discovery" {
                    *value
                } else {
                    None
                }
            })
            .collect::<Vec<_>>();
        let thresholds = quantile_thresholds(discovery_values, FACTOR_BUCKETS);
        if thresholds.len() + 1 < FACTOR_BUCKETS {
            continue;
        }
        let factor_buckets = factor_values
            .iter()
            .map(|value| value.and_then(|value| bucket_for_value(value, &thresholds)))
            .collect::<Vec<_>>();

        for target in targets {
            if !factor_enabled_for_evaluation_family(factor, &target.evaluation_family) {
                continue;
            }
            let target_values = target_values_by_name
                .get(&target.name)
                .expect("target values were precomputed");
            let discovery = eval_split(
                candidates,
                &factor_values,
                &factor_buckets,
                target_values,
                "discovery",
            );
            let validation = eval_split(
                candidates,
                &factor_values,
                &factor_buckets,
                target_values,
                "validation",
            );
            let forward = eval_split(
                candidates,
                &factor_values,
                &factor_buckets,
                target_values,
                "forward",
            );
            if discovery.n < 100 || validation.n < 100 {
                continue;
            }
            let status = validation_status(&discovery, &validation, &forward);
            let summary_row = FactorExpressionSummaryRow {
                validation_rank: 0,
                factor: factor.to_string(),
                factor_family: factor_family(factor).to_string(),
                factor_role: factor_role(factor).to_string(),
                target: target.name.clone(),
                horizon: target.horizon.clone(),
                target_kind: target.kind.clone(),
                evaluation_family: target.evaluation_family.clone(),
                status,
                discovery_n: discovery.n,
                discovery_spearman: discovery.spearman,
                discovery_top_minus_bottom: discovery.high_minus_low,
                validation_n: validation.n,
                validation_spearman: validation.spearman,
                validation_top_minus_bottom: validation.high_minus_low,
                forward_n: forward.n,
                forward_spearman: forward.spearman,
                forward_top_minus_bottom: forward.high_minus_low,
            };
            if target.evaluation_family == EVALUATION_FAMILY_GROSS_FACTOR_MAP {
                gross_summary_rows.push(summary_row);
            } else {
                diagnostic_rows.push(summary_row);
            }

            append_bucket_profiles(
                &mut bucket_rows,
                candidates,
                &factor_values,
                &factor_buckets,
                target_values,
                factor,
                &target.name,
                &target.kind,
                &target.evaluation_family,
            );
            append_stability_rows(
                &mut stability_rows,
                candidates,
                &factor_values,
                &factor_buckets,
                target_values,
                factor,
                &target.name,
                &target.kind,
                &target.evaluation_family,
            );
        }
    }

    sort_factor_summary_rows(&mut gross_summary_rows);
    sort_factor_summary_rows(&mut diagnostic_rows);
    (
        gross_summary_rows,
        diagnostic_rows,
        stability_rows,
        bucket_rows,
    )
}

#[cfg(test)]
fn eval_split(
    candidates: &[FactorCandidateRow],
    factor_values: &[Option<f64>],
    factor_buckets: &[Option<u8>],
    target_values: &[Option<f64>],
    split: &str,
) -> EvalStats {
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let mut top_bottom = TopBottomAgg::default();
    for ((row, factor), (bucket, target)) in candidates
        .iter()
        .zip(factor_values)
        .zip(factor_buckets.iter().zip(target_values))
    {
        if row.split != split {
            continue;
        }
        let Some(factor) = factor.filter(|value| value.is_finite()) else {
            continue;
        };
        let Some(target) = target.filter(|value| value.is_finite()) else {
            continue;
        };
        xs.push(factor);
        ys.push(target);
        if let Some(bucket) = bucket {
            top_bottom.add(*bucket, factor, target, row.quote_abs);
        }
    }
    let mut stats = top_bottom.stats();
    stats.n = xs.len() as u64;
    stats.spearman = sampled_spearman(&xs, &ys, 200_000);
    stats
}

fn sampled_spearman(xs: &[f64], ys: &[f64], max_rows: usize) -> Option<f64> {
    if xs.len() <= max_rows {
        return spearman(xs, ys);
    }
    let stride = (xs.len() / max_rows).max(1);
    let mut sampled_x = Vec::with_capacity(max_rows + 1);
    let mut sampled_y = Vec::with_capacity(max_rows + 1);
    for index in (0..xs.len()).step_by(stride) {
        sampled_x.push(xs[index]);
        sampled_y.push(ys[index]);
        if sampled_x.len() >= max_rows {
            break;
        }
    }
    spearman(&sampled_x, &sampled_y)
}

#[cfg(test)]
fn append_bucket_profiles(
    rows: &mut Vec<FactorBucketProfileRow>,
    candidates: &[FactorCandidateRow],
    factor_values: &[Option<f64>],
    factor_buckets: &[Option<u8>],
    target_values: &[Option<f64>],
    factor: &str,
    target: &str,
    target_kind: &str,
    evaluation_family: &str,
) {
    let mut by_key = BTreeMap::<(String, u8), BucketStats>::new();
    for ((row, factor_value), (bucket, target_value)) in candidates
        .iter()
        .zip(factor_values)
        .zip(factor_buckets.iter().zip(target_values))
    {
        let Some(factor_value) = factor_value.filter(|value| value.is_finite()) else {
            continue;
        };
        let Some(target_value) = target_value.filter(|value| value.is_finite()) else {
            continue;
        };
        let Some(bucket) = bucket else {
            continue;
        };
        by_key.entry((row.split.clone(), *bucket)).or_default().add(
            factor_value,
            target_value,
            row.quote_abs,
        );
    }
    for ((split, bucket), stats) in by_key {
        if stats.n < 30 {
            continue;
        }
        rows.push(FactorBucketProfileRow {
            factor: factor.to_string(),
            factor_family: factor_family(factor).to_string(),
            target: target.to_string(),
            target_kind: target_kind.to_string(),
            evaluation_family: evaluation_family.to_string(),
            split,
            bucket: bucket as u64,
            n: stats.n,
            mean_target: stats.mean_target(),
            positive_rate: stats.positive_rate(),
            mean_factor: stats.mean_factor(),
            mean_quote_abs: stats.mean_quote_abs(),
        });
    }
}

#[cfg(test)]
fn append_stability_rows(
    rows: &mut Vec<FactorStabilityRow>,
    candidates: &[FactorCandidateRow],
    factor_values: &[Option<f64>],
    factor_buckets: &[Option<u8>],
    target_values: &[Option<f64>],
    factor: &str,
    target: &str,
    target_kind: &str,
    evaluation_family: &str,
) {
    let mut by_key = BTreeMap::<(String, String, String), TopBottomAgg>::new();
    for ((row, factor_value), (bucket, target_value)) in candidates
        .iter()
        .zip(factor_values)
        .zip(factor_buckets.iter().zip(target_values))
    {
        let Some(factor_value) = factor_value.filter(|value| value.is_finite()) else {
            continue;
        };
        let Some(target_value) = target_value.filter(|value| value.is_finite()) else {
            continue;
        };
        let Some(bucket) = bucket else {
            continue;
        };
        for (stratum_type, stratum_value) in [
            ("quality_tier", row.quality_tier.as_str()),
            ("pool", row.pool_address.as_str()),
            ("date", row.date_utc.as_str()),
            ("volatility_regime", row.volatility_regime.as_str()),
            ("quote_notional_bucket", row.quote_notional_bucket.as_str()),
        ] {
            by_key
                .entry((
                    row.split.clone(),
                    stratum_type.to_string(),
                    stratum_value.to_string(),
                ))
                .or_default()
                .add(*bucket, factor_value, target_value, row.quote_abs);
        }
    }
    for ((split, stratum_type, stratum_value), agg) in by_key {
        let stats = agg.stats();
        if stats.n < 30 || stats.low_bucket_n == 0 || stats.high_bucket_n == 0 {
            continue;
        }
        rows.push(FactorStabilityRow {
            factor: factor.to_string(),
            factor_family: factor_family(factor).to_string(),
            target: target.to_string(),
            target_kind: target_kind.to_string(),
            evaluation_family: evaluation_family.to_string(),
            split,
            stratum_type,
            stratum_value,
            n: stats.n,
            low_bucket_n: stats.low_bucket_n,
            high_bucket_n: stats.high_bucket_n,
            low_mean: stats.low_mean,
            high_mean: stats.high_mean,
            high_minus_low: stats.high_minus_low,
            low_positive_rate: stats.low_positive_rate,
            high_positive_rate: stats.high_positive_rate,
        });
    }
}

fn build_split_summary(candidates: &[FactorCandidateRow]) -> Vec<FactorSplitSummaryRow> {
    #[derive(Default)]
    struct Agg {
        rows: u64,
        dates: BTreeSet<String>,
        quote_abs_sum: f64,
    }
    let mut by_key = BTreeMap::<(String, String), Agg>::new();
    for row in candidates {
        let agg = by_key
            .entry((row.split.clone(), row.quality_tier.clone()))
            .or_default();
        agg.rows += 1;
        agg.dates.insert(row.date_utc.clone());
        if let Some(quote_abs) = row.quote_abs.filter(|value| value.is_finite()) {
            agg.quote_abs_sum += quote_abs;
        }
    }
    by_key
        .into_iter()
        .map(|((split, quality_tier), agg)| FactorSplitSummaryRow {
            split,
            quality_tier,
            rows: agg.rows,
            unique_dates: agg.dates.len() as u64,
            first_date: agg.dates.iter().next().cloned().unwrap_or_default(),
            last_date: agg.dates.iter().next_back().cloned().unwrap_or_default(),
            quote_abs_sum: agg.quote_abs_sum,
        })
        .collect()
}

fn build_factor_role_summary() -> Vec<FactorRoleSummaryRow> {
    FACTOR_NAMES
        .iter()
        .map(|factor| {
            let mechanical = is_mechanical_net_label_factor(factor);
            FactorRoleSummaryRow {
                factor: (*factor).to_string(),
                factor_family: factor_family(factor).to_string(),
                factor_role: factor_role(factor).to_string(),
                gross_factor_map_allowed: true,
                net_return_alpha_allowed: false,
                tradability_diagnostic_allowed: mechanical,
                mechanical_net_label_factor: mechanical,
                rationale: factor_role_rationale(factor).to_string(),
            }
        })
        .collect()
}

fn target_specs() -> Vec<TargetSpec> {
    let mut targets = Vec::new();
    for (horizon, _) in HORIZONS {
        targets.push(TargetSpec {
            name: format!("market_gross_return_{horizon}"),
            horizon: horizon.to_string(),
            kind: TARGET_KIND_MARKET_GROSS.to_string(),
            evaluation_family: EVALUATION_FAMILY_GROSS_FACTOR_MAP.to_string(),
        });
    }
    for (horizon, _) in HORIZONS {
        targets.push(TargetSpec {
            name: format!("side_gross_return_{horizon}"),
            horizon: horizon.to_string(),
            kind: TARGET_KIND_SIDE_GROSS.to_string(),
            evaluation_family: EVALUATION_FAMILY_GROSS_FACTOR_MAP.to_string(),
        });
    }
    for (horizon, _) in HORIZONS {
        targets.push(TargetSpec {
            name: format!("net_return_{horizon}_slip25bps"),
            horizon: horizon.to_string(),
            kind: TARGET_KIND_NET_DIAGNOSTIC.to_string(),
            evaluation_family: EVALUATION_FAMILY_TRADABILITY_DIAGNOSTIC.to_string(),
        });
    }
    targets
}

fn target_value(row: &CostLabelRow, target: &str) -> Option<f64> {
    match target {
        "market_gross_return_5m" => row.market_gross_return_5m,
        "market_gross_return_15m" => row.market_gross_return_15m,
        "market_gross_return_1h" => row.market_gross_return_1h,
        "market_gross_return_3h" => row.market_gross_return_3h,
        "market_gross_return_6h" => row.market_gross_return_6h,
        "side_gross_return_5m" => row.side_gross_return_5m,
        "side_gross_return_15m" => row.side_gross_return_15m,
        "side_gross_return_1h" => row.side_gross_return_1h,
        "side_gross_return_3h" => row.side_gross_return_3h,
        "side_gross_return_6h" => row.side_gross_return_6h,
        "net_return_5m_slip25bps" => row.net_return_5m_slip25bps,
        "net_return_15m_slip25bps" => row.net_return_15m_slip25bps,
        "net_return_1h_slip25bps" => row.net_return_1h_slip25bps,
        "net_return_3h_slip25bps" => row.net_return_3h_slip25bps,
        "net_return_6h_slip25bps" => row.net_return_6h_slip25bps,
        _ => None,
    }
}

fn factor_value(row: &FactorCandidateRow, factor: &str) -> Option<f64> {
    match factor {
        "log1p_quote_abs" => row.log1p_quote_abs,
        "sqrt_quote_abs" => row.sqrt_quote_abs,
        "signed_quote_flow_over_log_abs" => row.signed_quote_flow_over_log_abs,
        "signed_quote_flow_times_log_abs" => row.signed_quote_flow_times_log_abs,
        "quote_abs_over_liquidity" => row.quote_abs_over_liquidity,
        "flow_over_liquidity" => row.flow_over_liquidity,
        "flow_over_sqrt_liquidity" => row.flow_over_sqrt_liquidity,
        "dislocation_over_vol_1h" => row.dislocation_over_vol_1h,
        "dislocation_over_vol_6h" => row.dislocation_over_vol_6h,
        "gas_over_quote_abs" => row.gas_over_quote_abs,
        "quote_abs_over_log_liquidity" => row.quote_abs_over_log_liquidity,
        "age_times_dislocation" => row.age_times_dislocation,
        "dislocation_over_log_quote_abs" => row.dislocation_over_log_quote_abs,
        "signed_quote_flow" => row.signed_quote_flow,
        "liquidity_pressure" => row.liquidity_pressure,
        "gas_pressure" => row.gas_pressure,
        "crowding" => row.crowding,
        "pool_quote_hhi" => row.pool_quote_hhi,
        "trailing_realized_vol_1h" => row.trailing_realized_vol_1h,
        "trailing_realized_vol_6h" => row.trailing_realized_vol_6h,
        "same_block_event_count" => row.same_block_event_count,
        _ => None,
    }
}

fn factor_family(factor: &str) -> &'static str {
    match factor {
        "log1p_quote_abs" | "sqrt_quote_abs" => "event_size",
        "signed_quote_flow"
        | "signed_quote_flow_over_log_abs"
        | "signed_quote_flow_times_log_abs" => "signed_flow",
        "quote_abs_over_liquidity"
        | "liquidity_pressure"
        | "flow_over_liquidity"
        | "flow_over_sqrt_liquidity"
        | "quote_abs_over_log_liquidity" => "liquidity_capacity",
        "dislocation_over_vol_1h"
        | "dislocation_over_vol_6h"
        | "dislocation_over_log_quote_abs"
        | "age_times_dislocation" => "cross_pool_dislocation",
        "gas_over_quote_abs" | "gas_pressure" => "execution_cost",
        "crowding" | "same_block_event_count" | "pool_quote_hhi" => "crowding_quality",
        "trailing_realized_vol_1h" | "trailing_realized_vol_6h" => "volatility_regime",
        _ => "other",
    }
}

fn factor_role(factor: &str) -> &'static str {
    match factor {
        "signed_quote_flow"
        | "signed_quote_flow_over_log_abs"
        | "signed_quote_flow_times_log_abs" => "directional_alpha_candidate",
        "log1p_quote_abs" | "sqrt_quote_abs" => "event_continuation_candidate",
        "dislocation_over_vol_1h"
        | "dislocation_over_vol_6h"
        | "dislocation_over_log_quote_abs"
        | "trailing_realized_vol_1h"
        | "trailing_realized_vol_6h" => "regime_filter",
        "gas_over_quote_abs" | "gas_pressure" => "execution_filter",
        "quote_abs_over_liquidity"
        | "liquidity_pressure"
        | "flow_over_liquidity"
        | "flow_over_sqrt_liquidity"
        | "quote_abs_over_log_liquidity" => "capacity_filter",
        "crowding" | "same_block_event_count" | "pool_quote_hhi" => "quality_filter",
        "age_times_dislocation" => "unstable_or_diagnostic_only",
        _ => "unstable_or_diagnostic_only",
    }
}

fn factor_role_rationale(factor: &str) -> &'static str {
    match factor_role(factor) {
        "directional_alpha_candidate" => {
            "signed event flow can be studied against gross market and side continuation labels"
        }
        "event_continuation_candidate" => {
            "event size can explain future gross-return behavior but is mechanical in net labels"
        }
        "regime_filter" => {
            "state, dislocation, or volatility context is better interpreted as a regime condition"
        }
        "execution_filter" => {
            "execution cost pressure directly affects net labels and belongs in diagnostics"
        }
        "capacity_filter" => {
            "notional versus liquidity describes capacity and execution feasibility"
        }
        "quality_filter" => {
            "crowding and concentration describe sample quality or local microstructure congestion"
        }
        _ => "kept for diagnostics until a stable gross-return relationship is demonstrated",
    }
}

fn validation_status(discovery: &EvalStats, validation: &EvalStats, forward: &EvalStats) -> String {
    let Some(discovery_sign) = sign(discovery.high_minus_low) else {
        return "discovery_only".to_string();
    };
    let Some(validation_sign) = sign(validation.high_minus_low) else {
        return "discovery_only".to_string();
    };
    if discovery_sign != validation_sign {
        return "discovery_only".to_string();
    }
    if let Some(forward_sign) = sign(forward.high_minus_low) {
        if forward_sign != validation_sign {
            return "failed_forward".to_string();
        }
    }
    "validated_same_sign".to_string()
}

fn sign(value: Option<f64>) -> Option<i8> {
    let value = value.filter(|value| value.is_finite())?;
    if value > 0.0 {
        Some(1)
    } else if value < 0.0 {
        Some(-1)
    } else {
        None
    }
}

fn hourly_pool_quote_hhi(rows: &[ExecutionEventRow]) -> HashMap<String, Option<f64>> {
    let mut by_hour_pool = BTreeMap::<String, BTreeMap<String, f64>>::new();
    for row in rows {
        let Some(quote_abs) = row
            .quote_abs
            .filter(|value| value.is_finite() && *value > 0.0)
        else {
            continue;
        };
        *by_hour_pool
            .entry(row.hour_utc.clone())
            .or_default()
            .entry(row.pool_address.clone())
            .or_default() += quote_abs;
    }
    by_hour_pool
        .into_iter()
        .map(|(hour, pool_quote)| {
            let total = pool_quote.values().sum::<f64>();
            let hhi = if total > 0.0 {
                finite(
                    pool_quote
                        .values()
                        .map(|value| {
                            let share = *value / total;
                            share * share
                        })
                        .sum::<f64>(),
                )
            } else {
                None
            };
            (hour, hhi)
        })
        .collect()
}

fn minute_realized_volatility(
    rows: &[ExecutionEventRow],
) -> HashMap<i64, (Option<f64>, Option<f64>)> {
    let mut minute_volume = BTreeMap::<i64, (f64, f64)>::new();
    for row in rows {
        let minute = floor_to_minute(row.timestamp);
        match (row.base_abs, row.quote_abs) {
            (Some(base), Some(quote))
                if base.is_finite() && quote.is_finite() && base > 0.0 && quote > 0.0 =>
            {
                let entry = minute_volume.entry(minute).or_default();
                entry.0 += base;
                entry.1 += quote;
            }
            _ => {}
        }
    }
    let Some(start) = minute_volume.keys().next().copied() else {
        return HashMap::new();
    };
    let Some(end) = minute_volume.keys().next_back().copied() else {
        return HashMap::new();
    };

    let mut result = HashMap::new();
    let mut last_price = None::<f64>;
    let mut prev_price = None::<f64>;
    let mut one_hour = RollingVol::new(60);
    let mut six_hour = RollingVol::new(360);
    let mut minute = start;
    while minute <= end {
        let observed = minute_volume.get(&minute).and_then(|(base, quote)| {
            if *base > 0.0 {
                finite(*quote / *base)
            } else {
                None
            }
        });
        let price = observed.or(last_price);
        result.insert(minute, (one_hour.vol(), six_hour.vol()));
        let ret = prev_price
            .zip(price)
            .and_then(|(prev, current)| forward_return(Some(prev), Some(current)));
        one_hour.push(ret);
        six_hour.push(ret);
        if let Some(price) = price {
            last_price = Some(price);
            prev_price = Some(price);
        }
        minute += 60;
    }
    result
}

struct RollingVol {
    window: usize,
    values: VecDeque<f64>,
    sum_sq: f64,
}

impl RollingVol {
    fn new(window: usize) -> Self {
        Self {
            window,
            values: VecDeque::new(),
            sum_sq: 0.0,
        }
    }

    fn push(&mut self, value: Option<f64>) {
        if let Some(value) = value.filter(|value| value.is_finite()) {
            self.sum_sq += value * value;
            self.values.push_back(value);
        } else {
            self.values.push_back(0.0);
        }
        while self.values.len() > self.window {
            if let Some(value) = self.values.pop_front() {
                self.sum_sq -= value * value;
            }
        }
    }

    fn vol(&self) -> Option<f64> {
        if self.values.is_empty() {
            None
        } else {
            finite((self.sum_sq / self.values.len() as f64).sqrt())
        }
    }
}

fn thresholds_from_physical_split<F>(
    rows: &[PhysicalFeatureRow],
    split_by_date: &BTreeMap<String, String>,
    value_fn: F,
    buckets: usize,
) -> Vec<f64>
where
    F: Fn(&PhysicalFeatureRow) -> Option<f64>,
{
    let values = rows
        .iter()
        .filter(|row| row.research_sample_included)
        .filter(|row| split_by_date.get(&row.date_utc).map(String::as_str) == Some("discovery"))
        .filter_map(value_fn)
        .collect::<Vec<_>>();
    quantile_thresholds(values, buckets)
}

pub fn chronological_split_map<I>(dates: I) -> BTreeMap<String, String>
where
    I: IntoIterator<Item = String>,
{
    let unique = dates
        .into_iter()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let n = unique.len();
    if n == 0 {
        return BTreeMap::new();
    }
    let discovery_end = ((n as f64) * 0.60).floor().max(1.0) as usize;
    let validation_end = ((n as f64) * 0.80)
        .floor()
        .max(discovery_end as f64 + 1.0)
        .min(n as f64) as usize;
    unique
        .into_iter()
        .enumerate()
        .map(|(index, date)| {
            let split = if index < discovery_end {
                "discovery"
            } else if index < validation_end {
                "validation"
            } else {
                "forward"
            };
            (date, split.to_string())
        })
        .collect()
}

fn quantile_thresholds(mut values: Vec<f64>, buckets: usize) -> Vec<f64> {
    values.retain(|value| value.is_finite());
    values.sort_by(f64::total_cmp);
    values.dedup_by(|a, b| a.total_cmp(b) == Ordering::Equal);
    if buckets < 2 || values.len() < buckets {
        return Vec::new();
    }
    let len = values.len();
    (1..buckets)
        .filter_map(|bucket| {
            let index = ((len * bucket) / buckets).min(len - 1);
            values.get(index).copied().and_then(finite)
        })
        .collect()
}

fn bucket_for_value(value: f64, thresholds: &[f64]) -> Option<u8> {
    if !value.is_finite() {
        return None;
    }
    let mut bucket = 0usize;
    while bucket < thresholds.len() && value > thresholds[bucket] {
        bucket += 1;
    }
    Some(bucket as u8)
}

fn notional_bucket(value: Option<f64>, thresholds: &[f64]) -> String {
    match value.and_then(|value| bucket_for_value(value, thresholds)) {
        Some(bucket) => format!("q{}", bucket + 1),
        None => "unavailable".to_string(),
    }
}

fn volatility_regime(value: Option<f64>, thresholds: &[f64]) -> String {
    let Some(bucket) = value.and_then(|value| bucket_for_value(value, thresholds)) else {
        return "unavailable".to_string();
    };
    match bucket {
        0 => "low".to_string(),
        1 => "mid".to_string(),
        _ => "high".to_string(),
    }
}

fn research_sample_included(quality_tier: &str) -> bool {
    RESEARCH_TIERS.contains(&quality_tier)
}

fn signed_quote_flow(direction: &str, quote_abs: Option<f64>) -> Option<f64> {
    let quote_abs = quote_abs.filter(|value| value.is_finite())?;
    match direction {
        "buy_base" => finite(quote_abs),
        "sell_base" => finite(-quote_abs),
        _ => None,
    }
}

fn market_gross_return(fwd_return: Option<f64>) -> Option<f64> {
    fwd_return.filter(|value| value.is_finite())
}

fn side_gross_return(direction: &str, fwd_return: Option<f64>) -> Option<f64> {
    let fwd_return = fwd_return.filter(|value| value.is_finite())?;
    match direction {
        "buy_base" => finite(fwd_return),
        "sell_base" => finite(-fwd_return),
        _ => None,
    }
}

fn net_label(
    side_gross: Option<f64>,
    assumed_fee_bps_one_way: f64,
    roundtrip_gas_return_proxy: Option<f64>,
    slippage_bps: f64,
) -> Option<f64> {
    let side_gross = side_gross.filter(|value| value.is_finite())?;
    let gas = roundtrip_gas_return_proxy.filter(|value| value.is_finite())?;
    let fee = 2.0 * assumed_fee_bps_one_way / 10_000.0;
    let slippage = 2.0 * slippage_bps / 10_000.0;
    finite(side_gross - fee - gas - slippage)
}

fn gas_return_proxies(
    gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
    price_quote_per_base: Option<f64>,
    quote_abs: Option<f64>,
) -> (Option<f64>, Option<f64>) {
    let Some(gas_used) = gas_used.map(|value| value as f64) else {
        return (None, None);
    };
    let Some(effective_gas_price) = effective_gas_price.map(|value| value as f64) else {
        return (None, None);
    };
    let Some(price) = price_quote_per_base.filter(|value| value.is_finite() && *value > 0.0) else {
        return (None, None);
    };
    let Some(quote_abs) = quote_abs.filter(|value| value.is_finite() && *value > 0.0) else {
        return (None, None);
    };
    let gas_quote = gas_used * effective_gas_price / 1e18 * price;
    let one_way = safe_div(gas_quote, quote_abs);
    (one_way, one_way.and_then(|value| finite(value * 2.0)))
}

fn infer_liquidity_proxy(quote_abs: Option<f64>, liquidity_pressure: Option<f64>) -> Option<f64> {
    quote_abs
        .zip(liquidity_pressure)
        .and_then(|(quote_abs, pressure)| safe_div(quote_abs, pressure))
}

fn safe_div(numerator: f64, denominator: f64) -> Option<f64> {
    if numerator.is_finite() && denominator.is_finite() && denominator != 0.0 {
        finite(numerator / denominator)
    } else {
        None
    }
}

fn sqrt_positive(value: f64) -> Option<f64> {
    if value.is_finite() && value > 0.0 {
        finite(value.sqrt())
    } else {
        None
    }
}

fn log1p_positive(value: f64) -> Option<f64> {
    if value.is_finite() && value > 0.0 {
        finite(value.ln_1p())
    } else {
        None
    }
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

fn finite(value: f64) -> Option<f64> {
    if value.is_finite() { Some(value) } else { None }
}

fn mean_from_sum(sum: f64, n: u64) -> Option<f64> {
    if n == 0 { None } else { finite(sum / n as f64) }
}

fn floor_to_minute(timestamp: i64) -> i64 {
    timestamp - timestamp.rem_euclid(60)
}

fn format_hour(timestamp: i64) -> Result<String> {
    Ok(
        DateTime::<Utc>::from_timestamp(timestamp - timestamp.rem_euclid(3600), 0)
            .ok_or_else(|| anyhow!("invalid timestamp {timestamp}"))?
            .format("%Y-%m-%dT%H:00:00Z")
            .to_string(),
    )
}

fn parse_event_timestamp(value: &str) -> Result<i64> {
    DateTime::parse_from_rfc3339(value)
        .with_context(|| format!("failed to parse event_time_utc {value}"))
        .map(|value| value.timestamp())
}

fn utc_string(timestamp: i64) -> Result<String> {
    Ok(DateTime::<Utc>::from_timestamp(timestamp, 0)
        .ok_or_else(|| anyhow!("invalid timestamp {timestamp}"))?
        .to_rfc3339_opts(SecondsFormat::Secs, true))
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

fn desc_option_abs_f64(a: Option<f64>, b: Option<f64>) -> Ordering {
    match (a, b) {
        (Some(a), Some(b)) => b.abs().total_cmp(&a.abs()),
        (Some(_), None) => Ordering::Less,
        (None, Some(_)) => Ordering::Greater,
        (None, None) => Ordering::Equal,
    }
}

pub fn filter_source_run_tag_paths_from_list(
    files: &[PathBuf],
    source_run_tag: &str,
) -> Vec<PathBuf> {
    files
        .iter()
        .filter(|path| {
            path.file_name()
                .and_then(|value| value.to_str())
                .is_some_and(|name| name.contains(source_run_tag))
        })
        .cloned()
        .collect()
}

fn source_run_tag_part_paths(
    data_root: &Path,
    dataset: &str,
    source_run_tag: &str,
) -> Result<Vec<PathBuf>> {
    let root = data_root.join(DERIVED_DIR).join(dataset);
    let files = parquet_files_under(&root)?;
    let filtered = filter_source_run_tag_paths_from_list(&files, source_run_tag);
    if filtered.is_empty() {
        bail!(
            "no parquet parts for dataset {dataset} and source run tag {source_run_tag} under {}",
            root.display()
        );
    }
    Ok(filtered)
}

fn cached_derived_part_path(
    data_root: &Path,
    dataset: &str,
    expected_schema: SchemaRef,
    run_tag: &str,
) -> Result<Option<PathBuf>> {
    let path = derived_single_part_path(data_root, dataset, run_tag);
    if !path.exists() {
        return Ok(None);
    }
    if parquet_schema_matches(&path, expected_schema.as_ref())? {
        Ok(Some(path))
    } else {
        bail!(
            "cached parquet part exists but schema does not match current {} schema: {}",
            dataset,
            path.display()
        );
    }
}

fn parquet_schema_matches(path: &Path, expected: &Schema) -> Result<bool> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(1)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    let Some(batch) = reader.next() else {
        return Ok(false);
    };
    let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
    Ok(schemas_compatible(batch.schema().as_ref(), expected))
}

fn schemas_compatible(actual: &Schema, expected: &Schema) -> bool {
    if actual.fields().len() != expected.fields().len() {
        return false;
    }
    actual
        .fields()
        .iter()
        .zip(expected.fields().iter())
        .all(|(actual, expected)| {
            actual.name() == expected.name()
                && actual.data_type() == expected.data_type()
                && actual.is_nullable() == expected.is_nullable()
        })
}

fn read_execution_rows(
    files: &[PathBuf],
    source_run_tag: &str,
    progress_interval: usize,
) -> Result<Vec<ExecutionEventRow>> {
    let mut rows = Vec::new();
    for (file_index, path) in files.iter().enumerate() {
        if progress_interval > 0 && (file_index == 0 || (file_index + 1) % progress_interval == 0) {
            eprintln!(
                "[mon_usdc_event_factor_search] reading execution feature part {}/{}",
                file_index + 1,
                files.len()
            );
        }
        read_parquet_batches(path, |batch| {
            let run_tag = string_column(batch, "run_tag")?;
            let block_number = u64_column(batch, "block_number")?;
            let event_time_utc = string_column(batch, "event_time_utc")?;
            let transaction_hash = string_column(batch, "transaction_hash")?;
            let transaction_index = u64_column(batch, "transaction_index")?;
            let log_index = u64_column(batch, "log_index")?;
            let pool_address = string_column(batch, "pool_address")?;
            let dex_id = string_column(batch, "dex_id")?;
            let family = string_column(batch, "family")?;
            let direction = string_column(batch, "direction")?;
            let base_abs = f64_column(batch, "base_abs")?;
            let quote_abs = f64_column(batch, "quote_abs")?;
            let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
            let receipt_gas_used = u64_column(batch, "receipt_gas_used")?;
            let effective_gas_price = u64_column(batch, "effective_gas_price")?;
            let base_fee_per_gas = u64_column(batch, "base_fee_per_gas")?;
            let same_block_event_count = u64_column(batch, "same_block_event_count")?;
            let fwd_return_5m = f64_column(batch, "fwd_return_5m")?;
            let fwd_return_15m = f64_column(batch, "fwd_return_15m")?;
            let fwd_return_1h = f64_column(batch, "fwd_return_1h")?;
            let fwd_return_3h = f64_column(batch, "fwd_return_3h")?;
            let fwd_return_6h = f64_column(batch, "fwd_return_6h")?;
            let pool_dislocation_bps = f64_column(batch, "pool_dislocation_bps")?;
            let tx_path_source = string_column(batch, "tx_path_source")?;
            let tx_path_confidence = string_column(batch, "tx_path_confidence")?;
            let pool_pre_state_age_blocks = u64_column(batch, "pool_pre_state_age_blocks")?;
            let trace_path_class = string_column(batch, "trace_path_class")?;
            let trace_source = string_column(batch, "trace_source")?;
            let trace_confidence = string_column(batch, "trace_confidence")?;
            let quality_tier = string_column(batch, "quality_tier")?;
            let usable_for_execution_research =
                bool_column(batch, "usable_for_execution_research")?;

            for index in 0..batch.num_rows() {
                let row_run_tag = string_value(run_tag, index);
                if row_run_tag != source_run_tag {
                    bail!(
                        "run_tag mismatch in {}: expected {source_run_tag}, found {row_run_tag}",
                        path.display()
                    );
                }
                let time = string_value(event_time_utc, index);
                let timestamp = parse_event_timestamp(&time)?;
                rows.push(ExecutionEventRow {
                    block_number: u64_value(block_number, index),
                    timestamp,
                    event_time_utc: time,
                    date_utc: utc_string(timestamp)?.get(..10).unwrap_or("").to_string(),
                    hour_utc: format_hour(timestamp)?,
                    transaction_hash: string_value(transaction_hash, index),
                    transaction_index: u64_value(transaction_index, index),
                    log_index: u64_value(log_index, index),
                    pool_address: string_value(pool_address, index),
                    dex_id: string_value(dex_id, index),
                    family: string_value(family, index),
                    direction: string_value(direction, index),
                    base_abs: f64_option(base_abs, index),
                    quote_abs: f64_option(quote_abs, index),
                    price_quote_per_base: f64_option(price_quote_per_base, index),
                    receipt_gas_used: u64_option(receipt_gas_used, index),
                    effective_gas_price: u64_option(effective_gas_price, index),
                    base_fee_per_gas: u64_option(base_fee_per_gas, index),
                    same_block_event_count: u64_value(same_block_event_count, index),
                    fwd_return_5m: f64_option(fwd_return_5m, index),
                    fwd_return_15m: f64_option(fwd_return_15m, index),
                    fwd_return_1h: f64_option(fwd_return_1h, index),
                    fwd_return_3h: f64_option(fwd_return_3h, index),
                    fwd_return_6h: f64_option(fwd_return_6h, index),
                    pool_dislocation_bps: f64_option(pool_dislocation_bps, index),
                    tx_path_source: string_value(tx_path_source, index),
                    tx_path_confidence: string_value(tx_path_confidence, index),
                    pool_pre_state_age_blocks: u64_option(pool_pre_state_age_blocks, index),
                    trace_path_class: string_value(trace_path_class, index),
                    trace_source: string_value(trace_source, index),
                    trace_confidence: string_value(trace_confidence, index),
                    quality_tier: string_value(quality_tier, index),
                    usable_for_execution_research: bool_value(usable_for_execution_research, index),
                });
            }
            Ok(())
        })?;
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

fn read_tx_path_rows(files: &[PathBuf], source_run_tag: &str) -> Result<Vec<TxPathRow>> {
    let mut rows = Vec::new();
    for path in files {
        read_parquet_batches(path, |batch| {
            let run_tag = string_column(batch, "run_tag")?;
            let transaction_hash = string_column(batch, "transaction_hash")?;
            let pool_count = u64_column(batch, "pool_count")?;
            let swap_count = u64_column(batch, "swap_count")?;
            let tx_path_source = string_column(batch, "tx_path_source")?;
            let tx_path_confidence = string_column(batch, "tx_path_confidence")?;
            for index in 0..batch.num_rows() {
                let row_run_tag = string_value(run_tag, index);
                if row_run_tag != source_run_tag {
                    bail!(
                        "run_tag mismatch in {}: expected {source_run_tag}, found {row_run_tag}",
                        path.display()
                    );
                }
                rows.push(TxPathRow {
                    transaction_hash: string_value(transaction_hash, index),
                    pool_count: u64_value(pool_count, index),
                    swap_count: u64_value(swap_count, index),
                    tx_path_source: string_value(tx_path_source, index),
                    tx_path_confidence: string_value(tx_path_confidence, index),
                });
            }
            Ok(())
        })?;
    }
    Ok(rows)
}

fn read_pool_state_rows(files: &[PathBuf], source_run_tag: &str) -> Result<Vec<PoolStateProxyRow>> {
    let mut rows = Vec::new();
    for path in files {
        read_parquet_batches(path, |batch| {
            let run_tag = string_column(batch, "run_tag")?;
            let block_number = u64_column(batch, "block_number")?;
            let transaction_hash = string_column(batch, "transaction_hash")?;
            let log_index = u64_column(batch, "log_index")?;
            let pool_address = string_column(batch, "pool_address")?;
            let event_state_source = string_column(batch, "event_state_source")?;
            let event_state_confidence = string_column(batch, "event_state_confidence")?;
            let pre_state_age_blocks = u64_column(batch, "pre_state_age_blocks")?;
            let liquidity_pressure = f64_column(batch, "event_notional_to_active_liquidity_proxy")?;
            for index in 0..batch.num_rows() {
                let row_run_tag = string_value(run_tag, index);
                if row_run_tag != source_run_tag {
                    bail!(
                        "run_tag mismatch in {}: expected {source_run_tag}, found {row_run_tag}",
                        path.display()
                    );
                }
                rows.push(PoolStateProxyRow {
                    key: EventKey {
                        block_number: u64_value(block_number, index),
                        transaction_hash: string_value(transaction_hash, index),
                        log_index: u64_value(log_index, index),
                        pool_address: string_value(pool_address, index),
                    },
                    event_state_source: string_value(event_state_source, index),
                    event_state_confidence: string_value(event_state_confidence, index),
                    pre_state_age_blocks: u64_option(pre_state_age_blocks, index),
                    liquidity_pressure: f64_option(liquidity_pressure, index),
                });
            }
            Ok(())
        })?;
    }
    Ok(rows)
}

fn read_physical_feature_rows(
    path: &Path,
    run_tag_expected: &str,
    source_run_tag_expected: &str,
) -> Result<Vec<PhysicalFeatureRow>> {
    let mut rows = Vec::new();
    read_parquet_batches(path, |batch| {
        let run_tag = string_column(batch, "run_tag")?;
        let source_run_tag = string_column(batch, "source_run_tag")?;
        let block_number = u64_column(batch, "block_number")?;
        let event_time_utc = string_column(batch, "event_time_utc")?;
        let date_utc = string_column(batch, "date_utc")?;
        let hour_utc = string_column(batch, "hour_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let transaction_index = u64_column(batch, "transaction_index")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let dex_id = string_column(batch, "dex_id")?;
        let family = string_column(batch, "family")?;
        let direction = string_column(batch, "direction")?;
        let quality_tier = string_column(batch, "quality_tier")?;
        let research_sample_included = bool_column(batch, "research_sample_included")?;
        let base_abs = f64_column(batch, "base_abs")?;
        let quote_abs = f64_column(batch, "quote_abs")?;
        let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
        let signed_quote_flow = f64_column(batch, "signed_quote_flow")?;
        let signed_quote_flow_source = string_column(batch, "signed_quote_flow_source")?;
        let signed_quote_flow_confidence = string_column(batch, "signed_quote_flow_confidence")?;
        let liquidity_pressure = f64_column(batch, "liquidity_pressure")?;
        let liquidity_pressure_source = string_column(batch, "liquidity_pressure_source")?;
        let liquidity_pressure_confidence = string_column(batch, "liquidity_pressure_confidence")?;
        let gas_pressure = f64_column(batch, "gas_pressure")?;
        let roundtrip_gas_return_proxy = f64_column(batch, "roundtrip_gas_return_proxy")?;
        let gas_pressure_source = string_column(batch, "gas_pressure_source")?;
        let gas_pressure_confidence = string_column(batch, "gas_pressure_confidence")?;
        let crowding = f64_column(batch, "crowding")?;
        let crowding_source = string_column(batch, "crowding_source")?;
        let crowding_confidence = string_column(batch, "crowding_confidence")?;
        let dislocation_return = f64_column(batch, "dislocation_return")?;
        let dislocation_source = string_column(batch, "dislocation_source")?;
        let dislocation_confidence = string_column(batch, "dislocation_confidence")?;
        let pool_pre_state_age_blocks = u64_column(batch, "pool_pre_state_age_blocks")?;
        let pool_quote_hhi = f64_column(batch, "pool_quote_hhi")?;
        let pool_quote_hhi_source = string_column(batch, "pool_quote_hhi_source")?;
        let pool_quote_hhi_confidence = string_column(batch, "pool_quote_hhi_confidence")?;
        let trailing_realized_vol_1h = f64_column(batch, "trailing_realized_vol_1h")?;
        let trailing_realized_vol_6h = f64_column(batch, "trailing_realized_vol_6h")?;
        let volatility_source = string_column(batch, "volatility_source")?;
        let volatility_confidence = string_column(batch, "volatility_confidence")?;
        let tx_pool_count = u64_column(batch, "tx_pool_count")?;
        let tx_swap_count = u64_column(batch, "tx_swap_count")?;
        let tx_path_source = string_column(batch, "tx_path_source")?;
        let tx_path_confidence = string_column(batch, "tx_path_confidence")?;
        let receipt_gas_used = u64_column(batch, "receipt_gas_used")?;
        let effective_gas_price = u64_column(batch, "effective_gas_price")?;
        let base_fee_per_gas = u64_column(batch, "base_fee_per_gas")?;
        let same_block_event_count = u64_column(batch, "same_block_event_count")?;
        let trace_path_class = string_column(batch, "trace_path_class")?;
        let trace_source = string_column(batch, "trace_source")?;
        let trace_confidence = string_column(batch, "trace_confidence")?;

        for index in 0..batch.num_rows() {
            validate_run_tags(
                path,
                string_value(run_tag, index),
                run_tag_expected,
                string_value(source_run_tag, index),
                source_run_tag_expected,
            )?;
            rows.push(PhysicalFeatureRow {
                run_tag: run_tag_expected.to_string(),
                source_run_tag: source_run_tag_expected.to_string(),
                block_number: u64_value(block_number, index),
                event_time_utc: string_value(event_time_utc, index),
                date_utc: string_value(date_utc, index),
                hour_utc: string_value(hour_utc, index),
                transaction_hash: string_value(transaction_hash, index),
                transaction_index: u64_value(transaction_index, index),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                direction: string_value(direction, index),
                quality_tier: string_value(quality_tier, index),
                research_sample_included: bool_value(research_sample_included, index),
                base_abs: f64_option(base_abs, index),
                quote_abs: f64_option(quote_abs, index),
                price_quote_per_base: f64_option(price_quote_per_base, index),
                signed_quote_flow: f64_option(signed_quote_flow, index),
                signed_quote_flow_source: string_value(signed_quote_flow_source, index),
                signed_quote_flow_confidence: string_value(signed_quote_flow_confidence, index),
                liquidity_pressure: f64_option(liquidity_pressure, index),
                liquidity_pressure_source: string_value(liquidity_pressure_source, index),
                liquidity_pressure_confidence: string_value(liquidity_pressure_confidence, index),
                gas_pressure: f64_option(gas_pressure, index),
                roundtrip_gas_return_proxy: f64_option(roundtrip_gas_return_proxy, index),
                gas_pressure_source: string_value(gas_pressure_source, index),
                gas_pressure_confidence: string_value(gas_pressure_confidence, index),
                crowding: f64_option(crowding, index),
                crowding_source: string_value(crowding_source, index),
                crowding_confidence: string_value(crowding_confidence, index),
                dislocation_return: f64_option(dislocation_return, index),
                dislocation_source: string_value(dislocation_source, index),
                dislocation_confidence: string_value(dislocation_confidence, index),
                pool_pre_state_age_blocks: u64_option(pool_pre_state_age_blocks, index),
                pool_quote_hhi: f64_option(pool_quote_hhi, index),
                pool_quote_hhi_source: string_value(pool_quote_hhi_source, index),
                pool_quote_hhi_confidence: string_value(pool_quote_hhi_confidence, index),
                trailing_realized_vol_1h: f64_option(trailing_realized_vol_1h, index),
                trailing_realized_vol_6h: f64_option(trailing_realized_vol_6h, index),
                volatility_source: string_value(volatility_source, index),
                volatility_confidence: string_value(volatility_confidence, index),
                tx_pool_count: u64_option(tx_pool_count, index),
                tx_swap_count: u64_option(tx_swap_count, index),
                tx_path_source: string_value(tx_path_source, index),
                tx_path_confidence: string_value(tx_path_confidence, index),
                receipt_gas_used: u64_option(receipt_gas_used, index),
                effective_gas_price: u64_option(effective_gas_price, index),
                base_fee_per_gas: u64_option(base_fee_per_gas, index),
                same_block_event_count: u64_value(same_block_event_count, index),
                trace_path_class: string_value(trace_path_class, index),
                trace_source: string_value(trace_source, index),
                trace_confidence: string_value(trace_confidence, index),
            });
        }
        Ok(())
    })?;
    if rows.is_empty() {
        bail!("cached physical feature part is empty: {}", path.display());
    }
    Ok(rows)
}

fn read_cost_label_rows(
    path: &Path,
    run_tag_expected: &str,
    source_run_tag_expected: &str,
    assumed_fee_bps_one_way_expected: f64,
) -> Result<Vec<CostLabelRow>> {
    let mut rows = Vec::new();
    read_parquet_batches(path, |batch| {
        let run_tag = string_column(batch, "run_tag")?;
        let source_run_tag = string_column(batch, "source_run_tag")?;
        let block_number = u64_column(batch, "block_number")?;
        let event_time_utc = string_column(batch, "event_time_utc")?;
        let date_utc = string_column(batch, "date_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let direction = string_column(batch, "direction")?;
        let quality_tier = string_column(batch, "quality_tier")?;
        let cost_label_type = string_column(batch, "cost_label_type")?;
        let assumed_fee_bps_one_way = f64_column(batch, "assumed_fee_bps_one_way")?;
        let fee_source = string_column(batch, "fee_source")?;
        let roundtrip_gas_return_proxy = f64_column(batch, "roundtrip_gas_return_proxy")?;
        let roundtrip_gas_source = string_column(batch, "roundtrip_gas_source")?;
        let market_gross_return_5m = f64_column(batch, "market_gross_return_5m")?;
        let market_gross_return_15m = f64_column(batch, "market_gross_return_15m")?;
        let market_gross_return_1h = f64_column(batch, "market_gross_return_1h")?;
        let market_gross_return_3h = f64_column(batch, "market_gross_return_3h")?;
        let market_gross_return_6h = f64_column(batch, "market_gross_return_6h")?;
        let side_gross_return_5m = f64_column(batch, "side_gross_return_5m")?;
        let side_gross_return_15m = f64_column(batch, "side_gross_return_15m")?;
        let side_gross_return_1h = f64_column(batch, "side_gross_return_1h")?;
        let side_gross_return_3h = f64_column(batch, "side_gross_return_3h")?;
        let side_gross_return_6h = f64_column(batch, "side_gross_return_6h")?;
        let net_return_5m_slip0bps = f64_column(batch, "net_return_5m_slip0bps")?;
        let net_return_5m_slip25bps = f64_column(batch, "net_return_5m_slip25bps")?;
        let net_return_5m_slip100bps = f64_column(batch, "net_return_5m_slip100bps")?;
        let net_return_15m_slip0bps = f64_column(batch, "net_return_15m_slip0bps")?;
        let net_return_15m_slip25bps = f64_column(batch, "net_return_15m_slip25bps")?;
        let net_return_15m_slip100bps = f64_column(batch, "net_return_15m_slip100bps")?;
        let net_return_1h_slip0bps = f64_column(batch, "net_return_1h_slip0bps")?;
        let net_return_1h_slip25bps = f64_column(batch, "net_return_1h_slip25bps")?;
        let net_return_1h_slip100bps = f64_column(batch, "net_return_1h_slip100bps")?;
        let net_return_3h_slip0bps = f64_column(batch, "net_return_3h_slip0bps")?;
        let net_return_3h_slip25bps = f64_column(batch, "net_return_3h_slip25bps")?;
        let net_return_3h_slip100bps = f64_column(batch, "net_return_3h_slip100bps")?;
        let net_return_6h_slip0bps = f64_column(batch, "net_return_6h_slip0bps")?;
        let net_return_6h_slip25bps = f64_column(batch, "net_return_6h_slip25bps")?;
        let net_return_6h_slip100bps = f64_column(batch, "net_return_6h_slip100bps")?;

        for index in 0..batch.num_rows() {
            validate_run_tags(
                path,
                string_value(run_tag, index),
                run_tag_expected,
                string_value(source_run_tag, index),
                source_run_tag_expected,
            )?;
            let fee_bps = f64_value(assumed_fee_bps_one_way, index);
            if (fee_bps - assumed_fee_bps_one_way_expected).abs() > 1e-9 {
                bail!(
                    "cached cost label fee mismatch in {}: expected {}, found {}",
                    path.display(),
                    assumed_fee_bps_one_way_expected,
                    fee_bps
                );
            }
            rows.push(CostLabelRow {
                run_tag: run_tag_expected.to_string(),
                source_run_tag: source_run_tag_expected.to_string(),
                block_number: u64_value(block_number, index),
                event_time_utc: string_value(event_time_utc, index),
                date_utc: string_value(date_utc, index),
                transaction_hash: string_value(transaction_hash, index),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index),
                direction: string_value(direction, index),
                quality_tier: string_value(quality_tier, index),
                cost_label_type: string_value(cost_label_type, index),
                assumed_fee_bps_one_way: fee_bps,
                fee_source: string_value(fee_source, index),
                roundtrip_gas_return_proxy: f64_option(roundtrip_gas_return_proxy, index),
                roundtrip_gas_source: string_value(roundtrip_gas_source, index),
                market_gross_return_5m: f64_option(market_gross_return_5m, index),
                market_gross_return_15m: f64_option(market_gross_return_15m, index),
                market_gross_return_1h: f64_option(market_gross_return_1h, index),
                market_gross_return_3h: f64_option(market_gross_return_3h, index),
                market_gross_return_6h: f64_option(market_gross_return_6h, index),
                side_gross_return_5m: f64_option(side_gross_return_5m, index),
                side_gross_return_15m: f64_option(side_gross_return_15m, index),
                side_gross_return_1h: f64_option(side_gross_return_1h, index),
                side_gross_return_3h: f64_option(side_gross_return_3h, index),
                side_gross_return_6h: f64_option(side_gross_return_6h, index),
                net_return_5m_slip0bps: f64_option(net_return_5m_slip0bps, index),
                net_return_5m_slip25bps: f64_option(net_return_5m_slip25bps, index),
                net_return_5m_slip100bps: f64_option(net_return_5m_slip100bps, index),
                net_return_15m_slip0bps: f64_option(net_return_15m_slip0bps, index),
                net_return_15m_slip25bps: f64_option(net_return_15m_slip25bps, index),
                net_return_15m_slip100bps: f64_option(net_return_15m_slip100bps, index),
                net_return_1h_slip0bps: f64_option(net_return_1h_slip0bps, index),
                net_return_1h_slip25bps: f64_option(net_return_1h_slip25bps, index),
                net_return_1h_slip100bps: f64_option(net_return_1h_slip100bps, index),
                net_return_3h_slip0bps: f64_option(net_return_3h_slip0bps, index),
                net_return_3h_slip25bps: f64_option(net_return_3h_slip25bps, index),
                net_return_3h_slip100bps: f64_option(net_return_3h_slip100bps, index),
                net_return_6h_slip0bps: f64_option(net_return_6h_slip0bps, index),
                net_return_6h_slip25bps: f64_option(net_return_6h_slip25bps, index),
                net_return_6h_slip100bps: f64_option(net_return_6h_slip100bps, index),
            });
        }
        Ok(())
    })?;
    if rows.is_empty() {
        bail!("cached cost label part is empty: {}", path.display());
    }
    Ok(rows)
}

fn read_factor_candidate_rows(
    path: &Path,
    run_tag_expected: &str,
    source_run_tag_expected: &str,
) -> Result<Vec<FactorCandidateRow>> {
    let mut rows = Vec::new();
    read_parquet_batches(path, |batch| {
        let run_tag = string_column(batch, "run_tag")?;
        let source_run_tag = string_column(batch, "source_run_tag")?;
        let block_number = u64_column(batch, "block_number")?;
        let event_time_utc = string_column(batch, "event_time_utc")?;
        let date_utc = string_column(batch, "date_utc")?;
        let split = string_column(batch, "split")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let dex_id = string_column(batch, "dex_id")?;
        let family = string_column(batch, "family")?;
        let direction = string_column(batch, "direction")?;
        let quality_tier = string_column(batch, "quality_tier")?;
        let volatility_regime = string_column(batch, "volatility_regime")?;
        let quote_notional_bucket = string_column(batch, "quote_notional_bucket")?;
        let quote_abs = f64_column(batch, "quote_abs")?;
        let signed_quote_flow = f64_column(batch, "signed_quote_flow")?;
        let liquidity_proxy = f64_column(batch, "liquidity_proxy")?;
        let log1p_quote_abs = f64_column(batch, "log1p_quote_abs")?;
        let sqrt_quote_abs = f64_column(batch, "sqrt_quote_abs")?;
        let signed_quote_flow_over_log_abs = f64_column(batch, "signed_quote_flow_over_log_abs")?;
        let signed_quote_flow_times_log_abs = f64_column(batch, "signed_quote_flow_times_log_abs")?;
        let quote_abs_over_liquidity = f64_column(batch, "quote_abs_over_liquidity")?;
        let flow_over_liquidity = f64_column(batch, "flow_over_liquidity")?;
        let flow_over_sqrt_liquidity = f64_column(batch, "flow_over_sqrt_liquidity")?;
        let dislocation_over_vol_1h = f64_column(batch, "dislocation_over_vol_1h")?;
        let dislocation_over_vol_6h = f64_column(batch, "dislocation_over_vol_6h")?;
        let gas_over_quote_abs = f64_column(batch, "gas_over_quote_abs")?;
        let quote_abs_over_log_liquidity = f64_column(batch, "quote_abs_over_log_liquidity")?;
        let age_times_dislocation = f64_column(batch, "age_times_dislocation")?;
        let dislocation_over_log_quote_abs = f64_column(batch, "dislocation_over_log_quote_abs")?;
        let liquidity_pressure = f64_column(batch, "liquidity_pressure")?;
        let gas_pressure = f64_column(batch, "gas_pressure")?;
        let crowding = f64_column(batch, "crowding")?;
        let pool_quote_hhi = f64_column(batch, "pool_quote_hhi")?;
        let trailing_realized_vol_1h = f64_column(batch, "trailing_realized_vol_1h")?;
        let trailing_realized_vol_6h = f64_column(batch, "trailing_realized_vol_6h")?;
        let same_block_event_count = f64_column(batch, "same_block_event_count")?;

        for index in 0..batch.num_rows() {
            validate_run_tags(
                path,
                string_value(run_tag, index),
                run_tag_expected,
                string_value(source_run_tag, index),
                source_run_tag_expected,
            )?;
            rows.push(FactorCandidateRow {
                run_tag: run_tag_expected.to_string(),
                source_run_tag: source_run_tag_expected.to_string(),
                block_number: u64_value(block_number, index),
                event_time_utc: string_value(event_time_utc, index),
                date_utc: string_value(date_utc, index),
                split: string_value(split, index),
                transaction_hash: string_value(transaction_hash, index),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                direction: string_value(direction, index),
                quality_tier: string_value(quality_tier, index),
                volatility_regime: string_value(volatility_regime, index),
                quote_notional_bucket: string_value(quote_notional_bucket, index),
                quote_abs: f64_option(quote_abs, index),
                signed_quote_flow: f64_option(signed_quote_flow, index),
                liquidity_proxy: f64_option(liquidity_proxy, index),
                log1p_quote_abs: f64_option(log1p_quote_abs, index),
                sqrt_quote_abs: f64_option(sqrt_quote_abs, index),
                signed_quote_flow_over_log_abs: f64_option(signed_quote_flow_over_log_abs, index),
                signed_quote_flow_times_log_abs: f64_option(signed_quote_flow_times_log_abs, index),
                quote_abs_over_liquidity: f64_option(quote_abs_over_liquidity, index),
                flow_over_liquidity: f64_option(flow_over_liquidity, index),
                flow_over_sqrt_liquidity: f64_option(flow_over_sqrt_liquidity, index),
                dislocation_over_vol_1h: f64_option(dislocation_over_vol_1h, index),
                dislocation_over_vol_6h: f64_option(dislocation_over_vol_6h, index),
                gas_over_quote_abs: f64_option(gas_over_quote_abs, index),
                quote_abs_over_log_liquidity: f64_option(quote_abs_over_log_liquidity, index),
                age_times_dislocation: f64_option(age_times_dislocation, index),
                dislocation_over_log_quote_abs: f64_option(dislocation_over_log_quote_abs, index),
                liquidity_pressure: f64_option(liquidity_pressure, index),
                gas_pressure: f64_option(gas_pressure, index),
                crowding: f64_option(crowding, index),
                pool_quote_hhi: f64_option(pool_quote_hhi, index),
                trailing_realized_vol_1h: f64_option(trailing_realized_vol_1h, index),
                trailing_realized_vol_6h: f64_option(trailing_realized_vol_6h, index),
                same_block_event_count: f64_option(same_block_event_count, index),
            });
        }
        Ok(())
    })?;
    if rows.is_empty() {
        bail!("cached factor candidate part is empty: {}", path.display());
    }
    Ok(rows)
}

fn validate_run_tags(
    path: &Path,
    run_tag_found: String,
    run_tag_expected: &str,
    source_run_tag_found: String,
    source_run_tag_expected: &str,
) -> Result<()> {
    if run_tag_found != run_tag_expected {
        bail!(
            "run_tag mismatch in {}: expected {}, found {}",
            path.display(),
            run_tag_expected,
            run_tag_found
        );
    }
    if source_run_tag_found != source_run_tag_expected {
        bail!(
            "source_run_tag mismatch in {}: expected {}, found {}",
            path.display(),
            source_run_tag_expected,
            source_run_tag_found
        );
    }
    Ok(())
}

fn read_parquet_batches<F>(path: &Path, mut on_batch: F) -> Result<()>
where
    F: FnMut(&RecordBatch) -> Result<()>,
{
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
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
    Ok(())
}

fn write_physical_features_parquet(
    data_root: &Path,
    rows: &[PhysicalFeatureRow],
    run_tag: &str,
) -> Result<PathBuf> {
    let schema = physical_features_schema();
    write_schema_metadata(
        data_root,
        PHYSICAL_FEATURES_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            strings(rows.iter().map(|row| row.source_run_tag.clone())),
            u64s(rows.iter().map(|row| row.block_number)),
            strings(rows.iter().map(|row| row.event_time_utc.clone())),
            strings(rows.iter().map(|row| row.date_utc.clone())),
            strings(rows.iter().map(|row| row.hour_utc.clone())),
            strings(rows.iter().map(|row| row.transaction_hash.clone())),
            u64s(rows.iter().map(|row| row.transaction_index)),
            u64s(rows.iter().map(|row| row.log_index)),
            strings(rows.iter().map(|row| row.pool_address.clone())),
            strings(rows.iter().map(|row| row.dex_id.clone())),
            strings(rows.iter().map(|row| row.family.clone())),
            strings(rows.iter().map(|row| row.direction.clone())),
            strings(rows.iter().map(|row| row.quality_tier.clone())),
            bools(rows.iter().map(|row| row.research_sample_included)),
            opt_f64s(rows.iter().map(|row| row.base_abs)),
            opt_f64s(rows.iter().map(|row| row.quote_abs)),
            opt_f64s(rows.iter().map(|row| row.price_quote_per_base)),
            opt_f64s(rows.iter().map(|row| row.signed_quote_flow)),
            strings(rows.iter().map(|row| row.signed_quote_flow_source.clone())),
            strings(
                rows.iter()
                    .map(|row| row.signed_quote_flow_confidence.clone()),
            ),
            opt_f64s(rows.iter().map(|row| row.liquidity_pressure)),
            strings(rows.iter().map(|row| row.liquidity_pressure_source.clone())),
            strings(
                rows.iter()
                    .map(|row| row.liquidity_pressure_confidence.clone()),
            ),
            opt_f64s(rows.iter().map(|row| row.gas_pressure)),
            opt_f64s(rows.iter().map(|row| row.roundtrip_gas_return_proxy)),
            strings(rows.iter().map(|row| row.gas_pressure_source.clone())),
            strings(rows.iter().map(|row| row.gas_pressure_confidence.clone())),
            opt_f64s(rows.iter().map(|row| row.crowding)),
            strings(rows.iter().map(|row| row.crowding_source.clone())),
            strings(rows.iter().map(|row| row.crowding_confidence.clone())),
            opt_f64s(rows.iter().map(|row| row.dislocation_return)),
            strings(rows.iter().map(|row| row.dislocation_source.clone())),
            strings(rows.iter().map(|row| row.dislocation_confidence.clone())),
            opt_u64s(rows.iter().map(|row| row.pool_pre_state_age_blocks)),
            opt_f64s(rows.iter().map(|row| row.pool_quote_hhi)),
            strings(rows.iter().map(|row| row.pool_quote_hhi_source.clone())),
            strings(rows.iter().map(|row| row.pool_quote_hhi_confidence.clone())),
            opt_f64s(rows.iter().map(|row| row.trailing_realized_vol_1h)),
            opt_f64s(rows.iter().map(|row| row.trailing_realized_vol_6h)),
            strings(rows.iter().map(|row| row.volatility_source.clone())),
            strings(rows.iter().map(|row| row.volatility_confidence.clone())),
            opt_u64s(rows.iter().map(|row| row.tx_pool_count)),
            opt_u64s(rows.iter().map(|row| row.tx_swap_count)),
            strings(rows.iter().map(|row| row.tx_path_source.clone())),
            strings(rows.iter().map(|row| row.tx_path_confidence.clone())),
            opt_u64s(rows.iter().map(|row| row.receipt_gas_used)),
            opt_u64s(rows.iter().map(|row| row.effective_gas_price)),
            opt_u64s(rows.iter().map(|row| row.base_fee_per_gas)),
            u64s(rows.iter().map(|row| row.same_block_event_count)),
            strings(rows.iter().map(|row| row.trace_path_class.clone())),
            strings(rows.iter().map(|row| row.trace_source.clone())),
            strings(rows.iter().map(|row| row.trace_confidence.clone())),
        ],
    )?;
    write_single_part(data_root, PHYSICAL_FEATURES_DATASET, schema, batch, run_tag)
}

fn write_cost_labels_parquet(
    data_root: &Path,
    rows: &[CostLabelRow],
    run_tag: &str,
) -> Result<PathBuf> {
    let schema = cost_labels_schema();
    write_schema_metadata(data_root, COST_LABELS_DATASET, schema.as_ref(), &["dt"])?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            strings(rows.iter().map(|row| row.source_run_tag.clone())),
            u64s(rows.iter().map(|row| row.block_number)),
            strings(rows.iter().map(|row| row.event_time_utc.clone())),
            strings(rows.iter().map(|row| row.date_utc.clone())),
            strings(rows.iter().map(|row| row.transaction_hash.clone())),
            u64s(rows.iter().map(|row| row.log_index)),
            strings(rows.iter().map(|row| row.pool_address.clone())),
            strings(rows.iter().map(|row| row.direction.clone())),
            strings(rows.iter().map(|row| row.quality_tier.clone())),
            strings(rows.iter().map(|row| row.cost_label_type.clone())),
            f64s(rows.iter().map(|row| row.assumed_fee_bps_one_way)),
            strings(rows.iter().map(|row| row.fee_source.clone())),
            opt_f64s(rows.iter().map(|row| row.roundtrip_gas_return_proxy)),
            strings(rows.iter().map(|row| row.roundtrip_gas_source.clone())),
            opt_f64s(rows.iter().map(|row| row.market_gross_return_5m)),
            opt_f64s(rows.iter().map(|row| row.market_gross_return_15m)),
            opt_f64s(rows.iter().map(|row| row.market_gross_return_1h)),
            opt_f64s(rows.iter().map(|row| row.market_gross_return_3h)),
            opt_f64s(rows.iter().map(|row| row.market_gross_return_6h)),
            opt_f64s(rows.iter().map(|row| row.side_gross_return_5m)),
            opt_f64s(rows.iter().map(|row| row.side_gross_return_15m)),
            opt_f64s(rows.iter().map(|row| row.side_gross_return_1h)),
            opt_f64s(rows.iter().map(|row| row.side_gross_return_3h)),
            opt_f64s(rows.iter().map(|row| row.side_gross_return_6h)),
            opt_f64s(rows.iter().map(|row| row.net_return_5m_slip0bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_5m_slip25bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_5m_slip100bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_15m_slip0bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_15m_slip25bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_15m_slip100bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_1h_slip0bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_1h_slip25bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_1h_slip100bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_3h_slip0bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_3h_slip25bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_3h_slip100bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_6h_slip0bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_6h_slip25bps)),
            opt_f64s(rows.iter().map(|row| row.net_return_6h_slip100bps)),
        ],
    )?;
    write_single_part(data_root, COST_LABELS_DATASET, schema, batch, run_tag)
}

fn write_factor_candidates_parquet(
    data_root: &Path,
    rows: &[FactorCandidateRow],
    run_tag: &str,
) -> Result<PathBuf> {
    let schema = factor_candidates_schema();
    write_schema_metadata(
        data_root,
        FACTOR_CANDIDATES_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            strings(rows.iter().map(|row| row.source_run_tag.clone())),
            u64s(rows.iter().map(|row| row.block_number)),
            strings(rows.iter().map(|row| row.event_time_utc.clone())),
            strings(rows.iter().map(|row| row.date_utc.clone())),
            strings(rows.iter().map(|row| row.split.clone())),
            strings(rows.iter().map(|row| row.transaction_hash.clone())),
            u64s(rows.iter().map(|row| row.log_index)),
            strings(rows.iter().map(|row| row.pool_address.clone())),
            strings(rows.iter().map(|row| row.dex_id.clone())),
            strings(rows.iter().map(|row| row.family.clone())),
            strings(rows.iter().map(|row| row.direction.clone())),
            strings(rows.iter().map(|row| row.quality_tier.clone())),
            strings(rows.iter().map(|row| row.volatility_regime.clone())),
            strings(rows.iter().map(|row| row.quote_notional_bucket.clone())),
            opt_f64s(rows.iter().map(|row| row.quote_abs)),
            opt_f64s(rows.iter().map(|row| row.signed_quote_flow)),
            opt_f64s(rows.iter().map(|row| row.liquidity_proxy)),
            opt_f64s(rows.iter().map(|row| row.log1p_quote_abs)),
            opt_f64s(rows.iter().map(|row| row.sqrt_quote_abs)),
            opt_f64s(rows.iter().map(|row| row.signed_quote_flow_over_log_abs)),
            opt_f64s(rows.iter().map(|row| row.signed_quote_flow_times_log_abs)),
            opt_f64s(rows.iter().map(|row| row.quote_abs_over_liquidity)),
            opt_f64s(rows.iter().map(|row| row.flow_over_liquidity)),
            opt_f64s(rows.iter().map(|row| row.flow_over_sqrt_liquidity)),
            opt_f64s(rows.iter().map(|row| row.dislocation_over_vol_1h)),
            opt_f64s(rows.iter().map(|row| row.dislocation_over_vol_6h)),
            opt_f64s(rows.iter().map(|row| row.gas_over_quote_abs)),
            opt_f64s(rows.iter().map(|row| row.quote_abs_over_log_liquidity)),
            opt_f64s(rows.iter().map(|row| row.age_times_dislocation)),
            opt_f64s(rows.iter().map(|row| row.dislocation_over_log_quote_abs)),
            opt_f64s(rows.iter().map(|row| row.liquidity_pressure)),
            opt_f64s(rows.iter().map(|row| row.gas_pressure)),
            opt_f64s(rows.iter().map(|row| row.crowding)),
            opt_f64s(rows.iter().map(|row| row.pool_quote_hhi)),
            opt_f64s(rows.iter().map(|row| row.trailing_realized_vol_1h)),
            opt_f64s(rows.iter().map(|row| row.trailing_realized_vol_6h)),
            opt_f64s(rows.iter().map(|row| row.same_block_event_count)),
        ],
    )?;
    write_single_part(data_root, FACTOR_CANDIDATES_DATASET, schema, batch, run_tag)
}

fn physical_features_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_utf8("source_run_tag", false),
        field_u64("block_number", false),
        field_utf8("event_time_utc", false),
        field_utf8("date_utc", false),
        field_utf8("hour_utc", false),
        field_utf8("transaction_hash", false),
        field_u64("transaction_index", false),
        field_u64("log_index", false),
        field_utf8("pool_address", false),
        field_utf8("dex_id", false),
        field_utf8("family", false),
        field_utf8("direction", false),
        field_utf8("quality_tier", false),
        Field::new("research_sample_included", DataType::Boolean, false),
        field_f64("base_abs", true),
        field_f64("quote_abs", true),
        field_f64("price_quote_per_base", true),
        field_f64("signed_quote_flow", true),
        field_utf8("signed_quote_flow_source", false),
        field_utf8("signed_quote_flow_confidence", false),
        field_f64("liquidity_pressure", true),
        field_utf8("liquidity_pressure_source", false),
        field_utf8("liquidity_pressure_confidence", false),
        field_f64("gas_pressure", true),
        field_f64("roundtrip_gas_return_proxy", true),
        field_utf8("gas_pressure_source", false),
        field_utf8("gas_pressure_confidence", false),
        field_f64("crowding", true),
        field_utf8("crowding_source", false),
        field_utf8("crowding_confidence", false),
        field_f64("dislocation_return", true),
        field_utf8("dislocation_source", false),
        field_utf8("dislocation_confidence", false),
        field_u64("pool_pre_state_age_blocks", true),
        field_f64("pool_quote_hhi", true),
        field_utf8("pool_quote_hhi_source", false),
        field_utf8("pool_quote_hhi_confidence", false),
        field_f64("trailing_realized_vol_1h", true),
        field_f64("trailing_realized_vol_6h", true),
        field_utf8("volatility_source", false),
        field_utf8("volatility_confidence", false),
        field_u64("tx_pool_count", true),
        field_u64("tx_swap_count", true),
        field_utf8("tx_path_source", false),
        field_utf8("tx_path_confidence", false),
        field_u64("receipt_gas_used", true),
        field_u64("effective_gas_price", true),
        field_u64("base_fee_per_gas", true),
        field_u64("same_block_event_count", false),
        field_utf8("trace_path_class", false),
        field_utf8("trace_source", false),
        field_utf8("trace_confidence", false),
    ]))
}

fn cost_labels_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_utf8("source_run_tag", false),
        field_u64("block_number", false),
        field_utf8("event_time_utc", false),
        field_utf8("date_utc", false),
        field_utf8("transaction_hash", false),
        field_u64("log_index", false),
        field_utf8("pool_address", false),
        field_utf8("direction", false),
        field_utf8("quality_tier", false),
        field_utf8("cost_label_type", false),
        field_f64("assumed_fee_bps_one_way", false),
        field_utf8("fee_source", false),
        field_f64("roundtrip_gas_return_proxy", true),
        field_utf8("roundtrip_gas_source", false),
        field_f64("market_gross_return_5m", true),
        field_f64("market_gross_return_15m", true),
        field_f64("market_gross_return_1h", true),
        field_f64("market_gross_return_3h", true),
        field_f64("market_gross_return_6h", true),
        field_f64("side_gross_return_5m", true),
        field_f64("side_gross_return_15m", true),
        field_f64("side_gross_return_1h", true),
        field_f64("side_gross_return_3h", true),
        field_f64("side_gross_return_6h", true),
        field_f64("net_return_5m_slip0bps", true),
        field_f64("net_return_5m_slip25bps", true),
        field_f64("net_return_5m_slip100bps", true),
        field_f64("net_return_15m_slip0bps", true),
        field_f64("net_return_15m_slip25bps", true),
        field_f64("net_return_15m_slip100bps", true),
        field_f64("net_return_1h_slip0bps", true),
        field_f64("net_return_1h_slip25bps", true),
        field_f64("net_return_1h_slip100bps", true),
        field_f64("net_return_3h_slip0bps", true),
        field_f64("net_return_3h_slip25bps", true),
        field_f64("net_return_3h_slip100bps", true),
        field_f64("net_return_6h_slip0bps", true),
        field_f64("net_return_6h_slip25bps", true),
        field_f64("net_return_6h_slip100bps", true),
    ]))
}

fn factor_candidates_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_utf8("source_run_tag", false),
        field_u64("block_number", false),
        field_utf8("event_time_utc", false),
        field_utf8("date_utc", false),
        field_utf8("split", false),
        field_utf8("transaction_hash", false),
        field_u64("log_index", false),
        field_utf8("pool_address", false),
        field_utf8("dex_id", false),
        field_utf8("family", false),
        field_utf8("direction", false),
        field_utf8("quality_tier", false),
        field_utf8("volatility_regime", false),
        field_utf8("quote_notional_bucket", false),
        field_f64("quote_abs", true),
        field_f64("signed_quote_flow", true),
        field_f64("liquidity_proxy", true),
        field_f64("log1p_quote_abs", true),
        field_f64("sqrt_quote_abs", true),
        field_f64("signed_quote_flow_over_log_abs", true),
        field_f64("signed_quote_flow_times_log_abs", true),
        field_f64("quote_abs_over_liquidity", true),
        field_f64("flow_over_liquidity", true),
        field_f64("flow_over_sqrt_liquidity", true),
        field_f64("dislocation_over_vol_1h", true),
        field_f64("dislocation_over_vol_6h", true),
        field_f64("gas_over_quote_abs", true),
        field_f64("quote_abs_over_log_liquidity", true),
        field_f64("age_times_dislocation", true),
        field_f64("dislocation_over_log_quote_abs", true),
        field_f64("liquidity_pressure", true),
        field_f64("gas_pressure", true),
        field_f64("crowding", true),
        field_f64("pool_quote_hhi", true),
        field_f64("trailing_realized_vol_1h", true),
        field_f64("trailing_realized_vol_6h", true),
        field_f64("same_block_event_count", true),
    ]))
}

fn write_single_part(
    data_root: &Path,
    dataset: &str,
    schema: SchemaRef,
    batch: RecordBatch,
    run_tag: &str,
) -> Result<PathBuf> {
    let path = derived_single_part_path(data_root, dataset, run_tag);
    write_parquet_part(&path, schema, batch)?;
    Ok(path)
}

fn derived_single_part_path(data_root: &Path, dataset: &str, run_tag: &str) -> PathBuf {
    let dt = run_tag.get(..10).unwrap_or("factor").replace('_', "-");
    let stem = format!("mon_usdc_{}_{}", dataset, run_tag);
    custom_part_path(data_root, DERIVED_DIR, dataset, &dt, &stem)
}

fn field_utf8(name: &str, nullable: bool) -> Field {
    Field::new(name, DataType::Utf8, nullable)
}

fn field_u64(name: &str, nullable: bool) -> Field {
    Field::new(name, DataType::UInt64, nullable)
}

fn field_f64(name: &str, nullable: bool) -> Field {
    Field::new(name, DataType::Float64, nullable)
}

fn strings<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = String>,
{
    string_array(&values.into_iter().collect::<Vec<_>>())
}

fn u64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = u64>,
{
    u64_array(&values.into_iter().collect::<Vec<_>>())
}

fn f64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = f64>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    Arc::new(Float64Array::from(values)) as ArrayRef
}

fn bools<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = bool>,
{
    bool_array(&values.into_iter().collect::<Vec<_>>())
}

fn opt_u64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = Option<u64>>,
{
    opt_u64_array(&values.into_iter().collect::<Vec<_>>())
}

fn opt_f64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = Option<f64>>,
{
    opt_f64_array(&values.into_iter().collect::<Vec<_>>())
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

fn write_factor_search_report(
    summary: &EventFactorSearchSummary,
    expression_summary: &[FactorExpressionSummaryRow],
    tradability_diagnostics: &[FactorExpressionSummaryRow],
) -> Result<()> {
    let path = Path::new(&summary.outputs.report);
    ensure_parent_dir(path)?;
    let factor_map_sections = format_factor_map_sections(expression_summary);
    let diagnostic_top = tradability_diagnostics
        .iter()
        .take(12)
        .map(|row| {
            format!(
                "| {} | {} | {} | {} | {} | {} | {} |",
                row.validation_rank,
                row.factor,
                row.factor_family,
                row.target,
                row.validation_n,
                fmt_opt(row.validation_spearman),
                fmt_opt(row.validation_top_minus_bottom)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let mechanical = summary
        .mechanical_net_label_factors
        .iter()
        .map(|factor| format!("`{factor}`"))
        .collect::<Vec<_>>()
        .join(", ");
    let gross_target_kinds = summary.gross_factor_map_target_kinds.join(", ");
    let cache_reuse = format!(
        "physical={}, cost={}, candidates={}",
        summary.cache_reuse.physical_features,
        summary.cache_reuse.cost_labels,
        summary.cache_reuse.factor_candidates
    );
    let stage_timing_rows = summary
        .stage_timings
        .iter()
        .map(|row| {
            format!(
                "| {} | {} | {} |",
                row.stage, row.elapsed_ms, row.reused_cache
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let body = format!(
        "# MON/USDC V1 Factor Map\n\nStatus: `{}` from source run `{}`.\n\nThis report is exploratory only. It does not use RPC, does not modify raw data, and does not claim true pool fee, true slippage, or executable capacity. Net labels use `{}` one-way fee bps and a stress grid of `0/25/100` bps per side.\n\n## Coverage\n\n- execution panel rows: `{}`\n- research sample rows: `{}` (`A_observed + B_reconstructed`)\n- coverage-only rows: `{}` (`C_price_only`)\n- physical feature rows: `{}`\n- cost label rows: `{}`\n- factor candidate rows: `{}`\n- gross factor-map rows: `{}`\n- tradability diagnostic rows: `{}`\n- eval workers: `{}` (requested `{}`)\n- cache reuse: `{}`\n\n## Validation\n\nDates are split chronologically into discovery, validation, and forward windows. Discovery-only quantiles define factor buckets, volatility regimes, and quote-notional buckets; validation is the ranking split and forward is confirmation only.\n\n## Factor Map\n\nThe main table is a gross-return factor map over `{}` targets. Every candidate factor, including gas, quote size, liquidity pressure, and crowding, can be studied here against future gross returns. `side_gross_return_*` asks whether following the event side continues; `market_gross_return_*` asks whether price itself rises or falls after the event.\n\n{}\n## Tradability Diagnostics\n\nThe diagnostic table keeps the net-return view for cost, notional, and liquidity-pressure mechanics: {}. These rows explain execution feasibility and label sensitivity. `gas_over_quote_abs` is not being discarded: it remains in the gross factor map, but it cannot be mixed with gas-deducted net labels as an alpha ranking because that relationship is partly mechanical.\n\n| Rank | Factor | Family | Target | Validation N | Validation Spearman | Validation Top-Bottom |\n| ---: | --- | --- | --- | ---: | ---: | ---: |\n{}\n\n## Stage Timings\n\n| Stage | Elapsed ms | Reused cache |\n| --- | ---: | --- |\n{}\n\n## Outputs\n\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n",
        summary.run_tag,
        summary.source_run_tag,
        summary.cost_assumption.assumed_fee_bps_one_way,
        summary.coverage.execution_rows,
        summary.coverage.research_sample_rows,
        summary.coverage.coverage_only_rows,
        summary.output_rows.physical_features,
        summary.output_rows.cost_labels,
        summary.output_rows.factor_candidates,
        summary.output_rows.expression_summary,
        summary.output_rows.tradability_diagnostics,
        summary.eval_workers,
        summary.requested_eval_workers,
        cache_reuse,
        gross_target_kinds,
        factor_map_sections,
        mechanical,
        diagnostic_top,
        stage_timing_rows,
        summary.outputs.expression_summary_csv,
        summary.outputs.tradability_diagnostics_csv,
        summary.outputs.factor_role_summary_csv,
        summary.outputs.stability_csv,
        summary.outputs.bucket_profiles_csv,
        summary.outputs.split_summary_csv,
        summary.outputs.completion_json,
    );
    std::fs::write(path, body).with_context(|| format!("failed to write {}", path.display()))
}

fn format_factor_map_sections(rows: &[FactorExpressionSummaryRow]) -> String {
    let mut by_family = BTreeMap::<String, Vec<&FactorExpressionSummaryRow>>::new();
    for row in rows {
        by_family
            .entry(row.factor_family.clone())
            .or_default()
            .push(row);
    }
    if by_family.is_empty() {
        return "No gross factor-map rows passed the minimum sample filters.\n\n".to_string();
    }
    let mut sections = String::new();
    for (family, mut family_rows) in by_family {
        family_rows.sort_by(|a, b| {
            desc_option_abs_f64(a.validation_spearman, b.validation_spearman)
                .then_with(|| {
                    desc_option_abs_f64(
                        a.validation_top_minus_bottom,
                        b.validation_top_minus_bottom,
                    )
                })
                .then_with(|| a.factor.cmp(&b.factor))
                .then_with(|| a.target.cmp(&b.target))
        });
        sections.push_str(&format!("### {family}\n\n"));
        sections.push_str("| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |\n");
        sections.push_str("| ---: | --- | --- | --- | --- | ---: | ---: | ---: |\n");
        for row in family_rows.into_iter().take(6) {
            sections.push_str(&format!(
                "| {} | {} | {} | {} | {} | {} | {} | {} |\n",
                row.validation_rank,
                row.factor,
                row.factor_role,
                row.target_kind,
                row.target,
                row.validation_n,
                fmt_opt(row.validation_spearman),
                fmt_opt(row.validation_top_minus_bottom)
            ));
        }
        sections.push('\n');
    }
    sections
}

fn fmt_opt(value: Option<f64>) -> String {
    value
        .map(|value| format!("{value:.6}"))
        .unwrap_or_else(|| "".to_string())
}

fn assert_no_bad_float_text(path: &Path) -> Result<()> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    for record in reader.records() {
        let record = record.with_context(|| format!("failed reading {}", path.display()))?;
        for field in &record {
            let lower = field.to_ascii_lowercase();
            if matches!(
                lower.as_str(),
                "inf" | "-inf" | "infinity" | "-infinity" | "nan"
            ) {
                bail!("{} contains a non-finite value", path.display());
            }
        }
    }
    Ok(())
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn current_executable_path() -> String {
    std::env::current_exe()
        .map(|path| path_string(&path))
        .unwrap_or_default()
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

fn f64_option(values: &Float64Array, index: usize) -> Option<f64> {
    if values.is_null(index) {
        None
    } else {
        finite(values.value(index))
    }
}

fn f64_value(values: &Float64Array, index: usize) -> f64 {
    if values.is_null(index) {
        0.0
    } else {
        values.value(index)
    }
}

fn bool_value(values: &BooleanArray, index: usize) -> bool {
    !values.is_null(index) && values.value(index)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_execution(direction: &str, quality_tier: &str, family: &str) -> ExecutionEventRow {
        ExecutionEventRow {
            block_number: 100,
            timestamp: 1_700_000_000,
            event_time_utc: utc_string(1_700_000_000).unwrap(),
            date_utc: "2023-11-14".to_string(),
            hour_utc: format_hour(1_700_000_000).unwrap(),
            transaction_hash: "0x1".to_string(),
            transaction_index: 0,
            log_index: 0,
            pool_address: "0xpool".to_string(),
            dex_id: "dex".to_string(),
            family: family.to_string(),
            direction: direction.to_string(),
            base_abs: Some(10.0),
            quote_abs: Some(100.0),
            price_quote_per_base: Some(10.0),
            receipt_gas_used: Some(100_000),
            effective_gas_price: Some(1_000_000_000),
            base_fee_per_gas: Some(900_000_000),
            same_block_event_count: 2,
            fwd_return_5m: Some(0.10),
            fwd_return_15m: Some(0.10),
            fwd_return_1h: Some(0.10),
            fwd_return_3h: Some(0.10),
            fwd_return_6h: Some(0.10),
            pool_dislocation_bps: Some(50.0),
            tx_path_source: "reconstructed_from_swap_logs".to_string(),
            tx_path_confidence: "medium".to_string(),
            pool_pre_state_age_blocks: Some(5),
            trace_path_class: "single_pool_proxy".to_string(),
            trace_source: "proxy_from_tx_path".to_string(),
            trace_confidence: "low".to_string(),
            quality_tier: quality_tier.to_string(),
            usable_for_execution_research: quality_tier != "C_price_only",
        }
    }

    #[test]
    fn side_gross_return_uses_trade_side() {
        assert_eq!(side_gross_return("buy_base", Some(0.10)), Some(0.10));
        assert_eq!(side_gross_return("sell_base", Some(0.10)), Some(-0.10));
        assert_eq!(side_gross_return("unknown", Some(0.10)), None);
    }

    #[test]
    fn market_gross_return_does_not_flip_trade_side() {
        assert_eq!(market_gross_return(Some(0.10)), Some(0.10));
        assert_eq!(market_gross_return(Some(-0.03)), Some(-0.03));
        assert_eq!(market_gross_return(Some(f64::NAN)), None);
    }

    #[test]
    fn cost_labels_keep_market_return_unflipped_and_side_return_flipped() {
        let event = test_execution("sell_base", "B_reconstructed", "v3");
        let physical = test_physical();
        let rows = build_cost_labels(&[event], &[physical], "run", "source", 30.0);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].market_gross_return_5m, Some(0.10));
        assert_eq!(rows[0].side_gross_return_5m, Some(-0.10));
    }

    #[test]
    fn net_label_deducts_fee_gas_and_slippage() {
        let value = net_label(Some(0.10), 30.0, Some(0.001), 25.0).unwrap();
        let expected = 0.10 - 2.0 * 30.0 / 10_000.0 - 0.001 - 2.0 * 25.0 / 10_000.0;
        assert!((value - expected).abs() < 1e-12);
    }

    #[test]
    fn finite_guards_prevent_inf_and_nan_candidates() {
        assert_eq!(safe_div(1.0, 0.0), None);
        assert_eq!(safe_div(f64::NAN, 1.0), None);
        assert_eq!(log1p_positive(0.0), None);
        assert_eq!(sqrt_positive(-1.0), None);
        let mut row = test_physical();
        row.quote_abs = Some(0.0);
        row.liquidity_pressure = Some(0.0);
        row.trailing_realized_vol_1h = Some(0.0);
        let candidates = build_factor_candidates(
            &[row],
            &BTreeMap::from([("2023-11-14".to_string(), "discovery".to_string())]),
            &[],
            &[],
            "run",
            "source",
        );
        assert!(candidates[0].flow_over_liquidity.is_none());
        assert!(candidates[0].dislocation_over_vol_1h.is_none());
    }

    #[test]
    fn lb_without_reserve_or_liquidity_keeps_liquidity_pressure_null() {
        let event = test_execution("buy_base", "B_reconstructed", "lb_v22");
        let state = PoolStateProxyRow {
            key: EventKey {
                block_number: event.block_number,
                transaction_hash: event.transaction_hash.clone(),
                log_index: event.log_index,
                pool_address: event.pool_address.clone(),
            },
            event_state_source: "reconstructed_from_swap_logs".to_string(),
            event_state_confidence: "medium".to_string(),
            pre_state_age_blocks: None,
            liquidity_pressure: None,
        };
        let rows = build_physical_features(&[event], &[], &[state], "run", "source").unwrap();
        assert_eq!(rows[0].liquidity_pressure, None);
        assert_eq!(rows[0].liquidity_pressure_source, "unavailable");
    }

    #[test]
    fn run_tag_path_filter_excludes_old_parts() {
        let files = vec![
            PathBuf::from("x/mon_usdc_event_execution_features_20260511_reconstruct_v1.parquet"),
            PathBuf::from("x/mon_usdc_event_execution_features_20260510_87d.parquet"),
        ];
        let filtered = filter_source_run_tag_paths_from_list(&files, "20260511_reconstruct_v1");
        assert_eq!(filtered.len(), 1);
        assert!(
            filtered[0]
                .to_string_lossy()
                .contains("20260511_reconstruct_v1")
        );
    }

    #[test]
    fn chronological_split_is_ordered_and_non_random() {
        let dates = (1..=10)
            .map(|day| format!("2026-05-{day:02}"))
            .collect::<Vec<_>>();
        let splits = chronological_split_map(dates);
        assert_eq!(
            splits.get("2026-05-01").map(String::as_str),
            Some("discovery")
        );
        assert_eq!(
            splits.get("2026-05-06").map(String::as_str),
            Some("discovery")
        );
        assert_eq!(
            splits.get("2026-05-07").map(String::as_str),
            Some("validation")
        );
        assert_eq!(
            splits.get("2026-05-08").map(String::as_str),
            Some("validation")
        );
        assert_eq!(
            splits.get("2026-05-09").map(String::as_str),
            Some("forward")
        );
        assert_eq!(
            splits.get("2026-05-10").map(String::as_str),
            Some("forward")
        );
    }

    #[test]
    fn thresholds_use_discovery_only() {
        let discovery = (0..100).map(|value| value as f64).collect::<Vec<_>>();
        let thresholds = quantile_thresholds(discovery, 5);
        assert!(thresholds.iter().all(|value| *value < 100.0));
        assert_eq!(bucket_for_value(1_000.0, &thresholds), Some(4));
    }

    #[test]
    fn target_specs_include_market_side_and_net_diagnostic_families() {
        let targets = target_specs();
        let gross = targets
            .iter()
            .filter(|target| target.evaluation_family == EVALUATION_FAMILY_GROSS_FACTOR_MAP)
            .collect::<Vec<_>>();
        let diagnostics = targets
            .iter()
            .filter(|target| target.evaluation_family == EVALUATION_FAMILY_TRADABILITY_DIAGNOSTIC)
            .collect::<Vec<_>>();
        assert_eq!(gross.len(), HORIZONS.len() * 2);
        assert_eq!(diagnostics.len(), HORIZONS.len());
        assert!(gross.iter().any(|target| {
            target.kind == TARGET_KIND_MARKET_GROSS
                && target.name.starts_with("market_gross_return_")
        }));
        assert!(gross.iter().any(|target| {
            target.kind == TARGET_KIND_SIDE_GROSS && target.name.starts_with("side_gross_return_")
        }));
        assert!(diagnostics.iter().all(|target| {
            target.kind == TARGET_KIND_NET_DIAGNOSTIC
                && target.name.starts_with("net_return_")
                && target.name.ends_with("_slip25bps")
        }));
    }

    #[test]
    fn gross_factor_map_keeps_mechanical_factors_but_net_labels_are_diagnostics_only() {
        let (candidates, costs) = synthetic_eval_rows();
        let (gross_map, diagnostics, stability, bucket_profiles) =
            evaluate_factor_candidates(&candidates, &costs, &target_specs(), 2);

        assert!(!gross_map.is_empty());
        assert!(!diagnostics.is_empty());
        assert!(gross_map.iter().all(|row| {
            row.evaluation_family == EVALUATION_FAMILY_GROSS_FACTOR_MAP
                && (row.target_kind == TARGET_KIND_MARKET_GROSS
                    || row.target_kind == TARGET_KIND_SIDE_GROSS)
        }));
        assert!(
            gross_map
                .iter()
                .any(|row| row.factor == "gas_over_quote_abs")
        );
        assert!(diagnostics.iter().all(|row| {
            row.evaluation_family == EVALUATION_FAMILY_TRADABILITY_DIAGNOSTIC
                && row.target_kind == TARGET_KIND_NET_DIAGNOSTIC
                && row.target.starts_with("net_return_")
        }));
        assert!(
            diagnostics
                .iter()
                .any(|row| row.factor == "gas_over_quote_abs")
        );
        assert!(
            diagnostics
                .iter()
                .all(|row| is_mechanical_net_label_factor(&row.factor))
        );
        assert!(stability.iter().any(|row| {
            row.evaluation_family == EVALUATION_FAMILY_GROSS_FACTOR_MAP
                && row.target_kind == TARGET_KIND_MARKET_GROSS
                && !row.factor_family.is_empty()
        }));
        assert!(bucket_profiles.iter().any(|row| {
            row.evaluation_family == EVALUATION_FAMILY_TRADABILITY_DIAGNOSTIC
                && row.target_kind == TARGET_KIND_NET_DIAGNOSTIC
                && !row.factor_family.is_empty()
        }));
    }

    #[test]
    fn optimized_evaluator_matches_slow_reference_on_synthetic_rows() {
        let (candidates, costs) = synthetic_eval_rows();
        let targets = target_specs();
        let fast = evaluate_factor_candidates(&candidates, &costs, &targets, 2);
        let slow = evaluate_factor_candidates_slow(&candidates, &costs, &targets);
        assert_eq!(
            serde_json::to_value(&fast.0).unwrap(),
            serde_json::to_value(&slow.0).unwrap()
        );
        assert_eq!(
            serde_json::to_value(&fast.1).unwrap(),
            serde_json::to_value(&slow.1).unwrap()
        );
        assert_eq!(
            serde_json::to_value(&fast.2).unwrap(),
            serde_json::to_value(&slow.2).unwrap()
        );
        assert_eq!(
            serde_json::to_value(&fast.3).unwrap(),
            serde_json::to_value(&slow.3).unwrap()
        );
    }

    #[test]
    fn progress_percent_is_monotonic_and_finishes() {
        let mut progress = ProgressReporter::new(10);
        let mut seen = Vec::new();
        progress.begin_stage("a", 2_500);
        seen.push(progress.percent_x100());
        progress.set_stage_progress(5, 10);
        seen.push(progress.percent_x100());
        progress.finish_stage();
        seen.push(progress.percent_x100());
        progress.begin_stage("b", 7_500);
        seen.push(progress.percent_x100());
        progress.set_stage_progress(1, 3);
        seen.push(progress.percent_x100());
        progress.finish_all();
        seen.push(progress.percent_x100());
        assert!(seen.windows(2).all(|pair| pair[1] >= pair[0]));
        assert_eq!(seen.last().copied(), Some(10_000));
    }

    #[test]
    fn cache_path_detects_schema_match_and_cached_rows() {
        let root = std::env::temp_dir().join(format!(
            "mon_usdc_factor_cache_test_{}_{}",
            std::process::id(),
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        let _ = std::fs::remove_dir_all(&root);
        let mut physical = test_physical();
        physical.run_tag = "cache_run".to_string();
        physical.source_run_tag = "cache_source".to_string();
        let written = write_physical_features_parquet(&root, &[physical], "cache_run").unwrap();
        let cached = cached_derived_part_path(
            &root,
            PHYSICAL_FEATURES_DATASET,
            physical_features_schema(),
            "cache_run",
        )
        .unwrap()
        .unwrap();
        assert_eq!(cached, written);
        let rows = read_physical_feature_rows(&cached, "cache_run", "cache_source").unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].run_tag, "cache_run");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn role_summary_marks_mechanical_net_label_factors_as_diagnostics() {
        let rows = build_factor_role_summary();
        assert_eq!(rows.len(), FACTOR_NAMES.len());
        let gas = rows
            .iter()
            .find(|row| row.factor == "gas_over_quote_abs")
            .unwrap();
        assert_eq!(gas.factor_family, "execution_cost");
        assert_eq!(gas.factor_role, "execution_filter");
        assert!(gas.gross_factor_map_allowed);
        assert!(!gas.net_return_alpha_allowed);
        assert!(gas.tradability_diagnostic_allowed);
        assert!(gas.mechanical_net_label_factor);
        for role in [
            "directional_alpha_candidate",
            "event_continuation_candidate",
            "regime_filter",
            "execution_filter",
            "capacity_filter",
            "quality_filter",
            "unstable_or_diagnostic_only",
        ] {
            assert!(rows.iter().any(|row| row.factor_role == role));
        }
    }

    fn synthetic_eval_rows() -> (Vec<FactorCandidateRow>, Vec<CostLabelRow>) {
        let mut candidates = Vec::new();
        let mut costs = Vec::new();
        for (split_index, split) in ["discovery", "validation", "forward"].iter().enumerate() {
            for index in 0..200 {
                let global_index = split_index * 200 + index;
                candidates.push(test_candidate(global_index, split));
                costs.push(test_cost_label(global_index));
            }
        }
        (candidates, costs)
    }

    fn test_candidate(index: usize, split: &str) -> FactorCandidateRow {
        let x = (index % 200 + 1) as f64;
        let quote = 10.0 + x;
        let signed_flow = if index % 2 == 0 { quote } else { -quote };
        let liquidity = 1_000.0 + x * 10.0;
        let log_quote = quote.ln_1p();
        let log_liquidity = liquidity.ln_1p();
        let date_utc = match split {
            "discovery" => "2026-03-01",
            "validation" => "2026-04-01",
            _ => "2026-05-01",
        };
        FactorCandidateRow {
            run_tag: "run".to_string(),
            source_run_tag: "source".to_string(),
            block_number: index as u64,
            event_time_utc: utc_string(1_700_000_000 + index as i64).unwrap(),
            date_utc: date_utc.to_string(),
            split: split.to_string(),
            transaction_hash: format!("0x{index:x}"),
            log_index: index as u64,
            pool_address: "0xpool".to_string(),
            dex_id: "dex".to_string(),
            family: "v3".to_string(),
            direction: if index % 2 == 0 {
                "buy_base".to_string()
            } else {
                "sell_base".to_string()
            },
            quality_tier: "B_reconstructed".to_string(),
            volatility_regime: "mid".to_string(),
            quote_notional_bucket: "q3".to_string(),
            quote_abs: Some(quote),
            signed_quote_flow: Some(signed_flow),
            liquidity_proxy: Some(liquidity),
            log1p_quote_abs: Some(log_quote),
            sqrt_quote_abs: Some(quote.sqrt()),
            signed_quote_flow_over_log_abs: safe_div(signed_flow, log_quote),
            signed_quote_flow_times_log_abs: finite(signed_flow * log_quote),
            quote_abs_over_liquidity: safe_div(quote, liquidity),
            flow_over_liquidity: safe_div(signed_flow, liquidity),
            flow_over_sqrt_liquidity: safe_div(signed_flow, liquidity.sqrt()),
            dislocation_over_vol_1h: Some(x / 1_000.0),
            dislocation_over_vol_6h: Some(x / 1_200.0),
            gas_over_quote_abs: Some(1.0 / quote),
            quote_abs_over_log_liquidity: safe_div(quote, log_liquidity),
            age_times_dislocation: Some(x * 0.0001),
            dislocation_over_log_quote_abs: safe_div(0.01, log_quote),
            liquidity_pressure: Some(quote / liquidity),
            gas_pressure: Some(1.0 / quote),
            crowding: Some((index % 11) as f64),
            pool_quote_hhi: Some(0.1 + x / 1_000.0),
            trailing_realized_vol_1h: Some(0.01 + x / 10_000.0),
            trailing_realized_vol_6h: Some(0.02 + x / 10_000.0),
            same_block_event_count: Some((index % 7 + 1) as f64),
        }
    }

    fn test_cost_label(index: usize) -> CostLabelRow {
        let x = (index % 200 + 1) as f64;
        let gross = (x - 60.0) / 10_000.0;
        let gas = Some(x / 100_000.0);
        let net = net_label(Some(gross), 30.0, gas, 25.0);
        CostLabelRow {
            run_tag: "run".to_string(),
            source_run_tag: "source".to_string(),
            block_number: index as u64,
            event_time_utc: utc_string(1_700_000_000 + index as i64).unwrap(),
            date_utc: "2026-03-01".to_string(),
            transaction_hash: format!("0x{index:x}"),
            log_index: index as u64,
            pool_address: "0xpool".to_string(),
            direction: "buy_base".to_string(),
            quality_tier: "B_reconstructed".to_string(),
            cost_label_type: COST_LABEL_TYPE.to_string(),
            assumed_fee_bps_one_way: 30.0,
            fee_source: FEE_SOURCE.to_string(),
            roundtrip_gas_return_proxy: gas,
            roundtrip_gas_source: "test".to_string(),
            market_gross_return_5m: Some(gross),
            market_gross_return_15m: Some(gross * 1.1),
            market_gross_return_1h: Some(gross * 1.2),
            market_gross_return_3h: Some(gross * 1.3),
            market_gross_return_6h: Some(gross * 1.4),
            side_gross_return_5m: Some(gross),
            side_gross_return_15m: Some(gross * 1.1),
            side_gross_return_1h: Some(gross * 1.2),
            side_gross_return_3h: Some(gross * 1.3),
            side_gross_return_6h: Some(gross * 1.4),
            net_return_5m_slip0bps: net_label(Some(gross), 30.0, gas, 0.0),
            net_return_5m_slip25bps: net,
            net_return_5m_slip100bps: net_label(Some(gross), 30.0, gas, 100.0),
            net_return_15m_slip0bps: net_label(Some(gross * 1.1), 30.0, gas, 0.0),
            net_return_15m_slip25bps: net_label(Some(gross * 1.1), 30.0, gas, 25.0),
            net_return_15m_slip100bps: net_label(Some(gross * 1.1), 30.0, gas, 100.0),
            net_return_1h_slip0bps: net_label(Some(gross * 1.2), 30.0, gas, 0.0),
            net_return_1h_slip25bps: net_label(Some(gross * 1.2), 30.0, gas, 25.0),
            net_return_1h_slip100bps: net_label(Some(gross * 1.2), 30.0, gas, 100.0),
            net_return_3h_slip0bps: net_label(Some(gross * 1.3), 30.0, gas, 0.0),
            net_return_3h_slip25bps: net_label(Some(gross * 1.3), 30.0, gas, 25.0),
            net_return_3h_slip100bps: net_label(Some(gross * 1.3), 30.0, gas, 100.0),
            net_return_6h_slip0bps: net_label(Some(gross * 1.4), 30.0, gas, 0.0),
            net_return_6h_slip25bps: net_label(Some(gross * 1.4), 30.0, gas, 25.0),
            net_return_6h_slip100bps: net_label(Some(gross * 1.4), 30.0, gas, 100.0),
        }
    }

    fn test_physical() -> PhysicalFeatureRow {
        PhysicalFeatureRow {
            run_tag: "run".to_string(),
            source_run_tag: "source".to_string(),
            block_number: 1,
            event_time_utc: utc_string(1_700_000_000).unwrap(),
            date_utc: "2023-11-14".to_string(),
            hour_utc: format_hour(1_700_000_000).unwrap(),
            transaction_hash: "0x1".to_string(),
            transaction_index: 0,
            log_index: 0,
            pool_address: "0xpool".to_string(),
            dex_id: "dex".to_string(),
            family: "v3".to_string(),
            direction: "buy_base".to_string(),
            quality_tier: "B_reconstructed".to_string(),
            research_sample_included: true,
            base_abs: Some(1.0),
            quote_abs: Some(100.0),
            price_quote_per_base: Some(100.0),
            signed_quote_flow: Some(100.0),
            signed_quote_flow_source: "test".to_string(),
            signed_quote_flow_confidence: "high".to_string(),
            liquidity_pressure: Some(0.01),
            liquidity_pressure_source: "test".to_string(),
            liquidity_pressure_confidence: "medium".to_string(),
            gas_pressure: Some(0.001),
            roundtrip_gas_return_proxy: Some(0.002),
            gas_pressure_source: "test".to_string(),
            gas_pressure_confidence: "medium".to_string(),
            crowding: Some(1.0),
            crowding_source: "test".to_string(),
            crowding_confidence: "high".to_string(),
            dislocation_return: Some(0.001),
            dislocation_source: "test".to_string(),
            dislocation_confidence: "medium".to_string(),
            pool_pre_state_age_blocks: Some(5),
            pool_quote_hhi: Some(0.5),
            pool_quote_hhi_source: "test".to_string(),
            pool_quote_hhi_confidence: "high".to_string(),
            trailing_realized_vol_1h: Some(0.02),
            trailing_realized_vol_6h: Some(0.03),
            volatility_source: "test".to_string(),
            volatility_confidence: "medium".to_string(),
            tx_pool_count: Some(1),
            tx_swap_count: Some(1),
            tx_path_source: "test".to_string(),
            tx_path_confidence: "medium".to_string(),
            receipt_gas_used: Some(100),
            effective_gas_price: Some(100),
            base_fee_per_gas: Some(100),
            same_block_event_count: 1,
            trace_path_class: "test".to_string(),
            trace_source: "test".to_string(),
            trace_confidence: "low".to_string(),
        }
    }
}

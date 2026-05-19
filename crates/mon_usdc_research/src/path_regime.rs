use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fs::{self, File};
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{
    Array, ArrayRef, BooleanArray, BooleanBuilder, Float64Array, Float64Builder, StringArray,
    StringBuilder, UInt64Array, UInt64Builder,
};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::DateTime;
use finance_chain_core::storage::{
    DERIVED_DIR, custom_part_path, ensure_parent_dir, parquet_files_under, write_schema_metadata,
};
use parquet::arrow::ArrowWriter;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::file::properties::WriterProperties;
use serde::Serialize;

use crate::{DEFAULT_DATA_ROOT, DEFAULT_PROGRESS_INTERVAL};

pub const DEFAULT_PATH_REGIME_SOURCE_RUN_TAG: &str = "20260511_reconstruct_v1";
pub const DEFAULT_PATH_REGIME_FEATURE_RUN_TAG: &str = "20260511_factor_map_v1";
pub const DEFAULT_PATH_REGIME_RUN_TAG: &str = "20260511_path_regime_v1";

const EXECUTION_FEATURES_DATASET: &str = "mon_usdc_event_execution_features";
const PHYSICAL_FEATURES_DATASET: &str = "mon_usdc_event_physical_features";
const MINUTE_PRICE_REFERENCE_DATASET: &str = "mon_usdc_minute_price_reference";
const PATH_REGIME_LABELS_DATASET: &str = "mon_usdc_event_path_regime_labels";

const DEFAULT_FEE_BPS_ONE_WAY: f64 = 30.0;
const DEFAULT_SLIPPAGE_BPS_ONE_WAY: f64 = 25.0;
const DEFAULT_RISK_BUFFER_BPS: f64 = 25.0;
const DEFAULT_BASELINE_SIGMA_MULTIPLIER: f64 = 0.5;
const NOTIONAL_BUCKETS: usize = 5;
const REGIME_BUCKETS: usize = 3;
const OUTPUT_CHUNK_EVENTS: usize = 25_000;

const HORIZONS: [Horizon; 5] = [
    Horizon {
        label: "5m",
        minutes: 5,
    },
    Horizon {
        label: "15m",
        minutes: 15,
    },
    Horizon {
        label: "1h",
        minutes: 60,
    },
    Horizon {
        label: "3h",
        minutes: 180,
    },
    Horizon {
        label: "6h",
        minutes: 360,
    },
];

const SENSITIVITY_PROFILES: [BarrierProfile; 3] = [
    BarrierProfile {
        name: "cost_only",
        sigma_multiplier: 0.0,
    },
    BarrierProfile {
        name: "vol_half",
        sigma_multiplier: 0.5,
    },
    BarrierProfile {
        name: "vol_one",
        sigma_multiplier: 1.0,
    },
];

#[derive(Debug, Clone)]
pub struct PathRegimeConfig {
    pub data_root: PathBuf,
    pub source_run_tag: String,
    pub feature_run_tag: String,
    pub run_tag: String,
    pub date_dir: PathBuf,
    pub docs_dir: PathBuf,
    pub fee_bps_one_way: f64,
    pub slippage_bps_one_way: f64,
    pub risk_buffer_bps: f64,
    pub baseline_sigma_multiplier: f64,
    pub progress_interval: usize,
}

impl Default for PathRegimeConfig {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_DATA_ROOT),
            source_run_tag: DEFAULT_PATH_REGIME_SOURCE_RUN_TAG.to_string(),
            feature_run_tag: DEFAULT_PATH_REGIME_FEATURE_RUN_TAG.to_string(),
            run_tag: DEFAULT_PATH_REGIME_RUN_TAG.to_string(),
            date_dir: PathBuf::from("date"),
            docs_dir: PathBuf::from("docs"),
            fee_bps_one_way: DEFAULT_FEE_BPS_ONE_WAY,
            slippage_bps_one_way: DEFAULT_SLIPPAGE_BPS_ONE_WAY,
            risk_buffer_bps: DEFAULT_RISK_BUFFER_BPS,
            baseline_sigma_multiplier: DEFAULT_BASELINE_SIGMA_MULTIPLIER,
            progress_interval: DEFAULT_PROGRESS_INTERVAL,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct PathRegimeSummary {
    pub data_root: String,
    pub run_tag: String,
    pub source_run_tag: String,
    pub feature_run_tag: String,
    pub executable_path: String,
    pub exploratory_only: bool,
    pub inputs: PathRegimeInputs,
    pub cost_assumption: CostAssumption,
    pub coverage: PathRegimeCoverage,
    pub outputs: PathRegimeOutputs,
}

#[derive(Debug, Clone, Serialize)]
pub struct PathRegimeInputs {
    pub execution_features: String,
    pub physical_features: String,
    pub minute_price_reference: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CostAssumption {
    pub fee_bps_one_way: f64,
    pub slippage_bps_one_way: f64,
    pub risk_buffer_bps: f64,
    pub baseline_sigma_multiplier: f64,
    pub formula: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PathRegimeCoverage {
    pub execution_rows: u64,
    pub physical_rows: u64,
    pub joined_research_events: u64,
    pub missing_physical_rows: u64,
    pub minute_price_rows: u64,
    pub label_rows_written: u64,
    pub summary_rows: u64,
    pub sensitivity_rows: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PathRegimeOutputs {
    pub label_parts: Vec<String>,
    pub summary_csv: String,
    pub sensitivity_csv: String,
    pub completion_json: String,
    pub report: String,
}

#[derive(Clone, Copy)]
struct Horizon {
    label: &'static str,
    minutes: u64,
}

#[derive(Clone, Copy)]
struct BarrierProfile {
    name: &'static str,
    sigma_multiplier: f64,
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

#[derive(Debug, Clone)]
struct ExecutionRow {
    key: EventKey,
    timestamp: i64,
    event_time_utc: String,
    transaction_index: u64,
    direction: String,
    quality_tier: String,
    usable_for_execution_research: bool,
}

#[derive(Debug, Clone)]
struct PhysicalRow {
    key: EventKey,
    event_time_utc: String,
    date_utc: String,
    hour_utc: String,
    transaction_index: u64,
    dex_id: String,
    family: String,
    direction: String,
    quality_tier: String,
    research_sample_included: bool,
    quote_abs: Option<f64>,
    roundtrip_gas_return_proxy: Option<f64>,
    dislocation_return: Option<f64>,
    pool_quote_hhi: Option<f64>,
    trailing_realized_vol_1h: Option<f64>,
    trailing_realized_vol_6h: Option<f64>,
    same_block_event_count: u64,
}

#[derive(Debug, Clone)]
struct JoinedEvent {
    key: EventKey,
    timestamp: i64,
    event_time_utc: String,
    date_utc: String,
    hour_utc: String,
    transaction_index: u64,
    dex_id: String,
    family: String,
    direction: String,
    quality_tier: String,
    split: String,
    quote_abs: Option<f64>,
    roundtrip_gas_return_proxy: Option<f64>,
    dislocation_return: Option<f64>,
    pool_quote_hhi: Option<f64>,
    trailing_realized_vol_1h: Option<f64>,
    trailing_realized_vol_6h: Option<f64>,
    same_block_event_count: u64,
    volatility_regime: String,
    quote_notional_bucket: String,
    pool_concentration_bucket: String,
    gas_bucket: String,
    same_block_density_bucket: String,
    pool_dislocation_bucket: String,
}

#[derive(Debug, Clone)]
struct MinutePricePoint {
    timestamp: i64,
    price: Option<f64>,
}

#[derive(Debug, Clone)]
struct MinutePriceSeries {
    start_minute: i64,
    rows: Vec<Option<f64>>,
}

impl MinutePriceSeries {
    fn price_at(&self, minute_ts: i64) -> Option<f64> {
        if minute_ts < self.start_minute {
            return None;
        }
        let index = ((minute_ts - self.start_minute) / 60) as usize;
        self.rows
            .get(index)
            .copied()
            .flatten()
            .filter(|value| *value > 0.0 && value.is_finite())
    }
}

#[derive(Debug, Clone)]
struct PathPoint {
    seconds: u64,
    continuation_return: f64,
}

#[derive(Debug, Clone)]
struct RawPathMetrics {
    mfe_continuation: Option<f64>,
    mae_continuation: Option<f64>,
    mfe_reversal: Option<f64>,
    mae_reversal: Option<f64>,
    best_mfe: Option<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HitKind {
    Profit,
    Stop,
    None,
}

impl HitKind {
    fn as_str(self) -> &'static str {
        match self {
            Self::Profit => "profit",
            Self::Stop => "stop",
            Self::None => "none",
        }
    }
}

#[derive(Debug, Clone)]
struct BarrierHit {
    kind: HitKind,
    seconds: Option<u64>,
}

#[derive(Debug, Clone)]
struct LabelOutcome {
    cost_return: Option<f64>,
    sigma_return: Option<f64>,
    profit_barrier_return: Option<f64>,
    stop_barrier_return: Option<f64>,
    mfe_continuation: Option<f64>,
    mae_continuation: Option<f64>,
    mfe_reversal: Option<f64>,
    mae_reversal: Option<f64>,
    best_mfe: Option<f64>,
    continuation_hit_kind: String,
    continuation_hit_seconds: Option<u64>,
    reversal_hit_kind: String,
    reversal_hit_seconds: Option<u64>,
    dead_zone: bool,
    tradable_path: bool,
    risk_first: bool,
    directional_path: String,
    path_label: String,
    diagnostic_status: String,
}

#[derive(Debug, Clone)]
struct PathRegimeLabelRow {
    run_tag: String,
    source_run_tag: String,
    feature_run_tag: String,
    block_number: u64,
    event_time_utc: String,
    date_utc: String,
    hour_utc: String,
    split: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    quality_tier: String,
    horizon: String,
    horizon_minutes: u64,
    quote_abs: Option<f64>,
    same_block_event_count: u64,
    volatility_regime: String,
    quote_notional_bucket: String,
    pool_concentration_bucket: String,
    gas_bucket: String,
    same_block_density_bucket: String,
    pool_dislocation_bucket: String,
    cost_return: Option<f64>,
    cost_bps: Option<f64>,
    sigma_return: Option<f64>,
    sigma_bps: Option<f64>,
    profit_barrier_return: Option<f64>,
    stop_barrier_return: Option<f64>,
    mfe_continuation: Option<f64>,
    mae_continuation: Option<f64>,
    mfe_reversal: Option<f64>,
    mae_reversal: Option<f64>,
    best_mfe: Option<f64>,
    continuation_hit_kind: String,
    continuation_hit_seconds: Option<u64>,
    reversal_hit_kind: String,
    reversal_hit_seconds: Option<u64>,
    dead_zone: bool,
    tradable_path: bool,
    risk_first: bool,
    directional_path: String,
    path_label: String,
    diagnostic_status: String,
}

#[derive(Debug, Clone, Serialize)]
struct PathRegimeSummaryRow {
    run_tag: String,
    source_run_tag: String,
    feature_run_tag: String,
    horizon: String,
    group: String,
    group_value: String,
    rows: u64,
    dead_zone_rows: u64,
    tradable_path_rows: u64,
    continuation_rows: u64,
    reversal_rows: u64,
    risk_first_rows: u64,
    missing_price_rows: u64,
    missing_cost_rows: u64,
    missing_volatility_rows: u64,
    dead_zone_rate: Option<f64>,
    tradable_path_rate: Option<f64>,
    continuation_rate: Option<f64>,
    reversal_rate: Option<f64>,
    risk_first_rate: Option<f64>,
    median_mfe_bps: Option<f64>,
    p90_mfe_bps: Option<f64>,
    median_cost_bps: Option<f64>,
    median_sigma_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct PathRegimeSensitivityRow {
    run_tag: String,
    source_run_tag: String,
    feature_run_tag: String,
    profile: String,
    sigma_multiplier: f64,
    horizon: String,
    split: String,
    rows: u64,
    dead_zone_rows: u64,
    tradable_path_rows: u64,
    continuation_rows: u64,
    reversal_rows: u64,
    risk_first_rows: u64,
    missing_price_rows: u64,
    missing_cost_rows: u64,
    missing_volatility_rows: u64,
    dead_zone_rate: Option<f64>,
    tradable_path_rate: Option<f64>,
    continuation_rate: Option<f64>,
    reversal_rate: Option<f64>,
    risk_first_rate: Option<f64>,
    median_mfe_bps: Option<f64>,
    p90_mfe_bps: Option<f64>,
    median_cost_bps: Option<f64>,
    median_sigma_bps: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct SummaryKey {
    horizon: String,
    group: String,
    group_value: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct SensitivityKey {
    profile: String,
    horizon: String,
    split: String,
}

#[derive(Debug, Default, Clone)]
struct GroupStats {
    rows: u64,
    dead_zone_rows: u64,
    tradable_path_rows: u64,
    continuation_rows: u64,
    reversal_rows: u64,
    risk_first_rows: u64,
    missing_price_rows: u64,
    missing_cost_rows: u64,
    missing_volatility_rows: u64,
    best_mfe_bps: Vec<f64>,
    cost_bps: Vec<f64>,
    sigma_bps: Vec<f64>,
}

impl GroupStats {
    fn update(&mut self, outcome: &LabelOutcome) {
        self.rows += 1;
        if outcome.dead_zone {
            self.dead_zone_rows += 1;
        }
        if outcome.tradable_path {
            self.tradable_path_rows += 1;
        }
        match outcome.directional_path.as_str() {
            "continuation" => self.continuation_rows += 1,
            "reversal" => self.reversal_rows += 1,
            "both_or_ambiguous" => {
                self.continuation_rows += 1;
                self.reversal_rows += 1;
            }
            _ => {}
        }
        if outcome.path_label == "risk_first" {
            self.risk_first_rows += 1;
        }
        match outcome.diagnostic_status.as_str() {
            "missing_price" => self.missing_price_rows += 1,
            "missing_cost" => self.missing_cost_rows += 1,
            "missing_volatility" => self.missing_volatility_rows += 1,
            _ => {}
        }
        push_bps(&mut self.best_mfe_bps, outcome.best_mfe);
        push_bps(&mut self.cost_bps, outcome.cost_return);
        push_bps(&mut self.sigma_bps, outcome.sigma_return);
    }
}

pub fn run_path_regime_report(config: &PathRegimeConfig) -> Result<PathRegimeSummary> {
    validate_config(config)?;
    fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    fs::create_dir_all(config.docs_dir.join("markets/mon-usdc"))
        .with_context(|| format!("failed to create {}", config.docs_dir.display()))?;

    let outputs = build_output_paths(config);
    let execution_path = select_run_part(
        &config.data_root,
        EXECUTION_FEATURES_DATASET,
        &config.source_run_tag,
    )?;
    let physical_path = select_run_part(
        &config.data_root,
        PHYSICAL_FEATURES_DATASET,
        &config.feature_run_tag,
    )?;
    let minute_path = select_latest_part(&config.data_root, MINUTE_PRICE_REFERENCE_DATASET)?;

    eprintln!(
        "[mon_usdc_path_regime_report] read execution features: {}",
        execution_path.display()
    );
    let execution_rows = read_execution_rows(
        &execution_path,
        &config.source_run_tag,
        config.progress_interval,
    )?;
    eprintln!(
        "[mon_usdc_path_regime_report] read physical features: {}",
        physical_path.display()
    );
    let physical_rows = read_physical_rows(
        &physical_path,
        &config.feature_run_tag,
        &config.source_run_tag,
        config.progress_interval,
    )?;
    eprintln!(
        "[mon_usdc_path_regime_report] read minute price reference: {}",
        minute_path.display()
    );
    let minute_prices = read_minute_price_series(&minute_path)?;

    let (mut joined_events, missing_physical_rows) =
        join_research_events(&execution_rows, &physical_rows)?;
    if joined_events.is_empty() {
        bail!("path-regime report has no joined research events");
    }
    enrich_splits_and_buckets(&mut joined_events);

    let label_schema = label_schema();
    write_schema_metadata(
        &config.data_root,
        PATH_REGIME_LABELS_DATASET,
        label_schema.as_ref(),
        &["dt"],
    )?;
    let label_paths = label_part_paths(config);
    let mut writers = open_label_writers(&label_paths, label_schema.clone())?;
    let mut summary_stats = BTreeMap::<SummaryKey, GroupStats>::new();
    let mut sensitivity_stats = BTreeMap::<SensitivityKey, (f64, GroupStats)>::new();

    let mut label_rows_written = 0u64;
    for (chunk_index, chunk) in joined_events.chunks(OUTPUT_CHUNK_EVENTS).enumerate() {
        if config.progress_interval > 0
            && (chunk_index == 0
                || ((chunk_index + 1) * OUTPUT_CHUNK_EVENTS) % config.progress_interval == 0)
        {
            eprintln!(
                "[mon_usdc_path_regime_report] labeling events {}..{} of {}",
                chunk_index * OUTPUT_CHUNK_EVENTS,
                ((chunk_index + 1) * OUTPUT_CHUNK_EVENTS).min(joined_events.len()),
                joined_events.len()
            );
        }
        let mut rows_by_horizon = (0..HORIZONS.len())
            .map(|_| Vec::<PathRegimeLabelRow>::with_capacity(chunk.len()))
            .collect::<Vec<_>>();
        for event in chunk {
            let path_points = build_path_points(event, &minute_prices, max_horizon_minutes());
            for (horizon_index, horizon) in HORIZONS.iter().enumerate() {
                let outcome = label_for_event(
                    event,
                    &path_points,
                    *horizon,
                    config,
                    BarrierProfile {
                        name: "baseline",
                        sigma_multiplier: config.baseline_sigma_multiplier,
                    },
                );
                update_summary_stats(&mut summary_stats, event, horizon.label, &outcome);
                update_sensitivity_stats(
                    &mut sensitivity_stats,
                    event,
                    horizon.label,
                    &outcome,
                    "vol_half",
                    config.baseline_sigma_multiplier,
                );
                for profile in SENSITIVITY_PROFILES {
                    if (profile.sigma_multiplier - config.baseline_sigma_multiplier).abs() < 1e-12 {
                        continue;
                    }
                    let profile_outcome =
                        label_for_event(event, &path_points, *horizon, config, profile);
                    update_sensitivity_stats(
                        &mut sensitivity_stats,
                        event,
                        horizon.label,
                        &profile_outcome,
                        profile.name,
                        profile.sigma_multiplier,
                    );
                }
                rows_by_horizon[horizon_index]
                    .push(PathRegimeLabelRow::new(config, event, horizon, outcome));
            }
        }
        for (writer, rows) in writers.iter_mut().zip(rows_by_horizon.iter()) {
            let batch = label_batch(label_schema.clone(), rows)?;
            writer.write(&batch)?;
            label_rows_written += rows.len() as u64;
        }
    }
    for writer in writers {
        writer.close()?;
    }

    let summary_rows = finalize_summary_rows(
        &summary_stats,
        &config.run_tag,
        &config.source_run_tag,
        &config.feature_run_tag,
    );
    let sensitivity_rows = finalize_sensitivity_rows(
        &sensitivity_stats,
        &config.run_tag,
        &config.source_run_tag,
        &config.feature_run_tag,
    );
    write_csv(Path::new(&outputs.summary_csv), &summary_rows)?;
    write_csv(Path::new(&outputs.sensitivity_csv), &sensitivity_rows)?;

    let summary = PathRegimeSummary {
        data_root: path_string(&config.data_root),
        run_tag: config.run_tag.clone(),
        source_run_tag: config.source_run_tag.clone(),
        feature_run_tag: config.feature_run_tag.clone(),
        executable_path: current_executable_path(),
        exploratory_only: true,
        inputs: PathRegimeInputs {
            execution_features: path_string(&execution_path),
            physical_features: path_string(&physical_path),
            minute_price_reference: path_string(&minute_path),
        },
        cost_assumption: CostAssumption {
            fee_bps_one_way: config.fee_bps_one_way,
            slippage_bps_one_way: config.slippage_bps_one_way,
            risk_buffer_bps: config.risk_buffer_bps,
            baseline_sigma_multiplier: config.baseline_sigma_multiplier,
            formula: "C_e = 2f + 2eta + g_e + rho_e; B+ = B- = C_e + sigma_multiplier * sigma_e"
                .to_string(),
        },
        coverage: PathRegimeCoverage {
            execution_rows: execution_rows.len() as u64,
            physical_rows: physical_rows.len() as u64,
            joined_research_events: joined_events.len() as u64,
            missing_physical_rows,
            minute_price_rows: minute_prices.rows.len() as u64,
            label_rows_written,
            summary_rows: summary_rows.len() as u64,
            sensitivity_rows: sensitivity_rows.len() as u64,
        },
        outputs,
    };
    write_json(Path::new(&summary.outputs.completion_json), &summary)?;
    write_report(&summary, &summary_rows, &sensitivity_rows)?;
    Ok(summary)
}

impl PathRegimeLabelRow {
    fn new(
        config: &PathRegimeConfig,
        event: &JoinedEvent,
        horizon: &Horizon,
        outcome: LabelOutcome,
    ) -> Self {
        Self {
            run_tag: config.run_tag.clone(),
            source_run_tag: config.source_run_tag.clone(),
            feature_run_tag: config.feature_run_tag.clone(),
            block_number: event.key.block_number,
            event_time_utc: event.event_time_utc.clone(),
            date_utc: event.date_utc.clone(),
            hour_utc: event.hour_utc.clone(),
            split: event.split.clone(),
            transaction_hash: event.key.transaction_hash.clone(),
            transaction_index: event.transaction_index,
            log_index: event.key.log_index,
            pool_address: event.key.pool_address.clone(),
            dex_id: event.dex_id.clone(),
            family: event.family.clone(),
            direction: event.direction.clone(),
            quality_tier: event.quality_tier.clone(),
            horizon: horizon.label.to_string(),
            horizon_minutes: horizon.minutes,
            quote_abs: event.quote_abs,
            same_block_event_count: event.same_block_event_count,
            volatility_regime: event.volatility_regime.clone(),
            quote_notional_bucket: event.quote_notional_bucket.clone(),
            pool_concentration_bucket: event.pool_concentration_bucket.clone(),
            gas_bucket: event.gas_bucket.clone(),
            same_block_density_bucket: event.same_block_density_bucket.clone(),
            pool_dislocation_bucket: event.pool_dislocation_bucket.clone(),
            cost_bps: outcome.cost_return.map(to_bps),
            sigma_bps: outcome.sigma_return.map(to_bps),
            cost_return: outcome.cost_return,
            sigma_return: outcome.sigma_return,
            profit_barrier_return: outcome.profit_barrier_return,
            stop_barrier_return: outcome.stop_barrier_return,
            mfe_continuation: outcome.mfe_continuation,
            mae_continuation: outcome.mae_continuation,
            mfe_reversal: outcome.mfe_reversal,
            mae_reversal: outcome.mae_reversal,
            best_mfe: outcome.best_mfe,
            continuation_hit_kind: outcome.continuation_hit_kind,
            continuation_hit_seconds: outcome.continuation_hit_seconds,
            reversal_hit_kind: outcome.reversal_hit_kind,
            reversal_hit_seconds: outcome.reversal_hit_seconds,
            dead_zone: outcome.dead_zone,
            tradable_path: outcome.tradable_path,
            risk_first: outcome.risk_first,
            directional_path: outcome.directional_path,
            path_label: outcome.path_label,
            diagnostic_status: outcome.diagnostic_status,
        }
    }
}

fn validate_config(config: &PathRegimeConfig) -> Result<()> {
    for (name, value) in [
        ("fee_bps_one_way", config.fee_bps_one_way),
        ("slippage_bps_one_way", config.slippage_bps_one_way),
        ("risk_buffer_bps", config.risk_buffer_bps),
        (
            "baseline_sigma_multiplier",
            config.baseline_sigma_multiplier,
        ),
    ] {
        if !value.is_finite() || value < 0.0 {
            bail!("{name} must be finite and non-negative");
        }
    }
    Ok(())
}

fn select_run_part(data_root: &Path, dataset: &str, run_tag: &str) -> Result<PathBuf> {
    let root = data_root.join(DERIVED_DIR).join(dataset);
    let mut matches = parquet_files_under(&root)?
        .into_iter()
        .filter(|path| {
            path.file_name()
                .and_then(|value| value.to_str())
                .map(|name| name.contains(run_tag))
                .unwrap_or(false)
        })
        .collect::<Vec<_>>();
    matches.sort();
    match matches.len() {
        0 => bail!(
            "no parquet part found for dataset {dataset} run_tag {run_tag} under {}",
            root.display()
        ),
        1 => Ok(matches.remove(0)),
        _ => bail!(
            "multiple parquet parts found for dataset {dataset} run_tag {run_tag}; expected one"
        ),
    }
}

fn select_latest_part(data_root: &Path, dataset: &str) -> Result<PathBuf> {
    let root = data_root.join(DERIVED_DIR).join(dataset);
    let files = parquet_files_under(&root)?;
    files
        .into_iter()
        .max_by_key(|path| fs::metadata(path).and_then(|meta| meta.modified()).ok())
        .ok_or_else(|| {
            anyhow!(
                "no parquet part found for dataset {dataset} under {}",
                root.display()
            )
        })
}

fn read_execution_rows(
    path: &Path,
    source_run_tag: &str,
    progress_interval: usize,
) -> Result<Vec<ExecutionRow>> {
    let mut rows = Vec::new();
    read_parquet_batches(path, |batch| {
        let run_tag = string_column(batch, "run_tag")?;
        let block_number = u64_column(batch, "block_number")?;
        let event_time_utc = string_column(batch, "event_time_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let transaction_index = u64_column(batch, "transaction_index")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let direction = string_column(batch, "direction")?;
        let quality_tier = string_column(batch, "quality_tier")?;
        let usable_for_execution_research = bool_column(batch, "usable_for_execution_research")?;
        for index in 0..batch.num_rows() {
            let row_run_tag = string_value(run_tag, index);
            if row_run_tag != source_run_tag {
                bail!(
                    "run_tag mismatch in {}: expected {source_run_tag}, found {row_run_tag}",
                    path.display()
                );
            }
            let time = string_value(event_time_utc, index);
            rows.push(ExecutionRow {
                key: EventKey {
                    block_number: u64_value(block_number, index),
                    transaction_hash: string_value(transaction_hash, index),
                    log_index: u64_value(log_index, index),
                    pool_address: string_value(pool_address, index),
                },
                timestamp: parse_event_timestamp(&time)?,
                event_time_utc: time,
                transaction_index: u64_value(transaction_index, index),
                direction: string_value(direction, index),
                quality_tier: string_value(quality_tier, index),
                usable_for_execution_research: bool_value(usable_for_execution_research, index),
            });
        }
        if progress_interval > 0 && rows.len() % progress_interval < batch.num_rows() {
            eprintln!(
                "[mon_usdc_path_regime_report] execution rows read: {}",
                rows.len()
            );
        }
        Ok(())
    })?;
    rows.sort_by_key(|row| {
        (
            row.timestamp,
            row.key.block_number,
            row.transaction_index,
            row.key.log_index,
            row.key.pool_address.clone(),
        )
    });
    Ok(rows)
}

fn read_physical_rows(
    path: &Path,
    feature_run_tag: &str,
    source_run_tag_expected: &str,
    progress_interval: usize,
) -> Result<Vec<PhysicalRow>> {
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
        let quote_abs = f64_column(batch, "quote_abs")?;
        let roundtrip_gas_return_proxy = f64_column(batch, "roundtrip_gas_return_proxy")?;
        let dislocation_return = f64_column(batch, "dislocation_return")?;
        let pool_quote_hhi = f64_column(batch, "pool_quote_hhi")?;
        let trailing_realized_vol_1h = f64_column(batch, "trailing_realized_vol_1h")?;
        let trailing_realized_vol_6h = f64_column(batch, "trailing_realized_vol_6h")?;
        let same_block_event_count = u64_column(batch, "same_block_event_count")?;
        for index in 0..batch.num_rows() {
            let row_run_tag = string_value(run_tag, index);
            if row_run_tag != feature_run_tag {
                bail!(
                    "run_tag mismatch in {}: expected {feature_run_tag}, found {row_run_tag}",
                    path.display()
                );
            }
            let row_source_run_tag = string_value(source_run_tag, index);
            if row_source_run_tag != source_run_tag_expected {
                bail!(
                    "source_run_tag mismatch in {}: expected {source_run_tag_expected}, found {row_source_run_tag}",
                    path.display()
                );
            }
            rows.push(PhysicalRow {
                key: EventKey {
                    block_number: u64_value(block_number, index),
                    transaction_hash: string_value(transaction_hash, index),
                    log_index: u64_value(log_index, index),
                    pool_address: string_value(pool_address, index),
                },
                event_time_utc: string_value(event_time_utc, index),
                date_utc: string_value(date_utc, index),
                hour_utc: string_value(hour_utc, index),
                transaction_index: u64_value(transaction_index, index),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                direction: string_value(direction, index),
                quality_tier: string_value(quality_tier, index),
                research_sample_included: bool_value(research_sample_included, index),
                quote_abs: f64_option(quote_abs, index),
                roundtrip_gas_return_proxy: f64_option(roundtrip_gas_return_proxy, index),
                dislocation_return: f64_option(dislocation_return, index),
                pool_quote_hhi: f64_option(pool_quote_hhi, index),
                trailing_realized_vol_1h: f64_option(trailing_realized_vol_1h, index),
                trailing_realized_vol_6h: f64_option(trailing_realized_vol_6h, index),
                same_block_event_count: u64_value(same_block_event_count, index),
            });
        }
        if progress_interval > 0 && rows.len() % progress_interval < batch.num_rows() {
            eprintln!(
                "[mon_usdc_path_regime_report] physical rows read: {}",
                rows.len()
            );
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_minute_price_series(path: &Path) -> Result<MinutePriceSeries> {
    let mut points = Vec::<MinutePricePoint>::new();
    read_parquet_batches(path, |batch| {
        let minute_timestamp = u64_column(batch, "minute_timestamp")?;
        let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
        for index in 0..batch.num_rows() {
            points.push(MinutePricePoint {
                timestamp: u64_value(minute_timestamp, index) as i64,
                price: f64_option(price_quote_per_base, index),
            });
        }
        Ok(())
    })?;
    points.sort_by_key(|row| row.timestamp);
    let start_minute = points
        .first()
        .map(|row| row.timestamp)
        .ok_or_else(|| anyhow!("empty minute price reference {}", path.display()))?;
    let mut expected = start_minute;
    let mut rows = Vec::with_capacity(points.len());
    for point in points {
        if point.timestamp != expected {
            bail!(
                "minute price reference has a gap or duplicate at {} expected {}",
                point.timestamp,
                expected
            );
        }
        rows.push(point.price);
        expected += 60;
    }
    Ok(MinutePriceSeries { start_minute, rows })
}

fn join_research_events(
    execution_rows: &[ExecutionRow],
    physical_rows: &[PhysicalRow],
) -> Result<(Vec<JoinedEvent>, u64)> {
    let mut physical_by_key = HashMap::with_capacity(physical_rows.len());
    for row in physical_rows {
        if physical_by_key.insert(row.key.clone(), row).is_some() {
            bail!(
                "duplicate physical event key: block={} tx={} log={} pool={}",
                row.key.block_number,
                row.key.transaction_hash,
                row.key.log_index,
                row.key.pool_address
            );
        }
    }
    let mut seen_execution = HashSet::with_capacity(execution_rows.len());
    let mut joined = Vec::with_capacity(execution_rows.len());
    let mut missing_physical = 0u64;
    for execution in execution_rows {
        if !seen_execution.insert(execution.key.clone()) {
            bail!(
                "duplicate execution event key: block={} tx={} log={} pool={}",
                execution.key.block_number,
                execution.key.transaction_hash,
                execution.key.log_index,
                execution.key.pool_address
            );
        }
        let Some(physical) = physical_by_key.get(&execution.key) else {
            missing_physical += 1;
            continue;
        };
        if !execution.usable_for_execution_research || !physical.research_sample_included {
            continue;
        }
        joined.push(JoinedEvent {
            key: execution.key.clone(),
            timestamp: execution.timestamp,
            event_time_utc: if physical.event_time_utc.is_empty() {
                execution.event_time_utc.clone()
            } else {
                physical.event_time_utc.clone()
            },
            date_utc: physical.date_utc.clone(),
            hour_utc: physical.hour_utc.clone(),
            transaction_index: physical.transaction_index.max(execution.transaction_index),
            dex_id: physical.dex_id.clone(),
            family: physical.family.clone(),
            direction: if physical.direction.is_empty() {
                execution.direction.clone()
            } else {
                physical.direction.clone()
            },
            quality_tier: if physical.quality_tier.is_empty() {
                execution.quality_tier.clone()
            } else {
                physical.quality_tier.clone()
            },
            split: "unassigned".to_string(),
            quote_abs: physical.quote_abs,
            roundtrip_gas_return_proxy: physical.roundtrip_gas_return_proxy,
            dislocation_return: physical.dislocation_return,
            pool_quote_hhi: physical.pool_quote_hhi,
            trailing_realized_vol_1h: physical.trailing_realized_vol_1h,
            trailing_realized_vol_6h: physical.trailing_realized_vol_6h,
            same_block_event_count: physical.same_block_event_count,
            volatility_regime: String::new(),
            quote_notional_bucket: String::new(),
            pool_concentration_bucket: String::new(),
            gas_bucket: String::new(),
            same_block_density_bucket: String::new(),
            pool_dislocation_bucket: String::new(),
        });
    }
    Ok((joined, missing_physical))
}

fn enrich_splits_and_buckets(events: &mut [JoinedEvent]) {
    let split_by_date = chronological_split_map(events.iter().map(|row| row.date_utc.clone()));
    let quote_thresholds = thresholds(
        events.iter().filter_map(|row| {
            (split_by_date.get(&row.date_utc).map(String::as_str) == Some("discovery"))
                .then_some(row.quote_abs)
                .flatten()
        }),
        NOTIONAL_BUCKETS,
    );
    let vol_thresholds = thresholds(
        events.iter().filter_map(|row| {
            (split_by_date.get(&row.date_utc).map(String::as_str) == Some("discovery"))
                .then_some(row.trailing_realized_vol_1h)
                .flatten()
        }),
        REGIME_BUCKETS,
    );
    let hhi_thresholds = thresholds(
        events.iter().filter_map(|row| {
            (split_by_date.get(&row.date_utc).map(String::as_str) == Some("discovery"))
                .then_some(row.pool_quote_hhi)
                .flatten()
        }),
        REGIME_BUCKETS,
    );
    let gas_thresholds = thresholds(
        events.iter().filter_map(|row| {
            (split_by_date.get(&row.date_utc).map(String::as_str) == Some("discovery"))
                .then_some(row.roundtrip_gas_return_proxy)
                .flatten()
        }),
        REGIME_BUCKETS,
    );
    let same_block_thresholds = thresholds(
        events.iter().filter_map(|row| {
            if split_by_date.get(&row.date_utc).map(String::as_str) == Some("discovery") {
                finite(row.same_block_event_count as f64)
            } else {
                None
            }
        }),
        REGIME_BUCKETS,
    );
    let dislocation_thresholds = thresholds(
        events.iter().filter_map(|row| {
            (split_by_date.get(&row.date_utc).map(String::as_str) == Some("discovery"))
                .then_some(row.dislocation_return.map(f64::abs))
                .flatten()
        }),
        REGIME_BUCKETS,
    );
    for row in events {
        row.split = split_by_date
            .get(&row.date_utc)
            .cloned()
            .unwrap_or_else(|| "unavailable".to_string());
        row.quote_notional_bucket = quantile_bucket(row.quote_abs, &quote_thresholds, "q");
        row.volatility_regime = regime_bucket(row.trailing_realized_vol_1h, &vol_thresholds);
        row.pool_concentration_bucket = regime_bucket(row.pool_quote_hhi, &hhi_thresholds);
        row.gas_bucket = regime_bucket(row.roundtrip_gas_return_proxy, &gas_thresholds);
        row.same_block_density_bucket = regime_bucket(
            finite(row.same_block_event_count as f64),
            &same_block_thresholds,
        );
        row.pool_dislocation_bucket = regime_bucket(
            row.dislocation_return.map(f64::abs),
            &dislocation_thresholds,
        );
    }
}

fn build_path_points(
    event: &JoinedEvent,
    minute_prices: &MinutePriceSeries,
    max_horizon_minutes: u64,
) -> Option<Vec<PathPoint>> {
    let side = side_multiplier(&event.direction)?;
    let entry_minute = floor_to_minute(event.timestamp) + 60;
    let entry_price = minute_prices.price_at(entry_minute)?;
    let entry_log = entry_price.ln();
    let mut points = Vec::with_capacity(max_horizon_minutes as usize);
    for minute in 1..=max_horizon_minutes {
        let timestamp = entry_minute + minute as i64 * 60;
        if let Some(price) = minute_prices.price_at(timestamp) {
            points.push(PathPoint {
                seconds: minute * 60,
                continuation_return: side * (price.ln() - entry_log),
            });
        }
    }
    Some(points)
}

fn label_for_event(
    event: &JoinedEvent,
    path_points: &Option<Vec<PathPoint>>,
    horizon: Horizon,
    config: &PathRegimeConfig,
    profile: BarrierProfile,
) -> LabelOutcome {
    let cost_return = event
        .roundtrip_gas_return_proxy
        .and_then(finite)
        .map(|gas| {
            bps_to_return(
                2.0 * config.fee_bps_one_way
                    + 2.0 * config.slippage_bps_one_way
                    + config.risk_buffer_bps,
            ) + gas
        });
    let sigma_return = sigma_for_horizon(event, horizon).and_then(finite);
    let missing_price = path_points
        .as_ref()
        .map(|points| !has_horizon_price(points, horizon.minutes))
        .unwrap_or(true);
    let raw_metrics = path_points
        .as_ref()
        .and_then(|points| raw_path_metrics(points, horizon.minutes));

    let mut outcome = LabelOutcome {
        cost_return,
        sigma_return,
        profit_barrier_return: None,
        stop_barrier_return: None,
        mfe_continuation: raw_metrics
            .as_ref()
            .and_then(|metrics| metrics.mfe_continuation),
        mae_continuation: raw_metrics
            .as_ref()
            .and_then(|metrics| metrics.mae_continuation),
        mfe_reversal: raw_metrics
            .as_ref()
            .and_then(|metrics| metrics.mfe_reversal),
        mae_reversal: raw_metrics
            .as_ref()
            .and_then(|metrics| metrics.mae_reversal),
        best_mfe: raw_metrics.as_ref().and_then(|metrics| metrics.best_mfe),
        continuation_hit_kind: "none".to_string(),
        continuation_hit_seconds: None,
        reversal_hit_kind: "none".to_string(),
        reversal_hit_seconds: None,
        dead_zone: false,
        tradable_path: false,
        risk_first: false,
        directional_path: "none".to_string(),
        path_label: "unclassified".to_string(),
        diagnostic_status: "ok".to_string(),
    };

    if missing_price || raw_metrics.is_none() {
        outcome.path_label = "missing_price".to_string();
        outcome.diagnostic_status = "missing_price".to_string();
        return outcome;
    }
    let Some(cost) = cost_return else {
        outcome.path_label = "missing_cost".to_string();
        outcome.diagnostic_status = "missing_cost".to_string();
        return outcome;
    };
    if profile.sigma_multiplier > 0.0 && sigma_return.is_none() {
        outcome.path_label = "missing_volatility".to_string();
        outcome.diagnostic_status = "missing_volatility".to_string();
        return outcome;
    }
    let sigma_component = sigma_return.unwrap_or(0.0) * profile.sigma_multiplier;
    let profit_barrier = cost + sigma_component;
    let stop_barrier = cost + sigma_component;
    outcome.profit_barrier_return = Some(profit_barrier);
    outcome.stop_barrier_return = Some(stop_barrier);

    let points = path_points.as_ref().expect("checked above");
    let continuation_hit = first_barrier_hit(points, horizon.minutes, profit_barrier, stop_barrier);
    let reversal_hit =
        first_barrier_hit_reversed(points, horizon.minutes, profit_barrier, stop_barrier);
    outcome.continuation_hit_kind = continuation_hit.kind.as_str().to_string();
    outcome.continuation_hit_seconds = continuation_hit.seconds;
    outcome.reversal_hit_kind = reversal_hit.kind.as_str().to_string();
    outcome.reversal_hit_seconds = reversal_hit.seconds;

    let best_mfe = outcome.best_mfe.unwrap_or(f64::NEG_INFINITY);
    outcome.dead_zone = best_mfe < cost;
    let continuation_tradable = continuation_hit.kind == HitKind::Profit;
    let reversal_tradable = reversal_hit.kind == HitKind::Profit;
    outcome.tradable_path = !outcome.dead_zone && (continuation_tradable || reversal_tradable);
    outcome.risk_first = !outcome.dead_zone && !outcome.tradable_path;
    outcome.directional_path = match (continuation_tradable, reversal_tradable) {
        (true, true) => "both_or_ambiguous",
        (true, false) => "continuation",
        (false, true) => "reversal",
        (false, false) => "none",
    }
    .to_string();
    outcome.path_label = if outcome.dead_zone {
        "dead_zone"
    } else if outcome.tradable_path {
        "tradable_path"
    } else {
        "risk_first"
    }
    .to_string();
    outcome.diagnostic_status = if outcome.dead_zone {
        "dead_zone"
    } else if outcome.tradable_path {
        "profit_first"
    } else if continuation_hit.kind == HitKind::Stop {
        "event_side_risk_first"
    } else {
        "cost_edge_no_barrier"
    }
    .to_string();
    outcome
}

fn raw_path_metrics(points: &[PathPoint], horizon_minutes: u64) -> Option<RawPathMetrics> {
    let mut mfe_continuation: Option<f64> = None;
    let mut mae_continuation: Option<f64> = None;
    let horizon_seconds = horizon_minutes * 60;
    for point in points
        .iter()
        .take_while(|point| point.seconds <= horizon_seconds)
    {
        let value = point.continuation_return;
        if !value.is_finite() {
            continue;
        }
        if mfe_continuation.map_or(true, |current| value > current) {
            mfe_continuation = Some(value);
        }
        if mae_continuation.map_or(true, |current| value < current) {
            mae_continuation = Some(value);
        }
    }
    let mfe_continuation = mfe_continuation?;
    let mae_continuation = mae_continuation?;
    let mfe_reversal = -mae_continuation;
    let mae_reversal = -mfe_continuation;
    Some(RawPathMetrics {
        mfe_continuation: Some(mfe_continuation),
        mae_continuation: Some(mae_continuation),
        mfe_reversal: Some(mfe_reversal),
        mae_reversal: Some(mae_reversal),
        best_mfe: Some(mfe_continuation.max(mfe_reversal)),
    })
}

fn first_barrier_hit(
    points: &[PathPoint],
    horizon_minutes: u64,
    profit_barrier: f64,
    stop_barrier: f64,
) -> BarrierHit {
    first_barrier_hit_by(
        points,
        horizon_minutes,
        profit_barrier,
        stop_barrier,
        |value| value,
    )
}

fn first_barrier_hit_reversed(
    points: &[PathPoint],
    horizon_minutes: u64,
    profit_barrier: f64,
    stop_barrier: f64,
) -> BarrierHit {
    first_barrier_hit_by(
        points,
        horizon_minutes,
        profit_barrier,
        stop_barrier,
        |value| -value,
    )
}

fn first_barrier_hit_by<F>(
    points: &[PathPoint],
    horizon_minutes: u64,
    profit_barrier: f64,
    stop_barrier: f64,
    transform: F,
) -> BarrierHit
where
    F: Fn(f64) -> f64,
{
    let horizon_seconds = horizon_minutes * 60;
    for point in points
        .iter()
        .take_while(|point| point.seconds <= horizon_seconds)
    {
        let value = transform(point.continuation_return);
        if value >= profit_barrier {
            return BarrierHit {
                kind: HitKind::Profit,
                seconds: Some(point.seconds),
            };
        }
        if value <= -stop_barrier {
            return BarrierHit {
                kind: HitKind::Stop,
                seconds: Some(point.seconds),
            };
        }
    }
    BarrierHit {
        kind: HitKind::None,
        seconds: None,
    }
}

fn has_horizon_price(points: &[PathPoint], horizon_minutes: u64) -> bool {
    let horizon_seconds = horizon_minutes * 60;
    points
        .last()
        .map(|point| point.seconds >= horizon_seconds)
        .unwrap_or(false)
}

fn sigma_for_horizon(event: &JoinedEvent, horizon: Horizon) -> Option<f64> {
    if horizon.minutes <= 60 {
        event.trailing_realized_vol_1h
    } else {
        event.trailing_realized_vol_6h
    }
}

fn update_summary_stats(
    stats: &mut BTreeMap<SummaryKey, GroupStats>,
    event: &JoinedEvent,
    horizon: &str,
    outcome: &LabelOutcome,
) {
    for (group, group_value) in [
        ("overall", "all".to_string()),
        ("split", event.split.clone()),
        ("date", event.date_utc.clone()),
        ("pool", event.key.pool_address.clone()),
        ("quality_tier", event.quality_tier.clone()),
        ("volatility_regime", event.volatility_regime.clone()),
        ("quote_bucket", event.quote_notional_bucket.clone()),
        (
            "pool_concentration",
            event.pool_concentration_bucket.clone(),
        ),
        ("gas_bucket", event.gas_bucket.clone()),
        (
            "same_block_density",
            event.same_block_density_bucket.clone(),
        ),
        ("pool_dislocation", event.pool_dislocation_bucket.clone()),
    ] {
        stats
            .entry(SummaryKey {
                horizon: horizon.to_string(),
                group: group.to_string(),
                group_value,
            })
            .or_default()
            .update(outcome);
    }
}

fn update_sensitivity_stats(
    stats: &mut BTreeMap<SensitivityKey, (f64, GroupStats)>,
    event: &JoinedEvent,
    horizon: &str,
    outcome: &LabelOutcome,
    profile: &str,
    sigma_multiplier: f64,
) {
    for split in ["all", event.split.as_str()] {
        let entry = stats
            .entry(SensitivityKey {
                profile: profile.to_string(),
                horizon: horizon.to_string(),
                split: split.to_string(),
            })
            .or_insert_with(|| (sigma_multiplier, GroupStats::default()));
        entry.1.update(outcome);
    }
}

fn finalize_summary_rows(
    stats: &BTreeMap<SummaryKey, GroupStats>,
    run_tag: &str,
    source_run_tag: &str,
    feature_run_tag: &str,
) -> Vec<PathRegimeSummaryRow> {
    stats
        .iter()
        .map(|(key, stats)| PathRegimeSummaryRow {
            run_tag: run_tag.to_string(),
            source_run_tag: source_run_tag.to_string(),
            feature_run_tag: feature_run_tag.to_string(),
            horizon: key.horizon.clone(),
            group: key.group.clone(),
            group_value: key.group_value.clone(),
            rows: stats.rows,
            dead_zone_rows: stats.dead_zone_rows,
            tradable_path_rows: stats.tradable_path_rows,
            continuation_rows: stats.continuation_rows,
            reversal_rows: stats.reversal_rows,
            risk_first_rows: stats.risk_first_rows,
            missing_price_rows: stats.missing_price_rows,
            missing_cost_rows: stats.missing_cost_rows,
            missing_volatility_rows: stats.missing_volatility_rows,
            dead_zone_rate: rate(stats.dead_zone_rows, stats.rows),
            tradable_path_rate: rate(stats.tradable_path_rows, stats.rows),
            continuation_rate: rate(stats.continuation_rows, stats.rows),
            reversal_rate: rate(stats.reversal_rows, stats.rows),
            risk_first_rate: rate(stats.risk_first_rows, stats.rows),
            median_mfe_bps: quantile(stats.best_mfe_bps.clone(), 0.50),
            p90_mfe_bps: quantile(stats.best_mfe_bps.clone(), 0.90),
            median_cost_bps: quantile(stats.cost_bps.clone(), 0.50),
            median_sigma_bps: quantile(stats.sigma_bps.clone(), 0.50),
        })
        .collect()
}

fn finalize_sensitivity_rows(
    stats: &BTreeMap<SensitivityKey, (f64, GroupStats)>,
    run_tag: &str,
    source_run_tag: &str,
    feature_run_tag: &str,
) -> Vec<PathRegimeSensitivityRow> {
    stats
        .iter()
        .map(
            |(key, (sigma_multiplier, stats))| PathRegimeSensitivityRow {
                run_tag: run_tag.to_string(),
                source_run_tag: source_run_tag.to_string(),
                feature_run_tag: feature_run_tag.to_string(),
                profile: key.profile.clone(),
                sigma_multiplier: *sigma_multiplier,
                horizon: key.horizon.clone(),
                split: key.split.clone(),
                rows: stats.rows,
                dead_zone_rows: stats.dead_zone_rows,
                tradable_path_rows: stats.tradable_path_rows,
                continuation_rows: stats.continuation_rows,
                reversal_rows: stats.reversal_rows,
                risk_first_rows: stats.risk_first_rows,
                missing_price_rows: stats.missing_price_rows,
                missing_cost_rows: stats.missing_cost_rows,
                missing_volatility_rows: stats.missing_volatility_rows,
                dead_zone_rate: rate(stats.dead_zone_rows, stats.rows),
                tradable_path_rate: rate(stats.tradable_path_rows, stats.rows),
                continuation_rate: rate(stats.continuation_rows, stats.rows),
                reversal_rate: rate(stats.reversal_rows, stats.rows),
                risk_first_rate: rate(stats.risk_first_rows, stats.rows),
                median_mfe_bps: quantile(stats.best_mfe_bps.clone(), 0.50),
                p90_mfe_bps: quantile(stats.best_mfe_bps.clone(), 0.90),
                median_cost_bps: quantile(stats.cost_bps.clone(), 0.50),
                median_sigma_bps: quantile(stats.sigma_bps.clone(), 0.50),
            },
        )
        .collect()
}

fn label_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_utf8("source_run_tag", false),
        field_utf8("feature_run_tag", false),
        field_u64("block_number", false),
        field_utf8("event_time_utc", false),
        field_utf8("date_utc", false),
        field_utf8("hour_utc", false),
        field_utf8("split", false),
        field_utf8("transaction_hash", false),
        field_u64("transaction_index", false),
        field_u64("log_index", false),
        field_utf8("pool_address", false),
        field_utf8("dex_id", false),
        field_utf8("family", false),
        field_utf8("direction", false),
        field_utf8("quality_tier", false),
        field_utf8("horizon", false),
        field_u64("horizon_minutes", false),
        field_f64("quote_abs", true),
        field_u64("same_block_event_count", false),
        field_utf8("volatility_regime", false),
        field_utf8("quote_notional_bucket", false),
        field_utf8("pool_concentration_bucket", false),
        field_utf8("gas_bucket", false),
        field_utf8("same_block_density_bucket", false),
        field_utf8("pool_dislocation_bucket", false),
        field_f64("cost_return", true),
        field_f64("cost_bps", true),
        field_f64("sigma_return", true),
        field_f64("sigma_bps", true),
        field_f64("profit_barrier_return", true),
        field_f64("stop_barrier_return", true),
        field_f64("mfe_continuation", true),
        field_f64("mae_continuation", true),
        field_f64("mfe_reversal", true),
        field_f64("mae_reversal", true),
        field_f64("best_mfe", true),
        field_utf8("continuation_hit_kind", false),
        field_u64("continuation_hit_seconds", true),
        field_utf8("reversal_hit_kind", false),
        field_u64("reversal_hit_seconds", true),
        Field::new("dead_zone", DataType::Boolean, false),
        Field::new("tradable_path", DataType::Boolean, false),
        Field::new("risk_first", DataType::Boolean, false),
        field_utf8("directional_path", false),
        field_utf8("path_label", false),
        field_utf8("diagnostic_status", false),
    ]))
}

fn label_batch(schema: SchemaRef, rows: &[PathRegimeLabelRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            strings(rows.iter().map(|row| row.source_run_tag.clone())),
            strings(rows.iter().map(|row| row.feature_run_tag.clone())),
            u64s(rows.iter().map(|row| row.block_number)),
            strings(rows.iter().map(|row| row.event_time_utc.clone())),
            strings(rows.iter().map(|row| row.date_utc.clone())),
            strings(rows.iter().map(|row| row.hour_utc.clone())),
            strings(rows.iter().map(|row| row.split.clone())),
            strings(rows.iter().map(|row| row.transaction_hash.clone())),
            u64s(rows.iter().map(|row| row.transaction_index)),
            u64s(rows.iter().map(|row| row.log_index)),
            strings(rows.iter().map(|row| row.pool_address.clone())),
            strings(rows.iter().map(|row| row.dex_id.clone())),
            strings(rows.iter().map(|row| row.family.clone())),
            strings(rows.iter().map(|row| row.direction.clone())),
            strings(rows.iter().map(|row| row.quality_tier.clone())),
            strings(rows.iter().map(|row| row.horizon.clone())),
            u64s(rows.iter().map(|row| row.horizon_minutes)),
            opt_f64s(rows.iter().map(|row| row.quote_abs)),
            u64s(rows.iter().map(|row| row.same_block_event_count)),
            strings(rows.iter().map(|row| row.volatility_regime.clone())),
            strings(rows.iter().map(|row| row.quote_notional_bucket.clone())),
            strings(rows.iter().map(|row| row.pool_concentration_bucket.clone())),
            strings(rows.iter().map(|row| row.gas_bucket.clone())),
            strings(rows.iter().map(|row| row.same_block_density_bucket.clone())),
            strings(rows.iter().map(|row| row.pool_dislocation_bucket.clone())),
            opt_f64s(rows.iter().map(|row| row.cost_return)),
            opt_f64s(rows.iter().map(|row| row.cost_bps)),
            opt_f64s(rows.iter().map(|row| row.sigma_return)),
            opt_f64s(rows.iter().map(|row| row.sigma_bps)),
            opt_f64s(rows.iter().map(|row| row.profit_barrier_return)),
            opt_f64s(rows.iter().map(|row| row.stop_barrier_return)),
            opt_f64s(rows.iter().map(|row| row.mfe_continuation)),
            opt_f64s(rows.iter().map(|row| row.mae_continuation)),
            opt_f64s(rows.iter().map(|row| row.mfe_reversal)),
            opt_f64s(rows.iter().map(|row| row.mae_reversal)),
            opt_f64s(rows.iter().map(|row| row.best_mfe)),
            strings(rows.iter().map(|row| row.continuation_hit_kind.clone())),
            opt_u64s(rows.iter().map(|row| row.continuation_hit_seconds)),
            strings(rows.iter().map(|row| row.reversal_hit_kind.clone())),
            opt_u64s(rows.iter().map(|row| row.reversal_hit_seconds)),
            bools(rows.iter().map(|row| row.dead_zone)),
            bools(rows.iter().map(|row| row.tradable_path)),
            bools(rows.iter().map(|row| row.risk_first)),
            strings(rows.iter().map(|row| row.directional_path.clone())),
            strings(rows.iter().map(|row| row.path_label.clone())),
            strings(rows.iter().map(|row| row.diagnostic_status.clone())),
        ],
    )
    .context("failed to build path-regime label batch")
}

fn label_part_paths(config: &PathRegimeConfig) -> Vec<PathBuf> {
    let dt = config.run_tag.get(..10).unwrap_or("path").replace('_', "-");
    HORIZONS
        .iter()
        .map(|horizon| {
            custom_part_path(
                &config.data_root,
                DERIVED_DIR,
                PATH_REGIME_LABELS_DATASET,
                &dt,
                &format!(
                    "mon_usdc_{}_{}_h{}",
                    PATH_REGIME_LABELS_DATASET, config.run_tag, horizon.label
                ),
            )
        })
        .collect()
}

fn open_label_writers(paths: &[PathBuf], schema: SchemaRef) -> Result<Vec<ArrowWriter<File>>> {
    let mut writers = Vec::with_capacity(paths.len());
    for path in paths {
        ensure_parent_dir(path)?;
        let file =
            File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
        let props = WriterProperties::builder()
            .set_created_by("mon-usdc-path-regime-report".to_string())
            .build();
        writers.push(
            ArrowWriter::try_new(file, schema.clone(), Some(props))
                .with_context(|| format!("failed to create writer for {}", path.display()))?,
        );
    }
    Ok(writers)
}

fn build_output_paths(config: &PathRegimeConfig) -> PathRegimeOutputs {
    PathRegimeOutputs {
        label_parts: label_part_paths(config)
            .iter()
            .map(|path| path_string(path))
            .collect(),
        summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_path_regime_summary_{}.csv",
            config.run_tag
        ))),
        sensitivity_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_path_regime_sensitivity_{}.csv",
            config.run_tag
        ))),
        completion_json: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_path_regime_completion_{}.json",
            config.run_tag
        ))),
        report: path_string(
            &config
                .docs_dir
                .join("markets/mon-usdc/v1-path-regime-report.md"),
        ),
    }
}

fn write_report(
    summary: &PathRegimeSummary,
    summary_rows: &[PathRegimeSummaryRow],
    sensitivity_rows: &[PathRegimeSensitivityRow],
) -> Result<()> {
    let overall = summary_rows
        .iter()
        .filter(|row| row.group == "overall" && row.group_value == "all")
        .collect::<Vec<_>>();
    let baseline_table = overall
        .iter()
        .map(|row| {
            format!(
                "| {} | {} | {} | {} | {} | {} | {} | {} |",
                row.horizon,
                row.rows,
                fmt_rate(row.dead_zone_rate),
                fmt_rate(row.tradable_path_rate),
                fmt_rate(row.continuation_rate),
                fmt_rate(row.reversal_rate),
                fmt_rate(row.risk_first_rate),
                fmt_opt(row.median_cost_bps)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let sensitivity_overall = sensitivity_rows
        .iter()
        .filter(|row| row.split == "all")
        .map(|row| {
            format!(
                "| {} | {} | {} | {} | {} | {} |",
                row.profile,
                row.horizon,
                row.rows,
                fmt_rate(row.dead_zone_rate),
                fmt_rate(row.tradable_path_rate),
                fmt_rate(row.risk_first_rate)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let label_outputs = summary
        .outputs
        .label_parts
        .iter()
        .map(|path| format!("- `{path}`"))
        .collect::<Vec<_>>()
        .join("\n");

    let body = format!(
        "# MON/USDC V1 Path-Regime Report\n\nStatus: `{}` from source `{}` and features `{}`.\n\n这份报告只重打 path-label 并生成 regime summary；不使用 RPC，不修改 raw data，也不声称这是可执行交易规则。价格参考仍使用 minute VWAP/reference，入场点固定为事件后 1 分钟。\n\n## 成本与 Barrier\n\n- 成本公式：`C_e = 2f + 2eta + g_e + rho_e`\n- 默认参数：one-way fee `{}` bps，one-way slippage `{}` bps，risk buffer `{}` bps\n- baseline barrier：`B+ = B- = C_e + {} * sigma_e`\n- `5m/15m/1h` 使用 `trailing_realized_vol_1h`，`3h/6h` 使用 `trailing_realized_vol_6h`\n\n## Coverage\n\n- execution rows: `{}`\n- physical rows: `{}`\n- joined research events: `{}`\n- missing physical rows: `{}`\n- minute price rows: `{}`\n- label rows written: `{}`\n\n## Baseline Summary\n\n| Horizon | Rows | dead_zone | tradable_path | continuation | reversal | risk_first | Median Cost bps |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n{}\n\n## Barrier Sensitivity\n\n| Profile | Horizon | Rows | dead_zone | tradable_path | risk_first |\n| --- | --- | ---: | ---: | ---: | ---: |\n{}\n\n## Outputs\n\n- `{}`\n- `{}`\n- `{}`\n{}\n",
        summary.run_tag,
        summary.source_run_tag,
        summary.feature_run_tag,
        summary.cost_assumption.fee_bps_one_way,
        summary.cost_assumption.slippage_bps_one_way,
        summary.cost_assumption.risk_buffer_bps,
        summary.cost_assumption.baseline_sigma_multiplier,
        summary.coverage.execution_rows,
        summary.coverage.physical_rows,
        summary.coverage.joined_research_events,
        summary.coverage.missing_physical_rows,
        summary.coverage.minute_price_rows,
        summary.coverage.label_rows_written,
        baseline_table,
        sensitivity_overall,
        summary.outputs.summary_csv,
        summary.outputs.sensitivity_csv,
        summary.outputs.completion_json,
        label_outputs
    );
    let path = Path::new(&summary.outputs.report);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    fs::write(path, body).with_context(|| format!("failed to write {}", path.display()))
}

fn write_csv<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    ensure_parent_dir(path)?;
    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create {}", path.display()))?;
    for row in rows {
        writer.serialize(row)?;
    }
    writer.flush()?;
    Ok(())
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    ensure_parent_dir(path)?;
    let file =
        File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, value)
        .with_context(|| format!("failed to write {}", path.display()))
}

fn chronological_split_map<I>(dates: I) -> BTreeMap<String, String>
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

fn thresholds<I>(values: I, buckets: usize) -> Vec<f64>
where
    I: IntoIterator<Item = f64>,
{
    let mut values = values
        .into_iter()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    values.sort_by(|a, b| a.total_cmp(b));
    values.dedup_by(|a, b| (*a - *b).abs() < f64::EPSILON);
    if buckets <= 1 || values.len() < buckets {
        return Vec::new();
    }
    let len = values.len();
    (1..buckets)
        .filter_map(|bucket| values.get(((len * bucket) / buckets).min(len - 1)).copied())
        .collect()
}

fn quantile_bucket(value: Option<f64>, thresholds: &[f64], prefix: &str) -> String {
    let Some(value) = value.and_then(finite) else {
        return "unavailable".to_string();
    };
    let mut bucket = 0usize;
    while bucket < thresholds.len() && value > thresholds[bucket] {
        bucket += 1;
    }
    format!("{}{}", prefix, bucket + 1)
}

fn regime_bucket(value: Option<f64>, thresholds: &[f64]) -> String {
    let bucket = quantile_bucket(value, thresholds, "q");
    match bucket.as_str() {
        "q1" => "low".to_string(),
        "q2" => "mid".to_string(),
        "q3" => "high".to_string(),
        _ => bucket,
    }
}

fn floor_to_minute(timestamp: i64) -> i64 {
    timestamp - timestamp.rem_euclid(60)
}

fn parse_event_timestamp(value: &str) -> Result<i64> {
    DateTime::parse_from_rfc3339(value)
        .with_context(|| format!("failed to parse event_time_utc {value}"))
        .map(|value| value.timestamp())
}

fn side_multiplier(direction: &str) -> Option<f64> {
    match direction {
        "buy_base" => Some(1.0),
        "sell_base" => Some(-1.0),
        _ => None,
    }
}

fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn bps_to_return(value: f64) -> f64 {
    value / 10_000.0
}

fn to_bps(value: f64) -> f64 {
    value * 10_000.0
}

fn push_bps(values: &mut Vec<f64>, value: Option<f64>) {
    if let Some(value) = value.filter(|value| value.is_finite()) {
        values.push(to_bps(value));
    }
}

fn rate(count: u64, total: u64) -> Option<f64> {
    (total > 0).then_some(count as f64 / total as f64)
}

fn quantile(mut values: Vec<f64>, q: f64) -> Option<f64> {
    values.retain(|value| value.is_finite());
    if values.is_empty() {
        return None;
    }
    values.sort_by(|a, b| a.total_cmp(b));
    let index = (((values.len() - 1) as f64) * q.clamp(0.0, 1.0)).round() as usize;
    values.get(index).copied()
}

fn max_horizon_minutes() -> u64 {
    HORIZONS
        .iter()
        .map(|horizon| horizon.minutes)
        .max()
        .unwrap_or(0)
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

fn strings<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = String>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = StringBuilder::with_capacity(values.len(), values.len() * 16);
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn u64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = u64>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = UInt64Builder::with_capacity(values.len());
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn opt_u64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = Option<u64>>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = UInt64Builder::with_capacity(values.len());
    for value in values {
        match value {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

fn opt_f64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = Option<f64>>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        match value.and_then(finite) {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

fn bools<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = bool>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = BooleanBuilder::with_capacity(values.len());
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn fmt_rate(value: Option<f64>) -> String {
    value
        .map(|value| format!("{:.2}%", value * 100.0))
        .unwrap_or_else(|| "NA".to_string())
}

fn fmt_opt(value: Option<f64>) -> String {
    value
        .map(|value| format!("{value:.4}"))
        .unwrap_or_else(|| "NA".to_string())
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn current_executable_path() -> String {
    std::env::current_exe()
        .map(|path| path_string(&path))
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn event(direction: &str) -> JoinedEvent {
        JoinedEvent {
            key: EventKey {
                block_number: 1,
                transaction_hash: "0x1".to_string(),
                log_index: 0,
                pool_address: "0xpool".to_string(),
            },
            timestamp: 120,
            event_time_utc: "2026-01-01T00:02:00Z".to_string(),
            date_utc: "2026-01-01".to_string(),
            hour_utc: "2026-01-01T00:00:00Z".to_string(),
            transaction_index: 0,
            dex_id: "dex".to_string(),
            family: "v3".to_string(),
            direction: direction.to_string(),
            quality_tier: "A_observed".to_string(),
            split: "discovery".to_string(),
            quote_abs: Some(100.0),
            roundtrip_gas_return_proxy: Some(0.001),
            dislocation_return: Some(0.0),
            pool_quote_hhi: Some(0.5),
            trailing_realized_vol_1h: Some(0.01),
            trailing_realized_vol_6h: Some(0.02),
            same_block_event_count: 1,
            volatility_regime: "mid".to_string(),
            quote_notional_bucket: "q1".to_string(),
            pool_concentration_bucket: "mid".to_string(),
            gas_bucket: "mid".to_string(),
            same_block_density_bucket: "low".to_string(),
            pool_dislocation_bucket: "low".to_string(),
        }
    }

    fn test_config() -> PathRegimeConfig {
        PathRegimeConfig {
            fee_bps_one_way: 10.0,
            slippage_bps_one_way: 5.0,
            risk_buffer_bps: 5.0,
            baseline_sigma_multiplier: 0.0,
            ..PathRegimeConfig::default()
        }
    }

    #[test]
    fn path_regime_side_sign_uses_trade_direction() {
        assert_eq!(side_multiplier("buy_base"), Some(1.0));
        assert_eq!(side_multiplier("sell_base"), Some(-1.0));
        assert_eq!(side_multiplier("unknown"), None);
    }

    #[test]
    fn path_regime_log_path_flips_for_sell_base() {
        let buy = event("buy_base");
        let sell = event("sell_base");
        let series = MinutePriceSeries {
            start_minute: 180,
            rows: vec![Some(100.0), Some(101.0)],
        };
        let buy_points = build_path_points(&buy, &series, 1).unwrap();
        let sell_points = build_path_points(&sell, &series, 1).unwrap();
        let expected = (101.0_f64 / 100.0).ln();
        assert!((buy_points[0].continuation_return - expected).abs() < 1e-12);
        assert!((sell_points[0].continuation_return + expected).abs() < 1e-12);
    }

    #[test]
    fn path_regime_mfe_mae_are_path_extrema() {
        let points = vec![
            PathPoint {
                seconds: 60,
                continuation_return: 0.01,
            },
            PathPoint {
                seconds: 120,
                continuation_return: -0.02,
            },
            PathPoint {
                seconds: 180,
                continuation_return: 0.03,
            },
        ];
        let metrics = raw_path_metrics(&points, 3).unwrap();
        assert_eq!(metrics.mfe_continuation, Some(0.03));
        assert_eq!(metrics.mae_continuation, Some(-0.02));
        assert_eq!(metrics.mfe_reversal, Some(0.02));
        assert_eq!(metrics.mae_reversal, Some(-0.03));
        assert_eq!(metrics.best_mfe, Some(0.03));
    }

    #[test]
    fn path_regime_profit_and_stop_use_first_hit_order() {
        let points = vec![
            PathPoint {
                seconds: 60,
                continuation_return: -0.02,
            },
            PathPoint {
                seconds: 120,
                continuation_return: 0.04,
            },
        ];
        let continuation = first_barrier_hit(&points, 2, 0.03, 0.01);
        let reversal = first_barrier_hit_reversed(&points, 2, 0.01, 0.03);
        assert_eq!(continuation.kind, HitKind::Stop);
        assert_eq!(continuation.seconds, Some(60));
        assert_eq!(reversal.kind, HitKind::Profit);
        assert_eq!(reversal.seconds, Some(60));
    }

    #[test]
    fn path_regime_cost_bps_conversion_includes_roundtrip_terms() {
        let config = test_config();
        let event = event("buy_base");
        let points = Some(vec![PathPoint {
            seconds: 60,
            continuation_return: 0.02,
        }]);
        let outcome = label_for_event(
            &event,
            &points,
            Horizon {
                label: "1m",
                minutes: 1,
            },
            &config,
            BarrierProfile {
                name: "cost_only",
                sigma_multiplier: 0.0,
            },
        );
        let expected = bps_to_return(2.0 * 10.0 + 2.0 * 5.0 + 5.0) + 0.001;
        assert!((outcome.cost_return.unwrap() - expected).abs() < 1e-12);
    }

    #[test]
    fn path_regime_missing_statuses_are_not_forced() {
        let mut event = event("buy_base");
        let config = test_config();
        let missing_price = label_for_event(
            &event,
            &None,
            HORIZONS[0],
            &config,
            BarrierProfile {
                name: "cost_only",
                sigma_multiplier: 0.0,
            },
        );
        assert_eq!(missing_price.path_label, "missing_price");

        event.roundtrip_gas_return_proxy = None;
        let points = Some(vec![PathPoint {
            seconds: 60,
            continuation_return: 0.02,
        }]);
        let missing_cost = label_for_event(
            &event,
            &points,
            Horizon {
                label: "1m",
                minutes: 1,
            },
            &config,
            BarrierProfile {
                name: "cost_only",
                sigma_multiplier: 0.0,
            },
        );
        assert_eq!(missing_cost.path_label, "missing_cost");

        event.roundtrip_gas_return_proxy = Some(0.0);
        event.trailing_realized_vol_1h = None;
        let missing_vol = label_for_event(
            &event,
            &points,
            Horizon {
                label: "1m",
                minutes: 1,
            },
            &config,
            BarrierProfile {
                name: "vol_half",
                sigma_multiplier: 0.5,
            },
        );
        assert_eq!(missing_vol.path_label, "missing_volatility");
    }
}

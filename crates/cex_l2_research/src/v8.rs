use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread::sleep;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, ArrayRef, Float64Array, Float64Builder, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, Days, Utc};
use finance_chain_core::storage::{ensure_parent_dir, string_array, u64_array};
use parquet::arrow::{ArrowWriter, arrow_reader::ParquetRecordBatchReaderBuilder};
use parquet::file::properties::WriterProperties;
use serde::{Deserialize, Serialize};

use crate::download::{DEFAULT_BONK_DATA_ROOT, path_string};

pub const DEFAULT_V8_RUN_TAG: &str = "20260513_bullish_l2_basket_price_v1";

const MINUTE_US: u64 = 60_000_000;
const GUARDRAIL: &str = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim";
const ACCOUNT_QUOTE: f64 = 100.0;
const DEFAULT_FEE_BPS: f64 = 2.0;
const DEFAULT_TP_BPS: &[u32] = &[30, 50, 75, 100];
const DEFAULT_SL_BPS: &[u32] = &[20, 30, 50, 75];
const DEFAULT_TIMEOUT_MINUTES: &[u32] = &[10, 20, 30, 60];
const DEFAULT_EXECUTION_MODELS: &[&str] =
    &["mid_research", "maker_light", "taker_spread", "wide_stress"];
const DEFAULT_SYMBOLS: &[&str] = &["BONK1MUSDC", "BONK1MUSDT"];

#[derive(Debug, Clone)]
pub struct V8Config {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub run_tag: String,
    pub out_tag: String,
    pub report_md: PathBuf,
    pub resume: bool,
    pub force: bool,
    pub stop_after: Option<String>,
    pub dry_run: bool,
    pub skip_trades_write: bool,
    pub tp_bps: Vec<u32>,
    pub sl_bps: Vec<u32>,
    pub timeout_minutes: Vec<u32>,
    pub execution_models: Vec<String>,
    pub notional_quote: f64,
    pub fee_bps: f64,
    pub debounce_on_minutes: usize,
    pub debounce_off_minutes: usize,
    pub cooldown_minutes: usize,
    pub min_hold_minutes: usize,
}

impl Default for V8Config {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_BONK_DATA_ROOT),
            date_dir: PathBuf::from("date"),
            run_tag: DEFAULT_V8_RUN_TAG.to_string(),
            out_tag: DEFAULT_V8_RUN_TAG.to_string(),
            report_md: PathBuf::from("docs/markets/bonk/v1-cex-v8-profit-factor-factory.md"),
            resume: true,
            force: false,
            stop_after: None,
            dry_run: false,
            skip_trades_write: false,
            tp_bps: DEFAULT_TP_BPS.to_vec(),
            sl_bps: DEFAULT_SL_BPS.to_vec(),
            timeout_minutes: DEFAULT_TIMEOUT_MINUTES.to_vec(),
            execution_models: DEFAULT_EXECUTION_MODELS
                .iter()
                .map(|value| value.to_string())
                .collect(),
            notional_quote: ACCOUNT_QUOTE,
            fee_bps: DEFAULT_FEE_BPS,
            debounce_on_minutes: 2,
            debounce_off_minutes: 2,
            cooldown_minutes: 120,
            min_hold_minutes: 2,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct V8Summary {
    pub run_tag: String,
    pub out_tag: String,
    pub factor_rows: usize,
    pub factor_count: usize,
    pub factor_audit_rows: usize,
    pub candidate_fit_rows: usize,
    pub trades: usize,
    pub daily_rows: usize,
    pub summary_rows: usize,
    pub validation_passed: bool,
    pub manifest_json: String,
    pub checkpoint_json: String,
    pub factor_panel_parquet: String,
    pub factor_catalog_csv: String,
    pub factor_audit_csv: String,
    pub candidate_gates_csv: String,
    pub trades_csv: String,
    pub daily_csv: String,
    pub summary_csv: String,
    pub exit_reasons_csv: String,
    pub fold_stability_csv: String,
    pub non_overlap_csv: String,
    pub parameter_sensitivity_csv: String,
    pub single_day_dependence_csv: String,
    pub failure_diagnostics_csv: String,
    pub completion_json: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    l2_state: PathBuf,
    price_context: PathBuf,
    covariance: PathBuf,
    factor_panel: PathBuf,
    factor_catalog: PathBuf,
    factor_audit: PathBuf,
    candidate_gates: PathBuf,
    trades: PathBuf,
    daily: PathBuf,
    summary: PathBuf,
    exit_reasons: PathBuf,
    fold_stability: PathBuf,
    non_overlap: PathBuf,
    parameter_sensitivity: PathBuf,
    single_day_dependence: PathBuf,
    failure_diagnostics: PathBuf,
    manifest: PathBuf,
    checkpoint: PathBuf,
    completion: PathBuf,
}

impl Paths {
    fn new(config: &V8Config) -> Self {
        let out_tag = out_tag(config);
        let prefix = format!("bonk_v8_profit_factor_factory_{out_tag}");
        Self {
            l2_state: config
                .data_root
                .join("derived/bonk_cex_l2_state")
                .join(format!("bonk_cex_l2_state_{}.parquet", config.run_tag)),
            price_context: config
                .data_root
                .join("derived/bonk_cex_price_context")
                .join(format!("bonk_cex_price_context_{}.parquet", config.run_tag)),
            covariance: config
                .data_root
                .join("derived/bonk_cex_covariance_state")
                .join(format!(
                    "bonk_cex_covariance_state_{}.parquet",
                    config.run_tag
                )),
            factor_panel: config
                .data_root
                .join("derived/bonk_v8_factor_panel")
                .join(format!("bonk_v8_factor_panel_{out_tag}.parquet")),
            factor_catalog: config
                .date_dir
                .join(format!("bonk_v8_factor_catalog_{out_tag}.csv")),
            factor_audit: config
                .date_dir
                .join(format!("bonk_v8_factor_audit_{out_tag}.csv")),
            candidate_gates: config
                .date_dir
                .join(format!("bonk_v8_candidate_gates_{out_tag}.csv")),
            trades: config
                .date_dir
                .join(format!("bonk_v8_episode_backtest_{out_tag}_trades.csv")),
            daily: config
                .date_dir
                .join(format!("bonk_v8_episode_backtest_{out_tag}_daily.csv")),
            summary: config
                .date_dir
                .join(format!("bonk_v8_episode_backtest_{out_tag}_summary.csv")),
            exit_reasons: config.date_dir.join(format!(
                "bonk_v8_episode_backtest_{out_tag}_exit_reasons.csv"
            )),
            fold_stability: config.date_dir.join(format!(
                "bonk_v8_episode_backtest_{out_tag}_fold_stability.csv"
            )),
            non_overlap: config.date_dir.join(format!(
                "bonk_v8_episode_backtest_{out_tag}_non_overlap.csv"
            )),
            parameter_sensitivity: config.date_dir.join(format!(
                "bonk_v8_episode_backtest_{out_tag}_parameter_sensitivity.csv"
            )),
            single_day_dependence: config.date_dir.join(format!(
                "bonk_v8_episode_backtest_{out_tag}_single_day_dependence.csv"
            )),
            failure_diagnostics: config.date_dir.join(format!(
                "bonk_v8_episode_backtest_{out_tag}_failure_diagnostics.csv"
            )),
            manifest: config.date_dir.join(format!("{prefix}_manifest.json")),
            checkpoint: config.date_dir.join(format!("{prefix}_checkpoint.json")),
            completion: config.date_dir.join(format!("{prefix}_completion.json")),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct StepState {
    name: String,
    status: String,
    started_at_utc: String,
    finished_at_utc: String,
    detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Checkpoint {
    run_tag: String,
    out_tag: String,
    guardrail: String,
    updated_at_utc: String,
    steps: Vec<StepState>,
}

#[derive(Debug, Clone, Serialize)]
struct Manifest {
    run_name: String,
    run_tag: String,
    out_tag: String,
    generated_at_utc: String,
    guardrail: String,
    no_new_raw_data: bool,
    inputs: Vec<FileFingerprint>,
    outputs: BTreeMap<String, String>,
    steps: Vec<String>,
    resume_checkpoint: String,
}

#[derive(Debug, Clone, Serialize)]
struct FileFingerprint {
    path: String,
    exists: bool,
    bytes: u64,
    modified_unix_seconds: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
struct Completion {
    run_name: String,
    generated_at_utc: String,
    run_tag: String,
    out_tag: String,
    guardrail: String,
    config: CompletionConfig,
    counts: CompletionCounts,
    outputs: BTreeMap<String, String>,
    validation: ValidationChecks,
}

#[derive(Debug, Clone, Serialize)]
struct CompletionConfig {
    tp_bps: Vec<u32>,
    sl_bps: Vec<u32>,
    timeout_minutes: Vec<u32>,
    execution_models: Vec<String>,
    notional_quote: f64,
    fee_bps: f64,
    debounce_on_minutes: usize,
    debounce_off_minutes: usize,
    cooldown_minutes: usize,
    min_hold_minutes: usize,
}

#[derive(Debug, Clone, Serialize)]
struct CompletionCounts {
    factor_rows: usize,
    factor_count: usize,
    factor_audit_rows: usize,
    candidate_fit_rows: usize,
    trades: usize,
    daily_rows: usize,
    summary_rows: usize,
}

#[derive(Debug, Clone, Serialize)]
struct ValidationChecks {
    duplicate_trade_ids: usize,
    missing_exit_reason: usize,
    daily_trade_pnl_abs_diff: f64,
    non_overlap_violations: usize,
    cost_monotonic_violations: usize,
    primary_exec_rows: usize,
    passed: bool,
}

#[derive(Debug, Clone, Serialize)]
struct FactorCatalogRow {
    factor_name: String,
    family: String,
    description: String,
    trailing_only: bool,
    train_fit_required: bool,
}

#[derive(Debug, Clone, Copy)]
struct FactorDef {
    name: &'static str,
    family: &'static str,
    description: &'static str,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct L2RawRow {
    timestamp_utc: String,
    timestamp_us: u64,
    symbol: String,
    mid_open: Option<f64>,
    mid_high: Option<f64>,
    mid_low: Option<f64>,
    mid_close: Option<f64>,
    spread_bps_median: Option<f64>,
    spread_bps_last: Option<f64>,
    top_depth_bid: Option<f64>,
    top_depth_ask: Option<f64>,
    microprice_offset: Option<f64>,
    snapshot_spread_bps: Option<f64>,
    snapshot_microprice_offset: Option<f64>,
    wobi5: Option<f64>,
    wobi25: Option<f64>,
    depth_imbalance_5: Option<f64>,
    depth_imbalance_25: Option<f64>,
    depth_bid_5: Option<f64>,
    depth_ask_5: Option<f64>,
    depth_bid_25: Option<f64>,
    depth_ask_25: Option<f64>,
    trade_count: u64,
    trade_notional: f64,
    trade_flow_imbalance: Option<f64>,
    reported_buy_share: Option<f64>,
    l2_ret_1m_bps: Option<f64>,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct PriceRawRow {
    timestamp_us: u64,
    symbol: String,
    close: Option<f64>,
    quote_volume: f64,
    trade_count: u64,
    ret_1m_bps: Option<f64>,
    rv_15m_bps: Option<f64>,
    rv_1h_bps: Option<f64>,
    rv_4h_bps: Option<f64>,
    rv_12h_bps: Option<f64>,
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

#[derive(Debug, Clone)]
struct CovRawRow {
    timestamp_us: u64,
    avg_corr_60m: Option<f64>,
    first_eigen_share_60m: Option<f64>,
    cross_symbol_abs_ret_mean_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct FactorRow {
    run_tag: String,
    timestamp_utc: String,
    timestamp_us: u64,
    symbol: String,
    mid_open: Option<f64>,
    mid_high: Option<f64>,
    mid_low: Option<f64>,
    mid_close: Option<f64>,
    spread_bps: Option<f64>,
    depth_bid_25: Option<f64>,
    depth_ask_25: Option<f64>,
    factors: Vec<Option<f64>>,
}

#[derive(Debug, Clone, Serialize)]
struct FactorAuditRow {
    run_tag: String,
    out_tag: String,
    fold: String,
    symbol: String,
    factor_name: String,
    family: String,
    side: String,
    threshold_fit_on_train: String,
    horizon_minutes: u32,
    train_count: usize,
    valid_count: usize,
    selected_train_count: usize,
    selected_valid_count: usize,
    selected_valid_share: f64,
    train_mean_future_bps: Option<f64>,
    valid_mean_future_bps: Option<f64>,
    valid_median_future_bps: Option<f64>,
    valid_win_rate: Option<f64>,
    valid_signal_per_day: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CandidateFitRow {
    run_tag: String,
    out_tag: String,
    fold: String,
    symbol: String,
    candidate_id: String,
    candidate_group: String,
    candidate_name: String,
    gate_expression: String,
    fit_detail: String,
    selected_minutes: usize,
    selected_share: f64,
    starts_after_debounce: usize,
    starts_per_day: f64,
    debounce_on_minutes: usize,
    debounce_off_minutes: usize,
    cooldown_minutes: usize,
    min_hold_minutes: usize,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct CandidateSpec {
    candidate_id: &'static str,
    candidate_group: &'static str,
    candidate_name: &'static str,
    description: &'static str,
    conditions: Vec<ConditionSpec>,
}

#[derive(Debug, Clone)]
enum ConditionSpec {
    Factor {
        factor: &'static str,
        side: ConditionSide,
        quantile: f64,
    },
    Weighted {
        score_id: &'static str,
        side: ConditionSide,
        quantile: f64,
    },
}

#[derive(Debug, Clone, Copy)]
enum ConditionSide {
    Low,
    High,
    HighAbs,
}

#[derive(Debug, Clone)]
struct FitCondition {
    label: String,
    side: ConditionSide,
    threshold: f64,
    weighted: Option<WeightedFit>,
    factor_idx: Option<usize>,
}

#[derive(Debug, Clone)]
struct WeightedFit {
    score_id: String,
    terms: Vec<WeightedTerm>,
}

#[derive(Debug, Clone)]
struct WeightedTerm {
    factor_idx: usize,
    factor_name: String,
    mean: f64,
    std: f64,
    weight: f64,
}

#[derive(Debug, Clone)]
struct SignalRow {
    timestamp_us: u64,
    timestamp_utc: String,
    symbol: String,
    open: Option<f64>,
    high: Option<f64>,
    low: Option<f64>,
    close: Option<f64>,
    spread_bps: Option<f64>,
    depth_bid_25: Option<f64>,
    depth_ask_25: Option<f64>,
    gate_selected: bool,
}

#[derive(Debug, Clone)]
struct BaseTrade {
    base_trade_number: usize,
    fold: String,
    candidate_group: String,
    candidate_id: String,
    candidate_name: String,
    gate_expression: String,
    symbol: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    signal_timestamp_utc: String,
    signal_timestamp_us: u64,
    entry_timestamp_utc: String,
    entry_timestamp_us: u64,
    exit_timestamp_utc: String,
    exit_timestamp_us: u64,
    entry_price: f64,
    exit_price: f64,
    exit_reason: String,
    gross_bps: f64,
    duration_minutes: f64,
    mfe_bps: f64,
    mae_bps: f64,
    same_bar_ambiguous: bool,
    fallback_bar_count: u32,
    entry_price_fallback: bool,
    entry_spread_bps: Option<f64>,
    entry_depth_bid_25: Option<f64>,
    entry_depth_ask_25: Option<f64>,
    thresholds_fit_on_train: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TradeRow {
    trade_id: String,
    run_tag: String,
    out_tag: String,
    fold: String,
    candidate_group: String,
    candidate_id: String,
    candidate_name: String,
    gate_expression: String,
    symbol: String,
    execution_model: String,
    notional_quote: f64,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    signal_timestamp_utc: String,
    signal_timestamp_us: u64,
    entry_timestamp_utc: String,
    entry_timestamp_us: u64,
    exit_timestamp_utc: String,
    exit_timestamp_us: u64,
    entry_price: f64,
    exit_price: f64,
    exit_reason: String,
    gross_bps: f64,
    cost_bps: f64,
    net_bps: f64,
    pnl_quote: f64,
    duration_minutes: f64,
    mfe_bps: f64,
    mae_bps: f64,
    same_bar_ambiguous: bool,
    fallback_bar_count: u32,
    entry_price_fallback: bool,
    depth_missing_for_cost: bool,
    entry_participation_depth25: Option<f64>,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DailyRow {
    fold: String,
    date: String,
    candidate_group: String,
    candidate_id: String,
    candidate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    notional_quote: f64,
    trade_count: usize,
    total_pnl_quote: f64,
    return_bps_on_100: f64,
    win_rate: f64,
    max_intraday_drawdown_quote: f64,
    exposure_minutes: f64,
    turnover_quote: f64,
    best_trade_pnl_quote: f64,
    worst_trade_pnl_quote: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SummaryRow {
    summary_scope: String,
    fold: String,
    candidate_group: String,
    candidate_id: String,
    candidate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    notional_quote: f64,
    days: usize,
    trade_count: usize,
    total_pnl_quote: f64,
    total_return_bps_on_100: f64,
    avg_daily_pnl_quote: f64,
    median_daily_pnl_quote: f64,
    avg_daily_return_bps_on_100: f64,
    positive_day_rate: f64,
    max_drawdown_quote: f64,
    trades_per_day: f64,
    win_rate: f64,
    profit_factor: Option<f64>,
    median_trade_net_bps: Option<f64>,
    p25_trade_net_bps: Option<f64>,
    p75_trade_net_bps: Option<f64>,
    avg_gross_bps: Option<f64>,
    avg_cost_bps: Option<f64>,
    avg_net_bps: Option<f64>,
    median_duration_minutes: Option<f64>,
    exposure_minutes: f64,
    turnover_quote: f64,
    target_frequency_pass: bool,
    ambiguous_trade_count: usize,
    ambiguous_trade_rate: f64,
    exit_reason_counts_json: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct ExitReasonRow {
    summary_scope: String,
    fold: String,
    candidate_id: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    exit_reason: String,
    trade_count: usize,
    pnl_quote: f64,
    avg_net_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct FoldStabilityRow {
    candidate_id: String,
    candidate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    fold2_pnl_quote: Option<f64>,
    fold3_pnl_quote: Option<f64>,
    fold2_trades_per_day: Option<f64>,
    fold3_trades_per_day: Option<f64>,
    fold2_fold3_both_nonnegative: bool,
    stability_read: String,
}

#[derive(Debug, Clone, Serialize)]
struct NonOverlapRow {
    candidate_id: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    trade_count: usize,
    total_pnl_quote: f64,
    overlapping_trade_pairs: usize,
    non_overlap_mode: String,
}

#[derive(Debug, Clone, Serialize)]
struct ParameterSensitivityRow {
    candidate_id: String,
    candidate_name: String,
    symbol: String,
    execution_model: String,
    config_count: usize,
    best_total_pnl_quote: f64,
    median_total_pnl_quote: f64,
    worst_total_pnl_quote: f64,
    positive_config_rate: f64,
    best_trades_per_day: f64,
    pnl_range_quote: f64,
    sensitivity_read: String,
}

#[derive(Debug, Clone, Serialize)]
struct SingleDayDependenceRow {
    candidate_id: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    total_pnl_quote: f64,
    best_day: String,
    best_day_pnl_quote: f64,
    best_day_share_of_abs_pnl: f64,
    positive_days: usize,
    dependence_read: String,
}

#[derive(Debug, Clone, Serialize)]
struct FailureDiagnosticRow {
    candidate_id: String,
    candidate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    total_pnl_quote: f64,
    trades_per_day: f64,
    max_drawdown_quote: f64,
    fold2_fold3_stable: bool,
    target_frequency_pass: bool,
    primary_failure: String,
    diagnostic_detail: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct ConfigKey {
    fold: String,
    candidate_group: String,
    candidate_id: String,
    candidate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct ConfigRow {
    key: ConfigKey,
    validation_dates: Vec<String>,
    notional_quote: f64,
    episode_starts: usize,
    entry_skips: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct AllKey {
    candidate_group: String,
    candidate_id: String,
    candidate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
}

#[derive(Debug, Clone, Serialize)]
struct FoldDef {
    name: &'static str,
    train_end_utc: &'static str,
    valid_start_utc: &'static str,
    valid_end_utc: &'static str,
}

impl FoldDef {
    fn train_end_us(&self) -> Result<u64> {
        utc_us(self.train_end_utc)
    }

    fn valid_start_us(&self) -> Result<u64> {
        utc_us(self.valid_start_utc)
    }

    fn valid_end_us(&self) -> Result<u64> {
        utc_us(self.valid_end_utc)
    }

    fn validation_dates(&self) -> Result<Vec<String>> {
        let mut date = DateTime::parse_from_rfc3339(self.valid_start_utc)?
            .with_timezone(&Utc)
            .date_naive();
        let end = DateTime::parse_from_rfc3339(self.valid_end_utc)?
            .with_timezone(&Utc)
            .date_naive();
        let mut out = Vec::new();
        while date <= end {
            out.push(date.to_string());
            date = date
                .checked_add_days(Days::new(1))
                .ok_or_else(|| anyhow!("date overflow"))?;
        }
        Ok(out)
    }

    fn day_count(&self) -> Result<f64> {
        Ok(self.validation_dates()?.len() as f64)
    }
}

const FOLDS: &[FoldDef] = &[
    FoldDef {
        name: "fold1",
        train_end_utc: "2026-05-02T23:59:00Z",
        valid_start_utc: "2026-05-03T12:00:00Z",
        valid_end_utc: "2026-05-05T23:59:00Z",
    },
    FoldDef {
        name: "fold2",
        train_end_utc: "2026-05-05T23:59:00Z",
        valid_start_utc: "2026-05-06T12:00:00Z",
        valid_end_utc: "2026-05-08T23:59:00Z",
    },
    FoldDef {
        name: "fold3",
        train_end_utc: "2026-05-08T23:59:00Z",
        valid_start_utc: "2026-05-09T12:00:00Z",
        valid_end_utc: "2026-05-12T11:59:00Z",
    },
];

pub fn run_v8_profit_factor_factory(config: &V8Config) -> Result<V8Summary> {
    validate_config(config)?;
    let paths = Paths::new(config);
    ensure_parent_dir(&paths.manifest)?;
    ensure_parent_dir(&paths.factor_panel)?;
    let factor_defs = factor_defs();
    let mut checkpoint = load_checkpoint(&paths.checkpoint, config)?;
    write_manifest(config, &paths, &factor_defs)?;

    let mut factor_rows = Vec::new();
    if should_run_step(
        config,
        &checkpoint,
        "factor_panel",
        &[&paths.factor_panel, &paths.factor_catalog],
    ) {
        mark_step(
            &mut checkpoint,
            &paths.checkpoint,
            "factor_panel",
            "running",
            "building factor panel",
        )?;
        if config.dry_run {
            mark_step(
                &mut checkpoint,
                &paths.checkpoint,
                "factor_panel",
                "dry_run",
                "not written",
            )?;
        } else {
            factor_rows = build_factor_panel(config, &paths, &factor_defs)?;
            write_factor_panel(&paths.factor_panel, &factor_rows, &factor_defs)?;
            write_csv_atomic(&paths.factor_catalog, &factor_catalog_rows(&factor_defs))?;
            mark_step(
                &mut checkpoint,
                &paths.checkpoint,
                "factor_panel",
                "complete",
                &format!("rows={} factors={}", factor_rows.len(), factor_defs.len()),
            )?;
        }
        if stop_after(config, "factor_panel") {
            return summary_from_disk(config, &paths, &factor_defs);
        }
    }

    if factor_rows.is_empty() && paths.factor_panel.exists() {
        factor_rows = read_factor_panel(&paths.factor_panel, &factor_defs)?;
    }

    let mut factor_audit = Vec::new();
    if should_run_step(config, &checkpoint, "factor_audit", &[&paths.factor_audit]) {
        mark_step(
            &mut checkpoint,
            &paths.checkpoint,
            "factor_audit",
            "running",
            "testing broad factor universe",
        )?;
        if config.dry_run {
            mark_step(
                &mut checkpoint,
                &paths.checkpoint,
                "factor_audit",
                "dry_run",
                "not written",
            )?;
        } else {
            factor_audit = build_factor_audit(config, &factor_rows, &factor_defs)?;
            write_csv_atomic(&paths.factor_audit, &factor_audit)?;
            mark_step(
                &mut checkpoint,
                &paths.checkpoint,
                "factor_audit",
                "complete",
                &format!("rows={}", factor_audit.len()),
            )?;
        }
        if stop_after(config, "factor_audit") {
            return summary_from_disk(config, &paths, &factor_defs);
        }
    }

    let mut episode_outputs = EpisodeOutputs::default();
    if should_run_step(
        config,
        &checkpoint,
        "episode_backtest",
        &[
            &paths.candidate_gates,
            &paths.daily,
            &paths.summary,
            &paths.exit_reasons,
            &paths.fold_stability,
            &paths.non_overlap,
            &paths.parameter_sensitivity,
            &paths.single_day_dependence,
            &paths.failure_diagnostics,
        ],
    ) {
        mark_step(
            &mut checkpoint,
            &paths.checkpoint,
            "episode_backtest",
            "running",
            "canonical executable episodes",
        )?;
        if config.dry_run {
            mark_step(
                &mut checkpoint,
                &paths.checkpoint,
                "episode_backtest",
                "dry_run",
                "not written",
            )?;
        } else {
            episode_outputs = run_episode_backtests(config, &factor_rows, &factor_defs, &paths)?;
            if !config.skip_trades_write {
                write_csv_direct(&paths.trades, &episode_outputs.trades)?;
            }
            write_csv_atomic(&paths.candidate_gates, &episode_outputs.candidate_fits)?;
            write_csv_atomic(&paths.daily, &episode_outputs.daily)?;
            write_csv_atomic(&paths.summary, &episode_outputs.summary)?;
            write_csv_atomic(&paths.exit_reasons, &episode_outputs.exit_reasons)?;
            write_csv_atomic(&paths.fold_stability, &episode_outputs.fold_stability)?;
            write_csv_atomic(&paths.non_overlap, &episode_outputs.non_overlap)?;
            write_csv_atomic(
                &paths.parameter_sensitivity,
                &episode_outputs.parameter_sensitivity,
            )?;
            write_csv_atomic(
                &paths.single_day_dependence,
                &episode_outputs.single_day_dependence,
            )?;
            write_csv_atomic(
                &paths.failure_diagnostics,
                &episode_outputs.failure_diagnostics,
            )?;
            mark_step(
                &mut checkpoint,
                &paths.checkpoint,
                "episode_backtest",
                "complete",
                &format!(
                    "trades={} daily={} summary={}",
                    episode_outputs.trades.len(),
                    episode_outputs.daily.len(),
                    episode_outputs.summary.len()
                ),
            )?;
        }
        if stop_after(config, "episode_backtest") {
            return summary_from_disk(config, &paths, &factor_defs);
        }
    }

    if episode_outputs.summary.is_empty() && paths.summary.exists() {
        episode_outputs = read_episode_outputs_for_report(&paths)?;
    }

    let validation = validate_outputs(&episode_outputs.trades, &episode_outputs.daily);
    if should_run_step(
        config,
        &checkpoint,
        "report",
        &[&paths.completion, &config.report_md],
    ) {
        mark_step(
            &mut checkpoint,
            &paths.checkpoint,
            "report",
            "running",
            "writing report and completion",
        )?;
        if !config.dry_run {
            let completion = build_completion(
                config,
                &paths,
                &factor_defs,
                factor_rows.len(),
                factor_audit.len(),
                &episode_outputs,
                &validation,
            );
            write_json_atomic(&paths.completion, &completion)?;
            let report = build_report(
                config,
                &paths,
                &factor_defs,
                factor_rows.len(),
                factor_audit.len(),
                &episode_outputs,
                &validation,
            );
            write_text_atomic(&config.report_md, &report)?;
        }
        mark_step(
            &mut checkpoint,
            &paths.checkpoint,
            "report",
            "complete",
            "report written",
        )?;
    }

    Ok(V8Summary {
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        factor_rows: factor_rows.len(),
        factor_count: factor_defs.len(),
        factor_audit_rows: factor_audit.len(),
        candidate_fit_rows: episode_outputs.candidate_fits.len(),
        trades: episode_outputs.trades.len(),
        daily_rows: episode_outputs.daily.len(),
        summary_rows: episode_outputs.summary.len(),
        validation_passed: validation.passed,
        manifest_json: path_string(&paths.manifest),
        checkpoint_json: path_string(&paths.checkpoint),
        factor_panel_parquet: path_string(&paths.factor_panel),
        factor_catalog_csv: path_string(&paths.factor_catalog),
        factor_audit_csv: path_string(&paths.factor_audit),
        candidate_gates_csv: path_string(&paths.candidate_gates),
        trades_csv: path_string(&paths.trades),
        daily_csv: path_string(&paths.daily),
        summary_csv: path_string(&paths.summary),
        exit_reasons_csv: path_string(&paths.exit_reasons),
        fold_stability_csv: path_string(&paths.fold_stability),
        non_overlap_csv: path_string(&paths.non_overlap),
        parameter_sensitivity_csv: path_string(&paths.parameter_sensitivity),
        single_day_dependence_csv: path_string(&paths.single_day_dependence),
        failure_diagnostics_csv: path_string(&paths.failure_diagnostics),
        completion_json: path_string(&paths.completion),
        report_md: path_string(&config.report_md),
    })
}

#[derive(Debug, Clone, Default)]
#[allow(dead_code)]
struct EpisodeOutputs {
    candidate_fits: Vec<CandidateFitRow>,
    trades: Vec<TradeRow>,
    daily: Vec<DailyRow>,
    summary: Vec<SummaryRow>,
    exit_reasons: Vec<ExitReasonRow>,
    fold_stability: Vec<FoldStabilityRow>,
    non_overlap: Vec<NonOverlapRow>,
    parameter_sensitivity: Vec<ParameterSensitivityRow>,
    single_day_dependence: Vec<SingleDayDependenceRow>,
    failure_diagnostics: Vec<FailureDiagnosticRow>,
    configs: Vec<ConfigRow>,
}

fn validate_config(config: &V8Config) -> Result<()> {
    if config.notional_quote <= 0.0 {
        bail!("--notional-quote must be positive");
    }
    if config.fee_bps < 0.0 {
        bail!("--fee-bps must be non-negative");
    }
    if config.tp_bps.is_empty()
        || config.sl_bps.is_empty()
        || config.timeout_minutes.is_empty()
        || config.execution_models.is_empty()
    {
        bail!("tp/sl/timeout/execution grids must be non-empty");
    }
    let allowed: HashSet<&str> = DEFAULT_EXECUTION_MODELS.iter().copied().collect();
    for model in &config.execution_models {
        if !allowed.contains(model.as_str()) {
            bail!("unknown execution model: {model}");
        }
    }
    Ok(())
}

fn out_tag(config: &V8Config) -> String {
    if config.out_tag.is_empty() {
        config.run_tag.clone()
    } else {
        config.out_tag.clone()
    }
}

fn stop_after(config: &V8Config, step: &str) -> bool {
    config.stop_after.as_deref() == Some(step)
}

fn should_run_step(
    config: &V8Config,
    checkpoint: &Checkpoint,
    step: &str,
    outputs: &[&PathBuf],
) -> bool {
    if config.force {
        return true;
    }
    if !config.resume {
        return true;
    }
    let complete = checkpoint
        .steps
        .iter()
        .any(|state| state.name == step && state.status == "complete");
    !(complete && outputs.iter().all(|path| path.exists()))
}

fn load_checkpoint(path: &Path, config: &V8Config) -> Result<Checkpoint> {
    if config.resume && path.exists() {
        let file =
            File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
        let checkpoint: Checkpoint = serde_json::from_reader(file)
            .with_context(|| format!("failed to parse {}", path.display()))?;
        if checkpoint.run_tag == config.run_tag && checkpoint.out_tag == out_tag(config) {
            return Ok(checkpoint);
        }
    }
    Ok(Checkpoint {
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        guardrail: GUARDRAIL.to_string(),
        updated_at_utc: iso_now(),
        steps: Vec::new(),
    })
}

fn mark_step(
    checkpoint: &mut Checkpoint,
    path: &Path,
    step: &str,
    status: &str,
    detail: &str,
) -> Result<()> {
    let now = iso_now();
    if let Some(existing) = checkpoint.steps.iter_mut().find(|state| state.name == step) {
        existing.status = status.to_string();
        if existing.started_at_utc.is_empty() || status == "running" {
            existing.started_at_utc = now.clone();
        }
        existing.finished_at_utc = if status == "running" {
            String::new()
        } else {
            now.clone()
        };
        existing.detail = detail.to_string();
    } else {
        checkpoint.steps.push(StepState {
            name: step.to_string(),
            status: status.to_string(),
            started_at_utc: now.clone(),
            finished_at_utc: if status == "running" {
                String::new()
            } else {
                now.clone()
            },
            detail: detail.to_string(),
        });
    }
    checkpoint.updated_at_utc = now;
    write_json_atomic(path, checkpoint)
}

fn write_manifest(config: &V8Config, paths: &Paths, factor_defs: &[FactorDef]) -> Result<()> {
    let mut outputs = BTreeMap::new();
    outputs.insert("factor_panel".to_string(), path_string(&paths.factor_panel));
    outputs.insert(
        "factor_catalog".to_string(),
        path_string(&paths.factor_catalog),
    );
    outputs.insert("factor_audit".to_string(), path_string(&paths.factor_audit));
    outputs.insert(
        "candidate_gates".to_string(),
        path_string(&paths.candidate_gates),
    );
    outputs.insert("trades".to_string(), path_string(&paths.trades));
    outputs.insert("daily".to_string(), path_string(&paths.daily));
    outputs.insert("summary".to_string(), path_string(&paths.summary));
    outputs.insert("exit_reasons".to_string(), path_string(&paths.exit_reasons));
    outputs.insert(
        "fold_stability".to_string(),
        path_string(&paths.fold_stability),
    );
    outputs.insert("non_overlap".to_string(), path_string(&paths.non_overlap));
    outputs.insert(
        "parameter_sensitivity".to_string(),
        path_string(&paths.parameter_sensitivity),
    );
    outputs.insert(
        "single_day_dependence".to_string(),
        path_string(&paths.single_day_dependence),
    );
    outputs.insert(
        "failure_diagnostics".to_string(),
        path_string(&paths.failure_diagnostics),
    );
    outputs.insert("completion".to_string(), path_string(&paths.completion));
    outputs.insert("report".to_string(), path_string(&config.report_md));

    let manifest = Manifest {
        run_name: "bonk_v8_profit_factor_factory".to_string(),
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        generated_at_utc: iso_now(),
        guardrail: GUARDRAIL.to_string(),
        no_new_raw_data: true,
        inputs: vec![
            fingerprint(&paths.l2_state),
            fingerprint(&paths.price_context),
            fingerprint(&paths.covariance),
        ],
        outputs,
        steps: vec![
            "factor_panel".to_string(),
            "factor_audit".to_string(),
            "episode_backtest".to_string(),
            "report".to_string(),
        ],
        resume_checkpoint: path_string(&paths.checkpoint),
    };
    if !factor_defs.is_empty() {
        write_json_atomic(&paths.manifest, &manifest)?;
    }
    Ok(())
}

fn fingerprint(path: &Path) -> FileFingerprint {
    let Ok(meta) = fs::metadata(path) else {
        return FileFingerprint {
            path: path_string(path),
            exists: false,
            bytes: 0,
            modified_unix_seconds: None,
        };
    };
    let modified_unix_seconds = meta.modified().ok().and_then(system_time_seconds);
    FileFingerprint {
        path: path_string(path),
        exists: true,
        bytes: meta.len(),
        modified_unix_seconds,
    }
}

fn system_time_seconds(value: SystemTime) -> Option<u64> {
    value
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|duration| duration.as_secs())
}

fn summary_from_disk(
    config: &V8Config,
    paths: &Paths,
    factor_defs: &[FactorDef],
) -> Result<V8Summary> {
    let factor_rows = if paths.factor_panel.exists() {
        read_factor_panel(&paths.factor_panel, factor_defs)?.len()
    } else {
        0
    };
    Ok(V8Summary {
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        factor_rows,
        factor_count: factor_defs.len(),
        factor_audit_rows: csv_record_count(&paths.factor_audit).unwrap_or(0),
        candidate_fit_rows: csv_record_count(&paths.candidate_gates).unwrap_or(0),
        trades: csv_record_count(&paths.trades).unwrap_or(0),
        daily_rows: csv_record_count(&paths.daily).unwrap_or(0),
        summary_rows: csv_record_count(&paths.summary).unwrap_or(0),
        validation_passed: false,
        manifest_json: path_string(&paths.manifest),
        checkpoint_json: path_string(&paths.checkpoint),
        factor_panel_parquet: path_string(&paths.factor_panel),
        factor_catalog_csv: path_string(&paths.factor_catalog),
        factor_audit_csv: path_string(&paths.factor_audit),
        candidate_gates_csv: path_string(&paths.candidate_gates),
        trades_csv: path_string(&paths.trades),
        daily_csv: path_string(&paths.daily),
        summary_csv: path_string(&paths.summary),
        exit_reasons_csv: path_string(&paths.exit_reasons),
        fold_stability_csv: path_string(&paths.fold_stability),
        non_overlap_csv: path_string(&paths.non_overlap),
        parameter_sensitivity_csv: path_string(&paths.parameter_sensitivity),
        single_day_dependence_csv: path_string(&paths.single_day_dependence),
        failure_diagnostics_csv: path_string(&paths.failure_diagnostics),
        completion_json: path_string(&paths.completion),
        report_md: path_string(&config.report_md),
    })
}

fn csv_record_count(path: &Path) -> Result<usize> {
    if !path.exists() {
        return Ok(0);
    }
    let mut reader = csv::Reader::from_path(path)?;
    Ok(reader.records().count())
}

fn factor_defs() -> Vec<FactorDef> {
    vec![
        FactorDef {
            name: "price_mom_2m_bps",
            family: "price_momentum",
            description: "BONK Binance trailing 2m return",
        },
        FactorDef {
            name: "price_mom_5m_bps",
            family: "price_momentum",
            description: "BONK Binance trailing 5m return",
        },
        FactorDef {
            name: "price_mom_10m_bps",
            family: "price_momentum",
            description: "BONK Binance trailing 10m return",
        },
        FactorDef {
            name: "price_mom_20m_bps",
            family: "price_momentum",
            description: "BONK Binance trailing 20m return",
        },
        FactorDef {
            name: "price_mom_30m_bps",
            family: "price_momentum",
            description: "BONK Binance trailing 30m return",
        },
        FactorDef {
            name: "price_mom_60m_bps",
            family: "price_momentum",
            description: "BONK Binance trailing 60m return",
        },
        FactorDef {
            name: "price_mom_240m_bps",
            family: "price_momentum",
            description: "BONK Binance trailing 240m return",
        },
        FactorDef {
            name: "price_rev_2m_bps",
            family: "price_reversal",
            description: "Negative 2m return for reversal testing",
        },
        FactorDef {
            name: "price_rev_5m_bps",
            family: "price_reversal",
            description: "Negative 5m return for reversal testing",
        },
        FactorDef {
            name: "price_rev_10m_bps",
            family: "price_reversal",
            description: "Negative 10m return for reversal testing",
        },
        FactorDef {
            name: "price_rev_20m_bps",
            family: "price_reversal",
            description: "Negative 20m return for reversal testing",
        },
        FactorDef {
            name: "price_rev_30m_bps",
            family: "price_reversal",
            description: "Negative 30m return for reversal testing",
        },
        FactorDef {
            name: "price_rv_5m_bps",
            family: "volatility",
            description: "Trailing 5m realized volatility",
        },
        FactorDef {
            name: "price_rv_15m_bps",
            family: "volatility",
            description: "Trailing 15m realized volatility",
        },
        FactorDef {
            name: "price_rv_60m_bps",
            family: "volatility",
            description: "Trailing 60m realized volatility",
        },
        FactorDef {
            name: "price_rv_240m_bps",
            family: "volatility",
            description: "Trailing 240m realized volatility",
        },
        FactorDef {
            name: "vol_ratio_5m_60m",
            family: "volatility",
            description: "5m realized volatility divided by 60m volatility",
        },
        FactorDef {
            name: "vol_ratio_15m_240m",
            family: "volatility",
            description: "15m realized volatility divided by 240m volatility",
        },
        FactorDef {
            name: "vol_accel_15m_60m",
            family: "volatility",
            description: "15m minus scaled 60m volatility",
        },
        FactorDef {
            name: "range_pos_15m",
            family: "breakout_range",
            description: "Close position in trailing 15m range",
        },
        FactorDef {
            name: "range_pos_60m",
            family: "breakout_range",
            description: "Close position in trailing 60m range",
        },
        FactorDef {
            name: "range_pos_240m",
            family: "breakout_range",
            description: "Close position in trailing 240m range",
        },
        FactorDef {
            name: "range_width_15m_bps",
            family: "breakout_range",
            description: "Trailing 15m close range width",
        },
        FactorDef {
            name: "range_width_60m_bps",
            family: "breakout_range",
            description: "Trailing 60m close range width",
        },
        FactorDef {
            name: "range_width_240m_bps",
            family: "breakout_range",
            description: "Trailing 240m close range width",
        },
        FactorDef {
            name: "breakout_dist_15m_bps",
            family: "breakout_range",
            description: "Distance from trailing 15m high",
        },
        FactorDef {
            name: "breakout_dist_60m_bps",
            family: "breakout_range",
            description: "Distance from trailing 60m high",
        },
        FactorDef {
            name: "quote_volume_burst_15m",
            family: "volume_burst",
            description: "BONK quote-volume robust z score over 15m",
        },
        FactorDef {
            name: "quote_volume_burst_60m",
            family: "volume_burst",
            description: "BONK quote-volume robust z score over 60m",
        },
        FactorDef {
            name: "price_trade_count_burst_15m",
            family: "volume_burst",
            description: "BONK Binance trade-count robust z score over 15m",
        },
        FactorDef {
            name: "price_trade_count_burst_60m",
            family: "volume_burst",
            description: "BONK Binance trade-count robust z score over 60m",
        },
        FactorDef {
            name: "price_volume_confirm_5m",
            family: "volume_burst",
            description: "5m return times positive quote-volume burst",
        },
        FactorDef {
            name: "rel_btc_5m_bps",
            family: "relative_strength",
            description: "BONK 5m return minus BTC 5m return",
        },
        FactorDef {
            name: "rel_eth_5m_bps",
            family: "relative_strength",
            description: "BONK 5m return minus ETH 5m return",
        },
        FactorDef {
            name: "rel_sol_5m_bps",
            family: "relative_strength",
            description: "BONK 5m return minus SOL 5m return",
        },
        FactorDef {
            name: "rel_meme_5m_bps",
            family: "relative_strength",
            description: "BONK 5m return minus meme basket 5m return",
        },
        FactorDef {
            name: "rel_alt_5m_bps",
            family: "relative_strength",
            description: "BONK 5m return minus alt basket 5m return",
        },
        FactorDef {
            name: "rel_btc_15m_bps",
            family: "relative_strength",
            description: "BONK 15m return minus BTC 15m return",
        },
        FactorDef {
            name: "rel_sol_15m_bps",
            family: "relative_strength",
            description: "BONK 15m return minus SOL 15m return",
        },
        FactorDef {
            name: "rel_meme_15m_bps",
            family: "relative_strength",
            description: "BONK 15m return minus meme basket 15m return",
        },
        FactorDef {
            name: "rel_alt_15m_bps",
            family: "relative_strength",
            description: "BONK 15m return minus alt basket 15m return",
        },
        FactorDef {
            name: "rel_market_60m_bps",
            family: "relative_strength",
            description: "BONK 60m return minus BTC/ETH market basket",
        },
        FactorDef {
            name: "rel_meme_60m_bps",
            family: "relative_strength",
            description: "BONK 60m return minus meme basket",
        },
        FactorDef {
            name: "lead_btc_catchup_5m_bps",
            family: "lead_lag",
            description: "Prior BTC 5m move minus current BONK 5m move",
        },
        FactorDef {
            name: "lead_sol_catchup_5m_bps",
            family: "lead_lag",
            description: "Prior SOL 5m move minus current BONK 5m move",
        },
        FactorDef {
            name: "lead_meme_catchup_5m_bps",
            family: "lead_lag",
            description: "Prior meme 5m move minus current BONK 5m move",
        },
        FactorDef {
            name: "lead_market_catchup_15m_bps",
            family: "lead_lag",
            description: "Prior market 15m move minus current BONK 15m move",
        },
        FactorDef {
            name: "lead_sol_catchup_15m_bps",
            family: "lead_lag",
            description: "Prior SOL 15m move minus current BONK 15m move",
        },
        FactorDef {
            name: "lead_meme_catchup_15m_bps",
            family: "lead_lag",
            description: "Prior meme 15m move minus current BONK 15m move",
        },
        FactorDef {
            name: "corr_market_60m",
            family: "resonance",
            description: "BONK 60m correlation to market basket",
        },
        FactorDef {
            name: "corr_meme_60m",
            family: "resonance",
            description: "BONK 60m correlation to meme basket",
        },
        FactorDef {
            name: "corr_sol_60m",
            family: "resonance",
            description: "BONK 60m correlation to SOL",
        },
        FactorDef {
            name: "beta_market_60m",
            family: "resonance",
            description: "BONK 60m beta to market basket",
        },
        FactorDef {
            name: "beta_meme_60m",
            family: "resonance",
            description: "BONK 60m beta to meme basket",
        },
        FactorDef {
            name: "beta_sol_60m",
            family: "resonance",
            description: "BONK 60m beta to SOL",
        },
        FactorDef {
            name: "resonance_weighted_raw",
            family: "resonance",
            description: "Correlation-weighted current BONK/market/meme/SOL alignment",
        },
        FactorDef {
            name: "ask_withdraw_1m",
            family: "l2_delta",
            description: "Ask 25-level depth withdrawal over 1m",
        },
        FactorDef {
            name: "ask_withdraw_2m",
            family: "l2_delta",
            description: "Ask 25-level depth withdrawal over 2m",
        },
        FactorDef {
            name: "ask_withdraw_5m",
            family: "l2_delta",
            description: "Ask 25-level depth withdrawal over 5m",
        },
        FactorDef {
            name: "ask_withdraw_10m",
            family: "l2_delta",
            description: "Ask 25-level depth withdrawal over 10m",
        },
        FactorDef {
            name: "bid_replenish_1m",
            family: "l2_delta",
            description: "Bid 25-level depth replenish over 1m",
        },
        FactorDef {
            name: "bid_replenish_2m",
            family: "l2_delta",
            description: "Bid 25-level depth replenish over 2m",
        },
        FactorDef {
            name: "bid_replenish_5m",
            family: "l2_delta",
            description: "Bid 25-level depth replenish over 5m",
        },
        FactorDef {
            name: "bid_replenish_10m",
            family: "l2_delta",
            description: "Bid 25-level depth replenish over 10m",
        },
        FactorDef {
            name: "bid_withdraw_5m",
            family: "l2_delta",
            description: "Bid 25-level depth withdrawal over 5m",
        },
        FactorDef {
            name: "ask_replenish_5m",
            family: "l2_delta",
            description: "Ask 25-level depth replenish over 5m",
        },
        FactorDef {
            name: "spread_compression_1m_bps",
            family: "l2_delta",
            description: "Spread narrowing over 1m",
        },
        FactorDef {
            name: "spread_compression_5m_bps",
            family: "l2_delta",
            description: "Spread narrowing over 5m",
        },
        FactorDef {
            name: "spread_expansion_5m_bps",
            family: "l2_delta",
            description: "Spread widening over 5m",
        },
        FactorDef {
            name: "spread_bps_proxy",
            family: "l2_delta",
            description: "Current Bullish spread proxy in bps",
        },
        FactorDef {
            name: "microprice_impulse_1m_bps",
            family: "l2_delta",
            description: "Microprice offset impulse over 1m",
        },
        FactorDef {
            name: "microprice_impulse_5m_bps",
            family: "l2_delta",
            description: "Microprice offset impulse over 5m",
        },
        FactorDef {
            name: "wobi5_impulse_5m",
            family: "l2_delta",
            description: "WOBI5 impulse over 5m",
        },
        FactorDef {
            name: "wobi25_impulse_5m",
            family: "l2_delta",
            description: "WOBI25 impulse over 5m",
        },
        FactorDef {
            name: "depth_imbalance5_delta_5m",
            family: "l2_delta",
            description: "5-level depth imbalance delta over 5m",
        },
        FactorDef {
            name: "depth_imbalance25_delta_5m",
            family: "l2_delta",
            description: "25-level depth imbalance delta over 5m",
        },
        FactorDef {
            name: "top_depth_total_notional",
            family: "depth_shape",
            description: "Displayed top bid plus ask notional",
        },
        FactorDef {
            name: "depth_25_total_notional",
            family: "depth_shape",
            description: "25-level bid plus ask notional",
        },
        FactorDef {
            name: "top_vs_25_depth_shape",
            family: "depth_shape",
            description: "Top depth versus 25-level depth ratio",
        },
        FactorDef {
            name: "depth_shape_delta_5m",
            family: "depth_shape",
            description: "Top-vs-25 depth shape delta over 5m",
        },
        FactorDef {
            name: "depth_slope_bid",
            family: "depth_shape",
            description: "Bid depth outside top 5 as share of 25-level depth",
        },
        FactorDef {
            name: "depth_slope_ask",
            family: "depth_shape",
            description: "Ask depth outside top 5 as share of 25-level depth",
        },
        FactorDef {
            name: "depth_fragility",
            family: "depth_shape",
            description: "Spread divided by square-root 25-level depth",
        },
        FactorDef {
            name: "l2_mom_5m_bps",
            family: "liquidity_adjusted",
            description: "Bullish mid trailing 5m return",
        },
        FactorDef {
            name: "liquidity_adjusted_momentum_5m",
            family: "liquidity_adjusted",
            description: "5m L2 momentum scaled by depth and spread",
        },
        FactorDef {
            name: "cost_adjusted_signal_strength_5m",
            family: "liquidity_adjusted",
            description: "5m L2 momentum net of spread proxy and fee",
        },
        FactorDef {
            name: "inverse_spread_depth",
            family: "liquidity_adjusted",
            description: "Depth divided by spread proxy",
        },
        FactorDef {
            name: "l2_trade_notional_burst_15m",
            family: "flow_burst",
            description: "Bullish trade-notional burst over 15m",
        },
        FactorDef {
            name: "l2_trade_notional_burst_60m",
            family: "flow_burst",
            description: "Bullish trade-notional burst over 60m",
        },
        FactorDef {
            name: "l2_trade_count_burst_15m",
            family: "flow_burst",
            description: "Bullish trade-count burst over 15m",
        },
        FactorDef {
            name: "trade_flow_imbalance",
            family: "flow_burst",
            description: "Exchange-reported flow imbalance",
        },
        FactorDef {
            name: "reported_buy_share",
            family: "flow_burst",
            description: "Exchange-reported buy share",
        },
        FactorDef {
            name: "flow_imbalance_delta_5m",
            family: "flow_burst",
            description: "Exchange-reported flow imbalance delta over 5m",
        },
        FactorDef {
            name: "cross_venue_basis_bps",
            family: "basis_disagreement",
            description: "USDC/USDT mid basis",
        },
        FactorDef {
            name: "cross_venue_basis_abs_bps",
            family: "basis_disagreement",
            description: "Absolute USDC/USDT mid basis",
        },
        FactorDef {
            name: "cross_venue_spread_diff_bps",
            family: "basis_disagreement",
            description: "USDC/USDT spread difference",
        },
        FactorDef {
            name: "cross_venue_activity_ratio",
            family: "basis_disagreement",
            description: "Symbol activity versus other quote venue",
        },
        FactorDef {
            name: "cross_venue_microprice_disagreement_bps",
            family: "basis_disagreement",
            description: "USDC/USDT microprice disagreement",
        },
        FactorDef {
            name: "cross_venue_microprice_abs_bps",
            family: "basis_disagreement",
            description: "Absolute microprice disagreement",
        },
        FactorDef {
            name: "bullish_avg_corr_60m",
            family: "common_mode",
            description: "Bullish basket average 60m correlation",
        },
        FactorDef {
            name: "bullish_first_eigen_share_60m",
            family: "common_mode",
            description: "Bullish basket first eigen share",
        },
        FactorDef {
            name: "bullish_cross_abs_ret_mean_bps",
            family: "common_mode",
            description: "Bullish basket cross-sectional absolute return mean",
        },
        FactorDef {
            name: "bullish_common_mode_score",
            family: "common_mode",
            description: "Composite common-mode crowding score",
        },
        FactorDef {
            name: "price_positive_age_1m",
            family: "event_sequence",
            description: "Consecutive positive BONK price-return age in minutes",
        },
        FactorDef {
            name: "l2_positive_age_1m",
            family: "event_sequence",
            description: "Consecutive positive Bullish L2 return age in minutes",
        },
        FactorDef {
            name: "ask_withdraw_persistence_5m",
            family: "event_sequence",
            description: "Count of ask-withdraw transition minutes in trailing 5m",
        },
        FactorDef {
            name: "bid_replenish_persistence_5m",
            family: "event_sequence",
            description: "Count of bid-replenish transition minutes in trailing 5m",
        },
        FactorDef {
            name: "spread_compression_persistence_5m",
            family: "event_sequence",
            description: "Count of spread-compression transition minutes in trailing 5m",
        },
        FactorDef {
            name: "l2_impulse_decay_5m",
            family: "event_sequence",
            description: "Exponentially decayed recent L2 return impulse",
        },
        FactorDef {
            name: "l2_transition_count_10m",
            family: "event_sequence",
            description: "Count of L2 return sign transitions in trailing 10m",
        },
        FactorDef {
            name: "l2_impulse_score_raw",
            family: "interaction",
            description: "Book impulse raw combination",
        },
        FactorDef {
            name: "book_flow_alignment",
            family: "interaction",
            description: "Book impulse times flow imbalance",
        },
        FactorDef {
            name: "price_book_alignment_5m",
            family: "interaction",
            description: "Price momentum times book impulse",
        },
        FactorDef {
            name: "context_price_alignment",
            family: "interaction",
            description: "Market catch-up context times price momentum",
        },
        FactorDef {
            name: "context_book_alignment",
            family: "interaction",
            description: "Market resonance times book impulse",
        },
        FactorDef {
            name: "price_x_book_x_flow",
            family: "interaction",
            description: "Triple interaction across price, book, and flow",
        },
        FactorDef {
            name: "cost_x_context_signal",
            family: "interaction",
            description: "Context signal adjusted for cost proxy",
        },
        FactorDef {
            name: "market_resonance_weighted_impulse_raw",
            family: "weighted_combo_seed",
            description: "Seed for train-fit market-resonance weighted impulse",
        },
        FactorDef {
            name: "liquidity_adjusted_relative_momentum_raw",
            family: "weighted_combo_seed",
            description: "Seed for train-fit liquidity-adjusted relative momentum",
        },
        FactorDef {
            name: "spread_cost_adjusted_book_impulse_raw",
            family: "weighted_combo_seed",
            description: "Seed for train-fit spread-cost-adjusted book impulse",
        },
        FactorDef {
            name: "regime_conditioned_factor_mixture_raw",
            family: "weighted_combo_seed",
            description: "Seed for train-fit regime-conditioned factor mixture",
        },
    ]
}

fn factor_catalog_rows(defs: &[FactorDef]) -> Vec<FactorCatalogRow> {
    defs.iter()
        .map(|def| FactorCatalogRow {
            factor_name: def.name.to_string(),
            family: def.family.to_string(),
            description: def.description.to_string(),
            trailing_only: true,
            train_fit_required: matches!(def.family, "weighted_combo_seed" | "interaction"),
        })
        .collect()
}

fn factor_index(defs: &[FactorDef]) -> HashMap<&'static str, usize> {
    defs.iter()
        .enumerate()
        .map(|(idx, def)| (def.name, idx))
        .collect()
}

fn candidate_specs() -> Vec<CandidateSpec> {
    vec![
        CandidateSpec {
            candidate_id: "price_momentum_breakout_volume",
            candidate_group: "price_classic",
            candidate_name: "momentum + breakout + volume",
            description: "Classic momentum/breakout with volume confirmation.",
            conditions: vec![
                cond_high("price_mom_10m_bps", 0.80),
                cond_high("range_pos_60m", 0.75),
                cond_high("quote_volume_burst_60m", 0.75),
            ],
        },
        CandidateSpec {
            candidate_id: "price_reversal_spread_compress",
            candidate_group: "price_classic",
            candidate_name: "reversal + spread compression",
            description: "Short reversal after negative price pressure with improving spread.",
            conditions: vec![
                cond_high("price_rev_20m_bps", 0.80),
                cond_low("range_pos_60m", 0.25),
                cond_high("spread_compression_5m_bps", 0.75),
            ],
        },
        CandidateSpec {
            candidate_id: "vol_compression_breakout_depth",
            candidate_group: "price_classic",
            candidate_name: "vol compression + breakout + depth",
            description: "Quiet-to-breakout state gated by displayed depth.",
            conditions: vec![
                cond_low("vol_ratio_15m_240m", 0.25),
                cond_high("breakout_dist_60m_bps", 0.75),
                cond_high("top_depth_total_notional", 0.75),
            ],
        },
        CandidateSpec {
            candidate_id: "vol_expansion_trade_burst",
            candidate_group: "price_flow",
            candidate_name: "vol expansion + trade burst",
            description: "Fresh activity expansion with reported flow support.",
            conditions: vec![
                cond_high("vol_accel_15m_60m", 0.75),
                cond_high("l2_trade_notional_burst_15m", 0.80),
                cond_high("trade_flow_imbalance", 0.70),
            ],
        },
        CandidateSpec {
            candidate_id: "meme_sol_catchup_l2_impulse",
            candidate_group: "lead_lag",
            candidate_name: "meme/SOL catch-up + L2 impulse",
            description: "Market lead-lag pressure with local book confirmation.",
            conditions: vec![
                cond_high("lead_meme_catchup_15m_bps", 0.75),
                cond_high("lead_sol_catchup_15m_bps", 0.70),
                cond_high("l2_impulse_score_raw", 0.80),
            ],
        },
        CandidateSpec {
            candidate_id: "btc_market_lead_book_support",
            candidate_group: "lead_lag",
            candidate_name: "BTC/market lead + book support",
            description: "BTC/market lead-lag pressure with bid replenish.",
            conditions: vec![
                cond_high("lead_market_catchup_15m_bps", 0.75),
                cond_high("lead_btc_catchup_5m_bps", 0.70),
                cond_high("bid_replenish_5m", 0.75),
            ],
        },
        CandidateSpec {
            candidate_id: "ask_withdraw_bid_replenish",
            candidate_group: "book_transition",
            candidate_name: "ask withdrawal + bid replenish",
            description: "Ask liquidity pulls while bid side replenishes.",
            conditions: vec![
                cond_high("ask_withdraw_5m", 0.80),
                cond_high("bid_replenish_5m", 0.75),
                cond_high("spread_compression_5m_bps", 0.65),
            ],
        },
        CandidateSpec {
            candidate_id: "micro_wobi_depth_impulse",
            candidate_group: "book_transition",
            candidate_name: "microprice + WOBI + imbalance impulse",
            description: "Microprice, WOBI, and depth imbalance transition.",
            conditions: vec![
                cond_high("microprice_impulse_5m_bps", 0.75),
                cond_high("wobi5_impulse_5m", 0.75),
                cond_high("depth_imbalance25_delta_5m", 0.70),
            ],
        },
        CandidateSpec {
            candidate_id: "event_sequence_persistence_decay",
            candidate_group: "event_sequence",
            candidate_name: "event persistence + impulse decay",
            description: "Persistent book transition sequence with decayed L2 impulse.",
            conditions: vec![
                cond_high("l2_positive_age_1m", 0.75),
                cond_high("bid_replenish_persistence_5m", 0.70),
                cond_high("l2_impulse_decay_5m", 0.75),
            ],
        },
        CandidateSpec {
            candidate_id: "spread_cost_adjusted_book_impulse",
            candidate_group: "weighted_combo",
            candidate_name: "spread-cost-adjusted book impulse",
            description: "Train-fit weighted book impulse net of spread/cost.",
            conditions: vec![
                cond_weighted_high("spread_cost_adjusted_book_impulse", 0.88),
                cond_low("spread_bps_proxy", 0.45),
            ],
        },
        CandidateSpec {
            candidate_id: "liquidity_adjusted_relative_momentum",
            candidate_group: "weighted_combo",
            candidate_name: "liquidity-adjusted relative momentum",
            description: "Train-fit weighted relative momentum with depth support.",
            conditions: vec![
                cond_weighted_high("liquidity_adjusted_relative_momentum", 0.88),
                cond_high("top_depth_total_notional", 0.60),
            ],
        },
        CandidateSpec {
            candidate_id: "market_resonance_weighted_impulse",
            candidate_group: "weighted_combo",
            candidate_name: "market-resonance weighted impulse",
            description: "Train-fit weighted context resonance plus local impulse.",
            conditions: vec![
                cond_weighted_high("market_resonance_weighted_impulse", 0.88),
                cond_high("l2_impulse_score_raw", 0.70),
            ],
        },
        CandidateSpec {
            candidate_id: "regime_conditioned_factor_mixture",
            candidate_group: "weighted_combo",
            candidate_name: "regime-conditioned mixture",
            description: "Train-fit mixture gated by low common-mode crowding and lower RV.",
            conditions: vec![
                cond_weighted_high("regime_conditioned_factor_mixture", 0.88),
                cond_low("bullish_common_mode_score", 0.45),
                cond_low("price_rv_60m_bps", 0.55),
            ],
        },
        CandidateSpec {
            candidate_id: "basis_microprice_disagreement",
            candidate_group: "basis_disagreement",
            candidate_name: "basis + microprice disagreement",
            description: "USDC/USDT disagreement with local L2 impulse.",
            conditions: vec![
                cond_high_abs("cross_venue_basis_bps", 0.80),
                cond_high_abs("cross_venue_microprice_disagreement_bps", 0.80),
                cond_high("l2_impulse_score_raw", 0.70),
            ],
        },
        CandidateSpec {
            candidate_id: "common_mode_dispersion_break",
            candidate_group: "common_mode",
            candidate_name: "basket dispersion break",
            description: "Bullish basket dispersion with BONK relative strength.",
            conditions: vec![
                cond_high("bullish_cross_abs_ret_mean_bps", 0.75),
                cond_high("rel_meme_15m_bps", 0.65),
                cond_high("price_book_alignment_5m", 0.75),
            ],
        },
        CandidateSpec {
            candidate_id: "price_book_flow_triple",
            candidate_group: "nonlinear_interaction",
            candidate_name: "price x book x flow",
            description: "Nonlinear price, book, and flow interaction.",
            conditions: vec![
                cond_high("price_x_book_x_flow", 0.88),
                cond_high("cost_adjusted_signal_strength_5m", 0.65),
            ],
        },
        CandidateSpec {
            candidate_id: "context_cost_adjusted_signal",
            candidate_group: "nonlinear_interaction",
            candidate_name: "context x cost-adjusted signal",
            description: "Context alignment net of cost proxy.",
            conditions: vec![
                cond_high("cost_x_context_signal", 0.86),
                cond_high("inverse_spread_depth", 0.55),
            ],
        },
        CandidateSpec {
            candidate_id: "distilled_rv_low_market_beta",
            candidate_group: "exploratory_distilled",
            candidate_name: "distilled RV + low market beta",
            description: "Simple Rust gate promoted from the V8 symbolic scan: high realized volatility with low market beta.",
            conditions: vec![
                cond_high("price_rv_60m_bps", 0.80),
                cond_low("beta_market_60m", 0.20),
            ],
        },
        CandidateSpec {
            candidate_id: "distilled_rv240_low_market_beta",
            candidate_group: "exploratory_distilled",
            candidate_name: "distilled 240m RV + low market beta",
            description: "Simple Rust gate promoted from the V8 symbolic scan: high long-window realized volatility with low market beta.",
            conditions: vec![
                cond_high("price_rv_240m_bps", 0.80),
                cond_low("beta_market_60m", 0.20),
            ],
        },
        CandidateSpec {
            candidate_id: "distilled_dispersion_low_market_beta",
            candidate_group: "exploratory_distilled",
            candidate_name: "distilled dispersion + low market beta",
            description: "Simple Rust gate promoted from the V8 symbolic scan: Bullish basket dispersion while BONK beta is low.",
            conditions: vec![
                cond_high("bullish_cross_abs_ret_mean_bps", 0.80),
                cond_low("beta_market_60m", 0.20),
            ],
        },
        CandidateSpec {
            candidate_id: "distilled_momentum_low_market_beta",
            candidate_group: "exploratory_distilled",
            candidate_name: "distilled momentum + low market beta",
            description: "Simple Rust gate promoted from the V8 symbolic scan: high 240m BONK momentum with low market beta.",
            conditions: vec![
                cond_high("price_mom_240m_bps", 0.80),
                cond_low("beta_market_60m", 0.20),
            ],
        },
    ]
}

fn cond_high(factor: &'static str, quantile: f64) -> ConditionSpec {
    ConditionSpec::Factor {
        factor,
        side: ConditionSide::High,
        quantile,
    }
}

fn cond_low(factor: &'static str, quantile: f64) -> ConditionSpec {
    ConditionSpec::Factor {
        factor,
        side: ConditionSide::Low,
        quantile,
    }
}

fn cond_high_abs(factor: &'static str, quantile: f64) -> ConditionSpec {
    ConditionSpec::Factor {
        factor,
        side: ConditionSide::HighAbs,
        quantile,
    }
}

fn cond_weighted_high(score_id: &'static str, quantile: f64) -> ConditionSpec {
    ConditionSpec::Weighted {
        score_id,
        side: ConditionSide::High,
        quantile,
    }
}

fn weighted_score_factors(score_id: &str) -> Result<Vec<&'static str>> {
    match score_id {
        "market_resonance_weighted_impulse" => Ok(vec![
            "resonance_weighted_raw",
            "lead_meme_catchup_15m_bps",
            "lead_sol_catchup_15m_bps",
            "l2_impulse_score_raw",
            "microprice_impulse_5m_bps",
        ]),
        "liquidity_adjusted_relative_momentum" => Ok(vec![
            "rel_meme_15m_bps",
            "rel_sol_15m_bps",
            "price_mom_10m_bps",
            "liquidity_adjusted_momentum_5m",
            "inverse_spread_depth",
        ]),
        "spread_cost_adjusted_book_impulse" => Ok(vec![
            "ask_withdraw_5m",
            "bid_replenish_5m",
            "spread_compression_5m_bps",
            "microprice_impulse_5m_bps",
            "wobi5_impulse_5m",
            "cost_adjusted_signal_strength_5m",
        ]),
        "regime_conditioned_factor_mixture" => Ok(vec![
            "price_mom_10m_bps",
            "lead_meme_catchup_15m_bps",
            "l2_impulse_score_raw",
            "l2_trade_notional_burst_15m",
            "spread_cost_adjusted_book_impulse_raw",
            "regime_conditioned_factor_mixture_raw",
        ]),
        other => Err(anyhow!("unknown weighted score id: {other}")),
    }
}

fn build_factor_panel(
    config: &V8Config,
    paths: &Paths,
    defs: &[FactorDef],
) -> Result<Vec<FactorRow>> {
    eprintln!("[bonk_v8] read L2 {}", paths.l2_state.display());
    let l2_rows = read_l2_rows(&paths.l2_state, &config.run_tag)?;
    eprintln!(
        "[bonk_v8] read price context {}",
        paths.price_context.display()
    );
    let price_rows = read_price_rows(&paths.price_context)?;
    eprintln!("[bonk_v8] read covariance {}", paths.covariance.display());
    let cov_rows = read_cov_rows(&paths.covariance)?;

    let price = PriceBook::new(price_rows);
    let cov_by_ts = cov_rows
        .into_iter()
        .map(|row| (row.timestamp_us, row))
        .collect::<HashMap<_, _>>();
    let mut by_symbol: BTreeMap<String, Vec<L2RawRow>> = BTreeMap::new();
    for row in l2_rows {
        by_symbol.entry(row.symbol.clone()).or_default().push(row);
    }
    for rows in by_symbol.values_mut() {
        rows.sort_by_key(|row| row.timestamp_us);
    }
    let other_by_key = by_symbol
        .iter()
        .flat_map(|(symbol, rows)| {
            rows.iter()
                .map(move |row| ((symbol.clone(), row.timestamp_us), row.clone()))
        })
        .collect::<HashMap<_, _>>();

    let index = factor_index(defs);
    let mut out = Vec::new();
    for (symbol, rows) in &by_symbol {
        if !DEFAULT_SYMBOLS.contains(&symbol.as_str()) {
            continue;
        }
        for idx in 0..rows.len() {
            let row = &rows[idx];
            let other_symbol = if symbol == "BONK1MUSDC" {
                "BONK1MUSDT"
            } else {
                "BONK1MUSDC"
            };
            let other = other_by_key.get(&(other_symbol.to_string(), row.timestamp_us));
            let cov = cov_by_ts.get(&row.timestamp_us);
            let values = compute_factor_values(row, idx, rows, other, &price, cov, defs, &index);
            out.push(FactorRow {
                run_tag: config.run_tag.clone(),
                timestamp_utc: row.timestamp_utc.clone(),
                timestamp_us: row.timestamp_us,
                symbol: symbol.clone(),
                mid_open: row.mid_open,
                mid_high: row.mid_high,
                mid_low: row.mid_low,
                mid_close: row.mid_close,
                spread_bps: row.spread_bps_median,
                depth_bid_25: row.depth_bid_25,
                depth_ask_25: row.depth_ask_25,
                factors: values,
            });
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
    });
    Ok(out)
}

fn compute_factor_values(
    row: &L2RawRow,
    idx: usize,
    rows: &[L2RawRow],
    other: Option<&L2RawRow>,
    price: &PriceBook,
    cov: Option<&CovRawRow>,
    defs: &[FactorDef],
    index: &HashMap<&'static str, usize>,
) -> Vec<Option<f64>> {
    let mut values: HashMap<&'static str, Option<f64>> = HashMap::new();
    let ts = row.timestamp_us;
    let put = |values: &mut HashMap<&'static str, Option<f64>>,
               name: &'static str,
               value: Option<f64>| {
        values.insert(name, value.and_then(finite));
    };

    for &window in &[2usize, 5, 10, 20, 30, 60, 240] {
        let mom = price.sum_ret("BONKUSDT", ts, window);
        let name = match window {
            2 => "price_mom_2m_bps",
            5 => "price_mom_5m_bps",
            10 => "price_mom_10m_bps",
            20 => "price_mom_20m_bps",
            30 => "price_mom_30m_bps",
            60 => "price_mom_60m_bps",
            240 => "price_mom_240m_bps",
            _ => unreachable!(),
        };
        put(&mut values, name, mom);
        if window <= 30 {
            let rev_name = match window {
                2 => "price_rev_2m_bps",
                5 => "price_rev_5m_bps",
                10 => "price_rev_10m_bps",
                20 => "price_rev_20m_bps",
                30 => "price_rev_30m_bps",
                _ => unreachable!(),
            };
            put(&mut values, rev_name, mom.map(|value| -value));
        }
    }

    let rv5 = price.rv("BONKUSDT", ts, 5);
    let rv15 = price
        .rv("BONKUSDT", ts, 15)
        .or_else(|| price.bonk_row(ts).and_then(|r| r.rv_15m_bps));
    let rv60 = price
        .rv("BONKUSDT", ts, 60)
        .or_else(|| price.bonk_row(ts).and_then(|r| r.rv_1h_bps));
    let rv240 = price
        .rv("BONKUSDT", ts, 240)
        .or_else(|| price.bonk_row(ts).and_then(|r| r.rv_4h_bps));
    put(&mut values, "price_rv_5m_bps", rv5);
    put(&mut values, "price_rv_15m_bps", rv15);
    put(&mut values, "price_rv_60m_bps", rv60);
    put(&mut values, "price_rv_240m_bps", rv240);
    put(&mut values, "vol_ratio_5m_60m", ratio_opt(rv5, rv60));
    put(&mut values, "vol_ratio_15m_240m", ratio_opt(rv15, rv240));
    put(
        &mut values,
        "vol_accel_15m_60m",
        rv15.zip(rv60)
            .and_then(|(a, b)| finite(a - b * (15.0f64 / 60.0).sqrt())),
    );

    for &window in &[15usize, 60, 240] {
        let range = price.range_stats("BONKUSDT", ts, window);
        let (pos_name, width_name, dist_name) = match window {
            15 => (
                "range_pos_15m",
                "range_width_15m_bps",
                "breakout_dist_15m_bps",
            ),
            60 => (
                "range_pos_60m",
                "range_width_60m_bps",
                "breakout_dist_60m_bps",
            ),
            240 => (
                "range_pos_240m",
                "range_width_240m_bps",
                "breakout_dist_60m_bps",
            ),
            _ => unreachable!(),
        };
        put(&mut values, pos_name, range.and_then(|r| r.position));
        put(&mut values, width_name, range.and_then(|r| r.width_bps));
        if window != 240 {
            put(
                &mut values,
                dist_name,
                range.and_then(|r| r.dist_from_high_bps),
            );
        }
    }

    put(
        &mut values,
        "quote_volume_burst_15m",
        price.robust_z("BONKUSDT", ts, 15, PriceField::QuoteVolume),
    );
    put(
        &mut values,
        "quote_volume_burst_60m",
        price.robust_z("BONKUSDT", ts, 60, PriceField::QuoteVolume),
    );
    put(
        &mut values,
        "price_trade_count_burst_15m",
        price.robust_z("BONKUSDT", ts, 15, PriceField::TradeCount),
    );
    put(
        &mut values,
        "price_trade_count_burst_60m",
        price.robust_z("BONKUSDT", ts, 60, PriceField::TradeCount),
    );
    let price_volume_confirm_5m = get_factor_value(&values, "price_mom_5m_bps")
        .zip(get_factor_value(&values, "quote_volume_burst_15m"))
        .and_then(|(ret, burst)| finite(ret * burst.max(0.0)));
    put(
        &mut values,
        "price_volume_confirm_5m",
        price_volume_confirm_5m,
    );

    for &window in &[5usize, 15, 60] {
        let bonk = price.sum_ret("BONKUSDT", ts, window);
        if window <= 15 {
            put(
                &mut values,
                match window {
                    5 => "rel_btc_5m_bps",
                    15 => "rel_btc_15m_bps",
                    _ => unreachable!(),
                },
                diff_opt(bonk, price.sum_ret("BTCUSDT", ts, window)),
            );
            if window == 5 {
                put(
                    &mut values,
                    "rel_eth_5m_bps",
                    diff_opt(bonk, price.sum_ret("ETHUSDT", ts, window)),
                );
                put(
                    &mut values,
                    "rel_sol_5m_bps",
                    diff_opt(bonk, price.sum_ret("SOLUSDT", ts, window)),
                );
                put(
                    &mut values,
                    "rel_meme_5m_bps",
                    diff_opt(bonk, price.basket_ret(MEME_SYMBOLS, ts, window)),
                );
                put(
                    &mut values,
                    "rel_alt_5m_bps",
                    diff_opt(bonk, price.basket_ret(ALT_SYMBOLS, ts, window)),
                );
            } else {
                put(
                    &mut values,
                    "rel_sol_15m_bps",
                    diff_opt(bonk, price.sum_ret("SOLUSDT", ts, window)),
                );
                put(
                    &mut values,
                    "rel_meme_15m_bps",
                    diff_opt(bonk, price.basket_ret(MEME_SYMBOLS, ts, window)),
                );
                put(
                    &mut values,
                    "rel_alt_15m_bps",
                    diff_opt(bonk, price.basket_ret(ALT_SYMBOLS, ts, window)),
                );
            }
        } else {
            put(
                &mut values,
                "rel_market_60m_bps",
                diff_opt(bonk, price.basket_ret(MARKET_SYMBOLS, ts, window)),
            );
            put(
                &mut values,
                "rel_meme_60m_bps",
                diff_opt(bonk, price.basket_ret(MEME_SYMBOLS, ts, window)),
            );
        }
    }

    for &window in &[5usize, 15] {
        let bonk_current = price.sum_ret("BONKUSDT", ts, window);
        let btc_prior = price.prior_sum_ret("BTCUSDT", ts, window);
        let sol_prior = price.prior_sum_ret("SOLUSDT", ts, window);
        let meme_prior = price.prior_basket_ret(MEME_SYMBOLS, ts, window);
        if window == 5 {
            put(
                &mut values,
                "lead_btc_catchup_5m_bps",
                diff_opt(btc_prior, bonk_current),
            );
            put(
                &mut values,
                "lead_sol_catchup_5m_bps",
                diff_opt(sol_prior, bonk_current),
            );
            put(
                &mut values,
                "lead_meme_catchup_5m_bps",
                diff_opt(meme_prior, bonk_current),
            );
        } else {
            put(
                &mut values,
                "lead_market_catchup_15m_bps",
                diff_opt(
                    price.prior_basket_ret(MARKET_SYMBOLS, ts, window),
                    bonk_current,
                ),
            );
            put(
                &mut values,
                "lead_sol_catchup_15m_bps",
                diff_opt(sol_prior, bonk_current),
            );
            put(
                &mut values,
                "lead_meme_catchup_15m_bps",
                diff_opt(meme_prior, bonk_current),
            );
        }
    }

    if let Some(bonk) = price.bonk_row(ts) {
        put(&mut values, "corr_market_60m", bonk.bonk_corr_market_60m);
        put(&mut values, "corr_meme_60m", bonk.bonk_corr_meme_60m);
        put(&mut values, "corr_sol_60m", bonk.bonk_corr_sol_60m);
        put(&mut values, "beta_market_60m", bonk.bonk_beta_market_60m);
        put(&mut values, "beta_meme_60m", bonk.bonk_beta_meme_60m);
        put(&mut values, "beta_sol_60m", bonk.bonk_beta_sol_60m);
        let resonance = weighted_mean(&[
            signed_corr_component(
                price.sum_ret("BONKUSDT", ts, 5),
                price.basket_ret(MARKET_SYMBOLS, ts, 5),
                bonk.bonk_corr_market_60m,
            ),
            signed_corr_component(
                price.sum_ret("BONKUSDT", ts, 5),
                price.basket_ret(MEME_SYMBOLS, ts, 5),
                bonk.bonk_corr_meme_60m,
            ),
            signed_corr_component(
                price.sum_ret("BONKUSDT", ts, 5),
                price.sum_ret("SOLUSDT", ts, 5),
                bonk.bonk_corr_sol_60m,
            ),
        ]);
        put(&mut values, "resonance_weighted_raw", resonance);
    }

    for &k in &[1usize, 2, 5, 10] {
        let prev = prev_l2(rows, idx, k);
        if let Some(prev) = prev {
            let ask_withdraw = withdraw(prev.depth_ask_25, row.depth_ask_25);
            let bid_replenish = replenish(prev.depth_bid_25, row.depth_bid_25);
            let (ask_name, bid_name) = match k {
                1 => ("ask_withdraw_1m", "bid_replenish_1m"),
                2 => ("ask_withdraw_2m", "bid_replenish_2m"),
                5 => ("ask_withdraw_5m", "bid_replenish_5m"),
                10 => ("ask_withdraw_10m", "bid_replenish_10m"),
                _ => unreachable!(),
            };
            put(&mut values, ask_name, ask_withdraw);
            put(&mut values, bid_name, bid_replenish);
            if k == 5 {
                put(
                    &mut values,
                    "bid_withdraw_5m",
                    withdraw(prev.depth_bid_25, row.depth_bid_25),
                );
                put(
                    &mut values,
                    "ask_replenish_5m",
                    replenish(prev.depth_ask_25, row.depth_ask_25),
                );
            }
        }
    }

    let prev1 = prev_l2(rows, idx, 1);
    let prev5 = prev_l2(rows, idx, 5);
    put(
        &mut values,
        "spread_compression_1m_bps",
        prev1.and_then(|prev| compression(prev.spread_bps_median, row.spread_bps_median)),
    );
    put(
        &mut values,
        "spread_compression_5m_bps",
        prev5.and_then(|prev| compression(prev.spread_bps_median, row.spread_bps_median)),
    );
    put(
        &mut values,
        "spread_expansion_5m_bps",
        prev5.and_then(|prev| expansion(prev.spread_bps_median, row.spread_bps_median)),
    );
    put(&mut values, "spread_bps_proxy", row.spread_bps_median);
    put(
        &mut values,
        "microprice_impulse_1m_bps",
        prev1.and_then(|prev| diff_opt(row.microprice_offset, prev.microprice_offset)),
    );
    put(
        &mut values,
        "microprice_impulse_5m_bps",
        prev5.and_then(|prev| diff_opt(row.microprice_offset, prev.microprice_offset)),
    );
    put(
        &mut values,
        "wobi5_impulse_5m",
        prev5.and_then(|prev| diff_opt(row.wobi5, prev.wobi5)),
    );
    put(
        &mut values,
        "wobi25_impulse_5m",
        prev5.and_then(|prev| diff_opt(row.wobi25, prev.wobi25)),
    );
    put(
        &mut values,
        "depth_imbalance5_delta_5m",
        prev5.and_then(|prev| diff_opt(row.depth_imbalance_5, prev.depth_imbalance_5)),
    );
    put(
        &mut values,
        "depth_imbalance25_delta_5m",
        prev5.and_then(|prev| diff_opt(row.depth_imbalance_25, prev.depth_imbalance_25)),
    );

    let top_depth_total = add_opt(row.top_depth_bid, row.top_depth_ask);
    let depth25_total = add_opt(row.depth_bid_25, row.depth_ask_25);
    let depth5_total = add_opt(row.depth_bid_5, row.depth_ask_5);
    let shape = ratio_opt(depth5_total, depth25_total);
    put(&mut values, "top_depth_total_notional", top_depth_total);
    put(&mut values, "depth_25_total_notional", depth25_total);
    put(&mut values, "top_vs_25_depth_shape", shape);
    put(
        &mut values,
        "depth_shape_delta_5m",
        prev5.and_then(|prev| {
            let prev_shape = ratio_opt(
                add_opt(prev.depth_bid_5, prev.depth_ask_5),
                add_opt(prev.depth_bid_25, prev.depth_ask_25),
            );
            diff_opt(shape, prev_shape)
        }),
    );
    put(
        &mut values,
        "depth_slope_bid",
        slope(row.depth_bid_5, row.depth_bid_25),
    );
    put(
        &mut values,
        "depth_slope_ask",
        slope(row.depth_ask_5, row.depth_ask_25),
    );
    put(
        &mut values,
        "depth_fragility",
        row.spread_bps_median
            .zip(depth25_total)
            .and_then(|(spread, depth)| (depth > 0.0).then(|| spread / depth.sqrt()))
            .and_then(finite),
    );

    let l2_mom_5 = prev5.and_then(|prev| ret_bps(row.mid_close, prev.mid_close));
    put(&mut values, "l2_mom_5m_bps", l2_mom_5);
    put(
        &mut values,
        "liquidity_adjusted_momentum_5m",
        l2_mom_5
            .zip(depth25_total)
            .zip(row.spread_bps_median)
            .and_then(|((mom, depth), spread)| {
                finite(mom * (1.0 + depth).ln() / (1.0 + spread.max(0.0)))
            }),
    );
    put(
        &mut values,
        "cost_adjusted_signal_strength_5m",
        l2_mom_5
            .zip(row.spread_bps_median)
            .and_then(|(mom, spread)| finite(mom - spread.max(0.0) - DEFAULT_FEE_BPS)),
    );
    put(
        &mut values,
        "inverse_spread_depth",
        depth25_total
            .zip(row.spread_bps_median)
            .and_then(|(depth, spread)| finite((1.0 + depth).ln() / (1.0 + spread.max(0.0)))),
    );

    put(
        &mut values,
        "l2_trade_notional_burst_15m",
        l2_robust_z(rows, idx, 15, L2Field::TradeNotional),
    );
    put(
        &mut values,
        "l2_trade_notional_burst_60m",
        l2_robust_z(rows, idx, 60, L2Field::TradeNotional),
    );
    put(
        &mut values,
        "l2_trade_count_burst_15m",
        l2_robust_z(rows, idx, 15, L2Field::TradeCount),
    );
    put(
        &mut values,
        "trade_flow_imbalance",
        row.trade_flow_imbalance,
    );
    put(&mut values, "reported_buy_share", row.reported_buy_share);
    put(
        &mut values,
        "flow_imbalance_delta_5m",
        prev5.and_then(|prev| diff_opt(row.trade_flow_imbalance, prev.trade_flow_imbalance)),
    );

    let cross = cross_venue(row, other);
    put(&mut values, "cross_venue_basis_bps", cross.basis_bps);
    put(
        &mut values,
        "cross_venue_basis_abs_bps",
        cross.basis_bps.map(f64::abs),
    );
    put(
        &mut values,
        "cross_venue_spread_diff_bps",
        cross.spread_diff_bps,
    );
    put(
        &mut values,
        "cross_venue_activity_ratio",
        cross.activity_ratio,
    );
    put(
        &mut values,
        "cross_venue_microprice_disagreement_bps",
        cross.microprice_disagreement_bps,
    );
    put(
        &mut values,
        "cross_venue_microprice_abs_bps",
        cross.microprice_disagreement_bps.map(f64::abs),
    );

    put(
        &mut values,
        "bullish_avg_corr_60m",
        cov.and_then(|row| row.avg_corr_60m),
    );
    put(
        &mut values,
        "bullish_first_eigen_share_60m",
        cov.and_then(|row| row.first_eigen_share_60m),
    );
    put(
        &mut values,
        "bullish_cross_abs_ret_mean_bps",
        cov.and_then(|row| row.cross_symbol_abs_ret_mean_bps),
    );
    put(
        &mut values,
        "bullish_common_mode_score",
        cov.and_then(|row| {
            mean_opt(&[
                row.avg_corr_60m,
                row.first_eigen_share_60m,
                row.cross_symbol_abs_ret_mean_bps.map(|v| -v / 100.0),
            ])
        }),
    );
    put(
        &mut values,
        "price_positive_age_1m",
        price.positive_return_age("BONKUSDT", ts, 60),
    );
    put(
        &mut values,
        "l2_positive_age_1m",
        l2_positive_age(rows, idx, 60),
    );
    put(
        &mut values,
        "ask_withdraw_persistence_5m",
        l2_transition_persistence(rows, idx, 5, TransitionKind::AskWithdraw),
    );
    put(
        &mut values,
        "bid_replenish_persistence_5m",
        l2_transition_persistence(rows, idx, 5, TransitionKind::BidReplenish),
    );
    put(
        &mut values,
        "spread_compression_persistence_5m",
        l2_transition_persistence(rows, idx, 5, TransitionKind::SpreadCompression),
    );
    put(
        &mut values,
        "l2_impulse_decay_5m",
        l2_impulse_decay(rows, idx, 5),
    );
    put(
        &mut values,
        "l2_transition_count_10m",
        l2_transition_count(rows, idx, 10),
    );

    let l2_impulse = mean_opt(&[
        values
            .get("ask_withdraw_5m")
            .copied()
            .flatten()
            .map(|v| v * 100.0),
        values
            .get("bid_replenish_5m")
            .copied()
            .flatten()
            .map(|v| v * 100.0),
        values.get("spread_compression_5m_bps").copied().flatten(),
        values.get("microprice_impulse_5m_bps").copied().flatten(),
        values
            .get("wobi5_impulse_5m")
            .copied()
            .flatten()
            .map(|v| v * 100.0),
        values
            .get("depth_imbalance25_delta_5m")
            .copied()
            .flatten()
            .map(|v| v * 100.0),
    ]);
    put(&mut values, "l2_impulse_score_raw", l2_impulse);
    put(
        &mut values,
        "book_flow_alignment",
        l2_impulse
            .zip(row.trade_flow_imbalance)
            .and_then(|(a, b)| finite(a * b)),
    );
    let price_book_alignment_5m = get_factor_value(&values, "price_mom_5m_bps")
        .zip(l2_impulse)
        .and_then(|(a, b)| finite(a * b / 100.0));
    put(
        &mut values,
        "price_book_alignment_5m",
        price_book_alignment_5m,
    );

    let context_price_alignment = get_factor_value(&values, "lead_meme_catchup_15m_bps")
        .zip(get_factor_value(&values, "price_mom_5m_bps"))
        .and_then(|(a, b)| finite(a * b / 100.0));
    put(
        &mut values,
        "context_price_alignment",
        context_price_alignment,
    );

    let context_book_alignment = get_factor_value(&values, "resonance_weighted_raw")
        .zip(l2_impulse)
        .and_then(|(a, b)| finite(a * b));
    put(
        &mut values,
        "context_book_alignment",
        context_book_alignment,
    );

    let price_x_book_x_flow = get_factor_value(&values, "price_mom_5m_bps")
        .zip(l2_impulse)
        .zip(row.trade_flow_imbalance)
        .and_then(|((a, b), c)| finite(a * b * c / 100.0));
    put(&mut values, "price_x_book_x_flow", price_x_book_x_flow);

    let cost_x_context_signal = context_book_alignment
        .zip(row.spread_bps_median)
        .and_then(|(signal, spread)| finite(signal - spread.max(0.0) - DEFAULT_FEE_BPS));
    put(&mut values, "cost_x_context_signal", cost_x_context_signal);

    let market_resonance_weighted_impulse_raw = mean_opt(&[
        get_factor_value(&values, "resonance_weighted_raw"),
        get_factor_value(&values, "lead_meme_catchup_15m_bps").map(|v| v / 100.0),
        get_factor_value(&values, "l2_impulse_score_raw"),
    ]);
    put(
        &mut values,
        "market_resonance_weighted_impulse_raw",
        market_resonance_weighted_impulse_raw,
    );

    let liquidity_adjusted_relative_momentum_raw = mean_opt(&[
        get_factor_value(&values, "rel_meme_15m_bps").map(|v| v / 100.0),
        get_factor_value(&values, "liquidity_adjusted_momentum_5m").map(|v| v / 100.0),
        get_factor_value(&values, "inverse_spread_depth"),
    ]);
    put(
        &mut values,
        "liquidity_adjusted_relative_momentum_raw",
        liquidity_adjusted_relative_momentum_raw,
    );

    let spread_cost_adjusted_book_impulse_raw = mean_opt(&[
        get_factor_value(&values, "l2_impulse_score_raw"),
        get_factor_value(&values, "cost_adjusted_signal_strength_5m").map(|v| v / 100.0),
        get_factor_value(&values, "spread_compression_5m_bps").map(|v| v / 10.0),
    ]);
    put(
        &mut values,
        "spread_cost_adjusted_book_impulse_raw",
        spread_cost_adjusted_book_impulse_raw,
    );

    let regime_conditioned_factor_mixture_raw = mean_opt(&[
        market_resonance_weighted_impulse_raw,
        liquidity_adjusted_relative_momentum_raw,
        get_factor_value(&values, "bullish_common_mode_score").map(|v| -v),
    ]);
    put(
        &mut values,
        "regime_conditioned_factor_mixture_raw",
        regime_conditioned_factor_mixture_raw,
    );

    let mut out = vec![None; defs.len()];
    for (name, value) in values {
        if let Some(&idx) = index.get(name) {
            out[idx] = value.and_then(finite);
        }
    }
    out
}

const MARKET_SYMBOLS: &[&str] = &["BTCUSDT", "ETHUSDT"];
const MEME_SYMBOLS: &[&str] = &["DOGEUSDT", "PEPEUSDT", "SHIBUSDT", "WIFUSDT", "PENGUUSDT"];
const ALT_SYMBOLS: &[&str] = &["APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT"];

#[derive(Debug, Clone, Copy)]
enum PriceField {
    QuoteVolume,
    TradeCount,
}

#[derive(Debug, Clone, Copy)]
enum L2Field {
    TradeNotional,
    TradeCount,
}

#[derive(Debug, Clone, Copy)]
enum TransitionKind {
    AskWithdraw,
    BidReplenish,
    SpreadCompression,
}

#[derive(Debug, Clone, Copy)]
struct RangeStats {
    position: Option<f64>,
    width_bps: Option<f64>,
    dist_from_high_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct PriceBook {
    rows: HashMap<String, Vec<PriceRawRow>>,
    pos: HashMap<(String, u64), usize>,
}

impl PriceBook {
    fn new(rows: Vec<PriceRawRow>) -> Self {
        let mut by_symbol: HashMap<String, Vec<PriceRawRow>> = HashMap::new();
        for row in rows {
            by_symbol.entry(row.symbol.clone()).or_default().push(row);
        }
        let mut pos = HashMap::new();
        for (symbol, rows) in &mut by_symbol {
            rows.sort_by_key(|row| row.timestamp_us);
            for (idx, row) in rows.iter().enumerate() {
                pos.insert((symbol.clone(), row.timestamp_us), idx);
            }
        }
        Self {
            rows: by_symbol,
            pos,
        }
    }

    fn row(&self, symbol: &str, ts: u64) -> Option<&PriceRawRow> {
        let idx = *self.pos.get(&(symbol.to_string(), ts))?;
        self.rows.get(symbol)?.get(idx)
    }

    fn bonk_row(&self, ts: u64) -> Option<&PriceRawRow> {
        self.row("BONKUSDT", ts)
    }

    fn rows_for(&self, symbol: &str) -> Option<&[PriceRawRow]> {
        self.rows.get(symbol).map(Vec::as_slice)
    }

    fn sum_ret(&self, symbol: &str, ts: u64, window: usize) -> Option<f64> {
        let rows = self.rows_for(symbol)?;
        let idx = *self.pos.get(&(symbol.to_string(), ts))?;
        trailing_sum_price(rows, idx, window, |row| row.ret_1m_bps)
    }

    fn prior_sum_ret(&self, symbol: &str, ts: u64, window: usize) -> Option<f64> {
        let rows = self.rows_for(symbol)?;
        let idx = *self.pos.get(&(symbol.to_string(), ts))?;
        if idx < window {
            return None;
        }
        trailing_sum_price(rows, idx - window, window, |row| row.ret_1m_bps)
    }

    fn basket_ret(&self, symbols: &[&str], ts: u64, window: usize) -> Option<f64> {
        mean_opt(
            &symbols
                .iter()
                .map(|symbol| self.sum_ret(symbol, ts, window))
                .collect::<Vec<_>>(),
        )
    }

    fn prior_basket_ret(&self, symbols: &[&str], ts: u64, window: usize) -> Option<f64> {
        mean_opt(
            &symbols
                .iter()
                .map(|symbol| self.prior_sum_ret(symbol, ts, window))
                .collect::<Vec<_>>(),
        )
    }

    fn rv(&self, symbol: &str, ts: u64, window: usize) -> Option<f64> {
        let rows = self.rows_for(symbol)?;
        let idx = *self.pos.get(&(symbol.to_string(), ts))?;
        trailing_rv_price(rows, idx, window, |row| row.ret_1m_bps)
    }

    fn range_stats(&self, symbol: &str, ts: u64, window: usize) -> Option<RangeStats> {
        let rows = self.rows_for(symbol)?;
        let idx = *self.pos.get(&(symbol.to_string(), ts))?;
        if idx + 1 < window {
            return None;
        }
        let start = idx + 1 - window;
        if rows[idx]
            .timestamp_us
            .saturating_sub(rows[start].timestamp_us)
            != (window as u64 - 1) * MINUTE_US
        {
            return None;
        }
        let close = rows[idx].close.and_then(finite)?;
        let mut min_close = f64::INFINITY;
        let mut max_close = f64::NEG_INFINITY;
        for row in rows.iter().take(idx + 1).skip(start) {
            let value = row.close.and_then(finite)?;
            min_close = min_close.min(value);
            max_close = max_close.max(value);
        }
        if min_close <= 0.0 || max_close <= min_close {
            return None;
        }
        Some(RangeStats {
            position: finite((close - min_close) / (max_close - min_close)),
            width_bps: finite((max_close / min_close - 1.0) * 10_000.0),
            dist_from_high_bps: finite((close / max_close - 1.0) * 10_000.0),
        })
    }

    fn robust_z(&self, symbol: &str, ts: u64, window: usize, field: PriceField) -> Option<f64> {
        let rows = self.rows_for(symbol)?;
        let idx = *self.pos.get(&(symbol.to_string(), ts))?;
        if idx + 1 < window {
            return None;
        }
        let start = idx + 1 - window;
        let mut vals = Vec::new();
        for row in rows.iter().take(idx + 1).skip(start) {
            vals.push(match field {
                PriceField::QuoteVolume => row.quote_volume,
                PriceField::TradeCount => row.trade_count as f64,
            });
        }
        robust_z_from_values(vals)
    }

    fn positive_return_age(&self, symbol: &str, ts: u64, max_minutes: usize) -> Option<f64> {
        let rows = self.rows_for(symbol)?;
        let mut idx = *self.pos.get(&(symbol.to_string(), ts))?;
        let mut age = 0usize;
        loop {
            let row = rows.get(idx)?;
            if row.ret_1m_bps.and_then(finite)? <= 0.0 {
                break;
            }
            age += 1;
            if age >= max_minutes || idx == 0 {
                break;
            }
            let prev = rows.get(idx - 1)?;
            if row.timestamp_us.saturating_sub(prev.timestamp_us) != MINUTE_US {
                break;
            }
            idx -= 1;
        }
        Some(age as f64)
    }
}

fn trailing_sum_price<F>(rows: &[PriceRawRow], idx: usize, window: usize, f: F) -> Option<f64>
where
    F: Fn(&PriceRawRow) -> Option<f64>,
{
    if idx + 1 < window {
        return None;
    }
    let start = idx + 1 - window;
    if rows[idx]
        .timestamp_us
        .saturating_sub(rows[start].timestamp_us)
        != (window as u64 - 1) * MINUTE_US
    {
        return None;
    }
    let mut sum = 0.0;
    for row in rows.iter().take(idx + 1).skip(start) {
        sum += f(row)?;
    }
    finite(sum)
}

fn trailing_rv_price<F>(rows: &[PriceRawRow], idx: usize, window: usize, f: F) -> Option<f64>
where
    F: Fn(&PriceRawRow) -> Option<f64>,
{
    if idx + 1 < window {
        return None;
    }
    let start = idx + 1 - window;
    if rows[idx]
        .timestamp_us
        .saturating_sub(rows[start].timestamp_us)
        != (window as u64 - 1) * MINUTE_US
    {
        return None;
    }
    let mut sum_sq = 0.0;
    for row in rows.iter().take(idx + 1).skip(start) {
        let value = f(row)?;
        sum_sq += value * value;
    }
    finite(sum_sq.sqrt())
}

fn l2_robust_z(rows: &[L2RawRow], idx: usize, window: usize, field: L2Field) -> Option<f64> {
    if idx + 1 < window {
        return None;
    }
    let start = idx + 1 - window;
    if rows[idx]
        .timestamp_us
        .saturating_sub(rows[start].timestamp_us)
        != (window as u64 - 1) * MINUTE_US
    {
        return None;
    }
    let vals = rows
        .iter()
        .take(idx + 1)
        .skip(start)
        .map(|row| match field {
            L2Field::TradeNotional => row.trade_notional,
            L2Field::TradeCount => row.trade_count as f64,
        })
        .collect::<Vec<_>>();
    robust_z_from_values(vals)
}

fn l2_positive_age(rows: &[L2RawRow], mut idx: usize, max_minutes: usize) -> Option<f64> {
    let mut age = 0usize;
    loop {
        let row = rows.get(idx)?;
        if row.l2_ret_1m_bps.and_then(finite)? <= 0.0 {
            break;
        }
        age += 1;
        if age >= max_minutes || idx == 0 {
            break;
        }
        let prev = rows.get(idx - 1)?;
        if row.timestamp_us.saturating_sub(prev.timestamp_us) != MINUTE_US {
            break;
        }
        idx -= 1;
    }
    Some(age as f64)
}

fn l2_transition_persistence(
    rows: &[L2RawRow],
    idx: usize,
    window: usize,
    kind: TransitionKind,
) -> Option<f64> {
    if idx < window {
        return None;
    }
    let mut count = 0usize;
    for cur_idx in (idx + 1 - window)..=idx {
        let prev = prev_l2(rows, cur_idx, 1)?;
        let cur = &rows[cur_idx];
        let active = match kind {
            TransitionKind::AskWithdraw => {
                withdraw(prev.depth_ask_25, cur.depth_ask_25).is_some_and(|value| value > 0.0)
            }
            TransitionKind::BidReplenish => {
                replenish(prev.depth_bid_25, cur.depth_bid_25).is_some_and(|value| value > 0.0)
            }
            TransitionKind::SpreadCompression => {
                compression(prev.spread_bps_median, cur.spread_bps_median)
                    .is_some_and(|value| value > 0.0)
            }
        };
        if active {
            count += 1;
        }
    }
    Some(count as f64)
}

fn l2_impulse_decay(rows: &[L2RawRow], idx: usize, window: usize) -> Option<f64> {
    if idx + 1 < window {
        return None;
    }
    let mut weighted = 0.0;
    let mut weight_sum = 0.0;
    for lag in 0..window {
        let cur_idx = idx - lag;
        if lag > 0
            && rows[cur_idx + 1]
                .timestamp_us
                .saturating_sub(rows[cur_idx].timestamp_us)
                != MINUTE_US
        {
            return None;
        }
        let value = rows[cur_idx].l2_ret_1m_bps?;
        let weight = (-(lag as f64) / 2.0).exp();
        weighted += value * weight;
        weight_sum += weight;
    }
    finite(weighted / weight_sum.max(1e-9))
}

fn l2_transition_count(rows: &[L2RawRow], idx: usize, window: usize) -> Option<f64> {
    if idx < window {
        return None;
    }
    let mut count = 0usize;
    let mut prev_sign = rows[idx - window].l2_ret_1m_bps?.signum();
    for cur_idx in (idx + 1 - window)..=idx {
        let prev = &rows[cur_idx - 1];
        let cur = &rows[cur_idx];
        if cur.timestamp_us.saturating_sub(prev.timestamp_us) != MINUTE_US {
            return None;
        }
        let sign = cur.l2_ret_1m_bps?.signum();
        if sign != 0.0 && prev_sign != 0.0 && sign != prev_sign {
            count += 1;
        }
        if sign != 0.0 {
            prev_sign = sign;
        }
    }
    Some(count as f64)
}

fn robust_z_from_values(mut vals: Vec<f64>) -> Option<f64> {
    vals.retain(|value| value.is_finite());
    if vals.len() < 5 {
        return None;
    }
    let current = *vals.last()?;
    vals.sort_by(|a, b| a.total_cmp(b));
    let med = quantile(&vals, 0.5);
    let q25 = quantile(&vals, 0.25);
    let q75 = quantile(&vals, 0.75);
    let scale = (q75 - q25).abs().max(1e-9);
    finite((current - med) / scale)
}

fn prev_l2(rows: &[L2RawRow], idx: usize, minutes: usize) -> Option<&L2RawRow> {
    if idx < minutes {
        return None;
    }
    let prev = &rows[idx - minutes];
    (rows[idx].timestamp_us.saturating_sub(prev.timestamp_us) == minutes as u64 * MINUTE_US)
        .then_some(prev)
}

#[derive(Debug, Clone, Copy)]
struct CrossVenue {
    basis_bps: Option<f64>,
    spread_diff_bps: Option<f64>,
    activity_ratio: Option<f64>,
    microprice_disagreement_bps: Option<f64>,
}

fn cross_venue(row: &L2RawRow, other: Option<&L2RawRow>) -> CrossVenue {
    let Some(other) = other else {
        return CrossVenue {
            basis_bps: None,
            spread_diff_bps: None,
            activity_ratio: None,
            microprice_disagreement_bps: None,
        };
    };
    let basis = row
        .mid_close
        .zip(other.mid_close)
        .and_then(|(a, b)| (a > 0.0 && b > 0.0).then(|| (a / b - 1.0) * 10_000.0))
        .and_then(finite);
    let spread_diff = diff_opt(row.spread_bps_median, other.spread_bps_median);
    let activity = finite((1.0 + row.trade_notional) / (1.0 + other.trade_notional));
    let micro = diff_opt(row.microprice_offset, other.microprice_offset);
    CrossVenue {
        basis_bps: basis,
        spread_diff_bps: spread_diff,
        activity_ratio: activity,
        microprice_disagreement_bps: micro,
    }
}

fn signed_corr_component(a: Option<f64>, b: Option<f64>, corr: Option<f64>) -> Option<f64> {
    let (a, b, corr) = (a?, b?, corr?);
    finite(a.signum() * b.signum() * corr.abs())
}

fn withdraw(prev: Option<f64>, cur: Option<f64>) -> Option<f64> {
    let (prev, cur) = (prev?, cur?);
    if prev <= 0.0 {
        return None;
    }
    finite(((prev - cur) / prev).max(0.0))
}

fn replenish(prev: Option<f64>, cur: Option<f64>) -> Option<f64> {
    let (prev, cur) = (prev?, cur?);
    if prev <= 0.0 {
        return None;
    }
    finite(((cur - prev) / prev).max(0.0))
}

fn compression(prev: Option<f64>, cur: Option<f64>) -> Option<f64> {
    let (prev, cur) = (prev?, cur?);
    finite((prev - cur).max(0.0))
}

fn expansion(prev: Option<f64>, cur: Option<f64>) -> Option<f64> {
    let (prev, cur) = (prev?, cur?);
    finite((cur - prev).max(0.0))
}

fn slope(top5: Option<f64>, depth25: Option<f64>) -> Option<f64> {
    let (top5, depth25) = (top5?, depth25?);
    if depth25 <= 0.0 {
        return None;
    }
    finite(((depth25 - top5).max(0.0)) / depth25)
}

fn ret_bps(cur: Option<f64>, prev: Option<f64>) -> Option<f64> {
    let (cur, prev) = (cur?, prev?);
    if cur <= 0.0 || prev <= 0.0 {
        return None;
    }
    finite((cur / prev - 1.0) * 10_000.0)
}

fn ratio_opt(a: Option<f64>, b: Option<f64>) -> Option<f64> {
    let (a, b) = (a?, b?);
    if b.abs() <= 1e-12 {
        return None;
    }
    finite(a / b)
}

fn add_opt(a: Option<f64>, b: Option<f64>) -> Option<f64> {
    a.zip(b).and_then(|(a, b)| finite(a + b))
}

fn diff_opt(a: Option<f64>, b: Option<f64>) -> Option<f64> {
    a.zip(b).and_then(|(a, b)| finite(a - b))
}

fn mean_opt(values: &[Option<f64>]) -> Option<f64> {
    let mut sum = 0.0;
    let mut count = 0usize;
    for value in values.iter().filter_map(|value| value.and_then(finite)) {
        sum += value;
        count += 1;
    }
    (count > 0).then_some(sum / count as f64).and_then(finite)
}

fn weighted_mean(values: &[Option<f64>]) -> Option<f64> {
    mean_opt(values)
}

fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn get_factor_value(
    values: &HashMap<&'static str, Option<f64>>,
    name: &'static str,
) -> Option<f64> {
    values.get(name).copied().flatten().and_then(finite)
}

fn read_l2_rows(path: &Path, run_tag_filter: &str) -> Result<Vec<L2RawRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let run_tag = str_array(&batch, "run_tag")?;
        let timestamp_utc = str_array(&batch, "timestamp_utc")?;
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        let mid_open = f64_array(&batch, "mid_price_per_unit_open")?;
        let mid_high = f64_array(&batch, "mid_price_per_unit_high")?;
        let mid_low = f64_array(&batch, "mid_price_per_unit_low")?;
        let mid_close = f64_array(&batch, "mid_price_per_unit_close")?;
        let spread_bps_median = f64_array(&batch, "spread_bps_median")?;
        let spread_bps_last = f64_array(&batch, "spread_bps_last")?;
        let top_depth_bid = f64_array(&batch, "top_depth_bid_notional_median")?;
        let top_depth_ask = f64_array(&batch, "top_depth_ask_notional_median")?;
        let microprice_offset = f64_array(&batch, "microprice_offset_bps_mean")?;
        let snapshot_spread_bps = f64_array(&batch, "snapshot_spread_bps_median")?;
        let snapshot_microprice_offset = f64_array(&batch, "snapshot_microprice_offset_bps_mean")?;
        let wobi5 = f64_array(&batch, "wobi5_mean")?;
        let wobi25 = f64_array(&batch, "wobi25_mean")?;
        let depth_imbalance_5 = f64_array(&batch, "depth_imbalance_5_mean")?;
        let depth_imbalance_25 = f64_array(&batch, "depth_imbalance_25_mean")?;
        let depth_bid_5 = f64_array(&batch, "depth_bid_notional_5_median")?;
        let depth_ask_5 = f64_array(&batch, "depth_ask_notional_5_median")?;
        let depth_bid_25 = f64_array(&batch, "depth_bid_notional_25_median")?;
        let depth_ask_25 = f64_array(&batch, "depth_ask_notional_25_median")?;
        let trade_count = u64_array_col(&batch, "trade_count")?;
        let trade_notional = f64_array(&batch, "trade_notional_quote_sum")?;
        let trade_flow_imbalance = f64_array(&batch, "trade_flow_imbalance")?;
        let reported_buy_share = f64_array(&batch, "reported_buy_share")?;
        let l2_ret_1m_bps = f64_array(&batch, "ret_1m_bps")?;
        for idx in 0..batch.num_rows() {
            if str_value(run_tag, idx) != run_tag_filter {
                continue;
            }
            let sym = str_value(symbol, idx);
            if !DEFAULT_SYMBOLS.contains(&sym.as_str()) {
                continue;
            }
            out.push(L2RawRow {
                timestamp_utc: str_value(timestamp_utc, idx),
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: sym,
                mid_open: opt_f64_value(mid_open, idx),
                mid_high: opt_f64_value(mid_high, idx),
                mid_low: opt_f64_value(mid_low, idx),
                mid_close: opt_f64_value(mid_close, idx),
                spread_bps_median: opt_f64_value(spread_bps_median, idx),
                spread_bps_last: opt_f64_value(spread_bps_last, idx),
                top_depth_bid: opt_f64_value(top_depth_bid, idx),
                top_depth_ask: opt_f64_value(top_depth_ask, idx),
                microprice_offset: opt_f64_value(microprice_offset, idx),
                snapshot_spread_bps: opt_f64_value(snapshot_spread_bps, idx),
                snapshot_microprice_offset: opt_f64_value(snapshot_microprice_offset, idx),
                wobi5: opt_f64_value(wobi5, idx),
                wobi25: opt_f64_value(wobi25, idx),
                depth_imbalance_5: opt_f64_value(depth_imbalance_5, idx),
                depth_imbalance_25: opt_f64_value(depth_imbalance_25, idx),
                depth_bid_5: opt_f64_value(depth_bid_5, idx),
                depth_ask_5: opt_f64_value(depth_ask_5, idx),
                depth_bid_25: opt_f64_value(depth_bid_25, idx),
                depth_ask_25: opt_f64_value(depth_ask_25, idx),
                trade_count: u64_value(trade_count, idx),
                trade_notional: opt_f64_value(trade_notional, idx).unwrap_or(0.0),
                trade_flow_imbalance: opt_f64_value(trade_flow_imbalance, idx),
                reported_buy_share: opt_f64_value(reported_buy_share, idx),
                l2_ret_1m_bps: opt_f64_value(l2_ret_1m_bps, idx),
            });
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
    });
    Ok(out)
}

fn read_price_rows(path: &Path) -> Result<Vec<PriceRawRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        let close = f64_array(&batch, "close")?;
        let quote_volume = f64_array(&batch, "quote_volume")?;
        let trade_count = u64_array_col(&batch, "trade_count")?;
        let ret_1m_bps = f64_array(&batch, "ret_1m_bps")?;
        let rv_15m_bps = f64_array(&batch, "rv_15m_bps")?;
        let rv_1h_bps = f64_array(&batch, "rv_1h_bps")?;
        let rv_4h_bps = f64_array(&batch, "rv_4h_bps")?;
        let rv_12h_bps = f64_array(&batch, "rv_12h_bps")?;
        let bonk_beta_market_60m = f64_array(&batch, "bonk_beta_market_60m")?;
        let bonk_corr_market_60m = f64_array(&batch, "bonk_corr_market_60m")?;
        let bonk_beta_meme_60m = f64_array(&batch, "bonk_beta_meme_60m")?;
        let bonk_corr_meme_60m = f64_array(&batch, "bonk_corr_meme_60m")?;
        let bonk_beta_sol_60m = f64_array(&batch, "bonk_beta_sol_60m")?;
        let bonk_corr_sol_60m = f64_array(&batch, "bonk_corr_sol_60m")?;
        let bonk_beta_market_240m = f64_array(&batch, "bonk_beta_market_240m")?;
        let bonk_corr_market_240m = f64_array(&batch, "bonk_corr_market_240m")?;
        let bonk_beta_meme_240m = f64_array(&batch, "bonk_beta_meme_240m")?;
        let bonk_corr_meme_240m = f64_array(&batch, "bonk_corr_meme_240m")?;
        let bonk_beta_sol_240m = f64_array(&batch, "bonk_beta_sol_240m")?;
        let bonk_corr_sol_240m = f64_array(&batch, "bonk_corr_sol_240m")?;
        for idx in 0..batch.num_rows() {
            out.push(PriceRawRow {
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: str_value(symbol, idx),
                close: opt_f64_value(close, idx),
                quote_volume: opt_f64_value(quote_volume, idx).unwrap_or(0.0),
                trade_count: u64_value(trade_count, idx),
                ret_1m_bps: opt_f64_value(ret_1m_bps, idx),
                rv_15m_bps: opt_f64_value(rv_15m_bps, idx),
                rv_1h_bps: opt_f64_value(rv_1h_bps, idx),
                rv_4h_bps: opt_f64_value(rv_4h_bps, idx),
                rv_12h_bps: opt_f64_value(rv_12h_bps, idx),
                bonk_beta_market_60m: opt_f64_value(bonk_beta_market_60m, idx),
                bonk_corr_market_60m: opt_f64_value(bonk_corr_market_60m, idx),
                bonk_beta_meme_60m: opt_f64_value(bonk_beta_meme_60m, idx),
                bonk_corr_meme_60m: opt_f64_value(bonk_corr_meme_60m, idx),
                bonk_beta_sol_60m: opt_f64_value(bonk_beta_sol_60m, idx),
                bonk_corr_sol_60m: opt_f64_value(bonk_corr_sol_60m, idx),
                bonk_beta_market_240m: opt_f64_value(bonk_beta_market_240m, idx),
                bonk_corr_market_240m: opt_f64_value(bonk_corr_market_240m, idx),
                bonk_beta_meme_240m: opt_f64_value(bonk_beta_meme_240m, idx),
                bonk_corr_meme_240m: opt_f64_value(bonk_corr_meme_240m, idx),
                bonk_beta_sol_240m: opt_f64_value(bonk_beta_sol_240m, idx),
                bonk_corr_sol_240m: opt_f64_value(bonk_corr_sol_240m, idx),
            });
        }
    }
    Ok(out)
}

fn read_cov_rows(path: &Path) -> Result<Vec<CovRawRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let avg_corr_60m = f64_array(&batch, "avg_corr_60m")?;
        let first_eigen_share_60m = f64_array(&batch, "first_eigen_share_60m")?;
        let cross_symbol_abs_ret_mean_bps = f64_array(&batch, "cross_symbol_abs_ret_mean_bps")?;
        for idx in 0..batch.num_rows() {
            out.push(CovRawRow {
                timestamp_us: u64_value(timestamp_us, idx),
                avg_corr_60m: opt_f64_value(avg_corr_60m, idx),
                first_eigen_share_60m: opt_f64_value(first_eigen_share_60m, idx),
                cross_symbol_abs_ret_mean_bps: opt_f64_value(cross_symbol_abs_ret_mean_bps, idx),
            });
        }
    }
    Ok(out)
}

fn write_factor_panel(path: &Path, rows: &[FactorRow], defs: &[FactorDef]) -> Result<()> {
    let mut fields = vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("timestamp_utc", DataType::Utf8, false),
        Field::new("timestamp_us", DataType::UInt64, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("mid_open", DataType::Float64, true),
        Field::new("mid_high", DataType::Float64, true),
        Field::new("mid_low", DataType::Float64, true),
        Field::new("mid_close", DataType::Float64, true),
        Field::new("spread_bps", DataType::Float64, true),
        Field::new("depth_bid_25", DataType::Float64, true),
        Field::new("depth_ask_25", DataType::Float64, true),
    ];
    for def in defs {
        fields.push(Field::new(def.name, DataType::Float64, true));
    }
    let schema = Arc::new(Schema::new(fields));
    let mut columns: Vec<ArrayRef> = vec![
        string_array(
            &rows
                .iter()
                .map(|row| row.run_tag.clone())
                .collect::<Vec<_>>(),
        ),
        string_array(
            &rows
                .iter()
                .map(|row| row.timestamp_utc.clone())
                .collect::<Vec<_>>(),
        ),
        u64_array(&rows.iter().map(|row| row.timestamp_us).collect::<Vec<_>>()),
        string_array(
            &rows
                .iter()
                .map(|row| row.symbol.clone())
                .collect::<Vec<_>>(),
        ),
        opt_col(rows, |row| row.mid_open),
        opt_col(rows, |row| row.mid_high),
        opt_col(rows, |row| row.mid_low),
        opt_col(rows, |row| row.mid_close),
        opt_col(rows, |row| row.spread_bps),
        opt_col(rows, |row| row.depth_bid_25),
        opt_col(rows, |row| row.depth_ask_25),
    ];
    for idx in 0..defs.len() {
        let mut builder = Float64Builder::with_capacity(rows.len());
        for row in rows {
            match row.factors.get(idx).copied().flatten().and_then(finite) {
                Some(value) => builder.append_value(value),
                None => builder.append_null(),
            }
        }
        columns.push(Arc::new(builder.finish()));
    }
    let batch = RecordBatch::try_new(schema.clone(), columns)?;
    write_parquet_atomic(path, schema, batch)
}

fn read_factor_panel(path: &Path, defs: &[FactorDef]) -> Result<Vec<FactorRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let run_tag = str_array(&batch, "run_tag")?;
        let timestamp_utc = str_array(&batch, "timestamp_utc")?;
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        let mid_open = f64_array(&batch, "mid_open")?;
        let mid_high = f64_array(&batch, "mid_high")?;
        let mid_low = f64_array(&batch, "mid_low")?;
        let mid_close = f64_array(&batch, "mid_close")?;
        let spread_bps = f64_array(&batch, "spread_bps")?;
        let depth_bid_25 = f64_array(&batch, "depth_bid_25")?;
        let depth_ask_25 = f64_array(&batch, "depth_ask_25")?;
        let factor_arrays = defs
            .iter()
            .map(|def| f64_array(&batch, def.name))
            .collect::<Result<Vec<_>>>()?;
        for idx in 0..batch.num_rows() {
            out.push(FactorRow {
                run_tag: str_value(run_tag, idx),
                timestamp_utc: str_value(timestamp_utc, idx),
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: str_value(symbol, idx),
                mid_open: opt_f64_value(mid_open, idx),
                mid_high: opt_f64_value(mid_high, idx),
                mid_low: opt_f64_value(mid_low, idx),
                mid_close: opt_f64_value(mid_close, idx),
                spread_bps: opt_f64_value(spread_bps, idx),
                depth_bid_25: opt_f64_value(depth_bid_25, idx),
                depth_ask_25: opt_f64_value(depth_ask_25, idx),
                factors: factor_arrays
                    .iter()
                    .map(|array| opt_f64_value(array, idx))
                    .collect(),
            });
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
    });
    Ok(out)
}

fn build_factor_audit(
    config: &V8Config,
    rows: &[FactorRow],
    defs: &[FactorDef],
) -> Result<Vec<FactorAuditRow>> {
    let out_tag = out_tag(config);
    let by_symbol = rows_by_symbol(rows);
    let horizons = [5u32, 10, 20, 30, 60];
    let mut out = Vec::new();
    for &symbol in DEFAULT_SYMBOLS {
        let Some(symbol_rows) = by_symbol.get(symbol) else {
            continue;
        };
        for fold in FOLDS {
            let train_end = fold.train_end_us()?;
            let valid_start = fold.valid_start_us()?;
            let valid_end = fold.valid_end_us()?;
            let train_idx = symbol_rows
                .iter()
                .enumerate()
                .filter(|(_, row)| row.timestamp_us <= train_end)
                .map(|(idx, _)| idx)
                .collect::<Vec<_>>();
            let valid_idx = symbol_rows
                .iter()
                .enumerate()
                .filter(|(_, row)| row.timestamp_us >= valid_start && row.timestamp_us <= valid_end)
                .map(|(idx, _)| idx)
                .collect::<Vec<_>>();
            if train_idx.is_empty() || valid_idx.is_empty() {
                continue;
            }
            for (factor_idx, def) in defs.iter().enumerate() {
                let train_values = train_idx
                    .iter()
                    .filter_map(|&idx| symbol_rows[idx].factors.get(factor_idx).copied().flatten())
                    .collect::<Vec<_>>();
                let Some((low, high)) = fit_tertiles(train_values) else {
                    continue;
                };
                for side in [ConditionSide::High, ConditionSide::Low] {
                    let threshold = match side {
                        ConditionSide::High => high,
                        ConditionSide::Low => low,
                        ConditionSide::HighAbs => high.abs().max(low.abs()),
                    };
                    for &horizon in &horizons {
                        let selected_train = select_indices_by_threshold(
                            symbol_rows,
                            &train_idx,
                            factor_idx,
                            side,
                            threshold,
                        );
                        let selected_valid = select_indices_by_threshold(
                            symbol_rows,
                            &valid_idx,
                            factor_idx,
                            side,
                            threshold,
                        );
                        let train_returns = selected_train
                            .iter()
                            .filter_map(|&idx| {
                                future_return_bps(symbol_rows, idx, horizon as usize)
                            })
                            .collect::<Vec<_>>();
                        let valid_returns = selected_valid
                            .iter()
                            .filter_map(|&idx| {
                                future_return_bps(symbol_rows, idx, horizon as usize)
                            })
                            .collect::<Vec<_>>();
                        let side_name = match side {
                            ConditionSide::High => "high",
                            ConditionSide::Low => "low",
                            ConditionSide::HighAbs => "high_abs",
                        };
                        out.push(FactorAuditRow {
                            run_tag: config.run_tag.clone(),
                            out_tag: out_tag.clone(),
                            fold: fold.name.to_string(),
                            symbol: symbol.to_string(),
                            factor_name: def.name.to_string(),
                            family: def.family.to_string(),
                            side: side_name.to_string(),
                            threshold_fit_on_train: format!(
                                "{side_name}@{}",
                                fmt_float(threshold, 6)
                            ),
                            horizon_minutes: horizon,
                            train_count: train_idx.len(),
                            valid_count: valid_idx.len(),
                            selected_train_count: selected_train.len(),
                            selected_valid_count: selected_valid.len(),
                            selected_valid_share: selected_valid.len() as f64
                                / valid_idx.len() as f64,
                            train_mean_future_bps: mean(&train_returns),
                            valid_mean_future_bps: mean(&valid_returns),
                            valid_median_future_bps: median(&valid_returns),
                            valid_win_rate: win_rate_bps(&valid_returns),
                            valid_signal_per_day: selected_valid.len() as f64 / fold.day_count()?,
                            guardrail: GUARDRAIL.to_string(),
                        });
                    }
                }
            }
        }
    }
    out.sort_by(|a, b| {
        a.fold
            .cmp(&b.fold)
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.family.cmp(&b.family))
            .then_with(|| a.factor_name.cmp(&b.factor_name))
            .then_with(|| a.horizon_minutes.cmp(&b.horizon_minutes))
    });
    Ok(out)
}

fn select_indices_by_threshold(
    rows: &[&FactorRow],
    indices: &[usize],
    factor_idx: usize,
    side: ConditionSide,
    threshold: f64,
) -> Vec<usize> {
    indices
        .iter()
        .copied()
        .filter(|&idx| {
            let value = rows[idx].factors.get(factor_idx).copied().flatten();
            pass_threshold(value, side, threshold)
        })
        .collect()
}

fn rows_by_symbol(rows: &[FactorRow]) -> BTreeMap<String, Vec<&FactorRow>> {
    let mut by_symbol: BTreeMap<String, Vec<&FactorRow>> = BTreeMap::new();
    for row in rows {
        by_symbol.entry(row.symbol.clone()).or_default().push(row);
    }
    for rows in by_symbol.values_mut() {
        rows.sort_by_key(|row| row.timestamp_us);
    }
    by_symbol
}

fn future_return_bps(rows: &[&FactorRow], idx: usize, horizon_minutes: usize) -> Option<f64> {
    let future_idx = idx.checked_add(horizon_minutes)?;
    let cur = rows.get(idx)?;
    let future = rows.get(future_idx)?;
    if future.timestamp_us.saturating_sub(cur.timestamp_us) != horizon_minutes as u64 * MINUTE_US {
        return None;
    }
    ret_bps(future.mid_close, cur.mid_close)
}

fn pass_threshold(value: Option<f64>, side: ConditionSide, threshold: f64) -> bool {
    let Some(value) = value.and_then(finite) else {
        return false;
    };
    match side {
        ConditionSide::Low => value <= threshold,
        ConditionSide::High => value >= threshold,
        ConditionSide::HighAbs => value.abs() >= threshold,
    }
}

fn run_episode_backtests(
    config: &V8Config,
    rows: &[FactorRow],
    defs: &[FactorDef],
    _paths: &Paths,
) -> Result<EpisodeOutputs> {
    let out_tag = out_tag(config);
    let index = factor_index(defs);
    let specs = candidate_specs();
    let by_symbol = rows_by_symbol(rows);
    let mut candidate_fits = Vec::new();
    let mut trades = Vec::new();
    let mut configs = Vec::new();
    let mut base_trade_number = 0usize;

    for &symbol in DEFAULT_SYMBOLS {
        let Some(symbol_rows) = by_symbol.get(symbol) else {
            continue;
        };
        for spec in &specs {
            for fold in FOLDS {
                let (signals, fit_detail, selected_minutes, starts) =
                    build_candidate_signal_frame(config, symbol_rows, &index, spec, fold)?;
                let validation_dates = fold.validation_dates()?;
                let starts_per_day = starts as f64 / fold.day_count()?;
                candidate_fits.push(CandidateFitRow {
                    run_tag: config.run_tag.clone(),
                    out_tag: out_tag.clone(),
                    fold: fold.name.to_string(),
                    symbol: symbol.to_string(),
                    candidate_id: spec.candidate_id.to_string(),
                    candidate_group: spec.candidate_group.to_string(),
                    candidate_name: spec.candidate_name.to_string(),
                    gate_expression: spec.description.to_string(),
                    fit_detail: fit_detail.clone(),
                    selected_minutes,
                    selected_share: if signals.is_empty() {
                        0.0
                    } else {
                        selected_minutes as f64 / signals.len() as f64
                    },
                    starts_after_debounce: starts,
                    starts_per_day,
                    debounce_on_minutes: config.debounce_on_minutes,
                    debounce_off_minutes: config.debounce_off_minutes,
                    cooldown_minutes: config.cooldown_minutes,
                    min_hold_minutes: config.min_hold_minutes,
                    guardrail: GUARDRAIL.to_string(),
                });

                for &tp_bps in &config.tp_bps {
                    for &sl_bps in &config.sl_bps {
                        for &timeout_minutes in &config.timeout_minutes {
                            let mut entry_skips = 0usize;
                            let base_trades = simulate_base_trades_for_config(
                                config,
                                &signals,
                                spec,
                                fold,
                                tp_bps,
                                sl_bps,
                                timeout_minutes,
                                &fit_detail,
                                &mut base_trade_number,
                                &mut entry_skips,
                            );
                            for execution_model in &config.execution_models {
                                for base in &base_trades {
                                    trades.push(expand_execution_trade(
                                        base,
                                        execution_model,
                                        &config.run_tag,
                                        &out_tag,
                                        config.notional_quote,
                                        config.fee_bps,
                                    ));
                                }
                                configs.push(ConfigRow {
                                    key: ConfigKey {
                                        fold: fold.name.to_string(),
                                        candidate_group: spec.candidate_group.to_string(),
                                        candidate_id: spec.candidate_id.to_string(),
                                        candidate_name: spec.candidate_name.to_string(),
                                        symbol: symbol.to_string(),
                                        execution_model: execution_model.clone(),
                                        tp_bps,
                                        sl_bps,
                                        timeout_minutes,
                                    },
                                    validation_dates: validation_dates.clone(),
                                    notional_quote: config.notional_quote,
                                    episode_starts: base_trades.len(),
                                    entry_skips,
                                });
                            }
                        }
                    }
                }
            }
        }
    }

    let daily = aggregate_daily(&trades, &configs);
    let summary = aggregate_summary(&trades, &daily);
    let exit_reasons = build_exit_reasons(&trades);
    let fold_stability = build_fold_stability(&summary);
    let non_overlap = build_non_overlap(&trades, &summary);
    let parameter_sensitivity = build_parameter_sensitivity(&summary);
    let single_day_dependence = build_single_day_dependence(&daily);
    let failure_diagnostics = build_failure_diagnostics(&summary, &fold_stability);

    Ok(EpisodeOutputs {
        candidate_fits,
        trades,
        daily,
        summary,
        exit_reasons,
        fold_stability,
        non_overlap,
        parameter_sensitivity,
        single_day_dependence,
        failure_diagnostics,
        configs,
    })
}

fn build_candidate_signal_frame(
    config: &V8Config,
    rows: &[&FactorRow],
    index: &HashMap<&'static str, usize>,
    spec: &CandidateSpec,
    fold: &FoldDef,
) -> Result<(Vec<SignalRow>, String, usize, usize)> {
    let train_end = fold.train_end_us()?;
    let valid_start = fold.valid_start_us()?;
    let valid_end = fold.valid_end_us()?;
    let train_idx = rows
        .iter()
        .enumerate()
        .filter(|(_, row)| row.timestamp_us <= train_end)
        .map(|(idx, _)| idx)
        .collect::<Vec<_>>();
    let valid_idx = rows
        .iter()
        .enumerate()
        .filter(|(_, row)| row.timestamp_us >= valid_start && row.timestamp_us <= valid_end)
        .map(|(idx, _)| idx)
        .collect::<Vec<_>>();
    if train_idx.is_empty() || valid_idx.is_empty() {
        return Ok((Vec::new(), "empty_train_or_validation".to_string(), 0, 0));
    }
    let fit_conditions = fit_candidate_conditions(rows, &train_idx, index, spec)?;
    let raw_selected = valid_idx
        .iter()
        .map(|&idx| {
            fit_conditions
                .iter()
                .all(|condition| condition_passes(condition, rows[idx]))
        })
        .collect::<Vec<_>>();
    let debounced = debounce_gate(
        &raw_selected,
        config.debounce_on_minutes,
        config.debounce_off_minutes,
    );
    let mut selected_minutes = 0usize;
    let signals = valid_idx
        .iter()
        .zip(debounced)
        .map(|(&idx, gate_selected)| {
            if gate_selected {
                selected_minutes += 1;
            }
            let row = rows[idx];
            SignalRow {
                timestamp_us: row.timestamp_us,
                timestamp_utc: row.timestamp_utc.clone(),
                symbol: row.symbol.clone(),
                open: row.mid_open,
                high: row.mid_high,
                low: row.mid_low,
                close: row.mid_close,
                spread_bps: row.spread_bps,
                depth_bid_25: row.depth_bid_25,
                depth_ask_25: row.depth_ask_25,
                gate_selected,
            }
        })
        .collect::<Vec<_>>();
    let starts = count_debounced_starts(&signals);
    let fit_detail = fit_conditions
        .iter()
        .map(fit_condition_detail)
        .collect::<Vec<_>>()
        .join("; ");
    Ok((signals, fit_detail, selected_minutes, starts))
}

fn fit_candidate_conditions(
    rows: &[&FactorRow],
    train_idx: &[usize],
    index: &HashMap<&'static str, usize>,
    spec: &CandidateSpec,
) -> Result<Vec<FitCondition>> {
    let mut out = Vec::new();
    for condition in &spec.conditions {
        match condition {
            ConditionSpec::Factor {
                factor,
                side,
                quantile,
            } => {
                let factor_idx = *index.get(*factor).ok_or_else(|| {
                    anyhow!(
                        "candidate {} references unknown factor {factor}",
                        spec.candidate_id
                    )
                })?;
                let values = train_idx
                    .iter()
                    .filter_map(|&idx| rows[idx].factors.get(factor_idx).copied().flatten())
                    .map(|value| match side {
                        ConditionSide::HighAbs => value.abs(),
                        ConditionSide::Low | ConditionSide::High => value,
                    })
                    .collect::<Vec<_>>();
                let threshold = fit_quantile(values, *quantile)
                    .ok_or_else(|| anyhow!("cannot fit threshold for {factor}"))?;
                out.push(FitCondition {
                    label: factor.to_string(),
                    side: *side,
                    threshold,
                    weighted: None,
                    factor_idx: Some(factor_idx),
                });
            }
            ConditionSpec::Weighted {
                score_id,
                side,
                quantile,
            } => {
                let fit = fit_weighted_score(rows, train_idx, index, score_id)?;
                let values = train_idx
                    .iter()
                    .filter_map(|&idx| weighted_score_value(rows[idx], &fit))
                    .map(|value| match side {
                        ConditionSide::HighAbs => value.abs(),
                        ConditionSide::Low | ConditionSide::High => value,
                    })
                    .collect::<Vec<_>>();
                let threshold = fit_quantile(values, *quantile)
                    .ok_or_else(|| anyhow!("cannot fit weighted threshold for {score_id}"))?;
                out.push(FitCondition {
                    label: score_id.to_string(),
                    side: *side,
                    threshold,
                    weighted: Some(fit),
                    factor_idx: None,
                });
            }
        }
    }
    Ok(out)
}

fn fit_weighted_score(
    rows: &[&FactorRow],
    train_idx: &[usize],
    index: &HashMap<&'static str, usize>,
    score_id: &str,
) -> Result<WeightedFit> {
    let factors = weighted_score_factors(score_id)?;
    let mut terms = Vec::new();
    let mut raw_weights = Vec::new();
    for factor in factors {
        let factor_idx = *index.get(factor).ok_or_else(|| {
            anyhow!("weighted score {score_id} references unknown factor {factor}")
        })?;
        let pairs = train_idx
            .iter()
            .filter_map(|&idx| {
                let x = rows[idx].factors.get(factor_idx).copied().flatten()?;
                let y = future_return_bps(rows, idx, 10)?;
                Some((x, y))
            })
            .collect::<Vec<_>>();
        let xs = pairs.iter().map(|(x, _)| *x).collect::<Vec<_>>();
        let ys = pairs.iter().map(|(_, y)| *y).collect::<Vec<_>>();
        let mean_x = mean(&xs).unwrap_or(0.0);
        let std_x = stddev(&xs).unwrap_or(1.0).max(1e-9);
        let corr = corr(&xs, &ys).unwrap_or(0.0);
        terms.push(WeightedTerm {
            factor_idx,
            factor_name: factor.to_string(),
            mean: mean_x,
            std: std_x,
            weight: corr,
        });
        raw_weights.push(corr);
    }
    let norm: f64 = raw_weights.iter().map(|value| value.abs()).sum();
    if norm <= 1e-12 {
        let equal = if terms.is_empty() {
            0.0
        } else {
            1.0 / terms.len() as f64
        };
        for term in &mut terms {
            term.weight = equal;
        }
    } else {
        for term in &mut terms {
            term.weight /= norm;
        }
    }
    Ok(WeightedFit {
        score_id: score_id.to_string(),
        terms,
    })
}

fn weighted_score_value(row: &FactorRow, fit: &WeightedFit) -> Option<f64> {
    let mut score = 0.0;
    let mut used = 0usize;
    for term in &fit.terms {
        let value = row.factors.get(term.factor_idx).copied().flatten()?;
        score += ((value - term.mean) / term.std) * term.weight;
        used += 1;
    }
    (used == fit.terms.len()).then_some(score).and_then(finite)
}

fn condition_passes(condition: &FitCondition, row: &FactorRow) -> bool {
    let value = if let Some(fit) = &condition.weighted {
        weighted_score_value(row, fit)
    } else {
        condition
            .factor_idx
            .and_then(|idx| row.factors.get(idx).copied().flatten())
    };
    pass_threshold(value, condition.side, condition.threshold)
}

fn fit_condition_detail(condition: &FitCondition) -> String {
    let side = match condition.side {
        ConditionSide::Low => "low",
        ConditionSide::High => "high",
        ConditionSide::HighAbs => "high_abs",
    };
    if let Some(fit) = &condition.weighted {
        let weights = fit
            .terms
            .iter()
            .map(|term| {
                format!(
                    "{}:w={},mean={},std={}",
                    term.factor_name,
                    fmt_float(term.weight, 4),
                    fmt_float(term.mean, 4),
                    fmt_float(term.std, 4)
                )
            })
            .collect::<Vec<_>>()
            .join("|");
        format!(
            "{}:{side}@{} train_weighted_terms=[{}]",
            fit.score_id,
            fmt_float(condition.threshold, 6),
            weights
        )
    } else {
        format!(
            "{}:{side}@{}",
            condition.label,
            fmt_float(condition.threshold, 6)
        )
    }
}

fn debounce_gate(raw: &[bool], on_minutes: usize, off_minutes: usize) -> Vec<bool> {
    let on_minutes = on_minutes.max(1);
    let off_minutes = off_minutes.max(1);
    let mut out = Vec::with_capacity(raw.len());
    let mut active = false;
    let mut true_run = 0usize;
    let mut false_run = 0usize;
    for &value in raw {
        if value {
            true_run += 1;
            false_run = 0;
        } else {
            false_run += 1;
            true_run = 0;
        }
        if !active && true_run >= on_minutes {
            active = true;
        }
        if active && false_run >= off_minutes {
            active = false;
        }
        out.push(active);
    }
    out
}

fn count_debounced_starts(rows: &[SignalRow]) -> usize {
    let mut count = 0usize;
    let mut prev = false;
    for row in rows {
        if row.gate_selected && !prev {
            count += 1;
        }
        prev = row.gate_selected;
    }
    count
}

#[allow(clippy::too_many_arguments)]
fn simulate_base_trades_for_config(
    config: &V8Config,
    rows: &[SignalRow],
    spec: &CandidateSpec,
    fold: &FoldDef,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    thresholds: &str,
    base_trade_number: &mut usize,
    entry_skips: &mut usize,
) -> Vec<BaseTrade> {
    let mut out = Vec::new();
    let mut idx = 0usize;
    let mut prev_selected = false;
    while idx + 1 < rows.len() {
        let row = &rows[idx];
        if row.gate_selected && !prev_selected {
            let entry_idx = idx + 1;
            if rows[entry_idx]
                .timestamp_us
                .saturating_sub(row.timestamp_us)
                > MINUTE_US
            {
                *entry_skips += 1;
                idx += 1;
                prev_selected = row.gate_selected;
                continue;
            }
            *base_trade_number += 1;
            if let Some(trade) = simulate_base_episode(
                config,
                rows,
                spec,
                fold,
                entry_idx,
                idx,
                tp_bps,
                sl_bps,
                timeout_minutes,
                *base_trade_number,
                thresholds,
            ) {
                idx = trade_exit_index(rows, trade.exit_timestamp_us)
                    .unwrap_or(entry_idx)
                    .saturating_add(config.cooldown_minutes);
                out.push(trade);
                prev_selected = false;
                continue;
            }
            *entry_skips += 1;
        }
        prev_selected = row.gate_selected;
        idx += 1;
    }
    out
}

fn trade_exit_index(rows: &[SignalRow], exit_ts: u64) -> Option<usize> {
    rows.iter().position(|row| row.timestamp_us == exit_ts)
}

#[allow(clippy::too_many_arguments)]
fn simulate_base_episode(
    config: &V8Config,
    rows: &[SignalRow],
    spec: &CandidateSpec,
    fold: &FoldDef,
    entry_idx: usize,
    signal_idx: usize,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    base_trade_number: usize,
    thresholds: &str,
) -> Option<BaseTrade> {
    let entry = &rows[entry_idx];
    let mut entry_price = entry.open.filter(|value| valid_price(*value));
    let entry_price_fallback = entry_price.is_none();
    if entry_price.is_none() {
        entry_price = entry.close.filter(|value| valid_price(*value));
    }
    let entry_price = entry_price?;
    let tp_price = entry_price * (1.0 + tp_bps as f64 / 10_000.0);
    let sl_price = entry_price * (1.0 - sl_bps as f64 / 10_000.0);

    let mut max_high = entry_price;
    let mut min_low = entry_price;
    let mut fallback_bar_count = u32::from(entry_price_fallback);
    let mut same_bar_ambiguous = false;
    let mut exit_idx = entry_idx;
    let mut exit_price = entry_price;
    let mut exit_reason = "fold_end";
    let mut prev_idx = entry_idx;

    for idx in entry_idx..rows.len() {
        let row = &rows[idx];
        if idx > entry_idx {
            let prev_ts = rows[prev_idx].timestamp_us;
            if row.timestamp_us.saturating_sub(prev_ts) > MINUTE_US {
                let prev = &rows[prev_idx];
                exit_idx = prev_idx;
                exit_price = prev
                    .close
                    .filter(|value| valid_price(*value))
                    .or(prev.open.filter(|value| valid_price(*value)))
                    .unwrap_or(entry_price);
                exit_reason = "data_gap";
                break;
            }
        }

        let open_price = row.open;
        let close_price = row.close;
        let (high_price, high_fallback) = fallback_bar_value(row.high, close_price, open_price);
        let (low_price, low_fallback) = fallback_bar_value(row.low, close_price, open_price);
        if high_fallback || low_fallback {
            fallback_bar_count += 1;
        }
        if let Some(high) = high_price.filter(|value| valid_price(*value)) {
            max_high = max_high.max(high);
        }
        if let Some(low) = low_price.filter(|value| valid_price(*value)) {
            min_low = min_low.min(low);
        }

        let hit_tp = high_price.is_some_and(|high| high >= tp_price);
        let hit_sl = low_price.is_some_and(|low| low <= sl_price);
        exit_idx = idx;
        if hit_tp && hit_sl {
            same_bar_ambiguous = true;
            exit_price = sl_price;
            exit_reason = "stop_loss_ambiguous";
            break;
        }
        if hit_sl {
            exit_price = sl_price;
            exit_reason = "stop_loss";
            break;
        }
        if hit_tp {
            exit_price = tp_price;
            exit_reason = "take_profit";
            break;
        }
        let held_minutes = row.timestamp_us.saturating_sub(entry.timestamp_us) / MINUTE_US;
        if held_minutes >= config.min_hold_minutes as u64 && !row.gate_selected {
            exit_price = close_price
                .filter(|value| valid_price(*value))
                .or(open_price.filter(|value| valid_price(*value)))
                .unwrap_or(entry_price);
            exit_reason = "gate_off";
            break;
        }
        if held_minutes >= timeout_minutes as u64 {
            exit_price = close_price
                .filter(|value| valid_price(*value))
                .or(open_price.filter(|value| valid_price(*value)))
                .unwrap_or(entry_price);
            exit_reason = "timeout";
            break;
        }
        prev_idx = idx;
    }

    let exit = &rows[exit_idx];
    let gross_bps = (exit_price / entry_price - 1.0) * 10_000.0;
    let duration_minutes =
        (exit.timestamp_us.saturating_sub(entry.timestamp_us) as f64 / MINUTE_US as f64).max(1.0);
    Some(BaseTrade {
        base_trade_number,
        fold: fold.name.to_string(),
        candidate_group: spec.candidate_group.to_string(),
        candidate_id: spec.candidate_id.to_string(),
        candidate_name: spec.candidate_name.to_string(),
        gate_expression: spec.description.to_string(),
        symbol: entry.symbol.clone(),
        tp_bps,
        sl_bps,
        timeout_minutes,
        signal_timestamp_utc: rows[signal_idx].timestamp_utc.clone(),
        signal_timestamp_us: rows[signal_idx].timestamp_us,
        entry_timestamp_utc: entry.timestamp_utc.clone(),
        entry_timestamp_us: entry.timestamp_us,
        exit_timestamp_utc: exit.timestamp_utc.clone(),
        exit_timestamp_us: exit.timestamp_us,
        entry_price,
        exit_price,
        exit_reason: exit_reason.to_string(),
        gross_bps,
        duration_minutes,
        mfe_bps: (max_high / entry_price - 1.0) * 10_000.0,
        mae_bps: (min_low / entry_price - 1.0) * 10_000.0,
        same_bar_ambiguous,
        fallback_bar_count,
        entry_price_fallback,
        entry_spread_bps: entry.spread_bps,
        entry_depth_bid_25: entry.depth_bid_25,
        entry_depth_ask_25: entry.depth_ask_25,
        thresholds_fit_on_train: thresholds.to_string(),
    })
}

fn fallback_bar_value(
    primary: Option<f64>,
    close: Option<f64>,
    open: Option<f64>,
) -> (Option<f64>, bool) {
    if primary.is_some_and(valid_price) {
        return (primary, false);
    }
    if close.is_some_and(valid_price) {
        return (close, true);
    }
    if open.is_some_and(valid_price) {
        return (open, true);
    }
    (None, true)
}

fn valid_price(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn expand_execution_trade(
    base: &BaseTrade,
    execution_model: &str,
    run_tag: &str,
    out_tag: &str,
    notional_quote: f64,
    fee_bps: f64,
) -> TradeRow {
    let (cost_bps, participation, depth_missing) = execution_cost_bps(
        execution_model,
        base.entry_spread_bps,
        base.entry_depth_bid_25,
        base.entry_depth_ask_25,
        notional_quote,
        fee_bps,
    );
    let net_bps = base.gross_bps - cost_bps;
    let pnl_quote = notional_quote * net_bps / 10_000.0;
    TradeRow {
        trade_id: format!(
            "{}|{}|{}|{}|tp{}|sl{}|to{}|{}",
            out_tag,
            base.fold,
            base.candidate_id,
            execution_model,
            base.tp_bps,
            base.sl_bps,
            base.timeout_minutes,
            base.base_trade_number
        ),
        run_tag: run_tag.to_string(),
        out_tag: out_tag.to_string(),
        fold: base.fold.clone(),
        candidate_group: base.candidate_group.clone(),
        candidate_id: base.candidate_id.clone(),
        candidate_name: base.candidate_name.clone(),
        gate_expression: base.gate_expression.clone(),
        symbol: base.symbol.clone(),
        execution_model: execution_model.to_string(),
        notional_quote,
        tp_bps: base.tp_bps,
        sl_bps: base.sl_bps,
        timeout_minutes: base.timeout_minutes,
        signal_timestamp_utc: base.signal_timestamp_utc.clone(),
        signal_timestamp_us: base.signal_timestamp_us,
        entry_timestamp_utc: base.entry_timestamp_utc.clone(),
        entry_timestamp_us: base.entry_timestamp_us,
        exit_timestamp_utc: base.exit_timestamp_utc.clone(),
        exit_timestamp_us: base.exit_timestamp_us,
        entry_price: base.entry_price,
        exit_price: base.exit_price,
        exit_reason: base.exit_reason.clone(),
        gross_bps: base.gross_bps,
        cost_bps,
        net_bps,
        pnl_quote,
        duration_minutes: base.duration_minutes,
        mfe_bps: base.mfe_bps,
        mae_bps: base.mae_bps,
        same_bar_ambiguous: base.same_bar_ambiguous,
        fallback_bar_count: base.fallback_bar_count,
        entry_price_fallback: base.entry_price_fallback,
        depth_missing_for_cost: depth_missing,
        entry_participation_depth25: participation,
        thresholds_fit_on_train: base.thresholds_fit_on_train.clone(),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn execution_cost_bps(
    execution_model: &str,
    spread_bps: Option<f64>,
    depth_bid_25: Option<f64>,
    depth_ask_25: Option<f64>,
    notional_quote: f64,
    fee_bps: f64,
) -> (f64, Option<f64>, bool) {
    match execution_model {
        "mid_research" => (0.0, Some(0.0), false),
        "maker_light" => (fee_bps, Some(0.0), false),
        "taker_spread" | "wide_stress" => {
            let spread = spread_bps.and_then(finite).unwrap_or(0.0).max(0.0);
            let depth = match (depth_bid_25.and_then(finite), depth_ask_25.and_then(finite)) {
                (Some(bid), Some(ask)) if bid > 0.0 && ask > 0.0 => Some(bid.min(ask)),
                _ => None,
            };
            let depth_missing = depth.is_none();
            let participation = depth.map(|value| notional_quote / value);
            if execution_model == "taker_spread" {
                let slip = participation
                    .map(|part| (spread * part).min(20.0))
                    .unwrap_or(20.0);
                (spread + fee_bps + slip, participation, depth_missing)
            } else {
                let slip = participation
                    .map(|part| (spread * 2.0 * part).min(50.0))
                    .unwrap_or(50.0);
                (spread * 1.5 + fee_bps + slip, participation, depth_missing)
            }
        }
        _ => (f64::NAN, None, true),
    }
}

fn aggregate_daily(trades: &[TradeRow], configs: &[ConfigRow]) -> Vec<DailyRow> {
    let mut by_key_date: HashMap<(ConfigKey, String), Vec<&TradeRow>> = HashMap::new();
    for trade in trades {
        let key = ConfigKey {
            fold: trade.fold.clone(),
            candidate_group: trade.candidate_group.clone(),
            candidate_id: trade.candidate_id.clone(),
            candidate_name: trade.candidate_name.clone(),
            symbol: trade.symbol.clone(),
            execution_model: trade.execution_model.clone(),
            tp_bps: trade.tp_bps,
            sl_bps: trade.sl_bps,
            timeout_minutes: trade.timeout_minutes,
        };
        by_key_date
            .entry((key, date_part(&trade.exit_timestamp_utc)))
            .or_default()
            .push(trade);
    }
    let mut out = Vec::new();
    for config in configs {
        for date in &config.validation_dates {
            let rows = by_key_date
                .get(&(config.key.clone(), date.clone()))
                .cloned()
                .unwrap_or_default();
            let pnl = rows.iter().map(|trade| trade.pnl_quote).collect::<Vec<_>>();
            let trade_count = rows.len();
            out.push(DailyRow {
                fold: config.key.fold.clone(),
                date: date.clone(),
                candidate_group: config.key.candidate_group.clone(),
                candidate_id: config.key.candidate_id.clone(),
                candidate_name: config.key.candidate_name.clone(),
                symbol: config.key.symbol.clone(),
                execution_model: config.key.execution_model.clone(),
                tp_bps: config.key.tp_bps,
                sl_bps: config.key.sl_bps,
                timeout_minutes: config.key.timeout_minutes,
                notional_quote: config.notional_quote,
                trade_count,
                total_pnl_quote: pnl.iter().sum(),
                return_bps_on_100: pnl.iter().sum::<f64>() / config.notional_quote * 10_000.0,
                win_rate: if trade_count == 0 {
                    0.0
                } else {
                    pnl.iter().filter(|value| **value > 0.0).count() as f64 / trade_count as f64
                },
                max_intraday_drawdown_quote: max_drawdown(&pnl),
                exposure_minutes: rows.iter().map(|trade| trade.duration_minutes).sum(),
                turnover_quote: trade_count as f64 * config.notional_quote,
                best_trade_pnl_quote: pnl.iter().copied().reduce(f64::max).unwrap_or(0.0),
                worst_trade_pnl_quote: pnl.iter().copied().reduce(f64::min).unwrap_or(0.0),
                guardrail: GUARDRAIL.to_string(),
            });
        }
    }
    out.sort_by(|a, b| {
        a.fold
            .cmp(&b.fold)
            .then_with(|| a.date.cmp(&b.date))
            .then_with(|| a.candidate_id.cmp(&b.candidate_id))
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.execution_model.cmp(&b.execution_model))
    });
    out
}

fn aggregate_summary(trades: &[TradeRow], daily: &[DailyRow]) -> Vec<SummaryRow> {
    let mut by_fold: HashMap<ConfigKey, Vec<&DailyRow>> = HashMap::new();
    for row in daily {
        by_fold.entry(daily_key(row)).or_default().push(row);
    }
    let mut out = Vec::new();
    for (key, days) in by_fold {
        let trade_rows = trades
            .iter()
            .filter(|trade| {
                trade.fold == key.fold
                    && trade.candidate_id == key.candidate_id
                    && trade.symbol == key.symbol
                    && trade.execution_model == key.execution_model
                    && trade.tp_bps == key.tp_bps
                    && trade.sl_bps == key.sl_bps
                    && trade.timeout_minutes == key.timeout_minutes
            })
            .collect::<Vec<_>>();
        out.push(summarize_group("fold", &key.fold, &key, &days, &trade_rows));
    }

    let mut by_all: HashMap<AllKey, Vec<&DailyRow>> = HashMap::new();
    for row in daily {
        by_all.entry(all_key(row)).or_default().push(row);
    }
    for (key, days) in by_all {
        let trade_rows = trades
            .iter()
            .filter(|trade| {
                trade.candidate_id == key.candidate_id
                    && trade.symbol == key.symbol
                    && trade.execution_model == key.execution_model
                    && trade.tp_bps == key.tp_bps
                    && trade.sl_bps == key.sl_bps
                    && trade.timeout_minutes == key.timeout_minutes
            })
            .collect::<Vec<_>>();
        let config_key = ConfigKey {
            fold: "all".to_string(),
            candidate_group: key.candidate_group,
            candidate_id: key.candidate_id,
            candidate_name: key.candidate_name,
            symbol: key.symbol,
            execution_model: key.execution_model,
            tp_bps: key.tp_bps,
            sl_bps: key.sl_bps,
            timeout_minutes: key.timeout_minutes,
        };
        out.push(summarize_group(
            "all",
            "all",
            &config_key,
            &days,
            &trade_rows,
        ));
    }
    out.sort_by(|a, b| {
        b.total_pnl_quote
            .total_cmp(&a.total_pnl_quote)
            .then_with(|| a.execution_model.cmp(&b.execution_model))
    });
    out
}

fn summarize_group(
    scope: &str,
    fold: &str,
    key: &ConfigKey,
    days: &[&DailyRow],
    trades: &[&TradeRow],
) -> SummaryRow {
    let daily_pnl = days
        .iter()
        .map(|row| row.total_pnl_quote)
        .collect::<Vec<_>>();
    let trade_pnl = trades.iter().map(|row| row.pnl_quote).collect::<Vec<_>>();
    let trade_net = trades.iter().map(|row| row.net_bps).collect::<Vec<_>>();
    let trade_gross = trades.iter().map(|row| row.gross_bps).collect::<Vec<_>>();
    let trade_cost = trades.iter().map(|row| row.cost_bps).collect::<Vec<_>>();
    let durations = trades
        .iter()
        .map(|row| row.duration_minutes)
        .collect::<Vec<_>>();
    let total_pnl = daily_pnl.iter().sum::<f64>();
    let trade_count = trades.len();
    let days_count = days.len();
    let exit_counts = exit_reason_counts_json(trades);
    SummaryRow {
        summary_scope: scope.to_string(),
        fold: fold.to_string(),
        candidate_group: key.candidate_group.clone(),
        candidate_id: key.candidate_id.clone(),
        candidate_name: key.candidate_name.clone(),
        symbol: key.symbol.clone(),
        execution_model: key.execution_model.clone(),
        tp_bps: key.tp_bps,
        sl_bps: key.sl_bps,
        timeout_minutes: key.timeout_minutes,
        notional_quote: days
            .first()
            .map(|row| row.notional_quote)
            .unwrap_or(ACCOUNT_QUOTE),
        days: days_count,
        trade_count,
        total_pnl_quote: total_pnl,
        total_return_bps_on_100: total_pnl / ACCOUNT_QUOTE * 10_000.0,
        avg_daily_pnl_quote: if days_count == 0 {
            0.0
        } else {
            total_pnl / days_count as f64
        },
        median_daily_pnl_quote: median(&daily_pnl).unwrap_or(0.0),
        avg_daily_return_bps_on_100: if days_count == 0 {
            0.0
        } else {
            total_pnl / days_count as f64 / ACCOUNT_QUOTE * 10_000.0
        },
        positive_day_rate: if days_count == 0 {
            0.0
        } else {
            daily_pnl.iter().filter(|value| **value > 0.0).count() as f64 / days_count as f64
        },
        max_drawdown_quote: max_drawdown(&daily_pnl),
        trades_per_day: if days_count == 0 {
            0.0
        } else {
            trade_count as f64 / days_count as f64
        },
        win_rate: if trade_count == 0 {
            0.0
        } else {
            trade_pnl.iter().filter(|value| **value > 0.0).count() as f64 / trade_count as f64
        },
        profit_factor: profit_factor(&trade_pnl),
        median_trade_net_bps: median(&trade_net),
        p25_trade_net_bps: quantile_opt(&trade_net, 0.25),
        p75_trade_net_bps: quantile_opt(&trade_net, 0.75),
        avg_gross_bps: mean(&trade_gross),
        avg_cost_bps: mean(&trade_cost),
        avg_net_bps: mean(&trade_net),
        median_duration_minutes: median(&durations),
        exposure_minutes: days.iter().map(|row| row.exposure_minutes).sum(),
        turnover_quote: days.iter().map(|row| row.turnover_quote).sum(),
        target_frequency_pass: {
            let tpd = if days_count == 0 {
                0.0
            } else {
                trade_count as f64 / days_count as f64
            };
            (1.0..=5.0).contains(&tpd)
        },
        ambiguous_trade_count: trades.iter().filter(|row| row.same_bar_ambiguous).count(),
        ambiguous_trade_rate: if trade_count == 0 {
            0.0
        } else {
            trades.iter().filter(|row| row.same_bar_ambiguous).count() as f64 / trade_count as f64
        },
        exit_reason_counts_json: exit_counts,
        guardrail: GUARDRAIL.to_string(),
    }
}

fn daily_key(row: &DailyRow) -> ConfigKey {
    ConfigKey {
        fold: row.fold.clone(),
        candidate_group: row.candidate_group.clone(),
        candidate_id: row.candidate_id.clone(),
        candidate_name: row.candidate_name.clone(),
        symbol: row.symbol.clone(),
        execution_model: row.execution_model.clone(),
        tp_bps: row.tp_bps,
        sl_bps: row.sl_bps,
        timeout_minutes: row.timeout_minutes,
    }
}

fn all_key(row: &DailyRow) -> AllKey {
    AllKey {
        candidate_group: row.candidate_group.clone(),
        candidate_id: row.candidate_id.clone(),
        candidate_name: row.candidate_name.clone(),
        symbol: row.symbol.clone(),
        execution_model: row.execution_model.clone(),
        tp_bps: row.tp_bps,
        sl_bps: row.sl_bps,
        timeout_minutes: row.timeout_minutes,
    }
}

fn build_exit_reasons(trades: &[TradeRow]) -> Vec<ExitReasonRow> {
    let mut by_key: HashMap<
        (String, String, String, String, u32, u32, u32, String),
        Vec<&TradeRow>,
    > = HashMap::new();
    for trade in trades {
        by_key
            .entry((
                trade.fold.clone(),
                trade.candidate_id.clone(),
                trade.symbol.clone(),
                trade.execution_model.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_minutes,
                trade.exit_reason.clone(),
            ))
            .or_default()
            .push(trade);
        by_key
            .entry((
                "all".to_string(),
                trade.candidate_id.clone(),
                trade.symbol.clone(),
                trade.execution_model.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_minutes,
                trade.exit_reason.clone(),
            ))
            .or_default()
            .push(trade);
    }
    let mut out = by_key
        .into_iter()
        .map(
            |(
                (fold, candidate_id, symbol, execution_model, tp, sl, timeout, exit_reason),
                rows,
            )| {
                let pnl = rows.iter().map(|row| row.pnl_quote).sum::<f64>();
                let net = rows.iter().map(|row| row.net_bps).collect::<Vec<_>>();
                ExitReasonRow {
                    summary_scope: if fold == "all" { "all" } else { "fold" }.to_string(),
                    fold,
                    candidate_id,
                    symbol,
                    execution_model,
                    tp_bps: tp,
                    sl_bps: sl,
                    timeout_minutes: timeout,
                    exit_reason,
                    trade_count: rows.len(),
                    pnl_quote: pnl,
                    avg_net_bps: mean(&net),
                }
            },
        )
        .collect::<Vec<_>>();
    out.sort_by(|a, b| {
        a.candidate_id
            .cmp(&b.candidate_id)
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.execution_model.cmp(&b.execution_model))
            .then_with(|| a.fold.cmp(&b.fold))
            .then_with(|| a.exit_reason.cmp(&b.exit_reason))
    });
    out
}

fn build_fold_stability(summary: &[SummaryRow]) -> Vec<FoldStabilityRow> {
    let mut by_key: HashMap<
        (String, String, String, String, u32, u32, u32),
        HashMap<String, &SummaryRow>,
    > = HashMap::new();
    for row in summary.iter().filter(|row| row.summary_scope == "fold") {
        by_key
            .entry((
                row.candidate_id.clone(),
                row.candidate_name.clone(),
                row.symbol.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
            ))
            .or_default()
            .insert(row.fold.clone(), row);
    }
    let mut out = Vec::new();
    for ((candidate_id, candidate_name, symbol, execution_model, tp, sl, timeout), folds) in by_key
    {
        let fold2 = folds.get("fold2").copied();
        let fold3 = folds.get("fold3").copied();
        let f2_pnl = fold2.map(|row| row.total_pnl_quote);
        let f3_pnl = fold3.map(|row| row.total_pnl_quote);
        let stable = f2_pnl.unwrap_or(f64::NEG_INFINITY) >= 0.0
            && f3_pnl.unwrap_or(f64::NEG_INFINITY) >= 0.0;
        out.push(FoldStabilityRow {
            candidate_id,
            candidate_name,
            symbol,
            execution_model,
            tp_bps: tp,
            sl_bps: sl,
            timeout_minutes: timeout,
            fold2_pnl_quote: f2_pnl,
            fold3_pnl_quote: f3_pnl,
            fold2_trades_per_day: fold2.map(|row| row.trades_per_day),
            fold3_trades_per_day: fold3.map(|row| row.trades_per_day),
            fold2_fold3_both_nonnegative: stable,
            stability_read: if stable {
                "fold2_and_fold3_nonnegative"
            } else {
                "unstable_or_negative_fold"
            }
            .to_string(),
        });
    }
    out.sort_by(|a, b| {
        b.fold2_fold3_both_nonnegative
            .cmp(&a.fold2_fold3_both_nonnegative)
            .then_with(|| a.candidate_id.cmp(&b.candidate_id))
    });
    out
}

fn build_non_overlap(trades: &[TradeRow], summary: &[SummaryRow]) -> Vec<NonOverlapRow> {
    let mut out = Vec::new();
    for row in summary.iter().filter(|row| row.summary_scope == "all") {
        let selected = trades
            .iter()
            .filter(|trade| {
                trade.candidate_id == row.candidate_id
                    && trade.symbol == row.symbol
                    && trade.execution_model == row.execution_model
                    && trade.tp_bps == row.tp_bps
                    && trade.sl_bps == row.sl_bps
                    && trade.timeout_minutes == row.timeout_minutes
            })
            .collect::<Vec<_>>();
        out.push(NonOverlapRow {
            candidate_id: row.candidate_id.clone(),
            symbol: row.symbol.clone(),
            execution_model: row.execution_model.clone(),
            tp_bps: row.tp_bps,
            sl_bps: row.sl_bps,
            timeout_minutes: row.timeout_minutes,
            trade_count: selected.len(),
            total_pnl_quote: selected.iter().map(|trade| trade.pnl_quote).sum(),
            overlapping_trade_pairs: count_overlaps(&selected),
            non_overlap_mode: "sequential_single_position_with_cooldown".to_string(),
        });
    }
    out
}

fn count_overlaps(trades: &[&TradeRow]) -> usize {
    let mut sorted = trades.to_vec();
    sorted.sort_by_key(|trade| trade.entry_timestamp_us);
    let mut overlaps = 0usize;
    for pair in sorted.windows(2) {
        if pair[1].entry_timestamp_us < pair[0].exit_timestamp_us {
            overlaps += 1;
        }
    }
    overlaps
}

fn build_parameter_sensitivity(summary: &[SummaryRow]) -> Vec<ParameterSensitivityRow> {
    let mut by_key: HashMap<(String, String, String, String), Vec<&SummaryRow>> = HashMap::new();
    for row in summary.iter().filter(|row| row.summary_scope == "all") {
        by_key
            .entry((
                row.candidate_id.clone(),
                row.candidate_name.clone(),
                row.symbol.clone(),
                row.execution_model.clone(),
            ))
            .or_default()
            .push(row);
    }
    let mut out = Vec::new();
    for ((candidate_id, candidate_name, symbol, execution_model), rows) in by_key {
        let pnls = rows
            .iter()
            .map(|row| row.total_pnl_quote)
            .collect::<Vec<_>>();
        let best = pnls.iter().copied().reduce(f64::max).unwrap_or(0.0);
        let worst = pnls.iter().copied().reduce(f64::min).unwrap_or(0.0);
        let best_tpd = rows
            .iter()
            .max_by(|a, b| a.total_pnl_quote.total_cmp(&b.total_pnl_quote))
            .map(|row| row.trades_per_day)
            .unwrap_or(0.0);
        let positive_rate = if pnls.is_empty() {
            0.0
        } else {
            pnls.iter().filter(|value| **value > 0.0).count() as f64 / pnls.len() as f64
        };
        out.push(ParameterSensitivityRow {
            candidate_id,
            candidate_name,
            symbol,
            execution_model,
            config_count: rows.len(),
            best_total_pnl_quote: best,
            median_total_pnl_quote: median(&pnls).unwrap_or(0.0),
            worst_total_pnl_quote: worst,
            positive_config_rate: positive_rate,
            best_trades_per_day: best_tpd,
            pnl_range_quote: best - worst,
            sensitivity_read: if positive_rate >= 0.5 {
                "less_parameter_fragile"
            } else {
                "parameter_fragile"
            }
            .to_string(),
        });
    }
    out.sort_by(|a, b| b.best_total_pnl_quote.total_cmp(&a.best_total_pnl_quote));
    out
}

fn build_single_day_dependence(daily: &[DailyRow]) -> Vec<SingleDayDependenceRow> {
    let mut by_key: HashMap<(String, String, String, u32, u32, u32), Vec<&DailyRow>> =
        HashMap::new();
    for row in daily {
        by_key
            .entry((
                row.candidate_id.clone(),
                row.symbol.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
            ))
            .or_default()
            .push(row);
    }
    let mut out = Vec::new();
    for ((candidate_id, symbol, execution_model, tp, sl, timeout), rows) in by_key {
        let total = rows.iter().map(|row| row.total_pnl_quote).sum::<f64>();
        let abs_total = rows
            .iter()
            .map(|row| row.total_pnl_quote.abs())
            .sum::<f64>()
            .max(1e-9);
        let best = rows
            .iter()
            .max_by(|a, b| a.total_pnl_quote.total_cmp(&b.total_pnl_quote));
        if let Some(best) = best {
            let share = best.total_pnl_quote.abs() / abs_total;
            out.push(SingleDayDependenceRow {
                candidate_id,
                symbol,
                execution_model,
                tp_bps: tp,
                sl_bps: sl,
                timeout_minutes: timeout,
                total_pnl_quote: total,
                best_day: best.date.clone(),
                best_day_pnl_quote: best.total_pnl_quote,
                best_day_share_of_abs_pnl: share,
                positive_days: rows.iter().filter(|row| row.total_pnl_quote > 0.0).count(),
                dependence_read: if share > 0.65 {
                    "single_day_dependent"
                } else {
                    "not_single_day_dominated"
                }
                .to_string(),
            });
        }
    }
    out.sort_by(|a, b| {
        b.best_day_share_of_abs_pnl
            .total_cmp(&a.best_day_share_of_abs_pnl)
    });
    out
}

fn build_failure_diagnostics(
    summary: &[SummaryRow],
    stability: &[FoldStabilityRow],
) -> Vec<FailureDiagnosticRow> {
    let stable_keys = stability
        .iter()
        .filter(|row| row.fold2_fold3_both_nonnegative)
        .map(|row| {
            (
                row.candidate_id.clone(),
                row.symbol.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
            )
        })
        .collect::<HashSet<_>>();
    let mut out = Vec::new();
    for row in summary.iter().filter(|row| row.summary_scope == "all") {
        let stable = stable_keys.contains(&(
            row.candidate_id.clone(),
            row.symbol.clone(),
            row.execution_model.clone(),
            row.tp_bps,
            row.sl_bps,
            row.timeout_minutes,
        ));
        let primary_failure = if !row.target_frequency_pass {
            "frequency_outside_1_to_5_per_day"
        } else if row.total_pnl_quote < 0.0 && row.execution_model != "mid_research" {
            "negative_after_cost"
        } else if !stable && matches!(row.execution_model.as_str(), "maker_light" | "taker_spread")
        {
            "fold2_fold3_instability"
        } else if row.max_drawdown_quote > row.total_pnl_quote.abs().max(1.0) {
            "drawdown_dominates"
        } else {
            "passed_basic_diagnostics"
        };
        out.push(FailureDiagnosticRow {
            candidate_id: row.candidate_id.clone(),
            candidate_name: row.candidate_name.clone(),
            symbol: row.symbol.clone(),
            execution_model: row.execution_model.clone(),
            tp_bps: row.tp_bps,
            sl_bps: row.sl_bps,
            timeout_minutes: row.timeout_minutes,
            total_pnl_quote: row.total_pnl_quote,
            trades_per_day: row.trades_per_day,
            max_drawdown_quote: row.max_drawdown_quote,
            fold2_fold3_stable: stable,
            target_frequency_pass: row.target_frequency_pass,
            primary_failure: primary_failure.to_string(),
            diagnostic_detail: format!(
                "pf={} win={} exits={}",
                fmt_opt(row.profit_factor, 3),
                fmt_float(row.win_rate, 3),
                row.exit_reason_counts_json
            ),
        });
    }
    out.sort_by(|a, b| {
        a.primary_failure
            .cmp(&b.primary_failure)
            .then_with(|| b.total_pnl_quote.total_cmp(&a.total_pnl_quote))
    });
    out
}

fn validate_outputs(trades: &[TradeRow], daily: &[DailyRow]) -> ValidationChecks {
    let mut ids = HashSet::new();
    let mut duplicate_trade_ids = 0usize;
    for trade in trades {
        if !ids.insert(trade.trade_id.clone()) {
            duplicate_trade_ids += 1;
        }
    }
    let missing_exit_reason = trades
        .iter()
        .filter(|trade| trade.exit_reason.trim().is_empty())
        .count();
    let daily_total = daily.iter().map(|row| row.total_pnl_quote).sum::<f64>();
    let trade_total = trades.iter().map(|row| row.pnl_quote).sum::<f64>();
    let daily_trade_pnl_abs_diff = (daily_total - trade_total).abs();
    let non_overlap_violations = {
        let mut by_key: HashMap<(String, String, String, String, u32, u32, u32), Vec<&TradeRow>> =
            HashMap::new();
        for trade in trades {
            by_key
                .entry((
                    trade.fold.clone(),
                    trade.candidate_id.clone(),
                    trade.symbol.clone(),
                    trade.execution_model.clone(),
                    trade.tp_bps,
                    trade.sl_bps,
                    trade.timeout_minutes,
                ))
                .or_default()
                .push(trade);
        }
        by_key
            .values()
            .map(|rows| count_overlaps(rows))
            .sum::<usize>()
    };
    let cost_monotonic_violations = count_cost_monotonic_violations(trades);
    let primary_exec_rows = trades
        .iter()
        .filter(|trade| {
            matches!(
                trade.execution_model.as_str(),
                "maker_light" | "taker_spread"
            )
        })
        .count();
    ValidationChecks {
        duplicate_trade_ids,
        missing_exit_reason,
        daily_trade_pnl_abs_diff,
        non_overlap_violations,
        cost_monotonic_violations,
        primary_exec_rows,
        passed: duplicate_trade_ids == 0
            && missing_exit_reason == 0
            && daily_trade_pnl_abs_diff < 1e-6
            && non_overlap_violations == 0
            && cost_monotonic_violations == 0
            && primary_exec_rows > 0,
    }
}

fn count_cost_monotonic_violations(trades: &[TradeRow]) -> usize {
    let mut by_base: HashMap<String, HashMap<String, f64>> = HashMap::new();
    for trade in trades {
        let base = trade
            .trade_id
            .rsplit_once('|')
            .map(|(_, n)| n.to_string())
            .unwrap_or_else(|| trade.trade_id.clone());
        by_base
            .entry(format!(
                "{}|{}|{}|{}|{}|{}|{}",
                trade.fold,
                trade.candidate_id,
                trade.symbol,
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_minutes,
                base
            ))
            .or_default()
            .insert(trade.execution_model.clone(), trade.net_bps);
    }
    let mut violations = 0usize;
    for costs in by_base.values() {
        if let (Some(mid), Some(maker)) = (costs.get("mid_research"), costs.get("maker_light")) {
            if maker > &(mid + 1e-9) {
                violations += 1;
            }
        }
        if let (Some(maker), Some(taker)) = (costs.get("maker_light"), costs.get("taker_spread")) {
            if taker > &(maker + 1e-9) {
                violations += 1;
            }
        }
        if let (Some(taker), Some(wide)) = (costs.get("taker_spread"), costs.get("wide_stress")) {
            if wide > &(taker + 1e-9) {
                violations += 1;
            }
        }
    }
    violations
}

fn fit_tertiles(values: Vec<f64>) -> Option<(f64, f64)> {
    let mut values = values
        .into_iter()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    values.sort_by(|a, b| a.total_cmp(b));
    values.dedup_by(|a, b| a.total_cmp(b).is_eq());
    if values.len() < 3 {
        return None;
    }
    Some((quantile(&values, 1.0 / 3.0), quantile(&values, 2.0 / 3.0)))
}

fn fit_quantile(values: Vec<f64>, q: f64) -> Option<f64> {
    let mut values = values
        .into_iter()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    values.sort_by(|a, b| a.total_cmp(b));
    if values.len() < 3 {
        return None;
    }
    Some(quantile(&values, q.clamp(0.0, 1.0)))
}

fn quantile(values: &[f64], q: f64) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    if values.len() == 1 {
        return values[0];
    }
    let pos = q.clamp(0.0, 1.0) * (values.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    if lo == hi {
        values[lo]
    } else {
        let weight = pos - lo as f64;
        values[lo] * (1.0 - weight) + values[hi] * weight
    }
}

fn quantile_opt(values: &[f64], q: f64) -> Option<f64> {
    let mut values = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    values.sort_by(|a, b| a.total_cmp(b));
    (!values.is_empty()).then(|| quantile(&values, q))
}

fn mean(values: &[f64]) -> Option<f64> {
    let mut sum = 0.0;
    let mut count = 0usize;
    for value in values.iter().copied().filter(|value| value.is_finite()) {
        sum += value;
        count += 1;
    }
    (count > 0).then_some(sum / count as f64)
}

fn median(values: &[f64]) -> Option<f64> {
    quantile_opt(values, 0.5)
}

fn stddev(values: &[f64]) -> Option<f64> {
    let avg = mean(values)?;
    let vals = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if vals.len() < 2 {
        return None;
    }
    let var = vals
        .iter()
        .map(|value| {
            let d = value - avg;
            d * d
        })
        .sum::<f64>()
        / (vals.len() - 1) as f64;
    finite(var.sqrt())
}

fn corr(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 3 {
        return None;
    }
    let mean_x = mean(xs)?;
    let mean_y = mean(ys)?;
    let mut num = 0.0;
    let mut den_x = 0.0;
    let mut den_y = 0.0;
    let mut count = 0usize;
    for (&x, &y) in xs.iter().zip(ys.iter()) {
        if !x.is_finite() || !y.is_finite() {
            continue;
        }
        let dx = x - mean_x;
        let dy = y - mean_y;
        num += dx * dy;
        den_x += dx * dx;
        den_y += dy * dy;
        count += 1;
    }
    if count < 3 || den_x <= 0.0 || den_y <= 0.0 {
        return None;
    }
    finite(num / (den_x.sqrt() * den_y.sqrt()))
}

fn win_rate_bps(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    Some(values.iter().filter(|value| **value > 0.0).count() as f64 / values.len() as f64)
}

fn max_drawdown(values: &[f64]) -> f64 {
    let mut equity = 0.0;
    let mut peak = 0.0;
    let mut max_dd = 0.0;
    for value in values {
        equity += value;
        if equity > peak {
            peak = equity;
        }
        let dd = peak - equity;
        if dd > max_dd {
            max_dd = dd;
        }
    }
    max_dd
}

fn profit_factor(pnl: &[f64]) -> Option<f64> {
    let gains: f64 = pnl.iter().copied().filter(|value| *value > 0.0).sum();
    let losses: f64 = pnl
        .iter()
        .copied()
        .filter(|value| *value < 0.0)
        .map(f64::abs)
        .sum();
    if losses > 0.0 {
        finite(gains / losses)
    } else if gains > 0.0 {
        Some(f64::INFINITY)
    } else {
        None
    }
}

fn date_part(timestamp_utc: &str) -> String {
    timestamp_utc.get(..10).unwrap_or("unknown").to_string()
}

fn exit_reason_counts_json(trades: &[&TradeRow]) -> String {
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for trade in trades {
        *counts.entry(trade.exit_reason.clone()).or_default() += 1;
    }
    serde_json::to_string(&counts).unwrap_or_else(|_| "{}".to_string())
}

fn fmt_float(value: f64, digits: usize) -> String {
    if value.is_finite() {
        format!("{value:.digits$}")
    } else if value.is_infinite() && value.is_sign_positive() {
        "inf".to_string()
    } else if value.is_infinite() {
        "-inf".to_string()
    } else {
        "nan".to_string()
    }
}

fn fmt_opt(value: Option<f64>, digits: usize) -> String {
    value
        .map(|value| fmt_float(value, digits))
        .unwrap_or_else(|| "NA".to_string())
}

fn fmt_pct(value: f64) -> String {
    format!("{}%", fmt_float(value * 100.0, 1))
}

fn build_completion(
    config: &V8Config,
    paths: &Paths,
    defs: &[FactorDef],
    factor_rows: usize,
    factor_audit_rows: usize,
    outputs: &EpisodeOutputs,
    validation: &ValidationChecks,
) -> Completion {
    let mut out = BTreeMap::new();
    out.insert("manifest".to_string(), path_string(&paths.manifest));
    out.insert("checkpoint".to_string(), path_string(&paths.checkpoint));
    out.insert("factor_panel".to_string(), path_string(&paths.factor_panel));
    out.insert(
        "factor_catalog".to_string(),
        path_string(&paths.factor_catalog),
    );
    out.insert("factor_audit".to_string(), path_string(&paths.factor_audit));
    out.insert(
        "candidate_gates".to_string(),
        path_string(&paths.candidate_gates),
    );
    out.insert("trades".to_string(), path_string(&paths.trades));
    out.insert("daily".to_string(), path_string(&paths.daily));
    out.insert("summary".to_string(), path_string(&paths.summary));
    out.insert("exit_reasons".to_string(), path_string(&paths.exit_reasons));
    out.insert(
        "fold_stability".to_string(),
        path_string(&paths.fold_stability),
    );
    out.insert("non_overlap".to_string(), path_string(&paths.non_overlap));
    out.insert(
        "parameter_sensitivity".to_string(),
        path_string(&paths.parameter_sensitivity),
    );
    out.insert(
        "single_day_dependence".to_string(),
        path_string(&paths.single_day_dependence),
    );
    out.insert(
        "failure_diagnostics".to_string(),
        path_string(&paths.failure_diagnostics),
    );
    out.insert("completion".to_string(), path_string(&paths.completion));
    out.insert("report".to_string(), path_string(&config.report_md));
    Completion {
        run_name: "bonk_v8_profit_factor_factory".to_string(),
        generated_at_utc: iso_now(),
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        guardrail: GUARDRAIL.to_string(),
        config: CompletionConfig {
            tp_bps: config.tp_bps.clone(),
            sl_bps: config.sl_bps.clone(),
            timeout_minutes: config.timeout_minutes.clone(),
            execution_models: config.execution_models.clone(),
            notional_quote: config.notional_quote,
            fee_bps: config.fee_bps,
            debounce_on_minutes: config.debounce_on_minutes,
            debounce_off_minutes: config.debounce_off_minutes,
            cooldown_minutes: config.cooldown_minutes,
            min_hold_minutes: config.min_hold_minutes,
        },
        counts: CompletionCounts {
            factor_rows,
            factor_count: defs.len(),
            factor_audit_rows,
            candidate_fit_rows: outputs.candidate_fits.len(),
            trades: outputs.trades.len(),
            daily_rows: outputs.daily.len(),
            summary_rows: outputs.summary.len(),
        },
        outputs: out,
        validation: validation.clone(),
    }
}

fn build_report(
    config: &V8Config,
    paths: &Paths,
    defs: &[FactorDef],
    factor_rows: usize,
    factor_audit_rows: usize,
    outputs: &EpisodeOutputs,
    validation: &ValidationChecks,
) -> String {
    let mut lines = Vec::new();
    lines.push("# BONK V8 Profit-First Factor Factory".to_string());
    lines.push(String::new());
    lines.push(format!(
        "Status: {}. Run tag: `{}`. Output tag: `{}`.",
        iso_now(),
        config.run_tag,
        out_tag(config)
    ));
    lines.push(String::new());
    lines.push("Research infrastructure only: no trading advice, no execution recommendation, and no alpha claim.".to_string());
    lines.push(String::new());
    lines.push("## Scope".to_string());
    lines.push(String::new());
    lines.push(
        "- Used existing local BONK/Bullish/Binance derived data only; no new raw data pull."
            .to_string(),
    );
    lines.push("- Rust is the canonical path for the V8 factor panel, train-fitted gate thresholds/weights, executable episode labels, and after-cost backtest.".to_string());
    lines.push("- Exploratory symbolic patterns were distilled back into simple Rust gates under `exploratory_distilled` and rerun through the canonical episode backtest.".to_string());
    lines.push("- The objective is low-frequency `$100`-notional episodes after cost, not statistical significance.".to_string());
    lines.push(format!(
        "- Factor panel rows: `{factor_rows}`. Factor universe size: `{}`. Factor audit rows: `{factor_audit_rows}`.",
        defs.len()
    ));
    lines.push(format!(
        "- Episode trades: `{}`. Daily rows: `{}`. Summary rows: `{}`.",
        outputs.trades.len(),
        outputs.daily.len(),
        outputs.summary.len()
    ));
    lines.push(String::new());
    lines.push("## Resume Contract".to_string());
    lines.push(String::new());
    lines.push(format!("- Manifest: `{}`", path_string(&paths.manifest)));
    lines.push(format!(
        "- Checkpoint: `{}`",
        path_string(&paths.checkpoint)
    ));
    lines.push("- Steps are `factor_panel -> factor_audit -> episode_backtest -> report`; completed steps are skipped on resume when outputs still exist.".to_string());
    lines.push(String::new());
    lines.push("## Factor Families".to_string());
    lines.push(String::new());
    let mut families: BTreeMap<&str, usize> = BTreeMap::new();
    for def in defs {
        *families.entry(def.family).or_default() += 1;
    }
    for (family, count) in families {
        lines.push(format!("- `{family}`: `{count}` factors"));
    }
    lines.push(String::new());
    lines.push("## Primary Target-Frequency Candidate Ranking".to_string());
    lines.push(String::new());
    lines.push("| rank | execution | candidate | symbol | tp/sl/to | total $ | avg $/day | win | pf | tr/day | max DD | fold/freq read |".to_string());
    lines.push(
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
            .to_string(),
    );
    let mut primary = outputs
        .summary
        .iter()
        .filter(|row| row.summary_scope == "all")
        .filter(|row| matches!(row.execution_model.as_str(), "maker_light" | "taker_spread"))
        .filter(|row| row.target_frequency_pass)
        .collect::<Vec<_>>();
    if primary.is_empty() {
        primary = outputs
            .summary
            .iter()
            .filter(|row| row.summary_scope == "all")
            .filter(|row| matches!(row.execution_model.as_str(), "maker_light" | "taker_spread"))
            .collect::<Vec<_>>();
    }
    primary.sort_by(|a, b| {
        b.total_pnl_quote
            .total_cmp(&a.total_pnl_quote)
            .then_with(|| a.trades_per_day.total_cmp(&b.trades_per_day))
    });
    let stability = outputs
        .fold_stability
        .iter()
        .map(|row| {
            (
                row.candidate_id.clone(),
                row.symbol.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
                row.fold2_fold3_both_nonnegative,
            )
        })
        .collect::<HashSet<_>>();
    for (rank, row) in primary.iter().take(20).enumerate() {
        let stable = stability.contains(&(
            row.candidate_id.clone(),
            row.symbol.clone(),
            row.execution_model.clone(),
            row.tp_bps,
            row.sl_bps,
            row.timeout_minutes,
            true,
        ));
        let read = format!(
            "{}{}",
            if stable { "fold2/3 ok" } else { "fold2/3 weak" },
            if row.target_frequency_pass {
                ", target freq"
            } else {
                ", freq miss"
            }
        );
        lines.push(format!(
            "| {} | {} | `{}` | {} | {}/{}/{} | {} | {} | {} | {} | {} | {} | {} |",
            rank + 1,
            row.execution_model,
            row.candidate_id,
            row.symbol,
            row.tp_bps,
            row.sl_bps,
            row.timeout_minutes,
            fmt_float(row.total_pnl_quote, 4),
            fmt_float(row.avg_daily_pnl_quote, 4),
            fmt_pct(row.win_rate),
            fmt_opt(row.profit_factor, 2),
            fmt_float(row.trades_per_day, 2),
            fmt_float(row.max_drawdown_quote, 4),
            read
        ));
    }
    lines.push(String::new());
    lines.push("## Upper Bound And Stress".to_string());
    lines.push(String::new());
    lines.push("- `mid_research` is reported only as an upper bound.".to_string());
    lines.push("- `maker_light` and `taker_spread` are the primary rows.".to_string());
    lines.push("- `wide_stress` is the downside stress row.".to_string());
    lines.push(String::new());
    lines.push("## Diagnostics".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- Validation passed: `{}`; duplicate trade ids `{}`, missing exits `{}`, daily/trade PnL diff `{}`, non-overlap violations `{}`, cost monotonic violations `{}`.",
        validation.passed,
        validation.duplicate_trade_ids,
        validation.missing_exit_reason,
        fmt_float(validation.daily_trade_pnl_abs_diff, 8),
        validation.non_overlap_violations,
        validation.cost_monotonic_violations
    ));
    lines.push(format!(
        "- Fold stability rows: `{}`. Parameter sensitivity rows: `{}`. Single-day dependence rows: `{}`. Failure diagnostic rows: `{}`.",
        outputs.fold_stability.len(),
        outputs.parameter_sensitivity.len(),
        outputs.single_day_dependence.len(),
        outputs.failure_diagnostics.len()
    ));
    lines.push(String::new());
    lines.push("## Exploratory Model Layer".to_string());
    lines.push(String::new());
    lines.push("Python exploration reads the Rust V8 factor panel and is discovery-only: LightGBM, RandomForest, and symbolic pair scans suggest interpretable interactions, while executable candidates are tested only after being expressed as Rust gates and rerun through the canonical episode backtest.".to_string());
    lines.push(format!(
        "- Exploratory model metrics: `date/bonk_v8_exploratory_model_metrics_{}.csv`",
        out_tag(config)
    ));
    lines.push(format!(
        "- Exploratory feature importance: `date/bonk_v8_exploratory_feature_importance_{}.csv`",
        out_tag(config)
    ));
    lines.push(format!(
        "- Exploratory symbolic candidates: `date/bonk_v8_exploratory_symbolic_candidates_{}.csv`",
        out_tag(config)
    ));
    lines.push("- Distilled Rust gate group: `exploratory_distilled`.".to_string());
    lines.push(String::new());
    lines.push("## Outputs".to_string());
    lines.push(String::new());
    for (label, path) in [
        ("factor panel", &paths.factor_panel),
        ("factor catalog", &paths.factor_catalog),
        ("factor audit", &paths.factor_audit),
        ("candidate gates", &paths.candidate_gates),
        ("trades", &paths.trades),
        ("daily", &paths.daily),
        ("summary", &paths.summary),
        ("exit reasons", &paths.exit_reasons),
        ("fold stability", &paths.fold_stability),
        ("non-overlap", &paths.non_overlap),
        ("parameter sensitivity", &paths.parameter_sensitivity),
        ("single-day dependence", &paths.single_day_dependence),
        ("failure diagnostics", &paths.failure_diagnostics),
        ("completion", &paths.completion),
    ] {
        lines.push(format!("- {label}: `{}`", path_string(path)));
    }
    lines.join("\n")
}

fn read_episode_outputs_for_report(paths: &Paths) -> Result<EpisodeOutputs> {
    Ok(EpisodeOutputs {
        candidate_fits: read_csv_rows(&paths.candidate_gates).unwrap_or_default(),
        trades: read_csv_rows(&paths.trades).unwrap_or_default(),
        daily: read_csv_rows(&paths.daily).unwrap_or_default(),
        summary: read_csv_rows(&paths.summary).unwrap_or_default(),
        exit_reasons: Vec::new(),
        fold_stability: Vec::new(),
        non_overlap: Vec::new(),
        parameter_sensitivity: Vec::new(),
        single_day_dependence: Vec::new(),
        failure_diagnostics: Vec::new(),
        configs: Vec::new(),
    })
}

fn read_csv_rows<T>(path: &Path) -> Result<Vec<T>>
where
    T: for<'de> Deserialize<'de>,
{
    if !path.exists() {
        return Ok(Vec::new());
    }
    let mut reader = csv::Reader::from_path(path)?;
    reader
        .deserialize()
        .collect::<std::result::Result<Vec<T>, _>>()
        .map_err(Into::into)
}

fn read_parquet_batches(path: &Path) -> Result<Vec<RecordBatch>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = ParquetRecordBatchReaderBuilder::try_new(file)
        .and_then(|builder| builder.build())
        .with_context(|| format!("failed to build parquet reader for {}", path.display()))?;
    reader
        .collect::<std::result::Result<Vec<_>, _>>()
        .with_context(|| format!("failed to read parquet batches from {}", path.display()))
}

fn str_array<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray> {
    batch
        .column_by_name(name)
        .ok_or_else(|| anyhow!("missing column {name}"))?
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| anyhow!("column {name} is not Utf8"))
}

fn u64_array_col<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a UInt64Array> {
    batch
        .column_by_name(name)
        .ok_or_else(|| anyhow!("missing column {name}"))?
        .as_any()
        .downcast_ref::<UInt64Array>()
        .ok_or_else(|| anyhow!("column {name} is not UInt64"))
}

fn f64_array<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array> {
    batch
        .column_by_name(name)
        .ok_or_else(|| anyhow!("missing column {name}"))?
        .as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| anyhow!("column {name} is not Float64"))
}

fn str_value(array: &StringArray, index: usize) -> String {
    if array.is_null(index) {
        String::new()
    } else {
        array.value(index).to_string()
    }
}

fn u64_value(array: &UInt64Array, index: usize) -> u64 {
    if array.is_null(index) {
        0
    } else {
        array.value(index)
    }
}

fn opt_f64_value(array: &Float64Array, index: usize) -> Option<f64> {
    if array.is_null(index) {
        None
    } else {
        finite(array.value(index))
    }
}

fn opt_col<T, F>(rows: &[T], f: F) -> ArrayRef
where
    F: Fn(&T) -> Option<f64>,
{
    let mut builder = Float64Builder::with_capacity(rows.len());
    for row in rows {
        match f(row).and_then(finite) {
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
            .set_created_by("cex-l2-research-v8".to_string())
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

fn write_csv_direct<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    ensure_parent_dir(path)?;
    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create {}", path.display()))?;
    for row in rows {
        writer.serialize(row)?;
    }
    writer.flush()?;
    Ok(())
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
                    sleep(Duration::from_millis(100 * (attempt as u64 + 1)));
                    if attempt + 2 == ATTEMPTS {
                        return Err(err)
                            .with_context(|| format!("failed to remove old {}", path.display()));
                    }
                    continue;
                }
                Err(err) => {
                    return Err(err)
                        .with_context(|| format!("failed to remove old {}", path.display()));
                }
            }
        }
        match fs::rename(temp, path) {
            Ok(()) => return Ok(()),
            Err(err) if attempt + 1 < ATTEMPTS => {
                sleep(Duration::from_millis(100 * (attempt as u64 + 1)));
                if attempt + 2 == ATTEMPTS {
                    return Err(err)
                        .with_context(|| format!("failed to replace {}", path.display()));
                }
            }
            Err(err) => {
                return Err(err).with_context(|| format!("failed to replace {}", path.display()));
            }
        }
    }
    Ok(())
}

fn temp_path_for(path: &Path) -> PathBuf {
    let filename = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("tmp");
    let nonce = Utc::now()
        .timestamp_nanos_opt()
        .unwrap_or_else(|| Utc::now().timestamp_micros());
    path.with_file_name(format!(".{filename}.tmp.{}.{}", std::process::id(), nonce))
}

fn iso_now() -> String {
    Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

fn utc_us(value: &str) -> Result<u64> {
    let parsed = DateTime::parse_from_rfc3339(value)?.with_timezone(&Utc);
    Ok(parsed.timestamp_micros() as u64)
}

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, Float64Array, StringArray, UInt64Array};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, Days, Utc};
use finance_chain_core::storage::ensure_parent_dir;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::{Deserialize, Serialize};

use crate::download::{DEFAULT_BONK_DATA_ROOT, path_string};
use crate::v8::DEFAULT_V8_RUN_TAG;

const MINUTE_US: u64 = 60_000_000;
const GUARDRAIL: &str = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim";
const DEFAULT_SYMBOLS: &[&str] = &["BONK1MUSDC", "BONK1MUSDT"];
const DEFAULT_EXECUTION_MODELS: &[&str] =
    &["mid_research", "maker_light", "taker_spread", "wide_stress"];
const DEFAULT_SIDES: &[&str] = &["long", "short"];
const DEFAULT_TP_BPS: &[u32] = &[30, 50, 75];
const DEFAULT_SL_BPS: &[u32] = &[20, 40, 60];
const DEFAULT_TIMEOUT_MINUTES: &[u32] = &[10, 30, 60];
const POTENTIAL_FEATURES: &[&str] = &[
    "phi_bid",
    "phi_ask",
    "net_potential",
    "potential_gradient",
    "potential_curvature",
    "energy_release",
    "liquidity_barrier",
    "queue_depth_pressure",
    "cancellation_withdrawal_energy",
    "replenish_relaxation",
    "spread_depth_resistance",
    "cross_venue_forcing",
    "event_time_decay",
    "kalman_pressure_fixed",
    "yau_pressure_fixed",
    "potential_barrier_distance",
];

#[derive(Debug, Clone)]
pub struct V9Config {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub run_tag: String,
    pub out_tag: String,
    pub research_md: PathBuf,
    pub report_md: PathBuf,
    pub resume: bool,
    pub force: bool,
    pub stop_after: Option<String>,
    pub dry_run: bool,
    pub notional_quote: f64,
    pub fee_bps: f64,
    pub cooldown_minutes: usize,
    pub min_hold_minutes: usize,
    pub debounce_on_minutes: usize,
    pub debounce_off_minutes: usize,
    pub tp_bps: Vec<u32>,
    pub sl_bps: Vec<u32>,
    pub timeout_minutes: Vec<u32>,
    pub execution_models: Vec<String>,
}

impl Default for V9Config {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_BONK_DATA_ROOT),
            date_dir: PathBuf::from("date"),
            run_tag: DEFAULT_V8_RUN_TAG.to_string(),
            out_tag: DEFAULT_V8_RUN_TAG.to_string(),
            research_md: PathBuf::from(
                "docs/research/bonk/v9-orderbook-potential-filtering-research.md",
            ),
            report_md: PathBuf::from(
                "docs/markets/bonk/v1-cex-v9-orderbook-potential-filtering.md",
            ),
            resume: true,
            force: false,
            stop_after: None,
            dry_run: false,
            notional_quote: 100.0,
            fee_bps: 2.0,
            cooldown_minutes: 120,
            min_hold_minutes: 2,
            debounce_on_minutes: 2,
            debounce_off_minutes: 2,
            tp_bps: DEFAULT_TP_BPS.to_vec(),
            sl_bps: DEFAULT_SL_BPS.to_vec(),
            timeout_minutes: DEFAULT_TIMEOUT_MINUTES.to_vec(),
            execution_models: DEFAULT_EXECUTION_MODELS
                .iter()
                .map(|value| value.to_string())
                .collect(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct V9Summary {
    pub run_tag: String,
    pub out_tag: String,
    pub potential_rows: usize,
    pub filter_rows: usize,
    pub anchor_fit_rows: usize,
    pub trades: usize,
    pub daily_rows: usize,
    pub summary_rows: usize,
    pub spearman_rows: usize,
    pub negative_control_rows: usize,
    pub validation_passed: bool,
    pub manifest_json: String,
    pub checkpoint_json: String,
    pub potential_state_csv: String,
    pub filter_state_csv: String,
    pub filter_params_csv: String,
    pub anchor_candidates_csv: String,
    pub trades_csv: String,
    pub daily_csv: String,
    pub summary_csv: String,
    pub exit_reasons_csv: String,
    pub fold_stability_csv: String,
    pub non_overlap_csv: String,
    pub parameter_sensitivity_csv: String,
    pub single_day_dependence_csv: String,
    pub failure_diagnostics_csv: String,
    pub spearman_stability_csv: String,
    pub negative_controls_csv: String,
    pub completion_json: String,
    pub research_md: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    v8_factor_panel: PathBuf,
    manifest: PathBuf,
    checkpoint: PathBuf,
    completion: PathBuf,
    potential_state: PathBuf,
    filter_state: PathBuf,
    filter_params: PathBuf,
    anchor_candidates: PathBuf,
    trades: PathBuf,
    daily: PathBuf,
    summary: PathBuf,
    exit_reasons: PathBuf,
    fold_stability: PathBuf,
    non_overlap: PathBuf,
    parameter_sensitivity: PathBuf,
    single_day_dependence: PathBuf,
    failure_diagnostics: PathBuf,
    spearman_stability: PathBuf,
    negative_controls: PathBuf,
}

impl Paths {
    fn new(config: &V9Config) -> Self {
        let out_tag = out_tag(config);
        let prefix = format!("bonk_v9_orderbook_potential_filtering_{out_tag}");
        Self {
            v8_factor_panel: config
                .data_root
                .join("derived/bonk_v8_factor_panel")
                .join(format!("bonk_v8_factor_panel_{}.parquet", config.run_tag)),
            manifest: config.date_dir.join(format!("{prefix}_manifest.json")),
            checkpoint: config.date_dir.join(format!("{prefix}_checkpoint.json")),
            completion: config.date_dir.join(format!("{prefix}_completion.json")),
            potential_state: config
                .date_dir
                .join(format!("bonk_v9_potential_state_{out_tag}.csv")),
            filter_state: config
                .date_dir
                .join(format!("bonk_v9_filter_state_{out_tag}.csv")),
            filter_params: config
                .date_dir
                .join(format!("bonk_v9_filter_params_{out_tag}.csv")),
            anchor_candidates: config
                .date_dir
                .join(format!("bonk_v9_anchor_candidates_{out_tag}.csv")),
            trades: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_trades.csv"
            )),
            daily: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_daily.csv"
            )),
            summary: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_summary.csv"
            )),
            exit_reasons: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_exit_reasons.csv"
            )),
            fold_stability: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_fold_stability.csv"
            )),
            non_overlap: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_non_overlap.csv"
            )),
            parameter_sensitivity: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_parameter_sensitivity.csv"
            )),
            single_day_dependence: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_single_day_dependence.csv"
            )),
            failure_diagnostics: config.date_dir.join(format!(
                "bonk_v9_long_short_episode_backtest_{out_tag}_failure_diagnostics.csv"
            )),
            spearman_stability: config
                .date_dir
                .join(format!("bonk_v9_spearman_stability_{out_tag}.csv")),
            negative_controls: config
                .date_dir
                .join(format!("bonk_v9_negative_controls_{out_tag}.csv")),
        }
    }
}

#[derive(Debug, Serialize)]
struct Manifest {
    run_name: String,
    run_tag: String,
    out_tag: String,
    generated_at_utc: String,
    guardrail: String,
    no_new_raw_data: bool,
    inputs: Vec<InputState>,
    outputs: BTreeMap<String, String>,
    steps: Vec<String>,
    resume_checkpoint: String,
}

#[derive(Debug, Serialize)]
struct InputState {
    path: String,
    exists: bool,
    bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Checkpoint {
    run_tag: String,
    out_tag: String,
    guardrail: String,
    updated_at_utc: String,
    steps: Vec<StepState>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct StepState {
    name: String,
    status: String,
    started_at_utc: String,
    finished_at_utc: Option<String>,
    detail: String,
}

#[derive(Debug, Serialize)]
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

#[derive(Debug, Serialize)]
struct CompletionConfig {
    notional_quote: f64,
    fee_bps: f64,
    cooldown_minutes: usize,
    min_hold_minutes: usize,
    debounce_on_minutes: usize,
    debounce_off_minutes: usize,
    tp_bps: Vec<u32>,
    sl_bps: Vec<u32>,
    timeout_minutes: Vec<u32>,
    execution_models: Vec<String>,
    sides: Vec<String>,
}

#[derive(Debug, Serialize)]
struct CompletionCounts {
    potential_rows: usize,
    filter_rows: usize,
    filter_param_rows: usize,
    anchor_fit_rows: usize,
    trades: usize,
    daily_rows: usize,
    summary_rows: usize,
    spearman_rows: usize,
    negative_control_rows: usize,
}

#[derive(Debug, Clone, Serialize)]
struct ValidationChecks {
    duplicate_trade_ids: usize,
    missing_exit_reason: usize,
    daily_trade_pnl_abs_diff: f64,
    non_overlap_violations: usize,
    primary_exec_rows: usize,
    long_rows: usize,
    short_rows: usize,
    negative_control_rows: usize,
    passed: bool,
}

#[derive(Debug, Clone)]
struct V8PanelRow {
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
    depth_25_total_notional: Option<f64>,
    top_depth_total_notional: Option<f64>,
    inverse_spread_depth: Option<f64>,
    depth_fragility: Option<f64>,
    top_vs_25_depth_shape: Option<f64>,
    depth_slope_bid: Option<f64>,
    depth_slope_ask: Option<f64>,
    ask_withdraw_1m: Option<f64>,
    ask_withdraw_5m: Option<f64>,
    ask_withdraw_10m: Option<f64>,
    bid_replenish_1m: Option<f64>,
    bid_replenish_5m: Option<f64>,
    bid_replenish_10m: Option<f64>,
    bid_withdraw_5m: Option<f64>,
    ask_replenish_5m: Option<f64>,
    spread_compression_5m_bps: Option<f64>,
    spread_expansion_5m_bps: Option<f64>,
    microprice_impulse_5m_bps: Option<f64>,
    wobi5_impulse_5m: Option<f64>,
    wobi25_impulse_5m: Option<f64>,
    depth_imbalance25_delta_5m: Option<f64>,
    l2_impulse_score_raw: Option<f64>,
    l2_trade_count_burst_15m: Option<f64>,
    l2_trade_notional_burst_15m: Option<f64>,
    trade_flow_imbalance: Option<f64>,
    reported_buy_share: Option<f64>,
    cross_venue_basis_bps: Option<f64>,
    cross_venue_microprice_disagreement_bps: Option<f64>,
    cross_venue_activity_ratio: Option<f64>,
    rel_market_60m_bps: Option<f64>,
    rel_meme_60m_bps: Option<f64>,
    lead_market_catchup_15m_bps: Option<f64>,
    lead_btc_catchup_5m_bps: Option<f64>,
    price_mom_60m_bps: Option<f64>,
    price_rv_60m_bps: Option<f64>,
    bullish_common_mode_score: Option<f64>,
    bullish_cross_abs_ret_mean_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PotentialStateRow {
    run_tag: String,
    out_tag: String,
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
    phi_bid: Option<f64>,
    phi_ask: Option<f64>,
    net_potential: Option<f64>,
    potential_gradient: Option<f64>,
    potential_curvature: Option<f64>,
    energy_release: Option<f64>,
    liquidity_barrier: Option<f64>,
    queue_depth_pressure: Option<f64>,
    cancellation_withdrawal_energy: Option<f64>,
    replenish_relaxation: Option<f64>,
    spread_depth_resistance: Option<f64>,
    cross_venue_forcing: Option<f64>,
    event_time_decay: Option<f64>,
    kalman_pressure_fixed: Option<f64>,
    yau_pressure_fixed: Option<f64>,
    potential_barrier_distance: Option<f64>,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct FilterParamRow {
    run_tag: String,
    out_tag: String,
    fold: String,
    symbol: String,
    train_count: usize,
    measurement_variance: f64,
    process_variance: f64,
    kalman_gain: f64,
    kalman_decay: f64,
    yau_gain: f64,
    yau_decay: f64,
    yau_restart_width: f64,
    net_low: f64,
    net_high: f64,
    energy_high: f64,
    barrier_high: f64,
    gradient_low: f64,
    gradient_high: f64,
    hidden_low: f64,
    hidden_high: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct FilterStateRow {
    run_tag: String,
    out_tag: String,
    fold: String,
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
    net_potential: Option<f64>,
    energy_release: Option<f64>,
    liquidity_barrier: Option<f64>,
    potential_barrier_distance: Option<f64>,
    replenish_relaxation: Option<f64>,
    cancellation_withdrawal_energy: Option<f64>,
    kalman_pressure: Option<f64>,
    yau_pressure: Option<f64>,
    kalman_innovation: Option<f64>,
    yau_log_likelihood_delta: Option<f64>,
    potential_bucket_train_fit: String,
    hidden_bucket_train_fit: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AnchorCandidateRow {
    run_tag: String,
    out_tag: String,
    fold: String,
    symbol: String,
    anchor_type: String,
    side: String,
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
struct SignalRow {
    timestamp_utc: String,
    timestamp_us: u64,
    symbol: String,
    mid_open: Option<f64>,
    mid_high: Option<f64>,
    mid_low: Option<f64>,
    mid_close: Option<f64>,
    queue_fill_probability: f64,
    liquidity_barrier: f64,
    gate_selected: bool,
}

#[derive(Debug, Clone)]
struct BaseTrade {
    fold: String,
    symbol: String,
    anchor_type: String,
    side: String,
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
    queue_fill_probability: f64,
    liquidity_barrier: f64,
    thresholds_fit_on_train: String,
    trade_number: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TradeRow {
    trade_id: String,
    run_tag: String,
    out_tag: String,
    fold: String,
    symbol: String,
    anchor_type: String,
    side: String,
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
    latency_bps: f64,
    slippage_bps: f64,
    queue_penalty_bps: f64,
    net_bps: f64,
    pnl_quote: f64,
    duration_minutes: f64,
    mfe_bps: f64,
    mae_bps: f64,
    same_bar_ambiguous: bool,
    queue_fill_probability: f64,
    liquidity_barrier: f64,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DailyRow {
    fold: String,
    date: String,
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    trade_count: usize,
    pnl_quote: f64,
    avg_net_bps: Option<f64>,
    max_intraday_drawdown_quote: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SummaryRow {
    summary_scope: String,
    fold: String,
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    notional_quote: f64,
    days: usize,
    trade_count: usize,
    total_pnl_quote: f64,
    avg_daily_pnl_quote: f64,
    median_daily_pnl_quote: f64,
    positive_day_rate: Option<f64>,
    max_drawdown_quote: f64,
    trades_per_day: f64,
    win_rate: Option<f64>,
    profit_factor: Option<f64>,
    median_trade_net_bps: Option<f64>,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ExitReasonRow {
    summary_scope: String,
    fold: String,
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    exit_reason: String,
    trade_count: usize,
    pnl_quote: f64,
    avg_net_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct FoldStabilityRow {
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    fold1_pnl: Option<f64>,
    fold2_pnl: Option<f64>,
    fold3_pnl: Option<f64>,
    fold2_fold3_both_nonnegative: bool,
    positive_fold_count: usize,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct NonOverlapRow {
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    overlap_violations: usize,
    non_overlap_mode: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ParameterSensitivityRow {
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    configs_tested: usize,
    positive_configs: usize,
    best_total_pnl_quote: f64,
    median_total_pnl_quote: Option<f64>,
    pnl_iqr_quote: Option<f64>,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SingleDayDependenceRow {
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    total_pnl_quote: f64,
    max_day_pnl_quote: f64,
    max_day_share_of_positive_pnl: Option<f64>,
    dependence_flag: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct FailureDiagnosticRow {
    symbol: String,
    anchor_type: String,
    side: String,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
struct NegativeControlRow {
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    control_type: String,
    base_total_pnl_quote: f64,
    control_total_pnl_quote: f64,
    control_trade_count: usize,
    control_note: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SpearmanRow {
    run_tag: String,
    out_tag: String,
    fold: String,
    symbol: String,
    horizon_minutes: u32,
    feature_name: String,
    spearman: f64,
    abs_spearman: f64,
    n: usize,
    sign: String,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct EpisodeOutputs {
    anchor_candidates: Vec<AnchorCandidateRow>,
    trades: Vec<TradeRow>,
    daily: Vec<DailyRow>,
    summary: Vec<SummaryRow>,
    exit_reasons: Vec<ExitReasonRow>,
    fold_stability: Vec<FoldStabilityRow>,
    non_overlap: Vec<NonOverlapRow>,
    parameter_sensitivity: Vec<ParameterSensitivityRow>,
    single_day_dependence: Vec<SingleDayDependenceRow>,
    failure_diagnostics: Vec<FailureDiagnosticRow>,
    negative_controls: Vec<NegativeControlRow>,
}

#[derive(Debug, Clone)]
struct AnchorSpec {
    anchor_type: &'static str,
    description: &'static str,
}

#[derive(Debug, Clone)]
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

pub fn run_v9_orderbook_potential_filtering(config: &V9Config) -> Result<V9Summary> {
    validate_config(config)?;
    let paths = Paths::new(config);
    ensure_parent_dir(&paths.manifest)?;
    ensure_parent_dir(&config.research_md)?;
    ensure_parent_dir(&config.report_md)?;
    let mut checkpoint = load_checkpoint(&paths.checkpoint, config)?;
    write_manifest(config, &paths)?;

    let mut potential_rows = Vec::new();
    if should_run_step(
        config,
        &checkpoint,
        "potential_state",
        &[&paths.potential_state],
    ) {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "potential_state",
            "running",
            "construct Phi_bid/Phi_ask and order-book potential states",
        )?;
        if config.dry_run {
            update_checkpoint(
                &mut checkpoint,
                &paths.checkpoint,
                "potential_state",
                "complete",
                "dry-run skipped",
            )?;
            return Ok(summary_from_existing(config, &paths));
        }
        let v8_rows = read_v8_factor_panel(&paths.v8_factor_panel, &config.run_tag)?;
        potential_rows = build_potential_states(config, &v8_rows);
        write_csv_atomic(&paths.potential_state, &potential_rows)?;
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "potential_state",
            "complete",
            &format!("rows={}", potential_rows.len()),
        )?;
        if stop_after(config, "potential_state") {
            return Ok(summary_from_existing(config, &paths));
        }
    }
    if potential_rows.is_empty() && paths.potential_state.exists() {
        potential_rows = read_csv_rows(&paths.potential_state)?;
    }

    let mut filter_params = Vec::new();
    let mut filter_rows = Vec::new();
    if should_run_step(
        config,
        &checkpoint,
        "filter_state",
        &[&paths.filter_params, &paths.filter_state],
    ) {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "filter_state",
            "running",
            "fit train-only Kalman/Yau-Yau-inspired filter params and apply to validation",
        )?;
        let outputs = build_filter_states(config, &potential_rows)?;
        filter_params = outputs.0;
        filter_rows = outputs.1;
        write_csv_atomic(&paths.filter_params, &filter_params)?;
        write_csv_atomic(&paths.filter_state, &filter_rows)?;
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "filter_state",
            "complete",
            &format!(
                "filter_params={} filter_rows={}",
                filter_params.len(),
                filter_rows.len()
            ),
        )?;
        if stop_after(config, "filter_state") {
            return Ok(summary_from_existing(config, &paths));
        }
    }
    if filter_params.is_empty() && paths.filter_params.exists() {
        filter_params = read_csv_rows(&paths.filter_params)?;
    }
    if filter_rows.is_empty() && paths.filter_state.exists() {
        filter_rows = read_csv_rows(&paths.filter_state)?;
    }

    let mut episode_outputs = None;
    if should_run_step(
        config,
        &checkpoint,
        "episode_backtest",
        &[
            &paths.anchor_candidates,
            &paths.trades,
            &paths.daily,
            &paths.summary,
            &paths.exit_reasons,
            &paths.fold_stability,
            &paths.non_overlap,
            &paths.parameter_sensitivity,
            &paths.single_day_dependence,
            &paths.failure_diagnostics,
            &paths.negative_controls,
        ],
    ) {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "episode_backtest",
            "running",
            "movable-anchor long/short after-cost backtest",
        )?;
        let outputs = run_episode_backtests(config, &filter_rows)?;
        write_csv_atomic(&paths.anchor_candidates, &outputs.anchor_candidates)?;
        write_csv_atomic(&paths.trades, &outputs.trades)?;
        write_csv_atomic(&paths.daily, &outputs.daily)?;
        write_csv_atomic(&paths.summary, &outputs.summary)?;
        write_csv_atomic(&paths.exit_reasons, &outputs.exit_reasons)?;
        write_csv_atomic(&paths.fold_stability, &outputs.fold_stability)?;
        write_csv_atomic(&paths.non_overlap, &outputs.non_overlap)?;
        write_csv_atomic(&paths.parameter_sensitivity, &outputs.parameter_sensitivity)?;
        write_csv_atomic(&paths.single_day_dependence, &outputs.single_day_dependence)?;
        write_csv_atomic(&paths.failure_diagnostics, &outputs.failure_diagnostics)?;
        write_csv_atomic(&paths.negative_controls, &outputs.negative_controls)?;
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "episode_backtest",
            "complete",
            &format!(
                "trades={} daily={} summary={}",
                outputs.trades.len(),
                outputs.daily.len(),
                outputs.summary.len()
            ),
        )?;
        episode_outputs = Some(outputs);
        if stop_after(config, "episode_backtest") {
            return Ok(summary_from_existing(config, &paths));
        }
    }

    let mut spearman_rows = Vec::new();
    if should_run_step(
        config,
        &checkpoint,
        "spearman_stability",
        &[&paths.spearman_stability],
    ) {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "spearman_stability",
            "running",
            "validation-only Spearman and horizon-decay diagnostics",
        )?;
        spearman_rows = build_spearman_stability(&potential_rows)?;
        write_csv_atomic(&paths.spearman_stability, &spearman_rows)?;
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "spearman_stability",
            "complete",
            &format!("rows={}", spearman_rows.len()),
        )?;
        if stop_after(config, "spearman_stability") {
            return Ok(summary_from_existing(config, &paths));
        }
    }

    if should_run_step(
        config,
        &checkpoint,
        "docs",
        &[&config.research_md, &config.report_md],
    ) {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "docs",
            "running",
            "write research review and market report",
        )?;
        let outputs = match episode_outputs {
            Some(outputs) => outputs,
            None => read_episode_outputs(&paths)?,
        };
        if spearman_rows.is_empty() && paths.spearman_stability.exists() {
            spearman_rows = read_csv_rows(&paths.spearman_stability)?;
        }
        let validation =
            validate_outputs(&outputs.trades, &outputs.daily, &outputs.negative_controls);
        write_text_atomic(&config.research_md, &build_research_doc(config))?;
        write_text_atomic(
            &config.report_md,
            &build_report_doc(config, &paths, &outputs, &spearman_rows, &validation),
        )?;
        let completion = build_completion(
            config,
            &paths,
            potential_rows.len(),
            filter_rows.len(),
            filter_params.len(),
            &outputs,
            spearman_rows.len(),
            &validation,
        );
        write_json_atomic(&paths.completion, &completion)?;
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "docs",
            "complete",
            "research doc, report, completion written",
        )?;
    }

    Ok(summary_from_existing(config, &paths))
}

fn out_tag(config: &V9Config) -> String {
    if config.out_tag.is_empty() {
        config.run_tag.clone()
    } else {
        config.out_tag.clone()
    }
}

fn validate_config(config: &V9Config) -> Result<()> {
    if config.run_tag.trim().is_empty() {
        bail!("run_tag must not be empty");
    }
    if config.notional_quote <= 0.0 {
        bail!("notional_quote must be positive");
    }
    if config.tp_bps.is_empty()
        || config.sl_bps.is_empty()
        || config.timeout_minutes.is_empty()
        || config.execution_models.is_empty()
    {
        bail!("tp/sl/timeout/execution grids must be non-empty");
    }
    Ok(())
}

fn should_run_step(
    config: &V9Config,
    checkpoint: &Checkpoint,
    step: &str,
    required_outputs: &[&Path],
) -> bool {
    if config.force {
        return true;
    }
    let complete = checkpoint
        .steps
        .iter()
        .any(|state| state.name == step && state.status == "complete");
    !config.resume || !complete || required_outputs.iter().any(|path| !path.exists())
}

fn stop_after(config: &V9Config, step: &str) -> bool {
    config.stop_after.as_deref() == Some(step)
}

fn load_checkpoint(path: &Path, config: &V9Config) -> Result<Checkpoint> {
    if config.resume && path.exists() && !config.force {
        let file = File::open(path)?;
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

fn update_checkpoint(
    checkpoint: &mut Checkpoint,
    path: &Path,
    step: &str,
    status: &str,
    detail: &str,
) -> Result<()> {
    let now = iso_now();
    if let Some(existing) = checkpoint.steps.iter_mut().find(|state| state.name == step) {
        existing.status = status.to_string();
        existing.detail = detail.to_string();
        if status == "running" {
            existing.started_at_utc = now.clone();
            existing.finished_at_utc = None;
        } else {
            existing.finished_at_utc = Some(now.clone());
        }
    } else {
        checkpoint.steps.push(StepState {
            name: step.to_string(),
            status: status.to_string(),
            started_at_utc: now.clone(),
            finished_at_utc: (status != "running").then_some(now.clone()),
            detail: detail.to_string(),
        });
    }
    checkpoint.updated_at_utc = now;
    write_json_atomic(path, checkpoint)
}

fn write_manifest(config: &V9Config, paths: &Paths) -> Result<()> {
    let mut outputs = BTreeMap::new();
    outputs.insert("completion".to_string(), path_string(&paths.completion));
    outputs.insert(
        "potential_state".to_string(),
        path_string(&paths.potential_state),
    );
    outputs.insert("filter_state".to_string(), path_string(&paths.filter_state));
    outputs.insert(
        "filter_params".to_string(),
        path_string(&paths.filter_params),
    );
    outputs.insert(
        "anchor_candidates".to_string(),
        path_string(&paths.anchor_candidates),
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
    outputs.insert(
        "spearman_stability".to_string(),
        path_string(&paths.spearman_stability),
    );
    outputs.insert(
        "negative_controls".to_string(),
        path_string(&paths.negative_controls),
    );
    outputs.insert("research_doc".to_string(), path_string(&config.research_md));
    outputs.insert("report".to_string(), path_string(&config.report_md));
    outputs.insert("checkpoint".to_string(), path_string(&paths.checkpoint));
    outputs.insert("manifest".to_string(), path_string(&paths.manifest));

    let input = InputState {
        path: path_string(&paths.v8_factor_panel),
        exists: paths.v8_factor_panel.exists(),
        bytes: paths
            .v8_factor_panel
            .metadata()
            .map(|meta| meta.len())
            .unwrap_or(0),
    };
    let manifest = Manifest {
        run_name: "bonk_v9_orderbook_potential_filtering".to_string(),
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        generated_at_utc: iso_now(),
        guardrail: GUARDRAIL.to_string(),
        no_new_raw_data: true,
        inputs: vec![input],
        outputs,
        steps: vec![
            "potential_state".to_string(),
            "filter_state".to_string(),
            "episode_backtest".to_string(),
            "spearman_stability".to_string(),
            "docs".to_string(),
        ],
        resume_checkpoint: path_string(&paths.checkpoint),
    };
    write_json_atomic(&paths.manifest, &manifest)
}

fn read_v8_factor_panel(path: &Path, run_tag_filter: &str) -> Result<Vec<V8PanelRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let run_tag = str_array(&batch, "run_tag")?;
        let timestamp_utc = str_array(&batch, "timestamp_utc")?;
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        for idx in 0..batch.num_rows() {
            if str_value(run_tag, idx) != run_tag_filter {
                continue;
            }
            let sym = str_value(symbol, idx);
            if !DEFAULT_SYMBOLS.contains(&sym.as_str()) {
                continue;
            }
            out.push(V8PanelRow {
                run_tag: run_tag_filter.to_string(),
                timestamp_utc: str_value(timestamp_utc, idx),
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: sym,
                mid_open: opt_col_value(&batch, "mid_open", idx)?,
                mid_high: opt_col_value(&batch, "mid_high", idx)?,
                mid_low: opt_col_value(&batch, "mid_low", idx)?,
                mid_close: opt_col_value(&batch, "mid_close", idx)?,
                spread_bps: opt_col_value(&batch, "spread_bps", idx)?,
                depth_bid_25: opt_col_value(&batch, "depth_bid_25", idx)?,
                depth_ask_25: opt_col_value(&batch, "depth_ask_25", idx)?,
                depth_25_total_notional: opt_col_value(&batch, "depth_25_total_notional", idx)?,
                top_depth_total_notional: opt_col_value(&batch, "top_depth_total_notional", idx)?,
                inverse_spread_depth: opt_col_value(&batch, "inverse_spread_depth", idx)?,
                depth_fragility: opt_col_value(&batch, "depth_fragility", idx)?,
                top_vs_25_depth_shape: opt_col_value(&batch, "top_vs_25_depth_shape", idx)?,
                depth_slope_bid: opt_col_value(&batch, "depth_slope_bid", idx)?,
                depth_slope_ask: opt_col_value(&batch, "depth_slope_ask", idx)?,
                ask_withdraw_1m: opt_col_value(&batch, "ask_withdraw_1m", idx)?,
                ask_withdraw_5m: opt_col_value(&batch, "ask_withdraw_5m", idx)?,
                ask_withdraw_10m: opt_col_value(&batch, "ask_withdraw_10m", idx)?,
                bid_replenish_1m: opt_col_value(&batch, "bid_replenish_1m", idx)?,
                bid_replenish_5m: opt_col_value(&batch, "bid_replenish_5m", idx)?,
                bid_replenish_10m: opt_col_value(&batch, "bid_replenish_10m", idx)?,
                bid_withdraw_5m: opt_col_value(&batch, "bid_withdraw_5m", idx)?,
                ask_replenish_5m: opt_col_value(&batch, "ask_replenish_5m", idx)?,
                spread_compression_5m_bps: opt_col_value(&batch, "spread_compression_5m_bps", idx)?,
                spread_expansion_5m_bps: opt_col_value(&batch, "spread_expansion_5m_bps", idx)?,
                microprice_impulse_5m_bps: opt_col_value(&batch, "microprice_impulse_5m_bps", idx)?,
                wobi5_impulse_5m: opt_col_value(&batch, "wobi5_impulse_5m", idx)?,
                wobi25_impulse_5m: opt_col_value(&batch, "wobi25_impulse_5m", idx)?,
                depth_imbalance25_delta_5m: opt_col_value(
                    &batch,
                    "depth_imbalance25_delta_5m",
                    idx,
                )?,
                l2_impulse_score_raw: opt_col_value(&batch, "l2_impulse_score_raw", idx)?,
                l2_trade_count_burst_15m: opt_col_value(&batch, "l2_trade_count_burst_15m", idx)?,
                l2_trade_notional_burst_15m: opt_col_value(
                    &batch,
                    "l2_trade_notional_burst_15m",
                    idx,
                )?,
                trade_flow_imbalance: opt_col_value(&batch, "trade_flow_imbalance", idx)?,
                reported_buy_share: opt_col_value(&batch, "reported_buy_share", idx)?,
                cross_venue_basis_bps: opt_col_value(&batch, "cross_venue_basis_bps", idx)?,
                cross_venue_microprice_disagreement_bps: opt_col_value(
                    &batch,
                    "cross_venue_microprice_disagreement_bps",
                    idx,
                )?,
                cross_venue_activity_ratio: opt_col_value(
                    &batch,
                    "cross_venue_activity_ratio",
                    idx,
                )?,
                rel_market_60m_bps: opt_col_value(&batch, "rel_market_60m_bps", idx)?,
                rel_meme_60m_bps: opt_col_value(&batch, "rel_meme_60m_bps", idx)?,
                lead_market_catchup_15m_bps: opt_col_value(
                    &batch,
                    "lead_market_catchup_15m_bps",
                    idx,
                )?,
                lead_btc_catchup_5m_bps: opt_col_value(&batch, "lead_btc_catchup_5m_bps", idx)?,
                price_mom_60m_bps: opt_col_value(&batch, "price_mom_60m_bps", idx)?,
                price_rv_60m_bps: opt_col_value(&batch, "price_rv_60m_bps", idx)?,
                bullish_common_mode_score: opt_col_value(&batch, "bullish_common_mode_score", idx)?,
                bullish_cross_abs_ret_mean_bps: opt_col_value(
                    &batch,
                    "bullish_cross_abs_ret_mean_bps",
                    idx,
                )?,
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

fn build_potential_states(config: &V9Config, rows: &[V8PanelRow]) -> Vec<PotentialStateRow> {
    let mut out = Vec::with_capacity(rows.len());
    let mut prev_by_symbol: HashMap<String, PotentialStateRow> = HashMap::new();
    let mut kalman_fixed_by_symbol: HashMap<String, f64> = HashMap::new();
    let mut yau_fixed_by_symbol: HashMap<String, f64> = HashMap::new();
    let mut decay_by_symbol: HashMap<String, f64> = HashMap::new();
    let out_tag = out_tag(config);

    for row in rows {
        let queue_depth_pressure = depth_pressure(row.depth_bid_25, row.depth_ask_25);
        let cancellation_withdrawal_energy = mean_opt(&[
            row.ask_withdraw_1m.map(|v| v * 0.5),
            row.ask_withdraw_5m,
            row.ask_withdraw_10m.map(|v| v * 0.5),
            row.bid_withdraw_5m.map(|v| v * 0.7),
            row.spread_expansion_5m_bps.map(|v| squash(v, 5.0)),
        ]);
        let replenish_relaxation = mean_opt(&[
            row.bid_replenish_1m.map(|v| v * 0.5),
            row.bid_replenish_5m,
            row.bid_replenish_10m.map(|v| v * 0.5),
            row.ask_replenish_5m.map(|v| v * 0.3),
            row.spread_compression_5m_bps.map(|v| squash(v, 5.0)),
        ]);
        let spread_depth_resistance = mean_opt(&[
            row.spread_bps.map(|v| squash(v, 6.0)),
            row.depth_fragility,
            row.top_vs_25_depth_shape.map(|v| v.abs()),
            row.inverse_spread_depth.map(|v| -squash(v, 10.0)),
        ]);
        let cross_venue_forcing = mean_opt(&[
            row.cross_venue_basis_bps.map(|v| squash(v, 8.0)),
            row.cross_venue_microprice_disagreement_bps
                .map(|v| squash(v, 8.0)),
            row.lead_market_catchup_15m_bps.map(|v| squash(v, 20.0)),
            row.lead_btc_catchup_5m_bps.map(|v| squash(v, 15.0)),
            row.rel_market_60m_bps.map(|v| squash(v, 80.0)),
            row.rel_meme_60m_bps.map(|v| squash(v, 80.0)),
            row.cross_venue_activity_ratio.map(|v| squash(v, 30.0)),
        ]);
        let book_impulse = mean_opt(&[
            row.microprice_impulse_5m_bps.map(|v| squash(v, 5.0)),
            row.wobi5_impulse_5m,
            row.wobi25_impulse_5m,
            row.depth_imbalance25_delta_5m,
            row.l2_impulse_score_raw.map(|v| squash(v, 8.0)),
        ]);
        let flow_pressure = mean_opt(&[
            row.trade_flow_imbalance,
            row.reported_buy_share.map(|v| (v - 0.5) * 2.0),
            row.l2_trade_count_burst_15m.map(|v| squash(v, 2.5)),
            row.l2_trade_notional_burst_15m.map(|v| squash(v, 2.5)),
        ]);
        let regime_pressure = mean_opt(&[
            row.price_mom_60m_bps.map(|v| squash(v, 80.0)),
            row.price_rv_60m_bps.map(|v| squash(v, 120.0)),
            row.bullish_common_mode_score.map(|v| -squash(v, 1.5)),
            row.bullish_cross_abs_ret_mean_bps.map(|v| squash(v, 8.0)),
        ]);
        let liquidity_barrier = mean_opt(&[
            spread_depth_resistance,
            row.depth_slope_ask,
            row.depth_slope_bid.map(|v| -v),
            row.depth_25_total_notional.map(|v| -squash(v, 25_000.0)),
            row.top_depth_total_notional.map(|v| -squash(v, 1_000.0)),
        ]);

        let phi_bid = mean_opt(&[
            queue_depth_pressure,
            book_impulse,
            replenish_relaxation,
            flow_pressure,
            cross_venue_forcing,
            regime_pressure,
        ]);
        let phi_ask = mean_opt(&[
            queue_depth_pressure.map(|v| -v),
            cancellation_withdrawal_energy,
            spread_depth_resistance,
            cross_venue_forcing.map(|v| -v),
            regime_pressure.map(|v| -0.5 * v),
        ]);
        let net_potential = phi_bid
            .zip(phi_ask)
            .and_then(|(bid, ask)| finite(bid - ask));
        let prev = prev_by_symbol.get(&row.symbol);
        let potential_gradient = prev
            .and_then(|prev| net_potential.zip(prev.net_potential))
            .and_then(|(cur, prev)| finite(cur - prev));
        let potential_curvature = prev
            .and_then(|prev| potential_gradient.zip(prev.potential_gradient))
            .and_then(|(cur, prev)| finite(cur - prev));
        let energy_release = mean_opt(&[
            potential_gradient.map(f64::abs),
            potential_curvature.map(f64::abs),
            cancellation_withdrawal_energy,
            replenish_relaxation,
            row.l2_trade_notional_burst_15m.map(|v| squash(v, 2.5)),
            row.spread_expansion_5m_bps.map(|v| squash(v, 5.0)),
        ]);
        let previous_decay = decay_by_symbol.get(&row.symbol).copied().unwrap_or(0.0);
        let event_time_decay = energy_release
            .map(|energy| 0.86 * previous_decay + energy.max(0.0))
            .and_then(finite);
        if let Some(value) = event_time_decay {
            decay_by_symbol.insert(row.symbol.clone(), value);
        }
        let previous_kalman = kalman_fixed_by_symbol
            .get(&row.symbol)
            .copied()
            .unwrap_or(0.0);
        let kalman_pressure_fixed = net_potential
            .map(|measurement| 0.82 * previous_kalman + 0.18 * measurement)
            .and_then(finite);
        if let Some(value) = kalman_pressure_fixed {
            kalman_fixed_by_symbol.insert(row.symbol.clone(), value);
        }
        let previous_yau = yau_fixed_by_symbol.get(&row.symbol).copied().unwrap_or(0.0);
        let yau_pressure_fixed = net_potential
            .map(|measurement| {
                let correction = measurement - previous_yau;
                0.88 * previous_yau + 0.12 * correction.tanh()
            })
            .and_then(finite);
        if let Some(value) = yau_pressure_fixed {
            yau_fixed_by_symbol.insert(row.symbol.clone(), value);
        }
        let potential_barrier_distance = net_potential
            .zip(liquidity_barrier)
            .and_then(|(net, barrier)| finite(net.abs() - barrier.abs()));

        let state = PotentialStateRow {
            run_tag: row.run_tag.clone(),
            out_tag: out_tag.clone(),
            timestamp_utc: row.timestamp_utc.clone(),
            timestamp_us: row.timestamp_us,
            symbol: row.symbol.clone(),
            mid_open: row.mid_open,
            mid_high: row.mid_high,
            mid_low: row.mid_low,
            mid_close: row.mid_close,
            spread_bps: row.spread_bps,
            depth_bid_25: row.depth_bid_25,
            depth_ask_25: row.depth_ask_25,
            phi_bid,
            phi_ask,
            net_potential,
            potential_gradient,
            potential_curvature,
            energy_release,
            liquidity_barrier,
            queue_depth_pressure,
            cancellation_withdrawal_energy,
            replenish_relaxation,
            spread_depth_resistance,
            cross_venue_forcing,
            event_time_decay,
            kalman_pressure_fixed,
            yau_pressure_fixed,
            potential_barrier_distance,
            guardrail: GUARDRAIL.to_string(),
        };
        prev_by_symbol.insert(row.symbol.clone(), state.clone());
        out.push(state);
    }
    out
}

fn build_filter_states(
    config: &V9Config,
    rows: &[PotentialStateRow],
) -> Result<(Vec<FilterParamRow>, Vec<FilterStateRow>)> {
    let mut params = Vec::new();
    let mut filter_rows = Vec::new();
    let by_symbol = potential_by_symbol(rows);
    let out_tag = out_tag(config);
    for fold in FOLDS {
        for &symbol in DEFAULT_SYMBOLS {
            let Some(symbol_rows) = by_symbol.get(symbol) else {
                continue;
            };
            let train_end = fold.train_end_us()?;
            let valid_start = fold.valid_start_us()?;
            let valid_end = fold.valid_end_us()?;
            let train = symbol_rows
                .iter()
                .copied()
                .filter(|row| row.timestamp_us <= train_end)
                .collect::<Vec<_>>();
            let valid = symbol_rows
                .iter()
                .copied()
                .filter(|row| row.timestamp_us >= valid_start && row.timestamp_us <= valid_end)
                .collect::<Vec<_>>();
            if train.is_empty() || valid.is_empty() {
                continue;
            }
            let param = fit_filter_params(config, fold, symbol, &train);
            let mut kalman = 0.0;
            let mut yau = 0.0;
            let mut initialized = false;
            for row in valid {
                let measurement = row.net_potential.unwrap_or(0.0);
                if !initialized {
                    kalman = measurement;
                    yau = measurement;
                    initialized = true;
                }
                let prediction = param.kalman_decay * kalman;
                let innovation = measurement - prediction;
                kalman = prediction + param.kalman_gain * innovation;

                let yau_prediction = param.yau_decay * yau;
                let yau_error = measurement - yau_prediction;
                let log_correction = param.yau_gain * yau_error
                    - 0.5 * param.yau_gain * param.yau_gain * yau_prediction * yau_prediction;
                yau = yau_prediction + log_correction.tanh();
                if (yau - measurement).abs() > param.yau_restart_width {
                    yau = 0.5 * yau + 0.5 * measurement;
                }

                filter_rows.push(FilterStateRow {
                    run_tag: config.run_tag.clone(),
                    out_tag: out_tag.clone(),
                    fold: fold.name.to_string(),
                    timestamp_utc: row.timestamp_utc.clone(),
                    timestamp_us: row.timestamp_us,
                    symbol: symbol.to_string(),
                    mid_open: row.mid_open,
                    mid_high: row.mid_high,
                    mid_low: row.mid_low,
                    mid_close: row.mid_close,
                    spread_bps: row.spread_bps,
                    depth_bid_25: row.depth_bid_25,
                    depth_ask_25: row.depth_ask_25,
                    net_potential: row.net_potential,
                    energy_release: row.energy_release,
                    liquidity_barrier: row.liquidity_barrier,
                    potential_barrier_distance: row.potential_barrier_distance,
                    replenish_relaxation: row.replenish_relaxation,
                    cancellation_withdrawal_energy: row.cancellation_withdrawal_energy,
                    kalman_pressure: finite(kalman),
                    yau_pressure: finite(yau),
                    kalman_innovation: finite(innovation),
                    yau_log_likelihood_delta: finite(log_correction),
                    potential_bucket_train_fit: bucket_label(
                        measurement,
                        param.net_low,
                        param.net_high,
                    ),
                    hidden_bucket_train_fit: bucket_label(
                        kalman,
                        param.hidden_low,
                        param.hidden_high,
                    ),
                    guardrail: GUARDRAIL.to_string(),
                });
            }
            params.push(param);
        }
    }
    Ok((params, filter_rows))
}

fn fit_filter_params(
    config: &V9Config,
    fold: &FoldDef,
    symbol: &str,
    train: &[&PotentialStateRow],
) -> FilterParamRow {
    let net = train
        .iter()
        .filter_map(|row| row.net_potential)
        .collect::<Vec<_>>();
    let energy = train
        .iter()
        .filter_map(|row| row.energy_release)
        .collect::<Vec<_>>();
    let barrier = train
        .iter()
        .filter_map(|row| row.potential_barrier_distance)
        .collect::<Vec<_>>();
    let gradient = train
        .iter()
        .filter_map(|row| row.potential_gradient)
        .collect::<Vec<_>>();
    let diffs = net
        .windows(2)
        .map(|pair| pair[1] - pair[0])
        .collect::<Vec<_>>();
    let measurement_variance = variance(&net).unwrap_or(1.0).max(1e-6);
    let process_variance = variance(&diffs)
        .unwrap_or(measurement_variance * 0.2)
        .max(1e-6);
    let kalman_gain = (process_variance.sqrt()
        / (process_variance.sqrt() + measurement_variance.sqrt()))
    .clamp(0.05, 0.65);
    let kalman_decay = lag_corr(&net).unwrap_or(0.85).clamp(0.20, 0.98);
    let yau_gain = (1.0 / (1.0 + measurement_variance.sqrt())).clamp(0.05, 0.55);
    let yau_decay = (0.5 * kalman_decay + 0.45).clamp(0.20, 0.98);
    let yau_restart_width = stddev(&net).unwrap_or(1.0).max(0.05) * 2.5;
    let hidden_proxy = train
        .iter()
        .filter_map(|row| row.kalman_pressure_fixed)
        .collect::<Vec<_>>();
    FilterParamRow {
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        fold: fold.name.to_string(),
        symbol: symbol.to_string(),
        train_count: train.len(),
        measurement_variance,
        process_variance,
        kalman_gain,
        kalman_decay,
        yau_gain,
        yau_decay,
        yau_restart_width,
        net_low: quantile_opt(&net, 0.20).unwrap_or(-0.5),
        net_high: quantile_opt(&net, 0.80).unwrap_or(0.5),
        energy_high: quantile_opt(&energy, 0.80).unwrap_or(0.5),
        barrier_high: quantile_opt(&barrier, 0.80).unwrap_or(0.0),
        gradient_low: quantile_opt(&gradient, 0.20).unwrap_or(-0.1),
        gradient_high: quantile_opt(&gradient, 0.80).unwrap_or(0.1),
        hidden_low: quantile_opt(&hidden_proxy, 0.20).unwrap_or(-0.25),
        hidden_high: quantile_opt(&hidden_proxy, 0.80).unwrap_or(0.25),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn run_episode_backtests(
    config: &V9Config,
    filter_rows: &[FilterStateRow],
) -> Result<EpisodeOutputs> {
    let mut anchor_candidates = Vec::new();
    let mut trades = Vec::new();
    let mut base_trade_number = 0usize;
    let anchor_specs = anchor_specs();
    let by_fold_symbol = filter_by_fold_symbol(filter_rows);

    for fold in FOLDS {
        for &symbol in DEFAULT_SYMBOLS {
            let Some(rows) = by_fold_symbol.get(&(fold.name.to_string(), symbol.to_string()))
            else {
                continue;
            };
            for anchor in &anchor_specs {
                for &side in DEFAULT_SIDES {
                    let (signals, fit_detail, selected_minutes, starts) =
                        build_anchor_signals(config, rows, anchor, side);
                    let starts_per_day = starts as f64 / fold.day_count()?;
                    anchor_candidates.push(AnchorCandidateRow {
                        run_tag: config.run_tag.clone(),
                        out_tag: out_tag(config),
                        fold: fold.name.to_string(),
                        symbol: symbol.to_string(),
                        anchor_type: anchor.anchor_type.to_string(),
                        side: side.to_string(),
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
                                let bases = simulate_base_trades(
                                    config,
                                    &signals,
                                    anchor,
                                    side,
                                    fold,
                                    tp_bps,
                                    sl_bps,
                                    timeout_minutes,
                                    &build_anchor_signal_thresholds(
                                        &fit_detail,
                                        tp_bps,
                                        sl_bps,
                                        timeout_minutes,
                                    ),
                                    &mut base_trade_number,
                                );
                                for execution_model in &config.execution_models {
                                    for base in &bases {
                                        trades.push(expand_execution_trade(
                                            config,
                                            base,
                                            execution_model,
                                        ));
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    let daily = aggregate_daily(&trades);
    let summary = aggregate_summary(config, &trades, &daily)?;
    let exit_reasons = build_exit_reasons(&trades);
    let fold_stability = build_fold_stability(&summary);
    let non_overlap = build_non_overlap(&trades, &summary);
    let parameter_sensitivity = build_parameter_sensitivity(&summary);
    let single_day_dependence = build_single_day_dependence(&daily);
    let failure_diagnostics = build_failure_diagnostics(&summary, &fold_stability);
    let negative_controls = build_negative_controls(&summary, &trades);
    Ok(EpisodeOutputs {
        anchor_candidates,
        trades,
        daily,
        summary,
        exit_reasons,
        fold_stability,
        non_overlap,
        parameter_sensitivity,
        single_day_dependence,
        failure_diagnostics,
        negative_controls,
    })
}

fn anchor_specs() -> Vec<AnchorSpec> {
    vec![
        AnchorSpec {
            anchor_type: "pre_event",
            description: "potential gradient builds before the barrier break",
        },
        AnchorSpec {
            anchor_type: "event",
            description: "energy release coincides with signed potential pressure",
        },
        AnchorSpec {
            anchor_type: "post_event",
            description: "post-shock replenishment/relaxation after a potential event",
        },
        AnchorSpec {
            anchor_type: "first_passage",
            description: "hidden pressure crosses a train-fitted state boundary",
        },
        AnchorSpec {
            anchor_type: "potential_barrier_break",
            description: "absolute potential clears the train-fitted liquidity barrier",
        },
    ]
}

fn build_anchor_signals(
    config: &V9Config,
    rows: &[&FilterStateRow],
    anchor: &AnchorSpec,
    side: &str,
) -> (Vec<SignalRow>, String, usize, usize) {
    let raw = rows
        .iter()
        .enumerate()
        .map(|(idx, _row)| anchor_passes(rows, idx, anchor, side))
        .collect::<Vec<_>>();
    let debounced = debounce_gate(
        &raw,
        config.debounce_on_minutes,
        config.debounce_off_minutes,
    );
    let mut selected_minutes = 0usize;
    let signals = rows
        .iter()
        .zip(debounced)
        .map(|(row, selected)| {
            if selected {
                selected_minutes += 1;
            }
            SignalRow {
                timestamp_utc: row.timestamp_utc.clone(),
                timestamp_us: row.timestamp_us,
                symbol: row.symbol.clone(),
                mid_open: row.mid_open,
                mid_high: row.mid_high,
                mid_low: row.mid_low,
                mid_close: row.mid_close,
                queue_fill_probability: queue_fill_probability(row),
                liquidity_barrier: row.liquidity_barrier.unwrap_or(0.0).abs(),
                gate_selected: selected,
            }
        })
        .collect::<Vec<_>>();
    let starts = count_debounced_starts(&signals);
    let fit_detail = format!(
        "{}; side={}; train-fitted buckets: net/energy/barrier/hidden from filter_params",
        anchor.description, side
    );
    (signals, fit_detail, selected_minutes, starts)
}

fn anchor_passes(rows: &[&FilterStateRow], idx: usize, anchor: &AnchorSpec, side: &str) -> bool {
    let row = rows[idx];
    let net = row.net_potential.unwrap_or(0.0);
    let energy = row.energy_release.unwrap_or(0.0);
    let barrier = row.potential_barrier_distance.unwrap_or(0.0);
    let kalman = row.kalman_pressure.unwrap_or(0.0);
    let yau = row.yau_pressure.unwrap_or(0.0);
    let hidden = 0.5 * kalman + 0.5 * yau;
    let hidden_high = row.hidden_bucket_train_fit == "high";
    let hidden_low = row.hidden_bucket_train_fit == "low";
    let potential_high = row.potential_bucket_train_fit == "high";
    let potential_low = row.potential_bucket_train_fit == "low";
    let prev = idx.checked_sub(1).and_then(|prev| rows.get(prev).copied());
    let prev_hidden = prev
        .map(|prev| {
            0.5 * prev.kalman_pressure.unwrap_or(0.0) + 0.5 * prev.yau_pressure.unwrap_or(0.0)
        })
        .unwrap_or(hidden);
    let prev_energy = prev.and_then(|prev| prev.energy_release).unwrap_or(0.0);
    let replenish = row.replenish_relaxation.unwrap_or(0.0);
    let cancel = row.cancellation_withdrawal_energy.unwrap_or(0.0);
    let signed = if side == "long" { 1.0 } else { -1.0 };
    match anchor.anchor_type {
        "pre_event" => {
            signed * net > 0.0
                && signed * (hidden - prev_hidden) > 0.02
                && energy > 0.25
                && barrier > -0.15
        }
        "event" => {
            energy > 0.45
                && ((side == "long" && potential_high) || (side == "short" && potential_low))
        }
        "post_event" => {
            prev_energy > 0.45
                && replenish > cancel * 0.7
                && ((side == "long" && net > 0.0) || (side == "short" && net < 0.0))
        }
        "first_passage" => {
            if side == "long" {
                hidden_high && prev_hidden <= hidden
            } else {
                hidden_low && prev_hidden >= hidden
            }
        }
        "potential_barrier_break" => {
            barrier > 0.0
                && ((side == "long" && potential_high) || (side == "short" && potential_low))
        }
        _ => false,
    }
}

#[allow(clippy::too_many_arguments)]
fn simulate_base_trades(
    config: &V9Config,
    rows: &[SignalRow],
    anchor: &AnchorSpec,
    side: &str,
    fold: &FoldDef,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    thresholds: &str,
    base_trade_number: &mut usize,
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
                idx += 1;
                prev_selected = row.gate_selected;
                continue;
            }
            *base_trade_number += 1;
            if let Some(trade) = simulate_base_episode(
                config,
                rows,
                anchor,
                side,
                fold,
                entry_idx,
                idx,
                tp_bps,
                sl_bps,
                timeout_minutes,
                thresholds,
                *base_trade_number,
            ) {
                idx = trade_exit_index(rows, trade.exit_timestamp_us)
                    .unwrap_or(entry_idx)
                    .saturating_add(config.cooldown_minutes);
                out.push(trade);
                prev_selected = false;
                continue;
            }
        }
        prev_selected = row.gate_selected;
        idx += 1;
    }
    out
}

#[allow(clippy::too_many_arguments)]
fn simulate_base_episode(
    config: &V9Config,
    rows: &[SignalRow],
    anchor: &AnchorSpec,
    side: &str,
    fold: &FoldDef,
    entry_idx: usize,
    signal_idx: usize,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    thresholds: &str,
    trade_number: usize,
) -> Option<BaseTrade> {
    let entry = &rows[entry_idx];
    let entry_price = entry
        .mid_open
        .or(entry.mid_close)
        .filter(|value| valid_price(*value))?;
    let long = side == "long";
    let tp_price = if long {
        entry_price * (1.0 + tp_bps as f64 / 10_000.0)
    } else {
        entry_price * (1.0 - tp_bps as f64 / 10_000.0)
    };
    let sl_price = if long {
        entry_price * (1.0 - sl_bps as f64 / 10_000.0)
    } else {
        entry_price * (1.0 + sl_bps as f64 / 10_000.0)
    };
    let mut max_favorable = 0.0;
    let mut max_adverse = 0.0;
    let mut same_bar_ambiguous = false;
    let mut exit_price = entry_price;
    let mut exit_reason = "fold_end";
    let mut exit_idx = entry_idx;
    let mut prev_idx = entry_idx;

    for idx in entry_idx..rows.len() {
        let row = &rows[idx];
        if idx > entry_idx {
            let prev_ts = rows[prev_idx].timestamp_us;
            if row.timestamp_us.saturating_sub(prev_ts) > MINUTE_US {
                let prev = &rows[prev_idx];
                exit_idx = prev_idx;
                exit_price = prev.mid_close.or(prev.mid_open).unwrap_or(entry_price);
                exit_reason = "data_gap";
                break;
            }
        }
        let high = row.mid_high.or(row.mid_close).or(row.mid_open);
        let low = row.mid_low.or(row.mid_close).or(row.mid_open);
        let close = row.mid_close.or(row.mid_open).unwrap_or(entry_price);
        let hit_tp = if long {
            high.is_some_and(|price| price >= tp_price)
        } else {
            low.is_some_and(|price| price <= tp_price)
        };
        let hit_sl = if long {
            low.is_some_and(|price| price <= sl_price)
        } else {
            high.is_some_and(|price| price >= sl_price)
        };
        exit_idx = idx;
        let favorable = if long {
            high.map(|price| price / entry_price - 1.0)
        } else {
            low.map(|price| entry_price / price - 1.0)
        }
        .unwrap_or(0.0)
            * 10_000.0;
        let adverse = if long {
            low.map(|price| price / entry_price - 1.0)
        } else {
            high.map(|price| entry_price / price - 1.0)
        }
        .unwrap_or(0.0)
            * 10_000.0;
        if favorable.is_finite() {
            max_favorable = f64::max(max_favorable, favorable);
        }
        if adverse.is_finite() {
            max_adverse = f64::min(max_adverse, adverse);
        }
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
        let held_minutes = rows[idx].timestamp_us.saturating_sub(entry.timestamp_us) / MINUTE_US;
        if held_minutes >= config.min_hold_minutes as u64 && !row.gate_selected {
            exit_price = close;
            exit_reason = "gate_off";
            break;
        }
        if held_minutes >= timeout_minutes as u64 {
            exit_price = close;
            exit_reason = "timeout";
            break;
        }
        prev_idx = idx;
    }
    let gross_bps = if long {
        (exit_price / entry_price - 1.0) * 10_000.0
    } else {
        (entry_price / exit_price - 1.0) * 10_000.0
    };
    Some(BaseTrade {
        fold: fold.name.to_string(),
        symbol: entry.symbol.clone(),
        anchor_type: anchor.anchor_type.to_string(),
        side: side.to_string(),
        tp_bps,
        sl_bps,
        timeout_minutes,
        signal_timestamp_utc: rows[signal_idx].timestamp_utc.clone(),
        signal_timestamp_us: rows[signal_idx].timestamp_us,
        entry_timestamp_utc: entry.timestamp_utc.clone(),
        entry_timestamp_us: entry.timestamp_us,
        exit_timestamp_utc: rows[exit_idx].timestamp_utc.clone(),
        exit_timestamp_us: rows[exit_idx].timestamp_us,
        entry_price,
        exit_price,
        exit_reason: exit_reason.to_string(),
        gross_bps,
        duration_minutes: rows[exit_idx]
            .timestamp_us
            .saturating_sub(entry.timestamp_us) as f64
            / MINUTE_US as f64,
        mfe_bps: max_favorable,
        mae_bps: max_adverse,
        same_bar_ambiguous,
        queue_fill_probability: entry.queue_fill_probability,
        liquidity_barrier: entry.liquidity_barrier,
        thresholds_fit_on_train: thresholds.to_string(),
        trade_number,
    })
}

fn expand_execution_trade(config: &V9Config, base: &BaseTrade, execution_model: &str) -> TradeRow {
    let (cost_bps, latency_bps, slippage_bps, queue_penalty_bps) =
        execution_cost_bps(base, execution_model, config.fee_bps);
    let net_bps = base.gross_bps - cost_bps;
    let pnl_quote = config.notional_quote * net_bps / 10_000.0;
    TradeRow {
        trade_id: format!(
            "{}|{}|{}|{}|{}|{}|tp{}|sl{}|to{}|{}",
            config.run_tag,
            base.fold,
            base.symbol,
            base.anchor_type,
            base.side,
            execution_model,
            base.tp_bps,
            base.sl_bps,
            base.timeout_minutes,
            base.trade_number
        ),
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        fold: base.fold.clone(),
        symbol: base.symbol.clone(),
        anchor_type: base.anchor_type.clone(),
        side: base.side.clone(),
        execution_model: execution_model.to_string(),
        notional_quote: config.notional_quote,
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
        latency_bps,
        slippage_bps,
        queue_penalty_bps,
        net_bps,
        pnl_quote,
        duration_minutes: base.duration_minutes,
        mfe_bps: base.mfe_bps,
        mae_bps: base.mae_bps,
        same_bar_ambiguous: base.same_bar_ambiguous,
        queue_fill_probability: base.queue_fill_probability,
        liquidity_barrier: base.liquidity_barrier,
        thresholds_fit_on_train: base.thresholds_fit_on_train.clone(),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn execution_cost_bps(
    base: &BaseTrade,
    execution_model: &str,
    fee_bps: f64,
) -> (f64, f64, f64, f64) {
    let spread = base.liquidity_barrier.abs().min(10.0);
    let queue_penalty = (1.0 - base.queue_fill_probability).max(0.0) * 2.5;
    match execution_model {
        "mid_research" => (0.0, 0.0, 0.0, 0.0),
        "maker_light" => {
            let latency = 0.25 + spread * 0.05;
            let slippage = 0.25;
            let cost = fee_bps + latency + slippage + queue_penalty;
            (cost, latency, slippage, queue_penalty)
        }
        "taker_spread" => {
            let latency = 0.50 + spread * 0.08;
            let slippage = spread.max(0.5);
            let cost = fee_bps + latency + slippage;
            (cost, latency, slippage, 0.0)
        }
        "wide_stress" => {
            let latency = 1.25 + spread * 0.15;
            let slippage = 2.0 * spread.max(1.0) + 3.0;
            let cost = fee_bps + latency + slippage + queue_penalty;
            (cost, latency, slippage, queue_penalty)
        }
        _ => (fee_bps, 0.0, 0.0, 0.0),
    }
}

fn aggregate_daily(trades: &[TradeRow]) -> Vec<DailyRow> {
    let mut groups: BTreeMap<
        (
            String,
            String,
            String,
            String,
            String,
            u32,
            u32,
            u32,
            String,
        ),
        Vec<&TradeRow>,
    > = BTreeMap::new();
    for trade in trades {
        let date = trade
            .entry_timestamp_utc
            .chars()
            .take(10)
            .collect::<String>();
        groups
            .entry((
                trade.fold.clone(),
                date,
                trade.symbol.clone(),
                trade.anchor_type.clone(),
                trade.side.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_minutes,
                trade.execution_model.clone(),
            ))
            .or_default()
            .push(trade);
    }
    groups
        .into_iter()
        .map(
            |((fold, date, symbol, anchor_type, side, tp, sl, timeout, execution), rows)| {
                let pnl = rows.iter().map(|trade| trade.pnl_quote).collect::<Vec<_>>();
                let net = rows.iter().map(|trade| trade.net_bps).collect::<Vec<_>>();
                DailyRow {
                    fold,
                    date,
                    symbol,
                    anchor_type,
                    side,
                    execution_model: execution,
                    tp_bps: tp,
                    sl_bps: sl,
                    timeout_minutes: timeout,
                    trade_count: rows.len(),
                    pnl_quote: pnl.iter().sum(),
                    avg_net_bps: mean(&net),
                    max_intraday_drawdown_quote: max_drawdown(&pnl),
                    guardrail: GUARDRAIL.to_string(),
                }
            },
        )
        .collect()
}

fn aggregate_summary(
    config: &V9Config,
    trades: &[TradeRow],
    daily: &[DailyRow],
) -> Result<Vec<SummaryRow>> {
    let mut out = Vec::new();
    let mut fold_groups: BTreeMap<
        (String, String, String, String, String, u32, u32, u32),
        Vec<&TradeRow>,
    > = BTreeMap::new();
    let mut all_groups: BTreeMap<(String, String, String, String, u32, u32, u32), Vec<&TradeRow>> =
        BTreeMap::new();
    for trade in trades {
        fold_groups
            .entry((
                trade.fold.clone(),
                trade.symbol.clone(),
                trade.anchor_type.clone(),
                trade.side.clone(),
                trade.execution_model.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_minutes,
            ))
            .or_default()
            .push(trade);
        all_groups
            .entry((
                trade.symbol.clone(),
                trade.anchor_type.clone(),
                trade.side.clone(),
                trade.execution_model.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_minutes,
            ))
            .or_default()
            .push(trade);
    }
    for ((fold, symbol, anchor, side, execution, tp, sl, timeout), rows) in fold_groups {
        let day_count = FOLDS
            .iter()
            .find(|def| def.name == fold)
            .map(FoldDef::validation_dates)
            .transpose()?
            .map(|dates| dates.len())
            .unwrap_or(0);
        let day_rows = daily
            .iter()
            .filter(|row| {
                row.fold == fold
                    && row.symbol == symbol
                    && row.anchor_type == anchor
                    && row.side == side
                    && row.execution_model == execution
                    && row.tp_bps == tp
                    && row.sl_bps == sl
                    && row.timeout_minutes == timeout
            })
            .collect::<Vec<_>>();
        out.push(summary_from_group(
            config, "fold", &fold, &symbol, &anchor, &side, &execution, tp, sl, timeout, day_count,
            &rows, &day_rows,
        ));
    }
    for ((symbol, anchor, side, execution, tp, sl, timeout), rows) in all_groups {
        let day_rows = daily
            .iter()
            .filter(|row| {
                row.symbol == symbol
                    && row.anchor_type == anchor
                    && row.side == side
                    && row.execution_model == execution
                    && row.tp_bps == tp
                    && row.sl_bps == sl
                    && row.timeout_minutes == timeout
            })
            .collect::<Vec<_>>();
        out.push(summary_from_group(
            config, "all", "all", &symbol, &anchor, &side, &execution, tp, sl, timeout, 10, &rows,
            &day_rows,
        ));
    }
    Ok(out)
}

#[allow(clippy::too_many_arguments)]
fn summary_from_group(
    config: &V9Config,
    scope: &str,
    fold: &str,
    symbol: &str,
    anchor: &str,
    side: &str,
    execution: &str,
    tp: u32,
    sl: u32,
    timeout: u32,
    days: usize,
    trades: &[&TradeRow],
    daily: &[&DailyRow],
) -> SummaryRow {
    let pnl = trades
        .iter()
        .map(|trade| trade.pnl_quote)
        .collect::<Vec<_>>();
    let gross = trades
        .iter()
        .map(|trade| trade.gross_bps)
        .collect::<Vec<_>>();
    let cost = trades
        .iter()
        .map(|trade| trade.cost_bps)
        .collect::<Vec<_>>();
    let net = trades.iter().map(|trade| trade.net_bps).collect::<Vec<_>>();
    let duration = trades
        .iter()
        .map(|trade| trade.duration_minutes)
        .collect::<Vec<_>>();
    let daily_pnl = daily.iter().map(|row| row.pnl_quote).collect::<Vec<_>>();
    let total_pnl = pnl.iter().sum::<f64>();
    let positive_days = daily.iter().filter(|row| row.pnl_quote > 0.0).count();
    let mut exits = BTreeMap::new();
    for trade in trades {
        *exits.entry(trade.exit_reason.clone()).or_insert(0usize) += 1;
    }
    SummaryRow {
        summary_scope: scope.to_string(),
        fold: fold.to_string(),
        symbol: symbol.to_string(),
        anchor_type: anchor.to_string(),
        side: side.to_string(),
        execution_model: execution.to_string(),
        tp_bps: tp,
        sl_bps: sl,
        timeout_minutes: timeout,
        notional_quote: config.notional_quote,
        days,
        trade_count: trades.len(),
        total_pnl_quote: total_pnl,
        avg_daily_pnl_quote: if days > 0 {
            total_pnl / days as f64
        } else {
            0.0
        },
        median_daily_pnl_quote: median(&daily_pnl).unwrap_or(0.0),
        positive_day_rate: (days > 0).then_some(positive_days as f64 / days as f64),
        max_drawdown_quote: max_drawdown(&daily_pnl),
        trades_per_day: if days > 0 {
            trades.len() as f64 / days as f64
        } else {
            0.0
        },
        win_rate: win_rate_bps(&pnl),
        profit_factor: profit_factor(&pnl),
        median_trade_net_bps: median(&net),
        avg_gross_bps: mean(&gross),
        avg_cost_bps: mean(&cost),
        avg_net_bps: mean(&net),
        median_duration_minutes: median(&duration),
        exposure_minutes: duration.iter().sum(),
        turnover_quote: trades.len() as f64 * config.notional_quote,
        target_frequency_pass: {
            let per_day = if days > 0 {
                trades.len() as f64 / days as f64
            } else {
                0.0
            };
            (1.0..=5.0).contains(&per_day)
        },
        ambiguous_trade_count: trades
            .iter()
            .filter(|trade| trade.same_bar_ambiguous)
            .count(),
        ambiguous_trade_rate: if trades.is_empty() {
            0.0
        } else {
            trades
                .iter()
                .filter(|trade| trade.same_bar_ambiguous)
                .count() as f64
                / trades.len() as f64
        },
        exit_reason_counts_json: serde_json::to_string(&exits).unwrap_or_else(|_| "{}".to_string()),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn build_exit_reasons(trades: &[TradeRow]) -> Vec<ExitReasonRow> {
    let mut groups: BTreeMap<
        (
            String,
            String,
            String,
            String,
            String,
            u32,
            u32,
            u32,
            String,
        ),
        Vec<&TradeRow>,
    > = BTreeMap::new();
    for trade in trades {
        groups
            .entry((
                "all".to_string(),
                trade.symbol.clone(),
                trade.anchor_type.clone(),
                trade.side.clone(),
                trade.execution_model.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_minutes,
                trade.exit_reason.clone(),
            ))
            .or_default()
            .push(trade);
    }
    groups
        .into_iter()
        .map(
            |((scope, symbol, anchor, side, execution, tp, sl, timeout, reason), rows)| {
                let pnl = rows.iter().map(|trade| trade.pnl_quote).sum();
                let net = rows.iter().map(|trade| trade.net_bps).collect::<Vec<_>>();
                ExitReasonRow {
                    summary_scope: scope,
                    fold: "all".to_string(),
                    symbol,
                    anchor_type: anchor,
                    side,
                    execution_model: execution,
                    tp_bps: tp,
                    sl_bps: sl,
                    timeout_minutes: timeout,
                    exit_reason: reason,
                    trade_count: rows.len(),
                    pnl_quote: pnl,
                    avg_net_bps: mean(&net),
                }
            },
        )
        .collect()
}

fn build_fold_stability(summary: &[SummaryRow]) -> Vec<FoldStabilityRow> {
    let folds = summary
        .iter()
        .filter(|row| row.summary_scope == "fold")
        .collect::<Vec<_>>();
    let mut groups: BTreeMap<(String, String, String, String, u32, u32, u32), Vec<&SummaryRow>> =
        BTreeMap::new();
    for row in folds {
        groups
            .entry((
                row.symbol.clone(),
                row.anchor_type.clone(),
                row.side.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
            ))
            .or_default()
            .push(row);
    }
    groups
        .into_iter()
        .map(
            |((symbol, anchor, side, execution, tp, sl, timeout), rows)| {
                let pnl_for = |fold: &str| {
                    rows.iter()
                        .find(|row| row.fold == fold)
                        .map(|row| row.total_pnl_quote)
                };
                let fold1 = pnl_for("fold1");
                let fold2 = pnl_for("fold2");
                let fold3 = pnl_for("fold3");
                let positive_fold_count = [fold1, fold2, fold3]
                    .iter()
                    .filter(|value| value.is_some_and(|v| v >= 0.0))
                    .count();
                FoldStabilityRow {
                    symbol,
                    anchor_type: anchor,
                    side,
                    execution_model: execution,
                    tp_bps: tp,
                    sl_bps: sl,
                    timeout_minutes: timeout,
                    fold1_pnl: fold1,
                    fold2_pnl: fold2,
                    fold3_pnl: fold3,
                    fold2_fold3_both_nonnegative: fold2.is_some_and(|v| v >= 0.0)
                        && fold3.is_some_and(|v| v >= 0.0),
                    positive_fold_count,
                    guardrail: GUARDRAIL.to_string(),
                }
            },
        )
        .collect()
}

fn build_non_overlap(trades: &[TradeRow], summary: &[SummaryRow]) -> Vec<NonOverlapRow> {
    summary
        .iter()
        .filter(|row| row.summary_scope == "all")
        .map(|row| {
            let mut rows = trades
                .iter()
                .filter(|trade| {
                    trade.symbol == row.symbol
                        && trade.anchor_type == row.anchor_type
                        && trade.side == row.side
                        && trade.execution_model == row.execution_model
                        && trade.tp_bps == row.tp_bps
                        && trade.sl_bps == row.sl_bps
                        && trade.timeout_minutes == row.timeout_minutes
                })
                .collect::<Vec<_>>();
            rows.sort_by_key(|trade| trade.entry_timestamp_us);
            let mut violations = 0usize;
            for pair in rows.windows(2) {
                if pair[1].entry_timestamp_us < pair[0].exit_timestamp_us {
                    violations += 1;
                }
            }
            NonOverlapRow {
                symbol: row.symbol.clone(),
                anchor_type: row.anchor_type.clone(),
                side: row.side.clone(),
                execution_model: row.execution_model.clone(),
                tp_bps: row.tp_bps,
                sl_bps: row.sl_bps,
                timeout_minutes: row.timeout_minutes,
                overlap_violations: violations,
                non_overlap_mode: "single_position_per_config_with_cooldown".to_string(),
                guardrail: GUARDRAIL.to_string(),
            }
        })
        .collect()
}

fn build_parameter_sensitivity(summary: &[SummaryRow]) -> Vec<ParameterSensitivityRow> {
    let mut groups: BTreeMap<(String, String, String, String), Vec<&SummaryRow>> = BTreeMap::new();
    for row in summary.iter().filter(|row| row.summary_scope == "all") {
        groups
            .entry((
                row.symbol.clone(),
                row.anchor_type.clone(),
                row.side.clone(),
                row.execution_model.clone(),
            ))
            .or_default()
            .push(row);
    }
    groups
        .into_iter()
        .map(|((symbol, anchor, side, execution), rows)| {
            let pnl = rows
                .iter()
                .map(|row| row.total_pnl_quote)
                .collect::<Vec<_>>();
            ParameterSensitivityRow {
                symbol,
                anchor_type: anchor,
                side,
                execution_model: execution,
                configs_tested: rows.len(),
                positive_configs: rows.iter().filter(|row| row.total_pnl_quote > 0.0).count(),
                best_total_pnl_quote: pnl.iter().copied().fold(f64::NEG_INFINITY, f64::max),
                median_total_pnl_quote: median(&pnl),
                pnl_iqr_quote: quantile_opt(&pnl, 0.75)
                    .zip(quantile_opt(&pnl, 0.25))
                    .map(|(hi, lo)| hi - lo),
                guardrail: GUARDRAIL.to_string(),
            }
        })
        .collect()
}

fn build_single_day_dependence(daily: &[DailyRow]) -> Vec<SingleDayDependenceRow> {
    let mut groups: BTreeMap<(String, String, String, String, u32, u32, u32), Vec<&DailyRow>> =
        BTreeMap::new();
    for row in daily {
        groups
            .entry((
                row.symbol.clone(),
                row.anchor_type.clone(),
                row.side.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
            ))
            .or_default()
            .push(row);
    }
    groups
        .into_iter()
        .map(
            |((symbol, anchor, side, execution, tp, sl, timeout), rows)| {
                let total = rows.iter().map(|row| row.pnl_quote).sum::<f64>();
                let max_day = rows
                    .iter()
                    .map(|row| row.pnl_quote)
                    .fold(f64::NEG_INFINITY, f64::max);
                let positive = rows.iter().map(|row| row.pnl_quote.max(0.0)).sum::<f64>();
                let share = (positive > 0.0).then_some(max_day.max(0.0) / positive);
                SingleDayDependenceRow {
                    symbol,
                    anchor_type: anchor,
                    side,
                    execution_model: execution,
                    tp_bps: tp,
                    sl_bps: sl,
                    timeout_minutes: timeout,
                    total_pnl_quote: total,
                    max_day_pnl_quote: max_day,
                    max_day_share_of_positive_pnl: share,
                    dependence_flag: if share.is_some_and(|v| v > 0.65) {
                        "single_day_dependent".to_string()
                    } else {
                        "not_single_day_dominated".to_string()
                    },
                    guardrail: GUARDRAIL.to_string(),
                }
            },
        )
        .collect()
}

fn build_failure_diagnostics(
    summary: &[SummaryRow],
    stability: &[FoldStabilityRow],
) -> Vec<FailureDiagnosticRow> {
    let stable = stability
        .iter()
        .map(|row| {
            (
                row.symbol.clone(),
                row.anchor_type.clone(),
                row.side.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
                row.fold2_fold3_both_nonnegative,
            )
        })
        .collect::<HashSet<_>>();
    summary
        .iter()
        .filter(|row| row.summary_scope == "all")
        .map(|row| {
            let fold_ok = stable.contains(&(
                row.symbol.clone(),
                row.anchor_type.clone(),
                row.side.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
                true,
            ));
            let primary_failure = if !row.target_frequency_pass {
                "target_frequency_miss"
            } else if !fold_ok
                && matches!(row.execution_model.as_str(), "maker_light" | "taker_spread")
            {
                "fold_instability"
            } else if row.total_pnl_quote <= 0.0 {
                "after_cost_negative"
            } else if row.max_drawdown_quote > row.total_pnl_quote.abs().max(1.0) {
                "drawdown_dominates"
            } else {
                "passes_basic_research_filters"
            };
            FailureDiagnosticRow {
                symbol: row.symbol.clone(),
                anchor_type: row.anchor_type.clone(),
                side: row.side.clone(),
                execution_model: row.execution_model.clone(),
                tp_bps: row.tp_bps,
                sl_bps: row.sl_bps,
                timeout_minutes: row.timeout_minutes,
                total_pnl_quote: row.total_pnl_quote,
                trades_per_day: row.trades_per_day,
                max_drawdown_quote: row.max_drawdown_quote,
                fold2_fold3_stable: fold_ok,
                target_frequency_pass: row.target_frequency_pass,
                primary_failure: primary_failure.to_string(),
                diagnostic_detail: format!(
                    "pf={} win={} exits={}",
                    fmt_opt(row.profit_factor, 3),
                    fmt_opt(row.win_rate, 3),
                    row.exit_reason_counts_json
                ),
            }
        })
        .collect()
}

fn build_negative_controls(summary: &[SummaryRow], trades: &[TradeRow]) -> Vec<NegativeControlRow> {
    let mut out = Vec::new();
    for row in summary.iter().filter(|row| row.summary_scope == "all") {
        let matching = trades
            .iter()
            .filter(|trade| {
                trade.symbol == row.symbol
                    && trade.anchor_type == row.anchor_type
                    && trade.side == row.side
                    && trade.execution_model == row.execution_model
                    && trade.tp_bps == row.tp_bps
                    && trade.sl_bps == row.sl_bps
                    && trade.timeout_minutes == row.timeout_minutes
            })
            .collect::<Vec<_>>();
        let reversed = matching
            .iter()
            .map(|trade| (-trade.gross_bps - trade.cost_bps) * trade.notional_quote / 10_000.0)
            .sum::<f64>();
        out.push(NegativeControlRow {
            symbol: row.symbol.clone(),
            anchor_type: row.anchor_type.clone(),
            side: row.side.clone(),
            execution_model: row.execution_model.clone(),
            tp_bps: row.tp_bps,
            sl_bps: row.sl_bps,
            timeout_minutes: row.timeout_minutes,
            control_type: "reversed_sign".to_string(),
            base_total_pnl_quote: row.total_pnl_quote,
            control_total_pnl_quote: reversed,
            control_trade_count: matching.len(),
            control_note: "same timestamps and costs, gross return sign reversed".to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
        let shuffled = matching
            .iter()
            .enumerate()
            .map(|(idx, trade)| {
                let sign = if pseudo_shuffle_sign(trade.entry_timestamp_us, idx as u64) {
                    1.0
                } else {
                    -1.0
                };
                (sign * trade.gross_bps.abs() - trade.cost_bps) * trade.notional_quote / 10_000.0
            })
            .sum::<f64>();
        out.push(NegativeControlRow {
            symbol: row.symbol.clone(),
            anchor_type: row.anchor_type.clone(),
            side: row.side.clone(),
            execution_model: row.execution_model.clone(),
            tp_bps: row.tp_bps,
            sl_bps: row.sl_bps,
            timeout_minutes: row.timeout_minutes,
            control_type: "shuffled_timestamp_sign_proxy".to_string(),
            base_total_pnl_quote: row.total_pnl_quote,
            control_total_pnl_quote: shuffled,
            control_trade_count: matching.len(),
            control_note:
                "deterministic timestamp hash flips return signs to proxy shuffled alignment"
                    .to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
        let other_symbol = if row.symbol == "BONK1MUSDC" {
            "BONK1MUSDT"
        } else {
            "BONK1MUSDC"
        };
        let wrong_symbol = summary
            .iter()
            .find(|other| {
                other.summary_scope == "all"
                    && other.symbol == other_symbol
                    && other.anchor_type == row.anchor_type
                    && other.side == row.side
                    && other.execution_model == row.execution_model
                    && other.tp_bps == row.tp_bps
                    && other.sl_bps == row.sl_bps
                    && other.timeout_minutes == row.timeout_minutes
            })
            .map(|other| other.total_pnl_quote)
            .unwrap_or(0.0);
        out.push(NegativeControlRow {
            symbol: row.symbol.clone(),
            anchor_type: row.anchor_type.clone(),
            side: row.side.clone(),
            execution_model: row.execution_model.clone(),
            tp_bps: row.tp_bps,
            sl_bps: row.sl_bps,
            timeout_minutes: row.timeout_minutes,
            control_type: "wrong_symbol_proxy".to_string(),
            base_total_pnl_quote: row.total_pnl_quote,
            control_total_pnl_quote: wrong_symbol,
            control_trade_count: row.trade_count,
            control_note: format!("same gate family evaluated on {other_symbol}"),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    out
}

fn build_spearman_stability(rows: &[PotentialStateRow]) -> Result<Vec<SpearmanRow>> {
    let by_symbol = potential_by_symbol(rows);
    let mut out = Vec::new();
    for fold in FOLDS {
        let valid_start = fold.valid_start_us()?;
        let valid_end = fold.valid_end_us()?;
        for &symbol in DEFAULT_SYMBOLS {
            let Some(symbol_rows) = by_symbol.get(symbol) else {
                continue;
            };
            let close_by_ts = symbol_rows
                .iter()
                .filter_map(|row| row.mid_close.map(|close| (row.timestamp_us, close)))
                .collect::<HashMap<_, _>>();
            let valid = symbol_rows
                .iter()
                .copied()
                .filter(|row| row.timestamp_us >= valid_start && row.timestamp_us <= valid_end)
                .collect::<Vec<_>>();
            for horizon in [5u32, 10, 20, 30] {
                let y = valid
                    .iter()
                    .map(|row| {
                        row.mid_close
                            .zip(
                                close_by_ts
                                    .get(&(row.timestamp_us + horizon as u64 * MINUTE_US))
                                    .copied(),
                            )
                            .and_then(|(cur, future)| {
                                if cur > 0.0 && future > 0.0 {
                                    finite((future / cur - 1.0) * 10_000.0)
                                } else {
                                    None
                                }
                            })
                    })
                    .collect::<Vec<_>>();
                for feature in POTENTIAL_FEATURES {
                    let x = valid
                        .iter()
                        .map(|row| potential_feature(row, feature))
                        .collect::<Vec<_>>();
                    let pairs = x
                        .iter()
                        .zip(y.iter())
                        .filter_map(|(x, y)| x.zip(*y))
                        .collect::<Vec<_>>();
                    if pairs.len() < 30 {
                        continue;
                    }
                    let xs = pairs.iter().map(|pair| pair.0).collect::<Vec<_>>();
                    let ys = pairs.iter().map(|pair| pair.1).collect::<Vec<_>>();
                    let Some(sp) = spearman(&xs, &ys) else {
                        continue;
                    };
                    out.push(SpearmanRow {
                        run_tag: rows
                            .first()
                            .map(|row| row.run_tag.clone())
                            .unwrap_or_default(),
                        out_tag: rows
                            .first()
                            .map(|row| row.out_tag.clone())
                            .unwrap_or_default(),
                        fold: fold.name.to_string(),
                        symbol: symbol.to_string(),
                        horizon_minutes: horizon,
                        feature_name: feature.to_string(),
                        spearman: sp,
                        abs_spearman: sp.abs(),
                        n: pairs.len(),
                        sign: if sp >= 0.0 { "positive" } else { "negative" }.to_string(),
                        guardrail: GUARDRAIL.to_string(),
                    });
                }
            }
        }
    }
    out.sort_by(|a, b| {
        b.abs_spearman
            .total_cmp(&a.abs_spearman)
            .then_with(|| a.horizon_minutes.cmp(&b.horizon_minutes))
    });
    Ok(out)
}

fn read_episode_outputs(paths: &Paths) -> Result<EpisodeOutputs> {
    Ok(EpisodeOutputs {
        anchor_candidates: read_csv_rows(&paths.anchor_candidates)?,
        trades: read_csv_rows(&paths.trades)?,
        daily: read_csv_rows(&paths.daily)?,
        summary: read_csv_rows(&paths.summary)?,
        exit_reasons: read_csv_rows(&paths.exit_reasons)?,
        fold_stability: read_csv_rows(&paths.fold_stability)?,
        non_overlap: read_csv_rows(&paths.non_overlap)?,
        parameter_sensitivity: read_csv_rows(&paths.parameter_sensitivity)?,
        single_day_dependence: read_csv_rows(&paths.single_day_dependence)?,
        failure_diagnostics: read_csv_rows(&paths.failure_diagnostics)?,
        negative_controls: read_csv_rows(&paths.negative_controls)?,
    })
}

fn validate_outputs(
    trades: &[TradeRow],
    daily: &[DailyRow],
    controls: &[NegativeControlRow],
) -> ValidationChecks {
    let mut ids = HashSet::new();
    let duplicate_trade_ids = trades
        .iter()
        .filter(|trade| !ids.insert(trade.trade_id.clone()))
        .count();
    let missing_exit_reason = trades
        .iter()
        .filter(|trade| trade.exit_reason.trim().is_empty())
        .count();
    let daily_trade_pnl_abs_diff = (trades.iter().map(|trade| trade.pnl_quote).sum::<f64>()
        - daily.iter().map(|row| row.pnl_quote).sum::<f64>())
    .abs();
    let non_overlap_violations = {
        let mut groups: BTreeMap<(String, String, String, String, u32, u32, u32), Vec<&TradeRow>> =
            BTreeMap::new();
        for trade in trades {
            groups
                .entry((
                    trade.symbol.clone(),
                    trade.anchor_type.clone(),
                    trade.side.clone(),
                    trade.execution_model.clone(),
                    trade.tp_bps,
                    trade.sl_bps,
                    trade.timeout_minutes,
                ))
                .or_default()
                .push(trade);
        }
        groups
            .values_mut()
            .map(|rows| {
                rows.sort_by_key(|trade| trade.entry_timestamp_us);
                rows.windows(2)
                    .filter(|pair| pair[1].entry_timestamp_us < pair[0].exit_timestamp_us)
                    .count()
            })
            .sum()
    };
    let primary_exec_rows = trades
        .iter()
        .filter(|trade| {
            matches!(
                trade.execution_model.as_str(),
                "maker_light" | "taker_spread"
            )
        })
        .count();
    let long_rows = trades.iter().filter(|trade| trade.side == "long").count();
    let short_rows = trades.iter().filter(|trade| trade.side == "short").count();
    ValidationChecks {
        duplicate_trade_ids,
        missing_exit_reason,
        daily_trade_pnl_abs_diff,
        non_overlap_violations,
        primary_exec_rows,
        long_rows,
        short_rows,
        negative_control_rows: controls.len(),
        passed: duplicate_trade_ids == 0
            && missing_exit_reason == 0
            && daily_trade_pnl_abs_diff < 1e-6
            && non_overlap_violations == 0
            && primary_exec_rows > 0
            && long_rows > 0
            && short_rows > 0
            && !controls.is_empty(),
    }
}

fn build_completion(
    config: &V9Config,
    paths: &Paths,
    potential_rows: usize,
    filter_rows: usize,
    filter_param_rows: usize,
    outputs: &EpisodeOutputs,
    spearman_rows: usize,
    validation: &ValidationChecks,
) -> Completion {
    Completion {
        run_name: "bonk_v9_orderbook_potential_filtering".to_string(),
        generated_at_utc: iso_now(),
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        guardrail: GUARDRAIL.to_string(),
        config: CompletionConfig {
            notional_quote: config.notional_quote,
            fee_bps: config.fee_bps,
            cooldown_minutes: config.cooldown_minutes,
            min_hold_minutes: config.min_hold_minutes,
            debounce_on_minutes: config.debounce_on_minutes,
            debounce_off_minutes: config.debounce_off_minutes,
            tp_bps: config.tp_bps.clone(),
            sl_bps: config.sl_bps.clone(),
            timeout_minutes: config.timeout_minutes.clone(),
            execution_models: config.execution_models.clone(),
            sides: DEFAULT_SIDES.iter().map(|side| side.to_string()).collect(),
        },
        counts: CompletionCounts {
            potential_rows,
            filter_rows,
            filter_param_rows,
            anchor_fit_rows: outputs.anchor_candidates.len(),
            trades: outputs.trades.len(),
            daily_rows: outputs.daily.len(),
            summary_rows: outputs.summary.len(),
            spearman_rows,
            negative_control_rows: outputs.negative_controls.len(),
        },
        outputs: completion_outputs(config, paths),
        validation: validation.clone(),
    }
}

fn completion_outputs(config: &V9Config, paths: &Paths) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    out.insert("manifest".to_string(), path_string(&paths.manifest));
    out.insert("checkpoint".to_string(), path_string(&paths.checkpoint));
    out.insert("completion".to_string(), path_string(&paths.completion));
    out.insert(
        "potential_state".to_string(),
        path_string(&paths.potential_state),
    );
    out.insert("filter_state".to_string(), path_string(&paths.filter_state));
    out.insert(
        "filter_params".to_string(),
        path_string(&paths.filter_params),
    );
    out.insert(
        "anchor_candidates".to_string(),
        path_string(&paths.anchor_candidates),
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
    out.insert(
        "spearman_stability".to_string(),
        path_string(&paths.spearman_stability),
    );
    out.insert(
        "negative_controls".to_string(),
        path_string(&paths.negative_controls),
    );
    out.insert("research_doc".to_string(), path_string(&config.research_md));
    out.insert("report".to_string(), path_string(&config.report_md));
    out
}

fn summary_from_existing(config: &V9Config, paths: &Paths) -> V9Summary {
    let outputs = read_episode_outputs(paths).unwrap_or_else(|_| EpisodeOutputs {
        anchor_candidates: Vec::new(),
        trades: Vec::new(),
        daily: Vec::new(),
        summary: Vec::new(),
        exit_reasons: Vec::new(),
        fold_stability: Vec::new(),
        non_overlap: Vec::new(),
        parameter_sensitivity: Vec::new(),
        single_day_dependence: Vec::new(),
        failure_diagnostics: Vec::new(),
        negative_controls: Vec::new(),
    });
    let validation = validate_outputs(&outputs.trades, &outputs.daily, &outputs.negative_controls);
    V9Summary {
        run_tag: config.run_tag.clone(),
        out_tag: out_tag(config),
        potential_rows: csv_record_count(&paths.potential_state).unwrap_or(0),
        filter_rows: csv_record_count(&paths.filter_state).unwrap_or(0),
        anchor_fit_rows: csv_record_count(&paths.anchor_candidates).unwrap_or(0),
        trades: csv_record_count(&paths.trades).unwrap_or(0),
        daily_rows: csv_record_count(&paths.daily).unwrap_or(0),
        summary_rows: csv_record_count(&paths.summary).unwrap_or(0),
        spearman_rows: csv_record_count(&paths.spearman_stability).unwrap_or(0),
        negative_control_rows: csv_record_count(&paths.negative_controls).unwrap_or(0),
        validation_passed: validation.passed,
        manifest_json: path_string(&paths.manifest),
        checkpoint_json: path_string(&paths.checkpoint),
        potential_state_csv: path_string(&paths.potential_state),
        filter_state_csv: path_string(&paths.filter_state),
        filter_params_csv: path_string(&paths.filter_params),
        anchor_candidates_csv: path_string(&paths.anchor_candidates),
        trades_csv: path_string(&paths.trades),
        daily_csv: path_string(&paths.daily),
        summary_csv: path_string(&paths.summary),
        exit_reasons_csv: path_string(&paths.exit_reasons),
        fold_stability_csv: path_string(&paths.fold_stability),
        non_overlap_csv: path_string(&paths.non_overlap),
        parameter_sensitivity_csv: path_string(&paths.parameter_sensitivity),
        single_day_dependence_csv: path_string(&paths.single_day_dependence),
        failure_diagnostics_csv: path_string(&paths.failure_diagnostics),
        spearman_stability_csv: path_string(&paths.spearman_stability),
        negative_controls_csv: path_string(&paths.negative_controls),
        completion_json: path_string(&paths.completion),
        research_md: path_string(&config.research_md),
        report_md: path_string(&config.report_md),
    }
}

fn build_research_doc(_config: &V9Config) -> String {
    [
        "# BONK V9 Order-Book Potential And Filtering Research",
        "",
        "Status: research design notes for the V9 canonical runner. Research infrastructure only: no trading advice, no execution recommendation, and no alpha claim.",
        "",
        "## External Practice Review",
        "",
        "- GitHub order-book practice is less about isolated indicators and more about replay/fill realism. `hftbacktest` explicitly accounts for limit orders, queue position, and latency using L2/L3 tick data, which is a useful warning that maker rows without queue/latency stress are optimistic.",
        "- The GitHub `limit-order-book` topic contains reconstructors, heatmaps, feature-analysis projects, matching engines, RL environments, and DeepLOB-style prediction code. That suggests the V9 pipeline should separate book reconstruction/state estimation from execution simulation instead of blending them into one flat feature table.",
        "- Multi-Level Order-Flow Imbalance (MLOFI) treats imbalance as a vector over book levels rather than a single top-of-book scalar. V9 only has derived 5/25-depth summaries, so it uses a compressed potential-field proxy and marks this as an approximation until deeper raw book data is approved.",
        "- Latent liquidity work distinguishes the displayed book from hidden/intended liquidity and studies how latent volume reveals itself near the current price. V9 uses `kalman_pressure`/`yau_pressure` as observable-book latent-pressure proxies, not as a full latent order-book estimator.",
        "- Resiliency literature frames the book as a replenishment process after liquidity shocks. This maps directly to V9 `cancellation_withdrawal_energy`, `replenish_relaxation`, `event_time_decay`, and `post_event` anchors.",
        "- Queue-reactive Hawkes work combines current queue state with self-exciting order-flow memory. V9 does not fit a full Hawkes process yet; it approximates this with event-time decay plus train-fitted first-passage/energy anchors.",
        "- Kalman/EKF/UKF are appropriate baselines for latent pressure when observations are noisy. V9 includes train-fitted one-dimensional Kalman-family pressure filters over the potential observation.",
        "- Yau-Yau nonlinear filtering is a density-filtering framework built around offline propagation and online observation correction. V9 includes a lightweight Yau-Yau-inspired log-domain correction and restart heuristic, explicitly labeled experimental rather than a faithful DMZ PDE solver.",
        "",
        "## Source Pointers",
        "",
        "- hftbacktest: https://github.com/nkaz001/hftbacktest",
        "- GitHub limit-order-book topic: https://github.com/topics/limit-order-book",
        "- Multi-Level Order-Flow Imbalance: https://arxiv.org/abs/1907.06230",
        "- Latent liquidity revelation: https://arxiv.org/abs/1808.09677",
        "- Queue-reactive Hawkes models for order flow: https://arxiv.org/abs/1901.08938",
        "- Measuring the resiliency of an electronic limit order book: https://www.sciencedirect.com/science/article/pii/S1386418106000528",
        "- Improved Yau-Yau nonlinear filtering reference: https://arxiv.org/abs/2509.16896",
        "",
        "## V9 Definitions",
        "",
        "- `Phi_bid`: compressed demand-side potential from queue pressure, microprice/WOBI impulse, bid replenishment, flow pressure, cross-venue forcing, and regime pressure.",
        "- `Phi_ask`: compressed supply/resistance potential from opposite queue pressure, cancellation/withdrawal energy, spread-depth resistance, and opposing cross-venue/regime pressure.",
        "- `net_potential = Phi_bid - Phi_ask`: signed book pressure.",
        "- `potential_gradient` and `potential_curvature`: first and second differences in signed pressure.",
        "- `energy_release`: absolute potential movement plus cancellation, replenishment, notional burst, and spread expansion.",
        "- `liquidity_barrier`: spread/depth/fragility resistance proxy.",
        "- `queue_depth_pressure`: bid/ask 25-level pressure proxy.",
        "- `cancellation_withdrawal_energy`: ask/bid withdrawal and spread-expansion pressure.",
        "- `replenish_relaxation`: bid/ask replenishment and spread compression.",
        "- `cross_venue_forcing`: basis, microprice disagreement, lead-lag catch-up, and relative market/meme pressure.",
        "- `event_time_decay`: Hawkes-like memory proxy for recent energy release.",
        "- `kalman_pressure`: train-fitted latent pressure baseline.",
        "- `yau_pressure`: experimental online log-domain nonlinear correction with restart when the state leaves a train-fitted local region.",
        "",
        "## Movable Anchors",
        "",
        "- `pre_event`: pressure gradient builds before a barrier break.",
        "- `event`: energy release coincides with signed potential pressure.",
        "- `post_event`: replenishment/relaxation after a shock.",
        "- `first_passage`: hidden pressure crosses train-fitted state boundaries.",
        "- `potential_barrier_break`: signed potential clears liquidity resistance.",
        "",
        "## Canonical Discipline",
        "",
        "All thresholds, filter parameters, buckets, and anchor selectors are fit on train folds only and applied to validation folds after the purge gap. Python is reserved for visualization/search only; V9 executable labels and backtests are Rust canonical.",
    ]
    .join("\n")
}

fn build_report_doc(
    config: &V9Config,
    paths: &Paths,
    outputs: &EpisodeOutputs,
    spearman: &[SpearmanRow],
    validation: &ValidationChecks,
) -> String {
    let mut lines = Vec::new();
    lines.push("# BONK V9 Order-Book Potential Filtering".to_string());
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
    lines.push("- Used existing V8 factor-panel data only; no new raw data pull.".to_string());
    lines.push("- Rust is canonical for potential-state reconstruction, train-fitted filter parameters, movable anchors, long/short labels, after-cost backtests, negative controls, and reports.".to_string());
    lines.push("- The model treats the order book as a compressed dynamic pressure field rather than as a flat feature table.".to_string());
    lines.push(format!(
        "- Potential rows: `{}`. Filter rows: `{}`. Anchor fit rows: `{}`. Trades: `{}`. Summary rows: `{}`.",
        csv_record_count(&paths.potential_state).unwrap_or(0),
        csv_record_count(&paths.filter_state).unwrap_or(0),
        outputs.anchor_candidates.len(),
        outputs.trades.len(),
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
    lines.push("- Steps are `potential_state -> filter_state -> episode_backtest -> spearman_stability -> docs`.".to_string());
    lines.push(String::new());
    lines.push("## Primary After-Cost Rows".to_string());
    lines.push(String::new());
    lines.push("| rank | side | execution | anchor | symbol | tp/sl/to | total $ | avg $/day | win | pf | tr/day | max DD | fold/freq |".to_string());
    lines.push(
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
            .to_string(),
    );
    let stability = outputs
        .fold_stability
        .iter()
        .map(|row| {
            (
                row.symbol.clone(),
                row.anchor_type.clone(),
                row.side.clone(),
                row.execution_model.clone(),
                row.tp_bps,
                row.sl_bps,
                row.timeout_minutes,
                row.fold2_fold3_both_nonnegative,
            )
        })
        .collect::<HashSet<_>>();
    let mut primary = outputs
        .summary
        .iter()
        .filter(|row| row.summary_scope == "all")
        .filter(|row| matches!(row.execution_model.as_str(), "maker_light" | "taker_spread"))
        .filter(|row| row.target_frequency_pass)
        .filter(|row| row.total_pnl_quote > 0.0)
        .collect::<Vec<_>>();
    if primary.is_empty() {
        lines.push("| note | - | - | `no_positive_primary_target_frequency_rows` | - | - | 0.0000 | 0.0000 | - | - | - | - | V9 first pass found no positive primary rows after costs |".to_string());
        primary = outputs
            .summary
            .iter()
            .filter(|row| row.summary_scope == "all")
            .filter(|row| matches!(row.execution_model.as_str(), "maker_light" | "taker_spread"))
            .filter(|row| row.target_frequency_pass)
            .collect::<Vec<_>>();
    }
    if primary.is_empty() {
        primary = outputs
            .summary
            .iter()
            .filter(|row| row.summary_scope == "all")
            .filter(|row| matches!(row.execution_model.as_str(), "maker_light" | "taker_spread"))
            .collect::<Vec<_>>();
    }
    primary.sort_by(|a, b| b.total_pnl_quote.total_cmp(&a.total_pnl_quote));
    for (rank, row) in primary.iter().take(20).enumerate() {
        let stable = stability.contains(&(
            row.symbol.clone(),
            row.anchor_type.clone(),
            row.side.clone(),
            row.execution_model.clone(),
            row.tp_bps,
            row.sl_bps,
            row.timeout_minutes,
            true,
        ));
        lines.push(format!(
            "| {} | {} | {} | `{}` | {} | {}/{}/{} | {} | {} | {} | {} | {} | {} | {}{} |",
            rank + 1,
            row.side,
            row.execution_model,
            row.anchor_type,
            row.symbol,
            row.tp_bps,
            row.sl_bps,
            row.timeout_minutes,
            fmt_float(row.total_pnl_quote, 4),
            fmt_float(row.avg_daily_pnl_quote, 4),
            fmt_opt(row.win_rate, 2),
            fmt_opt(row.profit_factor, 2),
            fmt_float(row.trades_per_day, 2),
            fmt_float(row.max_drawdown_quote, 4),
            if stable { "fold2/3 ok" } else { "fold2/3 weak" },
            if row.target_frequency_pass {
                ", target freq"
            } else {
                ", freq miss"
            }
        ));
    }
    lines.push(String::new());
    lines.push("## Diagnostics".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- Validation passed: `{}`; duplicate trade ids `{}`, missing exits `{}`, daily/trade PnL diff `{}`, non-overlap violations `{}`.",
        validation.passed,
        validation.duplicate_trade_ids,
        validation.missing_exit_reason,
        fmt_float(validation.daily_trade_pnl_abs_diff, 8),
        validation.non_overlap_violations
    ));
    lines.push(format!(
        "- Long trades: `{}`. Short trades: `{}`. Negative-control rows: `{}`. Spearman rows: `{}`.",
        validation.long_rows,
        validation.short_rows,
        outputs.negative_controls.len(),
        spearman.len()
    ));
    if let Some(top_sp) = spearman.first() {
        lines.push(format!(
            "- Top validation Spearman: `{}` `{}` {}m {} = `{}` over `{}` rows.",
            top_sp.symbol,
            top_sp.feature_name,
            top_sp.horizon_minutes,
            top_sp.fold,
            fmt_float(top_sp.spearman, 4),
            top_sp.n
        ));
    }
    lines.push(String::new());
    lines.push("## Outputs".to_string());
    lines.push(String::new());
    for (label, path) in [
        ("potential state", &paths.potential_state),
        ("filter params", &paths.filter_params),
        ("filter state", &paths.filter_state),
        ("anchor candidates", &paths.anchor_candidates),
        ("trades", &paths.trades),
        ("daily", &paths.daily),
        ("summary", &paths.summary),
        ("exit reasons", &paths.exit_reasons),
        ("fold stability", &paths.fold_stability),
        ("non-overlap", &paths.non_overlap),
        ("parameter sensitivity", &paths.parameter_sensitivity),
        ("single-day dependence", &paths.single_day_dependence),
        ("failure diagnostics", &paths.failure_diagnostics),
        ("negative controls", &paths.negative_controls),
        ("spearman stability", &paths.spearman_stability),
        ("completion", &paths.completion),
    ] {
        lines.push(format!("- {label}: `{}`", path_string(path)));
    }
    lines.join("\n")
}

fn build_anchor_signal_thresholds(thresholds: &str, tp: u32, sl: u32, timeout: u32) -> String {
    format!("{thresholds}; tp={tp}; sl={sl}; to={timeout}")
}

fn trade_exit_index(rows: &[SignalRow], exit_ts: u64) -> Option<usize> {
    rows.iter().position(|row| row.timestamp_us == exit_ts)
}

fn debounce_gate(raw: &[bool], on_minutes: usize, off_minutes: usize) -> Vec<bool> {
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

fn queue_fill_probability(row: &FilterStateRow) -> f64 {
    let depth = row
        .depth_bid_25
        .zip(row.depth_ask_25)
        .map(|(bid, ask)| (bid + ask).max(0.0))
        .unwrap_or(0.0);
    let depth_score = squash(depth, 25_000.0).max(0.0);
    let resistance = row.liquidity_barrier.unwrap_or(0.0).abs();
    let replenish = row.replenish_relaxation.unwrap_or(0.0).max(0.0);
    (0.35 + 0.35 * depth_score + 0.20 * replenish - 0.10 * resistance).clamp(0.05, 0.95)
}

fn potential_by_symbol(rows: &[PotentialStateRow]) -> HashMap<String, Vec<&PotentialStateRow>> {
    let mut out: HashMap<String, Vec<&PotentialStateRow>> = HashMap::new();
    for row in rows {
        out.entry(row.symbol.clone()).or_default().push(row);
    }
    for rows in out.values_mut() {
        rows.sort_by_key(|row| row.timestamp_us);
    }
    out
}

fn filter_by_fold_symbol(
    rows: &[FilterStateRow],
) -> HashMap<(String, String), Vec<&FilterStateRow>> {
    let mut out: HashMap<(String, String), Vec<&FilterStateRow>> = HashMap::new();
    for row in rows {
        out.entry((row.fold.clone(), row.symbol.clone()))
            .or_default()
            .push(row);
    }
    for rows in out.values_mut() {
        rows.sort_by_key(|row| row.timestamp_us);
    }
    out
}

fn potential_feature(row: &PotentialStateRow, feature: &str) -> Option<f64> {
    match feature {
        "phi_bid" => row.phi_bid,
        "phi_ask" => row.phi_ask,
        "net_potential" => row.net_potential,
        "potential_gradient" => row.potential_gradient,
        "potential_curvature" => row.potential_curvature,
        "energy_release" => row.energy_release,
        "liquidity_barrier" => row.liquidity_barrier,
        "queue_depth_pressure" => row.queue_depth_pressure,
        "cancellation_withdrawal_energy" => row.cancellation_withdrawal_energy,
        "replenish_relaxation" => row.replenish_relaxation,
        "spread_depth_resistance" => row.spread_depth_resistance,
        "cross_venue_forcing" => row.cross_venue_forcing,
        "event_time_decay" => row.event_time_decay,
        "kalman_pressure_fixed" => row.kalman_pressure_fixed,
        "yau_pressure_fixed" => row.yau_pressure_fixed,
        "potential_barrier_distance" => row.potential_barrier_distance,
        _ => None,
    }
}

fn depth_pressure(bid: Option<f64>, ask: Option<f64>) -> Option<f64> {
    let (bid, ask) = (bid?, ask?);
    let denom = bid + ask;
    if denom <= 0.0 {
        return None;
    }
    finite((bid - ask) / denom)
}

fn squash(value: f64, scale: f64) -> f64 {
    (value / scale.max(1e-9)).tanh()
}

fn mean_opt(values: &[Option<f64>]) -> Option<f64> {
    let vals = values
        .iter()
        .filter_map(|value| value.and_then(finite))
        .collect::<Vec<_>>();
    mean(&vals)
}

fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn valid_price(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn bucket_label(value: f64, low: f64, high: f64) -> String {
    if value <= low {
        "low".to_string()
    } else if value >= high {
        "high".to_string()
    } else {
        "mid".to_string()
    }
}

fn pseudo_shuffle_sign(timestamp_us: u64, salt: u64) -> bool {
    let mut x = timestamp_us ^ salt.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    x ^= x >> 33;
    x = x.wrapping_mul(0xff51afd7ed558ccd);
    x ^= x >> 33;
    x & 1 == 0
}

fn mean(values: &[f64]) -> Option<f64> {
    let vals = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if vals.is_empty() {
        None
    } else {
        Some(vals.iter().sum::<f64>() / vals.len() as f64)
    }
}

fn variance(values: &[f64]) -> Option<f64> {
    let vals = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if vals.len() < 2 {
        return None;
    }
    let avg = vals.iter().sum::<f64>() / vals.len() as f64;
    Some(vals.iter().map(|value| (value - avg).powi(2)).sum::<f64>() / (vals.len() - 1) as f64)
}

fn stddev(values: &[f64]) -> Option<f64> {
    variance(values).and_then(|value| finite(value.sqrt()))
}

fn median(values: &[f64]) -> Option<f64> {
    quantile_opt(values, 0.5)
}

fn quantile_opt(values: &[f64], q: f64) -> Option<f64> {
    let mut vals = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    vals.sort_by(|a, b| a.total_cmp(b));
    if vals.is_empty() {
        return None;
    }
    let pos = q.clamp(0.0, 1.0) * (vals.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    if lo == hi {
        Some(vals[lo])
    } else {
        let weight = pos - lo as f64;
        Some(vals[lo] * (1.0 - weight) + vals[hi] * weight)
    }
}

fn win_rate_bps(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        Some(values.iter().filter(|value| **value > 0.0).count() as f64 / values.len() as f64)
    }
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

fn max_drawdown(values: &[f64]) -> f64 {
    let mut equity = 0.0;
    let mut peak = 0.0;
    let mut max_dd = 0.0;
    for value in values {
        equity += value;
        peak = f64::max(peak, equity);
        max_dd = f64::max(max_dd, peak - equity);
    }
    max_dd
}

fn lag_corr(values: &[f64]) -> Option<f64> {
    if values.len() < 3 {
        return None;
    }
    let xs = values[..values.len() - 1].to_vec();
    let ys = values[1..].to_vec();
    corr(&xs, &ys)
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
        None
    } else {
        finite(num / (den_x.sqrt() * den_y.sqrt()))
    }
}

fn spearman(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 3 {
        return None;
    }
    let rx = ranks(xs);
    let ry = ranks(ys);
    corr(&rx, &ry)
}

fn ranks(values: &[f64]) -> Vec<f64> {
    let mut indexed = values.iter().copied().enumerate().collect::<Vec<_>>();
    indexed.sort_by(|a, b| a.1.total_cmp(&b.1));
    let mut ranks = vec![0.0; values.len()];
    let mut idx = 0usize;
    while idx < indexed.len() {
        let start = idx;
        let value = indexed[idx].1;
        while idx < indexed.len() && indexed[idx].1 == value {
            idx += 1;
        }
        let rank = (start + idx - 1) as f64 / 2.0 + 1.0;
        for j in start..idx {
            ranks[indexed[j].0] = rank;
        }
    }
    ranks
}

fn fmt_float(value: f64, digits: usize) -> String {
    if value.is_finite() {
        format!("{value:.digits$}")
    } else {
        String::new()
    }
}

fn fmt_opt(value: Option<f64>, digits: usize) -> String {
    value
        .map(|value| fmt_float(value, digits))
        .unwrap_or_default()
}

fn utc_us(value: &str) -> Result<u64> {
    let dt = DateTime::parse_from_rfc3339(value)?.with_timezone(&Utc);
    Ok(dt.timestamp_micros() as u64)
}

fn iso_now() -> String {
    Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()
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

fn opt_col_value(batch: &RecordBatch, name: &str, idx: usize) -> Result<Option<f64>> {
    f64_array(batch, name).map(|array| opt_f64_value(array, idx))
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

fn csv_record_count(path: &Path) -> Result<usize> {
    if !path.exists() {
        return Ok(0);
    }
    let mut reader = csv::Reader::from_path(path)?;
    Ok(reader.records().count())
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

fn temp_path_for(path: &Path) -> PathBuf {
    let suffix = format!(".{}.tmp", std::process::id());
    let mut name = path
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "tmp".to_string());
    name.push_str(&suffix);
    path.with_file_name(name)
}

fn replace_file(temp: &Path, path: &Path) -> Result<()> {
    if path.exists() {
        fs::remove_file(path).with_context(|| format!("failed to remove {}", path.display()))?;
    }
    fs::rename(temp, path)
        .with_context(|| format!("failed to rename {} to {}", temp.display(), path.display()))
}

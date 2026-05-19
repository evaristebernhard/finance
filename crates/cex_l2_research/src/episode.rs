use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::path::{Path, PathBuf};
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, anyhow};
use arrow::array::{Array, Float64Array, StringArray, UInt64Array};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, Days, NaiveDate, Utc};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::{Deserialize, Serialize};

use crate::download::DEFAULT_BONK_DATA_ROOT;

pub const DEFAULT_EPISODE_RUN_TAG: &str = "20260513_bullish_l2_basket_price_v1";

const MINUTE_US: u64 = 60_000_000;
const PRIMARY_HORIZON_HOURS: u64 = 4;
const PRIMARY_BARRIER_BPS: u64 = 100;
const ACCOUNT_QUOTE: f64 = 100.0;
const GUARDRAIL: &str = "research_only_not_trading_rule_no_alpha_claim";

const DEFAULT_TP_BPS: &[u32] = &[30, 50, 75, 100, 150];
const DEFAULT_SL_BPS: &[u32] = &[20, 30, 50, 75, 100];
const DEFAULT_TIMEOUT_MINUTES: &[u32] = &[30, 60, 120, 240];
const DEFAULT_EXECUTION_MODELS: &[&str] =
    &["mid_research", "maker_light", "taker_spread", "wide_stress"];

#[derive(Debug, Clone)]
pub struct EpisodeConfig {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub run_tag: String,
    pub out_tag: String,
    pub panel_path: Option<PathBuf>,
    pub l2_state_path: Option<PathBuf>,
    pub report_md: PathBuf,
    pub gate_set: String,
    pub gates: Vec<String>,
    pub tp_bps: Vec<u32>,
    pub sl_bps: Vec<u32>,
    pub timeout_minutes: Vec<u32>,
    pub execution_models: Vec<String>,
    pub notional_quote: f64,
    pub fee_bps: f64,
    pub dry_run: bool,
    pub skip_trades_write: bool,
}

impl Default for EpisodeConfig {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_BONK_DATA_ROOT),
            date_dir: PathBuf::from("date"),
            run_tag: DEFAULT_EPISODE_RUN_TAG.to_string(),
            out_tag: DEFAULT_EPISODE_RUN_TAG.to_string(),
            panel_path: None,
            l2_state_path: None,
            report_md: PathBuf::from("docs/markets/bonk/v1-cex-v6-episode-backtest.md"),
            gate_set: "active_watch".to_string(),
            gates: Vec::new(),
            tp_bps: DEFAULT_TP_BPS.to_vec(),
            sl_bps: DEFAULT_SL_BPS.to_vec(),
            timeout_minutes: DEFAULT_TIMEOUT_MINUTES.to_vec(),
            execution_models: DEFAULT_EXECUTION_MODELS
                .iter()
                .map(|value| value.to_string())
                .collect(),
            notional_quote: ACCOUNT_QUOTE,
            fee_bps: 2.0,
            dry_run: false,
            skip_trades_write: false,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct EpisodeSummary {
    pub out_tag: String,
    pub trades: usize,
    pub daily_rows: usize,
    pub summary_rows: usize,
    pub validation_checks: ValidationChecks,
    pub trades_csv: String,
    pub daily_csv: String,
    pub summary_csv: String,
    pub completion_json: String,
    pub report_md: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationChecks {
    pub duplicate_trade_ids: usize,
    pub missing_exit_reason: usize,
    pub entry_not_after_signal: usize,
    pub daily_trade_pnl_abs_diff: f64,
    pub cost_monotonic_violations: usize,
    pub passed: bool,
}

#[derive(Debug, Clone, Serialize)]
struct Completion {
    eval_name: String,
    generated_at_utc: String,
    run_tag: String,
    out_tag: String,
    guardrail: String,
    inputs: CompletionInputs,
    outputs: CompletionOutputs,
    report: String,
    gates: Vec<GateSpec>,
    folds: Vec<FoldDef>,
    params: CompletionParams,
    counts: CompletionCounts,
    validation_checks: ValidationChecks,
}

#[derive(Debug, Clone, Serialize)]
struct CompletionInputs {
    panel: String,
    l2_state: String,
}

#[derive(Debug, Clone, Serialize)]
struct CompletionOutputs {
    trades: String,
    daily: String,
    summary: String,
    completion: String,
}

#[derive(Debug, Clone, Serialize)]
struct CompletionParams {
    tp_bps: Vec<u32>,
    sl_bps: Vec<u32>,
    timeout_minutes: Vec<u32>,
    execution_models: Vec<String>,
    notional_quote: f64,
    fee_bps: f64,
}

#[derive(Debug, Clone, Serialize)]
struct CompletionCounts {
    config_rows: usize,
    trades: usize,
    daily_rows: usize,
    summary_rows: usize,
    episode_starts: usize,
    entry_skips: usize,
}

#[derive(Debug, Clone)]
struct OutputPaths {
    trades: PathBuf,
    daily: PathBuf,
    summary: PathBuf,
    completion: PathBuf,
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

#[derive(Debug, Clone, Serialize)]
struct GateSpec {
    gate_id: &'static str,
    gate_group: &'static str,
    symbol: &'static str,
    gate_name: &'static str,
    component_names: Vec<&'static str>,
}

#[derive(Debug, Clone)]
struct ComponentSpec {
    resolved_name: &'static str,
    factor: &'static str,
    bucket: Bucket,
}

#[derive(Debug, Clone, Copy)]
enum Bucket {
    Low,
    High,
}

#[derive(Debug, Clone)]
struct GateDef {
    factor: &'static str,
    bucket: Bucket,
}

#[derive(Debug, Clone)]
struct PanelRow {
    timestamp_us: u64,
    symbol: String,
    top_depth_total_notional_median: Option<f64>,
    ctx_bonk_rv_1h_bps: Option<f64>,
    cross_venue_spread_diff_bps: Option<f64>,
    snapshot_microprice_offset_bps_mean: Option<f64>,
}

#[derive(Debug, Clone)]
struct L2Row {
    timestamp_us: u64,
    timestamp_utc: String,
    symbol: String,
    mid_price_per_unit_open: Option<f64>,
    mid_price_per_unit_high: Option<f64>,
    mid_price_per_unit_low: Option<f64>,
    mid_price_per_unit_close: Option<f64>,
    spread_bps_median: Option<f64>,
    depth_bid_notional_25_median: Option<f64>,
    depth_ask_notional_25_median: Option<f64>,
}

#[derive(Debug, Clone)]
struct SignalRow {
    timestamp_us: u64,
    timestamp_utc: String,
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
    run_tag: String,
    out_tag: String,
    fold: String,
    gate_group: String,
    gate_id: String,
    gate_name: String,
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

#[derive(Debug, Clone, Serialize)]
struct TradeRow {
    trade_id: String,
    run_tag: String,
    out_tag: String,
    fold: String,
    gate_group: String,
    gate_id: String,
    gate_name: String,
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

#[derive(Debug, Clone, Serialize)]
struct DailyRow {
    fold: String,
    date: String,
    gate_group: String,
    gate_id: String,
    gate_name: String,
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

#[derive(Debug, Clone, Serialize)]
struct SummaryRow {
    summary_scope: String,
    fold: String,
    gate_group: String,
    gate_id: String,
    gate_name: String,
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
    ambiguous_trade_count: usize,
    ambiguous_trade_rate: f64,
    exit_reason_counts_json: String,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct ConfigRow {
    key: ConfigKey,
    validation_dates: Vec<String>,
    notional_quote: f64,
    episode_starts: usize,
    entry_skips: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct ConfigKey {
    fold: String,
    gate_group: String,
    gate_id: String,
    gate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct AllKey {
    gate_group: String,
    gate_id: String,
    gate_name: String,
    symbol: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
}

pub fn run_episode_backtest(config: &EpisodeConfig) -> Result<EpisodeSummary> {
    validate_config(config)?;
    let out_tag = if config.out_tag.is_empty() {
        config.run_tag.clone()
    } else {
        config.out_tag.clone()
    };
    let paths = output_paths(&config.date_dir, &out_tag);
    let panel_path = panel_path(config);
    let l2_state_path = l2_state_path(config);
    let gates = select_gates(config)?;
    let symbols: HashSet<String> = gates.iter().map(|gate| gate.symbol.to_string()).collect();

    eprintln!(
        "[bonk_v6_episode_backtest] read panel {}",
        panel_path.display()
    );
    let panel = read_panel_rows(&panel_path, &config.run_tag, &symbols)?;
    eprintln!(
        "[bonk_v6_episode_backtest] read L2 {}",
        l2_state_path.display()
    );
    let l2_state = read_l2_rows(&l2_state_path, &config.run_tag, &symbols)?;
    eprintln!(
        "[bonk_v6_episode_backtest] simulate {} gates x {} TP x {} SL x {} timeout x {} exec",
        gates.len(),
        config.tp_bps.len(),
        config.sl_bps.len(),
        config.timeout_minutes.len(),
        config.execution_models.len()
    );
    let (trades, configs) = run_backtests(&panel, &l2_state, &gates, config, &out_tag)?;
    let daily = aggregate_daily(&trades, &configs);
    let summary_rows = aggregate_summary(&trades, &daily);
    let validation_checks = validate_outputs(&trades, &daily, &summary_rows);
    let completion = build_completion(
        config,
        &out_tag,
        &paths,
        &panel_path,
        &l2_state_path,
        &gates,
        &trades,
        &daily,
        &summary_rows,
        &configs,
        &validation_checks,
    );
    let report = build_report(
        config,
        &out_tag,
        &gates,
        &trades,
        &daily,
        &summary_rows,
        &completion,
    );

    if !config.dry_run {
        if !config.skip_trades_write {
            write_csv_direct(&paths.trades, &trades)?;
        }
        write_csv_atomic(&paths.daily, &daily)?;
        write_csv_atomic(&paths.summary, &summary_rows)?;
        write_json_atomic(&paths.completion, &completion)?;
        write_text_atomic(&config.report_md, &report)?;
    }

    Ok(EpisodeSummary {
        out_tag,
        trades: trades.len(),
        daily_rows: daily.len(),
        summary_rows: summary_rows.len(),
        validation_checks,
        trades_csv: path_string(&paths.trades),
        daily_csv: path_string(&paths.daily),
        summary_csv: path_string(&paths.summary),
        completion_json: path_string(&paths.completion),
        report_md: path_string(&config.report_md),
    })
}

fn validate_config(config: &EpisodeConfig) -> Result<()> {
    if config.notional_quote <= 0.0 {
        return Err(anyhow!("--notional-quote must be positive"));
    }
    if config.fee_bps < 0.0 {
        return Err(anyhow!("--fee-bps must be non-negative"));
    }
    let allowed_exec: HashSet<&str> = DEFAULT_EXECUTION_MODELS.iter().copied().collect();
    for model in &config.execution_models {
        if !allowed_exec.contains(model.as_str()) {
            return Err(anyhow!("unknown execution model: {model}"));
        }
    }
    if config.tp_bps.is_empty()
        || config.sl_bps.is_empty()
        || config.timeout_minutes.is_empty()
        || config.execution_models.is_empty()
    {
        return Err(anyhow!("tp/sl/timeout/execution grids must be non-empty"));
    }
    Ok(())
}

fn output_paths(date_dir: &Path, out_tag: &str) -> OutputPaths {
    let prefix = format!("bonk_v6_episode_backtest_{out_tag}");
    OutputPaths {
        trades: date_dir.join(format!("{prefix}_trades.csv")),
        daily: date_dir.join(format!("{prefix}_daily.csv")),
        summary: date_dir.join(format!("{prefix}_summary.csv")),
        completion: date_dir.join(format!("{prefix}_completion.json")),
    }
}

fn panel_path(config: &EpisodeConfig) -> PathBuf {
    config.panel_path.clone().unwrap_or_else(|| {
        config
            .data_root
            .join("derived/bonk_l2_label_context_panel")
            .join(format!(
                "bonk_l2_label_context_panel_{}.parquet",
                config.run_tag
            ))
    })
}

fn l2_state_path(config: &EpisodeConfig) -> PathBuf {
    config.l2_state_path.clone().unwrap_or_else(|| {
        config
            .data_root
            .join("derived/bonk_cex_l2_state")
            .join(format!("bonk_cex_l2_state_{}.parquet", config.run_tag))
    })
}

fn select_gates(config: &EpisodeConfig) -> Result<Vec<GateSpec>> {
    let all = all_gates();
    if !config.gates.is_empty() {
        let by_id: HashMap<&str, GateSpec> = all
            .iter()
            .map(|gate| (gate.gate_id, gate.clone()))
            .collect();
        let mut out = Vec::new();
        for gate_id in &config.gates {
            let gate = by_id
                .get(gate_id.as_str())
                .ok_or_else(|| anyhow!("unknown gate id: {gate_id}"))?;
            out.push(gate.clone());
        }
        return Ok(out);
    }
    match config.gate_set.as_str() {
        "active" => Ok(all
            .into_iter()
            .filter(|gate| gate.gate_group == "active")
            .collect()),
        "active_watch" => Ok(all),
        other => Err(anyhow!("unknown gate set: {other}")),
    }
}

fn all_gates() -> Vec<GateSpec> {
    vec![
        GateSpec {
            gate_id: "h4_usdt_depth_rv",
            gate_group: "active",
            symbol: "BONK1MUSDT",
            gate_name: "depth_high+rv_low",
            component_names: vec!["depth_high", "rv_low"],
        },
        GateSpec {
            gate_id: "h4_usdt_depth_rv_cv",
            gate_group: "active",
            symbol: "BONK1MUSDT",
            gate_name: "depth_high+rv_low+cv_spread",
            component_names: vec!["depth_high", "rv_low", "cv_spread_selected"],
        },
        GateSpec {
            gate_id: "h4_usdt_depth_rv_micro",
            gate_group: "watch",
            symbol: "BONK1MUSDT",
            gate_name: "depth_high+rv_low+snapshot_microprice",
            component_names: vec!["depth_high", "rv_low", "snapshot_microprice_low"],
        },
        GateSpec {
            gate_id: "h4_usdt_depth_rv_cv_micro",
            gate_group: "watch",
            symbol: "BONK1MUSDT",
            gate_name: "depth_high+rv_low+cv_spread+snapshot_microprice",
            component_names: vec![
                "depth_high",
                "rv_low",
                "cv_spread_selected",
                "snapshot_microprice_low",
            ],
        },
        GateSpec {
            gate_id: "h4_usdc_depth_rv_mirror",
            gate_group: "mirror",
            symbol: "BONK1MUSDC",
            gate_name: "depth_high+rv_low",
            component_names: vec!["depth_high", "rv_low"],
        },
        GateSpec {
            gate_id: "h4_usdc_depth_rv_cv_mirror",
            gate_group: "mirror",
            symbol: "BONK1MUSDC",
            gate_name: "depth_high+rv_low+cv_spread",
            component_names: vec!["depth_high", "rv_low", "cv_spread_selected"],
        },
    ]
}

fn gate_def(name: &str, symbol: &str) -> Result<GateDef> {
    let resolved = selected_gate_key(name, symbol);
    match resolved {
        "depth_high" => Ok(GateDef {
            factor: "top_depth_total_notional_median",
            bucket: Bucket::High,
        }),
        "rv_low" => Ok(GateDef {
            factor: "ctx_bonk_rv_1h_bps",
            bucket: Bucket::Low,
        }),
        "cv_spread_high" => Ok(GateDef {
            factor: "cross_venue_spread_diff_bps",
            bucket: Bucket::High,
        }),
        "cv_spread_low" => Ok(GateDef {
            factor: "cross_venue_spread_diff_bps",
            bucket: Bucket::Low,
        }),
        "snapshot_microprice_low" => Ok(GateDef {
            factor: "snapshot_microprice_offset_bps_mean",
            bucket: Bucket::Low,
        }),
        _ => Err(anyhow!("unknown component gate: {name}")),
    }
}

fn gate_components(gate: &GateSpec) -> Result<Vec<ComponentSpec>> {
    let mut out = Vec::new();
    for raw_name in &gate.component_names {
        let resolved_name = selected_gate_key(raw_name, gate.symbol);
        let def = gate_def(raw_name, gate.symbol)?;
        out.push(ComponentSpec {
            resolved_name,
            factor: def.factor,
            bucket: def.bucket,
        });
    }
    Ok(out)
}

fn selected_gate_key<'a>(name: &'a str, symbol: &str) -> &'a str {
    if name == "cv_spread_selected" {
        if symbol == "BONK1MUSDC" {
            "cv_spread_low"
        } else {
            "cv_spread_high"
        }
    } else {
        name
    }
}

fn run_backtests(
    panel: &[PanelRow],
    l2_state: &[L2Row],
    gates: &[GateSpec],
    config: &EpisodeConfig,
    out_tag: &str,
) -> Result<(Vec<TradeRow>, Vec<ConfigRow>)> {
    let mut trades = Vec::new();
    let mut configs = Vec::new();
    let mut base_trade_number = 0usize;
    for gate in gates {
        for fold in FOLDS {
            let (rows, thresholds, selected_minutes) =
                build_signal_frame(panel, l2_state, gate, fold)?;
            let validation_dates = fold.validation_dates()?;
            let base = ConfigKey {
                fold: fold.name.to_string(),
                gate_group: gate.gate_group.to_string(),
                gate_id: gate.gate_id.to_string(),
                gate_name: gate.gate_name.to_string(),
                symbol: gate.symbol.to_string(),
                execution_model: String::new(),
                tp_bps: 0,
                sl_bps: 0,
                timeout_minutes: 0,
            };

            if rows.is_empty() {
                for execution_model in &config.execution_models {
                    for &tp_bps in &config.tp_bps {
                        for &sl_bps in &config.sl_bps {
                            for &timeout_minutes in &config.timeout_minutes {
                                let mut key = base.clone();
                                key.execution_model = execution_model.clone();
                                key.tp_bps = tp_bps;
                                key.sl_bps = sl_bps;
                                key.timeout_minutes = timeout_minutes;
                                configs.push(ConfigRow {
                                    key,
                                    validation_dates: validation_dates.clone(),
                                    notional_quote: config.notional_quote,
                                    episode_starts: 0,
                                    entry_skips: 0,
                                });
                            }
                        }
                    }
                }
                continue;
            }

            let starts = episode_starts(&rows);
            eprintln!(
                "[bonk_v6_episode_backtest] {} {} selected_minutes={} starts={}",
                gate.gate_id,
                fold.name,
                selected_minutes,
                starts.len()
            );
            for &tp_bps in &config.tp_bps {
                for &sl_bps in &config.sl_bps {
                    for &timeout_minutes in &config.timeout_minutes {
                        let mut entry_skips = 0usize;
                        let mut base_trades = Vec::new();
                        for &signal_idx in &starts {
                            let entry_idx = signal_idx + 1;
                            if entry_idx >= rows.len() {
                                entry_skips += 1;
                                continue;
                            }
                            let signal_ts = rows[signal_idx].timestamp_us;
                            let entry_ts = rows[entry_idx].timestamp_us;
                            if entry_ts.saturating_sub(signal_ts) > MINUTE_US {
                                entry_skips += 1;
                                continue;
                            }
                            base_trade_number += 1;
                            if let Some(base_trade) = simulate_base_episode(
                                &rows,
                                gate,
                                fold,
                                entry_idx,
                                signal_idx,
                                tp_bps,
                                sl_bps,
                                timeout_minutes,
                                base_trade_number,
                                out_tag,
                                &thresholds,
                                &config.run_tag,
                            ) {
                                base_trades.push(base_trade);
                            } else {
                                entry_skips += 1;
                            }
                        }
                        for execution_model in &config.execution_models {
                            for base_trade in &base_trades {
                                trades.push(expand_execution_trade(
                                    base_trade,
                                    execution_model,
                                    config.notional_quote,
                                    config.fee_bps,
                                ));
                            }
                            let mut key = base.clone();
                            key.execution_model = execution_model.clone();
                            key.tp_bps = tp_bps;
                            key.sl_bps = sl_bps;
                            key.timeout_minutes = timeout_minutes;
                            configs.push(ConfigRow {
                                key,
                                validation_dates: validation_dates.clone(),
                                notional_quote: config.notional_quote,
                                episode_starts: starts.len(),
                                entry_skips,
                            });
                        }
                    }
                }
            }
        }
    }
    Ok((trades, configs))
}

fn build_signal_frame(
    panel: &[PanelRow],
    l2_state: &[L2Row],
    gate: &GateSpec,
    fold: &FoldDef,
) -> Result<(Vec<SignalRow>, String, usize)> {
    let train_end = fold.train_end_us()?;
    let valid_start = fold.valid_start_us()?;
    let valid_end = fold.valid_end_us()?;
    let train: Vec<&PanelRow> = panel
        .iter()
        .filter(|row| row.symbol == gate.symbol && row.timestamp_us <= train_end)
        .collect();
    let valid: Vec<&PanelRow> = panel
        .iter()
        .filter(|row| {
            row.symbol == gate.symbol
                && row.timestamp_us >= valid_start
                && row.timestamp_us <= valid_end
        })
        .collect();
    if train.is_empty() || valid.is_empty() {
        return Ok((Vec::new(), "empty_train_or_valid".to_string(), 0));
    }

    let mut selected_by_ts: HashMap<u64, bool> = HashMap::with_capacity(valid.len());
    let mut threshold_bits = Vec::new();
    let components = gate_components(gate)?;
    let mut thresholds = Vec::new();
    for component in &components {
        let values = train
            .iter()
            .filter_map(|row| panel_factor(row, component.factor))
            .collect::<Vec<_>>();
        let threshold = fit_threshold(values);
        threshold_bits.push(threshold_bit(component, threshold));
        thresholds.push((component.clone(), threshold));
    }
    let mut selected_minutes = 0usize;
    for row in valid {
        let mut selected = true;
        for (component, threshold) in &thresholds {
            match (panel_factor(row, component.factor), threshold) {
                (Some(value), Some((low, high))) => {
                    selected &= match component.bucket {
                        Bucket::Low => value <= *low,
                        Bucket::High => value >= *high,
                    };
                }
                _ => selected = false,
            }
        }
        if selected {
            selected_minutes += 1;
        }
        selected_by_ts.insert(row.timestamp_us, selected);
    }

    let mut rows: Vec<SignalRow> = l2_state
        .iter()
        .filter(|row| {
            row.symbol == gate.symbol
                && row.timestamp_us >= valid_start
                && row.timestamp_us <= valid_end
        })
        .map(|row| SignalRow {
            timestamp_us: row.timestamp_us,
            timestamp_utc: row.timestamp_utc.clone(),
            open: row.mid_price_per_unit_open,
            high: row.mid_price_per_unit_high,
            low: row.mid_price_per_unit_low,
            close: row.mid_price_per_unit_close,
            spread_bps: row.spread_bps_median,
            depth_bid_25: row.depth_bid_notional_25_median,
            depth_ask_25: row.depth_ask_notional_25_median,
            gate_selected: *selected_by_ts.get(&row.timestamp_us).unwrap_or(&false),
        })
        .collect();
    rows.sort_by_key(|row| row.timestamp_us);
    Ok((rows, threshold_bits.join("; "), selected_minutes))
}

fn panel_factor(row: &PanelRow, factor: &str) -> Option<f64> {
    match factor {
        "top_depth_total_notional_median" => row.top_depth_total_notional_median,
        "ctx_bonk_rv_1h_bps" => row.ctx_bonk_rv_1h_bps,
        "cross_venue_spread_diff_bps" => row.cross_venue_spread_diff_bps,
        "snapshot_microprice_offset_bps_mean" => row.snapshot_microprice_offset_bps_mean,
        _ => None,
    }
    .and_then(finite_option)
}

fn fit_threshold(mut values: Vec<f64>) -> Option<(f64, f64)> {
    values.retain(|value| value.is_finite());
    values.sort_by(|a, b| a.total_cmp(b));
    values.dedup_by(|a, b| a.total_cmp(b).is_eq());
    if values.len() < 3 {
        return None;
    }
    Some((quantile(&values, 1.0 / 3.0), quantile(&values, 2.0 / 3.0)))
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

fn threshold_bit(component: &ComponentSpec, threshold: Option<(f64, f64)>) -> String {
    let bucket = match component.bucket {
        Bucket::Low => "low",
        Bucket::High => "high",
    };
    match threshold {
        Some((low, high)) => format!(
            "{}:{}[{},{}]",
            component.resolved_name,
            bucket,
            fmt_float(low, 6),
            fmt_float(high, 6)
        ),
        None => format!("{}:{}[missing]", component.resolved_name, bucket),
    }
}

fn episode_starts(rows: &[SignalRow]) -> Vec<usize> {
    let mut out = Vec::new();
    let mut prev = false;
    for (idx, row) in rows.iter().enumerate() {
        if row.gate_selected && !prev {
            out.push(idx);
        }
        prev = row.gate_selected;
    }
    out
}

#[allow(clippy::too_many_arguments)]
fn simulate_base_episode(
    rows: &[SignalRow],
    gate: &GateSpec,
    fold: &FoldDef,
    entry_idx: usize,
    signal_idx: usize,
    tp_bps: u32,
    sl_bps: u32,
    timeout_minutes: u32,
    base_trade_number: usize,
    out_tag: &str,
    thresholds: &str,
    run_tag: &str,
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
        if !row.gate_selected {
            exit_price = close_price
                .filter(|value| valid_price(*value))
                .or(open_price.filter(|value| valid_price(*value)))
                .unwrap_or(entry_price);
            exit_reason = "gate_off";
            break;
        }
        if row.timestamp_us.saturating_sub(entry.timestamp_us) >= timeout_minutes as u64 * MINUTE_US
        {
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
        run_tag: run_tag.to_string(),
        out_tag: out_tag.to_string(),
        fold: fold.name.to_string(),
        gate_group: gate.gate_group.to_string(),
        gate_id: gate.gate_id.to_string(),
        gate_name: gate.gate_name.to_string(),
        gate_expression: gate.component_names.join(" AND "),
        symbol: gate.symbol.to_string(),
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

fn expand_execution_trade(
    base: &BaseTrade,
    execution_model: &str,
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
            base.out_tag,
            base.fold,
            base.gate_id,
            execution_model,
            base.tp_bps,
            base.sl_bps,
            base.timeout_minutes,
            base.base_trade_number
        ),
        run_tag: base.run_tag.clone(),
        out_tag: base.out_tag.clone(),
        fold: base.fold.clone(),
        gate_group: base.gate_group.clone(),
        gate_id: base.gate_id.clone(),
        gate_name: base.gate_name.clone(),
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
            let spread = spread_bps.and_then(finite_option).unwrap_or(0.0).max(0.0);
            let depth = match (
                depth_bid_25.and_then(finite_option),
                depth_ask_25.and_then(finite_option),
            ) {
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
            gate_group: trade.gate_group.clone(),
            gate_id: trade.gate_id.clone(),
            gate_name: trade.gate_name.clone(),
            symbol: trade.symbol.clone(),
            execution_model: trade.execution_model.clone(),
            tp_bps: trade.tp_bps,
            sl_bps: trade.sl_bps,
            timeout_minutes: trade.timeout_minutes,
        };
        let date = date_part(&trade.exit_timestamp_utc);
        by_key_date.entry((key, date)).or_default().push(trade);
    }

    let mut out = Vec::new();
    for config in configs {
        for date in &config.validation_dates {
            let mut day = by_key_date
                .get(&(config.key.clone(), date.clone()))
                .cloned()
                .unwrap_or_default();
            day.sort_by_key(|trade| trade.exit_timestamp_us);
            let pnl_values: Vec<f64> = day.iter().map(|trade| trade.pnl_quote).collect();
            let net_values: Vec<f64> = day.iter().map(|trade| trade.net_bps).collect();
            let duration_sum: f64 = day.iter().map(|trade| trade.duration_minutes).sum();
            let total_pnl: f64 = pnl_values.iter().sum();
            out.push(DailyRow {
                fold: config.key.fold.clone(),
                date: date.clone(),
                gate_group: config.key.gate_group.clone(),
                gate_id: config.key.gate_id.clone(),
                gate_name: config.key.gate_name.clone(),
                symbol: config.key.symbol.clone(),
                execution_model: config.key.execution_model.clone(),
                tp_bps: config.key.tp_bps,
                sl_bps: config.key.sl_bps,
                timeout_minutes: config.key.timeout_minutes,
                notional_quote: config.notional_quote,
                trade_count: day.len(),
                total_pnl_quote: total_pnl,
                return_bps_on_100: if config.notional_quote > 0.0 {
                    total_pnl / config.notional_quote * 10_000.0
                } else {
                    0.0
                },
                win_rate: rate_count(
                    net_values.iter().filter(|value| **value > 0.0).count(),
                    day.len(),
                ),
                max_intraday_drawdown_quote: max_drawdown(&pnl_values),
                exposure_minutes: duration_sum,
                turnover_quote: config.notional_quote * day.len() as f64,
                best_trade_pnl_quote: pnl_values.iter().copied().reduce(f64::max).unwrap_or(0.0),
                worst_trade_pnl_quote: pnl_values.iter().copied().reduce(f64::min).unwrap_or(0.0),
                guardrail: GUARDRAIL.to_string(),
            });
        }
    }
    out
}

fn aggregate_summary(trades: &[TradeRow], daily: &[DailyRow]) -> Vec<SummaryRow> {
    let mut trade_by_fold: HashMap<ConfigKey, Vec<&TradeRow>> = HashMap::new();
    let mut daily_by_fold: HashMap<ConfigKey, Vec<&DailyRow>> = HashMap::new();
    let mut trade_by_all: HashMap<AllKey, Vec<&TradeRow>> = HashMap::new();
    let mut daily_by_all: HashMap<AllKey, Vec<&DailyRow>> = HashMap::new();

    for trade in trades {
        let key = trade_config_key(trade);
        let all_key = all_key_from_config(&key);
        trade_by_fold.entry(key).or_default().push(trade);
        trade_by_all.entry(all_key).or_default().push(trade);
    }
    for row in daily {
        let key = daily_config_key(row);
        let all_key = all_key_from_config(&key);
        daily_by_fold.entry(key).or_default().push(row);
        daily_by_all.entry(all_key).or_default().push(row);
    }

    let mut out = Vec::new();
    for (key, days) in daily_by_fold {
        let trades_for_key = trade_by_fold.get(&key).cloned().unwrap_or_default();
        out.push(summarize_group("fold", &key, &days, &trades_for_key));
    }
    for (key, days) in daily_by_all {
        let trades_for_key = trade_by_all.get(&key).cloned().unwrap_or_default();
        let fold_key = ConfigKey {
            fold: "all".to_string(),
            gate_group: key.gate_group,
            gate_id: key.gate_id,
            gate_name: key.gate_name,
            symbol: key.symbol,
            execution_model: key.execution_model,
            tp_bps: key.tp_bps,
            sl_bps: key.sl_bps,
            timeout_minutes: key.timeout_minutes,
        };
        out.push(summarize_group(
            "all_folds",
            &fold_key,
            &days,
            &trades_for_key,
        ));
    }
    out.sort_by(|a, b| {
        a.summary_scope
            .cmp(&b.summary_scope)
            .then(a.execution_model.cmp(&b.execution_model))
            .then(a.gate_group.cmp(&b.gate_group))
            .then(a.gate_id.cmp(&b.gate_id))
            .then_with(|| b.total_pnl_quote.total_cmp(&a.total_pnl_quote))
    });
    out
}

fn summarize_group(
    scope: &str,
    key: &ConfigKey,
    daily: &[&DailyRow],
    trades: &[&TradeRow],
) -> SummaryRow {
    let mut daily_pnl: Vec<f64> = daily.iter().map(|row| row.total_pnl_quote).collect();
    daily_pnl.sort_by(|a, b| a.total_cmp(b));
    let mut trade_net: Vec<f64> = trades.iter().map(|row| row.net_bps).collect();
    trade_net.sort_by(|a, b| a.total_cmp(b));
    let mut durations: Vec<f64> = trades.iter().map(|row| row.duration_minutes).collect();
    durations.sort_by(|a, b| a.total_cmp(b));
    let trade_pnl: Vec<f64> = trades.iter().map(|row| row.pnl_quote).collect();
    let total_pnl: f64 = daily_pnl.iter().sum();
    let notional = daily
        .first()
        .map(|row| row.notional_quote)
        .or_else(|| trades.first().map(|row| row.notional_quote))
        .unwrap_or(ACCOUNT_QUOTE);
    let positive_days = daily_pnl.iter().filter(|value| **value > 0.0).count();
    let wins = trade_net.iter().filter(|value| **value > 0.0).count();
    let mut exit_counts: HashMap<String, usize> = HashMap::new();
    for trade in trades {
        *exit_counts.entry(trade.exit_reason.clone()).or_default() += 1;
    }
    let ambiguous = trades
        .iter()
        .filter(|trade| trade.same_bar_ambiguous)
        .count();
    SummaryRow {
        summary_scope: scope.to_string(),
        fold: key.fold.clone(),
        gate_group: key.gate_group.clone(),
        gate_id: key.gate_id.clone(),
        gate_name: key.gate_name.clone(),
        symbol: key.symbol.clone(),
        execution_model: key.execution_model.clone(),
        tp_bps: key.tp_bps,
        sl_bps: key.sl_bps,
        timeout_minutes: key.timeout_minutes,
        notional_quote: notional,
        days: daily.len(),
        trade_count: trades.len(),
        total_pnl_quote: total_pnl,
        total_return_bps_on_100: if notional > 0.0 {
            total_pnl / notional * 10_000.0
        } else {
            0.0
        },
        avg_daily_pnl_quote: mean(&daily_pnl).unwrap_or(0.0),
        median_daily_pnl_quote: percentile_sorted(&daily_pnl, 0.5).unwrap_or(0.0),
        avg_daily_return_bps_on_100: if notional > 0.0 {
            mean(&daily_pnl).unwrap_or(0.0) / notional * 10_000.0
        } else {
            0.0
        },
        positive_day_rate: rate_count(positive_days, daily.len()),
        max_drawdown_quote: max_drawdown(&daily_pnl),
        trades_per_day: if daily.is_empty() {
            0.0
        } else {
            trades.len() as f64 / daily.len() as f64
        },
        win_rate: rate_count(wins, trades.len()),
        profit_factor: profit_factor(&trade_pnl),
        median_trade_net_bps: percentile_sorted(&trade_net, 0.5),
        p25_trade_net_bps: percentile_sorted(&trade_net, 0.25),
        p75_trade_net_bps: percentile_sorted(&trade_net, 0.75),
        avg_gross_bps: mean_iter(trades.iter().map(|row| row.gross_bps)),
        avg_cost_bps: mean_iter(trades.iter().map(|row| row.cost_bps)),
        avg_net_bps: mean_iter(trades.iter().map(|row| row.net_bps)),
        median_duration_minutes: percentile_sorted(&durations, 0.5),
        ambiguous_trade_count: ambiguous,
        ambiguous_trade_rate: rate_count(ambiguous, trades.len()),
        exit_reason_counts_json: serde_json::to_string(&exit_counts)
            .unwrap_or_else(|_| "{}".to_string()),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn trade_config_key(trade: &TradeRow) -> ConfigKey {
    ConfigKey {
        fold: trade.fold.clone(),
        gate_group: trade.gate_group.clone(),
        gate_id: trade.gate_id.clone(),
        gate_name: trade.gate_name.clone(),
        symbol: trade.symbol.clone(),
        execution_model: trade.execution_model.clone(),
        tp_bps: trade.tp_bps,
        sl_bps: trade.sl_bps,
        timeout_minutes: trade.timeout_minutes,
    }
}

fn daily_config_key(row: &DailyRow) -> ConfigKey {
    ConfigKey {
        fold: row.fold.clone(),
        gate_group: row.gate_group.clone(),
        gate_id: row.gate_id.clone(),
        gate_name: row.gate_name.clone(),
        symbol: row.symbol.clone(),
        execution_model: row.execution_model.clone(),
        tp_bps: row.tp_bps,
        sl_bps: row.sl_bps,
        timeout_minutes: row.timeout_minutes,
    }
}

fn all_key_from_config(key: &ConfigKey) -> AllKey {
    AllKey {
        gate_group: key.gate_group.clone(),
        gate_id: key.gate_id.clone(),
        gate_name: key.gate_name.clone(),
        symbol: key.symbol.clone(),
        execution_model: key.execution_model.clone(),
        tp_bps: key.tp_bps,
        sl_bps: key.sl_bps,
        timeout_minutes: key.timeout_minutes,
    }
}

fn validate_outputs(
    trades: &[TradeRow],
    daily: &[DailyRow],
    summary: &[SummaryRow],
) -> ValidationChecks {
    let mut ids = HashSet::new();
    let mut duplicate_trade_ids = 0usize;
    let mut missing_exit_reason = 0usize;
    let mut entry_not_after_signal = 0usize;
    for trade in trades {
        if !ids.insert(trade.trade_id.as_str()) {
            duplicate_trade_ids += 1;
        }
        if trade.exit_reason.is_empty() {
            missing_exit_reason += 1;
        }
        if trade.entry_timestamp_us <= trade.signal_timestamp_us {
            entry_not_after_signal += 1;
        }
    }
    let trade_pnl: f64 = trades.iter().map(|trade| trade.pnl_quote).sum();
    let daily_pnl: f64 = daily.iter().map(|row| row.total_pnl_quote).sum();
    let daily_trade_pnl_abs_diff = (trade_pnl - daily_pnl).abs();
    let cost_monotonic_violations = cost_monotonic_violations(summary);
    let passed = duplicate_trade_ids == 0
        && missing_exit_reason == 0
        && entry_not_after_signal == 0
        && daily_trade_pnl_abs_diff < 1e-6
        && cost_monotonic_violations == 0;
    ValidationChecks {
        duplicate_trade_ids,
        missing_exit_reason,
        entry_not_after_signal,
        daily_trade_pnl_abs_diff,
        cost_monotonic_violations,
        passed,
    }
}

fn cost_monotonic_violations(summary: &[SummaryRow]) -> usize {
    let mut grouped: HashMap<(String, u32, u32, u32), HashMap<String, f64>> = HashMap::new();
    for row in summary
        .iter()
        .filter(|row| row.summary_scope == "all_folds")
    {
        if let Some(cost) = row.avg_cost_bps {
            grouped
                .entry((
                    row.gate_id.clone(),
                    row.tp_bps,
                    row.sl_bps,
                    row.timeout_minutes,
                ))
                .or_default()
                .insert(row.execution_model.clone(), cost);
        }
    }
    grouped
        .values()
        .filter(|costs| {
            let Some(mid) = costs.get("mid_research") else {
                return false;
            };
            let Some(maker) = costs.get("maker_light") else {
                return false;
            };
            let Some(taker) = costs.get("taker_spread") else {
                return false;
            };
            let Some(wide) = costs.get("wide_stress") else {
                return false;
            };
            !(mid <= maker && maker <= taker && taker <= wide)
        })
        .count()
}

fn build_completion(
    config: &EpisodeConfig,
    out_tag: &str,
    paths: &OutputPaths,
    panel_path: &Path,
    l2_state_path: &Path,
    gates: &[GateSpec],
    trades: &[TradeRow],
    daily: &[DailyRow],
    summary_rows: &[SummaryRow],
    configs: &[ConfigRow],
    validation_checks: &ValidationChecks,
) -> Completion {
    Completion {
        eval_name: "bonk_v6_episode_backtest".to_string(),
        generated_at_utc: iso_now(),
        run_tag: config.run_tag.clone(),
        out_tag: out_tag.to_string(),
        guardrail: GUARDRAIL.to_string(),
        inputs: CompletionInputs {
            panel: path_string(panel_path),
            l2_state: path_string(l2_state_path),
        },
        outputs: CompletionOutputs {
            trades: path_string(&paths.trades),
            daily: path_string(&paths.daily),
            summary: path_string(&paths.summary),
            completion: path_string(&paths.completion),
        },
        report: path_string(&config.report_md),
        gates: gates.to_vec(),
        folds: FOLDS.to_vec(),
        params: CompletionParams {
            tp_bps: config.tp_bps.clone(),
            sl_bps: config.sl_bps.clone(),
            timeout_minutes: config.timeout_minutes.clone(),
            execution_models: config.execution_models.clone(),
            notional_quote: config.notional_quote,
            fee_bps: config.fee_bps,
        },
        counts: CompletionCounts {
            config_rows: configs.len(),
            trades: trades.len(),
            daily_rows: daily.len(),
            summary_rows: summary_rows.len(),
            episode_starts: configs.iter().map(|row| row.episode_starts).sum(),
            entry_skips: configs.iter().map(|row| row.entry_skips).sum(),
        },
        validation_checks: validation_checks.clone(),
    }
}

fn build_report(
    config: &EpisodeConfig,
    out_tag: &str,
    gates: &[GateSpec],
    trades: &[TradeRow],
    daily: &[DailyRow],
    summary: &[SummaryRow],
    completion: &Completion,
) -> String {
    let all_rows: Vec<&SummaryRow> = summary
        .iter()
        .filter(|row| row.summary_scope == "all_folds")
        .collect();
    let maker = top_rows(&all_rows, Some("maker_light"), None, 12);
    let taker = top_rows(&all_rows, Some("taker_spread"), None, 12);
    let mid = top_rows(&all_rows, Some("mid_research"), None, 8);
    let wide = top_rows(&all_rows, Some("wide_stress"), None, 8);
    let active = top_rows(&all_rows, None, Some("active"), 16);
    let ambiguous = trades
        .iter()
        .filter(|trade| trade.same_bar_ambiguous)
        .count();
    let mut lines = Vec::new();
    lines.push("# BONK V6 Episode Backtest".to_string());
    lines.push(String::new());
    lines.push(format!(
        "Status: {}. Run tag: `{}`. Output tag: `{}`.",
        iso_now(),
        config.run_tag,
        out_tag
    ));
    lines.push(String::new());
    lines.push("This report is research-only. It is not a trading rule, not an execution instruction, not a sizing rule, and not an alpha claim.".to_string());
    lines.push(String::new());
    lines.push("## Setup".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- Gates: {}.",
        gates
            .iter()
            .map(|gate| gate.gate_id)
            .collect::<Vec<_>>()
            .join(", ")
    ));
    lines.push(format!(
        "- TP grid: `{:?}` bps; SL grid: `{:?}` bps; timeout grid: `{:?}` minutes.",
        config.tp_bps, config.sl_bps, config.timeout_minutes
    ));
    lines.push(format!(
        "- Execution models: `{:?}`; notional quote: `{}`.",
        config.execution_models, config.notional_quote
    ));
    lines.push(
        "- Entry: next-minute Bullish L2 mid open after a false-to-true gate transition."
            .to_string(),
    );
    lines.push("- Exit order: worst-case same-bar stop, stop, take-profit, gate-off, timeout, data-gap/fold-end.".to_string());
    lines.push(String::new());
    lines.push("## Completion".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- Trades: `{}`; daily rows: `{}`; summary rows: `{}`.",
        trades.len(),
        daily.len(),
        summary.len()
    ));
    lines.push(format!(
        "- Validation checks passed: `{}`.",
        completion.validation_checks.passed
    ));
    lines.push(format!("- Same-bar ambiguous trades: `{}`.", ambiguous));
    lines.push(String::new());
    lines.push("## Maker-Light Top Rows".to_string());
    lines.push(String::new());
    lines.push(markdown_table(&maker));
    lines.push(String::new());
    lines.push("## Taker-Spread Top Rows".to_string());
    lines.push(String::new());
    lines.push(markdown_table(&taker));
    lines.push(String::new());
    lines.push("## Mid Research Upper Bound".to_string());
    lines.push(String::new());
    lines.push(markdown_table(&mid));
    lines.push(String::new());
    lines.push("## Wide Stress Downside".to_string());
    lines.push(String::new());
    lines.push(markdown_table(&wide));
    lines.push(String::new());
    lines.push("## Active Gate View".to_string());
    lines.push(String::new());
    lines.push(markdown_table(&active));
    lines.push(String::new());
    lines.push("## Read".to_string());
    lines.push(String::new());
    lines.push("- `mid_research` is only a signal-shape upper bound; it is not a feasible execution claim.".to_string());
    lines.push("- `maker_light` and `taker_spread` are the main rows to inspect for small-account feasibility.".to_string());
    lines.push("- The grid is exploratory and should be read with parameter-sensitivity, fold, and same-bar ambiguity columns next to PnL.".to_string());
    lines.push("- A positive row in this short window is a candidate for next-window validation, not evidence of persistent alpha.".to_string());
    lines.push(String::new());
    lines.push("## Outputs".to_string());
    lines.push(String::new());
    lines.push(format!("- `{}`", completion.outputs.trades));
    lines.push(format!("- `{}`", completion.outputs.daily));
    lines.push(format!("- `{}`", completion.outputs.summary));
    lines.push(format!("- `{}`", completion.outputs.completion));
    lines.join("\n") + "\n"
}

fn top_rows<'a>(
    rows: &[&'a SummaryRow],
    execution_model: Option<&str>,
    gate_group: Option<&str>,
    limit: usize,
) -> Vec<&'a SummaryRow> {
    let mut out: Vec<&SummaryRow> = rows
        .iter()
        .copied()
        .filter(|row| execution_model.is_none_or(|model| row.execution_model == model))
        .filter(|row| gate_group.is_none_or(|group| row.gate_group == group))
        .collect();
    out.sort_by(|a, b| b.avg_daily_pnl_quote.total_cmp(&a.avg_daily_pnl_quote));
    out.truncate(limit);
    out
}

fn markdown_table(rows: &[&SummaryRow]) -> String {
    if rows.is_empty() {
        return "_No rows._".to_string();
    }
    let mut lines = vec![
        "| gate | exec | tp | sl | to | avg $/day | total $ | win | tr/d | max DD | ambig |"
            .to_string(),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |".to_string(),
    ];
    for row in rows {
        lines.push(format!(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
            row.gate_id,
            row.execution_model,
            row.tp_bps,
            row.sl_bps,
            row.timeout_minutes,
            fmt_float(row.avg_daily_pnl_quote, 3),
            fmt_float(row.total_pnl_quote, 3),
            fmt_pct(row.win_rate),
            fmt_float(row.trades_per_day, 2),
            fmt_float(row.max_drawdown_quote, 3),
            fmt_pct(row.ambiguous_trade_rate),
        ));
    }
    lines.join("\n")
}

fn read_panel_rows(path: &Path, run_tag: &str, symbols: &HashSet<String>) -> Result<Vec<PanelRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let run_tag_col = str_array(&batch, "run_tag")?;
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        let horizon_hours = u64_array_col(&batch, "horizon_hours")?;
        let barrier_bps = u64_array_col(&batch, "barrier_bps")?;
        let label_status = str_array(&batch, "label_status")?;
        let top_depth_total_notional_median = f64_array(&batch, "top_depth_total_notional_median")?;
        let ctx_bonk_rv_1h_bps = f64_array(&batch, "ctx_bonk_rv_1h_bps")?;
        let cross_venue_spread_diff_bps = f64_array(&batch, "cross_venue_spread_diff_bps")?;
        let snapshot_microprice_offset_bps_mean =
            f64_array(&batch, "snapshot_microprice_offset_bps_mean")?;
        for idx in 0..batch.num_rows() {
            let sym = str_value(symbol, idx);
            if run_tag_col.value(idx) != run_tag
                || !symbols.contains(&sym)
                || u64_value(horizon_hours, idx) != PRIMARY_HORIZON_HOURS
                || u64_value(barrier_bps, idx) != PRIMARY_BARRIER_BPS
                || label_status.value(idx) != "ok"
            {
                continue;
            }
            out.push(PanelRow {
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: sym,
                top_depth_total_notional_median: opt_f64_value(
                    top_depth_total_notional_median,
                    idx,
                ),
                ctx_bonk_rv_1h_bps: opt_f64_value(ctx_bonk_rv_1h_bps, idx),
                cross_venue_spread_diff_bps: opt_f64_value(cross_venue_spread_diff_bps, idx),
                snapshot_microprice_offset_bps_mean: opt_f64_value(
                    snapshot_microprice_offset_bps_mean,
                    idx,
                ),
            });
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then(a.timestamp_us.cmp(&b.timestamp_us))
    });
    if out.is_empty() {
        return Err(anyhow!("panel selection is empty: {}", path.display()));
    }
    Ok(out)
}

fn read_l2_rows(path: &Path, run_tag: &str, symbols: &HashSet<String>) -> Result<Vec<L2Row>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let run_tag_col = str_array(&batch, "run_tag")?;
        let timestamp_utc = str_array(&batch, "timestamp_utc")?;
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        let mid_open = f64_array(&batch, "mid_price_per_unit_open")?;
        let mid_high = f64_array(&batch, "mid_price_per_unit_high")?;
        let mid_low = f64_array(&batch, "mid_price_per_unit_low")?;
        let mid_close = f64_array(&batch, "mid_price_per_unit_close")?;
        let spread_bps_median = f64_array(&batch, "spread_bps_median")?;
        let depth_bid_25 = f64_array(&batch, "depth_bid_notional_25_median")?;
        let depth_ask_25 = f64_array(&batch, "depth_ask_notional_25_median")?;
        for idx in 0..batch.num_rows() {
            let sym = str_value(symbol, idx);
            if run_tag_col.value(idx) != run_tag || !symbols.contains(&sym) {
                continue;
            }
            out.push(L2Row {
                timestamp_us: u64_value(timestamp_us, idx),
                timestamp_utc: str_value(timestamp_utc, idx),
                symbol: sym,
                mid_price_per_unit_open: opt_f64_value(mid_open, idx),
                mid_price_per_unit_high: opt_f64_value(mid_high, idx),
                mid_price_per_unit_low: opt_f64_value(mid_low, idx),
                mid_price_per_unit_close: opt_f64_value(mid_close, idx),
                spread_bps_median: opt_f64_value(spread_bps_median, idx),
                depth_bid_notional_25_median: opt_f64_value(depth_bid_25, idx),
                depth_ask_notional_25_median: opt_f64_value(depth_ask_25, idx),
            });
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then(a.timestamp_us.cmp(&b.timestamp_us))
    });
    if out.is_empty() {
        return Err(anyhow!("L2 state selection is empty: {}", path.display()));
    }
    Ok(out)
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
        finite_option(array.value(index))
    }
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
    std::fs::write(&temp, text).with_context(|| format!("failed to write {}", temp.display()))?;
    replace_file(&temp, path)
}

fn ensure_parent_dir(path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    Ok(())
}

fn temp_path_for(path: &Path) -> PathBuf {
    let mut temp = path.to_path_buf();
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("tmp");
    temp.set_file_name(format!(
        "{file_name}.{}.{}.part",
        std::process::id(),
        Utc::now().timestamp_micros()
    ));
    temp
}

fn replace_file(temp: &Path, path: &Path) -> Result<()> {
    let mut last_error: Option<std::io::Error> = None;
    for attempt in 0..20 {
        if path.exists() {
            match std::fs::remove_file(path) {
                Ok(()) => {}
                Err(err) => {
                    last_error = Some(err);
                    sleep(Duration::from_millis(250));
                    continue;
                }
            }
        }
        match std::fs::rename(temp, path) {
            Ok(()) => return Ok(()),
            Err(err) => {
                last_error = Some(err);
                let delay_ms = 150 + (attempt as u64 * 75);
                sleep(Duration::from_millis(delay_ms));
            }
        }
    }
    Err(anyhow!(
        "failed to rename {} to {} after retries: {}",
        temp.display(),
        path.display(),
        last_error
            .map(|err| err.to_string())
            .unwrap_or_else(|| "unknown error".to_string())
    ))
}

fn utc_us(raw: &str) -> Result<u64> {
    let parsed = DateTime::parse_from_rfc3339(raw)
        .with_context(|| format!("failed to parse timestamp {raw}"))?
        .with_timezone(&Utc);
    Ok(parsed.timestamp_micros() as u64)
}

fn iso_now() -> String {
    Utc::now()
        .to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
        .replace("+00:00", "Z")
}

fn date_part(timestamp_utc: &str) -> String {
    timestamp_utc
        .get(0..10)
        .filter(|value| NaiveDate::parse_from_str(value, "%Y-%m-%d").is_ok())
        .unwrap_or("")
        .to_string()
}

fn valid_price(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn finite_option(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn max_drawdown(pnl_values: &[f64]) -> f64 {
    let mut curve = 0.0;
    let mut peak = 0.0;
    let mut max_dd = 0.0;
    for pnl in pnl_values {
        curve += *pnl;
        if curve > peak {
            peak = curve;
        }
        let dd = peak - curve;
        if dd > max_dd {
            max_dd = dd;
        }
    }
    max_dd
}

fn rate_count(numer: usize, denom: usize) -> f64 {
    if denom == 0 {
        0.0
    } else {
        numer as f64 / denom as f64
    }
}

fn mean(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        Some(values.iter().sum::<f64>() / values.len() as f64)
    }
}

fn mean_iter<I>(values: I) -> Option<f64>
where
    I: Iterator<Item = f64>,
{
    let mut sum = 0.0;
    let mut count = 0usize;
    for value in values {
        if value.is_finite() {
            sum += value;
            count += 1;
        }
    }
    (count > 0).then_some(sum / count as f64)
}

fn percentile_sorted(values: &[f64], q: f64) -> Option<f64> {
    let clean: Vec<f64> = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect();
    if clean.is_empty() {
        None
    } else {
        Some(quantile(&clean, q))
    }
}

fn profit_factor(pnl: &[f64]) -> Option<f64> {
    if pnl.is_empty() {
        return None;
    }
    let gains: f64 = pnl.iter().copied().filter(|value| *value > 0.0).sum();
    let losses: f64 = pnl.iter().copied().filter(|value| *value < 0.0).sum();
    if losses == 0.0 {
        if gains > 0.0 {
            Some(f64::INFINITY)
        } else {
            None
        }
    } else {
        Some(gains / losses.abs())
    }
}

fn fmt_float(value: f64, digits: usize) -> String {
    if value.is_finite() {
        format!("{value:.digits$}")
    } else {
        String::new()
    }
}

fn fmt_pct(value: f64) -> String {
    if value.is_finite() {
        format!("{:.1}%", value * 100.0)
    } else {
        String::new()
    }
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

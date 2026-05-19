use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use anyhow::{Context, Result, bail};
use chrono::{SecondsFormat, Utc};
use finance_chain_core::storage::ensure_parent_dir;
use serde::de::{self, Deserializer};
use serde::{Deserialize, Serialize};

use crate::download::path_string;
use crate::v10::DEFAULT_V10_RUN_TAG;

const GUARDRAIL: &str = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim";
const V10_PURGE_US: u64 = 300_000_000;
const REQUIRED_SYMBOLS: [&str; 2] = ["BONK1MUSDC", "BONK1MUSDT"];
const STRUCTURE_WINDOWS: [u32; 3] = [60, 300, 900];
const WAIT_SECONDS: [u32; 3] = [300, 600, 1800];
const TIMEOUT_SECONDS: [u32; 2] = [1800, 3600];
const ENTRY_SPECS: [EntrySpec; 6] = [
    EntrySpec {
        mode: EntryMode::Pullback,
        name: "pullback_382",
        lambda: Some(0.382),
    },
    EntrySpec {
        mode: EntryMode::Pullback,
        name: "pullback_500",
        lambda: Some(0.500),
    },
    EntrySpec {
        mode: EntryMode::Pullback,
        name: "pullback_618",
        lambda: Some(0.618),
    },
    EntrySpec {
        mode: EntryMode::BreakoutConfirm,
        name: "breakout_confirm",
        lambda: None,
    },
    EntrySpec {
        mode: EntryMode::RangeMidRetest,
        name: "range_mid_retest",
        lambda: None,
    },
    EntrySpec {
        mode: EntryMode::LiquidityRecovery,
        name: "liquidity_recovery",
        lambda: None,
    },
];
const BARRIER_SPECS: [BarrierSpec; 2] = [
    BarrierSpec {
        name: "balanced_vol_1x_range_05",
        alpha_u: 1.0,
        alpha_d: 1.0,
        beta_d: 0.50,
        margin_bps: 1.0,
    },
    BarrierSpec {
        name: "patient_vol_15x_range_075",
        alpha_u: 1.5,
        alpha_d: 1.0,
        beta_d: 0.75,
        margin_bps: 1.0,
    },
];
const MIN_TRAIN_FILLS_STRICT: usize = 20;
const MIN_TRAIN_FILLS_FALLBACK: usize = 5;
const MIN_VALID_FILLS: usize = 30;
const MAX_DATE_SHARE: f64 = 0.65;
const CONTROL_ABS_GE_BASE_LIMIT: f64 = 0.35;
const MAX_TRAIN_SIGNALS_PER_BUCKET: usize = 80;
const FILE_REPLACE_RETRIES: usize = 80;
const FILE_REPLACE_RETRY_MS: u64 = 250;
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct V12Config {
    pub date_dir: PathBuf,
    pub report_md: PathBuf,
    pub run_tag: String,
    pub fee_bps: f64,
    pub cooldown_seconds: u32,
}

impl Default for V12Config {
    fn default() -> Self {
        Self {
            date_dir: PathBuf::from("date"),
            report_md: PathBuf::from("docs/markets/bonk/v1-cex-v12-pending-entry-adaptive-tpsl.md"),
            run_tag: DEFAULT_V10_RUN_TAG.to_string(),
            fee_bps: 2.0,
            cooldown_seconds: 300,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct V12Summary {
    pub run_tag: String,
    pub potential_rows: usize,
    pub candidate_rows: usize,
    pub trade_rows: usize,
    pub summary_rows: usize,
    pub negative_control_rows: usize,
    pub primary_status: String,
    pub candidates_csv: String,
    pub trades_csv: String,
    pub summary_csv: String,
    pub negative_controls_csv: String,
    pub failure_report_csv: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    potential_csv: PathBuf,
    candidates_csv: PathBuf,
    trades_csv: PathBuf,
    summary_csv: PathBuf,
    negative_controls_csv: PathBuf,
    failure_report_csv: PathBuf,
    report_md: PathBuf,
}

impl Paths {
    fn new(config: &V12Config) -> Self {
        Self {
            potential_csv: config
                .date_dir
                .join(format!("bonk_v10_potential_state_{}.csv", config.run_tag)),
            candidates_csv: config.date_dir.join(format!(
                "bonk_v12_pending_entry_candidates_{}.csv",
                config.run_tag
            )),
            trades_csv: config.date_dir.join(format!(
                "bonk_v12_pending_entry_trades_{}.csv",
                config.run_tag
            )),
            summary_csv: config.date_dir.join(format!(
                "bonk_v12_pending_entry_summary_{}.csv",
                config.run_tag
            )),
            negative_controls_csv: config.date_dir.join(format!(
                "bonk_v12_pending_entry_negative_controls_{}.csv",
                config.run_tag
            )),
            failure_report_csv: config.date_dir.join(format!(
                "bonk_v12_pending_entry_failure_report_{}.csv",
                config.run_tag
            )),
            report_md: config.report_md.clone(),
        }
    }
}

#[derive(Debug, Clone)]
struct PotentialRow {
    run_tag: String,
    date: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    mid_price: Option<f64>,
    spread_bps: Option<f64>,
    trade_buy_amount: f64,
    trade_sell_amount: f64,
    trade_notional_quote: f64,
    trade_flow_imbalance: Option<f64>,
    fill_realism_score: Option<f64>,
}

impl PotentialRow {
    fn has_trade_flow_signal(&self) -> bool {
        self.mid_price
            .is_some_and(|value| value.is_finite() && value > 0.0)
            && self
                .spread_bps
                .is_some_and(|value| value.is_finite() && value >= 0.0)
            && self
                .fill_realism_score
                .is_some_and(|value| value.is_finite())
            && self.trade_notional_quote > 0.0
            && self.trade_flow_imbalance.unwrap_or(0.0).abs() > 0.0
            && (self.trade_buy_amount - self.trade_sell_amount).abs() > 0.0
    }

    fn flow(&self) -> Option<FlowDerived> {
        if !self.has_trade_flow_signal() {
            return None;
        }
        let delta = self.trade_buy_amount - self.trade_sell_amount;
        let side_sign = if delta > 0.0 { 1 } else { -1 };
        let signed_flow_shock = side_sign as f64 * self.trade_notional_quote.ln_1p();
        finite(signed_flow_shock).map(|signed_flow_shock| FlowDerived {
            side_sign,
            signed_flow_shock,
            abs_flow_shock: signed_flow_shock.abs(),
        })
    }
}

#[derive(Debug, Clone, Copy)]
struct FlowDerived {
    side_sign: i8,
    signed_flow_shock: f64,
    abs_flow_shock: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct RawPotentialRow {
    run_tag: String,
    date: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    #[serde(deserialize_with = "de_opt_f64")]
    mid_price: Option<f64>,
    #[serde(deserialize_with = "de_opt_f64")]
    spread_bps: Option<f64>,
    #[serde(deserialize_with = "de_f64_or_zero")]
    trade_buy_amount: f64,
    #[serde(deserialize_with = "de_f64_or_zero")]
    trade_sell_amount: f64,
    #[serde(deserialize_with = "de_f64_or_zero")]
    trade_notional_quote: f64,
    #[serde(deserialize_with = "de_opt_f64")]
    trade_flow_imbalance: Option<f64>,
    #[serde(deserialize_with = "de_opt_f64")]
    fill_realism_score: Option<f64>,
}

impl From<RawPotentialRow> for PotentialRow {
    fn from(row: RawPotentialRow) -> Self {
        Self {
            run_tag: row.run_tag,
            date: row.date,
            symbol: row.symbol,
            timestamp: row.timestamp,
            local_timestamp: row.local_timestamp,
            mid_price: row.mid_price.and_then(finite),
            spread_bps: row.spread_bps.and_then(finite),
            trade_buy_amount: row.trade_buy_amount.max(0.0),
            trade_sell_amount: row.trade_sell_amount.max(0.0),
            trade_notional_quote: row.trade_notional_quote.max(0.0),
            trade_flow_imbalance: row.trade_flow_imbalance.and_then(finite),
            fill_realism_score: row.fill_realism_score.and_then(finite),
        }
    }
}

#[derive(Debug, Clone)]
struct FoldRange {
    name: String,
    train_start: u64,
    train_end: u64,
    valid_start: u64,
    valid_end: u64,
}

#[derive(Debug, Clone)]
struct ThresholdSet {
    fold: FoldRange,
    symbol: String,
    shock_q95: f64,
    shock_q99: f64,
    train_rows: usize,
    valid_rows: usize,
}

#[derive(Debug, Clone)]
struct WatchSignal {
    run_tag: String,
    phase: Phase,
    fold: String,
    date: String,
    symbol: String,
    bucket: String,
    threshold: f64,
    pos: usize,
    timestamp: u64,
    local_timestamp: u64,
    side_sign: i8,
    signed_flow_shock: f64,
    abs_flow_shock: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Phase {
    Train,
    Validation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
enum EntryMode {
    Pullback,
    BreakoutConfirm,
    RangeMidRetest,
    LiquidityRecovery,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct EntrySpec {
    mode: EntryMode,
    name: &'static str,
    lambda: Option<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct BarrierSpec {
    name: &'static str,
    alpha_u: f64,
    alpha_d: f64,
    beta_d: f64,
    margin_bps: f64,
}

#[derive(Debug, Clone, PartialEq)]
struct StrategySpec {
    source_signal: String,
    entry: EntrySpec,
    barrier: BarrierSpec,
    structure_window_seconds: u32,
    wait_seconds: u32,
    timeout_seconds: u32,
}

impl StrategySpec {
    fn id(&self) -> String {
        format!(
            "{}|{}|{}|struct{}s|wait{}s|timeout{}s",
            self.source_signal,
            self.entry.name,
            self.barrier.name,
            self.structure_window_seconds,
            self.wait_seconds,
            self.timeout_seconds
        )
    }
}

#[derive(Debug, Clone, Serialize)]
struct CandidateRow {
    run_tag: String,
    fold: String,
    symbol: String,
    bucket: String,
    selected: bool,
    strategy_id: String,
    source_signal: String,
    entry_mode: String,
    structure_window_seconds: u32,
    wait_seconds: u32,
    timeout_seconds: u32,
    barrier_profile: String,
    alpha_u: f64,
    alpha_d: f64,
    beta_d: f64,
    margin_bps: f64,
    train_setups: usize,
    train_fills: usize,
    train_fill_rate: f64,
    train_maker_net_bps_mean: Option<f64>,
    train_taker_net_bps_mean: Option<f64>,
    train_win_rate: Option<f64>,
    train_max_date_share: Option<f64>,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct TradeRow {
    run_tag: String,
    fold: String,
    phase: String,
    date: String,
    symbol: String,
    bucket: String,
    strategy_id: String,
    source_signal: String,
    entry_mode: String,
    barrier_profile: String,
    structure_window_seconds: u32,
    wait_seconds: u32,
    timeout_seconds: u32,
    signal_timestamp: u64,
    signal_local_timestamp: u64,
    side: String,
    fill_status: String,
    exit_reason: String,
    signal_mid: Option<f64>,
    entry_target_price: Option<f64>,
    entry_local_timestamp: Option<u64>,
    exit_local_timestamp: Option<u64>,
    entry_price: Option<f64>,
    exit_price: Option<f64>,
    take_profit_bps: Option<f64>,
    stop_loss_bps: Option<f64>,
    take_profit_price: Option<f64>,
    stop_loss_price: Option<f64>,
    gross_bps: Option<f64>,
    fee_bps: f64,
    maker_cost_bps: Option<f64>,
    taker_cost_bps: Option<f64>,
    maker_net_bps: Option<f64>,
    taker_net_bps: Option<f64>,
    pre_range_bps: Option<f64>,
    pre_sigma_bps: Option<f64>,
    spread_bps: Option<f64>,
    fill_realism_score: Option<f64>,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct SummaryRow {
    run_tag: String,
    fold: String,
    symbol: String,
    bucket: String,
    strategy_id: String,
    source_signal: String,
    entry_mode: String,
    barrier_profile: String,
    structure_window_seconds: u32,
    wait_seconds: u32,
    timeout_seconds: u32,
    setups: usize,
    fills: usize,
    no_fills: usize,
    fill_rate: f64,
    maker_net_bps_mean: Option<f64>,
    taker_net_bps_mean: Option<f64>,
    gross_bps_mean: Option<f64>,
    maker_cost_bps_mean: Option<f64>,
    win_rate: Option<f64>,
    take_profit_rate: Option<f64>,
    stop_loss_rate: Option<f64>,
    timeout_rate: Option<f64>,
    max_date_share: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    best_control_maker_net_bps_mean: Option<f64>,
    control_separated: bool,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct NegativeControlRow {
    run_tag: String,
    control_type: String,
    fold: String,
    symbol: String,
    bucket: String,
    strategy_id: String,
    setups: usize,
    fills: usize,
    fill_rate: f64,
    maker_net_bps_mean: Option<f64>,
    taker_net_bps_mean: Option<f64>,
    gross_bps_mean: Option<f64>,
    win_rate: Option<f64>,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct FailureReportRow {
    run_tag: String,
    primary_status: String,
    candidate_key: String,
    setups: usize,
    fills: usize,
    fill_rate: f64,
    maker_net_bps_mean: Option<f64>,
    best_control_maker_net_bps_mean: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    max_date_share: Option<f64>,
    evidence: String,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct InputAudit {
    potential_rows: usize,
    missing_mid_rows: usize,
    missing_spread_rows: usize,
    missing_fill_rows: usize,
    sort_violations: usize,
    blockers: Vec<String>,
}

#[derive(Debug, Clone)]
struct Structure {
    high: f64,
    low: f64,
    range_price: f64,
    range_bps: f64,
    sigma_bps: f64,
    median_spread_bps: f64,
    median_fill_realism: f64,
}

#[derive(Debug, Clone)]
enum EntryRule {
    Price {
        target: f64,
        condition: EntryCondition,
    },
    LiquidityRecovery {
        max_spread_bps: f64,
        min_fill_realism: f64,
    },
    RandomizedPrice {
        target: f64,
        condition: EntryCondition,
    },
}

#[derive(Debug, Clone, Copy)]
enum EntryCondition {
    AtOrBelow,
    AtOrAbove,
}

#[derive(Debug, Clone)]
struct SimResult {
    fill_status: String,
    exit_reason: String,
    entry_target_price: Option<f64>,
    entry_pos: Option<usize>,
    exit_pos: Option<usize>,
    entry_price: Option<f64>,
    exit_price: Option<f64>,
    take_profit_bps: Option<f64>,
    stop_loss_bps: Option<f64>,
    take_profit_price: Option<f64>,
    stop_loss_price: Option<f64>,
    gross_bps: Option<f64>,
    maker_cost_bps: Option<f64>,
    taker_cost_bps: Option<f64>,
    maker_net_bps: Option<f64>,
    taker_net_bps: Option<f64>,
    pre_range_bps: Option<f64>,
    pre_sigma_bps: Option<f64>,
    spread_bps: Option<f64>,
    fill_realism_score: Option<f64>,
}

#[derive(Debug, Clone)]
struct GroupStats {
    setups: usize,
    fills: usize,
    no_fills: usize,
    maker_net: Vec<f64>,
    taker_net: Vec<f64>,
    gross: Vec<f64>,
    maker_cost: Vec<f64>,
    wins: usize,
    take_profit: usize,
    stop_loss: usize,
    timeout: usize,
    date_counts: BTreeMap<String, usize>,
}

pub fn run_v12(config: &V12Config) -> Result<V12Summary> {
    if !config.fee_bps.is_finite() || config.fee_bps < 0.0 {
        bail!("--fee-bps must be finite and non-negative");
    }
    if config.cooldown_seconds == 0 {
        bail!("--cooldown-seconds must be positive");
    }

    let paths = Paths::new(config);
    let (mut rows, audit) = read_potential_rows(&paths.potential_csv, &config.run_tag)?;
    rows.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.local_timestamp.cmp(&b.local_timestamp))
    });
    let by_symbol = rows_by_symbol(&rows);
    let thresholds = fit_thresholds(&by_symbol);
    let specs = strategy_grid();

    let mut candidate_rows = Vec::new();
    let mut selected: Vec<(ThresholdSet, String, StrategySpec)> = Vec::new();
    for fit in &thresholds {
        let Some(symbol_rows) = by_symbol.get(&fit.symbol) else {
            continue;
        };
        let train_signals =
            build_watch_signals(symbol_rows, fit, Phase::Train, config.cooldown_seconds);
        for bucket in ["shock_q95", "shock_q99"] {
            let bucket_signals = train_signals
                .iter()
                .filter(|signal| signal.bucket == bucket)
                .cloned()
                .collect::<Vec<_>>();
            let bucket_signals = sample_train_signals(bucket_signals, MAX_TRAIN_SIGNALS_PER_BUCKET);
            let mut rows_for_bucket = specs
                .iter()
                .map(|spec| candidate_row_for_spec(config, symbol_rows, fit, &bucket_signals, spec))
                .collect::<Vec<_>>();
            let selected_idx = select_candidate(&rows_for_bucket);
            if let Some(idx) = selected_idx {
                rows_for_bucket[idx].selected = true;
                selected.push((
                    fit.clone(),
                    rows_for_bucket[idx].bucket.clone(),
                    specs[idx % specs.len()].clone(),
                ));
            }
            candidate_rows.extend(rows_for_bucket);
        }
    }

    let mut trades = Vec::new();
    let mut controls = Vec::new();
    for (fit, selected_bucket, spec) in &selected {
        let Some(symbol_rows) = by_symbol.get(&fit.symbol) else {
            continue;
        };
        let valid_signals =
            build_watch_signals(symbol_rows, fit, Phase::Validation, config.cooldown_seconds);
        let signals = valid_signals
            .iter()
            .filter(|signal| signal.bucket == *selected_bucket)
            .cloned()
            .collect::<Vec<_>>();
        trades.extend(simulate_trade_rows(
            config,
            symbol_rows,
            &signals,
            spec,
            ControlMode::Base,
            &by_symbol,
        ));
        controls.extend(simulate_controls(
            config,
            &by_symbol,
            symbol_rows,
            &signals,
            spec,
        ));
    }

    let mut control_lookup = summarize_controls(&controls);
    let mut summaries = summarize_trades(&trades);
    for summary in &mut summaries {
        let control_key = summary_key(summary);
        if let Some(control_rows) = control_lookup.remove(&control_key) {
            attach_control_metrics(summary, &control_rows);
            control_lookup.insert(control_key, control_rows);
        }
    }

    let failure = build_failure_report(&config.run_tag, &audit, &summaries);

    write_csv_atomic(&paths.candidates_csv, &candidate_rows)?;
    write_csv_atomic(&paths.trades_csv, &trades)?;
    write_csv_atomic(&paths.summary_csv, &summaries)?;
    write_csv_atomic(&paths.negative_controls_csv, &controls)?;
    write_csv_atomic(&paths.failure_report_csv, &[failure.clone()])?;
    write_report(
        config,
        &paths,
        &audit,
        &failure,
        &candidate_rows,
        &trades,
        &summaries,
        &controls,
    )?;

    Ok(V12Summary {
        run_tag: config.run_tag.clone(),
        potential_rows: audit.potential_rows,
        candidate_rows: candidate_rows.len(),
        trade_rows: trades.len(),
        summary_rows: summaries.len(),
        negative_control_rows: controls.len(),
        primary_status: failure.primary_status,
        candidates_csv: path_string(&paths.candidates_csv),
        trades_csv: path_string(&paths.trades_csv),
        summary_csv: path_string(&paths.summary_csv),
        negative_controls_csv: path_string(&paths.negative_controls_csv),
        failure_report_csv: path_string(&paths.failure_report_csv),
        report_md: path_string(&paths.report_md),
    })
}

fn read_potential_rows(path: &Path, run_tag: &str) -> Result<(Vec<PotentialRow>, InputAudit)> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    let mut rows = Vec::new();
    let mut audit = InputAudit {
        potential_rows: 0,
        missing_mid_rows: 0,
        missing_spread_rows: 0,
        missing_fill_rows: 0,
        sort_violations: 0,
        blockers: Vec::new(),
    };
    let mut seen_symbols = BTreeSet::new();
    let mut closed_symbols = BTreeSet::new();
    let mut current_symbol = String::new();
    let mut last_ts_by_symbol: BTreeMap<String, u64> = BTreeMap::new();

    for record in reader.deserialize::<RawPotentialRow>() {
        let raw = record.with_context(|| format!("failed to parse {}", path.display()))?;
        if raw.run_tag != run_tag {
            audit.blockers.push(format!(
                "potential row run_tag mismatch: expected {run_tag}, got {}",
                raw.run_tag
            ));
        }
        if current_symbol.is_empty() {
            current_symbol.clone_from(&raw.symbol);
        } else if current_symbol != raw.symbol {
            closed_symbols.insert(current_symbol.clone());
            current_symbol.clone_from(&raw.symbol);
        }
        if closed_symbols.contains(&raw.symbol) {
            audit.sort_violations += 1;
        }
        if let Some(last) = last_ts_by_symbol.get(&raw.symbol) {
            if raw.local_timestamp < *last {
                audit.sort_violations += 1;
            }
        }
        last_ts_by_symbol.insert(raw.symbol.clone(), raw.local_timestamp);
        seen_symbols.insert(raw.symbol.clone());
        let row = PotentialRow::from(raw);
        if row.mid_price.is_none() {
            audit.missing_mid_rows += 1;
        }
        if row.spread_bps.is_none() {
            audit.missing_spread_rows += 1;
        }
        if row.fill_realism_score.is_none() {
            audit.missing_fill_rows += 1;
        }
        rows.push(row);
    }
    audit.potential_rows = rows.len();
    for symbol in REQUIRED_SYMBOLS {
        if !seen_symbols.contains(symbol) {
            audit.blockers.push(format!(
                "required symbol missing from potential_state: {symbol}"
            ));
        }
    }
    if audit.sort_violations > 0 {
        audit.blockers.push(format!(
            "potential_state is not sorted by contiguous symbol/local_timestamp blocks: violations={}",
            audit.sort_violations
        ));
    }
    if rows.is_empty() {
        audit
            .blockers
            .push("potential_state has zero rows".to_string());
    }
    Ok((rows, audit))
}

fn rows_by_symbol(rows: &[PotentialRow]) -> BTreeMap<String, Vec<&PotentialRow>> {
    let mut by_symbol: BTreeMap<String, Vec<&PotentialRow>> = BTreeMap::new();
    for row in rows {
        by_symbol.entry(row.symbol.clone()).or_default().push(row);
    }
    for rows in by_symbol.values_mut() {
        rows.sort_by_key(|row| row.local_timestamp);
    }
    by_symbol
}

fn fit_thresholds(by_symbol: &BTreeMap<String, Vec<&PotentialRow>>) -> Vec<ThresholdSet> {
    let mut out = Vec::new();
    for (symbol, rows) in by_symbol {
        for fold in dynamic_folds(rows) {
            let train = rows
                .iter()
                .copied()
                .filter(|row| {
                    row.local_timestamp >= fold.train_start && row.local_timestamp <= fold.train_end
                })
                .collect::<Vec<_>>();
            let valid_rows = rows
                .iter()
                .filter(|row| {
                    row.local_timestamp >= fold.valid_start && row.local_timestamp <= fold.valid_end
                })
                .count();
            let shocks = train
                .iter()
                .filter_map(|row| row.flow().map(|flow| flow.abs_flow_shock))
                .collect::<Vec<_>>();
            let (Some(q95), Some(q99)) = (quantile(&shocks, 0.95), quantile(&shocks, 0.99)) else {
                continue;
            };
            out.push(ThresholdSet {
                fold,
                symbol: symbol.clone(),
                shock_q95: q95,
                shock_q99: q99,
                train_rows: train.len(),
                valid_rows,
            });
        }
    }
    out
}

fn dynamic_folds(rows: &[&PotentialRow]) -> Vec<FoldRange> {
    if rows.len() < 100 {
        return Vec::new();
    }
    let start = rows.first().map(|row| row.local_timestamp).unwrap_or(0);
    let end = rows.last().map(|row| row.local_timestamp).unwrap_or(start);
    let span = end.saturating_sub(start);
    if span <= V10_PURGE_US * 3 {
        return Vec::new();
    }
    [(45u64, 63u64), (60, 78), (72, 94)]
        .iter()
        .enumerate()
        .filter_map(|(idx, (train_pct, valid_end_pct))| {
            let train_end = start + span.saturating_mul(*train_pct) / 100;
            let valid_start = train_end.saturating_add(V10_PURGE_US);
            let valid_end = start + span.saturating_mul(*valid_end_pct) / 100;
            (valid_start < valid_end).then_some(FoldRange {
                name: format!("fold{}", idx + 1),
                train_start: start,
                train_end,
                valid_start,
                valid_end,
            })
        })
        .collect()
}

fn build_watch_signals(
    rows: &[&PotentialRow],
    fit: &ThresholdSet,
    phase: Phase,
    cooldown_seconds: u32,
) -> Vec<WatchSignal> {
    let (start, end) = match phase {
        Phase::Train => (fit.fold.train_start, fit.fold.train_end),
        Phase::Validation => (fit.fold.valid_start, fit.fold.valid_end),
    };
    let mut candidates = rows
        .iter()
        .enumerate()
        .filter_map(|(pos, row)| {
            if row.local_timestamp < start || row.local_timestamp > end {
                return None;
            }
            let flow = row.flow()?;
            let (bucket, threshold) = if flow.abs_flow_shock >= fit.shock_q99 {
                ("shock_q99", fit.shock_q99)
            } else if flow.abs_flow_shock >= fit.shock_q95 {
                ("shock_q95", fit.shock_q95)
            } else {
                return None;
            };
            Some(WatchSignal {
                run_tag: row.run_tag.clone(),
                phase,
                fold: fit.fold.name.clone(),
                date: row.date.clone(),
                symbol: row.symbol.clone(),
                bucket: bucket.to_string(),
                threshold,
                pos,
                timestamp: row.timestamp,
                local_timestamp: row.local_timestamp,
                side_sign: flow.side_sign,
                signed_flow_shock: flow.signed_flow_shock,
                abs_flow_shock: flow.abs_flow_shock,
            })
        })
        .collect::<Vec<_>>();
    candidates.sort_by(|a, b| {
        a.local_timestamp
            .cmp(&b.local_timestamp)
            .then_with(|| bucket_rank(&a.bucket).cmp(&bucket_rank(&b.bucket)))
    });

    let cooldown_us = cooldown_seconds as u64 * 1_000_000;
    let mut next_allowed = 0u64;
    let mut out = Vec::new();
    for candidate in candidates {
        if candidate.local_timestamp < next_allowed {
            continue;
        }
        next_allowed = candidate.local_timestamp.saturating_add(cooldown_us);
        out.push(candidate);
    }
    out
}

fn sample_train_signals(mut signals: Vec<WatchSignal>, max_rows: usize) -> Vec<WatchSignal> {
    if max_rows == 0 || signals.len() <= max_rows {
        return signals;
    }
    signals.sort_by_key(|signal| signal.local_timestamp);
    let step = signals.len() as f64 / max_rows as f64;
    let mut out = Vec::with_capacity(max_rows);
    for idx in 0..max_rows {
        let source_idx = ((idx as f64) * step).floor() as usize;
        out.push(signals[source_idx.min(signals.len() - 1)].clone());
    }
    out
}

fn strategy_grid() -> Vec<StrategySpec> {
    let mut out = Vec::new();
    for entry in ENTRY_SPECS {
        for structure_window_seconds in STRUCTURE_WINDOWS {
            for wait_seconds in WAIT_SECONDS {
                for timeout_seconds in TIMEOUT_SECONDS {
                    for barrier in BARRIER_SPECS {
                        out.push(StrategySpec {
                            source_signal: "v11_trade_flow_shock".to_string(),
                            entry,
                            barrier,
                            structure_window_seconds,
                            wait_seconds,
                            timeout_seconds,
                        });
                    }
                }
            }
        }
    }
    out
}

fn candidate_row_for_spec(
    config: &V12Config,
    rows: &[&PotentialRow],
    fit: &ThresholdSet,
    signals: &[WatchSignal],
    spec: &StrategySpec,
) -> CandidateRow {
    let trades = simulate_trade_rows(
        config,
        rows,
        signals,
        spec,
        ControlMode::Base,
        &BTreeMap::new(),
    );
    let stats = group_stats(&trades);
    CandidateRow {
        run_tag: config.run_tag.clone(),
        fold: fit.fold.name.clone(),
        symbol: fit.symbol.clone(),
        bucket: signals
            .first()
            .map(|signal| signal.bucket.clone())
            .unwrap_or_else(|| "none".to_string()),
        selected: false,
        strategy_id: spec.id(),
        source_signal: spec.source_signal.clone(),
        entry_mode: spec.entry.name.to_string(),
        structure_window_seconds: spec.structure_window_seconds,
        wait_seconds: spec.wait_seconds,
        timeout_seconds: spec.timeout_seconds,
        barrier_profile: spec.barrier.name.to_string(),
        alpha_u: spec.barrier.alpha_u,
        alpha_d: spec.barrier.alpha_d,
        beta_d: spec.barrier.beta_d,
        margin_bps: spec.barrier.margin_bps,
        train_setups: stats.setups,
        train_fills: stats.fills,
        train_fill_rate: rate(stats.fills, stats.setups),
        train_maker_net_bps_mean: mean(&stats.maker_net),
        train_taker_net_bps_mean: mean(&stats.taker_net),
        train_win_rate: win_rate(&stats.maker_net),
        train_max_date_share: max_date_share(&stats.date_counts),
        thresholds_fit_on_train: threshold_rule(fit),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn select_candidate(rows: &[CandidateRow]) -> Option<usize> {
    let strict = rows
        .iter()
        .enumerate()
        .filter(|(_, row)| row.train_fills >= MIN_TRAIN_FILLS_STRICT && row.train_fill_rate >= 0.03)
        .max_by(|(_, a), (_, b)| {
            candidate_score(a)
                .total_cmp(&candidate_score(b))
                .then_with(|| a.train_fills.cmp(&b.train_fills))
        })
        .map(|(idx, _)| idx);
    strict.or_else(|| {
        rows.iter()
            .enumerate()
            .filter(|(_, row)| row.train_fills >= MIN_TRAIN_FILLS_FALLBACK)
            .max_by(|(_, a), (_, b)| candidate_score(a).total_cmp(&candidate_score(b)))
            .map(|(idx, _)| idx)
    })
}

fn candidate_score(row: &CandidateRow) -> f64 {
    let net = row.train_maker_net_bps_mean.unwrap_or(f64::NEG_INFINITY);
    let date_penalty = row
        .train_max_date_share
        .map(|share| (share - 0.65).max(0.0) * 5.0)
        .unwrap_or(0.0);
    net - date_penalty
}

#[derive(Debug, Clone, Copy)]
enum ControlMode {
    Base,
    SideFlip,
    TimestampShiftPlus60,
    TimestampShiftMinus60,
    WrongSymbolSameTime,
    RandomizedEntryZone,
}

fn simulate_trade_rows(
    config: &V12Config,
    rows: &[&PotentialRow],
    signals: &[WatchSignal],
    spec: &StrategySpec,
    control_mode: ControlMode,
    by_symbol: &BTreeMap<String, Vec<&PotentialRow>>,
) -> Vec<TradeRow> {
    signals
        .iter()
        .filter_map(|signal| {
            let (control_rows, control_signal, side_sign) =
                control_signal(rows, signal, control_mode, by_symbol)?;
            let sim = simulate_one(
                control_rows,
                &control_signal,
                spec,
                side_sign,
                config.fee_bps,
                control_mode,
            );
            Some(trade_row_from_sim(
                config,
                &control_signal,
                spec,
                sim,
                control_rows,
            ))
        })
        .collect()
}

fn simulate_controls(
    config: &V12Config,
    by_symbol: &BTreeMap<String, Vec<&PotentialRow>>,
    rows: &[&PotentialRow],
    signals: &[WatchSignal],
    spec: &StrategySpec,
) -> Vec<NegativeControlRow> {
    [
        ControlMode::SideFlip,
        ControlMode::TimestampShiftPlus60,
        ControlMode::TimestampShiftMinus60,
        ControlMode::WrongSymbolSameTime,
        ControlMode::RandomizedEntryZone,
    ]
    .into_iter()
    .filter_map(|mode| {
        let control_trades = simulate_trade_rows(config, rows, signals, spec, mode, by_symbol);
        let stats = group_stats(&control_trades);
        let first = signals.first()?;
        Some(NegativeControlRow {
            run_tag: config.run_tag.clone(),
            control_type: control_name(mode).to_string(),
            fold: first.fold.clone(),
            symbol: first.symbol.clone(),
            bucket: first.bucket.clone(),
            strategy_id: spec.id(),
            setups: stats.setups,
            fills: stats.fills,
            fill_rate: rate(stats.fills, stats.setups),
            maker_net_bps_mean: mean(&stats.maker_net),
            taker_net_bps_mean: mean(&stats.taker_net),
            gross_bps_mean: mean(&stats.gross),
            win_rate: win_rate(&stats.maker_net),
            guardrail: GUARDRAIL.to_string(),
        })
    })
    .collect()
}

fn control_signal<'a>(
    rows: &'a [&'a PotentialRow],
    signal: &WatchSignal,
    mode: ControlMode,
    by_symbol: &'a BTreeMap<String, Vec<&'a PotentialRow>>,
) -> Option<(&'a [&'a PotentialRow], WatchSignal, i8)> {
    match mode {
        ControlMode::Base | ControlMode::RandomizedEntryZone => {
            Some((rows, signal.clone(), signal.side_sign))
        }
        ControlMode::SideFlip => Some((rows, signal.clone(), -signal.side_sign)),
        ControlMode::TimestampShiftPlus60 => {
            let target = signal.local_timestamp.saturating_add(60_000_000);
            let pos = first_row_at_or_after(rows, target)?;
            Some((
                rows,
                signal_with_pos(rows[pos], signal, pos),
                signal.side_sign,
            ))
        }
        ControlMode::TimestampShiftMinus60 => {
            let target = signal.local_timestamp.saturating_sub(60_000_000);
            let pos = first_row_at_or_after(rows, target)?;
            Some((
                rows,
                signal_with_pos(rows[pos], signal, pos),
                signal.side_sign,
            ))
        }
        ControlMode::WrongSymbolSameTime => {
            let (symbol, other_rows) = by_symbol.iter().find(|(symbol, candidate_rows)| {
                symbol.as_str() != signal.symbol && !candidate_rows.is_empty()
            })?;
            let pos = first_row_at_or_after(other_rows, signal.local_timestamp)?;
            let mut shifted = signal_with_pos(other_rows[pos], signal, pos);
            shifted.symbol = symbol.clone();
            Some((other_rows.as_slice(), shifted, signal.side_sign))
        }
    }
}

fn signal_with_pos(row: &PotentialRow, source: &WatchSignal, pos: usize) -> WatchSignal {
    WatchSignal {
        run_tag: source.run_tag.clone(),
        phase: source.phase,
        fold: source.fold.clone(),
        date: row.date.clone(),
        symbol: row.symbol.clone(),
        bucket: source.bucket.clone(),
        threshold: source.threshold,
        pos,
        timestamp: row.timestamp,
        local_timestamp: row.local_timestamp,
        side_sign: source.side_sign,
        signed_flow_shock: source.signed_flow_shock,
        abs_flow_shock: source.abs_flow_shock,
    }
}

fn simulate_one(
    rows: &[&PotentialRow],
    signal: &WatchSignal,
    spec: &StrategySpec,
    side_sign: i8,
    fee_bps: f64,
    control_mode: ControlMode,
) -> SimResult {
    let Some(structure) = pre_signal_structure(rows, signal.pos, spec.structure_window_seconds)
    else {
        return no_fill_result("no_structure");
    };
    let Some(rule) = entry_rule(rows, signal, spec, side_sign, &structure, control_mode) else {
        return no_fill_result("no_entry_rule");
    };
    let wait_until = signal
        .local_timestamp
        .saturating_add(spec.wait_seconds as u64 * 1_000_000);
    let Some(entry_pos) = find_entry(rows, signal.pos, wait_until, &rule) else {
        let mut result = no_fill_result("no_fill");
        result.entry_target_price = entry_target(&rule);
        result.pre_range_bps = Some(structure.range_bps);
        result.pre_sigma_bps = Some(structure.sigma_bps);
        return result;
    };
    let entry = rows[entry_pos];
    let Some(entry_price) = entry.mid_price else {
        return no_fill_result("entry_missing_mid");
    };
    let Some(spread_bps) = entry.spread_bps else {
        return no_fill_result("entry_missing_spread");
    };
    let Some(fill_realism_score) = entry.fill_realism_score else {
        return no_fill_result("entry_missing_fill");
    };
    let maker_cost = maker_cost_bps(fee_bps, spread_bps, fill_realism_score);
    let taker_cost = taker_cost_bps(fee_bps, spread_bps, fill_realism_score);
    let take_profit_bps = (spec.barrier.alpha_u * structure.sigma_bps)
        .max(maker_cost + spec.barrier.margin_bps)
        .max(0.5);
    let stop_loss_bps = (spec.barrier.alpha_d * structure.sigma_bps)
        .max(spec.barrier.beta_d * structure.range_bps)
        .max(0.5);
    let take_profit_price = entry_price * (1.0 + side_sign as f64 * take_profit_bps / 10_000.0);
    let stop_loss_price = entry_price * (1.0 - side_sign as f64 * stop_loss_bps / 10_000.0);
    let timeout_ts = entry
        .local_timestamp
        .saturating_add(spec.timeout_seconds as u64 * 1_000_000);
    let (exit_pos, exit_reason) = find_exit(
        rows,
        entry_pos,
        entry_price,
        side_sign,
        take_profit_bps,
        stop_loss_bps,
        timeout_ts,
    );
    let Some(exit) = rows.get(exit_pos) else {
        return no_fill_result("missing_exit");
    };
    let Some(exit_price) = exit.mid_price else {
        return no_fill_result("exit_missing_mid");
    };
    let gross_bps = side_sign as f64 * (exit_price - entry_price) / entry_price * 10_000.0;
    SimResult {
        fill_status: "filled".to_string(),
        exit_reason,
        entry_target_price: entry_target(&rule),
        entry_pos: Some(entry_pos),
        exit_pos: Some(exit_pos),
        entry_price: Some(entry_price),
        exit_price: Some(exit_price),
        take_profit_bps: Some(take_profit_bps),
        stop_loss_bps: Some(stop_loss_bps),
        take_profit_price: Some(take_profit_price),
        stop_loss_price: Some(stop_loss_price),
        gross_bps: Some(gross_bps),
        maker_cost_bps: Some(maker_cost),
        taker_cost_bps: Some(taker_cost),
        maker_net_bps: Some(gross_bps - maker_cost),
        taker_net_bps: Some(gross_bps - taker_cost),
        pre_range_bps: Some(structure.range_bps),
        pre_sigma_bps: Some(structure.sigma_bps),
        spread_bps: Some(spread_bps),
        fill_realism_score: Some(fill_realism_score),
    }
}

fn no_fill_result(reason: &str) -> SimResult {
    SimResult {
        fill_status: "no_fill".to_string(),
        exit_reason: reason.to_string(),
        entry_target_price: None,
        entry_pos: None,
        exit_pos: None,
        entry_price: None,
        exit_price: None,
        take_profit_bps: None,
        stop_loss_bps: None,
        take_profit_price: None,
        stop_loss_price: None,
        gross_bps: None,
        maker_cost_bps: None,
        taker_cost_bps: None,
        maker_net_bps: None,
        taker_net_bps: None,
        pre_range_bps: None,
        pre_sigma_bps: None,
        spread_bps: None,
        fill_realism_score: None,
    }
}

fn pre_signal_structure(
    rows: &[&PotentialRow],
    signal_pos: usize,
    window_seconds: u32,
) -> Option<Structure> {
    let signal = rows.get(signal_pos)?;
    let start_ts = signal
        .local_timestamp
        .saturating_sub(window_seconds as u64 * 1_000_000);
    let start = first_row_at_or_after(rows, start_ts).unwrap_or(0);
    let mids = rows[start..=signal_pos]
        .iter()
        .filter_map(|row| row.mid_price)
        .filter(|value| value.is_finite() && *value > 0.0)
        .collect::<Vec<_>>();
    if mids.len() < 3 {
        return None;
    }
    let high = mids.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let low = mids.iter().copied().fold(f64::INFINITY, f64::min);
    let signal_mid = signal.mid_price?;
    let range_price = (high - low).max(0.0);
    let range_bps = finite(range_price / signal_mid * 10_000.0).unwrap_or(0.0);
    let rets = mids
        .windows(2)
        .filter_map(|pair| (pair[0] > 0.0).then(|| (pair[1] - pair[0]) / pair[0] * 10_000.0))
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    let sigma_bps = if rets.is_empty() {
        range_bps.max(0.5)
    } else {
        (rets.iter().map(|value| value * value).sum::<f64>() / rets.len() as f64).sqrt()
    }
    .max(0.5);
    let spreads = rows[start..=signal_pos]
        .iter()
        .filter_map(|row| row.spread_bps)
        .collect::<Vec<_>>();
    let fills = rows[start..=signal_pos]
        .iter()
        .filter_map(|row| row.fill_realism_score)
        .collect::<Vec<_>>();
    Some(Structure {
        high,
        low,
        range_price,
        range_bps,
        sigma_bps,
        median_spread_bps: quantile(&spreads, 0.5).unwrap_or(signal.spread_bps.unwrap_or(0.0)),
        median_fill_realism: quantile(&fills, 0.5)
            .unwrap_or(signal.fill_realism_score.unwrap_or(0.5)),
    })
}

fn entry_rule(
    rows: &[&PotentialRow],
    signal: &WatchSignal,
    spec: &StrategySpec,
    side_sign: i8,
    structure: &Structure,
    control_mode: ControlMode,
) -> Option<EntryRule> {
    if matches!(control_mode, ControlMode::RandomizedEntryZone) {
        let lambda = 0.2 + deterministic_unit(signal.local_timestamp, &signal.symbol) * 0.6;
        let target = if side_sign >= 0 {
            structure.low + lambda * structure.range_price
        } else {
            structure.high - lambda * structure.range_price
        };
        let condition = if side_sign >= 0 {
            EntryCondition::AtOrBelow
        } else {
            EntryCondition::AtOrAbove
        };
        return Some(EntryRule::RandomizedPrice { target, condition });
    }

    match spec.entry.mode {
        EntryMode::Pullback => {
            let lambda = spec.entry.lambda?;
            let target = if side_sign >= 0 {
                structure.high - lambda * structure.range_price
            } else {
                structure.low + lambda * structure.range_price
            };
            let condition = if side_sign >= 0 {
                EntryCondition::AtOrBelow
            } else {
                EntryCondition::AtOrAbove
            };
            Some(EntryRule::Price { target, condition })
        }
        EntryMode::BreakoutConfirm => {
            let delta_bps = (0.25 * structure.sigma_bps).max(0.25);
            let target = if side_sign >= 0 {
                structure.high * (1.0 + delta_bps / 10_000.0)
            } else {
                structure.low * (1.0 - delta_bps / 10_000.0)
            };
            let condition = if side_sign >= 0 {
                EntryCondition::AtOrAbove
            } else {
                EntryCondition::AtOrBelow
            };
            Some(EntryRule::Price { target, condition })
        }
        EntryMode::RangeMidRetest => {
            let target = (structure.high + structure.low) / 2.0;
            let condition = if side_sign >= 0 {
                EntryCondition::AtOrBelow
            } else {
                EntryCondition::AtOrAbove
            };
            Some(EntryRule::Price { target, condition })
        }
        EntryMode::LiquidityRecovery => {
            let signal_row = rows.get(signal.pos)?;
            let signal_spread = signal_row.spread_bps?;
            let signal_fill = signal_row.fill_realism_score?;
            Some(EntryRule::LiquidityRecovery {
                max_spread_bps: signal_spread.min(structure.median_spread_bps) * 0.98,
                min_fill_realism: (signal_fill.max(structure.median_fill_realism) + 0.015)
                    .min(0.98),
            })
        }
    }
}

fn find_entry(
    rows: &[&PotentialRow],
    signal_pos: usize,
    wait_until: u64,
    rule: &EntryRule,
) -> Option<usize> {
    let mut pos = signal_pos.saturating_add(1);
    while pos < rows.len() {
        let row = rows[pos];
        if row.local_timestamp > wait_until {
            return None;
        }
        let mid = row.mid_price?;
        let spread_ok = row
            .spread_bps
            .is_some_and(|value| value.is_finite() && value >= 0.0);
        let fill_ok = row
            .fill_realism_score
            .is_some_and(|value| value.is_finite());
        if !spread_ok || !fill_ok {
            pos += 1;
            continue;
        }
        let passed = match rule {
            EntryRule::Price { target, condition }
            | EntryRule::RandomizedPrice { target, condition } => match condition {
                EntryCondition::AtOrBelow => mid <= *target,
                EntryCondition::AtOrAbove => mid >= *target,
            },
            EntryRule::LiquidityRecovery {
                max_spread_bps,
                min_fill_realism,
            } => {
                row.spread_bps.unwrap_or(f64::INFINITY) <= *max_spread_bps
                    && row.fill_realism_score.unwrap_or(0.0) >= *min_fill_realism
            }
        };
        if passed {
            return Some(pos);
        }
        pos += 1;
    }
    None
}

fn find_exit(
    rows: &[&PotentialRow],
    entry_pos: usize,
    entry_price: f64,
    side_sign: i8,
    take_profit_bps: f64,
    stop_loss_bps: f64,
    timeout_ts: u64,
) -> (usize, String) {
    let mut pos = entry_pos.saturating_add(1);
    let mut last_seen = entry_pos;
    while pos < rows.len() {
        let row = rows[pos];
        if let Some(mid) = row.mid_price {
            last_seen = pos;
            let side_ret = side_sign as f64 * (mid - entry_price) / entry_price * 10_000.0;
            if side_ret <= -stop_loss_bps {
                return (pos, "stop_loss".to_string());
            }
            if side_ret >= take_profit_bps {
                return (pos, "take_profit".to_string());
            }
        }
        if row.local_timestamp >= timeout_ts {
            return (last_seen, "timeout".to_string());
        }
        pos += 1;
    }
    (last_seen, "data_end".to_string())
}

fn trade_row_from_sim(
    config: &V12Config,
    signal: &WatchSignal,
    spec: &StrategySpec,
    sim: SimResult,
    rows: &[&PotentialRow],
) -> TradeRow {
    let entry_local_timestamp = sim
        .entry_pos
        .and_then(|pos| rows.get(pos).map(|row| row.local_timestamp));
    let exit_local_timestamp = sim
        .exit_pos
        .and_then(|pos| rows.get(pos).map(|row| row.local_timestamp));
    TradeRow {
        run_tag: config.run_tag.clone(),
        fold: signal.fold.clone(),
        phase: match signal.phase {
            Phase::Train => "train".to_string(),
            Phase::Validation => "validation".to_string(),
        },
        date: signal.date.clone(),
        symbol: signal.symbol.clone(),
        bucket: signal.bucket.clone(),
        strategy_id: spec.id(),
        source_signal: spec.source_signal.clone(),
        entry_mode: spec.entry.name.to_string(),
        barrier_profile: spec.barrier.name.to_string(),
        structure_window_seconds: spec.structure_window_seconds,
        wait_seconds: spec.wait_seconds,
        timeout_seconds: spec.timeout_seconds,
        signal_timestamp: signal.timestamp,
        signal_local_timestamp: signal.local_timestamp,
        side: side_name(signal.side_sign).to_string(),
        fill_status: sim.fill_status,
        exit_reason: sim.exit_reason,
        signal_mid: rows.get(signal.pos).and_then(|row| row.mid_price),
        entry_target_price: sim.entry_target_price,
        entry_local_timestamp,
        exit_local_timestamp,
        entry_price: sim.entry_price,
        exit_price: sim.exit_price,
        take_profit_bps: sim.take_profit_bps,
        stop_loss_bps: sim.stop_loss_bps,
        take_profit_price: sim.take_profit_price,
        stop_loss_price: sim.stop_loss_price,
        gross_bps: sim.gross_bps,
        fee_bps: config.fee_bps,
        maker_cost_bps: sim.maker_cost_bps,
        taker_cost_bps: sim.taker_cost_bps,
        maker_net_bps: sim.maker_net_bps,
        taker_net_bps: sim.taker_net_bps,
        pre_range_bps: sim.pre_range_bps,
        pre_sigma_bps: sim.pre_sigma_bps,
        spread_bps: sim.spread_bps,
        fill_realism_score: sim.fill_realism_score,
        guardrail: GUARDRAIL.to_string(),
    }
}

fn summarize_trades(trades: &[TradeRow]) -> Vec<SummaryRow> {
    let mut groups: BTreeMap<(String, String, String, String), Vec<&TradeRow>> = BTreeMap::new();
    for trade in trades {
        groups
            .entry((
                trade.fold.clone(),
                trade.symbol.clone(),
                trade.bucket.clone(),
                trade.strategy_id.clone(),
            ))
            .or_default()
            .push(trade);
    }
    groups
        .into_iter()
        .map(|((fold, symbol, bucket, strategy_id), rows)| {
            let stats = group_stats_refs(&rows);
            let first = rows[0];
            SummaryRow {
                run_tag: first.run_tag.clone(),
                fold,
                symbol,
                bucket,
                strategy_id,
                source_signal: first.source_signal.clone(),
                entry_mode: first.entry_mode.clone(),
                barrier_profile: first.barrier_profile.clone(),
                structure_window_seconds: first.structure_window_seconds,
                wait_seconds: first.wait_seconds,
                timeout_seconds: first.timeout_seconds,
                setups: stats.setups,
                fills: stats.fills,
                no_fills: stats.no_fills,
                fill_rate: rate(stats.fills, stats.setups),
                maker_net_bps_mean: mean(&stats.maker_net),
                taker_net_bps_mean: mean(&stats.taker_net),
                gross_bps_mean: mean(&stats.gross),
                maker_cost_bps_mean: mean(&stats.maker_cost),
                win_rate: win_rate(&stats.maker_net),
                take_profit_rate: Some(rate(stats.take_profit, stats.fills)),
                stop_loss_rate: Some(rate(stats.stop_loss, stats.fills)),
                timeout_rate: Some(rate(stats.timeout, stats.fills)),
                max_date_share: max_date_share(&stats.date_counts),
                control_abs_ge_base_abs_rate: None,
                best_control_maker_net_bps_mean: None,
                control_separated: false,
                guardrail: GUARDRAIL.to_string(),
            }
        })
        .collect()
}

fn summarize_controls(
    controls: &[NegativeControlRow],
) -> BTreeMap<(String, String, String, String), Vec<NegativeControlRow>> {
    let mut grouped = BTreeMap::new();
    for row in controls {
        grouped
            .entry((
                row.fold.clone(),
                row.symbol.clone(),
                row.bucket.clone(),
                row.strategy_id.clone(),
            ))
            .or_insert_with(Vec::new)
            .push(row.clone());
    }
    grouped
}

fn attach_control_metrics(summary: &mut SummaryRow, controls: &[NegativeControlRow]) {
    let Some(base) = summary.maker_net_bps_mean else {
        return;
    };
    let means = controls
        .iter()
        .filter_map(|row| row.maker_net_bps_mean)
        .collect::<Vec<_>>();
    if means.is_empty() {
        return;
    }
    let count_abs_ge = means
        .iter()
        .filter(|value| value.abs() >= base.abs())
        .count();
    let rate_abs_ge = rate(count_abs_ge, means.len());
    let best_control = means.iter().copied().max_by(f64::total_cmp);
    summary.control_abs_ge_base_abs_rate = Some(rate_abs_ge);
    summary.best_control_maker_net_bps_mean = best_control;
    summary.control_separated = base > 0.0
        && means.iter().all(|control| base > *control)
        && rate_abs_ge <= CONTROL_ABS_GE_BASE_LIMIT;
}

fn summary_key(row: &SummaryRow) -> (String, String, String, String) {
    (
        row.fold.clone(),
        row.symbol.clone(),
        row.bucket.clone(),
        row.strategy_id.clone(),
    )
}

fn build_failure_report(
    run_tag: &str,
    audit: &InputAudit,
    summaries: &[SummaryRow],
) -> FailureReportRow {
    if !audit.blockers.is_empty() {
        return FailureReportRow {
            run_tag: run_tag.to_string(),
            primary_status: "data_quality_blocked".to_string(),
            candidate_key: "none".to_string(),
            setups: 0,
            fills: 0,
            fill_rate: 0.0,
            maker_net_bps_mean: None,
            best_control_maker_net_bps_mean: None,
            control_abs_ge_base_abs_rate: None,
            max_date_share: None,
            evidence: format!("input blockers={}", audit.blockers.len()),
            guardrail: GUARDRAIL.to_string(),
        };
    }

    let best = summaries.iter().max_by(|a, b| {
        a.maker_net_bps_mean
            .unwrap_or(f64::NEG_INFINITY)
            .total_cmp(&b.maker_net_bps_mean.unwrap_or(f64::NEG_INFINITY))
    });
    let Some(best) = best else {
        return failure_row_empty(run_tag, "insufficient_fills", "no summary rows generated");
    };
    let status = if best.fills < MIN_VALID_FILLS {
        "insufficient_fills"
    } else if best.maker_net_bps_mean.unwrap_or(f64::NEG_INFINITY) <= 0.0 {
        "gross_edge_too_thin"
    } else if !best.control_separated {
        "controls_not_separated"
    } else if best.max_date_share.unwrap_or(1.0) > MAX_DATE_SHARE {
        "single_date_dependent"
    } else {
        "pending_entry_survives_2bps"
    };
    FailureReportRow {
        run_tag: run_tag.to_string(),
        primary_status: status.to_string(),
        candidate_key: format!(
            "{}|{}|{}|{}",
            best.fold, best.symbol, best.bucket, best.strategy_id
        ),
        setups: best.setups,
        fills: best.fills,
        fill_rate: best.fill_rate,
        maker_net_bps_mean: best.maker_net_bps_mean,
        best_control_maker_net_bps_mean: best.best_control_maker_net_bps_mean,
        control_abs_ge_base_abs_rate: best.control_abs_ge_base_abs_rate,
        max_date_share: best.max_date_share,
        evidence: format!(
            "best validation candidate maker_net={} fills={} fill_rate={:.4}",
            fmt_opt(best.maker_net_bps_mean, 6),
            best.fills,
            best.fill_rate
        ),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn failure_row_empty(run_tag: &str, status: &str, evidence: &str) -> FailureReportRow {
    FailureReportRow {
        run_tag: run_tag.to_string(),
        primary_status: status.to_string(),
        candidate_key: "none".to_string(),
        setups: 0,
        fills: 0,
        fill_rate: 0.0,
        maker_net_bps_mean: None,
        best_control_maker_net_bps_mean: None,
        control_abs_ge_base_abs_rate: None,
        max_date_share: None,
        evidence: evidence.to_string(),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn write_report(
    config: &V12Config,
    paths: &Paths,
    audit: &InputAudit,
    failure: &FailureReportRow,
    candidates: &[CandidateRow],
    trades: &[TradeRow],
    summaries: &[SummaryRow],
    controls: &[NegativeControlRow],
) -> Result<()> {
    ensure_parent_dir(&paths.report_md)?;
    let best = summaries.iter().max_by(|a, b| {
        a.maker_net_bps_mean
            .unwrap_or(f64::NEG_INFINITY)
            .total_cmp(&b.maker_net_bps_mean.unwrap_or(f64::NEG_INFINITY))
    });
    let selected_count = candidates.iter().filter(|row| row.selected).count();
    let mut lines = Vec::new();
    lines.push("# BONK V12 Pending Entry Adaptive TP/SL".to_string());
    lines.push(String::new());
    lines.push(format!("Status: {}.", utc_now_string()));
    lines.push(format!("Run tag: `{}`.", config.run_tag));
    lines.push(format!("Fee bps: `{:.4}`.", config.fee_bps));
    lines.push(String::new());
    lines.push(GUARDRAIL.to_string());
    lines.push(String::new());
    lines.push("## Primary Status".to_string());
    lines.push(String::new());
    lines.push(format!("`{}`", failure.primary_status));
    lines.push(String::new());
    lines.push(failure.evidence.clone());
    lines.push(String::new());
    lines.push("## What Changed Versus V11".to_string());
    lines.push(String::new());
    lines.push("- V11 entered immediately and exited after a fixed horizon.".to_string());
    lines.push("- V12 treats trade-flow shock as a watch state, waits for a valid entry zone, and exits by first hit of adaptive take-profit, stop-loss, or timeout.".to_string());
    lines.push("- No-fill setups are counted rather than forced into bad trades.".to_string());
    lines.push(String::new());
    lines.push("## Output Counts".to_string());
    lines.push(String::new());
    lines.push(format!("- potential rows: `{}`", audit.potential_rows));
    lines.push(format!("- candidate grid rows: `{}`", candidates.len()));
    lines.push(format!("- selected frozen configs: `{}`", selected_count));
    lines.push(format!("- validation setup/trade rows: `{}`", trades.len()));
    lines.push(format!("- summary rows: `{}`", summaries.len()));
    lines.push(format!("- negative-control rows: `{}`", controls.len()));
    lines.push(String::new());
    if let Some(best) = best {
        lines.push("## Best Validation Candidate".to_string());
        lines.push(String::new());
        lines.push(format!(
            "- `{}` `{}` `{}` `{}`",
            best.fold, best.symbol, best.bucket, best.strategy_id
        ));
        lines.push(format!(
            "- setups=`{}`, fills=`{}`, fill_rate=`{:.4}`",
            best.setups, best.fills, best.fill_rate
        ));
        lines.push(format!(
            "- maker_net_bps_mean=`{}`, win_rate=`{}`, max_date_share=`{}`",
            fmt_opt(best.maker_net_bps_mean, 6),
            fmt_opt(best.win_rate, 4),
            fmt_opt(best.max_date_share, 4)
        ));
        lines.push(format!(
            "- control_abs_ge_base_abs_rate=`{}`, control_separated=`{}`",
            fmt_opt(best.control_abs_ge_base_abs_rate, 4),
            best.control_separated
        ));
        lines.push(String::new());
    }
    lines.push("## Artifacts".to_string());
    lines.push(String::new());
    lines.push(format!("- `{}`", path_string(&paths.candidates_csv)));
    lines.push(format!("- `{}`", path_string(&paths.trades_csv)));
    lines.push(format!("- `{}`", path_string(&paths.summary_csv)));
    lines.push(format!("- `{}`", path_string(&paths.negative_controls_csv)));
    lines.push(format!("- `{}`", path_string(&paths.failure_report_csv)));
    lines.push(String::new());
    lines.push("## Interpretation Boundary".to_string());
    lines.push(String::new());
    lines.push("This is still a research diagnostic. A positive row would mean the patient translation is worth validating, not that the strategy is deployable.".to_string());
    lines.push(String::new());
    fs::write(&paths.report_md, lines.join("\n"))
        .with_context(|| format!("failed to write {}", paths.report_md.display()))
}

fn group_stats(trades: &[TradeRow]) -> GroupStats {
    group_stats_refs(&trades.iter().collect::<Vec<_>>())
}

fn group_stats_refs(trades: &[&TradeRow]) -> GroupStats {
    let mut stats = GroupStats {
        setups: trades.len(),
        fills: 0,
        no_fills: 0,
        maker_net: Vec::new(),
        taker_net: Vec::new(),
        gross: Vec::new(),
        maker_cost: Vec::new(),
        wins: 0,
        take_profit: 0,
        stop_loss: 0,
        timeout: 0,
        date_counts: BTreeMap::new(),
    };
    for trade in trades {
        if trade.fill_status == "filled" {
            stats.fills += 1;
            *stats.date_counts.entry(trade.date.clone()).or_insert(0) += 1;
            if let Some(value) = trade.maker_net_bps {
                if value > 0.0 {
                    stats.wins += 1;
                }
                stats.maker_net.push(value);
            }
            if let Some(value) = trade.taker_net_bps {
                stats.taker_net.push(value);
            }
            if let Some(value) = trade.gross_bps {
                stats.gross.push(value);
            }
            if let Some(value) = trade.maker_cost_bps {
                stats.maker_cost.push(value);
            }
            match trade.exit_reason.as_str() {
                "take_profit" => stats.take_profit += 1,
                "stop_loss" => stats.stop_loss += 1,
                "timeout" => stats.timeout += 1,
                _ => {}
            }
        } else {
            stats.no_fills += 1;
        }
    }
    stats
}

fn maker_cost_bps(fee_bps: f64, spread_bps: f64, fill_realism_score: f64) -> f64 {
    fee_bps + 0.25 * spread_bps + (1.0 - fill_realism_score) * spread_bps
}

fn taker_cost_bps(fee_bps: f64, spread_bps: f64, fill_realism_score: f64) -> f64 {
    fee_bps + spread_bps + 0.50 * (1.0 - fill_realism_score) * spread_bps
}

fn first_row_at_or_after(rows: &[&PotentialRow], target: u64) -> Option<usize> {
    let mut lo = 0usize;
    let mut hi = rows.len();
    while lo < hi {
        let mid = (lo + hi) / 2;
        if rows[mid].local_timestamp < target {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    (lo < rows.len()).then_some(lo)
}

fn entry_target(rule: &EntryRule) -> Option<f64> {
    match rule {
        EntryRule::Price { target, .. } | EntryRule::RandomizedPrice { target, .. } => {
            Some(*target)
        }
        EntryRule::LiquidityRecovery { .. } => None,
    }
}

fn bucket_rank(bucket: &str) -> u8 {
    match bucket {
        "shock_q99" => 0,
        "shock_q95" => 1,
        _ => 2,
    }
}

fn side_name(side_sign: i8) -> &'static str {
    if side_sign >= 0 { "long" } else { "short" }
}

fn threshold_rule(fit: &ThresholdSet) -> String {
    format!(
        "train_only;purge_us={};fold={};train_rows={};valid_rows={};shock_q95={:.6};shock_q99={:.6}",
        V10_PURGE_US, fit.fold.name, fit.train_rows, fit.valid_rows, fit.shock_q95, fit.shock_q99
    )
}

fn control_name(mode: ControlMode) -> &'static str {
    match mode {
        ControlMode::Base => "base",
        ControlMode::SideFlip => "side_flip",
        ControlMode::TimestampShiftPlus60 => "timestamp_shift_plus_60s",
        ControlMode::TimestampShiftMinus60 => "timestamp_shift_minus_60s",
        ControlMode::WrongSymbolSameTime => "wrong_symbol_same_time",
        ControlMode::RandomizedEntryZone => "randomized_entry_zone",
    }
}

fn max_date_share(counts: &BTreeMap<String, usize>) -> Option<f64> {
    let total = counts.values().sum::<usize>();
    if total == 0 {
        None
    } else {
        counts.values().max().map(|max| *max as f64 / total as f64)
    }
}

fn deterministic_unit(seed: u64, symbol: &str) -> f64 {
    let mut hash = seed ^ 0x9E37_79B9_7F4A_7C15;
    for byte in symbol.as_bytes() {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0xBF58_476D_1CE4_E5B9);
        hash ^= hash >> 27;
    }
    (hash % 10_000) as f64 / 10_000.0
}

fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn mean(values: &[f64]) -> Option<f64> {
    let values = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if values.is_empty() {
        None
    } else {
        Some(values.iter().sum::<f64>() / values.len() as f64)
    }
}

fn quantile(values: &[f64], q: f64) -> Option<f64> {
    let mut values = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let pos = q.clamp(0.0, 1.0) * (values.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    if lo == hi {
        Some(values[lo])
    } else {
        let weight = pos - lo as f64;
        Some(values[lo] * (1.0 - weight) + values[hi] * weight)
    }
}

fn win_rate(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        Some(rate(
            values
                .iter()
                .filter(|value| value.is_finite() && **value > 0.0)
                .count(),
            values.len(),
        ))
    }
}

fn rate(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64
    }
}

fn fmt_opt(value: Option<f64>, digits: usize) -> String {
    value
        .map(|value| format!("{value:.digits$}"))
        .unwrap_or_else(|| "NA".to_string())
}

fn de_opt_f64<'de, D>(deserializer: D) -> std::result::Result<Option<f64>, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = Option::<String>::deserialize(deserializer)?;
    let Some(raw) = raw else {
        return Ok(None);
    };
    let raw = raw.trim();
    if raw.is_empty() {
        return Ok(None);
    }
    raw.parse::<f64>().map(finite).map_err(de::Error::custom)
}

fn de_f64_or_zero<'de, D>(deserializer: D) -> std::result::Result<f64, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = Option::<String>::deserialize(deserializer)?;
    let Some(raw) = raw else {
        return Ok(0.0);
    };
    let raw = raw.trim();
    if raw.is_empty() {
        return Ok(0.0);
    }
    raw.parse::<f64>().map_err(de::Error::custom)
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
    replace_with_temp(&temp, path)
}

fn temp_path_for(path: &Path) -> PathBuf {
    let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let stamp = Utc::now().timestamp_micros();
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("bonk_v12_output");
    std::env::temp_dir().join(format!("{file_name}.{pid}.{stamp}.{counter}.tmp"))
}

fn backup_path_for(path: &Path) -> PathBuf {
    let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let stamp = Utc::now().timestamp_micros();
    path.with_extension(format!(
        "{}.{}.{}.{}.bak",
        path.extension()
            .and_then(|value| value.to_str())
            .unwrap_or("out"),
        pid,
        stamp,
        counter
    ))
}

fn replace_with_temp(temp: &Path, path: &Path) -> Result<()> {
    match rename_with_retries(temp, path) {
        Ok(()) => Ok(()),
        Err(first_err) => {
            if !path.exists() {
                return Err(first_err).with_context(|| {
                    format!("failed to rename {} -> {}", temp.display(), path.display())
                });
            }
            let backup = backup_path_for(path);
            rename_with_retries(path, &backup).with_context(|| {
                format!(
                    "failed to move existing {} -> {} after initial temp rename failed: {}",
                    path.display(),
                    backup.display(),
                    first_err
                )
            })?;
            match rename_with_retries(temp, path) {
                Ok(()) => {
                    let _ = fs::remove_file(&backup);
                    Ok(())
                }
                Err(second_err) => {
                    if let Err(restore_err) = rename_with_retries(&backup, path) {
                        bail!(
                            "failed to rename {} -> {} after moving existing target to {}; initial rename error: {}; replacement error: {}; restore error: {}",
                            temp.display(),
                            path.display(),
                            backup.display(),
                            first_err,
                            second_err,
                            restore_err
                        );
                    }
                    Err(second_err).with_context(|| {
                        format!(
                            "failed to rename {} -> {} after moving existing target to {}; restored original target; initial rename error: {}",
                            temp.display(),
                            path.display(),
                            backup.display(),
                            first_err
                        )
                    })
                }
            }
        }
    }
}

fn rename_with_retries(from: &Path, to: &Path) -> std::io::Result<()> {
    let mut last_err = None;
    for attempt in 0..=FILE_REPLACE_RETRIES {
        match fs::rename(from, to) {
            Ok(()) => return Ok(()),
            Err(err) => {
                last_err = Some(err);
                if attempt < FILE_REPLACE_RETRIES {
                    std::thread::sleep(std::time::Duration::from_millis(FILE_REPLACE_RETRY_MS));
                }
            }
        }
    }
    Err(last_err.expect("rename attempted at least once"))
}

fn utc_now_string() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(ts: u64, mid: f64) -> PotentialRow {
        PotentialRow {
            run_tag: "test".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            timestamp: ts,
            local_timestamp: ts,
            mid_price: Some(mid),
            spread_bps: Some(2.0),
            trade_buy_amount: 100.0,
            trade_sell_amount: 0.0,
            trade_notional_quote: 100.0,
            trade_flow_imbalance: Some(1.0),
            fill_realism_score: Some(0.5),
        }
    }

    fn signal(pos: usize, ts: u64) -> WatchSignal {
        WatchSignal {
            run_tag: "test".to_string(),
            phase: Phase::Validation,
            fold: "fold1".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            bucket: "shock_q95".to_string(),
            threshold: 1.0,
            pos,
            timestamp: ts,
            local_timestamp: ts,
            side_sign: 1,
            signed_flow_shock: 2.0,
            abs_flow_shock: 2.0,
        }
    }

    fn base_spec(entry: EntrySpec) -> StrategySpec {
        StrategySpec {
            source_signal: "test".to_string(),
            entry,
            barrier: BARRIER_SPECS[0],
            structure_window_seconds: 60,
            wait_seconds: 60,
            timeout_seconds: 60,
        }
    }

    #[test]
    fn entry_zone_uses_only_pre_signal_structure() {
        let rows = vec![
            row(0, 100.0),
            row(10_000_000, 101.0),
            row(20_000_000, 102.0),
            row(30_000_000, 100.0),
            row(40_000_000, 150.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();
        let sig = signal(2, 20_000_000);
        let structure = pre_signal_structure(&refs, sig.pos, 60).unwrap();
        assert_eq!(structure.high, 102.0);
        assert_eq!(structure.low, 100.0);
    }

    #[test]
    fn no_fill_setup_is_counted() {
        let rows = vec![
            row(0, 100.0),
            row(10_000_000, 101.0),
            row(20_000_000, 102.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();
        let sig = signal(1, 10_000_000);
        let spec = base_spec(EntrySpec {
            mode: EntryMode::Pullback,
            name: "pullback_500",
            lambda: Some(0.5),
        });
        let trade = simulate_trade_rows(
            &V12Config::default(),
            &refs,
            &[sig],
            &spec,
            ControlMode::Base,
            &BTreeMap::new(),
        );
        assert_eq!(trade.len(), 1);
        assert_eq!(trade[0].fill_status, "no_fill");
    }

    #[test]
    fn first_hit_take_profit_precedes_later_stop_loss() {
        let rows = vec![row(0, 100.0), row(1, 100.0), row(2, 101.0), row(3, 98.0)];
        let refs = rows.iter().collect::<Vec<_>>();
        let (exit_pos, reason) = find_exit(&refs, 1, 100.0, 1, 50.0, 50.0, 10);
        assert_eq!(exit_pos, 2);
        assert_eq!(reason, "take_profit");
    }

    #[test]
    fn adaptive_take_profit_respects_cost_floor() {
        let rows = vec![row(0, 100.0), row(1, 100.0), row(2, 100.0), row(3, 101.0)];
        let refs = rows.iter().collect::<Vec<_>>();
        let sig = signal(2, 2);
        let spec = base_spec(ENTRY_SPECS[3]);
        let result = simulate_one(&refs, &sig, &spec, 1, 2.0, ControlMode::Base);
        let tp = result.take_profit_bps.unwrap();
        let cost = result.maker_cost_bps.unwrap();
        assert!(tp >= cost + spec.barrier.margin_bps - 1e-9);
    }

    #[test]
    fn selected_grid_is_marked_from_train_metrics() {
        fn candidate(id: &str, net: f64) -> CandidateRow {
            CandidateRow {
                run_tag: "test".to_string(),
                fold: "fold1".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                bucket: "shock_q95".to_string(),
                selected: false,
                strategy_id: id.to_string(),
                source_signal: "test".to_string(),
                entry_mode: id.to_string(),
                structure_window_seconds: 60,
                wait_seconds: 300,
                timeout_seconds: 600,
                barrier_profile: id.to_string(),
                alpha_u: 1.0,
                alpha_d: 1.0,
                beta_d: 0.5,
                margin_bps: 1.0,
                train_setups: 100,
                train_fills: 30,
                train_fill_rate: 0.3,
                train_maker_net_bps_mean: Some(net),
                train_taker_net_bps_mean: Some(0.0),
                train_win_rate: Some(0.5),
                train_max_date_share: Some(0.5),
                thresholds_fit_on_train: "train_only".to_string(),
                guardrail: GUARDRAIL.to_string(),
            }
        }
        let rows = vec![candidate("a", 1.0), candidate("b", -1.0)];
        assert_eq!(select_candidate(&rows), Some(0));
    }
}

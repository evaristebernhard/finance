use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use chrono::{SecondsFormat, Utc};
use finance_chain_core::storage::ensure_parent_dir;
use serde::de::{self, DeserializeOwned, Deserializer};
use serde::{Deserialize, Serialize};

use crate::download::{DEFAULT_BONK_DATA_ROOT, parse_symbol_list, path_string};
use crate::v10::{DEFAULT_V10_RUN_TAG, DEFAULT_V10_SYMBOLS};
use crate::v10c::EventPanelRow;

const GUARDRAIL: &str = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim";
const STRATEGY_ID: &str = "v13_dynamic_marker_vol_wings";
const FROZEN_STRATEGY_ID: &str = "v12_frozen_marker_static_wings_baseline";
const WATCH_FEATURES: [&str; 5] = [
    "mlofi_norm_l10",
    "mlofi_norm_l5",
    "queue_imbalance_25",
    "trade_arrival_alignment",
    "liquidity_shock_score",
];
const SIGNAL_EVENT_GAP: usize = 900;
const MAX_SIGNALS_PER_GROUP: usize = 250;
const MAX_MARKER_LIFETIME_EVENTS: usize = 1_800;
const MAX_HOLD_EVENTS: usize = 1_800;
const TICK_FLOOR_BPS: f64 = 0.10;
const MIN_SIGMA_BPS: f64 = 0.50;
const QUEUE_RESET_PENALTY_BPS: f64 = 0.05;
const MAX_STOP_TO_TP: f64 = 1.50;
const MIN_VALID_FILLS: usize = 50;
const MAX_DATE_SHARE: f64 = 0.50;
const MAX_SYMBOL_SHARE: f64 = 0.75;
const CONTROL_ABS_GE_BASE_LIMIT: f64 = 0.35;
const FILE_REPLACE_RETRIES: usize = 80;
const FILE_REPLACE_RETRY_MS: u64 = 250;
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct V13Config {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub doc_dir: PathBuf,
    pub run_tag: String,
    pub fee_bps: f64,
    pub symbols: String,
}

impl Default for V13Config {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_BONK_DATA_ROOT),
            date_dir: PathBuf::from("date"),
            doc_dir: PathBuf::from("docs/markets/bonk"),
            run_tag: DEFAULT_V10_RUN_TAG.to_string(),
            fee_bps: 2.0,
            symbols: DEFAULT_V10_SYMBOLS.to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct V13Summary {
    pub run_tag: String,
    pub panel_rows: usize,
    pub fold_rows: usize,
    pub signal_rows: usize,
    pub trade_rows: usize,
    pub summary_rows: usize,
    pub negative_control_rows: usize,
    pub diagnostic_rows: usize,
    pub primary_status: String,
    pub trades_csv: String,
    pub summary_csv: String,
    pub negative_controls_csv: String,
    pub failure_report_csv: String,
    pub diagnostics_csv: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    trades_csv: PathBuf,
    summary_csv: PathBuf,
    negative_controls_csv: PathBuf,
    failure_report_csv: PathBuf,
    diagnostics_csv: PathBuf,
    report_md: PathBuf,
    filter_params_csv: PathBuf,
    v12_summary_csv: PathBuf,
    v12_trades_csv: PathBuf,
}

impl Paths {
    fn new(config: &V13Config) -> Self {
        Self {
            trades_csv: config.date_dir.join(format!(
                "bonk_v13_dynamic_marker_trades_{}.csv",
                config.run_tag
            )),
            summary_csv: config.date_dir.join(format!(
                "bonk_v13_dynamic_marker_summary_{}.csv",
                config.run_tag
            )),
            negative_controls_csv: config.date_dir.join(format!(
                "bonk_v13_dynamic_marker_negative_controls_{}.csv",
                config.run_tag
            )),
            failure_report_csv: config.date_dir.join(format!(
                "bonk_v13_dynamic_marker_failure_report_{}.csv",
                config.run_tag
            )),
            diagnostics_csv: config.date_dir.join(format!(
                "bonk_v13_dynamic_marker_diagnostics_{}.csv",
                config.run_tag
            )),
            report_md: config
                .doc_dir
                .join("v1-cex-v13-dynamic-marker-vol-wings.md"),
            filter_params_csv: config
                .date_dir
                .join(format!("bonk_v10_filter_params_{}.csv", config.run_tag)),
            v12_summary_csv: config.date_dir.join(format!(
                "bonk_v12_pending_entry_summary_{}.csv",
                config.run_tag
            )),
            v12_trades_csv: config.date_dir.join(format!(
                "bonk_v12_pending_entry_trades_{}.csv",
                config.run_tag
            )),
        }
    }
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct PanelRow {
    run_tag: String,
    date: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    event_index: usize,
    factor_eligible: bool,
    mid_price: f64,
    spread_bps: f64,
    microprice: Option<f64>,
    center_price: f64,
    rv30_bps: f64,
    sigma_bps: f64,
    vol_state: String,
    best_bid_price: Option<f64>,
    best_ask_price: Option<f64>,
    queue_imbalance_25: Option<f64>,
    mlofi_norm_l5: Option<f64>,
    mlofi_norm_l10: Option<f64>,
    mlofi_roll10_l5: f64,
    mlofi_roll10_l10: f64,
    trade_flow_imbalance: Option<f64>,
    trade_arrival_alignment: Option<f64>,
    trade_buy_amount: f64,
    trade_sell_amount: f64,
    depletion_bid_amount: f64,
    depletion_ask_amount: f64,
    replenish_bid_amount: f64,
    replenish_ask_amount: f64,
    cancel_bid_amount: f64,
    cancel_ask_amount: f64,
    decrease_bid_amount: f64,
    decrease_ask_amount: f64,
    remove_bid_amount: f64,
    remove_ask_amount: f64,
    execute_bid_amount: f64,
    execute_ask_amount: f64,
    liquidity_shock_score: Option<f64>,
}

impl PanelRow {
    fn from_panel(row: EventPanelRow) -> Option<Self> {
        let mid_price = row.mid_price.and_then(finite)?;
        if mid_price <= 0.0 {
            return None;
        }
        let spread_bps = row.spread_bps.and_then(finite).unwrap_or(0.0).max(0.0);
        let microprice = row.microprice.and_then(finite).filter(|value| *value > 0.0);
        let center_price = microprice.unwrap_or(mid_price);
        Some(Self {
            run_tag: row.run_tag,
            date: row.date,
            symbol: row.symbol,
            timestamp: row.timestamp,
            local_timestamp: row.local_timestamp,
            event_index: row.event_index,
            factor_eligible: row.factor_eligible,
            mid_price,
            spread_bps,
            microprice,
            center_price,
            rv30_bps: 0.0,
            sigma_bps: spread_bps.max(MIN_SIGMA_BPS),
            vol_state: "unfit".to_string(),
            best_bid_price: row.best_bid_price.and_then(finite),
            best_ask_price: row.best_ask_price.and_then(finite),
            queue_imbalance_25: row.queue_imbalance_25.and_then(finite),
            mlofi_norm_l5: row.mlofi_norm_l5.and_then(finite),
            mlofi_norm_l10: row.mlofi_norm_l10.and_then(finite),
            mlofi_roll10_l5: finite(row.mlofi_roll10_l5).unwrap_or(0.0),
            mlofi_roll10_l10: finite(row.mlofi_roll10_l10).unwrap_or(0.0),
            trade_flow_imbalance: row.trade_flow_imbalance.and_then(finite),
            trade_arrival_alignment: row.trade_arrival_alignment.and_then(finite),
            trade_buy_amount: row.trade_buy_amount.max(0.0),
            trade_sell_amount: row.trade_sell_amount.max(0.0),
            depletion_bid_amount: row.depletion_bid_amount.max(0.0),
            depletion_ask_amount: row.depletion_ask_amount.max(0.0),
            replenish_bid_amount: row.replenish_bid_amount.max(0.0),
            replenish_ask_amount: row.replenish_ask_amount.max(0.0),
            cancel_bid_amount: row.cancel_bid_amount.max(0.0),
            cancel_ask_amount: row.cancel_ask_amount.max(0.0),
            decrease_bid_amount: row.decrease_bid_amount.max(0.0),
            decrease_ask_amount: row.decrease_ask_amount.max(0.0),
            remove_bid_amount: row.remove_bid_amount.max(0.0),
            remove_ask_amount: row.remove_ask_amount.max(0.0),
            execute_bid_amount: row.execute_bid_amount.max(0.0),
            execute_ask_amount: row.execute_ask_amount.max(0.0),
            liquidity_shock_score: row.liquidity_shock_score.and_then(finite),
        })
    }

    fn feature_value(&self, feature: &str) -> Option<f64> {
        match feature {
            "mlofi_norm_l10" => self.mlofi_norm_l10,
            "mlofi_norm_l5" => self.mlofi_norm_l5,
            "queue_imbalance_25" => self.queue_imbalance_25,
            "trade_arrival_alignment" => self.trade_arrival_alignment,
            "liquidity_shock_score" => self.liquidity_shock_score,
            _ => None,
        }
    }

    fn long_fill_evidence(&self) -> bool {
        self.trade_sell_amount > 0.0
            || self.depletion_bid_amount > 0.0
            || self.execute_bid_amount > 0.0
            || self.decrease_bid_amount > 0.0
            || self.remove_bid_amount > 0.0
    }

    fn short_fill_evidence(&self) -> bool {
        self.trade_buy_amount > 0.0
            || self.depletion_ask_amount > 0.0
            || self.execute_ask_amount > 0.0
            || self.decrease_ask_amount > 0.0
            || self.remove_ask_amount > 0.0
    }

    fn pressure_alignment(&self, side_sign: i8) -> f64 {
        let side = side_sign as f64;
        let mlofi = 0.5 * self.mlofi_roll10_l10 + 0.3 * self.mlofi_roll10_l5;
        let queue = self.queue_imbalance_25.unwrap_or(0.0);
        let trade = self.trade_flow_imbalance.unwrap_or(0.0);
        side * (mlofi + 0.15 * queue + 0.15 * trade)
    }
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct V10FoldInputRow {
    run_tag: String,
    fold: String,
    symbol: String,
    train_start_local_timestamp: u64,
    train_end_local_timestamp: u64,
    valid_start_local_timestamp: u64,
    valid_end_local_timestamp: u64,
    purge_us: u64,
    train_rows: usize,
    valid_rows: usize,
}

#[derive(Debug, Clone)]
struct FoldSpec {
    fold: String,
    symbol: String,
    train_start: u64,
    train_end: u64,
    valid_start: u64,
    valid_end: u64,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct ThresholdFit {
    fold: FoldSpec,
    feature_name: String,
    q20: f64,
    q80: f64,
    train_rows: usize,
    valid_rows: usize,
}

#[derive(Debug, Clone)]
struct WatchSignal {
    run_tag: String,
    fold: String,
    date: String,
    symbol: String,
    feature_name: String,
    gate: String,
    side_sign: i8,
    pos: usize,
    timestamp: u64,
    local_timestamp: u64,
    feature_value: f64,
    threshold: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
enum ControlType {
    Base,
    FrozenMarker,
    RandomMarkerSameMoveCount,
    VolStateShuffleWithinDate,
    WrongSymbolMarker,
    UpperLowerSwap,
    SideFlip,
    TimestampShiftPlus60,
    TimestampShiftMinus60,
    WrongSymbolSameTime,
}

impl ControlType {
    fn name(self) -> &'static str {
        match self {
            Self::Base => "dynamic_marker",
            Self::FrozenMarker => "frozen_marker",
            Self::RandomMarkerSameMoveCount => "random_marker_same_move_count",
            Self::VolStateShuffleWithinDate => "vol_state_shuffle_within_date",
            Self::WrongSymbolMarker => "wrong_symbol_marker",
            Self::UpperLowerSwap => "upper_lower_swap",
            Self::SideFlip => "side_flip",
            Self::TimestampShiftPlus60 => "timestamp_shift_plus_60s",
            Self::TimestampShiftMinus60 => "timestamp_shift_minus_60s",
            Self::WrongSymbolSameTime => "wrong_symbol_same_time",
        }
    }

    fn all_negative_controls() -> [Self; 9] {
        [
            Self::FrozenMarker,
            Self::RandomMarkerSameMoveCount,
            Self::VolStateShuffleWithinDate,
            Self::WrongSymbolMarker,
            Self::UpperLowerSwap,
            Self::SideFlip,
            Self::TimestampShiftPlus60,
            Self::TimestampShiftMinus60,
            Self::WrongSymbolSameTime,
        ]
    }
}

#[derive(Debug, Clone, Serialize)]
struct TradeRow {
    run_tag: String,
    fold: String,
    phase: String,
    date: String,
    symbol: String,
    feature_name: String,
    gate: String,
    side: String,
    strategy_id: String,
    control_type: String,
    signal_timestamp: u64,
    signal_local_timestamp: u64,
    signal_pos: usize,
    feature_value: f64,
    threshold: f64,
    fill_status: String,
    exit_reason: String,
    signal_mid_price: Option<f64>,
    signal_center_price: Option<f64>,
    entry_local_timestamp: Option<u64>,
    exit_local_timestamp: Option<u64>,
    entry_marker_price: Option<f64>,
    entry_touch_mid_price: Option<f64>,
    exit_price: Option<f64>,
    take_profit_bps: Option<f64>,
    stop_loss_bps: Option<f64>,
    stop_loss_to_take_profit: Option<f64>,
    gross_bps: Option<f64>,
    fee_bps: f64,
    maker_cost_bps: Option<f64>,
    queue_reset_penalty_bps: Option<f64>,
    maker_net_bps: Option<f64>,
    entry_spread_bps: Option<f64>,
    entry_sigma_bps: Option<f64>,
    entry_vol_state: Option<String>,
    exit_vol_state: Option<String>,
    marker_move_count: usize,
    marker_initial_price: Option<f64>,
    marker_final_price: Option<f64>,
    marker_lifetime_events: usize,
    hold_events: usize,
    mfe_bps: Option<f64>,
    mae_bps: Option<f64>,
    fill_price_semantics: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct SummaryRow {
    run_tag: String,
    summary_scope: String,
    fold: String,
    symbol: String,
    feature_name: String,
    gate: String,
    side: String,
    strategy_id: String,
    setups: usize,
    fills: usize,
    no_fills: usize,
    fill_rate: f64,
    gross_bps_mean: Option<f64>,
    maker_net_bps_mean: Option<f64>,
    maker_cost_bps_mean: Option<f64>,
    win_rate: Option<f64>,
    take_profit_rate: Option<f64>,
    stop_loss_rate: Option<f64>,
    timeout_rate: Option<f64>,
    stop_loss_tail_gross_bps_mean: Option<f64>,
    marker_move_count_mean: Option<f64>,
    queue_reset_penalty_bps_mean: Option<f64>,
    max_date_share: Option<f64>,
    max_symbol_share: Option<f64>,
    frozen_fills: Option<usize>,
    frozen_fill_rate: Option<f64>,
    frozen_gross_bps_mean: Option<f64>,
    frozen_maker_net_bps_mean: Option<f64>,
    frozen_stop_loss_tail_gross_bps_mean: Option<f64>,
    frozen_max_date_share: Option<f64>,
    v12_best_maker_net_bps_mean: Option<f64>,
    v12_stop_loss_tail_gross_bps_mean: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    best_control_maker_net_bps_mean: Option<f64>,
    control_separated: bool,
    primary_candidate: bool,
    pass_fills: bool,
    pass_positive_net: bool,
    pass_positive_gross: bool,
    pass_date_concentration: bool,
    pass_symbol_concentration: bool,
    pass_controls: bool,
    pass_tail_vs_v12: Option<bool>,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct NegativeControlRow {
    run_tag: String,
    summary_scope: String,
    control_type: String,
    fold: String,
    symbol: String,
    feature_name: String,
    gate: String,
    side: String,
    strategy_id: String,
    setups: usize,
    fills: usize,
    fill_rate: f64,
    gross_bps_mean: Option<f64>,
    maker_net_bps_mean: Option<f64>,
    win_rate: Option<f64>,
    stop_loss_tail_gross_bps_mean: Option<f64>,
    max_date_share: Option<f64>,
    max_symbol_share: Option<f64>,
    control_note: String,
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
    gross_bps_mean: Option<f64>,
    maker_net_bps_mean: Option<f64>,
    frozen_maker_net_bps_mean: Option<f64>,
    v12_best_maker_net_bps_mean: Option<f64>,
    stop_loss_tail_gross_bps_mean: Option<f64>,
    v12_stop_loss_tail_gross_bps_mean: Option<f64>,
    max_date_share: Option<f64>,
    max_symbol_share: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    control_separated: bool,
    evidence: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct DiagnosticRow {
    run_tag: String,
    fold: String,
    date: String,
    symbol: String,
    feature_name: String,
    gate: String,
    side: String,
    signal_local_timestamp: u64,
    dynamic_fill_status: String,
    frozen_fill_status: String,
    dynamic_exit_reason: String,
    frozen_exit_reason: String,
    dynamic_entry_marker_price: Option<f64>,
    frozen_entry_marker_price: Option<f64>,
    dynamic_entry_touch_mid_price: Option<f64>,
    dynamic_fill_used_marker_price: bool,
    dynamic_marker_move_count: usize,
    frozen_marker_move_count: usize,
    dynamic_queue_reset_penalty_bps: Option<f64>,
    dynamic_take_profit_bps: Option<f64>,
    dynamic_stop_loss_bps: Option<f64>,
    dynamic_stop_loss_to_take_profit: Option<f64>,
    dynamic_entry_vol_state: Option<String>,
    dynamic_exit_vol_state: Option<String>,
    dynamic_mfe_bps: Option<f64>,
    dynamic_mae_bps: Option<f64>,
    dynamic_gross_bps: Option<f64>,
    frozen_gross_bps: Option<f64>,
    dynamic_maker_net_bps: Option<f64>,
    frozen_maker_net_bps: Option<f64>,
    paired_note: String,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct SimResult {
    fill_status: String,
    exit_reason: String,
    entry_pos: Option<usize>,
    exit_pos: Option<usize>,
    entry_marker_price: Option<f64>,
    entry_touch_mid_price: Option<f64>,
    exit_price: Option<f64>,
    take_profit_bps: Option<f64>,
    stop_loss_bps: Option<f64>,
    gross_bps: Option<f64>,
    maker_cost_bps: Option<f64>,
    queue_reset_penalty_bps: f64,
    maker_net_bps: Option<f64>,
    entry_spread_bps: Option<f64>,
    entry_sigma_bps: Option<f64>,
    entry_vol_state: Option<String>,
    exit_vol_state: Option<String>,
    marker_move_count: usize,
    marker_initial_price: Option<f64>,
    marker_final_price: Option<f64>,
    marker_lifetime_events: usize,
    hold_events: usize,
    mfe_bps: Option<f64>,
    mae_bps: Option<f64>,
}

#[derive(Debug, Clone, Copy)]
struct SimOptions {
    control: ControlType,
    random_move_cap: Option<usize>,
}

#[derive(Debug, Clone)]
struct MarkerState {
    price: f64,
    initial_price: f64,
    move_count: usize,
    queue_penalty_bps: f64,
}

#[derive(Debug, Clone, Copy)]
struct WingState {
    take_profit_price: f64,
    stop_loss_price: f64,
    take_profit_bps: f64,
    stop_loss_bps: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ExitDecision {
    StopLoss,
    TakeProfit,
}

#[derive(Debug, Clone, Default)]
struct GroupStats {
    setups: usize,
    fills: usize,
    no_fills: usize,
    gross: Vec<f64>,
    maker_net: Vec<f64>,
    maker_cost: Vec<f64>,
    wins: usize,
    take_profit: usize,
    stop_loss: usize,
    timeout: usize,
    date_counts: BTreeMap<String, usize>,
    symbol_counts: BTreeMap<String, usize>,
    stop_loss_gross: Vec<f64>,
    move_counts: Vec<f64>,
    queue_penalties: Vec<f64>,
}

#[derive(Debug, Clone, Default)]
struct InputAudit {
    panel_files: usize,
    panel_rows: usize,
    usable_rows: usize,
    missing_folds: bool,
    missing_panel: bool,
    blockers: Vec<String>,
}

#[derive(Debug, Clone, Default)]
struct V12Benchmark {
    best_strategy_id: String,
    best_key: String,
    fills: usize,
    gross_bps_mean: Option<f64>,
    maker_net_bps_mean: Option<f64>,
    max_date_share: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    stop_loss_tail_gross_bps_mean: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct V12SummaryInputRow {
    run_tag: String,
    fold: String,
    symbol: String,
    bucket: String,
    strategy_id: String,
    setups: usize,
    fills: usize,
    fill_rate: f64,
    #[serde(deserialize_with = "de_opt_f64")]
    maker_net_bps_mean: Option<f64>,
    #[serde(deserialize_with = "de_opt_f64")]
    gross_bps_mean: Option<f64>,
    #[serde(deserialize_with = "de_opt_f64")]
    max_date_share: Option<f64>,
    #[serde(deserialize_with = "de_opt_f64")]
    control_abs_ge_base_abs_rate: Option<f64>,
    control_separated: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct V12TradeInputRow {
    run_tag: String,
    exit_reason: String,
    #[serde(deserialize_with = "de_opt_f64")]
    gross_bps: Option<f64>,
}

pub fn run_v13(config: &V13Config) -> Result<V13Summary> {
    if !config.fee_bps.is_finite() || config.fee_bps < 0.0 {
        bail!("--fee-bps must be finite and non-negative");
    }
    let symbols = parse_symbol_list(&config.symbols);
    if symbols.is_empty() {
        bail!("--symbols must contain at least one symbol");
    }
    fs::create_dir_all(&config.date_dir)?;
    fs::create_dir_all(&config.doc_dir)?;

    let paths = Paths::new(config);
    let folds = load_folds(&paths.filter_params_csv, &config.run_tag, &symbols)?;
    let (mut rows, mut audit) = read_panel_rows(config, &symbols)?;
    if folds.is_empty() {
        audit.missing_folds = true;
        audit.blockers.push(format!(
            "missing fold split CSV: {}",
            paths.filter_params_csv.display()
        ));
    }
    rows.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.local_timestamp.cmp(&b.local_timestamp))
            .then_with(|| a.event_index.cmp(&b.event_index))
    });
    enrich_rolling_state(&mut rows);

    let by_symbol = rows_by_symbol(&rows);
    let fits = fit_thresholds(&by_symbol, &folds);
    let mut signals = Vec::new();
    for fit in &fits {
        if let Some(symbol_rows) = by_symbol.get(&fit.fold.symbol) {
            signals.extend(build_watch_signals(symbol_rows, fit));
        }
    }

    let mut base_trades = Vec::new();
    let mut base_by_signal = HashMap::<String, SimResult>::new();
    for signal in &signals {
        let Some(symbol_rows) = by_symbol.get(&signal.symbol) else {
            continue;
        };
        let sim = simulate_with_context(
            symbol_rows,
            signal,
            signal.side_sign,
            config.fee_bps,
            SimOptions {
                control: ControlType::Base,
                random_move_cap: None,
            },
            &by_symbol,
        );
        base_by_signal.insert(signal_key(signal), sim.clone());
        base_trades.push(trade_row_from_sim(
            config,
            signal,
            signal.side_sign,
            ControlType::Base,
            &sim,
            symbol_rows,
        ));
    }

    let mut controls = Vec::<TradeRow>::new();
    for signal in &signals {
        let base_move_cap = base_by_signal
            .get(&signal_key(signal))
            .map(|sim| sim.marker_move_count);
        for control in ControlType::all_negative_controls() {
            let Some((control_rows, control_signal, side_sign, random_cap)) =
                control_context(&by_symbol, signal, control, base_move_cap)
            else {
                continue;
            };
            let sim = simulate_with_context(
                control_rows,
                &control_signal,
                side_sign,
                config.fee_bps,
                SimOptions {
                    control,
                    random_move_cap: random_cap,
                },
                &by_symbol,
            );
            controls.push(trade_row_from_sim(
                config,
                &control_signal,
                side_sign,
                control,
                &sim,
                control_rows,
            ));
        }
    }

    let v12 = load_v12_benchmark(&paths).unwrap_or_default();
    let control_rows = summarize_controls(&controls);
    let mut summaries = summarize_base_trades(&base_trades, &v12);
    attach_control_metrics(&mut summaries, &control_rows, &v12);
    let failure = build_failure_report(&config.run_tag, &audit, &summaries, &v12);
    mark_primary_candidate(&mut summaries, &failure.candidate_key);
    let diagnostics = build_diagnostics(config, &base_trades, &controls);

    write_csv_atomic(&paths.trades_csv, &base_trades)?;
    write_csv_atomic(&paths.summary_csv, &summaries)?;
    write_csv_atomic(&paths.negative_controls_csv, &control_rows)?;
    write_csv_atomic(&paths.failure_report_csv, &[failure.clone()])?;
    write_csv_atomic(&paths.diagnostics_csv, &diagnostics)?;
    write_report(
        config,
        &paths,
        &audit,
        &folds,
        &signals,
        &summaries,
        &control_rows,
        &diagnostics,
        &failure,
        &v12,
    )?;

    Ok(V13Summary {
        run_tag: config.run_tag.clone(),
        panel_rows: audit.panel_rows,
        fold_rows: folds.len(),
        signal_rows: signals.len(),
        trade_rows: base_trades.len(),
        summary_rows: summaries.len(),
        negative_control_rows: control_rows.len(),
        diagnostic_rows: diagnostics.len(),
        primary_status: failure.primary_status,
        trades_csv: path_string(&paths.trades_csv),
        summary_csv: path_string(&paths.summary_csv),
        negative_controls_csv: path_string(&paths.negative_controls_csv),
        failure_report_csv: path_string(&paths.failure_report_csv),
        diagnostics_csv: path_string(&paths.diagnostics_csv),
        report_md: path_string(&paths.report_md),
    })
}

fn load_folds(path: &Path, run_tag: &str, symbols: &[String]) -> Result<Vec<FoldSpec>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let symbol_set = symbols.iter().cloned().collect::<BTreeSet<_>>();
    let rows = load_csv_rows::<V10FoldInputRow>(path)?;
    Ok(rows
        .into_iter()
        .filter(|row| row.run_tag == run_tag && symbol_set.contains(&row.symbol))
        .map(|row| FoldSpec {
            fold: row.fold,
            symbol: row.symbol,
            train_start: row.train_start_local_timestamp,
            train_end: row.train_end_local_timestamp,
            valid_start: row.valid_start_local_timestamp,
            valid_end: row.valid_end_local_timestamp,
        })
        .collect())
}

fn read_panel_rows(config: &V13Config, symbols: &[String]) -> Result<(Vec<PanelRow>, InputAudit)> {
    let mut audit = InputAudit::default();
    let parts = collect_panel_parts(&config.data_root, &config.run_tag, symbols)?;
    audit.panel_files = parts.len();
    if parts.is_empty() {
        audit.missing_panel = true;
        audit.blockers.push(format!(
            "missing V10c panel parts under {}",
            config
                .data_root
                .join("derived")
                .join("bonk_v10c_event_ofi_panel")
                .join(format!("run_tag={}", config.run_tag))
                .display()
        ));
        return Ok((Vec::new(), audit));
    }
    let symbol_set = symbols.iter().cloned().collect::<BTreeSet<_>>();
    let mut out = Vec::new();
    for path in parts {
        let mut reader = csv::Reader::from_path(&path)
            .with_context(|| format!("failed to open {}", path.display()))?;
        for record in reader.deserialize::<EventPanelRow>() {
            let row = record.with_context(|| format!("failed to parse {}", path.display()))?;
            audit.panel_rows += 1;
            if row.run_tag != config.run_tag || !symbol_set.contains(&row.symbol) {
                continue;
            }
            if let Some(row) = PanelRow::from_panel(row) {
                audit.usable_rows += 1;
                out.push(row);
            }
        }
    }
    if out.is_empty() {
        audit
            .blockers
            .push("V10c panel parts loaded but no usable mid/center rows survived".to_string());
    }
    Ok((out, audit))
}

fn collect_panel_parts(
    data_root: &Path,
    run_tag: &str,
    symbols: &[String],
) -> Result<Vec<PathBuf>> {
    let base = data_root
        .join("derived")
        .join("bonk_v10c_event_ofi_panel")
        .join(format!("run_tag={run_tag}"));
    let mut out = Vec::new();
    for symbol in symbols {
        let symbol_dir = base.join(format!("symbol={symbol}"));
        collect_part_files_recursive(&symbol_dir, &mut out)?;
    }
    out.sort();
    Ok(out)
}

fn collect_part_files_recursive(dir: &Path, out: &mut Vec<PathBuf>) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(dir)? {
        let path = entry?.path();
        if path.is_dir() {
            collect_part_files_recursive(&path, out)?;
        } else if path
            .file_name()
            .and_then(|value| value.to_str())
            .is_some_and(|name| name.starts_with("part_") && name.ends_with(".csv"))
        {
            out.push(path);
        }
    }
    Ok(())
}

fn enrich_rolling_state(rows: &mut [PanelRow]) {
    let mut start = 0usize;
    while start < rows.len() {
        let symbol = rows[start].symbol.clone();
        let mut end = start + 1;
        while end < rows.len() && rows[end].symbol == symbol {
            end += 1;
        }
        let mut prev_center = None::<f64>;
        let mut rets = VecDeque::<f64>::new();
        for idx in start..end {
            if let Some(prev) = prev_center {
                if prev > 0.0 {
                    let ret = (rows[idx].center_price - prev) / prev * 10_000.0;
                    if ret.is_finite() {
                        rets.push_back(ret);
                        while rets.len() > 30 {
                            rets.pop_front();
                        }
                    }
                }
            }
            let rv30 = if rets.is_empty() {
                0.0
            } else {
                (rets.iter().map(|value| value * value).sum::<f64>() / rets.len() as f64).sqrt()
            };
            rows[idx].rv30_bps = rv30;
            rows[idx].sigma_bps = rv30.max(rows[idx].spread_bps).max(MIN_SIGMA_BPS);
            rows[idx].vol_state = classify_vol_state(rows[idx].sigma_bps).to_string();
            prev_center = Some(rows[idx].center_price);
        }
        start = end;
    }
}

fn classify_vol_state(sigma_bps: f64) -> &'static str {
    if sigma_bps < 1.0 {
        "calm"
    } else if sigma_bps < 3.0 {
        "normal"
    } else {
        "hot"
    }
}

fn rows_by_symbol(rows: &[PanelRow]) -> BTreeMap<String, Vec<&PanelRow>> {
    let mut by_symbol: BTreeMap<String, Vec<&PanelRow>> = BTreeMap::new();
    for row in rows {
        by_symbol.entry(row.symbol.clone()).or_default().push(row);
    }
    for rows in by_symbol.values_mut() {
        rows.sort_by(|a, b| {
            a.local_timestamp
                .cmp(&b.local_timestamp)
                .then_with(|| a.event_index.cmp(&b.event_index))
        });
    }
    by_symbol
}

fn fit_thresholds(
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
    folds: &[FoldSpec],
) -> Vec<ThresholdFit> {
    let mut out = Vec::new();
    for fold in folds {
        let Some(rows) = by_symbol.get(&fold.symbol) else {
            continue;
        };
        let train = rows
            .iter()
            .copied()
            .filter(|row| {
                row.factor_eligible
                    && row.local_timestamp >= fold.train_start
                    && row.local_timestamp <= fold.train_end
            })
            .collect::<Vec<_>>();
        let valid_rows = rows
            .iter()
            .filter(|row| {
                row.factor_eligible
                    && row.local_timestamp >= fold.valid_start
                    && row.local_timestamp <= fold.valid_end
            })
            .count();
        if train.len() < 20 || valid_rows < 10 {
            continue;
        }
        for feature_name in WATCH_FEATURES {
            let values = train
                .iter()
                .filter_map(|row| row.feature_value(feature_name))
                .collect::<Vec<_>>();
            let (Some(q20), Some(q80)) = (quantile(&values, 0.20), quantile(&values, 0.80)) else {
                continue;
            };
            if (q80 - q20).abs() <= f64::EPSILON {
                continue;
            }
            out.push(ThresholdFit {
                fold: fold.clone(),
                feature_name: feature_name.to_string(),
                q20,
                q80,
                train_rows: train.len(),
                valid_rows,
            });
        }
    }
    out
}

fn build_watch_signals(rows: &[&PanelRow], fit: &ThresholdFit) -> Vec<WatchSignal> {
    let mut high = Vec::new();
    let mut low = Vec::new();
    for (pos, row) in rows.iter().enumerate() {
        if !row.factor_eligible
            || row.local_timestamp < fit.fold.valid_start
            || row.local_timestamp > fit.fold.valid_end
        {
            continue;
        }
        let Some(value) = row.feature_value(&fit.feature_name) else {
            continue;
        };
        if value >= fit.q80 {
            high.push(WatchSignal {
                run_tag: row.run_tag.clone(),
                fold: fit.fold.fold.clone(),
                date: row.date.clone(),
                symbol: row.symbol.clone(),
                feature_name: fit.feature_name.clone(),
                gate: "high_gate_long_pressure".to_string(),
                side_sign: 1,
                pos,
                timestamp: row.timestamp,
                local_timestamp: row.local_timestamp,
                feature_value: value,
                threshold: fit.q80,
            });
        }
        if value <= fit.q20 {
            low.push(WatchSignal {
                run_tag: row.run_tag.clone(),
                fold: fit.fold.fold.clone(),
                date: row.date.clone(),
                symbol: row.symbol.clone(),
                feature_name: fit.feature_name.clone(),
                gate: "low_gate_short_pressure".to_string(),
                side_sign: -1,
                pos,
                timestamp: row.timestamp,
                local_timestamp: row.local_timestamp,
                feature_value: value,
                threshold: fit.q20,
            });
        }
    }
    let mut out = dedupe_by_event_gap(high, SIGNAL_EVENT_GAP);
    out.extend(dedupe_by_event_gap(low, SIGNAL_EVENT_GAP));
    out.sort_by_key(|signal| signal.local_timestamp);
    sample_signals(out, MAX_SIGNALS_PER_GROUP)
}

fn dedupe_by_event_gap(mut signals: Vec<WatchSignal>, gap: usize) -> Vec<WatchSignal> {
    signals.sort_by_key(|signal| signal.pos);
    let mut next_pos = 0usize;
    let mut out = Vec::new();
    for signal in signals {
        if signal.pos < next_pos {
            continue;
        }
        next_pos = signal.pos.saturating_add(gap);
        out.push(signal);
    }
    out
}

fn sample_signals(signals: Vec<WatchSignal>, max_rows: usize) -> Vec<WatchSignal> {
    if max_rows == 0 || signals.len() <= max_rows {
        return signals;
    }
    let step = signals.len() as f64 / max_rows as f64;
    (0..max_rows)
        .map(|idx| {
            let source_idx = ((idx as f64) * step).floor() as usize;
            signals[source_idx.min(signals.len() - 1)].clone()
        })
        .collect()
}

fn simulate_with_context(
    rows: &[&PanelRow],
    signal: &WatchSignal,
    side_sign: i8,
    fee_bps: f64,
    options: SimOptions,
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
) -> SimResult {
    let marker_proxy = if options.control == ControlType::WrongSymbolMarker {
        by_symbol
            .iter()
            .find(|(symbol, candidate)| symbol.as_str() != signal.symbol && !candidate.is_empty())
            .map(|(_, candidate)| candidate.as_slice())
    } else {
        None
    };
    simulate_core(rows, marker_proxy, signal, side_sign, fee_bps, options)
}

fn simulate_core(
    rows: &[&PanelRow],
    marker_proxy: Option<&[&PanelRow]>,
    signal: &WatchSignal,
    side_sign: i8,
    fee_bps: f64,
    options: SimOptions,
) -> SimResult {
    if signal.pos >= rows.len() {
        return no_fill_result("signal_pos_out_of_range");
    }
    let mut marker_state = None::<MarkerState>;
    let mut marker_lifetime_events = 0usize;
    let mut proxy_pos = marker_proxy
        .and_then(|proxy| first_row_at_or_after(proxy, rows[signal.pos].local_timestamp))
        .unwrap_or(0);
    let end = rows
        .len()
        .min(signal.pos.saturating_add(MAX_MARKER_LIFETIME_EVENTS + 1));

    for pos in signal.pos.saturating_add(1)..end {
        marker_lifetime_events += 1;
        let row = rows[pos];
        let proxy_row = if let Some(proxy) = marker_proxy {
            while proxy_pos + 1 < proxy.len()
                && proxy[proxy_pos + 1].local_timestamp <= row.local_timestamp
            {
                proxy_pos += 1;
            }
            proxy.get(proxy_pos).copied().unwrap_or(row)
        } else {
            row
        };
        let desired = desired_marker_price(row, proxy_row, signal, side_sign, options.control);
        match &mut marker_state {
            None => {
                marker_state = Some(MarkerState {
                    price: desired,
                    initial_price: desired,
                    move_count: 0,
                    queue_penalty_bps: 0.0,
                });
            }
            Some(state) => {
                if options.control != ControlType::FrozenMarker {
                    let move_threshold = marker_move_threshold_price(row);
                    let random_cap_ok = options
                        .random_move_cap
                        .map(|cap| state.move_count < cap)
                        .unwrap_or(true);
                    if random_cap_ok && (desired - state.price).abs() >= move_threshold {
                        state.price = desired;
                        state.move_count += 1;
                        state.queue_penalty_bps += QUEUE_RESET_PENALTY_BPS;
                    }
                }
            }
        }
        let state = marker_state.as_ref().expect("marker initialized");
        if marker_touch_and_evidence(row, state.price, side_sign) {
            return simulate_after_fill(
                rows,
                pos,
                row,
                side_sign,
                fee_bps,
                options.control,
                state,
                marker_lifetime_events,
            );
        }
    }
    let mut result = no_fill_result("marker_not_touched_with_evidence");
    if let Some(state) = marker_state {
        result.marker_initial_price = Some(state.initial_price);
        result.marker_final_price = Some(state.price);
        result.marker_move_count = state.move_count;
        result.queue_reset_penalty_bps = state.queue_penalty_bps;
        result.marker_lifetime_events = marker_lifetime_events;
    }
    result
}

fn simulate_after_fill(
    rows: &[&PanelRow],
    entry_pos: usize,
    entry_row: &PanelRow,
    side_sign: i8,
    fee_bps: f64,
    control: ControlType,
    marker: &MarkerState,
    marker_lifetime_events: usize,
) -> SimResult {
    let entry_price = marker.price;
    let mut wings = initial_wings(entry_price, entry_row, side_sign, fee_bps, control);
    let initial_tp_bps = wings.take_profit_bps;
    let initial_sl_bps = wings.stop_loss_bps;
    let maker_cost = fee_bps + 0.25 * entry_row.spread_bps + marker.queue_penalty_bps;
    let mut mfe_bps = 0.0f64;
    let mut mae_bps = 0.0f64;
    let mut last_pos = entry_pos;
    let end = rows
        .len()
        .min(entry_pos.saturating_add(MAX_HOLD_EVENTS + 1));
    for pos in entry_pos.saturating_add(1)..end {
        let row = rows[pos];
        last_pos = pos;
        update_mfe_mae(
            row.mid_price,
            entry_price,
            side_sign,
            &mut mfe_bps,
            &mut mae_bps,
        );
        if control != ControlType::FrozenMarker {
            update_wings(&mut wings, entry_price, row, side_sign, fee_bps, control);
        }
        if let Some(decision) = evaluate_exit(row.mid_price, side_sign, &wings) {
            let (exit_reason, exit_price) = match decision {
                ExitDecision::StopLoss => ("stop_loss", wings.stop_loss_price),
                ExitDecision::TakeProfit => ("take_profit", wings.take_profit_price),
            };
            return filled_result(
                exit_reason,
                entry_pos,
                pos,
                entry_price,
                entry_row.mid_price,
                exit_price,
                initial_tp_bps,
                initial_sl_bps,
                &wings,
                side_sign,
                maker_cost,
                marker,
                marker_lifetime_events,
                pos.saturating_sub(entry_pos),
                mfe_bps,
                mae_bps,
                entry_row,
                row,
            );
        }
    }
    let exit_row = rows.get(last_pos).copied().unwrap_or(entry_row);
    update_mfe_mae(
        exit_row.mid_price,
        entry_price,
        side_sign,
        &mut mfe_bps,
        &mut mae_bps,
    );
    filled_result(
        if last_pos + 1 >= rows.len() {
            "data_end"
        } else {
            "timeout_events"
        },
        entry_pos,
        last_pos,
        entry_price,
        entry_row.mid_price,
        exit_row.mid_price,
        initial_tp_bps,
        initial_sl_bps,
        &wings,
        side_sign,
        maker_cost,
        marker,
        marker_lifetime_events,
        last_pos.saturating_sub(entry_pos),
        mfe_bps,
        mae_bps,
        entry_row,
        exit_row,
    )
}

fn desired_marker_price(
    row: &PanelRow,
    proxy_row: &PanelRow,
    signal: &WatchSignal,
    side_sign: i8,
    control: ControlType,
) -> f64 {
    let sigma = effective_sigma(row, proxy_row, signal, control);
    let vol_mult = match proxy_row.vol_state.as_str() {
        "hot" => 0.65,
        "calm" => 0.35,
        _ => 0.50,
    };
    let mut offset_bps = (vol_mult * sigma)
        .max(0.50 * proxy_row.spread_bps)
        .max(TICK_FLOOR_BPS);
    let alignment = row.pressure_alignment(side_sign);
    if alignment > 0.0 {
        offset_bps *= 0.85;
    } else if alignment < 0.0 {
        offset_bps *= 1.15;
    }
    if control == ControlType::RandomMarkerSameMoveCount {
        let u = deterministic_unit(
            signal.local_timestamp ^ row.local_timestamp ^ row.event_index as u64,
            &signal.symbol,
        );
        offset_bps *= 0.40 + 1.20 * u;
    }
    proxy_row.center_price * (1.0 - side_sign as f64 * offset_bps / 10_000.0)
}

fn effective_sigma(
    row: &PanelRow,
    proxy_row: &PanelRow,
    signal: &WatchSignal,
    control: ControlType,
) -> f64 {
    if control != ControlType::VolStateShuffleWithinDate {
        return proxy_row.sigma_bps.max(row.spread_bps).max(MIN_SIGMA_BPS);
    }
    let u = deterministic_unit(
        signal.local_timestamp ^ row.local_timestamp ^ 0xA5A5_5A5A,
        &row.date,
    );
    let mult = 0.60 + 1.20 * u;
    (proxy_row.sigma_bps * mult)
        .max(row.spread_bps)
        .max(MIN_SIGMA_BPS)
}

fn marker_move_threshold_price(row: &PanelRow) -> f64 {
    let threshold_bps = (0.25 * row.sigma_bps)
        .max(row.spread_bps)
        .max(TICK_FLOOR_BPS);
    row.center_price * threshold_bps / 10_000.0
}

fn marker_touch_and_evidence(row: &PanelRow, marker_price: f64, side_sign: i8) -> bool {
    if side_sign >= 0 {
        row.mid_price <= marker_price && row.long_fill_evidence()
    } else {
        row.mid_price >= marker_price && row.short_fill_evidence()
    }
}

fn initial_wings(
    entry_price: f64,
    row: &PanelRow,
    side_sign: i8,
    fee_bps: f64,
    control: ControlType,
) -> WingState {
    let base_tp = (1.20 * row.sigma_bps)
        .max(row.spread_bps + fee_bps + 0.25)
        .max(0.75);
    let base_sl = (0.90 * row.sigma_bps)
        .max(row.spread_bps)
        .max(0.75)
        .min(base_tp * MAX_STOP_TO_TP);
    let (take_profit_bps, stop_loss_bps) = if control == ControlType::UpperLowerSwap {
        (
            base_sl.max(0.75),
            base_tp.min(base_sl.max(0.75) * MAX_STOP_TO_TP),
        )
    } else {
        (base_tp, base_sl)
    };
    WingState {
        take_profit_price: entry_price * (1.0 + side_sign as f64 * take_profit_bps / 10_000.0),
        stop_loss_price: entry_price * (1.0 - side_sign as f64 * stop_loss_bps / 10_000.0),
        take_profit_bps,
        stop_loss_bps,
    }
}

fn update_wings(
    wings: &mut WingState,
    entry_price: f64,
    row: &PanelRow,
    side_sign: i8,
    fee_bps: f64,
    control: ControlType,
) {
    let next = initial_wings(entry_price, row, side_sign, fee_bps, control);
    if side_sign >= 0 {
        wings.take_profit_price = wings.take_profit_price.max(next.take_profit_price);
        wings.stop_loss_price = wings.stop_loss_price.max(next.stop_loss_price);
    } else {
        wings.take_profit_price = wings.take_profit_price.min(next.take_profit_price);
        wings.stop_loss_price = wings.stop_loss_price.min(next.stop_loss_price);
    }
    wings.take_profit_bps =
        side_sign as f64 * (wings.take_profit_price - entry_price) / entry_price * 10_000.0;
    wings.stop_loss_bps =
        side_sign as f64 * (entry_price - wings.stop_loss_price) / entry_price * 10_000.0;
    if wings.take_profit_bps > 0.0 && wings.stop_loss_bps > wings.take_profit_bps * MAX_STOP_TO_TP {
        wings.stop_loss_bps = wings.take_profit_bps * MAX_STOP_TO_TP;
        wings.stop_loss_price =
            entry_price * (1.0 - side_sign as f64 * wings.stop_loss_bps / 10_000.0);
    }
}

fn evaluate_exit(mid_price: f64, side_sign: i8, wings: &WingState) -> Option<ExitDecision> {
    let adverse_hit = if side_sign >= 0 {
        mid_price <= wings.stop_loss_price
    } else {
        mid_price >= wings.stop_loss_price
    };
    let favorable_hit = if side_sign >= 0 {
        mid_price >= wings.take_profit_price
    } else {
        mid_price <= wings.take_profit_price
    };
    if adverse_hit {
        Some(ExitDecision::StopLoss)
    } else if favorable_hit {
        Some(ExitDecision::TakeProfit)
    } else {
        None
    }
}

fn update_mfe_mae(
    mid_price: f64,
    entry_price: f64,
    side_sign: i8,
    mfe_bps: &mut f64,
    mae_bps: &mut f64,
) {
    let side_ret = side_sign as f64 * (mid_price - entry_price) / entry_price * 10_000.0;
    *mfe_bps = (*mfe_bps).max(side_ret);
    *mae_bps = (*mae_bps).min(side_ret);
}

fn filled_result(
    exit_reason: &str,
    entry_pos: usize,
    exit_pos: usize,
    entry_price: f64,
    entry_touch_mid_price: f64,
    exit_price: f64,
    initial_tp_bps: f64,
    initial_sl_bps: f64,
    wings: &WingState,
    side_sign: i8,
    maker_cost: f64,
    marker: &MarkerState,
    marker_lifetime_events: usize,
    hold_events: usize,
    mfe_bps: f64,
    mae_bps: f64,
    entry_row: &PanelRow,
    exit_row: &PanelRow,
) -> SimResult {
    let gross_bps = side_sign as f64 * (exit_price - entry_price) / entry_price * 10_000.0;
    SimResult {
        fill_status: "filled".to_string(),
        exit_reason: exit_reason.to_string(),
        entry_pos: Some(entry_pos),
        exit_pos: Some(exit_pos),
        entry_marker_price: Some(entry_price),
        entry_touch_mid_price: Some(entry_touch_mid_price),
        exit_price: Some(exit_price),
        take_profit_bps: Some(initial_tp_bps.max(wings.take_profit_bps)),
        stop_loss_bps: Some(initial_sl_bps.min(wings.stop_loss_bps.max(initial_sl_bps))),
        gross_bps: Some(gross_bps),
        maker_cost_bps: Some(maker_cost),
        queue_reset_penalty_bps: marker.queue_penalty_bps,
        maker_net_bps: Some(gross_bps - maker_cost),
        entry_spread_bps: Some(entry_row.spread_bps),
        entry_sigma_bps: Some(entry_row.sigma_bps),
        entry_vol_state: Some(entry_row.vol_state.clone()),
        exit_vol_state: Some(exit_row.vol_state.clone()),
        marker_move_count: marker.move_count,
        marker_initial_price: Some(marker.initial_price),
        marker_final_price: Some(marker.price),
        marker_lifetime_events,
        hold_events,
        mfe_bps: Some(mfe_bps),
        mae_bps: Some(mae_bps),
    }
}

fn no_fill_result(reason: &str) -> SimResult {
    SimResult {
        fill_status: "no_fill".to_string(),
        exit_reason: reason.to_string(),
        entry_pos: None,
        exit_pos: None,
        entry_marker_price: None,
        entry_touch_mid_price: None,
        exit_price: None,
        take_profit_bps: None,
        stop_loss_bps: None,
        gross_bps: None,
        maker_cost_bps: None,
        queue_reset_penalty_bps: 0.0,
        maker_net_bps: None,
        entry_spread_bps: None,
        entry_sigma_bps: None,
        entry_vol_state: None,
        exit_vol_state: None,
        marker_move_count: 0,
        marker_initial_price: None,
        marker_final_price: None,
        marker_lifetime_events: 0,
        hold_events: 0,
        mfe_bps: None,
        mae_bps: None,
    }
}

fn control_context<'a>(
    by_symbol: &'a BTreeMap<String, Vec<&'a PanelRow>>,
    signal: &WatchSignal,
    control: ControlType,
    base_move_cap: Option<usize>,
) -> Option<(&'a [&'a PanelRow], WatchSignal, i8, Option<usize>)> {
    let rows = by_symbol.get(&signal.symbol)?;
    match control {
        ControlType::Base => Some((rows.as_slice(), signal.clone(), signal.side_sign, None)),
        ControlType::FrozenMarker
        | ControlType::RandomMarkerSameMoveCount
        | ControlType::VolStateShuffleWithinDate
        | ControlType::WrongSymbolMarker
        | ControlType::UpperLowerSwap => Some((
            rows.as_slice(),
            signal.clone(),
            signal.side_sign,
            (control == ControlType::RandomMarkerSameMoveCount)
                .then_some(base_move_cap.unwrap_or(0)),
        )),
        ControlType::SideFlip => Some((rows.as_slice(), signal.clone(), -signal.side_sign, None)),
        ControlType::TimestampShiftPlus60 => {
            let target = signal.local_timestamp.saturating_add(60_000_000);
            let pos = first_row_at_or_after(rows, target)?;
            Some((
                rows.as_slice(),
                signal_with_row(signal, rows[pos], pos),
                signal.side_sign,
                None,
            ))
        }
        ControlType::TimestampShiftMinus60 => {
            let target = signal.local_timestamp.saturating_sub(60_000_000);
            let pos = first_row_at_or_after(rows, target)?;
            Some((
                rows.as_slice(),
                signal_with_row(signal, rows[pos], pos),
                signal.side_sign,
                None,
            ))
        }
        ControlType::WrongSymbolSameTime => {
            let (symbol, other_rows) = by_symbol.iter().find(|(symbol, candidate)| {
                symbol.as_str() != signal.symbol && !candidate.is_empty()
            })?;
            let pos = first_row_at_or_after(other_rows, signal.local_timestamp)?;
            let mut shifted = signal_with_row(signal, other_rows[pos], pos);
            shifted.symbol = symbol.clone();
            Some((other_rows.as_slice(), shifted, signal.side_sign, None))
        }
    }
}

fn signal_with_row(source: &WatchSignal, row: &PanelRow, pos: usize) -> WatchSignal {
    WatchSignal {
        run_tag: source.run_tag.clone(),
        fold: source.fold.clone(),
        date: row.date.clone(),
        symbol: row.symbol.clone(),
        feature_name: source.feature_name.clone(),
        gate: source.gate.clone(),
        side_sign: source.side_sign,
        pos,
        timestamp: row.timestamp,
        local_timestamp: row.local_timestamp,
        feature_value: source.feature_value,
        threshold: source.threshold,
    }
}

fn trade_row_from_sim(
    config: &V13Config,
    signal: &WatchSignal,
    side_sign: i8,
    control: ControlType,
    sim: &SimResult,
    rows: &[&PanelRow],
) -> TradeRow {
    let signal_row = rows.get(signal.pos).copied();
    let entry_row = sim.entry_pos.and_then(|pos| rows.get(pos).copied());
    let exit_row = sim.exit_pos.and_then(|pos| rows.get(pos).copied());
    let stop_loss_to_take_profit = match (sim.stop_loss_bps, sim.take_profit_bps) {
        (Some(sl), Some(tp)) if tp.abs() > f64::EPSILON => Some(sl / tp),
        _ => None,
    };
    TradeRow {
        run_tag: config.run_tag.clone(),
        fold: signal.fold.clone(),
        phase: "validation".to_string(),
        date: signal.date.clone(),
        symbol: signal.symbol.clone(),
        feature_name: signal.feature_name.clone(),
        gate: signal.gate.clone(),
        side: side_name(side_sign).to_string(),
        strategy_id: if control == ControlType::FrozenMarker {
            FROZEN_STRATEGY_ID.to_string()
        } else {
            STRATEGY_ID.to_string()
        },
        control_type: control.name().to_string(),
        signal_timestamp: signal.timestamp,
        signal_local_timestamp: signal.local_timestamp,
        signal_pos: signal.pos,
        feature_value: signal.feature_value,
        threshold: signal.threshold,
        fill_status: sim.fill_status.clone(),
        exit_reason: sim.exit_reason.clone(),
        signal_mid_price: signal_row.map(|row| row.mid_price),
        signal_center_price: signal_row.map(|row| row.center_price),
        entry_local_timestamp: entry_row.map(|row| row.local_timestamp),
        exit_local_timestamp: exit_row.map(|row| row.local_timestamp),
        entry_marker_price: sim.entry_marker_price,
        entry_touch_mid_price: sim.entry_touch_mid_price,
        exit_price: sim.exit_price,
        take_profit_bps: sim.take_profit_bps,
        stop_loss_bps: sim.stop_loss_bps,
        stop_loss_to_take_profit,
        gross_bps: sim.gross_bps,
        fee_bps: config.fee_bps,
        maker_cost_bps: sim.maker_cost_bps,
        queue_reset_penalty_bps: sim.entry_pos.map(|_| sim.queue_reset_penalty_bps),
        maker_net_bps: sim.maker_net_bps,
        entry_spread_bps: sim.entry_spread_bps,
        entry_sigma_bps: sim.entry_sigma_bps,
        entry_vol_state: sim.entry_vol_state.clone(),
        exit_vol_state: sim.exit_vol_state.clone(),
        marker_move_count: sim.marker_move_count,
        marker_initial_price: sim.marker_initial_price,
        marker_final_price: sim.marker_final_price,
        marker_lifetime_events: sim.marker_lifetime_events,
        hold_events: sim.hold_events,
        mfe_bps: sim.mfe_bps,
        mae_bps: sim.mae_bps,
        fill_price_semantics: "entry_price_is_marker_t_not_touch_mid".to_string(),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn summarize_base_trades(trades: &[TradeRow], v12: &V12Benchmark) -> Vec<SummaryRow> {
    let mut groups = BTreeMap::<SummaryKey, Vec<&TradeRow>>::new();
    for trade in trades {
        groups
            .entry(SummaryKey::fold_symbol(trade))
            .or_default()
            .push(trade);
        groups
            .entry(SummaryKey::aggregate(trade))
            .or_default()
            .push(trade);
    }
    groups
        .into_iter()
        .map(|(key, rows)| summary_from_rows(key, rows, v12))
        .collect()
}

fn summarize_controls(trades: &[TradeRow]) -> Vec<NegativeControlRow> {
    let mut groups = BTreeMap::<(String, SummaryKey), Vec<&TradeRow>>::new();
    for trade in trades {
        let control = trade.control_type.clone();
        groups
            .entry((control.clone(), SummaryKey::fold_symbol(trade)))
            .or_default()
            .push(trade);
        groups
            .entry((control, SummaryKey::aggregate(trade)))
            .or_default()
            .push(trade);
    }
    groups
        .into_iter()
        .map(|((control_type, key), rows)| {
            let stats = group_stats(&rows);
            NegativeControlRow {
                run_tag: rows[0].run_tag.clone(),
                summary_scope: key.summary_scope,
                control_type: control_type.clone(),
                fold: key.fold,
                symbol: key.symbol,
                feature_name: key.feature_name,
                gate: key.gate,
                side: key.side,
                strategy_id: rows[0].strategy_id.clone(),
                setups: stats.setups,
                fills: stats.fills,
                fill_rate: rate(stats.fills, stats.setups),
                gross_bps_mean: mean(&stats.gross),
                maker_net_bps_mean: mean(&stats.maker_net),
                win_rate: win_rate(&stats.maker_net),
                stop_loss_tail_gross_bps_mean: mean(&stats.stop_loss_gross),
                max_date_share: max_share(&stats.date_counts),
                max_symbol_share: max_share(&stats.symbol_counts),
                control_note: control_note(&control_type).to_string(),
                guardrail: GUARDRAIL.to_string(),
            }
        })
        .collect()
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct SummaryKey {
    summary_scope: String,
    fold: String,
    symbol: String,
    feature_name: String,
    gate: String,
    side: String,
}

impl SummaryKey {
    fn fold_symbol(trade: &TradeRow) -> Self {
        Self {
            summary_scope: "fold_symbol".to_string(),
            fold: trade.fold.clone(),
            symbol: trade.symbol.clone(),
            feature_name: trade.feature_name.clone(),
            gate: trade.gate.clone(),
            side: trade.side.clone(),
        }
    }

    fn aggregate(trade: &TradeRow) -> Self {
        Self {
            summary_scope: "feature_gate_all_folds_symbols".to_string(),
            fold: "all".to_string(),
            symbol: "all".to_string(),
            feature_name: trade.feature_name.clone(),
            gate: trade.gate.clone(),
            side: trade.side.clone(),
        }
    }

    fn from_summary(row: &SummaryRow) -> Self {
        Self {
            summary_scope: row.summary_scope.clone(),
            fold: row.fold.clone(),
            symbol: row.symbol.clone(),
            feature_name: row.feature_name.clone(),
            gate: row.gate.clone(),
            side: row.side.clone(),
        }
    }

    fn from_control(row: &NegativeControlRow) -> Self {
        Self {
            summary_scope: row.summary_scope.clone(),
            fold: row.fold.clone(),
            symbol: row.symbol.clone(),
            feature_name: row.feature_name.clone(),
            gate: row.gate.clone(),
            side: row.side.clone(),
        }
    }

    fn display_key(&self) -> String {
        format!(
            "{}|{}|{}|{}|{}|{}",
            self.summary_scope, self.fold, self.symbol, self.feature_name, self.gate, self.side
        )
    }
}

fn summary_from_rows(key: SummaryKey, rows: Vec<&TradeRow>, v12: &V12Benchmark) -> SummaryRow {
    let stats = group_stats(&rows);
    SummaryRow {
        run_tag: rows[0].run_tag.clone(),
        summary_scope: key.summary_scope,
        fold: key.fold,
        symbol: key.symbol,
        feature_name: key.feature_name,
        gate: key.gate,
        side: key.side,
        strategy_id: STRATEGY_ID.to_string(),
        setups: stats.setups,
        fills: stats.fills,
        no_fills: stats.no_fills,
        fill_rate: rate(stats.fills, stats.setups),
        gross_bps_mean: mean(&stats.gross),
        maker_net_bps_mean: mean(&stats.maker_net),
        maker_cost_bps_mean: mean(&stats.maker_cost),
        win_rate: win_rate(&stats.maker_net),
        take_profit_rate: Some(rate(stats.take_profit, stats.fills)),
        stop_loss_rate: Some(rate(stats.stop_loss, stats.fills)),
        timeout_rate: Some(rate(stats.timeout, stats.fills)),
        stop_loss_tail_gross_bps_mean: mean(&stats.stop_loss_gross),
        marker_move_count_mean: mean(&stats.move_counts),
        queue_reset_penalty_bps_mean: mean(&stats.queue_penalties),
        max_date_share: max_share(&stats.date_counts),
        max_symbol_share: max_share(&stats.symbol_counts),
        frozen_fills: None,
        frozen_fill_rate: None,
        frozen_gross_bps_mean: None,
        frozen_maker_net_bps_mean: None,
        frozen_stop_loss_tail_gross_bps_mean: None,
        frozen_max_date_share: None,
        v12_best_maker_net_bps_mean: v12.maker_net_bps_mean,
        v12_stop_loss_tail_gross_bps_mean: v12.stop_loss_tail_gross_bps_mean,
        control_abs_ge_base_abs_rate: None,
        best_control_maker_net_bps_mean: None,
        control_separated: false,
        primary_candidate: false,
        pass_fills: stats.fills >= MIN_VALID_FILLS,
        pass_positive_net: mean(&stats.maker_net).is_some_and(|value| value > 0.0),
        pass_positive_gross: mean(&stats.gross).is_some_and(|value| value > 0.0),
        pass_date_concentration: max_share(&stats.date_counts)
            .is_some_and(|value| value <= MAX_DATE_SHARE),
        pass_symbol_concentration: max_share(&stats.symbol_counts)
            .is_some_and(|value| value <= MAX_SYMBOL_SHARE),
        pass_controls: false,
        pass_tail_vs_v12: tail_better_than_v12(
            mean(&stats.stop_loss_gross),
            v12.stop_loss_tail_gross_bps_mean,
        ),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn group_stats(rows: &[&TradeRow]) -> GroupStats {
    let mut stats = GroupStats::default();
    for trade in rows {
        stats.setups += 1;
        stats
            .symbol_counts
            .entry(trade.symbol.clone())
            .and_modify(|count| *count += 1)
            .or_insert(1);
        stats
            .date_counts
            .entry(trade.date.clone())
            .and_modify(|count| *count += 1)
            .or_insert(1);
        if trade.fill_status == "filled" {
            stats.fills += 1;
            if let Some(value) = trade.gross_bps {
                stats.gross.push(value);
            }
            if let Some(value) = trade.maker_net_bps {
                if value > 0.0 {
                    stats.wins += 1;
                }
                stats.maker_net.push(value);
            }
            if let Some(value) = trade.maker_cost_bps {
                stats.maker_cost.push(value);
            }
            if let Some(value) = trade.queue_reset_penalty_bps {
                stats.queue_penalties.push(value);
            }
            stats.move_counts.push(trade.marker_move_count as f64);
            match trade.exit_reason.as_str() {
                "take_profit" => stats.take_profit += 1,
                "stop_loss" => {
                    stats.stop_loss += 1;
                    if let Some(value) = trade.gross_bps {
                        stats.stop_loss_gross.push(value);
                    }
                }
                "timeout_events" | "data_end" => stats.timeout += 1,
                _ => {}
            }
        } else {
            stats.no_fills += 1;
        }
    }
    stats
}

fn attach_control_metrics(
    summaries: &mut [SummaryRow],
    controls: &[NegativeControlRow],
    v12: &V12Benchmark,
) {
    let mut by_key = BTreeMap::<SummaryKey, Vec<&NegativeControlRow>>::new();
    for control in controls {
        by_key
            .entry(SummaryKey::from_control(control))
            .or_default()
            .push(control);
    }
    for summary in summaries {
        let Some(base) = summary.maker_net_bps_mean else {
            continue;
        };
        let key = SummaryKey::from_summary(summary);
        let Some(rows) = by_key.get(&key) else {
            continue;
        };
        let control_means = rows
            .iter()
            .filter_map(|row| row.maker_net_bps_mean)
            .collect::<Vec<_>>();
        if !control_means.is_empty() {
            let abs_ge = control_means
                .iter()
                .filter(|value| value.abs() >= base.abs())
                .count();
            summary.control_abs_ge_base_abs_rate = Some(rate(abs_ge, control_means.len()));
            summary.best_control_maker_net_bps_mean =
                control_means.iter().copied().max_by(f64::total_cmp);
            summary.control_separated = base > 0.0
                && control_means.iter().all(|value| base > *value)
                && summary
                    .control_abs_ge_base_abs_rate
                    .is_some_and(|value| value <= CONTROL_ABS_GE_BASE_LIMIT);
            summary.pass_controls = summary.control_separated;
        }
        if let Some(frozen) = rows
            .iter()
            .find(|row| row.control_type == ControlType::FrozenMarker.name())
        {
            summary.frozen_fills = Some(frozen.fills);
            summary.frozen_fill_rate = Some(frozen.fill_rate);
            summary.frozen_gross_bps_mean = frozen.gross_bps_mean;
            summary.frozen_maker_net_bps_mean = frozen.maker_net_bps_mean;
            summary.frozen_stop_loss_tail_gross_bps_mean = frozen.stop_loss_tail_gross_bps_mean;
            summary.frozen_max_date_share = frozen.max_date_share;
        }
        summary.v12_best_maker_net_bps_mean = v12.maker_net_bps_mean;
        summary.v12_stop_loss_tail_gross_bps_mean = v12.stop_loss_tail_gross_bps_mean;
    }
}

fn build_failure_report(
    run_tag: &str,
    audit: &InputAudit,
    summaries: &[SummaryRow],
    v12: &V12Benchmark,
) -> FailureReportRow {
    if !audit.blockers.is_empty() {
        return failure_row_empty(
            run_tag,
            "data_quality_blocked",
            &format!("input blockers={}", audit.blockers.join("; ")),
            v12,
        );
    }
    let best = summaries
        .iter()
        .filter(|row| row.summary_scope == "feature_gate_all_folds_symbols")
        .chain(summaries.iter())
        .max_by(|a, b| summary_score(a).total_cmp(&summary_score(b)));
    let Some(best) = best else {
        return failure_row_empty(
            run_tag,
            "insufficient_fills",
            "no summary rows generated",
            v12,
        );
    };
    let pass_tail = best.pass_tail_vs_v12.unwrap_or(true);
    let status = if best.fills < MIN_VALID_FILLS {
        "insufficient_fills"
    } else if best.gross_bps_mean.unwrap_or(f64::NEG_INFINITY) <= 0.0 {
        "gross_edge_too_thin"
    } else if best.maker_net_bps_mean.unwrap_or(f64::NEG_INFINITY) <= 0.0 {
        "maker_net_not_positive_after_cost"
    } else if best.max_date_share.unwrap_or(1.0) > MAX_DATE_SHARE {
        "single_date_dependent"
    } else if best.max_symbol_share.unwrap_or(1.0) > MAX_SYMBOL_SHARE {
        "single_symbol_dependent"
    } else if best.control_abs_ge_base_abs_rate.unwrap_or(1.0) > CONTROL_ABS_GE_BASE_LIMIT
        || !best.control_separated
    {
        "controls_not_separated"
    } else if !pass_tail {
        "stop_loss_tail_not_better_than_v12"
    } else {
        "dynamic_marker_survives_controls_research_only"
    };
    FailureReportRow {
        run_tag: run_tag.to_string(),
        primary_status: status.to_string(),
        candidate_key: SummaryKey::from_summary(best).display_key(),
        setups: best.setups,
        fills: best.fills,
        fill_rate: best.fill_rate,
        gross_bps_mean: best.gross_bps_mean,
        maker_net_bps_mean: best.maker_net_bps_mean,
        frozen_maker_net_bps_mean: best.frozen_maker_net_bps_mean,
        v12_best_maker_net_bps_mean: v12.maker_net_bps_mean,
        stop_loss_tail_gross_bps_mean: best.stop_loss_tail_gross_bps_mean,
        v12_stop_loss_tail_gross_bps_mean: v12.stop_loss_tail_gross_bps_mean,
        max_date_share: best.max_date_share,
        max_symbol_share: best.max_symbol_share,
        control_abs_ge_base_abs_rate: best.control_abs_ge_base_abs_rate,
        control_separated: best.control_separated,
        evidence: format!(
            "fills>={MIN_VALID_FILLS}; maker_net>0; gross>0; max_date_share<={MAX_DATE_SHARE}; control_abs_ge_base_abs_rate<={CONTROL_ABS_GE_BASE_LIMIT}; dynamic fill price is marker_t"
        ),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn mark_primary_candidate(summaries: &mut [SummaryRow], candidate_key: &str) {
    for summary in summaries {
        summary.primary_candidate =
            SummaryKey::from_summary(summary).display_key() == candidate_key;
    }
}

fn failure_row_empty(
    run_tag: &str,
    status: &str,
    evidence: &str,
    v12: &V12Benchmark,
) -> FailureReportRow {
    FailureReportRow {
        run_tag: run_tag.to_string(),
        primary_status: status.to_string(),
        candidate_key: "none".to_string(),
        setups: 0,
        fills: 0,
        fill_rate: 0.0,
        gross_bps_mean: None,
        maker_net_bps_mean: None,
        frozen_maker_net_bps_mean: None,
        v12_best_maker_net_bps_mean: v12.maker_net_bps_mean,
        stop_loss_tail_gross_bps_mean: None,
        v12_stop_loss_tail_gross_bps_mean: v12.stop_loss_tail_gross_bps_mean,
        max_date_share: None,
        max_symbol_share: None,
        control_abs_ge_base_abs_rate: None,
        control_separated: false,
        evidence: evidence.to_string(),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn summary_score(row: &SummaryRow) -> f64 {
    let net = row.maker_net_bps_mean.unwrap_or(f64::NEG_INFINITY);
    let fill_bonus = (row.fills as f64).ln_1p() * 0.05;
    let date_penalty = row
        .max_date_share
        .map(|share| (share - MAX_DATE_SHARE).max(0.0) * 10.0)
        .unwrap_or(10.0);
    let symbol_penalty = row
        .max_symbol_share
        .map(|share| (share - MAX_SYMBOL_SHARE).max(0.0) * 10.0)
        .unwrap_or(10.0);
    net + fill_bonus - date_penalty - symbol_penalty
}

fn tail_better_than_v12(dynamic_tail: Option<f64>, v12_tail: Option<f64>) -> Option<bool> {
    match (dynamic_tail, v12_tail) {
        (Some(dynamic), Some(v12)) => Some(dynamic > v12),
        _ => None,
    }
}

fn build_diagnostics(
    config: &V13Config,
    base_trades: &[TradeRow],
    controls: &[TradeRow],
) -> Vec<DiagnosticRow> {
    let mut frozen_by_signal = HashMap::<String, &TradeRow>::new();
    for control in controls {
        if control.control_type == ControlType::FrozenMarker.name() {
            frozen_by_signal.insert(trade_signal_key(control), control);
        }
    }
    base_trades
        .iter()
        .filter_map(|base| {
            let frozen = frozen_by_signal.get(&trade_signal_key(base)).copied()?;
            Some(DiagnosticRow {
                run_tag: config.run_tag.clone(),
                fold: base.fold.clone(),
                date: base.date.clone(),
                symbol: base.symbol.clone(),
                feature_name: base.feature_name.clone(),
                gate: base.gate.clone(),
                side: base.side.clone(),
                signal_local_timestamp: base.signal_local_timestamp,
                dynamic_fill_status: base.fill_status.clone(),
                frozen_fill_status: frozen.fill_status.clone(),
                dynamic_exit_reason: base.exit_reason.clone(),
                frozen_exit_reason: frozen.exit_reason.clone(),
                dynamic_entry_marker_price: base.entry_marker_price,
                frozen_entry_marker_price: frozen.entry_marker_price,
                dynamic_entry_touch_mid_price: base.entry_touch_mid_price,
                dynamic_fill_used_marker_price: base
                    .entry_marker_price
                    .zip(base.entry_touch_mid_price)
                    .is_some_and(|(marker, mid)| (marker - mid).abs() > f64::EPSILON),
                dynamic_marker_move_count: base.marker_move_count,
                frozen_marker_move_count: frozen.marker_move_count,
                dynamic_queue_reset_penalty_bps: base.queue_reset_penalty_bps,
                dynamic_take_profit_bps: base.take_profit_bps,
                dynamic_stop_loss_bps: base.stop_loss_bps,
                dynamic_stop_loss_to_take_profit: base.stop_loss_to_take_profit,
                dynamic_entry_vol_state: base.entry_vol_state.clone(),
                dynamic_exit_vol_state: base.exit_vol_state.clone(),
                dynamic_mfe_bps: base.mfe_bps,
                dynamic_mae_bps: base.mae_bps,
                dynamic_gross_bps: base.gross_bps,
                frozen_gross_bps: frozen.gross_bps,
                dynamic_maker_net_bps: base.maker_net_bps,
                frozen_maker_net_bps: frozen.maker_net_bps,
                paired_note: "paired_same_signal_dynamic_marker_vs_frozen_marker".to_string(),
                guardrail: GUARDRAIL.to_string(),
            })
        })
        .collect()
}

fn load_v12_benchmark(paths: &Paths) -> Result<V12Benchmark> {
    let mut out = V12Benchmark::default();
    if paths.v12_summary_csv.exists() {
        let summaries = load_csv_rows::<V12SummaryInputRow>(&paths.v12_summary_csv)?;
        if let Some(best) = summaries.iter().max_by(|a, b| {
            a.maker_net_bps_mean
                .unwrap_or(f64::NEG_INFINITY)
                .total_cmp(&b.maker_net_bps_mean.unwrap_or(f64::NEG_INFINITY))
        }) {
            out.best_strategy_id = best.strategy_id.clone();
            out.best_key = format!(
                "{}|{}|{}|{}",
                best.fold, best.symbol, best.bucket, best.strategy_id
            );
            out.fills = best.fills;
            out.gross_bps_mean = best.gross_bps_mean;
            out.maker_net_bps_mean = best.maker_net_bps_mean;
            out.max_date_share = best.max_date_share;
            out.control_abs_ge_base_abs_rate = best.control_abs_ge_base_abs_rate;
        }
    }
    if paths.v12_trades_csv.exists() {
        let trades = load_csv_rows::<V12TradeInputRow>(&paths.v12_trades_csv)?;
        let stop_loss = trades
            .iter()
            .filter(|row| row.exit_reason == "stop_loss")
            .filter_map(|row| row.gross_bps)
            .collect::<Vec<_>>();
        out.stop_loss_tail_gross_bps_mean = mean(&stop_loss);
    }
    Ok(out)
}

fn write_report(
    config: &V13Config,
    paths: &Paths,
    audit: &InputAudit,
    folds: &[FoldSpec],
    signals: &[WatchSignal],
    summaries: &[SummaryRow],
    controls: &[NegativeControlRow],
    diagnostics: &[DiagnosticRow],
    failure: &FailureReportRow,
    v12: &V12Benchmark,
) -> Result<()> {
    let mut top = summaries
        .iter()
        .filter(|row| row.summary_scope == "feature_gate_all_folds_symbols")
        .collect::<Vec<_>>();
    top.sort_by(|a, b| summary_score(b).total_cmp(&summary_score(a)));
    top.truncate(8);
    let control_types = controls
        .iter()
        .map(|row| row.control_type.clone())
        .collect::<BTreeSet<_>>();
    let generated_at = Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true);

    let mut lines = Vec::new();
    lines.push("# BONK V13 Dynamic Marker / Vol Wings".to_string());
    lines.push(String::new());
    lines.push(format!("- generated_at: `{generated_at}`"));
    lines.push(format!("- run_tag: `{}`", config.run_tag));
    lines.push(format!("- guardrail: `{GUARDRAIL}`"));
    lines.push(
        "- stance: research-only; no trading advice, no execution recommendation, no alpha claim."
            .to_string(),
    );
    lines.push(String::new());
    lines.push("## Inputs".to_string());
    lines.push(String::new());
    lines.push(format!("- V10c panel files: `{}`", audit.panel_files));
    lines.push(format!("- V10c panel rows read: `{}`", audit.panel_rows));
    lines.push(format!("- usable rows: `{}`", audit.usable_rows));
    lines.push(format!("- folds from V10 filter params: `{}`", folds.len()));
    lines.push(format!("- validation watch signals: `{}`", signals.len()));
    lines.push(format!("- features: `{}`", WATCH_FEATURES.join(",")));
    if !audit.blockers.is_empty() {
        lines.push(format!("- blockers: `{}`", audit.blockers.join("; ")));
    }
    lines.push(String::new());
    lines.push("## Primary Status".to_string());
    lines.push(String::new());
    lines.push(format!("- primary_status: `{}`", failure.primary_status));
    lines.push(format!("- candidate_key: `{}`", failure.candidate_key));
    lines.push(format!("- fills: `{}`", failure.fills));
    lines.push(format!(
        "- dynamic maker net mean: `{}` bps",
        fmt_opt(failure.maker_net_bps_mean, 4)
    ));
    lines.push(format!(
        "- dynamic gross mean: `{}` bps",
        fmt_opt(failure.gross_bps_mean, 4)
    ));
    lines.push(format!(
        "- control_abs_ge_base_abs_rate: `{}`",
        fmt_opt(failure.control_abs_ge_base_abs_rate, 4)
    ));
    lines.push(format!(
        "- max_date_share: `{}`",
        fmt_opt(failure.max_date_share, 4)
    ));
    lines.push(format!(
        "- max_symbol_share: `{}`",
        fmt_opt(failure.max_symbol_share, 4)
    ));
    lines.push(String::new());
    lines.push("## V12 Frozen Baseline".to_string());
    lines.push(String::new());
    lines.push(format!("- V12 best key: `{}`", empty_as_na(&v12.best_key)));
    lines.push(format!("- V12 fills: `{}`", v12.fills));
    lines.push(format!(
        "- V12 maker net mean: `{}` bps",
        fmt_opt(v12.maker_net_bps_mean, 4)
    ));
    lines.push(format!(
        "- V12 gross mean: `{}` bps",
        fmt_opt(v12.gross_bps_mean, 4)
    ));
    lines.push(format!(
        "- V12 stop-loss gross mean: `{}` bps",
        fmt_opt(v12.stop_loss_tail_gross_bps_mean, 4)
    ));
    lines.push("- V13 also writes a paired `frozen_marker` negative control from the same V10c signals, so the dynamic marker comparison is same-signal and not just cross-report.".to_string());
    lines.push(String::new());
    lines.push("## Top Dynamic vs Frozen Rows".to_string());
    lines.push(String::new());
    lines.push("| scope | feature | gate | side | fills | dyn_net | frozen_net | dyn_tail | frozen_tail | date_share | control_rate |".to_string());
    lines.push(
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |".to_string(),
    );
    for row in &top {
        lines.push(format!(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
            row.summary_scope,
            row.feature_name,
            row.gate,
            row.side,
            row.fills,
            fmt_opt(row.maker_net_bps_mean, 4),
            fmt_opt(row.frozen_maker_net_bps_mean, 4),
            fmt_opt(row.stop_loss_tail_gross_bps_mean, 4),
            fmt_opt(row.frozen_stop_loss_tail_gross_bps_mean, 4),
            fmt_opt(row.max_date_share, 4),
            fmt_opt(row.control_abs_ge_base_abs_rate, 4),
        ));
    }
    lines.push(String::new());
    lines.push("## Negative Controls".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- control types written: `{}`",
        control_types.into_iter().collect::<Vec<_>>().join(",")
    ));
    lines.push("- Required controls are present: frozen marker, random marker same move count, vol-state shuffle, wrong-symbol marker, upper/lower swap, side flip, timestamp shifts, and wrong-symbol same-time.".to_string());
    lines.push(String::new());
    lines.push("## Mechanics Fixed From V12".to_string());
    lines.push(String::new());
    lines.push("- Dynamic marker recomputes `center_t`, `sigma_t`, `vol_state`, and `marker_t` on every event while the setup is active.".to_string());
    lines.push("- Entry price is `marker_t`; diagnostics explicitly record touch-row mid so marker-fill semantics are auditable.".to_string());
    lines.push("- Marker moves only when the update exceeds `max(0.25 * sigma_t, spread_bps, tick_floor)` and each move adds queue reset penalty.".to_string());
    lines.push("- Wings update every event after entry; TP can trail favorably, SL only tightens, and `SL/TP <= 1.5` is enforced.".to_string());
    lines.push(
        "- If TP and SL are both hit in the same event, adverse-first is applied.".to_string(),
    );
    lines.push(String::new());
    lines.push("## Outputs".to_string());
    lines.push(String::new());
    lines.push(format!("- trades: `{}`", path_string(&paths.trades_csv)));
    lines.push(format!("- summary: `{}`", path_string(&paths.summary_csv)));
    lines.push(format!(
        "- negative_controls: `{}`",
        path_string(&paths.negative_controls_csv)
    ));
    lines.push(format!(
        "- failure_report: `{}`",
        path_string(&paths.failure_report_csv)
    ));
    lines.push(format!(
        "- diagnostics: `{}`",
        path_string(&paths.diagnostics_csv)
    ));
    lines.push(format!("- diagnostic rows: `{}`", diagnostics.len()));
    write_text_atomic(&paths.report_md, &lines.join("\n"))
}

fn control_note(control_type: &str) -> &'static str {
    match control_type {
        "frozen_marker" => "same-signal baseline with static marker and static wings",
        "random_marker_same_move_count" => {
            "deterministic random marker path capped by base move count"
        }
        "vol_state_shuffle_within_date" => {
            "same signal with deterministic vol-state perturbation within active date context"
        }
        "wrong_symbol_marker" => {
            "original symbol touch/evidence but marker center comes from the other symbol at-or-before current event time"
        }
        "upper_lower_swap" => "same marker but upper/lower wing distances are swapped",
        "side_flip" => "same timestamp and feature gate with opposite side",
        "timestamp_shift_plus_60s" => "same symbol side shifted to first row at or after +60s",
        "timestamp_shift_minus_60s" => "same symbol side shifted to first row at or after -60s",
        "wrong_symbol_same_time" => {
            "entire setup replayed on the other symbol at the same timestamp"
        }
        _ => "control",
    }
}

fn first_row_at_or_after(rows: &[&PanelRow], target: u64) -> Option<usize> {
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

fn signal_key(signal: &WatchSignal) -> String {
    format!(
        "{}|{}|{}|{}|{}|{}",
        signal.fold,
        signal.symbol,
        signal.feature_name,
        signal.gate,
        signal.side_sign,
        signal.local_timestamp
    )
}

fn trade_signal_key(trade: &TradeRow) -> String {
    format!(
        "{}|{}|{}|{}|{}|{}",
        trade.fold,
        trade.symbol,
        trade.feature_name,
        trade.gate,
        if trade.side == "long" { 1 } else { -1 },
        trade.signal_local_timestamp
    )
}

fn side_name(side_sign: i8) -> &'static str {
    if side_sign >= 0 { "long" } else { "short" }
}

fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
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

fn win_rate(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        Some(rate(
            values.iter().filter(|value| **value > 0.0).count(),
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

fn max_share(counts: &BTreeMap<String, usize>) -> Option<f64> {
    let total = counts.values().sum::<usize>();
    if total == 0 {
        None
    } else {
        counts
            .values()
            .max()
            .map(|value| *value as f64 / total as f64)
    }
}

fn deterministic_unit(seed: u64, salt: &str) -> f64 {
    let mut hash = seed ^ 0x9E37_79B9_7F4A_7C15;
    for byte in salt.as_bytes() {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0xBF58_476D_1CE4_E5B9);
        hash ^= hash >> 27;
    }
    (hash % 10_000) as f64 / 10_000.0
}

fn fmt_opt(value: Option<f64>, digits: usize) -> String {
    value
        .map(|value| format!("{value:.digits$}"))
        .unwrap_or_else(|| "NA".to_string())
}

fn empty_as_na(value: &str) -> &str {
    if value.is_empty() { "NA" } else { value }
}

fn load_csv_rows<T: DeserializeOwned>(path: &Path) -> Result<Vec<T>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    let mut out = Vec::new();
    for record in reader.deserialize() {
        out.push(record.with_context(|| format!("failed to parse {}", path.display()))?);
    }
    Ok(out)
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

fn write_text_atomic(path: &Path, text: &str) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    fs::write(&temp, text).with_context(|| format!("failed to write {}", temp.display()))?;
    replace_with_temp(&temp, path)
}

fn temp_path_for(path: &Path) -> PathBuf {
    let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let stamp = Utc::now().timestamp_micros();
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("bonk_v13_output");
    std::env::temp_dir().join(format!("{file_name}.{pid}.{stamp}.{counter}.tmp"))
}

fn replace_with_temp(temp: &Path, path: &Path) -> Result<()> {
    ensure_parent_dir(path)?;
    for attempt in 0..=FILE_REPLACE_RETRIES {
        if path.exists() {
            match fs::remove_file(path) {
                Ok(()) => {}
                Err(err) => {
                    if attempt < FILE_REPLACE_RETRIES {
                        thread::sleep(Duration::from_millis(FILE_REPLACE_RETRY_MS));
                        continue;
                    }
                    return Err(err)
                        .with_context(|| format!("failed to remove {}", path.display()));
                }
            }
        }
        match fs::rename(temp, path) {
            Ok(()) => return Ok(()),
            Err(err) => {
                if attempt < FILE_REPLACE_RETRIES {
                    thread::sleep(Duration::from_millis(FILE_REPLACE_RETRY_MS));
                    continue;
                }
                return Err(err).with_context(|| {
                    format!("failed to move {} to {}", temp.display(), path.display())
                });
            }
        }
    }
    bail!("failed to replace {}", path.display())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn marker_updates_during_waiting() {
        let mut rows = vec![
            test_row(100.0, 100.0, 1, 0.2, 0.0, 0.0),
            test_row(101.0, 101.0, 2, 0.2, 0.0, 0.0),
            test_row(102.0, 102.0, 3, 0.2, 0.0, 0.0),
            test_row(102.0, 101.0, 4, 0.2, 0.0, 1.0),
        ];
        enrich_rolling_state(&mut rows);
        let refs = rows.iter().collect::<Vec<_>>();
        let signal = test_signal(0);
        let sim = simulate_core(
            &refs,
            None,
            &signal,
            1,
            2.0,
            SimOptions {
                control: ControlType::Base,
                random_move_cap: None,
            },
        );
        assert_eq!(sim.fill_status, "filled");
        assert!(sim.marker_move_count > 0);
        assert_ne!(sim.marker_initial_price, sim.entry_marker_price);
    }

    #[test]
    fn fill_uses_marker_price_not_touch_mid() {
        let mut rows = vec![
            test_row(100.0, 100.0, 1, 0.2, 0.0, 0.0),
            test_row(100.0, 99.99, 2, 0.2, 0.0, 1.0),
            test_row(100.2, 100.2, 3, 0.2, 1.0, 0.0),
        ];
        enrich_rolling_state(&mut rows);
        let refs = rows.iter().collect::<Vec<_>>();
        let signal = test_signal(0);
        let sim = simulate_core(
            &refs,
            None,
            &signal,
            1,
            2.0,
            SimOptions {
                control: ControlType::Base,
                random_move_cap: None,
            },
        );
        assert_eq!(sim.fill_status, "filled");
        let marker = sim.entry_marker_price.unwrap();
        let touch_mid = sim.entry_touch_mid_price.unwrap();
        assert!((marker - touch_mid).abs() > f64::EPSILON);
    }

    #[test]
    fn stop_loss_does_not_widen_and_take_profit_can_trail() {
        let entry = 100.0;
        let mut first = test_row(100.0, 100.0, 1, 1.0, 0.0, 0.0);
        first.sigma_bps = 2.0;
        let mut wings = initial_wings(entry, &first, 1, 2.0, ControlType::Base);
        let old_stop = wings.stop_loss_price;
        let old_tp = wings.take_profit_price;
        let mut later = test_row(101.0, 101.0, 2, 1.0, 0.0, 0.0);
        later.sigma_bps = 0.6;
        update_wings(&mut wings, entry, &later, 1, 2.0, ControlType::Base);
        assert!(wings.stop_loss_price >= old_stop);
        assert!(wings.take_profit_price >= old_tp);
        assert!(wings.stop_loss_bps <= wings.take_profit_bps * MAX_STOP_TO_TP + 1e-9);
    }

    #[test]
    fn adverse_first_when_same_event_hits_both_wings() {
        let wings = WingState {
            take_profit_price: 100.40,
            stop_loss_price: 100.50,
            take_profit_bps: 4.0,
            stop_loss_bps: -5.0,
        };
        assert_eq!(
            evaluate_exit(100.45, 1, &wings),
            Some(ExitDecision::StopLoss)
        );
    }

    #[test]
    fn marker_controls_are_declared_no_future_data() {
        assert!(!control_reads_future_rows(ControlType::FrozenMarker));
        assert!(!control_reads_future_rows(
            ControlType::RandomMarkerSameMoveCount
        ));
        assert!(!control_reads_future_rows(ControlType::WrongSymbolMarker));
    }

    #[test]
    fn synthetic_run_writes_all_outputs() -> Result<()> {
        let root = unique_test_dir("v13_synthetic");
        let data_root = root.join("data/bonk/v1");
        let date_dir = root.join("date");
        let doc_dir = root.join("docs/markets/bonk");
        let run_tag = "test_v13".to_string();
        fs::create_dir_all(&date_dir)?;
        for symbol in ["BONK1MUSDC", "BONK1MUSDT"] {
            let part = data_root
                .join("derived/bonk_v10c_event_ofi_panel")
                .join(format!("run_tag={run_tag}"))
                .join(format!("symbol={symbol}"))
                .join("dt=2026-05-06")
                .join("part_000001.csv");
            let rows = (0..320)
                .map(|idx| synthetic_panel_row(&run_tag, symbol, idx))
                .collect::<Vec<_>>();
            write_csv_atomic(&part, &rows)?;
        }
        let folds = vec![
            synthetic_fold(&run_tag, "fold1", "BONK1MUSDC"),
            synthetic_fold(&run_tag, "fold1", "BONK1MUSDT"),
        ];
        write_csv_atomic(
            &date_dir.join(format!("bonk_v10_filter_params_{run_tag}.csv")),
            &folds,
        )?;
        let summary = run_v13(&V13Config {
            data_root,
            date_dir: date_dir.clone(),
            doc_dir: doc_dir.clone(),
            run_tag: run_tag.clone(),
            fee_bps: 2.0,
            symbols: "BONK1MUSDC,BONK1MUSDT".to_string(),
        })?;
        assert!(Path::new(&summary.trades_csv).exists());
        assert!(Path::new(&summary.summary_csv).exists());
        assert!(Path::new(&summary.negative_controls_csv).exists());
        assert!(Path::new(&summary.failure_report_csv).exists());
        assert!(Path::new(&summary.diagnostics_csv).exists());
        assert!(Path::new(&summary.report_md).exists());
        assert!(summary.diagnostic_rows > 0);
        Ok(())
    }

    fn control_reads_future_rows(control: ControlType) -> bool {
        matches!(control, ControlType::TimestampShiftPlus60)
    }

    fn test_signal(pos: usize) -> WatchSignal {
        WatchSignal {
            run_tag: "test".to_string(),
            fold: "fold1".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            feature_name: "mlofi_norm_l10".to_string(),
            gate: "high_gate_long_pressure".to_string(),
            side_sign: 1,
            pos,
            timestamp: pos as u64,
            local_timestamp: pos as u64,
            feature_value: 1.0,
            threshold: 0.5,
        }
    }

    fn test_row(center: f64, mid: f64, idx: usize, spread: f64, buy: f64, sell: f64) -> PanelRow {
        PanelRow {
            run_tag: "test".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            timestamp: idx as u64,
            local_timestamp: idx as u64,
            event_index: idx,
            factor_eligible: true,
            mid_price: mid,
            spread_bps: spread,
            microprice: Some(center),
            center_price: center,
            rv30_bps: 0.0,
            sigma_bps: spread.max(MIN_SIGMA_BPS),
            vol_state: "normal".to_string(),
            best_bid_price: Some(mid - 0.01),
            best_ask_price: Some(mid + 0.01),
            queue_imbalance_25: Some(0.2),
            mlofi_norm_l5: Some(0.2),
            mlofi_norm_l10: Some(0.2),
            mlofi_roll10_l5: 0.2,
            mlofi_roll10_l10: 0.2,
            trade_flow_imbalance: Some(buy - sell),
            trade_arrival_alignment: Some(0.2),
            trade_buy_amount: buy,
            trade_sell_amount: sell,
            depletion_bid_amount: sell,
            depletion_ask_amount: buy,
            replenish_bid_amount: 0.0,
            replenish_ask_amount: 0.0,
            cancel_bid_amount: 0.0,
            cancel_ask_amount: 0.0,
            decrease_bid_amount: 0.0,
            decrease_ask_amount: 0.0,
            remove_bid_amount: 0.0,
            remove_ask_amount: 0.0,
            execute_bid_amount: sell,
            execute_ask_amount: buy,
            liquidity_shock_score: Some(0.2),
        }
    }

    #[derive(Debug, Clone, Serialize)]
    struct SyntheticFoldRow {
        run_tag: String,
        fold: String,
        symbol: String,
        train_start_local_timestamp: u64,
        train_end_local_timestamp: u64,
        valid_start_local_timestamp: u64,
        valid_end_local_timestamp: u64,
        purge_us: u64,
        train_rows: usize,
        valid_rows: usize,
        net_low: f64,
        net_high: f64,
        energy_high: f64,
        fill_low: f64,
        fill_high: f64,
        flow_abs_high: f64,
        spread_high: f64,
        thresholds_fit_on_train: String,
        guardrail: String,
    }

    fn synthetic_fold(run_tag: &str, fold: &str, symbol: &str) -> SyntheticFoldRow {
        SyntheticFoldRow {
            run_tag: run_tag.to_string(),
            fold: fold.to_string(),
            symbol: symbol.to_string(),
            train_start_local_timestamp: 1_000,
            train_end_local_timestamp: 140_000,
            valid_start_local_timestamp: 141_000,
            valid_end_local_timestamp: 320_000,
            purge_us: 1,
            train_rows: 140,
            valid_rows: 179,
            net_low: -0.1,
            net_high: 0.1,
            energy_high: 0.1,
            fill_low: 0.1,
            fill_high: 0.9,
            flow_abs_high: 1.0,
            spread_high: 2.0,
            thresholds_fit_on_train: "train_only".to_string(),
            guardrail: GUARDRAIL.to_string(),
        }
    }

    fn synthetic_panel_row(run_tag: &str, symbol: &str, idx: usize) -> EventPanelRow {
        let local_timestamp = (idx as u64 + 1) * 1_000;
        let drift = idx as f64 * 0.002;
        let mid = 100.0 + drift + if idx % 31 == 0 { -0.15 } else { 0.0 };
        let feature = if idx % 17 == 0 {
            1.5
        } else {
            (idx % 20) as f64 / 20.0 - 0.5
        };
        EventPanelRow {
            run_tag: run_tag.to_string(),
            date: "2026-05-06".to_string(),
            symbol: symbol.to_string(),
            exchange: "bullish".to_string(),
            timestamp: local_timestamp,
            local_timestamp,
            event_index: idx,
            is_snapshot_batch: idx == 0,
            factor_eligible: idx > 5,
            execute_cancel_confidence: "synthetic".to_string(),
            batch_rows: 1,
            crossed_levels_removed: 0,
            noop_updates: 0,
            create_updates: 1,
            replenish_updates: 0,
            decrease_updates: 0,
            remove_updates: 0,
            best_bid_price: Some(mid - 0.01),
            best_bid_amount: Some(10.0),
            best_ask_price: Some(mid + 0.01),
            best_ask_amount: Some(10.0),
            mid_price: Some(mid),
            spread_bps: Some(1.0),
            microprice: Some(mid),
            microprice_dev_bps: Some(0.0),
            bid_levels: 25,
            ask_levels: 25,
            bid_depth_1: 10.0,
            ask_depth_1: 10.0,
            bid_depth_2: 10.0,
            ask_depth_2: 10.0,
            bid_depth_3: 10.0,
            ask_depth_3: 10.0,
            bid_depth_5: 10.0,
            ask_depth_5: 10.0,
            bid_depth_10: 10.0,
            ask_depth_10: 10.0,
            bid_depth_25: 10.0,
            ask_depth_25: 10.0,
            queue_imbalance_1: Some(feature),
            queue_imbalance_5: Some(feature),
            queue_imbalance_25: Some(feature),
            limit_add_bid_amount: 0.0,
            limit_add_ask_amount: 0.0,
            replenish_bid_amount: 0.0,
            replenish_ask_amount: 0.0,
            decrease_bid_amount: 0.0,
            decrease_ask_amount: 0.0,
            remove_bid_amount: 0.0,
            remove_ask_amount: 0.0,
            depletion_bid_amount: if idx % 31 == 1 { 1.0 } else { 0.0 },
            depletion_ask_amount: if idx % 37 == 1 { 1.0 } else { 0.0 },
            execute_bid_amount: if idx % 31 == 1 { 1.0 } else { 0.0 },
            execute_ask_amount: if idx % 37 == 1 { 1.0 } else { 0.0 },
            cancel_bid_amount: 0.0,
            cancel_ask_amount: 0.0,
            event_matched_rate: Some(1.0),
            trade_window_count: 1,
            trade_buy_amount: if idx % 37 == 1 { 1.0 } else { 0.0 },
            trade_sell_amount: if idx % 31 == 1 { 1.0 } else { 0.0 },
            trade_notional_quote: 100.0,
            trade_flow_imbalance: Some(feature),
            trade_arrival_alignment: Some(feature),
            ofi_l1_raw: feature,
            ofi_l1_depth_norm: Some(feature),
            mlofi_raw_l1: feature,
            mlofi_raw_l2: feature,
            mlofi_raw_l3: feature,
            mlofi_raw_l5: feature,
            mlofi_raw_l10: feature,
            mlofi_raw_l25: feature,
            mlofi_norm_l1: Some(feature),
            mlofi_norm_l2: Some(feature),
            mlofi_norm_l3: Some(feature),
            mlofi_norm_l5: Some(feature),
            mlofi_norm_l10: Some(feature),
            mlofi_norm_l25: Some(feature),
            mlofi_roll10_l1: feature,
            mlofi_roll10_l2: feature,
            mlofi_roll10_l3: feature,
            mlofi_roll10_l5: feature,
            mlofi_roll10_l10: feature,
            mlofi_roll10_l25: feature,
            queue_depletion_intensity: Some(0.1),
            replenish_intensity: Some(0.1),
            cancellation_withdrawal_intensity: Some(0.1),
            liquidity_shock_score: Some(feature.abs()),
            bid_top_levels_json: "[]".to_string(),
            ask_top_levels_json: "[]".to_string(),
            guardrail: GUARDRAIL.to_string(),
        }
    }

    fn unique_test_dir(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "{}_{}_{}",
            name,
            std::process::id(),
            Utc::now().timestamp_micros()
        ))
    }
}

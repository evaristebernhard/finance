use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use chrono::{SecondsFormat, Utc};
use finance_chain_core::storage::ensure_parent_dir;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

use crate::download::{DEFAULT_BONK_DATA_ROOT, parse_symbol_list, path_string};
use crate::v10::{DEFAULT_V10_RUN_TAG, DEFAULT_V10_SYMBOLS};
use crate::v10c::EventPanelRow;

const GUARDRAIL: &str = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim";
const STRATEGY_ID: &str = "v14_queue_reactive_first_passage_state_policy";
const FILE_REPLACE_RETRIES: usize = 80;
const FILE_REPLACE_RETRY_MS: u64 = 250;
const MIN_SIGMA_BPS: f64 = 0.50;
const TICK_FLOOR_BPS: f64 = 0.10;
const MAX_FILL_WAIT_EVENTS: usize = 300;
const MAX_TRAIN_ANCHORS_PER_FOLD_SYMBOL: usize = 700;
const MAX_VALID_ANCHORS_PER_FOLD_SYMBOL: usize = 12_000;
const VALID_EVENT_GAP: usize = 20;
const MIN_SUPPORT: usize = 20;
const MIN_P_FILL_GATE: f64 = 0.025;
const MIN_P_UP_FIRST_GATE: f64 = 0.42;
const STRESS_COST_BPS: f64 = 2.0;
const HARD_MIN_FILLS: usize = 500;
const HARD_MIN_MAKER_NET_BPS: f64 = 2.0;
const HARD_MAX_CONTROL_RATE: f64 = 0.10;
const HARD_MAX_DATE_SHARE: f64 = 0.30;
const HARD_MAX_SYMBOL_SHARE: f64 = 0.60;
const DISTANCE_GRID_X10: [i32; 5] = [5, 10, 15, 25, 40];
const WING_GRID_X10: [(i32, i32, usize); 4] = [
    (20, 10, 300),
    (30, 15, 900),
    (50, 25, 1_800),
    (80, 40, 1_800),
];
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct V14Config {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub doc_dir: PathBuf,
    pub run_tag: String,
    pub fee_bps: f64,
    pub symbols: String,
}

impl Default for V14Config {
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
pub struct V14Summary {
    pub run_tag: String,
    pub panel_rows: usize,
    pub fold_rows: usize,
    pub train_label_rows: usize,
    pub calibration_rows: usize,
    pub valid_decision_rows: usize,
    pub valid_trade_rows: usize,
    pub negative_control_rows: usize,
    pub diagnostic_rows: usize,
    pub primary_status: String,
    pub train_labels_csv: String,
    pub calibration_csv: String,
    pub params_csv: String,
    pub valid_decisions_csv: String,
    pub valid_trades_csv: String,
    pub summary_csv: String,
    pub negative_controls_csv: String,
    pub diagnostics_csv: String,
    pub failure_report_csv: String,
    pub manifest_csv: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    train_labels_csv: PathBuf,
    calibration_csv: PathBuf,
    params_csv: PathBuf,
    valid_decisions_csv: PathBuf,
    valid_trades_csv: PathBuf,
    summary_csv: PathBuf,
    negative_controls_csv: PathBuf,
    diagnostics_csv: PathBuf,
    failure_report_csv: PathBuf,
    manifest_csv: PathBuf,
    report_md: PathBuf,
    filter_params_csv: PathBuf,
}

impl Paths {
    fn new(config: &V14Config) -> Self {
        Self {
            train_labels_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_train_labels_{}.csv",
                config.run_tag
            )),
            calibration_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_calibration_{}.csv",
                config.run_tag
            )),
            params_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_params_{}.csv",
                config.run_tag
            )),
            valid_decisions_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_valid_decisions_{}.csv",
                config.run_tag
            )),
            valid_trades_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_valid_trades_{}.csv",
                config.run_tag
            )),
            summary_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_summary_{}.csv",
                config.run_tag
            )),
            negative_controls_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_negative_controls_{}.csv",
                config.run_tag
            )),
            diagnostics_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_diagnostics_{}.csv",
                config.run_tag
            )),
            failure_report_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_failure_report_{}.csv",
                config.run_tag
            )),
            manifest_csv: config.date_dir.join(format!(
                "bonk_v14_state_policy_manifest_{}.csv",
                config.run_tag
            )),
            report_md: config.doc_dir.join("v1-cex-v14-state-policy.md"),
            filter_params_csv: config
                .date_dir
                .join(format!("bonk_v10_filter_params_{}.csv", config.run_tag)),
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
    microprice_dev_bps: f64,
    center_price: f64,
    best_bid_price: Option<f64>,
    best_ask_price: Option<f64>,
    best_bid_amount: f64,
    best_ask_amount: f64,
    bid_depth_1: f64,
    ask_depth_1: f64,
    bid_depth_5: f64,
    ask_depth_5: f64,
    bid_depth_10: f64,
    ask_depth_10: f64,
    bid_depth_25: f64,
    ask_depth_25: f64,
    queue_imbalance_1: f64,
    queue_imbalance_5: f64,
    queue_imbalance_25: f64,
    mlofi_norm_l1: f64,
    mlofi_norm_l5: f64,
    mlofi_norm_l10: f64,
    mlofi_norm_l25: f64,
    mlofi_roll10_l1: f64,
    mlofi_roll10_l5: f64,
    mlofi_roll10_l10: f64,
    mlofi_roll10_l25: f64,
    trade_flow_imbalance: f64,
    trade_arrival_alignment: f64,
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
    queue_depletion_intensity: f64,
    replenish_intensity: f64,
    cancellation_withdrawal_intensity: f64,
    liquidity_shock_score: f64,
    rv30_bps: f64,
    sigma_bps: f64,
    vol_bucket: String,
    microprice_drift_bps: f64,
    cross_lagged_pressure: f64,
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
            microprice_dev_bps: row.microprice_dev_bps.and_then(finite).unwrap_or(0.0),
            center_price,
            best_bid_price: row.best_bid_price.and_then(finite),
            best_ask_price: row.best_ask_price.and_then(finite),
            best_bid_amount: row.best_bid_amount.and_then(finite).unwrap_or(0.0).max(0.0),
            best_ask_amount: row.best_ask_amount.and_then(finite).unwrap_or(0.0).max(0.0),
            bid_depth_1: row.bid_depth_1.max(0.0),
            ask_depth_1: row.ask_depth_1.max(0.0),
            bid_depth_5: row.bid_depth_5.max(0.0),
            ask_depth_5: row.ask_depth_5.max(0.0),
            bid_depth_10: row.bid_depth_10.max(0.0),
            ask_depth_10: row.ask_depth_10.max(0.0),
            bid_depth_25: row.bid_depth_25.max(0.0),
            ask_depth_25: row.ask_depth_25.max(0.0),
            queue_imbalance_1: row.queue_imbalance_1.and_then(finite).unwrap_or(0.0),
            queue_imbalance_5: row.queue_imbalance_5.and_then(finite).unwrap_or(0.0),
            queue_imbalance_25: row.queue_imbalance_25.and_then(finite).unwrap_or(0.0),
            mlofi_norm_l1: row.mlofi_norm_l1.and_then(finite).unwrap_or(0.0),
            mlofi_norm_l5: row.mlofi_norm_l5.and_then(finite).unwrap_or(0.0),
            mlofi_norm_l10: row.mlofi_norm_l10.and_then(finite).unwrap_or(0.0),
            mlofi_norm_l25: row.mlofi_norm_l25.and_then(finite).unwrap_or(0.0),
            mlofi_roll10_l1: finite(row.mlofi_roll10_l1).unwrap_or(0.0),
            mlofi_roll10_l5: finite(row.mlofi_roll10_l5).unwrap_or(0.0),
            mlofi_roll10_l10: finite(row.mlofi_roll10_l10).unwrap_or(0.0),
            mlofi_roll10_l25: finite(row.mlofi_roll10_l25).unwrap_or(0.0),
            trade_flow_imbalance: row.trade_flow_imbalance.and_then(finite).unwrap_or(0.0),
            trade_arrival_alignment: row.trade_arrival_alignment.and_then(finite).unwrap_or(0.0),
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
            queue_depletion_intensity: row
                .queue_depletion_intensity
                .and_then(finite)
                .unwrap_or(0.0)
                .max(0.0),
            replenish_intensity: row
                .replenish_intensity
                .and_then(finite)
                .unwrap_or(0.0)
                .max(0.0),
            cancellation_withdrawal_intensity: row
                .cancellation_withdrawal_intensity
                .and_then(finite)
                .unwrap_or(0.0)
                .max(0.0),
            liquidity_shock_score: row
                .liquidity_shock_score
                .and_then(finite)
                .unwrap_or(0.0)
                .max(0.0),
            rv30_bps: 0.0,
            sigma_bps: spread_bps.max(MIN_SIGMA_BPS),
            vol_bucket: "unfit".to_string(),
            microprice_drift_bps: 0.0,
            cross_lagged_pressure: 0.0,
        })
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

    fn pressure_score(&self) -> f64 {
        0.28 * self.mlofi_roll10_l10
            + 0.22 * self.mlofi_roll10_l5
            + 0.18 * self.queue_imbalance_25
            + 0.16 * self.trade_flow_imbalance
            + 0.16 * self.trade_arrival_alignment
    }

    fn total_depth_25(&self) -> f64 {
        self.bid_depth_25 + self.ask_depth_25
    }

    fn depth_curvature(&self) -> f64 {
        let near = self.bid_depth_5 + self.ask_depth_5;
        let far = self.bid_depth_25 + self.ask_depth_25;
        if far > 0.0 {
            (near / far).clamp(0.0, 5.0)
        } else {
            0.0
        }
    }

    fn depletion_pressure(&self) -> f64 {
        signed_ratio(
            self.depletion_ask_amount + self.execute_ask_amount,
            self.depletion_bid_amount + self.execute_bid_amount,
        )
    }

    fn replenish_absorption(&self) -> f64 {
        signed_ratio(self.replenish_bid_amount, self.replenish_ask_amount)
    }

    fn cancel_withdrawal_pressure(&self) -> f64 {
        signed_ratio(
            self.cancel_ask_amount + self.remove_ask_amount,
            self.cancel_bid_amount + self.remove_bid_amount,
        )
    }

    fn toxicity_proxy(&self) -> f64 {
        (self.trade_flow_imbalance.abs()
            + self.trade_arrival_alignment.abs()
            + self.liquidity_shock_score
            + 0.25 * self.queue_depletion_intensity
            + 0.25 * self.cancellation_withdrawal_intensity)
            .max(0.0)
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
struct StateSnapshot {
    full_key: String,
    parent_key: String,
    root_key: String,
    vol_bucket: String,
    spread_bucket: String,
    liquidity_bucket: String,
    pressure_bucket: String,
    toxicity_bucket: String,
    cross_bucket: String,
    micro_bucket: String,
    curvature_bucket: String,
    depletion_bucket: String,
    replenish_bucket: String,
    cancel_bucket: String,
    event_rv_bps: f64,
    pressure_score: f64,
    toxicity_proxy: f64,
    cross_lagged_pressure: f64,
}

impl StateSnapshot {
    fn from_row(row: &PanelRow) -> Self {
        let vol_bucket = row.vol_bucket.clone();
        let spread_bucket = bucket_3(row.spread_bps, 1.0, 3.0, "tight", "normal", "wide");
        let liquidity_bucket = if row.total_depth_25() < 10.0 {
            "thin"
        } else if row.total_depth_25() < 100.0 {
            "normal"
        } else {
            "deep"
        }
        .to_string();
        let pressure = row.pressure_score();
        let pressure_bucket = signed_bucket(pressure, 0.20, 0.75);
        let toxicity = row.toxicity_proxy();
        let toxicity_bucket = bucket_3(toxicity, 0.50, 1.50, "quiet", "mixed", "toxic");
        let cross_bucket = signed_bucket(row.cross_lagged_pressure, 0.20, 0.75);
        let micro_bucket = signed_bucket(
            row.microprice_dev_bps + row.microprice_drift_bps,
            0.25,
            1.00,
        );
        let curvature_bucket = bucket_3(
            row.depth_curvature(),
            0.20,
            0.55,
            "flat",
            "curved",
            "top_heavy",
        );
        let depletion_bucket = signed_bucket(row.depletion_pressure(), 0.10, 0.40);
        let replenish_bucket = signed_bucket(row.replenish_absorption(), 0.10, 0.40);
        let cancel_bucket = signed_bucket(row.cancel_withdrawal_pressure(), 0.10, 0.40);
        let full_key = format!(
            "vol={vol_bucket}|spread={spread_bucket}|liq={liquidity_bucket}|pressure={pressure_bucket}|tox={toxicity_bucket}|cross={cross_bucket}|micro={micro_bucket}|curv={curvature_bucket}|dep={depletion_bucket}|rep={replenish_bucket}|cancel={cancel_bucket}"
        );
        let parent_key = format!(
            "vol={vol_bucket}|spread={spread_bucket}|liq={liquidity_bucket}|pressure={pressure_bucket}|tox={toxicity_bucket}|cross={cross_bucket}"
        );
        let root_key = format!("vol={vol_bucket}|spread={spread_bucket}|liq={liquidity_bucket}");
        Self {
            full_key,
            parent_key,
            root_key,
            vol_bucket,
            spread_bucket,
            liquidity_bucket,
            pressure_bucket,
            toxicity_bucket,
            cross_bucket,
            micro_bucket,
            curvature_bucket,
            depletion_bucket,
            replenish_bucket,
            cancel_bucket,
            event_rv_bps: row.rv30_bps,
            pressure_score: pressure,
            toxicity_proxy: toxicity,
            cross_lagged_pressure: row.cross_lagged_pressure,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
enum FirstPassage {
    UpFirst,
    DownFirst,
    Timeout,
    NoFill,
}

impl FirstPassage {
    fn as_str(self) -> &'static str {
        match self {
            Self::UpFirst => "up_first",
            Self::DownFirst => "down_first",
            Self::Timeout => "timeout",
            Self::NoFill => "no_fill",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ExitDecision {
    StopLoss,
    TakeProfit,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
enum ControlType {
    TimestampShiftMinus300,
    TimestampShiftMinus60,
    TimestampShiftMinus30,
    TimestampShiftMinus5,
    TimestampShiftPlus5,
    TimestampShiftPlus30,
    TimestampShiftPlus60,
    TimestampShiftPlus300,
    SideFlip,
    WrongSymbolSameTime,
    WrongSymbolLaggedState,
    SurfaceShuffle,
    SkewFlip,
    WrongDateSurface,
    FutureVolLeakTest,
    RandomMarkerSameSupport,
    UpperLowerSwap,
}

impl ControlType {
    fn all() -> [Self; 17] {
        [
            Self::TimestampShiftMinus300,
            Self::TimestampShiftMinus60,
            Self::TimestampShiftMinus30,
            Self::TimestampShiftMinus5,
            Self::TimestampShiftPlus5,
            Self::TimestampShiftPlus30,
            Self::TimestampShiftPlus60,
            Self::TimestampShiftPlus300,
            Self::SideFlip,
            Self::WrongSymbolSameTime,
            Self::WrongSymbolLaggedState,
            Self::SurfaceShuffle,
            Self::SkewFlip,
            Self::WrongDateSurface,
            Self::FutureVolLeakTest,
            Self::RandomMarkerSameSupport,
            Self::UpperLowerSwap,
        ]
    }

    fn name(self) -> &'static str {
        match self {
            Self::TimestampShiftMinus300 => "timestamp_shift_minus_300s",
            Self::TimestampShiftMinus60 => "timestamp_shift_minus_60s",
            Self::TimestampShiftMinus30 => "timestamp_shift_minus_30s",
            Self::TimestampShiftMinus5 => "timestamp_shift_minus_5s",
            Self::TimestampShiftPlus5 => "timestamp_shift_plus_5s",
            Self::TimestampShiftPlus30 => "timestamp_shift_plus_30s",
            Self::TimestampShiftPlus60 => "timestamp_shift_plus_60s",
            Self::TimestampShiftPlus300 => "timestamp_shift_plus_300s",
            Self::SideFlip => "side_flip",
            Self::WrongSymbolSameTime => "wrong_symbol_same_time",
            Self::WrongSymbolLaggedState => "wrong_symbol_lagged_state",
            Self::SurfaceShuffle => "surface_shuffle",
            Self::SkewFlip => "skew_flip",
            Self::WrongDateSurface => "wrong_date_surface",
            Self::FutureVolLeakTest => "future_vol_leak_test",
            Self::RandomMarkerSameSupport => "random_marker_same_support",
            Self::UpperLowerSwap => "upper_lower_swap",
        }
    }

    fn is_control_only(self) -> bool {
        self == Self::FutureVolLeakTest
    }

    fn shift_seconds(self) -> Option<i64> {
        match self {
            Self::TimestampShiftMinus300 => Some(-300),
            Self::TimestampShiftMinus60 => Some(-60),
            Self::TimestampShiftMinus30 => Some(-30),
            Self::TimestampShiftMinus5 => Some(-5),
            Self::TimestampShiftPlus5 => Some(5),
            Self::TimestampShiftPlus30 => Some(30),
            Self::TimestampShiftPlus60 => Some(60),
            Self::TimestampShiftPlus300 => Some(300),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct TrainLabelRow {
    run_tag: String,
    fold: String,
    symbol: String,
    date: String,
    label_source_phase: String,
    anchor_local_timestamp: u64,
    anchor_event_index: usize,
    side: String,
    marker_distance_bps: f64,
    take_profit_bps: f64,
    stop_loss_bps: f64,
    hold_events: usize,
    state_key: String,
    parent_state_key: String,
    root_state_key: String,
    vol_bucket: String,
    spread_bucket: String,
    liquidity_bucket: String,
    pressure_bucket: String,
    toxicity_bucket: String,
    cross_bucket: String,
    micro_bucket: String,
    curvature_bucket: String,
    depletion_bucket: String,
    replenish_bucket: String,
    cancel_bucket: String,
    pressure_score: f64,
    toxicity_proxy: f64,
    event_rv_bps: f64,
    cross_lagged_pressure: f64,
    filled_with_evidence: bool,
    first_passage: String,
    entry_local_timestamp: Option<u64>,
    exit_local_timestamp: Option<u64>,
    marker_price: f64,
    entry_touch_mid_price: Option<f64>,
    exit_price: Option<f64>,
    mfe_bps: f64,
    mae_bps: f64,
    timeout_return_bps: f64,
    gross_bps: f64,
    maker_cost_bps: f64,
    maker_net_bps: f64,
    stress_maker_net_bps: f64,
    fill_price_semantics: String,
    guardrail: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct CalKey {
    fold: String,
    symbol_scope: String,
    side_sign: i8,
    distance_x10: i32,
    take_profit_x10: i32,
    stop_loss_x10: i32,
    hold_events: usize,
    state_key: String,
    fallback_level: u8,
}

#[derive(Debug, Clone, Default)]
struct CalStats {
    support: usize,
    fills: usize,
    up_first: usize,
    down_first: usize,
    timeout: usize,
    gross_sum: f64,
    net_sum: f64,
    stress_net_sum: f64,
    timeout_ret_sum: f64,
    timeout_ret_count: usize,
    net_values: Vec<f64>,
}

impl CalStats {
    fn add(&mut self, label: &TrainLabelRow) {
        self.support += 1;
        if label.filled_with_evidence {
            self.fills += 1;
        }
        match label.first_passage.as_str() {
            "up_first" => self.up_first += 1,
            "down_first" => self.down_first += 1,
            "timeout" => {
                self.timeout += 1;
                self.timeout_ret_sum += label.timeout_return_bps;
                self.timeout_ret_count += 1;
            }
            _ => {}
        }
        self.gross_sum += label.gross_bps;
        self.net_sum += label.maker_net_bps;
        self.stress_net_sum += label.stress_maker_net_bps;
        self.net_values.push(label.maker_net_bps);
    }

    fn to_cell(&self) -> CalibrationCell {
        let support = self.support.max(1);
        let fills = self.fills.max(1);
        CalibrationCell {
            support: self.support,
            fills: self.fills,
            p_fill: self.fills as f64 / support as f64,
            p_up_first: self.up_first as f64 / fills as f64,
            p_down_first: self.down_first as f64 / fills as f64,
            p_timeout: self.timeout as f64 / fills as f64,
            e_timeout_ret_bps: if self.timeout_ret_count == 0 {
                0.0
            } else {
                self.timeout_ret_sum / self.timeout_ret_count as f64
            },
            e_gross_bps: self.gross_sum / support as f64,
            e_net_bps: self.net_sum / support as f64,
            e_stress_net_bps: self.stress_net_sum / support as f64,
            tail_es_bps: expected_shortfall(&self.net_values, 0.05).unwrap_or(0.0),
        }
    }
}

#[derive(Debug, Clone)]
struct CalibrationCell {
    support: usize,
    fills: usize,
    p_fill: f64,
    p_up_first: f64,
    p_down_first: f64,
    p_timeout: f64,
    e_timeout_ret_bps: f64,
    e_gross_bps: f64,
    e_net_bps: f64,
    e_stress_net_bps: f64,
    tail_es_bps: f64,
}

#[derive(Debug, Clone)]
struct CalibrationBook {
    map: BTreeMap<CalKey, CalibrationCell>,
    rows: Vec<CalibrationRow>,
}

impl CalibrationBook {
    fn resolve(
        &self,
        fold: &str,
        symbol: &str,
        side_sign: i8,
        distance_x10: i32,
        take_profit_x10: i32,
        stop_loss_x10: i32,
        hold_events: usize,
        state: &StateSnapshot,
    ) -> Option<(CalibrationCell, String, u8, String)> {
        let candidates = [
            (
                symbol.to_string(),
                state.full_key.clone(),
                0u8,
                "symbol_full",
            ),
            (
                symbol.to_string(),
                state.parent_key.clone(),
                1u8,
                "symbol_parent",
            ),
            (
                symbol.to_string(),
                state.root_key.clone(),
                2u8,
                "symbol_root",
            ),
            (
                "*".to_string(),
                state.root_key.clone(),
                3u8,
                "fold_symbol_pool_root",
            ),
        ];
        for (symbol_scope, state_key, fallback_level, source) in candidates {
            let key = CalKey {
                fold: fold.to_string(),
                symbol_scope,
                side_sign,
                distance_x10,
                take_profit_x10,
                stop_loss_x10,
                hold_events,
                state_key: state_key.clone(),
                fallback_level,
            };
            if let Some(cell) = self.map.get(&key) {
                if cell.support >= MIN_SUPPORT {
                    return Some((cell.clone(), state_key, fallback_level, source.to_string()));
                }
            }
        }
        None
    }
}

#[derive(Debug, Clone, Serialize)]
struct CalibrationRow {
    run_tag: String,
    fold: String,
    symbol_scope: String,
    state_key: String,
    fallback_level: u8,
    side: String,
    marker_distance_bps: f64,
    take_profit_bps: f64,
    stop_loss_bps: f64,
    hold_events: usize,
    support: usize,
    fills: usize,
    p_fill: f64,
    p_up_first: f64,
    p_down_first: f64,
    p_timeout: f64,
    e_timeout_ret_bps: f64,
    e_gross_bps: f64,
    e_net_bps: f64,
    e_stress_net_bps: f64,
    tail_es_bps: f64,
    min_support: usize,
    calibration_source_phase: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct ParamsRow {
    run_tag: String,
    parameter: String,
    value: String,
    source_phase: String,
    frozen_for_validation: bool,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct PolicySetup {
    decision_id: usize,
    fold: String,
    date: String,
    symbol: String,
    anchor_pos: usize,
    anchor_local_timestamp: u64,
    side_sign: i8,
    distance_x10: i32,
    take_profit_x10: i32,
    stop_loss_x10: i32,
    hold_events: usize,
    state_key: String,
    fallback_level: u8,
    support: usize,
    p_fill: f64,
    p_up_first: f64,
    p_down_first: f64,
    expected_net_bps: f64,
    j_score_bps: f64,
}

#[derive(Debug, Clone, Serialize)]
struct DecisionRow {
    run_tag: String,
    decision_id: usize,
    fold: String,
    phase: String,
    date: String,
    symbol: String,
    anchor_local_timestamp: u64,
    anchor_event_index: usize,
    action: String,
    skip_reason: String,
    side: Option<String>,
    marker_distance_bps: Option<f64>,
    take_profit_bps: Option<f64>,
    stop_loss_bps: Option<f64>,
    hold_events: Option<usize>,
    state_key: String,
    parent_state_key: String,
    root_state_key: String,
    resolved_state_key: Option<String>,
    fallback_level: Option<u8>,
    calibration_source: Option<String>,
    support: Option<usize>,
    p_fill: Option<f64>,
    p_up_first: Option<f64>,
    p_down_first: Option<f64>,
    p_timeout: Option<f64>,
    expected_net_bps: Option<f64>,
    j_score_bps: Option<f64>,
    maker_cost_bps: Option<f64>,
    toxicity_penalty_bps: Option<f64>,
    tail_penalty_bps: Option<f64>,
    queue_reset_cost_bps: Option<f64>,
    frozen_calibration: bool,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct TradeRow {
    run_tag: String,
    decision_id: usize,
    fold: String,
    phase: String,
    date: String,
    symbol: String,
    side: String,
    strategy_id: String,
    control_type: String,
    control_only: bool,
    anchor_local_timestamp: u64,
    anchor_event_index: usize,
    marker_distance_bps: f64,
    take_profit_bps: f64,
    stop_loss_bps: f64,
    hold_events: usize,
    state_key: String,
    fallback_level: u8,
    support: usize,
    p_fill: f64,
    p_up_first: f64,
    p_down_first: f64,
    expected_net_bps: f64,
    j_score_bps: f64,
    fill_status: String,
    exit_reason: String,
    entry_local_timestamp: Option<u64>,
    exit_local_timestamp: Option<u64>,
    marker_price: f64,
    entry_touch_mid_price: Option<f64>,
    exit_price: Option<f64>,
    gross_bps: Option<f64>,
    maker_cost_bps: Option<f64>,
    maker_net_bps: Option<f64>,
    stress_maker_net_bps: Option<f64>,
    mfe_bps: Option<f64>,
    mae_bps: Option<f64>,
    fill_price_semantics: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct SummaryRow {
    run_tag: String,
    summary_scope: String,
    symbol: String,
    setups: usize,
    fills: usize,
    no_fills: usize,
    fill_rate: f64,
    gross_bps_mean: Option<f64>,
    maker_net_bps_mean: Option<f64>,
    stress_maker_net_bps_mean: Option<f64>,
    winsorized_top1_maker_net_bps_mean: Option<f64>,
    win_rate: Option<f64>,
    stop_loss_rate: Option<f64>,
    take_profit_rate: Option<f64>,
    timeout_rate: Option<f64>,
    max_date_share: Option<f64>,
    max_symbol_share: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    leave_one_day_min_net_bps: Option<f64>,
    leave_one_hour_min_net_bps: Option<f64>,
    leave_one_symbol_min_net_bps: Option<f64>,
    pass_fills: bool,
    pass_maker_net: bool,
    pass_stress_net: bool,
    pass_winsorized: bool,
    pass_controls: bool,
    pass_date_concentration: bool,
    pass_symbol_concentration: bool,
    pass_leave_one_out: bool,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct NegativeControlRow {
    run_tag: String,
    control_type: String,
    strategy_id: String,
    control_only: bool,
    setups: usize,
    fills: usize,
    fill_rate: f64,
    gross_bps_mean: Option<f64>,
    maker_net_bps_mean: Option<f64>,
    stress_maker_net_bps_mean: Option<f64>,
    winsorized_top1_maker_net_bps_mean: Option<f64>,
    max_date_share: Option<f64>,
    max_symbol_share: Option<f64>,
    abs_net_ge_base_abs_net: Option<bool>,
    control_note: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct DiagnosticRow {
    run_tag: String,
    decision_id: usize,
    fold: String,
    date: String,
    symbol: String,
    side: String,
    state_key: String,
    fallback_level: u8,
    support: usize,
    p_fill: f64,
    p_up_first: f64,
    p_down_first: f64,
    expected_net_bps: f64,
    j_score_bps: f64,
    fill_status: String,
    exit_reason: String,
    gross_bps: Option<f64>,
    maker_net_bps: Option<f64>,
    paired_note: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct FailureReportRow {
    run_tag: String,
    primary_status: String,
    evidence: String,
    blockers: String,
    setups: usize,
    fills: usize,
    maker_net_bps_mean: Option<f64>,
    stress_maker_net_bps_mean: Option<f64>,
    winsorized_top1_maker_net_bps_mean: Option<f64>,
    max_date_share: Option<f64>,
    max_symbol_share: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    leave_one_day_min_net_bps: Option<f64>,
    leave_one_hour_min_net_bps: Option<f64>,
    leave_one_symbol_min_net_bps: Option<f64>,
    hard_gate_fills: bool,
    hard_gate_maker_net: bool,
    hard_gate_stress_net: bool,
    hard_gate_winsorized: bool,
    hard_gate_controls: bool,
    hard_gate_date_share: bool,
    hard_gate_symbol_share: bool,
    hard_gate_leave_one_out: bool,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct ManifestRow {
    run_tag: String,
    artifact: String,
    path: String,
    rows: usize,
    status: String,
    guardrail: String,
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

#[derive(Debug, Clone)]
struct SimOutcome {
    fill_status: String,
    exit_reason: String,
    entry_pos: Option<usize>,
    exit_pos: Option<usize>,
    marker_price: f64,
    entry_touch_mid_price: Option<f64>,
    exit_price: Option<f64>,
    gross_bps: Option<f64>,
    maker_cost_bps: Option<f64>,
    maker_net_bps: Option<f64>,
    stress_maker_net_bps: Option<f64>,
    mfe_bps: Option<f64>,
    mae_bps: Option<f64>,
}

#[derive(Debug, Clone, Default)]
struct TradeStats {
    setups: usize,
    fills: usize,
    gross: Vec<f64>,
    net: Vec<f64>,
    stress_net: Vec<f64>,
    stop_loss: usize,
    take_profit: usize,
    timeout: usize,
    date_counts: BTreeMap<String, usize>,
    symbol_counts: BTreeMap<String, usize>,
    hour_counts: BTreeMap<String, usize>,
}

pub fn run_v14(config: &V14Config) -> Result<V14Summary> {
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
    enrich_cross_lagged_state(&mut rows);
    let by_symbol = rows_by_symbol(&rows);

    let mut train_labels = Vec::new();
    let mut calibration = CalibrationBook {
        map: BTreeMap::new(),
        rows: Vec::new(),
    };
    let mut decisions = Vec::new();
    let mut trades = Vec::new();
    let mut controls = Vec::new();
    let params = build_params_rows(config);

    if audit.blockers.is_empty() {
        train_labels = build_train_labels(config, &folds, &by_symbol);
        calibration = build_calibration(config, &train_labels);
        let replay = replay_validation(config, &folds, &by_symbol, &calibration);
        decisions = replay.0;
        let setups = replay.1;
        trades = simulate_setups(config, &by_symbol, &setups, "base", false);
        controls = build_negative_control_rows(config, &by_symbol, &setups, &trades);
    }

    let summary_rows = build_summary_rows(config, &trades, &controls);
    let failure = build_failure_report(&config.run_tag, &audit, &summary_rows);
    let diagnostics = build_diagnostics(config, &trades);
    let manifest = build_manifest(
        config,
        &paths,
        &train_labels,
        &calibration.rows,
        &params,
        &decisions,
        &trades,
        &summary_rows,
        &controls,
        &diagnostics,
        &failure,
    );

    write_csv_atomic(&paths.train_labels_csv, &train_labels)?;
    write_csv_atomic(&paths.calibration_csv, &calibration.rows)?;
    write_csv_atomic(&paths.params_csv, &params)?;
    write_csv_atomic(&paths.valid_decisions_csv, &decisions)?;
    write_csv_atomic(&paths.valid_trades_csv, &trades)?;
    write_csv_atomic(&paths.summary_csv, &summary_rows)?;
    write_csv_atomic(&paths.negative_controls_csv, &controls)?;
    write_csv_atomic(&paths.diagnostics_csv, &diagnostics)?;
    write_csv_atomic(&paths.failure_report_csv, &[failure.clone()])?;
    write_csv_atomic(&paths.manifest_csv, &manifest)?;
    write_report(
        config,
        &paths,
        &audit,
        &folds,
        &train_labels,
        &calibration.rows,
        &decisions,
        &trades,
        &summary_rows,
        &controls,
        &failure,
    )?;

    Ok(V14Summary {
        run_tag: config.run_tag.clone(),
        panel_rows: audit.panel_rows,
        fold_rows: folds.len(),
        train_label_rows: train_labels.len(),
        calibration_rows: calibration.rows.len(),
        valid_decision_rows: decisions.len(),
        valid_trade_rows: trades.len(),
        negative_control_rows: controls.len(),
        diagnostic_rows: diagnostics.len(),
        primary_status: failure.primary_status,
        train_labels_csv: path_string(&paths.train_labels_csv),
        calibration_csv: path_string(&paths.calibration_csv),
        params_csv: path_string(&paths.params_csv),
        valid_decisions_csv: path_string(&paths.valid_decisions_csv),
        valid_trades_csv: path_string(&paths.valid_trades_csv),
        summary_csv: path_string(&paths.summary_csv),
        negative_controls_csv: path_string(&paths.negative_controls_csv),
        diagnostics_csv: path_string(&paths.diagnostics_csv),
        failure_report_csv: path_string(&paths.failure_report_csv),
        manifest_csv: path_string(&paths.manifest_csv),
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

fn read_panel_rows(config: &V14Config, symbols: &[String]) -> Result<(Vec<PanelRow>, InputAudit)> {
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
                        rows[idx].microprice_drift_bps = ret;
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
            rows[idx].vol_bucket = classify_vol_state(rows[idx].sigma_bps).to_string();
            prev_center = Some(rows[idx].center_price);
        }
        start = end;
    }
}

fn enrich_cross_lagged_state(rows: &mut [PanelRow]) {
    let mut order = (0..rows.len()).collect::<Vec<_>>();
    order.sort_by(|a, b| {
        rows[*a]
            .local_timestamp
            .cmp(&rows[*b].local_timestamp)
            .then_with(|| rows[*a].symbol.cmp(&rows[*b].symbol))
    });
    let mut latest = BTreeMap::<String, f64>::new();
    let mut start = 0usize;
    while start < order.len() {
        let ts = rows[order[start]].local_timestamp;
        let mut end = start + 1;
        while end < order.len() && rows[order[end]].local_timestamp == ts {
            end += 1;
        }
        for idx in &order[start..end] {
            let symbol = rows[*idx].symbol.clone();
            let mut values = latest
                .iter()
                .filter(|(other, _)| other.as_str() != symbol)
                .map(|(_, value)| *value)
                .collect::<Vec<_>>();
            rows[*idx].cross_lagged_pressure = mean(&values).unwrap_or(0.0);
            values.clear();
        }
        for idx in &order[start..end] {
            latest.insert(rows[*idx].symbol.clone(), rows[*idx].pressure_score());
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

fn build_train_labels(
    config: &V14Config,
    folds: &[FoldSpec],
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
) -> Vec<TrainLabelRow> {
    let mut out = Vec::new();
    for fold in folds {
        let Some(rows) = by_symbol.get(&fold.symbol) else {
            continue;
        };
        let anchors = rows
            .iter()
            .enumerate()
            .filter(|(_, row)| {
                row.factor_eligible
                    && row.local_timestamp >= fold.train_start
                    && row.local_timestamp <= fold.train_end
            })
            .map(|(pos, _)| pos)
            .collect::<Vec<_>>();
        for pos in sample_positions(&anchors, MAX_TRAIN_ANCHORS_PER_FOLD_SYMBOL) {
            let state = StateSnapshot::from_row(rows[pos]);
            for side_sign in [1i8, -1i8] {
                for distance_x10 in DISTANCE_GRID_X10 {
                    for (take_profit_x10, stop_loss_x10, hold_events) in WING_GRID_X10 {
                        if stop_loss_x10 as f64 / take_profit_x10 as f64 > 1.5 {
                            continue;
                        }
                        out.push(label_candidate(
                            config,
                            fold,
                            rows,
                            pos,
                            side_sign,
                            distance_x10,
                            take_profit_x10,
                            stop_loss_x10,
                            hold_events,
                            &state,
                        ));
                    }
                }
            }
        }
    }
    out
}

#[allow(clippy::too_many_arguments)]
fn label_candidate(
    config: &V14Config,
    fold: &FoldSpec,
    rows: &[&PanelRow],
    anchor_pos: usize,
    side_sign: i8,
    distance_x10: i32,
    take_profit_x10: i32,
    stop_loss_x10: i32,
    hold_events: usize,
    state: &StateSnapshot,
) -> TrainLabelRow {
    let anchor = rows[anchor_pos];
    let distance_bps = x10_to_bps(distance_x10);
    let take_profit_bps = x10_to_bps(take_profit_x10);
    let stop_loss_bps = x10_to_bps(stop_loss_x10);
    let marker_price = marker_price(anchor.center_price, side_sign, distance_bps);
    let mut first_passage = FirstPassage::NoFill;
    let mut entry_pos = None::<usize>;
    let mut exit_pos = None::<usize>;
    let mut entry_touch_mid_price = None::<f64>;
    let mut exit_price = None::<f64>;
    let mut gross_bps = 0.0;
    let mut timeout_return_bps = 0.0;
    let mut mfe_bps = 0.0;
    let mut mae_bps = 0.0;
    let maker_cost = config.fee_bps + 0.25 * anchor.spread_bps;

    let fill_end = rows
        .len()
        .min(anchor_pos.saturating_add(MAX_FILL_WAIT_EVENTS + 1));
    for pos in anchor_pos.saturating_add(1)..fill_end {
        let row = rows[pos];
        if marker_touch_and_evidence(row, marker_price, side_sign) {
            entry_pos = Some(pos);
            entry_touch_mid_price = Some(row.mid_price);
            break;
        }
    }

    if let Some(fill_pos) = entry_pos {
        let hold_end = rows.len().min(fill_pos.saturating_add(hold_events + 1));
        let mut last_pos = fill_pos;
        for pos in fill_pos.saturating_add(1)..hold_end {
            let row = rows[pos];
            last_pos = pos;
            update_mfe_mae(
                row.mid_price,
                marker_price,
                side_sign,
                &mut mfe_bps,
                &mut mae_bps,
            );
            if let Some(exit) = evaluate_first_passage(
                row.mid_price,
                marker_price,
                side_sign,
                take_profit_bps,
                stop_loss_bps,
            ) {
                match exit {
                    ExitDecision::StopLoss => {
                        first_passage = FirstPassage::DownFirst;
                        exit_price = Some(
                            marker_price * (1.0 - side_sign as f64 * stop_loss_bps / 10_000.0),
                        );
                    }
                    ExitDecision::TakeProfit => {
                        first_passage = FirstPassage::UpFirst;
                        exit_price = Some(
                            marker_price * (1.0 + side_sign as f64 * take_profit_bps / 10_000.0),
                        );
                    }
                }
                exit_pos = Some(pos);
                break;
            }
        }
        if first_passage == FirstPassage::NoFill {
            first_passage = FirstPassage::Timeout;
            let row = rows.get(last_pos).copied().unwrap_or(rows[fill_pos]);
            exit_price = Some(row.mid_price);
            exit_pos = Some(last_pos);
            timeout_return_bps =
                side_sign as f64 * (row.mid_price - marker_price) / marker_price * 10_000.0;
        }
        let px = exit_price.unwrap_or(marker_price);
        gross_bps = side_sign as f64 * (px - marker_price) / marker_price * 10_000.0;
    }

    TrainLabelRow {
        run_tag: config.run_tag.clone(),
        fold: fold.fold.clone(),
        symbol: fold.symbol.clone(),
        date: anchor.date.clone(),
        label_source_phase: "train".to_string(),
        anchor_local_timestamp: anchor.local_timestamp,
        anchor_event_index: anchor.event_index,
        side: side_name(side_sign).to_string(),
        marker_distance_bps: distance_bps,
        take_profit_bps,
        stop_loss_bps,
        hold_events,
        state_key: state.full_key.clone(),
        parent_state_key: state.parent_key.clone(),
        root_state_key: state.root_key.clone(),
        vol_bucket: state.vol_bucket.clone(),
        spread_bucket: state.spread_bucket.clone(),
        liquidity_bucket: state.liquidity_bucket.clone(),
        pressure_bucket: state.pressure_bucket.clone(),
        toxicity_bucket: state.toxicity_bucket.clone(),
        cross_bucket: state.cross_bucket.clone(),
        micro_bucket: state.micro_bucket.clone(),
        curvature_bucket: state.curvature_bucket.clone(),
        depletion_bucket: state.depletion_bucket.clone(),
        replenish_bucket: state.replenish_bucket.clone(),
        cancel_bucket: state.cancel_bucket.clone(),
        pressure_score: state.pressure_score,
        toxicity_proxy: state.toxicity_proxy,
        event_rv_bps: state.event_rv_bps,
        cross_lagged_pressure: state.cross_lagged_pressure,
        filled_with_evidence: entry_pos.is_some(),
        first_passage: first_passage.as_str().to_string(),
        entry_local_timestamp: entry_pos.map(|pos| rows[pos].local_timestamp),
        exit_local_timestamp: exit_pos.map(|pos| rows[pos].local_timestamp),
        marker_price,
        entry_touch_mid_price,
        exit_price,
        mfe_bps,
        mae_bps,
        timeout_return_bps,
        gross_bps,
        maker_cost_bps: if entry_pos.is_some() { maker_cost } else { 0.0 },
        maker_net_bps: if entry_pos.is_some() {
            gross_bps - maker_cost
        } else {
            0.0
        },
        stress_maker_net_bps: if entry_pos.is_some() {
            gross_bps - maker_cost - STRESS_COST_BPS
        } else {
            0.0
        },
        fill_price_semantics: "entry_price_is_marker_distance_from_anchor_center_not_touch_mid"
            .to_string(),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn build_calibration(config: &V14Config, labels: &[TrainLabelRow]) -> CalibrationBook {
    let mut stats = BTreeMap::<CalKey, CalStats>::new();
    for label in labels {
        let Some(side_sign) = side_sign_from_name(&label.side) else {
            continue;
        };
        let distance_x10 = bps_to_x10(label.marker_distance_bps);
        let tp_x10 = bps_to_x10(label.take_profit_bps);
        let sl_x10 = bps_to_x10(label.stop_loss_bps);
        let keys = [
            (label.symbol.clone(), label.state_key.clone(), 0u8),
            (label.symbol.clone(), label.parent_state_key.clone(), 1u8),
            (label.symbol.clone(), label.root_state_key.clone(), 2u8),
            ("*".to_string(), label.root_state_key.clone(), 3u8),
        ];
        for (symbol_scope, state_key, fallback_level) in keys {
            let key = CalKey {
                fold: label.fold.clone(),
                symbol_scope,
                side_sign,
                distance_x10,
                take_profit_x10: tp_x10,
                stop_loss_x10: sl_x10,
                hold_events: label.hold_events,
                state_key,
                fallback_level,
            };
            stats.entry(key).or_default().add(label);
        }
    }

    let mut map = BTreeMap::new();
    let mut rows = Vec::new();
    for (key, stat) in stats {
        let cell = stat.to_cell();
        rows.push(CalibrationRow {
            run_tag: config.run_tag.clone(),
            fold: key.fold.clone(),
            symbol_scope: key.symbol_scope.clone(),
            state_key: key.state_key.clone(),
            fallback_level: key.fallback_level,
            side: side_name(key.side_sign).to_string(),
            marker_distance_bps: x10_to_bps(key.distance_x10),
            take_profit_bps: x10_to_bps(key.take_profit_x10),
            stop_loss_bps: x10_to_bps(key.stop_loss_x10),
            hold_events: key.hold_events,
            support: cell.support,
            fills: cell.fills,
            p_fill: cell.p_fill,
            p_up_first: cell.p_up_first,
            p_down_first: cell.p_down_first,
            p_timeout: cell.p_timeout,
            e_timeout_ret_bps: cell.e_timeout_ret_bps,
            e_gross_bps: cell.e_gross_bps,
            e_net_bps: cell.e_net_bps,
            e_stress_net_bps: cell.e_stress_net_bps,
            tail_es_bps: cell.tail_es_bps,
            min_support: MIN_SUPPORT,
            calibration_source_phase: "train".to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
        map.insert(key, cell);
    }
    CalibrationBook { map, rows }
}

fn replay_validation(
    config: &V14Config,
    folds: &[FoldSpec],
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
    calibration: &CalibrationBook,
) -> (Vec<DecisionRow>, Vec<PolicySetup>) {
    let mut decisions = Vec::new();
    let mut setups = Vec::new();
    let mut decision_id = 1usize;
    for fold in folds {
        let Some(rows) = by_symbol.get(&fold.symbol) else {
            continue;
        };
        let anchors = rows
            .iter()
            .enumerate()
            .filter(|(_, row)| {
                row.factor_eligible
                    && row.local_timestamp >= fold.valid_start
                    && row.local_timestamp <= fold.valid_end
            })
            .map(|(pos, _)| pos)
            .collect::<Vec<_>>();
        let anchors = sample_positions(&anchors, MAX_VALID_ANCHORS_PER_FOLD_SYMBOL);
        let mut next_pos = 0usize;
        for pos in anchors {
            if pos < next_pos {
                continue;
            }
            let row = rows[pos];
            let state = StateSnapshot::from_row(row);
            let best = choose_best_candidate(config, fold, &state, row, calibration);
            let (decision, setup) =
                decision_from_candidate(config, decision_id, fold, rows, pos, &state, best);
            if setup.is_some() {
                next_pos = pos.saturating_add(VALID_EVENT_GAP);
            }
            decisions.push(decision);
            if let Some(setup) = setup {
                setups.push(setup);
            }
            decision_id += 1;
        }
    }
    (decisions, setups)
}

#[derive(Debug, Clone)]
struct CandidateChoice {
    side_sign: i8,
    distance_x10: i32,
    take_profit_x10: i32,
    stop_loss_x10: i32,
    hold_events: usize,
    cell: CalibrationCell,
    resolved_state_key: String,
    fallback_level: u8,
    calibration_source: String,
    expected_net_bps: f64,
    j_score_bps: f64,
    maker_cost_bps: f64,
    toxicity_penalty_bps: f64,
    tail_penalty_bps: f64,
    queue_reset_cost_bps: f64,
}

fn choose_best_candidate(
    config: &V14Config,
    fold: &FoldSpec,
    state: &StateSnapshot,
    row: &PanelRow,
    calibration: &CalibrationBook,
) -> Option<CandidateChoice> {
    let mut best = None::<CandidateChoice>;
    for side_sign in [1i8, -1i8] {
        for distance_x10 in DISTANCE_GRID_X10 {
            for (take_profit_x10, stop_loss_x10, hold_events) in WING_GRID_X10 {
                let Some((cell, resolved_state_key, fallback_level, source)) = calibration.resolve(
                    &fold.fold,
                    &fold.symbol,
                    side_sign,
                    distance_x10,
                    take_profit_x10,
                    stop_loss_x10,
                    hold_events,
                    state,
                ) else {
                    continue;
                };
                let maker_cost = config.fee_bps + 0.25 * row.spread_bps;
                let toxicity_penalty = toxicity_penalty_bps(state, side_sign);
                let tail_penalty = (-cell.tail_es_bps).max(0.0) * 0.15;
                let queue_reset_cost =
                    queue_reset_cost_bps(x10_to_bps(distance_x10), row.spread_bps, row.sigma_bps);
                let j_score = cell.p_fill
                    * (cell.p_up_first * x10_to_bps(take_profit_x10)
                        - cell.p_down_first * x10_to_bps(stop_loss_x10)
                        + cell.p_timeout * cell.e_timeout_ret_bps)
                    - maker_cost
                    - toxicity_penalty
                    - tail_penalty
                    - queue_reset_cost;
                let expected_net =
                    cell.e_net_bps - toxicity_penalty - tail_penalty - queue_reset_cost;
                let candidate = CandidateChoice {
                    side_sign,
                    distance_x10,
                    take_profit_x10,
                    stop_loss_x10,
                    hold_events,
                    cell,
                    resolved_state_key,
                    fallback_level,
                    calibration_source: source,
                    expected_net_bps: expected_net,
                    j_score_bps: j_score,
                    maker_cost_bps: maker_cost,
                    toxicity_penalty_bps: toxicity_penalty,
                    tail_penalty_bps: tail_penalty,
                    queue_reset_cost_bps: queue_reset_cost,
                };
                if best
                    .as_ref()
                    .map(|current| candidate.j_score_bps > current.j_score_bps)
                    .unwrap_or(true)
                {
                    best = Some(candidate);
                }
            }
        }
    }
    best
}

fn decision_from_candidate(
    config: &V14Config,
    decision_id: usize,
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    state: &StateSnapshot,
    best: Option<CandidateChoice>,
) -> (DecisionRow, Option<PolicySetup>) {
    let row = rows[pos];
    let Some(best) = best else {
        return (
            DecisionRow {
                run_tag: config.run_tag.clone(),
                decision_id,
                fold: fold.fold.clone(),
                phase: "frozen_validation".to_string(),
                date: row.date.clone(),
                symbol: row.symbol.clone(),
                anchor_local_timestamp: row.local_timestamp,
                anchor_event_index: row.event_index,
                action: "Skip".to_string(),
                skip_reason: "insufficient_support".to_string(),
                side: None,
                marker_distance_bps: None,
                take_profit_bps: None,
                stop_loss_bps: None,
                hold_events: None,
                state_key: state.full_key.clone(),
                parent_state_key: state.parent_key.clone(),
                root_state_key: state.root_key.clone(),
                resolved_state_key: None,
                fallback_level: None,
                calibration_source: None,
                support: None,
                p_fill: None,
                p_up_first: None,
                p_down_first: None,
                p_timeout: None,
                expected_net_bps: None,
                j_score_bps: None,
                maker_cost_bps: None,
                toxicity_penalty_bps: None,
                tail_penalty_bps: None,
                queue_reset_cost_bps: None,
                frozen_calibration: true,
                guardrail: GUARDRAIL.to_string(),
            },
            None,
        );
    };

    let skip_reason = if best.cell.support < MIN_SUPPORT {
        "insufficient_support"
    } else if best.expected_net_bps < config.fee_bps + 1.0 {
        "expected_net_below_fee_plus_one"
    } else if best.cell.p_fill < MIN_P_FILL_GATE {
        "p_fill_below_train_gate"
    } else if best.cell.p_up_first < MIN_P_UP_FIRST_GATE {
        "p_up_first_below_train_gate"
    } else {
        ""
    };
    let enter = skip_reason.is_empty();
    let setup = enter.then(|| PolicySetup {
        decision_id,
        fold: fold.fold.clone(),
        date: row.date.clone(),
        symbol: row.symbol.clone(),
        anchor_pos: pos,
        anchor_local_timestamp: row.local_timestamp,
        side_sign: best.side_sign,
        distance_x10: best.distance_x10,
        take_profit_x10: best.take_profit_x10,
        stop_loss_x10: best.stop_loss_x10,
        hold_events: best.hold_events,
        state_key: best.resolved_state_key.clone(),
        fallback_level: best.fallback_level,
        support: best.cell.support,
        p_fill: best.cell.p_fill,
        p_up_first: best.cell.p_up_first,
        p_down_first: best.cell.p_down_first,
        expected_net_bps: best.expected_net_bps,
        j_score_bps: best.j_score_bps,
    });
    (
        DecisionRow {
            run_tag: config.run_tag.clone(),
            decision_id,
            fold: fold.fold.clone(),
            phase: "frozen_validation".to_string(),
            date: row.date.clone(),
            symbol: row.symbol.clone(),
            anchor_local_timestamp: row.local_timestamp,
            anchor_event_index: row.event_index,
            action: if enter { "Enter" } else { "Skip" }.to_string(),
            skip_reason: skip_reason.to_string(),
            side: Some(side_name(best.side_sign).to_string()),
            marker_distance_bps: Some(x10_to_bps(best.distance_x10)),
            take_profit_bps: Some(x10_to_bps(best.take_profit_x10)),
            stop_loss_bps: Some(x10_to_bps(best.stop_loss_x10)),
            hold_events: Some(best.hold_events),
            state_key: state.full_key.clone(),
            parent_state_key: state.parent_key.clone(),
            root_state_key: state.root_key.clone(),
            resolved_state_key: Some(best.resolved_state_key),
            fallback_level: Some(best.fallback_level),
            calibration_source: Some(best.calibration_source),
            support: Some(best.cell.support),
            p_fill: Some(best.cell.p_fill),
            p_up_first: Some(best.cell.p_up_first),
            p_down_first: Some(best.cell.p_down_first),
            p_timeout: Some(best.cell.p_timeout),
            expected_net_bps: Some(best.expected_net_bps),
            j_score_bps: Some(best.j_score_bps),
            maker_cost_bps: Some(best.maker_cost_bps),
            toxicity_penalty_bps: Some(best.toxicity_penalty_bps),
            tail_penalty_bps: Some(best.tail_penalty_bps),
            queue_reset_cost_bps: Some(best.queue_reset_cost_bps),
            frozen_calibration: true,
            guardrail: GUARDRAIL.to_string(),
        },
        setup,
    )
}

fn simulate_setups(
    config: &V14Config,
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
    setups: &[PolicySetup],
    control_type: &str,
    control_only: bool,
) -> Vec<TradeRow> {
    setups
        .iter()
        .filter_map(|setup| {
            let rows = by_symbol.get(&setup.symbol)?;
            let outcome = simulate_policy_setup(config, rows, setup);
            Some(trade_from_outcome(
                config,
                setup,
                rows,
                &outcome,
                control_type,
                control_only,
            ))
        })
        .collect()
}

fn simulate_policy_setup(
    config: &V14Config,
    rows: &[&PanelRow],
    setup: &PolicySetup,
) -> SimOutcome {
    let anchor = rows[setup.anchor_pos];
    let distance_bps = x10_to_bps(setup.distance_x10);
    let take_profit_bps = x10_to_bps(setup.take_profit_x10);
    let stop_loss_bps = x10_to_bps(setup.stop_loss_x10);
    let marker = marker_price(anchor.center_price, setup.side_sign, distance_bps);
    let mut entry_pos = None::<usize>;
    let fill_end = rows
        .len()
        .min(setup.anchor_pos.saturating_add(MAX_FILL_WAIT_EVENTS + 1));
    for pos in setup.anchor_pos.saturating_add(1)..fill_end {
        if marker_touch_and_evidence(rows[pos], marker, setup.side_sign) {
            entry_pos = Some(pos);
            break;
        }
    }
    let Some(entry_pos) = entry_pos else {
        return SimOutcome {
            fill_status: "no_fill".to_string(),
            exit_reason: "marker_not_touched_with_evidence".to_string(),
            entry_pos: None,
            exit_pos: None,
            marker_price: marker,
            entry_touch_mid_price: None,
            exit_price: None,
            gross_bps: None,
            maker_cost_bps: None,
            maker_net_bps: None,
            stress_maker_net_bps: None,
            mfe_bps: None,
            mae_bps: None,
        };
    };

    let mut mfe_bps = 0.0;
    let mut mae_bps = 0.0;
    let mut exit_reason = "timeout_events";
    let mut exit_pos = entry_pos;
    let mut exit_price = rows[entry_pos].mid_price;
    let hold_end = rows
        .len()
        .min(entry_pos.saturating_add(setup.hold_events + 1));
    for pos in entry_pos.saturating_add(1)..hold_end {
        let row = rows[pos];
        exit_pos = pos;
        exit_price = row.mid_price;
        update_mfe_mae(
            row.mid_price,
            marker,
            setup.side_sign,
            &mut mfe_bps,
            &mut mae_bps,
        );
        if let Some(exit) = evaluate_first_passage(
            row.mid_price,
            marker,
            setup.side_sign,
            take_profit_bps,
            stop_loss_bps,
        ) {
            match exit {
                ExitDecision::StopLoss => {
                    exit_reason = "stop_loss";
                    exit_price = marker * (1.0 - setup.side_sign as f64 * stop_loss_bps / 10_000.0);
                }
                ExitDecision::TakeProfit => {
                    exit_reason = "take_profit";
                    exit_price =
                        marker * (1.0 + setup.side_sign as f64 * take_profit_bps / 10_000.0);
                }
            }
            break;
        }
    }
    if exit_pos + 1 >= rows.len() && exit_reason == "timeout_events" {
        exit_reason = "data_end";
    }
    let gross = setup.side_sign as f64 * (exit_price - marker) / marker * 10_000.0;
    let maker_cost = config.fee_bps + 0.25 * rows[entry_pos].spread_bps;
    SimOutcome {
        fill_status: "filled".to_string(),
        exit_reason: exit_reason.to_string(),
        entry_pos: Some(entry_pos),
        exit_pos: Some(exit_pos),
        marker_price: marker,
        entry_touch_mid_price: Some(rows[entry_pos].mid_price),
        exit_price: Some(exit_price),
        gross_bps: Some(gross),
        maker_cost_bps: Some(maker_cost),
        maker_net_bps: Some(gross - maker_cost),
        stress_maker_net_bps: Some(gross - maker_cost - STRESS_COST_BPS),
        mfe_bps: Some(mfe_bps),
        mae_bps: Some(mae_bps),
    }
}

fn trade_from_outcome(
    config: &V14Config,
    setup: &PolicySetup,
    rows: &[&PanelRow],
    outcome: &SimOutcome,
    control_type: &str,
    control_only: bool,
) -> TradeRow {
    let anchor = rows[setup.anchor_pos];
    let entry_row = outcome.entry_pos.and_then(|pos| rows.get(pos).copied());
    let exit_row = outcome.exit_pos.and_then(|pos| rows.get(pos).copied());
    TradeRow {
        run_tag: config.run_tag.clone(),
        decision_id: setup.decision_id,
        fold: setup.fold.clone(),
        phase: "frozen_validation".to_string(),
        date: setup.date.clone(),
        symbol: setup.symbol.clone(),
        side: side_name(setup.side_sign).to_string(),
        strategy_id: STRATEGY_ID.to_string(),
        control_type: control_type.to_string(),
        control_only,
        anchor_local_timestamp: setup.anchor_local_timestamp,
        anchor_event_index: anchor.event_index,
        marker_distance_bps: x10_to_bps(setup.distance_x10),
        take_profit_bps: x10_to_bps(setup.take_profit_x10),
        stop_loss_bps: x10_to_bps(setup.stop_loss_x10),
        hold_events: setup.hold_events,
        state_key: setup.state_key.clone(),
        fallback_level: setup.fallback_level,
        support: setup.support,
        p_fill: setup.p_fill,
        p_up_first: setup.p_up_first,
        p_down_first: setup.p_down_first,
        expected_net_bps: setup.expected_net_bps,
        j_score_bps: setup.j_score_bps,
        fill_status: outcome.fill_status.clone(),
        exit_reason: outcome.exit_reason.clone(),
        entry_local_timestamp: entry_row.map(|row| row.local_timestamp),
        exit_local_timestamp: exit_row.map(|row| row.local_timestamp),
        marker_price: outcome.marker_price,
        entry_touch_mid_price: outcome.entry_touch_mid_price,
        exit_price: outcome.exit_price,
        gross_bps: outcome.gross_bps,
        maker_cost_bps: outcome.maker_cost_bps,
        maker_net_bps: outcome.maker_net_bps,
        stress_maker_net_bps: outcome.stress_maker_net_bps,
        mfe_bps: outcome.mfe_bps,
        mae_bps: outcome.mae_bps,
        fill_price_semantics: "entry_price_is_policy_marker_not_touch_mid".to_string(),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn build_negative_control_rows(
    config: &V14Config,
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
    base_setups: &[PolicySetup],
    base_trades: &[TradeRow],
) -> Vec<NegativeControlRow> {
    let base_net = mean(
        &base_trades
            .iter()
            .filter_map(|trade| trade.maker_net_bps)
            .collect::<Vec<_>>(),
    );
    let mut out = Vec::new();
    for control in ControlType::all() {
        let setups = base_setups
            .iter()
            .filter_map(|setup| control_setup(setup, control, by_symbol))
            .collect::<Vec<_>>();
        let trades = simulate_setups(
            config,
            by_symbol,
            &setups,
            control.name(),
            control.is_control_only(),
        );
        let stats = collect_trade_stats(&trades);
        let net = mean(&stats.net);
        out.push(NegativeControlRow {
            run_tag: config.run_tag.clone(),
            control_type: control.name().to_string(),
            strategy_id: STRATEGY_ID.to_string(),
            control_only: control.is_control_only(),
            setups: stats.setups,
            fills: stats.fills,
            fill_rate: rate(stats.fills, stats.setups),
            gross_bps_mean: mean(&stats.gross),
            maker_net_bps_mean: net,
            stress_maker_net_bps_mean: mean(&stats.stress_net),
            winsorized_top1_maker_net_bps_mean: winsorized_top_mean(&stats.net, 0.01),
            max_date_share: max_share(&stats.date_counts),
            max_symbol_share: max_share(&stats.symbol_counts),
            abs_net_ge_base_abs_net: match (base_net, net) {
                (Some(base), Some(control_net)) => Some(control_net.abs() >= base.abs()),
                _ => None,
            },
            control_note: control_note(control).to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    out
}

fn control_setup(
    setup: &PolicySetup,
    control: ControlType,
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
) -> Option<PolicySetup> {
    let mut out = setup.clone();
    if let Some(shift) = control.shift_seconds() {
        let rows = by_symbol.get(&setup.symbol)?;
        let target = if shift >= 0 {
            setup
                .anchor_local_timestamp
                .saturating_add(shift as u64 * 1_000_000)
        } else {
            setup
                .anchor_local_timestamp
                .saturating_sub((-shift) as u64 * 1_000_000)
        };
        out.anchor_pos = first_row_at_or_after(rows, target)?;
        out.anchor_local_timestamp = rows[out.anchor_pos].local_timestamp;
        out.date = rows[out.anchor_pos].date.clone();
        return Some(out);
    }
    match control {
        ControlType::SideFlip => {
            out.side_sign *= -1;
            Some(out)
        }
        ControlType::WrongSymbolSameTime | ControlType::WrongSymbolLaggedState => {
            let (symbol, rows) = by_symbol
                .iter()
                .find(|(symbol, rows)| symbol.as_str() != setup.symbol && !rows.is_empty())?;
            out.symbol = symbol.clone();
            out.anchor_pos = first_row_at_or_after(rows, setup.anchor_local_timestamp)?;
            out.anchor_local_timestamp = rows[out.anchor_pos].local_timestamp;
            out.date = rows[out.anchor_pos].date.clone();
            if control == ControlType::WrongSymbolLaggedState {
                out.state_key = format!("wrong_symbol_lagged_state|{}", out.state_key);
            }
            Some(out)
        }
        ControlType::SurfaceShuffle => {
            let salt = deterministic_unit(setup.anchor_local_timestamp, &setup.symbol);
            out.distance_x10 = DISTANCE_GRID_X10[((salt * DISTANCE_GRID_X10.len() as f64)
                as usize)
                .min(DISTANCE_GRID_X10.len() - 1)];
            Some(out)
        }
        ControlType::SkewFlip => {
            out.side_sign *= -1;
            std::mem::swap(&mut out.take_profit_x10, &mut out.stop_loss_x10);
            Some(out)
        }
        ControlType::WrongDateSurface => {
            let rows = by_symbol.get(&setup.symbol)?;
            let pos = rows
                .iter()
                .position(|row| row.date != setup.date && row.factor_eligible)
                .unwrap_or(setup.anchor_pos);
            out.anchor_pos = pos;
            out.anchor_local_timestamp = rows[pos].local_timestamp;
            out.date = rows[pos].date.clone();
            Some(out)
        }
        ControlType::FutureVolLeakTest => {
            let rows = by_symbol.get(&setup.symbol)?;
            let future = rows
                .get(setup.anchor_pos.saturating_add(30))
                .copied()
                .unwrap_or(rows[setup.anchor_pos]);
            let d = (future.sigma_bps.max(TICK_FLOOR_BPS) * 10.0).round() as i32;
            out.distance_x10 = nearest_distance_x10(d);
            Some(out)
        }
        ControlType::RandomMarkerSameSupport => {
            let u = deterministic_unit(
                setup.anchor_local_timestamp ^ setup.decision_id as u64,
                "random_marker",
            );
            out.distance_x10 = DISTANCE_GRID_X10
                [((u * DISTANCE_GRID_X10.len() as f64) as usize).min(DISTANCE_GRID_X10.len() - 1)];
            Some(out)
        }
        ControlType::UpperLowerSwap => {
            std::mem::swap(&mut out.take_profit_x10, &mut out.stop_loss_x10);
            Some(out)
        }
        _ => Some(out),
    }
}

fn build_summary_rows(
    config: &V14Config,
    trades: &[TradeRow],
    controls: &[NegativeControlRow],
) -> Vec<SummaryRow> {
    let control_rate = control_abs_ge_base_abs_rate(controls);
    let mut out = Vec::new();
    out.push(summary_row_from_trades(
        config,
        "all_valid_entered",
        "ALL",
        trades,
        control_rate,
    ));
    let mut by_symbol = BTreeMap::<String, Vec<TradeRow>>::new();
    for trade in trades {
        by_symbol
            .entry(trade.symbol.clone())
            .or_default()
            .push(trade.clone());
    }
    for (symbol, rows) in by_symbol {
        out.push(summary_row_from_trades(
            config,
            "by_symbol",
            &symbol,
            &rows,
            control_rate,
        ));
    }
    out
}

fn summary_row_from_trades(
    config: &V14Config,
    scope: &str,
    symbol: &str,
    trades: &[TradeRow],
    control_rate: Option<f64>,
) -> SummaryRow {
    let stats = collect_trade_stats(trades);
    let net = mean(&stats.net);
    let stress = mean(&stats.stress_net);
    let winsor = winsorized_top_mean(&stats.net, 0.01);
    let max_date = max_share(&stats.date_counts);
    let max_symbol = max_share(&stats.symbol_counts);
    let leave_day = leave_one_min_mean(&stats.net, trades, |trade| trade.date.clone());
    let leave_hour = leave_one_min_mean(&stats.net, trades, |trade| {
        trade
            .entry_local_timestamp
            .or(Some(trade.anchor_local_timestamp))
            .map(hour_bucket)
            .unwrap_or_else(|| "NA".to_string())
    });
    let leave_symbol = leave_one_min_mean(&stats.net, trades, |trade| trade.symbol.clone());
    let pass_leave_one = [leave_day, leave_hour, leave_symbol]
        .into_iter()
        .flatten()
        .all(|value| value > 0.0);
    SummaryRow {
        run_tag: config.run_tag.clone(),
        summary_scope: scope.to_string(),
        symbol: symbol.to_string(),
        setups: stats.setups,
        fills: stats.fills,
        no_fills: stats.setups.saturating_sub(stats.fills),
        fill_rate: rate(stats.fills, stats.setups),
        gross_bps_mean: mean(&stats.gross),
        maker_net_bps_mean: net,
        stress_maker_net_bps_mean: stress,
        winsorized_top1_maker_net_bps_mean: winsor,
        win_rate: win_rate(&stats.net),
        stop_loss_rate: Some(rate(stats.stop_loss, stats.fills)),
        take_profit_rate: Some(rate(stats.take_profit, stats.fills)),
        timeout_rate: Some(rate(stats.timeout, stats.fills)),
        max_date_share: max_date,
        max_symbol_share: max_symbol,
        control_abs_ge_base_abs_rate: control_rate,
        leave_one_day_min_net_bps: leave_day,
        leave_one_hour_min_net_bps: leave_hour,
        leave_one_symbol_min_net_bps: leave_symbol,
        pass_fills: stats.fills >= HARD_MIN_FILLS,
        pass_maker_net: net
            .map(|value| value > HARD_MIN_MAKER_NET_BPS)
            .unwrap_or(false),
        pass_stress_net: stress.map(|value| value > 0.0).unwrap_or(false),
        pass_winsorized: winsor.map(|value| value > 0.0).unwrap_or(false),
        pass_controls: control_rate
            .map(|value| value <= HARD_MAX_CONTROL_RATE)
            .unwrap_or(false),
        pass_date_concentration: max_date
            .map(|value| value <= HARD_MAX_DATE_SHARE)
            .unwrap_or(false),
        pass_symbol_concentration: max_symbol
            .map(|value| value <= HARD_MAX_SYMBOL_SHARE)
            .unwrap_or(false),
        pass_leave_one_out: pass_leave_one,
        guardrail: GUARDRAIL.to_string(),
    }
}

fn build_failure_report(
    run_tag: &str,
    audit: &InputAudit,
    summaries: &[SummaryRow],
) -> FailureReportRow {
    let aggregate = summaries
        .iter()
        .find(|row| row.summary_scope == "all_valid_entered")
        .cloned()
        .unwrap_or_else(|| SummaryRow {
            run_tag: run_tag.to_string(),
            summary_scope: "all_valid_entered".to_string(),
            symbol: "ALL".to_string(),
            setups: 0,
            fills: 0,
            no_fills: 0,
            fill_rate: 0.0,
            gross_bps_mean: None,
            maker_net_bps_mean: None,
            stress_maker_net_bps_mean: None,
            winsorized_top1_maker_net_bps_mean: None,
            win_rate: None,
            stop_loss_rate: None,
            take_profit_rate: None,
            timeout_rate: None,
            max_date_share: None,
            max_symbol_share: None,
            control_abs_ge_base_abs_rate: None,
            leave_one_day_min_net_bps: None,
            leave_one_hour_min_net_bps: None,
            leave_one_symbol_min_net_bps: None,
            pass_fills: false,
            pass_maker_net: false,
            pass_stress_net: false,
            pass_winsorized: false,
            pass_controls: false,
            pass_date_concentration: false,
            pass_symbol_concentration: false,
            pass_leave_one_out: false,
            guardrail: GUARDRAIL.to_string(),
        });
    let primary_status = if !audit.blockers.is_empty() {
        "blocker_missing_inputs"
    } else if !aggregate.pass_fills {
        "hard_fail_fills_lt_500"
    } else if !aggregate.pass_maker_net {
        "hard_fail_maker_net_not_gt_2bps"
    } else if !aggregate.pass_stress_net {
        "hard_fail_stress_maker_net_not_positive"
    } else if !aggregate.pass_winsorized {
        "hard_fail_winsorized_top1_not_positive"
    } else if !aggregate.pass_controls {
        "hard_fail_controls_not_separated"
    } else if !aggregate.pass_date_concentration {
        "hard_fail_date_concentration"
    } else if !aggregate.pass_symbol_concentration {
        "hard_fail_symbol_concentration"
    } else if !aggregate.pass_leave_one_out {
        "hard_fail_leave_one_out_negative"
    } else {
        "passed_research_gates_not_trading_rule"
    };
    FailureReportRow {
        run_tag: run_tag.to_string(),
        primary_status: primary_status.to_string(),
        evidence: format!(
            "setups={} fills={} maker_net={} stress_net={} control_rate={}",
            aggregate.setups,
            aggregate.fills,
            fmt_opt(aggregate.maker_net_bps_mean, 4),
            fmt_opt(aggregate.stress_maker_net_bps_mean, 4),
            fmt_opt(aggregate.control_abs_ge_base_abs_rate, 4)
        ),
        blockers: audit.blockers.join("; "),
        setups: aggregate.setups,
        fills: aggregate.fills,
        maker_net_bps_mean: aggregate.maker_net_bps_mean,
        stress_maker_net_bps_mean: aggregate.stress_maker_net_bps_mean,
        winsorized_top1_maker_net_bps_mean: aggregate.winsorized_top1_maker_net_bps_mean,
        max_date_share: aggregate.max_date_share,
        max_symbol_share: aggregate.max_symbol_share,
        control_abs_ge_base_abs_rate: aggregate.control_abs_ge_base_abs_rate,
        leave_one_day_min_net_bps: aggregate.leave_one_day_min_net_bps,
        leave_one_hour_min_net_bps: aggregate.leave_one_hour_min_net_bps,
        leave_one_symbol_min_net_bps: aggregate.leave_one_symbol_min_net_bps,
        hard_gate_fills: aggregate.pass_fills,
        hard_gate_maker_net: aggregate.pass_maker_net,
        hard_gate_stress_net: aggregate.pass_stress_net,
        hard_gate_winsorized: aggregate.pass_winsorized,
        hard_gate_controls: aggregate.pass_controls,
        hard_gate_date_share: aggregate.pass_date_concentration,
        hard_gate_symbol_share: aggregate.pass_symbol_concentration,
        hard_gate_leave_one_out: aggregate.pass_leave_one_out,
        guardrail: GUARDRAIL.to_string(),
    }
}

fn build_diagnostics(config: &V14Config, trades: &[TradeRow]) -> Vec<DiagnosticRow> {
    trades
        .iter()
        .take(5_000)
        .map(|trade| DiagnosticRow {
            run_tag: config.run_tag.clone(),
            decision_id: trade.decision_id,
            fold: trade.fold.clone(),
            date: trade.date.clone(),
            symbol: trade.symbol.clone(),
            side: trade.side.clone(),
            state_key: trade.state_key.clone(),
            fallback_level: trade.fallback_level,
            support: trade.support,
            p_fill: trade.p_fill,
            p_up_first: trade.p_up_first,
            p_down_first: trade.p_down_first,
            expected_net_bps: trade.expected_net_bps,
            j_score_bps: trade.j_score_bps,
            fill_status: trade.fill_status.clone(),
            exit_reason: trade.exit_reason.clone(),
            gross_bps: trade.gross_bps,
            maker_net_bps: trade.maker_net_bps,
            paired_note: "validation decision chosen from frozen train-only calibration surface"
                .to_string(),
            guardrail: GUARDRAIL.to_string(),
        })
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn build_manifest(
    config: &V14Config,
    paths: &Paths,
    train_labels: &[TrainLabelRow],
    calibration: &[CalibrationRow],
    params: &[ParamsRow],
    decisions: &[DecisionRow],
    trades: &[TradeRow],
    summaries: &[SummaryRow],
    controls: &[NegativeControlRow],
    diagnostics: &[DiagnosticRow],
    failure: &FailureReportRow,
) -> Vec<ManifestRow> {
    let artifacts = [
        ("train_labels", &paths.train_labels_csv, train_labels.len()),
        ("calibration", &paths.calibration_csv, calibration.len()),
        ("params", &paths.params_csv, params.len()),
        (
            "valid_decisions",
            &paths.valid_decisions_csv,
            decisions.len(),
        ),
        ("valid_trades", &paths.valid_trades_csv, trades.len()),
        ("summary", &paths.summary_csv, summaries.len()),
        (
            "negative_controls",
            &paths.negative_controls_csv,
            controls.len(),
        ),
        ("diagnostics", &paths.diagnostics_csv, diagnostics.len()),
        ("failure_report", &paths.failure_report_csv, 1usize),
        ("manifest", &paths.manifest_csv, 10usize),
        ("report_md", &paths.report_md, 1usize),
    ];
    artifacts
        .into_iter()
        .map(|(artifact, path, rows)| ManifestRow {
            run_tag: config.run_tag.clone(),
            artifact: artifact.to_string(),
            path: path_string(path),
            rows,
            status: failure.primary_status.clone(),
            guardrail: GUARDRAIL.to_string(),
        })
        .collect()
}

fn build_params_rows(config: &V14Config) -> Vec<ParamsRow> {
    let mut rows = Vec::new();
    for (parameter, value) in [
        (
            "marker_distance_grid_bps",
            grid_to_string(&DISTANCE_GRID_X10),
        ),
        ("wing_grid_tp_sl_h", wing_grid_to_string()),
        ("max_fill_wait_events", MAX_FILL_WAIT_EVENTS.to_string()),
        (
            "max_train_anchors_per_fold_symbol",
            MAX_TRAIN_ANCHORS_PER_FOLD_SYMBOL.to_string(),
        ),
        (
            "max_valid_anchors_per_fold_symbol",
            MAX_VALID_ANCHORS_PER_FOLD_SYMBOL.to_string(),
        ),
        ("valid_event_gap", VALID_EVENT_GAP.to_string()),
        ("min_support", MIN_SUPPORT.to_string()),
        ("min_p_fill_gate", MIN_P_FILL_GATE.to_string()),
        ("min_p_up_first_gate", MIN_P_UP_FIRST_GATE.to_string()),
        (
            "expected_net_gate_bps",
            format!("fee_bps+1.0={}", config.fee_bps + 1.0),
        ),
        ("hard_gate_fills", HARD_MIN_FILLS.to_string()),
        (
            "hard_gate_maker_net_bps",
            HARD_MIN_MAKER_NET_BPS.to_string(),
        ),
        (
            "hard_gate_control_abs_ge_base_abs_rate",
            HARD_MAX_CONTROL_RATE.to_string(),
        ),
        ("hard_gate_max_date_share", HARD_MAX_DATE_SHARE.to_string()),
        (
            "hard_gate_max_symbol_share",
            HARD_MAX_SYMBOL_SHARE.to_string(),
        ),
    ] {
        rows.push(ParamsRow {
            run_tag: config.run_tag.clone(),
            parameter: parameter.to_string(),
            value,
            source_phase: "train_only_or_fixed_before_validation".to_string(),
            frozen_for_validation: true,
            guardrail: GUARDRAIL.to_string(),
        });
    }
    rows
}

fn collect_trade_stats(trades: &[TradeRow]) -> TradeStats {
    let mut stats = TradeStats {
        setups: trades.len(),
        ..TradeStats::default()
    };
    for trade in trades {
        if trade.fill_status == "filled" {
            stats.fills += 1;
            if let Some(gross) = trade.gross_bps {
                stats.gross.push(gross);
            }
            if let Some(net) = trade.maker_net_bps {
                stats.net.push(net);
            }
            if let Some(stress) = trade.stress_maker_net_bps {
                stats.stress_net.push(stress);
            }
            match trade.exit_reason.as_str() {
                "stop_loss" => stats.stop_loss += 1,
                "take_profit" => stats.take_profit += 1,
                "timeout_events" | "data_end" => stats.timeout += 1,
                _ => {}
            }
            *stats.date_counts.entry(trade.date.clone()).or_default() += 1;
            *stats.symbol_counts.entry(trade.symbol.clone()).or_default() += 1;
            let hour = trade
                .entry_local_timestamp
                .or(Some(trade.anchor_local_timestamp))
                .map(hour_bucket)
                .unwrap_or_else(|| "NA".to_string());
            *stats.hour_counts.entry(hour).or_default() += 1;
        }
    }
    stats
}

fn write_report(
    config: &V14Config,
    paths: &Paths,
    audit: &InputAudit,
    folds: &[FoldSpec],
    train_labels: &[TrainLabelRow],
    calibration: &[CalibrationRow],
    decisions: &[DecisionRow],
    trades: &[TradeRow],
    summaries: &[SummaryRow],
    controls: &[NegativeControlRow],
    failure: &FailureReportRow,
) -> Result<()> {
    let generated_at = Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true);
    let aggregate = summaries
        .iter()
        .find(|row| row.summary_scope == "all_valid_entered");
    let control_types = controls
        .iter()
        .map(|row| row.control_type.clone())
        .collect::<Vec<_>>()
        .join(",");
    let mut lines = Vec::new();
    lines.push("# BONK V14 Queue-Reactive First-Passage State Policy".to_string());
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
    lines.push(format!("- train label rows: `{}`", train_labels.len()));
    lines.push(format!("- calibration rows: `{}`", calibration.len()));
    lines.push(format!("- validation decision rows: `{}`", decisions.len()));
    lines.push(format!(
        "- validation entered setup rows: `{}`",
        trades.len()
    ));
    if !audit.blockers.is_empty() {
        lines.push(format!("- blockers: `{}`", audit.blockers.join("; ")));
    }
    lines.push(String::new());
    lines.push("## Primary Status".to_string());
    lines.push(String::new());
    lines.push(format!("- primary_status: `{}`", failure.primary_status));
    lines.push(format!("- evidence: `{}`", failure.evidence));
    if let Some(row) = aggregate {
        lines.push(format!("- fills: `{}`", row.fills));
        lines.push(format!(
            "- maker_net_bps_mean: `{}`",
            fmt_opt(row.maker_net_bps_mean, 4)
        ));
        lines.push(format!(
            "- stress_maker_net_bps_mean: `{}`",
            fmt_opt(row.stress_maker_net_bps_mean, 4)
        ));
        lines.push(format!(
            "- winsorized_top1_maker_net_bps_mean: `{}`",
            fmt_opt(row.winsorized_top1_maker_net_bps_mean, 4)
        ));
        lines.push(format!(
            "- max_date_share: `{}`",
            fmt_opt(row.max_date_share, 4)
        ));
        lines.push(format!(
            "- max_symbol_share: `{}`",
            fmt_opt(row.max_symbol_share, 4)
        ));
        lines.push(format!(
            "- control_abs_ge_base_abs_rate: `{}`",
            fmt_opt(row.control_abs_ge_base_abs_rate, 4)
        ));
    }
    lines.push(String::new());
    lines.push("## Model Mechanics".to_string());
    lines.push(String::new());
    lines.push("- V14 labels are generated only inside each fold train window with `label_source_phase=train`.".to_string());
    lines.push("- State buckets combine causal MLOFI tensor pressure, depth curvature, microprice drift/deviation, spread/liquidity, depletion/replenish/cancel pressure, trade-flow imbalance, liquidity shock, event-time RV, cross-symbol lagged pressure, and toxicity proxy.".to_string());
    lines.push("- Calibration estimates `P_fill`, side-specific favorable first-passage `P_up_first`, adverse `P_down_first`, timeout probability, expected gross/net, stress net, and tail ES from train labels only.".to_string());
    lines.push("- Validation replay is frozen: every validation event enumerates `(side,d,U,D,H)`, resolves support through exact/parent/root fallback, and enters only if support, expected net, fill probability, and first-passage gates pass.".to_string());
    lines.push("- Same-event TP/SL collision is adverse-first; fill price is the marker, not the touch-row mid.".to_string());
    lines.push(String::new());
    lines.push("## Negative Controls".to_string());
    lines.push(String::new());
    lines.push(format!("- controls written: `{control_types}`"));
    lines.push("- Required controls include timestamp shifts +/-5s/+/-30s/+/-60s/+/-300s, side flip, wrong-symbol same-time, wrong-symbol lagged-state, surface shuffle, skew flip, wrong-date surface, future-vol leak test, random marker same support, and upper/lower swap.".to_string());
    lines.push("- `future_vol_leak_test` is explicitly marked `control_only=true` and is never used in base calibration or validation decisions.".to_string());
    lines.push(String::new());
    lines.push("## Outputs".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- train_labels: `{}`",
        path_string(&paths.train_labels_csv)
    ));
    lines.push(format!(
        "- calibration: `{}`",
        path_string(&paths.calibration_csv)
    ));
    lines.push(format!("- params: `{}`", path_string(&paths.params_csv)));
    lines.push(format!(
        "- valid_decisions: `{}`",
        path_string(&paths.valid_decisions_csv)
    ));
    lines.push(format!(
        "- valid_trades: `{}`",
        path_string(&paths.valid_trades_csv)
    ));
    lines.push(format!("- summary: `{}`", path_string(&paths.summary_csv)));
    lines.push(format!(
        "- negative_controls: `{}`",
        path_string(&paths.negative_controls_csv)
    ));
    lines.push(format!(
        "- diagnostics: `{}`",
        path_string(&paths.diagnostics_csv)
    ));
    lines.push(format!(
        "- failure_report: `{}`",
        path_string(&paths.failure_report_csv)
    ));
    lines.push(format!(
        "- manifest: `{}`",
        path_string(&paths.manifest_csv)
    ));
    write_text_atomic(&paths.report_md, &lines.join("\n"))
}

fn evaluate_first_passage(
    mid_price: f64,
    entry_price: f64,
    side_sign: i8,
    take_profit_bps: f64,
    stop_loss_bps: f64,
) -> Option<ExitDecision> {
    let take_profit_price = entry_price * (1.0 + side_sign as f64 * take_profit_bps / 10_000.0);
    let stop_loss_price = entry_price * (1.0 - side_sign as f64 * stop_loss_bps / 10_000.0);
    let adverse_hit = if side_sign >= 0 {
        mid_price <= stop_loss_price
    } else {
        mid_price >= stop_loss_price
    };
    let favorable_hit = if side_sign >= 0 {
        mid_price >= take_profit_price
    } else {
        mid_price <= take_profit_price
    };
    if adverse_hit {
        Some(ExitDecision::StopLoss)
    } else if favorable_hit {
        Some(ExitDecision::TakeProfit)
    } else {
        None
    }
}

fn marker_touch_and_evidence(row: &PanelRow, marker_price: f64, side_sign: i8) -> bool {
    if side_sign >= 0 {
        row.mid_price <= marker_price && row.long_fill_evidence()
    } else {
        row.mid_price >= marker_price && row.short_fill_evidence()
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

fn toxicity_penalty_bps(state: &StateSnapshot, side_sign: i8) -> f64 {
    let adverse_cross = (-side_sign as f64 * state.cross_lagged_pressure).max(0.0);
    (0.15 * state.toxicity_proxy + 0.20 * adverse_cross).min(3.0)
}

fn queue_reset_cost_bps(distance_bps: f64, spread_bps: f64, sigma_bps: f64) -> f64 {
    if distance_bps < spread_bps.max(0.25 * sigma_bps).max(TICK_FLOOR_BPS) {
        0.15
    } else {
        0.0
    }
}

fn marker_price(center_price: f64, side_sign: i8, distance_bps: f64) -> f64 {
    center_price * (1.0 - side_sign as f64 * distance_bps / 10_000.0)
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

fn sample_positions(positions: &[usize], max_rows: usize) -> Vec<usize> {
    if max_rows == 0 || positions.len() <= max_rows {
        return positions.to_vec();
    }
    let step = positions.len() as f64 / max_rows as f64;
    (0..max_rows)
        .map(|idx| {
            let source_idx = ((idx as f64) * step).floor() as usize;
            positions[source_idx.min(positions.len() - 1)]
        })
        .collect()
}

fn bucket_3(
    value: f64,
    low: f64,
    high: f64,
    low_name: &str,
    mid_name: &str,
    high_name: &str,
) -> String {
    if value < low {
        low_name
    } else if value < high {
        mid_name
    } else {
        high_name
    }
    .to_string()
}

fn signed_bucket(value: f64, weak: f64, strong: f64) -> String {
    if value <= -strong {
        "neg_strong"
    } else if value <= -weak {
        "neg"
    } else if value < weak {
        "flat"
    } else if value < strong {
        "pos"
    } else {
        "pos_strong"
    }
    .to_string()
}

fn signed_ratio(pos: f64, neg: f64) -> f64 {
    let denom = pos.abs() + neg.abs();
    if denom <= f64::EPSILON {
        0.0
    } else {
        ((pos - neg) / denom).clamp(-1.0, 1.0)
    }
}

fn nearest_distance_x10(target: i32) -> i32 {
    DISTANCE_GRID_X10
        .iter()
        .copied()
        .min_by_key(|value| (value - target).abs())
        .unwrap_or(DISTANCE_GRID_X10[0])
}

fn x10_to_bps(value: i32) -> f64 {
    value as f64 / 10.0
}

fn bps_to_x10(value: f64) -> i32 {
    (value * 10.0).round() as i32
}

fn side_name(side_sign: i8) -> &'static str {
    if side_sign >= 0 { "long" } else { "short" }
}

fn side_sign_from_name(value: &str) -> Option<i8> {
    match value {
        "long" => Some(1),
        "short" => Some(-1),
        _ => None,
    }
}

fn hour_bucket(local_timestamp: u64) -> String {
    (local_timestamp / 3_600_000_000).to_string()
}

fn control_note(control: ControlType) -> &'static str {
    match control {
        ControlType::TimestampShiftMinus300
        | ControlType::TimestampShiftMinus60
        | ControlType::TimestampShiftMinus30
        | ControlType::TimestampShiftMinus5
        | ControlType::TimestampShiftPlus5
        | ControlType::TimestampShiftPlus30
        | ControlType::TimestampShiftPlus60
        | ControlType::TimestampShiftPlus300 => {
            "same learned setup shifted in event time; checks timestamp decay"
        }
        ControlType::SideFlip => "same marker/wings with opposite side",
        ControlType::WrongSymbolSameTime => "replayed on the other symbol at the same timestamp",
        ControlType::WrongSymbolLaggedState => "replayed with other-symbol lagged state context",
        ControlType::SurfaceShuffle => "deterministic marker-distance shuffle over same support",
        ControlType::SkewFlip => "side/skew flipped control",
        ControlType::WrongDateSurface => "same setup replayed on a different date surface",
        ControlType::FutureVolLeakTest => {
            "control-only future volatility leak test; never used in base"
        }
        ControlType::RandomMarkerSameSupport => {
            "deterministic random marker distance with same support"
        }
        ControlType::UpperLowerSwap => "take-profit and stop-loss distances swapped",
    }
}

fn grid_to_string(values: &[i32]) -> String {
    values
        .iter()
        .map(|value| format!("{:.1}", x10_to_bps(*value)))
        .collect::<Vec<_>>()
        .join("|")
}

fn wing_grid_to_string() -> String {
    WING_GRID_X10
        .iter()
        .map(|(tp, sl, hold)| format!("{:.1}:{:.1}:{hold}", x10_to_bps(*tp), x10_to_bps(*sl)))
        .collect::<Vec<_>>()
        .join("|")
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

fn expected_shortfall(values: &[f64], alpha: f64) -> Option<f64> {
    let mut values = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let n = ((values.len() as f64 * alpha).ceil() as usize)
        .max(1)
        .min(values.len());
    mean(&values[..n])
}

fn winsorized_top_mean(values: &[f64], top_share: f64) -> Option<f64> {
    let mut values = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let drop =
        ((values.len() as f64 * top_share).ceil() as usize).min(values.len().saturating_sub(1));
    let keep = values.len().saturating_sub(drop);
    mean(&values[..keep])
}

fn leave_one_min_mean<F>(all_values: &[f64], trades: &[TradeRow], key_fn: F) -> Option<f64>
where
    F: Fn(&TradeRow) -> String,
{
    if all_values.is_empty() {
        return None;
    }
    let mut by_key = BTreeMap::<String, Vec<f64>>::new();
    for trade in trades {
        if let Some(value) = trade.maker_net_bps {
            by_key.entry(key_fn(trade)).or_default().push(value);
        }
    }
    if by_key.len() <= 1 {
        return mean(all_values);
    }
    let mut out = Vec::new();
    for key in by_key.keys() {
        let values = trades
            .iter()
            .filter(|trade| key_fn(trade) != *key)
            .filter_map(|trade| trade.maker_net_bps)
            .collect::<Vec<_>>();
        if let Some(value) = mean(&values) {
            out.push(value);
        }
    }
    out.into_iter().min_by(f64::total_cmp)
}

fn control_abs_ge_base_abs_rate(controls: &[NegativeControlRow]) -> Option<f64> {
    let values = controls
        .iter()
        .filter_map(|row| row.abs_net_ge_base_abs_net)
        .collect::<Vec<_>>();
    if values.is_empty() {
        None
    } else {
        Some(rate(
            values.iter().filter(|value| **value).count(),
            values.len(),
        ))
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

fn load_csv_rows<T: DeserializeOwned>(path: &Path) -> Result<Vec<T>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    let mut out = Vec::new();
    for record in reader.deserialize() {
        out.push(record.with_context(|| format!("failed to parse {}", path.display()))?);
    }
    Ok(out)
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
        .unwrap_or("bonk_v14_output");
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
    fn validation_rows_do_not_change_calibration() {
        let run_tag = "test_v14";
        let fold = synthetic_fold(run_tag, "fold1", "BONK1MUSDC");
        let mut rows = (0..120)
            .map(|idx| test_row(run_tag, "BONK1MUSDC", idx, 100.0 + idx as f64 * 0.001))
            .collect::<Vec<_>>();
        enrich_rolling_state(&mut rows);
        enrich_cross_lagged_state(&mut rows);
        let by_symbol = rows_by_symbol(&rows);
        let config = test_config(run_tag);
        let labels_a = build_train_labels(&config, &[fold.clone()], &by_symbol);
        let cal_a = build_calibration(&config, &labels_a);

        let mut changed = rows.clone();
        for row in changed
            .iter_mut()
            .filter(|row| row.local_timestamp > fold.valid_start)
        {
            row.mid_price *= 10.0;
            row.center_price *= 10.0;
        }
        enrich_rolling_state(&mut changed);
        enrich_cross_lagged_state(&mut changed);
        let changed_by_symbol = rows_by_symbol(&changed);
        let labels_b = build_train_labels(&config, &[fold], &changed_by_symbol);
        let cal_b = build_calibration(&config, &labels_b);
        assert_eq!(cal_a.rows.len(), cal_b.rows.len());
        assert_eq!(cal_a.rows[0].support, cal_b.rows[0].support);
        assert!((cal_a.rows[0].p_fill - cal_b.rows[0].p_fill).abs() < 1e-12);
    }

    #[test]
    fn state_updater_uses_only_current_and_past() {
        let run_tag = "test_v14";
        let mut rows = vec![
            test_row(run_tag, "BONK1MUSDC", 0, 100.0),
            test_row(run_tag, "BONK1MUSDC", 1, 100.1),
            test_row(run_tag, "BONK1MUSDC", 2, 120.0),
        ];
        enrich_rolling_state(&mut rows);
        let first_sigma = rows[0].sigma_bps;
        let second_drift = rows[1].microprice_drift_bps;
        rows[2].center_price = 10_000.0;
        enrich_rolling_state(&mut rows);
        assert_eq!(first_sigma, rows[0].sigma_bps);
        assert_eq!(second_drift, rows[1].microprice_drift_bps);
    }

    #[test]
    fn bucket_fallback_uses_parent_when_full_support_is_low() {
        let run_tag = "test_v14";
        let config = test_config(run_tag);
        let mut labels = Vec::new();
        let mut row = test_row(run_tag, "BONK1MUSDC", 1, 100.0);
        row.vol_bucket = "normal".to_string();
        let state = StateSnapshot::from_row(&row);
        for idx in 0..MIN_SUPPORT {
            let mut label = base_label(&config, "fold1", &row, &state);
            label.anchor_event_index = idx;
            label.state_key = format!("unique_{idx}");
            labels.push(label);
        }
        let book = build_calibration(&config, &labels);
        let resolved = book.resolve("fold1", "BONK1MUSDC", 1, 10, 20, 10, 300, &state);
        assert!(resolved.is_some());
        assert_eq!(resolved.unwrap().2, 1);
    }

    #[test]
    fn insufficient_support_causes_skip() {
        let run_tag = "test_v14";
        let config = test_config(run_tag);
        let fold = synthetic_fold(run_tag, "fold1", "BONK1MUSDC");
        let mut rows = (0..220)
            .map(|idx| test_row(run_tag, "BONK1MUSDC", idx, 100.0))
            .collect::<Vec<_>>();
        enrich_rolling_state(&mut rows);
        enrich_cross_lagged_state(&mut rows);
        let by_symbol = rows_by_symbol(&rows);
        let book = CalibrationBook {
            map: BTreeMap::new(),
            rows: Vec::new(),
        };
        let (decisions, setups) = replay_validation(&config, &[fold], &by_symbol, &book);
        assert!(setups.is_empty());
        assert!(
            decisions
                .iter()
                .any(|row| row.skip_reason == "insufficient_support")
        );
    }

    #[test]
    fn same_event_adverse_first() {
        let exit = evaluate_first_passage(100.0, 100.0, 1, 0.0, 0.0);
        assert_eq!(exit, Some(ExitDecision::StopLoss));
    }

    #[test]
    fn ev_cost_math_subtracts_costs() {
        let mut row = test_row("test_v14", "BONK1MUSDC", 1, 100.0);
        row.spread_bps = 2.0;
        row.sigma_bps = 2.0;
        let state = StateSnapshot::from_row(&row);
        let cell = CalibrationCell {
            support: MIN_SUPPORT,
            fills: MIN_SUPPORT,
            p_fill: 1.0,
            p_up_first: 1.0,
            p_down_first: 0.0,
            p_timeout: 0.0,
            e_timeout_ret_bps: 0.0,
            e_gross_bps: 5.0,
            e_net_bps: 2.5,
            e_stress_net_bps: 0.5,
            tail_es_bps: 0.0,
        };
        let maker_cost = 2.0 + 0.25 * row.spread_bps;
        let j =
            cell.p_fill * (cell.p_up_first * 5.0) - maker_cost - toxicity_penalty_bps(&state, 1);
        assert!(j < 5.0);
        assert!(j <= 2.5);
    }

    #[test]
    fn controls_are_deterministic_and_future_vol_is_control_only() {
        let setup = PolicySetup {
            decision_id: 7,
            fold: "fold1".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            anchor_pos: 1,
            anchor_local_timestamp: 1_000,
            side_sign: 1,
            distance_x10: 10,
            take_profit_x10: 20,
            stop_loss_x10: 10,
            hold_events: 300,
            state_key: "state".to_string(),
            fallback_level: 0,
            support: 20,
            p_fill: 0.5,
            p_up_first: 0.6,
            p_down_first: 0.2,
            expected_net_bps: 5.0,
            j_score_bps: 1.0,
        };
        let rows = (0..50)
            .map(|idx| test_row("test_v14", "BONK1MUSDC", idx, 100.0 + idx as f64 * 0.01))
            .collect::<Vec<_>>();
        let by_symbol = rows_by_symbol(&rows);
        let a = control_setup(&setup, ControlType::SurfaceShuffle, &by_symbol).unwrap();
        let b = control_setup(&setup, ControlType::SurfaceShuffle, &by_symbol).unwrap();
        assert_eq!(a.distance_x10, b.distance_x10);
        assert!(ControlType::FutureVolLeakTest.is_control_only());
    }

    #[test]
    fn synthetic_run_writes_all_outputs() -> Result<()> {
        let root = unique_test_dir("v14_synthetic");
        let data_root = root.join("data/bonk/v1");
        let date_dir = root.join("date");
        let doc_dir = root.join("docs/markets/bonk");
        let run_tag = "test_v14".to_string();
        fs::create_dir_all(&date_dir)?;
        for symbol in ["BONK1MUSDC", "BONK1MUSDT"] {
            let part = data_root
                .join("derived/bonk_v10c_event_ofi_panel")
                .join(format!("run_tag={run_tag}"))
                .join(format!("symbol={symbol}"))
                .join("dt=2026-05-06")
                .join("part_000001.csv");
            let rows = (0..260)
                .map(|idx| synthetic_panel_row(&run_tag, symbol, idx))
                .collect::<Vec<_>>();
            write_csv_atomic(&part, &rows)?;
        }
        let folds = vec![
            synthetic_fold_row(&run_tag, "fold1", "BONK1MUSDC"),
            synthetic_fold_row(&run_tag, "fold1", "BONK1MUSDT"),
        ];
        write_csv_atomic(
            &date_dir.join(format!("bonk_v10_filter_params_{run_tag}.csv")),
            &folds,
        )?;
        let summary = run_v14(&V14Config {
            data_root,
            date_dir: date_dir.clone(),
            doc_dir: doc_dir.clone(),
            run_tag: run_tag.clone(),
            fee_bps: 0.2,
            symbols: "BONK1MUSDC,BONK1MUSDT".to_string(),
        })?;
        assert!(Path::new(&summary.train_labels_csv).exists());
        assert!(Path::new(&summary.calibration_csv).exists());
        assert!(Path::new(&summary.params_csv).exists());
        assert!(Path::new(&summary.valid_decisions_csv).exists());
        assert!(Path::new(&summary.valid_trades_csv).exists());
        assert!(Path::new(&summary.summary_csv).exists());
        assert!(Path::new(&summary.negative_controls_csv).exists());
        assert!(Path::new(&summary.diagnostics_csv).exists());
        assert!(Path::new(&summary.failure_report_csv).exists());
        assert!(Path::new(&summary.manifest_csv).exists());
        assert!(Path::new(&summary.report_md).exists());
        assert!(summary.negative_control_rows >= ControlType::all().len());
        Ok(())
    }

    #[test]
    fn missing_panel_or_fold_writes_blocker() -> Result<()> {
        let root = unique_test_dir("v14_missing");
        let summary = run_v14(&V14Config {
            data_root: root.join("missing_data"),
            date_dir: root.join("date"),
            doc_dir: root.join("docs"),
            run_tag: "missing".to_string(),
            fee_bps: 2.0,
            symbols: "BONK1MUSDC".to_string(),
        })?;
        assert_eq!(summary.primary_status, "blocker_missing_inputs");
        assert!(Path::new(&summary.failure_report_csv).exists());
        Ok(())
    }

    fn test_config(run_tag: &str) -> V14Config {
        V14Config {
            data_root: PathBuf::from("data/bonk/v1"),
            date_dir: PathBuf::from("date"),
            doc_dir: PathBuf::from("docs/markets/bonk"),
            run_tag: run_tag.to_string(),
            fee_bps: 0.2,
            symbols: "BONK1MUSDC".to_string(),
        }
    }

    fn base_label(
        config: &V14Config,
        fold: &str,
        row: &PanelRow,
        state: &StateSnapshot,
    ) -> TrainLabelRow {
        TrainLabelRow {
            run_tag: config.run_tag.clone(),
            fold: fold.to_string(),
            symbol: row.symbol.clone(),
            date: row.date.clone(),
            label_source_phase: "train".to_string(),
            anchor_local_timestamp: row.local_timestamp,
            anchor_event_index: row.event_index,
            side: "long".to_string(),
            marker_distance_bps: 1.0,
            take_profit_bps: 2.0,
            stop_loss_bps: 1.0,
            hold_events: 300,
            state_key: state.full_key.clone(),
            parent_state_key: state.parent_key.clone(),
            root_state_key: state.root_key.clone(),
            vol_bucket: state.vol_bucket.clone(),
            spread_bucket: state.spread_bucket.clone(),
            liquidity_bucket: state.liquidity_bucket.clone(),
            pressure_bucket: state.pressure_bucket.clone(),
            toxicity_bucket: state.toxicity_bucket.clone(),
            cross_bucket: state.cross_bucket.clone(),
            micro_bucket: state.micro_bucket.clone(),
            curvature_bucket: state.curvature_bucket.clone(),
            depletion_bucket: state.depletion_bucket.clone(),
            replenish_bucket: state.replenish_bucket.clone(),
            cancel_bucket: state.cancel_bucket.clone(),
            pressure_score: state.pressure_score,
            toxicity_proxy: state.toxicity_proxy,
            event_rv_bps: state.event_rv_bps,
            cross_lagged_pressure: state.cross_lagged_pressure,
            filled_with_evidence: true,
            first_passage: "up_first".to_string(),
            entry_local_timestamp: Some(row.local_timestamp),
            exit_local_timestamp: Some(row.local_timestamp + 1),
            marker_price: row.center_price,
            entry_touch_mid_price: Some(row.mid_price),
            exit_price: Some(row.mid_price * 1.001),
            mfe_bps: 2.0,
            mae_bps: 0.0,
            timeout_return_bps: 0.0,
            gross_bps: 2.0,
            maker_cost_bps: 0.2,
            maker_net_bps: 1.8,
            stress_maker_net_bps: -0.2,
            fill_price_semantics: "test".to_string(),
            guardrail: GUARDRAIL.to_string(),
        }
    }

    fn synthetic_fold(run_tag: &str, fold: &str, symbol: &str) -> FoldSpec {
        let row = synthetic_fold_row(run_tag, fold, symbol);
        FoldSpec {
            fold: row.fold,
            symbol: row.symbol,
            train_start: row.train_start_local_timestamp,
            train_end: row.train_end_local_timestamp,
            valid_start: row.valid_start_local_timestamp,
            valid_end: row.valid_end_local_timestamp,
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

    fn synthetic_fold_row(run_tag: &str, fold: &str, symbol: &str) -> SyntheticFoldRow {
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

    fn test_row(run_tag: &str, symbol: &str, idx: usize, mid: f64) -> PanelRow {
        PanelRow {
            run_tag: run_tag.to_string(),
            date: if idx < 200 {
                "2026-05-06".to_string()
            } else {
                "2026-05-07".to_string()
            },
            symbol: symbol.to_string(),
            timestamp: (idx as u64 + 1) * 1_000,
            local_timestamp: (idx as u64 + 1) * 1_000,
            event_index: idx,
            factor_eligible: idx > 3,
            mid_price: mid,
            spread_bps: 0.5,
            microprice: Some(mid),
            microprice_dev_bps: 0.0,
            center_price: mid,
            best_bid_price: Some(mid - 0.01),
            best_ask_price: Some(mid + 0.01),
            best_bid_amount: 10.0,
            best_ask_amount: 10.0,
            bid_depth_1: 10.0,
            ask_depth_1: 10.0,
            bid_depth_5: 20.0,
            ask_depth_5: 20.0,
            bid_depth_10: 30.0,
            ask_depth_10: 30.0,
            bid_depth_25: 60.0,
            ask_depth_25: 60.0,
            queue_imbalance_1: 0.2,
            queue_imbalance_5: 0.2,
            queue_imbalance_25: 0.2,
            mlofi_norm_l1: 0.2,
            mlofi_norm_l5: 0.2,
            mlofi_norm_l10: 0.2,
            mlofi_norm_l25: 0.2,
            mlofi_roll10_l1: 0.2,
            mlofi_roll10_l5: 0.2,
            mlofi_roll10_l10: 0.2,
            mlofi_roll10_l25: 0.2,
            trade_flow_imbalance: 0.2,
            trade_arrival_alignment: 0.2,
            trade_buy_amount: if idx % 11 == 0 { 1.0 } else { 0.0 },
            trade_sell_amount: if idx % 7 == 0 { 1.0 } else { 0.0 },
            depletion_bid_amount: if idx % 7 == 0 { 1.0 } else { 0.0 },
            depletion_ask_amount: if idx % 11 == 0 { 1.0 } else { 0.0 },
            replenish_bid_amount: 0.0,
            replenish_ask_amount: 0.0,
            cancel_bid_amount: 0.0,
            cancel_ask_amount: 0.0,
            decrease_bid_amount: 0.0,
            decrease_ask_amount: 0.0,
            remove_bid_amount: 0.0,
            remove_ask_amount: 0.0,
            execute_bid_amount: if idx % 7 == 0 { 1.0 } else { 0.0 },
            execute_ask_amount: if idx % 11 == 0 { 1.0 } else { 0.0 },
            queue_depletion_intensity: 0.1,
            replenish_intensity: 0.1,
            cancellation_withdrawal_intensity: 0.1,
            liquidity_shock_score: 0.1,
            rv30_bps: 0.0,
            sigma_bps: 0.5,
            vol_bucket: "normal".to_string(),
            microprice_drift_bps: 0.0,
            cross_lagged_pressure: 0.0,
        }
    }

    fn synthetic_panel_row(run_tag: &str, symbol: &str, idx: usize) -> EventPanelRow {
        let local_timestamp = (idx as u64 + 1) * 1_000;
        let cycle = (idx % 16) as f64;
        let mid = 100.0 + idx as f64 * 0.001 + if idx % 23 == 0 { -0.03 } else { 0.0 };
        let feature = (cycle - 8.0) / 8.0;
        EventPanelRow {
            run_tag: run_tag.to_string(),
            date: if idx < 200 {
                "2026-05-06".to_string()
            } else {
                "2026-05-07".to_string()
            },
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
            spread_bps: Some(0.5),
            microprice: Some(mid),
            microprice_dev_bps: Some(feature * 0.1),
            bid_levels: 25,
            ask_levels: 25,
            bid_depth_1: 10.0,
            ask_depth_1: 10.0,
            bid_depth_2: 12.0,
            ask_depth_2: 12.0,
            bid_depth_3: 14.0,
            ask_depth_3: 14.0,
            bid_depth_5: 20.0,
            ask_depth_5: 20.0,
            bid_depth_10: 30.0,
            ask_depth_10: 30.0,
            bid_depth_25: 60.0,
            ask_depth_25: 60.0,
            queue_imbalance_1: Some(feature),
            queue_imbalance_5: Some(feature),
            queue_imbalance_25: Some(feature),
            limit_add_bid_amount: 0.0,
            limit_add_ask_amount: 0.0,
            replenish_bid_amount: 0.1,
            replenish_ask_amount: 0.1,
            decrease_bid_amount: 0.0,
            decrease_ask_amount: 0.0,
            remove_bid_amount: 0.0,
            remove_ask_amount: 0.0,
            depletion_bid_amount: if idx % 7 == 0 { 1.0 } else { 0.0 },
            depletion_ask_amount: if idx % 11 == 0 { 1.0 } else { 0.0 },
            execute_bid_amount: if idx % 7 == 0 { 1.0 } else { 0.0 },
            execute_ask_amount: if idx % 11 == 0 { 1.0 } else { 0.0 },
            cancel_bid_amount: 0.0,
            cancel_ask_amount: 0.0,
            event_matched_rate: Some(1.0),
            trade_window_count: 1,
            trade_buy_amount: if idx % 11 == 0 { 1.0 } else { 0.0 },
            trade_sell_amount: if idx % 7 == 0 { 1.0 } else { 0.0 },
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

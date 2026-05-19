use std::collections::{BTreeMap, HashMap, VecDeque};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use chrono::{NaiveDate, TimeZone, Utc};
use finance_chain_core::storage::ensure_parent_dir;
use flate2::read::GzDecoder;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

use crate::download::{parse_symbol_list, path_string};

pub const DEFAULT_CC_RUN_TAG: &str = "20260517_ccusdt_fixed_factors_v3";
pub const DEFAULT_CC_FROM_DATE: &str = "2026-04-29";
pub const DEFAULT_CC_TO_DATE: &str = "2026-05-15";
pub const DEFAULT_CC_SYMBOLS: &str = "CCUSDT";
pub const DEFAULT_CC_DATA_ROOT: &str = "data/ccusdt/v1";

const GUARDRAIL: &str =
    "research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim";
const PRICE_SCALE: f64 = 1_000_000_000.0;
const LEVELS: [usize; 6] = [1, 2, 3, 5, 10, 25];
const ROLLING_EVENTS: usize = 10;
const SPEARMAN_MAX_ROWS: usize = 250_000;
const EPS: f64 = 1e-12;
const REPLACE_RETRIES: usize = 40;
const REPLACE_RETRY_MS: u64 = 100;
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct CcFixedEventConfig {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub doc_dir: PathBuf,
    pub output_prefix: String,
    pub panel_dataset: String,
    pub report_name: String,
    pub market_label: String,
    pub reproduce_command: String,
    pub from_date: NaiveDate,
    pub to_date: NaiveDate,
    pub symbols: String,
    pub run_tag: String,
    pub part_rows: usize,
    pub trade_match_window_us: u64,
    pub cross_venue_tolerance_us: u64,
    pub max_symbol_days: Option<usize>,
    pub skip_panel: bool,
    pub skip_validation: bool,
    pub skip_episode_overlay: bool,
}

impl Default for CcFixedEventConfig {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_CC_DATA_ROOT),
            date_dir: PathBuf::from("date"),
            doc_dir: PathBuf::from("docs/markets/ccusdt"),
            output_prefix: "ccusdt_v1_fixed_event_factors".to_string(),
            panel_dataset: "ccusdt_v1_fixed_event_factor_panel".to_string(),
            report_name: "v1-fixed-event-orderbook-factors-v3.md".to_string(),
            market_label: "CCUSDT".to_string(),
            reproduce_command:
                "cargo run -p cex_l2_research --bin tardis_bullish_fixed_factor_panel --release"
                    .to_string(),
            from_date: parse_default_date(DEFAULT_CC_FROM_DATE),
            to_date: parse_default_date(DEFAULT_CC_TO_DATE),
            symbols: DEFAULT_CC_SYMBOLS.to_string(),
            run_tag: DEFAULT_CC_RUN_TAG.to_string(),
            part_rows: 25_000,
            trade_match_window_us: 2_000_000,
            cross_venue_tolerance_us: 2_000_000,
            max_symbol_days: None,
            skip_panel: false,
            skip_validation: false,
            skip_episode_overlay: false,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct CcFixedEventSummary {
    pub run_tag: String,
    pub symbol_days: usize,
    pub panel_rows: usize,
    pub quality_rows: usize,
    pub factor_param_rows: usize,
    pub path_ranking_rows: usize,
    pub stability_rows: usize,
    pub negative_control_rows: usize,
    pub spearman_rows: usize,
    pub episode_overlay_rows: usize,
    pub quality_csv: String,
    pub factor_params_csv: String,
    pub path_ranking_csv: String,
    pub stability_csv: String,
    pub negative_controls_csv: String,
    pub spearman_csv: String,
    pub episode_overlay_csv: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    quality_csv: PathBuf,
    factor_params_csv: PathBuf,
    path_ranking_csv: PathBuf,
    stability_csv: PathBuf,
    negative_controls_csv: PathBuf,
    spearman_csv: PathBuf,
    episode_overlay_csv: PathBuf,
    report_md: PathBuf,
}

impl Paths {
    fn new(config: &CcFixedEventConfig) -> Self {
        Self {
            quality_csv: config.date_dir.join(format!(
                "{}_quality_{}.csv",
                config.output_prefix, config.run_tag
            )),
            factor_params_csv: config.date_dir.join(format!(
                "{}_factor_params_{}.csv",
                config.output_prefix, config.run_tag
            )),
            path_ranking_csv: config.date_dir.join(format!(
                "{}_path_ranking_{}.csv",
                config.output_prefix, config.run_tag
            )),
            stability_csv: config.date_dir.join(format!(
                "{}_stability_{}.csv",
                config.output_prefix, config.run_tag
            )),
            negative_controls_csv: config.date_dir.join(format!(
                "{}_negative_controls_{}.csv",
                config.output_prefix, config.run_tag
            )),
            spearman_csv: config.date_dir.join(format!(
                "{}_spearman_{}.csv",
                config.output_prefix, config.run_tag
            )),
            episode_overlay_csv: config.date_dir.join(format!(
                "{}_episode_overlay_{}.csv",
                config.output_prefix, config.run_tag
            )),
            report_md: config.doc_dir.join(&config.report_name),
        }
    }
}

#[derive(Debug, Clone)]
struct SymbolDayJob {
    symbol: String,
    date: NaiveDate,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Side {
    Bid,
    Ask,
}

impl Side {
    fn parse(raw: &str) -> Self {
        match raw.to_ascii_lowercase().as_str() {
            "bid" | "buy" | "bids" => Self::Bid,
            _ => Self::Ask,
        }
    }

    fn trade_side_for_execution(self) -> &'static str {
        match self {
            Self::Bid => "sell",
            Self::Ask => "buy",
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
struct RawIncrementalRow {
    exchange: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    is_snapshot: bool,
    side: String,
    price: f64,
    amount: f64,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct IncrementalUpdate {
    exchange: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    is_snapshot: bool,
    side: Side,
    price: f64,
    amount: f64,
}

impl From<RawIncrementalRow> for IncrementalUpdate {
    fn from(row: RawIncrementalRow) -> Self {
        Self {
            exchange: row.exchange,
            symbol: row.symbol,
            timestamp: row.timestamp,
            local_timestamp: row.local_timestamp,
            is_snapshot: row.is_snapshot,
            side: Side::parse(&row.side),
            price: row.price,
            amount: row.amount,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct RawTradeRow {
    exchange: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    id: String,
    side: String,
    price: f64,
    amount: f64,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct TradeState {
    timestamp: u64,
    local_timestamp: u64,
    id: String,
    side: String,
    price: f64,
    amount: f64,
    remaining: f64,
}

impl From<RawTradeRow> for TradeState {
    fn from(row: RawTradeRow) -> Self {
        let amount = row.amount.max(0.0);
        Self {
            timestamp: row.timestamp,
            local_timestamp: row.local_timestamp,
            id: row.id,
            side: row.side.to_ascii_lowercase(),
            price: row.price,
            amount,
            remaining: amount,
        }
    }
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize)]
pub struct Level {
    pub price: f64,
    pub amount: f64,
}

#[derive(Debug, Clone, Default)]
pub struct EventBook {
    bids: BTreeMap<i64, f64>,
    asks: BTreeMap<i64, f64>,
}

#[derive(Debug, Clone, Copy, Default)]
struct TopState {
    bid: Option<Level>,
    ask: Option<Level>,
}

impl EventBook {
    fn clear(&mut self) {
        self.bids.clear();
        self.asks.clear();
    }

    fn map_mut(&mut self, side: Side) -> &mut BTreeMap<i64, f64> {
        match side {
            Side::Bid => &mut self.bids,
            Side::Ask => &mut self.asks,
        }
    }

    fn map(&self, side: Side) -> &BTreeMap<i64, f64> {
        match side {
            Side::Bid => &self.bids,
            Side::Ask => &self.asks,
        }
    }

    fn amount_at(&self, side: Side, price: f64) -> Option<f64> {
        self.map(side).get(&price_key(price)).copied()
    }

    fn set_level(&mut self, side: Side, price: f64, amount: f64) {
        let key = price_key(price);
        if amount <= 0.0 {
            self.map_mut(side).remove(&key);
        } else {
            self.map_mut(side).insert(key, amount);
        }
    }

    fn replace_from_snapshot(&mut self, batch: &[IncrementalUpdate]) {
        self.clear();
        for update in batch {
            self.set_level(update.side, update.price, update.amount);
        }
    }

    fn top_levels(&self, side: Side, limit: usize) -> Vec<Level> {
        match side {
            Side::Bid => self
                .bids
                .iter()
                .rev()
                .take(limit)
                .map(|(price, amount)| Level {
                    price: key_price(*price),
                    amount: *amount,
                })
                .collect(),
            Side::Ask => self
                .asks
                .iter()
                .take(limit)
                .map(|(price, amount)| Level {
                    price: key_price(*price),
                    amount: *amount,
                })
                .collect(),
        }
    }

    fn top_state(&self) -> TopState {
        TopState {
            bid: self.top_levels(Side::Bid, 1).into_iter().next(),
            ask: self.top_levels(Side::Ask, 1).into_iter().next(),
        }
    }

    fn is_crossed(&self) -> bool {
        let best_bid = self.bids.iter().next_back().map(|(price, _)| *price);
        let best_ask = self.asks.iter().next().map(|(price, _)| *price);
        matches!((best_bid, best_ask), (Some(bid), Some(ask)) if bid >= ask)
    }

    fn cleanup_crossed(&mut self, updated_side: Side) -> usize {
        let mut removed = 0usize;
        loop {
            let best_bid = self.bids.iter().next_back().map(|(price, _)| *price);
            let best_ask = self.asks.iter().next().map(|(price, _)| *price);
            let (Some(best_bid), Some(best_ask)) = (best_bid, best_ask) else {
                break;
            };
            if best_bid < best_ask {
                break;
            }
            match updated_side {
                Side::Bid => {
                    self.asks.remove(&best_ask);
                }
                Side::Ask => {
                    self.bids.remove(&best_bid);
                }
            }
            removed += 1;
        }
        removed
    }
}

#[derive(Debug, Clone, Copy, Default)]
struct UpdateStats {
    limit_add_bid_amount: f64,
    limit_add_ask_amount: f64,
    replenish_bid_amount: f64,
    replenish_ask_amount: f64,
    decrease_bid_amount: f64,
    decrease_ask_amount: f64,
    remove_bid_amount: f64,
    remove_ask_amount: f64,
    execute_bid_amount: f64,
    execute_ask_amount: f64,
    cancel_bid_amount: f64,
    cancel_ask_amount: f64,
    noop_updates: usize,
    create_updates: usize,
    replenish_updates: usize,
    decrease_updates: usize,
    remove_updates: usize,
}

impl UpdateStats {
    fn depletion_bid_amount(&self) -> f64 {
        self.decrease_bid_amount + self.remove_bid_amount
    }

    fn depletion_ask_amount(&self) -> f64 {
        self.decrease_ask_amount + self.remove_ask_amount
    }

    fn depletion_total(&self) -> f64 {
        self.depletion_bid_amount() + self.depletion_ask_amount()
    }

    fn matched_total(&self) -> f64 {
        self.execute_bid_amount + self.execute_ask_amount
    }

    fn replenish_total(&self) -> f64 {
        self.replenish_bid_amount + self.replenish_ask_amount
    }

    fn cancel_total(&self) -> f64 {
        self.cancel_bid_amount + self.cancel_ask_amount
    }
}

#[derive(Debug, Clone, Copy, Default)]
struct TradeWindowStats {
    trade_count: usize,
    buy_count: usize,
    sell_count: usize,
    buy_amount: f64,
    sell_amount: f64,
    notional_quote: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventPanelRow {
    pub run_tag: String,
    pub date: String,
    pub symbol: String,
    pub exchange: String,
    pub timestamp: u64,
    pub local_timestamp: u64,
    pub event_index: usize,
    pub is_snapshot_batch: bool,
    pub factor_eligible: bool,
    pub execute_cancel_confidence: String,
    pub batch_rows: usize,
    pub crossed_levels_removed: usize,
    pub noop_updates: usize,
    pub create_updates: usize,
    pub replenish_updates: usize,
    pub decrease_updates: usize,
    pub remove_updates: usize,
    pub best_bid_price: Option<f64>,
    pub best_bid_amount: Option<f64>,
    pub best_ask_price: Option<f64>,
    pub best_ask_amount: Option<f64>,
    pub mid_price: Option<f64>,
    pub spread_bps: Option<f64>,
    pub microprice: Option<f64>,
    pub microprice_dev_bps: Option<f64>,
    pub bid_levels: usize,
    pub ask_levels: usize,
    pub bid_depth_1: f64,
    pub ask_depth_1: f64,
    pub bid_depth_2: f64,
    pub ask_depth_2: f64,
    pub bid_depth_3: f64,
    pub ask_depth_3: f64,
    pub bid_depth_5: f64,
    pub ask_depth_5: f64,
    pub bid_depth_10: f64,
    pub ask_depth_10: f64,
    pub bid_depth_25: f64,
    pub ask_depth_25: f64,
    pub queue_imbalance_1: Option<f64>,
    pub queue_imbalance_5: Option<f64>,
    pub queue_imbalance_25: Option<f64>,
    pub limit_add_bid_amount: f64,
    pub limit_add_ask_amount: f64,
    pub replenish_bid_amount: f64,
    pub replenish_ask_amount: f64,
    pub decrease_bid_amount: f64,
    pub decrease_ask_amount: f64,
    pub remove_bid_amount: f64,
    pub remove_ask_amount: f64,
    pub depletion_bid_amount: f64,
    pub depletion_ask_amount: f64,
    pub execute_bid_amount: f64,
    pub execute_ask_amount: f64,
    pub cancel_bid_amount: f64,
    pub cancel_ask_amount: f64,
    pub event_matched_rate: Option<f64>,
    pub trade_window_count: usize,
    pub trade_buy_amount: f64,
    pub trade_sell_amount: f64,
    pub trade_notional_quote: f64,
    pub trade_flow_imbalance: Option<f64>,
    pub trade_arrival_alignment: Option<f64>,
    pub ofi_l1_raw: f64,
    pub ofi_l1_depth_norm: Option<f64>,
    pub mlofi_raw_l1: f64,
    pub mlofi_raw_l2: f64,
    pub mlofi_raw_l3: f64,
    pub mlofi_raw_l5: f64,
    pub mlofi_raw_l10: f64,
    pub mlofi_raw_l25: f64,
    pub mlofi_norm_l1: Option<f64>,
    pub mlofi_norm_l2: Option<f64>,
    pub mlofi_norm_l3: Option<f64>,
    pub mlofi_norm_l5: Option<f64>,
    pub mlofi_norm_l10: Option<f64>,
    pub mlofi_norm_l25: Option<f64>,
    pub mlofi_roll10_l1: f64,
    pub mlofi_roll10_l2: f64,
    pub mlofi_roll10_l3: f64,
    pub mlofi_roll10_l5: f64,
    pub mlofi_roll10_l10: f64,
    pub mlofi_roll10_l25: f64,
    pub queue_depletion_intensity: Option<f64>,
    pub replenish_intensity: Option<f64>,
    pub cancellation_withdrawal_intensity: Option<f64>,
    pub liquidity_shock_score: Option<f64>,
    pub bid_top_levels_json: String,
    pub ask_top_levels_json: String,
    pub guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QualityRow {
    pub run_tag: String,
    pub date: String,
    pub symbol: String,
    pub incremental_path: String,
    pub trades_path: String,
    pub panel_dir: String,
    pub status: String,
    pub raw_update_rows: usize,
    pub event_count: usize,
    pub replay_state_expected_rows: Option<usize>,
    pub replay_panel_row_delta: Option<i64>,
    pub snapshot_count: usize,
    pub trade_count: usize,
    pub crossed_levels_removed: usize,
    pub book_disorder_rows: usize,
    pub matched_depletion_amount: f64,
    pub total_depletion_amount: f64,
    pub matched_amount_rate: Option<f64>,
    pub unmatched_decrease_rate: Option<f64>,
    pub trade_side_price_inconsistent_rows: usize,
    pub execute_cancel_split_confidence: String,
    pub panel_part_files: usize,
    pub error: String,
    pub guardrail: String,
}

#[derive(Debug, Clone, Default)]
struct DayStats {
    raw_update_rows: usize,
    event_count: usize,
    snapshot_count: usize,
    trade_count: usize,
    crossed_levels_removed: usize,
    book_disorder_rows: usize,
    matched_depletion_amount: f64,
    total_depletion_amount: f64,
    trade_side_price_inconsistent_rows: usize,
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct ReplayManifestRow {
    run_tag: String,
    date: String,
    symbol: String,
    raw_path: String,
    output_path: String,
    part_files: usize,
    raw_rows_read: usize,
    replay_rows: usize,
    first_local_timestamp: Option<u64>,
    last_local_timestamp: Option<u64>,
    status: String,
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
struct FeatureRow {
    date: String,
    symbol: String,
    local_timestamp: u64,
    event_index: usize,
    hour_utc: String,
    mid_price: f64,
    spread_bps: f64,
    factor_eligible: bool,
    ofi_l1_depth_norm: f64,
    mlofi_norm: [f64; 6],
    mlofi_roll10: [f64; 6],
    queue_imbalance_1: f64,
    queue_imbalance_5: f64,
    queue_imbalance_25: f64,
    microprice_dev_bps: f64,
    queue_depletion_intensity: f64,
    replenish_intensity: f64,
    cancellation_withdrawal_intensity: f64,
    trade_arrival_alignment: f64,
    liquidity_shock_score: f64,
    low_confidence_split: bool,
    cross_venue_mlofi_lead_lag: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FactorParamRow {
    pub run_tag: String,
    pub fit_scope: String,
    pub fold: String,
    pub symbol: String,
    pub feature_name: String,
    pub train_rows: usize,
    pub valid_rows: usize,
    pub median: f64,
    pub mad: f64,
    pub q20: f64,
    pub q80: f64,
    pub low_gate_threshold: Option<f64>,
    pub high_gate_threshold: Option<f64>,
    pub gate_policy: String,
    pub mlofi_weight: f64,
    pub liquidity_shock_threshold: f64,
    pub first_passage_barrier_bps: f64,
    pub event_horizons_json: String,
    pub nonzero_mid_move_median_events: f64,
    pub guardrail: String,
}

#[derive(Debug, Clone)]
struct FeatureParam {
    feature_name: String,
    median: f64,
    mad: f64,
    q20: f64,
    q80: f64,
    low_gate_threshold: Option<f64>,
    high_gate_threshold: Option<f64>,
    gate_policy: String,
    mlofi_weight: f64,
}

#[derive(Debug, Clone)]
struct FoldFit {
    fold: String,
    symbol: String,
    train_rows: usize,
    valid_rows: usize,
    features: HashMap<String, FeatureParam>,
    horizons: Vec<usize>,
    barrier_bps: f64,
    shock_threshold: f64,
    nonzero_mid_move_median_events: f64,
    mlofi_weights: [f64; 6],
    valid_start: u64,
    valid_end: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathRankingRow {
    pub run_tag: String,
    pub fit_scope: String,
    pub fold: String,
    pub symbol: String,
    pub feature_name: String,
    pub feature_family: String,
    pub gate: String,
    pub side: String,
    pub horizon_events: usize,
    pub first_passage_barrier_bps: f64,
    pub validation_rows: usize,
    pub selected_rows: usize,
    pub selected_rate: f64,
    pub favorable_rate: f64,
    pub adverse_rate: f64,
    pub favorable_minus_adverse_rate: f64,
    pub side_return_bps_mean: f64,
    pub drawup_drawdown_asymmetry_bps_mean: f64,
    pub nonoverlap_buckets: usize,
    pub positive_bucket_rate: f64,
    pub score: f64,
    pub guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StabilityRow {
    pub run_tag: String,
    pub fold: String,
    pub symbol: String,
    pub feature_name: String,
    pub gate: String,
    pub side: String,
    pub horizon_events: usize,
    pub group_scope: String,
    pub group_value: String,
    pub rows: usize,
    pub favorable_minus_adverse_rate: f64,
    pub side_return_bps_mean: f64,
    pub drawup_drawdown_asymmetry_bps_mean: f64,
    pub guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NegativeControlRow {
    pub run_tag: String,
    pub control_type: String,
    pub fold: String,
    pub symbol: String,
    pub feature_name: String,
    pub gate: String,
    pub side: String,
    pub horizon_events: usize,
    pub selected_rows: usize,
    pub favorable_minus_adverse_rate: f64,
    pub side_return_bps_mean: f64,
    pub control_note: String,
    pub guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpearmanRow {
    pub run_tag: String,
    pub scope: String,
    pub fold: String,
    pub symbol: String,
    pub feature_name: String,
    pub horizon_events: usize,
    pub group_value: String,
    pub rows: usize,
    pub spearman: f64,
    pub target: String,
    pub guardrail: String,
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
struct EpisodeTradeInputRow {
    run_tag: String,
    fold: String,
    date: String,
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    notional_quote: f64,
    tp_bps: u32,
    sl_bps: u32,
    timeout_seconds: u32,
    signal_local_timestamp: u64,
    entry_local_timestamp: u64,
    exit_local_timestamp: u64,
    entry_mid: f64,
    exit_mid: f64,
    exit_reason: String,
    gross_bps: f64,
    cost_bps: f64,
    queue_penalty_bps: f64,
    fill_realism_score: f64,
    net_bps: f64,
    pnl_quote: f64,
}

#[derive(Debug, Clone, Default)]
struct EpisodeAgg {
    trades: usize,
    wins: usize,
    net_bps_sum: f64,
    pnl_quote_sum: f64,
    cost_bps_sum: f64,
    queue_penalty_bps_sum: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EpisodeOverlayRow {
    pub run_tag: String,
    pub fold: String,
    pub symbol: String,
    pub side: String,
    pub execution_model: String,
    pub overlay_state: String,
    pub trades: usize,
    pub net_bps_mean: f64,
    pub win_rate: f64,
    pub pnl_quote_sum: f64,
    pub cost_bps_mean: f64,
    pub queue_penalty_bps_mean: f64,
    pub guardrail: String,
}

#[derive(Debug, Clone, Default)]
struct PathMetric {
    rows: usize,
    favorable: usize,
    adverse: usize,
    side_return_sum: f64,
    asymmetry_sum: f64,
    bucket_rows: BTreeMap<usize, (usize, f64)>,
}

impl PathMetric {
    fn add(&mut self, outcome: PathOutcome, bucket: usize) {
        self.rows += 1;
        if outcome.favorable_first {
            self.favorable += 1;
        }
        if outcome.adverse_first {
            self.adverse += 1;
        }
        self.side_return_sum += outcome.side_return_bps;
        self.asymmetry_sum += outcome.asymmetry_bps;
        let entry = self.bucket_rows.entry(bucket).or_insert((0, 0.0));
        entry.0 += 1;
        entry.1 += outcome.side_return_bps;
    }

    fn selected_rate(&self, valid_rows: usize) -> f64 {
        rate(self.rows, valid_rows)
    }

    fn favorable_rate(&self) -> f64 {
        rate(self.favorable, self.rows)
    }

    fn adverse_rate(&self) -> f64 {
        rate(self.adverse, self.rows)
    }

    fn favorable_minus_adverse_rate(&self) -> f64 {
        self.favorable_rate() - self.adverse_rate()
    }

    fn side_return_mean(&self) -> f64 {
        if self.rows == 0 {
            0.0
        } else {
            self.side_return_sum / self.rows as f64
        }
    }

    fn asymmetry_mean(&self) -> f64 {
        if self.rows == 0 {
            0.0
        } else {
            self.asymmetry_sum / self.rows as f64
        }
    }

    fn positive_bucket_rate(&self) -> f64 {
        if self.bucket_rows.is_empty() {
            return 0.0;
        }
        let positive = self
            .bucket_rows
            .values()
            .filter(|(rows, sum)| *rows > 0 && *sum / *rows as f64 > 0.0)
            .count();
        positive as f64 / self.bucket_rows.len() as f64
    }

    fn score(&self) -> f64 {
        self.side_return_mean()
            + 12.0 * self.favorable_minus_adverse_rate()
            + self.asymmetry_mean()
            + 5.0 * (self.positive_bucket_rate() - 0.5)
    }
}

#[derive(Debug, Clone, Copy)]
struct PathOutcome {
    favorable_first: bool,
    adverse_first: bool,
    side_return_bps: f64,
    asymmetry_bps: f64,
}

#[derive(Debug, Clone)]
struct CandidateKey {
    fold: String,
    symbol: String,
    feature_name: String,
    gate: String,
    side: String,
    horizon_events: usize,
    low_gate_threshold: Option<f64>,
    high_gate_threshold: Option<f64>,
}

pub fn run_cc_fixed_event_orderbook(config: &CcFixedEventConfig) -> Result<CcFixedEventSummary> {
    if config.from_date > config.to_date {
        bail!(
            "--from-date {} is after --to-date {}",
            config.from_date,
            config.to_date
        );
    }
    if config.part_rows == 0 {
        bail!("--part-rows must be >= 1");
    }
    fs::create_dir_all(&config.date_dir)?;
    fs::create_dir_all(&config.doc_dir)?;

    let paths = Paths::new(config);
    let symbols = parse_symbol_list(&config.symbols);
    if symbols.is_empty() {
        bail!("at least one symbol is required");
    }
    let jobs = build_jobs(
        &symbols,
        config.from_date,
        config.to_date,
        config.max_symbol_days,
    );
    let replay_manifest = load_replay_expected(config).unwrap_or_default();

    let mut quality_rows = Vec::new();
    let mut feature_rows = Vec::new();
    let mut panel_rows_total = 0usize;
    if !config.skip_panel {
        for job in &jobs {
            eprintln!("[cc] panel {} {}", job.date, job.symbol);
            match build_symbol_day_panel(config, job, &replay_manifest) {
                Ok((quality, features)) => {
                    panel_rows_total += quality.event_count;
                    feature_rows.extend(features);
                    quality_rows.push(quality);
                }
                Err(err) => {
                    quality_rows.push(QualityRow {
                        run_tag: config.run_tag.clone(),
                        date: job.date.to_string(),
                        symbol: job.symbol.clone(),
                        incremental_path: path_string(&incremental_path(
                            &config.data_root,
                            &job.symbol,
                            job.date,
                        )),
                        trades_path: path_string(&trades_path(
                            &config.data_root,
                            &job.symbol,
                            job.date,
                        )),
                        panel_dir: path_string(&panel_output_dir(
                            &config.data_root,
                            &config.panel_dataset,
                            &config.run_tag,
                            &job.symbol,
                            job.date,
                        )),
                        status: "error".to_string(),
                        raw_update_rows: 0,
                        event_count: 0,
                        replay_state_expected_rows: replay_manifest
                            .get(&(job.date.to_string(), job.symbol.clone()))
                            .copied(),
                        replay_panel_row_delta: None,
                        snapshot_count: 0,
                        trade_count: 0,
                        crossed_levels_removed: 0,
                        book_disorder_rows: 0,
                        matched_depletion_amount: 0.0,
                        total_depletion_amount: 0.0,
                        matched_amount_rate: None,
                        unmatched_decrease_rate: None,
                        trade_side_price_inconsistent_rows: 0,
                        execute_cancel_split_confidence: "error".to_string(),
                        panel_part_files: 0,
                        error: err.to_string(),
                        guardrail: GUARDRAIL.to_string(),
                    });
                }
            }
        }
    } else {
        let loaded = load_existing_panel_features(config, &jobs)?;
        panel_rows_total = loaded.len();
        feature_rows = loaded;
        if paths.quality_csv.exists() {
            quality_rows = load_csv_rows::<QualityRow>(&paths.quality_csv)?;
        }
    }
    add_cross_venue_mlofi(&mut feature_rows, config.cross_venue_tolerance_us);
    write_csv_atomic(&paths.quality_csv, &quality_rows)?;

    let (factor_params, rankings, stability, controls, spearman, top_candidates) =
        if config.skip_validation {
            (
                Vec::new(),
                Vec::new(),
                Vec::new(),
                Vec::new(),
                Vec::new(),
                Vec::new(),
            )
        } else {
            validate_event_features(config, &feature_rows)?
        };
    write_csv_atomic(&paths.factor_params_csv, &factor_params)?;
    write_csv_atomic(&paths.path_ranking_csv, &rankings)?;
    write_csv_atomic(&paths.stability_csv, &stability)?;
    write_csv_atomic(&paths.negative_controls_csv, &controls)?;
    write_csv_atomic(&paths.spearman_csv, &spearman)?;

    let episode_overlay = if config.skip_episode_overlay {
        Vec::new()
    } else {
        build_episode_overlay(config, &feature_rows, &top_candidates)?
    };
    write_csv_atomic(&paths.episode_overlay_csv, &episode_overlay)?;

    write_report(
        config,
        &paths,
        &quality_rows,
        &factor_params,
        &rankings,
        &stability,
        &controls,
        &spearman,
        &episode_overlay,
    )?;

    Ok(CcFixedEventSummary {
        run_tag: config.run_tag.clone(),
        symbol_days: jobs.len(),
        panel_rows: panel_rows_total,
        quality_rows: quality_rows.len(),
        factor_param_rows: factor_params.len(),
        path_ranking_rows: rankings.len(),
        stability_rows: stability.len(),
        negative_control_rows: controls.len(),
        spearman_rows: spearman.len(),
        episode_overlay_rows: episode_overlay.len(),
        quality_csv: path_string(&paths.quality_csv),
        factor_params_csv: path_string(&paths.factor_params_csv),
        path_ranking_csv: path_string(&paths.path_ranking_csv),
        stability_csv: path_string(&paths.stability_csv),
        negative_controls_csv: path_string(&paths.negative_controls_csv),
        spearman_csv: path_string(&paths.spearman_csv),
        episode_overlay_csv: path_string(&paths.episode_overlay_csv),
        report_md: path_string(&paths.report_md),
    })
}

fn build_symbol_day_panel(
    config: &CcFixedEventConfig,
    job: &SymbolDayJob,
    replay_manifest: &HashMap<(String, String), usize>,
) -> Result<(QualityRow, Vec<FeatureRow>)> {
    let incremental_path = incremental_path(&config.data_root, &job.symbol, job.date);
    let trades_path = trades_path(&config.data_root, &job.symbol, job.date);
    if !incremental_path.exists() {
        bail!("missing incremental file {}", incremental_path.display());
    }
    let mut trades = read_trades(&trades_path)?;
    let mut book = EventBook::default();
    let mut rows = Vec::<EventPanelRow>::new();
    let mut stats = DayStats {
        trade_count: trades.len(),
        ..DayStats::default()
    };
    let mut rolling = RollingMlofi::default();
    let mut event_index = 0usize;
    let mut previous_local_timestamp = None::<u64>;
    let mut seen_snapshot = false;
    let mut batch = Vec::<IncrementalUpdate>::new();

    let file = File::open(&incremental_path)
        .with_context(|| format!("failed to open {}", incremental_path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = csv::Reader::from_reader(decoder);
    for record in reader.deserialize::<RawIncrementalRow>() {
        let update: IncrementalUpdate = record
            .with_context(|| format!("failed to parse {}", incremental_path.display()))?
            .into();
        stats.raw_update_rows += 1;
        if !seen_snapshot && !update.is_snapshot {
            continue;
        }
        if let Some(prev) = previous_local_timestamp {
            if update.local_timestamp < prev {
                stats.book_disorder_rows += 1;
            }
            if update.local_timestamp != prev && !batch.is_empty() {
                event_index += 1;
                let row = process_batch(
                    config,
                    job,
                    &mut book,
                    &mut trades,
                    &batch,
                    event_index,
                    &mut stats,
                    &mut rolling,
                    false,
                );
                rows.push(row);
                batch.clear();
            }
        }
        if update.is_snapshot {
            seen_snapshot = true;
        }
        previous_local_timestamp = Some(update.local_timestamp);
        batch.push(update);
    }
    if !batch.is_empty() {
        event_index += 1;
        let row = process_batch(
            config,
            job,
            &mut book,
            &mut trades,
            &batch,
            event_index,
            &mut stats,
            &mut rolling,
            false,
        );
        rows.push(row);
    }

    let matched_rate = if stats.total_depletion_amount > EPS {
        Some(stats.matched_depletion_amount / stats.total_depletion_amount)
    } else {
        None
    };
    let unmatched_rate = matched_rate.map(|rate| (1.0 - rate).max(0.0));
    let confidence =
        if stats.total_depletion_amount <= EPS && stats.snapshot_count == stats.event_count {
            "not_applicable_snapshot_rebuild"
        } else if matched_rate.unwrap_or(1.0) < 0.60 {
            "low_confidence"
        } else {
            "normal"
        };
    for row in &mut rows {
        row.execute_cancel_confidence = confidence.to_string();
    }
    let panel_dir = panel_output_dir(
        &config.data_root,
        &config.panel_dataset,
        &config.run_tag,
        &job.symbol,
        job.date,
    );
    let part_files = write_panel_parts(&panel_dir, &rows, config.part_rows)?;
    let features = rows
        .iter()
        .filter_map(|row| feature_from_panel(row))
        .collect::<Vec<_>>();
    let replay_rows = replay_manifest
        .get(&(job.date.to_string(), job.symbol.clone()))
        .copied();
    let delta = replay_rows.map(|expected| rows.len() as i64 - expected as i64);
    let status = quality_status(&stats, confidence, delta);
    Ok((
        QualityRow {
            run_tag: config.run_tag.clone(),
            date: job.date.to_string(),
            symbol: job.symbol.clone(),
            incremental_path: path_string(&incremental_path),
            trades_path: path_string(&trades_path),
            panel_dir: path_string(&panel_dir),
            status,
            raw_update_rows: stats.raw_update_rows,
            event_count: stats.event_count,
            replay_state_expected_rows: replay_rows,
            replay_panel_row_delta: delta,
            snapshot_count: stats.snapshot_count,
            trade_count: stats.trade_count,
            crossed_levels_removed: stats.crossed_levels_removed,
            book_disorder_rows: stats.book_disorder_rows,
            matched_depletion_amount: stats.matched_depletion_amount,
            total_depletion_amount: stats.total_depletion_amount,
            matched_amount_rate: matched_rate,
            unmatched_decrease_rate: unmatched_rate,
            trade_side_price_inconsistent_rows: stats.trade_side_price_inconsistent_rows,
            execute_cancel_split_confidence: confidence.to_string(),
            panel_part_files: part_files,
            error: String::new(),
            guardrail: GUARDRAIL.to_string(),
        },
        features,
    ))
}

fn quality_status(
    stats: &DayStats,
    confidence: &str,
    replay_panel_row_delta: Option<i64>,
) -> String {
    let has_warning = stats.book_disorder_rows > 0
        || stats.crossed_levels_removed > 0
        || stats.trade_side_price_inconsistent_rows > 0
        || replay_panel_row_delta.is_some_and(|delta| delta != 0)
        || confidence == "low_confidence";
    if has_warning {
        "completed_with_quality_warnings".to_string()
    } else {
        "completed".to_string()
    }
}

fn process_batch(
    config: &CcFixedEventConfig,
    job: &SymbolDayJob,
    book: &mut EventBook,
    trades: &mut [TradeState],
    batch: &[IncrementalUpdate],
    event_index: usize,
    stats: &mut DayStats,
    rolling: &mut RollingMlofi,
    _snapshot_reset_batch: bool,
) -> EventPanelRow {
    stats.event_count += 1;
    let snapshot_batch = batch.iter().any(|row| row.is_snapshot);
    if snapshot_batch {
        stats.snapshot_count += 1;
    }
    let before_bid = book.top_levels(Side::Bid, 25);
    let before_ask = book.top_levels(Side::Ask, 25);
    let before_depth_25 = depth_from_levels(&before_bid, 25) + depth_from_levels(&before_ask, 25);
    let before_has_book = !before_bid.is_empty() && !before_ask.is_empty();
    let mut update_stats = UpdateStats::default();
    let mut crossed_removed = 0usize;

    if snapshot_batch {
        book.replace_from_snapshot(batch);
    } else {
        let mut last_side = batch.first().map(|row| row.side).unwrap_or(Side::Bid);
        for update in batch {
            last_side = update.side;
            let prev_amount = book.amount_at(update.side, update.price).unwrap_or(0.0);
            classify_update(
                &mut update_stats,
                update.side,
                prev_amount,
                update.amount,
                update.local_timestamp,
                update.price,
                trades,
                config.trade_match_window_us,
                stats,
            );
            book.set_level(update.side, update.price, update.amount);
        }
        crossed_removed += book.cleanup_crossed(last_side);
    }
    stats.crossed_levels_removed += crossed_removed;

    let after_bid = book.top_levels(Side::Bid, 25);
    let after_ask = book.top_levels(Side::Ask, 25);
    let crossed_after_cleanup = book.is_crossed();
    if crossed_after_cleanup {
        stats.book_disorder_rows += 1;
    }
    let top = book.top_state();
    let mid = top
        .bid
        .zip(top.ask)
        .map(|(bid, ask)| (bid.price + ask.price) * 0.5);
    let spread_bps = top
        .bid
        .zip(top.ask)
        .zip(mid)
        .and_then(|((bid, ask), mid)| finite((ask.price - bid.price) / mid * 10_000.0));
    let microprice = top.bid.zip(top.ask).and_then(|(bid, ask)| {
        let depth = bid.amount + ask.amount;
        (depth > EPS).then(|| (ask.price * bid.amount + bid.price * ask.amount) / depth)
    });
    let microprice_dev_bps = microprice.zip(mid).and_then(|(micro, mid)| {
        if mid > EPS {
            finite((micro - mid) / mid * 10_000.0)
        } else {
            None
        }
    });

    let tradable_book = mid.is_some() && !crossed_after_cleanup;
    let diff_ready = before_has_book && tradable_book && crossed_removed == 0;
    let mlofi_raw = if diff_ready {
        mlofi_levels(&before_bid, &before_ask, &after_bid, &after_ask)
    } else {
        [0.0; 6]
    };
    let mlofi_norm = if diff_ready {
        normalize_mlofi(&mlofi_raw, &before_bid, &before_ask, &after_bid, &after_ask)
    } else {
        [None; 6]
    };
    let roll = rolling.push(mlofi_norm);
    let ofi_l1 = mlofi_raw[0];
    let ofi_l1_depth_norm = mlofi_norm[0];

    let trade_stats = trade_window_stats(
        trades,
        batch.first().map(|row| row.local_timestamp).unwrap_or(0),
        config.trade_match_window_us,
    );
    let trade_flow_imbalance = if trade_stats.buy_amount + trade_stats.sell_amount > EPS {
        Some(
            (trade_stats.buy_amount - trade_stats.sell_amount)
                / (trade_stats.buy_amount + trade_stats.sell_amount),
        )
    } else {
        None
    };
    let trade_arrival_alignment = trade_flow_imbalance
        .and_then(|flow| ofi_l1_depth_norm.and_then(|ofi| finite(flow.signum() * ofi.signum())));

    stats.matched_depletion_amount += update_stats.matched_total();
    stats.total_depletion_amount += update_stats.depletion_total();

    let bid_depth_1 = depth_from_levels(&after_bid, 1);
    let ask_depth_1 = depth_from_levels(&after_ask, 1);
    let bid_depth_2 = depth_from_levels(&after_bid, 2);
    let ask_depth_2 = depth_from_levels(&after_ask, 2);
    let bid_depth_3 = depth_from_levels(&after_bid, 3);
    let ask_depth_3 = depth_from_levels(&after_ask, 3);
    let bid_depth_5 = depth_from_levels(&after_bid, 5);
    let ask_depth_5 = depth_from_levels(&after_ask, 5);
    let bid_depth_10 = depth_from_levels(&after_bid, 10);
    let ask_depth_10 = depth_from_levels(&after_ask, 10);
    let bid_depth_25 = depth_from_levels(&after_bid, 25);
    let ask_depth_25 = depth_from_levels(&after_ask, 25);
    let depth_total_25 = bid_depth_25 + ask_depth_25;
    let depletion_total = update_stats.depletion_total();
    let event_matched_rate = if depletion_total > EPS {
        Some(update_stats.matched_total() / depletion_total)
    } else {
        None
    };
    let replenish_total = update_stats.replenish_total();
    let cancel_total = update_stats.cancel_total();

    EventPanelRow {
        run_tag: config.run_tag.clone(),
        date: job.date.to_string(),
        symbol: job.symbol.clone(),
        exchange: batch
            .first()
            .map(|row| row.exchange.clone())
            .unwrap_or_else(|| "bullish".to_string()),
        timestamp: batch.first().map(|row| row.timestamp).unwrap_or(0),
        local_timestamp: batch.first().map(|row| row.local_timestamp).unwrap_or(0),
        event_index,
        is_snapshot_batch: snapshot_batch,
        factor_eligible: tradable_book
            && crossed_removed == 0
            && (!snapshot_batch || before_has_book),
        execute_cancel_confidence: "pending".to_string(),
        batch_rows: batch.len(),
        crossed_levels_removed: crossed_removed,
        noop_updates: update_stats.noop_updates,
        create_updates: update_stats.create_updates,
        replenish_updates: update_stats.replenish_updates,
        decrease_updates: update_stats.decrease_updates,
        remove_updates: update_stats.remove_updates,
        best_bid_price: top.bid.map(|level| level.price),
        best_bid_amount: top.bid.map(|level| level.amount),
        best_ask_price: top.ask.map(|level| level.price),
        best_ask_amount: top.ask.map(|level| level.amount),
        mid_price: mid,
        spread_bps,
        microprice,
        microprice_dev_bps,
        bid_levels: book.bids.len(),
        ask_levels: book.asks.len(),
        bid_depth_1,
        ask_depth_1,
        bid_depth_2,
        ask_depth_2,
        bid_depth_3,
        ask_depth_3,
        bid_depth_5,
        ask_depth_5,
        bid_depth_10,
        ask_depth_10,
        bid_depth_25,
        ask_depth_25,
        queue_imbalance_1: imbalance(bid_depth_1, ask_depth_1),
        queue_imbalance_5: imbalance(bid_depth_5, ask_depth_5),
        queue_imbalance_25: imbalance(bid_depth_25, ask_depth_25),
        limit_add_bid_amount: update_stats.limit_add_bid_amount,
        limit_add_ask_amount: update_stats.limit_add_ask_amount,
        replenish_bid_amount: update_stats.replenish_bid_amount,
        replenish_ask_amount: update_stats.replenish_ask_amount,
        decrease_bid_amount: update_stats.decrease_bid_amount,
        decrease_ask_amount: update_stats.decrease_ask_amount,
        remove_bid_amount: update_stats.remove_bid_amount,
        remove_ask_amount: update_stats.remove_ask_amount,
        depletion_bid_amount: update_stats.depletion_bid_amount(),
        depletion_ask_amount: update_stats.depletion_ask_amount(),
        execute_bid_amount: update_stats.execute_bid_amount,
        execute_ask_amount: update_stats.execute_ask_amount,
        cancel_bid_amount: update_stats.cancel_bid_amount,
        cancel_ask_amount: update_stats.cancel_ask_amount,
        event_matched_rate,
        trade_window_count: trade_stats.trade_count,
        trade_buy_amount: trade_stats.buy_amount,
        trade_sell_amount: trade_stats.sell_amount,
        trade_notional_quote: trade_stats.notional_quote,
        trade_flow_imbalance,
        trade_arrival_alignment,
        ofi_l1_raw: ofi_l1,
        ofi_l1_depth_norm,
        mlofi_raw_l1: mlofi_raw[0],
        mlofi_raw_l2: mlofi_raw[1],
        mlofi_raw_l3: mlofi_raw[2],
        mlofi_raw_l5: mlofi_raw[3],
        mlofi_raw_l10: mlofi_raw[4],
        mlofi_raw_l25: mlofi_raw[5],
        mlofi_norm_l1: mlofi_norm[0].and_then(finite),
        mlofi_norm_l2: mlofi_norm[1].and_then(finite),
        mlofi_norm_l3: mlofi_norm[2].and_then(finite),
        mlofi_norm_l5: mlofi_norm[3].and_then(finite),
        mlofi_norm_l10: mlofi_norm[4].and_then(finite),
        mlofi_norm_l25: mlofi_norm[5].and_then(finite),
        mlofi_roll10_l1: roll[0],
        mlofi_roll10_l2: roll[1],
        mlofi_roll10_l3: roll[2],
        mlofi_roll10_l5: roll[3],
        mlofi_roll10_l10: roll[4],
        mlofi_roll10_l25: roll[5],
        queue_depletion_intensity: safe_div_opt(
            depletion_total,
            depth_total_25.max(before_depth_25),
        ),
        replenish_intensity: safe_div_opt(replenish_total, depth_total_25.max(before_depth_25)),
        cancellation_withdrawal_intensity: safe_div_opt(
            cancel_total,
            depth_total_25.max(before_depth_25),
        ),
        liquidity_shock_score: safe_div_opt(depletion_total, before_depth_25.max(EPS)),
        bid_top_levels_json: book_levels_json(&after_bid),
        ask_top_levels_json: book_levels_json(&after_ask),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn classify_update(
    stats: &mut UpdateStats,
    side: Side,
    prev_amount: f64,
    new_amount: f64,
    local_timestamp: u64,
    price: f64,
    trades: &mut [TradeState],
    match_window_us: u64,
    day_stats: &mut DayStats,
) {
    if prev_amount <= EPS && new_amount > EPS {
        match side {
            Side::Bid => stats.limit_add_bid_amount += new_amount,
            Side::Ask => stats.limit_add_ask_amount += new_amount,
        }
        stats.create_updates += 1;
    } else if new_amount > prev_amount + EPS {
        let delta = new_amount - prev_amount;
        match side {
            Side::Bid => stats.replenish_bid_amount += delta,
            Side::Ask => stats.replenish_ask_amount += delta,
        }
        stats.replenish_updates += 1;
    } else if new_amount > EPS && new_amount + EPS < prev_amount {
        let delta = prev_amount - new_amount;
        match side {
            Side::Bid => stats.decrease_bid_amount += delta,
            Side::Ask => stats.decrease_ask_amount += delta,
        }
        let matched = match_depletion(
            trades,
            side,
            price,
            delta,
            local_timestamp,
            match_window_us,
            day_stats,
        );
        add_execution_cancel(stats, side, matched, delta - matched);
        stats.decrease_updates += 1;
    } else if new_amount <= EPS && prev_amount > EPS {
        let delta = prev_amount;
        match side {
            Side::Bid => stats.remove_bid_amount += delta,
            Side::Ask => stats.remove_ask_amount += delta,
        }
        let matched = match_depletion(
            trades,
            side,
            price,
            delta,
            local_timestamp,
            match_window_us,
            day_stats,
        );
        add_execution_cancel(stats, side, matched, delta - matched);
        stats.remove_updates += 1;
    } else {
        stats.noop_updates += 1;
    }
}

fn add_execution_cancel(stats: &mut UpdateStats, side: Side, matched: f64, unmatched: f64) {
    match side {
        Side::Bid => {
            stats.execute_bid_amount += matched.max(0.0);
            stats.cancel_bid_amount += unmatched.max(0.0);
        }
        Side::Ask => {
            stats.execute_ask_amount += matched.max(0.0);
            stats.cancel_ask_amount += unmatched.max(0.0);
        }
    }
}

fn match_depletion(
    trades: &mut [TradeState],
    side: Side,
    level_price: f64,
    amount: f64,
    local_timestamp: u64,
    match_window_us: u64,
    day_stats: &mut DayStats,
) -> f64 {
    if amount <= EPS || trades.is_empty() {
        return 0.0;
    }
    let start_ts = local_timestamp.saturating_sub(match_window_us);
    let mut remaining = amount;
    let start = lower_bound_trade_ts(trades, start_ts);
    for trade in trades.iter_mut().skip(start) {
        if trade.local_timestamp > local_timestamp {
            break;
        }
        if trade.remaining <= EPS {
            continue;
        }
        if trade.side != side.trade_side_for_execution() {
            continue;
        }
        let price_ok = match side {
            Side::Ask => trade.price + 1e-9 >= level_price,
            Side::Bid => trade.price <= level_price + 1e-9,
        };
        if !price_ok {
            day_stats.trade_side_price_inconsistent_rows += 1;
            continue;
        }
        let take = remaining.min(trade.remaining);
        trade.remaining -= take;
        remaining -= take;
        if remaining <= EPS {
            break;
        }
    }
    amount - remaining.max(0.0)
}

fn lower_bound_trade_ts(trades: &[TradeState], ts: u64) -> usize {
    let mut left = 0usize;
    let mut right = trades.len();
    while left < right {
        let mid = (left + right) / 2;
        if trades[mid].local_timestamp < ts {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}

fn trade_window_stats(
    trades: &[TradeState],
    local_timestamp: u64,
    window_us: u64,
) -> TradeWindowStats {
    if trades.is_empty() {
        return TradeWindowStats::default();
    }
    let start_ts = local_timestamp.saturating_sub(window_us);
    let start = lower_bound_trade_ts(trades, start_ts);
    let mut out = TradeWindowStats::default();
    for trade in trades.iter().skip(start) {
        if trade.local_timestamp > local_timestamp {
            break;
        }
        out.trade_count += 1;
        out.notional_quote += trade.price * trade.amount;
        if trade.side == "buy" {
            out.buy_count += 1;
            out.buy_amount += trade.amount;
        } else if trade.side == "sell" {
            out.sell_count += 1;
            out.sell_amount += trade.amount;
        }
    }
    out
}

#[derive(Debug, Clone, Default)]
struct RollingMlofi {
    rows: VecDeque<[Option<f64>; 6]>,
}

impl RollingMlofi {
    fn push(&mut self, values: [Option<f64>; 6]) -> [f64; 6] {
        self.rows.push_back(values);
        while self.rows.len() > ROLLING_EVENTS {
            self.rows.pop_front();
        }
        let mut out = [0.0; 6];
        for row in &self.rows {
            for idx in 0..6 {
                out[idx] += row[idx].unwrap_or(0.0);
            }
        }
        out
    }
}

#[cfg(test)]
fn replay_event_panel_from_updates(
    run_tag: &str,
    date: &str,
    symbol: &str,
    updates: &[IncrementalUpdate],
    trades: &[TradeState],
) -> Vec<EventPanelRow> {
    replay_event_panel_with_stats_from_updates(run_tag, date, symbol, updates, trades).0
}

#[cfg(test)]
fn replay_event_panel_with_stats_from_updates(
    run_tag: &str,
    date: &str,
    symbol: &str,
    updates: &[IncrementalUpdate],
    trades: &[TradeState],
) -> (Vec<EventPanelRow>, DayStats) {
    let mut ordered = updates.to_vec();
    ordered.sort_by(|a, b| {
        a.local_timestamp
            .cmp(&b.local_timestamp)
            .then_with(|| a.timestamp.cmp(&b.timestamp))
    });
    let config = CcFixedEventConfig {
        run_tag: run_tag.to_string(),
        trade_match_window_us: 2_000_000,
        ..CcFixedEventConfig::default()
    };
    let job = SymbolDayJob {
        symbol: symbol.to_string(),
        date: NaiveDate::parse_from_str(date, "%Y-%m-%d").expect("valid date"),
    };
    let mut book = EventBook::default();
    let mut mutable_trades = trades.to_vec();
    mutable_trades.sort_by_key(|trade| trade.local_timestamp);
    let mut stats = DayStats::default();
    let mut rolling = RollingMlofi::default();
    let mut out = Vec::new();
    let mut idx = 0usize;
    for batch in ordered.chunk_by(|a, b| a.local_timestamp == b.local_timestamp) {
        idx += 1;
        out.push(process_batch(
            &config,
            &job,
            &mut book,
            &mut mutable_trades,
            batch,
            idx,
            &mut stats,
            &mut rolling,
            false,
        ));
    }
    (out, stats)
}

fn mlofi_levels(
    before_bid: &[Level],
    before_ask: &[Level],
    after_bid: &[Level],
    after_ask: &[Level],
) -> [f64; 6] {
    let mut out = [0.0; 6];
    for (idx, level) in LEVELS.iter().enumerate() {
        let b0 = before_bid.get(level - 1).copied();
        let b1 = after_bid.get(level - 1).copied();
        let a0 = before_ask.get(level - 1).copied();
        let a1 = after_ask.get(level - 1).copied();
        out[idx] = cks_level_ofi(b0, b1, a0, a1);
    }
    out
}

fn normalize_mlofi(
    raw: &[f64; 6],
    before_bid: &[Level],
    before_ask: &[Level],
    after_bid: &[Level],
    after_ask: &[Level],
) -> [Option<f64>; 6] {
    let mut out = [None; 6];
    for (idx, level) in LEVELS.iter().enumerate() {
        let before_depth = before_bid.get(level - 1).map(|x| x.amount).unwrap_or(0.0)
            + before_ask.get(level - 1).map(|x| x.amount).unwrap_or(0.0);
        let after_depth = after_bid.get(level - 1).map(|x| x.amount).unwrap_or(0.0)
            + after_ask.get(level - 1).map(|x| x.amount).unwrap_or(0.0);
        out[idx] = safe_div_opt(raw[idx], before_depth.max(after_depth));
    }
    out
}

fn cks_level_ofi(
    before_bid: Option<Level>,
    after_bid: Option<Level>,
    before_ask: Option<Level>,
    after_ask: Option<Level>,
) -> f64 {
    bid_ofi(before_bid, after_bid) + ask_ofi(before_ask, after_ask)
}

fn bid_ofi(before: Option<Level>, after: Option<Level>) -> f64 {
    match (before, after) {
        (None, None) => 0.0,
        (None, Some(after)) => after.amount,
        (Some(before), None) => -before.amount,
        (Some(before), Some(after)) => {
            if after.price > before.price {
                after.amount
            } else if after.price < before.price {
                -before.amount
            } else {
                after.amount - before.amount
            }
        }
    }
}

fn ask_ofi(before: Option<Level>, after: Option<Level>) -> f64 {
    match (before, after) {
        (None, None) => 0.0,
        (None, Some(after)) => -after.amount,
        (Some(before), None) => before.amount,
        (Some(before), Some(after)) => {
            if after.price < before.price {
                -after.amount
            } else if after.price > before.price {
                before.amount
            } else {
                before.amount - after.amount
            }
        }
    }
}

fn validate_event_features(
    config: &CcFixedEventConfig,
    rows: &[FeatureRow],
) -> Result<(
    Vec<FactorParamRow>,
    Vec<PathRankingRow>,
    Vec<StabilityRow>,
    Vec<NegativeControlRow>,
    Vec<SpearmanRow>,
    Vec<CandidateKey>,
)> {
    if rows.is_empty() {
        return Ok((
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        ));
    }
    let by_symbol = rows_by_symbol(rows);
    let mut folds = load_folds(config)?;
    if folds.is_empty() {
        folds = build_default_folds(&by_symbol);
    }
    if folds.is_empty() {
        return Ok((
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        ));
    }
    let mut param_rows = Vec::new();
    let mut rankings = Vec::new();
    let mut fits = Vec::new();

    for fold in folds {
        let Some(symbol_rows) = by_symbol.get(&fold.symbol) else {
            continue;
        };
        let train = symbol_rows
            .iter()
            .copied()
            .filter(|row| {
                row.factor_eligible
                    && row.local_timestamp >= fold.train_start
                    && row.local_timestamp <= fold.train_end
            })
            .collect::<Vec<_>>();
        let valid = symbol_rows
            .iter()
            .copied()
            .filter(|row| {
                row.factor_eligible
                    && row.local_timestamp >= fold.valid_start
                    && row.local_timestamp <= fold.valid_end
            })
            .collect::<Vec<_>>();
        if train.len() < 100 || valid.len() < 50 {
            continue;
        }
        let fit = fit_fold(&fold, &train, &valid);
        param_rows.extend(factor_param_rows(config, &fit));
        rankings.extend(rank_fold(config, &fit, &valid, None, "base"));
        fits.push(fit);
    }

    rankings.sort_by(|a, b| {
        b.score
            .total_cmp(&a.score)
            .then_with(|| b.selected_rows.cmp(&a.selected_rows))
            .then_with(|| a.feature_name.cmp(&b.feature_name))
    });
    let top_candidates = top_candidates(&rankings, &fits);
    let stability = build_stability(config, &by_symbol, &top_candidates, &fits);
    let controls = build_negative_controls(config, &by_symbol, &top_candidates, &fits);
    let spearman = build_spearman_diagnostics(config, &by_symbol, &top_candidates, &fits);
    Ok((
        param_rows,
        rankings,
        stability,
        controls,
        spearman,
        top_candidates,
    ))
}

fn fit_fold(fold: &FoldSpec, train: &[&FeatureRow], valid: &[&FeatureRow]) -> FoldFit {
    let future_horizon = 50usize.min(train.len().saturating_sub(1)).max(10);
    let mlofi_weights = fit_mlofi_weights(train, future_horizon);
    let horizons = fit_event_horizons(train);
    let barrier = fit_first_passage_barrier(train, horizons.first().copied().unwrap_or(50));
    let shock_threshold = quantile(
        train
            .iter()
            .map(|row| row.liquidity_shock_score)
            .collect::<Vec<_>>(),
        0.80,
    )
    .unwrap_or(0.0);
    let nonzero_mid_move_median_events = median_mid_move_events(train).unwrap_or(0.0);
    let feature_values = collect_feature_values(train, &mlofi_weights, None);
    let mut features = HashMap::new();
    for (feature_name, values) in feature_values {
        let median = median(values.clone()).unwrap_or(0.0);
        let mad = robust_mad(&values, median);
        let q20 = quantile(values.clone(), 0.20).unwrap_or(median);
        let q80 = quantile(values.clone(), 0.80).unwrap_or(median);
        let (low_gate_threshold, high_gate_threshold, gate_policy) =
            derive_gate_thresholds(&feature_name, &values, q20, q80);
        let mlofi_weight = parse_mlofi_level(&feature_name)
            .map(|idx| mlofi_weights[idx])
            .unwrap_or(0.0);
        features.insert(
            feature_name.clone(),
            FeatureParam {
                feature_name,
                median,
                mad,
                q20,
                q80,
                low_gate_threshold,
                high_gate_threshold,
                gate_policy,
                mlofi_weight,
            },
        );
    }
    FoldFit {
        fold: fold.fold.clone(),
        symbol: fold.symbol.clone(),
        train_rows: train.len(),
        valid_rows: valid.len(),
        features,
        horizons,
        barrier_bps: barrier,
        shock_threshold,
        nonzero_mid_move_median_events,
        mlofi_weights,
        valid_start: fold.valid_start,
        valid_end: fold.valid_end,
    }
}

fn derive_gate_thresholds(
    feature_name: &str,
    values: &[f64],
    q20: f64,
    q80: f64,
) -> (Option<f64>, Option<f64>, String) {
    if (q80 - q20).abs() > EPS {
        return (Some(q20), Some(q80), "train_q20_q80".to_string());
    }
    if feature_name.starts_with("pos__") || feature_name.starts_with("neg__") {
        let nonzero = values
            .iter()
            .copied()
            .filter(|value| value.is_finite() && value.abs() > EPS)
            .collect::<Vec<_>>();
        if nonzero.len() >= 25 {
            return (
                None,
                quantile(nonzero, 0.80),
                "zero_inflated_nonzero_high_q80_low_skipped".to_string(),
            );
        }
    }
    (None, None, "degenerate_gate_skipped".to_string())
}

fn rank_fold(
    config: &CcFixedEventConfig,
    fit: &FoldFit,
    valid: &[&FeatureRow],
    control_feature_values: Option<&HashMap<String, Vec<f64>>>,
    ranking_scope: &str,
) -> Vec<PathRankingRow> {
    let mut out = Vec::new();
    if valid.len() < 10 {
        return out;
    }
    for feature in fit.features.values() {
        if feature.feature_name == "cross_venue_mlofi_combo" && control_feature_values.is_none() {
            // Cross-venue values are added in the control/stability passes where both symbols are available.
        }
        for (gate, side) in [("high_train_q80", "long"), ("low_train_q20", "short")] {
            for &horizon in &fit.horizons {
                let mut metric = PathMetric::default();
                let values = control_feature_values
                    .and_then(|map| map.get(&feature.feature_name))
                    .cloned();
                for (idx, row) in valid.iter().enumerate() {
                    let x = values
                        .as_ref()
                        .and_then(|items| items.get(idx).copied())
                        .unwrap_or_else(|| {
                            feature_value(row, &feature.feature_name, &fit.mlofi_weights)
                        });
                    if !gate_passes(
                        x,
                        gate,
                        feature.low_gate_threshold,
                        feature.high_gate_threshold,
                    ) {
                        continue;
                    }
                    if let Some(outcome) =
                        first_passage_outcome(valid, idx, horizon, side, fit.barrier_bps)
                    {
                        metric.add(outcome, row.event_index / horizon.max(1));
                    }
                }
                if metric.rows == 0 {
                    continue;
                }
                out.push(PathRankingRow {
                    run_tag: config.run_tag.clone(),
                    fit_scope: format!("train_only;ranking_scope={ranking_scope}"),
                    fold: fit.fold.clone(),
                    symbol: fit.symbol.clone(),
                    feature_name: feature.feature_name.clone(),
                    feature_family: feature_family(&feature.feature_name).to_string(),
                    gate: gate.to_string(),
                    side: side.to_string(),
                    horizon_events: horizon,
                    first_passage_barrier_bps: fit.barrier_bps,
                    validation_rows: valid.len(),
                    selected_rows: metric.rows,
                    selected_rate: metric.selected_rate(valid.len()),
                    favorable_rate: metric.favorable_rate(),
                    adverse_rate: metric.adverse_rate(),
                    favorable_minus_adverse_rate: metric.favorable_minus_adverse_rate(),
                    side_return_bps_mean: metric.side_return_mean(),
                    drawup_drawdown_asymmetry_bps_mean: metric.asymmetry_mean(),
                    nonoverlap_buckets: metric.bucket_rows.len(),
                    positive_bucket_rate: metric.positive_bucket_rate(),
                    score: metric.score(),
                    guardrail: GUARDRAIL.to_string(),
                });
            }
        }
    }
    out.sort_by(|a, b| b.score.total_cmp(&a.score));
    out
}

fn first_passage_outcome(
    rows: &[&FeatureRow],
    idx: usize,
    horizon: usize,
    side: &str,
    barrier_bps: f64,
) -> Option<PathOutcome> {
    let start = rows.get(idx)?.mid_price;
    if start <= EPS {
        return None;
    }
    if horizon == 0 {
        return None;
    }
    let end = idx.checked_add(horizon)?;
    if end >= rows.len() {
        return None;
    }
    let sign = if side == "long" { 1.0 } else { -1.0 };
    let mut drawup = f64::NEG_INFINITY;
    let mut drawdown = f64::INFINITY;
    let mut favorable_first = false;
    let mut adverse_first = false;
    for row in rows.iter().take(end + 1).skip(idx + 1) {
        let ret = (row.mid_price / start - 1.0) * 10_000.0;
        drawup = drawup.max(ret);
        drawdown = drawdown.min(ret);
        let side_ret = sign * ret;
        if !favorable_first && !adverse_first {
            if side_ret >= barrier_bps {
                favorable_first = true;
            } else if side_ret <= -barrier_bps {
                adverse_first = true;
            }
        }
    }
    let final_ret = (rows[end].mid_price / start - 1.0) * 10_000.0;
    let side_return = sign * final_ret;
    let asymmetry = if side == "long" {
        drawup - drawdown.abs()
    } else {
        drawdown.abs() - drawup
    };
    Some(PathOutcome {
        favorable_first,
        adverse_first,
        side_return_bps: side_return,
        asymmetry_bps: asymmetry,
    })
}

fn build_stability(
    config: &CcFixedEventConfig,
    by_symbol: &HashMap<String, Vec<&FeatureRow>>,
    candidates: &[CandidateKey],
    fits: &[FoldFit],
) -> Vec<StabilityRow> {
    let fit_map = fits
        .iter()
        .map(|fit| ((fit.fold.clone(), fit.symbol.clone()), fit))
        .collect::<HashMap<_, _>>();
    let mut out = Vec::new();
    for candidate in candidates.iter().take(80) {
        let Some(fit) = fit_map.get(&(candidate.fold.clone(), candidate.symbol.clone())) else {
            continue;
        };
        let Some(rows) = by_symbol.get(&candidate.symbol) else {
            continue;
        };
        let valid = rows
            .iter()
            .copied()
            .filter(|row| {
                row.factor_eligible
                    && row.local_timestamp >= fit.valid_start
                    && row.local_timestamp <= fit.valid_end
            })
            .collect::<Vec<_>>();
        let selected = selected_outcomes(&valid, candidate, fit, None);
        for scope in ["date", "hour", "fold", "nonoverlap_event_bucket"] {
            let mut groups = BTreeMap::<String, PathMetric>::new();
            for (row, outcome) in &selected {
                let value = match scope {
                    "date" => row.date.clone(),
                    "hour" => row.hour_utc.clone(),
                    "fold" => candidate.fold.clone(),
                    "nonoverlap_event_bucket" => {
                        (row.event_index / candidate.horizon_events.max(1)).to_string()
                    }
                    _ => String::new(),
                };
                groups
                    .entry(value)
                    .or_default()
                    .add(*outcome, row.event_index / candidate.horizon_events.max(1));
            }
            for (group_value, metric) in groups {
                if metric.rows == 0 {
                    continue;
                }
                out.push(StabilityRow {
                    run_tag: config.run_tag.clone(),
                    fold: candidate.fold.clone(),
                    symbol: candidate.symbol.clone(),
                    feature_name: candidate.feature_name.clone(),
                    gate: candidate.gate.clone(),
                    side: candidate.side.clone(),
                    horizon_events: candidate.horizon_events,
                    group_scope: scope.to_string(),
                    group_value,
                    rows: metric.rows,
                    favorable_minus_adverse_rate: metric.favorable_minus_adverse_rate(),
                    side_return_bps_mean: metric.side_return_mean(),
                    drawup_drawdown_asymmetry_bps_mean: metric.asymmetry_mean(),
                    guardrail: GUARDRAIL.to_string(),
                });
            }
        }
    }
    out
}

fn build_negative_controls(
    config: &CcFixedEventConfig,
    by_symbol: &HashMap<String, Vec<&FeatureRow>>,
    candidates: &[CandidateKey],
    fits: &[FoldFit],
) -> Vec<NegativeControlRow> {
    let fit_map = fits
        .iter()
        .map(|fit| ((fit.fold.clone(), fit.symbol.clone()), fit))
        .collect::<HashMap<_, _>>();
    let symbols = by_symbol.keys().cloned().collect::<Vec<_>>();
    let mut out = Vec::new();
    for candidate in candidates.iter().take(80) {
        let Some(fit) = fit_map.get(&(candidate.fold.clone(), candidate.symbol.clone())) else {
            continue;
        };
        let Some(rows) = by_symbol.get(&candidate.symbol) else {
            continue;
        };
        let valid = rows
            .iter()
            .copied()
            .filter(|row| {
                row.factor_eligible
                    && row.local_timestamp >= fit.valid_start
                    && row.local_timestamp <= fit.valid_end
            })
            .collect::<Vec<_>>();
        push_control_metric(
            config,
            &mut out,
            "reversed_sign_gate",
            candidate,
            fit,
            &valid,
            None,
            Some(("reversed", opposite_side(&candidate.side))),
        );
        push_control_metric(
            config,
            &mut out,
            "same_state_opposite_side",
            candidate,
            fit,
            &valid,
            None,
            Some(("same_gate", opposite_side(&candidate.side))),
        );
        let shuffled = within_day_shuffled_feature_values(
            &valid,
            &candidate.feature_name,
            &fit.mlofi_weights,
            candidate,
        );
        push_control_metric(
            config,
            &mut out,
            "within_day_shuffled_event_time",
            candidate,
            fit,
            &valid,
            Some(&shuffled),
            None,
        );
        let future = shifted_feature_values_no_wrap(
            &valid,
            &candidate.feature_name,
            &fit.mlofi_weights,
            candidate.horizon_events.max(10),
        );
        push_control_metric(
            config,
            &mut out,
            "future_shift_placebo",
            candidate,
            fit,
            &valid,
            Some(&future),
            None,
        );
        if let Some(other_symbol) = symbols.iter().find(|symbol| **symbol != candidate.symbol) {
            if let Some(other_rows) = by_symbol.get(other_symbol) {
                let wrong = nearest_other_values(
                    &valid,
                    other_rows,
                    &candidate.feature_name,
                    &fit.mlofi_weights,
                    config.cross_venue_tolerance_us,
                );
                push_control_metric(
                    config,
                    &mut out,
                    "wrong_symbol_same_factor",
                    candidate,
                    fit,
                    &valid,
                    Some(&wrong),
                    None,
                );
            }
        }
    }
    out
}

fn within_day_shuffled_feature_values(
    rows: &[&FeatureRow],
    feature_name: &str,
    mlofi_weights: &[f64; 6],
    candidate: &CandidateKey,
) -> Vec<f64> {
    let mut out = rows
        .iter()
        .map(|row| feature_value(row, feature_name, mlofi_weights))
        .collect::<Vec<_>>();
    let mut by_date = BTreeMap::<String, Vec<usize>>::new();
    for (idx, row) in rows.iter().enumerate() {
        by_date.entry(row.date.clone()).or_default().push(idx);
    }
    for (date, indices) in by_date {
        if indices.len() < 2 {
            continue;
        }
        let original = indices.iter().map(|idx| out[*idx]).collect::<Vec<_>>();
        let mut order = (0..indices.len()).collect::<Vec<_>>();
        deterministic_shuffle_indices(
            &mut order,
            stable_control_seed(candidate, &date, indices.len()),
        );
        if order
            .iter()
            .enumerate()
            .all(|(idx, source_idx)| idx == *source_idx)
        {
            order.rotate_left(1);
        }
        for (target_pos, row_idx) in indices.iter().enumerate() {
            out[*row_idx] = original[order[target_pos]];
        }
    }
    out
}

fn shifted_feature_values_no_wrap(
    rows: &[&FeatureRow],
    feature_name: &str,
    mlofi_weights: &[f64; 6],
    shift: usize,
) -> Vec<f64> {
    let shift = shift.max(1);
    (0..rows.len())
        .map(|idx| {
            rows.get(idx + shift)
                .map(|row| feature_value(row, feature_name, mlofi_weights))
                .unwrap_or(f64::NAN)
        })
        .collect()
}

fn deterministic_shuffle_indices(order: &mut [usize], mut seed: u64) {
    if order.len() < 2 {
        return;
    }
    for idx in (1..order.len()).rev() {
        seed = splitmix64(seed.wrapping_add(idx as u64));
        let swap_idx = (seed as usize) % (idx + 1);
        order.swap(idx, swap_idx);
    }
}

fn stable_control_seed(candidate: &CandidateKey, date: &str, len: usize) -> u64 {
    let mut seed = 0x9e37_79b9_7f4a_7c15u64 ^ len as u64;
    for part in [
        candidate.fold.as_str(),
        candidate.symbol.as_str(),
        candidate.feature_name.as_str(),
        candidate.gate.as_str(),
        candidate.side.as_str(),
        date,
    ] {
        for byte in part.as_bytes() {
            seed ^= *byte as u64;
            seed = seed.wrapping_mul(0x100_0000_01b3).rotate_left(13);
        }
    }
    seed ^ candidate.horizon_events as u64
}

fn splitmix64(mut value: u64) -> u64 {
    value = value.wrapping_add(0x9e37_79b9_7f4a_7c15);
    value = (value ^ (value >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    value = (value ^ (value >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    value ^ (value >> 31)
}

fn push_control_metric(
    config: &CcFixedEventConfig,
    out: &mut Vec<NegativeControlRow>,
    control_type: &str,
    candidate: &CandidateKey,
    fit: &FoldFit,
    valid: &[&FeatureRow],
    control_values: Option<&[f64]>,
    override_gate_side: Option<(&str, &str)>,
) {
    let mut metric = PathMetric::default();
    let gate = match override_gate_side.map(|x| x.0) {
        Some("reversed") if candidate.gate.starts_with("high") => "low_train_q20",
        Some("reversed") => "high_train_q80",
        _ => candidate.gate.as_str(),
    };
    let side = override_gate_side
        .map(|x| x.1)
        .unwrap_or(candidate.side.as_str());
    for (idx, row) in valid.iter().enumerate() {
        let x = control_values
            .and_then(|values| values.get(idx).copied())
            .unwrap_or_else(|| feature_value(row, &candidate.feature_name, &fit.mlofi_weights));
        if !gate_passes(
            x,
            gate,
            candidate.low_gate_threshold,
            candidate.high_gate_threshold,
        ) {
            continue;
        }
        if let Some(outcome) =
            first_passage_outcome(valid, idx, candidate.horizon_events, side, fit.barrier_bps)
        {
            metric.add(outcome, row.event_index / candidate.horizon_events.max(1));
        }
    }
    if metric.rows == 0 {
        return;
    }
    out.push(NegativeControlRow {
        run_tag: config.run_tag.clone(),
        control_type: control_type.to_string(),
        fold: candidate.fold.clone(),
        symbol: candidate.symbol.clone(),
        feature_name: candidate.feature_name.clone(),
        gate: gate.to_string(),
        side: side.to_string(),
        horizon_events: candidate.horizon_events,
        selected_rows: metric.rows,
        favorable_minus_adverse_rate: metric.favorable_minus_adverse_rate(),
        side_return_bps_mean: metric.side_return_mean(),
        control_note:
            "candidate must clearly exceed this control or be treated as window/cost artifact"
                .to_string(),
        guardrail: GUARDRAIL.to_string(),
    });
}

fn selected_outcomes<'a>(
    valid: &[&'a FeatureRow],
    candidate: &CandidateKey,
    fit: &FoldFit,
    control_values: Option<&[f64]>,
) -> Vec<(&'a FeatureRow, PathOutcome)> {
    let mut out = Vec::new();
    for (idx, row) in valid.iter().enumerate() {
        let x = control_values
            .and_then(|values| values.get(idx).copied())
            .unwrap_or_else(|| feature_value(row, &candidate.feature_name, &fit.mlofi_weights));
        if !gate_passes(
            x,
            &candidate.gate,
            candidate.low_gate_threshold,
            candidate.high_gate_threshold,
        ) {
            continue;
        }
        if let Some(outcome) = first_passage_outcome(
            valid,
            idx,
            candidate.horizon_events,
            &candidate.side,
            fit.barrier_bps,
        ) {
            out.push((*row, outcome));
        }
    }
    out
}

fn build_spearman_diagnostics(
    config: &CcFixedEventConfig,
    by_symbol: &HashMap<String, Vec<&FeatureRow>>,
    candidates: &[CandidateKey],
    fits: &[FoldFit],
) -> Vec<SpearmanRow> {
    let fit_map = fits
        .iter()
        .map(|fit| ((fit.fold.clone(), fit.symbol.clone()), fit))
        .collect::<HashMap<_, _>>();
    let mut seen = std::collections::HashSet::<(String, String, String, usize)>::new();
    let mut out = Vec::new();
    for candidate in candidates.iter().take(24) {
        let key = (
            candidate.fold.clone(),
            candidate.symbol.clone(),
            candidate.feature_name.clone(),
            candidate.horizon_events,
        );
        if !seen.insert(key) {
            continue;
        }
        let Some(fit) = fit_map.get(&(candidate.fold.clone(), candidate.symbol.clone())) else {
            continue;
        };
        let Some(symbol_rows) = by_symbol.get(&candidate.symbol) else {
            continue;
        };
        let full = symbol_rows
            .iter()
            .copied()
            .filter(|row| row.factor_eligible)
            .collect::<Vec<_>>();
        let valid = full
            .iter()
            .copied()
            .filter(|row| {
                row.local_timestamp >= fit.valid_start && row.local_timestamp <= fit.valid_end
            })
            .collect::<Vec<_>>();
        push_spearman_row(
            config,
            &mut out,
            "fold_valid",
            &candidate.fold,
            &candidate.symbol,
            &candidate.feature_name,
            candidate.horizon_events,
            "valid",
            &valid,
            fit,
            0,
            None,
        );
        push_spearman_row(
            config,
            &mut out,
            "full_window",
            &candidate.fold,
            &candidate.symbol,
            &candidate.feature_name,
            candidate.horizon_events,
            "all",
            &full,
            fit,
            0,
            None,
        );

        let mut by_date = BTreeMap::<String, Vec<&FeatureRow>>::new();
        for row in &full {
            by_date.entry(row.date.clone()).or_default().push(*row);
        }
        for (date, rows) in by_date {
            push_spearman_row(
                config,
                &mut out,
                "daily",
                &candidate.fold,
                &candidate.symbol,
                &candidate.feature_name,
                candidate.horizon_events,
                &date,
                &rows,
                fit,
                0,
                None,
            );
        }

        for residue in 0..candidate.horizon_events.min(5) {
            push_spearman_row(
                config,
                &mut out,
                "nonoverlap_residue",
                &candidate.fold,
                &candidate.symbol,
                &candidate.feature_name,
                candidate.horizon_events,
                &residue.to_string(),
                &full,
                fit,
                0,
                Some(residue),
            );
        }
        for lag in [1usize, 10, 50, candidate.horizon_events] {
            push_spearman_row(
                config,
                &mut out,
                &format!("feature_lag_{lag}"),
                &candidate.fold,
                &candidate.symbol,
                &candidate.feature_name,
                candidate.horizon_events,
                "all",
                &full,
                fit,
                -(lag as isize),
                None,
            );
        }
        for shift in [1usize, candidate.horizon_events] {
            push_spearman_row(
                config,
                &mut out,
                &format!("future_shift_placebo_{shift}"),
                &candidate.fold,
                &candidate.symbol,
                &candidate.feature_name,
                candidate.horizon_events,
                "all",
                &full,
                fit,
                shift as isize,
                None,
            );
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.fold.cmp(&b.fold))
            .then_with(|| a.feature_name.cmp(&b.feature_name))
            .then_with(|| a.horizon_events.cmp(&b.horizon_events))
            .then_with(|| a.scope.cmp(&b.scope))
            .then_with(|| a.group_value.cmp(&b.group_value))
    });
    out
}

fn push_spearman_row(
    config: &CcFixedEventConfig,
    out: &mut Vec<SpearmanRow>,
    scope: &str,
    fold: &str,
    symbol: &str,
    feature_name: &str,
    horizon_events: usize,
    group_value: &str,
    rows: &[&FeatureRow],
    fit: &FoldFit,
    feature_offset: isize,
    residue: Option<usize>,
) {
    let Some((rows_count, spearman)) = spearman_dlog_mid(
        rows,
        feature_name,
        &fit.mlofi_weights,
        horizon_events,
        feature_offset,
        residue,
    ) else {
        return;
    };
    out.push(SpearmanRow {
        run_tag: config.run_tag.clone(),
        scope: scope.to_string(),
        fold: fold.to_string(),
        symbol: symbol.to_string(),
        feature_name: feature_name.to_string(),
        horizon_events,
        group_value: group_value.to_string(),
        rows: rows_count,
        spearman,
        target: format!("dlog_mid_t_to_t_plus_{horizon_events}_events"),
        guardrail: GUARDRAIL.to_string(),
    });
}

fn spearman_dlog_mid(
    rows: &[&FeatureRow],
    feature_name: &str,
    mlofi_weights: &[f64; 6],
    horizon: usize,
    feature_offset: isize,
    residue: Option<usize>,
) -> Option<(usize, f64)> {
    if rows.len() <= horizon + 1 || horizon == 0 {
        return None;
    }
    let mut xs = Vec::new();
    let mut ys = Vec::new();
    let span = rows.len().saturating_sub(horizon);
    let step = if residue.is_none() && span > SPEARMAN_MAX_ROWS {
        (span / SPEARMAN_MAX_ROWS).max(1)
    } else {
        1
    };
    for idx in 0..span {
        if step > 1 && idx % step != 0 {
            continue;
        }
        if residue.is_some_and(|value| idx % horizon != value) {
            continue;
        }
        let feature_idx = idx as isize + feature_offset;
        if feature_idx < 0 || feature_idx as usize >= rows.len() {
            continue;
        }
        let start = rows[idx].mid_price;
        let end = rows[idx + horizon].mid_price;
        if start <= EPS || end <= EPS {
            continue;
        }
        let x = feature_value(rows[feature_idx as usize], feature_name, mlofi_weights);
        let y = (end / start).ln();
        if x.is_finite() && y.is_finite() {
            xs.push(x);
            ys.push(y);
        }
    }
    spearman_xy(&xs, &ys).map(|value| (xs.len(), value))
}

fn spearman_xy(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 100 {
        return None;
    }
    let xr = ranks(xs);
    let yr = ranks(ys);
    let x_mean = xr.iter().sum::<f64>() / xr.len() as f64;
    let y_mean = yr.iter().sum::<f64>() / yr.len() as f64;
    let mut num = 0.0;
    let mut x_var = 0.0;
    let mut y_var = 0.0;
    for (x, y) in xr.iter().zip(yr.iter()) {
        let dx = *x - x_mean;
        let dy = *y - y_mean;
        num += dx * dy;
        x_var += dx * dx;
        y_var += dy * dy;
    }
    let den = (x_var * y_var).sqrt();
    (den > EPS).then_some(num / den)
}

fn ranks(values: &[f64]) -> Vec<f64> {
    let mut indexed = values
        .iter()
        .copied()
        .enumerate()
        .collect::<Vec<(usize, f64)>>();
    indexed.sort_by(|a, b| a.1.total_cmp(&b.1));
    let mut out = vec![0.0; values.len()];
    let mut idx = 0usize;
    while idx < indexed.len() {
        let mut end = idx + 1;
        while end < indexed.len() && indexed[end].1 == indexed[idx].1 {
            end += 1;
        }
        let rank = (idx + 1 + end) as f64 * 0.5;
        for item in indexed.iter().take(end).skip(idx) {
            out[item.0] = rank;
        }
        idx = end;
    }
    out
}

fn build_episode_overlay(
    config: &CcFixedEventConfig,
    rows: &[FeatureRow],
    candidates: &[CandidateKey],
) -> Result<Vec<EpisodeOverlayRow>> {
    let path = config.date_dir.join(format!(
        "{}_episode_backtest_{}_trades.csv",
        config.output_prefix, config.run_tag
    ));
    if !path.exists() || candidates.is_empty() || rows.is_empty() {
        return Ok(Vec::new());
    }
    let by_symbol_owned = rows_by_symbol_owned(rows);
    let candidate_map = candidates
        .iter()
        .take(50)
        .map(|candidate| {
            (
                (
                    candidate.fold.clone(),
                    candidate.symbol.clone(),
                    candidate.side.clone(),
                ),
                candidate.clone(),
            )
        })
        .collect::<HashMap<_, _>>();
    let mut aggs = BTreeMap::<(String, String, String, String, String), EpisodeAgg>::new();
    let mut reader = csv::Reader::from_path(&path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    for record in reader.deserialize::<EpisodeTradeInputRow>() {
        let trade = record.with_context(|| format!("failed to parse {}", path.display()))?;
        let overlay = if let Some(candidate) =
            candidate_map.get(&(trade.fold.clone(), trade.symbol.clone(), trade.side.clone()))
        {
            if let Some(symbol_rows) = by_symbol_owned.get(&trade.symbol) {
                let idx = lower_bound_feature_ts(symbol_rows, trade.signal_local_timestamp);
                let row = idx
                    .checked_sub(1)
                    .and_then(|i| symbol_rows.get(i))
                    .filter(|row| {
                        trade
                            .signal_local_timestamp
                            .saturating_sub(row.local_timestamp)
                            <= config.cross_venue_tolerance_us
                    });
                match row {
                    Some(row) => {
                        let value = feature_value(row, &candidate.feature_name, &[0.0; 6]);
                        if gate_passes(
                            value,
                            &candidate.gate,
                            candidate.low_gate_threshold,
                            candidate.high_gate_threshold,
                        ) {
                            "cc_candidate_aligned"
                        } else {
                            "cc_candidate_not_aligned"
                        }
                    }
                    None => "no_nearby_cc_state",
                }
            } else {
                "no_symbol_cc_state"
            }
        } else {
            "no_top_cc_candidate"
        };
        let key = (
            trade.fold,
            trade.symbol,
            trade.side,
            trade.execution_model,
            overlay.to_string(),
        );
        let agg = aggs.entry(key).or_default();
        agg.trades += 1;
        if trade.net_bps > 0.0 {
            agg.wins += 1;
        }
        agg.net_bps_sum += trade.net_bps;
        agg.pnl_quote_sum += trade.pnl_quote;
        agg.cost_bps_sum += trade.cost_bps;
        agg.queue_penalty_bps_sum += trade.queue_penalty_bps;
    }
    let mut out = aggs
        .into_iter()
        .map(
            |((fold, symbol, side, execution_model, overlay_state), agg)| EpisodeOverlayRow {
                run_tag: config.run_tag.clone(),
                fold,
                symbol,
                side,
                execution_model,
                overlay_state,
                trades: agg.trades,
                net_bps_mean: if agg.trades == 0 {
                    0.0
                } else {
                    agg.net_bps_sum / agg.trades as f64
                },
                win_rate: rate(agg.wins, agg.trades),
                pnl_quote_sum: agg.pnl_quote_sum,
                cost_bps_mean: if agg.trades == 0 {
                    0.0
                } else {
                    agg.cost_bps_sum / agg.trades as f64
                },
                queue_penalty_bps_mean: if agg.trades == 0 {
                    0.0
                } else {
                    agg.queue_penalty_bps_sum / agg.trades as f64
                },
                guardrail: GUARDRAIL.to_string(),
            },
        )
        .collect::<Vec<_>>();
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.fold.cmp(&b.fold))
            .then_with(|| b.net_bps_mean.total_cmp(&a.net_bps_mean))
    });
    Ok(out)
}

fn factor_param_rows(config: &CcFixedEventConfig, fit: &FoldFit) -> Vec<FactorParamRow> {
    let horizons = serde_json::to_string(&fit.horizons).unwrap_or_else(|_| "[]".to_string());
    let mut rows = fit
        .features
        .values()
        .map(|feature| FactorParamRow {
            run_tag: config.run_tag.clone(),
            fit_scope: "train_only".to_string(),
            fold: fit.fold.clone(),
            symbol: fit.symbol.clone(),
            feature_name: feature.feature_name.clone(),
            train_rows: fit.train_rows,
            valid_rows: fit.valid_rows,
            median: feature.median,
            mad: feature.mad,
            q20: feature.q20,
            q80: feature.q80,
            low_gate_threshold: feature.low_gate_threshold,
            high_gate_threshold: feature.high_gate_threshold,
            gate_policy: feature.gate_policy.clone(),
            mlofi_weight: feature.mlofi_weight,
            liquidity_shock_threshold: fit.shock_threshold,
            first_passage_barrier_bps: fit.barrier_bps,
            event_horizons_json: horizons.clone(),
            nonzero_mid_move_median_events: fit.nonzero_mid_move_median_events,
            guardrail: GUARDRAIL.to_string(),
        })
        .collect::<Vec<_>>();
    rows.sort_by(|a, b| a.feature_name.cmp(&b.feature_name));
    rows
}

fn top_candidates(rankings: &[PathRankingRow], fits: &[FoldFit]) -> Vec<CandidateKey> {
    let fit_map = fits
        .iter()
        .map(|fit| ((fit.fold.clone(), fit.symbol.clone()), fit))
        .collect::<HashMap<_, _>>();
    let mut candidates = Vec::new();
    let mut best_by_base =
        HashMap::<(String, String, String, String, String, usize), &PathRankingRow>::new();
    for row in rankings.iter().filter(|row| {
        row.selected_rows >= 25
            && row.score.is_finite()
            && fit_map.contains_key(&(row.fold.clone(), row.symbol.clone()))
    }) {
        let key = (
            row.fold.clone(),
            row.symbol.clone(),
            base_feature_key(&row.feature_name).to_string(),
            row.gate.clone(),
            row.side.clone(),
            row.horizon_events,
        );
        let replace = match best_by_base.get(&key) {
            Some(existing) => row.score > existing.score,
            None => true,
        };
        if replace {
            best_by_base.insert(key, row);
        }
    }
    let mut rows = best_by_base.into_values().collect::<Vec<_>>();
    rows.sort_by(|a, b| {
        b.score
            .total_cmp(&a.score)
            .then_with(|| b.selected_rows.cmp(&a.selected_rows))
            .then_with(|| a.feature_name.cmp(&b.feature_name))
    });
    for row in rows.into_iter().take(100) {
        let Some(fit) = fit_map.get(&(row.fold.clone(), row.symbol.clone())) else {
            continue;
        };
        let Some(param) = fit.features.get(&row.feature_name) else {
            continue;
        };
        candidates.push(CandidateKey {
            fold: row.fold.clone(),
            symbol: row.symbol.clone(),
            feature_name: row.feature_name.clone(),
            gate: row.gate.clone(),
            side: row.side.clone(),
            horizon_events: row.horizon_events,
            low_gate_threshold: param.low_gate_threshold,
            high_gate_threshold: param.high_gate_threshold,
        });
    }
    candidates
}

fn collect_feature_values(
    rows: &[&FeatureRow],
    mlofi_weights: &[f64; 6],
    cross_values: Option<Vec<f64>>,
) -> BTreeMap<String, Vec<f64>> {
    let mut out = BTreeMap::<String, Vec<f64>>::new();
    let names = feature_names();
    for name in &names {
        out.insert(
            name.to_string(),
            rows.iter()
                .map(|row| feature_value(row, name, mlofi_weights))
                .filter(|value| value.is_finite())
                .collect(),
        );
    }
    if let Some(values) = cross_values {
        out.insert(
            "cross_venue_mlofi_lead_lag".to_string(),
            values
                .into_iter()
                .filter(|value| value.is_finite())
                .collect(),
        );
    }
    out
}

fn base_feature_names() -> &'static [&'static str] {
    &[
        "ofi_l1_depth_norm",
        "mlofi_combo",
        "mlofi_norm_l1",
        "mlofi_norm_l2",
        "mlofi_norm_l3",
        "mlofi_norm_l5",
        "mlofi_norm_l10",
        "mlofi_norm_l25",
        "mlofi_roll10_l1",
        "mlofi_roll10_l5",
        "mlofi_roll10_l25",
        "queue_imbalance_1",
        "queue_imbalance_5",
        "queue_imbalance_25",
        "microprice_dev_bps",
        "queue_depletion_intensity",
        "replenish_intensity",
        "cancellation_withdrawal_intensity",
        "trade_arrival_alignment",
        "liquidity_shock_score",
        "cross_venue_mlofi_lead_lag",
    ]
}

fn feature_names() -> Vec<String> {
    let mut names = Vec::new();
    for base in base_feature_names() {
        names.push((*base).to_string());
        names.push(format!("abs__{base}"));
        names.push(format!("pos__{base}"));
        names.push(format!("neg__{base}"));
        names.push(format!("signed_sq__{base}"));
    }
    names
}

fn base_feature_key(name: &str) -> &str {
    name.strip_prefix("abs__")
        .or_else(|| name.strip_prefix("pos__"))
        .or_else(|| name.strip_prefix("neg__"))
        .or_else(|| name.strip_prefix("signed_sq__"))
        .unwrap_or(name)
}

fn feature_value(row: &FeatureRow, name: &str, mlofi_weights: &[f64; 6]) -> f64 {
    if let Some(base) = name.strip_prefix("abs__") {
        return base_feature_value(row, base, mlofi_weights).abs();
    }
    if let Some(base) = name.strip_prefix("pos__") {
        return base_feature_value(row, base, mlofi_weights).max(0.0);
    }
    if let Some(base) = name.strip_prefix("neg__") {
        return (-base_feature_value(row, base, mlofi_weights)).max(0.0);
    }
    if let Some(base) = name.strip_prefix("signed_sq__") {
        let value = base_feature_value(row, base, mlofi_weights);
        return value.signum() * value * value;
    }
    base_feature_value(row, name, mlofi_weights)
}

fn base_feature_value(row: &FeatureRow, name: &str, mlofi_weights: &[f64; 6]) -> f64 {
    match name {
        "ofi_l1_depth_norm" => row.ofi_l1_depth_norm,
        "mlofi_combo" => row
            .mlofi_norm
            .iter()
            .zip(mlofi_weights.iter())
            .map(|(value, weight)| value * weight)
            .sum(),
        "mlofi_norm_l1" => row.mlofi_norm[0],
        "mlofi_norm_l2" => row.mlofi_norm[1],
        "mlofi_norm_l3" => row.mlofi_norm[2],
        "mlofi_norm_l5" => row.mlofi_norm[3],
        "mlofi_norm_l10" => row.mlofi_norm[4],
        "mlofi_norm_l25" => row.mlofi_norm[5],
        "mlofi_roll10_l1" => row.mlofi_roll10[0],
        "mlofi_roll10_l5" => row.mlofi_roll10[3],
        "mlofi_roll10_l25" => row.mlofi_roll10[5],
        "queue_imbalance_1" => row.queue_imbalance_1,
        "queue_imbalance_5" => row.queue_imbalance_5,
        "queue_imbalance_25" => row.queue_imbalance_25,
        "microprice_dev_bps" => row.microprice_dev_bps,
        "queue_depletion_intensity" => row.queue_depletion_intensity,
        "replenish_intensity" => row.replenish_intensity,
        "cancellation_withdrawal_intensity" => row.cancellation_withdrawal_intensity,
        "trade_arrival_alignment" => row.trade_arrival_alignment,
        "liquidity_shock_score" => row.liquidity_shock_score,
        "cross_venue_mlofi_lead_lag" => row.cross_venue_mlofi_lead_lag,
        _ => 0.0,
    }
}

fn feature_family(name: &str) -> &'static str {
    let base = base_feature_key(name);
    if base.starts_with("ofi") {
        "OFI"
    } else if base.starts_with("mlofi") {
        "MLOFI"
    } else if base.starts_with("queue_imbalance") {
        "queue_imbalance"
    } else if base.starts_with("microprice") {
        "microprice"
    } else if base.contains("depletion") {
        "queue_depletion"
    } else if base.contains("replenish") {
        "replenish"
    } else if base.contains("cancellation") {
        "cancellation_withdrawal"
    } else if base.contains("trade_arrival") {
        "trade_arrival_alignment"
    } else if base.contains("shock") {
        "resiliency_liquidity_shock"
    } else if base.contains("cross_venue") {
        "cross_venue_mlofi_lead_lag"
    } else {
        "control"
    }
}

fn fit_mlofi_weights(train: &[&FeatureRow], horizon: usize) -> [f64; 6] {
    let mut raw = [0.0; 6];
    for level in 0..6 {
        let mut xs = Vec::new();
        let mut ys = Vec::new();
        for idx in 0..train.len().saturating_sub(horizon) {
            let start = train[idx].mid_price;
            let end = train[idx + horizon].mid_price;
            if start <= EPS || end <= EPS {
                continue;
            }
            xs.push(train[idx].mlofi_norm[level]);
            ys.push((end / start - 1.0) * 10_000.0);
        }
        raw[level] = correlation(&xs, &ys).unwrap_or(0.0);
    }
    let total = raw.iter().map(|value| value.abs()).sum::<f64>();
    if total <= EPS {
        [1.0 / 6.0; 6]
    } else {
        raw.map(|value| value / total)
    }
}

fn fit_event_horizons(train: &[&FeatureRow]) -> Vec<usize> {
    let median = median_mid_move_events(train).unwrap_or(25.0);
    let mut horizons = [1.0, 2.0, 5.0, 10.0]
        .iter()
        .map(|mult| (median * mult).round() as usize)
        .map(|value| value.clamp(10, 5000))
        .collect::<Vec<_>>();
    horizons.sort_unstable();
    horizons.dedup();
    horizons
}

fn median_mid_move_events(train: &[&FeatureRow]) -> Option<f64> {
    let mut gaps = Vec::new();
    let mut last_price = None::<f64>;
    let mut last_idx = 0usize;
    for (idx, row) in train.iter().enumerate() {
        if let Some(prev) = last_price {
            if (row.mid_price - prev).abs() > EPS {
                gaps.push((idx - last_idx).max(1) as f64);
                last_idx = idx;
                last_price = Some(row.mid_price);
            }
        } else {
            last_price = Some(row.mid_price);
            last_idx = idx;
        }
    }
    median(gaps)
}

fn fit_first_passage_barrier(train: &[&FeatureRow], horizon: usize) -> f64 {
    let mut ranges = Vec::new();
    for idx in 0..train.len().saturating_sub(horizon.max(1)) {
        let start = train[idx].mid_price;
        if start <= EPS {
            continue;
        }
        let end = (idx + horizon).min(train.len().saturating_sub(1));
        let mut high = 0.0f64;
        let mut low = 0.0f64;
        for row in train.iter().take(end + 1).skip(idx + 1) {
            let ret = (row.mid_price / start - 1.0) * 10_000.0;
            high = high.max(ret);
            low = low.min(ret);
        }
        ranges.push(high - low);
    }
    let q65 = quantile(ranges, 0.65).unwrap_or(2.0);
    let tick = estimate_tick_bps(train).unwrap_or(0.05);
    q65.clamp(tick.max(0.0001), 12.0)
}

fn estimate_tick_bps(train: &[&FeatureRow]) -> Option<f64> {
    let mut changes = Vec::new();
    for pair in train.windows(2) {
        let a = pair[0].mid_price;
        let b = pair[1].mid_price;
        if a > EPS && b > EPS && (a - b).abs() > EPS {
            changes.push(((b / a - 1.0) * 10_000.0).abs());
        }
    }
    quantile(changes, 0.05)
}

fn feature_from_panel(row: &EventPanelRow) -> Option<FeatureRow> {
    let mid_price = row.mid_price?;
    if mid_price <= EPS {
        return None;
    }
    Some(FeatureRow {
        date: row.date.clone(),
        symbol: row.symbol.clone(),
        local_timestamp: row.local_timestamp,
        event_index: row.event_index,
        hour_utc: hour_from_us(row.local_timestamp).unwrap_or_default(),
        mid_price,
        spread_bps: row.spread_bps.unwrap_or(0.0),
        factor_eligible: row.factor_eligible,
        ofi_l1_depth_norm: row.ofi_l1_depth_norm.unwrap_or(0.0),
        mlofi_norm: [
            row.mlofi_norm_l1.unwrap_or(0.0),
            row.mlofi_norm_l2.unwrap_or(0.0),
            row.mlofi_norm_l3.unwrap_or(0.0),
            row.mlofi_norm_l5.unwrap_or(0.0),
            row.mlofi_norm_l10.unwrap_or(0.0),
            row.mlofi_norm_l25.unwrap_or(0.0),
        ],
        mlofi_roll10: [
            row.mlofi_roll10_l1,
            row.mlofi_roll10_l2,
            row.mlofi_roll10_l3,
            row.mlofi_roll10_l5,
            row.mlofi_roll10_l10,
            row.mlofi_roll10_l25,
        ],
        queue_imbalance_1: row.queue_imbalance_1.unwrap_or(0.0),
        queue_imbalance_5: row.queue_imbalance_5.unwrap_or(0.0),
        queue_imbalance_25: row.queue_imbalance_25.unwrap_or(0.0),
        microprice_dev_bps: row.microprice_dev_bps.unwrap_or(0.0),
        queue_depletion_intensity: row.queue_depletion_intensity.unwrap_or(0.0),
        replenish_intensity: row.replenish_intensity.unwrap_or(0.0),
        cancellation_withdrawal_intensity: row.cancellation_withdrawal_intensity.unwrap_or(0.0),
        trade_arrival_alignment: row.trade_arrival_alignment.unwrap_or(0.0),
        liquidity_shock_score: row.liquidity_shock_score.unwrap_or(0.0),
        low_confidence_split: row.execute_cancel_confidence == "low_confidence",
        cross_venue_mlofi_lead_lag: f64::NAN,
    })
}

fn add_cross_venue_mlofi(rows: &mut [FeatureRow], tolerance_us: u64) {
    let mut by_symbol = BTreeMap::<String, Vec<(u64, f64)>>::new();
    for row in rows.iter() {
        by_symbol
            .entry(row.symbol.clone())
            .or_default()
            .push((row.local_timestamp, equal_weight_mlofi(row)));
    }
    for items in by_symbol.values_mut() {
        items.sort_by_key(|(ts, _)| *ts);
    }
    for row in rows.iter_mut() {
        let Some((_, other)) = by_symbol.iter().find(|(symbol, _)| *symbol != &row.symbol) else {
            continue;
        };
        let idx = lower_bound_ts_value(other, row.local_timestamp);
        let mut best = None::<(u64, f64)>;
        for candidate_idx in [idx.checked_sub(1), Some(idx)].into_iter().flatten() {
            if let Some((ts, value)) = other.get(candidate_idx).copied() {
                let diff = ts.abs_diff(row.local_timestamp);
                if diff <= tolerance_us && best.is_none_or(|(best_diff, _)| diff < best_diff) {
                    best = Some((diff, value));
                }
            }
        }
        row.cross_venue_mlofi_lead_lag = best.map(|(_, value)| value).unwrap_or(f64::NAN);
    }
}

fn equal_weight_mlofi(row: &FeatureRow) -> f64 {
    row.mlofi_norm.iter().sum::<f64>() / row.mlofi_norm.len() as f64
}

fn lower_bound_ts_value(rows: &[(u64, f64)], ts: u64) -> usize {
    let mut left = 0usize;
    let mut right = rows.len();
    while left < right {
        let mid = (left + right) / 2;
        if rows[mid].0 < ts {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}

fn load_existing_panel_features(
    config: &CcFixedEventConfig,
    jobs: &[SymbolDayJob],
) -> Result<Vec<FeatureRow>> {
    let mut out = Vec::new();
    for job in jobs {
        let dir = panel_output_dir(
            &config.data_root,
            &config.panel_dataset,
            &config.run_tag,
            &job.symbol,
            job.date,
        );
        for path in sorted_panel_parts(&dir)? {
            let rows = load_csv_rows::<EventPanelRow>(&path)?;
            out.extend(rows.iter().filter_map(feature_from_panel));
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.local_timestamp.cmp(&b.local_timestamp))
    });
    Ok(out)
}

fn read_trades(path: &Path) -> Result<Vec<TradeState>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = csv::Reader::from_reader(decoder);
    let mut rows = Vec::<TradeState>::new();
    for record in reader.deserialize::<RawTradeRow>() {
        rows.push(
            record
                .with_context(|| format!("failed to parse {}", path.display()))?
                .into(),
        );
    }
    rows.sort_by_key(|row| row.local_timestamp);
    Ok(rows)
}

fn load_replay_expected(config: &CcFixedEventConfig) -> Result<HashMap<(String, String), usize>> {
    let path = config.date_dir.join(format!(
        "{}_replay_state_manifest_{}.csv",
        config.output_prefix, config.run_tag
    ));
    if !path.exists() {
        return Ok(HashMap::new());
    }
    let rows = load_csv_rows::<ReplayManifestRow>(&path)?;
    Ok(rows
        .into_iter()
        .filter(|row| row.status == "completed")
        .map(|row| ((row.date, row.symbol), row.replay_rows))
        .collect())
}

fn load_folds(config: &CcFixedEventConfig) -> Result<Vec<FoldSpec>> {
    let path = config.date_dir.join(format!(
        "{}_filter_params_{}.csv",
        config.output_prefix, config.run_tag
    ));
    if !path.exists() {
        return Ok(Vec::new());
    }
    let rows = load_csv_rows::<V10FoldInputRow>(&path)?;
    Ok(rows
        .into_iter()
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

fn build_default_folds(by_symbol: &HashMap<String, Vec<&FeatureRow>>) -> Vec<FoldSpec> {
    let mut folds = Vec::new();
    for (symbol, rows) in by_symbol {
        let eligible = rows
            .iter()
            .copied()
            .filter(|row| row.factor_eligible)
            .collect::<Vec<_>>();
        let n = eligible.len();
        if n < 300 {
            continue;
        }
        for (idx, (train_frac, valid_frac)) in [(0.50, 0.67), (0.67, 0.84), (0.84, 1.00)]
            .into_iter()
            .enumerate()
        {
            let train_end_idx = ((n as f64 * train_frac).floor() as usize).clamp(100, n - 1);
            let valid_end_idx =
                ((n as f64 * valid_frac).floor() as usize).clamp(train_end_idx + 1, n) - 1;
            let valid_rows = valid_end_idx.saturating_sub(train_end_idx);
            if valid_rows < 50 {
                continue;
            }
            folds.push(FoldSpec {
                fold: format!("auto_expanding_{}", idx + 1),
                symbol: symbol.clone(),
                train_start: eligible[0].local_timestamp,
                train_end: eligible[train_end_idx - 1].local_timestamp,
                valid_start: eligible[train_end_idx].local_timestamp,
                valid_end: eligible[valid_end_idx].local_timestamp,
            });
        }
    }
    folds.sort_by(|a, b| a.symbol.cmp(&b.symbol).then_with(|| a.fold.cmp(&b.fold)));
    folds
}

fn write_panel_parts(dir: &Path, rows: &[EventPanelRow], part_rows: usize) -> Result<usize> {
    fs::create_dir_all(dir)?;
    clear_panel_parts(dir)?;
    let mut part_files = 0usize;
    for chunk in rows.chunks(part_rows) {
        part_files += 1;
        let path = dir.join(format!("part_{part_files:06}.csv"));
        write_csv_atomic(&path, chunk)?;
    }
    Ok(part_files)
}

fn clear_panel_parts(dir: &Path) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(dir)? {
        let path = entry?.path();
        if path
            .file_name()
            .and_then(|value| value.to_str())
            .is_some_and(|name| name.starts_with("part_") && name.ends_with(".csv"))
        {
            fs::remove_file(&path)
                .with_context(|| format!("failed to remove stale panel part {}", path.display()))?;
        }
    }
    Ok(())
}

fn sorted_panel_parts(dir: &Path) -> Result<Vec<PathBuf>> {
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut parts = Vec::new();
    for entry in fs::read_dir(dir)? {
        let path = entry?.path();
        if path
            .file_name()
            .and_then(|value| value.to_str())
            .is_some_and(|name| name.starts_with("part_") && name.ends_with(".csv"))
        {
            parts.push(path);
        }
    }
    parts.sort();
    Ok(parts)
}

fn write_report(
    config: &CcFixedEventConfig,
    paths: &Paths,
    quality: &[QualityRow],
    params: &[FactorParamRow],
    rankings: &[PathRankingRow],
    stability: &[StabilityRow],
    controls: &[NegativeControlRow],
    spearman: &[SpearmanRow],
    overlay: &[EpisodeOverlayRow],
) -> Result<()> {
    let completed = quality
        .iter()
        .filter(|row| row.status.starts_with("completed"))
        .count();
    let low_conf = quality
        .iter()
        .filter(|row| row.execute_cancel_split_confidence == "low_confidence")
        .count();
    let quality_warnings = quality
        .iter()
        .filter(|row| row.status == "completed_with_quality_warnings")
        .count();
    let top = reportable_top_rankings(rankings, controls, 10);
    let control_types = controls
        .iter()
        .map(|row| row.control_type.clone())
        .collect::<std::collections::HashSet<_>>()
        .len();
    let positive_overlay = overlay
        .iter()
        .filter(|row| {
            row.execution_model == "maker_light"
                && row.overlay_state == "cc_candidate_aligned"
                && row.trades >= 100
                && row.net_bps_mean > 0.0
        })
        .count();
    let after_cost_read = if overlay.is_empty() {
        "Profit/after-cost overlay was not run for this panel; Spearman and path diagnostics are information tests only, not realized PnL evidence."
    } else if positive_overlay > 0 {
        "Some maker-light overlay slices are positive, but they remain diagnostics only and require control separation before any stronger interpretation."
    } else {
        "No stable after-cost overlay candidate is promoted; the conservative read is execution/usability filter > directional alpha."
    };
    let mut lines = vec![
        format!("# {} Fixed Event-Defined OFI/MLOFI", config.market_label),
        String::new(),
        format!("Status: 2026-05-17. Run tag: `{}`.", config.run_tag),
        String::new(),
        format!("Guardrail: `{GUARDRAIL}`."),
        String::new(),
        "## Scope".to_string(),
        String::new(),
        "This pass starts from local `bullish_incremental_book_L2` and `bullish_trades` raw CSV.GZ files. It does not download raw data, delete raw files, or treat prior snapshot-factor mining conclusions as discovery evidence.".to_string(),
        String::new(),
        "The event layer distinguishes full snapshot batches from incremental updates. Snapshot batches rebuild the book at each timestamp and compute OFI/MLOFI from the previous completed book to the current completed book.".to_string(),
        String::new(),
        "## Coverage".to_string(),
        String::new(),
        format!("- Completed symbol-days: `{completed}/{}`.", quality.len()),
        format!("- Completed with quality warnings: `{quality_warnings}`."),
        format!(
            "- Event panel rows: `{}`.",
            quality.iter().map(|row| row.event_count).sum::<usize>()
        ),
        format!("- Low-confidence execute/cancel split symbol-days: `{low_conf}`."),
        format!(
            "- Fixed feature definitions per fold: `{}`.",
            feature_names().len()
        ),
        format!("- Factor params rows: `{}`.", params.len()),
        format!("- Path ranking rows: `{}`.", rankings.len()),
        format!("- Stability rows: `{}`.", stability.len()),
        format!("- Negative control rows: `{}` across `{control_types}` control types.", controls.len()),
        format!("- Spearman diagnostic rows: `{}`.", spearman.len()),
        String::new(),
        "## Event Definitions".to_string(),
        String::new(),
        "- New price with positive amount is `limit_add/create`.".to_string(),
        "- Size increase at an existing price is `replenish/add`.".to_string(),
        "- Size decrease or zero amount is queue depletion, split into executable and cancellation/withdrawal using same-side trades observed in the trailing local-time window.".to_string(),
        "- Trade side is taker-side: `buy` consumes asks and `sell` consumes bids.".to_string(),
        "- Spearman diagnostics use `dlog_mid_{t,t+h}` and are separate from profit or fill-realism overlays.".to_string(),
        "- If day-level matched depletion rate is below 60%, execute/cancel split is marked `low_confidence`; aggregate depletion/replenish factors remain usable diagnostics.".to_string(),
        String::new(),
        "## Factor Families".to_string(),
        String::new(),
        "Main ranked families are CKS best-level OFI, XGH-style MLOFI at levels `1/2/3/5/10/25`, depth-normalized/rolling event-time MLOFI, quote/queue imbalance, microprice deviation, queue depletion, replenish, cancellation/withdrawal, trade-arrival alignment, liquidity-shock resiliency, and cross-venue MLOFI lead-lag. Each base feature is tested as raw, absolute, positive-part, negative-part, and signed-square variants, giving a fixed reusable 100+ feature surface. Depth slope/curvature is intentionally not promoted here.".to_string(),
        String::new(),
        "## Top Path Diagnostics".to_string(),
        String::new(),
        "Rows shown here must clear same-gate/same-side negative controls; control-dominated candidates stay in the CSV but are not promoted in this table.".to_string(),
        String::new(),
    ];
    if top.is_empty() {
        lines.push(
            "_No path rows survived the top-table selected-row and control-separation filters._"
                .to_string(),
        );
    } else {
        lines.push("| fold | symbol | feature | gate | side | horizon_events | selected | fav-adv | side_ret_bps | score |".to_string());
        lines.push("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |".to_string());
        for row in top {
            lines.push(format!(
                "| {} | {} | {} | {} | {} | {} | {} | {:.4} | {:.4} | {:.4} |",
                row.fold,
                row.symbol,
                row.feature_name,
                row.gate,
                row.side,
                row.horizon_events,
                row.selected_rows,
                row.favorable_minus_adverse_rate,
                row.side_return_bps_mean,
                row.score
            ));
        }
    }
    lines.extend([
        String::new(),
        "## Controls And Read".to_string(),
        String::new(),
        "Negative controls include within-day shuffled event time and future-shift placebo as required promotion checks; wrong-symbol same-factor is also applied when another symbol is available. Reversed-sign gate and same-state opposite-side checks remain diagnostic. Candidates that do not clearly separate from controls are classified as window/cost artifacts.".to_string(),
        String::new(),
        after_cost_read.to_string(),
        String::new(),
        "## Output Tables".to_string(),
        String::new(),
        format!("- `{}`", path_string(&paths.quality_csv)),
        format!("- `{}`", path_string(&paths.factor_params_csv)),
        format!("- `{}`", path_string(&paths.path_ranking_csv)),
        format!("- `{}`", path_string(&paths.stability_csv)),
        format!("- `{}`", path_string(&paths.negative_controls_csv)),
        format!("- `{}`", path_string(&paths.spearman_csv)),
        format!("- `{}`", path_string(&paths.episode_overlay_csv)),
        String::new(),
        "## Reproduce".to_string(),
        String::new(),
        "```bash".to_string(),
        config.reproduce_command.clone(),
        "```".to_string(),
        String::new(),
    ]);
    ensure_parent_dir(&paths.report_md)?;
    fs::write(&paths.report_md, lines.join("\n"))?;
    Ok(())
}

fn reportable_top_rankings<'a>(
    rankings: &'a [PathRankingRow],
    controls: &[NegativeControlRow],
    limit: usize,
) -> Vec<&'a PathRankingRow> {
    let mut best_by_base =
        HashMap::<(String, String, String, String, String, usize), &'a PathRankingRow>::new();
    for row in rankings.iter().filter(|row| {
        row.selected_rows >= 25
            && row.score.is_finite()
            && ranking_survives_same_signal_controls(row, controls)
    }) {
        let key = (
            row.fold.clone(),
            row.symbol.clone(),
            base_feature_key(&row.feature_name).to_string(),
            row.gate.clone(),
            row.side.clone(),
            row.horizon_events,
        );
        let replace = match best_by_base.get(&key) {
            Some(existing) => row.score > existing.score,
            None => true,
        };
        if replace {
            best_by_base.insert(key, row);
        }
    }
    let mut rows = best_by_base.into_values().collect::<Vec<_>>();
    rows.sort_by(|a, b| {
        b.score
            .total_cmp(&a.score)
            .then_with(|| b.selected_rows.cmp(&a.selected_rows))
            .then_with(|| a.feature_name.cmp(&b.feature_name))
    });
    rows.truncate(limit);
    rows
}

fn ranking_survives_same_signal_controls(
    row: &PathRankingRow,
    controls: &[NegativeControlRow],
) -> bool {
    let matching = controls
        .iter()
        .filter(|control| {
            control.fold == row.fold
                && control.symbol == row.symbol
                && control.feature_name == row.feature_name
                && control.horizon_events == row.horizon_events
                && control.gate == row.gate
                && control.side == row.side
                && matches!(
                    control.control_type.as_str(),
                    "future_shift_placebo"
                        | "within_day_shuffled_event_time"
                        | "wrong_symbol_same_factor"
                )
        })
        .collect::<Vec<_>>();
    for required_type in ["future_shift_placebo", "within_day_shuffled_event_time"] {
        if !matching
            .iter()
            .any(|control| control.control_type == required_type)
        {
            return false;
        }
    }
    !matching.iter().any(|control| {
        control.side_return_bps_mean >= row.side_return_bps_mean
            || control.favorable_minus_adverse_rate >= row.favorable_minus_adverse_rate
    })
}

fn build_jobs(
    symbols: &[String],
    from_date: NaiveDate,
    to_date: NaiveDate,
    max_symbol_days: Option<usize>,
) -> Vec<SymbolDayJob> {
    let mut jobs = Vec::new();
    let mut day = from_date;
    while day <= to_date {
        for symbol in symbols {
            jobs.push(SymbolDayJob {
                symbol: symbol.clone(),
                date: day,
            });
            if max_symbol_days.is_some_and(|max| jobs.len() >= max) {
                return jobs;
            }
        }
        day = day.succ_opt().expect("date overflow");
    }
    jobs
}

fn incremental_path(data_root: &Path, symbol: &str, date: NaiveDate) -> PathBuf {
    data_root
        .join("external")
        .join("bullish_incremental_book_L2")
        .join(format!("symbol={symbol}"))
        .join(format!("dt={date}"))
        .join(format!("{symbol}.csv.gz"))
}

fn trades_path(data_root: &Path, symbol: &str, date: NaiveDate) -> PathBuf {
    data_root
        .join("external")
        .join("bullish_trades")
        .join(format!("symbol={symbol}"))
        .join(format!("dt={date}"))
        .join(format!("{symbol}.csv.gz"))
}

fn panel_output_dir(
    data_root: &Path,
    panel_dataset: &str,
    run_tag: &str,
    symbol: &str,
    date: NaiveDate,
) -> PathBuf {
    data_root
        .join("derived")
        .join(panel_dataset)
        .join(format!("run_tag={run_tag}"))
        .join(format!("symbol={symbol}"))
        .join(format!("dt={date}"))
}

fn rows_by_symbol(rows: &[FeatureRow]) -> HashMap<String, Vec<&FeatureRow>> {
    let mut out = HashMap::<String, Vec<&FeatureRow>>::new();
    for row in rows {
        out.entry(row.symbol.clone()).or_default().push(row);
    }
    for rows in out.values_mut() {
        rows.sort_by_key(|row| row.local_timestamp);
    }
    out
}

fn rows_by_symbol_owned(rows: &[FeatureRow]) -> HashMap<String, Vec<FeatureRow>> {
    let mut out = HashMap::<String, Vec<FeatureRow>>::new();
    for row in rows {
        out.entry(row.symbol.clone()).or_default().push(row.clone());
    }
    for rows in out.values_mut() {
        rows.sort_by_key(|row| row.local_timestamp);
    }
    out
}

fn lower_bound_feature_ts(rows: &[FeatureRow], ts: u64) -> usize {
    let mut left = 0usize;
    let mut right = rows.len();
    while left < right {
        let mid = (left + right) / 2;
        if rows[mid].local_timestamp < ts {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}

fn nearest_other_values(
    rows: &[&FeatureRow],
    other: &[&FeatureRow],
    feature_name: &str,
    mlofi_weights: &[f64; 6],
    tolerance_us: u64,
) -> Vec<f64> {
    rows.iter()
        .map(|row| {
            let idx = lower_bound_feature_ref_ts(other, row.local_timestamp);
            let candidates = [idx.checked_sub(1), Some(idx)]
                .into_iter()
                .flatten()
                .filter_map(|i| other.get(i).copied())
                .collect::<Vec<_>>();
            candidates
                .into_iter()
                .filter_map(|candidate| {
                    let diff = candidate.local_timestamp.abs_diff(row.local_timestamp);
                    (diff <= tolerance_us)
                        .then(|| (diff, feature_value(candidate, feature_name, mlofi_weights)))
                })
                .min_by_key(|(diff, _)| *diff)
                .map(|(_, value)| value)
                .unwrap_or(f64::NAN)
        })
        .collect()
}

fn lower_bound_feature_ref_ts(rows: &[&FeatureRow], ts: u64) -> usize {
    let mut left = 0usize;
    let mut right = rows.len();
    while left < right {
        let mid = (left + right) / 2;
        if rows[mid].local_timestamp < ts {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    left
}

fn gate_passes(
    value: f64,
    gate: &str,
    low_threshold: Option<f64>,
    high_threshold: Option<f64>,
) -> bool {
    if !value.is_finite() {
        return false;
    }
    if gate.starts_with("high") {
        high_threshold.is_some_and(|threshold| value >= threshold)
    } else {
        low_threshold.is_some_and(|threshold| value <= threshold)
    }
}

fn opposite_side(side: &str) -> &str {
    if side == "long" { "short" } else { "long" }
}

fn parse_mlofi_level(name: &str) -> Option<usize> {
    match name {
        "mlofi_norm_l1" => Some(0),
        "mlofi_norm_l2" => Some(1),
        "mlofi_norm_l3" => Some(2),
        "mlofi_norm_l5" => Some(3),
        "mlofi_norm_l10" => Some(4),
        "mlofi_norm_l25" => Some(5),
        _ => None,
    }
}

fn price_key(price: f64) -> i64 {
    (price * PRICE_SCALE).round() as i64
}

fn key_price(key: i64) -> f64 {
    key as f64 / PRICE_SCALE
}

fn depth_from_levels(levels: &[Level], n: usize) -> f64 {
    levels.iter().take(n).map(|level| level.amount).sum()
}

fn imbalance(bid: f64, ask: f64) -> Option<f64> {
    let total = bid + ask;
    if total > EPS {
        finite((bid - ask) / total)
    } else {
        None
    }
}

fn safe_div_opt(num: f64, den: f64) -> Option<f64> {
    if den.abs() > EPS {
        finite(num / den)
    } else {
        None
    }
}

fn finite(value: f64) -> Option<f64> {
    if value.is_finite() { Some(value) } else { None }
}

fn rate(num: usize, den: usize) -> f64 {
    if den == 0 {
        0.0
    } else {
        num as f64 / den as f64
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
        Some((values[mid - 1] + values[mid]) * 0.5)
    } else {
        Some(values[mid])
    }
}

fn quantile(mut values: Vec<f64>, q: f64) -> Option<f64> {
    values.retain(|value| value.is_finite());
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let idx = ((values.len() - 1) as f64 * q.clamp(0.0, 1.0)).round() as usize;
    values.get(idx).copied()
}

fn robust_mad(values: &[f64], center: f64) -> f64 {
    let deviations = values
        .iter()
        .filter(|value| value.is_finite())
        .map(|value| (value - center).abs())
        .collect::<Vec<_>>();
    median(deviations).unwrap_or(1.0).max(1e-9)
}

fn correlation(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 3 {
        return None;
    }
    let pairs = xs
        .iter()
        .zip(ys.iter())
        .filter(|(x, y)| x.is_finite() && y.is_finite())
        .map(|(x, y)| (*x, *y))
        .collect::<Vec<_>>();
    if pairs.len() < 3 {
        return None;
    }
    let mean_x = pairs.iter().map(|(x, _)| *x).sum::<f64>() / pairs.len() as f64;
    let mean_y = pairs.iter().map(|(_, y)| *y).sum::<f64>() / pairs.len() as f64;
    let mut cov = 0.0;
    let mut vx = 0.0;
    let mut vy = 0.0;
    for (x, y) in pairs {
        let dx = x - mean_x;
        let dy = y - mean_y;
        cov += dx * dy;
        vx += dx * dx;
        vy += dy * dy;
    }
    if vx <= EPS || vy <= EPS {
        None
    } else {
        finite(cov / (vx.sqrt() * vy.sqrt()))
    }
}

fn book_levels_json(levels: &[Level]) -> String {
    serde_json::to_string(
        &levels
            .iter()
            .take(25)
            .map(|level| (level.price, level.amount))
            .collect::<Vec<_>>(),
    )
    .unwrap_or_else(|_| "[]".to_string())
}

fn hour_from_us(timestamp_us: u64) -> Result<String> {
    let secs = (timestamp_us / 1_000_000) as i64;
    let dt = Utc
        .timestamp_opt(secs, 0)
        .single()
        .ok_or_else(|| anyhow!("invalid timestamp_us {timestamp_us}"))?;
    Ok(dt.format("%Y-%m-%dT%H:00:00Z").to_string())
}

fn parse_default_date(raw: &str) -> NaiveDate {
    NaiveDate::parse_from_str(raw, "%Y-%m-%d").expect("valid default date")
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

fn temp_path_for(path: &Path) -> PathBuf {
    let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let stamp = Utc::now().timestamp_micros();
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("cc_fixed_event_output");
    std::env::temp_dir().join(format!("{file_name}.{pid}.{stamp}.{counter}.tmp"))
}

fn replace_with_temp(temp: &Path, path: &Path) -> Result<()> {
    ensure_parent_dir(path)?;
    for attempt in 0..REPLACE_RETRIES {
        if path.exists() {
            match fs::remove_file(path) {
                Ok(()) => {}
                Err(err) if attempt + 1 < REPLACE_RETRIES => {
                    thread::sleep(Duration::from_millis(REPLACE_RETRY_MS));
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
            Err(err) if attempt + 1 < REPLACE_RETRIES => {
                thread::sleep(Duration::from_millis(REPLACE_RETRY_MS));
                if !temp.exists() {
                    return Err(err).with_context(|| {
                        format!("failed to move {} to {}", temp.display(), path.display())
                    });
                }
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

#[cfg(test)]
mod tests {
    use super::*;

    fn update(ts: u64, snap: bool, side: Side, price: f64, amount: f64) -> IncrementalUpdate {
        IncrementalUpdate {
            exchange: "bullish".to_string(),
            symbol: "CCUSDT".to_string(),
            timestamp: ts,
            local_timestamp: ts,
            is_snapshot: snap,
            side,
            price,
            amount,
        }
    }

    fn trade(ts: u64, side: &str, price: f64, amount: f64) -> TradeState {
        TradeState {
            timestamp: ts,
            local_timestamp: ts,
            id: format!("t{ts}"),
            side: side.to_string(),
            price,
            amount,
            remaining: amount,
        }
    }

    fn feature_row(date: &str, ts: u64, event_index: usize, value: f64) -> FeatureRow {
        FeatureRow {
            date: date.to_string(),
            symbol: "CCUSDT".to_string(),
            local_timestamp: ts,
            event_index,
            hour_utc: "2026-05-06T00:00:00Z".to_string(),
            mid_price: 10.0 + event_index as f64 * 0.01,
            spread_bps: 1.0,
            factor_eligible: true,
            ofi_l1_depth_norm: value,
            mlofi_norm: [value, 0.0, 0.0, 0.0, 0.0, 0.0],
            mlofi_roll10: [value, 0.0, 0.0, 0.0, 0.0, 0.0],
            queue_imbalance_1: 0.0,
            queue_imbalance_5: 0.0,
            queue_imbalance_25: 0.0,
            microprice_dev_bps: 0.0,
            queue_depletion_intensity: 0.0,
            replenish_intensity: 0.0,
            cancellation_withdrawal_intensity: 0.0,
            trade_arrival_alignment: 0.0,
            liquidity_shock_score: 0.0,
            low_confidence_split: false,
            cross_venue_mlofi_lead_lag: f64::NAN,
        }
    }

    fn candidate_key() -> CandidateKey {
        CandidateKey {
            fold: "fold1".to_string(),
            symbol: "CCUSDT".to_string(),
            feature_name: "mlofi_norm_l1".to_string(),
            gate: "high_train_q80".to_string(),
            side: "long".to_string(),
            horizon_events: 10,
            low_gate_threshold: Some(-1.0),
            high_gate_threshold: Some(1.0),
        }
    }

    fn ranking_row(side_return: f64, fav_adv: f64) -> PathRankingRow {
        PathRankingRow {
            run_tag: "test".to_string(),
            fit_scope: "train_only;ranking_scope=base".to_string(),
            fold: "fold1".to_string(),
            symbol: "CCUSDT".to_string(),
            feature_name: "mlofi_norm_l1".to_string(),
            feature_family: "MLOFI".to_string(),
            gate: "high_train_q80".to_string(),
            side: "long".to_string(),
            horizon_events: 10,
            first_passage_barrier_bps: 1.0,
            validation_rows: 100,
            selected_rows: 25,
            selected_rate: 0.25,
            favorable_rate: 0.6,
            adverse_rate: 0.4,
            favorable_minus_adverse_rate: fav_adv,
            side_return_bps_mean: side_return,
            drawup_drawdown_asymmetry_bps_mean: 0.0,
            nonoverlap_buckets: 10,
            positive_bucket_rate: 0.7,
            score: side_return + fav_adv,
            guardrail: GUARDRAIL.to_string(),
        }
    }

    fn control_row(control_type: &str, side_return: f64, fav_adv: f64) -> NegativeControlRow {
        NegativeControlRow {
            run_tag: "test".to_string(),
            control_type: control_type.to_string(),
            fold: "fold1".to_string(),
            symbol: "CCUSDT".to_string(),
            feature_name: "mlofi_norm_l1".to_string(),
            gate: "high_train_q80".to_string(),
            side: "long".to_string(),
            horizon_events: 10,
            selected_rows: 25,
            favorable_minus_adverse_rate: fav_adv,
            side_return_bps_mean: side_return,
            control_note: "test".to_string(),
            guardrail: GUARDRAIL.to_string(),
        }
    }

    fn feature_param(name: &str) -> FeatureParam {
        FeatureParam {
            feature_name: name.to_string(),
            median: 0.0,
            mad: 1.0,
            q20: -1.0,
            q80: 1.0,
            low_gate_threshold: Some(-1.0),
            high_gate_threshold: Some(1.0),
            gate_policy: "test".to_string(),
            mlofi_weight: 0.0,
        }
    }

    #[test]
    fn default_config_uses_ccusdt_paths_and_labels() {
        let config = CcFixedEventConfig::default();
        assert_eq!(config.data_root, PathBuf::from("data/ccusdt/v1"));
        assert_eq!(config.doc_dir, PathBuf::from("docs/markets/ccusdt"));
        assert_eq!(config.output_prefix, "ccusdt_v1_fixed_event_factors");
        assert_eq!(config.panel_dataset, "ccusdt_v1_fixed_event_factor_panel");
        assert_eq!(config.report_name, "v1-fixed-event-orderbook-factors-v3.md");
        assert_eq!(config.market_label, "CCUSDT");
        assert_eq!(config.symbols, "CCUSDT");
    }

    #[test]
    fn quality_status_warns_on_rebuild_anomalies() {
        let mut stats = DayStats::default();
        assert_eq!(quality_status(&stats, "normal", None), "completed");

        stats.book_disorder_rows = 1;
        assert_eq!(
            quality_status(&stats, "normal", None),
            "completed_with_quality_warnings"
        );
        stats.book_disorder_rows = 0;

        assert_eq!(
            quality_status(&stats, "low_confidence", None),
            "completed_with_quality_warnings"
        );
        assert_eq!(
            quality_status(&stats, "normal", Some(1)),
            "completed_with_quality_warnings"
        );
    }

    #[test]
    fn snapshot_batch_resets_book() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 1.0),
                update(1, true, Side::Ask, 11.0, 1.0),
                update(2, false, Side::Bid, 10.0, 2.0),
                update(3, true, Side::Bid, 20.0, 1.0),
                update(3, true, Side::Ask, 21.0, 1.0),
            ],
            &[],
        );
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[1].best_bid_price, Some(10.0));
        assert_eq!(rows[2].best_bid_price, Some(20.0));
        assert_eq!(rows[2].bid_levels, 1);
    }

    #[test]
    fn consecutive_snapshot_batches_rebuild_each_time() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 10.0),
                update(1, true, Side::Ask, 11.0, 10.0),
                update(2, true, Side::Bid, 20.0, 2.0),
                update(2, true, Side::Ask, 21.0, 3.0),
            ],
            &[],
        );
        assert_eq!(rows.len(), 2);
        assert!(rows[0].is_snapshot_batch);
        assert!(
            !rows[0].factor_eligible,
            "first snapshot has no prior state"
        );
        assert_eq!(rows[1].best_bid_price, Some(20.0));
        assert_eq!(rows[1].best_ask_price, Some(21.0));
        assert_eq!(rows[1].bid_levels, 1);
        assert_eq!(rows[1].ask_levels, 1);
        assert!(rows[1].factor_eligible);
        assert!(rows[1].ofi_l1_raw > 0.0);
    }

    #[test]
    fn price_level_classification_add_decrease_remove() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 10.0),
                update(1, true, Side::Ask, 11.0, 10.0),
                update(2, false, Side::Bid, 10.0, 12.0),
                update(3, false, Side::Bid, 10.0, 7.0),
                update(4, false, Side::Bid, 10.0, 0.0),
            ],
            &[],
        );
        assert_eq!(rows[1].replenish_bid_amount, 2.0);
        assert_eq!(rows[2].decrease_bid_amount, 5.0);
        assert_eq!(rows[3].remove_bid_amount, 7.0);
        assert_eq!(rows[3].cancel_bid_amount, 7.0);
    }

    #[test]
    fn ofi_best_level_signs_follow_cks_buy_pressure() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 10.0),
                update(1, true, Side::Ask, 11.0, 10.0),
                update(2, false, Side::Bid, 10.5, 3.0),
                update(3, false, Side::Ask, 10.8, 4.0),
                update(4, false, Side::Ask, 10.8, 0.0),
            ],
            &[],
        );
        assert!(rows[1].ofi_l1_raw > 0.0, "bid price up is positive");
        assert!(rows[2].ofi_l1_raw < 0.0, "ask price down is negative");
        assert!(rows[3].ofi_l1_raw > 0.0, "ask price up is positive");
    }

    #[test]
    fn mlofi_signs_on_price_shift_and_size_change() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 10.0),
                update(1, true, Side::Bid, 9.9, 10.0),
                update(1, true, Side::Ask, 11.0, 10.0),
                update(1, true, Side::Ask, 11.1, 10.0),
                update(2, false, Side::Bid, 9.9, 12.0),
                update(3, false, Side::Ask, 11.0, 8.0),
            ],
            &[],
        );
        assert!(
            rows[1].mlofi_raw_l2 > 0.0,
            "bid size add at level 2 is positive"
        );
        assert!(
            rows[2].mlofi_raw_l1 > 0.0,
            "ask size decrease at best is positive buy pressure"
        );
    }

    #[test]
    fn trades_match_buy_to_ask_and_sell_to_bid() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 10.0),
                update(1, true, Side::Ask, 11.0, 10.0),
                update(2, false, Side::Ask, 11.0, 6.0),
                update(3, false, Side::Bid, 10.0, 7.0),
            ],
            &[trade(2, "buy", 11.0, 4.0), trade(3, "sell", 10.0, 3.0)],
        );
        assert_eq!(rows[1].execute_ask_amount, 4.0);
        assert_eq!(rows[1].cancel_ask_amount, 0.0);
        assert_eq!(rows[2].execute_bid_amount, 3.0);
        assert_eq!(rows[2].cancel_bid_amount, 0.0);
    }

    #[test]
    fn trade_window_stats_are_past_only_for_factor_inputs() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1_000_000, true, Side::Bid, 10.0, 10.0),
                update(1_000_000, true, Side::Ask, 11.0, 10.0),
                update(3_000_000, false, Side::Ask, 11.0, 9.0),
            ],
            &[
                trade(2_900_000, "buy", 11.0, 1.0),
                trade(3_100_000, "sell", 10.0, 5.0),
            ],
        );
        assert_eq!(rows[1].trade_window_count, 1);
        assert_eq!(rows[1].trade_buy_amount, 1.0);
        assert_eq!(rows[1].trade_sell_amount, 0.0);
        assert_eq!(rows[1].trade_arrival_alignment, Some(1.0));
    }

    #[test]
    fn future_trades_do_not_create_trade_arrival_alignment() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1_000_000, true, Side::Bid, 10.0, 10.0),
                update(1_000_000, true, Side::Ask, 11.0, 10.0),
                update(3_000_000, false, Side::Ask, 11.0, 9.0),
            ],
            &[trade(3_100_000, "buy", 11.0, 5.0)],
        );
        assert_eq!(rows[1].trade_window_count, 0);
        assert_eq!(rows[1].trade_arrival_alignment, None);
    }

    #[test]
    fn unmatched_decrease_is_cancellation() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 10.0),
                update(1, true, Side::Ask, 11.0, 10.0),
                update(2, false, Side::Ask, 11.0, 8.0),
            ],
            &[],
        );
        assert_eq!(rows[1].execute_ask_amount, 0.0);
        assert_eq!(rows[1].cancel_ask_amount, 2.0);
    }

    #[test]
    fn future_trades_do_not_match_depletion_for_factor_inputs() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1_000_000, true, Side::Bid, 10.0, 10.0),
                update(1_000_000, true, Side::Ask, 11.0, 10.0),
                update(3_000_000, false, Side::Ask, 11.0, 8.0),
            ],
            &[trade(3_100_000, "buy", 11.0, 2.0)],
        );
        assert_eq!(rows[1].execute_ask_amount, 0.0);
        assert_eq!(rows[1].cancel_ask_amount, 2.0);
    }

    #[test]
    fn crossed_cleanup_event_is_not_factor_eligible() {
        let rows = replay_event_panel_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 10.0, 10.0),
                update(1, true, Side::Ask, 11.0, 5.0),
                update(2, false, Side::Bid, 11.5, 2.0),
            ],
            &[],
        );
        assert_eq!(rows[1].crossed_levels_removed, 1);
        assert!(!rows[1].factor_eligible);
        assert_eq!(rows[1].ofi_l1_raw, 0.0);
    }

    #[test]
    fn crossed_snapshot_batch_is_counted_as_book_disorder() {
        let (rows, stats) = replay_event_panel_with_stats_from_updates(
            "test",
            "2026-05-06",
            "CCUSDT",
            &[
                update(1, true, Side::Bid, 12.0, 10.0),
                update(1, true, Side::Ask, 11.0, 10.0),
            ],
            &[],
        );
        assert_eq!(rows.len(), 1);
        assert!(!rows[0].factor_eligible);
        assert_eq!(rows[0].crossed_levels_removed, 0);
        assert_eq!(stats.book_disorder_rows, 1);
    }

    #[test]
    fn within_day_shuffle_is_deterministic_and_stays_inside_date() {
        let rows = [
            feature_row("2026-05-06", 1, 1, 1.0),
            feature_row("2026-05-06", 2, 2, 2.0),
            feature_row("2026-05-06", 3, 3, 3.0),
            feature_row("2026-05-06", 4, 4, 4.0),
            feature_row("2026-05-07", 5, 5, 10.0),
            feature_row("2026-05-07", 6, 6, 20.0),
            feature_row("2026-05-07", 7, 7, 30.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();
        let weights = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let candidate = candidate_key();
        let shuffled_a =
            within_day_shuffled_feature_values(&refs, "mlofi_norm_l1", &weights, &candidate);
        let shuffled_b =
            within_day_shuffled_feature_values(&refs, "mlofi_norm_l1", &weights, &candidate);
        assert_eq!(shuffled_a, shuffled_b);
        assert_ne!(shuffled_a[0..4], [1.0, 2.0, 3.0, 4.0]);
        assert_ne!(shuffled_a[4..7], [10.0, 20.0, 30.0]);
        assert!(shuffled_a[0..4].iter().all(|value| *value <= 4.0));
        assert!(shuffled_a[4..7].iter().all(|value| *value >= 10.0));
    }

    #[test]
    fn future_shift_placebo_does_not_wrap_validation_tail() {
        let rows = [
            feature_row("2026-05-06", 1, 1, 1.0),
            feature_row("2026-05-06", 2, 2, 2.0),
            feature_row("2026-05-06", 3, 3, 3.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();
        let shifted = shifted_feature_values_no_wrap(
            &refs,
            "mlofi_norm_l1",
            &[1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            2,
        );
        assert_eq!(shifted[0], 3.0);
        assert!(shifted[1].is_nan());
        assert!(shifted[2].is_nan());
    }

    #[test]
    fn first_passage_outcome_requires_full_horizon() {
        let rows = [
            feature_row("2026-05-06", 1, 1, 1.0),
            feature_row("2026-05-06", 2, 2, 2.0),
            feature_row("2026-05-06", 3, 3, 3.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();
        assert!(first_passage_outcome(&refs, 0, 2, "long", 1.0).is_some());
        assert!(first_passage_outcome(&refs, 1, 2, "long", 1.0).is_none());
        assert!(first_passage_outcome(&refs, 0, 3, "long", 1.0).is_none());
    }

    #[test]
    fn top_report_filters_control_dominated_candidates() {
        let base = ranking_row(2.0, 0.10);
        let stronger_future = control_row("future_shift_placebo", 2.1, 0.05);
        let weaker_shuffled = control_row("within_day_shuffled_event_time", 1.0, 0.05);
        assert!(
            reportable_top_rankings(
                std::slice::from_ref(&base),
                &[stronger_future, weaker_shuffled.clone()],
                10
            )
            .is_empty()
        );

        let weaker_future = control_row("future_shift_placebo", 1.0, 0.05);
        assert!(
            reportable_top_rankings(std::slice::from_ref(&base), &[weaker_future.clone()], 10)
                .is_empty()
        );

        let top = reportable_top_rankings(
            std::slice::from_ref(&base),
            &[weaker_future, weaker_shuffled],
            10,
        );
        assert_eq!(top.len(), 1);
    }

    #[test]
    fn top_report_wrong_symbol_control_is_optional_but_binding_when_present() {
        let base = ranking_row(2.0, 0.10);
        let weaker_future = control_row("future_shift_placebo", 1.0, 0.05);
        let weaker_shuffled = control_row("within_day_shuffled_event_time", 1.0, 0.05);
        let top = reportable_top_rankings(
            std::slice::from_ref(&base),
            &[weaker_future.clone(), weaker_shuffled.clone()],
            10,
        );
        assert_eq!(top.len(), 1);

        let stronger_wrong = control_row("wrong_symbol_same_factor", 2.1, 0.05);
        assert!(
            reportable_top_rankings(
                std::slice::from_ref(&base),
                &[weaker_future, weaker_shuffled, stronger_wrong],
                10,
            )
            .is_empty()
        );
    }

    #[test]
    fn top_report_dedupes_feature_transforms_by_best_score() {
        let raw = ranking_row(1.0, 0.05);
        let mut positive = ranking_row(2.0, 0.10);
        positive.feature_name = "pos__mlofi_norm_l1".to_string();
        positive.score = 10.0;
        let mut future = control_row("future_shift_placebo", 0.5, 0.01);
        future.feature_name = positive.feature_name.clone();
        let mut shuffled = control_row("within_day_shuffled_event_time", 0.5, 0.01);
        shuffled.feature_name = positive.feature_name.clone();
        let controls = [future, shuffled];
        let rankings = [raw, positive];
        let top = reportable_top_rankings(&rankings, &controls, 10);
        assert_eq!(top.len(), 1);
        assert_eq!(top[0].feature_name, "pos__mlofi_norm_l1");
    }

    #[test]
    fn top_candidates_dedupes_feature_transforms_by_best_score() {
        let raw = ranking_row(1.0, 0.05);
        let mut positive = ranking_row(2.0, 0.10);
        positive.feature_name = "pos__mlofi_norm_l1".to_string();
        positive.score = 10.0;
        let mut features = HashMap::new();
        features.insert(raw.feature_name.clone(), feature_param(&raw.feature_name));
        features.insert(
            positive.feature_name.clone(),
            feature_param(&positive.feature_name),
        );
        let fit = FoldFit {
            fold: "fold1".to_string(),
            symbol: "CCUSDT".to_string(),
            train_rows: 100,
            valid_rows: 100,
            features,
            horizons: vec![10],
            barrier_bps: 1.0,
            shock_threshold: 0.0,
            nonzero_mid_move_median_events: 0.0,
            mlofi_weights: [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            valid_start: 0,
            valid_end: 100,
        };
        let candidates = top_candidates(&[raw, positive], &[fit]);
        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].feature_name, "pos__mlofi_norm_l1");
    }

    #[test]
    fn zero_inflated_positive_gate_uses_nonzero_high_quantile() {
        let values = (0..125)
            .map(|idx| if idx < 100 { 0.0 } else { (idx - 99) as f64 })
            .collect::<Vec<_>>();
        let (low, high, policy) = derive_gate_thresholds("pos__mlofi_roll10_l5", &values, 0.0, 0.0);
        assert!(low.is_none());
        assert!(high.is_some_and(|threshold| threshold > 0.0));
        assert!(policy.contains("zero_inflated"));
        assert!(!gate_passes(0.0, "high_train_q80", low, high));
        assert!(gate_passes(25.0, "high_train_q80", low, high));
    }
}

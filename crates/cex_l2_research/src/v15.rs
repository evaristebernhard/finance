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
const STRATEGY_ID: &str = "v15_fibonacci_rsi_book_level_path_diagnostics";
const FILE_REPLACE_RETRIES: usize = 80;
const FILE_REPLACE_RETRY_MS: u64 = 250;
const MIN_SIGMA_BPS: f64 = 0.50;
const TICK_FLOOR_BPS: f64 = 0.10;
const SWING_LOOKBACK_EVENTS: usize = 360;
const RSI_LOOKBACK_EXTREME_EVENTS: usize = 60;
const MIN_SWING_EVENTS: usize = 90;
const EVENT_GAP: usize = 30;
const MAX_EVENTS_PER_VARIANT_FOLD_SYMBOL: usize = 2_000;
const PATH_HORIZON_EVENTS: usize = 150;
const SHIFT_60S_US: u64 = 60_000_000;
const FIB_RATIOS: [f64; 3] = [0.382, 0.500, 0.618];
const EXTENSION_RATIOS: [f64; 2] = [1.272, 1.618];
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct V15Config {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub doc_dir: PathBuf,
    pub run_tag: String,
    pub fee_bps: f64,
    pub symbols: String,
}

impl Default for V15Config {
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
pub struct V15Summary {
    pub run_tag: String,
    pub panel_rows: usize,
    pub usable_rows: usize,
    pub fold_rows: usize,
    pub level_rows: usize,
    pub event_rows: usize,
    pub path_profile_rows: usize,
    pub summary_rows: usize,
    pub negative_control_rows: usize,
    pub diagnostic_rows: usize,
    pub plot_rows: usize,
    pub primary_status: String,
    pub levels_csv: String,
    pub events_csv: String,
    pub path_profiles_csv: String,
    pub summary_csv: String,
    pub negative_controls_csv: String,
    pub diagnostics_csv: String,
    pub manifest_csv: String,
    pub report_md: String,
    pub path_mix_svg: String,
    pub return_svg: String,
    pub control_svg: String,
    pub sample_overlay_svg: String,
}

#[derive(Debug, Clone)]
struct Paths {
    levels_csv: PathBuf,
    events_csv: PathBuf,
    path_profiles_csv: PathBuf,
    summary_csv: PathBuf,
    negative_controls_csv: PathBuf,
    diagnostics_csv: PathBuf,
    manifest_csv: PathBuf,
    report_md: PathBuf,
    path_mix_svg: PathBuf,
    return_svg: PathBuf,
    control_svg: PathBuf,
    sample_overlay_svg: PathBuf,
    filter_params_csv: PathBuf,
}

impl Paths {
    fn new(config: &V15Config) -> Self {
        let figures_dir = config.doc_dir.join("figures");
        Self {
            levels_csv: config.date_dir.join(format!(
                "bonk_v15_fib_rsi_book_levels_{}.csv",
                config.run_tag
            )),
            events_csv: config.date_dir.join(format!(
                "bonk_v15_fib_rsi_book_events_{}.csv",
                config.run_tag
            )),
            path_profiles_csv: config.date_dir.join(format!(
                "bonk_v15_fib_rsi_book_path_profiles_{}.csv",
                config.run_tag
            )),
            summary_csv: config.date_dir.join(format!(
                "bonk_v15_fib_rsi_book_summary_{}.csv",
                config.run_tag
            )),
            negative_controls_csv: config.date_dir.join(format!(
                "bonk_v15_fib_rsi_book_negative_controls_{}.csv",
                config.run_tag
            )),
            diagnostics_csv: config.date_dir.join(format!(
                "bonk_v15_fib_rsi_book_diagnostics_{}.csv",
                config.run_tag
            )),
            manifest_csv: config.date_dir.join(format!(
                "bonk_v15_fib_rsi_book_manifest_{}.csv",
                config.run_tag
            )),
            report_md: config
                .doc_dir
                .join("v1-cex-v15-fibonacci-rsi-book-levels.md"),
            path_mix_svg: figures_dir.join(format!(
                "bonk_v15_fib_rsi_book_path_mix_{}.svg",
                config.run_tag
            )),
            return_svg: figures_dir.join(format!(
                "bonk_v15_fib_rsi_book_returns_{}.svg",
                config.run_tag
            )),
            control_svg: figures_dir.join(format!(
                "bonk_v15_fib_rsi_book_controls_{}.svg",
                config.run_tag
            )),
            sample_overlay_svg: figures_dir.join(format!(
                "bonk_v15_fib_rsi_book_sample_overlay_{}.svg",
                config.run_tag
            )),
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
    is_snapshot_batch: bool,
    factor_eligible: bool,
    execute_cancel_confidence: String,
    crossed_levels_removed: usize,
    mid_price: f64,
    spread_bps: f64,
    microprice: Option<f64>,
    microprice_dev_bps: f64,
    best_bid_price: Option<f64>,
    best_ask_price: Option<f64>,
    best_bid_amount: f64,
    best_ask_amount: f64,
    bid_depth_5: f64,
    ask_depth_5: f64,
    bid_depth_25: f64,
    ask_depth_25: f64,
    queue_imbalance_5: f64,
    queue_imbalance_25: f64,
    mlofi_norm_l5: f64,
    mlofi_norm_l10: f64,
    mlofi_norm_l25: f64,
    mlofi_roll10_l5: f64,
    mlofi_roll10_l10: f64,
    mlofi_roll10_l25: f64,
    trade_buy_amount: f64,
    trade_sell_amount: f64,
    trade_flow_imbalance: f64,
    trade_arrival_alignment: f64,
    depletion_bid_amount: f64,
    depletion_ask_amount: f64,
    replenish_bid_amount: f64,
    replenish_ask_amount: f64,
    cancel_bid_amount: f64,
    cancel_ask_amount: f64,
    remove_bid_amount: f64,
    remove_ask_amount: f64,
    queue_depletion_intensity: f64,
    replenish_intensity: f64,
    cancellation_withdrawal_intensity: f64,
    liquidity_shock_score: f64,
    bid_top_levels_json: String,
    ask_top_levels_json: String,
    rv30_bps: f64,
    sigma_bps: f64,
    rsi_fast: f64,
    rsi_slow: f64,
    rsi_diff: f64,
    rsi_diff_delta: f64,
    microprice_drift_bps: f64,
}

impl PanelRow {
    fn from_panel(row: EventPanelRow) -> Option<Self> {
        let mid_price = row.mid_price.and_then(finite)?;
        if mid_price <= 0.0 {
            return None;
        }
        let spread_bps = row.spread_bps.and_then(finite).unwrap_or(0.0).max(0.0);
        Some(Self {
            run_tag: row.run_tag,
            date: row.date,
            symbol: row.symbol,
            timestamp: row.timestamp,
            local_timestamp: row.local_timestamp,
            event_index: row.event_index,
            is_snapshot_batch: row.is_snapshot_batch,
            factor_eligible: row.factor_eligible,
            execute_cancel_confidence: row.execute_cancel_confidence,
            crossed_levels_removed: row.crossed_levels_removed,
            mid_price,
            spread_bps,
            microprice: row.microprice.and_then(finite).filter(|value| *value > 0.0),
            microprice_dev_bps: row.microprice_dev_bps.and_then(finite).unwrap_or(0.0),
            best_bid_price: row.best_bid_price.and_then(finite),
            best_ask_price: row.best_ask_price.and_then(finite),
            best_bid_amount: row.best_bid_amount.and_then(finite).unwrap_or(0.0).max(0.0),
            best_ask_amount: row.best_ask_amount.and_then(finite).unwrap_or(0.0).max(0.0),
            bid_depth_5: row.bid_depth_5.max(0.0),
            ask_depth_5: row.ask_depth_5.max(0.0),
            bid_depth_25: row.bid_depth_25.max(0.0),
            ask_depth_25: row.ask_depth_25.max(0.0),
            queue_imbalance_5: row.queue_imbalance_5.and_then(finite).unwrap_or(0.0),
            queue_imbalance_25: row.queue_imbalance_25.and_then(finite).unwrap_or(0.0),
            mlofi_norm_l5: row.mlofi_norm_l5.and_then(finite).unwrap_or(0.0),
            mlofi_norm_l10: row.mlofi_norm_l10.and_then(finite).unwrap_or(0.0),
            mlofi_norm_l25: row.mlofi_norm_l25.and_then(finite).unwrap_or(0.0),
            mlofi_roll10_l5: finite(row.mlofi_roll10_l5).unwrap_or(0.0),
            mlofi_roll10_l10: finite(row.mlofi_roll10_l10).unwrap_or(0.0),
            mlofi_roll10_l25: finite(row.mlofi_roll10_l25).unwrap_or(0.0),
            trade_buy_amount: row.trade_buy_amount.max(0.0),
            trade_sell_amount: row.trade_sell_amount.max(0.0),
            trade_flow_imbalance: row.trade_flow_imbalance.and_then(finite).unwrap_or(0.0),
            trade_arrival_alignment: row.trade_arrival_alignment.and_then(finite).unwrap_or(0.0),
            depletion_bid_amount: row.depletion_bid_amount.max(0.0),
            depletion_ask_amount: row.depletion_ask_amount.max(0.0),
            replenish_bid_amount: row.replenish_bid_amount.max(0.0),
            replenish_ask_amount: row.replenish_ask_amount.max(0.0),
            cancel_bid_amount: row.cancel_bid_amount.max(0.0),
            cancel_ask_amount: row.cancel_ask_amount.max(0.0),
            remove_bid_amount: row.remove_bid_amount.max(0.0),
            remove_ask_amount: row.remove_ask_amount.max(0.0),
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
            bid_top_levels_json: row.bid_top_levels_json,
            ask_top_levels_json: row.ask_top_levels_json,
            rv30_bps: 0.0,
            sigma_bps: spread_bps.max(MIN_SIGMA_BPS),
            rsi_fast: 50.0,
            rsi_slow: 50.0,
            rsi_diff: 0.0,
            rsi_diff_delta: 0.0,
            microprice_drift_bps: 0.0,
        })
    }

    fn center_price(&self) -> f64 {
        self.microprice.unwrap_or(self.mid_price)
    }

    fn touch_band_bps(&self) -> f64 {
        self.spread_bps
            .max(0.25 * self.sigma_bps)
            .max(TICK_FLOOR_BPS)
    }

    fn level_dist_bps(&self, level_price: f64) -> f64 {
        if self.mid_price > 0.0 {
            (self.mid_price - level_price) / self.mid_price * 10_000.0
        } else {
            0.0
        }
    }

    fn book_confirm_score(&self, side_sign: i8) -> f64 {
        let side = side_sign as f64;
        let queue = side * (0.55 * self.queue_imbalance_25 + 0.45 * self.queue_imbalance_5);
        let flow = side * (0.45 * self.mlofi_roll10_l10 + 0.35 * self.mlofi_roll10_l5);
        let trade = side * self.trade_flow_imbalance;
        let replenish = if side_sign > 0 {
            signed_ratio(self.replenish_bid_amount, self.replenish_ask_amount)
        } else {
            signed_ratio(self.replenish_ask_amount, self.replenish_bid_amount)
        };
        let depth = if side_sign > 0 {
            signed_ratio(self.bid_depth_25, self.ask_depth_25)
        } else {
            signed_ratio(self.ask_depth_25, self.bid_depth_25)
        };
        0.30 * queue + 0.25 * flow + 0.20 * trade + 0.15 * replenish + 0.10 * depth
    }

    fn absorption_score(&self, side_sign: i8) -> f64 {
        if side_sign > 0 {
            let taker_against = self.trade_sell_amount + self.depletion_bid_amount;
            let defend = self.replenish_bid_amount
                + self.best_bid_amount
                + 0.20 * self.bid_depth_5
                + 0.10 * self.bid_depth_25;
            signed_ratio(defend, taker_against)
                + 0.35 * self.queue_imbalance_5
                + 0.20 * self.mlofi_roll10_l5
        } else {
            let taker_against = self.trade_buy_amount + self.depletion_ask_amount;
            let defend = self.replenish_ask_amount
                + self.best_ask_amount
                + 0.20 * self.ask_depth_5
                + 0.10 * self.ask_depth_25;
            signed_ratio(defend, taker_against)
                - 0.35 * self.queue_imbalance_5
                - 0.20 * self.mlofi_roll10_l5
        }
    }

    fn taker_pressure_against_level(&self, side_sign: i8) -> f64 {
        if side_sign > 0 {
            self.trade_sell_amount + self.depletion_bid_amount
        } else {
            self.trade_buy_amount + self.depletion_ask_amount
        }
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
#[allow(dead_code)]
struct FoldSpec {
    fold: String,
    symbol: String,
    train_start: u64,
    train_end: u64,
    valid_start: u64,
    valid_end: u64,
}

#[derive(Debug, Clone, Copy)]
struct Swing {
    lookback_events: usize,
    low_price: f64,
    high_price: f64,
    low_pos: usize,
    high_pos: usize,
}

impl Swing {
    fn range(&self) -> f64 {
        self.high_price - self.low_price
    }

    fn side_sign(&self) -> i8 {
        if self.low_pos < self.high_pos { 1 } else { -1 }
    }

    fn start_pos(&self) -> usize {
        self.low_pos.min(self.high_pos)
    }

    fn end_pos(&self) -> usize {
        self.low_pos.max(self.high_pos)
    }
}

#[derive(Debug, Clone, Serialize)]
struct LevelRow {
    run_tag: String,
    draft_id: String,
    variant: String,
    fold: String,
    phase: String,
    date: String,
    symbol: String,
    event_ts: u64,
    event_index: usize,
    source_pos: usize,
    side: String,
    side_sign: i8,
    mid_price: f64,
    spread_bps: f64,
    sigma_bps: f64,
    best_bid_price: Option<f64>,
    best_ask_price: Option<f64>,
    level_id: String,
    level_type: String,
    level_price: f64,
    level_dist_bps: f64,
    touch_band_bps: f64,
    swing_lookback_events: usize,
    swing_start_event_index: usize,
    swing_end_event_index: usize,
    swing_low: f64,
    swing_high: f64,
    swing_range_bps: f64,
    fib_ratio: Option<f64>,
    extension_ratio: Option<f64>,
    rsi_fast: f64,
    rsi_slow: f64,
    rsi_diff: f64,
    rsi_diff_delta: f64,
    book_confirm_score: f64,
    absorption_score: f64,
    trigger_reason: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct EventRow {
    run_tag: String,
    draft_id: String,
    variant: String,
    negative_control_type: String,
    control_group_id: String,
    fold: String,
    phase: String,
    date: String,
    symbol: String,
    event_ts: u64,
    event_index: usize,
    source_pos: usize,
    side: String,
    side_sign: i8,
    mid_price: f64,
    spread_bps: f64,
    sigma_bps: f64,
    best_bid_price: Option<f64>,
    best_ask_price: Option<f64>,
    level_price: f64,
    level_type: String,
    level_dist_bps: f64,
    touch_band_bps: f64,
    trigger_reason: String,
    path_horizon_events: usize,
    path_barrier_bps: f64,
    path_label: String,
    favorable_first: bool,
    adverse_first: bool,
    timeout: bool,
    reaction_latency_events: Option<usize>,
    mfe_bps: f64,
    mae_bps: f64,
    side_return_bps: f64,
    rsi_fast: f64,
    rsi_slow: f64,
    rsi_diff: f64,
    rsi_diff_delta: f64,
    queue_imbalance_25: f64,
    mlofi_roll10_l10: f64,
    trade_flow_imbalance: f64,
    book_confirm_score: f64,
    absorption_score: f64,
    liquidity_shock_score: f64,
    factor_eligible: bool,
    execute_cancel_confidence: String,
    snapshot_batch: bool,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct PathProfileRow {
    run_tag: String,
    draft_id: String,
    variant: String,
    negative_control_type: String,
    side: String,
    path_horizon_events: usize,
    events: usize,
    favorable_first_rate: f64,
    adverse_first_rate: f64,
    timeout_rate: f64,
    mean_side_return_bps: f64,
    median_side_return_bps: f64,
    mean_mfe_bps: f64,
    mean_mae_bps: f64,
    mean_book_confirm_score: f64,
    mean_absorption_score: f64,
    max_date_share: f64,
    max_symbol_share: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct SummaryRow {
    run_tag: String,
    variant: String,
    negative_control_type: String,
    events: usize,
    favorable_first_rate: f64,
    adverse_first_rate: f64,
    favorable_minus_adverse_rate: f64,
    mean_side_return_bps: f64,
    median_side_return_bps: f64,
    mean_mfe_bps: f64,
    mean_mae_bps: f64,
    gross_after_fee_probe_bps: f64,
    max_date_share: f64,
    max_symbol_share: f64,
    pass_sample_500: bool,
    pass_date_concentration_035: bool,
    pass_symbol_concentration_070: bool,
    pass_positive_path_return: bool,
    primary_candidate: bool,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct NegativeControlRow {
    run_tag: String,
    variant: String,
    control_type: String,
    base_events: usize,
    control_events: usize,
    base_mean_side_return_bps: f64,
    control_mean_side_return_bps: f64,
    base_favorable_minus_adverse_rate: f64,
    control_favorable_minus_adverse_rate: f64,
    control_abs_ge_base_abs: bool,
    interpretation: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct DiagnosticRow {
    run_tag: String,
    metric: String,
    value: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct ManifestRow {
    run_tag: String,
    artifact: String,
    path: String,
    rows: usize,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct PathOutcome {
    label: String,
    favorable_first: bool,
    adverse_first: bool,
    timeout: bool,
    reaction_latency_events: Option<usize>,
    mfe_bps: f64,
    mae_bps: f64,
    side_return_bps: f64,
}

#[derive(Debug, Clone, Default)]
struct InputAudit {
    panel_files: usize,
    panel_rows: usize,
    usable_rows: usize,
    missing_panel: bool,
    blockers: Vec<String>,
}

pub fn run_v15(config: &V15Config) -> Result<V15Summary> {
    let paths = Paths::new(config);
    let symbols = parse_symbol_list(&config.symbols);
    if symbols.is_empty() {
        bail!("symbols cannot be empty");
    }

    let folds = load_folds(&paths.filter_params_csv, &config.run_tag, &symbols)?;
    let (mut rows, mut audit) = read_panel_rows(config, &symbols)?;
    rows.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.local_timestamp.cmp(&b.local_timestamp))
            .then_with(|| a.event_index.cmp(&b.event_index))
    });
    enrich_rolling_state(&mut rows);
    let by_symbol = rows_by_symbol(&rows);

    if folds.is_empty() {
        audit.blockers.push(format!(
            "missing fold params at {}",
            paths.filter_params_csv.display()
        ));
    }

    let mut levels = Vec::new();
    let mut events = Vec::new();
    if audit.blockers.is_empty() {
        build_level_events(config, &folds, &by_symbol, &mut levels, &mut events);
    }

    let path_profiles = build_path_profiles(&events);
    let mut summaries = build_summary_rows(config, &events);
    mark_primary_candidate(&mut summaries);
    let controls = build_negative_control_rows(&summaries);
    let diagnostics = build_diagnostics(&audit, &folds, &levels, &events, &summaries);
    let manifest = build_manifest(
        &paths,
        config,
        &levels,
        &events,
        &path_profiles,
        &summaries,
        &controls,
        &diagnostics,
    );

    write_csv_atomic(&paths.levels_csv, &levels)?;
    write_csv_atomic(&paths.events_csv, &events)?;
    write_csv_atomic(&paths.path_profiles_csv, &path_profiles)?;
    write_csv_atomic(&paths.summary_csv, &summaries)?;
    write_csv_atomic(&paths.negative_controls_csv, &controls)?;
    write_csv_atomic(&paths.diagnostics_csv, &diagnostics)?;
    write_csv_atomic(&paths.manifest_csv, &manifest)?;
    write_path_mix_svg(&paths.path_mix_svg, &summaries)?;
    write_return_svg(&paths.return_svg, &summaries)?;
    write_control_svg(&paths.control_svg, &controls)?;
    write_sample_overlay_svg(&paths.sample_overlay_svg, &events, &by_symbol)?;
    write_report(
        &paths,
        config,
        &audit,
        folds.len(),
        &summaries,
        &controls,
        &diagnostics,
    )?;

    let primary_status = primary_status(&audit, &summaries, &controls);
    Ok(V15Summary {
        run_tag: config.run_tag.clone(),
        panel_rows: audit.panel_rows,
        usable_rows: audit.usable_rows,
        fold_rows: folds.len(),
        level_rows: levels.len(),
        event_rows: events.len(),
        path_profile_rows: path_profiles.len(),
        summary_rows: summaries.len(),
        negative_control_rows: controls.len(),
        diagnostic_rows: diagnostics.len(),
        plot_rows: 4,
        primary_status,
        levels_csv: path_string(&paths.levels_csv),
        events_csv: path_string(&paths.events_csv),
        path_profiles_csv: path_string(&paths.path_profiles_csv),
        summary_csv: path_string(&paths.summary_csv),
        negative_controls_csv: path_string(&paths.negative_controls_csv),
        diagnostics_csv: path_string(&paths.diagnostics_csv),
        manifest_csv: path_string(&paths.manifest_csv),
        report_md: path_string(&paths.report_md),
        path_mix_svg: path_string(&paths.path_mix_svg),
        return_svg: path_string(&paths.return_svg),
        control_svg: path_string(&paths.control_svg),
        sample_overlay_svg: path_string(&paths.sample_overlay_svg),
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

fn read_panel_rows(config: &V15Config, symbols: &[String]) -> Result<(Vec<PanelRow>, InputAudit)> {
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
        collect_part_files_recursive(&base.join(format!("symbol={symbol}")), &mut out)?;
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
        let mut gains_fast = VecDeque::<f64>::new();
        let mut losses_fast = VecDeque::<f64>::new();
        let mut gains_slow = VecDeque::<f64>::new();
        let mut losses_slow = VecDeque::<f64>::new();
        let mut prev_rsi_diff = 0.0;
        for idx in start..end {
            let center = rows[idx].center_price();
            if let Some(prev) = prev_center {
                if prev > 0.0 {
                    let ret = (center - prev) / prev * 10_000.0;
                    if ret.is_finite() {
                        rows[idx].microprice_drift_bps = ret;
                        rets.push_back(ret);
                        while rets.len() > 30 {
                            rets.pop_front();
                        }
                        push_rsi(ret, &mut gains_fast, &mut losses_fast, 14);
                        push_rsi(ret, &mut gains_slow, &mut losses_slow, 42);
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
            rows[idx].rsi_fast = rsi_from_queues(&gains_fast, &losses_fast);
            rows[idx].rsi_slow = rsi_from_queues(&gains_slow, &losses_slow);
            rows[idx].rsi_diff = rows[idx].rsi_fast - rows[idx].rsi_slow;
            rows[idx].rsi_diff_delta = rows[idx].rsi_diff - prev_rsi_diff;
            prev_rsi_diff = rows[idx].rsi_diff;
            prev_center = Some(center);
        }
        start = end;
    }
}

fn push_rsi(ret_bps: f64, gains: &mut VecDeque<f64>, losses: &mut VecDeque<f64>, window: usize) {
    gains.push_back(ret_bps.max(0.0));
    losses.push_back((-ret_bps).max(0.0));
    while gains.len() > window {
        gains.pop_front();
    }
    while losses.len() > window {
        losses.pop_front();
    }
}

fn rsi_from_queues(gains: &VecDeque<f64>, losses: &VecDeque<f64>) -> f64 {
    if gains.is_empty() || losses.is_empty() {
        return 50.0;
    }
    let avg_gain = gains.iter().sum::<f64>() / gains.len() as f64;
    let avg_loss = losses.iter().sum::<f64>() / losses.len() as f64;
    if avg_loss <= 1e-12 {
        if avg_gain <= 1e-12 { 50.0 } else { 100.0 }
    } else {
        100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    }
}

fn rows_by_symbol(rows: &[PanelRow]) -> BTreeMap<String, Vec<&PanelRow>> {
    let mut by_symbol = BTreeMap::<String, Vec<&PanelRow>>::new();
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

fn build_level_events(
    config: &V15Config,
    folds: &[FoldSpec],
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
    levels: &mut Vec<LevelRow>,
    events: &mut Vec<EventRow>,
) {
    for fold in folds {
        let Some(rows) = by_symbol.get(&fold.symbol) else {
            continue;
        };
        let valid_positions = rows
            .iter()
            .enumerate()
            .filter(|(_, row)| {
                row.factor_eligible
                    && row.local_timestamp >= fold.valid_start
                    && row.local_timestamp <= fold.valid_end
            })
            .map(|(pos, _)| pos)
            .collect::<Vec<_>>();
        let mut counters = BTreeMap::<String, usize>::new();
        let mut last_pos_by_variant = BTreeMap::<String, usize>::new();
        for pos in valid_positions {
            if pos < MIN_SWING_EVENTS {
                continue;
            }
            let Some(swing) = trailing_swing(rows, pos, SWING_LOOKBACK_EVENTS) else {
                continue;
            };
            if swing.range() <= 0.0 || rows[pos].mid_price <= 0.0 {
                continue;
            }
            let candidates = build_base_candidates(fold, rows, pos, swing);
            for candidate in candidates {
                let count = counters.entry(candidate.variant.clone()).or_default();
                if *count >= MAX_EVENTS_PER_VARIANT_FOLD_SYMBOL {
                    continue;
                }
                if let Some(last_pos) = last_pos_by_variant.get(&candidate.variant) {
                    if pos.saturating_sub(*last_pos) < EVENT_GAP {
                        continue;
                    }
                }
                *count += 1;
                last_pos_by_variant.insert(candidate.variant.clone(), pos);
                levels.push(candidate.level.clone());
                events.push(candidate.event.clone());
                append_controls(config, fold, by_symbol, rows, &candidate.event, events);
            }
        }
    }
}

#[derive(Debug, Clone)]
struct Candidate {
    variant: String,
    level: LevelRow,
    event: EventRow,
}

fn build_base_candidates(
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    swing: Swing,
) -> Vec<Candidate> {
    let mut out = Vec::new();
    for ratio in FIB_RATIOS {
        if let Some(candidate) = build_retracement_candidate(fold, rows, pos, swing, ratio) {
            let near_level = candidate.event.level_dist_bps.abs() <= candidate.event.touch_band_bps;
            if near_level {
                out.push(candidate.clone());
                if let Some(rsi) = build_rsi_divergence_candidate(fold, rows, pos, swing, ratio) {
                    out.push(rsi);
                }
                if let Some(absorption) = build_absorption_candidate(fold, rows, pos, swing, ratio)
                {
                    out.push(absorption);
                }
            }
        }
    }
    for ratio in EXTENSION_RATIOS {
        if let Some(candidate) = build_extension_candidate(fold, rows, pos, swing, ratio) {
            if candidate.event.level_dist_bps.abs() <= candidate.event.touch_band_bps {
                out.push(candidate);
            }
        }
    }
    out
}

fn build_retracement_candidate(
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    swing: Swing,
    ratio: f64,
) -> Option<Candidate> {
    let side_sign = swing.side_sign();
    let level_price = if side_sign > 0 {
        swing.high_price - ratio * swing.range()
    } else {
        swing.low_price + ratio * swing.range()
    };
    let row = rows[pos];
    if row.level_dist_bps(level_price).abs() > row.touch_band_bps() {
        return None;
    }
    Some(build_candidate(
        fold,
        rows,
        pos,
        swing,
        side_sign,
        "bonk_v15_fib_retracement_reaction",
        "fib_retracement_reaction",
        "fib_retracement",
        level_price,
        Some(ratio),
        None,
        format!("fib_{ratio:.3}_touch_within_band"),
    ))
}

fn build_extension_candidate(
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    swing: Swing,
    ratio: f64,
) -> Option<Candidate> {
    let side_sign = swing.side_sign();
    let level_price = if side_sign > 0 {
        swing.high_price + (ratio - 1.0) * swing.range()
    } else {
        swing.low_price - (ratio - 1.0) * swing.range()
    };
    let row = rows[pos];
    if row.level_dist_bps(level_price).abs() > row.touch_band_bps() {
        return None;
    }
    Some(build_candidate(
        fold,
        rows,
        pos,
        swing,
        side_sign,
        "bonk_v15_fib_extension_continuation",
        "fib_extension_continuation",
        "fib_extension",
        level_price,
        None,
        Some(ratio),
        format!("extension_{ratio:.3}_touch_within_band"),
    ))
}

fn build_rsi_divergence_candidate(
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    swing: Swing,
    ratio: f64,
) -> Option<Candidate> {
    let side_sign = swing.side_sign();
    let level_price = if side_sign > 0 {
        swing.high_price - ratio * swing.range()
    } else {
        swing.low_price + ratio * swing.range()
    };
    let row = rows[pos];
    let start = pos.saturating_sub(RSI_LOOKBACK_EXTREME_EVENTS);
    let previous = rows[start];
    let price_momentum_bps = if previous.mid_price > 0.0 {
        (row.mid_price - previous.mid_price) / previous.mid_price * 10_000.0
    } else {
        0.0
    };
    let divergence_score =
        side_sign as f64 * row.rsi_diff_delta - 0.015 * side_sign as f64 * price_momentum_bps;
    if row.level_dist_bps(level_price).abs() <= row.touch_band_bps()
        && side_sign as f64 * price_momentum_bps < -0.25
        && divergence_score > 0.05
    {
        Some(build_candidate(
            fold,
            rows,
            pos,
            swing,
            side_sign,
            "bonk_v15_rsi_diff_divergence_dynamic_level",
            "rsi_diff_divergence_dynamic_level",
            "fib_rsi_divergence",
            level_price,
            Some(ratio),
            None,
            format!("rsi_diff_divergence_score_{divergence_score:.3}"),
        ))
    } else {
        None
    }
}

fn build_absorption_candidate(
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    swing: Swing,
    ratio: f64,
) -> Option<Candidate> {
    let side_sign = swing.side_sign();
    let level_price = if side_sign > 0 {
        swing.high_price - ratio * swing.range()
    } else {
        swing.low_price + ratio * swing.range()
    };
    let row = rows[pos];
    if row.level_dist_bps(level_price).abs() <= row.touch_band_bps()
        && row.taker_pressure_against_level(side_sign) > 0.0
        && row.absorption_score(side_sign) > 0.05
    {
        Some(build_candidate(
            fold,
            rows,
            pos,
            swing,
            side_sign,
            "bonk_v15_orderbook_absorption_rejection",
            "orderbook_absorption_rejection",
            "fib_orderbook_absorption",
            level_price,
            Some(ratio),
            None,
            format!(
                "absorption_score_{:.3}_near_fib_{ratio:.3}",
                row.absorption_score(side_sign)
            ),
        ))
    } else {
        None
    }
}

#[allow(clippy::too_many_arguments)]
fn build_candidate(
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    swing: Swing,
    side_sign: i8,
    draft_id: &str,
    variant: &str,
    level_type: &str,
    level_price: f64,
    fib_ratio: Option<f64>,
    extension_ratio: Option<f64>,
    trigger_reason: String,
) -> Candidate {
    let row = rows[pos];
    let level_id = format!(
        "{}|{}|{}|{}|{}|{}",
        fold.fold, row.symbol, row.event_index, variant, level_type, side_sign
    );
    let path_barrier_bps = row.sigma_bps.max(1.5).max(2.0 * row.spread_bps);
    let outcome = path_outcome(rows, pos, side_sign, PATH_HORIZON_EVENTS, path_barrier_bps);
    let side = side_name(side_sign).to_string();
    let swing_range_bps = if row.mid_price > 0.0 {
        swing.range() / row.mid_price * 10_000.0
    } else {
        0.0
    };
    let level = LevelRow {
        run_tag: row.run_tag.clone(),
        draft_id: draft_id.to_string(),
        variant: variant.to_string(),
        fold: fold.fold.clone(),
        phase: "valid".to_string(),
        date: row.date.clone(),
        symbol: row.symbol.clone(),
        event_ts: row.local_timestamp,
        event_index: row.event_index,
        source_pos: pos,
        side: side.clone(),
        side_sign,
        mid_price: row.mid_price,
        spread_bps: row.spread_bps,
        sigma_bps: row.sigma_bps,
        best_bid_price: row.best_bid_price,
        best_ask_price: row.best_ask_price,
        level_id,
        level_type: level_type.to_string(),
        level_price,
        level_dist_bps: row.level_dist_bps(level_price),
        touch_band_bps: row.touch_band_bps(),
        swing_lookback_events: swing.lookback_events,
        swing_start_event_index: rows[swing.start_pos()].event_index,
        swing_end_event_index: rows[swing.end_pos()].event_index,
        swing_low: swing.low_price,
        swing_high: swing.high_price,
        swing_range_bps,
        fib_ratio,
        extension_ratio,
        rsi_fast: row.rsi_fast,
        rsi_slow: row.rsi_slow,
        rsi_diff: row.rsi_diff,
        rsi_diff_delta: row.rsi_diff_delta,
        book_confirm_score: row.book_confirm_score(side_sign),
        absorption_score: row.absorption_score(side_sign),
        trigger_reason: trigger_reason.clone(),
        guardrail: GUARDRAIL.to_string(),
    };
    let mut event = event_from_outcome(
        row,
        draft_id,
        variant,
        "base",
        &format!("{}|{}|{}", fold.fold, row.symbol, row.event_index),
        &fold.fold,
        side_sign,
        level_price,
        level_type,
        row.level_dist_bps(level_price),
        row.touch_band_bps(),
        &trigger_reason,
        path_barrier_bps,
        outcome,
    );
    event.source_pos = pos;
    Candidate {
        variant: variant.to_string(),
        level,
        event,
    }
}

#[allow(clippy::too_many_arguments)]
fn event_from_outcome(
    row: &PanelRow,
    draft_id: &str,
    variant: &str,
    control_type: &str,
    control_group_id: &str,
    fold: &str,
    side_sign: i8,
    level_price: f64,
    level_type: &str,
    level_dist_bps: f64,
    touch_band_bps: f64,
    trigger_reason: &str,
    path_barrier_bps: f64,
    outcome: PathOutcome,
) -> EventRow {
    EventRow {
        run_tag: row.run_tag.clone(),
        draft_id: draft_id.to_string(),
        variant: variant.to_string(),
        negative_control_type: control_type.to_string(),
        control_group_id: control_group_id.to_string(),
        fold: fold.to_string(),
        phase: "valid".to_string(),
        date: row.date.clone(),
        symbol: row.symbol.clone(),
        event_ts: row.local_timestamp,
        event_index: row.event_index,
        source_pos: 0,
        side: side_name(side_sign).to_string(),
        side_sign,
        mid_price: row.mid_price,
        spread_bps: row.spread_bps,
        sigma_bps: row.sigma_bps,
        best_bid_price: row.best_bid_price,
        best_ask_price: row.best_ask_price,
        level_price,
        level_type: level_type.to_string(),
        level_dist_bps,
        touch_band_bps,
        trigger_reason: trigger_reason.to_string(),
        path_horizon_events: PATH_HORIZON_EVENTS,
        path_barrier_bps,
        path_label: outcome.label,
        favorable_first: outcome.favorable_first,
        adverse_first: outcome.adverse_first,
        timeout: outcome.timeout,
        reaction_latency_events: outcome.reaction_latency_events,
        mfe_bps: outcome.mfe_bps,
        mae_bps: outcome.mae_bps,
        side_return_bps: outcome.side_return_bps,
        rsi_fast: row.rsi_fast,
        rsi_slow: row.rsi_slow,
        rsi_diff: row.rsi_diff,
        rsi_diff_delta: row.rsi_diff_delta,
        queue_imbalance_25: row.queue_imbalance_25,
        mlofi_roll10_l10: row.mlofi_roll10_l10,
        trade_flow_imbalance: row.trade_flow_imbalance,
        book_confirm_score: row.book_confirm_score(side_sign),
        absorption_score: row.absorption_score(side_sign),
        liquidity_shock_score: row.liquidity_shock_score,
        factor_eligible: row.factor_eligible,
        execute_cancel_confidence: row.execute_cancel_confidence.clone(),
        snapshot_batch: row.is_snapshot_batch,
        guardrail: GUARDRAIL.to_string(),
    }
}

fn append_controls(
    config: &V15Config,
    fold: &FoldSpec,
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
    base_rows: &[&PanelRow],
    base: &EventRow,
    events: &mut Vec<EventRow>,
) {
    let Some(pos) = find_event_pos(base_rows, base.event_ts, base.event_index) else {
        return;
    };
    let row = base_rows[pos];
    let group_id = base.control_group_id.clone();

    let side_flip = -base.side_sign;
    events.push(control_event(
        fold,
        base_rows,
        pos,
        base,
        "side_flip",
        side_flip,
        row.level_dist_bps(base.level_price),
        &group_id,
    ));

    if let Some(shift_pos) = nearest_pos_by_timestamp(
        base_rows,
        row.local_timestamp.saturating_add(SHIFT_60S_US),
        fold.valid_start,
        fold.valid_end,
    ) {
        events.push(control_event(
            fold,
            base_rows,
            shift_pos,
            base,
            "timestamp_shift_plus_60s",
            base.side_sign,
            base_rows[shift_pos].level_dist_bps(base.level_price),
            &group_id,
        ));
    }
    if row.local_timestamp > SHIFT_60S_US {
        if let Some(shift_pos) = nearest_pos_by_timestamp(
            base_rows,
            row.local_timestamp - SHIFT_60S_US,
            fold.valid_start,
            fold.valid_end,
        ) {
            events.push(control_event(
                fold,
                base_rows,
                shift_pos,
                base,
                "timestamp_shift_minus_60s",
                base.side_sign,
                base_rows[shift_pos].level_dist_bps(base.level_price),
                &group_id,
            ));
        }
    }

    let random_pos = random_same_symbol_pos(base_rows, pos, fold.valid_start, fold.valid_end);
    if let Some(random_pos) = random_pos {
        events.push(control_event(
            fold,
            base_rows,
            random_pos,
            base,
            "random_time_same_symbol",
            base.side_sign,
            base_rows[random_pos].level_dist_bps(base.level_price),
            &group_id,
        ));
    }

    let random_ratio = pseudo_unit(row.local_timestamp ^ row.event_index as u64);
    let random_level = if row.mid_price > 0.0 {
        row.mid_price * (1.0 + (random_ratio - 0.5) * 0.002)
    } else {
        base.level_price
    };
    let mut random_level_event = control_event(
        fold,
        base_rows,
        pos,
        base,
        "random_level_same_anchor",
        base.side_sign,
        row.level_dist_bps(random_level),
        &group_id,
    );
    random_level_event.level_price = random_level;
    random_level_event.level_type = "random_level_same_anchor".to_string();
    events.push(random_level_event);

    let mut ratio_shuffle = control_event(
        fold,
        base_rows,
        pos,
        base,
        "level_ratio_shuffle",
        base.side_sign,
        -base.level_dist_bps,
        &group_id,
    );
    ratio_shuffle.level_price = row.mid_price * (1.0 - base.level_dist_bps / 10_000.0);
    ratio_shuffle.level_type = "level_ratio_shuffle".to_string();
    events.push(ratio_shuffle);

    for (other_symbol, other_rows) in by_symbol {
        if other_symbol == &fold.symbol {
            continue;
        }
        if let Some(other_pos) = nearest_pos_by_timestamp(
            other_rows,
            row.local_timestamp,
            fold.valid_start,
            fold.valid_end,
        ) {
            events.push(control_event(
                fold,
                other_rows,
                other_pos,
                base,
                "wrong_symbol_same_time",
                base.side_sign,
                other_rows[other_pos].level_dist_bps(base.level_price),
                &group_id,
            ));
            break;
        }
    }

    let _ = config.fee_bps;
}

fn control_event(
    fold: &FoldSpec,
    rows: &[&PanelRow],
    pos: usize,
    base: &EventRow,
    control_type: &str,
    side_sign: i8,
    level_dist_bps: f64,
    group_id: &str,
) -> EventRow {
    let row = rows[pos];
    let outcome = path_outcome(
        rows,
        pos,
        side_sign,
        PATH_HORIZON_EVENTS,
        base.path_barrier_bps,
    );
    let mut event = event_from_outcome(
        row,
        &base.draft_id,
        &base.variant,
        control_type,
        group_id,
        &fold.fold,
        side_sign,
        base.level_price,
        &base.level_type,
        level_dist_bps,
        base.touch_band_bps,
        &format!("control:{control_type};base={}", base.trigger_reason),
        base.path_barrier_bps,
        outcome,
    );
    event.source_pos = pos;
    event
}

fn trailing_swing(rows: &[&PanelRow], pos: usize, lookback: usize) -> Option<Swing> {
    let start = pos.saturating_sub(lookback);
    if pos.saturating_sub(start) < MIN_SWING_EVENTS {
        return None;
    }
    let mut low_price = f64::INFINITY;
    let mut high_price = f64::NEG_INFINITY;
    let mut low_pos = start;
    let mut high_pos = start;
    for (idx, row) in rows.iter().enumerate().take(pos).skip(start) {
        if row.mid_price < low_price {
            low_price = row.mid_price;
            low_pos = idx;
        }
        if row.mid_price > high_price {
            high_price = row.mid_price;
            high_pos = idx;
        }
    }
    if low_price.is_finite() && high_price.is_finite() && high_price > low_price {
        Some(Swing {
            lookback_events: pos - start,
            low_price,
            high_price,
            low_pos,
            high_pos,
        })
    } else {
        None
    }
}

fn path_outcome(
    rows: &[&PanelRow],
    pos: usize,
    side_sign: i8,
    horizon_events: usize,
    barrier_bps: f64,
) -> PathOutcome {
    let entry = rows[pos].mid_price;
    let side = side_sign as f64;
    let end = (pos + horizon_events).min(rows.len().saturating_sub(1));
    let mut mfe = 0.0f64;
    let mut mae = 0.0f64;
    let mut first = None::<(bool, usize)>;
    for (offset, row) in rows.iter().enumerate().take(end + 1).skip(pos + 1) {
        let ret = side * (row.mid_price - entry) / entry * 10_000.0;
        mfe = mfe.max(ret);
        mae = mae.min(ret);
        if first.is_none() {
            if ret <= -barrier_bps {
                first = Some((false, offset - pos));
            } else if ret >= barrier_bps {
                first = Some((true, offset - pos));
            }
        }
    }
    let end_price = rows[end].mid_price;
    let side_return = side * (end_price - entry) / entry * 10_000.0;
    match first {
        Some((true, latency)) => PathOutcome {
            label: "favorable_first".to_string(),
            favorable_first: true,
            adverse_first: false,
            timeout: false,
            reaction_latency_events: Some(latency),
            mfe_bps: mfe,
            mae_bps: mae,
            side_return_bps: side_return,
        },
        Some((false, latency)) => PathOutcome {
            label: "adverse_first".to_string(),
            favorable_first: false,
            adverse_first: true,
            timeout: false,
            reaction_latency_events: Some(latency),
            mfe_bps: mfe,
            mae_bps: mae,
            side_return_bps: side_return,
        },
        None => PathOutcome {
            label: "timeout".to_string(),
            favorable_first: false,
            adverse_first: false,
            timeout: true,
            reaction_latency_events: None,
            mfe_bps: mfe,
            mae_bps: mae,
            side_return_bps: side_return,
        },
    }
}

fn find_event_pos(rows: &[&PanelRow], local_timestamp: u64, event_index: usize) -> Option<usize> {
    rows.binary_search_by(|row| {
        row.local_timestamp
            .cmp(&local_timestamp)
            .then_with(|| row.event_index.cmp(&event_index))
    })
    .ok()
}

fn nearest_pos_by_timestamp(
    rows: &[&PanelRow],
    target_ts: u64,
    valid_start: u64,
    valid_end: u64,
) -> Option<usize> {
    let idx = rows.partition_point(|row| row.local_timestamp < target_ts);
    let mut best = None::<(usize, u64)>;
    for candidate in [
        idx.saturating_sub(1),
        idx,
        (idx + 1).min(rows.len().saturating_sub(1)),
    ] {
        let row = rows.get(candidate)?;
        if row.local_timestamp < valid_start || row.local_timestamp > valid_end {
            continue;
        }
        let dist = row.local_timestamp.abs_diff(target_ts);
        if best.is_none_or(|(_, best_dist)| dist < best_dist) {
            best = Some((candidate, dist));
        }
    }
    best.map(|(idx, _)| idx)
}

fn random_same_symbol_pos(
    rows: &[&PanelRow],
    pos: usize,
    valid_start: u64,
    valid_end: u64,
) -> Option<usize> {
    if rows.is_empty() {
        return None;
    }
    for step in [997usize, 1597, 2584, 4181] {
        let candidate = (pos + step) % rows.len();
        let row = rows[candidate];
        if row.local_timestamp >= valid_start && row.local_timestamp <= valid_end {
            return Some(candidate);
        }
    }
    None
}

fn build_path_profiles(events: &[EventRow]) -> Vec<PathProfileRow> {
    let mut grouped = BTreeMap::<(String, String, String, String, usize), Vec<&EventRow>>::new();
    for event in events {
        grouped
            .entry((
                event.draft_id.clone(),
                event.variant.clone(),
                event.negative_control_type.clone(),
                event.side.clone(),
                event.path_horizon_events,
            ))
            .or_default()
            .push(event);
    }
    grouped
        .into_iter()
        .map(
            |((draft_id, variant, negative_control_type, side, horizon), rows)| {
                let events = rows.len();
                PathProfileRow {
                    run_tag: rows[0].run_tag.clone(),
                    draft_id,
                    variant,
                    negative_control_type,
                    side,
                    path_horizon_events: horizon,
                    events,
                    favorable_first_rate: rate(
                        rows.iter().filter(|row| row.favorable_first).count(),
                        events,
                    ),
                    adverse_first_rate: rate(
                        rows.iter().filter(|row| row.adverse_first).count(),
                        events,
                    ),
                    timeout_rate: rate(rows.iter().filter(|row| row.timeout).count(), events),
                    mean_side_return_bps: mean_iter(rows.iter().map(|row| row.side_return_bps)),
                    median_side_return_bps: median(
                        rows.iter().map(|row| row.side_return_bps).collect(),
                    ),
                    mean_mfe_bps: mean_iter(rows.iter().map(|row| row.mfe_bps)),
                    mean_mae_bps: mean_iter(rows.iter().map(|row| row.mae_bps)),
                    mean_book_confirm_score: mean_iter(
                        rows.iter().map(|row| row.book_confirm_score),
                    ),
                    mean_absorption_score: mean_iter(rows.iter().map(|row| row.absorption_score)),
                    max_date_share: max_share(rows.iter().map(|row| row.date.as_str()), events),
                    max_symbol_share: max_share(rows.iter().map(|row| row.symbol.as_str()), events),
                    guardrail: GUARDRAIL.to_string(),
                }
            },
        )
        .collect()
}

fn build_summary_rows(config: &V15Config, events: &[EventRow]) -> Vec<SummaryRow> {
    let mut grouped = BTreeMap::<(String, String), Vec<&EventRow>>::new();
    for event in events {
        grouped
            .entry((event.variant.clone(), event.negative_control_type.clone()))
            .or_default()
            .push(event);
    }
    grouped
        .into_iter()
        .map(|((variant, control), rows)| {
            let events = rows.len();
            let favorable = rows.iter().filter(|row| row.favorable_first).count();
            let adverse = rows.iter().filter(|row| row.adverse_first).count();
            let mean_return = mean_iter(rows.iter().map(|row| row.side_return_bps));
            let max_date_share = max_share(rows.iter().map(|row| row.date.as_str()), events);
            let max_symbol_share = max_share(rows.iter().map(|row| row.symbol.as_str()), events);
            SummaryRow {
                run_tag: config.run_tag.clone(),
                variant,
                negative_control_type: control,
                events,
                favorable_first_rate: rate(favorable, events),
                adverse_first_rate: rate(adverse, events),
                favorable_minus_adverse_rate: rate(favorable, events) - rate(adverse, events),
                mean_side_return_bps: mean_return,
                median_side_return_bps: median(
                    rows.iter().map(|row| row.side_return_bps).collect(),
                ),
                mean_mfe_bps: mean_iter(rows.iter().map(|row| row.mfe_bps)),
                mean_mae_bps: mean_iter(rows.iter().map(|row| row.mae_bps)),
                gross_after_fee_probe_bps: mean_return - config.fee_bps,
                max_date_share,
                max_symbol_share,
                pass_sample_500: events >= 500,
                pass_date_concentration_035: max_date_share <= 0.35,
                pass_symbol_concentration_070: max_symbol_share <= 0.70,
                pass_positive_path_return: mean_return > 0.0,
                primary_candidate: false,
                guardrail: GUARDRAIL.to_string(),
            }
        })
        .collect()
}

fn mark_primary_candidate(rows: &mut [SummaryRow]) {
    let mut best_idx = None::<usize>;
    let mut best_score = f64::NEG_INFINITY;
    for (idx, row) in rows.iter().enumerate() {
        if row.negative_control_type != "base" || row.events < 50 {
            continue;
        }
        let score = row.mean_side_return_bps + 5.0 * row.favorable_minus_adverse_rate
            - 2.0 * row.max_date_share;
        if score > best_score {
            best_score = score;
            best_idx = Some(idx);
        }
    }
    if let Some(idx) = best_idx {
        rows[idx].primary_candidate = true;
    }
}

fn build_negative_control_rows(summaries: &[SummaryRow]) -> Vec<NegativeControlRow> {
    let mut by_variant_control = BTreeMap::<(String, String), &SummaryRow>::new();
    for row in summaries {
        by_variant_control.insert(
            (row.variant.clone(), row.negative_control_type.clone()),
            row,
        );
    }
    let mut out = Vec::new();
    for row in summaries {
        if row.negative_control_type == "base" {
            continue;
        }
        let Some(base) = by_variant_control.get(&(row.variant.clone(), "base".to_string())) else {
            continue;
        };
        let control_abs_ge_base_abs =
            row.mean_side_return_bps.abs() >= base.mean_side_return_bps.abs();
        out.push(NegativeControlRow {
            run_tag: row.run_tag.clone(),
            variant: row.variant.clone(),
            control_type: row.negative_control_type.clone(),
            base_events: base.events,
            control_events: row.events,
            base_mean_side_return_bps: base.mean_side_return_bps,
            control_mean_side_return_bps: row.mean_side_return_bps,
            base_favorable_minus_adverse_rate: base.favorable_minus_adverse_rate,
            control_favorable_minus_adverse_rate: row.favorable_minus_adverse_rate,
            control_abs_ge_base_abs,
            interpretation: if control_abs_ge_base_abs {
                "control_abs_ge_base_abs; no path separation claim".to_string()
            } else {
                "control_weaker_than_base".to_string()
            },
            guardrail: GUARDRAIL.to_string(),
        });
    }
    out
}

fn build_diagnostics(
    audit: &InputAudit,
    folds: &[FoldSpec],
    levels: &[LevelRow],
    events: &[EventRow],
    summaries: &[SummaryRow],
) -> Vec<DiagnosticRow> {
    let mut out = Vec::new();
    let mut push = |metric: &str, value: String| {
        out.push(DiagnosticRow {
            run_tag: levels
                .first()
                .map(|row| row.run_tag.clone())
                .or_else(|| summaries.first().map(|row| row.run_tag.clone()))
                .unwrap_or_else(|| DEFAULT_V10_RUN_TAG.to_string()),
            metric: metric.to_string(),
            value,
            guardrail: GUARDRAIL.to_string(),
        });
    };
    push("panel_files", audit.panel_files.to_string());
    push("panel_rows", audit.panel_rows.to_string());
    push("usable_rows", audit.usable_rows.to_string());
    push("fold_rows", folds.len().to_string());
    push("level_rows", levels.len().to_string());
    push("event_rows_including_controls", events.len().to_string());
    push(
        "base_event_rows",
        events
            .iter()
            .filter(|row| row.negative_control_type == "base")
            .count()
            .to_string(),
    );
    push(
        "control_event_rows",
        events
            .iter()
            .filter(|row| row.negative_control_type != "base")
            .count()
            .to_string(),
    );
    push(
        "blockers",
        if audit.blockers.is_empty() {
            "none".to_string()
        } else {
            audit.blockers.join(";")
        },
    );
    push(
        "stance",
        "factor_path_diagnostics_only_no_trades_csv_no_execution_recommendation".to_string(),
    );
    out
}

#[allow(clippy::too_many_arguments)]
fn build_manifest(
    paths: &Paths,
    config: &V15Config,
    levels: &[LevelRow],
    events: &[EventRow],
    profiles: &[PathProfileRow],
    summaries: &[SummaryRow],
    controls: &[NegativeControlRow],
    diagnostics: &[DiagnosticRow],
) -> Vec<ManifestRow> {
    let artifacts = [
        ("levels", &paths.levels_csv, levels.len()),
        ("events", &paths.events_csv, events.len()),
        ("path_profiles", &paths.path_profiles_csv, profiles.len()),
        ("summary", &paths.summary_csv, summaries.len()),
        (
            "negative_controls",
            &paths.negative_controls_csv,
            controls.len(),
        ),
        ("diagnostics", &paths.diagnostics_csv, diagnostics.len()),
        ("path_mix_svg", &paths.path_mix_svg, 1),
        ("returns_svg", &paths.return_svg, 1),
        ("controls_svg", &paths.control_svg, 1),
        ("sample_overlay_svg", &paths.sample_overlay_svg, 1),
        ("report_md", &paths.report_md, 1),
    ];
    artifacts
        .into_iter()
        .map(|(artifact, path, rows)| ManifestRow {
            run_tag: config.run_tag.clone(),
            artifact: artifact.to_string(),
            path: path_string(path),
            rows,
            guardrail: GUARDRAIL.to_string(),
        })
        .collect()
}

fn primary_status(
    audit: &InputAudit,
    summaries: &[SummaryRow],
    controls: &[NegativeControlRow],
) -> String {
    if !audit.blockers.is_empty() {
        return "blocker_missing_inputs".to_string();
    }
    let Some(base) = summaries
        .iter()
        .filter(|row| row.negative_control_type == "base")
        .max_by(|a, b| a.mean_side_return_bps.total_cmp(&b.mean_side_return_bps))
    else {
        return "no_base_level_events".to_string();
    };
    if base.events < 500 {
        return "exploratory_only_events_lt_500".to_string();
    }
    if controls
        .iter()
        .filter(|row| row.variant == base.variant)
        .filter(|row| row.control_abs_ge_base_abs)
        .count()
        > 0
    {
        return "path_structure_not_control_separated".to_string();
    }
    if base.mean_side_return_bps <= 0.0 {
        return "base_path_return_not_positive".to_string();
    }
    "path_diagnostic_candidate_needs_oos".to_string()
}

fn write_path_mix_svg(path: &Path, summaries: &[SummaryRow]) -> Result<()> {
    let base_rows = summaries
        .iter()
        .filter(|row| row.negative_control_type == "base")
        .collect::<Vec<_>>();
    let width = 980.0;
    let height = 420.0;
    let mut svg = svg_header(width, height, "V15 Path Mix by Variant");
    let chart_x = 90.0;
    let chart_y = 70.0;
    let chart_w = 820.0;
    let chart_h = 260.0;
    svg.push_str(&axis(chart_x, chart_y, chart_w, chart_h, "rate"));
    let bar_group_w = if base_rows.is_empty() {
        chart_w
    } else {
        chart_w / base_rows.len() as f64
    };
    for (idx, row) in base_rows.iter().enumerate() {
        let x0 = chart_x + idx as f64 * bar_group_w + 16.0;
        let bar_w = (bar_group_w - 34.0).max(20.0) / 3.0;
        let vals = [
            (row.favorable_first_rate, "#287C5E", "fav"),
            (row.adverse_first_rate, "#B84A4A", "adv"),
            (
                (1.0 - row.favorable_first_rate - row.adverse_first_rate).max(0.0),
                "#9AA4B2",
                "timeout",
            ),
        ];
        for (j, (value, color, _)) in vals.iter().enumerate() {
            let h = chart_h * value.clamp(0.0, 1.0);
            let x = x0 + j as f64 * bar_w;
            let y = chart_y + chart_h - h;
            svg.push_str(&format!(
                "<rect x=\"{x:.1}\" y=\"{y:.1}\" width=\"{:.1}\" height=\"{h:.1}\" fill=\"{color}\" rx=\"3\"/>\n",
                bar_w * 0.82
            ));
        }
        svg.push_str(&rotated_label(
            x0 + bar_group_w * 0.26,
            chart_y + chart_h + 72.0,
            &row.variant,
        ));
    }
    svg.push_str(&legend(
        650.0,
        24.0,
        &[
            ("fav", "#287C5E"),
            ("adv", "#B84A4A"),
            ("timeout", "#9AA4B2"),
        ],
    ));
    svg.push_str("</svg>\n");
    write_text_atomic(path, &svg)
}

fn write_return_svg(path: &Path, summaries: &[SummaryRow]) -> Result<()> {
    let rows = summaries
        .iter()
        .filter(|row| row.negative_control_type == "base")
        .collect::<Vec<_>>();
    let width = 980.0;
    let height = 420.0;
    let mut svg = svg_header(width, height, "V15 Base Mean Side Return by Variant");
    let chart_x = 90.0;
    let chart_y = 70.0;
    let chart_w = 820.0;
    let chart_h = 250.0;
    let max_abs = rows
        .iter()
        .map(|row| row.mean_side_return_bps.abs())
        .fold(1.0, f64::max);
    let mid_y = chart_y + chart_h / 2.0;
    svg.push_str(&axis(chart_x, chart_y, chart_w, chart_h, "bps"));
    svg.push_str(&format!(
        "<line x1=\"{chart_x:.1}\" y1=\"{mid_y:.1}\" x2=\"{:.1}\" y2=\"{mid_y:.1}\" stroke=\"#1F2937\" stroke-width=\"1\"/>\n",
        chart_x + chart_w
    ));
    let group_w = if rows.is_empty() {
        chart_w
    } else {
        chart_w / rows.len() as f64
    };
    for (idx, row) in rows.iter().enumerate() {
        let x = chart_x + idx as f64 * group_w + group_w * 0.25;
        let h = (row.mean_side_return_bps.abs() / max_abs) * chart_h * 0.42;
        let y = if row.mean_side_return_bps >= 0.0 {
            mid_y - h
        } else {
            mid_y
        };
        let color = if row.mean_side_return_bps >= 0.0 {
            "#287C5E"
        } else {
            "#B84A4A"
        };
        svg.push_str(&format!(
            "<rect x=\"{x:.1}\" y=\"{y:.1}\" width=\"{:.1}\" height=\"{h:.1}\" fill=\"{color}\" rx=\"4\"/>\n",
            group_w * 0.45
        ));
        svg.push_str(&format!(
            "<text x=\"{:.1}\" y=\"{:.1}\" text-anchor=\"middle\" font-size=\"11\" fill=\"#111827\">{:.2}</text>\n",
            x + group_w * 0.225,
            if row.mean_side_return_bps >= 0.0 { y - 6.0 } else { y + h + 15.0 },
            row.mean_side_return_bps
        ));
        svg.push_str(&rotated_label(
            x + group_w * 0.225,
            chart_y + chart_h + 78.0,
            &row.variant,
        ));
    }
    svg.push_str("</svg>\n");
    write_text_atomic(path, &svg)
}

fn write_control_svg(path: &Path, controls: &[NegativeControlRow]) -> Result<()> {
    let width = 1100.0;
    let height = 460.0;
    let mut svg = svg_header(width, height, "V15 Base vs Negative Controls");
    let chart_x = 90.0;
    let chart_y = 70.0;
    let chart_w = 930.0;
    let chart_h = 270.0;
    svg.push_str(&axis(chart_x, chart_y, chart_w, chart_h, "abs mean bps"));
    let rows = controls.iter().take(18).collect::<Vec<_>>();
    let max_abs = rows
        .iter()
        .flat_map(|row| {
            [
                row.base_mean_side_return_bps.abs(),
                row.control_mean_side_return_bps.abs(),
            ]
        })
        .fold(1.0, f64::max);
    let group_w = if rows.is_empty() {
        chart_w
    } else {
        chart_w / rows.len() as f64
    };
    for (idx, row) in rows.iter().enumerate() {
        let x0 = chart_x + idx as f64 * group_w + 8.0;
        let base_h = row.base_mean_side_return_bps.abs() / max_abs * chart_h;
        let ctrl_h = row.control_mean_side_return_bps.abs() / max_abs * chart_h;
        svg.push_str(&format!(
            "<rect x=\"{x0:.1}\" y=\"{:.1}\" width=\"{:.1}\" height=\"{base_h:.1}\" fill=\"#2F6FED\" rx=\"3\"/>\n",
            chart_y + chart_h - base_h,
            group_w * 0.28
        ));
        svg.push_str(&format!(
            "<rect x=\"{:.1}\" y=\"{:.1}\" width=\"{:.1}\" height=\"{ctrl_h:.1}\" fill=\"#D97706\" rx=\"3\"/>\n",
            x0 + group_w * 0.32,
            chart_y + chart_h - ctrl_h,
            group_w * 0.28
        ));
        svg.push_str(&rotated_label(
            x0 + group_w * 0.30,
            chart_y + chart_h + 92.0,
            &format!("{}:{}", row.variant.replace('_', " "), row.control_type),
        ));
    }
    svg.push_str(&legend(
        760.0,
        24.0,
        &[("base abs", "#2F6FED"), ("control abs", "#D97706")],
    ));
    svg.push_str("</svg>\n");
    write_text_atomic(path, &svg)
}

fn write_sample_overlay_svg(
    path: &Path,
    events: &[EventRow],
    by_symbol: &BTreeMap<String, Vec<&PanelRow>>,
) -> Result<()> {
    let Some(sample) = events
        .iter()
        .filter(|row| row.negative_control_type == "base")
        .max_by(|a, b| a.side_return_bps.abs().total_cmp(&b.side_return_bps.abs()))
    else {
        return write_text_atomic(path, &empty_svg("No base events available"));
    };
    let Some(rows) = by_symbol.get(&sample.symbol) else {
        return write_text_atomic(path, &empty_svg("Missing sample symbol rows"));
    };
    let Some(pos) = find_event_pos(rows, sample.event_ts, sample.event_index) else {
        return write_text_atomic(path, &empty_svg("Missing sample event"));
    };
    let start = pos.saturating_sub(70);
    let end = (pos + 180).min(rows.len().saturating_sub(1));
    let window = &rows[start..=end];
    let entry = rows[pos].mid_price;
    let mut values = window
        .iter()
        .map(|row| (row.mid_price - entry) / entry * 10_000.0)
        .collect::<Vec<_>>();
    let level_bps = (sample.level_price - entry) / entry * 10_000.0;
    values.push(level_bps);
    let min_v = values
        .iter()
        .copied()
        .fold(f64::INFINITY, f64::min)
        .min(-1.0);
    let max_v = values
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max)
        .max(1.0);
    let width = 980.0;
    let height = 460.0;
    let chart_x = 80.0;
    let chart_y = 70.0;
    let chart_w = 820.0;
    let chart_h = 280.0;
    let mut svg = svg_header(width, height, "V15 Sample Price Path Around Dynamic Level");
    svg.push_str(&axis(chart_x, chart_y, chart_w, chart_h, "relative bps"));
    let to_x = |idx: usize| {
        chart_x + (idx as f64 / (window.len().saturating_sub(1).max(1) as f64)) * chart_w
    };
    let to_y = |v: f64| chart_y + chart_h - ((v - min_v) / (max_v - min_v).max(1e-9)) * chart_h;
    let mut points = String::new();
    for (idx, row) in window.iter().enumerate() {
        let v = (row.mid_price - entry) / entry * 10_000.0;
        points.push_str(&format!("{:.1},{:.1} ", to_x(idx), to_y(v)));
    }
    svg.push_str(&format!(
        "<polyline points=\"{}\" fill=\"none\" stroke=\"#1D4ED8\" stroke-width=\"2\"/>\n",
        points.trim()
    ));
    let level_y = to_y(level_bps);
    svg.push_str(&format!(
        "<line x1=\"{chart_x:.1}\" y1=\"{level_y:.1}\" x2=\"{:.1}\" y2=\"{level_y:.1}\" stroke=\"#D97706\" stroke-width=\"2\" stroke-dasharray=\"7 5\"/>\n",
        chart_x + chart_w
    ));
    let event_x = to_x(pos - start);
    svg.push_str(&format!(
        "<line x1=\"{event_x:.1}\" y1=\"{chart_y:.1}\" x2=\"{event_x:.1}\" y2=\"{:.1}\" stroke=\"#B91C1C\" stroke-width=\"1.5\"/>\n",
        chart_y + chart_h
    ));
    svg.push_str(&format!(
        "<text x=\"80\" y=\"390\" font-size=\"13\" fill=\"#111827\">{} {} {} side={} return={:.2}bps level={:.2}bps</text>\n",
        sample.symbol,
        sample.date,
        sample.variant,
        sample.side,
        sample.side_return_bps,
        level_bps
    ));
    svg.push_str(&legend(
        700.0,
        24.0,
        &[
            ("price", "#1D4ED8"),
            ("level", "#D97706"),
            ("event", "#B91C1C"),
        ],
    ));
    svg.push_str("</svg>\n");
    write_text_atomic(path, &svg)
}

fn svg_header(width: f64, height: f64, title: &str) -> String {
    format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width:.0}\" height=\"{height:.0}\" viewBox=\"0 0 {width:.0} {height:.0}\">\n<rect width=\"100%\" height=\"100%\" fill=\"#F8FAFC\"/>\n<text x=\"32\" y=\"34\" font-size=\"20\" font-family=\"Georgia,serif\" font-weight=\"700\" fill=\"#0F172A\">{}</text>\n",
        escape_xml(title)
    )
}

fn empty_svg(message: &str) -> String {
    let mut svg = svg_header(760.0, 220.0, "V15 Plot");
    svg.push_str(&format!(
        "<text x=\"40\" y=\"110\" font-size=\"16\" fill=\"#475569\">{}</text>\n</svg>\n",
        escape_xml(message)
    ));
    svg
}

fn axis(x: f64, y: f64, w: f64, h: f64, label: &str) -> String {
    format!(
        "<rect x=\"{x:.1}\" y=\"{y:.1}\" width=\"{w:.1}\" height=\"{h:.1}\" fill=\"#FFFFFF\" stroke=\"#CBD5E1\"/>\n<line x1=\"{x:.1}\" y1=\"{:.1}\" x2=\"{:.1}\" y2=\"{:.1}\" stroke=\"#64748B\"/>\n<line x1=\"{x:.1}\" y1=\"{y:.1}\" x2=\"{x:.1}\" y2=\"{:.1}\" stroke=\"#64748B\"/>\n<text x=\"{:.1}\" y=\"{:.1}\" font-size=\"12\" fill=\"#475569\">{}</text>\n",
        y + h,
        x + w,
        y + h,
        y + h,
        x + w - 50.0,
        y - 10.0,
        escape_xml(label)
    )
}

fn rotated_label(x: f64, y: f64, text: &str) -> String {
    let clipped = if text.len() > 28 {
        format!("{}...", &text[..28])
    } else {
        text.to_string()
    };
    format!(
        "<text x=\"{x:.1}\" y=\"{y:.1}\" transform=\"rotate(-35 {x:.1} {y:.1})\" font-size=\"10\" fill=\"#334155\">{}</text>\n",
        escape_xml(&clipped)
    )
}

fn legend(x: f64, y: f64, items: &[(&str, &str)]) -> String {
    let mut out = String::new();
    for (idx, (label, color)) in items.iter().enumerate() {
        let yy = y + idx as f64 * 20.0;
        out.push_str(&format!(
            "<rect x=\"{x:.1}\" y=\"{yy:.1}\" width=\"12\" height=\"12\" fill=\"{color}\" rx=\"2\"/><text x=\"{:.1}\" y=\"{:.1}\" font-size=\"12\" fill=\"#334155\">{}</text>\n",
            x + 18.0,
            yy + 11.0,
            escape_xml(label)
        ));
    }
    out
}

fn write_report(
    paths: &Paths,
    config: &V15Config,
    audit: &InputAudit,
    fold_rows: usize,
    summaries: &[SummaryRow],
    controls: &[NegativeControlRow],
    diagnostics: &[DiagnosticRow],
) -> Result<()> {
    let generated_at = Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true);
    let primary = summaries
        .iter()
        .find(|row| row.primary_candidate)
        .or_else(|| {
            summaries
                .iter()
                .find(|row| row.negative_control_type == "base")
        });
    let mut lines = Vec::new();
    lines.push("# BONK V15 Fibonacci / RSI / Book Level Diagnostics".to_string());
    lines.push(String::new());
    lines.push(format!("- generated_at: `{generated_at}`"));
    lines.push(format!("- run_tag: `{}`", config.run_tag));
    lines.push(format!("- strategy_id: `{STRATEGY_ID}`"));
    lines.push(format!("- guardrail: `{GUARDRAIL}`"));
    lines.push("- stance: research-only factor/path diagnostics; no trades CSV, no execution recommendation, no alpha claim.".to_string());
    lines.push(String::new());
    lines.push("## Inputs".to_string());
    lines.push(String::new());
    lines.push(format!("- V10c panel files: `{}`", audit.panel_files));
    lines.push(format!("- V10c panel rows read: `{}`", audit.panel_rows));
    lines.push(format!("- usable rows: `{}`", audit.usable_rows));
    lines.push(format!("- fold rows: `{fold_rows}`"));
    if !audit.blockers.is_empty() {
        lines.push(format!("- blockers: `{}`", audit.blockers.join(";")));
    }
    lines.push(String::new());
    lines.push("## Primary Read".to_string());
    lines.push(String::new());
    if let Some(row) = primary {
        lines.push(format!(
            "- primary variant: `{}` control=`{}` events=`{}`",
            row.variant, row.negative_control_type, row.events
        ));
        lines.push(format!(
            "- favorable/adverse/timeout proxy: `{:.4}` / `{:.4}` / `{:.4}`",
            row.favorable_first_rate,
            row.adverse_first_rate,
            (1.0 - row.favorable_first_rate - row.adverse_first_rate).max(0.0)
        ));
        lines.push(format!(
            "- mean side return: `{:.4}` bps; median `{:.4}` bps; max_date_share `{:.4}`; max_symbol_share `{:.4}`",
            row.mean_side_return_bps,
            row.median_side_return_bps,
            row.max_date_share,
            row.max_symbol_share
        ));
    } else {
        lines.push("- no base dynamic-level events were generated.".to_string());
    }
    let control_failures = controls
        .iter()
        .filter(|row| row.control_abs_ge_base_abs)
        .count();
    lines.push(format!(
        "- control_abs_ge_base_abs rows: `{}` / `{}`",
        control_failures,
        controls.len()
    ));
    lines.push(String::new());
    lines.push("## Plots".to_string());
    lines.push(String::new());
    lines.push(format!("![Path mix]({})", path_string(&paths.path_mix_svg)));
    lines.push(String::new());
    lines.push(format!("![Returns]({})", path_string(&paths.return_svg)));
    lines.push(String::new());
    lines.push(format!("![Controls]({})", path_string(&paths.control_svg)));
    lines.push(String::new());
    lines.push(format!(
        "![Sample overlay]({})",
        path_string(&paths.sample_overlay_svg)
    ));
    lines.push(String::new());
    lines.push("## Interpretation Boundary".to_string());
    lines.push(String::new());
    lines.push("- Marker here means a dynamic price level. It is not a maker quote, not a fill price, and not a wait-until-filled instruction.".to_string());
    lines.push("- RSI is treated as lagging context and a divergence filter; it is not allowed to create a standalone signal.".to_string());
    lines.push("- Order book fields are confirmation diagnostics around a level touch, not standalone alpha claims.".to_string());
    lines.push("- Negative controls are expected to kill most attractive-looking rows; if controls match base, the report should be read as no path separation.".to_string());
    lines.push(String::new());
    lines.push("## Outputs".to_string());
    lines.push(String::new());
    lines.push(format!("- levels: `{}`", path_string(&paths.levels_csv)));
    lines.push(format!("- events: `{}`", path_string(&paths.events_csv)));
    lines.push(format!(
        "- path_profiles: `{}`",
        path_string(&paths.path_profiles_csv)
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
        "- manifest: `{}`",
        path_string(&paths.manifest_csv)
    ));
    lines.push(String::new());
    lines.push("## Diagnostics".to_string());
    lines.push(String::new());
    for diagnostic in diagnostics {
        lines.push(format!("- `{}`: `{}`", diagnostic.metric, diagnostic.value));
    }
    write_text_atomic(&paths.report_md, &lines.join("\n"))
}

fn side_name(side_sign: i8) -> &'static str {
    if side_sign >= 0 { "long" } else { "short" }
}

fn rate(count: usize, total: usize) -> f64 {
    if total == 0 {
        0.0
    } else {
        count as f64 / total as f64
    }
}

fn mean_iter(iter: impl Iterator<Item = f64>) -> f64 {
    let mut sum = 0.0;
    let mut count = 0usize;
    for value in iter {
        if value.is_finite() {
            sum += value;
            count += 1;
        }
    }
    if count == 0 { 0.0 } else { sum / count as f64 }
}

fn median(mut values: Vec<f64>) -> f64 {
    values.retain(|value| value.is_finite());
    if values.is_empty() {
        return 0.0;
    }
    values.sort_by(f64::total_cmp);
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        (values[mid - 1] + values[mid]) / 2.0
    } else {
        values[mid]
    }
}

fn max_share<'a>(keys: impl Iterator<Item = &'a str>, total: usize) -> f64 {
    if total == 0 {
        return 0.0;
    }
    let mut counts = BTreeMap::<&'a str, usize>::new();
    for key in keys {
        *counts.entry(key).or_default() += 1;
    }
    counts.values().copied().max().unwrap_or(0) as f64 / total as f64
}

fn signed_ratio(a: f64, b: f64) -> f64 {
    let denom = a.abs() + b.abs();
    if denom <= 1e-12 {
        0.0
    } else {
        ((a - b) / denom).clamp(-1.0, 1.0)
    }
}

fn pseudo_unit(seed: u64) -> f64 {
    let mut x = seed.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    x ^= x >> 33;
    x = x.wrapping_mul(0xC2B2_AE3D_27D4_EB4F);
    ((x >> 11) as f64) / ((1u64 << 53) as f64)
}

fn finite(value: f64) -> Option<f64> {
    if value.is_finite() { Some(value) } else { None }
}

fn escape_xml(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
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
        .unwrap_or("bonk_v15_output");
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
    fn rsi_uses_only_past_returns() {
        let mut rows = (0..80)
            .map(|idx| PanelRow {
                run_tag: "test".to_string(),
                date: "2026-05-01".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: idx,
                local_timestamp: idx as u64,
                event_index: idx as usize,
                is_snapshot_batch: false,
                factor_eligible: true,
                execute_cancel_confidence: "synthetic".to_string(),
                crossed_levels_removed: 0,
                mid_price: 100.0 + idx as f64,
                spread_bps: 1.0,
                microprice: None,
                microprice_dev_bps: 0.0,
                best_bid_price: Some(99.0),
                best_ask_price: Some(101.0),
                best_bid_amount: 10.0,
                best_ask_amount: 10.0,
                bid_depth_5: 10.0,
                ask_depth_5: 10.0,
                bid_depth_25: 50.0,
                ask_depth_25: 50.0,
                queue_imbalance_5: 0.0,
                queue_imbalance_25: 0.0,
                mlofi_norm_l5: 0.0,
                mlofi_norm_l10: 0.0,
                mlofi_norm_l25: 0.0,
                mlofi_roll10_l5: 0.0,
                mlofi_roll10_l10: 0.0,
                mlofi_roll10_l25: 0.0,
                trade_buy_amount: 0.0,
                trade_sell_amount: 0.0,
                trade_flow_imbalance: 0.0,
                trade_arrival_alignment: 0.0,
                depletion_bid_amount: 0.0,
                depletion_ask_amount: 0.0,
                replenish_bid_amount: 0.0,
                replenish_ask_amount: 0.0,
                cancel_bid_amount: 0.0,
                cancel_ask_amount: 0.0,
                remove_bid_amount: 0.0,
                remove_ask_amount: 0.0,
                queue_depletion_intensity: 0.0,
                replenish_intensity: 0.0,
                cancellation_withdrawal_intensity: 0.0,
                liquidity_shock_score: 0.0,
                bid_top_levels_json: "[]".to_string(),
                ask_top_levels_json: "[]".to_string(),
                rv30_bps: 0.0,
                sigma_bps: 1.0,
                rsi_fast: 50.0,
                rsi_slow: 50.0,
                rsi_diff: 0.0,
                rsi_diff_delta: 0.0,
                microprice_drift_bps: 0.0,
            })
            .collect::<Vec<_>>();
        enrich_rolling_state(&mut rows);
        let before_future_change = rows[40].rsi_fast;
        rows[70].mid_price = 1.0;
        enrich_rolling_state(&mut rows);
        assert_eq!(before_future_change, rows[40].rsi_fast);
    }

    #[test]
    fn adverse_first_path_is_labelled_before_favorable() {
        let mut owned = Vec::new();
        for (idx, price) in [100.0, 99.0, 102.0].into_iter().enumerate() {
            owned.push(PanelRow {
                run_tag: "test".to_string(),
                date: "2026-05-01".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: idx as u64,
                local_timestamp: idx as u64,
                event_index: idx,
                is_snapshot_batch: false,
                factor_eligible: true,
                execute_cancel_confidence: "synthetic".to_string(),
                crossed_levels_removed: 0,
                mid_price: price,
                spread_bps: 1.0,
                microprice: None,
                microprice_dev_bps: 0.0,
                best_bid_price: None,
                best_ask_price: None,
                best_bid_amount: 0.0,
                best_ask_amount: 0.0,
                bid_depth_5: 0.0,
                ask_depth_5: 0.0,
                bid_depth_25: 0.0,
                ask_depth_25: 0.0,
                queue_imbalance_5: 0.0,
                queue_imbalance_25: 0.0,
                mlofi_norm_l5: 0.0,
                mlofi_norm_l10: 0.0,
                mlofi_norm_l25: 0.0,
                mlofi_roll10_l5: 0.0,
                mlofi_roll10_l10: 0.0,
                mlofi_roll10_l25: 0.0,
                trade_buy_amount: 0.0,
                trade_sell_amount: 0.0,
                trade_flow_imbalance: 0.0,
                trade_arrival_alignment: 0.0,
                depletion_bid_amount: 0.0,
                depletion_ask_amount: 0.0,
                replenish_bid_amount: 0.0,
                replenish_ask_amount: 0.0,
                cancel_bid_amount: 0.0,
                cancel_ask_amount: 0.0,
                remove_bid_amount: 0.0,
                remove_ask_amount: 0.0,
                queue_depletion_intensity: 0.0,
                replenish_intensity: 0.0,
                cancellation_withdrawal_intensity: 0.0,
                liquidity_shock_score: 0.0,
                bid_top_levels_json: "[]".to_string(),
                ask_top_levels_json: "[]".to_string(),
                rv30_bps: 0.0,
                sigma_bps: 1.0,
                rsi_fast: 50.0,
                rsi_slow: 50.0,
                rsi_diff: 0.0,
                rsi_diff_delta: 0.0,
                microprice_drift_bps: 0.0,
            });
        }
        let refs = owned.iter().collect::<Vec<_>>();
        let outcome = path_outcome(&refs, 0, 1, 2, 50.0);
        assert!(outcome.adverse_first);
        assert_eq!(outcome.reaction_latency_events, Some(1));
    }
}

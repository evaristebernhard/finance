use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use anyhow::{Context, Result, bail};
use chrono::{SecondsFormat, Utc};
use finance_chain_core::storage::ensure_parent_dir;
use serde::de::{self, DeserializeOwned, Deserializer};
use serde::{Deserialize, Serialize};

use crate::download::{DEFAULT_BONK_DATA_ROOT, path_string};
use crate::v10::DEFAULT_V10_RUN_TAG;

const GUARDRAIL: &str = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim";
const V10_PURGE_US: u64 = 300_000_000;
const HORIZONS: [u32; 4] = [30, 60, 300, 900];
const ANCHOR_HORIZONS: [u32; 2] = [30, 60];
const COOLDOWNS: [u32; 3] = [60, 180, 300];
const NOTIONAL_BUCKETS: [(&str, f64); 5] = [
    ("notional_q50", 0.50),
    ("notional_q75", 0.75),
    ("notional_q90", 0.90),
    ("notional_q95", 0.95),
    ("notional_q99", 0.99),
];
const SHOCK_BUCKETS: [(&str, f64); 3] = [
    ("shock_q90", 0.90),
    ("shock_q95", 0.95),
    ("shock_q99", 0.99),
];
const REQUIRED_SYMBOLS: [&str; 2] = ["BONK1MUSDC", "BONK1MUSDT"];
const SPARSE_GLOBAL_MIN_EVENTS: usize = 100;
const FILE_REPLACE_RETRIES: usize = 80;
const FILE_REPLACE_RETRY_MS: u64 = 250;
static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct V11Config {
    pub date_dir: PathBuf,
    pub report_md: PathBuf,
    pub run_tag: String,
    pub fee_bps: f64,
}

impl Default for V11Config {
    fn default() -> Self {
        Self {
            date_dir: PathBuf::from("date"),
            report_md: PathBuf::from("docs/markets/bonk/v1-cex-v11-trade-flow-edge-audit.md"),
            run_tag: DEFAULT_V10_RUN_TAG.to_string(),
            fee_bps: 2.0,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct V11Summary {
    pub run_tag: String,
    pub fee_bps: f64,
    pub potential_rows: usize,
    pub quality_rows: usize,
    pub side_alignment_rows: usize,
    pub event_study_rows: usize,
    pub sparse_anchor_rows: usize,
    pub after_cost_rows: usize,
    pub negative_control_rows: usize,
    pub primary_status: String,
    pub side_alignment_csv: String,
    pub event_study_csv: String,
    pub sparse_anchors_csv: String,
    pub after_cost_csv: String,
    pub negative_controls_csv: String,
    pub failure_report_csv: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    potential_csv: PathBuf,
    quality_csv: PathBuf,
    side_alignment_csv: PathBuf,
    event_study_csv: PathBuf,
    sparse_anchors_csv: PathBuf,
    after_cost_csv: PathBuf,
    negative_controls_csv: PathBuf,
    failure_report_csv: PathBuf,
    report_md: PathBuf,
}

impl Paths {
    fn new(config: &V11Config) -> Self {
        Self {
            potential_csv: config
                .date_dir
                .join(format!("bonk_v10_potential_state_{}.csv", config.run_tag)),
            quality_csv: config.date_dir.join(format!(
                "bonk_v10_dynamic_quality_coverage_{}.csv",
                config.run_tag
            )),
            side_alignment_csv: config.date_dir.join(format!(
                "bonk_v11_trade_flow_side_alignment_{}.csv",
                config.run_tag
            )),
            event_study_csv: config.date_dir.join(format!(
                "bonk_v11_trade_flow_event_study_{}.csv",
                config.run_tag
            )),
            sparse_anchors_csv: config.date_dir.join(format!(
                "bonk_v11_trade_flow_sparse_anchors_{}.csv",
                config.run_tag
            )),
            after_cost_csv: config.date_dir.join(format!(
                "bonk_v11_trade_flow_after_cost_{}.csv",
                config.run_tag
            )),
            negative_controls_csv: config.date_dir.join(format!(
                "bonk_v11_trade_flow_negative_controls_{}.csv",
                config.run_tag
            )),
            failure_report_csv: config.date_dir.join(format!(
                "bonk_v11_trade_flow_failure_report_{}.csv",
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
    fn has_cost_inputs(&self) -> bool {
        self.mid_price
            .is_some_and(|value| value.is_finite() && value > 0.0)
            && self
                .spread_bps
                .is_some_and(|value| value.is_finite() && value >= 0.0)
            && self
                .fill_realism_score
                .is_some_and(|value| value.is_finite())
    }

    fn flow_derived(&self) -> Option<FlowDerived> {
        if !self.has_cost_inputs() || self.trade_notional_quote <= 0.0 {
            return None;
        }
        if self.trade_flow_imbalance.unwrap_or(0.0).abs() <= 0.0 {
            return None;
        }
        let delta = self.trade_buy_amount - self.trade_sell_amount;
        let flow_sign = if delta > 0.0 {
            1
        } else if delta < 0.0 {
            -1
        } else {
            return None;
        };
        let signed_flow_shock = flow_sign as f64 * self.trade_notional_quote.ln_1p();
        finite(signed_flow_shock).map(|signed_flow_shock| FlowDerived {
            flow_sign,
            signed_flow_shock,
            abs_flow_shock: signed_flow_shock.abs(),
        })
    }
}

#[derive(Debug, Clone, Copy)]
struct FlowDerived {
    flow_sign: i8,
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

#[derive(Debug, Clone, Deserialize)]
struct QualityCoverageRow {
    run_tag: String,
    date: String,
    symbol: String,
    raw_status: String,
    #[serde(deserialize_with = "de_bool_loose")]
    required_schema_ok: bool,
    replay_status: String,
    #[serde(deserialize_with = "de_bool_loose")]
    multilevel_schema_ok: bool,
    #[serde(deserialize_with = "de_usize_or_zero")]
    actual_part_files: usize,
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
    train_rows: usize,
    valid_rows: usize,
    notional_thresholds: BTreeMap<&'static str, f64>,
    shock_thresholds: BTreeMap<&'static str, f64>,
}

#[derive(Debug, Clone, Serialize)]
struct SideAlignmentRow {
    run_tag: String,
    fold: String,
    symbol: String,
    validation_rows: usize,
    flow_valid_rows: usize,
    missing_mid_rows: usize,
    missing_spread_rows: usize,
    missing_fill_rows: usize,
    signed_gross_bps_mean_30s: Option<f64>,
    signed_gross_bps_mean_60s: Option<f64>,
    alignment_rate_30s: Option<f64>,
    alignment_rate_60s: Option<f64>,
    stable_side_alignment: bool,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct EventStudyRow {
    run_tag: String,
    fold: String,
    symbol: String,
    bucket_type: String,
    bucket: String,
    threshold: f64,
    horizon_seconds: u32,
    validation_rows: usize,
    selected_rows: usize,
    selected_rate: f64,
    long_rows: usize,
    short_rows: usize,
    signed_gross_bps_mean: Option<f64>,
    signed_gross_bps_median: Option<f64>,
    signed_gross_bps_p25: Option<f64>,
    signed_gross_bps_p75: Option<f64>,
    win_rate: Option<f64>,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct SparseAnchorRow {
    run_tag: String,
    fold: String,
    date: String,
    symbol: String,
    bucket: String,
    cooldown_seconds: u32,
    signal_timestamp: u64,
    signal_local_timestamp: u64,
    side: String,
    flow_sign: i8,
    trade_buy_amount: f64,
    trade_sell_amount: f64,
    trade_notional_quote: f64,
    trade_flow_imbalance: Option<f64>,
    signed_flow_shock: f64,
    abs_flow_shock: f64,
    shock_threshold: f64,
    thresholds_fit_on_train: String,
    guardrail: String,
    #[serde(skip_serializing)]
    signal_pos: usize,
}

#[derive(Debug, Clone, Serialize)]
struct AfterCostRow {
    run_tag: String,
    fold: String,
    date: String,
    symbol: String,
    bucket: String,
    cooldown_seconds: u32,
    horizon_seconds: u32,
    side: String,
    signal_local_timestamp: u64,
    entry_local_timestamp: u64,
    exit_local_timestamp: u64,
    entry_mid: f64,
    exit_mid: f64,
    spread_bps: f64,
    fill_realism_score: f64,
    signed_gross_bps: f64,
    fee_bps: f64,
    maker_cost_bps: f64,
    taker_cost_bps: f64,
    maker_net_bps: f64,
    taker_net_bps: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct NegativeControlRow {
    run_tag: String,
    control_type: String,
    fold: String,
    date: String,
    symbol: String,
    control_symbol: String,
    bucket: String,
    cooldown_seconds: u32,
    horizon_seconds: u32,
    side: String,
    base_signal_local_timestamp: u64,
    control_signal_local_timestamp: u64,
    entry_local_timestamp: u64,
    exit_local_timestamp: u64,
    entry_mid: f64,
    exit_mid: f64,
    spread_bps: f64,
    fill_realism_score: f64,
    signed_gross_bps: f64,
    fee_bps: f64,
    maker_cost_bps: f64,
    taker_cost_bps: f64,
    maker_net_bps: f64,
    taker_net_bps: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize)]
struct FailureReportRow {
    run_tag: String,
    primary_status: String,
    candidate_key: String,
    sparse_anchor_rows: usize,
    after_cost_rows: usize,
    negative_control_rows: usize,
    base_maker_net_mean: Option<f64>,
    best_control_maker_net_mean: Option<f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    data_quality_blockers: usize,
    excluded_missing_mid_rows: usize,
    excluded_missing_spread_rows: usize,
    excluded_missing_fill_rows: usize,
    evidence: String,
    guardrail: String,
}

#[derive(Debug, Clone)]
struct InputAudit {
    potential_rows: usize,
    quality_rows: usize,
    missing_mid_rows: usize,
    missing_spread_rows: usize,
    missing_fill_rows: usize,
    sort_violations: usize,
    quality_blockers: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
struct CandidateKey {
    symbol: String,
    bucket: String,
    cooldown_seconds: u32,
    horizon_seconds: u32,
}

impl CandidateKey {
    fn label(&self) -> String {
        format!(
            "{}|{}|cooldown_{}s|horizon_{}s",
            self.symbol, self.bucket, self.cooldown_seconds, self.horizon_seconds
        )
    }
}

#[derive(Debug, Clone)]
struct CandidateEval {
    key: CandidateKey,
    base_rows: usize,
    base_maker_net_mean: f64,
    control_means: BTreeMap<String, f64>,
    control_abs_ge_base_abs_rate: Option<f64>,
    passes_controls: bool,
}

#[derive(Debug, Clone)]
struct CostResult {
    date: String,
    entry_local_timestamp: u64,
    exit_local_timestamp: u64,
    entry_mid: f64,
    exit_mid: f64,
    spread_bps: f64,
    fill_realism_score: f64,
    signed_gross_bps: f64,
    maker_cost_bps: f64,
    taker_cost_bps: f64,
    maker_net_bps: f64,
    taker_net_bps: f64,
}

pub fn run_v11(config: &V11Config) -> Result<V11Summary> {
    if !config.fee_bps.is_finite() || config.fee_bps < 0.0 {
        bail!("--fee-bps must be finite and non-negative");
    }

    let paths = Paths::new(config);
    let (mut rows, mut audit) = read_potential_rows(&paths.potential_csv, &config.run_tag)?;
    let quality_rows = read_quality_rows(&paths.quality_csv, &config.run_tag)?;
    audit.quality_rows = quality_rows.len();
    audit
        .quality_blockers
        .extend(quality_blockers(&quality_rows, &config.run_tag));

    rows.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.local_timestamp.cmp(&b.local_timestamp))
    });
    let by_symbol = rows_by_symbol(&rows);
    let thresholds = fit_thresholds(&by_symbol);
    let side_alignment = build_side_alignment(&by_symbol, &thresholds);
    let event_study = build_event_study(&by_symbol, &thresholds);
    let sparse_anchors = build_sparse_anchors(&by_symbol, &thresholds);
    let after_cost = build_after_cost_rows(&by_symbol, &sparse_anchors, config.fee_bps);
    let negative_controls =
        build_negative_controls(&by_symbol, &sparse_anchors, &after_cost, config.fee_bps);

    let (primary_status, candidate) = choose_primary_status(
        &audit,
        &side_alignment,
        &event_study,
        &sparse_anchors,
        &after_cost,
        &negative_controls,
    );
    let failure_report = vec![build_failure_report_row(
        &config.run_tag,
        &primary_status,
        candidate.as_ref(),
        &audit,
        sparse_anchors.len(),
        after_cost.len(),
        negative_controls.len(),
    )];

    write_csv_atomic(&paths.side_alignment_csv, &side_alignment)?;
    write_csv_atomic(&paths.event_study_csv, &event_study)?;
    write_csv_atomic(&paths.sparse_anchors_csv, &sparse_anchors)?;
    write_csv_atomic(&paths.after_cost_csv, &after_cost)?;
    write_csv_atomic(&paths.negative_controls_csv, &negative_controls)?;
    write_csv_atomic(&paths.failure_report_csv, &failure_report)?;
    write_report(
        config,
        &paths,
        &audit,
        &side_alignment,
        &event_study,
        &sparse_anchors,
        &after_cost,
        &negative_controls,
        &failure_report[0],
    )?;

    Ok(V11Summary {
        run_tag: config.run_tag.clone(),
        fee_bps: config.fee_bps,
        potential_rows: audit.potential_rows,
        quality_rows: audit.quality_rows,
        side_alignment_rows: side_alignment.len(),
        event_study_rows: event_study.len(),
        sparse_anchor_rows: sparse_anchors.len(),
        after_cost_rows: after_cost.len(),
        negative_control_rows: negative_controls.len(),
        primary_status,
        side_alignment_csv: path_string(&paths.side_alignment_csv),
        event_study_csv: path_string(&paths.event_study_csv),
        sparse_anchors_csv: path_string(&paths.sparse_anchors_csv),
        after_cost_csv: path_string(&paths.after_cost_csv),
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
        quality_rows: 0,
        missing_mid_rows: 0,
        missing_spread_rows: 0,
        missing_fill_rows: 0,
        sort_violations: 0,
        quality_blockers: Vec::new(),
    };
    let mut last_ts_by_symbol: BTreeMap<String, u64> = BTreeMap::new();
    let mut seen_symbols = BTreeSet::new();
    let mut closed_symbols = BTreeSet::new();
    let mut current_symbol = String::new();
    for record in reader.deserialize::<RawPotentialRow>() {
        let raw = record.with_context(|| format!("failed to parse {}", path.display()))?;
        if raw.run_tag != run_tag {
            audit.quality_blockers.push(format!(
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
        if let Some(last_ts) = last_ts_by_symbol.get(&raw.symbol) {
            if raw.local_timestamp < *last_ts {
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
            audit.quality_blockers.push(format!(
                "required symbol missing from potential_state: {symbol}"
            ));
        }
    }
    if audit.sort_violations > 0 {
        audit.quality_blockers.push(format!(
            "potential_state is not sorted by contiguous symbol/local_timestamp blocks: violations={}",
            audit.sort_violations
        ));
    }
    if rows.is_empty() {
        audit
            .quality_blockers
            .push("potential_state has zero rows".to_string());
    }
    Ok((rows, audit))
}

fn read_quality_rows(path: &Path, run_tag: &str) -> Result<Vec<QualityCoverageRow>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    let mut rows = Vec::new();
    for record in reader.deserialize::<QualityCoverageRow>() {
        let row = record.with_context(|| format!("failed to parse {}", path.display()))?;
        if row.run_tag == run_tag {
            rows.push(row);
        }
    }
    Ok(rows)
}

fn quality_blockers(rows: &[QualityCoverageRow], run_tag: &str) -> Vec<String> {
    let mut blockers = Vec::new();
    if rows.is_empty() {
        blockers.push(format!(
            "dynamic quality coverage is empty for run_tag={run_tag}"
        ));
        return blockers;
    }
    for row in rows {
        if row.raw_status != "present" {
            blockers.push(format!(
                "{} {} raw_status={}",
                row.symbol, row.date, row.raw_status
            ));
        }
        if !row.required_schema_ok {
            blockers.push(format!(
                "{} {} required_schema_ok=false",
                row.symbol, row.date
            ));
        }
        if row.replay_status != "completed" {
            blockers.push(format!(
                "{} {} replay_status={}",
                row.symbol, row.date, row.replay_status
            ));
        }
        if !row.multilevel_schema_ok {
            blockers.push(format!(
                "{} {} multilevel_schema_ok=false",
                row.symbol, row.date
            ));
        }
        if row.actual_part_files == 0 {
            blockers.push(format!("{} {} actual_part_files=0", row.symbol, row.date));
        }
    }
    blockers
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
            let mut notional_values = Vec::new();
            let mut shock_values = Vec::new();
            for row in &train {
                if let Some(flow) = row.flow_derived() {
                    notional_values.push(row.trade_notional_quote);
                    shock_values.push(flow.abs_flow_shock);
                }
            }
            if notional_values.is_empty() || shock_values.is_empty() || valid_rows == 0 {
                continue;
            }
            let notional_thresholds = NOTIONAL_BUCKETS
                .iter()
                .filter_map(|(name, q)| quantile(&notional_values, *q).map(|value| (*name, value)))
                .collect::<BTreeMap<_, _>>();
            let shock_thresholds = SHOCK_BUCKETS
                .iter()
                .filter_map(|(name, q)| quantile(&shock_values, *q).map(|value| (*name, value)))
                .collect::<BTreeMap<_, _>>();
            out.push(ThresholdSet {
                fold,
                symbol: symbol.clone(),
                train_rows: train.len(),
                valid_rows,
                notional_thresholds,
                shock_thresholds,
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

fn build_side_alignment(
    by_symbol: &BTreeMap<String, Vec<&PotentialRow>>,
    thresholds: &[ThresholdSet],
) -> Vec<SideAlignmentRow> {
    let mut out = Vec::new();
    for fit in thresholds {
        let Some(rows) = by_symbol.get(&fit.symbol) else {
            continue;
        };
        let validation = validation_positions(rows, &fit.fold);
        let mut gross_30 = Vec::new();
        let mut gross_60 = Vec::new();
        let mut flow_valid_rows = 0usize;
        let mut missing_mid_rows = 0usize;
        let mut missing_spread_rows = 0usize;
        let mut missing_fill_rows = 0usize;
        for pos in &validation {
            let row = rows[*pos];
            if row.mid_price.is_none() {
                missing_mid_rows += 1;
            }
            if row.spread_bps.is_none() {
                missing_spread_rows += 1;
            }
            if row.fill_realism_score.is_none() {
                missing_fill_rows += 1;
            }
            let Some(flow) = row.flow_derived() else {
                continue;
            };
            flow_valid_rows += 1;
            if let Some(ret) = forward_return_bps(rows, *pos, 30) {
                gross_30.push(flow.flow_sign as f64 * ret);
            }
            if let Some(ret) = forward_return_bps(rows, *pos, 60) {
                gross_60.push(flow.flow_sign as f64 * ret);
            }
        }
        let mean_30 = mean(&gross_30);
        let mean_60 = mean(&gross_60);
        let align_30 = win_rate(&gross_30);
        let align_60 = win_rate(&gross_60);
        let stable_side_alignment = gross_30.len() >= 30
            && gross_60.len() >= 30
            && mean_30.is_some_and(|value| value > 0.0)
            && mean_60.is_some_and(|value| value > 0.0)
            && align_30.is_some_and(|value| value >= 0.50)
            && align_60.is_some_and(|value| value >= 0.50);
        out.push(SideAlignmentRow {
            run_tag: rows
                .first()
                .map(|row| row.run_tag.clone())
                .unwrap_or_default(),
            fold: fit.fold.name.clone(),
            symbol: fit.symbol.clone(),
            validation_rows: validation.len(),
            flow_valid_rows,
            missing_mid_rows,
            missing_spread_rows,
            missing_fill_rows,
            signed_gross_bps_mean_30s: mean_30,
            signed_gross_bps_mean_60s: mean_60,
            alignment_rate_30s: align_30,
            alignment_rate_60s: align_60,
            stable_side_alignment,
            thresholds_fit_on_train: threshold_rule(fit),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    out.sort_by(|a, b| a.fold.cmp(&b.fold).then_with(|| a.symbol.cmp(&b.symbol)));
    out
}

fn build_event_study(
    by_symbol: &BTreeMap<String, Vec<&PotentialRow>>,
    thresholds: &[ThresholdSet],
) -> Vec<EventStudyRow> {
    let mut out = Vec::new();
    for fit in thresholds {
        let Some(rows) = by_symbol.get(&fit.symbol) else {
            continue;
        };
        let validation = validation_positions(rows, &fit.fold);
        for &horizon_seconds in &HORIZONS {
            for (bucket, threshold) in &fit.notional_thresholds {
                out.push(event_study_for_bucket(
                    rows,
                    &validation,
                    fit,
                    "notional",
                    bucket,
                    *threshold,
                    horizon_seconds,
                ));
            }
            for (bucket, threshold) in &fit.shock_thresholds {
                out.push(event_study_for_bucket(
                    rows,
                    &validation,
                    fit,
                    "shock",
                    bucket,
                    *threshold,
                    horizon_seconds,
                ));
            }
        }
    }
    out.sort_by(|a, b| {
        a.fold
            .cmp(&b.fold)
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.horizon_seconds.cmp(&b.horizon_seconds))
            .then_with(|| a.bucket_type.cmp(&b.bucket_type))
            .then_with(|| a.bucket.cmp(&b.bucket))
    });
    out
}

fn event_study_for_bucket(
    rows: &[&PotentialRow],
    validation: &[usize],
    fit: &ThresholdSet,
    bucket_type: &str,
    bucket: &str,
    threshold: f64,
    horizon_seconds: u32,
) -> EventStudyRow {
    let mut signed_gross = Vec::new();
    let mut selected_rows = 0usize;
    let mut long_rows = 0usize;
    let mut short_rows = 0usize;
    for pos in validation {
        let row = rows[*pos];
        let Some(flow) = row.flow_derived() else {
            continue;
        };
        let passes = match bucket_type {
            "notional" => row.trade_notional_quote >= threshold,
            "shock" => flow.abs_flow_shock >= threshold,
            _ => false,
        };
        if !passes {
            continue;
        }
        selected_rows += 1;
        if flow.flow_sign > 0 {
            long_rows += 1;
        } else {
            short_rows += 1;
        }
        if let Some(ret) = forward_return_bps(rows, *pos, horizon_seconds) {
            signed_gross.push(flow.flow_sign as f64 * ret);
        }
    }
    EventStudyRow {
        run_tag: rows
            .first()
            .map(|row| row.run_tag.clone())
            .unwrap_or_default(),
        fold: fit.fold.name.clone(),
        symbol: fit.symbol.clone(),
        bucket_type: bucket_type.to_string(),
        bucket: bucket.to_string(),
        threshold,
        horizon_seconds,
        validation_rows: validation.len(),
        selected_rows,
        selected_rate: rate(selected_rows, validation.len()),
        long_rows,
        short_rows,
        signed_gross_bps_mean: mean(&signed_gross),
        signed_gross_bps_median: quantile(&signed_gross, 0.50),
        signed_gross_bps_p25: quantile(&signed_gross, 0.25),
        signed_gross_bps_p75: quantile(&signed_gross, 0.75),
        win_rate: win_rate(&signed_gross),
        thresholds_fit_on_train: threshold_rule(fit),
        guardrail: GUARDRAIL.to_string(),
    }
}

fn build_sparse_anchors(
    by_symbol: &BTreeMap<String, Vec<&PotentialRow>>,
    thresholds: &[ThresholdSet],
) -> Vec<SparseAnchorRow> {
    let mut candidates = Vec::new();
    for fit in thresholds {
        let Some(rows) = by_symbol.get(&fit.symbol) else {
            continue;
        };
        let validation = validation_positions(rows, &fit.fold);
        let q95 = fit.shock_thresholds.get("shock_q95").copied();
        let q99 = fit.shock_thresholds.get("shock_q99").copied();
        for pos in validation {
            let row = rows[pos];
            let Some(flow) = row.flow_derived() else {
                continue;
            };
            let bucket_and_threshold =
                if q99.is_some_and(|threshold| flow.abs_flow_shock >= threshold) {
                    Some(("shock_q99", q99.unwrap_or(0.0)))
                } else if q95.is_some_and(|threshold| flow.abs_flow_shock >= threshold) {
                    Some(("shock_q95", q95.unwrap_or(0.0)))
                } else {
                    None
                };
            let Some((bucket, threshold)) = bucket_and_threshold else {
                continue;
            };
            for &cooldown_seconds in &COOLDOWNS {
                candidates.push(SparseAnchorRow {
                    run_tag: row.run_tag.clone(),
                    fold: fit.fold.name.clone(),
                    date: row.date.clone(),
                    symbol: fit.symbol.clone(),
                    bucket: bucket.to_string(),
                    cooldown_seconds,
                    signal_timestamp: row.timestamp,
                    signal_local_timestamp: row.local_timestamp,
                    side: side_from_flow_sign(flow.flow_sign).to_string(),
                    flow_sign: flow.flow_sign,
                    trade_buy_amount: row.trade_buy_amount,
                    trade_sell_amount: row.trade_sell_amount,
                    trade_notional_quote: row.trade_notional_quote,
                    trade_flow_imbalance: row.trade_flow_imbalance,
                    signed_flow_shock: flow.signed_flow_shock,
                    abs_flow_shock: flow.abs_flow_shock,
                    shock_threshold: threshold,
                    thresholds_fit_on_train: threshold_rule(fit),
                    guardrail: GUARDRAIL.to_string(),
                    signal_pos: pos,
                });
            }
        }
    }
    candidates.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.cooldown_seconds.cmp(&b.cooldown_seconds))
            .then_with(|| a.signal_local_timestamp.cmp(&b.signal_local_timestamp))
            .then_with(|| bucket_rank(&a.bucket).cmp(&bucket_rank(&b.bucket)))
            .then_with(|| a.fold.cmp(&b.fold))
    });

    let mut next_allowed: BTreeMap<(String, u32), u64> = BTreeMap::new();
    let mut seen_key: HashSet<(String, u32, u64)> = HashSet::new();
    let mut out = Vec::new();
    for candidate in candidates {
        let dedupe_key = (
            candidate.symbol.clone(),
            candidate.cooldown_seconds,
            candidate.signal_local_timestamp,
        );
        if seen_key.contains(&dedupe_key) {
            continue;
        }
        let cooldown_key = (candidate.symbol.clone(), candidate.cooldown_seconds);
        let allowed_ts = next_allowed.get(&cooldown_key).copied().unwrap_or(0);
        if candidate.signal_local_timestamp < allowed_ts {
            continue;
        }
        seen_key.insert(dedupe_key);
        next_allowed.insert(
            cooldown_key,
            candidate
                .signal_local_timestamp
                .saturating_add(candidate.cooldown_seconds as u64 * 1_000_000),
        );
        out.push(candidate);
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.cooldown_seconds.cmp(&b.cooldown_seconds))
            .then_with(|| a.signal_local_timestamp.cmp(&b.signal_local_timestamp))
    });
    out
}

fn build_after_cost_rows(
    by_symbol: &BTreeMap<String, Vec<&PotentialRow>>,
    anchors: &[SparseAnchorRow],
    fee_bps: f64,
) -> Vec<AfterCostRow> {
    let mut out = Vec::new();
    for anchor in anchors {
        let Some(rows) = by_symbol.get(&anchor.symbol) else {
            continue;
        };
        for &horizon_seconds in &ANCHOR_HORIZONS {
            let Some(cost) = cost_from_signal(
                rows,
                anchor.signal_pos,
                anchor.flow_sign,
                horizon_seconds,
                fee_bps,
            ) else {
                continue;
            };
            out.push(AfterCostRow {
                run_tag: anchor.run_tag.clone(),
                fold: anchor.fold.clone(),
                date: cost.date,
                symbol: anchor.symbol.clone(),
                bucket: anchor.bucket.clone(),
                cooldown_seconds: anchor.cooldown_seconds,
                horizon_seconds,
                side: anchor.side.clone(),
                signal_local_timestamp: anchor.signal_local_timestamp,
                entry_local_timestamp: cost.entry_local_timestamp,
                exit_local_timestamp: cost.exit_local_timestamp,
                entry_mid: cost.entry_mid,
                exit_mid: cost.exit_mid,
                spread_bps: cost.spread_bps,
                fill_realism_score: cost.fill_realism_score,
                signed_gross_bps: cost.signed_gross_bps,
                fee_bps,
                maker_cost_bps: cost.maker_cost_bps,
                taker_cost_bps: cost.taker_cost_bps,
                maker_net_bps: cost.maker_net_bps,
                taker_net_bps: cost.taker_net_bps,
                guardrail: GUARDRAIL.to_string(),
            });
        }
    }
    out
}

fn build_negative_controls(
    by_symbol: &BTreeMap<String, Vec<&PotentialRow>>,
    anchors: &[SparseAnchorRow],
    after_cost: &[AfterCostRow],
    fee_bps: f64,
) -> Vec<NegativeControlRow> {
    let after_cost_keys = after_cost
        .iter()
        .map(|row| {
            (
                row.symbol.clone(),
                row.bucket.clone(),
                row.cooldown_seconds,
                row.horizon_seconds,
                row.signal_local_timestamp,
            )
        })
        .collect::<HashSet<_>>();
    let mut out = Vec::new();
    for anchor in anchors {
        let Some(rows) = by_symbol.get(&anchor.symbol) else {
            continue;
        };
        for &horizon_seconds in &ANCHOR_HORIZONS {
            let base_key = (
                anchor.symbol.clone(),
                anchor.bucket.clone(),
                anchor.cooldown_seconds,
                horizon_seconds,
                anchor.signal_local_timestamp,
            );
            if !after_cost_keys.contains(&base_key) {
                continue;
            }
            push_control(
                &mut out,
                "side_flip",
                anchor,
                rows,
                &anchor.symbol,
                anchor.signal_pos,
                -anchor.flow_sign,
                horizon_seconds,
                fee_bps,
            );
            let plus_target = anchor.signal_local_timestamp.saturating_add(60_000_000);
            if let Some(pos) = first_row_at_or_after(rows, plus_target) {
                push_control(
                    &mut out,
                    "timestamp_shift_plus_60s",
                    anchor,
                    rows,
                    &anchor.symbol,
                    pos,
                    anchor.flow_sign,
                    horizon_seconds,
                    fee_bps,
                );
            }
            let minus_target = anchor.signal_local_timestamp.saturating_sub(60_000_000);
            if let Some(pos) = first_row_at_or_after(rows, minus_target) {
                push_control(
                    &mut out,
                    "timestamp_shift_minus_60s",
                    anchor,
                    rows,
                    &anchor.symbol,
                    pos,
                    anchor.flow_sign,
                    horizon_seconds,
                    fee_bps,
                );
            }
            if let Some((control_symbol, control_rows)) =
                wrong_symbol_rows(by_symbol, &anchor.symbol)
            {
                if let Some(pos) =
                    first_row_at_or_after(control_rows, anchor.signal_local_timestamp)
                {
                    push_control(
                        &mut out,
                        "wrong_symbol_same_time",
                        anchor,
                        control_rows,
                        control_symbol,
                        pos,
                        anchor.flow_sign,
                        horizon_seconds,
                        fee_bps,
                    );
                }
            }
        }
    }
    out
}

fn push_control(
    out: &mut Vec<NegativeControlRow>,
    control_type: &str,
    anchor: &SparseAnchorRow,
    rows: &[&PotentialRow],
    control_symbol: &str,
    signal_pos: usize,
    flow_sign: i8,
    horizon_seconds: u32,
    fee_bps: f64,
) {
    let Some(cost) = cost_from_signal(rows, signal_pos, flow_sign, horizon_seconds, fee_bps) else {
        return;
    };
    let control_signal_ts = rows
        .get(signal_pos)
        .map(|row| row.local_timestamp)
        .unwrap_or(anchor.signal_local_timestamp);
    out.push(NegativeControlRow {
        run_tag: anchor.run_tag.clone(),
        control_type: control_type.to_string(),
        fold: anchor.fold.clone(),
        date: cost.date,
        symbol: anchor.symbol.clone(),
        control_symbol: control_symbol.to_string(),
        bucket: anchor.bucket.clone(),
        cooldown_seconds: anchor.cooldown_seconds,
        horizon_seconds,
        side: side_from_flow_sign(flow_sign).to_string(),
        base_signal_local_timestamp: anchor.signal_local_timestamp,
        control_signal_local_timestamp: control_signal_ts,
        entry_local_timestamp: cost.entry_local_timestamp,
        exit_local_timestamp: cost.exit_local_timestamp,
        entry_mid: cost.entry_mid,
        exit_mid: cost.exit_mid,
        spread_bps: cost.spread_bps,
        fill_realism_score: cost.fill_realism_score,
        signed_gross_bps: cost.signed_gross_bps,
        fee_bps,
        maker_cost_bps: cost.maker_cost_bps,
        taker_cost_bps: cost.taker_cost_bps,
        maker_net_bps: cost.maker_net_bps,
        taker_net_bps: cost.taker_net_bps,
        guardrail: GUARDRAIL.to_string(),
    });
}

fn choose_primary_status(
    audit: &InputAudit,
    side_alignment: &[SideAlignmentRow],
    event_study: &[EventStudyRow],
    sparse_anchors: &[SparseAnchorRow],
    after_cost: &[AfterCostRow],
    negative_controls: &[NegativeControlRow],
) -> (String, Option<CandidateEval>) {
    if !audit.quality_blockers.is_empty()
        || !event_study_has_required_symbols_and_horizons(event_study)
    {
        return ("data_quality_blocked".to_string(), None);
    }
    if sparse_anchors.len() < SPARSE_GLOBAL_MIN_EVENTS {
        return ("insufficient_sparse_events".to_string(), None);
    }
    if !side_alignment.iter().any(|row| row.stable_side_alignment) {
        return ("side_alignment_unstable".to_string(), None);
    }
    let evaluations = evaluate_candidates(after_cost, negative_controls);
    if evaluations.is_empty() {
        return ("gross_edge_too_thin".to_string(), None);
    }
    let best_positive = evaluations
        .iter()
        .filter(|eval| eval.base_maker_net_mean > 0.0)
        .max_by(|a, b| a.base_maker_net_mean.total_cmp(&b.base_maker_net_mean))
        .cloned();
    let Some(best_positive) = best_positive else {
        let best = evaluations
            .into_iter()
            .max_by(|a, b| a.base_maker_net_mean.total_cmp(&b.base_maker_net_mean));
        return ("gross_edge_too_thin".to_string(), best);
    };
    let best_pass = evaluations
        .into_iter()
        .filter(|eval| eval.base_maker_net_mean > 0.0 && eval.passes_controls)
        .max_by(|a, b| a.base_maker_net_mean.total_cmp(&b.base_maker_net_mean));
    if let Some(best_pass) = best_pass {
        ("trade_flow_survives_2bps".to_string(), Some(best_pass))
    } else {
        ("controls_not_separated".to_string(), Some(best_positive))
    }
}

fn evaluate_candidates(
    after_cost: &[AfterCostRow],
    negative_controls: &[NegativeControlRow],
) -> Vec<CandidateEval> {
    let mut base: BTreeMap<CandidateKey, Vec<f64>> = BTreeMap::new();
    for row in after_cost {
        base.entry(CandidateKey {
            symbol: row.symbol.clone(),
            bucket: row.bucket.clone(),
            cooldown_seconds: row.cooldown_seconds,
            horizon_seconds: row.horizon_seconds,
        })
        .or_default()
        .push(row.maker_net_bps);
    }

    let mut controls: BTreeMap<CandidateKey, BTreeMap<String, Vec<f64>>> = BTreeMap::new();
    for row in negative_controls {
        controls
            .entry(CandidateKey {
                symbol: row.symbol.clone(),
                bucket: row.bucket.clone(),
                cooldown_seconds: row.cooldown_seconds,
                horizon_seconds: row.horizon_seconds,
            })
            .or_default()
            .entry(row.control_type.clone())
            .or_default()
            .push(row.maker_net_bps);
    }

    let mut out = Vec::new();
    for (key, base_values) in base {
        let Some(base_mean) = mean(&base_values) else {
            continue;
        };
        let mut control_means = BTreeMap::new();
        if let Some(control_groups) = controls.get(&key) {
            for (control_type, values) in control_groups {
                if let Some(value) = mean(values) {
                    control_means.insert(control_type.clone(), value);
                }
            }
        }
        let control_abs_ge_base_abs_rate = if control_means.is_empty() {
            None
        } else {
            let count = control_means
                .values()
                .filter(|value| value.abs() >= base_mean.abs())
                .count();
            Some(rate(count, control_means.len()))
        };
        let has_all_controls = [
            "side_flip",
            "timestamp_shift_plus_60s",
            "timestamp_shift_minus_60s",
            "wrong_symbol_same_time",
        ]
        .iter()
        .all(|name| control_means.contains_key(*name));
        let base_beats_controls = control_means.values().all(|value| base_mean > *value);
        let passes_controls = has_all_controls
            && base_mean > 0.0
            && base_beats_controls
            && control_abs_ge_base_abs_rate.is_some_and(|rate| rate <= 0.35);
        out.push(CandidateEval {
            key,
            base_rows: base_values.len(),
            base_maker_net_mean: base_mean,
            control_means,
            control_abs_ge_base_abs_rate,
            passes_controls,
        });
    }
    out
}

fn build_failure_report_row(
    run_tag: &str,
    primary_status: &str,
    candidate: Option<&CandidateEval>,
    audit: &InputAudit,
    sparse_anchor_rows: usize,
    after_cost_rows: usize,
    negative_control_rows: usize,
) -> FailureReportRow {
    let best_control_maker_net_mean =
        candidate.and_then(|eval| eval.control_means.values().copied().max_by(f64::total_cmp));
    let evidence = match (primary_status, candidate) {
        ("data_quality_blocked", _) => format!(
            "data quality blockers={}, sort violations={}, missing required symbols or horizons may be present",
            audit.quality_blockers.len(),
            audit.sort_violations
        ),
        ("insufficient_sparse_events", _) => format!(
            "sparse anchors={} below global minimum {}",
            sparse_anchor_rows, SPARSE_GLOBAL_MIN_EVENTS
        ),
        ("side_alignment_unstable", _) => {
            "no fold/symbol row has positive 30s and 60s signed-gross alignment".to_string()
        }
        ("gross_edge_too_thin", Some(eval)) => format!(
            "best candidate {} has maker_net_mean={:.6} over {} rows",
            eval.key.label(),
            eval.base_maker_net_mean,
            eval.base_rows
        ),
        ("gross_edge_too_thin", None) => "no after-cost candidate rows were generated".to_string(),
        ("controls_not_separated", Some(eval)) => format!(
            "best positive candidate {} maker_net_mean={:.6}; control_abs_ge_base_abs_rate={}",
            eval.key.label(),
            eval.base_maker_net_mean,
            fmt_opt(eval.control_abs_ge_base_abs_rate, 6)
        ),
        ("trade_flow_survives_2bps", Some(eval)) => format!(
            "candidate {} maker_net_mean={:.6} beats all controls; control_abs_ge_base_abs_rate={}",
            eval.key.label(),
            eval.base_maker_net_mean,
            fmt_opt(eval.control_abs_ge_base_abs_rate, 6)
        ),
        _ => "status selected by V11 precedence".to_string(),
    };
    FailureReportRow {
        run_tag: run_tag.to_string(),
        primary_status: primary_status.to_string(),
        candidate_key: candidate
            .map(|eval| eval.key.label())
            .unwrap_or_else(|| "none".to_string()),
        sparse_anchor_rows,
        after_cost_rows,
        negative_control_rows,
        base_maker_net_mean: candidate.map(|eval| eval.base_maker_net_mean),
        best_control_maker_net_mean,
        control_abs_ge_base_abs_rate: candidate.and_then(|eval| eval.control_abs_ge_base_abs_rate),
        data_quality_blockers: audit.quality_blockers.len(),
        excluded_missing_mid_rows: audit.missing_mid_rows,
        excluded_missing_spread_rows: audit.missing_spread_rows,
        excluded_missing_fill_rows: audit.missing_fill_rows,
        evidence,
        guardrail: GUARDRAIL.to_string(),
    }
}

fn write_report(
    config: &V11Config,
    paths: &Paths,
    audit: &InputAudit,
    side_alignment: &[SideAlignmentRow],
    event_study: &[EventStudyRow],
    sparse_anchors: &[SparseAnchorRow],
    after_cost: &[AfterCostRow],
    negative_controls: &[NegativeControlRow],
    failure: &FailureReportRow,
) -> Result<()> {
    ensure_parent_dir(&paths.report_md)?;
    let top_event = event_study
        .iter()
        .filter(|row| row.bucket_type == "shock")
        .max_by(|a, b| {
            a.signed_gross_bps_mean
                .unwrap_or(f64::NEG_INFINITY)
                .total_cmp(&b.signed_gross_bps_mean.unwrap_or(f64::NEG_INFINITY))
        });
    let best_after_cost = after_cost
        .iter()
        .max_by(|a, b| a.maker_net_bps.total_cmp(&b.maker_net_bps));
    let mut lines = Vec::new();
    lines.push("# BONK V11 Trade-Flow Edge Audit".to_string());
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
    lines.push("## Input And Data Checks".to_string());
    lines.push(String::new());
    lines.push(format!("- potential rows: `{}`", audit.potential_rows));
    lines.push(format!("- quality rows: `{}`", audit.quality_rows));
    lines.push(format!(
        "- excluded missing mid/spread/fill rows: `{}` / `{}` / `{}`",
        audit.missing_mid_rows, audit.missing_spread_rows, audit.missing_fill_rows
    ));
    lines.push(format!(
        "- data quality blockers: `{}`",
        audit.quality_blockers.len()
    ));
    if !audit.quality_blockers.is_empty() {
        lines.push("- blockers:".to_string());
        for blocker in audit.quality_blockers.iter().take(10) {
            lines.push(format!("  - `{blocker}`"));
        }
    }
    lines.push(String::new());
    lines.push("## Audit Outputs".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- side alignment rows: `{}` -> `{}`",
        side_alignment.len(),
        path_string(&paths.side_alignment_csv)
    ));
    lines.push(format!(
        "- event study rows: `{}` -> `{}`",
        event_study.len(),
        path_string(&paths.event_study_csv)
    ));
    lines.push(format!(
        "- sparse anchor rows: `{}` -> `{}`",
        sparse_anchors.len(),
        path_string(&paths.sparse_anchors_csv)
    ));
    lines.push(format!(
        "- after-cost rows: `{}` -> `{}`",
        after_cost.len(),
        path_string(&paths.after_cost_csv)
    ));
    lines.push(format!(
        "- negative-control rows: `{}` -> `{}`",
        negative_controls.len(),
        path_string(&paths.negative_controls_csv)
    ));
    lines.push(format!(
        "- failure report: `{}`",
        path_string(&paths.failure_report_csv)
    ));
    lines.push(String::new());
    lines.push("## Top Diagnostics".to_string());
    lines.push(String::new());
    if let Some(row) = top_event {
        lines.push(format!(
            "- top shock event-study row: `{}` `{}` `{}` horizon `{}` mean signed gross `{}` selected `{}`",
            row.fold,
            row.symbol,
            row.bucket,
            row.horizon_seconds,
            fmt_opt(row.signed_gross_bps_mean, 6),
            row.selected_rows
        ));
    }
    if let Some(row) = best_after_cost {
        lines.push(format!(
            "- best single after-cost row: `{}` `{}` `{}` cooldown `{}` horizon `{}` maker net `{:.6}`",
            row.fold,
            row.symbol,
            row.bucket,
            row.cooldown_seconds,
            row.horizon_seconds,
            row.maker_net_bps
        ));
    }
    lines.push(String::new());
    lines.push("## Interpretation Boundary".to_string());
    lines.push(String::new());
    lines.push("V11 tests whether V10 trade-flow shocks can become sparse, cost-aware, and control-separated events under a fixed 2 bps cost. It does not expand the window, train a richer model, or convert the result into an execution recommendation.".to_string());
    lines.push(String::new());
    fs::write(&paths.report_md, lines.join("\n"))
        .with_context(|| format!("failed to write {}", paths.report_md.display()))
}

fn event_study_has_required_symbols_and_horizons(event_study: &[EventStudyRow]) -> bool {
    for symbol in REQUIRED_SYMBOLS {
        let horizons = event_study
            .iter()
            .filter(|row| row.symbol == symbol)
            .map(|row| row.horizon_seconds)
            .collect::<BTreeSet<_>>();
        if HORIZONS.iter().any(|horizon| !horizons.contains(horizon)) {
            return false;
        }
    }
    true
}

fn validation_positions(rows: &[&PotentialRow], fold: &FoldRange) -> Vec<usize> {
    rows.iter()
        .enumerate()
        .filter_map(|(idx, row)| {
            (row.local_timestamp >= fold.valid_start && row.local_timestamp <= fold.valid_end)
                .then_some(idx)
        })
        .collect()
}

fn forward_return_bps(
    rows: &[&PotentialRow],
    start_pos: usize,
    horizon_seconds: u32,
) -> Option<f64> {
    let start = rows.get(start_pos)?;
    let start_mid = start.mid_price?;
    if start_mid <= 0.0 {
        return None;
    }
    let target = start
        .local_timestamp
        .saturating_add(horizon_seconds as u64 * 1_000_000);
    let exit_pos = first_mid_at_or_after(rows, target)?;
    let exit_mid = rows.get(exit_pos)?.mid_price?;
    finite((exit_mid - start_mid) / start_mid * 10_000.0)
}

fn cost_from_signal(
    rows: &[&PotentialRow],
    signal_pos: usize,
    flow_sign: i8,
    horizon_seconds: u32,
    fee_bps: f64,
) -> Option<CostResult> {
    let signal_ts = rows.get(signal_pos)?.local_timestamp;
    let entry_pos = first_entry_after(rows, signal_ts)?;
    let entry = rows.get(entry_pos)?;
    let entry_mid = entry.mid_price?;
    let spread_bps = entry.spread_bps?;
    let fill_realism_score = entry.fill_realism_score?;
    let target = entry
        .local_timestamp
        .saturating_add(horizon_seconds as u64 * 1_000_000);
    let exit_pos = first_mid_at_or_after_from(rows, target, entry_pos)?;
    let exit = rows.get(exit_pos)?;
    let exit_mid = exit.mid_price?;
    if entry_mid <= 0.0 {
        return None;
    }
    let signed_gross_bps = if flow_sign >= 0 {
        (exit_mid - entry_mid) / entry_mid * 10_000.0
    } else {
        (entry_mid - exit_mid) / entry_mid * 10_000.0
    };
    let maker_cost_bps = maker_cost_bps(fee_bps, spread_bps, fill_realism_score);
    let taker_cost_bps = taker_cost_bps(fee_bps, spread_bps, fill_realism_score);
    Some(CostResult {
        date: entry.date.clone(),
        entry_local_timestamp: entry.local_timestamp,
        exit_local_timestamp: exit.local_timestamp,
        entry_mid,
        exit_mid,
        spread_bps,
        fill_realism_score,
        signed_gross_bps,
        maker_cost_bps,
        taker_cost_bps,
        maker_net_bps: signed_gross_bps - maker_cost_bps,
        taker_net_bps: signed_gross_bps - taker_cost_bps,
    })
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

fn first_mid_at_or_after(rows: &[&PotentialRow], target: u64) -> Option<usize> {
    first_mid_at_or_after_from(
        rows,
        target,
        first_row_at_or_after(rows, target).unwrap_or(rows.len()),
    )
}

fn first_mid_at_or_after_from(
    rows: &[&PotentialRow],
    target: u64,
    start_pos: usize,
) -> Option<usize> {
    let mut pos = first_row_at_or_after(rows, target).unwrap_or(rows.len());
    if pos < start_pos {
        pos = start_pos;
    }
    while pos < rows.len() {
        if rows[pos]
            .mid_price
            .is_some_and(|value| value.is_finite() && value > 0.0)
        {
            return Some(pos);
        }
        pos += 1;
    }
    None
}

fn first_entry_after(rows: &[&PotentialRow], signal_ts: u64) -> Option<usize> {
    let mut pos = first_row_at_or_after(rows, signal_ts.saturating_add(1))?;
    while pos < rows.len() {
        if rows[pos].has_cost_inputs() {
            return Some(pos);
        }
        pos += 1;
    }
    None
}

fn wrong_symbol_rows<'a>(
    by_symbol: &'a BTreeMap<String, Vec<&'a PotentialRow>>,
    symbol: &str,
) -> Option<(&'a str, &'a Vec<&'a PotentialRow>)> {
    by_symbol
        .iter()
        .find(|(candidate, rows)| candidate.as_str() != symbol && !rows.is_empty())
        .map(|(candidate, rows)| (candidate.as_str(), rows))
}

fn maker_cost_bps(fee_bps: f64, spread_bps: f64, fill_realism_score: f64) -> f64 {
    fee_bps + 0.25 * spread_bps + (1.0 - fill_realism_score) * spread_bps
}

fn taker_cost_bps(fee_bps: f64, spread_bps: f64, fill_realism_score: f64) -> f64 {
    fee_bps + spread_bps + 0.50 * (1.0 - fill_realism_score) * spread_bps
}

fn side_from_flow_sign(flow_sign: i8) -> &'static str {
    if flow_sign >= 0 { "long" } else { "short" }
}

fn bucket_rank(bucket: &str) -> u8 {
    match bucket {
        "shock_q99" => 0,
        "shock_q95" => 1,
        _ => 2,
    }
}

fn threshold_rule(fit: &ThresholdSet) -> String {
    let notional = NOTIONAL_BUCKETS
        .iter()
        .filter_map(|(name, _)| {
            fit.notional_thresholds
                .get(name)
                .map(|value| format!("{name}={value:.6}"))
        })
        .collect::<Vec<_>>()
        .join(";");
    let shock = SHOCK_BUCKETS
        .iter()
        .filter_map(|(name, _)| {
            fit.shock_thresholds
                .get(name)
                .map(|value| format!("{name}={value:.6}"))
        })
        .collect::<Vec<_>>()
        .join(";");
    format!(
        "train_only;purge_us={};fold={};train_rows={};valid_rows={};{};{}",
        V10_PURGE_US, fit.fold.name, fit.train_rows, fit.valid_rows, notional, shock
    )
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

fn de_usize_or_zero<'de, D>(deserializer: D) -> std::result::Result<usize, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = Option::<String>::deserialize(deserializer)?;
    let Some(raw) = raw else {
        return Ok(0);
    };
    let raw = raw.trim();
    if raw.is_empty() {
        return Ok(0);
    }
    raw.parse::<usize>().map_err(de::Error::custom)
}

fn de_bool_loose<'de, D>(deserializer: D) -> std::result::Result<bool, D::Error>
where
    D: Deserializer<'de>,
{
    let raw = String::deserialize(deserializer)?;
    match raw.trim().to_ascii_lowercase().as_str() {
        "true" | "1" | "yes" => Ok(true),
        "false" | "0" | "no" => Ok(false),
        other => Err(de::Error::custom(format!("invalid bool value {other}"))),
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
    replace_with_temp(&temp, path)
}

#[allow(dead_code)]
fn load_csv_rows<T: DeserializeOwned>(path: &Path) -> Result<Vec<T>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    let mut out = Vec::new();
    for record in reader.deserialize() {
        out.push(record.with_context(|| format!("failed to parse {}", path.display()))?);
    }
    Ok(out)
}

fn temp_path_for(path: &Path) -> PathBuf {
    let counter = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let stamp = Utc::now().timestamp_micros();
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("bonk_v11_output");
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

#[allow(dead_code)]
fn default_data_root() -> PathBuf {
    PathBuf::from(DEFAULT_BONK_DATA_ROOT)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(ts: u64, mid: f64, buy: f64, sell: f64, notional: f64) -> PotentialRow {
        PotentialRow {
            run_tag: "test".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            timestamp: ts,
            local_timestamp: ts,
            mid_price: Some(mid),
            spread_bps: Some(2.0),
            trade_buy_amount: buy,
            trade_sell_amount: sell,
            trade_notional_quote: notional,
            trade_flow_imbalance: Some(if buy >= sell { 1.0 } else { -1.0 }),
            fill_realism_score: Some(0.5),
        }
    }

    #[test]
    fn train_only_quantile_thresholds_ignore_validation_rows() {
        let mut rows = Vec::new();
        for idx in 0..2000u64 {
            let notional = if idx < 900 { 10.0 } else { 10_000.0 };
            rows.push(row(idx * 1_000_000, 10.0, notional, 0.0, notional));
        }
        let refs = rows.iter().collect::<Vec<_>>();
        let mut by_symbol = BTreeMap::new();
        by_symbol.insert("BONK1MUSDC".to_string(), refs);
        let fits = fit_thresholds(&by_symbol);
        let fold1 = fits.iter().find(|fit| fit.fold.name == "fold1").unwrap();
        assert_eq!(
            fold1.notional_thresholds.get("notional_q99").copied(),
            Some(10.0)
        );
    }

    #[test]
    fn forward_return_uses_first_row_at_or_after_target_timestamp() {
        let rows = vec![
            row(0, 100.0, 1.0, 0.0, 10.0),
            row(29_000_000, 101.0, 1.0, 0.0, 10.0),
            row(31_000_000, 103.0, 1.0, 0.0, 10.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();
        let ret = forward_return_bps(&refs, 0, 30).unwrap();
        assert!((ret - 300.0).abs() < 1e-9);
    }

    #[test]
    fn fee_bps_is_applied_exactly_once_in_cost_formula() {
        let maker = maker_cost_bps(2.0, 4.0, 0.5);
        let taker = taker_cost_bps(2.0, 4.0, 0.5);
        assert!((maker - 5.0).abs() < 1e-9);
        assert!((taker - 7.0).abs() < 1e-9);
    }

    #[test]
    fn cooldown_dedup_keeps_first_event_per_symbol_cooldown_window() {
        let mut rows = Vec::new();
        for idx in 0..2000u64 {
            let ts = idx * 1_000_000;
            let notional = if (1200..=1202).contains(&idx) {
                10_000.0
            } else if idx < 1200 && idx % 10 == 0 {
                100.0
            } else {
                1.0
            };
            rows.push(row(ts, 10.0, notional, 0.0, notional));
        }
        let refs = rows.iter().collect::<Vec<_>>();
        let mut by_symbol = BTreeMap::new();
        by_symbol.insert("BONK1MUSDC".to_string(), refs);
        let fits = fit_thresholds(&by_symbol);
        let anchors = build_sparse_anchors(&by_symbol, &fits);
        let cooldown_60 = anchors
            .iter()
            .filter(|anchor| anchor.cooldown_seconds == 60)
            .collect::<Vec<_>>();
        assert_eq!(cooldown_60.len(), 1);
        assert_eq!(cooldown_60[0].signal_local_timestamp, 1_200_000_000);
    }

    #[test]
    fn negative_controls_preserve_base_cost_formula() {
        let mut rows = vec![
            row(0, 100.0, 10.0, 0.0, 10.0),
            row(1, 100.0, 10.0, 0.0, 10.0),
            row(30_000_001, 101.0, 10.0, 0.0, 10.0),
            row(60_000_001, 102.0, 10.0, 0.0, 10.0),
            row(90_000_001, 103.0, 10.0, 0.0, 10.0),
        ];
        rows[1].spread_bps = Some(4.0);
        rows[1].fill_realism_score = Some(0.5);
        let refs = rows.iter().collect::<Vec<_>>();
        let anchor = SparseAnchorRow {
            run_tag: "test".to_string(),
            fold: "fold1".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            bucket: "shock_q95".to_string(),
            cooldown_seconds: 60,
            signal_timestamp: 0,
            signal_local_timestamp: 0,
            side: "long".to_string(),
            flow_sign: 1,
            trade_buy_amount: 10.0,
            trade_sell_amount: 0.0,
            trade_notional_quote: 10.0,
            trade_flow_imbalance: Some(1.0),
            signed_flow_shock: 10.0_f64.ln_1p(),
            abs_flow_shock: 10.0_f64.ln_1p(),
            shock_threshold: 1.0,
            thresholds_fit_on_train: "train_only".to_string(),
            guardrail: GUARDRAIL.to_string(),
            signal_pos: 0,
        };
        let base = cost_from_signal(&refs, anchor.signal_pos, anchor.flow_sign, 30, 2.0).unwrap();
        let mut controls = Vec::new();
        push_control(
            &mut controls,
            "side_flip",
            &anchor,
            &refs,
            "BONK1MUSDC",
            0,
            -anchor.flow_sign,
            30,
            2.0,
        );
        assert_eq!(controls.len(), 1);
        assert!((controls[0].maker_cost_bps - base.maker_cost_bps).abs() < 1e-9);
        assert!((controls[0].taker_cost_bps - base.taker_cost_bps).abs() < 1e-9);
    }
}

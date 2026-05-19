use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, ArrayRef, Float64Array, Float64Builder, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::Utc;
use finance_chain_core::storage::{ensure_parent_dir, string_array, u64_array};
use parquet::arrow::{ArrowWriter, arrow_reader::ParquetRecordBatchReaderBuilder};
use parquet::file::properties::WriterProperties;
use serde::Serialize;

use crate::download::path_string;

const MINUTE_US: u64 = 60_000_000;

#[derive(Debug, Clone)]
pub struct ResearchPanelConfig {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub run_tag: String,
    pub l2_run_tag: String,
    pub price_context_run_tag: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ResearchPanelSummary {
    pub run_tag: String,
    pub panel_rows: usize,
    pub controlled_factor_rows: usize,
    pub input_label_rows: usize,
    pub panel_duplicate_keys: usize,
    pub price_context_missing_rows: usize,
    pub panel_parquet: String,
    pub controlled_factor_csv: String,
    pub completion_json: String,
}

#[derive(Debug, Clone)]
pub struct ModelReportConfig {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub doc_dir: PathBuf,
    pub run_tag: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ModelReportSummary {
    pub run_tag: String,
    pub metric_rows: usize,
    pub stability_rows: usize,
    pub metrics_csv: String,
    pub stability_csv: String,
    pub report_md: String,
    pub completion_json: String,
}

#[derive(Debug, Clone)]
struct PanelPaths {
    state: PathBuf,
    labels: PathBuf,
    covariance: PathBuf,
    price_context: PathBuf,
    panel: PathBuf,
    controlled_factor_csv: PathBuf,
    panel_completion_json: PathBuf,
}

#[derive(Debug, Clone)]
struct ModelPaths {
    panel: PathBuf,
    metrics_csv: PathBuf,
    stability_csv: PathBuf,
    report_md: PathBuf,
    completion_json: PathBuf,
}

#[derive(Debug, Clone)]
struct StateRow {
    timestamp_us: u64,
    symbol: String,
    book_ticker_count: u64,
    mid_price_per_token_close: Option<f64>,
    spread_bps_median: Option<f64>,
    spread_bps_last: Option<f64>,
    top_depth_bid_notional_median: Option<f64>,
    top_depth_ask_notional_median: Option<f64>,
    microprice_offset_bps_mean: Option<f64>,
    snapshot_count: u64,
    snapshot_spread_bps_median: Option<f64>,
    wobi5_mean: Option<f64>,
    wobi25_mean: Option<f64>,
    depth_imbalance_5_mean: Option<f64>,
    depth_imbalance_25_mean: Option<f64>,
    depth_bid_notional_5_median: Option<f64>,
    depth_ask_notional_5_median: Option<f64>,
    depth_bid_notional_25_median: Option<f64>,
    depth_ask_notional_25_median: Option<f64>,
    snapshot_microprice_offset_bps_mean: Option<f64>,
    trade_count: u64,
    trade_notional_quote_sum: f64,
    trade_flow_imbalance: Option<f64>,
    reported_buy_share: Option<f64>,
    ret_1m_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct LabelRow {
    timestamp_utc: String,
    timestamp_us: u64,
    symbol: String,
    asset: String,
    horizon_hours: u64,
    barrier_bps: u64,
    price_per_token: Option<f64>,
    future_return_bps: Option<f64>,
    mfe_up_bps: Option<f64>,
    mae_down_bps: Option<f64>,
    barrier_first_hit: String,
    label_status: String,
}

#[derive(Debug, Clone)]
struct CovRow {
    timestamp_us: u64,
    avg_corr_60m: Option<f64>,
    first_eigen_share_60m: Option<f64>,
    cross_symbol_abs_ret_mean_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct PriceContextRow {
    timestamp_us: u64,
    close: f64,
    ret_1m_bps: Option<f64>,
    rv_15m_bps: Option<f64>,
    rv_1h_bps: Option<f64>,
    rv_4h_bps: Option<f64>,
    rv_12h_bps: Option<f64>,
    market_return_bps: Option<f64>,
    meme_return_bps: Option<f64>,
    sol_return_bps: Option<f64>,
    bonk_rel_market_bps: Option<f64>,
    bonk_rel_meme_bps: Option<f64>,
    bonk_rel_sol_bps: Option<f64>,
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

#[derive(Debug, Clone, Default)]
struct TrailingContext {
    market_ret_15m_bps: Option<f64>,
    market_ret_60m_bps: Option<f64>,
    market_ret_240m_bps: Option<f64>,
    meme_ret_15m_bps: Option<f64>,
    meme_ret_60m_bps: Option<f64>,
    meme_ret_240m_bps: Option<f64>,
    sol_ret_15m_bps: Option<f64>,
    sol_ret_60m_bps: Option<f64>,
    sol_ret_240m_bps: Option<f64>,
    market_rv_1h_bps: Option<f64>,
    meme_rv_1h_bps: Option<f64>,
    sol_rv_1h_bps: Option<f64>,
}

#[derive(Debug, Clone, Default)]
struct FutureContext {
    market_return_bps: Option<f64>,
    meme_return_bps: Option<f64>,
    sol_return_bps: Option<f64>,
    bonk_binance_return_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct PanelRow {
    run_tag: String,
    timestamp_utc: String,
    timestamp_us: u64,
    symbol: String,
    asset: String,
    quote: String,
    horizon_hours: u64,
    barrier_bps: u64,
    label_status: String,
    barrier_first_hit: String,
    price_per_token: Option<f64>,
    future_return_bps: Option<f64>,
    mfe_up_bps: Option<f64>,
    mae_down_bps: Option<f64>,
    future_ctx_market_return_bps: Option<f64>,
    future_ctx_meme_return_bps: Option<f64>,
    future_ctx_sol_return_bps: Option<f64>,
    future_ctx_bonk_binance_return_bps: Option<f64>,
    future_bonk_rel_market_bps: Option<f64>,
    future_bonk_rel_meme_bps: Option<f64>,
    future_bonk_rel_sol_bps: Option<f64>,
    future_resid_mkt_meme_sol_bps: Option<f64>,
    residual_positive_flag: Option<f64>,
    vol_adj_barrier_bps: Option<f64>,
    vol_adj_barrier_first_hit: String,
    book_ticker_count: u64,
    snapshot_count: u64,
    trade_count: u64,
    trade_notional_quote_sum: f64,
    spread_bps_median: Option<f64>,
    spread_bps_last: Option<f64>,
    top_depth_bid_notional_median: Option<f64>,
    top_depth_ask_notional_median: Option<f64>,
    top_depth_total_notional_median: Option<f64>,
    microprice_offset_bps_mean: Option<f64>,
    snapshot_spread_bps_median: Option<f64>,
    snapshot_microprice_offset_bps_mean: Option<f64>,
    wobi5_mean: Option<f64>,
    wobi25_mean: Option<f64>,
    wobi5_minus_wobi25: Option<f64>,
    depth_imbalance_5_mean: Option<f64>,
    depth_imbalance_25_mean: Option<f64>,
    depth_bid_notional_5_median: Option<f64>,
    depth_ask_notional_5_median: Option<f64>,
    depth_bid_notional_25_median: Option<f64>,
    depth_ask_notional_25_median: Option<f64>,
    trade_flow_imbalance: Option<f64>,
    reported_buy_share: Option<f64>,
    l2_ret_1m_bps: Option<f64>,
    cross_venue_basis_bps: Option<f64>,
    cross_venue_spread_diff_bps: Option<f64>,
    cross_venue_activity_ratio: Option<f64>,
    cross_venue_microprice_disagreement_bps: Option<f64>,
    ctx_bonk_close: Option<f64>,
    ctx_bonk_ret_1m_bps: Option<f64>,
    ctx_market_ret_15m_bps: Option<f64>,
    ctx_market_ret_60m_bps: Option<f64>,
    ctx_market_ret_240m_bps: Option<f64>,
    ctx_meme_ret_15m_bps: Option<f64>,
    ctx_meme_ret_60m_bps: Option<f64>,
    ctx_meme_ret_240m_bps: Option<f64>,
    ctx_sol_ret_15m_bps: Option<f64>,
    ctx_sol_ret_60m_bps: Option<f64>,
    ctx_sol_ret_240m_bps: Option<f64>,
    ctx_bonk_rel_market_bps: Option<f64>,
    ctx_bonk_rel_meme_bps: Option<f64>,
    ctx_bonk_rel_sol_bps: Option<f64>,
    ctx_bonk_rv_15m_bps: Option<f64>,
    ctx_bonk_rv_1h_bps: Option<f64>,
    ctx_bonk_rv_4h_bps: Option<f64>,
    ctx_bonk_rv_12h_bps: Option<f64>,
    ctx_market_rv_1h_bps: Option<f64>,
    ctx_meme_rv_1h_bps: Option<f64>,
    ctx_sol_rv_1h_bps: Option<f64>,
    ctx_bonk_beta_market_60m: Option<f64>,
    ctx_bonk_corr_market_60m: Option<f64>,
    ctx_bonk_beta_meme_60m: Option<f64>,
    ctx_bonk_corr_meme_60m: Option<f64>,
    ctx_bonk_beta_sol_60m: Option<f64>,
    ctx_bonk_corr_sol_60m: Option<f64>,
    ctx_bonk_beta_market_240m: Option<f64>,
    ctx_bonk_corr_market_240m: Option<f64>,
    ctx_bonk_beta_meme_240m: Option<f64>,
    ctx_bonk_corr_meme_240m: Option<f64>,
    ctx_bonk_beta_sol_240m: Option<f64>,
    ctx_bonk_corr_sol_240m: Option<f64>,
    bullish_avg_corr_60m: Option<f64>,
    bullish_first_eigen_share_60m: Option<f64>,
    bullish_cross_abs_ret_mean_bps: Option<f64>,
    bullish_common_mode_score: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct ControlledFactorRow {
    run_tag: String,
    fold: String,
    symbol: String,
    horizon_hours: u64,
    barrier_bps: u64,
    factor_family: String,
    factor: String,
    factor_bucket: String,
    control_set: String,
    regime_control: String,
    regime_bucket: String,
    rows: u64,
    bucket_rows: u64,
    baseline_upper_rate: Option<f64>,
    baseline_lower_rate: Option<f64>,
    factor_upper_rate: Option<f64>,
    factor_lower_rate: Option<f64>,
    edge_raw: Option<f64>,
    edge_conditional: Option<f64>,
    edge_residual: Option<f64>,
    upper_edge_minus_lower_edge: Option<f64>,
    median_resid_future_return_bps: Option<f64>,
    placebo_edge_upper: Option<f64>,
    forward_split_min_edge: Option<f64>,
    forward_split_max_edge: Option<f64>,
    non_overlap_edge_upper: Option<f64>,
    market_wide_move_flag: String,
}

#[derive(Debug, Clone, Serialize)]
struct ModelMetricRow {
    run_tag: String,
    fold: String,
    symbol: String,
    horizon_hours: u64,
    barrier_bps: u64,
    model: String,
    sample: String,
    rows: u64,
    positives: u64,
    baseline_upper_rate: Option<f64>,
    log_loss: Option<f64>,
    brier: Option<f64>,
    top_decile_lift: Option<f64>,
    upper_edge_minus_lower_edge: Option<f64>,
    median_future_return_top_decile_bps: Option<f64>,
    daily_spearman_ic: Option<f64>,
    calibration_slope: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct ModelStabilityRow {
    run_tag: String,
    fold: String,
    symbol: String,
    horizon_hours: u64,
    barrier_bps: u64,
    model: String,
    date: String,
    rows: u64,
    baseline_upper_rate: Option<f64>,
    top_decile_lift: Option<f64>,
    upper_edge_minus_lower_edge: Option<f64>,
}

#[derive(Debug, Clone)]
struct Fold {
    name: &'static str,
    train_end_us: u64,
    val_start_us: u64,
    val_end_us: u64,
}

#[derive(Debug, Clone, Copy)]
struct FeatureSpec {
    name: &'static str,
    family: &'static str,
}

const FACTORS: [FeatureSpec; 21] = [
    FeatureSpec {
        name: "snapshot_count",
        family: "activity",
    },
    FeatureSpec {
        name: "trade_count",
        family: "activity",
    },
    FeatureSpec {
        name: "book_ticker_count",
        family: "activity",
    },
    FeatureSpec {
        name: "trade_notional_quote_sum",
        family: "activity",
    },
    FeatureSpec {
        name: "spread_bps_median",
        family: "spread_liquidity",
    },
    FeatureSpec {
        name: "spread_bps_last",
        family: "spread_liquidity",
    },
    FeatureSpec {
        name: "top_depth_total_notional_median",
        family: "spread_liquidity",
    },
    FeatureSpec {
        name: "wobi5_mean",
        family: "imbalance",
    },
    FeatureSpec {
        name: "wobi25_mean",
        family: "imbalance",
    },
    FeatureSpec {
        name: "wobi5_minus_wobi25",
        family: "imbalance",
    },
    FeatureSpec {
        name: "depth_imbalance_25_mean",
        family: "imbalance",
    },
    FeatureSpec {
        name: "microprice_offset_bps_mean",
        family: "microprice",
    },
    FeatureSpec {
        name: "snapshot_microprice_offset_bps_mean",
        family: "microprice",
    },
    FeatureSpec {
        name: "reported_buy_share",
        family: "reported_flow",
    },
    FeatureSpec {
        name: "trade_flow_imbalance",
        family: "reported_flow",
    },
    FeatureSpec {
        name: "cross_venue_basis_bps",
        family: "cross_venue",
    },
    FeatureSpec {
        name: "cross_venue_spread_diff_bps",
        family: "cross_venue",
    },
    FeatureSpec {
        name: "cross_venue_activity_ratio",
        family: "cross_venue",
    },
    FeatureSpec {
        name: "cross_venue_microprice_disagreement_bps",
        family: "cross_venue",
    },
    FeatureSpec {
        name: "bullish_common_mode_score",
        family: "context",
    },
    FeatureSpec {
        name: "ctx_bonk_rv_1h_bps",
        family: "context",
    },
];

const CONTEXT_FEATURES: [&str; 31] = [
    "ctx_market_ret_15m_bps",
    "ctx_market_ret_60m_bps",
    "ctx_market_ret_240m_bps",
    "ctx_meme_ret_15m_bps",
    "ctx_meme_ret_60m_bps",
    "ctx_meme_ret_240m_bps",
    "ctx_sol_ret_15m_bps",
    "ctx_sol_ret_60m_bps",
    "ctx_sol_ret_240m_bps",
    "ctx_bonk_rel_market_bps",
    "ctx_bonk_rel_meme_bps",
    "ctx_bonk_rel_sol_bps",
    "ctx_bonk_rv_15m_bps",
    "ctx_bonk_rv_1h_bps",
    "ctx_bonk_rv_4h_bps",
    "ctx_bonk_rv_12h_bps",
    "ctx_bonk_beta_market_60m",
    "ctx_bonk_corr_market_60m",
    "ctx_bonk_beta_meme_60m",
    "ctx_bonk_corr_meme_60m",
    "ctx_bonk_beta_sol_60m",
    "ctx_bonk_corr_sol_60m",
    "ctx_bonk_beta_market_240m",
    "ctx_bonk_corr_market_240m",
    "ctx_bonk_beta_meme_240m",
    "ctx_bonk_corr_meme_240m",
    "ctx_bonk_beta_sol_240m",
    "ctx_bonk_corr_sol_240m",
    "bullish_avg_corr_60m",
    "bullish_first_eigen_share_60m",
    "bullish_cross_abs_ret_mean_bps",
];

const L2_MODEL_FEATURES: [&str; 16] = [
    "snapshot_count",
    "trade_count",
    "book_ticker_count",
    "trade_notional_quote_sum",
    "spread_bps_median",
    "spread_bps_last",
    "top_depth_total_notional_median",
    "wobi25_mean",
    "wobi5_minus_wobi25",
    "microprice_offset_bps_mean",
    "snapshot_microprice_offset_bps_mean",
    "reported_buy_share",
    "trade_flow_imbalance",
    "cross_venue_basis_bps",
    "cross_venue_spread_diff_bps",
    "cross_venue_activity_ratio",
];

pub fn run_research_panel(config: &ResearchPanelConfig) -> Result<ResearchPanelSummary> {
    let paths = panel_paths(config);
    for path in [
        &paths.panel,
        &paths.controlled_factor_csv,
        &paths.panel_completion_json,
    ] {
        ensure_parent_dir(path)?;
    }

    eprintln!("[bonk_cex_research_panel] read inputs");
    let state = read_state_rows(&paths.state)?;
    let labels = read_label_rows(&paths.labels)?;
    let covariance = read_cov_rows(&paths.covariance)?;
    let price_context = read_price_context_rows(&paths.price_context)?;

    eprintln!("[bonk_cex_research_panel] build panel");
    let panel = build_panel(config, &state, &labels, &covariance, &price_context)?;
    let duplicate_keys = count_panel_duplicate_keys(&panel);
    let price_context_missing = panel
        .iter()
        .filter(|row| row.ctx_bonk_close.is_none())
        .count();

    eprintln!("[bonk_cex_research_panel] controlled diagnostics");
    let controlled = build_controlled_factor_tests(&config.run_tag, &panel)?;

    eprintln!("[bonk_cex_research_panel] write outputs");
    write_panel_parquet(&paths.panel, &panel)?;
    write_csv_atomic(&paths.controlled_factor_csv, &controlled)?;
    let summary = ResearchPanelSummary {
        run_tag: config.run_tag.clone(),
        panel_rows: panel.len(),
        controlled_factor_rows: controlled.len(),
        input_label_rows: labels.len(),
        panel_duplicate_keys: duplicate_keys,
        price_context_missing_rows: price_context_missing,
        panel_parquet: path_string(&paths.panel),
        controlled_factor_csv: path_string(&paths.controlled_factor_csv),
        completion_json: path_string(&paths.panel_completion_json),
    };
    write_json_atomic(&paths.panel_completion_json, &summary)?;
    Ok(summary)
}

pub fn run_model_report(config: &ModelReportConfig) -> Result<ModelReportSummary> {
    let paths = model_paths(config);
    for path in [
        &paths.metrics_csv,
        &paths.stability_csv,
        &paths.report_md,
        &paths.completion_json,
    ] {
        ensure_parent_dir(path)?;
    }
    if !paths.panel.exists() {
        bail!(
            "research panel not found at {}; run bonk_cex_research_panel first",
            paths.panel.display()
        );
    }
    eprintln!("[bonk_cex_model_report] read panel");
    let panel = read_panel_rows(&paths.panel)?;
    eprintln!("[bonk_cex_model_report] run models");
    let (metrics, stability) = build_model_metrics(&config.run_tag, &panel)?;
    write_csv_atomic(&paths.metrics_csv, &metrics)?;
    write_csv_atomic(&paths.stability_csv, &stability)?;
    render_model_report(config, &paths, &metrics, &stability)?;
    let summary = ModelReportSummary {
        run_tag: config.run_tag.clone(),
        metric_rows: metrics.len(),
        stability_rows: stability.len(),
        metrics_csv: path_string(&paths.metrics_csv),
        stability_csv: path_string(&paths.stability_csv),
        report_md: path_string(&paths.report_md),
        completion_json: path_string(&paths.completion_json),
    };
    write_json_atomic(&paths.completion_json, &summary)?;
    Ok(summary)
}

fn build_panel(
    config: &ResearchPanelConfig,
    state: &[StateRow],
    labels: &[LabelRow],
    covariance: &[CovRow],
    price_context: &[PriceContextRow],
) -> Result<Vec<PanelRow>> {
    let state_by_key = state
        .iter()
        .map(|row| ((row.symbol.clone(), row.timestamp_us), row))
        .collect::<HashMap<_, _>>();
    let cov_by_ts = covariance
        .iter()
        .map(|row| (row.timestamp_us, row))
        .collect::<HashMap<_, _>>();
    let ctx_by_ts = price_context
        .iter()
        .map(|row| (row.timestamp_us, row))
        .collect::<HashMap<_, _>>();
    let trailing = build_trailing_context(price_context);
    let horizons = labels
        .iter()
        .map(|row| row.horizon_hours)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let future = build_future_context(price_context, &horizons);
    let cov_stats = CovStats::fit(covariance);

    let mut out = Vec::with_capacity(labels.len());
    for label in labels {
        let Some(st) = state_by_key.get(&(label.symbol.clone(), label.timestamp_us)) else {
            continue;
        };
        let ctx = ctx_by_ts.get(&label.timestamp_us).copied();
        let tr = trailing
            .get(&label.timestamp_us)
            .cloned()
            .unwrap_or_default();
        let fut = future
            .get(&(label.timestamp_us, label.horizon_hours))
            .cloned()
            .unwrap_or_default();
        let cov = cov_by_ts.get(&label.timestamp_us).copied();
        let quote = quote_from_symbol(&label.symbol);
        let other_symbol = if label.symbol == "BONK1MUSDC" {
            "BONK1MUSDT"
        } else {
            "BONK1MUSDC"
        };
        let other = state_by_key.get(&(other_symbol.to_string(), label.timestamp_us));
        let top_depth_total = st
            .top_depth_bid_notional_median
            .zip(st.top_depth_ask_notional_median)
            .and_then(|(a, b)| finite(a + b));
        let future_rel_market = diff_opt(label.future_return_bps, fut.market_return_bps);
        let future_rel_meme = diff_opt(label.future_return_bps, fut.meme_return_bps);
        let future_rel_sol = diff_opt(label.future_return_bps, fut.sol_return_bps);
        let future_resid = label
            .future_return_bps
            .zip(mean_opt(&[
                fut.market_return_bps,
                fut.meme_return_bps,
                fut.sol_return_bps,
            ]))
            .and_then(|(raw, common)| finite(raw - common));
        let vol_barrier = ctx
            .and_then(|row| row.rv_1h_bps)
            .map(|rv| (rv * (label.horizon_hours as f64).sqrt()).clamp(50.0, 300.0));
        let vol_hit = vol_adj_hit(
            vol_barrier,
            label.mfe_up_bps,
            label.mae_down_bps,
            &label.label_status,
        );
        let cross = build_cross_venue(st, other.copied());
        let common_score = cov.and_then(|row| cov_stats.score(row));
        out.push(PanelRow {
            run_tag: config.run_tag.clone(),
            timestamp_utc: label.timestamp_utc.clone(),
            timestamp_us: label.timestamp_us,
            symbol: label.symbol.clone(),
            asset: label.asset.clone(),
            quote,
            horizon_hours: label.horizon_hours,
            barrier_bps: label.barrier_bps,
            label_status: label.label_status.clone(),
            barrier_first_hit: label.barrier_first_hit.clone(),
            price_per_token: label.price_per_token,
            future_return_bps: label.future_return_bps,
            mfe_up_bps: label.mfe_up_bps,
            mae_down_bps: label.mae_down_bps,
            future_ctx_market_return_bps: fut.market_return_bps,
            future_ctx_meme_return_bps: fut.meme_return_bps,
            future_ctx_sol_return_bps: fut.sol_return_bps,
            future_ctx_bonk_binance_return_bps: fut.bonk_binance_return_bps,
            future_bonk_rel_market_bps: future_rel_market,
            future_bonk_rel_meme_bps: future_rel_meme,
            future_bonk_rel_sol_bps: future_rel_sol,
            future_resid_mkt_meme_sol_bps: future_resid,
            residual_positive_flag: future_resid.map(|value| if value > 0.0 { 1.0 } else { 0.0 }),
            vol_adj_barrier_bps: vol_barrier,
            vol_adj_barrier_first_hit: vol_hit,
            book_ticker_count: st.book_ticker_count,
            snapshot_count: st.snapshot_count,
            trade_count: st.trade_count,
            trade_notional_quote_sum: st.trade_notional_quote_sum,
            spread_bps_median: st.spread_bps_median,
            spread_bps_last: st.spread_bps_last,
            top_depth_bid_notional_median: st.top_depth_bid_notional_median,
            top_depth_ask_notional_median: st.top_depth_ask_notional_median,
            top_depth_total_notional_median: top_depth_total,
            microprice_offset_bps_mean: st.microprice_offset_bps_mean,
            snapshot_spread_bps_median: st.snapshot_spread_bps_median,
            snapshot_microprice_offset_bps_mean: st.snapshot_microprice_offset_bps_mean,
            wobi5_mean: st.wobi5_mean,
            wobi25_mean: st.wobi25_mean,
            wobi5_minus_wobi25: st
                .wobi5_mean
                .zip(st.wobi25_mean)
                .and_then(|(a, b)| finite(a - b)),
            depth_imbalance_5_mean: st.depth_imbalance_5_mean,
            depth_imbalance_25_mean: st.depth_imbalance_25_mean,
            depth_bid_notional_5_median: st.depth_bid_notional_5_median,
            depth_ask_notional_5_median: st.depth_ask_notional_5_median,
            depth_bid_notional_25_median: st.depth_bid_notional_25_median,
            depth_ask_notional_25_median: st.depth_ask_notional_25_median,
            trade_flow_imbalance: st.trade_flow_imbalance,
            reported_buy_share: st.reported_buy_share,
            l2_ret_1m_bps: st.ret_1m_bps,
            cross_venue_basis_bps: cross.basis_bps,
            cross_venue_spread_diff_bps: cross.spread_diff_bps,
            cross_venue_activity_ratio: cross.activity_ratio,
            cross_venue_microprice_disagreement_bps: cross.microprice_disagreement_bps,
            ctx_bonk_close: ctx.map(|row| row.close),
            ctx_bonk_ret_1m_bps: ctx.and_then(|row| row.ret_1m_bps),
            ctx_market_ret_15m_bps: tr.market_ret_15m_bps,
            ctx_market_ret_60m_bps: tr.market_ret_60m_bps,
            ctx_market_ret_240m_bps: tr.market_ret_240m_bps,
            ctx_meme_ret_15m_bps: tr.meme_ret_15m_bps,
            ctx_meme_ret_60m_bps: tr.meme_ret_60m_bps,
            ctx_meme_ret_240m_bps: tr.meme_ret_240m_bps,
            ctx_sol_ret_15m_bps: tr.sol_ret_15m_bps,
            ctx_sol_ret_60m_bps: tr.sol_ret_60m_bps,
            ctx_sol_ret_240m_bps: tr.sol_ret_240m_bps,
            ctx_bonk_rel_market_bps: ctx.and_then(|row| row.bonk_rel_market_bps),
            ctx_bonk_rel_meme_bps: ctx.and_then(|row| row.bonk_rel_meme_bps),
            ctx_bonk_rel_sol_bps: ctx.and_then(|row| row.bonk_rel_sol_bps),
            ctx_bonk_rv_15m_bps: ctx.and_then(|row| row.rv_15m_bps),
            ctx_bonk_rv_1h_bps: ctx.and_then(|row| row.rv_1h_bps),
            ctx_bonk_rv_4h_bps: ctx.and_then(|row| row.rv_4h_bps),
            ctx_bonk_rv_12h_bps: ctx.and_then(|row| row.rv_12h_bps),
            ctx_market_rv_1h_bps: tr.market_rv_1h_bps,
            ctx_meme_rv_1h_bps: tr.meme_rv_1h_bps,
            ctx_sol_rv_1h_bps: tr.sol_rv_1h_bps,
            ctx_bonk_beta_market_60m: ctx.and_then(|row| row.bonk_beta_market_60m),
            ctx_bonk_corr_market_60m: ctx.and_then(|row| row.bonk_corr_market_60m),
            ctx_bonk_beta_meme_60m: ctx.and_then(|row| row.bonk_beta_meme_60m),
            ctx_bonk_corr_meme_60m: ctx.and_then(|row| row.bonk_corr_meme_60m),
            ctx_bonk_beta_sol_60m: ctx.and_then(|row| row.bonk_beta_sol_60m),
            ctx_bonk_corr_sol_60m: ctx.and_then(|row| row.bonk_corr_sol_60m),
            ctx_bonk_beta_market_240m: ctx.and_then(|row| row.bonk_beta_market_240m),
            ctx_bonk_corr_market_240m: ctx.and_then(|row| row.bonk_corr_market_240m),
            ctx_bonk_beta_meme_240m: ctx.and_then(|row| row.bonk_beta_meme_240m),
            ctx_bonk_corr_meme_240m: ctx.and_then(|row| row.bonk_corr_meme_240m),
            ctx_bonk_beta_sol_240m: ctx.and_then(|row| row.bonk_beta_sol_240m),
            ctx_bonk_corr_sol_240m: ctx.and_then(|row| row.bonk_corr_sol_240m),
            bullish_avg_corr_60m: cov.and_then(|row| row.avg_corr_60m),
            bullish_first_eigen_share_60m: cov.and_then(|row| row.first_eigen_share_60m),
            bullish_cross_abs_ret_mean_bps: cov.and_then(|row| row.cross_symbol_abs_ret_mean_bps),
            bullish_common_mode_score: common_score,
        });
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.timestamp_us.cmp(&b.timestamp_us))
            .then_with(|| a.horizon_hours.cmp(&b.horizon_hours))
            .then_with(|| a.barrier_bps.cmp(&b.barrier_bps))
    });
    Ok(out)
}

fn build_trailing_context(rows: &[PriceContextRow]) -> HashMap<u64, TrailingContext> {
    let mut out = HashMap::new();
    for idx in 0..rows.len() {
        out.insert(
            rows[idx].timestamp_us,
            TrailingContext {
                market_ret_15m_bps: trailing_sum(rows, idx, 15, |row| row.market_return_bps),
                market_ret_60m_bps: trailing_sum(rows, idx, 60, |row| row.market_return_bps),
                market_ret_240m_bps: trailing_sum(rows, idx, 240, |row| row.market_return_bps),
                meme_ret_15m_bps: trailing_sum(rows, idx, 15, |row| row.meme_return_bps),
                meme_ret_60m_bps: trailing_sum(rows, idx, 60, |row| row.meme_return_bps),
                meme_ret_240m_bps: trailing_sum(rows, idx, 240, |row| row.meme_return_bps),
                sol_ret_15m_bps: trailing_sum(rows, idx, 15, |row| row.sol_return_bps),
                sol_ret_60m_bps: trailing_sum(rows, idx, 60, |row| row.sol_return_bps),
                sol_ret_240m_bps: trailing_sum(rows, idx, 240, |row| row.sol_return_bps),
                market_rv_1h_bps: trailing_rv(rows, idx, 60, |row| row.market_return_bps),
                meme_rv_1h_bps: trailing_rv(rows, idx, 60, |row| row.meme_return_bps),
                sol_rv_1h_bps: trailing_rv(rows, idx, 60, |row| row.sol_return_bps),
            },
        );
    }
    out
}

fn build_future_context(
    rows: &[PriceContextRow],
    horizons: &[u64],
) -> HashMap<(u64, u64), FutureContext> {
    let mut out = HashMap::new();
    for idx in 0..rows.len() {
        for horizon in horizons {
            let window = (*horizon * 60) as usize;
            out.insert(
                (rows[idx].timestamp_us, *horizon),
                FutureContext {
                    market_return_bps: future_sum(rows, idx, window, |row| row.market_return_bps),
                    meme_return_bps: future_sum(rows, idx, window, |row| row.meme_return_bps),
                    sol_return_bps: future_sum(rows, idx, window, |row| row.sol_return_bps),
                    bonk_binance_return_bps: future_sum(rows, idx, window, |row| row.ret_1m_bps),
                },
            );
        }
    }
    out
}

fn trailing_sum<F>(rows: &[PriceContextRow], idx: usize, window: usize, f: F) -> Option<f64>
where
    F: Fn(&PriceContextRow) -> Option<f64>,
{
    let start = (idx + 1).saturating_sub(window);
    let mut sum = 0.0;
    let mut count = 0usize;
    for row in rows.iter().take(idx + 1).skip(start) {
        sum += f(row)?;
        count += 1;
    }
    (count >= window.min(15)).then_some(sum).and_then(finite)
}

fn trailing_rv<F>(rows: &[PriceContextRow], idx: usize, window: usize, f: F) -> Option<f64>
where
    F: Fn(&PriceContextRow) -> Option<f64>,
{
    let start = (idx + 1).saturating_sub(window);
    let mut sum_sq = 0.0;
    let mut count = 0usize;
    for row in rows.iter().take(idx + 1).skip(start) {
        let value = f(row)?;
        sum_sq += value * value;
        count += 1;
    }
    (count >= window.min(15))
        .then_some(sum_sq.sqrt())
        .and_then(finite)
}

fn future_sum<F>(rows: &[PriceContextRow], idx: usize, window: usize, f: F) -> Option<f64>
where
    F: Fn(&PriceContextRow) -> Option<f64>,
{
    if idx + window >= rows.len() {
        return None;
    }
    let expected_ts = rows[idx].timestamp_us + (window as u64 * MINUTE_US);
    if rows[idx + window].timestamp_us != expected_ts {
        return None;
    }
    let mut sum = 0.0;
    for row in rows.iter().take(idx + window + 1).skip(idx + 1) {
        sum += f(row)?;
    }
    finite(sum)
}

#[derive(Debug, Clone, Default)]
struct CrossVenue {
    basis_bps: Option<f64>,
    spread_diff_bps: Option<f64>,
    activity_ratio: Option<f64>,
    microprice_disagreement_bps: Option<f64>,
}

fn build_cross_venue(row: &StateRow, other: Option<&StateRow>) -> CrossVenue {
    let Some(other) = other else {
        return CrossVenue::default();
    };
    let basis_bps = match (
        row.symbol.as_str(),
        row.mid_price_per_token_close,
        other.mid_price_per_token_close,
    ) {
        ("BONK1MUSDC", Some(this), Some(that)) if this > 0.0 && that > 0.0 => {
            finite((this / that - 1.0) * 10_000.0)
        }
        ("BONK1MUSDT", Some(this), Some(that)) if this > 0.0 && that > 0.0 => {
            finite((that / this - 1.0) * 10_000.0)
        }
        _ => None,
    };
    let activity = row.book_ticker_count + row.snapshot_count + row.trade_count;
    let other_activity = other.book_ticker_count + other.snapshot_count + other.trade_count;
    CrossVenue {
        basis_bps,
        spread_diff_bps: row
            .spread_bps_median
            .zip(other.spread_bps_median)
            .and_then(|(a, b)| finite(a - b)),
        activity_ratio: (other_activity > 0)
            .then_some(activity as f64 / other_activity as f64)
            .and_then(finite),
        microprice_disagreement_bps: row
            .microprice_offset_bps_mean
            .zip(other.microprice_offset_bps_mean)
            .and_then(|(a, b)| finite(a - b)),
    }
}

#[derive(Debug, Clone)]
struct CovStats {
    avg_corr: ZStat,
    eigen: ZStat,
    cross_abs: ZStat,
}

impl CovStats {
    fn fit(rows: &[CovRow]) -> Self {
        Self {
            avg_corr: ZStat::fit(rows.iter().filter_map(|row| row.avg_corr_60m)),
            eigen: ZStat::fit(rows.iter().filter_map(|row| row.first_eigen_share_60m)),
            cross_abs: ZStat::fit(
                rows.iter()
                    .filter_map(|row| row.cross_symbol_abs_ret_mean_bps),
            ),
        }
    }

    fn score(&self, row: &CovRow) -> Option<f64> {
        mean_opt(&[
            row.avg_corr_60m.and_then(|v| self.avg_corr.z(v)),
            row.first_eigen_share_60m.and_then(|v| self.eigen.z(v)),
            row.cross_symbol_abs_ret_mean_bps
                .and_then(|v| self.cross_abs.z(v)),
        ])
    }
}

#[derive(Debug, Clone, Default)]
struct ZStat {
    mean: f64,
    std: f64,
}

impl ZStat {
    fn fit(values: impl Iterator<Item = f64>) -> Self {
        let values = values.filter_map(finite).collect::<Vec<_>>();
        let mean = mean(&values).unwrap_or(0.0);
        let var = values
            .iter()
            .map(|value| (value - mean) * (value - mean))
            .sum::<f64>()
            / values.len().max(1) as f64;
        Self {
            mean,
            std: var.sqrt().max(1e-12),
        }
    }

    fn z(&self, value: f64) -> Option<f64> {
        finite((value - self.mean) / self.std)
    }
}

fn build_controlled_factor_tests(
    run_tag: &str,
    panel: &[PanelRow],
) -> Result<Vec<ControlledFactorRow>> {
    let folds = folds()?;
    let mut out = Vec::new();
    for fold in folds {
        for symbol in ["BONK1MUSDC", "BONK1MUSDT"] {
            for horizon in [1u64, 4, 12] {
                for barrier in [50u64, 100, 200, 300] {
                    let train = panel
                        .iter()
                        .filter(|row| {
                            row.symbol == symbol
                                && row.horizon_hours == horizon
                                && row.barrier_bps == barrier
                                && row.label_status == "ok"
                                && row.timestamp_us <= fold.train_end_us
                        })
                        .collect::<Vec<_>>();
                    let val = panel
                        .iter()
                        .filter(|row| {
                            row.symbol == symbol
                                && row.horizon_hours == horizon
                                && row.barrier_bps == barrier
                                && row.label_status == "ok"
                                && row.timestamp_us >= fold.val_start_us
                                && row.timestamp_us <= fold.val_end_us
                        })
                        .collect::<Vec<_>>();
                    if train.len() < 100 || val.len() < 30 {
                        continue;
                    }
                    for factor in FACTORS {
                        let Some(thresholds) = BucketThresholds::fit(
                            train
                                .iter()
                                .filter_map(|row| feature_value(row, factor.name)),
                        ) else {
                            continue;
                        };
                        for (control_name, control_value) in control_specs() {
                            let control_thresholds = if control_name == "all" {
                                None
                            } else {
                                BucketThresholds::fit(
                                    train
                                        .iter()
                                        .filter_map(|row| feature_value(row, control_value)),
                                )
                            };
                            for control_bucket in if control_name == "all" {
                                vec!["all"]
                            } else {
                                vec!["low", "mid", "high"]
                            } {
                                let subset = val
                                    .iter()
                                    .copied()
                                    .filter(|row| {
                                        if control_name == "all" {
                                            true
                                        } else {
                                            control_thresholds
                                                .as_ref()
                                                .and_then(|t| {
                                                    feature_value(row, control_value)
                                                        .map(|v| t.bucket(v))
                                                })
                                                .as_deref()
                                                == Some(control_bucket)
                                        }
                                    })
                                    .collect::<Vec<_>>();
                                if subset.len() < 30 {
                                    continue;
                                }
                                for factor_bucket in ["high", "low"] {
                                    let raw_stats = factor_bucket_stats(
                                        &val,
                                        factor.name,
                                        factor_bucket,
                                        &thresholds,
                                    );
                                    let placebo_edge =
                                        placebo_edge(&val, factor.name, factor_bucket, &thresholds);
                                    let (split_min, split_max) = forward_split_edges(
                                        &val,
                                        factor.name,
                                        factor_bucket,
                                        &thresholds,
                                    );
                                    let non_overlap_edge = non_overlap_edge(
                                        &val,
                                        factor.name,
                                        factor_bucket,
                                        &thresholds,
                                        horizon,
                                    );
                                    let stats = factor_bucket_stats(
                                        &subset,
                                        factor.name,
                                        factor_bucket,
                                        &thresholds,
                                    );
                                    if stats.bucket_rows == 0 {
                                        continue;
                                    }
                                    let mut flags = Vec::new();
                                    if stats.edge_upper.unwrap_or(0.0) > 0.0
                                        && stats.edge_residual.unwrap_or(0.0) <= 0.0
                                    {
                                        flags.push("market_wide_move_likely");
                                    }
                                    if stats.edge_upper.unwrap_or(0.0) > 0.0
                                        && stats.edge_lower.unwrap_or(0.0) > 0.0
                                    {
                                        flags.push("path_width_not_direction");
                                    }
                                    if let (Some(edge), Some(placebo)) =
                                        (raw_stats.edge_upper, placebo_edge)
                                    {
                                        if edge.abs() > 1e-12 && placebo.abs() > edge.abs() * 0.30 {
                                            flags.push("regime_persistence_confounded");
                                        }
                                    }
                                    out.push(ControlledFactorRow {
                                        run_tag: run_tag.to_string(),
                                        fold: fold.name.to_string(),
                                        symbol: symbol.to_string(),
                                        horizon_hours: horizon,
                                        barrier_bps: barrier,
                                        factor_family: factor.family.to_string(),
                                        factor: factor.name.to_string(),
                                        factor_bucket: factor_bucket.to_string(),
                                        control_set: control_name.to_string(),
                                        regime_control: control_value.to_string(),
                                        regime_bucket: control_bucket.to_string(),
                                        rows: subset.len() as u64,
                                        bucket_rows: stats.bucket_rows,
                                        baseline_upper_rate: stats.baseline_upper_rate,
                                        baseline_lower_rate: stats.baseline_lower_rate,
                                        factor_upper_rate: stats.bucket_upper_rate,
                                        factor_lower_rate: stats.bucket_lower_rate,
                                        edge_raw: raw_stats.edge_upper,
                                        edge_conditional: stats.edge_upper,
                                        edge_residual: stats.edge_residual,
                                        upper_edge_minus_lower_edge: stats
                                            .edge_upper
                                            .zip(stats.edge_lower)
                                            .and_then(|(u, l)| finite(u - l)),
                                        median_resid_future_return_bps: stats
                                            .median_resid_future_return_bps,
                                        placebo_edge_upper: placebo_edge,
                                        forward_split_min_edge: split_min,
                                        forward_split_max_edge: split_max,
                                        non_overlap_edge_upper: non_overlap_edge,
                                        market_wide_move_flag: if flags.is_empty() {
                                            "none".to_string()
                                        } else {
                                            flags.join("|")
                                        },
                                    });
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    Ok(out)
}

#[derive(Debug, Clone, Copy)]
struct BucketThresholds {
    low_cut: f64,
    high_cut: f64,
}

impl BucketThresholds {
    fn fit(values: impl Iterator<Item = f64>) -> Option<Self> {
        let mut values = values.filter_map(finite).collect::<Vec<_>>();
        values.sort_by(|a, b| a.total_cmp(b));
        values.dedup_by(|a, b| (*a - *b).abs() < 1e-12);
        if values.len() < 3 {
            return None;
        }
        let low_cut = quantile_sorted(&values, 1.0 / 3.0)?;
        let high_cut = quantile_sorted(&values, 2.0 / 3.0)?;
        Some(Self { low_cut, high_cut })
    }

    fn bucket(&self, value: f64) -> String {
        if value <= self.low_cut {
            "low".to_string()
        } else if value >= self.high_cut {
            "high".to_string()
        } else {
            "mid".to_string()
        }
    }
}

#[derive(Debug, Clone, Default)]
struct BucketStats {
    bucket_rows: u64,
    baseline_upper_rate: Option<f64>,
    baseline_lower_rate: Option<f64>,
    bucket_upper_rate: Option<f64>,
    bucket_lower_rate: Option<f64>,
    edge_upper: Option<f64>,
    edge_lower: Option<f64>,
    edge_residual: Option<f64>,
    median_resid_future_return_bps: Option<f64>,
}

fn factor_bucket_stats(
    rows: &[&PanelRow],
    factor: &str,
    bucket: &str,
    thresholds: &BucketThresholds,
) -> BucketStats {
    let clean = rows
        .iter()
        .copied()
        .filter(|row| feature_value(row, factor).is_some())
        .collect::<Vec<_>>();
    let bucket_rows = clean
        .iter()
        .copied()
        .filter(|row| {
            feature_value(row, factor)
                .map(|value| thresholds.bucket(value) == bucket)
                .unwrap_or(false)
        })
        .collect::<Vec<_>>();
    let baseline_upper = rate(
        clean.iter().map(|row| row.barrier_first_hit.as_str()),
        "upper_first",
    );
    let baseline_lower = rate(
        clean.iter().map(|row| row.barrier_first_hit.as_str()),
        "lower_first",
    );
    let bucket_upper = rate(
        bucket_rows.iter().map(|row| row.barrier_first_hit.as_str()),
        "upper_first",
    );
    let bucket_lower = rate(
        bucket_rows.iter().map(|row| row.barrier_first_hit.as_str()),
        "lower_first",
    );
    let baseline_resid = mean_opt(
        &clean
            .iter()
            .map(|row| row.residual_positive_flag)
            .collect::<Vec<_>>(),
    );
    let bucket_resid = mean_opt(
        &bucket_rows
            .iter()
            .map(|row| row.residual_positive_flag)
            .collect::<Vec<_>>(),
    );
    BucketStats {
        bucket_rows: bucket_rows.len() as u64,
        baseline_upper_rate: baseline_upper,
        baseline_lower_rate: baseline_lower,
        bucket_upper_rate: bucket_upper,
        bucket_lower_rate: bucket_lower,
        edge_upper: diff_opt(bucket_upper, baseline_upper),
        edge_lower: diff_opt(bucket_lower, baseline_lower),
        edge_residual: diff_opt(bucket_resid, baseline_resid),
        median_resid_future_return_bps: median(
            bucket_rows
                .iter()
                .filter_map(|row| row.future_resid_mkt_meme_sol_bps)
                .collect(),
        ),
    }
}

fn placebo_edge(
    rows: &[&PanelRow],
    factor: &str,
    bucket: &str,
    thresholds: &BucketThresholds,
) -> Option<f64> {
    let mut rows = rows.to_vec();
    rows.sort_by_key(|row| row.timestamp_us);
    if rows.len() <= 60 {
        return None;
    }
    let shifted = (60..rows.len())
        .filter_map(|idx| feature_value(rows[idx - 60], factor).map(|v| (rows[idx], v)))
        .collect::<Vec<_>>();
    let baseline = rate(
        shifted
            .iter()
            .map(|(row, _)| row.barrier_first_hit.as_str()),
        "upper_first",
    );
    let selected = shifted
        .iter()
        .filter(|(_, value)| thresholds.bucket(*value) == bucket)
        .map(|(row, _)| *row)
        .collect::<Vec<_>>();
    let selected_rate = rate(
        selected.iter().map(|row| row.barrier_first_hit.as_str()),
        "upper_first",
    );
    diff_opt(selected_rate, baseline)
}

fn forward_split_edges(
    rows: &[&PanelRow],
    factor: &str,
    bucket: &str,
    thresholds: &BucketThresholds,
) -> (Option<f64>, Option<f64>) {
    if rows.len() < 2 {
        return (None, None);
    }
    let mut rows = rows.to_vec();
    rows.sort_by_key(|row| row.timestamp_us);
    let mid = rows.len() / 2;
    let edges = [&rows[..mid], &rows[mid..]]
        .iter()
        .filter_map(|sub| {
            let sub = sub.to_vec();
            let stats = factor_bucket_stats(&sub, factor, bucket, thresholds);
            stats.edge_upper
        })
        .collect::<Vec<_>>();
    if edges.is_empty() {
        return (None, None);
    }
    (
        edges.iter().copied().min_by(|a, b| a.total_cmp(b)),
        edges.iter().copied().max_by(|a, b| a.total_cmp(b)),
    )
}

fn non_overlap_edge(
    rows: &[&PanelRow],
    factor: &str,
    bucket: &str,
    thresholds: &BucketThresholds,
    horizon_hours: u64,
) -> Option<f64> {
    let mut rows = rows.to_vec();
    rows.sort_by_key(|row| row.timestamp_us);
    let step = (horizon_hours * 60).max(1) as usize;
    let sampled = rows.into_iter().step_by(step).collect::<Vec<_>>();
    let stats = factor_bucket_stats(&sampled, factor, bucket, thresholds);
    stats.edge_upper
}

fn control_specs() -> Vec<(&'static str, &'static str)> {
    vec![
        ("all", "all"),
        ("control_market_momentum_bucket", "ctx_market_ret_60m_bps"),
        ("control_meme_momentum_bucket", "ctx_meme_ret_60m_bps"),
        ("control_sol_momentum_bucket", "ctx_sol_ret_60m_bps"),
        ("control_bonk_rel_meme_bucket", "ctx_bonk_rel_meme_bps"),
        ("control_bonk_rv_bucket", "ctx_bonk_rv_1h_bps"),
        ("control_common_mode_bucket", "bullish_common_mode_score"),
    ]
}

fn build_model_metrics(
    run_tag: &str,
    panel: &[PanelRow],
) -> Result<(Vec<ModelMetricRow>, Vec<ModelStabilityRow>)> {
    let folds = folds()?;
    let mut metrics = Vec::new();
    let mut stability = Vec::new();
    for fold in folds {
        for symbol in ["BONK1MUSDC", "BONK1MUSDT"] {
            for horizon in [1u64, 4] {
                let barrier = 100u64;
                let train = panel
                    .iter()
                    .filter(|row| {
                        row.symbol == symbol
                            && row.horizon_hours == horizon
                            && row.barrier_bps == barrier
                            && row.label_status == "ok"
                            && row.timestamp_us <= fold.train_end_us
                    })
                    .collect::<Vec<_>>();
                let val = panel
                    .iter()
                    .filter(|row| {
                        row.symbol == symbol
                            && row.horizon_hours == horizon
                            && row.barrier_bps == barrier
                            && row.label_status == "ok"
                            && row.timestamp_us >= fold.val_start_us
                            && row.timestamp_us <= fold.val_end_us
                    })
                    .collect::<Vec<_>>();
                if train.len() < 100 || val.len() < 50 {
                    continue;
                }
                for (model_name, features) in [
                    ("constant", Vec::<&str>::new()),
                    ("context_only_ridge_logistic", CONTEXT_FEATURES.to_vec()),
                    ("l2_only_ridge_logistic", L2_MODEL_FEATURES.to_vec()),
                    (
                        "context_plus_l2_ridge_logistic",
                        CONTEXT_FEATURES
                            .iter()
                            .chain(L2_MODEL_FEATURES.iter())
                            .copied()
                            .collect::<Vec<_>>(),
                    ),
                ] {
                    let predictions = if model_name == "constant" {
                        let p = train_upper_rate(&train).unwrap_or(0.5);
                        val.iter().map(|_| p).collect::<Vec<_>>()
                    } else {
                        let model = LogisticModel::fit(&train, &features, 1.0)?;
                        val.iter().map(|row| model.predict(row)).collect::<Vec<_>>()
                    };
                    metrics.push(eval_model_sample(
                        run_tag,
                        fold.name,
                        symbol,
                        horizon,
                        barrier,
                        model_name,
                        "full_minute",
                        &val,
                        &predictions,
                    ));
                    let (non_rows, non_preds) =
                        non_overlap_predictions(&val, &predictions, horizon);
                    metrics.push(eval_model_sample(
                        run_tag,
                        fold.name,
                        symbol,
                        horizon,
                        barrier,
                        model_name,
                        "stride_h_non_overlap",
                        &non_rows,
                        &non_preds,
                    ));
                    stability.extend(eval_model_by_day(
                        run_tag,
                        fold.name,
                        symbol,
                        horizon,
                        barrier,
                        model_name,
                        &val,
                        &predictions,
                    ));
                }
            }
        }
    }
    Ok((metrics, stability))
}

#[derive(Debug, Clone)]
struct LogisticModel {
    features: Vec<String>,
    means: Vec<f64>,
    stds: Vec<f64>,
    weights: Vec<f64>,
}

impl LogisticModel {
    fn fit(rows: &[&PanelRow], features: &[&str], ridge: f64) -> Result<Self> {
        let mut means = Vec::with_capacity(features.len());
        let mut stds = Vec::with_capacity(features.len());
        for feature in features {
            let values = rows
                .iter()
                .filter_map(|row| feature_value(row, feature))
                .collect::<Vec<_>>();
            let mean = mean(&values).unwrap_or(0.0);
            let var = values
                .iter()
                .map(|value| (value - mean) * (value - mean))
                .sum::<f64>()
                / values.len().max(1) as f64;
            means.push(mean);
            stds.push(var.sqrt().max(1e-9));
        }
        let x = rows
            .iter()
            .map(|row| z_features(row, features, &means, &stds))
            .collect::<Vec<_>>();
        let y = rows
            .iter()
            .map(|row| (row.barrier_first_hit == "upper_first") as u8 as f64)
            .collect::<Vec<_>>();
        let mut weights = vec![0.0; features.len() + 1];
        let base = y.iter().sum::<f64>() / y.len().max(1) as f64;
        weights[0] = logit(base.clamp(1e-4, 1.0 - 1e-4));
        let lr = 0.12;
        let n = y.len().max(1) as f64;
        for _ in 0..500 {
            let mut grad = vec![0.0; weights.len()];
            for (row, target) in x.iter().zip(&y) {
                let mut score = weights[0];
                for (idx, value) in row.iter().enumerate() {
                    score += weights[idx + 1] * value;
                }
                let p = sigmoid(score);
                let diff = p - target;
                grad[0] += diff;
                for (idx, value) in row.iter().enumerate() {
                    grad[idx + 1] += diff * value;
                }
            }
            for idx in 0..weights.len() {
                grad[idx] /= n;
                if idx > 0 {
                    grad[idx] += ridge * weights[idx] / n;
                }
                weights[idx] -= lr * grad[idx];
            }
        }
        Ok(Self {
            features: features.iter().map(|value| value.to_string()).collect(),
            means,
            stds,
            weights,
        })
    }

    fn predict(&self, row: &PanelRow) -> f64 {
        let features = self.features.iter().map(String::as_str).collect::<Vec<_>>();
        let x = z_features(row, &features, &self.means, &self.stds);
        let mut score = self.weights[0];
        for (idx, value) in x.iter().enumerate() {
            score += self.weights[idx + 1] * value;
        }
        sigmoid(score).clamp(1e-6, 1.0 - 1e-6)
    }
}

fn z_features(row: &PanelRow, features: &[&str], means: &[f64], stds: &[f64]) -> Vec<f64> {
    features
        .iter()
        .enumerate()
        .map(|(idx, feature)| {
            let value = feature_value(row, feature).unwrap_or(means[idx]);
            ((value - means[idx]) / stds[idx]).clamp(-5.0, 5.0)
        })
        .collect()
}

fn eval_model_sample(
    run_tag: &str,
    fold: &str,
    symbol: &str,
    horizon: u64,
    barrier: u64,
    model: &str,
    sample: &str,
    rows: &[&PanelRow],
    predictions: &[f64],
) -> ModelMetricRow {
    let y = rows
        .iter()
        .map(|row| (row.barrier_first_hit == "upper_first") as u8 as f64)
        .collect::<Vec<_>>();
    let positives = y.iter().filter(|value| **value > 0.5).count() as u64;
    let baseline = mean(&y);
    let log_loss = (!rows.is_empty()).then(|| {
        y.iter()
            .zip(predictions)
            .map(|(target, p)| {
                let p = p.clamp(1e-6, 1.0 - 1e-6);
                -(target * p.ln() + (1.0 - target) * (1.0 - p).ln())
            })
            .sum::<f64>()
            / rows.len() as f64
    });
    let brier = (!rows.is_empty()).then(|| {
        y.iter()
            .zip(predictions)
            .map(|(target, p)| (p - target) * (p - target))
            .sum::<f64>()
            / rows.len() as f64
    });
    let top = top_prediction_indexes(predictions, 0.10);
    let top_rows = top.iter().map(|idx| rows[*idx]).collect::<Vec<_>>();
    let top_upper = rate(
        top_rows.iter().map(|row| row.barrier_first_hit.as_str()),
        "upper_first",
    );
    let top_lower = rate(
        top_rows.iter().map(|row| row.barrier_first_hit.as_str()),
        "lower_first",
    );
    let base_lower = rate(
        rows.iter().map(|row| row.barrier_first_hit.as_str()),
        "lower_first",
    );
    ModelMetricRow {
        run_tag: run_tag.to_string(),
        fold: fold.to_string(),
        symbol: symbol.to_string(),
        horizon_hours: horizon,
        barrier_bps: barrier,
        model: model.to_string(),
        sample: sample.to_string(),
        rows: rows.len() as u64,
        positives,
        baseline_upper_rate: baseline,
        log_loss,
        brier,
        top_decile_lift: diff_opt(top_upper, baseline),
        upper_edge_minus_lower_edge: diff_opt(top_upper, baseline)
            .zip(diff_opt(top_lower, base_lower))
            .and_then(|(u, l)| finite(u - l)),
        median_future_return_top_decile_bps: median(
            top_rows
                .iter()
                .filter_map(|row| row.future_return_bps)
                .collect(),
        ),
        daily_spearman_ic: daily_spearman(rows, predictions),
        calibration_slope: calibration_slope(&y, predictions),
    }
}

fn eval_model_by_day(
    run_tag: &str,
    fold: &str,
    symbol: &str,
    horizon: u64,
    barrier: u64,
    model: &str,
    rows: &[&PanelRow],
    predictions: &[f64],
) -> Vec<ModelStabilityRow> {
    let mut by_day = BTreeMap::<String, Vec<(usize, &PanelRow)>>::new();
    for (idx, row) in rows.iter().enumerate() {
        by_day
            .entry(row.timestamp_utc.chars().take(10).collect())
            .or_default()
            .push((idx, *row));
    }
    by_day
        .into_iter()
        .map(|(date, group)| {
            let sub_rows = group.iter().map(|(_, row)| *row).collect::<Vec<_>>();
            let sub_preds = group
                .iter()
                .map(|(idx, _)| predictions[*idx])
                .collect::<Vec<_>>();
            let top = top_prediction_indexes(&sub_preds, 0.10);
            let top_rows = top.iter().map(|idx| sub_rows[*idx]).collect::<Vec<_>>();
            let baseline = rate(
                sub_rows.iter().map(|row| row.barrier_first_hit.as_str()),
                "upper_first",
            );
            let base_lower = rate(
                sub_rows.iter().map(|row| row.barrier_first_hit.as_str()),
                "lower_first",
            );
            let top_upper = rate(
                top_rows.iter().map(|row| row.barrier_first_hit.as_str()),
                "upper_first",
            );
            let top_lower = rate(
                top_rows.iter().map(|row| row.barrier_first_hit.as_str()),
                "lower_first",
            );
            ModelStabilityRow {
                run_tag: run_tag.to_string(),
                fold: fold.to_string(),
                symbol: symbol.to_string(),
                horizon_hours: horizon,
                barrier_bps: barrier,
                model: model.to_string(),
                date,
                rows: sub_rows.len() as u64,
                baseline_upper_rate: baseline,
                top_decile_lift: diff_opt(top_upper, baseline),
                upper_edge_minus_lower_edge: diff_opt(top_upper, baseline)
                    .zip(diff_opt(top_lower, base_lower))
                    .and_then(|(u, l)| finite(u - l)),
            }
        })
        .collect()
}

fn non_overlap_predictions<'a>(
    rows: &[&'a PanelRow],
    predictions: &[f64],
    horizon: u64,
) -> (Vec<&'a PanelRow>, Vec<f64>) {
    let mut pairs = rows
        .iter()
        .copied()
        .zip(predictions.iter().copied())
        .collect::<Vec<_>>();
    pairs.sort_by_key(|(row, _)| row.timestamp_us);
    let step = (horizon * 60).max(1) as usize;
    pairs.into_iter().step_by(step).unzip()
}

fn render_model_report(
    config: &ModelReportConfig,
    paths: &ModelPaths,
    metrics: &[ModelMetricRow],
    stability: &[ModelStabilityRow],
) -> Result<()> {
    let mut lines = Vec::new();
    lines.push("# BONK Controlled L2 Modeling Report v2".to_string());
    lines.push(String::new());
    lines.push(format!("- `run_tag`: `{}`", config.run_tag));
    lines.push(
        "- 本报告只做 market-controlled modeling diagnostics，不输出交易规则，也不声称 alpha。"
            .to_string(),
    );
    lines.push(
        "- 主任务: `1h/100bps` 与 `4h/100bps`; `12h` 仍只作为 regime/path-width 诊断。".to_string(),
    );
    lines.push("- 模型阶梯: constant baseline -> context-only ridge logistic -> L2-only ridge logistic -> context+L2 ridge logistic。".to_string());
    lines.push(String::new());
    lines.push("## Outputs".to_string());
    lines.push(String::new());
    lines.push(format!(
        "- Metrics CSV: `{}`",
        path_string(&paths.metrics_csv)
    ));
    lines.push(format!(
        "- Stability CSV: `{}`",
        path_string(&paths.stability_csv)
    ));
    lines.push(format!("- Panel parquet: `{}`", path_string(&paths.panel)));
    lines.push(String::new());
    lines.push("## Non-overlap Smoke".to_string());
    lines.push(String::new());
    lines.push("| symbol | H | fold | model | rows | logloss | brier | top decile lift | upper-lower edge | calib slope |".to_string());
    lines.push("|---|---:|---|---|---:|---:|---:|---:|---:|---:|".to_string());
    for row in metrics
        .iter()
        .filter(|row| row.sample == "stride_h_non_overlap" && row.barrier_bps == 100)
    {
        lines.push(format!(
            "| {} | {}h | {} | `{}` | {} | {} | {} | {} | {} | {} |",
            row.symbol,
            row.horizon_hours,
            row.fold,
            row.model,
            row.rows,
            fmt_num(row.log_loss, 4),
            fmt_num(row.brier, 4),
            fmt_pct(row.top_decile_lift),
            fmt_pct(row.upper_edge_minus_lower_edge),
            fmt_num(row.calibration_slope, 3)
        ));
    }
    lines.push(String::new());
    lines.push("## Interpretation Guardrails".to_string());
    lines.push(String::new());
    lines.push("- `context+L2` 必须在 Fold 2/3 的 non-overlap 上稳定优于 `context-only`，否则只保留为现象诊断。".to_string());
    lines.push("- 若 top-decile 同时提高 upper 与 lower first-passage，则标记为 path-width 状态，不解释为方向性。".to_string());
    lines.push("- Binance/Bullish context 只使用 t 及以前信息；future market/meme/SOL 只用于 residual labels 和事后归因。".to_string());
    lines.push(String::new());
    lines.push("## Acceptance Read".to_string());
    lines.push(String::new());
    lines.push("| symbol | H | fold | context+L2 vs context-only | logloss delta | brier delta | top-decile lift delta |".to_string());
    lines.push("|---|---:|---|---|---:|---:|---:|".to_string());
    let mut stable_wins = 0usize;
    let mut stable_cases = 0usize;
    for fold in ["fold2", "fold3"] {
        for symbol in ["BONK1MUSDC", "BONK1MUSDT"] {
            for horizon in [1u64, 4] {
                let ctx = metrics.iter().find(|row| {
                    row.sample == "stride_h_non_overlap"
                        && row.fold == fold
                        && row.symbol == symbol
                        && row.horizon_hours == horizon
                        && row.barrier_bps == 100
                        && row.model == "context_only_ridge_logistic"
                });
                let combined = metrics.iter().find(|row| {
                    row.sample == "stride_h_non_overlap"
                        && row.fold == fold
                        && row.symbol == symbol
                        && row.horizon_hours == horizon
                        && row.barrier_bps == 100
                        && row.model == "context_plus_l2_ridge_logistic"
                });
                let logloss_delta = combined
                    .and_then(|c| c.log_loss.zip(ctx.and_then(|r| r.log_loss)))
                    .and_then(|(c, base)| finite(c - base));
                let brier_delta = combined
                    .and_then(|c| c.brier.zip(ctx.and_then(|r| r.brier)))
                    .and_then(|(c, base)| finite(c - base));
                let lift_delta = combined
                    .and_then(|c| c.top_decile_lift.zip(ctx.and_then(|r| r.top_decile_lift)))
                    .and_then(|(c, base)| finite(c - base));
                let pass = logloss_delta.unwrap_or(f64::INFINITY) < 0.0
                    && brier_delta.unwrap_or(f64::INFINITY) < 0.0
                    && lift_delta.unwrap_or(f64::NEG_INFINITY) >= 0.0;
                stable_cases += 1;
                stable_wins += usize::from(pass);
                lines.push(format!(
                    "| {} | {}h | {} | {} | {} | {} | {} |",
                    symbol,
                    horizon,
                    fold,
                    if pass { "pass" } else { "diagnostic_only" },
                    fmt_num(logloss_delta, 4),
                    fmt_num(brier_delta, 4),
                    fmt_pct(lift_delta)
                ));
            }
        }
    }
    lines.push(String::new());
    lines.push(format!(
        "- Fold 2/3 non-overlap stable wins: `{stable_wins}/{stable_cases}`. Unless this is consistently positive, the result stays a phenomenon diagnostic rather than an alpha claim."
    ));
    let best = metrics
        .iter()
        .filter(|row| {
            row.sample == "stride_h_non_overlap" && row.model == "context_plus_l2_ridge_logistic"
        })
        .filter_map(|row| row.top_decile_lift.map(|lift| (row, lift)))
        .max_by(|a, b| a.1.total_cmp(&b.1));
    if let Some((row, lift)) = best {
        lines.push(format!(
            "- Best context+L2 non-overlap top-decile lift observed: `{}` for `{}` {}h {}. Treat as smoke only.",
            fmt_pct(Some(lift)),
            row.symbol,
            row.horizon_hours,
            row.fold
        ));
    }
    lines.push(format!("- Daily stability rows: `{}`.", stability.len()));
    write_text_atomic(&paths.report_md, &lines.join("\n"))
}

fn read_state_rows(path: &Path) -> Result<Vec<StateRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        let book_ticker_count = u64_array_col(&batch, "book_ticker_count")?;
        let mid_price_per_token_close = f64_array(&batch, "mid_price_per_token_close")?;
        let spread_bps_median = f64_array(&batch, "spread_bps_median")?;
        let spread_bps_last = f64_array(&batch, "spread_bps_last")?;
        let top_depth_bid_notional_median = f64_array(&batch, "top_depth_bid_notional_median")?;
        let top_depth_ask_notional_median = f64_array(&batch, "top_depth_ask_notional_median")?;
        let microprice_offset_bps_mean = f64_array(&batch, "microprice_offset_bps_mean")?;
        let snapshot_count = u64_array_col(&batch, "snapshot_count")?;
        let snapshot_spread_bps_median = f64_array(&batch, "snapshot_spread_bps_median")?;
        let wobi5_mean = f64_array(&batch, "wobi5_mean")?;
        let wobi25_mean = f64_array(&batch, "wobi25_mean")?;
        let depth_imbalance_5_mean = f64_array(&batch, "depth_imbalance_5_mean")?;
        let depth_imbalance_25_mean = f64_array(&batch, "depth_imbalance_25_mean")?;
        let depth_bid_notional_5_median = f64_array(&batch, "depth_bid_notional_5_median")?;
        let depth_ask_notional_5_median = f64_array(&batch, "depth_ask_notional_5_median")?;
        let depth_bid_notional_25_median = f64_array(&batch, "depth_bid_notional_25_median")?;
        let depth_ask_notional_25_median = f64_array(&batch, "depth_ask_notional_25_median")?;
        let snapshot_microprice_offset_bps_mean =
            f64_array(&batch, "snapshot_microprice_offset_bps_mean")?;
        let trade_count = u64_array_col(&batch, "trade_count")?;
        let trade_notional_quote_sum = f64_array(&batch, "trade_notional_quote_sum")?;
        let trade_flow_imbalance = f64_array(&batch, "trade_flow_imbalance")?;
        let reported_buy_share = f64_array(&batch, "reported_buy_share")?;
        let ret_1m_bps = f64_array(&batch, "ret_1m_bps")?;
        for idx in 0..batch.num_rows() {
            out.push(StateRow {
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: str_value(symbol, idx),
                book_ticker_count: u64_value(book_ticker_count, idx),
                mid_price_per_token_close: opt_f64_value(mid_price_per_token_close, idx),
                spread_bps_median: opt_f64_value(spread_bps_median, idx),
                spread_bps_last: opt_f64_value(spread_bps_last, idx),
                top_depth_bid_notional_median: opt_f64_value(top_depth_bid_notional_median, idx),
                top_depth_ask_notional_median: opt_f64_value(top_depth_ask_notional_median, idx),
                microprice_offset_bps_mean: opt_f64_value(microprice_offset_bps_mean, idx),
                snapshot_count: u64_value(snapshot_count, idx),
                snapshot_spread_bps_median: opt_f64_value(snapshot_spread_bps_median, idx),
                wobi5_mean: opt_f64_value(wobi5_mean, idx),
                wobi25_mean: opt_f64_value(wobi25_mean, idx),
                depth_imbalance_5_mean: opt_f64_value(depth_imbalance_5_mean, idx),
                depth_imbalance_25_mean: opt_f64_value(depth_imbalance_25_mean, idx),
                depth_bid_notional_5_median: opt_f64_value(depth_bid_notional_5_median, idx),
                depth_ask_notional_5_median: opt_f64_value(depth_ask_notional_5_median, idx),
                depth_bid_notional_25_median: opt_f64_value(depth_bid_notional_25_median, idx),
                depth_ask_notional_25_median: opt_f64_value(depth_ask_notional_25_median, idx),
                snapshot_microprice_offset_bps_mean: opt_f64_value(
                    snapshot_microprice_offset_bps_mean,
                    idx,
                ),
                trade_count: u64_value(trade_count, idx),
                trade_notional_quote_sum: opt_f64_value(trade_notional_quote_sum, idx)
                    .unwrap_or(0.0),
                trade_flow_imbalance: opt_f64_value(trade_flow_imbalance, idx),
                reported_buy_share: opt_f64_value(reported_buy_share, idx),
                ret_1m_bps: opt_f64_value(ret_1m_bps, idx),
            });
        }
    }
    Ok(out)
}

fn read_label_rows(path: &Path) -> Result<Vec<LabelRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let timestamp_utc = str_array(&batch, "timestamp_utc")?;
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let symbol = str_array(&batch, "symbol")?;
        let asset = str_array(&batch, "asset")?;
        let horizon_hours = u64_array_col(&batch, "horizon_hours")?;
        let barrier_bps = u64_array_col(&batch, "barrier_bps")?;
        let price_per_token = f64_array(&batch, "price_per_token")?;
        let future_return_bps = f64_array(&batch, "future_return_bps")?;
        let mfe_up_bps = f64_array(&batch, "mfe_up_bps")?;
        let mae_down_bps = f64_array(&batch, "mae_down_bps")?;
        let barrier_first_hit = str_array(&batch, "barrier_first_hit")?;
        let label_status = str_array(&batch, "label_status")?;
        for idx in 0..batch.num_rows() {
            out.push(LabelRow {
                timestamp_utc: str_value(timestamp_utc, idx),
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: str_value(symbol, idx),
                asset: str_value(asset, idx),
                horizon_hours: u64_value(horizon_hours, idx),
                barrier_bps: u64_value(barrier_bps, idx),
                price_per_token: opt_f64_value(price_per_token, idx),
                future_return_bps: opt_f64_value(future_return_bps, idx),
                mfe_up_bps: opt_f64_value(mfe_up_bps, idx),
                mae_down_bps: opt_f64_value(mae_down_bps, idx),
                barrier_first_hit: str_value(barrier_first_hit, idx),
                label_status: str_value(label_status, idx),
            });
        }
    }
    Ok(out)
}

fn read_cov_rows(path: &Path) -> Result<Vec<CovRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let avg_corr_60m = f64_array(&batch, "avg_corr_60m")?;
        let first_eigen_share_60m = f64_array(&batch, "first_eigen_share_60m")?;
        let cross_symbol_abs_ret_mean_bps = f64_array(&batch, "cross_symbol_abs_ret_mean_bps")?;
        for idx in 0..batch.num_rows() {
            out.push(CovRow {
                timestamp_us: u64_value(timestamp_us, idx),
                avg_corr_60m: opt_f64_value(avg_corr_60m, idx),
                first_eigen_share_60m: opt_f64_value(first_eigen_share_60m, idx),
                cross_symbol_abs_ret_mean_bps: opt_f64_value(cross_symbol_abs_ret_mean_bps, idx),
            });
        }
    }
    Ok(out)
}

fn read_price_context_rows(path: &Path) -> Result<Vec<PriceContextRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let symbol = str_array(&batch, "symbol")?;
        let timestamp_us = u64_array_col(&batch, "timestamp_us")?;
        let close = f64_array(&batch, "close")?;
        let ret_1m_bps = f64_array(&batch, "ret_1m_bps")?;
        let rv_15m_bps = f64_array(&batch, "rv_15m_bps")?;
        let rv_1h_bps = f64_array(&batch, "rv_1h_bps")?;
        let rv_4h_bps = f64_array(&batch, "rv_4h_bps")?;
        let rv_12h_bps = f64_array(&batch, "rv_12h_bps")?;
        let market_return_bps = f64_array(&batch, "market_return_bps")?;
        let meme_return_bps = f64_array(&batch, "meme_return_bps")?;
        let sol_return_bps = f64_array(&batch, "sol_return_bps")?;
        let bonk_rel_market_bps = f64_array(&batch, "bonk_rel_market_bps")?;
        let bonk_rel_meme_bps = f64_array(&batch, "bonk_rel_meme_bps")?;
        let bonk_rel_sol_bps = f64_array(&batch, "bonk_rel_sol_bps")?;
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
            if symbol.value(idx) != "BONKUSDT" {
                continue;
            }
            out.push(PriceContextRow {
                timestamp_us: u64_value(timestamp_us, idx),
                close: opt_f64_value(close, idx).unwrap_or(f64::NAN),
                ret_1m_bps: opt_f64_value(ret_1m_bps, idx),
                rv_15m_bps: opt_f64_value(rv_15m_bps, idx),
                rv_1h_bps: opt_f64_value(rv_1h_bps, idx),
                rv_4h_bps: opt_f64_value(rv_4h_bps, idx),
                rv_12h_bps: opt_f64_value(rv_12h_bps, idx),
                market_return_bps: opt_f64_value(market_return_bps, idx),
                meme_return_bps: opt_f64_value(meme_return_bps, idx),
                sol_return_bps: opt_f64_value(sol_return_bps, idx),
                bonk_rel_market_bps: opt_f64_value(bonk_rel_market_bps, idx),
                bonk_rel_meme_bps: opt_f64_value(bonk_rel_meme_bps, idx),
                bonk_rel_sol_bps: opt_f64_value(bonk_rel_sol_bps, idx),
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
    out.sort_by_key(|row| row.timestamp_us);
    Ok(out)
}

fn read_panel_rows(path: &Path) -> Result<Vec<PanelRow>> {
    let mut out = Vec::new();
    for batch in read_parquet_batches(path)? {
        let s = |name| str_array(&batch, name);
        let u = |name| u64_array_col(&batch, name);
        let f = |name| f64_array(&batch, name);
        let run_tag = s("run_tag")?;
        let timestamp_utc = s("timestamp_utc")?;
        let timestamp_us = u("timestamp_us")?;
        let symbol = s("symbol")?;
        let asset = s("asset")?;
        let quote = s("quote")?;
        let horizon_hours = u("horizon_hours")?;
        let barrier_bps = u("barrier_bps")?;
        let label_status = s("label_status")?;
        let barrier_first_hit = s("barrier_first_hit")?;
        let price_per_token = f("price_per_token")?;
        let future_return_bps = f("future_return_bps")?;
        let mfe_up_bps = f("mfe_up_bps")?;
        let mae_down_bps = f("mae_down_bps")?;
        let future_ctx_market_return_bps = f("future_ctx_market_return_bps")?;
        let future_ctx_meme_return_bps = f("future_ctx_meme_return_bps")?;
        let future_ctx_sol_return_bps = f("future_ctx_sol_return_bps")?;
        let future_ctx_bonk_binance_return_bps = f("future_ctx_bonk_binance_return_bps")?;
        let future_bonk_rel_market_bps = f("future_bonk_rel_market_bps")?;
        let future_bonk_rel_meme_bps = f("future_bonk_rel_meme_bps")?;
        let future_bonk_rel_sol_bps = f("future_bonk_rel_sol_bps")?;
        let future_resid_mkt_meme_sol_bps = f("future_resid_mkt_meme_sol_bps")?;
        let residual_positive_flag = f("residual_positive_flag")?;
        let vol_adj_barrier_bps = f("vol_adj_barrier_bps")?;
        let vol_adj_barrier_first_hit = s("vol_adj_barrier_first_hit")?;
        let book_ticker_count = u("book_ticker_count")?;
        let snapshot_count = u("snapshot_count")?;
        let trade_count = u("trade_count")?;
        let trade_notional_quote_sum = f("trade_notional_quote_sum")?;
        let spread_bps_median = f("spread_bps_median")?;
        let spread_bps_last = f("spread_bps_last")?;
        let top_depth_bid_notional_median = f("top_depth_bid_notional_median")?;
        let top_depth_ask_notional_median = f("top_depth_ask_notional_median")?;
        let top_depth_total_notional_median = f("top_depth_total_notional_median")?;
        let microprice_offset_bps_mean = f("microprice_offset_bps_mean")?;
        let snapshot_spread_bps_median = f("snapshot_spread_bps_median")?;
        let snapshot_microprice_offset_bps_mean = f("snapshot_microprice_offset_bps_mean")?;
        let wobi5_mean = f("wobi5_mean")?;
        let wobi25_mean = f("wobi25_mean")?;
        let wobi5_minus_wobi25 = f("wobi5_minus_wobi25")?;
        let depth_imbalance_5_mean = f("depth_imbalance_5_mean")?;
        let depth_imbalance_25_mean = f("depth_imbalance_25_mean")?;
        let depth_bid_notional_5_median = f("depth_bid_notional_5_median")?;
        let depth_ask_notional_5_median = f("depth_ask_notional_5_median")?;
        let depth_bid_notional_25_median = f("depth_bid_notional_25_median")?;
        let depth_ask_notional_25_median = f("depth_ask_notional_25_median")?;
        let trade_flow_imbalance = f("trade_flow_imbalance")?;
        let reported_buy_share = f("reported_buy_share")?;
        let l2_ret_1m_bps = f("l2_ret_1m_bps")?;
        let cross_venue_basis_bps = f("cross_venue_basis_bps")?;
        let cross_venue_spread_diff_bps = f("cross_venue_spread_diff_bps")?;
        let cross_venue_activity_ratio = f("cross_venue_activity_ratio")?;
        let cross_venue_microprice_disagreement_bps = f("cross_venue_microprice_disagreement_bps")?;
        let ctx_bonk_close = f("ctx_bonk_close")?;
        let ctx_bonk_ret_1m_bps = f("ctx_bonk_ret_1m_bps")?;
        let ctx_market_ret_15m_bps = f("ctx_market_ret_15m_bps")?;
        let ctx_market_ret_60m_bps = f("ctx_market_ret_60m_bps")?;
        let ctx_market_ret_240m_bps = f("ctx_market_ret_240m_bps")?;
        let ctx_meme_ret_15m_bps = f("ctx_meme_ret_15m_bps")?;
        let ctx_meme_ret_60m_bps = f("ctx_meme_ret_60m_bps")?;
        let ctx_meme_ret_240m_bps = f("ctx_meme_ret_240m_bps")?;
        let ctx_sol_ret_15m_bps = f("ctx_sol_ret_15m_bps")?;
        let ctx_sol_ret_60m_bps = f("ctx_sol_ret_60m_bps")?;
        let ctx_sol_ret_240m_bps = f("ctx_sol_ret_240m_bps")?;
        let ctx_bonk_rel_market_bps = f("ctx_bonk_rel_market_bps")?;
        let ctx_bonk_rel_meme_bps = f("ctx_bonk_rel_meme_bps")?;
        let ctx_bonk_rel_sol_bps = f("ctx_bonk_rel_sol_bps")?;
        let ctx_bonk_rv_15m_bps = f("ctx_bonk_rv_15m_bps")?;
        let ctx_bonk_rv_1h_bps = f("ctx_bonk_rv_1h_bps")?;
        let ctx_bonk_rv_4h_bps = f("ctx_bonk_rv_4h_bps")?;
        let ctx_bonk_rv_12h_bps = f("ctx_bonk_rv_12h_bps")?;
        let ctx_market_rv_1h_bps = f("ctx_market_rv_1h_bps")?;
        let ctx_meme_rv_1h_bps = f("ctx_meme_rv_1h_bps")?;
        let ctx_sol_rv_1h_bps = f("ctx_sol_rv_1h_bps")?;
        let ctx_bonk_beta_market_60m = f("ctx_bonk_beta_market_60m")?;
        let ctx_bonk_corr_market_60m = f("ctx_bonk_corr_market_60m")?;
        let ctx_bonk_beta_meme_60m = f("ctx_bonk_beta_meme_60m")?;
        let ctx_bonk_corr_meme_60m = f("ctx_bonk_corr_meme_60m")?;
        let ctx_bonk_beta_sol_60m = f("ctx_bonk_beta_sol_60m")?;
        let ctx_bonk_corr_sol_60m = f("ctx_bonk_corr_sol_60m")?;
        let ctx_bonk_beta_market_240m = f("ctx_bonk_beta_market_240m")?;
        let ctx_bonk_corr_market_240m = f("ctx_bonk_corr_market_240m")?;
        let ctx_bonk_beta_meme_240m = f("ctx_bonk_beta_meme_240m")?;
        let ctx_bonk_corr_meme_240m = f("ctx_bonk_corr_meme_240m")?;
        let ctx_bonk_beta_sol_240m = f("ctx_bonk_beta_sol_240m")?;
        let ctx_bonk_corr_sol_240m = f("ctx_bonk_corr_sol_240m")?;
        let bullish_avg_corr_60m = f("bullish_avg_corr_60m")?;
        let bullish_first_eigen_share_60m = f("bullish_first_eigen_share_60m")?;
        let bullish_cross_abs_ret_mean_bps = f("bullish_cross_abs_ret_mean_bps")?;
        let bullish_common_mode_score = f("bullish_common_mode_score")?;
        for idx in 0..batch.num_rows() {
            out.push(PanelRow {
                run_tag: str_value(run_tag, idx),
                timestamp_utc: str_value(timestamp_utc, idx),
                timestamp_us: u64_value(timestamp_us, idx),
                symbol: str_value(symbol, idx),
                asset: str_value(asset, idx),
                quote: str_value(quote, idx),
                horizon_hours: u64_value(horizon_hours, idx),
                barrier_bps: u64_value(barrier_bps, idx),
                label_status: str_value(label_status, idx),
                barrier_first_hit: str_value(barrier_first_hit, idx),
                price_per_token: opt_f64_value(price_per_token, idx),
                future_return_bps: opt_f64_value(future_return_bps, idx),
                mfe_up_bps: opt_f64_value(mfe_up_bps, idx),
                mae_down_bps: opt_f64_value(mae_down_bps, idx),
                future_ctx_market_return_bps: opt_f64_value(future_ctx_market_return_bps, idx),
                future_ctx_meme_return_bps: opt_f64_value(future_ctx_meme_return_bps, idx),
                future_ctx_sol_return_bps: opt_f64_value(future_ctx_sol_return_bps, idx),
                future_ctx_bonk_binance_return_bps: opt_f64_value(
                    future_ctx_bonk_binance_return_bps,
                    idx,
                ),
                future_bonk_rel_market_bps: opt_f64_value(future_bonk_rel_market_bps, idx),
                future_bonk_rel_meme_bps: opt_f64_value(future_bonk_rel_meme_bps, idx),
                future_bonk_rel_sol_bps: opt_f64_value(future_bonk_rel_sol_bps, idx),
                future_resid_mkt_meme_sol_bps: opt_f64_value(future_resid_mkt_meme_sol_bps, idx),
                residual_positive_flag: opt_f64_value(residual_positive_flag, idx),
                vol_adj_barrier_bps: opt_f64_value(vol_adj_barrier_bps, idx),
                vol_adj_barrier_first_hit: str_value(vol_adj_barrier_first_hit, idx),
                book_ticker_count: u64_value(book_ticker_count, idx),
                snapshot_count: u64_value(snapshot_count, idx),
                trade_count: u64_value(trade_count, idx),
                trade_notional_quote_sum: opt_f64_value(trade_notional_quote_sum, idx)
                    .unwrap_or(0.0),
                spread_bps_median: opt_f64_value(spread_bps_median, idx),
                spread_bps_last: opt_f64_value(spread_bps_last, idx),
                top_depth_bid_notional_median: opt_f64_value(top_depth_bid_notional_median, idx),
                top_depth_ask_notional_median: opt_f64_value(top_depth_ask_notional_median, idx),
                top_depth_total_notional_median: opt_f64_value(
                    top_depth_total_notional_median,
                    idx,
                ),
                microprice_offset_bps_mean: opt_f64_value(microprice_offset_bps_mean, idx),
                snapshot_spread_bps_median: opt_f64_value(snapshot_spread_bps_median, idx),
                snapshot_microprice_offset_bps_mean: opt_f64_value(
                    snapshot_microprice_offset_bps_mean,
                    idx,
                ),
                wobi5_mean: opt_f64_value(wobi5_mean, idx),
                wobi25_mean: opt_f64_value(wobi25_mean, idx),
                wobi5_minus_wobi25: opt_f64_value(wobi5_minus_wobi25, idx),
                depth_imbalance_5_mean: opt_f64_value(depth_imbalance_5_mean, idx),
                depth_imbalance_25_mean: opt_f64_value(depth_imbalance_25_mean, idx),
                depth_bid_notional_5_median: opt_f64_value(depth_bid_notional_5_median, idx),
                depth_ask_notional_5_median: opt_f64_value(depth_ask_notional_5_median, idx),
                depth_bid_notional_25_median: opt_f64_value(depth_bid_notional_25_median, idx),
                depth_ask_notional_25_median: opt_f64_value(depth_ask_notional_25_median, idx),
                trade_flow_imbalance: opt_f64_value(trade_flow_imbalance, idx),
                reported_buy_share: opt_f64_value(reported_buy_share, idx),
                l2_ret_1m_bps: opt_f64_value(l2_ret_1m_bps, idx),
                cross_venue_basis_bps: opt_f64_value(cross_venue_basis_bps, idx),
                cross_venue_spread_diff_bps: opt_f64_value(cross_venue_spread_diff_bps, idx),
                cross_venue_activity_ratio: opt_f64_value(cross_venue_activity_ratio, idx),
                cross_venue_microprice_disagreement_bps: opt_f64_value(
                    cross_venue_microprice_disagreement_bps,
                    idx,
                ),
                ctx_bonk_close: opt_f64_value(ctx_bonk_close, idx),
                ctx_bonk_ret_1m_bps: opt_f64_value(ctx_bonk_ret_1m_bps, idx),
                ctx_market_ret_15m_bps: opt_f64_value(ctx_market_ret_15m_bps, idx),
                ctx_market_ret_60m_bps: opt_f64_value(ctx_market_ret_60m_bps, idx),
                ctx_market_ret_240m_bps: opt_f64_value(ctx_market_ret_240m_bps, idx),
                ctx_meme_ret_15m_bps: opt_f64_value(ctx_meme_ret_15m_bps, idx),
                ctx_meme_ret_60m_bps: opt_f64_value(ctx_meme_ret_60m_bps, idx),
                ctx_meme_ret_240m_bps: opt_f64_value(ctx_meme_ret_240m_bps, idx),
                ctx_sol_ret_15m_bps: opt_f64_value(ctx_sol_ret_15m_bps, idx),
                ctx_sol_ret_60m_bps: opt_f64_value(ctx_sol_ret_60m_bps, idx),
                ctx_sol_ret_240m_bps: opt_f64_value(ctx_sol_ret_240m_bps, idx),
                ctx_bonk_rel_market_bps: opt_f64_value(ctx_bonk_rel_market_bps, idx),
                ctx_bonk_rel_meme_bps: opt_f64_value(ctx_bonk_rel_meme_bps, idx),
                ctx_bonk_rel_sol_bps: opt_f64_value(ctx_bonk_rel_sol_bps, idx),
                ctx_bonk_rv_15m_bps: opt_f64_value(ctx_bonk_rv_15m_bps, idx),
                ctx_bonk_rv_1h_bps: opt_f64_value(ctx_bonk_rv_1h_bps, idx),
                ctx_bonk_rv_4h_bps: opt_f64_value(ctx_bonk_rv_4h_bps, idx),
                ctx_bonk_rv_12h_bps: opt_f64_value(ctx_bonk_rv_12h_bps, idx),
                ctx_market_rv_1h_bps: opt_f64_value(ctx_market_rv_1h_bps, idx),
                ctx_meme_rv_1h_bps: opt_f64_value(ctx_meme_rv_1h_bps, idx),
                ctx_sol_rv_1h_bps: opt_f64_value(ctx_sol_rv_1h_bps, idx),
                ctx_bonk_beta_market_60m: opt_f64_value(ctx_bonk_beta_market_60m, idx),
                ctx_bonk_corr_market_60m: opt_f64_value(ctx_bonk_corr_market_60m, idx),
                ctx_bonk_beta_meme_60m: opt_f64_value(ctx_bonk_beta_meme_60m, idx),
                ctx_bonk_corr_meme_60m: opt_f64_value(ctx_bonk_corr_meme_60m, idx),
                ctx_bonk_beta_sol_60m: opt_f64_value(ctx_bonk_beta_sol_60m, idx),
                ctx_bonk_corr_sol_60m: opt_f64_value(ctx_bonk_corr_sol_60m, idx),
                ctx_bonk_beta_market_240m: opt_f64_value(ctx_bonk_beta_market_240m, idx),
                ctx_bonk_corr_market_240m: opt_f64_value(ctx_bonk_corr_market_240m, idx),
                ctx_bonk_beta_meme_240m: opt_f64_value(ctx_bonk_beta_meme_240m, idx),
                ctx_bonk_corr_meme_240m: opt_f64_value(ctx_bonk_corr_meme_240m, idx),
                ctx_bonk_beta_sol_240m: opt_f64_value(ctx_bonk_beta_sol_240m, idx),
                ctx_bonk_corr_sol_240m: opt_f64_value(ctx_bonk_corr_sol_240m, idx),
                bullish_avg_corr_60m: opt_f64_value(bullish_avg_corr_60m, idx),
                bullish_first_eigen_share_60m: opt_f64_value(bullish_first_eigen_share_60m, idx),
                bullish_cross_abs_ret_mean_bps: opt_f64_value(bullish_cross_abs_ret_mean_bps, idx),
                bullish_common_mode_score: opt_f64_value(bullish_common_mode_score, idx),
            });
        }
    }
    Ok(out)
}

fn write_panel_parquet(path: &Path, rows: &[PanelRow]) -> Result<()> {
    let schema = panel_schema();
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            str_col(rows, |r| &r.run_tag),
            str_col(rows, |r| &r.timestamp_utc),
            u64_array(&rows.iter().map(|r| r.timestamp_us).collect::<Vec<_>>()),
            str_col(rows, |r| &r.symbol),
            str_col(rows, |r| &r.asset),
            str_col(rows, |r| &r.quote),
            u64_array(&rows.iter().map(|r| r.horizon_hours).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|r| r.barrier_bps).collect::<Vec<_>>()),
            str_col(rows, |r| &r.label_status),
            str_col(rows, |r| &r.barrier_first_hit),
            opt_col(rows, |r| r.price_per_token),
            opt_col(rows, |r| r.future_return_bps),
            opt_col(rows, |r| r.mfe_up_bps),
            opt_col(rows, |r| r.mae_down_bps),
            opt_col(rows, |r| r.future_ctx_market_return_bps),
            opt_col(rows, |r| r.future_ctx_meme_return_bps),
            opt_col(rows, |r| r.future_ctx_sol_return_bps),
            opt_col(rows, |r| r.future_ctx_bonk_binance_return_bps),
            opt_col(rows, |r| r.future_bonk_rel_market_bps),
            opt_col(rows, |r| r.future_bonk_rel_meme_bps),
            opt_col(rows, |r| r.future_bonk_rel_sol_bps),
            opt_col(rows, |r| r.future_resid_mkt_meme_sol_bps),
            opt_col(rows, |r| r.residual_positive_flag),
            opt_col(rows, |r| r.vol_adj_barrier_bps),
            str_col(rows, |r| &r.vol_adj_barrier_first_hit),
            u64_array(&rows.iter().map(|r| r.book_ticker_count).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|r| r.snapshot_count).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|r| r.trade_count).collect::<Vec<_>>()),
            f64_col(rows, |r| r.trade_notional_quote_sum),
            opt_col(rows, |r| r.spread_bps_median),
            opt_col(rows, |r| r.spread_bps_last),
            opt_col(rows, |r| r.top_depth_bid_notional_median),
            opt_col(rows, |r| r.top_depth_ask_notional_median),
            opt_col(rows, |r| r.top_depth_total_notional_median),
            opt_col(rows, |r| r.microprice_offset_bps_mean),
            opt_col(rows, |r| r.snapshot_spread_bps_median),
            opt_col(rows, |r| r.snapshot_microprice_offset_bps_mean),
            opt_col(rows, |r| r.wobi5_mean),
            opt_col(rows, |r| r.wobi25_mean),
            opt_col(rows, |r| r.wobi5_minus_wobi25),
            opt_col(rows, |r| r.depth_imbalance_5_mean),
            opt_col(rows, |r| r.depth_imbalance_25_mean),
            opt_col(rows, |r| r.depth_bid_notional_5_median),
            opt_col(rows, |r| r.depth_ask_notional_5_median),
            opt_col(rows, |r| r.depth_bid_notional_25_median),
            opt_col(rows, |r| r.depth_ask_notional_25_median),
            opt_col(rows, |r| r.trade_flow_imbalance),
            opt_col(rows, |r| r.reported_buy_share),
            opt_col(rows, |r| r.l2_ret_1m_bps),
            opt_col(rows, |r| r.cross_venue_basis_bps),
            opt_col(rows, |r| r.cross_venue_spread_diff_bps),
            opt_col(rows, |r| r.cross_venue_activity_ratio),
            opt_col(rows, |r| r.cross_venue_microprice_disagreement_bps),
            opt_col(rows, |r| r.ctx_bonk_close),
            opt_col(rows, |r| r.ctx_bonk_ret_1m_bps),
            opt_col(rows, |r| r.ctx_market_ret_15m_bps),
            opt_col(rows, |r| r.ctx_market_ret_60m_bps),
            opt_col(rows, |r| r.ctx_market_ret_240m_bps),
            opt_col(rows, |r| r.ctx_meme_ret_15m_bps),
            opt_col(rows, |r| r.ctx_meme_ret_60m_bps),
            opt_col(rows, |r| r.ctx_meme_ret_240m_bps),
            opt_col(rows, |r| r.ctx_sol_ret_15m_bps),
            opt_col(rows, |r| r.ctx_sol_ret_60m_bps),
            opt_col(rows, |r| r.ctx_sol_ret_240m_bps),
            opt_col(rows, |r| r.ctx_bonk_rel_market_bps),
            opt_col(rows, |r| r.ctx_bonk_rel_meme_bps),
            opt_col(rows, |r| r.ctx_bonk_rel_sol_bps),
            opt_col(rows, |r| r.ctx_bonk_rv_15m_bps),
            opt_col(rows, |r| r.ctx_bonk_rv_1h_bps),
            opt_col(rows, |r| r.ctx_bonk_rv_4h_bps),
            opt_col(rows, |r| r.ctx_bonk_rv_12h_bps),
            opt_col(rows, |r| r.ctx_market_rv_1h_bps),
            opt_col(rows, |r| r.ctx_meme_rv_1h_bps),
            opt_col(rows, |r| r.ctx_sol_rv_1h_bps),
            opt_col(rows, |r| r.ctx_bonk_beta_market_60m),
            opt_col(rows, |r| r.ctx_bonk_corr_market_60m),
            opt_col(rows, |r| r.ctx_bonk_beta_meme_60m),
            opt_col(rows, |r| r.ctx_bonk_corr_meme_60m),
            opt_col(rows, |r| r.ctx_bonk_beta_sol_60m),
            opt_col(rows, |r| r.ctx_bonk_corr_sol_60m),
            opt_col(rows, |r| r.ctx_bonk_beta_market_240m),
            opt_col(rows, |r| r.ctx_bonk_corr_market_240m),
            opt_col(rows, |r| r.ctx_bonk_beta_meme_240m),
            opt_col(rows, |r| r.ctx_bonk_corr_meme_240m),
            opt_col(rows, |r| r.ctx_bonk_beta_sol_240m),
            opt_col(rows, |r| r.ctx_bonk_corr_sol_240m),
            opt_col(rows, |r| r.bullish_avg_corr_60m),
            opt_col(rows, |r| r.bullish_first_eigen_share_60m),
            opt_col(rows, |r| r.bullish_cross_abs_ret_mean_bps),
            opt_col(rows, |r| r.bullish_common_mode_score),
        ],
    )?;
    write_parquet_atomic(path, schema, batch)
}

fn panel_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_s("run_tag"),
        field_s("timestamp_utc"),
        field_u("timestamp_us"),
        field_s("symbol"),
        field_s("asset"),
        field_s("quote"),
        field_u("horizon_hours"),
        field_u("barrier_bps"),
        field_s("label_status"),
        field_s("barrier_first_hit"),
        field_f("price_per_token"),
        field_f("future_return_bps"),
        field_f("mfe_up_bps"),
        field_f("mae_down_bps"),
        field_f("future_ctx_market_return_bps"),
        field_f("future_ctx_meme_return_bps"),
        field_f("future_ctx_sol_return_bps"),
        field_f("future_ctx_bonk_binance_return_bps"),
        field_f("future_bonk_rel_market_bps"),
        field_f("future_bonk_rel_meme_bps"),
        field_f("future_bonk_rel_sol_bps"),
        field_f("future_resid_mkt_meme_sol_bps"),
        field_f("residual_positive_flag"),
        field_f("vol_adj_barrier_bps"),
        field_s("vol_adj_barrier_first_hit"),
        field_u("book_ticker_count"),
        field_u("snapshot_count"),
        field_u("trade_count"),
        field_f_required("trade_notional_quote_sum"),
        field_f("spread_bps_median"),
        field_f("spread_bps_last"),
        field_f("top_depth_bid_notional_median"),
        field_f("top_depth_ask_notional_median"),
        field_f("top_depth_total_notional_median"),
        field_f("microprice_offset_bps_mean"),
        field_f("snapshot_spread_bps_median"),
        field_f("snapshot_microprice_offset_bps_mean"),
        field_f("wobi5_mean"),
        field_f("wobi25_mean"),
        field_f("wobi5_minus_wobi25"),
        field_f("depth_imbalance_5_mean"),
        field_f("depth_imbalance_25_mean"),
        field_f("depth_bid_notional_5_median"),
        field_f("depth_ask_notional_5_median"),
        field_f("depth_bid_notional_25_median"),
        field_f("depth_ask_notional_25_median"),
        field_f("trade_flow_imbalance"),
        field_f("reported_buy_share"),
        field_f("l2_ret_1m_bps"),
        field_f("cross_venue_basis_bps"),
        field_f("cross_venue_spread_diff_bps"),
        field_f("cross_venue_activity_ratio"),
        field_f("cross_venue_microprice_disagreement_bps"),
        field_f("ctx_bonk_close"),
        field_f("ctx_bonk_ret_1m_bps"),
        field_f("ctx_market_ret_15m_bps"),
        field_f("ctx_market_ret_60m_bps"),
        field_f("ctx_market_ret_240m_bps"),
        field_f("ctx_meme_ret_15m_bps"),
        field_f("ctx_meme_ret_60m_bps"),
        field_f("ctx_meme_ret_240m_bps"),
        field_f("ctx_sol_ret_15m_bps"),
        field_f("ctx_sol_ret_60m_bps"),
        field_f("ctx_sol_ret_240m_bps"),
        field_f("ctx_bonk_rel_market_bps"),
        field_f("ctx_bonk_rel_meme_bps"),
        field_f("ctx_bonk_rel_sol_bps"),
        field_f("ctx_bonk_rv_15m_bps"),
        field_f("ctx_bonk_rv_1h_bps"),
        field_f("ctx_bonk_rv_4h_bps"),
        field_f("ctx_bonk_rv_12h_bps"),
        field_f("ctx_market_rv_1h_bps"),
        field_f("ctx_meme_rv_1h_bps"),
        field_f("ctx_sol_rv_1h_bps"),
        field_f("ctx_bonk_beta_market_60m"),
        field_f("ctx_bonk_corr_market_60m"),
        field_f("ctx_bonk_beta_meme_60m"),
        field_f("ctx_bonk_corr_meme_60m"),
        field_f("ctx_bonk_beta_sol_60m"),
        field_f("ctx_bonk_corr_sol_60m"),
        field_f("ctx_bonk_beta_market_240m"),
        field_f("ctx_bonk_corr_market_240m"),
        field_f("ctx_bonk_beta_meme_240m"),
        field_f("ctx_bonk_corr_meme_240m"),
        field_f("ctx_bonk_beta_sol_240m"),
        field_f("ctx_bonk_corr_sol_240m"),
        field_f("bullish_avg_corr_60m"),
        field_f("bullish_first_eigen_share_60m"),
        field_f("bullish_cross_abs_ret_mean_bps"),
        field_f("bullish_common_mode_score"),
    ]))
}

fn feature_value(row: &PanelRow, feature: &str) -> Option<f64> {
    match feature {
        "snapshot_count" => Some(row.snapshot_count as f64),
        "trade_count" => Some(row.trade_count as f64),
        "book_ticker_count" => Some(row.book_ticker_count as f64),
        "trade_notional_quote_sum" => Some(row.trade_notional_quote_sum),
        "spread_bps_median" => row.spread_bps_median,
        "spread_bps_last" => row.spread_bps_last,
        "top_depth_total_notional_median" => row.top_depth_total_notional_median,
        "wobi5_mean" => row.wobi5_mean,
        "wobi25_mean" => row.wobi25_mean,
        "wobi5_minus_wobi25" => row.wobi5_minus_wobi25,
        "depth_imbalance_25_mean" => row.depth_imbalance_25_mean,
        "microprice_offset_bps_mean" => row.microprice_offset_bps_mean,
        "snapshot_microprice_offset_bps_mean" => row.snapshot_microprice_offset_bps_mean,
        "reported_buy_share" => row.reported_buy_share,
        "trade_flow_imbalance" => row.trade_flow_imbalance,
        "cross_venue_basis_bps" => row.cross_venue_basis_bps,
        "cross_venue_spread_diff_bps" => row.cross_venue_spread_diff_bps,
        "cross_venue_activity_ratio" => row.cross_venue_activity_ratio,
        "cross_venue_microprice_disagreement_bps" => row.cross_venue_microprice_disagreement_bps,
        "ctx_market_ret_15m_bps" => row.ctx_market_ret_15m_bps,
        "ctx_market_ret_60m_bps" => row.ctx_market_ret_60m_bps,
        "ctx_market_ret_240m_bps" => row.ctx_market_ret_240m_bps,
        "ctx_meme_ret_15m_bps" => row.ctx_meme_ret_15m_bps,
        "ctx_meme_ret_60m_bps" => row.ctx_meme_ret_60m_bps,
        "ctx_meme_ret_240m_bps" => row.ctx_meme_ret_240m_bps,
        "ctx_sol_ret_15m_bps" => row.ctx_sol_ret_15m_bps,
        "ctx_sol_ret_60m_bps" => row.ctx_sol_ret_60m_bps,
        "ctx_sol_ret_240m_bps" => row.ctx_sol_ret_240m_bps,
        "ctx_bonk_rel_market_bps" => row.ctx_bonk_rel_market_bps,
        "ctx_bonk_rel_meme_bps" => row.ctx_bonk_rel_meme_bps,
        "ctx_bonk_rel_sol_bps" => row.ctx_bonk_rel_sol_bps,
        "ctx_bonk_rv_15m_bps" => row.ctx_bonk_rv_15m_bps,
        "ctx_bonk_rv_1h_bps" => row.ctx_bonk_rv_1h_bps,
        "ctx_bonk_rv_4h_bps" => row.ctx_bonk_rv_4h_bps,
        "ctx_bonk_rv_12h_bps" => row.ctx_bonk_rv_12h_bps,
        "ctx_bonk_beta_market_60m" => row.ctx_bonk_beta_market_60m,
        "ctx_bonk_corr_market_60m" => row.ctx_bonk_corr_market_60m,
        "ctx_bonk_beta_meme_60m" => row.ctx_bonk_beta_meme_60m,
        "ctx_bonk_corr_meme_60m" => row.ctx_bonk_corr_meme_60m,
        "ctx_bonk_beta_sol_60m" => row.ctx_bonk_beta_sol_60m,
        "ctx_bonk_corr_sol_60m" => row.ctx_bonk_corr_sol_60m,
        "ctx_bonk_beta_market_240m" => row.ctx_bonk_beta_market_240m,
        "ctx_bonk_corr_market_240m" => row.ctx_bonk_corr_market_240m,
        "ctx_bonk_beta_meme_240m" => row.ctx_bonk_beta_meme_240m,
        "ctx_bonk_corr_meme_240m" => row.ctx_bonk_corr_meme_240m,
        "ctx_bonk_beta_sol_240m" => row.ctx_bonk_beta_sol_240m,
        "ctx_bonk_corr_sol_240m" => row.ctx_bonk_corr_sol_240m,
        "bullish_avg_corr_60m" => row.bullish_avg_corr_60m,
        "bullish_first_eigen_share_60m" => row.bullish_first_eigen_share_60m,
        "bullish_cross_abs_ret_mean_bps" => row.bullish_cross_abs_ret_mean_bps,
        "bullish_common_mode_score" => row.bullish_common_mode_score,
        _ => None,
    }
}

fn panel_paths(config: &ResearchPanelConfig) -> PanelPaths {
    PanelPaths {
        state: config
            .data_root
            .join("derived/bonk_cex_l2_state")
            .join(format!("bonk_cex_l2_state_{}.parquet", config.l2_run_tag)),
        labels: config
            .data_root
            .join("derived/bonk_path_labels")
            .join(format!("bonk_path_labels_{}.parquet", config.l2_run_tag)),
        covariance: config
            .data_root
            .join("derived/bonk_cex_covariance_state")
            .join(format!(
                "bonk_cex_covariance_state_{}.parquet",
                config.l2_run_tag
            )),
        price_context: config
            .data_root
            .join("derived/bonk_cex_price_context")
            .join(format!(
                "bonk_cex_price_context_{}.parquet",
                config.price_context_run_tag
            )),
        panel: config
            .data_root
            .join("derived/bonk_l2_label_context_panel")
            .join(format!(
                "bonk_l2_label_context_panel_{}.parquet",
                config.run_tag
            )),
        controlled_factor_csv: config.date_dir.join(format!(
            "bonk_v1_controlled_factor_tests_{}.csv",
            config.run_tag
        )),
        panel_completion_json: config.date_dir.join(format!(
            "bonk_v1_research_panel_completion_{}.json",
            config.run_tag
        )),
    }
}

fn model_paths(config: &ModelReportConfig) -> ModelPaths {
    ModelPaths {
        panel: config
            .data_root
            .join("derived/bonk_l2_label_context_panel")
            .join(format!(
                "bonk_l2_label_context_panel_{}.parquet",
                config.run_tag
            )),
        metrics_csv: config
            .date_dir
            .join(format!("bonk_v1_model_metrics_{}.csv", config.run_tag)),
        stability_csv: config
            .date_dir
            .join(format!("bonk_v1_model_stability_{}.csv", config.run_tag)),
        report_md: config.doc_dir.join("v1-cex-modeling-report.md"),
        completion_json: config.date_dir.join(format!(
            "bonk_v1_model_report_completion_{}.json",
            config.run_tag
        )),
    }
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

fn str_col<T, F>(rows: &[T], f: F) -> ArrayRef
where
    F: Fn(&T) -> &String,
{
    string_array(&rows.iter().map(|row| f(row).clone()).collect::<Vec<_>>())
}

fn f64_col<T, F>(rows: &[T], f: F) -> ArrayRef
where
    F: Fn(&T) -> f64,
{
    let mut builder = Float64Builder::with_capacity(rows.len());
    for row in rows {
        builder.append_value(f(row));
    }
    Arc::new(builder.finish())
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
            .set_created_by("cex-l2-research".to_string())
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
                    sleep_replace_retry(attempt);
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
            Err(_err) if attempt + 1 < ATTEMPTS => {
                sleep_replace_retry(attempt);
                continue;
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

fn sleep_replace_retry(attempt: usize) {
    let millis = 50 * ((attempt as u64 + 1).min(20));
    std::thread::sleep(std::time::Duration::from_millis(millis));
}

fn temp_path_for(path: &Path) -> PathBuf {
    let filename = path.file_name().and_then(|v| v.to_str()).unwrap_or("out");
    path.with_file_name(format!(".{filename}.tmp.{}", std::process::id()))
}

fn folds() -> Result<Vec<Fold>> {
    Ok(vec![
        Fold {
            name: "fold1",
            train_end_us: parse_utc_us("2026-05-02T23:59:00Z")?,
            val_start_us: parse_utc_us("2026-05-03T12:00:00Z")?,
            val_end_us: parse_utc_us("2026-05-05T23:59:00Z")?,
        },
        Fold {
            name: "fold2",
            train_end_us: parse_utc_us("2026-05-05T23:59:00Z")?,
            val_start_us: parse_utc_us("2026-05-06T12:00:00Z")?,
            val_end_us: parse_utc_us("2026-05-08T23:59:00Z")?,
        },
        Fold {
            name: "fold3",
            train_end_us: parse_utc_us("2026-05-08T23:59:00Z")?,
            val_start_us: parse_utc_us("2026-05-09T12:00:00Z")?,
            val_end_us: parse_utc_us("2026-05-12T11:59:00Z")?,
        },
    ])
}

fn parse_utc_us(raw: &str) -> Result<u64> {
    Ok(chrono::DateTime::parse_from_rfc3339(raw)?
        .with_timezone(&Utc)
        .timestamp_micros() as u64)
}

fn quote_from_symbol(symbol: &str) -> String {
    if symbol.ends_with("USDC") {
        "USDC".to_string()
    } else if symbol.ends_with("USDT") {
        "USDT".to_string()
    } else {
        String::new()
    }
}

fn vol_adj_hit(
    barrier: Option<f64>,
    mfe_up: Option<f64>,
    mae_down: Option<f64>,
    status: &str,
) -> String {
    if status != "ok" {
        return status.to_string();
    }
    let Some(barrier) = barrier else {
        return "missing_barrier".to_string();
    };
    let up = mfe_up.map(|v| v >= barrier).unwrap_or(false);
    let down = mae_down.map(|v| v <= -barrier).unwrap_or(false);
    match (up, down) {
        (true, false) => "upper_path_hit".to_string(),
        (false, true) => "lower_path_hit".to_string(),
        (true, true) => "both_path_hit_unordered".to_string(),
        (false, false) => "none".to_string(),
    }
}

fn count_panel_duplicate_keys(rows: &[PanelRow]) -> usize {
    let mut seen = BTreeSet::new();
    let mut duplicates = 0usize;
    for row in rows {
        if !seen.insert((
            row.symbol.clone(),
            row.timestamp_us,
            row.horizon_hours,
            row.barrier_bps,
        )) {
            duplicates += 1;
        }
    }
    duplicates
}

fn train_upper_rate(rows: &[&PanelRow]) -> Option<f64> {
    rate(
        rows.iter().map(|row| row.barrier_first_hit.as_str()),
        "upper_first",
    )
}

fn rate<'a>(values: impl Iterator<Item = &'a str>, target: &str) -> Option<f64> {
    let mut total = 0usize;
    let mut hits = 0usize;
    for value in values {
        total += 1;
        if value == target {
            hits += 1;
        }
    }
    (total > 0).then_some(hits as f64 / total as f64)
}

fn mean(values: &[f64]) -> Option<f64> {
    let values = values
        .iter()
        .copied()
        .filter_map(finite)
        .collect::<Vec<_>>();
    (!values.is_empty()).then(|| values.iter().sum::<f64>() / values.len() as f64)
}

fn mean_opt(values: &[Option<f64>]) -> Option<f64> {
    let values = values.iter().filter_map(|v| *v).collect::<Vec<_>>();
    mean(&values)
}

fn median(mut values: Vec<f64>) -> Option<f64> {
    values = values.into_iter().filter_map(finite).collect();
    if values.is_empty() {
        return None;
    }
    values.sort_by(|a, b| a.total_cmp(b));
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        finite((values[mid - 1] + values[mid]) / 2.0)
    } else {
        Some(values[mid])
    }
}

fn quantile_sorted(values: &[f64], q: f64) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    let idx = ((values.len() - 1) as f64 * q).round() as usize;
    values.get(idx).copied()
}

fn diff_opt(left: Option<f64>, right: Option<f64>) -> Option<f64> {
    left.zip(right)
        .and_then(|(left, right)| finite(left - right))
}

fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn sigmoid(value: f64) -> f64 {
    if value >= 0.0 {
        1.0 / (1.0 + (-value).exp())
    } else {
        let exp = value.exp();
        exp / (1.0 + exp)
    }
}

fn logit(value: f64) -> f64 {
    (value / (1.0 - value)).ln()
}

fn top_prediction_indexes(predictions: &[f64], frac: f64) -> Vec<usize> {
    if predictions.is_empty() {
        return Vec::new();
    }
    let n = ((predictions.len() as f64 * frac).ceil() as usize).max(1);
    let mut indexes = (0..predictions.len()).collect::<Vec<_>>();
    indexes.sort_by(|a, b| predictions[*b].total_cmp(&predictions[*a]));
    indexes.truncate(n);
    indexes
}

fn daily_spearman(rows: &[&PanelRow], predictions: &[f64]) -> Option<f64> {
    let mut by_day = BTreeMap::<String, Vec<(f64, f64)>>::new();
    for (row, pred) in rows.iter().zip(predictions) {
        if let Some(ret) = row.future_return_bps {
            by_day
                .entry(row.timestamp_utc.chars().take(10).collect())
                .or_default()
                .push((*pred, ret));
        }
    }
    let values = by_day
        .values()
        .filter_map(|pairs| spearman(pairs))
        .collect::<Vec<_>>();
    mean(&values)
}

fn spearman(pairs: &[(f64, f64)]) -> Option<f64> {
    if pairs.len() < 5 {
        return None;
    }
    let x = ranks(&pairs.iter().map(|(x, _)| *x).collect::<Vec<_>>());
    let y = ranks(&pairs.iter().map(|(_, y)| *y).collect::<Vec<_>>());
    pearson(&x, &y)
}

fn ranks(values: &[f64]) -> Vec<f64> {
    let mut indexes = (0..values.len()).collect::<Vec<_>>();
    indexes.sort_by(|a, b| values[*a].total_cmp(&values[*b]));
    let mut ranks = vec![0.0; values.len()];
    for (rank, idx) in indexes.iter().enumerate() {
        ranks[*idx] = rank as f64;
    }
    ranks
}

fn pearson(x: &[f64], y: &[f64]) -> Option<f64> {
    if x.len() != y.len() || x.len() < 2 {
        return None;
    }
    let mx = mean(x)?;
    let my = mean(y)?;
    let mut cov = 0.0;
    let mut vx = 0.0;
    let mut vy = 0.0;
    for (a, b) in x.iter().zip(y) {
        cov += (a - mx) * (b - my);
        vx += (a - mx) * (a - mx);
        vy += (b - my) * (b - my);
    }
    if vx <= 0.0 || vy <= 0.0 {
        None
    } else {
        finite(cov / (vx.sqrt() * vy.sqrt()))
    }
}

fn calibration_slope(y: &[f64], predictions: &[f64]) -> Option<f64> {
    let logits = predictions
        .iter()
        .map(|p| logit(p.clamp(1e-6, 1.0 - 1e-6)))
        .collect::<Vec<_>>();
    let mx = mean(&logits)?;
    let my = mean(y)?;
    let mut cov = 0.0;
    let mut var = 0.0;
    for (x, y) in logits.iter().zip(y) {
        cov += (x - mx) * (y - my);
        var += (x - mx) * (x - mx);
    }
    (var > 0.0).then_some(cov / var).and_then(finite)
}

fn field_s(name: &str) -> Field {
    Field::new(name, DataType::Utf8, false)
}

fn field_u(name: &str) -> Field {
    Field::new(name, DataType::UInt64, false)
}

fn field_f(name: &str) -> Field {
    Field::new(name, DataType::Float64, true)
}

fn field_f_required(name: &str) -> Field {
    Field::new(name, DataType::Float64, false)
}

fn fmt_num(value: Option<f64>, digits: usize) -> String {
    match value.and_then(finite) {
        Some(value) => format!("{value:.digits$}"),
        None => "n/a".to_string(),
    }
}

fn fmt_pct(value: Option<f64>) -> String {
    match value.and_then(finite) {
        Some(value) => format!("{:.1}%", value * 100.0),
        None => "n/a".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn panel_row(
        timestamp_us: u64,
        symbol: &str,
        horizon_hours: u64,
        barrier_bps: u64,
        barrier_first_hit: &str,
        snapshot_count: u64,
    ) -> PanelRow {
        PanelRow {
            run_tag: "test".to_string(),
            timestamp_utc: "2026-05-01T00:00:00Z".to_string(),
            timestamp_us,
            symbol: symbol.to_string(),
            asset: "BONK".to_string(),
            quote: quote_from_symbol(symbol),
            horizon_hours,
            barrier_bps,
            label_status: "ok".to_string(),
            barrier_first_hit: barrier_first_hit.to_string(),
            price_per_token: Some(0.00002),
            future_return_bps: Some(if barrier_first_hit == "upper_first" {
                120.0
            } else {
                -80.0
            }),
            mfe_up_bps: Some(120.0),
            mae_down_bps: Some(-80.0),
            future_ctx_market_return_bps: Some(10.0),
            future_ctx_meme_return_bps: Some(20.0),
            future_ctx_sol_return_bps: Some(5.0),
            future_ctx_bonk_binance_return_bps: Some(100.0),
            future_bonk_rel_market_bps: Some(90.0),
            future_bonk_rel_meme_bps: Some(80.0),
            future_bonk_rel_sol_bps: Some(95.0),
            future_resid_mkt_meme_sol_bps: Some(88.0),
            residual_positive_flag: Some((barrier_first_hit == "upper_first") as u8 as f64),
            vol_adj_barrier_bps: Some(100.0),
            vol_adj_barrier_first_hit: "upper_path_hit".to_string(),
            book_ticker_count: 1,
            snapshot_count,
            trade_count: 1,
            trade_notional_quote_sum: snapshot_count as f64,
            spread_bps_median: Some(10.0),
            spread_bps_last: Some(11.0),
            top_depth_bid_notional_median: Some(1_000.0),
            top_depth_ask_notional_median: Some(1_100.0),
            top_depth_total_notional_median: Some(2_100.0),
            microprice_offset_bps_mean: Some(1.0),
            snapshot_spread_bps_median: Some(10.5),
            snapshot_microprice_offset_bps_mean: Some(1.2),
            wobi5_mean: Some(0.1),
            wobi25_mean: Some(0.05),
            wobi5_minus_wobi25: Some(0.05),
            depth_imbalance_5_mean: Some(0.1),
            depth_imbalance_25_mean: Some(0.05),
            depth_bid_notional_5_median: Some(1_000.0),
            depth_ask_notional_5_median: Some(1_100.0),
            depth_bid_notional_25_median: Some(3_000.0),
            depth_ask_notional_25_median: Some(3_100.0),
            trade_flow_imbalance: Some(0.2),
            reported_buy_share: Some(0.6),
            l2_ret_1m_bps: Some(1.0),
            cross_venue_basis_bps: Some(0.5),
            cross_venue_spread_diff_bps: Some(0.2),
            cross_venue_activity_ratio: Some(1.1),
            cross_venue_microprice_disagreement_bps: Some(0.3),
            ctx_bonk_close: Some(0.00002),
            ctx_bonk_ret_1m_bps: Some(1.0),
            ctx_market_ret_15m_bps: Some(2.0),
            ctx_market_ret_60m_bps: Some(3.0),
            ctx_market_ret_240m_bps: Some(4.0),
            ctx_meme_ret_15m_bps: Some(5.0),
            ctx_meme_ret_60m_bps: Some(6.0),
            ctx_meme_ret_240m_bps: Some(7.0),
            ctx_sol_ret_15m_bps: Some(8.0),
            ctx_sol_ret_60m_bps: Some(9.0),
            ctx_sol_ret_240m_bps: Some(10.0),
            ctx_bonk_rel_market_bps: Some(1.0),
            ctx_bonk_rel_meme_bps: Some(2.0),
            ctx_bonk_rel_sol_bps: Some(3.0),
            ctx_bonk_rv_15m_bps: Some(20.0),
            ctx_bonk_rv_1h_bps: Some(40.0),
            ctx_bonk_rv_4h_bps: Some(80.0),
            ctx_bonk_rv_12h_bps: Some(120.0),
            ctx_market_rv_1h_bps: Some(30.0),
            ctx_meme_rv_1h_bps: Some(35.0),
            ctx_sol_rv_1h_bps: Some(25.0),
            ctx_bonk_beta_market_60m: Some(1.0),
            ctx_bonk_corr_market_60m: Some(0.5),
            ctx_bonk_beta_meme_60m: Some(1.2),
            ctx_bonk_corr_meme_60m: Some(0.6),
            ctx_bonk_beta_sol_60m: Some(0.9),
            ctx_bonk_corr_sol_60m: Some(0.4),
            ctx_bonk_beta_market_240m: Some(1.1),
            ctx_bonk_corr_market_240m: Some(0.55),
            ctx_bonk_beta_meme_240m: Some(1.3),
            ctx_bonk_corr_meme_240m: Some(0.65),
            ctx_bonk_beta_sol_240m: Some(0.95),
            ctx_bonk_corr_sol_240m: Some(0.45),
            bullish_avg_corr_60m: Some(0.2),
            bullish_first_eigen_share_60m: Some(0.3),
            bullish_cross_abs_ret_mean_bps: Some(20.0),
            bullish_common_mode_score: Some(0.1),
        }
    }

    #[test]
    fn bucket_thresholds_use_train_tertiles_and_ignore_nonfinite() {
        let thresholds =
            BucketThresholds::fit([1.0, 2.0, f64::NAN, 3.0, 4.0, 5.0].into_iter()).unwrap();
        assert_eq!(thresholds.low_cut, 2.0);
        assert_eq!(thresholds.high_cut, 4.0);
        assert_eq!(thresholds.bucket(1.5), "low");
        assert_eq!(thresholds.bucket(3.0), "mid");
        assert_eq!(thresholds.bucket(4.5), "high");
    }

    #[test]
    fn vol_adjusted_hit_preserves_status_and_path_width_cases() {
        assert_eq!(
            vol_adj_hit(Some(100.0), Some(120.0), Some(-20.0), "ok"),
            "upper_path_hit"
        );
        assert_eq!(
            vol_adj_hit(Some(100.0), Some(120.0), Some(-140.0), "ok"),
            "both_path_hit_unordered"
        );
        assert_eq!(
            vol_adj_hit(Some(100.0), Some(20.0), Some(-30.0), "future_missing"),
            "future_missing"
        );
        assert_eq!(
            vol_adj_hit(None, Some(120.0), Some(-20.0), "ok"),
            "missing_barrier"
        );
    }

    #[test]
    fn folds_keep_twelve_hour_purge_between_train_and_validation() {
        let folds = folds().unwrap();
        assert_eq!(folds.len(), 3);
        for fold in folds {
            assert!(fold.train_end_us < fold.val_start_us);
            assert!(fold.val_start_us - fold.train_end_us >= 12 * 60 * MINUTE_US);
        }
    }

    #[test]
    fn duplicate_panel_keys_count_symbol_timestamp_horizon_barrier() {
        let rows = vec![
            panel_row(1, "BONK1MUSDC", 1, 100, "upper_first", 1),
            panel_row(1, "BONK1MUSDC", 1, 100, "lower_first", 2),
            panel_row(1, "BONK1MUSDC", 4, 100, "upper_first", 3),
            panel_row(1, "BONK1MUSDT", 1, 100, "upper_first", 4),
        ];
        assert_eq!(count_panel_duplicate_keys(&rows), 1);
    }

    #[test]
    fn logistic_model_learns_simple_monotone_l2_feature() {
        let rows = (0..200)
            .map(|idx| {
                let high = idx >= 100;
                panel_row(
                    idx * MINUTE_US,
                    "BONK1MUSDC",
                    1,
                    100,
                    if high { "upper_first" } else { "lower_first" },
                    if high { 100 } else { 1 },
                )
            })
            .collect::<Vec<_>>();
        let refs = rows.iter().collect::<Vec<_>>();
        let model = LogisticModel::fit(&refs, &["snapshot_count"], 1.0).unwrap();
        let low = panel_row(1, "BONK1MUSDC", 1, 100, "lower_first", 1);
        let high = panel_row(2, "BONK1MUSDC", 1, 100, "upper_first", 100);
        assert!(model.predict(&high) > model.predict(&low) + 0.5);
    }
}

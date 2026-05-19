use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{
    Array, ArrayRef, Float64Array, Float64Builder, StringArray, StringBuilder, UInt64Array,
    UInt64Builder,
};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, SecondsFormat, Utc};
use finance_chain_core::storage::{
    DERIVED_DIR, ensure_parent_dir, parquet_files_under, write_parquet_part, write_schema_metadata,
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::Serialize;

use crate::{DEFAULT_DATA_ROOT, DEFAULT_PROGRESS_INTERVAL};

pub const DEFAULT_ORDERBOOK_RUN_TAG: &str = "20260512_orderbook_v1";

const BOOK_DEPTH_DATASET: &str = "binance_um_futures_book_depth";
const FUTURES_AGG_TRADES_DATASET: &str = "binance_um_futures_agg_trades";
const FUTURES_KLINES_DATASET: &str = "binance_um_futures_klines";
const FUTURES_MARK_PRICE_KLINES_DATASET: &str = "binance_um_futures_mark_price_klines";
const FUTURES_PREMIUM_INDEX_KLINES_DATASET: &str = "binance_um_futures_premium_index_klines";
const MINUTE_PRICE_REFERENCE_DATASET: &str = "mon_usdc_minute_price_reference";
const CEX_DEX_LAG_PANEL_DATASET: &str = "mon_usdc_cex_dex_lag_panel";
const ORDERBOOK_STATE_DATASET: &str = "mon_usdc_cex_orderbook_state";
const TRADE_FLOW_STATE_DATASET: &str = "mon_usdc_cex_trade_flow_state";
const ORDERBOOK_LAG_PANEL_DATASET: &str = "mon_usdc_cex_dex_orderbook_lag_panel";

const EPS: f64 = 1e-12;

#[derive(Debug, Clone)]
pub struct OrderbookConfig {
    pub data_root: PathBuf,
    pub run_tag: String,
    pub date_dir: PathBuf,
    pub docs_dir: PathBuf,
    pub expected_start_day: String,
    pub expected_end_day: String,
    pub progress_interval: usize,
}

impl Default for OrderbookConfig {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_DATA_ROOT),
            run_tag: DEFAULT_ORDERBOOK_RUN_TAG.to_string(),
            date_dir: PathBuf::from("date"),
            docs_dir: PathBuf::from("docs"),
            expected_start_day: "2026-02-01".to_string(),
            expected_end_day: "2026-05-11".to_string(),
            progress_interval: DEFAULT_PROGRESS_INTERVAL,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderbookReportSummary {
    pub data_root: String,
    pub run_tag: String,
    pub executable_path: String,
    pub exploratory_only: bool,
    pub inputs: OrderbookInputs,
    pub assumptions: OrderbookAssumptions,
    pub coverage: OrderbookCoverage,
    pub basis: FuturesBasisSummary,
    pub outputs: OrderbookOutputs,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderbookInputs {
    pub book_depth_dir: String,
    pub agg_trades_dir: String,
    pub futures_klines_dir: String,
    pub futures_mark_price_klines_dir: String,
    pub futures_premium_index_klines_dir: String,
    pub minute_price_reference: String,
    pub cex_dex_lag_panel: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderbookAssumptions {
    pub symbol: String,
    pub book_depth_format: String,
    pub depth_join_policy: String,
    pub trade_flow_join_policy: String,
    pub strict_ofi_scope: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderbookCoverage {
    pub expected_days: u64,
    pub book_depth_csv_files: u64,
    pub book_depth_zip_files: u64,
    pub book_depth_rows: u64,
    pub book_depth_snapshots: u64,
    pub book_depth_state_rows: u64,
    pub agg_trade_csv_files: u64,
    pub agg_trade_zip_files: u64,
    pub agg_trade_rows: u64,
    pub trade_flow_state_rows: u64,
    pub futures_kline_rows: u64,
    pub mark_price_rows: u64,
    pub premium_index_rows: u64,
    pub minute_price_reference_rows: u64,
    pub dex_lag_rows: u64,
    pub joined_panel_rows: u64,
    pub depth_joined_rows: u64,
    pub trade_flow_joined_rows: u64,
    pub missing_book_depth_days: Vec<String>,
    pub missing_agg_trade_days: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FuturesBasisSummary {
    pub common_rows: u64,
    pub median_trade_mark_basis_bps: Option<f64>,
    pub median_abs_trade_mark_basis_bps: Option<f64>,
    pub p90_abs_trade_mark_basis_bps: Option<f64>,
    pub median_premium_index_bps: Option<f64>,
    pub median_abs_premium_index_bps: Option<f64>,
    pub p90_abs_premium_index_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderbookOutputs {
    pub orderbook_state_parquet: String,
    pub trade_flow_state_parquet: String,
    pub orderbook_lag_panel_parquet: String,
    pub orderbook_summary_csv: String,
    pub orderbook_factor_tests_csv: String,
    pub completion_json: String,
    pub report: String,
}

#[derive(Debug, Default, Clone)]
struct ExternalCoverage {
    book_depth_csv_files: u64,
    book_depth_zip_files: u64,
    book_depth_rows: u64,
    book_depth_snapshots: u64,
    agg_trade_csv_files: u64,
    agg_trade_zip_files: u64,
    agg_trade_rows: u64,
    futures_kline_rows: u64,
    mark_price_rows: u64,
    premium_index_rows: u64,
}

#[derive(Debug, Default, Clone)]
struct BookSnapshotAgg {
    source_ts: i64,
    bid_notional_1pct: Option<f64>,
    ask_notional_1pct: Option<f64>,
    bid_notional_3pct: Option<f64>,
    ask_notional_3pct: Option<f64>,
    bid_notional_5pct: Option<f64>,
    ask_notional_5pct: Option<f64>,
    row_count: u64,
}

#[derive(Debug, Clone)]
struct OrderbookStateRow {
    run_tag: String,
    minute_ts: i64,
    minute_utc: String,
    source_ts: i64,
    source_utc: String,
    source_lag_seconds: i64,
    bid_notional_1pct: Option<f64>,
    ask_notional_1pct: Option<f64>,
    depth_imbalance_1pct: Option<f64>,
    bid_notional_3pct: Option<f64>,
    ask_notional_3pct: Option<f64>,
    depth_imbalance_3pct: Option<f64>,
    bid_notional_5pct: Option<f64>,
    ask_notional_5pct: Option<f64>,
    depth_imbalance_5pct: Option<f64>,
    bid_notional_depth: Option<f64>,
    ask_notional_depth: Option<f64>,
    liquidity_slope: Option<f64>,
    liquidity_vacuum: bool,
    wall_asymmetry: Option<f64>,
    snapshot_rows: u64,
    diagnostic_status: String,
}

#[derive(Debug, Default, Clone)]
struct TradeFlowAgg {
    minute_ts: i64,
    trade_count: u64,
    taker_buy_quote: f64,
    taker_sell_quote: f64,
    max_trade_quote: f64,
}

#[derive(Debug, Clone)]
struct TradeFlowStateRow {
    run_tag: String,
    minute_ts: i64,
    minute_utc: String,
    trade_count: u64,
    taker_buy_quote: f64,
    taker_sell_quote: f64,
    total_quote: f64,
    trade_imbalance: Option<f64>,
    sweep_intensity: Option<f64>,
    burst_trade_count: u64,
    max_trade_quote: Option<f64>,
    diagnostic_status: String,
}

#[derive(Debug, Clone)]
struct DexLagRow {
    source_run_tag: String,
    block_number: u64,
    event_timestamp: i64,
    event_time_utc: String,
    minute_ts: i64,
    split: String,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    quote_abs: Option<f64>,
    pool_price: Option<f64>,
    anchor_price: Option<f64>,
    anchor_source: String,
    dislocation_bps: Option<f64>,
    abs_dislocation_bps: Option<f64>,
    cost_adjusted_dislocation_bps: Option<f64>,
    half_life_minutes: Option<u64>,
    time_to_reenter_band_minutes: Option<u64>,
    max_adverse_dislocation_bps: Option<f64>,
    diagnostic_status: String,
}

#[derive(Debug, Clone)]
struct JoinedOrderbookLagRow {
    run_tag: String,
    source_lag_run_tag: String,
    block_number: u64,
    event_timestamp: i64,
    event_time_utc: String,
    minute_ts: i64,
    split: String,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    quote_abs: Option<f64>,
    pool_price: Option<f64>,
    anchor_price: Option<f64>,
    anchor_source: String,
    dislocation_bps: Option<f64>,
    abs_dislocation_bps: Option<f64>,
    cost_adjusted_dislocation_bps: Option<f64>,
    half_life_minutes: Option<u64>,
    time_to_reenter_band_minutes: Option<u64>,
    max_adverse_dislocation_bps: Option<f64>,
    depth_source_ts: Option<i64>,
    depth_source_lag_seconds: Option<u64>,
    depth_imbalance_1pct: Option<f64>,
    depth_imbalance_3pct: Option<f64>,
    depth_imbalance_5pct: Option<f64>,
    bid_notional_depth: Option<f64>,
    ask_notional_depth: Option<f64>,
    liquidity_slope: Option<f64>,
    liquidity_vacuum: Option<bool>,
    wall_asymmetry: Option<f64>,
    trade_flow_minute_ts: Option<i64>,
    trade_source_lag_minutes: Option<u64>,
    taker_buy_quote: Option<f64>,
    taker_sell_quote: Option<f64>,
    total_trade_quote: Option<f64>,
    trade_imbalance: Option<f64>,
    sweep_intensity: Option<f64>,
    burst_trade_count: Option<u64>,
    max_trade_quote: Option<f64>,
    diagnostic_status: String,
}

#[derive(Debug, Clone, Serialize)]
struct OrderbookSummaryRow {
    run_tag: String,
    group: String,
    group_value: String,
    rows: u64,
    depth_joined_rows: u64,
    depth_coverage_rate: Option<f64>,
    trade_flow_joined_rows: u64,
    trade_flow_coverage_rate: Option<f64>,
    liquidity_vacuum_rate: Option<f64>,
    cost_adjusted_positive_rate: Option<f64>,
    median_depth_imbalance_1pct: Option<f64>,
    median_depth_imbalance_5pct: Option<f64>,
    median_bid_notional_depth: Option<f64>,
    median_ask_notional_depth: Option<f64>,
    median_wall_asymmetry: Option<f64>,
    median_trade_imbalance: Option<f64>,
    median_total_trade_quote: Option<f64>,
    median_abs_dislocation_bps: Option<f64>,
    median_max_adverse_dislocation_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct OrderbookFactorTestRow {
    run_tag: String,
    factor: String,
    target: String,
    n: u64,
    factor_non_null: u64,
    pearson: Option<f64>,
    spearman: Option<f64>,
    low_bucket: i64,
    high_bucket: i64,
    low_mean: Option<f64>,
    high_mean: Option<f64>,
    high_minus_low: Option<f64>,
    low_positive_rate: Option<f64>,
    high_positive_rate: Option<f64>,
}

pub fn run_orderbook_report(config: &OrderbookConfig) -> Result<OrderbookReportSummary> {
    validate_config(config)?;
    fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    fs::create_dir_all(config.docs_dir.join("markets/mon-usdc"))
        .with_context(|| format!("failed to create {}", config.docs_dir.display()))?;
    for dataset in [
        BOOK_DEPTH_DATASET,
        FUTURES_AGG_TRADES_DATASET,
        FUTURES_KLINES_DATASET,
        FUTURES_MARK_PRICE_KLINES_DATASET,
        FUTURES_PREMIUM_INDEX_KLINES_DATASET,
    ] {
        fs::create_dir_all(external_dir(&config.data_root, dataset))?;
    }

    let outputs = build_output_paths(config);
    let minute_price_path = select_latest_part(&config.data_root, MINUTE_PRICE_REFERENCE_DATASET)?;
    let dex_lag_path = select_latest_part(&config.data_root, CEX_DEX_LAG_PANEL_DATASET)?;

    eprintln!("[mon_usdc_cex_orderbook_report] scan external Binance CSV inputs");
    let (mut snapshots, mut coverage) = read_book_depth_inputs(config)?;
    let vacuum_threshold = orderbook_vacuum_threshold(&snapshots);
    apply_liquidity_vacuum(&mut snapshots, vacuum_threshold);
    let mut orderbook_rows = build_orderbook_state_rows(&snapshots)?;
    let trade_flow_rows = read_trade_flow_inputs(config, &mut coverage)?;
    let basis = read_futures_basis_summary(config, &mut coverage)?;

    eprintln!(
        "[mon_usdc_cex_orderbook_report] read DEX-CEX lag panel: {}",
        dex_lag_path.display()
    );
    let dex_lag_rows = read_dex_lag_rows(&dex_lag_path, config.progress_interval)?;
    let minute_price_rows = count_parquet_rows(&minute_price_path)?;
    let joined_rows = build_joined_panel(config, &dex_lag_rows, &snapshots, &trade_flow_rows)?;
    let summary_rows = build_orderbook_summary(config, &joined_rows);
    let factor_rows = build_factor_tests(config, &joined_rows);
    if orderbook_rows.is_empty() {
        bail!("orderbook state is empty");
    }
    if trade_flow_rows.is_empty() {
        bail!("trade flow state is empty");
    }
    if joined_rows.is_empty() {
        bail!("joined orderbook lag panel is empty");
    }
    if summary_rows.is_empty() || factor_rows.is_empty() {
        bail!("orderbook report produced empty summary/factor outputs");
    }

    write_schema_metadata(
        &config.data_root,
        ORDERBOOK_STATE_DATASET,
        orderbook_state_schema().as_ref(),
        &["dt"],
    )?;
    write_schema_metadata(
        &config.data_root,
        TRADE_FLOW_STATE_DATASET,
        trade_flow_state_schema().as_ref(),
        &["dt"],
    )?;
    write_schema_metadata(
        &config.data_root,
        ORDERBOOK_LAG_PANEL_DATASET,
        joined_panel_schema().as_ref(),
        &["dt"],
    )?;

    orderbook_rows.sort_by_key(|row| row.minute_ts);
    let orderbook_batch = orderbook_state_batch(orderbook_state_schema(), &orderbook_rows)?;
    write_parquet_part(
        Path::new(&outputs.orderbook_state_parquet),
        orderbook_state_schema(),
        orderbook_batch,
    )?;
    let trade_batch = trade_flow_state_batch(trade_flow_state_schema(), &trade_flow_rows)?;
    write_parquet_part(
        Path::new(&outputs.trade_flow_state_parquet),
        trade_flow_state_schema(),
        trade_batch,
    )?;
    let joined_batch = joined_panel_batch(joined_panel_schema(), &joined_rows)?;
    write_parquet_part(
        Path::new(&outputs.orderbook_lag_panel_parquet),
        joined_panel_schema(),
        joined_batch,
    )?;

    write_csv(Path::new(&outputs.orderbook_summary_csv), &summary_rows)?;
    write_csv(Path::new(&outputs.orderbook_factor_tests_csv), &factor_rows)?;
    assert_no_inf(Path::new(&outputs.orderbook_summary_csv))?;
    assert_no_inf(Path::new(&outputs.orderbook_factor_tests_csv))?;

    let expected_days = expected_days(config);
    let book_days = covered_days_from_csv_names(
        &csv_files_under(&external_dir(&config.data_root, BOOK_DEPTH_DATASET))?,
        "bookDepth",
        &expected_days,
    );
    let trade_days = covered_days_from_csv_names(
        &csv_files_under(&external_dir(&config.data_root, FUTURES_AGG_TRADES_DATASET))?,
        "aggTrades",
        &expected_days,
    );
    let missing_book_depth_days = expected_days
        .iter()
        .filter(|day| !book_days.contains(*day))
        .cloned()
        .collect::<Vec<_>>();
    let missing_agg_trade_days = expected_days
        .iter()
        .filter(|day| !trade_days.contains(*day))
        .cloned()
        .collect::<Vec<_>>();
    let depth_joined_rows = joined_rows
        .iter()
        .filter(|row| row.depth_source_ts.is_some())
        .count() as u64;
    let trade_flow_joined_rows = joined_rows
        .iter()
        .filter(|row| row.trade_flow_minute_ts.is_some())
        .count() as u64;

    let report_summary = OrderbookReportSummary {
        data_root: path_string(&config.data_root),
        run_tag: config.run_tag.clone(),
        executable_path: current_executable_path(),
        exploratory_only: true,
        inputs: OrderbookInputs {
            book_depth_dir: path_string(&external_dir(&config.data_root, BOOK_DEPTH_DATASET)),
            agg_trades_dir: path_string(&external_dir(
                &config.data_root,
                FUTURES_AGG_TRADES_DATASET,
            )),
            futures_klines_dir: path_string(&external_dir(&config.data_root, FUTURES_KLINES_DATASET)),
            futures_mark_price_klines_dir: path_string(&external_dir(
                &config.data_root,
                FUTURES_MARK_PRICE_KLINES_DATASET,
            )),
            futures_premium_index_klines_dir: path_string(&external_dir(
                &config.data_root,
                FUTURES_PREMIUM_INDEX_KLINES_DATASET,
            )),
            minute_price_reference: path_string(&minute_price_path),
            cex_dex_lag_panel: path_string(&dex_lag_path),
        },
        assumptions: OrderbookAssumptions {
            symbol: "MONUSDT USD-M futures".to_string(),
            book_depth_format:
                "Binance public futures bookDepth CSV: timestamp, percentage, depth, notional"
                    .to_string(),
            depth_join_policy:
                "event rows use the latest bookDepth snapshot with source_ts <= event_timestamp"
                    .to_string(),
            trade_flow_join_policy:
                "event rows use the previous complete minute of aggTrades to avoid current-minute lookahead"
                    .to_string(),
            strict_ofi_scope:
                "free bookDepth is coarse depth distribution; strict OFI/microprice require live/Tardis L2"
                    .to_string(),
        },
        coverage: OrderbookCoverage {
            expected_days: expected_days.len() as u64,
            book_depth_csv_files: coverage.book_depth_csv_files,
            book_depth_zip_files: coverage.book_depth_zip_files,
            book_depth_rows: coverage.book_depth_rows,
            book_depth_snapshots: coverage.book_depth_snapshots,
            book_depth_state_rows: orderbook_rows.len() as u64,
            agg_trade_csv_files: coverage.agg_trade_csv_files,
            agg_trade_zip_files: coverage.agg_trade_zip_files,
            agg_trade_rows: coverage.agg_trade_rows,
            trade_flow_state_rows: trade_flow_rows.len() as u64,
            futures_kline_rows: coverage.futures_kline_rows,
            mark_price_rows: coverage.mark_price_rows,
            premium_index_rows: coverage.premium_index_rows,
            minute_price_reference_rows: minute_price_rows,
            dex_lag_rows: dex_lag_rows.len() as u64,
            joined_panel_rows: joined_rows.len() as u64,
            depth_joined_rows,
            trade_flow_joined_rows,
            missing_book_depth_days,
            missing_agg_trade_days,
        },
        basis,
        outputs,
    };
    write_json(
        Path::new(&report_summary.outputs.completion_json),
        &report_summary,
    )?;
    write_report(&report_summary, &summary_rows, &factor_rows)?;
    Ok(report_summary)
}

fn validate_config(config: &OrderbookConfig) -> Result<()> {
    if config.run_tag.trim().is_empty() {
        bail!("run_tag cannot be empty");
    }
    if config.expected_start_day > config.expected_end_day {
        bail!("expected_start_day must be <= expected_end_day");
    }
    Ok(())
}

fn external_dir(data_root: &Path, dataset: &str) -> PathBuf {
    data_root.join("external").join(dataset)
}

fn build_output_paths(config: &OrderbookConfig) -> OrderbookOutputs {
    let dt = config
        .run_tag
        .get(..10)
        .unwrap_or("orderbook")
        .replace('_', "-");
    OrderbookOutputs {
        orderbook_state_parquet: path_string(
            &config
                .data_root
                .join(DERIVED_DIR)
                .join(ORDERBOOK_STATE_DATASET)
                .join(format!("dt={dt}"))
                .join(format!(
                    "mon_usdc_{}_{}.parquet",
                    ORDERBOOK_STATE_DATASET, config.run_tag
                )),
        ),
        trade_flow_state_parquet: path_string(
            &config
                .data_root
                .join(DERIVED_DIR)
                .join(TRADE_FLOW_STATE_DATASET)
                .join(format!("dt={dt}"))
                .join(format!(
                    "mon_usdc_{}_{}.parquet",
                    TRADE_FLOW_STATE_DATASET, config.run_tag
                )),
        ),
        orderbook_lag_panel_parquet: path_string(
            &config
                .data_root
                .join(DERIVED_DIR)
                .join(ORDERBOOK_LAG_PANEL_DATASET)
                .join(format!("dt={dt}"))
                .join(format!(
                    "mon_usdc_{}_{}.parquet",
                    ORDERBOOK_LAG_PANEL_DATASET, config.run_tag
                )),
        ),
        orderbook_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_cex_orderbook_summary_{}.csv",
            config.run_tag
        ))),
        orderbook_factor_tests_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_cex_orderbook_factor_tests_{}.csv",
            config.run_tag
        ))),
        completion_json: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_cex_orderbook_completion_{}.json",
            config.run_tag
        ))),
        report: path_string(
            &config
                .docs_dir
                .join("markets/mon-usdc/v1-cex-orderbook-report.md"),
        ),
    }
}

fn read_book_depth_inputs(
    config: &OrderbookConfig,
) -> Result<(Vec<OrderbookStateRow>, ExternalCoverage)> {
    let root = external_dir(&config.data_root, BOOK_DEPTH_DATASET);
    let mut coverage = ExternalCoverage {
        book_depth_zip_files: zip_files_under(&root)?.len() as u64,
        ..ExternalCoverage::default()
    };
    let csv_files = csv_files_under(&root)?;
    coverage.book_depth_csv_files = csv_files.len() as u64;
    let mut snapshots = BTreeMap::<i64, BookSnapshotAgg>::new();
    for (index, path) in csv_files.iter().enumerate() {
        if config.progress_interval > 0 && (index + 1 == csv_files.len() || index % 25 == 0) {
            eprintln!(
                "[mon_usdc_cex_orderbook_report] read bookDepth CSV {}/{}",
                index + 1,
                csv_files.len()
            );
        }
        let mut reader = csv::ReaderBuilder::new()
            .has_headers(true)
            .from_path(path)
            .with_context(|| format!("failed to read {}", path.display()))?;
        for record in reader.records() {
            let record = record.with_context(|| format!("failed CSV record {}", path.display()))?;
            if record.len() < 4 {
                continue;
            }
            let Some(source_ts) = parse_book_depth_timestamp(record.get(0).unwrap_or_default())
            else {
                continue;
            };
            let Some(percentage) = parse_f64_cell(record.get(1)) else {
                continue;
            };
            let Some(notional) = parse_f64_cell(record.get(3)).map(|value| value.max(0.0)) else {
                continue;
            };
            let entry = snapshots
                .entry(source_ts)
                .or_insert_with(|| BookSnapshotAgg {
                    source_ts,
                    ..BookSnapshotAgg::default()
                });
            entry.row_count += 1;
            let distance = percentage.abs();
            if percentage < 0.0 {
                update_depth_buckets(
                    distance,
                    notional,
                    &mut entry.bid_notional_1pct,
                    &mut entry.bid_notional_3pct,
                    &mut entry.bid_notional_5pct,
                );
            } else if percentage > 0.0 {
                update_depth_buckets(
                    distance,
                    notional,
                    &mut entry.ask_notional_1pct,
                    &mut entry.ask_notional_3pct,
                    &mut entry.ask_notional_5pct,
                );
            }
            coverage.book_depth_rows += 1;
        }
    }
    coverage.book_depth_snapshots = snapshots.len() as u64;
    let rows = snapshots
        .into_values()
        .map(|snapshot| orderbook_row_from_snapshot(config, snapshot, None))
        .collect::<Result<Vec<_>>>()?;
    Ok((rows, coverage))
}

fn orderbook_vacuum_threshold(snapshots: &[OrderbookStateRow]) -> Option<f64> {
    let totals = snapshots
        .iter()
        .filter_map(|row| row.bid_notional_1pct.zip(row.ask_notional_1pct))
        .map(|(bid, ask)| bid + ask)
        .collect::<Vec<_>>();
    percentile(totals, 0.20)
}

fn apply_liquidity_vacuum(rows: &mut [OrderbookStateRow], threshold: Option<f64>) {
    for row in rows {
        row.liquidity_vacuum = threshold
            .zip(row.bid_notional_1pct.zip(row.ask_notional_1pct))
            .map(|(threshold, (bid, ask))| bid + ask <= threshold)
            .unwrap_or(false);
    }
}

fn build_orderbook_state_rows(snapshots: &[OrderbookStateRow]) -> Result<Vec<OrderbookStateRow>> {
    if snapshots.is_empty() {
        return Ok(Vec::new());
    }
    let mut latest_by_minute = BTreeMap::<i64, OrderbookStateRow>::new();
    for row in snapshots {
        let minute = floor_to_minute(row.source_ts);
        let mut next = row.clone();
        next.minute_ts = minute;
        next.minute_utc = utc_string(minute)?;
        next.source_lag_seconds = row.source_ts.saturating_sub(minute);
        if latest_by_minute
            .get(&minute)
            .map(|existing| row.source_ts >= existing.source_ts)
            .unwrap_or(true)
        {
            latest_by_minute.insert(minute, next);
        }
    }
    Ok(latest_by_minute.into_values().collect())
}

fn orderbook_row_from_snapshot(
    config: &OrderbookConfig,
    snapshot: BookSnapshotAgg,
    vacuum_threshold: Option<f64>,
) -> Result<OrderbookStateRow> {
    let bid_depth = snapshot.bid_notional_5pct;
    let ask_depth = snapshot.ask_notional_5pct;
    let total_1pct = snapshot
        .bid_notional_1pct
        .zip(snapshot.ask_notional_1pct)
        .map(|(bid, ask)| bid + ask);
    let total_5pct = bid_depth.zip(ask_depth).map(|(bid, ask)| bid + ask);
    Ok(OrderbookStateRow {
        run_tag: config.run_tag.clone(),
        minute_ts: floor_to_minute(snapshot.source_ts),
        minute_utc: utc_string(floor_to_minute(snapshot.source_ts))?,
        source_ts: snapshot.source_ts,
        source_utc: utc_string(snapshot.source_ts)?,
        source_lag_seconds: 0,
        bid_notional_1pct: snapshot.bid_notional_1pct,
        ask_notional_1pct: snapshot.ask_notional_1pct,
        depth_imbalance_1pct: imbalance(snapshot.bid_notional_1pct, snapshot.ask_notional_1pct),
        bid_notional_3pct: snapshot.bid_notional_3pct,
        ask_notional_3pct: snapshot.ask_notional_3pct,
        depth_imbalance_3pct: imbalance(snapshot.bid_notional_3pct, snapshot.ask_notional_3pct),
        bid_notional_5pct: snapshot.bid_notional_5pct,
        ask_notional_5pct: snapshot.ask_notional_5pct,
        depth_imbalance_5pct: imbalance(snapshot.bid_notional_5pct, snapshot.ask_notional_5pct),
        bid_notional_depth: bid_depth,
        ask_notional_depth: ask_depth,
        liquidity_slope: total_5pct
            .zip(total_1pct)
            .and_then(|(wide, tight)| finite((wide - tight) / 4.0)),
        liquidity_vacuum: vacuum_threshold
            .zip(total_1pct)
            .map(|(threshold, total)| total <= threshold)
            .unwrap_or(false),
        wall_asymmetry: bid_depth
            .zip(ask_depth)
            .and_then(|(bid, ask)| finite(((ask + EPS) / (bid + EPS)).ln())),
        snapshot_rows: snapshot.row_count,
        diagnostic_status: if bid_depth.is_some() && ask_depth.is_some() {
            "ok".to_string()
        } else {
            "partial_depth".to_string()
        },
    })
}

fn update_depth_buckets(
    distance: f64,
    notional: f64,
    one_pct: &mut Option<f64>,
    three_pct: &mut Option<f64>,
    five_pct: &mut Option<f64>,
) {
    if distance <= 1.0 {
        update_max(one_pct, notional);
    }
    if distance <= 3.0 {
        update_max(three_pct, notional);
    }
    if distance <= 5.0 {
        update_max(five_pct, notional);
    }
}

fn update_max(slot: &mut Option<f64>, value: f64) {
    if slot.map(|existing| value > existing).unwrap_or(true) {
        *slot = Some(value);
    }
}

fn read_trade_flow_inputs(
    config: &OrderbookConfig,
    coverage: &mut ExternalCoverage,
) -> Result<Vec<TradeFlowStateRow>> {
    let root = external_dir(&config.data_root, FUTURES_AGG_TRADES_DATASET);
    coverage.agg_trade_zip_files = zip_files_under(&root)?.len() as u64;
    let csv_files = csv_files_under(&root)?;
    coverage.agg_trade_csv_files = csv_files.len() as u64;
    let mut by_minute = BTreeMap::<i64, TradeFlowAgg>::new();
    for (index, path) in csv_files.iter().enumerate() {
        if config.progress_interval > 0 && (index + 1 == csv_files.len() || index % 5 == 0) {
            eprintln!(
                "[mon_usdc_cex_orderbook_report] read aggTrades CSV {}/{}",
                index + 1,
                csv_files.len()
            );
        }
        let mut reader = csv::ReaderBuilder::new()
            .has_headers(true)
            .from_path(path)
            .with_context(|| format!("failed to read {}", path.display()))?;
        for record in reader.records() {
            let record = record.with_context(|| format!("failed CSV record {}", path.display()))?;
            if record.len() < 7 {
                continue;
            }
            let Some(price) = parse_f64_cell(record.get(1)) else {
                continue;
            };
            let Some(quantity) = parse_f64_cell(record.get(2)) else {
                continue;
            };
            let Some(raw_ts) = parse_i64_cell(record.get(5)) else {
                continue;
            };
            let buyer_maker = record
                .get(6)
                .map(|value| value.eq_ignore_ascii_case("true"))
                .unwrap_or(false);
            if price <= 0.0 || quantity <= 0.0 {
                continue;
            }
            let quote = price * quantity;
            let minute_ts = floor_to_minute(epoch_to_seconds(raw_ts));
            let entry = by_minute.entry(minute_ts).or_insert_with(|| TradeFlowAgg {
                minute_ts,
                ..TradeFlowAgg::default()
            });
            entry.trade_count += 1;
            if buyer_maker {
                entry.taker_sell_quote += quote;
            } else {
                entry.taker_buy_quote += quote;
            }
            entry.max_trade_quote = entry.max_trade_quote.max(quote);
            coverage.agg_trade_rows += 1;
        }
    }
    by_minute
        .into_values()
        .map(|agg| trade_flow_row_from_agg(config, agg))
        .collect()
}

fn trade_flow_row_from_agg(
    config: &OrderbookConfig,
    agg: TradeFlowAgg,
) -> Result<TradeFlowStateRow> {
    let total_quote = agg.taker_buy_quote + agg.taker_sell_quote;
    Ok(TradeFlowStateRow {
        run_tag: config.run_tag.clone(),
        minute_ts: agg.minute_ts,
        minute_utc: utc_string(agg.minute_ts)?,
        trade_count: agg.trade_count,
        taker_buy_quote: agg.taker_buy_quote,
        taker_sell_quote: agg.taker_sell_quote,
        total_quote,
        trade_imbalance: safe_div(agg.taker_buy_quote - agg.taker_sell_quote, total_quote),
        sweep_intensity: safe_div(agg.max_trade_quote, total_quote),
        burst_trade_count: agg.trade_count,
        max_trade_quote: if agg.max_trade_quote > 0.0 {
            Some(agg.max_trade_quote)
        } else {
            None
        },
        diagnostic_status: if agg.trade_count > 0 { "ok" } else { "empty" }.to_string(),
    })
}

fn read_futures_basis_summary(
    config: &OrderbookConfig,
    coverage: &mut ExternalCoverage,
) -> Result<FuturesBasisSummary> {
    let trade = read_kline_close_map(&external_dir(&config.data_root, FUTURES_KLINES_DATASET))?;
    let mark = read_kline_close_map(&external_dir(
        &config.data_root,
        FUTURES_MARK_PRICE_KLINES_DATASET,
    ))?;
    let premium = read_kline_close_map(&external_dir(
        &config.data_root,
        FUTURES_PREMIUM_INDEX_KLINES_DATASET,
    ))?;
    coverage.futures_kline_rows = trade.len() as u64;
    coverage.mark_price_rows = mark.len() as u64;
    coverage.premium_index_rows = premium.len() as u64;
    let mut basis = Vec::new();
    let mut premiums = Vec::new();
    for (minute, trade_close) in &trade {
        if let Some(mark_close) = mark.get(minute) {
            if *trade_close > 0.0 && *mark_close > 0.0 {
                basis.push(10_000.0 * (trade_close / mark_close).ln());
            }
        }
        if let Some(premium_close) = premium.get(minute) {
            premiums.push(10_000.0 * premium_close);
        }
    }
    let abs_basis = basis.iter().map(|value| value.abs()).collect::<Vec<_>>();
    let abs_premium = premiums.iter().map(|value| value.abs()).collect::<Vec<_>>();
    Ok(FuturesBasisSummary {
        common_rows: basis.len() as u64,
        median_trade_mark_basis_bps: median(basis.clone()),
        median_abs_trade_mark_basis_bps: median(abs_basis.clone()),
        p90_abs_trade_mark_basis_bps: percentile(abs_basis, 0.90),
        median_premium_index_bps: median(premiums.clone()),
        median_abs_premium_index_bps: median(abs_premium.clone()),
        p90_abs_premium_index_bps: percentile(abs_premium, 0.90),
    })
}

fn read_kline_close_map(root: &Path) -> Result<BTreeMap<i64, f64>> {
    let mut out = BTreeMap::new();
    for path in csv_files_under(root)? {
        let mut reader = csv::ReaderBuilder::new()
            .has_headers(false)
            .from_path(&path)
            .with_context(|| format!("failed to read {}", path.display()))?;
        for record in reader.records() {
            let record = record.with_context(|| format!("failed CSV record {}", path.display()))?;
            if record.len() < 5 {
                continue;
            }
            let Some(open_time_raw) = parse_i64_cell(record.get(0)) else {
                continue;
            };
            let Some(close) = parse_f64_cell(record.get(4)) else {
                continue;
            };
            if close.is_finite() {
                out.insert(floor_to_minute(epoch_to_seconds(open_time_raw)), close);
            }
        }
    }
    Ok(out)
}

fn build_joined_panel(
    config: &OrderbookConfig,
    dex_rows: &[DexLagRow],
    orderbook_rows: &[OrderbookStateRow],
    trade_rows: &[TradeFlowStateRow],
) -> Result<Vec<JoinedOrderbookLagRow>> {
    let depth_times = orderbook_rows
        .iter()
        .map(|row| row.source_ts)
        .collect::<Vec<_>>();
    let trade_by_minute = trade_rows
        .iter()
        .map(|row| (row.minute_ts, row))
        .collect::<BTreeMap<_, _>>();
    let mut joined = Vec::with_capacity(dex_rows.len());
    for (index, row) in dex_rows.iter().enumerate() {
        if config.progress_interval > 0
            && (index + 1 == dex_rows.len() || index % config.progress_interval == 0)
        {
            eprintln!(
                "[mon_usdc_cex_orderbook_report] join orderbook panel {}/{}",
                index + 1,
                dex_rows.len()
            );
        }
        let depth =
            asof_index(&depth_times, row.event_timestamp).and_then(|idx| orderbook_rows.get(idx));
        let trade_minute = row.minute_ts - 60;
        let trade = trade_by_minute.get(&trade_minute).copied();
        let mut status = Vec::new();
        status.push(row.diagnostic_status.clone());
        if depth.is_none() {
            status.push("missing_depth".to_string());
        }
        if trade.is_none() {
            status.push("missing_trade_flow".to_string());
        }
        joined.push(JoinedOrderbookLagRow {
            run_tag: config.run_tag.clone(),
            source_lag_run_tag: row.source_run_tag.clone(),
            block_number: row.block_number,
            event_timestamp: row.event_timestamp,
            event_time_utc: row.event_time_utc.clone(),
            minute_ts: row.minute_ts,
            split: row.split.clone(),
            transaction_hash: row.transaction_hash.clone(),
            log_index: row.log_index,
            pool_address: row.pool_address.clone(),
            dex_id: row.dex_id.clone(),
            family: row.family.clone(),
            direction: row.direction.clone(),
            quote_abs: row.quote_abs,
            pool_price: row.pool_price,
            anchor_price: row.anchor_price,
            anchor_source: row.anchor_source.clone(),
            dislocation_bps: row.dislocation_bps,
            abs_dislocation_bps: row.abs_dislocation_bps,
            cost_adjusted_dislocation_bps: row.cost_adjusted_dislocation_bps,
            half_life_minutes: row.half_life_minutes,
            time_to_reenter_band_minutes: row.time_to_reenter_band_minutes,
            max_adverse_dislocation_bps: row.max_adverse_dislocation_bps,
            depth_source_ts: depth.map(|value| value.source_ts),
            depth_source_lag_seconds: depth
                .map(|value| row.event_timestamp.saturating_sub(value.source_ts).max(0) as u64),
            depth_imbalance_1pct: depth.and_then(|value| value.depth_imbalance_1pct),
            depth_imbalance_3pct: depth.and_then(|value| value.depth_imbalance_3pct),
            depth_imbalance_5pct: depth.and_then(|value| value.depth_imbalance_5pct),
            bid_notional_depth: depth.and_then(|value| value.bid_notional_depth),
            ask_notional_depth: depth.and_then(|value| value.ask_notional_depth),
            liquidity_slope: depth.and_then(|value| value.liquidity_slope),
            liquidity_vacuum: depth.map(|value| value.liquidity_vacuum),
            wall_asymmetry: depth.and_then(|value| value.wall_asymmetry),
            trade_flow_minute_ts: trade.map(|value| value.minute_ts),
            trade_source_lag_minutes: trade.map(|_| 1),
            taker_buy_quote: trade.map(|value| value.taker_buy_quote),
            taker_sell_quote: trade.map(|value| value.taker_sell_quote),
            total_trade_quote: trade.map(|value| value.total_quote),
            trade_imbalance: trade.and_then(|value| value.trade_imbalance),
            sweep_intensity: trade.and_then(|value| value.sweep_intensity),
            burst_trade_count: trade.map(|value| value.burst_trade_count),
            max_trade_quote: trade.and_then(|value| value.max_trade_quote),
            diagnostic_status: status.join("|"),
        });
    }
    Ok(joined)
}

fn asof_index(sorted_times: &[i64], target: i64) -> Option<usize> {
    match sorted_times.binary_search(&target) {
        Ok(index) => Some(index),
        Err(0) => None,
        Err(index) => Some(index - 1),
    }
}

fn build_orderbook_summary(
    config: &OrderbookConfig,
    rows: &[JoinedOrderbookLagRow],
) -> Vec<OrderbookSummaryRow> {
    let mut groups = BTreeMap::<(String, String), Vec<&JoinedOrderbookLagRow>>::new();
    for row in rows {
        groups
            .entry(("overall".to_string(), "all".to_string()))
            .or_default()
            .push(row);
        groups
            .entry(("split".to_string(), row.split.clone()))
            .or_default()
            .push(row);
        groups
            .entry(("pool".to_string(), row.pool_address.clone()))
            .or_default()
            .push(row);
        groups
            .entry(("dex".to_string(), row.dex_id.clone()))
            .or_default()
            .push(row);
        groups
            .entry((
                "depth_vacuum".to_string(),
                row.liquidity_vacuum
                    .map(|value| value.to_string())
                    .unwrap_or_else(|| "missing".to_string()),
            ))
            .or_default()
            .push(row);
        groups
            .entry((
                "trade_imbalance_sign".to_string(),
                sign_bucket(row.trade_imbalance),
            ))
            .or_default()
            .push(row);
        groups
            .entry(("wall_side".to_string(), wall_bucket(row.wall_asymmetry)))
            .or_default()
            .push(row);
    }
    groups
        .into_iter()
        .map(|((group, group_value), group_rows)| {
            summary_row(config, &group, &group_value, &group_rows)
        })
        .collect()
}

fn summary_row(
    config: &OrderbookConfig,
    group: &str,
    group_value: &str,
    rows: &[&JoinedOrderbookLagRow],
) -> OrderbookSummaryRow {
    let depth_joined = rows
        .iter()
        .filter(|row| row.depth_source_ts.is_some())
        .count() as u64;
    let trade_joined = rows
        .iter()
        .filter(|row| row.trade_flow_minute_ts.is_some())
        .count() as u64;
    let vacuum_values = rows
        .iter()
        .filter_map(|row| {
            row.liquidity_vacuum
                .map(|value| if value { 1.0 } else { 0.0 })
        })
        .collect::<Vec<_>>();
    let cost_values = rows
        .iter()
        .filter_map(|row| row.cost_adjusted_dislocation_bps)
        .collect::<Vec<_>>();
    OrderbookSummaryRow {
        run_tag: config.run_tag.clone(),
        group: group.to_string(),
        group_value: group_value.to_string(),
        rows: rows.len() as u64,
        depth_joined_rows: depth_joined,
        depth_coverage_rate: safe_div(depth_joined as f64, rows.len() as f64),
        trade_flow_joined_rows: trade_joined,
        trade_flow_coverage_rate: safe_div(trade_joined as f64, rows.len() as f64),
        liquidity_vacuum_rate: mean(&vacuum_values),
        cost_adjusted_positive_rate: positive_rate(&cost_values),
        median_depth_imbalance_1pct: median(
            rows.iter()
                .filter_map(|row| row.depth_imbalance_1pct)
                .collect(),
        ),
        median_depth_imbalance_5pct: median(
            rows.iter()
                .filter_map(|row| row.depth_imbalance_5pct)
                .collect(),
        ),
        median_bid_notional_depth: median(
            rows.iter()
                .filter_map(|row| row.bid_notional_depth)
                .collect(),
        ),
        median_ask_notional_depth: median(
            rows.iter()
                .filter_map(|row| row.ask_notional_depth)
                .collect(),
        ),
        median_wall_asymmetry: median(rows.iter().filter_map(|row| row.wall_asymmetry).collect()),
        median_trade_imbalance: median(rows.iter().filter_map(|row| row.trade_imbalance).collect()),
        median_total_trade_quote: median(
            rows.iter()
                .filter_map(|row| row.total_trade_quote)
                .collect(),
        ),
        median_abs_dislocation_bps: median(
            rows.iter()
                .filter_map(|row| row.abs_dislocation_bps)
                .collect(),
        ),
        median_max_adverse_dislocation_bps: median(
            rows.iter()
                .filter_map(|row| row.max_adverse_dislocation_bps)
                .collect(),
        ),
    }
}

fn build_factor_tests(
    config: &OrderbookConfig,
    rows: &[JoinedOrderbookLagRow],
) -> Vec<OrderbookFactorTestRow> {
    let factors = [
        "depth_imbalance_1pct",
        "depth_imbalance_3pct",
        "depth_imbalance_5pct",
        "bid_notional_depth",
        "ask_notional_depth",
        "liquidity_slope",
        "liquidity_vacuum",
        "wall_asymmetry",
        "trade_imbalance",
        "sweep_intensity",
        "burst_trade_count",
        "max_trade_quote",
        "total_trade_quote",
    ];
    let targets = [
        "dislocation_bps",
        "abs_dislocation_bps",
        "cost_adjusted_dislocation_bps",
        "max_adverse_dislocation_bps",
    ];
    let mut out = Vec::new();
    for factor in factors {
        let factor_values = rows
            .iter()
            .map(|row| factor_value(row, factor))
            .collect::<Vec<_>>();
        for target in targets {
            let target_values = rows
                .iter()
                .map(|row| target_value(row, target))
                .collect::<Vec<_>>();
            if let Some(row) = factor_test(
                &config.run_tag,
                factor,
                target,
                &factor_values,
                &target_values,
                500,
            ) {
                out.push(row);
            }
        }
    }
    out.sort_by(|a, b| {
        a.target
            .cmp(&b.target)
            .then_with(|| desc_option_abs_f64(a.spearman, b.spearman))
            .then_with(|| b.n.cmp(&a.n))
    });
    out
}

fn factor_value(row: &JoinedOrderbookLagRow, factor: &str) -> Option<f64> {
    match factor {
        "depth_imbalance_1pct" => row.depth_imbalance_1pct,
        "depth_imbalance_3pct" => row.depth_imbalance_3pct,
        "depth_imbalance_5pct" => row.depth_imbalance_5pct,
        "bid_notional_depth" => row.bid_notional_depth,
        "ask_notional_depth" => row.ask_notional_depth,
        "liquidity_slope" => row.liquidity_slope,
        "liquidity_vacuum" => row
            .liquidity_vacuum
            .map(|value| if value { 1.0 } else { 0.0 }),
        "wall_asymmetry" => row.wall_asymmetry,
        "trade_imbalance" => row.trade_imbalance,
        "sweep_intensity" => row.sweep_intensity,
        "burst_trade_count" => row.burst_trade_count.map(|value| value as f64),
        "max_trade_quote" => row.max_trade_quote,
        "total_trade_quote" => row.total_trade_quote,
        _ => None,
    }
}

fn target_value(row: &JoinedOrderbookLagRow, target: &str) -> Option<f64> {
    match target {
        "dislocation_bps" => row.dislocation_bps,
        "abs_dislocation_bps" => row.abs_dislocation_bps,
        "cost_adjusted_dislocation_bps" => row.cost_adjusted_dislocation_bps,
        "max_adverse_dislocation_bps" => row.max_adverse_dislocation_bps,
        _ => None,
    }
}

fn factor_test(
    run_tag: &str,
    factor: &str,
    target: &str,
    factor_values: &[Option<f64>],
    target_values: &[Option<f64>],
    min_rows: usize,
) -> Option<OrderbookFactorTestRow> {
    let mut pairs = Vec::<(f64, f64)>::new();
    for (factor_value, target_value) in factor_values.iter().zip(target_values) {
        let Some(factor_value) = factor_value
            .as_ref()
            .copied()
            .filter(|value| value.is_finite())
        else {
            continue;
        };
        let Some(target_value) = target_value
            .as_ref()
            .copied()
            .filter(|value| value.is_finite())
        else {
            continue;
        };
        pairs.push((factor_value, target_value));
    }
    if pairs.len() < min_rows {
        return None;
    }
    let factors = pairs.iter().map(|(factor, _)| *factor).collect::<Vec<_>>();
    let targets = pairs.iter().map(|(_, target)| *target).collect::<Vec<_>>();
    let buckets = qcut_buckets(&factors, 3)?;
    let low = pairs
        .iter()
        .zip(&buckets)
        .filter(|(_, bucket)| **bucket == 0)
        .map(|((_, target), _)| *target)
        .collect::<Vec<_>>();
    let high = pairs
        .iter()
        .zip(&buckets)
        .filter(|(_, bucket)| **bucket == 2)
        .map(|((_, target), _)| *target)
        .collect::<Vec<_>>();
    if low.is_empty() || high.is_empty() {
        return None;
    }
    Some(OrderbookFactorTestRow {
        run_tag: run_tag.to_string(),
        factor: factor.to_string(),
        target: target.to_string(),
        n: pairs.len() as u64,
        factor_non_null: pairs.len() as u64,
        pearson: pearson(&factors, &targets),
        spearman: spearman(&factors, &targets),
        low_bucket: 0,
        high_bucket: 2,
        low_mean: mean(&low),
        high_mean: mean(&high),
        high_minus_low: mean(&high)
            .zip(mean(&low))
            .and_then(|(high, low)| finite(high - low)),
        low_positive_rate: positive_rate(&low),
        high_positive_rate: positive_rate(&high),
    })
}

fn qcut_buckets(values: &[f64], buckets: usize) -> Option<Vec<usize>> {
    if values.len() < buckets || buckets == 0 {
        return None;
    }
    let unique = values
        .iter()
        .map(|value| value.to_bits())
        .collect::<BTreeSet<_>>();
    if unique.len() < buckets {
        return None;
    }
    let mut indexed = values
        .iter()
        .copied()
        .enumerate()
        .collect::<Vec<(usize, f64)>>();
    indexed.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
    let mut out = vec![0usize; values.len()];
    let len = indexed.len();
    for (position, (index, _)) in indexed.into_iter().enumerate() {
        out[index] = ((position * buckets) / len).min(buckets - 1);
    }
    Some(out)
}

fn sign_bucket(value: Option<f64>) -> String {
    match value {
        Some(value) if value > 0.05 => "buy_pressure".to_string(),
        Some(value) if value < -0.05 => "sell_pressure".to_string(),
        Some(_) => "balanced".to_string(),
        None => "missing".to_string(),
    }
}

fn wall_bucket(value: Option<f64>) -> String {
    match value {
        Some(value) if value > 0.05 => "ask_wall".to_string(),
        Some(value) if value < -0.05 => "bid_wall".to_string(),
        Some(_) => "balanced".to_string(),
        None => "missing".to_string(),
    }
}

fn read_dex_lag_rows(path: &Path, progress_interval: usize) -> Result<Vec<DexLagRow>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(8192)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    let mut out = Vec::new();
    let mut batch_count = 0usize;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        batch_count += 1;
        if progress_interval > 0 && batch_count % 100 == 0 {
            eprintln!(
                "[mon_usdc_cex_orderbook_report] read DEX lag batches: {} rows",
                out.len()
            );
        }
        let run_tag = string_column(&batch, "run_tag")?;
        let block_number = u64_column(&batch, "block_number")?;
        let event_time_utc = string_column(&batch, "event_time_utc")?;
        let minute_timestamp = u64_column(&batch, "minute_timestamp")?;
        let split = string_column(&batch, "split")?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        let log_index = u64_column(&batch, "log_index")?;
        let pool_address = string_column(&batch, "pool_address")?;
        let dex_id = string_column(&batch, "dex_id")?;
        let family = string_column(&batch, "family")?;
        let direction = string_column(&batch, "direction")?;
        let quote_abs = f64_column(&batch, "quote_abs")?;
        let pool_price = f64_column(&batch, "pool_price")?;
        let anchor_price = f64_column(&batch, "anchor_price")?;
        let anchor_source = string_column(&batch, "anchor_source")?;
        let dislocation_bps = f64_column(&batch, "dislocation_bps")?;
        let abs_dislocation_bps = f64_column(&batch, "abs_dislocation_bps")?;
        let cost_adjusted_dislocation_bps = f64_column(&batch, "cost_adjusted_dislocation_bps")?;
        let half_life_minutes = u64_column(&batch, "half_life_minutes")?;
        let time_to_reenter_band_minutes = u64_column(&batch, "time_to_reenter_band_minutes")?;
        let max_adverse_dislocation_bps = f64_column(&batch, "max_adverse_dislocation_bps")?;
        let diagnostic_status = string_column(&batch, "diagnostic_status")?;
        for index in 0..batch.num_rows() {
            let event_time = string_value(event_time_utc, index);
            let event_timestamp = parse_utc_timestamp(&event_time)
                .unwrap_or_else(|| u64_value(minute_timestamp, index) as i64);
            out.push(DexLagRow {
                source_run_tag: string_value(run_tag, index),
                block_number: u64_value(block_number, index),
                event_timestamp,
                event_time_utc: event_time,
                minute_ts: u64_value(minute_timestamp, index) as i64,
                split: string_value(split, index),
                transaction_hash: string_value(transaction_hash, index),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                direction: string_value(direction, index),
                quote_abs: f64_option(quote_abs, index),
                pool_price: f64_option(pool_price, index),
                anchor_price: f64_option(anchor_price, index),
                anchor_source: string_value(anchor_source, index),
                dislocation_bps: f64_option(dislocation_bps, index),
                abs_dislocation_bps: f64_option(abs_dislocation_bps, index),
                cost_adjusted_dislocation_bps: f64_option(cost_adjusted_dislocation_bps, index),
                half_life_minutes: u64_option(half_life_minutes, index),
                time_to_reenter_band_minutes: u64_option(time_to_reenter_band_minutes, index),
                max_adverse_dislocation_bps: f64_option(max_adverse_dislocation_bps, index),
                diagnostic_status: string_value(diagnostic_status, index),
            });
        }
    }
    Ok(out)
}

fn count_parquet_rows(path: &Path) -> Result<u64> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    Ok(builder.metadata().file_metadata().num_rows().max(0) as u64)
}

fn select_latest_part(data_root: &Path, dataset: &str) -> Result<PathBuf> {
    let root = data_root.join(DERIVED_DIR).join(dataset);
    let files = parquet_files_under(&root)?;
    files
        .into_iter()
        .max_by_key(|path| fs::metadata(path).and_then(|meta| meta.modified()).ok())
        .ok_or_else(|| {
            anyhow!(
                "no parquet part found for dataset {dataset} under {}",
                root.display()
            )
        })
}

fn csv_files_under(root: &Path) -> Result<Vec<PathBuf>> {
    let mut files = Vec::new();
    if !root.exists() {
        return Ok(files);
    }
    collect_files(root, &mut files)?;
    files.retain(|path| {
        path.extension()
            .and_then(|value| value.to_str())
            .map(|value| value.eq_ignore_ascii_case("csv"))
            .unwrap_or(false)
    });
    files.sort();
    Ok(files)
}

fn zip_files_under(root: &Path) -> Result<Vec<PathBuf>> {
    let mut files = Vec::new();
    if !root.exists() {
        return Ok(files);
    }
    collect_files(root, &mut files)?;
    files.retain(|path| {
        path.extension()
            .and_then(|value| value.to_str())
            .map(|value| value.eq_ignore_ascii_case("zip"))
            .unwrap_or(false)
    });
    files.sort();
    Ok(files)
}

fn collect_files(root: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
    for entry in fs::read_dir(root).with_context(|| format!("failed to read {}", root.display()))? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_files(&path, files)?;
        } else if path.is_file() {
            files.push(path);
        }
    }
    Ok(())
}

fn covered_days_from_csv_names(
    paths: &[PathBuf],
    marker: &str,
    expected_days: &[String],
) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    for path in paths {
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or_default();
        if !name.contains(marker) {
            continue;
        }
        let mut matched_specific_day = false;
        for day in expected_days {
            if name.contains(day) {
                matched_specific_day = true;
                out.insert(day.clone());
            }
        }
        if !matched_specific_day {
            for day in expected_days {
                if let Some(month) = day.get(..7) {
                    let monthly_csv = format!("{month}.csv");
                    let monthly_zip = format!("{month}.zip");
                    if name.contains(&monthly_csv) || name.contains(&monthly_zip) {
                        out.insert(day.clone());
                    }
                }
            }
        }
    }
    out
}

fn expected_days(config: &OrderbookConfig) -> Vec<String> {
    let Some(mut cursor) = parse_day(&config.expected_start_day) else {
        return Vec::new();
    };
    let Some(end) = parse_day(&config.expected_end_day) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    while cursor <= end {
        out.push(format!("{:04}-{:02}-{:02}", cursor.0, cursor.1, cursor.2));
        cursor = next_day(cursor);
    }
    out
}

fn parse_day(value: &str) -> Option<(i32, u32, u32)> {
    let mut parts = value.split('-');
    Some((
        parts.next()?.parse().ok()?,
        parts.next()?.parse().ok()?,
        parts.next()?.parse().ok()?,
    ))
}

fn next_day((year, month, day): (i32, u32, u32)) -> (i32, u32, u32) {
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap_year(year) => 29,
        2 => 28,
        _ => 30,
    };
    if day < days {
        (year, month, day + 1)
    } else if month < 12 {
        (year, month + 1, 1)
    } else {
        (year + 1, 1, 1)
    }
}

fn is_leap_year(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

fn parse_book_depth_timestamp(value: &str) -> Option<i64> {
    let value = value.trim();
    if value.len() < 19 {
        return None;
    }
    let year = value.get(0..4)?.parse::<i32>().ok()?;
    let month = value.get(5..7)?.parse::<u32>().ok()?;
    let day = value.get(8..10)?.parse::<u32>().ok()?;
    let hour = value.get(11..13)?.parse::<u32>().ok()?;
    let minute = value.get(14..16)?.parse::<u32>().ok()?;
    let second = value.get(17..19)?.parse::<u32>().ok()?;
    chrono::NaiveDate::from_ymd_opt(year, month, day)
        .and_then(|date| date.and_hms_opt(hour, minute, second))
        .map(|dt| dt.and_utc().timestamp())
}

fn parse_i64_cell(value: Option<&str>) -> Option<i64> {
    value?.trim().parse::<i64>().ok()
}

fn parse_f64_cell(value: Option<&str>) -> Option<f64> {
    value?.trim().parse::<f64>().ok().and_then(finite)
}

fn epoch_to_seconds(value: i64) -> i64 {
    match value.abs() {
        raw if raw >= 1_000_000_000_000_000_000 => value / 1_000_000_000,
        raw if raw >= 1_000_000_000_000_000 => value / 1_000_000,
        raw if raw >= 1_000_000_000_000 => value / 1_000,
        _ => value,
    }
}

fn imbalance(left: Option<f64>, right: Option<f64>) -> Option<f64> {
    left.zip(right)
        .and_then(|(left, right)| safe_div(left - right, left + right))
}

fn safe_div(numerator: f64, denominator: f64) -> Option<f64> {
    if !numerator.is_finite() || !denominator.is_finite() || denominator.abs() < EPS {
        None
    } else {
        finite(numerator / denominator)
    }
}

fn finite(value: f64) -> Option<f64> {
    if value.is_finite() { Some(value) } else { None }
}

fn floor_to_minute(timestamp: i64) -> i64 {
    timestamp - timestamp.rem_euclid(60)
}

fn utc_string(timestamp: i64) -> Result<String> {
    Ok(DateTime::<Utc>::from_timestamp(timestamp, 0)
        .ok_or_else(|| anyhow!("invalid timestamp {timestamp}"))?
        .to_rfc3339_opts(SecondsFormat::Secs, true))
}

fn parse_utc_timestamp(value: &str) -> Option<i64> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|value| value.timestamp())
}

fn median(mut values: Vec<f64>) -> Option<f64> {
    values.retain(|value| value.is_finite());
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        finite((values[mid - 1] + values[mid]) / 2.0)
    } else {
        finite(values[mid])
    }
}

fn percentile(mut values: Vec<f64>, q: f64) -> Option<f64> {
    values.retain(|value| value.is_finite());
    if values.is_empty() || !q.is_finite() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let q = q.clamp(0.0, 1.0);
    let position = (values.len() - 1) as f64 * q;
    let low = position.floor() as usize;
    let high = position.ceil() as usize;
    if low == high {
        Some(values[low])
    } else {
        let weight = position - low as f64;
        finite(values[low] * (1.0 - weight) + values[high] * weight)
    }
}

fn mean(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    finite(values.iter().sum::<f64>() / values.len() as f64)
}

fn positive_rate(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    finite(values.iter().filter(|value| **value > 0.0).count() as f64 / values.len() as f64)
}

fn pearson(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 2 {
        return None;
    }
    let mean_x = xs.iter().sum::<f64>() / xs.len() as f64;
    let mean_y = ys.iter().sum::<f64>() / ys.len() as f64;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    for (x, y) in xs.iter().zip(ys) {
        let dx = *x - mean_x;
        let dy = *y - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    if var_x <= 0.0 || var_y <= 0.0 {
        None
    } else {
        finite(cov / (var_x.sqrt() * var_y.sqrt()))
    }
}

fn spearman(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 2 {
        return None;
    }
    let xr = average_ranks(xs);
    let yr = average_ranks(ys);
    pearson(&xr, &yr)
}

fn average_ranks(values: &[f64]) -> Vec<f64> {
    let mut indexed = values
        .iter()
        .copied()
        .enumerate()
        .collect::<Vec<(usize, f64)>>();
    indexed.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
    let mut ranks = vec![0.0; values.len()];
    let mut start = 0usize;
    while start < indexed.len() {
        let mut end = start + 1;
        while end < indexed.len() && indexed[end].1 == indexed[start].1 {
            end += 1;
        }
        let rank = (start + 1 + end) as f64 / 2.0;
        for (index, _) in &indexed[start..end] {
            ranks[*index] = rank;
        }
        start = end;
    }
    ranks
}

fn desc_option_abs_f64(a: Option<f64>, b: Option<f64>) -> std::cmp::Ordering {
    match (a, b) {
        (Some(a), Some(b)) => b.abs().total_cmp(&a.abs()),
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => std::cmp::Ordering::Equal,
    }
}

fn orderbook_state_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_u64("minute_timestamp", false),
        field_utf8("minute_utc", false),
        field_u64("source_timestamp", false),
        field_utf8("source_utc", false),
        field_u64("source_lag_seconds", false),
        field_f64("bid_notional_1pct", true),
        field_f64("ask_notional_1pct", true),
        field_f64("depth_imbalance_1pct", true),
        field_f64("bid_notional_3pct", true),
        field_f64("ask_notional_3pct", true),
        field_f64("depth_imbalance_3pct", true),
        field_f64("bid_notional_5pct", true),
        field_f64("ask_notional_5pct", true),
        field_f64("depth_imbalance_5pct", true),
        field_f64("bid_notional_depth", true),
        field_f64("ask_notional_depth", true),
        field_f64("liquidity_slope", true),
        Field::new("liquidity_vacuum", DataType::Boolean, false),
        field_f64("wall_asymmetry", true),
        field_u64("snapshot_rows", false),
        field_utf8("diagnostic_status", false),
    ]))
}

fn orderbook_state_batch(schema: SchemaRef, rows: &[OrderbookStateRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            u64s(rows.iter().map(|row| row.minute_ts.max(0) as u64)),
            strings(rows.iter().map(|row| row.minute_utc.clone())),
            u64s(rows.iter().map(|row| row.source_ts.max(0) as u64)),
            strings(rows.iter().map(|row| row.source_utc.clone())),
            u64s(rows.iter().map(|row| row.source_lag_seconds.max(0) as u64)),
            opt_f64s(rows.iter().map(|row| row.bid_notional_1pct)),
            opt_f64s(rows.iter().map(|row| row.ask_notional_1pct)),
            opt_f64s(rows.iter().map(|row| row.depth_imbalance_1pct)),
            opt_f64s(rows.iter().map(|row| row.bid_notional_3pct)),
            opt_f64s(rows.iter().map(|row| row.ask_notional_3pct)),
            opt_f64s(rows.iter().map(|row| row.depth_imbalance_3pct)),
            opt_f64s(rows.iter().map(|row| row.bid_notional_5pct)),
            opt_f64s(rows.iter().map(|row| row.ask_notional_5pct)),
            opt_f64s(rows.iter().map(|row| row.depth_imbalance_5pct)),
            opt_f64s(rows.iter().map(|row| row.bid_notional_depth)),
            opt_f64s(rows.iter().map(|row| row.ask_notional_depth)),
            opt_f64s(rows.iter().map(|row| row.liquidity_slope)),
            bools(rows.iter().map(|row| row.liquidity_vacuum)),
            opt_f64s(rows.iter().map(|row| row.wall_asymmetry)),
            u64s(rows.iter().map(|row| row.snapshot_rows)),
            strings(rows.iter().map(|row| row.diagnostic_status.clone())),
        ],
    )
    .context("failed to build orderbook state batch")
}

fn trade_flow_state_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_u64("minute_timestamp", false),
        field_utf8("minute_utc", false),
        field_u64("trade_count", false),
        field_f64("taker_buy_quote", false),
        field_f64("taker_sell_quote", false),
        field_f64("total_quote", false),
        field_f64("trade_imbalance", true),
        field_f64("sweep_intensity", true),
        field_u64("burst_trade_count", false),
        field_f64("max_trade_quote", true),
        field_utf8("diagnostic_status", false),
    ]))
}

fn trade_flow_state_batch(schema: SchemaRef, rows: &[TradeFlowStateRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            u64s(rows.iter().map(|row| row.minute_ts.max(0) as u64)),
            strings(rows.iter().map(|row| row.minute_utc.clone())),
            u64s(rows.iter().map(|row| row.trade_count)),
            f64s(rows.iter().map(|row| row.taker_buy_quote)),
            f64s(rows.iter().map(|row| row.taker_sell_quote)),
            f64s(rows.iter().map(|row| row.total_quote)),
            opt_f64s(rows.iter().map(|row| row.trade_imbalance)),
            opt_f64s(rows.iter().map(|row| row.sweep_intensity)),
            u64s(rows.iter().map(|row| row.burst_trade_count)),
            opt_f64s(rows.iter().map(|row| row.max_trade_quote)),
            strings(rows.iter().map(|row| row.diagnostic_status.clone())),
        ],
    )
    .context("failed to build trade flow state batch")
}

fn joined_panel_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_utf8("source_lag_run_tag", false),
        field_u64("block_number", false),
        field_u64("event_timestamp", false),
        field_utf8("event_time_utc", false),
        field_u64("minute_timestamp", false),
        field_utf8("split", false),
        field_utf8("transaction_hash", false),
        field_u64("log_index", false),
        field_utf8("pool_address", false),
        field_utf8("dex_id", false),
        field_utf8("family", false),
        field_utf8("direction", false),
        field_f64("quote_abs", true),
        field_f64("pool_price", true),
        field_f64("anchor_price", true),
        field_utf8("anchor_source", false),
        field_f64("dislocation_bps", true),
        field_f64("abs_dislocation_bps", true),
        field_f64("cost_adjusted_dislocation_bps", true),
        field_u64("half_life_minutes", true),
        field_u64("time_to_reenter_band_minutes", true),
        field_f64("max_adverse_dislocation_bps", true),
        field_u64("depth_source_timestamp", true),
        field_u64("depth_source_lag_seconds", true),
        field_f64("depth_imbalance_1pct", true),
        field_f64("depth_imbalance_3pct", true),
        field_f64("depth_imbalance_5pct", true),
        field_f64("bid_notional_depth", true),
        field_f64("ask_notional_depth", true),
        field_f64("liquidity_slope", true),
        Field::new("liquidity_vacuum", DataType::Boolean, true),
        field_f64("wall_asymmetry", true),
        field_u64("trade_flow_minute_timestamp", true),
        field_u64("trade_source_lag_minutes", true),
        field_f64("taker_buy_quote", true),
        field_f64("taker_sell_quote", true),
        field_f64("total_trade_quote", true),
        field_f64("trade_imbalance", true),
        field_f64("sweep_intensity", true),
        field_u64("burst_trade_count", true),
        field_f64("max_trade_quote", true),
        field_utf8("diagnostic_status", false),
    ]))
}

fn joined_panel_batch(schema: SchemaRef, rows: &[JoinedOrderbookLagRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            strings(rows.iter().map(|row| row.source_lag_run_tag.clone())),
            u64s(rows.iter().map(|row| row.block_number)),
            u64s(rows.iter().map(|row| row.event_timestamp.max(0) as u64)),
            strings(rows.iter().map(|row| row.event_time_utc.clone())),
            u64s(rows.iter().map(|row| row.minute_ts.max(0) as u64)),
            strings(rows.iter().map(|row| row.split.clone())),
            strings(rows.iter().map(|row| row.transaction_hash.clone())),
            u64s(rows.iter().map(|row| row.log_index)),
            strings(rows.iter().map(|row| row.pool_address.clone())),
            strings(rows.iter().map(|row| row.dex_id.clone())),
            strings(rows.iter().map(|row| row.family.clone())),
            strings(rows.iter().map(|row| row.direction.clone())),
            opt_f64s(rows.iter().map(|row| row.quote_abs)),
            opt_f64s(rows.iter().map(|row| row.pool_price)),
            opt_f64s(rows.iter().map(|row| row.anchor_price)),
            strings(rows.iter().map(|row| row.anchor_source.clone())),
            opt_f64s(rows.iter().map(|row| row.dislocation_bps)),
            opt_f64s(rows.iter().map(|row| row.abs_dislocation_bps)),
            opt_f64s(rows.iter().map(|row| row.cost_adjusted_dislocation_bps)),
            opt_u64s(rows.iter().map(|row| row.half_life_minutes)),
            opt_u64s(rows.iter().map(|row| row.time_to_reenter_band_minutes)),
            opt_f64s(rows.iter().map(|row| row.max_adverse_dislocation_bps)),
            opt_u64s(
                rows.iter()
                    .map(|row| row.depth_source_ts.map(|value| value.max(0) as u64)),
            ),
            opt_u64s(rows.iter().map(|row| row.depth_source_lag_seconds)),
            opt_f64s(rows.iter().map(|row| row.depth_imbalance_1pct)),
            opt_f64s(rows.iter().map(|row| row.depth_imbalance_3pct)),
            opt_f64s(rows.iter().map(|row| row.depth_imbalance_5pct)),
            opt_f64s(rows.iter().map(|row| row.bid_notional_depth)),
            opt_f64s(rows.iter().map(|row| row.ask_notional_depth)),
            opt_f64s(rows.iter().map(|row| row.liquidity_slope)),
            opt_bools(rows.iter().map(|row| row.liquidity_vacuum)),
            opt_f64s(rows.iter().map(|row| row.wall_asymmetry)),
            opt_u64s(
                rows.iter()
                    .map(|row| row.trade_flow_minute_ts.map(|value| value.max(0) as u64)),
            ),
            opt_u64s(rows.iter().map(|row| row.trade_source_lag_minutes)),
            opt_f64s(rows.iter().map(|row| row.taker_buy_quote)),
            opt_f64s(rows.iter().map(|row| row.taker_sell_quote)),
            opt_f64s(rows.iter().map(|row| row.total_trade_quote)),
            opt_f64s(rows.iter().map(|row| row.trade_imbalance)),
            opt_f64s(rows.iter().map(|row| row.sweep_intensity)),
            opt_u64s(rows.iter().map(|row| row.burst_trade_count)),
            opt_f64s(rows.iter().map(|row| row.max_trade_quote)),
            strings(rows.iter().map(|row| row.diagnostic_status.clone())),
        ],
    )
    .context("failed to build joined orderbook lag panel batch")
}

fn field_utf8(name: &str, nullable: bool) -> Field {
    Field::new(name, DataType::Utf8, nullable)
}

fn field_u64(name: &str, nullable: bool) -> Field {
    Field::new(name, DataType::UInt64, nullable)
}

fn field_f64(name: &str, nullable: bool) -> Field {
    Field::new(name, DataType::Float64, nullable)
}

fn strings<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = String>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let bytes = values.iter().map(String::len).sum();
    let mut builder = StringBuilder::with_capacity(values.len(), bytes);
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn u64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = u64>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = UInt64Builder::with_capacity(values.len());
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn opt_u64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = Option<u64>>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = UInt64Builder::with_capacity(values.len());
    for value in values {
        match value {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

fn f64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = f64>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn opt_f64s<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = Option<f64>>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        match value.and_then(finite) {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

fn bools<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = bool>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = arrow::array::BooleanBuilder::with_capacity(values.len());
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn opt_bools<I>(values: I) -> ArrayRef
where
    I: IntoIterator<Item = Option<bool>>,
{
    let values = values.into_iter().collect::<Vec<_>>();
    let mut builder = arrow::array::BooleanBuilder::with_capacity(values.len());
    for value in values {
        match value {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

fn string_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| anyhow!("column {name} is not utf8"))
}

fn u64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a UInt64Array> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .ok_or_else(|| anyhow!("column {name} is not uint64"))
}

fn f64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| anyhow!("column {name} is not float64"))
}

fn string_value(values: &StringArray, index: usize) -> String {
    if values.is_null(index) {
        String::new()
    } else {
        values.value(index).to_string()
    }
}

fn u64_value(values: &UInt64Array, index: usize) -> u64 {
    if values.is_null(index) {
        0
    } else {
        values.value(index)
    }
}

fn u64_option(values: &UInt64Array, index: usize) -> Option<u64> {
    if values.is_null(index) {
        None
    } else {
        Some(values.value(index))
    }
}

fn f64_option(values: &Float64Array, index: usize) -> Option<f64> {
    if values.is_null(index) {
        None
    } else {
        finite(values.value(index))
    }
}

fn write_csv<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    if rows.is_empty() {
        bail!("refusing to write empty CSV {}", path.display());
    }
    ensure_parent_dir(path)?;
    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create {}", path.display()))?;
    for row in rows {
        writer
            .serialize(row)
            .with_context(|| format!("failed to serialize row into {}", path.display()))?;
    }
    writer
        .flush()
        .with_context(|| format!("failed to flush {}", path.display()))
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    ensure_parent_dir(path)?;
    let file =
        File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, value)
        .with_context(|| format!("failed to write {}", path.display()))
}

fn assert_no_inf(path: &Path) -> Result<()> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    for record in reader.records() {
        let record = record.with_context(|| format!("failed reading {}", path.display()))?;
        for field in &record {
            let lower = field.to_ascii_lowercase();
            if lower == "inf" || lower == "-inf" || lower == "infinity" || lower == "-infinity" {
                bail!("{} contains an infinite value", path.display());
            }
        }
    }
    Ok(())
}

fn write_report(
    summary: &OrderbookReportSummary,
    summary_rows: &[OrderbookSummaryRow],
    factor_rows: &[OrderbookFactorTestRow],
) -> Result<()> {
    let overall = summary_rows
        .iter()
        .find(|row| row.group == "overall" && row.group_value == "all");
    let top_factors = factor_rows
        .iter()
        .take(12)
        .map(|row| {
            format!(
                "| {} | {} | {} | {} | {} | {} |",
                row.factor,
                row.target,
                row.n,
                fmt_opt(row.spearman),
                fmt_opt(row.high_minus_low),
                fmt_rate(row.high_positive_rate)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let group_rows = summary_rows
        .iter()
        .filter(|row| {
            row.group == "overall"
                || row.group == "depth_vacuum"
                || row.group == "trade_imbalance_sign"
                || row.group == "wall_side"
        })
        .take(16)
        .map(|row| {
            format!(
                "| {} | {} | {} | {} | {} | {} | {} | {} |",
                row.group,
                row.group_value,
                row.rows,
                fmt_rate(row.depth_coverage_rate),
                fmt_rate(row.trade_flow_coverage_rate),
                fmt_opt(row.median_abs_dislocation_bps),
                fmt_opt(row.median_trade_imbalance),
                fmt_rate(row.cost_adjusted_positive_rate)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let overall_text = overall
        .map(|row| {
            format!(
                "- depth coverage: `{}`\n- trade-flow coverage: `{}`\n- median abs DEX-CEX dislocation: `{}` bps\n- cost-adjusted positive rate: `{}`",
                fmt_rate(row.depth_coverage_rate),
                fmt_rate(row.trade_flow_coverage_rate),
                fmt_opt(row.median_abs_dislocation_bps),
                fmt_rate(row.cost_adjusted_positive_rate)
            )
        })
        .unwrap_or_else(|| "- overall summary unavailable".to_string());
    let text = format!(
        "# MON/USDC V1.5 Binance Order Book Dynamics Report\n\n状态: `{}`。\n\n这份报告使用 Binance public data 的 USD-M futures `MONUSDT` 免费历史数据：`bookDepth` 粗深度快照与 `aggTrades` 主动成交流。它不是逐笔全量 L2，也不能直接计算严格 OFI；更精细的 `depth/depthSnapshot/bookTicker` 需要 live collector 或 Tardis/Crypto Lake 路线。\n\n## 数据覆盖\n\n- expected days: `{}`\n- bookDepth CSV files: `{}`\n- bookDepth rows: `{}`\n- bookDepth snapshots: `{}`\n- orderbook state rows: `{}`\n- aggTrades CSV files: `{}`\n- aggTrade rows: `{}`\n- trade-flow state rows: `{}`\n- DEX lag rows: `{}`\n- joined panel rows: `{}`\n- missing bookDepth days: `{}`\n- missing aggTrade days: `{}`\n\n## Futures Basis 背景\n\n- common trade/mark rows: `{}`\n- median trade-mark basis: `{}` bps\n- median abs trade-mark basis: `{}` bps\n- p90 abs trade-mark basis: `{}` bps\n- median premium index: `{}` bps\n- p90 abs premium index: `{}` bps\n\n## Overall 结果\n\n{}\n\n## Regime Summary\n\n| Group | Value | Rows | Depth Coverage | Trade Coverage | Median Abs Dislocation bps | Median Trade Imbalance | Cost-Adjusted Positive |\n| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |\n{}\n\n## Factor Tests\n\n| Factor | Target | N | Spearman | High-Low Mean | High Positive Rate |\n| --- | --- | ---: | ---: | ---: | ---: |\n{}\n\n## 研究解释\n\n- `percentage < 0` 视为 bid-side depth，`percentage > 0` 视为 ask-side depth；`1pct/3pct/5pct` 使用对应范围内最大 cumulative notional，避免重复相加。\n- `depth_imbalance = (bid - ask) / (bid + ask)`，正值表示 bid depth 更厚；`wall_asymmetry = log(ask_5pct / bid_5pct)`，正值表示 ask wall 更厚。\n- DEX event join 使用 `source_ts <= event_timestamp` 的最近 `bookDepth` 快照；`aggTrades` 使用上一完整分钟，避免当前分钟偷看未来。\n- `liquidity_vacuum` 是 `1pct` 双边 depth 处在全样本底部 20% 的状态标签。\n- 这仍是解释性研究，不是可执行交易规则；若粗深度/成交流没有解释力，上更复杂模型也大概率只是拟合噪声。\n\n## 输出\n\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n",
        summary.run_tag,
        summary.coverage.expected_days,
        summary.coverage.book_depth_csv_files,
        summary.coverage.book_depth_rows,
        summary.coverage.book_depth_snapshots,
        summary.coverage.book_depth_state_rows,
        summary.coverage.agg_trade_csv_files,
        summary.coverage.agg_trade_rows,
        summary.coverage.trade_flow_state_rows,
        summary.coverage.dex_lag_rows,
        summary.coverage.joined_panel_rows,
        summary.coverage.missing_book_depth_days.join(", "),
        summary.coverage.missing_agg_trade_days.join(", "),
        summary.basis.common_rows,
        fmt_opt(summary.basis.median_trade_mark_basis_bps),
        fmt_opt(summary.basis.median_abs_trade_mark_basis_bps),
        fmt_opt(summary.basis.p90_abs_trade_mark_basis_bps),
        fmt_opt(summary.basis.median_premium_index_bps),
        fmt_opt(summary.basis.p90_abs_premium_index_bps),
        overall_text,
        group_rows,
        top_factors,
        summary.outputs.orderbook_state_parquet,
        summary.outputs.trade_flow_state_parquet,
        summary.outputs.orderbook_lag_panel_parquet,
        summary.outputs.orderbook_summary_csv,
        summary.outputs.orderbook_factor_tests_csv,
        summary.outputs.completion_json,
    );
    ensure_parent_dir(Path::new(&summary.outputs.report))?;
    fs::write(&summary.outputs.report, text)
        .with_context(|| format!("failed to write {}", summary.outputs.report))
}

fn fmt_opt(value: Option<f64>) -> String {
    value
        .map(|value| format!("{value:.4}"))
        .unwrap_or_else(|| String::new())
}

fn fmt_rate(value: Option<f64>) -> String {
    value
        .map(|value| format!("{:.2}%", value * 100.0))
        .unwrap_or_else(|| String::new())
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn current_executable_path() -> String {
    std::env::current_exe()
        .map(|path| path_string(&path))
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn orderbook_book_depth_timestamp_parses_utc_seconds() {
        let ts = parse_book_depth_timestamp("2026-05-10 00:00:08").unwrap();
        assert_eq!(utc_string(ts).unwrap(), "2026-05-10T00:00:08Z");
    }

    #[test]
    fn orderbook_depth_sign_and_imbalance_use_bid_minus_ask() {
        let mut agg = BookSnapshotAgg {
            source_ts: parse_book_depth_timestamp("2026-05-10 00:00:08").unwrap(),
            ..BookSnapshotAgg::default()
        };
        update_depth_buckets(
            1.0,
            120.0,
            &mut agg.bid_notional_1pct,
            &mut agg.bid_notional_3pct,
            &mut agg.bid_notional_5pct,
        );
        update_depth_buckets(
            1.0,
            80.0,
            &mut agg.ask_notional_1pct,
            &mut agg.ask_notional_3pct,
            &mut agg.ask_notional_5pct,
        );
        let row = orderbook_row_from_snapshot(&OrderbookConfig::default(), agg, None).unwrap();
        assert!((row.depth_imbalance_1pct.unwrap() - 0.2).abs() < 1e-12);
    }

    #[test]
    fn orderbook_agg_trade_taker_side_uses_buyer_maker_flag() {
        let mut agg = TradeFlowAgg {
            minute_ts: 60,
            ..TradeFlowAgg::default()
        };
        let buy_quote = 10.0;
        let sell_quote = 5.0;
        agg.taker_buy_quote += buy_quote;
        agg.taker_sell_quote += sell_quote;
        agg.trade_count = 2;
        agg.max_trade_quote = buy_quote;
        let row = trade_flow_row_from_agg(&OrderbookConfig::default(), agg).unwrap();
        assert!((row.trade_imbalance.unwrap() - (5.0 / 15.0)).abs() < 1e-12);
    }

    #[test]
    fn orderbook_asof_join_never_uses_future_snapshot() {
        let times = vec![100, 160, 220];
        assert_eq!(asof_index(&times, 99), None);
        assert_eq!(asof_index(&times, 100), Some(0));
        assert_eq!(asof_index(&times, 219), Some(1));
        assert_eq!(asof_index(&times, 999), Some(2));
    }

    #[test]
    fn orderbook_epoch_normalizes_ms_to_seconds() {
        assert_eq!(epoch_to_seconds(1_778_371_200_549), 1_778_371_200);
    }

    #[test]
    fn orderbook_missing_days_detects_daily_csv_names() {
        let paths = vec![
            PathBuf::from("MONUSDT-bookDepth-2026-05-10.csv"),
            PathBuf::from("MONUSDT-bookDepth-2026-05-09.csv"),
        ];
        let expected = vec![
            "2026-05-09".to_string(),
            "2026-05-10".to_string(),
            "2026-05-11".to_string(),
        ];
        let days = covered_days_from_csv_names(&paths, "bookDepth", &expected);
        assert!(days.contains("2026-05-10"));
        assert!(days.contains("2026-05-09"));
        assert!(!days.contains("2026-05-11"));
    }
}

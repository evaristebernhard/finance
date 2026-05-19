use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{
    Array, ArrayRef, BooleanArray, BooleanBuilder, Float64Array, Float64Builder, StringArray,
    StringBuilder, UInt64Array, UInt64Builder,
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

pub const DEFAULT_CEX_DYNAMICS_RUN_TAG: &str = "20260512_cex_dynamics_v1";

const BINANCE_KLINES_DATASET: &str = "binance_klines";
const BINANCE_AGG_TRADES_DATASET: &str = "binance_agg_trades";
const BINANCE_UM_FUTURES_KLINES_DATASET: &str = "binance_um_futures_klines";
const MINUTE_PRICE_REFERENCE_DATASET: &str = "mon_usdc_minute_price_reference";
const EVENT_FEATURES_DATASET: &str = "mon_usdc_event_features";
const CEX_MARKET_STATE_DATASET: &str = "mon_usdc_cex_market_state";
const CEX_DEX_LAG_PANEL_DATASET: &str = "mon_usdc_cex_dex_lag_panel";

const MON_CEX_SYMBOLS: [&str; 2] = ["MONUSDT", "MONUSDC"];
const MKT_WEIGHTS: [(&str, f64); 3] = [("BTCUSDT", 0.45), ("ETHUSDT", 0.35), ("SOLUSDT", 0.20)];
const L1_SYMBOLS: [&str; 7] = [
    "SOLUSDT", "SUIUSDT", "APTUSDT", "SEIUSDT", "TIAUSDT", "ARBUSDT", "OPUSDT",
];
const MEME_SYMBOLS: [&str; 5] = ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT", "BONKUSDT"];
const LARGE_SYMBOLS: [&str; 4] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];
const CORR_SYMBOLS: [&str; 8] = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "SUIUSDT", "APTUSDT", "DOGEUSDT", "PEPEUSDT",
];
const LAG_GRID_MINUTES: [i64; 7] = [-15, -5, -1, 0, 1, 5, 15];

#[derive(Debug, Clone)]
pub struct CexDynamicsConfig {
    pub data_root: PathBuf,
    pub run_tag: String,
    pub date_dir: PathBuf,
    pub docs_dir: PathBuf,
    pub symbols: Vec<String>,
    pub lag_horizon_minutes: u64,
    pub cost_threshold_bps: f64,
    pub progress_interval: usize,
}

impl Default for CexDynamicsConfig {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_DATA_ROOT),
            run_tag: DEFAULT_CEX_DYNAMICS_RUN_TAG.to_string(),
            date_dir: PathBuf::from("date"),
            docs_dir: PathBuf::from("docs"),
            symbols: [
                "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "SUIUSDT", "APTUSDT", "SEIUSDT",
                "TIAUSDT", "ARBUSDT", "OPUSDT", "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT",
                "BONKUSDT", "MONUSDT", "MONUSDC",
            ]
            .iter()
            .map(|value| value.to_string())
            .collect(),
            lag_horizon_minutes: 60,
            cost_threshold_bps: 135.0,
            progress_interval: DEFAULT_PROGRESS_INTERVAL,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct CexDynamicsSummary {
    pub data_root: String,
    pub run_tag: String,
    pub executable_path: String,
    pub exploratory_only: bool,
    pub inputs: CexDynamicsInputs,
    pub assumptions: CexDynamicsAssumptions,
    pub coverage: CexDynamicsCoverage,
    pub outputs: CexDynamicsOutputs,
}

#[derive(Debug, Clone, Serialize)]
pub struct CexDynamicsInputs {
    pub binance_klines_dir: String,
    pub binance_um_futures_klines_dir: String,
    pub binance_agg_trades_dir: String,
    pub minute_price_reference: String,
    pub event_features: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CexDynamicsAssumptions {
    pub symbols: Vec<String>,
    pub cex_input_format: String,
    pub anchor_fallback: String,
    pub lag_horizon_minutes: u64,
    pub cost_threshold_bps: f64,
    pub orderbook_scope: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CexDynamicsCoverage {
    pub cex_kline_files: u64,
    pub cex_kline_rows: u64,
    pub cex_um_futures_kline_files: u64,
    pub cex_um_futures_kline_rows: u64,
    pub cex_agg_trade_files: u64,
    pub cex_agg_trade_rows: u64,
    pub cex_symbols_available: Vec<String>,
    pub ignored_non_csv_files: u64,
    pub duplicate_cex_symbol_minutes: u64,
    pub minute_price_rows: u64,
    pub event_price_rows: u64,
    pub market_state_rows: u64,
    pub dex_lag_panel_rows: u64,
    pub dex_lag_summary_rows: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct CexDynamicsOutputs {
    pub market_state_parquet: String,
    pub dex_lag_panel_parquet: String,
    pub dynamics_summary_csv: String,
    pub dex_lag_summary_csv: String,
    pub completion_json: String,
    pub report: String,
}

#[derive(Debug, Clone)]
struct BinanceKlineRow {
    symbol: String,
    source: String,
    minute_ts: i64,
    close: f64,
    quote_volume: f64,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct BinanceAggTradeRow {
    symbol: String,
    minute_ts: i64,
    quote_volume: f64,
    buyer_maker: bool,
}

#[derive(Debug, Clone)]
struct ExternalInputCoverage {
    kline_files: u64,
    kline_rows: u64,
    futures_kline_files: u64,
    futures_kline_rows: u64,
    agg_trade_files: u64,
    agg_trade_rows: u64,
    ignored_non_csv_files: u64,
    duplicate_symbol_minutes: u64,
}

#[derive(Debug, Clone)]
struct MinutePricePoint {
    minute_ts: i64,
    price: Option<f64>,
}

#[derive(Debug, Clone)]
struct MinutePriceSeries {
    points: Vec<MinutePricePoint>,
}

impl MinutePriceSeries {
    fn price_at(&self, minute_ts: i64) -> Option<f64> {
        self.points
            .binary_search_by_key(&minute_ts, |point| point.minute_ts)
            .ok()
            .and_then(|index| self.points.get(index))
            .and_then(|point| point.price)
            .filter(|value| *value > 0.0 && value.is_finite())
    }

    fn minutes(&self) -> Vec<i64> {
        self.points.iter().map(|point| point.minute_ts).collect()
    }
}

#[derive(Debug, Clone)]
struct EventPriceRow {
    block_number: u64,
    timestamp: i64,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    clean_keep: bool,
    price_quote_per_base: Option<f64>,
    quote_abs: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct CexDynamicsSummaryRow {
    run_tag: String,
    frequency: String,
    group: String,
    group_value: String,
    rows: u64,
    anchor_source: String,
    cex_factor_rows: u64,
    compressed_range_rate: Option<f64>,
    upper_breakout_rate: Option<f64>,
    lower_breakout_rate: Option<f64>,
    drawdown_recovery_rate: Option<f64>,
    positive_cusum_rate: Option<f64>,
    upper_first_rate: Option<f64>,
    lower_first_rate: Option<f64>,
    median_anchor_return_bps: Option<f64>,
    median_realized_vol_bps: Option<f64>,
    median_beta_residual_bps: Option<f64>,
}

#[derive(Debug, Clone)]
struct MarketStateRow {
    run_tag: String,
    frequency: String,
    timestamp: i64,
    minute_utc: String,
    split: String,
    anchor_symbol: String,
    anchor_source: String,
    anchor_price: Option<f64>,
    anchor_return: Option<f64>,
    mkt_return: Option<f64>,
    l1_return: Option<f64>,
    meme_return: Option<f64>,
    size_rot_return: Option<f64>,
    liq_score: Option<f64>,
    avg_corr: Option<f64>,
    realized_vol_1h: Option<f64>,
    vol_state: String,
    beta_mkt: Option<f64>,
    beta_l1: Option<f64>,
    beta_meme: Option<f64>,
    beta_residual: Option<f64>,
    compressed_range: bool,
    upper_breakout: bool,
    lower_breakout: bool,
    drawdown_recovery: bool,
    positive_cusum_regime: bool,
    barrier_first_hit: String,
    barrier_first_hit_minutes: Option<u64>,
}

#[derive(Debug, Clone)]
struct DexLagPanelRow {
    run_tag: String,
    block_number: u64,
    event_time_utc: String,
    minute_timestamp: i64,
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

#[derive(Debug, Clone, Serialize)]
struct DexLagSummaryRow {
    run_tag: String,
    group: String,
    group_value: String,
    rows: u64,
    priced_rows: u64,
    cost_adjusted_positive_rows: u64,
    cost_adjusted_positive_rate: Option<f64>,
    median_abs_dislocation_bps: Option<f64>,
    p90_abs_dislocation_bps: Option<f64>,
    median_max_adverse_dislocation_bps: Option<f64>,
    reenter_band_rate: Option<f64>,
    half_life_observed_rate: Option<f64>,
    median_half_life_minutes: Option<f64>,
    best_lag_minutes: Option<i64>,
    best_lag_corr: Option<f64>,
    cex_to_dex_beta: Option<f64>,
}

pub fn run_cex_dynamics_report(config: &CexDynamicsConfig) -> Result<CexDynamicsSummary> {
    validate_config(config)?;
    fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    fs::create_dir_all(config.docs_dir.join("markets/mon-usdc"))
        .with_context(|| format!("failed to create {}", config.docs_dir.display()))?;
    fs::create_dir_all(external_dir(&config.data_root, BINANCE_KLINES_DATASET))?;
    fs::create_dir_all(external_dir(
        &config.data_root,
        BINANCE_UM_FUTURES_KLINES_DATASET,
    ))?;
    fs::create_dir_all(external_dir(&config.data_root, BINANCE_AGG_TRADES_DATASET))?;

    let outputs = build_output_paths(config);
    let minute_path = select_latest_part(&config.data_root, MINUTE_PRICE_REFERENCE_DATASET)?;
    let event_features_path = select_latest_part(&config.data_root, EVENT_FEATURES_DATASET)?;

    eprintln!(
        "[mon_usdc_cex_dynamics_report] read minute price reference: {}",
        minute_path.display()
    );
    let minute_prices = read_minute_price_series(&minute_path)?;
    eprintln!(
        "[mon_usdc_cex_dynamics_report] read event features: {}",
        event_features_path.display()
    );
    let event_rows = read_event_price_rows(&event_features_path, config.progress_interval)?;

    eprintln!("[mon_usdc_cex_dynamics_report] scan Binance local CSV inputs");
    let (kline_rows, agg_trade_rows, external_coverage) = read_external_inputs(config)?;

    let (market_rows_1m, available_symbols, duplicate_symbol_minutes) =
        build_market_state_1m(config, &minute_prices, &kline_rows)?;
    let mut coverage = external_coverage;
    coverage.duplicate_symbol_minutes += duplicate_symbol_minutes;
    let mut market_rows = market_rows_1m.clone();
    market_rows.extend(aggregate_market_rows(config, &market_rows_1m, "5m", 5)?);
    market_rows.extend(aggregate_market_rows(config, &market_rows_1m, "1h", 60)?);

    let dex_lag_rows = build_dex_lag_panel(config, &market_rows_1m, &event_rows)?;
    let dex_lag_summary = build_dex_lag_summary(config, &market_rows_1m, &dex_lag_rows)?;
    let dynamics_summary = build_dynamics_summary(config, &market_rows);

    write_schema_metadata(
        &config.data_root,
        CEX_MARKET_STATE_DATASET,
        market_state_schema().as_ref(),
        &["dt"],
    )?;
    write_schema_metadata(
        &config.data_root,
        CEX_DEX_LAG_PANEL_DATASET,
        dex_lag_panel_schema().as_ref(),
        &["dt"],
    )?;
    let market_batch = market_state_batch(market_state_schema(), &market_rows)?;
    write_parquet_part(
        Path::new(&outputs.market_state_parquet),
        market_state_schema(),
        market_batch,
    )?;
    let lag_batch = dex_lag_panel_batch(dex_lag_panel_schema(), &dex_lag_rows)?;
    write_parquet_part(
        Path::new(&outputs.dex_lag_panel_parquet),
        dex_lag_panel_schema(),
        lag_batch,
    )?;
    write_csv(Path::new(&outputs.dynamics_summary_csv), &dynamics_summary)?;
    write_csv(Path::new(&outputs.dex_lag_summary_csv), &dex_lag_summary)?;

    let summary = CexDynamicsSummary {
        data_root: path_string(&config.data_root),
        run_tag: config.run_tag.clone(),
        executable_path: current_executable_path(),
        exploratory_only: true,
        inputs: CexDynamicsInputs {
            binance_klines_dir: path_string(&external_dir(&config.data_root, BINANCE_KLINES_DATASET)),
            binance_um_futures_klines_dir: path_string(&external_dir(
                &config.data_root,
                BINANCE_UM_FUTURES_KLINES_DATASET,
            )),
            binance_agg_trades_dir: path_string(&external_dir(
                &config.data_root,
                BINANCE_AGG_TRADES_DATASET,
            )),
            minute_price_reference: path_string(&minute_path),
            event_features: path_string(&event_features_path),
        },
        assumptions: CexDynamicsAssumptions {
            symbols: config.symbols.clone(),
            cex_input_format: "local extracted Binance CSV rows; zip files are left untouched in v1"
                .to_string(),
            anchor_fallback: "MONUSDT/MONUSDC close if available, otherwise mon_usdc_minute_price_reference"
                .to_string(),
            lag_horizon_minutes: config.lag_horizon_minutes,
            cost_threshold_bps: config.cost_threshold_bps,
            orderbook_scope: "v1 does not backfill order book; depth/bookTicker live collection is reserved for v2"
                .to_string(),
        },
        coverage: CexDynamicsCoverage {
            cex_kline_files: coverage.kline_files,
            cex_kline_rows: coverage.kline_rows,
            cex_um_futures_kline_files: coverage.futures_kline_files,
            cex_um_futures_kline_rows: coverage.futures_kline_rows,
            cex_agg_trade_files: coverage.agg_trade_files,
            cex_agg_trade_rows: coverage.agg_trade_rows,
            cex_symbols_available: available_symbols,
            ignored_non_csv_files: coverage.ignored_non_csv_files,
            duplicate_cex_symbol_minutes: coverage.duplicate_symbol_minutes,
            minute_price_rows: minute_prices.points.len() as u64,
            event_price_rows: event_rows.len() as u64,
            market_state_rows: market_rows.len() as u64,
            dex_lag_panel_rows: dex_lag_rows.len() as u64,
            dex_lag_summary_rows: dex_lag_summary.len() as u64,
        },
        outputs,
    };
    write_json(Path::new(&summary.outputs.completion_json), &summary)?;
    write_report(&summary, &dynamics_summary, &dex_lag_summary)?;
    drop(agg_trade_rows);
    Ok(summary)
}

fn validate_config(config: &CexDynamicsConfig) -> Result<()> {
    if config.run_tag.trim().is_empty() {
        bail!("run_tag cannot be empty");
    }
    if config.lag_horizon_minutes == 0 {
        bail!("lag_horizon_minutes must be positive");
    }
    if !config.cost_threshold_bps.is_finite() || config.cost_threshold_bps < 0.0 {
        bail!("cost_threshold_bps must be finite and non-negative");
    }
    Ok(())
}

fn external_dir(data_root: &Path, dataset: &str) -> PathBuf {
    data_root.join("external").join(dataset)
}

fn build_output_paths(config: &CexDynamicsConfig) -> CexDynamicsOutputs {
    let dt = config.run_tag.get(..10).unwrap_or("cex").replace('_', "-");
    CexDynamicsOutputs {
        market_state_parquet: path_string(
            &config
                .data_root
                .join(DERIVED_DIR)
                .join(CEX_MARKET_STATE_DATASET)
                .join(format!("dt={dt}"))
                .join(format!(
                    "mon_usdc_{}_{}.parquet",
                    CEX_MARKET_STATE_DATASET, config.run_tag
                )),
        ),
        dex_lag_panel_parquet: path_string(
            &config
                .data_root
                .join(DERIVED_DIR)
                .join(CEX_DEX_LAG_PANEL_DATASET)
                .join(format!("dt={dt}"))
                .join(format!(
                    "mon_usdc_{}_{}.parquet",
                    CEX_DEX_LAG_PANEL_DATASET, config.run_tag
                )),
        ),
        dynamics_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_cex_dynamics_summary_{}.csv",
            config.run_tag
        ))),
        dex_lag_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_cex_dex_lag_summary_{}.csv",
            config.run_tag
        ))),
        completion_json: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_cex_dynamics_completion_{}.json",
            config.run_tag
        ))),
        report: path_string(
            &config
                .docs_dir
                .join("markets/mon-usdc/v1-cex-dynamics-report.md"),
        ),
    }
}

fn read_external_inputs(
    config: &CexDynamicsConfig,
) -> Result<(
    Vec<BinanceKlineRow>,
    Vec<BinanceAggTradeRow>,
    ExternalInputCoverage,
)> {
    let mut coverage = ExternalInputCoverage {
        kline_files: 0,
        kline_rows: 0,
        futures_kline_files: 0,
        futures_kline_rows: 0,
        agg_trade_files: 0,
        agg_trade_rows: 0,
        ignored_non_csv_files: 0,
        duplicate_symbol_minutes: 0,
    };
    let kline_files = csv_files_under(&external_dir(&config.data_root, BINANCE_KLINES_DATASET))?;
    let futures_kline_files = csv_files_under(&external_dir(
        &config.data_root,
        BINANCE_UM_FUTURES_KLINES_DATASET,
    ))?;
    let agg_files = csv_files_under(&external_dir(&config.data_root, BINANCE_AGG_TRADES_DATASET))?;
    coverage.ignored_non_csv_files +=
        non_csv_files_under(&external_dir(&config.data_root, BINANCE_KLINES_DATASET))?;
    coverage.ignored_non_csv_files += non_csv_files_under(&external_dir(
        &config.data_root,
        BINANCE_UM_FUTURES_KLINES_DATASET,
    ))?;
    coverage.ignored_non_csv_files +=
        non_csv_files_under(&external_dir(&config.data_root, BINANCE_AGG_TRADES_DATASET))?;

    let symbols = config
        .symbols
        .iter()
        .map(|value| value.to_uppercase())
        .collect::<BTreeSet<_>>();
    let mut kline_rows = Vec::new();
    for path in kline_files {
        let Some(symbol) = infer_symbol_from_path(&path, &symbols) else {
            continue;
        };
        coverage.kline_files += 1;
        let rows = read_kline_csv(&path, &symbol, "binance_spot")?;
        coverage.kline_rows += rows.len() as u64;
        kline_rows.extend(rows);
    }
    for path in futures_kline_files {
        let Some(symbol) = infer_symbol_from_path(&path, &symbols) else {
            continue;
        };
        coverage.futures_kline_files += 1;
        let rows = read_kline_csv(&path, &symbol, "binance_um_futures")?;
        coverage.futures_kline_rows += rows.len() as u64;
        kline_rows.extend(rows);
    }

    let mut agg_rows = Vec::new();
    for path in agg_files {
        let Some(symbol) = infer_symbol_from_path(&path, &symbols) else {
            continue;
        };
        coverage.agg_trade_files += 1;
        let rows = read_agg_trade_csv(&path, &symbol)?;
        coverage.agg_trade_rows += rows.len() as u64;
        agg_rows.extend(rows);
    }
    Ok((kline_rows, agg_rows, coverage))
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

fn non_csv_files_under(root: &Path) -> Result<u64> {
    let mut files = Vec::new();
    if !root.exists() {
        return Ok(0);
    }
    collect_files(root, &mut files)?;
    Ok(files
        .into_iter()
        .filter(|path| {
            !path
                .extension()
                .and_then(|value| value.to_str())
                .map(|value| value.eq_ignore_ascii_case("csv"))
                .unwrap_or(false)
        })
        .count() as u64)
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

fn infer_symbol_from_path(path: &Path, symbols: &BTreeSet<String>) -> Option<String> {
    let haystack = path.to_string_lossy().to_uppercase();
    symbols
        .iter()
        .filter(|symbol| haystack.contains(symbol.as_str()))
        .max_by_key(|symbol| symbol.len())
        .cloned()
}

fn read_kline_csv(path: &Path, symbol: &str, source: &str) -> Result<Vec<BinanceKlineRow>> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .from_path(path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record.with_context(|| format!("failed CSV record {}", path.display()))?;
        if record.len() < 8 {
            continue;
        }
        let Some(open_time_raw) = parse_i64_cell(record.get(0)) else {
            continue;
        };
        let Some(close) = parse_f64_cell(record.get(4)) else {
            continue;
        };
        let quote_volume = parse_f64_cell(record.get(7)).unwrap_or(0.0);
        if close > 0.0 && close.is_finite() {
            rows.push(BinanceKlineRow {
                symbol: symbol.to_string(),
                source: source.to_string(),
                minute_ts: floor_to_minute(epoch_to_seconds(open_time_raw)),
                close,
                quote_volume: quote_volume.max(0.0),
            });
        }
    }
    Ok(rows)
}

fn read_agg_trade_csv(path: &Path, symbol: &str) -> Result<Vec<BinanceAggTradeRow>> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .from_path(path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record.with_context(|| format!("failed CSV record {}", path.display()))?;
        if record.len() < 7 {
            continue;
        }
        let Some(price) = parse_f64_cell(record.get(1)) else {
            continue;
        };
        let Some(qty) = parse_f64_cell(record.get(2)) else {
            continue;
        };
        let Some(time_raw) = parse_i64_cell(record.get(5)) else {
            continue;
        };
        let buyer_maker = record
            .get(6)
            .map(|value| value.eq_ignore_ascii_case("true"))
            .unwrap_or(false);
        if price > 0.0 && qty > 0.0 && price.is_finite() && qty.is_finite() {
            rows.push(BinanceAggTradeRow {
                symbol: symbol.to_string(),
                minute_ts: floor_to_minute(epoch_to_seconds(time_raw)),
                quote_volume: price * qty,
                buyer_maker,
            });
        }
    }
    Ok(rows)
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

fn build_market_state_1m(
    config: &CexDynamicsConfig,
    minute_prices: &MinutePriceSeries,
    kline_rows: &[BinanceKlineRow],
) -> Result<(Vec<MarketStateRow>, Vec<String>, u64)> {
    let mut by_symbol_minute = HashMap::<String, BTreeMap<i64, (f64, f64, String)>>::new();
    let mut duplicates = 0u64;
    for row in kline_rows {
        let entry = by_symbol_minute.entry(row.symbol.clone()).or_default();
        if entry
            .insert(
                row.minute_ts,
                (row.close, row.quote_volume, row.source.clone()),
            )
            .is_some()
        {
            duplicates += 1;
        }
    }
    let available_symbols = by_symbol_minute
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();

    let mut minutes = minute_prices.minutes();
    if minutes.is_empty() {
        minutes = by_symbol_minute
            .values()
            .flat_map(|rows| rows.keys().copied())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
    }
    if minutes.is_empty() {
        bail!("no minute reference or CEX kline rows available");
    }

    let split_map = chronological_split_map(minutes.iter().map(|minute| date_from_ts(*minute)));
    let returns_by_symbol = build_returns_by_symbol(&by_symbol_minute);
    let mut raw_rows = Vec::<MarketStateRow>::with_capacity(minutes.len());
    let mut raw_liq = Vec::<Option<f64>>::with_capacity(minutes.len());
    let mut anchor_returns = Vec::<Option<f64>>::with_capacity(minutes.len());

    let mut previous_anchor_price: Option<f64> = None;
    for minute in &minutes {
        let anchor_symbol_price = MON_CEX_SYMBOLS.iter().find_map(|symbol| {
            by_symbol_minute
                .get(*symbol)?
                .get(minute)
                .map(|value| (*symbol, value.0, value.2.clone()))
        });
        let (anchor_symbol, anchor_source, anchor_price) =
            if let Some((symbol, price, source)) = anchor_symbol_price {
                let source = match (symbol, source.as_str()) {
                    ("MONUSDT", "binance_um_futures") => "binance_um_futures_monusdt",
                    ("MONUSDC", "binance_um_futures") => "binance_um_futures_monusdc",
                    (_, "binance_spot") => "binance_spot_mon_symbol",
                    _ => "cex_mon_symbol",
                };
                (symbol.to_string(), source.to_string(), Some(price))
            } else {
                (
                    "MON/USDC".to_string(),
                    "dex_minute_reference_fallback".to_string(),
                    minute_prices.price_at(*minute),
                )
            };
        let anchor_return = match (previous_anchor_price, anchor_price) {
            (Some(prev), Some(price)) if prev > 0.0 && price > 0.0 => Some((price / prev).ln()),
            _ => None,
        };
        if anchor_price.is_some() {
            previous_anchor_price = anchor_price;
        }
        let mkt_return = weighted_return(*minute, &returns_by_symbol, &MKT_WEIGHTS);
        let l1_return = equal_return(*minute, &returns_by_symbol, &L1_SYMBOLS);
        let meme_return = equal_return(*minute, &returns_by_symbol, &MEME_SYMBOLS);
        let large_return = equal_return(*minute, &returns_by_symbol, &LARGE_SYMBOLS);
        let small_return = equal_return(*minute, &returns_by_symbol, &L1_SYMBOLS)
            .or_else(|| equal_return(*minute, &returns_by_symbol, &MEME_SYMBOLS));
        let size_rot_return = match (small_return, large_return) {
            (Some(small), Some(large)) => Some(small - large),
            _ => None,
        };
        let total_quote_volume = by_symbol_minute
            .values()
            .filter_map(|rows| rows.get(minute).map(|value| value.1))
            .sum::<f64>();
        let liq_raw = if total_quote_volume > 0.0 {
            let impact =
                mkt_return.unwrap_or(0.0).abs() / (total_quote_volume / 1_000_000.0).max(1.0);
            Some((1.0 + total_quote_volume).ln() - impact)
        } else {
            None
        };
        raw_liq.push(liq_raw);
        anchor_returns.push(anchor_return);
        raw_rows.push(MarketStateRow {
            run_tag: config.run_tag.clone(),
            frequency: "1m".to_string(),
            timestamp: *minute,
            minute_utc: utc_from_timestamp(*minute),
            split: split_map
                .get(&date_from_ts(*minute))
                .cloned()
                .unwrap_or_else(|| "unknown".to_string()),
            anchor_symbol,
            anchor_source,
            anchor_price,
            anchor_return,
            mkt_return,
            l1_return,
            meme_return,
            size_rot_return,
            liq_score: None,
            avg_corr: None,
            realized_vol_1h: None,
            vol_state: "unavailable".to_string(),
            beta_mkt: None,
            beta_l1: None,
            beta_meme: None,
            beta_residual: None,
            compressed_range: false,
            upper_breakout: false,
            lower_breakout: false,
            drawdown_recovery: false,
            positive_cusum_regime: false,
            barrier_first_hit: "none".to_string(),
            barrier_first_hit_minutes: None,
        });
    }

    let liq_z = rolling_zscores(&raw_liq, 1440);
    let realized_vol = rolling_realized_vol(&anchor_returns, 60);
    let vol_thresholds = thresholds(realized_vol.iter().filter_map(|value| *value), 3);
    let avg_corr = rolling_avg_corr(&minutes, &returns_by_symbol, &CORR_SYMBOLS, 60);
    let beta_rows = rolling_beta_rows(&raw_rows, 720, 1e-6);
    apply_price_sequence_labels(&mut raw_rows, &anchor_returns, 60, 0.001, 0.005, 60);
    apply_cusum_labels(&mut raw_rows, &anchor_returns, 0.0001, 0.005);

    for index in 0..raw_rows.len() {
        raw_rows[index].liq_score = liq_z[index];
        raw_rows[index].realized_vol_1h = realized_vol[index];
        raw_rows[index].vol_state = regime_bucket(realized_vol[index], &vol_thresholds);
        raw_rows[index].avg_corr = avg_corr[index];
        if let Some(beta) = beta_rows.get(index).and_then(|value| *value) {
            raw_rows[index].beta_mkt = Some(beta[0]);
            raw_rows[index].beta_l1 = Some(beta[1]);
            raw_rows[index].beta_meme = Some(beta[2]);
            raw_rows[index].beta_residual = Some(beta[3]);
        }
    }
    Ok((raw_rows, available_symbols, duplicates))
}

fn aggregate_market_rows(
    config: &CexDynamicsConfig,
    rows_1m: &[MarketStateRow],
    frequency: &str,
    step_minutes: i64,
) -> Result<Vec<MarketStateRow>> {
    let mut grouped = BTreeMap::<i64, Vec<&MarketStateRow>>::new();
    for row in rows_1m {
        let bucket = row.timestamp - row.timestamp.rem_euclid(step_minutes * 60);
        grouped.entry(bucket).or_default().push(row);
    }
    let mut rows = Vec::new();
    let mut previous_anchor_price: Option<f64> = None;
    for (bucket, group) in grouped {
        let last = group
            .iter()
            .rev()
            .find(|row| row.anchor_price.is_some())
            .copied();
        let anchor_price = last.and_then(|row| row.anchor_price);
        let anchor_return = match (previous_anchor_price, anchor_price) {
            (Some(prev), Some(price)) if prev > 0.0 && price > 0.0 => Some((price / prev).ln()),
            _ => None,
        };
        if anchor_price.is_some() {
            previous_anchor_price = anchor_price;
        }
        let realized_vol_1h = quantile(
            group.iter().filter_map(|row| row.realized_vol_1h).collect(),
            0.5,
        );
        rows.push(MarketStateRow {
            run_tag: config.run_tag.clone(),
            frequency: frequency.to_string(),
            timestamp: bucket,
            minute_utc: utc_from_timestamp(bucket),
            split: last
                .map(|row| row.split.clone())
                .unwrap_or_else(|| "unknown".to_string()),
            anchor_symbol: last
                .map(|row| row.anchor_symbol.clone())
                .unwrap_or_else(|| "MON/USDC".to_string()),
            anchor_source: last
                .map(|row| row.anchor_source.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            anchor_price,
            anchor_return,
            mkt_return: sum_options(group.iter().map(|row| row.mkt_return)),
            l1_return: sum_options(group.iter().map(|row| row.l1_return)),
            meme_return: sum_options(group.iter().map(|row| row.meme_return)),
            size_rot_return: sum_options(group.iter().map(|row| row.size_rot_return)),
            liq_score: quantile(group.iter().filter_map(|row| row.liq_score).collect(), 0.5),
            avg_corr: quantile(group.iter().filter_map(|row| row.avg_corr).collect(), 0.5),
            realized_vol_1h,
            vol_state: last
                .map(|row| row.vol_state.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            beta_mkt: last.and_then(|row| row.beta_mkt),
            beta_l1: last.and_then(|row| row.beta_l1),
            beta_meme: last.and_then(|row| row.beta_meme),
            beta_residual: last.and_then(|row| row.beta_residual),
            compressed_range: group.iter().any(|row| row.compressed_range),
            upper_breakout: group.iter().any(|row| row.upper_breakout),
            lower_breakout: group.iter().any(|row| row.lower_breakout),
            drawdown_recovery: group.iter().any(|row| row.drawdown_recovery),
            positive_cusum_regime: group.iter().any(|row| row.positive_cusum_regime),
            barrier_first_hit: last
                .map(|row| row.barrier_first_hit.clone())
                .unwrap_or_else(|| "none".to_string()),
            barrier_first_hit_minutes: last.and_then(|row| row.barrier_first_hit_minutes),
        });
    }
    Ok(rows)
}

fn build_returns_by_symbol(
    by_symbol_minute: &HashMap<String, BTreeMap<i64, (f64, f64, String)>>,
) -> HashMap<String, BTreeMap<i64, f64>> {
    let mut out = HashMap::new();
    for (symbol, rows) in by_symbol_minute {
        let mut prev: Option<f64> = None;
        let mut returns = BTreeMap::new();
        for (minute, (price, _, _)) in rows {
            if let Some(prev_price) = prev {
                if prev_price > 0.0 && *price > 0.0 {
                    returns.insert(*minute, (*price / prev_price).ln());
                }
            }
            prev = Some(*price);
        }
        out.insert(symbol.clone(), returns);
    }
    out
}

fn weighted_return(
    minute: i64,
    returns_by_symbol: &HashMap<String, BTreeMap<i64, f64>>,
    weights: &[(&str, f64)],
) -> Option<f64> {
    let mut value = 0.0;
    let mut weight_sum = 0.0;
    for (symbol, weight) in weights {
        if let Some(ret) = returns_by_symbol
            .get(*symbol)
            .and_then(|rows| rows.get(&minute))
        {
            value += ret * weight;
            weight_sum += weight;
        }
    }
    (weight_sum > 0.0).then_some(value / weight_sum)
}

fn equal_return(
    minute: i64,
    returns_by_symbol: &HashMap<String, BTreeMap<i64, f64>>,
    symbols: &[&str],
) -> Option<f64> {
    let values = symbols
        .iter()
        .filter_map(|symbol| {
            returns_by_symbol
                .get(*symbol)
                .and_then(|rows| rows.get(&minute))
        })
        .copied()
        .collect::<Vec<_>>();
    if values.is_empty() {
        None
    } else {
        Some(values.iter().sum::<f64>() / values.len() as f64)
    }
}

fn rolling_zscores(values: &[Option<f64>], window: usize) -> Vec<Option<f64>> {
    (0..values.len())
        .map(|index| {
            let start = index.saturating_sub(window);
            let slice = values[start..index]
                .iter()
                .filter_map(|value| *value)
                .collect::<Vec<_>>();
            let value = values[index]?;
            if slice.len() < 5 {
                return None;
            }
            let mean = slice.iter().sum::<f64>() / slice.len() as f64;
            let var = slice
                .iter()
                .map(|sample| (sample - mean).powi(2))
                .sum::<f64>()
                / slice.len() as f64;
            let sd = var.sqrt();
            (sd > 0.0).then_some((value - mean) / sd)
        })
        .collect()
}

fn rolling_realized_vol(returns: &[Option<f64>], window: usize) -> Vec<Option<f64>> {
    (0..returns.len())
        .map(|index| {
            let start = index.saturating_sub(window);
            let values = returns[start..index]
                .iter()
                .filter_map(|value| *value)
                .collect::<Vec<_>>();
            if values.len() < 5 {
                None
            } else {
                Some(values.iter().map(|value| value * value).sum::<f64>().sqrt())
            }
        })
        .collect()
}

fn rolling_avg_corr(
    minutes: &[i64],
    returns_by_symbol: &HashMap<String, BTreeMap<i64, f64>>,
    symbols: &[&str],
    window: usize,
) -> Vec<Option<f64>> {
    let series = symbols
        .iter()
        .map(|symbol| {
            minutes
                .iter()
                .map(|minute| {
                    returns_by_symbol
                        .get(*symbol)
                        .and_then(|rows| rows.get(minute))
                        .copied()
                })
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    (0..minutes.len())
        .map(|index| {
            let start = index.saturating_sub(window);
            let mut corrs = Vec::new();
            for i in 0..series.len() {
                for j in (i + 1)..series.len() {
                    if let Some(corr) =
                        corr_options(&series[i][start..index], &series[j][start..index])
                    {
                        corrs.push(corr);
                    }
                }
            }
            if corrs.is_empty() {
                None
            } else {
                Some(corrs.iter().sum::<f64>() / corrs.len() as f64)
            }
        })
        .collect()
}

fn rolling_beta_rows(rows: &[MarketStateRow], window: usize, ridge: f64) -> Vec<Option<[f64; 4]>> {
    let mut out = vec![None; rows.len()];
    for index in 0..rows.len() {
        if index < 20 {
            continue;
        }
        let start = index.saturating_sub(window);
        let samples = rows[start..index]
            .iter()
            .filter_map(|row| {
                Some([
                    row.anchor_return?,
                    row.mkt_return?,
                    row.l1_return.unwrap_or(0.0),
                    row.meme_return.unwrap_or(0.0),
                ])
            })
            .collect::<Vec<_>>();
        if samples.len() < 20 {
            continue;
        }
        let beta = ridge_beta_3(&samples, ridge);
        if let (Some(y), Some(mkt)) = (rows[index].anchor_return, rows[index].mkt_return) {
            let l1 = rows[index].l1_return.unwrap_or(0.0);
            let meme = rows[index].meme_return.unwrap_or(0.0);
            let residual = y - beta[0] * mkt - beta[1] * l1 - beta[2] * meme;
            out[index] = Some([beta[0], beta[1], beta[2], residual]);
        }
    }
    out
}

fn ridge_beta_3(samples: &[[f64; 4]], ridge: f64) -> [f64; 3] {
    let mut xtx = [[0.0; 3]; 3];
    let mut xty = [0.0; 3];
    for sample in samples {
        let y = sample[0];
        let x = [sample[1], sample[2], sample[3]];
        for i in 0..3 {
            xty[i] += x[i] * y;
            for j in 0..3 {
                xtx[i][j] += x[i] * x[j];
            }
        }
    }
    for (i, row) in xtx.iter_mut().enumerate() {
        row[i] += ridge;
    }
    solve_3x3(xtx, xty).unwrap_or([0.0; 3])
}

fn solve_3x3(mut a: [[f64; 3]; 3], mut b: [f64; 3]) -> Option<[f64; 3]> {
    for col in 0..3 {
        let mut pivot = col;
        for row in (col + 1)..3 {
            if a[row][col].abs() > a[pivot][col].abs() {
                pivot = row;
            }
        }
        if a[pivot][col].abs() < 1e-18 {
            return None;
        }
        if pivot != col {
            a.swap(pivot, col);
            b.swap(pivot, col);
        }
        let denom = a[col][col];
        for j in col..3 {
            a[col][j] /= denom;
        }
        b[col] /= denom;
        for row in 0..3 {
            if row == col {
                continue;
            }
            let factor = a[row][col];
            for j in col..3 {
                a[row][j] -= factor * a[col][j];
            }
            b[row] -= factor * b[col];
        }
    }
    Some(b)
}

fn apply_price_sequence_labels(
    rows: &mut [MarketStateRow],
    returns: &[Option<f64>],
    window: usize,
    breakout_epsilon: f64,
    barrier_return: f64,
    horizon: usize,
) {
    let mut cusum_prices = Vec::with_capacity(rows.len());
    let mut price = 1.0f64;
    for ret in returns {
        if let Some(ret) = ret {
            price *= ret.exp();
            cusum_prices.push(Some(price));
        } else {
            cusum_prices.push(None);
        }
    }
    for index in 0..rows.len() {
        let Some(current) = cusum_prices[index] else {
            continue;
        };
        let start = index.saturating_sub(window);
        let history = cusum_prices[start..index]
            .iter()
            .filter_map(|value| *value)
            .collect::<Vec<_>>();
        if history.len() >= 10 {
            let high = history.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            let low = history.iter().copied().fold(f64::INFINITY, f64::min);
            let range = (high - low) / current.max(1e-12);
            rows[index].compressed_range = range < 0.01;
            rows[index].upper_breakout = current > high * (1.0 + breakout_epsilon);
            rows[index].lower_breakout = current < low * (1.0 - breakout_epsilon);
            let drawdown = 1.0 - current / high;
            let recovery = if high > low {
                (current - low) / (high - low)
            } else {
                0.0
            };
            rows[index].drawdown_recovery = drawdown > 0.02 && recovery > 0.6;
        }
        let upper = current * (1.0 + barrier_return);
        let lower = current * (1.0 - barrier_return);
        for forward in 1..=horizon {
            let Some(future) = cusum_prices.get(index + forward).copied().flatten() else {
                continue;
            };
            if future >= upper {
                rows[index].barrier_first_hit = "upper".to_string();
                rows[index].barrier_first_hit_minutes = Some(forward as u64);
                break;
            }
            if future <= lower {
                rows[index].barrier_first_hit = "lower".to_string();
                rows[index].barrier_first_hit_minutes = Some(forward as u64);
                break;
            }
        }
    }
}

fn apply_cusum_labels(
    rows: &mut [MarketStateRow],
    returns: &[Option<f64>],
    drift: f64,
    threshold: f64,
) {
    let mut g = 0.0;
    for (row, ret) in rows.iter_mut().zip(returns.iter()) {
        if let Some(ret) = ret {
            g = f64::max(0.0, g + ret - drift);
            row.positive_cusum_regime = g > threshold;
        }
    }
}

fn build_dex_lag_panel(
    config: &CexDynamicsConfig,
    market_rows_1m: &[MarketStateRow],
    event_rows: &[EventPriceRow],
) -> Result<Vec<DexLagPanelRow>> {
    let anchor_by_minute = market_rows_1m
        .iter()
        .map(|row| {
            (
                row.timestamp,
                (
                    row.anchor_price,
                    row.anchor_source.clone(),
                    row.split.clone(),
                ),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut base_rows = Vec::new();
    for event in event_rows.iter().filter(|row| row.clean_keep) {
        let minute = floor_to_minute(event.timestamp);
        let anchor = anchor_by_minute.get(&minute);
        let anchor_price = anchor.and_then(|value| value.0);
        let anchor_source = anchor
            .map(|value| value.1.clone())
            .unwrap_or_else(|| "unavailable".to_string());
        let split = anchor
            .map(|value| value.2.clone())
            .unwrap_or_else(|| "unknown".to_string());
        let dislocation = match (event.price_quote_per_base, anchor_price) {
            (Some(pool), Some(anchor)) if pool > 0.0 && anchor > 0.0 => {
                Some(10_000.0 * (pool / anchor).ln())
            }
            _ => None,
        };
        let abs_dislocation = dislocation.map(f64::abs);
        let cost_adjusted = abs_dislocation.map(|value| value - config.cost_threshold_bps);
        let diagnostic_status = if event.price_quote_per_base.is_none() {
            "missing_pool_price"
        } else if anchor_price.is_none() {
            "missing_anchor_price"
        } else if anchor_source == "dex_minute_reference_fallback" {
            "fallback_anchor"
        } else {
            "ok"
        };
        base_rows.push(DexLagPanelRow {
            run_tag: config.run_tag.clone(),
            block_number: event.block_number,
            event_time_utc: utc_from_timestamp(event.timestamp),
            minute_timestamp: minute,
            split,
            transaction_hash: event.transaction_hash.clone(),
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
            dex_id: event.dex_id.clone(),
            family: event.family.clone(),
            direction: event.direction.clone(),
            quote_abs: event.quote_abs,
            pool_price: event.price_quote_per_base,
            anchor_price,
            anchor_source,
            dislocation_bps: dislocation,
            abs_dislocation_bps: abs_dislocation,
            cost_adjusted_dislocation_bps: cost_adjusted,
            half_life_minutes: None,
            time_to_reenter_band_minutes: None,
            max_adverse_dislocation_bps: None,
            diagnostic_status: diagnostic_status.to_string(),
        });
    }
    base_rows.sort_by_key(|row| {
        (
            row.pool_address.clone(),
            row.minute_timestamp,
            row.log_index,
        )
    });
    let mut by_pool = BTreeMap::<String, Vec<usize>>::new();
    for (index, row) in base_rows.iter().enumerate() {
        by_pool
            .entry(row.pool_address.clone())
            .or_default()
            .push(index);
    }
    for indexes in by_pool.values() {
        for (position, index) in indexes.iter().enumerate() {
            let Some(initial_abs) = base_rows[*index].abs_dislocation_bps else {
                continue;
            };
            let start_minute = base_rows[*index].minute_timestamp;
            let half_threshold = initial_abs * 0.5;
            let mut max_abs = initial_abs;
            for future_index in indexes.iter().skip(position + 1) {
                let future_minute = base_rows[*future_index].minute_timestamp;
                let delta_minutes = ((future_minute - start_minute) / 60).max(0) as u64;
                if delta_minutes > config.lag_horizon_minutes {
                    break;
                }
                let Some(future_abs) = base_rows[*future_index].abs_dislocation_bps else {
                    continue;
                };
                max_abs = max_abs.max(future_abs);
                if base_rows[*index].half_life_minutes.is_none() && future_abs <= half_threshold {
                    base_rows[*index].half_life_minutes = Some(delta_minutes);
                }
                if base_rows[*index].time_to_reenter_band_minutes.is_none()
                    && future_abs <= config.cost_threshold_bps
                {
                    base_rows[*index].time_to_reenter_band_minutes = Some(delta_minutes);
                }
            }
            base_rows[*index].max_adverse_dislocation_bps = Some((max_abs - initial_abs).max(0.0));
        }
    }
    Ok(base_rows)
}

fn build_dex_lag_summary(
    config: &CexDynamicsConfig,
    market_rows_1m: &[MarketStateRow],
    lag_rows: &[DexLagPanelRow],
) -> Result<Vec<DexLagSummaryRow>> {
    let mut groups = BTreeMap::<(String, String), Vec<&DexLagPanelRow>>::new();
    for row in lag_rows {
        groups
            .entry(("overall".to_string(), "all".to_string()))
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
            .entry(("split".to_string(), row.split.clone()))
            .or_default()
            .push(row);
        groups
            .entry(("anchor_source".to_string(), row.anchor_source.clone()))
            .or_default()
            .push(row);
    }
    let lead_lag = pool_lead_lag_stats(market_rows_1m, lag_rows);
    let mut out = Vec::new();
    for ((group, group_value), rows) in groups {
        let priced = rows
            .iter()
            .filter(|row| row.dislocation_bps.is_some())
            .count() as u64;
        let cost_positive = rows
            .iter()
            .filter(|row| {
                row.cost_adjusted_dislocation_bps
                    .unwrap_or(f64::NEG_INFINITY)
                    > 0.0
            })
            .count() as u64;
        let half_life_rows = rows
            .iter()
            .filter_map(|row| row.half_life_minutes.map(|value| value as f64))
            .collect::<Vec<_>>();
        let reentry_rows = rows
            .iter()
            .filter(|row| row.time_to_reenter_band_minutes.is_some())
            .count() as u64;
        let abs_values = rows
            .iter()
            .filter_map(|row| row.abs_dislocation_bps)
            .collect::<Vec<_>>();
        let adverse_values = rows
            .iter()
            .filter_map(|row| row.max_adverse_dislocation_bps)
            .collect::<Vec<_>>();
        let lag_stat = if group == "pool" {
            lead_lag.get(&group_value).copied()
        } else if group == "overall" {
            lead_lag.get("all").copied()
        } else {
            None
        };
        out.push(DexLagSummaryRow {
            run_tag: config.run_tag.clone(),
            group,
            group_value,
            rows: rows.len() as u64,
            priced_rows: priced,
            cost_adjusted_positive_rows: cost_positive,
            cost_adjusted_positive_rate: rate(cost_positive, rows.len() as u64),
            median_abs_dislocation_bps: quantile(abs_values.clone(), 0.5),
            p90_abs_dislocation_bps: quantile(abs_values, 0.9),
            median_max_adverse_dislocation_bps: quantile(adverse_values, 0.5),
            reenter_band_rate: rate(reentry_rows, priced),
            half_life_observed_rate: rate(half_life_rows.len() as u64, priced),
            median_half_life_minutes: quantile(half_life_rows, 0.5),
            best_lag_minutes: lag_stat.map(|value| value.0),
            best_lag_corr: lag_stat.and_then(|value| finite(value.1)),
            cex_to_dex_beta: lag_stat.and_then(|value| finite(value.2)),
        });
    }
    out.sort_by(|a, b| {
        (a.group.as_str(), a.group_value.as_str()).cmp(&(b.group.as_str(), b.group_value.as_str()))
    });
    Ok(out)
}

fn pool_lead_lag_stats(
    market_rows_1m: &[MarketStateRow],
    lag_rows: &[DexLagPanelRow],
) -> HashMap<String, (i64, f64, f64)> {
    let minutes = market_rows_1m
        .iter()
        .map(|row| row.timestamp)
        .collect::<Vec<_>>();
    let cex_returns = market_rows_1m
        .iter()
        .map(|row| row.anchor_return)
        .collect::<Vec<_>>();
    let mut out = HashMap::new();
    let mut groups = BTreeMap::<String, Vec<&DexLagPanelRow>>::new();
    for row in lag_rows.iter().filter(|row| row.pool_price.is_some()) {
        groups
            .entry(row.pool_address.clone())
            .or_default()
            .push(row);
        groups.entry("all".to_string()).or_default().push(row);
    }
    for (pool, rows) in groups {
        let mut price_by_minute = BTreeMap::<i64, f64>::new();
        for row in rows {
            if let Some(price) = row.pool_price.filter(|value| *value > 0.0) {
                price_by_minute.insert(row.minute_timestamp, price);
            }
        }
        let dex_returns = ffilled_returns(&minutes, &price_by_minute);
        let mut best = None::<(i64, f64, f64)>;
        for lag in LAG_GRID_MINUTES {
            let (x, y) = lagged_pairs(&cex_returns, &dex_returns, lag);
            if let Some(corr) = corr_values(&x, &y) {
                let beta = beta_values(&x, &y).unwrap_or(0.0);
                if best
                    .map(|(_, best_corr, _)| corr > best_corr)
                    .unwrap_or(true)
                {
                    best = Some((lag, corr, beta));
                }
            }
        }
        if let Some(best) = best {
            out.insert(pool, best);
        }
    }
    out
}

fn ffilled_returns(minutes: &[i64], price_by_minute: &BTreeMap<i64, f64>) -> Vec<Option<f64>> {
    let mut current = None::<f64>;
    let mut previous = None::<f64>;
    let mut returns = Vec::with_capacity(minutes.len());
    for minute in minutes {
        if let Some(price) = price_by_minute.get(minute) {
            current = Some(*price);
        }
        let ret = match (previous, current) {
            (Some(prev), Some(price)) if prev > 0.0 && price > 0.0 => Some((price / prev).ln()),
            _ => None,
        };
        if current.is_some() {
            previous = current;
        }
        returns.push(ret);
    }
    returns
}

fn lagged_pairs(x: &[Option<f64>], y: &[Option<f64>], lag: i64) -> (Vec<f64>, Vec<f64>) {
    let mut left = Vec::new();
    let mut right = Vec::new();
    for i in 0..x.len() {
        let j = i as i64 + lag;
        if j < 0 || j >= y.len() as i64 {
            continue;
        }
        if let (Some(a), Some(b)) = (x[i], y[j as usize]) {
            left.push(a);
            right.push(b);
        }
    }
    (left, right)
}

fn build_dynamics_summary(
    config: &CexDynamicsConfig,
    market_rows: &[MarketStateRow],
) -> Vec<CexDynamicsSummaryRow> {
    let mut groups = BTreeMap::<(String, String, String), Vec<&MarketStateRow>>::new();
    for row in market_rows {
        groups
            .entry((
                row.frequency.clone(),
                "overall".to_string(),
                "all".to_string(),
            ))
            .or_default()
            .push(row);
        groups
            .entry((
                row.frequency.clone(),
                "split".to_string(),
                row.split.clone(),
            ))
            .or_default()
            .push(row);
        groups
            .entry((
                row.frequency.clone(),
                "anchor_source".to_string(),
                row.anchor_source.clone(),
            ))
            .or_default()
            .push(row);
        groups
            .entry((
                row.frequency.clone(),
                "vol_state".to_string(),
                row.vol_state.clone(),
            ))
            .or_default()
            .push(row);
    }
    let mut out = Vec::new();
    for ((frequency, group, group_value), rows) in groups {
        let total = rows.len() as u64;
        let cex_factor_rows = rows
            .iter()
            .filter(|row| row.mkt_return.is_some() || row.l1_return.is_some())
            .count() as u64;
        let anchor_source = most_common(rows.iter().map(|row| row.anchor_source.as_str()));
        out.push(CexDynamicsSummaryRow {
            run_tag: config.run_tag.clone(),
            frequency,
            group,
            group_value,
            rows: total,
            anchor_source,
            cex_factor_rows,
            compressed_range_rate: rate(
                rows.iter().filter(|row| row.compressed_range).count() as u64,
                total,
            ),
            upper_breakout_rate: rate(
                rows.iter().filter(|row| row.upper_breakout).count() as u64,
                total,
            ),
            lower_breakout_rate: rate(
                rows.iter().filter(|row| row.lower_breakout).count() as u64,
                total,
            ),
            drawdown_recovery_rate: rate(
                rows.iter().filter(|row| row.drawdown_recovery).count() as u64,
                total,
            ),
            positive_cusum_rate: rate(
                rows.iter().filter(|row| row.positive_cusum_regime).count() as u64,
                total,
            ),
            upper_first_rate: rate(
                rows.iter()
                    .filter(|row| row.barrier_first_hit == "upper")
                    .count() as u64,
                total,
            ),
            lower_first_rate: rate(
                rows.iter()
                    .filter(|row| row.barrier_first_hit == "lower")
                    .count() as u64,
                total,
            ),
            median_anchor_return_bps: quantile(
                rows.iter()
                    .filter_map(|row| row.anchor_return.map(to_bps))
                    .collect(),
                0.5,
            ),
            median_realized_vol_bps: quantile(
                rows.iter()
                    .filter_map(|row| row.realized_vol_1h.map(to_bps))
                    .collect(),
                0.5,
            ),
            median_beta_residual_bps: quantile(
                rows.iter()
                    .filter_map(|row| row.beta_residual.map(to_bps))
                    .collect(),
                0.5,
            ),
        });
    }
    out.sort_by(|a, b| {
        (
            a.frequency.as_str(),
            a.group.as_str(),
            a.group_value.as_str(),
        )
            .cmp(&(
                b.frequency.as_str(),
                b.group.as_str(),
                b.group_value.as_str(),
            ))
    });
    out
}

fn read_minute_price_series(path: &Path) -> Result<MinutePriceSeries> {
    let mut points = Vec::new();
    read_parquet_batches(path, |batch| {
        let minute_timestamp = u64_column(batch, "minute_timestamp")?;
        let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
        for index in 0..batch.num_rows() {
            points.push(MinutePricePoint {
                minute_ts: u64_value(minute_timestamp, index) as i64,
                price: f64_option(price_quote_per_base, index),
            });
        }
        Ok(())
    })?;
    points.sort_by_key(|point| point.minute_ts);
    Ok(MinutePriceSeries { points })
}

fn read_event_price_rows(path: &Path, progress_interval: usize) -> Result<Vec<EventPriceRow>> {
    let mut rows = Vec::new();
    read_parquet_batches(path, |batch| {
        let block_number = u64_column(batch, "block_number")?;
        let timestamp = u64_column(batch, "block_timestamp")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let dex_id = string_column(batch, "dex_id")?;
        let family = string_column(batch, "family")?;
        let is_buy_base = bool_column(batch, "is_buy_base")?;
        let is_sell_base = bool_column(batch, "is_sell_base")?;
        let clean_keep = bool_column(batch, "clean_keep")?;
        let price_quote_per_base = f64_column(batch, "price_quote_per_base")?;
        let quote_abs = f64_column(batch, "quote_abs")?;
        for index in 0..batch.num_rows() {
            rows.push(EventPriceRow {
                block_number: u64_value(block_number, index),
                timestamp: u64_value(timestamp, index) as i64,
                transaction_hash: string_value(transaction_hash, index),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                direction: if bool_value(is_buy_base, index) {
                    "buy_base".to_string()
                } else if bool_value(is_sell_base, index) {
                    "sell_base".to_string()
                } else {
                    "unknown".to_string()
                },
                clean_keep: bool_value(clean_keep, index),
                price_quote_per_base: f64_option(price_quote_per_base, index),
                quote_abs: f64_option(quote_abs, index),
            });
        }
        if progress_interval > 0 && rows.len() % progress_interval < batch.num_rows() {
            eprintln!(
                "[mon_usdc_cex_dynamics_report] event price rows read: {}",
                rows.len()
            );
        }
        Ok(())
    })?;
    rows.sort_by_key(|row| (row.timestamp, row.block_number, row.log_index));
    Ok(rows)
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

fn market_state_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_utf8("frequency", false),
        field_u64("minute_timestamp", false),
        field_utf8("minute_utc", false),
        field_utf8("split", false),
        field_utf8("anchor_symbol", false),
        field_utf8("anchor_source", false),
        field_f64("anchor_price", true),
        field_f64("anchor_return", true),
        field_f64("mkt_return", true),
        field_f64("l1_return", true),
        field_f64("meme_return", true),
        field_f64("size_rot_return", true),
        field_f64("liq_score", true),
        field_f64("avg_corr", true),
        field_f64("realized_vol_1h", true),
        field_utf8("vol_state", false),
        field_f64("beta_mkt", true),
        field_f64("beta_l1", true),
        field_f64("beta_meme", true),
        field_f64("beta_residual", true),
        Field::new("compressed_range", DataType::Boolean, false),
        Field::new("upper_breakout", DataType::Boolean, false),
        Field::new("lower_breakout", DataType::Boolean, false),
        Field::new("drawdown_recovery", DataType::Boolean, false),
        Field::new("positive_cusum_regime", DataType::Boolean, false),
        field_utf8("barrier_first_hit", false),
        field_u64("barrier_first_hit_minutes", true),
    ]))
}

fn market_state_batch(schema: SchemaRef, rows: &[MarketStateRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            strings(rows.iter().map(|row| row.frequency.clone())),
            u64s(rows.iter().map(|row| row.timestamp.max(0) as u64)),
            strings(rows.iter().map(|row| row.minute_utc.clone())),
            strings(rows.iter().map(|row| row.split.clone())),
            strings(rows.iter().map(|row| row.anchor_symbol.clone())),
            strings(rows.iter().map(|row| row.anchor_source.clone())),
            opt_f64s(rows.iter().map(|row| row.anchor_price)),
            opt_f64s(rows.iter().map(|row| row.anchor_return)),
            opt_f64s(rows.iter().map(|row| row.mkt_return)),
            opt_f64s(rows.iter().map(|row| row.l1_return)),
            opt_f64s(rows.iter().map(|row| row.meme_return)),
            opt_f64s(rows.iter().map(|row| row.size_rot_return)),
            opt_f64s(rows.iter().map(|row| row.liq_score)),
            opt_f64s(rows.iter().map(|row| row.avg_corr)),
            opt_f64s(rows.iter().map(|row| row.realized_vol_1h)),
            strings(rows.iter().map(|row| row.vol_state.clone())),
            opt_f64s(rows.iter().map(|row| row.beta_mkt)),
            opt_f64s(rows.iter().map(|row| row.beta_l1)),
            opt_f64s(rows.iter().map(|row| row.beta_meme)),
            opt_f64s(rows.iter().map(|row| row.beta_residual)),
            bools(rows.iter().map(|row| row.compressed_range)),
            bools(rows.iter().map(|row| row.upper_breakout)),
            bools(rows.iter().map(|row| row.lower_breakout)),
            bools(rows.iter().map(|row| row.drawdown_recovery)),
            bools(rows.iter().map(|row| row.positive_cusum_regime)),
            strings(rows.iter().map(|row| row.barrier_first_hit.clone())),
            opt_u64s(rows.iter().map(|row| row.barrier_first_hit_minutes)),
        ],
    )
    .context("failed to build CEX market state batch")
}

fn dex_lag_panel_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        field_utf8("run_tag", false),
        field_u64("block_number", false),
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
        field_utf8("diagnostic_status", false),
    ]))
}

fn dex_lag_panel_batch(schema: SchemaRef, rows: &[DexLagPanelRow]) -> Result<RecordBatch> {
    RecordBatch::try_new(
        schema,
        vec![
            strings(rows.iter().map(|row| row.run_tag.clone())),
            u64s(rows.iter().map(|row| row.block_number)),
            strings(rows.iter().map(|row| row.event_time_utc.clone())),
            u64s(rows.iter().map(|row| row.minute_timestamp.max(0) as u64)),
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
            strings(rows.iter().map(|row| row.diagnostic_status.clone())),
        ],
    )
    .context("failed to build CEX-DEX lag panel batch")
}

fn write_report(
    summary: &CexDynamicsSummary,
    dynamics_rows: &[CexDynamicsSummaryRow],
    lag_rows: &[DexLagSummaryRow],
) -> Result<()> {
    let overall = dynamics_rows
        .iter()
        .filter(|row| row.group == "overall" && row.group_value == "all")
        .map(|row| {
            format!(
                "| {} | {} | {} | {} | {} | {} | {} |",
                row.frequency,
                row.rows,
                row.cex_factor_rows,
                row.anchor_source,
                fmt_rate(row.compressed_range_rate),
                fmt_rate(row.positive_cusum_rate),
                fmt_opt(row.median_realized_vol_bps)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let lag_overall = lag_rows
        .iter()
        .filter(|row| row.group == "overall" || row.group == "pool")
        .take(12)
        .map(|row| {
            format!(
                "| {} | {} | {} | {} | {} | {} | {} | {} |",
                row.group,
                row.group_value,
                row.rows,
                row.priced_rows,
                fmt_opt(row.median_abs_dislocation_bps),
                fmt_rate(row.cost_adjusted_positive_rate),
                row.best_lag_minutes
                    .map(|value| value.to_string())
                    .unwrap_or_else(|| "NA".to_string()),
                fmt_opt(row.best_lag_corr)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    let cex_status = if summary.coverage.cex_um_futures_kline_rows > 0 {
        "已发现 Binance USD-M futures `MONUSDT` kline，本次使用 futures `MONUSDT` 作为 MON anchor；CEX basket 仍用于市场状态压缩。"
    } else if summary.coverage.cex_kline_rows == 0 {
        "未发现本地 Binance kline CSV，本次使用 `mon_usdc_minute_price_reference` 作为 fallback anchor；因此报告只能说明价格序列和 DEX 相对参考价偏离，不能证明 CEX 领先。"
    } else {
        "已发现本地 Binance kline CSV，CEX factor rows 可用于检验主价格驱动。"
    };
    let body = format!(
        "# MON/USDC V1 CEX Dynamics Report\n\n状态: `{}`。\n\n这份报告把研究重心从链上单事件切到 `CEX anchor -> DEX lag/dislocation -> path stopping labels`。它不运行 RPC、不重采链上 raw data、不声称已经得到可执行套利策略。{}\n\n## 数据覆盖\n\n- Binance spot kline CSV files: `{}`\n- Binance spot kline rows: `{}`\n- Binance USD-M futures kline CSV files: `{}`\n- Binance USD-M futures kline rows: `{}`\n- Binance aggTrade CSV files: `{}`\n- Binance aggTrade rows: `{}`\n- ignored non-CSV files: `{}`\n- CEX symbols available: `{}`\n- minute reference rows: `{}`\n- event price rows: `{}`\n- market-state rows: `{}`\n- DEX lag panel rows: `{}`\n\n## Market-State Summary\n\n| Frequency | Rows | CEX Factor Rows | Anchor Source | compressed_range | positive_cusum | Median Realized Vol bps |\n| --- | ---: | ---: | --- | ---: | ---: | ---: |\n{}\n\n## DEX-CEX / Reference Lag Summary\n\n| Group | Value | Rows | Priced Rows | Median Abs Dislocation bps | Cost-Adjusted Positive | Best Lag min | Best Lag Corr |\n| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |\n{}\n\n## 研究解释\n\n- `MKT/L1/MEME/SIZE_ROT/LIQ/avg_corr` 是低算力 CEX 状态压缩，不是机器学习模型。\n- 如果 `anchor_source = binance_um_futures_monusdt`，`dislocation_bps` 表示 DEX pool 相对 Binance USD-M futures MONUSDT 的偏离。\n- 如果 `anchor_source = dex_minute_reference_fallback`，`dislocation_bps` 表示单池价格相对聚合 minute reference 的偏离，不是相对 Binance 的真实偏离。\n- 订单簿因子放到 v2/live collector；v1 不回补历史 order book，也不信 raw depth 单独作为阻力。\n- `barrier_first_hit`、`compressed_range`、`positive_cusum_regime` 是价格序列停时标签，用来替代过于平的固定 future return。\n\n## 输出\n\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n- `{}`\n",
        summary.run_tag,
        cex_status,
        summary.coverage.cex_kline_files,
        summary.coverage.cex_kline_rows,
        summary.coverage.cex_um_futures_kline_files,
        summary.coverage.cex_um_futures_kline_rows,
        summary.coverage.cex_agg_trade_files,
        summary.coverage.cex_agg_trade_rows,
        summary.coverage.ignored_non_csv_files,
        summary.coverage.cex_symbols_available.join(", "),
        summary.coverage.minute_price_rows,
        summary.coverage.event_price_rows,
        summary.coverage.market_state_rows,
        summary.coverage.dex_lag_panel_rows,
        overall,
        lag_overall,
        summary.outputs.market_state_parquet,
        summary.outputs.dex_lag_panel_parquet,
        summary.outputs.dynamics_summary_csv,
        summary.outputs.dex_lag_summary_csv,
        summary.outputs.completion_json
    );
    let path = Path::new(&summary.outputs.report);
    ensure_parent_dir(path)?;
    fs::write(path, body).with_context(|| format!("failed to write {}", path.display()))
}

fn read_parquet_batches<F>(path: &Path, mut on_batch: F) -> Result<()>
where
    F: FnMut(&RecordBatch) -> Result<()>,
{
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(8192)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        on_batch(&batch)?;
    }
    Ok(())
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

fn bool_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a BooleanArray> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<BooleanArray>()
        .ok_or_else(|| anyhow!("column {name} is not boolean"))
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

fn f64_option(values: &Float64Array, index: usize) -> Option<f64> {
    if values.is_null(index) {
        None
    } else {
        finite(values.value(index))
    }
}

fn bool_value(values: &BooleanArray, index: usize) -> bool {
    !values.is_null(index) && values.value(index)
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
    let mut builder = StringBuilder::with_capacity(values.len(), values.len() * 16);
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
    let mut builder = BooleanBuilder::with_capacity(values.len());
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

fn write_csv<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    ensure_parent_dir(path)?;
    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create {}", path.display()))?;
    for row in rows {
        writer.serialize(row)?;
    }
    writer.flush()?;
    Ok(())
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    ensure_parent_dir(path)?;
    let file =
        File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, value)
        .with_context(|| format!("failed to write {}", path.display()))
}

fn sum_options<I>(values: I) -> Option<f64>
where
    I: IntoIterator<Item = Option<f64>>,
{
    let values = values.into_iter().flatten().collect::<Vec<_>>();
    if values.is_empty() {
        None
    } else {
        Some(values.iter().sum())
    }
}

fn corr_options(x: &[Option<f64>], y: &[Option<f64>]) -> Option<f64> {
    let (xv, yv): (Vec<_>, Vec<_>) = x
        .iter()
        .zip(y.iter())
        .filter_map(|(a, b)| match (*a, *b) {
            (Some(a), Some(b)) => Some((a, b)),
            _ => None,
        })
        .unzip();
    corr_values(&xv, &yv)
}

fn corr_values(x: &[f64], y: &[f64]) -> Option<f64> {
    if x.len() != y.len() || x.len() < 5 {
        return None;
    }
    let mean_x = x.iter().sum::<f64>() / x.len() as f64;
    let mean_y = y.iter().sum::<f64>() / y.len() as f64;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    for (a, b) in x.iter().zip(y.iter()) {
        cov += (a - mean_x) * (b - mean_y);
        var_x += (a - mean_x).powi(2);
        var_y += (b - mean_y).powi(2);
    }
    let denom = (var_x * var_y).sqrt();
    (denom > 0.0).then_some(cov / denom)
}

fn beta_values(x: &[f64], y: &[f64]) -> Option<f64> {
    if x.len() != y.len() || x.len() < 5 {
        return None;
    }
    let mean_x = x.iter().sum::<f64>() / x.len() as f64;
    let mean_y = y.iter().sum::<f64>() / y.len() as f64;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    for (a, b) in x.iter().zip(y.iter()) {
        cov += (a - mean_x) * (b - mean_y);
        var_x += (a - mean_x).powi(2);
    }
    (var_x > 0.0).then_some(cov / var_x)
}

fn thresholds<I>(values: I, buckets: usize) -> Vec<f64>
where
    I: IntoIterator<Item = f64>,
{
    let mut values = values
        .into_iter()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    values.sort_by(|a, b| a.total_cmp(b));
    values.dedup_by(|a, b| (*a - *b).abs() < f64::EPSILON);
    if buckets <= 1 || values.len() < buckets {
        return Vec::new();
    }
    let len = values.len();
    (1..buckets)
        .filter_map(|bucket| values.get(((len * bucket) / buckets).min(len - 1)).copied())
        .collect()
}

fn regime_bucket(value: Option<f64>, thresholds: &[f64]) -> String {
    let Some(value) = value.and_then(finite) else {
        return "unavailable".to_string();
    };
    if thresholds.is_empty() {
        return "unavailable".to_string();
    }
    let mut bucket = 0usize;
    while bucket < thresholds.len() && value > thresholds[bucket] {
        bucket += 1;
    }
    match bucket {
        0 => "low",
        1 => "mid",
        _ => "high",
    }
    .to_string()
}

fn quantile(mut values: Vec<f64>, q: f64) -> Option<f64> {
    values.retain(|value| value.is_finite());
    if values.is_empty() {
        return None;
    }
    values.sort_by(|a, b| a.total_cmp(b));
    let index = (((values.len() - 1) as f64) * q.clamp(0.0, 1.0)).round() as usize;
    values.get(index).copied()
}

fn rate(count: u64, total: u64) -> Option<f64> {
    (total > 0).then_some(count as f64 / total as f64)
}

fn most_common<'a, I>(values: I) -> String
where
    I: IntoIterator<Item = &'a str>,
{
    let mut counts = BTreeMap::<String, u64>::new();
    for value in values {
        *counts.entry(value.to_string()).or_default() += 1;
    }
    counts
        .into_iter()
        .max_by_key(|(_, count)| *count)
        .map(|(value, _)| value)
        .unwrap_or_else(|| "unavailable".to_string())
}

fn chronological_split_map<I>(dates: I) -> BTreeMap<String, String>
where
    I: IntoIterator<Item = String>,
{
    let unique = dates
        .into_iter()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let n = unique.len();
    if n == 0 {
        return BTreeMap::new();
    }
    let discovery_end = ((n as f64) * 0.60).floor().max(1.0) as usize;
    let validation_end = ((n as f64) * 0.80)
        .floor()
        .max(discovery_end as f64 + 1.0)
        .min(n as f64) as usize;
    unique
        .into_iter()
        .enumerate()
        .map(|(index, date)| {
            let split = if index < discovery_end {
                "discovery"
            } else if index < validation_end {
                "validation"
            } else {
                "forward"
            };
            (date, split.to_string())
        })
        .collect()
}

fn finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn to_bps(value: f64) -> f64 {
    value * 10_000.0
}

fn floor_to_minute(timestamp: i64) -> i64 {
    timestamp - timestamp.rem_euclid(60)
}

fn date_from_ts(timestamp: i64) -> String {
    DateTime::<Utc>::from_timestamp(timestamp, 0)
        .map(|value| value.format("%Y-%m-%d").to_string())
        .unwrap_or_else(|| "unknown".to_string())
}

fn utc_from_timestamp(timestamp: i64) -> String {
    DateTime::<Utc>::from_timestamp(timestamp, 0)
        .map(|value| value.to_rfc3339_opts(SecondsFormat::Secs, true))
        .unwrap_or_default()
}

fn fmt_rate(value: Option<f64>) -> String {
    value
        .map(|value| format!("{:.2}%", value * 100.0))
        .unwrap_or_else(|| "NA".to_string())
}

fn fmt_opt(value: Option<f64>) -> String {
    value
        .map(|value| format!("{value:.4}"))
        .unwrap_or_else(|| "NA".to_string())
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
    fn cex_dynamics_log_return_uses_close_ratio() {
        let mut by_symbol = HashMap::new();
        by_symbol.insert(
            "BTCUSDT".to_string(),
            BTreeMap::from([
                (60, (100.0, 1.0, "binance_spot".to_string())),
                (120, (110.0, 1.0, "binance_spot".to_string())),
            ]),
        );
        let returns = build_returns_by_symbol(&by_symbol);
        let ret = returns.get("BTCUSDT").unwrap().get(&120).copied().unwrap();
        assert!((ret - (1.1f64).ln()).abs() < 1e-12);
    }

    #[test]
    fn cex_dynamics_epoch_normalizes_seconds_ms_us_and_ns() {
        let seconds = 1_735_689_600i64;
        assert_eq!(epoch_to_seconds(seconds), seconds);
        assert_eq!(epoch_to_seconds(seconds * 1_000), seconds);
        assert_eq!(epoch_to_seconds(seconds * 1_000_000), seconds);
        assert_eq!(epoch_to_seconds(seconds * 1_000_000_000), seconds);
    }

    #[test]
    fn cex_dynamics_ridge_beta_recovers_linear_relation() {
        let samples = (1..100)
            .map(|i| {
                let x1 = i as f64 / 10_000.0;
                let x2 = ((i * i) % 37) as f64 / 10_000.0;
                let x3 = ((i * 17) % 29) as f64 / 10_000.0;
                [2.0 * x1 - 1.0 * x2 + 0.5 * x3, x1, x2, x3]
            })
            .collect::<Vec<_>>();
        let beta = ridge_beta_3(&samples, 1e-12);
        assert!((beta[0] - 2.0).abs() < 1e-6);
        assert!((beta[1] + 1.0).abs() < 1e-6);
        assert!((beta[2] - 0.5).abs() < 1e-6);
    }

    #[test]
    fn cex_dynamics_cusum_flags_positive_drift() {
        let returns = vec![Some(0.002); 10];
        let mut rows = (0..10)
            .map(|i| MarketStateRow {
                run_tag: "run".to_string(),
                frequency: "1m".to_string(),
                timestamp: i * 60,
                minute_utc: String::new(),
                split: "discovery".to_string(),
                anchor_symbol: "MON/USDC".to_string(),
                anchor_source: "test".to_string(),
                anchor_price: Some(1.0),
                anchor_return: returns[i as usize],
                mkt_return: None,
                l1_return: None,
                meme_return: None,
                size_rot_return: None,
                liq_score: None,
                avg_corr: None,
                realized_vol_1h: None,
                vol_state: "unavailable".to_string(),
                beta_mkt: None,
                beta_l1: None,
                beta_meme: None,
                beta_residual: None,
                compressed_range: false,
                upper_breakout: false,
                lower_breakout: false,
                drawdown_recovery: false,
                positive_cusum_regime: false,
                barrier_first_hit: "none".to_string(),
                barrier_first_hit_minutes: None,
            })
            .collect::<Vec<_>>();
        apply_cusum_labels(&mut rows, &returns, 0.0001, 0.005);
        assert!(rows.iter().any(|row| row.positive_cusum_regime));
    }

    #[test]
    fn cex_dynamics_barrier_first_hit_orders_upper_before_lower() {
        let returns = vec![Some(0.0), Some(0.006), Some(-0.02)];
        let mut rows = (0..returns.len())
            .map(|i| MarketStateRow {
                run_tag: "run".to_string(),
                frequency: "1m".to_string(),
                timestamp: (i as i64) * 60,
                minute_utc: String::new(),
                split: "discovery".to_string(),
                anchor_symbol: "MON/USDC".to_string(),
                anchor_source: "test".to_string(),
                anchor_price: Some(1.0),
                anchor_return: returns[i],
                mkt_return: None,
                l1_return: None,
                meme_return: None,
                size_rot_return: None,
                liq_score: None,
                avg_corr: None,
                realized_vol_1h: None,
                vol_state: "unavailable".to_string(),
                beta_mkt: None,
                beta_l1: None,
                beta_meme: None,
                beta_residual: None,
                compressed_range: false,
                upper_breakout: false,
                lower_breakout: false,
                drawdown_recovery: false,
                positive_cusum_regime: false,
                barrier_first_hit: "none".to_string(),
                barrier_first_hit_minutes: None,
            })
            .collect::<Vec<_>>();
        apply_price_sequence_labels(&mut rows, &returns, 2, 0.001, 0.005, 2);
        assert_eq!(rows[0].barrier_first_hit, "upper");
        assert_eq!(rows[0].barrier_first_hit_minutes, Some(1));
    }

    #[test]
    fn cex_dynamics_dislocation_is_log_pool_over_anchor_bps() {
        let config = CexDynamicsConfig::default();
        let market = vec![MarketStateRow {
            run_tag: "run".to_string(),
            frequency: "1m".to_string(),
            timestamp: 60,
            minute_utc: String::new(),
            split: "discovery".to_string(),
            anchor_symbol: "MON/USDC".to_string(),
            anchor_source: "test".to_string(),
            anchor_price: Some(2.0),
            anchor_return: None,
            mkt_return: None,
            l1_return: None,
            meme_return: None,
            size_rot_return: None,
            liq_score: None,
            avg_corr: None,
            realized_vol_1h: None,
            vol_state: "unavailable".to_string(),
            beta_mkt: None,
            beta_l1: None,
            beta_meme: None,
            beta_residual: None,
            compressed_range: false,
            upper_breakout: false,
            lower_breakout: false,
            drawdown_recovery: false,
            positive_cusum_regime: false,
            barrier_first_hit: "none".to_string(),
            barrier_first_hit_minutes: None,
        }];
        let events = vec![EventPriceRow {
            block_number: 1,
            timestamp: 60,
            transaction_hash: "0x1".to_string(),
            log_index: 0,
            pool_address: "0xpool".to_string(),
            dex_id: "dex".to_string(),
            family: "v3".to_string(),
            direction: "buy_base".to_string(),
            clean_keep: true,
            price_quote_per_base: Some(2.2),
            quote_abs: Some(1.0),
        }];
        let rows = build_dex_lag_panel(&config, &market, &events).unwrap();
        let expected = 10_000.0 * (1.1f64).ln();
        assert!((rows[0].dislocation_bps.unwrap() - expected).abs() < 1e-12);
    }
}

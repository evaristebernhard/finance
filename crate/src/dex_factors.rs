use std::collections::BTreeMap;
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow};
use arrow::array::{Array, BooleanArray, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::Serialize;

use crate::chog_v1::{
    RAW_DIR, bool_array, opt_f64_array, opt_i64_array, opt_u64_array, parquet_files_under,
    string_array, u64_array, write_parquet_part, write_schema_metadata,
};
use crate::dex::{CHOG_TOKEN, DEX_SWAP_DATASET};
use crate::dex_hourly::derived_part_path;

pub const DEX_SWAP_FACTORS_DATASET: &str = "dex_swap_factors";

const Q96: f64 = 79_228_162_514_264_337_593_543_950_336.0;
const FACTOR_NAMES: &[&str] = &[
    "price_log_return_1",
    "log_chog_amount",
    "log_quote_amount",
    "signed_chog_flow",
    "rolling_5_buy_ratio",
    "rolling_5_net_flow_chog",
    "rolling_5_chog_volume",
    "rolling_5_realized_volatility",
    "rolling_20_buy_ratio",
    "rolling_20_net_flow_chog",
    "rolling_20_chog_volume",
    "rolling_20_realized_volatility",
    "execution_vs_terminal_price_bps",
    "liquidity_log",
    "tick_move_from_prev",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DexFactorPartSummary {
    pub dt: String,
    pub rows: usize,
    pub path: PathBuf,
}

#[derive(Debug, Clone, Serialize)]
pub struct DexFactorReport {
    pub dataset: String,
    pub input_rows: u64,
    pub factor_rows: u64,
    pub target_rows: u64,
    pub pools: u64,
    pub min_block: Option<u64>,
    pub max_block: Option<u64>,
    pub parquet_parts: u64,
    pub invariant_diagnostics: InvariantDiagnostics,
    pub factor_tests: Vec<FactorTest>,
}

#[derive(Debug, Clone, Serialize)]
pub struct InvariantDiagnostics {
    pub delta_sign_invalid: u64,
    pub direction_mismatch: u64,
    pub amount_price_consistency_checked: u64,
    pub amount_price_consistency_over_1bp: u64,
    pub max_amount_price_consistency_bps: Option<f64>,
    pub v3_rows: u64,
    pub v3_terminal_price_rows: u64,
    pub max_execution_vs_terminal_abs_bps: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FactorTest {
    pub factor: String,
    pub observations: u64,
    pub buckets: u64,
    pub pearson: Option<f64>,
    pub spearman: Option<f64>,
    pub bottom_mean_target: Option<f64>,
    pub top_mean_target: Option<f64>,
    pub top_minus_bottom: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct DexFactorRebuildSummary {
    pub input_root: PathBuf,
    pub min_block: Option<u64>,
    pub max_block: Option<u64>,
    pub factor_rows: u64,
    pub target_rows: u64,
    pub parquet_parts: u64,
    pub parts: Vec<DexFactorPartSummary>,
    pub report: DexFactorReport,
    pub dry_run: bool,
}

#[derive(Debug, Clone)]
struct RawSwap {
    fetched_at_utc: String,
    block_number: u64,
    block_timestamp: u64,
    block_datetime_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    token0_address: String,
    token1_address: String,
    token0_symbol: String,
    token1_symbol: String,
    token0_decimals: u64,
    token1_decimals: u64,
    quote_address: String,
    quote_symbol: String,
    amount0_delta_raw: String,
    amount1_delta_raw: String,
    direction: String,
    chog_abs: String,
    quote_abs: String,
    price_quote_per_chog: String,
    sqrt_price_x96: Option<String>,
    liquidity_raw: Option<String>,
    tick: Option<String>,
    removed: bool,
    dt: String,
}

#[derive(Debug, Clone)]
struct FactorRow {
    fetched_at_utc: String,
    block_number: u64,
    block_timestamp: u64,
    block_datetime_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    token0_address: String,
    token1_address: String,
    token0_symbol: String,
    token1_symbol: String,
    token0_decimals: u64,
    token1_decimals: u64,
    quote_address: String,
    quote_symbol: String,
    direction: String,
    chog_amount: Option<f64>,
    quote_amount: Option<f64>,
    price_quote_per_chog: Option<f64>,
    signed_chog_flow: Option<f64>,
    log_chog_amount: Option<f64>,
    log_quote_amount: Option<f64>,
    price_log_return_1: Option<f64>,
    seconds_since_prev_swap: Option<u64>,
    blocks_since_prev_swap: Option<u64>,
    rolling_5_buy_ratio: Option<f64>,
    rolling_5_net_flow_chog: Option<f64>,
    rolling_5_chog_volume: Option<f64>,
    rolling_5_realized_volatility: Option<f64>,
    rolling_20_buy_ratio: Option<f64>,
    rolling_20_net_flow_chog: Option<f64>,
    rolling_20_chog_volume: Option<f64>,
    rolling_20_realized_volatility: Option<f64>,
    next_price_quote_per_chog: Option<f64>,
    target_next_swap_log_return: Option<f64>,
    delta_sign_valid: bool,
    direction_sign_consistent: bool,
    amount_price_consistency_bps: Option<f64>,
    v3_terminal_price_quote_per_chog: Option<f64>,
    execution_vs_terminal_price_bps: Option<f64>,
    liquidity_log: Option<f64>,
    tick: Option<i64>,
    tick_move_from_prev: Option<i64>,
    dt: String,
}

#[derive(Default)]
struct RollingStats {
    buy_ratio: Option<f64>,
    net_flow_chog: Option<f64>,
    chog_volume: Option<f64>,
    realized_volatility: Option<f64>,
}

pub fn rebuild_dex_swap_factors(
    data_root: &Path,
    dry_run: bool,
    top: usize,
) -> Result<DexFactorRebuildSummary> {
    let input_root = data_root.join(RAW_DIR).join(DEX_SWAP_DATASET);
    let mut raw_rows = Vec::new();
    for path in parquet_files_under(&input_root)? {
        read_swap_file(&path, &mut raw_rows)?;
    }
    raw_rows.sort_by(event_order);

    let factor_rows = build_factor_rows(&raw_rows);
    let report = build_report(&raw_rows, &factor_rows, top);
    let parts = planned_parts(data_root, &factor_rows);
    if dry_run {
        return Ok(DexFactorRebuildSummary {
            input_root,
            min_block: report.min_block,
            max_block: report.max_block,
            factor_rows: factor_rows.len() as u64,
            target_rows: report.target_rows,
            parquet_parts: parts.len() as u64,
            parts,
            report,
            dry_run,
        });
    }

    let schema = factor_schema();
    write_schema_metadata(
        data_root,
        DEX_SWAP_FACTORS_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let mut written_parts = Vec::new();
    for (dt, rows) in rows_by_dt(factor_rows) {
        let batch = factor_rows_to_batch(schema.clone(), &rows)?;
        let path = factor_part_path(data_root, &rows, &dt);
        let write = write_parquet_part(&path, schema.clone(), batch)?;
        written_parts.push(DexFactorPartSummary {
            dt,
            rows: write.rows,
            path: write.path,
        });
    }

    Ok(DexFactorRebuildSummary {
        input_root,
        min_block: report.min_block,
        max_block: report.max_block,
        factor_rows: report.factor_rows,
        target_rows: report.target_rows,
        parquet_parts: written_parts.len() as u64,
        parts: written_parts,
        report,
        dry_run,
    })
}

fn read_swap_file(path: &Path, rows: &mut Vec<RawSwap>) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(4096)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let fetched_at_utc = string_column(&batch, "fetched_at_utc")?;
        let block_number = uint64_column(&batch, "block_number")?;
        let block_timestamp = uint64_column(&batch, "block_timestamp")?;
        let block_datetime_utc = string_column(&batch, "block_datetime_utc")?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        let transaction_index = uint64_column(&batch, "transaction_index")?;
        let log_index = uint64_column(&batch, "log_index")?;
        let pool_address = string_column(&batch, "pool_address")?;
        let dex_id = string_column(&batch, "dex_id")?;
        let family = string_column(&batch, "family")?;
        let token0_address = string_column(&batch, "token0_address")?;
        let token1_address = string_column(&batch, "token1_address")?;
        let token0_symbol = string_column(&batch, "token0_symbol")?;
        let token1_symbol = string_column(&batch, "token1_symbol")?;
        let token0_decimals = uint64_column(&batch, "token0_decimals")?;
        let token1_decimals = uint64_column(&batch, "token1_decimals")?;
        let quote_address = string_column(&batch, "quote_address")?;
        let quote_symbol = string_column(&batch, "quote_symbol")?;
        let amount0_delta_raw = string_column(&batch, "amount0_delta_raw")?;
        let amount1_delta_raw = string_column(&batch, "amount1_delta_raw")?;
        let direction = string_column(&batch, "direction")?;
        let chog_abs = string_column(&batch, "chog_abs")?;
        let quote_abs = string_column(&batch, "quote_abs")?;
        let price_quote_per_chog = string_column(&batch, "price_quote_per_chog")?;
        let sqrt_price_x96 = optional_string_column(&batch, "sqrt_price_x96")?;
        let liquidity_raw = optional_string_column(&batch, "liquidity_raw")?;
        let tick = optional_string_column(&batch, "tick")?;
        let removed = bool_column(&batch, "removed")?;
        let dt = string_column(&batch, "dt")?;
        for index in 0..batch.num_rows() {
            rows.push(RawSwap {
                fetched_at_utc: string_value(fetched_at_utc, index),
                block_number: block_number.value(index),
                block_timestamp: block_timestamp.value(index),
                block_datetime_utc: string_value(block_datetime_utc, index),
                transaction_hash: string_value(transaction_hash, index),
                transaction_index: transaction_index.value(index),
                log_index: log_index.value(index),
                pool_address: string_value(pool_address, index).to_ascii_lowercase(),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                token0_address: string_value(token0_address, index).to_ascii_lowercase(),
                token1_address: string_value(token1_address, index).to_ascii_lowercase(),
                token0_symbol: string_value(token0_symbol, index),
                token1_symbol: string_value(token1_symbol, index),
                token0_decimals: token0_decimals.value(index),
                token1_decimals: token1_decimals.value(index),
                quote_address: string_value(quote_address, index).to_ascii_lowercase(),
                quote_symbol: string_value(quote_symbol, index),
                amount0_delta_raw: string_value(amount0_delta_raw, index),
                amount1_delta_raw: string_value(amount1_delta_raw, index),
                direction: string_value(direction, index),
                chog_abs: string_value(chog_abs, index),
                quote_abs: string_value(quote_abs, index),
                price_quote_per_chog: string_value(price_quote_per_chog, index),
                sqrt_price_x96: optional_string(sqrt_price_x96, index),
                liquidity_raw: optional_string(liquidity_raw, index),
                tick: optional_string(tick, index),
                removed: !removed.is_null(index) && removed.value(index),
                dt: string_value(dt, index),
            });
        }
    }
    Ok(())
}

fn build_factor_rows(raw_rows: &[RawSwap]) -> Vec<FactorRow> {
    let mut by_pool = BTreeMap::<String, Vec<&RawSwap>>::new();
    for row in raw_rows.iter().filter(|row| !row.removed) {
        by_pool
            .entry(row.pool_address.clone())
            .or_default()
            .push(row);
    }

    let mut rows = Vec::new();
    for (_pool, mut pool_rows) in by_pool {
        pool_rows.sort_by(|a, b| event_order(a, b));
        let mut one_step_returns = vec![None; pool_rows.len()];
        for index in 0..pool_rows.len() {
            let current = pool_rows[index];
            let previous = index.checked_sub(1).map(|value| pool_rows[value]);
            let next = pool_rows.get(index + 1).copied();
            let chog_amount = parse_f64(&current.chog_abs);
            let quote_amount = parse_f64(&current.quote_abs);
            let price = parse_f64(&current.price_quote_per_chog);
            let previous_price = previous.and_then(|row| parse_f64(&row.price_quote_per_chog));
            let price_log_return_1 = log_return(price, previous_price);
            one_step_returns[index] = price_log_return_1;
            let next_price = next.and_then(|row| parse_f64(&row.price_quote_per_chog));
            let target_next_swap_log_return = log_return(next_price, price);
            let signed_chog_flow = chog_amount.map(|amount| {
                if current.direction == "buy_chog" {
                    amount
                } else if current.direction == "sell_chog" {
                    -amount
                } else {
                    0.0
                }
            });
            let delta0 = parse_i128(&current.amount0_delta_raw);
            let delta1 = parse_i128(&current.amount1_delta_raw);
            let delta_sign_valid = matches!((delta0, delta1), (Some(a), Some(b)) if (a > 0 && b < 0) || (a < 0 && b > 0));
            let direction_sign_consistent = direction_sign_consistent(current, delta0, delta1);
            let amount_price_consistency_bps =
                amount_price_consistency_bps(quote_amount, chog_amount, price);
            let v3_terminal_price_quote_per_chog = if current.family == "v3" {
                v3_terminal_price_quote_per_chog(current)
            } else {
                None
            };
            let execution_vs_terminal_price_bps =
                bps_difference(price, v3_terminal_price_quote_per_chog);
            let tick = current.tick.as_deref().and_then(parse_i64);
            let previous_tick = previous
                .and_then(|row| row.tick.as_deref())
                .and_then(parse_i64);
            let liquidity_log = current
                .liquidity_raw
                .as_deref()
                .and_then(parse_f64)
                .filter(|value| *value > 0.0)
                .map(f64::ln);
            let rolling_5 = rolling_stats(&pool_rows, &one_step_returns, index, 5);
            let rolling_20 = rolling_stats(&pool_rows, &one_step_returns, index, 20);

            rows.push(FactorRow {
                fetched_at_utc: current.fetched_at_utc.clone(),
                block_number: current.block_number,
                block_timestamp: current.block_timestamp,
                block_datetime_utc: current.block_datetime_utc.clone(),
                transaction_hash: current.transaction_hash.clone(),
                transaction_index: current.transaction_index,
                log_index: current.log_index,
                pool_address: current.pool_address.clone(),
                dex_id: current.dex_id.clone(),
                family: current.family.clone(),
                token0_address: current.token0_address.clone(),
                token1_address: current.token1_address.clone(),
                token0_symbol: current.token0_symbol.clone(),
                token1_symbol: current.token1_symbol.clone(),
                token0_decimals: current.token0_decimals,
                token1_decimals: current.token1_decimals,
                quote_address: current.quote_address.clone(),
                quote_symbol: current.quote_symbol.clone(),
                direction: current.direction.clone(),
                chog_amount,
                quote_amount,
                price_quote_per_chog: price,
                signed_chog_flow,
                log_chog_amount: chog_amount.filter(|value| *value > 0.0).map(f64::ln),
                log_quote_amount: quote_amount.filter(|value| *value > 0.0).map(f64::ln),
                price_log_return_1,
                seconds_since_prev_swap: previous.and_then(|row| {
                    current
                        .block_timestamp
                        .checked_sub(row.block_timestamp)
                        .filter(|value| *value > 0)
                }),
                blocks_since_prev_swap: previous.and_then(|row| {
                    current
                        .block_number
                        .checked_sub(row.block_number)
                        .filter(|value| *value > 0)
                }),
                rolling_5_buy_ratio: rolling_5.buy_ratio,
                rolling_5_net_flow_chog: rolling_5.net_flow_chog,
                rolling_5_chog_volume: rolling_5.chog_volume,
                rolling_5_realized_volatility: rolling_5.realized_volatility,
                rolling_20_buy_ratio: rolling_20.buy_ratio,
                rolling_20_net_flow_chog: rolling_20.net_flow_chog,
                rolling_20_chog_volume: rolling_20.chog_volume,
                rolling_20_realized_volatility: rolling_20.realized_volatility,
                next_price_quote_per_chog: next_price,
                target_next_swap_log_return,
                delta_sign_valid,
                direction_sign_consistent,
                amount_price_consistency_bps,
                v3_terminal_price_quote_per_chog,
                execution_vs_terminal_price_bps,
                liquidity_log,
                tick,
                tick_move_from_prev: match (tick, previous_tick) {
                    (Some(current), Some(previous)) => Some(current - previous),
                    _ => None,
                },
                dt: current.dt.clone(),
            });
        }
    }
    rows.sort_by(factor_event_order);
    rows
}

fn build_report(raw_rows: &[RawSwap], rows: &[FactorRow], top: usize) -> DexFactorReport {
    let mut diagnostics = InvariantDiagnostics {
        delta_sign_invalid: 0,
        direction_mismatch: 0,
        amount_price_consistency_checked: 0,
        amount_price_consistency_over_1bp: 0,
        max_amount_price_consistency_bps: None,
        v3_rows: 0,
        v3_terminal_price_rows: 0,
        max_execution_vs_terminal_abs_bps: None,
    };
    let mut pools = BTreeMap::<String, ()>::new();
    let mut min_block = None::<u64>;
    let mut max_block = None::<u64>;
    let mut target_rows = 0u64;
    for row in rows {
        pools.insert(row.pool_address.clone(), ());
        min_block = Some(min_block.map_or(row.block_number, |value| value.min(row.block_number)));
        max_block = Some(max_block.map_or(row.block_number, |value| value.max(row.block_number)));
        if row.target_next_swap_log_return.is_some() {
            target_rows += 1;
        }
        if !row.delta_sign_valid {
            diagnostics.delta_sign_invalid += 1;
        }
        if !row.direction_sign_consistent {
            diagnostics.direction_mismatch += 1;
        }
        if let Some(bps) = row.amount_price_consistency_bps {
            diagnostics.amount_price_consistency_checked += 1;
            if bps.abs() > 1.0 {
                diagnostics.amount_price_consistency_over_1bp += 1;
            }
            update_max_abs(&mut diagnostics.max_amount_price_consistency_bps, bps);
        }
        if row.family == "v3" {
            diagnostics.v3_rows += 1;
        }
        if row.v3_terminal_price_quote_per_chog.is_some() {
            diagnostics.v3_terminal_price_rows += 1;
        }
        if let Some(bps) = row.execution_vs_terminal_price_bps {
            update_max_abs(&mut diagnostics.max_execution_vs_terminal_abs_bps, bps);
        }
    }
    let mut factor_tests = FACTOR_NAMES
        .iter()
        .map(|factor| factor_test(factor, rows))
        .filter(|test| test.observations > 0)
        .collect::<Vec<_>>();
    factor_tests.sort_by(|a, b| {
        abs_option(b.spearman)
            .total_cmp(&abs_option(a.spearman))
            .then_with(|| b.observations.cmp(&a.observations))
            .then_with(|| a.factor.cmp(&b.factor))
    });
    factor_tests.truncate(top);

    DexFactorReport {
        dataset: DEX_SWAP_FACTORS_DATASET.to_string(),
        input_rows: raw_rows.len() as u64,
        factor_rows: rows.len() as u64,
        target_rows,
        pools: pools.len() as u64,
        min_block,
        max_block,
        parquet_parts: planned_parts_from_rows(rows).len() as u64,
        invariant_diagnostics: diagnostics,
        factor_tests,
    }
}

fn factor_test(factor: &str, rows: &[FactorRow]) -> FactorTest {
    let mut pairs = rows
        .iter()
        .filter_map(|row| Some((factor_value(factor, row)?, row.target_next_swap_log_return?)))
        .filter(|(x, y)| x.is_finite() && y.is_finite())
        .collect::<Vec<_>>();
    if pairs.is_empty() {
        return FactorTest {
            factor: factor.to_string(),
            observations: 0,
            buckets: 0,
            pearson: None,
            spearman: None,
            bottom_mean_target: None,
            top_mean_target: None,
            top_minus_bottom: None,
        };
    }
    let pearson = correlation(&pairs);
    let spearman = rank_correlation(&pairs);
    pairs.sort_by(|a, b| a.0.total_cmp(&b.0));
    let buckets = if pairs.len() >= 200 { 5 } else { 3 };
    let bucket_size = pairs.len().div_ceil(buckets);
    let bottom_mean = mean_targets(&pairs[..pairs.len().min(bucket_size)]);
    let top_start = pairs.len().saturating_sub(bucket_size);
    let top_mean = mean_targets(&pairs[top_start..]);
    FactorTest {
        factor: factor.to_string(),
        observations: pairs.len() as u64,
        buckets: buckets as u64,
        pearson,
        spearman,
        bottom_mean_target: bottom_mean,
        top_mean_target: top_mean,
        top_minus_bottom: match (top_mean, bottom_mean) {
            (Some(top), Some(bottom)) => Some(top - bottom),
            _ => None,
        },
    }
}

fn factor_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, false),
        Field::new("block_timestamp", DataType::UInt64, false),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("token0_address", DataType::Utf8, false),
        Field::new("token1_address", DataType::Utf8, false),
        Field::new("token0_symbol", DataType::Utf8, false),
        Field::new("token1_symbol", DataType::Utf8, false),
        Field::new("token0_decimals", DataType::UInt64, false),
        Field::new("token1_decimals", DataType::UInt64, false),
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("chog_amount", DataType::Float64, true),
        Field::new("quote_amount", DataType::Float64, true),
        Field::new("price_quote_per_chog", DataType::Float64, true),
        Field::new("signed_chog_flow", DataType::Float64, true),
        Field::new("log_chog_amount", DataType::Float64, true),
        Field::new("log_quote_amount", DataType::Float64, true),
        Field::new("price_log_return_1", DataType::Float64, true),
        Field::new("seconds_since_prev_swap", DataType::UInt64, true),
        Field::new("blocks_since_prev_swap", DataType::UInt64, true),
        Field::new("rolling_5_buy_ratio", DataType::Float64, true),
        Field::new("rolling_5_net_flow_chog", DataType::Float64, true),
        Field::new("rolling_5_chog_volume", DataType::Float64, true),
        Field::new("rolling_5_realized_volatility", DataType::Float64, true),
        Field::new("rolling_20_buy_ratio", DataType::Float64, true),
        Field::new("rolling_20_net_flow_chog", DataType::Float64, true),
        Field::new("rolling_20_chog_volume", DataType::Float64, true),
        Field::new("rolling_20_realized_volatility", DataType::Float64, true),
        Field::new("next_price_quote_per_chog", DataType::Float64, true),
        Field::new("target_next_swap_log_return", DataType::Float64, true),
        Field::new("delta_sign_valid", DataType::Boolean, false),
        Field::new("direction_sign_consistent", DataType::Boolean, false),
        Field::new("amount_price_consistency_bps", DataType::Float64, true),
        Field::new("v3_terminal_price_quote_per_chog", DataType::Float64, true),
        Field::new("execution_vs_terminal_price_bps", DataType::Float64, true),
        Field::new("liquidity_log", DataType::Float64, true),
        Field::new("tick", DataType::Int64, true),
        Field::new("tick_move_from_prev", DataType::Int64, true),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn factor_rows_to_batch(schema: SchemaRef, rows: &[FactorRow]) -> Result<RecordBatch> {
    Ok(RecordBatch::try_new(
        schema,
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.fetched_at_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.block_timestamp)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.block_datetime_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_index)
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.log_index).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.dex_id.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.family.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.token0_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.token1_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.token0_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.token1_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.token0_decimals)
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.token1_decimals)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quote_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quote_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.direction.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.chog_amount).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.quote_amount).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_quote_per_chog)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.signed_chog_flow)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.log_chog_amount)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.log_quote_amount)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_log_return_1)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.seconds_since_prev_swap)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.blocks_since_prev_swap)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_5_buy_ratio)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_5_net_flow_chog)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_5_chog_volume)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_5_realized_volatility)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_20_buy_ratio)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_20_net_flow_chog)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_20_chog_volume)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.rolling_20_realized_volatility)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.next_price_quote_per_chog)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.target_next_swap_log_return)
                    .collect::<Vec<_>>(),
            ),
            bool_array(
                &rows
                    .iter()
                    .map(|row| row.delta_sign_valid)
                    .collect::<Vec<_>>(),
            ),
            bool_array(
                &rows
                    .iter()
                    .map(|row| row.direction_sign_consistent)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.amount_price_consistency_bps)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.v3_terminal_price_quote_per_chog)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.execution_vs_terminal_price_bps)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.liquidity_log).collect::<Vec<_>>()),
            opt_i64_array(&rows.iter().map(|row| row.tick).collect::<Vec<_>>()),
            opt_i64_array(
                &rows
                    .iter()
                    .map(|row| row.tick_move_from_prev)
                    .collect::<Vec<_>>(),
            ),
            string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
        ],
    )?)
}

fn rolling_stats(
    pool_rows: &[&RawSwap],
    one_step_returns: &[Option<f64>],
    index: usize,
    window: usize,
) -> RollingStats {
    if index == 0 {
        return RollingStats::default();
    }
    let start = index.saturating_sub(window);
    let history = &pool_rows[start..index];
    let mut buys = 0usize;
    let mut net_flow = 0.0;
    let mut volume = 0.0;
    let mut observations = 0usize;
    for row in history {
        let Some(chog) = parse_f64(&row.chog_abs) else {
            continue;
        };
        observations += 1;
        volume += chog;
        if row.direction == "buy_chog" {
            buys += 1;
            net_flow += chog;
        } else if row.direction == "sell_chog" {
            net_flow -= chog;
        }
    }
    let returns = one_step_returns[start..index]
        .iter()
        .filter_map(|value| *value)
        .collect::<Vec<_>>();
    RollingStats {
        buy_ratio: (observations > 0).then_some(buys as f64 / observations as f64),
        net_flow_chog: (observations > 0).then_some(net_flow),
        chog_volume: (observations > 0).then_some(volume),
        realized_volatility: stddev(&returns),
    }
}

fn planned_parts(data_root: &Path, rows: &[FactorRow]) -> Vec<DexFactorPartSummary> {
    planned_parts_from_rows(rows)
        .into_iter()
        .map(|(dt, rows)| DexFactorPartSummary {
            path: factor_part_path_for_window(
                data_root,
                &dt,
                rows.min_block.unwrap_or(0),
                rows.max_block.unwrap_or(0),
            ),
            dt,
            rows: rows.rows,
        })
        .collect()
}

#[derive(Default)]
struct PlannedPart {
    rows: usize,
    min_block: Option<u64>,
    max_block: Option<u64>,
}

fn planned_parts_from_rows(rows: &[FactorRow]) -> BTreeMap<String, PlannedPart> {
    let mut by_dt = BTreeMap::<String, PlannedPart>::new();
    for row in rows {
        let part = by_dt.entry(row.dt.clone()).or_default();
        part.rows += 1;
        part.min_block = Some(
            part.min_block
                .map_or(row.block_number, |value| value.min(row.block_number)),
        );
        part.max_block = Some(
            part.max_block
                .map_or(row.block_number, |value| value.max(row.block_number)),
        );
    }
    by_dt
}

fn rows_by_dt(rows: Vec<FactorRow>) -> BTreeMap<String, Vec<FactorRow>> {
    let mut by_dt = BTreeMap::<String, Vec<FactorRow>>::new();
    for row in rows {
        by_dt.entry(row.dt.clone()).or_default().push(row);
    }
    by_dt
}

fn factor_part_path(data_root: &Path, rows: &[FactorRow], dt: &str) -> PathBuf {
    let min_block = rows.iter().map(|row| row.block_number).min().unwrap_or(0);
    let max_block = rows.iter().map(|row| row.block_number).max().unwrap_or(0);
    factor_part_path_for_window(data_root, dt, min_block, max_block)
}

fn factor_part_path_for_window(
    data_root: &Path,
    dt: &str,
    min_block: u64,
    max_block: u64,
) -> PathBuf {
    derived_part_path(
        data_root,
        DEX_SWAP_FACTORS_DATASET,
        dt,
        &format!("dex_rebuild_factors_{min_block}_{max_block}"),
    )
}

fn direction_sign_consistent(row: &RawSwap, delta0: Option<i128>, delta1: Option<i128>) -> bool {
    let chog = CHOG_TOKEN.to_ascii_lowercase();
    let chog_delta = if row.token0_address == chog {
        delta0
    } else if row.token1_address == chog {
        delta1
    } else {
        None
    };
    matches!(
        (row.direction.as_str(), chog_delta),
        ("buy_chog", Some(delta)) if delta < 0
    ) || matches!(
        (row.direction.as_str(), chog_delta),
        ("sell_chog", Some(delta)) if delta > 0
    )
}

fn amount_price_consistency_bps(
    quote_amount: Option<f64>,
    chog_amount: Option<f64>,
    price: Option<f64>,
) -> Option<f64> {
    let implied = quote_amount? / chog_amount?;
    let price = price?;
    if !implied.is_finite() || !price.is_finite() || price == 0.0 {
        return None;
    }
    Some(((implied / price) - 1.0) * 10_000.0)
}

fn v3_terminal_price_quote_per_chog(row: &RawSwap) -> Option<f64> {
    let sqrt = row.sqrt_price_x96.as_deref().and_then(parse_f64)?;
    if sqrt <= 0.0 {
        return None;
    }
    let raw_ratio_token1_per_token0 = (sqrt / Q96).powi(2);
    let human_ratio_token1_per_token0 = raw_ratio_token1_per_token0
        * 10f64.powi(row.token0_decimals as i32 - row.token1_decimals as i32);
    let chog = CHOG_TOKEN.to_ascii_lowercase();
    if row.token0_address == chog {
        Some(human_ratio_token1_per_token0)
    } else if row.token1_address == chog && human_ratio_token1_per_token0 > 0.0 {
        Some(1.0 / human_ratio_token1_per_token0)
    } else {
        None
    }
}

fn bps_difference(execution_price: Option<f64>, terminal_price: Option<f64>) -> Option<f64> {
    let execution = execution_price?;
    let terminal = terminal_price?;
    if execution <= 0.0 || terminal <= 0.0 {
        return None;
    }
    Some(((execution / terminal) - 1.0) * 10_000.0)
}

fn log_return(current: Option<f64>, previous: Option<f64>) -> Option<f64> {
    let current = current?;
    let previous = previous?;
    if current > 0.0 && previous > 0.0 {
        Some((current / previous).ln())
    } else {
        None
    }
}

fn factor_value(factor: &str, row: &FactorRow) -> Option<f64> {
    match factor {
        "price_log_return_1" => row.price_log_return_1,
        "log_chog_amount" => row.log_chog_amount,
        "log_quote_amount" => row.log_quote_amount,
        "signed_chog_flow" => row.signed_chog_flow,
        "rolling_5_buy_ratio" => row.rolling_5_buy_ratio,
        "rolling_5_net_flow_chog" => row.rolling_5_net_flow_chog,
        "rolling_5_chog_volume" => row.rolling_5_chog_volume,
        "rolling_5_realized_volatility" => row.rolling_5_realized_volatility,
        "rolling_20_buy_ratio" => row.rolling_20_buy_ratio,
        "rolling_20_net_flow_chog" => row.rolling_20_net_flow_chog,
        "rolling_20_chog_volume" => row.rolling_20_chog_volume,
        "rolling_20_realized_volatility" => row.rolling_20_realized_volatility,
        "execution_vs_terminal_price_bps" => row.execution_vs_terminal_price_bps,
        "liquidity_log" => row.liquidity_log,
        "tick_move_from_prev" => row.tick_move_from_prev.map(|value| value as f64),
        _ => None,
    }
}

fn correlation(pairs: &[(f64, f64)]) -> Option<f64> {
    if pairs.len() < 2 {
        return None;
    }
    let mean_x = pairs.iter().map(|(x, _)| *x).sum::<f64>() / pairs.len() as f64;
    let mean_y = pairs.iter().map(|(_, y)| *y).sum::<f64>() / pairs.len() as f64;
    let mut numerator = 0.0;
    let mut x_var = 0.0;
    let mut y_var = 0.0;
    for (x, y) in pairs {
        let dx = x - mean_x;
        let dy = y - mean_y;
        numerator += dx * dy;
        x_var += dx * dx;
        y_var += dy * dy;
    }
    if x_var == 0.0 || y_var == 0.0 {
        None
    } else {
        Some(numerator / (x_var.sqrt() * y_var.sqrt()))
    }
}

fn rank_correlation(pairs: &[(f64, f64)]) -> Option<f64> {
    if pairs.len() < 2 {
        return None;
    }
    let x_ranks = ranks(&pairs.iter().map(|(x, _)| *x).collect::<Vec<_>>());
    let y_ranks = ranks(&pairs.iter().map(|(_, y)| *y).collect::<Vec<_>>());
    correlation(
        &x_ranks
            .into_iter()
            .zip(y_ranks)
            .collect::<Vec<(f64, f64)>>(),
    )
}

fn ranks(values: &[f64]) -> Vec<f64> {
    let mut indexed = values
        .iter()
        .enumerate()
        .map(|(index, value)| (index, *value))
        .collect::<Vec<_>>();
    indexed.sort_by(|a, b| a.1.total_cmp(&b.1));
    let mut ranks = vec![0.0; values.len()];
    let mut index = 0;
    while index < indexed.len() {
        let start = index;
        let value = indexed[index].1;
        while index < indexed.len() && indexed[index].1 == value {
            index += 1;
        }
        let rank = (start + 1 + index) as f64 / 2.0;
        for (original_index, _) in &indexed[start..index] {
            ranks[*original_index] = rank;
        }
    }
    ranks
}

fn mean_targets(pairs: &[(f64, f64)]) -> Option<f64> {
    if pairs.is_empty() {
        None
    } else {
        Some(pairs.iter().map(|(_, target)| *target).sum::<f64>() / pairs.len() as f64)
    }
}

fn stddev(values: &[f64]) -> Option<f64> {
    if values.len() < 2 {
        return None;
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    let variance = values
        .iter()
        .map(|value| {
            let diff = value - mean;
            diff * diff
        })
        .sum::<f64>()
        / values.len() as f64;
    Some(variance.sqrt())
}

fn update_max_abs(current: &mut Option<f64>, candidate: f64) {
    if current.is_none_or(|value| candidate.abs() > value.abs()) {
        *current = Some(candidate);
    }
}

fn abs_option(value: Option<f64>) -> f64 {
    value.map(f64::abs).unwrap_or(0.0)
}

fn event_order(a: &RawSwap, b: &RawSwap) -> std::cmp::Ordering {
    a.pool_address
        .cmp(&b.pool_address)
        .then_with(|| a.block_number.cmp(&b.block_number))
        .then_with(|| a.transaction_index.cmp(&b.transaction_index))
        .then_with(|| a.log_index.cmp(&b.log_index))
}

fn factor_event_order(a: &FactorRow, b: &FactorRow) -> std::cmp::Ordering {
    a.block_number
        .cmp(&b.block_number)
        .then_with(|| a.transaction_index.cmp(&b.transaction_index))
        .then_with(|| a.log_index.cmp(&b.log_index))
        .then_with(|| a.pool_address.cmp(&b.pool_address))
}

fn parse_f64(value: &str) -> Option<f64> {
    if value.is_empty() {
        None
    } else {
        value.parse::<f64>().ok()
    }
}

fn parse_i128(value: &str) -> Option<i128> {
    if value.is_empty() {
        None
    } else {
        value.parse::<i128>().ok()
    }
}

fn parse_i64(value: &str) -> Option<i64> {
    if value.is_empty() {
        None
    } else {
        value.parse::<i64>().ok()
    }
}

fn optional_string(values: Option<&StringArray>, index: usize) -> Option<String> {
    let values = values?;
    if values.is_null(index) {
        None
    } else {
        Some(values.value(index).to_string())
    }
}

fn string_value(values: &StringArray, index: usize) -> String {
    if values.is_null(index) {
        String::new()
    } else {
        values.value(index).to_string()
    }
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

fn optional_string_column<'a>(
    batch: &'a RecordBatch,
    name: &str,
) -> Result<Option<&'a StringArray>> {
    let Ok(index) = batch.schema().index_of(name) else {
        return Ok(None);
    };
    Ok(Some(
        batch
            .column(index)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| anyhow!("column {name} is not utf8"))?,
    ))
}

fn uint64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a UInt64Array> {
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

#[cfg(test)]
mod tests {
    use super::*;

    fn raw_swap(pool: &str, block: u64, log: u64, price: &str, direction: &str) -> RawSwap {
        RawSwap {
            fetched_at_utc: "2026-05-07T00:00:00Z".to_string(),
            block_number: block,
            block_timestamp: 1_778_112_000 + block,
            block_datetime_utc: "2026-05-07T00:00:00Z".to_string(),
            transaction_hash: format!("0x{block:x}{log:x}"),
            transaction_index: 0,
            log_index: log,
            pool_address: pool.to_string(),
            dex_id: "test".to_string(),
            family: "v3".to_string(),
            token0_address: CHOG_TOKEN.to_string(),
            token1_address: "0xquote".to_string(),
            token0_symbol: "CHOG".to_string(),
            token1_symbol: "MON".to_string(),
            token0_decimals: 18,
            token1_decimals: 18,
            quote_address: "0xquote".to_string(),
            quote_symbol: "MON".to_string(),
            amount0_delta_raw: if direction == "buy_chog" {
                "-10".to_string()
            } else {
                "10".to_string()
            },
            amount1_delta_raw: if direction == "buy_chog" {
                "1".to_string()
            } else {
                "-1".to_string()
            },
            direction: direction.to_string(),
            chog_abs: "10".to_string(),
            quote_abs: "1".to_string(),
            price_quote_per_chog: price.to_string(),
            sqrt_price_x96: None,
            liquidity_raw: Some("1000".to_string()),
            tick: Some("1".to_string()),
            removed: false,
            dt: "2026-05-07".to_string(),
        }
    }

    #[test]
    fn labels_next_swap_return_within_pool_only() {
        let rows = vec![
            raw_swap("0xa", 1, 0, "1.0", "buy_chog"),
            raw_swap("0xb", 2, 0, "100.0", "buy_chog"),
            raw_swap("0xa", 3, 0, "1.1", "sell_chog"),
        ];
        let factors = build_factor_rows(&rows);
        let first_a = factors
            .iter()
            .find(|row| row.pool_address == "0xa" && row.block_number == 1)
            .unwrap();
        assert!((first_a.target_next_swap_log_return.unwrap() - 1.1f64.ln()).abs() < 1e-12);
        let only_b = factors
            .iter()
            .find(|row| row.pool_address == "0xb")
            .unwrap();
        assert!(only_b.target_next_swap_log_return.is_none());
    }

    #[test]
    fn rolling_window_uses_only_prior_rows() {
        let rows = vec![
            raw_swap("0xa", 1, 0, "1.0", "buy_chog"),
            raw_swap("0xa", 2, 0, "2.0", "sell_chog"),
            raw_swap("0xa", 3, 0, "4.0", "buy_chog"),
        ];
        let factors = build_factor_rows(&rows);
        let third = factors.iter().find(|row| row.block_number == 3).unwrap();
        assert_eq!(third.rolling_5_buy_ratio, Some(0.5));
        assert_eq!(third.rolling_5_net_flow_chog, Some(0.0));
        assert_eq!(third.rolling_5_chog_volume, Some(20.0));
    }

    #[test]
    fn direction_sign_invariant_matches_chog_delta() {
        let row = raw_swap("0xa", 1, 0, "1.0", "buy_chog");
        assert!(direction_sign_consistent(&row, Some(-10), Some(1)));
        assert!(!direction_sign_consistent(&row, Some(10), Some(-1)));
    }
}

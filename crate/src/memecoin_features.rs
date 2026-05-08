use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow};
use arrow::array::{Array, BooleanArray, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

use crate::chog_v1::{
    RAW_DIR, dt_from_utc_string, f64_array, opt_f64_array, opt_u64_array, parquet_files_under,
    string_array, u64_array, write_parquet_part, write_schema_metadata,
};
use crate::dex::DEX_SWAP_DATASET;
use crate::dex_hourly::derived_part_path;

pub const MEMECOIN_EVENT_FEATURES_DATASET: &str = "memecoin_event_features";
pub const MEMECOIN_HOURLY_FEATURES_DATASET: &str = "memecoin_hourly_features";

const RECEIPT_DATASET: &str = "tx_receipts";
const EVENT_HEADER_DATASET: &str = "event_block_headers";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MemecoinFeaturePartSummary {
    pub dataset: &'static str,
    pub dt: String,
    pub rows: usize,
    pub path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct MemecoinFeatureRebuildSummary {
    pub input_root: PathBuf,
    pub min_block: Option<u64>,
    pub max_block: Option<u64>,
    pub event_rows: u64,
    pub hourly_rows: u64,
    pub parquet_parts: u64,
    pub parts: Vec<MemecoinFeaturePartSummary>,
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
    quote_address: String,
    quote_symbol: String,
    direction: String,
    chog_amount: Option<f64>,
    quote_amount: Option<f64>,
    price_quote_per_chog: Option<f64>,
    dt: String,
}

#[derive(Debug, Clone, Default)]
struct ReceiptInfo {
    receipt_status: Option<u64>,
    gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
}

#[derive(Debug, Clone, Default)]
struct HeaderInfo {
    base_fee_per_gas: Option<u64>,
}

#[derive(Debug, Clone)]
struct EventFeatureRow {
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
    quote_address: String,
    quote_symbol: String,
    direction: String,
    chog_amount: Option<f64>,
    quote_amount: Option<f64>,
    price_quote_per_chog: Option<f64>,
    signed_chog_flow: Option<f64>,
    receipt_status: Option<u64>,
    gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
    base_fee_per_gas: Option<u64>,
    priority_fee_per_gas_proxy: Option<u64>,
    same_block_pool_event_count: u64,
    dt: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct HourKey {
    hour_utc: String,
    pool_address: String,
    dex_id: String,
    family: String,
    quote_symbol: String,
    quote_address: String,
}

#[derive(Default)]
struct HourAgg {
    events: u64,
    txs: BTreeSet<String>,
    blocks: BTreeSet<u64>,
    buy_events: u64,
    sell_events: u64,
    buy_chog: f64,
    sell_chog: f64,
    chog_volume: f64,
    quote_volume: f64,
    gas_used: Vec<u64>,
    effective_gas_price: Vec<u64>,
    priority_fee_per_gas_proxy: Vec<u64>,
    receipt_success: u64,
    receipt_known: u64,
}

#[derive(Debug, Clone)]
struct HourFeatureRow {
    hour_utc: String,
    pool_address: String,
    dex_id: String,
    family: String,
    quote_symbol: String,
    quote_address: String,
    events: u64,
    unique_txs: u64,
    buy_events: u64,
    sell_events: u64,
    buy_chog: f64,
    sell_chog: f64,
    net_buy_chog: f64,
    chog_volume: f64,
    quote_volume: f64,
    avg_price_quote_per_chog: Option<f64>,
    gas_used_mean: Option<f64>,
    gas_used_median: Option<f64>,
    effective_gas_price_mean: Option<f64>,
    effective_gas_price_median: Option<f64>,
    priority_fee_per_gas_proxy_mean: Option<f64>,
    priority_fee_per_gas_proxy_median: Option<f64>,
    active_blocks: u64,
    receipt_success_rate: Option<f64>,
    dt: String,
}

pub fn rebuild_memecoin_features(
    data_root: &Path,
    dry_run: bool,
) -> Result<MemecoinFeatureRebuildSummary> {
    let input_root = data_root.join(RAW_DIR).join(DEX_SWAP_DATASET);
    let mut swaps = Vec::new();
    for path in parquet_files_under(&input_root)? {
        read_swap_file(&path, &mut swaps)?;
    }
    swaps.sort_by(event_order);

    let receipts = read_receipts(data_root)?;
    let headers = read_event_headers(data_root)?;
    let event_rows = build_event_rows(&swaps, &receipts, &headers);
    let hour_rows = build_hour_rows(&event_rows);
    let min_block = event_rows.iter().map(|row| row.block_number).min();
    let max_block = event_rows.iter().map(|row| row.block_number).max();
    let parts = planned_parts(data_root, &event_rows, &hour_rows);

    if dry_run {
        return Ok(MemecoinFeatureRebuildSummary {
            input_root,
            min_block,
            max_block,
            event_rows: event_rows.len() as u64,
            hourly_rows: hour_rows.len() as u64,
            parquet_parts: parts.len() as u64,
            parts,
            dry_run,
        });
    }

    let event_schema = event_schema();
    let hour_schema = hourly_schema();
    write_schema_metadata(
        data_root,
        MEMECOIN_EVENT_FEATURES_DATASET,
        event_schema.as_ref(),
        &["dt"],
    )?;
    write_schema_metadata(
        data_root,
        MEMECOIN_HOURLY_FEATURES_DATASET,
        hour_schema.as_ref(),
        &["dt"],
    )?;

    let mut written_parts = Vec::new();
    for (dt, rows) in event_rows_by_dt(event_rows) {
        let batch = event_rows_to_batch(event_schema.clone(), &rows)?;
        let path = memecoin_part_path(
            data_root,
            MEMECOIN_EVENT_FEATURES_DATASET,
            &dt,
            rows.iter()
                .map(|row| row.block_number)
                .min()
                .unwrap_or_default(),
            rows.iter()
                .map(|row| row.block_number)
                .max()
                .unwrap_or_default(),
        );
        let write = write_parquet_part(&path, event_schema.clone(), batch)?;
        written_parts.push(MemecoinFeaturePartSummary {
            dataset: MEMECOIN_EVENT_FEATURES_DATASET,
            dt,
            rows: write.rows,
            path: write.path,
        });
    }
    for (dt, rows) in hour_rows_by_dt(hour_rows) {
        let batch = hour_rows_to_batch(hour_schema.clone(), &rows)?;
        let stem = format!(
            "memecoin_hourly_features_{}_{}",
            min_block.unwrap_or_default(),
            max_block.unwrap_or_default()
        );
        let path = derived_part_path(data_root, MEMECOIN_HOURLY_FEATURES_DATASET, &dt, &stem);
        let write = write_parquet_part(&path, hour_schema.clone(), batch)?;
        written_parts.push(MemecoinFeaturePartSummary {
            dataset: MEMECOIN_HOURLY_FEATURES_DATASET,
            dt,
            rows: write.rows,
            path: write.path,
        });
    }

    let event_rows = written_parts
        .iter()
        .filter(|part| part.dataset == MEMECOIN_EVENT_FEATURES_DATASET)
        .map(|part| part.rows as u64)
        .sum::<u64>();
    let hourly_rows = written_parts
        .iter()
        .filter(|part| part.dataset == MEMECOIN_HOURLY_FEATURES_DATASET)
        .map(|part| part.rows as u64)
        .sum::<u64>();
    Ok(MemecoinFeatureRebuildSummary {
        input_root,
        min_block,
        max_block,
        event_rows,
        hourly_rows,
        parquet_parts: written_parts.len() as u64,
        parts: written_parts,
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
        let quote_address = string_column(&batch, "quote_address")?;
        let quote_symbol = string_column(&batch, "quote_symbol")?;
        let direction = string_column(&batch, "direction")?;
        let chog_abs = string_column(&batch, "chog_abs")?;
        let quote_abs = string_column(&batch, "quote_abs")?;
        let price_quote_per_chog = string_column(&batch, "price_quote_per_chog")?;
        let removed = bool_column(&batch, "removed")?;
        let dt = string_column(&batch, "dt")?;
        for index in 0..batch.num_rows() {
            if !removed.is_null(index) && removed.value(index) {
                continue;
            }
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
                quote_address: string_value(quote_address, index).to_ascii_lowercase(),
                quote_symbol: string_value(quote_symbol, index),
                direction: string_value(direction, index),
                chog_amount: parse_f64(chog_abs, index)?,
                quote_amount: parse_f64(quote_abs, index)?,
                price_quote_per_chog: parse_f64(price_quote_per_chog, index)?,
                dt: string_value(dt, index),
            });
        }
    }
    Ok(())
}

fn read_receipts(data_root: &Path) -> Result<BTreeMap<String, ReceiptInfo>> {
    let root = data_root.join(RAW_DIR).join(RECEIPT_DATASET);
    let mut receipts = BTreeMap::new();
    for path in parquet_files_under(&root)? {
        read_receipt_file(&path, &mut receipts)?;
    }
    Ok(receipts)
}

fn read_receipt_file(path: &Path, receipts: &mut BTreeMap<String, ReceiptInfo>) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(4096)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        let receipt_status = uint64_column(&batch, "receipt_status")?;
        let gas_used = uint64_column(&batch, "gas_used")?;
        let effective_gas_price = uint64_column(&batch, "effective_gas_price")?;
        for index in 0..batch.num_rows() {
            if transaction_hash.is_null(index) || transaction_hash.value(index).is_empty() {
                continue;
            }
            receipts.insert(
                transaction_hash.value(index).to_string(),
                ReceiptInfo {
                    receipt_status: optional_u64(receipt_status, index),
                    gas_used: optional_u64(gas_used, index),
                    effective_gas_price: optional_u64(effective_gas_price, index),
                },
            );
        }
    }
    Ok(())
}

fn read_event_headers(data_root: &Path) -> Result<BTreeMap<u64, HeaderInfo>> {
    let root = data_root.join(RAW_DIR).join(EVENT_HEADER_DATASET);
    let mut headers = BTreeMap::new();
    for path in parquet_files_under(&root)? {
        read_event_header_file(&path, &mut headers)?;
    }
    Ok(headers)
}

fn read_event_header_file(path: &Path, headers: &mut BTreeMap<u64, HeaderInfo>) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(4096)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let block_number = uint64_column(&batch, "block_number")?;
        let base_fee_per_gas = uint64_column(&batch, "base_fee_per_gas")?;
        for index in 0..batch.num_rows() {
            if block_number.is_null(index) {
                continue;
            }
            headers.insert(
                block_number.value(index),
                HeaderInfo {
                    base_fee_per_gas: optional_u64(base_fee_per_gas, index),
                },
            );
        }
    }
    Ok(())
}

fn build_event_rows(
    swaps: &[RawSwap],
    receipts: &BTreeMap<String, ReceiptInfo>,
    headers: &BTreeMap<u64, HeaderInfo>,
) -> Vec<EventFeatureRow> {
    let mut same_block_pool_counts = BTreeMap::<(u64, String), u64>::new();
    for swap in swaps {
        *same_block_pool_counts
            .entry((swap.block_number, swap.pool_address.clone()))
            .or_default() += 1;
    }

    swaps
        .iter()
        .map(|swap| {
            let receipt = receipts
                .get(&swap.transaction_hash)
                .cloned()
                .unwrap_or_default();
            let header = headers.get(&swap.block_number).cloned().unwrap_or_default();
            let priority_fee_per_gas_proxy =
                match (receipt.effective_gas_price, header.base_fee_per_gas) {
                    (Some(effective), Some(base)) if effective >= base => Some(effective - base),
                    _ => None,
                };
            EventFeatureRow {
                fetched_at_utc: swap.fetched_at_utc.clone(),
                block_number: swap.block_number,
                block_timestamp: swap.block_timestamp,
                block_datetime_utc: swap.block_datetime_utc.clone(),
                transaction_hash: swap.transaction_hash.clone(),
                transaction_index: swap.transaction_index,
                log_index: swap.log_index,
                pool_address: swap.pool_address.clone(),
                dex_id: swap.dex_id.clone(),
                family: swap.family.clone(),
                quote_address: swap.quote_address.clone(),
                quote_symbol: swap.quote_symbol.clone(),
                direction: swap.direction.clone(),
                chog_amount: swap.chog_amount,
                quote_amount: swap.quote_amount,
                price_quote_per_chog: swap.price_quote_per_chog,
                signed_chog_flow: signed_chog_flow(swap.direction.as_str(), swap.chog_amount),
                receipt_status: receipt.receipt_status,
                gas_used: receipt.gas_used,
                effective_gas_price: receipt.effective_gas_price,
                base_fee_per_gas: header.base_fee_per_gas,
                priority_fee_per_gas_proxy,
                same_block_pool_event_count: same_block_pool_counts
                    .get(&(swap.block_number, swap.pool_address.clone()))
                    .copied()
                    .unwrap_or(1),
                dt: swap.dt.clone(),
            }
        })
        .collect()
}

fn build_hour_rows(rows: &[EventFeatureRow]) -> Vec<HourFeatureRow> {
    let mut aggs = BTreeMap::<HourKey, HourAgg>::new();
    for row in rows {
        let key = HourKey {
            hour_utc: hour_from_utc(&row.block_datetime_utc),
            pool_address: row.pool_address.clone(),
            dex_id: row.dex_id.clone(),
            family: row.family.clone(),
            quote_symbol: row.quote_symbol.clone(),
            quote_address: row.quote_address.clone(),
        };
        let agg = aggs.entry(key).or_default();
        agg.events += 1;
        agg.txs.insert(row.transaction_hash.clone());
        agg.blocks.insert(row.block_number);
        if let Some(chog) = row.chog_amount {
            agg.chog_volume += chog;
            match row.direction.as_str() {
                "buy_chog" => {
                    agg.buy_events += 1;
                    agg.buy_chog += chog;
                }
                "sell_chog" => {
                    agg.sell_events += 1;
                    agg.sell_chog += chog;
                }
                _ => {}
            }
        }
        if let Some(quote) = row.quote_amount {
            agg.quote_volume += quote;
        }
        if let Some(value) = row.gas_used {
            agg.gas_used.push(value);
        }
        if let Some(value) = row.effective_gas_price {
            agg.effective_gas_price.push(value);
        }
        if let Some(value) = row.priority_fee_per_gas_proxy {
            agg.priority_fee_per_gas_proxy.push(value);
        }
        if let Some(status) = row.receipt_status {
            agg.receipt_known += 1;
            if status == 1 {
                agg.receipt_success += 1;
            }
        }
    }

    aggs.into_iter()
        .map(|(key, agg)| HourFeatureRow {
            dt: dt_from_utc_string(&key.hour_utc),
            hour_utc: key.hour_utc,
            pool_address: key.pool_address,
            dex_id: key.dex_id,
            family: key.family,
            quote_symbol: key.quote_symbol,
            quote_address: key.quote_address,
            events: agg.events,
            unique_txs: agg.txs.len() as u64,
            buy_events: agg.buy_events,
            sell_events: agg.sell_events,
            buy_chog: clean_zero(agg.buy_chog),
            sell_chog: clean_zero(agg.sell_chog),
            net_buy_chog: clean_zero(agg.buy_chog - agg.sell_chog),
            chog_volume: clean_zero(agg.chog_volume),
            quote_volume: clean_zero(agg.quote_volume),
            avg_price_quote_per_chog: (agg.chog_volume > 0.0)
                .then_some(agg.quote_volume / agg.chog_volume),
            gas_used_mean: mean_u64(&agg.gas_used),
            gas_used_median: median_u64(agg.gas_used),
            effective_gas_price_mean: mean_u64(&agg.effective_gas_price),
            effective_gas_price_median: median_u64(agg.effective_gas_price),
            priority_fee_per_gas_proxy_mean: mean_u64(&agg.priority_fee_per_gas_proxy),
            priority_fee_per_gas_proxy_median: median_u64(agg.priority_fee_per_gas_proxy),
            active_blocks: agg.blocks.len() as u64,
            receipt_success_rate: (agg.receipt_known > 0)
                .then_some(agg.receipt_success as f64 / agg.receipt_known as f64),
        })
        .collect()
}

fn event_schema() -> SchemaRef {
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
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("chog_amount", DataType::Float64, true),
        Field::new("quote_amount", DataType::Float64, true),
        Field::new("price_quote_per_chog", DataType::Float64, true),
        Field::new("signed_chog_flow", DataType::Float64, true),
        Field::new("receipt_status", DataType::UInt64, true),
        Field::new("gas_used", DataType::UInt64, true),
        Field::new("effective_gas_price", DataType::UInt64, true),
        Field::new("base_fee_per_gas", DataType::UInt64, true),
        Field::new("priority_fee_per_gas_proxy", DataType::UInt64, true),
        Field::new("same_block_pool_event_count", DataType::UInt64, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn hourly_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("hour_utc", DataType::Utf8, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("events", DataType::UInt64, false),
        Field::new("unique_txs", DataType::UInt64, false),
        Field::new("buy_events", DataType::UInt64, false),
        Field::new("sell_events", DataType::UInt64, false),
        Field::new("buy_chog", DataType::Float64, false),
        Field::new("sell_chog", DataType::Float64, false),
        Field::new("net_buy_chog", DataType::Float64, false),
        Field::new("chog_volume", DataType::Float64, false),
        Field::new("quote_volume", DataType::Float64, false),
        Field::new("avg_price_quote_per_chog", DataType::Float64, true),
        Field::new("gas_used_mean", DataType::Float64, true),
        Field::new("gas_used_median", DataType::Float64, true),
        Field::new("effective_gas_price_mean", DataType::Float64, true),
        Field::new("effective_gas_price_median", DataType::Float64, true),
        Field::new("priority_fee_per_gas_proxy_mean", DataType::Float64, true),
        Field::new("priority_fee_per_gas_proxy_median", DataType::Float64, true),
        Field::new("active_blocks", DataType::UInt64, false),
        Field::new("receipt_success_rate", DataType::Float64, true),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn event_rows_to_batch(schema: SchemaRef, rows: &[EventFeatureRow]) -> Result<RecordBatch> {
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
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_status)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(&rows.iter().map(|row| row.gas_used).collect::<Vec<_>>()),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.effective_gas_price)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.base_fee_per_gas)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.priority_fee_per_gas_proxy)
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.same_block_pool_event_count)
                    .collect::<Vec<_>>(),
            ),
            string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
        ],
    )?)
}

fn hour_rows_to_batch(schema: SchemaRef, rows: &[HourFeatureRow]) -> Result<RecordBatch> {
    Ok(RecordBatch::try_new(
        schema,
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.hour_utc.clone())
                    .collect::<Vec<_>>(),
            ),
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
                    .map(|row| row.quote_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quote_address.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.events).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.unique_txs).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.buy_events).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.sell_events).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.buy_chog).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.sell_chog).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.net_buy_chog).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.chog_volume).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.quote_volume).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.avg_price_quote_per_chog)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.gas_used_mean).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.gas_used_median)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.effective_gas_price_mean)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.effective_gas_price_median)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.priority_fee_per_gas_proxy_mean)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.priority_fee_per_gas_proxy_median)
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.active_blocks).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_success_rate)
                    .collect::<Vec<_>>(),
            ),
            string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
        ],
    )?)
}

fn planned_parts(
    data_root: &Path,
    event_rows: &[EventFeatureRow],
    hour_rows: &[HourFeatureRow],
) -> Vec<MemecoinFeaturePartSummary> {
    let mut parts = Vec::new();
    for (dt, rows) in event_rows_by_dt_ref(event_rows) {
        let min_block = rows
            .iter()
            .map(|row| row.block_number)
            .min()
            .unwrap_or_default();
        let max_block = rows
            .iter()
            .map(|row| row.block_number)
            .max()
            .unwrap_or_default();
        parts.push(MemecoinFeaturePartSummary {
            dataset: MEMECOIN_EVENT_FEATURES_DATASET,
            dt: dt.clone(),
            rows: rows.len(),
            path: memecoin_part_path(
                data_root,
                MEMECOIN_EVENT_FEATURES_DATASET,
                &dt,
                min_block,
                max_block,
            ),
        });
    }
    for (dt, rows) in hour_rows_by_dt_ref(hour_rows) {
        let min_block = event_rows
            .iter()
            .map(|row| row.block_number)
            .min()
            .unwrap_or_default();
        let max_block = event_rows
            .iter()
            .map(|row| row.block_number)
            .max()
            .unwrap_or_default();
        parts.push(MemecoinFeaturePartSummary {
            dataset: MEMECOIN_HOURLY_FEATURES_DATASET,
            dt: dt.clone(),
            rows: rows.len(),
            path: derived_part_path(
                data_root,
                MEMECOIN_HOURLY_FEATURES_DATASET,
                &dt,
                &format!("memecoin_hourly_features_{min_block}_{max_block}"),
            ),
        });
    }
    parts
}

fn memecoin_part_path(
    data_root: &Path,
    dataset: &str,
    dt: &str,
    min_block: u64,
    max_block: u64,
) -> PathBuf {
    derived_part_path(
        data_root,
        dataset,
        dt,
        &format!("memecoin_event_features_{min_block}_{max_block}"),
    )
}

fn event_rows_by_dt(rows: Vec<EventFeatureRow>) -> BTreeMap<String, Vec<EventFeatureRow>> {
    let mut by_dt = BTreeMap::new();
    for row in rows {
        by_dt
            .entry(row.dt.clone())
            .or_insert_with(Vec::new)
            .push(row);
    }
    by_dt
}

fn hour_rows_by_dt(rows: Vec<HourFeatureRow>) -> BTreeMap<String, Vec<HourFeatureRow>> {
    let mut by_dt = BTreeMap::new();
    for row in rows {
        by_dt
            .entry(row.dt.clone())
            .or_insert_with(Vec::new)
            .push(row);
    }
    by_dt
}

fn event_rows_by_dt_ref(rows: &[EventFeatureRow]) -> BTreeMap<String, Vec<&EventFeatureRow>> {
    let mut by_dt = BTreeMap::new();
    for row in rows {
        by_dt
            .entry(row.dt.clone())
            .or_insert_with(Vec::new)
            .push(row);
    }
    by_dt
}

fn hour_rows_by_dt_ref(rows: &[HourFeatureRow]) -> BTreeMap<String, Vec<&HourFeatureRow>> {
    let mut by_dt = BTreeMap::new();
    for row in rows {
        by_dt
            .entry(row.dt.clone())
            .or_insert_with(Vec::new)
            .push(row);
    }
    by_dt
}

fn event_order(a: &RawSwap, b: &RawSwap) -> std::cmp::Ordering {
    a.block_number
        .cmp(&b.block_number)
        .then_with(|| a.transaction_index.cmp(&b.transaction_index))
        .then_with(|| a.log_index.cmp(&b.log_index))
        .then_with(|| a.pool_address.cmp(&b.pool_address))
}

fn signed_chog_flow(direction: &str, amount: Option<f64>) -> Option<f64> {
    amount.map(|amount| match direction {
        "buy_chog" => amount,
        "sell_chog" => -amount,
        _ => 0.0,
    })
}

fn hour_from_utc(value: &str) -> String {
    if value.len() >= 13 {
        format!("{}:00:00Z", &value[..13])
    } else {
        String::new()
    }
}

fn mean_u64(values: &[u64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    Some(values.iter().map(|value| *value as f64).sum::<f64>() / values.len() as f64)
}

fn median_u64(mut values: Vec<u64>) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_unstable();
    let middle = values.len() / 2;
    if values.len() % 2 == 1 {
        Some(values[middle] as f64)
    } else {
        Some((values[middle - 1] as f64 + values[middle] as f64) / 2.0)
    }
}

fn clean_zero(value: f64) -> f64 {
    if value.abs() < f64::EPSILON {
        0.0
    } else {
        value
    }
}

fn parse_f64(values: &StringArray, index: usize) -> Result<Option<f64>> {
    if values.is_null(index) || values.value(index).is_empty() {
        return Ok(None);
    }
    values
        .value(index)
        .parse::<f64>()
        .map(Some)
        .with_context(|| format!("invalid numeric value {}", values.value(index)))
}

fn optional_u64(values: &UInt64Array, index: usize) -> Option<u64> {
    (!values.is_null(index)).then_some(values.value(index))
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

    #[test]
    fn builds_event_rows_with_gas_and_priority_fee_proxy() {
        let swaps = vec![RawSwap {
            fetched_at_utc: "2026-05-07T01:00:00Z".to_string(),
            block_number: 10,
            block_timestamp: 1_778_112_000,
            block_datetime_utc: "2026-05-07T01:00:00Z".to_string(),
            transaction_hash: "0xa".to_string(),
            transaction_index: 1,
            log_index: 2,
            pool_address: "0xpool".to_string(),
            dex_id: "dex".to_string(),
            family: "v2".to_string(),
            quote_address: "0xquote".to_string(),
            quote_symbol: "MON".to_string(),
            direction: "buy_chog".to_string(),
            chog_amount: Some(4.0),
            quote_amount: Some(0.2),
            price_quote_per_chog: Some(0.05),
            dt: "2026-05-07".to_string(),
        }];
        let receipts = BTreeMap::from([(
            "0xa".to_string(),
            ReceiptInfo {
                receipt_status: Some(1),
                gas_used: Some(21_000),
                effective_gas_price: Some(103),
            },
        )]);
        let headers = BTreeMap::from([(
            10,
            HeaderInfo {
                base_fee_per_gas: Some(100),
            },
        )]);
        let rows = build_event_rows(&swaps, &receipts, &headers);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].signed_chog_flow, Some(4.0));
        assert_eq!(rows[0].priority_fee_per_gas_proxy, Some(3));
        assert_eq!(rows[0].same_block_pool_event_count, 1);
    }

    #[test]
    fn hourly_rows_aggregate_flow_gas_and_receipt_success() {
        let rows = vec![
            EventFeatureRow {
                fetched_at_utc: String::new(),
                block_number: 10,
                block_timestamp: 1,
                block_datetime_utc: "2026-05-07T01:12:00Z".to_string(),
                transaction_hash: "0xa".to_string(),
                transaction_index: 0,
                log_index: 0,
                pool_address: "0xpool".to_string(),
                dex_id: "dex".to_string(),
                family: "v2".to_string(),
                quote_address: "0xquote".to_string(),
                quote_symbol: "MON".to_string(),
                direction: "buy_chog".to_string(),
                chog_amount: Some(4.0),
                quote_amount: Some(0.2),
                price_quote_per_chog: Some(0.05),
                signed_chog_flow: Some(4.0),
                receipt_status: Some(1),
                gas_used: Some(10),
                effective_gas_price: Some(100),
                base_fee_per_gas: Some(90),
                priority_fee_per_gas_proxy: Some(10),
                same_block_pool_event_count: 2,
                dt: "2026-05-07".to_string(),
            },
            EventFeatureRow {
                fetched_at_utc: String::new(),
                block_number: 11,
                block_timestamp: 2,
                block_datetime_utc: "2026-05-07T01:40:00Z".to_string(),
                transaction_hash: "0xb".to_string(),
                transaction_index: 0,
                log_index: 0,
                pool_address: "0xpool".to_string(),
                dex_id: "dex".to_string(),
                family: "v2".to_string(),
                quote_address: "0xquote".to_string(),
                quote_symbol: "MON".to_string(),
                direction: "sell_chog".to_string(),
                chog_amount: Some(1.0),
                quote_amount: Some(0.06),
                price_quote_per_chog: Some(0.06),
                signed_chog_flow: Some(-1.0),
                receipt_status: Some(0),
                gas_used: Some(20),
                effective_gas_price: Some(120),
                base_fee_per_gas: Some(90),
                priority_fee_per_gas_proxy: Some(30),
                same_block_pool_event_count: 1,
                dt: "2026-05-07".to_string(),
            },
        ];
        let hourly = build_hour_rows(&rows);
        assert_eq!(hourly.len(), 1);
        assert_eq!(hourly[0].unique_txs, 2);
        assert_eq!(hourly[0].active_blocks, 2);
        assert_eq!(hourly[0].net_buy_chog, 3.0);
        assert_eq!(hourly[0].gas_used_mean, Some(15.0));
        assert_eq!(hourly[0].gas_used_median, Some(15.0));
        assert_eq!(hourly[0].receipt_success_rate, Some(0.5));
    }
}

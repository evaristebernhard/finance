use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::Path;

use anyhow::{Context, Result, anyhow};
use arrow::array::{Array, Float64Array, StringArray, UInt64Array};
use arrow::record_batch::RecordBatch;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::Serialize;

use crate::chog_v1::{RAW_DIR, parquet_files_under};
use crate::dex::DEX_SWAP_DATASET;
use crate::dex_factors::DEX_SWAP_FACTORS_DATASET;
use crate::dex_hourly::{DERIVED_DIR, DEX_POOL_SWAP_HOURLY_DATASET};

const RAW_DATASETS: &[&str] = &[
    "main_pool_swap_logs",
    "dex_pool_swap_logs",
    "erc20_transfer_logs",
    "dex_pairs_snapshots",
    "tx_receipts",
    "block_headers",
    "prices_hourly",
    "collection_runs",
];
const DERIVED_DATASETS: &[&str] = &[DEX_POOL_SWAP_HOURLY_DATASET, DEX_SWAP_FACTORS_DATASET];
const PRICE_DATASET: &str = "prices_hourly";

#[derive(Debug, Clone, Serialize)]
pub struct BasicAnalysis {
    pub inventory: Vec<DatasetInventory>,
    pub dex: DexAnalysis,
    pub prices: Option<PriceSummary>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DatasetInventory {
    pub layer: String,
    pub dataset: String,
    pub files: u64,
    pub rows: u64,
    pub min_block: Option<u64>,
    pub max_block: Option<u64>,
    pub min_utc: Option<String>,
    pub max_utc: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct DexAnalysis {
    pub overview: DexOverview,
    pub by_quote: Vec<DexQuoteSummary>,
    pub top_pools: Vec<DexPoolSummary>,
    pub top_hours: Vec<DexHourSummary>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct DexOverview {
    pub swaps: u64,
    pub txs: u64,
    pub pools: u64,
    pub first_block: Option<u64>,
    pub last_block: Option<u64>,
    pub first_utc: Option<String>,
    pub last_utc: Option<String>,
    pub buy_swaps: u64,
    pub sell_swaps: u64,
    pub buy_chog: f64,
    pub sell_chog: f64,
    pub net_buy_chog: f64,
    pub chog_volume: f64,
    pub quote_volume: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct DexQuoteSummary {
    pub quote_symbol: String,
    pub quote_address: String,
    pub swaps: u64,
    pub txs: u64,
    pub pools: u64,
    pub buy_swaps: u64,
    pub sell_swaps: u64,
    pub buy_chog: f64,
    pub sell_chog: f64,
    pub net_buy_chog: f64,
    pub chog_volume: f64,
    pub quote_volume: f64,
    pub avg_price_quote_per_chog: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct DexPoolSummary {
    pub pool_address: String,
    pub dex_id: String,
    pub family: String,
    pub quote_symbol: String,
    pub quote_address: String,
    pub swaps: u64,
    pub txs: u64,
    pub buy_swaps: u64,
    pub sell_swaps: u64,
    pub buy_chog: f64,
    pub sell_chog: f64,
    pub net_buy_chog: f64,
    pub chog_volume: f64,
    pub quote_volume: f64,
    pub avg_price_quote_per_chog: f64,
    pub first_block: Option<u64>,
    pub last_block: Option<u64>,
    pub first_utc: Option<String>,
    pub last_utc: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DexHourSummary {
    pub hour_utc: String,
    pub swaps: u64,
    pub pool_txs: u64,
    pub buy_swaps: u64,
    pub sell_swaps: u64,
    pub buy_chog: f64,
    pub sell_chog: f64,
    pub net_buy_chog: f64,
    pub chog_volume: f64,
    pub quote_volume: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct PriceSummary {
    pub points: u64,
    pub min_hour_utc: Option<String>,
    pub max_hour_utc: Option<String>,
    pub latest_hour_utc: Option<String>,
    pub latest_price_usd: Option<f64>,
    pub min_price_usd: Option<f64>,
    pub max_price_usd: Option<f64>,
}

#[derive(Debug, Default)]
struct DexAgg {
    swaps: u64,
    txs: BTreeSet<String>,
    pools: BTreeSet<String>,
    first_block: Option<u64>,
    last_block: Option<u64>,
    first_utc: Option<String>,
    last_utc: Option<String>,
    buy_swaps: u64,
    sell_swaps: u64,
    buy_chog: f64,
    sell_chog: f64,
    chog_volume: f64,
    quote_volume: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct PoolKey {
    pool_address: String,
    dex_id: String,
    family: String,
    quote_symbol: String,
    quote_address: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct QuoteKey {
    quote_symbol: String,
    quote_address: String,
}

#[derive(Debug, Default)]
struct HourAgg {
    swaps: u64,
    pool_txs: u64,
    buy_swaps: u64,
    sell_swaps: u64,
    buy_chog: f64,
    sell_chog: f64,
    chog_volume: f64,
    quote_volume: f64,
}

pub fn basic_analysis(data_root: &Path, limit: usize) -> Result<BasicAnalysis> {
    Ok(BasicAnalysis {
        inventory: inventory(data_root)?,
        dex: dex_analysis(data_root, limit)?,
        prices: price_summary(data_root)?,
    })
}

pub fn inventory(data_root: &Path) -> Result<Vec<DatasetInventory>> {
    let mut rows = Vec::new();
    for dataset in RAW_DATASETS {
        rows.push(scan_inventory_dataset(
            "raw",
            dataset,
            &data_root.join(RAW_DIR).join(dataset),
        )?);
    }
    for dataset in DERIVED_DATASETS {
        rows.push(scan_inventory_dataset(
            "derived",
            dataset,
            &data_root.join(DERIVED_DIR).join(dataset),
        )?);
    }
    Ok(rows)
}

pub fn dex_analysis(data_root: &Path, limit: usize) -> Result<DexAnalysis> {
    let raw_root = data_root.join(RAW_DIR).join(DEX_SWAP_DATASET);
    let mut overview = DexAgg::default();
    let mut by_pool = BTreeMap::<PoolKey, DexAgg>::new();
    let mut by_quote = BTreeMap::<QuoteKey, DexAgg>::new();
    for path in parquet_files_under(&raw_root)? {
        read_dex_swap_file(&path, &mut overview, &mut by_pool, &mut by_quote)?;
    }

    let derived_root = data_root
        .join(DERIVED_DIR)
        .join(DEX_POOL_SWAP_HOURLY_DATASET);
    let mut by_hour = BTreeMap::<String, HourAgg>::new();
    for path in parquet_files_under(&derived_root)? {
        read_dex_hourly_file(&path, &mut by_hour)?;
    }

    let mut top_pools = by_pool
        .into_iter()
        .map(|(key, agg)| pool_summary(key, agg))
        .collect::<Vec<_>>();
    top_pools.sort_by(|a, b| {
        b.chog_volume
            .total_cmp(&a.chog_volume)
            .then_with(|| b.swaps.cmp(&a.swaps))
            .then_with(|| a.pool_address.cmp(&b.pool_address))
    });
    top_pools.truncate(limit);

    let mut quote_rows = by_quote
        .into_iter()
        .map(|(key, agg)| quote_summary(key, agg))
        .collect::<Vec<_>>();
    quote_rows.sort_by(|a, b| {
        b.chog_volume
            .total_cmp(&a.chog_volume)
            .then_with(|| b.swaps.cmp(&a.swaps))
            .then_with(|| a.quote_symbol.cmp(&b.quote_symbol))
    });

    let mut top_hours = by_hour
        .into_iter()
        .map(|(hour_utc, agg)| hour_summary(hour_utc, agg))
        .collect::<Vec<_>>();
    top_hours.sort_by(|a, b| {
        b.chog_volume
            .total_cmp(&a.chog_volume)
            .then_with(|| b.swaps.cmp(&a.swaps))
            .then_with(|| a.hour_utc.cmp(&b.hour_utc))
    });
    top_hours.truncate(limit);

    Ok(DexAnalysis {
        overview: overview_summary(overview),
        by_quote: quote_rows,
        top_pools,
        top_hours,
    })
}

pub fn price_summary(data_root: &Path) -> Result<Option<PriceSummary>> {
    let root = data_root.join(RAW_DIR).join(PRICE_DATASET);
    let mut summary = PriceSummary {
        points: 0,
        min_hour_utc: None,
        max_hour_utc: None,
        latest_hour_utc: None,
        latest_price_usd: None,
        min_price_usd: None,
        max_price_usd: None,
    };
    for path in parquet_files_under(&root)? {
        read_price_file(&path, &mut summary)?;
    }
    if summary.points == 0 {
        Ok(None)
    } else {
        Ok(Some(summary))
    }
}

fn scan_inventory_dataset(layer: &str, dataset: &str, root: &Path) -> Result<DatasetInventory> {
    let mut stats = DatasetInventory {
        layer: layer.to_string(),
        dataset: dataset.to_string(),
        files: 0,
        rows: 0,
        min_block: None,
        max_block: None,
        min_utc: None,
        max_utc: None,
    };
    for path in parquet_files_under(root)? {
        stats.files += 1;
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder
            .with_batch_size(4096)
            .build()
            .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            stats.rows += batch.num_rows() as u64;
            update_block_window(&batch, &mut stats.min_block, &mut stats.max_block)?;
            update_utc_window(&batch, &mut stats.min_utc, &mut stats.max_utc)?;
        }
    }
    Ok(stats)
}

fn read_dex_swap_file(
    path: &Path,
    overview: &mut DexAgg,
    by_pool: &mut BTreeMap<PoolKey, DexAgg>,
    by_quote: &mut BTreeMap<QuoteKey, DexAgg>,
) -> Result<()> {
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
        let block_datetime_utc = string_column(&batch, "block_datetime_utc")?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        let pool_address = string_column(&batch, "pool_address")?;
        let dex_id = string_column(&batch, "dex_id")?;
        let family = string_column(&batch, "family")?;
        let quote_symbol = string_column(&batch, "quote_symbol")?;
        let quote_address = string_column(&batch, "quote_address")?;
        let direction = string_column(&batch, "direction")?;
        let chog_abs = string_column(&batch, "chog_abs")?;
        let quote_abs = string_column(&batch, "quote_abs")?;
        for index in 0..batch.num_rows() {
            let pool = string_value(pool_address, index).to_ascii_lowercase();
            let quote = string_value(quote_symbol, index);
            let quote_addr = string_value(quote_address, index).to_ascii_lowercase();
            let block = optional_u64(block_number, index);
            let utc = optional_string(block_datetime_utc, index);
            let tx = optional_string(transaction_hash, index);
            let dir = string_value(direction, index);
            let chog = parse_f64(chog_abs, index)?;
            let quote_amount = parse_f64(quote_abs, index)?;

            observe_swap(
                overview,
                block,
                utc.as_deref(),
                tx.as_deref(),
                Some(&pool),
                &dir,
                chog,
                quote_amount,
            );

            let pool_key = PoolKey {
                pool_address: pool.clone(),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                quote_symbol: quote.clone(),
                quote_address: quote_addr.clone(),
            };
            observe_swap(
                by_pool.entry(pool_key).or_default(),
                block,
                utc.as_deref(),
                tx.as_deref(),
                Some(&pool),
                &dir,
                chog,
                quote_amount,
            );

            let quote_key = QuoteKey {
                quote_symbol: quote,
                quote_address: quote_addr,
            };
            observe_swap(
                by_quote.entry(quote_key).or_default(),
                block,
                utc.as_deref(),
                tx.as_deref(),
                Some(&pool),
                &dir,
                chog,
                quote_amount,
            );
        }
    }
    Ok(())
}

fn read_dex_hourly_file(path: &Path, by_hour: &mut BTreeMap<String, HourAgg>) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(4096)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let hour_utc = string_column(&batch, "hour_utc")?;
        let swaps = uint64_column(&batch, "swaps")?;
        let txs = uint64_column(&batch, "txs")?;
        let buy_swaps = uint64_column(&batch, "buy_swaps")?;
        let sell_swaps = uint64_column(&batch, "sell_swaps")?;
        let buy_chog = string_column(&batch, "buy_chog")?;
        let sell_chog = string_column(&batch, "sell_chog")?;
        let chog_volume = string_column(&batch, "chog_volume")?;
        let quote_volume = string_column(&batch, "quote_volume")?;
        for index in 0..batch.num_rows() {
            let hour = string_value(hour_utc, index);
            if hour.is_empty() {
                continue;
            }
            let agg = by_hour.entry(hour).or_default();
            agg.swaps += optional_u64(swaps, index).unwrap_or(0);
            agg.pool_txs += optional_u64(txs, index).unwrap_or(0);
            agg.buy_swaps += optional_u64(buy_swaps, index).unwrap_or(0);
            agg.sell_swaps += optional_u64(sell_swaps, index).unwrap_or(0);
            agg.buy_chog += parse_f64(buy_chog, index)?;
            agg.sell_chog += parse_f64(sell_chog, index)?;
            agg.chog_volume += parse_f64(chog_volume, index)?;
            agg.quote_volume += parse_f64(quote_volume, index)?;
        }
    }
    Ok(())
}

fn read_price_file(path: &Path, summary: &mut PriceSummary) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(4096)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let hour_utc = string_column(&batch, "hour_utc")?;
        let price_usd = float64_column(&batch, "price_usd")?;
        for index in 0..batch.num_rows() {
            if price_usd.is_null(index) {
                continue;
            }
            let hour = optional_string(hour_utc, index);
            let price = price_usd.value(index);
            summary.points += 1;
            update_min_max_string(&mut summary.min_hour_utc, &mut summary.max_hour_utc, &hour);
            summary.min_price_usd = Some(summary.min_price_usd.map_or(price, |v| v.min(price)));
            summary.max_price_usd = Some(summary.max_price_usd.map_or(price, |v| v.max(price)));
            if should_replace_latest(summary.latest_hour_utc.as_deref(), hour.as_deref()) {
                summary.latest_hour_utc = hour;
                summary.latest_price_usd = Some(price);
            }
        }
    }
    Ok(())
}

fn observe_swap(
    agg: &mut DexAgg,
    block: Option<u64>,
    utc: Option<&str>,
    tx: Option<&str>,
    pool: Option<&str>,
    direction: &str,
    chog: f64,
    quote: f64,
) {
    agg.swaps += 1;
    if let Some(tx) = tx.filter(|value| !value.is_empty()) {
        agg.txs.insert(tx.to_string());
    }
    if let Some(pool) = pool.filter(|value| !value.is_empty()) {
        agg.pools.insert(pool.to_string());
    }
    if let Some(block) = block {
        agg.first_block = Some(agg.first_block.map_or(block, |value| value.min(block)));
        agg.last_block = Some(agg.last_block.map_or(block, |value| value.max(block)));
    }
    if let Some(utc) = utc.filter(|value| !value.is_empty()) {
        update_min_max_string(
            &mut agg.first_utc,
            &mut agg.last_utc,
            &Some(utc.to_string()),
        );
    }
    agg.chog_volume += chog;
    agg.quote_volume += quote;
    match direction {
        "buy_chog" => {
            agg.buy_swaps += 1;
            agg.buy_chog += chog;
        }
        "sell_chog" => {
            agg.sell_swaps += 1;
            agg.sell_chog += chog;
        }
        _ => {}
    }
}

fn overview_summary(agg: DexAgg) -> DexOverview {
    DexOverview {
        swaps: agg.swaps,
        txs: agg.txs.len() as u64,
        pools: agg.pools.len() as u64,
        first_block: agg.first_block,
        last_block: agg.last_block,
        first_utc: agg.first_utc,
        last_utc: agg.last_utc,
        buy_swaps: agg.buy_swaps,
        sell_swaps: agg.sell_swaps,
        buy_chog: agg.buy_chog,
        sell_chog: agg.sell_chog,
        net_buy_chog: clean_zero(agg.buy_chog - agg.sell_chog),
        chog_volume: agg.chog_volume,
        quote_volume: agg.quote_volume,
    }
}

fn quote_summary(key: QuoteKey, agg: DexAgg) -> DexQuoteSummary {
    DexQuoteSummary {
        quote_symbol: key.quote_symbol,
        quote_address: key.quote_address,
        swaps: agg.swaps,
        txs: agg.txs.len() as u64,
        pools: agg.pools.len() as u64,
        buy_swaps: agg.buy_swaps,
        sell_swaps: agg.sell_swaps,
        buy_chog: agg.buy_chog,
        sell_chog: agg.sell_chog,
        net_buy_chog: clean_zero(agg.buy_chog - agg.sell_chog),
        chog_volume: agg.chog_volume,
        quote_volume: agg.quote_volume,
        avg_price_quote_per_chog: safe_div(agg.quote_volume, agg.chog_volume),
    }
}

fn pool_summary(key: PoolKey, agg: DexAgg) -> DexPoolSummary {
    DexPoolSummary {
        pool_address: key.pool_address,
        dex_id: key.dex_id,
        family: key.family,
        quote_symbol: key.quote_symbol,
        quote_address: key.quote_address,
        swaps: agg.swaps,
        txs: agg.txs.len() as u64,
        buy_swaps: agg.buy_swaps,
        sell_swaps: agg.sell_swaps,
        buy_chog: agg.buy_chog,
        sell_chog: agg.sell_chog,
        net_buy_chog: clean_zero(agg.buy_chog - agg.sell_chog),
        chog_volume: agg.chog_volume,
        quote_volume: agg.quote_volume,
        avg_price_quote_per_chog: safe_div(agg.quote_volume, agg.chog_volume),
        first_block: agg.first_block,
        last_block: agg.last_block,
        first_utc: agg.first_utc,
        last_utc: agg.last_utc,
    }
}

fn hour_summary(hour_utc: String, agg: HourAgg) -> DexHourSummary {
    DexHourSummary {
        hour_utc,
        swaps: agg.swaps,
        pool_txs: agg.pool_txs,
        buy_swaps: agg.buy_swaps,
        sell_swaps: agg.sell_swaps,
        buy_chog: agg.buy_chog,
        sell_chog: agg.sell_chog,
        net_buy_chog: clean_zero(agg.buy_chog - agg.sell_chog),
        chog_volume: agg.chog_volume,
        quote_volume: agg.quote_volume,
    }
}

fn update_block_window(
    batch: &RecordBatch,
    min_block: &mut Option<u64>,
    max_block: &mut Option<u64>,
) -> Result<()> {
    let Some(values) = optional_uint64_column(batch, "block_number")? else {
        return Ok(());
    };
    for index in 0..values.len() {
        if values.is_null(index) {
            continue;
        }
        let value = values.value(index);
        *min_block = Some(min_block.map_or(value, |current| current.min(value)));
        *max_block = Some(max_block.map_or(value, |current| current.max(value)));
    }
    Ok(())
}

fn update_utc_window(
    batch: &RecordBatch,
    min_utc: &mut Option<String>,
    max_utc: &mut Option<String>,
) -> Result<()> {
    for name in [
        "block_datetime_utc",
        "hour_utc",
        "fetched_at_utc",
        "started_at_utc",
        "finished_at_utc",
        "source_datetime_utc",
    ] {
        let Some(values) = optional_string_column(batch, name)? else {
            continue;
        };
        for index in 0..values.len() {
            update_min_max_string(min_utc, max_utc, &optional_string(values, index));
        }
        return Ok(());
    }
    Ok(())
}

fn update_min_max_string(
    min_value: &mut Option<String>,
    max_value: &mut Option<String>,
    value: &Option<String>,
) {
    let Some(value) = value.as_ref().filter(|value| !value.is_empty()) else {
        return;
    };
    if min_value.as_ref().is_none_or(|current| value < current) {
        *min_value = Some(value.clone());
    }
    if max_value.as_ref().is_none_or(|current| value > current) {
        *max_value = Some(value.clone());
    }
}

fn should_replace_latest(current: Option<&str>, next: Option<&str>) -> bool {
    match (current, next) {
        (_, None) => false,
        (None, Some(_)) => true,
        (Some(current), Some(next)) => next > current,
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

fn optional_uint64_column<'a>(
    batch: &'a RecordBatch,
    name: &str,
) -> Result<Option<&'a UInt64Array>> {
    let Ok(index) = batch.schema().index_of(name) else {
        return Ok(None);
    };
    Ok(Some(
        batch
            .column(index)
            .as_any()
            .downcast_ref::<UInt64Array>()
            .ok_or_else(|| anyhow!("column {name} is not uint64"))?,
    ))
}

fn float64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array> {
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

fn optional_u64(values: &UInt64Array, index: usize) -> Option<u64> {
    if values.is_null(index) {
        None
    } else {
        Some(values.value(index))
    }
}

fn optional_string(values: &StringArray, index: usize) -> Option<String> {
    if values.is_null(index) {
        None
    } else {
        Some(values.value(index).to_string())
    }
}

fn string_value(values: &StringArray, index: usize) -> String {
    optional_string(values, index).unwrap_or_default()
}

fn parse_f64(values: &StringArray, index: usize) -> Result<f64> {
    if values.is_null(index) || values.value(index).is_empty() {
        return Ok(0.0);
    }
    values
        .value(index)
        .parse::<f64>()
        .with_context(|| format!("invalid numeric value {}", values.value(index)))
}

fn safe_div(numerator: f64, denominator: f64) -> f64 {
    if denominator > 0.0 {
        numerator / denominator
    } else {
        0.0
    }
}

fn clean_zero(value: f64) -> f64 {
    if value.abs() < f64::EPSILON {
        0.0
    } else {
        value
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn summarizes_quote_aggregate() {
        let mut agg = DexAgg::default();
        observe_swap(
            &mut agg,
            Some(10),
            Some("2026-05-07T00:01:00Z"),
            Some("0xtx1"),
            Some("0xpool1"),
            "buy_chog",
            10.0,
            0.5,
        );
        observe_swap(
            &mut agg,
            Some(11),
            Some("2026-05-07T00:02:00Z"),
            Some("0xtx2"),
            Some("0xpool2"),
            "sell_chog",
            4.0,
            0.2,
        );

        let row = quote_summary(
            QuoteKey {
                quote_symbol: "MON".to_string(),
                quote_address: "0xquote".to_string(),
            },
            agg,
        );
        assert_eq!(row.swaps, 2);
        assert_eq!(row.txs, 2);
        assert_eq!(row.pools, 2);
        assert_eq!(row.net_buy_chog, 6.0);
        assert!((row.avg_price_quote_per_chog - 0.05).abs() < 1e-12);
    }
}

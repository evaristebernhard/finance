use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow};
use arrow::array::{Array, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

use crate::chog_v1::{
    RAW_DIR, dt_from_utc_string, f64_array, parquet_files_under, string_array, u64_array,
    write_parquet_part, write_schema_metadata,
};
use crate::dex::DEX_SWAP_DATASET;

pub const DERIVED_DIR: &str = "derived";
pub const DEX_POOL_SWAP_HOURLY_DATASET: &str = "dex_pool_swap_hourly";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DexHourlyPartSummary {
    pub dt: String,
    pub rows: usize,
    pub path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DexHourlyRebuildSummary {
    pub input_root: PathBuf,
    pub min_block: Option<u64>,
    pub max_block: Option<u64>,
    pub hourly_rows: u64,
    pub parquet_parts: u64,
    pub parts: Vec<DexHourlyPartSummary>,
    pub dry_run: bool,
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
    swaps: u64,
    txs: BTreeSet<String>,
    buy_swaps: u64,
    sell_swaps: u64,
    buy_chog: f64,
    sell_chog: f64,
    chog_volume: f64,
    quote_volume: f64,
}

#[derive(Debug, Clone)]
struct HourRow {
    hour_utc: String,
    pool_address: String,
    dex_id: String,
    family: String,
    quote_symbol: String,
    quote_address: String,
    swaps: u64,
    txs: u64,
    buy_swaps: u64,
    sell_swaps: u64,
    count_imbalance: f64,
    buy_chog: String,
    sell_chog: String,
    net_buy_chog: String,
    net_sell_chog: String,
    chog_volume: String,
    quote_volume: String,
    avg_price_quote_per_chog: String,
    dt: String,
}

pub fn rebuild_dex_pool_swap_hourly(
    data_root: &Path,
    pool_addresses: &[String],
    dry_run: bool,
) -> Result<DexHourlyRebuildSummary> {
    let requested = pool_addresses
        .iter()
        .map(|value| value.to_ascii_lowercase())
        .collect::<BTreeSet<_>>();
    let root = data_root.join(RAW_DIR).join(DEX_SWAP_DATASET);
    let mut aggs = BTreeMap::<HourKey, HourAgg>::new();
    let mut min_block = None::<u64>;
    let mut max_block = None::<u64>;
    for path in parquet_files_under(&root)? {
        read_swap_file(&path, &requested, &mut aggs, &mut min_block, &mut max_block)?;
    }
    if aggs.is_empty() {
        return Ok(DexHourlyRebuildSummary {
            input_root: root,
            min_block,
            max_block,
            hourly_rows: 0,
            parquet_parts: 0,
            parts: Vec::new(),
            dry_run,
        });
    }

    let rows = build_hour_rows(aggs);
    let schema = hourly_schema();
    write_schema_metadata(
        data_root,
        DEX_POOL_SWAP_HOURLY_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let min_block = min_block.unwrap_or(0);
    let max_block = max_block.unwrap_or(0);
    let stem = format!("dex_rebuild_hourly_{min_block}_{max_block}");

    if dry_run {
        let parts = row_counts_by_dt(&rows)
            .into_iter()
            .map(|(dt, rows)| DexHourlyPartSummary {
                path: derived_part_path(data_root, DEX_POOL_SWAP_HOURLY_DATASET, &dt, &stem),
                dt,
                rows,
            })
            .collect::<Vec<_>>();
        return Ok(DexHourlyRebuildSummary {
            input_root: root,
            min_block: Some(min_block),
            max_block: Some(max_block),
            hourly_rows: rows.len() as u64,
            parquet_parts: parts.len() as u64,
            parts,
            dry_run,
        });
    }

    let mut parts = Vec::new();
    for (dt, rows) in rows_by_dt(rows) {
        let batch = hour_rows_to_batch(schema.clone(), &rows)?;
        let path = derived_part_path(data_root, DEX_POOL_SWAP_HOURLY_DATASET, &dt, &stem);
        let write = write_parquet_part(&path, schema.clone(), batch)?;
        parts.push(DexHourlyPartSummary {
            dt,
            rows: write.rows,
            path: write.path,
        });
    }
    let written_rows = parts.iter().map(|part| part.rows as u64).sum::<u64>();
    Ok(DexHourlyRebuildSummary {
        input_root: root,
        min_block: Some(min_block),
        max_block: Some(max_block),
        hourly_rows: written_rows,
        parquet_parts: parts.len() as u64,
        parts,
        dry_run,
    })
}

pub fn derived_part_path(data_root: &Path, dataset: &str, dt: &str, part_stem: &str) -> PathBuf {
    data_root
        .join(DERIVED_DIR)
        .join(dataset)
        .join(format!("dt={dt}"))
        .join(format!("{part_stem}.parquet"))
}

fn read_swap_file(
    path: &Path,
    requested: &BTreeSet<String>,
    aggs: &mut BTreeMap<HourKey, HourAgg>,
    min_block: &mut Option<u64>,
    max_block: &mut Option<u64>,
) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(2048)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let block_number = uint64_column(&batch, "block_number")?;
        let block_datetime_utc = string_column(&batch, "block_datetime_utc")?;
        let fetched_at_utc = string_column(&batch, "fetched_at_utc")?;
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
            if block_number.is_null(index) || pool_address.is_null(index) {
                continue;
            }
            let pool = pool_address.value(index).to_ascii_lowercase();
            if !requested.is_empty() && !requested.contains(&pool) {
                continue;
            }
            let block = block_number.value(index);
            *min_block = Some(min_block.map_or(block, |value| value.min(block)));
            *max_block = Some(max_block.map_or(block, |value| value.max(block)));
            let time = if !block_datetime_utc.is_null(index)
                && !block_datetime_utc.value(index).is_empty()
            {
                block_datetime_utc.value(index)
            } else {
                fetched_at_utc.value(index)
            };
            let key = HourKey {
                hour_utc: hour_from_utc(time),
                pool_address: pool,
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                quote_symbol: string_value(quote_symbol, index),
                quote_address: string_value(quote_address, index),
            };
            let agg = aggs.entry(key).or_default();
            agg.swaps += 1;
            if !transaction_hash.is_null(index) {
                agg.txs.insert(transaction_hash.value(index).to_string());
            }
            let chog = parse_f64(chog_abs, index)?;
            let quote = parse_f64(quote_abs, index)?;
            agg.chog_volume += chog;
            agg.quote_volume += quote;
            match string_value(direction, index).as_str() {
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
    }
    Ok(())
}

fn build_hour_rows(aggs: BTreeMap<HourKey, HourAgg>) -> Vec<HourRow> {
    aggs.into_iter()
        .map(|(key, agg)| {
            let count_imbalance = if agg.swaps == 0 {
                0.0
            } else {
                (agg.buy_swaps as f64 - agg.sell_swaps as f64) / agg.swaps as f64
            };
            let net_buy_chog = clean_zero(agg.buy_chog - agg.sell_chog);
            let net_sell_chog = clean_zero(agg.sell_chog - agg.buy_chog);
            let avg_price = if agg.chog_volume > 0.0 {
                agg.quote_volume / agg.chog_volume
            } else {
                0.0
            };
            let dt = dt_from_utc_string(&key.hour_utc);
            HourRow {
                hour_utc: key.hour_utc,
                pool_address: key.pool_address,
                dex_id: key.dex_id,
                family: key.family,
                quote_symbol: key.quote_symbol,
                quote_address: key.quote_address,
                swaps: agg.swaps,
                txs: agg.txs.len() as u64,
                buy_swaps: agg.buy_swaps,
                sell_swaps: agg.sell_swaps,
                count_imbalance,
                buy_chog: format_decimal(agg.buy_chog),
                sell_chog: format_decimal(agg.sell_chog),
                net_buy_chog: format_decimal(net_buy_chog),
                net_sell_chog: format_decimal(net_sell_chog),
                chog_volume: format_decimal(agg.chog_volume),
                quote_volume: format_decimal(agg.quote_volume),
                avg_price_quote_per_chog: format_decimal(avg_price),
                dt,
            }
        })
        .collect()
}

fn hourly_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("hour_utc", DataType::Utf8, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("swaps", DataType::UInt64, false),
        Field::new("txs", DataType::UInt64, false),
        Field::new("buy_swaps", DataType::UInt64, false),
        Field::new("sell_swaps", DataType::UInt64, false),
        Field::new("count_imbalance", DataType::Float64, false),
        Field::new("buy_chog", DataType::Utf8, false),
        Field::new("sell_chog", DataType::Utf8, false),
        Field::new("net_buy_chog", DataType::Utf8, false),
        Field::new("net_sell_chog", DataType::Utf8, false),
        Field::new("chog_volume", DataType::Utf8, false),
        Field::new("quote_volume", DataType::Utf8, false),
        Field::new("avg_price_quote_per_chog", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn hour_rows_to_batch(schema: SchemaRef, rows: &[HourRow]) -> Result<RecordBatch> {
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
            u64_array(&rows.iter().map(|row| row.swaps).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.txs).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.buy_swaps).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.sell_swaps).collect::<Vec<_>>()),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.count_imbalance)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.buy_chog.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.sell_chog.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.net_buy_chog.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.net_sell_chog.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.chog_volume.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quote_volume.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.avg_price_quote_per_chog.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
        ],
    )?)
}

fn rows_by_dt(rows: Vec<HourRow>) -> BTreeMap<String, Vec<HourRow>> {
    let mut by_dt = BTreeMap::<String, Vec<HourRow>>::new();
    for row in rows {
        by_dt.entry(row.dt.clone()).or_default().push(row);
    }
    by_dt
}

fn row_counts_by_dt(rows: &[HourRow]) -> BTreeMap<String, usize> {
    let mut by_dt = BTreeMap::<String, usize>::new();
    for row in rows {
        *by_dt.entry(row.dt.clone()).or_default() += 1;
    }
    by_dt
}

fn hour_from_utc(value: &str) -> String {
    if value.len() >= 13 {
        format!("{}:00:00Z", &value[..13])
    } else {
        String::new()
    }
}

fn format_decimal(value: f64) -> String {
    format!("{:.18}", clean_zero(value))
}

fn clean_zero(value: f64) -> f64 {
    if value.abs() < f64::EPSILON {
        0.0
    } else {
        value
    }
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

fn string_value(values: &StringArray, index: usize) -> String {
    if values.is_null(index) {
        String::new()
    } else {
        values.value(index).to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_hour_rows_from_aggregates() {
        let key = HourKey {
            hour_utc: "2026-05-07T01:00:00Z".to_string(),
            pool_address: "0xpool".to_string(),
            dex_id: "dex".to_string(),
            family: "v2".to_string(),
            quote_symbol: "MON".to_string(),
            quote_address: "0xquote".to_string(),
        };
        let mut agg = HourAgg {
            swaps: 2,
            buy_swaps: 1,
            sell_swaps: 1,
            buy_chog: 10.0,
            sell_chog: 4.0,
            chog_volume: 14.0,
            quote_volume: 0.7,
            ..HourAgg::default()
        };
        agg.txs.insert("0xa".to_string());
        agg.txs.insert("0xb".to_string());
        let rows = build_hour_rows(BTreeMap::from([(key, agg)]));
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].txs, 2);
        assert_eq!(rows[0].net_buy_chog, "6.000000000000000000");
        let avg_price = rows[0].avg_price_quote_per_chog.parse::<f64>().unwrap();
        assert!((avg_price - 0.05).abs() < 1e-12);
    }
}

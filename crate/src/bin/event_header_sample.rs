use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chog_prices::{
    CHECKPOINT_VERSION, Checkpoint, RpcUrlPool,
    chog_v1::{
        ChogCollectionRunRecord, PartWrite, PartWriteStatus, RpcBlock, checkpoint_path_with_suffix,
        custom_part_path, default_data_root_path, dt_from_timestamp, opt_u64_array,
        parquet_files_under, part_paths_to_string, string_array, u64_array,
        write_collection_run_parquet, write_parquet_part, write_schema_metadata,
    },
    parse_hex_u64, save_checkpoint, to_hex, utc_now_string,
};
use clap::Parser;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use reqwest::blocking::Client;
use serde_json::{Value, json};

const DEFAULT_RPC_URL: &str = "https://rpc.monad.xyz";
const DEFAULT_BATCH_SIZE: usize = 200;
const DEFAULT_BATCH_THROTTLE_MS: u64 = 0;
const MAX_RETRIES: usize = 5;
const COLLECTOR: &str = "event_header_sample";
const CHAIN: &str = "monad";
const DATASET: &str = "event_block_headers";
const SOURCE_DATASETS: &[&str] = &[
    "main_pool_swap_logs",
    "dex_pool_swap_logs",
    "erc20_transfer_logs",
];

#[derive(Debug, Parser)]
#[command(
    name = "event_header_sample",
    about = "Fetch block headers only for locally observed CHOG event blocks."
)]
struct Args {
    #[arg(long = "rpc-url", default_value = DEFAULT_RPC_URL)]
    rpc_url: Vec<String>,

    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Optional first event block to consider.
    #[arg(long)]
    from_block: Option<u64>,

    /// Optional final event block to consider.
    #[arg(long)]
    to_block: Option<u64>,

    /// Suffix for the default checkpoint filename, useful for parallel shards.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Block numbers per JSON-RPC batch when fetching headers.
    #[arg(long, default_value_t = DEFAULT_BATCH_SIZE)]
    batch_size: usize,

    /// Milliseconds to sleep between JSON-RPC header batches.
    #[arg(long, default_value_t = DEFAULT_BATCH_THROTTLE_MS)]
    batch_throttle_ms: u64,

    /// Resolve local event blocks and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct EventBlockStats {
    log_count: u64,
    tx_hashes: BTreeSet<String>,
    source_datasets: BTreeSet<String>,
}

impl EventBlockStats {
    fn tx_count(&self) -> u64 {
        self.tx_hashes.len() as u64
    }

    fn source_datasets(&self) -> String {
        self.source_datasets
            .iter()
            .cloned()
            .collect::<Vec<_>>()
            .join("|")
    }
}

#[derive(Debug, Clone)]
struct EventHeaderRow {
    fetched_at_utc: String,
    block_number: u64,
    block_hash: String,
    parent_hash: String,
    block_timestamp: u64,
    block_datetime_utc: String,
    base_fee_per_gas: Option<u64>,
    gas_used: u64,
    gas_limit: u64,
    miner: String,
    extra_data: String,
    transaction_count: u64,
    event_log_count: u64,
    event_tx_count: u64,
    source_datasets: String,
    dt: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.batch_size == 0 {
        bail!("--batch-size must be greater than 0");
    }
    if let (Some(from_block), Some(to_block)) = (args.from_block, args.to_block) {
        if from_block > to_block {
            bail!("--from-block {from_block} is greater than --to-block {to_block}");
        }
    }

    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let event_blocks = discover_event_blocks(&data_root, args.from_block, args.to_block)?;
    let existing_blocks = existing_event_header_blocks(&data_root)?;
    let missing_blocks = missing_event_blocks(&event_blocks, &existing_blocks);
    let estimated_batches = missing_blocks.len().div_ceil(args.batch_size);

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DATASET}");
        match (args.from_block, args.to_block) {
            (Some(from_block), Some(to_block)) => {
                println!("block window: {from_block}..{to_block}")
            }
            (Some(from_block), None) => println!("block window: {from_block}..local-max"),
            (None, Some(to_block)) => println!("block window: local-min..{to_block}"),
            (None, None) => println!("block window: all local events"),
        }
        println!("unique event blocks: {}", event_blocks.len());
        println!("existing event headers: {}", existing_blocks.len());
        println!("missing event headers: {}", missing_blocks.len());
        println!("estimated RPC batches: {estimated_batches}");
        println!("data root: {}", data_root.display());
        return Ok(());
    }

    let schema = event_header_schema();
    write_schema_metadata(&data_root, DATASET, schema.as_ref(), &["dt"])?;

    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-event-header-sample/0.1")
        .build()
        .context("failed to build HTTP client")?;
    let rpc_urls = RpcUrlPool::from_values(&args.rpc_url, DEFAULT_RPC_URL)?;
    let rows = fetch_event_headers_with_retry(
        &client,
        &rpc_urls,
        &missing_blocks,
        &event_blocks,
        &fetched_at,
        args.batch_size,
        args.batch_throttle_ms,
    )?;
    let output_parts = write_event_header_parts(&data_root, schema, &rows)?;
    let rows_written = output_parts
        .iter()
        .filter(|part| part.status == PartWriteStatus::Written)
        .map(|part| part.rows as u64)
        .sum::<u64>();
    let finished_at = utc_now_string();
    let checkpoint_path =
        checkpoint_path_with_suffix(&data_root, COLLECTOR, args.checkpoint_suffix.as_deref())?;
    let checkpoint = Checkpoint {
        version: CHECKPOINT_VERSION,
        collector: COLLECTOR.to_string(),
        chain: CHAIN.to_string(),
        address: String::new(),
        topic0: SOURCE_DATASETS.join("|"),
        from_block: args.from_block.unwrap_or(0),
        to_block: args.to_block.unwrap_or(0),
        last_completed_block: args
            .to_block
            .unwrap_or_else(|| event_blocks.keys().next_back().copied().unwrap_or_default()),
        rows_written,
        output: part_paths_to_string(&output_parts),
        updated_at_utc: finished_at.clone(),
    };
    save_checkpoint(&checkpoint_path, &checkpoint)?;
    write_collection_run_parquet(
        &data_root,
        &ChogCollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: SOURCE_DATASETS.join("|"),
            from_block: args.from_block,
            to_block: args.to_block,
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed: missing_blocks.chunks(args.batch_size).count() as u64,
            status: if missing_blocks.is_empty() {
                "empty"
            } else {
                "completed"
            }
            .to_string(),
            error: String::new(),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    println!("unique event blocks: {}", event_blocks.len());
    println!("missing event headers fetched: {}", missing_blocks.len());
    println!("event headers written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    Ok(())
}

fn discover_event_blocks(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> Result<BTreeMap<u64, EventBlockStats>> {
    let mut blocks = BTreeMap::<u64, EventBlockStats>::new();
    for dataset in SOURCE_DATASETS {
        let root = data_root.join(chog_prices::chog_v1::RAW_DIR).join(dataset);
        for path in parquet_files_under(&root)? {
            read_event_blocks_from_file(&path, dataset, from_block, to_block, &mut blocks)?;
        }
    }
    Ok(blocks)
}

fn read_event_blocks_from_file(
    path: &Path,
    dataset: &str,
    from_block: Option<u64>,
    to_block: Option<u64>,
    blocks: &mut BTreeMap<u64, EventBlockStats>,
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
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        for index in 0..batch.num_rows() {
            if block_number.is_null(index) {
                continue;
            }
            let block = block_number.value(index);
            if !block_in_window(block, from_block, to_block) {
                continue;
            }
            let stats = blocks.entry(block).or_default();
            stats.log_count += 1;
            stats.source_datasets.insert(dataset.to_string());
            if !transaction_hash.is_null(index) && !transaction_hash.value(index).is_empty() {
                stats
                    .tx_hashes
                    .insert(transaction_hash.value(index).to_string());
            }
        }
    }
    Ok(())
}

fn block_in_window(block: u64, from_block: Option<u64>, to_block: Option<u64>) -> bool {
    from_block.map_or(true, |from_block| block >= from_block)
        && to_block.map_or(true, |to_block| block <= to_block)
}

fn existing_event_header_blocks(data_root: &Path) -> Result<BTreeSet<u64>> {
    let mut blocks = BTreeSet::new();
    let root = data_root.join(chog_prices::chog_v1::RAW_DIR).join(DATASET);
    for path in parquet_files_under(&root)? {
        read_block_numbers_from_file(&path, &mut blocks)?;
    }
    Ok(blocks)
}

fn read_block_numbers_from_file(path: &Path, blocks: &mut BTreeSet<u64>) -> Result<()> {
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
        for index in 0..batch.num_rows() {
            if !block_number.is_null(index) {
                blocks.insert(block_number.value(index));
            }
        }
    }
    Ok(())
}

fn missing_event_blocks(
    event_blocks: &BTreeMap<u64, EventBlockStats>,
    existing_blocks: &BTreeSet<u64>,
) -> Vec<u64> {
    event_blocks
        .keys()
        .filter(|block| !existing_blocks.contains(block))
        .copied()
        .collect()
}

fn fetch_event_headers_with_retry(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    block_numbers: &[u64],
    event_blocks: &BTreeMap<u64, EventBlockStats>,
    fetched_at: &str,
    batch_size: usize,
    batch_throttle_ms: u64,
) -> Result<Vec<EventHeaderRow>> {
    let mut last_error = None;
    let max_attempts = MAX_RETRIES * rpc_urls.len();
    for attempt in 1..=max_attempts {
        match fetch_event_headers(
            client,
            rpc_urls,
            block_numbers,
            event_blocks,
            fetched_at,
            batch_size,
            batch_throttle_ms,
        ) {
            Ok(rows) => return Ok(rows),
            Err(error) => {
                last_error = Some(error);
                if attempt < max_attempts {
                    sleep(Duration::from_secs(2 * attempt as u64));
                }
            }
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("event header batch fetch failed without an error")))
}

fn fetch_event_headers(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    block_numbers: &[u64],
    event_blocks: &BTreeMap<u64, EventBlockStats>,
    fetched_at: &str,
    batch_size: usize,
    batch_throttle_ms: u64,
) -> Result<Vec<EventHeaderRow>> {
    if block_numbers.is_empty() {
        return Ok(Vec::new());
    }

    let mut rows = Vec::with_capacity(block_numbers.len());
    for (index, batch) in block_numbers.chunks(batch_size).enumerate() {
        if index > 0 && batch_throttle_ms > 0 {
            sleep(Duration::from_millis(batch_throttle_ms));
        }
        rows.extend(fetch_event_header_batch(
            client,
            rpc_urls.next_url(),
            batch,
            event_blocks,
            fetched_at,
        )?);
    }
    Ok(rows)
}

fn fetch_event_header_batch(
    client: &Client,
    rpc_url: &str,
    block_numbers: &[u64],
    event_blocks: &BTreeMap<u64, EventBlockStats>,
    fetched_at: &str,
) -> Result<Vec<EventHeaderRow>> {
    let body = block_numbers
        .iter()
        .map(|block_number| {
            json!({
                "jsonrpc": "2.0",
                "id": block_number,
                "method": "eth_getBlockByNumber",
                "params": [to_hex(*block_number), false],
            })
        })
        .collect::<Vec<_>>();

    let response = client
        .post(rpc_url)
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .context("failed RPC batch request eth_getBlockByNumber")?;
    let status = response.status();
    let text = response
        .text()
        .context("failed to read RPC batch response")?;
    if !status.is_success() {
        bail!("RPC batch request eth_getBlockByNumber failed with status {status}: {text}");
    }

    let responses: Vec<Value> = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse RPC batch response: {text}"))?;
    if responses.len() != block_numbers.len() {
        bail!(
            "RPC batch response length mismatch: got {}, expected {}",
            responses.len(),
            block_numbers.len()
        );
    }

    let mut by_id = BTreeMap::<u64, Value>::new();
    for response in responses {
        if let Some(error) = response.get("error") {
            bail!("RPC error from eth_getBlockByNumber batch: {error}");
        }
        let id = response
            .get("id")
            .and_then(Value::as_u64)
            .ok_or_else(|| anyhow!("RPC batch response did not include numeric id"))?;
        let result = response
            .get("result")
            .cloned()
            .ok_or_else(|| anyhow!("RPC batch response for block {id} did not include result"))?;
        by_id.insert(id, result);
    }

    let mut rows = Vec::with_capacity(block_numbers.len());
    for block_number in block_numbers {
        let value = by_id
            .remove(block_number)
            .ok_or_else(|| anyhow!("RPC batch response missing block {block_number}"))?;
        if value.is_null() {
            bail!("block {block_number} not found");
        }
        let block: RpcBlock = serde_json::from_value(value)
            .with_context(|| format!("failed to parse block {block_number}"))?;
        let stats = event_blocks
            .get(block_number)
            .ok_or_else(|| anyhow!("missing event stats for block {block_number}"))?;
        rows.push(parse_event_header(*block_number, block, fetched_at, stats)?);
    }
    Ok(rows)
}

fn parse_event_header(
    block_number: u64,
    block: RpcBlock,
    fetched_at: &str,
    stats: &EventBlockStats,
) -> Result<EventHeaderRow> {
    let parsed_block_number = block
        .number
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?
        .unwrap_or(block_number);
    let block_timestamp = parse_hex_u64(&block.timestamp)?;
    let dt = dt_from_timestamp(block_timestamp)?;
    Ok(EventHeaderRow {
        fetched_at_utc: fetched_at.to_string(),
        block_number: parsed_block_number,
        block_hash: block.hash.unwrap_or_default(),
        parent_hash: block.parent_hash.unwrap_or_default(),
        block_timestamp,
        block_datetime_utc: chog_prices::chog_v1::utc_from_timestamp(block_timestamp)?,
        base_fee_per_gas: block
            .base_fee_per_gas
            .as_deref()
            .map(parse_hex_u64)
            .transpose()?,
        gas_used: parse_hex_u64(&block.gas_used)?,
        gas_limit: parse_hex_u64(&block.gas_limit)?,
        miner: block.miner.unwrap_or_default(),
        extra_data: block.extra_data.unwrap_or_default(),
        transaction_count: block.transactions.len() as u64,
        event_log_count: stats.log_count,
        event_tx_count: stats.tx_count(),
        source_datasets: stats.source_datasets(),
        dt,
    })
}

fn event_header_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, false),
        Field::new("block_hash", DataType::Utf8, false),
        Field::new("parent_hash", DataType::Utf8, false),
        Field::new("block_timestamp", DataType::UInt64, false),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("base_fee_per_gas", DataType::UInt64, true),
        Field::new("gas_used", DataType::UInt64, false),
        Field::new("gas_limit", DataType::UInt64, false),
        Field::new("miner", DataType::Utf8, false),
        Field::new("extra_data", DataType::Utf8, false),
        Field::new("transaction_count", DataType::UInt64, false),
        Field::new("event_log_count", DataType::UInt64, false),
        Field::new("event_tx_count", DataType::UInt64, false),
        Field::new("source_datasets", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn write_event_header_parts(
    data_root: &Path,
    schema: SchemaRef,
    rows: &[EventHeaderRow],
) -> Result<Vec<PartWrite>> {
    if rows.is_empty() {
        return Ok(Vec::new());
    }

    let min_block = rows.iter().map(|row| row.block_number).min().unwrap_or(0);
    let max_block = rows.iter().map(|row| row.block_number).max().unwrap_or(0);
    let stem = format!("{COLLECTOR}_{min_block}_{max_block}");
    let mut by_dt = BTreeMap::<String, Vec<EventHeaderRow>>::new();
    for row in rows {
        by_dt.entry(row.dt.clone()).or_default().push(row.clone());
    }

    let mut parts = Vec::new();
    for (dt, rows) in by_dt {
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.fetched_at_utc.clone())
                        .collect::<Vec<_>>(),
                ),
                u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.block_hash.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.parent_hash.clone())
                        .collect::<Vec<_>>(),
                ),
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
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.base_fee_per_gas)
                        .collect::<Vec<_>>(),
                ),
                u64_array(&rows.iter().map(|row| row.gas_used).collect::<Vec<_>>()),
                u64_array(&rows.iter().map(|row| row.gas_limit).collect::<Vec<_>>()),
                string_array(&rows.iter().map(|row| row.miner.clone()).collect::<Vec<_>>()),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.extra_data.clone())
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.transaction_count)
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.event_log_count)
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.event_tx_count)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.source_datasets.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
            ],
        )?;
        parts.push(write_parquet_part(
            &custom_part_path(data_root, DATASET, &dt, &stem),
            schema.clone(),
            batch,
        )?);
    }
    Ok(parts)
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn block_window_filters_bounds_inclusively() {
        assert!(!block_in_window(99, Some(100), Some(200)));
        assert!(block_in_window(100, Some(100), Some(200)));
        assert!(block_in_window(200, Some(100), Some(200)));
        assert!(!block_in_window(201, Some(100), Some(200)));
    }

    #[test]
    fn missing_event_blocks_dedupes_and_skips_existing_headers() {
        let mut event_blocks = BTreeMap::new();
        event_blocks.insert(100, EventBlockStats::default());
        event_blocks.insert(101, EventBlockStats::default());
        event_blocks.insert(102, EventBlockStats::default());
        let existing = BTreeSet::from([101]);
        assert_eq!(
            missing_event_blocks(&event_blocks, &existing),
            vec![100, 102]
        );
    }

    #[test]
    fn event_block_stats_counts_unique_transactions_and_sources() {
        let mut stats = EventBlockStats::default();
        stats.log_count += 3;
        stats.tx_hashes.insert("0xa".to_string());
        stats.tx_hashes.insert("0xa".to_string());
        stats.tx_hashes.insert("0xb".to_string());
        stats
            .source_datasets
            .insert("dex_pool_swap_logs".to_string());
        stats
            .source_datasets
            .insert("main_pool_swap_logs".to_string());
        assert_eq!(stats.tx_count(), 2);
        assert_eq!(
            stats.source_datasets(),
            "dex_pool_swap_logs|main_pool_swap_logs"
        );
    }
}

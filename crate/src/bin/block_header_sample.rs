use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chog_prices::{
    CHECKPOINT_VERSION, Checkpoint, RpcUrlPool,
    chog_v1::{
        ChogCollectionRunRecord, PartWrite, PartWriteStatus, RpcBlock, checkpoint_path_with_suffix,
        default_data_root_path, dt_from_timestamp, opt_u64_array, part_paths_to_string,
        rpc_part_path, string_array, u64_array, write_collection_run_parquet, write_parquet_part,
        write_schema_metadata,
    },
    load_checkpoint, parse_hex_u64, resolve_block_range, rpc_call_hex_u64_from_pool,
    save_checkpoint, to_hex, utc_now_string, validate_checkpoint_identity,
};
use clap::Parser;
use reqwest::blocking::Client;
use serde_json::{Value, json};

const DEFAULT_RPC_URL: &str = "https://rpc.monad.xyz";
const DEFAULT_BLOCKS: u64 = 5_000;
const DEFAULT_PART_BLOCKS: u64 = 100;
const DEFAULT_BLOCK_BATCH_SIZE: usize = 10;
const DEFAULT_BATCH_THROTTLE_MS: u64 = 1_300;
const MAX_RETRIES: usize = 5;
const COLLECTOR: &str = "block_header_sample";
const CHAIN: &str = "monad";
const DATASET: &str = "block_headers";

#[derive(Debug, Parser)]
#[command(
    name = "block_header_sample",
    about = "Fetch CHOG v1 block headers and gas metadata from Monad RPC."
)]
struct Args {
    #[arg(long = "rpc-url", default_value = DEFAULT_RPC_URL)]
    rpc_url: Vec<String>,

    /// Recent block count to scan.
    #[arg(long, default_value_t = DEFAULT_BLOCKS)]
    blocks: u64,

    /// Explicit first block to scan. Takes precedence over --resume and --blocks.
    #[arg(long)]
    from_block: Option<u64>,

    /// Explicit final block to scan. Defaults to latest block at run start.
    #[arg(long)]
    to_block: Option<u64>,

    /// Resume from checkpoint last_completed_block + 1 when a checkpoint exists.
    #[arg(long)]
    resume: bool,

    /// Checkpoint path. Defaults to <data-root>/_checkpoints/block_header_sample.json.
    #[arg(long)]
    checkpoint: Option<PathBuf>,

    /// Suffix for the default checkpoint filename, useful for parallel shards.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Block count per output part/checkpoint chunk.
    #[arg(long, default_value_t = DEFAULT_PART_BLOCKS)]
    part_blocks: u64,

    /// Block numbers per JSON-RPC batch when fetching headers.
    #[arg(long, default_value_t = DEFAULT_BLOCK_BATCH_SIZE)]
    batch_size: usize,

    /// Milliseconds to sleep between JSON-RPC header batches.
    #[arg(long, default_value_t = DEFAULT_BATCH_THROTTLE_MS)]
    batch_throttle_ms: u64,

    /// Resolve the block window and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug, Clone)]
struct BlockHeaderRow {
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
    dt: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.blocks == 0 {
        bail!("--blocks must be greater than 0");
    }
    if args.batch_size == 0 {
        bail!("--batch-size must be greater than 0");
    }
    if args.part_blocks == 0 {
        bail!("--part-blocks must be greater than 0");
    }

    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    let checkpoint_path = if let Some(path) = args.checkpoint.clone() {
        path
    } else {
        checkpoint_path_with_suffix(&data_root, COLLECTOR, args.checkpoint_suffix.as_deref())?
    };
    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-block-header-sample/0.1")
        .build()
        .context("failed to build HTTP client")?;

    let rpc_urls = RpcUrlPool::from_values(&args.rpc_url, DEFAULT_RPC_URL)?;
    let latest_block =
        rpc_call_hex_u64_from_pool(&client, &rpc_urls, "eth_blockNumber", json!([]))?;
    let checkpoint = if args.resume && args.from_block.is_none() && checkpoint_path.exists() {
        let checkpoint = load_checkpoint(&checkpoint_path)?;
        validate_checkpoint_identity(&checkpoint, COLLECTOR, CHAIN, "", "")?;
        Some(checkpoint)
    } else {
        None
    };
    let range = resolve_block_range(
        args.blocks,
        latest_block,
        args.from_block,
        args.to_block,
        args.resume,
        checkpoint.as_ref(),
    )?;

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DATASET}");
        println!("block window: {}..{}", range.from_block, range.to_block);
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        return Ok(());
    }

    let schema = header_schema();
    write_schema_metadata(&data_root, DATASET, schema.as_ref(), &["dt"])?;

    let mut output_parts = Vec::new();
    let mut rows_written = 0u64;
    let mut chunks_completed = 0u64;
    let mut start = range.from_block;
    while start <= range.to_block {
        let end = range
            .to_block
            .min(start.saturating_add(args.part_blocks - 1));
        let block_numbers = (start..=end).collect::<Vec<_>>();
        let rows = fetch_headers_with_retry(
            &client,
            &rpc_urls,
            &block_numbers,
            &fetched_at,
            args.batch_size,
            args.batch_throttle_ms,
        )?;

        let parts = write_header_parts(&data_root, schema.clone(), &rows, start, end)?;
        rows_written += parts
            .iter()
            .filter(|part| part.status == PartWriteStatus::Written)
            .map(|part| part.rows as u64)
            .sum::<u64>();
        output_parts.extend(parts);
        chunks_completed += 1;

        let checkpoint = Checkpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: String::new(),
            from_block: range.from_block,
            to_block: range.to_block,
            last_completed_block: end,
            rows_written,
            output: part_paths_to_string(&output_parts),
            updated_at_utc: utc_now_string(),
        };
        save_checkpoint(&checkpoint_path, &checkpoint)?;

        if end == u64::MAX {
            break;
        }
        start = end + 1;
    }

    let finished_at = utc_now_string();
    let status = if range.is_empty() {
        "empty"
    } else {
        "completed"
    };
    write_collection_run_parquet(
        &data_root,
        &ChogCollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: String::new(),
            from_block: Some(range.from_block),
            to_block: Some(range.to_block),
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed,
            status: status.to_string(),
            error: String::new(),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    println!("block window: {}..{}", range.from_block, range.to_block);
    println!("headers written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());

    Ok(())
}

fn fetch_headers_with_retry(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    block_numbers: &[u64],
    fetched_at: &str,
    batch_size: usize,
    batch_throttle_ms: u64,
) -> Result<Vec<BlockHeaderRow>> {
    let mut last_error = None;
    let max_attempts = MAX_RETRIES * rpc_urls.len();
    for attempt in 1..=max_attempts {
        match fetch_headers(
            client,
            rpc_urls,
            block_numbers,
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
    Err(last_error.unwrap_or_else(|| anyhow!("block header batch fetch failed without an error")))
}

fn fetch_headers(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    block_numbers: &[u64],
    fetched_at: &str,
    batch_size: usize,
    batch_throttle_ms: u64,
) -> Result<Vec<BlockHeaderRow>> {
    if block_numbers.is_empty() {
        return Ok(Vec::new());
    }

    let mut rows = Vec::with_capacity(block_numbers.len());
    for (index, batch) in block_numbers.chunks(batch_size).enumerate() {
        if index > 0 && batch_throttle_ms > 0 {
            sleep(Duration::from_millis(batch_throttle_ms));
        }
        rows.extend(fetch_header_batch(
            client,
            rpc_urls.next_url(),
            batch,
            fetched_at,
        )?);
    }
    Ok(rows)
}

fn fetch_header_batch(
    client: &Client,
    rpc_url: &str,
    block_numbers: &[u64],
    fetched_at: &str,
) -> Result<Vec<BlockHeaderRow>> {
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
        rows.push(parse_header(*block_number, block, fetched_at)?);
    }
    Ok(rows)
}

fn parse_header(block_number: u64, block: RpcBlock, fetched_at: &str) -> Result<BlockHeaderRow> {
    let parsed_block_number = block
        .number
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?
        .unwrap_or(block_number);
    let block_timestamp = parse_hex_u64(&block.timestamp)?;
    let dt = dt_from_timestamp(block_timestamp)?;
    Ok(BlockHeaderRow {
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
        dt,
    })
}

fn header_schema() -> SchemaRef {
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
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn write_header_parts(
    data_root: &std::path::Path,
    schema: SchemaRef,
    rows: &[BlockHeaderRow],
    from_block: u64,
    to_block: u64,
) -> Result<Vec<PartWrite>> {
    let mut by_dt = std::collections::BTreeMap::<String, Vec<BlockHeaderRow>>::new();
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
                string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
            ],
        )?;
        parts.push(write_parquet_part(
            &rpc_part_path(data_root, DATASET, &dt, COLLECTOR, from_block, to_block),
            schema.clone(),
            batch,
        )?);
    }
    Ok(parts)
}

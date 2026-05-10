use std::path::PathBuf;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use clap::Parser;
use finance_chain_core::rpc::{RpcBatchItem, RpcBlock, RpcUrlPool, rpc_batch_items, to_hex};
use finance_chain_core::storage::{
    CHECKPOINT_VERSION, Checkpoint, CollectionRunRecord, checkpoint_path_with_suffix,
    part_paths_to_string, save_checkpoint, utc_now_string, write_collection_run_parquet,
};
use mon_usdc_collectors::{
    CHAIN, DEFAULT_RPC_URL, EVENT_HEADERS_DATASET, count_written_rows, default_data_root_path,
    discover_swap_event_blocks, event_header_row_from_block, existing_event_header_blocks,
    resolve_rpc_urls, write_event_header_parts,
};
use reqwest::blocking::Client;
use serde_json::{Value, json};

const COLLECTOR: &str = "mon_usdc_event_header_sample";
const DEFAULT_BATCH_SIZE: usize = 200;
const MAX_RETRIES: usize = 3;

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_event_header_sample",
    about = "Fetch block headers for locally observed MON/USDC swap event blocks."
)]
struct Args {
    #[arg(long = "rpc-url")]
    rpc_url: Vec<String>,

    /// Local env file used only for RPC URL discovery.
    #[arg(long, default_value = ".env.chog.local")]
    env_file: PathBuf,

    /// MON/USDC v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Optional first event block to consider.
    #[arg(long)]
    from_block: Option<u64>,

    /// Optional final event block to consider.
    #[arg(long)]
    to_block: Option<u64>,

    /// Block headers per JSON-RPC batch.
    #[arg(long, default_value_t = DEFAULT_BATCH_SIZE)]
    batch_size: usize,

    /// Milliseconds to sleep between batches.
    #[arg(long, default_value_t = 0)]
    batch_throttle_ms: u64,

    /// Suffix for the default checkpoint filename.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Resolve local event blocks and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.batch_size == 0 {
        bail!("--batch-size must be greater than 0");
    }
    if let (Some(from), Some(to)) = (args.from_block, args.to_block) {
        if from > to {
            bail!("--from-block {from} is greater than --to-block {to}");
        }
    }

    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    let checkpoint_path =
        checkpoint_path_with_suffix(&data_root, COLLECTOR, args.checkpoint_suffix.as_deref())?;
    let event_blocks = discover_swap_event_blocks(&data_root, args.from_block, args.to_block)?;
    let existing_blocks = existing_event_header_blocks(&data_root)?;
    let missing_blocks = event_blocks
        .keys()
        .filter(|block| !existing_blocks.contains(block))
        .copied()
        .collect::<Vec<_>>();

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {EVENT_HEADERS_DATASET}");
        println!("unique swap event blocks: {}", event_blocks.len());
        println!("existing event headers: {}", existing_blocks.len());
        println!("missing event headers: {}", missing_blocks.len());
        println!(
            "estimated RPC batches: {}",
            missing_blocks.len().div_ceil(args.batch_size)
        );
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        return Ok(());
    }

    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let client = Client::builder()
        .timeout(Duration::from_secs(45))
        .user_agent("finance-chain-mon-usdc-event-header/0.1")
        .build()
        .context("failed to build HTTP client")?;
    let rpc_urls = RpcUrlPool::from_values(
        &resolve_rpc_urls(&args.rpc_url, &args.env_file),
        DEFAULT_RPC_URL,
    )?;
    let total_batches = missing_blocks.len().div_ceil(args.batch_size);
    let mut output_parts = Vec::new();
    let mut rows_written = 0u64;
    let mut chunks_completed = 0u64;
    let checkpoint_from_block = args
        .from_block
        .or_else(|| event_blocks.keys().next().copied())
        .unwrap_or(0);
    let checkpoint_to_block = args
        .to_block
        .or_else(|| event_blocks.keys().next_back().copied())
        .unwrap_or(0);

    for (index, batch_blocks) in missing_blocks.chunks(args.batch_size).enumerate() {
        if index > 0 && args.batch_throttle_ms > 0 {
            sleep(Duration::from_millis(args.batch_throttle_ms));
        }
        let blocks = fetch_block_batch(&client, &rpc_urls, batch_blocks)?;
        let mut batch_rows = Vec::with_capacity(blocks.len());
        for (block_number, block) in batch_blocks.iter().copied().zip(blocks) {
            let stats = event_blocks
                .get(&block_number)
                .ok_or_else(|| anyhow!("missing event stats for block {block_number}"))?;
            batch_rows.push(event_header_row_from_block(
                &fetched_at,
                block_number,
                block,
                stats,
            )?);
        }
        let parts = write_event_header_parts(&data_root, &batch_rows)?;
        let batch_rows_written = count_written_rows(&parts);
        let batch_parts = parts.len();
        rows_written += batch_rows_written;
        output_parts.extend(parts);
        chunks_completed += 1;

        let batch_min_block = batch_blocks.iter().copied().min().unwrap_or(0);
        let batch_max_block = batch_blocks.iter().copied().max().unwrap_or(0);
        let finished_batch_at = utc_now_string();
        let checkpoint = Checkpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: EVENT_HEADERS_DATASET.to_string(),
            from_block: checkpoint_from_block,
            to_block: checkpoint_to_block,
            last_completed_block: batch_max_block,
            rows_written,
            output: part_paths_to_string(&output_parts),
            updated_at_utc: finished_batch_at,
        };
        save_checkpoint(&checkpoint_path, &checkpoint)?;

        let remaining = missing_blocks
            .len()
            .saturating_sub((index + 1) * args.batch_size);
        println!(
            "batch {}/{} blocks {}..{} rows={} parts={} written_total={} remaining={}",
            index + 1,
            total_batches,
            batch_min_block,
            batch_max_block,
            batch_rows.len(),
            batch_parts,
            rows_written,
            remaining
        );
    }
    let finished_at = utc_now_string();
    if chunks_completed == 0 {
        let checkpoint = Checkpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: EVENT_HEADERS_DATASET.to_string(),
            from_block: checkpoint_from_block,
            to_block: checkpoint_to_block,
            last_completed_block: checkpoint_to_block,
            rows_written,
            output: part_paths_to_string(&output_parts),
            updated_at_utc: finished_at.clone(),
        };
        save_checkpoint(&checkpoint_path, &checkpoint)?;
    }
    write_collection_run_parquet(
        &data_root,
        &CollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: EVENT_HEADERS_DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: EVENT_HEADERS_DATASET.to_string(),
            from_block: args.from_block,
            to_block: args.to_block,
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed,
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

    println!("unique swap event blocks: {}", event_blocks.len());
    println!("missing event headers fetched: {}", missing_blocks.len());
    println!("event headers written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    Ok(())
}

fn fetch_block_batch(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    blocks: &[u64],
) -> Result<Vec<RpcBlock>> {
    let params = blocks
        .iter()
        .map(|block| json!([to_hex(*block), false]))
        .collect::<Vec<Value>>();
    let mut last_error = None;
    for attempt in 1..=MAX_RETRIES * rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_batch_items(client, rpc_url, "eth_getBlockByNumber", &params) {
            Ok(items) => return parse_block_batch_items(items),
            Err(error) => {
                last_error = Some(error);
                if attempt < MAX_RETRIES * rpc_urls.len() {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("eth_getBlockByNumber batch failed without error")))
}

fn parse_block_batch_items(items: Vec<RpcBatchItem>) -> Result<Vec<RpcBlock>> {
    let mut blocks = Vec::with_capacity(items.len());
    for item in items {
        match item {
            RpcBatchItem::Result(value) => {
                if value.is_null() {
                    bail!("eth_getBlockByNumber returned null block");
                }
                blocks.push(serde_json::from_value::<RpcBlock>(value)?);
            }
            RpcBatchItem::Error(error) => bail!("eth_getBlockByNumber batch item failed: {error}"),
        }
    }
    Ok(blocks)
}

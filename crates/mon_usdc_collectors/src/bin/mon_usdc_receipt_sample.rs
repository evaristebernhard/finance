use std::path::PathBuf;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use clap::Parser;
use finance_chain_core::rpc::{RpcBatchItem, RpcUrlPool, rpc_batch_items};
use finance_chain_core::storage::{
    CHECKPOINT_VERSION, Checkpoint, CollectionRunRecord, checkpoint_path_with_suffix,
    part_paths_to_string, save_checkpoint, utc_now_string, write_collection_run_parquet,
};
use mon_usdc_collectors::{
    CHAIN, DEFAULT_RPC_URL, TX_RECEIPTS_DATASET, collect_receipt_queue, count_written_rows,
    default_data_root_path, read_event_header_timestamps, receipt_row_from_rpc, resolve_rpc_urls,
    write_receipt_parts,
};
use reqwest::blocking::Client;
use serde_json::{Value, json};

const COLLECTOR: &str = "mon_usdc_receipt_sample";
const DEFAULT_BATCH_SIZE: usize = 250;
const DEFAULT_RPC_BATCH_SIZE: usize = 50;
const MAX_RETRIES: usize = 3;

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_receipt_sample",
    about = "Fetch receipt-only gas/status rows for MON/USDC swap transactions."
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

    /// Only source swap transaction hashes from blocks at or after this block.
    #[arg(long)]
    from_block: Option<u64>,

    /// Only source swap transaction hashes from blocks at or before this block.
    #[arg(long)]
    to_block: Option<u64>,

    /// Accepted for parity with CHOG. MON/USDC receipts are always sourced from data root.
    #[arg(long)]
    from_data_root: bool,

    /// Maximum hashes to collect after existing-receipt dedupe.
    #[arg(long)]
    max_txs: Option<usize>,

    /// Zero-based receipt queue shard index.
    #[arg(long)]
    shard_index: Option<usize>,

    /// Total receipt queue shard count.
    #[arg(long)]
    shard_count: Option<usize>,

    /// Hashes per deterministic output part.
    #[arg(long, default_value_t = DEFAULT_BATCH_SIZE)]
    batch_size: usize,

    /// Hashes per JSON-RPC batch.
    #[arg(long, default_value_t = DEFAULT_RPC_BATCH_SIZE)]
    rpc_batch_size: usize,

    /// Receipt-only mode is the default and current V1 behavior.
    #[arg(long)]
    receipt_only: bool,

    /// Suffix for the default checkpoint filename.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Resolve queue and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.batch_size == 0 {
        bail!("--batch-size must be greater than 0");
    }
    if args.rpc_batch_size == 0 {
        bail!("--rpc-batch-size must be greater than 0");
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
    let (mut queue, local_metadata) =
        collect_receipt_queue(&data_root, args.from_block, args.to_block)?;
    if args.shard_index.is_some() != args.shard_count.is_some() {
        bail!("--shard-index and --shard-count must be supplied together");
    }
    if let (Some(shard_index), Some(shard_count)) = (args.shard_index, args.shard_count) {
        if shard_count == 0 {
            bail!("--shard-count must be greater than 0");
        }
        if shard_index >= shard_count {
            bail!("--shard-index must be less than --shard-count");
        }
        queue = queue
            .into_iter()
            .filter(|hash| stable_shard_index(hash, shard_count) == shard_index)
            .collect();
    }
    if let Some(max_txs) = args.max_txs {
        queue.truncate(max_txs);
    }

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {TX_RECEIPTS_DATASET}");
        println!("receipt only: true");
        if args.from_block.is_some() || args.to_block.is_some() {
            println!(
                "block window: {}..{}",
                args.from_block
                    .map(|block| block.to_string())
                    .unwrap_or_else(|| "start".to_string()),
                args.to_block
                    .map(|block| block.to_string())
                    .unwrap_or_else(|| "end".to_string())
            );
        }
        println!("queued hashes after dedupe: {}", queue.len());
        if let (Some(shard_index), Some(shard_count)) = (args.shard_index, args.shard_count) {
            println!("queue shard: {shard_index}/{shard_count} (stable-hash)");
        }
        println!("rpc batch size: {}", args.rpc_batch_size);
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        return Ok(());
    }

    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let event_header_timestamps = read_event_header_timestamps(&data_root)?;
    let client = Client::builder()
        .timeout(Duration::from_secs(45))
        .user_agent("finance-chain-mon-usdc-receipt-sample/0.1")
        .build()
        .context("failed to build HTTP client")?;
    let rpc_urls = RpcUrlPool::from_values(
        &resolve_rpc_urls(&args.rpc_url, &args.env_file),
        DEFAULT_RPC_URL,
    )?;

    let mut output_parts = Vec::new();
    let mut rows_written = 0u64;
    let mut chunks_completed = 0u64;
    for batch_hashes in queue.chunks(args.batch_size) {
        let mut rows = Vec::new();
        for rpc_hashes in batch_hashes.chunks(args.rpc_batch_size) {
            let items = fetch_receipt_items(&client, &rpc_urls, rpc_hashes)?;
            for (hash, item) in rpc_hashes.iter().zip(items) {
                let (value, error) = match item {
                    RpcBatchItem::Result(value) => (value, None),
                    RpcBatchItem::Error(error) => (Value::Null, Some(error)),
                };
                rows.push(receipt_row_from_rpc(
                    &fetched_at,
                    hash,
                    value,
                    error,
                    local_metadata.get(hash),
                    &event_header_timestamps,
                )?);
            }
        }
        let parts = write_receipt_parts(&data_root, &rows, batch_hashes)?;
        rows_written += count_written_rows(&parts);
        output_parts.extend(parts);
        chunks_completed += 1;
    }

    let finished_at = utc_now_string();
    let checkpoint = Checkpoint {
        version: CHECKPOINT_VERSION,
        collector: COLLECTOR.to_string(),
        chain: CHAIN.to_string(),
        address: String::new(),
        topic0: String::new(),
        from_block: args.from_block.unwrap_or(0),
        to_block: args.to_block.unwrap_or(0),
        last_completed_block: args.to_block.unwrap_or(0),
        rows_written,
        output: part_paths_to_string(&output_parts),
        updated_at_utc: finished_at.clone(),
    };
    save_checkpoint(&checkpoint_path, &checkpoint)?;
    write_collection_run_parquet(
        &data_root,
        &CollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: TX_RECEIPTS_DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: String::new(),
            from_block: args.from_block,
            to_block: args.to_block,
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed,
            status: if queue.is_empty() {
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

    println!("receipt rows written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    Ok(())
}

fn stable_shard_index(hash: &str, shard_count: usize) -> usize {
    let mut value = 0xcbf29ce484222325u64;
    for byte in hash.bytes() {
        value ^= u64::from(byte.to_ascii_lowercase());
        value = value.wrapping_mul(0x100000001b3);
    }
    (value % shard_count as u64) as usize
}

fn fetch_receipt_items(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    hashes: &[String],
) -> Result<Vec<RpcBatchItem>> {
    let params = hashes
        .iter()
        .map(|hash| json!([hash]))
        .collect::<Vec<Value>>();
    let mut last_error = None;
    for attempt in 1..=MAX_RETRIES * rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_batch_items(client, rpc_url, "eth_getTransactionReceipt", &params) {
            Ok(items) => return Ok(items),
            Err(error) => {
                last_error = Some(error);
                if attempt < MAX_RETRIES * rpc_urls.len() {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }

    let batch_error = last_error
        .map(|error| format!("{error:#}"))
        .unwrap_or_else(|| "batch failed without error".to_string());
    let mut items = Vec::with_capacity(hashes.len());
    for hash in hashes {
        let single = vec![json!([hash])];
        let mut single_error = None;
        let mut value = None;
        for _ in 0..rpc_urls.len() {
            let rpc_url = rpc_urls.next_url();
            match rpc_batch_items(client, rpc_url, "eth_getTransactionReceipt", &single) {
                Ok(mut items) => {
                    value = items.pop();
                    break;
                }
                Err(error) => single_error = Some(error),
            }
        }
        items.push(value.unwrap_or_else(|| {
            RpcBatchItem::Error(
                single_error
                    .map(|error| format!("{error:#}"))
                    .unwrap_or_else(|| batch_error.clone()),
            )
        }));
    }
    Ok(items)
}

#[cfg(test)]
mod tests {
    use super::stable_shard_index;

    #[test]
    fn stable_shard_index_is_case_insensitive_and_bounded() {
        let lower = "0x0123456789abcdef";
        let upper = "0x0123456789ABCDEF";
        assert_eq!(stable_shard_index(lower, 4), stable_shard_index(upper, 4));
        assert!(stable_shard_index(lower, 4) < 4);
    }
}

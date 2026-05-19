use std::fs;
use std::path::PathBuf;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use clap::Parser;
use finance_chain_core::rpc::{RpcBatchItem, RpcUrlPool, rpc_batch_items};
use finance_chain_core::storage::{
    CHECKPOINT_VERSION, Checkpoint, CollectionRunRecord, checkpoint_path_with_suffix,
    ensure_parent_dir, part_paths_to_string, save_checkpoint, utc_now_string,
    write_collection_run_parquet,
};
use mon_usdc_collectors::enrichment::{
    DEBUG_TRACE_SUMMARIES_DATASET, apply_stable_tx_shard, collect_trace_queue,
    debug_trace_rows_from_rpc, write_debug_trace_parts,
};
use mon_usdc_collectors::{
    CHAIN, DEFAULT_RPC_URL, count_written_rows, default_data_root_path, resolve_rpc_urls,
};
use reqwest::blocking::Client;
use serde_json::{Value, json};

const COLLECTOR: &str = "mon_usdc_trace_sample";
const DEFAULT_BATCH_SIZE: usize = 50;
const DEFAULT_RPC_BATCH_SIZE: usize = 1;
const DEFAULT_MAX_TXS: usize = 25_000;
const MAX_RETRIES: usize = 2;

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_trace_sample",
    about = "Sample debug_traceTransaction callTracer paths for MON/USDC swap transactions."
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

    /// Maximum trace candidate txs before sharding.
    #[arg(long, default_value_t = DEFAULT_MAX_TXS)]
    max_txs: usize,

    /// Zero-based queue shard index.
    #[arg(long)]
    shard_index: Option<usize>,

    /// Total queue shard count.
    #[arg(long)]
    shard_count: Option<usize>,

    /// Hashes per deterministic output part.
    #[arg(long, default_value_t = DEFAULT_BATCH_SIZE)]
    batch_size: usize,

    /// Hashes per JSON-RPC batch. Trace defaults to 1.
    #[arg(long, default_value_t = DEFAULT_RPC_BATCH_SIZE)]
    rpc_batch_size: usize,

    /// Save full callTracer JSON under data_root/_local_debug_traces for local debugging.
    #[arg(long)]
    save_raw_json_local: bool,

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
    let (queue, metadata) =
        collect_trace_queue(&data_root, args.from_block, args.to_block, args.max_txs)?;
    let queue = apply_stable_tx_shard(queue, args.shard_index, args.shard_count)?;

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DEBUG_TRACE_SUMMARIES_DATASET}");
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
        println!(
            "queued hashes after candidate selection/dedupe: {}",
            queue.len()
        );
        if let (Some(shard_index), Some(shard_count)) = (args.shard_index, args.shard_count) {
            println!("queue shard: {shard_index}/{shard_count} (stable-hash)");
        }
        println!("rpc batch size: {}", args.rpc_batch_size);
        println!("save raw json local: {}", args.save_raw_json_local);
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        return Ok(());
    }

    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let client = Client::builder()
        .timeout(Duration::from_secs(120))
        .user_agent("finance-chain-mon-usdc-trace-sample/0.1")
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
        let mut summaries = Vec::new();
        let mut calls = Vec::new();
        for rpc_hashes in batch_hashes.chunks(args.rpc_batch_size) {
            let items = fetch_trace_items(&client, &rpc_urls, rpc_hashes)?;
            for (hash, item) in rpc_hashes.iter().zip(items) {
                let (value, error) = match item {
                    RpcBatchItem::Result(value) => (value, None),
                    RpcBatchItem::Error(error) => (Value::Null, Some(error)),
                };
                if args.save_raw_json_local && error.is_none() {
                    save_raw_trace_json(&data_root, hash, &value)?;
                }
                let (summary, mut call_rows) =
                    debug_trace_rows_from_rpc(&fetched_at, hash, value, error, metadata.get(hash))?;
                summaries.push(summary);
                calls.append(&mut call_rows);
            }
        }
        let parts = write_debug_trace_parts(&data_root, &summaries, &calls, batch_hashes)?;
        rows_written += count_written_rows(&parts);
        output_parts.extend(parts);
        chunks_completed += 1;
    }

    let finished_at = utc_now_string();
    save_checkpoint(
        &checkpoint_path,
        &Checkpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: DEBUG_TRACE_SUMMARIES_DATASET.to_string(),
            from_block: args.from_block.unwrap_or(0),
            to_block: args.to_block.unwrap_or(0),
            last_completed_block: args.to_block.unwrap_or(0),
            rows_written,
            output: part_paths_to_string(&output_parts),
            updated_at_utc: finished_at.clone(),
        },
    )?;
    write_collection_run_parquet(
        &data_root,
        &CollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DEBUG_TRACE_SUMMARIES_DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: DEBUG_TRACE_SUMMARIES_DATASET.to_string(),
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

    println!("debug trace rows written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    Ok(())
}

fn fetch_trace_items(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    hashes: &[String],
) -> Result<Vec<RpcBatchItem>> {
    let params = hashes
        .iter()
        .map(|hash| json!([hash, { "tracer": "callTracer", "timeout": "20s" }]))
        .collect::<Vec<Value>>();
    let mut last_error = None;
    for attempt in 1..=MAX_RETRIES * rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_batch_items(client, rpc_url, "debug_traceTransaction", &params) {
            Ok(items) => return Ok(items),
            Err(error) => {
                last_error = Some(error);
                if attempt < MAX_RETRIES * rpc_urls.len() {
                    sleep(Duration::from_millis(1_000 * attempt as u64));
                }
            }
        }
    }
    let batch_error = last_error
        .map(|error| format!("{error:#}"))
        .unwrap_or_else(|| "batch failed without error".to_string());
    Ok(hashes
        .iter()
        .map(|_| RpcBatchItem::Error(batch_error.clone()))
        .collect())
}

fn save_raw_trace_json(data_root: &std::path::Path, hash: &str, value: &Value) -> Result<()> {
    let path = data_root
        .join("_local_debug_traces")
        .join(format!("{}.json", hash.trim_start_matches("0x")));
    ensure_parent_dir(&path)?;
    fs::write(&path, serde_json::to_vec_pretty(value)?)
        .with_context(|| format!("failed to write {}", path.display()))
}

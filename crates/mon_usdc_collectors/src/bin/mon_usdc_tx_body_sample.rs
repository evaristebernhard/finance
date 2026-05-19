use std::collections::BTreeMap;
use std::fs::File;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, mpsc};
use std::thread::{self, sleep};
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail};
use clap::Parser;
use finance_chain_core::rpc::{RpcBatchItem, RpcUrlPool, rpc_batch_items};
use finance_chain_core::storage::{
    CHECKPOINT_VERSION, CollectionRunRecord, PartWrite, checkpoint_path_with_suffix,
    ensure_parent_dir, part_paths_to_string, utc_now_string, write_collection_run_parquet,
    write_schema_metadata,
};
use mon_usdc_collectors::enrichment::{
    TX_BODIES_DATASET, TxSourceMetadata, apply_stable_tx_shard, collect_tx_body_queue_cached,
    tx_body_row_from_rpc, tx_body_schema, write_tx_body_parts,
};
use mon_usdc_collectors::{
    CHAIN, DEFAULT_RPC_URL, count_written_rows, default_data_root_path, resolve_rpc_urls,
};
use reqwest::blocking::Client;
use serde::Serialize;
use serde_json::{Value, json};

const COLLECTOR: &str = "mon_usdc_tx_body_sample";
const DEFAULT_BATCH_SIZE: usize = 250;
const DEFAULT_RPC_BATCH_SIZE: usize = 50;
const MAX_RETRIES: usize = 3;

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_tx_body_sample",
    about = "Fetch eth_getTransactionByHash bodies for MON/USDC swap transactions."
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

    /// Maximum hashes to collect after existing-body dedupe.
    #[arg(long)]
    max_txs: Option<usize>,

    /// Zero-based queue shard index.
    #[arg(long)]
    shard_index: Option<usize>,

    /// Total queue shard count.
    #[arg(long)]
    shard_count: Option<usize>,

    /// Hashes per deterministic output part.
    #[arg(long, default_value_t = DEFAULT_BATCH_SIZE)]
    batch_size: usize,

    /// Hashes per JSON-RPC batch.
    #[arg(long, default_value_t = DEFAULT_RPC_BATCH_SIZE)]
    rpc_batch_size: usize,

    /// Number of in-process workers. Each worker owns its own HTTP client and RPC URL rotation.
    #[arg(long, default_value_t = 1)]
    workers: usize,

    /// Rebuild the cached source queue under data_root/_work before applying output dedupe.
    #[arg(long)]
    refresh_queue_cache: bool,

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
    if args.workers == 0 {
        bail!("--workers must be greater than 0");
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
    let queue_info = collect_tx_body_queue_cached(
        &data_root,
        args.from_block,
        args.to_block,
        args.refresh_queue_cache,
    )?;
    let cache_path = queue_info.cache_path.clone();
    let cache_status = queue_info.cache_status;
    let source_count = queue_info.source_count;
    let existing_count = queue_info.existing_count;
    let metadata = queue_info.metadata;
    let mut queue = apply_stable_tx_shard(queue_info.queue, args.shard_index, args.shard_count)?;
    if let Some(max_txs) = args.max_txs {
        queue.truncate(max_txs);
    }

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {TX_BODIES_DATASET}");
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
        println!("source swap txs in cache: {}", source_count);
        println!("existing tx body hashes: {}", existing_count);
        println!("queued hashes after dedupe: {}", queue.len());
        if let (Some(shard_index), Some(shard_count)) = (args.shard_index, args.shard_count) {
            println!("queue shard: {shard_index}/{shard_count} (stable-hash)");
        }
        println!(
            "queue cache: {} {}",
            cache_status.as_str(),
            cache_path.display()
        );
        println!("workers: {}", args.workers);
        println!("batch size: {}", args.batch_size);
        println!("rpc batch size: {}", args.rpc_batch_size);
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        return Ok(());
    }

    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let rpc_values = resolve_rpc_urls(&args.rpc_url, &args.env_file);
    let chunks = build_tx_chunks(&queue, args.batch_size);
    let total_chunks = chunks.len() as u64;
    let total_queued = queue.len() as u64;

    if !queue.is_empty() {
        let schema = tx_body_schema();
        write_schema_metadata(&data_root, TX_BODIES_DATASET, schema.as_ref(), &["dt"])?;
    }

    let mut output_parts = Vec::<PartWrite>::new();
    let mut rows_written = 0u64;
    let mut failed_rows = 0u64;
    let mut chunks_completed = 0u64;
    let mut hashes_completed = 0u64;
    let mut fatal_errors = Vec::<String>::new();
    let run_started = Instant::now();

    if !chunks.is_empty() {
        let assignments = assign_chunks_to_workers(chunks, args.workers);
        let metadata = Arc::new(metadata);
        let worker_status = Arc::new(Mutex::new(vec!["idle".to_string(); args.workers]));
        let (sender, receiver) = mpsc::channel::<WorkerMessage>();
        let mut handles = Vec::new();
        for (worker_id, chunks) in assignments.into_iter().enumerate() {
            let sender = sender.clone();
            let data_root = data_root.clone();
            let fetched_at = fetched_at.clone();
            let rpc_values = rpc_values.clone();
            let metadata = Arc::clone(&metadata);
            let worker_status = Arc::clone(&worker_status);
            let rpc_batch_size = args.rpc_batch_size;
            handles.push(thread::spawn(move || {
                run_worker(WorkerConfig {
                    worker_id,
                    data_root,
                    fetched_at,
                    rpc_values,
                    rpc_batch_size,
                    metadata,
                    chunks,
                    worker_status,
                    sender,
                });
            }));
        }
        drop(sender);

        println!(
            "collecting {} tx bodies across {} chunks with {} workers",
            total_queued, total_chunks, args.workers
        );
        print_progress(
            total_queued,
            hashes_completed,
            rows_written,
            failed_rows,
            chunks_completed,
            total_chunks,
            run_started,
            &worker_status,
        );
        let mut last_progress = Instant::now();
        loop {
            match receiver.recv_timeout(Duration::from_secs(5)) {
                Ok(WorkerMessage::Chunk(report)) => {
                    hashes_completed += report.hash_count as u64;
                    rows_written += report.rows_written;
                    failed_rows += report.failed_rows;
                    chunks_completed += 1;
                    output_parts.extend(report.output_parts);
                    if chunks_completed <= args.workers as u64
                        || chunks_completed == total_chunks
                        || last_progress.elapsed() >= Duration::from_secs(30)
                    {
                        println!(
                            "worker {} completed chunk {} ({} hashes, {:.2}s)",
                            report.worker_id,
                            report.chunk_index,
                            report.hash_count,
                            report.elapsed_secs
                        );
                        print_progress(
                            total_queued,
                            hashes_completed,
                            rows_written,
                            failed_rows,
                            chunks_completed,
                            total_chunks,
                            run_started,
                            &worker_status,
                        );
                        last_progress = Instant::now();
                    }
                }
                Ok(WorkerMessage::Fatal(error)) => {
                    failed_rows += error.hash_count as u64;
                    let message = format!(
                        "worker {} chunk {} failed: {}",
                        error.worker_id, error.chunk_index, error.error
                    );
                    println!("{message}");
                    fatal_errors.push(message);
                    if last_progress.elapsed() >= Duration::from_secs(30) {
                        print_progress(
                            total_queued,
                            hashes_completed,
                            rows_written,
                            failed_rows,
                            chunks_completed,
                            total_chunks,
                            run_started,
                            &worker_status,
                        );
                        last_progress = Instant::now();
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    if last_progress.elapsed() >= Duration::from_secs(30) {
                        print_progress(
                            total_queued,
                            hashes_completed,
                            rows_written,
                            failed_rows,
                            chunks_completed,
                            total_chunks,
                            run_started,
                            &worker_status,
                        );
                        last_progress = Instant::now();
                    }
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }

        for (worker_id, handle) in handles.into_iter().enumerate() {
            if handle.join().is_err() {
                let message = format!("worker {worker_id} panicked");
                println!("{message}");
                fatal_errors.push(message);
            }
        }
    }

    let finished_at = utc_now_string();
    let rows_per_sec = rows_per_sec(hashes_completed, run_started);
    save_tx_body_checkpoint(
        &checkpoint_path,
        &TxBodyCheckpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: TX_BODIES_DATASET.to_string(),
            from_block: args.from_block.unwrap_or(0),
            to_block: args.to_block.unwrap_or(0),
            last_completed_block: args.to_block.unwrap_or(0),
            rows_written,
            output: part_paths_to_string(&output_parts),
            updated_at_utc: finished_at.clone(),
            workers: args.workers as u64,
            queued: total_queued,
            written: rows_written,
            failed: failed_rows,
            rows_per_sec,
            completed_chunks: chunks_completed,
        },
    )?;
    write_collection_run_parquet(
        &data_root,
        &CollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: TX_BODIES_DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: TX_BODIES_DATASET.to_string(),
            from_block: args.from_block,
            to_block: args.to_block,
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed,
            status: if queue.is_empty() {
                "empty"
            } else if fatal_errors.is_empty() {
                "completed"
            } else {
                "failed"
            }
            .to_string(),
            error: fatal_errors.join(" | "),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    println!("tx body rows written: {rows_written}");
    println!("tx body failed rows: {failed_rows}");
    println!("completed chunks: {chunks_completed}/{total_chunks}");
    println!("rows/sec: {rows_per_sec:.2}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    if !fatal_errors.is_empty() {
        bail!(
            "tx body collection finished with {} worker/chunk errors",
            fatal_errors.len()
        );
    }
    Ok(())
}

#[derive(Debug, Clone)]
struct TxChunk {
    index: usize,
    hashes: Vec<String>,
}

#[derive(Debug)]
struct ChunkReport {
    worker_id: usize,
    chunk_index: usize,
    hash_count: usize,
    rows_written: u64,
    failed_rows: u64,
    elapsed_secs: f64,
    output_parts: Vec<PartWrite>,
}

#[derive(Debug)]
struct WorkerFatal {
    worker_id: usize,
    chunk_index: usize,
    hash_count: usize,
    error: String,
}

#[derive(Debug)]
enum WorkerMessage {
    Chunk(ChunkReport),
    Fatal(WorkerFatal),
}

struct WorkerConfig {
    worker_id: usize,
    data_root: PathBuf,
    fetched_at: String,
    rpc_values: Vec<String>,
    rpc_batch_size: usize,
    metadata: Arc<BTreeMap<String, TxSourceMetadata>>,
    chunks: Vec<TxChunk>,
    worker_status: Arc<Mutex<Vec<String>>>,
    sender: mpsc::Sender<WorkerMessage>,
}

#[derive(Debug, Serialize)]
struct TxBodyCheckpoint {
    version: u32,
    collector: String,
    chain: String,
    address: String,
    topic0: String,
    from_block: u64,
    to_block: u64,
    last_completed_block: u64,
    rows_written: u64,
    output: String,
    updated_at_utc: String,
    workers: u64,
    queued: u64,
    written: u64,
    failed: u64,
    rows_per_sec: f64,
    completed_chunks: u64,
}

fn build_tx_chunks(queue: &[String], batch_size: usize) -> Vec<TxChunk> {
    queue
        .chunks(batch_size)
        .enumerate()
        .map(|(index, hashes)| TxChunk {
            index,
            hashes: hashes.to_vec(),
        })
        .collect()
}

fn assign_chunks_to_workers(chunks: Vec<TxChunk>, workers: usize) -> Vec<Vec<TxChunk>> {
    let mut assignments = vec![Vec::new(); workers];
    for chunk in chunks {
        let worker_index = chunk.index % workers;
        assignments[worker_index].push(chunk);
    }
    assignments
}

fn run_worker(config: WorkerConfig) {
    if config.chunks.is_empty() {
        set_worker_status(&config.worker_status, config.worker_id, "idle");
        return;
    }
    set_worker_status(&config.worker_status, config.worker_id, "starting");
    let result = (|| -> Result<()> {
        let client = Client::builder()
            .timeout(Duration::from_secs(45))
            .user_agent("finance-chain-mon-usdc-tx-body/0.1")
            .build()
            .context("failed to build HTTP client")?;
        let rpc_urls = RpcUrlPool::from_values(&config.rpc_values, DEFAULT_RPC_URL)?;
        for chunk in &config.chunks {
            set_worker_status(
                &config.worker_status,
                config.worker_id,
                &format!("chunk {}", chunk.index),
            );
            match collect_chunk(&config, &client, &rpc_urls, chunk) {
                Ok(report) => {
                    if config.sender.send(WorkerMessage::Chunk(report)).is_err() {
                        return Ok(());
                    }
                }
                Err(error) => {
                    let fatal = WorkerFatal {
                        worker_id: config.worker_id,
                        chunk_index: chunk.index,
                        hash_count: chunk.hashes.len(),
                        error: format!("{error:#}"),
                    };
                    if config.sender.send(WorkerMessage::Fatal(fatal)).is_err() {
                        return Ok(());
                    }
                }
            }
        }
        Ok(())
    })();
    if let Err(error) = result {
        let _ = config.sender.send(WorkerMessage::Fatal(WorkerFatal {
            worker_id: config.worker_id,
            chunk_index: usize::MAX,
            hash_count: 0,
            error: format!("{error:#}"),
        }));
    }
    set_worker_status(&config.worker_status, config.worker_id, "done");
}

fn collect_chunk(
    config: &WorkerConfig,
    client: &Client,
    rpc_urls: &RpcUrlPool,
    chunk: &TxChunk,
) -> Result<ChunkReport> {
    let started = Instant::now();
    let mut rows = Vec::with_capacity(chunk.hashes.len());
    for rpc_hashes in chunk.hashes.chunks(config.rpc_batch_size) {
        let items = fetch_tx_items(client, rpc_urls, rpc_hashes)?;
        for (hash, item) in rpc_hashes.iter().zip(items) {
            let (value, error) = match item {
                RpcBatchItem::Result(value) => (value, None),
                RpcBatchItem::Error(error) => (Value::Null, Some(error)),
            };
            rows.push(tx_body_row_from_rpc(
                &config.fetched_at,
                hash,
                value,
                error,
                config.metadata.get(hash),
            )?);
        }
    }
    let failed_rows = rows.iter().filter(|row| row.request_status != "ok").count() as u64;
    let output_parts = write_tx_body_parts(&config.data_root, &rows, &chunk.hashes)?;
    let rows_written = count_written_rows(&output_parts);
    Ok(ChunkReport {
        worker_id: config.worker_id,
        chunk_index: chunk.index,
        hash_count: chunk.hashes.len(),
        rows_written,
        failed_rows,
        elapsed_secs: started.elapsed().as_secs_f64(),
        output_parts,
    })
}

fn set_worker_status(worker_status: &Arc<Mutex<Vec<String>>>, worker_id: usize, status: &str) {
    if let Ok(mut statuses) = worker_status.lock() {
        if let Some(slot) = statuses.get_mut(worker_id) {
            *slot = status.to_string();
        }
    }
}

fn print_progress(
    total_queued: u64,
    hashes_completed: u64,
    rows_written: u64,
    failed_rows: u64,
    chunks_completed: u64,
    total_chunks: u64,
    started: Instant,
    worker_status: &Arc<Mutex<Vec<String>>>,
) {
    let remaining = total_queued.saturating_sub(hashes_completed);
    let rows_per_sec = rows_per_sec(hashes_completed, started);
    let workers = worker_status
        .lock()
        .map(|statuses| {
            statuses
                .iter()
                .enumerate()
                .map(|(index, status)| format!("{index}:{status}"))
                .collect::<Vec<_>>()
                .join(", ")
        })
        .unwrap_or_else(|_| "unavailable".to_string());
    println!(
        "progress: completed={} remaining={} written={} failed={} chunks={}/{} rows/sec={:.2} workers=[{}]",
        hashes_completed,
        remaining,
        rows_written,
        failed_rows,
        chunks_completed,
        total_chunks,
        rows_per_sec,
        workers
    );
}

fn rows_per_sec(rows: u64, started: Instant) -> f64 {
    let elapsed = started.elapsed().as_secs_f64();
    if elapsed <= 0.0 {
        0.0
    } else {
        rows as f64 / elapsed
    }
}

fn save_tx_body_checkpoint(path: &PathBuf, checkpoint: &TxBodyCheckpoint) -> Result<()> {
    ensure_parent_dir(path)?;
    let file =
        File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, checkpoint)
        .with_context(|| format!("failed to write {}", path.display()))
}

fn fetch_tx_items(
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
        match rpc_batch_items(client, rpc_url, "eth_getTransactionByHash", &params) {
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
    Ok(hashes
        .iter()
        .map(|_| RpcBatchItem::Error(batch_error.clone()))
        .collect())
}

#[cfg(test)]
mod tests {
    use mon_usdc_collectors::enrichment::stable_shard_index;

    use super::*;

    #[test]
    fn shard_index_is_bounded() {
        assert!(stable_shard_index("0xabc", 4) < 4);
    }

    #[test]
    fn chunk_assignment_has_no_duplicates_or_gaps() {
        let queue = (0..10)
            .map(|index| format!("0x{index:064x}"))
            .collect::<Vec<_>>();
        let chunks = build_tx_chunks(&queue, 3);
        assert_eq!(chunks.len(), 4);

        let assignments = assign_chunks_to_workers(chunks, 3);
        assert_eq!(assignments.len(), 3);
        let mut seen = assignments
            .iter()
            .flat_map(|worker_chunks| worker_chunks.iter())
            .flat_map(|chunk| chunk.hashes.iter().cloned())
            .collect::<Vec<_>>();
        seen.sort();
        let mut expected = queue.clone();
        expected.sort();
        assert_eq!(seen, expected);

        let assigned_chunk_ids = assignments
            .iter()
            .flat_map(|worker_chunks| worker_chunks.iter().map(|chunk| chunk.index))
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(assigned_chunk_ids, [0, 1, 2, 3].into_iter().collect());
    }
}

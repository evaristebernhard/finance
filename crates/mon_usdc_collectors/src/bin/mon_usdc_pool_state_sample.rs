use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, mpsc};
use std::thread::{self, sleep};
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail};
use clap::{Parser, ValueEnum};
use finance_chain_core::dexscreener::PoolCandidate;
use finance_chain_core::rpc::{RpcBatchItem, RpcUrlPool, rpc_batch_items, to_hex};
use finance_chain_core::storage::{
    CHECKPOINT_VERSION, CollectionRunRecord, PartWrite, checkpoint_path_with_suffix,
    ensure_parent_dir, part_paths_to_string, utc_now_string, write_collection_run_parquet,
    write_schema_metadata,
};
use mon_usdc_collectors::enrichment::{
    POOL_LIQUIDITY_WINDOWS_DATASET, POOL_STATE_SAMPLES_DATASET, PoolLiquidityWindowRow,
    PoolStateCandidate, PoolStateSampleRow, collect_pool_state_candidates, encode_i24_call,
    encode_no_arg_call, encode_u24_call, existing_pool_state_keys, parse_lb_bin_result,
    parse_single_u256_result, parse_v3_slot0, parse_v3_tick_result, pool_liquidity_window_schema,
    pool_state_sample_schema, sample_dt_from_candidate, stable_shard_index, write_pool_state_parts,
};
use mon_usdc_collectors::{
    CHAIN, DEFAULT_RPC_URL, count_written_rows, default_data_root_path, resolve_rpc_urls,
    select_pools,
};
use reqwest::blocking::Client;
use serde::Serialize;
use serde_json::{Value, json};

const COLLECTOR: &str = "mon_usdc_pool_state_sample";
const DEFAULT_BATCH_SIZE: usize = 250;
const DEFAULT_RPC_BATCH_SIZE: usize = 25;
const DEFAULT_MAX_EVENT_BLOCKS: usize = 20_000;
const DEFAULT_WINDOW_RADIUS: i64 = 20;
const DEFAULT_FULL_CROSS_POOL_EVENT_BLOCKS: usize = 1_000;
const DEFAULT_WINDOW_EVENT_BLOCKS: usize = 1_000;
const MAX_RETRIES: usize = 3;

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
#[value(rename_all = "kebab-case")]
enum SamplingMode {
    Tiered,
    EventPool,
    AllPools,
}

impl SamplingMode {
    fn as_str(self) -> &'static str {
        match self {
            Self::Tiered => "tiered",
            Self::EventPool => "event-pool",
            Self::AllPools => "all-pools",
        }
    }
}

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_pool_state_sample",
    about = "Sample historical MON/USDC pool state around selected event blocks."
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

    /// Only source candidate event blocks at or after this block.
    #[arg(long)]
    from_block: Option<u64>,

    /// Only source candidate event blocks at or before this block.
    #[arg(long)]
    to_block: Option<u64>,

    /// Maximum unique event blocks to sample.
    #[arg(long, default_value_t = DEFAULT_MAX_EVENT_BLOCKS)]
    max_event_blocks: usize,

    /// Pool-state sampling strategy.
    #[arg(long, value_enum, default_value_t = SamplingMode::Tiered)]
    sampling_mode: SamplingMode,

    /// In tiered mode, sample all selected pools for the top N event blocks.
    #[arg(long, default_value_t = DEFAULT_FULL_CROSS_POOL_EVENT_BLOCKS)]
    full_cross_pool_event_blocks: usize,

    /// Sample liquidity windows only for the top N primary event-pool blocks.
    #[arg(long, default_value_t = DEFAULT_WINDOW_EVENT_BLOCKS)]
    window_event_blocks: usize,

    /// Maximum sample tasks after queue filtering.
    #[arg(long)]
    max_tasks: Option<usize>,

    /// Zero-based queue shard index.
    #[arg(long)]
    shard_index: Option<usize>,

    /// Total queue shard count.
    #[arg(long)]
    shard_count: Option<usize>,

    /// State tasks per deterministic output part.
    #[arg(long, default_value_t = DEFAULT_BATCH_SIZE)]
    batch_size: usize,

    /// eth_call requests per JSON-RPC batch.
    #[arg(long, default_value_t = DEFAULT_RPC_BATCH_SIZE)]
    rpc_batch_size: usize,

    /// Number of in-process workers. Each worker owns its own HTTP client and RPC URL rotation.
    #[arg(long, default_value_t = 1)]
    workers: usize,

    /// Ticks/bins to sample on each side of active tick/bin.
    #[arg(long, default_value_t = DEFAULT_WINDOW_RADIUS)]
    window_radius: i64,

    /// Suffix for the default checkpoint filename.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Resolve queue and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct PoolInfo {
    address: String,
    dex_id: String,
    family: String,
}

#[derive(Debug, Clone)]
struct OutputTask {
    candidate: PoolStateCandidate,
    pool: PoolInfo,
    sample_block_number: u64,
    sample_side: String,
    with_window: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct FetchKey {
    pool_address: String,
    sample_block_number: u64,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct ActiveStateResult {
    request_status: String,
    error: String,
    sqrt_price_x96: String,
    tick: String,
    liquidity: String,
    tick_spacing: String,
    active_id: String,
    bin_step: String,
    active_bin_reserve_x: String,
    active_bin_reserve_y: String,
}

#[derive(Debug, Clone)]
struct RankedEventBlock {
    rank: usize,
    primary: PoolStateCandidate,
}

#[derive(Debug, Clone, Default)]
struct TaskBuildStats {
    ranked_event_blocks: usize,
    candidate_event_rows: usize,
    full_cross_pool_blocks: usize,
    primary_only_blocks: usize,
    window_event_blocks: usize,
    state_tasks_before_existing_dedupe: usize,
    window_tasks_before_existing_dedupe: usize,
    state_tasks_after_existing_dedupe: usize,
    window_tasks_after_existing_dedupe: usize,
}

#[derive(Debug, Clone)]
struct TaskBuildPlan {
    tasks: Vec<OutputTask>,
    stats: TaskBuildStats,
}

#[derive(Debug, Clone)]
struct TaskChunk {
    index: usize,
    tasks: Vec<OutputTask>,
}

#[derive(Debug)]
struct ChunkReport {
    worker_id: usize,
    chunk_index: usize,
    state_task_count: usize,
    window_task_count: usize,
    rows_written: u64,
    failed_rows: u64,
    elapsed_secs: f64,
    output_parts: Vec<PartWrite>,
}

#[derive(Debug)]
struct WorkerFatal {
    worker_id: usize,
    chunk_index: usize,
    state_task_count: usize,
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
    window_radius: i64,
    chunks: Vec<TaskChunk>,
    worker_status: Arc<Mutex<Vec<String>>>,
    sender: mpsc::Sender<WorkerMessage>,
}

#[derive(Debug, Serialize)]
struct PoolStateCheckpoint {
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
    queued_state_tasks: u64,
    queued_window_tasks: u64,
    written: u64,
    failed: u64,
    rows_per_sec: f64,
    completed_chunks: u64,
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
    if args.window_radius < 0 {
        bail!("--window-radius must be greater than or equal to 0");
    }
    if let (Some(from), Some(to)) = (args.from_block, args.to_block) {
        if from > to {
            bail!("--from-block {from} is greater than --to-block {to}");
        }
    }
    if args.shard_index.is_some() != args.shard_count.is_some() {
        bail!("--shard-index and --shard-count must be supplied together");
    }

    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    let checkpoint_path =
        checkpoint_path_with_suffix(&data_root, COLLECTOR, args.checkpoint_suffix.as_deref())?;
    let candidates = collect_pool_state_candidates(
        &data_root,
        args.from_block,
        args.to_block,
        args.max_event_blocks,
    )?;
    let pools = select_pools(&data_root, &[], 4)?
        .into_iter()
        .map(pool_info)
        .collect::<Vec<_>>();
    let existing = existing_pool_state_keys(&data_root)?;
    let TaskBuildPlan { mut tasks, stats } = build_tasks(
        &candidates,
        &pools,
        &existing,
        args.sampling_mode,
        args.full_cross_pool_event_blocks,
        args.window_event_blocks,
    );
    if let (Some(shard_index), Some(shard_count)) = (args.shard_index, args.shard_count) {
        if shard_count == 0 {
            bail!("--shard-count must be greater than 0");
        }
        if shard_index >= shard_count {
            bail!("--shard-index must be less than --shard-count");
        }
        tasks.retain(|task| stable_shard_index(&output_key(task), shard_count) == shard_index);
    }
    if let Some(max_tasks) = args.max_tasks {
        tasks.truncate(max_tasks);
    }

    let queued_state_tasks = tasks.len() as u64;
    let queued_window_tasks = tasks.iter().filter(|task| task.with_window).count() as u64;
    let active_fetch_keys = active_fetch_key_count(&tasks);
    let estimates = estimate_rpc_work(&tasks, args.window_radius, args.rpc_batch_size);

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {POOL_STATE_SAMPLES_DATASET}|{POOL_LIQUIDITY_WINDOWS_DATASET}");
        println!("sampling mode: {}", args.sampling_mode.as_str());
        println!("candidate event rows: {}", stats.candidate_event_rows);
        println!("ranked event blocks: {}", stats.ranked_event_blocks);
        println!("selected pools: {}", pools.len());
        println!(
            "tier full-cross-pool blocks: {}",
            stats.full_cross_pool_blocks
        );
        println!("primary-only blocks: {}", stats.primary_only_blocks);
        println!("window event blocks: {}", stats.window_event_blocks);
        println!(
            "state tasks before existing-key dedupe: {}",
            stats.state_tasks_before_existing_dedupe
        );
        println!(
            "window tasks before existing-key dedupe: {}",
            stats.window_tasks_before_existing_dedupe
        );
        println!(
            "state tasks after existing-key dedupe: {}",
            stats.state_tasks_after_existing_dedupe
        );
        println!(
            "window tasks after existing-key dedupe: {}",
            stats.window_tasks_after_existing_dedupe
        );
        println!(
            "queued state tasks after shard/max filters: {}",
            queued_state_tasks
        );
        println!(
            "queued window tasks after shard/max filters: {}",
            queued_window_tasks
        );
        println!("unique active fetch keys: {active_fetch_keys}");
        println!(
            "estimated active eth_call requests: {}",
            estimates.active_calls
        );
        println!("estimated active RPC batches: {}", estimates.active_batches);
        println!(
            "estimated window eth_call requests: {}",
            estimates.window_calls
        );
        println!("estimated window RPC batches: {}", estimates.window_batches);
        if let (Some(shard_index), Some(shard_count)) = (args.shard_index, args.shard_count) {
            println!("queue shard: {shard_index}/{shard_count} (stable-hash)");
        }
        println!("workers: {}", args.workers);
        println!("batch size: {}", args.batch_size);
        println!("rpc batch size: {}", args.rpc_batch_size);
        println!("window radius: {}", args.window_radius);
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        return Ok(());
    }

    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let rpc_values = resolve_rpc_urls(&args.rpc_url, &args.env_file);
    let chunks = build_task_chunks(&tasks, args.batch_size);
    let total_chunks = chunks.len() as u64;

    if !tasks.is_empty() {
        let state_schema = pool_state_sample_schema();
        write_schema_metadata(
            &data_root,
            POOL_STATE_SAMPLES_DATASET,
            state_schema.as_ref(),
            &["dt"],
        )?;
        if queued_window_tasks > 0 {
            let window_schema = pool_liquidity_window_schema();
            write_schema_metadata(
                &data_root,
                POOL_LIQUIDITY_WINDOWS_DATASET,
                window_schema.as_ref(),
                &["dt"],
            )?;
        }
    }

    let mut output_parts = Vec::<PartWrite>::new();
    let mut rows_written = 0u64;
    let mut failed_rows = 0u64;
    let mut chunks_completed = 0u64;
    let mut state_tasks_completed = 0u64;
    let mut fatal_errors = Vec::<String>::new();
    let run_started = Instant::now();

    if !chunks.is_empty() {
        let assignments = assign_chunks_to_workers(chunks, args.workers);
        let worker_status = Arc::new(Mutex::new(vec!["idle".to_string(); args.workers]));
        let (sender, receiver) = mpsc::channel::<WorkerMessage>();
        let mut handles = Vec::new();
        for (worker_id, chunks) in assignments.into_iter().enumerate() {
            let sender = sender.clone();
            let data_root = data_root.clone();
            let fetched_at = fetched_at.clone();
            let rpc_values = rpc_values.clone();
            let worker_status = Arc::clone(&worker_status);
            let rpc_batch_size = args.rpc_batch_size;
            let window_radius = args.window_radius;
            handles.push(thread::spawn(move || {
                run_worker(WorkerConfig {
                    worker_id,
                    data_root,
                    fetched_at,
                    rpc_values,
                    rpc_batch_size,
                    window_radius,
                    chunks,
                    worker_status,
                    sender,
                });
            }));
        }
        drop(sender);

        println!(
            "collecting {} pool-state tasks ({} window tasks, {} active fetch keys) across {} chunks with {} workers",
            queued_state_tasks, queued_window_tasks, active_fetch_keys, total_chunks, args.workers
        );
        print_progress(
            queued_state_tasks,
            state_tasks_completed,
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
                    state_tasks_completed += report.state_task_count as u64;
                    rows_written += report.rows_written;
                    failed_rows += report.failed_rows;
                    chunks_completed += 1;
                    output_parts.extend(report.output_parts);
                    if chunks_completed <= args.workers as u64
                        || chunks_completed == total_chunks
                        || last_progress.elapsed() >= Duration::from_secs(30)
                    {
                        println!(
                            "worker {} completed chunk {} ({} state tasks, {} window tasks, {:.2}s)",
                            report.worker_id,
                            report.chunk_index,
                            report.state_task_count,
                            report.window_task_count,
                            report.elapsed_secs
                        );
                        print_progress(
                            queued_state_tasks,
                            state_tasks_completed,
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
                    failed_rows += error.state_task_count as u64;
                    let message = format!(
                        "worker {} chunk {} failed: {}",
                        error.worker_id, error.chunk_index, error.error
                    );
                    println!("{message}");
                    fatal_errors.push(message);
                    if last_progress.elapsed() >= Duration::from_secs(30) {
                        print_progress(
                            queued_state_tasks,
                            state_tasks_completed,
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
                            queued_state_tasks,
                            state_tasks_completed,
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
    let rows_per_sec = rows_per_sec(rows_written, run_started);
    save_pool_state_checkpoint(
        &checkpoint_path,
        &PoolStateCheckpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: pools
                .iter()
                .map(|pool| pool.address.clone())
                .collect::<Vec<_>>()
                .join("|"),
            topic0: POOL_STATE_SAMPLES_DATASET.to_string(),
            from_block: args.from_block.unwrap_or(0),
            to_block: args.to_block.unwrap_or(0),
            last_completed_block: args.to_block.unwrap_or(0),
            rows_written,
            output: part_paths_to_string(&output_parts),
            updated_at_utc: finished_at.clone(),
            workers: args.workers as u64,
            queued_state_tasks,
            queued_window_tasks,
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
            mode: args.sampling_mode.as_str().to_string(),
            dataset: POOL_STATE_SAMPLES_DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: pools
                .iter()
                .map(|pool| pool.address.clone())
                .collect::<Vec<_>>()
                .join("|"),
            topic0: POOL_STATE_SAMPLES_DATASET.to_string(),
            from_block: args.from_block,
            to_block: args.to_block,
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed,
            status: if tasks.is_empty() {
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

    println!("pool state/window rows written: {rows_written}");
    println!("failed rows: {failed_rows}");
    println!("completed chunks: {chunks_completed}/{total_chunks}");
    println!("rows/sec: {rows_per_sec:.2}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    if !fatal_errors.is_empty() {
        bail!(
            "pool-state collection finished with {} worker/chunk errors",
            fatal_errors.len()
        );
    }
    Ok(())
}

fn pool_info(pool: PoolCandidate) -> PoolInfo {
    let family = if pool.dex_id.eq_ignore_ascii_case("traderjoe")
        || pool.family_hint.to_ascii_lowercase().contains("2.2")
    {
        "lb_v22"
    } else if pool.dex_id.eq_ignore_ascii_case("pancakeswap") {
        "pancake_v3"
    } else {
        "v3"
    };
    PoolInfo {
        address: pool.pair_address.to_ascii_lowercase(),
        dex_id: pool.dex_id,
        family: family.to_string(),
    }
}

fn build_tasks(
    candidates: &[PoolStateCandidate],
    pools: &[PoolInfo],
    existing: &BTreeSet<(String, u64, String)>,
    sampling_mode: SamplingMode,
    full_cross_pool_event_blocks: usize,
    window_event_blocks: usize,
) -> TaskBuildPlan {
    let ranked_blocks = rank_event_blocks(candidates);
    let mut task_map = BTreeMap::<String, OutputTask>::new();
    let pool_by_address = pools
        .iter()
        .cloned()
        .map(|pool| (pool.address.clone(), pool))
        .collect::<BTreeMap<_, _>>();

    for block in &ranked_blocks {
        let primary_pool = pool_by_address
            .get(&block.primary.pool_address)
            .cloned()
            .unwrap_or_else(|| pool_info_from_candidate(&block.primary));
        let active_pools = active_pools_for_block(
            sampling_mode,
            block.rank,
            full_cross_pool_event_blocks,
            pools,
            primary_pool.clone(),
        );
        let window_enabled_for_block = block.rank < window_event_blocks;
        for (sample_side, sample_block_number) in [
            ("pre", block.primary.event_block_number.saturating_sub(1)),
            ("event", block.primary.event_block_number),
        ] {
            for pool in &active_pools {
                let with_window = window_enabled_for_block
                    && pool.address.eq_ignore_ascii_case(&primary_pool.address);
                let task = OutputTask {
                    candidate: block.primary.clone(),
                    pool: pool.clone(),
                    sample_block_number,
                    sample_side: sample_side.to_string(),
                    with_window,
                };
                let key = output_key(&task);
                task_map
                    .entry(key)
                    .and_modify(|current| current.with_window |= with_window)
                    .or_insert(task);
            }
        }
    }

    let state_tasks_before_existing_dedupe = task_map.len();
    let window_tasks_before_existing_dedupe =
        task_map.values().filter(|task| task.with_window).count();
    let mut tasks = task_map
        .into_values()
        .filter(|task| !existing.contains(&existing_key(task)))
        .collect::<Vec<_>>();
    tasks.sort_by(|a, b| {
        fetch_key(a)
            .cmp(&fetch_key(b))
            .then_with(|| output_key(a).cmp(&output_key(b)))
    });

    let full_cross_pool_blocks = match sampling_mode {
        SamplingMode::Tiered => full_cross_pool_event_blocks.min(ranked_blocks.len()),
        SamplingMode::AllPools => ranked_blocks.len(),
        SamplingMode::EventPool => 0,
    };
    let primary_only_blocks = match sampling_mode {
        SamplingMode::Tiered => ranked_blocks.len().saturating_sub(full_cross_pool_blocks),
        SamplingMode::EventPool => ranked_blocks.len(),
        SamplingMode::AllPools => 0,
    };
    let window_tasks_after_existing_dedupe = tasks.iter().filter(|task| task.with_window).count();

    TaskBuildPlan {
        stats: TaskBuildStats {
            ranked_event_blocks: ranked_blocks.len(),
            candidate_event_rows: candidates.len(),
            full_cross_pool_blocks,
            primary_only_blocks,
            window_event_blocks: window_event_blocks.min(ranked_blocks.len()),
            state_tasks_before_existing_dedupe,
            window_tasks_before_existing_dedupe,
            state_tasks_after_existing_dedupe: tasks.len(),
            window_tasks_after_existing_dedupe,
        },
        tasks,
    }
}

fn rank_event_blocks(candidates: &[PoolStateCandidate]) -> Vec<RankedEventBlock> {
    let mut by_block = BTreeMap::<u64, Vec<PoolStateCandidate>>::new();
    for candidate in candidates {
        by_block
            .entry(candidate.event_block_number)
            .or_default()
            .push(candidate.clone());
    }
    let mut blocks = by_block
        .into_iter()
        .filter_map(|(block_number, mut rows)| {
            rows.sort_by(|a, b| {
                quote_abs(b)
                    .total_cmp(&quote_abs(a))
                    .then_with(|| a.pool_address.cmp(&b.pool_address))
            });
            let primary = rows.first()?.clone();
            let score = quote_abs(&primary);
            Some((block_number, score, primary, rows))
        })
        .collect::<Vec<_>>();
    blocks.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    blocks
        .into_iter()
        .enumerate()
        .map(
            |(rank, (_block_number, _score, primary, _candidates))| RankedEventBlock {
                rank,
                primary,
            },
        )
        .collect()
}

fn quote_abs(candidate: &PoolStateCandidate) -> f64 {
    candidate
        .quote_abs
        .parse::<f64>()
        .ok()
        .filter(|value| value.is_finite())
        .unwrap_or(0.0)
}

fn pool_info_from_candidate(candidate: &PoolStateCandidate) -> PoolInfo {
    PoolInfo {
        address: candidate.pool_address.to_ascii_lowercase(),
        dex_id: candidate.dex_id.clone(),
        family: candidate.family.clone(),
    }
}

fn active_pools_for_block(
    sampling_mode: SamplingMode,
    rank: usize,
    full_cross_pool_event_blocks: usize,
    pools: &[PoolInfo],
    primary_pool: PoolInfo,
) -> Vec<PoolInfo> {
    let mut active_pools = match sampling_mode {
        SamplingMode::AllPools => pools.to_vec(),
        SamplingMode::EventPool => vec![primary_pool.clone()],
        SamplingMode::Tiered if rank < full_cross_pool_event_blocks => pools.to_vec(),
        SamplingMode::Tiered => vec![primary_pool.clone()],
    };
    if !active_pools
        .iter()
        .any(|pool| pool.address.eq_ignore_ascii_case(&primary_pool.address))
    {
        active_pools.push(primary_pool);
    }
    dedupe_pools(active_pools)
}

fn dedupe_pools(pools: Vec<PoolInfo>) -> Vec<PoolInfo> {
    let mut by_address = BTreeMap::<String, PoolInfo>::new();
    for pool in pools {
        by_address.entry(pool.address.clone()).or_insert(pool);
    }
    by_address.into_values().collect()
}

fn build_task_chunks(tasks: &[OutputTask], batch_size: usize) -> Vec<TaskChunk> {
    tasks
        .chunks(batch_size)
        .enumerate()
        .map(|(index, tasks)| TaskChunk {
            index,
            tasks: tasks.to_vec(),
        })
        .collect()
}

fn assign_chunks_to_workers(chunks: Vec<TaskChunk>, workers: usize) -> Vec<Vec<TaskChunk>> {
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
            .user_agent("finance-chain-mon-usdc-pool-state/0.1")
            .build()
            .context("failed to build HTTP client")?;
        let rpc_urls = RpcUrlPool::from_values(&config.rpc_values, DEFAULT_RPC_URL)?;
        let mut active_cache = BTreeMap::<FetchKey, ActiveStateResult>::new();
        for chunk in &config.chunks {
            set_worker_status(
                &config.worker_status,
                config.worker_id,
                &format!("chunk {}", chunk.index),
            );
            match collect_chunk(&config, &client, &rpc_urls, &mut active_cache, chunk) {
                Ok(report) => {
                    if config.sender.send(WorkerMessage::Chunk(report)).is_err() {
                        return Ok(());
                    }
                }
                Err(error) => {
                    let fatal = WorkerFatal {
                        worker_id: config.worker_id,
                        chunk_index: chunk.index,
                        state_task_count: chunk.tasks.len(),
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
            state_task_count: 0,
            error: format!("{error:#}"),
        }));
    }
    set_worker_status(&config.worker_status, config.worker_id, "done");
}

fn collect_chunk(
    config: &WorkerConfig,
    client: &Client,
    rpc_urls: &RpcUrlPool,
    active_cache: &mut BTreeMap<FetchKey, ActiveStateResult>,
    chunk: &TaskChunk,
) -> Result<ChunkReport> {
    let started = Instant::now();
    let mut state_rows = Vec::with_capacity(chunk.tasks.len());
    let mut window_rows = Vec::new();
    for task in &chunk.tasks {
        let dt = sample_dt_from_candidate(&task.candidate, &config.fetched_at);
        let key = fetch_key(task);
        let active = match active_cache.get(&key) {
            Some(active) => active.clone(),
            None => {
                let active = fetch_active_state(client, rpc_urls, task)?;
                active_cache.insert(key, active.clone());
                active
            }
        };
        state_rows.push(state_row_from_active(
            task,
            &config.fetched_at,
            &dt,
            &active,
        ));
        if task.with_window {
            window_rows.extend(sample_windows(
                client,
                rpc_urls,
                task,
                &config.fetched_at,
                &dt,
                &active,
                config.window_radius,
                config.rpc_batch_size,
            )?);
        }
    }
    let failed_rows = state_rows
        .iter()
        .filter(|row| row.request_status != "ok")
        .count() as u64
        + window_rows
            .iter()
            .filter(|row| row.request_status != "ok")
            .count() as u64;
    let batch_key = chunk.tasks.iter().map(output_key).collect::<Vec<_>>();
    let output_parts =
        write_pool_state_parts(&config.data_root, &state_rows, &window_rows, &batch_key)?;
    let rows_written = count_written_rows(&output_parts);
    Ok(ChunkReport {
        worker_id: config.worker_id,
        chunk_index: chunk.index,
        state_task_count: chunk.tasks.len(),
        window_task_count: chunk.tasks.iter().filter(|task| task.with_window).count(),
        rows_written,
        failed_rows,
        elapsed_secs: started.elapsed().as_secs_f64(),
        output_parts,
    })
}

fn fetch_active_state(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    task: &OutputTask,
) -> Result<ActiveStateResult> {
    if task.pool.family == "lb_v22" {
        fetch_lb_active_state(client, rpc_urls, task)
    } else {
        fetch_v3_active_state(client, rpc_urls, task)
    }
}

fn fetch_v3_active_state(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    task: &OutputTask,
) -> Result<ActiveStateResult> {
    let calls = vec![
        encode_no_arg_call("slot0()"),
        encode_no_arg_call("liquidity()"),
        encode_no_arg_call("tickSpacing()"),
    ];
    let results = eth_call_batch(
        client,
        rpc_urls,
        &task.pool.address,
        task.sample_block_number,
        &calls,
    )?;
    let mut active = ActiveStateResult::default();
    if results.iter().all(Result::is_ok) {
        let slot0 = results[0].as_ref().unwrap();
        let (sqrt_price_x96, tick) = parse_v3_slot0(slot0);
        let liquidity = parse_single_u256_result(results[1].as_ref().unwrap());
        let tick_spacing = parse_single_u256_result(results[2].as_ref().unwrap());
        active.request_status = "ok".to_string();
        active.sqrt_price_x96 = sqrt_price_x96;
        active.tick = tick;
        active.liquidity = liquidity;
        active.tick_spacing = tick_spacing;
    } else {
        active.request_status = "rpc_error".to_string();
        active.error = results
            .into_iter()
            .filter_map(Result::err)
            .collect::<Vec<_>>()
            .join(" | ");
    }
    Ok(active)
}

fn fetch_lb_active_state(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    task: &OutputTask,
) -> Result<ActiveStateResult> {
    let calls = vec![
        encode_no_arg_call("getActiveId()"),
        encode_no_arg_call("getBinStep()"),
    ];
    let results = eth_call_batch(
        client,
        rpc_urls,
        &task.pool.address,
        task.sample_block_number,
        &calls,
    )?;
    let mut active = ActiveStateResult::default();
    if results.iter().all(Result::is_ok) {
        let active_id = parse_single_u256_result(results[0].as_ref().unwrap());
        let bin_step = parse_single_u256_result(results[1].as_ref().unwrap());
        let active_id_u64 = active_id.parse::<u64>().unwrap_or(0);
        active.active_id = active_id;
        active.bin_step = bin_step;
        let bin_result = eth_call_batch(
            client,
            rpc_urls,
            &task.pool.address,
            task.sample_block_number,
            &[encode_u24_call("getBin(uint24)", active_id_u64)],
        )?
        .into_iter()
        .next()
        .unwrap_or_else(|| Err("missing getBin response".to_string()));
        match bin_result {
            Ok(value) => {
                let (reserve_x, reserve_y) = parse_lb_bin_result(&value);
                active.request_status = "ok".to_string();
                active.active_bin_reserve_x = reserve_x;
                active.active_bin_reserve_y = reserve_y;
            }
            Err(error) => {
                active.request_status = "rpc_error".to_string();
                active.error = error;
            }
        }
    } else {
        active.request_status = "rpc_error".to_string();
        active.error = results
            .into_iter()
            .filter_map(Result::err)
            .collect::<Vec<_>>()
            .join(" | ");
    }
    Ok(active)
}

fn state_row_from_active(
    task: &OutputTask,
    fetched_at: &str,
    dt: &str,
    active: &ActiveStateResult,
) -> PoolStateSampleRow {
    PoolStateSampleRow {
        fetched_at_utc: fetched_at.to_string(),
        event_block_number: task.candidate.event_block_number,
        sample_block_number: task.sample_block_number,
        sample_side: task.sample_side.clone(),
        pool_address: task.pool.address.clone(),
        dex_id: task.pool.dex_id.clone(),
        family: task.pool.family.clone(),
        request_status: active.request_status.clone(),
        error: active.error.clone(),
        sqrt_price_x96: active.sqrt_price_x96.clone(),
        tick: active.tick.clone(),
        liquidity: active.liquidity.clone(),
        tick_spacing: active.tick_spacing.clone(),
        active_id: active.active_id.clone(),
        bin_step: active.bin_step.clone(),
        active_bin_reserve_x: active.active_bin_reserve_x.clone(),
        active_bin_reserve_y: active.active_bin_reserve_y.clone(),
        dt: dt.to_string(),
    }
}

fn sample_windows(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    task: &OutputTask,
    fetched_at: &str,
    dt: &str,
    active: &ActiveStateResult,
    window_radius: i64,
    rpc_batch_size: usize,
) -> Result<Vec<PoolLiquidityWindowRow>> {
    if task.pool.family == "lb_v22" {
        sample_lb_windows(
            client,
            rpc_urls,
            task,
            fetched_at,
            dt,
            active,
            window_radius,
            rpc_batch_size,
        )
    } else {
        sample_v3_windows(
            client,
            rpc_urls,
            task,
            fetched_at,
            dt,
            active,
            window_radius,
            rpc_batch_size,
        )
    }
}

fn sample_v3_windows(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    task: &OutputTask,
    fetched_at: &str,
    dt: &str,
    active: &ActiveStateResult,
    window_radius: i64,
    rpc_batch_size: usize,
) -> Result<Vec<PoolLiquidityWindowRow>> {
    if active.tick.is_empty() || active.tick_spacing.is_empty() {
        return Ok(Vec::new());
    }
    let active_tick = active.tick.parse::<i64>().unwrap_or(0);
    let spacing = active.tick_spacing.parse::<i64>().unwrap_or(1).max(1);
    let mut window_calls = Vec::new();
    let mut offsets = Vec::new();
    for offset in -window_radius..=window_radius {
        let tick = active_tick + offset * spacing;
        window_calls.push(encode_i24_call("ticks(int24)", tick));
        offsets.push((offset, tick));
    }
    let mut windows = Vec::new();
    for chunk in window_calls.chunks(rpc_batch_size) {
        let base = windows.len();
        let chunk_results = eth_call_batch(
            client,
            rpc_urls,
            &task.pool.address,
            task.sample_block_number,
            chunk,
        )?;
        for (inner, result) in chunk_results.into_iter().enumerate() {
            let (offset, tick) = offsets[base + inner];
            let mut row = base_window_row(task, fetched_at, dt, "v3_tick", offset, tick);
            match result {
                Ok(value) => {
                    let (gross, net) = parse_v3_tick_result(&value);
                    row.request_status = "ok".to_string();
                    row.liquidity_gross = gross;
                    row.liquidity_net = net;
                }
                Err(error) => {
                    row.request_status = "rpc_error".to_string();
                    row.error = error;
                }
            }
            windows.push(row);
        }
    }
    Ok(windows)
}

fn sample_lb_windows(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    task: &OutputTask,
    fetched_at: &str,
    dt: &str,
    active: &ActiveStateResult,
    window_radius: i64,
    rpc_batch_size: usize,
) -> Result<Vec<PoolLiquidityWindowRow>> {
    if active.active_id.is_empty() {
        return Ok(Vec::new());
    }
    let active_id_u64 = active.active_id.parse::<u64>().unwrap_or(0);
    let mut window_calls = Vec::new();
    let mut offsets = Vec::new();
    for offset in -window_radius..=window_radius {
        let bin = if offset < 0 {
            active_id_u64.saturating_sub(offset.unsigned_abs())
        } else {
            active_id_u64.saturating_add(offset as u64)
        };
        window_calls.push(encode_u24_call("getBin(uint24)", bin));
        offsets.push((offset, bin));
    }
    let mut windows = Vec::new();
    for chunk in window_calls.chunks(rpc_batch_size) {
        let base = windows.len();
        let chunk_results = eth_call_batch(
            client,
            rpc_urls,
            &task.pool.address,
            task.sample_block_number,
            chunk,
        )?;
        for (inner, result) in chunk_results.into_iter().enumerate() {
            let (offset, bin) = offsets[base + inner];
            let mut row = base_window_row(task, fetched_at, dt, "lb_bin", offset, bin as i64);
            match result {
                Ok(value) => {
                    let (reserve_x, reserve_y) = parse_lb_bin_result(&value);
                    row.request_status = "ok".to_string();
                    row.reserve_x = reserve_x;
                    row.reserve_y = reserve_y;
                }
                Err(error) => {
                    row.request_status = "rpc_error".to_string();
                    row.error = error;
                }
            }
            windows.push(row);
        }
    }
    Ok(windows)
}

fn base_window_row(
    task: &OutputTask,
    fetched_at: &str,
    dt: &str,
    window_kind: &str,
    offset: i64,
    tick_or_bin: i64,
) -> PoolLiquidityWindowRow {
    PoolLiquidityWindowRow {
        fetched_at_utc: fetched_at.to_string(),
        event_block_number: task.candidate.event_block_number,
        sample_block_number: task.sample_block_number,
        pool_address: task.pool.address.clone(),
        family: task.pool.family.clone(),
        window_kind: window_kind.to_string(),
        offset,
        tick_or_bin: tick_or_bin.to_string(),
        request_status: "pending".to_string(),
        error: String::new(),
        liquidity_gross: String::new(),
        liquidity_net: String::new(),
        reserve_x: String::new(),
        reserve_y: String::new(),
        dt: dt.to_string(),
    }
}

fn eth_call_batch(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    to: &str,
    block: u64,
    calls: &[String],
) -> Result<Vec<Result<String, String>>> {
    let params = calls
        .iter()
        .map(|data| json!([{ "to": to, "data": data }, to_hex(block)]))
        .collect::<Vec<Value>>();
    let mut last_error = None;
    for attempt in 1..=MAX_RETRIES * rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_batch_items(client, rpc_url, "eth_call", &params) {
            Ok(items) => {
                return Ok(items
                    .into_iter()
                    .map(|item| match item {
                        RpcBatchItem::Result(value) => value
                            .as_str()
                            .map(|value| Ok(value.to_string()))
                            .unwrap_or_else(|| Err(value.to_string())),
                        RpcBatchItem::Error(error) => Err(error),
                    })
                    .collect());
            }
            Err(error) => {
                last_error = Some(error);
                if attempt < MAX_RETRIES * rpc_urls.len() {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }
    let error = last_error
        .map(|error| format!("{error:#}"))
        .unwrap_or_else(|| "batch failed without error".to_string());
    Ok(calls.iter().map(|_| Err(error.clone())).collect())
}

fn output_key(task: &OutputTask) -> String {
    format!(
        "{}:{}:{}",
        task.pool.address, task.sample_block_number, task.sample_side
    )
}

fn existing_key(task: &OutputTask) -> (String, u64, String) {
    (
        task.pool.address.clone(),
        task.sample_block_number,
        task.sample_side.clone(),
    )
}

fn fetch_key(task: &OutputTask) -> FetchKey {
    FetchKey {
        pool_address: task.pool.address.clone(),
        sample_block_number: task.sample_block_number,
    }
}

fn active_fetch_key_count(tasks: &[OutputTask]) -> usize {
    tasks.iter().map(fetch_key).collect::<BTreeSet<_>>().len()
}

#[derive(Debug, Clone, Copy, Default)]
struct RpcWorkEstimate {
    active_calls: usize,
    active_batches: usize,
    window_calls: usize,
    window_batches: usize,
}

fn estimate_rpc_work(
    tasks: &[OutputTask],
    window_radius: i64,
    rpc_batch_size: usize,
) -> RpcWorkEstimate {
    let mut active_by_key = BTreeMap::<FetchKey, PoolInfo>::new();
    for task in tasks {
        active_by_key
            .entry(fetch_key(task))
            .or_insert_with(|| task.pool.clone());
    }
    let mut estimate = RpcWorkEstimate::default();
    for pool in active_by_key.values() {
        estimate.active_calls += 3;
        estimate.active_batches += if pool.family == "lb_v22" {
            ceil_div(2, rpc_batch_size) + 1
        } else {
            ceil_div(3, rpc_batch_size)
        };
    }
    let window_width = (window_radius.saturating_mul(2).saturating_add(1)) as usize;
    let window_tasks = tasks.iter().filter(|task| task.with_window).count();
    estimate.window_calls = window_tasks * window_width;
    estimate.window_batches = window_tasks * ceil_div(window_width, rpc_batch_size);
    estimate
}

fn ceil_div(value: usize, divisor: usize) -> usize {
    if value == 0 {
        0
    } else {
        (value - 1) / divisor + 1
    }
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
    tasks_completed: u64,
    rows_written: u64,
    failed_rows: u64,
    chunks_completed: u64,
    total_chunks: u64,
    started: Instant,
    worker_status: &Arc<Mutex<Vec<String>>>,
) {
    let remaining = total_queued.saturating_sub(tasks_completed);
    let rows_per_sec = rows_per_sec(rows_written, started);
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
        tasks_completed,
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

fn save_pool_state_checkpoint(path: &PathBuf, checkpoint: &PoolStateCheckpoint) -> Result<()> {
    ensure_parent_dir(path)?;
    let file =
        File::create(path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, checkpoint)
        .with_context(|| format!("failed to write {}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_pool(index: usize) -> PoolInfo {
        PoolInfo {
            address: format!("0xpool{index}"),
            dex_id: if index >= 2 {
                "traderjoe".to_string()
            } else {
                "uniswap".to_string()
            },
            family: if index >= 2 {
                "lb_v22".to_string()
            } else {
                "v3".to_string()
            },
        }
    }

    fn test_pools() -> Vec<PoolInfo> {
        (0..4).map(test_pool).collect()
    }

    fn candidate(block: u64, pool_index: usize, quote: f64) -> PoolStateCandidate {
        PoolStateCandidate {
            event_block_number: block,
            block_timestamp: 1_700_000_000 + block,
            block_datetime_utc: "2026-05-11T00:00:00Z".to_string(),
            pool_address: format!("0xpool{pool_index}"),
            dex_id: "uniswap".to_string(),
            family: "v3".to_string(),
            direction: "buy_base".to_string(),
            quote_abs: format!("{quote:.12}"),
        }
    }

    fn candidates(count: usize) -> Vec<PoolStateCandidate> {
        (0..count)
            .map(|index| candidate(10_000 + index as u64, 0, (count - index) as f64))
            .collect()
    }

    #[test]
    fn tiered_mode_samples_top_blocks_cross_pool_then_primary_only() {
        let plan = build_tasks(
            &candidates(5_000),
            &test_pools(),
            &BTreeSet::new(),
            SamplingMode::Tiered,
            1_000,
            1_000,
        );
        assert_eq!(plan.stats.full_cross_pool_blocks, 1_000);
        assert_eq!(plan.stats.primary_only_blocks, 4_000);
        assert_eq!(plan.tasks.len(), 16_000);
        assert_eq!(
            plan.tasks.iter().filter(|task| task.with_window).count(),
            2_000
        );
    }

    #[test]
    fn event_pool_mode_only_samples_primary_pool_pre_and_event() {
        let plan = build_tasks(
            &candidates(5_000),
            &test_pools(),
            &BTreeSet::new(),
            SamplingMode::EventPool,
            1_000,
            1_000,
        );
        assert_eq!(plan.stats.full_cross_pool_blocks, 0);
        assert_eq!(plan.stats.primary_only_blocks, 5_000);
        assert_eq!(plan.tasks.len(), 10_000);
        assert!(plan.tasks.iter().all(|task| task.pool.address == "0xpool0"));
    }

    #[test]
    fn all_pools_mode_keeps_old_state_fanout() {
        let plan = build_tasks(
            &candidates(5_000),
            &test_pools(),
            &BTreeSet::new(),
            SamplingMode::AllPools,
            1_000,
            1_000,
        );
        assert_eq!(plan.stats.full_cross_pool_blocks, 5_000);
        assert_eq!(plan.tasks.len(), 40_000);
    }

    #[test]
    fn windows_only_attach_to_top_primary_event_pool_blocks() {
        let mut rows = candidates(10);
        rows.push(candidate(10_000, 1, 0.5));
        let plan = build_tasks(
            &rows,
            &test_pools(),
            &BTreeSet::new(),
            SamplingMode::Tiered,
            10,
            3,
        );
        let window_tasks = plan
            .tasks
            .iter()
            .filter(|task| task.with_window)
            .collect::<Vec<_>>();
        assert_eq!(window_tasks.len(), 6);
        assert!(
            window_tasks
                .iter()
                .all(|task| task.pool.address == "0xpool0")
        );
        assert!(
            window_tasks
                .iter()
                .all(|task| task.candidate.event_block_number < 10_003)
        );
    }

    #[test]
    fn chunk_assignment_has_no_duplicates_or_gaps() {
        let plan = build_tasks(
            &candidates(10),
            &test_pools(),
            &BTreeSet::new(),
            SamplingMode::EventPool,
            0,
            0,
        );
        let chunks = build_task_chunks(&plan.tasks, 3);
        assert_eq!(chunks.len(), 7);
        let assignments = assign_chunks_to_workers(chunks, 3);
        assert_eq!(assignments.len(), 3);
        let mut seen = assignments
            .iter()
            .flat_map(|worker_chunks| worker_chunks.iter())
            .flat_map(|chunk| chunk.tasks.iter().map(output_key))
            .collect::<Vec<_>>();
        seen.sort();
        let mut expected = plan.tasks.iter().map(output_key).collect::<Vec<_>>();
        expected.sort();
        assert_eq!(seen, expected);
        let assigned_chunk_ids = assignments
            .iter()
            .flat_map(|worker_chunks| worker_chunks.iter().map(|chunk| chunk.index))
            .collect::<BTreeSet<_>>();
        assert_eq!(assigned_chunk_ids, (0..7).collect());
    }

    #[test]
    fn fetch_key_cache_can_serve_multiple_output_rows() {
        let pool = test_pool(0);
        let base = OutputTask {
            candidate: candidate(20, 0, 100.0),
            pool: pool.clone(),
            sample_block_number: 19,
            sample_side: "pre".to_string(),
            with_window: false,
        };
        let other = OutputTask {
            sample_side: "event".to_string(),
            ..base.clone()
        };
        assert_eq!(fetch_key(&base), fetch_key(&other));

        let active = ActiveStateResult {
            request_status: "ok".to_string(),
            tick: "123".to_string(),
            liquidity: "456".to_string(),
            ..ActiveStateResult::default()
        };
        let mut cache = BTreeMap::<FetchKey, ActiveStateResult>::new();
        cache.insert(fetch_key(&base), active.clone());
        let first = state_row_from_active(&base, "2026-05-11T00:00:00Z", "2026-05-11", &active);
        let cached = cache.get(&fetch_key(&other)).unwrap();
        let second = state_row_from_active(&other, "2026-05-11T00:00:00Z", "2026-05-11", cached);
        assert_eq!(first.tick, "123");
        assert_eq!(second.tick, "123");
        assert_eq!(first.sample_side, "pre");
        assert_eq!(second.sample_side, "event");
    }
}

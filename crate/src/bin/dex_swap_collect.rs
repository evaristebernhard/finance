use std::collections::BTreeMap;
use std::path::PathBuf;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use chog_prices::{
    CHECKPOINT_VERSION, Checkpoint, RpcUrlPool,
    chog_v1::{
        ChogCollectionRunRecord, PartWriteStatus, checkpoint_path_with_suffix,
        default_data_root_path, part_paths_to_string, write_collection_run_parquet,
        write_schema_metadata,
    },
    dex::{
        DEX_SWAP_DATASET, SWAP_FAMILIES, V2_SWAP_TOPIC, V3_SWAP_TOPIC, dex_swap_schema,
        fetch_swap_logs_for_address_batch_with_retry, fetch_swap_logs_with_retry, parse_swap_log,
        pool_metadata_from_snapshot, read_latest_dex_pools, resolve_pool_metadata_with_retry,
        write_dex_swap_parts,
    },
    load_checkpoint, resolve_block_range, rpc_call_hex_u64_from_pool, save_checkpoint,
    utc_now_string, validate_checkpoint_identity,
};
use clap::{Parser, ValueEnum};
use reqwest::blocking::Client;
use serde_json::json;

const DEFAULT_RPC_URL: &str = "https://rpc.monad.xyz";
const DEFAULT_BLOCKS: u64 = 5_000;
const DEFAULT_LOG_RANGE_BLOCKS: u64 = 100;
const COLLECTOR: &str = "dex_swap_collect";
const CHAIN: &str = "monad";
const CHECKPOINT_ADDRESS: &str = "known_chog_pools";

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum MetadataSource {
    Snapshot,
    Rpc,
}

#[derive(Debug, Parser)]
#[command(
    name = "dex_swap_collect",
    about = "Fetch V2/V3 Swap logs for all known CHOG DexScreener pools."
)]
struct Args {
    #[arg(long = "rpc-url", default_value = DEFAULT_RPC_URL)]
    rpc_url: Vec<String>,

    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Recent block count to scan when --from-block is omitted.
    #[arg(long, default_value_t = DEFAULT_BLOCKS)]
    blocks: u64,

    /// Block range size per eth_getLogs request.
    #[arg(long, default_value_t = DEFAULT_LOG_RANGE_BLOCKS)]
    log_range_blocks: u64,

    /// Number of eth_getLogs chunks per JSON-RPC batch request.
    #[arg(long, default_value_t = 20)]
    log_batch_size: usize,

    /// Pool token metadata source.
    #[arg(long, value_enum, default_value_t = MetadataSource::Snapshot)]
    metadata_source: MetadataSource,

    /// Explicit first block to scan. Takes precedence over --resume and --blocks.
    #[arg(long)]
    from_block: Option<u64>,

    /// Explicit final block to scan. Defaults to latest block at run start.
    #[arg(long)]
    to_block: Option<u64>,

    /// Resume from checkpoint last_completed_block + 1 when a checkpoint exists.
    #[arg(long)]
    resume: bool,

    /// Explicit checkpoint path.
    #[arg(long)]
    checkpoint: Option<PathBuf>,

    /// Suffix for the default checkpoint filename, useful for parallel shards.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Accepted for parity with log collectors; Parquet output is always idempotent.
    #[arg(long)]
    append: bool,

    /// Restrict collection to one or more pool addresses from the latest snapshot.
    #[arg(long = "pool-address")]
    pool_addresses: Vec<String>,

    /// Resolve pools, block window, and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.blocks == 0 {
        bail!("--blocks must be greater than 0");
    }
    if args.log_range_blocks == 0 {
        bail!("--log-range-blocks must be greater than 0");
    }
    if args.log_batch_size == 0 {
        bail!("--log-batch-size must be greater than 0");
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
        .user_agent("finance-chain-dex-swap-collect/0.1")
        .build()
        .context("failed to build HTTP client")?;
    let rpc_urls = RpcUrlPool::from_values(&args.rpc_url, DEFAULT_RPC_URL)?;
    let latest_block = if let Some(to_block) = args.to_block {
        to_block
    } else {
        rpc_call_hex_u64_from_pool(&client, &rpc_urls, "eth_blockNumber", json!([]))?
    };
    let topic_identity = checkpoint_topic_identity();
    let checkpoint = if args.resume && args.from_block.is_none() && checkpoint_path.exists() {
        let checkpoint = load_checkpoint(&checkpoint_path)?;
        validate_checkpoint_identity(
            &checkpoint,
            COLLECTOR,
            CHAIN,
            CHECKPOINT_ADDRESS,
            &topic_identity,
        )?;
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

    let pools = filter_pools(read_latest_dex_pools(&data_root)?, &args.pool_addresses)?;
    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DEX_SWAP_DATASET}");
        println!("block window: {}..{}", range.from_block, range.to_block);
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        println!("known pools: {}", pools.len());
        for pool in &pools {
            println!(
                "{} {} {} {}/{} liq_usd={:.2} vol24_usd={:.2}",
                pool.dex_id,
                pool.family_hint(),
                pool.pair_address,
                pool.base_symbol,
                pool.quote_symbol,
                pool.liquidity_usd.unwrap_or(0.0),
                pool.volume_h24_usd.unwrap_or(0.0)
            );
        }
        return Ok(());
    }

    let mut metadata = Vec::new();
    let mut skipped = Vec::new();
    for pool in pools {
        let resolved = match args.metadata_source {
            MetadataSource::Snapshot => pool_metadata_from_snapshot(&pool),
            MetadataSource::Rpc => resolve_pool_metadata_with_retry(&client, &rpc_urls, &pool),
        };
        match resolved {
            Ok(value) => metadata.push(value),
            Err(error) => skipped.push(format!("{}: {error:#}", pool.pair_address)),
        }
    }
    if metadata.is_empty() {
        bail!("no known pools could be resolved via token0/token1/decimals eth_call");
    }

    let schema = dex_swap_schema();
    write_schema_metadata(&data_root, DEX_SWAP_DATASET, schema.as_ref(), &["dt"])?;
    let metadata_by_address = metadata
        .iter()
        .map(|pool| (pool.pool.pair_address.to_ascii_lowercase(), pool))
        .collect::<BTreeMap<_, _>>();
    let pool_addresses = metadata
        .iter()
        .map(|pool| pool.pool.pair_address.clone())
        .collect::<Vec<_>>();

    let mut output_parts = Vec::new();
    let mut rows_written = 0u64;
    let mut chunks_completed = 0u64;
    let mut start = range.from_block;
    while start <= range.to_block {
        let mut ranges = Vec::new();
        let mut range_start = start;
        while range_start <= range.to_block && ranges.len() < args.log_batch_size {
            let range_end = range
                .to_block
                .min(range_start.saturating_add(args.log_range_blocks - 1));
            ranges.push((range_start, range_end));
            if range_end == u64::MAX {
                break;
            }
            range_start = range_end + 1;
        }

        let batch_logs = match fetch_swap_logs_for_address_batch_with_retry(
            &client,
            &rpc_urls,
            &pool_addresses,
            &ranges,
        ) {
            Ok(logs) => logs,
            Err(batch_error) => {
                fallback_fetch_ranges(&client, &rpc_urls, &metadata, &ranges, batch_error)?
            }
        };

        for ((chunk_start, chunk_end), logs) in ranges.iter().copied().zip(batch_logs) {
            let mut chunk_rows = Vec::new();
            for log in logs {
                let address = log.address.to_ascii_lowercase();
                let Some(pool) = metadata_by_address.get(&address) else {
                    skipped.push(format!(
                        "{}: swap log returned for unknown pool",
                        log.address
                    ));
                    continue;
                };
                let Some(family) = family_from_log(&log) else {
                    skipped.push(format!(
                        "{}: swap log returned with unknown topic",
                        log.transaction_hash
                    ));
                    continue;
                };
                chunk_rows.push(parse_swap_log(&fetched_at, pool, family, log)?);
            }
            chunk_rows.sort_by_key(|row| {
                (
                    row.block_number,
                    row.transaction_index,
                    row.log_index,
                    row.pool_address.clone(),
                )
            });

            let parts = write_dex_swap_parts(
                &data_root,
                schema.clone(),
                &chunk_rows,
                chunk_start,
                chunk_end,
                COLLECTOR,
            )?;
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
                address: CHECKPOINT_ADDRESS.to_string(),
                topic0: topic_identity.clone(),
                from_block: range.from_block,
                to_block: range.to_block,
                last_completed_block: chunk_end,
                rows_written,
                output: part_paths_to_string(&output_parts),
                updated_at_utc: utc_now_string(),
            };
            save_checkpoint(&checkpoint_path, &checkpoint)?;
        }

        let last_end = ranges.last().map(|(_, end)| *end).unwrap_or(start);
        if last_end == u64::MAX {
            break;
        }
        start = last_end + 1;
    }

    let finished_at = utc_now_string();
    let status = if !skipped.is_empty() {
        "completed_with_skips"
    } else if range.is_empty() {
        "empty"
    } else {
        "completed"
    };
    write_collection_run_parquet(
        &data_root,
        &ChogCollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DEX_SWAP_DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: CHECKPOINT_ADDRESS.to_string(),
            topic0: topic_identity,
            from_block: Some(range.from_block),
            to_block: Some(range.to_block),
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed,
            status: status.to_string(),
            error: skipped.join(" | "),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    println!("block window: {}..{}", range.from_block, range.to_block);
    println!("resolved pools: {}", metadata.len());
    println!("skipped pools: {}", skipped.len());
    println!("swap logs written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());

    Ok(())
}

fn checkpoint_topic_identity() -> String {
    format!("{V2_SWAP_TOPIC}|{V3_SWAP_TOPIC}")
}

fn family_from_log(log: &chog_prices::dex::RpcSwapLog) -> Option<chog_prices::dex::SwapFamily> {
    let topic0 = log.topics.first()?;
    if topic0.eq_ignore_ascii_case(V2_SWAP_TOPIC) {
        Some(chog_prices::dex::SwapFamily::V2)
    } else if topic0.eq_ignore_ascii_case(V3_SWAP_TOPIC) {
        Some(chog_prices::dex::SwapFamily::V3)
    } else {
        None
    }
}

fn fallback_fetch_ranges(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    metadata: &[chog_prices::dex::PoolMetadata],
    ranges: &[(u64, u64)],
    batch_error: anyhow::Error,
) -> Result<Vec<Vec<chog_prices::dex::RpcSwapLog>>> {
    let mut results = Vec::new();
    for (start, end) in ranges {
        let mut chunk_logs = Vec::new();
        for pool in metadata {
            for family in SWAP_FAMILIES {
                let logs = fetch_swap_logs_with_retry(
                    client,
                    rpc_urls,
                    &pool.pool.pair_address,
                    family,
                    *start,
                    *end,
                )
                .with_context(|| {
                    format!(
                        "JSON-RPC batch fetch failed ({batch_error:#}); fallback failed for {} logs for {} blocks {start}..{end}",
                        family.as_str(),
                        pool.pool.pair_address
                    )
                })?;
                chunk_logs.extend(logs);
            }
        }
        results.push(chunk_logs);
    }
    Ok(results)
}

fn filter_pools(
    pools: Vec<chog_prices::dex::DexPool>,
    requested: &[String],
) -> Result<Vec<chog_prices::dex::DexPool>> {
    if requested.is_empty() {
        return Ok(pools);
    }
    let requested = requested
        .iter()
        .map(|value| value.to_ascii_lowercase())
        .collect::<std::collections::BTreeSet<_>>();
    let filtered = pools
        .into_iter()
        .filter(|pool| requested.contains(&pool.pair_address.to_ascii_lowercase()))
        .collect::<Vec<_>>();
    if filtered.is_empty() {
        bail!("none of the requested --pool-address values were found in the latest Dex snapshot");
    }
    Ok(filtered)
}

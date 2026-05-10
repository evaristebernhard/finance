use std::collections::BTreeMap;
use std::path::PathBuf;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use clap::Parser;
use finance_chain_core::amm::{RpcSwapLog, SwapFamily, resolve_pool_metadata};
use finance_chain_core::rpc::{
    RpcBatchItem, RpcUrlPool, rpc_batch_items, rpc_call_from_pool, to_hex,
};
use finance_chain_core::storage::{
    CHECKPOINT_VERSION, Checkpoint, CollectionRunRecord, checkpoint_path_with_suffix,
    part_paths_to_string, safe_file_suffix, save_checkpoint, utc_now_string,
    write_collection_run_parquet,
};
use mon_usdc_collectors::{
    BASE_SYMBOL, CHAIN, DEFAULT_RPC_URL, MON_TOKEN, ONE_DAY_BLOCKS, POOL_SWAP_LOGS_DATASET,
    QUOTE_SYMBOL, USDC_TOKEN, count_written_rows, default_data_root_path, resolve_rpc_urls,
    select_pools, swap_row_from_log, topic_identity, write_pool_swap_parts,
};
use reqwest::blocking::Client;
use serde_json::{Value, json};

const COLLECTOR: &str = "mon_usdc_swap_collect";
const DEFAULT_LOG_RANGE_BLOCKS: u64 = 1_000;
const DEFAULT_LOG_BATCH_SIZE: usize = 8;
const MAX_RETRIES: usize = 3;

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_swap_collect",
    about = "Fetch MON/USDC top-pool swap logs into data/mon_usdc/v1."
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

    /// Recent block count to scan when --from-block is omitted.
    #[arg(long, default_value_t = ONE_DAY_BLOCKS)]
    blocks: u64,

    /// Explicit first block to scan.
    #[arg(long)]
    from_block: Option<u64>,

    /// Explicit final block to scan. Defaults to latest block at run start.
    #[arg(long)]
    to_block: Option<u64>,

    /// Block range per eth_getLogs request.
    #[arg(long, default_value_t = DEFAULT_LOG_RANGE_BLOCKS)]
    log_range_blocks: u64,

    /// Number of eth_getLogs calls per JSON-RPC batch.
    #[arg(long, default_value_t = DEFAULT_LOG_BATCH_SIZE)]
    log_batch_size: usize,

    /// Restrict collection to one or more pool addresses.
    #[arg(long = "pool-address")]
    pool_addresses: Vec<String>,

    /// Number of discovered pools to use when no explicit pool address is supplied.
    #[arg(long, default_value_t = 4)]
    top_pools: usize,

    /// Suffix for the default checkpoint filename.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Prefix for Parquet part filenames. Defaults to collector plus checkpoint suffix.
    #[arg(long)]
    part_prefix: Option<String>,

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
    let default_part_prefix = if let Some(suffix) = args
        .checkpoint_suffix
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        format!("{COLLECTOR}_{}", safe_file_suffix(suffix)?)
    } else {
        COLLECTOR.to_string()
    };
    let part_prefix = args
        .part_prefix
        .as_deref()
        .map(safe_file_suffix)
        .transpose()?
        .unwrap_or(default_part_prefix);
    let checkpoint_path =
        checkpoint_path_with_suffix(&data_root, COLLECTOR, args.checkpoint_suffix.as_deref())?;
    let rpc_urls = RpcUrlPool::from_values(
        &resolve_rpc_urls(&args.rpc_url, &args.env_file),
        DEFAULT_RPC_URL,
    )?;
    let client = Client::builder()
        .timeout(Duration::from_secs(45))
        .user_agent("finance-chain-mon-usdc-swap-collect/0.1")
        .build()
        .context("failed to build HTTP client")?;
    let latest_block = if let Some(to_block) = args.to_block {
        to_block
    } else {
        let value: String = rpc_call_from_pool(&client, &rpc_urls, "eth_blockNumber", json!([]))?;
        finance_chain_core::parse_hex_u64(&value)?
    };
    let to_block = latest_block;
    let from_block = args
        .from_block
        .unwrap_or_else(|| to_block.saturating_sub(args.blocks - 1));
    if from_block > to_block {
        bail!("--from-block {from_block} is greater than --to-block/latest {to_block}");
    }

    let pools = select_pools(&data_root, &args.pool_addresses, args.top_pools)?;
    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {POOL_SWAP_LOGS_DATASET}");
        println!("block window: {from_block}..{to_block}");
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        println!("part prefix: {part_prefix}");
        println!("selected pools: {}", pools.len());
        for pool in &pools {
            println!(
                "{} {} {} {}/{}",
                pool.dex_id,
                pool.family_hint,
                pool.pair_address,
                pool.base_symbol,
                pool.quote_symbol
            );
        }
        return Ok(());
    }

    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let mut metadata = Vec::new();
    let mut skipped = Vec::new();
    for pool in &pools {
        match resolve_pool_metadata(
            &client,
            &rpc_urls,
            pool,
            MON_TOKEN,
            USDC_TOKEN,
            BASE_SYMBOL,
            QUOTE_SYMBOL,
        ) {
            Ok(value) => metadata.push(value),
            Err(error) => skipped.push(format!("{}: {error:#}", pool.pair_address)),
        }
    }
    if metadata.is_empty() {
        bail!("no selected pools could be resolved via token metadata RPC");
    }

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
    let mut start = from_block;
    while start <= to_block {
        let mut ranges = Vec::new();
        let mut range_start = start;
        while range_start <= to_block && ranges.len() < args.log_batch_size {
            let range_end = to_block.min(range_start.saturating_add(args.log_range_blocks - 1));
            ranges.push((range_start, range_end));
            if range_end == u64::MAX {
                break;
            }
            range_start = range_end + 1;
        }

        let batch_logs = fetch_swap_logs_batch(&client, &rpc_urls, &pool_addresses, &ranges)?;
        for ((chunk_start, chunk_end), logs) in ranges.iter().copied().zip(batch_logs) {
            let mut rows = Vec::new();
            for log in logs {
                let address = log.address.to_ascii_lowercase();
                let Some(pool) = metadata_by_address.get(&address) else {
                    skipped.push(format!(
                        "{}: swap log returned for unknown pool",
                        log.address
                    ));
                    continue;
                };
                let Some(topic0) = log.topics.first() else {
                    skipped.push(format!(
                        "{}: swap log returned without topics",
                        log.transaction_hash
                    ));
                    continue;
                };
                let Some(family) = SwapFamily::from_topic(topic0) else {
                    skipped.push(format!(
                        "{}: swap log returned with unknown topic {}",
                        log.transaction_hash, topic0
                    ));
                    continue;
                };
                rows.push(swap_row_from_log(&fetched_at, pool, family, log)?);
            }
            rows.sort_by_key(|row| {
                (
                    row.block_number,
                    row.transaction_index,
                    row.log_index,
                    row.pool_address.clone(),
                )
            });

            let parts =
                write_pool_swap_parts(&data_root, &rows, chunk_start, chunk_end, &part_prefix)?;
            rows_written += count_written_rows(&parts);
            output_parts.extend(parts);
            chunks_completed += 1;

            let checkpoint = Checkpoint {
                version: CHECKPOINT_VERSION,
                collector: COLLECTOR.to_string(),
                chain: CHAIN.to_string(),
                address: pool_addresses.join("|"),
                topic0: topic_identity(),
                from_block,
                to_block,
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
    let status = if skipped.is_empty() {
        "completed"
    } else {
        "completed_with_skips"
    };
    write_collection_run_parquet(
        &data_root,
        &CollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: POOL_SWAP_LOGS_DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: pool_addresses.join("|"),
            topic0: topic_identity(),
            from_block: Some(from_block),
            to_block: Some(to_block),
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

    println!("block window: {from_block}..{to_block}");
    println!("resolved pools: {}", metadata.len());
    println!("skipped: {}", skipped.len());
    println!("swap logs written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    Ok(())
}

fn fetch_swap_logs_batch(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool_addresses: &[String],
    ranges: &[(u64, u64)],
) -> Result<Vec<Vec<RpcSwapLog>>> {
    let params_list = ranges
        .iter()
        .map(|(from_block, to_block)| {
            json!([
                {
                    "address": pool_addresses,
                    "fromBlock": to_hex(*from_block),
                    "toBlock": to_hex(*to_block),
                    "topics": [[
                        finance_chain_core::amm::V2_SWAP_TOPIC,
                        finance_chain_core::amm::V3_SWAP_TOPIC,
                        finance_chain_core::amm::PANCAKE_V3_SWAP_TOPIC,
                        finance_chain_core::amm::LB_V22_SWAP_TOPIC
                    ]],
                }
            ])
        })
        .collect::<Vec<Value>>();

    let mut last_error = None;
    for attempt in 1..=MAX_RETRIES * rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_batch_items(client, rpc_url, "eth_getLogs", &params_list) {
            Ok(items) => return parse_log_batch_items(items),
            Err(error) => {
                last_error = Some(error);
                if attempt < MAX_RETRIES * rpc_urls.len() {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("eth_getLogs batch failed without an error")))
}

fn parse_log_batch_items(items: Vec<RpcBatchItem>) -> Result<Vec<Vec<RpcSwapLog>>> {
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        match item {
            RpcBatchItem::Result(value) => {
                out.push(serde_json::from_value::<Vec<RpcSwapLog>>(value)?);
            }
            RpcBatchItem::Error(error) => bail!("eth_getLogs batch item failed: {error}"),
        }
    }
    Ok(out)
}

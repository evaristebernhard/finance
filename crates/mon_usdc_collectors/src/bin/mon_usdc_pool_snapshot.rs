use std::time::Duration;

use anyhow::{Context, Result};
use clap::Parser;
use finance_chain_core::dexscreener::discover_pair_pools;
use finance_chain_core::storage::{
    CHECKPOINT_VERSION, Checkpoint, CollectionRunRecord, checkpoint_path_with_suffix,
    part_paths_to_string, save_checkpoint, utc_now_string, write_collection_run_parquet,
};
use mon_usdc_collectors::{
    BASE_SYMBOL, CHAIN, MON_TOKEN, POOL_SNAPSHOTS_DATASET, QUOTE_SYMBOL, USDC_TOKEN,
    count_written_rows, default_data_root_path, known_top4_pools, write_pool_snapshot_part,
};
use reqwest::blocking::Client;

const COLLECTOR: &str = "mon_usdc_pool_snapshot";

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_pool_snapshot",
    about = "Discover and persist MON/USDC pool candidates from DexScreener."
)]
struct Args {
    /// MON/USDC v1 data root.
    #[arg(long)]
    data_root: Option<std::path::PathBuf>,

    /// DexScreener chain id.
    #[arg(long, default_value = CHAIN)]
    chain: String,

    /// Use the built-in top4 pool list without calling DexScreener.
    #[arg(long)]
    known_top4_only: bool,

    /// Resolve output paths without fetching or writing.
    #[arg(long)]
    dry_run: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let data_root = args.data_root.unwrap_or_else(default_data_root_path);
    let started_at = utc_now_string();
    let fetched_at = started_at.clone();

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {POOL_SNAPSHOTS_DATASET}");
        println!("chain: {}", args.chain);
        println!("base: {BASE_SYMBOL} {MON_TOKEN}");
        println!("quote: {QUOTE_SYMBOL} {USDC_TOKEN}");
        println!("data root: {}", data_root.display());
        println!("known top4 fallback: {}", known_top4_pools().len());
        return Ok(());
    }

    let mut rows = if args.known_top4_only {
        known_top4_pools()
    } else {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .user_agent("finance-chain-mon-usdc-pool-snapshot/0.1")
            .build()
            .context("failed to build HTTP client")?;
        discover_pair_pools(&client, &args.chain, MON_TOKEN, USDC_TOKEN, &fetched_at)?
    };
    if rows.is_empty() {
        rows = known_top4_pools();
    }
    for row in &mut rows {
        if row.fetched_at_utc.is_empty() {
            row.fetched_at_utc = fetched_at.clone();
        }
    }

    let part = write_pool_snapshot_part(&data_root, &rows, &fetched_at)?;
    let parts = vec![part];
    let rows_written = count_written_rows(&parts);
    let finished_at = utc_now_string();
    let checkpoint_path = checkpoint_path_with_suffix(&data_root, COLLECTOR, None)?;
    let checkpoint = Checkpoint {
        version: CHECKPOINT_VERSION,
        collector: COLLECTOR.to_string(),
        chain: args.chain.clone(),
        address: format!("{MON_TOKEN}|{USDC_TOKEN}"),
        topic0: String::new(),
        from_block: 0,
        to_block: 0,
        last_completed_block: 0,
        rows_written,
        output: part_paths_to_string(&parts),
        updated_at_utc: finished_at.clone(),
    };
    save_checkpoint(&checkpoint_path, &checkpoint)?;
    write_collection_run_parquet(
        &data_root,
        &CollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: POOL_SNAPSHOTS_DATASET.to_string(),
            chain: args.chain,
            address: format!("{MON_TOKEN}|{USDC_TOKEN}"),
            topic0: String::new(),
            from_block: None,
            to_block: None,
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&parts),
            rows_written,
            chunks_completed: 1,
            status: "completed".to_string(),
            error: String::new(),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    println!("pool candidates: {}", rows.len());
    println!("rows written: {rows_written}");
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());
    Ok(())
}

use std::path::{Path, PathBuf};

use anyhow::Result;
use chog_prices::{
    chog_v1::default_data_root_path,
    dex::read_latest_dex_pools,
    dex_factors::{
        DEX_SWAP_FACTORS_DATASET, DexFactorReport, FactorTest, rebuild_dex_swap_factors,
    },
    dex_hourly::{DEX_POOL_SWAP_HOURLY_DATASET, rebuild_dex_pool_swap_hourly},
    memecoin_features::{
        MEMECOIN_EVENT_FEATURES_DATASET, MEMECOIN_HOURLY_FEATURES_DATASET,
        rebuild_memecoin_features,
    },
};
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(
    name = "dex_rebuild",
    about = "Rebuild derived CHOG DEX tables from local Parquet data."
)]
struct Args {
    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Print the latest DexScreener-derived known pool registry.
    ListPools,

    /// Aggregate dex_pool_swap_logs into hourly pool swap features.
    Hourly {
        /// Restrict aggregation to one or more pool addresses.
        #[arg(long = "pool-address")]
        pool_addresses: Vec<String>,

        /// Resolve rows and output paths without writing derived Parquet.
        #[arg(long)]
        dry_run: bool,
    },

    /// Build trade-level factor rows and exploratory factor diagnostics.
    Factors {
        /// Number of factor tests to print in the report.
        #[arg(long, default_value_t = 20)]
        top: usize,

        /// Resolve rows and output paths without writing derived Parquet.
        #[arg(long)]
        dry_run: bool,

        /// Print machine-readable JSON instead of a text report.
        #[arg(long)]
        json: bool,
    },

    /// Build event-level and hourly memecoin strategy features.
    MemecoinFeatures {
        /// Resolve rows and output paths without writing derived Parquet.
        #[arg(long)]
        dry_run: bool,
    },
}

fn main() -> Result<()> {
    let args = Args::parse();
    let data_root = args.data_root.unwrap_or_else(default_data_root_path);
    match args.command {
        Command::ListPools => list_pools(&data_root),
        Command::Hourly {
            pool_addresses,
            dry_run,
        } => rebuild_hourly(&data_root, &pool_addresses, dry_run),
        Command::Factors { top, dry_run, json } => rebuild_factors(&data_root, top, dry_run, json),
        Command::MemecoinFeatures { dry_run } => rebuild_memecoin(&data_root, dry_run),
    }
}

fn list_pools(data_root: &Path) -> Result<()> {
    let pools = read_latest_dex_pools(data_root)?;
    println!("known pools: {}", pools.len());
    for pool in pools {
        println!(
            "{}\t{}\t{}\t{}/{}\tliq_usd={:.2}\tvol24_usd={:.2}\tfetched_at={}",
            pool.dex_id,
            pool.family_hint(),
            pool.pair_address,
            pool.base_symbol,
            pool.quote_symbol,
            pool.liquidity_usd.unwrap_or(0.0),
            pool.volume_h24_usd.unwrap_or(0.0),
            pool.fetched_at_utc
        );
    }
    Ok(())
}

fn rebuild_hourly(data_root: &Path, pool_addresses: &[String], dry_run: bool) -> Result<()> {
    let summary = rebuild_dex_pool_swap_hourly(data_root, pool_addresses, dry_run)?;
    if summary.hourly_rows == 0 {
        println!(
            "no dex swap rows found under {}",
            summary.input_root.display()
        );
        return Ok(());
    }

    let min_block = summary.min_block.unwrap_or(0);
    let max_block = summary.max_block.unwrap_or(0);
    if dry_run {
        println!("dataset: {DEX_POOL_SWAP_HOURLY_DATASET}");
        println!("input block window: {min_block}..{max_block}");
        println!("hourly rows: {}", summary.hourly_rows);
        for part in summary.parts {
            println!(
                "{}: rows={} path={}",
                part.dt,
                part.rows,
                part.path.display()
            );
        }
        return Ok(());
    }

    println!("input block window: {min_block}..{max_block}");
    println!("hourly rows written: {}", summary.hourly_rows);
    println!("parquet parts: {}", summary.parquet_parts);
    Ok(())
}

fn rebuild_factors(data_root: &Path, top: usize, dry_run: bool, json: bool) -> Result<()> {
    let summary = rebuild_dex_swap_factors(data_root, dry_run, top)?;
    if json {
        println!("{}", serde_json::to_string_pretty(&summary.report)?);
        return Ok(());
    }

    if summary.factor_rows == 0 {
        println!(
            "no dex swap rows found under {}",
            summary.input_root.display()
        );
        return Ok(());
    }

    let min_block = summary.min_block.unwrap_or(0);
    let max_block = summary.max_block.unwrap_or(0);
    println!("dataset: {DEX_SWAP_FACTORS_DATASET}");
    println!("input block window: {min_block}..{max_block}");
    if dry_run {
        println!("factor rows: {}", summary.factor_rows);
        for part in summary.parts {
            println!(
                "{}: rows={} path={}",
                part.dt,
                part.rows,
                part.path.display()
            );
        }
    } else {
        println!("factor rows written: {}", summary.factor_rows);
        println!("target rows: {}", summary.target_rows);
        println!("parquet parts: {}", summary.parquet_parts);
    }
    print_factor_report(&summary.report);
    Ok(())
}

fn rebuild_memecoin(data_root: &Path, dry_run: bool) -> Result<()> {
    let summary = rebuild_memecoin_features(data_root, dry_run)?;
    if summary.event_rows == 0 {
        println!(
            "no dex swap rows found under {}",
            summary.input_root.display()
        );
        return Ok(());
    }

    let min_block = summary.min_block.unwrap_or(0);
    let max_block = summary.max_block.unwrap_or(0);
    println!("datasets: {MEMECOIN_EVENT_FEATURES_DATASET}, {MEMECOIN_HOURLY_FEATURES_DATASET}");
    println!("input block window: {min_block}..{max_block}");
    if dry_run {
        println!("event rows: {}", summary.event_rows);
        println!("hourly rows: {}", summary.hourly_rows);
        for part in summary.parts {
            println!(
                "{}.{}: rows={} path={}",
                part.dataset,
                part.dt,
                part.rows,
                part.path.display()
            );
        }
    } else {
        println!("event rows written: {}", summary.event_rows);
        println!("hourly rows written: {}", summary.hourly_rows);
        println!("parquet parts: {}", summary.parquet_parts);
    }
    Ok(())
}

fn print_factor_report(report: &DexFactorReport) {
    println!();
    println!("invariant diagnostics");
    let diagnostics = &report.invariant_diagnostics;
    println!(
        "delta_sign_invalid={} direction_mismatch={} amount_price_checked={} amount_price_over_1bp={} max_amount_price_bps={}",
        diagnostics.delta_sign_invalid,
        diagnostics.direction_mismatch,
        diagnostics.amount_price_consistency_checked,
        diagnostics.amount_price_consistency_over_1bp,
        fmt_optional(diagnostics.max_amount_price_consistency_bps),
    );
    println!(
        "v3_rows={} v3_terminal_price_rows={} max_execution_vs_terminal_abs_bps={}",
        diagnostics.v3_rows,
        diagnostics.v3_terminal_price_rows,
        fmt_optional(diagnostics.max_execution_vs_terminal_abs_bps),
    );

    if !report.factor_tests.is_empty() {
        println!();
        println!("factor tests vs next same-pool swap log return");
        for test in &report.factor_tests {
            print_factor_test(test);
        }
    }
}

fn print_factor_test(test: &FactorTest) {
    println!(
        "{} n={} buckets={} pearson={} spearman={} top_minus_bottom={}",
        test.factor,
        test.observations,
        test.buckets,
        fmt_optional(test.pearson),
        fmt_optional(test.spearman),
        fmt_optional(test.top_minus_bottom),
    );
}

fn fmt_optional(value: Option<f64>) -> String {
    value
        .map(|value| format!("{value:.8}"))
        .unwrap_or_else(|| "n/a".to_string())
}

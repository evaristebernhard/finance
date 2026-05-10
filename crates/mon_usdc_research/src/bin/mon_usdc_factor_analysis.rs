use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use mon_usdc_research::{
    AnalysisConfig, DEFAULT_DATA_ROOT, DEFAULT_PROGRESS_INTERVAL, DEFAULT_RUN_TAG, run_analysis,
};

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_factor_analysis",
    about = "Build MON/USDC v1 pool, hourly, and event-level factor research outputs."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = DEFAULT_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs")]
    docs_dir: PathBuf,

    #[arg(long)]
    force_derived: bool,

    #[arg(long)]
    no_derived_cache: bool,

    #[arg(long, default_value_t = DEFAULT_PROGRESS_INTERVAL)]
    progress_interval: usize,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_analysis(&AnalysisConfig {
        data_root: args.data_root,
        run_tag: args.run_tag,
        date_dir: args.date_dir,
        docs_dir: args.docs_dir,
        force_derived: args.force_derived,
        no_derived_cache: args.no_derived_cache,
        progress_interval: args.progress_interval,
    })?;
    println!(
        "derived cache: {} schema={} raw_hash={}",
        summary.derived_cache.status,
        summary.derived_cache.schema_version,
        summary.derived_cache.raw_fingerprint_hash
    );
    println!(
        "clean swaps: {} / raw {}",
        summary.coverage.clean_swap_rows, summary.coverage.raw_swap_rows
    );
    println!(
        "quality: missing_event_headers={} missing_receipts={} receipt_request_status_errors={}",
        summary.coverage.missing_event_headers,
        summary.coverage.missing_receipts,
        summary.coverage.receipt_request_status_errors
    );
    println!(
        "wrote {} rows={}",
        summary.outputs.pool_summary, summary.output_rows.pool_summary
    );
    println!(
        "wrote {} rows={}",
        summary.outputs.hourly_market, summary.output_rows.hourly_market
    );
    println!(
        "wrote {} rows={}",
        summary.outputs.hourly_factor_tests, summary.output_rows.hourly_factor_tests
    );
    println!(
        "wrote {} rows={}",
        summary.outputs.event_factor_tests, summary.output_rows.event_factor_tests
    );
    println!("wrote {}", summary.outputs.summary_json);
    Ok(())
}

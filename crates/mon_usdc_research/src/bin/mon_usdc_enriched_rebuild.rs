use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use mon_usdc_research::{
    DEFAULT_DATA_ROOT, DEFAULT_ENRICHMENT_RUN_TAG, DEFAULT_PROGRESS_INTERVAL, EnrichmentConfig,
    run_enrichment_rebuild,
};

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_enriched_rebuild",
    about = "Build MON/USDC v1 enrichment derived datasets and completion reports."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = DEFAULT_ENRICHMENT_RUN_TAG)]
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
    let summary = run_enrichment_rebuild(&EnrichmentConfig {
        data_root: args.data_root,
        run_tag: args.run_tag,
        date_dir: args.date_dir,
        docs_dir: args.docs_dir,
        force_derived: args.force_derived,
        no_derived_cache: args.no_derived_cache,
        progress_interval: args.progress_interval,
    })?;
    println!(
        "base_enrichment_passed={} sample_enrichment_passed={}",
        summary.final_status.base_enrichment_passed, summary.final_status.sample_enrichment_passed
    );
    println!(
        "tx bodies: {}/{} missing={} errors={}",
        summary.coverage.tx_body.written_txs,
        summary.coverage.tx_body.expected_txs,
        summary.coverage.tx_body.missing_txs,
        summary.coverage.tx_body.request_errors
    );
    println!(
        "receipt log bundles: {}/{} logs={} missing={} errors={}",
        summary.coverage.receipt_log_bundle.summary_rows,
        summary.coverage.receipt_log_bundle.expected_txs,
        summary.coverage.receipt_log_bundle.log_rows,
        summary.coverage.receipt_log_bundle.missing_txs,
        summary.coverage.receipt_log_bundle.request_errors
    );
    println!("wrote {}", summary.outputs.completion_json);
    println!("wrote {}", summary.outputs.report);
    Ok(())
}

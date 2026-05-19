use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use mon_usdc_research::{
    DEFAULT_DATA_ROOT, DEFAULT_FACTOR_SEARCH_RUN_TAG, DEFAULT_FACTOR_SOURCE_RUN_TAG,
    DEFAULT_PROGRESS_INTERVAL, EventFactorSearchConfig, run_event_factor_search,
};

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_event_factor_search",
    about = "Build exploratory MON/USDC event physical features, cost labels, and gross factor-map reports."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = DEFAULT_FACTOR_SOURCE_RUN_TAG)]
    source_run_tag: String,

    #[arg(long, default_value = DEFAULT_FACTOR_SEARCH_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs")]
    docs_dir: PathBuf,

    #[arg(long, default_value_t = 30.0)]
    assumed_fee_bps_one_way: f64,

    #[arg(long, default_value_t = DEFAULT_PROGRESS_INTERVAL)]
    progress_interval: usize,

    #[arg(long, default_value_t = 0)]
    eval_workers: usize,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_event_factor_search(&EventFactorSearchConfig {
        data_root: args.data_root,
        source_run_tag: args.source_run_tag,
        run_tag: args.run_tag,
        date_dir: args.date_dir,
        docs_dir: args.docs_dir,
        assumed_fee_bps_one_way: args.assumed_fee_bps_one_way,
        progress_interval: args.progress_interval,
        eval_workers: args.eval_workers,
    })?;
    println!(
        "exploratory_only={} source_run_tag={} run_tag={}",
        summary.exploratory_only, summary.source_run_tag, summary.run_tag
    );
    println!(
        "rows: physical={} cost={} candidates={} gross_summary={} diagnostics={} role_summary={} stability={}",
        summary.output_rows.physical_features,
        summary.output_rows.cost_labels,
        summary.output_rows.factor_candidates,
        summary.output_rows.expression_summary,
        summary.output_rows.tradability_diagnostics,
        summary.output_rows.factor_role_summary,
        summary.output_rows.stability
    );
    println!(
        "eval_workers={} cache_reuse: physical={} cost={} candidates={}",
        summary.eval_workers,
        summary.cache_reuse.physical_features,
        summary.cache_reuse.cost_labels,
        summary.cache_reuse.factor_candidates
    );
    println!("wrote {}", summary.outputs.completion_json);
    println!("wrote {}", summary.outputs.report);
    Ok(())
}

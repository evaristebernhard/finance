use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use mon_usdc_research::{
    DEFAULT_DATA_ROOT, DEFAULT_PATH_REGIME_FEATURE_RUN_TAG, DEFAULT_PATH_REGIME_RUN_TAG,
    DEFAULT_PATH_REGIME_SOURCE_RUN_TAG, DEFAULT_PROGRESS_INTERVAL, PathRegimeConfig,
    run_path_regime_report,
};

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_path_regime_report",
    about = "Build MON/USDC path-regime labels and regime summaries from local derived data."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = DEFAULT_PATH_REGIME_SOURCE_RUN_TAG)]
    source_run_tag: String,

    #[arg(long, default_value = DEFAULT_PATH_REGIME_FEATURE_RUN_TAG)]
    feature_run_tag: String,

    #[arg(long, default_value = DEFAULT_PATH_REGIME_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs")]
    docs_dir: PathBuf,

    #[arg(long, default_value_t = 30.0)]
    fee_bps_one_way: f64,

    #[arg(long, default_value_t = 25.0)]
    slippage_bps_one_way: f64,

    #[arg(long, default_value_t = 25.0)]
    risk_buffer_bps: f64,

    #[arg(long, default_value_t = 0.5)]
    baseline_sigma_multiplier: f64,

    #[arg(long, default_value_t = DEFAULT_PROGRESS_INTERVAL)]
    progress_interval: usize,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_path_regime_report(&PathRegimeConfig {
        data_root: args.data_root,
        source_run_tag: args.source_run_tag,
        feature_run_tag: args.feature_run_tag,
        run_tag: args.run_tag,
        date_dir: args.date_dir,
        docs_dir: args.docs_dir,
        fee_bps_one_way: args.fee_bps_one_way,
        slippage_bps_one_way: args.slippage_bps_one_way,
        risk_buffer_bps: args.risk_buffer_bps,
        baseline_sigma_multiplier: args.baseline_sigma_multiplier,
        progress_interval: args.progress_interval,
    })?;
    println!(
        "joined_research_events={} label_rows_written={}",
        summary.coverage.joined_research_events, summary.coverage.label_rows_written
    );
    println!("wrote {}", summary.outputs.summary_csv);
    println!("wrote {}", summary.outputs.sensitivity_csv);
    println!("wrote {}", summary.outputs.completion_json);
    println!("wrote {}", summary.outputs.report);
    Ok(())
}

use std::path::PathBuf;

use anyhow::Result;
use cex_l2_research::download::DEFAULT_BONK_DATA_ROOT;
use cex_l2_research::price::DEFAULT_PRICE_CONTEXT_RUN_TAG;
use cex_l2_research::research::{ModelReportConfig, run_model_report};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_cex_model_report",
    about = "Run lightweight controlled BONK L2 modeling diagnostics."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_BONK_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs/markets/bonk")]
    doc_dir: PathBuf,

    #[arg(long, default_value = DEFAULT_PRICE_CONTEXT_RUN_TAG)]
    run_tag: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_model_report(&ModelReportConfig {
        data_root: args.data_root,
        date_dir: args.date_dir,
        doc_dir: args.doc_dir,
        run_tag: args.run_tag,
    })?;
    println!("model_metric_rows={}", summary.metric_rows);
    println!("model_stability_rows={}", summary.stability_rows);
    println!("metrics_csv={}", summary.metrics_csv);
    println!("stability_csv={}", summary.stability_csv);
    println!("report_md={}", summary.report_md);
    println!("completion_json={}", summary.completion_json);
    Ok(())
}

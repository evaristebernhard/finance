use std::path::PathBuf;

use anyhow::Result;
use cex_l2_research::download::DEFAULT_BONK_DATA_ROOT;
use cex_l2_research::price::DEFAULT_PRICE_CONTEXT_RUN_TAG;
use cex_l2_research::research::{ResearchPanelConfig, run_research_panel};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_cex_research_panel",
    about = "Build a BONK L2 + labels + covariance + kline context research panel."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_BONK_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = DEFAULT_PRICE_CONTEXT_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = DEFAULT_PRICE_CONTEXT_RUN_TAG)]
    l2_run_tag: String,

    #[arg(long, default_value = DEFAULT_PRICE_CONTEXT_RUN_TAG)]
    price_context_run_tag: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_research_panel(&ResearchPanelConfig {
        data_root: args.data_root,
        date_dir: args.date_dir,
        run_tag: args.run_tag,
        l2_run_tag: args.l2_run_tag,
        price_context_run_tag: args.price_context_run_tag,
    })?;
    println!("panel_rows={}", summary.panel_rows);
    println!("controlled_factor_rows={}", summary.controlled_factor_rows);
    println!("panel_parquet={}", summary.panel_parquet);
    println!("controlled_factor_csv={}", summary.controlled_factor_csv);
    println!("completion_json={}", summary.completion_json);
    Ok(())
}

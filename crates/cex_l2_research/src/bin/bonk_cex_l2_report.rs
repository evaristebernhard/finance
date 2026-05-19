use std::path::PathBuf;

use anyhow::Result;
use cex_l2_research::download::{
    DEFAULT_BONK_DATA_ROOT, DEFAULT_BULLISH_BASKET_RUN_TAG, DEFAULT_BULLISH_BASKET_SYMBOLS,
};
use cex_l2_research::report::{BullishL2ReportConfig, run_bullish_l2_report};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_cex_l2_report",
    about = "Build Rust BONK Bullish CEX L2 state, labels, diagnostics, and report."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_BONK_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs/markets/bonk")]
    doc_dir: PathBuf,

    #[arg(long, default_value = DEFAULT_BULLISH_BASKET_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = DEFAULT_BULLISH_BASKET_SYMBOLS)]
    symbols: String,

    #[arg(long, default_value = "BONK1MUSDC,BONK1MUSDT")]
    label_symbols: String,

    #[arg(long, default_value = "1,4,12")]
    horizons_hours: String,

    #[arg(long, default_value = "50,100,200,300")]
    barriers_bps: String,

    #[arg(long, default_value_t = 1000.0)]
    abnormal_spread_bps: f64,

    #[arg(long, default_value_t = 4)]
    workers: usize,

    #[arg(long, default_value_t = 25)]
    progress_interval: usize,

    #[arg(long)]
    price_context_run_tag: Option<String>,

    #[arg(long)]
    no_price_context: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_bullish_l2_report(&BullishL2ReportConfig {
        data_root: args.data_root,
        date_dir: args.date_dir,
        doc_dir: args.doc_dir,
        run_tag: args.run_tag,
        symbols: args.symbols,
        label_symbols: args.label_symbols,
        horizons_hours: args.horizons_hours,
        barriers_bps: args.barriers_bps,
        abnormal_spread_bps: args.abnormal_spread_bps,
        workers: args.workers,
        progress_interval: args.progress_interval,
        price_context_run_tag: args.price_context_run_tag,
        no_price_context: args.no_price_context,
    })?;
    println!("l2_state_rows={}", summary.rows.l2_state);
    println!("covariance_rows={}", summary.rows.covariance_state);
    println!("label_rows={}", summary.rows.path_labels);
    println!("quality_rows={}", summary.rows.quality);
    println!("factor_tests_rows={}", summary.rows.factor_tests);
    println!("stability_rows={}", summary.rows.stability);
    println!("price_context_status={}", summary.price_context.status);
    println!("completion_json={}", summary.outputs.completion_json);
    println!("report_md={}", summary.outputs.report_md);
    Ok(())
}

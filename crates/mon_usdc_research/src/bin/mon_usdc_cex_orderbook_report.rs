use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use mon_usdc_research::{
    DEFAULT_DATA_ROOT, DEFAULT_ORDERBOOK_RUN_TAG, DEFAULT_PROGRESS_INTERVAL, OrderbookConfig,
    run_orderbook_report,
};

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_cex_orderbook_report",
    about = "Build MON/USDC Binance futures bookDepth/aggTrades order-book diagnostics."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = DEFAULT_ORDERBOOK_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs")]
    docs_dir: PathBuf,

    #[arg(long, default_value = "2026-02-01")]
    expected_start_day: String,

    #[arg(long, default_value = "2026-05-11")]
    expected_end_day: String,

    #[arg(long, default_value_t = DEFAULT_PROGRESS_INTERVAL)]
    progress_interval: usize,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_orderbook_report(&OrderbookConfig {
        data_root: args.data_root,
        run_tag: args.run_tag,
        date_dir: args.date_dir,
        docs_dir: args.docs_dir,
        expected_start_day: args.expected_start_day,
        expected_end_day: args.expected_end_day,
        progress_interval: args.progress_interval,
    })?;
    println!(
        "book_depth_rows={} agg_trade_rows={} joined_rows={}",
        summary.coverage.book_depth_rows,
        summary.coverage.agg_trade_rows,
        summary.coverage.joined_panel_rows
    );
    println!("wrote {}", summary.outputs.orderbook_state_parquet);
    println!("wrote {}", summary.outputs.trade_flow_state_parquet);
    println!("wrote {}", summary.outputs.orderbook_lag_panel_parquet);
    println!("wrote {}", summary.outputs.orderbook_summary_csv);
    println!("wrote {}", summary.outputs.orderbook_factor_tests_csv);
    println!("wrote {}", summary.outputs.report);
    Ok(())
}

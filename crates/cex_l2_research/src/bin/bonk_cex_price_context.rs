use std::path::PathBuf;

use anyhow::Result;
use cex_l2_research::download::{DEFAULT_BONK_DATA_ROOT, DEFAULT_FROM_DATE, DEFAULT_TO_DATE};
use cex_l2_research::price::{
    DEFAULT_BINANCE_KLINE_SYMBOLS, DEFAULT_PRICE_CONTEXT_RUN_TAG, PriceContextConfig,
    run_price_context,
};
use chrono::NaiveDate;
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_cex_price_context",
    about = "Build Binance spot 1m kline price context for the BONK Bullish L2 basket."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_BONK_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "data/mon_usdc/v1/external/binance_klines")]
    local_kline_dir: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value_t = default_from_date())]
    from_date: NaiveDate,

    #[arg(long, default_value_t = default_to_date())]
    to_date: NaiveDate,

    #[arg(long, default_value = DEFAULT_BINANCE_KLINE_SYMBOLS)]
    symbols: String,

    #[arg(long, default_value = DEFAULT_PRICE_CONTEXT_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value_t = 4)]
    workers: usize,

    #[arg(long, default_value_t = 120)]
    timeout_seconds: u64,

    #[arg(long)]
    no_download: bool,

    #[arg(long)]
    force_download: bool,
}

fn default_from_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_FROM_DATE, "%Y-%m-%d").expect("valid default date")
}

fn default_to_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_TO_DATE, "%Y-%m-%d").expect("valid default date")
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_price_context(&PriceContextConfig {
        data_root: args.data_root,
        local_kline_dir: args.local_kline_dir,
        date_dir: args.date_dir,
        from_date: args.from_date,
        to_date: args.to_date,
        symbols: args.symbols,
        run_tag: args.run_tag,
        workers: args.workers,
        timeout_seconds: args.timeout_seconds,
        no_download: args.no_download,
        force_download: args.force_download,
    })?;
    println!("price_context_rows={}", summary.rows.price_context);
    println!("quality_rows={}", summary.rows.quality);
    println!("summary_rows={}", summary.rows.summary);
    println!("completion_json={}", summary.outputs.completion_json);
    println!(
        "price_context_parquet={}",
        summary.outputs.price_context_parquet
    );
    Ok(())
}

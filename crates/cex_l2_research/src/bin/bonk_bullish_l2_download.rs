use std::path::PathBuf;

use anyhow::Result;
use cex_l2_research::download::{
    BullishDownloadConfig, DEFAULT_BONK_DATA_ROOT, DEFAULT_BULLISH_BASKET_RUN_TAG,
    DEFAULT_BULLISH_BASKET_SYMBOLS, DEFAULT_BULLISH_DATA_TYPES, DEFAULT_BULLISH_EXCHANGE,
    DEFAULT_FROM_DATE, DEFAULT_MIN_DOWNLOAD_BYTES_PER_SECOND, DEFAULT_TO_DATE,
    run_bullish_l2_download,
};
use chrono::NaiveDate;
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_bullish_l2_download",
    about = "Download Bullish/Tardis L2 CSV.gz files for the BONK CEX basket."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_BONK_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = ".env.chog.local")]
    env_file: PathBuf,

    #[arg(long, default_value = DEFAULT_BULLISH_EXCHANGE)]
    exchange: String,

    #[arg(long, default_value_t = default_from_date())]
    from_date: NaiveDate,

    #[arg(long, default_value_t = default_to_date())]
    to_date: NaiveDate,

    #[arg(long, default_value = DEFAULT_BULLISH_BASKET_SYMBOLS)]
    symbols: String,

    #[arg(long, default_value = "")]
    extra_symbols: String,

    #[arg(long, default_value = DEFAULT_BULLISH_DATA_TYPES)]
    data_types: String,

    #[arg(long, default_value = DEFAULT_BULLISH_BASKET_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value_t = 120)]
    timeout_seconds: u64,

    #[arg(long, default_value_t = 3)]
    max_retries: usize,

    #[arg(long, default_value_t = 4)]
    workers: usize,

    #[arg(long)]
    skip_preflight: bool,

    #[arg(long, default_value_t = 5.0)]
    min_free_gb: f64,

    #[arg(long)]
    force: bool,

    #[arg(long)]
    dry_run: bool,

    #[arg(long)]
    quick_validate: bool,

    #[arg(long, default_value_t = DEFAULT_MIN_DOWNLOAD_BYTES_PER_SECOND)]
    min_bytes_per_second: u64,

    #[arg(long)]
    api_key: Option<String>,
}

fn default_from_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_FROM_DATE, "%Y-%m-%d").expect("valid default date")
}

fn default_to_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_TO_DATE, "%Y-%m-%d").expect("valid default date")
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_bullish_l2_download(&BullishDownloadConfig {
        exchange: args.exchange,
        data_root: args.data_root,
        date_dir: args.date_dir,
        env_file: args.env_file,
        api_key: args.api_key,
        from_date: args.from_date,
        to_date: args.to_date,
        symbols: args.symbols,
        extra_symbols: args.extra_symbols,
        data_types: args.data_types,
        run_tag: args.run_tag,
        timeout_seconds: args.timeout_seconds,
        max_retries: args.max_retries,
        workers: args.workers,
        skip_preflight: args.skip_preflight,
        min_free_gb: args.min_free_gb,
        force: args.force,
        dry_run: args.dry_run,
        quick_validate: args.quick_validate,
        min_bytes_per_second: args.min_bytes_per_second,
        output_prefix: "bonk_bullish_l2_download".to_string(),
    })?;
    println!("completion_json={}", summary.outputs.completion_json);
    println!("manifest_csv={}", summary.outputs.manifest_csv);
    println!("counts={}", serde_json::to_string(&summary.counts)?);
    if summary.counts.get("error").copied().unwrap_or(0) > 0 {
        std::process::exit(2);
    }
    Ok(())
}

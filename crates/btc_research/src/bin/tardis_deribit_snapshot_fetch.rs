use std::path::PathBuf;

use anyhow::Result;
use btc_research::tardis_deribit::{
    DEFAULT_MAX_RETRIES, DEFAULT_TARDIS_DATA_ROOT, DEFAULT_TARDIS_RUN_TAG,
    TardisDeribitFetchConfig, default_from_date, default_to_date,
    run_tardis_deribit_snapshot_fetch,
};
use chrono::NaiveDate;
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "tardis_deribit_snapshot_fetch",
    about = "Fetch Tardis Deribit options chain and derivative ticker data into BTC/ETH research snapshots."
)]
struct Args {
    #[arg(long, default_value_t = default_from_date())]
    from_date: NaiveDate,

    #[arg(long, default_value_t = default_to_date())]
    to_date: NaiveDate,

    #[arg(long, default_value = ".env.chog.local")]
    env_file: PathBuf,

    #[arg(long, default_value = DEFAULT_TARDIS_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = DEFAULT_TARDIS_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = "BTC,ETH")]
    underlyings: String,

    #[arg(long, default_value_t = 5)]
    snapshot_interval_min: u64,

    #[arg(long, default_value_t = 1)]
    index_interval_min: u64,

    #[arg(long, default_value_t = 700)]
    max_dte: i64,

    #[arg(long, default_value_t = true)]
    keep_raw: bool,

    #[arg(long)]
    delete_raw_after_extract: bool,

    #[arg(long)]
    force: bool,

    #[arg(long)]
    dry_run: bool,

    #[arg(long, default_value_t = 250_000)]
    progress_interval: usize,

    #[arg(long, default_value_t = DEFAULT_MAX_RETRIES)]
    max_retries: usize,

    #[arg(long)]
    api_key: Option<String>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let underlyings = args
        .underlyings
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    let summary = run_tardis_deribit_snapshot_fetch(&TardisDeribitFetchConfig {
        data_root: args.data_root,
        date_dir: args.date_dir,
        env_file: args.env_file,
        api_key: args.api_key,
        from_date: args.from_date,
        to_date: args.to_date,
        underlyings,
        snapshot_interval_min: args.snapshot_interval_min,
        index_interval_min: args.index_interval_min,
        max_dte: args.max_dte,
        keep_raw: args.keep_raw,
        delete_raw_after_extract: args.delete_raw_after_extract,
        force: args.force,
        dry_run: args.dry_run,
        run_tag: args.run_tag,
        progress_interval: args.progress_interval,
        max_retries: args.max_retries,
    })?;
    println!(
        "tardis_deribit run_tag={} dry_run={} days={}",
        summary.run_tag,
        summary.dry_run,
        summary.days.len()
    );
    for day in &summary.days {
        println!(
            "{} status={} option_rows={} index_rows={} raw_status={} error={}",
            day.date,
            day.status,
            day.options_snapshot_rows,
            day.index_ohlc_rows,
            day.options_raw_download_status,
            day.error
        );
    }
    println!("completion_json={}", summary.outputs.completion_json);
    Ok(())
}

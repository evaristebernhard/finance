use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use mon_usdc_research::{
    CexDynamicsConfig, DEFAULT_CEX_DYNAMICS_RUN_TAG, DEFAULT_DATA_ROOT, DEFAULT_PROGRESS_INTERVAL,
    run_cex_dynamics_report,
};

const DEFAULT_SYMBOLS: &str = concat!(
    "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,SUIUSDT,APTUSDT,SEIUSDT,TIAUSDT,",
    "ARBUSDT,OPUSDT,DOGEUSDT,SHIBUSDT,PEPEUSDT,WIFUSDT,BONKUSDT,MONUSDT,MONUSDC"
);

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_cex_dynamics_report",
    about = "Build MON/USDC CEX-driven dynamics and DEX lag diagnostics from local data."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = DEFAULT_CEX_DYNAMICS_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs")]
    docs_dir: PathBuf,

    #[arg(long, default_value = DEFAULT_SYMBOLS)]
    symbols: String,

    #[arg(long, default_value_t = 60)]
    lag_horizon_minutes: u64,

    #[arg(long, default_value_t = 135.0)]
    cost_threshold_bps: f64,

    #[arg(long, default_value_t = DEFAULT_PROGRESS_INTERVAL)]
    progress_interval: usize,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let symbols = args
        .symbols
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect::<Vec<_>>();
    let summary = run_cex_dynamics_report(&CexDynamicsConfig {
        data_root: args.data_root,
        run_tag: args.run_tag,
        date_dir: args.date_dir,
        docs_dir: args.docs_dir,
        symbols,
        lag_horizon_minutes: args.lag_horizon_minutes,
        cost_threshold_bps: args.cost_threshold_bps,
        progress_interval: args.progress_interval,
    })?;
    println!(
        "market_state_rows={} dex_lag_rows={} cex_kline_rows={}",
        summary.coverage.market_state_rows,
        summary.coverage.dex_lag_panel_rows,
        summary.coverage.cex_kline_rows
    );
    println!("wrote {}", summary.outputs.market_state_parquet);
    println!("wrote {}", summary.outputs.dex_lag_panel_parquet);
    println!("wrote {}", summary.outputs.dynamics_summary_csv);
    println!("wrote {}", summary.outputs.dex_lag_summary_csv);
    println!("wrote {}", summary.outputs.report);
    Ok(())
}

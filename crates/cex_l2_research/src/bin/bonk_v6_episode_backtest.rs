use std::path::PathBuf;

use anyhow::{Result, anyhow};
use cex_l2_research::download::DEFAULT_BONK_DATA_ROOT;
use cex_l2_research::episode::{DEFAULT_EPISODE_RUN_TAG, EpisodeConfig, run_episode_backtest};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v6_episode_backtest",
    about = "Run BONK V6 episode backtest from existing L2 parquet outputs."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_BONK_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = DEFAULT_EPISODE_RUN_TAG)]
    run_tag: String,

    #[arg(long)]
    out_tag: Option<String>,

    #[arg(long)]
    panel: Option<PathBuf>,

    #[arg(long)]
    l2_state: Option<PathBuf>,

    #[arg(
        long,
        default_value = "docs/markets/bonk/v1-cex-v6-episode-backtest.md"
    )]
    report_md: PathBuf,

    #[arg(long, default_value = "active_watch")]
    gate_set: String,

    #[arg(long, default_value = "")]
    gates: String,

    #[arg(long, default_value = "30,50,75,100,150")]
    tp_bps: String,

    #[arg(long, default_value = "20,30,50,75,100")]
    sl_bps: String,

    #[arg(long, default_value = "30,60,120,240")]
    timeouts_minutes: String,

    #[arg(
        long,
        default_value = "mid_research,maker_light,taker_spread,wide_stress"
    )]
    execution_models: String,

    #[arg(long, default_value_t = 100.0)]
    notional_quote: f64,

    #[arg(long, default_value_t = 2.0)]
    fee_bps: f64,

    #[arg(long)]
    dry_run: bool,

    #[arg(long)]
    skip_trades_write: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let out_tag = args.out_tag.clone().unwrap_or_else(|| args.run_tag.clone());
    let summary = run_episode_backtest(&EpisodeConfig {
        data_root: args.data_root,
        date_dir: args.date_dir,
        run_tag: args.run_tag,
        out_tag,
        panel_path: args.panel,
        l2_state_path: args.l2_state,
        report_md: args.report_md,
        gate_set: args.gate_set,
        gates: parse_string_list(&args.gates),
        tp_bps: parse_u32_list(&args.tp_bps, "tp-bps")?,
        sl_bps: parse_u32_list(&args.sl_bps, "sl-bps")?,
        timeout_minutes: parse_u32_list(&args.timeouts_minutes, "timeouts-minutes")?,
        execution_models: parse_string_list(&args.execution_models),
        notional_quote: args.notional_quote,
        fee_bps: args.fee_bps,
        dry_run: args.dry_run,
        skip_trades_write: args.skip_trades_write,
    })?;
    println!("out_tag={}", summary.out_tag);
    println!("trades={}", summary.trades);
    println!("daily_rows={}", summary.daily_rows);
    println!("summary_rows={}", summary.summary_rows);
    println!("validation_passed={}", summary.validation_checks.passed);
    println!("trades_csv={}", summary.trades_csv);
    println!("daily_csv={}", summary.daily_csv);
    println!("summary_csv={}", summary.summary_csv);
    println!("completion_json={}", summary.completion_json);
    println!("report_md={}", summary.report_md);
    Ok(())
}

fn parse_string_list(raw: &str) -> Vec<String> {
    raw.split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn parse_u32_list(raw: &str, name: &str) -> Result<Vec<u32>> {
    let mut out = Vec::new();
    for item in raw
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
    {
        let value = item
            .parse::<u32>()
            .map_err(|err| anyhow!("invalid {name} value {item}: {err}"))?;
        if value == 0 {
            return Err(anyhow!("{name} values must be positive"));
        }
        out.push(value);
    }
    out.sort_unstable();
    out.dedup();
    if out.is_empty() {
        return Err(anyhow!("{name} must be non-empty"));
    }
    Ok(out)
}

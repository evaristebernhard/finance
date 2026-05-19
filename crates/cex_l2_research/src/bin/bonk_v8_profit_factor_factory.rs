use std::path::PathBuf;

use anyhow::{Result, anyhow};
use cex_l2_research::download::DEFAULT_BONK_DATA_ROOT;
use cex_l2_research::v8::{DEFAULT_V8_RUN_TAG, V8Config, run_v8_profit_factor_factory};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v8_profit_factor_factory",
    about = "Run the resumable BONK V8 profit-first factor factory over existing derived data."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_BONK_DATA_ROOT)]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = DEFAULT_V8_RUN_TAG)]
    run_tag: String,

    #[arg(long)]
    out_tag: Option<String>,

    #[arg(
        long,
        default_value = "docs/markets/bonk/v1-cex-v8-profit-factor-factory.md"
    )]
    report_md: PathBuf,

    #[arg(long, default_value_t = true)]
    resume: bool,

    #[arg(long)]
    force: bool,

    #[arg(long)]
    stop_after: Option<String>,

    #[arg(long)]
    dry_run: bool,

    #[arg(long)]
    skip_trades_write: bool,

    #[arg(long, default_value = "30,50,75,100")]
    tp_bps: String,

    #[arg(long, default_value = "20,30,50,75")]
    sl_bps: String,

    #[arg(long, default_value = "10,20,30,60")]
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

    #[arg(long, default_value_t = 2)]
    debounce_on_minutes: usize,

    #[arg(long, default_value_t = 2)]
    debounce_off_minutes: usize,

    #[arg(long, default_value_t = 120)]
    cooldown_minutes: usize,

    #[arg(long, default_value_t = 2)]
    min_hold_minutes: usize,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let out_tag = args.out_tag.clone().unwrap_or_else(|| args.run_tag.clone());
    let summary = run_v8_profit_factor_factory(&V8Config {
        data_root: args.data_root,
        date_dir: args.date_dir,
        run_tag: args.run_tag,
        out_tag,
        report_md: args.report_md,
        resume: args.resume,
        force: args.force,
        stop_after: args.stop_after,
        dry_run: args.dry_run,
        skip_trades_write: args.skip_trades_write,
        tp_bps: parse_u32_list(&args.tp_bps, "tp-bps")?,
        sl_bps: parse_u32_list(&args.sl_bps, "sl-bps")?,
        timeout_minutes: parse_u32_list(&args.timeouts_minutes, "timeouts-minutes")?,
        execution_models: parse_string_list(&args.execution_models),
        notional_quote: args.notional_quote,
        fee_bps: args.fee_bps,
        debounce_on_minutes: args.debounce_on_minutes,
        debounce_off_minutes: args.debounce_off_minutes,
        cooldown_minutes: args.cooldown_minutes,
        min_hold_minutes: args.min_hold_minutes,
    })?;
    println!("out_tag={}", summary.out_tag);
    println!("factor_rows={}", summary.factor_rows);
    println!("factor_count={}", summary.factor_count);
    println!("factor_audit_rows={}", summary.factor_audit_rows);
    println!("candidate_fit_rows={}", summary.candidate_fit_rows);
    println!("trades={}", summary.trades);
    println!("daily_rows={}", summary.daily_rows);
    println!("summary_rows={}", summary.summary_rows);
    println!("validation_passed={}", summary.validation_passed);
    println!("manifest_json={}", summary.manifest_json);
    println!("checkpoint_json={}", summary.checkpoint_json);
    println!("factor_panel_parquet={}", summary.factor_panel_parquet);
    println!("factor_audit_csv={}", summary.factor_audit_csv);
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

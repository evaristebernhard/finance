use std::path::PathBuf;

use anyhow::{Result, anyhow};
use cex_l2_research::download::DEFAULT_BONK_DATA_ROOT;
use cex_l2_research::v8::DEFAULT_V8_RUN_TAG;
use cex_l2_research::v9::{V9Config, run_v9_orderbook_potential_filtering};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v9_orderbook_potential_filtering",
    about = "Run the resumable BONK V9 order-book potential/filtering research pipeline."
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
        default_value = "docs/research/bonk/v9-orderbook-potential-filtering-research.md"
    )]
    research_md: PathBuf,

    #[arg(
        long,
        default_value = "docs/markets/bonk/v1-cex-v9-orderbook-potential-filtering.md"
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

    #[arg(long, default_value_t = 100.0)]
    notional_quote: f64,

    #[arg(long, default_value_t = 2.0)]
    fee_bps: f64,

    #[arg(long, default_value_t = 120)]
    cooldown_minutes: usize,

    #[arg(long, default_value_t = 2)]
    min_hold_minutes: usize,

    #[arg(long, default_value_t = 2)]
    debounce_on_minutes: usize,

    #[arg(long, default_value_t = 2)]
    debounce_off_minutes: usize,

    #[arg(long, default_value = "30,50,75")]
    tp_bps: String,

    #[arg(long, default_value = "20,40,60")]
    sl_bps: String,

    #[arg(long, default_value = "10,30,60")]
    timeouts_minutes: String,

    #[arg(
        long,
        default_value = "mid_research,maker_light,taker_spread,wide_stress"
    )]
    execution_models: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let out_tag = args.out_tag.clone().unwrap_or_else(|| args.run_tag.clone());
    let summary = run_v9_orderbook_potential_filtering(&V9Config {
        data_root: args.data_root,
        date_dir: args.date_dir,
        run_tag: args.run_tag,
        out_tag,
        research_md: args.research_md,
        report_md: args.report_md,
        resume: args.resume,
        force: args.force,
        stop_after: args.stop_after,
        dry_run: args.dry_run,
        notional_quote: args.notional_quote,
        fee_bps: args.fee_bps,
        cooldown_minutes: args.cooldown_minutes,
        min_hold_minutes: args.min_hold_minutes,
        debounce_on_minutes: args.debounce_on_minutes,
        debounce_off_minutes: args.debounce_off_minutes,
        tp_bps: parse_u32_list(&args.tp_bps, "tp-bps")?,
        sl_bps: parse_u32_list(&args.sl_bps, "sl-bps")?,
        timeout_minutes: parse_u32_list(&args.timeouts_minutes, "timeouts-minutes")?,
        execution_models: parse_string_list(&args.execution_models),
    })?;
    println!("out_tag={}", summary.out_tag);
    println!("potential_rows={}", summary.potential_rows);
    println!("filter_rows={}", summary.filter_rows);
    println!("anchor_fit_rows={}", summary.anchor_fit_rows);
    println!("trades={}", summary.trades);
    println!("daily_rows={}", summary.daily_rows);
    println!("summary_rows={}", summary.summary_rows);
    println!("spearman_rows={}", summary.spearman_rows);
    println!("negative_control_rows={}", summary.negative_control_rows);
    println!("validation_passed={}", summary.validation_passed);
    println!("manifest_json={}", summary.manifest_json);
    println!("checkpoint_json={}", summary.checkpoint_json);
    println!("potential_state_csv={}", summary.potential_state_csv);
    println!("summary_csv={}", summary.summary_csv);
    println!("completion_json={}", summary.completion_json);
    println!("research_md={}", summary.research_md);
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
        out.push(value);
    }
    if out.is_empty() {
        Err(anyhow!("{name} cannot be empty"))
    } else {
        Ok(out)
    }
}

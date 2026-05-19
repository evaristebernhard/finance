use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

use cex_l2_research::v12::{V12Config, run_v12};

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v12_pending_entry_adaptive_tpsl",
    about = "Research BONK watch-state signals as pending-entry adaptive TP/SL strategies."
)]
struct Args {
    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(
        long,
        default_value = "docs/markets/bonk/v1-cex-v12-pending-entry-adaptive-tpsl.md"
    )]
    report_md: PathBuf,

    #[arg(long, default_value = "20260514_bonk_v10_stage1_pilot")]
    run_tag: String,

    #[arg(long, default_value_t = 2.0)]
    fee_bps: f64,

    #[arg(long, default_value_t = 300)]
    cooldown_seconds: u32,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_v12(&V12Config {
        date_dir: args.date_dir,
        report_md: args.report_md,
        run_tag: args.run_tag,
        fee_bps: args.fee_bps,
        cooldown_seconds: args.cooldown_seconds,
    })?;

    println!("potential_rows={}", summary.potential_rows);
    println!("candidate_rows={}", summary.candidate_rows);
    println!("trade_rows={}", summary.trade_rows);
    println!("summary_rows={}", summary.summary_rows);
    println!("negative_control_rows={}", summary.negative_control_rows);
    println!("primary_status={}", summary.primary_status);
    println!("candidates_csv={}", summary.candidates_csv);
    println!("trades_csv={}", summary.trades_csv);
    println!("summary_csv={}", summary.summary_csv);
    println!("negative_controls_csv={}", summary.negative_controls_csv);
    println!("failure_report_csv={}", summary.failure_report_csv);
    println!("report_md={}", summary.report_md);
    Ok(())
}

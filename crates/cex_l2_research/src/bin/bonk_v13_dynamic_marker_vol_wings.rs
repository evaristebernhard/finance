use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

use cex_l2_research::v13::{V13Config, run_v13};

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v13_dynamic_marker_vol_wings",
    about = "Research BONK V13 dynamic marker and dynamic upper/lower vol wings from V10c event OFI/MLOFI panels."
)]
struct Args {
    #[arg(long, default_value = "data/bonk/v1")]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs/markets/bonk")]
    doc_dir: PathBuf,

    #[arg(long, default_value = "20260514_bonk_v10_stage1_pilot")]
    run_tag: String,

    #[arg(long, default_value_t = 2.0)]
    fee_bps: f64,

    #[arg(long, default_value = "BONK1MUSDC,BONK1MUSDT")]
    symbols: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_v13(&V13Config {
        data_root: args.data_root,
        date_dir: args.date_dir,
        doc_dir: args.doc_dir,
        run_tag: args.run_tag,
        fee_bps: args.fee_bps,
        symbols: args.symbols,
    })?;

    println!("panel_rows={}", summary.panel_rows);
    println!("fold_rows={}", summary.fold_rows);
    println!("signal_rows={}", summary.signal_rows);
    println!("trade_rows={}", summary.trade_rows);
    println!("summary_rows={}", summary.summary_rows);
    println!("negative_control_rows={}", summary.negative_control_rows);
    println!("diagnostic_rows={}", summary.diagnostic_rows);
    println!("primary_status={}", summary.primary_status);
    println!("trades_csv={}", summary.trades_csv);
    println!("summary_csv={}", summary.summary_csv);
    println!("negative_controls_csv={}", summary.negative_controls_csv);
    println!("failure_report_csv={}", summary.failure_report_csv);
    println!("diagnostics_csv={}", summary.diagnostics_csv);
    println!("report_md={}", summary.report_md);
    Ok(())
}

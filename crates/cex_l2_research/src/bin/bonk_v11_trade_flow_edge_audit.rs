use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

use cex_l2_research::v11::{V11Config, run_v11};

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v11_trade_flow_edge_audit",
    about = "Audit whether BONK V10 trade-flow shocks survive a fixed 2 bps cost model."
)]
struct Args {
    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(
        long,
        default_value = "docs/markets/bonk/v1-cex-v11-trade-flow-edge-audit.md"
    )]
    report_md: PathBuf,

    #[arg(long, default_value = "20260514_bonk_v10_stage1_pilot")]
    run_tag: String,

    #[arg(long, default_value_t = 2.0)]
    fee_bps: f64,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_v11(&V11Config {
        date_dir: args.date_dir,
        report_md: args.report_md,
        run_tag: args.run_tag,
        fee_bps: args.fee_bps,
    })?;

    println!("potential_rows={}", summary.potential_rows);
    println!("quality_rows={}", summary.quality_rows);
    println!("side_alignment_rows={}", summary.side_alignment_rows);
    println!("event_study_rows={}", summary.event_study_rows);
    println!("sparse_anchor_rows={}", summary.sparse_anchor_rows);
    println!("after_cost_rows={}", summary.after_cost_rows);
    println!("negative_control_rows={}", summary.negative_control_rows);
    println!("primary_status={}", summary.primary_status);
    println!("side_alignment_csv={}", summary.side_alignment_csv);
    println!("event_study_csv={}", summary.event_study_csv);
    println!("sparse_anchors_csv={}", summary.sparse_anchors_csv);
    println!("after_cost_csv={}", summary.after_cost_csv);
    println!("negative_controls_csv={}", summary.negative_controls_csv);
    println!("failure_report_csv={}", summary.failure_report_csv);
    println!("report_md={}", summary.report_md);
    Ok(())
}

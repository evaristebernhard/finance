use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;

use cex_l2_research::v15::{V15Config, run_v15};

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v15_fib_rsi_book_levels",
    about = "Research BONK V15 dynamic Fibonacci/RSI/orderbook level reaction path diagnostics from V10c event OFI/MLOFI panels."
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
    let summary = run_v15(&V15Config {
        data_root: args.data_root,
        date_dir: args.date_dir,
        doc_dir: args.doc_dir,
        run_tag: args.run_tag,
        fee_bps: args.fee_bps,
        symbols: args.symbols,
    })?;

    println!("panel_rows={}", summary.panel_rows);
    println!("usable_rows={}", summary.usable_rows);
    println!("fold_rows={}", summary.fold_rows);
    println!("level_rows={}", summary.level_rows);
    println!("event_rows={}", summary.event_rows);
    println!("path_profile_rows={}", summary.path_profile_rows);
    println!("summary_rows={}", summary.summary_rows);
    println!("negative_control_rows={}", summary.negative_control_rows);
    println!("diagnostic_rows={}", summary.diagnostic_rows);
    println!("plot_rows={}", summary.plot_rows);
    println!("primary_status={}", summary.primary_status);
    println!("levels_csv={}", summary.levels_csv);
    println!("events_csv={}", summary.events_csv);
    println!("path_profiles_csv={}", summary.path_profiles_csv);
    println!("summary_csv={}", summary.summary_csv);
    println!("negative_controls_csv={}", summary.negative_controls_csv);
    println!("diagnostics_csv={}", summary.diagnostics_csv);
    println!("manifest_csv={}", summary.manifest_csv);
    println!("report_md={}", summary.report_md);
    println!("path_mix_svg={}", summary.path_mix_svg);
    println!("return_svg={}", summary.return_svg);
    println!("control_svg={}", summary.control_svg);
    println!("sample_overlay_svg={}", summary.sample_overlay_svg);
    Ok(())
}

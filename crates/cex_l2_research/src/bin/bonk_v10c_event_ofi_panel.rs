use std::path::PathBuf;

use anyhow::Result;
use chrono::NaiveDate;
use clap::Parser;

use cex_l2_research::v10c::{
    DEFAULT_V10C_FROM_DATE, DEFAULT_V10C_RUN_TAG, DEFAULT_V10C_SYMBOLS, DEFAULT_V10C_TO_DATE,
    V10cConfig, run_v10c,
};

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v10c_event_ofi_panel",
    about = "Build BONK V10c event-defined OFI/MLOFI panels and queue-reactive diagnostics from local Bullish raw files."
)]
struct Args {
    #[arg(long, default_value = "data/bonk/v1")]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs/markets/bonk")]
    doc_dir: PathBuf,

    #[arg(long, default_value_t = default_from_date())]
    from_date: NaiveDate,

    #[arg(long, default_value_t = default_to_date())]
    to_date: NaiveDate,

    #[arg(long, default_value = DEFAULT_V10C_SYMBOLS)]
    symbols: String,

    #[arg(long, default_value = DEFAULT_V10C_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value_t = 25_000)]
    part_rows: usize,

    #[arg(long, default_value_t = 2_000_000)]
    trade_match_window_us: u64,

    #[arg(long, default_value_t = 2_000_000)]
    cross_venue_tolerance_us: u64,

    #[arg(long)]
    max_symbol_days: Option<usize>,

    #[arg(long)]
    skip_panel: bool,

    #[arg(long)]
    skip_validation: bool,

    #[arg(long)]
    skip_episode_overlay: bool,
}

fn default_from_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_V10C_FROM_DATE, "%Y-%m-%d").expect("valid default date")
}

fn default_to_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_V10C_TO_DATE, "%Y-%m-%d").expect("valid default date")
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_v10c(&V10cConfig {
        data_root: args.data_root,
        date_dir: args.date_dir,
        doc_dir: args.doc_dir,
        output_prefix: "bonk_v10c_event_ofi".to_string(),
        panel_dataset: "bonk_v10c_event_ofi_panel".to_string(),
        report_name: "v1-cex-v10c-event-defined-ofi-mlofi.md".to_string(),
        market_label: "BONK".to_string(),
        reproduce_command: "cargo run -p cex_l2_research --bin bonk_v10c_event_ofi_panel --release"
            .to_string(),
        from_date: args.from_date,
        to_date: args.to_date,
        symbols: args.symbols,
        run_tag: args.run_tag,
        part_rows: args.part_rows,
        trade_match_window_us: args.trade_match_window_us,
        cross_venue_tolerance_us: args.cross_venue_tolerance_us,
        max_symbol_days: args.max_symbol_days,
        skip_panel: args.skip_panel,
        skip_validation: args.skip_validation,
        skip_episode_overlay: args.skip_episode_overlay,
    })?;

    println!("symbol_days={}", summary.symbol_days);
    println!("panel_rows={}", summary.panel_rows);
    println!("quality_rows={}", summary.quality_rows);
    println!("factor_param_rows={}", summary.factor_param_rows);
    println!("path_ranking_rows={}", summary.path_ranking_rows);
    println!("stability_rows={}", summary.stability_rows);
    println!("negative_control_rows={}", summary.negative_control_rows);
    println!("spearman_rows={}", summary.spearman_rows);
    println!("episode_overlay_rows={}", summary.episode_overlay_rows);
    println!("quality_csv={}", summary.quality_csv);
    println!("factor_params_csv={}", summary.factor_params_csv);
    println!("path_ranking_csv={}", summary.path_ranking_csv);
    println!("stability_csv={}", summary.stability_csv);
    println!("negative_controls_csv={}", summary.negative_controls_csv);
    println!("spearman_csv={}", summary.spearman_csv);
    println!("episode_overlay_csv={}", summary.episode_overlay_csv);
    println!("report_md={}", summary.report_md);
    Ok(())
}

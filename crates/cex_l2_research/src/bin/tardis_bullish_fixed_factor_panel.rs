use std::path::PathBuf;

use anyhow::Result;
use chrono::NaiveDate;
use clap::Parser;

use cex_l2_research::cc::fixed_event_orderbook::{
    CcFixedEventConfig, run_cc_fixed_event_orderbook,
};

#[derive(Debug, Parser)]
#[command(
    name = "tardis_bullish_fixed_factor_panel",
    about = "Build reusable fixed event-orderbook factor panels from local Tardis Bullish L2/trades files."
)]
struct Args {
    #[arg(long, default_value = "data/ccusdt/v1")]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = "docs/markets/ccusdt")]
    doc_dir: PathBuf,

    #[arg(long, default_value = "ccusdt_v1_fixed_event_factors")]
    output_prefix: String,

    #[arg(long, default_value = "ccusdt_v1_fixed_event_factor_panel")]
    panel_dataset: String,

    #[arg(long, default_value = "v1-fixed-event-orderbook-factors-v3.md")]
    report_name: String,

    #[arg(long, default_value = "CCUSDT")]
    market_label: String,

    #[arg(long, default_value = "2026-04-29")]
    from_date: NaiveDate,

    #[arg(long, default_value = "2026-05-15")]
    to_date: NaiveDate,

    #[arg(long, default_value = "CCUSDT")]
    symbols: String,

    #[arg(long, default_value = "20260517_ccusdt_fixed_factors_v3")]
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

fn main() -> Result<()> {
    let args = Args::parse();
    let reproduce_command = format!(
        "cargo run -p cex_l2_research --bin tardis_bullish_fixed_factor_panel --release -- --data-root {} --date-dir {} --doc-dir {} --output-prefix {} --panel-dataset {} --report-name {} --market-label \"{}\" --from-date {} --to-date {} --symbols {} --run-tag {} --part-rows {} --trade-match-window-us {} --cross-venue-tolerance-us {}",
        args.data_root.display(),
        args.date_dir.display(),
        args.doc_dir.display(),
        args.output_prefix,
        args.panel_dataset,
        args.report_name,
        args.market_label,
        args.from_date,
        args.to_date,
        args.symbols,
        args.run_tag,
        args.part_rows,
        args.trade_match_window_us,
        args.cross_venue_tolerance_us
    );
    let summary = run_cc_fixed_event_orderbook(&CcFixedEventConfig {
        data_root: args.data_root,
        date_dir: args.date_dir,
        doc_dir: args.doc_dir,
        output_prefix: args.output_prefix,
        panel_dataset: args.panel_dataset,
        report_name: args.report_name,
        market_label: args.market_label,
        reproduce_command,
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

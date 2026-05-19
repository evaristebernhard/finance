use std::path::PathBuf;

use anyhow::Result;
use chrono::NaiveDate;
use clap::Parser;

use cex_l2_research::v10::{
    DEFAULT_V10_DATA_TYPES, DEFAULT_V10_FROM_DATE, DEFAULT_V10_RUN_TAG, DEFAULT_V10_SYMBOLS,
    DEFAULT_V10_TO_DATE, V10Config, run_v10,
};

#[derive(Debug, Parser)]
#[command(
    name = "bonk_v10_reconstruction_and_path",
    about = "Build the BONK V10 high-fidelity intake inventory, missing-download plan, and worker shards."
)]
struct Args {
    #[arg(long, default_value = "data/bonk/v1")]
    data_root: PathBuf,

    #[arg(long, default_value = "date")]
    date_dir: PathBuf,

    #[arg(long, default_value = ".env.chog.local")]
    env_file: PathBuf,

    #[arg(long, default_value_t = default_from_date())]
    from_date: NaiveDate,

    #[arg(long, default_value_t = default_to_date())]
    to_date: NaiveDate,

    #[arg(long, default_value = DEFAULT_V10_SYMBOLS)]
    symbols: String,

    #[arg(long, default_value = DEFAULT_V10_DATA_TYPES)]
    data_types: String,

    #[arg(long, default_value = DEFAULT_V10_RUN_TAG)]
    run_tag: String,

    #[arg(long, default_value_t = 4)]
    workers: usize,

    #[arg(long, default_value_t = 120)]
    timeout_seconds: u64,

    #[arg(long, default_value_t = 3)]
    max_retries: usize,

    #[arg(long, default_value_t = 5.0)]
    min_free_gb: f64,

    #[arg(long)]
    skip_preflight: bool,

    #[arg(long)]
    no_resume: bool,

    #[arg(long)]
    force: bool,

    #[arg(long)]
    dry_run: bool,

    #[arg(long)]
    download_missing: bool,

    #[arg(long)]
    max_replay_files: Option<usize>,

    #[arg(long)]
    api_key: Option<String>,

    #[arg(
        long,
        default_value = "docs/research/bonk/v10-data-spec-and-reconstruction-plan.md"
    )]
    research_md: PathBuf,

    #[arg(
        long,
        default_value = "docs/markets/bonk/v1-cex-v10-reconstruction-and-path-report.md"
    )]
    report_md: PathBuf,
}

fn default_from_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_V10_FROM_DATE, "%Y-%m-%d").expect("valid default date")
}

fn default_to_date() -> NaiveDate {
    NaiveDate::parse_from_str(DEFAULT_V10_TO_DATE, "%Y-%m-%d").expect("valid default date")
}

fn main() -> Result<()> {
    let args = Args::parse();
    let summary = run_v10(&V10Config {
        data_root: args.data_root,
        date_dir: args.date_dir,
        env_file: args.env_file,
        api_key: args.api_key,
        from_date: args.from_date,
        to_date: args.to_date,
        symbols: args.symbols,
        data_types: args.data_types,
        run_tag: args.run_tag,
        workers: args.workers,
        timeout_seconds: args.timeout_seconds,
        max_retries: args.max_retries,
        min_free_gb: args.min_free_gb,
        skip_preflight: args.skip_preflight,
        resume: !args.no_resume,
        force: args.force,
        dry_run: args.dry_run,
        download_missing: args.download_missing,
        max_replay_files: args.max_replay_files,
        research_md: args.research_md,
        report_md: args.report_md,
    })?;

    println!("inventory_rows={}", summary.inventory_rows);
    println!("present_rows={}", summary.present_rows);
    println!("missing_rows={}", summary.missing_rows);
    println!("empty_rows={}", summary.empty_rows);
    println!("invalid_rows={}", summary.invalid_rows);
    println!("actionable_rows={}", summary.actionable_rows);
    println!("blocking_rows={}", summary.blocking_rows);
    println!("worker_rows={}", summary.worker_rows);
    println!("replay_state_files={}", summary.replay_state_files);
    println!("replay_preview_rows={}", summary.replay_preview_rows);
    println!(
        "replay_full_summary_rows={}",
        summary.replay_full_summary_rows
    );
    println!("potential_rows={}", summary.potential_rows);
    println!("filter_rows={}", summary.filter_rows);
    println!("anchor_candidates={}", summary.anchor_candidates);
    println!("path_trades={}", summary.path_trades);
    println!("path_summary_rows={}", summary.path_summary_rows);
    println!("negative_control_rows={}", summary.negative_control_rows);
    println!("spearman_rows={}", summary.spearman_rows);
    println!("horizon_decay_rows={}", summary.horizon_decay_rows);
    println!("failure_rows={}", summary.failure_rows);
    println!("download_executed={}", summary.download_executed);
    println!("manifest_json={}", summary.manifest_json);
    println!("checkpoint_json={}", summary.checkpoint_json);
    println!("inventory_csv={}", summary.inventory_csv);
    println!("download_metadata_csv={}", summary.download_metadata_csv);
    println!("worker_shards_csv={}", summary.worker_shards_csv);
    println!(
        "replay_state_manifest_csv={}",
        summary.replay_state_manifest_csv
    );
    println!("replay_preview_csv={}", summary.replay_preview_csv);
    println!(
        "replay_full_summary_csv={}",
        summary.replay_full_summary_csv
    );
    println!("potential_state_csv={}", summary.potential_state_csv);
    println!("filter_params_csv={}", summary.filter_params_csv);
    println!("filter_state_csv={}", summary.filter_rows_csv);
    println!("anchor_candidates_csv={}", summary.anchor_candidates_csv);
    println!("path_trades_csv={}", summary.path_trades_csv);
    println!("path_summary_csv={}", summary.path_summary_csv);
    println!("negative_controls_csv={}", summary.negative_controls_csv);
    println!("spearman_stability_csv={}", summary.spearman_stability_csv);
    println!("horizon_decay_csv={}", summary.horizon_decay_csv);
    println!("failure_report_csv={}", summary.failure_report_csv);
    println!("completion_json={}", summary.completion_json);
    println!("research_md={}", summary.research_md);
    println!("report_md={}", summary.report_md);
    Ok(())
}

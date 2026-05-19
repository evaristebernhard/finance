use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File};
use std::hash::{Hash, Hasher};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use anyhow::{Context, Result, bail};
use chrono::{Datelike, NaiveDate, SecondsFormat, Utc};
use finance_chain_core::storage::ensure_parent_dir;
use flate2::read::GzDecoder;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

use crate::download::{
    BullishDownloadConfig, BullishDownloadSummary, DEFAULT_BONK_DATA_ROOT, FileResult,
    parse_data_types, parse_symbol_list, path_string, run_bullish_l2_download,
};

pub const DEFAULT_V10_RUN_TAG: &str = "20260514_bonk_v10_stage1_pilot";
pub const DEFAULT_V10_FROM_DATE: &str = "2026-05-06";
pub const DEFAULT_V10_TO_DATE: &str = "2026-05-12";
pub const DEFAULT_V10_SYMBOLS: &str = "BONK1MUSDC,BONK1MUSDT";
pub const DEFAULT_V10_DATA_TYPES: &str = "book_snapshot_25,book_ticker,trades,incremental_book_L2";
const DEFAULT_REPLAY_PREVIEW_MAX_ROWS_PER_FILE: usize = 250_000;
const FULL_SUMMARY_PROGRESS_INTERVAL_ROWS: usize = 1_000_000;
const REPLAY_STATE_PART_ROWS: usize = 25_000;
const V10_PURGE_US: u64 = 300_000_000;
const V10_NOTIONAL_QUOTE: f64 = 100.0;
const V10_FEE_BPS: f64 = 2.0;
const V10_ANCHORS: &[&str] = &["pressure_break", "energy_replenish", "microprice_flow"];
const V10_SIDES: &[&str] = &["long", "short"];
const V10_EXECUTION_MODELS: &[&str] = &["maker_light", "taker_spread", "wide_stress"];
const V10_TP_BPS: &[u32] = &[5, 10];
const V10_SL_BPS: &[u32] = &[5, 10];
const V10_TIMEOUT_SECONDS: &[u32] = &[60, 300];
const V10_HORIZON_SECONDS: &[u32] = &[30, 60, 300, 900];

const EXCHANGE: &str = "bullish";
const DATASETS_BASE: &str = "https://datasets.tardis.dev/v1";
const RUN_NAME: &str = "bonk_v10_reconstruction_and_path";
const GUARDRAIL: &str = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim";
const FILE_REPLACE_RETRIES: usize = 120;
const FILE_REPLACE_RETRY_MS: u64 = 500;
static SIDE_CAR_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct V10Config {
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub env_file: PathBuf,
    pub api_key: Option<String>,
    pub from_date: NaiveDate,
    pub to_date: NaiveDate,
    pub symbols: String,
    pub data_types: String,
    pub run_tag: String,
    pub workers: usize,
    pub timeout_seconds: u64,
    pub max_retries: usize,
    pub min_free_gb: f64,
    pub skip_preflight: bool,
    pub resume: bool,
    pub force: bool,
    pub dry_run: bool,
    pub download_missing: bool,
    pub max_replay_files: Option<usize>,
    pub research_md: PathBuf,
    pub report_md: PathBuf,
}

impl Default for V10Config {
    fn default() -> Self {
        Self {
            data_root: PathBuf::from(DEFAULT_BONK_DATA_ROOT),
            date_dir: PathBuf::from("date"),
            env_file: PathBuf::from(".env.chog.local"),
            api_key: None,
            from_date: parse_default_date(DEFAULT_V10_FROM_DATE),
            to_date: parse_default_date(DEFAULT_V10_TO_DATE),
            symbols: DEFAULT_V10_SYMBOLS.to_string(),
            data_types: DEFAULT_V10_DATA_TYPES.to_string(),
            run_tag: DEFAULT_V10_RUN_TAG.to_string(),
            workers: 4,
            timeout_seconds: 120,
            max_retries: 3,
            min_free_gb: 5.0,
            skip_preflight: false,
            resume: true,
            force: false,
            dry_run: false,
            download_missing: false,
            max_replay_files: None,
            research_md: PathBuf::from(
                "docs/research/bonk/v10-data-spec-and-reconstruction-plan.md",
            ),
            report_md: PathBuf::from(
                "docs/markets/bonk/v1-cex-v10-reconstruction-and-path-report.md",
            ),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct V10Summary {
    pub run_tag: String,
    pub from_date: String,
    pub to_date: String,
    pub symbols: Vec<String>,
    pub data_types: Vec<String>,
    pub workers: usize,
    pub inventory_rows: usize,
    pub present_rows: usize,
    pub missing_rows: usize,
    pub empty_rows: usize,
    pub invalid_rows: usize,
    pub actionable_rows: usize,
    pub blocking_rows: usize,
    pub worker_rows: usize,
    pub raw_fingerprint: RawInventoryFingerprint,
    pub download_executed: bool,
    pub download_completion_json: String,
    pub download_manifest_csv: String,
    pub manifest_json: String,
    pub checkpoint_json: String,
    pub inventory_csv: String,
    pub worker_shards_csv: String,
    pub download_metadata_csv: String,
    pub replay_state_manifest_csv: String,
    pub replay_state_files: usize,
    pub replay_preview_csv: String,
    pub replay_preview_rows: usize,
    pub replay_full_summary_csv: String,
    pub replay_full_summary_rows: usize,
    pub potential_state_csv: String,
    pub potential_rows: usize,
    pub filter_params_csv: String,
    pub filter_rows_csv: String,
    pub filter_rows: usize,
    pub anchor_candidates_csv: String,
    pub anchor_candidates: usize,
    pub path_trades_csv: String,
    pub path_trades: usize,
    pub path_summary_csv: String,
    pub path_summary_rows: usize,
    pub negative_controls_csv: String,
    pub negative_control_rows: usize,
    pub spearman_stability_csv: String,
    pub spearman_rows: usize,
    pub horizon_decay_csv: String,
    pub horizon_decay_rows: usize,
    pub failure_report_csv: String,
    pub failure_rows: usize,
    pub completion_json: String,
    pub research_md: String,
    pub report_md: String,
}

#[derive(Debug, Clone)]
struct Paths {
    manifest: PathBuf,
    checkpoint: PathBuf,
    completion: PathBuf,
    inventory_csv: PathBuf,
    worker_shards_csv: PathBuf,
    download_metadata_csv: PathBuf,
    replay_state_manifest_csv: PathBuf,
    replay_preview_csv: PathBuf,
    replay_full_summary_csv: PathBuf,
    potential_state_csv: PathBuf,
    filter_params_csv: PathBuf,
    filter_rows_csv: PathBuf,
    anchor_candidates_csv: PathBuf,
    path_trades_csv: PathBuf,
    path_summary_csv: PathBuf,
    negative_controls_csv: PathBuf,
    spearman_stability_csv: PathBuf,
    horizon_decay_csv: PathBuf,
    failure_report_csv: PathBuf,
}

impl Paths {
    fn new(config: &V10Config) -> Self {
        let prefix = format!("{RUN_NAME}_{}", config.run_tag);
        Self {
            manifest: config.date_dir.join(format!("{prefix}_manifest.json")),
            checkpoint: config.date_dir.join(format!("{prefix}_checkpoint.json")),
            completion: config.date_dir.join(format!("{prefix}_completion.json")),
            inventory_csv: config
                .date_dir
                .join(format!("bonk_v10_raw_inventory_{}.csv", config.run_tag)),
            worker_shards_csv: config
                .date_dir
                .join(format!("bonk_v10_worker_shards_{}.csv", config.run_tag)),
            download_metadata_csv: config
                .date_dir
                .join(format!("bonk_v10_download_metadata_{}.csv", config.run_tag)),
            replay_state_manifest_csv: config.date_dir.join(format!(
                "bonk_v10_replay_state_manifest_{}.csv",
                config.run_tag
            )),
            replay_preview_csv: config.date_dir.join(format!(
                "bonk_v10_incremental_replay_preview_{}.csv",
                config.run_tag
            )),
            replay_full_summary_csv: config.date_dir.join(format!(
                "bonk_v10_incremental_replay_full_summary_{}.csv",
                config.run_tag
            )),
            potential_state_csv: config
                .date_dir
                .join(format!("bonk_v10_potential_state_{}.csv", config.run_tag)),
            filter_params_csv: config
                .date_dir
                .join(format!("bonk_v10_filter_params_{}.csv", config.run_tag)),
            filter_rows_csv: config
                .date_dir
                .join(format!("bonk_v10_filter_state_{}.csv", config.run_tag)),
            anchor_candidates_csv: config
                .date_dir
                .join(format!("bonk_v10_anchor_candidates_{}.csv", config.run_tag)),
            path_trades_csv: config.date_dir.join(format!(
                "bonk_v10_long_short_episode_backtest_{}_trades.csv",
                config.run_tag
            )),
            path_summary_csv: config.date_dir.join(format!(
                "bonk_v10_long_short_episode_backtest_{}_summary.csv",
                config.run_tag
            )),
            negative_controls_csv: config
                .date_dir
                .join(format!("bonk_v10_negative_controls_{}.csv", config.run_tag)),
            spearman_stability_csv: config.date_dir.join(format!(
                "bonk_v10_spearman_stability_{}.csv",
                config.run_tag
            )),
            horizon_decay_csv: config
                .date_dir
                .join(format!("bonk_v10_horizon_decay_{}.csv", config.run_tag)),
            failure_report_csv: config
                .date_dir
                .join(format!("bonk_v10_failure_report_{}.csv", config.run_tag)),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct Manifest {
    run_name: String,
    run_tag: String,
    generated_at_utc: String,
    from_date: String,
    to_date: String,
    symbols: Vec<String>,
    data_types: Vec<String>,
    workers: usize,
    download_missing: bool,
    dry_run: bool,
    guardrail: String,
    inputs: Vec<InputState>,
    outputs: BTreeMap<String, String>,
    steps: Vec<String>,
    resume_checkpoint: String,
}

#[derive(Debug, Clone, Serialize)]
struct InputState {
    path: String,
    exists: bool,
    bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Checkpoint {
    run_tag: String,
    updated_at_utc: String,
    steps: Vec<StepState>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct StepState {
    name: String,
    status: String,
    started_at_utc: String,
    finished_at_utc: Option<String>,
    detail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InventoryRow {
    pub run_tag: String,
    pub date: String,
    pub symbol: String,
    pub data_type: String,
    pub stage: String,
    pub priority: usize,
    pub expected_path: String,
    pub url: String,
    pub exists: bool,
    pub status: String,
    pub bytes: u64,
    pub gzip_ok: bool,
    pub sample_rows: u64,
    pub header_columns: usize,
    pub header_preview: String,
    pub required_schema_ok: bool,
    pub ask_levels: usize,
    pub bid_levels: usize,
    pub note: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownloadMetadataRow {
    pub run_tag: String,
    pub date: String,
    pub symbol: String,
    pub data_type: String,
    pub stage: String,
    pub priority: usize,
    pub local_status: String,
    pub action: String,
    pub blocking_reconstruction: bool,
    pub estimated_compressed_mb: f64,
    pub download_requested: bool,
    pub download_result_status: String,
    pub download_result_bytes: u64,
    pub download_result_error: String,
    pub url: String,
    pub expected_path: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkerShardRow {
    pub run_tag: String,
    pub worker_id: usize,
    pub queue_index: usize,
    pub date: String,
    pub symbol: String,
    pub data_type: String,
    pub stage: String,
    pub action: String,
    pub local_status: String,
    pub blocking_reconstruction: bool,
    pub estimated_compressed_mb: f64,
    pub expected_path: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RawInventoryFingerprint {
    pub file_count: usize,
    pub total_bytes: u64,
    pub hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayPreviewRow {
    pub run_tag: String,
    pub date: String,
    pub symbol: String,
    pub raw_rows_read: usize,
    pub replay_rows: usize,
    pub snapshot_batches: usize,
    pub first_local_timestamp: Option<u64>,
    pub last_local_timestamp: Option<u64>,
    pub avg_bid_levels: f64,
    pub avg_ask_levels: f64,
    pub max_bid_levels: usize,
    pub max_ask_levels: usize,
    pub avg_spread_bps: Option<f64>,
    pub median_spread_bps: Option<f64>,
    pub top_of_book_coverage: f64,
    pub crossed_batches: usize,
    pub crossed_level_removals: usize,
    pub bid_depth_5_mean: f64,
    pub ask_depth_5_mean: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayStateFileRow {
    pub run_tag: String,
    pub date: String,
    pub symbol: String,
    pub raw_path: String,
    pub output_path: String,
    #[serde(default)]
    pub part_files: usize,
    pub raw_rows_read: usize,
    pub replay_rows: usize,
    pub first_local_timestamp: Option<u64>,
    pub last_local_timestamp: Option<u64>,
    pub status: String,
}

#[derive(Debug, Clone, Deserialize)]
struct TradeCsvRow {
    exchange: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    id: String,
    side: String,
    price: f64,
    amount: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10PotentialStateRow {
    run_tag: String,
    date: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    mid_price: Option<f64>,
    spread_bps: Option<f64>,
    microprice: Option<f64>,
    microprice_bps: Option<f64>,
    bid_depth_5: f64,
    ask_depth_5: f64,
    depth_total_5: f64,
    bid_depth_25: f64,
    ask_depth_25: f64,
    depth_total_25: f64,
    imbalance_25: Option<f64>,
    bid_slope_5: Option<f64>,
    ask_slope_5: Option<f64>,
    depth_curvature_5: Option<f64>,
    queue_depth_pressure: Option<f64>,
    cancellation_withdrawal_energy: Option<f64>,
    replenish_relaxation: Option<f64>,
    spread_resistance: Option<f64>,
    microprice_impulse_bps: Option<f64>,
    trade_count: usize,
    trade_buy_amount: f64,
    trade_sell_amount: f64,
    trade_notional_quote: f64,
    trade_flow_imbalance: Option<f64>,
    phi_bid: Option<f64>,
    phi_ask: Option<f64>,
    net_potential: Option<f64>,
    potential_gradient: Option<f64>,
    potential_curvature: Option<f64>,
    energy_release: Option<f64>,
    fill_realism_score: Option<f64>,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10FilterParamRow {
    run_tag: String,
    fold: String,
    symbol: String,
    train_start_local_timestamp: u64,
    train_end_local_timestamp: u64,
    valid_start_local_timestamp: u64,
    valid_end_local_timestamp: u64,
    purge_us: u64,
    train_rows: usize,
    valid_rows: usize,
    net_low: f64,
    net_high: f64,
    energy_high: f64,
    fill_low: f64,
    fill_high: f64,
    flow_abs_high: f64,
    spread_high: f64,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10FilterStateRow {
    run_tag: String,
    fold: String,
    date: String,
    symbol: String,
    timestamp: u64,
    local_timestamp: u64,
    mid_price: Option<f64>,
    spread_bps: Option<f64>,
    net_potential: Option<f64>,
    potential_gradient: Option<f64>,
    potential_curvature: Option<f64>,
    energy_release: Option<f64>,
    fill_realism_score: Option<f64>,
    trade_flow_imbalance: Option<f64>,
    queue_depth_pressure: Option<f64>,
    cancellation_withdrawal_energy: Option<f64>,
    replenish_relaxation: Option<f64>,
    net_bucket_train_fit: String,
    energy_bucket_train_fit: String,
    fill_bucket_train_fit: String,
    flow_bucket_train_fit: String,
    spread_bucket_train_fit: String,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10AnchorCandidateRow {
    run_tag: String,
    fold: String,
    symbol: String,
    anchor_type: String,
    side: String,
    validation_rows: usize,
    selected_rows: usize,
    selected_rate: f64,
    train_fit_rule: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10PathTradeRow {
    run_tag: String,
    fold: String,
    date: String,
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    notional_quote: f64,
    tp_bps: u32,
    sl_bps: u32,
    timeout_seconds: u32,
    signal_local_timestamp: u64,
    entry_local_timestamp: u64,
    exit_local_timestamp: u64,
    entry_mid: f64,
    exit_mid: f64,
    exit_reason: String,
    gross_bps: f64,
    cost_bps: f64,
    queue_penalty_bps: f64,
    fill_realism_score: f64,
    net_bps: f64,
    pnl_quote: f64,
    thresholds_fit_on_train: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10PathSummaryRow {
    run_tag: String,
    summary_scope: String,
    fold: String,
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_seconds: u32,
    trade_count: usize,
    total_pnl_quote: f64,
    avg_net_bps: Option<f64>,
    median_net_bps: Option<f64>,
    win_rate: Option<f64>,
    profit_factor: Option<f64>,
    trades_per_day: f64,
    max_drawdown_quote: f64,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10NegativeControlRow {
    run_tag: String,
    symbol: String,
    anchor_type: String,
    side: String,
    execution_model: String,
    tp_bps: u32,
    sl_bps: u32,
    timeout_seconds: u32,
    control_type: String,
    base_trade_count: usize,
    base_total_pnl_quote: f64,
    control_total_pnl_quote: f64,
    control_note: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10SpearmanRow {
    run_tag: String,
    fold: String,
    symbol: String,
    horizon_seconds: u32,
    feature_name: String,
    spearman: f64,
    abs_spearman: f64,
    n: usize,
    sign: String,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10HorizonDecayRow {
    run_tag: String,
    symbol: String,
    feature_name: String,
    horizon_seconds: u32,
    abs_spearman: f64,
    n: usize,
    decay_rank: usize,
    guardrail: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct V10FailureReportRow {
    run_tag: String,
    severity: String,
    check_name: String,
    evidence: String,
    required_action: String,
    guardrail: String,
}

#[derive(Debug, Clone, Default)]
struct V10DerivedOutputs {
    potential_rows: Vec<V10PotentialStateRow>,
    filter_params: Vec<V10FilterParamRow>,
    filter_rows: Vec<V10FilterStateRow>,
    anchor_candidates: Vec<V10AnchorCandidateRow>,
    path_trades: Vec<V10PathTradeRow>,
    path_summary: Vec<V10PathSummaryRow>,
    negative_controls: Vec<V10NegativeControlRow>,
    spearman_rows: Vec<V10SpearmanRow>,
    horizon_decay: Vec<V10HorizonDecayRow>,
    failure_report: Vec<V10FailureReportRow>,
}

#[derive(Debug, Clone, Serialize)]
struct Completion {
    run_name: String,
    run_tag: String,
    finished_at_utc: String,
    from_date: String,
    to_date: String,
    symbols: Vec<String>,
    data_types: Vec<String>,
    workers: usize,
    inventory_rows: usize,
    present_rows: usize,
    missing_rows: usize,
    empty_rows: usize,
    invalid_rows: usize,
    actionable_rows: usize,
    blocking_rows: usize,
    worker_rows: usize,
    raw_fingerprint: RawInventoryFingerprint,
    download_executed: bool,
    download_completion_json: String,
    download_manifest_csv: String,
    outputs: BTreeMap<String, String>,
    docs: BTreeMap<String, String>,
    notes: Vec<String>,
}

pub fn run_v10(config: &V10Config) -> Result<V10Summary> {
    if config.from_date > config.to_date {
        bail!(
            "--from-date {} is after --to-date {}",
            config.from_date,
            config.to_date
        );
    }
    if config.workers == 0 {
        bail!("--workers must be >= 1");
    }

    fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    ensure_parent_dir(&config.research_md)?;
    ensure_parent_dir(&config.report_md)?;

    let paths = Paths::new(config);
    write_manifest(config, &paths)?;
    let mut checkpoint = load_checkpoint(&paths.checkpoint, config)?;
    let symbols = parse_symbol_list(&config.symbols);
    let data_types = parse_data_types(&config.data_types);

    let mut inventory_rows = if can_reuse_step(
        &checkpoint,
        "inventory_local_raw",
        config,
        &[&paths.inventory_csv],
    )? {
        load_csv_rows::<InventoryRow>(&paths.inventory_csv)?
    } else {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "inventory_local_raw",
            "running",
            "scan local Bullish raw shards",
        )?;
        let rows = scan_inventory(config, &symbols, &data_types)?;
        write_csv_atomic(&paths.inventory_csv, &rows)?;
        let detail = format!(
            "rows={} present={} missing={} empty={} invalid={}",
            rows.len(),
            rows.iter().filter(|row| row.status == "present").count(),
            rows.iter().filter(|row| row.status == "missing").count(),
            rows.iter().filter(|row| row.status == "empty").count(),
            rows.iter().filter(|row| row.status == "invalid").count(),
        );
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "inventory_local_raw",
            "completed",
            &detail,
        )?;
        rows
    };

    let mut download_metadata_rows = build_download_metadata(config, &inventory_rows, None);
    if config.download_missing && has_actionable_rows(&download_metadata_rows) && !config.dry_run {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "download_missing",
            "running",
            "download actionable missing or invalid raw shards",
        )?;
        let download = run_download(config, &download_metadata_rows)?;
        inventory_rows = scan_inventory(config, &symbols, &data_types)?;
        write_csv_atomic(&paths.inventory_csv, &inventory_rows)?;
        download_metadata_rows =
            build_download_metadata(config, &inventory_rows, Some(&download.files));
        let detail = format!(
            "downloaded_counts={}",
            serde_json::to_string(&download.counts).unwrap_or_else(|_| "{}".to_string())
        );
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "download_missing",
            "completed",
            &detail,
        )?;
        write_csv_atomic(&paths.download_metadata_csv, &download_metadata_rows)?;
        let worker_rows = build_worker_shards(config, &download_metadata_rows);
        write_csv_atomic(&paths.worker_shards_csv, &worker_rows)?;
        let replay_state_files =
            build_replay_state_files_incremental(config, &paths, &mut checkpoint, &inventory_rows)?;
        let replay_preview_rows = build_replay_preview_rows(config, &inventory_rows)?;
        if !replay_preview_rows.is_empty() {
            write_csv_atomic(&paths.replay_preview_csv, &replay_preview_rows)?;
        }
        let replay_full_summary_rows =
            build_replay_full_summary_rows_from_state_manifest(config, &replay_state_files)?;
        if !replay_full_summary_rows.is_empty() {
            write_csv_atomic(&paths.replay_full_summary_csv, &replay_full_summary_rows)?;
        }
        let derived_outputs =
            build_v10_derived_outputs(config, &paths, &mut checkpoint, &replay_state_files)?;
        let summary = finalize_summary(
            config,
            &paths,
            inventory_rows,
            download_metadata_rows,
            worker_rows,
            replay_state_files,
            replay_preview_rows,
            replay_full_summary_rows,
            derived_outputs,
            Some(download),
        )?;
        write_json_atomic(
            &paths.completion,
            &build_completion(config, &paths, &summary),
        )?;
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "write_completion",
            "completed",
            "completion written",
        )?;
        return Ok(summary);
    }

    if !step_completed(&checkpoint, "download_missing") {
        let detail = if config.download_missing && config.dry_run {
            "download requested but skipped because --dry-run is active"
        } else if config.download_missing {
            "download requested but no actionable shards were found"
        } else {
            "download step disabled"
        };
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "download_missing",
            "completed",
            detail,
        )?;
    }

    if !can_reuse_step(
        &checkpoint,
        "plan_download_metadata",
        config,
        &[&paths.download_metadata_csv],
    )? {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "plan_download_metadata",
            "running",
            "build staged missing-download metadata",
        )?;
        write_csv_atomic(&paths.download_metadata_csv, &download_metadata_rows)?;
        let detail = format!(
            "rows={} actionable={} blocking={}",
            download_metadata_rows.len(),
            download_metadata_rows
                .iter()
                .filter(|row| row.action != "keep_local")
                .count(),
            download_metadata_rows
                .iter()
                .filter(|row| row.blocking_reconstruction)
                .count(),
        );
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "plan_download_metadata",
            "completed",
            &detail,
        )?;
    } else {
        download_metadata_rows =
            load_csv_rows::<DownloadMetadataRow>(&paths.download_metadata_csv)?;
    }

    let worker_rows = if can_reuse_step(
        &checkpoint,
        "plan_worker_shards",
        config,
        &[&paths.worker_shards_csv],
    )? {
        load_csv_rows::<WorkerShardRow>(&paths.worker_shards_csv)?
    } else {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "plan_worker_shards",
            "running",
            "assign worker queues for local-ready and missing-download shards",
        )?;
        let rows = build_worker_shards(config, &download_metadata_rows);
        write_csv_atomic(&paths.worker_shards_csv, &rows)?;
        let detail = format!("rows={} workers={}", rows.len(), config.workers);
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "plan_worker_shards",
            "completed",
            &detail,
        )?;
        rows
    };

    let replay_state_files =
        build_replay_state_files_incremental(config, &paths, &mut checkpoint, &inventory_rows)?;

    let replay_preview_rows = if can_reuse_step(
        &checkpoint,
        "replay_incremental_preview",
        config,
        &[&paths.replay_preview_csv],
    )? {
        load_csv_rows::<ReplayPreviewRow>(&paths.replay_preview_csv)?
    } else {
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "replay_incremental_preview",
            "running",
            "build incremental replay preview summary for locally present pilot shards",
        )?;
        let rows = build_replay_preview_rows(config, &inventory_rows)?;
        if !rows.is_empty() {
            write_csv_atomic(&paths.replay_preview_csv, &rows)?;
        }
        let detail = if rows.is_empty() {
            "no present incremental_book_L2 shards to replay".to_string()
        } else {
            format!("rows={} source_files={}", rows.len(), rows.len())
        };
        update_checkpoint(
            &mut checkpoint,
            &paths.checkpoint,
            "replay_incremental_preview",
            "completed",
            &detail,
        )?;
        rows
    };

    let replay_full_summary_rows = build_replay_full_summary_rows_incremental(
        config,
        &paths,
        &mut checkpoint,
        &replay_state_files,
    )?;

    let derived_outputs =
        build_v10_derived_outputs(config, &paths, &mut checkpoint, &replay_state_files)?;

    update_checkpoint(
        &mut checkpoint,
        &paths.checkpoint,
        "write_completion",
        "running",
        "finalize V10 stage-1 intake summary",
    )?;
    let summary = finalize_summary(
        config,
        &paths,
        inventory_rows,
        download_metadata_rows,
        worker_rows,
        replay_state_files,
        replay_preview_rows,
        replay_full_summary_rows,
        derived_outputs,
        None,
    )?;
    write_json_atomic(
        &paths.completion,
        &build_completion(config, &paths, &summary),
    )?;
    update_checkpoint(
        &mut checkpoint,
        &paths.checkpoint,
        "write_completion",
        "completed",
        "completion written",
    )?;
    Ok(summary)
}

fn finalize_summary(
    config: &V10Config,
    paths: &Paths,
    inventory_rows: Vec<InventoryRow>,
    download_metadata_rows: Vec<DownloadMetadataRow>,
    worker_rows: Vec<WorkerShardRow>,
    replay_state_files: Vec<ReplayStateFileRow>,
    replay_preview_rows: Vec<ReplayPreviewRow>,
    replay_full_summary_rows: Vec<ReplayPreviewRow>,
    derived_outputs: V10DerivedOutputs,
    download: Option<BullishDownloadSummary>,
) -> Result<V10Summary> {
    let raw_fingerprint = fingerprint_inventory(&inventory_rows);
    let present_rows = inventory_rows
        .iter()
        .filter(|row| row.status == "present")
        .count();
    let missing_rows = inventory_rows
        .iter()
        .filter(|row| row.status == "missing")
        .count();
    let empty_rows = inventory_rows
        .iter()
        .filter(|row| row.status == "empty")
        .count();
    let invalid_rows = inventory_rows
        .iter()
        .filter(|row| row.status == "invalid")
        .count();
    let actionable_rows = download_metadata_rows
        .iter()
        .filter(|row| row.action != "keep_local")
        .count();
    let blocking_rows = download_metadata_rows
        .iter()
        .filter(|row| row.blocking_reconstruction)
        .count();
    let (download_executed, download_completion_json, download_manifest_csv) =
        if let Some(run) = download {
            (true, run.outputs.completion_json, run.outputs.manifest_csv)
        } else {
            (false, String::new(), String::new())
        };
    let _filter_param_rows = derived_outputs.filter_params.len();
    Ok(V10Summary {
        run_tag: config.run_tag.clone(),
        from_date: config.from_date.to_string(),
        to_date: config.to_date.to_string(),
        symbols: parse_symbol_list(&config.symbols),
        data_types: parse_data_types(&config.data_types),
        workers: config.workers,
        inventory_rows: inventory_rows.len(),
        present_rows,
        missing_rows,
        empty_rows,
        invalid_rows,
        actionable_rows,
        blocking_rows,
        worker_rows: worker_rows.len(),
        raw_fingerprint,
        download_executed,
        download_completion_json,
        download_manifest_csv,
        manifest_json: path_string(&paths.manifest),
        checkpoint_json: path_string(&paths.checkpoint),
        inventory_csv: path_string(&paths.inventory_csv),
        worker_shards_csv: path_string(&paths.worker_shards_csv),
        download_metadata_csv: path_string(&paths.download_metadata_csv),
        replay_state_manifest_csv: path_string(&paths.replay_state_manifest_csv),
        replay_state_files: replay_state_files.len(),
        replay_preview_csv: path_string(&paths.replay_preview_csv),
        replay_preview_rows: replay_preview_rows.len(),
        replay_full_summary_csv: path_string(&paths.replay_full_summary_csv),
        replay_full_summary_rows: replay_full_summary_rows.len(),
        potential_state_csv: path_string(&paths.potential_state_csv),
        potential_rows: derived_outputs.potential_rows.len(),
        filter_params_csv: path_string(&paths.filter_params_csv),
        filter_rows_csv: path_string(&paths.filter_rows_csv),
        filter_rows: derived_outputs.filter_rows.len(),
        anchor_candidates_csv: path_string(&paths.anchor_candidates_csv),
        anchor_candidates: derived_outputs.anchor_candidates.len(),
        path_trades_csv: path_string(&paths.path_trades_csv),
        path_trades: derived_outputs.path_trades.len(),
        path_summary_csv: path_string(&paths.path_summary_csv),
        path_summary_rows: derived_outputs.path_summary.len(),
        negative_controls_csv: path_string(&paths.negative_controls_csv),
        negative_control_rows: derived_outputs.negative_controls.len(),
        spearman_stability_csv: path_string(&paths.spearman_stability_csv),
        spearman_rows: derived_outputs.spearman_rows.len(),
        horizon_decay_csv: path_string(&paths.horizon_decay_csv),
        horizon_decay_rows: derived_outputs.horizon_decay.len(),
        failure_report_csv: path_string(&paths.failure_report_csv),
        failure_rows: derived_outputs.failure_report.len(),
        completion_json: path_string(&paths.completion),
        research_md: path_string(&config.research_md),
        report_md: path_string(&config.report_md),
    })
}

fn build_completion(config: &V10Config, paths: &Paths, summary: &V10Summary) -> Completion {
    let mut outputs = BTreeMap::new();
    outputs.insert("manifest".to_string(), path_string(&paths.manifest));
    outputs.insert("checkpoint".to_string(), path_string(&paths.checkpoint));
    outputs.insert(
        "inventory_csv".to_string(),
        path_string(&paths.inventory_csv),
    );
    outputs.insert(
        "download_metadata_csv".to_string(),
        path_string(&paths.download_metadata_csv),
    );
    outputs.insert(
        "replay_state_manifest_csv".to_string(),
        path_string(&paths.replay_state_manifest_csv),
    );
    outputs.insert(
        "worker_shards_csv".to_string(),
        path_string(&paths.worker_shards_csv),
    );
    outputs.insert(
        "replay_preview_csv".to_string(),
        path_string(&paths.replay_preview_csv),
    );
    outputs.insert(
        "replay_full_summary_csv".to_string(),
        path_string(&paths.replay_full_summary_csv),
    );
    outputs.insert(
        "potential_state_csv".to_string(),
        path_string(&paths.potential_state_csv),
    );
    outputs.insert(
        "filter_params_csv".to_string(),
        path_string(&paths.filter_params_csv),
    );
    outputs.insert(
        "filter_state_csv".to_string(),
        path_string(&paths.filter_rows_csv),
    );
    outputs.insert(
        "anchor_candidates_csv".to_string(),
        path_string(&paths.anchor_candidates_csv),
    );
    outputs.insert(
        "path_trades_csv".to_string(),
        path_string(&paths.path_trades_csv),
    );
    outputs.insert(
        "path_summary_csv".to_string(),
        path_string(&paths.path_summary_csv),
    );
    outputs.insert(
        "negative_controls_csv".to_string(),
        path_string(&paths.negative_controls_csv),
    );
    outputs.insert(
        "spearman_stability_csv".to_string(),
        path_string(&paths.spearman_stability_csv),
    );
    outputs.insert(
        "horizon_decay_csv".to_string(),
        path_string(&paths.horizon_decay_csv),
    );
    outputs.insert(
        "failure_report_csv".to_string(),
        path_string(&paths.failure_report_csv),
    );
    outputs.insert("completion".to_string(), path_string(&paths.completion));

    let mut docs = BTreeMap::new();
    docs.insert("research_doc".to_string(), path_string(&config.research_md));
    docs.insert("report_doc".to_string(), path_string(&config.report_md));

    let expected_replay_state_files = date_range(config.from_date, config.to_date).len()
        * parse_symbol_list(&config.symbols).len();
    let replay_diagnostics_note = if expected_replay_state_files > 0
        && summary.replay_state_files >= expected_replay_state_files
    {
        format!(
            "Queue-level replay-derived potential, movable-anchor episodes, and after-cost diagnostics are materialized for the fixed pilot ({}/{} replay state files).",
            summary.replay_state_files, expected_replay_state_files
        )
    } else {
        format!(
            "Queue-level replay-derived potential, movable-anchor episodes, and after-cost diagnostics are materialized for completed replay state files; full-pilot coverage still depends on replaying all incremental shards ({}/{} replay state files).",
            summary.replay_state_files, expected_replay_state_files
        )
    };

    let notes = vec![
        "Stage-1 V10 focuses on local raw inventory, missing-download planning, and worker shard scheduling.".to_string(),
        format!(
            "Replayed book-state files currently materialized: {}.",
            summary.replay_state_files
        ),
        replay_diagnostics_note,
        format!(
            "Incremental replay preview rows currently materialized: {}.",
            summary.replay_preview_rows
        ),
        format!(
            "Incremental replay full-summary rows currently materialized: {}.",
            summary.replay_full_summary_rows
        ),
        format!(
            "Potential/filter/path diagnostic rows currently materialized: potential={} filter={} trades={} summaries={} controls={} spearman={} failures={}.",
            summary.potential_rows,
            summary.filter_rows,
            summary.path_trades,
            summary.path_summary_rows,
            summary.negative_control_rows,
            summary.spearman_rows,
            summary.failure_rows
        ),
    ];

    Completion {
        run_name: RUN_NAME.to_string(),
        run_tag: summary.run_tag.clone(),
        finished_at_utc: utc_now_string(),
        from_date: summary.from_date.clone(),
        to_date: summary.to_date.clone(),
        symbols: summary.symbols.clone(),
        data_types: summary.data_types.clone(),
        workers: summary.workers,
        inventory_rows: summary.inventory_rows,
        present_rows: summary.present_rows,
        missing_rows: summary.missing_rows,
        empty_rows: summary.empty_rows,
        invalid_rows: summary.invalid_rows,
        actionable_rows: summary.actionable_rows,
        blocking_rows: summary.blocking_rows,
        worker_rows: summary.worker_rows,
        raw_fingerprint: summary.raw_fingerprint.clone(),
        download_executed: summary.download_executed,
        download_completion_json: summary.download_completion_json.clone(),
        download_manifest_csv: summary.download_manifest_csv.clone(),
        outputs,
        docs,
        notes,
    }
}

fn can_reuse_step(
    checkpoint: &Checkpoint,
    step: &str,
    config: &V10Config,
    outputs: &[&Path],
) -> Result<bool> {
    if config.force || !config.resume {
        return Ok(false);
    }
    if !step_completed(checkpoint, step) {
        return Ok(false);
    }
    for output in outputs {
        if !output.exists() {
            return Ok(false);
        }
    }
    Ok(true)
}

fn step_completed(checkpoint: &Checkpoint, step: &str) -> bool {
    checkpoint
        .steps
        .iter()
        .find(|state| state.name == step)
        .is_some_and(|state| state.status == "completed")
}

fn load_checkpoint(path: &Path, config: &V10Config) -> Result<Checkpoint> {
    if path.exists() {
        let file =
            File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
        let checkpoint: Checkpoint = serde_json::from_reader(file)
            .with_context(|| format!("failed to parse {}", path.display()))?;
        if checkpoint.run_tag == config.run_tag {
            return Ok(checkpoint);
        }
    }
    Ok(Checkpoint {
        run_tag: config.run_tag.clone(),
        updated_at_utc: utc_now_string(),
        steps: Vec::new(),
    })
}

fn update_checkpoint(
    checkpoint: &mut Checkpoint,
    path: &Path,
    step: &str,
    status: &str,
    detail: &str,
) -> Result<()> {
    let now = utc_now_string();
    if let Some(existing) = checkpoint.steps.iter_mut().find(|state| state.name == step) {
        if existing.status != "completed" {
            existing.started_at_utc = now.clone();
        }
        existing.status = status.to_string();
        existing.detail = detail.to_string();
        existing.finished_at_utc = if status == "completed" {
            Some(now.clone())
        } else {
            None
        };
    } else {
        checkpoint.steps.push(StepState {
            name: step.to_string(),
            status: status.to_string(),
            started_at_utc: now.clone(),
            finished_at_utc: if status == "completed" {
                Some(now.clone())
            } else {
                None
            },
            detail: detail.to_string(),
        });
    }
    checkpoint.updated_at_utc = now;
    write_json_atomic(path, checkpoint)
}

fn write_manifest(config: &V10Config, paths: &Paths) -> Result<()> {
    let symbols = parse_symbol_list(&config.symbols);
    let data_types = parse_data_types(&config.data_types);
    let inputs = vec![
        input_state(&config.data_root),
        input_state(&config.data_root.join("external")),
        input_state(&config.research_md),
        input_state(&config.report_md),
    ];
    let mut outputs = BTreeMap::new();
    outputs.insert("manifest".to_string(), path_string(&paths.manifest));
    outputs.insert("checkpoint".to_string(), path_string(&paths.checkpoint));
    outputs.insert("completion".to_string(), path_string(&paths.completion));
    outputs.insert(
        "inventory_csv".to_string(),
        path_string(&paths.inventory_csv),
    );
    outputs.insert(
        "download_metadata_csv".to_string(),
        path_string(&paths.download_metadata_csv),
    );
    outputs.insert(
        "replay_state_manifest_csv".to_string(),
        path_string(&paths.replay_state_manifest_csv),
    );
    outputs.insert(
        "worker_shards_csv".to_string(),
        path_string(&paths.worker_shards_csv),
    );
    outputs.insert(
        "replay_preview_csv".to_string(),
        path_string(&paths.replay_preview_csv),
    );
    outputs.insert(
        "replay_full_summary_csv".to_string(),
        path_string(&paths.replay_full_summary_csv),
    );
    outputs.insert(
        "potential_state_csv".to_string(),
        path_string(&paths.potential_state_csv),
    );
    outputs.insert(
        "filter_params_csv".to_string(),
        path_string(&paths.filter_params_csv),
    );
    outputs.insert(
        "filter_state_csv".to_string(),
        path_string(&paths.filter_rows_csv),
    );
    outputs.insert(
        "anchor_candidates_csv".to_string(),
        path_string(&paths.anchor_candidates_csv),
    );
    outputs.insert(
        "path_trades_csv".to_string(),
        path_string(&paths.path_trades_csv),
    );
    outputs.insert(
        "path_summary_csv".to_string(),
        path_string(&paths.path_summary_csv),
    );
    outputs.insert(
        "negative_controls_csv".to_string(),
        path_string(&paths.negative_controls_csv),
    );
    outputs.insert(
        "spearman_stability_csv".to_string(),
        path_string(&paths.spearman_stability_csv),
    );
    outputs.insert(
        "horizon_decay_csv".to_string(),
        path_string(&paths.horizon_decay_csv),
    );
    outputs.insert(
        "failure_report_csv".to_string(),
        path_string(&paths.failure_report_csv),
    );
    outputs.insert("research_doc".to_string(), path_string(&config.research_md));
    outputs.insert("report_doc".to_string(), path_string(&config.report_md));
    let manifest = Manifest {
        run_name: RUN_NAME.to_string(),
        run_tag: config.run_tag.clone(),
        generated_at_utc: utc_now_string(),
        from_date: config.from_date.to_string(),
        to_date: config.to_date.to_string(),
        symbols,
        data_types,
        workers: config.workers,
        download_missing: config.download_missing,
        dry_run: config.dry_run,
        guardrail: GUARDRAIL.to_string(),
        inputs,
        outputs,
        steps: vec![
            "inventory_local_raw".to_string(),
            "download_missing".to_string(),
            "plan_download_metadata".to_string(),
            "plan_worker_shards".to_string(),
            "replay_book_state_files".to_string(),
            "replay_incremental_preview".to_string(),
            "replay_incremental_full_summary".to_string(),
            "potential_state".to_string(),
            "train_purged_filter_state".to_string(),
            "movable_anchor_path_backtest".to_string(),
            "negative_controls".to_string(),
            "spearman_horizon_decay".to_string(),
            "failure_report".to_string(),
            "write_completion".to_string(),
        ],
        resume_checkpoint: path_string(&paths.checkpoint),
    };
    write_json_atomic(&paths.manifest, &manifest)
}

fn input_state(path: &Path) -> InputState {
    let exists = path.exists();
    let bytes = if exists {
        fs::metadata(path).map(|meta| meta.len()).unwrap_or(0)
    } else {
        0
    };
    InputState {
        path: path_string(path),
        exists,
        bytes,
    }
}

fn scan_inventory(
    config: &V10Config,
    symbols: &[String],
    data_types: &[String],
) -> Result<Vec<InventoryRow>> {
    let dates = date_range(config.from_date, config.to_date);
    let mut rows = Vec::new();
    for day in dates {
        for symbol in symbols {
            for data_type in data_types {
                let path = raw_path(&config.data_root, data_type, day, symbol);
                let url = dataset_url(data_type, day, symbol);
                let mut status = "missing".to_string();
                let mut bytes = 0u64;
                let mut gzip_ok = false;
                let mut sample_rows = 0u64;
                let mut header = Vec::new();
                let mut note = default_note(data_type, "missing");
                if path.exists() {
                    bytes = path.metadata().map(|meta| meta.len()).unwrap_or(0);
                    match quick_validate_gzip_csv(&path) {
                        Ok(validation) => {
                            gzip_ok = validation.gzip_ok;
                            sample_rows = validation.sample_rows;
                            status = classify_inventory_status(&validation);
                            header = validation.header;
                            note = if validation.error.is_empty() {
                                default_note(data_type, &status)
                            } else {
                                validation.error
                            };
                        }
                        Err(err) => {
                            status = "invalid".to_string();
                            note = err.to_string();
                        }
                    }
                }
                let ask_levels = detect_levels(&header, "asks");
                let bid_levels = detect_levels(&header, "bids");
                let required_schema_ok = status == "present"
                    && validate_required_schema(data_type, &header, ask_levels, bid_levels);
                if status == "present" && !required_schema_ok {
                    status = "invalid".to_string();
                    note = "present gzip but missing required reconstruction columns".to_string();
                }
                rows.push(InventoryRow {
                    run_tag: config.run_tag.clone(),
                    date: day.to_string(),
                    symbol: symbol.clone(),
                    data_type: data_type.clone(),
                    stage: stage_for_data_type(data_type).to_string(),
                    priority: priority_for_inventory(data_type, &status),
                    expected_path: path_string(&path),
                    url,
                    exists: path.exists(),
                    status,
                    bytes,
                    gzip_ok,
                    sample_rows,
                    header_columns: header.len(),
                    header_preview: header
                        .iter()
                        .take(12)
                        .cloned()
                        .collect::<Vec<_>>()
                        .join("|"),
                    required_schema_ok,
                    ask_levels,
                    bid_levels,
                    note,
                });
            }
        }
    }
    rows.sort_by(|a, b| {
        a.priority
            .cmp(&b.priority)
            .then_with(|| a.date.cmp(&b.date))
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.data_type.cmp(&b.data_type))
    });
    Ok(rows)
}

fn build_download_metadata(
    config: &V10Config,
    inventory_rows: &[InventoryRow],
    download_results: Option<&[FileResult]>,
) -> Vec<DownloadMetadataRow> {
    let mut by_key = HashMap::<(String, String, String), FileResult>::new();
    if let Some(results) = download_results {
        for result in results {
            by_key.insert(
                (
                    result.date.clone(),
                    result.symbol.clone(),
                    result.data_type.clone(),
                ),
                result.clone(),
            );
        }
    }
    let mut rows = inventory_rows
        .iter()
        .map(|row| {
            let action = action_for_inventory(row);
            let blocking_reconstruction =
                action != "keep_local" && row.data_type == "incremental_book_L2";
            let reason = reason_for_action(row, action);
            let result = by_key.get(&(row.date.clone(), row.symbol.clone(), row.data_type.clone()));
            let estimated_compressed_mb = if row.bytes > 0 {
                row.bytes as f64 / 1_000_000.0
            } else {
                default_estimated_mb(&row.data_type)
            };
            DownloadMetadataRow {
                run_tag: config.run_tag.clone(),
                date: row.date.clone(),
                symbol: row.symbol.clone(),
                data_type: row.data_type.clone(),
                stage: row.stage.clone(),
                priority: row.priority,
                local_status: row.status.clone(),
                action: action.to_string(),
                blocking_reconstruction,
                estimated_compressed_mb,
                download_requested: config.download_missing,
                download_result_status: result.map(|item| item.status.clone()).unwrap_or_default(),
                download_result_bytes: result.map(|item| item.bytes).unwrap_or(0),
                download_result_error: result.map(|item| item.error.clone()).unwrap_or_default(),
                url: row.url.clone(),
                expected_path: row.expected_path.clone(),
                reason,
            }
        })
        .collect::<Vec<_>>();
    rows.sort_by(|a, b| {
        a.priority
            .cmp(&b.priority)
            .then_with(|| a.date.cmp(&b.date))
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.data_type.cmp(&b.data_type))
    });
    rows
}

fn build_worker_shards(config: &V10Config, rows: &[DownloadMetadataRow]) -> Vec<WorkerShardRow> {
    let mut sorted = rows.to_vec();
    sorted.sort_by(|a, b| {
        action_rank(&a.action)
            .cmp(&action_rank(&b.action))
            .then_with(|| a.priority.cmp(&b.priority))
            .then_with(|| a.date.cmp(&b.date))
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.data_type.cmp(&b.data_type))
    });
    sorted
        .iter()
        .enumerate()
        .map(|(idx, row)| WorkerShardRow {
            run_tag: config.run_tag.clone(),
            worker_id: (idx % config.workers) + 1,
            queue_index: idx + 1,
            date: row.date.clone(),
            symbol: row.symbol.clone(),
            data_type: row.data_type.clone(),
            stage: row.stage.clone(),
            action: row.action.clone(),
            local_status: row.local_status.clone(),
            blocking_reconstruction: row.blocking_reconstruction,
            estimated_compressed_mb: row.estimated_compressed_mb,
            expected_path: row.expected_path.clone(),
        })
        .collect()
}

#[derive(Debug, Default)]
struct FileReplayStats {
    raw_rows_read: usize,
    replay_rows: usize,
    snapshot_batches: usize,
    first_local_timestamp: Option<u64>,
    last_local_timestamp: Option<u64>,
    bid_levels_sum: f64,
    ask_levels_sum: f64,
    max_bid_levels: usize,
    max_ask_levels: usize,
    spreads: Vec<f64>,
    top_of_book_count: usize,
    crossed_batches: usize,
    crossed_level_removals: usize,
    bid_depth_5_sum: f64,
    ask_depth_5_sum: f64,
}

fn build_replay_preview_rows(
    config: &V10Config,
    inventory_rows: &[InventoryRow],
) -> Result<Vec<ReplayPreviewRow>> {
    build_replay_summary_rows(
        config,
        inventory_rows,
        Some(DEFAULT_REPLAY_PREVIEW_MAX_ROWS_PER_FILE),
    )
}

fn build_replay_full_summary_rows_from_state_manifest(
    config: &V10Config,
    replay_state_files: &[ReplayStateFileRow],
) -> Result<Vec<ReplayPreviewRow>> {
    let mut rows = replay_state_files
        .iter()
        .map(|state_file| build_replay_full_summary_row_from_state_file(config, state_file))
        .collect::<Result<Vec<_>>>()?;
    rows.sort_by(|a, b| a.date.cmp(&b.date).then_with(|| a.symbol.cmp(&b.symbol)));
    Ok(rows)
}

fn build_replay_full_summary_rows_incremental(
    config: &V10Config,
    paths: &Paths,
    checkpoint: &mut Checkpoint,
    replay_state_files: &[ReplayStateFileRow],
) -> Result<Vec<ReplayPreviewRow>> {
    let step = "replay_incremental_full_summary";
    if can_reuse_step(checkpoint, step, config, &[&paths.replay_full_summary_csv])? {
        let rows = load_csv_rows::<ReplayPreviewRow>(&paths.replay_full_summary_csv)?;
        let completed = rows
            .iter()
            .map(|row| (row.date.clone(), row.symbol.clone()))
            .collect::<HashSet<_>>();
        let covers_current = replay_state_files
            .iter()
            .all(|row| completed.contains(&(row.date.clone(), row.symbol.clone())));
        if covers_current {
            return Ok(rows);
        }
    }

    let mut rows = if config.resume && !config.force && paths.replay_full_summary_csv.exists() {
        load_csv_rows::<ReplayPreviewRow>(&paths.replay_full_summary_csv)?
    } else {
        Vec::new()
    };
    let mut completed = rows
        .iter()
        .map(|row| (row.date.clone(), row.symbol.clone()))
        .collect::<HashSet<_>>();
    let total = replay_state_files.len();
    let max_files = config.max_replay_files.unwrap_or(usize::MAX);

    update_checkpoint(
        checkpoint,
        &paths.checkpoint,
        step,
        "running",
        &format!("resume_rows={} total_present_files={}", rows.len(), total),
    )?;

    let mut processed_this_run = 0usize;
    for state_file in replay_state_files {
        let key = (state_file.date.clone(), state_file.symbol.clone());
        if completed.contains(&key) {
            continue;
        }
        if processed_this_run >= max_files {
            break;
        }
        let row = build_replay_full_summary_row_from_state_file(config, state_file)?;
        rows.push(row);
        rows.sort_by(|a, b| a.date.cmp(&b.date).then_with(|| a.symbol.cmp(&b.symbol)));
        write_csv_atomic(&paths.replay_full_summary_csv, &rows)?;
        completed.insert(key.clone());
        processed_this_run += 1;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            step,
            "running",
            &format!(
                "completed_files={}/{} last_file={}",
                completed.len(),
                total,
                state_file.output_path
            ),
        )?;
    }

    let detail = if rows.is_empty() {
        "no present incremental_book_L2 shards for full replay summary".to_string()
    } else if completed.len() < total {
        format!(
            "partial rows={} completed_files={}/{}",
            rows.len(),
            completed.len(),
            total
        )
    } else {
        format!("rows={} source_files={}", rows.len(), total)
    };
    let status = if completed.len() < total {
        "partial"
    } else {
        "completed"
    };
    update_checkpoint(checkpoint, &paths.checkpoint, step, status, &detail)?;
    Ok(rows)
}

fn build_replay_state_files_incremental(
    config: &V10Config,
    paths: &Paths,
    checkpoint: &mut Checkpoint,
    inventory_rows: &[InventoryRow],
) -> Result<Vec<ReplayStateFileRow>> {
    let step = "replay_book_state_files";
    let mut rows = if config.resume && !config.force && paths.replay_state_manifest_csv.exists() {
        load_csv_rows::<ReplayStateFileRow>(&paths.replay_state_manifest_csv)?
    } else {
        Vec::new()
    };
    let mut completed = HashSet::new();
    for row in rows.iter() {
        if replay_state_file_is_reusable(row) {
            completed.insert((row.date.clone(), row.symbol.clone()));
        }
    }
    let present = inventory_rows
        .iter()
        .filter(|row| {
            row.data_type == "incremental_book_L2"
                && row.status == "present"
                && row.required_schema_ok
        })
        .collect::<Vec<_>>();
    let mut present = present;
    present.sort_by(|a, b| {
        a.bytes
            .cmp(&b.bytes)
            .then_with(|| a.date.cmp(&b.date))
            .then_with(|| a.symbol.cmp(&b.symbol))
    });
    let total = present.len();
    let max_files = config.max_replay_files.unwrap_or(usize::MAX);

    update_checkpoint(
        checkpoint,
        &paths.checkpoint,
        step,
        "running",
        &format!("resume_rows={} total_present_files={}", rows.len(), total),
    )?;

    let mut processed_this_run = 0usize;
    for inventory in present {
        let key = (inventory.date.clone(), inventory.symbol.clone());
        if completed.contains(&key) {
            continue;
        }
        if processed_this_run >= max_files {
            break;
        }
        let raw_path = PathBuf::from(&inventory.expected_path);
        let output_path = replay_state_output_path(config, &inventory.symbol, &inventory.date);
        let file_label = path_string(&raw_path);
        let mut progress = |raw_rows_read: usize,
                            current_local_timestamp: Option<u64>|
         -> Result<()> {
            update_checkpoint(
                checkpoint,
                &paths.checkpoint,
                step,
                "running",
                &format!(
                    "completed_files={}/{} current_file={} raw_rows_read={} current_local_timestamp={}",
                    completed.len(),
                    total,
                    file_label,
                    raw_rows_read,
                    current_local_timestamp
                        .map(|value| value.to_string())
                        .unwrap_or_default()
                ),
            )
        };
        let (part_files, replay_rows, raw_rows_read, first_local_timestamp, last_local_timestamp) =
            replay_incremental_book_file_to_parts(&raw_path, &output_path, Some(&mut progress))?;
        let row = ReplayStateFileRow {
            run_tag: config.run_tag.clone(),
            date: inventory.date.clone(),
            symbol: inventory.symbol.clone(),
            raw_path: inventory.expected_path.clone(),
            output_path: path_string(&output_path),
            part_files,
            raw_rows_read,
            replay_rows,
            first_local_timestamp,
            last_local_timestamp,
            status: "completed".to_string(),
        };
        upsert_replay_state_row(&mut rows, row);
        rows.sort_by(|a, b| a.date.cmp(&b.date).then_with(|| a.symbol.cmp(&b.symbol)));
        write_csv_atomic(&paths.replay_state_manifest_csv, &rows)?;
        completed.insert(key.clone());
        processed_this_run += 1;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            step,
            "running",
            &format!(
                "completed_files={}/{} last_file={}",
                completed.len(),
                total,
                file_label
            ),
        )?;
    }

    let detail = if rows.is_empty() {
        "no present incremental_book_L2 shards for replay book-state files".to_string()
    } else if completed.len() < total {
        format!(
            "partial rows={} completed_files={}/{}",
            rows.len(),
            completed.len(),
            total
        )
    } else {
        format!("rows={} source_files={}", rows.len(), total)
    };
    let status = if completed.len() < total {
        "partial"
    } else {
        "completed"
    };
    update_checkpoint(checkpoint, &paths.checkpoint, step, status, &detail)?;
    Ok(rows)
}

fn build_v10_derived_outputs(
    config: &V10Config,
    paths: &Paths,
    checkpoint: &mut Checkpoint,
    replay_state_files: &[ReplayStateFileRow],
) -> Result<V10DerivedOutputs> {
    let potential_step_completed = step_completed(checkpoint, "potential_state");
    let completed_reusable = if config.resume && !config.force && potential_step_completed {
        load_reusable_potential_rows(&paths.potential_state_csv, replay_state_files, true)?
    } else {
        None
    };
    let recovered_reusable = if config.resume
        && !config.force
        && !potential_step_completed
        && completed_reusable.is_none()
    {
        load_reusable_potential_rows(&paths.potential_state_csv, replay_state_files, false)?
    } else {
        None
    };
    let (potential_rows, potential_rebuilt) = if let Some(rows) = completed_reusable {
        (rows, false)
    } else if let Some(rows) = recovered_reusable {
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "potential_state",
            "completed",
            &format!(
                "recovered existing rows={} source_state_files={} despite incomplete checkpoint",
                rows.len(),
                replay_state_files.len()
            ),
        )?;
        (rows, false)
    } else {
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "potential_state",
            "running",
            "build queue-replay potential state from completed book-state parts and aligned trades",
        )?;
        let rows = build_v10_potential_rows(config, replay_state_files)?;
        write_csv_atomic(&paths.potential_state_csv, &rows)?;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "potential_state",
            "completed",
            &format!(
                "rows={} source_state_files={}",
                rows.len(),
                replay_state_files.len()
            ),
        )?;
        (rows, true)
    };
    let potential_covers_current =
        v10_potential_rows_cover_state_files(&potential_rows, replay_state_files);

    let (filter_params, filter_rows) = if can_reuse_step(
        checkpoint,
        "train_purged_filter_state",
        config,
        &[&paths.filter_params_csv, &paths.filter_rows_csv],
    )? && potential_covers_current
        && !potential_rebuilt
    {
        (
            load_csv_rows::<V10FilterParamRow>(&paths.filter_params_csv)?,
            load_csv_rows::<V10FilterStateRow>(&paths.filter_rows_csv)?,
        )
    } else {
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "train_purged_filter_state",
            "running",
            "fit thresholds on train folds only and apply after purge gaps",
        )?;
        let (params, rows) = build_v10_filter_state(&potential_rows);
        write_csv_atomic(&paths.filter_params_csv, &params)?;
        write_csv_atomic(&paths.filter_rows_csv, &rows)?;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "train_purged_filter_state",
            "completed",
            &format!("params={} validation_rows={}", params.len(), rows.len()),
        )?;
        (params, rows)
    };

    let (anchor_candidates, path_trades, path_summary) = if can_reuse_step(
        checkpoint,
        "movable_anchor_path_backtest",
        config,
        &[
            &paths.anchor_candidates_csv,
            &paths.path_trades_csv,
            &paths.path_summary_csv,
        ],
    )? && potential_covers_current
        && !potential_rebuilt
    {
        (
            load_csv_rows::<V10AnchorCandidateRow>(&paths.anchor_candidates_csv)?,
            load_csv_rows::<V10PathTradeRow>(&paths.path_trades_csv)?,
            load_csv_rows::<V10PathSummaryRow>(&paths.path_summary_csv)?,
        )
    } else {
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "movable_anchor_path_backtest",
            "running",
            "generate movable-anchor long/short episodes and maker/taker/stress diagnostics",
        )?;
        let (anchors, trades, summary) = build_v10_path_outputs(&filter_rows);
        write_csv_atomic(&paths.anchor_candidates_csv, &anchors)?;
        write_csv_atomic(&paths.path_trades_csv, &trades)?;
        write_csv_atomic(&paths.path_summary_csv, &summary)?;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "movable_anchor_path_backtest",
            "completed",
            &format!(
                "anchors={} trades={} summary_rows={}",
                anchors.len(),
                trades.len(),
                summary.len()
            ),
        )?;
        (anchors, trades, summary)
    };

    let negative_controls = if can_reuse_step(
        checkpoint,
        "negative_controls",
        config,
        &[&paths.negative_controls_csv],
    )? && potential_covers_current
        && !potential_rebuilt
    {
        load_csv_rows::<V10NegativeControlRow>(&paths.negative_controls_csv)?
    } else {
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "negative_controls",
            "running",
            "build side-flip and deterministic phase controls for validation trades",
        )?;
        let rows = build_v10_negative_controls(&path_trades);
        write_csv_atomic(&paths.negative_controls_csv, &rows)?;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "negative_controls",
            "completed",
            &format!("rows={}", rows.len()),
        )?;
        rows
    };

    let (spearman_rows, horizon_decay) = if can_reuse_step(
        checkpoint,
        "spearman_horizon_decay",
        config,
        &[&paths.spearman_stability_csv, &paths.horizon_decay_csv],
    )? && potential_covers_current
        && !potential_rebuilt
    {
        (
            load_csv_rows::<V10SpearmanRow>(&paths.spearman_stability_csv)?,
            load_csv_rows::<V10HorizonDecayRow>(&paths.horizon_decay_csv)?,
        )
    } else {
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "spearman_horizon_decay",
            "running",
            "measure event-time Spearman stability and horizon decay on replay-derived states",
        )?;
        let rows = build_v10_spearman_rows(&potential_rows);
        let decay = build_v10_horizon_decay(&rows);
        write_csv_atomic(&paths.spearman_stability_csv, &rows)?;
        write_csv_atomic(&paths.horizon_decay_csv, &decay)?;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "spearman_horizon_decay",
            "completed",
            &format!("spearman_rows={} decay_rows={}", rows.len(), decay.len()),
        )?;
        (rows, decay)
    };

    let failure_report = if can_reuse_step(
        checkpoint,
        "failure_report",
        config,
        &[&paths.failure_report_csv],
    )? && potential_covers_current
        && !potential_rebuilt
        && v10_failure_report_has_schema_check(&paths.failure_report_csv)?
    {
        load_csv_rows::<V10FailureReportRow>(&paths.failure_report_csv)?
    } else {
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "failure_report",
            "running",
            "write V10 coverage and path-quality failure report",
        )?;
        let rows = build_v10_failure_report(
            config,
            replay_state_files,
            &potential_rows,
            &filter_rows,
            &path_trades,
            &negative_controls,
            &spearman_rows,
        );
        write_csv_atomic(&paths.failure_report_csv, &rows)?;
        update_checkpoint(
            checkpoint,
            &paths.checkpoint,
            "failure_report",
            "completed",
            &format!("rows={}", rows.len()),
        )?;
        rows
    };

    Ok(V10DerivedOutputs {
        potential_rows,
        filter_params,
        filter_rows,
        anchor_candidates,
        path_trades,
        path_summary,
        negative_controls,
        spearman_rows,
        horizon_decay,
        failure_report,
    })
}

fn build_v10_potential_rows(
    config: &V10Config,
    replay_state_files: &[ReplayStateFileRow],
) -> Result<Vec<V10PotentialStateRow>> {
    let mut files = replay_state_files.to_vec();
    files.sort_by(|a, b| a.symbol.cmp(&b.symbol).then_with(|| a.date.cmp(&b.date)));
    let mut out = Vec::new();
    let mut prev_by_symbol: HashMap<String, V10PotentialStateRow> = HashMap::new();

    for state_file in &files {
        if state_file.status != "completed" {
            continue;
        }
        let mut states = read_replayed_state_file_rows(state_file)?;
        states.sort_by_key(|row| row.local_timestamp);
        let trades = read_v10_trade_rows(config, state_file)?;
        let mut trade_idx = 0usize;
        let mut last_state_ts = state_file
            .first_local_timestamp
            .unwrap_or(0)
            .saturating_sub(1);

        for state in states {
            let mut trade_count = 0usize;
            let mut trade_buy_amount = 0.0;
            let mut trade_sell_amount = 0.0;
            let mut trade_notional_quote = 0.0;
            while trade_idx < trades.len()
                && trades[trade_idx].local_timestamp <= state.local_timestamp
            {
                let trade = &trades[trade_idx];
                if trade.local_timestamp > last_state_ts {
                    if trade.symbol != state.symbol
                        || !trade.exchange.eq_ignore_ascii_case(EXCHANGE)
                    {
                        trade_idx += 1;
                        continue;
                    }
                    let _source_order_key = (trade.timestamp, trade.id.as_str());
                    let amount = trade.amount.max(0.0);
                    let notional = amount * trade.price.max(0.0);
                    if trade.side.eq_ignore_ascii_case("buy") {
                        trade_buy_amount += amount;
                    } else if trade.side.eq_ignore_ascii_case("sell") {
                        trade_sell_amount += amount;
                    }
                    trade_notional_quote += notional;
                    trade_count += 1;
                }
                trade_idx += 1;
            }
            let row = materialize_v10_potential_state(
                config,
                state_file,
                &state,
                prev_by_symbol.get(&state.symbol),
                trade_count,
                trade_buy_amount,
                trade_sell_amount,
                trade_notional_quote,
            );
            last_state_ts = state.local_timestamp;
            prev_by_symbol.insert(state.symbol.clone(), row.clone());
            out.push(row);
        }
    }
    out.sort_by(|a, b| {
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a.local_timestamp.cmp(&b.local_timestamp))
    });
    Ok(out)
}

fn materialize_v10_potential_state(
    config: &V10Config,
    state_file: &ReplayStateFileRow,
    state: &ReplayedBookStateRow,
    prev: Option<&V10PotentialStateRow>,
    trade_count: usize,
    trade_buy_amount: f64,
    trade_sell_amount: f64,
    trade_notional_quote: f64,
) -> V10PotentialStateRow {
    let depth_total_5 = state.bid_depth_5 + state.ask_depth_5;
    let depth_total_25 = state.bid_depth_25 + state.ask_depth_25;
    let queue_depth_pressure = state
        .imbalance_25
        .or(state.imbalance_5)
        .and_then(v10_finite);
    let microprice_bps = state
        .microprice
        .zip(state.mid_price)
        .and_then(|(micro, mid)| (mid > 0.0).then_some((micro - mid) / mid * 10_000.0))
        .and_then(v10_finite);
    let microprice_impulse_bps = prev
        .and_then(|prev| microprice_bps.zip(prev.microprice_bps))
        .and_then(|(cur, old)| v10_finite(cur - old));
    let prev_depth = prev.map(|row| row.depth_total_5).unwrap_or(0.0).max(0.0);
    let cancellation_withdrawal_energy = prev.and_then(|prev| {
        if prev_depth <= 0.0 {
            None
        } else {
            let bid_down = (prev.bid_depth_5 - state.bid_depth_5).max(0.0);
            let ask_down = (prev.ask_depth_5 - state.ask_depth_5).max(0.0);
            v10_finite((bid_down + ask_down) / prev_depth)
        }
    });
    let replenish_relaxation = prev.and_then(|prev| {
        if prev_depth <= 0.0 {
            None
        } else {
            let bid_up = (state.bid_depth_5 - prev.bid_depth_5).max(0.0);
            let ask_up = (state.ask_depth_5 - prev.ask_depth_5).max(0.0);
            v10_finite((bid_up + ask_up) / prev_depth)
        }
    });
    let spread_resistance = state.spread_bps.and_then(|spread| {
        let slope = v10_mean_opt(&[state.bid_slope_5, state.ask_slope_5]).unwrap_or(0.0);
        v10_finite(
            v10_squash(spread, 6.0) + 0.25 * v10_squash(slope, 0.01)
                - 0.25 * v10_squash(depth_total_25.max(depth_total_5), 1_000.0),
        )
    });
    let trade_flow_imbalance = if trade_buy_amount + trade_sell_amount > 0.0 {
        v10_finite((trade_buy_amount - trade_sell_amount) / (trade_buy_amount + trade_sell_amount))
    } else {
        None
    };
    let micropressure = microprice_bps.map(|value| v10_squash(value, 3.0));
    let phi_bid = v10_mean_opt(&[
        queue_depth_pressure,
        micropressure,
        trade_flow_imbalance,
        replenish_relaxation,
        spread_resistance.map(|value| -0.5 * value),
    ]);
    let phi_ask = v10_mean_opt(&[
        queue_depth_pressure.map(|value| -value),
        micropressure.map(|value| -value),
        trade_flow_imbalance.map(|value| -value),
        cancellation_withdrawal_energy,
        spread_resistance,
    ]);
    let net_potential = phi_bid
        .zip(phi_ask)
        .and_then(|(bid, ask)| v10_finite(bid - ask));
    let potential_gradient = prev
        .and_then(|prev| net_potential.zip(prev.net_potential))
        .and_then(|(cur, old)| v10_finite(cur - old));
    let potential_curvature = prev
        .and_then(|prev| potential_gradient.zip(prev.potential_gradient))
        .and_then(|(cur, old)| v10_finite(cur - old));
    let energy_release = v10_mean_opt(&[
        potential_gradient.map(f64::abs),
        potential_curvature.map(f64::abs),
        cancellation_withdrawal_energy,
        replenish_relaxation,
        trade_flow_imbalance.map(f64::abs),
        state
            .crossed_levels_removed
            .checked_sub(0)
            .map(|value| v10_squash(value as f64, 20.0)),
    ]);
    let fill_realism_score = v10_finite(
        0.35 + 0.25 * v10_squash(depth_total_5, 250.0)
            + 0.20 * replenish_relaxation.unwrap_or(0.0).clamp(0.0, 1.0)
            - 0.15
                * cancellation_withdrawal_energy
                    .unwrap_or(0.0)
                    .clamp(0.0, 1.0)
            - 0.10 * spread_resistance.unwrap_or(0.0).max(0.0),
    )
    .map(|value| value.clamp(0.02, 0.98));

    V10PotentialStateRow {
        run_tag: config.run_tag.clone(),
        date: state_file.date.clone(),
        symbol: state.symbol.clone(),
        timestamp: state.timestamp,
        local_timestamp: state.local_timestamp,
        mid_price: state.mid_price,
        spread_bps: state.spread_bps,
        microprice: state.microprice,
        microprice_bps,
        bid_depth_5: state.bid_depth_5,
        ask_depth_5: state.ask_depth_5,
        depth_total_5,
        bid_depth_25: state.bid_depth_25,
        ask_depth_25: state.ask_depth_25,
        depth_total_25,
        imbalance_25: state.imbalance_25,
        bid_slope_5: state.bid_slope_5,
        ask_slope_5: state.ask_slope_5,
        depth_curvature_5: state.depth_curvature_5,
        queue_depth_pressure,
        cancellation_withdrawal_energy,
        replenish_relaxation,
        spread_resistance,
        microprice_impulse_bps,
        trade_count,
        trade_buy_amount,
        trade_sell_amount,
        trade_notional_quote,
        trade_flow_imbalance,
        phi_bid,
        phi_ask,
        net_potential,
        potential_gradient,
        potential_curvature,
        energy_release,
        fill_realism_score,
        guardrail: GUARDRAIL.to_string(),
    }
}

fn read_replayed_state_file_rows(
    state_file: &ReplayStateFileRow,
) -> Result<Vec<ReplayedBookStateRow>> {
    let mut rows = Vec::new();
    let output_dir = Path::new(&state_file.output_path);
    for part_index in 1..=state_file.part_files {
        let part_path = replay_state_part_path(output_dir, part_index);
        rows.extend(load_csv_rows::<ReplayedBookStateRow>(&part_path)?);
    }
    Ok(rows)
}

fn read_v10_trade_rows(
    config: &V10Config,
    state_file: &ReplayStateFileRow,
) -> Result<Vec<TradeCsvRow>> {
    let path = raw_path(
        &config.data_root,
        "trades",
        NaiveDate::parse_from_str(&state_file.date, "%Y-%m-%d")?,
        &state_file.symbol,
    );
    if !path.exists() {
        return Ok(Vec::new());
    }
    let file = File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = csv::Reader::from_reader(decoder);
    let mut rows = Vec::new();
    for record in reader.deserialize() {
        rows.push(record.with_context(|| format!("failed to parse {}", path.display()))?);
    }
    rows.sort_by_key(|row: &TradeCsvRow| row.local_timestamp);
    Ok(rows)
}

#[derive(Debug, Clone)]
struct V10FoldRange {
    name: String,
    train_start: u64,
    train_end: u64,
    valid_start: u64,
    valid_end: u64,
}

fn build_v10_filter_state(
    potential_rows: &[V10PotentialStateRow],
) -> (Vec<V10FilterParamRow>, Vec<V10FilterStateRow>) {
    let mut params = Vec::new();
    let mut out = Vec::new();
    let by_symbol = v10_potential_by_symbol(potential_rows);
    for (symbol, rows) in by_symbol {
        for fold in v10_dynamic_folds(&rows) {
            let train = rows
                .iter()
                .copied()
                .filter(|row| {
                    row.local_timestamp >= fold.train_start && row.local_timestamp <= fold.train_end
                })
                .collect::<Vec<_>>();
            let valid = rows
                .iter()
                .copied()
                .filter(|row| {
                    row.local_timestamp >= fold.valid_start && row.local_timestamp <= fold.valid_end
                })
                .collect::<Vec<_>>();
            if train.len() < 25 || valid.is_empty() {
                continue;
            }
            let net_values = train
                .iter()
                .filter_map(|row| row.net_potential)
                .collect::<Vec<_>>();
            let energy_values = train
                .iter()
                .filter_map(|row| row.energy_release)
                .collect::<Vec<_>>();
            let fill_values = train
                .iter()
                .filter_map(|row| row.fill_realism_score)
                .collect::<Vec<_>>();
            let flow_values = train
                .iter()
                .filter_map(|row| row.trade_flow_imbalance.map(f64::abs))
                .collect::<Vec<_>>();
            let spread_values = train
                .iter()
                .filter_map(|row| row.spread_bps)
                .collect::<Vec<_>>();
            let net_low = v10_quantile(&net_values, 0.25).unwrap_or(-0.25);
            let net_high = v10_quantile(&net_values, 0.75).unwrap_or(0.25);
            let energy_high = v10_quantile(&energy_values, 0.75).unwrap_or(0.25);
            let fill_low = v10_quantile(&fill_values, 0.25).unwrap_or(0.25);
            let fill_high = v10_quantile(&fill_values, 0.75).unwrap_or(0.65);
            let flow_abs_high = v10_quantile(&flow_values, 0.75).unwrap_or(0.25);
            let spread_high = v10_quantile(&spread_values, 0.75).unwrap_or(5.0);
            let thresholds = format!(
                "train_only;purge_us={};net_low={:.6};net_high={:.6};energy_high={:.6};fill_low={:.6};fill_high={:.6};flow_abs_high={:.6};spread_high={:.6}",
                V10_PURGE_US,
                net_low,
                net_high,
                energy_high,
                fill_low,
                fill_high,
                flow_abs_high,
                spread_high
            );
            params.push(V10FilterParamRow {
                run_tag: valid[0].run_tag.clone(),
                fold: fold.name.clone(),
                symbol: symbol.clone(),
                train_start_local_timestamp: fold.train_start,
                train_end_local_timestamp: fold.train_end,
                valid_start_local_timestamp: fold.valid_start,
                valid_end_local_timestamp: fold.valid_end,
                purge_us: V10_PURGE_US,
                train_rows: train.len(),
                valid_rows: valid.len(),
                net_low,
                net_high,
                energy_high,
                fill_low,
                fill_high,
                flow_abs_high,
                spread_high,
                thresholds_fit_on_train: thresholds.clone(),
                guardrail: GUARDRAIL.to_string(),
            });
            for row in valid {
                let flow_abs = row.trade_flow_imbalance.map(f64::abs).unwrap_or(0.0);
                out.push(V10FilterStateRow {
                    run_tag: row.run_tag.clone(),
                    fold: fold.name.clone(),
                    date: row.date.clone(),
                    symbol: row.symbol.clone(),
                    timestamp: row.timestamp,
                    local_timestamp: row.local_timestamp,
                    mid_price: row.mid_price,
                    spread_bps: row.spread_bps,
                    net_potential: row.net_potential,
                    potential_gradient: row.potential_gradient,
                    potential_curvature: row.potential_curvature,
                    energy_release: row.energy_release,
                    fill_realism_score: row.fill_realism_score,
                    trade_flow_imbalance: row.trade_flow_imbalance,
                    queue_depth_pressure: row.queue_depth_pressure,
                    cancellation_withdrawal_energy: row.cancellation_withdrawal_energy,
                    replenish_relaxation: row.replenish_relaxation,
                    net_bucket_train_fit: v10_bucket(
                        row.net_potential.unwrap_or(0.0),
                        net_low,
                        net_high,
                    ),
                    energy_bucket_train_fit: if row.energy_release.unwrap_or(0.0) >= energy_high {
                        "high".to_string()
                    } else {
                        "not_high".to_string()
                    },
                    fill_bucket_train_fit: v10_bucket(
                        row.fill_realism_score.unwrap_or(0.0),
                        fill_low,
                        fill_high,
                    ),
                    flow_bucket_train_fit: if flow_abs >= flow_abs_high {
                        "high_abs".to_string()
                    } else {
                        "normal".to_string()
                    },
                    spread_bucket_train_fit: if row.spread_bps.unwrap_or(0.0) >= spread_high {
                        "wide".to_string()
                    } else {
                        "normal".to_string()
                    },
                    thresholds_fit_on_train: thresholds.clone(),
                    guardrail: GUARDRAIL.to_string(),
                });
            }
        }
    }
    out.sort_by(|a, b| {
        a.fold
            .cmp(&b.fold)
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.local_timestamp.cmp(&b.local_timestamp))
    });
    (params, out)
}

fn v10_dynamic_folds(rows: &[&V10PotentialStateRow]) -> Vec<V10FoldRange> {
    if rows.len() < 100 {
        return Vec::new();
    }
    let start = rows.first().map(|row| row.local_timestamp).unwrap_or(0);
    let end = rows.last().map(|row| row.local_timestamp).unwrap_or(start);
    let span = end.saturating_sub(start);
    if span <= V10_PURGE_US * 3 {
        return Vec::new();
    }
    let specs = [(45u64, 63u64), (60, 78), (72, 94)];
    specs
        .iter()
        .enumerate()
        .filter_map(|(idx, (train_pct, valid_end_pct))| {
            let train_end = start + span.saturating_mul(*train_pct) / 100;
            let valid_start = train_end.saturating_add(V10_PURGE_US);
            let valid_end = start + span.saturating_mul(*valid_end_pct) / 100;
            (valid_start < valid_end).then_some(V10FoldRange {
                name: format!("fold{}", idx + 1),
                train_start: start,
                train_end,
                valid_start,
                valid_end,
            })
        })
        .collect()
}

fn build_v10_path_outputs(
    filter_rows: &[V10FilterStateRow],
) -> (
    Vec<V10AnchorCandidateRow>,
    Vec<V10PathTradeRow>,
    Vec<V10PathSummaryRow>,
) {
    let mut anchors = Vec::new();
    let mut trades = Vec::new();
    let grouped = v10_filter_by_fold_symbol(filter_rows);
    for ((fold, symbol), rows) in grouped {
        for &anchor in V10_ANCHORS {
            for &side in V10_SIDES {
                let selected = rows
                    .iter()
                    .filter(|row| v10_anchor_passes(row, anchor, side))
                    .count();
                anchors.push(V10AnchorCandidateRow {
                    run_tag: rows
                        .first()
                        .map(|row| row.run_tag.clone())
                        .unwrap_or_default(),
                    fold: fold.clone(),
                    symbol: symbol.clone(),
                    anchor_type: anchor.to_string(),
                    side: side.to_string(),
                    validation_rows: rows.len(),
                    selected_rows: selected,
                    selected_rate: v10_rate(selected, rows.len()),
                    train_fit_rule: rows
                        .first()
                        .map(|row| row.thresholds_fit_on_train.clone())
                        .unwrap_or_default(),
                    guardrail: GUARDRAIL.to_string(),
                });
                let mut last_signal = 0u64;
                for idx in 0..rows.len().saturating_sub(2) {
                    if rows[idx].local_timestamp < last_signal.saturating_add(60_000_000) {
                        continue;
                    }
                    if !v10_anchor_passes(rows[idx], anchor, side) {
                        continue;
                    }
                    last_signal = rows[idx].local_timestamp;
                    for &execution_model in V10_EXECUTION_MODELS {
                        for &tp_bps in V10_TP_BPS {
                            for &sl_bps in V10_SL_BPS {
                                for &timeout_seconds in V10_TIMEOUT_SECONDS {
                                    if let Some(trade) = simulate_v10_path_trade(
                                        &rows,
                                        idx,
                                        anchor,
                                        side,
                                        execution_model,
                                        tp_bps,
                                        sl_bps,
                                        timeout_seconds,
                                    ) {
                                        trades.push(trade);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    let summary = summarize_v10_path_trades(&trades);
    (anchors, trades, summary)
}

fn v10_anchor_passes(row: &V10FilterStateRow, anchor: &str, side: &str) -> bool {
    let long = side == "long";
    let net = row.net_potential.unwrap_or(0.0);
    let grad = row.potential_gradient.unwrap_or(0.0);
    let flow = row.trade_flow_imbalance.unwrap_or(0.0);
    let micro_side_ok = if long { flow >= 0.0 } else { flow <= 0.0 };
    let net_side_ok = if long {
        row.net_bucket_train_fit == "high" && net > 0.0
    } else {
        row.net_bucket_train_fit == "low" && net < 0.0
    };
    match anchor {
        "pressure_break" => {
            net_side_ok
                && ((long && grad > 0.0) || (!long && grad < 0.0))
                && row.fill_bucket_train_fit != "low"
        }
        "energy_replenish" => {
            net_side_ok
                && row.energy_bucket_train_fit == "high"
                && row.replenish_relaxation.unwrap_or(0.0)
                    >= row.cancellation_withdrawal_energy.unwrap_or(0.0)
        }
        "microprice_flow" => {
            net_side_ok
                && micro_side_ok
                && row.flow_bucket_train_fit == "high_abs"
                && row.spread_bucket_train_fit != "wide"
        }
        _ => false,
    }
}

fn simulate_v10_path_trade(
    rows: &[&V10FilterStateRow],
    signal_idx: usize,
    anchor: &str,
    side: &str,
    execution_model: &str,
    tp_bps: u32,
    sl_bps: u32,
    timeout_seconds: u32,
) -> Option<V10PathTradeRow> {
    let signal = rows.get(signal_idx)?;
    let entry = rows.get(signal_idx + 1)?;
    let entry_mid = entry.mid_price?;
    if entry_mid <= 0.0 {
        return None;
    }
    let timeout_us = timeout_seconds as u64 * 1_000_000;
    let mut exit = *rows.last()?;
    let mut exit_reason = "timeout".to_string();
    for candidate in rows.iter().skip(signal_idx + 2) {
        let mid = candidate.mid_price?;
        let gross = v10_gross_bps(side, entry_mid, mid);
        if gross >= tp_bps as f64 {
            exit = *candidate;
            exit_reason = "take_profit".to_string();
            break;
        }
        if gross <= -(sl_bps as f64) {
            exit = *candidate;
            exit_reason = "stop_loss".to_string();
            break;
        }
        if candidate
            .local_timestamp
            .saturating_sub(entry.local_timestamp)
            >= timeout_us
        {
            exit = *candidate;
            break;
        }
    }
    let exit_mid = exit.mid_price?;
    let gross_bps = v10_gross_bps(side, entry_mid, exit_mid);
    let fill = entry.fill_realism_score.unwrap_or(0.35).clamp(0.02, 0.98);
    let spread = entry.spread_bps.unwrap_or(0.0).max(0.0);
    let queue_penalty_bps = (1.0 - fill) * spread;
    let cost_bps = match execution_model {
        "maker_light" => V10_FEE_BPS + 0.25 * spread + queue_penalty_bps,
        "taker_spread" => V10_FEE_BPS + spread + 0.50 * queue_penalty_bps,
        "wide_stress" => V10_FEE_BPS + 2.0 * spread + 5.0 + queue_penalty_bps,
        _ => V10_FEE_BPS + spread,
    };
    let net_bps = gross_bps - cost_bps;
    Some(V10PathTradeRow {
        run_tag: entry.run_tag.clone(),
        fold: entry.fold.clone(),
        date: entry.date.clone(),
        symbol: entry.symbol.clone(),
        anchor_type: anchor.to_string(),
        side: side.to_string(),
        execution_model: execution_model.to_string(),
        notional_quote: V10_NOTIONAL_QUOTE,
        tp_bps,
        sl_bps,
        timeout_seconds,
        signal_local_timestamp: signal.local_timestamp,
        entry_local_timestamp: entry.local_timestamp,
        exit_local_timestamp: exit.local_timestamp,
        entry_mid,
        exit_mid,
        exit_reason,
        gross_bps,
        cost_bps,
        queue_penalty_bps,
        fill_realism_score: fill,
        net_bps,
        pnl_quote: net_bps / 10_000.0 * V10_NOTIONAL_QUOTE,
        thresholds_fit_on_train: entry.thresholds_fit_on_train.clone(),
        guardrail: GUARDRAIL.to_string(),
    })
}

fn summarize_v10_path_trades(trades: &[V10PathTradeRow]) -> Vec<V10PathSummaryRow> {
    let mut groups: BTreeMap<
        (
            String,
            String,
            String,
            String,
            String,
            String,
            u32,
            u32,
            u32,
        ),
        Vec<&V10PathTradeRow>,
    > = BTreeMap::new();
    for trade in trades {
        groups
            .entry((
                trade.run_tag.clone(),
                trade.fold.clone(),
                trade.symbol.clone(),
                trade.anchor_type.clone(),
                trade.side.clone(),
                trade.execution_model.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_seconds,
            ))
            .or_default()
            .push(trade);
    }
    groups
        .into_iter()
        .map(
            |(
                (run_tag, fold, symbol, anchor_type, side, execution_model, tp, sl, timeout),
                rows,
            )| {
                let pnl = rows.iter().map(|row| row.pnl_quote).collect::<Vec<_>>();
                let net = rows.iter().map(|row| row.net_bps).collect::<Vec<_>>();
                let days = rows
                    .iter()
                    .map(|row| row.date.clone())
                    .collect::<HashSet<_>>()
                    .len()
                    .max(1);
                V10PathSummaryRow {
                    run_tag,
                    summary_scope: "fold".to_string(),
                    fold,
                    symbol,
                    anchor_type,
                    side,
                    execution_model,
                    tp_bps: tp,
                    sl_bps: sl,
                    timeout_seconds: timeout,
                    trade_count: rows.len(),
                    total_pnl_quote: pnl.iter().sum(),
                    avg_net_bps: v10_mean(&net),
                    median_net_bps: v10_quantile(&net, 0.5),
                    win_rate: Some(v10_rate(
                        net.iter().filter(|value| **value > 0.0).count(),
                        net.len(),
                    )),
                    profit_factor: v10_profit_factor(&pnl),
                    trades_per_day: rows.len() as f64 / days as f64,
                    max_drawdown_quote: v10_max_drawdown(&pnl),
                    guardrail: GUARDRAIL.to_string(),
                }
            },
        )
        .collect()
}

fn build_v10_negative_controls(trades: &[V10PathTradeRow]) -> Vec<V10NegativeControlRow> {
    let mut groups: BTreeMap<
        (String, String, String, String, u32, u32, u32),
        Vec<&V10PathTradeRow>,
    > = BTreeMap::new();
    for trade in trades {
        groups
            .entry((
                trade.symbol.clone(),
                trade.anchor_type.clone(),
                trade.side.clone(),
                trade.execution_model.clone(),
                trade.tp_bps,
                trade.sl_bps,
                trade.timeout_seconds,
            ))
            .or_default()
            .push(trade);
    }
    let mut out = Vec::new();
    for ((symbol, anchor, side, execution, tp, sl, timeout), rows) in groups {
        let base_total: f64 = rows.iter().map(|row| row.pnl_quote).sum();
        let side_flip_total: f64 = rows
            .iter()
            .map(|row| ((-row.gross_bps) - row.cost_bps) / 10_000.0 * row.notional_quote)
            .sum();
        out.push(V10NegativeControlRow {
            run_tag: rows
                .first()
                .map(|row| row.run_tag.clone())
                .unwrap_or_default(),
            symbol: symbol.clone(),
            anchor_type: anchor.clone(),
            side: side.clone(),
            execution_model: execution.clone(),
            tp_bps: tp,
            sl_bps: sl,
            timeout_seconds: timeout,
            control_type: "side_flip_proxy".to_string(),
            base_trade_count: rows.len(),
            base_total_pnl_quote: base_total,
            control_total_pnl_quote: side_flip_total,
            control_note: "same timestamps and cost model, opposite gross direction".to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
        let phase_total: f64 = rows
            .iter()
            .map(|row| {
                let sign = if v10_pseudo_bool(row.signal_local_timestamp, 17) {
                    1.0
                } else {
                    -1.0
                };
                (sign * row.gross_bps - row.cost_bps) / 10_000.0 * row.notional_quote
            })
            .sum();
        out.push(V10NegativeControlRow {
            run_tag: rows
                .first()
                .map(|row| row.run_tag.clone())
                .unwrap_or_default(),
            symbol,
            anchor_type: anchor,
            side,
            execution_model: execution,
            tp_bps: tp,
            sl_bps: sl,
            timeout_seconds: timeout,
            control_type: "deterministic_phase_sign_proxy".to_string(),
            base_trade_count: rows.len(),
            base_total_pnl_quote: base_total,
            control_total_pnl_quote: phase_total,
            control_note:
                "deterministic timestamp hash flips gross direction before identical costs"
                    .to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    out
}

fn build_v10_spearman_rows(potential_rows: &[V10PotentialStateRow]) -> Vec<V10SpearmanRow> {
    let features = [
        "net_potential",
        "potential_gradient",
        "potential_curvature",
        "energy_release",
        "queue_depth_pressure",
        "replenish_relaxation",
        "cancellation_withdrawal_energy",
        "trade_flow_imbalance",
        "fill_realism_score",
    ];
    let mut out = Vec::new();
    let grouped = v10_potential_by_symbol(potential_rows);
    for (symbol, rows) in grouped {
        for &horizon_seconds in V10_HORIZON_SECONDS {
            let targets = v10_future_returns(&rows, horizon_seconds);
            for feature in features {
                let mut xs = Vec::new();
                let mut ys = Vec::new();
                for (idx, row) in rows.iter().enumerate() {
                    let Some(target) = targets[idx] else {
                        continue;
                    };
                    let Some(value) = v10_potential_feature(row, feature) else {
                        continue;
                    };
                    xs.push(value);
                    ys.push(target);
                }
                if let Some(sp) = v10_spearman(&xs, &ys) {
                    out.push(V10SpearmanRow {
                        run_tag: rows
                            .first()
                            .map(|row| row.run_tag.clone())
                            .unwrap_or_default(),
                        fold: "all_completed_replay".to_string(),
                        symbol: symbol.clone(),
                        horizon_seconds,
                        feature_name: feature.to_string(),
                        spearman: sp,
                        abs_spearman: sp.abs(),
                        n: xs.len(),
                        sign: if sp >= 0.0 {
                            "positive".to_string()
                        } else {
                            "negative".to_string()
                        },
                        guardrail: GUARDRAIL.to_string(),
                    });
                }
            }
        }
    }
    out.sort_by(|a, b| {
        b.abs_spearman
            .total_cmp(&a.abs_spearman)
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.horizon_seconds.cmp(&b.horizon_seconds))
    });
    out
}

fn build_v10_horizon_decay(rows: &[V10SpearmanRow]) -> Vec<V10HorizonDecayRow> {
    let mut grouped: BTreeMap<(String, String), Vec<&V10SpearmanRow>> = BTreeMap::new();
    for row in rows {
        grouped
            .entry((row.symbol.clone(), row.feature_name.clone()))
            .or_default()
            .push(row);
    }
    let mut out = Vec::new();
    for ((symbol, feature), mut items) in grouped {
        items.sort_by_key(|row| row.horizon_seconds);
        for (idx, item) in items.iter().enumerate() {
            out.push(V10HorizonDecayRow {
                run_tag: item.run_tag.clone(),
                symbol: symbol.clone(),
                feature_name: feature.clone(),
                horizon_seconds: item.horizon_seconds,
                abs_spearman: item.abs_spearman,
                n: item.n,
                decay_rank: idx + 1,
                guardrail: GUARDRAIL.to_string(),
            });
        }
    }
    out
}

fn build_v10_failure_report(
    config: &V10Config,
    replay_state_files: &[ReplayStateFileRow],
    potential_rows: &[V10PotentialStateRow],
    filter_rows: &[V10FilterStateRow],
    path_trades: &[V10PathTradeRow],
    negative_controls: &[V10NegativeControlRow],
    spearman_rows: &[V10SpearmanRow],
) -> Vec<V10FailureReportRow> {
    let expected_incremental_files = date_range(config.from_date, config.to_date).len()
        * parse_symbol_list(&config.symbols).len();
    let completed_files = replay_state_files
        .iter()
        .filter(|row| row.status == "completed")
        .count();
    let mut rows = Vec::new();
    if completed_files < expected_incremental_files {
        rows.push(V10FailureReportRow {
            run_tag: config.run_tag.clone(),
            severity: "blocker".to_string(),
            check_name: "partial_replay_coverage".to_string(),
            evidence: format!(
                "completed_replay_files={} expected_incremental_files={}",
                completed_files, expected_incremental_files
            ),
            required_action: "continue replay_book_state_files until every pilot incremental shard has durable state parts".to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    let legacy_schema_files = replay_state_files
        .iter()
        .filter(|row| row.status == "completed")
        .filter(|row| !replay_state_file_has_multilevel_schema(row).unwrap_or(false))
        .map(|row| format!("{} {}", row.symbol, row.date))
        .collect::<Vec<_>>();
    if !legacy_schema_files.is_empty() {
        rows.push(V10FailureReportRow {
            run_tag: config.run_tag.clone(),
            severity: "warning".to_string(),
            check_name: "completed_state_parts_missing_multilevel_schema".to_string(),
            evidence: legacy_schema_files.join("; "),
            required_action: "continue or rerun replay_book_state_files with the current schema so state parts include top-25 bid/ask level JSON and depth geometry fields".to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    if potential_rows.is_empty() {
        rows.push(V10FailureReportRow {
            run_tag: config.run_tag.clone(),
            severity: "blocker".to_string(),
            check_name: "no_potential_rows".to_string(),
            evidence: "no replay-derived potential rows were materialized".to_string(),
            required_action: "complete at least one replay state file before path diagnostics"
                .to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    if filter_rows.is_empty() {
        rows.push(V10FailureReportRow {
            run_tag: config.run_tag.clone(),
            severity: "blocker".to_string(),
            check_name: "no_train_valid_filter_rows".to_string(),
            evidence: "no purged validation fold rows were produced".to_string(),
            required_action: "check replay window length and train/validation split coverage"
                .to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    if path_trades.is_empty() {
        rows.push(V10FailureReportRow {
            run_tag: config.run_tag.clone(),
            severity: "warning".to_string(),
            check_name: "no_path_trades".to_string(),
            evidence: "movable-anchor filters produced zero executable-path diagnostic trades"
                .to_string(),
            required_action:
                "inspect train-fitted thresholds and anchor sparsity before changing parameters"
                    .to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    if negative_controls.is_empty() {
        rows.push(V10FailureReportRow {
            run_tag: config.run_tag.clone(),
            severity: "warning".to_string(),
            check_name: "no_negative_controls".to_string(),
            evidence: "negative-control rows were not generated".to_string(),
            required_action: "negative controls require at least one path trade group".to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    if spearman_rows.is_empty() {
        rows.push(V10FailureReportRow {
            run_tag: config.run_tag.clone(),
            severity: "warning".to_string(),
            check_name: "no_spearman_diagnostics".to_string(),
            evidence: "no feature/forward-return Spearman rows were generated".to_string(),
            required_action:
                "ensure replay state rows contain valid mid prices across the requested horizons"
                    .to_string(),
            guardrail: GUARDRAIL.to_string(),
        });
    }
    rows.push(V10FailureReportRow {
        run_tag: config.run_tag.clone(),
        severity: "info".to_string(),
        check_name: "research_guardrail".to_string(),
        evidence: "outputs are diagnostics only: no trading advice, no execution recommendation, no alpha claim".to_string(),
        required_action: "treat all path and cost outputs as validation artifacts, not deployable rules".to_string(),
        guardrail: GUARDRAIL.to_string(),
    });
    rows
}

fn replay_state_file_has_multilevel_schema(state_file: &ReplayStateFileRow) -> Result<bool> {
    if state_file.part_files == 0 {
        return Ok(false);
    }
    let first_part = replay_state_part_path(Path::new(&state_file.output_path), 1);
    if !first_part.exists() {
        return Ok(false);
    }
    let file = File::open(&first_part)
        .with_context(|| format!("failed to open {}", first_part.display()))?;
    let mut reader = BufReader::new(file);
    let mut header = String::new();
    reader
        .read_line(&mut header)
        .with_context(|| format!("failed to read {}", first_part.display()))?;
    let header = parse_header_line(&header)?;
    Ok(header.iter().any(|col| col == "bid_top_levels_json")
        && header.iter().any(|col| col == "ask_top_levels_json")
        && header.iter().any(|col| col == "bid_depth_25")
        && header.iter().any(|col| col == "ask_depth_25"))
}

fn v10_failure_report_has_schema_check(path: &Path) -> Result<bool> {
    if !path.exists() {
        return Ok(false);
    }
    let rows = load_csv_rows::<V10FailureReportRow>(path)?;
    Ok(rows
        .iter()
        .any(|row| row.check_name == "completed_state_parts_missing_multilevel_schema"))
}

fn v10_potential_by_symbol(
    rows: &[V10PotentialStateRow],
) -> BTreeMap<String, Vec<&V10PotentialStateRow>> {
    let mut grouped: BTreeMap<String, Vec<&V10PotentialStateRow>> = BTreeMap::new();
    for row in rows {
        grouped.entry(row.symbol.clone()).or_default().push(row);
    }
    for rows in grouped.values_mut() {
        rows.sort_by_key(|row| row.local_timestamp);
    }
    grouped
}

fn load_reusable_potential_rows(
    path: &Path,
    replay_state_files: &[ReplayStateFileRow],
    require_fresh_mtime: bool,
) -> Result<Option<Vec<V10PotentialStateRow>>> {
    if !path.exists() {
        return Ok(None);
    }
    if require_fresh_mtime && !output_is_newer_than_state_parts(path, replay_state_files)? {
        return Ok(None);
    }
    let rows = load_csv_rows::<V10PotentialStateRow>(path)?;
    if v10_potential_rows_cover_state_files(&rows, replay_state_files) {
        Ok(Some(rows))
    } else {
        Ok(None)
    }
}

fn output_is_newer_than_state_parts(
    output_path: &Path,
    replay_state_files: &[ReplayStateFileRow],
) -> Result<bool> {
    let output_modified = fs::metadata(output_path)
        .with_context(|| format!("failed to stat {}", output_path.display()))?
        .modified()
        .with_context(|| format!("failed to read mtime for {}", output_path.display()))?;
    for state_file in replay_state_files {
        if state_file.status != "completed" {
            continue;
        }
        let output_dir = Path::new(&state_file.output_path);
        for part_index in 1..=state_file.part_files {
            let part_path = replay_state_part_path(output_dir, part_index);
            let part_modified = fs::metadata(&part_path)
                .with_context(|| format!("failed to stat {}", part_path.display()))?
                .modified()
                .with_context(|| format!("failed to read mtime for {}", part_path.display()))?;
            if part_modified > output_modified {
                return Ok(false);
            }
        }
    }
    Ok(true)
}

fn v10_potential_rows_cover_state_files(
    rows: &[V10PotentialStateRow],
    replay_state_files: &[ReplayStateFileRow],
) -> bool {
    let present = rows
        .iter()
        .map(|row| (row.date.clone(), row.symbol.clone()))
        .collect::<HashSet<_>>();
    replay_state_files
        .iter()
        .filter(|row| row.status == "completed")
        .all(|row| present.contains(&(row.date.clone(), row.symbol.clone())))
}

fn v10_filter_by_fold_symbol(
    rows: &[V10FilterStateRow],
) -> BTreeMap<(String, String), Vec<&V10FilterStateRow>> {
    let mut grouped: BTreeMap<(String, String), Vec<&V10FilterStateRow>> = BTreeMap::new();
    for row in rows {
        grouped
            .entry((row.fold.clone(), row.symbol.clone()))
            .or_default()
            .push(row);
    }
    for rows in grouped.values_mut() {
        rows.sort_by_key(|row| row.local_timestamp);
    }
    grouped
}

fn v10_future_returns(rows: &[&V10PotentialStateRow], horizon_seconds: u32) -> Vec<Option<f64>> {
    let horizon_us = horizon_seconds as u64 * 1_000_000;
    let mut out = vec![None; rows.len()];
    let mut j = 0usize;
    for i in 0..rows.len() {
        let target_ts = rows[i].local_timestamp.saturating_add(horizon_us);
        if j < i {
            j = i;
        }
        while j < rows.len() && rows[j].local_timestamp < target_ts {
            j += 1;
        }
        let (Some(start), Some(end)) =
            (rows[i].mid_price, rows.get(j).and_then(|row| row.mid_price))
        else {
            continue;
        };
        if start > 0.0 {
            out[i] = v10_finite((end - start) / start * 10_000.0);
        }
    }
    out
}

fn v10_potential_feature(row: &V10PotentialStateRow, feature: &str) -> Option<f64> {
    match feature {
        "net_potential" => row.net_potential,
        "potential_gradient" => row.potential_gradient,
        "potential_curvature" => row.potential_curvature,
        "energy_release" => row.energy_release,
        "queue_depth_pressure" => row.queue_depth_pressure,
        "replenish_relaxation" => row.replenish_relaxation,
        "cancellation_withdrawal_energy" => row.cancellation_withdrawal_energy,
        "trade_flow_imbalance" => row.trade_flow_imbalance,
        "fill_realism_score" => row.fill_realism_score,
        _ => None,
    }
}

fn v10_gross_bps(side: &str, entry: f64, exit: f64) -> f64 {
    if side == "short" {
        (entry - exit) / entry * 10_000.0
    } else {
        (exit - entry) / entry * 10_000.0
    }
}

fn v10_bucket(value: f64, low: f64, high: f64) -> String {
    if value <= low {
        "low".to_string()
    } else if value >= high {
        "high".to_string()
    } else {
        "mid".to_string()
    }
}

fn v10_mean_opt(values: &[Option<f64>]) -> Option<f64> {
    let finite = values
        .iter()
        .filter_map(|value| value.and_then(v10_finite))
        .collect::<Vec<_>>();
    v10_mean(&finite)
}

fn v10_mean(values: &[f64]) -> Option<f64> {
    let finite = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if finite.is_empty() {
        None
    } else {
        Some(finite.iter().sum::<f64>() / finite.len() as f64)
    }
}

fn v10_quantile(values: &[f64], q: f64) -> Option<f64> {
    let mut finite = values
        .iter()
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if finite.is_empty() {
        return None;
    }
    finite.sort_by(|a, b| a.total_cmp(b));
    let pos = q.clamp(0.0, 1.0) * (finite.len() - 1) as f64;
    let lo = pos.floor() as usize;
    let hi = pos.ceil() as usize;
    if lo == hi {
        Some(finite[lo])
    } else {
        let weight = pos - lo as f64;
        Some(finite[lo] * (1.0 - weight) + finite[hi] * weight)
    }
}

fn v10_profit_factor(pnl: &[f64]) -> Option<f64> {
    let gains: f64 = pnl.iter().copied().filter(|value| *value > 0.0).sum();
    let losses: f64 = pnl
        .iter()
        .copied()
        .filter(|value| *value < 0.0)
        .map(f64::abs)
        .sum();
    if losses > 0.0 {
        v10_finite(gains / losses)
    } else if gains > 0.0 {
        Some(f64::INFINITY)
    } else {
        None
    }
}

fn v10_max_drawdown(pnl: &[f64]) -> f64 {
    let mut equity = 0.0;
    let mut peak = 0.0;
    let mut max_drawdown = 0.0;
    for value in pnl {
        equity += value;
        if equity > peak {
            peak = equity;
        }
        let drawdown = peak - equity;
        if drawdown > max_drawdown {
            max_drawdown = drawdown;
        }
    }
    max_drawdown
}

fn v10_rate(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64
    }
}

fn v10_spearman(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 3 {
        return None;
    }
    let rx = v10_ranks(xs);
    let ry = v10_ranks(ys);
    v10_corr(&rx, &ry)
}

fn v10_corr(xs: &[f64], ys: &[f64]) -> Option<f64> {
    if xs.len() != ys.len() || xs.len() < 3 {
        return None;
    }
    let mean_x = v10_mean(xs)?;
    let mean_y = v10_mean(ys)?;
    let mut num = 0.0;
    let mut den_x = 0.0;
    let mut den_y = 0.0;
    let mut count = 0usize;
    for (&x, &y) in xs.iter().zip(ys.iter()) {
        if !x.is_finite() || !y.is_finite() {
            continue;
        }
        let dx = x - mean_x;
        let dy = y - mean_y;
        num += dx * dy;
        den_x += dx * dx;
        den_y += dy * dy;
        count += 1;
    }
    if count < 3 || den_x <= 0.0 || den_y <= 0.0 {
        None
    } else {
        v10_finite(num / (den_x.sqrt() * den_y.sqrt()))
    }
}

fn v10_ranks(values: &[f64]) -> Vec<f64> {
    let mut indexed = values.iter().copied().enumerate().collect::<Vec<_>>();
    indexed.sort_by(|a, b| a.1.total_cmp(&b.1));
    let mut ranks = vec![0.0; values.len()];
    let mut idx = 0usize;
    while idx < indexed.len() {
        let start = idx;
        let value = indexed[idx].1;
        while idx < indexed.len() && indexed[idx].1 == value {
            idx += 1;
        }
        let rank = (start + idx - 1) as f64 / 2.0 + 1.0;
        for item in indexed.iter().take(idx).skip(start) {
            ranks[item.0] = rank;
        }
    }
    ranks
}

fn v10_pseudo_bool(timestamp: u64, salt: u64) -> bool {
    let mut x = timestamp ^ salt.wrapping_mul(0x9E37_79B9_7F4A_7C15);
    x ^= x >> 33;
    x = x.wrapping_mul(0xff51afd7ed558ccd);
    x ^= x >> 33;
    x & 1 == 0
}

fn v10_squash(value: f64, scale: f64) -> f64 {
    (value / scale.max(1e-9)).tanh()
}

fn v10_finite(value: f64) -> Option<f64> {
    value.is_finite().then_some(value)
}

fn build_replay_summary_rows(
    config: &V10Config,
    inventory_rows: &[InventoryRow],
    limit: Option<usize>,
) -> Result<Vec<ReplayPreviewRow>> {
    let mut rows = Vec::new();
    for inventory in inventory_rows.iter().filter(|row| {
        row.data_type == "incremental_book_L2" && row.status == "present" && row.required_schema_ok
    }) {
        rows.push(build_replay_summary_row(config, inventory, limit, None)?);
    }
    rows.sort_by(|a, b| a.date.cmp(&b.date).then_with(|| a.symbol.cmp(&b.symbol)));
    Ok(rows)
}

fn build_replay_summary_row(
    config: &V10Config,
    inventory: &InventoryRow,
    limit: Option<usize>,
    progress: Option<&mut dyn FnMut(usize, Option<u64>) -> Result<()>>,
) -> Result<ReplayPreviewRow> {
    let path = PathBuf::from(&inventory.expected_path);
    let stats = summarize_incremental_book_file(&path, limit, progress)?;
    Ok(ReplayPreviewRow {
        run_tag: config.run_tag.clone(),
        date: inventory.date.clone(),
        symbol: inventory.symbol.clone(),
        raw_rows_read: stats.raw_rows_read,
        replay_rows: stats.replay_rows,
        snapshot_batches: stats.snapshot_batches,
        first_local_timestamp: stats.first_local_timestamp,
        last_local_timestamp: stats.last_local_timestamp,
        avg_bid_levels: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.bid_levels_sum / stats.replay_rows as f64
        },
        avg_ask_levels: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.ask_levels_sum / stats.replay_rows as f64
        },
        max_bid_levels: stats.max_bid_levels,
        max_ask_levels: stats.max_ask_levels,
        avg_spread_bps: mean_option(&stats.spreads),
        median_spread_bps: median(stats.spreads.clone()),
        top_of_book_coverage: rate_count(stats.top_of_book_count, stats.replay_rows),
        crossed_batches: stats.crossed_batches,
        crossed_level_removals: stats.crossed_level_removals,
        bid_depth_5_mean: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.bid_depth_5_sum / stats.replay_rows as f64
        },
        ask_depth_5_mean: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.ask_depth_5_sum / stats.replay_rows as f64
        },
    })
}

fn build_replay_full_summary_row_from_state_file(
    config: &V10Config,
    state_file: &ReplayStateFileRow,
) -> Result<ReplayPreviewRow> {
    let stats = summarize_replayed_state_parts(state_file)?;
    Ok(ReplayPreviewRow {
        run_tag: config.run_tag.clone(),
        date: state_file.date.clone(),
        symbol: state_file.symbol.clone(),
        raw_rows_read: state_file.raw_rows_read,
        replay_rows: stats.replay_rows,
        snapshot_batches: stats.snapshot_batches,
        first_local_timestamp: stats.first_local_timestamp,
        last_local_timestamp: stats.last_local_timestamp,
        avg_bid_levels: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.bid_levels_sum / stats.replay_rows as f64
        },
        avg_ask_levels: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.ask_levels_sum / stats.replay_rows as f64
        },
        max_bid_levels: stats.max_bid_levels,
        max_ask_levels: stats.max_ask_levels,
        avg_spread_bps: mean_option(&stats.spreads),
        median_spread_bps: median(stats.spreads),
        top_of_book_coverage: rate_count(stats.top_of_book_count, stats.replay_rows),
        crossed_batches: stats.crossed_batches,
        crossed_level_removals: stats.crossed_level_removals,
        bid_depth_5_mean: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.bid_depth_5_sum / stats.replay_rows as f64
        },
        ask_depth_5_mean: if stats.replay_rows == 0 {
            0.0
        } else {
            stats.ask_depth_5_sum / stats.replay_rows as f64
        },
    })
}

fn replay_state_output_path(config: &V10Config, symbol: &str, date: &str) -> PathBuf {
    config
        .data_root
        .join("derived")
        .join("bonk_v10_replayed_book_state")
        .join(format!("run_tag={}", config.run_tag))
        .join(format!("symbol={symbol}"))
        .join(format!("dt={date}"))
        .join("state_parts")
}

fn replay_state_part_path(output_dir: &Path, part_index: usize) -> PathBuf {
    output_dir.join(format!("part_{part_index:06}.csv"))
}

fn replay_state_file_has_expected_parts(state_file: &ReplayStateFileRow) -> bool {
    if state_file.status != "completed" || state_file.part_files == 0 {
        return false;
    }
    let output_dir = Path::new(&state_file.output_path);
    if !output_dir.is_dir() {
        return false;
    }
    (1..=state_file.part_files).all(|part_index| {
        let path = replay_state_part_path(output_dir, part_index);
        path.is_file() && path.metadata().is_ok_and(|metadata| metadata.len() > 0)
    })
}

fn replay_state_file_is_reusable(state_file: &ReplayStateFileRow) -> bool {
    replay_state_file_has_expected_parts(state_file)
        && replay_state_file_has_multilevel_schema(state_file).unwrap_or(false)
}

fn clear_replay_state_parts(output_dir: &Path) -> Result<()> {
    if !output_dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(output_dir)
        .with_context(|| format!("failed to read {}", output_dir.display()))?
    {
        let entry = entry.with_context(|| format!("failed to read {}", output_dir.display()))?;
        let path = entry.path();
        let is_part = path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.starts_with("part_") && name.ends_with(".csv"));
        if is_part {
            fs::remove_file(&path)
                .with_context(|| format!("failed to remove stale {}", path.display()))?;
        }
    }
    Ok(())
}

fn upsert_replay_state_row(rows: &mut Vec<ReplayStateFileRow>, new_row: ReplayStateFileRow) {
    if let Some(existing) = rows
        .iter_mut()
        .find(|row| row.date == new_row.date && row.symbol == new_row.symbol)
    {
        *existing = new_row;
    } else {
        rows.push(new_row);
    }
}

fn replay_incremental_book_file_to_parts(
    path: &Path,
    output_dir: &Path,
    mut progress: Option<&mut dyn FnMut(usize, Option<u64>) -> Result<()>>,
) -> Result<(usize, usize, usize, Option<u64>, Option<u64>)> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = csv::Reader::from_reader(decoder);
    fs::create_dir_all(output_dir)
        .with_context(|| format!("failed to create {}", output_dir.display()))?;
    clear_replay_state_parts(output_dir)?;
    let mut buffer = Vec::new();
    let mut part_files = 0usize;
    let mut replay_rows = 0usize;
    let mut first_local_timestamp = None;
    let mut last_local_timestamp = None;
    let mut raw_rows_read = 0usize;
    let mut book = LocalBook::default();
    let mut seen_snapshot = false;
    let mut previous_was_snapshot = false;
    let mut batch_rows = 0usize;
    let mut batch_snapshot = false;
    let mut batch_local_timestamp = 0u64;
    let mut batch_timestamp = 0u64;
    let mut batch_exchange = String::new();
    let mut batch_symbol = String::new();
    let mut batch_crossed_removed = 0usize;

    for record in reader.deserialize() {
        let row: IncrementalBookCsvRow =
            record.with_context(|| format!("failed to parse {}", path.display()))?;
        raw_rows_read += 1;
        if raw_rows_read % FULL_SUMMARY_PROGRESS_INTERVAL_ROWS == 0 {
            if let Some(callback) = progress.as_mut() {
                callback(raw_rows_read, Some(row.local_timestamp))?;
            }
        }
        if !seen_snapshot && !row.is_snapshot {
            continue;
        }
        if batch_rows > 0 && row.local_timestamp != batch_local_timestamp {
            let state = materialize_replayed_state(
                &book,
                &batch_exchange,
                &batch_symbol,
                batch_timestamp,
                batch_local_timestamp,
                batch_snapshot,
                batch_rows,
                batch_crossed_removed,
                5,
            );
            if first_local_timestamp.is_none() {
                first_local_timestamp = Some(state.local_timestamp);
            }
            last_local_timestamp = Some(state.local_timestamp);
            buffer.push(state);
            replay_rows += 1;
            if buffer.len() >= REPLAY_STATE_PART_ROWS {
                part_files += 1;
                write_csv_atomic(&replay_state_part_path(output_dir, part_files), &buffer)?;
                buffer.clear();
            }
            batch_rows = 0;
            batch_crossed_removed = 0;
        }
        if row.is_snapshot && !previous_was_snapshot {
            book = LocalBook::default();
            seen_snapshot = true;
        }
        if batch_rows == 0 {
            batch_local_timestamp = row.local_timestamp;
            batch_timestamp = row.timestamp;
            batch_snapshot = row.is_snapshot;
            batch_exchange = row.exchange.clone();
            batch_symbol = row.symbol.clone();
        }
        batch_crossed_removed += apply_incremental_row(&mut book, &row);
        batch_rows += 1;
        previous_was_snapshot = row.is_snapshot;
    }

    if batch_rows > 0 {
        let state = materialize_replayed_state(
            &book,
            &batch_exchange,
            &batch_symbol,
            batch_timestamp,
            batch_local_timestamp,
            batch_snapshot,
            batch_rows,
            batch_crossed_removed,
            5,
        );
        if first_local_timestamp.is_none() {
            first_local_timestamp = Some(state.local_timestamp);
        }
        last_local_timestamp = Some(state.local_timestamp);
        buffer.push(state);
        replay_rows += 1;
    }

    if !buffer.is_empty() {
        part_files += 1;
        write_csv_atomic(&replay_state_part_path(output_dir, part_files), &buffer)?;
    }

    Ok((
        part_files,
        replay_rows,
        raw_rows_read,
        first_local_timestamp,
        last_local_timestamp,
    ))
}

fn summarize_replayed_state_parts(state_file: &ReplayStateFileRow) -> Result<FileReplayStats> {
    let output_dir = Path::new(&state_file.output_path);
    let mut stats = FileReplayStats::default();
    stats.raw_rows_read = state_file.raw_rows_read;
    for part_index in 1..=state_file.part_files {
        let part_path = replay_state_part_path(output_dir, part_index);
        let file = File::open(&part_path)
            .with_context(|| format!("failed to open {}", part_path.display()))?;
        let mut reader = csv::Reader::from_reader(file);
        for record in reader.deserialize() {
            let row: ReplayedBookStateRow =
                record.with_context(|| format!("failed to parse {}", part_path.display()))?;
            accumulate_replay_state(&mut stats, &row);
        }
    }
    Ok(stats)
}

fn summarize_incremental_book_file(
    path: &Path,
    limit: Option<usize>,
    mut progress: Option<&mut dyn FnMut(usize, Option<u64>) -> Result<()>>,
) -> Result<FileReplayStats> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = csv::Reader::from_reader(decoder);
    let mut stats = FileReplayStats::default();
    let mut book = LocalBook::default();
    let mut seen_snapshot = false;
    let mut previous_was_snapshot = false;
    let mut batch_rows = 0usize;
    let mut batch_snapshot = false;
    let mut batch_local_timestamp = 0u64;
    let mut batch_timestamp = 0u64;
    let mut batch_exchange = String::new();
    let mut batch_symbol = String::new();
    let mut batch_crossed_removed = 0usize;

    for record in reader.deserialize() {
        if limit.is_some_and(|value| stats.raw_rows_read >= value) {
            break;
        }
        let row: IncrementalBookCsvRow =
            record.with_context(|| format!("failed to parse {}", path.display()))?;
        stats.raw_rows_read += 1;
        if stats.raw_rows_read % FULL_SUMMARY_PROGRESS_INTERVAL_ROWS == 0 {
            if let Some(callback) = progress.as_mut() {
                callback(stats.raw_rows_read, Some(row.local_timestamp))?;
            }
        }
        if !seen_snapshot && !row.is_snapshot {
            continue;
        }
        if batch_rows > 0 && row.local_timestamp != batch_local_timestamp {
            let state = materialize_replayed_state(
                &book,
                &batch_exchange,
                &batch_symbol,
                batch_timestamp,
                batch_local_timestamp,
                batch_snapshot,
                batch_rows,
                batch_crossed_removed,
                5,
            );
            accumulate_replay_state(&mut stats, &state);
            batch_rows = 0;
            batch_crossed_removed = 0;
        }
        if row.is_snapshot && !previous_was_snapshot {
            book = LocalBook::default();
            seen_snapshot = true;
        }
        if batch_rows == 0 {
            batch_local_timestamp = row.local_timestamp;
            batch_timestamp = row.timestamp;
            batch_snapshot = row.is_snapshot;
            batch_exchange = row.exchange.clone();
            batch_symbol = row.symbol.clone();
        }
        batch_crossed_removed += apply_incremental_row(&mut book, &row);
        batch_rows += 1;
        previous_was_snapshot = row.is_snapshot;
    }

    if batch_rows > 0 {
        let state = materialize_replayed_state(
            &book,
            &batch_exchange,
            &batch_symbol,
            batch_timestamp,
            batch_local_timestamp,
            batch_snapshot,
            batch_rows,
            batch_crossed_removed,
            5,
        );
        accumulate_replay_state(&mut stats, &state);
    }

    Ok(stats)
}

fn accumulate_replay_state(stats: &mut FileReplayStats, state: &ReplayedBookStateRow) {
    stats.replay_rows += 1;
    if state.snapshot_batch {
        stats.snapshot_batches += 1;
    }
    if stats.first_local_timestamp.is_none() {
        stats.first_local_timestamp = Some(state.local_timestamp);
    }
    stats.last_local_timestamp = Some(state.local_timestamp);
    stats.bid_levels_sum += state.bid_levels as f64;
    stats.ask_levels_sum += state.ask_levels as f64;
    stats.max_bid_levels = stats.max_bid_levels.max(state.bid_levels);
    stats.max_ask_levels = stats.max_ask_levels.max(state.ask_levels);
    if let Some(spread) = state.spread_bps {
        stats.spreads.push(spread);
    }
    if state.best_bid_price.is_some() && state.best_ask_price.is_some() {
        stats.top_of_book_count += 1;
    }
    if state.crossed_levels_removed > 0 {
        stats.crossed_batches += 1;
    }
    stats.crossed_level_removals += state.crossed_levels_removed;
    stats.bid_depth_5_sum += state.bid_depth_5;
    stats.ask_depth_5_sum += state.ask_depth_5;
}

fn run_download(
    config: &V10Config,
    rows: &[DownloadMetadataRow],
) -> Result<BullishDownloadSummary> {
    let actionable_symbols = rows
        .iter()
        .filter(|row| row.action != "keep_local")
        .map(|row| row.symbol.clone())
        .collect::<HashSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let actionable_types = rows
        .iter()
        .filter(|row| row.action != "keep_local")
        .map(|row| row.data_type.clone())
        .collect::<HashSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    run_bullish_l2_download(&BullishDownloadConfig {
        exchange: EXCHANGE.to_string(),
        data_root: config.data_root.clone(),
        date_dir: config.date_dir.clone(),
        env_file: config.env_file.clone(),
        api_key: config.api_key.clone(),
        from_date: config.from_date,
        to_date: config.to_date,
        symbols: actionable_symbols.join(","),
        extra_symbols: String::new(),
        data_types: actionable_types.join(","),
        run_tag: format!("{}_v10_missing", config.run_tag),
        timeout_seconds: config.timeout_seconds,
        max_retries: config.max_retries,
        workers: config.workers,
        skip_preflight: config.skip_preflight,
        min_free_gb: config.min_free_gb,
        force: config.force,
        dry_run: false,
        quick_validate: true,
        min_bytes_per_second: crate::download::DEFAULT_MIN_DOWNLOAD_BYTES_PER_SECOND,
        output_prefix: "bonk_bullish_l2_download".to_string(),
    })
}

fn has_actionable_rows(rows: &[DownloadMetadataRow]) -> bool {
    rows.iter().any(|row| row.action != "keep_local")
}

fn action_for_inventory(row: &InventoryRow) -> &'static str {
    match row.status.as_str() {
        "present" if row.required_schema_ok => "keep_local",
        "missing" | "empty" => "download_missing",
        _ => "redownload_invalid",
    }
}

fn reason_for_action(row: &InventoryRow, action: &str) -> String {
    match action {
        "keep_local" => "usable local raw shard already present".to_string(),
        "download_missing" if row.data_type == "incremental_book_L2" => {
            "missing queue-level replay shard; blocks high-fidelity reconstruction".to_string()
        }
        "download_missing" => "required pilot shard is missing locally".to_string(),
        _ => format!("local shard status={} note={}", row.status, row.note),
    }
}

fn action_rank(action: &str) -> usize {
    match action {
        "download_missing" => 0,
        "redownload_invalid" => 1,
        _ => 2,
    }
}

fn classify_inventory_status(validation: &ValidateResult) -> String {
    if !validation.gzip_ok {
        "invalid".to_string()
    } else if validation.empty_payload || validation.sample_rows == 0 {
        "empty".to_string()
    } else {
        "present".to_string()
    }
}

fn validate_required_schema(
    data_type: &str,
    header: &[String],
    ask_levels: usize,
    bid_levels: usize,
) -> bool {
    let required = match data_type {
        "book_snapshot_25" => vec![
            "timestamp",
            "local_timestamp",
            "asks[0].price",
            "asks[0].amount",
            "bids[0].price",
            "bids[0].amount",
        ],
        "book_ticker" => vec![
            "timestamp",
            "local_timestamp",
            "ask_amount",
            "ask_price",
            "bid_price",
            "bid_amount",
        ],
        "trades" => vec![
            "timestamp",
            "local_timestamp",
            "id",
            "side",
            "price",
            "amount",
        ],
        "incremental_book_L2" => vec!["timestamp", "local_timestamp", "price", "amount"],
        _ => Vec::new(),
    };
    let found = required
        .iter()
        .all(|needle| header.iter().any(|field| field == needle));
    if data_type == "book_snapshot_25" {
        found && ask_levels >= 25 && bid_levels >= 25
    } else {
        found
    }
}

fn default_note(data_type: &str, status: &str) -> String {
    match (data_type, status) {
        ("incremental_book_L2", "missing") => {
            "queue-level replay shard is not present locally".to_string()
        }
        ("book_snapshot_25", "present") => {
            "top-25 depth snapshot available for shape, slope, curvature, and barrier proxies"
                .to_string()
        }
        ("book_ticker", "present") => {
            "top-of-book ticker available for quote alignment and microprice evolution".to_string()
        }
        ("trades", "present") => {
            "public trades available for aggressor-flow proxy and event-time alignment".to_string()
        }
        (_, "empty") => "gzip exists but does not contain usable rows".to_string(),
        (_, "invalid") => "local gzip exists but failed validation".to_string(),
        _ => "local shard missing".to_string(),
    }
}

fn stage_for_data_type(data_type: &str) -> &'static str {
    match data_type {
        "incremental_book_L2" => "stage1_incremental_replay",
        _ => "stage0_baseline_raw",
    }
}

fn priority_for_inventory(data_type: &str, status: &str) -> usize {
    match (data_type, status) {
        ("incremental_book_L2", "missing") | ("incremental_book_L2", "empty") => 0,
        (_, "invalid") => 1,
        (_, "missing") | (_, "empty") => 2,
        _ => 3,
    }
}

fn default_estimated_mb(data_type: &str) -> f64 {
    match data_type {
        "incremental_book_L2" => 277.0,
        "book_snapshot_25" => 21.0,
        "book_ticker" => 1.8,
        "trades" => 0.8,
        _ => 0.0,
    }
}

fn detect_levels(header: &[String], prefix: &str) -> usize {
    let mut max_level = 0usize;
    for field in header {
        if let Some(rest) = field.strip_prefix(prefix) {
            if let Some(index_str) = rest
                .strip_prefix('[')
                .and_then(|value| value.split(']').next())
            {
                if let Ok(index) = index_str.parse::<usize>() {
                    max_level = max_level.max(index + 1);
                }
            }
        }
    }
    max_level
}

fn date_range(start: NaiveDate, end: NaiveDate) -> Vec<NaiveDate> {
    let mut out = Vec::new();
    let mut day = start;
    while day <= end {
        out.push(day);
        day = day.succ_opt().expect("date overflow");
    }
    out
}

fn dataset_url(data_type: &str, day: NaiveDate, symbol: &str) -> String {
    format!(
        "{DATASETS_BASE}/{EXCHANGE}/{}/{:04}/{:02}/{:02}/{}.csv.gz",
        data_type,
        day.year(),
        day.month(),
        day.day(),
        symbol
    )
}

fn raw_path(data_root: &Path, data_type: &str, day: NaiveDate, symbol: &str) -> PathBuf {
    data_root
        .join("external")
        .join(format!("{EXCHANGE}_{data_type}"))
        .join(format!("symbol={symbol}"))
        .join(format!("dt={day}"))
        .join(format!("{symbol}.csv.gz"))
}

#[derive(Debug)]
struct ValidateResult {
    gzip_ok: bool,
    header: Vec<String>,
    sample_rows: u64,
    empty_payload: bool,
    error: String,
}

fn quick_validate_gzip_csv(path: &Path) -> Result<ValidateResult> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = BufReader::new(decoder);
    let mut header_line = String::new();
    let header_bytes = reader
        .read_line(&mut header_line)
        .with_context(|| format!("failed to read gzip header {}", path.display()))?;
    if header_bytes == 0 {
        return Ok(ValidateResult {
            gzip_ok: true,
            header: Vec::new(),
            sample_rows: 0,
            empty_payload: true,
            error: "empty gzip payload".to_string(),
        });
    }
    let header = parse_header_line(&header_line)?;
    let mut sample_rows = 0u64;
    let mut line = String::new();
    for _ in 0..3 {
        line.clear();
        if reader
            .read_line(&mut line)
            .with_context(|| format!("failed to read sample row {}", path.display()))?
            == 0
        {
            break;
        }
        if !line.trim().is_empty() {
            sample_rows += 1;
        }
    }
    Ok(ValidateResult {
        gzip_ok: true,
        header,
        sample_rows,
        empty_payload: false,
        error: String::new(),
    })
}

fn parse_header_line(line: &str) -> Result<Vec<String>> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .from_reader(line.as_bytes());
    let record = reader
        .records()
        .next()
        .ok_or_else(|| anyhow::anyhow!("missing CSV header"))?
        .context("failed to parse CSV header")?;
    Ok(record.iter().map(str::to_string).collect())
}

fn fingerprint_inventory(rows: &[InventoryRow]) -> RawInventoryFingerprint {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    let mut file_count = 0usize;
    let mut total_bytes = 0u64;
    for row in rows.iter().filter(|row| row.status == "present") {
        file_count += 1;
        total_bytes = total_bytes.saturating_add(row.bytes);
        row.expected_path.hash(&mut hasher);
        row.bytes.hash(&mut hasher);
        row.sample_rows.hash(&mut hasher);
    }
    RawInventoryFingerprint {
        file_count,
        total_bytes,
        hash: format!("{:016x}", hasher.finish()),
    }
}

fn write_csv_atomic<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    {
        let mut writer = csv::Writer::from_path(&temp)
            .with_context(|| format!("failed to create {}", temp.display()))?;
        for row in rows {
            writer.serialize(row)?;
        }
        writer.flush()?;
    }
    replace_with_temp(&temp, path)
}

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let temp = temp_path_for(path);
    ensure_parent_dir(path)?;
    {
        let mut file =
            File::create(&temp).with_context(|| format!("failed to create {}", temp.display()))?;
        serde_json::to_writer_pretty(&mut file, value)?;
        file.write_all(b"\n")?;
        file.flush()?;
    }
    replace_with_temp(&temp, path)
}

fn load_csv_rows<T: DeserializeOwned>(path: &Path) -> Result<Vec<T>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open {}", path.display()))?;
    let mut rows = Vec::new();
    for record in reader.deserialize() {
        rows.push(record.with_context(|| format!("failed to parse {}", path.display()))?);
    }
    Ok(rows)
}

fn temp_path_for(path: &Path) -> PathBuf {
    let counter = SIDE_CAR_COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let stamp = Utc::now().timestamp_micros();
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("bonk_v10_output");
    std::env::temp_dir().join(format!("{file_name}.{pid}.{stamp}.{counter}.tmp"))
}

fn backup_path_for(path: &Path) -> PathBuf {
    side_car_path_for(path, "bak")
}

fn side_car_path_for(path: &Path, marker: &str) -> PathBuf {
    let counter = SIDE_CAR_COUNTER.fetch_add(1, Ordering::Relaxed);
    let pid = std::process::id();
    let stamp = Utc::now().timestamp_micros();
    path.with_extension(format!(
        "{}.{}.{}.{}.{}",
        path.extension()
            .and_then(|value| value.to_str())
            .unwrap_or("out"),
        pid,
        stamp,
        counter,
        marker
    ))
}

fn replace_with_temp(temp: &Path, path: &Path) -> Result<()> {
    match rename_with_retries(temp, path) {
        Ok(()) => Ok(()),
        Err(first_err) => {
            if !path.exists() {
                return Err(first_err).with_context(|| {
                    format!("failed to rename {} -> {}", temp.display(), path.display())
                });
            }

            let backup = backup_path_for(path);
            rename_with_retries(path, &backup).with_context(|| {
                format!(
                    "failed to move existing {} -> {} after initial temp rename failed: {}",
                    path.display(),
                    backup.display(),
                    first_err
                )
            })?;

            match rename_with_retries(temp, path) {
                Ok(()) => {
                    let _ = fs::remove_file(&backup);
                    Ok(())
                }
                Err(second_err) => {
                    if let Err(restore_err) = rename_with_retries(&backup, path) {
                        bail!(
                            "failed to rename {} -> {} after moving existing target to {}; initial rename error: {}; replacement error: {}; restore error: {}",
                            temp.display(),
                            path.display(),
                            backup.display(),
                            first_err,
                            second_err,
                            restore_err
                        );
                    }
                    Err(second_err).with_context(|| {
                        format!(
                            "failed to rename {} -> {} after moving existing target to {}; restored original target; initial rename error: {}",
                            temp.display(),
                            path.display(),
                            backup.display(),
                            first_err
                        )
                    })
                }
            }
        }
    }
}

fn rename_with_retries(from: &Path, to: &Path) -> std::io::Result<()> {
    let mut last_err = None;
    for attempt in 0..=FILE_REPLACE_RETRIES {
        match fs::rename(from, to) {
            Ok(()) => return Ok(()),
            Err(err) => {
                last_err = Some(err);
                if attempt < FILE_REPLACE_RETRIES {
                    std::thread::sleep(std::time::Duration::from_millis(FILE_REPLACE_RETRY_MS));
                }
            }
        }
    }
    Err(last_err.expect("rename attempted at least once"))
}

fn utc_now_string() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
}

fn parse_default_date(raw: &str) -> NaiveDate {
    NaiveDate::parse_from_str(raw, "%Y-%m-%d").expect("valid default date")
}

#[derive(Debug, Clone, Deserialize)]
pub struct IncrementalBookCsvRow {
    pub exchange: String,
    pub symbol: String,
    pub timestamp: u64,
    pub local_timestamp: u64,
    pub is_snapshot: bool,
    pub side: String,
    pub price: f64,
    pub amount: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplayedBookStateRow {
    pub exchange: String,
    pub symbol: String,
    pub timestamp: u64,
    pub local_timestamp: u64,
    pub snapshot_batch: bool,
    pub batch_rows: usize,
    pub best_bid_price: Option<f64>,
    pub best_bid_amount: Option<f64>,
    pub best_ask_price: Option<f64>,
    pub best_ask_amount: Option<f64>,
    pub mid_price: Option<f64>,
    pub spread_bps: Option<f64>,
    pub microprice: Option<f64>,
    pub bid_levels: usize,
    pub ask_levels: usize,
    pub crossed_levels_removed: usize,
    pub bid_depth_5: f64,
    pub ask_depth_5: f64,
    pub imbalance_5: Option<f64>,
    #[serde(default)]
    pub bid_depth_25: f64,
    #[serde(default)]
    pub ask_depth_25: f64,
    #[serde(default)]
    pub imbalance_25: Option<f64>,
    #[serde(default)]
    pub bid_slope_5: Option<f64>,
    #[serde(default)]
    pub ask_slope_5: Option<f64>,
    #[serde(default)]
    pub depth_curvature_5: Option<f64>,
    #[serde(default)]
    pub bid_top_levels_json: String,
    #[serde(default)]
    pub ask_top_levels_json: String,
}

#[derive(Debug, Clone)]
struct BookLevel {
    price: f64,
    amount: f64,
}

#[derive(Debug, Clone, Default)]
struct LocalBook {
    bids: Vec<BookLevel>,
    asks: Vec<BookLevel>,
}

pub fn read_incremental_book_rows(path: &Path) -> Result<Vec<IncrementalBookCsvRow>> {
    read_incremental_book_rows_limited(path, usize::MAX)
}

fn read_incremental_book_rows_limited(
    path: &Path,
    max_rows: usize,
) -> Result<Vec<IncrementalBookCsvRow>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = csv::Reader::from_reader(decoder);
    let mut rows = Vec::new();
    for record in reader.deserialize() {
        let row: IncrementalBookCsvRow =
            record.with_context(|| format!("failed to parse {}", path.display()))?;
        rows.push(row);
        if rows.len() >= max_rows {
            break;
        }
    }
    Ok(rows)
}

pub fn replay_incremental_rows(
    rows: &[IncrementalBookCsvRow],
    depth_levels: usize,
) -> Vec<ReplayedBookStateRow> {
    if rows.is_empty() {
        return Vec::new();
    }
    let mut ordered = rows.to_vec();
    ordered.sort_by(|a, b| {
        a.local_timestamp
            .cmp(&b.local_timestamp)
            .then_with(|| a.timestamp.cmp(&b.timestamp))
    });
    let mut out = Vec::new();
    let mut book = LocalBook::default();
    let mut seen_snapshot = false;
    let mut previous_was_snapshot = false;
    let mut batch_rows = 0usize;
    let mut batch_snapshot = false;
    let mut batch_local_timestamp = 0u64;
    let mut batch_timestamp = 0u64;
    let mut batch_exchange = String::new();
    let mut batch_symbol = String::new();
    let mut batch_crossed_removed = 0usize;

    for row in &ordered {
        if !seen_snapshot && !row.is_snapshot {
            continue;
        }
        if batch_rows > 0 && row.local_timestamp != batch_local_timestamp {
            out.push(materialize_replayed_state(
                &book,
                &batch_exchange,
                &batch_symbol,
                batch_timestamp,
                batch_local_timestamp,
                batch_snapshot,
                batch_rows,
                batch_crossed_removed,
                depth_levels,
            ));
            batch_rows = 0;
            batch_crossed_removed = 0;
        }
        if row.is_snapshot && !previous_was_snapshot {
            book = LocalBook::default();
            seen_snapshot = true;
        }
        if batch_rows == 0 {
            batch_local_timestamp = row.local_timestamp;
            batch_timestamp = row.timestamp;
            batch_snapshot = row.is_snapshot;
            batch_exchange = row.exchange.clone();
            batch_symbol = row.symbol.clone();
        }
        batch_crossed_removed += apply_incremental_row(&mut book, row);
        batch_rows += 1;
        previous_was_snapshot = row.is_snapshot;
    }
    if batch_rows > 0 {
        out.push(materialize_replayed_state(
            &book,
            &batch_exchange,
            &batch_symbol,
            batch_timestamp,
            batch_local_timestamp,
            batch_snapshot,
            batch_rows,
            batch_crossed_removed,
            depth_levels,
        ));
    }
    out
}

fn apply_incremental_row(book: &mut LocalBook, row: &IncrementalBookCsvRow) -> usize {
    let side = row.side.to_ascii_lowercase();
    let levels = if matches!(side.as_str(), "bid" | "buy" | "bids") {
        &mut book.bids
    } else {
        &mut book.asks
    };
    if let Some(index) = levels
        .iter()
        .position(|level| level.price.to_bits() == row.price.to_bits())
    {
        if row.amount <= 0.0 {
            levels.remove(index);
        } else {
            levels[index].amount = row.amount;
        }
    } else if row.amount > 0.0 {
        levels.push(BookLevel {
            price: row.price,
            amount: row.amount,
        });
    }
    if matches!(side.as_str(), "bid" | "buy" | "bids") {
        levels.sort_by(|a, b| b.price.total_cmp(&a.price));
    } else {
        levels.sort_by(|a, b| a.price.total_cmp(&b.price));
    }
    remove_crossed_levels(book, side.as_str())
}

fn materialize_replayed_state(
    book: &LocalBook,
    exchange: &str,
    symbol: &str,
    timestamp: u64,
    local_timestamp: u64,
    snapshot_batch: bool,
    batch_rows: usize,
    crossed_levels_removed: usize,
    depth_levels: usize,
) -> ReplayedBookStateRow {
    let best_bid = book.bids.first();
    let best_ask = book.asks.first();
    let mid_price = match (best_bid, best_ask) {
        (Some(bid), Some(ask)) => Some((bid.price + ask.price) * 0.5),
        _ => None,
    };
    let spread_bps = match (best_bid, best_ask, mid_price) {
        (Some(bid), Some(ask), Some(mid)) if mid > 0.0 => {
            Some((ask.price - bid.price) / mid * 10_000.0)
        }
        _ => None,
    };
    let microprice = match (best_bid, best_ask) {
        (Some(bid), Some(ask)) if bid.amount + ask.amount > 0.0 => {
            Some((ask.price * bid.amount + bid.price * ask.amount) / (bid.amount + ask.amount))
        }
        _ => None,
    };
    let bid_depth_5 = book
        .bids
        .iter()
        .take(depth_levels)
        .map(|level| level.amount)
        .sum::<f64>();
    let ask_depth_5 = book
        .asks
        .iter()
        .take(depth_levels)
        .map(|level| level.amount)
        .sum::<f64>();
    let imbalance_5 = if bid_depth_5 + ask_depth_5 > 0.0 {
        Some((bid_depth_5 - ask_depth_5) / (bid_depth_5 + ask_depth_5))
    } else {
        None
    };
    let bid_depth_25 = book
        .bids
        .iter()
        .take(25)
        .map(|level| level.amount)
        .sum::<f64>();
    let ask_depth_25 = book
        .asks
        .iter()
        .take(25)
        .map(|level| level.amount)
        .sum::<f64>();
    let imbalance_25 = if bid_depth_25 + ask_depth_25 > 0.0 {
        Some((bid_depth_25 - ask_depth_25) / (bid_depth_25 + ask_depth_25))
    } else {
        None
    };
    let bid_slope_5 = book
        .bids
        .first()
        .zip(book.bids.iter().take(5).last())
        .and_then(|(best, fifth)| v10_finite((best.price - fifth.price).max(0.0)));
    let ask_slope_5 = book
        .asks
        .first()
        .zip(book.asks.iter().take(5).last())
        .and_then(|(best, fifth)| v10_finite((fifth.price - best.price).max(0.0)));
    let top_depth = book.bids.first().map(|level| level.amount).unwrap_or(0.0)
        + book.asks.first().map(|level| level.amount).unwrap_or(0.0);
    let depth_curvature_5 = if bid_depth_5 + ask_depth_5 > 0.0 {
        v10_finite(top_depth / (bid_depth_5 + ask_depth_5))
    } else {
        None
    };
    ReplayedBookStateRow {
        exchange: exchange.to_string(),
        symbol: symbol.to_string(),
        timestamp,
        local_timestamp,
        snapshot_batch,
        batch_rows,
        best_bid_price: best_bid.map(|level| level.price),
        best_bid_amount: best_bid.map(|level| level.amount),
        best_ask_price: best_ask.map(|level| level.price),
        best_ask_amount: best_ask.map(|level| level.amount),
        mid_price,
        spread_bps,
        microprice,
        bid_levels: book.bids.len(),
        ask_levels: book.asks.len(),
        crossed_levels_removed,
        bid_depth_5,
        ask_depth_5,
        imbalance_5,
        bid_depth_25,
        ask_depth_25,
        imbalance_25,
        bid_slope_5,
        ask_slope_5,
        depth_curvature_5,
        bid_top_levels_json: book_levels_json(&book.bids, 25),
        ask_top_levels_json: book_levels_json(&book.asks, 25),
    }
}

fn book_levels_json(levels: &[BookLevel], limit: usize) -> String {
    let levels = levels
        .iter()
        .take(limit)
        .map(|level| (level.price, level.amount))
        .collect::<Vec<_>>();
    serde_json::to_string(&levels).unwrap_or_else(|_| "[]".to_string())
}

fn remove_crossed_levels(book: &mut LocalBook, side: &str) -> usize {
    let mut removed = 0usize;
    loop {
        let (Some(best_bid), Some(best_ask)) = (book.bids.first(), book.asks.first()) else {
            break;
        };
        if best_bid.price < best_ask.price {
            break;
        }
        if matches!(side, "bid" | "buy" | "bids") {
            book.asks.remove(0);
        } else {
            book.bids.remove(0);
        }
        removed += 1;
    }
    removed
}

fn mean_option(values: &[f64]) -> Option<f64> {
    if values.is_empty() {
        None
    } else {
        Some(values.iter().sum::<f64>() / values.len() as f64)
    }
}

fn median(mut values: Vec<f64>) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(|a, b| a.total_cmp(b));
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        Some((values[mid - 1] + values[mid]) * 0.5)
    } else {
        Some(values[mid])
    }
}

fn rate_count(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::Compression;
    use flate2::write::GzEncoder;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn snapshot_schema_requires_top25_levels() {
        let mut header = vec![
            "exchange".to_string(),
            "symbol".to_string(),
            "timestamp".to_string(),
            "local_timestamp".to_string(),
        ];
        for level in 0..25 {
            header.push(format!("asks[{level}].price"));
            header.push(format!("asks[{level}].amount"));
            header.push(format!("bids[{level}].price"));
            header.push(format!("bids[{level}].amount"));
        }
        let ask_levels = detect_levels(&header, "asks");
        let bid_levels = detect_levels(&header, "bids");
        assert_eq!(ask_levels, 25);
        assert_eq!(bid_levels, 25);
        assert!(validate_required_schema(
            "book_snapshot_25",
            &header,
            ask_levels,
            bid_levels
        ));
    }

    #[test]
    fn missing_incremental_is_blocking_download() {
        let row = InventoryRow {
            run_tag: "test".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            data_type: "incremental_book_L2".to_string(),
            stage: "stage1_incremental_replay".to_string(),
            priority: 0,
            expected_path: "data/bonk/v1/external/bullish_incremental_book_L2/...".to_string(),
            url: "https://datasets.tardis.dev/v1/bullish/incremental_book_L2/2026/05/06/BONK1MUSDC.csv.gz".to_string(),
            exists: false,
            status: "missing".to_string(),
            bytes: 0,
            gzip_ok: false,
            sample_rows: 0,
            header_columns: 0,
            header_preview: String::new(),
            required_schema_ok: false,
            ask_levels: 0,
            bid_levels: 0,
            note: "queue-level replay shard is not present locally".to_string(),
        };
        assert_eq!(action_for_inventory(&row), "download_missing");
        let plan = build_download_metadata(&V10Config::default(), &[row], None);
        assert_eq!(plan.len(), 1);
        assert!(plan[0].blocking_reconstruction);
        assert_eq!(plan[0].action, "download_missing");
    }

    #[test]
    fn replay_incremental_resets_on_new_snapshot_batch() {
        let rows = vec![
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 1,
                local_timestamp: 1,
                is_snapshot: false,
                side: "bid".to_string(),
                price: 99.0,
                amount: 1.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 10,
                local_timestamp: 10,
                is_snapshot: true,
                side: "bid".to_string(),
                price: 100.0,
                amount: 2.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 10,
                local_timestamp: 10,
                is_snapshot: true,
                side: "ask".to_string(),
                price: 101.0,
                amount: 3.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 20,
                local_timestamp: 20,
                is_snapshot: false,
                side: "bid".to_string(),
                price: 100.0,
                amount: 0.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 20,
                local_timestamp: 20,
                is_snapshot: false,
                side: "bid".to_string(),
                price: 99.0,
                amount: 4.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 30,
                local_timestamp: 30,
                is_snapshot: true,
                side: "bid".to_string(),
                price: 105.0,
                amount: 1.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 30,
                local_timestamp: 30,
                is_snapshot: true,
                side: "ask".to_string(),
                price: 106.0,
                amount: 1.5,
            },
        ];
        let replayed = replay_incremental_rows(&rows, 5);
        assert_eq!(replayed.len(), 3);
        assert_eq!(replayed[0].best_bid_price, Some(100.0));
        assert_eq!(replayed[0].best_ask_price, Some(101.0));
        assert_eq!(replayed[1].best_bid_price, Some(99.0));
        assert_eq!(replayed[1].best_ask_price, Some(101.0));
        assert_eq!(replayed[2].best_bid_price, Some(105.0));
        assert_eq!(replayed[2].best_ask_price, Some(106.0));
        assert_eq!(replayed[2].bid_levels, 1);
        assert_eq!(replayed[2].ask_levels, 1);
    }

    #[test]
    fn replay_incremental_batches_on_local_timestamp() {
        let rows = vec![
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDT".to_string(),
                timestamp: 10,
                local_timestamp: 100,
                is_snapshot: true,
                side: "bid".to_string(),
                price: 10.0,
                amount: 2.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDT".to_string(),
                timestamp: 10,
                local_timestamp: 100,
                is_snapshot: true,
                side: "ask".to_string(),
                price: 11.0,
                amount: 1.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDT".to_string(),
                timestamp: 11,
                local_timestamp: 101,
                is_snapshot: false,
                side: "ask".to_string(),
                price: 11.0,
                amount: 2.0,
            },
        ];
        let replayed = replay_incremental_rows(&rows, 5);
        assert_eq!(replayed.len(), 2);
        assert_eq!(replayed[0].batch_rows, 2);
        assert_eq!(replayed[1].batch_rows, 1);
        assert_eq!(
            replayed[0].microprice,
            Some((11.0 * 2.0 + 10.0 * 1.0) / 3.0)
        );
        assert_eq!(replayed[1].best_ask_amount, Some(2.0));
        assert_eq!(replayed[1].bid_depth_25, 2.0);
        assert_eq!(replayed[1].ask_depth_25, 2.0);
        assert_eq!(replayed[1].imbalance_25, Some(0.0));
        assert!(replayed[1].bid_top_levels_json.contains("[10.0,2.0]"));
    }

    #[test]
    fn replay_incremental_removes_crossed_levels() {
        let rows = vec![
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 1,
                local_timestamp: 1,
                is_snapshot: true,
                side: "ask".to_string(),
                price: 10.0,
                amount: 1.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 1,
                local_timestamp: 1,
                is_snapshot: true,
                side: "bid".to_string(),
                price: 9.0,
                amount: 1.0,
            },
            IncrementalBookCsvRow {
                exchange: "bullish".to_string(),
                symbol: "BONK1MUSDC".to_string(),
                timestamp: 2,
                local_timestamp: 2,
                is_snapshot: false,
                side: "bid".to_string(),
                price: 10.5,
                amount: 1.0,
            },
        ];
        let replayed = replay_incremental_rows(&rows, 5);
        assert_eq!(replayed.len(), 2);
        assert!(replayed[1].crossed_levels_removed > 0);
        assert_eq!(replayed[1].best_bid_price, Some(10.5));
        assert_eq!(replayed[1].best_ask_price, None);
    }

    #[test]
    fn replay_state_parts_roundtrip_summary() {
        let root = std::env::temp_dir().join(format!(
            "bonk_v10_state_parts_test_{}_{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        ));
        let raw_path = root.join("raw.csv.gz");
        let output_dir = root.join("state_parts");
        fs::create_dir_all(&root).unwrap();

        {
            let file = File::create(&raw_path).unwrap();
            let encoder = GzEncoder::new(file, Compression::default());
            let mut writer = csv::Writer::from_writer(encoder);
            writer
                .write_record([
                    "exchange",
                    "symbol",
                    "timestamp",
                    "local_timestamp",
                    "is_snapshot",
                    "side",
                    "price",
                    "amount",
                ])
                .unwrap();
            for idx in 0..25_010usize {
                let ts = 1_000_000u64 + idx as u64;
                writer
                    .write_record([
                        "bullish",
                        "BONK1MUSDC",
                        &ts.to_string(),
                        &ts.to_string(),
                        if idx == 0 { "true" } else { "false" },
                        if idx % 2 == 0 { "bid" } else { "ask" },
                        if idx % 2 == 0 { "10.0" } else { "10.1" },
                        "1.0",
                    ])
                    .unwrap();
            }
            writer.flush().unwrap();
        }

        let (part_files, replay_rows, raw_rows_read, first_local_timestamp, last_local_timestamp) =
            replay_incremental_book_file_to_parts(&raw_path, &output_dir, None).unwrap();
        assert_eq!(raw_rows_read, 25_010);
        assert_eq!(replay_rows, 25_010);
        assert_eq!(part_files, 2);
        assert_eq!(first_local_timestamp, Some(1_000_000));
        assert_eq!(last_local_timestamp, Some(1_025_009));
        assert!(replay_state_part_path(&output_dir, 1).exists());
        assert!(replay_state_part_path(&output_dir, 2).exists());

        let state_file = ReplayStateFileRow {
            run_tag: "test".to_string(),
            date: "2026-05-06".to_string(),
            symbol: "BONK1MUSDC".to_string(),
            raw_path: path_string(&raw_path),
            output_path: path_string(&output_dir),
            part_files,
            raw_rows_read,
            replay_rows,
            first_local_timestamp,
            last_local_timestamp,
            status: "completed".to_string(),
        };
        assert!(replay_state_file_has_expected_parts(&state_file));
        assert!(replay_state_file_has_multilevel_schema(&state_file).unwrap());
        assert!(replay_state_file_is_reusable(&state_file));

        let stats = summarize_replayed_state_parts(&state_file).unwrap();
        assert_eq!(stats.replay_rows, replay_rows);
        assert_eq!(stats.snapshot_batches, 1);
        assert_eq!(stats.first_local_timestamp, first_local_timestamp);
        assert_eq!(stats.last_local_timestamp, last_local_timestamp);

        let stale_part = replay_state_part_path(&output_dir, 99);
        fs::write(&stale_part, "stale\n").unwrap();
        clear_replay_state_parts(&output_dir).unwrap();
        assert!(!replay_state_part_path(&output_dir, 1).exists());
        assert!(!replay_state_part_path(&output_dir, 2).exists());
        assert!(!stale_part.exists());

        let _ = fs::remove_dir_all(&root);
    }
}

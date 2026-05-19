use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result};
use arrow::array::{Array, BooleanArray, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use finance_chain_core::storage::{
    DERIVED_DIR, RAW_DIR, custom_part_path, f64_array, opt_u64_array, parquet_files_under,
    string_array, u64_array, write_parquet_part, write_schema_metadata,
};
use mon_usdc_collectors::enrichment::{
    DEBUG_TRACE_CALLS_DATASET, DEBUG_TRACE_SUMMARIES_DATASET, POOL_LIQUIDITY_WINDOWS_DATASET,
    POOL_STATE_SAMPLES_DATASET, TX_BODIES_DATASET, TX_RECEIPT_LOG_SUMMARIES_DATASET,
    TX_RECEIPT_LOGS_DATASET,
};
use mon_usdc_collectors::{POOL_SWAP_LOGS_DATASET, known_top4_pools};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::Serialize;

use super::*;

pub const DEFAULT_ENRICHMENT_RUN_TAG: &str = "20260510_87d";

const EVENT_PRICE_PATH_LABELS_DATASET: &str = "event_price_path_labels";
const TX_EXECUTION_PATH_LABELS_DATASET: &str = "tx_execution_path_labels";
const CROSS_POOL_DISLOCATION_FEATURES_DATASET: &str = "cross_pool_dislocation_features";
const POOL_STATE_EVENT_FEATURES_DATASET: &str = "pool_state_event_features";
const DEBUG_TRACE_LABELS_DATASET: &str = "debug_trace_labels";
const TX_EXECUTION_PATH_LABELS_RECONSTRUCTED_DATASET: &str =
    "tx_execution_path_labels_reconstructed";
const POOL_STATE_EVENT_FEATURES_RECONSTRUCTED_DATASET: &str =
    "pool_state_event_features_reconstructed";
const EVENT_EXECUTION_FEATURES_DATASET: &str = "mon_usdc_event_execution_features";

#[derive(Debug, Clone)]
pub struct EnrichmentConfig {
    pub data_root: PathBuf,
    pub run_tag: String,
    pub date_dir: PathBuf,
    pub docs_dir: PathBuf,
    pub force_derived: bool,
    pub no_derived_cache: bool,
    pub progress_interval: usize,
}

#[derive(Debug, Serialize)]
pub struct EnrichmentSummary {
    pub data_root: String,
    pub run_tag: String,
    pub executable_path: String,
    pub outputs: EnrichmentOutputPaths,
    pub coverage: EnrichmentCoverage,
    pub provider_capability_flags: ProviderCapabilityFlags,
    pub final_status: EnrichmentFinalStatus,
}

#[derive(Debug, Serialize)]
pub struct EnrichmentOutputPaths {
    pub completion_json: String,
    pub coverage_csv: String,
    pub path_label_summary_csv: String,
    pub price_path_label_summary_csv: String,
    pub cross_pool_dislocation_summary_csv: String,
    pub pool_state_sample_summary_csv: String,
    pub trace_sample_summary_csv: String,
    pub reconstruction_summary_csv: String,
    pub execution_event_panel_summary_csv: String,
    pub report: String,
}

#[derive(Debug, Serialize)]
pub struct EnrichmentCoverage {
    pub tx_body: TxBodyCoverage,
    pub receipt_log_bundle: ReceiptLogBundleCoverage,
    pub derived_full: DerivedFullCoverage,
    pub sampled: SampledCoverage,
    pub reconstruction: ReconstructionCoverage,
}

#[derive(Debug, Serialize)]
pub struct TxBodyCoverage {
    pub expected_txs: u64,
    pub written_txs: u64,
    pub missing_txs: u64,
    pub request_errors: u64,
}

#[derive(Debug, Serialize)]
pub struct ReceiptLogBundleCoverage {
    pub expected_txs: u64,
    pub summary_rows: u64,
    pub log_rows: u64,
    pub missing_txs: u64,
    pub request_errors: u64,
}

#[derive(Debug, Serialize)]
pub struct DerivedFullCoverage {
    pub event_price_path_rows: u64,
    pub tx_path_label_rows: u64,
    pub cross_pool_rows: u64,
}

#[derive(Debug, Serialize)]
pub struct SampledCoverage {
    pub pool_state_candidate_count: u64,
    pub pool_state_sampled_count: u64,
    pub pool_state_success_count: u64,
    pub pool_state_failed_count: u64,
    pub pool_state_failure_reasons: Vec<FailureReasonRow>,
    pub trace_candidate_count: u64,
    pub trace_sampled_count: u64,
    pub trace_success_count: u64,
    pub trace_failed_count: u64,
    pub trace_failure_reasons: Vec<FailureReasonRow>,
}

#[derive(Debug, Serialize)]
pub struct ReconstructionCoverage {
    pub tx_path: SourceConfidenceCoverage,
    pub pool_event_state: SourceConfidenceCoverage,
    pub pool_pre_state: SourceConfidenceCoverage,
    pub trace_proxy: SourceConfidenceCoverage,
    pub event_panel: EventPanelCoverage,
}

#[derive(Debug, Serialize)]
pub struct SourceConfidenceCoverage {
    pub rows: u64,
    pub by_source_confidence: Vec<SourceConfidenceSummaryRow>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SourceConfidenceSummaryRow {
    pub source: String,
    pub confidence: String,
    pub rows: u64,
}

#[derive(Debug, Serialize)]
pub struct EventPanelCoverage {
    pub rows: u64,
    pub usable_for_execution_research: u64,
    pub quality_tier_counts: Vec<LabelSummaryRow>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FailureReasonRow {
    pub reason: String,
    pub rows: u64,
    pub retryable: bool,
}

#[derive(Debug, Serialize)]
pub struct ProviderCapabilityFlags {
    pub eth_get_transaction_by_hash: bool,
    pub receipt_logs: bool,
    pub eth_call_historical_block: bool,
    pub debug_trace_transaction: bool,
}

#[derive(Debug, Serialize)]
pub struct EnrichmentFinalStatus {
    pub base_enrichment_passed: bool,
    pub sample_enrichment_passed: bool,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct TxBodyRaw {
    fetched_at_utc: String,
    transaction_hash: String,
    request_status: String,
    error: String,
    to_address: String,
    method_selector: String,
    input_len: u64,
    gas: Option<u64>,
    max_priority_fee_per_gas: Option<u64>,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct ReceiptSummaryRaw {
    fetched_at_utc: String,
    transaction_hash: String,
    request_status: String,
    error: String,
    logs_count: u64,
    mon_usdc_swap_log_count: u64,
    erc20_transfer_count: u64,
    pool_addresses_seen: String,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct ReceiptLogRaw {
    transaction_hash: String,
    log_index: u64,
    address: String,
    topic0: String,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct PoolStateRaw {
    event_block_number: u64,
    sample_block_number: u64,
    sample_side: String,
    pool_address: String,
    family: String,
    request_status: String,
    error: String,
    sqrt_price_x96: String,
    tick: String,
    liquidity: String,
    tick_spacing: String,
    active_id: String,
    bin_step: String,
    active_bin_reserve_x: String,
    active_bin_reserve_y: String,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct PoolWindowRaw {
    event_block_number: u64,
    sample_block_number: u64,
    pool_address: String,
    window_kind: String,
    offset: String,
    liquidity_gross: String,
    liquidity_net: String,
    reserve_x: String,
    reserve_y: String,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct TraceSummaryRaw {
    fetched_at_utc: String,
    transaction_hash: String,
    request_status: String,
    error: String,
    call_count: u64,
    max_depth: u64,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct TraceCallRaw {
    transaction_hash: String,
    depth: u64,
    call_type: String,
    from_address: String,
    to_address: String,
    input_selector: String,
    error: String,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct SwapMetadataRaw {
    block_number: u64,
    timestamp: i64,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    family: String,
    sqrt_price_x96: String,
    liquidity_raw: String,
    tick: String,
}

#[derive(Debug, Clone, Serialize)]
struct EventPricePathLabelRow {
    block_number: u64,
    timestamp: i64,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    direction: String,
    quote_abs: f64,
    entry_minute_utc: String,
    fwd_return_5m: Option<f64>,
    fwd_return_15m: Option<f64>,
    fwd_return_1h: Option<f64>,
    fwd_return_3h: Option<f64>,
    fwd_return_6h: Option<f64>,
    mfe_5m: Option<f64>,
    mae_5m: Option<f64>,
    mfe_15m: Option<f64>,
    mae_15m: Option<f64>,
    mfe_1h: Option<f64>,
    mae_1h: Option<f64>,
    mfe_3h: Option<f64>,
    mae_3h: Option<f64>,
    mfe_6h: Option<f64>,
    mae_6h: Option<f64>,
    time_to_peak_seconds: Option<u64>,
    time_to_trough_seconds: Option<u64>,
    reversal_after_initial_move: bool,
    label: String,
}

#[derive(Debug, Clone, Serialize)]
struct TxExecutionPathLabelRow {
    transaction_hash: String,
    path_label: String,
    method_selector: String,
    router_to_address: String,
    pool_sequence: String,
    pool_count: u64,
    swap_count: u64,
    mon_usdc_quote_notional: f64,
    has_external_non_pool_logs: bool,
    input_len: u64,
    gas: Option<u64>,
    max_priority_fee_per_gas: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
struct TxExecutionPathReconstructedRow {
    run_tag: String,
    transaction_hash: String,
    path_label: String,
    tx_path_source: String,
    tx_path_confidence: String,
    tx_body_request_status: String,
    receipt_request_status: String,
    method_selector: String,
    router_to_address: String,
    pool_sequence: String,
    pool_count: u64,
    swap_count: u64,
    mon_usdc_quote_notional: f64,
    external_non_pool_logs_status: String,
    erc20_transfer_count_status: String,
    input_len: u64,
    gas: Option<u64>,
    max_priority_fee_per_gas: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
struct CrossPoolDislocationRow {
    block_number: u64,
    timestamp: i64,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    minute_utc: String,
    pool_price: Option<f64>,
    reference_price: Option<f64>,
    pool_dislocation_bps: Option<f64>,
    max_min_pool_spread_bps: Option<f64>,
    pool_freshness_age_minutes: Option<u64>,
    leader_1m_pool: String,
    leader_5m_pool: String,
    leader_15m_pool: String,
    convergence_5m_label: String,
    convergence_15m_label: String,
}

#[derive(Debug, Clone, Serialize)]
struct PoolStateEventFeatureRow {
    event_block_number: u64,
    sample_block_number: u64,
    sample_side: String,
    pool_address: String,
    family: String,
    sampled: bool,
    request_status: String,
    event_quote_notional: f64,
    active_tick_or_bin: String,
    active_liquidity_or_reserve: String,
    event_notional_to_active_liquidity_proxy: Option<f64>,
    local_window_imbalance: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct PoolStateEventFeatureReconstructedRow {
    run_tag: String,
    block_number: u64,
    transaction_hash: String,
    log_index: u64,
    pool_address: String,
    family: String,
    direction: String,
    quote_abs: f64,
    event_request_status: String,
    pre_request_status: String,
    event_state_source: String,
    event_state_confidence: String,
    pre_state_source: String,
    pre_state_confidence: String,
    event_sqrt_price_x96: String,
    event_tick_or_bin: String,
    event_liquidity_or_reserve: String,
    pre_sqrt_price_x96: String,
    pre_tick_or_bin: String,
    pre_liquidity_or_reserve: String,
    pre_state_age_blocks: Option<u64>,
    pre_state_age_minutes: Option<u64>,
    event_notional_to_active_liquidity_proxy: Option<f64>,
    event_local_window_imbalance: Option<f64>,
    pre_local_window_imbalance: Option<f64>,
    usable_for_research: bool,
}

#[derive(Debug, Clone, Serialize)]
struct DebugTraceLabelRow {
    transaction_hash: String,
    sampled: bool,
    request_status: String,
    call_graph_depth: u64,
    call_count: u64,
    router_calls: u64,
    pool_calls: u64,
    token_calls: u64,
    reverts: u64,
    internal_value_transfers: u64,
    trace_path_class: String,
}

#[derive(Debug, Clone)]
struct TraceProxyLabelRow {
    transaction_hash: String,
    trace_path_class: String,
    trace_source: String,
    trace_confidence: String,
    trace_request_status: String,
    call_graph_depth: Option<u64>,
    call_count: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
struct EventExecutionFeatureRow {
    run_tag: String,
    block_number: u64,
    event_time_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pool_address: String,
    dex_id: String,
    family: String,
    direction: String,
    base_abs: Option<f64>,
    quote_abs: Option<f64>,
    price_quote_per_base: Option<f64>,
    receipt_request_status: String,
    receipt_status: Option<u64>,
    receipt_gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
    base_fee_per_gas: Option<u64>,
    same_block_event_count: u64,
    price_path_label: String,
    fwd_return_5m: Option<f64>,
    fwd_return_15m: Option<f64>,
    fwd_return_1h: Option<f64>,
    fwd_return_3h: Option<f64>,
    fwd_return_6h: Option<f64>,
    pool_dislocation_bps: Option<f64>,
    max_min_pool_spread_bps: Option<f64>,
    convergence_15m_label: String,
    tx_path_label: String,
    tx_path_source: String,
    tx_path_confidence: String,
    pool_event_state_source: String,
    pool_event_state_confidence: String,
    pool_pre_state_source: String,
    pool_pre_state_confidence: String,
    pool_pre_state_age_blocks: Option<u64>,
    trace_path_class: String,
    trace_source: String,
    trace_confidence: String,
    trace_call_graph_depth: Option<u64>,
    trace_call_count: Option<u64>,
    quality_tier: String,
    usable_for_execution_research: bool,
}

#[derive(Debug, Clone, Serialize)]
struct ReconstructionSummaryCsvRow {
    component: String,
    source: String,
    confidence: String,
    rows: u64,
}

#[derive(Debug, Clone, Serialize)]
struct ExecutionPanelSummaryCsvRow {
    scope: String,
    quality_tier: String,
    label: String,
    rows: u64,
}

#[derive(Debug, Serialize)]
struct CoverageCsvRow {
    scope: String,
    metric: String,
    value: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LabelSummaryRow {
    pub label: String,
    pub rows: u64,
}

pub fn run_enrichment_rebuild(config: &EnrichmentConfig) -> Result<EnrichmentSummary> {
    std::fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    std::fs::create_dir_all(&config.docs_dir)
        .with_context(|| format!("failed to create {}", config.docs_dir.display()))?;

    log_stage("scan base raw inventory");
    let raw_inventory = scan_raw_inventory(&config.data_root, config.progress_interval)?;
    let derived = load_or_build_derived(
        &AnalysisConfig {
            data_root: config.data_root.clone(),
            run_tag: config.run_tag.clone(),
            date_dir: config.date_dir.clone(),
            docs_dir: config.docs_dir.clone(),
            force_derived: config.force_derived,
            no_derived_cache: config.no_derived_cache,
            progress_interval: config.progress_interval,
        },
        raw_inventory,
    )?;

    log_stage("read enrichment raw datasets");
    let tx_bodies = dedup_by_latest(
        read_tx_bodies(&config.data_root)?,
        |row| row.transaction_hash.clone(),
        |row| &row.fetched_at_utc,
    )
    .0;
    let receipt_summaries = dedup_by_latest(
        read_receipt_summaries(&config.data_root)?,
        |row| row.transaction_hash.clone(),
        |row| &row.fetched_at_utc,
    )
    .0;
    let receipt_logs = read_receipt_logs(&config.data_root)?;
    let swap_metadata = read_swap_metadata(&config.data_root)?;
    let pool_state = read_pool_state_samples(&config.data_root)?;
    let pool_windows = read_pool_windows(&config.data_root)?;
    let trace_summaries = dedup_by_latest(
        read_trace_summaries(&config.data_root)?,
        |row| row.transaction_hash.clone(),
        |row| &row.fetched_at_utc,
    )
    .0;
    let trace_calls = read_trace_calls(&config.data_root)?;

    log_stage("build enrichment derived rows");
    let price_path_rows =
        build_event_price_path_labels(&derived.clean_events, &derived.minute_prices)?;
    let tx_path_rows = build_tx_execution_path_labels(
        &derived.clean_events,
        &tx_bodies,
        &receipt_summaries,
        &receipt_logs,
    );
    let dislocation_rows = build_cross_pool_dislocation_features(&derived.clean_events)?;
    let pool_state_rows =
        build_pool_state_event_features(&derived.clean_events, &pool_state, &pool_windows);
    let trace_label_rows = build_debug_trace_labels(&trace_summaries, &trace_calls);
    let tx_path_reconstructed_rows = build_tx_execution_path_labels_reconstructed(
        &derived.clean_events,
        &tx_bodies,
        &receipt_summaries,
        &receipt_logs,
        &config.run_tag,
    );
    let pool_state_reconstructed_rows = build_pool_state_event_features_reconstructed(
        &derived.clean_events,
        &swap_metadata,
        &pool_state,
        &pool_windows,
        &config.run_tag,
    );
    let trace_proxy_rows = build_trace_proxy_labels(&tx_path_reconstructed_rows, &trace_label_rows);
    let event_execution_rows = build_event_execution_features(
        &derived.clean_events,
        &price_path_rows,
        &dislocation_rows,
        &tx_path_reconstructed_rows,
        &pool_state_reconstructed_rows,
        &trace_proxy_rows,
        &config.run_tag,
    );

    log_stage("write enrichment derived parquet");
    write_event_price_path_parquet(&config.data_root, &price_path_rows, &config.run_tag)?;
    write_tx_path_parquet(&config.data_root, &tx_path_rows, &config.run_tag)?;
    write_cross_pool_parquet(&config.data_root, &dislocation_rows, &config.run_tag)?;
    write_pool_state_features_parquet(&config.data_root, &pool_state_rows, &config.run_tag)?;
    write_trace_labels_parquet(&config.data_root, &trace_label_rows, &config.run_tag)?;
    write_tx_path_reconstructed_parquet(
        &config.data_root,
        &tx_path_reconstructed_rows,
        &config.run_tag,
    )?;
    write_pool_state_reconstructed_parquet(
        &config.data_root,
        &pool_state_reconstructed_rows,
        &config.run_tag,
    )?;
    write_event_execution_features_parquet(
        &config.data_root,
        &event_execution_rows,
        &config.run_tag,
    )?;

    let outputs = build_enrichment_output_paths(config);
    let coverage = build_enrichment_coverage(
        &derived.coverage,
        &tx_bodies,
        &receipt_summaries,
        &receipt_logs,
        &price_path_rows,
        &tx_path_rows,
        &dislocation_rows,
        &pool_state_rows,
        &trace_label_rows,
        &tx_path_reconstructed_rows,
        &pool_state_reconstructed_rows,
        &trace_proxy_rows,
        &event_execution_rows,
    );
    let provider_capability_flags = ProviderCapabilityFlags {
        eth_get_transaction_by_hash: tx_bodies.iter().any(|row| row.request_status == "ok"),
        receipt_logs: receipt_summaries
            .iter()
            .any(|row| row.request_status == "ok"),
        eth_call_historical_block: pool_state_rows.iter().any(|row| row.request_status == "ok"),
        debug_trace_transaction: trace_label_rows
            .iter()
            .any(|row| row.request_status == "ok"),
    };
    let final_status = EnrichmentFinalStatus {
        base_enrichment_passed: coverage.tx_body.expected_txs == coverage.tx_body.written_txs
            && coverage.tx_body.request_errors == 0
            && coverage.receipt_log_bundle.expected_txs == coverage.receipt_log_bundle.summary_rows
            && coverage.receipt_log_bundle.request_errors == 0,
        sample_enrichment_passed: (coverage.sampled.pool_state_failed_count == 0
            || !coverage.sampled.pool_state_failure_reasons.is_empty())
            && (coverage.sampled.trace_failed_count == 0
                || !coverage.sampled.trace_failure_reasons.is_empty()),
    };

    let coverage_rows = coverage_csv_rows(&coverage);
    let path_label_summary = label_summary(
        tx_path_reconstructed_rows
            .iter()
            .map(|row| row.path_label.clone())
            .collect(),
    );
    let price_path_label_summary = label_summary(
        price_path_rows
            .iter()
            .map(|row| row.label.clone())
            .collect(),
    );
    let cross_pool_summary = label_summary(
        dislocation_rows
            .iter()
            .map(|row| row.convergence_15m_label.clone())
            .collect(),
    );
    let pool_state_summary = label_summary(
        pool_state_rows
            .iter()
            .map(|row| row.request_status.clone())
            .collect(),
    );
    let trace_summary = label_summary(
        trace_label_rows
            .iter()
            .map(|row| row.trace_path_class.clone())
            .collect(),
    );
    let reconstruction_summary = reconstruction_summary_rows(
        &tx_path_reconstructed_rows,
        &pool_state_reconstructed_rows,
        &trace_proxy_rows,
    );
    let execution_panel_summary = execution_panel_summary_rows(&event_execution_rows);
    write_csv(Path::new(&outputs.coverage_csv), &coverage_rows)?;
    write_csv(
        Path::new(&outputs.path_label_summary_csv),
        &path_label_summary,
    )?;
    write_csv(
        Path::new(&outputs.price_path_label_summary_csv),
        &price_path_label_summary,
    )?;
    write_csv(
        Path::new(&outputs.cross_pool_dislocation_summary_csv),
        &cross_pool_summary,
    )?;
    write_csv(
        Path::new(&outputs.pool_state_sample_summary_csv),
        &pool_state_summary,
    )?;
    write_csv(Path::new(&outputs.trace_sample_summary_csv), &trace_summary)?;
    write_csv(
        Path::new(&outputs.reconstruction_summary_csv),
        &reconstruction_summary,
    )?;
    write_csv(
        Path::new(&outputs.execution_event_panel_summary_csv),
        &execution_panel_summary,
    )?;

    let summary = EnrichmentSummary {
        data_root: path_string(&config.data_root),
        run_tag: config.run_tag.clone(),
        executable_path: current_executable_path(),
        outputs,
        coverage,
        provider_capability_flags,
        final_status,
    };
    write_json(Path::new(&summary.outputs.completion_json), &summary)?;
    write_enrichment_report(&summary)?;
    Ok(summary)
}

fn build_enrichment_output_paths(config: &EnrichmentConfig) -> EnrichmentOutputPaths {
    let report = config
        .docs_dir
        .join("markets")
        .join("mon-usdc")
        .join("v1-enrichment-report.md");
    EnrichmentOutputPaths {
        completion_json: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_enrichment_completion_{}.json",
            config.run_tag
        ))),
        coverage_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_enrichment_coverage_{}.csv",
            config.run_tag
        ))),
        path_label_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_path_label_summary_{}.csv",
            config.run_tag
        ))),
        price_path_label_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_price_path_label_summary_{}.csv",
            config.run_tag
        ))),
        cross_pool_dislocation_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_cross_pool_dislocation_summary_{}.csv",
            config.run_tag
        ))),
        pool_state_sample_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_pool_state_sample_summary_{}.csv",
            config.run_tag
        ))),
        trace_sample_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_trace_sample_summary_{}.csv",
            config.run_tag
        ))),
        reconstruction_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_reconstruction_summary_{}.csv",
            config.run_tag
        ))),
        execution_event_panel_summary_csv: path_string(&config.date_dir.join(format!(
            "mon_usdc_v1_execution_event_panel_summary_{}.csv",
            config.run_tag
        ))),
        report: path_string(&report),
    }
}

fn build_event_price_path_labels(
    clean_events: &[EventRecord],
    minute_prices: &MinutePriceSeries,
) -> Result<Vec<EventPricePathLabelRow>> {
    clean_events
        .iter()
        .map(|event| {
            let entry_minute = floor_to_minute(event.timestamp) + 60;
            let entry_price = minute_prices.price_at(entry_minute);
            let h5 = path_metrics(minute_prices, entry_minute, 5)?;
            let h15 = path_metrics(minute_prices, entry_minute, 15)?;
            let h60 = path_metrics(minute_prices, entry_minute, 60)?;
            let h180 = path_metrics(minute_prices, entry_minute, 180)?;
            let h360 = path_metrics(minute_prices, entry_minute, 360)?;
            let label = price_path_label(event, h15.fwd_return, h360.fwd_return, entry_price);
            Ok(EventPricePathLabelRow {
                block_number: event.block_number,
                timestamp: event.timestamp,
                transaction_hash: event.transaction_hash.clone(),
                log_index: event.log_index,
                pool_address: event.pool_address.clone(),
                direction: event.direction_string(),
                quote_abs: event.quote_abs.unwrap_or(0.0),
                entry_minute_utc: utc_string(entry_minute)?,
                fwd_return_5m: h5.fwd_return,
                fwd_return_15m: h15.fwd_return,
                fwd_return_1h: h60.fwd_return,
                fwd_return_3h: h180.fwd_return,
                fwd_return_6h: h360.fwd_return,
                mfe_5m: h5.mfe,
                mae_5m: h5.mae,
                mfe_15m: h15.mfe,
                mae_15m: h15.mae,
                mfe_1h: h60.mfe,
                mae_1h: h60.mae,
                mfe_3h: h180.mfe,
                mae_3h: h180.mae,
                mfe_6h: h360.mfe,
                mae_6h: h360.mae,
                time_to_peak_seconds: h360.time_to_peak_seconds,
                time_to_trough_seconds: h360.time_to_trough_seconds,
                reversal_after_initial_move: reversal_after_initial_move(
                    h15.fwd_return,
                    h360.fwd_return,
                ),
                label,
            })
        })
        .collect()
}

struct PathMetrics {
    fwd_return: Option<f64>,
    mfe: Option<f64>,
    mae: Option<f64>,
    time_to_peak_seconds: Option<u64>,
    time_to_trough_seconds: Option<u64>,
}

fn path_metrics(
    minute_prices: &MinutePriceSeries,
    entry_minute: i64,
    horizon_minutes: i64,
) -> Result<PathMetrics> {
    let entry_price = minute_prices.price_at(entry_minute);
    let exit_price = minute_prices.price_at(entry_minute + horizon_minutes * 60);
    let mut best: Option<(f64, u64)> = None;
    let mut worst: Option<(f64, u64)> = None;
    for minute in 1..=horizon_minutes {
        let ts = entry_minute + minute * 60;
        let ret = forward_return(entry_price, minute_prices.price_at(ts));
        if let Some(ret) = ret {
            if best.map_or(true, |(value, _)| ret > value) {
                best = Some((ret, minute as u64 * 60));
            }
            if worst.map_or(true, |(value, _)| ret < value) {
                worst = Some((ret, minute as u64 * 60));
            }
        }
    }
    Ok(PathMetrics {
        fwd_return: forward_return(entry_price, exit_price),
        mfe: best.map(|(value, _)| value),
        mae: worst.map(|(value, _)| value),
        time_to_peak_seconds: best.map(|(_, seconds)| seconds),
        time_to_trough_seconds: worst.map(|(_, seconds)| seconds),
    })
}

fn price_path_label(
    event: &EventRecord,
    short_return: Option<f64>,
    long_return: Option<f64>,
    entry_price: Option<f64>,
) -> String {
    if entry_price.is_none() || long_return.is_none() {
        return "insufficient_future_price".to_string();
    }
    let side = if event.is_buy_base { 1.0 } else { -1.0 };
    let short_signed = short_return.unwrap_or(0.0) * side;
    let long_signed = long_return.unwrap_or(0.0) * side;
    if long_signed.abs() < 0.0005 {
        "flat".to_string()
    } else if short_signed.signum() != 0.0 && short_signed.signum() != long_signed.signum() {
        "reversal".to_string()
    } else if long_signed > 0.0 {
        "continuation".to_string()
    } else if short_signed.abs() > 0.001 && long_signed.abs() < short_signed.abs() * 0.35 {
        "whipsaw".to_string()
    } else {
        "reversal".to_string()
    }
}

fn reversal_after_initial_move(short_return: Option<f64>, long_return: Option<f64>) -> bool {
    matches!((short_return, long_return), (Some(short), Some(long)) if short.signum() != 0.0 && short.signum() != long.signum())
}

fn build_tx_execution_path_labels(
    clean_events: &[EventRecord],
    tx_bodies: &[TxBodyRaw],
    receipt_summaries: &[ReceiptSummaryRaw],
    receipt_logs: &[ReceiptLogRaw],
) -> Vec<TxExecutionPathLabelRow> {
    let bodies = tx_bodies
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();
    let summaries = receipt_summaries
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();
    let pools = known_pool_set();
    let mut events_by_tx = BTreeMap::<String, Vec<&EventRecord>>::new();
    for event in clean_events {
        events_by_tx
            .entry(event.transaction_hash.clone())
            .or_default()
            .push(event);
    }
    let mut logs_by_tx = BTreeMap::<String, Vec<&ReceiptLogRaw>>::new();
    for log in receipt_logs {
        logs_by_tx
            .entry(log.transaction_hash.clone())
            .or_default()
            .push(log);
    }
    let mut rows = Vec::new();
    for (hash, events) in events_by_tx {
        let body = bodies.get(&hash).copied();
        let summary = summaries.get(&hash).copied();
        let pool_sequence = events
            .iter()
            .map(|event| event.pool_address.clone())
            .collect::<Vec<_>>();
        let pool_count = pool_sequence.iter().collect::<BTreeSet<_>>().len() as u64;
        let swap_count = events.len() as u64;
        let quote_notional = events
            .iter()
            .map(|event| event.quote_abs.unwrap_or(0.0))
            .sum::<f64>();
        let logs = logs_by_tx.get(&hash).cloned().unwrap_or_default();
        let has_external_non_pool_logs = logs
            .iter()
            .any(|log| !pools.contains(&log.address) && !log.topic0.is_empty());
        let method_selector = body
            .map(|row| row.method_selector.clone())
            .unwrap_or_default();
        let router_to = body.map(|row| row.to_address.clone()).unwrap_or_default();
        let label = classify_tx_path(
            body,
            summary,
            &router_to,
            &method_selector,
            pool_count,
            swap_count,
            &events,
        );
        rows.push(TxExecutionPathLabelRow {
            transaction_hash: hash,
            path_label: label,
            method_selector,
            router_to_address: router_to,
            pool_sequence: pool_sequence.join("|"),
            pool_count,
            swap_count,
            mon_usdc_quote_notional: quote_notional,
            has_external_non_pool_logs,
            input_len: body.map(|row| row.input_len).unwrap_or(0),
            gas: body.and_then(|row| row.gas),
            max_priority_fee_per_gas: body.and_then(|row| row.max_priority_fee_per_gas),
        });
    }
    rows
}

fn build_tx_execution_path_labels_reconstructed(
    clean_events: &[EventRecord],
    tx_bodies: &[TxBodyRaw],
    receipt_summaries: &[ReceiptSummaryRaw],
    receipt_logs: &[ReceiptLogRaw],
    run_tag: &str,
) -> Vec<TxExecutionPathReconstructedRow> {
    let bodies = tx_bodies
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();
    let summaries = receipt_summaries
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();
    let pools = known_pool_set();
    let mut events_by_tx = BTreeMap::<String, Vec<&EventRecord>>::new();
    for event in clean_events {
        events_by_tx
            .entry(event.transaction_hash.clone())
            .or_default()
            .push(event);
    }
    let mut logs_by_tx = BTreeMap::<String, Vec<&ReceiptLogRaw>>::new();
    for log in receipt_logs {
        logs_by_tx
            .entry(log.transaction_hash.clone())
            .or_default()
            .push(log);
    }

    let mut rows = Vec::new();
    for (hash, events) in events_by_tx {
        let body = bodies.get(&hash).copied();
        let summary = summaries.get(&hash).copied();
        let body_ok = body.is_some_and(|row| row.request_status == "ok");
        let summary_ok = summary.is_some_and(|row| row.request_status == "ok");
        let pool_sequence = events
            .iter()
            .map(|event| event.pool_address.clone())
            .collect::<Vec<_>>();
        let pool_count = pool_sequence.iter().collect::<BTreeSet<_>>().len() as u64;
        let swap_count = events.len() as u64;
        let quote_notional = events
            .iter()
            .map(|event| event.quote_abs.unwrap_or(0.0))
            .sum::<f64>();
        let logs = logs_by_tx.get(&hash).cloned().unwrap_or_default();
        let method_selector = body
            .map(|row| row.method_selector.clone())
            .unwrap_or_default();
        let router_to = body.map(|row| row.to_address.clone()).unwrap_or_default();
        let label = classify_tx_path_reconstructed(
            body,
            summary,
            &router_to,
            &method_selector,
            pool_count,
            swap_count,
            &events,
        );
        let (tx_path_source, tx_path_confidence) =
            tx_path_source_confidence(body_ok, summary_ok, swap_count, !method_selector.is_empty());
        let external_non_pool_logs_status = if summary_ok {
            logs.iter()
                .any(|log| !pools.contains(&log.address) && !log.topic0.is_empty())
                .to_string()
        } else {
            "unknown".to_string()
        };
        let erc20_transfer_count_status = if summary_ok {
            summary
                .map(|row| row.erc20_transfer_count.to_string())
                .unwrap_or_else(|| "0".to_string())
        } else {
            "unknown".to_string()
        };

        rows.push(TxExecutionPathReconstructedRow {
            run_tag: run_tag.to_string(),
            transaction_hash: hash,
            path_label: label,
            tx_path_source,
            tx_path_confidence,
            tx_body_request_status: body
                .map(|row| row.request_status.clone())
                .unwrap_or_else(|| "missing".to_string()),
            receipt_request_status: summary
                .map(|row| row.request_status.clone())
                .unwrap_or_else(|| "missing".to_string()),
            method_selector,
            router_to_address: router_to,
            pool_sequence: pool_sequence.join("|"),
            pool_count,
            swap_count,
            mon_usdc_quote_notional: quote_notional,
            external_non_pool_logs_status,
            erc20_transfer_count_status,
            input_len: body.map(|row| row.input_len).unwrap_or(0),
            gas: body.and_then(|row| row.gas),
            max_priority_fee_per_gas: body.and_then(|row| row.max_priority_fee_per_gas),
        });
    }
    rows
}

fn classify_tx_path(
    body: Option<&TxBodyRaw>,
    summary: Option<&ReceiptSummaryRaw>,
    router_to: &str,
    method_selector: &str,
    pool_count: u64,
    swap_count: u64,
    events: &[&EventRecord],
) -> String {
    if body.map_or(true, |row| row.request_status != "ok")
        || summary.map_or(true, |row| row.request_status != "ok")
    {
        return "trace_required".to_string();
    }
    let pools = known_pool_set();
    let directions = events
        .iter()
        .map(|event| event.direction_string())
        .collect::<BTreeSet<_>>();
    if pool_count > 1 && directions.len() > 1 {
        return "possible_arb_cycle".to_string();
    }
    if pool_count > 1 {
        return "multi_mon_usdc_pool".to_string();
    }
    if is_multicall_selector(method_selector) {
        return "aggregator_or_multicall".to_string();
    }
    if swap_count > 1 {
        return "router_multi_pool".to_string();
    }
    if swap_count == 1 && pools.contains(&router_to.to_ascii_lowercase()) {
        return "direct_pool_swap".to_string();
    }
    if swap_count == 1 {
        return "router_single_pool".to_string();
    }
    if summary.map_or(false, |row| row.erc20_transfer_count > 0) {
        return "transfer_only_or_unclassified".to_string();
    }
    "trace_required".to_string()
}

fn classify_tx_path_reconstructed(
    body: Option<&TxBodyRaw>,
    summary: Option<&ReceiptSummaryRaw>,
    router_to: &str,
    method_selector: &str,
    pool_count: u64,
    swap_count: u64,
    events: &[&EventRecord],
) -> String {
    let body_ok = body.is_some_and(|row| row.request_status == "ok");
    let summary_ok = summary.is_some_and(|row| row.request_status == "ok");
    if !body_ok && swap_count == 0 {
        return "trace_required".to_string();
    }
    let pools = known_pool_set();
    let directions = events
        .iter()
        .map(|event| event.direction_string())
        .collect::<BTreeSet<_>>();
    if pool_count > 1 && directions.len() > 1 {
        return "possible_arb_cycle".to_string();
    }
    if pool_count > 1 {
        return "multi_mon_usdc_pool".to_string();
    }
    if body_ok && is_multicall_selector(method_selector) {
        return "aggregator_or_multicall".to_string();
    }
    if swap_count > 1 {
        return "router_multi_pool".to_string();
    }
    if swap_count == 1 && body_ok && pools.contains(&router_to.to_ascii_lowercase()) {
        return "direct_pool_swap".to_string();
    }
    if swap_count == 1 {
        return "router_single_pool".to_string();
    }
    if summary_ok && summary.is_some_and(|row| row.erc20_transfer_count > 0) {
        return "transfer_only_or_unclassified".to_string();
    }
    "trace_required".to_string()
}

fn tx_path_source_confidence(
    body_ok: bool,
    summary_ok: bool,
    swap_count: u64,
    has_method_selector: bool,
) -> (String, String) {
    if body_ok && summary_ok {
        ("observed_rpc".to_string(), "high".to_string())
    } else if swap_count > 0 && body_ok {
        (
            "reconstructed_from_swap_logs".to_string(),
            "medium".to_string(),
        )
    } else if swap_count > 0 && has_method_selector {
        (
            "reconstructed_from_swap_logs".to_string(),
            "low".to_string(),
        )
    } else if swap_count > 0 {
        (
            "reconstructed_from_swap_logs".to_string(),
            "low".to_string(),
        )
    } else {
        ("unavailable".to_string(), "none".to_string())
    }
}

fn build_cross_pool_dislocation_features(
    clean_events: &[EventRecord],
) -> Result<Vec<CrossPoolDislocationRow>> {
    let panel = build_minute_pool_panel(clean_events);
    let mut rows = Vec::new();
    for event in clean_events {
        let minute = floor_to_minute(event.timestamp);
        let state = panel_state(&panel, minute, &event.pool_address);
        rows.push(CrossPoolDislocationRow {
            block_number: event.block_number,
            timestamp: event.timestamp,
            transaction_hash: event.transaction_hash.clone(),
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
            minute_utc: utc_string(minute)?,
            pool_price: state.pool_price,
            reference_price: state.reference_price,
            pool_dislocation_bps: state.pool_dislocation_bps,
            max_min_pool_spread_bps: state.max_min_pool_spread_bps,
            pool_freshness_age_minutes: state.pool_freshness_age_minutes,
            leader_1m_pool: leader_pool(&panel, minute, 1),
            leader_5m_pool: leader_pool(&panel, minute, 5),
            leader_15m_pool: leader_pool(&panel, minute, 15),
            convergence_5m_label: convergence_label(&panel, minute, &event.pool_address, 5),
            convergence_15m_label: convergence_label(&panel, minute, &event.pool_address, 15),
        });
    }
    Ok(rows)
}

#[derive(Default)]
struct MinutePoolAgg {
    base_volume: f64,
    quote_volume: f64,
    last_price: Option<f64>,
}

#[derive(Clone)]
struct PoolMinuteState {
    price: Option<f64>,
    last_seen_minute: i64,
    volume: f64,
}

#[derive(Default)]
struct DislocationState {
    pool_price: Option<f64>,
    reference_price: Option<f64>,
    pool_dislocation_bps: Option<f64>,
    max_min_pool_spread_bps: Option<f64>,
    pool_freshness_age_minutes: Option<u64>,
}

fn build_minute_pool_panel(
    clean_events: &[EventRecord],
) -> BTreeMap<i64, BTreeMap<String, PoolMinuteState>> {
    let mut aggs = BTreeMap::<(i64, String), MinutePoolAgg>::new();
    for event in clean_events {
        let key = (floor_to_minute(event.timestamp), event.pool_address.clone());
        let entry = aggs.entry(key).or_default();
        entry.base_volume += event.base_abs.unwrap_or(0.0);
        entry.quote_volume += event.quote_abs.unwrap_or(0.0);
        entry.last_price = event.price_quote_per_base;
    }
    let min_minute = clean_events
        .iter()
        .map(|event| floor_to_minute(event.timestamp))
        .min()
        .unwrap_or(0);
    let max_minute = clean_events
        .iter()
        .map(|event| floor_to_minute(event.timestamp))
        .max()
        .unwrap_or(0);
    let pools = clean_events
        .iter()
        .map(|event| event.pool_address.clone())
        .collect::<BTreeSet<_>>();
    let mut last = BTreeMap::<String, PoolMinuteState>::new();
    let mut panel = BTreeMap::new();
    let mut minute = min_minute;
    while minute <= max_minute {
        let mut row = BTreeMap::new();
        for pool in &pools {
            if let Some(agg) = aggs.remove(&(minute, pool.clone())) {
                let price = safe_div(agg.quote_volume, agg.base_volume).or(agg.last_price);
                let state = PoolMinuteState {
                    price,
                    last_seen_minute: minute,
                    volume: agg.quote_volume,
                };
                last.insert(pool.clone(), state.clone());
                row.insert(pool.clone(), state);
            } else if let Some(prev) = last.get(pool) {
                row.insert(pool.clone(), prev.clone());
            }
        }
        panel.insert(minute, row);
        minute += 60;
    }
    panel
}

fn panel_state(
    panel: &BTreeMap<i64, BTreeMap<String, PoolMinuteState>>,
    minute: i64,
    pool: &str,
) -> DislocationState {
    let Some(row) = panel.get(&minute) else {
        return DislocationState::default();
    };
    let mut weighted_sum = 0.0;
    let mut total_weight = 0.0;
    let mut prices = Vec::new();
    for state in row.values() {
        let age = ((minute - state.last_seen_minute) / 60).max(0);
        if age > 5 {
            continue;
        }
        if let Some(price) = state
            .price
            .filter(|value| value.is_finite() && *value > 0.0)
        {
            let weight = state.volume.max(1.0);
            weighted_sum += price * weight;
            total_weight += weight;
            prices.push(price);
        }
    }
    let reference_price = safe_div(weighted_sum, total_weight);
    let pool_state = row.get(pool);
    let pool_price = pool_state.and_then(|state| state.price);
    let pool_freshness_age_minutes =
        pool_state.map(|state| ((minute - state.last_seen_minute) / 60).max(0) as u64);
    let pool_dislocation_bps = match (pool_price, reference_price.filter(|value| *value > 0.0)) {
        (Some(pool_price), Some(reference)) => finite((pool_price / reference - 1.0) * 10_000.0),
        _ => None,
    };
    let max_min_pool_spread_bps = if prices.len() >= 2 {
        let min = prices.iter().copied().fold(f64::INFINITY, f64::min);
        let max = prices.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        finite((max / min - 1.0) * 10_000.0)
    } else {
        None
    };
    DislocationState {
        pool_price,
        reference_price,
        pool_dislocation_bps,
        max_min_pool_spread_bps,
        pool_freshness_age_minutes,
    }
}

fn leader_pool(
    panel: &BTreeMap<i64, BTreeMap<String, PoolMinuteState>>,
    minute: i64,
    lag_minutes: i64,
) -> String {
    let current = panel_state(panel, minute, "");
    let Some(reference) = current.reference_price else {
        return String::new();
    };
    let Some(prev) = panel.get(&(minute - lag_minutes * 60)) else {
        return String::new();
    };
    prev.iter()
        .filter_map(|(pool, state)| {
            state
                .price
                .map(|price| (pool.clone(), (price - reference).abs()))
        })
        .max_by(|a, b| a.1.total_cmp(&b.1))
        .map(|(pool, _)| pool)
        .unwrap_or_default()
}

fn convergence_label(
    panel: &BTreeMap<i64, BTreeMap<String, PoolMinuteState>>,
    minute: i64,
    pool: &str,
    horizon_minutes: i64,
) -> String {
    let current = panel_state(panel, minute, pool)
        .pool_dislocation_bps
        .map(f64::abs);
    let future = panel_state(panel, minute + horizon_minutes * 60, pool)
        .pool_dislocation_bps
        .map(f64::abs);
    match (current, future) {
        (Some(current), Some(future)) if future < current * 0.8 => "shrink".to_string(),
        (Some(current), Some(future)) if future > current * 1.2 => "expand".to_string(),
        (Some(_), Some(_)) => "flat".to_string(),
        _ => "insufficient_future_price".to_string(),
    }
}

fn build_pool_state_event_features(
    clean_events: &[EventRecord],
    state_rows: &[PoolStateRaw],
    window_rows: &[PoolWindowRaw],
) -> Vec<PoolStateEventFeatureRow> {
    let event_notional_by_key =
        clean_events
            .iter()
            .fold(BTreeMap::<(u64, String), f64>::new(), |mut map, event| {
                *map.entry((event.block_number, event.pool_address.clone()))
                    .or_default() += event.quote_abs.unwrap_or(0.0);
                map
            });
    let imbalance_by_key = build_window_imbalance(window_rows);
    state_rows
        .iter()
        .map(|state| {
            let event_quote_notional = event_notional_by_key
                .get(&(state.event_block_number, state.pool_address.clone()))
                .copied()
                .unwrap_or(0.0);
            let active_liquidity_or_reserve = if state.family == "lb_v22" {
                state.active_bin_reserve_y.clone()
            } else {
                state.liquidity.clone()
            };
            let liquidity_proxy = active_liquidity_or_reserve.parse::<f64>().ok();
            PoolStateEventFeatureRow {
                event_block_number: state.event_block_number,
                sample_block_number: state.sample_block_number,
                sample_side: state.sample_side.clone(),
                pool_address: state.pool_address.clone(),
                family: state.family.clone(),
                sampled: true,
                request_status: state.request_status.clone(),
                event_quote_notional,
                active_tick_or_bin: if state.family == "lb_v22" {
                    state.active_id.clone()
                } else {
                    state.tick.clone()
                },
                active_liquidity_or_reserve,
                event_notional_to_active_liquidity_proxy: safe_div(
                    event_quote_notional,
                    liquidity_proxy.unwrap_or(0.0),
                ),
                local_window_imbalance: imbalance_by_key
                    .get(&(
                        state.event_block_number,
                        state.sample_block_number,
                        state.pool_address.clone(),
                    ))
                    .copied()
                    .flatten(),
            }
        })
        .collect()
}

fn build_window_imbalance(rows: &[PoolWindowRaw]) -> BTreeMap<(u64, u64, String), Option<f64>> {
    let mut sums = BTreeMap::<(u64, u64, String), (f64, f64)>::new();
    for row in rows {
        let key = (
            row.event_block_number,
            row.sample_block_number,
            row.pool_address.clone(),
        );
        let entry = sums.entry(key).or_default();
        if row.window_kind == "lb_bin" {
            entry.0 += row.reserve_x.parse::<f64>().unwrap_or(0.0);
            entry.1 += row.reserve_y.parse::<f64>().unwrap_or(0.0);
        } else {
            let offset = row.offset.parse::<i64>().unwrap_or(0);
            let liq = row.liquidity_gross.parse::<f64>().unwrap_or(0.0);
            if offset < 0 {
                entry.0 += liq;
            } else if offset > 0 {
                entry.1 += liq;
            }
        }
    }
    sums.into_iter()
        .map(|(key, (left, right))| (key, safe_div(right - left, right + left)))
        .collect()
}

#[derive(Debug, Clone)]
struct PoolStateSnapshot {
    block_number: u64,
    timestamp: i64,
    source: String,
    confidence: String,
    sqrt_price_x96: String,
    tick_or_bin: String,
    liquidity_or_reserve: String,
}

fn build_pool_state_event_features_reconstructed(
    clean_events: &[EventRecord],
    swap_metadata: &[SwapMetadataRaw],
    state_rows: &[PoolStateRaw],
    window_rows: &[PoolWindowRaw],
    run_tag: &str,
) -> Vec<PoolStateEventFeatureReconstructedRow> {
    let metadata_by_key = swap_metadata
        .iter()
        .map(|row| {
            (
                (
                    row.block_number,
                    row.transaction_hash.clone(),
                    row.log_index,
                    row.pool_address.clone(),
                ),
                row,
            )
        })
        .collect::<HashMap<_, _>>();
    let sampled_by_key = best_pool_state_by_key(state_rows);
    let imbalance_by_key = build_window_imbalance(window_rows);
    let mut last_by_pool = BTreeMap::<String, PoolStateSnapshot>::new();
    let mut rows = Vec::with_capacity(clean_events.len());

    for event in clean_events {
        let key = (
            event.block_number,
            event.transaction_hash.clone(),
            event.log_index,
            event.pool_address.clone(),
        );
        let metadata = metadata_by_key.get(&key).copied();
        let sampled_event = sampled_by_key.get(&(
            event.block_number,
            event.pool_address.clone(),
            "event".to_string(),
        ));
        let sampled_pre = sampled_by_key.get(&(
            event.block_number,
            event.pool_address.clone(),
            "pre".to_string(),
        ));
        let event_snapshot = sampled_event
            .and_then(|state| observed_pool_state_snapshot(state, event.timestamp))
            .or_else(|| metadata.and_then(|row| reconstructed_pool_state_snapshot(event, row)));
        let pre_snapshot = sampled_pre
            .and_then(|state| observed_pool_state_snapshot(state, event.timestamp))
            .or_else(|| {
                last_by_pool
                    .get(&event.pool_address)
                    .cloned()
                    .map(|mut snapshot| {
                        snapshot.source = "carry_forward_swap_state".to_string();
                        snapshot.confidence = carry_forward_confidence(
                            event.block_number.saturating_sub(snapshot.block_number),
                            event.timestamp.saturating_sub(snapshot.timestamp),
                        );
                        snapshot
                    })
            });

        let event_request_status = sampled_event
            .map(|state| state.request_status.clone())
            .unwrap_or_else(|| "not_sampled".to_string());
        let pre_request_status = sampled_pre
            .map(|state| state.request_status.clone())
            .unwrap_or_else(|| "not_sampled".to_string());
        let pre_age_blocks = pre_snapshot
            .as_ref()
            .map(|snapshot| event.block_number.saturating_sub(snapshot.block_number));
        let pre_age_minutes = pre_snapshot.as_ref().and_then(|snapshot| {
            let seconds = event.timestamp.saturating_sub(snapshot.timestamp);
            (seconds >= 0).then_some((seconds as u64) / 60)
        });
        let event_liquidity_proxy = event_snapshot
            .as_ref()
            .and_then(|snapshot| snapshot.liquidity_or_reserve.parse::<f64>().ok());
        let event_notional_to_active_liquidity_proxy =
            event_snapshot.as_ref().and_then(|snapshot| {
                if event.family == "lb_v22" && snapshot.source != "observed_rpc" {
                    None
                } else {
                    safe_div(
                        event.quote_abs.unwrap_or(0.0),
                        event_liquidity_proxy.unwrap_or(0.0),
                    )
                }
            });
        let event_local_window_imbalance = sampled_event.and_then(|state| {
            imbalance_by_key
                .get(&(
                    state.event_block_number,
                    state.sample_block_number,
                    state.pool_address.clone(),
                ))
                .copied()
                .flatten()
        });
        let pre_local_window_imbalance = sampled_pre.and_then(|state| {
            imbalance_by_key
                .get(&(
                    state.event_block_number,
                    state.sample_block_number,
                    state.pool_address.clone(),
                ))
                .copied()
                .flatten()
        });
        let usable_for_research = event_snapshot
            .as_ref()
            .is_some_and(|snapshot| snapshot.source != "unavailable");

        rows.push(PoolStateEventFeatureReconstructedRow {
            run_tag: run_tag.to_string(),
            block_number: event.block_number,
            transaction_hash: event.transaction_hash.clone(),
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
            family: event.family.clone(),
            direction: event.direction_string(),
            quote_abs: event.quote_abs.unwrap_or(0.0),
            event_request_status,
            pre_request_status,
            event_state_source: event_snapshot
                .as_ref()
                .map(|snapshot| snapshot.source.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            event_state_confidence: event_snapshot
                .as_ref()
                .map(|snapshot| snapshot.confidence.clone())
                .unwrap_or_else(|| "none".to_string()),
            pre_state_source: pre_snapshot
                .as_ref()
                .map(|snapshot| snapshot.source.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            pre_state_confidence: pre_snapshot
                .as_ref()
                .map(|snapshot| snapshot.confidence.clone())
                .unwrap_or_else(|| "none".to_string()),
            event_sqrt_price_x96: event_snapshot
                .as_ref()
                .map(|snapshot| snapshot.sqrt_price_x96.clone())
                .unwrap_or_default(),
            event_tick_or_bin: event_snapshot
                .as_ref()
                .map(|snapshot| snapshot.tick_or_bin.clone())
                .unwrap_or_default(),
            event_liquidity_or_reserve: event_snapshot
                .as_ref()
                .map(|snapshot| snapshot.liquidity_or_reserve.clone())
                .unwrap_or_default(),
            pre_sqrt_price_x96: pre_snapshot
                .as_ref()
                .map(|snapshot| snapshot.sqrt_price_x96.clone())
                .unwrap_or_default(),
            pre_tick_or_bin: pre_snapshot
                .as_ref()
                .map(|snapshot| snapshot.tick_or_bin.clone())
                .unwrap_or_default(),
            pre_liquidity_or_reserve: pre_snapshot
                .as_ref()
                .map(|snapshot| snapshot.liquidity_or_reserve.clone())
                .unwrap_or_default(),
            pre_state_age_blocks: pre_age_blocks,
            pre_state_age_minutes: pre_age_minutes,
            event_notional_to_active_liquidity_proxy,
            event_local_window_imbalance,
            pre_local_window_imbalance,
            usable_for_research,
        });

        if let Some(snapshot) = event_snapshot {
            last_by_pool.insert(event.pool_address.clone(), snapshot);
        }
    }
    rows
}

fn best_pool_state_by_key(
    state_rows: &[PoolStateRaw],
) -> BTreeMap<(u64, String, String), &PoolStateRaw> {
    let mut by_key = BTreeMap::<(u64, String, String), &PoolStateRaw>::new();
    for state in state_rows {
        let key = (
            state.event_block_number,
            state.pool_address.clone(),
            state.sample_side.clone(),
        );
        by_key
            .entry(key)
            .and_modify(|current| {
                if current.request_status != "ok" && state.request_status == "ok" {
                    *current = state;
                }
            })
            .or_insert(state);
    }
    by_key
}

fn observed_pool_state_snapshot(
    state: &PoolStateRaw,
    fallback_timestamp: i64,
) -> Option<PoolStateSnapshot> {
    if state.request_status != "ok" {
        return None;
    }
    let (tick_or_bin, liquidity_or_reserve) = if state.family == "lb_v22" {
        (state.active_id.clone(), state.active_bin_reserve_y.clone())
    } else {
        (state.tick.clone(), state.liquidity.clone())
    };
    Some(PoolStateSnapshot {
        block_number: state.sample_block_number,
        timestamp: fallback_timestamp,
        source: "observed_rpc".to_string(),
        confidence: "high".to_string(),
        sqrt_price_x96: state.sqrt_price_x96.clone(),
        tick_or_bin,
        liquidity_or_reserve,
    })
}

fn reconstructed_pool_state_snapshot(
    event: &EventRecord,
    metadata: &SwapMetadataRaw,
) -> Option<PoolStateSnapshot> {
    if event.family == "lb_v22" {
        if metadata.tick.is_empty() {
            return None;
        }
        return Some(PoolStateSnapshot {
            block_number: event.block_number,
            timestamp: event.timestamp,
            source: "reconstructed_from_swap_logs".to_string(),
            confidence: "medium".to_string(),
            sqrt_price_x96: String::new(),
            tick_or_bin: metadata.tick.clone(),
            liquidity_or_reserve: String::new(),
        });
    }
    if metadata.tick.is_empty() && metadata.sqrt_price_x96.is_empty() {
        return None;
    }
    Some(PoolStateSnapshot {
        block_number: event.block_number,
        timestamp: event.timestamp,
        source: "reconstructed_from_swap_logs".to_string(),
        confidence: "medium".to_string(),
        sqrt_price_x96: metadata.sqrt_price_x96.clone(),
        tick_or_bin: metadata.tick.clone(),
        liquidity_or_reserve: metadata.liquidity_raw.clone(),
    })
}

fn carry_forward_confidence(age_blocks: u64, age_seconds: i64) -> String {
    if age_blocks <= 750 && age_seconds <= 300 {
        "medium".to_string()
    } else {
        "low".to_string()
    }
}

fn build_debug_trace_labels(
    summaries: &[TraceSummaryRaw],
    calls: &[TraceCallRaw],
) -> Vec<DebugTraceLabelRow> {
    let pool_set = known_pool_set();
    let token_set = [
        mon_usdc_collectors::MON_TOKEN.to_ascii_lowercase(),
        mon_usdc_collectors::USDC_TOKEN.to_ascii_lowercase(),
    ]
    .into_iter()
    .collect::<BTreeSet<_>>();
    let mut calls_by_tx = BTreeMap::<String, Vec<&TraceCallRaw>>::new();
    for call in calls {
        calls_by_tx
            .entry(call.transaction_hash.clone())
            .or_default()
            .push(call);
    }
    summaries
        .iter()
        .map(|summary| {
            let calls = calls_by_tx
                .get(&summary.transaction_hash)
                .cloned()
                .unwrap_or_default();
            let pool_calls = calls
                .iter()
                .filter(|call| pool_set.contains(&call.to_address))
                .count() as u64;
            let token_calls = calls
                .iter()
                .filter(|call| token_set.contains(&call.to_address))
                .count() as u64;
            let reverts = calls.iter().filter(|call| !call.error.is_empty()).count() as u64;
            let router_calls = calls
                .iter()
                .filter(|call| {
                    !pool_set.contains(&call.to_address) && !token_set.contains(&call.to_address)
                })
                .count() as u64;
            let trace_path_class = if summary.request_status != "ok" {
                "trace_failed"
            } else if reverts > 0 {
                "reverting_path"
            } else if pool_calls > 1 {
                "multi_pool_trace"
            } else if pool_calls == 1 {
                "single_pool_trace"
            } else {
                "non_pool_trace"
            };
            DebugTraceLabelRow {
                transaction_hash: summary.transaction_hash.clone(),
                sampled: true,
                request_status: summary.request_status.clone(),
                call_graph_depth: summary.max_depth,
                call_count: summary.call_count,
                router_calls,
                pool_calls,
                token_calls,
                reverts,
                internal_value_transfers: 0,
                trace_path_class: trace_path_class.to_string(),
            }
        })
        .collect()
}

fn build_trace_proxy_labels(
    tx_path_rows: &[TxExecutionPathReconstructedRow],
    trace_label_rows: &[DebugTraceLabelRow],
) -> Vec<TraceProxyLabelRow> {
    let traces = trace_label_rows
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();
    tx_path_rows
        .iter()
        .map(|tx| {
            if let Some(trace) = traces.get(&tx.transaction_hash) {
                if trace.request_status == "ok" {
                    return TraceProxyLabelRow {
                        transaction_hash: tx.transaction_hash.clone(),
                        trace_path_class: trace.trace_path_class.clone(),
                        trace_source: "observed_rpc".to_string(),
                        trace_confidence: "high".to_string(),
                        trace_request_status: trace.request_status.clone(),
                        call_graph_depth: Some(trace.call_graph_depth),
                        call_count: Some(trace.call_count),
                    };
                }
                return TraceProxyLabelRow {
                    transaction_hash: tx.transaction_hash.clone(),
                    trace_path_class: proxy_trace_class_from_tx_path(&tx.path_label),
                    trace_source: "proxy_from_tx_path".to_string(),
                    trace_confidence: "low".to_string(),
                    trace_request_status: trace.request_status.clone(),
                    call_graph_depth: None,
                    call_count: None,
                };
            }
            TraceProxyLabelRow {
                transaction_hash: tx.transaction_hash.clone(),
                trace_path_class: "not_sampled".to_string(),
                trace_source: "unavailable".to_string(),
                trace_confidence: "none".to_string(),
                trace_request_status: "not_sampled".to_string(),
                call_graph_depth: None,
                call_count: None,
            }
        })
        .collect()
}

fn proxy_trace_class_from_tx_path(path_label: &str) -> String {
    match path_label {
        "possible_arb_cycle" => "arb_cycle_proxy",
        "multi_mon_usdc_pool" | "router_multi_pool" => "multi_pool_proxy",
        "direct_pool_swap" | "router_single_pool" => "single_pool_proxy",
        "aggregator_or_multicall" => "aggregator_or_multicall_proxy",
        "transfer_only_or_unclassified" => "transfer_or_unclassified_proxy",
        _ => "trace_required",
    }
    .to_string()
}

fn build_event_execution_features(
    clean_events: &[EventRecord],
    price_path_rows: &[EventPricePathLabelRow],
    dislocation_rows: &[CrossPoolDislocationRow],
    tx_path_rows: &[TxExecutionPathReconstructedRow],
    pool_state_rows: &[PoolStateEventFeatureReconstructedRow],
    trace_proxy_rows: &[TraceProxyLabelRow],
    run_tag: &str,
) -> Vec<EventExecutionFeatureRow> {
    let price_by_key = price_path_rows
        .iter()
        .map(|row| {
            (
                (
                    row.block_number,
                    row.transaction_hash.clone(),
                    row.log_index,
                    row.pool_address.clone(),
                ),
                row,
            )
        })
        .collect::<HashMap<_, _>>();
    let dislocation_by_key = dislocation_rows
        .iter()
        .map(|row| {
            (
                (
                    row.block_number,
                    row.transaction_hash.clone(),
                    row.log_index,
                    row.pool_address.clone(),
                ),
                row,
            )
        })
        .collect::<HashMap<_, _>>();
    let tx_by_hash = tx_path_rows
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();
    let pool_state_by_key = pool_state_rows
        .iter()
        .map(|row| {
            (
                (
                    row.block_number,
                    row.transaction_hash.clone(),
                    row.log_index,
                    row.pool_address.clone(),
                ),
                row,
            )
        })
        .collect::<HashMap<_, _>>();
    let trace_by_hash = trace_proxy_rows
        .iter()
        .map(|row| (row.transaction_hash.clone(), row))
        .collect::<HashMap<_, _>>();

    let mut rows = Vec::with_capacity(clean_events.len());
    for event in clean_events {
        let key = (
            event.block_number,
            event.transaction_hash.clone(),
            event.log_index,
            event.pool_address.clone(),
        );
        let price = price_by_key.get(&key).copied();
        let dislocation = dislocation_by_key.get(&key).copied();
        let tx = tx_by_hash.get(&event.transaction_hash).copied();
        let pool_state = pool_state_by_key.get(&key).copied();
        let trace = trace_by_hash.get(&event.transaction_hash).copied();
        let quality_tier = event_quality_tier(tx, pool_state, trace);
        let usable_for_execution_research = quality_tier != "C_price_only";

        rows.push(EventExecutionFeatureRow {
            run_tag: run_tag.to_string(),
            block_number: event.block_number,
            event_time_utc: event.block_datetime_utc.clone(),
            transaction_hash: event.transaction_hash.clone(),
            transaction_index: event.transaction_index,
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
            dex_id: event.dex_id.clone(),
            family: event.family.clone(),
            direction: event.direction_string(),
            base_abs: event.base_abs,
            quote_abs: event.quote_abs,
            price_quote_per_base: event.price_quote_per_base,
            receipt_request_status: event.receipt_request_status.clone(),
            receipt_status: event.receipt_status,
            receipt_gas_used: event.receipt_gas_used,
            effective_gas_price: event.effective_gas_price,
            base_fee_per_gas: event.base_fee_per_gas,
            same_block_event_count: event.same_block_event_count,
            price_path_label: price
                .map(|row| row.label.clone())
                .unwrap_or_else(|| "missing_price_path".to_string()),
            fwd_return_5m: price.and_then(|row| row.fwd_return_5m),
            fwd_return_15m: price.and_then(|row| row.fwd_return_15m),
            fwd_return_1h: price.and_then(|row| row.fwd_return_1h),
            fwd_return_3h: price.and_then(|row| row.fwd_return_3h),
            fwd_return_6h: price.and_then(|row| row.fwd_return_6h),
            pool_dislocation_bps: dislocation.and_then(|row| row.pool_dislocation_bps),
            max_min_pool_spread_bps: dislocation.and_then(|row| row.max_min_pool_spread_bps),
            convergence_15m_label: dislocation
                .map(|row| row.convergence_15m_label.clone())
                .unwrap_or_else(|| "missing_dislocation".to_string()),
            tx_path_label: tx
                .map(|row| row.path_label.clone())
                .unwrap_or_else(|| "trace_required".to_string()),
            tx_path_source: tx
                .map(|row| row.tx_path_source.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            tx_path_confidence: tx
                .map(|row| row.tx_path_confidence.clone())
                .unwrap_or_else(|| "none".to_string()),
            pool_event_state_source: pool_state
                .map(|row| row.event_state_source.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            pool_event_state_confidence: pool_state
                .map(|row| row.event_state_confidence.clone())
                .unwrap_or_else(|| "none".to_string()),
            pool_pre_state_source: pool_state
                .map(|row| row.pre_state_source.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            pool_pre_state_confidence: pool_state
                .map(|row| row.pre_state_confidence.clone())
                .unwrap_or_else(|| "none".to_string()),
            pool_pre_state_age_blocks: pool_state.and_then(|row| row.pre_state_age_blocks),
            trace_path_class: trace
                .map(|row| row.trace_path_class.clone())
                .unwrap_or_else(|| "not_sampled".to_string()),
            trace_source: trace
                .map(|row| row.trace_source.clone())
                .unwrap_or_else(|| "unavailable".to_string()),
            trace_confidence: trace
                .map(|row| row.trace_confidence.clone())
                .unwrap_or_else(|| "none".to_string()),
            trace_call_graph_depth: trace.and_then(|row| row.call_graph_depth),
            trace_call_count: trace.and_then(|row| row.call_count),
            quality_tier,
            usable_for_execution_research,
        });
    }
    rows
}

fn event_quality_tier(
    tx: Option<&TxExecutionPathReconstructedRow>,
    pool_state: Option<&PoolStateEventFeatureReconstructedRow>,
    trace: Option<&TraceProxyLabelRow>,
) -> String {
    let tx_source = tx
        .map(|row| row.tx_path_source.as_str())
        .unwrap_or("unavailable");
    let event_state_source = pool_state
        .map(|row| row.event_state_source.as_str())
        .unwrap_or("unavailable");
    let pre_state_source = pool_state
        .map(|row| row.pre_state_source.as_str())
        .unwrap_or("unavailable");
    if tx_source == "unavailable" || event_state_source == "unavailable" {
        return "C_price_only".to_string();
    }
    let trace_is_observed_or_not_sampled = trace.map_or(true, |row| {
        row.trace_source == "observed_rpc" || row.trace_request_status == "not_sampled"
    });
    if tx_source == "observed_rpc"
        && event_state_source == "observed_rpc"
        && (pre_state_source == "observed_rpc" || pre_state_source == "unavailable")
        && trace_is_observed_or_not_sampled
    {
        "A_observed".to_string()
    } else {
        "B_reconstructed".to_string()
    }
}

fn build_enrichment_coverage(
    base: &CoverageSummary,
    tx_bodies: &[TxBodyRaw],
    receipt_summaries: &[ReceiptSummaryRaw],
    receipt_logs: &[ReceiptLogRaw],
    price_path_rows: &[EventPricePathLabelRow],
    tx_path_rows: &[TxExecutionPathLabelRow],
    dislocation_rows: &[CrossPoolDislocationRow],
    pool_state_rows: &[PoolStateEventFeatureRow],
    trace_label_rows: &[DebugTraceLabelRow],
    tx_path_reconstructed_rows: &[TxExecutionPathReconstructedRow],
    pool_state_reconstructed_rows: &[PoolStateEventFeatureReconstructedRow],
    trace_proxy_rows: &[TraceProxyLabelRow],
    event_execution_rows: &[EventExecutionFeatureRow],
) -> EnrichmentCoverage {
    let expected = base.unique_swap_txs;
    let tx_body_errors = tx_bodies
        .iter()
        .filter(|row| row.request_status != "ok")
        .count() as u64;
    let receipt_errors = receipt_summaries
        .iter()
        .filter(|row| row.request_status != "ok")
        .count() as u64;
    let pool_state_failures = failure_reasons(pool_state_rows.iter().filter_map(|row| {
        if row.request_status == "ok" {
            None
        } else {
            Some(row.request_status.clone())
        }
    }));
    let trace_failures = failure_reasons(trace_label_rows.iter().filter_map(|row| {
        if row.request_status == "ok" {
            None
        } else {
            Some(row.request_status.clone())
        }
    }));
    EnrichmentCoverage {
        tx_body: TxBodyCoverage {
            expected_txs: expected,
            written_txs: tx_bodies.len() as u64,
            missing_txs: expected.saturating_sub(tx_bodies.len() as u64),
            request_errors: tx_body_errors,
        },
        receipt_log_bundle: ReceiptLogBundleCoverage {
            expected_txs: expected,
            summary_rows: receipt_summaries.len() as u64,
            log_rows: receipt_logs.len() as u64,
            missing_txs: expected.saturating_sub(receipt_summaries.len() as u64),
            request_errors: receipt_errors,
        },
        derived_full: DerivedFullCoverage {
            event_price_path_rows: price_path_rows.len() as u64,
            tx_path_label_rows: tx_path_rows.len() as u64,
            cross_pool_rows: dislocation_rows.len() as u64,
        },
        sampled: SampledCoverage {
            pool_state_candidate_count: pool_state_rows.len() as u64,
            pool_state_sampled_count: pool_state_rows.len() as u64,
            pool_state_success_count: pool_state_rows
                .iter()
                .filter(|row| row.request_status == "ok")
                .count() as u64,
            pool_state_failed_count: pool_state_rows
                .iter()
                .filter(|row| row.request_status != "ok")
                .count() as u64,
            pool_state_failure_reasons: pool_state_failures,
            trace_candidate_count: trace_label_rows.len() as u64,
            trace_sampled_count: trace_label_rows.len() as u64,
            trace_success_count: trace_label_rows
                .iter()
                .filter(|row| row.request_status == "ok")
                .count() as u64,
            trace_failed_count: trace_label_rows
                .iter()
                .filter(|row| row.request_status != "ok")
                .count() as u64,
            trace_failure_reasons: trace_failures,
        },
        reconstruction: ReconstructionCoverage {
            tx_path: source_confidence_coverage(
                tx_path_reconstructed_rows
                    .iter()
                    .map(|row| (row.tx_path_source.clone(), row.tx_path_confidence.clone())),
            ),
            pool_event_state: source_confidence_coverage(pool_state_reconstructed_rows.iter().map(
                |row| {
                    (
                        row.event_state_source.clone(),
                        row.event_state_confidence.clone(),
                    )
                },
            )),
            pool_pre_state: source_confidence_coverage(pool_state_reconstructed_rows.iter().map(
                |row| {
                    (
                        row.pre_state_source.clone(),
                        row.pre_state_confidence.clone(),
                    )
                },
            )),
            trace_proxy: source_confidence_coverage(
                trace_proxy_rows
                    .iter()
                    .map(|row| (row.trace_source.clone(), row.trace_confidence.clone())),
            ),
            event_panel: EventPanelCoverage {
                rows: event_execution_rows.len() as u64,
                usable_for_execution_research: event_execution_rows
                    .iter()
                    .filter(|row| row.usable_for_execution_research)
                    .count() as u64,
                quality_tier_counts: label_summary(
                    event_execution_rows
                        .iter()
                        .map(|row| row.quality_tier.clone())
                        .collect(),
                ),
            },
        },
    }
}

fn source_confidence_coverage<I>(values: I) -> SourceConfidenceCoverage
where
    I: Iterator<Item = (String, String)>,
{
    let mut counts = BTreeMap::<(String, String), u64>::new();
    let mut total = 0_u64;
    for (source, confidence) in values {
        total += 1;
        *counts.entry((source, confidence)).or_default() += 1;
    }
    SourceConfidenceCoverage {
        rows: total,
        by_source_confidence: counts
            .into_iter()
            .map(|((source, confidence), rows)| SourceConfidenceSummaryRow {
                source,
                confidence,
                rows,
            })
            .collect(),
    }
}

fn failure_reasons<I: Iterator<Item = String>>(values: I) -> Vec<FailureReasonRow> {
    let mut counts = BTreeMap::<String, u64>::new();
    for value in values {
        *counts.entry(value).or_default() += 1;
    }
    counts
        .into_iter()
        .map(|(reason, rows)| FailureReasonRow {
            retryable: reason.contains("rpc") || reason.contains("missing"),
            reason,
            rows,
        })
        .collect()
}

fn coverage_csv_rows(coverage: &EnrichmentCoverage) -> Vec<CoverageCsvRow> {
    vec![
        csv_metric("tx_body", "expected_txs", coverage.tx_body.expected_txs),
        csv_metric("tx_body", "written_txs", coverage.tx_body.written_txs),
        csv_metric("tx_body", "missing_txs", coverage.tx_body.missing_txs),
        csv_metric("tx_body", "request_errors", coverage.tx_body.request_errors),
        csv_metric(
            "receipt_log_bundle",
            "expected_txs",
            coverage.receipt_log_bundle.expected_txs,
        ),
        csv_metric(
            "receipt_log_bundle",
            "summary_rows",
            coverage.receipt_log_bundle.summary_rows,
        ),
        csv_metric(
            "receipt_log_bundle",
            "log_rows",
            coverage.receipt_log_bundle.log_rows,
        ),
        csv_metric(
            "receipt_log_bundle",
            "missing_txs",
            coverage.receipt_log_bundle.missing_txs,
        ),
        csv_metric(
            "receipt_log_bundle",
            "request_errors",
            coverage.receipt_log_bundle.request_errors,
        ),
        csv_metric(
            "derived_full",
            "event_price_path_rows",
            coverage.derived_full.event_price_path_rows,
        ),
        csv_metric(
            "derived_full",
            "tx_path_label_rows",
            coverage.derived_full.tx_path_label_rows,
        ),
        csv_metric(
            "derived_full",
            "cross_pool_rows",
            coverage.derived_full.cross_pool_rows,
        ),
        csv_metric(
            "sampled",
            "pool_state_sampled_count",
            coverage.sampled.pool_state_sampled_count,
        ),
        csv_metric(
            "sampled",
            "trace_sampled_count",
            coverage.sampled.trace_sampled_count,
        ),
        csv_metric(
            "reconstruction",
            "event_panel_rows",
            coverage.reconstruction.event_panel.rows,
        ),
        csv_metric(
            "reconstruction",
            "event_panel_usable_for_execution_research",
            coverage
                .reconstruction
                .event_panel
                .usable_for_execution_research,
        ),
    ]
}

fn csv_metric(scope: &str, metric: &str, value: u64) -> CoverageCsvRow {
    CoverageCsvRow {
        scope: scope.to_string(),
        metric: metric.to_string(),
        value: value.to_string(),
    }
}

fn label_summary(labels: Vec<String>) -> Vec<LabelSummaryRow> {
    let mut counts = BTreeMap::<String, u64>::new();
    for label in labels {
        *counts.entry(label).or_default() += 1;
    }
    counts
        .into_iter()
        .map(|(label, rows)| LabelSummaryRow { label, rows })
        .collect()
}

fn reconstruction_summary_rows(
    tx_path_rows: &[TxExecutionPathReconstructedRow],
    pool_state_rows: &[PoolStateEventFeatureReconstructedRow],
    trace_proxy_rows: &[TraceProxyLabelRow],
) -> Vec<ReconstructionSummaryCsvRow> {
    let mut rows = Vec::new();
    rows.extend(reconstruction_component_summary(
        "tx_path",
        tx_path_rows
            .iter()
            .map(|row| (row.tx_path_source.clone(), row.tx_path_confidence.clone())),
    ));
    rows.extend(reconstruction_component_summary(
        "pool_event_state",
        pool_state_rows.iter().map(|row| {
            (
                row.event_state_source.clone(),
                row.event_state_confidence.clone(),
            )
        }),
    ));
    rows.extend(reconstruction_component_summary(
        "pool_pre_state",
        pool_state_rows.iter().map(|row| {
            (
                row.pre_state_source.clone(),
                row.pre_state_confidence.clone(),
            )
        }),
    ));
    rows.extend(reconstruction_component_summary(
        "trace_proxy",
        trace_proxy_rows
            .iter()
            .map(|row| (row.trace_source.clone(), row.trace_confidence.clone())),
    ));
    rows
}

fn reconstruction_component_summary<I>(
    component: &str,
    values: I,
) -> Vec<ReconstructionSummaryCsvRow>
where
    I: Iterator<Item = (String, String)>,
{
    let mut counts = BTreeMap::<(String, String), u64>::new();
    for (source, confidence) in values {
        *counts.entry((source, confidence)).or_default() += 1;
    }
    counts
        .into_iter()
        .map(|((source, confidence), rows)| ReconstructionSummaryCsvRow {
            component: component.to_string(),
            source,
            confidence,
            rows,
        })
        .collect()
}

fn execution_panel_summary_rows(
    rows: &[EventExecutionFeatureRow],
) -> Vec<ExecutionPanelSummaryCsvRow> {
    let mut out = Vec::new();
    out.extend(panel_summary_scope(
        rows.iter()
            .map(|row| (row.quality_tier.clone(), row.quality_tier.clone())),
        "quality_tier",
    ));
    out.extend(panel_summary_scope(
        rows.iter()
            .map(|row| (row.quality_tier.clone(), row.tx_path_label.clone())),
        "tx_path_label",
    ));
    out.extend(panel_summary_scope(
        rows.iter()
            .map(|row| (row.quality_tier.clone(), row.price_path_label.clone())),
        "price_path_label",
    ));
    out.extend(panel_summary_scope(
        rows.iter()
            .map(|row| (row.quality_tier.clone(), row.trace_path_class.clone())),
        "trace_path_class",
    ));
    out
}

fn panel_summary_scope<I>(values: I, scope: &str) -> Vec<ExecutionPanelSummaryCsvRow>
where
    I: Iterator<Item = (String, String)>,
{
    let mut counts = BTreeMap::<(String, String), u64>::new();
    for (quality_tier, label) in values {
        *counts.entry((quality_tier, label)).or_default() += 1;
    }
    counts
        .into_iter()
        .map(
            |((quality_tier, label), rows)| ExecutionPanelSummaryCsvRow {
                scope: scope.to_string(),
                quality_tier,
                label,
                rows,
            },
        )
        .collect()
}

fn known_pool_set() -> BTreeSet<String> {
    known_top4_pools()
        .into_iter()
        .map(|pool| pool.pair_address.to_ascii_lowercase())
        .collect()
}

fn is_multicall_selector(selector: &str) -> bool {
    matches!(
        selector,
        "0x5ae401dc" | "0xac9650d8" | "0x1cff79cd" | "0x252dba42"
    )
}

trait EventDirectionExt {
    fn direction_string(&self) -> String;
}

impl EventDirectionExt for EventRecord {
    fn direction_string(&self) -> String {
        if self.is_buy_base {
            "buy_base".to_string()
        } else if self.is_sell_base {
            "sell_base".to_string()
        } else {
            "unknown".to_string()
        }
    }
}

fn optional_dataset_files(data_root: &Path, dataset: &str) -> Result<Vec<PathBuf>> {
    parquet_files_under(&data_root.join(RAW_DIR).join(dataset))
}

fn read_tx_bodies(data_root: &Path) -> Result<Vec<TxBodyRaw>> {
    let files = optional_dataset_files(data_root, TX_BODIES_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let fetched_at_utc = string_column(batch, "fetched_at_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let request_status = string_column(batch, "request_status")?;
        let error = string_column(batch, "error")?;
        let to_address = string_column(batch, "to_address")?;
        let method_selector = string_column(batch, "method_selector")?;
        let input_len = u64_column(batch, "input_len")?;
        let gas = u64_column(batch, "gas")?;
        let max_priority_fee_per_gas = u64_column(batch, "max_priority_fee_per_gas")?;
        for index in 0..batch.num_rows() {
            rows.push(TxBodyRaw {
                fetched_at_utc: string_value(fetched_at_utc, index),
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                request_status: string_value(request_status, index),
                error: string_value(error, index),
                to_address: string_value(to_address, index).to_ascii_lowercase(),
                method_selector: string_value(method_selector, index),
                input_len: u64_value(input_len, index),
                gas: u64_option(gas, index),
                max_priority_fee_per_gas: u64_option(max_priority_fee_per_gas, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_receipt_summaries(data_root: &Path) -> Result<Vec<ReceiptSummaryRaw>> {
    let files = optional_dataset_files(data_root, TX_RECEIPT_LOG_SUMMARIES_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let fetched_at_utc = string_column(batch, "fetched_at_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let request_status = string_column(batch, "request_status")?;
        let error = string_column(batch, "error")?;
        let logs_count = u64_column(batch, "logs_count")?;
        let mon_usdc_swap_log_count = u64_column(batch, "mon_usdc_swap_log_count")?;
        let erc20_transfer_count = u64_column(batch, "erc20_transfer_count")?;
        let pool_addresses_seen = string_column(batch, "pool_addresses_seen")?;
        for index in 0..batch.num_rows() {
            rows.push(ReceiptSummaryRaw {
                fetched_at_utc: string_value(fetched_at_utc, index),
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                request_status: string_value(request_status, index),
                error: string_value(error, index),
                logs_count: u64_value(logs_count, index),
                mon_usdc_swap_log_count: u64_value(mon_usdc_swap_log_count, index),
                erc20_transfer_count: u64_value(erc20_transfer_count, index),
                pool_addresses_seen: string_value(pool_addresses_seen, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_receipt_logs(data_root: &Path) -> Result<Vec<ReceiptLogRaw>> {
    let files = optional_dataset_files(data_root, TX_RECEIPT_LOGS_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let log_index = u64_column(batch, "log_index")?;
        let address = string_column(batch, "address")?;
        let topic0 = string_column(batch, "topic0")?;
        for index in 0..batch.num_rows() {
            rows.push(ReceiptLogRaw {
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                log_index: u64_value(log_index, index),
                address: string_value(address, index).to_ascii_lowercase(),
                topic0: string_value(topic0, index).to_ascii_lowercase(),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_swap_metadata(data_root: &Path) -> Result<Vec<SwapMetadataRaw>> {
    let files = optional_dataset_files(data_root, POOL_SWAP_LOGS_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let block_number = u64_column(batch, "block_number")?;
        let block_timestamp = u64_column(batch, "block_timestamp")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let log_index = u64_column(batch, "log_index")?;
        let pool_address = string_column(batch, "pool_address")?;
        let family = string_column(batch, "family")?;
        let sqrt_price_x96 = string_column(batch, "sqrt_price_x96")?;
        let liquidity_raw = string_column(batch, "liquidity_raw")?;
        let tick = string_column(batch, "tick")?;
        for index in 0..batch.num_rows() {
            let timestamp = u64_value(block_timestamp, index) as i64;
            rows.push(SwapMetadataRaw {
                block_number: u64_value(block_number, index),
                timestamp,
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index).to_ascii_lowercase(),
                family: string_value(family, index),
                sqrt_price_x96: string_value(sqrt_price_x96, index),
                liquidity_raw: string_value(liquidity_raw, index),
                tick: string_value(tick, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_pool_state_samples(data_root: &Path) -> Result<Vec<PoolStateRaw>> {
    let files = optional_dataset_files(data_root, POOL_STATE_SAMPLES_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let event_block_number = u64_column(batch, "event_block_number")?;
        let sample_block_number = u64_column(batch, "sample_block_number")?;
        let sample_side = string_column(batch, "sample_side")?;
        let pool_address = string_column(batch, "pool_address")?;
        let family = string_column(batch, "family")?;
        let request_status = string_column(batch, "request_status")?;
        let error = string_column(batch, "error")?;
        let sqrt_price_x96 = string_column(batch, "sqrt_price_x96")?;
        let tick = string_column(batch, "tick")?;
        let liquidity = string_column(batch, "liquidity")?;
        let tick_spacing = string_column(batch, "tick_spacing")?;
        let active_id = string_column(batch, "active_id")?;
        let bin_step = string_column(batch, "bin_step")?;
        let active_bin_reserve_x = string_column(batch, "active_bin_reserve_x")?;
        let active_bin_reserve_y = string_column(batch, "active_bin_reserve_y")?;
        for index in 0..batch.num_rows() {
            rows.push(PoolStateRaw {
                event_block_number: u64_value(event_block_number, index),
                sample_block_number: u64_value(sample_block_number, index),
                sample_side: string_value(sample_side, index),
                pool_address: string_value(pool_address, index).to_ascii_lowercase(),
                family: string_value(family, index),
                request_status: string_value(request_status, index),
                error: string_value(error, index),
                sqrt_price_x96: string_value(sqrt_price_x96, index),
                tick: string_value(tick, index),
                liquidity: string_value(liquidity, index),
                tick_spacing: string_value(tick_spacing, index),
                active_id: string_value(active_id, index),
                bin_step: string_value(bin_step, index),
                active_bin_reserve_x: string_value(active_bin_reserve_x, index),
                active_bin_reserve_y: string_value(active_bin_reserve_y, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_pool_windows(data_root: &Path) -> Result<Vec<PoolWindowRaw>> {
    let files = optional_dataset_files(data_root, POOL_LIQUIDITY_WINDOWS_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let event_block_number = u64_column(batch, "event_block_number")?;
        let sample_block_number = u64_column(batch, "sample_block_number")?;
        let pool_address = string_column(batch, "pool_address")?;
        let window_kind = string_column(batch, "window_kind")?;
        let offset = string_column(batch, "offset")?;
        let liquidity_gross = string_column(batch, "liquidity_gross")?;
        let liquidity_net = string_column(batch, "liquidity_net")?;
        let reserve_x = string_column(batch, "reserve_x")?;
        let reserve_y = string_column(batch, "reserve_y")?;
        for index in 0..batch.num_rows() {
            rows.push(PoolWindowRaw {
                event_block_number: u64_value(event_block_number, index),
                sample_block_number: u64_value(sample_block_number, index),
                pool_address: string_value(pool_address, index).to_ascii_lowercase(),
                window_kind: string_value(window_kind, index),
                offset: string_value(offset, index),
                liquidity_gross: string_value(liquidity_gross, index),
                liquidity_net: string_value(liquidity_net, index),
                reserve_x: string_value(reserve_x, index),
                reserve_y: string_value(reserve_y, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_trace_summaries(data_root: &Path) -> Result<Vec<TraceSummaryRaw>> {
    let files = optional_dataset_files(data_root, DEBUG_TRACE_SUMMARIES_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let fetched_at_utc = string_column(batch, "fetched_at_utc")?;
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let request_status = string_column(batch, "request_status")?;
        let error = string_column(batch, "error")?;
        let call_count = u64_column(batch, "call_count")?;
        let max_depth = u64_column(batch, "max_depth")?;
        for index in 0..batch.num_rows() {
            rows.push(TraceSummaryRaw {
                fetched_at_utc: string_value(fetched_at_utc, index),
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                request_status: string_value(request_status, index),
                error: string_value(error, index),
                call_count: u64_value(call_count, index),
                max_depth: u64_value(max_depth, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_trace_calls(data_root: &Path) -> Result<Vec<TraceCallRaw>> {
    let files = optional_dataset_files(data_root, DEBUG_TRACE_CALLS_DATASET)?;
    let mut rows = Vec::new();
    read_optional_files(&files, |batch| {
        let transaction_hash = string_column(batch, "transaction_hash")?;
        let depth = u64_column(batch, "depth")?;
        let call_type = string_column(batch, "call_type")?;
        let from_address = string_column(batch, "from_address")?;
        let to_address = string_column(batch, "to_address")?;
        let input_selector = string_column(batch, "input_selector")?;
        let error = string_column(batch, "error")?;
        for index in 0..batch.num_rows() {
            rows.push(TraceCallRaw {
                transaction_hash: string_value(transaction_hash, index).to_ascii_lowercase(),
                depth: u64_value(depth, index),
                call_type: string_value(call_type, index),
                from_address: string_value(from_address, index).to_ascii_lowercase(),
                to_address: string_value(to_address, index).to_ascii_lowercase(),
                input_selector: string_value(input_selector, index),
                error: string_value(error, index),
            });
        }
        Ok(())
    })?;
    Ok(rows)
}

fn read_optional_files<F>(files: &[PathBuf], mut on_batch: F) -> Result<()>
where
    F: FnMut(&RecordBatch) -> Result<()>,
{
    for path in files {
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder.with_batch_size(8192).build()?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            on_batch(&batch)?;
        }
    }
    Ok(())
}

fn write_event_price_path_parquet(
    data_root: &Path,
    rows: &[EventPricePathLabelRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("block_number", DataType::UInt64, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("quote_abs", DataType::Float64, false),
        Field::new("entry_minute_utc", DataType::Utf8, false),
        Field::new("fwd_return_5m", DataType::Float64, true),
        Field::new("fwd_return_15m", DataType::Float64, true),
        Field::new("fwd_return_1h", DataType::Float64, true),
        Field::new("fwd_return_3h", DataType::Float64, true),
        Field::new("fwd_return_6h", DataType::Float64, true),
        Field::new("mfe_6h", DataType::Float64, true),
        Field::new("mae_6h", DataType::Float64, true),
        Field::new("time_to_peak_seconds", DataType::UInt64, true),
        Field::new("time_to_trough_seconds", DataType::UInt64, true),
        Field::new("reversal_after_initial_move", DataType::Boolean, false),
        Field::new("label", DataType::Utf8, false),
    ]));
    write_schema_metadata(
        data_root,
        EVENT_PRICE_PATH_LABELS_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.log_index).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.direction.clone())
                    .collect::<Vec<_>>(),
            ),
            f64_array(&rows.iter().map(|row| row.quote_abs).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.entry_minute_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_5m).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.fwd_return_15m)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_1h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_3h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_6h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.mfe_6h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.mae_6h).collect::<Vec<_>>()),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.time_to_peak_seconds)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.time_to_trough_seconds)
                    .collect::<Vec<_>>(),
            ),
            finance_chain_core::storage::bool_array(
                &rows
                    .iter()
                    .map(|row| row.reversal_after_initial_move)
                    .collect::<Vec<_>>(),
            ),
            string_array(&rows.iter().map(|row| row.label.clone()).collect::<Vec<_>>()),
        ],
    )?;
    write_single_derived_part(
        data_root,
        EVENT_PRICE_PATH_LABELS_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_tx_path_parquet(
    data_root: &Path,
    rows: &[TxExecutionPathLabelRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("path_label", DataType::Utf8, false),
        Field::new("method_selector", DataType::Utf8, false),
        Field::new("router_to_address", DataType::Utf8, false),
        Field::new("pool_sequence", DataType::Utf8, false),
        Field::new("pool_count", DataType::UInt64, false),
        Field::new("swap_count", DataType::UInt64, false),
        Field::new("mon_usdc_quote_notional", DataType::Float64, false),
        Field::new("has_external_non_pool_logs", DataType::Boolean, false),
        Field::new("input_len", DataType::UInt64, false),
        Field::new("gas", DataType::UInt64, true),
        Field::new("max_priority_fee_per_gas", DataType::UInt64, true),
    ]));
    write_schema_metadata(
        data_root,
        TX_EXECUTION_PATH_LABELS_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.path_label.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.method_selector.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.router_to_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_sequence.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.pool_count).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.swap_count).collect::<Vec<_>>()),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.mon_usdc_quote_notional)
                    .collect::<Vec<_>>(),
            ),
            finance_chain_core::storage::bool_array(
                &rows
                    .iter()
                    .map(|row| row.has_external_non_pool_logs)
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.input_len).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.gas).collect::<Vec<_>>()),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.max_priority_fee_per_gas)
                    .collect::<Vec<_>>(),
            ),
        ],
    )?;
    write_single_derived_part(
        data_root,
        TX_EXECUTION_PATH_LABELS_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_tx_path_reconstructed_parquet(
    data_root: &Path,
    rows: &[TxExecutionPathReconstructedRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("path_label", DataType::Utf8, false),
        Field::new("tx_path_source", DataType::Utf8, false),
        Field::new("tx_path_confidence", DataType::Utf8, false),
        Field::new("tx_body_request_status", DataType::Utf8, false),
        Field::new("receipt_request_status", DataType::Utf8, false),
        Field::new("method_selector", DataType::Utf8, false),
        Field::new("router_to_address", DataType::Utf8, false),
        Field::new("pool_sequence", DataType::Utf8, false),
        Field::new("pool_count", DataType::UInt64, false),
        Field::new("swap_count", DataType::UInt64, false),
        Field::new("mon_usdc_quote_notional", DataType::Float64, false),
        Field::new("external_non_pool_logs_status", DataType::Utf8, false),
        Field::new("erc20_transfer_count_status", DataType::Utf8, false),
        Field::new("input_len", DataType::UInt64, false),
        Field::new("gas", DataType::UInt64, true),
        Field::new("max_priority_fee_per_gas", DataType::UInt64, true),
    ]));
    write_schema_metadata(
        data_root,
        TX_EXECUTION_PATH_LABELS_RECONSTRUCTED_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.run_tag.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.path_label.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.tx_path_source.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.tx_path_confidence.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.tx_body_request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.method_selector.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.router_to_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_sequence.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.pool_count).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.swap_count).collect::<Vec<_>>()),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.mon_usdc_quote_notional)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.external_non_pool_logs_status.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.erc20_transfer_count_status.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.input_len).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.gas).collect::<Vec<_>>()),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.max_priority_fee_per_gas)
                    .collect::<Vec<_>>(),
            ),
        ],
    )?;
    write_single_derived_part(
        data_root,
        TX_EXECUTION_PATH_LABELS_RECONSTRUCTED_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_cross_pool_parquet(
    data_root: &Path,
    rows: &[CrossPoolDislocationRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("block_number", DataType::UInt64, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("minute_utc", DataType::Utf8, false),
        Field::new("pool_price", DataType::Float64, true),
        Field::new("reference_price", DataType::Float64, true),
        Field::new("pool_dislocation_bps", DataType::Float64, true),
        Field::new("max_min_pool_spread_bps", DataType::Float64, true),
        Field::new("pool_freshness_age_minutes", DataType::UInt64, true),
        Field::new("leader_1m_pool", DataType::Utf8, false),
        Field::new("leader_5m_pool", DataType::Utf8, false),
        Field::new("leader_15m_pool", DataType::Utf8, false),
        Field::new("convergence_5m_label", DataType::Utf8, false),
        Field::new("convergence_15m_label", DataType::Utf8, false),
    ]));
    write_schema_metadata(
        data_root,
        CROSS_POOL_DISLOCATION_FEATURES_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.log_index).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.minute_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.pool_price).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.reference_price)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.pool_dislocation_bps)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.max_min_pool_spread_bps)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.pool_freshness_age_minutes)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.leader_1m_pool.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.leader_5m_pool.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.leader_15m_pool.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.convergence_5m_label.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.convergence_15m_label.clone())
                    .collect::<Vec<_>>(),
            ),
        ],
    )?;
    write_single_derived_part(
        data_root,
        CROSS_POOL_DISLOCATION_FEATURES_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_pool_state_features_parquet(
    data_root: &Path,
    rows: &[PoolStateEventFeatureRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("event_block_number", DataType::UInt64, false),
        Field::new("sample_block_number", DataType::UInt64, false),
        Field::new("sample_side", DataType::Utf8, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("sampled", DataType::Boolean, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("event_quote_notional", DataType::Float64, false),
        Field::new("active_tick_or_bin", DataType::Utf8, false),
        Field::new("active_liquidity_or_reserve", DataType::Utf8, false),
        Field::new(
            "event_notional_to_active_liquidity_proxy",
            DataType::Float64,
            true,
        ),
        Field::new("local_window_imbalance", DataType::Float64, true),
    ]));
    write_schema_metadata(
        data_root,
        POOL_STATE_EVENT_FEATURES_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.event_block_number)
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.sample_block_number)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.sample_side.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.family.clone())
                    .collect::<Vec<_>>(),
            ),
            finance_chain_core::storage::bool_array(
                &rows.iter().map(|row| row.sampled).collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.event_quote_notional)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.active_tick_or_bin.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.active_liquidity_or_reserve.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.event_notional_to_active_liquidity_proxy)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.local_window_imbalance)
                    .collect::<Vec<_>>(),
            ),
        ],
    )?;
    write_single_derived_part(
        data_root,
        POOL_STATE_EVENT_FEATURES_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_pool_state_reconstructed_parquet(
    data_root: &Path,
    rows: &[PoolStateEventFeatureReconstructedRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("quote_abs", DataType::Float64, false),
        Field::new("event_request_status", DataType::Utf8, false),
        Field::new("pre_request_status", DataType::Utf8, false),
        Field::new("event_state_source", DataType::Utf8, false),
        Field::new("event_state_confidence", DataType::Utf8, false),
        Field::new("pre_state_source", DataType::Utf8, false),
        Field::new("pre_state_confidence", DataType::Utf8, false),
        Field::new("event_sqrt_price_x96", DataType::Utf8, false),
        Field::new("event_tick_or_bin", DataType::Utf8, false),
        Field::new("event_liquidity_or_reserve", DataType::Utf8, false),
        Field::new("pre_sqrt_price_x96", DataType::Utf8, false),
        Field::new("pre_tick_or_bin", DataType::Utf8, false),
        Field::new("pre_liquidity_or_reserve", DataType::Utf8, false),
        Field::new("pre_state_age_blocks", DataType::UInt64, true),
        Field::new("pre_state_age_minutes", DataType::UInt64, true),
        Field::new(
            "event_notional_to_active_liquidity_proxy",
            DataType::Float64,
            true,
        ),
        Field::new("event_local_window_imbalance", DataType::Float64, true),
        Field::new("pre_local_window_imbalance", DataType::Float64, true),
        Field::new("usable_for_research", DataType::Boolean, false),
    ]));
    write_schema_metadata(
        data_root,
        POOL_STATE_EVENT_FEATURES_RECONSTRUCTED_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.run_tag.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.log_index).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.family.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.direction.clone())
                    .collect::<Vec<_>>(),
            ),
            f64_array(&rows.iter().map(|row| row.quote_abs).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.event_request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pre_request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.event_state_source.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.event_state_confidence.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pre_state_source.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pre_state_confidence.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.event_sqrt_price_x96.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.event_tick_or_bin.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.event_liquidity_or_reserve.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pre_sqrt_price_x96.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pre_tick_or_bin.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pre_liquidity_or_reserve.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.pre_state_age_blocks)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.pre_state_age_minutes)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.event_notional_to_active_liquidity_proxy)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.event_local_window_imbalance)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.pre_local_window_imbalance)
                    .collect::<Vec<_>>(),
            ),
            finance_chain_core::storage::bool_array(
                &rows
                    .iter()
                    .map(|row| row.usable_for_research)
                    .collect::<Vec<_>>(),
            ),
        ],
    )?;
    write_single_derived_part(
        data_root,
        POOL_STATE_EVENT_FEATURES_RECONSTRUCTED_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_trace_labels_parquet(
    data_root: &Path,
    rows: &[DebugTraceLabelRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("sampled", DataType::Boolean, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("call_graph_depth", DataType::UInt64, false),
        Field::new("call_count", DataType::UInt64, false),
        Field::new("router_calls", DataType::UInt64, false),
        Field::new("pool_calls", DataType::UInt64, false),
        Field::new("token_calls", DataType::UInt64, false),
        Field::new("reverts", DataType::UInt64, false),
        Field::new("internal_value_transfers", DataType::UInt64, false),
        Field::new("trace_path_class", DataType::Utf8, false),
    ]));
    write_schema_metadata(
        data_root,
        DEBUG_TRACE_LABELS_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            finance_chain_core::storage::bool_array(
                &rows.iter().map(|row| row.sampled).collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.call_graph_depth)
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.call_count).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.router_calls).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.pool_calls).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.token_calls).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.reverts).collect::<Vec<_>>()),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.internal_value_transfers)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.trace_path_class.clone())
                    .collect::<Vec<_>>(),
            ),
        ],
    )?;
    write_single_derived_part(
        data_root,
        DEBUG_TRACE_LABELS_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_event_execution_features_parquet(
    data_root: &Path,
    rows: &[EventExecutionFeatureRow],
    run_tag: &str,
) -> Result<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("run_tag", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, false),
        Field::new("event_time_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("base_abs", DataType::Float64, true),
        Field::new("quote_abs", DataType::Float64, true),
        Field::new("price_quote_per_base", DataType::Float64, true),
        Field::new("receipt_request_status", DataType::Utf8, false),
        Field::new("receipt_status", DataType::UInt64, true),
        Field::new("receipt_gas_used", DataType::UInt64, true),
        Field::new("effective_gas_price", DataType::UInt64, true),
        Field::new("base_fee_per_gas", DataType::UInt64, true),
        Field::new("same_block_event_count", DataType::UInt64, false),
        Field::new("price_path_label", DataType::Utf8, false),
        Field::new("fwd_return_5m", DataType::Float64, true),
        Field::new("fwd_return_15m", DataType::Float64, true),
        Field::new("fwd_return_1h", DataType::Float64, true),
        Field::new("fwd_return_3h", DataType::Float64, true),
        Field::new("fwd_return_6h", DataType::Float64, true),
        Field::new("pool_dislocation_bps", DataType::Float64, true),
        Field::new("max_min_pool_spread_bps", DataType::Float64, true),
        Field::new("convergence_15m_label", DataType::Utf8, false),
        Field::new("tx_path_label", DataType::Utf8, false),
        Field::new("tx_path_source", DataType::Utf8, false),
        Field::new("tx_path_confidence", DataType::Utf8, false),
        Field::new("pool_event_state_source", DataType::Utf8, false),
        Field::new("pool_event_state_confidence", DataType::Utf8, false),
        Field::new("pool_pre_state_source", DataType::Utf8, false),
        Field::new("pool_pre_state_confidence", DataType::Utf8, false),
        Field::new("pool_pre_state_age_blocks", DataType::UInt64, true),
        Field::new("trace_path_class", DataType::Utf8, false),
        Field::new("trace_source", DataType::Utf8, false),
        Field::new("trace_confidence", DataType::Utf8, false),
        Field::new("trace_call_graph_depth", DataType::UInt64, true),
        Field::new("trace_call_count", DataType::UInt64, true),
        Field::new("quality_tier", DataType::Utf8, false),
        Field::new("usable_for_execution_research", DataType::Boolean, false),
    ]));
    write_schema_metadata(
        data_root,
        EVENT_EXECUTION_FEATURES_DATASET,
        schema.as_ref(),
        &["dt"],
    )?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            string_array(
                &rows
                    .iter()
                    .map(|row| row.run_tag.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.event_time_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_hash.clone())
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.transaction_index)
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.log_index).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.dex_id.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.family.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.direction.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.base_abs).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.quote_abs).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_quote_per_base)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_request_status.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_status)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.receipt_gas_used)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.effective_gas_price)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.base_fee_per_gas)
                    .collect::<Vec<_>>(),
            ),
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.same_block_event_count)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.price_path_label.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_5m).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.fwd_return_15m)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_1h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_3h).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.fwd_return_6h).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.pool_dislocation_bps)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.max_min_pool_spread_bps)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.convergence_15m_label.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.tx_path_label.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.tx_path_source.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.tx_path_confidence.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_event_state_source.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_event_state_confidence.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_pre_state_source.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pool_pre_state_confidence.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.pool_pre_state_age_blocks)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.trace_path_class.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.trace_source.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.trace_confidence.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.trace_call_graph_depth)
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(
                &rows
                    .iter()
                    .map(|row| row.trace_call_count)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quality_tier.clone())
                    .collect::<Vec<_>>(),
            ),
            finance_chain_core::storage::bool_array(
                &rows
                    .iter()
                    .map(|row| row.usable_for_execution_research)
                    .collect::<Vec<_>>(),
            ),
        ],
    )?;
    write_single_derived_part(
        data_root,
        EVENT_EXECUTION_FEATURES_DATASET,
        schema,
        batch,
        run_tag,
    )
}

fn write_single_derived_part(
    data_root: &Path,
    dataset: &str,
    schema: SchemaRef,
    batch: RecordBatch,
    run_tag: &str,
) -> Result<()> {
    let dt = run_tag.get(..10).unwrap_or("enrichment").replace('_', "-");
    let stem = format!("mon_usdc_{}_{}", dataset, run_tag);
    write_parquet_part(
        &custom_part_path(data_root, DERIVED_DIR, dataset, &dt, &stem),
        schema,
        batch,
    )?;
    Ok(())
}

fn write_enrichment_report(summary: &EnrichmentSummary) -> Result<()> {
    let path = Path::new(&summary.outputs.report);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    let quality_tiers = summary
        .coverage
        .reconstruction
        .event_panel
        .quality_tier_counts
        .iter()
        .map(|row| format!("{} `{}`", row.label, row.rows))
        .collect::<Vec<_>>()
        .join(", ");
    let body = format!(
        "# MON/USDC V1 Enrichment Report\n\nStatus: `{}`.\n\n## Coverage\n\n- tx bodies: `{}/{}` missing `{}` errors `{}`\n- receipt log bundles: `{}/{}` log rows `{}` missing `{}` errors `{}`\n- derived rows: price paths `{}`, tx paths `{}`, cross-pool `{}`\n- pool state samples: success `{}` failed `{}`\n- trace samples: success `{}` failed `{}`\n- reconstructed execution panel: rows `{}`, usable `{}`, tiers {}\n\n## Final Status\n\n- base_enrichment_passed: `{}`\n- sample_enrichment_passed: `{}`\n\nOutputs are listed in `{}`.\n",
        summary.run_tag,
        summary.coverage.tx_body.written_txs,
        summary.coverage.tx_body.expected_txs,
        summary.coverage.tx_body.missing_txs,
        summary.coverage.tx_body.request_errors,
        summary.coverage.receipt_log_bundle.summary_rows,
        summary.coverage.receipt_log_bundle.expected_txs,
        summary.coverage.receipt_log_bundle.log_rows,
        summary.coverage.receipt_log_bundle.missing_txs,
        summary.coverage.receipt_log_bundle.request_errors,
        summary.coverage.derived_full.event_price_path_rows,
        summary.coverage.derived_full.tx_path_label_rows,
        summary.coverage.derived_full.cross_pool_rows,
        summary.coverage.sampled.pool_state_success_count,
        summary.coverage.sampled.pool_state_failed_count,
        summary.coverage.sampled.trace_success_count,
        summary.coverage.sampled.trace_failed_count,
        summary.coverage.reconstruction.event_panel.rows,
        summary
            .coverage
            .reconstruction
            .event_panel
            .usable_for_execution_research,
        quality_tiers,
        summary.final_status.base_enrichment_passed,
        summary.final_status.sample_enrichment_passed,
        summary.outputs.completion_json,
    );
    std::fs::write(path, body).with_context(|| format!("failed to write {}", path.display()))
}

fn string_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| anyhow!("column {name} is not utf8"))
}

fn u64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a UInt64Array> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .ok_or_else(|| anyhow!("column {name} is not uint64"))
}

#[allow(dead_code)]
fn bool_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a BooleanArray> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<BooleanArray>()
        .ok_or_else(|| anyhow!("column {name} is not boolean"))
}

fn string_value(values: &StringArray, index: usize) -> String {
    if values.is_null(index) {
        String::new()
    } else {
        values.value(index).to_string()
    }
}

fn u64_value(values: &UInt64Array, index: usize) -> u64 {
    if values.is_null(index) {
        0
    } else {
        values.value(index)
    }
}

fn u64_option(values: &UInt64Array, index: usize) -> Option<u64> {
    if values.is_null(index) {
        None
    } else {
        Some(values.value(index))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_event(
        block_number: u64,
        timestamp: i64,
        transaction_hash: &str,
        log_index: u64,
        pool_address: &str,
        family: &str,
        direction: &str,
        quote_abs: f64,
    ) -> EventRecord {
        let is_buy_base = direction == "buy_base";
        let is_sell_base = direction == "sell_base";
        EventRecord {
            block_number,
            timestamp,
            block_datetime_utc: String::new(),
            hour_utc: String::new(),
            minute_utc: String::new(),
            transaction_hash: transaction_hash.to_string(),
            transaction_index: 0,
            log_index,
            pool_address: pool_address.to_ascii_lowercase(),
            dex_id: String::new(),
            family: family.to_string(),
            base_symbol: "MON".to_string(),
            quote_symbol: "USDC".to_string(),
            base_abs: Some(1.0),
            quote_abs: Some(quote_abs),
            price_quote_per_base: Some(1.0),
            clean_keep: true,
            clean_exclusion_reason: String::new(),
            is_buy_base,
            is_sell_base,
            buy_base: if is_buy_base { 1.0 } else { 0.0 },
            sell_base: if is_sell_base { 1.0 } else { 0.0 },
            net_buy_base: if is_buy_base {
                1.0
            } else if is_sell_base {
                -1.0
            } else {
                0.0
            },
            signed_quote_flow: if is_buy_base {
                quote_abs
            } else if is_sell_base {
                -quote_abs
            } else {
                0.0
            },
            receipt_request_status: "ok".to_string(),
            receipt_status: Some(1),
            receipt_gas_used: None,
            effective_gas_price: None,
            base_fee_per_gas: None,
            priority_fee_gwei: None,
            gas_to_base_fee_ratio: None,
            header_event_log_count: None,
            same_block_event_count: 1,
        }
    }

    fn test_swap_metadata(
        event: &EventRecord,
        sqrt: &str,
        liquidity: &str,
        tick: &str,
    ) -> SwapMetadataRaw {
        SwapMetadataRaw {
            block_number: event.block_number,
            timestamp: event.timestamp,
            transaction_hash: event.transaction_hash.clone(),
            log_index: event.log_index,
            pool_address: event.pool_address.clone(),
            family: event.family.clone(),
            sqrt_price_x96: sqrt.to_string(),
            liquidity_raw: liquidity.to_string(),
            tick: tick.to_string(),
        }
    }

    #[test]
    fn path_label_marks_insufficient_future_price() {
        let event = test_event(1, 60, "0x1", 0, "pool", "v3", "buy_base", 1.0);
        assert_eq!(
            price_path_label(&event, Some(0.01), None, Some(1.0)),
            "insufficient_future_price"
        );
    }

    #[test]
    fn classifier_detects_direct_pool_swap() {
        let pool = known_top4_pools()[0].pair_address.to_ascii_lowercase();
        let body = TxBodyRaw {
            fetched_at_utc: String::new(),
            transaction_hash: "0x1".to_string(),
            request_status: "ok".to_string(),
            error: String::new(),
            to_address: pool.clone(),
            method_selector: "0xabcdef01".to_string(),
            input_len: 4,
            gas: None,
            max_priority_fee_per_gas: None,
        };
        let summary = ReceiptSummaryRaw {
            fetched_at_utc: String::new(),
            transaction_hash: "0x1".to_string(),
            request_status: "ok".to_string(),
            error: String::new(),
            logs_count: 1,
            mon_usdc_swap_log_count: 1,
            erc20_transfer_count: 0,
            pool_addresses_seen: pool.clone(),
        };
        assert_eq!(
            classify_tx_path(Some(&body), Some(&summary), &pool, "0xabcdef01", 1, 1, &[]),
            "direct_pool_swap"
        );
    }

    #[test]
    fn reconstructed_tx_path_uses_swap_logs_when_receipt_summary_rpc_errors() {
        let pool = known_top4_pools()[0].pair_address.to_ascii_lowercase();
        let events = vec![test_event(1, 60, "0x1", 0, &pool, "v3", "buy_base", 100.0)];
        let body = TxBodyRaw {
            fetched_at_utc: String::new(),
            transaction_hash: "0x1".to_string(),
            request_status: "ok".to_string(),
            error: String::new(),
            to_address: "0xrouter".to_string(),
            method_selector: "0xabcdef01".to_string(),
            input_len: 128,
            gas: Some(100_000),
            max_priority_fee_per_gas: None,
        };
        let summary = ReceiptSummaryRaw {
            fetched_at_utc: String::new(),
            transaction_hash: "0x1".to_string(),
            request_status: "rpc_error".to_string(),
            error: "rate limited".to_string(),
            logs_count: 0,
            mon_usdc_swap_log_count: 0,
            erc20_transfer_count: 0,
            pool_addresses_seen: String::new(),
        };
        let rows =
            build_tx_execution_path_labels_reconstructed(&events, &[body], &[summary], &[], "test");
        assert_eq!(rows[0].path_label, "router_single_pool");
        assert_eq!(rows[0].tx_path_source, "reconstructed_from_swap_logs");
        assert_eq!(rows[0].tx_path_confidence, "medium");
        assert_eq!(rows[0].erc20_transfer_count_status, "unknown");
        assert_eq!(rows[0].external_non_pool_logs_status, "unknown");
    }

    #[test]
    fn v3_like_swap_metadata_generates_event_state_proxy() {
        let pool = known_top4_pools()[1].pair_address.to_ascii_lowercase();
        let event = test_event(10, 600, "0x2", 1, &pool, "pancake_v3", "sell_base", 25.0);
        let metadata = test_swap_metadata(&event, "123456", "987654321", "-42");
        let rows =
            build_pool_state_event_features_reconstructed(&[event], &[metadata], &[], &[], "test");
        assert_eq!(rows[0].event_state_source, "reconstructed_from_swap_logs");
        assert_eq!(rows[0].event_state_confidence, "medium");
        assert_eq!(rows[0].event_sqrt_price_x96, "123456");
        assert_eq!(rows[0].event_tick_or_bin, "-42");
        assert_eq!(rows[0].event_liquidity_or_reserve, "987654321");
        assert!(rows[0].event_notional_to_active_liquidity_proxy.is_some());
    }

    #[test]
    fn lb_swap_metadata_does_not_fabricate_reserve_or_liquidity() {
        let pool = known_top4_pools()[2].pair_address.to_ascii_lowercase();
        let event = test_event(11, 660, "0x3", 0, &pool, "lb_v22", "buy_base", 50.0);
        let metadata = test_swap_metadata(&event, "", "", "8388600");
        let rows =
            build_pool_state_event_features_reconstructed(&[event], &[metadata], &[], &[], "test");
        assert_eq!(rows[0].event_state_source, "reconstructed_from_swap_logs");
        assert_eq!(rows[0].event_tick_or_bin, "8388600");
        assert!(rows[0].event_liquidity_or_reserve.is_empty());
        assert!(rows[0].event_notional_to_active_liquidity_proxy.is_none());
    }

    #[test]
    fn carry_forward_pre_state_records_age_and_confidence() {
        let pool = known_top4_pools()[0].pair_address.to_ascii_lowercase();
        let first = test_event(100, 1_000, "0x4", 0, &pool, "v3", "buy_base", 10.0);
        let second = test_event(120, 1_120, "0x5", 0, &pool, "v3", "sell_base", 20.0);
        let third = test_event(2_000, 2_000, "0x6", 0, &pool, "v3", "buy_base", 30.0);
        let metadata = vec![
            test_swap_metadata(&first, "1", "1000", "10"),
            test_swap_metadata(&second, "2", "1000", "11"),
            test_swap_metadata(&third, "3", "1000", "12"),
        ];
        let rows = build_pool_state_event_features_reconstructed(
            &[first, second, third],
            &metadata,
            &[],
            &[],
            "test",
        );
        assert_eq!(rows[1].pre_state_source, "carry_forward_swap_state");
        assert_eq!(rows[1].pre_state_age_blocks, Some(20));
        assert_eq!(rows[1].pre_state_confidence, "medium");
        assert_eq!(rows[2].pre_state_source, "carry_forward_swap_state");
        assert_eq!(rows[2].pre_state_confidence, "low");
    }
}

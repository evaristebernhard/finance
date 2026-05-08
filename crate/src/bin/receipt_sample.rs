use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use arrow::array::{Array, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chog_prices::{
    CHECKPOINT_VERSION, Checkpoint, RpcUrlPool,
    chog_v1::{
        ChogCollectionRunRecord, PartWrite, PartWriteStatus, checkpoint_path_with_suffix,
        custom_part_path, default_data_root_path, deterministic_list_id, dt_from_timestamp,
        dt_from_utc_string, fetch_block_timestamp_from_pool, opt_u64_array, parquet_files_under,
        part_paths_to_string, read_string_column_from_parquet, repo_root, string_array,
        unique_tx_hashes_from_datasets, utc_from_timestamp, write_collection_run_parquet,
        write_parquet_part, write_schema_metadata,
    },
    parse_hex_u64, save_checkpoint, utc_now_string,
};
use clap::{Parser, ValueEnum};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::{Value, json};

const DEFAULT_RPC_URL: &str = "https://rpc.monad.xyz";
const DEFAULT_BATCH_SIZE: usize = 250;
const DEFAULT_RPC_BATCH_SIZE: usize = 50;
const COLLECTOR: &str = "receipt_sample";
const CHAIN: &str = "monad";
const DATASET: &str = "tx_receipts";
const SOURCE_DATASETS: &[&str] = &[
    "erc20_transfer_logs",
    "main_pool_swap_logs",
    "dex_pool_swap_logs",
];
const CHOG_POOL_TX_DATASETS: &[&str] = &["main_pool_swap_logs", "dex_pool_swap_logs"];
const MAIN_POOL_DATASETS: &[&str] = &["main_pool_swap_logs"];
const EVENT_HEADER_DATASET: &str = "event_block_headers";

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum SourceScope {
    ChogPoolTxs,
    MainPool,
    AllToken,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum TimestampSource {
    LocalFirst,
    RpcOnly,
}

#[derive(Debug, Parser)]
#[command(
    name = "receipt_sample",
    about = "Fetch transaction receipts and transaction bodies for CHOG-related tx hashes."
)]
struct Args {
    #[arg(long = "rpc-url", default_value = DEFAULT_RPC_URL)]
    rpc_url: Vec<String>,

    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Explicit transaction hash. Can be repeated.
    #[arg(long = "tx-hash")]
    tx_hashes: Vec<String>,

    /// Optional newline-delimited transaction hash file.
    #[arg(long)]
    tx_hashes_file: Option<PathBuf>,

    /// Scan CHOG v1 swap/transfer Parquet datasets for transaction hashes.
    #[arg(long)]
    from_data_root: bool,

    /// Local Parquet source scope used when reading tx hashes from --data-root.
    #[arg(long, value_enum, default_value_t = SourceScope::ChogPoolTxs)]
    source_scope: SourceScope,

    /// Block timestamp source for receipt rows.
    #[arg(long, value_enum, default_value_t = TimestampSource::LocalFirst)]
    timestamp_source: TimestampSource,

    /// Maximum hashes to collect in this run after dedupe.
    #[arg(long)]
    max_txs: Option<usize>,

    /// Suffix for the default checkpoint filename, useful for parallel shards.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Number of hashes per deterministic output part.
    #[arg(long, default_value_t = DEFAULT_BATCH_SIZE)]
    batch_size: usize,

    /// Number of hashes per JSON-RPC batch request.
    #[arg(long, default_value_t = DEFAULT_RPC_BATCH_SIZE)]
    rpc_batch_size: usize,

    /// Fetch only transaction receipts and leave transaction-body-only fields empty.
    #[arg(long)]
    receipt_only: bool,

    /// Resolve the queue and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RpcReceipt {
    transaction_hash: String,
    transaction_index: Option<String>,
    block_hash: Option<String>,
    block_number: Option<String>,
    from: Option<String>,
    to: Option<String>,
    cumulative_gas_used: Option<String>,
    gas_used: Option<String>,
    contract_address: Option<String>,
    logs: Option<Vec<Value>>,
    status: Option<String>,
    effective_gas_price: Option<String>,
    #[serde(rename = "type")]
    tx_type: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RpcTransaction {
    hash: String,
    nonce: Option<String>,
    block_hash: Option<String>,
    block_number: Option<String>,
    transaction_index: Option<String>,
    from: Option<String>,
    to: Option<String>,
    value: Option<String>,
    gas: Option<String>,
    gas_price: Option<String>,
    input: Option<String>,
    max_fee_per_gas: Option<String>,
    max_priority_fee_per_gas: Option<String>,
    #[serde(rename = "type")]
    tx_type: Option<String>,
}

#[derive(Debug, Clone)]
struct ReceiptRow {
    fetched_at_utc: String,
    transaction_hash: String,
    request_status: String,
    error: String,
    block_number: Option<u64>,
    block_hash: String,
    block_timestamp: Option<u64>,
    block_datetime_utc: String,
    transaction_index: Option<u64>,
    from_address: String,
    to_address: String,
    contract_address: String,
    receipt_status: Option<u64>,
    gas_used: Option<u64>,
    cumulative_gas_used: Option<u64>,
    effective_gas_price: Option<u64>,
    tx_type: String,
    nonce: Option<u64>,
    gas: Option<u64>,
    gas_price: Option<u64>,
    max_fee_per_gas: Option<u64>,
    max_priority_fee_per_gas: Option<u64>,
    value_raw: String,
    input: String,
    logs_count: Option<u64>,
    dt: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
struct SourceTxMetadata {
    block_number: Option<u64>,
    block_timestamp: Option<u64>,
}

#[derive(Debug, Clone)]
struct ReceiptQueue {
    hashes: Vec<String>,
    local_metadata: BTreeMap<String, SourceTxMetadata>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.batch_size == 0 {
        anyhow::bail!("--batch-size must be greater than 0");
    }
    if args.rpc_batch_size == 0 {
        anyhow::bail!("--rpc-batch-size must be greater than 0");
    }

    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    let started_at = utc_now_string();
    let mut queue = collect_tx_queue(&args, &data_root)?;
    let existing = existing_receipt_hashes(&data_root)?;
    queue.hashes.retain(|hash| !existing.contains(hash));
    if let Some(max_txs) = args.max_txs {
        queue.hashes.truncate(max_txs);
    }

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DATASET}");
        println!("source scope: {:?}", args.source_scope);
        println!("timestamp source: {:?}", args.timestamp_source);
        println!("rpc batch size: {}", args.rpc_batch_size);
        println!("receipt only: {}", args.receipt_only);
        println!("queued hashes after dedupe: {}", queue.hashes.len());
        println!("data root: {}", data_root.display());
        return Ok(());
    }

    let schema = receipt_schema();
    write_schema_metadata(&data_root, DATASET, schema.as_ref(), &["dt"])?;

    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-receipt-sample/0.1")
        .build()
        .context("failed to build HTTP client")?;
    let rpc_urls = receipt_rpc_pool(&args.rpc_url)?;

    let event_header_timestamps = if args.timestamp_source == TimestampSource::LocalFirst {
        read_event_header_timestamps(&data_root)?
    } else {
        BTreeMap::new()
    };
    let mut timestamp_cache = BTreeMap::<u64, (u64, String)>::new();
    let mut output_parts = Vec::new();
    let mut rows_written = 0u64;
    let fetched_at = started_at.clone();
    for batch_hashes in queue.hashes.chunks(args.batch_size) {
        let mut rows = Vec::new();
        for rpc_batch_hashes in batch_hashes.chunks(args.rpc_batch_size) {
            rows.extend(fetch_receipt_row_results_batch(
                &client,
                &rpc_urls,
                rpc_batch_hashes,
                &fetched_at,
                args.timestamp_source,
                &queue.local_metadata,
                &event_header_timestamps,
                &mut timestamp_cache,
                args.receipt_only,
            )?);
        }

        let parts = write_receipt_parts(&data_root, schema.clone(), &rows, batch_hashes)?;
        rows_written += parts
            .iter()
            .filter(|part| part.status == PartWriteStatus::Written)
            .map(|part| part.rows as u64)
            .sum::<u64>();
        output_parts.extend(parts);
    }

    let finished_at = utc_now_string();
    let checkpoint = Checkpoint {
        version: CHECKPOINT_VERSION,
        collector: COLLECTOR.to_string(),
        chain: CHAIN.to_string(),
        address: String::new(),
        topic0: String::new(),
        from_block: 0,
        to_block: 0,
        last_completed_block: 0,
        rows_written,
        output: part_paths_to_string(&output_parts),
        updated_at_utc: finished_at.clone(),
    };
    let checkpoint_path =
        checkpoint_path_with_suffix(&data_root, COLLECTOR, args.checkpoint_suffix.as_deref())?;
    save_checkpoint(&checkpoint_path, &checkpoint)?;
    write_collection_run_parquet(
        &data_root,
        &ChogCollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: String::new(),
            topic0: String::new(),
            from_block: None,
            to_block: None,
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed: queue.hashes.chunks(args.batch_size).count() as u64,
            status: if queue.hashes.is_empty() {
                "empty"
            } else {
                "completed"
            }
            .to_string(),
            error: String::new(),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    println!("receipt rows written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    Ok(())
}

fn collect_tx_queue(args: &Args, data_root: &Path) -> Result<ReceiptQueue> {
    let mut hashes = BTreeSet::new();
    let mut local_metadata = BTreeMap::<String, SourceTxMetadata>::new();
    for hash in &args.tx_hashes {
        hashes.insert(hash.to_string());
    }
    if let Some(path) = &args.tx_hashes_file {
        let body = std::fs::read_to_string(path)
            .with_context(|| format!("failed to read {}", path.display()))?;
        for line in body.lines() {
            let hash = line.trim();
            if !hash.is_empty() {
                hashes.insert(hash.to_string());
            }
        }
    }
    if args.from_data_root || hashes.is_empty() {
        let datasets = source_datasets_for_scope(args.source_scope);
        for hash in unique_tx_hashes_from_datasets(data_root, datasets)? {
            hashes.insert(hash);
        }
        local_metadata = read_source_tx_metadata(data_root, datasets)?;
    }
    Ok(ReceiptQueue {
        hashes: hashes.into_iter().collect(),
        local_metadata,
    })
}

fn source_datasets_for_scope(scope: SourceScope) -> &'static [&'static str] {
    match scope {
        SourceScope::ChogPoolTxs => CHOG_POOL_TX_DATASETS,
        SourceScope::MainPool => MAIN_POOL_DATASETS,
        SourceScope::AllToken => SOURCE_DATASETS,
    }
}

fn receipt_rpc_pool(arg_rpc_urls: &[String]) -> Result<RpcUrlPool> {
    let mut rpc_urls = Vec::new();
    if let Some(alchemy_rpc) = alchemy_rpc_from_env()? {
        push_unique_rpc_values(&mut rpc_urls, &alchemy_rpc);
    }
    for rpc_url in arg_rpc_urls {
        push_unique_rpc_values(&mut rpc_urls, rpc_url);
    }
    if rpc_urls.is_empty() {
        rpc_urls.push(DEFAULT_RPC_URL.to_string());
    }
    RpcUrlPool::from_values(&rpc_urls, DEFAULT_RPC_URL)
}

fn alchemy_rpc_from_env() -> Result<Option<String>> {
    if let Ok(value) = std::env::var("ALCHEMY_RPC") {
        let value = value.trim();
        if !value.is_empty() {
            return Ok(Some(value.to_string()));
        }
    }

    let path = repo_root().join(".env.chog.local");
    if !path.exists() {
        return Ok(None);
    }
    let body = std::fs::read_to_string(&path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    Ok(parse_env_value(&body, "ALCHEMY_RPC"))
}

fn parse_env_value(body: &str, key: &str) -> Option<String> {
    for raw_line in body.lines() {
        let mut line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(rest) = line.strip_prefix("export ") {
            line = rest.trim_start();
        }
        let Some((name, value)) = line.split_once('=') else {
            continue;
        };
        if name.trim() != key {
            continue;
        }
        let value = clean_env_value(value);
        if !value.is_empty() {
            return Some(value);
        }
    }
    None
}

fn clean_env_value(value: &str) -> String {
    let value = value.trim();
    if let Some(rest) = value.strip_prefix('"') {
        return rest
            .split_once('"')
            .map(|(quoted, _)| quoted)
            .unwrap_or(rest)
            .to_string();
    }
    if let Some(rest) = value.strip_prefix('\'') {
        return rest
            .split_once('\'')
            .map(|(quoted, _)| quoted)
            .unwrap_or(rest)
            .to_string();
    }
    value
        .split_once('#')
        .map(|(before_comment, _)| before_comment)
        .unwrap_or(value)
        .trim()
        .to_string()
}

fn push_unique_rpc_values(rpc_urls: &mut Vec<String>, value: &str) {
    for rpc_url in value.split(',') {
        let rpc_url = rpc_url.trim();
        if !rpc_url.is_empty() && !rpc_urls.iter().any(|existing| existing == rpc_url) {
            rpc_urls.push(rpc_url.to_string());
        }
    }
}

fn existing_receipt_hashes(data_root: &std::path::Path) -> Result<BTreeSet<String>> {
    let mut hashes = BTreeSet::new();
    let root = data_root.join(chog_prices::chog_v1::RAW_DIR).join(DATASET);
    for path in parquet_files_under(&root)? {
        for hash in read_string_column_from_parquet(&path, "transaction_hash")? {
            hashes.insert(hash);
        }
    }
    Ok(hashes)
}

fn read_source_tx_metadata(
    data_root: &Path,
    datasets: &[&str],
) -> Result<BTreeMap<String, SourceTxMetadata>> {
    let mut metadata = BTreeMap::<String, SourceTxMetadata>::new();
    for dataset in datasets {
        let root = data_root.join(chog_prices::chog_v1::RAW_DIR).join(dataset);
        for path in parquet_files_under(&root)? {
            read_source_tx_metadata_file(&path, &mut metadata)?;
        }
    }
    Ok(metadata)
}

fn read_source_tx_metadata_file(
    path: &Path,
    metadata: &mut BTreeMap<String, SourceTxMetadata>,
) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(4096)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        let block_number = uint64_column(&batch, "block_number")?;
        let block_timestamp = uint64_column(&batch, "block_timestamp")?;
        for index in 0..batch.num_rows() {
            if transaction_hash.is_null(index) || transaction_hash.value(index).is_empty() {
                continue;
            }
            let entry = metadata
                .entry(transaction_hash.value(index).to_string())
                .or_default();
            if entry.block_number.is_none() && !block_number.is_null(index) {
                entry.block_number = Some(block_number.value(index));
            }
            if entry.block_timestamp.is_none()
                && !block_timestamp.is_null(index)
                && block_timestamp.value(index) > 0
            {
                entry.block_timestamp = Some(block_timestamp.value(index));
            }
        }
    }
    Ok(())
}

fn read_event_header_timestamps(data_root: &Path) -> Result<BTreeMap<u64, (u64, String)>> {
    let mut timestamps = BTreeMap::<u64, (u64, String)>::new();
    let root = data_root
        .join(chog_prices::chog_v1::RAW_DIR)
        .join(EVENT_HEADER_DATASET);
    for path in parquet_files_under(&root)? {
        read_event_header_timestamp_file(&path, &mut timestamps)?;
    }
    Ok(timestamps)
}

fn read_event_header_timestamp_file(
    path: &Path,
    timestamps: &mut BTreeMap<u64, (u64, String)>,
) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(4096)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let block_number = uint64_column(&batch, "block_number")?;
        let block_timestamp = uint64_column(&batch, "block_timestamp")?;
        let block_datetime_utc = string_column(&batch, "block_datetime_utc")?;
        for index in 0..batch.num_rows() {
            if block_number.is_null(index) || block_timestamp.is_null(index) {
                continue;
            }
            let datetime = if !block_datetime_utc.is_null(index) {
                block_datetime_utc.value(index).to_string()
            } else {
                utc_from_timestamp(block_timestamp.value(index))?
            };
            timestamps
                .entry(block_number.value(index))
                .or_insert((block_timestamp.value(index), datetime));
        }
    }
    Ok(())
}

fn fetch_receipt_row_results_batch(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    hashes: &[String],
    fetched_at: &str,
    timestamp_source: TimestampSource,
    local_metadata: &BTreeMap<String, SourceTxMetadata>,
    event_header_timestamps: &BTreeMap<u64, (u64, String)>,
    timestamp_cache: &mut BTreeMap<u64, (u64, String)>,
    receipt_only: bool,
) -> Result<Vec<ReceiptRow>> {
    let receipt_values = rpc_call_nullable_values_batch_adaptive(
        client,
        rpc_urls,
        "eth_getTransactionReceipt",
        hashes,
    )
    .with_context(|| format!("failed to fetch receipt batch with {} txs", hashes.len()))?;
    let tx_values = if receipt_only {
        vec![Value::Null; hashes.len()]
    } else {
        rpc_call_nullable_values_batch_adaptive(
            client,
            rpc_urls,
            "eth_getTransactionByHash",
            hashes,
        )
        .with_context(|| {
            format!(
                "failed to fetch transaction body batch with {} txs",
                hashes.len()
            )
        })?
    };

    let mut rows = Vec::with_capacity(hashes.len());
    for ((hash, receipt_value), tx_value) in hashes.iter().zip(receipt_values).zip(tx_values) {
        rows.push(receipt_row_from_rpc_values(
            client,
            rpc_urls,
            hash,
            fetched_at,
            timestamp_source,
            local_metadata.get(hash),
            event_header_timestamps,
            timestamp_cache,
            receipt_value,
            tx_value,
            receipt_only,
        )?);
    }
    Ok(rows)
}

fn rpc_call_nullable_values_batch_adaptive(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    method: &str,
    hashes: &[String],
) -> Result<Vec<Value>> {
    match rpc_call_nullable_values_batch_from_pool(client, rpc_urls, method, hashes) {
        Ok(values) => Ok(values),
        Err(error) if hashes.len() > 1 => {
            let mid = hashes.len() / 2;
            let mut left = rpc_call_nullable_values_batch_adaptive(
                client,
                rpc_urls,
                method,
                &hashes[..mid],
            )
            .with_context(|| {
                format!(
                    "failed split JSON-RPC batch {method} left half after original error: {error:#}"
                )
            })?;
            let mut right =
                rpc_call_nullable_values_batch_adaptive(client, rpc_urls, method, &hashes[mid..])
                    .with_context(|| {
                        format!(
                            "failed split JSON-RPC batch {method} right half after original error: {error:#}"
                        )
                    })?;
            left.append(&mut right);
            Ok(left)
        }
        Err(error) => Err(error),
    }
}

fn rpc_call_nullable_values_batch_from_pool(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    method: &str,
    hashes: &[String],
) -> Result<Vec<Value>> {
    let mut last_error = None;
    for _ in 0..rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_call_nullable_values_batch(client, rpc_url, method, hashes) {
            Ok(values) => return Ok(values),
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow::anyhow!("RPC pool has no URLs")))
}

fn rpc_call_nullable_values_batch(
    client: &Client,
    rpc_url: &str,
    method: &str,
    hashes: &[String],
) -> Result<Vec<Value>> {
    let body = hashes
        .iter()
        .enumerate()
        .map(|(id, hash)| {
            json!({
                "jsonrpc": "2.0",
                "id": id as u64,
                "method": method,
                "params": [hash],
            })
        })
        .collect::<Vec<_>>();

    let response = client
        .post(rpc_url)
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .with_context(|| format!("failed RPC batch request {method}"))?;
    let status = response.status();
    let text = response
        .text()
        .context("failed to read RPC batch response")?;
    if !status.is_success() {
        anyhow::bail!("RPC batch request {method} failed with status {status}: {text}");
    }

    let response: Value = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse RPC batch response: {text}"))?;
    parse_rpc_batch_response(method, hashes.len(), response)
}

fn parse_rpc_batch_response(
    method: &str,
    expected_len: usize,
    response: Value,
) -> Result<Vec<Value>> {
    let items = response
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("RPC batch response from {method} was not an array"))?;
    if items.len() != expected_len {
        anyhow::bail!(
            "RPC batch response from {method} length mismatch: got {}, expected {}",
            items.len(),
            expected_len
        );
    }

    let mut results = vec![None; expected_len];
    for item in items {
        let id =
            item.get("id").and_then(|id| id.as_u64()).ok_or_else(|| {
                anyhow::anyhow!("RPC batch response from {method} missing numeric id")
            })? as usize;
        if id >= expected_len {
            anyhow::bail!("RPC batch response from {method} had out-of-range id {id}");
        }
        if results[id].is_some() {
            anyhow::bail!("RPC batch response from {method} had duplicate id {id}");
        }
        if let Some(error) = item.get("error") {
            anyhow::bail!("RPC batch error from {method} id {id}: {error}");
        }
        results[id] = Some(item.get("result").cloned().unwrap_or(Value::Null));
    }

    results
        .into_iter()
        .enumerate()
        .map(|(id, value)| {
            value.ok_or_else(|| anyhow::anyhow!("RPC batch response from {method} missing id {id}"))
        })
        .collect()
}

fn receipt_row_from_rpc_values(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    hash: &str,
    fetched_at: &str,
    timestamp_source: TimestampSource,
    local_metadata: Option<&SourceTxMetadata>,
    event_header_timestamps: &BTreeMap<u64, (u64, String)>,
    timestamp_cache: &mut BTreeMap<u64, (u64, String)>,
    receipt_value: Value,
    tx_value: Value,
    transaction_fetch_skipped: bool,
) -> Result<ReceiptRow> {
    let receipt = if receipt_value.is_null() {
        None
    } else {
        Some(serde_json::from_value::<RpcReceipt>(receipt_value)?)
    };
    let transaction = if tx_value.is_null() {
        None
    } else {
        Some(serde_json::from_value::<RpcTransaction>(tx_value)?)
    };

    let block_number = receipt
        .as_ref()
        .and_then(|receipt| receipt.block_number.as_deref())
        .or_else(|| {
            transaction
                .as_ref()
                .and_then(|tx| tx.block_number.as_deref())
        })
        .map(parse_hex_u64)
        .transpose()?;
    let (block_timestamp, block_datetime_utc, dt) = resolve_block_time(
        block_number,
        fetched_at,
        timestamp_source,
        local_metadata,
        event_header_timestamps,
        timestamp_cache,
        |block_number| {
            fetch_block_timestamp_from_pool(client, rpc_urls, block_number)
                .with_context(|| format!("failed to fetch timestamp for block {block_number}"))
        },
    )?;

    let request_status = match (&receipt, &transaction, transaction_fetch_skipped) {
        (Some(_), _, true) => "receipt_only",
        (None, _, true) => "missing_receipt",
        (Some(_), Some(_), false) => "completed",
        (None, Some(_), false) => "missing_receipt",
        (Some(_), None, false) => "missing_transaction",
        (None, None, false) => "missing",
    };
    let transaction_hash = receipt
        .as_ref()
        .map(|receipt| receipt.transaction_hash.clone())
        .or_else(|| transaction.as_ref().map(|tx| tx.hash.clone()))
        .unwrap_or_else(|| hash.to_string());
    let block_hash = receipt
        .as_ref()
        .and_then(|receipt| receipt.block_hash.clone())
        .or_else(|| transaction.as_ref().and_then(|tx| tx.block_hash.clone()))
        .unwrap_or_default();
    let transaction_index = receipt
        .as_ref()
        .and_then(|receipt| receipt.transaction_index.as_deref())
        .or_else(|| {
            transaction
                .as_ref()
                .and_then(|tx| tx.transaction_index.as_deref())
        })
        .map(parse_hex_u64)
        .transpose()?;

    Ok(ReceiptRow {
        fetched_at_utc: fetched_at.to_string(),
        transaction_hash,
        request_status: request_status.to_string(),
        error: String::new(),
        block_number,
        block_hash,
        block_timestamp,
        block_datetime_utc,
        transaction_index,
        from_address: receipt
            .as_ref()
            .and_then(|receipt| receipt.from.clone())
            .or_else(|| transaction.as_ref().and_then(|tx| tx.from.clone()))
            .unwrap_or_default(),
        to_address: receipt
            .as_ref()
            .and_then(|receipt| receipt.to.clone())
            .or_else(|| transaction.as_ref().and_then(|tx| tx.to.clone()))
            .unwrap_or_default(),
        contract_address: receipt
            .as_ref()
            .and_then(|receipt| receipt.contract_address.clone())
            .unwrap_or_default(),
        receipt_status: receipt
            .as_ref()
            .and_then(|receipt| receipt.status.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        gas_used: receipt
            .as_ref()
            .and_then(|receipt| receipt.gas_used.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        cumulative_gas_used: receipt
            .as_ref()
            .and_then(|receipt| receipt.cumulative_gas_used.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        effective_gas_price: receipt
            .as_ref()
            .and_then(|receipt| receipt.effective_gas_price.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        tx_type: receipt
            .as_ref()
            .and_then(|receipt| receipt.tx_type.clone())
            .or_else(|| transaction.as_ref().and_then(|tx| tx.tx_type.clone()))
            .unwrap_or_default(),
        nonce: transaction
            .as_ref()
            .and_then(|tx| tx.nonce.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        gas: transaction
            .as_ref()
            .and_then(|tx| tx.gas.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        gas_price: transaction
            .as_ref()
            .and_then(|tx| tx.gas_price.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        max_fee_per_gas: transaction
            .as_ref()
            .and_then(|tx| tx.max_fee_per_gas.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        max_priority_fee_per_gas: transaction
            .as_ref()
            .and_then(|tx| tx.max_priority_fee_per_gas.as_deref())
            .map(parse_hex_u64)
            .transpose()?,
        value_raw: transaction
            .as_ref()
            .and_then(|tx| tx.value.clone())
            .unwrap_or_default(),
        input: transaction
            .as_ref()
            .and_then(|tx| tx.input.clone())
            .unwrap_or_default(),
        logs_count: receipt
            .as_ref()
            .and_then(|receipt| receipt.logs.as_ref().map(|logs| logs.len() as u64)),
        dt,
    })
}

fn resolve_block_time<F>(
    block_number: Option<u64>,
    fetched_at: &str,
    timestamp_source: TimestampSource,
    local_metadata: Option<&SourceTxMetadata>,
    event_header_timestamps: &BTreeMap<u64, (u64, String)>,
    timestamp_cache: &mut BTreeMap<u64, (u64, String)>,
    mut fetch_timestamp: F,
) -> Result<(Option<u64>, String, String)>
where
    F: FnMut(u64) -> Result<u64>,
{
    let Some(block_number) = block_number else {
        return Ok((None, String::new(), dt_from_utc_string(fetched_at)));
    };

    if let Some(cached) = timestamp_cache.get(&block_number) {
        let (timestamp, datetime) = cached.clone();
        return Ok((Some(timestamp), datetime, dt_from_timestamp(timestamp)?));
    }

    if timestamp_source == TimestampSource::LocalFirst {
        if let Some(timestamp) = local_metadata
            .filter(|metadata| {
                metadata
                    .block_number
                    .map_or(true, |local_block| local_block == block_number)
            })
            .and_then(|metadata| metadata.block_timestamp)
            .filter(|timestamp| *timestamp > 0)
        {
            let datetime = utc_from_timestamp(timestamp)?;
            timestamp_cache.insert(block_number, (timestamp, datetime.clone()));
            return Ok((Some(timestamp), datetime, dt_from_timestamp(timestamp)?));
        }

        if let Some((timestamp, datetime)) = event_header_timestamps.get(&block_number) {
            timestamp_cache.insert(block_number, (*timestamp, datetime.clone()));
            return Ok((
                Some(*timestamp),
                datetime.clone(),
                dt_from_timestamp(*timestamp)?,
            ));
        }
    }

    let timestamp = fetch_timestamp(block_number)?;
    let datetime = utc_from_timestamp(timestamp)?;
    timestamp_cache.insert(block_number, (timestamp, datetime.clone()));
    Ok((Some(timestamp), datetime, dt_from_timestamp(timestamp)?))
}

fn receipt_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, true),
        Field::new("block_hash", DataType::Utf8, false),
        Field::new("block_timestamp", DataType::UInt64, true),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, true),
        Field::new("from_address", DataType::Utf8, false),
        Field::new("to_address", DataType::Utf8, false),
        Field::new("contract_address", DataType::Utf8, false),
        Field::new("receipt_status", DataType::UInt64, true),
        Field::new("gas_used", DataType::UInt64, true),
        Field::new("cumulative_gas_used", DataType::UInt64, true),
        Field::new("effective_gas_price", DataType::UInt64, true),
        Field::new("tx_type", DataType::Utf8, false),
        Field::new("nonce", DataType::UInt64, true),
        Field::new("gas", DataType::UInt64, true),
        Field::new("gas_price", DataType::UInt64, true),
        Field::new("max_fee_per_gas", DataType::UInt64, true),
        Field::new("max_priority_fee_per_gas", DataType::UInt64, true),
        Field::new("value_raw", DataType::Utf8, false),
        Field::new("input", DataType::Utf8, false),
        Field::new("logs_count", DataType::UInt64, true),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn write_receipt_parts(
    data_root: &std::path::Path,
    schema: SchemaRef,
    rows: &[ReceiptRow],
    batch_hashes: &[String],
) -> Result<Vec<PartWrite>> {
    let mut by_dt = BTreeMap::<String, Vec<ReceiptRow>>::new();
    for row in rows {
        by_dt.entry(row.dt.clone()).or_default().push(row.clone());
    }

    let batch_id = deterministic_list_id(batch_hashes);
    let mut parts = Vec::new();
    for (dt, rows) in by_dt {
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.fetched_at_utc.clone())
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
                        .map(|row| row.request_status.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(&rows.iter().map(|row| row.error.clone()).collect::<Vec<_>>()),
                opt_u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.block_hash.clone())
                        .collect::<Vec<_>>(),
                ),
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.block_timestamp)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.block_datetime_utc.clone())
                        .collect::<Vec<_>>(),
                ),
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.transaction_index)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.from_address.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.to_address.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.contract_address.clone())
                        .collect::<Vec<_>>(),
                ),
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.receipt_status)
                        .collect::<Vec<_>>(),
                ),
                opt_u64_array(&rows.iter().map(|row| row.gas_used).collect::<Vec<_>>()),
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.cumulative_gas_used)
                        .collect::<Vec<_>>(),
                ),
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.effective_gas_price)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.tx_type.clone())
                        .collect::<Vec<_>>(),
                ),
                opt_u64_array(&rows.iter().map(|row| row.nonce).collect::<Vec<_>>()),
                opt_u64_array(&rows.iter().map(|row| row.gas).collect::<Vec<_>>()),
                opt_u64_array(&rows.iter().map(|row| row.gas_price).collect::<Vec<_>>()),
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.max_fee_per_gas)
                        .collect::<Vec<_>>(),
                ),
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.max_priority_fee_per_gas)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.value_raw.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(&rows.iter().map(|row| row.input.clone()).collect::<Vec<_>>()),
                opt_u64_array(&rows.iter().map(|row| row.logs_count).collect::<Vec<_>>()),
                string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
            ],
        )?;
        let stem = format!("{COLLECTOR}_{batch_id}");
        parts.push(write_parquet_part(
            &custom_part_path(data_root, DATASET, &dt, &stem),
            schema.clone(),
            batch,
        )?);
    }
    Ok(parts)
}

fn uint64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a UInt64Array> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .ok_or_else(|| anyhow::anyhow!("column {name} is not uint64"))
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
        .ok_or_else(|| anyhow::anyhow!("column {name} is not utf8"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_local_alchemy_rpc_value() {
        let body = r#"
            # ignored
            CHOG_DATA_ROOT="data/chog/v1"
            export ALCHEMY_RPC="https://private.example/rpc"
        "#;
        assert_eq!(
            parse_env_value(body, "ALCHEMY_RPC"),
            Some("https://private.example/rpc".to_string())
        );
    }

    #[test]
    fn parses_unquoted_env_value_before_comment() {
        let body = "ALCHEMY_RPC=https://private.example/rpc # local only";
        assert_eq!(
            parse_env_value(body, "ALCHEMY_RPC"),
            Some("https://private.example/rpc".to_string())
        );
    }

    #[test]
    fn push_rpc_values_splits_and_dedupes() {
        let mut values = vec!["https://first.example".to_string()];
        push_unique_rpc_values(&mut values, "https://first.example, https://second.example");
        assert_eq!(
            values,
            vec![
                "https://first.example".to_string(),
                "https://second.example".to_string()
            ]
        );
    }

    #[test]
    fn chog_pool_scope_reads_only_swap_datasets() {
        assert_eq!(
            source_datasets_for_scope(SourceScope::ChogPoolTxs),
            &["main_pool_swap_logs", "dex_pool_swap_logs"]
        );
        assert_eq!(
            source_datasets_for_scope(SourceScope::MainPool),
            &["main_pool_swap_logs"]
        );
        assert_eq!(
            source_datasets_for_scope(SourceScope::AllToken),
            &[
                "erc20_transfer_logs",
                "main_pool_swap_logs",
                "dex_pool_swap_logs"
            ]
        );
    }

    #[test]
    fn local_first_timestamp_uses_local_metadata_without_rpc_fallback() {
        let mut calls = 0usize;
        let mut cache = BTreeMap::new();
        let metadata = SourceTxMetadata {
            block_number: Some(10),
            block_timestamp: Some(1_778_112_345),
        };
        let (timestamp, datetime, dt) = resolve_block_time(
            Some(10),
            "2026-05-07T00:00:00Z",
            TimestampSource::LocalFirst,
            Some(&metadata),
            &BTreeMap::new(),
            &mut cache,
            |_| {
                calls += 1;
                Ok(1)
            },
        )
        .unwrap();
        assert_eq!(timestamp, Some(1_778_112_345));
        assert!(datetime.ends_with('Z'));
        assert_eq!(dt, "2026-05-07");
        assert_eq!(calls, 0);
    }

    #[test]
    fn rpc_only_timestamp_ignores_local_metadata() {
        let mut calls = 0usize;
        let mut cache = BTreeMap::new();
        let metadata = SourceTxMetadata {
            block_number: Some(10),
            block_timestamp: Some(1_778_112_345),
        };
        let (timestamp, _datetime, _dt) = resolve_block_time(
            Some(10),
            "2026-05-07T00:00:00Z",
            TimestampSource::RpcOnly,
            Some(&metadata),
            &BTreeMap::new(),
            &mut cache,
            |_| {
                calls += 1;
                Ok(1_778_112_400)
            },
        )
        .unwrap();
        assert_eq!(timestamp, Some(1_778_112_400));
        assert_eq!(calls, 1);
    }

    #[test]
    fn parses_rpc_batch_response_by_id_order() {
        let values = parse_rpc_batch_response(
            "eth_test",
            2,
            json!([
                {"jsonrpc": "2.0", "id": 1, "result": "second"},
                {"jsonrpc": "2.0", "id": 0, "result": null}
            ]),
        )
        .unwrap();
        assert!(values[0].is_null());
        assert_eq!(values[1], json!("second"));
    }

    #[test]
    fn receipt_only_row_uses_receipt_fields_without_transaction_body() {
        let client = Client::new();
        let rpc_urls =
            RpcUrlPool::from_values(&["https://example.invalid".to_string()], DEFAULT_RPC_URL)
                .unwrap();
        let metadata = SourceTxMetadata {
            block_number: Some(10),
            block_timestamp: Some(1_778_112_345),
        };
        let mut cache = BTreeMap::new();
        let row = receipt_row_from_rpc_values(
            &client,
            &rpc_urls,
            "0xabc",
            "2026-05-07T00:00:00Z",
            TimestampSource::LocalFirst,
            Some(&metadata),
            &BTreeMap::new(),
            &mut cache,
            json!({
                "transactionHash": "0xabc",
                "transactionIndex": "0x1",
                "blockHash": "0xblock",
                "blockNumber": "0xa",
                "from": "0xfrom",
                "to": "0xto",
                "cumulativeGasUsed": "0x20",
                "gasUsed": "0x10",
                "contractAddress": null,
                "logs": [],
                "status": "0x1",
                "effectiveGasPrice": "0x64",
                "type": "0x2"
            }),
            Value::Null,
            true,
        )
        .unwrap();

        assert_eq!(row.request_status, "receipt_only");
        assert_eq!(row.transaction_hash, "0xabc");
        assert_eq!(row.block_number, Some(10));
        assert_eq!(row.receipt_status, Some(1));
        assert_eq!(row.gas_used, Some(16));
        assert_eq!(row.effective_gas_price, Some(100));
        assert_eq!(row.nonce, None);
    }
}

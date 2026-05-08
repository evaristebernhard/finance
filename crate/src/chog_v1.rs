use std::collections::BTreeSet;
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{
    Array, ArrayRef, BooleanBuilder, Float64Builder, Int64Builder, StringArray, StringBuilder,
    UInt64Builder,
};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, SecondsFormat, Utc};
use clap::ValueEnum;
use parquet::arrow::ArrowWriter;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::file::properties::WriterProperties;
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::{RpcUrlPool, parse_hex_u64, rpc_call, rpc_call_from_pool, to_hex};

pub const DEFAULT_DATA_ROOT: &str = "data/chog/v1";
pub const RAW_DIR: &str = "raw";
pub const CHECKPOINT_DIR: &str = "_checkpoints";
pub const SCHEMA_DIR: &str = "_schemas";
pub const COLLECTION_RUNS_DATASET: &str = "collection_runs";
pub const MAX_RPC_LOG_RANGE: u64 = 100;

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
pub enum OutputFormat {
    Csv,
    Parquet,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PartWriteStatus {
    Written,
    Skipped,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PartWrite {
    pub path: PathBuf,
    pub rows: usize,
    pub status: PartWriteStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChogCollectionRunRecord {
    pub collector: String,
    pub mode: String,
    pub dataset: String,
    pub chain: String,
    pub address: String,
    pub topic0: String,
    pub from_block: Option<u64>,
    pub to_block: Option<u64>,
    pub time_window_start_utc: String,
    pub time_window_end_utc: String,
    pub output_parts: String,
    pub rows_written: u64,
    pub chunks_completed: u64,
    pub status: String,
    pub error: String,
    pub started_at_utc: String,
    pub finished_at_utc: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct DatasetSchemaFile {
    version: u32,
    dataset: String,
    format: String,
    partition_columns: Vec<String>,
    fields: Vec<DatasetField>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct DatasetField {
    name: String,
    data_type: String,
    nullable: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RpcBlock {
    pub number: Option<String>,
    pub hash: Option<String>,
    pub parent_hash: Option<String>,
    pub timestamp: String,
    pub base_fee_per_gas: Option<String>,
    pub gas_used: String,
    pub gas_limit: String,
    pub miner: Option<String>,
    pub extra_data: Option<String>,
    #[serde(default)]
    pub transactions: Vec<Value>,
}

pub fn repo_root() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir.parent().unwrap_or(&manifest_dir).to_path_buf()
}

pub fn default_data_root_path() -> PathBuf {
    repo_root().join(DEFAULT_DATA_ROOT)
}

pub fn checkpoint_path(data_root: &Path, collector: &str) -> PathBuf {
    checkpoint_path_with_suffix(data_root, collector, None)
        .expect("collector checkpoint names are static and valid")
}

pub fn checkpoint_path_with_suffix(
    data_root: &Path,
    collector: &str,
    suffix: Option<&str>,
) -> Result<PathBuf> {
    let filename = if let Some(suffix) = suffix.map(str::trim).filter(|value| !value.is_empty()) {
        format!("{collector}--{}.json", safe_file_suffix(suffix)?)
    } else {
        format!("{collector}.json")
    };
    Ok(data_root.join(CHECKPOINT_DIR).join(filename))
}

pub fn schema_path(data_root: &Path, dataset: &str) -> PathBuf {
    data_root.join(SCHEMA_DIR).join(format!("{dataset}.json"))
}

pub fn partition_dir(data_root: &Path, dataset: &str, dt: &str) -> PathBuf {
    data_root
        .join(RAW_DIR)
        .join(dataset)
        .join(format!("dt={dt}"))
}

pub fn rpc_part_path(
    data_root: &Path,
    dataset: &str,
    dt: &str,
    collector: &str,
    from_block: u64,
    to_block: u64,
) -> PathBuf {
    partition_dir(data_root, dataset, dt).join(rpc_part_filename(collector, from_block, to_block))
}

pub fn rpc_part_filename(collector: &str, from_block: u64, to_block: u64) -> String {
    format!("{collector}_{from_block}_{to_block}.parquet")
}

pub fn snapshot_part_path(
    data_root: &Path,
    dataset: &str,
    dt: &str,
    collector: &str,
    captured_at_utc: &str,
) -> PathBuf {
    partition_dir(data_root, dataset, dt).join(snapshot_part_filename(collector, captured_at_utc))
}

pub fn snapshot_part_filename(collector: &str, captured_at_utc: &str) -> String {
    format!(
        "{}_{}.parquet",
        collector,
        safe_timestamp_for_filename(captured_at_utc)
    )
}

pub fn custom_part_path(data_root: &Path, dataset: &str, dt: &str, part_stem: &str) -> PathBuf {
    partition_dir(data_root, dataset, dt).join(format!("{part_stem}.parquet"))
}

pub fn dt_from_timestamp(timestamp: u64) -> Result<String> {
    Ok(DateTime::<Utc>::from_timestamp(timestamp as i64, 0)
        .ok_or_else(|| anyhow!("invalid block timestamp {timestamp}"))?
        .format("%Y-%m-%d")
        .to_string())
}

pub fn dt_from_utc_string(value: &str) -> String {
    value.get(..10).unwrap_or("unknown").to_string()
}

pub fn utc_from_timestamp(timestamp: u64) -> Result<String> {
    Ok(DateTime::<Utc>::from_timestamp(timestamp as i64, 0)
        .ok_or_else(|| anyhow!("invalid block timestamp {timestamp}"))?
        .to_rfc3339_opts(SecondsFormat::Secs, true))
}

pub fn safe_timestamp_for_filename(value: &str) -> String {
    value
        .chars()
        .map(|ch| match ch {
            'A'..='Z' | 'a'..='z' | '0'..='9' | '-' | '_' => ch,
            ':' => '-',
            _ => '_',
        })
        .collect()
}

pub fn safe_file_suffix(value: &str) -> Result<String> {
    let suffix = value.trim();
    if suffix.is_empty() {
        bail!("checkpoint suffix cannot be empty");
    }
    if suffix.len() > 120 {
        bail!("checkpoint suffix is too long");
    }
    if !suffix
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.'))
    {
        bail!("checkpoint suffix may only contain ASCII letters, digits, '.', '-' and '_'");
    }
    Ok(suffix.to_string())
}

pub fn ensure_parent_dir(path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    Ok(())
}

pub fn write_schema_metadata(
    data_root: &Path,
    dataset: &str,
    schema: &Schema,
    partition_columns: &[&str],
) -> Result<()> {
    let path = schema_path(data_root, dataset);
    let next = DatasetSchemaFile {
        version: 1,
        dataset: dataset.to_string(),
        format: "parquet".to_string(),
        partition_columns: partition_columns
            .iter()
            .map(|value| value.to_string())
            .collect(),
        fields: schema
            .fields()
            .iter()
            .map(|field| DatasetField {
                name: field.name().to_string(),
                data_type: data_type_name(field.data_type()),
                nullable: field.is_nullable(),
            })
            .collect(),
    };

    if path.exists() {
        let existing: DatasetSchemaFile = serde_json::from_reader(
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?,
        )
        .with_context(|| format!("failed to parse {}", path.display()))?;
        if existing != next {
            bail!(
                "schema metadata conflict for dataset {dataset}: existing {} differs from generated schema",
                path.display()
            );
        }
        return Ok(());
    }

    ensure_parent_dir(&path)?;
    let file =
        File::create(&path).with_context(|| format!("failed to create {}", path.display()))?;
    serde_json::to_writer_pretty(file, &next)
        .with_context(|| format!("failed to write {}", path.display()))
}

pub fn write_parquet_part(path: &Path, schema: SchemaRef, batch: RecordBatch) -> Result<PartWrite> {
    if schema.fields().len() != batch.num_columns() {
        bail!(
            "schema has {} fields but batch has {} columns for {}",
            schema.fields().len(),
            batch.num_columns(),
            path.display()
        );
    }

    ensure_parent_dir(path)?;
    let temp_path = temp_path_for(path);
    {
        let file = File::create(&temp_path)
            .with_context(|| format!("failed to create temp part {}", temp_path.display()))?;
        let props = WriterProperties::builder()
            .set_created_by("finance-chain-chog-v1".to_string())
            .build();
        let mut writer = ArrowWriter::try_new(file, schema, Some(props))
            .with_context(|| format!("failed to create parquet writer for {}", path.display()))?;
        writer
            .write(&batch)
            .with_context(|| format!("failed to write parquet batch {}", path.display()))?;
        writer
            .close()
            .with_context(|| format!("failed to close parquet writer {}", path.display()))?;
    }

    if path.exists() {
        let expected = fs::read(&temp_path)
            .with_context(|| format!("failed to read temp part {}", temp_path.display()))?;
        let existing =
            fs::read(path).with_context(|| format!("failed to read part {}", path.display()))?;
        fs::remove_file(&temp_path)
            .with_context(|| format!("failed to remove temp part {}", temp_path.display()))?;
        if existing == expected {
            return Ok(PartWrite {
                path: path.to_path_buf(),
                rows: batch.num_rows(),
                status: PartWriteStatus::Skipped,
            });
        }
        bail!(
            "existing parquet part conflicts with generated part: {}",
            path.display()
        );
    }

    fs::rename(&temp_path, path).with_context(|| {
        format!(
            "failed to atomically move {} to {}",
            temp_path.display(),
            path.display()
        )
    })?;

    Ok(PartWrite {
        path: path.to_path_buf(),
        rows: batch.num_rows(),
        status: PartWriteStatus::Written,
    })
}

pub fn string_array(values: &[String]) -> ArrayRef {
    let bytes = values.iter().map(String::len).sum();
    let mut builder = StringBuilder::with_capacity(values.len(), bytes);
    for value in values {
        builder.append_value(value);
    }
    Arc::new(builder.finish())
}

pub fn opt_string_array(values: &[Option<String>]) -> ArrayRef {
    let bytes = values
        .iter()
        .filter_map(|value| value.as_ref().map(String::len))
        .sum();
    let mut builder = StringBuilder::with_capacity(values.len(), bytes);
    for value in values {
        match value {
            Some(value) => builder.append_value(value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

pub fn u64_array(values: &[u64]) -> ArrayRef {
    let mut builder = UInt64Builder::with_capacity(values.len());
    for value in values {
        builder.append_value(*value);
    }
    Arc::new(builder.finish())
}

pub fn opt_u64_array(values: &[Option<u64>]) -> ArrayRef {
    let mut builder = UInt64Builder::with_capacity(values.len());
    for value in values {
        match value {
            Some(value) => builder.append_value(*value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

pub fn i64_array(values: &[i64]) -> ArrayRef {
    let mut builder = Int64Builder::with_capacity(values.len());
    for value in values {
        builder.append_value(*value);
    }
    Arc::new(builder.finish())
}

pub fn opt_i64_array(values: &[Option<i64>]) -> ArrayRef {
    let mut builder = Int64Builder::with_capacity(values.len());
    for value in values {
        match value {
            Some(value) => builder.append_value(*value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

pub fn f64_array(values: &[f64]) -> ArrayRef {
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        builder.append_value(*value);
    }
    Arc::new(builder.finish())
}

pub fn opt_f64_array(values: &[Option<f64>]) -> ArrayRef {
    let mut builder = Float64Builder::with_capacity(values.len());
    for value in values {
        match value {
            Some(value) => builder.append_value(*value),
            None => builder.append_null(),
        }
    }
    Arc::new(builder.finish())
}

pub fn bool_array(values: &[bool]) -> ArrayRef {
    let mut builder = BooleanBuilder::with_capacity(values.len());
    for value in values {
        builder.append_value(*value);
    }
    Arc::new(builder.finish())
}

pub fn collection_runs_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("collector", DataType::Utf8, false),
        Field::new("mode", DataType::Utf8, false),
        Field::new("dataset", DataType::Utf8, false),
        Field::new("chain", DataType::Utf8, false),
        Field::new("address", DataType::Utf8, false),
        Field::new("topic0", DataType::Utf8, false),
        Field::new("from_block", DataType::UInt64, true),
        Field::new("to_block", DataType::UInt64, true),
        Field::new("time_window_start_utc", DataType::Utf8, false),
        Field::new("time_window_end_utc", DataType::Utf8, false),
        Field::new("output_parts", DataType::Utf8, false),
        Field::new("rows_written", DataType::UInt64, false),
        Field::new("chunks_completed", DataType::UInt64, false),
        Field::new("status", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("started_at_utc", DataType::Utf8, false),
        Field::new("finished_at_utc", DataType::Utf8, false),
    ]))
}

pub fn write_collection_run_parquet(
    data_root: &Path,
    record: &ChogCollectionRunRecord,
) -> Result<PartWrite> {
    let schema = collection_runs_schema();
    write_schema_metadata(data_root, COLLECTION_RUNS_DATASET, schema.as_ref(), &["dt"])?;
    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![
            string_array(&[record.collector.clone()]),
            string_array(&[record.mode.clone()]),
            string_array(&[record.dataset.clone()]),
            string_array(&[record.chain.clone()]),
            string_array(&[record.address.clone()]),
            string_array(&[record.topic0.clone()]),
            opt_u64_array(&[record.from_block]),
            opt_u64_array(&[record.to_block]),
            string_array(&[record.time_window_start_utc.clone()]),
            string_array(&[record.time_window_end_utc.clone()]),
            string_array(&[record.output_parts.clone()]),
            u64_array(&[record.rows_written]),
            u64_array(&[record.chunks_completed]),
            string_array(&[record.status.clone()]),
            string_array(&[record.error.clone()]),
            string_array(&[record.started_at_utc.clone()]),
            string_array(&[record.finished_at_utc.clone()]),
        ],
    )?;
    let dt = dt_from_utc_string(&record.started_at_utc);
    let range = match (record.from_block, record.to_block) {
        (Some(from_block), Some(to_block)) => format!("_{from_block}_{to_block}"),
        _ => String::new(),
    };
    let stem = format!(
        "collection_runs_{}{}_{}_{}",
        record.collector,
        range,
        safe_timestamp_for_filename(&record.started_at_utc),
        safe_timestamp_for_filename(&record.finished_at_utc)
    );
    write_parquet_part(
        &custom_part_path(data_root, COLLECTION_RUNS_DATASET, &dt, &stem),
        schema,
        batch,
    )
}

pub fn rpc_call_nullable_value(
    client: &Client,
    rpc_url: &str,
    method: &str,
    params: Value,
) -> Result<Value> {
    let body = json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    });

    let response = client
        .post(rpc_url)
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .with_context(|| format!("failed RPC request {method}"))?;
    let status = response.status();
    let text = response.text().context("failed to read RPC response")?;
    if !status.is_success() {
        bail!("RPC request {method} failed with status {status}: {text}");
    }

    let response: Value = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse RPC response: {text}"))?;
    if let Some(error) = response.get("error") {
        bail!("RPC error from {method}: {error}");
    }
    Ok(response.get("result").cloned().unwrap_or(Value::Null))
}

pub fn rpc_call_nullable_value_from_pool(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    method: &str,
    params: Value,
) -> Result<Value> {
    let mut last_error = None;
    for _ in 0..rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_call_nullable_value(client, rpc_url, method, params.clone()) {
            Ok(value) => return Ok(value),
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("RPC pool has no URLs")))
}

pub fn fetch_block_by_number(
    client: &Client,
    rpc_url: &str,
    block_number: u64,
) -> Result<RpcBlock> {
    let block: Option<RpcBlock> = rpc_call(
        client,
        rpc_url,
        "eth_getBlockByNumber",
        json!([to_hex(block_number), false]),
    )?;
    block.ok_or_else(|| anyhow!("block {block_number} not found"))
}

pub fn fetch_block_timestamp(client: &Client, rpc_url: &str, block_number: u64) -> Result<u64> {
    let block = fetch_block_by_number(client, rpc_url, block_number)?;
    parse_hex_u64(&block.timestamp)
}

pub fn fetch_block_timestamp_from_pool(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    block_number: u64,
) -> Result<u64> {
    let block: Option<RpcBlock> = rpc_call_from_pool(
        client,
        rpc_urls,
        "eth_getBlockByNumber",
        json!([to_hex(block_number), false]),
    )?;
    let block = block.ok_or_else(|| anyhow!("block {block_number} not found"))?;
    parse_hex_u64(&block.timestamp)
}

pub fn find_block_at_or_before_timestamp(
    client: &Client,
    rpc_url: &str,
    target_timestamp: u64,
    latest_block: u64,
) -> Result<u64> {
    let latest_timestamp = fetch_block_timestamp(client, rpc_url, latest_block)?;
    if latest_timestamp <= target_timestamp {
        return Ok(latest_block);
    }

    let mut low = 0u64;
    let mut high = latest_block;
    while low < high {
        let mid = low + (high - low).div_ceil(2);
        let mid_timestamp = fetch_block_timestamp(client, rpc_url, mid)
            .with_context(|| format!("failed timestamp lookup for block {mid}"))?;
        if mid_timestamp <= target_timestamp {
            low = mid;
        } else {
            high = mid - 1;
        }
    }
    Ok(low)
}

pub fn parquet_files_under(root: &Path) -> Result<Vec<PathBuf>> {
    let mut files = Vec::new();
    if !root.exists() {
        return Ok(files);
    }
    collect_parquet_files(root, &mut files)?;
    files.sort();
    Ok(files)
}

pub fn read_string_column_from_parquet(path: &Path, column_name: &str) -> Result<Vec<String>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(1024)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    let mut values = Vec::new();
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let index = batch
            .schema()
            .index_of(column_name)
            .with_context(|| format!("missing column {column_name} in {}", path.display()))?;
        let column = batch.column(index);
        let strings = column
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| {
                anyhow!(
                    "column {column_name} is not utf8 in parquet file {}",
                    path.display()
                )
            })?;
        for index in 0..strings.len() {
            if !strings.is_null(index) {
                values.push(strings.value(index).to_string());
            }
        }
    }
    Ok(values)
}

pub fn unique_tx_hashes_from_datasets(data_root: &Path, datasets: &[&str]) -> Result<Vec<String>> {
    let mut hashes = BTreeSet::new();
    for dataset in datasets {
        let root = data_root.join(RAW_DIR).join(dataset);
        for path in parquet_files_under(&root)? {
            for hash in read_string_column_from_parquet(&path, "transaction_hash")? {
                hashes.insert(hash);
            }
        }
    }
    Ok(hashes.into_iter().collect())
}

pub fn deterministic_list_id(values: &[String]) -> String {
    let mut hash = 0xcbf29ce484222325u64;
    for value in values {
        for byte in value.as_bytes().iter().copied().chain([0xff]) {
            hash ^= u64::from(byte);
            hash = hash.wrapping_mul(0x100000001b3);
        }
    }
    format!("{hash:016x}")
}

pub fn part_paths_to_string(parts: &[PartWrite]) -> String {
    parts
        .iter()
        .map(|part| part.path.display().to_string())
        .collect::<Vec<_>>()
        .join("|")
}

fn collect_parquet_files(root: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
    for entry in fs::read_dir(root).with_context(|| format!("failed to read {}", root.display()))? {
        let entry = entry.with_context(|| format!("failed to read entry in {}", root.display()))?;
        let path = entry.path();
        if path.is_dir() {
            collect_parquet_files(&path, files)?;
        } else if path.extension().and_then(|value| value.to_str()) == Some("parquet") {
            files.push(path);
        }
    }
    Ok(())
}

fn temp_path_for(path: &Path) -> PathBuf {
    let filename = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("part.parquet");
    let nonce = Utc::now()
        .timestamp_nanos_opt()
        .unwrap_or_else(|| Utc::now().timestamp_micros());
    path.with_file_name(format!(".{filename}.tmp.{}.{}", std::process::id(), nonce))
}

fn data_type_name(data_type: &DataType) -> String {
    match data_type {
        DataType::Utf8 => "utf8".to_string(),
        DataType::UInt64 => "uint64".to_string(),
        DataType::Int64 => "int64".to_string(),
        DataType::Float64 => "float64".to_string(),
        DataType::Boolean => "boolean".to_string(),
        other => format!("{other:?}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_partition_and_rpc_part_paths() {
        let root = PathBuf::from("/tmp/chog-v1");
        let path = rpc_part_path(
            &root,
            "erc20_transfer_logs",
            "2026-05-07",
            "transfer_sample",
            100,
            199,
        );
        assert_eq!(
            path,
            PathBuf::from(
                "/tmp/chog-v1/raw/erc20_transfer_logs/dt=2026-05-07/transfer_sample_100_199.parquet"
            )
        );
    }

    #[test]
    fn writes_and_reads_parquet_string_column() {
        let root = temp_root("parquet_roundtrip");
        let dataset = "test_dataset";
        let schema = Arc::new(Schema::new(vec![
            Field::new("transaction_hash", DataType::Utf8, false),
            Field::new("block_number", DataType::UInt64, false),
        ]));
        write_schema_metadata(&root, dataset, schema.as_ref(), &["dt"]).unwrap();
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                string_array(&["0xa".to_string(), "0xb".to_string()]),
                u64_array(&[1, 2]),
            ],
        )
        .unwrap();
        let part = custom_part_path(&root, dataset, "2026-05-07", "test_part");
        let write = write_parquet_part(&part, schema, batch).unwrap();
        assert_eq!(write.status, PartWriteStatus::Written);

        let values = read_string_column_from_parquet(&part, "transaction_hash").unwrap();
        assert_eq!(values, vec!["0xa".to_string(), "0xb".to_string()]);

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn deterministic_list_id_is_order_sensitive_and_stable() {
        let values = vec!["0xa".to_string(), "0xb".to_string()];
        assert_eq!(
            deterministic_list_id(&values),
            deterministic_list_id(&values)
        );
        assert_ne!(
            deterministic_list_id(&values),
            deterministic_list_id(&["0xb".to_string(), "0xa".to_string()])
        );
    }

    fn temp_root(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "finance_chain_chog_v1_{}_{}_{}",
            std::process::id(),
            Utc::now()
                .timestamp_nanos_opt()
                .unwrap_or_else(|| Utc::now().timestamp_micros()),
            name
        ))
    }
}

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow};
use arrow::array::{Array, BooleanArray, Float64Array, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use finance_chain_core::amm::{
    LB_V22_SWAP_TOPIC, PANCAKE_V3_SWAP_TOPIC, V2_SWAP_TOPIC, V3_SWAP_TOPIC,
};
use finance_chain_core::parse_hex_u64;
use finance_chain_core::rpc::RpcReceipt;
use finance_chain_core::storage::{
    RAW_DIR, bool_array, custom_part_path, deterministic_list_id, dt_from_timestamp,
    dt_from_utc_string, opt_u64_array, parquet_files_under, read_string_column_from_parquet,
    string_array, u64_array, utc_from_timestamp, write_parquet_part, write_schema_metadata,
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tiny_keccak::{Hasher, Keccak};

use crate::{POOL_SWAP_LOGS_DATASET, known_top4_pools};

pub const TX_BODIES_DATASET: &str = "tx_bodies";
pub const TX_RECEIPT_LOGS_DATASET: &str = "tx_receipt_logs";
pub const TX_RECEIPT_LOG_SUMMARIES_DATASET: &str = "tx_receipt_log_summaries";
pub const POOL_STATE_SAMPLES_DATASET: &str = "pool_state_samples";
pub const POOL_LIQUIDITY_WINDOWS_DATASET: &str = "pool_liquidity_windows";
pub const DEBUG_TRACE_SUMMARIES_DATASET: &str = "debug_trace_summaries";
pub const DEBUG_TRACE_CALLS_DATASET: &str = "debug_trace_calls";

pub const ERC20_TRANSFER_TOPIC: &str =
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";

const WORK_DIR: &str = "_work";
const TX_QUEUE_CACHE_VERSION: u32 = 1;

#[derive(Debug, Clone, Default, PartialEq)]
pub struct TxSourceMetadata {
    pub block_number: Option<u64>,
    pub block_timestamp: Option<u64>,
    pub block_datetime_utc: String,
    pub transaction_index: Option<u64>,
    pub max_quote_abs: f64,
    pub swap_count: u64,
    pub pools: BTreeSet<String>,
    pub directions: BTreeSet<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TxQueueEntry {
    pub tx_hash: String,
    pub block_number: Option<u64>,
    pub transaction_index: Option<u64>,
    pub block_timestamp: Option<u64>,
    pub block_datetime_utc: String,
    pub dt: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TxQueueCacheStatus {
    Hit,
    Created,
    Refreshed,
}

impl TxQueueCacheStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Hit => "hit",
            Self::Created => "created",
            Self::Refreshed => "refreshed",
        }
    }
}

#[derive(Debug, Clone)]
pub struct TxBodyQueue {
    pub queue: Vec<String>,
    pub metadata: BTreeMap<String, TxSourceMetadata>,
    pub cache_path: PathBuf,
    pub cache_status: TxQueueCacheStatus,
    pub source_count: usize,
    pub existing_count: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SwapEventLite {
    pub block_number: u64,
    pub block_timestamp: u64,
    pub block_datetime_utc: String,
    pub transaction_hash: String,
    pub transaction_index: u64,
    pub log_index: u64,
    pub pool_address: String,
    pub dex_id: String,
    pub family: String,
    pub direction: String,
    pub base_abs: Option<f64>,
    pub quote_abs: Option<f64>,
    pub price_quote_per_base: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TxBodyRow {
    pub fetched_at_utc: String,
    pub transaction_hash: String,
    pub request_status: String,
    pub error: String,
    pub block_number: Option<u64>,
    pub block_timestamp: Option<u64>,
    pub block_datetime_utc: String,
    pub transaction_index: Option<u64>,
    pub from_address: String,
    pub to_address: String,
    pub nonce: Option<u64>,
    pub tx_type: String,
    pub value: String,
    pub gas: Option<u64>,
    pub gas_price: Option<u64>,
    pub max_fee_per_gas: Option<u64>,
    pub max_priority_fee_per_gas: Option<u64>,
    pub input_hex: String,
    pub input_len: u64,
    pub method_selector: String,
    pub dt: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReceiptLogRow {
    pub fetched_at_utc: String,
    pub transaction_hash: String,
    pub request_status: String,
    pub block_number: Option<u64>,
    pub block_timestamp: Option<u64>,
    pub block_datetime_utc: String,
    pub transaction_index: Option<u64>,
    pub log_index: Option<u64>,
    pub address: String,
    pub topic0: String,
    pub topics_json: String,
    pub data: String,
    pub removed: bool,
    pub dt: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReceiptLogSummaryRow {
    pub fetched_at_utc: String,
    pub transaction_hash: String,
    pub request_status: String,
    pub error: String,
    pub block_number: Option<u64>,
    pub block_timestamp: Option<u64>,
    pub block_datetime_utc: String,
    pub transaction_index: Option<u64>,
    pub logs_count: u64,
    pub mon_usdc_swap_log_count: u64,
    pub erc20_transfer_count: u64,
    pub pool_addresses_seen: String,
    pub dt: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PoolStateCandidate {
    pub event_block_number: u64,
    pub block_timestamp: u64,
    pub block_datetime_utc: String,
    pub pool_address: String,
    pub dex_id: String,
    pub family: String,
    pub direction: String,
    pub quote_abs: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PoolStateSampleRow {
    pub fetched_at_utc: String,
    pub event_block_number: u64,
    pub sample_block_number: u64,
    pub sample_side: String,
    pub pool_address: String,
    pub dex_id: String,
    pub family: String,
    pub request_status: String,
    pub error: String,
    pub sqrt_price_x96: String,
    pub tick: String,
    pub liquidity: String,
    pub tick_spacing: String,
    pub active_id: String,
    pub bin_step: String,
    pub active_bin_reserve_x: String,
    pub active_bin_reserve_y: String,
    pub dt: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PoolLiquidityWindowRow {
    pub fetched_at_utc: String,
    pub event_block_number: u64,
    pub sample_block_number: u64,
    pub pool_address: String,
    pub family: String,
    pub window_kind: String,
    pub offset: i64,
    pub tick_or_bin: String,
    pub request_status: String,
    pub error: String,
    pub liquidity_gross: String,
    pub liquidity_net: String,
    pub reserve_x: String,
    pub reserve_y: String,
    pub dt: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DebugTraceSummaryRow {
    pub fetched_at_utc: String,
    pub transaction_hash: String,
    pub request_status: String,
    pub error: String,
    pub block_number: Option<u64>,
    pub block_timestamp: Option<u64>,
    pub block_datetime_utc: String,
    pub call_count: u64,
    pub max_depth: u64,
    pub root_call_type: String,
    pub root_from: String,
    pub root_to: String,
    pub root_error: String,
    pub dt: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DebugTraceCallRow {
    pub fetched_at_utc: String,
    pub transaction_hash: String,
    pub request_status: String,
    pub depth: u64,
    pub trace_address: String,
    pub call_type: String,
    pub from_address: String,
    pub to_address: String,
    pub value: String,
    pub gas: Option<u64>,
    pub gas_used: Option<u64>,
    pub input_selector: String,
    pub error: String,
    pub revert_reason: String,
    pub dt: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceFlattenStats {
    pub call_count: u64,
    pub max_depth: u64,
    pub root_call_type: String,
    pub root_from: String,
    pub root_to: String,
    pub root_error: String,
}

pub fn stable_shard_index(value: &str, shard_count: usize) -> usize {
    let mut hash = 0xcbf29ce484222325u64;
    for byte in value.bytes() {
        hash ^= u64::from(byte.to_ascii_lowercase());
        hash = hash.wrapping_mul(0x100000001b3);
    }
    (hash % shard_count as u64) as usize
}

pub fn apply_stable_tx_shard(
    queue: Vec<String>,
    shard_index: Option<usize>,
    shard_count: Option<usize>,
) -> Result<Vec<String>> {
    if shard_index.is_some() != shard_count.is_some() {
        anyhow::bail!("--shard-index and --shard-count must be supplied together");
    }
    let Some(shard_index) = shard_index else {
        return Ok(queue);
    };
    let shard_count = shard_count.expect("checked with shard_index");
    if shard_count == 0 {
        anyhow::bail!("--shard-count must be greater than 0");
    }
    if shard_index >= shard_count {
        anyhow::bail!("--shard-index must be less than --shard-count");
    }
    Ok(queue
        .into_iter()
        .filter(|hash| stable_shard_index(hash, shard_count) == shard_index)
        .collect())
}

pub fn collect_swap_sources(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> Result<(
    Vec<String>,
    BTreeMap<String, TxSourceMetadata>,
    Vec<SwapEventLite>,
)> {
    let mut hashes = BTreeSet::<String>::new();
    let mut metadata = BTreeMap::<String, TxSourceMetadata>::new();
    let mut events = Vec::new();
    let root = data_root.join(RAW_DIR).join(POOL_SWAP_LOGS_DATASET);
    for path in parquet_files_under(&root)? {
        if !parquet_path_may_overlap_blocks(&path, from_block, to_block) {
            continue;
        }
        read_swap_sources_file(
            &path,
            from_block,
            to_block,
            &mut hashes,
            &mut metadata,
            &mut events,
        )?;
    }
    Ok((hashes.into_iter().collect(), metadata, events))
}

pub fn collect_tx_body_queue(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> Result<(Vec<String>, BTreeMap<String, TxSourceMetadata>)> {
    let (hashes, metadata, _) = collect_swap_sources(data_root, from_block, to_block)?;
    let existing = existing_tx_hashes(data_root, TX_BODIES_DATASET)?;
    let mut queue = hashes
        .into_iter()
        .filter(|hash| !existing.contains(hash))
        .collect::<Vec<_>>();
    sort_hash_queue_by_source(&mut queue, &metadata);
    Ok((queue, metadata))
}

pub fn collect_tx_body_queue_cached(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
    refresh_cache: bool,
) -> Result<TxBodyQueue> {
    let cache_path = tx_body_queue_cache_path(data_root, from_block, to_block);
    let (entries, cache_status) = if cache_path.exists() && !refresh_cache {
        (
            read_tx_queue_cache(&cache_path, from_block, to_block)
                .with_context(|| format!("failed to read queue cache {}", cache_path.display()))?,
            TxQueueCacheStatus::Hit,
        )
    } else {
        let (hashes, metadata, _) = collect_swap_sources(data_root, from_block, to_block)?;
        let entries = tx_queue_entries_from_sources(hashes, &metadata)?;
        write_tx_queue_cache(&cache_path, from_block, to_block, &entries)
            .with_context(|| format!("failed to write queue cache {}", cache_path.display()))?;
        (
            entries,
            if refresh_cache {
                TxQueueCacheStatus::Refreshed
            } else {
                TxQueueCacheStatus::Created
            },
        )
    };

    let source_count = entries.len();
    let metadata = tx_queue_metadata_from_entries(&entries);
    let existing = existing_tx_hashes(data_root, TX_BODIES_DATASET)?;
    let existing_count = existing.len();
    let mut queue = entries
        .into_iter()
        .map(|entry| entry.tx_hash)
        .filter(|hash| !existing.contains(hash))
        .collect::<Vec<_>>();
    sort_hash_queue_by_source(&mut queue, &metadata);
    Ok(TxBodyQueue {
        queue,
        metadata,
        cache_path,
        cache_status,
        source_count,
        existing_count,
    })
}

pub fn collect_receipt_log_bundle_queue(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> Result<(Vec<String>, BTreeMap<String, TxSourceMetadata>)> {
    let (hashes, metadata, _) = collect_swap_sources(data_root, from_block, to_block)?;
    let existing = existing_tx_hashes(data_root, TX_RECEIPT_LOG_SUMMARIES_DATASET)?;
    let mut queue = hashes
        .into_iter()
        .filter(|hash| !existing.contains(hash))
        .collect::<Vec<_>>();
    sort_hash_queue_by_source(&mut queue, &metadata);
    Ok((queue, metadata))
}

pub fn collect_trace_queue(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
    max_txs: usize,
) -> Result<(Vec<String>, BTreeMap<String, TxSourceMetadata>)> {
    let (hashes, metadata, _) = collect_swap_sources(data_root, from_block, to_block)?;
    let existing = existing_tx_hashes(data_root, DEBUG_TRACE_SUMMARIES_DATASET)?;
    let mut scored = hashes
        .into_iter()
        .filter(|hash| !existing.contains(hash))
        .map(|hash| {
            let score = metadata
                .get(&hash)
                .map(|row| {
                    row.max_quote_abs + row.swap_count as f64 + row.pools.len() as f64 * 10_000.0
                })
                .unwrap_or(0.0);
            (hash, score)
        })
        .collect::<Vec<_>>();
    scored.sort_by(|a, b| {
        b.1.total_cmp(&a.1)
            .then_with(|| {
                stable_shard_index(&a.0, usize::MAX).cmp(&stable_shard_index(&b.0, usize::MAX))
            })
            .then_with(|| a.0.cmp(&b.0))
    });
    let queue = scored
        .into_iter()
        .take(max_txs)
        .map(|(hash, _)| hash)
        .collect();
    Ok((queue, metadata))
}

pub fn existing_tx_hashes(data_root: &Path, dataset: &str) -> Result<BTreeSet<String>> {
    let root = data_root.join(RAW_DIR).join(dataset);
    let mut hashes = BTreeSet::new();
    for path in parquet_files_under(&root)? {
        if path.exists() {
            for hash in read_string_column_from_parquet(&path, "transaction_hash")? {
                if !hash.is_empty() {
                    hashes.insert(hash.to_ascii_lowercase());
                }
            }
        }
    }
    Ok(hashes)
}

pub fn sort_hash_queue_by_source(
    queue: &mut [String],
    metadata: &BTreeMap<String, TxSourceMetadata>,
) {
    queue.sort_by(|a, b| {
        let a_meta = metadata.get(a);
        let b_meta = metadata.get(b);
        a_meta
            .and_then(|row| row.block_number)
            .unwrap_or(u64::MAX)
            .cmp(&b_meta.and_then(|row| row.block_number).unwrap_or(u64::MAX))
            .then_with(|| {
                a_meta
                    .and_then(|row| row.transaction_index)
                    .unwrap_or(u64::MAX)
                    .cmp(
                        &b_meta
                            .and_then(|row| row.transaction_index)
                            .unwrap_or(u64::MAX),
                    )
            })
            .then_with(|| a.cmp(b))
    });
}

pub fn tx_body_queue_cache_path(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> PathBuf {
    let from = from_block
        .map(|value| value.to_string())
        .unwrap_or_else(|| "start".to_string());
    let to = to_block
        .map(|value| value.to_string())
        .unwrap_or_else(|| "end".to_string());
    data_root.join(WORK_DIR).join(format!(
        "mon_usdc_tx_body_queue_v{TX_QUEUE_CACHE_VERSION}_{from}_{to}.tsv"
    ))
}

pub fn tx_queue_entries_from_sources(
    mut hashes: Vec<String>,
    metadata: &BTreeMap<String, TxSourceMetadata>,
) -> Result<Vec<TxQueueEntry>> {
    sort_hash_queue_by_source(&mut hashes, metadata);
    hashes
        .into_iter()
        .map(|hash| tx_queue_entry_from_metadata(hash, metadata))
        .collect()
}

fn tx_queue_entry_from_metadata(
    hash: String,
    metadata: &BTreeMap<String, TxSourceMetadata>,
) -> Result<TxQueueEntry> {
    let meta = metadata.get(&hash);
    let block_timestamp = meta.and_then(|row| row.block_timestamp);
    let block_datetime_utc = match (meta, block_timestamp) {
        (Some(row), _) if !row.block_datetime_utc.is_empty() => row.block_datetime_utc.clone(),
        (_, Some(timestamp)) if timestamp > 0 => utc_from_timestamp(timestamp)?,
        _ => String::new(),
    };
    let dt = match block_timestamp.filter(|timestamp| *timestamp > 0) {
        Some(timestamp) => dt_from_timestamp(timestamp)?,
        None => block_datetime_utc
            .get(..10)
            .filter(|value| !value.is_empty())
            .unwrap_or("unknown")
            .to_string(),
    };
    Ok(TxQueueEntry {
        tx_hash: hash.to_ascii_lowercase(),
        block_number: meta.and_then(|row| row.block_number),
        transaction_index: meta.and_then(|row| row.transaction_index),
        block_timestamp,
        block_datetime_utc,
        dt,
    })
}

fn tx_queue_metadata_from_entries(entries: &[TxQueueEntry]) -> BTreeMap<String, TxSourceMetadata> {
    entries
        .iter()
        .map(|entry| {
            (
                entry.tx_hash.clone(),
                TxSourceMetadata {
                    block_number: entry.block_number,
                    block_timestamp: entry.block_timestamp,
                    block_datetime_utc: entry.block_datetime_utc.clone(),
                    transaction_index: entry.transaction_index,
                    ..TxSourceMetadata::default()
                },
            )
        })
        .collect()
}

fn read_tx_queue_cache(
    path: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> Result<Vec<TxQueueEntry>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let mut reader = BufReader::new(file);
    let mut header_line = String::new();
    reader
        .read_line(&mut header_line)
        .with_context(|| format!("failed to read header {}", path.display()))?;
    let header = parse_tx_queue_cache_header(header_line.trim_end())?;
    if header.version != TX_QUEUE_CACHE_VERSION {
        anyhow::bail!(
            "queue cache version mismatch: expected {}, got {}",
            TX_QUEUE_CACHE_VERSION,
            header.version
        );
    }
    if header.dataset != TX_BODIES_DATASET {
        anyhow::bail!("queue cache dataset mismatch: {}", header.dataset);
    }
    if header.from_block != from_block || header.to_block != to_block {
        anyhow::bail!("queue cache block window mismatch");
    }

    let mut entries = Vec::with_capacity(header.entry_count);
    for (line_index, line) in reader.lines().enumerate() {
        let line = line.with_context(|| {
            format!(
                "failed to read queue cache line {} from {}",
                line_index + 2,
                path.display()
            )
        })?;
        if line.trim().is_empty() {
            continue;
        }
        entries.push(parse_tx_queue_cache_entry(&line).with_context(|| {
            format!(
                "failed to parse queue cache line {} from {}",
                line_index + 2,
                path.display()
            )
        })?);
    }
    if header.entry_count != entries.len() {
        anyhow::bail!(
            "queue cache entry_count mismatch: header {} actual {}",
            header.entry_count,
            entries.len()
        );
    }
    Ok(entries)
}

fn write_tx_queue_cache(
    path: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
    entries: &[TxQueueEntry],
) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    let filename = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("tx_queue.tsv");
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    let temp_path =
        path.with_file_name(format!(".{filename}.tmp.{}.{}", std::process::id(), nonce));
    {
        let file = File::create(&temp_path)
            .with_context(|| format!("failed to create {}", temp_path.display()))?;
        let mut writer = BufWriter::new(file);
        writeln!(
            writer,
            "version={TX_QUEUE_CACHE_VERSION}\tdataset={TX_BODIES_DATASET}\tfrom={}\tto={}\tcount={}",
            format_optional_u64(from_block),
            format_optional_u64(to_block),
            entries.len()
        )
        .with_context(|| format!("failed to write {}", temp_path.display()))?;
        for entry in entries {
            writeln!(
                writer,
                "{}\t{}\t{}\t{}\t{}\t{}",
                entry.tx_hash,
                format_optional_u64(entry.block_number),
                format_optional_u64(entry.transaction_index),
                format_optional_u64(entry.block_timestamp),
                entry.block_datetime_utc,
                entry.dt
            )
            .with_context(|| format!("failed to write {}", temp_path.display()))?;
        }
        writer
            .flush()
            .with_context(|| format!("failed to flush {}", temp_path.display()))?;
    }
    if path.exists() {
        fs::remove_file(path)
            .with_context(|| format!("failed to replace queue cache {}", path.display()))?;
    }
    fs::rename(&temp_path, path).with_context(|| {
        format!(
            "failed to move queue cache {} to {}",
            temp_path.display(),
            path.display()
        )
    })?;
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct TxQueueCacheHeader {
    version: u32,
    dataset: String,
    from_block: Option<u64>,
    to_block: Option<u64>,
    entry_count: usize,
}

fn parse_tx_queue_cache_header(line: &str) -> Result<TxQueueCacheHeader> {
    let mut fields = BTreeMap::<&str, &str>::new();
    for part in line.split('\t') {
        let Some((key, value)) = part.split_once('=') else {
            anyhow::bail!("invalid queue cache header field {part}");
        };
        fields.insert(key, value);
    }
    Ok(TxQueueCacheHeader {
        version: fields
            .get("version")
            .ok_or_else(|| anyhow!("missing queue cache version"))?
            .parse::<u32>()
            .context("invalid queue cache version")?,
        dataset: fields
            .get("dataset")
            .ok_or_else(|| anyhow!("missing queue cache dataset"))?
            .to_string(),
        from_block: parse_optional_u64(
            fields
                .get("from")
                .ok_or_else(|| anyhow!("missing queue cache from"))?,
        )?,
        to_block: parse_optional_u64(
            fields
                .get("to")
                .ok_or_else(|| anyhow!("missing queue cache to"))?,
        )?,
        entry_count: fields
            .get("count")
            .ok_or_else(|| anyhow!("missing queue cache count"))?
            .parse::<usize>()
            .context("invalid queue cache count")?,
    })
}

fn parse_tx_queue_cache_entry(line: &str) -> Result<TxQueueEntry> {
    let fields = line.split('\t').collect::<Vec<_>>();
    if fields.len() != 6 {
        anyhow::bail!("expected 6 fields, got {}", fields.len());
    }
    Ok(TxQueueEntry {
        tx_hash: fields[0].to_ascii_lowercase(),
        block_number: parse_optional_u64(fields[1])?,
        transaction_index: parse_optional_u64(fields[2])?,
        block_timestamp: parse_optional_u64(fields[3])?,
        block_datetime_utc: fields[4].to_string(),
        dt: fields[5].to_string(),
    })
}

fn format_optional_u64(value: Option<u64>) -> String {
    value.map(|value| value.to_string()).unwrap_or_default()
}

fn parse_optional_u64(value: &str) -> Result<Option<u64>> {
    let value = value.trim();
    if value.is_empty() {
        Ok(None)
    } else {
        Ok(Some(value.parse::<u64>()?))
    }
}

fn parquet_path_may_overlap_blocks(
    path: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> bool {
    let Some((file_from, file_to)) = block_range_from_filename(path) else {
        return true;
    };
    !from_block.map_or(false, |from| file_to < from) && !to_block.map_or(false, |to| file_from > to)
}

fn block_range_from_filename(path: &Path) -> Option<(u64, u64)> {
    let stem = path.file_stem()?.to_str()?;
    let mut numbers = stem
        .split('_')
        .rev()
        .filter_map(|part| part.parse::<u64>().ok());
    let to_block = numbers.next()?;
    let from_block = numbers.next()?;
    (from_block <= to_block).then_some((from_block, to_block))
}

pub fn collect_pool_state_candidates(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
    max_event_blocks: usize,
) -> Result<Vec<PoolStateCandidate>> {
    let (_, _, events) = collect_swap_sources(data_root, from_block, to_block)?;
    let mut by_block = BTreeMap::<u64, Vec<SwapEventLite>>::new();
    for event in events.into_iter().filter(|event| event.block_number > 0) {
        by_block.entry(event.block_number).or_default().push(event);
    }
    let mut block_scores = by_block
        .iter()
        .map(|(block, events)| {
            let score = events
                .iter()
                .filter_map(|event| event.quote_abs)
                .fold(0.0f64, f64::max);
            (*block, score)
        })
        .collect::<Vec<_>>();
    block_scores.sort_by(|a, b| b.1.total_cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let selected_blocks = block_scores
        .into_iter()
        .take(max_event_blocks)
        .map(|(block, _)| block)
        .collect::<BTreeSet<_>>();

    let mut candidates = Vec::new();
    for block in selected_blocks {
        let Some(events) = by_block.remove(&block) else {
            continue;
        };
        let mut by_pool = BTreeMap::<String, SwapEventLite>::new();
        for event in events {
            by_pool
                .entry(event.pool_address.clone())
                .and_modify(|current| {
                    if event.quote_abs.unwrap_or(0.0) > current.quote_abs.unwrap_or(0.0) {
                        *current = event.clone();
                    }
                })
                .or_insert(event);
        }
        for event in by_pool.into_values() {
            candidates.push(PoolStateCandidate {
                event_block_number: event.block_number,
                block_timestamp: event.block_timestamp,
                block_datetime_utc: event.block_datetime_utc,
                pool_address: event.pool_address,
                dex_id: event.dex_id,
                family: event.family,
                direction: event.direction,
                quote_abs: event
                    .quote_abs
                    .map(|value| format!("{value:.12}"))
                    .unwrap_or_default(),
            });
        }
    }
    candidates.sort_by(|a, b| {
        a.event_block_number
            .cmp(&b.event_block_number)
            .then_with(|| a.pool_address.cmp(&b.pool_address))
    });
    Ok(candidates)
}

pub fn existing_pool_state_keys(data_root: &Path) -> Result<BTreeSet<(String, u64, String)>> {
    let root = data_root.join(RAW_DIR).join(POOL_STATE_SAMPLES_DATASET);
    let mut keys = BTreeSet::new();
    for path in parquet_files_under(&root)? {
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder.with_batch_size(4096).build()?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            let sample_block_number = uint64_column(&batch, "sample_block_number")?;
            let sample_side = string_column(&batch, "sample_side")?;
            let pool_address = string_column(&batch, "pool_address")?;
            for index in 0..batch.num_rows() {
                if sample_block_number.is_null(index)
                    || sample_side.is_null(index)
                    || pool_address.is_null(index)
                {
                    continue;
                }
                keys.insert((
                    pool_address.value(index).to_ascii_lowercase(),
                    sample_block_number.value(index),
                    sample_side.value(index).to_string(),
                ));
            }
        }
    }
    Ok(keys)
}

pub fn tx_body_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, true),
        Field::new("block_timestamp", DataType::UInt64, true),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, true),
        Field::new("from_address", DataType::Utf8, false),
        Field::new("to_address", DataType::Utf8, false),
        Field::new("nonce", DataType::UInt64, true),
        Field::new("tx_type", DataType::Utf8, false),
        Field::new("value", DataType::Utf8, false),
        Field::new("gas", DataType::UInt64, true),
        Field::new("gas_price", DataType::UInt64, true),
        Field::new("max_fee_per_gas", DataType::UInt64, true),
        Field::new("max_priority_fee_per_gas", DataType::UInt64, true),
        Field::new("input_hex", DataType::Utf8, false),
        Field::new("input_len", DataType::UInt64, false),
        Field::new("method_selector", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn tx_body_row_from_rpc(
    fetched_at_utc: &str,
    hash: &str,
    value: Value,
    error: Option<String>,
    metadata: Option<&TxSourceMetadata>,
) -> Result<TxBodyRow> {
    let (block_timestamp, block_datetime_utc, dt) = timestamp_fields(
        fetched_at_utc,
        metadata.and_then(|row| row.block_timestamp),
        metadata,
    )?;
    if let Some(error) = error {
        return Ok(TxBodyRow {
            fetched_at_utc: fetched_at_utc.to_string(),
            transaction_hash: hash.to_ascii_lowercase(),
            request_status: "rpc_error".to_string(),
            error,
            block_number: metadata.and_then(|row| row.block_number),
            block_timestamp,
            block_datetime_utc,
            transaction_index: metadata.and_then(|row| row.transaction_index),
            from_address: String::new(),
            to_address: String::new(),
            nonce: None,
            tx_type: String::new(),
            value: String::new(),
            gas: None,
            gas_price: None,
            max_fee_per_gas: None,
            max_priority_fee_per_gas: None,
            input_hex: String::new(),
            input_len: 0,
            method_selector: String::new(),
            dt,
        });
    }
    if value.is_null() {
        return Ok(TxBodyRow {
            fetched_at_utc: fetched_at_utc.to_string(),
            transaction_hash: hash.to_ascii_lowercase(),
            request_status: "missing_transaction".to_string(),
            error: String::new(),
            block_number: metadata.and_then(|row| row.block_number),
            block_timestamp,
            block_datetime_utc,
            transaction_index: metadata.and_then(|row| row.transaction_index),
            from_address: String::new(),
            to_address: String::new(),
            nonce: None,
            tx_type: String::new(),
            value: String::new(),
            gas: None,
            gas_price: None,
            max_fee_per_gas: None,
            max_priority_fee_per_gas: None,
            input_hex: String::new(),
            input_len: 0,
            method_selector: String::new(),
            dt,
        });
    }

    let tx_hash = string_field(&value, "hash")
        .unwrap_or_else(|| hash.to_string())
        .to_ascii_lowercase();
    let input_hex = string_field(&value, "input")
        .or_else(|| string_field(&value, "data"))
        .unwrap_or_default();
    let block_number =
        hex_u64_field(&value, "blockNumber")?.or_else(|| metadata.and_then(|row| row.block_number));
    let transaction_index = hex_u64_field(&value, "transactionIndex")?
        .or_else(|| metadata.and_then(|row| row.transaction_index));
    Ok(TxBodyRow {
        fetched_at_utc: fetched_at_utc.to_string(),
        transaction_hash: tx_hash,
        request_status: "ok".to_string(),
        error: String::new(),
        block_number,
        block_timestamp,
        block_datetime_utc,
        transaction_index,
        from_address: string_field(&value, "from")
            .unwrap_or_default()
            .to_ascii_lowercase(),
        to_address: string_field(&value, "to")
            .unwrap_or_default()
            .to_ascii_lowercase(),
        nonce: hex_u64_field(&value, "nonce")?,
        tx_type: string_field(&value, "type").unwrap_or_default(),
        value: string_field(&value, "value")
            .map(|raw| hex_to_decimal_string(&raw))
            .unwrap_or_default(),
        gas: hex_u64_field(&value, "gas")?,
        gas_price: hex_u64_field(&value, "gasPrice")?,
        max_fee_per_gas: hex_u64_field(&value, "maxFeePerGas")?,
        max_priority_fee_per_gas: hex_u64_field(&value, "maxPriorityFeePerGas")?,
        input_len: hex_data_byte_len(&input_hex),
        method_selector: method_selector(&input_hex),
        input_hex,
        dt,
    })
}

pub fn write_tx_body_parts(
    data_root: &Path,
    rows: &[TxBodyRow],
    batch_hashes: &[String],
) -> Result<Vec<finance_chain_core::storage::PartWrite>> {
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let schema = tx_body_schema();
    write_schema_metadata(data_root, TX_BODIES_DATASET, schema.as_ref(), &["dt"])?;
    let batch_id = deterministic_list_id(batch_hashes);
    let mut by_dt = BTreeMap::<String, Vec<TxBodyRow>>::new();
    for row in rows {
        by_dt.entry(row.dt.clone()).or_default().push(row.clone());
    }
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
                opt_u64_array(&rows.iter().map(|row| row.nonce).collect::<Vec<_>>()),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.tx_type.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(&rows.iter().map(|row| row.value.clone()).collect::<Vec<_>>()),
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
                        .map(|row| row.input_hex.clone())
                        .collect::<Vec<_>>(),
                ),
                u64_array(&rows.iter().map(|row| row.input_len).collect::<Vec<_>>()),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.method_selector.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
            ],
        )?;
        let stem = format!("mon_usdc_tx_body_sample_{batch_id}");
        parts.push(write_parquet_part(
            &custom_part_path(data_root, RAW_DIR, TX_BODIES_DATASET, &dt, &stem),
            schema.clone(),
            batch,
        )?);
    }
    Ok(parts)
}

pub fn receipt_log_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, true),
        Field::new("block_timestamp", DataType::UInt64, true),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, true),
        Field::new("log_index", DataType::UInt64, true),
        Field::new("address", DataType::Utf8, false),
        Field::new("topic0", DataType::Utf8, false),
        Field::new("topics_json", DataType::Utf8, false),
        Field::new("data", DataType::Utf8, false),
        Field::new("removed", DataType::Boolean, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn receipt_log_summary_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, true),
        Field::new("block_timestamp", DataType::UInt64, true),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, true),
        Field::new("logs_count", DataType::UInt64, false),
        Field::new("mon_usdc_swap_log_count", DataType::UInt64, false),
        Field::new("erc20_transfer_count", DataType::UInt64, false),
        Field::new("pool_addresses_seen", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn receipt_log_bundle_rows_from_rpc(
    fetched_at_utc: &str,
    hash: &str,
    value: Value,
    error: Option<String>,
    metadata: Option<&TxSourceMetadata>,
) -> Result<(ReceiptLogSummaryRow, Vec<ReceiptLogRow>)> {
    let (local_ts, local_datetime, local_dt) = timestamp_fields(
        fetched_at_utc,
        metadata.and_then(|row| row.block_timestamp),
        metadata,
    )?;
    if let Some(error) = error {
        return Ok((
            ReceiptLogSummaryRow {
                fetched_at_utc: fetched_at_utc.to_string(),
                transaction_hash: hash.to_ascii_lowercase(),
                request_status: "rpc_error".to_string(),
                error,
                block_number: metadata.and_then(|row| row.block_number),
                block_timestamp: local_ts,
                block_datetime_utc: local_datetime,
                transaction_index: metadata.and_then(|row| row.transaction_index),
                logs_count: 0,
                mon_usdc_swap_log_count: 0,
                erc20_transfer_count: 0,
                pool_addresses_seen: String::new(),
                dt: local_dt,
            },
            Vec::new(),
        ));
    }
    if value.is_null() {
        return Ok((
            ReceiptLogSummaryRow {
                fetched_at_utc: fetched_at_utc.to_string(),
                transaction_hash: hash.to_ascii_lowercase(),
                request_status: "missing_receipt".to_string(),
                error: String::new(),
                block_number: metadata.and_then(|row| row.block_number),
                block_timestamp: local_ts,
                block_datetime_utc: local_datetime,
                transaction_index: metadata.and_then(|row| row.transaction_index),
                logs_count: 0,
                mon_usdc_swap_log_count: 0,
                erc20_transfer_count: 0,
                pool_addresses_seen: String::new(),
                dt: local_dt,
            },
            Vec::new(),
        ));
    }

    let receipt: RpcReceipt = serde_json::from_value(value.clone())?;
    let block_number = receipt
        .block_number
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?
        .or_else(|| metadata.and_then(|row| row.block_number));
    let transaction_index = receipt
        .transaction_index
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?
        .or_else(|| metadata.and_then(|row| row.transaction_index));
    let (block_timestamp, block_datetime_utc, dt) =
        timestamp_fields(fetched_at_utc, local_ts, metadata)?;
    let tx_hash = receipt.transaction_hash.to_ascii_lowercase();
    let logs = receipt.logs.unwrap_or_default();
    let pools = known_top4_pool_set();
    let mut rows = Vec::new();
    let mut pool_addresses_seen = BTreeSet::new();
    let mut mon_usdc_swap_log_count = 0u64;
    let mut erc20_transfer_count = 0u64;
    for log in &logs {
        let address = string_field(log, "address")
            .unwrap_or_default()
            .to_ascii_lowercase();
        let topics = topics_from_log(log);
        let topic0 = topics
            .first()
            .cloned()
            .unwrap_or_default()
            .to_ascii_lowercase();
        if pools.contains(&address) {
            pool_addresses_seen.insert(address.clone());
        }
        if pools.contains(&address) && is_swap_topic(&topic0) {
            mon_usdc_swap_log_count += 1;
        }
        if topic0.eq_ignore_ascii_case(ERC20_TRANSFER_TOPIC) {
            erc20_transfer_count += 1;
        }
        rows.push(ReceiptLogRow {
            fetched_at_utc: fetched_at_utc.to_string(),
            transaction_hash: tx_hash.clone(),
            request_status: "ok".to_string(),
            block_number,
            block_timestamp,
            block_datetime_utc: block_datetime_utc.clone(),
            transaction_index,
            log_index: hex_u64_field(log, "logIndex")?,
            address,
            topic0,
            topics_json: serde_json::to_string(&topics)?,
            data: string_field(log, "data").unwrap_or_default(),
            removed: log.get("removed").and_then(Value::as_bool).unwrap_or(false),
            dt: dt.clone(),
        });
    }
    Ok((
        ReceiptLogSummaryRow {
            fetched_at_utc: fetched_at_utc.to_string(),
            transaction_hash: tx_hash,
            request_status: "ok".to_string(),
            error: String::new(),
            block_number,
            block_timestamp,
            block_datetime_utc,
            transaction_index,
            logs_count: logs.len() as u64,
            mon_usdc_swap_log_count,
            erc20_transfer_count,
            pool_addresses_seen: pool_addresses_seen
                .into_iter()
                .collect::<Vec<_>>()
                .join("|"),
            dt,
        },
        rows,
    ))
}

pub fn write_receipt_log_bundle_parts(
    data_root: &Path,
    summaries: &[ReceiptLogSummaryRow],
    logs: &[ReceiptLogRow],
    batch_hashes: &[String],
) -> Result<Vec<finance_chain_core::storage::PartWrite>> {
    let mut parts = Vec::new();
    let batch_id = deterministic_list_id(batch_hashes);
    if !summaries.is_empty() {
        let schema = receipt_log_summary_schema();
        write_schema_metadata(
            data_root,
            TX_RECEIPT_LOG_SUMMARIES_DATASET,
            schema.as_ref(),
            &["dt"],
        )?;
        let mut by_dt = BTreeMap::<String, Vec<ReceiptLogSummaryRow>>::new();
        for row in summaries {
            by_dt.entry(row.dt.clone()).or_default().push(row.clone());
        }
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
                    u64_array(&rows.iter().map(|row| row.logs_count).collect::<Vec<_>>()),
                    u64_array(
                        &rows
                            .iter()
                            .map(|row| row.mon_usdc_swap_log_count)
                            .collect::<Vec<_>>(),
                    ),
                    u64_array(
                        &rows
                            .iter()
                            .map(|row| row.erc20_transfer_count)
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.pool_addresses_seen.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
                ],
            )?;
            let stem = format!("mon_usdc_receipt_log_summaries_{batch_id}");
            parts.push(write_parquet_part(
                &custom_part_path(
                    data_root,
                    RAW_DIR,
                    TX_RECEIPT_LOG_SUMMARIES_DATASET,
                    &dt,
                    &stem,
                ),
                schema.clone(),
                batch,
            )?);
        }
    }
    if !logs.is_empty() {
        let schema = receipt_log_schema();
        write_schema_metadata(data_root, TX_RECEIPT_LOGS_DATASET, schema.as_ref(), &["dt"])?;
        let mut by_dt = BTreeMap::<String, Vec<ReceiptLogRow>>::new();
        for row in logs {
            by_dt.entry(row.dt.clone()).or_default().push(row.clone());
        }
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
                    opt_u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
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
                    opt_u64_array(&rows.iter().map(|row| row.log_index).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.address.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.topic0.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.topics_json.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.data.clone()).collect::<Vec<_>>()),
                    bool_array(&rows.iter().map(|row| row.removed).collect::<Vec<_>>()),
                    string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
                ],
            )?;
            let stem = format!("mon_usdc_receipt_logs_{batch_id}");
            parts.push(write_parquet_part(
                &custom_part_path(data_root, RAW_DIR, TX_RECEIPT_LOGS_DATASET, &dt, &stem),
                schema.clone(),
                batch,
            )?);
        }
    }
    Ok(parts)
}

pub fn pool_state_sample_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("event_block_number", DataType::UInt64, false),
        Field::new("sample_block_number", DataType::UInt64, false),
        Field::new("sample_side", DataType::Utf8, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("sqrt_price_x96", DataType::Utf8, false),
        Field::new("tick", DataType::Utf8, false),
        Field::new("liquidity", DataType::Utf8, false),
        Field::new("tick_spacing", DataType::Utf8, false),
        Field::new("active_id", DataType::Utf8, false),
        Field::new("bin_step", DataType::Utf8, false),
        Field::new("active_bin_reserve_x", DataType::Utf8, false),
        Field::new("active_bin_reserve_y", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn pool_liquidity_window_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("event_block_number", DataType::UInt64, false),
        Field::new("sample_block_number", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("window_kind", DataType::Utf8, false),
        Field::new("offset", DataType::Utf8, false),
        Field::new("tick_or_bin", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("liquidity_gross", DataType::Utf8, false),
        Field::new("liquidity_net", DataType::Utf8, false),
        Field::new("reserve_x", DataType::Utf8, false),
        Field::new("reserve_y", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn write_pool_state_parts(
    data_root: &Path,
    state_rows: &[PoolStateSampleRow],
    window_rows: &[PoolLiquidityWindowRow],
    batch_key: &[String],
) -> Result<Vec<finance_chain_core::storage::PartWrite>> {
    let mut parts = Vec::new();
    let batch_id = deterministic_list_id(batch_key);
    if !state_rows.is_empty() {
        let schema = pool_state_sample_schema();
        write_schema_metadata(
            data_root,
            POOL_STATE_SAMPLES_DATASET,
            schema.as_ref(),
            &["dt"],
        )?;
        let mut by_dt = BTreeMap::<String, Vec<PoolStateSampleRow>>::new();
        for row in state_rows {
            by_dt.entry(row.dt.clone()).or_default().push(row.clone());
        }
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
                            .map(|row| row.request_status.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.error.clone()).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.sqrt_price_x96.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.tick.clone()).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.liquidity.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.tick_spacing.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.active_id.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.bin_step.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.active_bin_reserve_x.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.active_bin_reserve_y.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
                ],
            )?;
            let stem = format!("mon_usdc_pool_state_samples_{batch_id}");
            parts.push(write_parquet_part(
                &custom_part_path(data_root, RAW_DIR, POOL_STATE_SAMPLES_DATASET, &dt, &stem),
                schema.clone(),
                batch,
            )?);
        }
    }
    if !window_rows.is_empty() {
        let schema = pool_liquidity_window_schema();
        write_schema_metadata(
            data_root,
            POOL_LIQUIDITY_WINDOWS_DATASET,
            schema.as_ref(),
            &["dt"],
        )?;
        let mut by_dt = BTreeMap::<String, Vec<PoolLiquidityWindowRow>>::new();
        for row in window_rows {
            by_dt.entry(row.dt.clone()).or_default().push(row.clone());
        }
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
                            .map(|row| row.window_kind.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.offset.to_string())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.tick_or_bin.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.request_status.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.error.clone()).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.liquidity_gross.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.liquidity_net.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.reserve_x.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.reserve_y.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
                ],
            )?;
            let stem = format!("mon_usdc_pool_liquidity_windows_{batch_id}");
            parts.push(write_parquet_part(
                &custom_part_path(
                    data_root,
                    RAW_DIR,
                    POOL_LIQUIDITY_WINDOWS_DATASET,
                    &dt,
                    &stem,
                ),
                schema.clone(),
                batch,
            )?);
        }
    }
    Ok(parts)
}

pub fn debug_trace_summary_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, true),
        Field::new("block_timestamp", DataType::UInt64, true),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("call_count", DataType::UInt64, false),
        Field::new("max_depth", DataType::UInt64, false),
        Field::new("root_call_type", DataType::Utf8, false),
        Field::new("root_from", DataType::Utf8, false),
        Field::new("root_to", DataType::Utf8, false),
        Field::new("root_error", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn debug_trace_call_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("request_status", DataType::Utf8, false),
        Field::new("depth", DataType::UInt64, false),
        Field::new("trace_address", DataType::Utf8, false),
        Field::new("call_type", DataType::Utf8, false),
        Field::new("from_address", DataType::Utf8, false),
        Field::new("to_address", DataType::Utf8, false),
        Field::new("value", DataType::Utf8, false),
        Field::new("gas", DataType::UInt64, true),
        Field::new("gas_used", DataType::UInt64, true),
        Field::new("input_selector", DataType::Utf8, false),
        Field::new("error", DataType::Utf8, false),
        Field::new("revert_reason", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn debug_trace_rows_from_rpc(
    fetched_at_utc: &str,
    hash: &str,
    value: Value,
    error: Option<String>,
    metadata: Option<&TxSourceMetadata>,
) -> Result<(DebugTraceSummaryRow, Vec<DebugTraceCallRow>)> {
    let (block_timestamp, block_datetime_utc, dt) = timestamp_fields(
        fetched_at_utc,
        metadata.and_then(|row| row.block_timestamp),
        metadata,
    )?;
    if let Some(error) = error {
        return Ok((
            DebugTraceSummaryRow {
                fetched_at_utc: fetched_at_utc.to_string(),
                transaction_hash: hash.to_ascii_lowercase(),
                request_status: "rpc_error".to_string(),
                error,
                block_number: metadata.and_then(|row| row.block_number),
                block_timestamp,
                block_datetime_utc,
                call_count: 0,
                max_depth: 0,
                root_call_type: String::new(),
                root_from: String::new(),
                root_to: String::new(),
                root_error: String::new(),
                dt,
            },
            Vec::new(),
        ));
    }
    if value.is_null() {
        return Ok((
            DebugTraceSummaryRow {
                fetched_at_utc: fetched_at_utc.to_string(),
                transaction_hash: hash.to_ascii_lowercase(),
                request_status: "missing_trace".to_string(),
                error: String::new(),
                block_number: metadata.and_then(|row| row.block_number),
                block_timestamp,
                block_datetime_utc,
                call_count: 0,
                max_depth: 0,
                root_call_type: String::new(),
                root_from: String::new(),
                root_to: String::new(),
                root_error: String::new(),
                dt,
            },
            Vec::new(),
        ));
    }
    let mut rows = Vec::new();
    flatten_trace_call(
        fetched_at_utc,
        hash,
        "ok",
        &value,
        0,
        &mut Vec::new(),
        &dt,
        &mut rows,
    )?;
    let stats = trace_flatten_stats(&rows);
    Ok((
        DebugTraceSummaryRow {
            fetched_at_utc: fetched_at_utc.to_string(),
            transaction_hash: hash.to_ascii_lowercase(),
            request_status: "ok".to_string(),
            error: String::new(),
            block_number: metadata.and_then(|row| row.block_number),
            block_timestamp,
            block_datetime_utc,
            call_count: stats.call_count,
            max_depth: stats.max_depth,
            root_call_type: stats.root_call_type,
            root_from: stats.root_from,
            root_to: stats.root_to,
            root_error: stats.root_error,
            dt,
        },
        rows,
    ))
}

pub fn write_debug_trace_parts(
    data_root: &Path,
    summaries: &[DebugTraceSummaryRow],
    calls: &[DebugTraceCallRow],
    batch_hashes: &[String],
) -> Result<Vec<finance_chain_core::storage::PartWrite>> {
    let mut parts = Vec::new();
    let batch_id = deterministic_list_id(batch_hashes);
    if !summaries.is_empty() {
        let schema = debug_trace_summary_schema();
        write_schema_metadata(
            data_root,
            DEBUG_TRACE_SUMMARIES_DATASET,
            schema.as_ref(),
            &["dt"],
        )?;
        let mut by_dt = BTreeMap::<String, Vec<DebugTraceSummaryRow>>::new();
        for row in summaries {
            by_dt.entry(row.dt.clone()).or_default().push(row.clone());
        }
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
                    u64_array(&rows.iter().map(|row| row.call_count).collect::<Vec<_>>()),
                    u64_array(&rows.iter().map(|row| row.max_depth).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.root_call_type.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.root_from.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.root_to.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.root_error.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
                ],
            )?;
            let stem = format!("mon_usdc_debug_trace_summaries_{batch_id}");
            parts.push(write_parquet_part(
                &custom_part_path(
                    data_root,
                    RAW_DIR,
                    DEBUG_TRACE_SUMMARIES_DATASET,
                    &dt,
                    &stem,
                ),
                schema.clone(),
                batch,
            )?);
        }
    }
    if !calls.is_empty() {
        let schema = debug_trace_call_schema();
        write_schema_metadata(
            data_root,
            DEBUG_TRACE_CALLS_DATASET,
            schema.as_ref(),
            &["dt"],
        )?;
        let mut by_dt = BTreeMap::<String, Vec<DebugTraceCallRow>>::new();
        for row in calls {
            by_dt.entry(row.dt.clone()).or_default().push(row.clone());
        }
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
                    u64_array(&rows.iter().map(|row| row.depth).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.trace_address.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.call_type.clone())
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
                    string_array(&rows.iter().map(|row| row.value.clone()).collect::<Vec<_>>()),
                    opt_u64_array(&rows.iter().map(|row| row.gas).collect::<Vec<_>>()),
                    opt_u64_array(&rows.iter().map(|row| row.gas_used).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.input_selector.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.error.clone()).collect::<Vec<_>>()),
                    string_array(
                        &rows
                            .iter()
                            .map(|row| row.revert_reason.clone())
                            .collect::<Vec<_>>(),
                    ),
                    string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
                ],
            )?;
            let stem = format!("mon_usdc_debug_trace_calls_{batch_id}");
            parts.push(write_parquet_part(
                &custom_part_path(data_root, RAW_DIR, DEBUG_TRACE_CALLS_DATASET, &dt, &stem),
                schema.clone(),
                batch,
            )?);
        }
    }
    Ok(parts)
}

pub fn function_selector(signature: &str) -> String {
    let mut hasher = Keccak::v256();
    let mut output = [0u8; 32];
    hasher.update(signature.as_bytes());
    hasher.finalize(&mut output);
    format!(
        "0x{:02x}{:02x}{:02x}{:02x}",
        output[0], output[1], output[2], output[3]
    )
}

pub fn encode_no_arg_call(signature: &str) -> String {
    function_selector(signature)
}

pub fn encode_u24_call(signature: &str, value: u64) -> String {
    format!("{}{:064x}", function_selector(signature), value)
}

pub fn encode_i24_call(signature: &str, value: i64) -> String {
    if value >= 0 {
        format!("{}{:064x}", function_selector(signature), value as u64)
    } else {
        let low = format!("{:032x}", value as i128 as u128);
        format!("{}{}{}", function_selector(signature), "f".repeat(32), low)
    }
}

pub fn parse_v3_slot0(result: &str) -> (String, String) {
    let sqrt_price_x96 = word_at(result, 0).unwrap_or_default();
    let tick = word_at(result, 1)
        .and_then(|word| parse_signed_word_bits(&word, 24))
        .unwrap_or_default();
    (u256_word_to_decimal(&sqrt_price_x96), tick)
}

pub fn parse_v3_tick_result(result: &str) -> (String, String) {
    let liquidity_gross = word_at(result, 0)
        .map(|word| u256_word_to_decimal(&word))
        .unwrap_or_default();
    let liquidity_net = word_at(result, 1)
        .and_then(|word| parse_signed_word_bits(&word, 128))
        .unwrap_or_default();
    (liquidity_gross, liquidity_net)
}

pub fn parse_lb_bin_result(result: &str) -> (String, String) {
    let reserve_x = word_at(result, 0)
        .map(|word| u256_word_to_decimal(&word))
        .unwrap_or_default();
    let reserve_y = word_at(result, 1)
        .map(|word| u256_word_to_decimal(&word))
        .unwrap_or_default();
    (reserve_x, reserve_y)
}

pub fn parse_single_u256_result(result: &str) -> String {
    word_at(result, 0)
        .map(|word| u256_word_to_decimal(&word))
        .unwrap_or_default()
}

pub fn sample_dt_from_candidate(candidate: &PoolStateCandidate, fetched_at_utc: &str) -> String {
    if candidate.block_timestamp > 0 {
        dt_from_timestamp(candidate.block_timestamp)
            .unwrap_or_else(|_| dt_from_utc_string(fetched_at_utc))
    } else {
        dt_from_utc_string(fetched_at_utc)
    }
}

fn read_swap_sources_file(
    path: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
    hashes: &mut BTreeSet<String>,
    metadata: &mut BTreeMap<String, TxSourceMetadata>,
    events: &mut Vec<SwapEventLite>,
) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder.with_batch_size(4096).build()?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let block_number = uint64_column(&batch, "block_number")?;
        let block_timestamp = uint64_column(&batch, "block_timestamp")?;
        let block_datetime_utc = string_column(&batch, "block_datetime_utc")?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        let transaction_index = uint64_column(&batch, "transaction_index")?;
        let log_index = uint64_column(&batch, "log_index")?;
        let pool_address = string_column(&batch, "pool_address")?;
        let dex_id = string_column(&batch, "dex_id")?;
        let family = string_column(&batch, "family")?;
        let direction = string_column(&batch, "direction")?;
        let base_abs = string_column(&batch, "base_abs")?;
        let quote_abs = string_column(&batch, "quote_abs")?;
        let price_quote_per_base = string_column(&batch, "price_quote_per_base")?;
        for index in 0..batch.num_rows() {
            if transaction_hash.is_null(index) || transaction_hash.value(index).is_empty() {
                continue;
            }
            if block_number.is_null(index) {
                continue;
            }
            let block = block_number.value(index);
            if from_block.map_or(false, |from| block < from)
                || to_block.map_or(false, |to| block > to)
            {
                continue;
            }
            let hash = transaction_hash.value(index).to_ascii_lowercase();
            let block_ts = u64_value(block_timestamp, index);
            let tx_index = if transaction_index.is_null(index) {
                None
            } else {
                Some(transaction_index.value(index))
            };
            let quote = parse_f64_string(quote_abs, index);
            hashes.insert(hash.clone());
            let entry = metadata.entry(hash.clone()).or_default();
            entry.block_number.get_or_insert(block);
            if block_ts > 0 {
                entry.block_timestamp.get_or_insert(block_ts);
            }
            if entry.block_datetime_utc.is_empty() {
                entry.block_datetime_utc = string_value(block_datetime_utc, index);
            }
            if tx_index.is_some() {
                entry.transaction_index.get_or_insert(tx_index.unwrap());
            }
            entry.max_quote_abs = entry.max_quote_abs.max(quote.unwrap_or(0.0));
            entry.swap_count += 1;
            entry
                .pools
                .insert(string_value(pool_address, index).to_ascii_lowercase());
            entry.directions.insert(string_value(direction, index));
            events.push(SwapEventLite {
                block_number: block,
                block_timestamp: block_ts,
                block_datetime_utc: string_value(block_datetime_utc, index),
                transaction_hash: hash,
                transaction_index: tx_index.unwrap_or(0),
                log_index: u64_value(log_index, index),
                pool_address: string_value(pool_address, index).to_ascii_lowercase(),
                dex_id: string_value(dex_id, index),
                family: string_value(family, index),
                direction: string_value(direction, index),
                base_abs: parse_f64_string(base_abs, index),
                quote_abs: quote,
                price_quote_per_base: parse_f64_string(price_quote_per_base, index),
            });
        }
    }
    Ok(())
}

fn flatten_trace_call(
    fetched_at_utc: &str,
    hash: &str,
    request_status: &str,
    node: &Value,
    depth: u64,
    trace_address: &mut Vec<usize>,
    dt: &str,
    rows: &mut Vec<DebugTraceCallRow>,
) -> Result<()> {
    let address = trace_address
        .iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>()
        .join(".");
    let input = string_field(node, "input").unwrap_or_default();
    rows.push(DebugTraceCallRow {
        fetched_at_utc: fetched_at_utc.to_string(),
        transaction_hash: hash.to_ascii_lowercase(),
        request_status: request_status.to_string(),
        depth,
        trace_address: address,
        call_type: string_field(node, "type").unwrap_or_default(),
        from_address: string_field(node, "from")
            .unwrap_or_default()
            .to_ascii_lowercase(),
        to_address: string_field(node, "to")
            .unwrap_or_default()
            .to_ascii_lowercase(),
        value: string_field(node, "value")
            .map(|raw| hex_to_decimal_string(&raw))
            .unwrap_or_default(),
        gas: hex_u64_field(node, "gas")?,
        gas_used: hex_u64_field(node, "gasUsed")?,
        input_selector: method_selector(&input),
        error: string_field(node, "error").unwrap_or_default(),
        revert_reason: string_field(node, "revertReason").unwrap_or_default(),
        dt: dt.to_string(),
    });
    if let Some(calls) = node.get("calls").and_then(Value::as_array) {
        for (index, child) in calls.iter().enumerate() {
            trace_address.push(index);
            flatten_trace_call(
                fetched_at_utc,
                hash,
                request_status,
                child,
                depth + 1,
                trace_address,
                dt,
                rows,
            )?;
            trace_address.pop();
        }
    }
    Ok(())
}

fn trace_flatten_stats(rows: &[DebugTraceCallRow]) -> TraceFlattenStats {
    let root = rows.first();
    TraceFlattenStats {
        call_count: rows.len() as u64,
        max_depth: rows.iter().map(|row| row.depth).max().unwrap_or(0),
        root_call_type: root.map(|row| row.call_type.clone()).unwrap_or_default(),
        root_from: root.map(|row| row.from_address.clone()).unwrap_or_default(),
        root_to: root.map(|row| row.to_address.clone()).unwrap_or_default(),
        root_error: root.map(|row| row.error.clone()).unwrap_or_default(),
    }
}

fn timestamp_fields(
    fetched_at_utc: &str,
    block_timestamp: Option<u64>,
    metadata: Option<&TxSourceMetadata>,
) -> Result<(Option<u64>, String, String)> {
    if let Some(timestamp) = block_timestamp.filter(|value| *value > 0) {
        return Ok((
            Some(timestamp),
            utc_from_timestamp(timestamp)?,
            dt_from_timestamp(timestamp)?,
        ));
    }
    if let Some(metadata) = metadata {
        if !metadata.block_datetime_utc.is_empty() {
            let dt = metadata
                .block_datetime_utc
                .get(..10)
                .map(str::to_string)
                .unwrap_or_else(|| dt_from_utc_string(fetched_at_utc));
            return Ok((None, metadata.block_datetime_utc.clone(), dt));
        }
    }
    Ok((None, String::new(), dt_from_utc_string(fetched_at_utc)))
}

fn known_top4_pool_set() -> BTreeSet<String> {
    known_top4_pools()
        .into_iter()
        .map(|pool| pool.pair_address.to_ascii_lowercase())
        .collect()
}

fn is_swap_topic(topic: &str) -> bool {
    [
        V2_SWAP_TOPIC,
        V3_SWAP_TOPIC,
        PANCAKE_V3_SWAP_TOPIC,
        LB_V22_SWAP_TOPIC,
    ]
    .iter()
    .any(|known| topic.eq_ignore_ascii_case(known))
}

fn topics_from_log(value: &Value) -> Vec<String> {
    value
        .get("topics")
        .and_then(Value::as_array)
        .map(|topics| {
            topics
                .iter()
                .filter_map(Value::as_str)
                .map(|topic| topic.to_ascii_lowercase())
                .collect()
        })
        .unwrap_or_default()
}

fn string_field(value: &Value, name: &str) -> Option<String> {
    value
        .get(name)
        .and_then(Value::as_str)
        .map(|value| value.to_string())
}

fn hex_u64_field(value: &Value, name: &str) -> Result<Option<u64>> {
    value
        .get(name)
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .map(parse_hex_u64)
        .transpose()
}

fn hex_data_byte_len(value: &str) -> u64 {
    value
        .strip_prefix("0x")
        .map(|body| body.len() / 2)
        .unwrap_or(0) as u64
}

pub fn method_selector(input_hex: &str) -> String {
    if input_hex.len() >= 10 && input_hex.starts_with("0x") {
        input_hex[..10].to_ascii_lowercase()
    } else {
        String::new()
    }
}

fn hex_to_decimal_string(value: &str) -> String {
    let mut out = "0".to_string();
    for ch in value.trim_start_matches("0x").chars() {
        let Some(digit) = ch.to_digit(16) else {
            return String::new();
        };
        decimal_mul_add(&mut out, 16, digit);
    }
    trim_decimal_leading_zeros(&out)
}

fn decimal_mul_add(out: &mut String, mul: u32, add: u32) {
    let mut carry = add;
    let mut digits = Vec::new();
    for ch in out.bytes().rev() {
        let value = u32::from(ch - b'0') * mul + carry;
        digits.push((value % 10) as u8 + b'0');
        carry = value / 10;
    }
    while carry > 0 {
        digits.push((carry % 10) as u8 + b'0');
        carry /= 10;
    }
    digits.reverse();
    *out = String::from_utf8(digits).unwrap_or_else(|_| "0".to_string());
}

fn trim_decimal_leading_zeros(value: &str) -> String {
    let trimmed = value.trim_start_matches('0');
    if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    }
}

fn word_at(result: &str, index: usize) -> Option<String> {
    let body = result.trim_start_matches("0x");
    let start = index.checked_mul(64)?;
    let end = start + 64;
    if body.len() < end {
        None
    } else {
        Some(body[start..end].to_string())
    }
}

fn u256_word_to_decimal(word: &str) -> String {
    hex_to_decimal_string(&format!("0x{word}"))
}

fn parse_signed_word_bits(word: &str, bits: u32) -> Option<String> {
    if bits == 0 || bits > 128 {
        return None;
    }
    let hex_chars = bits.div_ceil(4) as usize;
    let low_hex = if word.len() > hex_chars {
        &word[word.len() - hex_chars..]
    } else {
        word
    };
    let value = u128::from_str_radix(low_hex, 16).ok()?;
    if bits == 128 {
        return Some((value as i128).to_string());
    }
    let sign_bit = 1u128 << (bits - 1);
    if value & sign_bit == 0 {
        Some(value.to_string())
    } else {
        let modulus = 1i128 << bits;
        Some((value as i128 - modulus).to_string())
    }
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
        .ok_or_else(|| anyhow!("column {name} is not uint64"))
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

#[allow(dead_code)]
fn float64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array> {
    let index = batch
        .schema()
        .index_of(name)
        .with_context(|| format!("missing column {name}"))?;
    batch
        .column(index)
        .as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| anyhow!("column {name} is not float64"))
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

fn parse_f64_string(values: &StringArray, index: usize) -> Option<f64> {
    if values.is_null(index) {
        return None;
    }
    values
        .value(index)
        .parse::<f64>()
        .ok()
        .filter(|value| value.is_finite())
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    use serde_json::json;

    use super::*;

    fn unique_temp_dir(name: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or(0);
        std::env::temp_dir().join(format!(
            "finance_chain_{name}_{}_{}",
            std::process::id(),
            nonce
        ))
    }

    #[test]
    fn tx_body_parser_handles_eip1559_and_selector() {
        let row = tx_body_row_from_rpc(
            "2026-05-10T00:00:00Z",
            "0xabc",
            json!({
                "hash": "0xABC",
                "blockNumber": "0x10",
                "transactionIndex": "0x2",
                "from": "0xF00",
                "to": "0xBaa",
                "nonce": "0x9",
                "type": "0x2",
                "value": "0xde0b6b3a7640000",
                "gas": "0x5208",
                "gasPrice": "0x3b9aca00",
                "maxFeePerGas": "0x77359400",
                "maxPriorityFeePerGas": "0x5f5e100",
                "input": "0xabcdef010203"
            }),
            None,
            Some(&TxSourceMetadata {
                block_timestamp: Some(1_700_000_000),
                ..TxSourceMetadata::default()
            }),
        )
        .unwrap();
        assert_eq!(row.transaction_hash, "0xabc");
        assert_eq!(row.block_number, Some(16));
        assert_eq!(row.transaction_index, Some(2));
        assert_eq!(row.value, "1000000000000000000");
        assert_eq!(row.input_len, 6);
        assert_eq!(row.method_selector, "0xabcdef01");
        assert_eq!(row.request_status, "ok");
    }

    #[test]
    fn tx_body_parser_handles_legacy_missing_and_rpc_error() {
        let metadata = TxSourceMetadata {
            block_number: Some(7),
            block_timestamp: Some(1_700_000_000),
            transaction_index: Some(1),
            ..TxSourceMetadata::default()
        };
        let legacy = tx_body_row_from_rpc(
            "2026-05-10T00:00:00Z",
            "0xdef",
            json!({
                "hash": "0xDEF",
                "from": "0xF00",
                "to": "0xBaa",
                "nonce": "0x1",
                "type": "0x0",
                "value": "0x0",
                "gas": "0x5208",
                "gasPrice": "0x3b9aca00",
                "input": "0x"
            }),
            None,
            Some(&metadata),
        )
        .unwrap();
        assert_eq!(legacy.request_status, "ok");
        assert_eq!(legacy.tx_type, "0x0");
        assert_eq!(legacy.gas_price, Some(1_000_000_000));
        assert_eq!(legacy.max_fee_per_gas, None);

        let missing = tx_body_row_from_rpc(
            "2026-05-10T00:00:00Z",
            "0xmissing",
            Value::Null,
            None,
            Some(&metadata),
        )
        .unwrap();
        assert_eq!(missing.request_status, "missing_transaction");
        assert_eq!(missing.block_number, Some(7));

        let rpc_error = tx_body_row_from_rpc(
            "2026-05-10T00:00:00Z",
            "0xerr",
            Value::Null,
            Some("rate limited".to_string()),
            Some(&metadata),
        )
        .unwrap();
        assert_eq!(rpc_error.request_status, "rpc_error");
        assert_eq!(rpc_error.error, "rate limited");
    }

    #[test]
    fn tx_queue_cache_roundtrip_preserves_source_order() {
        let dir = unique_temp_dir("tx_queue_cache");
        let path = dir.join("_work").join("queue.json");
        let mut metadata = BTreeMap::<String, TxSourceMetadata>::new();
        metadata.insert(
            "0xcccc".to_string(),
            TxSourceMetadata {
                block_number: Some(12),
                transaction_index: Some(0),
                block_timestamp: Some(1_700_000_012),
                ..TxSourceMetadata::default()
            },
        );
        metadata.insert(
            "0xaaaa".to_string(),
            TxSourceMetadata {
                block_number: Some(10),
                transaction_index: Some(2),
                block_timestamp: Some(1_700_000_010),
                ..TxSourceMetadata::default()
            },
        );
        metadata.insert(
            "0xbbbb".to_string(),
            TxSourceMetadata {
                block_number: Some(10),
                transaction_index: Some(3),
                block_timestamp: Some(1_700_000_010),
                ..TxSourceMetadata::default()
            },
        );
        let entries = tx_queue_entries_from_sources(
            vec![
                "0xcccc".to_string(),
                "0xbbbb".to_string(),
                "0xaaaa".to_string(),
            ],
            &metadata,
        )
        .unwrap();
        assert_eq!(
            entries
                .iter()
                .map(|entry| entry.tx_hash.as_str())
                .collect::<Vec<_>>(),
            vec!["0xaaaa", "0xbbbb", "0xcccc"]
        );

        write_tx_queue_cache(&path, Some(10), Some(12), &entries).unwrap();
        let loaded = read_tx_queue_cache(&path, Some(10), Some(12)).unwrap();
        assert_eq!(loaded, entries);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn filename_block_range_prunes_non_overlapping_parts() {
        let path = PathBuf::from("mon_usdc_swap_collect_tag_100_199.parquet");
        assert_eq!(block_range_from_filename(&path), Some((100, 199)));
        assert!(parquet_path_may_overlap_blocks(&path, Some(150), Some(250)));
        assert!(!parquet_path_may_overlap_blocks(
            &path,
            Some(200),
            Some(250)
        ));
        assert!(!parquet_path_may_overlap_blocks(&path, Some(1), Some(99)));
    }

    #[test]
    fn receipt_log_bundle_counts_swaps_and_transfers() {
        let pool = known_top4_pools()[0].pair_address.to_ascii_lowercase();
        let (summary, logs) = receipt_log_bundle_rows_from_rpc(
            "2026-05-10T00:00:00Z",
            "0xaaa",
            json!({
                "transactionHash": "0xAAA",
                "transactionIndex": "0x0",
                "blockNumber": "0x20",
                "logs": [
                    {"address": pool, "logIndex": "0x1", "topics": [V3_SWAP_TOPIC], "data": "0x", "removed": false},
                    {"address": "0xtoken", "logIndex": "0x2", "topics": [ERC20_TRANSFER_TOPIC], "data": "0x", "removed": false}
                ]
            }),
            None,
            Some(&TxSourceMetadata {
                block_timestamp: Some(1_700_000_000),
                ..TxSourceMetadata::default()
            }),
        )
        .unwrap();
        assert_eq!(summary.logs_count, 2);
        assert_eq!(summary.mon_usdc_swap_log_count, 1);
        assert_eq!(summary.erc20_transfer_count, 1);
        assert_eq!(logs.len(), 2);
    }

    #[test]
    fn function_selector_and_signed_decoding_work() {
        assert_eq!(function_selector("slot0()"), "0x3850c7bd");
        assert_eq!(function_selector("ticks(int24)"), "0xf30dba93");
        let encoded_negative = encode_i24_call("ticks(int24)", -60);
        assert!(encoded_negative.ends_with("ffffffffffffffffffffffffffffffc4"));
        let word = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffc4";
        assert_eq!(parse_signed_word_bits(word, 24).unwrap(), "-60");
    }

    #[test]
    fn trace_flattener_preserves_depth_and_address() {
        let (_, rows) = debug_trace_rows_from_rpc(
            "2026-05-10T00:00:00Z",
            "0xaaa",
            json!({
                "type": "CALL",
                "from": "0x1",
                "to": "0x2",
                "gas": "0x64",
                "gasUsed": "0x32",
                "input": "0x12345678",
                "calls": [
                    {"type": "STATICCALL", "from": "0x2", "to": "0x3", "gas": "0x10", "gasUsed": "0x8", "input": "0xabcdef01"}
                ]
            }),
            None,
            Some(&TxSourceMetadata {
                block_timestamp: Some(1_700_000_000),
                ..TxSourceMetadata::default()
            }),
        )
        .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].depth, 0);
        assert_eq!(rows[0].trace_address, "");
        assert_eq!(rows[1].depth, 1);
        assert_eq!(rows[1].trace_address, "0");
        assert_eq!(rows[1].input_selector, "0xabcdef01");
    }

    #[test]
    fn stable_shard_index_is_case_insensitive() {
        assert_eq!(
            stable_shard_index("0xABCDEF", 7),
            stable_shard_index("0xabcdef", 7)
        );
    }
}

use std::cell::Cell;
use std::collections::HashSet;
use std::fs::{self, File, OpenOptions};
use std::marker::PhantomData;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, anyhow, bail};
use chrono::{SecondsFormat, Utc};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub mod analysis;
pub mod chog_v1;
pub mod dex;
pub mod dex_factors;
pub mod dex_hourly;
pub mod memecoin_features;

pub const CHECKPOINT_VERSION: u32 = 1;

#[derive(Debug)]
pub struct RpcUrlPool {
    urls: Vec<String>,
    next: Cell<usize>,
}

impl RpcUrlPool {
    pub fn from_values(values: &[String], default_url: &str) -> Result<Self> {
        let mut urls = Vec::new();
        for value in values {
            for url in value.split(',') {
                let url = url.trim();
                if !url.is_empty() {
                    urls.push(url.to_string());
                }
            }
        }
        if urls.is_empty() {
            urls.push(default_url.to_string());
        }
        Ok(Self {
            urls,
            next: Cell::new(0),
        })
    }

    pub fn primary(&self) -> &str {
        &self.urls[0]
    }

    pub fn len(&self) -> usize {
        self.urls.len()
    }

    pub fn next_url(&self) -> &str {
        let index = self.next.get();
        self.next.set((index + 1) % self.urls.len());
        &self.urls[index]
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Checkpoint {
    pub version: u32,
    pub collector: String,
    pub chain: String,
    pub address: String,
    pub topic0: String,
    pub from_block: u64,
    pub to_block: u64,
    pub last_completed_block: u64,
    pub rows_written: u64,
    pub output: String,
    pub updated_at_utc: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BlockRange {
    pub from_block: u64,
    pub to_block: u64,
}

impl BlockRange {
    pub fn is_empty(self) -> bool {
        self.from_block > self.to_block
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct LogKey {
    pub block_number: u64,
    pub transaction_hash: String,
    pub log_index: u64,
}

pub trait LogCsvRow: Serialize {
    fn log_key(&self) -> LogKey;
    fn csv_header() -> &'static [&'static str];
}

#[derive(Debug, Serialize)]
pub struct CollectionRunRecord {
    pub collector: String,
    pub chain: String,
    pub address: String,
    pub topic0: String,
    pub from_block: u64,
    pub to_block: u64,
    pub output: String,
    pub checkpoint: String,
    pub rows_written: u64,
    pub chunks_completed: u64,
    pub status: String,
    pub started_at_utc: String,
    pub finished_at_utc: String,
}

#[derive(Debug, Deserialize)]
struct RpcResponse<T> {
    result: Option<T>,
    error: Option<RpcError>,
}

#[derive(Debug, Deserialize)]
struct RpcError {
    code: i64,
    message: String,
}

#[derive(Debug, Deserialize)]
struct DedupeRecord {
    block_number: u64,
    transaction_hash: String,
    log_index: u64,
}

pub struct LogCsvWriter<T> {
    writer: csv::Writer<File>,
    seen: HashSet<LogKey>,
    total_rows: u64,
    _marker: PhantomData<T>,
}

impl<T> LogCsvWriter<T>
where
    T: LogCsvRow,
{
    pub fn open(path: &Path, append: bool) -> Result<Self> {
        ensure_parent_dir(path)?;

        let existing_non_empty = path.exists()
            && path
                .metadata()
                .with_context(|| format!("failed to stat {}", path.display()))?
                .len()
                > 0;

        let seen = if append && existing_non_empty {
            read_existing_log_keys(path)?
        } else {
            HashSet::new()
        };
        let total_rows = seen.len() as u64;

        let file = if append {
            OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .with_context(|| format!("failed to open {} for append", path.display()))?
        } else {
            File::create(path).with_context(|| format!("failed to create {}", path.display()))?
        };

        let write_header = !append || !existing_non_empty;
        let mut writer = csv::WriterBuilder::new()
            .has_headers(false)
            .from_writer(file);
        if write_header {
            writer.write_record(T::csv_header())?;
            writer.flush()?;
        }

        Ok(Self {
            writer,
            seen,
            total_rows,
            _marker: PhantomData,
        })
    }

    pub fn append_new(&mut self, rows: &[T]) -> Result<Vec<usize>> {
        let mut written_indexes = Vec::new();
        for (index, row) in rows.iter().enumerate() {
            if self.seen.insert(row.log_key()) {
                self.writer.serialize(row)?;
                self.total_rows += 1;
                written_indexes.push(index);
            }
        }
        Ok(written_indexes)
    }

    pub fn flush(&mut self) -> Result<()> {
        self.writer.flush().context("failed to flush CSV writer")
    }

    pub fn total_rows(&self) -> u64 {
        self.total_rows
    }
}

pub fn resolve_block_range(
    blocks: u64,
    latest_block: u64,
    from_block: Option<u64>,
    to_block: Option<u64>,
    resume: bool,
    checkpoint: Option<&Checkpoint>,
) -> Result<BlockRange> {
    if blocks == 0 {
        bail!("--blocks must be greater than 0");
    }

    let to_block = to_block.unwrap_or(latest_block);
    let resolved_from = if let Some(from_block) = from_block {
        from_block
    } else if resume {
        if let Some(checkpoint) = checkpoint {
            checkpoint
                .last_completed_block
                .checked_add(1)
                .ok_or_else(|| anyhow!("checkpoint last_completed_block cannot advance"))?
        } else {
            to_block.saturating_sub(blocks - 1)
        }
    } else {
        to_block.saturating_sub(blocks - 1)
    };

    if from_block.is_some() && resolved_from > to_block {
        bail!("--from-block {resolved_from} is greater than --to-block/latest {to_block}");
    }

    Ok(BlockRange {
        from_block: resolved_from,
        to_block,
    })
}

pub fn checkpoint_path_for_output(output: &Path) -> PathBuf {
    let mut path = output.as_os_str().to_os_string();
    path.push(".checkpoint.json");
    PathBuf::from(path)
}

pub fn load_checkpoint(path: &Path) -> Result<Checkpoint> {
    let file = File::open(path)
        .with_context(|| format!("failed to open checkpoint {}", path.display()))?;
    serde_json::from_reader(file)
        .with_context(|| format!("failed to parse checkpoint {}", path.display()))
}

pub fn save_checkpoint(path: &Path, checkpoint: &Checkpoint) -> Result<()> {
    ensure_parent_dir(path)?;
    let file = File::create(path)
        .with_context(|| format!("failed to create checkpoint {}", path.display()))?;
    serde_json::to_writer_pretty(file, checkpoint)
        .with_context(|| format!("failed to write checkpoint {}", path.display()))
}

pub fn validate_checkpoint_identity(
    checkpoint: &Checkpoint,
    collector: &str,
    chain: &str,
    address: &str,
    topic0: &str,
) -> Result<()> {
    if checkpoint.version != CHECKPOINT_VERSION {
        bail!(
            "unsupported checkpoint version {}; expected {}",
            checkpoint.version,
            CHECKPOINT_VERSION
        );
    }
    if checkpoint.collector != collector {
        bail!(
            "checkpoint collector mismatch: got {}, expected {}",
            checkpoint.collector,
            collector
        );
    }
    if !checkpoint.chain.eq_ignore_ascii_case(chain) {
        bail!(
            "checkpoint chain mismatch: got {}, expected {}",
            checkpoint.chain,
            chain
        );
    }
    if !checkpoint.address.eq_ignore_ascii_case(address) {
        bail!(
            "checkpoint address mismatch: got {}, expected {}",
            checkpoint.address,
            address
        );
    }
    if !checkpoint.topic0.eq_ignore_ascii_case(topic0) {
        bail!("checkpoint topic0 mismatch");
    }

    Ok(())
}

pub fn append_collection_run(path: &Path, record: &CollectionRunRecord) -> Result<()> {
    ensure_parent_dir(path)?;
    let existing_non_empty = path.exists()
        && path
            .metadata()
            .with_context(|| format!("failed to stat {}", path.display()))?
            .len()
            > 0;

    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .with_context(|| format!("failed to open run manifest {}", path.display()))?;
    let mut writer = csv::WriterBuilder::new()
        .has_headers(!existing_non_empty)
        .from_writer(file);
    writer.serialize(record)?;
    writer.flush()?;
    Ok(())
}

pub fn rpc_call_hex_u64(
    client: &Client,
    rpc_url: &str,
    method: &str,
    params: Value,
) -> Result<u64> {
    let value: String = rpc_call(client, rpc_url, method, params)?;
    parse_hex_u64(&value)
}

pub fn rpc_call_hex_u64_from_pool(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    method: &str,
    params: Value,
) -> Result<u64> {
    let value: String = rpc_call_from_pool(client, rpc_urls, method, params)?;
    parse_hex_u64(&value)
}

pub fn rpc_call_from_pool<T: for<'de> Deserialize<'de>>(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    method: &str,
    params: Value,
) -> Result<T> {
    let mut last_error = None;
    for _ in 0..rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_call(client, rpc_url, method, params.clone()) {
            Ok(value) => return Ok(value),
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("RPC pool has no URLs")))
}

pub fn rpc_call<T: for<'de> Deserialize<'de>>(
    client: &Client,
    rpc_url: &str,
    method: &str,
    params: Value,
) -> Result<T> {
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

    let response: RpcResponse<T> = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse RPC response: {text}"))?;
    if let Some(error) = response.error {
        bail!("RPC error {} from {method}: {}", error.code, error.message);
    }

    response
        .result
        .ok_or_else(|| anyhow!("RPC response from {method} did not include result"))
}

pub fn parse_hex_u64(value: &str) -> Result<u64> {
    u64::from_str_radix(value.trim_start_matches("0x"), 16)
        .with_context(|| format!("invalid hex u64: {value}"))
}

pub fn to_hex(value: u64) -> String {
    format!("0x{value:x}")
}

pub fn utc_now_string() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true)
}

pub fn repo_date_path(filename: &str) -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir.parent().unwrap_or(&manifest_dir);
    repo_root.join("date").join(filename)
}

pub fn read_existing_log_keys(path: &Path) -> Result<HashSet<LogKey>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to read {}", path.display()))?;
    let mut keys = HashSet::new();
    for row in reader.deserialize::<DedupeRecord>() {
        let row = row.with_context(|| format!("failed to parse {}", path.display()))?;
        keys.insert(LogKey {
            block_number: row.block_number,
            transaction_hash: row.transaction_hash,
            log_index: row.log_index,
        });
    }
    Ok(keys)
}

fn ensure_parent_dir(path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug, Serialize)]
    struct TestRow {
        block_number: u64,
        transaction_hash: String,
        log_index: u64,
        value: String,
    }

    impl LogCsvRow for TestRow {
        fn log_key(&self) -> LogKey {
            LogKey {
                block_number: self.block_number,
                transaction_hash: self.transaction_hash.clone(),
                log_index: self.log_index,
            }
        }

        fn csv_header() -> &'static [&'static str] {
            &["block_number", "transaction_hash", "log_index", "value"]
        }
    }

    #[test]
    fn resolves_default_recent_range() {
        let range = resolve_block_range(200, 1_000, None, None, false, None).unwrap();
        assert_eq!(
            range,
            BlockRange {
                from_block: 801,
                to_block: 1_000
            }
        );
    }

    #[test]
    fn explicit_from_block_has_priority_over_resume() {
        let checkpoint = sample_checkpoint(500);
        let range =
            resolve_block_range(200, 1_000, Some(700), Some(900), true, Some(&checkpoint)).unwrap();
        assert_eq!(
            range,
            BlockRange {
                from_block: 700,
                to_block: 900
            }
        );
    }

    #[test]
    fn resume_starts_after_last_completed_block() {
        let checkpoint = sample_checkpoint(850);
        let range = resolve_block_range(200, 1_000, None, None, true, Some(&checkpoint)).unwrap();
        assert_eq!(
            range,
            BlockRange {
                from_block: 851,
                to_block: 1_000
            }
        );
    }

    #[test]
    fn resume_can_be_empty_when_checkpoint_is_at_head() {
        let checkpoint = sample_checkpoint(1_000);
        let range = resolve_block_range(200, 1_000, None, None, true, Some(&checkpoint)).unwrap();
        assert!(range.is_empty());
        assert_eq!(range.from_block, 1_001);
        assert_eq!(range.to_block, 1_000);
    }

    #[test]
    fn checkpoint_round_trips() {
        let path = temp_path("checkpoint_round_trips.json");
        let checkpoint = sample_checkpoint(900);
        save_checkpoint(&path, &checkpoint).unwrap();
        let loaded = load_checkpoint(&path).unwrap();
        assert_eq!(loaded, checkpoint);
        let _ = fs::remove_file(path);
    }

    #[test]
    fn append_csv_dedupes_and_does_not_repeat_header() {
        let path = temp_path("append_csv_dedupes.csv");
        let _ = fs::remove_file(&path);

        {
            let mut writer = LogCsvWriter::<TestRow>::open(&path, false).unwrap();
            let rows = vec![
                row(1, "0xa", 0, "first"),
                row(2, "0xb", 0, "second"),
                row(2, "0xb", 0, "duplicate-in-batch"),
            ];
            let written = writer.append_new(&rows).unwrap();
            writer.flush().unwrap();
            assert_eq!(written, vec![0, 1]);
            assert_eq!(writer.total_rows(), 2);
        }

        {
            let mut writer = LogCsvWriter::<TestRow>::open(&path, true).unwrap();
            let rows = vec![
                row(2, "0xb", 0, "duplicate-from-file"),
                row(3, "0xc", 1, "third"),
            ];
            let written = writer.append_new(&rows).unwrap();
            writer.flush().unwrap();
            assert_eq!(written, vec![1]);
            assert_eq!(writer.total_rows(), 3);
        }

        let body = fs::read_to_string(&path).unwrap();
        assert_eq!(
            body.matches("block_number,transaction_hash,log_index,value")
                .count(),
            1
        );
        assert!(body.contains("1,0xa,0,first"));
        assert!(body.contains("2,0xb,0,second"));
        assert!(!body.contains("duplicate"));
        assert!(body.contains("3,0xc,1,third"));

        let _ = fs::remove_file(path);
    }

    #[test]
    fn csv_writer_writes_header_for_empty_outputs() {
        let path = temp_path("empty_csv_has_header.csv");
        let _ = fs::remove_file(&path);

        {
            let mut writer = LogCsvWriter::<TestRow>::open(&path, false).unwrap();
            writer.flush().unwrap();
        }
        {
            let mut writer = LogCsvWriter::<TestRow>::open(&path, true).unwrap();
            writer.flush().unwrap();
        }

        let body = fs::read_to_string(&path).unwrap();
        assert_eq!(
            body.matches("block_number,transaction_hash,log_index,value")
                .count(),
            1
        );
        assert_eq!(body.lines().count(), 1);

        let _ = fs::remove_file(path);
    }

    fn sample_checkpoint(last_completed_block: u64) -> Checkpoint {
        Checkpoint {
            version: CHECKPOINT_VERSION,
            collector: "collector".to_string(),
            chain: "monad".to_string(),
            address: "0xabc".to_string(),
            topic0: "0xtopic".to_string(),
            from_block: 1,
            to_block: 1_000,
            last_completed_block,
            rows_written: 0,
            output: "out.csv".to_string(),
            updated_at_utc: "2026-05-07T00:00:00Z".to_string(),
        }
    }

    fn row(block_number: u64, transaction_hash: &str, log_index: u64, value: &str) -> TestRow {
        TestRow {
            block_number,
            transaction_hash: transaction_hash.to_string(),
            log_index,
            value: value.to_string(),
        }
    }

    fn temp_path(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "finance_chain_{}_{}_{}",
            std::process::id(),
            Utc::now()
                .timestamp_nanos_opt()
                .unwrap_or_else(|| Utc::now().timestamp_micros()),
            name
        ))
    }
}

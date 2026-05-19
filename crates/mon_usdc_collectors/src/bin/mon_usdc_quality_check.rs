use std::collections::HashSet;
use std::fs::File;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, StringArray, UInt64Array};
use chrono::DateTime;
use clap::Parser;
use finance_chain_core::storage::{COLLECTION_RUNS_DATASET, RAW_DIR, parquet_files_under};
use mon_usdc_collectors::enrichment::{
    DEBUG_TRACE_CALLS_DATASET, DEBUG_TRACE_SUMMARIES_DATASET, POOL_LIQUIDITY_WINDOWS_DATASET,
    POOL_STATE_SAMPLES_DATASET, TX_BODIES_DATASET, TX_RECEIPT_LOG_SUMMARIES_DATASET,
    TX_RECEIPT_LOGS_DATASET,
};
use mon_usdc_collectors::{
    EVENT_HEADERS_DATASET, POOL_SNAPSHOTS_DATASET, POOL_SWAP_LOGS_DATASET, TX_RECEIPTS_DATASET,
    default_data_root_path, discover_swap_event_blocks, existing_event_header_blocks,
    known_top4_pools, read_latest_pool_snapshots,
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

const RAW_DATASETS: &[&str] = &[
    POOL_SNAPSHOTS_DATASET,
    POOL_SWAP_LOGS_DATASET,
    EVENT_HEADERS_DATASET,
    TX_RECEIPTS_DATASET,
    TX_BODIES_DATASET,
    TX_RECEIPT_LOGS_DATASET,
    TX_RECEIPT_LOG_SUMMARIES_DATASET,
    POOL_STATE_SAMPLES_DATASET,
    POOL_LIQUIDITY_WINDOWS_DATASET,
    DEBUG_TRACE_SUMMARIES_DATASET,
    DEBUG_TRACE_CALLS_DATASET,
    COLLECTION_RUNS_DATASET,
];

#[derive(Debug, Parser)]
#[command(
    name = "mon_usdc_quality_check",
    about = "Run MON/USDC v1 Parquet coverage and sanity checks."
)]
struct Args {
    /// MON/USDC v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Only check rows and coverage at or after this block where block-scoped columns exist.
    #[arg(long)]
    from_block: Option<u64>,

    /// Only check rows and coverage at or before this block where block-scoped columns exist.
    #[arg(long)]
    to_block: Option<u64>,
}

#[derive(Default)]
struct QualityStats {
    files: u64,
    rows: u64,
    duplicate_keys: u64,
    request_status_errors: u64,
    utc_errors: u64,
    dt_errors: u64,
    price_errors: u64,
    unknown_direction: u64,
    zero_amount_swaps: u64,
}

#[derive(Clone, Copy)]
struct BlockRange {
    from_block: Option<u64>,
    to_block: Option<u64>,
}

impl BlockRange {
    fn new(from_block: Option<u64>, to_block: Option<u64>) -> Result<Self> {
        if let (Some(from), Some(to)) = (from_block, to_block) {
            if from > to {
                bail!("--from-block {from} is greater than --to-block {to}");
            }
        }
        Ok(Self {
            from_block,
            to_block,
        })
    }

    fn is_active(self) -> bool {
        self.from_block.is_some() || self.to_block.is_some()
    }

    fn contains(self, block: u64) -> bool {
        !self.from_block.map_or(false, |from| block < from)
            && !self.to_block.map_or(false, |to| block > to)
    }

    fn overlaps(self, from_block: u64, to_block: u64) -> bool {
        !self.from_block.map_or(false, |from| to_block < from)
            && !self.to_block.map_or(false, |to| from_block > to)
    }
}

struct RowFilter {
    include: Vec<bool>,
}

impl RowFilter {
    fn all(len: usize) -> Self {
        Self {
            include: vec![true; len],
        }
    }

    fn includes(&self, index: usize) -> bool {
        self.include[index]
    }

    fn count(&self) -> u64 {
        self.include.iter().filter(|include| **include).count() as u64
    }
}

fn main() -> Result<()> {
    let args = Args::parse();
    let data_root = args.data_root.unwrap_or_else(default_data_root_path);
    let range = BlockRange::new(args.from_block, args.to_block)?;
    if range.is_active() {
        println!(
            "block window: {}..{}",
            args.from_block
                .map(|block| block.to_string())
                .unwrap_or_else(|| "start".to_string()),
            args.to_block
                .map(|block| block.to_string())
                .unwrap_or_else(|| "end".to_string())
        );
    }
    let mut total = QualityStats::default();
    for dataset in RAW_DATASETS {
        let stats = check_dataset(&data_root.join(RAW_DIR).join(dataset), dataset, range)?;
        println!(
            "raw.{dataset}: files={} rows={} duplicate_keys={} request_status_errors={} utc_errors={} dt_errors={} price_errors={} unknown_direction={} zero_amount_swaps={}",
            stats.files,
            stats.rows,
            stats.duplicate_keys,
            stats.request_status_errors,
            stats.utc_errors,
            stats.dt_errors,
            stats.price_errors,
            stats.unknown_direction,
            stats.zero_amount_swaps
        );
        total.files += stats.files;
        total.rows += stats.rows;
        total.duplicate_keys += stats.duplicate_keys;
        total.request_status_errors += stats.request_status_errors;
        total.utc_errors += stats.utc_errors;
        total.dt_errors += stats.dt_errors;
        total.price_errors += stats.price_errors;
        total.unknown_direction += stats.unknown_direction;
        total.zero_amount_swaps += stats.zero_amount_swaps;
    }

    let snapshot_missing = missing_top4_snapshot_addresses(&data_root)?;
    let swap_missing = top4_pools_without_swaps(&data_root, range)?;
    let event_blocks = discover_swap_event_blocks(&data_root, args.from_block, args.to_block)?;
    let header_blocks = existing_event_header_blocks(&data_root)?;
    let scoped_header_blocks = header_blocks
        .iter()
        .filter(|block| range.contains(**block))
        .count();
    let missing_headers = event_blocks
        .keys()
        .filter(|block| !header_blocks.contains(block))
        .count() as u64;
    let swap_tx_hashes = all_swap_tx_hashes(&data_root, range)?;
    let receipt_hashes = all_receipt_hashes(&data_root, range)?;
    let missing_receipts = swap_tx_hashes
        .iter()
        .filter(|hash| !receipt_hashes.contains(*hash))
        .count() as u64;
    println!(
        "coverage: swap_blocks={} event_headers={} missing_event_headers={} swap_txs={} receipts={} missing_receipts={}",
        event_blocks.len(),
        scoped_header_blocks,
        missing_headers,
        swap_tx_hashes.len(),
        receipt_hashes.len(),
        missing_receipts
    );
    if !snapshot_missing.is_empty() {
        println!(
            "snapshot missing top4 pools: {}",
            snapshot_missing.join(",")
        );
    }
    if !swap_missing.is_empty() {
        println!("swap rows missing top4 pools: {}", swap_missing.join(","));
    }

    if total.duplicate_keys > 0
        || total.request_status_errors > 0
        || total.utc_errors > 0
        || total.dt_errors > 0
        || total.price_errors > 0
        || total.unknown_direction > 0
        || missing_headers > 0
        || missing_receipts > 0
        || !snapshot_missing.is_empty()
        || !swap_missing.is_empty()
        || swap_tx_hashes.is_empty()
    {
        bail!(
            "quality check failed: duplicate_keys={} request_status_errors={} utc_errors={} dt_errors={} price_errors={} unknown_direction={} zero_amount_swaps={} missing_headers={} missing_receipts={} snapshot_missing={} swap_missing={} swap_txs={}",
            total.duplicate_keys,
            total.request_status_errors,
            total.utc_errors,
            total.dt_errors,
            total.price_errors,
            total.unknown_direction,
            total.zero_amount_swaps,
            missing_headers,
            missing_receipts,
            snapshot_missing.len(),
            swap_missing.len(),
            swap_tx_hashes.len()
        );
    }

    println!(
        "quality check passed: files={} rows={}",
        total.files, total.rows
    );
    Ok(())
}

fn check_dataset(root: &Path, dataset: &str, range: BlockRange) -> Result<QualityStats> {
    let mut stats = QualityStats::default();
    let mut log_keys = HashSet::<(u64, String, u64)>::new();
    let mut block_numbers = HashSet::<u64>::new();
    let mut tx_hashes = HashSet::<String>::new();
    for path in parquet_files_under(root)? {
        let mut file_rows = 0u64;
        let partition_dt = partition_dt(&path);
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder.with_batch_size(4096).build()?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            let row_filter = row_filter_for_batch(&batch, range)?;
            let rows = row_filter.count();
            if rows == 0 {
                continue;
            }
            file_rows += rows;
            stats.rows += rows;
            stats.utc_errors += count_utc_errors(&batch, &row_filter)?;
            if let Some(partition_dt) = partition_dt.as_deref() {
                stats.dt_errors += count_dt_errors(&batch, partition_dt, &row_filter)?;
            }
            match dataset {
                POOL_SWAP_LOGS_DATASET => {
                    stats.duplicate_keys +=
                        count_duplicate_log_keys(&batch, &mut log_keys, &row_filter)?;
                    stats.zero_amount_swaps += count_zero_amount_swaps(&batch, &row_filter)?;
                    stats.price_errors += count_price_errors(&batch, &row_filter)?;
                    stats.unknown_direction += count_unknown_direction(&batch, &row_filter)?;
                }
                EVENT_HEADERS_DATASET => {
                    stats.duplicate_keys +=
                        count_duplicate_block_numbers(&batch, &mut block_numbers, &row_filter)?;
                }
                TX_RECEIPTS_DATASET => {
                    stats.duplicate_keys +=
                        count_duplicate_tx_hashes(&batch, &mut tx_hashes, &row_filter)?;
                    stats.request_status_errors +=
                        count_receipt_error_statuses(&batch, &row_filter)?;
                }
                TX_BODIES_DATASET | TX_RECEIPT_LOG_SUMMARIES_DATASET => {
                    stats.duplicate_keys +=
                        count_duplicate_tx_hashes(&batch, &mut tx_hashes, &row_filter)?;
                    stats.request_status_errors +=
                        count_request_status_errors(&batch, &row_filter)?;
                }
                DEBUG_TRACE_SUMMARIES_DATASET => {
                    stats.duplicate_keys +=
                        count_duplicate_tx_hashes(&batch, &mut tx_hashes, &row_filter)?;
                }
                _ => {}
            }
        }
        if file_rows > 0 {
            stats.files += 1;
        }
    }
    Ok(stats)
}

fn row_filter_for_batch(
    batch: &arrow::record_batch::RecordBatch,
    range: BlockRange,
) -> Result<RowFilter> {
    if !range.is_active() {
        return Ok(RowFilter::all(batch.num_rows()));
    }
    if batch.schema().index_of("block_number").is_ok() {
        let block_number = uint64_column(batch, "block_number")?;
        let include = (0..batch.num_rows())
            .map(|index| !block_number.is_null(index) && range.contains(block_number.value(index)))
            .collect();
        return Ok(RowFilter { include });
    }
    if batch.schema().index_of("from_block").is_ok() && batch.schema().index_of("to_block").is_ok()
    {
        let from_block = uint64_column(batch, "from_block")?;
        let to_block = uint64_column(batch, "to_block")?;
        let include = (0..batch.num_rows())
            .map(|index| {
                !from_block.is_null(index)
                    && !to_block.is_null(index)
                    && range.overlaps(from_block.value(index), to_block.value(index))
            })
            .collect();
        return Ok(RowFilter { include });
    }
    Ok(RowFilter::all(batch.num_rows()))
}

fn missing_top4_snapshot_addresses(data_root: &Path) -> Result<Vec<String>> {
    let latest = read_latest_pool_snapshots(data_root)?;
    let latest = latest
        .iter()
        .map(|pool| pool.pair_address.to_ascii_lowercase())
        .collect::<HashSet<_>>();
    Ok(known_top4_pools()
        .into_iter()
        .map(|pool| pool.pair_address.to_ascii_lowercase())
        .filter(|address| !latest.contains(address))
        .collect())
}

fn top4_pools_without_swaps(data_root: &Path, range: BlockRange) -> Result<Vec<String>> {
    let mut present = HashSet::<String>::new();
    let root = data_root.join(RAW_DIR).join(POOL_SWAP_LOGS_DATASET);
    for path in parquet_files_under(&root)? {
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder.with_batch_size(4096).build()?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            let row_filter = row_filter_for_batch(&batch, range)?;
            let pool_address = string_column(&batch, "pool_address")?;
            for index in 0..batch.num_rows() {
                if !row_filter.includes(index) {
                    continue;
                }
                if !pool_address.is_null(index) && !pool_address.value(index).is_empty() {
                    present.insert(pool_address.value(index).to_ascii_lowercase());
                }
            }
        }
    }
    Ok(known_top4_pools()
        .into_iter()
        .map(|pool| pool.pair_address.to_ascii_lowercase())
        .filter(|address| !present.contains(address))
        .collect())
}

fn all_swap_tx_hashes(data_root: &Path, range: BlockRange) -> Result<HashSet<String>> {
    let mut hashes = HashSet::new();
    let root = data_root.join(RAW_DIR).join(POOL_SWAP_LOGS_DATASET);
    for path in parquet_files_under(&root)? {
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder.with_batch_size(4096).build()?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            let row_filter = row_filter_for_batch(&batch, range)?;
            let transaction_hash = string_column(&batch, "transaction_hash")?;
            for index in 0..batch.num_rows() {
                if !row_filter.includes(index) {
                    continue;
                }
                if !transaction_hash.is_null(index) && !transaction_hash.value(index).is_empty() {
                    hashes.insert(transaction_hash.value(index).to_string());
                }
            }
        }
    }
    Ok(hashes)
}

fn all_receipt_hashes(data_root: &Path, range: BlockRange) -> Result<HashSet<String>> {
    let mut hashes = HashSet::new();
    let root = data_root.join(RAW_DIR).join(TX_RECEIPTS_DATASET);
    for path in parquet_files_under(&root)? {
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder.with_batch_size(4096).build()?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            let row_filter = row_filter_for_batch(&batch, range)?;
            let transaction_hash = string_column(&batch, "transaction_hash")?;
            for index in 0..batch.num_rows() {
                if !row_filter.includes(index) {
                    continue;
                }
                if !transaction_hash.is_null(index) && !transaction_hash.value(index).is_empty() {
                    hashes.insert(transaction_hash.value(index).to_string());
                }
            }
        }
    }
    Ok(hashes)
}

fn count_duplicate_log_keys(
    batch: &arrow::record_batch::RecordBatch,
    seen: &mut HashSet<(u64, String, u64)>,
    row_filter: &RowFilter,
) -> Result<u64> {
    let block_number = uint64_column(batch, "block_number")?;
    let transaction_hash = string_column(batch, "transaction_hash")?;
    let log_index = uint64_column(batch, "log_index")?;
    let mut duplicates = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) {
            continue;
        }
        if block_number.is_null(index)
            || transaction_hash.is_null(index)
            || log_index.is_null(index)
        {
            continue;
        }
        let key = (
            block_number.value(index),
            transaction_hash.value(index).to_string(),
            log_index.value(index),
        );
        if !seen.insert(key) {
            duplicates += 1;
        }
    }
    Ok(duplicates)
}

fn count_duplicate_block_numbers(
    batch: &arrow::record_batch::RecordBatch,
    seen: &mut HashSet<u64>,
    row_filter: &RowFilter,
) -> Result<u64> {
    let block_number = uint64_column(batch, "block_number")?;
    let mut duplicates = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) {
            continue;
        }
        if !block_number.is_null(index) && !seen.insert(block_number.value(index)) {
            duplicates += 1;
        }
    }
    Ok(duplicates)
}

fn count_duplicate_tx_hashes(
    batch: &arrow::record_batch::RecordBatch,
    seen: &mut HashSet<String>,
    row_filter: &RowFilter,
) -> Result<u64> {
    let transaction_hash = string_column(batch, "transaction_hash")?;
    let mut duplicates = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) {
            continue;
        }
        if !transaction_hash.is_null(index)
            && !seen.insert(transaction_hash.value(index).to_string())
        {
            duplicates += 1;
        }
    }
    Ok(duplicates)
}

fn count_receipt_error_statuses(
    batch: &arrow::record_batch::RecordBatch,
    row_filter: &RowFilter,
) -> Result<u64> {
    let request_status = string_column(batch, "request_status")?;
    let mut errors = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) {
            continue;
        }
        if request_status.is_null(index) {
            continue;
        }
        let value = request_status.value(index);
        if value.contains("error") || value == "missing_receipt" {
            errors += 1;
        }
    }
    Ok(errors)
}

fn count_request_status_errors(
    batch: &arrow::record_batch::RecordBatch,
    row_filter: &RowFilter,
) -> Result<u64> {
    if batch.schema().index_of("request_status").is_err() {
        return Ok(0);
    }
    let request_status = string_column(batch, "request_status")?;
    let mut errors = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) || request_status.is_null(index) {
            continue;
        }
        let value = request_status.value(index);
        if value.contains("error") || value.starts_with("missing") {
            errors += 1;
        }
    }
    Ok(errors)
}

fn count_price_errors(
    batch: &arrow::record_batch::RecordBatch,
    row_filter: &RowFilter,
) -> Result<u64> {
    let price = string_column(batch, "price_quote_per_base")?;
    let base_abs = string_column(batch, "base_abs")?;
    let quote_abs = string_column(batch, "quote_abs")?;
    let mut errors = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) {
            continue;
        }
        if is_zero_amount(base_abs, index) || is_zero_amount(quote_abs, index) {
            continue;
        }
        let value = if price.is_null(index) {
            ""
        } else {
            price.value(index)
        };
        if value.parse::<f64>().map_or(true, |value| value <= 0.0) {
            errors += 1;
        }
    }
    Ok(errors)
}

fn count_unknown_direction(
    batch: &arrow::record_batch::RecordBatch,
    row_filter: &RowFilter,
) -> Result<u64> {
    let direction = string_column(batch, "direction")?;
    let base_abs = string_column(batch, "base_abs")?;
    let mut errors = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) {
            continue;
        }
        if is_zero_amount(base_abs, index) {
            continue;
        }
        if direction.is_null(index) || direction.value(index) == "unknown" {
            errors += 1;
        }
    }
    Ok(errors)
}

fn count_zero_amount_swaps(
    batch: &arrow::record_batch::RecordBatch,
    row_filter: &RowFilter,
) -> Result<u64> {
    let base_abs = string_column(batch, "base_abs")?;
    let quote_abs = string_column(batch, "quote_abs")?;
    let mut zero_amount = 0;
    for index in 0..batch.num_rows() {
        if !row_filter.includes(index) {
            continue;
        }
        if is_zero_amount(base_abs, index) || is_zero_amount(quote_abs, index) {
            zero_amount += 1;
        }
    }
    Ok(zero_amount)
}

fn is_zero_amount(values: &StringArray, index: usize) -> bool {
    if values.is_null(index) {
        return true;
    }
    values
        .value(index)
        .parse::<f64>()
        .map_or(true, |value| value == 0.0)
}

fn count_utc_errors(
    batch: &arrow::record_batch::RecordBatch,
    row_filter: &RowFilter,
) -> Result<u64> {
    let mut errors = 0;
    for (index, field) in batch.schema().fields().iter().enumerate() {
        if !field.name().ends_with("_utc") {
            continue;
        }
        let Some(values) = batch.column(index).as_any().downcast_ref::<StringArray>() else {
            continue;
        };
        for row in 0..values.len() {
            if !row_filter.includes(row) {
                continue;
            }
            if values.is_null(row) || values.value(row).is_empty() {
                continue;
            }
            let value = values.value(row);
            if !value.ends_with('Z') || DateTime::parse_from_rfc3339(value).is_err() {
                errors += 1;
            }
        }
    }
    Ok(errors)
}

fn count_dt_errors(
    batch: &arrow::record_batch::RecordBatch,
    partition_dt: &str,
    row_filter: &RowFilter,
) -> Result<u64> {
    let Ok(index) = batch.schema().index_of("dt") else {
        return Ok(0);
    };
    let Some(values) = batch.column(index).as_any().downcast_ref::<StringArray>() else {
        return Ok(batch.num_rows() as u64);
    };
    let mut errors = 0;
    for row in 0..values.len() {
        if !row_filter.includes(row) {
            continue;
        }
        if values.is_null(row) || values.value(row) != partition_dt {
            errors += 1;
        }
    }
    Ok(errors)
}

fn uint64_column<'a>(
    batch: &'a arrow::record_batch::RecordBatch,
    name: &str,
) -> Result<&'a UInt64Array> {
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

fn string_column<'a>(
    batch: &'a arrow::record_batch::RecordBatch,
    name: &str,
) -> Result<&'a StringArray> {
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

fn partition_dt(path: &Path) -> Option<String> {
    path.components()
        .filter_map(|component| component.as_os_str().to_str())
        .find_map(|part| part.strip_prefix("dt=").map(ToOwned::to_owned))
}

use std::collections::HashSet;
use std::fs::File;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, StringArray, UInt64Array};
use chog_prices::{
    Checkpoint,
    chog_v1::{RAW_DIR, checkpoint_path, default_data_root_path, parquet_files_under},
    dex_factors::DEX_SWAP_FACTORS_DATASET,
    dex_hourly::{DERIVED_DIR, DEX_POOL_SWAP_HOURLY_DATASET},
    load_checkpoint,
    memecoin_features::{MEMECOIN_EVENT_FEATURES_DATASET, MEMECOIN_HOURLY_FEATURES_DATASET},
};
use chrono::DateTime;
use clap::Parser;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

const DATASETS: &[&str] = &[
    "main_pool_swap_logs",
    "dex_pool_swap_logs",
    "erc20_transfer_logs",
    "dex_pairs_snapshots",
    "tx_receipts",
    "block_headers",
    "event_block_headers",
    "prices_hourly",
    "collection_runs",
];
const DERIVED_DATASETS: &[&str] = &[
    DEX_POOL_SWAP_HOURLY_DATASET,
    DEX_SWAP_FACTORS_DATASET,
    MEMECOIN_EVENT_FEATURES_DATASET,
    MEMECOIN_HOURLY_FEATURES_DATASET,
];
const CHECKPOINTS: &[&str] = &[
    "transfer_sample",
    "v3_swap_sample",
    "block_header_sample",
    "event_header_sample",
    "receipt_sample",
    "chog_prices",
];

#[derive(Debug, Parser)]
#[command(
    name = "chog_quality_check",
    about = "Run CHOG v1 Parquet data quality checks."
)]
struct Args {
    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,
}

#[derive(Default)]
struct QualityStats {
    files: u64,
    rows: u64,
    duplicate_keys: u64,
    request_status_errors: u64,
    utc_errors: u64,
    dt_errors: u64,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let data_root = args.data_root.unwrap_or_else(default_data_root_path);
    let mut total = QualityStats::default();

    for dataset in DATASETS {
        let stats = check_dataset(&data_root.join(RAW_DIR).join(dataset), dataset)?;
        println!(
            "raw.{dataset}: files={} rows={} duplicate_keys={} request_status_errors={} utc_errors={} dt_errors={}",
            stats.files,
            stats.rows,
            stats.duplicate_keys,
            stats.request_status_errors,
            stats.utc_errors,
            stats.dt_errors
        );
        total.files += stats.files;
        total.rows += stats.rows;
        total.duplicate_keys += stats.duplicate_keys;
        total.request_status_errors += stats.request_status_errors;
        total.utc_errors += stats.utc_errors;
        total.dt_errors += stats.dt_errors;
    }

    for dataset in DERIVED_DATASETS {
        let stats = check_dataset(&data_root.join(DERIVED_DIR).join(dataset), dataset)?;
        println!(
            "derived.{dataset}: files={} rows={} duplicate_keys={} request_status_errors={} utc_errors={} dt_errors={}",
            stats.files,
            stats.rows,
            stats.duplicate_keys,
            stats.request_status_errors,
            stats.utc_errors,
            stats.dt_errors
        );
        total.files += stats.files;
        total.rows += stats.rows;
        total.duplicate_keys += stats.duplicate_keys;
        total.request_status_errors += stats.request_status_errors;
        total.utc_errors += stats.utc_errors;
        total.dt_errors += stats.dt_errors;
    }

    check_checkpoints(&data_root)?;

    if total.duplicate_keys > 0
        || total.request_status_errors > 0
        || total.utc_errors > 0
        || total.dt_errors > 0
    {
        bail!(
            "quality check failed: duplicate_keys={} request_status_errors={} utc_errors={} dt_errors={}",
            total.duplicate_keys,
            total.request_status_errors,
            total.utc_errors,
            total.dt_errors
        );
    }
    println!(
        "quality check passed: files={} rows={}",
        total.files, total.rows
    );
    Ok(())
}

fn check_dataset(root: &Path, dataset: &str) -> Result<QualityStats> {
    let mut stats = QualityStats::default();
    let mut log_keys = HashSet::<(u64, String, u64)>::new();
    let mut tx_hashes = HashSet::<String>::new();
    let mut block_numbers = HashSet::<u64>::new();

    for path in parquet_files_under(&root)? {
        stats.files += 1;
        let partition_dt = partition_dt(&path);
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder
            .with_batch_size(2048)
            .build()
            .with_context(|| format!("failed to build parquet reader {}", path.display()))?;

        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            stats.rows += batch.num_rows() as u64;
            stats.utc_errors += count_utc_errors(&batch)?;
            if let Some(partition_dt) = partition_dt.as_deref() {
                stats.dt_errors += count_dt_errors(&batch, partition_dt)?;
            }

            if matches!(
                dataset,
                "main_pool_swap_logs"
                    | "dex_pool_swap_logs"
                    | "erc20_transfer_logs"
                    | DEX_SWAP_FACTORS_DATASET
            ) {
                stats.duplicate_keys += count_duplicate_log_keys(&batch, &mut log_keys)?;
            } else if dataset == "tx_receipts" {
                stats.duplicate_keys += count_duplicate_tx_hashes(&batch, &mut tx_hashes)?;
                stats.request_status_errors += count_receipt_error_statuses(&batch)?;
            } else if dataset == "event_block_headers" {
                stats.duplicate_keys += count_duplicate_block_numbers(&batch, &mut block_numbers)?;
            }
        }
    }
    Ok(stats)
}

fn count_duplicate_log_keys(
    batch: &arrow::record_batch::RecordBatch,
    seen: &mut HashSet<(u64, String, u64)>,
) -> Result<u64> {
    let block_number = uint64_column(batch, "block_number")?;
    let transaction_hash = string_column(batch, "transaction_hash")?;
    let log_index = uint64_column(batch, "log_index")?;
    let mut duplicates = 0;
    for index in 0..batch.num_rows() {
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

fn count_duplicate_tx_hashes(
    batch: &arrow::record_batch::RecordBatch,
    seen: &mut HashSet<String>,
) -> Result<u64> {
    let transaction_hash = string_column(batch, "transaction_hash")?;
    let mut duplicates = 0;
    for index in 0..batch.num_rows() {
        if transaction_hash.is_null(index) {
            continue;
        }
        if !seen.insert(transaction_hash.value(index).to_string()) {
            duplicates += 1;
        }
    }
    Ok(duplicates)
}

fn count_duplicate_block_numbers(
    batch: &arrow::record_batch::RecordBatch,
    seen: &mut HashSet<u64>,
) -> Result<u64> {
    let block_number = uint64_column(batch, "block_number")?;
    let mut duplicates = 0;
    for index in 0..batch.num_rows() {
        if block_number.is_null(index) {
            continue;
        }
        if !seen.insert(block_number.value(index)) {
            duplicates += 1;
        }
    }
    Ok(duplicates)
}

fn count_receipt_error_statuses(batch: &arrow::record_batch::RecordBatch) -> Result<u64> {
    let request_status = string_column(batch, "request_status")?;
    let mut errors = 0;
    for index in 0..batch.num_rows() {
        if !request_status.is_null(index) && request_status.value(index) == "error" {
            errors += 1;
        }
    }
    Ok(errors)
}

fn count_utc_errors(batch: &arrow::record_batch::RecordBatch) -> Result<u64> {
    let mut errors = 0;
    for (index, field) in batch.schema().fields().iter().enumerate() {
        if !field.name().ends_with("_utc") {
            continue;
        }
        let Some(values) = batch.column(index).as_any().downcast_ref::<StringArray>() else {
            continue;
        };
        for row in 0..values.len() {
            if values.is_null(row) {
                continue;
            }
            let value = values.value(row);
            if value.is_empty() {
                continue;
            }
            if !value.ends_with('Z') || DateTime::parse_from_rfc3339(value).is_err() {
                errors += 1;
            }
        }
    }
    Ok(errors)
}

fn count_dt_errors(batch: &arrow::record_batch::RecordBatch, partition_dt: &str) -> Result<u64> {
    let Ok(index) = batch.schema().index_of("dt") else {
        return Ok(0);
    };
    let Some(values) = batch.column(index).as_any().downcast_ref::<StringArray>() else {
        return Ok(batch.num_rows() as u64);
    };
    let mut errors = 0;
    for row in 0..values.len() {
        if values.is_null(row) || values.value(row) != partition_dt {
            errors += 1;
        }
    }
    Ok(errors)
}

fn check_checkpoints(data_root: &Path) -> Result<()> {
    for collector in CHECKPOINTS {
        let path = checkpoint_path(data_root, collector);
        if !path.exists() {
            continue;
        }
        let checkpoint: Checkpoint = load_checkpoint(&path)?;
        if checkpoint.last_completed_block > checkpoint.to_block && checkpoint.to_block != 0 {
            bail!(
                "checkpoint {} has last_completed_block {} beyond to_block {}",
                path.display(),
                checkpoint.last_completed_block,
                checkpoint.to_block
            );
        }
    }
    Ok(())
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

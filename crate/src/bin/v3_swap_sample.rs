use std::path::PathBuf;
use std::sync::Arc;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chog_prices::{
    CHECKPOINT_VERSION, Checkpoint, CollectionRunRecord, LogCsvRow, LogCsvWriter, LogKey,
    RpcUrlPool, append_collection_run, checkpoint_path_for_output,
    chog_v1::{
        ChogCollectionRunRecord, OutputFormat, PartWrite, PartWriteStatus, bool_array,
        checkpoint_path_with_suffix, default_data_root_path, dt_from_utc_string,
        part_paths_to_string, rpc_part_path, string_array, u64_array, write_collection_run_parquet,
        write_parquet_part, write_schema_metadata,
    },
    load_checkpoint, parse_hex_u64, repo_date_path, resolve_block_range, rpc_call,
    rpc_call_hex_u64_from_pool, save_checkpoint, to_hex, utc_now_string,
    validate_checkpoint_identity,
};
use chrono::{DateTime, SecondsFormat, Utc};
use clap::Parser;
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::json;

const DEFAULT_RPC_URL: &str = "https://rpc.monad.xyz";
const DEFAULT_PAIR: &str = "0x116e7D070f1888B81E1E0324F56d6746B2D7d8f1";
const DEFAULT_BLOCKS: u64 = 20_000;
const DEFAULT_LOG_RANGE_BLOCKS: u64 = 100;
const MAX_RETRIES: usize = 3;
const COLLECTOR: &str = "v3_swap_sample";
const CHAIN: &str = "monad";
const SWAP_TOPIC: &str = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67";
const TOKEN0_SYMBOL: &str = "CHOG";
const TOKEN1_SYMBOL: &str = "MON";
const TOKEN0_DECIMALS: i32 = 18;
const TOKEN1_DECIMALS: i32 = 18;
const DATASET: &str = "main_pool_swap_logs";

#[derive(Debug, Parser)]
#[command(
    name = "v3_swap_sample",
    about = "Fetch recent Uniswap V3-style Swap logs for the CHOG/MON main pool."
)]
struct Args {
    #[arg(long = "rpc-url", default_value = DEFAULT_RPC_URL)]
    rpc_url: Vec<String>,

    #[arg(long, default_value = DEFAULT_PAIR)]
    pair: String,

    /// Recent block count to scan. Monad public RPC limits eth_getLogs to 100 blocks per request.
    #[arg(long, default_value_t = DEFAULT_BLOCKS)]
    blocks: u64,

    /// Block range size per eth_getLogs request.
    #[arg(long, default_value_t = DEFAULT_LOG_RANGE_BLOCKS)]
    log_range_blocks: u64,

    /// Explicit first block to scan. Takes precedence over --resume and --blocks.
    #[arg(long)]
    from_block: Option<u64>,

    /// Explicit final block to scan. Defaults to latest block at run start.
    #[arg(long)]
    to_block: Option<u64>,

    /// Resume from checkpoint last_completed_block + 1 when a checkpoint exists.
    #[arg(long)]
    resume: bool,

    /// Checkpoint path. Defaults to <output>.checkpoint.json.
    #[arg(long)]
    checkpoint: Option<PathBuf>,

    /// Suffix for the default Parquet checkpoint filename, useful for parallel shards.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Append to CSV and dedupe by (block_number, transaction_hash, log_index).
    #[arg(long)]
    append: bool,

    /// Output format. CSV preserves the legacy path; Parquet writes CHOG v1 parts.
    #[arg(long, value_enum, default_value_t = OutputFormat::Csv)]
    format: OutputFormat,

    /// CHOG v1 data root used when --format parquet.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Resolve the block window and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,

    #[arg(long)]
    output: Option<PathBuf>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SwapLog {
    address: String,
    topics: Vec<String>,
    data: String,
    block_number: String,
    block_timestamp: Option<String>,
    transaction_hash: String,
    transaction_index: String,
    log_index: String,
    removed: bool,
}

#[derive(Debug, Clone, Serialize)]
struct CsvSwap {
    fetched_at_utc: String,
    block_number: u64,
    block_timestamp: u64,
    block_datetime_utc: String,
    transaction_hash: String,
    transaction_index: u64,
    log_index: u64,
    pair_address: String,
    sender: String,
    recipient: String,
    amount0_raw: String,
    amount1_raw: String,
    amount0_token: String,
    amount1_token: String,
    token0_symbol: String,
    token1_symbol: String,
    direction: String,
    chog_abs: String,
    mon_abs: String,
    price_mon_per_chog: String,
    sqrt_price_x96: String,
    liquidity_raw: String,
    tick: i128,
    removed: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    match args.format {
        OutputFormat::Csv => run_csv(args),
        OutputFormat::Parquet => run_parquet(args),
    }
}

fn run_csv(args: Args) -> Result<()> {
    if args.blocks == 0 {
        bail!("--blocks must be greater than 0");
    }
    if args.log_range_blocks == 0 {
        bail!("--log-range-blocks must be greater than 0");
    }

    let output = args.output.clone().unwrap_or_else(default_output_path);
    let checkpoint_path = args
        .checkpoint
        .clone()
        .unwrap_or_else(|| checkpoint_path_for_output(&output));
    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-v3-swap-sample/0.1")
        .build()
        .context("failed to build HTTP client")?;

    let rpc_urls = RpcUrlPool::from_values(&args.rpc_url, DEFAULT_RPC_URL)?;
    let latest_block =
        rpc_call_hex_u64_from_pool(&client, &rpc_urls, "eth_blockNumber", json!([]))?;
    let checkpoint = if args.resume && args.from_block.is_none() && checkpoint_path.exists() {
        let checkpoint = load_checkpoint(&checkpoint_path)?;
        validate_checkpoint_identity(&checkpoint, COLLECTOR, CHAIN, &args.pair, SWAP_TOPIC)?;
        Some(checkpoint)
    } else {
        None
    };
    let range = resolve_block_range(
        args.blocks,
        latest_block,
        args.from_block,
        args.to_block,
        args.resume,
        checkpoint.as_ref(),
    )?;

    let mut writer = None;
    let mut written_rows = Vec::new();
    let mut chunks_completed = 0u64;
    let mut start = range.from_block;
    while start <= range.to_block {
        let end = range
            .to_block
            .min(start.saturating_add(args.log_range_blocks - 1));
        let logs = fetch_swap_logs_with_retry(&client, &rpc_urls, &args.pair, start, end)
            .with_context(|| format!("failed to fetch swap logs for blocks {start}..{end}"))?;

        let mut chunk_rows = Vec::new();
        for log in logs {
            chunk_rows.push(parse_log(&fetched_at, log)?);
        }
        chunk_rows.sort_by_key(|row| (row.block_number, row.transaction_index, row.log_index));

        if writer.is_none() {
            writer = Some(LogCsvWriter::<CsvSwap>::open(&output, args.append)?);
        }
        let writer = writer.as_mut().expect("writer is initialized");
        let written_indexes = writer.append_new(&chunk_rows)?;
        writer.flush()?;
        for index in written_indexes {
            written_rows.push(chunk_rows[index].clone());
        }
        chunks_completed += 1;

        let checkpoint = Checkpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: args.pair.clone(),
            topic0: SWAP_TOPIC.to_string(),
            from_block: range.from_block,
            to_block: range.to_block,
            last_completed_block: end,
            rows_written: writer.total_rows(),
            output: output.display().to_string(),
            updated_at_utc: utc_now_string(),
        };
        save_checkpoint(&checkpoint_path, &checkpoint)?;

        if end == u64::MAX {
            break;
        }
        start = end + 1;
    }

    let finished_at = utc_now_string();
    let status = if range.is_empty() {
        "empty"
    } else {
        "completed"
    };
    append_collection_run(
        &repo_date_path("chog_collection_runs.csv"),
        &CollectionRunRecord {
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: args.pair.clone(),
            topic0: SWAP_TOPIC.to_string(),
            from_block: range.from_block,
            to_block: range.to_block,
            output: output.display().to_string(),
            checkpoint: checkpoint_path.display().to_string(),
            rows_written: written_rows.len() as u64,
            chunks_completed,
            status: status.to_string(),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;
    print_summary(&output, &written_rows, range.from_block, range.to_block);
    println!("checkpoint: {}", checkpoint_path.display());

    Ok(())
}

fn run_parquet(args: Args) -> Result<()> {
    if args.blocks == 0 {
        bail!("--blocks must be greater than 0");
    }
    if args.log_range_blocks == 0 {
        bail!("--log-range-blocks must be greater than 0");
    }

    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    let checkpoint_path = if let Some(path) = args.checkpoint.clone() {
        path
    } else {
        checkpoint_path_with_suffix(&data_root, COLLECTOR, args.checkpoint_suffix.as_deref())?
    };
    let started_at = utc_now_string();
    let fetched_at = started_at.clone();
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-v3-swap-sample/0.1")
        .build()
        .context("failed to build HTTP client")?;

    let rpc_urls = RpcUrlPool::from_values(&args.rpc_url, DEFAULT_RPC_URL)?;
    let latest_block =
        rpc_call_hex_u64_from_pool(&client, &rpc_urls, "eth_blockNumber", json!([]))?;
    let checkpoint = if args.resume && args.from_block.is_none() && checkpoint_path.exists() {
        let checkpoint = load_checkpoint(&checkpoint_path)?;
        validate_checkpoint_identity(&checkpoint, COLLECTOR, CHAIN, &args.pair, SWAP_TOPIC)?;
        Some(checkpoint)
    } else {
        None
    };
    let range = resolve_block_range(
        args.blocks,
        latest_block,
        args.from_block,
        args.to_block,
        args.resume,
        checkpoint.as_ref(),
    )?;

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DATASET}");
        println!("block window: {}..{}", range.from_block, range.to_block);
        println!("data root: {}", data_root.display());
        println!("checkpoint: {}", checkpoint_path.display());
        return Ok(());
    }

    let schema = swap_schema();
    write_schema_metadata(&data_root, DATASET, schema.as_ref(), &["dt"])?;

    let mut output_parts = Vec::new();
    let mut rows_written = 0u64;
    let mut chunks_completed = 0u64;
    let mut start = range.from_block;
    while start <= range.to_block {
        let end = range
            .to_block
            .min(start.saturating_add(args.log_range_blocks - 1));
        let logs = fetch_swap_logs_with_retry(&client, &rpc_urls, &args.pair, start, end)
            .with_context(|| format!("failed to fetch swap logs for blocks {start}..{end}"))?;

        let mut chunk_rows = Vec::new();
        for log in logs {
            chunk_rows.push(parse_log(&fetched_at, log)?);
        }
        chunk_rows.sort_by_key(|row| (row.block_number, row.transaction_index, row.log_index));

        let parts = write_swap_parquet_parts(&data_root, schema.clone(), &chunk_rows, start, end)?;
        rows_written += parts
            .iter()
            .filter(|part| part.status == PartWriteStatus::Written)
            .map(|part| part.rows as u64)
            .sum::<u64>();
        output_parts.extend(parts);
        chunks_completed += 1;

        let checkpoint = Checkpoint {
            version: CHECKPOINT_VERSION,
            collector: COLLECTOR.to_string(),
            chain: CHAIN.to_string(),
            address: args.pair.clone(),
            topic0: SWAP_TOPIC.to_string(),
            from_block: range.from_block,
            to_block: range.to_block,
            last_completed_block: end,
            rows_written,
            output: part_paths_to_string(&output_parts),
            updated_at_utc: utc_now_string(),
        };
        save_checkpoint(&checkpoint_path, &checkpoint)?;

        if end == u64::MAX {
            break;
        }
        start = end + 1;
    }

    let finished_at = utc_now_string();
    let status = if range.is_empty() {
        "empty"
    } else {
        "completed"
    };
    write_collection_run_parquet(
        &data_root,
        &ChogCollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: args.pair.clone(),
            topic0: SWAP_TOPIC.to_string(),
            from_block: Some(range.from_block),
            to_block: Some(range.to_block),
            time_window_start_utc: String::new(),
            time_window_end_utc: String::new(),
            output_parts: part_paths_to_string(&output_parts),
            rows_written,
            chunks_completed,
            status: status.to_string(),
            error: String::new(),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    println!("block window: {}..{}", range.from_block, range.to_block);
    println!("swap logs written: {rows_written}");
    println!("parquet parts: {}", output_parts.len());
    println!("data root: {}", data_root.display());
    println!("checkpoint: {}", checkpoint_path.display());

    Ok(())
}

impl LogCsvRow for CsvSwap {
    fn log_key(&self) -> LogKey {
        LogKey {
            block_number: self.block_number,
            transaction_hash: self.transaction_hash.clone(),
            log_index: self.log_index,
        }
    }

    fn csv_header() -> &'static [&'static str] {
        &[
            "fetched_at_utc",
            "block_number",
            "block_timestamp",
            "block_datetime_utc",
            "transaction_hash",
            "transaction_index",
            "log_index",
            "pair_address",
            "sender",
            "recipient",
            "amount0_raw",
            "amount1_raw",
            "amount0_token",
            "amount1_token",
            "token0_symbol",
            "token1_symbol",
            "direction",
            "chog_abs",
            "mon_abs",
            "price_mon_per_chog",
            "sqrt_price_x96",
            "liquidity_raw",
            "tick",
            "removed",
        ]
    }
}

fn swap_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, false),
        Field::new("block_timestamp", DataType::UInt64, false),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pair_address", DataType::Utf8, false),
        Field::new("sender", DataType::Utf8, false),
        Field::new("recipient", DataType::Utf8, false),
        Field::new("amount0_raw", DataType::Utf8, false),
        Field::new("amount1_raw", DataType::Utf8, false),
        Field::new("amount0_token", DataType::Utf8, false),
        Field::new("amount1_token", DataType::Utf8, false),
        Field::new("token0_symbol", DataType::Utf8, false),
        Field::new("token1_symbol", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("chog_abs", DataType::Utf8, false),
        Field::new("mon_abs", DataType::Utf8, false),
        Field::new("price_mon_per_chog", DataType::Utf8, false),
        Field::new("sqrt_price_x96", DataType::Utf8, false),
        Field::new("liquidity_raw", DataType::Utf8, false),
        Field::new("tick", DataType::Utf8, false),
        Field::new("removed", DataType::Boolean, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn write_swap_parquet_parts(
    data_root: &std::path::Path,
    schema: SchemaRef,
    rows: &[CsvSwap],
    from_block: u64,
    to_block: u64,
) -> Result<Vec<PartWrite>> {
    let mut by_dt = std::collections::BTreeMap::<String, Vec<CsvSwap>>::new();
    for row in rows {
        let dt = if row.block_datetime_utc.is_empty() {
            dt_from_utc_string(&row.fetched_at_utc)
        } else {
            dt_from_utc_string(&row.block_datetime_utc)
        };
        by_dt.entry(dt).or_default().push(row.clone());
    }

    let mut parts = Vec::new();
    for (dt, rows) in by_dt {
        let dt_values = vec![dt.clone(); rows.len()];
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.fetched_at_utc.clone())
                        .collect::<Vec<_>>(),
                ),
                u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
                u64_array(
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
                        .map(|row| row.pair_address.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.sender.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.recipient.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount0_raw.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount1_raw.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount0_token.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount1_token.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.token0_symbol.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.token1_symbol.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.direction.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.chog_abs.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.mon_abs.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.price_mon_per_chog.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.sqrt_price_x96.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.liquidity_raw.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.tick.to_string())
                        .collect::<Vec<_>>(),
                ),
                bool_array(&rows.iter().map(|row| row.removed).collect::<Vec<_>>()),
                string_array(&dt_values),
            ],
        )?;
        parts.push(write_parquet_part(
            &rpc_part_path(data_root, DATASET, &dt, COLLECTOR, from_block, to_block),
            schema.clone(),
            batch,
        )?);
    }

    Ok(parts)
}

fn fetch_swap_logs_with_retry(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pair: &str,
    from_block: u64,
    to_block: u64,
) -> Result<Vec<SwapLog>> {
    let mut last_error = None;
    let max_attempts = MAX_RETRIES * rpc_urls.len();
    for attempt in 1..=max_attempts {
        let rpc_url = rpc_urls.next_url();
        match fetch_swap_logs(client, rpc_url, pair, from_block, to_block) {
            Ok(logs) => return Ok(logs),
            Err(error) => {
                last_error = Some(error);
                if attempt < max_attempts {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }

    Err(last_error.unwrap_or_else(|| anyhow!("swap log fetch failed without an error")))
}

fn fetch_swap_logs(
    client: &Client,
    rpc_url: &str,
    pair: &str,
    from_block: u64,
    to_block: u64,
) -> Result<Vec<SwapLog>> {
    let params = json!([
        {
            "address": pair,
            "fromBlock": to_hex(from_block),
            "toBlock": to_hex(to_block),
            "topics": [SWAP_TOPIC],
        }
    ]);

    rpc_call(client, rpc_url, "eth_getLogs", params)
}

fn parse_log(fetched_at: &str, log: SwapLog) -> Result<CsvSwap> {
    if log.topics.len() < 3 {
        bail!("swap log has fewer than 3 topics: {:?}", log.topics);
    }

    let chunks = data_chunks(&log.data)?;
    if chunks.len() < 5 {
        bail!("swap data has fewer than 5 words: {}", log.data);
    }

    let amount0_raw = parse_i256_to_i128(chunks[0])?;
    let amount1_raw = parse_i256_to_i128(chunks[1])?;
    let sqrt_price_x96 = parse_u256_decimal(chunks[2])?;
    let liquidity_raw = parse_u256_decimal(chunks[3])?;
    let tick = parse_i256_to_i128(chunks[4])?;

    let amount0_token = scale_i128(amount0_raw, TOKEN0_DECIMALS);
    let amount1_token = scale_i128(amount1_raw, TOKEN1_DECIMALS);
    let chog_abs = amount0_token.abs();
    let mon_abs = amount1_token.abs();
    let price_mon_per_chog = if chog_abs > 0.0 {
        Some(mon_abs / chog_abs)
    } else {
        None
    };

    let direction = if amount0_raw > 0 {
        "sell_chog"
    } else if amount0_raw < 0 {
        "buy_chog"
    } else {
        "unknown"
    };

    let block_number = parse_hex_u64(&log.block_number)?;
    let block_timestamp = log
        .block_timestamp
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?
        .unwrap_or(0);
    let block_datetime_utc = if block_timestamp == 0 {
        String::new()
    } else {
        DateTime::<Utc>::from_timestamp(block_timestamp as i64, 0)
            .ok_or_else(|| anyhow!("invalid block timestamp {block_timestamp}"))?
            .to_rfc3339_opts(SecondsFormat::Secs, true)
    };

    Ok(CsvSwap {
        fetched_at_utc: fetched_at.to_string(),
        block_number,
        block_timestamp,
        block_datetime_utc,
        transaction_hash: log.transaction_hash,
        transaction_index: parse_hex_u64(&log.transaction_index)?,
        log_index: parse_hex_u64(&log.log_index)?,
        pair_address: log.address,
        sender: topic_to_address(&log.topics[1])?,
        recipient: topic_to_address(&log.topics[2])?,
        amount0_raw: amount0_raw.to_string(),
        amount1_raw: amount1_raw.to_string(),
        amount0_token: format!("{amount0_token:.18}"),
        amount1_token: format!("{amount1_token:.18}"),
        token0_symbol: TOKEN0_SYMBOL.to_string(),
        token1_symbol: TOKEN1_SYMBOL.to_string(),
        direction: direction.to_string(),
        chog_abs: format!("{chog_abs:.18}"),
        mon_abs: format!("{mon_abs:.18}"),
        price_mon_per_chog: price_mon_per_chog
            .map(|value| format!("{value:.18}"))
            .unwrap_or_default(),
        sqrt_price_x96,
        liquidity_raw,
        tick,
        removed: log.removed,
    })
}

fn data_chunks(data: &str) -> Result<Vec<&str>> {
    let data = data.trim_start_matches("0x");
    if data.len() % 64 != 0 {
        bail!("data length is not a multiple of 32 bytes: 0x{data}");
    }

    Ok(data
        .as_bytes()
        .chunks(64)
        .map(std::str::from_utf8)
        .collect::<std::result::Result<Vec<_>, _>>()?)
}

fn parse_i256_to_i128(word: &str) -> Result<i128> {
    if word.len() != 64 {
        bail!("expected 32-byte word, got {word}");
    }

    let negative = u8::from_str_radix(&word[..2], 16)? >= 0x80;
    let high = &word[..32];
    let low = &word[32..];

    if negative {
        if !high.chars().all(|c| c == 'f' || c == 'F') {
            bail!("negative int256 does not fit i128: 0x{word}");
        }
        let low_value = u128::from_str_radix(low, 16)?;
        let magnitude = (!low_value).wrapping_add(1);
        if magnitude > i128::MAX as u128 {
            bail!("negative int256 magnitude does not fit i128: 0x{word}");
        }
        Ok(-(magnitude as i128))
    } else {
        if high != "00000000000000000000000000000000" {
            bail!("positive int256 does not fit i128: 0x{word}");
        }
        let value = u128::from_str_radix(low, 16)?;
        if value > i128::MAX as u128 {
            bail!("positive int256 does not fit i128: 0x{word}");
        }
        Ok(value as i128)
    }
}

fn parse_u256_decimal(word: &str) -> Result<String> {
    let mut digits = vec![0u8];
    for byte in word.bytes() {
        let nibble = match byte {
            b'0'..=b'9' => byte - b'0',
            b'a'..=b'f' => byte - b'a' + 10,
            b'A'..=b'F' => byte - b'A' + 10,
            _ => bail!("invalid hex digit in {word}"),
        };
        multiply_decimal_digits(&mut digits, 16);
        add_decimal_digit(&mut digits, nibble);
    }

    while digits.len() > 1 && digits[0] == 0 {
        digits.remove(0);
    }

    Ok(digits
        .into_iter()
        .map(|digit| char::from(b'0' + digit))
        .collect())
}

fn multiply_decimal_digits(digits: &mut Vec<u8>, multiplier: u8) {
    let mut carry = 0u16;
    for digit in digits.iter_mut().rev() {
        let value = u16::from(*digit) * u16::from(multiplier) + carry;
        *digit = (value % 10) as u8;
        carry = value / 10;
    }
    while carry > 0 {
        digits.insert(0, (carry % 10) as u8);
        carry /= 10;
    }
}

fn add_decimal_digit(digits: &mut Vec<u8>, addend: u8) {
    let mut carry = u16::from(addend);
    for digit in digits.iter_mut().rev() {
        let value = u16::from(*digit) + carry;
        *digit = (value % 10) as u8;
        carry = value / 10;
        if carry == 0 {
            break;
        }
    }
    while carry > 0 {
        digits.insert(0, (carry % 10) as u8);
        carry /= 10;
    }
}

fn scale_i128(value: i128, decimals: i32) -> f64 {
    value as f64 / 10f64.powi(decimals)
}

fn topic_to_address(topic: &str) -> Result<String> {
    let topic = topic.trim_start_matches("0x");
    if topic.len() != 64 {
        bail!("invalid indexed address topic: 0x{topic}");
    }
    Ok(format!("0x{}", &topic[24..]))
}

fn default_output_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir.parent().unwrap_or(&manifest_dir);
    repo_root
        .join("date")
        .join("chog_main_pool_swaps_20k_blocks.csv")
}

fn print_summary(path: &PathBuf, rows: &[CsvSwap], from_block: u64, to_block: u64) {
    let buys = rows
        .iter()
        .filter(|row| row.direction == "buy_chog")
        .count();
    let sells = rows
        .iter()
        .filter(|row| row.direction == "sell_chog")
        .count();
    let buy_chog: f64 = rows
        .iter()
        .filter(|row| row.direction == "buy_chog")
        .filter_map(|row| row.chog_abs.parse::<f64>().ok())
        .sum();
    let sell_chog: f64 = rows
        .iter()
        .filter(|row| row.direction == "sell_chog")
        .filter_map(|row| row.chog_abs.parse::<f64>().ok())
        .sum();
    let buy_chog = clean_zero(buy_chog);
    let sell_chog = clean_zero(sell_chog);
    let net_sell_chog = clean_zero(sell_chog - buy_chog);

    println!("block window: {from_block}..{to_block}");
    println!("swap logs written: {}", rows.len());
    println!("buy/sell swaps: {buys}/{sells}");
    println!("buy_chog_amount: {buy_chog:.6}");
    println!("sell_chog_amount: {sell_chog:.6}");
    println!("net_sell_chog: {net_sell_chog:.6}");
    println!("csv: {}", path.display());
}

fn clean_zero(value: f64) -> f64 {
    if value.abs() < f64::EPSILON {
        0.0
    } else {
        value
    }
}

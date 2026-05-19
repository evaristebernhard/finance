use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, Float64Array, StringArray, UInt64Array};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use finance_chain_core::amm::{
    LB_V22_SWAP_TOPIC, PANCAKE_V3_SWAP_TOPIC, PoolMetadata, RpcSwapLog, SwapFamily, V2_SWAP_TOPIC,
    V3_SWAP_TOPIC, direction_for_base_delta, parse_log_block_number, parse_log_index,
    parse_log_transaction_index, parse_swap_deltas, price_quote_per_base, topic_to_address,
};
use finance_chain_core::dexscreener::PoolCandidate;
use finance_chain_core::parse_hex_u64;
use finance_chain_core::rpc::{RpcBlock, RpcReceipt};
use finance_chain_core::storage::{
    PartWrite, PartWriteStatus, RAW_DIR, bool_array, custom_part_path, deterministic_list_id,
    dt_from_timestamp, dt_from_utc_string, f64_array, opt_string_array, opt_u64_array,
    parquet_files_under, repo_root, rpc_part_path, string_array, u64_array, utc_from_timestamp,
    write_parquet_part, write_schema_metadata,
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde_json::Value;

pub mod enrichment;

pub const CHAIN: &str = "monad";
pub const DEFAULT_DATA_ROOT: &str = "data/mon_usdc/v1";
pub const DEFAULT_RPC_URL: &str = "https://rpc.monad.xyz";
pub const MON_TOKEN: &str = "0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A";
pub const USDC_TOKEN: &str = "0x754704Bc059F8C67012fEd69BC8A327a5aafb603";
pub const BASE_SYMBOL: &str = "MON";
pub const QUOTE_SYMBOL: &str = "USDC";
pub const POOL_SNAPSHOTS_DATASET: &str = "pool_snapshots";
pub const POOL_SWAP_LOGS_DATASET: &str = "pool_swap_logs";
pub const EVENT_HEADERS_DATASET: &str = "event_block_headers";
pub const TX_RECEIPTS_DATASET: &str = "tx_receipts";
pub const ONE_DAY_BLOCKS: u64 = 216_000;

#[derive(Debug, Clone)]
pub struct PoolSwapRow {
    pub fetched_at_utc: String,
    pub block_number: u64,
    pub block_timestamp: u64,
    pub block_datetime_utc: String,
    pub transaction_hash: String,
    pub transaction_index: u64,
    pub log_index: u64,
    pub pool_address: String,
    pub dex_id: String,
    pub family: String,
    pub swap_topic: String,
    pub sender: String,
    pub recipient: String,
    pub token0_address: String,
    pub token1_address: String,
    pub token0_decimals: u64,
    pub token1_decimals: u64,
    pub base_symbol: String,
    pub quote_symbol: String,
    pub base_address: String,
    pub quote_address: String,
    pub base_token_index: u64,
    pub quote_token_index: u64,
    pub amount0_delta_raw: String,
    pub amount1_delta_raw: String,
    pub amount0_delta: String,
    pub amount1_delta: String,
    pub direction: String,
    pub base_abs: String,
    pub quote_abs: String,
    pub price_quote_per_base: String,
    pub sqrt_price_x96: Option<String>,
    pub liquidity_raw: Option<String>,
    pub tick: Option<String>,
    pub removed: bool,
    pub dt: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct EventBlockStats {
    pub log_count: u64,
    pub tx_hashes: BTreeSet<String>,
    pub source_datasets: BTreeSet<String>,
}

impl EventBlockStats {
    pub fn tx_count(&self) -> u64 {
        self.tx_hashes.len() as u64
    }

    pub fn source_datasets(&self) -> String {
        self.source_datasets
            .iter()
            .cloned()
            .collect::<Vec<_>>()
            .join("|")
    }
}

#[derive(Debug, Clone)]
pub struct EventHeaderRow {
    pub fetched_at_utc: String,
    pub block_number: u64,
    pub block_hash: String,
    pub parent_hash: String,
    pub block_timestamp: u64,
    pub block_datetime_utc: String,
    pub base_fee_per_gas: Option<u64>,
    pub gas_used: u64,
    pub gas_limit: u64,
    pub miner: String,
    pub extra_data: String,
    pub transaction_count: u64,
    pub event_log_count: u64,
    pub event_tx_count: u64,
    pub source_datasets: String,
    pub dt: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SourceTxMetadata {
    pub block_number: Option<u64>,
    pub block_timestamp: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct ReceiptRow {
    pub fetched_at_utc: String,
    pub transaction_hash: String,
    pub request_status: String,
    pub error: String,
    pub block_number: Option<u64>,
    pub block_hash: String,
    pub block_timestamp: Option<u64>,
    pub block_datetime_utc: String,
    pub transaction_index: Option<u64>,
    pub from_address: String,
    pub to_address: String,
    pub contract_address: String,
    pub receipt_status: Option<u64>,
    pub gas_used: Option<u64>,
    pub cumulative_gas_used: Option<u64>,
    pub effective_gas_price: Option<u64>,
    pub tx_type: String,
    pub logs_count: Option<u64>,
    pub dt: String,
}

pub fn default_data_root_path() -> PathBuf {
    repo_root().join(DEFAULT_DATA_ROOT)
}

pub fn known_top4_pools() -> Vec<PoolCandidate> {
    vec![
        PoolCandidate::from_known(
            1,
            "uniswap",
            "v3",
            "0x659bD0BC4167BA25c62E05656F78043E7eD4a9da",
            MON_TOKEN,
            BASE_SYMBOL,
            USDC_TOKEN,
            QUOTE_SYMBOL,
        ),
        PoolCandidate::from_known(
            2,
            "pancakeswap",
            "v3",
            "0x63e48B725540A3Db24ACF6682a29f877808C53F2",
            MON_TOKEN,
            BASE_SYMBOL,
            USDC_TOKEN,
            QUOTE_SYMBOL,
        ),
        PoolCandidate::from_known(
            3,
            "traderjoe",
            "v2.2",
            "0x5AFD3EC861f6104af26e8755aBcc1f876de77620",
            MON_TOKEN,
            BASE_SYMBOL,
            USDC_TOKEN,
            QUOTE_SYMBOL,
        ),
        PoolCandidate::from_known(
            4,
            "traderjoe",
            "v2.2",
            "0x5E60BC3F7a7303BC4dfE4dc2220bdC90bc04fE22",
            MON_TOKEN,
            BASE_SYMBOL,
            USDC_TOKEN,
            QUOTE_SYMBOL,
        ),
    ]
}

pub fn topic_identity() -> String {
    format!("{V2_SWAP_TOPIC}|{V3_SWAP_TOPIC}|{PANCAKE_V3_SWAP_TOPIC}|{LB_V22_SWAP_TOPIC}")
}

pub fn merge_known_top4_with_snapshot(snapshot: Vec<PoolCandidate>) -> Vec<PoolCandidate> {
    let mut by_address = BTreeMap::<String, PoolCandidate>::new();
    for pool in known_top4_pools() {
        by_address.insert(pool.pair_address.to_ascii_lowercase(), pool);
    }
    for pool in snapshot {
        by_address.insert(pool.pair_address.to_ascii_lowercase(), pool);
    }
    let mut rows = by_address.into_values().collect::<Vec<_>>();
    rows.sort_by(|a, b| {
        a.rank_liquidity
            .cmp(&b.rank_liquidity)
            .then_with(|| b.liquidity_usd.total_cmp(&a.liquidity_usd))
            .then_with(|| a.pair_address.cmp(&b.pair_address))
    });
    rows
}

pub fn select_pools(
    data_root: &Path,
    pool_addresses: &[String],
    top_pools: usize,
) -> Result<Vec<PoolCandidate>> {
    let mut pools = merge_known_top4_with_snapshot(read_latest_pool_snapshots(data_root)?);
    if !pool_addresses.is_empty() {
        let requested = pool_addresses
            .iter()
            .map(|value| value.to_ascii_lowercase())
            .collect::<BTreeSet<_>>();
        pools.retain(|pool| requested.contains(&pool.pair_address.to_ascii_lowercase()));
        if pools.is_empty() {
            bail!("none of the requested --pool-address values were found");
        }
        return Ok(pools);
    }
    pools.truncate(top_pools);
    Ok(pools)
}

pub fn pool_snapshot_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("rank_liquidity", DataType::UInt64, false),
        Field::new("chain_id", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("labels", DataType::Utf8, false),
        Field::new("family_hint", DataType::Utf8, false),
        Field::new("pair_address", DataType::Utf8, false),
        Field::new("base_address", DataType::Utf8, false),
        Field::new("base_symbol", DataType::Utf8, false),
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("price_usd", DataType::Utf8, false),
        Field::new("liquidity_usd", DataType::Float64, false),
        Field::new("volume_m5_usd", DataType::Float64, false),
        Field::new("volume_h1_usd", DataType::Float64, false),
        Field::new("volume_h6_usd", DataType::Float64, false),
        Field::new("volume_h24_usd", DataType::Float64, false),
        Field::new("m5_buys", DataType::UInt64, false),
        Field::new("m5_sells", DataType::UInt64, false),
        Field::new("h1_buys", DataType::UInt64, false),
        Field::new("h1_sells", DataType::UInt64, false),
        Field::new("h6_buys", DataType::UInt64, false),
        Field::new("h6_sells", DataType::UInt64, false),
        Field::new("h24_buys", DataType::UInt64, false),
        Field::new("h24_sells", DataType::UInt64, false),
        Field::new("pair_created_at", DataType::Utf8, false),
        Field::new("url", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn write_pool_snapshot_part(
    data_root: &Path,
    rows: &[PoolCandidate],
    fetched_at_utc: &str,
) -> Result<PartWrite> {
    let schema = pool_snapshot_schema();
    write_schema_metadata(data_root, POOL_SNAPSHOTS_DATASET, schema.as_ref(), &["dt"])?;
    let dt = dt_from_utc_string(fetched_at_utc);
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
            u64_array(
                &rows
                    .iter()
                    .map(|row| row.rank_liquidity)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.chain_id.clone())
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
                    .map(|row| row.labels.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.family_hint.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pair_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.base_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.base_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quote_address.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.quote_symbol.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.price_usd.clone())
                    .collect::<Vec<_>>(),
            ),
            f64_array(&rows.iter().map(|row| row.liquidity_usd).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.volume_m5_usd).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.volume_h1_usd).collect::<Vec<_>>()),
            f64_array(&rows.iter().map(|row| row.volume_h6_usd).collect::<Vec<_>>()),
            f64_array(
                &rows
                    .iter()
                    .map(|row| row.volume_h24_usd)
                    .collect::<Vec<_>>(),
            ),
            u64_array(&rows.iter().map(|row| row.m5_buys).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.m5_sells).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.h1_buys).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.h1_sells).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.h6_buys).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.h6_sells).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.h24_buys).collect::<Vec<_>>()),
            u64_array(&rows.iter().map(|row| row.h24_sells).collect::<Vec<_>>()),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pair_created_at.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(&rows.iter().map(|row| row.url.clone()).collect::<Vec<_>>()),
            string_array(&dt_values),
        ],
    )?;
    let stem = format!(
        "mon_usdc_pool_snapshot_{}",
        finance_chain_core::storage::safe_timestamp_for_filename(fetched_at_utc)
    );
    write_parquet_part(
        &custom_part_path(data_root, RAW_DIR, POOL_SNAPSHOTS_DATASET, &dt, &stem),
        schema,
        batch,
    )
}

pub fn pool_swap_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, false),
        Field::new("block_timestamp", DataType::UInt64, false),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("transaction_hash", DataType::Utf8, false),
        Field::new("transaction_index", DataType::UInt64, false),
        Field::new("log_index", DataType::UInt64, false),
        Field::new("pool_address", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("family", DataType::Utf8, false),
        Field::new("swap_topic", DataType::Utf8, false),
        Field::new("sender", DataType::Utf8, false),
        Field::new("recipient", DataType::Utf8, false),
        Field::new("token0_address", DataType::Utf8, false),
        Field::new("token1_address", DataType::Utf8, false),
        Field::new("token0_decimals", DataType::UInt64, false),
        Field::new("token1_decimals", DataType::UInt64, false),
        Field::new("base_symbol", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("base_address", DataType::Utf8, false),
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("base_token_index", DataType::UInt64, false),
        Field::new("quote_token_index", DataType::UInt64, false),
        Field::new("amount0_delta_raw", DataType::Utf8, false),
        Field::new("amount1_delta_raw", DataType::Utf8, false),
        Field::new("amount0_delta", DataType::Utf8, false),
        Field::new("amount1_delta", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("base_abs", DataType::Utf8, false),
        Field::new("quote_abs", DataType::Utf8, false),
        Field::new("price_quote_per_base", DataType::Utf8, false),
        Field::new("sqrt_price_x96", DataType::Utf8, true),
        Field::new("liquidity_raw", DataType::Utf8, true),
        Field::new("tick", DataType::Utf8, true),
        Field::new("removed", DataType::Boolean, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn swap_row_from_log(
    fetched_at_utc: &str,
    metadata: &PoolMetadata,
    family: SwapFamily,
    log: RpcSwapLog,
) -> Result<PoolSwapRow> {
    if log.topics.len() < 3 {
        bail!("swap log has fewer than 3 topics: {:?}", log.topics);
    }
    let deltas = parse_swap_deltas(family, &log.data)?;
    let block_number = parse_log_block_number(&log)?;
    let block_timestamp = log
        .block_timestamp
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?
        .unwrap_or(0);
    let block_datetime_utc = if block_timestamp > 0 {
        utc_from_timestamp(block_timestamp)?
    } else {
        String::new()
    };
    let dt = if block_timestamp > 0 {
        dt_from_timestamp(block_timestamp)?
    } else {
        dt_from_utc_string(fetched_at_utc)
    };

    let base_delta = if metadata.base_token_index == 0 {
        deltas.amount0_delta_raw
    } else {
        deltas.amount1_delta_raw
    };
    let quote_delta = if metadata.quote_token_index == 0 {
        deltas.amount0_delta_raw
    } else {
        deltas.amount1_delta_raw
    };
    let base_decimals = if metadata.base_token_index == 0 {
        metadata.token0_decimals
    } else {
        metadata.token1_decimals
    };
    let quote_decimals = if metadata.quote_token_index == 0 {
        metadata.token0_decimals
    } else {
        metadata.token1_decimals
    };
    let price = price_quote_per_base(
        base_delta.magnitude(),
        base_decimals,
        quote_delta.magnitude(),
        quote_decimals,
    )
    .unwrap_or_default();
    let transaction_index = parse_log_transaction_index(&log)?;
    let log_index = parse_log_index(&log)?;

    Ok(PoolSwapRow {
        fetched_at_utc: fetched_at_utc.to_string(),
        block_number,
        block_timestamp,
        block_datetime_utc,
        transaction_hash: log.transaction_hash,
        transaction_index,
        log_index,
        pool_address: log.address.to_ascii_lowercase(),
        dex_id: metadata.pool.dex_id.clone(),
        family: family.as_str().to_string(),
        swap_topic: family.topic().to_string(),
        sender: topic_to_address(&log.topics[1])?,
        recipient: topic_to_address(&log.topics[2])?,
        token0_address: metadata.token0_address.clone(),
        token1_address: metadata.token1_address.clone(),
        token0_decimals: u64::from(metadata.token0_decimals),
        token1_decimals: u64::from(metadata.token1_decimals),
        base_symbol: metadata.base_symbol.clone(),
        quote_symbol: metadata.quote_symbol.clone(),
        base_address: metadata.base_address.clone(),
        quote_address: metadata.quote_address.clone(),
        base_token_index: u64::from(metadata.base_token_index),
        quote_token_index: u64::from(metadata.quote_token_index),
        amount0_delta_raw: deltas.amount0_delta_raw.raw_string(),
        amount1_delta_raw: deltas.amount1_delta_raw.raw_string(),
        amount0_delta: deltas
            .amount0_delta_raw
            .signed_decimal_string(metadata.token0_decimals),
        amount1_delta: deltas
            .amount1_delta_raw
            .signed_decimal_string(metadata.token1_decimals),
        direction: direction_for_base_delta(base_delta).to_string(),
        base_abs: base_delta.abs_decimal_string(base_decimals),
        quote_abs: quote_delta.abs_decimal_string(quote_decimals),
        price_quote_per_base: price,
        sqrt_price_x96: deltas.sqrt_price_x96,
        liquidity_raw: deltas.liquidity_raw,
        tick: deltas.tick,
        removed: log.removed,
        dt,
    })
}

pub fn write_pool_swap_parts(
    data_root: &Path,
    rows: &[PoolSwapRow],
    from_block: u64,
    to_block: u64,
    collector: &str,
) -> Result<Vec<PartWrite>> {
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let schema = pool_swap_schema();
    write_schema_metadata(data_root, POOL_SWAP_LOGS_DATASET, schema.as_ref(), &["dt"])?;
    let mut by_dt = BTreeMap::<String, Vec<PoolSwapRow>>::new();
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
                        .map(|row| row.swap_topic.clone())
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
                        .map(|row| row.token0_address.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.token1_address.clone())
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.token0_decimals)
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.token1_decimals)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.base_symbol.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.quote_symbol.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.base_address.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.quote_address.clone())
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.base_token_index)
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.quote_token_index)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount0_delta_raw.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount1_delta_raw.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount0_delta.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount1_delta.clone())
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
                        .map(|row| row.base_abs.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.quote_abs.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.price_quote_per_base.clone())
                        .collect::<Vec<_>>(),
                ),
                opt_string_array(
                    &rows
                        .iter()
                        .map(|row| row.sqrt_price_x96.clone())
                        .collect::<Vec<_>>(),
                ),
                opt_string_array(
                    &rows
                        .iter()
                        .map(|row| row.liquidity_raw.clone())
                        .collect::<Vec<_>>(),
                ),
                opt_string_array(&rows.iter().map(|row| row.tick.clone()).collect::<Vec<_>>()),
                bool_array(&rows.iter().map(|row| row.removed).collect::<Vec<_>>()),
                string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
            ],
        )?;
        parts.push(write_parquet_part(
            &rpc_part_path(
                data_root,
                RAW_DIR,
                POOL_SWAP_LOGS_DATASET,
                &dt,
                collector,
                from_block,
                to_block,
            ),
            schema.clone(),
            batch,
        )?);
    }
    Ok(parts)
}

pub fn event_header_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("block_number", DataType::UInt64, false),
        Field::new("block_hash", DataType::Utf8, false),
        Field::new("parent_hash", DataType::Utf8, false),
        Field::new("block_timestamp", DataType::UInt64, false),
        Field::new("block_datetime_utc", DataType::Utf8, false),
        Field::new("base_fee_per_gas", DataType::UInt64, true),
        Field::new("gas_used", DataType::UInt64, false),
        Field::new("gas_limit", DataType::UInt64, false),
        Field::new("miner", DataType::Utf8, false),
        Field::new("extra_data", DataType::Utf8, false),
        Field::new("transaction_count", DataType::UInt64, false),
        Field::new("event_log_count", DataType::UInt64, false),
        Field::new("event_tx_count", DataType::UInt64, false),
        Field::new("source_datasets", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn event_header_row_from_block(
    fetched_at_utc: &str,
    expected_block_number: u64,
    block: RpcBlock,
    stats: &EventBlockStats,
) -> Result<EventHeaderRow> {
    let block_number = block
        .number
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?
        .unwrap_or(expected_block_number);
    let block_timestamp = parse_hex_u64(&block.timestamp)?;
    let dt = dt_from_timestamp(block_timestamp)?;
    Ok(EventHeaderRow {
        fetched_at_utc: fetched_at_utc.to_string(),
        block_number,
        block_hash: block.hash.unwrap_or_default(),
        parent_hash: block.parent_hash.unwrap_or_default(),
        block_timestamp,
        block_datetime_utc: utc_from_timestamp(block_timestamp)?,
        base_fee_per_gas: block
            .base_fee_per_gas
            .as_deref()
            .map(parse_hex_u64)
            .transpose()?,
        gas_used: parse_hex_u64(&block.gas_used)?,
        gas_limit: parse_hex_u64(&block.gas_limit)?,
        miner: block.miner.unwrap_or_default(),
        extra_data: block.extra_data.unwrap_or_default(),
        transaction_count: block.transactions.len() as u64,
        event_log_count: stats.log_count,
        event_tx_count: stats.tx_count(),
        source_datasets: stats.source_datasets(),
        dt,
    })
}

pub fn write_event_header_parts(
    data_root: &Path,
    rows: &[EventHeaderRow],
) -> Result<Vec<PartWrite>> {
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let schema = event_header_schema();
    write_schema_metadata(data_root, EVENT_HEADERS_DATASET, schema.as_ref(), &["dt"])?;
    let min_block = rows.iter().map(|row| row.block_number).min().unwrap_or(0);
    let max_block = rows.iter().map(|row| row.block_number).max().unwrap_or(0);
    let mut block_ids = rows
        .iter()
        .map(|row| row.block_number.to_string())
        .collect::<Vec<_>>();
    block_ids.sort();
    let stem = format!(
        "mon_usdc_event_header_sample_{min_block}_{max_block}_{}",
        deterministic_list_id(&block_ids)
    );
    let mut by_dt = BTreeMap::<String, Vec<EventHeaderRow>>::new();
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
                u64_array(&rows.iter().map(|row| row.block_number).collect::<Vec<_>>()),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.block_hash.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.parent_hash.clone())
                        .collect::<Vec<_>>(),
                ),
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
                opt_u64_array(
                    &rows
                        .iter()
                        .map(|row| row.base_fee_per_gas)
                        .collect::<Vec<_>>(),
                ),
                u64_array(&rows.iter().map(|row| row.gas_used).collect::<Vec<_>>()),
                u64_array(&rows.iter().map(|row| row.gas_limit).collect::<Vec<_>>()),
                string_array(&rows.iter().map(|row| row.miner.clone()).collect::<Vec<_>>()),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.extra_data.clone())
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.transaction_count)
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.event_log_count)
                        .collect::<Vec<_>>(),
                ),
                u64_array(
                    &rows
                        .iter()
                        .map(|row| row.event_tx_count)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.source_datasets.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
            ],
        )?;
        parts.push(write_parquet_part(
            &custom_part_path(data_root, RAW_DIR, EVENT_HEADERS_DATASET, &dt, &stem),
            schema.clone(),
            batch,
        )?);
    }
    Ok(parts)
}

pub fn receipt_schema() -> SchemaRef {
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
        Field::new("logs_count", DataType::UInt64, true),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn receipt_row_from_rpc(
    fetched_at_utc: &str,
    hash: &str,
    receipt_value: Value,
    item_error: Option<String>,
    local_metadata: Option<&SourceTxMetadata>,
    event_header_timestamps: &BTreeMap<u64, (u64, String)>,
) -> Result<ReceiptRow> {
    if let Some(error) = item_error {
        let dt = dt_from_utc_string(fetched_at_utc);
        return Ok(ReceiptRow {
            fetched_at_utc: fetched_at_utc.to_string(),
            transaction_hash: hash.to_string(),
            request_status: "rpc_error".to_string(),
            error,
            block_number: local_metadata.and_then(|metadata| metadata.block_number),
            block_hash: String::new(),
            block_timestamp: local_metadata.and_then(|metadata| metadata.block_timestamp),
            block_datetime_utc: String::new(),
            transaction_index: None,
            from_address: String::new(),
            to_address: String::new(),
            contract_address: String::new(),
            receipt_status: None,
            gas_used: None,
            cumulative_gas_used: None,
            effective_gas_price: None,
            tx_type: String::new(),
            logs_count: None,
            dt,
        });
    }

    if receipt_value.is_null() {
        let dt = dt_from_utc_string(fetched_at_utc);
        return Ok(ReceiptRow {
            fetched_at_utc: fetched_at_utc.to_string(),
            transaction_hash: hash.to_string(),
            request_status: "missing_receipt".to_string(),
            error: String::new(),
            block_number: local_metadata.and_then(|metadata| metadata.block_number),
            block_hash: String::new(),
            block_timestamp: local_metadata.and_then(|metadata| metadata.block_timestamp),
            block_datetime_utc: String::new(),
            transaction_index: None,
            from_address: String::new(),
            to_address: String::new(),
            contract_address: String::new(),
            receipt_status: None,
            gas_used: None,
            cumulative_gas_used: None,
            effective_gas_price: None,
            tx_type: String::new(),
            logs_count: None,
            dt,
        });
    }

    let receipt: RpcReceipt = serde_json::from_value(receipt_value)?;
    let block_number = receipt
        .block_number
        .as_deref()
        .map(parse_hex_u64)
        .transpose()?;
    let (block_timestamp, block_datetime_utc, dt) = if let Some(block_number) = block_number {
        resolve_local_block_time(
            block_number,
            local_metadata,
            event_header_timestamps,
            fetched_at_utc,
        )?
    } else {
        (None, String::new(), dt_from_utc_string(fetched_at_utc))
    };

    Ok(ReceiptRow {
        fetched_at_utc: fetched_at_utc.to_string(),
        transaction_hash: receipt.transaction_hash,
        request_status: "receipt_only".to_string(),
        error: String::new(),
        block_number,
        block_hash: receipt.block_hash.unwrap_or_default(),
        block_timestamp,
        block_datetime_utc,
        transaction_index: receipt
            .transaction_index
            .as_deref()
            .map(parse_hex_u64)
            .transpose()?,
        from_address: receipt.from.unwrap_or_default(),
        to_address: receipt.to.unwrap_or_default(),
        contract_address: receipt.contract_address.unwrap_or_default(),
        receipt_status: receipt.status.as_deref().map(parse_hex_u64).transpose()?,
        gas_used: receipt.gas_used.as_deref().map(parse_hex_u64).transpose()?,
        cumulative_gas_used: receipt
            .cumulative_gas_used
            .as_deref()
            .map(parse_hex_u64)
            .transpose()?,
        effective_gas_price: receipt
            .effective_gas_price
            .as_deref()
            .map(parse_hex_u64)
            .transpose()?,
        tx_type: receipt.tx_type.unwrap_or_default(),
        logs_count: receipt.logs.as_ref().map(|logs| logs.len() as u64),
        dt,
    })
}

pub fn write_receipt_parts(
    data_root: &Path,
    rows: &[ReceiptRow],
    batch_hashes: &[String],
) -> Result<Vec<PartWrite>> {
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let schema = receipt_schema();
    write_schema_metadata(data_root, TX_RECEIPTS_DATASET, schema.as_ref(), &["dt"])?;
    let batch_id = deterministic_list_id(batch_hashes);
    let mut by_dt = BTreeMap::<String, Vec<ReceiptRow>>::new();
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
                opt_u64_array(&rows.iter().map(|row| row.logs_count).collect::<Vec<_>>()),
                string_array(&rows.iter().map(|row| row.dt.clone()).collect::<Vec<_>>()),
            ],
        )?;
        let stem = format!("mon_usdc_receipt_sample_{batch_id}");
        parts.push(write_parquet_part(
            &custom_part_path(data_root, RAW_DIR, TX_RECEIPTS_DATASET, &dt, &stem),
            schema.clone(),
            batch,
        )?);
    }
    Ok(parts)
}

pub fn read_latest_pool_snapshots(data_root: &Path) -> Result<Vec<PoolCandidate>> {
    let root = data_root.join(RAW_DIR).join(POOL_SNAPSHOTS_DATASET);
    let mut rows = Vec::new();
    for path in parquet_files_under(&root)? {
        read_pool_snapshot_file(&path, &mut rows)?;
    }
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let latest = rows
        .iter()
        .map(|row| row.fetched_at_utc.as_str())
        .max()
        .unwrap_or_default()
        .to_string();
    rows.retain(|row| row.fetched_at_utc == latest);
    rows.sort_by_key(|row| row.rank_liquidity);
    Ok(rows)
}

pub fn discover_swap_event_blocks(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> Result<BTreeMap<u64, EventBlockStats>> {
    let mut blocks = BTreeMap::<u64, EventBlockStats>::new();
    let root = data_root.join(RAW_DIR).join(POOL_SWAP_LOGS_DATASET);
    for path in parquet_files_under(&root)? {
        read_swap_blocks_from_file(&path, from_block, to_block, &mut blocks)?;
    }
    Ok(blocks)
}

pub fn existing_event_header_blocks(data_root: &Path) -> Result<BTreeSet<u64>> {
    let mut blocks = BTreeSet::new();
    let root = data_root.join(RAW_DIR).join(EVENT_HEADERS_DATASET);
    for path in parquet_files_under(&root)? {
        read_block_numbers_from_file(&path, &mut blocks)?;
    }
    Ok(blocks)
}

pub fn collect_receipt_queue(
    data_root: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
) -> Result<(Vec<String>, BTreeMap<String, SourceTxMetadata>)> {
    let mut hashes = BTreeSet::new();
    let mut metadata = BTreeMap::<String, SourceTxMetadata>::new();
    let root = data_root.join(RAW_DIR).join(POOL_SWAP_LOGS_DATASET);
    for path in parquet_files_under(&root)? {
        read_swap_tx_metadata_file(&path, from_block, to_block, &mut hashes, &mut metadata)?;
    }
    let existing = existing_receipt_hashes(data_root)?;
    let hashes = hashes
        .into_iter()
        .filter(|hash| !existing.contains(hash))
        .collect::<Vec<_>>();
    Ok((hashes, metadata))
}

pub fn existing_receipt_hashes(data_root: &Path) -> Result<BTreeSet<String>> {
    let mut hashes = BTreeSet::new();
    let root = data_root.join(RAW_DIR).join(TX_RECEIPTS_DATASET);
    for path in parquet_files_under(&root)? {
        for hash in
            finance_chain_core::storage::read_string_column_from_parquet(&path, "transaction_hash")?
        {
            hashes.insert(hash);
        }
    }
    Ok(hashes)
}

pub fn read_event_header_timestamps(data_root: &Path) -> Result<BTreeMap<u64, (u64, String)>> {
    let mut timestamps = BTreeMap::<u64, (u64, String)>::new();
    let root = data_root.join(RAW_DIR).join(EVENT_HEADERS_DATASET);
    for path in parquet_files_under(&root)? {
        read_event_header_timestamp_file(&path, &mut timestamps)?;
    }
    Ok(timestamps)
}

pub fn read_all_swap_keys(data_root: &Path) -> Result<BTreeSet<(u64, String, u64)>> {
    let mut keys = BTreeSet::new();
    let root = data_root.join(RAW_DIR).join(POOL_SWAP_LOGS_DATASET);
    for path in parquet_files_under(&root)? {
        let file =
            File::open(&path).with_context(|| format!("failed to open {}", path.display()))?;
        let builder = ParquetRecordBatchReaderBuilder::try_new(file)
            .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
        let mut reader = builder.with_batch_size(4096).build()?;
        for batch in &mut reader {
            let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
            let block_number = uint64_column(&batch, "block_number")?;
            let transaction_hash = string_column(&batch, "transaction_hash")?;
            let log_index = uint64_column(&batch, "log_index")?;
            for index in 0..batch.num_rows() {
                if block_number.is_null(index)
                    || transaction_hash.is_null(index)
                    || log_index.is_null(index)
                {
                    continue;
                }
                keys.insert((
                    block_number.value(index),
                    transaction_hash.value(index).to_string(),
                    log_index.value(index),
                ));
            }
        }
    }
    Ok(keys)
}

fn resolve_local_block_time(
    block_number: u64,
    local_metadata: Option<&SourceTxMetadata>,
    event_header_timestamps: &BTreeMap<u64, (u64, String)>,
    fetched_at_utc: &str,
) -> Result<(Option<u64>, String, String)> {
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
        return Ok((Some(timestamp), datetime, dt_from_timestamp(timestamp)?));
    }
    if let Some((timestamp, datetime)) = event_header_timestamps.get(&block_number) {
        return Ok((
            Some(*timestamp),
            datetime.clone(),
            dt_from_timestamp(*timestamp)?,
        ));
    }
    Ok((None, String::new(), dt_from_utc_string(fetched_at_utc)))
}

fn read_pool_snapshot_file(path: &Path, rows: &mut Vec<PoolCandidate>) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder.with_batch_size(2048).build()?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let fetched_at_utc = string_column(&batch, "fetched_at_utc")?;
        let rank_liquidity = uint64_column(&batch, "rank_liquidity")?;
        let chain_id = string_column(&batch, "chain_id")?;
        let dex_id = string_column(&batch, "dex_id")?;
        let labels = string_column(&batch, "labels")?;
        let family_hint = string_column(&batch, "family_hint")?;
        let pair_address = string_column(&batch, "pair_address")?;
        let base_address = string_column(&batch, "base_address")?;
        let base_symbol = string_column(&batch, "base_symbol")?;
        let quote_address = string_column(&batch, "quote_address")?;
        let quote_symbol = string_column(&batch, "quote_symbol")?;
        let price_usd = string_column(&batch, "price_usd")?;
        let liquidity_usd = float64_column(&batch, "liquidity_usd")?;
        let volume_m5_usd = float64_column(&batch, "volume_m5_usd")?;
        let volume_h1_usd = float64_column(&batch, "volume_h1_usd")?;
        let volume_h6_usd = float64_column(&batch, "volume_h6_usd")?;
        let volume_h24_usd = float64_column(&batch, "volume_h24_usd")?;
        let m5_buys = uint64_column(&batch, "m5_buys")?;
        let m5_sells = uint64_column(&batch, "m5_sells")?;
        let h1_buys = uint64_column(&batch, "h1_buys")?;
        let h1_sells = uint64_column(&batch, "h1_sells")?;
        let h6_buys = uint64_column(&batch, "h6_buys")?;
        let h6_sells = uint64_column(&batch, "h6_sells")?;
        let h24_buys = uint64_column(&batch, "h24_buys")?;
        let h24_sells = uint64_column(&batch, "h24_sells")?;
        let pair_created_at = string_column(&batch, "pair_created_at")?;
        let url = string_column(&batch, "url")?;
        for index in 0..batch.num_rows() {
            rows.push(PoolCandidate {
                fetched_at_utc: string_value(fetched_at_utc, index),
                rank_liquidity: u64_value(rank_liquidity, index),
                chain_id: string_value(chain_id, index),
                dex_id: string_value(dex_id, index),
                labels: string_value(labels, index),
                family_hint: string_value(family_hint, index),
                pair_address: string_value(pair_address, index),
                base_address: string_value(base_address, index),
                base_symbol: string_value(base_symbol, index),
                quote_address: string_value(quote_address, index),
                quote_symbol: string_value(quote_symbol, index),
                price_usd: string_value(price_usd, index),
                liquidity_usd: f64_value(liquidity_usd, index),
                volume_m5_usd: f64_value(volume_m5_usd, index),
                volume_h1_usd: f64_value(volume_h1_usd, index),
                volume_h6_usd: f64_value(volume_h6_usd, index),
                volume_h24_usd: f64_value(volume_h24_usd, index),
                m5_buys: u64_value(m5_buys, index),
                m5_sells: u64_value(m5_sells, index),
                h1_buys: u64_value(h1_buys, index),
                h1_sells: u64_value(h1_sells, index),
                h6_buys: u64_value(h6_buys, index),
                h6_sells: u64_value(h6_sells, index),
                h24_buys: u64_value(h24_buys, index),
                h24_sells: u64_value(h24_sells, index),
                pair_created_at: string_value(pair_created_at, index),
                url: string_value(url, index),
            });
        }
    }
    Ok(())
}

fn read_swap_blocks_from_file(
    path: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
    blocks: &mut BTreeMap<u64, EventBlockStats>,
) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder.with_batch_size(4096).build()?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let block_number = uint64_column(&batch, "block_number")?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        for index in 0..batch.num_rows() {
            if block_number.is_null(index) {
                continue;
            }
            let block = block_number.value(index);
            if from_block.map_or(false, |from| block < from)
                || to_block.map_or(false, |to| block > to)
            {
                continue;
            }
            let stats = blocks.entry(block).or_default();
            stats.log_count += 1;
            stats
                .source_datasets
                .insert(POOL_SWAP_LOGS_DATASET.to_string());
            if !transaction_hash.is_null(index) && !transaction_hash.value(index).is_empty() {
                stats
                    .tx_hashes
                    .insert(transaction_hash.value(index).to_string());
            }
        }
    }
    Ok(())
}

fn read_block_numbers_from_file(path: &Path, blocks: &mut BTreeSet<u64>) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder.with_batch_size(4096).build()?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let block_number = uint64_column(&batch, "block_number")?;
        for index in 0..batch.num_rows() {
            if !block_number.is_null(index) {
                blocks.insert(block_number.value(index));
            }
        }
    }
    Ok(())
}

fn read_swap_tx_metadata_file(
    path: &Path,
    from_block: Option<u64>,
    to_block: Option<u64>,
    hashes: &mut BTreeSet<String>,
    metadata: &mut BTreeMap<String, SourceTxMetadata>,
) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder.with_batch_size(4096).build()?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let transaction_hash = string_column(&batch, "transaction_hash")?;
        let block_number = uint64_column(&batch, "block_number")?;
        let block_timestamp = uint64_column(&batch, "block_timestamp")?;
        for index in 0..batch.num_rows() {
            if transaction_hash.is_null(index) || transaction_hash.value(index).is_empty() {
                continue;
            }
            let block = if block_number.is_null(index) {
                if from_block.is_some() || to_block.is_some() {
                    continue;
                }
                None
            } else {
                Some(block_number.value(index))
            };
            if let Some(block) = block {
                if from_block.map_or(false, |from| block < from)
                    || to_block.map_or(false, |to| block > to)
                {
                    continue;
                }
            }
            let hash = transaction_hash.value(index).to_string();
            hashes.insert(hash.clone());
            let entry = metadata.entry(hash).or_default();
            if entry.block_number.is_none() {
                entry.block_number = block;
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

fn read_event_header_timestamp_file(
    path: &Path,
    timestamps: &mut BTreeMap<u64, (u64, String)>,
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

fn f64_value(values: &Float64Array, index: usize) -> f64 {
    if values.is_null(index) {
        0.0
    } else {
        values.value(index)
    }
}

pub fn count_written_rows(parts: &[PartWrite]) -> u64 {
    parts
        .iter()
        .filter(|part| part.status == PartWriteStatus::Written)
        .map(|part| part.rows as u64)
        .sum()
}

pub fn resolve_rpc_urls(cli_urls: &[String], env_file: &Path) -> Vec<String> {
    let mut urls = Vec::new();
    for url in cli_urls {
        push_rpc_values(&mut urls, url);
    }
    for name in [
        "MON_USDC_RPC_URLS",
        "MONAD_RPC_URLS",
        "CHOG_LOG_RPCS",
        "CHOG_PUBLIC_LOG_RPCS",
        "CHOG_HEADER_RPC",
        "ALCHEMY_RPC",
        "RPC_URL",
    ] {
        if let Ok(value) = std::env::var(name) {
            push_rpc_values(&mut urls, &value);
        }
    }
    if env_file.exists() {
        if let Ok(body) = std::fs::read_to_string(env_file) {
            for name in [
                "MON_USDC_RPC_URLS",
                "MONAD_RPC_URLS",
                "CHOG_LOG_RPCS",
                "CHOG_PUBLIC_LOG_RPCS",
                "CHOG_HEADER_RPC",
                "ALCHEMY_RPC",
                "RPC_URL",
            ] {
                if let Some(value) = parse_env_value(&body, name) {
                    push_rpc_values(&mut urls, &value);
                }
            }
        }
    }
    if urls.is_empty() {
        urls.push(DEFAULT_RPC_URL.to_string());
    }
    urls
}

fn parse_env_value(body: &str, key: &str) -> Option<String> {
    let mut lines = body.lines().peekable();
    while let Some(raw_line) = lines.next() {
        let mut line = raw_line.trim().to_string();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(rest) = line.strip_prefix("export ") {
            line = rest.trim_start().to_string();
        }
        let Some((name, value)) = line.split_once('=') else {
            continue;
        };
        if name.trim() != key {
            continue;
        }
        let mut value = value.trim().to_string();
        if value.starts_with('[') && !value.ends_with(']') {
            while let Some(next) = lines.peek() {
                value.push(' ');
                value.push_str(next.trim());
                let done = next.trim().ends_with(']');
                lines.next();
                if done {
                    break;
                }
            }
        }
        return Some(clean_env_value(&value));
    }
    None
}

fn clean_env_value(value: &str) -> String {
    let mut quote = None;
    let mut end = value.len();
    for (index, ch) in value.char_indices() {
        if matches!(ch, '"' | '\'') {
            quote = if quote == Some(ch) {
                None
            } else if quote.is_none() {
                Some(ch)
            } else {
                quote
            };
        } else if ch == '#' && quote.is_none() {
            end = index;
            break;
        }
    }
    value[..end].trim().to_string()
}

fn push_rpc_values(urls: &mut Vec<String>, value: &str) {
    let mut text = value
        .trim()
        .trim_matches('"')
        .trim_matches('\'')
        .to_string();
    if text.starts_with('[') && text.ends_with(']') {
        text = text[1..text.len() - 1].to_string();
    }
    for part in text.split([',', ' ', '\n', '\t']) {
        let url = part.trim().trim_matches('"').trim_matches('\'');
        if !url.is_empty() && !urls.iter().any(|existing| existing == url) {
            urls.push(url.to_string());
        }
    }
}

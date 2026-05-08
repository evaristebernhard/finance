use std::collections::BTreeMap;
use std::fs::File;
use std::path::Path;
use std::sync::Arc;
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use arrow::array::{Array, Float64Array, StringArray};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{DateTime, SecondsFormat, Utc};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::{Value, json};

use crate::chog_v1::{
    PartWrite, bool_array, dt_from_utc_string, opt_string_array, parquet_files_under,
    rpc_part_path, string_array, u64_array, write_parquet_part,
};
use crate::{RpcUrlPool, parse_hex_u64, rpc_call, rpc_call_from_pool, to_hex};

pub const CHOG_TOKEN: &str = "0x350035555e10d9afaf1566aaebfced5ba6c27777";
pub const DEX_SNAPSHOT_DATASET: &str = "dex_pairs_snapshots";
pub const DEX_SWAP_DATASET: &str = "dex_pool_swap_logs";
pub const V2_SWAP_TOPIC: &str =
    "0xd78ad95fa46c994b6551d0da85fc275fe61363d4b8e3ee75a7d8e5be0c7f3b6a";
pub const V3_SWAP_TOPIC: &str =
    "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67";

const TOKEN0_SELECTOR: &str = "0x0dfe1681";
const TOKEN1_SELECTOR: &str = "0xd21220a7";
const DECIMALS_SELECTOR: &str = "0x313ce567";
const MAX_RETRIES: usize = 3;

#[derive(Debug, Clone)]
pub struct DexPool {
    pub fetched_at_utc: String,
    pub chain_id: String,
    pub dex_id: String,
    pub labels: String,
    pub pair_address: String,
    pub base_address: String,
    pub base_symbol: String,
    pub quote_address: String,
    pub quote_symbol: String,
    pub liquidity_usd: Option<f64>,
    pub volume_h24_usd: Option<f64>,
}

impl DexPool {
    pub fn family_hint(&self) -> &'static str {
        let labels = self.labels.to_ascii_lowercase();
        if labels.split('|').any(|label| label == "v3") {
            "v3"
        } else if labels.split('|').any(|label| label == "v2") {
            "v2"
        } else {
            "unknown"
        }
    }
}

#[derive(Debug, Clone)]
pub struct PoolMetadata {
    pub pool: DexPool,
    pub token0_address: String,
    pub token1_address: String,
    pub token0_symbol: String,
    pub token1_symbol: String,
    pub token0_decimals: u8,
    pub token1_decimals: u8,
    pub chog_token_index: u8,
    pub quote_address: String,
    pub quote_symbol: String,
    pub quote_decimals: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SwapFamily {
    V2,
    V3,
}

impl SwapFamily {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::V2 => "v2",
            Self::V3 => "v3",
        }
    }

    pub fn topic(self) -> &'static str {
        match self {
            Self::V2 => V2_SWAP_TOPIC,
            Self::V3 => V3_SWAP_TOPIC,
        }
    }
}

pub const SWAP_FAMILIES: [SwapFamily; 2] = [SwapFamily::V2, SwapFamily::V3];

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RpcSwapLog {
    pub address: String,
    pub topics: Vec<String>,
    pub data: String,
    pub block_number: String,
    pub block_timestamp: Option<String>,
    pub transaction_hash: String,
    pub transaction_index: String,
    pub log_index: String,
    pub removed: bool,
}

#[derive(Debug, Clone)]
pub struct DexSwapRow {
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
    pub token0_symbol: String,
    pub token1_symbol: String,
    pub token0_decimals: u64,
    pub token1_decimals: u64,
    pub quote_address: String,
    pub quote_symbol: String,
    pub amount0_delta_raw: String,
    pub amount1_delta_raw: String,
    pub amount0_delta_token: String,
    pub amount1_delta_token: String,
    pub direction: String,
    pub chog_abs: String,
    pub quote_abs: String,
    pub price_quote_per_chog: String,
    pub sqrt_price_x96: Option<String>,
    pub liquidity_raw: Option<String>,
    pub tick: Option<String>,
    pub removed: bool,
}

#[derive(Debug, Clone)]
struct SwapDeltas {
    amount0_delta_raw: i128,
    amount1_delta_raw: i128,
    sqrt_price_x96: Option<String>,
    liquidity_raw: Option<String>,
    tick: Option<String>,
}

pub fn read_latest_dex_pools(data_root: &Path) -> Result<Vec<DexPool>> {
    let root = data_root
        .join(crate::chog_v1::RAW_DIR)
        .join(DEX_SNAPSHOT_DATASET);
    let mut rows = Vec::new();
    for path in parquet_files_under(&root)? {
        read_dex_pool_rows(&path, &mut rows)?;
    }
    if rows.is_empty() {
        bail!(
            "no Dex pool snapshots found under {}; run dex_snapshot first",
            root.display()
        );
    }

    let latest = rows
        .iter()
        .map(|row| row.fetched_at_utc.as_str())
        .max()
        .ok_or_else(|| anyhow!("no Dex pool snapshots found"))?
        .to_string();
    let mut by_address = BTreeMap::<String, DexPool>::new();
    for row in rows {
        if row.fetched_at_utc == latest && pool_contains_chog(&row) {
            by_address.insert(row.pair_address.to_ascii_lowercase(), row);
        }
    }
    let mut pools = by_address.into_values().collect::<Vec<_>>();
    pools.sort_by(|a, b| {
        b.liquidity_usd
            .unwrap_or(0.0)
            .total_cmp(&a.liquidity_usd.unwrap_or(0.0))
            .then_with(|| a.pair_address.cmp(&b.pair_address))
    });
    Ok(pools)
}

pub fn resolve_pool_metadata(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool: &DexPool,
) -> Result<PoolMetadata> {
    let token0_address = eth_call_address(client, rpc_urls, &pool.pair_address, TOKEN0_SELECTOR)
        .with_context(|| format!("failed token0() for {}", pool.pair_address))?;
    let token1_address = eth_call_address(client, rpc_urls, &pool.pair_address, TOKEN1_SELECTOR)
        .with_context(|| format!("failed token1() for {}", pool.pair_address))?;
    let token0_decimals = eth_call_u8(client, rpc_urls, &token0_address, DECIMALS_SELECTOR)
        .with_context(|| format!("failed decimals() for token0 {token0_address}"))?;
    let token1_decimals = eth_call_u8(client, rpc_urls, &token1_address, DECIMALS_SELECTOR)
        .with_context(|| format!("failed decimals() for token1 {token1_address}"))?;

    let chog = CHOG_TOKEN.to_ascii_lowercase();
    let token0_lower = token0_address.to_ascii_lowercase();
    let token1_lower = token1_address.to_ascii_lowercase();
    let chog_token_index = if token0_lower == chog {
        0
    } else if token1_lower == chog {
        1
    } else {
        bail!(
            "pool {} token0/token1 do not include CHOG: {token0_address}/{token1_address}",
            pool.pair_address
        );
    };

    let token0_symbol = symbol_for_address(pool, &token0_address);
    let token1_symbol = symbol_for_address(pool, &token1_address);
    let (quote_address, quote_symbol, quote_decimals) = if chog_token_index == 0 {
        (
            token1_address.clone(),
            token1_symbol.clone(),
            token1_decimals,
        )
    } else {
        (
            token0_address.clone(),
            token0_symbol.clone(),
            token0_decimals,
        )
    };

    Ok(PoolMetadata {
        pool: pool.clone(),
        token0_address,
        token1_address,
        token0_symbol,
        token1_symbol,
        token0_decimals,
        token1_decimals,
        chog_token_index,
        quote_address,
        quote_symbol,
        quote_decimals,
    })
}

pub fn resolve_pool_metadata_with_retry(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool: &DexPool,
) -> Result<PoolMetadata> {
    let mut last_error = None;
    for attempt in 1..=MAX_RETRIES {
        match resolve_pool_metadata(client, rpc_urls, pool) {
            Ok(metadata) => return Ok(metadata),
            Err(error) => {
                last_error = Some(error);
                if attempt < MAX_RETRIES {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("pool metadata resolution failed without an error")))
}

pub fn pool_metadata_from_snapshot(pool: &DexPool) -> Result<PoolMetadata> {
    let token0_address = pool.base_address.to_ascii_lowercase();
    let token1_address = pool.quote_address.to_ascii_lowercase();
    let token0_decimals = decimals_for_symbol(&pool.base_symbol);
    let token1_decimals = decimals_for_symbol(&pool.quote_symbol);
    let chog = CHOG_TOKEN.to_ascii_lowercase();
    let chog_token_index = if token0_address == chog {
        0
    } else if token1_address == chog {
        1
    } else {
        bail!(
            "snapshot pool {} does not include CHOG: {}/{}",
            pool.pair_address,
            pool.base_address,
            pool.quote_address
        );
    };
    let (quote_address, quote_symbol, quote_decimals) = if chog_token_index == 0 {
        (
            token1_address.clone(),
            pool.quote_symbol.clone(),
            token1_decimals,
        )
    } else {
        (
            token0_address.clone(),
            pool.base_symbol.clone(),
            token0_decimals,
        )
    };

    Ok(PoolMetadata {
        pool: pool.clone(),
        token0_address,
        token1_address,
        token0_symbol: pool.base_symbol.clone(),
        token1_symbol: pool.quote_symbol.clone(),
        token0_decimals,
        token1_decimals,
        chog_token_index,
        quote_address,
        quote_symbol,
        quote_decimals,
    })
}

pub fn fetch_swap_logs_with_retry(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool_address: &str,
    family: SwapFamily,
    from_block: u64,
    to_block: u64,
) -> Result<Vec<RpcSwapLog>> {
    let mut last_error = None;
    let max_attempts = MAX_RETRIES * rpc_urls.len();
    for attempt in 1..=max_attempts {
        let rpc_url = rpc_urls.next_url();
        match fetch_swap_logs(client, rpc_url, pool_address, family, from_block, to_block) {
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

pub fn fetch_swap_logs_for_addresses_with_retry(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool_addresses: &[String],
    family: SwapFamily,
    from_block: u64,
    to_block: u64,
) -> Result<Vec<RpcSwapLog>> {
    let mut last_error = None;
    let max_attempts = MAX_RETRIES * rpc_urls.len();
    for attempt in 1..=max_attempts {
        let rpc_url = rpc_urls.next_url();
        match fetch_swap_logs_for_addresses(
            client,
            rpc_url,
            pool_addresses,
            family,
            from_block,
            to_block,
        ) {
            Ok(logs) => return Ok(logs),
            Err(error) => {
                last_error = Some(error);
                if attempt < max_attempts {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }

    Err(last_error.unwrap_or_else(|| anyhow!("batched swap log fetch failed without an error")))
}

pub fn fetch_swap_logs_for_address_batch_with_retry(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool_addresses: &[String],
    ranges: &[(u64, u64)],
) -> Result<Vec<Vec<RpcSwapLog>>> {
    let mut last_error = None;
    let max_attempts = MAX_RETRIES * rpc_urls.len();
    for attempt in 1..=max_attempts {
        let rpc_url = rpc_urls.next_url();
        match fetch_swap_logs_for_address_batch(client, rpc_url, pool_addresses, ranges) {
            Ok(logs) => return Ok(logs),
            Err(error) => {
                last_error = Some(error);
                if attempt < max_attempts {
                    sleep(Duration::from_millis(500 * attempt as u64));
                }
            }
        }
    }

    Err(last_error.unwrap_or_else(|| anyhow!("JSON-RPC batch swap fetch failed without an error")))
}

pub fn parse_swap_log(
    fetched_at: &str,
    metadata: &PoolMetadata,
    family: SwapFamily,
    log: RpcSwapLog,
) -> Result<DexSwapRow> {
    if log.topics.len() < 3 {
        bail!("swap log has fewer than 3 topics: {:?}", log.topics);
    }

    let deltas = match family {
        SwapFamily::V2 => parse_v2_deltas(&log.data)?,
        SwapFamily::V3 => parse_v3_deltas(&log.data)?,
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

    let chog_delta_raw = if metadata.chog_token_index == 0 {
        deltas.amount0_delta_raw
    } else {
        deltas.amount1_delta_raw
    };
    let quote_delta_raw = if metadata.chog_token_index == 0 {
        deltas.amount1_delta_raw
    } else {
        deltas.amount0_delta_raw
    };
    let chog_abs_raw = chog_delta_raw.unsigned_abs();
    let quote_abs_raw = quote_delta_raw.unsigned_abs();
    let chog_decimals = if metadata.chog_token_index == 0 {
        metadata.token0_decimals
    } else {
        metadata.token1_decimals
    };
    let chog_abs_float = scale_u128_to_f64(chog_abs_raw, chog_decimals);
    let quote_abs_float = scale_u128_to_f64(quote_abs_raw, metadata.quote_decimals);
    let price_quote_per_chog = if chog_abs_float > 0.0 {
        format!("{:.18}", quote_abs_float / chog_abs_float)
    } else {
        String::new()
    };

    Ok(DexSwapRow {
        fetched_at_utc: fetched_at.to_string(),
        block_number,
        block_timestamp,
        block_datetime_utc,
        transaction_hash: log.transaction_hash,
        transaction_index: parse_hex_u64(&log.transaction_index)?,
        log_index: parse_hex_u64(&log.log_index)?,
        pool_address: log.address.to_ascii_lowercase(),
        dex_id: metadata.pool.dex_id.clone(),
        family: family.as_str().to_string(),
        swap_topic: family.topic().to_string(),
        sender: topic_to_address(&log.topics[1])?,
        recipient: topic_to_address(&log.topics[2])?,
        token0_address: metadata.token0_address.clone(),
        token1_address: metadata.token1_address.clone(),
        token0_symbol: metadata.token0_symbol.clone(),
        token1_symbol: metadata.token1_symbol.clone(),
        token0_decimals: u64::from(metadata.token0_decimals),
        token1_decimals: u64::from(metadata.token1_decimals),
        quote_address: metadata.quote_address.clone(),
        quote_symbol: metadata.quote_symbol.clone(),
        amount0_delta_raw: deltas.amount0_delta_raw.to_string(),
        amount1_delta_raw: deltas.amount1_delta_raw.to_string(),
        amount0_delta_token: format_signed_decimal(
            deltas.amount0_delta_raw,
            metadata.token0_decimals,
        ),
        amount1_delta_token: format_signed_decimal(
            deltas.amount1_delta_raw,
            metadata.token1_decimals,
        ),
        direction: direction_for_chog_delta(chog_delta_raw).to_string(),
        chog_abs: format_unsigned_decimal(chog_abs_raw, chog_decimals),
        quote_abs: format_unsigned_decimal(quote_abs_raw, metadata.quote_decimals),
        price_quote_per_chog,
        sqrt_price_x96: deltas.sqrt_price_x96,
        liquidity_raw: deltas.liquidity_raw,
        tick: deltas.tick,
        removed: log.removed,
    })
}

pub fn direction_for_chog_delta(chog_delta_raw: i128) -> &'static str {
    if chog_delta_raw > 0 {
        "sell_chog"
    } else if chog_delta_raw < 0 {
        "buy_chog"
    } else {
        "unknown"
    }
}

pub fn dex_swap_schema() -> SchemaRef {
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
        Field::new("token0_symbol", DataType::Utf8, false),
        Field::new("token1_symbol", DataType::Utf8, false),
        Field::new("token0_decimals", DataType::UInt64, false),
        Field::new("token1_decimals", DataType::UInt64, false),
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("amount0_delta_raw", DataType::Utf8, false),
        Field::new("amount1_delta_raw", DataType::Utf8, false),
        Field::new("amount0_delta_token", DataType::Utf8, false),
        Field::new("amount1_delta_token", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("chog_abs", DataType::Utf8, false),
        Field::new("quote_abs", DataType::Utf8, false),
        Field::new("price_quote_per_chog", DataType::Utf8, false),
        Field::new("sqrt_price_x96", DataType::Utf8, true),
        Field::new("liquidity_raw", DataType::Utf8, true),
        Field::new("tick", DataType::Utf8, true),
        Field::new("removed", DataType::Boolean, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

pub fn write_dex_swap_parts(
    data_root: &Path,
    schema: SchemaRef,
    rows: &[DexSwapRow],
    from_block: u64,
    to_block: u64,
    collector: &str,
) -> Result<Vec<PartWrite>> {
    let mut by_dt = BTreeMap::<String, Vec<DexSwapRow>>::new();
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
                        .map(|row| row.amount0_delta_token.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.amount1_delta_token.clone())
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
                        .map(|row| row.quote_abs.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.price_quote_per_chog.clone())
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
                string_array(&dt_values),
            ],
        )?;
        parts.push(write_parquet_part(
            &rpc_part_path(
                data_root,
                DEX_SWAP_DATASET,
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

fn read_dex_pool_rows(path: &Path, rows: &mut Vec<DexPool>) -> Result<()> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .with_context(|| format!("failed to read parquet metadata {}", path.display()))?;
    let mut reader = builder
        .with_batch_size(1024)
        .build()
        .with_context(|| format!("failed to build parquet reader {}", path.display()))?;
    for batch in &mut reader {
        let batch = batch.with_context(|| format!("failed reading {}", path.display()))?;
        let fetched_at_utc = string_column(&batch, "fetched_at_utc")?;
        let chain_id = string_column(&batch, "chain_id")?;
        let dex_id = string_column(&batch, "dex_id")?;
        let labels = string_column(&batch, "labels")?;
        let pair_address = string_column(&batch, "pair_address")?;
        let base_address = string_column(&batch, "base_address")?;
        let base_symbol = string_column(&batch, "base_symbol")?;
        let quote_address = string_column(&batch, "quote_address")?;
        let quote_symbol = string_column(&batch, "quote_symbol")?;
        let liquidity_usd = optional_float64_column(&batch, "liquidity_usd")?;
        let volume_h24_usd = optional_float64_column(&batch, "volume_h24_usd")?;
        for index in 0..batch.num_rows() {
            rows.push(DexPool {
                fetched_at_utc: string_value(fetched_at_utc, index),
                chain_id: string_value(chain_id, index),
                dex_id: string_value(dex_id, index),
                labels: string_value(labels, index),
                pair_address: string_value(pair_address, index),
                base_address: string_value(base_address, index),
                base_symbol: string_value(base_symbol, index),
                quote_address: string_value(quote_address, index),
                quote_symbol: string_value(quote_symbol, index),
                liquidity_usd: optional_f64_value(liquidity_usd, index),
                volume_h24_usd: optional_f64_value(volume_h24_usd, index),
            });
        }
    }
    Ok(())
}

fn pool_contains_chog(pool: &DexPool) -> bool {
    pool.base_address.eq_ignore_ascii_case(CHOG_TOKEN)
        || pool.quote_address.eq_ignore_ascii_case(CHOG_TOKEN)
}

fn fetch_swap_logs(
    client: &Client,
    rpc_url: &str,
    pool_address: &str,
    family: SwapFamily,
    from_block: u64,
    to_block: u64,
) -> Result<Vec<RpcSwapLog>> {
    let params = json!([
        {
            "address": pool_address,
            "fromBlock": to_hex(from_block),
            "toBlock": to_hex(to_block),
            "topics": [family.topic()],
        }
    ]);
    rpc_call(client, rpc_url, "eth_getLogs", params)
}

fn fetch_swap_logs_for_addresses(
    client: &Client,
    rpc_url: &str,
    pool_addresses: &[String],
    family: SwapFamily,
    from_block: u64,
    to_block: u64,
) -> Result<Vec<RpcSwapLog>> {
    let params = json!([
        {
            "address": pool_addresses,
            "fromBlock": to_hex(from_block),
            "toBlock": to_hex(to_block),
            "topics": [family.topic()],
        }
    ]);
    rpc_call(client, rpc_url, "eth_getLogs", params)
}

#[derive(Debug, Deserialize)]
struct BatchRpcResponse {
    id: u64,
    result: Option<Vec<RpcSwapLog>>,
    error: Option<BatchRpcError>,
}

#[derive(Debug, Deserialize)]
struct BatchRpcError {
    code: i64,
    message: String,
}

fn fetch_swap_logs_for_address_batch(
    client: &Client,
    rpc_url: &str,
    pool_addresses: &[String],
    ranges: &[(u64, u64)],
) -> Result<Vec<Vec<RpcSwapLog>>> {
    if ranges.is_empty() {
        return Ok(Vec::new());
    }
    let body = ranges
        .iter()
        .enumerate()
        .map(|(index, (from_block, to_block))| {
            json!({
                "jsonrpc": "2.0",
                "id": index as u64,
                "method": "eth_getLogs",
                "params": [
                    {
                        "address": pool_addresses,
                        "fromBlock": to_hex(*from_block),
                        "toBlock": to_hex(*to_block),
                        "topics": [[V2_SWAP_TOPIC, V3_SWAP_TOPIC]],
                    }
                ],
            })
        })
        .collect::<Vec<Value>>();

    let response = client
        .post(rpc_url)
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .context("failed JSON-RPC batch eth_getLogs request")?;
    let status = response.status();
    let text = response
        .text()
        .context("failed to read RPC batch response")?;
    if !status.is_success() {
        bail!("RPC batch eth_getLogs failed with status {status}: {text}");
    }
    let responses: Vec<BatchRpcResponse> = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse RPC batch response: {text}"))?;
    if responses.len() != ranges.len() {
        bail!(
            "RPC batch response count {} does not match request count {}",
            responses.len(),
            ranges.len()
        );
    }

    let mut by_id = BTreeMap::<u64, Vec<RpcSwapLog>>::new();
    for response in responses {
        if let Some(error) = response.error {
            bail!(
                "RPC batch item {} failed {}: {}",
                response.id,
                error.code,
                error.message
            );
        }
        by_id.insert(response.id, response.result.unwrap_or_default());
    }

    let mut logs = Vec::with_capacity(ranges.len());
    for index in 0..ranges.len() {
        logs.push(by_id.remove(&(index as u64)).unwrap_or_default());
    }
    Ok(logs)
}

fn eth_call_address(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    to: &str,
    selector: &str,
) -> Result<String> {
    let value: String = rpc_call_from_pool(
        client,
        rpc_urls,
        "eth_call",
        json!([{ "to": to, "data": selector }, "latest"]),
    )?;
    decode_address_word(&value)
}

fn eth_call_u8(client: &Client, rpc_urls: &RpcUrlPool, to: &str, selector: &str) -> Result<u8> {
    let value: String = rpc_call_from_pool(
        client,
        rpc_urls,
        "eth_call",
        json!([{ "to": to, "data": selector }, "latest"]),
    )?;
    let value = parse_u256_to_u128(value.trim_start_matches("0x"))?;
    if value > u8::MAX as u128 {
        bail!("eth_call value does not fit u8: {value}");
    }
    Ok(value as u8)
}

fn decode_address_word(value: &str) -> Result<String> {
    let word = value.trim_start_matches("0x");
    if word.len() < 64 {
        bail!("eth_call address result is shorter than 32 bytes: {value}");
    }
    Ok(format!("0x{}", &word[word.len() - 40..]).to_ascii_lowercase())
}

fn symbol_for_address(pool: &DexPool, address: &str) -> String {
    if pool.base_address.eq_ignore_ascii_case(address) {
        pool.base_symbol.clone()
    } else if pool.quote_address.eq_ignore_ascii_case(address) {
        pool.quote_symbol.clone()
    } else {
        "UNKNOWN".to_string()
    }
}

fn decimals_for_symbol(symbol: &str) -> u8 {
    match symbol.to_ascii_uppercase().as_str() {
        "USDC" | "USDT" => 6,
        _ => 18,
    }
}

fn parse_v2_deltas(data: &str) -> Result<SwapDeltas> {
    let chunks = data_chunks(data)?;
    if chunks.len() < 4 {
        bail!("v2 swap data has fewer than 4 words: {data}");
    }
    let amount0_in = parse_u256_to_u128(chunks[0])?;
    let amount1_in = parse_u256_to_u128(chunks[1])?;
    let amount0_out = parse_u256_to_u128(chunks[2])?;
    let amount1_out = parse_u256_to_u128(chunks[3])?;
    Ok(SwapDeltas {
        amount0_delta_raw: u128_diff_to_i128(amount0_in, amount0_out)?,
        amount1_delta_raw: u128_diff_to_i128(amount1_in, amount1_out)?,
        sqrt_price_x96: None,
        liquidity_raw: None,
        tick: None,
    })
}

fn parse_v3_deltas(data: &str) -> Result<SwapDeltas> {
    let chunks = data_chunks(data)?;
    if chunks.len() < 5 {
        bail!("v3 swap data has fewer than 5 words: {data}");
    }
    Ok(SwapDeltas {
        amount0_delta_raw: parse_i256_to_i128(chunks[0])?,
        amount1_delta_raw: parse_i256_to_i128(chunks[1])?,
        sqrt_price_x96: Some(parse_u256_decimal(chunks[2])?),
        liquidity_raw: Some(parse_u256_decimal(chunks[3])?),
        tick: Some(parse_i256_to_i128(chunks[4])?.to_string()),
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

fn parse_u256_to_u128(word: &str) -> Result<u128> {
    if word.len() != 64 {
        bail!("expected 32-byte word, got {word}");
    }
    let high = &word[..32];
    if high != "00000000000000000000000000000000" {
        bail!("uint256 does not fit u128: 0x{word}");
    }
    u128::from_str_radix(&word[32..], 16).with_context(|| format!("invalid uint256: 0x{word}"))
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

fn u128_diff_to_i128(left: u128, right: u128) -> Result<i128> {
    if left >= right {
        let value = left - right;
        if value > i128::MAX as u128 {
            bail!("positive delta does not fit i128: {value}");
        }
        Ok(value as i128)
    } else {
        let value = right - left;
        if value > i128::MAX as u128 {
            bail!("negative delta magnitude does not fit i128: {value}");
        }
        Ok(-(value as i128))
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

fn format_signed_decimal(value: i128, decimals: u8) -> String {
    if value < 0 {
        format!(
            "-{}",
            format_unsigned_decimal(value.unsigned_abs(), decimals)
        )
    } else {
        format_unsigned_decimal(value as u128, decimals)
    }
}

fn format_unsigned_decimal(value: u128, decimals: u8) -> String {
    if decimals == 0 {
        return value.to_string();
    }
    let scale = 10u128.pow(u32::from(decimals));
    let whole = value / scale;
    let frac = value % scale;
    let mut frac_text = format!("{:0width$}", frac, width = decimals as usize);
    while frac_text.len() > 1 && frac_text.ends_with('0') {
        frac_text.pop();
    }
    format!("{whole}.{frac_text}")
}

fn scale_u128_to_f64(value: u128, decimals: u8) -> f64 {
    value as f64 / 10f64.powi(i32::from(decimals))
}

fn topic_to_address(topic: &str) -> Result<String> {
    let topic = topic.trim_start_matches("0x");
    if topic.len() != 64 {
        bail!("invalid indexed address topic: 0x{topic}");
    }
    Ok(format!("0x{}", &topic[24..]).to_ascii_lowercase())
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

fn optional_float64_column<'a>(
    batch: &'a RecordBatch,
    name: &str,
) -> Result<Option<&'a Float64Array>> {
    let Ok(index) = batch.schema().index_of(name) else {
        return Ok(None);
    };
    Ok(batch.column(index).as_any().downcast_ref::<Float64Array>())
}

fn string_value(values: &StringArray, index: usize) -> String {
    if values.is_null(index) {
        String::new()
    } else {
        values.value(index).to_string()
    }
}

fn optional_f64_value(values: Option<&Float64Array>, index: usize) -> Option<f64> {
    values.and_then(|values| {
        if values.is_null(index) {
            None
        } else {
            Some(values.value(index))
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn word(value: u128) -> String {
        format!("{value:064x}")
    }

    fn signed_word(value: i128) -> String {
        if value >= 0 {
            word(value as u128)
        } else {
            let encoded = (!value.unsigned_abs()).wrapping_add(1);
            format!("ffffffffffffffffffffffffffffffff{encoded:032x}")
        }
    }

    #[test]
    fn parses_v2_pool_deltas() {
        let data = format!(
            "0x{}{}{}{}",
            word(1_000_000_000_000_000_000),
            word(0),
            word(0),
            word(50_000_000_000_000_000)
        );
        let deltas = parse_v2_deltas(&data).unwrap();
        assert_eq!(deltas.amount0_delta_raw, 1_000_000_000_000_000_000);
        assert_eq!(deltas.amount1_delta_raw, -50_000_000_000_000_000);
    }

    #[test]
    fn parses_v3_pool_deltas() {
        let data = format!(
            "0x{}{}{}{}{}",
            signed_word(-1_000_000_000_000_000_000),
            signed_word(50_000_000_000_000_000),
            word(42),
            word(123),
            signed_word(-10)
        );
        let deltas = parse_v3_deltas(&data).unwrap();
        assert_eq!(deltas.amount0_delta_raw, -1_000_000_000_000_000_000);
        assert_eq!(deltas.amount1_delta_raw, 50_000_000_000_000_000);
        assert_eq!(deltas.sqrt_price_x96.as_deref(), Some("42"));
        assert_eq!(deltas.liquidity_raw.as_deref(), Some("123"));
        assert_eq!(deltas.tick.as_deref(), Some("-10"));
    }

    #[test]
    fn formats_scaled_values_without_trailing_noise() {
        assert_eq!(
            format_unsigned_decimal(1_230_000_000_000_000_000, 18),
            "1.23"
        );
        assert_eq!(format_signed_decimal(-50_000_000_000_000_000, 18), "-0.05");
    }

    #[test]
    fn classifies_chog_direction_from_pool_delta() {
        assert_eq!(direction_for_chog_delta(1), "sell_chog");
        assert_eq!(direction_for_chog_delta(-1), "buy_chog");
        assert_eq!(direction_for_chog_delta(0), "unknown");
    }
}

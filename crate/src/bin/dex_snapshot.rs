use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chog_prices::chog_v1::{
    ChogCollectionRunRecord, OutputFormat, default_data_root_path, dt_from_utc_string,
    opt_f64_array, opt_i64_array, opt_u64_array, snapshot_part_path, string_array,
    write_collection_run_parquet, write_parquet_part, write_schema_metadata,
};
use chrono::{DateTime, SecondsFormat, Utc};
use clap::Parser;
use reqwest::blocking::Client;
use serde::Deserialize;

const DEFAULT_TOKEN: &str = "0x350035555e10d9afaf1566aaebfced5ba6c27777";
const DEFAULT_CHAIN: &str = "monad";
const COLLECTOR: &str = "dex_snapshot";
const DATASET: &str = "dex_pairs_snapshots";

#[derive(Debug, Parser)]
#[command(
    name = "dex_snapshot",
    about = "Fetch a current CHOG pair snapshot from DexScreener."
)]
struct Args {
    #[arg(long, default_value = DEFAULT_CHAIN)]
    chain: String,

    #[arg(long, default_value = DEFAULT_TOKEN)]
    token: String,

    #[arg(long)]
    output: Option<PathBuf>,

    /// Output format. CSV preserves the legacy overwrite path; Parquet appends CHOG v1 snapshots.
    #[arg(long, value_enum, default_value_t = OutputFormat::Csv)]
    format: OutputFormat,

    /// CHOG v1 data root used when --format parquet.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Resolve output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Pair {
    chain_id: String,
    dex_id: String,
    url: String,
    pair_address: String,
    labels: Option<Vec<String>>,
    base_token: Token,
    quote_token: Token,
    price_native: Option<String>,
    price_usd: Option<String>,
    txns: Option<Windowed<Txns>>,
    volume: Option<Windowed<f64>>,
    price_change: Option<Windowed<f64>>,
    liquidity: Option<Liquidity>,
    fdv: Option<f64>,
    market_cap: Option<f64>,
    pair_created_at: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct Token {
    address: String,
    name: String,
    symbol: String,
}

#[derive(Debug, Deserialize)]
struct Windowed<T> {
    m5: Option<T>,
    h1: Option<T>,
    h6: Option<T>,
    h24: Option<T>,
}

#[derive(Debug, Deserialize)]
struct Txns {
    buys: Option<u64>,
    sells: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct Liquidity {
    usd: Option<f64>,
    base: Option<f64>,
    quote: Option<f64>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    match args.format {
        OutputFormat::Csv => run_csv(args),
        OutputFormat::Parquet => run_parquet(args),
    }
}

fn run_csv(args: Args) -> Result<()> {
    let (fetched_at, pairs) = fetch_pairs(&args)?;

    let output = args.output.unwrap_or_else(default_output_path);
    write_csv(&output, &pairs, fetched_at)?;
    print_summary(&output, &pairs);

    Ok(())
}

fn run_parquet(args: Args) -> Result<()> {
    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DATASET}");
        println!("data root: {}", data_root.display());
        return Ok(());
    }

    let (fetched_at, pairs) = fetch_pairs(&args)?;
    let fetched_at_utc = fetched_at.to_rfc3339_opts(SecondsFormat::Secs, true);
    let dt = dt_from_utc_string(&fetched_at_utc);
    let rows = build_rows(&pairs, &fetched_at_utc);
    let schema = dex_schema();
    write_schema_metadata(&data_root, DATASET, schema.as_ref(), &["dt"])?;
    let part = write_parquet_part(
        &snapshot_part_path(&data_root, DATASET, &dt, COLLECTOR, &fetched_at_utc),
        schema.clone(),
        rows_to_batch(schema, &rows, &dt)?,
    )?;

    let finished_at = Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true);
    write_collection_run_parquet(
        &data_root,
        &ChogCollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DATASET.to_string(),
            chain: args.chain.clone(),
            address: args.token.clone(),
            topic0: String::new(),
            from_block: None,
            to_block: None,
            time_window_start_utc: fetched_at_utc.clone(),
            time_window_end_utc: fetched_at_utc.clone(),
            output_parts: part.path.display().to_string(),
            rows_written: rows.len() as u64,
            chunks_completed: 1,
            status: "completed".to_string(),
            error: String::new(),
            started_at_utc: fetched_at_utc,
            finished_at_utc: finished_at,
        },
    )?;

    println!("pairs written: {}", rows.len());
    println!("parquet: {}", part.path.display());
    Ok(())
}

fn fetch_pairs(args: &Args) -> Result<(DateTime<Utc>, Vec<Pair>)> {
    let fetched_at = Utc::now();
    let url = format!(
        "https://api.dexscreener.com/token-pairs/v1/{}/{}",
        args.chain, args.token
    );

    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-dex-snapshot/0.1")
        .build()
        .context("failed to build HTTP client")?;

    let response = client
        .get(&url)
        .header("accept", "application/json")
        .send()
        .with_context(|| format!("failed to request {url}"))?;

    let status = response.status();
    let body = response.text().context("failed to read DexScreener body")?;
    if !status.is_success() {
        anyhow::bail!("DexScreener request failed with status {status}: {body}");
    }

    let mut pairs: Vec<Pair> = serde_json::from_str(&body)
        .with_context(|| format!("failed to parse DexScreener response: {body}"))?;
    pairs.sort_by(|a, b| {
        let a_liq = a.liquidity.as_ref().and_then(|l| l.usd).unwrap_or(0.0);
        let b_liq = b.liquidity.as_ref().and_then(|l| l.usd).unwrap_or(0.0);
        b_liq.total_cmp(&a_liq)
    });

    Ok((fetched_at, pairs))
}

#[derive(Debug, Clone)]
struct DexSnapshotRow {
    fetched_at_utc: String,
    chain_id: String,
    dex_id: String,
    labels: String,
    pair_address: String,
    base_address: String,
    base_symbol: String,
    base_name: String,
    quote_address: String,
    quote_symbol: String,
    quote_name: String,
    price_native: String,
    price_usd: String,
    m5_buys: Option<u64>,
    m5_sells: Option<u64>,
    h1_buys: Option<u64>,
    h1_sells: Option<u64>,
    h6_buys: Option<u64>,
    h6_sells: Option<u64>,
    h24_buys: Option<u64>,
    h24_sells: Option<u64>,
    h24_buy_ratio: Option<f64>,
    h24_count_imbalance: Option<f64>,
    volume_m5_usd: Option<f64>,
    volume_h1_usd: Option<f64>,
    volume_h6_usd: Option<f64>,
    volume_h24_usd: Option<f64>,
    price_change_m5_pct: Option<f64>,
    price_change_h1_pct: Option<f64>,
    price_change_h6_pct: Option<f64>,
    price_change_h24_pct: Option<f64>,
    liquidity_usd: Option<f64>,
    liquidity_base: Option<f64>,
    liquidity_quote: Option<f64>,
    volume_h24_to_liquidity: Option<f64>,
    fdv: Option<f64>,
    market_cap: Option<f64>,
    pair_created_at_ms: Option<i64>,
    pair_created_at_utc: String,
    url: String,
}

fn build_rows(pairs: &[Pair], fetched_at_utc: &str) -> Vec<DexSnapshotRow> {
    pairs
        .iter()
        .map(|pair| {
            let h24_buys = txns(pair, |w| w.h24.as_ref().and_then(|t| t.buys));
            let h24_sells = txns(pair, |w| w.h24.as_ref().and_then(|t| t.sells));
            let h24_total = h24_buys.unwrap_or(0) + h24_sells.unwrap_or(0);
            let h24_buy_ratio = if h24_total == 0 {
                None
            } else {
                Some(h24_buys.unwrap_or(0) as f64 / h24_total as f64)
            };
            let h24_count_imbalance = if h24_total == 0 {
                None
            } else {
                Some(
                    (h24_buys.unwrap_or(0) as f64 - h24_sells.unwrap_or(0) as f64)
                        / h24_total as f64,
                )
            };
            let volume_h24 = window(pair.volume.as_ref(), |w| w.h24);
            let liquidity_usd = pair.liquidity.as_ref().and_then(|l| l.usd);
            let volume_h24_to_liquidity = match (volume_h24, liquidity_usd) {
                (Some(volume), Some(liquidity)) if liquidity > 0.0 => Some(volume / liquidity),
                _ => None,
            };

            DexSnapshotRow {
                fetched_at_utc: fetched_at_utc.to_string(),
                chain_id: pair.chain_id.clone(),
                dex_id: pair.dex_id.clone(),
                labels: pair
                    .labels
                    .as_ref()
                    .map(|v| v.join("|"))
                    .unwrap_or_default(),
                pair_address: pair.pair_address.clone(),
                base_address: pair.base_token.address.clone(),
                base_symbol: pair.base_token.symbol.clone(),
                base_name: pair.base_token.name.clone(),
                quote_address: pair.quote_token.address.clone(),
                quote_symbol: pair.quote_token.symbol.clone(),
                quote_name: pair.quote_token.name.clone(),
                price_native: pair.price_native.clone().unwrap_or_default(),
                price_usd: pair.price_usd.clone().unwrap_or_default(),
                m5_buys: txns(pair, |w| w.m5.as_ref().and_then(|t| t.buys)),
                m5_sells: txns(pair, |w| w.m5.as_ref().and_then(|t| t.sells)),
                h1_buys: txns(pair, |w| w.h1.as_ref().and_then(|t| t.buys)),
                h1_sells: txns(pair, |w| w.h1.as_ref().and_then(|t| t.sells)),
                h6_buys: txns(pair, |w| w.h6.as_ref().and_then(|t| t.buys)),
                h6_sells: txns(pair, |w| w.h6.as_ref().and_then(|t| t.sells)),
                h24_buys,
                h24_sells,
                h24_buy_ratio,
                h24_count_imbalance,
                volume_m5_usd: window(pair.volume.as_ref(), |w| w.m5),
                volume_h1_usd: window(pair.volume.as_ref(), |w| w.h1),
                volume_h6_usd: window(pair.volume.as_ref(), |w| w.h6),
                volume_h24_usd: volume_h24,
                price_change_m5_pct: window(pair.price_change.as_ref(), |w| w.m5),
                price_change_h1_pct: window(pair.price_change.as_ref(), |w| w.h1),
                price_change_h6_pct: window(pair.price_change.as_ref(), |w| w.h6),
                price_change_h24_pct: window(pair.price_change.as_ref(), |w| w.h24),
                liquidity_usd,
                liquidity_base: pair.liquidity.as_ref().and_then(|l| l.base),
                liquidity_quote: pair.liquidity.as_ref().and_then(|l| l.quote),
                volume_h24_to_liquidity,
                fdv: pair.fdv,
                market_cap: pair.market_cap,
                pair_created_at_ms: pair.pair_created_at,
                pair_created_at_utc: pair
                    .pair_created_at
                    .and_then(DateTime::<Utc>::from_timestamp_millis)
                    .map(|dt| dt.to_rfc3339_opts(SecondsFormat::Secs, true))
                    .unwrap_or_default(),
                url: pair.url.clone(),
            }
        })
        .collect()
}

fn dex_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("fetched_at_utc", DataType::Utf8, false),
        Field::new("chain_id", DataType::Utf8, false),
        Field::new("dex_id", DataType::Utf8, false),
        Field::new("labels", DataType::Utf8, false),
        Field::new("pair_address", DataType::Utf8, false),
        Field::new("base_address", DataType::Utf8, false),
        Field::new("base_symbol", DataType::Utf8, false),
        Field::new("base_name", DataType::Utf8, false),
        Field::new("quote_address", DataType::Utf8, false),
        Field::new("quote_symbol", DataType::Utf8, false),
        Field::new("quote_name", DataType::Utf8, false),
        Field::new("price_native", DataType::Utf8, false),
        Field::new("price_usd", DataType::Utf8, false),
        Field::new("m5_buys", DataType::UInt64, true),
        Field::new("m5_sells", DataType::UInt64, true),
        Field::new("h1_buys", DataType::UInt64, true),
        Field::new("h1_sells", DataType::UInt64, true),
        Field::new("h6_buys", DataType::UInt64, true),
        Field::new("h6_sells", DataType::UInt64, true),
        Field::new("h24_buys", DataType::UInt64, true),
        Field::new("h24_sells", DataType::UInt64, true),
        Field::new("h24_buy_ratio", DataType::Float64, true),
        Field::new("h24_count_imbalance", DataType::Float64, true),
        Field::new("volume_m5_usd", DataType::Float64, true),
        Field::new("volume_h1_usd", DataType::Float64, true),
        Field::new("volume_h6_usd", DataType::Float64, true),
        Field::new("volume_h24_usd", DataType::Float64, true),
        Field::new("price_change_m5_pct", DataType::Float64, true),
        Field::new("price_change_h1_pct", DataType::Float64, true),
        Field::new("price_change_h6_pct", DataType::Float64, true),
        Field::new("price_change_h24_pct", DataType::Float64, true),
        Field::new("liquidity_usd", DataType::Float64, true),
        Field::new("liquidity_base", DataType::Float64, true),
        Field::new("liquidity_quote", DataType::Float64, true),
        Field::new("volume_h24_to_liquidity", DataType::Float64, true),
        Field::new("fdv", DataType::Float64, true),
        Field::new("market_cap", DataType::Float64, true),
        Field::new("pair_created_at_ms", DataType::Int64, true),
        Field::new("pair_created_at_utc", DataType::Utf8, false),
        Field::new("url", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn rows_to_batch(schema: SchemaRef, rows: &[DexSnapshotRow], dt: &str) -> Result<RecordBatch> {
    let dt_values = vec![dt.to_string(); rows.len()];
    Ok(RecordBatch::try_new(
        schema,
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
                    .map(|row| row.base_name.clone())
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
                    .map(|row| row.quote_name.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.price_native.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.price_usd.clone())
                    .collect::<Vec<_>>(),
            ),
            opt_u64_array(&rows.iter().map(|row| row.m5_buys).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.m5_sells).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.h1_buys).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.h1_sells).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.h6_buys).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.h6_sells).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.h24_buys).collect::<Vec<_>>()),
            opt_u64_array(&rows.iter().map(|row| row.h24_sells).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.h24_buy_ratio).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.h24_count_imbalance)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.volume_m5_usd).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.volume_h1_usd).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.volume_h6_usd).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.volume_h24_usd)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_change_m5_pct)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_change_h1_pct)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_change_h6_pct)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.price_change_h24_pct)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.liquidity_usd).collect::<Vec<_>>()),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.liquidity_base)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.liquidity_quote)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(
                &rows
                    .iter()
                    .map(|row| row.volume_h24_to_liquidity)
                    .collect::<Vec<_>>(),
            ),
            opt_f64_array(&rows.iter().map(|row| row.fdv).collect::<Vec<_>>()),
            opt_f64_array(&rows.iter().map(|row| row.market_cap).collect::<Vec<_>>()),
            opt_i64_array(
                &rows
                    .iter()
                    .map(|row| row.pair_created_at_ms)
                    .collect::<Vec<_>>(),
            ),
            string_array(
                &rows
                    .iter()
                    .map(|row| row.pair_created_at_utc.clone())
                    .collect::<Vec<_>>(),
            ),
            string_array(&rows.iter().map(|row| row.url.clone()).collect::<Vec<_>>()),
            string_array(&dt_values),
        ],
    )?)
}

fn write_csv(path: &PathBuf, pairs: &[Pair], fetched_at: DateTime<Utc>) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }

    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create {}", path.display()))?;

    writer.write_record([
        "fetched_at_utc",
        "chain_id",
        "dex_id",
        "labels",
        "pair_address",
        "base_address",
        "base_symbol",
        "base_name",
        "quote_address",
        "quote_symbol",
        "quote_name",
        "price_native",
        "price_usd",
        "m5_buys",
        "m5_sells",
        "h1_buys",
        "h1_sells",
        "h6_buys",
        "h6_sells",
        "h24_buys",
        "h24_sells",
        "h24_buy_ratio",
        "h24_count_imbalance",
        "volume_m5_usd",
        "volume_h1_usd",
        "volume_h6_usd",
        "volume_h24_usd",
        "price_change_m5_pct",
        "price_change_h1_pct",
        "price_change_h6_pct",
        "price_change_h24_pct",
        "liquidity_usd",
        "liquidity_base",
        "liquidity_quote",
        "volume_h24_to_liquidity",
        "fdv",
        "market_cap",
        "pair_created_at_ms",
        "pair_created_at_utc",
        "url",
    ])?;

    let fetched_at = fetched_at.to_rfc3339_opts(SecondsFormat::Secs, true);
    for pair in pairs {
        let h24_buys = txns(pair, |w| w.h24.as_ref().and_then(|t| t.buys));
        let h24_sells = txns(pair, |w| w.h24.as_ref().and_then(|t| t.sells));
        let h24_total = h24_buys.unwrap_or(0) + h24_sells.unwrap_or(0);
        let h24_buy_ratio = if h24_total == 0 {
            None
        } else {
            Some(h24_buys.unwrap_or(0) as f64 / h24_total as f64)
        };
        let h24_count_imbalance = if h24_total == 0 {
            None
        } else {
            Some((h24_buys.unwrap_or(0) as f64 - h24_sells.unwrap_or(0) as f64) / h24_total as f64)
        };
        let volume_h24 = window(pair.volume.as_ref(), |w| w.h24);
        let liquidity_usd = pair.liquidity.as_ref().and_then(|l| l.usd);
        let volume_h24_to_liquidity = match (volume_h24, liquidity_usd) {
            (Some(volume), Some(liquidity)) if liquidity > 0.0 => Some(volume / liquidity),
            _ => None,
        };

        writer.write_record([
            fetched_at.clone(),
            pair.chain_id.clone(),
            pair.dex_id.clone(),
            pair.labels
                .as_ref()
                .map(|v| v.join("|"))
                .unwrap_or_default(),
            pair.pair_address.clone(),
            pair.base_token.address.clone(),
            pair.base_token.symbol.clone(),
            pair.base_token.name.clone(),
            pair.quote_token.address.clone(),
            pair.quote_token.symbol.clone(),
            pair.quote_token.name.clone(),
            pair.price_native.clone().unwrap_or_default(),
            pair.price_usd.clone().unwrap_or_default(),
            fmt_opt_u64(txns(pair, |w| w.m5.as_ref().and_then(|t| t.buys))),
            fmt_opt_u64(txns(pair, |w| w.m5.as_ref().and_then(|t| t.sells))),
            fmt_opt_u64(txns(pair, |w| w.h1.as_ref().and_then(|t| t.buys))),
            fmt_opt_u64(txns(pair, |w| w.h1.as_ref().and_then(|t| t.sells))),
            fmt_opt_u64(txns(pair, |w| w.h6.as_ref().and_then(|t| t.buys))),
            fmt_opt_u64(txns(pair, |w| w.h6.as_ref().and_then(|t| t.sells))),
            fmt_opt_u64(h24_buys),
            fmt_opt_u64(h24_sells),
            fmt_opt_f64(h24_buy_ratio),
            fmt_opt_f64(h24_count_imbalance),
            fmt_opt_f64(window(pair.volume.as_ref(), |w| w.m5)),
            fmt_opt_f64(window(pair.volume.as_ref(), |w| w.h1)),
            fmt_opt_f64(window(pair.volume.as_ref(), |w| w.h6)),
            fmt_opt_f64(volume_h24),
            fmt_opt_f64(window(pair.price_change.as_ref(), |w| w.m5)),
            fmt_opt_f64(window(pair.price_change.as_ref(), |w| w.h1)),
            fmt_opt_f64(window(pair.price_change.as_ref(), |w| w.h6)),
            fmt_opt_f64(window(pair.price_change.as_ref(), |w| w.h24)),
            fmt_opt_f64(liquidity_usd),
            fmt_opt_f64(pair.liquidity.as_ref().and_then(|l| l.base)),
            fmt_opt_f64(pair.liquidity.as_ref().and_then(|l| l.quote)),
            fmt_opt_f64(volume_h24_to_liquidity),
            fmt_opt_f64(pair.fdv),
            fmt_opt_f64(pair.market_cap),
            pair.pair_created_at
                .map(|value| value.to_string())
                .unwrap_or_default(),
            pair.pair_created_at
                .and_then(DateTime::<Utc>::from_timestamp_millis)
                .map(|dt| dt.to_rfc3339_opts(SecondsFormat::Secs, true))
                .unwrap_or_default(),
            pair.url.clone(),
        ])?;
    }

    writer.flush()?;
    Ok(())
}

fn txns(pair: &Pair, get: impl FnOnce(&Windowed<Txns>) -> Option<u64>) -> Option<u64> {
    pair.txns.as_ref().and_then(get)
}

fn window<T: Copy>(
    windowed: Option<&Windowed<T>>,
    get: impl FnOnce(&Windowed<T>) -> Option<T>,
) -> Option<T> {
    windowed.and_then(get)
}

fn fmt_opt_u64(value: Option<u64>) -> String {
    value.map(|value| value.to_string()).unwrap_or_default()
}

fn fmt_opt_f64(value: Option<f64>) -> String {
    value
        .map(|value| format!("{value:.12}"))
        .unwrap_or_default()
}

fn default_output_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir.parent().unwrap_or(&manifest_dir);
    repo_root.join("date").join("chog_dex_pairs_snapshot.csv")
}

fn print_summary(path: &PathBuf, pairs: &[Pair]) {
    let total_liquidity: f64 = pairs
        .iter()
        .filter_map(|pair| pair.liquidity.as_ref().and_then(|l| l.usd))
        .sum();
    let total_volume_h24: f64 = pairs
        .iter()
        .filter_map(|pair| pair.volume.as_ref().and_then(|v| v.h24))
        .sum();
    let h24_buys: u64 = pairs
        .iter()
        .filter_map(|pair| txns(pair, |w| w.h24.as_ref().and_then(|t| t.buys)))
        .sum();
    let h24_sells: u64 = pairs
        .iter()
        .filter_map(|pair| txns(pair, |w| w.h24.as_ref().and_then(|t| t.sells)))
        .sum();

    println!("pairs written: {}", pairs.len());
    println!("total liquidity usd: {total_liquidity:.2}");
    println!("total h24 volume usd: {total_volume_h24:.2}");
    println!("h24 buys/sells: {h24_buys}/{h24_sells}");
    println!("csv: {}", path.display());
}

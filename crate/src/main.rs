use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, anyhow, bail};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chog_prices::{
    CHECKPOINT_VERSION, Checkpoint,
    chog_v1::{
        ChogCollectionRunRecord, OutputFormat, PartWrite, PartWriteStatus,
        checkpoint_path as parquet_checkpoint_path, custom_part_path, default_data_root_path,
        dt_from_utc_string, f64_array, i64_array, part_paths_to_string, string_array,
        write_collection_run_parquet, write_parquet_part, write_schema_metadata,
    },
    save_checkpoint, utc_now_string,
};
use chrono::{DateTime, SecondsFormat, Utc};
use clap::Parser;
use reqwest::blocking::Client;
use serde::Deserialize;
use url::Url;

const DEFAULT_COIN: &str = "monad:0x350035555e10d9afaf1566aaebfced5ba6c27777";
const DEFAULT_BASE_URL: &str = "https://coins.llama.fi";
const DEFAULT_PERIOD: &str = "1h";
const DEFAULT_SEARCH_WIDTH: &str = "6h";
const DEFAULT_HOURS: u32 = 7 * 24;
const DEFAULT_LOOKBACK_PADDING_HOURS: u32 = 24;
const HOUR_SECONDS: i64 = 60 * 60;
const COLLECTOR: &str = "chog_prices";
const CHAIN: &str = "monad";
const DATASET: &str = "prices_hourly";

#[derive(Debug, Parser)]
#[command(
    name = "chog_prices",
    about = "Fetch recent hourly CHOG prices on Monad from DeFiLlama."
)]
struct Args {
    /// DeFiLlama coin id. Default is CHOG on Monad.
    #[arg(long, default_value = DEFAULT_COIN)]
    coin: String,

    /// Number of recent hours to fetch. 168 means 7 * 24 hourly points.
    #[arg(long, default_value_t = DEFAULT_HOURS)]
    hours: u32,

    /// DeFiLlama chart period.
    #[arg(long, default_value = DEFAULT_PERIOD)]
    period: String,

    /// Price lookup window around each hourly timestamp.
    #[arg(long, default_value = DEFAULT_SEARCH_WIDTH)]
    search_width: String,

    /// Optional fixed end timestamp for reproducible runs.
    #[arg(long)]
    end_timestamp: Option<i64>,

    /// CSV output path. Defaults to ../date/chog_prices_7d_1h.csv from this crate.
    #[arg(long)]
    output: Option<PathBuf>,

    /// Output format. CSV preserves the legacy path; Parquet writes CHOG v1 hourly prices.
    #[arg(long, value_enum, default_value_t = OutputFormat::Csv)]
    format: OutputFormat,

    /// CHOG v1 data root used when --format parquet.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Resolve the time window and output paths without fetching or writing rows.
    #[arg(long)]
    dry_run: bool,

    /// DeFiLlama coins API base URL.
    #[arg(long, default_value = DEFAULT_BASE_URL)]
    base_url: String,
}

#[derive(Debug, Deserialize)]
struct ChartResponse {
    coins: HashMap<String, CoinChart>,
}

#[derive(Debug, Deserialize)]
struct CoinChart {
    symbol: Option<String>,
    confidence: Option<f64>,
    decimals: Option<u32>,
    prices: Vec<PricePoint>,
}

#[derive(Debug, Deserialize)]
struct PricePoint {
    timestamp: i64,
    price: f64,
}

#[derive(Debug, Clone)]
struct PriceRow {
    hour_timestamp: i64,
    hour_utc: String,
    symbol: String,
    price_usd: f64,
    confidence: Option<f64>,
    source_timestamp: i64,
    source_datetime_utc: String,
    source_offset_seconds: i64,
    fill_method: &'static str,
}

fn main() -> Result<()> {
    let args = Args::parse();
    validate_args(&args)?;

    let query_end_timestamp = args.end_timestamp.unwrap_or_else(|| Utc::now().timestamp());
    let end_hour_timestamp = last_completed_hour(query_end_timestamp)?;
    let start_hour_timestamp = end_hour_timestamp
        .checked_sub((i64::from(args.hours) - 1) * HOUR_SECONDS)
        .ok_or_else(|| anyhow!("invalid hours value: {}", args.hours))?;

    if args.dry_run {
        println!("collector: {COLLECTOR}");
        println!("dataset: {DATASET}");
        println!("hour window: {start_hour_timestamp}..{end_hour_timestamp}");
        if args.format == OutputFormat::Parquet {
            let data_root = args
                .data_root
                .clone()
                .unwrap_or_else(default_data_root_path);
            println!("data root: {}", data_root.display());
        }
        return Ok(());
    }

    let fetch_hours = args
        .hours
        .checked_add(DEFAULT_LOOKBACK_PADDING_HOURS)
        .ok_or_else(|| anyhow!("invalid hours value: {}", args.hours))?;

    let url = build_chart_url(&args, fetch_hours, end_hour_timestamp + HOUR_SECONDS - 1)?;
    let response = fetch_chart(&url)?;
    let chart = pick_chart(response, &args.coin)?;
    let raw_points = chart.prices.len();

    let rows = build_hourly_rows(chart, start_hour_timestamp, args.hours)?;

    match args.format {
        OutputFormat::Csv => {
            let output = args.output.unwrap_or_else(default_output_path);
            write_csv(&output, &rows)?;
            print_summary(
                &output,
                &rows,
                raw_points,
                start_hour_timestamp,
                end_hour_timestamp,
            );
        }
        OutputFormat::Parquet => {
            let data_root = args
                .data_root
                .clone()
                .unwrap_or_else(default_data_root_path);
            let parts = write_price_parquet(
                &data_root,
                &args.coin,
                &rows,
                start_hour_timestamp,
                end_hour_timestamp,
            )?;
            println!("hourly rows written: {}", rows.len());
            println!("parquet parts: {}", parts.len());
            println!("data root: {}", data_root.display());
        }
    }

    Ok(())
}

fn validate_args(args: &Args) -> Result<()> {
    if args.hours == 0 {
        bail!("--hours must be greater than 0");
    }
    if args.period != "1h" {
        bail!("this program is scoped to hourly prices; use --period 1h");
    }
    Ok(())
}

fn build_chart_url(args: &Args, fetch_hours: u32, end_timestamp: i64) -> Result<Url> {
    let base = args.base_url.trim_end_matches('/');
    let mut url = Url::parse(&format!("{base}/chart/{}", args.coin))
        .with_context(|| format!("invalid API URL for base {}", args.base_url))?;

    url.query_pairs_mut()
        .append_pair("end", &end_timestamp.to_string())
        .append_pair("span", &fetch_hours.to_string())
        .append_pair("period", &args.period)
        .append_pair("searchWidth", &args.search_width);

    Ok(url)
}

fn last_completed_hour(timestamp: i64) -> Result<i64> {
    let current_hour = timestamp
        .checked_sub(timestamp.rem_euclid(HOUR_SECONDS))
        .ok_or_else(|| anyhow!("invalid timestamp {timestamp}"))?;

    current_hour
        .checked_sub(HOUR_SECONDS)
        .ok_or_else(|| anyhow!("timestamp is too early: {timestamp}"))
}

fn fetch_chart(url: &Url) -> Result<ChartResponse> {
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-chog-prices/0.1")
        .build()
        .context("failed to build HTTP client")?;

    let response = client
        .get(url.clone())
        .header("accept", "application/json")
        .send()
        .with_context(|| format!("failed to request {url}"))?;

    let status = response.status();
    let body = response.text().context("failed to read API response")?;

    if !status.is_success() {
        bail!("API request failed with status {status}: {body}");
    }

    serde_json::from_str(&body).with_context(|| format!("failed to parse API response: {body}"))
}

fn pick_chart(mut response: ChartResponse, coin: &str) -> Result<CoinChart> {
    if let Some(chart) = response.coins.remove(coin) {
        return Ok(chart);
    }

    if response.coins.len() == 1 {
        return response
            .coins
            .into_values()
            .next()
            .ok_or_else(|| anyhow!("empty API response"));
    }

    let available = response
        .coins
        .keys()
        .cloned()
        .collect::<Vec<_>>()
        .join(", ");
    bail!("coin {coin} not found in API response; available coins: {available}");
}

fn build_hourly_rows(
    chart: CoinChart,
    start_hour_timestamp: i64,
    hours: u32,
) -> Result<Vec<PriceRow>> {
    if chart.prices.is_empty() {
        bail!("API response did not include price points");
    }

    let symbol = chart.symbol.unwrap_or_else(|| "CHOG".to_string());
    let _decimals = chart.decimals;
    let confidence = chart.confidence;
    let mut prices = chart.prices;
    prices.sort_by_key(|point| point.timestamp);

    let mut rows = Vec::with_capacity(hours as usize);
    let mut raw_index = 0usize;
    let mut last_observed_index = None;

    for offset in 0..hours {
        let hour_timestamp = start_hour_timestamp + i64::from(offset) * HOUR_SECONDS;
        let next_hour_timestamp = hour_timestamp + HOUR_SECONDS;
        let mut bucket_index = None;

        while raw_index < prices.len() && prices[raw_index].timestamp < next_hour_timestamp {
            if prices[raw_index].timestamp >= hour_timestamp {
                bucket_index = Some(raw_index);
            } else {
                last_observed_index = Some(raw_index);
            }
            raw_index += 1;
        }

        let (source_index, fill_method) = if let Some(index) = bucket_index {
            last_observed_index = Some(index);
            (index, "observed")
        } else if let Some(index) = last_observed_index {
            (index, "forward_fill")
        } else if raw_index < prices.len() {
            (raw_index, "back_fill_initial")
        } else {
            bail!("no source price available for hour {}", hour_timestamp);
        };

        let source = &prices[source_index];
        rows.push(PriceRow {
            hour_timestamp,
            hour_utc: format_timestamp(hour_timestamp)?,
            symbol: symbol.clone(),
            price_usd: source.price,
            confidence,
            source_timestamp: source.timestamp,
            source_datetime_utc: format_timestamp(source.timestamp)?,
            source_offset_seconds: source.timestamp - hour_timestamp,
            fill_method,
        });
    }

    Ok(rows)
}

fn format_timestamp(timestamp: i64) -> Result<String> {
    let datetime = DateTime::<Utc>::from_timestamp(timestamp, 0)
        .ok_or_else(|| anyhow!("invalid timestamp {}", timestamp))?;

    Ok(datetime.to_rfc3339_opts(SecondsFormat::Secs, true))
}

fn write_csv(path: &PathBuf, rows: &[PriceRow]) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("failed to create output directory {}", parent.display()))?;
    }

    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create CSV {}", path.display()))?;

    writer.write_record([
        "hour_timestamp",
        "hour_utc",
        "symbol",
        "price_usd",
        "confidence",
        "source_timestamp",
        "source_datetime_utc",
        "source_offset_seconds",
        "fill_method",
    ])?;

    for row in rows {
        writer.write_record([
            row.hour_timestamp.to_string(),
            row.hour_utc.clone(),
            row.symbol.clone(),
            format!("{:.18}", row.price_usd),
            row.confidence
                .map(|value| value.to_string())
                .unwrap_or_default(),
            row.source_timestamp.to_string(),
            row.source_datetime_utc.clone(),
            row.source_offset_seconds.to_string(),
            row.fill_method.to_string(),
        ])?;
    }

    writer.flush()?;
    Ok(())
}

fn write_price_parquet(
    data_root: &std::path::Path,
    coin: &str,
    rows: &[PriceRow],
    start_hour_timestamp: i64,
    end_hour_timestamp: i64,
) -> Result<Vec<PartWrite>> {
    let schema = price_schema();
    write_schema_metadata(data_root, DATASET, schema.as_ref(), &["dt"])?;

    let mut by_dt = std::collections::BTreeMap::<String, Vec<PriceRow>>::new();
    for row in rows {
        by_dt
            .entry(dt_from_utc_string(&row.hour_utc))
            .or_default()
            .push(row.clone());
    }

    let mut parts = Vec::new();
    for (dt, rows) in by_dt {
        let dt_values = vec![dt.clone(); rows.len()];
        let batch = RecordBatch::try_new(
            schema.clone(),
            vec![
                i64_array(
                    &rows
                        .iter()
                        .map(|row| row.hour_timestamp)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.hour_utc.clone())
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.symbol.clone())
                        .collect::<Vec<_>>(),
                ),
                f64_array(&rows.iter().map(|row| row.price_usd).collect::<Vec<_>>()),
                chog_prices::chog_v1::opt_f64_array(
                    &rows.iter().map(|row| row.confidence).collect::<Vec<_>>(),
                ),
                i64_array(
                    &rows
                        .iter()
                        .map(|row| row.source_timestamp)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.source_datetime_utc.clone())
                        .collect::<Vec<_>>(),
                ),
                i64_array(
                    &rows
                        .iter()
                        .map(|row| row.source_offset_seconds)
                        .collect::<Vec<_>>(),
                ),
                string_array(
                    &rows
                        .iter()
                        .map(|row| row.fill_method.to_string())
                        .collect::<Vec<_>>(),
                ),
                string_array(&dt_values),
            ],
        )?;
        let stem = format!("{COLLECTOR}_{start_hour_timestamp}_{end_hour_timestamp}");
        parts.push(write_parquet_part(
            &custom_part_path(data_root, DATASET, &dt, &stem),
            schema.clone(),
            batch,
        )?);
    }

    let rows_written = parts
        .iter()
        .filter(|part| part.status == PartWriteStatus::Written)
        .map(|part| part.rows as u64)
        .sum::<u64>();
    let started_at = utc_now_string();
    let finished_at = utc_now_string();
    let checkpoint = Checkpoint {
        version: CHECKPOINT_VERSION,
        collector: COLLECTOR.to_string(),
        chain: CHAIN.to_string(),
        address: coin.to_string(),
        topic0: String::new(),
        from_block: 0,
        to_block: 0,
        last_completed_block: 0,
        rows_written,
        output: part_paths_to_string(&parts),
        updated_at_utc: finished_at.clone(),
    };
    save_checkpoint(&parquet_checkpoint_path(data_root, COLLECTOR), &checkpoint)?;
    write_collection_run_parquet(
        data_root,
        &ChogCollectionRunRecord {
            collector: COLLECTOR.to_string(),
            mode: "collector".to_string(),
            dataset: DATASET.to_string(),
            chain: CHAIN.to_string(),
            address: coin.to_string(),
            topic0: String::new(),
            from_block: None,
            to_block: None,
            time_window_start_utc: format_timestamp(start_hour_timestamp)?,
            time_window_end_utc: format_timestamp(end_hour_timestamp)?,
            output_parts: part_paths_to_string(&parts),
            rows_written,
            chunks_completed: parts.len() as u64,
            status: "completed".to_string(),
            error: String::new(),
            started_at_utc: started_at,
            finished_at_utc: finished_at,
        },
    )?;

    Ok(parts)
}

fn price_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("hour_timestamp", DataType::Int64, false),
        Field::new("hour_utc", DataType::Utf8, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("price_usd", DataType::Float64, false),
        Field::new("confidence", DataType::Float64, true),
        Field::new("source_timestamp", DataType::Int64, false),
        Field::new("source_datetime_utc", DataType::Utf8, false),
        Field::new("source_offset_seconds", DataType::Int64, false),
        Field::new("fill_method", DataType::Utf8, false),
        Field::new("dt", DataType::Utf8, false),
    ]))
}

fn default_output_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir.parent().unwrap_or(&manifest_dir);
    repo_root.join("date").join("chog_prices_7d_1h.csv")
}

fn print_summary(
    path: &PathBuf,
    rows: &[PriceRow],
    raw_points: usize,
    start_timestamp: i64,
    end_timestamp: i64,
) {
    let start = format_timestamp(start_timestamp).unwrap_or_else(|_| start_timestamp.to_string());
    let end = format_timestamp(end_timestamp).unwrap_or_else(|_| end_timestamp.to_string());
    let observed = rows
        .iter()
        .filter(|row| row.fill_method == "observed")
        .count();
    let filled = rows.len().saturating_sub(observed);

    println!("hourly window: {start} to {end}");
    println!("raw API points: {raw_points}");
    println!("rows written: {}", rows.len());
    println!("observed rows: {observed}");
    println!("filled rows: {filled}");
    println!("csv: {}", path.display());

    if let Some(first) = rows.first() {
        println!(
            "first: {}, price_usd={:.10}",
            first.hour_utc, first.price_usd
        );
    }

    if let Some(last) = rows.last() {
        println!(
            "latest: {}, price_usd={:.10}",
            last.hour_utc, last.price_usd
        );
    }
}

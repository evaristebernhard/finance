use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use flate2::Compression;
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use serde::{Deserialize, Serialize};

use crate::catalog::date_range;

const RAW_ROOT: &str = "data/ccusdt/v1/external";
const CANONICAL_ROOT: &str = "data/canonical/cex/bullish";

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CanonicalBuildResult {
    pub dataset: String,
    pub symbol: String,
    pub dates: Vec<CanonicalDateResult>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CanonicalDateResult {
    pub date: String,
    pub output_path: String,
    pub rows: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CanonicalValidationResult {
    pub symbol: String,
    pub start_date: String,
    pub end_date: String,
    pub datasets: Vec<CanonicalDatasetValidation>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CanonicalDatasetValidation {
    pub dataset: String,
    pub date: String,
    pub path: String,
    pub exists: bool,
    pub rows: u64,
    pub status: String,
}

pub fn build_canonical_dataset(
    repo_root: &Path,
    symbol: &str,
    dataset: &str,
    from: &str,
    to: &str,
) -> Result<CanonicalBuildResult> {
    let mut dates = Vec::new();
    for date in date_range(from, to)? {
        let result = match dataset {
            "quote_frame_v1" => build_quote_frame(repo_root, symbol, &date)?,
            "trade_event_v1" => build_trade_event(repo_root, symbol, &date)?,
            "l2_level_update_v1" => build_l2_update(repo_root, symbol, &date)?,
            other => anyhow::bail!("unsupported canonical dataset: {other}"),
        };
        dates.push(result);
    }
    Ok(CanonicalBuildResult {
        dataset: dataset.to_string(),
        symbol: symbol.to_string(),
        dates,
    })
}

pub fn validate_canonical(
    repo_root: &Path,
    symbol: &str,
    from: &str,
    to: &str,
) -> Result<CanonicalValidationResult> {
    let mut datasets = Vec::new();
    for date in date_range(from, to)? {
        for dataset in ["quote_frame_v1", "trade_event_v1", "l2_level_update_v1"] {
            datasets.push(validate_one(repo_root, symbol, dataset, &date)?);
        }
    }
    Ok(CanonicalValidationResult {
        symbol: symbol.to_string(),
        start_date: from.to_string(),
        end_date: to.to_string(),
        datasets,
    })
}

pub fn canonical_quote_path(repo_root: &Path, symbol: &str, date: &str) -> PathBuf {
    canonical_path(repo_root, symbol, "quote_frame_v1", date)
}

fn build_quote_frame(repo_root: &Path, symbol: &str, date: &str) -> Result<CanonicalDateResult> {
    let input = raw_path(repo_root, "bullish_book_ticker", symbol, date);
    let output = canonical_path(repo_root, symbol, "quote_frame_v1", date);
    let mut reader = csv_reader(&input)?;
    let headers = reader.headers()?.clone();
    let idx = QuoteIdx::new(&headers)?;
    let mut writer = csv_gz_writer(&output)?;
    writer.write_record([
        "seq",
        "exchange_ts_us",
        "local_ts_us",
        "bid_px",
        "bid_qty",
        "ask_px",
        "ask_qty",
        "mid_px",
        "spread_bps",
    ])?;
    let mut rows = 0u64;
    for row in reader.records() {
        let row = row?;
        let bid_px = parse_f64(&row, idx.bid_px, "bid_price")?;
        let ask_px = parse_f64(&row, idx.ask_px, "ask_price")?;
        anyhow::ensure!(
            bid_px > 0.0 && ask_px > 0.0,
            "non-positive quote at {date}:{rows}"
        );
        anyhow::ensure!(bid_px <= ask_px, "crossed quote at {date}:{rows}");
        let bid_qty = parse_f64(&row, idx.bid_qty, "bid_amount")?;
        let ask_qty = parse_f64(&row, idx.ask_qty, "ask_amount")?;
        let mid = (bid_px + ask_px) * 0.5;
        let spread_bps = (ask_px - bid_px) / mid * 10_000.0;
        writer.write_record([
            rows.to_string(),
            field(&row, idx.exchange_ts).to_string(),
            field(&row, idx.local_ts).to_string(),
            bid_px.to_string(),
            bid_qty.to_string(),
            ask_px.to_string(),
            ask_qty.to_string(),
            mid.to_string(),
            spread_bps.to_string(),
        ])?;
        rows += 1;
    }
    writer.flush()?;
    Ok(result(date, output, rows))
}

fn build_trade_event(repo_root: &Path, symbol: &str, date: &str) -> Result<CanonicalDateResult> {
    let input = raw_path(repo_root, "bullish_trades", symbol, date);
    let output = canonical_path(repo_root, symbol, "trade_event_v1", date);
    let mut reader = csv_reader(&input)?;
    let headers = reader.headers()?.clone();
    let idx = TradeIdx::new(&headers)?;
    let mut writer = csv_gz_writer(&output)?;
    writer.write_record([
        "seq",
        "trade_id",
        "exchange_ts_us",
        "local_ts_us",
        "side",
        "price",
        "qty",
        "notional_quote",
    ])?;
    let mut rows = 0u64;
    for row in reader.records() {
        let row = row?;
        let price = parse_f64(&row, idx.price, "price")?;
        let qty = parse_f64(&row, idx.qty, "amount")?;
        let side = normalize_side(field(&row, idx.side))?;
        writer.write_record([
            rows.to_string(),
            field(&row, idx.trade_id).to_string(),
            field(&row, idx.exchange_ts).to_string(),
            field(&row, idx.local_ts).to_string(),
            side.to_string(),
            price.to_string(),
            qty.to_string(),
            (price * qty).to_string(),
        ])?;
        rows += 1;
    }
    writer.flush()?;
    Ok(result(date, output, rows))
}

fn build_l2_update(repo_root: &Path, symbol: &str, date: &str) -> Result<CanonicalDateResult> {
    let input = raw_path(repo_root, "bullish_incremental_book_L2", symbol, date);
    let output = canonical_path(repo_root, symbol, "l2_level_update_v1", date);
    let mut reader = csv_reader(&input)?;
    let headers = reader.headers()?.clone();
    let idx = L2Idx::new(&headers)?;
    let mut writer = csv_gz_writer(&output)?;
    writer.write_record([
        "seq",
        "exchange_ts_us",
        "local_ts_us",
        "is_snapshot",
        "side",
        "price",
        "qty",
    ])?;
    let mut rows = 0u64;
    for row in reader.records() {
        let row = row?;
        let price = parse_f64(&row, idx.price, "price")?;
        let qty = parse_f64(&row, idx.qty, "amount")?;
        let side = normalize_side(field(&row, idx.side))?;
        writer.write_record([
            rows.to_string(),
            field(&row, idx.exchange_ts).to_string(),
            field(&row, idx.local_ts).to_string(),
            field(&row, idx.is_snapshot).to_ascii_lowercase(),
            side.to_string(),
            price.to_string(),
            qty.to_string(),
        ])?;
        rows += 1;
    }
    writer.flush()?;
    Ok(result(date, output, rows))
}

fn validate_one(
    repo_root: &Path,
    symbol: &str,
    dataset: &str,
    date: &str,
) -> Result<CanonicalDatasetValidation> {
    let path = canonical_path(repo_root, symbol, dataset, date);
    if !path.exists() {
        return Ok(CanonicalDatasetValidation {
            dataset: dataset.to_string(),
            date: date.to_string(),
            path: relative_to_repo(repo_root, &path),
            exists: false,
            rows: 0,
            status: "missing".to_string(),
        });
    }
    let mut reader = csv_reader(&path)?;
    let headers = reader.headers()?.clone();
    let seq_idx = header_idx(&headers, "seq")?;
    let mut last_seq = None;
    let mut rows = 0u64;
    let quote_idxs = if dataset == "quote_frame_v1" {
        Some((
            header_idx(&headers, "bid_px")?,
            header_idx(&headers, "ask_px")?,
        ))
    } else {
        None
    };
    for row in reader.records() {
        let row = row?;
        let seq = field(&row, seq_idx).parse::<u64>()?;
        if let Some(last) = last_seq {
            anyhow::ensure!(
                seq == last + 1,
                "non-monotonic seq in {} at row {}",
                path.display(),
                rows + 2
            );
        }
        if let Some((bid_idx, ask_idx)) = quote_idxs {
            let bid = parse_f64(&row, bid_idx, "bid_px")?;
            let ask = parse_f64(&row, ask_idx, "ask_px")?;
            anyhow::ensure!(
                bid <= ask,
                "crossed canonical quote in {} at row {}",
                path.display(),
                rows + 2
            );
        }
        last_seq = Some(seq);
        rows += 1;
    }
    Ok(CanonicalDatasetValidation {
        dataset: dataset.to_string(),
        date: date.to_string(),
        path: relative_to_repo(repo_root, &path),
        exists: true,
        rows,
        status: "ok".to_string(),
    })
}

fn raw_path(repo_root: &Path, data_dir: &str, symbol: &str, date: &str) -> PathBuf {
    repo_root
        .join(RAW_ROOT)
        .join(data_dir)
        .join(format!("symbol={symbol}"))
        .join(format!("dt={date}"))
        .join(format!("{symbol}.csv.gz"))
}

fn canonical_path(repo_root: &Path, symbol: &str, dataset: &str, date: &str) -> PathBuf {
    repo_root
        .join(CANONICAL_ROOT)
        .join(symbol)
        .join(dataset)
        .join(format!("dt={date}"))
        .join("part_000001.csv.gz")
}

fn csv_reader(path: &Path) -> Result<csv::Reader<Box<dyn Read>>> {
    let file = File::open(path).with_context(|| format!("open csv {}", path.display()))?;
    let reader: Box<dyn Read> = if path.extension().and_then(|ext| ext.to_str()) == Some("gz") {
        Box::new(GzDecoder::new(file))
    } else {
        Box::new(file)
    };
    Ok(csv::Reader::from_reader(reader))
}

fn csv_gz_writer(path: &Path) -> Result<csv::Writer<GzEncoder<File>>> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let file = File::create(path).with_context(|| format!("create {}", path.display()))?;
    let encoder = GzEncoder::new(file, Compression::default());
    Ok(csv::Writer::from_writer(encoder))
}

fn result(date: &str, output: PathBuf, rows: u64) -> CanonicalDateResult {
    CanonicalDateResult {
        date: date.to_string(),
        output_path: output.to_string_lossy().replace('\\', "/"),
        rows,
    }
}

fn field(row: &csv::StringRecord, idx: usize) -> &str {
    row.get(idx).unwrap_or("")
}

fn parse_f64(row: &csv::StringRecord, idx: usize, name: &str) -> Result<f64> {
    row.get(idx)
        .context("missing field")?
        .parse::<f64>()
        .with_context(|| format!("parse {name}"))
}

fn normalize_side(side: &str) -> Result<&'static str> {
    match side.trim().to_ascii_lowercase().as_str() {
        "buy" | "bid" => Ok("buy"),
        "sell" | "ask" => Ok("sell"),
        other => anyhow::bail!("unsupported side: {other}"),
    }
}

fn header_idx(headers: &csv::StringRecord, name: &str) -> Result<usize> {
    headers
        .iter()
        .position(|header| header.eq_ignore_ascii_case(name))
        .with_context(|| format!("missing csv header: {name}"))
}

fn relative_to_repo(repo_root: &Path, path: &Path) -> String {
    path.strip_prefix(repo_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

struct QuoteIdx {
    exchange_ts: usize,
    local_ts: usize,
    bid_px: usize,
    bid_qty: usize,
    ask_px: usize,
    ask_qty: usize,
}

impl QuoteIdx {
    fn new(headers: &csv::StringRecord) -> Result<Self> {
        Ok(Self {
            exchange_ts: header_idx(headers, "timestamp")?,
            local_ts: header_idx(headers, "local_timestamp")?,
            bid_px: header_idx(headers, "bid_price")?,
            bid_qty: header_idx(headers, "bid_amount")?,
            ask_px: header_idx(headers, "ask_price")?,
            ask_qty: header_idx(headers, "ask_amount")?,
        })
    }
}

struct TradeIdx {
    exchange_ts: usize,
    local_ts: usize,
    trade_id: usize,
    side: usize,
    price: usize,
    qty: usize,
}

impl TradeIdx {
    fn new(headers: &csv::StringRecord) -> Result<Self> {
        Ok(Self {
            exchange_ts: header_idx(headers, "timestamp")?,
            local_ts: header_idx(headers, "local_timestamp")?,
            trade_id: header_idx(headers, "id")?,
            side: header_idx(headers, "side")?,
            price: header_idx(headers, "price")?,
            qty: header_idx(headers, "amount")?,
        })
    }
}

struct L2Idx {
    exchange_ts: usize,
    local_ts: usize,
    is_snapshot: usize,
    side: usize,
    price: usize,
    qty: usize,
}

impl L2Idx {
    fn new(headers: &csv::StringRecord) -> Result<Self> {
        Ok(Self {
            exchange_ts: header_idx(headers, "timestamp")?,
            local_ts: header_idx(headers, "local_timestamp")?,
            is_snapshot: header_idx(headers, "is_snapshot")?,
            side: header_idx(headers, "side")?,
            price: header_idx(headers, "price")?,
            qty: header_idx(headers, "amount")?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn side_normalization_is_stable() {
        assert_eq!(normalize_side("BUY").unwrap(), "buy");
        assert_eq!(normalize_side("ask").unwrap(), "sell");
        assert!(normalize_side("unknown").is_err());
    }

    #[test]
    fn build_quote_frame_rejects_crossed_quotes() {
        let root = temp_repo("crossed_quote");
        write_raw_gz(
            &raw_path(&root, "bullish_book_ticker", "CCUSDT", "2026-05-18"),
            "exchange,symbol,timestamp,local_timestamp,ask_amount,ask_price,bid_price,bid_amount\nbullish,CCUSDT,1,2,1,0.99,1.00,1\n",
        );
        let err = build_canonical_dataset(
            &root,
            "CCUSDT",
            "quote_frame_v1",
            "2026-05-18",
            "2026-05-18",
        )
        .unwrap_err()
        .to_string();
        assert!(err.contains("crossed quote"));
    }

    #[test]
    fn build_and_validate_quote_and_trade_fixtures() {
        let root = temp_repo("canonical_ok");
        write_raw_gz(
            &raw_path(&root, "bullish_book_ticker", "CCUSDT", "2026-05-18"),
            "exchange,symbol,timestamp,local_timestamp,ask_amount,ask_price,bid_price,bid_amount\nbullish,CCUSDT,1,2,5,1.01,1.00,4\n",
        );
        write_raw_gz(
            &raw_path(&root, "bullish_trades", "CCUSDT", "2026-05-18"),
            "exchange,symbol,timestamp,local_timestamp,id,side,price,amount\nbullish,CCUSDT,3,4,t1,BUY,1.01,7\n",
        );
        build_canonical_dataset(
            &root,
            "CCUSDT",
            "quote_frame_v1",
            "2026-05-18",
            "2026-05-18",
        )
        .unwrap();
        build_canonical_dataset(
            &root,
            "CCUSDT",
            "trade_event_v1",
            "2026-05-18",
            "2026-05-18",
        )
        .unwrap();
        let validation = validate_canonical(&root, "CCUSDT", "2026-05-18", "2026-05-18").unwrap();
        let quote = validation
            .datasets
            .iter()
            .find(|row| row.dataset == "quote_frame_v1")
            .unwrap();
        let trade = validation
            .datasets
            .iter()
            .find(|row| row.dataset == "trade_event_v1")
            .unwrap();
        assert_eq!(quote.status, "ok");
        assert_eq!(quote.rows, 1);
        assert_eq!(trade.status, "ok");
        assert_eq!(trade.rows, 1);
    }

    #[test]
    fn build_l2_fixture_normalizes_book_sides() {
        let root = temp_repo("l2_ok");
        write_raw_gz(
            &raw_path(&root, "bullish_incremental_book_L2", "CCUSDT", "2026-05-18"),
            "exchange,symbol,timestamp,local_timestamp,is_snapshot,side,price,amount\nbullish,CCUSDT,1,2,true,bid,1.00,4\nbullish,CCUSDT,3,4,false,ask,1.01,5\n",
        );
        let result = build_canonical_dataset(
            &root,
            "CCUSDT",
            "l2_level_update_v1",
            "2026-05-18",
            "2026-05-18",
        )
        .unwrap();
        assert_eq!(result.dates[0].rows, 2);

        let validation = validate_one(&root, "CCUSDT", "l2_level_update_v1", "2026-05-18").unwrap();
        assert_eq!(validation.status, "ok");
        assert_eq!(validation.rows, 2);

        let mut reader = csv_reader(&canonical_path(
            &root,
            "CCUSDT",
            "l2_level_update_v1",
            "2026-05-18",
        ))
        .unwrap();
        let headers = reader.headers().unwrap().clone();
        let side_idx = header_idx(&headers, "side").unwrap();
        let sides = reader
            .records()
            .map(|row| row.unwrap().get(side_idx).unwrap().to_string())
            .collect::<Vec<_>>();
        assert_eq!(sides, vec!["buy", "sell"]);
    }

    #[test]
    fn validate_rejects_non_monotonic_seq() {
        let root = temp_repo("bad_seq");
        write_raw_gz(
            &canonical_path(&root, "CCUSDT", "quote_frame_v1", "2026-05-18"),
            "seq,exchange_ts_us,local_ts_us,bid_px,bid_qty,ask_px,ask_qty,mid_px,spread_bps\n0,1,2,1.00,4,1.01,5,1.005,99.5\n2,3,4,1.00,4,1.01,5,1.005,99.5\n",
        );
        let err = validate_one(&root, "CCUSDT", "quote_frame_v1", "2026-05-18")
            .unwrap_err()
            .to_string();
        assert!(err.contains("non-monotonic seq"));
    }

    fn temp_repo(name: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("ccusdt_replay_{name}_{nonce}"));
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn write_raw_gz(path: &Path, content: &str) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        let file = File::create(path).unwrap();
        let mut encoder = GzEncoder::new(file, Compression::default());
        encoder.write_all(content.as_bytes()).unwrap();
        encoder.finish().unwrap();
    }
}

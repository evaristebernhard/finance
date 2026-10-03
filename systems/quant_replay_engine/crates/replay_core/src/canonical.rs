use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use flate2::Compression;
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use serde::{Deserialize, Serialize};

use crate::catalog::date_range;
use crate::types::{L2LevelUpdate, MarketFrame, Side, TradeEvent};

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
    pub quality: DatasetQuality,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct DatasetQuality {
    pub snapshot_rows: u64,
    pub update_rows: u64,
    pub timestamp_regressions: u64,
    pub invalid_rows: u64,
    pub reconstructible: bool,
    pub warnings: Vec<String>,
}

/// Cheap run-start preflight for large compressed L2 files.
///
/// Full canonical validation remains available through `canonical validate`.
/// A replay run only needs to reject obviously unusable input before opening
/// the stream; the report deliberately says that it is sampled so callers do
/// not present it as a full READY guarantee.
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct L2PreflightReport {
    pub path: String,
    pub sampled_rows: usize,
    pub saw_snapshot: bool,
    pub saw_incremental_update: bool,
    pub timestamp_regressions: u64,
    pub invalid_rows: u64,
    pub sampled_only: bool,
    pub status: String,
    pub warnings: Vec<String>,
}

pub fn preflight_canonical_l2(
    repo_root: &Path,
    symbol: &str,
    date: &str,
    sample_rows: usize,
) -> Result<L2PreflightReport> {
    anyhow::ensure!(sample_rows > 0, "sample_rows must be >= 1");
    let path = canonical_l2_path(repo_root, symbol, date);
    let mut report = L2PreflightReport {
        path: path.to_string_lossy().replace('\\', "/"),
        sampled_only: true,
        ..L2PreflightReport::default()
    };
    if !path.exists() {
        report.status = "missing".to_string();
        report.warnings.push("canonical L2 file is missing".to_string());
        return Ok(report);
    }

    let mut reader = csv_reader(&path)?;
    let headers = reader.headers()?.clone();
    let idx = CanonicalL2Idx::new(&headers)?;
    let mut last_exchange_ts = None;
    let mut last_local_ts = None;
    let mut row = csv::StringRecord::new();
    while report.sampled_rows < sample_rows && reader.read_record(&mut row)? {
        let update = parse_canonical_l2(&row, &idx)?;
        report.sampled_rows += 1;
        report.saw_snapshot |= update.is_snapshot;
        report.saw_incremental_update |= !update.is_snapshot;
        if update.price <= 0.0
            || !update.price.is_finite()
            || update.qty < 0.0
            || !update.qty.is_finite()
        {
            report.invalid_rows += 1;
        }
        if last_exchange_ts.is_some_and(|last| update.exchange_ts_us < last)
            || last_local_ts.is_some_and(|last| update.local_ts_us < last)
        {
            report.timestamp_regressions += 1;
        }
        last_exchange_ts = Some(update.exchange_ts_us);
        last_local_ts = Some(update.local_ts_us);
        row.clear();
    }

    if report.sampled_rows == 0 {
        report.status = "empty".to_string();
        report.warnings.push("canonical L2 file is empty".to_string());
    } else if !report.saw_snapshot {
        report.status = "warning_no_snapshot".to_string();
        report.warnings.push("sample contains no snapshot".to_string());
    } else if report.invalid_rows > 0 || report.timestamp_regressions > 0 {
        report.status = "invalid_l2".to_string();
        report.warnings.push("sample contains invalid rows or timestamp regressions".to_string());
    } else {
        report.status = "sampled_ok".to_string();
        report.warnings.push("sampled prefix only; full L2 semantics are not verified".to_string());
    }
    Ok(report)
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

pub fn canonical_trade_path(repo_root: &Path, symbol: &str, date: &str) -> PathBuf {
    canonical_path(repo_root, symbol, "trade_event_v1", date)
}

pub fn canonical_l2_path(repo_root: &Path, symbol: &str, date: &str) -> PathBuf {
    canonical_path(repo_root, symbol, "l2_level_update_v1", date)
}

pub fn load_canonical_trades(
    repo_root: &Path,
    symbol: &str,
    date: &str,
) -> Result<Vec<TradeEvent>> {
    let path = canonical_trade_path(repo_root, symbol, date);
    let mut reader = csv_reader(&path)?;
    let headers = reader.headers()?.clone();
    let idx = CanonicalTradeIdx::new(&headers)?;
    let mut out = Vec::new();
    for row in reader.records() {
        let row = row?;
        out.push(parse_canonical_trade(&row, &idx)?);
    }
    Ok(out)
}

pub fn load_canonical_l2_updates(
    repo_root: &Path,
    symbol: &str,
    date: &str,
    max_rows: Option<usize>,
) -> Result<Vec<L2LevelUpdate>> {
    let path = canonical_l2_path(repo_root, symbol, date);
    let mut reader = csv_reader(&path)?;
    let headers = reader.headers()?.clone();
    let idx = CanonicalL2Idx::new(&headers)?;
    let mut out = Vec::new();
    for row in reader.records() {
        if max_rows.is_some_and(|max| out.len() >= max) {
            break;
        }
        let row = row?;
        out.push(parse_canonical_l2(&row, &idx)?);
    }
    Ok(out)
}

pub fn stream_canonical_quotes(
    repo_root: &Path,
    symbol: &str,
    date: &str,
) -> Result<CanonicalQuoteIter> {
    CanonicalQuoteIter::open(canonical_quote_path(repo_root, symbol, date))
}

pub fn stream_canonical_trades(
    repo_root: &Path,
    symbol: &str,
    date: &str,
) -> Result<CanonicalTradeIter> {
    CanonicalTradeIter::open(canonical_trade_path(repo_root, symbol, date))
}

pub fn stream_canonical_l2_batches(
    repo_root: &Path,
    symbol: &str,
    date: &str,
    max_batch_rows: usize,
    max_rows: Option<usize>,
) -> Result<CanonicalL2BatchIter> {
    CanonicalL2BatchIter::open(
        canonical_l2_path(repo_root, symbol, date),
        max_batch_rows,
        max_rows,
    )
}

pub fn stream_canonical_market(
    repo_root: &Path,
    symbol: &str,
    date: &str,
    include_l2: bool,
    l2_batch_size: usize,
    l2_max_rows: Option<usize>,
) -> Result<CanonicalMarketStream> {
    CanonicalMarketStream::open(
        repo_root,
        symbol,
        date,
        include_l2,
        l2_batch_size,
        l2_max_rows,
    )
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
            quality: DatasetQuality::default(),
        });
    }
    let mut reader = csv_reader(&path)?;
    let headers = reader.headers()?.clone();
    let seq_idx = header_idx(&headers, "seq")?;
    let mut last_seq = None;
    let mut rows = 0u64;
    let mut quality = DatasetQuality {
        reconstructible: dataset != "l2_level_update_v1",
        ..DatasetQuality::default()
    };
    let mut last_exchange_ts = None;
    let mut last_local_ts = None;
    let quote_idxs = if dataset == "quote_frame_v1" {
        Some((
            header_idx(&headers, "bid_px")?,
            header_idx(&headers, "ask_px")?,
        ))
    } else {
        None
    };
    let l2_idx = if dataset == "l2_level_update_v1" {
        Some(CanonicalL2Idx::new(&headers)?)
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
        if let Some(idx) = &l2_idx {
            let update = parse_canonical_l2(&row, idx)
                .with_context(|| format!("invalid L2 row {}", rows + 2))?;
            if update.is_snapshot {
                quality.snapshot_rows += 1;
            } else {
                quality.update_rows += 1;
            }
            if update.price <= 0.0
                || !update.price.is_finite()
                || update.qty < 0.0
                || !update.qty.is_finite()
            {
                quality.invalid_rows += 1;
            }
            if last_exchange_ts.is_some_and(|last| update.exchange_ts_us < last)
                || last_local_ts.is_some_and(|last| update.local_ts_us < last)
            {
                quality.timestamp_regressions += 1;
            }
            last_exchange_ts = Some(update.exchange_ts_us);
            last_local_ts = Some(update.local_ts_us);
        }
        last_seq = Some(seq);
        rows += 1;
    }
    if dataset == "l2_level_update_v1" {
        quality.reconstructible = rows > 0
            && quality.snapshot_rows > 0
            && quality.timestamp_regressions == 0
            && quality.invalid_rows == 0;
        if quality.snapshot_rows == 0 {
            quality.warnings.push("no initial snapshot".to_string());
        }
        if quality.update_rows == 0 && rows > 0 {
            quality.warnings.push(
                "all rows are marked snapshot; verify vendor feed semantics before queue replay"
                    .to_string(),
            );
        }
        if quality.timestamp_regressions > 0 {
            quality.warnings.push("timestamp regression".to_string());
        }
        if quality.invalid_rows > 0 {
            quality
                .warnings
                .push("invalid price or quantity".to_string());
        }
    }
    let status = if dataset == "l2_level_update_v1" && !quality.reconstructible {
        if quality.snapshot_rows == 0 {
            "warning_no_snapshot"
        } else {
            "invalid_l2"
        }
    } else if dataset == "l2_level_update_v1" && !quality.warnings.is_empty() {
        "warning_l2_semantics"
    } else {
        "ok"
    };
    Ok(CanonicalDatasetValidation {
        dataset: dataset.to_string(),
        date: date.to_string(),
        path: relative_to_repo(repo_root, &path),
        exists: true,
        rows,
        status: status.to_string(),
        quality,
    })
}

pub struct CanonicalQuoteIter {
    reader: csv::Reader<Box<dyn Read>>,
    idx: CanonicalQuoteIdx,
}

impl CanonicalQuoteIter {
    fn open(path: PathBuf) -> Result<Self> {
        let mut reader = csv_reader(&path)?;
        let headers = reader.headers()?.clone();
        Ok(Self {
            reader,
            idx: CanonicalQuoteIdx::new(&headers)?,
        })
    }

    fn read_next(&mut self) -> Result<Option<MarketFrame>> {
        let mut row = csv::StringRecord::new();
        if !self.reader.read_record(&mut row)? {
            return Ok(None);
        }
        let seq = parse_u64(&row, self.idx.seq, "seq")?;
        let exchange_ts_us = parse_u64(&row, self.idx.exchange_ts, "exchange_ts_us")?;
        let local_ts_us = parse_u64(&row, self.idx.local_ts, "local_ts_us")?;
        let bid = parse_f64(&row, self.idx.bid_px, "bid_px")?;
        let ask = parse_f64(&row, self.idx.ask_px, "ask_px")?;
        Ok(Some(MarketFrame::new_with_timestamps_and_qty(
            seq,
            exchange_ts_us.to_string(),
            exchange_ts_us,
            local_ts_us,
            bid,
            parse_f64(&row, self.idx.bid_qty, "bid_qty")?,
            ask,
            parse_f64(&row, self.idx.ask_qty, "ask_qty")?,
        )?))
    }
}

impl Iterator for CanonicalQuoteIter {
    type Item = Result<MarketFrame>;

    fn next(&mut self) -> Option<Self::Item> {
        self.read_next().transpose()
    }
}

pub struct CanonicalTradeIter {
    reader: csv::Reader<Box<dyn Read>>,
    idx: CanonicalTradeIdx,
}

impl CanonicalTradeIter {
    fn open(path: PathBuf) -> Result<Self> {
        let mut reader = csv_reader(&path)?;
        let headers = reader.headers()?.clone();
        Ok(Self {
            reader,
            idx: CanonicalTradeIdx::new(&headers)?,
        })
    }

    fn read_next(&mut self) -> Result<Option<TradeEvent>> {
        let mut row = csv::StringRecord::new();
        if !self.reader.read_record(&mut row)? {
            return Ok(None);
        }
        Ok(Some(parse_canonical_trade(&row, &self.idx)?))
    }
}

impl Iterator for CanonicalTradeIter {
    type Item = Result<TradeEvent>;

    fn next(&mut self) -> Option<Self::Item> {
        self.read_next().transpose()
    }
}

pub struct CanonicalL2BatchIter {
    reader: csv::Reader<Box<dyn Read>>,
    idx: CanonicalL2Idx,
    max_batch_rows: usize,
    max_rows: Option<usize>,
    rows_seen: usize,
    buffered: Option<L2LevelUpdate>,
}

impl CanonicalL2BatchIter {
    fn open(path: PathBuf, max_batch_rows: usize, max_rows: Option<usize>) -> Result<Self> {
        anyhow::ensure!(max_batch_rows > 0, "max_batch_rows must be >= 1");
        let mut reader = csv_reader(&path)?;
        let headers = reader.headers()?.clone();
        Ok(Self {
            reader,
            idx: CanonicalL2Idx::new(&headers)?,
            max_batch_rows,
            max_rows,
            rows_seen: 0,
            buffered: None,
        })
    }

    fn read_update(&mut self) -> Result<Option<L2LevelUpdate>> {
        if self.max_rows.is_some_and(|max| self.rows_seen >= max) {
            return Ok(None);
        }
        let mut row = csv::StringRecord::new();
        if !self.reader.read_record(&mut row)? {
            return Ok(None);
        }
        self.rows_seen += 1;
        parse_canonical_l2(&row, &self.idx).map(Some)
    }

    fn read_next_batch(&mut self) -> Result<Option<Vec<L2LevelUpdate>>> {
        let first = if let Some(buffered) = self.buffered.take() {
            buffered
        } else {
            let Some(update) = self.read_update()? else {
                return Ok(None);
            };
            update
        };
        let batch_ts = first.local_ts_us;
        let mut batch = vec![first];
        while batch.len() < self.max_batch_rows {
            let Some(next) = self.read_update()? else {
                break;
            };
            if next.local_ts_us != batch_ts {
                self.buffered = Some(next);
                break;
            }
            batch.push(next);
        }
        // Keep the batch bounded even when a vendor emits a very large
        // snapshot at one timestamp. `L2Book::apply_batch` preserves the
        // snapshot boundary by timestamp, so splitting same-timestamp rows
        // does not change replay semantics and avoids a giant allocation.
        Ok(Some(batch))
    }
}

impl Iterator for CanonicalL2BatchIter {
    type Item = Result<Vec<L2LevelUpdate>>;

    fn next(&mut self) -> Option<Self::Item> {
        self.read_next_batch().transpose()
    }
}

#[derive(Clone, Debug)]
pub enum CanonicalMarketEvent {
    Quote {
        stream_seq: u64,
        frame: MarketFrame,
    },
    Trade {
        stream_seq: u64,
        trade: TradeEvent,
    },
    L2Batch {
        stream_seq: u64,
        local_ts_us: u64,
        updates: Vec<L2LevelUpdate>,
    },
}

impl CanonicalMarketEvent {
    pub fn stream_seq(&self) -> u64 {
        match self {
            Self::Quote { stream_seq, .. }
            | Self::Trade { stream_seq, .. }
            | Self::L2Batch { stream_seq, .. } => *stream_seq,
        }
    }

    pub fn local_ts_us(&self) -> u64 {
        match self {
            Self::Quote { frame, .. } => frame.local_ts_us,
            Self::Trade { trade, .. } => trade.local_ts_us,
            Self::L2Batch { local_ts_us, .. } => *local_ts_us,
        }
    }
}

pub struct CanonicalMarketStream {
    quote_iter: CanonicalQuoteIter,
    trade_iter: CanonicalTradeIter,
    l2_iter: Option<CanonicalL2BatchIter>,
    next_quote: Option<MarketFrame>,
    next_trade: Option<TradeEvent>,
    next_l2_batch: Option<Vec<L2LevelUpdate>>,
    next_stream_seq: u64,
}

impl CanonicalMarketStream {
    fn open(
        repo_root: &Path,
        symbol: &str,
        date: &str,
        include_l2: bool,
        l2_batch_size: usize,
        l2_max_rows: Option<usize>,
    ) -> Result<Self> {
        let mut quote_iter = stream_canonical_quotes(repo_root, symbol, date)?;
        let mut trade_iter = stream_canonical_trades(repo_root, symbol, date)?;
        let mut l2_iter = if include_l2 {
            Some(stream_canonical_l2_batches(
                repo_root,
                symbol,
                date,
                l2_batch_size,
                l2_max_rows,
            )?)
        } else {
            None
        };
        let next_quote = quote_iter.next().transpose()?;
        let next_trade = trade_iter.next().transpose()?;
        let next_l2_batch = match l2_iter.as_mut() {
            Some(iter) => iter.next().transpose()?,
            None => None,
        };
        Ok(Self {
            quote_iter,
            trade_iter,
            l2_iter,
            next_quote,
            next_trade,
            next_l2_batch,
            next_stream_seq: 0,
        })
    }

    fn read_next(&mut self) -> Result<Option<CanonicalMarketEvent>> {
        let quote_key = self
            .next_quote
            .as_ref()
            .map(|quote| (quote.local_ts_us, 0u8));
        let trade_key = self
            .next_trade
            .as_ref()
            .map(|trade| (trade.local_ts_us, 1u8));
        let l2_key = self
            .next_l2_batch
            .as_ref()
            .and_then(|batch| batch.first().map(|update| (update.local_ts_us, 2u8)));
        let choice = [quote_key, trade_key, l2_key]
            .into_iter()
            .enumerate()
            .filter_map(|(idx, key)| key.map(|key| (idx, key)))
            .min_by_key(|(_, key)| *key)
            .map(|(idx, _)| idx);
        let Some(choice) = choice else {
            return Ok(None);
        };
        let stream_seq = self.next_stream_seq;
        self.next_stream_seq += 1;
        match choice {
            0 => {
                let frame = self.next_quote.take().expect("choice checked quote");
                self.next_quote = self.quote_iter.next().transpose()?;
                Ok(Some(CanonicalMarketEvent::Quote { stream_seq, frame }))
            }
            1 => {
                let trade = self.next_trade.take().expect("choice checked trade");
                self.next_trade = self.trade_iter.next().transpose()?;
                Ok(Some(CanonicalMarketEvent::Trade { stream_seq, trade }))
            }
            2 => {
                let updates = self.next_l2_batch.take().expect("choice checked l2");
                let local_ts_us = updates
                    .first()
                    .map(|update| update.local_ts_us)
                    .unwrap_or_default();
                self.next_l2_batch = match self.l2_iter.as_mut() {
                    Some(iter) => iter.next().transpose()?,
                    None => None,
                };
                Ok(Some(CanonicalMarketEvent::L2Batch {
                    stream_seq,
                    local_ts_us,
                    updates,
                }))
            }
            _ => unreachable!("only three market sources"),
        }
    }
}

impl Iterator for CanonicalMarketStream {
    type Item = Result<CanonicalMarketEvent>;

    fn next(&mut self) -> Option<Self::Item> {
        self.read_next().transpose()
    }
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

fn parse_u64(row: &csv::StringRecord, idx: usize, name: &str) -> Result<u64> {
    let raw = row.get(idx).context("missing field")?.trim();
    if let Ok(value) = raw.parse::<u64>() {
        return Ok(value);
    }
    let as_float = raw
        .parse::<f64>()
        .with_context(|| format!("parse {name}"))?;
    anyhow::ensure!(as_float >= 0.0 && as_float.is_finite(), "bad {name}");
    Ok(as_float as u64)
}

fn normalize_side(side: &str) -> Result<&'static str> {
    match side.trim().to_ascii_lowercase().as_str() {
        "buy" | "bid" => Ok("buy"),
        "sell" | "ask" => Ok("sell"),
        other => anyhow::bail!("unsupported side: {other}"),
    }
}

fn parse_side(side: &str) -> Result<Side> {
    match normalize_side(side)? {
        "buy" => Ok(Side::Buy),
        "sell" => Ok(Side::Sell),
        _ => unreachable!("normalize_side only returns buy/sell"),
    }
}

fn parse_canonical_trade(row: &csv::StringRecord, idx: &CanonicalTradeIdx) -> Result<TradeEvent> {
    Ok(TradeEvent {
        seq: parse_u64(row, idx.seq, "seq")?,
        trade_id: field(row, idx.trade_id).to_string(),
        exchange_ts_us: parse_u64(row, idx.exchange_ts, "exchange_ts_us")?,
        local_ts_us: parse_u64(row, idx.local_ts, "local_ts_us")?,
        side: parse_side(field(row, idx.side))?,
        price: parse_f64(row, idx.price, "price")?,
        qty: parse_f64(row, idx.qty, "qty")?,
        notional_quote: parse_f64(row, idx.notional_quote, "notional_quote")?,
    })
}

fn parse_canonical_l2(row: &csv::StringRecord, idx: &CanonicalL2Idx) -> Result<L2LevelUpdate> {
    Ok(L2LevelUpdate {
        seq: parse_u64(row, idx.seq, "seq")?,
        exchange_ts_us: parse_u64(row, idx.exchange_ts, "exchange_ts_us")?,
        local_ts_us: parse_u64(row, idx.local_ts, "local_ts_us")?,
        is_snapshot: parse_bool(field(row, idx.is_snapshot)),
        side: parse_side(field(row, idx.side))?,
        price: parse_f64(row, idx.price, "price")?,
        qty: parse_f64(row, idx.qty, "qty")?,
    })
}

fn parse_bool(raw: &str) -> bool {
    matches!(
        raw.trim().to_ascii_lowercase().as_str(),
        "true" | "1" | "yes"
    )
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

struct CanonicalQuoteIdx {
    seq: usize,
    exchange_ts: usize,
    local_ts: usize,
    bid_px: usize,
    bid_qty: usize,
    ask_px: usize,
    ask_qty: usize,
}

impl CanonicalQuoteIdx {
    fn new(headers: &csv::StringRecord) -> Result<Self> {
        Ok(Self {
            seq: header_idx(headers, "seq")?,
            exchange_ts: header_idx(headers, "exchange_ts_us")?,
            local_ts: header_idx(headers, "local_ts_us")?,
            bid_px: header_idx(headers, "bid_px")?,
            bid_qty: header_idx(headers, "bid_qty")?,
            ask_px: header_idx(headers, "ask_px")?,
            ask_qty: header_idx(headers, "ask_qty")?,
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

struct CanonicalTradeIdx {
    seq: usize,
    trade_id: usize,
    exchange_ts: usize,
    local_ts: usize,
    side: usize,
    price: usize,
    qty: usize,
    notional_quote: usize,
}

impl CanonicalTradeIdx {
    fn new(headers: &csv::StringRecord) -> Result<Self> {
        Ok(Self {
            seq: header_idx(headers, "seq")?,
            trade_id: header_idx(headers, "trade_id")?,
            exchange_ts: header_idx(headers, "exchange_ts_us")?,
            local_ts: header_idx(headers, "local_ts_us")?,
            side: header_idx(headers, "side")?,
            price: header_idx(headers, "price")?,
            qty: header_idx(headers, "qty")?,
            notional_quote: header_idx(headers, "notional_quote")?,
        })
    }
}

struct CanonicalL2Idx {
    seq: usize,
    exchange_ts: usize,
    local_ts: usize,
    is_snapshot: usize,
    side: usize,
    price: usize,
    qty: usize,
}

impl CanonicalL2Idx {
    fn new(headers: &csv::StringRecord) -> Result<Self> {
        Ok(Self {
            seq: header_idx(headers, "seq")?,
            exchange_ts: header_idx(headers, "exchange_ts_us")?,
            local_ts: header_idx(headers, "local_ts_us")?,
            is_snapshot: header_idx(headers, "is_snapshot")?,
            side: header_idx(headers, "side")?,
            price: header_idx(headers, "price")?,
            qty: header_idx(headers, "qty")?,
        })
    }
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
    fn l2_without_snapshot_is_present_but_not_reconstructible() {
        let root = temp_repo("l2_without_snapshot");
        write_raw_gz(
            &canonical_path(&root, "CCUSDT", "l2_level_update_v1", "2026-05-18"),
            "seq,exchange_ts_us,local_ts_us,is_snapshot,side,price,qty\n0,1,2,false,buy,1.00,4\n",
        );

        let validation = validate_one(&root, "CCUSDT", "l2_level_update_v1", "2026-05-18").unwrap();
        assert_eq!(validation.status, "warning_no_snapshot");
        assert!(!validation.quality.reconstructible);
        assert_eq!(validation.quality.snapshot_rows, 0);
        assert!(
            validation
                .quality
                .warnings
                .iter()
                .any(|warning| warning == "no initial snapshot")
        );
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

    #[test]
    fn market_stream_merges_by_time_with_stable_ties() {
        let root = temp_repo("market_stream_order");
        write_raw_gz(
            &canonical_path(&root, "CCUSDT", "quote_frame_v1", "2026-05-18"),
            "seq,exchange_ts_us,local_ts_us,bid_px,bid_qty,ask_px,ask_qty,mid_px,spread_bps\n0,100,1000,1.00,4,1.01,5,1.005,99.5\n1,200,2000,1.01,4,1.02,5,1.015,98.5\n",
        );
        write_raw_gz(
            &canonical_path(&root, "CCUSDT", "trade_event_v1", "2026-05-18"),
            "seq,trade_id,exchange_ts_us,local_ts_us,side,price,qty,notional_quote\n0,t0,100,1000,buy,1.01,7,7.07\n",
        );
        write_raw_gz(
            &canonical_path(&root, "CCUSDT", "l2_level_update_v1", "2026-05-18"),
            "seq,exchange_ts_us,local_ts_us,is_snapshot,side,price,qty\n0,100,1000,true,buy,1.00,4\n",
        );

        let events = stream_canonical_market(&root, "CCUSDT", "2026-05-18", true, 100, None)
            .unwrap()
            .take(4)
            .map(|event| event.unwrap())
            .collect::<Vec<_>>();
        let tags = events
            .iter()
            .map(|event| match event {
                CanonicalMarketEvent::Quote { .. } => "quote",
                CanonicalMarketEvent::Trade { .. } => "trade",
                CanonicalMarketEvent::L2Batch { .. } => "l2",
            })
            .collect::<Vec<_>>();
        assert_eq!(tags, vec!["quote", "trade", "l2", "quote"]);
        assert_eq!(
            events
                .iter()
                .map(CanonicalMarketEvent::stream_seq)
                .collect::<Vec<_>>(),
            vec![0, 1, 2, 3]
        );
    }

    #[test]
    fn l2_stream_batches_remain_bounded_for_same_timestamp() {
        let root = temp_repo("l2_batch_cap");
        write_raw_gz(
            &canonical_path(&root, "CCUSDT", "l2_level_update_v1", "2026-05-18"),
            "seq,exchange_ts_us,local_ts_us,is_snapshot,side,price,qty\n0,100,1000,true,buy,1.00,4\n1,101,1000,true,sell,1.01,5\n2,102,1000,true,buy,0.99,6\n3,200,2000,false,sell,1.02,7\n",
        );

        let batches = stream_canonical_l2_batches(&root, "CCUSDT", "2026-05-18", 2, None)
            .unwrap()
            .map(|batch| batch.unwrap())
            .collect::<Vec<_>>();
        assert_eq!(batches.len(), 3);
        assert_eq!(batches[0].len(), 2);
        assert_eq!(batches[1].len(), 1);
        assert_eq!(batches[2].len(), 1);
        assert_eq!(batches[0][0].local_ts_us, 1000);
        assert_eq!(batches[1][0].local_ts_us, 1000);
        assert_eq!(batches[2][0].local_ts_us, 2000);
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

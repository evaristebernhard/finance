use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, bail};
use arrow::array::{
    ArrayRef, BooleanBuilder, Float64Builder, Int64Builder, StringBuilder,
};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use chrono::{Duration, NaiveDate};
use clap::Parser;
use flate2::read::GzDecoder;
use serde::Serialize;

use finance_chain_core::storage::write_parquet_part;

const EPS: f64 = 1e-12;
const PRICE_SCALE: f64 = 1_000_000_000.0;
const TRADE_WINDOW_US: i64 = 2_000_000;
const BUCKET_US: i64 = 60_000_000;
const BUILDER_VERSION: &str = "decision_frame_builder_v1.1_market_derived_cache";
const RUST_EXPORTER_VERSION: &str = "ccusdt_rust_decision_frame_cache_v0_1";
const SCHEMA_VERSION: &str = "decision_frame_v1.parquet.schema_v1";

const CACHE_FIELDS: &[&str] = &[
    "schema_id",
    "runtime_safe",
    "observed_seq",
    "exchange_ts_us",
    "local_ts_us",
    "local_timestamp",
    "event_index",
    "is_snapshot_batch",
    "factor_eligible",
    "batch_rows",
    "crossed_levels_removed",
    "best_bid_price",
    "best_bid_amount",
    "best_ask_price",
    "best_ask_amount",
    "mid_price",
    "mid",
    "spread_bps",
    "bid_levels",
    "ask_levels",
    "trade_window_count",
    "trade_buy_amount",
    "trade_sell_amount",
    "trade_notional_quote",
    "trade_flow_imbalance",
    "mid_change_prev",
    "quote_change_prev",
    "top_size_change_prev",
    "frames_since_mid_change",
    "past_event_25_bps",
    "fwd_time_60s_bucket",
];

#[derive(Debug, Parser)]
#[command(
    name = "ccusdt_rust_decision_frame_cache",
    about = "Build decision_frame_v1 Parquet cache from raw Bullish trades and incremental L2 in Rust."
)]
struct Args {
    #[arg(long, default_value = ".")]
    repo_root: PathBuf,

    #[arg(long, default_value = "ETHFIUSDC")]
    symbol: String,

    #[arg(long)]
    from_date: NaiveDate,

    #[arg(long)]
    to_date: NaiveDate,

    #[arg(long)]
    force: bool,

    #[arg(long)]
    max_l2_rows_per_day: Option<usize>,
}

#[derive(Debug, Clone)]
struct Trade {
    local_ts_us: i64,
    side: Side,
    price: f64,
    qty: f64,
}

#[derive(Debug, Clone)]
struct L2Update {
    exchange_ts_us: i64,
    local_ts_us: i64,
    is_snapshot: bool,
    side: Side,
    price: f64,
    qty: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Side {
    Buy,
    Sell,
}

#[derive(Debug, Clone)]
struct DecisionFrame {
    runtime_safe: bool,
    exchange_ts_us: i64,
    local_ts_us: i64,
    event_index: i64,
    is_snapshot_batch: bool,
    factor_eligible: bool,
    batch_rows: i64,
    crossed_levels_removed: i64,
    best_bid_price: Option<f64>,
    best_bid_amount: Option<f64>,
    best_ask_price: Option<f64>,
    best_ask_amount: Option<f64>,
    mid_price: Option<f64>,
    spread_bps: Option<f64>,
    bid_levels: i64,
    ask_levels: i64,
    trade_window_count: i64,
    trade_buy_amount: f64,
    trade_sell_amount: f64,
    trade_notional_quote: f64,
    trade_flow_imbalance: Option<f64>,
    mid_change_prev: bool,
    quote_change_prev: bool,
    top_size_change_prev: bool,
    frames_since_mid_change: f64,
    past_event_25_bps: Option<f64>,
    fwd_time_60s_bucket: i64,
}

#[derive(Debug, Default)]
struct DecisionL2Book {
    bids: BTreeMap<i64, f64>,
    asks: BTreeMap<i64, f64>,
}

impl DecisionL2Book {
    fn price_key(price: f64) -> i64 {
        (price * PRICE_SCALE).round() as i64
    }

    fn key_price(key: i64) -> f64 {
        key as f64 / PRICE_SCALE
    }

    fn clear(&mut self) {
        self.bids.clear();
        self.asks.clear();
    }

    fn set_level(&mut self, side: Side, price: f64, qty: f64) {
        let key = Self::price_key(price);
        let levels = match side {
            Side::Buy => &mut self.bids,
            Side::Sell => &mut self.asks,
        };
        if qty <= 0.0 {
            levels.remove(&key);
        } else {
            levels.insert(key, qty);
        }
    }

    fn replace_from_snapshot(&mut self, updates: &[L2Update]) {
        self.clear();
        for update in updates {
            self.set_level(update.side, update.price, update.qty);
        }
    }

    fn cleanup_crossed(&mut self, updated_side: Side) -> i64 {
        let mut removed = 0;
        while let (Some(best_bid), Some(best_ask)) = (
            self.bids.keys().next_back().copied(),
            self.asks.keys().next().copied(),
        ) {
            if best_bid < best_ask {
                break;
            }
            match updated_side {
                Side::Buy => {
                    self.asks.remove(&best_ask);
                }
                Side::Sell => {
                    self.bids.remove(&best_bid);
                }
            }
            removed += 1;
        }
        removed
    }

    fn top(&self) -> (Option<f64>, Option<f64>, Option<f64>, Option<f64>) {
        let bid_key = self.bids.keys().next_back().copied();
        let ask_key = self.asks.keys().next().copied();
        let bid = bid_key.map(Self::key_price);
        let ask = ask_key.map(Self::key_price);
        let bid_qty = bid_key.and_then(|key| self.bids.get(&key).copied());
        let ask_qty = ask_key.and_then(|key| self.asks.get(&key).copied());
        (bid, bid_qty, ask, ask_qty)
    }

    fn is_crossed(&self) -> bool {
        match (
            self.bids.keys().next_back().copied(),
            self.asks.keys().next().copied(),
        ) {
            (Some(bid), Some(ask)) => bid >= ask,
            _ => false,
        }
    }
}

#[derive(Debug)]
struct DecisionFrameBuilder {
    book: DecisionL2Book,
    trades: VecDeque<Trade>,
    seen_snapshot: bool,
    event_index: i64,
    day_start_ts_us: Option<i64>,
    previous_mid: Option<f64>,
    previous_bid: Option<f64>,
    previous_ask: Option<f64>,
    previous_bid_qty: Option<f64>,
    previous_ask_qty: Option<f64>,
    last_mid_change_index: Option<i64>,
    mid_history: VecDeque<f64>,
}

impl DecisionFrameBuilder {
    fn new() -> Self {
        Self {
            book: DecisionL2Book::default(),
            trades: VecDeque::new(),
            seen_snapshot: false,
            event_index: 0,
            day_start_ts_us: None,
            previous_mid: None,
            previous_bid: None,
            previous_ask: None,
            previous_bid_qty: None,
            previous_ask_qty: None,
            last_mid_change_index: None,
            mid_history: VecDeque::with_capacity(25),
        }
    }

    fn observe_trade(&mut self, trade: Trade) {
        self.trades.push_back(trade);
    }

    fn build_from_l2_updates(&mut self, updates: &[L2Update]) -> Option<DecisionFrame> {
        if updates.is_empty() {
            return None;
        }
        let local_ts_us = updates[0].local_ts_us;
        let exchange_ts_us = updates[0].exchange_ts_us;
        let snapshot_batch = updates.iter().any(|update| update.is_snapshot);
        if !self.seen_snapshot && !snapshot_batch {
            return None;
        }

        let before_has_book = !self.book.bids.is_empty() && !self.book.asks.is_empty();
        let crossed_removed = if snapshot_batch {
            self.seen_snapshot = true;
            self.book.replace_from_snapshot(updates);
            0
        } else {
            let mut last_side = updates[0].side;
            for update in updates {
                last_side = update.side;
                self.book.set_level(last_side, update.price, update.qty);
            }
            self.book.cleanup_crossed(last_side)
        };

        self.event_index += 1;
        if self.day_start_ts_us.is_none() {
            self.day_start_ts_us = Some(local_ts_us);
        }

        self.trim_trades(local_ts_us);
        let (bid, bid_qty, ask, ask_qty) = self.book.top();
        let mid = match (bid, ask) {
            (Some(bid), Some(ask)) => Some((bid + ask) * 0.5),
            _ => None,
        };
        let spread_bps = match (bid, ask, mid) {
            (Some(bid), Some(ask), Some(mid)) if mid > EPS => Some((ask - bid) / mid * 10_000.0),
            _ => None,
        };
        let crossed_after_cleanup = self.book.is_crossed();
        let factor_eligible =
            mid.is_some() && !crossed_after_cleanup && crossed_removed == 0 && (!snapshot_batch || before_has_book);

        let (trade_count, buy_qty, sell_qty, notional) = self.trade_window_stats(local_ts_us);
        let tfi = if buy_qty + sell_qty > EPS {
            Some((buy_qty - sell_qty) / (buy_qty + sell_qty))
        } else {
            None
        };

        let mid_change_prev = match (self.previous_mid, mid) {
            (Some(prev), Some(mid)) => (mid - prev).abs() > EPS,
            _ => false,
        };
        let quote_change_prev = match (self.previous_bid, self.previous_ask, bid, ask) {
            (Some(prev_bid), Some(prev_ask), Some(bid), Some(ask)) => {
                (bid - prev_bid).abs() > EPS || (ask - prev_ask).abs() > EPS
            }
            _ => false,
        };
        let top_size_change_prev = match (self.previous_bid_qty, self.previous_ask_qty, bid_qty, ask_qty) {
            (Some(prev_bid_qty), Some(prev_ask_qty), Some(bid_qty), Some(ask_qty)) => {
                (bid_qty - prev_bid_qty).abs() > EPS || (ask_qty - prev_ask_qty).abs() > EPS
            }
            _ => false,
        };
        if mid_change_prev {
            self.last_mid_change_index = Some(self.event_index - 1);
        }
        let frames_since_mid_change = self
            .last_mid_change_index
            .map(|last| ((self.event_index - 1) - last) as f64)
            .unwrap_or(f64::INFINITY);

        let mut past_event_25_bps = None;
        if let Some(mid) = mid.filter(|value| *value > EPS) {
            if self.mid_history.len() >= 25 {
                if let Some(past_mid) = self.mid_history.front().copied().filter(|value| *value > EPS) {
                    past_event_25_bps = Some((mid / past_mid).ln() * 10_000.0);
                }
            }
            self.mid_history.push_back(mid);
            while self.mid_history.len() > 25 {
                self.mid_history.pop_front();
            }
        }

        let bucket = (local_ts_us - self.day_start_ts_us.unwrap_or(local_ts_us)) / BUCKET_US.max(1);
        let frame = DecisionFrame {
            runtime_safe: true,
            exchange_ts_us,
            local_ts_us,
            event_index: self.event_index,
            is_snapshot_batch: snapshot_batch,
            factor_eligible,
            batch_rows: updates.len() as i64,
            crossed_levels_removed: crossed_removed,
            best_bid_price: bid,
            best_bid_amount: bid_qty,
            best_ask_price: ask,
            best_ask_amount: ask_qty,
            mid_price: mid,
            spread_bps,
            bid_levels: self.book.bids.len() as i64,
            ask_levels: self.book.asks.len() as i64,
            trade_window_count: trade_count,
            trade_buy_amount: buy_qty,
            trade_sell_amount: sell_qty,
            trade_notional_quote: notional,
            trade_flow_imbalance: tfi,
            mid_change_prev,
            quote_change_prev,
            top_size_change_prev,
            frames_since_mid_change,
            past_event_25_bps,
            fwd_time_60s_bucket: bucket,
        };

        self.previous_mid = mid;
        self.previous_bid = bid;
        self.previous_ask = ask;
        self.previous_bid_qty = bid_qty;
        self.previous_ask_qty = ask_qty;
        Some(frame)
    }

    fn trim_trades(&mut self, local_ts_us: i64) {
        let min_ts = local_ts_us - TRADE_WINDOW_US;
        while self
            .trades
            .front()
            .map(|trade| trade.local_ts_us < min_ts)
            .unwrap_or(false)
        {
            self.trades.pop_front();
        }
    }

    fn trade_window_stats(&self, local_ts_us: i64) -> (i64, f64, f64, f64) {
        let mut count = 0;
        let mut buy_qty = 0.0;
        let mut sell_qty = 0.0;
        let mut notional = 0.0;
        for trade in &self.trades {
            if trade.local_ts_us > local_ts_us {
                break;
            }
            count += 1;
            notional += trade.price * trade.qty;
            match trade.side {
                Side::Buy => buy_qty += trade.qty,
                Side::Sell => sell_qty += trade.qty,
            }
        }
        (count, buy_qty, sell_qty, notional)
    }
}

#[derive(Debug, Serialize)]
struct Manifest {
    schema_id: String,
    schema_version: String,
    builder_version: String,
    dataset: String,
    symbol: String,
    date: String,
    input_layer: String,
    fields: Vec<String>,
    row_count: usize,
    rows: usize,
    rust_exporter_version: String,
    output_path: String,
    raw_trades_path: String,
    raw_l2_path: String,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.from_date > args.to_date {
        bail!("--from-date is after --to-date");
    }
    let repo_root = args.repo_root.canonicalize().unwrap_or(args.repo_root.clone());
    for day in date_range(args.from_date, args.to_date) {
        let rows = build_day(&repo_root, &args.symbol, day, args.force, args.max_l2_rows_per_day)
            .with_context(|| format!("build decision_frame_v1 {} {}", args.symbol, day))?;
        println!("decision_frame_rust day={day} rows={rows}");
    }
    Ok(())
}

fn build_day(
    repo_root: &Path,
    symbol: &str,
    day: NaiveDate,
    force: bool,
    max_l2_rows: Option<usize>,
) -> Result<usize> {
    let day_str = day.to_string();
    let output_dir = repo_root
        .join("data")
        .join("canonical_parquet")
        .join("cex")
        .join("bullish")
        .join(symbol)
        .join("decision_frame_v1")
        .join(format!("dt={day_str}"));
    let part_path = output_dir.join("part_000001.parquet");
    let manifest_path = output_dir.join("manifest.json");
    if part_path.exists() && !force {
        println!("decision_frame_rust day={day_str} status=exists path={}", part_path.display());
        return Ok(0);
    }
    if force {
        if part_path.exists() {
            fs::remove_file(&part_path)
                .with_context(|| format!("remove existing {}", part_path.display()))?;
        }
        if manifest_path.exists() {
            fs::remove_file(&manifest_path)
                .with_context(|| format!("remove existing {}", manifest_path.display()))?;
        }
    }

    let trades_path = raw_path(repo_root, "bullish_trades", symbol, &day_str);
    let l2_path = raw_path(repo_root, "bullish_incremental_book_L2", symbol, &day_str);
    let trades = read_trades(&trades_path)?;
    let frames = build_frames_from_raw_l2(&l2_path, trades, max_l2_rows)?;
    let schema = decision_schema();
    let batch = frames_to_batch(schema.clone(), &frames)?;
    write_parquet_part(&part_path, schema, batch)?;

    let manifest = Manifest {
        schema_id: "decision_frame_parquet_cache_manifest_v1".to_string(),
        schema_version: SCHEMA_VERSION.to_string(),
        builder_version: BUILDER_VERSION.to_string(),
        dataset: "decision_frame_v1".to_string(),
        symbol: symbol.to_string(),
        date: day_str.clone(),
        input_layer: "raw_bullish_csv_gz".to_string(),
        fields: CACHE_FIELDS.iter().map(|value| value.to_string()).collect(),
        row_count: frames.len(),
        rows: frames.len(),
        rust_exporter_version: RUST_EXPORTER_VERSION.to_string(),
        output_path: relative_to_repo(repo_root, &part_path),
        raw_trades_path: relative_to_repo(repo_root, &trades_path),
        raw_l2_path: relative_to_repo(repo_root, &l2_path),
    };
    fs::create_dir_all(&output_dir)?;
    serde_json::to_writer_pretty(File::create(&manifest_path)?, &manifest)?;
    Ok(frames.len())
}

fn build_frames_from_raw_l2(
    path: &Path,
    trades: Vec<Trade>,
    max_l2_rows: Option<usize>,
) -> Result<Vec<DecisionFrame>> {
    let mut reader = csv_reader(path)?;
    let headers = reader.headers()?.clone();
    let idx = L2Idx::new(&headers)?;
    let mut builder = DecisionFrameBuilder::new();
    let mut trade_pos = 0usize;
    let mut frames = Vec::new();
    let mut current_ts: Option<i64> = None;
    let mut batch = Vec::new();
    let mut raw_rows = 0usize;

    for row in reader.records() {
        if max_l2_rows.map(|max| raw_rows >= max).unwrap_or(false) {
            break;
        }
        let row = row?;
        raw_rows += 1;
        let update = parse_l2_update(&row, &idx)?;
        if current_ts.is_some_and(|ts| ts != update.local_ts_us) && !batch.is_empty() {
            flush_batch(&mut builder, &trades, &mut trade_pos, &mut frames, &batch);
            batch.clear();
        }
        current_ts = Some(update.local_ts_us);
        batch.push(update);
    }
    if !batch.is_empty() {
        flush_batch(&mut builder, &trades, &mut trade_pos, &mut frames, &batch);
    }
    Ok(frames)
}

fn flush_batch(
    builder: &mut DecisionFrameBuilder,
    trades: &[Trade],
    trade_pos: &mut usize,
    frames: &mut Vec<DecisionFrame>,
    batch: &[L2Update],
) {
    let ts = batch[0].local_ts_us;
    while *trade_pos < trades.len() && trades[*trade_pos].local_ts_us <= ts {
        builder.observe_trade(trades[*trade_pos].clone());
        *trade_pos += 1;
    }
    if let Some(frame) = builder.build_from_l2_updates(batch) {
        frames.push(frame);
    }
}

fn read_trades(path: &Path) -> Result<Vec<Trade>> {
    let mut reader = csv_reader(path)?;
    let headers = reader.headers()?.clone();
    let idx = TradeIdx::new(&headers)?;
    let mut out = Vec::new();
    for row in reader.records() {
        let row = row?;
        out.push(Trade {
            local_ts_us: parse_i64(&row, idx.local_ts, "local_timestamp")?,
            side: parse_side(field(&row, idx.side))?,
            price: parse_f64(&row, idx.price, "price")?,
            qty: parse_f64(&row, idx.qty, "amount")?.max(0.0),
        });
    }
    out.sort_by_key(|trade| trade.local_ts_us);
    Ok(out)
}

fn frames_to_batch(schema: SchemaRef, frames: &[DecisionFrame]) -> Result<RecordBatch> {
    let n = frames.len();
    let mut schema_id = StringBuilder::with_capacity(n, n * 17);
    let mut runtime_safe = BooleanBuilder::with_capacity(n);
    let mut observed_seq = Int64Builder::with_capacity(n);
    let mut exchange_ts_us = Int64Builder::with_capacity(n);
    let mut local_ts_us = Int64Builder::with_capacity(n);
    let mut local_timestamp = Int64Builder::with_capacity(n);
    let mut event_index = Int64Builder::with_capacity(n);
    let mut is_snapshot_batch = BooleanBuilder::with_capacity(n);
    let mut factor_eligible = BooleanBuilder::with_capacity(n);
    let mut batch_rows = Int64Builder::with_capacity(n);
    let mut crossed_levels_removed = Int64Builder::with_capacity(n);
    let mut best_bid_price = Float64Builder::with_capacity(n);
    let mut best_bid_amount = Float64Builder::with_capacity(n);
    let mut best_ask_price = Float64Builder::with_capacity(n);
    let mut best_ask_amount = Float64Builder::with_capacity(n);
    let mut mid_price = Float64Builder::with_capacity(n);
    let mut mid = Float64Builder::with_capacity(n);
    let mut spread_bps = Float64Builder::with_capacity(n);
    let mut bid_levels = Int64Builder::with_capacity(n);
    let mut ask_levels = Int64Builder::with_capacity(n);
    let mut trade_window_count = Int64Builder::with_capacity(n);
    let mut trade_buy_amount = Float64Builder::with_capacity(n);
    let mut trade_sell_amount = Float64Builder::with_capacity(n);
    let mut trade_notional_quote = Float64Builder::with_capacity(n);
    let mut trade_flow_imbalance = Float64Builder::with_capacity(n);
    let mut mid_change_prev = BooleanBuilder::with_capacity(n);
    let mut quote_change_prev = BooleanBuilder::with_capacity(n);
    let mut top_size_change_prev = BooleanBuilder::with_capacity(n);
    let mut frames_since_mid_change = Float64Builder::with_capacity(n);
    let mut past_event_25_bps = Float64Builder::with_capacity(n);
    let mut fwd_time_60s_bucket = Int64Builder::with_capacity(n);

    for frame in frames {
        schema_id.append_value("decision_frame_v1");
        runtime_safe.append_value(frame.runtime_safe);
        observed_seq.append_null();
        exchange_ts_us.append_value(frame.exchange_ts_us);
        local_ts_us.append_value(frame.local_ts_us);
        local_timestamp.append_value(frame.local_ts_us);
        event_index.append_value(frame.event_index);
        is_snapshot_batch.append_value(frame.is_snapshot_batch);
        factor_eligible.append_value(frame.factor_eligible);
        batch_rows.append_value(frame.batch_rows);
        crossed_levels_removed.append_value(frame.crossed_levels_removed);
        append_opt_f64(&mut best_bid_price, frame.best_bid_price);
        append_opt_f64(&mut best_bid_amount, frame.best_bid_amount);
        append_opt_f64(&mut best_ask_price, frame.best_ask_price);
        append_opt_f64(&mut best_ask_amount, frame.best_ask_amount);
        append_opt_f64(&mut mid_price, frame.mid_price);
        append_opt_f64(&mut mid, frame.mid_price);
        append_opt_f64(&mut spread_bps, frame.spread_bps);
        bid_levels.append_value(frame.bid_levels);
        ask_levels.append_value(frame.ask_levels);
        trade_window_count.append_value(frame.trade_window_count);
        trade_buy_amount.append_value(frame.trade_buy_amount);
        trade_sell_amount.append_value(frame.trade_sell_amount);
        trade_notional_quote.append_value(frame.trade_notional_quote);
        append_opt_f64(&mut trade_flow_imbalance, frame.trade_flow_imbalance);
        mid_change_prev.append_value(frame.mid_change_prev);
        quote_change_prev.append_value(frame.quote_change_prev);
        top_size_change_prev.append_value(frame.top_size_change_prev);
        frames_since_mid_change.append_value(frame.frames_since_mid_change);
        append_opt_f64(&mut past_event_25_bps, frame.past_event_25_bps);
        fwd_time_60s_bucket.append_value(frame.fwd_time_60s_bucket);
    }

    let columns: Vec<ArrayRef> = vec![
        Arc::new(schema_id.finish()),
        Arc::new(runtime_safe.finish()),
        Arc::new(observed_seq.finish()),
        Arc::new(exchange_ts_us.finish()),
        Arc::new(local_ts_us.finish()),
        Arc::new(local_timestamp.finish()),
        Arc::new(event_index.finish()),
        Arc::new(is_snapshot_batch.finish()),
        Arc::new(factor_eligible.finish()),
        Arc::new(batch_rows.finish()),
        Arc::new(crossed_levels_removed.finish()),
        Arc::new(best_bid_price.finish()),
        Arc::new(best_bid_amount.finish()),
        Arc::new(best_ask_price.finish()),
        Arc::new(best_ask_amount.finish()),
        Arc::new(mid_price.finish()),
        Arc::new(mid.finish()),
        Arc::new(spread_bps.finish()),
        Arc::new(bid_levels.finish()),
        Arc::new(ask_levels.finish()),
        Arc::new(trade_window_count.finish()),
        Arc::new(trade_buy_amount.finish()),
        Arc::new(trade_sell_amount.finish()),
        Arc::new(trade_notional_quote.finish()),
        Arc::new(trade_flow_imbalance.finish()),
        Arc::new(mid_change_prev.finish()),
        Arc::new(quote_change_prev.finish()),
        Arc::new(top_size_change_prev.finish()),
        Arc::new(frames_since_mid_change.finish()),
        Arc::new(past_event_25_bps.finish()),
        Arc::new(fwd_time_60s_bucket.finish()),
    ];
    Ok(RecordBatch::try_new(schema, columns)?)
}

fn append_opt_f64(builder: &mut Float64Builder, value: Option<f64>) {
    match value {
        Some(value) => builder.append_value(value),
        None => builder.append_null(),
    }
}

fn decision_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("schema_id", DataType::Utf8, false),
        Field::new("runtime_safe", DataType::Boolean, false),
        Field::new("observed_seq", DataType::Int64, true),
        Field::new("exchange_ts_us", DataType::Int64, false),
        Field::new("local_ts_us", DataType::Int64, false),
        Field::new("local_timestamp", DataType::Int64, false),
        Field::new("event_index", DataType::Int64, false),
        Field::new("is_snapshot_batch", DataType::Boolean, false),
        Field::new("factor_eligible", DataType::Boolean, false),
        Field::new("batch_rows", DataType::Int64, false),
        Field::new("crossed_levels_removed", DataType::Int64, false),
        Field::new("best_bid_price", DataType::Float64, true),
        Field::new("best_bid_amount", DataType::Float64, true),
        Field::new("best_ask_price", DataType::Float64, true),
        Field::new("best_ask_amount", DataType::Float64, true),
        Field::new("mid_price", DataType::Float64, true),
        Field::new("mid", DataType::Float64, true),
        Field::new("spread_bps", DataType::Float64, true),
        Field::new("bid_levels", DataType::Int64, false),
        Field::new("ask_levels", DataType::Int64, false),
        Field::new("trade_window_count", DataType::Int64, false),
        Field::new("trade_buy_amount", DataType::Float64, false),
        Field::new("trade_sell_amount", DataType::Float64, false),
        Field::new("trade_notional_quote", DataType::Float64, false),
        Field::new("trade_flow_imbalance", DataType::Float64, true),
        Field::new("mid_change_prev", DataType::Boolean, false),
        Field::new("quote_change_prev", DataType::Boolean, false),
        Field::new("top_size_change_prev", DataType::Boolean, false),
        Field::new("frames_since_mid_change", DataType::Float64, false),
        Field::new("past_event_25_bps", DataType::Float64, true),
        Field::new("fwd_time_60s_bucket", DataType::Int64, false),
    ]))
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

fn raw_path(repo_root: &Path, dataset: &str, symbol: &str, day: &str) -> PathBuf {
    repo_root
        .join("data")
        .join("ccusdt")
        .join("v1")
        .join("external")
        .join(dataset)
        .join(format!("symbol={symbol}"))
        .join(format!("dt={day}"))
        .join(format!("{symbol}.csv.gz"))
}

fn date_range(from: NaiveDate, to: NaiveDate) -> Vec<NaiveDate> {
    let mut out = Vec::new();
    let mut day = from;
    while day <= to {
        out.push(day);
        day += Duration::days(1);
    }
    out
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

fn parse_i64(row: &csv::StringRecord, idx: usize, name: &str) -> Result<i64> {
    let raw = row.get(idx).context("missing field")?.trim();
    if let Ok(value) = raw.parse::<i64>() {
        return Ok(value);
    }
    let value = raw.parse::<f64>().with_context(|| format!("parse {name}"))?;
    anyhow::ensure!(value.is_finite(), "bad {name}");
    Ok(value as i64)
}

fn parse_bool(raw: &str) -> bool {
    matches!(raw.trim().to_ascii_lowercase().as_str(), "true" | "1" | "yes")
}

fn parse_side(raw: &str) -> Result<Side> {
    match raw.trim().to_ascii_lowercase().as_str() {
        "buy" | "bid" | "b" | "1" => Ok(Side::Buy),
        "sell" | "ask" | "a" | "-1" => Ok(Side::Sell),
        other => bail!("unsupported side: {other}"),
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

struct TradeIdx {
    local_ts: usize,
    side: usize,
    price: usize,
    qty: usize,
}

impl TradeIdx {
    fn new(headers: &csv::StringRecord) -> Result<Self> {
        Ok(Self {
            local_ts: header_idx(headers, "local_timestamp")?,
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

fn parse_l2_update(row: &csv::StringRecord, idx: &L2Idx) -> Result<L2Update> {
    Ok(L2Update {
        exchange_ts_us: parse_i64(row, idx.exchange_ts, "timestamp")?,
        local_ts_us: parse_i64(row, idx.local_ts, "local_timestamp")?,
        is_snapshot: parse_bool(field(row, idx.is_snapshot)),
        side: parse_side(field(row, idx.side))?,
        price: parse_f64(row, idx.price, "price")?,
        qty: parse_f64(row, idx.qty, "amount")?,
    })
}

use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, TryRecvError};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use quant_exchange_sim::PaperExchange;
use quant_replay_core::{
    AccountView, CanonicalMarketEvent, CanonicalMarketStream, ExchangeConfig, ExchangeSnapshot,
    Fill, L2LevelUpdate, MarketFrame, NewOrder, Order, OrderKind, Side, TimeInForce, TradeEvent,
};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunnerOptions {
    pub run_id: String,
    pub run_root: PathBuf,
    pub source_label: String,
    pub exchange_config: ExchangeConfig,
    pub max_frames: usize,
    pub latency_frames: u64,
    pub log_holds: bool,
    pub strategy: ToyStrategyConfig,
}

impl RunnerOptions {
    pub fn run_dir(&self) -> PathBuf {
        self.run_root.join(&self.run_id)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ToyStrategyConfig {
    pub qty: f64,
    pub hold_frames: u64,
}

/// Small, native strategies shipped with the desktop application.
///
/// These are deliberately execution-oriented profiles. They consume only
/// canonical public events and are useful as stable presets before users
/// bring their own strategy plugin.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BuiltinStrategyProfile {
    Tfi,
    QuoteImbalance,
    TradeFlowMomentum,
}

impl BuiltinStrategyProfile {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Tfi => "tfi",
            Self::QuoteImbalance => "quote_imbalance",
            Self::TradeFlowMomentum => "trade_flow_momentum",
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NativeStrategyOptions {
    pub run_id: String,
    pub run_root: PathBuf,
    pub source_label: String,
    pub exchange_config: ExchangeConfig,
    pub max_events: usize,
    pub latency_us: u64,
    pub fill_model: TakerFillModel,
    pub profile: BuiltinStrategyProfile,
    pub qty: f64,
    pub threshold: f64,
    pub window_us: u64,
    pub hold_us: u64,
    pub max_orders: usize,
    #[serde(default)]
    pub l2_preflight: Option<serde_json::Value>,
    #[serde(default = "default_progress_every")]
    pub progress_every: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct NativeStrategySummary {
    pub run_id: String,
    pub run_dir: String,
    pub source_label: String,
    pub strategy_profile: BuiltinStrategyProfile,
    pub events_seen: usize,
    pub quote_events_seen: u64,
    pub trade_events_seen: u64,
    pub l2_batches_seen: u64,
    pub event_count: u64,
    pub orders_submitted: u64,
    pub fills_created: u64,
    pub final_stream_seq: u64,
    pub final_account: AccountView,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunSummary {
    pub run_id: String,
    pub run_dir: String,
    pub source_label: String,
    pub frames_seen: usize,
    pub final_cursor: usize,
    pub final_seq: u64,
    pub event_count: u64,
    pub intents_created: u64,
    pub orders_submitted: u64,
    pub fills_created: u64,
    pub final_account: AccountView,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunEvent {
    pub event_id: u64,
    pub run_id: String,
    pub event_type: String,
    pub replay_seq: u64,
    pub replay_ts: String,
    pub wall_ts_ms: u64,
    pub source: String,
    pub payload: serde_json::Value,
}

#[derive(Clone, Debug, Serialize)]
struct ReplayIndexEntry {
    event_id: u64,
    event_type: String,
    replay_seq: u64,
    replay_ts: String,
    byte_offset: u64,
    byte_len: u64,
}

#[derive(Clone, Debug, Serialize)]
struct ReplayIndex {
    schema_id: &'static str,
    event_count: usize,
    events: Vec<ReplayIndexEntry>,
    orders: BTreeMap<String, Vec<u64>>,
    fills: BTreeMap<String, Vec<u64>>,
}

#[derive(Clone, Debug, Serialize)]
struct PendingIntent {
    intent_id: u64,
    created_seq: u64,
    arrival_seq: u64,
    reason: String,
    observed_mid: f64,
    order: NewOrder,
}

#[derive(Clone, Debug, Serialize)]
struct StrategyDecision {
    action: StrategyAction,
    reason: String,
    order: Option<NewOrder>,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
enum StrategyAction {
    Enter,
    Exit,
    Hold,
}

pub fn default_run_id(prefix: &str) -> String {
    format!("{prefix}_{}", now_ms())
}

pub fn run_toy_strategy(frames: Vec<MarketFrame>, options: RunnerOptions) -> Result<RunSummary> {
    anyhow::ensure!(options.max_frames > 0, "max_frames must be >= 1");
    anyhow::ensure!(options.strategy.qty > 0.0, "strategy qty must be positive");

    let run_dir = options.run_dir();
    fs::create_dir_all(&run_dir).with_context(|| format!("create {}", run_dir.display()))?;
    write_manifest(run_dir.join("manifest.json"), &options)?;

    let mut logger = EventLogger::create(&run_dir, &options.run_id)?;
    let mut exchange = PaperExchange::new(options.exchange_config.clone(), frames)?;
    let mut strategy = ToyOnceStrategy::new(options.strategy.clone());
    let mut pending = VecDeque::<PendingIntent>::new();
    let mut seen_fill_count = 0usize;
    let mut next_intent_id = 1u64;
    let mut frames_seen = 0usize;
    let mut intents_created = 0u64;
    let mut orders_submitted = 0u64;

    let first = exchange.snapshot();
    logger.emit(
        "run_start",
        &first,
        "runner",
        serde_json::json!({
            "source_label": options.source_label,
            "max_frames": options.max_frames,
            "latency_frames": options.latency_frames,
            "strategy": options.strategy,
        }),
    )?;

    loop {
        submit_due_intents(
            &mut exchange,
            &mut pending,
            &mut logger,
            &mut seen_fill_count,
            &mut orders_submitted,
        )?;

        let snapshot = exchange.snapshot();
        logger.emit(
            "market_frame",
            &snapshot,
            "replay_clock",
            serde_json::json!({
                "cursor": snapshot.cursor,
                "frame_count": snapshot.frame_count,
                "frame": snapshot.current_frame,
            }),
        )?;
        logger.emit(
            "portfolio_state",
            &snapshot,
            "portfolio",
            serde_json::json!({
                "account": snapshot.account,
                "open_orders": snapshot.open_orders,
                "order_count": snapshot.order_count,
                "fill_count": snapshot.fill_count,
            }),
        )?;

        let decision = strategy.decide(&snapshot);
        let should_log_decision = options.log_holds || decision.order.is_some();
        if should_log_decision {
            logger.emit(
                "strategy_decision",
                &snapshot,
                "toy_once_strategy",
                serde_json::json!({
                    "decision": decision,
                }),
            )?;
        }

        if let Some(order) = decision.order {
            let intent = PendingIntent {
                intent_id: next_intent_id,
                created_seq: snapshot.current_frame.seq,
                arrival_seq: snapshot
                    .current_frame
                    .seq
                    .saturating_add(options.latency_frames),
                reason: decision.reason,
                observed_mid: snapshot.current_frame.mid,
                order,
            };
            next_intent_id += 1;
            intents_created += 1;
            logger.emit(
                "order_intent",
                &snapshot,
                "toy_once_strategy",
                serde_json::json!({
                    "intent": intent,
                }),
            )?;
            logger.emit(
                "order_scheduled",
                &snapshot,
                "runner",
                serde_json::json!({
                    "intent_id": intent.intent_id,
                    "created_seq": intent.created_seq,
                    "arrival_seq": intent.arrival_seq,
                    "latency_frames": options.latency_frames,
                }),
            )?;
            pending.push_back(intent);
        }

        frames_seen += 1;
        if frames_seen >= options.max_frames || snapshot.cursor + 1 >= snapshot.frame_count {
            break;
        }

        let from_seq = snapshot.current_frame.seq;
        let stepped = exchange.step(1);
        logger.emit(
            "clock_advanced",
            &stepped,
            "runner",
            serde_json::json!({
                "from_seq": from_seq,
                "to_seq": stepped.current_frame.seq,
                "cursor": stepped.cursor,
            }),
        )?;
        emit_new_fills(&exchange, &mut logger, &mut seen_fill_count)?;
    }

    let final_snapshot = exchange.snapshot();
    logger.emit(
        "run_end",
        &final_snapshot,
        "runner",
        serde_json::json!({
            "frames_seen": frames_seen,
            "pending_intents": pending.len(),
            "intents_created": intents_created,
            "orders_submitted": orders_submitted,
            "fills_created": seen_fill_count,
        }),
    )?;
    let event_count = logger.event_count();
    logger.finalize()?;

    let summary = RunSummary {
        run_id: options.run_id,
        run_dir: path_string(&run_dir),
        source_label: options.source_label,
        frames_seen,
        final_cursor: final_snapshot.cursor,
        final_seq: final_snapshot.current_frame.seq,
        event_count,
        intents_created,
        orders_submitted,
        fills_created: seen_fill_count as u64,
        final_account: final_snapshot.account,
    };
    write_json(run_dir.join("summary.json"), &summary)?;
    Ok(summary)
}

pub fn run_native_strategy(
    mut market_stream: CanonicalMarketStream,
    options: NativeStrategyOptions,
) -> Result<NativeStrategySummary> {
    anyhow::ensure!(options.max_events > 0, "max_events must be >= 1");
    anyhow::ensure!(options.qty > 0.0, "strategy qty must be positive");
    anyhow::ensure!(options.threshold > 0.0, "strategy threshold must be positive");
    anyhow::ensure!(options.window_us > 0, "strategy window_us must be positive");
    anyhow::ensure!(options.hold_us > 0, "strategy hold_us must be positive");
    anyhow::ensure!(options.max_orders > 0, "strategy max_orders must be positive");

    let run_dir = options.run_root.join(&options.run_id);
    fs::create_dir_all(&run_dir).with_context(|| format!("create {}", run_dir.display()))?;
    write_manifest(run_dir.join("manifest.json"), &options)?;
    write_native_progress(&run_dir, "running", 0, 0, 0, 0, 0, 0, None)?;

    let mut queued = VecDeque::new();
    let first_quote = loop {
        let event = market_stream
            .next()
            .transpose()?
            .context("market stream had no quote frame")?;
        match event {
            CanonicalMarketEvent::Quote { stream_seq, frame } => break (stream_seq, frame),
            other => queued.push_back(other),
        }
    };
    let mut logger = EventLogger::create(&run_dir, &options.run_id)?;
    let mut exchange = PaperExchange::from_current_frame(
        options.exchange_config.clone(),
        first_quote.1.clone(),
    )?;
    let mut l2_book = L2Book::new();
    let mut strategy = BuiltinStrategy::new(&options);
    let mut pending = VecDeque::<NativePendingOrder>::new();
    let mut events_seen = 0usize;
    let mut quote_events_seen = 0u64;
    let mut trade_events_seen = 0u64;
    let mut l2_batches_seen = 0u64;
    let mut orders_submitted = 0u64;
    let mut next_intent_id = 1u64;
    let mut final_stream_seq = first_quote.0;

    let first_snapshot = exchange.snapshot();
    logger.emit(
        "run_start",
        &first_snapshot,
        "runner",
        serde_json::json!({
            "protocol": "native_builtin_strategy_v1",
            "source_label": options.source_label,
            "strategy_profile": options.profile,
            "latency_us": options.latency_us,
            "max_events": options.max_events,
            "max_orders": options.max_orders,
        }),
    )?;

    queued.push_back(CanonicalMarketEvent::Quote {
        stream_seq: first_quote.0,
        frame: first_quote.1,
    });

    while events_seen < options.max_events {
        let event = match queued.pop_front() {
            Some(event) => event,
            None => match market_stream.next().transpose()? {
                Some(event) => event,
                None => break,
            },
        };
        let stream_seq = event.stream_seq();
        final_stream_seq = stream_seq;
        let event_ts = event.local_ts_us();

        if let Some(frame) = event_quote(&event) {
            exchange.advance_to_frame(frame.clone());
        }
        if let CanonicalMarketEvent::L2Batch { updates, .. } = &event {
            l2_book.apply_batch(updates);
        }
        process_native_due_orders(
            &mut exchange,
            &mut pending,
            &mut logger,
            &options,
            &l2_book,
            event_ts,
            &mut orders_submitted,
        )?;

        let signal = match &event {
            CanonicalMarketEvent::Quote { frame, .. } => {
                quote_events_seen += 1;
                strategy.on_quote(frame);
                Some(strategy.signal())
            }
            CanonicalMarketEvent::Trade { trade, .. } => {
                trade_events_seen += 1;
                strategy.on_trade(trade);
                None
            }
            CanonicalMarketEvent::L2Batch { updates, .. } => {
                l2_batches_seen += 1;
                strategy.on_l2_batch(updates);
                None
            }
        };

        let snapshot = exchange.snapshot();
        match &event {
            CanonicalMarketEvent::Quote { frame, .. } => logger.emit(
                "market_quote",
                &snapshot,
                "replay_clock",
                serde_json::json!({ "stream_seq": stream_seq, "frame": frame, "signal": signal }),
            )?,
            CanonicalMarketEvent::Trade { trade, .. } => logger.emit(
                "market_trade",
                &snapshot,
                "replay_clock",
                serde_json::json!({ "stream_seq": stream_seq, "trade": trade }),
            )?,
            CanonicalMarketEvent::L2Batch { updates, .. } => logger.emit(
                "market_l2_batch",
                &snapshot,
                "replay_clock",
                serde_json::json!({
                    "stream_seq": stream_seq,
                    "update_count": updates.len(),
                    "snapshot_update_count": updates.iter().filter(|update| update.is_snapshot).count(),
                    "incremental_update_count": updates.iter().filter(|update| !update.is_snapshot).count(),
                    "local_ts_us": event.local_ts_us(),
                    "book": l2_book.view(),
                }),
            )?,
        }

        if let (CanonicalMarketEvent::Quote { frame, .. }, Some(signal)) = (&event, signal) {
            logger.emit(
                "strategy_signal",
                &snapshot,
                "native_strategy",
                serde_json::json!({
                    "strategy_profile": options.profile,
                    "signal": signal,
                    "threshold": options.threshold,
                    "signal_snapshot": {
                        "mid": frame.mid,
                        "spread_bps": frame.spread_bps(),
                        "position_qty": snapshot.account.position_qty,
                    },
                    "observed_quote": frame,
                    "observed_ts_us": frame.local_ts_us,
                }),
            )?;
        }

        if let Some(frame) = event_quote(&event) {
            if pending.is_empty() {
                if let Some(decision) = strategy.decide(&snapshot, frame.local_ts_us) {
                    let intent_id = next_intent_id;
                    next_intent_id += 1;
                    let arrival_ts = frame.local_ts_us.saturating_add(options.latency_us);
                    let order = NewOrder {
                        side: decision.side,
                        kind: OrderKind::Market,
                        qty: decision.qty,
                        limit_price: None,
                        tif: TimeInForce::Ioc,
                        reduce_only: decision.reduce_only,
                        client_order_id: Some(format!("native-{intent_id}")),
                    };
                    let pending_order = NativePendingOrder {
                        intent_id,
                        observed_seq: stream_seq,
                        observed_ts_us: frame.local_ts_us,
                        arrival_ts_us: arrival_ts,
                        reason: decision.reason.to_string(),
                        signal: strategy.signal(),
                        observed_quote: frame.clone(),
                        order,
                    };
                    logger.emit(
                        "order_intent",
                        &snapshot,
                        "native_strategy",
                        serde_json::json!({
                            "intent": pending_order,
                            "intent_id": intent_id,
                            "client_order_id": format!("native-{intent_id}"),
                            "strategy_profile": options.profile,
                            "signal": strategy.signal(),
                            "threshold": options.threshold,
                            "signal_snapshot": {
                                "signal": strategy.signal(),
                                "position_qty": snapshot.account.position_qty,
                                "mid": frame.mid,
                                "spread_bps": frame.spread_bps(),
                            },
                            "observed_quote": frame,
                            "observed_spread_bps": frame.spread_bps(),
                            "observed_ts_us": frame.local_ts_us,
                            "reason": pending_order.reason,
                        }),
                    )?;
                    pending.push_back(pending_order);
                }
            }
        }

        events_seen += 1;
        if options.progress_every > 0 && events_seen % options.progress_every == 0 {
            write_native_progress(
                &run_dir,
                "running",
                events_seen,
                quote_events_seen,
                trade_events_seen,
                l2_batches_seen,
                orders_submitted,
                exchange.fills().len() as u64,
                Some(event_ts),
            )?;
        }
    }

    if !pending.is_empty() {
        let last_ts = exchange.current_frame().local_ts_us;
        process_native_due_orders(
            &mut exchange,
            &mut pending,
            &mut logger,
            &options,
            &l2_book,
            last_ts.saturating_add(options.latency_us),
            &mut orders_submitted,
        )?;
    }
    let final_snapshot = exchange.snapshot();
    logger.emit(
        "position_snapshot",
        &final_snapshot,
        "portfolio",
        serde_json::json!({ "account": final_snapshot.account }),
    )?;
    logger.emit(
        "run_end",
        &final_snapshot,
        "runner",
        serde_json::json!({
            "events_seen": events_seen,
            "quote_events_seen": quote_events_seen,
            "trade_events_seen": trade_events_seen,
            "l2_batches_seen": l2_batches_seen,
            "orders_submitted": orders_submitted,
            "fills_created": exchange.fills().len(),
        }),
    )?;

    let summary = NativeStrategySummary {
        run_id: options.run_id.clone(),
        run_dir: run_dir.to_string_lossy().replace('\\', "/"),
        source_label: options.source_label,
        strategy_profile: options.profile,
        events_seen,
        quote_events_seen,
        trade_events_seen,
        l2_batches_seen,
        event_count: logger.event_count(),
        orders_submitted,
        fills_created: exchange.fills().len() as u64,
        final_stream_seq,
        final_account: final_snapshot.account,
    };
    write_native_progress(
        &run_dir,
        "complete",
        events_seen,
        quote_events_seen,
        trade_events_seen,
        l2_batches_seen,
        orders_submitted,
        exchange.fills().len() as u64,
        Some(final_snapshot.current_frame.local_ts_us),
    )?;
    logger.finalize()?;
    write_json(run_dir.join("summary.json"), &summary)?;
    Ok(summary)
}

#[derive(Clone, Debug, Serialize)]
struct NativePendingOrder {
    intent_id: u64,
    observed_seq: u64,
    observed_ts_us: u64,
    arrival_ts_us: u64,
    reason: String,
    signal: f64,
    observed_quote: MarketFrame,
    order: NewOrder,
}

#[derive(Clone, Copy, Debug)]
struct NativeDecision {
    side: Side,
    qty: f64,
    reduce_only: bool,
    reason: &'static str,
}

struct BuiltinStrategy {
    profile: BuiltinStrategyProfile,
    qty: f64,
    threshold: f64,
    window_us: u64,
    hold_us: u64,
    max_orders: usize,
    orders: usize,
    entry_ts_us: Option<u64>,
    last_decision_ts_us: u64,
    current_quote: Option<MarketFrame>,
    previous_quote: Option<MarketFrame>,
    trades: VecDeque<(u64, f64)>,
    signed_flow: f64,
    total_flow: f64,
}

impl BuiltinStrategy {
    fn new(options: &NativeStrategyOptions) -> Self {
        Self {
            profile: options.profile,
            qty: options.qty,
            threshold: options.threshold,
            window_us: options.window_us,
            hold_us: options.hold_us,
            max_orders: options.max_orders,
            orders: 0,
            entry_ts_us: None,
            last_decision_ts_us: 0,
            current_quote: None,
            previous_quote: None,
            trades: VecDeque::new(),
            signed_flow: 0.0,
            total_flow: 0.0,
        }
    }

    fn on_quote(&mut self, frame: &MarketFrame) {
        self.previous_quote = self.current_quote.take();
        self.current_quote = Some(frame.clone());
    }

    fn on_trade(&mut self, trade: &TradeEvent) {
        let signed = trade.side.signed_qty(trade.qty);
        self.trades.push_back((trade.local_ts_us, signed));
        self.signed_flow += signed;
        self.total_flow += trade.qty.abs();
        let cutoff = trade.local_ts_us.saturating_sub(self.window_us);
        while self.trades.front().is_some_and(|(ts, _)| *ts < cutoff) {
            if let Some((_, value)) = self.trades.pop_front() {
                self.signed_flow -= value;
            }
        }
    }

    fn on_l2_batch(&mut self, _updates: &[L2LevelUpdate]) {}

    fn signal(&self) -> f64 {
        match self.profile {
            BuiltinStrategyProfile::Tfi => {
                if self.total_flow <= 0.0 {
                    0.0
                } else {
                    (self.signed_flow / self.total_flow).clamp(-1.0, 1.0)
                }
            }
            BuiltinStrategyProfile::QuoteImbalance => self
                .current_quote
                .as_ref()
                .and_then(MarketFrame::quote_imbalance)
                .unwrap_or(0.0),
            BuiltinStrategyProfile::TradeFlowMomentum => {
                let short_cutoff = self
                    .current_quote
                    .as_ref()
                    .map(|quote| quote.local_ts_us.saturating_sub(self.window_us / 5))
                    .unwrap_or(0);
                let short_flow: f64 = self
                    .trades
                    .iter()
                    .filter(|(ts, _)| *ts >= short_cutoff)
                    .map(|(_, value)| *value)
                    .sum();
                if self.signed_flow.abs() < f64::EPSILON {
                    0.0
                } else {
                    (short_flow / self.signed_flow.abs().max(1e-9)).clamp(-1.0, 1.0)
                }
            }
        }
    }

    fn decide(&mut self, snapshot: &ExchangeSnapshot, ts_us: u64) -> Option<NativeDecision> {
        if self.orders >= self.max_orders || ts_us < self.last_decision_ts_us.saturating_add(1_000_000) {
            return None;
        }
        let signal = self.signal();
        let position = snapshot.account.position_qty;
        if position.abs() > 1e-12 {
            let entry_ts = self.entry_ts_us.unwrap_or(ts_us);
            if ts_us.saturating_sub(entry_ts) >= self.hold_us
                || (position > 0.0 && signal <= -self.threshold)
                || (position < 0.0 && signal >= self.threshold)
            {
                self.orders += 1;
                self.last_decision_ts_us = ts_us;
                self.entry_ts_us = None;
                return Some(NativeDecision {
                    side: if position > 0.0 { Side::Sell } else { Side::Buy },
                    qty: position.abs(),
                    reduce_only: true,
                    reason: "builtin_exit_signal_or_holding_period",
                });
            }
            return None;
        }
        if signal.abs() < self.threshold {
            return None;
        }
        self.orders += 1;
        self.last_decision_ts_us = ts_us;
        self.entry_ts_us = Some(ts_us);
        Some(NativeDecision {
            side: if signal > 0.0 { Side::Buy } else { Side::Sell },
            qty: self.qty,
            reduce_only: false,
            reason: "builtin_entry_signal",
        })
    }
}

fn event_quote(event: &CanonicalMarketEvent) -> Option<&MarketFrame> {
    match event {
        CanonicalMarketEvent::Quote { frame, .. } => Some(frame),
        _ => None,
    }
}

fn process_native_due_orders(
    exchange: &mut PaperExchange,
    pending: &mut VecDeque<NativePendingOrder>,
    logger: &mut EventLogger,
    _options: &NativeStrategyOptions,
    l2_book: &L2Book,
    now_ts_us: u64,
    orders_submitted: &mut u64,
) -> Result<()> {
    while pending
        .front()
        .is_some_and(|intent| intent.arrival_ts_us <= now_ts_us)
    {
        let intent = pending.pop_front().expect("pending order checked");
        let quote = exchange.current_frame().clone();
        let before = exchange.snapshot();
        let fill_start = exchange.fills().len();
        let actual_arrival_ts_us = now_ts_us.max(intent.arrival_ts_us);
        let actual_latency_us = actual_arrival_ts_us.saturating_sub(intent.observed_ts_us);
        let latency_slippage_bps = match intent.order.side {
            Side::Buy => (quote.ask - intent.observed_quote.ask) / intent.observed_quote.mid * 10_000.0,
            Side::Sell => (intent.observed_quote.bid - quote.bid) / intent.observed_quote.mid * 10_000.0,
        };
        let order = match _options.fill_model {
            TakerFillModel::TopOfBookTakerIocV1 => {
                exchange.place_taker_quote_order(intent.order.clone(), &quote)?
            }
            TakerFillModel::L2TakerDepthV1 => {
                let sweep = l2_book.sweep(intent.order.side, intent.order.qty);
                exchange.place_taker_depth_order(
                    intent.order.clone(),
                    sweep.filled_qty,
                    sweep.vwap,
                )?
            }
        };
        *orders_submitted += 1;
        let snapshot = exchange.snapshot();
        logger.emit(
            "order_arrival",
            &snapshot,
            "latency_queue",
            serde_json::json!({
                "intent_id": intent.intent_id,
                "client_order_id": intent.order.client_order_id,
                "observed_seq": intent.observed_seq,
                "observed_ts_us": intent.observed_ts_us,
                "scheduled_arrival_ts_us": intent.arrival_ts_us,
                "arrival_ts_us": actual_arrival_ts_us,
                "actual_latency_us": actual_latency_us,
                "latency_slippage_bps": latency_slippage_bps,
                "arrival_quote": quote,
                "arrival_spread_bps": quote.spread_bps(),
                "reason": intent.reason,
                "signal": intent.signal,
                "fill_model": _options.fill_model,
                "order_id": order.id,
                "order_status": order.status,
                "order": order,
            }),
        )?;
        for fill in &exchange.fills()[fill_start..] {
            let after = exchange.snapshot();
            let signed_qty = fill.side.signed_qty(fill.qty);
            let gross_execution_pnl = (quote.mid - fill.price) * signed_qty;
            let latency_mark_pnl = (quote.mid - intent.observed_quote.mid) * signed_qty;
            let spread_execution_cost = (fill.price - quote.mid) * signed_qty;
            logger.emit(
                "fill_created",
                &snapshot,
                "exchange_simulator",
                serde_json::json!({
                    "intent_id": intent.intent_id,
                    "client_order_id": intent.order.client_order_id,
                    "order_id": fill.order_id,
                    "fill_id": fill.id,
                    "fill": fill,
                    "fee": fill.fee,
                    "position_before": before.account.position_qty,
                    "position_after": after.account.position_qty,
                    "realized_pnl_delta": after.account.realized_pnl - before.account.realized_pnl,
                    "unrealized_pnl": after.account.unrealized_pnl,
                    "net_pnl_delta": after.account.equity - before.account.equity,
                    "actual_latency_us": actual_latency_us,
                    "latency_us": actual_latency_us,
                    "latency_slippage_bps": latency_slippage_bps,
                    "observed_quote": intent.observed_quote,
                    "arrival_quote": quote,
                    "attribution": {
                        "gross_execution_pnl": gross_execution_pnl,
                        "latency_mark_pnl": latency_mark_pnl,
                        "spread_execution_cost": spread_execution_cost,
                        "fee_pnl": -fill.fee,
                        "adverse_selection_pnl": serde_json::Value::Null,
                        "adverse_selection_status": "requires_post_fill_quote",
                        "net_pnl": after.account.equity - before.account.equity,
                    },
                }),
            )?;
            logger.emit(
                "position_snapshot",
                &after,
                "portfolio",
                serde_json::json!({
                    "fill_id": fill.id,
                    "account": after.account,
                }),
            )?;
        }
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BridgeFailurePolicy {
    FailFast,
    HoldAndLog,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum StreamClockMode {
    DeterministicStep,
    AcceleratedAsync,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum StreamLogMode {
    Compact,
    Audit,
    Full,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SparsePublicStreamMode {
    StrictEvent,
    BatchedPublicV1,
    BatchedPublicBarrierV1,
    PanelSparseV1,
    PanelSparseFastClockV1,
}

const SPARSE_PROGRESS_INTERVAL_EVENTS: usize = 25_000;
const SPARSE_FLUSH_INTERVAL_EVENTS: usize = 5_000;

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum OrderArrivalMode {
    Timer,
    NextEvent,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TakerFillModel {
    TopOfBookTakerIocV1,
    L2TakerDepthV1,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct PythonStreamOptions {
    pub run_id: String,
    pub run_root: PathBuf,
    pub source_label: String,
    pub exchange_config: ExchangeConfig,
    pub max_frames: usize,
    pub latency_us: u64,
    pub arrival_mode: OrderArrivalMode,
    pub clock_mode: StreamClockMode,
    pub wall_latency_speedup: f64,
    pub bridge_timeout_ms: u64,
    pub failure_policy: BridgeFailurePolicy,
    pub python: PathBuf,
    pub strategy_script: PathBuf,
    pub strategy_args: Vec<String>,
    pub include_l2: bool,
    pub l2_batch_size: usize,
    pub l2_depth_smoke_qty: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SparsePythonStreamOptions {
    pub run_id: String,
    pub run_root: PathBuf,
    pub source_label: String,
    pub exchange_config: ExchangeConfig,
    pub max_events: usize,
    pub latency_us: u64,
    pub arrival_mode: OrderArrivalMode,
    pub clock_mode: StreamClockMode,
    pub wall_latency_speedup: f64,
    pub bridge_timeout_ms: u64,
    pub failure_policy: BridgeFailurePolicy,
    pub log_mode: StreamLogMode,
    pub fill_model: TakerFillModel,
    pub public_stream_mode: SparsePublicStreamMode,
    pub public_batch_size: usize,
    pub public_batch_max_span_us: u64,
    pub panel_frame_cache_manifest: Option<serde_json::Value>,
    pub compact_l2: bool,
    pub python: PathBuf,
    pub strategy_script: PathBuf,
    pub strategy_args: Vec<String>,
}

impl SparsePythonStreamOptions {
    pub fn run_dir(&self) -> PathBuf {
        self.run_root.join(&self.run_id)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct RunnerServerOptions {
    pub run_id: String,
    pub run_root: PathBuf,
    pub source_label: String,
    pub exchange_config: ExchangeConfig,
    pub max_events: usize,
    pub latency_us: u64,
    pub arrival_mode: OrderArrivalMode,
    pub clock_mode: StreamClockMode,
    pub wall_latency_speedup: f64,
    pub log_mode: StreamLogMode,
    pub fill_model: TakerFillModel,
    pub public_addr: SocketAddr,
    pub private_addr: SocketAddr,
    pub order_addr: SocketAddr,
    pub state_addr: Option<SocketAddr>,
    pub startup_wait_ms: u64,
    pub event_sleep_us: u64,
}

impl RunnerServerOptions {
    pub fn run_dir(&self) -> PathBuf {
        self.run_root.join(&self.run_id)
    }
}

impl PythonStreamOptions {
    pub fn run_dir(&self) -> PathBuf {
        self.run_root.join(&self.run_id)
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct PythonStreamSummary {
    pub run_id: String,
    pub run_dir: String,
    pub source_label: String,
    pub clock_mode: StreamClockMode,
    pub wall_latency_speedup: f64,
    pub frames_seen: usize,
    pub final_cursor: usize,
    pub final_seq: u64,
    pub event_count: u64,
    pub market_quotes_sent: u64,
    pub market_trades_sent: u64,
    pub l2_batches_sent: u64,
    pub l2_depth_sweeps: u64,
    pub strategy_messages_received: u64,
    pub intents_created: u64,
    pub orders_submitted: u64,
    pub fills_created: u64,
    pub bridge_errors: u64,
    pub final_account: AccountView,
}

#[derive(Clone, Debug, Serialize)]
pub struct SparsePythonStreamSummary {
    pub run_id: String,
    pub run_dir: String,
    pub source_label: String,
    pub determinism_mode: String,
    pub profile_manifest_hash: Option<String>,
    pub clock_mode: StreamClockMode,
    pub wall_latency_speedup: f64,
    pub log_mode: StreamLogMode,
    pub fill_model: TakerFillModel,
    pub public_stream_mode: SparsePublicStreamMode,
    pub public_batch_size: usize,
    pub public_batches_sent: u64,
    pub public_barriers_triggered: u64,
    pub public_requeued_suffix_count: u64,
    pub public_requeued_suffix_events: u64,
    pub panel_frames_sent: u64,
    pub arrival_mode: OrderArrivalMode,
    pub events_seen: usize,
    pub quote_events_seen: u64,
    pub trade_events_seen: u64,
    pub l2_batches_seen: u64,
    pub final_stream_seq: u64,
    pub final_quote_seq: u64,
    pub event_count: u64,
    pub strategy_messages_received: u64,
    pub intents_created: u64,
    pub orders_submitted: u64,
    pub fills_created: u64,
    pub bridge_errors: u64,
    pub bot_response_late_count: u64,
    pub arrival_quote_lag_count: u64,
    pub arrival_stream_lag_count: u64,
    pub bridge_wall_latency_us_p50: Option<u64>,
    pub bridge_wall_latency_us_p95: Option<u64>,
    pub bridge_wall_latency_us_max: Option<u64>,
    pub target_miss_us_p50: Option<u64>,
    pub target_miss_us_p95: Option<u64>,
    pub target_miss_us_max: Option<u64>,
    pub timing_ms: serde_json::Value,
    pub final_account: AccountView,
}

#[derive(Clone, Debug)]
pub struct PanelDecisionFrame {
    pub frame: serde_json::Value,
    pub observed_seq: u64,
    pub arrival_stream_seq: u64,
    pub exchange_ts_us: u64,
    pub local_ts_us: u64,
    pub event_index: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunnerServerSummary {
    pub run_id: String,
    pub run_dir: String,
    pub source_label: String,
    pub clock_mode: StreamClockMode,
    pub wall_latency_speedup: f64,
    pub log_mode: StreamLogMode,
    pub fill_model: TakerFillModel,
    pub arrival_mode: OrderArrivalMode,
    pub public_addr: SocketAddr,
    pub private_addr: SocketAddr,
    pub order_addr: SocketAddr,
    pub state_addr: Option<SocketAddr>,
    pub events_seen: usize,
    pub quote_events_seen: u64,
    pub trade_events_seen: u64,
    pub l2_batches_seen: u64,
    pub final_stream_seq: u64,
    pub final_quote_seq: u64,
    pub event_count: u64,
    pub ingress_messages_received: u64,
    pub intents_created: u64,
    pub orders_submitted: u64,
    pub fills_created: u64,
    pub ingress_errors: u64,
    pub final_account: AccountView,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunnerServerStateView {
    pub run_id: String,
    pub source_label: String,
    pub clock_mode: StreamClockMode,
    pub log_mode: StreamLogMode,
    pub fill_model: TakerFillModel,
    pub arrival_mode: OrderArrivalMode,
    pub public_addr: SocketAddr,
    pub private_addr: SocketAddr,
    pub order_addr: SocketAddr,
    pub state_addr: Option<SocketAddr>,
    pub done: bool,
    pub stream_seq: u64,
    pub quote_seq: u64,
    pub exchange_ts_us: u64,
    pub local_ts_us: u64,
    pub mid: f64,
    pub spread_bps: f64,
    pub account: AccountView,
    pub pending_intents: usize,
    pub quote_events_seen: u64,
    pub trade_events_seen: u64,
    pub l2_batches_seen: u64,
    pub ingress_messages_received: u64,
    pub intents_created: u64,
    pub orders_submitted: u64,
    pub fills_created: u64,
    pub ingress_errors: u64,
}

#[derive(Clone, Debug, Serialize)]
struct StreamPendingOrder {
    intent_id: u64,
    observed_seq: u64,
    observed_local_ts_us: u64,
    arrival_local_ts_us: u64,
    arrival_quote_override: Option<MarketFrame>,
    arrival_stream_seq_override: Option<u64>,
    effective_latency_us: u64,
    wall_latency_virtual_staleness_us: u64,
    bridge_wall_latency_us: u64,
    reason: String,
    bridge_wall_latency_ms: u64,
    feature_snapshot: Option<serde_json::Value>,
    shadow_signal: Option<serde_json::Value>,
    observed_quote: MarketFrame,
    order: NewOrder,
}

#[derive(Clone, Debug, Deserialize)]
struct StrategyOrderRequest {
    side: Side,
    #[serde(default = "default_market_kind")]
    kind: OrderKind,
    qty: f64,
    #[serde(default)]
    limit_price: Option<f64>,
    #[serde(default = "default_ioc_tif")]
    tif: TimeInForce,
    #[serde(default)]
    reduce_only: bool,
    #[serde(default)]
    client_order_id: Option<String>,
    #[serde(default)]
    execution_role: Option<String>,
    #[serde(default)]
    post_only: bool,
    #[serde(default)]
    maker_profile_id: Option<String>,
    #[serde(default)]
    queue_model_id: Option<String>,
    #[serde(default)]
    max_rest_us: Option<u64>,
    #[serde(default)]
    queue_reservation_id: Option<String>,
}

impl StrategyOrderRequest {
    fn into_new_order(self) -> Result<NewOrder> {
        let execution_role = self
            .execution_role
            .as_deref()
            .unwrap_or("taker")
            .to_ascii_lowercase();
        anyhow::ensure!(
            execution_role == "taker",
            "maker-aware execution_role={execution_role} is reserved-only; maker execution is disabled"
        );
        anyhow::ensure!(
            !self.post_only
                && self.maker_profile_id.is_none()
                && self.queue_model_id.is_none()
                && self.max_rest_us.is_none()
                && self.queue_reservation_id.is_none(),
            "maker-aware order fields are reserved-only; maker execution is disabled"
        );
        Ok(NewOrder {
            side: self.side,
            kind: self.kind,
            qty: self.qty,
            limit_price: self.limit_price,
            tif: self.tif,
            reduce_only: self.reduce_only,
            client_order_id: self.client_order_id,
        })
    }
}

#[derive(Clone, Debug, Deserialize)]
struct StrategyResponse {
    #[serde(rename = "type")]
    message_type: String,
    #[serde(default)]
    observed_seq: Option<u64>,
    #[serde(default)]
    observed_local_ts_us: Option<u64>,
    #[serde(default)]
    consumed_seq: Option<u64>,
    #[serde(default)]
    consumed_local_ts_us: Option<u64>,
    #[serde(default)]
    reason: Option<String>,
    #[serde(default)]
    cancel_intent_id: Option<u64>,
    #[serde(default)]
    cancel_order_id: Option<u64>,
    #[serde(default)]
    cancel_client_order_id: Option<String>,
    #[serde(default)]
    feature_snapshot: Option<serde_json::Value>,
    #[serde(default)]
    shadow_signal: Option<serde_json::Value>,
    #[serde(default)]
    orders: Vec<StrategyOrderRequest>,
    #[serde(flatten)]
    order: Option<StrategyOrderRequest>,
}

#[derive(Default)]
struct SparseDrainOutcome {
    barrier_consumed_seq: Option<u64>,
    barrier_consumed_local_ts_us: Option<u64>,
    barrier_message_type: Option<String>,
    batch_done: bool,
}

impl SparseDrainOutcome {
    fn observe_response(
        &mut self,
        options: &SparsePythonStreamOptions,
        response: &StrategyResponse,
    ) {
        if self.barrier_consumed_seq.is_some()
            || !matches!(
                options.public_stream_mode,
                SparsePublicStreamMode::BatchedPublicBarrierV1
                    | SparsePublicStreamMode::PanelSparseV1
                    | SparsePublicStreamMode::PanelSparseFastClockV1
            )
        {
            return;
        }
        if !matches!(
            response.message_type.as_str(),
            "submit_order" | "submit_orders" | "cancel_order"
        ) {
            if response.message_type == "batch_done" {
                self.batch_done = true;
                self.barrier_message_type = Some(response.message_type.clone());
            }
            return;
        }
        self.barrier_consumed_seq = response.consumed_seq.or(response.observed_seq);
        self.barrier_consumed_local_ts_us = response
            .consumed_local_ts_us
            .or(response.observed_local_ts_us);
        self.barrier_message_type = Some(response.message_type.clone());
    }
}

fn capacity_decision_from_shadow(
    shadow_signal: &Option<serde_json::Value>,
) -> Option<serde_json::Value> {
    shadow_signal
        .as_ref()
        .and_then(|shadow| shadow.get("capacity_decision"))
        .cloned()
}

fn capacity_shadow_position_id(shadow_signal: &Option<serde_json::Value>) -> Option<u64> {
    capacity_decision_from_shadow(shadow_signal)
        .and_then(|capacity| capacity.get("shadow_position_id").cloned())
        .and_then(|raw| raw.as_u64().or_else(|| raw.as_str()?.parse::<u64>().ok()))
}

fn should_emit_capacity_decision_for_order(
    shadow_signal: &Option<serde_json::Value>,
    order: &NewOrder,
) -> bool {
    let Some(position_id) = capacity_shadow_position_id(shadow_signal) else {
        return capacity_decision_from_shadow(shadow_signal).is_some();
    };
    let expected_client_order_id = format!("shadow-entry-{}", position_id);
    order.client_order_id.as_deref() == Some(expected_client_order_id.as_str())
}

fn emit_capacity_decision(
    logger: &mut EventLogger,
    snapshot: &ExchangeSnapshot,
    source: &str,
    observed_seq: Option<u64>,
    intent_id: Option<u64>,
    reason: Option<&str>,
    feature_snapshot: Option<serde_json::Value>,
    shadow_signal: Option<serde_json::Value>,
) -> Result<()> {
    if let Some(capacity_decision) = capacity_decision_from_shadow(&shadow_signal) {
        logger.emit(
            "capacity_decision",
            snapshot,
            source,
            serde_json::json!({
                "intent_id": intent_id,
                "observed_seq": observed_seq,
                "reason": reason,
                "capacity_decision": capacity_decision,
                "feature_snapshot": feature_snapshot,
                "shadow_signal": shadow_signal,
            }),
        )?;
    }
    Ok(())
}

fn shadow_position_id_from_client_order(
    client_order_id: Option<&String>,
    prefix: &str,
) -> Option<u64> {
    client_order_id
        .and_then(|id| id.strip_prefix(prefix))
        .and_then(|raw| raw.parse::<u64>().ok())
}

fn emit_shadow_position_event(
    logger: &mut EventLogger,
    snapshot: &ExchangeSnapshot,
    source: &str,
    intent: &StreamPendingOrder,
    fill: &Fill,
    intent_id: u64,
) -> Result<()> {
    let client_order_id = intent.order.client_order_id.as_ref();
    if let Some(position_id) =
        shadow_position_id_from_client_order(client_order_id, "shadow-entry-")
    {
        logger.emit(
            "position_opened",
            snapshot,
            source,
            serde_json::json!({
                "intent_id": intent_id,
                "client_order_id": client_order_id,
                "position_lot_id": format!("shadow-lot-{}", position_id),
                "shadow_position_id": position_id,
                "filled_qty": fill.qty,
                "avg_fill_price": fill.price,
                "remaining_qty": fill.qty,
                "fill": fill,
                "capacity_decision": capacity_decision_from_shadow(&intent.shadow_signal),
                "shadow_signal": intent.shadow_signal.clone(),
            }),
        )?;
    } else if let Some(position_id) =
        shadow_position_id_from_client_order(client_order_id, "shadow-exit-")
    {
        let remaining_qty = (intent.order.qty - fill.qty).max(0.0);
        let event_type = if remaining_qty <= 1e-12 {
            "position_closed"
        } else {
            "position_partial_closed"
        };
        logger.emit(
            event_type,
            snapshot,
            source,
            serde_json::json!({
                "intent_id": intent_id,
                "client_order_id": client_order_id,
                "position_lot_id": format!("shadow-lot-{}", position_id),
                "shadow_position_id": position_id,
                "closed_qty": fill.qty,
                "remaining_qty": remaining_qty,
                "exit_price": fill.price,
                "fill": fill,
                "shadow_signal": intent.shadow_signal.clone(),
            }),
        )?;
    }
    Ok(())
}

struct StreamCounters {
    market_quotes_sent: u64,
    market_trades_sent: u64,
    l2_batches_sent: u64,
    l2_depth_sweeps: u64,
    strategy_messages_received: u64,
    intents_created: u64,
    orders_submitted: u64,
    fills_created: u64,
    bridge_errors: u64,
}

struct ServerIngressLine {
    line: String,
    received_wall_us: u64,
}

#[derive(Clone, Debug)]
struct SparseObservation {
    stream_seq: u64,
    local_ts_us: u64,
    sent_wall_us: u64,
    quote: MarketFrame,
}

#[derive(Clone, Debug)]
struct SparsePublicBatch {
    items: Vec<SparsePublicBatchItem>,
    seq_start: Option<u64>,
    seq_end: u64,
    local_ts_start_us: u64,
    local_ts_us: u64,
    exchange_ts_us: u64,
}

#[derive(Clone, Debug)]
struct SparsePublicBatchItem {
    message: serde_json::Value,
    stream_seq: u64,
    exchange_ts_us: u64,
    local_ts_us: u64,
}

impl SparsePublicBatch {
    fn new() -> Self {
        Self {
            items: Vec::new(),
            seq_start: None,
            seq_end: 0,
            local_ts_start_us: 0,
            local_ts_us: 0,
            exchange_ts_us: 0,
        }
    }

    fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    fn push(
        &mut self,
        message: serde_json::Value,
        stream_seq: u64,
        exchange_ts_us: u64,
        local_ts_us: u64,
    ) {
        if self.items.is_empty() {
            self.seq_start = Some(stream_seq);
            self.local_ts_start_us = local_ts_us;
        }
        self.seq_end = stream_seq;
        self.exchange_ts_us = exchange_ts_us;
        self.local_ts_us = local_ts_us;
        self.items.push(SparsePublicBatchItem {
            message,
            stream_seq,
            exchange_ts_us,
            local_ts_us,
        });
    }

    fn should_flush(&self, max_messages: usize, max_span_us: u64) -> bool {
        if self.items.len() >= max_messages.max(1) {
            return true;
        }
        !self.items.is_empty()
            && max_span_us > 0
            && self.local_ts_us.saturating_sub(self.local_ts_start_us) >= max_span_us
    }
}

struct SparseCounters {
    quote_events_seen: u64,
    trade_events_seen: u64,
    l2_batches_seen: u64,
    public_batches_sent: u64,
    public_barriers_triggered: u64,
    public_requeued_suffix_count: u64,
    public_requeued_suffix_events: u64,
    panel_frames_sent: u64,
    strategy_messages_received: u64,
    intents_created: u64,
    orders_submitted: u64,
    fills_created: u64,
    bridge_errors: u64,
    bot_response_late_count: u64,
    arrival_quote_lag_count: u64,
    arrival_stream_lag_count: u64,
    bridge_wall_latency_us_samples: Vec<u64>,
    target_miss_us_samples: Vec<u64>,
}

#[derive(Clone, Debug)]
struct SparseTiming {
    market_read_us: u64,
    bridge_drain_and_response_us: u64,
    order_submit_fill_us: u64,
    barrier_requeue_us: u64,
    progress_emit_us: u64,
    logger_flush_us: u64,
    periodic_flush_count: u64,
    progress_events_emitted: u64,
}

impl SparseTiming {
    fn new() -> Self {
        Self {
            market_read_us: 0,
            bridge_drain_and_response_us: 0,
            order_submit_fill_us: 0,
            barrier_requeue_us: 0,
            progress_emit_us: 0,
            logger_flush_us: 0,
            periodic_flush_count: 0,
            progress_events_emitted: 0,
        }
    }
}

struct ScopeTimer<'a> {
    started: Instant,
    target_us: &'a mut u64,
}

impl<'a> ScopeTimer<'a> {
    fn new(target_us: &'a mut u64) -> Self {
        Self {
            started: Instant::now(),
            target_us,
        }
    }
}

impl Drop for ScopeTimer<'_> {
    fn drop(&mut self) {
        *self.target_us = self.target_us.saturating_add(elapsed_us(self.started));
    }
}

struct ServerCounters {
    quote_events_seen: u64,
    trade_events_seen: u64,
    l2_batches_seen: u64,
    ingress_messages_received: u64,
    intents_created: u64,
    orders_submitted: u64,
    fills_created: u64,
    ingress_errors: u64,
}

impl ServerCounters {
    fn new() -> Self {
        Self {
            quote_events_seen: 0,
            trade_events_seen: 0,
            l2_batches_seen: 0,
            ingress_messages_received: 0,
            intents_created: 0,
            orders_submitted: 0,
            fills_created: 0,
            ingress_errors: 0,
        }
    }
}

impl SparseCounters {
    fn new() -> Self {
        Self {
            quote_events_seen: 0,
            trade_events_seen: 0,
            l2_batches_seen: 0,
            public_batches_sent: 0,
            public_barriers_triggered: 0,
            public_requeued_suffix_count: 0,
            public_requeued_suffix_events: 0,
            panel_frames_sent: 0,
            strategy_messages_received: 0,
            intents_created: 0,
            orders_submitted: 0,
            fills_created: 0,
            bridge_errors: 0,
            bot_response_late_count: 0,
            arrival_quote_lag_count: 0,
            arrival_stream_lag_count: 0,
            bridge_wall_latency_us_samples: Vec::new(),
            target_miss_us_samples: Vec::new(),
        }
    }
}

impl StreamCounters {
    fn new() -> Self {
        Self {
            market_quotes_sent: 0,
            market_trades_sent: 0,
            l2_batches_sent: 0,
            l2_depth_sweeps: 0,
            strategy_messages_received: 0,
            intents_created: 0,
            orders_submitted: 0,
            fills_created: 0,
            bridge_errors: 0,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
struct L2BookView {
    bid_levels: usize,
    ask_levels: usize,
    best_bid: Option<f64>,
    best_ask: Option<f64>,
    bid_depth: Vec<L2BookLevelView>,
    ask_depth: Vec<L2BookLevelView>,
}

#[derive(Clone, Debug, Serialize)]
struct L2BookLevelView {
    price: f64,
    qty: f64,
    cumulative_qty: f64,
}

#[derive(Clone, Debug, Serialize)]
struct DepthSweep {
    side: Side,
    requested_qty: f64,
    filled_qty: f64,
    remaining_qty: f64,
    vwap: Option<f64>,
    depth_slippage_bps: Option<f64>,
    partial_fill: bool,
    levels_consumed: usize,
    reason: String,
}

fn sparse_l2_payload(
    updates: &[L2LevelUpdate],
    book: L2BookView,
    compact_l2: bool,
) -> serde_json::Value {
    if compact_l2 {
        let compact = updates
            .iter()
            .map(|update| {
                let side_code = match update.side {
                    Side::Buy => 1,
                    Side::Sell => -1,
                };
                serde_json::json!([
                    update.seq,
                    update.exchange_ts_us,
                    update.local_ts_us,
                    update.is_snapshot,
                    side_code,
                    update.price,
                    update.qty,
                ])
            })
            .collect::<Vec<_>>();
        serde_json::json!({
            "schema_id": "market_l2_update_compact_v1",
            "updates_compact": compact,
            "book": book,
        })
    } else {
        serde_json::json!({
            "updates": updates,
            "book": book,
        })
    }
}

struct L2Book {
    bids: BTreeMap<i64, f64>,
    asks: BTreeMap<i64, f64>,
    active_snapshot_ts: Option<u64>,
}

impl L2Book {
    const PRICE_SCALE: f64 = 100_000_000.0;
    const DISPLAY_LEVELS: usize = 5;

    fn new() -> Self {
        Self {
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
            active_snapshot_ts: None,
        }
    }

    fn apply_batch(&mut self, updates: &[L2LevelUpdate]) {
        for update in updates {
            if update.is_snapshot && self.active_snapshot_ts != Some(update.local_ts_us) {
                self.bids.clear();
                self.asks.clear();
                self.active_snapshot_ts = Some(update.local_ts_us);
            }
            let key = Self::price_key(update.price);
            let book_side = match update.side {
                Side::Buy => &mut self.bids,
                Side::Sell => &mut self.asks,
            };
            if update.qty <= 0.0 {
                book_side.remove(&key);
            } else {
                book_side.insert(key, update.qty);
            }
        }
    }

    fn view(&self) -> L2BookView {
        let mut bid_cumulative = 0.0;
        let bid_depth = self
            .bids
            .iter()
            .rev()
            .take(Self::DISPLAY_LEVELS)
            .map(|(key, qty)| {
                bid_cumulative += *qty;
                L2BookLevelView {
                    price: Self::price_from_key(*key),
                    qty: *qty,
                    cumulative_qty: bid_cumulative,
                }
            })
            .collect();
        let mut ask_cumulative = 0.0;
        let ask_depth = self
            .asks
            .iter()
            .take(Self::DISPLAY_LEVELS)
            .map(|(key, qty)| {
                ask_cumulative += *qty;
                L2BookLevelView {
                    price: Self::price_from_key(*key),
                    qty: *qty,
                    cumulative_qty: ask_cumulative,
                }
            })
            .collect();
        L2BookView {
            bid_levels: self.bids.len(),
            ask_levels: self.asks.len(),
            best_bid: self
                .bids
                .keys()
                .next_back()
                .map(|key| Self::price_from_key(*key)),
            best_ask: self
                .asks
                .keys()
                .next()
                .map(|key| Self::price_from_key(*key)),
            bid_depth,
            ask_depth,
        }
    }

    fn sweep(&self, side: Side, qty: f64) -> DepthSweep {
        if qty <= 0.0 || !qty.is_finite() {
            return DepthSweep {
                side,
                requested_qty: qty,
                filled_qty: 0.0,
                remaining_qty: qty.max(0.0),
                vwap: None,
                depth_slippage_bps: None,
                partial_fill: true,
                levels_consumed: 0,
                reason: "invalid_qty".to_string(),
            };
        }

        let mut remaining = qty;
        let mut notional = 0.0;
        let mut filled = 0.0;
        let mut levels = 0usize;
        let top_price = match side {
            Side::Buy => self
                .asks
                .keys()
                .next()
                .map(|key| Self::price_from_key(*key)),
            Side::Sell => self
                .bids
                .keys()
                .next_back()
                .map(|key| Self::price_from_key(*key)),
        };

        match side {
            Side::Buy => {
                for (key, level_qty) in &self.asks {
                    let take = remaining.min(*level_qty);
                    if take <= 0.0 {
                        continue;
                    }
                    levels += 1;
                    let price = Self::price_from_key(*key);
                    notional += take * price;
                    filled += take;
                    remaining -= take;
                    if remaining <= 1e-12 {
                        break;
                    }
                }
            }
            Side::Sell => {
                for (key, level_qty) in self.bids.iter().rev() {
                    let take = remaining.min(*level_qty);
                    if take <= 0.0 {
                        continue;
                    }
                    levels += 1;
                    let price = Self::price_from_key(*key);
                    notional += take * price;
                    filled += take;
                    remaining -= take;
                    if remaining <= 1e-12 {
                        break;
                    }
                }
            }
        }

        let vwap = if filled > 0.0 {
            Some(notional / filled)
        } else {
            None
        };
        let depth_slippage_bps = match (side, top_price, vwap) {
            (Side::Buy, Some(top), Some(vwap)) => Some((vwap / top).ln() * 10_000.0),
            (Side::Sell, Some(top), Some(vwap)) => Some((top / vwap).ln() * 10_000.0),
            _ => None,
        };
        let partial_fill = remaining > 1e-12;
        DepthSweep {
            side,
            requested_qty: qty,
            filled_qty: filled,
            remaining_qty: remaining.max(0.0),
            vwap,
            depth_slippage_bps,
            partial_fill,
            levels_consumed: levels,
            reason: if filled == 0.0 {
                "empty_book".to_string()
            } else if partial_fill {
                "insufficient_depth".to_string()
            } else {
                "filled".to_string()
            },
        }
    }

    fn price_key(price: f64) -> i64 {
        (price * Self::PRICE_SCALE).round() as i64
    }

    fn price_from_key(key: i64) -> f64 {
        key as f64 / Self::PRICE_SCALE
    }
}

#[derive(Clone)]
struct StreamHub {
    clients: Arc<Mutex<Vec<TcpStream>>>,
}

impl StreamHub {
    fn bind(addr: SocketAddr, label: &'static str) -> Result<Self> {
        let listener =
            TcpListener::bind(addr).with_context(|| format!("bind {label} stream {addr}"))?;
        let clients = Arc::new(Mutex::new(Vec::new()));
        let accept_clients = Arc::clone(&clients);
        thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(stream) = stream else {
                    break;
                };
                let _ = stream.set_nodelay(true);
                if let Ok(mut clients) = accept_clients.lock() {
                    clients.push(stream);
                } else {
                    break;
                }
            }
        });
        Ok(Self { clients })
    }

    fn broadcast(&self, message: &serde_json::Value) -> Result<()> {
        let mut line = serde_json::to_vec(message)?;
        line.push(b'\n');
        let mut clients = self
            .clients
            .lock()
            .map_err(|_| anyhow::anyhow!("stream hub client lock poisoned"))?;
        let mut kept = Vec::with_capacity(clients.len());
        for mut stream in clients.drain(..) {
            if stream.write_all(&line).is_ok() && stream.flush().is_ok() {
                kept.push(stream);
            }
        }
        *clients = kept;
        Ok(())
    }

    fn has_clients(&self) -> Result<bool> {
        Ok(!self
            .clients
            .lock()
            .map_err(|_| anyhow::anyhow!("stream hub client lock poisoned"))?
            .is_empty())
    }
}

fn spawn_order_ingress(addr: SocketAddr, tx: mpsc::Sender<ServerIngressLine>) -> Result<()> {
    let listener = TcpListener::bind(addr).with_context(|| format!("bind order ingress {addr}"))?;
    thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(stream) = stream else {
                break;
            };
            let tx = tx.clone();
            thread::spawn(move || {
                let reader = BufReader::new(stream);
                for line in reader.lines() {
                    let Ok(line) = line else {
                        break;
                    };
                    if line.trim().is_empty() {
                        continue;
                    }
                    if tx
                        .send(ServerIngressLine {
                            line,
                            received_wall_us: now_us(),
                        })
                        .is_err()
                    {
                        break;
                    }
                }
            });
        }
    });
    Ok(())
}

fn spawn_state_query(addr: SocketAddr, state: Arc<Mutex<RunnerServerStateView>>) -> Result<()> {
    let listener = TcpListener::bind(addr).with_context(|| format!("bind state query {addr}"))?;
    thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(stream) = stream else {
                break;
            };
            let state = Arc::clone(&state);
            thread::spawn(move || {
                let _ = handle_state_query(stream, state);
            });
        }
    });
    Ok(())
}

fn handle_state_query(
    mut stream: TcpStream,
    state: Arc<Mutex<RunnerServerStateView>>,
) -> Result<()> {
    let mut request_line = String::new();
    {
        let mut reader = BufReader::new(&mut stream);
        reader.read_line(&mut request_line)?;
    }
    let path = request_line.split_whitespace().nth(1).unwrap_or("/");
    let (status, body) = match path {
        "/health" => ("200 OK", serde_json::json!({ "ok": true })),
        "/api/state" => {
            let view = state
                .lock()
                .map_err(|_| anyhow::anyhow!("runner server state lock poisoned"))?
                .clone();
            ("200 OK", serde_json::to_value(view)?)
        }
        _ => ("404 Not Found", serde_json::json!({ "error": "not found" })),
    };
    let body = serde_json::to_string_pretty(&body)?;
    write!(
        stream,
        "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.as_bytes().len(),
        body,
    )?;
    stream.flush()?;
    Ok(())
}

fn server_state_view(
    options: &RunnerServerOptions,
    snapshot: &ExchangeSnapshot,
    stream_seq: u64,
    counters: &ServerCounters,
    pending_intents: usize,
    done: bool,
) -> RunnerServerStateView {
    RunnerServerStateView {
        run_id: options.run_id.clone(),
        source_label: options.source_label.clone(),
        clock_mode: options.clock_mode,
        log_mode: options.log_mode,
        fill_model: options.fill_model,
        arrival_mode: options.arrival_mode,
        public_addr: options.public_addr,
        private_addr: options.private_addr,
        order_addr: options.order_addr,
        state_addr: options.state_addr,
        done,
        stream_seq,
        quote_seq: snapshot.current_frame.seq,
        exchange_ts_us: snapshot.current_frame.exchange_ts_us,
        local_ts_us: snapshot.current_frame.local_ts_us,
        mid: snapshot.current_frame.mid,
        spread_bps: snapshot.current_frame.spread_bps(),
        account: snapshot.account.clone(),
        pending_intents,
        quote_events_seen: counters.quote_events_seen,
        trade_events_seen: counters.trade_events_seen,
        l2_batches_seen: counters.l2_batches_seen,
        ingress_messages_received: counters.ingress_messages_received,
        intents_created: counters.intents_created,
        orders_submitted: counters.orders_submitted,
        fills_created: counters.fills_created,
        ingress_errors: counters.ingress_errors,
    }
}

fn update_server_state(
    state: &Arc<Mutex<RunnerServerStateView>>,
    options: &RunnerServerOptions,
    snapshot: &ExchangeSnapshot,
    stream_seq: u64,
    counters: &ServerCounters,
    pending_intents: usize,
    done: bool,
) -> Result<()> {
    let view = server_state_view(
        options,
        snapshot,
        stream_seq,
        counters,
        pending_intents,
        done,
    );
    *state
        .lock()
        .map_err(|_| anyhow::anyhow!("runner server state lock poisoned"))? = view;
    Ok(())
}

struct PythonBridge {
    child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout_rx: Receiver<String>,
    timeout: Duration,
    messages_sent: u64,
    stdin_write_us: u64,
}

impl PythonBridge {
    fn spawn(
        python: &Path,
        strategy_script: &Path,
        strategy_args: &[String],
        timeout: Duration,
    ) -> Result<Self> {
        let mut command = Command::new(python);
        command
            .arg("-u")
            .arg(strategy_script)
            .args(strategy_args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit());
        let mut child = command
            .spawn()
            .with_context(|| format!("spawn python strategy {}", strategy_script.display()))?;
        let stdin = child
            .stdin
            .take()
            .context("python strategy stdin was not piped")?;
        let stdout = child
            .stdout
            .take()
            .context("python strategy stdout was not piped")?;
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                match line {
                    Ok(line) if !line.trim().is_empty() => {
                        if tx.send(line).is_err() {
                            break;
                        }
                    }
                    Ok(_) => {}
                    Err(_) => break,
                }
            }
        });
        Ok(Self {
            child,
            stdin: BufWriter::new(stdin),
            stdout_rx: rx,
            timeout,
            messages_sent: 0,
            stdin_write_us: 0,
        })
    }

    fn send_json(&mut self, value: &serde_json::Value) -> Result<()> {
        let started = Instant::now();
        serde_json::to_writer(&mut self.stdin, value)?;
        self.stdin.write_all(b"\n")?;
        self.stdin.flush()?;
        self.messages_sent += 1;
        self.stdin_write_us = self.stdin_write_us.saturating_add(elapsed_us(started));
        Ok(())
    }

    fn read_line(&self) -> Result<String> {
        match self.stdout_rx.recv_timeout(self.timeout) {
            Ok(line) => Ok(line),
            Err(RecvTimeoutError::Timeout) => anyhow::bail!(
                "python strategy did not respond within {} ms",
                self.timeout.as_millis()
            ),
            Err(RecvTimeoutError::Disconnected) => anyhow::bail!("python strategy stdout closed"),
        }
    }

    fn drain_lines(&self) -> Result<Vec<String>> {
        let mut out = Vec::new();
        loop {
            match self.stdout_rx.try_recv() {
                Ok(line) => out.push(line),
                Err(TryRecvError::Empty) => return Ok(out),
                Err(TryRecvError::Disconnected) => {
                    if out.is_empty() {
                        anyhow::bail!("python strategy stdout closed");
                    }
                    return Ok(out);
                }
            }
        }
    }

    fn drain_lines_after_settle(&self, settle: Duration) -> Result<Vec<String>> {
        let mut out = self.drain_lines()?;
        if !out.is_empty() || settle.is_zero() {
            return Ok(out);
        }
        match self.stdout_rx.recv_timeout(settle) {
            Ok(line) => out.push(line),
            Err(RecvTimeoutError::Timeout) => return Ok(out),
            Err(RecvTimeoutError::Disconnected) => {
                anyhow::bail!("python strategy stdout closed");
            }
        }
        loop {
            match self.stdout_rx.try_recv() {
                Ok(line) => out.push(line),
                Err(TryRecvError::Empty) => return Ok(out),
                Err(TryRecvError::Disconnected) => return Ok(out),
            }
        }
    }
}

pub fn run_python_stream_strategy(
    frames: Vec<MarketFrame>,
    trades: Vec<TradeEvent>,
    l2_updates: Vec<L2LevelUpdate>,
    options: PythonStreamOptions,
) -> Result<PythonStreamSummary> {
    anyhow::ensure!(options.max_frames > 0, "max_frames must be >= 1");
    anyhow::ensure!(
        options.bridge_timeout_ms > 0,
        "bridge_timeout_ms must be >= 1"
    );
    anyhow::ensure!(options.l2_batch_size > 0, "l2_batch_size must be >= 1");
    anyhow::ensure!(
        options.wall_latency_speedup >= 0.0 && options.wall_latency_speedup.is_finite(),
        "wall_latency_speedup must be finite and >= 0"
    );

    let run_dir = options.run_dir();
    fs::create_dir_all(&run_dir).with_context(|| format!("create {}", run_dir.display()))?;
    write_manifest(run_dir.join("manifest.json"), &options)?;

    let mut logger = EventLogger::create(&run_dir, &options.run_id)?;
    let mut bridge = PythonBridge::spawn(
        &options.python,
        &options.strategy_script,
        &options.strategy_args,
        Duration::from_millis(options.bridge_timeout_ms),
    )?;
    let mut exchange = PaperExchange::new(options.exchange_config.clone(), frames)?;
    let mut pending = VecDeque::<StreamPendingOrder>::new();
    let mut counters = StreamCounters::new();
    let mut next_intent_id = 1u64;
    let mut trade_idx = 0usize;
    let mut l2_idx = 0usize;
    let mut l2_book = L2Book::new();
    let mut seen_fill_count = 0usize;
    let mut frames_seen = 0usize;

    let first = exchange.snapshot();
    logger.emit(
        "run_start",
        &first,
        "runner",
        serde_json::json!({
            "protocol": "exchange_stream_v1",
            "mode": options.clock_mode,
            "source_label": options.source_label,
            "latency_us": options.latency_us,
            "wall_latency_speedup": options.wall_latency_speedup,
            "fill_model": "top_of_book_taker_ioc_v1",
            "include_l2": options.include_l2,
            "l2_depth_smoke_qty": options.l2_depth_smoke_qty,
            "python": path_string(&options.python),
            "strategy_script": path_string(&options.strategy_script),
            "strategy_args": options.strategy_args,
        }),
    )?;

    let session_start = stream_message(
        &options.run_id,
        "session_start",
        "control",
        &first,
        serde_json::json!({
            "protocol": "exchange_stream_v1",
            "source_label": options.source_label,
            "latency_us": options.latency_us,
            "clock_mode": options.clock_mode,
            "wall_latency_speedup": options.wall_latency_speedup,
            "fill_model": "top_of_book_taker_ioc_v1",
            "l2_depth_smoke_qty": options.l2_depth_smoke_qty,
        }),
    );
    send_strategy_message(
        &mut bridge,
        &mut logger,
        &options,
        &first,
        session_start,
        &mut pending,
        &mut next_intent_id,
        &mut counters,
    )?;
    submit_due_stream_orders(
        &mut exchange,
        &mut pending,
        &mut logger,
        &mut bridge,
        &options,
        &mut seen_fill_count,
        &mut counters,
        &mut next_intent_id,
    )?;

    loop {
        submit_due_stream_orders(
            &mut exchange,
            &mut pending,
            &mut logger,
            &mut bridge,
            &options,
            &mut seen_fill_count,
            &mut counters,
            &mut next_intent_id,
        )?;

        let snapshot = exchange.snapshot();
        let quote_message = stream_message(
            &options.run_id,
            "market_quote",
            "public",
            &snapshot,
            serde_json::json!({
                "quote": snapshot.current_frame,
            }),
        );
        logger.emit(
            "market_event_sent",
            &snapshot,
            "runner",
            quote_message.clone(),
        )?;
        counters.market_quotes_sent += 1;
        send_strategy_message(
            &mut bridge,
            &mut logger,
            &options,
            &snapshot,
            quote_message,
            &mut pending,
            &mut next_intent_id,
            &mut counters,
        )?;
        submit_due_stream_orders(
            &mut exchange,
            &mut pending,
            &mut logger,
            &mut bridge,
            &options,
            &mut seen_fill_count,
            &mut counters,
            &mut next_intent_id,
        )?;

        while trade_idx < trades.len()
            && trades[trade_idx].local_ts_us <= snapshot.current_frame.local_ts_us
        {
            let trade = trades[trade_idx].clone();
            trade_idx += 1;
            let trade_message = stream_message(
                &options.run_id,
                "market_trade",
                "public",
                &snapshot,
                serde_json::json!({
                    "trade": trade,
                }),
            );
            logger.emit(
                "market_event_sent",
                &snapshot,
                "runner",
                trade_message.clone(),
            )?;
            counters.market_trades_sent += 1;
            send_strategy_message(
                &mut bridge,
                &mut logger,
                &options,
                &snapshot,
                trade_message,
                &mut pending,
                &mut next_intent_id,
                &mut counters,
            )?;
            submit_due_stream_orders(
                &mut exchange,
                &mut pending,
                &mut logger,
                &mut bridge,
                &options,
                &mut seen_fill_count,
                &mut counters,
                &mut next_intent_id,
            )?;
        }

        if options.include_l2 {
            while l2_idx < l2_updates.len()
                && l2_updates[l2_idx].local_ts_us <= snapshot.current_frame.local_ts_us
            {
                let start = l2_idx;
                let batch_ts = l2_updates[l2_idx].local_ts_us;
                while l2_idx < l2_updates.len()
                    && l2_updates[l2_idx].local_ts_us <= snapshot.current_frame.local_ts_us
                    && l2_updates[l2_idx].local_ts_us == batch_ts
                    && l2_idx - start < options.l2_batch_size
                {
                    l2_idx += 1;
                }
                let batch = l2_updates[start..l2_idx].to_vec();
                l2_book.apply_batch(&batch);
                if let Some(qty) = options.l2_depth_smoke_qty {
                    logger.emit(
                        "l2_taker_depth_smoke",
                        &snapshot,
                        "runner",
                        serde_json::json!({
                            "model": "l2_taker_depth_v1",
                            "qty": qty,
                            "book": l2_book.view(),
                            "buy_sweep": l2_book.sweep(Side::Buy, qty),
                            "sell_sweep": l2_book.sweep(Side::Sell, qty),
                        }),
                    )?;
                    counters.l2_depth_sweeps += 1;
                }
                let l2_message = stream_message(
                    &options.run_id,
                    "market_l2_update",
                    "public",
                    &snapshot,
                    serde_json::json!({
                        "updates": batch,
                    }),
                );
                logger.emit("market_event_sent", &snapshot, "runner", l2_message.clone())?;
                counters.l2_batches_sent += 1;
                send_strategy_message(
                    &mut bridge,
                    &mut logger,
                    &options,
                    &snapshot,
                    l2_message,
                    &mut pending,
                    &mut next_intent_id,
                    &mut counters,
                )?;
                submit_due_stream_orders(
                    &mut exchange,
                    &mut pending,
                    &mut logger,
                    &mut bridge,
                    &options,
                    &mut seen_fill_count,
                    &mut counters,
                    &mut next_intent_id,
                )?;
            }
        }

        let account_snapshot = exchange.snapshot();
        let account_message = stream_message(
            &options.run_id,
            "account_snapshot",
            "private",
            &account_snapshot,
            serde_json::json!({
                "account": account_snapshot.account,
                "open_orders": account_snapshot.open_orders,
                "order_count": account_snapshot.order_count,
                "fill_count": account_snapshot.fill_count,
            }),
        );
        send_strategy_message(
            &mut bridge,
            &mut logger,
            &options,
            &account_snapshot,
            account_message,
            &mut pending,
            &mut next_intent_id,
            &mut counters,
        )?;
        submit_due_stream_orders(
            &mut exchange,
            &mut pending,
            &mut logger,
            &mut bridge,
            &options,
            &mut seen_fill_count,
            &mut counters,
            &mut next_intent_id,
        )?;

        logger.emit(
            "portfolio_state",
            &account_snapshot,
            "portfolio",
            serde_json::json!({
                "account": account_snapshot.account,
                "open_orders": account_snapshot.open_orders,
                "order_count": account_snapshot.order_count,
                "fill_count": account_snapshot.fill_count,
            }),
        )?;

        frames_seen += 1;
        if frames_seen >= options.max_frames || snapshot.cursor + 1 >= snapshot.frame_count {
            break;
        }

        let from_seq = snapshot.current_frame.seq;
        let stepped = exchange.step(1);
        logger.emit(
            "clock_advanced",
            &stepped,
            "runner",
            serde_json::json!({
                "from_seq": from_seq,
                "to_seq": stepped.current_frame.seq,
                "cursor": stepped.cursor,
            }),
        )?;
    }

    let final_snapshot = exchange.snapshot();
    let session_end = stream_message(
        &options.run_id,
        "session_end",
        "control",
        &final_snapshot,
        serde_json::json!({
            "frames_seen": frames_seen,
        }),
    );
    let _ = send_strategy_message(
        &mut bridge,
        &mut logger,
        &options,
        &final_snapshot,
        session_end,
        &mut pending,
        &mut next_intent_id,
        &mut counters,
    );

    logger.emit(
        "run_end",
        &final_snapshot,
        "runner",
        serde_json::json!({
            "frames_seen": frames_seen,
            "pending_intents": pending.len(),
            "counters": {
                "market_quotes_sent": counters.market_quotes_sent,
                "market_trades_sent": counters.market_trades_sent,
                "l2_batches_sent": counters.l2_batches_sent,
                "l2_depth_sweeps": counters.l2_depth_sweeps,
                "strategy_messages_received": counters.strategy_messages_received,
                "intents_created": counters.intents_created,
                "orders_submitted": counters.orders_submitted,
                "fills_created": counters.fills_created,
                "bridge_errors": counters.bridge_errors,
            },
        }),
    )?;
    let event_count = logger.event_count();
    logger.finalize()?;
    let _ = bridge.child.kill();

    let summary = PythonStreamSummary {
        run_id: options.run_id,
        run_dir: path_string(&run_dir),
        source_label: options.source_label,
        clock_mode: options.clock_mode,
        wall_latency_speedup: options.wall_latency_speedup,
        frames_seen,
        final_cursor: final_snapshot.cursor,
        final_seq: final_snapshot.current_frame.seq,
        event_count,
        market_quotes_sent: counters.market_quotes_sent,
        market_trades_sent: counters.market_trades_sent,
        l2_batches_sent: counters.l2_batches_sent,
        l2_depth_sweeps: counters.l2_depth_sweeps,
        strategy_messages_received: counters.strategy_messages_received,
        intents_created: counters.intents_created,
        orders_submitted: counters.orders_submitted,
        fills_created: counters.fills_created,
        bridge_errors: counters.bridge_errors,
        final_account: final_snapshot.account,
    };
    logger.finalize()?;
    write_json(run_dir.join("summary.json"), &summary)?;
    Ok(summary)
}

pub fn run_sparse_python_stream_strategy(
    market_stream: CanonicalMarketStream,
    options: SparsePythonStreamOptions,
) -> Result<SparsePythonStreamSummary> {
    run_sparse_python_stream_strategy_inner(market_stream, options, None)
}

pub fn run_panel_sparse_python_stream_strategy(
    market_stream: CanonicalMarketStream,
    panel_frames: VecDeque<PanelDecisionFrame>,
    options: SparsePythonStreamOptions,
) -> Result<SparsePythonStreamSummary> {
    anyhow::ensure!(
        matches!(
            options.public_stream_mode,
            SparsePublicStreamMode::PanelSparseV1
        ),
        "run_panel_sparse_python_stream_strategy requires public_stream_mode=panel_sparse_v1"
    );
    run_sparse_python_stream_strategy_inner(market_stream, options, Some(panel_frames))
}

pub fn run_panel_sparse_fast_clock_python_stream_strategy(
    quote_frames: Vec<MarketFrame>,
    panel_frames: VecDeque<PanelDecisionFrame>,
    options: SparsePythonStreamOptions,
) -> Result<SparsePythonStreamSummary> {
    anyhow::ensure!(
        matches!(
            options.public_stream_mode,
            SparsePublicStreamMode::PanelSparseFastClockV1
        ),
        "run_panel_sparse_fast_clock_python_stream_strategy requires public_stream_mode=panel_sparse_fast_clock_v1"
    );
    anyhow::ensure!(
        matches!(options.fill_model, TakerFillModel::TopOfBookTakerIocV1),
        "panel_sparse_fast_clock_v1 only supports top_of_book_taker_ioc_v1"
    );
    run_panel_sparse_fast_clock_inner(quote_frames, panel_frames, options)
}

fn run_sparse_python_stream_strategy_inner(
    mut market_stream: CanonicalMarketStream,
    options: SparsePythonStreamOptions,
    mut panel_frames: Option<VecDeque<PanelDecisionFrame>>,
) -> Result<SparsePythonStreamSummary> {
    let run_started = Instant::now();
    anyhow::ensure!(options.max_events > 0, "max_events must be >= 1");
    anyhow::ensure!(
        options.bridge_timeout_ms > 0,
        "bridge_timeout_ms must be >= 1"
    );
    anyhow::ensure!(
        options.wall_latency_speedup >= 0.0 && options.wall_latency_speedup.is_finite(),
        "wall_latency_speedup must be finite and >= 0"
    );
    anyhow::ensure!(
        options.public_batch_size > 0,
        "public_batch_size must be >= 1"
    );
    anyhow::ensure!(
        !matches!(
            options.public_stream_mode,
            SparsePublicStreamMode::PanelSparseV1
        ) || panel_frames.is_some(),
        "panel_sparse_v1 requires decision_frame cache input"
    );

    let run_dir = options.run_dir();
    fs::create_dir_all(&run_dir).with_context(|| format!("create {}", run_dir.display()))?;
    write_manifest(run_dir.join("manifest.json"), &options)?;
    let profile_manifest = sparse_profile_manifest(&options);
    write_json(run_dir.join("profile_manifest.json"), &profile_manifest)?;

    let mut pending_start = VecDeque::new();
    let first_quote = loop {
        let event = market_stream
            .next()
            .transpose()?
            .context("market stream had no quote frame")?;
        match event {
            CanonicalMarketEvent::Quote { stream_seq, frame } => break (stream_seq, frame),
            other => pending_start.push_back(other),
        }
    };

    let mut logger = EventLogger::create(&run_dir, &options.run_id)?;
    let mut bridge = PythonBridge::spawn(
        &options.python,
        &options.strategy_script,
        &options.strategy_args,
        Duration::from_millis(options.bridge_timeout_ms),
    )?;
    let mut exchange =
        PaperExchange::from_current_frame(options.exchange_config.clone(), first_quote.1.clone())?;
    let mut l2_book = L2Book::new();
    let mut pending_orders = VecDeque::<StreamPendingOrder>::new();
    let mut observations = VecDeque::<SparseObservation>::new();
    let mut public_batch = SparsePublicBatch::new();
    let mut counters = SparseCounters::new();
    let mut timing = SparseTiming::new();
    let mut next_intent_id = 1u64;
    let mut seen_fill_count = 0usize;
    let mut events_seen = 0usize;
    let mut final_stream_seq = first_quote.0;
    let mut next_progress_at = SPARSE_PROGRESS_INTERVAL_EVENTS;
    let mut next_flush_at = SPARSE_FLUSH_INTERVAL_EVENTS;

    let first_snapshot = exchange.snapshot();
    logger.emit(
        "run_start",
        &first_snapshot,
        "runner",
        serde_json::json!({
            "protocol": "exchange_sparse_stream_v1",
            "source_label": options.source_label,
            "clock_mode": options.clock_mode,
            "latency_us": options.latency_us,
            "arrival_mode": options.arrival_mode,
            "wall_latency_speedup": options.wall_latency_speedup,
            "log_mode": options.log_mode,
            "fill_model": options.fill_model,
            "public_stream_mode": options.public_stream_mode,
            "public_batch_size": options.public_batch_size,
            "public_batch_max_span_us": options.public_batch_max_span_us,
            "panel_frame_cache_manifest": options.panel_frame_cache_manifest.clone(),
            "profile_manifest": profile_manifest.clone(),
            "python": path_string(&options.python),
            "strategy_script": path_string(&options.strategy_script),
            "strategy_args": options.strategy_args,
        }),
    )?;

    let session_start = sparse_stream_message(
        &options.run_id,
        "session_start",
        "control",
        first_quote.0,
        &first_snapshot.current_frame,
        first_snapshot.current_frame.exchange_ts_us,
        first_snapshot.current_frame.local_ts_us,
        serde_json::json!({
            "protocol": "exchange_sparse_stream_v1",
            "source_label": options.source_label,
            "latency_us": options.latency_us,
            "arrival_mode": options.arrival_mode,
            "clock_mode": options.clock_mode,
            "fill_model": options.fill_model,
            "log_mode": options.log_mode,
            "public_stream_mode": options.public_stream_mode,
            "public_batch_size": options.public_batch_size,
            "public_batch_max_span_us": options.public_batch_max_span_us,
            "panel_frame_cache_manifest": options.panel_frame_cache_manifest.clone(),
            "profile_manifest": profile_manifest.clone(),
        }),
    );
    send_sparse_strategy_message(
        &mut bridge,
        &mut logger,
        &options,
        &first_snapshot,
        session_start,
        false,
    )?;
    send_sparse_account_snapshot(&mut bridge, &mut logger, &options, &first_snapshot)?;
    drain_sparse_strategy_messages(
        &bridge,
        &mut logger,
        &options,
        &exchange.snapshot(),
        &observations,
        &mut pending_orders,
        &mut next_intent_id,
        &mut counters,
        &mut timing,
    )?;
    submit_due_sparse_orders(
        &mut exchange,
        &mut pending_orders,
        &mut logger,
        &mut bridge,
        &options,
        &mut seen_fill_count,
        &mut counters,
        &mut timing,
        &mut l2_book,
        first_quote.0,
        first_snapshot.current_frame.exchange_ts_us,
        first_snapshot.current_frame.local_ts_us,
    )?;

    let mut queued_events = pending_start;
    queued_events.push_back(CanonicalMarketEvent::Quote {
        stream_seq: first_quote.0,
        frame: first_quote.1,
    });

    while events_seen < options.max_events {
        let event = if let Some(event) = queued_events.pop_front() {
            Some(event)
        } else {
            let read_started = Instant::now();
            let event = market_stream.next().transpose()?;
            timing.market_read_us = timing
                .market_read_us
                .saturating_add(elapsed_us(read_started));
            event
        };
        let Some(event) = event else {
            break;
        };
        final_stream_seq = event.stream_seq();
        match event {
            CanonicalMarketEvent::Quote { stream_seq, frame } => {
                if matches!(options.arrival_mode, OrderArrivalMode::Timer) {
                    let due_snapshot = exchange.snapshot();
                    flush_sparse_public_batch_if_due(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &due_snapshot,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                        frame.local_ts_us,
                    )?;
                    submit_due_sparse_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &mut bridge,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut timing,
                        &mut l2_book,
                        stream_seq,
                        frame.exchange_ts_us,
                        frame.local_ts_us,
                    )?;
                }
                exchange.advance_to_frame(frame.clone());
                if matches!(options.arrival_mode, OrderArrivalMode::NextEvent) {
                    let due_snapshot = exchange.snapshot();
                    flush_sparse_public_batch_if_due(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &due_snapshot,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                        frame.local_ts_us,
                    )?;
                    submit_due_sparse_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &mut bridge,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut timing,
                        &mut l2_book,
                        stream_seq,
                        frame.exchange_ts_us,
                        frame.local_ts_us,
                    )?;
                }
                let snapshot = exchange.snapshot();
                counters.quote_events_seen += 1;
                remember_observation(
                    &mut observations,
                    SparseObservation {
                        stream_seq,
                        local_ts_us: frame.local_ts_us,
                        sent_wall_us: if matches!(
                            options.public_stream_mode,
                            SparsePublicStreamMode::StrictEvent
                        ) {
                            now_us()
                        } else {
                            0
                        },
                        quote: frame.clone(),
                    },
                );
                let message = sparse_stream_message(
                    &options.run_id,
                    "market_quote",
                    "public",
                    stream_seq,
                    &snapshot.current_frame,
                    frame.exchange_ts_us,
                    frame.local_ts_us,
                    serde_json::json!({
                        "quote": frame,
                    }),
                );
                if !matches!(
                    options.public_stream_mode,
                    SparsePublicStreamMode::PanelSparseV1
                ) {
                    dispatch_sparse_public_message(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &snapshot,
                        message,
                        stream_seq,
                        frame.exchange_ts_us,
                        frame.local_ts_us,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                    )?;
                }
            }
            CanonicalMarketEvent::Trade { stream_seq, trade } => {
                let snapshot = exchange.snapshot();
                let exchange_ts_us = trade.exchange_ts_us;
                let local_ts_us = trade.local_ts_us;
                counters.trade_events_seen += 1;
                flush_sparse_public_batch_if_due(
                    &mut bridge,
                    &mut logger,
                    &options,
                    &snapshot,
                    &mut public_batch,
                    &mut observations,
                    &mut pending_orders,
                    &mut next_intent_id,
                    &mut counters,
                    &mut timing,
                    &mut exchange,
                    &mut seen_fill_count,
                    &mut l2_book,
                    local_ts_us,
                )?;
                submit_due_sparse_orders(
                    &mut exchange,
                    &mut pending_orders,
                    &mut logger,
                    &mut bridge,
                    &options,
                    &mut seen_fill_count,
                    &mut counters,
                    &mut timing,
                    &mut l2_book,
                    stream_seq,
                    exchange_ts_us,
                    local_ts_us,
                )?;
                remember_observation(
                    &mut observations,
                    SparseObservation {
                        stream_seq,
                        local_ts_us,
                        sent_wall_us: if matches!(
                            options.public_stream_mode,
                            SparsePublicStreamMode::StrictEvent
                        ) {
                            now_us()
                        } else {
                            0
                        },
                        quote: snapshot.current_frame.clone(),
                    },
                );
                let message = sparse_stream_message(
                    &options.run_id,
                    "market_trade",
                    "public",
                    stream_seq,
                    &snapshot.current_frame,
                    exchange_ts_us,
                    local_ts_us,
                    serde_json::json!({
                        "trade": trade,
                    }),
                );
                if !matches!(
                    options.public_stream_mode,
                    SparsePublicStreamMode::PanelSparseV1
                ) {
                    dispatch_sparse_public_message(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &snapshot,
                        message,
                        stream_seq,
                        exchange_ts_us,
                        local_ts_us,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                    )?;
                }
            }
            CanonicalMarketEvent::L2Batch {
                stream_seq,
                local_ts_us,
                updates,
            } => {
                let snapshot = exchange.snapshot();
                let exchange_ts_us = updates
                    .first()
                    .map(|update| update.exchange_ts_us)
                    .unwrap_or(local_ts_us);
                if matches!(options.arrival_mode, OrderArrivalMode::Timer) {
                    let due_snapshot = exchange.snapshot();
                    flush_sparse_public_batch_if_due(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &due_snapshot,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                        local_ts_us,
                    )?;
                    submit_due_sparse_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &mut bridge,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut timing,
                        &mut l2_book,
                        stream_seq,
                        exchange_ts_us,
                        local_ts_us,
                    )?;
                }
                l2_book.apply_batch(&updates);
                counters.l2_batches_seen += 1;
                if matches!(options.arrival_mode, OrderArrivalMode::NextEvent) {
                    let due_snapshot = exchange.snapshot();
                    flush_sparse_public_batch_if_due(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &due_snapshot,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                        local_ts_us,
                    )?;
                    submit_due_sparse_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &mut bridge,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut timing,
                        &mut l2_book,
                        stream_seq,
                        exchange_ts_us,
                        local_ts_us,
                    )?;
                }
                remember_observation(
                    &mut observations,
                    SparseObservation {
                        stream_seq,
                        local_ts_us,
                        sent_wall_us: if matches!(
                            options.public_stream_mode,
                            SparsePublicStreamMode::StrictEvent
                        ) {
                            now_us()
                        } else {
                            0
                        },
                        quote: snapshot.current_frame.clone(),
                    },
                );
                let message = sparse_stream_message(
                    &options.run_id,
                    "market_l2_update",
                    "public",
                    stream_seq,
                    &snapshot.current_frame,
                    exchange_ts_us,
                    local_ts_us,
                    sparse_l2_payload(&updates, l2_book.view(), options.compact_l2),
                );
                if matches!(
                    options.public_stream_mode,
                    SparsePublicStreamMode::PanelSparseV1
                ) {
                    dispatch_panel_sparse_decision_frame(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &snapshot,
                        stream_seq,
                        exchange_ts_us,
                        local_ts_us,
                        panel_frames
                            .as_mut()
                            .context("panel_sparse_v1 missing frames")?,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                    )?;
                } else {
                    dispatch_sparse_public_message(
                        &mut bridge,
                        &mut logger,
                        &options,
                        &snapshot,
                        message,
                        stream_seq,
                        exchange_ts_us,
                        local_ts_us,
                        &mut public_batch,
                        &mut observations,
                        &mut pending_orders,
                        &mut next_intent_id,
                        &mut counters,
                        &mut timing,
                        &mut exchange,
                        &mut seen_fill_count,
                        &mut l2_book,
                    )?;
                }
            }
        }
        events_seen += 1;
        if events_seen >= next_progress_at {
            let progress_snapshot = exchange.snapshot();
            emit_sparse_progress(
                &mut logger,
                &options,
                &progress_snapshot,
                &counters,
                &mut timing,
                events_seen,
                final_stream_seq,
                pending_orders.len(),
                run_started,
            )?;
            next_progress_at = next_progress_at.saturating_add(SPARSE_PROGRESS_INTERVAL_EVENTS);
        }
        if events_seen >= next_flush_at {
            flush_sparse_logger(&mut logger, &mut timing)?;
            next_flush_at = next_flush_at.saturating_add(SPARSE_FLUSH_INTERVAL_EVENTS);
        }
    }

    let final_snapshot = exchange.snapshot();
    flush_sparse_public_batch(
        &mut bridge,
        &mut logger,
        &options,
        &final_snapshot,
        &mut public_batch,
        &mut observations,
        &mut pending_orders,
        &mut next_intent_id,
        &mut counters,
        &mut timing,
        &mut exchange,
        &mut seen_fill_count,
        &mut l2_book,
    )?;
    let final_snapshot = exchange.snapshot();
    let session_end = sparse_stream_message(
        &options.run_id,
        "session_end",
        "control",
        final_stream_seq,
        &final_snapshot.current_frame,
        final_snapshot.current_frame.exchange_ts_us,
        final_snapshot.current_frame.local_ts_us,
        serde_json::json!({
            "events_seen": events_seen,
        }),
    );
    let _ = send_sparse_strategy_message(
        &mut bridge,
        &mut logger,
        &options,
        &final_snapshot,
        session_end,
        false,
    );
    logger.emit(
        "run_end",
        &final_snapshot,
        "runner",
        serde_json::json!({
            "events_seen": events_seen,
            "pending_intents": pending_orders.len(),
            "counters": {
                "quote_events_seen": counters.quote_events_seen,
                "trade_events_seen": counters.trade_events_seen,
                "l2_batches_seen": counters.l2_batches_seen,
                "public_batches_sent": counters.public_batches_sent,
                "public_barriers_triggered": counters.public_barriers_triggered,
                "public_requeued_suffix_count": counters.public_requeued_suffix_count,
                "public_requeued_suffix_events": counters.public_requeued_suffix_events,
                "panel_frames_sent": counters.panel_frames_sent,
                "strategy_messages_received": counters.strategy_messages_received,
                "intents_created": counters.intents_created,
                "orders_submitted": counters.orders_submitted,
                "fills_created": counters.fills_created,
                "bridge_errors": counters.bridge_errors,
            },
            "progress": {
                "progress_events_emitted": timing.progress_events_emitted,
                "periodic_flush_count": timing.periodic_flush_count,
                "progress_interval_events": SPARSE_PROGRESS_INTERVAL_EVENTS,
                "flush_interval_events": SPARSE_FLUSH_INTERVAL_EVENTS,
            },
        }),
    )?;
    let event_count = logger.event_count();
    flush_sparse_logger(&mut logger, &mut timing)?;
    let _ = bridge.child.kill();
    let total_elapsed_wall_ms = run_started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    let event_rate_per_s = if total_elapsed_wall_ms > 0 {
        Some(events_seen as f64 / (total_elapsed_wall_ms as f64 / 1_000.0))
    } else {
        None
    };

    let summary = SparsePythonStreamSummary {
        run_id: options.run_id,
        run_dir: path_string(&run_dir),
        source_label: options.source_label,
        determinism_mode: determinism_mode(options.clock_mode).to_string(),
        profile_manifest_hash: profile_manifest_hash(&profile_manifest),
        clock_mode: options.clock_mode,
        wall_latency_speedup: options.wall_latency_speedup,
        log_mode: options.log_mode,
        fill_model: options.fill_model,
        public_stream_mode: options.public_stream_mode,
        public_batch_size: options.public_batch_size,
        public_batches_sent: counters.public_batches_sent,
        public_barriers_triggered: counters.public_barriers_triggered,
        public_requeued_suffix_count: counters.public_requeued_suffix_count,
        public_requeued_suffix_events: counters.public_requeued_suffix_events,
        panel_frames_sent: counters.panel_frames_sent,
        arrival_mode: options.arrival_mode,
        events_seen,
        quote_events_seen: counters.quote_events_seen,
        trade_events_seen: counters.trade_events_seen,
        l2_batches_seen: counters.l2_batches_seen,
        final_stream_seq,
        final_quote_seq: final_snapshot.current_frame.seq,
        event_count,
        strategy_messages_received: counters.strategy_messages_received,
        intents_created: counters.intents_created,
        orders_submitted: counters.orders_submitted,
        fills_created: counters.fills_created,
        bridge_errors: counters.bridge_errors,
        bot_response_late_count: counters.bot_response_late_count,
        arrival_quote_lag_count: counters.arrival_quote_lag_count,
        arrival_stream_lag_count: counters.arrival_stream_lag_count,
        bridge_wall_latency_us_p50: percentile_u64(&counters.bridge_wall_latency_us_samples, 0.50),
        bridge_wall_latency_us_p95: percentile_u64(&counters.bridge_wall_latency_us_samples, 0.95),
        bridge_wall_latency_us_max: counters
            .bridge_wall_latency_us_samples
            .iter()
            .max()
            .copied(),
        target_miss_us_p50: percentile_u64(&counters.target_miss_us_samples, 0.50),
        target_miss_us_p95: percentile_u64(&counters.target_miss_us_samples, 0.95),
        target_miss_us_max: counters.target_miss_us_samples.iter().max().copied(),
        timing_ms: serde_json::json!({
            "total_elapsed_wall_ms": total_elapsed_wall_ms,
            "events_per_second": event_rate_per_s,
            "market_read_ms": timing.market_read_us / 1_000,
            "bridge_stdin_write_ms": bridge.stdin_write_us / 1_000,
            "bridge_stdout_drain_and_response_ms": timing.bridge_drain_and_response_us / 1_000,
            "order_submit_fill_ms": timing.order_submit_fill_us / 1_000,
            "barrier_requeue_ms": timing.barrier_requeue_us / 1_000,
            "progress_emit_ms": timing.progress_emit_us / 1_000,
            "logger_flush_ms": timing.logger_flush_us / 1_000,
            "strategy_messages_sent": bridge.messages_sent,
            "progress_events_emitted": timing.progress_events_emitted,
            "logger_flush_count": timing.periodic_flush_count,
            "progress_interval_events": SPARSE_PROGRESS_INTERVAL_EVENTS,
            "flush_interval_events": SPARSE_FLUSH_INTERVAL_EVENTS,
            "public_stream_mode": options.public_stream_mode,
            "public_batch_size": options.public_batch_size,
            "public_batch_max_span_us": options.public_batch_max_span_us,
            "public_batches_sent": counters.public_batches_sent,
            "public_barriers_triggered": counters.public_barriers_triggered,
            "public_requeued_suffix_count": counters.public_requeued_suffix_count,
            "public_requeued_suffix_events": counters.public_requeued_suffix_events,
            "panel_frames_sent": counters.panel_frames_sent,
            "batch_count": counters.public_batches_sent,
            "barrier_count": counters.public_barriers_triggered,
            "requeued_suffix_count": counters.public_requeued_suffix_count,
            "events_per_sec": event_rate_per_s,
            "bot_parse_time": null,
            "bridge_wait_time_ms": timing.bridge_drain_and_response_us / 1_000,
            "runner_fill_time_ms": timing.order_submit_fill_us / 1_000,
        }),
        final_account: final_snapshot.account,
    };
    logger.finalize()?;
    write_json(run_dir.join("summary.json"), &summary)?;
    Ok(summary)
}

fn run_panel_sparse_fast_clock_inner(
    quote_frames: Vec<MarketFrame>,
    mut panel_frames: VecDeque<PanelDecisionFrame>,
    options: SparsePythonStreamOptions,
) -> Result<SparsePythonStreamSummary> {
    let run_started = Instant::now();
    anyhow::ensure!(options.max_events > 0, "max_events must be >= 1");
    anyhow::ensure!(
        options.bridge_timeout_ms > 0,
        "bridge_timeout_ms must be >= 1"
    );
    anyhow::ensure!(
        options.public_batch_size > 0,
        "public_batch_size must be >= 1"
    );
    anyhow::ensure!(!quote_frames.is_empty(), "quote frame index is empty");
    anyhow::ensure!(!panel_frames.is_empty(), "decision frame cache is empty");
    anyhow::ensure!(
        matches!(options.arrival_mode, OrderArrivalMode::Timer),
        "panel_sparse_fast_clock_v1 currently requires arrival_mode=timer"
    );
    let run_dir = options.run_dir();
    fs::create_dir_all(&run_dir).with_context(|| format!("create {}", run_dir.display()))?;
    write_manifest(run_dir.join("manifest.json"), &options)?;
    let profile_manifest = sparse_profile_manifest(&options);
    let profile_manifest_hash_value = profile_manifest_hash(&profile_manifest);
    write_json(run_dir.join("profile_manifest.json"), &profile_manifest)?;

    let mut logger = EventLogger::create(&run_dir, &options.run_id)?;
    let mut bridge = PythonBridge::spawn(
        &options.python,
        &options.strategy_script,
        &options.strategy_args,
        Duration::from_millis(options.bridge_timeout_ms),
    )?;
    let mut exchange = PaperExchange::from_current_frame(
        options.exchange_config.clone(),
        quote_frames[0].clone(),
    )?;
    let mut l2_book = L2Book::new();
    let mut pending_orders = VecDeque::<StreamPendingOrder>::new();
    let mut observations = VecDeque::<SparseObservation>::new();
    let mut public_batch = SparsePublicBatch::new();
    let mut counters = SparseCounters::new();
    let mut timing = SparseTiming::new();
    let mut next_intent_id = 1u64;
    let mut seen_fill_count = 0usize;
    let mut events_seen = 0usize;
    let mut final_stream_seq = 0u64;
    let mut next_progress_at = SPARSE_PROGRESS_INTERVAL_EVENTS;
    let mut next_flush_at = SPARSE_FLUSH_INTERVAL_EVENTS;

    let first_snapshot = exchange.snapshot();
    logger.emit(
        "run_start",
        &first_snapshot,
        "runner",
        serde_json::json!({
            "protocol": "exchange_sparse_stream_v1",
            "source_label": options.source_label,
            "clock_mode": options.clock_mode,
            "latency_us": options.latency_us,
            "arrival_mode": options.arrival_mode,
            "wall_latency_speedup": options.wall_latency_speedup,
            "log_mode": options.log_mode,
            "fill_model": options.fill_model,
            "public_stream_mode": options.public_stream_mode,
            "public_batch_size": options.public_batch_size,
            "public_batch_max_span_us": options.public_batch_max_span_us,
            "panel_frame_cache_manifest": options.panel_frame_cache_manifest.clone(),
            "profile_manifest": profile_manifest.clone(),
            "quote_index": {
                "source": "quote_frame_v1_canonical_index",
                "row_count": quote_frames.len(),
                "first_local_ts_us": quote_frames.first().map(|frame| frame.local_ts_us),
                "last_local_ts_us": quote_frames.last().map(|frame| frame.local_ts_us),
            },
            "python": path_string(&options.python),
            "strategy_script": path_string(&options.strategy_script),
            "strategy_args": options.strategy_args,
        }),
    )?;

    let session_start = sparse_stream_message(
        &options.run_id,
        "session_start",
        "control",
        0,
        &first_snapshot.current_frame,
        first_snapshot.current_frame.exchange_ts_us,
        first_snapshot.current_frame.local_ts_us,
        serde_json::json!({
            "protocol": "exchange_sparse_stream_v1",
            "source_label": options.source_label,
            "latency_us": options.latency_us,
            "arrival_mode": options.arrival_mode,
            "clock_mode": options.clock_mode,
            "fill_model": options.fill_model,
            "log_mode": options.log_mode,
            "public_stream_mode": options.public_stream_mode,
            "public_batch_size": options.public_batch_size,
            "public_batch_max_span_us": options.public_batch_max_span_us,
            "panel_frame_cache_manifest": options.panel_frame_cache_manifest.clone(),
            "profile_manifest": profile_manifest,
        }),
    );
    send_sparse_strategy_message(
        &mut bridge,
        &mut logger,
        &options,
        &first_snapshot,
        session_start,
        false,
    )?;
    send_sparse_account_snapshot(&mut bridge, &mut logger, &options, &first_snapshot)?;
    drain_sparse_strategy_messages(
        &bridge,
        &mut logger,
        &options,
        &exchange.snapshot(),
        &observations,
        &mut pending_orders,
        &mut next_intent_id,
        &mut counters,
        &mut timing,
    )?;

    while events_seen < options.max_events {
        let Some(panel_frame) = panel_frames.pop_front() else {
            break;
        };
        let read_started = Instant::now();
        let quote = quote_at_or_before(&quote_frames, panel_frame.local_ts_us)
            .with_context(|| {
                format!(
                    "no quote_frame_v1 row at or before decision local_ts_us={}",
                    panel_frame.local_ts_us
                )
            })?
            .clone();
        timing.market_read_us = timing
            .market_read_us
            .saturating_add(elapsed_us(read_started));
        exchange.advance_to_frame(quote.clone());
        final_stream_seq = panel_frame.observed_seq;

        let due_snapshot = exchange.snapshot();
        flush_sparse_public_batch_if_due(
            &mut bridge,
            &mut logger,
            &options,
            &due_snapshot,
            &mut public_batch,
            &mut observations,
            &mut pending_orders,
            &mut next_intent_id,
            &mut counters,
            &mut timing,
            &mut exchange,
            &mut seen_fill_count,
            &mut l2_book,
            panel_frame.local_ts_us,
        )?;
        submit_due_sparse_orders(
            &mut exchange,
            &mut pending_orders,
            &mut logger,
            &mut bridge,
            &options,
            &mut seen_fill_count,
            &mut counters,
            &mut timing,
            &mut l2_book,
            panel_frame.observed_seq,
            panel_frame.exchange_ts_us,
            panel_frame.local_ts_us,
        )?;

        let snapshot = exchange.snapshot();
        if panel_frame.arrival_stream_seq != panel_frame.observed_seq {
            remember_observation(
                &mut observations,
                SparseObservation {
                    stream_seq: panel_frame.arrival_stream_seq,
                    local_ts_us: panel_frame.local_ts_us,
                    sent_wall_us: 0,
                    quote: quote.clone(),
                },
            );
        }
        remember_observation(
            &mut observations,
            SparseObservation {
                stream_seq: panel_frame.observed_seq,
                local_ts_us: panel_frame.local_ts_us,
                sent_wall_us: 0,
                quote: quote.clone(),
            },
        );
        dispatch_panel_sparse_decision_frame_value(
            &mut bridge,
            &mut logger,
            &options,
            &snapshot,
            panel_frame.observed_seq,
            panel_frame.exchange_ts_us,
            panel_frame.local_ts_us,
            panel_frame,
            &mut public_batch,
            &mut observations,
            &mut pending_orders,
            &mut next_intent_id,
            &mut counters,
            &mut timing,
            &mut exchange,
            &mut seen_fill_count,
            &mut l2_book,
        )?;

        counters.l2_batches_seen += 1;
        events_seen += 1;
        if events_seen >= next_progress_at {
            let progress_snapshot = exchange.snapshot();
            emit_sparse_progress(
                &mut logger,
                &options,
                &progress_snapshot,
                &counters,
                &mut timing,
                events_seen,
                final_stream_seq,
                pending_orders.len(),
                run_started,
            )?;
            next_progress_at = next_progress_at.saturating_add(SPARSE_PROGRESS_INTERVAL_EVENTS);
        }
        if events_seen >= next_flush_at {
            flush_sparse_logger(&mut logger, &mut timing)?;
            next_flush_at = next_flush_at.saturating_add(SPARSE_FLUSH_INTERVAL_EVENTS);
        }
    }

    let final_snapshot = exchange.snapshot();
    flush_sparse_public_batch(
        &mut bridge,
        &mut logger,
        &options,
        &final_snapshot,
        &mut public_batch,
        &mut observations,
        &mut pending_orders,
        &mut next_intent_id,
        &mut counters,
        &mut timing,
        &mut exchange,
        &mut seen_fill_count,
        &mut l2_book,
    )?;
    let final_snapshot = exchange.snapshot();
    let session_end = sparse_stream_message(
        &options.run_id,
        "session_end",
        "control",
        final_stream_seq,
        &final_snapshot.current_frame,
        final_snapshot.current_frame.exchange_ts_us,
        final_snapshot.current_frame.local_ts_us,
        serde_json::json!({
            "events_seen": events_seen,
        }),
    );
    let _ = send_sparse_strategy_message(
        &mut bridge,
        &mut logger,
        &options,
        &final_snapshot,
        session_end,
        false,
    );
    logger.emit(
        "run_end",
        &final_snapshot,
        "runner",
        serde_json::json!({
            "events_seen": events_seen,
            "pending_intents": pending_orders.len(),
            "counters": {
                "quote_events_seen": counters.quote_events_seen,
                "trade_events_seen": counters.trade_events_seen,
                "l2_batches_seen": counters.l2_batches_seen,
                "public_batches_sent": counters.public_batches_sent,
                "public_barriers_triggered": counters.public_barriers_triggered,
                "public_requeued_suffix_count": counters.public_requeued_suffix_count,
                "public_requeued_suffix_events": counters.public_requeued_suffix_events,
                "panel_frames_sent": counters.panel_frames_sent,
                "strategy_messages_received": counters.strategy_messages_received,
                "intents_created": counters.intents_created,
                "orders_submitted": counters.orders_submitted,
                "fills_created": counters.fills_created,
                "bridge_errors": counters.bridge_errors,
            },
            "progress": {
                "progress_events_emitted": timing.progress_events_emitted,
                "periodic_flush_count": timing.periodic_flush_count,
                "progress_interval_events": SPARSE_PROGRESS_INTERVAL_EVENTS,
                "flush_interval_events": SPARSE_FLUSH_INTERVAL_EVENTS,
            },
        }),
    )?;
    let event_count = logger.event_count();
    flush_sparse_logger(&mut logger, &mut timing)?;
    let _ = bridge.child.kill();
    let total_elapsed_wall_ms = run_started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    let event_rate_per_s = if total_elapsed_wall_ms > 0 {
        Some(events_seen as f64 / (total_elapsed_wall_ms as f64 / 1_000.0))
    } else {
        None
    };
    let final_snapshot = exchange.snapshot();
    let summary = SparsePythonStreamSummary {
        run_id: options.run_id,
        run_dir: path_string(&run_dir),
        source_label: options.source_label,
        determinism_mode: determinism_mode(options.clock_mode).to_string(),
        profile_manifest_hash: profile_manifest_hash_value,
        clock_mode: options.clock_mode,
        wall_latency_speedup: options.wall_latency_speedup,
        log_mode: options.log_mode,
        fill_model: options.fill_model,
        public_stream_mode: options.public_stream_mode,
        public_batch_size: options.public_batch_size,
        public_batches_sent: counters.public_batches_sent,
        public_barriers_triggered: counters.public_barriers_triggered,
        public_requeued_suffix_count: counters.public_requeued_suffix_count,
        public_requeued_suffix_events: counters.public_requeued_suffix_events,
        panel_frames_sent: counters.panel_frames_sent,
        arrival_mode: options.arrival_mode,
        events_seen,
        quote_events_seen: counters.quote_events_seen,
        trade_events_seen: counters.trade_events_seen,
        l2_batches_seen: counters.l2_batches_seen,
        final_stream_seq,
        final_quote_seq: final_snapshot.current_frame.seq,
        event_count,
        strategy_messages_received: counters.strategy_messages_received,
        intents_created: counters.intents_created,
        orders_submitted: counters.orders_submitted,
        fills_created: counters.fills_created,
        bridge_errors: counters.bridge_errors,
        bot_response_late_count: counters.bot_response_late_count,
        arrival_quote_lag_count: counters.arrival_quote_lag_count,
        arrival_stream_lag_count: counters.arrival_stream_lag_count,
        bridge_wall_latency_us_p50: percentile_u64(&counters.bridge_wall_latency_us_samples, 0.50),
        bridge_wall_latency_us_p95: percentile_u64(&counters.bridge_wall_latency_us_samples, 0.95),
        bridge_wall_latency_us_max: counters
            .bridge_wall_latency_us_samples
            .iter()
            .max()
            .copied(),
        target_miss_us_p50: percentile_u64(&counters.target_miss_us_samples, 0.50),
        target_miss_us_p95: percentile_u64(&counters.target_miss_us_samples, 0.95),
        target_miss_us_max: counters.target_miss_us_samples.iter().max().copied(),
        timing_ms: serde_json::json!({
            "total_elapsed_wall_ms": total_elapsed_wall_ms,
            "events_per_second": event_rate_per_s,
            "market_read_ms": timing.market_read_us / 1_000,
            "bridge_stdin_write_ms": bridge.stdin_write_us / 1_000,
            "bridge_stdout_drain_and_response_ms": timing.bridge_drain_and_response_us / 1_000,
            "order_submit_fill_ms": timing.order_submit_fill_us / 1_000,
            "barrier_requeue_ms": timing.barrier_requeue_us / 1_000,
            "progress_emit_ms": timing.progress_emit_us / 1_000,
            "logger_flush_ms": timing.logger_flush_us / 1_000,
            "strategy_messages_sent": bridge.messages_sent,
            "progress_events_emitted": timing.progress_events_emitted,
            "logger_flush_count": timing.periodic_flush_count,
            "progress_interval_events": SPARSE_PROGRESS_INTERVAL_EVENTS,
            "flush_interval_events": SPARSE_FLUSH_INTERVAL_EVENTS,
            "public_stream_mode": options.public_stream_mode,
            "public_batch_size": options.public_batch_size,
            "public_batch_max_span_us": options.public_batch_max_span_us,
            "public_batches_sent": counters.public_batches_sent,
            "public_barriers_triggered": counters.public_barriers_triggered,
            "public_requeued_suffix_count": counters.public_requeued_suffix_count,
            "public_requeued_suffix_events": counters.public_requeued_suffix_events,
            "panel_frames_sent": counters.panel_frames_sent,
            "quote_index_rows": quote_frames.len(),
            "batch_count": counters.public_batches_sent,
            "barrier_count": counters.public_barriers_triggered,
            "requeued_suffix_count": counters.public_requeued_suffix_count,
            "events_per_sec": event_rate_per_s,
            "bot_parse_time": null,
            "bridge_wait_time_ms": timing.bridge_drain_and_response_us / 1_000,
            "runner_fill_time_ms": timing.order_submit_fill_us / 1_000,
        }),
        final_account: final_snapshot.account,
    };
    logger.finalize()?;
    write_json(run_dir.join("summary.json"), &summary)?;
    Ok(summary)
}

pub fn run_runner_server(
    mut market_stream: CanonicalMarketStream,
    options: RunnerServerOptions,
) -> Result<RunnerServerSummary> {
    anyhow::ensure!(options.max_events > 0, "max_events must be >= 1");
    anyhow::ensure!(
        options.wall_latency_speedup >= 0.0 && options.wall_latency_speedup.is_finite(),
        "wall_latency_speedup must be finite and >= 0"
    );

    let run_dir = options.run_dir();
    fs::create_dir_all(&run_dir).with_context(|| format!("create {}", run_dir.display()))?;
    write_manifest(run_dir.join("manifest.json"), &options)?;

    let public_hub = StreamHub::bind(options.public_addr, "public")?;
    let private_hub = StreamHub::bind(options.private_addr, "private")?;
    let (ingress_tx, ingress_rx) = mpsc::channel::<ServerIngressLine>();
    spawn_order_ingress(options.order_addr, ingress_tx)?;

    let mut pending_start = VecDeque::new();
    let first_quote = loop {
        let event = market_stream
            .next()
            .transpose()?
            .context("market stream had no quote frame")?;
        match event {
            CanonicalMarketEvent::Quote { stream_seq, frame } => break (stream_seq, frame),
            other => pending_start.push_back(other),
        }
    };

    let mut logger = EventLogger::create(&run_dir, &options.run_id)?;
    let mut exchange =
        PaperExchange::from_current_frame(options.exchange_config.clone(), first_quote.1.clone())?;
    let mut l2_book = L2Book::new();
    let mut pending_orders = VecDeque::<StreamPendingOrder>::new();
    let mut observations = VecDeque::<SparseObservation>::new();
    let mut counters = ServerCounters::new();
    let mut next_intent_id = 1u64;
    let mut seen_fill_count = 0usize;
    let mut events_seen = 0usize;
    let mut final_stream_seq = first_quote.0;

    let first_snapshot = exchange.snapshot();
    let state_view = Arc::new(Mutex::new(server_state_view(
        &options,
        &first_snapshot,
        first_quote.0,
        &counters,
        0,
        false,
    )));
    if let Some(addr) = options.state_addr {
        spawn_state_query(addr, Arc::clone(&state_view))?;
    }
    if options.startup_wait_ms > 0 {
        thread::sleep(Duration::from_millis(options.startup_wait_ms));
    }
    logger.emit(
        "run_start",
        &first_snapshot,
        "runner_server",
        serde_json::json!({
            "protocol": "exchange_runner_server_tcp_v1",
            "source_label": options.source_label,
            "clock_mode": options.clock_mode,
            "latency_us": options.latency_us,
            "arrival_mode": options.arrival_mode,
            "wall_latency_speedup": options.wall_latency_speedup,
            "log_mode": options.log_mode,
            "fill_model": options.fill_model,
            "public_addr": options.public_addr,
            "private_addr": options.private_addr,
            "order_addr": options.order_addr,
            "state_addr": options.state_addr,
        }),
    )?;

    let session_start = sparse_stream_message(
        &options.run_id,
        "session_start",
        "control",
        first_quote.0,
        &first_snapshot.current_frame,
        first_snapshot.current_frame.exchange_ts_us,
        first_snapshot.current_frame.local_ts_us,
        serde_json::json!({
            "protocol": "exchange_runner_server_tcp_v1",
            "source_label": options.source_label,
            "latency_us": options.latency_us,
            "arrival_mode": options.arrival_mode,
            "clock_mode": options.clock_mode,
            "fill_model": options.fill_model,
            "log_mode": options.log_mode,
            "public_addr": options.public_addr,
            "private_addr": options.private_addr,
            "order_addr": options.order_addr,
        }),
    );
    public_hub.broadcast(&session_start)?;
    private_hub.broadcast(&server_account_snapshot_message(
        &options.run_id,
        &first_snapshot,
        first_quote.0,
        first_snapshot.current_frame.exchange_ts_us,
        first_snapshot.current_frame.local_ts_us,
    ))?;

    drain_server_ingress(
        &ingress_rx,
        &mut logger,
        &options,
        &exchange.snapshot(),
        &observations,
        &mut pending_orders,
        &private_hub,
        &mut next_intent_id,
        &mut counters,
    )?;
    submit_due_server_orders(
        &mut exchange,
        &mut pending_orders,
        &mut logger,
        &private_hub,
        &options,
        &mut seen_fill_count,
        &mut counters,
        &mut l2_book,
        first_quote.0,
        first_snapshot.current_frame.exchange_ts_us,
        first_snapshot.current_frame.local_ts_us,
    )?;

    let mut queued_events = pending_start;
    queued_events.push_back(CanonicalMarketEvent::Quote {
        stream_seq: first_quote.0,
        frame: first_quote.1,
    });

    while events_seen < options.max_events {
        let event = if let Some(event) = queued_events.pop_front() {
            Some(event)
        } else {
            market_stream.next().transpose()?
        };
        let Some(event) = event else {
            break;
        };
        final_stream_seq = event.stream_seq();
        match event {
            CanonicalMarketEvent::Quote { stream_seq, frame } => {
                if matches!(options.arrival_mode, OrderArrivalMode::Timer) {
                    submit_due_server_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &private_hub,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut l2_book,
                        stream_seq,
                        frame.exchange_ts_us,
                        frame.local_ts_us,
                    )?;
                }
                exchange.advance_to_frame(frame.clone());
                if matches!(options.arrival_mode, OrderArrivalMode::NextEvent) {
                    submit_due_server_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &private_hub,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut l2_book,
                        stream_seq,
                        frame.exchange_ts_us,
                        frame.local_ts_us,
                    )?;
                }
                let snapshot = exchange.snapshot();
                counters.quote_events_seen += 1;
                remember_observation(
                    &mut observations,
                    SparseObservation {
                        stream_seq,
                        local_ts_us: frame.local_ts_us,
                        sent_wall_us: now_us(),
                        quote: frame.clone(),
                    },
                );
                if should_emit_server_market_message(&public_hub, &options)? {
                    let message = sparse_stream_message(
                        &options.run_id,
                        "market_quote",
                        "public",
                        stream_seq,
                        &snapshot.current_frame,
                        frame.exchange_ts_us,
                        frame.local_ts_us,
                        serde_json::json!({ "quote": frame }),
                    );
                    send_server_stream_message(
                        &public_hub,
                        &mut logger,
                        &options,
                        &snapshot,
                        message,
                        true,
                    )?;
                }
                drain_server_ingress(
                    &ingress_rx,
                    &mut logger,
                    &options,
                    &snapshot,
                    &observations,
                    &mut pending_orders,
                    &private_hub,
                    &mut next_intent_id,
                    &mut counters,
                )?;
                submit_due_server_orders(
                    &mut exchange,
                    &mut pending_orders,
                    &mut logger,
                    &private_hub,
                    &options,
                    &mut seen_fill_count,
                    &mut counters,
                    &mut l2_book,
                    stream_seq,
                    frame.exchange_ts_us,
                    frame.local_ts_us,
                )?;
            }
            CanonicalMarketEvent::Trade { stream_seq, trade } => {
                let snapshot = exchange.snapshot();
                let exchange_ts_us = trade.exchange_ts_us;
                let local_ts_us = trade.local_ts_us;
                counters.trade_events_seen += 1;
                submit_due_server_orders(
                    &mut exchange,
                    &mut pending_orders,
                    &mut logger,
                    &private_hub,
                    &options,
                    &mut seen_fill_count,
                    &mut counters,
                    &mut l2_book,
                    stream_seq,
                    exchange_ts_us,
                    local_ts_us,
                )?;
                remember_observation(
                    &mut observations,
                    SparseObservation {
                        stream_seq,
                        local_ts_us,
                        sent_wall_us: now_us(),
                        quote: snapshot.current_frame.clone(),
                    },
                );
                if should_emit_server_market_message(&public_hub, &options)? {
                    let message = sparse_stream_message(
                        &options.run_id,
                        "market_trade",
                        "public",
                        stream_seq,
                        &snapshot.current_frame,
                        exchange_ts_us,
                        local_ts_us,
                        serde_json::json!({ "trade": trade }),
                    );
                    send_server_stream_message(
                        &public_hub,
                        &mut logger,
                        &options,
                        &snapshot,
                        message,
                        true,
                    )?;
                }
                drain_server_ingress(
                    &ingress_rx,
                    &mut logger,
                    &options,
                    &snapshot,
                    &observations,
                    &mut pending_orders,
                    &private_hub,
                    &mut next_intent_id,
                    &mut counters,
                )?;
                submit_due_server_orders(
                    &mut exchange,
                    &mut pending_orders,
                    &mut logger,
                    &private_hub,
                    &options,
                    &mut seen_fill_count,
                    &mut counters,
                    &mut l2_book,
                    stream_seq,
                    exchange_ts_us,
                    local_ts_us,
                )?;
            }
            CanonicalMarketEvent::L2Batch {
                stream_seq,
                local_ts_us,
                updates,
            } => {
                let snapshot = exchange.snapshot();
                let exchange_ts_us = updates
                    .first()
                    .map(|update| update.exchange_ts_us)
                    .unwrap_or(local_ts_us);
                if matches!(options.arrival_mode, OrderArrivalMode::Timer) {
                    submit_due_server_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &private_hub,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut l2_book,
                        stream_seq,
                        exchange_ts_us,
                        local_ts_us,
                    )?;
                }
                l2_book.apply_batch(&updates);
                counters.l2_batches_seen += 1;
                if matches!(options.arrival_mode, OrderArrivalMode::NextEvent) {
                    submit_due_server_orders(
                        &mut exchange,
                        &mut pending_orders,
                        &mut logger,
                        &private_hub,
                        &options,
                        &mut seen_fill_count,
                        &mut counters,
                        &mut l2_book,
                        stream_seq,
                        exchange_ts_us,
                        local_ts_us,
                    )?;
                }
                remember_observation(
                    &mut observations,
                    SparseObservation {
                        stream_seq,
                        local_ts_us,
                        sent_wall_us: now_us(),
                        quote: snapshot.current_frame.clone(),
                    },
                );
                if should_emit_server_market_message(&public_hub, &options)? {
                    let message = sparse_stream_message(
                        &options.run_id,
                        "market_l2_update",
                        "public",
                        stream_seq,
                        &snapshot.current_frame,
                        exchange_ts_us,
                        local_ts_us,
                        serde_json::json!({
                            "updates": updates,
                            "book": l2_book.view(),
                        }),
                    );
                    send_server_stream_message(
                        &public_hub,
                        &mut logger,
                        &options,
                        &snapshot,
                        message,
                        true,
                    )?;
                }
                drain_server_ingress(
                    &ingress_rx,
                    &mut logger,
                    &options,
                    &snapshot,
                    &observations,
                    &mut pending_orders,
                    &private_hub,
                    &mut next_intent_id,
                    &mut counters,
                )?;
                submit_due_server_orders(
                    &mut exchange,
                    &mut pending_orders,
                    &mut logger,
                    &private_hub,
                    &options,
                    &mut seen_fill_count,
                    &mut counters,
                    &mut l2_book,
                    stream_seq,
                    exchange_ts_us,
                    local_ts_us,
                )?;
            }
        }
        events_seen += 1;
        update_server_state(
            &state_view,
            &options,
            &exchange.snapshot(),
            final_stream_seq,
            &counters,
            pending_orders.len(),
            false,
        )?;
        if options.event_sleep_us > 0 {
            thread::sleep(Duration::from_micros(options.event_sleep_us));
        }
    }

    let final_snapshot = exchange.snapshot();
    update_server_state(
        &state_view,
        &options,
        &final_snapshot,
        final_stream_seq,
        &counters,
        pending_orders.len(),
        true,
    )?;
    let session_end = sparse_stream_message(
        &options.run_id,
        "session_end",
        "control",
        final_stream_seq,
        &final_snapshot.current_frame,
        final_snapshot.current_frame.exchange_ts_us,
        final_snapshot.current_frame.local_ts_us,
        serde_json::json!({ "events_seen": events_seen }),
    );
    let _ = public_hub.broadcast(&session_end);
    logger.emit(
        "run_end",
        &final_snapshot,
        "runner_server",
        serde_json::json!({
            "events_seen": events_seen,
            "pending_intents": pending_orders.len(),
            "counters": {
                "quote_events_seen": counters.quote_events_seen,
                "trade_events_seen": counters.trade_events_seen,
                "l2_batches_seen": counters.l2_batches_seen,
                "ingress_messages_received": counters.ingress_messages_received,
                "intents_created": counters.intents_created,
                "orders_submitted": counters.orders_submitted,
                "fills_created": counters.fills_created,
                "ingress_errors": counters.ingress_errors,
            },
        }),
    )?;
    let event_count = logger.event_count();
    logger.finalize()?;

    let summary = RunnerServerSummary {
        run_id: options.run_id,
        run_dir: path_string(&run_dir),
        source_label: options.source_label,
        clock_mode: options.clock_mode,
        wall_latency_speedup: options.wall_latency_speedup,
        log_mode: options.log_mode,
        fill_model: options.fill_model,
        arrival_mode: options.arrival_mode,
        public_addr: options.public_addr,
        private_addr: options.private_addr,
        order_addr: options.order_addr,
        state_addr: options.state_addr,
        events_seen,
        quote_events_seen: counters.quote_events_seen,
        trade_events_seen: counters.trade_events_seen,
        l2_batches_seen: counters.l2_batches_seen,
        final_stream_seq,
        final_quote_seq: final_snapshot.current_frame.seq,
        event_count,
        ingress_messages_received: counters.ingress_messages_received,
        intents_created: counters.intents_created,
        orders_submitted: counters.orders_submitted,
        fills_created: counters.fills_created,
        ingress_errors: counters.ingress_errors,
        final_account: final_snapshot.account,
    };
    write_json(run_dir.join("summary.json"), &summary)?;
    Ok(summary)
}

fn stream_message(
    run_id: &str,
    message_type: &str,
    channel: &str,
    snapshot: &ExchangeSnapshot,
    payload: serde_json::Value,
) -> serde_json::Value {
    serde_json::json!({
        "type": message_type,
        "channel": channel,
        "run_id": run_id,
        "replay_seq": snapshot.current_frame.seq,
        "observed_seq": snapshot.current_frame.seq,
        "cursor": snapshot.cursor,
        "exchange_ts_us": snapshot.current_frame.exchange_ts_us,
        "local_ts_us": snapshot.current_frame.local_ts_us,
        "payload": payload,
    })
}

fn sparse_stream_message(
    run_id: &str,
    message_type: &str,
    channel: &str,
    stream_seq: u64,
    quote: &MarketFrame,
    exchange_ts_us: u64,
    local_ts_us: u64,
    payload: serde_json::Value,
) -> serde_json::Value {
    serde_json::json!({
        "type": message_type,
        "channel": channel,
        "run_id": run_id,
        "seq": stream_seq,
        "observed_seq": stream_seq,
        "quote_seq": quote.seq,
        "exchange_ts_us": exchange_ts_us,
        "local_ts_us": local_ts_us,
        "payload": payload,
    })
}

fn send_sparse_strategy_message(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    message: serde_json::Value,
    is_market_event: bool,
) -> Result<()> {
    if matches!(options.log_mode, StreamLogMode::Full)
        || (is_market_event && matches!(options.log_mode, StreamLogMode::Audit))
    {
        logger.emit(
            "stream_message_sent",
            snapshot,
            "runner",
            serde_json::json!({
                "message": message.clone(),
            }),
        )?;
    }
    bridge.send_json(&message)
}

#[allow(clippy::too_many_arguments)]
fn dispatch_panel_sparse_decision_frame(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    stream_seq: u64,
    exchange_ts_us: u64,
    local_ts_us: u64,
    panel_frames: &mut VecDeque<PanelDecisionFrame>,
    public_batch: &mut SparsePublicBatch,
    observations: &mut VecDeque<SparseObservation>,
    pending_orders: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    exchange: &mut PaperExchange,
    seen_fill_count: &mut usize,
    l2_book: &mut L2Book,
) -> Result<()> {
    let Some(panel_frame) = panel_frames.pop_front() else {
        anyhow::bail!("panel_sparse_v1 decision_frame cache exhausted at stream_seq={stream_seq}");
    };
    anyhow::ensure!(
        panel_frame.local_ts_us == local_ts_us,
        "panel_sparse_v1 local_ts mismatch: frame={} stream={}",
        panel_frame.local_ts_us,
        local_ts_us
    );
    dispatch_panel_sparse_decision_frame_value(
        bridge,
        logger,
        options,
        snapshot,
        stream_seq,
        exchange_ts_us,
        local_ts_us,
        panel_frame,
        public_batch,
        observations,
        pending_orders,
        next_intent_id,
        counters,
        timing,
        exchange,
        seen_fill_count,
        l2_book,
    )
}

#[allow(clippy::too_many_arguments)]
fn dispatch_panel_sparse_decision_frame_value(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    stream_seq: u64,
    exchange_ts_us: u64,
    local_ts_us: u64,
    mut panel_frame: PanelDecisionFrame,
    public_batch: &mut SparsePublicBatch,
    observations: &mut VecDeque<SparseObservation>,
    pending_orders: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    exchange: &mut PaperExchange,
    seen_fill_count: &mut usize,
    l2_book: &mut L2Book,
) -> Result<()> {
    panel_frame.frame["observed_seq"] = serde_json::json!(stream_seq);
    panel_frame.frame["exchange_ts_us"] = serde_json::json!(panel_frame.exchange_ts_us);
    panel_frame.frame["local_ts_us"] = serde_json::json!(panel_frame.local_ts_us);
    panel_frame.frame["local_timestamp"] = serde_json::json!(panel_frame.local_ts_us);
    counters.panel_frames_sent += 1;
    let message = sparse_stream_message(
        &options.run_id,
        "market_decision_frame",
        "public",
        stream_seq,
        &snapshot.current_frame,
        exchange_ts_us,
        local_ts_us,
        serde_json::json!({
            "schema_id": public_stream_mode_name(options.public_stream_mode),
            "decision_frame": panel_frame.frame,
            "audit": {
                "source": "decision_frame_v1_parquet_cache",
                "event_index": panel_frame.event_index,
                "observed_seq": stream_seq,
                "observed_local_ts_us": local_ts_us,
                "quote_seq": snapshot.current_frame.seq,
                "execution_quote": {
                    "seq": snapshot.current_frame.seq,
                    "exchange_ts_us": snapshot.current_frame.exchange_ts_us,
                    "local_ts_us": snapshot.current_frame.local_ts_us,
                    "bid": snapshot.current_frame.bid,
                    "ask": snapshot.current_frame.ask,
                    "mid": snapshot.current_frame.mid,
                    "spread_bps": snapshot.current_frame.spread_bps(),
                },
                "builder_version": options
                    .panel_frame_cache_manifest
                    .as_ref()
                    .and_then(|manifest| manifest.get("builder_version"))
                    .cloned(),
                "schema_version": options
                    .panel_frame_cache_manifest
                    .as_ref()
                    .and_then(|manifest| manifest.get("schema_version"))
                    .cloned(),
                "field_hash_sha256": options
                    .panel_frame_cache_manifest
                    .as_ref()
                    .and_then(|manifest| manifest.get("field_hash_sha256"))
                    .cloned(),
                "cache_file_sha256": options
                    .panel_frame_cache_manifest
                    .as_ref()
                    .and_then(|manifest| manifest.get("cache_file_sha256"))
                    .cloned(),
                "data_manifest_hash": options
                    .panel_frame_cache_manifest
                    .as_ref()
                    .and_then(|manifest| manifest.get("data_manifest_hash"))
                    .cloned(),
                "source_canonical": options
                    .panel_frame_cache_manifest
                    .as_ref()
                    .and_then(|manifest| manifest.get("source_canonical"))
                    .cloned(),
            },
        }),
    );
    dispatch_sparse_public_message(
        bridge,
        logger,
        options,
        snapshot,
        message,
        stream_seq,
        exchange_ts_us,
        local_ts_us,
        public_batch,
        observations,
        pending_orders,
        next_intent_id,
        counters,
        timing,
        exchange,
        seen_fill_count,
        l2_book,
    )
}

#[allow(clippy::too_many_arguments)]
fn dispatch_sparse_public_message(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    message: serde_json::Value,
    stream_seq: u64,
    exchange_ts_us: u64,
    local_ts_us: u64,
    public_batch: &mut SparsePublicBatch,
    observations: &mut VecDeque<SparseObservation>,
    pending_orders: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    exchange: &mut PaperExchange,
    seen_fill_count: &mut usize,
    l2_book: &mut L2Book,
) -> Result<()> {
    match options.public_stream_mode {
        SparsePublicStreamMode::StrictEvent => {
            send_sparse_strategy_message(bridge, logger, options, snapshot, message, true)?;
            drain_sparse_strategy_messages(
                bridge,
                logger,
                options,
                snapshot,
                observations,
                pending_orders,
                next_intent_id,
                counters,
                timing,
            )?;
            submit_due_sparse_orders(
                exchange,
                pending_orders,
                logger,
                bridge,
                options,
                seen_fill_count,
                counters,
                timing,
                l2_book,
                stream_seq,
                exchange_ts_us,
                local_ts_us,
            )
        }
        SparsePublicStreamMode::BatchedPublicV1
        | SparsePublicStreamMode::BatchedPublicBarrierV1
        | SparsePublicStreamMode::PanelSparseV1
        | SparsePublicStreamMode::PanelSparseFastClockV1 => {
            public_batch.push(message, stream_seq, exchange_ts_us, local_ts_us);
            if public_batch
                .should_flush(options.public_batch_size, options.public_batch_max_span_us)
            {
                flush_sparse_public_batch(
                    bridge,
                    logger,
                    options,
                    snapshot,
                    public_batch,
                    observations,
                    pending_orders,
                    next_intent_id,
                    counters,
                    timing,
                    exchange,
                    seen_fill_count,
                    l2_book,
                )?;
            }
            Ok(())
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn flush_sparse_public_batch_if_due(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    public_batch: &mut SparsePublicBatch,
    observations: &mut VecDeque<SparseObservation>,
    pending_orders: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    exchange: &mut PaperExchange,
    seen_fill_count: &mut usize,
    l2_book: &mut L2Book,
    arrival_local_ts_us: u64,
) -> Result<()> {
    if matches!(
        options.public_stream_mode,
        SparsePublicStreamMode::BatchedPublicV1
            | SparsePublicStreamMode::BatchedPublicBarrierV1
            | SparsePublicStreamMode::PanelSparseV1
            | SparsePublicStreamMode::PanelSparseFastClockV1
    ) && !public_batch.is_empty()
        && pending_orders
            .front()
            .is_some_and(|intent| intent.arrival_local_ts_us <= arrival_local_ts_us)
    {
        flush_sparse_public_batch(
            bridge,
            logger,
            options,
            snapshot,
            public_batch,
            observations,
            pending_orders,
            next_intent_id,
            counters,
            timing,
            exchange,
            seen_fill_count,
            l2_book,
        )?;
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn flush_sparse_public_batch(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    public_batch: &mut SparsePublicBatch,
    observations: &mut VecDeque<SparseObservation>,
    pending_orders: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    exchange: &mut PaperExchange,
    seen_fill_count: &mut usize,
    l2_book: &mut L2Book,
) -> Result<()> {
    if public_batch.is_empty() {
        return Ok(());
    }
    if matches!(
        options.public_stream_mode,
        SparsePublicStreamMode::BatchedPublicBarrierV1
            | SparsePublicStreamMode::PanelSparseV1
            | SparsePublicStreamMode::PanelSparseFastClockV1
    ) {
        return flush_sparse_public_barrier_batch(
            bridge,
            logger,
            options,
            snapshot,
            public_batch,
            observations,
            pending_orders,
            next_intent_id,
            counters,
            timing,
            exchange,
            seen_fill_count,
            l2_book,
        );
    }
    let sent_wall_us = now_us();
    let seq_start = public_batch.seq_start.unwrap_or(public_batch.seq_end);
    let seq_end = public_batch.seq_end;
    mark_observations_sent_wall_us(observations, seq_start, seq_end, sent_wall_us);
    let items = std::mem::take(&mut public_batch.items);
    let event_count = items.len();
    let events: Vec<_> = items.into_iter().map(|item| item.message).collect();
    let exchange_ts_us = public_batch.exchange_ts_us;
    let local_ts_us = public_batch.local_ts_us;
    let batch_message = sparse_stream_message(
        &options.run_id,
        "market_batch",
        "public",
        seq_end,
        &snapshot.current_frame,
        exchange_ts_us,
        local_ts_us,
        serde_json::json!({
            "schema_id": "batched_public_v1",
            "seq_start": seq_start,
            "seq_end": seq_end,
            "event_count": event_count,
            "local_ts_start_us": public_batch.local_ts_start_us,
            "local_ts_end_us": local_ts_us,
            "events": events,
        }),
    );
    public_batch.seq_start = None;
    counters.public_batches_sent += 1;
    send_sparse_strategy_message(bridge, logger, options, snapshot, batch_message, true)?;
    drain_sparse_strategy_messages(
        bridge,
        logger,
        options,
        snapshot,
        observations,
        pending_orders,
        next_intent_id,
        counters,
        timing,
    )?;
    submit_due_sparse_orders(
        exchange,
        pending_orders,
        logger,
        bridge,
        options,
        seen_fill_count,
        counters,
        timing,
        l2_book,
        seq_end,
        exchange_ts_us,
        local_ts_us,
    )
}

#[allow(clippy::too_many_arguments)]
fn flush_sparse_public_barrier_batch(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    public_batch: &mut SparsePublicBatch,
    observations: &mut VecDeque<SparseObservation>,
    pending_orders: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    exchange: &mut PaperExchange,
    seen_fill_count: &mut usize,
    l2_book: &mut L2Book,
) -> Result<()> {
    let items_vec = std::mem::take(&mut public_batch.items);
    public_batch.seq_start = None;
    let mut items: VecDeque<SparsePublicBatchItem> = VecDeque::from(items_vec);
    let batch_schema_id = match options.public_stream_mode {
        SparsePublicStreamMode::PanelSparseV1 => "panel_sparse_v1",
        SparsePublicStreamMode::PanelSparseFastClockV1 => "panel_sparse_fast_clock_v1",
        _ => "batched_public_barrier_v1",
    };
    while !items.is_empty() {
        let chunk_len = barrier_chunk_len(&items, pending_orders);
        let chunk: Vec<SparsePublicBatchItem> = items.iter().take(chunk_len).cloned().collect();
        let Some(last_chunk_item) = chunk.last().cloned() else {
            break;
        };
        let outcome = send_sparse_public_batch_items(
            bridge,
            logger,
            options,
            snapshot,
            observations,
            counters,
            timing,
            batch_schema_id,
            &chunk,
            pending_orders,
            next_intent_id,
        )?;
        let mut consumed_count = chunk_len;
        if let Some(consumed_seq) = outcome.barrier_consumed_seq {
            let _timer = ScopeTimer::new(&mut timing.barrier_requeue_us);
            let consumed_idx = chunk
                .iter()
                .position(|item| item.stream_seq == consumed_seq)
                .with_context(|| {
                    format!(
                        "barrier consumed_seq={} was not present in batch chunk {}..{}",
                        consumed_seq,
                        chunk.first().map(|item| item.stream_seq).unwrap_or(0),
                        last_chunk_item.stream_seq
                    )
                })?;
            consumed_count = consumed_idx + 1;
            counters.public_barriers_triggered += 1;
            let suffix_in_chunk = chunk_len.saturating_sub(consumed_count);
            if suffix_in_chunk > 0 {
                counters.public_requeued_suffix_count += 1;
                counters.public_requeued_suffix_events = counters
                    .public_requeued_suffix_events
                    .saturating_add(suffix_in_chunk as u64);
            }
            logger.emit(
                "public_batch_barrier",
                snapshot,
                "runner",
                serde_json::json!({
                    "schema_id": batch_schema_id,
                    "consumed_seq": consumed_seq,
                    "consumed_local_ts_us": outcome.barrier_consumed_local_ts_us,
                    "message_type": outcome.barrier_message_type,
                    "chunk_seq_start": chunk.first().map(|item| item.stream_seq),
                    "chunk_seq_end": last_chunk_item.stream_seq,
                    "chunk_event_count": chunk_len,
                    "consumed_event_count": consumed_count,
                    "requeued_suffix_events": suffix_in_chunk,
                }),
            )?;
        }
        let last_consumed_item = chunk
            .get(consumed_count.saturating_sub(1))
            .cloned()
            .unwrap_or(last_chunk_item);
        for _ in 0..consumed_count {
            let _ = items.pop_front();
        }
        submit_due_sparse_orders(
            exchange,
            pending_orders,
            logger,
            bridge,
            options,
            seen_fill_count,
            counters,
            timing,
            l2_book,
            last_consumed_item.stream_seq,
            last_consumed_item.exchange_ts_us,
            last_consumed_item.local_ts_us,
        )?;
    }
    Ok(())
}

fn barrier_chunk_len(
    items: &VecDeque<SparsePublicBatchItem>,
    pending_orders: &VecDeque<StreamPendingOrder>,
) -> usize {
    if let Some(intent) = pending_orders.front() {
        if let Some(idx) = items
            .iter()
            .position(|item| item.local_ts_us >= intent.arrival_local_ts_us)
        {
            return idx + 1;
        }
    }
    items.len()
}

#[allow(clippy::too_many_arguments)]
fn send_sparse_public_batch_items(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    observations: &mut VecDeque<SparseObservation>,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    schema_id: &str,
    items: &[SparsePublicBatchItem],
    pending_orders: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
) -> Result<SparseDrainOutcome> {
    let first = items
        .first()
        .context("send_sparse_public_batch_items received empty items")?;
    let last = items
        .last()
        .context("send_sparse_public_batch_items received empty items")?;
    let sent_wall_us = now_us();
    mark_observations_sent_wall_us(
        observations,
        first.stream_seq,
        last.stream_seq,
        sent_wall_us,
    );
    let events: Vec<_> = items.iter().map(|item| item.message.clone()).collect();
    let batch_message = sparse_stream_message(
        &options.run_id,
        "market_batch",
        "public",
        last.stream_seq,
        &snapshot.current_frame,
        last.exchange_ts_us,
        last.local_ts_us,
        serde_json::json!({
            "schema_id": schema_id,
            "seq_start": first.stream_seq,
            "seq_end": last.stream_seq,
            "event_count": events.len(),
            "local_ts_start_us": first.local_ts_us,
            "local_ts_end_us": last.local_ts_us,
            "events": events,
        }),
    );
    counters.public_batches_sent += 1;
    send_sparse_strategy_message(bridge, logger, options, snapshot, batch_message, true)?;
    if matches!(
        schema_id,
        "batched_public_barrier_v1" | "panel_sparse_v1" | "panel_sparse_fast_clock_v1"
    ) {
        drain_sparse_strategy_messages_until_batch_barrier(
            bridge,
            logger,
            options,
            snapshot,
            observations,
            pending_orders,
            next_intent_id,
            counters,
            timing,
        )
    } else {
        drain_sparse_strategy_messages(
            bridge,
            logger,
            options,
            snapshot,
            observations,
            pending_orders,
            next_intent_id,
            counters,
            timing,
        )
    }
}

fn flush_sparse_logger(logger: &mut EventLogger, timing: &mut SparseTiming) -> Result<()> {
    let started = Instant::now();
    let result = logger.flush();
    timing.logger_flush_us = timing.logger_flush_us.saturating_add(elapsed_us(started));
    timing.periodic_flush_count += 1;
    result
}

fn emit_sparse_progress(
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    counters: &SparseCounters,
    timing: &mut SparseTiming,
    events_seen: usize,
    final_stream_seq: u64,
    pending_intents: usize,
    run_started: Instant,
) -> Result<()> {
    timing.progress_events_emitted += 1;
    let _timer = ScopeTimer::new(&mut timing.progress_emit_us);
    let elapsed_wall_ms = run_started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    let event_rate_per_s = if elapsed_wall_ms > 0 {
        Some(events_seen as f64 / (elapsed_wall_ms as f64 / 1_000.0))
    } else {
        None
    };
    let payload = serde_json::json!({
        "protocol": "exchange_sparse_stream_v1",
        "source_label": options.source_label,
        "events_seen": events_seen,
        "max_events": options.max_events,
        "final_stream_seq": final_stream_seq,
        "pending_intents": pending_intents,
        "quote_events_seen": counters.quote_events_seen,
        "trade_events_seen": counters.trade_events_seen,
        "l2_batches_seen": counters.l2_batches_seen,
        "public_batches_sent": counters.public_batches_sent,
        "public_barriers_triggered": counters.public_barriers_triggered,
        "public_requeued_suffix_count": counters.public_requeued_suffix_count,
        "public_requeued_suffix_events": counters.public_requeued_suffix_events,
        "panel_frames_sent": counters.panel_frames_sent,
        "strategy_messages_received": counters.strategy_messages_received,
        "intents_created": counters.intents_created,
        "orders_submitted": counters.orders_submitted,
        "fills_created": counters.fills_created,
        "bridge_errors": counters.bridge_errors,
        "elapsed_wall_ms": elapsed_wall_ms,
        "event_rate_per_s": event_rate_per_s,
        "progress_interval_events": SPARSE_PROGRESS_INTERVAL_EVENTS,
        "flush_interval_events": SPARSE_FLUSH_INTERVAL_EVENTS,
    });
    logger.emit("run_progress", snapshot, "runner", payload.clone())?;
    eprintln!(
        "{}",
        serde_json::to_string(&serde_json::json!({
            "type": "run_progress",
            "run_id": options.run_id,
            "events_seen": events_seen,
            "max_events": options.max_events,
            "orders_submitted": counters.orders_submitted,
            "fills_created": counters.fills_created,
            "elapsed_wall_ms": elapsed_wall_ms,
            "event_rate_per_s": event_rate_per_s,
        }))?
    );
    Ok(())
}

fn send_sparse_account_snapshot(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
) -> Result<()> {
    send_sparse_account_snapshot_at(
        bridge,
        logger,
        options,
        snapshot,
        snapshot.current_frame.seq,
        snapshot.current_frame.exchange_ts_us,
        snapshot.current_frame.local_ts_us,
    )
}

fn send_sparse_account_snapshot_at(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    stream_seq: u64,
    exchange_ts_us: u64,
    local_ts_us: u64,
) -> Result<()> {
    let message = sparse_stream_message(
        &options.run_id,
        "account_snapshot",
        "private",
        stream_seq,
        &snapshot.current_frame,
        exchange_ts_us,
        local_ts_us,
        serde_json::json!({
            "account": snapshot.account,
            "open_orders": snapshot.open_orders,
            "order_count": snapshot.order_count,
            "fill_count": snapshot.fill_count,
        }),
    );
    send_sparse_strategy_message(bridge, logger, options, snapshot, message, false)
}

fn server_account_snapshot_message(
    run_id: &str,
    snapshot: &ExchangeSnapshot,
    stream_seq: u64,
    exchange_ts_us: u64,
    local_ts_us: u64,
) -> serde_json::Value {
    sparse_stream_message(
        run_id,
        "account_snapshot",
        "private",
        stream_seq,
        &snapshot.current_frame,
        exchange_ts_us,
        local_ts_us,
        serde_json::json!({
            "account": snapshot.account,
            "open_orders": snapshot.open_orders,
            "order_count": snapshot.order_count,
            "fill_count": snapshot.fill_count,
        }),
    )
}

fn send_server_stream_message(
    hub: &StreamHub,
    logger: &mut EventLogger,
    options: &RunnerServerOptions,
    snapshot: &ExchangeSnapshot,
    message: serde_json::Value,
    is_market_event: bool,
) -> Result<()> {
    if matches!(options.log_mode, StreamLogMode::Full)
        || (is_market_event && matches!(options.log_mode, StreamLogMode::Audit))
    {
        logger.emit(
            "stream_message_sent",
            snapshot,
            "runner_server",
            serde_json::json!({ "message": message.clone() }),
        )?;
    }
    hub.broadcast(&message)
}

fn should_emit_server_market_message(
    hub: &StreamHub,
    options: &RunnerServerOptions,
) -> Result<bool> {
    if matches!(options.log_mode, StreamLogMode::Audit | StreamLogMode::Full) {
        return Ok(true);
    }
    hub.has_clients()
}

fn order_arrival_local_ts(
    mode: OrderArrivalMode,
    target_arrival_local_ts_us: u64,
    trigger_local_ts_us: u64,
) -> u64 {
    match mode {
        OrderArrivalMode::Timer => target_arrival_local_ts_us,
        OrderArrivalMode::NextEvent => trigger_local_ts_us,
    }
}

fn order_arrival_exchange_ts(
    mode: OrderArrivalMode,
    current_quote: &MarketFrame,
    trigger_exchange_ts_us: u64,
) -> u64 {
    match mode {
        OrderArrivalMode::Timer => current_quote.exchange_ts_us,
        OrderArrivalMode::NextEvent => trigger_exchange_ts_us,
    }
}

fn order_arrival_time_source(mode: OrderArrivalMode) -> &'static str {
    match mode {
        OrderArrivalMode::Timer => "virtual_timer_last_known_book",
        OrderArrivalMode::NextEvent => "next_market_event_stress",
    }
}

fn drain_sparse_strategy_messages(
    bridge: &PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    observations: &VecDeque<SparseObservation>,
    pending: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
) -> Result<SparseDrainOutcome> {
    let _timer = ScopeTimer::new(&mut timing.bridge_drain_and_response_us);
    let mut outcome = SparseDrainOutcome::default();
    let lines_result = match options.clock_mode {
        StreamClockMode::DeterministicStep => {
            bridge.drain_lines_after_settle(Duration::from_millis(1))
        }
        StreamClockMode::AcceleratedAsync => bridge.drain_lines(),
    };
    let lines = match lines_result {
        Ok(lines) => lines,
        Err(error) => {
            handle_sparse_bridge_error(error, logger, options, snapshot, counters, "drain_stdout")?;
            return Ok(outcome);
        }
    };
    for line in lines {
        handle_sparse_strategy_line(
            line,
            logger,
            options,
            snapshot,
            observations,
            pending,
            next_intent_id,
            counters,
            &mut outcome,
        )?;
    }
    Ok(outcome)
}

#[allow(clippy::too_many_arguments)]
fn drain_sparse_strategy_messages_until_batch_barrier(
    bridge: &PythonBridge,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    observations: &VecDeque<SparseObservation>,
    pending: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
) -> Result<SparseDrainOutcome> {
    let _timer = ScopeTimer::new(&mut timing.bridge_drain_and_response_us);
    let mut outcome = SparseDrainOutcome::default();
    loop {
        let line = match bridge.read_line() {
            Ok(line) => line,
            Err(error) => {
                handle_sparse_bridge_error(
                    error,
                    logger,
                    options,
                    snapshot,
                    counters,
                    "read_batch_barrier",
                )?;
                return Ok(outcome);
            }
        };
        handle_sparse_strategy_line(
            line,
            logger,
            options,
            snapshot,
            observations,
            pending,
            next_intent_id,
            counters,
            &mut outcome,
        )?;
        if outcome.batch_done || outcome.barrier_consumed_seq.is_some() {
            break;
        }
    }
    Ok(outcome)
}

#[allow(clippy::too_many_arguments)]
fn handle_sparse_strategy_line(
    line: String,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    observations: &VecDeque<SparseObservation>,
    pending: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
    outcome: &mut SparseDrainOutcome,
) -> Result<()> {
    let response_value = serde_json::from_str::<serde_json::Value>(&line)
        .unwrap_or_else(|_| serde_json::json!({ "raw": line }));
    let response = match serde_json::from_str::<StrategyResponse>(&line) {
        Ok(response) => response,
        Err(error) => {
            if matches!(options.log_mode, StreamLogMode::Audit | StreamLogMode::Full) {
                logger.emit(
                    "strategy_message_received",
                    snapshot,
                    "strategy_bridge",
                    serde_json::json!({
                        "parse_ok": false,
                        "line": response_value,
                    }),
                )?;
            }
            handle_sparse_bridge_error(
                anyhow::anyhow!("invalid strategy response: {error}"),
                logger,
                options,
                snapshot,
                counters,
                "parse_response",
            )?;
            return Ok(());
        }
    };
    counters.strategy_messages_received += 1;
    if matches!(options.log_mode, StreamLogMode::Audit | StreamLogMode::Full)
        || matches!(
            response.message_type.as_str(),
            "submit_order" | "submit_orders" | "cancel_order"
        )
    {
        logger.emit(
            "strategy_message_received",
            snapshot,
            "strategy_bridge",
            serde_json::json!({
                "parse_ok": true,
                "response": response_value,
            }),
        )?;
    }
    outcome.observe_response(options, &response);
    handle_sparse_strategy_response(
        response,
        logger,
        options,
        snapshot,
        observations,
        pending,
        next_intent_id,
        counters,
    )
}

fn handle_sparse_strategy_response(
    response: StrategyResponse,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    observations: &VecDeque<SparseObservation>,
    pending: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut SparseCounters,
) -> Result<()> {
    match response.message_type.as_str() {
        "batch_done" => {
            if matches!(options.log_mode, StreamLogMode::Full) {
                logger.emit(
                    "strategy_batch_done",
                    snapshot,
                    "strategy_bridge",
                    serde_json::json!({
                        "observed_seq": response.observed_seq,
                        "observed_local_ts_us": response.observed_local_ts_us,
                        "consumed_seq": response.consumed_seq,
                        "consumed_local_ts_us": response.consumed_local_ts_us,
                    }),
                )?;
            }
            Ok(())
        }
        "heartbeat" | "hold" => {
            emit_capacity_decision(
                logger,
                snapshot,
                "python_strategy",
                response.observed_seq,
                None,
                response.reason.as_deref(),
                response.feature_snapshot.clone(),
                response.shadow_signal.clone(),
            )?;
            if let Some(feature_snapshot) = response.feature_snapshot.clone() {
                logger.emit(
                    "strategy_feature_checkpoint",
                    snapshot,
                    "python_strategy",
                    serde_json::json!({
                        "message_type": response.message_type.clone(),
                        "observed_seq": response.observed_seq,
                        "reason": response.reason.clone(),
                        "feature_snapshot": feature_snapshot,
                        "shadow_signal": response.shadow_signal.clone(),
                    }),
                )?;
            }
            if matches!(options.log_mode, StreamLogMode::Full) {
                logger.emit(
                    "strategy_heartbeat",
                    snapshot,
                    "strategy_bridge",
                    serde_json::json!({
                        "observed_seq": response.observed_seq,
                        "reason": response.reason,
                    }),
                )?;
            }
            Ok(())
        }
        "submit_order" | "submit_orders" => {
            let requests = if response.message_type == "submit_orders" {
                if response.orders.is_empty() {
                    return handle_sparse_bridge_error(
                        anyhow::anyhow!("submit_orders response did not include orders"),
                        logger,
                        options,
                        snapshot,
                        counters,
                        "submit_orders",
                    );
                }
                response.orders.clone()
            } else {
                let Some(request) = response.order.clone() else {
                    return handle_sparse_bridge_error(
                        anyhow::anyhow!("submit_order response did not include order fields"),
                        logger,
                        options,
                        snapshot,
                        counters,
                        "submit_order",
                    );
                };
                vec![request]
            };
            for request in requests {
                let observed_seq = response
                    .observed_seq
                    .or_else(|| observations.back().map(|obs| obs.stream_seq))
                    .context("submit_order missing observed_seq and no observation is available")?;
                let Some(observed) = find_observation(observations, observed_seq) else {
                    logger.emit(
                        "order_reject",
                        snapshot,
                        "runner",
                        serde_json::json!({
                            "reason": "observed_seq is not in retained observation window",
                            "observed_seq": observed_seq,
                        }),
                    )?;
                    continue;
                };
                if response
                    .observed_local_ts_us
                    .is_some_and(|ts| ts != observed.local_ts_us)
                {
                    logger.emit(
                        "strategy_observed_ts_mismatch",
                        snapshot,
                        "strategy_bridge",
                        serde_json::json!({
                            "observed_seq": observed_seq,
                            "response_observed_local_ts_us": response.observed_local_ts_us,
                            "runner_observed_local_ts_us": observed.local_ts_us,
                        }),
                    )?;
                }
                let mut order = request.into_new_order()?;
                if order.kind != OrderKind::Market || order.tif != TimeInForce::Ioc {
                    logger.emit(
                        "order_reject",
                        snapshot,
                        "runner",
                        serde_json::json!({
                            "reason": "sparse_stream_v1 only accepts taker market IOC orders",
                            "order": order,
                        }),
                    )?;
                    continue;
                }
                if order.client_order_id.is_none() {
                    order.client_order_id = Some(format!("sparse-intent-{}", next_intent_id));
                }
                let bridge_wall_latency_us = now_us().saturating_sub(observed.sent_wall_us);
                let bridge_wall_latency_ms = bridge_wall_latency_us / 1_000;
                let wall_latency_virtual_staleness_us = match options.clock_mode {
                    StreamClockMode::DeterministicStep => 0,
                    StreamClockMode::AcceleratedAsync => {
                        (bridge_wall_latency_us as f64 * options.wall_latency_speedup)
                            .round()
                            .clamp(0.0, u64::MAX as f64) as u64
                    }
                };
                let effective_latency_us = options
                    .latency_us
                    .saturating_add(wall_latency_virtual_staleness_us);
                let target_arrival_local_ts_us =
                    observed.local_ts_us.saturating_add(effective_latency_us);
                let deterministic_arrival_observation = if matches!(
                    (options.clock_mode, options.arrival_mode),
                    (StreamClockMode::DeterministicStep, OrderArrivalMode::Timer)
                ) {
                    find_arrival_observation(observations, target_arrival_local_ts_us)
                } else {
                    None
                };
                let current_observation_seq = observations.back().map(|obs| obs.stream_seq);
                if deterministic_arrival_observation
                    .as_ref()
                    .zip(current_observation_seq)
                    .is_some_and(|(arrival, current_seq)| arrival.stream_seq < current_seq)
                {
                    counters.bot_response_late_count += 1;
                }
                counters
                    .bridge_wall_latency_us_samples
                    .push(bridge_wall_latency_us);
                let intent = StreamPendingOrder {
                    intent_id: *next_intent_id,
                    observed_seq,
                    observed_local_ts_us: observed.local_ts_us,
                    arrival_local_ts_us: target_arrival_local_ts_us,
                    arrival_quote_override: deterministic_arrival_observation
                        .as_ref()
                        .map(|obs| obs.quote.clone()),
                    arrival_stream_seq_override: deterministic_arrival_observation
                        .as_ref()
                        .map(|obs| obs.stream_seq),
                    effective_latency_us,
                    wall_latency_virtual_staleness_us,
                    bridge_wall_latency_us,
                    reason: response
                        .reason
                        .clone()
                        .unwrap_or_else(|| "sparse_python_strategy_submit_order".to_string()),
                    bridge_wall_latency_ms,
                    feature_snapshot: response.feature_snapshot.clone(),
                    shadow_signal: response.shadow_signal.clone(),
                    observed_quote: observed.quote.clone(),
                    order,
                };
                *next_intent_id += 1;
                counters.intents_created += 1;
                if should_emit_capacity_decision_for_order(&intent.shadow_signal, &intent.order) {
                    emit_capacity_decision(
                        logger,
                        snapshot,
                        "python_strategy",
                        Some(intent.observed_seq),
                        Some(intent.intent_id),
                        Some(intent.reason.as_str()),
                        intent.feature_snapshot.clone(),
                        intent.shadow_signal.clone(),
                    )?;
                }
                logger.emit(
                    "order_intent",
                    snapshot,
                    "python_strategy",
                    serde_json::json!({
                        "intent": intent.clone(),
                        "feature_snapshot": intent.feature_snapshot.clone(),
                        "shadow_signal": intent.shadow_signal.clone(),
                    }),
                )?;
                logger.emit(
                    "order_scheduled",
                    snapshot,
                    "runner",
                    serde_json::json!({
                        "intent_id": intent.intent_id,
                        "observed_seq": intent.observed_seq,
                        "observed_local_ts_us": intent.observed_local_ts_us,
                        "arrival_local_ts_us": intent.arrival_local_ts_us,
                        "latency_us": options.latency_us,
                        "arrival_mode": options.arrival_mode,
                        "effective_latency_us": intent.effective_latency_us,
                        "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                        "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                        "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                    }),
                )?;
                pending.push_back(intent);
            }
            Ok(())
        }
        "cancel_order" => {
            let cancel_idx = pending.iter().position(|intent| {
                response
                    .cancel_intent_id
                    .is_some_and(|intent_id| intent_id == intent.intent_id)
                    || response
                        .cancel_client_order_id
                        .as_ref()
                        .is_some_and(|client_id| {
                            intent.order.client_order_id.as_ref() == Some(client_id)
                        })
            });
            match cancel_idx.and_then(|idx| pending.remove(idx)) {
                Some(intent) => logger.emit(
                    "cancel_ack",
                    snapshot,
                    "runner",
                    serde_json::json!({
                        "intent": intent,
                        "reason": response.reason,
                    }),
                ),
                None => logger.emit(
                    "cancel_reject",
                    snapshot,
                    "runner",
                    serde_json::json!({
                        "reason": response.reason.unwrap_or_else(|| {
                            "no matching pending taker IOC intent".to_string()
                        }),
                        "cancel_intent_id": response.cancel_intent_id,
                        "cancel_order_id": response.cancel_order_id,
                        "cancel_client_order_id": response.cancel_client_order_id,
                    }),
                ),
            }
        }
        other => handle_sparse_bridge_error(
            anyhow::anyhow!("unsupported strategy response type: {other}"),
            logger,
            options,
            snapshot,
            counters,
            "response_type",
        ),
    }
}

fn submit_due_sparse_orders(
    exchange: &mut PaperExchange,
    pending: &mut VecDeque<StreamPendingOrder>,
    logger: &mut EventLogger,
    bridge: &mut PythonBridge,
    options: &SparsePythonStreamOptions,
    seen_fill_count: &mut usize,
    counters: &mut SparseCounters,
    timing: &mut SparseTiming,
    l2_book: &mut L2Book,
    arrival_stream_seq: u64,
    arrival_exchange_ts_us: u64,
    arrival_local_ts_us: u64,
) -> Result<()> {
    let _timer = ScopeTimer::new(&mut timing.order_submit_fill_us);
    while pending
        .front()
        .is_some_and(|intent| intent.arrival_local_ts_us <= arrival_local_ts_us)
    {
        let intent = pending.pop_front().expect("pending front checked");
        let trigger_snapshot = exchange.snapshot();
        let arrival_quote = intent
            .arrival_quote_override
            .clone()
            .unwrap_or_else(|| trigger_snapshot.current_frame.clone());
        let effective_arrival_stream_seq = intent
            .arrival_stream_seq_override
            .unwrap_or(arrival_stream_seq);
        let virtual_event_stream_seq = effective_arrival_stream_seq;
        let trigger_local_ts_us = arrival_local_ts_us;
        let trigger_exchange_ts_us = arrival_exchange_ts_us;
        let arrival_local_ts_us = order_arrival_local_ts(
            options.arrival_mode,
            intent.arrival_local_ts_us,
            trigger_local_ts_us,
        );
        let arrival_exchange_ts_us =
            order_arrival_exchange_ts(options.arrival_mode, &arrival_quote, trigger_exchange_ts_us);
        let latency_slippage_bps =
            latency_slippage_bps(intent.order.side, &intent.observed_quote, &arrival_quote);
        let actual_latency_us = arrival_local_ts_us.saturating_sub(intent.observed_local_ts_us);
        let target_miss_us = trigger_local_ts_us.saturating_sub(intent.arrival_local_ts_us);
        let arrival_quote_lag = arrival_quote.seq.saturating_sub(intent.observed_quote.seq);
        let arrival_stream_lag = arrival_stream_seq.saturating_sub(effective_arrival_stream_seq);
        if arrival_quote_lag > 0 {
            counters.arrival_quote_lag_count += 1;
        }
        if arrival_stream_lag > 0 {
            counters.arrival_stream_lag_count += 1;
        }
        counters.target_miss_us_samples.push(target_miss_us);
        let arrival_snapshot = match options.fill_model {
            TakerFillModel::TopOfBookTakerIocV1 => exchange.snapshot_at_frame(&arrival_quote),
            TakerFillModel::L2TakerDepthV1 => trigger_snapshot.clone(),
        };
        logger.emit(
            "order_arrived",
            &arrival_snapshot,
            "runner",
            serde_json::json!({
                "intent_id": intent.intent_id,
                "observed_seq": intent.observed_seq,
                "arrival_seq": virtual_event_stream_seq,
                "drain_stream_seq": arrival_stream_seq,
                "effective_arrival_stream_seq": effective_arrival_stream_seq,
                "arrival_stream_lag": arrival_stream_lag,
                "arrival_mode": options.arrival_mode,
                "arrival_time_source": order_arrival_time_source(options.arrival_mode),
                "trigger_local_ts_us": trigger_local_ts_us,
                "trigger_exchange_ts_us": trigger_exchange_ts_us,
                "arrival_quote_seq": arrival_quote.seq,
                "arrival_quote_lag": arrival_quote_lag,
                "observed_local_ts_us": intent.observed_local_ts_us,
                "arrival_local_ts_us": arrival_local_ts_us,
                "arrival_exchange_ts_us": arrival_exchange_ts_us,
                "target_arrival_local_ts_us": intent.arrival_local_ts_us,
                "target_miss_us": target_miss_us,
                "latency_us": options.latency_us,
                "effective_latency_us": intent.effective_latency_us,
                "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                "actual_latency_us": actual_latency_us,
                "observed_quote": intent.observed_quote.clone(),
                "arrival_quote": arrival_quote.clone(),
                "spread_bps_at_arrival": arrival_quote.spread_bps(),
                "latency_slippage_bps": latency_slippage_bps,
                "order": intent.order.clone(),
                "reason": intent.reason.clone(),
                "fill_model": options.fill_model,
                "shadow_signal": intent.shadow_signal.clone(),
            }),
        )?;

        let depth_sweep = match options.fill_model {
            TakerFillModel::TopOfBookTakerIocV1 => None,
            TakerFillModel::L2TakerDepthV1 => {
                Some(l2_book.sweep(intent.order.side, intent.order.qty))
            }
        };
        let order = match depth_sweep.as_ref() {
            Some(sweep) => exchange.place_taker_depth_order(
                intent.order.clone(),
                sweep.filled_qty,
                sweep.vwap,
            )?,
            None => exchange.place_taker_quote_order(intent.order.clone(), &arrival_quote)?,
        };
        counters.orders_submitted += 1;
        let execution_snapshot = match options.fill_model {
            TakerFillModel::TopOfBookTakerIocV1 => exchange.snapshot_at_frame(&arrival_quote),
            TakerFillModel::L2TakerDepthV1 => exchange.snapshot(),
        };
        let post_order_snapshot = execution_snapshot.clone();
        let order_event_type = if order.status == quant_replay_core::OrderStatus::Rejected {
            "order_reject"
        } else {
            "order_ack"
        };
        let order_message = sparse_stream_message(
            &options.run_id,
            order_event_type,
            "private",
            virtual_event_stream_seq,
            &post_order_snapshot.current_frame,
            arrival_exchange_ts_us,
            arrival_local_ts_us,
            serde_json::json!({
                "intent_id": intent.intent_id,
                "order": order.clone(),
                "observed_quote": intent.observed_quote.clone(),
                "arrival_quote": arrival_quote.clone(),
                "arrival_seq": virtual_event_stream_seq,
                "drain_stream_seq": arrival_stream_seq,
                "effective_arrival_stream_seq": effective_arrival_stream_seq,
                "arrival_stream_lag": arrival_stream_lag,
                "arrival_mode": options.arrival_mode,
                "arrival_time_source": order_arrival_time_source(options.arrival_mode),
                "trigger_local_ts_us": trigger_local_ts_us,
                "trigger_exchange_ts_us": trigger_exchange_ts_us,
                "arrival_quote_seq": arrival_quote.seq,
                "arrival_quote_lag": arrival_quote_lag,
                "arrival_local_ts_us": arrival_local_ts_us,
                "arrival_exchange_ts_us": arrival_exchange_ts_us,
                "fill_price": order.avg_fill_price,
                "spread_bps_at_arrival": arrival_quote.spread_bps(),
                "target_miss_us": target_miss_us,
                "latency_us": options.latency_us,
                "effective_latency_us": intent.effective_latency_us,
                "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                "actual_latency_us": actual_latency_us,
                "latency_slippage_bps": latency_slippage_bps,
                "execution_model": options.fill_model,
                "depth_sweep": depth_sweep.clone(),
                "shadow_signal": intent.shadow_signal.clone(),
            }),
        );
        logger.emit(
            order_event_type,
            &post_order_snapshot,
            "exchange_sim",
            order_message.clone(),
        )?;
        send_sparse_strategy_message(
            bridge,
            logger,
            options,
            &post_order_snapshot,
            order_message,
            false,
        )?;

        let fills = exchange.fills()[*seen_fill_count..].to_vec();
        for fill in fills {
            counters.fills_created += 1;
            let fill_snapshot = execution_snapshot.clone();
            let fill_message = sparse_stream_message(
                &options.run_id,
                "fill",
                "private",
                virtual_event_stream_seq,
                &fill_snapshot.current_frame,
                arrival_exchange_ts_us,
                arrival_local_ts_us,
                serde_json::json!({
                    "intent_id": intent.intent_id,
                    "fill": fill.clone(),
                    "observed_quote": intent.observed_quote.clone(),
                    "arrival_quote": arrival_quote.clone(),
                    "arrival_seq": virtual_event_stream_seq,
                    "drain_stream_seq": arrival_stream_seq,
                    "effective_arrival_stream_seq": effective_arrival_stream_seq,
                    "arrival_stream_lag": arrival_stream_lag,
                    "arrival_mode": options.arrival_mode,
                    "arrival_time_source": order_arrival_time_source(options.arrival_mode),
                    "trigger_local_ts_us": trigger_local_ts_us,
                    "trigger_exchange_ts_us": trigger_exchange_ts_us,
                    "arrival_quote_seq": arrival_quote.seq,
                    "arrival_quote_lag": arrival_quote_lag,
                    "arrival_local_ts_us": arrival_local_ts_us,
                    "arrival_exchange_ts_us": arrival_exchange_ts_us,
                    "fill_price": fill.price,
                    "spread_bps_at_arrival": arrival_quote.spread_bps(),
                    "target_miss_us": target_miss_us,
                    "latency_us": options.latency_us,
                    "effective_latency_us": intent.effective_latency_us,
                    "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                    "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                    "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                    "actual_latency_us": actual_latency_us,
                    "latency_slippage_bps": latency_slippage_bps,
                    "fee_bps": options.exchange_config.fee_bps,
                    "execution_model": options.fill_model,
                    "depth_sweep": depth_sweep.clone(),
                    "shadow_signal": intent.shadow_signal.clone(),
                }),
            );
            logger.emit("fill", &fill_snapshot, "exchange_sim", fill_message.clone())?;
            emit_shadow_position_event(
                logger,
                &fill_snapshot,
                "portfolio",
                &intent,
                &fill,
                intent.intent_id,
            )?;
            send_sparse_strategy_message(
                bridge,
                logger,
                options,
                &fill_snapshot,
                fill_message,
                false,
            )?;
        }
        *seen_fill_count = exchange.fills().len();
        let portfolio_snapshot = execution_snapshot.clone();
        logger.emit(
            "portfolio_state_on_change",
            &portfolio_snapshot,
            "portfolio",
            serde_json::json!({
                "account": portfolio_snapshot.account,
                "open_orders": portfolio_snapshot.open_orders,
                "order_count": portfolio_snapshot.order_count,
                "fill_count": portfolio_snapshot.fill_count,
                "arrival_seq": virtual_event_stream_seq,
                "drain_stream_seq": arrival_stream_seq,
                "arrival_quote_seq": arrival_quote.seq,
                "arrival_local_ts_us": arrival_local_ts_us,
                "arrival_exchange_ts_us": arrival_exchange_ts_us,
            }),
        )?;
        send_sparse_account_snapshot_at(
            bridge,
            logger,
            options,
            &portfolio_snapshot,
            virtual_event_stream_seq,
            arrival_exchange_ts_us,
            arrival_local_ts_us,
        )?;
    }
    Ok(())
}

fn drain_server_ingress(
    ingress_rx: &Receiver<ServerIngressLine>,
    logger: &mut EventLogger,
    options: &RunnerServerOptions,
    snapshot: &ExchangeSnapshot,
    observations: &VecDeque<SparseObservation>,
    pending: &mut VecDeque<StreamPendingOrder>,
    private_hub: &StreamHub,
    next_intent_id: &mut u64,
    counters: &mut ServerCounters,
) -> Result<()> {
    loop {
        let ingress = match ingress_rx.try_recv() {
            Ok(ingress) => ingress,
            Err(TryRecvError::Empty) => return Ok(()),
            Err(TryRecvError::Disconnected) => return Ok(()),
        };
        let response_value = serde_json::from_str::<serde_json::Value>(&ingress.line)
            .unwrap_or_else(|_| serde_json::json!({ "raw": ingress.line }));
        let response = match serde_json::from_str::<StrategyResponse>(&ingress.line) {
            Ok(response) => response,
            Err(error) => {
                counters.ingress_errors += 1;
                logger.emit(
                    "order_ingress_error",
                    snapshot,
                    "order_ingress",
                    serde_json::json!({
                        "context": "parse_response",
                        "error": error.to_string(),
                        "line": response_value,
                    }),
                )?;
                continue;
            }
        };
        counters.ingress_messages_received += 1;
        if matches!(options.log_mode, StreamLogMode::Audit | StreamLogMode::Full)
            || matches!(
                response.message_type.as_str(),
                "submit_order" | "cancel_order"
            )
        {
            logger.emit(
                "order_ingress_received",
                snapshot,
                "order_ingress",
                serde_json::json!({
                    "response": response_value,
                    "received_wall_us": ingress.received_wall_us,
                }),
            )?;
        }
        handle_server_ingress_response(
            response,
            ingress.received_wall_us,
            logger,
            options,
            snapshot,
            observations,
            pending,
            private_hub,
            next_intent_id,
            counters,
        )?;
    }
}

fn handle_server_ingress_response(
    response: StrategyResponse,
    received_wall_us: u64,
    logger: &mut EventLogger,
    options: &RunnerServerOptions,
    snapshot: &ExchangeSnapshot,
    observations: &VecDeque<SparseObservation>,
    pending: &mut VecDeque<StreamPendingOrder>,
    private_hub: &StreamHub,
    next_intent_id: &mut u64,
    counters: &mut ServerCounters,
) -> Result<()> {
    match response.message_type.as_str() {
        "heartbeat" | "hold" => {
            emit_capacity_decision(
                logger,
                snapshot,
                "strategy_bot",
                response.observed_seq,
                None,
                response.reason.as_deref(),
                response.feature_snapshot.clone(),
                response.shadow_signal.clone(),
            )?;
            if let Some(feature_snapshot) = response.feature_snapshot.clone() {
                logger.emit(
                    "strategy_feature_checkpoint",
                    snapshot,
                    "strategy_bot",
                    serde_json::json!({
                        "message_type": response.message_type.clone(),
                        "observed_seq": response.observed_seq,
                        "reason": response.reason.clone(),
                        "feature_snapshot": feature_snapshot,
                        "shadow_signal": response.shadow_signal.clone(),
                    }),
                )?;
            }
            if matches!(options.log_mode, StreamLogMode::Full) {
                logger.emit(
                    "bot_heartbeat",
                    snapshot,
                    "order_ingress",
                    serde_json::json!({
                        "observed_seq": response.observed_seq,
                        "reason": response.reason,
                    }),
                )?;
            }
            Ok(())
        }
        "submit_order" => {
            let Some(request) = response.order else {
                return reject_server_ingress(
                    "submit_order response did not include order fields",
                    response.observed_seq,
                    logger,
                    options,
                    snapshot,
                    private_hub,
                    counters,
                );
            };
            let Some(observed_seq) = response.observed_seq else {
                return reject_server_ingress(
                    "submit_order missing observed_seq",
                    None,
                    logger,
                    options,
                    snapshot,
                    private_hub,
                    counters,
                );
            };
            let Some(observed) = find_observation(observations, observed_seq) else {
                return reject_server_ingress(
                    "observed_seq is not in retained observation window",
                    Some(observed_seq),
                    logger,
                    options,
                    snapshot,
                    private_hub,
                    counters,
                );
            };
            if response
                .observed_local_ts_us
                .is_some_and(|ts| ts != observed.local_ts_us)
            {
                logger.emit(
                    "strategy_observed_ts_mismatch",
                    snapshot,
                    "order_ingress",
                    serde_json::json!({
                        "observed_seq": observed_seq,
                        "response_observed_local_ts_us": response.observed_local_ts_us,
                        "runner_observed_local_ts_us": observed.local_ts_us,
                    }),
                )?;
            }
            let mut order = request.into_new_order()?;
            if order.kind != OrderKind::Market || order.tif != TimeInForce::Ioc {
                return reject_server_ingress(
                    "runner_server_v1 only accepts taker market IOC orders",
                    Some(observed_seq),
                    logger,
                    options,
                    snapshot,
                    private_hub,
                    counters,
                );
            }
            if order.client_order_id.is_none() {
                order.client_order_id = Some(format!("server-intent-{}", next_intent_id));
            }
            let bridge_wall_latency_us = received_wall_us.saturating_sub(observed.sent_wall_us);
            let bridge_wall_latency_ms = bridge_wall_latency_us / 1_000;
            let wall_latency_virtual_staleness_us = match options.clock_mode {
                StreamClockMode::DeterministicStep => 0,
                StreamClockMode::AcceleratedAsync => {
                    (bridge_wall_latency_us as f64 * options.wall_latency_speedup)
                        .round()
                        .clamp(0.0, u64::MAX as f64) as u64
                }
            };
            let effective_latency_us = options
                .latency_us
                .saturating_add(wall_latency_virtual_staleness_us);
            let intent = StreamPendingOrder {
                intent_id: *next_intent_id,
                observed_seq,
                observed_local_ts_us: observed.local_ts_us,
                arrival_local_ts_us: observed.local_ts_us.saturating_add(effective_latency_us),
                arrival_quote_override: None,
                arrival_stream_seq_override: None,
                effective_latency_us,
                wall_latency_virtual_staleness_us,
                bridge_wall_latency_us,
                reason: response
                    .reason
                    .unwrap_or_else(|| "server_bot_submit_order".to_string()),
                bridge_wall_latency_ms,
                feature_snapshot: response.feature_snapshot.clone(),
                shadow_signal: response.shadow_signal.clone(),
                observed_quote: observed.quote.clone(),
                order,
            };
            *next_intent_id += 1;
            counters.intents_created += 1;
            if should_emit_capacity_decision_for_order(&intent.shadow_signal, &intent.order) {
                emit_capacity_decision(
                    logger,
                    snapshot,
                    "strategy_bot",
                    Some(intent.observed_seq),
                    Some(intent.intent_id),
                    Some(intent.reason.as_str()),
                    intent.feature_snapshot.clone(),
                    intent.shadow_signal.clone(),
                )?;
            }
            logger.emit(
                "order_intent",
                snapshot,
                "strategy_bot",
                serde_json::json!({
                    "intent": intent.clone(),
                    "feature_snapshot": intent.feature_snapshot.clone(),
                    "shadow_signal": intent.shadow_signal.clone(),
                }),
            )?;
            logger.emit(
                "order_scheduled",
                snapshot,
                "runner_server",
                serde_json::json!({
                    "intent_id": intent.intent_id,
                    "observed_seq": intent.observed_seq,
                    "observed_local_ts_us": intent.observed_local_ts_us,
                    "arrival_local_ts_us": intent.arrival_local_ts_us,
                    "latency_us": options.latency_us,
                    "arrival_mode": options.arrival_mode,
                    "effective_latency_us": intent.effective_latency_us,
                    "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                    "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                    "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                }),
            )?;
            insert_pending_by_arrival(pending, intent);
            Ok(())
        }
        "cancel_order" => {
            let cancel_idx = pending.iter().position(|intent| {
                response
                    .cancel_intent_id
                    .is_some_and(|intent_id| intent_id == intent.intent_id)
                    || response
                        .cancel_client_order_id
                        .as_ref()
                        .is_some_and(|client_id| {
                            intent.order.client_order_id.as_ref() == Some(client_id)
                        })
            });
            let (event_type, payload) = match cancel_idx.and_then(|idx| pending.remove(idx)) {
                Some(intent) => (
                    "cancel_ack",
                    serde_json::json!({
                        "intent": intent,
                        "reason": response.reason,
                    }),
                ),
                None => (
                    "cancel_reject",
                    serde_json::json!({
                        "reason": response.reason.unwrap_or_else(|| {
                            "no matching pending taker IOC intent".to_string()
                        }),
                        "cancel_intent_id": response.cancel_intent_id,
                        "cancel_order_id": response.cancel_order_id,
                        "cancel_client_order_id": response.cancel_client_order_id,
                    }),
                ),
            };
            let message = sparse_stream_message(
                &options.run_id,
                event_type,
                "private",
                snapshot.current_frame.seq,
                &snapshot.current_frame,
                snapshot.current_frame.exchange_ts_us,
                snapshot.current_frame.local_ts_us,
                payload,
            );
            logger.emit(event_type, snapshot, "runner_server", message.clone())?;
            private_hub.broadcast(&message)?;
            Ok(())
        }
        other => reject_server_ingress(
            &format!("unsupported order ingress type: {other}"),
            response.observed_seq,
            logger,
            options,
            snapshot,
            private_hub,
            counters,
        ),
    }
}

fn reject_server_ingress(
    reason: &str,
    observed_seq: Option<u64>,
    logger: &mut EventLogger,
    options: &RunnerServerOptions,
    snapshot: &ExchangeSnapshot,
    private_hub: &StreamHub,
    counters: &mut ServerCounters,
) -> Result<()> {
    counters.ingress_errors += 1;
    let payload = serde_json::json!({
        "reason": reason,
        "observed_seq": observed_seq,
    });
    let message = sparse_stream_message(
        &options.run_id,
        "order_reject",
        "private",
        snapshot.current_frame.seq,
        &snapshot.current_frame,
        snapshot.current_frame.exchange_ts_us,
        snapshot.current_frame.local_ts_us,
        payload,
    );
    logger.emit("order_reject", snapshot, "runner_server", message.clone())?;
    private_hub.broadcast(&message)?;
    Ok(())
}

fn insert_pending_by_arrival(
    pending: &mut VecDeque<StreamPendingOrder>,
    intent: StreamPendingOrder,
) {
    let idx = pending
        .iter()
        .position(|queued| queued.arrival_local_ts_us > intent.arrival_local_ts_us)
        .unwrap_or(pending.len());
    pending.insert(idx, intent);
}

fn submit_due_server_orders(
    exchange: &mut PaperExchange,
    pending: &mut VecDeque<StreamPendingOrder>,
    logger: &mut EventLogger,
    private_hub: &StreamHub,
    options: &RunnerServerOptions,
    seen_fill_count: &mut usize,
    counters: &mut ServerCounters,
    l2_book: &mut L2Book,
    arrival_stream_seq: u64,
    arrival_exchange_ts_us: u64,
    arrival_local_ts_us: u64,
) -> Result<()> {
    while pending
        .front()
        .is_some_and(|intent| intent.arrival_local_ts_us <= arrival_local_ts_us)
    {
        let arrival_snapshot = exchange.snapshot();
        let arrival_quote = arrival_snapshot.current_frame.clone();
        let intent = pending.pop_front().expect("pending front checked");
        let trigger_local_ts_us = arrival_local_ts_us;
        let trigger_exchange_ts_us = arrival_exchange_ts_us;
        let arrival_local_ts_us = order_arrival_local_ts(
            options.arrival_mode,
            intent.arrival_local_ts_us,
            trigger_local_ts_us,
        );
        let arrival_exchange_ts_us =
            order_arrival_exchange_ts(options.arrival_mode, &arrival_quote, trigger_exchange_ts_us);
        let latency_slippage_bps =
            latency_slippage_bps(intent.order.side, &intent.observed_quote, &arrival_quote);
        let actual_latency_us = arrival_local_ts_us.saturating_sub(intent.observed_local_ts_us);
        logger.emit(
            "order_arrived",
            &arrival_snapshot,
            "runner_server",
            serde_json::json!({
                "intent_id": intent.intent_id,
                "observed_seq": intent.observed_seq,
                "arrival_seq": arrival_stream_seq,
                "arrival_mode": options.arrival_mode,
                "arrival_time_source": order_arrival_time_source(options.arrival_mode),
                "trigger_local_ts_us": trigger_local_ts_us,
                "trigger_exchange_ts_us": trigger_exchange_ts_us,
                "arrival_quote_seq": arrival_quote.seq,
                "observed_local_ts_us": intent.observed_local_ts_us,
                "arrival_local_ts_us": arrival_local_ts_us,
                "arrival_exchange_ts_us": arrival_exchange_ts_us,
                "target_arrival_local_ts_us": intent.arrival_local_ts_us,
                "latency_us": options.latency_us,
                "effective_latency_us": intent.effective_latency_us,
                "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                "actual_latency_us": actual_latency_us,
                "observed_quote": intent.observed_quote.clone(),
                "arrival_quote": arrival_quote.clone(),
                "spread_bps_at_arrival": arrival_quote.spread_bps(),
                "latency_slippage_bps": latency_slippage_bps,
                "order": intent.order.clone(),
                "reason": intent.reason.clone(),
                "fill_model": options.fill_model,
                "shadow_signal": intent.shadow_signal.clone(),
            }),
        )?;

        let depth_sweep = match options.fill_model {
            TakerFillModel::TopOfBookTakerIocV1 => None,
            TakerFillModel::L2TakerDepthV1 => {
                Some(l2_book.sweep(intent.order.side, intent.order.qty))
            }
        };
        let order = match depth_sweep.as_ref() {
            Some(sweep) => exchange.place_taker_depth_order(
                intent.order.clone(),
                sweep.filled_qty,
                sweep.vwap,
            )?,
            None => exchange.place_order(intent.order.clone())?,
        };
        counters.orders_submitted += 1;
        let post_order_snapshot = exchange.snapshot();
        let order_event_type = if order.status == quant_replay_core::OrderStatus::Rejected {
            "order_reject"
        } else {
            "order_ack"
        };
        let order_message = sparse_stream_message(
            &options.run_id,
            order_event_type,
            "private",
            arrival_stream_seq,
            &post_order_snapshot.current_frame,
            arrival_exchange_ts_us,
            arrival_local_ts_us,
            serde_json::json!({
                "intent_id": intent.intent_id,
                "order": order.clone(),
                "observed_quote": intent.observed_quote.clone(),
                "arrival_quote": post_order_snapshot.current_frame.clone(),
                "arrival_seq": arrival_stream_seq,
                "arrival_mode": options.arrival_mode,
                "arrival_time_source": order_arrival_time_source(options.arrival_mode),
                "trigger_local_ts_us": trigger_local_ts_us,
                "trigger_exchange_ts_us": trigger_exchange_ts_us,
                "arrival_quote_seq": post_order_snapshot.current_frame.seq,
                "arrival_local_ts_us": arrival_local_ts_us,
                "arrival_exchange_ts_us": arrival_exchange_ts_us,
                "fill_price": order.avg_fill_price,
                "spread_bps_at_arrival": post_order_snapshot.current_frame.spread_bps(),
                "latency_us": options.latency_us,
                "effective_latency_us": intent.effective_latency_us,
                "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                "actual_latency_us": actual_latency_us,
                "latency_slippage_bps": latency_slippage_bps,
                "execution_model": options.fill_model,
                "depth_sweep": depth_sweep.clone(),
                "shadow_signal": intent.shadow_signal.clone(),
            }),
        );
        logger.emit(
            order_event_type,
            &post_order_snapshot,
            "exchange_sim",
            order_message.clone(),
        )?;
        private_hub.broadcast(&order_message)?;

        let fills = exchange.fills()[*seen_fill_count..].to_vec();
        for fill in fills {
            counters.fills_created += 1;
            let fill_snapshot = exchange.snapshot();
            let fill_message = sparse_stream_message(
                &options.run_id,
                "fill",
                "private",
                arrival_stream_seq,
                &fill_snapshot.current_frame,
                arrival_exchange_ts_us,
                arrival_local_ts_us,
                serde_json::json!({
                    "intent_id": intent.intent_id,
                    "fill": fill.clone(),
                    "observed_quote": intent.observed_quote.clone(),
                    "arrival_quote": fill_snapshot.current_frame.clone(),
                    "arrival_seq": arrival_stream_seq,
                    "arrival_mode": options.arrival_mode,
                    "arrival_time_source": order_arrival_time_source(options.arrival_mode),
                    "trigger_local_ts_us": trigger_local_ts_us,
                    "trigger_exchange_ts_us": trigger_exchange_ts_us,
                    "arrival_quote_seq": fill_snapshot.current_frame.seq,
                    "arrival_local_ts_us": arrival_local_ts_us,
                    "arrival_exchange_ts_us": arrival_exchange_ts_us,
                    "fill_price": fill.price,
                    "spread_bps_at_arrival": fill_snapshot.current_frame.spread_bps(),
                    "latency_us": options.latency_us,
                    "effective_latency_us": intent.effective_latency_us,
                    "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                    "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                    "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                    "actual_latency_us": actual_latency_us,
                    "latency_slippage_bps": latency_slippage_bps,
                    "fee_bps": options.exchange_config.fee_bps,
                    "execution_model": options.fill_model,
                    "depth_sweep": depth_sweep.clone(),
                    "shadow_signal": intent.shadow_signal.clone(),
                }),
            );
            logger.emit("fill", &fill_snapshot, "exchange_sim", fill_message.clone())?;
            emit_shadow_position_event(
                logger,
                &fill_snapshot,
                "portfolio",
                &intent,
                &fill,
                intent.intent_id,
            )?;
            private_hub.broadcast(&fill_message)?;
        }
        *seen_fill_count = exchange.fills().len();
        let portfolio_snapshot = exchange.snapshot();
        logger.emit(
            "portfolio_state_on_change",
            &portfolio_snapshot,
            "portfolio",
            serde_json::json!({
                "account": portfolio_snapshot.account,
                "open_orders": portfolio_snapshot.open_orders,
                "order_count": portfolio_snapshot.order_count,
                "fill_count": portfolio_snapshot.fill_count,
                "arrival_seq": arrival_stream_seq,
                "arrival_quote_seq": portfolio_snapshot.current_frame.seq,
                "arrival_local_ts_us": arrival_local_ts_us,
                "arrival_exchange_ts_us": arrival_exchange_ts_us,
            }),
        )?;
        private_hub.broadcast(&server_account_snapshot_message(
            &options.run_id,
            &portfolio_snapshot,
            arrival_stream_seq,
            arrival_exchange_ts_us,
            arrival_local_ts_us,
        ))?;
    }
    Ok(())
}

fn handle_sparse_bridge_error(
    error: anyhow::Error,
    logger: &mut EventLogger,
    options: &SparsePythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    counters: &mut SparseCounters,
    context: &str,
) -> Result<()> {
    counters.bridge_errors += 1;
    let error_text = error.to_string();
    logger.emit(
        "strategy_bridge_error",
        snapshot,
        "strategy_bridge",
        serde_json::json!({
            "context": context,
            "error": error_text,
            "failure_policy": options.failure_policy,
        }),
    )?;
    match options.failure_policy {
        BridgeFailurePolicy::FailFast => Err(anyhow::anyhow!(error_text)),
        BridgeFailurePolicy::HoldAndLog => Ok(()),
    }
}

fn remember_observation(
    observations: &mut VecDeque<SparseObservation>,
    observation: SparseObservation,
) {
    const MAX_OBSERVATIONS: usize = 100_000;
    observations.push_back(observation);
    while observations.len() > MAX_OBSERVATIONS {
        observations.pop_front();
    }
}

fn mark_observations_sent_wall_us(
    observations: &mut VecDeque<SparseObservation>,
    seq_start: u64,
    seq_end: u64,
    sent_wall_us: u64,
) {
    for observation in observations.iter_mut().rev() {
        if observation.stream_seq < seq_start {
            break;
        }
        if observation.stream_seq <= seq_end {
            observation.sent_wall_us = sent_wall_us;
        }
    }
}

fn find_observation(
    observations: &VecDeque<SparseObservation>,
    stream_seq: u64,
) -> Option<SparseObservation> {
    observations
        .iter()
        .rev()
        .find(|observation| observation.stream_seq == stream_seq)
        .cloned()
}

fn find_arrival_observation(
    observations: &VecDeque<SparseObservation>,
    target_local_ts_us: u64,
) -> Option<SparseObservation> {
    observations
        .iter()
        .find(|observation| observation.local_ts_us >= target_local_ts_us)
        .cloned()
}

fn send_strategy_message(
    bridge: &mut PythonBridge,
    logger: &mut EventLogger,
    options: &PythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    message: serde_json::Value,
    pending: &mut VecDeque<StreamPendingOrder>,
    next_intent_id: &mut u64,
    counters: &mut StreamCounters,
) -> Result<()> {
    logger.emit(
        "strategy_message_sent",
        snapshot,
        "strategy_bridge",
        serde_json::json!({
            "message": message.clone(),
        }),
    )?;

    let started = Instant::now();
    if let Err(error) = bridge.send_json(&message) {
        return handle_bridge_error(error, logger, options, snapshot, counters, "send_json");
    }
    let bridge_line = match bridge.read_line() {
        Ok(line) => line,
        Err(error) => {
            return handle_bridge_error(error, logger, options, snapshot, counters, "read_stdout");
        }
    };
    let bridge_wall_latency_us = started.elapsed().as_micros().min(u64::MAX as u128) as u64;
    let bridge_wall_latency_ms = bridge_wall_latency_us / 1_000;
    let response_value = serde_json::from_str::<serde_json::Value>(&bridge_line)
        .unwrap_or_else(|_| serde_json::json!({ "raw": bridge_line }));
    let response = match serde_json::from_str::<StrategyResponse>(&bridge_line) {
        Ok(response) => response,
        Err(error) => {
            logger.emit(
                "strategy_message_received",
                snapshot,
                "strategy_bridge",
                serde_json::json!({
                    "parse_ok": false,
                    "line": response_value,
                    "bridge_wall_latency_us": bridge_wall_latency_us,
                    "bridge_wall_latency_ms": bridge_wall_latency_ms,
                }),
            )?;
            return handle_bridge_error(
                anyhow::anyhow!("invalid strategy response: {error}"),
                logger,
                options,
                snapshot,
                counters,
                "parse_response",
            );
        }
    };

    counters.strategy_messages_received += 1;
    logger.emit(
        "strategy_message_received",
        snapshot,
        "strategy_bridge",
        serde_json::json!({
            "parse_ok": true,
            "response": response_value,
            "bridge_wall_latency_us": bridge_wall_latency_us,
            "bridge_wall_latency_ms": bridge_wall_latency_ms,
        }),
    )?;

    if let Some(observed_seq) = response.observed_seq {
        if observed_seq != snapshot.current_frame.seq {
            logger.emit(
                "strategy_observed_seq_mismatch",
                snapshot,
                "strategy_bridge",
                serde_json::json!({
                    "response_observed_seq": observed_seq,
                    "runner_observed_seq": snapshot.current_frame.seq,
                }),
            )?;
        }
    }

    match response.message_type.as_str() {
        "heartbeat" | "hold" => {
            emit_capacity_decision(
                logger,
                snapshot,
                "python_strategy",
                response.observed_seq,
                None,
                response.reason.as_deref(),
                response.feature_snapshot.clone(),
                response.shadow_signal.clone(),
            )?;
            if let Some(feature_snapshot) = response.feature_snapshot.clone() {
                logger.emit(
                    "strategy_feature_checkpoint",
                    snapshot,
                    "python_strategy",
                    serde_json::json!({
                        "message_type": response.message_type.clone(),
                        "observed_seq": response.observed_seq,
                        "reason": response.reason.clone(),
                        "feature_snapshot": feature_snapshot,
                        "shadow_signal": response.shadow_signal.clone(),
                    }),
                )?;
            }
            Ok(())
        }
        "submit_order" => {
            let Some(request) = response.order else {
                return handle_bridge_error(
                    anyhow::anyhow!("submit_order response did not include order fields"),
                    logger,
                    options,
                    snapshot,
                    counters,
                    "submit_order",
                );
            };
            let mut order = request.into_new_order()?;
            if order.kind != OrderKind::Market || order.tif != TimeInForce::Ioc {
                logger.emit(
                    "order_reject",
                    snapshot,
                    "runner",
                    serde_json::json!({
                        "reason": "stream_v1 only accepts taker market IOC orders",
                        "order": order.clone(),
                    }),
                )?;
                return Ok(());
            }
            if order.client_order_id.is_none() {
                order.client_order_id = Some(format!("py-intent-{}", next_intent_id));
            }
            let wall_latency_virtual_staleness_us =
                wall_latency_virtual_staleness_us(options, bridge_wall_latency_us);
            let effective_latency_us = options
                .latency_us
                .saturating_add(wall_latency_virtual_staleness_us);
            let intent = StreamPendingOrder {
                intent_id: *next_intent_id,
                observed_seq: snapshot.current_frame.seq,
                observed_local_ts_us: snapshot.current_frame.local_ts_us,
                arrival_local_ts_us: snapshot
                    .current_frame
                    .local_ts_us
                    .saturating_add(effective_latency_us),
                arrival_quote_override: None,
                arrival_stream_seq_override: None,
                effective_latency_us,
                wall_latency_virtual_staleness_us,
                bridge_wall_latency_us,
                reason: response
                    .reason
                    .unwrap_or_else(|| "python_strategy_submit_order".to_string()),
                bridge_wall_latency_ms,
                feature_snapshot: response.feature_snapshot.clone(),
                shadow_signal: response.shadow_signal.clone(),
                observed_quote: snapshot.current_frame.clone(),
                order,
            };
            *next_intent_id += 1;
            counters.intents_created += 1;
            if should_emit_capacity_decision_for_order(&intent.shadow_signal, &intent.order) {
                emit_capacity_decision(
                    logger,
                    snapshot,
                    "python_strategy",
                    Some(intent.observed_seq),
                    Some(intent.intent_id),
                    Some(intent.reason.as_str()),
                    intent.feature_snapshot.clone(),
                    intent.shadow_signal.clone(),
                )?;
            }
            logger.emit(
                "order_intent",
                snapshot,
                "python_strategy",
                serde_json::json!({
                    "intent": intent.clone(),
                    "feature_snapshot": intent.feature_snapshot.clone(),
                    "shadow_signal": intent.shadow_signal.clone(),
                }),
            )?;
            logger.emit(
                "order_scheduled",
                snapshot,
                "runner",
                serde_json::json!({
                    "intent_id": intent.intent_id,
                    "observed_seq": intent.observed_seq,
                    "observed_local_ts_us": intent.observed_local_ts_us,
                    "arrival_local_ts_us": intent.arrival_local_ts_us,
                    "latency_us": options.latency_us,
                    "arrival_mode": options.arrival_mode,
                    "effective_latency_us": intent.effective_latency_us,
                    "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                    "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                    "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                }),
            )?;
            pending.push_back(intent);
            Ok(())
        }
        "cancel_order" => {
            let cancel_idx = pending.iter().position(|intent| {
                response
                    .cancel_intent_id
                    .is_some_and(|intent_id| intent_id == intent.intent_id)
                    || response
                        .cancel_client_order_id
                        .as_ref()
                        .is_some_and(|client_id| {
                            intent.order.client_order_id.as_ref() == Some(client_id)
                        })
            });
            match cancel_idx.and_then(|idx| pending.remove(idx)) {
                Some(intent) => logger.emit(
                    "cancel_ack",
                    snapshot,
                    "runner",
                    serde_json::json!({
                        "intent": intent,
                        "reason": response.reason,
                    }),
                ),
                None => logger.emit(
                    "cancel_reject",
                    snapshot,
                    "runner",
                    serde_json::json!({
                        "reason": response.reason.unwrap_or_else(|| {
                            "no matching pending taker IOC intent".to_string()
                        }),
                        "cancel_intent_id": response.cancel_intent_id,
                        "cancel_order_id": response.cancel_order_id,
                        "cancel_client_order_id": response.cancel_client_order_id,
                    }),
                ),
            }
        }
        other => handle_bridge_error(
            anyhow::anyhow!("unsupported strategy response type: {other}"),
            logger,
            options,
            snapshot,
            counters,
            "response_type",
        ),
    }
}

fn submit_due_stream_orders(
    exchange: &mut PaperExchange,
    pending: &mut VecDeque<StreamPendingOrder>,
    logger: &mut EventLogger,
    bridge: &mut PythonBridge,
    options: &PythonStreamOptions,
    seen_fill_count: &mut usize,
    counters: &mut StreamCounters,
    next_intent_id: &mut u64,
) -> Result<()> {
    while pending
        .front()
        .is_some_and(|intent| intent.arrival_local_ts_us <= exchange.current_frame().local_ts_us)
    {
        let arrival_snapshot = exchange.snapshot();
        let arrival_quote = arrival_snapshot.current_frame.clone();
        let intent = pending.pop_front().expect("pending front checked");
        let latency_slippage_bps =
            latency_slippage_bps(intent.order.side, &intent.observed_quote, &arrival_quote);
        let arrival_payload = serde_json::json!({
            "intent_id": intent.intent_id,
            "observed_seq": intent.observed_seq,
            "arrival_seq": arrival_quote.seq,
            "observed_local_ts_us": intent.observed_local_ts_us,
            "arrival_local_ts_us": arrival_quote.local_ts_us,
            "target_arrival_local_ts_us": intent.arrival_local_ts_us,
            "latency_us": options.latency_us,
            "effective_latency_us": intent.effective_latency_us,
            "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
            "bridge_wall_latency_us": intent.bridge_wall_latency_us,
            "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
            "observed_quote": intent.observed_quote.clone(),
            "arrival_quote": arrival_quote.clone(),
            "spread_bps_at_arrival": arrival_quote.spread_bps(),
            "latency_slippage_bps": latency_slippage_bps,
            "order": intent.order.clone(),
            "reason": intent.reason.clone(),
        });
        logger.emit(
            "order_arrived",
            &arrival_snapshot,
            "runner",
            arrival_payload.clone(),
        )?;

        let order = exchange.place_order(intent.order.clone())?;
        counters.orders_submitted += 1;
        let post_order_snapshot = exchange.snapshot();
        let order_event_type = if order.status == quant_replay_core::OrderStatus::Rejected {
            "order_reject"
        } else {
            "order_ack"
        };
        let order_message = stream_message(
            &options.run_id,
            order_event_type,
            "private",
            &post_order_snapshot,
            serde_json::json!({
                "intent_id": intent.intent_id,
                "order": order.clone(),
                "observed_quote": intent.observed_quote.clone(),
                "arrival_quote": post_order_snapshot.current_frame.clone(),
                "fill_price": order.avg_fill_price,
                "spread_bps_at_arrival": post_order_snapshot.current_frame.spread_bps(),
                "latency_us": options.latency_us,
                "effective_latency_us": intent.effective_latency_us,
                "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                "latency_slippage_bps": latency_slippage_bps,
            }),
        );
        logger.emit(
            order_event_type,
            &post_order_snapshot,
            "exchange_sim",
            order_message.clone(),
        )?;
        send_strategy_message(
            bridge,
            logger,
            options,
            &post_order_snapshot,
            order_message,
            pending,
            next_intent_id,
            counters,
        )?;

        let fills = exchange.fills()[*seen_fill_count..].to_vec();
        for fill in fills {
            counters.fills_created += 1;
            let fill_snapshot = exchange.snapshot();
            let fill_message = stream_message(
                &options.run_id,
                "fill",
                "private",
                &fill_snapshot,
                serde_json::json!({
                    "intent_id": intent.intent_id,
                    "fill": fill.clone(),
                    "observed_quote": intent.observed_quote.clone(),
                    "arrival_quote": fill_snapshot.current_frame.clone(),
                    "fill_price": fill.price,
                    "spread_bps_at_arrival": fill_snapshot.current_frame.spread_bps(),
                    "latency_us": options.latency_us,
                    "effective_latency_us": intent.effective_latency_us,
                    "wall_latency_virtual_staleness_us": intent.wall_latency_virtual_staleness_us,
                    "bridge_wall_latency_us": intent.bridge_wall_latency_us,
                    "bridge_wall_latency_ms": intent.bridge_wall_latency_ms,
                    "latency_slippage_bps": latency_slippage_bps,
                    "fee_bps": options.exchange_config.fee_bps,
                }),
            );
            logger.emit(
                "fill_created",
                &fill_snapshot,
                "exchange_sim",
                fill_message.clone(),
            )?;
            send_strategy_message(
                bridge,
                logger,
                options,
                &fill_snapshot,
                fill_message,
                pending,
                next_intent_id,
                counters,
            )?;
        }
        *seen_fill_count = exchange.fills().len();
        let portfolio_snapshot = exchange.snapshot();
        logger.emit(
            "portfolio_state",
            &portfolio_snapshot,
            "portfolio",
            serde_json::json!({
                "account": portfolio_snapshot.account,
                "open_orders": portfolio_snapshot.open_orders,
                "order_count": portfolio_snapshot.order_count,
                "fill_count": portfolio_snapshot.fill_count,
            }),
        )?;
    }
    Ok(())
}

fn handle_bridge_error(
    error: anyhow::Error,
    logger: &mut EventLogger,
    options: &PythonStreamOptions,
    snapshot: &ExchangeSnapshot,
    counters: &mut StreamCounters,
    context: &str,
) -> Result<()> {
    counters.bridge_errors += 1;
    let error_text = error.to_string();
    logger.emit(
        "strategy_bridge_error",
        snapshot,
        "strategy_bridge",
        serde_json::json!({
            "context": context,
            "error": error_text,
            "failure_policy": options.failure_policy,
        }),
    )?;
    match options.failure_policy {
        BridgeFailurePolicy::FailFast => Err(anyhow::anyhow!(error_text)),
        BridgeFailurePolicy::HoldAndLog => Ok(()),
    }
}

fn latency_slippage_bps(side: Side, observed: &MarketFrame, arrival: &MarketFrame) -> f64 {
    match side {
        Side::Buy => (arrival.ask / observed.ask).ln() * 10_000.0,
        Side::Sell => (observed.bid / arrival.bid).ln() * 10_000.0,
    }
}

fn wall_latency_virtual_staleness_us(
    options: &PythonStreamOptions,
    bridge_wall_latency_us: u64,
) -> u64 {
    match options.clock_mode {
        StreamClockMode::DeterministicStep => 0,
        StreamClockMode::AcceleratedAsync => {
            let staleness = bridge_wall_latency_us as f64 * options.wall_latency_speedup;
            staleness.round().clamp(0.0, u64::MAX as f64) as u64
        }
    }
}

fn default_market_kind() -> OrderKind {
    OrderKind::Market
}

fn default_ioc_tif() -> TimeInForce {
    TimeInForce::Ioc
}

fn submit_due_intents(
    exchange: &mut PaperExchange,
    pending: &mut VecDeque<PendingIntent>,
    logger: &mut EventLogger,
    seen_fill_count: &mut usize,
    orders_submitted: &mut u64,
) -> Result<()> {
    while pending
        .front()
        .is_some_and(|intent| intent.arrival_seq <= exchange.current_frame().seq)
    {
        let snapshot = exchange.snapshot();
        let intent = pending.pop_front().expect("pending front checked");
        logger.emit(
            "order_submitted",
            &snapshot,
            "runner",
            serde_json::json!({
                "intent": intent,
                "arrival_seq": snapshot.current_frame.seq,
            }),
        )?;
        let order = exchange.place_order(intent.order.clone())?;
        *orders_submitted += 1;
        emit_order_result(logger, &exchange.snapshot(), &order)?;
        emit_new_fills(exchange, logger, seen_fill_count)?;
    }
    Ok(())
}

fn emit_order_result(
    logger: &mut EventLogger,
    snapshot: &ExchangeSnapshot,
    order: &Order,
) -> Result<()> {
    let event_type = match order.status {
        quant_replay_core::OrderStatus::Rejected => "order_rejected",
        quant_replay_core::OrderStatus::Canceled => "order_canceled",
        _ => "order_accepted",
    };
    logger.emit(
        event_type,
        snapshot,
        "exchange_sim",
        serde_json::json!({
            "order": order,
        }),
    )
}

fn emit_new_fills(
    exchange: &PaperExchange,
    logger: &mut EventLogger,
    seen_fill_count: &mut usize,
) -> Result<()> {
    let snapshot = exchange.snapshot();
    for fill in &exchange.fills()[*seen_fill_count..] {
        logger.emit(
            "fill_created",
            &snapshot,
            "exchange_sim",
            serde_json::json!({
                "fill": fill,
                "frame": snapshot.current_frame,
            }),
        )?;
    }
    *seen_fill_count = exchange.fills().len();
    Ok(())
}

struct ToyOnceStrategy {
    config: ToyStrategyConfig,
    entered: bool,
    exited: bool,
    entry_decision_seq: Option<u64>,
}

impl ToyOnceStrategy {
    fn new(config: ToyStrategyConfig) -> Self {
        Self {
            config,
            entered: false,
            exited: false,
            entry_decision_seq: None,
        }
    }

    fn decide(&mut self, snapshot: &ExchangeSnapshot) -> StrategyDecision {
        if !self.entered && snapshot.account.position_qty == 0.0 {
            self.entered = true;
            self.entry_decision_seq = Some(snapshot.current_frame.seq);
            return StrategyDecision {
                action: StrategyAction::Enter,
                reason: "toy_once_enter_flat_position".to_string(),
                order: Some(NewOrder {
                    side: Side::Buy,
                    kind: OrderKind::Market,
                    qty: self.config.qty,
                    limit_price: None,
                    tif: TimeInForce::Ioc,
                    reduce_only: false,
                    client_order_id: Some(format!("toy-enter-{}", snapshot.current_frame.seq)),
                }),
            };
        }

        let entry_seq = self
            .entry_decision_seq
            .unwrap_or(snapshot.current_frame.seq);
        let held_long_enough = snapshot.current_frame.seq >= entry_seq + self.config.hold_frames;
        if self.entered && !self.exited && snapshot.account.position_qty > 0.0 && held_long_enough {
            self.exited = true;
            return StrategyDecision {
                action: StrategyAction::Exit,
                reason: "toy_once_exit_after_hold_frames".to_string(),
                order: Some(NewOrder {
                    side: Side::Sell,
                    kind: OrderKind::Market,
                    qty: snapshot.account.position_qty.abs(),
                    limit_price: None,
                    tif: TimeInForce::Ioc,
                    reduce_only: true,
                    client_order_id: Some(format!("toy-exit-{}", snapshot.current_frame.seq)),
                }),
            };
        }

        StrategyDecision {
            action: StrategyAction::Hold,
            reason: if self.entered && !self.exited {
                "toy_once_waiting_for_exit".to_string()
            } else {
                "toy_once_done".to_string()
            },
            order: None,
        }
    }
}

struct EventLogger {
    run_id: String,
    events_path: PathBuf,
    next_event_id: u64,
    writer: BufWriter<File>,
}

impl EventLogger {
    fn create(run_dir: &Path, run_id: &str) -> Result<Self> {
        let events_path = run_dir.join("events.ndjson");
        let file = File::create(&events_path)
            .with_context(|| format!("create {}", events_path.display()))?;
        Ok(Self {
            run_id: run_id.to_string(),
            events_path,
            next_event_id: 1,
            writer: BufWriter::new(file),
        })
    }

    fn emit(
        &mut self,
        event_type: &str,
        snapshot: &ExchangeSnapshot,
        source: &str,
        payload: serde_json::Value,
    ) -> Result<()> {
        let event = RunEvent {
            event_id: self.next_event_id,
            run_id: self.run_id.clone(),
            event_type: event_type.to_string(),
            replay_seq: snapshot.current_frame.seq,
            replay_ts: snapshot.current_frame.ts.clone(),
            wall_ts_ms: now_ms(),
            source: source.to_string(),
            payload,
        };
        serde_json::to_writer(&mut self.writer, &event)?;
        self.writer.write_all(b"\n")?;
        self.next_event_id += 1;
        Ok(())
    }

    fn event_count(&self) -> u64 {
        self.next_event_id - 1
    }

    fn flush(&mut self) -> Result<()> {
        self.writer.flush()?;
        Ok(())
    }

    fn finalize(&mut self) -> Result<()> {
        self.flush()?;
        write_replay_index(&self.events_path)
    }
}

fn write_manifest(path: PathBuf, value: &impl Serialize) -> Result<()> {
    let mut manifest = serde_json::to_value(value)?;
    if let Some(object) = manifest.as_object_mut() {
        object.insert(
            "artifact_schema".to_string(),
            serde_json::json!({
                "schema_id": "qrs_run_artifacts_v1",
                "files": ["manifest.json", "summary.json", "events.ndjson", "replay_index.json"],
                "event_contract": "causal_market_execution_v1"
            }),
        );
    }
    write_json(path, &manifest)
}

fn write_replay_index(events_path: &Path) -> Result<()> {
    let file = File::open(events_path)
        .with_context(|| format!("open {} for replay index", events_path.display()))?;
    let mut reader = BufReader::new(file);
    let mut line = String::new();
    let mut offset = 0_u64;
    let mut events = Vec::new();
    let mut orders: BTreeMap<String, Vec<u64>> = BTreeMap::new();
    let mut fills: BTreeMap<String, Vec<u64>> = BTreeMap::new();
    while reader.read_line(&mut line)? > 0 {
        let byte_len = line.len() as u64;
        if let Ok(event) = serde_json::from_str::<RunEvent>(line.trim_end()) {
            let payload = &event.payload;
            for key in ["intent_id", "client_order_id", "order_id"] {
                if let Some(value) = find_scalar(payload, key) {
                    orders.entry(format!("{key}:{value}")).or_default().push(event.event_id);
                }
            }
            for key in ["fill_id", "order_id"] {
                if let Some(value) = find_scalar(payload, key) {
                    fills.entry(format!("{key}:{value}")).or_default().push(event.event_id);
                }
            }
            events.push(ReplayIndexEntry {
                event_id: event.event_id,
                event_type: event.event_type,
                replay_seq: event.replay_seq,
                replay_ts: event.replay_ts,
                byte_offset: offset,
                byte_len,
            });
        }
        offset = offset.saturating_add(byte_len);
        line.clear();
    }
    let index = ReplayIndex {
        schema_id: "qrs_replay_index_v1",
        event_count: events.len(),
        events,
        orders,
        fills,
    };
    let index_path = events_path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("replay_index.json");
    write_json(index_path, &index)
}

fn find_scalar(value: &serde_json::Value, key: &str) -> Option<String> {
    match value {
        serde_json::Value::Object(object) => {
            if let Some(candidate) = object.get(key) {
                if let Some(text) = candidate.as_str() {
                    return Some(text.to_string());
                }
                if let Some(number) = candidate.as_u64() {
                    return Some(number.to_string());
                }
            }
            object.values().find_map(|child| find_scalar(child, key))
        }
        serde_json::Value::Array(values) => values.iter().find_map(|child| find_scalar(child, key)),
        _ => None,
    }
}

fn write_json(path: PathBuf, value: &impl Serialize) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let file = File::create(&path).with_context(|| format!("create {}", path.display()))?;
    serde_json::to_writer_pretty(file, value)?;
    Ok(())
}

fn default_progress_every() -> usize {
    1_000
}

fn write_native_progress(
    run_dir: &Path,
    state: &str,
    events_seen: usize,
    quote_events_seen: u64,
    trade_events_seen: u64,
    l2_batches_seen: u64,
    orders_submitted: u64,
    fills_created: u64,
    replay_ts_us: Option<u64>,
) -> Result<()> {
    write_json(
        run_dir.join("progress.json"),
        &serde_json::json!({
            "state": state,
            "events_processed": events_seen,
            "quotes": quote_events_seen,
            "trades": trade_events_seen,
            "l2_batches": l2_batches_seen,
            "orders": orders_submitted,
            "fills": fills_created,
            "replay_ts_us": replay_ts_us,
        }),
    )
}

fn sparse_profile_manifest(options: &SparsePythonStreamOptions) -> serde_json::Value {
    let args = &options.strategy_args;
    let policy_name = if has_strategy_arg(args, "--shadow-four-cell") {
        "old_tfi_four_cell_shadow_v1"
    } else {
        "online_tfi_skeleton_v1"
    };
    let capacity_profile = strategy_arg_value(args, "--shadow-capacity-profile")
        .unwrap_or_else(|| "fifo_clip".to_string());
    let mut manifest = serde_json::json!({
        "schema_id": "ccusdt_strategy_run_profiles_v1",
        "policy_profile": {
            "name": policy_name,
            "decision_clock": strategy_arg_value(args, "--decision-clock").unwrap_or_else(|| "quote".to_string()),
            "gamma_preset": strategy_arg_value(args, "--shadow-gamma-preset"),
            "gamma01_override": strategy_arg_value(args, "--shadow-gamma01-override").and_then(|v| v.parse::<f64>().ok()),
            "frames_threshold": strategy_arg_value(args, "--shadow-frames-threshold").and_then(|v| v.parse::<f64>().ok()),
            "overlay_threshold": strategy_arg_value(args, "--shadow-overlay-threshold").and_then(|v| v.parse::<f64>().ok()),
            "fixed_exit_us": strategy_arg_value(args, "--shadow-fixed-exit-us").and_then(|v| v.parse::<u64>().ok()),
        },
        "capacity_profile": {
            "name": capacity_profile,
            "leverage_cap": strategy_arg_value(args, "--shadow-leverage-cap").and_then(|v| v.parse::<f64>().ok()).unwrap_or(options.exchange_config.max_leverage),
            "idle01_gamma": strategy_arg_value(args, "--shadow-idle01-gamma").and_then(|v| v.parse::<f64>().ok()),
            "idle01_reserve": strategy_arg_value(args, "--shadow-idle01-reserve").and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0),
            "admission_profile": strategy_arg_value(args, "--shadow-admission-profile").unwrap_or_else(|| "none".to_string()),
            "admission_entry_cross_threshold_bps": strategy_arg_value(args, "--shadow-admission-entry-cross-threshold-bps").and_then(|v| v.parse::<f64>().ok()),
            "admission_threshold_source": strategy_arg_value(args, "--shadow-admission-threshold-source"),
            "admission_thresholds_json": strategy_arg_value(args, "--shadow-admission-thresholds-json"),
            "admission_date": strategy_arg_value(args, "--shadow-admission-date"),
            "core_cells": ["00_none", "10_r5_only", "11_r5_frames"],
            "idle_cell": "01_frames_only",
        },
        "exit_profile": {
            "name": strategy_arg_value(args, "--shadow-exit-profile").unwrap_or_else(|| "fixed60_taker".to_string()),
            "fixed_exit_us": strategy_arg_value(args, "--shadow-fixed-exit-us").and_then(|v| v.parse::<u64>().ok()),
            "manager_path_policy": if strategy_arg_value(args, "--shadow-exit-profile").as_deref() == Some("peakguard_taker_v1") { Some("pm_11_drawdown_h4_peakguard") } else { None },
            "stopping_rule_params_json": strategy_arg_value(args, "--shadow-stopping-rule-params-json"),
        },
        "fill_profile": {
            "name": options.fill_model,
            "fee_bps": options.exchange_config.fee_bps,
        },
        "latency_profile": {
            "name": determinism_mode(options.clock_mode),
            "latency_us": options.latency_us,
            "arrival_mode": options.arrival_mode,
            "clock_mode": options.clock_mode,
            "wall_latency_speedup": options.wall_latency_speedup,
        },
        "transport_profile": {
            "name": options.public_stream_mode,
            "public_batch_size": options.public_batch_size,
            "public_batch_max_span_us": options.public_batch_max_span_us,
            "panel_frame_cache": options.panel_frame_cache_manifest.clone(),
        },
        "data_profile": {
            "name": "runner_market_truth_v1",
            "source_label": options.source_label,
            "decision_frame_cache": options.panel_frame_cache_manifest.clone(),
            "decision_frame_data_manifest_hash": options
                .panel_frame_cache_manifest
                .as_ref()
                .and_then(|manifest| manifest.get("data_manifest_hash"))
                .cloned(),
            "source_canonical": options
                .panel_frame_cache_manifest
                .as_ref()
                .and_then(|manifest| manifest.get("source_canonical"))
                .cloned(),
        },
    });
    let manifest_hash = stable_json_fingerprint(&manifest);
    if let Some(object) = manifest.as_object_mut() {
        object.insert(
            "profile_manifest_hash".to_string(),
            serde_json::Value::String(manifest_hash),
        );
    }
    manifest
}

fn stable_json_fingerprint(value: &serde_json::Value) -> String {
    let payload = serde_json::to_string(value).unwrap_or_default();
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in payload.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

fn profile_manifest_hash(manifest: &serde_json::Value) -> Option<String> {
    manifest
        .get("profile_manifest_hash")
        .and_then(|value| value.as_str())
        .map(|value| value.to_string())
}

fn determinism_mode(clock_mode: StreamClockMode) -> &'static str {
    match clock_mode {
        StreamClockMode::DeterministicStep => "deterministic_replay_v1",
        StreamClockMode::AcceleratedAsync => "wall_latency_pressure_v1",
    }
}

fn public_stream_mode_name(mode: SparsePublicStreamMode) -> &'static str {
    match mode {
        SparsePublicStreamMode::StrictEvent => "strict_event",
        SparsePublicStreamMode::BatchedPublicV1 => "batched_public_v1",
        SparsePublicStreamMode::BatchedPublicBarrierV1 => "batched_public_barrier_v1",
        SparsePublicStreamMode::PanelSparseV1 => "panel_sparse_v1",
        SparsePublicStreamMode::PanelSparseFastClockV1 => "panel_sparse_fast_clock_v1",
    }
}

fn quote_at_or_before(frames: &[MarketFrame], local_ts_us: u64) -> Option<&MarketFrame> {
    let idx = frames.partition_point(|frame| frame.local_ts_us <= local_ts_us);
    if idx == 0 {
        frames.first()
    } else {
        frames.get(idx - 1)
    }
}

fn percentile_u64(values: &[u64], percentile: f64) -> Option<u64> {
    if values.is_empty() {
        return None;
    }
    let mut sorted = values.to_vec();
    sorted.sort_unstable();
    let idx = ((sorted.len() - 1) as f64 * percentile)
        .round()
        .clamp(0.0, (sorted.len() - 1) as f64) as usize;
    sorted.get(idx).copied()
}

fn has_strategy_arg(args: &[String], flag: &str) -> bool {
    args.iter().any(|arg| arg == flag)
}

fn strategy_arg_value(args: &[String], flag: &str) -> Option<String> {
    args.iter()
        .position(|arg| arg == flag)
        .and_then(|index| args.get(index + 1))
        .cloned()
}

fn now_ms() -> u64 {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0);
    millis.min(u64::MAX as u128) as u64
}

fn now_us() -> u64 {
    let micros = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_micros())
        .unwrap_or(0);
    micros.min(u64::MAX as u128) as u64
}

fn elapsed_us(started: Instant) -> u64 {
    started.elapsed().as_micros().min(u128::from(u64::MAX)) as u64
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

#[cfg(test)]
mod tests {
    use super::*;
    use quant_replay_core::{ReplaySource, load_replay};

    #[test]
    fn toy_runner_writes_causal_event_log() {
        let root = temp_dir("runner_events");
        let frames = load_replay(ReplaySource::Synthetic { frames: 8 }).unwrap();
        let summary = run_toy_strategy(
            frames,
            RunnerOptions {
                run_id: "unit_run".to_string(),
                run_root: root.clone(),
                source_label: "synthetic".to_string(),
                exchange_config: ExchangeConfig::default(),
                max_frames: 6,
                latency_frames: 1,
                log_holds: true,
                strategy: ToyStrategyConfig {
                    qty: 1.0,
                    hold_frames: 2,
                },
            },
        )
        .unwrap();

        assert_eq!(summary.frames_seen, 6);
        assert_eq!(summary.intents_created, 2);
        assert_eq!(summary.orders_submitted, 2);
        assert_eq!(summary.fills_created, 2);
        assert_eq!(summary.final_account.position_qty, 0.0);

        let events = fs::read_to_string(root.join("unit_run").join("events.ndjson")).unwrap();
        assert!(events.contains("\"event_type\":\"order_intent\""));
        assert!(events.contains("\"event_type\":\"order_submitted\""));
        assert!(events.contains("\"event_type\":\"fill_created\""));
        let parsed = events
            .lines()
            .map(|line| serde_json::from_str::<RunEvent>(line).unwrap())
            .collect::<Vec<_>>();
        let first_intent_seq = parsed
            .iter()
            .find(|event| event.event_type == "order_intent")
            .unwrap()
            .replay_seq;
        let first_submit_seq = parsed
            .iter()
            .find(|event| event.event_type == "order_submitted")
            .unwrap()
            .replay_seq;
        assert_eq!(first_submit_seq, first_intent_seq + 1);
        assert!(root.join("unit_run").join("manifest.json").exists());
        assert!(root.join("unit_run").join("summary.json").exists());
        assert!(root.join("unit_run").join("replay_index.json").exists());
        let index: serde_json::Value = serde_json::from_str(
            &fs::read_to_string(root.join("unit_run").join("replay_index.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(index["schema_id"], "qrs_replay_index_v1");
        assert!(index["event_count"].as_u64().unwrap_or(0) > 0);
    }

    #[test]
    fn sparse_stream_message_keeps_event_time_separate_from_quote_time() {
        let quote =
            MarketFrame::new_with_timestamps(17, "quote-ts", 1_000, 1_100, 1.00, 1.01).unwrap();
        let message = sparse_stream_message(
            "run",
            "market_trade",
            "public",
            42,
            &quote,
            2_000,
            2_100,
            serde_json::json!({ "trade_id": "t0" }),
        );
        assert_eq!(message["seq"], 42);
        assert_eq!(message["quote_seq"], 17);
        assert_eq!(message["exchange_ts_us"], 2_000);
        assert_eq!(message["local_ts_us"], 2_100);
    }

    #[test]
    fn strategy_order_request_rejects_reserved_maker_fields() {
        let request = serde_json::from_value::<StrategyOrderRequest>(serde_json::json!({
            "side": "buy",
            "kind": "market",
            "qty": 1.0,
            "tif": "ioc",
            "execution_role": "maker_reserved",
            "post_only": true
        }))
        .unwrap();
        let error = request.into_new_order().unwrap_err().to_string();
        assert!(error.contains("reserved-only"));
        assert!(error.contains("maker execution is disabled"));
    }

    #[test]
    fn l2_book_sweep_reports_partial_fill() {
        let mut book = L2Book::new();
        book.apply_batch(&[
            L2LevelUpdate {
                seq: 0,
                exchange_ts_us: 1,
                local_ts_us: 1,
                is_snapshot: true,
                side: Side::Sell,
                price: 101.0,
                qty: 2.0,
            },
            L2LevelUpdate {
                seq: 1,
                exchange_ts_us: 1,
                local_ts_us: 1,
                is_snapshot: true,
                side: Side::Sell,
                price: 102.0,
                qty: 3.0,
            },
        ]);
        let sweep = book.sweep(Side::Buy, 10.0);
        assert!(sweep.partial_fill);
        assert_eq!(sweep.filled_qty, 5.0);
        assert_eq!(sweep.remaining_qty, 5.0);
        assert_eq!(sweep.levels_consumed, 2);
        assert_eq!(sweep.reason, "insufficient_depth");
        assert!(sweep.depth_slippage_bps.unwrap() > 0.0);
    }

    fn temp_dir(name: &str) -> PathBuf {
        let nonce = now_ms();
        let path = std::env::temp_dir().join(format!("ccusdt_{name}_{nonce}"));
        fs::create_dir_all(&path).unwrap();
        path
    }
}

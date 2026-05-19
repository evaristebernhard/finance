use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use ccusdt_exchange_sim::PaperExchange;
use ccusdt_replay_core::{
    AccountView, ExchangeConfig, ExchangeSnapshot, L2LevelUpdate, MarketFrame, NewOrder, Order,
    OrderKind, Side, TimeInForce, TradeEvent,
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
    write_json(run_dir.join("manifest.json"), &options)?;

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
    logger.flush()?;

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

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct PythonStreamOptions {
    pub run_id: String,
    pub run_root: PathBuf,
    pub source_label: String,
    pub exchange_config: ExchangeConfig,
    pub max_frames: usize,
    pub latency_us: u64,
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
struct StreamPendingOrder {
    intent_id: u64,
    observed_seq: u64,
    observed_local_ts_us: u64,
    arrival_local_ts_us: u64,
    effective_latency_us: u64,
    wall_latency_virtual_staleness_us: u64,
    bridge_wall_latency_us: u64,
    reason: String,
    bridge_wall_latency_ms: u64,
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
}

impl StrategyOrderRequest {
    fn into_new_order(self) -> NewOrder {
        NewOrder {
            side: self.side,
            kind: self.kind,
            qty: self.qty,
            limit_price: self.limit_price,
            tif: self.tif,
            reduce_only: self.reduce_only,
            client_order_id: self.client_order_id,
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
struct StrategyResponse {
    #[serde(rename = "type")]
    message_type: String,
    #[serde(default)]
    observed_seq: Option<u64>,
    #[serde(default)]
    reason: Option<String>,
    #[serde(default)]
    cancel_intent_id: Option<u64>,
    #[serde(default)]
    cancel_order_id: Option<u64>,
    #[serde(default)]
    cancel_client_order_id: Option<String>,
    #[serde(flatten)]
    order: Option<StrategyOrderRequest>,
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

struct L2Book {
    bids: BTreeMap<i64, f64>,
    asks: BTreeMap<i64, f64>,
    active_snapshot_ts: Option<u64>,
}

impl L2Book {
    const PRICE_SCALE: f64 = 100_000_000.0;

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

struct PythonBridge {
    child: Child,
    stdin: BufWriter<ChildStdin>,
    stdout_rx: Receiver<String>,
    timeout: Duration,
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
        })
    }

    fn send_json(&mut self, value: &serde_json::Value) -> Result<()> {
        serde_json::to_writer(&mut self.stdin, value)?;
        self.stdin.write_all(b"\n")?;
        self.stdin.flush()?;
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
    write_json(run_dir.join("manifest.json"), &options)?;

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
    logger.flush()?;
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
        "heartbeat" | "hold" => Ok(()),
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
            let mut order = request.into_new_order();
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
                effective_latency_us,
                wall_latency_virtual_staleness_us,
                bridge_wall_latency_us,
                reason: response
                    .reason
                    .unwrap_or_else(|| "python_strategy_submit_order".to_string()),
                bridge_wall_latency_ms,
                observed_quote: snapshot.current_frame.clone(),
                order,
            };
            *next_intent_id += 1;
            counters.intents_created += 1;
            logger.emit(
                "order_intent",
                snapshot,
                "python_strategy",
                serde_json::json!({
                    "intent": intent.clone(),
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
        let order_event_type = if order.status == ccusdt_replay_core::OrderStatus::Rejected {
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
        ccusdt_replay_core::OrderStatus::Rejected => "order_rejected",
        ccusdt_replay_core::OrderStatus::Canceled => "order_canceled",
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
    next_event_id: u64,
    writer: BufWriter<File>,
}

impl EventLogger {
    fn create(run_dir: &Path, run_id: &str) -> Result<Self> {
        let file = File::create(run_dir.join("events.ndjson"))
            .with_context(|| format!("create {}", run_dir.join("events.ndjson").display()))?;
        Ok(Self {
            run_id: run_id.to_string(),
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
}

fn write_json(path: PathBuf, value: &impl Serialize) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let file = File::create(&path).with_context(|| format!("create {}", path.display()))?;
    serde_json::to_writer_pretty(file, value)?;
    Ok(())
}

fn now_ms() -> u64 {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0);
    millis.min(u64::MAX as u128) as u64
}

fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

#[cfg(test)]
mod tests {
    use super::*;
    use ccusdt_replay_core::{ReplaySource, load_replay};

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
    }

    fn temp_dir(name: &str) -> PathBuf {
        let nonce = now_ms();
        let path = std::env::temp_dir().join(format!("ccusdt_{name}_{nonce}"));
        fs::create_dir_all(&path).unwrap();
        path
    }
}

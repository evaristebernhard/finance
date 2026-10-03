use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

use serde_json::Value;

#[derive(Clone, Debug, Default)]
pub struct RunEntry {
    pub run_id: String,
    pub dataset_date: String,
    pub symbol: String,
    pub strategy: String,
    pub execution_model: String,
    pub event_count: usize,
    pub order_count: usize,
    pub fill_count: usize,
    pub status: String,
    pub run_directory: String,
}

#[derive(Clone, Debug, Default)]
pub struct QuoteSnapshot {
    pub bid: String,
    pub ask: String,
    pub mid: String,
    pub spread: String,
    pub microprice: String,
    pub bid_qty: String,
    pub ask_qty: String,
}

#[derive(Clone, Debug, Default)]
pub struct BookLevelSnapshot {
    pub price: String,
    pub qty: String,
    pub cumulative_qty: String,
}

#[derive(Clone, Debug, Default)]
pub struct OrderBookSnapshot {
    pub best_bid: String,
    pub best_ask: String,
    pub spread: String,
    pub bids: Vec<BookLevelSnapshot>,
    pub asks: Vec<BookLevelSnapshot>,
    pub update_count: usize,
    pub snapshot_batch_count: usize,
    pub quality: String,
}

#[derive(Clone, Debug, Default)]
pub struct StrategySignalSnapshot {
    pub profile: String,
    pub signal: String,
    pub threshold: String,
    pub reason: String,
    pub observed_quote: String,
    pub observed_ts_us: String,
}

#[derive(Clone, Debug, Default)]
pub struct OrderIntentSnapshot {
    pub intent_id: String,
    pub client_order_id: String,
    pub side: String,
    pub qty: String,
    pub reason: String,
    pub observed_quote: String,
    pub observed_ts_us: String,
}

#[derive(Clone, Debug, Default)]
pub struct OrderArrivalSnapshot {
    pub order_id: String,
    pub arrival_quote: String,
    pub arrival_ts_us: String,
    pub actual_latency_us: String,
    pub latency_slippage_bps: String,
    pub order_status: String,
}

#[derive(Clone, Debug, Default)]
pub struct FillSnapshot {
    pub fill_id: String,
    pub order_id: String,
    pub side: String,
    pub price: String,
    pub qty: String,
    pub fee: String,
    pub liquidity: String,
    pub realized_pnl_delta: String,
    pub net_pnl_delta: String,
    pub attribution: String,
}

#[derive(Clone, Debug, Default)]
pub struct PositionSnapshot {
    pub position_qty: String,
    pub avg_entry_price: String,
    pub equity: String,
    pub fees_paid: String,
}

#[derive(Clone, Debug, Default)]
pub struct PnlSnapshot {
    pub realized_pnl: String,
    pub unrealized_pnl: String,
    pub selected_fill_delta: String,
    pub net_equity: String,
}

#[derive(Clone, Debug, Default)]
pub struct PnlPoint {
    pub event_pos: usize,
    pub timestamp: String,
    pub realized_pnl: f64,
    pub unrealized_pnl: f64,
    pub net_pnl: f64,
}

#[derive(Clone, Debug, Default)]
pub struct L2QualitySnapshot {
    pub status: String,
    pub warning: String,
}

#[derive(Clone, Debug, Default)]
pub struct ReplaySnapshot {
    pub run_id: String,
    pub symbol: String,
    pub dataset_date: String,
    pub strategy: String,
    pub execution_model: String,
    pub delay_us: u64,
    pub fee_bps: f64,
    pub replay_time: String,
    pub event_cursor: String,
    pub state: String,
    pub progress: i32,
    pub mid: String,
    pub bid: String,
    pub ask: String,
    pub spread: String,
    pub microprice: String,
    pub signal: String,
    pub chart: String,
    pub book: String,
    pub event_tape: String,
    pub orders: String,
    pub fills: String,
    pub position_text: String,
    pub pnl_text: String,
    pub causal: String,
    pub warning: String,
    pub raw_event: String,
    pub selected_fill: String,
    pub cursor: usize,
    pub replay_state: String,
    pub quote: QuoteSnapshot,
    pub order_book: OrderBookSnapshot,
    pub strategy_signal: StrategySignalSnapshot,
    pub order_intent: OrderIntentSnapshot,
    pub order_arrival: OrderArrivalSnapshot,
    pub fill: FillSnapshot,
    pub position: PositionSnapshot,
    pub pnl: PnlSnapshot,
    pub pnl_curve: Vec<PnlPoint>,
    pub l2_quality: L2QualitySnapshot,
}

#[derive(Clone, Debug)]
struct QuotePoint {
    event_pos: usize,
    bid: f64,
    bid_qty: f64,
    ask: f64,
    ask_qty: f64,
    mid: f64,
    signal: f64,
}

#[derive(Clone, Debug)]
struct OrderRow {
    event_pos: usize,
    intent_id: String,
    client_order_id: String,
    side: String,
    qty: f64,
    reason: String,
    observed_ts: String,
    observed_quote: String,
    arrival_ts: String,
    arrival_quote: String,
    latency: String,
    signal: String,
    threshold: String,
    status: String,
}

#[derive(Clone, Debug)]
struct FillRow {
    event_pos: usize,
    fill_id: String,
    order_id: String,
    intent_id: String,
    side: String,
    qty: f64,
    price: f64,
    fee: f64,
    liquidity: String,
    realized_delta: f64,
    net_delta: f64,
    latency: String,
    slippage: f64,
    observed_quote: String,
    arrival_quote: String,
    gross_execution_pnl: f64,
    latency_mark_pnl: f64,
    spread_execution_cost: f64,
    fee_pnl: f64,
    adverse_selection: String,
}

#[derive(Clone, Debug)]
struct StrategySignalRow {
    event_pos: usize,
    profile: String,
    signal: f64,
    threshold: String,
    reason: String,
    observed_quote: String,
    observed_ts_us: String,
}

#[derive(Clone, Debug)]
pub struct RunRepository {
    manifest: Value,
    summary: Value,
    events: Vec<Value>,
    quotes: Vec<QuotePoint>,
    orders: Vec<OrderRow>,
    fills: Vec<FillRow>,
    signals: Vec<StrategySignalRow>,
    l2_books: Vec<(usize, Value)>,
    l2_stats: Vec<(usize, usize, usize)>,
}

impl RunRepository {
    /// List run metadata without opening or scanning `events.ndjson`.
    pub fn list_runs(run_root: &Path) -> Vec<RunEntry> {
        let mut runs: Vec<RunEntry> = std::fs::read_dir(run_root)
            .ok()
            .into_iter()
            .flatten()
            .filter_map(Result::ok)
            .filter(|entry| entry.file_type().map(|kind| kind.is_dir()).unwrap_or(false))
            .filter_map(|entry| {
                let run_directory = entry.path();
                let manifest = read_json(&run_directory.join("manifest.json")).ok()?;
                let summary = read_json(&run_directory.join("summary.json")).ok()?;
                let run_id = first_text(&summary, &["run_id"])
                    .or_else(|| first_text(&manifest, &["run_id"]))
                    .unwrap_or_else(|| entry.file_name().to_string_lossy().to_string());
                let source_label = first_text(&summary, &["source_label"])
                    .or_else(|| first_text(&manifest, &["source_label"]))
                    .unwrap_or_default();
                let dataset_date = first_text(&manifest, &["canonical_date"])
                    .or_else(|| first_text(&summary, &["canonical_date"]))
                    .or_else(|| source_label.rsplit(':').next().map(str::to_string))
                    .unwrap_or_else(|| "—".to_string());
                let symbol = manifest
                    .get("exchange_config")
                    .and_then(|value| first_text(value, &["symbol"]))
                    .or_else(|| source_label.split(':').nth(1).map(str::to_string))
                    .unwrap_or_else(|| "CCUSDT".to_string());
                let strategy = first_text(&manifest, &["profile", "strategy_profile"])
                    .or_else(|| first_text(&summary, &["strategy_profile"]))
                    .unwrap_or_else(|| "TFI".to_string());
                let execution_model = first_text(&manifest, &["fill_model"])
                    .or_else(|| first_text(&summary, &["fill_model"]))
                    .unwrap_or_else(|| "—".to_string());
                let event_count =
                    first_usize(&summary, &["event_count", "events_seen"]).unwrap_or(0);
                let order_count =
                    first_usize(&summary, &["orders_submitted", "order_count"]).unwrap_or(0);
                let fill_count =
                    first_usize(&summary, &["fills_created", "fill_count"]).unwrap_or(0);
                let status = first_text(&summary, &["status"])
                    .unwrap_or_else(|| {
                        if run_directory.join("events.ndjson").exists() {
                            "COMPLETE"
                        } else {
                            "INCOMPLETE"
                        }
                        .to_string()
                    })
                    .to_uppercase();
                Some(RunEntry {
                    run_id,
                    dataset_date,
                    symbol,
                    strategy,
                    execution_model,
                    event_count,
                    order_count,
                    fill_count,
                    status,
                    run_directory: run_directory.to_string_lossy().replace('\\', "/"),
                })
            })
            .collect();
        runs.sort_by(|left, right| right.run_id.cmp(&left.run_id));
        runs
    }

    pub fn open(run_dir: &Path) -> Result<Self, String> {
        let manifest = read_json(&run_dir.join("manifest.json"))?;
        let summary = read_json(&run_dir.join("summary.json"))?;
        let replay_index = if run_dir.join("replay_index.json").exists() {
            read_json(&run_dir.join("replay_index.json"))?
        } else {
            Value::Null
        };
        let events_file = File::open(run_dir.join("events.ndjson"))
            .map_err(|e| format!("打开 events.ndjson 失败: {e}"))?;
        let mut events = Vec::new();
        for line in BufReader::new(events_file).lines() {
            let line = line.map_err(|e| format!("读取事件失败: {e}"))?;
            if !line.trim().is_empty() {
                events
                    .push(serde_json::from_str(&line).map_err(|e| format!("事件 JSON 无效: {e}"))?);
            }
        }
        if events.is_empty() {
            return Err("run 没有事件".to_string());
        }
        if let Some(indexed_event_count) = replay_index.get("event_count").and_then(Value::as_u64) {
            if indexed_event_count as usize != events.len() {
                return Err(format!(
                    "replay_index event_count={} 与 events.ndjson={} 不一致",
                    indexed_event_count,
                    events.len()
                ));
            }
        }

        let mut repo = Self {
            manifest,
            summary,
            events,
            quotes: Vec::new(),
            orders: Vec::new(),
            fills: Vec::new(),
            signals: Vec::new(),
            l2_books: Vec::new(),
            l2_stats: Vec::new(),
        };
        repo.index_events();
        Ok(repo)
    }

    fn index_events(&mut self) {
        for (event_pos, event) in self.events.iter().enumerate() {
            let event_type = text(event, "event_type");
            let payload = event.get("payload").unwrap_or(&Value::Null);
            if event_type == "market_quote" {
                let frame = payload.get("frame").unwrap_or(payload);
                if let (Some(bid), Some(ask), Some(mid)) = (
                    number(frame, "bid"),
                    number(frame, "ask"),
                    number(frame, "mid"),
                ) {
                    self.quotes.push(QuotePoint {
                        event_pos,
                        bid,
                        bid_qty: number(frame, "bid_qty").unwrap_or(0.0),
                        ask,
                        ask_qty: number(frame, "ask_qty").unwrap_or(0.0),
                        mid,
                        signal: number(payload, "signal").unwrap_or(0.0),
                    });
                }
            } else if event_type == "strategy_signal" {
                let observed_quote = quote_text(payload.get("observed_quote"));
                self.signals.push(StrategySignalRow {
                    event_pos,
                    profile: scalar(payload, "strategy_profile")
                        .or_else(|| {
                            scalar(self.manifest.get("profile").unwrap_or(&Value::Null), "name")
                        })
                        .unwrap_or_else(|| {
                            self.manifest
                                .get("profile")
                                .and_then(Value::as_str)
                                .unwrap_or("TFI")
                                .to_string()
                        }),
                    signal: number(payload, "signal").unwrap_or(0.0),
                    threshold: scalar(payload, "threshold").unwrap_or_else(|| "—".to_string()),
                    reason: scalar(payload, "reason")
                        .unwrap_or_else(|| "strategy_signal".to_string()),
                    observed_quote,
                    observed_ts_us: scalar(payload, "observed_ts_us")
                        .unwrap_or_else(|| text(event, "replay_ts")),
                });
            } else if event_type == "market_l2_batch" {
                let updates = payload
                    .get("updates")
                    .and_then(Value::as_array)
                    .map_or(0, Vec::len);
                let update_count =
                    updates.max(number(payload, "update_count").unwrap_or(0.0) as usize);
                let snapshot_count =
                    number(payload, "snapshot_update_count").unwrap_or(0.0) as usize;
                let incremental_count =
                    number(payload, "incremental_update_count").unwrap_or(0.0) as usize;
                if let Some(book) = payload.get("book") {
                    self.l2_books.push((event_pos, book.clone()));
                }
                self.l2_stats.push((
                    event_pos,
                    update_count,
                    usize::from(snapshot_count > 0 && incremental_count == 0),
                ));
            } else if event_type == "order_intent" {
                let intent = payload.get("intent").unwrap_or(payload);
                let order = intent.get("order").unwrap_or(&Value::Null);
                self.orders.push(OrderRow {
                    event_pos,
                    intent_id: scalar(payload, "intent_id")
                        .or_else(|| scalar(intent, "intent_id"))
                        .unwrap_or_else(|| "—".to_string()),
                    client_order_id: scalar(payload, "client_order_id")
                        .or_else(|| scalar(order, "client_order_id"))
                        .unwrap_or_else(|| "—".to_string()),
                    side: text(order, "side").to_uppercase(),
                    qty: number(order, "qty").unwrap_or(0.0),
                    reason: scalar(payload, "reason")
                        .or_else(|| scalar(intent, "reason"))
                        .unwrap_or_else(|| "—".to_string()),
                    observed_ts: scalar(payload, "observed_ts_us")
                        .unwrap_or_else(|| text(event, "replay_ts")),
                    observed_quote: quote_text(
                        payload
                            .get("observed_quote")
                            .or_else(|| intent.get("observed_quote")),
                    ),
                    arrival_ts: "—".to_string(),
                    arrival_quote: "—".to_string(),
                    latency: "—".to_string(),
                    signal: scalar(payload, "signal").unwrap_or_else(|| "—".to_string()),
                    threshold: scalar(payload, "threshold").unwrap_or_else(|| "—".to_string()),
                    status: "WAITING".to_string(),
                });
            } else if event_type == "order_arrival" {
                let intent_id = scalar(payload, "intent_id").unwrap_or_else(|| "—".to_string());
                if let Some(row) = self
                    .orders
                    .iter_mut()
                    .rev()
                    .find(|row| row.intent_id == intent_id)
                {
                    row.arrival_ts = scalar(payload, "arrival_ts_us")
                        .unwrap_or_else(|| text(event, "replay_ts"));
                    row.arrival_quote = quote_text(payload.get("arrival_quote"));
                    row.latency = scalar(payload, "actual_latency_us")
                        .map(|v| format!("{} ms", v.parse::<u64>().unwrap_or(0) / 1_000))
                        .unwrap_or_else(|| "—".to_string());
                    row.status =
                        text(payload.get("order").unwrap_or(payload), "status").to_uppercase();
                }
            } else if event_type == "fill_created" || event_type == "fill" {
                let fill_payload = if event_type == "fill" {
                    payload.get("payload").unwrap_or(payload)
                } else {
                    payload
                };
                let fill = fill_payload.get("fill").unwrap_or(&Value::Null);
                let fill_id = scalar(fill_payload, "fill_id")
                    .or_else(|| scalar(fill, "id"))
                    .unwrap_or_else(|| "—".to_string());
                if self
                    .fills
                    .iter()
                    .any(|row| row.fill_id == fill_id && fill_id != "—")
                {
                    continue;
                }
                self.fills.push(FillRow {
                    event_pos,
                    fill_id,
                    order_id: scalar(fill_payload, "order_id")
                        .or_else(|| scalar(fill, "order_id"))
                        .unwrap_or_else(|| "—".to_string()),
                    intent_id: scalar(fill_payload, "intent_id").unwrap_or_else(|| "—".to_string()),
                    side: text(fill, "side").to_uppercase(),
                    qty: number(fill, "qty").unwrap_or(0.0),
                    price: number(fill, "price").unwrap_or(0.0),
                    fee: number(fill_payload, "fee")
                        .or_else(|| number(fill, "fee"))
                        .unwrap_or(0.0),
                    liquidity: text(fill, "liquidity").to_uppercase(),
                    realized_delta: number(fill_payload, "realized_pnl_delta").unwrap_or(0.0),
                    net_delta: number(fill_payload, "net_pnl_delta").unwrap_or(0.0),
                    latency: scalar(fill_payload, "actual_latency_us")
                        .or_else(|| scalar(fill_payload, "latency_us"))
                        .map(|v| format!("{} ms", v.parse::<u64>().unwrap_or(0) / 1_000))
                        .unwrap_or_else(|| "—".to_string()),
                    slippage: number(fill_payload, "latency_slippage_bps").unwrap_or(0.0),
                    observed_quote: quote_text(fill_payload.get("observed_quote")),
                    arrival_quote: quote_text(fill_payload.get("arrival_quote")),
                    gross_execution_pnl: number(
                        fill_payload.get("attribution").unwrap_or(&Value::Null),
                        "gross_execution_pnl",
                    )
                    .unwrap_or(0.0),
                    latency_mark_pnl: number(
                        fill_payload.get("attribution").unwrap_or(&Value::Null),
                        "latency_mark_pnl",
                    )
                    .unwrap_or(0.0),
                    spread_execution_cost: number(
                        fill_payload.get("attribution").unwrap_or(&Value::Null),
                        "spread_execution_cost",
                    )
                    .unwrap_or(0.0),
                    fee_pnl: number(
                        fill_payload.get("attribution").unwrap_or(&Value::Null),
                        "fee_pnl",
                    )
                    .unwrap_or(-number(fill_payload, "fee").unwrap_or(0.0)),
                    adverse_selection: scalar(
                        fill_payload.get("attribution").unwrap_or(&Value::Null),
                        "adverse_selection_status",
                    )
                    .unwrap_or_else(|| "—".to_string()),
                });
            }
        }

        for fill in &mut self.fills {
            if let Some(order) = self.orders.iter().find(|order| {
                (fill.intent_id != "—" && order.intent_id == fill.intent_id)
                    || (fill.order_id != "—" && order.client_order_id == fill.order_id)
            }) {
                if fill.intent_id == "—" {
                    fill.intent_id = order.intent_id.clone();
                }
                if fill.observed_quote == "—" {
                    fill.observed_quote = order.observed_quote.clone();
                }
                if fill.arrival_quote == "—" {
                    fill.arrival_quote = order.arrival_quote.clone();
                }
                if fill.latency == "—" {
                    fill.latency = order.latency.clone();
                }
            }
        }
    }

    pub fn summary(
        &self,
        cursor: usize,
        selected_fill: Option<&str>,
        tab: &str,
        playing: bool,
        _speed: f64,
    ) -> ReplaySnapshot {
        let end = cursor.min(self.events.len().saturating_sub(1));
        let visible_quotes: Vec<&QuotePoint> = self
            .quotes
            .iter()
            .filter(|quote| quote.event_pos <= end)
            .collect();
        let quote = visible_quotes
            .last()
            .copied()
            .or_else(|| self.quotes.first());
        let current = self.events.get(end).unwrap_or(&self.events[0]);
        let event_type = text(current, "event_type");
        let state = if event_type == "run_end" {
            "RUN COMPLETE"
        } else if event_type == "fill_created" {
            "FILL CREATED"
        } else if event_type == "order_arrival" {
            "ORDER ARRIVED"
        } else if event_type == "order_intent" {
            "WAITING FOR ORDER"
        } else if playing {
            "REPLAYING"
        } else {
            "PAUSED"
        };
        let (bid, ask, mid, spread, micro, signal) = quote
            .map(|q| {
                let micro = if q.bid_qty + q.ask_qty > 0.0 {
                    (q.ask * q.bid_qty + q.bid * q.ask_qty) / (q.bid_qty + q.ask_qty)
                } else {
                    q.mid
                };
                (
                    q.bid,
                    q.ask,
                    q.mid,
                    (q.ask - q.bid) / q.mid * 10_000.0,
                    micro,
                    q.signal,
                )
            })
            .unwrap_or_default();
        let visible_orders: Vec<&OrderRow> = self
            .orders
            .iter()
            .filter(|row| row.event_pos <= end)
            .collect();
        let visible_fills: Vec<&FillRow> = self
            .fills
            .iter()
            .filter(|row| row.event_pos <= end)
            .collect();
        let fill = selected_fill
            .and_then(|id| visible_fills.iter().find(|row| row.fill_id == id).copied())
            .or_else(|| visible_fills.last().copied());
        let account = self.account_at_cursor(end);
        let current_book = self
            .l2_books
            .iter()
            .rev()
            .find(|(event_pos, _)| *event_pos <= end)
            .map(|(_, book)| book);
        let (cursor_l2_updates, cursor_l2_snapshot_batches) = self
            .l2_stats
            .iter()
            .filter(|(event_pos, _, _)| *event_pos <= end)
            .fold(
                (0_usize, 0_usize),
                |(updates, snapshots), (_, update_count, snapshot_count)| {
                    (updates + update_count, snapshots + snapshot_count)
                },
            );
        let signal_row = self.signals.iter().rev().find(|row| row.event_pos <= end);
        let manifest_strategy = self
            .manifest
            .get("profile")
            .and_then(Value::as_str)
            .unwrap_or_else(|| {
                self.manifest
                    .get("strategy_profile")
                    .and_then(Value::as_str)
                    .unwrap_or("TFI")
            });
        let execution = self
            .manifest
            .get("fill_model")
            .and_then(Value::as_str)
            .unwrap_or("top_of_book_taker_ioc_v1");
        let symbol = self
            .manifest
            .get("exchange_config")
            .and_then(|v| v.get("symbol"))
            .and_then(Value::as_str)
            .unwrap_or("CCUSDT");
        let date = self
            .manifest
            .get("canonical_date")
            .and_then(Value::as_str)
            .unwrap_or("2026-10-01");
        let quote_snapshot = quote_snapshot(quote);
        let order_book_snapshot = order_book_snapshot(
            quote,
            current_book,
            cursor_l2_updates,
            cursor_l2_snapshot_batches,
            self.manifest.get("l2_preflight"),
        );
        let strategy_signal = signal_snapshot(signal_row, quote);
        let order = visible_orders
            .iter()
            .rev()
            .find(|row| {
                fill.map(|candidate| candidate.intent_id == row.intent_id)
                    .unwrap_or(false)
            })
            .copied()
            .or_else(|| visible_orders.last().copied());
        let order_intent = intent_snapshot(order);
        let order_arrival = arrival_snapshot(order, fill);
        let fill_snapshot = fill_snapshot(fill);
        let position_snapshot = position_snapshot(&account);
        let pnl_snapshot = pnl_snapshot(&account, fill);
        let l2_quality = l2_quality_snapshot(
            self.manifest.get("l2_preflight"),
            cursor_l2_snapshot_batches,
        );
        ReplaySnapshot {
            run_id: self
                .summary
                .get("run_id")
                .and_then(Value::as_str)
                .unwrap_or("—")
                .to_string(),
            symbol: symbol.to_string(),
            dataset_date: date.to_string(),
            strategy: manifest_strategy.to_string(),
            execution_model: execution.to_string(),
            delay_us: self
                .manifest
                .get("latency_us")
                .and_then(Value::as_u64)
                .unwrap_or(50_000),
            fee_bps: self
                .manifest
                .get("exchange_config")
                .and_then(|value| value.get("fee_bps"))
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
            replay_time: text(current, "replay_ts"),
            event_cursor: format!("{} / {}", end + 1, self.events.len()),
            state: state.to_string(),
            progress: ((end + 1) * 100 / self.events.len().max(1)) as i32,
            mid: price(mid),
            bid: price(bid),
            ask: price(ask),
            spread: format!("{spread:.2} bps"),
            microprice: price(micro),
            signal: format!("{signal:+.3}"),
            chart: chart_text(&visible_quotes),
            book: book_text(
                quote,
                current_book,
                cursor_l2_updates,
                cursor_l2_snapshot_batches,
            ),
            event_tape: match tab {
                "Orders" => order_text(&visible_orders),
                "Fills" => fill_text(&visible_fills),
                "Position" => position_text(&self.summary, fill),
                "PnL Attribution" => pnl_text(&self.summary, fill),
                _ => event_tape(&self.events, end),
            },
            orders: order_text(&visible_orders),
            fills: fill_text(&visible_fills),
            position_text: position_text(&account, fill),
            pnl_text: pnl_text(&account, fill),
            causal: causal_text(fill, &self.orders),
            warning: l2_quality.warning.clone(),
            raw_event: serde_json::to_string_pretty(current).unwrap_or_else(|_| "{}".to_string()),
            selected_fill: fill
                .map(|row| row.fill_id.clone())
                .unwrap_or_else(|| "—".to_string()),
            cursor: end,
            replay_state: state.to_string(),
            quote: quote_snapshot,
            order_book: order_book_snapshot,
            strategy_signal,
            order_intent,
            order_arrival,
            fill: fill_snapshot,
            position: position_snapshot,
            pnl: pnl_snapshot,
            pnl_curve: self.pnl_curve(end),
            l2_quality,
        }
    }

    pub fn len(&self) -> usize {
        self.events.len()
    }

    fn account_at_cursor(&self, end: usize) -> Value {
        self.events
            .iter()
            .take(end + 1)
            .rev()
            .filter(|event| {
                matches!(
                    text(event, "event_type").as_str(),
                    "position_snapshot" | "portfolio_state_on_change"
                )
            })
            .find_map(|event| {
                let payload = event.get("payload")?;
                payload.get("account").cloned().or_else(|| {
                    payload
                        .get("payload")
                        .and_then(|nested| nested.get("account"))
                        .cloned()
                })
            })
            .or_else(|| self.summary.get("final_account").cloned())
            .unwrap_or(Value::Null)
    }

    fn pnl_curve(&self, end: usize) -> Vec<PnlPoint> {
        let mut position: f64 = 0.0;
        let mut average_entry: f64 = 0.0;
        let mut realized: f64 = 0.0;
        let mut fees: f64 = 0.0;
        let mut points = Vec::new();

        for fill in self.fills.iter().filter(|fill| fill.event_pos <= end) {
            let signed_qty = if fill.side.eq_ignore_ascii_case("BUY") {
                fill.qty
            } else {
                -fill.qty
            };
            if position == 0.0 || position.signum() == signed_qty.signum() {
                let existing = position.abs();
                let incoming = signed_qty.abs();
                average_entry = if existing + incoming > 0.0 {
                    (average_entry * existing + fill.price * incoming) / (existing + incoming)
                } else {
                    0.0
                };
                position += signed_qty;
            } else {
                let closing = position.abs().min(signed_qty.abs());
                realized += if position > 0.0 {
                    (fill.price - average_entry) * closing
                } else {
                    (average_entry - fill.price) * closing
                };
                position += signed_qty.signum() * closing;
                if position.signum() != signed_qty.signum() && position != 0.0 {
                    average_entry = fill.price;
                }
                if position == 0.0 {
                    average_entry = 0.0;
                }
            }
            fees += fill.fee;
            let mark = self
                .quotes
                .iter()
                .rev()
                .find(|quote| quote.event_pos <= fill.event_pos)
                .map(|quote| quote.mid)
                .unwrap_or(fill.price);
            let unrealized = if position > 0.0 {
                (mark - average_entry) * position
            } else if position < 0.0 {
                (average_entry - mark) * position.abs()
            } else {
                0.0
            };
            points.push(PnlPoint {
                event_pos: fill.event_pos,
                timestamp: self
                    .events
                    .get(fill.event_pos)
                    .map(|event| text(event, "replay_ts"))
                    .unwrap_or_else(|| "—".to_string()),
                realized_pnl: realized,
                unrealized_pnl: unrealized,
                net_pnl: realized + unrealized - fees,
            });
        }

        let mark = self
            .quotes
            .iter()
            .rev()
            .find(|quote| quote.event_pos <= end)
            .map(|quote| quote.mid)
            .unwrap_or(average_entry);
        let unrealized = if position > 0.0 {
            (mark - average_entry) * position
        } else if position < 0.0 {
            (average_entry - mark) * position.abs()
        } else {
            0.0
        };
        points.push(PnlPoint {
            event_pos: end,
            timestamp: self
                .events
                .get(end)
                .map(|event| text(event, "replay_ts"))
                .unwrap_or_else(|| "—".to_string()),
            realized_pnl: realized,
            unrealized_pnl: unrealized,
            net_pnl: realized + unrealized - fees,
        });
        points
    }
}

#[derive(Clone, Debug)]
pub struct ReplaySession {
    pub repository: RunRepository,
    pub cursor: usize,
    pub playing: bool,
    pub speed: f64,
    pub selected_fill: Option<String>,
    pub tab: String,
}

impl ReplaySession {
    pub fn new(repository: RunRepository) -> Self {
        Self {
            repository,
            cursor: 0,
            playing: false,
            speed: 1.0,
            selected_fill: None,
            tab: "Event Tape".to_string(),
        }
    }
    pub fn tick(&mut self) {
        if self.playing {
            self.cursor = (self.cursor + self.speed.max(1.0).round() as usize)
                .min(self.repository.len().saturating_sub(1));
            if self.cursor + 1 >= self.repository.len() {
                self.playing = false;
            }
        }
    }
    pub fn step(&mut self, amount: isize) {
        self.playing = false;
        self.cursor = if amount.is_negative() {
            self.cursor.saturating_sub(amount.unsigned_abs())
        } else {
            (self.cursor + amount as usize).min(self.repository.len().saturating_sub(1))
        };
    }
    pub fn seek(&mut self, fraction: f64) {
        self.playing = false;
        self.cursor = ((self.repository.len().saturating_sub(1) as f64) * fraction.clamp(0.0, 1.0))
            .round() as usize;
    }
    pub fn snapshot(&self) -> ReplaySnapshot {
        self.repository.summary(
            self.cursor,
            self.selected_fill.as_deref(),
            &self.tab,
            self.playing,
            self.speed,
        )
    }
}

fn read_json(path: &Path) -> Result<Value, String> {
    let file = File::open(path).map_err(|e| format!("打开 {} 失败: {e}", path.display()))?;
    serde_json::from_reader(file).map_err(|e| format!("解析 {} 失败: {e}", path.display()))
}
fn text(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or("—")
        .to_string()
}
fn number(value: &Value, key: &str) -> Option<f64> {
    value.get(key).and_then(Value::as_f64)
}
fn scalar(value: &Value, key: &str) -> Option<String> {
    value.get(key).and_then(|v| {
        v.as_str()
            .map(str::to_string)
            .or_else(|| v.as_u64().map(|n| n.to_string()))
            .or_else(|| v.as_f64().map(|n| n.to_string()))
    })
}
fn first_text(value: &Value, keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| scalar(value, key))
}
fn first_usize(value: &Value, keys: &[&str]) -> Option<usize> {
    keys.iter().find_map(|key| {
        value.get(key).and_then(|candidate| {
            candidate
                .as_u64()
                .map(|number| number as usize)
                .or_else(|| candidate.as_f64().map(|number| number as usize))
        })
    })
}
fn price(value: f64) -> String {
    if value > 0.0 {
        format!("{value:.8}")
    } else {
        "—".to_string()
    }
}
fn quote_text(value: Option<&Value>) -> String {
    let Some(quote) = value else {
        return "—".to_string();
    };
    let (Some(bid), Some(ask)) = (number(quote, "bid"), number(quote, "ask")) else {
        return "—".to_string();
    };
    let mid = number(quote, "mid").unwrap_or((bid + ask) * 0.5);
    let spread = number(quote, "spread_bps")
        .unwrap_or_else(|| (ask - bid) / mid.max(f64::EPSILON) * 10_000.0);
    format!(
        "bid {} / ask {} / spread {:.2} bps",
        price(bid),
        price(ask),
        spread
    )
}

fn quote_snapshot(quote: Option<&QuotePoint>) -> QuoteSnapshot {
    let Some(quote) = quote else {
        return QuoteSnapshot::default();
    };
    let microprice = if quote.bid_qty + quote.ask_qty > 0.0 {
        (quote.ask * quote.bid_qty + quote.bid * quote.ask_qty) / (quote.bid_qty + quote.ask_qty)
    } else {
        quote.mid
    };
    QuoteSnapshot {
        bid: price(quote.bid),
        ask: price(quote.ask),
        mid: price(quote.mid),
        spread: format!(
            "{:.2} bps",
            (quote.ask - quote.bid) / quote.mid.max(f64::EPSILON) * 10_000.0
        ),
        microprice: price(microprice),
        bid_qty: format_qty(quote.bid_qty),
        ask_qty: format_qty(quote.ask_qty),
    }
}

fn format_qty(value: f64) -> String {
    if value > 0.0 {
        format!("{value:.3}")
    } else {
        "—".to_string()
    }
}

fn order_book_snapshot(
    quote: Option<&QuotePoint>,
    book: Option<&Value>,
    updates: usize,
    snapshot_batches: usize,
    preflight: Option<&Value>,
) -> OrderBookSnapshot {
    let quality = l2_quality_snapshot(preflight, snapshot_batches).status;
    let Some(book) = book else {
        return OrderBookSnapshot {
            best_bid: quote
                .map(|value| price(value.bid))
                .unwrap_or_else(|| "—".to_string()),
            best_ask: quote
                .map(|value| price(value.ask))
                .unwrap_or_else(|| "—".to_string()),
            spread: quote
                .map(|value| {
                    format!(
                        "{:.2} bps",
                        (value.ask - value.bid) / value.mid.max(f64::EPSILON) * 10_000.0
                    )
                })
                .unwrap_or_else(|| "—".to_string()),
            update_count: updates,
            snapshot_batch_count: snapshot_batches,
            quality,
            ..OrderBookSnapshot::default()
        };
    };
    let best_bid = number(book, "best_bid")
        .or_else(|| quote.map(|value| value.bid))
        .unwrap_or(0.0);
    let best_ask = number(book, "best_ask")
        .or_else(|| quote.map(|value| value.ask))
        .unwrap_or(0.0);
    let mid = if best_bid > 0.0 && best_ask > 0.0 {
        (best_bid + best_ask) * 0.5
    } else {
        0.0
    };
    OrderBookSnapshot {
        best_bid: price(best_bid),
        best_ask: price(best_ask),
        spread: if mid > 0.0 {
            format!("{:.2} bps", (best_ask - best_bid) / mid * 10_000.0)
        } else {
            "—".to_string()
        },
        bids: levels(book.get("bid_depth")),
        asks: levels(book.get("ask_depth")),
        update_count: updates,
        snapshot_batch_count: snapshot_batches,
        quality,
    }
}

fn levels(value: Option<&Value>) -> Vec<BookLevelSnapshot> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .take(5)
        .map(|level| BookLevelSnapshot {
            price: price(number(level, "price").unwrap_or(0.0)),
            qty: format_qty(number(level, "qty").unwrap_or(0.0)),
            cumulative_qty: format_qty(number(level, "cumulative_qty").unwrap_or(0.0)),
        })
        .collect()
}

fn signal_snapshot(
    signal: Option<&StrategySignalRow>,
    quote: Option<&QuotePoint>,
) -> StrategySignalSnapshot {
    let Some(signal) = signal else {
        return StrategySignalSnapshot {
            profile: "market_quote".to_string(),
            signal: quote
                .map(|value| format!("{:+.3}", value.signal))
                .unwrap_or_else(|| "—".to_string()),
            threshold: "—".to_string(),
            reason: "quote event signal".to_string(),
            observed_quote: quote
                .map(|value| format!("bid {} / ask {}", price(value.bid), price(value.ask)))
                .unwrap_or_else(|| "—".to_string()),
            observed_ts_us: "—".to_string(),
        };
    };
    StrategySignalSnapshot {
        profile: signal.profile.clone(),
        signal: format!("{:+.3}", signal.signal),
        threshold: signal.threshold.clone(),
        reason: signal.reason.clone(),
        observed_quote: if signal.observed_quote == "—" {
            quote
                .map(|value| format!("bid {} / ask {}", price(value.bid), price(value.ask)))
                .unwrap_or_else(|| "—".to_string())
        } else {
            signal.observed_quote.clone()
        },
        observed_ts_us: signal.observed_ts_us.clone(),
    }
}

fn intent_snapshot(order: Option<&OrderRow>) -> OrderIntentSnapshot {
    let Some(order) = order else {
        return OrderIntentSnapshot::default();
    };
    OrderIntentSnapshot {
        intent_id: order.intent_id.clone(),
        client_order_id: order.client_order_id.clone(),
        side: order.side.clone(),
        qty: format_qty(order.qty),
        reason: order.reason.clone(),
        observed_quote: order.observed_quote.clone(),
        observed_ts_us: order.observed_ts.clone(),
    }
}

fn arrival_snapshot(order: Option<&OrderRow>, fill: Option<&FillRow>) -> OrderArrivalSnapshot {
    let Some(order) = order else {
        return OrderArrivalSnapshot::default();
    };
    OrderArrivalSnapshot {
        order_id: fill
            .map(|value| value.order_id.clone())
            .unwrap_or_else(|| order.client_order_id.clone()),
        arrival_quote: order.arrival_quote.clone(),
        arrival_ts_us: order.arrival_ts.clone(),
        actual_latency_us: order.latency.clone(),
        latency_slippage_bps: fill
            .map(|value| format!("{:+.3} bps", value.slippage))
            .unwrap_or_else(|| "—".to_string()),
        order_status: order.status.clone(),
    }
}

fn fill_snapshot(fill: Option<&FillRow>) -> FillSnapshot {
    let Some(fill) = fill else {
        return FillSnapshot::default();
    };
    FillSnapshot {
        fill_id: fill.fill_id.clone(),
        order_id: fill.order_id.clone(),
        side: fill.side.clone(),
        price: price(fill.price),
        qty: format_qty(fill.qty),
        fee: format!("{:.8}", fill.fee),
        liquidity: fill.liquidity.clone(),
        realized_pnl_delta: format!("{:+.6}", fill.realized_delta),
        net_pnl_delta: format!("{:+.6}", fill.net_delta),
        attribution: format!(
            "gross {:+.6} · latency {:+.6} · spread {:+.6} · fee {:+.6}",
            fill.gross_execution_pnl,
            fill.latency_mark_pnl,
            fill.spread_execution_cost,
            fill.fee_pnl
        ),
    }
}

fn position_snapshot(account: &Value) -> PositionSnapshot {
    PositionSnapshot {
        position_qty: format_qty(number(account, "position_qty").unwrap_or(0.0)),
        avg_entry_price: price(number(account, "avg_entry_price").unwrap_or(0.0)),
        equity: price(number(account, "equity").unwrap_or(0.0)),
        fees_paid: price(number(account, "fees_paid").unwrap_or(0.0)),
    }
}
fn pnl_snapshot(account: &Value, fill: Option<&FillRow>) -> PnlSnapshot {
    PnlSnapshot {
        realized_pnl: format!("{:+.6}", number(account, "realized_pnl").unwrap_or(0.0)),
        unrealized_pnl: format!("{:+.6}", number(account, "unrealized_pnl").unwrap_or(0.0)),
        selected_fill_delta: format!("{:+.6}", fill.map(|value| value.net_delta).unwrap_or(0.0)),
        net_equity: price(number(account, "equity").unwrap_or(0.0)),
    }
}

fn l2_quality_snapshot(preflight: Option<&Value>, snapshot_batches: usize) -> L2QualitySnapshot {
    let Some(preflight) = preflight.filter(|value| value.is_object()) else {
        return if snapshot_batches > 0 {
            L2QualitySnapshot {
                status: "WARNING".to_string(),
                warning: "L2 warning · snapshot-heavy batches; incremental semantics not verified"
                    .to_string(),
            }
        } else {
            L2QualitySnapshot {
                status: "TOP OF BOOK".to_string(),
                warning: "L2 not loaded · top-of-book replay".to_string(),
            }
        };
    };
    let status = scalar(preflight, "status")
        .unwrap_or_else(|| "WARNING".to_string())
        .to_uppercase();
    let warning = preflight
        .get("warnings")
        .and_then(Value::as_array)
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .map(|value| format!("L2 warning · {value}"))
        .unwrap_or_else(|| {
            if snapshot_batches > 0 {
                "L2 warning · snapshot-heavy batches; queue replay disabled".to_string()
            } else {
                "L2 preflight available".to_string()
            }
        });
    L2QualitySnapshot { status, warning }
}

fn event_tape(events: &[Value], end: usize) -> String {
    events
        .iter()
        .take(end + 1)
        .rev()
        .take(18)
        .map(|event| {
            format!(
                "{}  {:<18}  seq {:<7}  {}",
                text(event, "replay_ts"),
                text(event, "event_type"),
                number(event, "replay_seq").unwrap_or(0.0) as u64,
                text(event, "source")
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}
fn order_text(rows: &[&OrderRow]) -> String {
    if rows.is_empty() {
        return "No order intents at this cursor.".to_string();
    }
    rows.iter().rev().take(12).map(|row| format!("{}  {}  {:<5} {:>8.3}  {:<10}  obs {}  arr {}  {}\n  signal {} / threshold {}\n  observed {}\n  arrival {}\n  {}", row.intent_id, row.client_order_id, row.side, row.qty, row.status, row.observed_ts, row.arrival_ts, row.latency, row.signal, row.threshold, row.observed_quote, row.arrival_quote, row.reason)).collect::<Vec<_>>().join("\n")
}
fn fill_text(rows: &[&FillRow]) -> String {
    if rows.is_empty() {
        return "No fills at this cursor.".to_string();
    }
    rows.iter()
        .rev()
        .take(12)
        .map(|row| {
            format!(
                "{}  order {}  {:<5} {:>8.3} @ {}  fee {:.6}  {}  ΔPnL {:+.6}",
                row.fill_id,
                row.order_id,
                row.side,
                row.qty,
                price(row.price),
                row.fee,
                row.liquidity,
                row.net_delta
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}
fn position_text(account: &Value, fill: Option<&FillRow>) -> String {
    format!(
        "Position  {}\nAvg entry  {}\nEquity  {}\nFees paid  {}",
        number(account, "position_qty").unwrap_or(0.0),
        price(number(account, "avg_entry_price").unwrap_or(0.0)),
        price(number(account, "equity").unwrap_or(0.0)),
        price(number(account, "fees_paid").unwrap_or(fill.map(|f| f.fee).unwrap_or(0.0)))
    )
}
fn pnl_text(account: &Value, fill: Option<&FillRow>) -> String {
    format!(
        "Realized PnL  {:+.6}\nUnrealized PnL  {:+.6}\nSelected fill Δ  {:+.6}\nNet equity  {}",
        number(account, "realized_pnl").unwrap_or(0.0),
        number(account, "unrealized_pnl").unwrap_or(0.0),
        fill.map(|f| f.net_delta).unwrap_or(0.0),
        price(number(account, "equity").unwrap_or(0.0))
    )
}
fn book_text(
    quote: Option<&QuotePoint>,
    book: Option<&Value>,
    updates: usize,
    snapshots: usize,
) -> String {
    if let Some(book) = book {
        let asks = depth_text(book.get("ask_depth"), "ASK");
        let bids = depth_text(book.get("bid_depth"), "BID");
        let best_bid =
            number(book, "best_bid").unwrap_or_else(|| quote.map(|q| q.bid).unwrap_or(0.0));
        let best_ask =
            number(book, "best_ask").unwrap_or_else(|| quote.map(|q| q.ask).unwrap_or(0.0));
        let mid = if best_bid > 0.0 && best_ask > 0.0 {
            (best_bid + best_ask) * 0.5
        } else {
            quote.map(|q| q.mid).unwrap_or(0.0)
        };
        return format!(
            "{}\nSPREAD  {:.2} bps\nMID    {}\n{}\n\n{} L2 updates · {} snapshot batches",
            asks,
            (best_ask - best_bid) / mid.max(f64::EPSILON) * 10_000.0,
            price(mid),
            bids,
            updates,
            snapshots
        );
    }
    quote.map(|q| format!("ASK  {}  × {}\n       cumulative {}\nSPREAD  {} bps\nMID    {}\nBID  {}  × {}\n       cumulative {}\n\n{} L2 updates · {} snapshot batches", price(q.ask), q.ask_qty, q.ask_qty, (q.ask - q.bid) / q.mid * 10_000.0, price(q.mid), price(q.bid), q.bid_qty, q.bid_qty, updates, snapshots)).unwrap_or_else(|| "No quote at this cursor.".to_string())
}
fn depth_text(value: Option<&Value>, label: &str) -> String {
    let Some(levels) = value.and_then(Value::as_array) else {
        return format!("{label}  —");
    };
    let lines = levels
        .iter()
        .take(5)
        .map(|level| {
            format!(
                "{label}  {} × {}  cum {}",
                price(number(level, "price").unwrap_or(0.0)),
                number(level, "qty").unwrap_or(0.0),
                number(level, "cumulative_qty").unwrap_or(0.0)
            )
        })
        .collect::<Vec<_>>();
    if lines.is_empty() {
        format!("{label}  —")
    } else {
        lines.join("\n")
    }
}
fn chart_text(quotes: &[&QuotePoint]) -> String {
    if quotes.is_empty() {
        return "Waiting for the first market quote…".to_string();
    }
    let values: Vec<f64> = quotes.iter().rev().take(64).map(|q| q.mid).collect();
    let min = values.iter().copied().fold(f64::INFINITY, f64::min);
    let max = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let blocks = "▁▂▃▄▅▆▇█";
    values
        .iter()
        .rev()
        .map(|value| {
            let idx = if (max - min).abs() < f64::EPSILON {
                4
            } else {
                (((value - min) / (max - min)) * 7.0).round() as usize
            };
            blocks.chars().nth(idx.min(7)).unwrap_or('▅')
        })
        .collect::<String>()
}
fn causal_text(fill: Option<&FillRow>, orders: &[OrderRow]) -> String {
    let Some(fill) = fill else {
        return "Select a fill to inspect the complete causal chain.".to_string();
    };
    let order = orders.iter().find(|row| row.intent_id == fill.intent_id);
    let reason = order.map(|o| o.reason.as_str()).unwrap_or("—");
    let signal = order.map(|o| o.signal.as_str()).unwrap_or("—");
    let threshold = order.map(|o| o.threshold.as_str()).unwrap_or("—");
    let observed_quote = order
        .map(|o| o.observed_quote.as_str())
        .unwrap_or(fill.observed_quote.as_str());
    format!(
        "TRADE {}\n{} {} @ {}\n\nSIGNAL\n  reason: {}\n  intent: {}\n  signal / threshold: {} / {}\n\nOBSERVED QUOTE\n  {}\n\nARRIVAL\n  order: {}\n  {}\n  latency: {}\n  latency slippage: {:+.3} bps\n\nFILL\n  {} {} @ {}\n  {} · fee {}\n\nATTRIBUTION\n  gross execution PnL: {:+.6}\n  latency mark PnL: {:+.6}\n  spread execution cost: {:+.6}\n  fee PnL: {:+.6}\n  adverse selection: {}\n  realized PnL delta: {:+.6}\n  net PnL delta: {:+.6}",
        fill.fill_id,
        fill.side,
        fill.qty,
        price(fill.price),
        reason,
        fill.intent_id,
        signal,
        threshold,
        observed_quote,
        fill.order_id,
        fill.arrival_quote,
        fill.latency,
        fill.slippage,
        fill.side,
        fill.qty,
        price(fill.price),
        fill.liquidity,
        price(fill.fee),
        fill.gross_execution_pnl,
        fill.latency_mark_pnl,
        fill.spread_execution_cost,
        fill.fee_pnl,
        fill.adverse_selection,
        fill.realized_delta,
        fill.net_delta
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repository_can_open_a_runner_artifact_directory() {
        let run_dir = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../systems/quant_replay_engine/runs/qrs_tob_smoke_20261001");
        if !run_dir.join("events.ndjson").exists() {
            return;
        }
        let repository = RunRepository::open(&run_dir).expect("runner artifacts should load");
        let snapshot = ReplaySession::new(repository.clone()).snapshot();
        assert!(snapshot
            .event_cursor
            .ends_with(&repository.len().to_string()));
        assert!(!snapshot.raw_event.is_empty());
    }

    #[test]
    fn list_runs_reads_metadata_without_requiring_events() {
        let run_root =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../systems/quant_replay_engine/runs");
        let runs = RunRepository::list_runs(&run_root);
        assert!(runs
            .iter()
            .any(|run| run.run_id == "qrs_tob_smoke_20261001"));
        let run = runs
            .iter()
            .find(|run| run.run_id == "qrs_tob_smoke_20261001")
            .expect("smoke run metadata");
        assert_eq!(run.symbol, "CCUSDT");
        assert_eq!(run.event_count, 293);
        assert_eq!(run.order_count, 1);
        assert_eq!(run.fill_count, 1);
        assert!(!run.run_directory.is_empty());
    }

    #[test]
    fn native_and_l2_artifacts_preserve_causal_and_quality_state() {
        let root =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../systems/quant_replay_engine/runs");
        let native =
            RunRepository::open(&root.join("qrs_native_product_smoke")).expect("native artifacts");
        let native_snapshot = ReplaySession {
            repository: native,
            cursor: usize::MAX,
            playing: false,
            speed: 1.0,
            selected_fill: None,
            tab: "Fills".to_string(),
        }
        .snapshot();
        assert_ne!(native_snapshot.fill.fill_id, "—");
        assert_ne!(native_snapshot.order_intent.intent_id, "—");
        assert_ne!(native_snapshot.strategy_signal.signal, "");

        let l2 = RunRepository::open(&root.join("qrs_1790951516603")).expect("l2 artifacts");
        let l2_snapshot = ReplaySession {
            repository: l2,
            cursor: usize::MAX,
            playing: false,
            speed: 1.0,
            selected_fill: None,
            tab: "Event Tape".to_string(),
        }
        .snapshot();
        assert_eq!(l2_snapshot.l2_quality.status, "SAMPLED_OK");
        assert!(l2_snapshot.warning.contains("L2 warning"));
    }
}

use std::collections::VecDeque;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use ccusdt_exchange_sim::PaperExchange;
use ccusdt_replay_core::{
    AccountView, ExchangeConfig, ExchangeSnapshot, MarketFrame, NewOrder, Order, OrderKind, Side,
    TimeInForce,
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

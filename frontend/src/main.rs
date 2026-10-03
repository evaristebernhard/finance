mod replay_repository;

use replay_repository::{
    FillSnapshot, OrderArrivalSnapshot, OrderBookSnapshot, OrderIntentSnapshot, PnlSnapshot,
    PositionSnapshot, ReplaySession, ReplaySnapshot, RunEntry, RunRepository,
};
use slint::Timer;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

slint::include_modules!();

#[derive(Default)]
struct AppState {
    replay: Option<ReplaySession>,
    progress_path: Option<PathBuf>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let window = MainWindow::new()?;
    let repo_root = find_repo_root();
    let run_root = repo_root.join("systems/quant_replay_engine/runs");
    let dataset = inspect_dataset(&repo_root, "CCUSDT", "2026-10-01");
    window.set_dataset_status(dataset.status.into());
    window.set_l2_quality(dataset.l2_quality.into());
    window.set_raw_size(dataset.raw_size.into());
    refresh_run_library(&window, &run_root);

    let state = Arc::new(Mutex::new(AppState::default()));
    let weak = window.as_weak();
    if let Ok(run_dir) = std::env::var("QRS_RUN_DIR") {
        load_run_async(&weak, &state, PathBuf::from(run_dir));
    }
    {
        let state = state.clone();
        let weak = weak.clone();
        let run_root = run_root.clone();
        window.on_navigate(move |page| {
            if let Some(window) = weak.upgrade() {
                window.set_current_page(page.clone());
                if page == "library" {
                    refresh_run_library(&window, &run_root);
                }
            }
            if page == "workbench" {
                refresh_window(&weak, &state);
            }
        });
    }
    {
        let weak = weak.clone();
        window.on_create_run(move || {
            if let Some(window) = weak.upgrade() {
                window.set_current_page("setup".into());
            }
        });
    }
    {
        let state = state.clone();
        let weak = weak.clone();
        let run_root = run_root.clone();
        window.on_open_run(move |run_id| open_run(&weak, &state, &run_root, run_id.to_string()));
    }
    {
        let weak = weak.clone();
        window.on_select_run(move |run_id| {
            if let Some(window) = weak.upgrade() {
                window.set_selected_run_id(run_id);
            }
        });
    }
    {
        let state = state.clone();
        let root = repo_root.clone();
        let weak = weak.clone();
        window.on_run_backtest(move || start_run(&weak, &state, &root));
    }
    {
        let weak = weak.clone();
        window.on_choose_fill_model(move |model| {
            if let Some(window) = weak.upgrade() {
                window.set_fill_model(model);
            }
        });
    }
    {
        let weak = weak.clone();
        window.on_choose_strategy(move |profile| {
            if let Some(window) = weak.upgrade() {
                window.set_strategy_profile(profile);
            }
        });
    }
    {
        let state = state.clone();
        let weak = weak.clone();
        window.on_replay_command(move |command| {
            let mut state = state.lock().expect("replay state lock");
            let Some(session) = state.replay.as_mut() else {
                return;
            };
            match command.as_str() {
                "play" => session.playing = true,
                "pause" => session.playing = false,
                "step_back" => session.step(-1),
                "step_forward" => session.step(1),
                "reset" => {
                    session.cursor = 0;
                    session.playing = false;
                    session.selected_fill = None;
                }
                "speed_up" => session.speed = (session.speed * 2.0).min(16.0),
                "speed_down" => session.speed = (session.speed / 2.0).max(0.25),
                _ => {}
            }
            let snapshot = session.snapshot();
            drop(state);
            apply_snapshot(&weak, snapshot);
        });
    }
    {
        let state = state.clone();
        let weak = weak.clone();
        window.on_seek(move |fraction| {
            let mut state = state.lock().expect("replay state lock");
            if let Some(session) = state.replay.as_mut() {
                session.seek(fraction as f64);
                let snapshot = session.snapshot();
                drop(state);
                apply_snapshot(&weak, snapshot);
            }
        });
    }
    {
        let state = state.clone();
        let weak = weak.clone();
        window.on_select_fill(move |fill_id| {
            let mut state = state.lock().expect("replay state lock");
            if let Some(session) = state.replay.as_mut() {
                session.selected_fill = Some(fill_id.to_string());
                let snapshot = session.snapshot();
                drop(state);
                apply_snapshot(&weak, snapshot);
            }
        });
    }
    {
        let state = state.clone();
        let weak = weak.clone();
        window.on_select_tab(move |tab| {
            let mut state = state.lock().expect("replay state lock");
            if let Some(session) = state.replay.as_mut() {
                session.tab = tab.to_string();
                let snapshot = session.snapshot();
                drop(state);
                apply_snapshot(&weak, snapshot);
            }
        });
    }

    let timer = Timer::default();
    {
        let state = state.clone();
        let weak = weak.clone();
        timer.start(slint::TimerMode::Repeated, Duration::from_millis(75), move || {
            let (snapshot, progress_path) = {
                let mut state = state.lock().expect("replay state lock");
                if let Some(session) = state.replay.as_mut() {
                    if session.playing {
                        session.tick();
                        (Some(session.snapshot()), None)
                    } else {
                        (None, None)
                    }
                } else {
                    (None, state.progress_path.clone())
                }
            };
            if let Some(snapshot) = snapshot {
                apply_snapshot(&weak, snapshot);
            }
            if let Some(path) = progress_path {
                if let Ok(raw) = std::fs::read_to_string(path) {
                    if let Ok(progress) = serde_json::from_str::<serde_json::Value>(&raw) {
                        let events = progress.get("events_processed").and_then(|v| v.as_u64()).unwrap_or(0);
                        let quotes = progress.get("quotes").and_then(|v| v.as_u64()).unwrap_or(0);
                        let trades = progress.get("trades").and_then(|v| v.as_u64()).unwrap_or(0);
                        let l2 = progress.get("l2_batches").and_then(|v| v.as_u64()).unwrap_or(0);
                        let orders = progress.get("orders").and_then(|v| v.as_u64()).unwrap_or(0);
                        let fills = progress.get("fills").and_then(|v| v.as_u64()).unwrap_or(0);
                        if let Some(window) = weak.upgrade() {
                            window.set_run_phase(format!("RUNNER ACTIVE · {events} EVENTS").into());
                            window.set_run_detail(format!("events processed {events} · quotes {quotes} · trades {trades} · L2 batches {l2} · orders {orders} · fills {fills}").into());
                        }
                    }
                }
            }
        });
    }
    window.run()?;
    Ok(())
}

fn refresh_run_library(window: &MainWindow, run_root: &Path) {
    let runs = RunRepository::list_runs(run_root);
    window.set_run_count(format!("{} RUNS", runs.len()).into());
    window.set_run_root(run_root.to_string_lossy().replace('\\', "/").into());
    for slot in 0..6 {
        set_run_slot(window, slot, runs.get(slot));
    }
}

fn set_run_slot(window: &MainWindow, slot: usize, entry: Option<&RunEntry>) {
    let value =
        |field: fn(&RunEntry) -> String| entry.map(field).unwrap_or_else(|| "—".to_string());
    let count = |field: fn(&RunEntry) -> usize| entry.map(field).unwrap_or(0);
    let run_id = value(|run| run.run_id.clone());
    let dataset = value(|run| run.dataset_date.clone());
    let strategy = value(|run| format!("{} / {}", run.strategy, run.execution_model));
    let stats = entry
        .map(|run| {
            format!(
                "{} events · {} orders · {} fills",
                run.event_count, run.order_count, run.fill_count
            )
        })
        .unwrap_or_else(|| "—".to_string());
    let status = value(|run| run.status.clone());
    let symbol = value(|run| run.symbol.clone());
    let _ = count;
    let _ = entry.map(|run| &run.run_directory);
    match slot {
        0 => {
            window.set_run_1_id(run_id.into());
            window.set_run_1_dataset(dataset.into());
            window.set_run_1_strategy(strategy.into());
            window.set_run_1_stats(stats.into());
            window.set_run_1_status(status.into());
            window.set_run_1_symbol(symbol.into());
        }
        1 => {
            window.set_run_2_id(run_id.into());
            window.set_run_2_dataset(dataset.into());
            window.set_run_2_strategy(strategy.into());
            window.set_run_2_stats(stats.into());
            window.set_run_2_status(status.into());
            window.set_run_2_symbol(symbol.into());
        }
        2 => {
            window.set_run_3_id(run_id.into());
            window.set_run_3_dataset(dataset.into());
            window.set_run_3_strategy(strategy.into());
            window.set_run_3_stats(stats.into());
            window.set_run_3_status(status.into());
            window.set_run_3_symbol(symbol.into());
        }
        3 => {
            window.set_run_4_id(run_id.into());
            window.set_run_4_dataset(dataset.into());
            window.set_run_4_strategy(strategy.into());
            window.set_run_4_stats(stats.into());
            window.set_run_4_status(status.into());
            window.set_run_4_symbol(symbol.into());
        }
        4 => {
            window.set_run_5_id(run_id.into());
            window.set_run_5_dataset(dataset.into());
            window.set_run_5_strategy(strategy.into());
            window.set_run_5_stats(stats.into());
            window.set_run_5_status(status.into());
            window.set_run_5_symbol(symbol.into());
        }
        5 => {
            window.set_run_6_id(run_id.into());
            window.set_run_6_dataset(dataset.into());
            window.set_run_6_strategy(strategy.into());
            window.set_run_6_stats(stats.into());
            window.set_run_6_status(status.into());
            window.set_run_6_symbol(symbol.into());
        }
        _ => {}
    }
}

fn open_run(
    weak: &slint::Weak<MainWindow>,
    state: &Arc<Mutex<AppState>>,
    run_root: &Path,
    run_id: String,
) {
    if run_id == "—" || run_id.contains('/') || run_id.contains('\\') || run_id.contains("..") {
        return;
    }
    let run_dir = run_root.join(&run_id);
    load_run_async(weak, state, run_dir);
}

fn load_run_async(weak: &slint::Weak<MainWindow>, state: &Arc<Mutex<AppState>>, run_dir: PathBuf) {
    let Some(window) = weak.upgrade() else {
        return;
    };
    window.set_current_page("workbench".into());
    window.set_run_state("loading".into());
    window.set_run_phase("LOADING RUN".into());
    window.set_run_detail("Loading manifest / summary / events / replay_index…".into());
    let state_for_load = state.clone();
    let weak_for_load = weak.clone();
    thread::spawn(move || match RunRepository::open(&run_dir) {
        Ok(repository) => {
            let mut app = state_for_load.lock().expect("replay state lock");
            app.replay = Some(ReplaySession::new(repository));
            let snapshot = app.replay.as_ref().expect("loaded replay").snapshot();
            drop(app);
            let run_dir_text = run_dir.to_string_lossy().replace('\\', "/");
            let _ = slint::invoke_from_event_loop(move || {
                if let Some(window) = weak_for_load.upgrade() {
                    window.set_run_state("complete".into());
                    window.set_run_phase("RUN COMPLETE".into());
                    window.set_run_detail("Loaded Runner artifacts.".into());
                    window.set_run_dir(run_dir_text.into());
                    window.set_selected_run_id(snapshot.run_id.clone().into());
                }
                apply_snapshot(&weak_for_load, snapshot);
            });
        }
        Err(error) => {
            let _ = slint::invoke_from_event_loop(move || {
                if let Some(window) = weak_for_load.upgrade() {
                    window.set_run_state("error".into());
                    window.set_run_phase("RUN LOAD ERROR".into());
                    window.set_run_detail(error.into());
                }
            });
        }
    });
}

fn start_run(weak: &slint::Weak<MainWindow>, state: &Arc<Mutex<AppState>>, repo_root: &Path) {
    let Some(window) = weak.upgrade() else {
        return;
    };
    if window.get_run_state() == "running" {
        return;
    }
    let date = window.get_dataset_date().to_string();
    let fill_model = window.get_fill_model().to_string();
    let profile = window.get_strategy_profile().to_string();
    let latency = window.get_latency_us();
    let cash = window.get_starting_cash();
    let run_id = format!("qrs_{}", timestamp_ms());
    let run_root = repo_root.join("systems/quant_replay_engine/runs");
    let runner = repo_root.join("systems/quant_replay_engine/target/debug/quant_replay_cli");
    window.set_run_state("running".into());
    window.set_run_phase("RUNNER ACTIVE".into());
    window.set_run_detail("正在读取 canonical quote / trade / L2 事件…".into());
    window.set_status_message(
        "Runner 正在生成事件级 artifacts；完成后自动打开 Replay Workbench。".into(),
    );
    window.set_current_run(run_id.clone().into());
    window.set_current_page("workbench".into());
    let weak = weak.clone();
    let state = state.clone();
    let root = repo_root.to_path_buf();
    {
        let mut app = state.lock().expect("replay state lock");
        app.replay = None;
        app.progress_path = Some(run_root.join(&run_id).join("progress.json"));
    }
    thread::spawn(move || {
        if !runner.exists() {
            finish_error(
                &weak,
                format!("Runner binary not found: {}", runner.display()),
            );
            return;
        }
        let mut command = Command::new(&runner);
        command.current_dir(&root).args([
            "run",
            "native",
            "--repo-root",
            ".",
            "--canonical-date",
            &date,
            "--run-root",
            run_root.to_string_lossy().as_ref(),
            "--run-id",
            &run_id,
            "--max-events",
            "25000",
            "--latency-us",
            &latency.to_string(),
            "--fill-model",
            &fill_model,
            "--profile",
            &profile,
            "--threshold",
            "0.35",
            "--max-orders",
            "12",
            "--starting-cash",
            &cash.to_string(),
        ]);
        if fill_model == "l2-depth" {
            command.arg("--include-l2");
        }
        match command.status() {
            Ok(status) if status.success() => match RunRepository::open(&run_root.join(&run_id)) {
                Ok(repository) => {
                    let mut app = state.lock().expect("replay state lock");
                    app.replay = Some(ReplaySession::new(repository));
                    app.progress_path = None;
                    let snapshot = app
                        .replay
                        .as_ref()
                        .expect("session just inserted")
                        .snapshot();
                    drop(app);
                    let _ = slint::invoke_from_event_loop({
                        let weak = weak.clone();
                        move || {
                            if let Some(window) = weak.upgrade() {
                                window.set_run_state("complete".into());
                                window.set_run_phase("RUN COMPLETE".into());
                                window.set_run_detail(
                                    "manifest / summary / events / replay_index 已加载。".into(),
                                );
                                window.set_status_message(
                                    "Run 完成。现在可以播放、逐事件检查并选择成交查看因果链。"
                                        .into(),
                                );
                                window.set_run_dir(
                                    run_root
                                        .join(&run_id)
                                        .to_string_lossy()
                                        .replace('\\', "/")
                                        .into(),
                                );
                                window.set_selected_run_id(run_id.clone().into());
                                refresh_run_library(&window, &run_root);
                            }
                            apply_snapshot(&weak, snapshot);
                        }
                    });
                }
                Err(error) => finish_error(&weak, error),
            },
            Ok(status) => finish_error(&weak, format!("Runner 退出状态: {status}")),
            Err(error) => finish_error(&weak, format!("无法启动 Runner: {error}")),
        }
    });
}

fn finish_error(weak: &slint::Weak<MainWindow>, message: String) {
    let _ = slint::invoke_from_event_loop({
        let weak = weak.clone();
        move || {
            if let Some(window) = weak.upgrade() {
                window.set_run_state("error".into());
                window.set_run_phase("RUNNER ERROR".into());
                window.set_run_detail(message.clone().into());
                window.set_status_message(message.into());
            }
        }
    });
}
fn refresh_window(weak: &slint::Weak<MainWindow>, state: &Arc<Mutex<AppState>>) {
    let state = state.lock().expect("replay state lock");
    if let Some(session) = state.replay.as_ref() {
        apply_snapshot(weak, session.snapshot());
    }
}
fn apply_snapshot(weak: &slint::Weak<MainWindow>, snapshot: ReplaySnapshot) {
    let Some(window) = weak.upgrade() else {
        return;
    };
    let quote = &snapshot.quote;
    let signal = &snapshot.strategy_signal;
    let signal_text = if signal.profile.is_empty() || signal.signal.is_empty() {
        snapshot.signal.clone()
    } else {
        format!(
            "{}  {} / {}",
            signal.profile, signal.signal, signal.threshold
        )
    };
    window.set_run_id(snapshot.run_id.into());
    window.set_symbol(snapshot.symbol.clone().into());
    window.set_dataset_date(snapshot.dataset_date.into());
    window.set_strategy_name(snapshot.strategy.into());
    window.set_execution_model(snapshot.execution_model.into());
    window.set_replay_time(snapshot.replay_time.into());
    window.set_event_cursor(snapshot.event_cursor.into());
    window.set_replay_state(snapshot.replay_state.into());
    window.set_replay_progress(snapshot.progress);
    window.set_mid(quote.mid.clone().into());
    window.set_best_bid(quote.bid.clone().into());
    window.set_best_ask(quote.ask.clone().into());
    window.set_spread(quote.spread.clone().into());
    window.set_microprice(quote.microprice.clone().into());
    window.set_signal(signal_text.into());
    window.set_chart(snapshot.chart.into());
    window.set_order_book(render_order_book(&snapshot.order_book).into());
    window.set_event_tape(snapshot.event_tape.into());
    window.set_orders_text(
        render_order_state(&snapshot.order_intent, &snapshot.order_arrival).into(),
    );
    window.set_fills_text(render_fill_state(&snapshot.fill).into());
    window.set_position_text(render_position(&snapshot.position).into());
    window.set_pnl_text(render_pnl(&snapshot.pnl).into());
    let trade_summary = if snapshot.fill.fill_id == "—" || snapshot.fill.fill_id.is_empty() {
        "No fill at this cursor".to_string()
    } else {
        format!(
            "{} {} {} @ {}",
            snapshot.fill.side, snapshot.fill.qty, snapshot.symbol, snapshot.fill.price
        )
    };
    let trade_detail = if snapshot.fill.fill_id == "—" || snapshot.fill.fill_id.is_empty() {
        "Move the cursor to an order or fill event to inspect the execution story.".to_string()
    } else {
        format!(
            "Fill {} · order {} · {} · fee {}",
            snapshot.fill.fill_id,
            snapshot.fill.order_id,
            snapshot.fill.liquidity,
            snapshot.fill.fee
        )
    };
    window.set_trade_summary(trade_summary.into());
    window.set_trade_detail(trade_detail.into());
    window.set_signal_story(
        format!("{} · {}\n{}", signal.profile, signal.signal, signal.reason).into(),
    );
    window.set_arrival_story(
        format!(
            "{} · {} · {}",
            snapshot.order_arrival.arrival_quote,
            snapshot.order_arrival.actual_latency_us,
            snapshot.order_arrival.latency_slippage_bps
        )
        .into(),
    );
    window.set_execution_story(
        format!("{}\n{}", snapshot.fill.price, snapshot.fill.attribution).into(),
    );
    window.set_account_story(
        format!(
            "Position {} · equity {}\nRealized {} · unrealized {}",
            snapshot.position.position_qty,
            snapshot.position.equity,
            snapshot.pnl.realized_pnl,
            snapshot.pnl.unrealized_pnl
        )
        .into(),
    );
    window.set_causal_text(snapshot.causal.into());
    window.set_l2_warning(snapshot.l2_quality.warning.into());
    window.set_raw_event(snapshot.raw_event.into());
    window.set_selected_fill(snapshot.selected_fill.into());
}

fn render_order_book(book: &OrderBookSnapshot) -> String {
    let bids = book
        .bids
        .iter()
        .map(|level| format!("BID  {} × {}", level.price, level.qty))
        .collect::<Vec<_>>()
        .join("\n");
    let asks = book
        .asks
        .iter()
        .map(|level| format!("ASK  {} × {}", level.price, level.qty))
        .collect::<Vec<_>>()
        .join("\n");
    format!(
        "ASK {}\n{}\n\nBEST BID / SPREAD  {} / {}\n\n{}\n\n{} updates · {} snapshot batches · {}",
        book.best_ask,
        asks,
        book.best_bid,
        book.spread,
        bids,
        book.update_count,
        book.snapshot_batch_count,
        book.quality
    )
}

fn render_order_state(intent: &OrderIntentSnapshot, arrival: &OrderArrivalSnapshot) -> String {
    if intent.intent_id == "" || intent.intent_id == "—" {
        return "No order intent at this cursor.".to_string();
    }
    format!(
        "{}  {} {} × {}\nreason: {}\nobserved: {} at {}\narrival: {} at {}\nlatency: {} · slippage {}\nstatus: {}",
        intent.intent_id,
        intent.side,
        intent.client_order_id,
        intent.qty,
        intent.reason,
        intent.observed_quote,
        intent.observed_ts_us,
        arrival.arrival_quote,
        arrival.arrival_ts_us,
        arrival.actual_latency_us,
        arrival.latency_slippage_bps,
        arrival.order_status
    )
}

fn render_fill_state(fill: &FillSnapshot) -> String {
    if fill.fill_id == "" || fill.fill_id == "—" {
        return "No fill at this cursor.".to_string();
    }
    format!(
        "{}  order {}\n{} @ {}\nfee {} · {}\nrealized {} · net {}\n{}",
        fill.fill_id,
        fill.order_id,
        fill.qty,
        fill.price,
        fill.fee,
        fill.liquidity,
        fill.realized_pnl_delta,
        fill.net_pnl_delta,
        fill.attribution
    )
}

fn render_position(position: &PositionSnapshot) -> String {
    format!(
        "Position  {}\nAvg entry  {}\nEquity  {}\nFees paid  {}",
        position.position_qty, position.avg_entry_price, position.equity, position.fees_paid
    )
}
fn render_pnl(pnl: &PnlSnapshot) -> String {
    format!(
        "Realized PnL  {}\nUnrealized PnL  {}\nSelected fill Δ  {}\nNet equity  {}",
        pnl.realized_pnl, pnl.unrealized_pnl, pnl.selected_fill_delta, pnl.net_equity
    )
}

#[derive(Default)]
struct DatasetUi {
    status: String,
    l2_quality: String,
    raw_size: String,
}
fn inspect_dataset(repo_root: &Path, symbol: &str, date: &str) -> DatasetUi {
    let raw_root = repo_root.join("data/ccusdt/v1/external").join(format!(
        "bullish_incremental_book_L2/symbol={symbol}/dt={date}"
    ));
    let raw_size = std::fs::read_dir(&raw_root)
        .ok()
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .filter_map(|entry| entry.metadata().ok())
        .map(|meta| meta.len())
        .sum::<u64>();
    let canonical = repo_root.join("data/canonical/cex/bullish").join(symbol);
    let quote = canonical.join(format!("quote_frame_v1/dt={date}/part_000001.csv.gz"));
    let l2 = canonical.join(format!("l2_level_update_v1/dt={date}/part_000001.csv.gz"));
    if quote.exists() {
        DatasetUi {
            status: "CANONICAL READY".into(),
            l2_quality: if l2.exists() {
                "L2 preflight available".into()
            } else {
                "Snapshot-heavy / L2 optional".into()
            },
            raw_size: format_bytes(raw_size),
        }
    } else if raw_size > 0 {
        DatasetUi {
            status: "RAW DOWNLOADED".into(),
            l2_quality: "Canonical build required".into(),
            raw_size: format_bytes(raw_size),
        }
    } else {
        DatasetUi {
            status: "DATASET NOT FOUND".into(),
            l2_quality: "Import or build a dataset".into(),
            raw_size: "—".into(),
        }
    }
}
fn format_bytes(bytes: u64) -> String {
    if bytes >= 1_000_000_000 {
        format!("{:.1} GB", bytes as f64 / 1e9)
    } else if bytes >= 1_000_000 {
        format!("{:.1} MB", bytes as f64 / 1e6)
    } else if bytes >= 1_000 {
        format!("{:.1} KB", bytes as f64 / 1e3)
    } else {
        format!("{bytes} B")
    }
}
fn find_repo_root() -> PathBuf {
    if let Ok(path) = std::env::var("QRS_REPO_ROOT") {
        return PathBuf::from(path);
    }
    std::env::current_dir()
        .ok()
        .filter(|path| path.join("systems/quant_replay_engine").is_dir())
        .or_else(|| Some(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")))
        .unwrap_or_else(|| PathBuf::from("."))
}
fn timestamp_ms() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or_default()
}

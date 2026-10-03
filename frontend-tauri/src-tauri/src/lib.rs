#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[allow(dead_code)]
#[path = "../../../frontend/src/replay_repository.rs"]
mod replay_repository;

use replay_repository::{RunEntry, RunRepository};
#[path = "../../../frontend/src/replay_v2.rs"]
mod replay_v2;
use replay_v2::{Repository, Session};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{Emitter, Manager};

struct AppState {
    repo_root: PathBuf,
    run_root: PathBuf,
    session: Mutex<Option<Session>>,
    generation: AtomicU64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RunEntryDto {
    run_id: String,
    dataset_date: String,
    symbol: String,
    strategy: String,
    execution_model: String,
    event_count: usize,
    order_count: usize,
    fill_count: usize,
    status: String,
    run_directory: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RunConfig {
    date: String,
    profile: String,
    fill_model: String,
    latency_us: u64,
    fee_bps: f64,
    starting_cash: f64,
}

fn repo_root() -> PathBuf {
    std::env::var_os("QRS_REPO_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

fn app_state() -> AppState {
    let root = repo_root();
    AppState {
        run_root: root.join("systems/quant_replay_engine/runs"),
        repo_root: root,
        session: Mutex::new(None),
        generation: AtomicU64::new(0),
    }
}

#[tauri::command]
fn list_runs(state: tauri::State<'_, AppState>) -> Vec<RunEntryDto> {
    RunRepository::list_runs(&state.run_root)
        .into_iter()
        .map(run_entry)
        .collect()
}

fn invalidate(state: &AppState) -> Result<u64, String> {
    let mut guard = state
        .session
        .lock()
        .map_err(|_| "replay state lock poisoned")?;
    let id = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    if let Some(s) = guard.as_mut() {
        s.playing = false;
    }
    Ok(id)
}
fn install(state: &AppState, repository: Repository, id: u64) -> Result<Value, String> {
    let mut guard = state
        .session
        .lock()
        .map_err(|_| "replay state lock poisoned")?;
    if state.generation.load(Ordering::SeqCst) != id {
        return Err("superseded open request".into());
    }
    let mut session = Session::new(repository, id);
    let snapshot = session.snapshot()?;
    *guard = Some(session);
    Ok(snapshot)
}

#[tauri::command]
async fn open_run(run_id: String, state: tauri::State<'_, AppState>) -> Result<Value, String> {
    let dir = safe_run_directory(&state.run_root, &run_id)?;
    let id = invalidate(&state)?;
    let repository = tauri::async_runtime::spawn_blocking(move || Repository::open(&dir))
        .await
        .map_err(|e| e.to_string())??;
    install(&state, repository, id)
}

fn with_session(
    state: &AppState,
    f: impl FnOnce(&mut Session) -> Result<Value, String>,
) -> Result<Value, String> {
    let mut guard = state
        .session
        .lock()
        .map_err(|_| "replay state lock poisoned")?;
    f(guard.as_mut().ok_or("open a run first")?)
}
#[tauri::command]
fn replay_command(command: String, state: tauri::State<'_, AppState>) -> Result<Value, String> {
    with_session(&state, |s| {
        s.command(&command)?;
        s.snapshot()
    })
}
#[tauri::command]
fn seek(fraction: f64, state: tauri::State<'_, AppState>) -> Result<Value, String> {
    with_session(&state, |s| {
        s.seek(fraction)?;
        s.snapshot()
    })
}
#[tauri::command]
fn select_fill(fill_id: String, state: tauri::State<'_, AppState>) -> Result<Value, String> {
    with_session(&state, |s| {
        let inspected = s.repository.inspect(&fill_id, s.cursor)?;
        if inspected["chain"]["fill"]["eventId"].as_str() != Some(&fill_id) {
            return Err("select a fill event id".into());
        }
        s.selected = Some(fill_id);
        s.snapshot()
    })
}
#[tauri::command]
fn select_tab(_tab: String, state: tauri::State<'_, AppState>) -> Result<Value, String> {
    with_session(&state, |s| s.snapshot())
}
fn query_session(s: &Session, session_id: &str, cursor_upper: usize) -> Result<usize, String> {
    if session_id != s.id.to_string() {
        return Err("stale replay session".into());
    }
    Ok(cursor_upper.min(s.cursor))
}
#[tauri::command]
fn get_replay_window(
    session_id: String,
    start_ts_us: Option<String>,
    end_ts_us: Option<String>,
    max_points: usize,
    cursor_upper: usize,
    state: tauri::State<'_, AppState>,
) -> Result<Value, String> {
    let start = start_ts_us
        .map(|v| v.parse::<u64>().map_err(|_| "invalid start timestamp"))
        .transpose()?;
    let stop = end_ts_us
        .map(|v| v.parse::<u64>().map_err(|_| "invalid end timestamp"))
        .transpose()?;
    if start.zip(stop).is_some_and(|(a, b)| a > b) {
        return Err("invalid time range".into());
    }
    with_session(&state, |s| {
        let end = query_session(s, &session_id, cursor_upper)?;
        Ok(s.envelope(s.repository.window(start, stop, max_points, end)))
    })
}
#[tauri::command]
fn query_replay_rows(
    session_id: String,
    event_type: Option<String>,
    offset: usize,
    limit: usize,
    cursor_upper: usize,
    state: tauri::State<'_, AppState>,
) -> Result<Value, String> {
    with_session(&state, |s| {
        let end = query_session(s, &session_id, cursor_upper)?;
        Ok(s.envelope(
            s.repository
                .rows(event_type.as_deref(), offset, limit, end)?,
        ))
    })
}
#[tauri::command]
fn inspect_replay_event(
    session_id: String,
    event_id: String,
    cursor_upper: usize,
    state: tauri::State<'_, AppState>,
) -> Result<Value, String> {
    with_session(&state, |s| {
        let end = query_session(s, &session_id, cursor_upper)?;
        Ok(s.envelope(s.repository.inspect(&event_id, end)?))
    })
}

#[tauri::command]
fn start_run(config: RunConfig, state: tauri::State<'_, AppState>) -> Result<Value, String> {
    let id = invalidate(&state)?;
    let run_id = format!("qrs_{}", timestamp_ms());
    let runner = state
        .repo_root
        .join("systems/quant_replay_engine/target/debug/quant_replay_cli");
    if !runner.exists() {
        return Err(format!("Runner binary not found: {}", runner.display()));
    }
    let run_root = state.run_root.to_string_lossy().to_string();
    let latency = config.latency_us.to_string();
    let fee_bps = config.fee_bps.to_string();
    let cash = config.starting_cash.to_string();
    let mut command = Command::new(runner);
    command.current_dir(&state.repo_root).args([
        "run",
        "native",
        "--repo-root",
        ".",
        "--canonical-date",
        &config.date,
        "--run-root",
        &run_root,
        "--run-id",
        &run_id,
        "--max-events",
        "25000",
        "--latency-us",
        &latency,
        "--fill-model",
        &config.fill_model,
        "--profile",
        &config.profile,
        "--threshold",
        "0.35",
        "--max-orders",
        "12",
        "--starting-cash",
        &cash,
        "--fee-bps",
        &fee_bps,
    ]);
    if config.fill_model == "l2-depth" {
        command.arg("--include-l2");
    }
    let status = command
        .status()
        .map_err(|error| format!("unable to start Runner: {error}"))?;
    if !status.success() {
        return Err(format!("Runner exited with status {status}"));
    }
    let repository = Repository::open(&state.run_root.join(&run_id))?;
    install(&state, repository, id)
}

fn safe_run_directory(run_root: &Path, run_id: &str) -> Result<PathBuf, String> {
    if run_id.is_empty()
        || run_id == "—"
        || run_id.contains('/')
        || run_id.contains('\\')
        || run_id.contains("..")
    {
        return Err("invalid run id".to_string());
    }
    Ok(run_root.join(run_id))
}

fn run_entry(entry: RunEntry) -> RunEntryDto {
    RunEntryDto {
        run_id: entry.run_id,
        dataset_date: entry.dataset_date,
        symbol: entry.symbol,
        strategy: entry.strategy,
        execution_model: entry.execution_model,
        event_count: entry.event_count,
        order_count: entry.order_count,
        fill_count: entry.fill_count,
        status: entry.status,
        run_directory: entry.run_directory,
    }
}

fn timestamp_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(app_state())
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || loop {
                std::thread::sleep(std::time::Duration::from_millis(50));
                let state = handle.state::<AppState>();
                if let Ok(mut guard) = state.session.lock() {
                    if let Some(s) = guard.as_mut().filter(|s| s.playing) {
                        s.tick();
                        // Emit under the same lock as controls: no old tick can overtake seek/pause.
                        if let Ok(snapshot) = s.snapshot() {
                            let _ = handle.emit("replay_snapshot_v2", snapshot);
                        }
                    }
                };
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_runs,
            open_run,
            replay_command,
            seek,
            select_fill,
            select_tab,
            start_run,
            get_replay_window,
            query_replay_rows,
            inspect_replay_event
        ])
        .run(tauri::generate_context!())
        .expect("error while running Quant Replay Studio");
}

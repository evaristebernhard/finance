# Quant Replay Studio — Slint reference frontend

This directory is **not the active product surface**.

The active desktop product is the React + Tauri application in
[`frontend-tauri/`](../frontend-tauri/README.md). This Slint implementation is
kept as a reference because its Rust replay repository and replay-v2 modules are
still shared by the Tauri bridge.

Do not add new user-facing product features here unless the work is explicitly
about migration, regression testing or the shared Rust replay layer.

## What remains useful here

- `src/replay_repository.rs`: artifact loading and run-library data access.
- `src/replay_v2.rs`: replay session, cursor/index and causal inspection logic.
- `replay-check/`: replay verification work.
- `ui/main.slint`: historical/reference UI.

The product flow and terminology are defined by `frontend-tauri/`:

```text
Experiments -> New Experiment -> Replay Debugger
```

The Runner remains the source of truth for fills and PnL.

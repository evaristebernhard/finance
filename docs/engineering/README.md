# Engineering Docs

Status: 2026-10-03.

The active product is **Quant Replay Studio: Deterministic Strategy Replay &
Historical Analysis**.

## Active product surface

- React + Tauri desktop app: [frontend-tauri](../../frontend-tauri/README.md)
- Tauri/Rust bridge: [frontend-tauri/src-tauri/src/lib.rs](../../frontend-tauri/src-tauri/src/lib.rs)
- Shared replay repository: [frontend/src/replay_repository.rs](../../frontend/src/replay_repository.rs)
- Replay v2 state/index/query layer: [frontend/src/replay_v2.rs](../../frontend/src/replay_v2.rs)
- Replay engine: [quant replay engine](../../systems/quant_replay_engine/README.md)
- Product direction: [Quant Replay Studio product note](../product/quant-replay-studio.md)
- Data platform boundary: [next-stage data platform](../next-stage-data-platform.md)

The old Slint UI under `frontend/` and old React workbench are references only.
New product work belongs in `frontend-tauri/` unless it is shared replay/data
logic.

## Runner and UI boundary

```text
Dataset preflight
  -> canonical event stream
  -> strategy decision
  -> latency queue
  -> exchange simulator
  -> portfolio/accounting
  -> causal run artifacts
  -> replay index / typed historical queries
  -> React + Tauri Replay Analysis
```

The key invariant is:

> The Runner owns outcomes. The UI replays and explains them.

The UI must not silently recompute fills, account transitions or execution PnL.

## Historical-analysis query layer

Replay v2 may derive read-only presentation/query fields from the Runner
artifact, for example:

- signal / threshold;
- order side and quantity;
- actual fill price;
- latency slippage;
- realized and execution deltas already recorded in events;
- historical price / PnL windows.

This is acceptable because it is reading artifact truth. It must not create new
orders, fills or trading outcomes.

## Storage direction

Local Parquet plus embedded DuckDB remains the storage direction for catalog,
validation and analytics. DuckDB does not belong in the Runner hot path.

L2 remains a gated capability: snapshot availability, timestamps,
price/quantity validity and deterministic reconstruction must pass preflight.

## Backend work that is still needed

The current engine is sufficient for deterministic single-run historical replay.
Do **not** rewrite it.

Priorities:

1. richer typed historical-analysis queries;
2. experiment manifest cleanup;
3. dataset and strategy registries / plugin boundaries;
4. typed execution/PnL attribution;
5. scalable checkpoints and indexes.

Automatic run comparison is deferred.

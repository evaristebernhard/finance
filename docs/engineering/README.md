# Engineering Docs

Status: 2026-10-03.

The active product is the local-first **Quant Replay Studio: Deterministic
Strategy Replay & Debugger**.

## Active product surface

- React + Tauri desktop app: [frontend-tauri](../../frontend-tauri/README.md)
- Tauri/Rust bridge: [frontend-tauri/src-tauri/src/lib.rs](../../frontend-tauri/src-tauri/src/lib.rs)
- Shared replay repository: [frontend/src/replay_repository.rs](../../frontend/src/replay_repository.rs)
- Replay v2 state/index layer: [frontend/src/replay_v2.rs](../../frontend/src/replay_v2.rs)
- Replay engine: [quant replay engine](../../systems/quant_replay_engine/README.md)
- Product boundary and roadmap: [Quant Replay Studio product note](../product/quant-replay-studio.md)
- Data platform boundary: [next-stage data platform](../next-stage-data-platform.md)

The old Slint frontend under `frontend/` is a reference implementation only.
The browser-era workbench under `archive/` is historical. Do not build new
product features in either surface unless explicitly doing migration or
regression work.

## Runner and data path

Run the active desktop app from `frontend-tauri/`:

```bash
npm install
npm run tauri:dev
```

The active execution path is:

```text
Dataset preflight
  -> canonical event stream
  -> strategy decision
  -> latency queue
  -> exchange simulator
  -> portfolio/accounting
  -> causal run artifacts
  -> replay index
  -> React + Tauri Replay Debugger
```

The key invariant is:

> The Runner owns outcomes. The UI explains them.

The UI must not silently recompute fills, latency effects or execution PnL.

## Storage direction

The active storage direction remains local Parquet plus embedded DuckDB for
catalog, validation and analytics. DuckDB does not belong in the Runner hot
path. The Runner consumes an ordered event stream through the
`MarketDataBackend` boundary.

L2 is a gated capability. Depth replay must not be advertised as valid merely
because depth rows exist; snapshot availability, timestamps, price/quantity
validity and deterministic reconstruction must pass preflight.

## Backend work that is still needed

The current engine is already sufficient for single-run deterministic replay.
Do **not** rewrite it.

The next backend work should be targeted at product generalization:

1. experiment manifests that are not hard-coded to one market pack;
2. stable Data / Strategy / Execution / Analysis plugin contracts;
3. a run-comparison service that aligns two causal timelines and reports where
   decisions, arrivals, fills and PnL first diverge;
4. typed PnL/execution attribution instead of presentation-only strings;
5. dataset registry + quality metadata for Parquet/DuckDB datasets;
6. scalable checkpoints/indexes for very large runs.

Live trading, broker account management and cloud execution are not required for
the current product thesis.

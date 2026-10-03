# Quant Replay Engine

This is the market-neutral Rust kernel behind Quant Replay Studio, a
**deterministic strategy replay & debugger**.

The engine owns the canonical event stream, deterministic replay clock, latency
queue, exchange simulation, portfolio accounting, causal event log, replay
index and local CLI. The UI must consume these outcomes rather than recomputing
execution results.

Market-specific strategies and diagnostics stay outside this workspace. The
current CCUSDT pack is under `systems/ccusdt_replay_exchange/`.

## Workspace crates

```text
quant_replay_core       canonical data, backend contract, replay stream
quant_exchange_sim      orders, fills, account and execution models
quant_replay_runner     deterministic runner and strategy bridges
quant_replay_cli        local command line entrypoint
```

Run from the repository root:

```bash
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml \
  -p quant_replay_cli -- run sparse-python \
  --canonical-date 2026-05-18 --max-events 500 --latency-us 50000
```

## Product invariant

A completed run should contain enough evidence to reconstruct and inspect:

```text
market observation
  -> strategy signal
  -> order intent
  -> latency / arrival
  -> fill
  -> position/account transition
  -> PnL attribution
```

The current artifact contract includes `manifest.json`, `summary.json`,
`events.ndjson` and `replay_index.json`.

## Data boundary

The engine accepts the current canonical-files adapter and exposes the
`MarketDataBackend` boundary for planned Parquet and embedded DuckDB adapters.
DuckDB belongs in dataset discovery, validation and analytics; the Runner
consumes a sequential event stream in its hot path.

## Next backend milestones

The engine does not need a rewrite for the new product positioning. The next
changes should generalize what already works:

- market-neutral experiment manifests and dataset selection;
- formal plugin contracts for data, strategy, execution and analysis;
- typed execution/PnL attribution fields;
- experiment A/B alignment and causal divergence reporting;
- scalable checkpoints for large replay artifacts.

Those capabilities turn the existing single-run debugger into a reusable
strategy-debugging platform without turning the core into a charting terminal,
broker or cloud service.

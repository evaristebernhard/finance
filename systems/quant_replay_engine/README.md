# Quant Replay Engine

This is the market-neutral Rust kernel behind Quant Replay Studio.

Its job is to produce deterministic, inspectable historical strategy runs. It
owns the canonical event stream, replay clock, latency queue, exchange
simulation, portfolio accounting, causal event log, replay index and local CLI.

The UI consumes these outcomes; it does not recompute execution results.

Market-specific strategies and diagnostics stay outside this workspace. The
current CCUSDT pack is under `systems/ccusdt_replay_exchange/`.

## Workspace crates

```text
quant_replay_core       canonical data, backend contract, replay stream
quant_exchange_sim      orders, fills, account and execution models
quant_replay_runner     deterministic runner and strategy bridges
quant_replay_cli        local command line entrypoint
```

## Product invariant

A completed run should contain enough evidence to reconstruct:

```text
market observation
  -> strategy signal
  -> order intent
  -> latency / arrival
  -> fill
  -> position/account transition
  -> PnL evolution
```

The current artifact contract includes `manifest.json`, `summary.json`,
`events.ndjson` and `replay_index.json`.

## Replay-analysis boundary

Read-only replay queries may expose typed historical fields such as signal,
threshold, side, fill price, latency slippage and recorded PnL deltas. They must
remain cursor-bounded and must never fabricate a future event or new execution
outcome.

## Data boundary

The engine accepts the current canonical-files adapter and exposes the
`MarketDataBackend` boundary for planned Parquet and embedded DuckDB adapters.
DuckDB belongs in dataset discovery, validation and analytics; the Runner
consumes a sequential event stream in its hot path.

## Next backend milestones

No rewrite is needed. Continue by generalizing what already works:

- richer historical-analysis queries;
- market-neutral experiment manifests and dataset selection;
- formal data / strategy / execution / analysis boundaries;
- typed execution/PnL attribution;
- scalable checkpoints for large replay artifacts.

Automatic experiment comparison is deferred until the single-run historical
analysis workflow is mature.

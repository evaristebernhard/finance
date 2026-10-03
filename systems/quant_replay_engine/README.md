# Quant Replay Engine

This is the market-neutral Rust kernel for Quant Replay Studio. It owns the
canonical event stream, deterministic replay clock, latency queue, exchange
simulation, portfolio accounting, event log, and local CLI.

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

The engine accepts the current canonical files adapter and exposes the
`MarketDataBackend` boundary for the planned Parquet and embedded DuckDB
adapters. DuckDB belongs in dataset discovery, validation, and analytics; the
Runner consumes a sequential event stream in its hot path.

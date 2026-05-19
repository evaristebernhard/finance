# CCUSDT Replay Exchange

Status: catalog + canonical + taker-first stream runner MVP, 2026-05-19.

This is a standalone local replay + paper exchange system. It is intentionally
separate from root-level research scripts, the older replay workbench backend,
and the legacy `date/` research-output directory.

System boundary:

```text
old raw/research files -> catalog -> canonical events -> replay exchange -> runs
```

## Layout

```text
docs/       architecture, contracts, execution model, runbook
configs/    local roots and runtime configs
schemas/    event/order/fill/portfolio contracts
engine/     Rust workspace
strategies/ external strategy clients
monitor/    future UI
runs/       local run outputs
tests/      fixtures and integration assets
```

## Next Stage Design

The next stage is defined in
`docs/next-stage-three-process-design.md`.

First-principles target:

```text
Runner Server = local exchange: truth, clock, streams, order ingress, fills
Strategy Bot  = independent client: online feature state and sparse intents
Monitor       = read-only screen: state/events/summary, never hot path
```

The current stdin/stdout Python runner remains useful for deterministic smoke
tests. The next implementation step is to split that model into independent
processes, compact the event log, stream canonical quote/trade/L2 through a
bounded-memory merge iterator, and move online features into the bot.

## Catalog And Canonical

Scan local source coverage:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
```

Build 2026-05-18 canonical market truth:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset trade_event_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset l2_level_update_v1 --from 2026-05-18 --to 2026-05-18
```

Validate:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical validate --from 2026-05-18 --to 2026-05-18
```

Generated outputs live under repo-level `data/catalog` and `data/canonical`.
Those directories are local generated data and remain git-ignored.

## Runner

Run the exchange-style Python stream runner from canonical quote/trade frames:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run python --canonical-date 2026-05-18 --max-frames 250 --latency-us 50000
```

This path is the realistic bot harness. Rust owns virtual time, latency,
portfolio, risk, fills, and the event log. Python receives stdin NDJSON
`session_start`, `market_quote`, `market_trade`, optional `market_l2_update`,
`account_snapshot`, `order_ack`, `order_reject`, and `fill` messages. Python may
only return `heartbeat`, `hold`, `submit_order`, or `cancel_order`.

The default fill model is `top_of_book_taker_ioc_v1`: market buy fills at the
arrival ask, market sell fills at the arrival bid, with `fee_bps=0` unless
configured otherwise. Timestamp latency is measured in microseconds:

```text
arrival frame = first quote with local_ts_us >= observed_local_ts_us + latency_us
```

Each order/fill event records observed quote, arrival quote, fill price, arrival
spread, latency, and latency slippage. Optional L2 smoke can be enabled without
changing the default top-of-book fill model:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run python --canonical-date 2026-05-18 --max-frames 20 --include-l2 --l2-max-rows 1000 --l2-batch-size 200 --l2-depth-smoke-qty 10
```

For pressure testing only, `--clock-mode accelerated-async` maps Python wall
response time into additional virtual staleness:

```text
effective_latency_us = latency_us + bridge_wall_latency_us * wall_latency_speedup
```

Run a deterministic toy strategy from canonical quote frames:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run toy --canonical-date 2026-05-18 --max-frames 200 --latency-frames 1 --qty 10 --hold-frames 20
```

The runner owns the replay clock. Strategy decisions create order intents, the
runner schedules them through a fixed frame latency, and the exchange only sees
orders when they arrive. Each run writes:

```text
systems/ccusdt_replay_exchange/runs/<run_id>/manifest.json
systems/ccusdt_replay_exchange/runs/<run_id>/events.ndjson
systems/ccusdt_replay_exchange/runs/<run_id>/summary.json
```

## Serve

Serve from canonical quote frames:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- serve --canonical-date 2026-05-18 --addr 127.0.0.1:8797
```

Serve from a small fixture:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- serve --csv systems/ccusdt_replay_exchange/tests/fixtures/frames.csv
```

API:

```text
GET  /health
GET  /api/state
POST /api/step?frames=1
POST /api/reset
GET  /api/orders
POST /api/orders
POST /api/orders/{id}/cancel
GET  /api/fills
```

## Boundary Rules

- Do not import root `scripts/` from this system.
- Do not make `date/` a runtime input.
- Use raw venue files as material for canonical market truth.
- Treat TFI/factor outputs as sidecars or labels, never as exchange truth.

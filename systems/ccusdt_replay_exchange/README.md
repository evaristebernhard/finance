# CCUSDT Replay Exchange

Status: catalog + canonical + sparse taker-first stream runner MVP, 2026-05-19.

This is the CCUSDT market pack for the standalone local replay + paper exchange
system. The generic Rust kernel now lives in
`systems/quant_replay_engine/`; this directory owns CCUSDT strategies,
diagnostics, monitor wiring, fixtures, and market-specific run history. It is intentionally
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
../quant_replay_engine/ generic Rust workspace
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

The current TCP runner server is the hard experimental kernel: Rust runs as a
local exchange process with public/private/order NDJSON sockets, while Python
runs as an independent bot process. The older stdin/stdout sparse runner remains
as a deterministic regression harness.

## Catalog And Canonical

Scan local source coverage:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
```

Build 2026-05-18 canonical market truth:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical build --dataset trade_event_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical build --dataset l2_level_update_v1 --from 2026-05-18 --to 2026-05-18
```

Validate:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical validate --from 2026-05-18 --to 2026-05-18
```

Generated outputs live under repo-level `data/catalog` and `data/canonical`.
Those directories are local generated data and remain git-ignored.

## Runner

Run the sparse exchange-style Python bot from canonical quote/trade streams:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500 --latency-us 50000
```

Python receives stdin NDJSON `session_start`, `market_quote`, `market_trade`,
optional `market_l2_update`, `account_snapshot`, `order_ack`, `order_reject`,
and `fill` messages. In sparse mode Python returns only `heartbeat`,
`submit_order`, or `cancel_order` when needed; it does not emit per-event holds.

The default fill model is `top_of_book_taker_ioc_v1`: market buy fills at the
arrival ask, market sell fills at the arrival bid, with `fee_bps=0` unless
configured otherwise. Timestamp latency is measured in microseconds:

```text
target_arrival_local_ts_us = observed_local_ts_us + latency_us
default arrival = exact virtual timer at target_arrival_local_ts_us
fill quote/book = last known quote/book before arrival
```

Use `--arrival-mode timer` for the default research baseline. Use
`--arrival-mode next-event` only as a conservative stress mode; it waits until
the first later market event and therefore adds event-gap overshoot to latency.

Each order/fill event records observed quote, arrival quote, fill price, arrival
spread, latency, wall-latency diagnostics, and latency slippage. Optional L2
depth fill can be enabled as the execution model:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 550 --include-l2 --l2-max-rows 1000 --l2-batch-size 200 --fill-model l2-depth
```

For pressure testing only, `--clock-mode accelerated-async` maps Python wall
response time into additional virtual staleness:

```text
effective_latency_us = latency_us + bridge_wall_latency_us * wall_latency_speedup
```

`run python` is retained as the older dense compatibility runner. New work
should prefer `run sparse-python`.

Run the independent Runner Server:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run server --canonical-date 2026-05-18 --max-events 900 --latency-us 50000 --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --order-addr 127.0.0.1:8803 --state-addr 127.0.0.1:8804 --startup-wait-ms 1500 --event-sleep-us 2000
```

Run the independent Python bot in a second terminal:

```powershell
python systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/tcp_bot.py --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --order-addr 127.0.0.1:8803
```

Run the read-only monitor in a third terminal:

```powershell
npm --prefix systems/ccusdt_replay_exchange/monitor run monitor -- --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --state-url http://127.0.0.1:8804/api/state
```

The monitor does not accept or know the order ingress port. It only reads
public/private streams and prints current clock, quote/account state, fills,
latency/slippage summaries, order causal chains, and the optional read-only
state endpoint. Add `--run-dir <run_dir>` to include the compact
`events.ndjson` and `summary.json` audit after `session_end`.

For a completed run:

```powershell
npm --prefix systems/ccusdt_replay_exchange/monitor run monitor -- --offline-run-dir systems/ccusdt_replay_exchange/runs/<run_id>
```

## Diagnostics

Run the hardening suite after changing runner/bot/log behavior:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/hardening_suite.py --repo-root . --date 2026-05-18
```

Run the individual checks:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py --run-dir systems/ccusdt_replay_exchange/runs/<run_id>
python systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py --repo-root . --date 2026-05-18
```

Latest hardening report:

```text
systems/ccusdt_replay_exchange/docs/hardening-report-20260520.md
```

Current strict-audit default for top-of-book taker research is
`panel_sparse_fast_clock_v1`: validated `decision_frame_v1` Parquet cache drives
the decision clock, while the runner uses the `quote_frame_v1` last-known quote
index for deterministic timer arrival/fill. It is much faster than full L2
streaming and remains equivalent to the full-stream/barrier gates for
`top_of_book_taker_ioc_v1`. Latest 2026-05-16..2026-05-18 four-profile matrix:

```text
systems/ccusdt_replay_exchange/runs/profile_matrix_top_of_book_20260516_18_20260521
```

Use the full-stream/barrier gates for L2-depth, maker/queue, or online feature
reconstruction validation.

The server writes the same compact `events.ndjson` causal chain. `event_sleep_us`
is a deliberate replay-throttle knob for local socket experiments; accelerated
async pressure mode remains explicit through `--clock-mode accelerated-async`.

Run a deterministic toy strategy from canonical quote frames:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run toy --canonical-date 2026-05-18 --max-frames 200 --latency-frames 1 --qty 10 --hold-frames 20
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
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- serve --canonical-date 2026-05-18 --addr 127.0.0.1:8797
```

Serve from a small fixture:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- serve --csv systems/ccusdt_replay_exchange/tests/fixtures/frames.csv
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

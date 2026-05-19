# CCUSDT Replay Exchange

Status: catalog + canonical + runner MVP, 2026-05-19.

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

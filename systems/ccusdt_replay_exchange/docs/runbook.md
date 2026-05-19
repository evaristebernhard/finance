# Runbook

Scan catalog:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
```

Build 2026-05-18 canonical datasets:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset trade_event_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset l2_level_update_v1 --from 2026-05-18 --to 2026-05-18
```

Validate canonical:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical validate --from 2026-05-18 --to 2026-05-18
```

Serve from canonical quotes:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- serve --canonical-date 2026-05-18 --addr 127.0.0.1:8797
```

Run the deterministic toy runner:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run toy --canonical-date 2026-05-18 --max-frames 200 --latency-frames 1 --qty 10 --hold-frames 20
```

Run outputs:

```text
systems/ccusdt_replay_exchange/runs/<run_id>/manifest.json
systems/ccusdt_replay_exchange/runs/<run_id>/events.ndjson
systems/ccusdt_replay_exchange/runs/<run_id>/summary.json
```

The runner is the rigorous replay path: it owns the clock, schedules order
intents through the latency queue, submits arrived orders to the exchange, and
writes append-only events.

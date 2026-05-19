# Runbook

Read the next-stage design before changing runner/bot/monitor architecture:

```text
systems/ccusdt_replay_exchange/docs/next-stage-three-process-design.md
```

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

Run the exchange-style Python stream runner:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run python --canonical-date 2026-05-18 --max-frames 250 --latency-us 50000
```

Run a short L2 batch and depth-sweep smoke:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run python --canonical-date 2026-05-18 --max-frames 20 --include-l2 --l2-max-rows 1000 --l2-batch-size 200 --l2-depth-smoke-qty 10
```

Run accelerated async pressure mode:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run python --canonical-date 2026-05-18 --max-frames 250 --latency-us 50000 --clock-mode accelerated-async --wall-latency-speedup 25
```

Run outputs:

```text
systems/ccusdt_replay_exchange/runs/<run_id>/manifest.json
systems/ccusdt_replay_exchange/runs/<run_id>/events.ndjson
systems/ccusdt_replay_exchange/runs/<run_id>/summary.json
```

The Python runner is the rigorous replay path: it owns the clock, streams only
exchange-style public/private events to Python, schedules returned taker intents
through the timestamp latency queue, submits arrived orders to the exchange, and
writes append-only events.

Validation commands used for this layer:

```powershell
cargo fmt --all --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml
cargo test --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml --offline
python -m py_compile systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/strategy.py
```

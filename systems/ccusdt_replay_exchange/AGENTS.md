# AGENTS.md

This directory is an independent CCUSDT replay + paper exchange product.

Hard boundaries:

- Do not import or call root-level `scripts/ccusdt_*` from engine code.
- Do not make `date/` files a runtime dependency.
- Treat old research outputs as spec/reference or feature sidecars only.
- Keep generated paper-trading logs under `runs/`.
- Keep canonical market truth under repo-level `data/canonical`, not mixed into
  source directories.
- All strategy/exchange interactions must flow through event contracts.

Current implementation:

- `engine/` is the Rust workspace.
- `engine/crates/replay_core` owns catalog, canonical data, and replay loading.
- `engine/crates/exchange_sim` owns order/fill/account simulation.
- `engine/crates/runner` owns deterministic replay loops, stdin/stdout Python
  strategy streams, sparse intent handling, timestamp latency queues, optional
  L2 depth fills, accelerated async pressure diagnostics, and run event logs.
- `engine/crates/cli` owns REST serving and data CLI commands.
- `strategies/python/ccusdt_tfi_core_idle01/online_features.py` is the
  runtime-safe feature module shared by stdin and TCP bots. It reads only
  exchange-visible events and owns TFI, rolling trade imbalance, quote
  spread/mid-change/frames state, optional L2 counters, and closed-fill-only R5
  shape state.
- `strategies/python/ccusdt_tfi_core_idle01/strategy.py` is the stdin/stdout
  sparse bot entrypoint. It must not read `date/` labels or import root scripts.

Current next-stage design:

- Start with `docs/next-stage-three-process-design.md` before implementing the
  next runner/bot/monitor split.
- Target architecture is three independent roles: Runner Server owns truth and
  time, Strategy Bot owns online feature state and sparse intents, Monitor is
  read-only.
- `run sparse-python` is the current hard kernel for this design. It streams
  quote/trade/L2 through a bounded-memory merge iterator and logs compact
  order/fill/portfolio chains.
- `run server` is the first independent Runner Server slice. It exposes local
  TCP NDJSON public/private/order channels plus an optional read-only HTTP state
  endpoint. The matching independent Python bot is
  `strategies/python/ccusdt_tfi_core_idle01/tcp_bot.py`.
- `monitor/src/console_monitor.mjs` is read-only. It connects only to
  public/private streams and must not submit orders or know the order ingress
  port.
- Compact event logs should record causal order/fill/risk/portfolio chains, not
  every per-event hold/heartbeat/echo.
- Full-day L2 must use streaming merge iterators, not full-day `Vec` loading.
- Online feature state belongs in the bot; Runner should not compute factors or
  expose research labels as runtime inputs. Runner may persist bot-provided
  `ccusdt_online_feature_snapshot_v1` checkpoints for diagnostics.
- Kernel hardening diagnostics live in `diagnostics/`. Latest acceptance report:
  `docs/hardening-report-20260520.md`.
- Latest strategy feature-state parity note:
  `docs/strategy-feature-state-parity-20260520.md`.

Useful commands:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500 --latency-us 50000
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 550 --include-l2 --l2-max-rows 1000 --l2-batch-size 200 --fill-model l2-depth
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run server --canonical-date 2026-05-18 --max-events 900 --latency-us 50000 --state-addr 127.0.0.1:8804 --startup-wait-ms 1500 --event-sleep-us 2000
python systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/tcp_bot.py
npm --prefix systems/ccusdt_replay_exchange/monitor run monitor -- --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --state-url http://127.0.0.1:8804/api/state
python systems/ccusdt_replay_exchange/diagnostics/hardening_suite.py --repo-root . --date 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run toy --canonical-date 2026-05-18 --max-frames 200 --latency-frames 1
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- serve --canonical-date 2026-05-18
```

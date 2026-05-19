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
  strategy streams, latency queues, L2 depth smoke diagnostics, and run event
  logs.
- `engine/crates/cli` owns REST serving and data CLI commands.
- `strategies/python/ccusdt_tfi_core_idle01/strategy.py` is an online TFI
  skeleton. It reads only exchange-style stdin NDJSON and must not read
  `date/` labels or import root scripts.

Current next-stage design:

- Start with `docs/next-stage-three-process-design.md` before implementing the
  next runner/bot/monitor split.
- Target architecture is three independent roles: Runner Server owns truth and
  time, Strategy Bot owns online feature state and sparse intents, Monitor is
  read-only.
- Compact event logs should record causal order/fill/risk/portfolio chains, not
  every per-event hold/heartbeat/echo.
- Full-day L2 must use streaming merge iterators, not full-day `Vec` loading.
- Online feature state belongs in the bot; Runner should not expose research
  labels as runtime inputs.

Useful commands:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run python --canonical-date 2026-05-18 --max-frames 250 --latency-us 50000
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run python --canonical-date 2026-05-18 --max-frames 20 --include-l2 --l2-max-rows 1000 --l2-depth-smoke-qty 10
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run toy --canonical-date 2026-05-18 --max-frames 200 --latency-frames 1
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- serve --canonical-date 2026-05-18
```

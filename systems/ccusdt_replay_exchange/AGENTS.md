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
- `engine/crates/runner` owns deterministic replay loops and run event logs.
- `engine/crates/cli` owns REST serving and data CLI commands.

Useful commands:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run toy --canonical-date 2026-05-18 --max-frames 200 --latency-frames 1
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- serve --canonical-date 2026-05-18
```

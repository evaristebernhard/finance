= 附录：代码入口索引与命令索引

== 核心代码入口

```text
系统入口
  systems/ccusdt_replay_exchange/README.md

Rust CLI
  systems/ccusdt_replay_exchange/engine/crates/cli/src/main.rs

Rust Runner
  systems/ccusdt_replay_exchange/engine/crates/runner/src/lib.rs

Python Bot
  systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/strategy.py
  systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/tcp_bot.py

在线特征与策略
  online_features.py
  decision_frame.py
  shadow_policy.py
  execution_runtime.py

Fast / cache / state
  diagnostics/decision_frame_cache.py
  diagnostics/shadow_state.py
  diagnostics/fast_strategy_backtest.py

Audit
  diagnostics/audit_event_log.py
  diagnostics/fast_vs_strict_consistency.py
```

== 最小命令索引

构建 decision frame cache：

```powershell
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py build --repo-root . --symbol CCUSDT --from-date 2026-05-18 --to-date 2026-05-18 --input-layer raw
```

校验 cache：

```powershell
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py validate --repo-root . --symbol CCUSDT --from-date 2026-05-18 --to-date 2026-05-18
```

生成 Bot-owned state：

```powershell
python systems/ccusdt_replay_exchange/diagnostics/shadow_state.py --repo-root . --from-date 2026-05-18 --to-date 2026-05-18 --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-17.json
```

跑 fast strategy backtest：

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_strategy_backtest.py --repo-root . --from-date 2026-05-19 --to-date 2026-05-30 --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-18.json --gamma-preset core_q70 --capacity-profile core_idle01 --idle01-gamma 1 --exit-profile fixed60_taker
```

运行 sparse Runner/Bot：

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- run sparse-python --repo-root . --symbol CCUSDT --canonical-date 2026-05-18 --public-stream-mode panel-sparse-fast-clock-v1 --clock-mode deterministic-step --latency-us 0
```

审计 run log：

```powershell
python systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py --run-dir systems/ccusdt_replay_exchange/runs/<run_id>
```

比较 fast 与 strict：

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/<fast_run_id> --strict-audit-dir systems/ccusdt_replay_exchange/runs/<strict_run_id> --date 2026-05-18 --out-dir systems/ccusdt_replay_exchange/runs/<comparison_id>
```

== 读 run output 的顺序

```text
config.json
profile_manifest.json
summary.json
daily.csv
entries.parquet / exits.parquet
events.ndjson
audit output
```


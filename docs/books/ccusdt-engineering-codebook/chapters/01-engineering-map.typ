= 第 1 章：工程地图

== 本章要解决的代码困惑

读代码前必须知道每个目录的角色。否则你会在 Rust Runner、Python Bot、cache builder、run outputs 之间来回跳，越看越乱。

== 先看哪些文件

```text
systems/ccusdt_replay_exchange/README.md
systems/ccusdt_replay_exchange/AGENTS.md
systems/ccusdt_replay_exchange/docs/architecture.md
systems/ccusdt_replay_exchange/docs/runbook.md
```

== 文件树

```text
systems/ccusdt_replay_exchange/
  configs/       路径和本地配置
  docs/          架构、协议、runbook、hardening 报告
  engine/        Rust workspace：CLI、Runner、exchange sim、portfolio
  strategies/    Python Bot 和在线特征/策略逻辑
  diagnostics/   cache、fast backtest、audit、consistency check
  monitor/       只读监控入口，目前不是主线
  runs/          本地实验输出，通常不进 git
```

== 这个模块在系统中负责什么

这套系统故意把旧研究脚本隔离出去。`systems/ccusdt_replay_exchange` 不应该 import 根目录 `scripts/ccusdt_*`。旧研究报告可以提供 spec/reference，但新的实验内核必须从 canonical/cache 和 public/private event stream 里还原因子。

== 输入是什么

工程入口通常从 repo root 运行，并通过 `--repo-root .` 找数据。核心数据路径不在系统目录内部，而在 repo 级别：

```text
data/ccusdt/v1/external/                 raw venue files
data/canonical/cex/bullish/CCUSDT/       canonical CSV.GZ
data/canonical_parquet/cex/bullish/...   decision_frame cache
systems/ccusdt_replay_exchange/runs/     run outputs and state
```

== 输出是什么

所有运行结果应该写到 `runs/`。如果一个脚本把中间结果写回旧 `date/`，你要警惕：那可能是研究脚本口径，而不是 replay exchange 系统口径。

== 它绝不能做什么

系统目录不能变成旧研究脚本的大杂烩。尤其不要把 fixed panel、scored entries、MFE/MAE、PnL label 直接塞进 Bot 或 Runner。

== 一个最小读代码路径

先读 README 的 “Runner”、“Diagnostics”、“Boundary Rules”。然后打开 `diagnostics/README.md`，看每个诊断脚本负责哪条验证链。最后再进入代码。

== 常见误解

`diagnostics` 不等于“不重要”。这里的 `fast_strategy_backtest.py` 是策略研究最快路径；`decision_frame_cache.py` 是热路径工程优化；`audit_event_log.py` 是严格回放的安全带。


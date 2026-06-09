= 第 2 章：数据从哪里来

== 本章要解决的代码困惑

代码里同时出现 raw、canonical、Parquet cache、decision frame、state、run artifacts。它们不是同一种东西。读懂数据层，才能知道一个脚本到底是在“准备市场真相”、“构建特征缓存”，还是“跑策略”。

== 先看哪些文件

```text
systems/ccusdt_replay_exchange/configs/data_roots.yaml
systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py
systems/ccusdt_replay_exchange/diagnostics/shadow_state.py
systems/ccusdt_replay_exchange/docs/hot-path-parquet-state-20260520.md
```

== 数据层流程图

```text
raw venue files
  -> canonical quote/trade/L2 CSV.GZ
  -> decision_frame_v1 Parquet cache
  -> Bot-owned shadow state
  -> fast backtest or strict replay
  -> run artifacts
```

== 这个模块在系统中负责什么

raw 是交易所原材料。canonical 是系统承认的市场真相。decision_frame cache 是为了让策略研究快起来的 typed Parquet 工作层。Bot-owned state 是策略自己连续维护的历史状态，尤其是 R5 和 pending lifecycle。

== 输入是什么

`decision_frame_cache.py` 可以从 raw 或 canonical 构建 cache。`shadow_state.py` 从 cache 读取 decision frames，然后输出某个日期后的状态文件。

== 输出是什么

典型输出：

```text
data/canonical_parquet/cex/bullish/CCUSDT/decision_frame_v1/dt=YYYY-MM-DD/
systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=YYYY-MM-DD.json
```

== 它绝不能做什么

decision_frame cache 不能包含未来收益、MFE、MAE、PnL、path class。Bot state 不能跳日期，也不能独立重复用于多个非连续日期。

== 一个最小读代码路径

在 `decision_frame_cache.py` 中先看：

```text
parse_args
iter_raw_decision_frames
build_one
iter_cached_decision_frames
validate_one
```

在 `shadow_state.py` 中先看：

```text
load_and_guard_state
policy.on_decision_frame
policy.export_state
```

== 常见误解

Parquet cache 不是旧 fixed panel 的复制品。它必须是 market-derived；manifest 里的 builder version、source hash、row count 是为了防止口径漂移。


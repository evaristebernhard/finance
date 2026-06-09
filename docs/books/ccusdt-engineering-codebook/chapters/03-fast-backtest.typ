= 第 3 章：先看 fast backtest

== 本章要解决的代码困惑

如果你想最快理解策略怎么跑，先看 `fast_strategy_backtest.py`。它没有 socket，没有 stdin/stdout，也没有真实 Runner 时钟；它直接读取 decision_frame cache 和 Bot-owned state，快速生成 entries、exits、daily 和 summary。

== 先看哪些文件

```text
systems/ccusdt_replay_exchange/diagnostics/fast_strategy_backtest.py
systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/shadow_policy.py
systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/execution_runtime.py
```

== fast backtest 流程图

```text
decision_frame cache
  -> load Bot-owned state
  -> ShadowFourCellPolicy
  -> admission gate
  -> capacity allocator
  -> exit profile
  -> entries/exits/daily/summary
```

== 这个模块在系统中负责什么

fast backtest 回答策略研究问题：entry 有多少、cell 如何分布、capacity 如何 clipping、fixed/taker exit 后收益如何、日度尾部如何。它不是实盘模拟器，但它必须和 strict replay 在核心决策上对齐。

== 输入是什么

核心输入包括：

```text
--from-date / --to-date
--shadow-state-in
--capacity-profile
--idle01-gamma
--exit-profile
--admission-profile
--admission-thresholds-json
```

读代码时注意 `load_and_guard_state`。它要求 state 的 `next_expected_date` 等于 backtest 的 `from-date`，这是防止 R5 断档的边界。

== 输出是什么

输出目录在：

```text
systems/ccusdt_replay_exchange/runs/experiments/<run_id>/
```

主要文件：

```text
config.json
data_manifest.json
policy_manifest.json
profile_manifest.json
summary.json
daily.csv
entries.parquet
exits.parquet
```

== 它绝不能做什么

fast backtest 不能读取 `date/` 的 scored entries 作为策略输入。它可以读取 run state、decision_frame cache、quote_frame index 和 prior-date thresholds，但不能使用未来标签。

== 一个最小读代码路径

从 `main()` 开始读：

```text
parse_args
load_and_guard_state
ShadowFourCellPolicy(...)
build_capacity_allocator(...)
for day in days:
  iter_cached_decision_frames(...)
  policy.on_decision_frame(...)
  add_entry(...)
  process_closed(...)
write summary/daily/parquet
```

== 常见误解

`gross_weighted_bps == net_weighted_bps` 不代表没扣 spread。对 `fixed60_taker` 来说，spread 已体现在 entry ask / exit bid 或 entry bid / exit ask 的成交价里；显式 fee、pressure、slippage 为 0 时，gross 和 net 才相等。


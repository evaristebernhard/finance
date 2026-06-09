= 第 9 章：fast 与 strict 为什么都需要

== 本章要解决的代码困惑

如果 fast 已经能跑策略，为什么还需要 strict？如果 strict 更真实，为什么还需要 fast？答案是二者回答不同问题。

== 先看哪些文件

```text
diagnostics/fast_strategy_backtest.py
diagnostics/fast_vs_strict_consistency.py
diagnostics/repeat_run_hash_gate.py
```

== 两条线

```text
fast line:
  decision_frame cache -> policy/capacity/exit -> entries/exits/PnL

strict line:
  exchange-style stream -> Bot -> Runner order/fill/portfolio -> event log
```

== 这个模块在系统中负责什么

fast 回答 edge、参数、容量、尾部和日度表现。strict 回答时序、延迟、成交、lot lifecycle、日志可信度和实盘形态。

== 输入是什么

`fast_vs_strict_consistency.py` 输入一个 fast run 和一个 strict run，按日期比较：

```text
timestamp
cell
side
membership
requested_exposure
actual_exposure
capacity_source
fill / lot lifecycle
PnL decomposition
```

== 输出是什么

输出通常是一个 consistency report 目录，里面有 summary 和 mismatch 表。它告诉你差异来自策略决策、capacity、entry spread、exit spread、latency、depth/slippage 还是 pressure。

== 它绝不能做什么

不能把不同 profile 的结果强行比较。比如 fixed60 mid、fixed60 taker、fixed30 taker、stopping_rule_v1、pressure mode 都是不同口径。

== 一个最小读代码路径

```text
fast_vs_strict_consistency.py
-> load fast entries/exits
-> load strict events
-> normalize rows
-> compare decision fields
-> compare fills/lots
-> write decomposition
```

== 常见误解

fast PnL 和 strict PnL 不一致不一定是 bug。若 timestamp/cell/side/capacity 都对齐，差异可能正是 execution decomposition 想告诉你的东西：spread、latency、depth、pressure。


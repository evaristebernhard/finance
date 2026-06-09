= 第 5 章：Bot-owned state 与 R5

== 本章要解决的代码困惑

R5 是最近已关闭 entry 的路径形状记忆。它不能从旧研究面板偷来，也不能用未来 entry。`shadow_state.py` 的作用，就是让 Bot 拥有自己的连续状态。

== 先看哪些文件

```text
systems/ccusdt_replay_exchange/diagnostics/shadow_state.py
systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/shadow_policy.py
systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/online_features.py
```

== 这个模块在系统中负责什么

`shadow_state.py` 读取 decision_frame cache，把四象限 shadow policy 从某个日期跑到另一个日期，然后导出 closed_bps、pending_entries、next_shadow_position_id、last_seen_ts_us 和 next_expected_date。

== 输入是什么

```text
--from-date
--to-date
--shadow-state-in
--fixed-exit-us
--gamma-preset
```

如果传入 `--shadow-state-in`，脚本会检查：

```text
state.next_expected_date == from_date
```

这就是 state boundary guard。

== 输出是什么

默认输出：

```text
systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=YYYY-MM-DD.json
```

对于 fixed30/fixed45 等 horizon 变体，应使用不同文件名，避免把不同 R5 lifecycle 混在一起。

== 它绝不能做什么

它不能跳过中间日期，也不能把同一个 state 独立用于多个非连续日期。R5 是时间连续状态，不是一个可随意加载的静态参数。

== 一个最小读代码路径

```text
load_and_guard_state
ShadowFourCellPolicy(...)
policy.load_state(...)
for frame in iter_cached_decision_frames:
  policy.on_decision_frame(...)
policy.export_state(...)
```

== 常见误解

`--warmup-reference-r5` 是诊断工具，不是运行时方案。真正可接受的方式是从 warmup 日期一路 replay 出 Bot-owned state，或者加载前一天持久化的 state。


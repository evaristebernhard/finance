= 后续章节提纲

本章不是精写章节，而是后续扩展路线。每一节都应按同一模板补全：问题、第一性原理、数学对象、工程映射、当前证据、未解决问题。

== 停时与 ExitController

目标：把 exit 从固定持有期变成 runtime-safe 停时问题。

应包含：

- $W_t(tau)$ 的定义。
- mid continuation 与 crossing improvement 的精确分解。
- residual pressure 与 exhaustion 的区别。
- 为什么 low exhaustion 更像 mid-continuation guard。
- 为什么 oracle exit 只能做上界，不能变成策略。
- 如何把 conditional wait 从 offline diagnostic 接进 strict Runner。

关键证据：

```text
v1-tfi-conditional-wait-exit-opportunity-20260522.md
v1-tfi-exit-controller-v1-conditional-wait-m010-20260522.md
v1-tfi-exit-residual-pressure-diagnostic-20260524.md
v1-tfi-exit-wait-value-decomposition-20260524.md
```

== 杠杆与容量

目标：把 3x cap 从最终缩放改成在线分配问题。

应包含：

- $sum_j w_j(t) <= 3$ 的在线约束。
- global scaled total 为什么过于保守。
- FIFO/arrival clipping 的含义。
- core cells 与 `01_frames_only` idle sleeve。
- capacity displacement 与 skipped/clipped legs。
- 为什么 `gamma01=0` 可能是优化目标误设，而不是结构无效。

关键证据：

```text
v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md
v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md
```

== 执行现实性

目标：区分 mid edge、taker executable edge、maker illusion。

应包含：

- top-of-book taker IOC 的基线意义。
- entry spread cost 与 exit spread cost。
- latency profile：deterministic vs wall pressure。
- L2 depth sweep 的必要性与局限。
- maker-first exit 为什么当前 no-go。
- 为什么 zero venue fee 不是 zero execution cost。

关键证据：

```text
v1-tfi-maker-exit-wait-vs-maker-20260522.md
v1-tfi-maker-first-exit-completion-audit-20260522.md
fast_vs_strict consistency outputs
```

== Monitor 与实验控制室

目标：设计只读 Monitor，而不是交易控制台。

应包含：

- Monitor 只读 `runs/<run_id>` artifacts。
- Run Catalog、Artifact Adapters、Derived State Builder、Read API、UI。
- Run Overview、Daily PnL、Order Causal Chain、Position Lifecycle。
- PnL Attribution、Wait Decomposition、Fast-vs-Strict Compare、Case Drilldown。
- 为什么 Monitor 不应控制 Runner clock/order/fill/portfolio。

== 失败案例与研究纪律

目标：把事故变成方法论。

应包含：

- 1615412：fast release + 60s decay + oversizing。
- 2583437：过早退出与 post-exit watcher。
- 为什么 profitable entry 也可以是 case。
- matched controls、walk-forward、prior-date thresholds。
- 不因 `net_median < 0` 丢弃右尾结构。
- 不把 q60/q65 sensitivity 提前提升为 live candidate。
- 不把 oracle 结果包装成 runtime policy。

== 全书最终结构草案

```text
第 0 章  序章：为什么要写这本书
第 1 章  从第一性原理定义 edge
第 2 章  因子语言与 Python 研究循环
第 3 章  本地 Replay Exchange 与双轨回测
第 4 章  停时与 ExitController
第 5 章  杠杆、容量与风险预算
第 6 章  执行现实性：taker、maker、latency、L2
第 7 章  Monitor 与实验控制室
第 8 章  失败案例与研究纪律
附录 A   符号表与证据地图
```

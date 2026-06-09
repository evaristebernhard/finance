#import "../styles.typ": definition, proposition, evidence, remark

= 第 9 章：四象限不是策略，而是分解语言

== 本章要解决的困惑

四象限经常被误读成“哪个象限赚钱就做哪个”。实际上四象限首先是分解语言：它把路径记忆和停滞状态拆开，使我们知道收益来自哪里、重叠在哪里、容量如何被占用。

== 一个具体例子

定义两个判断：

```text
A: R5 > 1
B: frames_since_mid_change >= q90
```

那么每个 entry 落入四个互斥格子之一：

```text
00: A=0, B=0
10: A=1, B=0
01: A=0, B=1
11: A=1, B=1
```

互斥的意思是：一个 entry 只能属于一个格子。这样我们不会把同一笔收益重复归因给 R5 和 frames。

== 从例子推导数学对象

令：

$ A_i = 1{R_(i,5) > 1} $

$ B_i = 1{F_i >= q_90} $

其中 $F_i$ 是 mid 长时间不变的帧数。cell 是：

$ C_i = (A_i, B_i) $

权重不是 cell 本身，而是策略选择：

$ w_i = b_i gamma_(C_i) psi_i phi_i $

$b_i$ 是 trigger base weight，$gamma$ 是 cell sizing，$psi$ 和 $phi$ 可以表示 admission、capacity、path manager 等调节项。

== 正式定义

#definition("frames_since_mid_change", [
  frames_since_mid_change 记录中间价已经连续多少个 quote frame 没有变化。它是停滞或潜在压力的代理变量，不是独立 alpha。
])

#definition("四象限", [
  四象限是由 R5 条件和 frames 条件生成的互斥状态分解。它用于分析 path memory 与 staleness 的交互，不等于最终策略。
])

== CCUSDT 实证证据

#evidence("idle capacity sleeve", [
  Leverage-constrained optimization 报告显示，`01_frames_only` 作为 idle-capacity sleeve 时，历史 C=0 从 core-only 6038.2000 提升到 `idle01_g1_r0` 6907.5648；2026-05-18 OOS 从 415.8276 提升到 472.5926。这说明 `01` 被早期优化丢掉，部分原因是容量竞争口径错误。
])

== 失败机制

四象限分析会失败，通常不是因为格子定义错，而是把 sizing 结果当成因子真相。

如果某个 cell 的 gamma 很高，它会占用更多 3x 杠杆容量，可能挤掉其他 cell。优化器看到的是组合结果，不是 cell 单位 alpha。`01_frames_only` 曾经被 gamma=0 丢掉，后来作为 idle-capacity sleeve 又有增量，就是这个问题。

#proposition("容量角色改变因子解释", [
  同一个 cell 若作为 core capacity 竞争者和作为 idle-capacity sleeve，其策略贡献不同。因此 gamma 搜索结果不能直接解释为 cell alpha。
])

== 策略/runtime 边界

四象限变量可以运行时安全，只要 R5 和 frames 都在线维护。capacity allocator 也必须在线：每个 entry 到达时查看当前 open exposure，按 3x 上限进行 FIFO/arrival clipping，而不是事后按全局最大并发缩放。

== 本章小结

四象限是把状态讲清楚的语言，不是终点。R5 表示路径记忆，frames 表示停滞状态，gamma 表示 sizing，capacity 决定实际能开多少。把这四层混在一起，就会误删有用结构。


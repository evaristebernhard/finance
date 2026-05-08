#import "../styles.typ": *
#import "../notation.typ": *

= 附录 E. Artifact 字段阅读工作册：怎样不把 JSON 当理论

#chapter_problem[
  这个附录专门训练读者阅读当前 CLI 产出的 JSON artifact。目标不是教你背字段名，而是让你始终问：这个字段在研究对象里到底对应什么，它是事实、projection、proxy 还是 calibration？
]

== E.1 读 `decision-state.json`

看到下面这组字段时：

```text
family
pool_address
theta_pool
theta_route
Gamma
q
r
u
kappa
gas_limit
bid
max_fee
```

要分四组理解：

- 几何/路径上下文：`family/pool_address/theta_*`
- 决策相关投影：#gamma/#qt/#rt/#ut/#kappat
- 动作参数：`gas_limit/bid/max_fee`
- 证据边界：`evidence/role/strength/assumptions`

== E.2 读 `decision.json`

这里最关键的不是“策略选了什么”，而是：

```text
它是基于什么状态边界、什么投影边界做出的选择？
```

如果看不到 evidence/role/strength，就说明 artifact 不够安全，容易被误读成裸真值。

== E.3 读 `execution.json`

`ExecutionRecord` 不是链上回执。  
它是研究闭环里的执行记录对象，作用是：

- 固化某次 decision。
- 记录 seed 与 paper execution 结果。
- 给 replay 和 eval 提供输入。

== E.4 读 `replay.json`

`replay` 不是再次广播交易，而是在给定 event/seed 条件下重新计算同一次研究动作的结果。  
它是把“事前 decision”和“事后 outcome”重新接回一条链。

== E.5 读 `eval` 输出

`pnl.realized` 与 `risk.score` 的意义是：

- 比较策略。
- 检查 replay 后果。
- 服务校准和研究判断。

它们不是“真实钱包盈亏截图”的替代物。

#chapter_summary[
  这个工作册的核心目标是：以后你看到任何 artifact，都先问“这在研究对象里是什么”，而不是先问“这个数字大不大”。只要这个习惯建立了，CLI 输出就不会再反向定义研究对象。
]

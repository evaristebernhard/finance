#import "../styles.typ": *
#import "../notation.typ": *

= 12. Bellman 决策、paper execution、replay、PnL/risk 与当前仓库闭环

#chapter_problem[
  本章把前面的状态、投影和参数链条收束成一个完整闭环：为什么要用 Bellman 比较 `act/wait/abort`，以及当前仓库如何用 paper execution、replay、PnL 和 risk 跑出研究闭环。
]

== 12.1 从最简单的 act 分数开始

考虑一步 act 分数：

$J^("act") = q times (u times r times Gamma - c_("gas") - (1 - u times r) times L) - kappa$

这是把：

- 毛机会
- 入链概率
- output 成立概率
- survival
- gas 成本
- 失败损失
- 冲突摩擦

放进同一个比较框架。

== 12.2 完整数值案例

按教材要求，取：

```text
Gamma = 10
q = 0.7
u = 0.8
r = 0.9
kappa = 1.2
gas_cost = 2
L = 3
```

先算：

$u times r = 0.8 times 0.9 = 0.72$

成功项：

$u times r times Gamma = 0.72 times 10 = 7.2$

失败损失项：

$(1 - 0.72) times 3 = 0.84$

括号内净值：

$7.2 - 2 - 0.84 = 4.36$

乘以 `q`：

$0.7 times 4.36 = 3.052$

扣除 `kappa`：

$J^("act") = 3.052 - 1.2 = 1.852$

#examplebox[
  例 1：在这组参数下，act 的一步分数为 `1.852`。若 wait 的期权价值低于它，策略应倾向于 `act`。
]

#examplebox[
  例 2：若 $Gamma$ 降到 5，其余不变：

  $u r Gamma = 0.72 times 5 = 3.6$

  $3.6 - 2 - 0.84 = 0.76$

  $0.7 times 0.76 - 1.2 = -0.668$

  此时 act 不值得。
]

== 12.3 从一步评分到 Bellman

一步评分只看眼前。Bellman 进一步比较：

- `abort`：现在放弃。
- `wait`：保留未来期权。
- `act`：现在下注。

写成价值函数就是：

$V_t = max(V_t^("abort"), V_t^("wait"), V_t^("act"))$

这一步非常重要，因为它把“现在的机会”放回“未来还会发生什么”的控制问题。

=== 为什么 `wait` 不是“什么都不做”

`wait` 的真正含义不是“世界暂停”，而是：

```text
我放弃当前 act，
但保留未来期权。
```

因此它既有代价，也有价值。

== 12.4 从 Bellman 到当前 decision artifact

当前 CLI 不是把 raw observation 直接丢给决策器，而是先构造带证据边界的 compressed decision state。  
这一步的意义是：

```text
Bellman 吃的是策略输入，
不是未经整理的原始观测。
```

== 12.5 当前仓库 paper closed loop

当前仓库闭环是：

```text
snapshot
  -> ingest-events
  -> build-decision-state
  -> decide
  -> paper-execute
  -> replay
  -> eval
```

它对应：

```text
raw observation / normalized events
  -> primitive state
  -> route candidate
  -> synthetic projection
  -> compressed decision state
  -> strategy decision
  -> execution record
  -> replay report
  -> pnl / risk report
```

#factbox[
  当前入口是 `crates/monad-mev-cli`。当前执行是 paper execution，不做签名、广播、私钥处理或 nonce 管理。
]

=== 一个完整工作流例子

```text
1. snapshot
   读取 pool 的局部可观测状态
2. ingest-events
   引入 normalized execution event 文件
3. build-decision-state
   把 primitive、route、projection 压缩成策略输入
4. decide
   用 paper Bellman policy 比较 act / wait / abort
5. paper-execute
   生成 execution record
6. replay
   在 event/seed 条件下复算结果
7. eval
   输出 PnL 与 risk
```

== 12.6 输出字段如何按对象地位阅读

当你读 `decision-state.json` 时，应按以下方式理解：

- `family/pool_address/theta_*`：primitive 的压缩或 geometry context。
- #gamma / #qt / #rt / #kappat / #ut / #pt：projection 或 synthetic calibration。
- `suggested_size/gas_limit/bid/max_fee`：策略输入或 paper execution 参数。

当你读 `replay/eval` 时：

- `realized_pnl` 是研究回放结果。
- `risk.score` 是研究风险分数。
- 它们用于比较策略，不代表真实账户资产变化。

#warningbox[
  反漂移提醒：paper execution 不是生产执行系统。教材只能把它讲成“研究可复现闭环”，不能把它讲成“实盘交易操作教程”。
]

== 12.7 为什么当前闭环对学习反而更好

paper closed loop 的教学优势在于：

```text
它先把高风险、强基础设施依赖的部分拿掉，
只留下研究对象本身。
```

于是读者可以先学会：

- 如何从观测构造 primitive。
- 如何从 primitive 构造 projection。
- 如何把 projection 放进 decision state。
- 如何通过 replay 与 eval 检查策略。

== 12.8 常见误解

#misconception[
  误解：既然 CLI 已经能 `paper-execute`，那这个仓库已经是交易机器人。

  纠正：当前闭环解决的是“研究上从观测到决策再到评估”的闭环，不是 live signer / broadcaster / executor。
]

== 12.9 小结

#chapter_summary[
  Bellman 决策把前面所有对象收束成 `act/wait/abort` 的比较。当前仓库则把这条理论链跑成 paper closed loop，让读者能把 primitive、projection、decision 和 eval 贯通起来。
]

== 12.10 练习题

#exercise[
  1. 计算题：用 $Gamma=10, q=0.7, u=0.8, r=0.9, kappa=1.2, c=2, L=3$ 重新手算 $J^("act")$。

  2. 计算题：若 `q` 降到 0.4，其余不变，`J^(act)` 变成多少？

  3. 工程题：写出当前 CLI 闭环的完整命令链。

  4. 概念题：为什么 `paper execution` 不能被讲成 live trading 教程？
]

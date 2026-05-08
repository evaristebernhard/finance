// Deprecated: this file is kept only as legacy source material.
// New entry point: docs/handbook/main.typ

#set page(paper: "a4", margin: (x: 20mm, y: 20mm))
#set text(font: ("Microsoft YaHei", "SimSun", "Arial"), lang: "zh")

= Deprecated

本文件不再是教材主入口，现仅作为旧版导览手册素材保留。

新的教材入口是：

```text
docs/handbook/main.typ
```

请使用下面命令编译新版教材：

```powershell
typst compile docs/handbook/main.typ target/monad-amm-engineering-handbook.pdf
```

#pagebreak()

#set document(
  title: "Monad + AMM + 数学建模工程手册",
  author: "monad_mev research workspace",
)
#set page(
  paper: "a4",
  margin: (x: 22mm, y: 22mm),
  numbering: "1",
)
#set text(
  font: ("Microsoft YaHei", "SimSun", "Arial"),
  lang: "zh",
  size: 10.5pt,
)
#set heading(numbering: "1.1")
#set par(justify: true, leading: 0.72em)
#show link: underline
#show raw.where(block: true): it => block(
  fill: rgb("#f7f7f7"),
  inset: 8pt,
  radius: 4pt,
  width: 100%,
  it,
)

#let callout(title, fill, stroke, body) = block(
  width: 100%,
  fill: fill,
  stroke: 0.8pt + stroke,
  inset: 9pt,
  radius: 5pt,
)[
  *#title* \
  #body
]

#let factbox(body) = callout("事实", rgb("#eef6ff"), rgb("#7aa7d9"), body)
#let assumptionbox(body) = callout("建模假设", rgb("#fff7e8"), rgb("#dfad52"), body)
#let examplebox(body) = callout("示例", rgb("#eefaf1"), rgb("#7ab883"), body)
#let warningbox(body) = callout("边界提醒", rgb("#fff0f0"), rgb("#d97979"), body)
#let intuitionbox(body) = callout("直觉", rgb("#f4f0ff"), rgb("#9b85d6"), body)
#let paramtable(body) = block(width: 100%)[#body]

#let param(
  symbol,
  name,
  unit,
  role,
  evidence,
  observability,
  example,
  intuition,
  risk,
) = [
  #paramtable[
    #table(
      columns: (22%, 78%),
      inset: 6pt,
      stroke: 0.45pt + rgb("#c9c9c9"),
      fill: (x, y) => if x == 0 { rgb("#f4f4f4") } else { none },
      [符号], [#symbol],
      [中文名], [#name],
      [单位], [#unit],
      [对象地位], [#role],
      [证据来源], [#evidence],
      [可观测性], [#observability],
      [示例值], [#example],
      [直觉解释], [#intuition],
      [估错影响], [#risk],
    )
  ]
]

#let chapter_intro(body) = callout("本章回答什么问题", rgb("#f7fbff"), rgb("#99badd"), body)
#let chapter_takeaway(body) = callout("你现在应该理解什么", rgb("#f8fff8"), rgb("#94c994"), body)

#align(center)[
  #text(size: 22pt, weight: "bold")[Monad + AMM + 数学建模工程手册]

  #v(8pt)
  #text(size: 13pt)[从 block 数组直觉到 Monad-native MEV 闭环]

  #v(20pt)
  #text(size: 10pt)[面向零 Monad 背景读者的中文 Typst 手册]

  #v(8pt)
  #text(size: 9pt)[证据来源：当前仓库代码、外部官方资料、建模假设]
]

#pagebreak()
#outline(title: [目录], indent: auto)
#pagebreak()

= 阅读说明

这本手册不是 Monad 官方白皮书，也不是 AMM 论文综述。它是一份工程手册：目标是让只知道“区块链是一串 block”的读者，能够逐步理解本仓库为什么要把 Monad MEV 问题写成：

$s_t = (G_t, M_t, C_t, R_t, E_t, F_t)$

以及为什么 `Gamma`、`q`、`r`、`kappa`、`u`、`p` 不能被当成 primitive，而应当作为 projection、proxy 或 calibration target。

#factbox[
  本手册复用以下本地锚点：
  - `docs/10-monad-mechanism/10-block-states-and-speculative-execution.md`
  - `docs/10-monad-mechanism/12-gas-pricing-and-reserve-balance.md`
  - `docs/20-core-model/20-monad-mev-main-model.md`
  - `docs/30-identification-and-data/36-first-principles-projection-derivations.md`
  - `external/monad-official/monad`
  - `external/amm-official/uniswap-v2-core`
  - `external/amm-official/uniswap-v3-core`
  - `external/amm-official/curve-core`
  - `external/amm-official/balancer-v3-monorepo`
]

#warningbox[
  本手册不会教学实盘发送交易、签名、私钥管理、nonce 管理或广播。当前仓库的闭环是 research paper execution：它用于理解状态、决策、回放与评估，不是生产交易系统。
]

= 1. 区块链最小模型

#chapter_intro[
  如果你只知道“区块链是 block 的数组”，本章把这个直觉扩展成交易、状态、执行与观测四个对象。
]

== 1.1 从数组开始

你可以先把区块链想象成一个只追加的数组：

```text
chain = [
  block[0],
  block[1],
  block[2],
  ...
]
```

每个 `block[i]` 里面有一批交易。交易不是普通数据库里的“写一行数据”，而是一段会改变全局状态的指令。状态可以粗略理解为：

```text
state = {
  account_A_balance,
  account_B_balance,
  pool_X_reserve0,
  pool_X_reserve1,
  contract_storage,
  ...
}
```

一个 block 的作用，就是把前一个状态变成下一个状态：

$S_(i+1) = "execute"("block"[i], S_i)$

#examplebox[
  假设 `state_0` 里 Alice 有 10 个 token，Bob 有 0 个 token。

  `block[0]` 包含一笔交易：Alice 给 Bob 转 3 个 token。

  那么执行后：

  - Alice: 10 -> 7
  - Bob: 0 -> 3
  - `state_1 = execute(block[0], state_0)`
]

== 1.2 为什么“看见 block”不等于“知道全部”

普通初学模型会说：block 已经在链上了，所以它就是事实。但 MEV 研究不能只看最终 block。原因是交易者做决策时，经常处在“未来 block 还没完全确定”的时刻。

你在时间 `t` 看到的东西可以分三类：

- 已经落链的事实：历史 block、receipt、log。
- 当前可见但未必最终成立的执行信息：候选块、事件、局部状态。
- 你无法直接看见、只能估计的环境：其他搜索者、传播延迟、leader 可达性。

#intuitionbox[
  如果区块链是数组，MEV 决策不是在数组写完之后回看，而是在下一个元素还没完全确定时下注。你下注的对象不是“最终事实”，而是“当前观测 + 对未来的 belief”。
]

== 1.3 最小术语

#param(
  [`block[i]`],
  [第 `i` 个区块],
  [无单位，数组下标],
  [基础数据对象],
  [当前链上数据或节点事件],
  [已落链 block 可直接观测；候选 block 需要事件重建],
  [`block[123456]`],
  [把链想成数组时，block 是数组元素。],
  [若把候选 block 当成最终 block，会高估确定性。],
)

#param(
  [`state_i`],
  [第 `i` 个区块前后的全局状态],
  [账户余额、合约存储、池储备等组成的高维对象],
  [primitive 的底层来源],
  [当前仓库代码 + 链上事实 + 建模假设],
  [完整 state 通常不能直接完整读取，只能读局部状态或重建部分事件],
  [`pool.reserve0 = 1000`, `pool.reserve1 = 1000`],
  [状态是“世界现在长什么样”。],
  [状态读错会让 AMM 价格、机会大小和风险判断全部错位。],
)

#chapter_takeaway[
  你现在应该能把区块链看成：block 数组 + 交易执行 + 状态转移 + 部分观测。后面所有 Monad/AMM/MEV 建模都只是把这四件事精细化。
]

= 2. Monad 是什么

#chapter_intro[
  本章只给工程建模所需的 Monad 直觉：Monad 不是“另一个普通 EVM 链”的简单替换，而是让 block 状态、执行事件与最终验证之间产生更细分层。
]

== 2.1 对初学者的解释

如果你已经知道 EVM 链，那么 Monad 可以先被理解为一个追求高性能、并行执行和更复杂执行流水线的 EVM-compatible 系统。对本项目而言，重要的不是“它快”，而是：

- 你看到的 execution output 可能有阶段性。
- 一个候选 block 可能经历多个 commit state。
- 交易是否最终有效，不只取决于 AMM 数学，还取决于 block、传播、reserve、冲突等机制。

#factbox[
  当前仓库文档把 Monad MEV 的 canonical primitive 写成：

  $s_t = (G_t, M_t, C_t, R_t, E_t, F_t)$

  本地锚点：`docs/20-core-model/20-monad-mev-main-model.md`。
]

== 2.2 为什么 Monad 会影响 MEV

在普通 AMM 套利教程里，常见思路是：

1. 读取池子价格。
2. 和外部价格比较。
3. 如果差价大于手续费和 gas，就交易。

Monad-native MEV 不能停在这里。你还要问：

- 这笔交易能不能及时进入相关 block？
- 当前看到的 execution output 会不会最终 survive 到 verified？
- reserve / gas 约束是否允许这笔交易？
- 这笔交易和别人是否访问同一账户或同一 storage slot？
- 如果发生重执行或冲突，损失是多少？

#intuitionbox[
  AMM 告诉你“有没有价差”。Monad 机制告诉你“这个价差能不能被你安全地拿到”。本项目研究的是两者结合后的端到端控制问题。
]

== 2.3 Monad 里的六个 primitive

#param(
  [`G_t`],
  [机会几何],
  [图、路径、pool 状态、价格锚的集合],
  [primitive],
  [当前仓库代码 + 链上事实 + 建模假设],
  [RPC 可以直接看到部分 pool state；route-level 上下文和外部价格常需 proxy 或校准],
  [`family = cpmm`, `reserve0 = 1000`, `reserve1 = 1000`],
  [它回答“市场里有什么机会”。],
  [若 `G_t` 错，`Gamma` 和路线选择会错。],
)

#param(
  [`M_t`],
  [提交态与执行推进状态],
  [block/event 状态],
  [primitive],
  [当前仓库代码 + 外部官方资料],
  [block-related events 可事件重建；leader-window 部分仍可能是 latent],
  [`Proposed -> Voted -> Finalized -> Verified`],
  [它回答“当前看到的世界能否变成最终世界”。],
  [若 `M_t` 错，`p_t` 和 `u_t` 会错。],
)

#param(
  [`C_t`],
  [竞争与传播环境],
  [延迟、对手、mempool、leader 可达性],
  [primitive],
  [外部官方资料 + 建模假设],
  [通常不能直接完整观测],
  [`competitor_bid_count = 5` 只是 proxy 示例],
  [它回答“别人和网络会怎么影响我”。],
  [若 `C_t` 错，`q_t` 会被高估或低估。],
)

#param(
  [`R_t`],
  [reserve / admissibility / survival 状态],
  [预算、gas、delegation、pending block 相关状态],
  [primitive],
  [当前仓库代码 + 建模假设],
  [规则事实可从实现核对；完整 survival 概率仍需投影],
  [`reserve_budget = 100`, `gas_cost = 2`],
  [它回答“这笔交易在预算/规则上能不能活下来”。],
  [若 `R_t` 错，交易可能理论有利但执行不可行。],
)

#param(
  [`E_t`],
  [访问结构与冲突环境],
  [account/storage access、热点、重执行环境],
  [primitive],
  [当前仓库代码 + normalized event 文件 + 建模假设],
  [事件可增强可见性；摩擦损失仍需模型],
  [`shared_storage_slots = 2`],
  [它回答“我的交易和别人会不会踩同一块状态”。],
  [若 `E_t` 错，`kappa_t` 会错。],
)

#param(
  [`F_t`],
  [费用状态],
  [base fee、gas price、fee cap 等],
  [primitive],
  [当前链上事实 + 当前仓库代码],
  [稳定链上字段通常可直接观测],
  [`base_fee = 20 gwei`],
  [它回答“行动成本是多少”。],
  [若 `F_t` 错，act 阈值会错。],
)

#chapter_takeaway[
  Monad 不是把 AMM 公式换掉，而是在 AMM 机会外面套上一层更细的状态、事件、reserve、冲突和费用约束。
]

= 3. Monad 观测层

#chapter_intro[
  本章解释“能看到什么”和“能推断什么”的差别。工程上最常见的错误，是把 RPC 快照或 synthetic 数值当成协议真值。
]

== 3.1 观测分层

本项目只允许三类证据：

1. 当前仓库代码。
2. 外部官方资料。
3. 建模假设。

在工程手册中，任何结论都要能落回这三类。比如：

- `reserve0` 来自 RPC 读取池合约，这是当前观测。
- `BlockVerified` 来自 execution event schema，这是事件层事实。
- `q_t = 0.7` 是一个 projection 或 synthetic calibration，不是协议字段。

#warningbox[
  `RPC-only` 快照可以给出某个时间点的 pool 状态，但它不能直接告诉你交易会不会入链、会不会 survive、会不会和别人冲突。这些是 projection 或 calibration target。
]

== 3.2 Execution event 的直觉

Monad 机制页把 block-related events 组织成：

- `BlockStart`
- `BlockReject`
- `BlockQC`
- `BlockFinalized`
- `BlockVerified`

研究层再把这些事件重建为：

```text
Proposed -> Voted -> Finalized -> Verified
```

#examplebox[
  假设你看到三个事件：

  ```text
  t=1: BlockStart(block_id=A)
  t=2: BlockQC(block_id=A)
  t=3: BlockFinalized(block_id=A)
  ```

  你可以说：候选块 A 至少已经从 `Proposed` 推进到 `Finalized`。

  但你不能因此说：`u_t = 1`。因为 `u_t` 是“当前 execution output 最终被 verified 并一致”的 projection。
]

== 3.3 Normalized event 文件

当前仓库采用隔离 ingest：主 MIT workspace 消费规范化 JSONL，不直接 path-depend GPL event-ring 代码。直觉上，它把上游复杂事件变成几类研究可用记录：

- `CommitStateUpdate`
- `AccessObservation`
- `TxnOutcomeObservation`

这些记录可以增强 `M_t`、`E_t`、`R_t` 的可见性，但不会直接生成全部投影值。

#param(
  [`p_t`],
  [候选块最终 canonical 的概率],
  [概率，0 到 1],
  [projection],
  [当前仓库代码 + 建模假设],
  [不能直接观测；可由 commit state 事件和模型诱导],
  [`p_t = 0.75`],
  [它是“这个候选世界最后成为真实世界”的信念。],
  [高估 `p_t` 会让你过早 act；低估会错过机会。],
)

#param(
  [`u_t`],
  [当前 execution output 最终成立的概率],
  [概率，0 到 1],
  [projection / calibration target],
  [当前仓库代码 + 建模假设],
  [不能直接从 RPC 读取；事件可增强识别],
  [`u_t = 0.8`],
  [它是“我现在看到的输出最后还能用”的信念。],
  [高估 `u_t` 会低估失败损失。],
)

#chapter_takeaway[
  观测层的关键不是“尽量抓更多数据”，而是明确每个数据到底是 direct fact、event reconstruction、proxy，还是 calibration target。
]

= 4. AMM 基础

#chapter_intro[
  本章从“没有订单簿的交易所”开始，解释 AMM 为什么可以只靠公式和流动性池定价。
]

== 4.1 AMM 与订单簿的差别

传统交易所通常有订单簿：有人挂买单，有人挂卖单，成交发生在买卖双方之间。AMM 则不同：你和一个合约池交易。池里有两种或多种 token，价格由池状态和数学公式决定。

最简单的双资产 AMM 有两个储备：

```text
reserve_x = 1000
reserve_y = 1000
```

你向池里放入 `x`，从池里拿走 `y`。交易后池的储备变化，价格也变化。

#intuitionbox[
  AMM 像一个自动售货机。它没有“对手方”在另一边点确认，而是按照机器内部的曲线报价。你买得越多，机器剩下越少，下一单位就越贵。
]

== 4.2 流动性、滑点、手续费

#param(
  [`liquidity`],
  [流动性],
  [token 数量或合约定义的 liquidity 单位],
  [primitive 或 primitive 的局部坐标],
  [AMM 合约状态],
  [CPMM 可从 reserves 直接读；CLMM 需读 active liquidity 和 tick],
  [`reserve_x = 1000`, `reserve_y = 1000`],
  [流动性越深，同样规模交易造成的价格移动越小。],
  [流动性估错会导致滑点和机会大小估错。],
)

#param(
  [`slippage`],
  [滑点],
  [百分比或价格差],
  [projection],
  [AMM 数学 + 当前池状态],
  [由交易规模和池状态计算，不是独立 primitive],
  [`expected price = 1`, `realized price = 1.02`, 滑点约 2%],
  [滑点是“你推动市场后，成交价变差的程度”。],
  [低估滑点会高估套利利润。],
)

#param(
  [`fee`],
  [AMM 手续费],
  [比例，例如 0.003],
  [primitive 或协议参数],
  [AMM 合约或协议配置],
  [很多池可直接读取；有 dynamic fee 的池需更小心],
  [`fee = 0.003` 表示 0.3%],
  [手续费会让小价差套利变得不划算。],
  [手续费估错会直接改变 `Gamma`。],
)

== 4.3 AMM 在统一模型里的位置

AMM 本身主要进入 `G_t`。但是 AMM 产生的机会，不直接等于最终收益。机会几何先变成：

$Gamma_t(P, x) = g_Gamma(s_t, P, x)$

然后再被 Monad 相关的 `q_t`、`r_t`、`kappa_t`、`u_t`、`F_t` 过滤。

#warningbox[
  `Gamma_t` 是 AMM 机会投影，不是 primitive。它由 `G_t`、路径 `P` 和规模 `x` 诱导出来。
]

#chapter_takeaway[
  AMM 是机会来源，但不是完整决策。MEV 决策要把 AMM 机会、链上机制、费用、冲突和失败概率合在一起。
]

= 5. CPMM 数学

#chapter_intro[
  本章完整走一遍常数乘积 AMM 的数值例子：储备量、手续费、输入规模、输出数量、价格冲击和 gross opportunity。
]

== 5.1 常数乘积公式

CPMM 的核心公式是：

$x dot y = k$

其中：

- `x` 是 token X 的储备。
- `y` 是 token Y 的储备。
- `k` 是交易前后大致保持不变的乘积。

如果池子有：

```text
x = 1000
y = 1000
k = 1,000,000
```

池内边际价格直觉上接近：

$P_(X -> Y) approx y / x = 1$

== 5.2 加入手续费的 swap

设手续费为 0.3%，用户输入 `Delta x = 10`。真正进入曲线计算的有效输入是：

$Delta x_("eff") = 10 times (1 - 0.003) = 9.97$

交易后 X 储备变成：

$x' = 1000 + 9.97 = 1009.97$

为了保持乘积，Y 储备应为：

$y' = k / x' = 1000000 / 1009.97 approx 990.1284$

所以用户拿到：

$Delta y = y - y' = 1000 - 990.1284 = 9.8716$

#examplebox[
  CPMM 完整数值例子：

  ```text
  初始储备: X=1000, Y=1000
  手续费: 0.3%
  输入: 10 X
  有效输入: 9.97 X
  输出: 约 9.8716 Y
  平均成交价: 10 / 9.8716 = 1.0130 X per Y
  初始池价: 1.0000 X per Y
  价格冲击: 约 1.30%
  ```
]

== 5.3 gross opportunity

假设外部市场中 `1 Y = 1.03 X`，而 CPMM 交易的平均成本约为 `1.013 X per Y`。那么每拿到 1 个 Y 的毛价差约为：

$"edge" = 1.03 - 1.013 = 0.017 X$

拿到 `9.8716 Y`，gross opportunity 为：

$Gamma approx 9.8716 times 0.017 = 0.1678 X$

这只是 AMM 几何上的毛机会，还没扣 Monad 机制成本。

#param(
  [`Gamma_t(P, x)`],
  [路径 `P` 和规模 `x` 下的 gross opportunity],
  [收益单位，例如 X 或 USD],
  [projection],
  [AMM 几何 + 外部价格锚 + 建模假设],
  [不能直接从 RPC 读取；由池状态、路径和价格锚计算],
  [`Gamma = 0.1678 X`],
  [它是“如果世界静止且我能成交，AMM 给我的毛机会”。],
  [高估 `Gamma` 会让策略在真实成本前过度乐观。],
)

== 5.4 局部二次近似

在 CPMM 或局部小规模交易下，常用近似是：

$Gamma_t(x) approx A_t x - B_t x^2$

其中：

- `A_t` 表示一开始的单位机会强度。
- `B_t` 表示规模扩大后被滑点吃掉的速度。

#param(
  [`A_t`],
  [局部线性机会系数],
  [收益 / 输入规模],
  [proxy / local coordinate],
  [AMM 数学 + 建模假设],
  [只适合 CPMM 或局部近似],
  [`A_t = 0.02`],
  [一开始每多做 1 单位，理论多赚多少。],
  [把 `A_t` 泛化到所有 AMM 会误导 CLMM/stable/weighted。],
)

#param(
  [`B_t`],
  [局部曲率/滑点系数],
  [收益 / 输入规模平方],
  [proxy / local coordinate],
  [AMM 数学 + 建模假设],
  [只适合 CPMM 或局部近似],
  [`B_t = 0.0004`],
  [规模越大，滑点越快吃掉利润。],
  [低估 `B_t` 会导致选择过大规模。],
)

#chapter_takeaway[
  CPMM 最重要的不是背公式，而是理解：储备决定价格，交易改变储备，规模越大滑点越大，`Gamma` 是由这些事实诱导的机会投影。
]

= 6. CLMM / Stable / Weighted AMM

#chapter_intro[
  本章说明为什么不能把所有 AMM 都压成 CPMM。不同 AMM 家族有不同的 pool geometry。
]

== 6.1 CLMM：集中流动性

CLMM 代表是 Uniswap v3 风格池。本地官方锚点包括：

- `external/amm-official/uniswap-v3-core/contracts/UniswapV3Pool.sol`
- `external/amm-official/uniswap-v3-core/contracts/libraries/TickMath.sol`
- `external/amm-official/uniswap-v3-core/contracts/libraries/Oracle.sol`

CLMM 的核心不再是单一 `(reserve0, reserve1)`，而是：

- `sqrtPriceX96`
- current tick
- active liquidity
- liquidity by tick
- fee tier

#examplebox[
  简化例子：

  ```text
  sqrtPriceX96 = 79228162514264337593543950336
  tick = 0
  active liquidity = 1,000,000
  fee = 0.05%
  ```

  这表示当前价格附近有一段 active liquidity。若交易把价格推过 tick 边界，下一段 liquidity 可能变化。因此 CLMM 的滑点曲线是分段的。
]

== 6.2 Stable：近锚定曲线

Stable AMM 代表是 Curve stableswap 和 Balancer StablePool。本地锚点包括：

- `external/amm-official/curve-core/contracts/amm/stableswap`
- `external/amm-official/balancer-v3-monorepo/pkg/pool-stable/contracts/StablePool.sol`

Stable 池通常服务于价格接近的资产，例如 USDC/USDT。它希望在锚定附近提供更低滑点，但远离锚定时曲线会变陡。

#intuitionbox[
  CPMM 像圆滑的双曲线；stable AMM 像中间很平、两边逐渐变陡的路。你在中间小幅交易很便宜，但把池子打偏会越来越贵。
]

== 6.3 Weighted：多资产加权池

Weighted AMM 代表是 Balancer WeightedPool。本地锚点包括：

- `external/amm-official/balancer-v3-monorepo/pkg/pool-weighted/contracts/WeightedPool.sol`

它不一定是 50/50 双资产池，可以是：

```text
Token A weight = 80%
Token B weight = 20%
```

价格由 balance vector 和 normalized weights 共同决定。这类池不能简单当成二元 CPMM。

== 6.4 家族化参数

为了统一建模，本项目把不同 AMM 家族装进：

$theta_t^("pool"), theta_t^("route")$

其中：

- `theta_pool`：池内部几何，例如 reserves、tick、liquidity、weights、amplification。
- `theta_route`：路径上下文，例如 router、vault、hook、外部价格锚。

#param(
  [`theta_t^("pool")`],
  [pool-level 几何坐标],
  [向量或结构体],
  [proxy / compressed state],
  [AMM 合约状态 + 建模压缩],
  [部分可直接读取，部分需家族化解释],
  [`cpmm: reserve0=1000, reserve1=1000`; `clmm: tick=0, liquidity=1e6`],
  [它是把不同 AMM 家族放进同一控制问题的压缩接口。],
  [压缩过度会丢失关键曲线形状。],
)

#param(
  [`theta_t^("route")`],
  [route-level 上下文],
  [路径、router、vault、hook、价格锚集合],
  [proxy / compressed state],
  [当前仓库代码 + 官方协议资料 + 建模假设],
  [通常不是单个 RPC 字段],
  [`route = token0 -> poolA -> token1`],
  [它解释“同一个池状态通过哪条路执行”。],
  [遗漏 route 约束会误估 gas、hook、冲突和失败路径。],
)

#chapter_takeaway[
  CPMM 是学习 AMM 的入口，不是所有 AMM 的统一原式。工程建模要先识别 pool 家族，再选择合适的几何坐标。
]

= 7. MEV 与套利机会

#chapter_intro[
  本章把 AMM 价差放回 MEV 闭环：机会识别、路径构造、规模选择、出价、执行和事后评估。
]

== 7.1 什么是 MEV

MEV 可以先理解为：由于交易排序、执行时机、状态可见性和市场价格差异，某些参与者可以从链上状态转移中提取额外收益。

本手册关注 AMM 套利：当链上池价格和外部价格不一致时，搜索者尝试交易，让价格回到更合理的位置，并捕获差价。

#examplebox[
  假设：

  ```text
  链上 AMM: 1 Y 约等于 1.013 X
  外部市场: 1 Y 等于 1.030 X
  ```

  你可以在 AMM 用较低成本买入 Y，再按外部价格估值。毛机会约为 `Gamma > 0`。
]

== 7.2 机会不等于收益

真正的一步期望收益可以写成：

$J_t = q_t times (u_t times r_t times Gamma_t - c_("gas") - (1 - u_t times r_t) times L_t) - kappa_t$

这里每个量的对象地位不同：

- `Gamma_t`：AMM 机会投影。
- `q_t`：入链概率投影。
- `u_t`：execution output 成立概率投影。
- `r_t`：survival 投影。
- `kappa_t`：冲突摩擦投影。
- `gas_cost`：费用/预算成本。
- `L_t`：失败损失函数。

#param(
  [`q_t(a)`],
  [动作 `a` 被及时 included 的概率],
  [概率，0 到 1],
  [projection / calibration target],
  [外部机制资料 + 建模假设],
  [不能直接从 RPC-only 读取；可用 provider-specific proxy 或事件/回放校准],
  [`q_t = 0.7`],
  [它是“我发出的交易能不能进入相关世界”的信念。],
  [高估 `q_t` 会让策略以为机会更容易捕获。],
)

#param(
  [`r_t(a)`],
  [included 后机会 survive 的概率],
  [概率，0 到 1],
  [projection / calibration target],
  [reserve 规则事实 + 建模假设],
  [规则可核对，概率需模型或校准],
  [`r_t = 0.9`],
  [它是“进块后还能不能通过 reserve/状态约束活下来”的信念。],
  [高估 `r_t` 会低估失败或 revert 风险。],
)

#param(
  [`kappa_t(a)`],
  [冲突/重执行摩擦损失],
  [收益单位],
  [projection / calibration target],
  [access events + 建模假设],
  [访问结构可事件重建；损失函数仍需校准],
  [`kappa_t = 1.2`],
  [它把热点账户、storage overlap、重执行延迟等摩擦压成成本。],
  [低估 `kappa_t` 会让策略在拥挤机会中过度交易。],
)

== 7.3 act / wait / abort

搜索者面对三个基本动作：

- `act`：现在行动，选择路径、规模、gas limit、bid、max fee。
- `wait`：暂不行动，保留未来期权。
- `abort`：放弃机会。

#intuitionbox[
  `act` 是下注，`wait` 是保留选择权，`abort` 是承认当前机会不值得研究成本或执行风险。
]

#chapter_takeaway[
  MEV 套利不是“有价差就打”。它是一个带不确定性、费用、冲突和状态约束的决策问题。
]

= 8. 统一状态模型

#chapter_intro[
  本章把前面的 Monad 和 AMM 对象放入统一核：primitive 只保留 `G/M/C/R/E/F`，常见概率和机会量全部作为投影。
]

== 8.1 primitive 状态

统一状态是：

$s_t = (G_t, M_t, C_t, R_t, E_t, F_t)$

这个 `s_t` 是研究层状态组织，不是当前代码里的某个裸结构体。它的意义是把 AMM 机会、Monad 提交态、竞争环境、reserve、访问冲突和费用放进同一个控制问题。

#factbox[
  当前 Rust workspace 中，primitive 对应 `PrimitiveStateView`。它只应承载 `g_t, m_t, c_t, r_t, e_t, f_t`，不能直接塞入 `Gamma/q/r/kappa/u/p`。
]

== 8.2 projection 状态

投影是 kernel 和 primitive 诱导出来的常见对象：

$Gamma_t(P, x), q_t(a), r_t(a), kappa_t(a), u_t, p_t$

它们不是“不重要”。恰恰相反，策略层非常需要它们。但它们的对象地位不是 primitive。

#warningbox[
  不能说“RPC 读到了 `q_t = 0.7`”。正确说法是：“在当前观测和建模假设下，我们构造了 `q_t` 的 proxy 或 synthetic calibration，示例值为 0.7。”
]

== 8.3 压缩决策态

策略不一定需要完整 `s_t`。它通常需要一个压缩态：

```text
CompressedDecisionState = {
  family,
  pool_address,
  theta_pool,
  theta_route,
  Gamma,
  p, u, q, r, kappa,
  reserve_budget,
  suggested_size,
  gas_limit,
  bid,
  max_fee,
}
```

但每个字段都必须保留：

- evidence
- role
- strength
- assumptions

否则压缩态会漂移成“裸标量表”，让读者误以为所有参数都同等可靠。

== 8.4 核心参数表

#param(
  [`a_t`],
  [动作],
  [路径、规模、gas、bid、fee cap、离散决策组成的向量],
  [control variable],
  [策略定义 + 建模假设],
  [由策略选择，不是外部观测],
  [`a_t = (P, x=10, gas_limit=180000, bid=5, max_fee=30, act)`],
  [动作是搜索者能控制的东西。],
  [动作空间定义错，Bellman 问题就错。],
)

#param(
  [`K_t`],
  [转移核],
  [条件分布],
  [primitive model object],
  [建模假设 + 可校准数据],
  [不能直接观测完整核，只能从事件和回放校准部分结构],
  [`miss/success/fail` 三种转移分支],
  [它描述“采取动作后，世界怎么随机演化”。],
  [核错会导致所有长期价值判断偏离。],
)

#param(
  [`b_t`],
  [belief],
  [概率分布],
  [canonical belief],
  [建模假设 + 观测数据],
  [完整 belief 不可直接观测，只能压缩],
  [`b_t` 认为当前候选块 verified 概率为 0.8],
  [它是“在不完全信息下我相信世界是什么样”。],
  [belief 错会让策略系统性偏向冒险或保守。],
)

#chapter_takeaway[
  统一状态模型的目的不是制造更多符号，而是防止对象地位混乱：primitive、projection、proxy、calibration 各有位置。
]

= 9. Bellman 决策

#chapter_intro[
  本章用一组完整数字演示如何从 `Gamma/q/u/r/kappa/gas_cost` 判断 `act / wait / abort`。
]

== 9.1 一步收益公式

一个简化的一步 act 分数是：

$J^("act") = q times (u times r times Gamma - c_("gas") - (1 - u times r) times L) - kappa$

其中：

- `Gamma` 是毛机会。
- `q` 是入链概率。
- `u` 是 execution output 成立概率。
- `r` 是 survival 概率。
- `gas_cost` 是执行成本。
- `L` 是失败损失。
- `kappa` 是冲突摩擦。

== 9.2 完整参数代入

按用户要求，取：

```text
Gamma = 10
q = 0.7
u = 0.8
r = 0.9
kappa = 1.2
gas_cost = 2
```

还需要给失败损失一个示例值。取：

```text
L = 3
```

先算成功有效概率：

$u times r = 0.8 times 0.9 = 0.72$

成功收益项：

$u times r times Gamma = 0.72 times 10 = 7.2$

失败损失权重：

$(1 - u times r) times L = (1 - 0.72) times 3 = 0.84$

括号内净值：

$7.2 - 2 - 0.84 = 4.36$

乘以入链概率：

$q times 4.36 = 0.7 times 4.36 = 3.052$

扣掉冲突摩擦：

$J^("act") = 3.052 - 1.2 = 1.852$

#examplebox[
  在这组参数下，`act` 的一步分数为 `1.852 > 0`。

  如果 `wait` 的期权价值低于 `1.852`，策略可以选择 `act`。

  如果 `wait` 的期权价值高于 `1.852`，策略应等待。

  如果 `act` 和 `wait` 都低于 0，则 `abort`。
]

== 9.3 wait 和 abort

`abort` 的基准价值通常写成：

$V^("abort") = 0$

`wait` 的价值是：

$V^("wait") = -K^("wait") + beta times E[V_(t+1)]$

直觉上，wait 有两个部分：

- 代价：你可能错过当前机会，或继续消耗监控资源。
- 期权：下一时刻信息可能更清楚，或者机会更大。

#assumptionbox[
  第一版 paper policy 可以用简化规则：若 `act_score > wait_score` 且 `act_score > 0`，选择 `act`；若 `wait_score >= 0`，选择 `wait`；否则 `abort`。这不是协议事实，而是研究闭环的策略假设。
]

== 9.4 参数敏感性

在上面的例子里，如果 `q` 从 0.7 降到 0.3：

$J^("act") = 0.3 times 4.36 - 1.2 = 0.108$

仍然略大于 0，但优势很小。

如果 `kappa` 从 1.2 升到 2.0：

$J^("act") = 3.052 - 2.0 = 1.052$

还能 act，但安全边际下降。

如果 `Gamma` 从 10 降到 5：

$u times r times Gamma = 0.72 times 5 = 3.6$

$3.6 - 2 - 0.84 = 0.76$

$J^("act") = 0.7 times 0.76 - 1.2 = -0.668$

此时 act 不再值得。

#chapter_takeaway[
  Bellman 决策的核心不是复杂公式，而是把“机会有多大”和“拿到机会的概率、成本、冲突、失败损失”放进同一个比较框架。
]

= 10. 当前仓库闭环

#chapter_intro[
  本章说明当前 Rust workspace 如何把前面的概念跑成 paper closed loop。它是研究闭环，不是实盘交易基础设施。
]

== 10.1 当前闭环

当前仓库闭环是：

```text
snapshot
  -> ingest-events
  -> build-decision-state
  -> plan-route
  -> decide
  -> paper-execute
  -> replay
  -> eval
```

它对应的研究流程是：

```text
RPC snapshot / normalized event file
  -> primitive state
  -> AMM-first route candidate
  -> seeded synthetic projection
  -> compressed decision state
  -> paper Bellman decision
  -> paper execution record
  -> replay
  -> pnl / risk
```

#factbox[
  当前代码边界：
  - `crates/monad-mev-rpc`：RPC-only AMM snapshot
  - `crates/monad-mev-observation`：raw observation 与 normalized event ingest
  - `crates/monad-mev-state`：primitive state 与 compressed decision state
  - `crates/monad-mev-projection`：AMM route 与 seeded synthetic projection
  - `crates/monad-mev-strategy`：paper Bellman policy
  - `crates/monad-mev-eval`：paper execution、replay、PnL、risk
]

== 10.2 CLI 示例

```powershell
cargo run -p monad-mev-cli -- ingest-events `
  --input data/fixtures/normalized-events.fixture.jsonl `
  --output data/derived/events.jsonl

cargo run -p monad-mev-cli -- build-decision-state `
  --snapshot data/fixtures/cpmm-snapshot.fixture.json `
  --events data/derived/events.jsonl `
  --seed 7 `
  --output data/derived/decision-state.json

cargo run -p monad-mev-cli -- decide `
  --state data/derived/decision-state.json `
  --output data/derived/decision.json

cargo run -p monad-mev-cli -- paper-execute `
  --decision data/derived/decision.json `
  --seed 7 `
  --output data/derived/execution.json

cargo run -p monad-mev-cli -- replay `
  --execution data/derived/execution.json `
  --events data/derived/events.jsonl `
  --seed 7 `
  --output data/derived/replay.json

cargo run -p monad-mev-cli -- eval `
  --replay data/derived/replay.json
```

== 10.3 paper execution 的边界

paper execution 只生成 `ExecutionRecord`。它的用途是：

- 记录策略在某个状态下会做什么。
- 用 seed 产生可复现的 synthetic 结果。
- 让 replay 和 eval 能跑通研究闭环。

它不做：

- 链上签名。
- 交易广播。
- nonce 管理。
- 私钥处理。
- 生产级风控。

#warningbox[
  如果你把 paper execution 当成真实执行系统，会误解整个仓库的阶段。当前目标是研究有效闭环，而不是链上资金执行。
]

== 10.4 如何读输出

当你看到 `decision-state.json`，要按对象地位读：

- `family`、`pool_address`、`reserve0` 等来自 primitive 或 direct observation。
- `Gamma`、`q`、`r`、`kappa`、`u`、`p` 来自 projection 或 synthetic calibration。
- `suggested_size`、`gas_limit`、`bid`、`max_fee` 是 paper policy 的输入或建议。

当你看到 `eval` 输出，要按研究评估读：

- `pnl.realized` 是 paper replay 的结果。
- `risk.score` 是研究风险分数。
- 它们用于比较策略，不代表真实账户收益。

#chapter_takeaway[
  当前仓库已经能跑从观测到 paper eval 的闭环。理解它的关键，是每一步都保留证据等级和对象地位，而不是把所有 JSON 字段都当成同一种真值。
]

= 术语表

#paramtable[
  #table(
    columns: (24%, 76%),
    inset: 6pt,
    stroke: 0.45pt + rgb("#c9c9c9"),
    fill: (x, y) => if x == 0 { rgb("#f4f4f4") } else { none },
    [`block`], [区块；可以先理解为区块链数组里的一个元素。],
    [`transaction`], [交易；改变链上状态的一条执行指令。],
    [`state`], [全局状态；账户余额、合约存储、AMM 储备等共同组成的世界状态。],
    [`mempool`], [未确认交易的可见集合；在本项目里只作为传播与竞争环境的一部分，不默认视为协议真值。],
    [`execution`], [执行；把交易作用到当前状态上，产生新状态、事件和输出。],
    [`reserve`], [Monad 相关的 gas/reserve/admissibility/survival 约束对象。],
    [`AMM`], [自动做市商；用池状态和公式报价的链上交易机制。],
    [`liquidity`], [流动性；池中可供交易的资产深度或协议定义的 active liquidity。],
    [`slippage`], [滑点；交易规模推动价格后，实际成交价相对初始价格变差的程度。],
    [`MEV`], [由交易排序、状态可见性、执行时机和市场差异带来的可提取价值。],
    [`primitive`], [主模型的一阶对象；本项目中是 `G/M/C/R/E/F` 和动作、转移核等。],
    [`projection`], [由 primitive、动作和 kernel 诱导出来的对象，例如 `Gamma/q/r/kappa/u/p`。],
    [`proxy`], [弱代理；数据不够强时构造的近似观测，不能当作机制真值。],
    [`calibration`], [校准；用数据、仿真或假设给 latent/projection 选择参数值。],
    [`paper execution`], [研究用纸面执行；生成可回放记录，不签名、不广播、不处理私钥。],
  )
]

= 引用与证据索引

#factbox[
  Monad 机制：
  - `docs/10-monad-mechanism/10-block-states-and-speculative-execution.md`
  - `docs/10-monad-mechanism/12-gas-pricing-and-reserve-balance.md`
  - `external/monad-official/monad/rust/crates/monad-exec-events`
  - `external/monad-official/monad/category/execution/monad/reserve_balance.cpp`
]

#factbox[
  AMM 官方资料：
  - `external/amm-official/uniswap-v2-core/contracts/UniswapV2Pair.sol`
  - `external/amm-official/uniswap-v3-core/contracts/UniswapV3Pool.sol`
  - `external/amm-official/uniswap-v3-core/contracts/libraries/TickMath.sol`
  - `external/amm-official/curve-core/contracts/amm/stableswap`
  - `external/amm-official/balancer-v3-monorepo/pkg/pool-stable/contracts/StablePool.sol`
  - `external/amm-official/balancer-v3-monorepo/pkg/pool-weighted/contracts/WeightedPool.sol`
]

#factbox[
  本仓库主模型与闭环：
  - `docs/20-core-model/20-monad-mev-main-model.md`
  - `docs/30-identification-and-data/36-first-principles-projection-derivations.md`
  - `README.md`
  - `crates/monad-mev-domain`
  - `crates/monad-mev-cli`
]

= 最后一页：学习路线

如果你是零基础读者，建议按下面顺序回读：

1. 先理解 `block[i] -> state_i -> state_(i+1)`。
2. 再理解 AMM 的 `x dot y = k` 和滑点。
3. 再理解 Monad 为什么引入 `M_t/R_t/E_t/F_t`。
4. 再理解 `Gamma/q/r/kappa/u/p` 为什么不是 primitive。
5. 最后运行当前仓库的 paper closed loop，看 JSON 输出里的 evidence/role/strength。

#intuitionbox[
  这套研究最终要回答的不是“怎么抓一个 RPC 字段”，也不是“怎么写一个 Bellman 公式”。它要回答的是：在 Monad 的协议结构、市场环境、观测能力和执行约束下，一个套利系统如何从观测走到决策，再走到评估。
]

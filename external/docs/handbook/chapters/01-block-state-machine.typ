#import "../styles.typ": *
#import "../notation.typ": *

= 1. 区块链从 block 数组到状态机

#chapter_problem[
  本章要把“区块链是 block 的数组”升级为“区块链是由交易驱动的状态机”。如果不先理解状态机，后面 Monad、AMM、MEV 的所有符号都会像突然扔上来的术语。
]

== 1.1 从最简单世界开始

先忘掉共识、费用、智能合约。只保留一个数组：

```text
chain = [block[0], block[1], block[2], ...]
```

再给世界一个状态 `S_i`。状态不是某一个账户，而是所有账户和合约存储的总和。最小例子：

```text
S_0 = {
  Alice: 10,
  Bob: 0,
}
block[0] = [
  tx_0: Alice -> Bob, amount = 3
]
```

执行 `block[0]` 后：

$S_1 = "execute"("block"[0], S_0)$

于是：

```text
S_1 = {
  Alice: 7,
  Bob: 3,
}
```

#examplebox[
  例 1：单笔转账状态转移。

  初始 `Alice=10, Bob=0`。交易 `Alice -> Bob = 3`。

  状态变化为 `Alice=7, Bob=3`。这个例子说明 block 的本质不是“存一堆文字”，而是“把旧状态变成新状态”。
]

#examplebox[
  例 2：两笔交易的顺序会影响中间状态。

  ```text
  S_0: Alice=10, Bob=0, Carol=0
  tx_0: Alice -> Bob = 8
  tx_1: Alice -> Carol = 5
  ```

  如果 `tx_0` 先执行，Alice 剩 2，`tx_1` 失败。若 `tx_1` 先执行，Alice 剩 5，`tx_0` 失败。交易顺序本身就是经济对象。
]

== 1.2 第一性推导：为什么需要状态转移函数

如果 block 只是数组元素，我们无法回答“交易后余额是多少”。所以必须引入执行函数：

$S_(i+1) = F(S_i, B_i)$

其中：

- `S_i` 是第 `i` 个 block 前的世界状态。
- `B_i` 是第 `i` 个 block。
- `F` 是执行规则。
- `S_(i+1)` 是执行后的新状态。

这一步非常关键：AMM 的价格、Monad 的 reserve、MEV 的收益，都不是孤立数字，而是某个 `F` 作用在某个 `S_i` 上之后的结果。

== 1.3 观测不是状态本身

真实系统里，你通常不能一次性读取完整 `S_i`。你只能读到局部：

- 某个账户余额。
- 某个 pool 的 reserves。
- 某笔交易 receipt。
- 某类 execution event。

因此我们要区分：

```text
真实状态 S_i
观测 O_i
根据观测形成的 belief b_i
```

#warningbox[
  反漂移规则：不能把“我通过 RPC 看到了某个 pool 的 reserve”写成“我知道完整状态”。RPC snapshot 是局部观测，不是完整机制真值。
]

== 1.4 对应到本项目

本项目最终不直接操作完整 `S_i`，而是构造研究层状态：

$s_t = (G_t, M_t, C_t, R_t, E_t, F_t)$

这不是凭空来的。它来自最小状态机问题：

- AMM 机会来自状态中的 pool 与 route，所以需要 `G_t`。
- Monad block/execution 分层影响状态是否最终成立，所以需要 `M_t`。
- 别人的交易和传播环境影响你是否能进入 block，所以需要 `C_t`。
- reserve/gas 规则影响交易是否 admissible 和 survive，所以需要 #rtstate。
- account/storage access 影响冲突，所以需要 `E_t`。
- fee 状态影响成本，所以需要 `F_t`。

#paramcard(
  [`S_i`],
  [链上全局状态],
  [账户、合约、pool 状态组成的高维对象],
  [底层状态，不是本项目最终压缩 primitive],
  [当前链上数据 + 执行规则],
  [不能完整直接观测，只能读取局部或事件重建],
  [`Alice=7, Bob=3, reserve0=1000`],
  [block 执行函数必须作用在某个状态上。],
  [误把局部观测当完整状态，会导致机会、风险和执行可行性误判。],
)

== 1.5 常见误解

#misconception[
  误解：区块链是 block 的数组，所以研究只要下载 block 就够了。

  纠正：block 数组只是历史记录。MEV 决策发生在未来 block 尚未完全确定时，研究对象必须包含状态、观测、belief 和行动后的转移。
]

== 1.6 小结

#chapter_summary[
  你现在应该能复述：区块链不是静态数组，而是 `S_(i+1)=F(S_i,B_i)` 的状态机。MEV 研究关心的不是只读历史 block，而是在不完全观测下选择行动，影响未来状态和收益。
]

== 1.7 练习题

#exercise[
  1. 概念题：为什么 `block[i]` 本身不足以定义交易后余额？

  2. 计算题：`Alice=12, Bob=1`，block 中有 `Alice -> Bob = 4` 和 `Bob -> Alice = 2`，按顺序执行后余额是多少？

  3. 工程题：在当前仓库中，找到哪个文档把主模型状态写成 `G/M/C/R/E/F`。

  4. 反思题：为什么完整状态 `S_i` 不适合作为策略直接输入？
]

#import "../styles.typ": *
#import "../notation.typ": *

= 4. Monad block state、execution event 与 verified output

#chapter_problem[
  本章真正要解决的问题是：#pt 与 #ut 到底从哪里来。它们为什么不能直接从 RPC 里读到？为什么当前仓库宁可先从 `BlockStart/BlockQC/BlockFinalized/BlockVerified` 这些事件出发，也不愿意直接把某个 provider 标签写成 canonical 真值？
]

== 4.1 从最简单的 block 分层开始

想象同一高度 `n` 上可能存在多个候选 block：

```text
height n:
  block A
  block B
  block C
```

每个候选 block 都不是瞬间“从不存在跳到最终事实”，而是可能经历多步推进。当前仓库机制页给出的研究语言是：

```text
Proposed -> Voted -> Finalized -> Verified
```

并允许某些候选块在中途被放弃：

```text
Proposed -> abandoned
Voted -> abandoned
```

这件事的第一性意义是：

```text
当前我看到某个 block 的局部执行结果，
并不等于我已经知道“这就是最终世界”。
```

== 4.2 事件是事实，概率是 belief

当前仓库能够给出的是事件层事实，例如：

```text
BlockStart
BlockReject
BlockQC
BlockFinalized
BlockVerified
```

这些是 observation / event reconstruction 层的对象。  
而 #pt 与 #ut 则是 belief / projection 层的对象。

可以把关系写成：

```text
event facts
  -> commit-state reconstruction
  -> belief about canonical / verified outcome
```

即：

$#pt = "belief induced by" #mt$

$#ut = "belief induced by block-state and output-consistency structure"$

#warningbox[
  反漂移提醒：事件可以很强，但事件不是概率。看到 `BlockQC` 不能直接写成 “因此 #pt = 1”。看到 `BlockVerified` 也不能回过头把所有事前时刻都当成完全确定。
]

== 4.3 一个完整时序例子

考虑高度 100 上两个候选块 `A` 和 `B`。

时间推进如下：

```text
t1: BlockStart(A)
t2: BlockStart(B)
t3: BlockQC(A)
t4: BlockFinalized(A)
t5: BlockVerified(A)
```

这串事件至少说明：

- `A` 在执行与提交路径上持续推进。
- `B` 没有走到与 `A` 同样的最终状态。
- 最终有一条路径比另一条更“真实”。

但在 `t3` 时刻，你仍然不能把 `A` 当成“已经 verified 的最终世界”。

#examplebox[
  数值例 1：事前 belief。

  在 `t3` 时刻，你可能根据已见事件形成：

  ```text
  p_t(A) = 0.75
  u_t(A) = 0.68
  ```

  这两个值都不是事件本身；它们是事件支撑下的 belief。
]

#examplebox[
  数值例 2：事后校准。

  到 `t5` 看到 `BlockVerified(A)` 后，你可以说：

  ```text
  事后结果：A 最终 verified
  ```

这可以被用于校准“在类似 `t3` 状态下，历史上 #pt/#ut 的估计是否偏高或偏低”，但不能反向把 `t3` 的 uncertainty 删除。
]

== 4.4 能推断什么，不能推断什么

#table(
  columns: (28%, 34%, 38%),
  inset: 6pt,
  stroke: 0.45pt + rgb("#c9c9c9"),
  fill: (x, y) => if y == 0 { rgb("#f3f3f3") } else { none },
  [观测或事件], [能推断什么], [不能直接推断什么],
  [`BlockStart(A)`], [候选块 `A` 开始进入某条执行/推进路径], [不能直接推出 #pt = 1 或 #ut = 1],
  [`BlockQC(A)`], [A 至少获得更强的推进信号], [不能直接推出 A 已 verified],
  [`BlockFinalized(A)`], [A 已进入更接近最终的状态], [不能把所有 output mismatch 风险自动设为 0],
  [`BlockVerified(A)`], [A 的相关结果在该链条下已更强成立], [不能回溯消除更早时刻的事前不确定性],
  [`provider latest/finalized 标签`], [可作为运营层 proxy 或辅助视角], [不能精确等同于完整 commit-state 语义],
)

== 4.5 为什么 #pt 不是 primitive

如果 #pt 是 primitive，意味着研究者把“最终 canonical 的概率”当作世界本身直接给定的一部分。  
但第一性上，概率不是世界本身，而是观察者在不完全信息下对世界未来走向的信念。

因此更合理的写法是：

$#pt = g_p(#st)$

其中 #mt 是它的关键来源，但它仍然是 projection，不是 primitive。

== 4.6 为什么 #ut 不是 primitive

同理，#ut 描述的是：

```text
当前可见的 local execution output
最终是否会和 verified output 一致
```

这依赖：

- 当前 block state 在哪一步。
- 当前 output 的可见范围。
- 后续路径如何选择。
- 一致性是否能保留。

所以更自然的局部分解是：

$#ut = #pt times d_t$

其中 `d_t` 是条件验证一致性。这里并不是说所有场景都必须严格乘法分解，而是强调：#ut 的第一性来源在 #mt 及其相关 output structure，而不是某个协议直接字段。

#paramcard(
  [#pt],
  [候选 block 最终 canonical 的概率],
  [概率，0 到 1],
  [projection / calibration target],
  [event reconstruction + 建模假设],
  [不能直接由 RPC-only 读取],
  [`#pt = 0.75`],
  [先有 block-state 结构和观测，再有对“最终哪条路径成为真实世界”的信念。],
  [高估 #pt 会把未定世界错当确定世界。],
)

#paramcard(
  [#ut],
  [当前可见 output 最终 verified 且一致的概率],
  [概率，0 到 1],
  [projection / calibration target],
  [event reconstruction + 建模假设],
  [不能直接由 RPC-only 读取],
  [`#ut = 0.80`],
  [先有 block-state 推进和 output consistency 问题，再有对“当前 output 最终还能不能成立”的信念。],
  [高估 #ut 会显著低估失败和误判损失。],
)

== 4.7 当前仓库为什么采用 normalized event ingest

当前工作区不是直接把完整上游事件处理逻辑链入主 MIT workspace，而是使用规范化 JSONL：

```text
CommitStateUpdate
AccessObservation
TxnOutcomeObservation
```

这是一个很重要的工程边界：

- 它承认事件是识别 #mt/#et/#rtstate 的强锚点。
- 它同时避免把上游复杂事件处理实现直接混入主研究逻辑。
- 它提醒读者：研究对象是“事件支撑的状态与投影”，而不是“某个 parser 的内部实现”。

== 4.8 常见错误写法

#misconception[
  错误写法 1：在正文里把 #pt 或 #ut 写成和文件路径一样的反引号代码样式，让人误以为它们是配置项或 JSON 键。

  错误写法 2：把 `latest/safe/finalized` 这类 provider 语义直接翻译成完整 block-state 真值。

  错误写法 3：看到事后 verified 结果，就假装事前不确定性不存在。
]

== 4.9 对象地位回收

到这里应当明确：

- `BlockStart/BlockQC/BlockFinalized/BlockVerified` 是事实或事件重建对象。
- #mt 是 primitive 的一个状态分量。
- #pt 与 #ut 是由 #mt 诱导出的 projection。

#chapter_summary[
  本章的核心不是“背几个事件名”，而是理解 observation 和 belief 的分层。事件增强识别，但不会自动把 #pt 和 #ut 变成协议真值。
]

== 4.10 练习题

#exercise[
  1. 概念题：为什么 `BlockQC` 是事实，而 #pt 是 projection？

  2. 计算题：若某时刻估计 `#pt = 0.75`，条件一致性 `d_t = 0.8`，则 #ut 约为多少？

  3. 工程题：当前仓库哪一个 normalized event 最贴近 commit-state 更新？

  4. 反思题：为什么事后看到 verified 不能消除事前决策时刻的不确定性？
]

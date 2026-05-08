#import "../styles.typ": *
#import "../notation.typ": *

= 3. Monad 为什么不是普通“更快的链”

#chapter_problem[
  本章真正要解决的问题是：为什么在本项目里，Monad 不能被理解成“普通 EVM 链，但吞吐更高一点”。如果只是速度更快，我们只需要更快地读取池子、计算 #gamma、发单即可；但本项目却必须引入 #mt、#ct、#rtstate、#et、#ft。这说明 Monad 改变的不是一个优化参数，而是研究对象的结构。
]

== 3.1 从“更快”这个直觉开始

零基础读者最自然的想法通常是：

```text
普通链：出块慢一些
Monad：出块快一些
```

如果这个理解足够，那么 MEV 模型只要把“时间间隔缩短”就行。你会得到下面这种非常诱人的简化：

```text
1. 读 AMM 池状态
2. 计算毛机会
3. 发交易
4. 等下一个 block
```

这套简化在工程上很吸引人，因为它会让你相信：

- 一切不确定性都在“能不能更快”。
- AMM 公式是核心，其他只是噪声。
- 交易只要进下一个 block，收益就差不多拿到了。

#misconception[
  误解：Monad 对建模的影响，主要是“同样的模型，速度更快，参数更极端”。

  纠正：Monad-native 问题的关键不是单一速度参数，而是 block state、execution event、verified output、传播结构、reserve 规则和访问冲突如何共同进入控制问题。
]

== 3.2 第一性问题：搜索者在决策时究竟面对什么

搜索者在时刻 `t` 不是在看一条已经写完的历史链，而是在面对一个尚未完全落定的世界。若要严格写成问题，搜索者要同时回答：

1. 当前可见池子是否真的给出一个可利用的几何机会？
2. 当前看到的 block / output 状态是否会走向最终成立的结果？
3. 我的动作是否能及时进入相关执行路径？
4. 进入后是否会因为 reserve、delegation、budget 或 state mismatch 而失败？
5. 即使成功进入，是否会因为访问冲突、热点和重执行而被摩擦吃掉？
6. 当前费用环境是否让这笔动作根本不值得做？

把这六类问题重新整理后，恰好得到六类 primitive：

$#st = (#gt, #mt, #ct, #rtstate, #et, #ft)$

这里的逻辑不是“先有六个字母，再编故事解释它们”，而是反过来：

```text
只要问题里真实存在这六类不可绕开的约束，
研究对象就必须保留这六类 primitive。
```

== 3.3 如果只有 AMM，会漏掉什么

先构造一个故意过度简化的世界：

```text
世界 A:
  只有一个 CPMM 池
  只有一个外部价格
  没有传播延迟
  没有 block state 分层
  没有 reserve 约束
  没有访问冲突
```

在这个世界里，决策几乎只取决于：

- 当前 reserves
- 外部价格
- 手续费
- 规模

于是你几乎可以把问题压成：

$"profit" approx #gammaof($P$, $x$) - "gas"$

但真实 Monad-native 世界至少还多出四类结构：

- 世界 B：你能看见 pool，但不能保证你看见的 execution output 会最终 verified。
- 世界 C：你能看见机会，但不能保证动作及时 included。
- 世界 D：即使 included，也不保证 reserve / admissibility / survival 通过。
- 世界 E：即使 survive，也不保证冲突摩擦可忽略。

这意味着：

```text
只研究 AMM 几何
  !=
研究 Monad 上的可执行套利
```

#examplebox[
  数值例 1：同一个毛机会在不同机制环境里价值完全不同。

  设某个机会在几何层面给出：

  ```text
  Gamma = 10
  gas_cost = 2
  ```

  如果你错误地只看 AMM，会觉得净边约为 8。

  但在 Monad-native 执行世界里，还可能有：

  ```text
  q = 0.35
  u = 0.7
  r = 0.8
  kappa = 1.5
  L = 3
  ```

  此时“真正可执行的价值”远低于 8。
]

#examplebox[
  数值例 2：两个搜索者看到相同价差，但不一定面对同一问题。

  ```text
  Searcher A: q = 0.85
  Searcher B: q = 0.30
  Gamma = 6
  ```

  即使两人对同一池、同一价格锚、同一规模做出完全相同的几何计算，他们的 act 决策也可能完全不同。区别并不在 AMM，而在传播与机制位置。
]

== 3.4 Monad 在建模上到底改变了什么

用教材语言说，Monad 对本项目的意义不是“给已有 AMM 模型换更小的毫秒数”，而是把“机会是否存在”和“机会是否可执行”强行分开。

这个分离可以写成三层：

```text
第一层：机会是否在几何上存在？
第二层：当前世界是否会走向我能利用的执行结果？
第三层：我的动作是否能进入并 survive？
```

对应到本项目对象：

- 第一层主要由 #gt 决定。
- 第二层主要由 #mt 决定，并与 #ut、#pt 相关。
- 第三层由 #ct、#rtstate、#et、#ft 共同决定，并投影为 #qt、#rt、#kappat。

因此，本项目研究的是：

```text
几何机会
  -> 执行环境
  -> 行动与收益
```

而不是：

```text
几何机会
  -> 直接收益
```

== 3.5 为什么需要 #mt

如果一个世界里 block 只有“未确认/已确认”两层，很多人会把 output 是否成立当成近似二值问题。

但当前仓库的 Monad 机制页明确提示：更稳的入口是 block-related events 和 commit-state 重建，而不是直接假装知道某个 canonical 真值。

因此在研究层，必须保留 #mt：

- 它回答“当前 block / output 位于哪一层推进状态”。
- 它承接 event layer 与 belief layer 的关系。
- 它是 #pt 和 #ut 的第一性来源之一。

#factbox[
  当前仓库锚点：
  - `docs/10-monad-mechanism/10-block-states-and-speculative-execution.md`
  - `external/monad-official/monad/rust/crates/monad-exec-events`
]

== 3.6 为什么需要 #ct

如果没有传播与竞争环境，动作能否入链会被偷换成：

```text
只要我决定 act，交易就进入相关 block
```

这是错误的。`act` 只是你做了一个选择，不是世界已经为你执行了这个选择。  
从第一性上看，“动作被世界采纳”是额外的随机结构，它必须通过 #ct 与 #mt 的共同作用进入：

$#qof($a$) = "projection induced by" #ct " and " #mt$

== 3.7 为什么需要 #rtstate

很多初学模型把 gas 看成利润表里的一项：

```text
net_profit = gross_profit - gas
```

但本项目要表达的是：

```text
有些动作不是利润变低，
而是因为 reserve / admissibility 规则直接变成不可行动作。
```

这就是为什么必须有 #rtstate，而不是只在最后扣一笔成本。

== 3.8 为什么需要 #et

如果交易之间不共享状态，冲突摩擦可以忽略。  
但真实执行里，访问同一账户、同一 storage slot、同一路径对象，会使重执行、热点和冲突损失变成真实经济量。这些不能被“平均误差”吞掉，所以要保留 #et。

== 3.9 为什么需要 #ft

费用不是背景常数。base fee、gas price、bid、max fee cap 都会改变 act 的阈值与可行动作集合。因此 #ft 是 primitive，而不是后验修正项。

== 3.10 对象地位回收

到这里，应该能清楚看到：

- #gt、#mt、#ct、#rtstate、#et、#ft 是研究对象的 primitive 分量。
- #gamma、#qt、#rt、#kappat、#ut、#pt 都是由这些 primitive 和动作诱导出来的决策量。

#paramcard(
  [#mt],
  [Monad 提交态、block state 与 execution-stage 状态],
  [离散状态、事件重建或 belief 来源],
  [primitive],
  [当前仓库代码 + 外部官方资料],
  [部分可事件重建，不能完整直接观测成单一真值],
  [`Proposed -> Voted -> Finalized -> Verified`],
  [如果 world state 的推进本身影响 output 是否最终成立，那么这部分就必须先于 #ut/#pt 被保留。],
  [误删 #mt，会把 verification/canonical 不确定性误写成纯噪声。],
)

#paramcard(
  [#ct],
  [竞争与传播环境],
  [延迟、对手、可见性、leader 可达性等状态],
  [primitive],
  [外部机制说明 + 建模假设],
  [通常不能直接完整观测],
  [`competitor density`、`leader reachability` 只是 reduced-form 示例],
  [如果 act 不必然等于 included，则动作进入世界的门槛必须来自一个独立状态分量。],
  [误删 #ct，会把 #qt 错写成协议直接保证。],
)

== 3.11 小结

#chapter_summary[
  Monad 对本项目的影响不是单一速度参数，而是把“几何机会”与“可执行机会”分开。只要 block state、传播、reserve、冲突和费用会改变决策，它们就必须进入 primitive 结构，而不能被塞回误差项。
]

== 3.12 练习题

#exercise[
  1. 概念题：如果一个模型只有 AMM 机会和 gas 成本，它为什么还不足以研究 Monad-native MEV？

  2. 计算题：若 $Gamma=10$、$q=0.35$、$u=0.7$、$r=0.8$、$L=3$、$c=2$、$kappa=1.5$，按一步 act 分数公式，粗略算出该机会为什么会比“净边 8”小很多。

  3. 工程题：在当前仓库文档中，哪一页最明确地说明了 block-related events 与 commit-state 的关系？

  4. 反思题：为什么“Monad 更快”这个说法虽然不完全错，但对本项目的研究对象来说是不够的？
]

#import "../styles.typ": *
#import "../notation.typ": *

= 附录 B. Monad 机制案例集：从事件到研究对象

#chapter_problem[
  这个附录通过具体案例把 Monad 机制拆开，让读者看到为什么 block state、传播、reserve、访问冲突和 verified output 不是抽象术语，而是会真实改变套利问题结构的对象。
]

== B.1 案例一：同一高度的两个候选 block

设高度 `n=120` 上先后出现两个候选块：

```text
t1: BlockStart(A)
t2: BlockStart(B)
t3: BlockQC(A)
t4: BlockFinalized(A)
t5: BlockVerified(A)
```

这至少说明：

- `A` 和 `B` 都曾进入观测窗口。
- `A` 获得了更强推进。
- `B` 没有和 `A` 走到同样终态。

但在 `t2/t3` 时刻，你仍然不能说“世界已经确定是 A”。

#examplebox[
  若某笔套利在 `A` 的局部 output 下看起来盈利，在 `B` 下不盈利，那么问题不是“利润等于多少”，而是“哪条分支会成为最终世界”的不完全信息问题。
]

== B.2 案例二：provider 标签为什么不等于 commit-state

工程上很容易偷懒，用：

```text
latest / safe / finalized
```

来代替完整的 block-state 语义。  
但从研究对象看，provider 标签只是基础设施视角，不是 commit-state 真值。

#warningbox[
  如果你把 provider 标签直接翻译成完整的 commit-state 结构，就把 weak proxy 写成了机制事实。
]

== B.3 案例三：传播差异如何重写同一机会的价值

同一个 #gamma，对两个搜索者的意义可能不同：

```text
Searcher A: q = 0.85
Searcher B: q = 0.30
Gamma = 5
u = 0.8
r = 0.9
```

这说明：同一个 AMM 机会不是一个“对所有人相同的对象”，而是一个“在给定传播位置下才有具体行动价值的对象”。

== B.4 案例四：reserve 把动作从“低收益”变成“不可行”

设：

```text
b = 100
c_gas = 60
m1 = 30
m2 = 20
```

则总占用为：

$60 + 30 + 20 = 110 > 100$

此时问题不是“该动作利润下降”，而是“该动作不在可行动作集合里”。

== B.5 案例五：访问冲突为什么不是小误差

若两笔交易访问同一账户或 storage slot：

```text
tx_A touches slot S
tx_B touches slot S
```

则 #kappat 可能变成系统性损失，而不是零均值噪声。

#examplebox[
  若 `kappa=0.1` 与 `kappa=1.8` 的两种世界其余条件相同，act 的价值可能从明显为正直接掉到接近零甚至为负。
]

== B.6 案例六：fee 状态为什么是 primitive

如果 base fee 从 10 升到 40，而其他条件不变，某些原本可行的动作会因为成本和 budget 约束直接失去吸引力。  
这说明 #ft 不是背景常数，而是会改变可行动作集合和 act 阈值的 primitive 状态。

== B.7 六个案例合起来说明什么

```text
同一个 AMM 价差
  + 不同 block state
  + 不同传播位置
  + 不同 reserve 约束
  + 不同冲突环境
  + 不同 fee 状态
  =
不同的决策问题
```

#chapter_summary[
  案例集的意义是把抽象对象压回真实情景。你不需要先相信复杂符号，只要接受这些情景都会改变决策价值，就会明白为什么必须保留对应的 primitive 和 projection。
]

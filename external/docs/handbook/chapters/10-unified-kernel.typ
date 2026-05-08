#import "../styles.typ": *
#import "../notation.typ": *

= 10. 统一核模型：为什么 `G/M/C/R/E/F` 是 primitive

#chapter_problem[
  本章要回答一个核心理论问题：为什么本项目把 #gt/#mt/#ct/#rtstate/#et/#ft 当作 primitive，而不是把 #gamma/#qt/#rt/#kappat/#ut/#pt 当作 primitive？这是整套研究防漂移的核心。
]

== 10.1 从最简单问题开始

如果你只研究一个静止 CPMM 池，似乎只要：

```text
Gamma(x)
```

就能讨论机会。但一旦把问题换成“在 Monad 上执行套利”，你还必须回答：

- block/output 是否成立？
- 我的交易是否 included？
- reserve 是否允许？
- access 是否冲突？
- 费用环境如何变化？

所以，单个 #gamma 不足以定义问题。

== 10.2 一个反方向论证：如果把投影错当 primitive，会怎样

假设 #gamma、#qt、#rt、#kappat、#ut、#pt 都是 primitive。  
那么你会立刻遇到几个矛盾：

1. #qt 明显依赖动作 `a`，为什么还能被写成“世界先验给定的状态分量”？
2. #gamma 明显依赖路径和规模，为什么还能被写成“动作之前就存在的世界状态”？
3. #ut/#pt 明显是 belief 或吸收概率，为什么还能被写成“世界直接给出的字段”？

这说明：

```text
策略最关心某个对象
  !=
该对象就是 primitive
```

== 10.3 第一性推导：primitive 应该回答什么

primitive 应该是“不能再继续降级为更基本对象的控制状态分量”。在本项目里：

$s_t = (G_t, M_t, C_t, R_t, E_t, F_t)$

因为：

- `G_t`：市场和几何来源。
- `M_t`：提交态和 execution-stage。
- `C_t`：竞争和传播环境。
- #rtstate：reserve/admissibility/survival 规则。
- `E_t`：访问结构与冲突环境。
- `F_t`：费用状态。

而 #gamma / #qt / #rt / #kappat / #ut / #pt 都依赖这些状态与动作，所以它们是 projection。

#factbox[
  本仓库文档锚点：`docs/20-core-model/20-monad-mev-main-model.md`。
]

== 10.4 为什么 #gamma 不是 primitive

#gammaof($P$, $x$) 依赖：

- 哪个 AMM 家族。
- pool 当前状态。
- route 上下文。
- 外部价格锚。
- 交易规模 `x`。

因此它不是世界状态本身，而是“给定状态和动作后计算出的机会函数”。

== 10.5 为什么 `q/r/kappa/u/p` 不是 primitive

同理：

- #qof($a$) 依赖传播和竞争环境。
- #rof($a$) 依赖 reserve/survival 规则和动作。
- #kappaof($a$) 依赖冲突与重执行环境。
- #ut/#pt 依赖 block state 和验证路径。

它们都是：

```text
state + action + kernel
  -> induced quantity
```

而不是 primitive state 自己。

#paramcard(
  [`s_t`],
  [统一核状态],
  [由六类 primitive 状态分量组成的结构],
  [primitive],
  [当前仓库代码 + 外部官方资料 + 建模假设],
  [不能一次性完整直接观测],
  [`s_t = (G_t, M_t, C_t, R_t, E_t, F_t)`],
  [控制问题必须先知道“世界由哪些类状态组成”。],
  [若 primitive 选错，后续 projection、Bellman 和校准都失去基础。],
)

== 10.6 为什么 primitive 不等于“当前能读到的字段”

这是本项目最重要的认识论提醒之一：

```text
研究对象先于数据面
```

换句话说，如果一个对象在问题结构中不可绕开，即使当前只能弱观测，也不能因为“现在读不到”就把它从 primitive 中删除。

== 10.7 常见误解

#misconception[
  误解：既然策略最关心 #gamma / #qt / #rt / #kappat / #ut / #pt，那它们就应该是 primitive。

  纠正：一个对象“重要”不等于它“基础”。恰恰因为策略关心它们，所以更要明确它们是从更基础的 primitive 中导出的投影。
]

#warningbox[
  反漂移提醒：观测层不能反向定义 primitive。即使当前只能读 RPC 快照，也不能因此把“能读到的字段”当成研究对象的全部。
]

== 10.8 小结

#chapter_summary[
  primitive 回答“世界由什么构成”；projection 回答“这些状态诱导出什么决策相关量”。本项目之所以坚持 `G/M/C/R/E/F`，是为了不让研究对象被某个局部工具、局部数据面或局部公式绑架。
]

== 10.9 练习题

#exercise[
  1. 概念题：为什么 #gamma 重要但不是 primitive？

  2. 概念题：#qof($a$) 为什么天然依赖动作 $a$？

  3. 工程题：当前 workspace 中哪个类型只承载 `g_t/m_t/c_t/r_t/e_t/f_t`？

  4. 反思题：如果把 #qt 错当 primitive，会导致什么建模后果？
]

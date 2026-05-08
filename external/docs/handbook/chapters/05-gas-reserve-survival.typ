#import "../styles.typ": *
#import "../notation.typ": *

= 5. gas、reserve、admissibility 与 survival

#chapter_problem[
  本章真正要解决的问题是：为什么“有毛机会”不等于“动作可行”。在 Monad-native 环境里，gas 不只是利润表里的一项成本，reserve/admissibility/survival 也不是补充说明，而是会直接改变动作集合与最终收益的第一性结构。
]

== 5.1 从预算世界开始

先构造一个没有 AMM、没有传播、没有冲突的最小世界，只保留预算约束：

```text
当前账户可用预算 = 100
动作 a 的 upfront gas-style 占用 = 40
前两块遗留 obligation = 25 和 20
```

则这个动作是否“允许被考虑”，不是看它毛机会多大，而是先看：

$c_("gas") + m_1 + m_2 = 40 + 25 + 20 = 85 <= 100$

这说明：

```text
动作先要进入 admissible set，
然后才谈收益。
```

#examplebox[
  数值例 1：可行动作。

  总占用 85，小于预算 100，因此该动作进入可行集合。
]

#examplebox[
  数值例 2：不可行动作。

  若动作改成 `c_gas = 65`，则：

  $65 + 25 + 20 = 110 > 100$

  即使几何毛机会很大，这个动作也不应进入策略优化问题。
]

== 5.2 第一性推导：为什么 gas 既是成本又是约束

教科书里常把 gas 写成：

```text
net_profit = gross_profit - gas_cost
```

这在某些近似下没错，但对本项目不够。第一性上，gas 至少有两层作用：

1. 作为执行成本，进入收益函数。
2. 作为 upfront budget 占用，进入可行动作集合。

所以 gas 不是单纯“多扣一笔钱”，它还会回答：

```text
这个动作是不是根本不能被执行？
```

== 5.3 为什么要把 reserve 单独建模成 #rtstate

如果 reserve 只是收益修正项，我们可以最后统一扣一个 penalty。  
但实际更强的情况是：

```text
有些动作不是收益低，
而是直接不可行。
```

这就要求把 reserve 相关结构保留在 primitive 里，也就是 #rtstate。

#factbox[
  本地锚点：
  - `docs/10-monad-mechanism/12-gas-pricing-and-reserve-balance.md`
  - `external/monad-official/monad/category/execution/monad/reserve_balance.cpp`
]

== 5.4 admissibility 与 survival 的分解

动作的命运至少可以分成两步：

1. admissibility：动作是否满足当前规则、预算、delegation、环境检查等条件。
2. survival：动作即使 included，是否仍能在执行后保留你想要的结果。

这就是为什么本项目把 survival 投影写成：

$#rof($a$) = chi_t(a) times rho_t(a)$

这里：

- `chi_t(a)` 更偏向“能否被允许进入相关路径”。
- `rho_t(a)` 更偏向“进入后是否还能活下来”。

这个分解的第一性意义在于：  
你不是直接假装知道一个神秘的 #rt 值，而是先承认它来自更基本的规则结构。

#examplebox[
  数值例 3：`chi` 与 `rho` 分开理解。

  若：

  ```text
  chi = 0.95
  rho = 0.80
  ```

  则：

  $#rof($a$) = 0.95 times 0.80 = 0.76$

  这意味着：动作先大概率 admissible，再在已进入的情况下以 80% 概率 survive。
]

== 5.5 为什么 #rt 不是协议字段

当前代码能直接支撑很多 reserve 规则事实，例如：

- revision gating
- delegated account 限制
- pending block 与当前块环境检查
- 某些 exemption 分支

这些都是事实层。  
但 #rt 仍然不是某个合约或节点直接吐给你的字段，因为它是：

```text
规则事实 + 当前状态 + 动作 + 不确定性
  -> survival projection
```

所以更合理的写法是：

$#rt = "projection induced by" #rtstate " and action"$

== 5.6 与费用状态 #ft 的关系

`base fee`、`priority bid`、`max fee cap` 不仅出现在成本函数里，还会与 reserve 约束一起定义动作的可行域。因此 #ft 必须是 primitive。

若写成局部成本形式，可记：

$c_t(a) = ell_t times min(F_t + pi_t, bar(F)_t)$

但这只是进入控制问题的 reduced-form 表达，不是逐行协议实现。

== 5.7 对象地位：谁是事实，谁是投影

#paramcard(
  [#rtstate],
  [reserve / admissibility / survival 相关 primitive 状态],
  [规则、预算与环境约束组成的状态分量],
  [primitive],
  [当前仓库代码 + 建模假设],
  [部分规则可核对，完整状态通常需压缩表示],
  [`b_t = 100`, `delegated = false` 只是局部示例],
  [只要规则会改变动作集合，就必须先保留这类状态。],
  [误删 #rtstate 会把不可行动作误当低收益动作。],
)

#paramcard(
  [#rt],
  [动作的 survival 投影],
  [概率，0 到 1],
  [projection / calibration target],
  [规则事实 + 建模假设],
  [不能直接完整观测],
  [`#rof($a$) = 0.76`],
  [先有 reserve/admissibility 结构，再有 survival belief。],
  [高估 #rt 会系统性低估失败、revert 或预算冲突。],
)

== 5.8 常见错误写法

#misconception[
  错误写法 1：把 gas 只当作利润表上的“扣掉一项”。

  错误写法 2：把 #rt 直接写成“协议给定的概率”。

  错误写法 3：不区分 admissibility 与 survival，导致“不可行动作”和“低价值动作”混为一类。
]

#warningbox[
  反漂移提醒：即使 reserve 规则来自当前代码事实，也不能因此把某个示例数值 `0.9` 写成协议直接给出的 #rt。示例值只是 projection 或 calibration。
]

== 5.9 对应到当前 CLI 闭环

在当前 workspace 中：

- primitive state 里会保留与 reserve、gas、事件相关的局部事实。
- compressed decision state 里可能出现 budget、gas limit、max fee 等决策输入。
- paper Bellman policy 再把它们一起变成 act / wait / abort 比较。

这说明教材不能把 reserve 写成“实现细节”，因为它已经直接进入研究闭环。

== 5.10 小结

#chapter_summary[
  gas 和 reserve 的第一性意义在于：它们定义动作是否可行，而不仅仅是动作值多少钱。#rtstate 是 primitive；#rt 是由规则、状态和动作诱导出的 survival projection。
]

== 5.11 练习题

#exercise[
  1. 概念题：为什么 gas 不是单纯的利润扣减项？

  2. 计算题：若预算为 120，`c_gas=50`，`m_1=30`，`m_2=20`，动作是否可行？

  3. 计算题：若 `chi=0.95`、`rho=0.8`，则 #rof($a$) 为多少？

  4. 工程题：当前文档中哪个锚点最直接支持 reserve-balance 规则事实？
]

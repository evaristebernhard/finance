#import "../styles.typ": *
#import "../notation.typ": *

= 2. EVM 与交易执行的最小模型

#chapter_problem[
  本章解释交易为什么不是“数据库 update”，而是带 gas、失败、日志和合约调用的执行过程。Monad 虽然有自己的机制细节，但第一步仍要先理解 EVM 风格执行的最小模型。
]

== 2.1 从最简单世界开始

把一笔交易看成一条指令：

```text
tx = {
  from: Alice,
  to: ContractOrBob,
  input: calldata,
  gas_limit: 100000,
  max_fee: 30,
}
```

执行后会产生：

```text
result = {
  success: true/false,
  gas_used,
  logs,
  state_delta,
}
```

如果 `to` 是普通账户，交易可能只是转账。如果 `to` 是合约，交易会运行合约代码，读取/写入 storage，并可能调用其他合约。

#examplebox[
  例 1：普通转账。

  `Alice -> Bob = 3`，gas 用于支付执行成本，但状态变化主要是余额变化。
]

#examplebox[
  例 2：AMM swap。

  `Alice -> Pool.swap(10 X)` 会读取池子的 reserves，计算输出，写回新 reserves，并把 token Y 转给 Alice。它不是单行转账，而是一段合约执行。
]

== 2.2 第一性推导：为什么要有 gas

如果执行合约代码没有成本，恶意用户可以提交无限循环，迫使节点永远运行。因此系统需要 gas：

$"gas_cost" = "gas_used" times "gas_price"$

gas 有两个作用：

- 限制执行资源。
- 给执行资源定价。

在策略建模中，gas 不只是费用，还会进入 reserve/admissibility 约束。也就是说，一笔交易不是“有利润就能做”，还必须满足执行预算条件。

== 2.3 成功、失败与 receipt

交易可能成功，也可能失败。失败不等于没有成本。常见情况：

- 合约 `revert`。
- gas 不够。
- 状态和预期不同。
- 访问路径触发额外冲突或限制。

因此我们要记录：

```text
TxnOutcomeObservation = {
  tx_hash,
  success,
  gas_used,
  effective_gas_price,
}
```

#warningbox[
  反漂移规则：不能只用“是否看到价差”判断收益。交易失败、gas 消耗、状态变化和执行路径都会影响最终 PnL。
]

== 2.4 对应到本项目对象地位

执行过程主要服务于三个 primitive：

- #rtstate：gas/reserve/admissibility/survival。
- #et：account/storage access 与冲突环境。
- #ft：费用状态。

从执行结果进一步构造出的 #rof($a$) 和 #kappaof($a$) 不是 primitive。它们是 projection。

#paramcard(
  [`gas_limit`],
  [交易愿意消耗的最大 gas],
  [gas 单位],
  [动作分量 / control variable],
  [交易字段 + 策略选择],
  [交易里可见；未来实际 `gas_used` 需执行后知道],
  [`gas_limit = 180000`],
  [必须限制执行资源，否则合约可无限消耗节点计算。],
  [设置太低会失败；设置太高会占用 reserve 预算。],
)

#paramcard(
  [`gas_used`],
  [实际消耗 gas],
  [gas 单位],
  [执行结果事实],
  [receipt / normalized event],
  [执行后可观测],
  [`gas_used = 135000`],
  [它是实际执行路径消耗的资源。],
  [估错会影响成本、reserve 占用和策略评分。],
)

== 2.5 常见误解

#misconception[
  误解：交易只要成功进入 block，就一定按我预期赚钱。

  纠正：进入 block 只是 included。它还可能因为状态变化、reserve、revert、冲突或价格滑点导致收益不如预期。因此本项目把 included、survive、friction 分开建模。
]

== 2.6 小结

#chapter_summary[
  EVM 风格执行告诉我们：交易是有成本、有失败、有日志、有状态读写的程序执行。MEV 建模不能只看交易是否存在，还要看执行路径、gas、结果和访问结构。
]

== 2.7 练习题

#exercise[
  1. 概念题：为什么 gas 是执行模型的第一性对象？

  2. 计算题：`gas_used=120000`，`gas_price=25 gwei`，费用是多少 gwei？

  3. 工程题：当前仓库 normalized event schema 中哪个对象记录 `success` 和 `gas_used`？

  4. 概念题：为什么 `gas_used` 是事实，而 #rof($a$) 是 projection？
]

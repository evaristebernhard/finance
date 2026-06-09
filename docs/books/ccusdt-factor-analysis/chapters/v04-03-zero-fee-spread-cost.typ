#import "../styles.typ": definition, proposition, evidence, remark

= 第 3 章：为什么零手续费仍然有成本

== 本章要解决的困惑

用户最容易困惑的一点是：如果交易所 taker fee 为零，为什么策略收益还会被“成本”吃掉？答案是，手续费只是显式费用；价差、到达时盘口变化、深度滑点和逆向选择是执行成本。零手续费不等于零执行成本。

== 一个具体例子

假设入场时：

```text
bid = 100.00
ask = 100.02
mid = 100.01
```

做多者用 taker 买入，成交在 ask=100.02。60 秒后中间价涨到 100.04，但盘口是：

```text
bid = 100.03
ask = 100.05
mid = 100.04
```

如果按中间价看，似乎赚了：

$ 10000 log(100.04 / 100.01) approx 3.00 "bps" $

但实际 taker 出场要卖给 bid=100.03，真实收益是：

$ 10000 log(100.03 / 100.02) approx 1.00 "bps" $

中间价涨了 3 bps，taker 往返只留下约 1 bps，差额就是入场和出场价差。

== 从例子推导数学对象

做多 taker：

$ R_"long,taker" = 10000 log(b_"exit" / a_"entry") $

做空 taker：

$ R_"short,taker" = 10000 log(b_"entry" / a_"exit") $

如果只看中间价收益，做多为：

$ R_"long,mid" = 10000 log(m_"exit" / m_"entry") $

二者的差可以近似看作：

$ R_"taker" approx R_"mid" - s_"entry" / 2 - s_"exit" / 2 $

这里没有手续费项。若手续费为零，公式仍然有价差项。

== 正式定义

#definition("显式费用", [
  显式费用是交易所费率，例如 maker fee、taker fee。Bullish CCUSDT 当前研究基线把显式 fee 设为 0。
])

#definition("执行摩擦", [
  执行摩擦包括 crossing spread、arrival quote movement、depth slippage、latency slippage 和 adverse selection。它们不是 fee，但会改变实际成交价。
])

#proposition("零手续费不推出零成本", [
  在 top-of-book taker 模型下，即使 fee 为 0，只要 $a_t>b_t$，一次先买后卖或先卖后买的往返就存在价差成本。
])

== CCUSDT 实证证据

#evidence("fast mid 与 taker 差异", [
  最近策略实验里，fast mid-edge 与 strict/fast taker round-trip net 的差异主要来自 entry/exit crossing spread。旧三日结果中，平均 taker entry+exit execution cost 约 1.2966 bps，其中 exit cost 约 1.0774 bps。这说明真正压缩收益的不是显式 fee，而是成交价格。
])

== 失败机制

一个因子可以正确预测中间价方向，但仍然不值得 taker 下单。原因是预测幅度不够覆盖价差。如果预期中间价只动 0.8 bps，而往返价差成本是 1.3 bps，那么方向正确也可能亏。

#remark("entry spread gate 的意义", [
  entry-spread q70 admission gate 不是在预测 alpha，而是在过滤执行环境。它的直觉是：如果入场 crossing 已经太贵，短周期 edge 很容易被价差吃掉。
])

== 策略/runtime 边界

运行时可以看到当前 bid/ask，因此可以计算入场 crossing cost。未来出场 spread 不可提前知道，只能用历史条件分布、保守压力项或 exit controller 处理。任何把未来 exit spread 当作入场特征的做法，都是泄漏。

== 本章小结

零手续费只移除了 fee，不移除 spread。短周期策略必须分开记录：中间价 edge、entry spread、exit spread、latency、depth slippage、capacity clipping。否则很容易把“因子没用”和“执行吃掉收益”混在一起。


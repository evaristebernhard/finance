#import "../styles.typ": definition, proposition, evidence, remark, factor

= 第 10 章：入场质量与分布估计

== 本章要解决的困惑

短周期右尾策略不能只看均值或中位数。一个结构可能大多数时候小亏，但少数时候有很大的右尾。如果右尾能被运行时状态识别，同时左尾能被控制，它仍然可能有价值。

== 一个具体例子

考虑两个 entry 组：

```text
A 组：多数 +1 bps，偶尔 -20 bps
B 组：多数 -0.5 bps，偶尔 +30 bps
```

如果只看 median，A 组好于 B 组。但如果 B 组的右尾可以被某个运行时条件识别，且左尾不会在高杠杆下放大，B 组也可能有策略价值。

== 从例子推导数学对象

对某个状态 $A$，我们真正关心的不是单点均值，而是条件分布：

$ F_(R | X in A, C=c) $

这里 $R$ 是收益，$X$ 是因子状态，$C$ 是控制条件，例如日期、价差、深度、容量环境。

常见统计量：

$ "mean" = E[R | A] $

$ "median" = Q_0.5(R | A) $

$ "CVaR"_alpha = E[R | R <= Q_alpha(R), A] $

$ "tail_share"_q = (sum_(R_i > Q_q) R_i) / (sum_i R_i + epsilon) $

CVaR 看左尾，tail_share 看右尾集中度。

== 正式定义

#definition("entry quality", [
  entry quality 是某类 entry 在给定运行时可见状态下的未来路径分布质量。它不是单个均值，也不是事后 PnL 标签。
])

#definition("收缩估计", [
  当某个 bucket 样本少时，可以把该 bucket 均值向父层均值收缩：$hat(mu)_A = lambda_A bar(r)_A + (1-lambda_A) hat(mu)_(pi(A))$。这降低小样本过拟合风险。
])

== CCUSDT 实证证据

#evidence("entry estimation", [
  Entry-level hierarchical shrinkage 报告中，active entries 1715、strict estimates 1665；`strong_positive` 有 252 entries、weighted mean 约 7.5693；`positive_right_tail_fragile` weighted mean 约 3.5521。分类是估计状态，不是机械删除规则。
])

== 失败机制

`net_median < 0` 不是删除结构的充分理由。原因很简单：net median 已经是 cost-adjusted 中位点，它只说明超过一半 entry 的结果不理想，不说明右尾不可捕获，也不说明左尾不可控。

真正危险的是以下情况：

- 右尾集中在一天或少数几笔。
- 左尾在高 exposure 时出现。
- 右尾只能用未来标签识别。
- capacity clipping 后保留了左尾、剪掉了右尾。
- strict taker 后收益被价差完全吃掉。

#remark("右尾结构的判断", [
  右尾策略的最低要求不是 median 为正，而是右尾机制可解释、跨日不过度集中、左尾有 CVaR 约束、capacity 不放大坏路径、strict execution 后仍有剩余。
])

== 策略/runtime 边界

entry quality 的估计可以离线做，但入场时只能使用运行时安全的分类器。未来收益、MFE、MAE、path class 都不能作为当前 entry 的直接输入。它们可以用于训练、诊断和 promotion checklist。

== 因子卡片

#factor("右尾质量 / 左尾约束", [
  中文名：右尾质量、左尾约束。英文/代码名：right-tail、CVaR、tail_share。它测量收益分布形状，而不是单点均值。它可能有效，是因为 CCUSDT TFI 结构有右尾；它会失败，是因为右尾可能不可前验识别，或被 capacity/execution 剪掉。
])

== 本章小结

因子分析必须从条件分布而不是单点均值出发。`net_median < 0` 可以提醒多数 entry 小负，但不能单独判死刑。真正的问题是：右尾能否运行时识别，左尾能否容量约束，执行后是否还有边。

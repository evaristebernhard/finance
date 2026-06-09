#import "../styles.typ": definition, proposition, evidence, remark

= 第 12 章：失败因子与反过拟合纪律

== 本章要解决的困惑

失败因子不是垃圾。一个失败因子可能说明“方向预测弱”，也可能说明“它只适合作为条件、控制变量或退出 guard”。本章把失败机制和反过拟合纪律讲清楚。

== 一个具体例子

静态 queue imbalance 看起来很自然：买盘比卖盘厚，价格是不是更容易涨？CCUSDT 结果显示，它作为 standalone direction alpha 很弱。但这不代表盘口信息无用。spread 影响执行，depth 影响释放，OFI/MLOFI 可能影响补单和吸收。

== 从例子推导数学对象

判断因子是否有效，不能只看：

$ E[R | X=1] $

还要看 matched control：

$ Delta_X(c) = E[R | X=1, C=c] - E[R | X=0, C=c] $

这里 $C$ 可以包含日期、价差、深度、cell、活动度等控制条件。否则一个因子可能只是碰巧出现在好日期或高波动状态。

== 正式定义

#definition("匹配控制", [
  匹配控制是在相近市场条件下比较有因子和无因子的差异。它用于区分因子本身的增量与背景状态的影响。
])

#definition("oracle 禁区", [
  oracle 是使用未来路径或事后最优选择得到的诊断上界。oracle 可以帮助发现可能机制，但不能直接变成 runtime 规则。
])

== CCUSDT 实证证据

#evidence("静态盘口弱", [
  `obi_1` 在 `fwd_time_60s_bps` 上 Spearman 约 0.0366、AUC 约 0.5094，说明静态盘口作为独立方向预测较弱。但 dynamic `trade_flow_imbalance` 对 event-time label 明显更强。
])

#evidence("residual pressure 不稳", [
  Residual pressure diagnostic 显示 residual pressure 单独不稳；exhaustion 更像 mid-continuation guard。低 exhaustion q1 在部分 OOS prior-bin fixed30 TTL=5 下为正，高 exhaustion q5 更差，但这仍需运行时安全验证。
])

== 失败机制

常见失败因子包括：

- 静态盘口：可撤单，不含未来主动流。
- 真空：释放条件，不是延续保证。
- residual pressure：容易和已经发生的路径、价差恢复混淆。
- q60/q65：可能提高 recall，但也可能是敏感性而非主线。
- oracle exit：知道未来最大点，不可运行时使用。

#remark("失败因子的合理归宿", [
  因子失败后有三种归宿：删除、降级为控制变量、转入 exit/execution diagnostic。不能因为 standalone alpha 弱，就把它从所有分析层删除。
])

== 策略/runtime 边界

任何新规则上线前必须回答：

```text
它是否只使用当时可见信息？
threshold 是否来自 prior-date？
是否和 matched controls 比较？
是否跨日稳定？
是否在 strict taker 后仍有收益？
是否只是 q60/q65 sensitivity？
```

== 本章小结

失败因子是研究纪律的一部分。它们告诉我们哪些解释不成立、哪些变量只能做条件、哪些结果可能是 oracle。真正危险的不是失败，而是不知道失败属于哪一层。


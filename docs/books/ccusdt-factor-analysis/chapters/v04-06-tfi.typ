#import "../styles.typ": definition, proposition, evidence, remark, factor

= 第 6 章：主动成交流不平衡 TFI

== 本章要解决的困惑

主动成交流不平衡（Trade Flow Imbalance, TFI）为什么是当前主线？因为它直接测量“谁在主动消耗流动性”。相比静态盘口，主动成交更接近价格冲击的分子。

== 一个具体例子

在最近 5 秒内发生了四笔成交：

```text
主动买入 100
主动买入 80
主动卖出 30
主动买入 50
```

如果把主动买入记为 +，主动卖出记为 -，那么原始 TFI 是：

$ 100 + 80 - 30 + 50 = 200 $

这个数不等于未来收益，但它说明最近主动流明显偏向买方。

== 从例子推导数学对象

令第 $j$ 笔成交方向为 $sigma_j$，主动买入为 +1，主动卖出为 -1；成交数量为 $q_j$。窗口 $W(t)$ 内的主动成交流不平衡为：

$ "TFI"_t = sum_(j in W(t)) sigma_j q_j $

如果用成交额而不是数量：

$ "NotionalTFI"_t = sum_(j in W(t)) sigma_j p_j q_j $

如果关心方向纯度：

$ "ShareTFI"_t = (sum sigma_j q_j) / (sum q_j + epsilon) $

如果想降低大成交量状态的尺度影响：

$ "ZTFI"_t = (sum sigma_j q_j) / sqrt(sum q_j^2 + epsilon) $

这些都是 TFI 家族，不是同一个因子。

== 正式定义

#definition("主动成交流不平衡", [
  主动成交流不平衡是在给定窗口内，对主动买入和主动卖出按方向加权后的净成交量或净成交额。它测量短期方向压力，而不是成交总活跃度。
])

#proposition("TFI 是冲击分子", [
  在局部价格冲击模型中，TFI 对应 signed aggressive flow，即推动价格的分子；对手方深度对应阻碍价格移动的分母。
])

== CCUSDT 实证证据

#evidence("动态流强于静态盘口", [
  CCUSDT LOB stylized factors 报告显示，动态 `trade_flow_imbalance` 对 `fwd_event_25_bps` 的 IC 约 0.2768，AUC 约 0.6217，top-bottom 约 2.8332 bps。静态 `obi_1` 在 `fwd_time_60s_bps` 上 Spearman 约 0.0366，AUC 约 0.5094。
])

== 失败机制

TFI 会失败，主要有四类原因。

第一，信号太晚。成交流确认时，价格可能已经释放完。

第二，被吸收。主动买入很强，但卖方不断补单，价格不继续上行。

第三，只释放不延续。短期 MFE 出现，但 60 秒后已经回吐。

第四，活动度混淆。高 TFI 可能只是高交易量状态，而不是更纯的方向压力。

#remark("TFI 不是一个按钮", [
  TFI 至少有窗口长度、成交单位、归一化方式、方向化方式和触发时钟五个选择。报告里只写 TFI 而不写口径，是不可复现的。
])

== 策略/runtime 边界

TFI 可以运行时安全，只要成交方向来自交易所可见字段或明确的在线推断规则。未来收益、未来 MFE、未来回吐不能用来修正当前 TFI。若 trade sign 需要推断，必须记录推断方法和误差。

== 因子卡片

#factor("主动成交流不平衡", [
  中文名：主动成交流不平衡。英文名：Trade Flow Imbalance，代码常写作 `trade_flow_imbalance` 或 `TFI`。它测量主动买卖流的净方向压力。它可能有效，是因为短周期价格变化首先来自 taker 对盘口的消耗。它会失败，是因为主动流可能已经释放、被吸收，或无法覆盖价差。
])

== 本章小结

TFI 的价值在于机制位置清楚：它不是万能 alpha，而是价格冲击的主动流分子。它必须和深度、价差、释放速度、退出时机一起使用。


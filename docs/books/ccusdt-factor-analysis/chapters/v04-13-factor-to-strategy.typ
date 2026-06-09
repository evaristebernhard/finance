#import "../styles.typ": definition, proposition, evidence, remark

= 第 13 章：从因子到策略

== 本章要解决的困惑

一个因子有效，不等于一个策略可用。策略还需要执行、容量、退出、日志和可复现回测。本章把因子证据、执行证据、容量证据和尾部证据分开。

== 一个具体例子

假设 TFI+R5+frames 预测中间价 60 秒后平均 +3 bps。但 taker 往返价差平均 1.3 bps，capacity clipping 剪掉一部分右尾，fixed60 退出又遇到 release/decay。最终策略收益可能远低于因子收益。

这不说明因子没用，也不说明策略可用。它说明必须分解：

```text
alpha: 中间价路径有没有边
execution: bid/ask 成交后还剩多少
exit: 释放后是否回吐
capacity: 3x 杠杆下实际能开多少
tail: 左尾是否被 sizing 放大
```

== 从例子推导数学对象

一次 entry 的实际结果可以拆成：

$ Y_i = A_i - C_i - D_i + K_i $

其中 $A_i$ 是中间价 alpha，$C_i$ 是执行成本，$D_i$ 是释放后衰减或不良退出，$K_i$ 是容量和 sizing 对组合结果的贡献。只看 $Y_i$ 无法识别哪一项出了问题。

容量约束可以写成：

$ sum_(i in "open"(t)) w_i <= 3 $

这说明高 gamma 不一定能实际开出来；重叠时会被 clipping。

== 正式定义

#definition("fast backtest", [
  fast backtest 使用 market-derived decision frame、Bot-owned state 和确定性近似执行，快速回答 edge、参数、容量和尾部问题。
])

#definition("strict replay", [
  strict replay 模拟交易所风格的数据流、Bot 下单、Runner 成交、portfolio 和 event log，用来验证实盘形态、时序、延迟和日志因果链。
])

#definition("profile manifest", [
  profile manifest 记录策略、容量、退出、成交、延迟和数据口径。不同 profile 的结果不能直接比较。
])

== CCUSDT 实证证据

#evidence("近期策略跑法", [
  当前 q70 core+idle01_g1、3x cap、entry-spread q70、taker top-of-book 的近期 2026-05-19..2026-05-30 fast run 显示 fixed60 taker net weighted bp-units 约 1204.7101，12/12 positive days；但这仍是 fast quote-frame taker-cross 路径，不等于 full sim-live 或真实账户结果。
])

== 失败机制

从因子到策略会失败，通常不是单点错误，而是边界没分清。

- 用未来 label 做入场：研究有效，实盘失效。
- 用 mid return 估收益：忽略价差。
- 用全局缩放处理容量：误删 idle sleeve。
- 用固定 60 秒标签判断 entry：混淆 release 和 decay。
- 混比不同 profile：把执行差异当策略差异。

#proposition("总收益不可直接解释因子机制", [
  若只观察策略总收益 $Y_i$，不能判断 entry alpha $A_i$ 是否为正。执行成本、退出衰减和容量约束都可能改变最终结果。
])

== 策略/runtime 边界

可进入运行时的只有公开市场流和私有成交回报生成的在线状态。研究报告、未来路径、MFE/MAE、scored entries、oracle exit、最终 PnL 都必须留在离线验收层。Monitor 只能只读 run artifacts，不参与交易热路径。

== 本章小结

因子到策略的转换不是“找到 alpha 就下单”。它是四层验证：因子是否解释路径，执行后是否还剩 edge，容量是否能承载，尾部是否可控。当前 CCUSDT 工作最有价值的部分，正是把这些层分开了。

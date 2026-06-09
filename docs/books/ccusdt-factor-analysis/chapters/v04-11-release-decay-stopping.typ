#import "../styles.typ": definition, proposition, evidence, remark

= 第 11 章：释放、衰减与停时问题

== 本章要解决的困惑

60 秒收益为什么会误导因子分析？因为它把 entry 是否有效和 exit 是否合理混在一起。一笔 entry 可能在 5 秒内释放 12 bps，但 60 秒后回吐成负数。说它是坏 entry，就错过了真正问题：退出和 sizing。

== 一个具体例子：1615412

 canonical case `1615412` 属于 `11_r5_frames / short`。它在 4.7051 秒内达到 MFE +12.5612 bps，但 60 秒结果是 R60 -27.8923 bps。在高 exposure 下，目标 PnL 约 -242.4187。

这不是“entry 没有 edge”的简单证据。更准确的分解是：

```text
entry impulse: 有，早期释放明显
fixed60 hold value: 差，释放后回吐
sizing: 过重，左尾被放大
exit model: 没有识别 release 已经结束
```

== 从例子推导数学对象

给定 entry time $t_i$ 和方向 $d_i$，路径收益为：

$ R_i(u) = d_i 10000 log(m_(t_i+u) / m_(t_i)) $

最大有利波动：

$ "MFE"_i(T) = max_(0 <= u <= T) R_i(u) $

最终收益：

$ R_i(T) $

回吐：

$ "Decay"_i(T) = "MFE"_i(T) - R_i(T) $

如果 MFE 很高但 R(T) 很低，问题不一定在 entry，而可能在 stopping time。

停时 $tau$ 是根据已经观察到的路径决定退出的时间：

$ tau = inf { u : "exit condition holds using information up to" t_i+u } $

停时不能看未来最大值，否则就是 oracle。

== 正式定义

#definition("释放", [
  释放是 entry 后价格快速沿信号方向移动。它反映 entry impulse 和盘口条件。
])

#definition("衰减", [
  衰减是释放后的收益回吐。它反映主动流停止、反向流出现、补单吸收或价格均值回归。
])

#definition("停时", [
  停时是只依赖当前及过去信息的退出时间。未来最大值、未来最终收益和 oracle 最优退出都不是运行时停时。
])

== CCUSDT 实证证据

#evidence("release/decay 事实", [
  Release/decay 报告中，1455 rebuilt entries 的 mean MFE5 约 2.5668、MFE10 约 3.6668、MFE60 约 9.9293、R60 约 4.2577、decay60 约 5.6716。说明很多 entry 有释放，但一部分收益被后续回吐。
])

#evidence("小路径管理器", [
  `pm_11_drawdown_h4_peakguard` 从 fixed60 total 8904.7590 提升到 9554.1874，delta +649.4284，action exit rate 2.82%。它救了 `1615412`、`2377379`、`2361187`，但也误伤 `2583437`。
])

== 失败机制

退出模型有两类错误。

第一，太晚。释放已经结束，价格开始回落，但策略仍然等到固定 60 秒。

第二，太早。早期回撤只是 reset，后面还有更大的多脉冲延续，例如 `2583437`。

所以不能简单说“30 秒更好”或“60 秒更好”。不同样本上 fixed30/fixed45/fixed60 的表现会变化。真正的问题是如何用当前路径判断释放是否衰竭。

#remark("60 秒标签只是投影", [
  60 秒收益是路径在一个固定时间点的投影。它方便比较，但会混淆 entry edge、release speed、decay 和 exit timing。
])

== 策略/runtime 边界

运行时 exit controller 可以使用 entry 后已经发生的路径：当前 MFE、从高点回撤、同向/反向成交流、价差状态、剩余持仓时间。不能使用未来最大值或未来最终收益。oracle exit 只能作为上界诊断。

== 本章小结

release/decay 是当前 CCUSDT 策略最核心的困难之一。很多坏结果不是没有释放，而是释放后没有及时管理。停时模型必须小而硬，避免把 oracle 诊断误装进 runtime。

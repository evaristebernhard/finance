#import "../styles.typ": definition, proposition, evidence, remark

= 第 5 章：从事件流到因子

== 本章要解决的困惑

因子不是从表格里凭空出现的。交易所先产生事件，程序按时间顺序接收事件，维护在线状态，再从状态里计算因子。本章解释 quote、trade、L2 update 如何变成运行时可用的特征。

== 一个具体例子

假设程序连续收到三类事件：

```text
quote: bid/ask 更新
trade: 一笔成交发生
L2 update: 某个价位的挂单数量变化
```

收到 quote 后，程序可以更新 mid、spread、frames_since_mid_change。收到 trade 后，程序可以更新主动成交流不平衡。收到 L2 update 后，程序可以更新多档深度、补单和撤单。

== 从例子推导数学对象

时间 $t$ 之前程序已经看到的信息，记为 $cal(F)_t$。如果一个因子只依赖这些信息，就可以在线计算：

$ X_t = f(cal(F)_t) $

如果一个变量需要 $t$ 之后的价格路径，例如未来 60 秒收益，则它不是运行时因子：

$ Y_t = g(m_(t+u), 0 < u <= 60s) $

这里 $X_t$ 是特征，$Y_t$ 是标签。把二者混在一起，就是未来信息泄漏。

== 正式定义

#definition("公开市场流", [
  公开市场流是策略在实盘中可以收到的行情事件，包括 quote、trade 和可选 L2 update。
])

#definition("在线状态", [
  在线状态是程序从公开市场流递推维护的状态，例如最近成交窗口、当前盘口、过去若干帧 mid 是否变化、当前深度摘要。
])

#definition("运行时安全", [
  运行时安全表示变量在下单时刻可由 $cal(F)_t$ 计算，不依赖未来收益、未来路径、事后标签或研究面板中的 oracle 字段。
])

== CCUSDT 实证证据

#evidence("Runner/Bot 边界", [
  当前 replay exchange 设计中，Runner 只负责市场真相、时钟、成交、组合和事件日志；Bot 自己从 public/private stream 维护在线特征。旧 `date/`、scored entries、MFE/MAE/PnL 只能作为离线验收标签，不能进入运行时输入。
])

== 失败机制

从 panel 翻译到 online 时，最容易产生新策略族。原因有三个。

第一，触发时钟不同。旧研究可能只在 decision frame 上评估，而在线 bot 如果每个 trade event 都触发，entry 数量会改变。

第二，状态更新时间不同。R5 只能在历史 entry 关闭后更新，不能因为 market stream 推进就把尚未结束的 entry 加进去。

第三，字段口径不同。旧 fixed panel 的某些字段可能是离线聚合结果，在线重建必须证明 timestamp 和字段一致。

#proposition("触发时钟是策略定义的一部分", [
  若两个系统使用相同公式但在不同事件集合上评估，则它们不是同一个策略。decision clock、first-per-bucket 规则和状态更新时间必须同时复现。
])

== 策略/runtime 边界

本书后续提到的因子，都会标记它来自哪类事件。若一个因子需要 L2，但当前实盘只稳定接入 quote/trade，则该因子不能直接进入第一版策略。若一个因子依赖未来路径，则永远不能进入运行时，只能做诊断。

== 本章小结

因子的合法性来自信息边界。市场事件形成可见信息集；在线状态是对信息集的递推压缩；运行时因子必须是在线状态的函数。这个边界比任何单个公式都重要。


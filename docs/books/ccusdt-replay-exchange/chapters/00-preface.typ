= 序章：为什么要写这本书

这本书不是为了把所有 CCUSDT 报告重新排版一遍。报告已经很多，真正缺的是一条能让未来自己和新的 Codex 迅速进入状态的解释路径：为什么一开始是因子，为什么后来变成路径问题，为什么又必须搭一个本地 replay exchange，为什么停时和杠杆不是策略之后的附属细节，而是 edge 能否被实际捕获的一部分。

本书的中心对象是一个很小但完整的研究系统：

```text
raw market truth
  -> canonical datasets
  -> decision frame / online features
  -> fast strategy backtest
  -> sim-live replay runner
  -> event log / attribution / monitor
```

这里的「研究」不是在静态表格里寻找一个漂亮的均值，而是反复回答同一个问题：

$ 
  "策略在当时能看到什么？"
  -> "它为什么会下单？"
  -> "订单按什么价格成交？"
  -> "风险和杠杆如何限制它？"
  -> "最终利润来自哪里？"
$

这个问题链条的每一环都可能制造假象。一个 60 秒 label 可能把 5 秒内完成的 release 写成亏损；一个看似有利润的 mid-price 回测，可能在 taker crossing 之后被 spread 吃掉；一个全局缩放的杠杆模型，可能错杀本来可以用 idle capacity 承接的 `01_frames_only`；一个 oracle exit 可能只是未来信息包装成了规则。

因此本书采用三条并行主线。

第一条是数学主线。它从路径收益、成本、停时、容量、风险预算出发，尽量把每个经验现象还原成可检验的数学对象。

第二条是工程主线。它解释为什么要有 canonical market truth、Runner/Bot 三进程边界、event log、profile manifest，以及为什么 Monitor 只能读结果，不能干预交易路径。

第三条是研究纪律。它记录哪些结论是证据，哪些只是候选解释；哪些规则是 runtime-safe，哪些只是离线 label；哪些数字是当前工作区已经跑出的结果，哪些还需要下一轮 out-of-sample。

本书不是最终答案。它是一个研究操作系统的说明书。


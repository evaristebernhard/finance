= 第 0 章：为什么这套代码难读

== 本章要解决的代码困惑

`systems/ccusdt_replay_exchange` 不是一个单一脚本。它同时包含本地交易所 Runner、Python 策略 Bot、快速回测、严格回放、诊断脚本、缓存构建器、运行日志和少量 Monitor。读者一进来容易把三件事混在一起：

- 研究诊断：为了判断一个因子或策略是否合理。
- 运行时路径：模拟实盘时真正能看到和能做的事。
- 输出证据：一次 run 结束后用来审计的 summary、events、entries、exits。

这本书不要求你马上懂 Rust。你只需要先懂一条主线：市场数据先变成可复现的数据层，fast backtest 用它快速研究策略，strict replay 用 Runner/Bot 验证实盘形态，event log 负责解释每笔订单为什么发生。

== 先看哪些文件

先看这几个入口，不要从全部文件开始：

```text
systems/ccusdt_replay_exchange/README.md
systems/ccusdt_replay_exchange/diagnostics/README.md
systems/ccusdt_replay_exchange/diagnostics/fast_strategy_backtest.py
systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/strategy.py
systems/ccusdt_replay_exchange/engine/crates/cli/src/main.rs
systems/ccusdt_replay_exchange/engine/crates/runner/src/lib.rs
```

== 这个模块在系统中负责什么

工程系统的目标是模拟一个本地交易所，而不是只跑一个收益 CSV。Runner 拥有市场真相、时钟、订单到达、成交、组合和日志。Bot 只像实盘程序一样接收行情、维护特征、发出下单意图。Diagnostics 可以读取更多产物，但它们不能反过来成为运行时输入。

== 输入是什么

输入分三层：

```text
raw venue files        原始交易所数据
canonical/cache        系统生成的市场真相与热路径缓存
Bot-owned state        策略自己连续维护的 R5/lifecycle 状态
```

== 输出是什么

输出也分三层：

```text
summary.json           一次 run 的总结果
events.ndjson          订单/成交/组合的因果链
daily.csv              日度汇总
entries/exits.parquet  fast backtest 的逐笔结果
```

== 它绝不能做什么

Runner 不能读取研究 label。Bot 不能读取 `date/`、scored entries、未来 PnL、MFE、MAE。Diagnostics 不能变成 runtime input。只要这三条边界被打破，回测就会变成带未来信息的研究幻觉。

== 一个最小读代码路径

第一遍读代码可以按这个顺序：

```text
fast_strategy_backtest.py
-> shadow_policy.py
-> execution_runtime.py
-> decision_frame_cache.py
-> strategy.py
-> cli/main.rs
-> runner/lib.rs
-> audit_event_log.py
```

先读 fast，是因为它最接近策略研究者的脑子；再读 Bot，是因为它把 fast 逻辑翻译成运行时；最后读 Runner，是因为 Runner 文件很大，必须带着问题进去。

== 常见误解

最常见误解是以为 `diagnostics/` 都是“边角料”。其实 fast backtest 和 cache builder 都在 diagnostics 下，但它们是研究热路径；真正的区别不是目录名，而是是否进入运行时交易路径。


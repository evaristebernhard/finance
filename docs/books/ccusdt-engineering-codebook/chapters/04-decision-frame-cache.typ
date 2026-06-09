= 第 4 章：decision_frame cache 是什么

== 本章要解决的代码困惑

为什么不直接在每次 backtest 里扫 raw L2？因为太慢。`decision_frame_cache.py` 把 quote/trade/L2 的在线重建结果持久化成 typed Parquet，让日常策略实验从分钟级或更慢变成秒级到几十秒级。

== 先看哪些文件

```text
systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py
systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/decision_frame.py
```

== 这个模块在系统中负责什么

它负责构建 `decision_frame_v1`。decision frame 是旧 fixed panel 的运行时安全替代物：只由 market-visible event stream 重建，不含未来收益和研究标签。

== 输入是什么

输入可以是 raw 或 canonical。重要参数：

```text
build / validate / parity / export-ndjson
--input-layer raw|canonical|cache
--from-date / --to-date
--batch-size
--force
--cleanup-tmp
```

== 输出是什么

每个日期输出：

```text
part_000001.parquet
manifest.json
```

manifest 记录 schema version、builder version、source manifest、row count、cache hash、field hash。读代码时重点看 `build_one`、`write_batch`、`validate_one`。

== 它绝不能做什么

它不能把 old fixed panel、future labels、MFE/MAE、PnL、path class 写进 cache。cache 是热路径数据层，不是研究标签层。

== 一个最小读代码路径

```text
main
-> build_one
-> frame_iter
-> iter_raw_decision_frames
-> DecisionFrameBuilder
-> write_batch
-> manifest write
```

验证路径：

```text
validate_one
parity_one
iter_cached_decision_frames
```

== 常见误解

`decision_frame_v1` 不是“为了偷懒预先算好策略结果”。它只是把运行时可见的决策帧持久化。策略仍然要自己计算 entry、capacity、exit 和 PnL。


= 第 11 章：常用实验路线

== 本章要解决的代码困惑

很多时候不是代码看不懂，而是不知道该先跑哪条链。这里给三条最小路线。

== 路线一：数据准备

```text
canonical build/validate
-> decision_frame_cache build/validate
-> shadow_state build
```

目的：证明市场数据和运行时安全 decision frame 已经准备好。

最小命令看附录，不要把长 runbook 背下来。关键是知道每一步生成什么。

== 路线二：快速策略

```text
fast_strategy_backtest.py
-> summary.json
-> daily.csv
-> entries.parquet / exits.parquet
```

目的：快速回答这组 profile 在某些日期上有没有边、容量是否被打满、哪天最差、左尾多大。

== 路线三：严格验收

```text
Runner/Bot strict
-> events.ndjson
-> audit_event_log.py
-> fast_vs_strict_consistency.py
```

目的：证明 fast 里的策略决策能在 exchange-style stream 下复现，并把 PnL 差异拆成执行、延迟、深度、压力。

== 一个最小读代码路径

若目标是理解一次新策略实验：

```text
1. 读 profile_manifest.json
2. 读 config.json
3. 读 summary.json
4. 看 daily.csv
5. 抽 entries.parquet 中几笔典型 entry
6. 若 strict run 存在，再读 events.ndjson 的 causal chain
```

== 常见误解

不要一上来就跑 full strict。先用 fast 判断策略是否值得看，再用 strict 验证实盘形态。full strict 是真实性 gate，不是参数扫描工具。


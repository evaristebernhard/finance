= 第 12 章：不要改错地方

== 本章要解决的代码困惑

工程系统最怕“为了方便”破坏边界。很多 bug 不是语法错，而是某个模块拿到了不该拿的信息。

== 先看哪些文件

```text
systems/ccusdt_replay_exchange/AGENTS.md
systems/ccusdt_replay_exchange/README.md
systems/ccusdt_replay_exchange/docs/event_contracts.md
systems/ccusdt_replay_exchange/docs/next-stage-three-process-design.md
```

== 不要让 Runner 读 label

Runner 是本地交易所。它可以读 canonical market truth，可以维护 portfolio，可以成交。它不能知道未来收益、MFE、MAE、path class。

== 不要让 Bot 读 date/

Bot 是实盘策略客户端。它只能读 public/private stream 和自己的 persisted state。旧 `date/` 是研究输出，不是运行时输入。

== 不要把 diagnostics 变成 runtime

Diagnostics 可以做 oracle 分析、casebook、decomposition、matched controls。但它们的结果不能直接进入 Bot。若一个诊断发现了有用条件，必须重新表达成运行时可见的 online feature。

== 不要混比不同 profile

每次 run 都必须记录：

```text
policy_profile
capacity_profile
exit_profile
fill_profile
latency_profile
transport_profile
data/cache manifest
```

不同 profile 的 PnL 不能直接比较。

== 不要绕过 state boundary guard

Bot-owned state 有日期连续性。若 `state_after_dt=2026-05-18.json` 的 `next_expected_date` 是 2026-05-19，它只能接 5/19，不能随便拿去跑 5/21。

== 常见误解

“只是为了跑快一点”不是破坏边界的理由。正确的工程优化是 Parquet cache、batched transport、panel sparse clock；错误的优化是让策略直接读未来结果。


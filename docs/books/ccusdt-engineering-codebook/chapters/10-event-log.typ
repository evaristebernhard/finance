= 第 10 章：event log 怎么读

== 本章要解决的代码困惑

`events.ndjson` 看起来像一堆 JSON 行，但它是 strict replay 最重要的证据。每一笔订单应该能从 intent 一路追到 fill 和 portfolio change。

== 先看哪些文件

```text
engine/crates/runner/src/lib.rs
diagnostics/audit_event_log.py
systems/ccusdt_replay_exchange/runs/<run_id>/events.ndjson
systems/ccusdt_replay_exchange/runs/<run_id>/summary.json
```

== 这个模块在系统中负责什么

event log 负责审计，不负责策略。它回答：

```text
订单为什么出现？
什么时候到达？
到达时盘口是什么？
成交价是什么？
组合怎么变？
重复运行是否一致？
```

== 输入是什么

`audit_event_log.py` 输入一个 run directory。

== 输出是什么

它输出 causal-chain validator 的结果，包括订单链是否完整、ack/fill 是否匹配、portfolio 是否变化、hash 是否可复现。

== 它绝不能做什么

event log 不应该反过来影响当次交易。Monitor 也只能只读 event log 或 state endpoint，不进入热路径。

== 一个最小读代码路径

Runner 里先看：

```text
EventLogger
logger.emit(...)
order_arrived
portfolio_state_on_change
summary write
```

Audit 里看：

```text
load_events
group by order/intent/position
validate causal chain
compute counts/mismatches
```

== 常见误解

compact log 没记录每帧 hold，不是信息缺失。hold 不是交易因果链的一部分。真正需要永久记录的是 intent、scheduled、arrival、ack/reject、fill、portfolio、summary。


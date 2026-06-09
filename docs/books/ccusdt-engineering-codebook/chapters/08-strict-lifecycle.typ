= 第 8 章：一次 strict replay 的生命周期

== 本章要解决的代码困惑

strict replay 不是“跑一遍回测”这么简单。它要保证每个订单都有可复盘因果链：Bot 在什么行情下观察到信号，Runner 什么时候让订单到达，在哪个盘口成交，组合如何变化。

== 先看哪些文件

```text
engine/crates/runner/src/lib.rs
strategies/python/ccusdt_tfi_core_idle01/strategy.py
diagnostics/audit_event_log.py
```

== event log causal chain

```text
market_quote / market_trade / decision_frame
  -> Bot feature update
  -> order_intent
  -> order_scheduled
  -> order_arrived
  -> order_ack or order_reject
  -> fill
  -> portfolio_state_on_change
  -> summary
```

== 这个模块在系统中负责什么

strict replay 验证实盘形态。fast 可以说“这个 entry 应该触发”，strict 要证明 Bot 在交易所式事件流下也会同一时间触发，并且 Runner 会生成一致的订单、成交和组合状态。

== 输入是什么

典型 strict 输入包括：

```text
canonical-date
public-stream-mode
latency-us
clock-mode
fill-model
strategy-arg
```

== 输出是什么

输出是 compact event log 和 summary。compact 的意思是：不记录每个 hold，只记录对交易因果链有意义的事件。

== 它绝不能做什么

deterministic replay 下，wall/bridge timing 不能影响 arrival quote、fill price、portfolio 或 PnL。wall latency 只能进入 pressure profile。

== 一个最小读代码路径

在 Runner 中跳读这些段：

```text
observations queue
Bot drain outcome
arrival observation lookup
order_arrived emit
fill creation
portfolio_state_on_change emit
summary hash/timing
```

== 常见误解

strict 不一定要比 fast 慢很多。`batched_public_barrier_v1` 和 `panel_sparse_fast_clock_v1` 都是为了减少 stdio/JSON 开销；但 full strict_event 仍是真实性 gate，不应被删除。


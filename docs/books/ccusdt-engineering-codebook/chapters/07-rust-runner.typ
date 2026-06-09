= 第 7 章：Rust Runner 是本地交易所

== 本章要解决的代码困惑

`runner/src/lib.rs` 很大，不能逐行读。正确读法是把它当作本地交易所：它拥有时钟、市场流、订单入口、延迟、成交、组合和日志。

== 先看哪些文件

```text
engine/crates/cli/src/main.rs
engine/crates/runner/src/lib.rs
engine/crates/exchange_sim/src/lib.rs
engine/crates/portfolio/src/lib.rs
```

== 这个模块在系统中负责什么

Rust Runner 的职责：

```text
读取 canonical/cache 市场事件
按 replay clock 推送 public stream
接收 Bot order intent
计算 deterministic arrival
按 fill model 成交
更新 portfolio
写 compact event log
```

== CLI command tree

`cli/main.rs` 用 `clap` 定义命令。先看：

```text
Command
CatalogCommand
CanonicalCommand
RunCommand
RunSparsePythonArgs
PublicStreamModeArg
run_sparse_python_command
```

Rust 里 `struct Args` 是命令行参数结构，`enum Command` 是子命令分发。你不需要先学完整 Rust，只要知道 CLI 最终会组装 options，然后调用 runner 函数。

== Runner 责任区域

在 `runner/lib.rs` 中按这些关键词跳读：

```text
SparsePythonStreamOptions
SparsePublicStreamMode
run_sparse_python_stream_strategy
run_panel_sparse_fast_clock_python_stream_strategy
run_runner_server
EventLogger
order_arrived
portfolio_state_on_change
SparseCounters
SparseTiming
```

== 输入是什么

Runner 输入包括 canonical market stream、decision frame cache、Bot process/socket、strategy args、latency profile、fill profile、run_id。

== 输出是什么

Runner 输出 run directory：

```text
manifest.json
events.ndjson
summary.json
```

== 它绝不能做什么

Runner 不应该读取研究 label，也不应该决定策略因子。Runner 只模拟交易所和账户。策略逻辑属于 Bot；研究诊断属于 diagnostics。

== 一个最小读代码路径

```text
cli/main.rs RunCommand::SparsePython
-> run_sparse_python_command
-> SparsePythonStreamOptions
-> run_panel_sparse_fast_clock_python_stream_strategy
-> run_sparse_python_stream_strategy_with_events
-> Bot drain / order processing / fill / EventLogger
```

== 常见误解

Runner 的 `panel_sparse_fast_clock_v1` 不是偷偷用未来信息。它只是用已经验证的 decision_frame cache 驱动 decision clock，并用 quote_frame last-known quote 计算 deterministic arrival/fill。full-stream strict gate 仍用于真实性验证。


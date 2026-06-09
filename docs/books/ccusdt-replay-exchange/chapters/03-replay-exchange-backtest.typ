= 本地 Replay Exchange 与双轨回测

== 问题

普通回测经常把策略写成：

```text
读一张表 -> 产生 signal -> 直接算收益
```

这对 bar 级别策略也许足够，但对 CCUSDT 的 L2 微观结构策略远远不够。我们关心的是：

```text
策略当时看到了什么？
什么时候发单？
订单什么时候到？
按哪个盘口成交？
仓位如何变化？
容量如何限制？
PnL 由哪些部分组成？
```

因此需要一个本地 replay exchange，而不是单纯的 dataframe backtest。

== 七层系统

当前系统边界可以写成：

```text
old raw/research files
  -> catalog
  -> canonical store
  -> replay clock
  -> book/state builder
  -> strategy bridge
  -> exchange simulator
  -> portfolio/risk/event log
```

这七层的关键原则是分权。

Runner 拥有 clock、market truth、latency、fill、portfolio 和 event log。Strategy Bot 只接收 exchange-visible events，并输出 submit/cancel/heartbeat。Monitor 只读 run artifacts，不参与交易热路径。

这个边界的数学意义是防止 filtration 污染。策略只能基于 $F_t$ 下单；Runner 才能在 $t_("arrival")$ 上决定成交。

== 双轨回测

系统实际有两条线。

第一条是 fast strategy backtest：

```text
decision_frame Parquet cache
  + Bot-owned state
  + capacity allocator
  + exit profile
  -> entries / exits / PnL / daily / tail / capacity
```

它回答：

```text
edge 是否存在？
参数是否敏感？
哪天亏？
哪个 cell 贡献？
容量是否挤压？
```

第二条是 sim-live replay backtest：

```text
canonical market stream
  + Runner virtual clock
  + Python Bot bridge
  + order/fill/portfolio
  + compact event log
```

它回答：

```text
策略像实盘 bot 一样运行时是否一致？
order causal chain 是否完整？
taker spread cost 有多大？
latency/fill/profile 是否改变 PnL？
fast 线和 strict 线差在哪里？
```

两条线不应该互相替代。fast 线用于研究速度，strict 线用于真实性验收。

== Profile Manifest

每一次 run 都必须明确 profile，否则不同实验会被误比较。至少需要：

```text
policy_profile
capacity_profile
exit_profile
fill_profile
latency_profile
transport_profile
data/cache manifest
```

例如 `fixed60_mid` 和 `fixed60_taker` 不是同一个退出模型；`deterministic_replay_v1` 和 `wall_latency_pressure_v1` 不是同一个延迟模型；`top_of_book_taker_ioc_v1` 和 `l2_taker_depth_v1` 也不是同一个成交模型。

没有 profile manifest，PnL 数字只是孤立数字；有了 profile manifest，PnL 才能被归因。

== 容量和 lot lifecycle

杠杆约束不是最后乘一个缩放系数。对 3x cap 来说，真正的约束是：

$
sum_j w_j(t) <= 3.
$

因此 capacity allocator 必须在 entry 前决定：

```text
requested_exposure
actual_exposure
clipped_exposure
skipped
open_exposure_before/after
capacity_source
```

一旦 entry fill 发生，就必须生成 position lot。exit 不能凭 shadow row 直接扣收益，而要对 lot 的 remaining quantity 反向平仓。

这就是为什么 Runner 推进比 Monitor 更优先：如果 lot lifecycle 不稳，Monitor 只会把不稳的东西画得更漂亮。

== Event Log

event log 是本地交易所的事实账本。最小因果链是：

```text
order_intent
capacity_decision
order_scheduled
order_arrived
order_ack / order_reject
fill
position_opened / position_closed
portfolio_state
```

compact log 不需要记录每帧 hold，但必须能复盘每笔订单的 observed state、arrival state、fill price、latency、slippage、capacity decision 和 portfolio change。

== 当前状态

目前 Runner 已经够做可信策略实验内核：

```text
canonical replay
deterministic clock
Python Bot bridge
top-of-book taker IOC
capacity/profile/lot baseline
fast vs strict comparison
panel_sparse_fast_clock hot path
repeat hash gate
```

但它还不是完整真实交易所模拟器：

```text
L2 depth fill 不是默认主路径
maker queue 生命周期暂缓
真实网络/API 延迟未校准
市场冲击和盘口反馈未建模
Monitor 仍未完成
```

== 未解决问题

后续 Runner 工作应优先服务研究问题，而不是追求全交易所仿真：

```text
把 ExitController 接入 strict order lifecycle
统一 experiment runner 输出 schema
自动生成 fast-vs-strict PnL decomposition
将 L2 depth fill 作为可选 fill_profile
为 Monitor 提供稳定只读 artifacts
```

这条路径比直接做 rich Monitor 更重要，因为 Monitor 的价值来自 Runner 产生的事实质量。

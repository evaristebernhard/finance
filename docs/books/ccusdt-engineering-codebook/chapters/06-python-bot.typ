= 第 6 章：Python Bot 的内部结构

== 本章要解决的代码困惑

Python Bot 不是一个单独函数，而是一组小模块拼起来的运行时策略。你要分清：谁维护特征，谁构造 decision frame，谁决定四象限，谁做容量，谁把 shadow signal 变成订单。

== 先看哪些文件

```text
online_features.py
decision_frame.py
shadow_policy.py
execution_runtime.py
strategy.py
tcp_bot.py
```

== 这个模块在系统中负责什么

Python Bot 像实盘 bot：接收 `market_quote`、`market_trade`、`market_l2_update`、`account_snapshot`、`order_ack`、`order_reject`、`fill`，输出 `heartbeat`、`submit_order`、`cancel_order`。

== Python Bot 流程图

```text
public/private event
  -> OnlineFeatureState
  -> DecisionFrameBuilder
  -> ShadowFourCellPolicy
  -> AdmissionGate
  -> CapacityAllocator
  -> submit_order / submit_orders / heartbeat
```

== 输入是什么

`strategy.py` 从 stdin 读取 NDJSON。`tcp_bot.py` 从 Runner Server 的 public/private/order ports 通信。两者复用相同的在线特征和策略模块。

== 输出是什么

Bot 输出 order intent，不直接成交。成交由 Runner 决定。Bot 输出的订单会携带 shadow_signal、feature_snapshot、capacity_decision 等诊断信息，方便 strict 与 fast 对齐。

== 它绝不能做什么

Bot 不能读 `date/`，不能读 scored entries，不能读 future labels、PnL、MFE、MAE。Bot 的 feature_snapshot 只能是运行时安全状态。

== 一个最小读代码路径

先读 `strategy.py`：

```text
parse_args
maybe_decide
maybe_shadow_entry_order
maybe_shadow_exit_orders
main
```

再读 `shadow_policy.py`：

```text
ShadowFourCellPolicy.on_decision_frame
_active_trigger_directions_from_values
_cell
_close_matured_at_mid
export_state/load_state
```

最后读 `execution_runtime.py`：

```text
EntrySpreadAdmissionGate
CapacityLedger
CoreIdle01CapacityAllocator
PositionLotLedger
build_profile_manifest
```

== 常见误解

`hold` 是旧 dense 模式兼容输出。稀疏/服务器模式不应该每个 market event 都输出 hold；Bot 应该只在 entry、exit、cancel 或 heartbeat checkpoint 时输出。


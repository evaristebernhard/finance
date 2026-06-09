# CCUSDT TFI Core Idle01 Strategy

Online strategy for the local replay exchange.

Entrypoints:

```text
strategy.py   stdin/stdout NDJSON bot for deterministic sparse-runner smoke
tcp_bot.py    independent TCP bot for Runner Server public/private/order ports
decision_frame.py  runtime-safe fixed-panel-equivalent L2 decision clock builder
online_features.py  runtime-safe feature state shared by both bot entrypoints
```

Runtime input is limited to exchange-style events:

```text
market_quote
market_trade
market_l2_update
account_snapshot
order_ack
order_reject
fill
```

Runtime output is limited to:

```text
heartbeat
submit_order
cancel_order
```

`hold` is accepted by older dense compatibility modes, but sparse/server mode
should not emit per-event holds.

The current skeleton computes rolling TFI and rolling trade imbalance from the
trade stream, quote-derived spread/mid-change/frames-since-mid-change state,
optional L2 counters, and a pretrade-safe closed-outcome R5 shape that can only
update from completed private fills. It sends at most one taker market IOC order
by default.

For old four-cell shadow translation, run `strategy.py` with:

```text
--decision-clock panel --shadow-four-cell
```

Panel mode evaluates only when `decision_frame_v1` is produced from
`market_l2_update` plus already observed trades. It should not trigger directly
on every quote or trade event.

For sim-live entry-fill diagnostics, add:

```text
--shadow-trade-entries --shadow-entry-notional 1.0
```

This turns nonzero-exposure shadow entries into taker market IOC entry orders
while preserving the `shadow_signal` in the order intent.

For sim-live round-trip diagnostics, also add:

```text
--shadow-trade-exits
```

This turns fixed60 shadow lifecycle closes into taker market IOC exit orders.
If several shadow positions close on the same decision frame, the Bot emits a
`submit_orders` batch so the Runner can preserve one causal chain per order.
The current capacity allocator still lives in the fast research runner; this
Bot path trades the shadow target notional to validate exchange-style stream,
order, fill, and private-event causality.

When it emits `submit_order` or sparse checkpoint `heartbeat`, it includes:

```text
feature_snapshot.schema_id = ccusdt_online_feature_snapshot_v1
```

The snapshot is diagnostic/runtime-safe state only. It must not import
root-level research scripts and must not read `date/` scored entries, path
labels, PnL, MFE, or MAE.

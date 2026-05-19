# Event Contracts

Status: MVP contracts.

## Market Truth

`quote_frame_v1` is the replay clock base for the MVP:

```text
seq,exchange_ts_us,local_ts_us,bid_px,bid_qty,ask_px,ask_qty,mid_px,spread_bps
```

`trade_event_v1` is the canonical trade stream:

```text
seq,trade_id,exchange_ts_us,local_ts_us,side,price,qty,notional_quote
```

`l2_level_update_v1` is the canonical L2 update stream:

```text
seq,exchange_ts_us,local_ts_us,is_snapshot,side,price,qty
```

## Feature Sidecars

`feature_sidecar_v1` may join pretrade-safe values to canonical market time. It
must not include realized future return, post-entry path labels, or strategy PnL.

Future/post-trade outputs belong to `research_label_v1` and are excluded from
strategy runtime by default.

## Exchange Events

`order_event_v1` records accepted/rejected/canceled orders.

`fill_event_v1` records simulated fills.

`portfolio_state_v1` records account, position, equity, and leverage snapshots.

## Run Event Log

Runner output is append-only NDJSON:

```text
runs/<run_id>/events.ndjson
```

Each row uses this envelope:

```text
event_id,run_id,event_type,replay_seq,replay_ts,wall_ts_ms,source,payload
```

The toy runner emits `run_start`, `market_frame`, `portfolio_state`,
`strategy_decision`, `order_intent`, `order_scheduled`, `order_submitted`,
`order_accepted` or `order_rejected`, `fill_created`, `clock_advanced`, and
`run_end`.

The exchange-style Python runner uses this strategy message envelope over
stdin/stdout NDJSON:

```json
{
  "type": "market_quote",
  "channel": "public",
  "run_id": "...",
  "replay_seq": 123,
  "observed_seq": 123,
  "cursor": 123,
  "exchange_ts_us": 1779062476207000,
  "local_ts_us": 1779062476433743,
  "payload": {}
}
```

Runtime inputs allowed for Python:

```text
session_start
market_quote
market_trade
market_l2_update
account_snapshot
order_ack
order_reject
fill
session_end
```

Runtime outputs allowed from Python:

```text
heartbeat
hold
submit_order
cancel_order
```

`submit_order` is taker-first in stream v1: `kind=market`, `tif=ioc`, `qty>0`.
The runner schedules it by `latency_us` and only then submits to the exchange.
Private order/fill events include observed quote, arrival quote, fill price,
arrival spread, base latency, effective latency, optional wall-latency virtual
staleness, and latency slippage. Future labels, scored entries, PnL, MFE, and
MAE must not be runtime inputs.

The important separation is:

```text
strategy intent != exchange order != fill
```

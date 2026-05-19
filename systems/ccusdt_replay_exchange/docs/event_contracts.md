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


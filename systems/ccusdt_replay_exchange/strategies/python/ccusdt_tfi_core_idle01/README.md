# CCUSDT TFI Core Idle01 Strategy

Online stdin/stdout NDJSON strategy for the local replay exchange.

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
hold
submit_order
cancel_order
```

The current skeleton computes rolling TFI from the trade stream and sends at
most one taker market IOC order by default. It must not import root-level
research scripts and must not read `date/` scored entries, path labels, PnL,
MFE, or MAE.

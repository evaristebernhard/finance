# Strategy Model

Strategies should not control the exchange clock.

Rigorous replay interaction:

```text
runner clock -> strategy observation -> order intent -> latency queue -> exchange order -> fill/portfolio event
```

The main implemented path is now `run python`, where the runner owns the replay
clock and a Python child process behaves like an exchange API bot over
stdin/stdout NDJSON.

Allowed Python inputs:

```text
market_quote
market_trade
market_l2_update
account_snapshot
order_ack
order_reject
fill
```

Allowed Python outputs:

```text
heartbeat
hold
submit_order
cancel_order
```

The first Python strategy is an online TFI skeleton. It maintains rolling state
from `market_trade` and `market_quote`, sends only taker market IOC orders, and
does not read scored entries, future labels, PnL, MFE, or MAE.

The older `run toy` path still exists for deterministic runner regression tests.

HTTP interaction remains useful for manual debugging:

```text
GET /api/state -> strategy decision -> POST /api/orders -> POST /api/step
```

Forbidden interaction:

```text
strategy imports root scripts
strategy reads date/ labels directly
strategy computes available leverage independently
```

The CCUSDT strategy client lives under
`strategies/python/ccusdt_tfi_core_idle01/`. It should remain an online runtime
client, not a wrapper around research CSVs.

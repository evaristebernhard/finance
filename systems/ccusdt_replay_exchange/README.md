# CCUSDT Replay Exchange MVP

Status: MVP, 2026-05-19.

This directory is intentionally independent from the older root `backend/` and
`frontend/` replay workbench. It is a local paper exchange surface that strategy
clients can talk to over HTTP while the market clock advances through a replay.

## Run

Synthetic replay:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/Cargo.toml -- --addr 127.0.0.1:8797
```

CSV replay:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/Cargo.toml -- --csv systems/ccusdt_replay_exchange/examples/frames.csv
```

CSV contract:

```text
ts,bid,ask
```

Accepted timestamp aliases are `ts`, `timestamp`, `local_ts`, and
`local_timestamp`. Accepted quote aliases are `bid`/`best_bid`/`best_bid_price`
and `ask`/`best_ask`/`best_ask_price`.

## API

```text
GET  /health
GET  /api/state
POST /api/step?frames=1
POST /api/reset
GET  /api/orders
POST /api/orders
POST /api/orders/{id}/cancel
GET  /api/fills
```

Example market order:

```powershell
Invoke-RestMethod http://127.0.0.1:8797/api/orders `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"side":"buy","kind":"market","qty":10,"tif":"ioc"}'
```

Example resting maker order:

```powershell
Invoke-RestMethod http://127.0.0.1:8797/api/orders `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"side":"buy","kind":"limit","qty":10,"limit_price":0.9999,"tif":"gtc"}'
Invoke-RestMethod 'http://127.0.0.1:8797/api/step?frames=1' -Method Post
```

## MVP Fill Model

- Market buy fills at current ask.
- Market sell fills at current bid.
- New crossing limit orders fill as taker at current ask/bid.
- Resting limit orders fill when the future quote crosses the limit; fill price
  is the limit price.
- Fees are configured in bps and default to zero.
- Risk rejects orders whose projected position notional exceeds
  `equity * max_leverage`.

This is a paper-exchange scaffold, not queue-position evidence. The next layer
should add latency, partial fills, queue model, strategy client process, and a UI
or log monitor.

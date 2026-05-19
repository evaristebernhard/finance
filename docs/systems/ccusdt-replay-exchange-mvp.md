# CCUSDT Replay Exchange MVP

Status: 2026-05-19.

The local paper exchange now lives independently from the older market replay
workbench:

```text
systems/ccusdt_replay_exchange/
```

Design boundary:

```text
market replay clock -> local exchange -> strategy client over HTTP
```

It should not import old research scripts. Research code can generate signals,
but executable rehearsal should talk to the exchange through the same API shape
that a future live adapter would expose.

Current MVP:

```text
Rust REST server
synthetic or CSV quote replay
market and limit orders
GTC and IOC
cash/position/equity/leverage accounting
fee-bps and max-leverage constraints
fills/orders/state endpoints
```

Run:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/Cargo.toml -- --addr 127.0.0.1:8797
```

Core endpoints:

```text
GET  /api/state
POST /api/orders
POST /api/step?frames=1
GET  /api/orders
GET  /api/fills
```

The first real integration step is not strategy optimization. It is to write a
separate tiny strategy client that consumes `/api/state`, decides whether to
submit an order, then advances replay with `/api/step`. That gives us a clean
paper-trading loop without coupling the exchange to any one TFI hypothesis.

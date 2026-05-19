# CCUSDT Replay Exchange MVP

Status: 2026-05-19. Updated to catalog + canonical data ingress.

The local paper exchange lives independently from the older market replay
workbench and now owns a catalog/canonical ingress layer:

```text
systems/ccusdt_replay_exchange/
```

Design boundary:

```text
old data/date -> catalog scan -> canonical market store -> local exchange -> strategy client over HTTP
```

It should not import old research scripts. Research code can generate signals,
but executable rehearsal should talk to the exchange through the same API shape
that a future live adapter would expose.

Current MVP:

```text
Rust REST server
synthetic or CSV quote replay
catalog scan
canonical quote/trade/L2 build and validate
market and limit orders
GTC and IOC
cash/position/equity/leverage accounting
fee-bps and max-leverage constraints
fills/orders/state endpoints
```

Current command shape:

```powershell
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/ccusdt_replay_exchange/engine/Cargo.toml -p ccusdt_replay_cli -- serve --canonical-date 2026-05-18
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

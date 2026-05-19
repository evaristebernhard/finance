# Architecture

Status: MVP architecture, 2026-05-19.

The system boundary is:

```text
old raw/research files -> catalog -> canonical events -> replay clock -> exchange sim -> runs
```

## Seven Layers

1. `catalog`: inventories local source data, dates, schema ids, and missing dates.
2. `canonical store`: materializes stable market-truth datasets from raw venue files.
3. `replay clock`: exposes canonical frames in deterministic time order.
4. `book/state builder`: turns canonical market events into strategy-observable state.
5. `strategy bridge`: accepts strategy intents without giving strategies raw file access.
6. `exchange simulator`: applies order, fill, cancel, latency, and future queue logic.
7. `portfolio/risk/event log`: owns account state, leverage checks, PnL, and run logs.

## Current MVP Boundary

Implemented now:

```text
catalog scan
canonical quote/trade/L2 materialization
quote-frame replay
market/limit paper exchange
REST API for state/orders/fills
```

Not implemented yet:

```text
latency queue
partial fills
real L2 queue-position model
strategy process supervisor
monitor UI
append-only run event log
```

## Data Policy

The system is non-destructive. It never moves old `data/ccusdt` or `date/`.
Generated catalog/canonical files are ignored local artifacts under repo-level
`data/catalog` and `data/canonical`.

The exchange reads canonical market truth. Research labels and TFI artifacts may
be cataloged as sidecars, but strategy runtime must not see post-trade labels by
default.


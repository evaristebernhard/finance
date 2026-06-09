# CCUSDT Replay Workbench

Status: 2026-05-17. This is the default market in the generic local replay UI/API. It is a diagnostic and rehearsal surface only, not a trading rule, execution recommendation, sizing rule, or alpha claim.

## Goal

The workbench generalizes the earlier BONK replay UI into:

```text
market replay artifacts -> Rust market replay API -> Next.js replay UI
```

For CCUSDT, the replay source is the fixed event-orderbook factor panel:

```text
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260517_ccusdt_fixed_factors_v3/
```

The API mode is `factor_panel_only`: each row already contains best bid/ask, top levels, mid, spread, microprice, and event-defined factor fields. This is good for factor inspection and replay drilling, but it is not queue-position fill evidence.

For CCUSDT, the visible replay rows are snapshot frames grouped by Tardis local timestamp. A quote can stay at the same best bid/ask for hundreds of frames while the snapshot depth and microprice move inside the book. The UI therefore labels CC cursors as frames, shows the current `snapshot / raw rows` source, and treats long stable-quote runs as a data-source diagnostic rather than proof that the browser froze.

## Run

Backend from the repo root:

```powershell
cargo run -p market_replay_backend -- --data-root . --addr 127.0.0.1:8787
```

Frontend from `frontend/`:

```powershell
npm run dev
```

Useful API checks:

```text
GET /health
GET /api/manifest?market=ccusdt
GET /api/replay?market=ccusdt&symbol=CCUSDT&date=2026-04-29&offset=0&limit=2400&stride=1
GET /api/summary?market=ccusdt&symbol=CCUSDT&date=2026-04-29
```

## Generic Pieces

- Backend market specs live in `backend/src/main.rs`.
- The frontend reads `market`, `symbols`, `dates`, `replay_mode`, and source caveats from `/api/manifest`.
- The factor board starts with the market's ranked `feature_name` values from `/api/summary`, then appends shared base factors.
- Derived research features such as `pos__mlofi_roll10_l25`, `neg__queue_imbalance_5`, `abs__microprice_dev_bps`, `signed_sq__mlofi_roll10_l1`, and `mlofi_combo` are computed in the UI from replay-row base factors.

## Current CCUSDT Window

Local coverage is `2026-04-29..2026-05-15` for `CCUSDT`. The current run tag is:

```text
20260517_ccusdt_fixed_factors_v3
```

Current interpretation stays conservative: the V3 ranking is useful for replay inspection, but after-cost execution evidence is not yet promoted into this UI.

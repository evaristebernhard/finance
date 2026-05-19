# Engineering Docs

Status: 2026-05-17. This page separates app engineering from research reports. The current app surface is the generic market replay workbench, with `CCUSDT` as the default market and BONK kept as an older selectable market.

## Market Replay Workbench

- CCUSDT runbook doc: [CCUSDT replay workbench](../markets/ccusdt/v1-replay-workbench.md)
- BONK legacy runbook doc: [BONK replay workbench](../markets/bonk/v1-replay-workbench.md)
- Backend package: [backend/Cargo.toml](../../backend/Cargo.toml)
- Backend entry point: [backend/src/main.rs](../../backend/src/main.rs)
- Frontend package: [frontend/package.json](../../frontend/package.json)
- Main UI component: [frontend/components/ReplayWorkbench.tsx](../../frontend/components/ReplayWorkbench.tsx)
- API client/types: [frontend/lib/api.ts](../../frontend/lib/api.ts), [frontend/lib/types.ts](../../frontend/lib/types.ts)
- Local AI proxy route: [frontend/app/api/local-ai/route.ts](../../frontend/app/api/local-ai/route.ts)

## Backend

Run from the repo root:

```powershell
cargo run -p market_replay_backend -- --data-root . --addr 127.0.0.1:8787
```

Primary endpoints:

```text
GET /health
GET /api/manifest?market=ccusdt
GET /api/replay?market=ccusdt&symbol=CCUSDT&date=2026-04-29&offset=0&limit=2400&stride=1
GET /api/summary?market=ccusdt&symbol=CCUSDT&date=2026-04-29
```

The backend is market-spec driven. `factor_panel_only` markets, currently CCUSDT, serve price/book/factors from a fixed event factor panel. `book_state_plus_factors` markets, currently BONK, serve canonical price/book state and join factor rows by exact timestamp.

## Frontend

Run from `frontend/`:

```powershell
npm install
npm run dev
```

Default backend base:

```text
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8787
```

Optional local AI proxy environment:

```text
LOCAL_AI_BASE=http://127.0.0.1:32081/v1
LOCAL_AI_MODEL=local-model
LOCAL_AI_API_KEY=<local service key, if required>
REPLAY_AI_NOTES_PATH=<optional notes jsonl path>
```

The first screen is the workbench itself: market/symbol/date selectors, replay controls, price/book view, factor board, factor inspector, local AI commentary, simulated order ticket, order tape, and portfolio state.

## Data Inputs

Default CCUSDT replay/factor source:

```text
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260517_ccusdt_fixed_factors_v3/
```

Older BONK replay source:

```text
data/bonk/v1/derived/bonk_v10_replayed_book_state/
data/bonk/v1/derived/bonk_v10c_event_ofi_panel/
```

Supporting summaries stay in `date/` for compatibility with existing scripts. See [date README](../../date/README.md) for cleanup policy.

## Engineering Boundary

The workbench is for inspection, rehearsal, and factor understanding. It is not a trading rule, execution instruction, sizing rule, or alpha claim. The UI deliberately keeps data-source caveats visible because CCUSDT factor-panel replay and BONK book-state replay have different fill-realism semantics.

# BONK Replay Workbench

Status: 2026-05-16. This is a local self-use UI and API layer for the fixed BONK V10 stage-1 pilot. It is an execution rehearsal and data-understanding tool, not a trading rule, execution recommendation, sizing rule, or alpha claim.

## Goal

The workbench turns the existing BONK replay artifacts into an interactive local system:

```text
V10/V10c replay artifacts -> Rust API -> Next.js replay UI
```

It is meant for manual replay:

```text
watch the reconstructed order book,
inspect factor values as event time advances,
place simulated market/limit orders,
see pending/fill behavior against the replayed book,
track position, cash, and mark-to-market PnL.
```

## Project Layout

```text
backend/
  Cargo.toml
  src/main.rs

frontend/
  package.json
  app/
  components/
  lib/
```

The backend is a Rust HTTP API. The frontend is a Next.js app. They are intentionally separate so the backend can later grow into a heavier replay service without coupling it to React state.

## Data Contract

Current canonical run:

```text
run_tag: 20260514_bonk_v10_stage1_pilot
symbols: BONK1MUSDC, BONK1MUSDT
dates: 2026-05-06 .. 2026-05-12
```

Canonical replay source for price and order book:

```text
data/bonk/v1/derived/bonk_v10_replayed_book_state/
  run_tag=20260514_bonk_v10_stage1_pilot/
    symbol=<SYMBOL>/
      dt=<YYYY-MM-DD>/
        state_parts/part_*.csv
```

Joined factor source:

```text
data/bonk/v1/derived/bonk_v10c_event_ofi_panel/
  run_tag=20260514_bonk_v10_stage1_pilot/
    symbol=<SYMBOL>/
      dt=<YYYY-MM-DD>/
        part_*.csv
```

The API joins these two sources by exact `timestamp`. Price, best bid/ask, spread, microprice, and book levels come from `bonk_v10_replayed_book_state`; V10c panel fields are used for OFI/MLOFI/queue/trade-flow factors and source diagnostics.

This split is intentional. A stale-price defect was observed in the V10c panel price fields:

```text
BONK1MUSDC 2026-05-06 00:04:00..00:05:30
V10c panel mid_price: one unique value, 6.5105
replayed book state mid_price: 14 unique values, 6.4905..6.5065
raw bullish_book_ticker bid/ask: also varied in the same window
```

The workbench therefore exposes `panel_mid_price`, `panel_mid_delta_bps`, and `panel_mid_delta_ticks_est` only as diagnostics. If the UI shows a source warning, trust the `book_state` price/book path for replay inspection and treat panel price fields as suspect for that window.

The joined factor panel contains:

```text
event timestamp and local timestamp
OFI, MLOFI, queue imbalance, trade-flow, depletion, replenish, cancellation factors
factor eligibility and execute/cancel confidence diagnostics
```

Supporting summaries:

```text
date/bonk_v10_replay_state_manifest_20260514_bonk_v10_stage1_pilot.csv
date/bonk_v10_dynamic_orderbook_analysis_quality_hourly_20260514_bonk_v10_stage1_pilot.csv
date/bonk_v10_dynamic_orderbook_analysis_state_hourly_20260514_bonk_v10_stage1_pilot.csv
date/bonk_v10_dynamic_orderbook_analysis_path_hourly_20260514_bonk_v10_stage1_pilot.csv
date/bonk_v10_dynamic_orderbook_analysis_path_summary_20260514_bonk_v10_stage1_pilot.csv
date/bonk_v10c_event_ofi_path_ranking_20260514_bonk_v10_stage1_pilot.csv
date/bonk_v10_dynamic_orderbook_analysis_blockers_20260514_bonk_v10_stage1_pilot.csv
```

## Backend

Run from the repo root:

```powershell
cargo run -p market_replay_backend -- --data-root . --addr 127.0.0.1:8787
```

Endpoints:

```text
GET /health
GET /api/manifest?market=bonk
GET /api/replay?market=bonk&symbol=BONK1MUSDC&date=2026-05-06&offset=0&limit=2400&stride=1
GET /api/summary?market=bonk&symbol=BONK1MUSDC&date=2026-05-06
```

The replay endpoint streams CSV parts and returns only a bounded slice. It does not load an entire 100k+ event day into the browser.

## Frontend

Install and run from `frontend/`:

```powershell
npm install
npm run dev
```

Default API base:

```text
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8787
```

Optional local AI proxy:

```text
LOCAL_AI_BASE=http://127.0.0.1:32081/v1
LOCAL_AI_MODEL=local-model
LOCAL_AI_API_KEY=<local service key, if required>
```

The browser calls the Next.js route `/api/local-ai`; the route calls the local OpenAI-compatible service server-side so the key is not exposed as `NEXT_PUBLIC_*`. The local service tested on 2026-05-16 required either `Authorization: Bearer ...` or `X-API-Key`, so the proxy sends both when `LOCAL_AI_API_KEY` is set.

The first screen is the workbench itself:

```text
symbol/date selector
offset/stride controls with explicit Go jump
play/pause/step/reset
event-time candle-style price chart with MID/MICRO overlays and volume/event-notional bars
top-level order book ladder
factor board with sparkline context and click-to-inspect behavior
factor detail panel with normalized overlay, scatter, lead/lag correlations, side-by-side price/factor charts, LaTeX formula, interpretation, and source paths
local AI assistant panel for current replay/factor/volatility context
market/limit simulated order ticket
order tape, position, cash, and equity
research context tables for factor ranking, path reads, and blockers
```

The UI intentionally borrows trading-terminal density for price/book/order ergonomics, but it is not meant to clone Binance. The important surface is the research workflow:

```text
select factor -> replay event time -> inspect normalized overlay/scatter/lag correlations -> read LaTeX formula/source/caveat -> decide whether the movement is interpretable or just noise
```

## Factor Inspector

Clicking a factor opens a dedicated technical-analysis panel. It shows:

```text
left chart: replay MID price from book_state
right chart: selected factor from V10c panel
current factor value
same-window Pearson rho(factor, price)
same-window Pearson rho(factor_t, next_event_return_t+1)
same-window Pearson rho(factor_t, abs(next_event_return_t+1))
lag table for factor_t vs future returns at +1/+3/+5/+10/+20/+40 events
scatter of factor z-score vs next move in ticks
normalized overlay of price z-score and factor z-score
LaTeX formula and interpretation
source paths and caveats
```

These correlations are local inspection aids only. They are computed over the loaded replay slice and can change with offset/stride. They are not validation, not out-of-sample evidence, and not a trading rule. In particular, a good-looking overlay can still be a lagging reaction; use the lag table and controls before trusting it.

The inspector also includes a simple cost hurdle:

```text
tick_size = inferred minimum positive MID change in the loaded slice
fee_hurdle_ticks = 2
mean_abs_next_move_ticks = mean(abs(mid[t+1] - mid[t]) / tick_size)
p_abs_move_gt_fee = share(abs(next move ticks) > fee_hurdle_ticks)
```

This is there because many BONK windows only move around two ticks per step. If typical event movement is roughly the same size as a two-tick fee/slippage hurdle, most apparent microstructure wiggles are mechanically hard to monetize even before signal error.

Current formula map:

| UI label | Field | Formula / definition | Read |
| --- | --- | --- | --- |
| Trade Flow Imb. | `trade_flow_imbalance` | `(trade_buy_amount - trade_sell_amount) / max(trade_buy_amount + trade_sell_amount, eps)` | Positive means taker buys dominated the matched trade window. |
| Queue Imb. L1 | `queue_imbalance_1` | `(bid_depth_1 - ask_depth_1) / max(bid_depth_1 + ask_depth_1, eps)` | Top-of-book visible depth skew. |
| Queue Imb. L5 | `queue_imbalance_5` | `(bid_depth_5 - ask_depth_5) / max(bid_depth_5 + ask_depth_5, eps)` | Five-level depth skew. |
| Queue Imb. L25 | `queue_imbalance_25` | `(bid_depth_25 - ask_depth_25) / max(bid_depth_25 + ask_depth_25, eps)` | Broad visible-book skew. |
| OFI L1 Norm | `ofi_l1_depth_norm` | `CKS_L1_OFI(before, after) / max(before_L1_depth, after_L1_depth, eps)` | Best-level pressure after depth normalization. |
| MLOFI L1/L5/L10 | `mlofi_norm_l1`, `mlofi_norm_l5`, `mlofi_norm_l10` | `CKS_OFI(level=N, before, after) / max(before_level_depth, after_level_depth, eps)` | Multi-level book-pressure diagnostics at different depths. |
| MLOFI L10 Roll | `mlofi_roll10_l10` | `mean(last 10 event values of mlofi_norm_l10)` | Persistence of deeper pressure in event time. |
| Micro Dev | `microprice_dev_bps` | `((microprice - mid_price) / mid_price) * 10000` | Size-weighted microprice deviation from mid. |
| Depletion Int. | `queue_depletion_intensity` | `depletion_total / max(current_depth_25, before_depth_25, eps)` | Current queue removal pressure versus visible depth. |
| Replenish Int. | `replenish_intensity` | `replenish_total / max(current_depth_25, before_depth_25, eps)` | Current replenishment pressure versus visible depth. |
| Cancel/Withdraw | `cancellation_withdrawal_intensity` | `cancel_total / max(current_depth_25, before_depth_25, eps)` | Estimated non-execution withdrawal pressure. |
| Liquidity Shock | `liquidity_shock_score` | `depletion_total / max(before_depth_25, eps)` | Size of depletion versus prior visible depth. |
| Cross Cleanup | `crossed_levels_removed` | Count of levels removed by crossed-book cleanup after an update batch. | Reconstruction quality/stress warning. |

Technical-analysis guardrail: indicators are derived from price/order-flow history. They should be used for context, structure, divergence/confirmation inspection, and hypothesis generation. Do not treat a single factor spike, local chart correlation, or local AI explanation as a live entry signal without after-cost validation, controls, sample size, and out-of-sample checks.

## Local AI Assistant

The AI assistant is intentionally a local commentary layer over the current replay state. It sends a compact context object with:

```text
symbol/date/timestamp/offset
selected factor name and value
price, best bid/ask, spread
volatility forecast and trailing realized vol
tick size, two-tick fee hurdle, mean absolute next move, fee-beat share
Pearson correlations and lag correlations
data-source diagnostics including panel_mid_delta_bps
```

The system prompt tells the assistant to classify the evidence as interpretable, noisy, lagging, or cost-constrained, and not to produce live trading advice, entries, or sizing.

## Current Simulation Semantics

The first simulated execution model is deliberately simple and visible:

```text
market buy fills at current best ask
market sell fills at current best bid
limit buy fills when limit >= replayed best ask
limit sell fills when limit <= replayed best bid
position is measured in BONK1M units
cash and PnL are measured in quote units
```

This is not a fill-realism claim. It is a manual rehearsal layer. Later versions can add queue position, maker wait, partial fills, cancellation, and cost model toggles once the UI loop feels usable.

## Volatility Forecast Display

The UI exposes a `Volatility Forecast` value as an interpretable replay proxy, not as a trained production model. It is trailing-only during normal replay:

```text
trailing realized event-return volatility
adjusted by current spread, absolute trade-flow imbalance, MLOFI pressure, and liquidity-shock score
```

At the very start of a slice, before enough trailing returns exist, it uses a warmup baseline from current spread and microprice deviation so the panel does not show a misleading zero. This warmup value should be read as "current microstructure risk proxy", not learned forecast skill.

## Skill Search Note

Searched the open skills ecosystem for:

```text
nextjs dashboard data visualization
trading quantitative finance ui
react financial dashboard
rust backend api nextjs
order book trading replay
market microstructure orderbook
trading terminal ui nextjs chart
```

No exact "order-book replay quant UI" skill was found. The closest generic matches were TradingView chart integration, terminal UI design, Next.js/React TypeScript, dashboard/data visualization, and market-microstructure skills. This project proceeds with a repo-specific implementation because the important part is wiring the local BONK V10/V10c artifacts correctly and exposing the data-source caveat in the UI.

## Guardrail

The UI can make weak factors feel concrete because it lets a human watch them move in event time. That is useful for understanding. It is not evidence that the factors are tradable. The existing V10/V10c/V13/V15A reports still control interpretation:

```text
use the replay UI for inspection and self-drill,
do not promote factor flashes to strategy rules without after-cost, control, and validation evidence.
```

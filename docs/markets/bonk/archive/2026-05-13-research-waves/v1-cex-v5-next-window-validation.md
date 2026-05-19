# BONK V5 Next-Window Validation Design

Status: 2026-05-13. This is a minimum-data validation design for the BONK Bullish L2 research state under the constraint that Tardis should not be asked for a roughly 50-day ticker/L2 pull. It is not a trading rule, not an execution plan, not a sizing rule, and not an alpha claim.

## Objective

Validate the current frozen BONK L2 state on a fresh, smaller window:

```text
BONK1MUSDT H4 depth_high + rv_low
BONK1MUSDT H4 depth_high + rv_low + cv_spread
```

The validation must answer only this:

```text
Does the same pre-registered state survive exact labels, public Binance context controls,
Bullish basket placebos, and displayed-depth stress on the next available window?
```

Do not reselect symbols, dates, barriers, horizons, or thresholds on the validation window.

## Current Frozen Source

Use the current canonical run only as the definition/training source:

```text
run_tag: 20260513_bullish_l2_basket_price_v1
raw L2 window: 2026-04-29..2026-05-12
primary report: docs/markets/bonk/v1-cex-v4-orderbook-synthesis.md
gate plan: docs/markets/bonk/v1-cex-v4-orderbook-research-plan.md
exact-label audit: docs/markets/bonk/v1-cex-v4-exact-label-audit.md
capacity audit: docs/markets/bonk/v1-cex-v4-orderbook-capacity.md
negative controls: docs/markets/bonk/v1-cex-v3-negative-controls.md
```

Freeze the gate definitions from that run:

| id | symbol | horizon | barrier | gate | role |
| --- | --- | ---: | ---: | --- | --- |
| `h4_usdt_depth_rv` | BONK1MUSDT | 4h | 100 bps | `depth_high + rv_low` | primary |
| `h4_usdt_depth_rv_cv` | BONK1MUSDT | 4h | 100 bps | `depth_high + rv_low + cv_spread` | primary |
| `h4_usdc_depth_rv_mirror` | BONK1MUSDC | 4h | 100 bps | same | watch only |
| `h4_usdc_depth_rv_cv_mirror` | BONK1MUSDC | 4h | 100 bps | same | watch only |

Thresholds must be the train-side thresholds already implied by the current pipeline. If the current artifacts do not expose reusable numeric thresholds for a true holdout run, the next engineering task is to export them before collecting more data. Do not fit thresholds on the next-window rows.

## Minimum Data

The minimum useful next collection is a five-UTC-date Bullish L2 tranche:

```text
validation outcome dates: 4 complete UTC dates immediately after 2026-05-12
lookahead date: 1 additional UTC date for exact 4h/12h endpoints
example if available: 2026-05-13..2026-05-17
```

As of 2026-05-13, that example tranche is mostly in the future. Do not substitute a partial current UTC day. Wait until the daily Tardis downloadable files exist, or shift the same five-date pattern to the earliest complete post-2026-05-12 dates that are available.

Why five dates:

- Four outcome days give `5,760` possible minute rows per BONK symbol before final horizon drops.
- The primary H4 gates previously selected about `6%..11%` of USDT rows, so four days is the minimum likely to reach about `300` selected minutes for at least the base H4 gate.
- The fifth date prevents the exact-label rebuild from depending on row-offset labels near the window end.
- It is far smaller than a 50-day ticker pull, roughly one third of the current 14-day Bullish L2 window.

Preferred if disk/network capacity is clearly fine:

```text
2026-05-13..2026-05-20
```

That is seven outcome days plus one lookahead day. It is still small, but gives the `h4_usdt_depth_rv_cv` gate a better chance of avoiding a `too_sparse` verdict.

## Symbols And Data Types

Use the same available Bullish basket if available:

```text
BONK1MUSDC,BONK1MUSDT,
BTCUSDC,ETHUSDC,SOLUSDC,
DOGEUSDC,PENGUUSDC,
PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,
SUIUSDC
```

Keep `APTUSDC`, `ARBUSDC`, and `OPUSDC` out unless Bullish metadata starts showing them as available. They were missing in the current run.

Data types:

```text
book_snapshot_25,book_ticker,trades
```

The primary H4 gates mostly need snapshots, book tickers, and public Binance context, but keeping `trades` preserves the current quality/activity surface and avoids a new missing-family branch in the report pipeline.

Fallback tiers:

| tier | collect | what remains valid |
| --- | --- | --- |
| A | same available Bullish basket above | full validation, basket/placebo/common-mode checks |
| B | BONK pair + BTC/ETH/SOL + DOGE/PENGU/SUI | primary gates plus limited Bullish common-mode checks |
| C | BONK1MUSDC/BONK1MUSDT only | exact labels, self-state, cross-venue, and capacity only; no promotion |

Tier C is a data-quality smoke only. It cannot promote the candidate because it loses Bullish basket placebos.

## Public Binance Context

Do not use Tardis for the market ticker context. Reuse the public Binance spot 1m kline path:

```text
data/mon_usdc/v1/external/binance_klines
data/bonk/v1/derived/bonk_cex_price_context
```

Use the same context basket:

```text
BONKUSDT,BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,
PEPEUSDT,SHIBUSDT,WIFUSDT,SUIUSDT,
APTUSDT,ARBUSDT,OPUSDT,PENGUUSDT
```

These public klines are enough for:

- BONK public price return and realized volatility.
- BTC/ETH/SOL market basket.
- Meme basket.
- SOL-specific relative return.
- Residual return labels and relative-meme checks.

All context features used for gates must be `t` and earlier. Future public Binance returns are outcomes/controls only.

## Exact Labels

The next-window report must use timestamp-exact labels, not row-offset labels.

Required labels:

| family | symbol | horizons | barriers | required columns |
| --- | --- | --- | --- | --- |
| primary path | BONK1MUSDC/BONK1MUSDT | 4h | 100 bps | `upper_first`, `lower_first`, `both_or_ambiguous`, `mfe_up_bps`, `mae_down_bps`, `path_width_bps`, exact `future_return_bps` |
| context path | BONK1MUSDC/BONK1MUSDT | 1h, 12h | 50, 100 bps | same, report-only |
| decay | BONK1MUSDC/BONK1MUSDT | 5m, 15m, 30m | 20, 30 bps | report-only |
| residual | BONK1MUSDC/BONK1MUSDT | 4h | exact endpoint return | raw and public-Binance-residual future returns |

Rows without exact endpoints are excluded from validation metrics and counted separately. A gate cannot pass if its selected rows are concentrated in exact-endpoint-missing rows.

## Capacity Checks

Carry forward the V4 capacity table shape. For each primary and mirror H4 gate, report:

- selected rows and selected share;
- median gross exact future return;
- median residual return and residual-positive edge;
- lower-first rate versus baseline;
- median adverse excursion;
- median spread and spread stress;
- p10 and median side-conservative displayed depth at top, 5 levels, and 25 levels;
- quote bucket survival for `5,10,25,50,100,250,500,1000`;
- stress-net capacity envelope under `spread_only`, `depth_light`, `depth_base`, and `wide_stress`.

The current V4 H4 status was capacity-limited but not zero:

```text
top-of-book envelope: effectively 0
5-level envelope: about 50 quote
25-level wide-stress envelope: about 500 quote
```

The next window should be rejected for execution-research promotion if the 25-level wide-stress envelope drops below `250` quote, if median stress net is not positive at small buckets, or if lower-first/drawdown dominates the gross edge.

## Sequence

Use these run tags for the first tranche, adjusted only if the actual available dates differ:

```text
NEXT_TAG=20260518_bullish_l2_nextwin_v1
FROM_DATE=2026-05-13
TO_DATE=2026-05-17
```

This sequence is intentionally written for the first complete post-2026-05-12 tranche. If run before 2026-05-17 UTC has settled and appeared in Tardis downloadable datasets, stop at preflight.

1. Capacity and access preflight:

```powershell
python scripts/tardis_access_probe.py --env-file .env.chog.local --exchange bullish --symbol BONK1MUSDT

python scripts/bonk_bullish_l2_download.py `
  --data-root data/bonk/v1 `
  --date-dir date `
  --from-date 2026-05-13 `
  --to-date 2026-05-17 `
  --symbols "BONK1MUSDC,BONK1MUSDT,BTCUSDC,ETHUSDC,SOLUSDC,DOGEUSDC,PENGUUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,SUIUSDC" `
  --data-types "book_snapshot_25,book_ticker,trades" `
  --run-tag 20260518_bullish_l2_nextwin_dryrun `
  --workers 4 `
  --min-free-gb 10 `
  --dry-run
```

Do not continue if BONK1MUSDC or BONK1MUSDT is missing, if the drive has less than `10 GB` free, or if preflight suggests the same basket is broadly unavailable.

2. Download the small Bullish tranche:

```powershell
python scripts/bonk_bullish_l2_download.py `
  --data-root data/bonk/v1 `
  --date-dir date `
  --from-date 2026-05-13 `
  --to-date 2026-05-17 `
  --symbols "BONK1MUSDC,BONK1MUSDT,BTCUSDC,ETHUSDC,SOLUSDC,DOGEUSDC,PENGUUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,SUIUSDC" `
  --data-types "book_snapshot_25,book_ticker,trades" `
  --run-tag 20260518_bullish_l2_nextwin_v1 `
  --workers 4 `
  --min-free-gb 10
```

Stop if any BONK file is `error`, gzip-invalid, or empty. Sparse meme files may be empty only if the manifest marks them consistently with the prior sparse-symbol behavior.

3. Build public Binance context for the same dates:

```powershell
cargo run --release -p cex_l2_research --bin bonk_cex_price_context -- `
  --data-root data/bonk/v1 `
  --local-kline-dir data/mon_usdc/v1/external/binance_klines `
  --date-dir date `
  --from-date 2026-05-13 `
  --to-date 2026-05-17 `
  --run-tag 20260518_bullish_l2_nextwin_v1 `
  --workers 4
```

Stop if public Binance context coverage is below `99.9%` for BONKUSDT, BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, PENGUUSDT, or SUIUSDT. Missing APT/ARB/OP context should be reported but does not block BONK validation.

4. Rebuild L2 state and panel for the next window:

```powershell
cargo run --release -p cex_l2_research --bin bonk_cex_l2_report -- `
  --data-root data/bonk/v1 `
  --date-dir date `
  --doc-dir docs/markets/bonk `
  --run-tag 20260518_bullish_l2_nextwin_v1 `
  --symbols "BONK1MUSDC,BONK1MUSDT,BTCUSDC,ETHUSDC,SOLUSDC,DOGEUSDC,PENGUUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,SUIUSDC" `
  --label-symbols "BONK1MUSDC,BONK1MUSDT" `
  --price-context-run-tag 20260518_bullish_l2_nextwin_v1

cargo run --release -p cex_l2_research --bin bonk_cex_research_panel -- `
  --data-root data/bonk/v1 `
  --date-dir date `
  --run-tag 20260518_bullish_l2_nextwin_v1 `
  --l2-run-tag 20260518_bullish_l2_nextwin_v1 `
  --price-context-run-tag 20260518_bullish_l2_nextwin_v1
```

Before using the results for validation, ensure the exact-label rebuild is canonical or run the V4 exact-label script against the next-window panel and consume only exact-label metrics.

5. Run the frozen-gate validation diagnostics:

```text
exact-label gate table
missing-minute impact table
negative controls: random phase, 240m/720m time shifts, symbol/quote placebo
cross-section placebo against available Bullish basket and public Binance meme basket
orderbook capacity table
short-horizon decay table, report-only
```

Any script that currently hardcodes `20260513_bullish_l2_basket_price_v1` should be parameterized or copied with a clearly named V5 run tag. Do not edit the hardcoded tag and overwrite V4 outputs.

## Pass / Fail Gates

The next-window validation can move a gate from `research_state` to `validation_candidate` only if all required rows below pass:

| check | pass condition |
| --- | --- |
| exact labels | active selected rows have exact endpoints; selected exact-endpoint-missing rate below `0.5%` |
| sample size | at least `300` selected H4 minutes, otherwise `too_sparse` |
| residual | selected median residual return `> 0` and residual-positive edge `> 0` |
| lower-first | selected lower-first rate no worse than window baseline; preferred improvement at least `5 pp` |
| relative meme | selected BONK future return positive versus public Binance meme basket |
| phase | at least `60%` of eligible phase rows have positive median residual edge |
| controls | random phase p95 and 240m/720m time shifts do not beat the actual gate |
| cross-section | BONK remains positive after meme-basket adjustment; non-BONK placebos do not dominate |
| capacity | positive median stress net at small buckets and 25-level wide-stress envelope at least `250` quote |

If `h4_usdt_depth_rv` passes but `h4_usdt_depth_rv_cv` is sparse, keep only the base gate as a validation candidate and keep the cross-venue gate as `watch_sparse`. If the cross-venue gate passes and the base gate fails, mark the result `needs_second_tranche` rather than promoting immediately.

## Stop Rules

Stop immediately and do not collect a larger window if any of these happens:

- Tardis access returns unauthorized/forbidden for Bullish, or BONK1MUSDC/BONK1MUSDT files are unavailable.
- Download manifest has BONK errors, gzip failures, empty BONK files, or repeated non-BONK errors above `5%` of scheduled files.
- BONK observed-minute coverage is below `99%` for either Bullish pair.
- Exact-label selected rows are too sparse for both primary gates.
- Exact labels erase the H4 residual/gross edge.
- Lower-first is worse than baseline for both primary gates.
- BONK is not positive relative to the public Binance meme basket inside the selected rows.
- Random phase, time-shift, or cross-section placebos dominate both primary gates.
- Capacity stress is negative or the 25-level wide-stress envelope falls below `250` quote.

If the first five-date tranche is promising but sparse, collect at most one more adjacent tranche with the same frozen gates:

```text
example second tranche: 2026-05-18..2026-05-22
```

After two small tranches, stop and summarize. Do not expand toward a 50-day Tardis ticker/L2 request unless the frozen gates pass exact labels, controls, relative-market checks, and capacity stress on the small tranches.

## Concrete Minimal Decision

Minimum next action:

```text
Collect or reuse only 2026-05-13..2026-05-17 Bullish downloadable L2 CSV.gz
for the same available Bullish basket, plus public Binance spot klines for the same dates.
```

The expected final V5 deliverable is a concise validation memo that says one of:

```text
pass_validation_candidate
needs_second_small_tranche
too_sparse
failed_exact_labels
failed_controls
failed_relative_meme
failed_capacity
```

Anything other than `pass_validation_candidate` or `needs_second_small_tranche` means stop collecting and return to factor design, label engineering, or data-quality repair.

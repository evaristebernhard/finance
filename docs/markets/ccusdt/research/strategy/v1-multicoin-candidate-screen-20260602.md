# CCUSDT TFI Structure Multicoin Candidate Screen

Status: `research_design_20260602`. No new market data is downloaded by this
document.

## Why This Screen Exists

The CCUSDT TFI/stale-release line should not be judged only on CCUSDT. If the
structure is real, a related version should appear on other Bullish symbols
with a suitable execution envelope. But the first migration basket should not
start from BTC/ETH/SOL: those instruments are highly efficient, heavily studied,
and likely to compress any simple short-horizon order-flow edge.

The target is not the largest symbol. The target is a symbol where:

```text
short-horizon release room / taker spread cost
```

is large enough, while trade density is still high enough for TFI to be a real
state rather than empty-window noise.

## Historical Input

Use the existing historical screen:

```text
docs/research/bonk/2026-05-16-tardis-bullish-volatility-symbol-screen.md
date/tardis_bullish_volatility_summary_20260516_bullish_vol_screen_v1.csv
date/tardis_bullish_volatility_fast_20260516_bullish_vol_screen_v1.csv
```

That screen used Tardis downloadable Bullish `book_ticker` over
`2026-05-12..2026-05-15` and ranked symbols by realized volatility, daily range,
median spread, and price-scale geometry.

Its own conclusion already warns against treating "highest volatility" as the
answer. A candidate must fit inside:

```text
volatility - spread - fee - tick/price-scale constraints
```

## Re-read of the Historical Screen

Primary historical candidates:

| symbol | avg 1m RV | avg range | median spread | avg mid | read |
|---|---:|---:|---:|---:|---|
| `CCUSDT` | 4.64% | 8.22% | 1.9 bps | 0.1594 | Known active line; use as reference. |
| `ETHFIUSDC` | 4.74% | 8.50% | 4.4 bps | 0.4453 | Best first migration candidate. |
| `IOTAUSDT` | 3.57% | 7.75% | 5.0 bps | 0.0617 | Low price scale, tolerable spread. |
| `NIGHTUSDT` | 3.21% | 7.73% | 8.2 bps | 0.0334 | Higher spread, but good movement and small scale. |
| `SUIUSDC` | 4.90% | 7.77% | 9.8 bps | 1.2098 | High movement, but near the spread warning boundary. |

Secondary / control candidates:

| symbol | role | reason |
|---|---|---|
| `VTHOUSDT` | low-cost secondary | Very small price scale and acceptable spread, but lower volatility. |
| `VETUSDT` | low-cost secondary/control | Very tight spread, but movement may be too low for strong release. |
| `BONK1MUSDT` | historical control | Prior BONK work exists; useful as comparison, not first migration. |
| `BONK1MUSDC` | historical control | Similar to BONK1MUSDT with wider spread. |
| `PENGUUSDT` | cost stress only | Excellent movement, but spread was about 16.9 bps. |
| `CHZUSDT` | cost stress only | High movement, but spread was about 21 bps. |
| `BTC/ETH/SOL` | efficiency controls | Good for negative/control checks, poor first alpha-discovery basket. |

## No-download Preflight

A dry-run availability preflight was run for:

```text
ETHFIUSDC,IOTAUSDT,NIGHTUSDT,SUIUSDC,VTHOUSDT,VETUSDT,BONK1MUSDT
```

over:

```text
2026-05-28..2026-05-30
```

with:

```text
book_ticker,trades,incremental_book_L2
```

Output:

```text
date/tardis_bullish_download_manifest_20260602_multicoin_candidate_preflight_dryrun_v1.csv
date/tardis_bullish_download_completion_20260602_multicoin_candidate_preflight_dryrun_v1.json
```

The dry run planned `63` files and did not download data.

## Recommended First Download Basket

Do not download BTC/ETH/SOL first. The first real migration basket should be:

```text
ETHFIUSDC
IOTAUSDT
NIGHTUSDT
SUIUSDC
```

Use `VTHOUSDT` and `VETUSDT` only if we want low-spread controls. Use
`BONK1MUSDT` only as historical comparison.

Recommended first window:

```text
2026-05-28..2026-05-30
```

Recommended data types:

```text
book_ticker,trades,incremental_book_L2
```

Reason: this is enough to rebuild `quote_frame_v1`, `trade_event_v1`,
`l2_level_update_v1`, and `decision_frame_v1`, then test the same
TFI/stale-release structure with executable top-of-book labels.

## Research Gate

For each symbol, the first diagnostic should report:

```text
symbol
days
decision_frame_rows
trade_window_nonempty_rate
median_spread_bps
p90_spread_bps
old_tfi_stale_candidate_n
mean_mid60_bps
mean_exec60_bps
daily_sign_rate
spread_cost_gap_bps
```

Promotion to deeper research requires:

```text
mean_exec60_bps > 0
daily_sign_rate >= 2/3
old_tfi_stale_candidate_n not tiny
spread_cost_gap not dominating mid edge
```

If a symbol has positive mid edge but negative executable edge, classify it as
`spread_cost_mirage` and do not proceed to strict replay.


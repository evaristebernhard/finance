# BONK V4 Short-Horizon Orderbook Analysis

Status: 2026-05-13T12:55:49Z. Research diagnostic only: no trading rule, no execution plan, no sizing rule, and no alpha claim.

## Inputs And Outputs

- L2 state input: `data\bonk\v1\derived\bonk_cex_l2_state\bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet`
- Price context input: `data\bonk\v1\derived\bonk_cex_price_context\bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet`
- No raw downloads were performed.
- Label summary: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_label_summary.csv`
- Train-only thresholds: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_thresholds.csv`
- Fold bucket summary: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_factor_buckets.csv`
- Day summary: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_day_summary.csv`
- Phase summary: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_phase_summary.csv`
- Lag decay: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_lag_decay.csv`
- Context/RV model comparison: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_model_metrics.csv`
- Completion JSON: `date\bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_completion.json`

## Label Coverage

| symbol | horizon | barrier | ok rows | upper | lower | any hit | median residual bps | path width bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDC | 5m | 20 | 20056 | 20.3% | 18.5% | 38.8% | -0.05 | 16.05 |
| BONK1MUSDC | 5m | 30 | 20056 | 10.3% | 9.3% | 19.5% | -0.05 | 16.05 |
| BONK1MUSDC | 15m | 20 | 20031 | 39.8% | 37.5% | 77.4% | -0.27 | 37.46 |
| BONK1MUSDC | 15m | 30 | 20031 | 28.1% | 26.2% | 54.2% | -0.27 | 37.46 |
| BONK1MUSDC | 30m | 20 | 20003 | 47.6% | 45.2% | 92.7% | -0.47 | 58.54 |
| BONK1MUSDC | 30m | 30 | 20003 | 40.1% | 37.1% | 77.2% | -0.47 | 58.54 |
| BONK1MUSDT | 5m | 20 | 20110 | 20.8% | 18.9% | 39.6% | -0.09 | 16.29 |
| BONK1MUSDT | 5m | 30 | 20110 | 10.6% | 9.5% | 20.1% | -0.09 | 16.29 |
| BONK1MUSDT | 15m | 20 | 20085 | 40.2% | 37.9% | 78.1% | -0.27 | 38.11 |
| BONK1MUSDT | 15m | 30 | 20085 | 28.5% | 26.6% | 55.0% | -0.27 | 38.11 |
| BONK1MUSDT | 30m | 20 | 20062 | 47.6% | 45.4% | 93.1% | -0.51 | 58.93 |
| BONK1MUSDT | 30m | 30 | 20062 | 40.5% | 37.4% | 77.9% | -0.51 | 58.93 |

## Strongest Train-Threshold Buckets

Buckets below are validation-only reads using thresholds fit on each fold's train side. Positive direction edge means upper-first improved and/or lower-first fell versus that fold's validation baseline.

| symbol | H | B | family | factor | bucket | rows | direction edge | resid-pos edge | median resid bps | stability |
| --- | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDC | 30m | 20 | spread | `spread_bps_last` | high | 440 | 14.3% | 20.2% | 8.18 | 1.50 |
| BONK1MUSDC | 30m | 30 | spread | `spread_bps_last` | high | 440 | 10.2% | 20.2% | 8.18 | 1.50 |
| BONK1MUSDC | 30m | 30 | spread | `spread_bps_median` | high | 450 | 13.8% | 16.7% | 6.53 | 1.50 |
| BONK1MUSDC | 30m | 20 | spread | `spread_bps_median` | high | 450 | 11.6% | 16.7% | 6.53 | 1.50 |
| BONK1MUSDC | 30m | 30 | depth | `depth25_total_notional_median` | high | 1064 | -8.0% | -4.1% | -6.00 | 1.50 |
| BONK1MUSDC | 15m | 30 | spread | `spread_bps_median` | high | 450 | 7.6% | 7.9% | 2.19 | 1.50 |
| BONK1MUSDC | 15m | 20 | spread | `spread_bps_median` | high | 450 | 6.1% | 7.9% | 2.19 | 1.50 |
| BONK1MUSDC | 15m | 20 | spread | `spread_bps_last` | high | 440 | 5.8% | 7.2% | 2.19 | 1.50 |
| BONK1MUSDC | 15m | 30 | depth | `depth25_total_notional_median` | high | 1065 | -7.2% | -4.0% | -2.03 | 1.50 |
| BONK1MUSDT | 15m | 30 | depth | `depth25_total_notional_median` | high | 1067 | -6.5% | -4.1% | -2.39 | 1.50 |
| BONK1MUSDC | 30m | 20 | cross_venue | `cross_venue_spread_diff_bps` | high | 540 | 8.1% | 3.7% | 0.93 | 1.50 |
| BONK1MUSDC | 15m | 30 | spread | `spread_bps_last` | high | 440 | 3.3% | 7.2% | 2.19 | 1.50 |
| BONK1MUSDT | 30m | 20 | cross_venue | `cross_venue_spread_diff_bps` | low | 539 | 7.8% | 3.5% | 0.64 | 1.50 |
| BONK1MUSDT | 15m | 20 | depth | `depth25_total_notional_median` | high | 1067 | -5.4% | -4.1% | -2.39 | 1.50 |
| BONK1MUSDC | 15m | 20 | depth | `depth25_total_notional_median` | high | 1065 | -5.2% | -4.0% | -2.03 | 1.50 |

## Lag Decay

Lag decay is measured as validation Spearman rank correlation against residual return, path direction, path width, and raw return. The table shows the largest median absolute short-lag reads.

| family | factor | lag | median abs rho | rows |
| --- | --- | ---: | ---: | ---: |
| spread | `spread_bps_median` | 0m | 0.0498 | 551856 |
| cross_venue | `cross_venue_basis_bps` | 0m | 0.0489 | 551712 |
| spread | `spread_bps_last` | 0m | 0.0488 | 551856 |
| activity | `snapshot_count` | 0m | 0.0474 | 551856 |
| spread | `spread_bps_median` | 15m | 0.0454 | 551856 |
| spread | `spread_bps_median` | 30m | 0.0451 | 551856 |
| activity | `log1p_activity_count` | 0m | 0.0441 | 551856 |
| spread | `spread_bps_median` | 5m | 0.0434 | 551856 |
| activity | `book_ticker_count` | 0m | 0.0431 | 551856 |
| spread | `spread_bps_last` | 5m | 0.0413 | 551856 |
| cross_venue | `cross_venue_basis_bps` | 5m | 0.0404 | 551712 |
| activity | `snapshot_count` | 5m | 0.0392 | 551856 |

## Context/RV Controls

The control model uses market/meme/SOL/BONK trailing returns, BONK-relative context, and BONK realized-volatility fields. The orderbook model adds spread, depth, microprice, WOBI, activity, and cross-venue fields.

- Overall logloss win rate for adding orderbook: 33.3%.
- Median delta logloss, orderbook minus context/RV: `0.00378`.
- Overall Brier win rate for adding orderbook: 29.6%.
- Median delta AUC, orderbook minus context/RV: `0.0015`.

| target | comparisons | logloss win | median delta logloss | brier win | median delta AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| lower_first | 36 | 33.3% | 0.00725 | 25.0% | 0.0019 |
| residual_positive | 36 | 22.2% | 0.00344 | 22.2% | -0.0013 |
| upper_first | 36 | 44.4% | 0.00311 | 41.7% | 0.0036 |

## Read

The strongest short-horizon objects are bucket/state diagnostics, not execution-ready signals. Activity and spread/depth variables often dominate movement and first-hit separation; cross-venue variables appear more as state/routing diagnostics than as clean signed alpha. Promotion still requires a next-window retest and explicit execution-cost modeling.

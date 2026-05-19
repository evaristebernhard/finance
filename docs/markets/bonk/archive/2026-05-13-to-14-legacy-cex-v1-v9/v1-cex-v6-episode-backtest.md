# BONK V6 Episode Backtest

Status: 2026-05-13T15:09:51Z. Run tag: `20260513_bullish_l2_basket_price_v1`. Output tag: `20260513_bullish_l2_basket_price_v1`.

This report is research-only. It is not a trading rule, not an execution instruction, not a sizing rule, and not an alpha claim.

## Setup

- Gates: h4_usdt_depth_rv, h4_usdt_depth_rv_cv, h4_usdt_depth_rv_micro, h4_usdt_depth_rv_cv_micro, h4_usdc_depth_rv_mirror, h4_usdc_depth_rv_cv_mirror.
- TP grid: `[30, 50, 75, 100, 150]` bps; SL grid: `[20, 30, 50, 75, 100]` bps; timeout grid: `[30, 60, 120, 240]` minutes.
- Execution models: `["mid_research", "maker_light", "taker_spread", "wide_stress"]`; notional quote: `100`.
- Entry: next-minute Bullish L2 mid open after a false-to-true gate transition.
- Exit order: worst-case same-bar stop, stop, take-profit, gate-off, timeout, data-gap/fold-end.

## Completion

- Trades: `1056400`; daily rows: `24000`; summary rows: `9600`.
- Validation checks passed: `true`.
- Same-bar ambiguous trades: `0`.

## Maker-Light Top Rows

| gate | exec | tp | sl | to | avg $/day | total $ | win | tr/d | max DD | ambig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4_usdt_depth_rv_cv_micro | maker_light | 100 | 20 | 60 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 100 | 20 | 120 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 150 | 20 | 60 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 100 | 20 | 240 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 75 | 20 | 60 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 150 | 20 | 240 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 75 | 20 | 30 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 100 | 20 | 30 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 150 | 20 | 30 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 75 | 20 | 120 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 150 | 20 | 120 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |
| h4_usdt_depth_rv_cv_micro | maker_light | 75 | 20 | 240 | -0.341 | -3.410 | 34.8% | 21.00 | 3.511 | 0.0% |

## Taker-Spread Top Rows

| gate | exec | tp | sl | to | avg $/day | total $ | win | tr/d | max DD | ambig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4_usdt_depth_rv_cv_micro | taker_spread | 75 | 20 | 120 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 75 | 20 | 60 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 100 | 20 | 120 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 100 | 20 | 30 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 150 | 20 | 30 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 100 | 20 | 60 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 150 | 20 | 240 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 100 | 20 | 240 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 75 | 20 | 240 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 75 | 20 | 30 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 150 | 20 | 60 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |
| h4_usdt_depth_rv_cv_micro | taker_spread | 150 | 20 | 120 | -0.804 | -8.041 | 25.7% | 21.00 | 8.041 | 0.0% |

## Mid Research Upper Bound

| gate | exec | tp | sl | to | avg $/day | total $ | win | tr/d | max DD | ambig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4_usdc_depth_rv_mirror | mid_research | 75 | 20 | 240 | 0.457 | 4.569 | 43.4% | 67.90 | 0.472 | 0.0% |
| h4_usdc_depth_rv_mirror | mid_research | 75 | 20 | 120 | 0.457 | 4.569 | 43.4% | 67.90 | 0.472 | 0.0% |
| h4_usdc_depth_rv_mirror | mid_research | 75 | 20 | 30 | 0.457 | 4.569 | 43.4% | 67.90 | 0.472 | 0.0% |
| h4_usdc_depth_rv_mirror | mid_research | 75 | 20 | 60 | 0.457 | 4.569 | 43.4% | 67.90 | 0.472 | 0.0% |
| h4_usdc_depth_rv_mirror | mid_research | 50 | 20 | 240 | 0.432 | 4.318 | 43.4% | 67.90 | 0.472 | 0.0% |
| h4_usdc_depth_rv_mirror | mid_research | 50 | 20 | 30 | 0.432 | 4.318 | 43.4% | 67.90 | 0.472 | 0.0% |
| h4_usdc_depth_rv_mirror | mid_research | 50 | 20 | 120 | 0.432 | 4.318 | 43.4% | 67.90 | 0.472 | 0.0% |
| h4_usdc_depth_rv_mirror | mid_research | 50 | 20 | 60 | 0.432 | 4.318 | 43.4% | 67.90 | 0.472 | 0.0% |

## Wide Stress Downside

| gate | exec | tp | sl | to | avg $/day | total $ | win | tr/d | max DD | ambig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4_usdt_depth_rv_cv_micro | wide_stress | 100 | 20 | 30 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |
| h4_usdt_depth_rv_cv_micro | wide_stress | 150 | 20 | 30 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |
| h4_usdt_depth_rv_cv_micro | wide_stress | 150 | 20 | 120 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |
| h4_usdt_depth_rv_cv_micro | wide_stress | 75 | 20 | 30 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |
| h4_usdt_depth_rv_cv_micro | wide_stress | 75 | 20 | 60 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |
| h4_usdt_depth_rv_cv_micro | wide_stress | 100 | 20 | 120 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |
| h4_usdt_depth_rv_cv_micro | wide_stress | 100 | 20 | 60 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |
| h4_usdt_depth_rv_cv_micro | wide_stress | 150 | 20 | 240 | -1.038 | -10.381 | 19.5% | 21.00 | 10.381 | 0.0% |

## Active Gate View

| gate | exec | tp | sl | to | avg $/day | total $ | win | tr/d | max DD | ambig |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4_usdt_depth_rv | mid_research | 75 | 20 | 30 | 0.204 | 2.042 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 75 | 20 | 240 | 0.204 | 2.042 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 75 | 20 | 60 | 0.204 | 2.042 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 75 | 20 | 120 | 0.204 | 2.042 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 50 | 20 | 30 | 0.202 | 2.016 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 50 | 20 | 240 | 0.202 | 2.016 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 50 | 20 | 120 | 0.202 | 2.016 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 50 | 20 | 60 | 0.202 | 2.016 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 150 | 20 | 240 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 100 | 20 | 240 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 150 | 20 | 60 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 150 | 20 | 30 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 100 | 20 | 120 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 100 | 20 | 60 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 100 | 20 | 30 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |
| h4_usdt_depth_rv | mid_research | 150 | 20 | 120 | 0.175 | 1.753 | 46.1% | 60.10 | 2.484 | 0.0% |

## Read

- `mid_research` is only a signal-shape upper bound; it is not a feasible execution claim.
- `maker_light` and `taker_spread` are the main rows to inspect for small-account feasibility.
- The grid is exploratory and should be read with parameter-sensitivity, fold, and same-bar ambiguity columns next to PnL.
- A positive row in this short window is a candidate for next-window validation, not evidence of persistent alpha.

## Outputs

- `date/bonk_v6_episode_backtest_20260513_bullish_l2_basket_price_v1_trades.csv`
- `date/bonk_v6_episode_backtest_20260513_bullish_l2_basket_price_v1_daily.csv`
- `date/bonk_v6_episode_backtest_20260513_bullish_l2_basket_price_v1_summary.csv`
- `date/bonk_v6_episode_backtest_20260513_bullish_l2_basket_price_v1_completion.json`

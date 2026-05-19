# BONK V9 Order-Book Potential Filtering

Status: 2026-05-14T06:21:08Z. Run tag: `20260513_bullish_l2_basket_price_v1`. Output tag: `20260513_bullish_l2_basket_price_v1`.

Research infrastructure only: no trading advice, no execution recommendation, and no alpha claim.

## Scope

- Used existing V8 factor-panel data only; no new raw data pull.
- Rust is canonical for potential-state reconstruction, train-fitted filter parameters, movable anchors, long/short labels, after-cost backtests, negative controls, and reports.
- The model treats the order book as a compressed dynamic pressure field rather than as a flat feature table.
- Potential rows: `40230`. Filter rows: `23018`. Anchor fit rows: `60`. Trades: `52444`. Summary rows: `6912`.

## Resume Contract

- Manifest: `date/bonk_v9_orderbook_potential_filtering_20260513_bullish_l2_basket_price_v1_manifest.json`
- Checkpoint: `date/bonk_v9_orderbook_potential_filtering_20260513_bullish_l2_basket_price_v1_checkpoint.json`
- Steps are `potential_state -> filter_state -> episode_backtest -> spearman_stability -> docs`.

## Primary After-Cost Rows

| rank | side | execution | anchor | symbol | tp/sl/to | total $ | avg $/day | win | pf | tr/day | max DD | fold/freq |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| note | - | - | `no_positive_primary_target_frequency_rows` | - | - | 0.0000 | 0.0000 | - | - | - | - | V9 first pass found no positive primary rows after costs |
| 1 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 75/60/10 | -0.3830 | -0.0383 | 0.52 | 0.85 | 3.10 | 1.4035 | fold2/3 ok, target freq |
| 2 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 75/60/30 | -0.3830 | -0.0383 | 0.52 | 0.85 | 3.10 | 1.4035 | fold2/3 ok, target freq |
| 3 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 75/60/60 | -0.3830 | -0.0383 | 0.52 | 0.85 | 3.10 | 1.4035 | fold2/3 ok, target freq |
| 4 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 50/60/10 | -0.3845 | -0.0384 | 0.52 | 0.85 | 3.10 | 1.4035 | fold2/3 ok, target freq |
| 5 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 50/60/30 | -0.3845 | -0.0384 | 0.52 | 0.85 | 3.10 | 1.4035 | fold2/3 ok, target freq |
| 6 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 50/60/60 | -0.3845 | -0.0384 | 0.52 | 0.85 | 3.10 | 1.4035 | fold2/3 ok, target freq |
| 7 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 30/60/10 | -0.4409 | -0.0441 | 0.55 | 0.83 | 3.10 | 1.0543 | fold2/3 ok, target freq |
| 8 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 30/60/30 | -0.4409 | -0.0441 | 0.55 | 0.83 | 3.10 | 1.0543 | fold2/3 ok, target freq |
| 9 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 30/60/60 | -0.4409 | -0.0441 | 0.55 | 0.83 | 3.10 | 1.0543 | fold2/3 ok, target freq |
| 10 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 75/20/10 | -0.5445 | -0.0544 | 0.48 | 0.78 | 3.10 | 0.9728 | fold2/3 weak, target freq |
| 11 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 75/20/30 | -0.5445 | -0.0544 | 0.48 | 0.78 | 3.10 | 0.9728 | fold2/3 weak, target freq |
| 12 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 75/20/60 | -0.5445 | -0.0544 | 0.48 | 0.78 | 3.10 | 0.9728 | fold2/3 weak, target freq |
| 13 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 50/20/10 | -0.5459 | -0.0546 | 0.48 | 0.78 | 3.10 | 0.9728 | fold2/3 weak, target freq |
| 14 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 50/20/30 | -0.5459 | -0.0546 | 0.48 | 0.78 | 3.10 | 0.9728 | fold2/3 weak, target freq |
| 15 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 50/20/60 | -0.5459 | -0.0546 | 0.48 | 0.78 | 3.10 | 0.9728 | fold2/3 weak, target freq |
| 16 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 30/20/10 | -0.5999 | -0.0600 | 0.52 | 0.75 | 3.10 | 0.8097 | fold2/3 weak, target freq |
| 17 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 30/20/30 | -0.5999 | -0.0600 | 0.52 | 0.75 | 3.10 | 0.8097 | fold2/3 weak, target freq |
| 18 | short | taker_spread | `potential_barrier_break` | BONK1MUSDT | 30/20/60 | -0.5999 | -0.0600 | 0.52 | 0.75 | 3.10 | 0.8097 | fold2/3 weak, target freq |
| 19 | short | maker_light | `potential_barrier_break` | BONK1MUSDT | 75/60/10 | -0.6113 | -0.0611 | 0.52 | 0.78 | 3.10 | 1.4499 | fold2/3 ok, target freq |
| 20 | short | maker_light | `potential_barrier_break` | BONK1MUSDT | 75/60/30 | -0.6113 | -0.0611 | 0.52 | 0.78 | 3.10 | 1.4499 | fold2/3 ok, target freq |

## Diagnostics

- Validation passed: `true`; duplicate trade ids `0`, missing exits `0`, daily/trade PnL diff `0.00000000`, non-overlap violations `0`.
- Long trades: `30700`. Short trades: `21744`. Negative-control rows: `5832`. Spearman rows: `384`.
- Top validation Spearman: `BONK1MUSDC` `kalman_pressure_fixed` 30m fold2 = `-0.1103` over `3578` rows.

## Outputs

- potential state: `date/bonk_v9_potential_state_20260513_bullish_l2_basket_price_v1.csv`
- filter params: `date/bonk_v9_filter_params_20260513_bullish_l2_basket_price_v1.csv`
- filter state: `date/bonk_v9_filter_state_20260513_bullish_l2_basket_price_v1.csv`
- anchor candidates: `date/bonk_v9_anchor_candidates_20260513_bullish_l2_basket_price_v1.csv`
- trades: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_trades.csv`
- daily: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_daily.csv`
- summary: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_summary.csv`
- exit reasons: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_exit_reasons.csv`
- fold stability: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_fold_stability.csv`
- non-overlap: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_non_overlap.csv`
- parameter sensitivity: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_parameter_sensitivity.csv`
- single-day dependence: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_single_day_dependence.csv`
- failure diagnostics: `date/bonk_v9_long_short_episode_backtest_20260513_bullish_l2_basket_price_v1_failure_diagnostics.csv`
- negative controls: `date/bonk_v9_negative_controls_20260513_bullish_l2_basket_price_v1.csv`
- spearman stability: `date/bonk_v9_spearman_stability_20260513_bullish_l2_basket_price_v1.csv`
- completion: `date/bonk_v9_orderbook_potential_filtering_20260513_bullish_l2_basket_price_v1_completion.json`
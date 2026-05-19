# BONK V7 Short-Horizon Impulse Probe

Status: 2026-05-13T15:30:21Z. Run tag: `20260513_bullish_l2_basket_price_v1`. Output tag: `20260513_bullish_l2_basket_price_v1`.

Research diagnostic only: no trading advice, no execution plan, no sizing rule, and no alpha claim.

## Inputs And Outputs

- L2 state input: `data\bonk\v1\derived\bonk_cex_l2_state\bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet`
- No new data was downloaded.
- Factor tests: `date\bonk_v7_short_impulse_probe_20260513_bullish_l2_basket_price_v1_factor_tests.csv`
- Event summary: `date\bonk_v7_short_impulse_probe_20260513_bullish_l2_basket_price_v1_event_summary.csv`
- Daily summary: `date\bonk_v7_short_impulse_probe_20260513_bullish_l2_basket_price_v1_daily.csv`
- Event sample: `date\bonk_v7_short_impulse_probe_20260513_bullish_l2_basket_price_v1_event_sample.csv`
- Completion JSON: `date\bonk_v7_short_impulse_probe_20260513_bullish_l2_basket_price_v1_completion.json`

## Available 1m L2 Fields Used

- Depth: `depth_bid_notional_5_median`, `depth_ask_notional_5_median`, `depth_bid_notional_25_median`, `depth_ask_notional_25_median`.
- Spread and price: `spread_bps_median`, `mid_price_per_unit_close`, `snapshot_microprice_offset_bps_mean`.
- Flow/activity: `trade_count`, `trade_notional_quote_sum`, `reported_buy_amount`, `reported_sell_amount`, `trade_flow_imbalance`.

## Coverage

| symbol | rows | first | last | mid miss | spread miss |
| --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 20103 | 2026-04-29T00:00:00Z | 2026-05-12T23:59:00Z | 0.002 | 0.000 |
| BONK1MUSDT | 20127 | 2026-04-29T00:00:00Z | 2026-05-12T23:59:00Z | 0.000 | 0.000 |

## Method

- Builds exact 2m/5m lag deltas only when minute timestamps are continuous.
- Bullish impulse score combines ask-depth withdrawal, bid replenish, spread compression, positive microprice impulse, trade burst, and buy-flow impulse.
- Bearish/short mirror score combines bid-depth withdrawal, ask replenish, spread compression, negative microprice impulse via sell-flow pressure, and trade burst.
- Forward labels are exact 2m/5m close-to-close log returns from the same L2 mid close. This is a probe label, not a path-execution label.

## Suggested Core Metrics

- `trade_notional_burst_2m` and `trade_notional_burst_5m`: activity impulse; currently the cleanest single-family read.
- `ask_depth_withdrawal_5_2m/5m` plus `bid_replenish_5_2m/5m`: bullish liquidity transition candidate.
- `bid_depth_withdrawal_5_2m/5m` plus `ask_replenish_5_2m/5m`: bearish/short mirror candidate.
- `spread_compression_2m/5m`: use as a state qualifier, not a standalone direction feature.
- `microprice_impulse_2m/5m` and `microprice_down_impulse_2m/5m`: direction qualifier after depth changes.
- `long_impulse_score_2m/5m`, `short_impulse_score_2m/5m`, `net_impulse_score_2m/5m`: composite probe fields to freeze before exact-path validation.

## Event Score Summary

| symbol | side | lb | rows | cut | 2m mean | 2m pos | 5m mean | 5m pos | 5m down10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | long_impulse | 2m | 2011 | 1.083 | -0.022 | 49.1% | 0.833 | 50.1% | 29.9% |
| BONK1MUSDT | net_long_minus_short | 5m | 2013 | 1.506 | 0.553 | 51.3% | 0.764 | 50.6% | 31.9% |
| BONK1MUSDC | short_impulse | 2m | 2011 | 0.898 | 0.686 | 50.5% | 0.730 | 51.8% | 30.2% |
| BONK1MUSDC | long_impulse | 5m | 2010 | 1.053 | 0.375 | 50.5% | 0.405 | 51.1% | 31.0% |
| BONK1MUSDT | net_long_minus_short | 2m | 2013 | 1.642 | -0.370 | 49.3% | 0.333 | 51.3% | 30.0% |
| BONK1MUSDT | short_impulse | 5m | 2013 | 0.822 | -0.109 | 46.5% | 0.165 | 49.7% | 30.8% |
| BONK1MUSDC | net_long_minus_short | 2m | 2011 | 1.618 | -0.790 | 47.9% | 0.150 | 50.2% | 30.3% |
| BONK1MUSDT | long_impulse | 2m | 2013 | 0.881 | -0.030 | 49.6% | 0.037 | 50.0% | 31.1% |
| BONK1MUSDC | short_impulse | 5m | 2010 | 0.899 | -0.077 | 48.6% | 0.029 | 50.7% | 30.9% |
| BONK1MUSDT | long_impulse | 5m | 2013 | 0.856 | 0.328 | 49.3% | 0.023 | 48.5% | 33.0% |
| BONK1MUSDT | short_impulse | 2m | 2013 | 0.855 | 0.412 | 48.6% | -0.006 | 49.7% | 30.8% |
| BONK1MUSDC | net_long_minus_short | 5m | 2010 | 1.525 | 0.017 | 49.8% | -0.676 | 48.8% | 33.4% |

## Strongest Up-Read Buckets

| symbol | H | family | factor | bucket | rows | edge | mean | pos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 2m | trade_burst | trade_notional_burst_5m | high | 2001 | 0.575 | 0.703 | 50.4% |
| BONK1MUSDC | 2m | trade_burst | trade_notional_burst_2m | high | 2001 | 0.445 | 0.573 | 50.6% |
| BONK1MUSDT | 2m | net_score | net_impulse_score_5m | high | 2011 | 0.428 | 0.553 | 51.3% |
| BONK1MUSDT | 2m | ask_withdrawal | ask_depth_withdrawal_5_5m | high | 2010 | 0.357 | 0.483 | 50.5% |
| BONK1MUSDC | 2m | microprice_impulse | microprice_impulse_5m | high | 2004 | 0.350 | 0.478 | 49.3% |
| BONK1MUSDC | 2m | long_score | long_impulse_score_5m | high | 2004 | 0.246 | 0.374 | 50.5% |
| BONK1MUSDT | 2m | trade_burst | trade_notional_burst_5m | high | 2008 | 0.204 | 0.329 | 48.5% |
| BONK1MUSDT | 2m | long_score | long_impulse_score_5m | high | 2011 | 0.198 | 0.323 | 49.3% |
| BONK1MUSDT | 2m | microprice_impulse | microprice_impulse_5m | high | 2010 | 0.191 | 0.317 | 48.4% |
| BONK1MUSDC | 2m | spread_compression | spread_compression_5m | high | 2004 | 0.162 | 0.290 | 47.7% |
| BONK1MUSDT | 2m | bid_replenish | bid_replenish_5_5m | high | 2010 | 0.146 | 0.271 | 50.9% |
| BONK1MUSDT | 2m | trade_burst | trade_notional_burst_2m | high | 2009 | 0.145 | 0.270 | 48.7% |

## Strongest Down-Read Buckets

| symbol | H | family | factor | bucket | rows | edge | mean | down10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDT | 2m | sell_flow | trade_sell_flow_impulse_5m | high | 1944 | -0.547 | -0.422 | 18.9% |
| BONK1MUSDT | 2m | bid_withdrawal | bid_depth_withdrawal_5_5m | high | 2010 | -0.301 | -0.175 | 24.4% |
| BONK1MUSDT | 2m | short_score | short_impulse_score_5m | high | 2011 | -0.251 | -0.125 | 21.8% |
| BONK1MUSDC | 2m | short_score | short_impulse_score_5m | high | 2004 | -0.196 | -0.068 | 23.2% |
| BONK1MUSDC | 2m | spread_compression | spread_compression_2m | high | 2004 | -0.140 | -0.012 | 13.0% |
| BONK1MUSDT | 2m | spread_compression | spread_compression_5m | high | 2010 | -0.096 | 0.030 | 17.9% |
| BONK1MUSDT | 2m | ask_replenish | ask_replenish_5_5m | high | 2010 | -0.087 | 0.039 | 22.6% |
| BONK1MUSDT | 2m | microprice_down | microprice_down_impulse_5m | high | 2010 | -0.082 | 0.044 | 15.4% |
| BONK1MUSDC | 2m | ask_replenish | ask_replenish_5_5m | high | 2004 | -0.047 | 0.081 | 23.0% |
| BONK1MUSDT | 2m | bid_withdrawal | bid_depth_withdrawal_5_2m | high | 2011 | 0.018 | 0.143 | 22.9% |
| BONK1MUSDT | 2m | sell_flow | trade_sell_flow_impulse_2m | high | 4466 | 0.033 | 0.159 | 17.7% |
| BONK1MUSDC | 2m | bid_withdrawal | bid_depth_withdrawal_5_5m | high | 2004 | 0.054 | 0.182 | 23.9% |

## Read

The core V7 object is not a static depth-high state. It is a minute-to-minute transition: liquidity pull/replenish plus spread compression, microprice displacement, and trade burst. Treat any positive bucket as an impulse-shape candidate that still needs exact path labels, cost stress, and next-window validation.

## Next Step

Promote only the stable 2m/5m transition definitions into the canonical label-context panel, then rerun with timestamp-exact path labels and the V5 small-capital stress lens. Do not pull new data until the frozen V7 definitions survive this local-data retest.

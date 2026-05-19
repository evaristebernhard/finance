# BONK V3 Short-Horizon Label Feasibility Probe

- `run_tag`: `20260513_bullish_l2_basket_price_v1`
- Probe only: no trading rule, no threshold rule, no execution plan, no alpha claim.
- Derived from existing Bullish L2 minute state and Binance kline context; no raw data download.

## Outputs

- Label summary CSV: `date\bonk_v3_short_horizon_label_summary_20260513.csv`
- Factor tests CSV: `date\bonk_v3_short_horizon_factor_tests_20260513.csv`
- Summary JSON: `date\bonk_v3_short_horizon_probe_summary_20260513.json`
- L2 state input: `data\bonk\v1\derived\bonk_cex_l2_state\bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet`
- Price context input: `data\bonk\v1\derived\bonk_cex_price_context\bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet`

## Feasibility Read

- Derived label rows: `482760`.
- Label status: `feasible for 5m/15m/30m using existing minute L2 state; 20/30bps are the useful short barriers`.
- Residual context status: `residual returns are feasible because Binance context covers the same minute grid`.
- Short-horizon factor read: `100bps is too wide for 5m; use 20/30bps for short microstructure and keep 50/100bps as path-width diagnostics`.

## Label Summary

| symbol | horizon | barrier | ok | upper | lower | any hit | median ret bps | abs resid med bps | path width med bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDC | 5m | 20 | 20066 | 20.3% | 18.5% | 38.8% | 0.00 | 7.53 | 16.05 |
| BONK1MUSDC | 5m | 30 | 20066 | 10.3% | 9.3% | 19.5% | 0.00 | 7.53 | 16.05 |
| BONK1MUSDC | 5m | 50 | 20066 | 2.8% | 3.1% | 5.9% | 0.00 | 7.53 | 16.05 |
| BONK1MUSDC | 5m | 100 | 20066 | 0.2% | 0.4% | 0.6% | 0.00 | 7.53 | 16.05 |
| BONK1MUSDC | 15m | 20 | 20057 | 39.8% | 37.6% | 77.4% | 0.79 | 12.25 | 37.47 |
| BONK1MUSDC | 15m | 30 | 20057 | 28.0% | 26.3% | 54.3% | 0.79 | 12.25 | 37.47 |
| BONK1MUSDC | 15m | 50 | 20057 | 13.2% | 11.9% | 25.1% | 0.79 | 12.25 | 37.47 |
| BONK1MUSDC | 15m | 100 | 20057 | 2.1% | 2.0% | 4.1% | 0.79 | 12.25 | 37.47 |
| BONK1MUSDC | 30m | 20 | 20042 | 47.5% | 45.3% | 92.7% | 1.60 | 16.63 | 58.60 |
| BONK1MUSDC | 30m | 30 | 20042 | 40.1% | 37.2% | 77.2% | 1.60 | 16.63 | 58.60 |
| BONK1MUSDC | 30m | 50 | 20042 | 24.3% | 22.7% | 46.9% | 1.60 | 16.63 | 58.60 |
| BONK1MUSDC | 30m | 100 | 20042 | 6.3% | 5.9% | 12.3% | 1.60 | 16.63 | 58.60 |
| BONK1MUSDT | 5m | 20 | 20120 | 20.8% | 18.9% | 39.6% | 0.00 | 7.62 | 16.29 |
| BONK1MUSDT | 5m | 30 | 20120 | 10.6% | 9.5% | 20.1% | 0.00 | 7.62 | 16.29 |
| BONK1MUSDT | 5m | 50 | 20120 | 2.9% | 3.1% | 6.0% | 0.00 | 7.62 | 16.29 |
| BONK1MUSDT | 5m | 100 | 20120 | 0.2% | 0.4% | 0.6% | 0.00 | 7.62 | 16.29 |
| BONK1MUSDT | 15m | 20 | 20110 | 40.1% | 38.0% | 78.1% | 0.76 | 12.29 | 38.12 |
| BONK1MUSDT | 15m | 30 | 20110 | 28.4% | 26.6% | 55.1% | 0.76 | 12.29 | 38.12 |
| BONK1MUSDT | 15m | 50 | 20110 | 13.5% | 12.2% | 25.6% | 0.76 | 12.29 | 38.12 |
| BONK1MUSDT | 15m | 100 | 20110 | 2.1% | 2.1% | 4.1% | 0.76 | 12.29 | 38.12 |
| BONK1MUSDT | 30m | 20 | 20095 | 47.5% | 45.5% | 93.1% | 1.60 | 16.71 | 58.93 |
| BONK1MUSDT | 30m | 30 | 20095 | 40.4% | 37.5% | 78.0% | 1.60 | 16.71 | 58.93 |
| BONK1MUSDT | 30m | 50 | 20095 | 24.5% | 22.9% | 47.4% | 1.60 | 16.71 | 58.93 |
| BONK1MUSDT | 30m | 100 | 20095 | 6.4% | 6.1% | 12.5% | 1.60 | 16.71 | 58.93 |

## Top Short-Horizon Factor Deltas

Sorted by absolute upper-minus-lower edge, then residual-positive edge. These are diagnostics only.

| symbol | H | B | factor | bucket | rows | dir edge | resid-pos edge | median resid bps | path width bps |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDC | 5m | 20 | `spread_bps_last` | low | 6711 | -2.2% | -0.9% | -0.28 | 16.54 |
| BONK1MUSDT | 5m | 20 | `spread_bps_median` | high | 6718 | 1.6% | 0.7% | 0.12 | 15.35 |
| BONK1MUSDC | 5m | 20 | `spread_bps_median` | low | 6713 | -1.6% | -0.4% | -0.18 | 15.96 |
| BONK1MUSDC | 5m | 20 | `spread_bps_median` | high | 6691 | 1.4% | 0.2% | -0.01 | 14.51 |
| BONK1MUSDC | 5m | 20 | `spread_bps_last` | high | 6689 | 1.3% | 0.3% | 0.00 | 14.78 |
| BONK1MUSDC | 5m | 20 | `trade_count` | high | 6973 | -1.3% | 1.5% | 0.56 | 21.54 |
| BONK1MUSDT | 5m | 20 | `trade_count` | high | 6912 | -1.2% | 0.4% | 0.00 | 17.86 |
| BONK1MUSDC | 5m | 20 | `snapshot_count` | high | 7111 | -1.1% | 1.4% | 0.49 | 21.50 |
| BONK1MUSDT | 5m | 20 | `reported_buy_share` | high | 5259 | 1.1% | -1.8% | -0.51 | 16.93 |
| BONK1MUSDT | 5m | 20 | `trade_flow_imbalance` | high | 5259 | 1.1% | -1.8% | -0.51 | 16.93 |
| BONK1MUSDC | 5m | 20 | `top_depth_total_notional_median` | high | 6689 | 1.0% | -0.3% | -0.11 | 13.74 |
| BONK1MUSDC | 5m | 20 | `cross_venue_basis_bps` | high | 10495 | -1.0% | -0.3% | -0.11 | 16.08 |
| BONK1MUSDC | 5m | 20 | `trade_count` | low | 7048 | 0.9% | -0.6% | -0.12 | 12.76 |
| BONK1MUSDT | 5m | 20 | `cross_venue_microprice_disagreement_bps` | low | 6699 | -0.9% | 0.6% | 0.04 | 17.39 |
| BONK1MUSDT | 5m | 20 | `cross_venue_activity_ratio` | low | 6699 | -0.9% | 0.7% | 0.10 | 18.87 |
| BONK1MUSDT | 5m | 20 | `top_depth_total_notional_median` | low | 6707 | -0.8% | 0.4% | 0.02 | 20.41 |
| BONK1MUSDT | 5m | 20 | `trade_notional_quote_sum` | low | 6707 | -0.8% | -0.6% | -0.26 | 15.86 |
| BONK1MUSDC | 5m | 20 | `cross_venue_spread_diff_bps` | low | 7013 | -0.8% | -0.2% | -0.10 | 15.22 |
| BONK1MUSDT | 5m | 20 | `top_depth_total_notional_median` | high | 6707 | 0.8% | 0.0% | -0.06 | 13.87 |
| BONK1MUSDC | 5m | 20 | `cross_venue_microprice_disagreement_bps` | high | 6689 | -0.8% | 0.8% | 0.14 | 16.97 |

## Interpretation

Measured short labels support adding 5m/15m probes without more raw data. They mostly reframe the work: 20/30bps labels are suitable for fast microstructure decay checks, while 50/100bps labels quickly become sparse at 5m and are better read as movement/path-width diagnostics. Factor rankings should therefore be re-read by horizon and barrier instead of porting the 1h/4h candidate book directly.

Short-horizon labels change the factor picture only if the same feature families that looked useful at 1h/4h also show meaningful 5m/15m separation. In this probe the main difference is that 100bps is mostly too wide for 5m/15m, while 20/30bps labels are feasible and more informative for microstructure decay.

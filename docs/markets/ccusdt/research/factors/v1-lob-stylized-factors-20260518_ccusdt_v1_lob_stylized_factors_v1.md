# CCUSDT Classic LOB Stylized-Factor Diagnostics

Status: `20260518_ccusdt_v1_lob_stylized_factors_v1`.

Guardrail: `research_only_lob_stylized_factors_no_execution_recommendation_no_alpha_claim`.

This is an independent BTC-style LOB factor pass on CCUSDT. It does not attach the findings to the current TFI strategy branch, does not simulate queue-position execution, and does not make a trading recommendation.

## Factor Map

Let best ask/bid be $a_t,b_t$, mid be $m_t=(a_t+b_t)/2$, and cumulative quote depth to level $K$ be $D^a_{K,t},D^b_{K,t}$.

- Spread: $s_t=10^4(a_t-b_t)/m_t$.
- Depth imbalance: $I_{K,t}=(D^b_{K,t}-D^a_{K,t})/(D^b_{K,t}+D^a_{K,t})$.
- Microprice deviation: $10^4(MP_t-m_t)/m_t$, with $MP_t=(a_t q^b_{1,t}+b_t q^a_{1,t})/(q^b_{1,t}+q^a_{1,t})$.
- Liquidity cost: $LC^+_{\omega,t}=10^4(VWAP^+_{\omega,t}/m_t-1)$ for buying quote notional $\omega$; sell-side cost is symmetric.
- Shape: near-depth concentration, $D_5/D_{25}$, 25-level quote-depth slope per bps, and shallow-versus-deep imbalance drift $I_5-I_{25}$.
- Dynamic order flow: OFI/MLOFI, trade-flow imbalance, depletion, replenishment, cancellation-withdrawal, and liquidity-shock fields from the fixed event panel.

## Scope

- Snapshot source: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1\external\bullish_book_snapshot_25\symbol=CCUSDT`.
- Event panel source: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1\derived\ccusdt_v1_fixed_event_factor_panel\run_tag=20260517_ccusdt_fixed_factors_v3\symbol=CCUSDT`.
- Snapshot sample per day: `25000`.
- Event sample per day: `25000`.
- Time horizons: `1,10,60` seconds.
- Event horizons: `25` events.

## Static Book Shape

| date | rows | mid_distinct | quote_change_rate | median_spread_bps | p95_spread_bps | p05_top_depth_quote | median_depth25_quote | median_two_sided_lc_100_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-29 | 129026 | 861 | 0.0481 | 2.0104 | 4.0059 | 7.1607 | 6593.8916 | 3.8898 |
| 2026-04-30 | 149743 | 674 | 0.0378 | 2.6273 | 3.9732 | 11.8672 | 5722.9068 | 3.5994 |
| 2026-05-01 | 134839 | 533 | 0.0391 | 2.0050 | 4.0051 | 13.6397 | 7599.3792 | 3.1569 |
| 2026-05-02 | 120516 | 514 | 0.0426 | 2.6697 | 4.0274 | 11.4407 | 7951.8001 | 3.3462 |
| 2026-05-03 | 120333 | 278 | 0.0280 | 2.6720 | 4.0260 | 50.0452 | 8127.7476 | 2.6976 |
| 2026-05-04 | 147195 | 491 | 0.0319 | 2.0381 | 4.0573 | 11.5192 | 5421.4406 | 3.2466 |
| 2026-05-05 | 181529 | 666 | 0.0389 | 2.0257 | 4.0497 | 7.6775 | 6640.5427 | 3.3484 |
| 2026-05-06 | 139137 | 515 | 0.0338 | 2.0203 | 4.0409 | 7.6796 | 6353.0808 | 3.3606 |
| 2026-05-07 | 121891 | 484 | 0.0274 | 1.3699 | 4.0822 | 6.6756 | 3216.1580 | 3.3455 |
| 2026-05-08 | 124746 | 555 | 0.0323 | 2.0587 | 4.0961 | 8.5316 | 3840.7980 | 3.4965 |
| 2026-05-09 | 114784 | 1582 | 0.0782 | 1.9961 | 4.0464 | 3.6076 | 3350.2011 | 4.1833 |
| 2026-05-10 | 115248 | 1133 | 0.0547 | 1.9244 | 3.8590 | 4.1932 | 3738.7520 | 3.8348 |
| 2026-05-11 | 123086 | 1884 | 0.0728 | 1.9529 | 3.8737 | 5.5788 | 3843.3042 | 3.7437 |
| 2026-05-12 | 121545 | 1691 | 0.0606 | 1.8746 | 3.7351 | 1.9790 | 3128.7629 | 4.6677 |
| 2026-05-13 | 121064 | 892 | 0.0488 | 1.9541 | 3.8991 | 4.6897 | 3535.6758 | 3.6991 |
| 2026-05-14 | 123024 | 2490 | 0.0984 | 1.8996 | 3.6812 | 3.3761 | 2633.1069 | 6.0874 |
| 2026-05-15 | 130923 | 2495 | 0.0838 | 1.8517 | 3.6971 | 3.3184 | 2970.9319 | 5.3934 |

## Aggregate Read

- snapshot days: `17`
- snapshot rows: `2218629`
- median daily quote-change rate: `0.0426`
- median daily median spread bps: `2.0050`
- median daily p95 spread bps: `4.0059`
- median daily p05 top depth quote: `7.1607`
- median daily median 25-level depth quote: `3843.3042`
- median daily near-share $D_5/D_{25}$: `0.1927`
- median daily two-sided LC 100 quote bps: `3.5994`

## Main Findings

1. CCUSDT is a sparse-moving snapshot book: median daily quote-change rate is `0.0426`, while the median daily median spread is `2.0050` bps and median p95 spread is `4.0059` bps.
2. Top-of-book depth is thin relative to the 25-level book: median daily p05 top depth is `7.1607` quote, but median 25-level depth is `3843.3042` quote. The median two-sided liquidity cost for 100 quote notional is `3.5994` bps.
3. Static BTC-style book-shape factors are weak as standalone forward predictors. The best snapshot row is `obi_1` on `fwd_time_60s_bps` with Spearman `0.0366`, AUC `0.5094`, top-bottom `1.4401` bps, and past/forward IC ratio `6.1900`.
4. Dynamic order-flow is the strongest LOB family: `trade_flow_imbalance` on `fwd_event_25_bps` has IC `0.2768`, AUC `0.6217`, and top-bottom `2.8332` bps. On `fwd_time_10s_bps`, its IC is `0.2595`, but the past/forward IC ratio is `2.7774`, so a large part of the signal is recent-flow persistence rather than a clean innovation.
5. MLOFI is a secondary family, not a replacement for trade flow: `mlofi_roll10_l1` on `fwd_time_10s_bps` has IC `0.0894`. OBI/microprice/shape variables are highly redundant and should be compressed before any future model.

## Snapshot Factor Diagnostics

| target | feature | family | rows | spearman | auc | top_bottom_bps | daily_sign_rate | past_ic | past_over_forward_abs_ratio | diagnostic_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fwd_time_60s_bps | obi_1 | imbalance | 424739 | 0.0366 | 0.5094 | 1.4401 | 0.9412 | -0.2265 | 6.1900 | 9.1487 |
| fwd_time_10s_bps | obi_5 | imbalance | 424952 | -0.0503 | 0.4662 | -0.1479 | 0.8824 | -0.2686 | 5.3406 | 8.5835 |
| fwd_time_10s_bps | obi_10 | imbalance | 424952 | -0.0482 | 0.4675 | -0.0135 | 0.9412 | -0.2619 | 5.4348 | 8.5752 |
| fwd_time_10s_bps | obi_5_minus_25 | imbalance_shape | 424952 | -0.0489 | 0.4667 | -0.1544 | 0.8824 | -0.2462 | 5.0343 | 8.4783 |
| fwd_time_10s_bps | obi_25 | imbalance | 424952 | -0.0466 | 0.4719 | 0.0447 | 0.9412 | -0.2530 | 5.4302 | 8.4772 |
| fwd_time_10s_bps | depth_slope_imbalance | depth_shape | 424952 | -0.0465 | 0.4719 | 0.0523 | 0.9412 | -0.2528 | 5.4392 | 8.4769 |
| fwd_time_60s_bps | microprice_dev_bps | microprice | 424739 | 0.0308 | 0.5062 | 1.3846 | 0.8824 | -0.1800 | 5.8521 | 8.3067 |
| fwd_time_60s_bps | ask_concentration_1_25 | depth_shape | 424739 | -0.0306 | 0.4895 | -1.2610 | 0.8824 | 0.1597 | 5.2149 | 8.1232 |
| fwd_time_60s_bps | bid_concentration_1_25 | depth_shape | 424739 | 0.0308 | 0.5035 | 1.1319 | 0.8824 | -0.1795 | 5.8317 | 8.0333 |
| fwd_time_1s_bps | obi_5 | imbalance | 424991 | -0.0354 | 0.4627 | -0.0177 | 0.8824 | -0.1480 | 4.1745 | 7.2650 |
| fwd_time_1s_bps | obi_10 | imbalance | 424991 | -0.0352 | 0.4632 | 0.0266 | 0.8824 | -0.1446 | 4.1095 | 7.2540 |
| fwd_time_1s_bps | depth_slope_imbalance | depth_shape | 424991 | -0.0340 | 0.4669 | 0.0614 | 0.8824 | -0.1405 | 4.1298 | 7.1945 |
| fwd_time_1s_bps | obi_25 | imbalance | 424991 | -0.0340 | 0.4669 | 0.0626 | 0.8824 | -0.1406 | 4.1346 | 7.1939 |
| fwd_time_1s_bps | obi_5_minus_25 | imbalance_shape | 424991 | -0.0308 | 0.4696 | -0.0676 | 0.8824 | -0.1316 | 4.2707 | 6.9452 |
| fwd_time_10s_bps | sell_lc_100_bps | liquidity_cost | 418881 | 0.0303 | 0.5452 | 0.0439 | 0.7059 | 0.1720 | 5.6676 | 6.3628 |
| fwd_time_60s_bps | ask_slope_quote_per_bps | depth_shape | 424739 | -0.0168 | 0.4695 | -0.9881 | 0.7647 | 0.0885 | 5.2701 | 6.1552 |
| fwd_time_10s_bps | sell_lc_25_bps | liquidity_cost | 424949 | 0.0294 | 0.5561 | -0.0033 | 0.6471 | 0.1648 | 5.6129 | 6.0363 |
| fwd_time_60s_bps | buy_lc_100_bps | liquidity_cost | 419814 | 0.0170 | 0.5210 | 0.5303 | 0.7647 | -0.2297 | 13.4981 | 5.8828 |
| fwd_time_60s_bps | buy_lc_25_bps | liquidity_cost | 424735 | 0.0118 | 0.5223 | 0.8564 | 0.7647 | -0.2328 | 19.7147 | 5.8032 |
| fwd_time_60s_bps | buy_lc_5_bps | liquidity_cost | 424739 | 0.0120 | 0.5202 | 0.7930 | 0.7647 | -0.0868 | 7.2629 | 5.7344 |
| fwd_time_10s_bps | two_sided_lc_25_bps | liquidity_cost | 424945 | 0.0090 | 0.5670 | 0.0069 | 0.8235 | 0.0045 | 0.5000 | 5.3799 |
| fwd_time_1s_bps | sell_lc_25_bps | liquidity_cost | 424988 | 0.0177 | 0.5735 | -0.0141 | 0.6471 | 0.0956 | 5.3871 | 5.2567 |
| fwd_time_10s_bps | bid_slope_quote_per_bps | depth_shape | 424952 | -0.0245 | 0.4460 | 0.0535 | 0.6471 | -0.0901 | 3.6795 | 5.2475 |
| fwd_time_10s_bps | two_sided_lc_100_bps | liquidity_cost | 414885 | 0.0081 | 0.5520 | 0.0119 | 0.8235 | 0.0073 | 0.8954 | 5.1938 |
| fwd_time_1s_bps | buy_lc_5_bps | liquidity_cost | 424991 | 0.0072 | 0.5458 | 0.0731 | 0.8235 | -0.0492 | 6.8206 | 5.1340 |
| fwd_time_1s_bps | two_sided_lc_25_bps | liquidity_cost | 424984 | 0.0056 | 0.5932 | 0.0182 | 0.7647 | -0.0009 | 0.1562 | 5.0312 |
| fwd_time_60s_bps | obi_10 | imbalance | 424739 | 0.0142 | 0.4954 | 0.5779 | 0.6471 | -0.3549 | 25.0651 | 4.9460 |
| fwd_time_60s_bps | depth_slope_imbalance | depth_shape | 424739 | 0.0115 | 0.4969 | 0.7811 | 0.6471 | -0.3408 | 29.5502 | 4.9389 |
| fwd_time_60s_bps | obi_25 | imbalance | 424739 | 0.0114 | 0.4969 | 0.6976 | 0.6471 | -0.3409 | 29.8949 | 4.8451 |
| fwd_time_60s_bps | obi_5 | imbalance | 424739 | 0.0127 | 0.4946 | 0.2468 | 0.7059 | -0.3630 | 28.6073 | 4.7913 |

## Event-Panel Dynamic Diagnostics

| target | feature | family | rows | spearman | auc | top_bottom_bps | daily_sign_rate | past_ic | past_over_forward_abs_ratio | diagnostic_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fwd_event_25_bps | trade_flow_imbalance | trade_flow | 48154 | 0.2768 | 0.6217 | 2.8332 | 1.0000 |  |  | 30.9501 |
| fwd_time_10s_bps | trade_flow_imbalance | trade_flow | 48160 | 0.2595 | 0.6090 | 2.9024 | 1.0000 | 0.7208 | 2.7774 | 29.5352 |
| fwd_time_60s_bps | trade_flow_imbalance | trade_flow | 48111 | 0.1463 | 0.5671 | 5.8173 | 1.0000 | 0.4589 | 3.1372 | 23.0566 |
| fwd_time_10s_bps | mlofi_roll10_l1 | mlofi | 424950 | 0.0894 | 0.5452 | 1.1523 | 1.0000 | 0.3225 | 3.6070 | 13.6675 |
| fwd_event_25_bps | mlofi_roll10_l1 | mlofi | 424932 | 0.0866 | 0.5431 | 1.1505 | 1.0000 |  |  | 13.4198 |
| fwd_time_10s_bps | mlofi_roll10_l25 | mlofi | 424950 | 0.0790 | 0.5359 | 1.1719 | 1.0000 | 0.4442 | 5.6247 | 12.7773 |
| fwd_event_25_bps | mlofi_roll10_l25 | mlofi | 424932 | 0.0788 | 0.5339 | 1.1474 | 1.0000 |  |  | 12.7263 |
| fwd_event_25_bps | mlofi_roll10_l5 | mlofi | 424932 | 0.0769 | 0.5426 | 0.9996 | 0.9412 |  |  | 12.1985 |
| fwd_time_10s_bps | mlofi_roll10_l5 | mlofi | 424950 | 0.0757 | 0.5438 | 1.0367 | 0.9412 | 0.4658 | 6.1499 | 12.1517 |
| fwd_time_60s_bps | mlofi_roll10_l1 | mlofi | 424715 | 0.0586 | 0.5262 | 1.6615 | 1.0000 | -0.0022 | 0.0372 | 11.5567 |
| fwd_event_25_bps | trade_arrival_alignment | trade_flow | 48154 | 0.1031 | 0.5589 | 0.9664 |  |  |  | 9.6867 |
| fwd_time_1s_bps | trade_flow_imbalance | trade_flow | 48166 | 0.0704 | 0.5157 | 0.6793 | 0.6471 | 0.6993 | 9.9265 | 9.6759 |
| fwd_time_10s_bps | queue_imbalance_5 | imbalance | 424950 | -0.0572 | 0.4636 | -0.2037 | 0.9412 | -0.2874 | 5.0249 | 9.4859 |
| fwd_event_25_bps | queue_imbalance_5 | imbalance | 424932 | -0.0558 | 0.4642 | -0.0942 | 0.9412 |  |  | 9.2668 |
| fwd_time_60s_bps | queue_imbalance_1 | imbalance | 424715 | 0.0346 | 0.5086 | 1.5435 | 0.9412 | -0.2233 | 6.4594 | 9.0838 |
| fwd_time_60s_bps | mlofi_roll10_l25 | mlofi | 424715 | 0.0380 | 0.5110 | 1.4769 | 0.8824 | 0.1783 | 4.6861 | 9.0207 |
| fwd_time_10s_bps | queue_imbalance_25 | imbalance | 424950 | -0.0530 | 0.4691 | 0.0318 | 0.9412 | -0.2707 | 5.1045 | 8.9795 |
| fwd_event_25_bps | queue_imbalance_25 | imbalance | 424932 | -0.0516 | 0.4698 | 0.1342 | 0.9412 |  |  | 8.9657 |
| fwd_time_60s_bps | microprice_dev_bps | microprice | 424715 | 0.0276 | 0.5048 | 1.3960 | 1.0000 | -0.1794 | 6.4999 | 8.6417 |
| fwd_time_10s_bps | trade_arrival_alignment | trade_flow | 48160 | 0.0899 | 0.5555 | 0.7688 |  | 0.2956 | 3.2895 | 8.4019 |
| fwd_time_1s_bps | mlofi_roll10_l1 | mlofi | 424995 | 0.0396 | 0.5279 | 0.2138 | 0.9412 | 0.3355 | 8.4753 | 8.3096 |
| fwd_time_60s_bps | ofi_l1_depth_norm | ofi | 424710 | 0.0306 | 0.5128 | 0.4632 | 1.0000 | -0.1539 | 5.0253 | 8.0152 |
| fwd_time_1s_bps | queue_imbalance_5 | imbalance | 424995 | -0.0372 | 0.4660 | -0.0207 | 1.0000 | -0.1697 | 4.5607 | 7.9967 |
| fwd_time_1s_bps | queue_imbalance_25 | imbalance | 424995 | -0.0362 | 0.4682 | 0.0623 | 1.0000 | -0.1613 | 4.4591 | 7.9557 |
| fwd_time_10s_bps | ofi_l1_depth_norm | ofi | 424945 | 0.0288 | 0.5098 | 0.3226 | 1.0000 | -0.0257 | 0.8919 | 7.7035 |
| fwd_time_60s_bps | mlofi_roll10_l5 | mlofi | 424715 | 0.0286 | 0.5151 | 1.2845 | 0.7647 | 0.2752 | 9.6267 | 7.5162 |
| fwd_event_25_bps | ofi_l1_depth_norm | ofi | 424927 | 0.0250 | 0.5086 | 0.3085 | 1.0000 |  |  | 7.3778 |
| fwd_time_1s_bps | mlofi_roll10_l25 | mlofi | 424995 | 0.0291 | 0.5167 | 0.2403 | 0.8235 | 0.4293 | 14.7337 | 6.8227 |
| fwd_time_60s_bps | trade_arrival_alignment | trade_flow | 48111 | 0.0482 | 0.5219 | 2.0040 |  | 0.1812 | 3.7622 | 6.0323 |
| fwd_time_1s_bps | ofi_l1_depth_norm | ofi | 424990 | 0.0184 | 0.5053 | 0.0440 | 0.8824 | 0.1555 | 8.4670 | 5.9672 |

## Factor Redundancy

| panel | feature_left | feature_right | spearman_corr | abs_corr |
| --- | --- | --- | --- | --- |
| snapshot_25 | depth_slope_imbalance | obi_25 | 1.0000 | 1.0000 |
| snapshot_25 | obi_5 | obi_10 | 0.9843 | 0.9843 |
| snapshot_25 | obi_10 | obi_25 | 0.9742 | 0.9742 |
| snapshot_25 | depth_slope_imbalance | obi_10 | 0.9741 | 0.9741 |
| snapshot_25 | sell_lc_25_bps | sell_lc_100_bps | 0.9635 | 0.9635 |
| snapshot_25 | buy_lc_25_bps | buy_lc_100_bps | 0.9621 | 0.9621 |
| snapshot_25 | obi_5 | obi_5_minus_25 | 0.9619 | 0.9619 |
| snapshot_25 | obi_5 | obi_25 | 0.9561 | 0.9561 |
| snapshot_25 | depth_slope_imbalance | obi_5 | 0.9561 | 0.9561 |
| event_panel | queue_imbalance_5 | queue_imbalance_25 | 0.9544 | 0.9544 |
| snapshot_25 | depth25_quote | ask_slope_quote_per_bps | 0.9388 | 0.9388 |
| snapshot_25 | sell_lc_5_bps | two_sided_lc_5_bps | 0.9359 | 0.9359 |
| snapshot_25 | buy_lc_5_bps | two_sided_lc_5_bps | 0.9329 | 0.9329 |
| snapshot_25 | two_sided_lc_25_bps | two_sided_lc_100_bps | 0.9306 | 0.9306 |
| snapshot_25 | depth25_quote | bid_slope_quote_per_bps | 0.9301 | 0.9301 |
| snapshot_25 | obi_10 | obi_5_minus_25 | 0.9289 | 0.9289 |
| snapshot_25 | spread_bps | two_sided_lc_5_bps | 0.9276 | 0.9276 |
| event_panel | microprice_dev_bps | queue_imbalance_1 | 0.9054 | 0.9054 |
| snapshot_25 | obi_1 | microprice_dev_bps | 0.9049 | 0.9049 |
| snapshot_25 | spread_bps | sell_lc_5_bps | 0.8789 | 0.8789 |

## Current Read

- This pass is descriptive and diagnostic. A high IC/top-bottom row means the factor is worth understanding; it is not an executable edge by itself.
- The most relevant negative-control column is `past_over_forward_abs_ratio`: values above `1` mean the factor explains recent past movement at least as strongly as future movement.
- Static book-shape factors should be interpreted as venue-state variables. They can condition spread/depth/regime, but they should not be forced into the TFI micro-structure found earlier.
- Dynamic OFI/MLOFI/trade-flow rows overlap conceptually with the earlier event-factor sweep, but this report treats them as a separate LOB-stylized-fact block.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_lob_stylized_snapshot_daily_20260518_ccusdt_v1_lob_stylized_factors_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_lob_stylized_snapshot_scorecard_20260518_ccusdt_v1_lob_stylized_factors_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_lob_stylized_event_scorecard_20260518_ccusdt_v1_lob_stylized_factors_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_lob_stylized_factor_corr_20260518_ccusdt_v1_lob_stylized_factors_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_lob_stylized_summary_20260518_ccusdt_v1_lob_stylized_factors_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_lob_stylized_factors.py
```

## Reference

- Schnaubelt, Rende, and Krauss, `Testing Stylized Facts of Bitcoin Limit Order Books`, Journal of Risk and Financial Management, 2019: https://www.mdpi.com/1911-8074/12/1/25

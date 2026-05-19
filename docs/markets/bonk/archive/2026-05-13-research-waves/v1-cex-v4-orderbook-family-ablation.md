# BONK V4 Orderbook Feature-Family Ablation

Status: 2026-05-13. `run_tag=20260513_bullish_l2_basket_price_v1`.

This is a controlled research diagnostic. It is not a trading rule, execution plan, sizing rule, or alpha claim.

## Outputs

```text
date\bonk_v4_orderbook_family_ablation_20260513_bullish_l2_basket_price_v1_gate_tests.csv
date\bonk_v4_orderbook_family_ablation_20260513_bullish_l2_basket_price_v1_model_metrics.csv
date\bonk_v4_orderbook_family_ablation_20260513_bullish_l2_basket_price_v1_model_deltas.csv
date\bonk_v4_orderbook_family_ablation_20260513_bullish_l2_basket_price_v1_family_summary.csv
date\bonk_v4_orderbook_family_ablation_20260513_bullish_l2_basket_price_v1_completion.json
```

## Method

- Primary scope: `BONK1MUSDC` and `BONK1MUSDT`, H1/H4, `100 bps`, `label_status=ok`.
- Short-horizon scope, where feasible: 5m/15m/30m at 20/30 bps, derived from the existing minute L2 state and Binance context.
- Bucket gates fit low/high tertiles on the train side of each fold, choose the best train bucket inside a family, then apply the frozen cut to validation.
- Models are shallow diagnostics: L2 logistic and depth-2 tree. Every orderbook family model is `context + family` and is compared against the same `context_only` model.
- Main model target for the family ranking is residual-positive on stride non-overlap rows in fold2/fold3.

## Family Ranking After Context Controls

| rank_after_context | family | model_proper_win_rate | model_median_delta_brier | model_median_delta_log_loss | model_median_delta_top_target_lift | primary_gate_median_resid_edge | primary_gate_median_lower_edge | family_score_after_context |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cross_venue | 0.5000 | -0.0000 | -0.0000 | 0.0000 | -0.0210 | 0.0074 | 0.1729 |
| 2 | activity | 0.3750 | 0.0000 | 0.0000 | 0.0000 | 0.0231 | -0.0092 | 0.1336 |
| 3 | microprice | 0.3750 | -0.0000 | 0.0000 | 0.0000 | 0.0230 | -0.0225 | 0.1335 |
| 4 | spread_liquidity | 0.3750 | 0.0000 | 0.0000 | 0.0000 | -0.0083 | -0.0073 | 0.1304 |
| 5 | imbalance | 0.3125 | 0.0000 | 0.0000 | 0.0000 | 0.0105 | -0.0033 | 0.1104 |
| 6 | combined | 0.1875 | 0.0032 | 0.0063 | 0.0000 | -0.0327 | -0.0479 | -0.2543 |

## Main Read

The strongest single orderbook family after context controls is `cross_venue`.

It ranks first because its context-plus-family models have proper-score win rate `50.0%`, median delta brier `-0.0000`, and median top-target lift delta `0.0%` on fold2/fold3 stride rows.

The combined orderbook set is a useful ceiling check, but it should not be read as a cleaner explanation by itself: proper-score win rate `18.8%`, median delta brier `0.0032`.

## Fold2/Fold3 Model Deltas

| fold | symbol | horizon_label | model_kind | family | proper_score_pass | delta_log_loss | delta_brier | delta_auc | delta_top_target_lift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | BONK1MUSDC | H1 | logistic_l2 | activity | no | 0.0164 | 0.0063 | -0.0311 | 0.0000 |
| fold3 | BONK1MUSDC | H1 | logistic_l2 | activity | yes | -0.0012 | -0.0010 | 0.0401 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | logistic_l2 | combined | no | 0.0631 | 0.0281 | -0.0656 | -0.1667 |
| fold3 | BONK1MUSDC | H1 | logistic_l2 | combined | no | 0.0126 | 0.0045 | 0.0324 | -0.0667 |
| fold2 | BONK1MUSDC | H1 | logistic_l2 | cross_venue | no | 0.0180 | 0.0111 | -0.0545 | -0.0833 |
| fold3 | BONK1MUSDC | H1 | logistic_l2 | cross_venue | no | 0.0085 | 0.0039 | -0.0077 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | logistic_l2 | imbalance | no | 0.0049 | 0.0024 | 0.0011 | 0.0000 |
| fold3 | BONK1MUSDC | H1 | logistic_l2 | imbalance | yes | -0.0017 | -0.0006 | 0.0093 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | logistic_l2 | microprice | yes | -0.0086 | -0.0027 | 0.0133 | -0.0833 |
| fold3 | BONK1MUSDC | H1 | logistic_l2 | microprice | no | 0.0069 | 0.0028 | -0.0031 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | logistic_l2 | spread_liquidity | no | 0.0098 | 0.0069 | -0.0111 | 0.0000 |
| fold3 | BONK1MUSDC | H1 | logistic_l2 | spread_liquidity | yes | -0.0081 | -0.0043 | 0.0370 | -0.0667 |
| fold2 | BONK1MUSDC | H1 | tree_depth2 | activity | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H1 | tree_depth2 | activity | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | tree_depth2 | combined | yes | -0.0448 | -0.0192 | 0.0545 | 0.1667 |
| fold3 | BONK1MUSDC | H1 | tree_depth2 | combined | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | tree_depth2 | cross_venue | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H1 | tree_depth2 | cross_venue | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | tree_depth2 | imbalance | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H1 | tree_depth2 | imbalance | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | tree_depth2 | microprice | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H1 | tree_depth2 | microprice | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H1 | tree_depth2 | spread_liquidity | yes | -0.0448 | -0.0192 | 0.0545 | 0.1667 |
| fold3 | BONK1MUSDC | H1 | tree_depth2 | spread_liquidity | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDT | H1 | logistic_l2 | activity | no | 0.0359 | 0.0130 | -0.0467 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | logistic_l2 | activity | no | 0.0135 | 0.0061 | -0.0139 | -0.0667 |
| fold2 | BONK1MUSDT | H1 | logistic_l2 | combined | no | 0.0842 | 0.0320 | -0.0845 | -0.0833 |
| fold3 | BONK1MUSDT | H1 | logistic_l2 | combined | no | 0.0150 | 0.0058 | -0.0046 | -0.2667 |
| fold2 | BONK1MUSDT | H1 | logistic_l2 | cross_venue | no | 0.0145 | 0.0080 | -0.0501 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | logistic_l2 | cross_venue | no | 0.0177 | 0.0085 | -0.0457 | -0.1333 |
| fold2 | BONK1MUSDT | H1 | logistic_l2 | imbalance | yes | -0.0007 | -0.0004 | 0.0167 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | logistic_l2 | imbalance | no | 0.0083 | 0.0039 | -0.0379 | -0.0667 |
| fold2 | BONK1MUSDT | H1 | logistic_l2 | microprice | no | 0.0057 | 0.0020 | -0.0122 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | logistic_l2 | microprice | yes | -0.0034 | -0.0020 | 0.0186 | 0.0000 |
| fold2 | BONK1MUSDT | H1 | logistic_l2 | spread_liquidity | no | 0.0145 | 0.0057 | 0.0022 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | logistic_l2 | spread_liquidity | yes | -0.0119 | -0.0061 | 0.0286 | -0.1333 |
| fold2 | BONK1MUSDT | H1 | tree_depth2 | activity | no | 0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | tree_depth2 | activity | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDT | H1 | tree_depth2 | combined | no | -0.0006 | 0.0019 | -0.0178 | 0.0833 |
| fold3 | BONK1MUSDT | H1 | tree_depth2 | combined | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDT | H1 | tree_depth2 | cross_venue | yes | -0.0450 | -0.0193 | 0.0545 | 0.1667 |
| fold3 | BONK1MUSDT | H1 | tree_depth2 | cross_venue | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDT | H1 | tree_depth2 | imbalance | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | tree_depth2 | imbalance | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDT | H1 | tree_depth2 | microprice | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDT | H1 | tree_depth2 | microprice | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDT | H1 | tree_depth2 | spread_liquidity | no | -0.0006 | 0.0019 | -0.0178 | 0.0833 |
| fold3 | BONK1MUSDT | H1 | tree_depth2 | spread_liquidity | no | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | logistic_l2 | activity | yes | -0.0152 | -0.0019 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | logistic_l2 | activity | no | 0.0045 | 0.0004 | -0.0130 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | logistic_l2 | combined | no | 0.1846 | 0.0622 | -0.0400 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | logistic_l2 | combined | no | 0.0599 | 0.0222 | 0.0390 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | logistic_l2 | cross_venue | yes | -0.0393 | -0.0031 | -0.0200 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | logistic_l2 | cross_venue | yes | -0.0069 | -0.0012 | 0.0390 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | logistic_l2 | imbalance | no | -0.0107 | 0.0005 | -0.0200 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | logistic_l2 | imbalance | no | 0.0003 | 0.0008 | 0.0130 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | logistic_l2 | microprice | no | 0.0019 | -0.0027 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | logistic_l2 | microprice | no | 0.0001 | -0.0001 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | logistic_l2 | spread_liquidity | no | 0.1712 | 0.0487 | -0.0400 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | logistic_l2 | spread_liquidity | no | 0.0487 | 0.0159 | 0.0130 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | tree_depth2 | activity | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | tree_depth2 | activity | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | tree_depth2 | combined | no | 0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | tree_depth2 | combined | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | tree_depth2 | cross_venue | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | tree_depth2 | cross_venue | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | tree_depth2 | imbalance | no | -0.0000 | 0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | tree_depth2 | imbalance | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | tree_depth2 | microprice | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | tree_depth2 | microprice | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDC | H4 | tree_depth2 | spread_liquidity | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold3 | BONK1MUSDC | H4 | tree_depth2 | spread_liquidity | yes | -0.0000 | -0.0000 | 0.0000 | 0.0000 |
| fold2 | BONK1MUSDT | H4 | logistic_l2 | activity | no | 0.0154 | 0.0026 | -0.0800 | 0.0000 |
| fold3 | BONK1MUSDT | H4 | logistic_l2 | activity | yes | -0.0584 | -0.0194 | 0.0417 | 0.2500 |
| fold2 | BONK1MUSDT | H4 | logistic_l2 | combined | no | 0.2413 | 0.0742 | -0.1600 | 0.0000 |
| fold3 | BONK1MUSDT | H4 | logistic_l2 | combined | no | 0.0166 | 0.0096 | 0.0972 | 0.2500 |
| fold2 | BONK1MUSDT | H4 | logistic_l2 | cross_venue | yes | -0.0089 | -0.0032 | 0.0200 | 0.3333 |
| fold3 | BONK1MUSDT | H4 | logistic_l2 | cross_venue | yes | -0.0198 | -0.0071 | 0.0694 | 0.2500 |
| fold2 | BONK1MUSDT | H4 | logistic_l2 | imbalance | no | 0.0147 | 0.0051 | -0.0200 | 0.0000 |
| fold3 | BONK1MUSDT | H4 | logistic_l2 | imbalance | no | 0.0072 | 0.0031 | -0.0278 | 0.0000 |

## Train-Only Gate Read

| fold | symbol | horizon_label | family | feature | side | val_selected_rows | val_selected_share | edge_residual_positive | edge_lower | median_future_resid_edge_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | BONK1MUSDC | H1 | activity | trade_notional_quote_sum | high | 1656 | 0.4614 | -0.0111 | 0.0186 | -1.1228 |
| fold2 | BONK1MUSDC | H1 | combined | depth_x_low_rv_proxy AND cross_venue_basis_bps AND wobi25_mean | high AND low AND low | 10 | 0.0028 | 0.1363 | -0.1867 | 22.1126 |
| fold2 | BONK1MUSDC | H1 | context_only | ctx_bonk_beta_sol_240m | low | 820 | 0.2285 | 0.0595 | 0.0036 | 10.9988 |
| fold2 | BONK1MUSDC | H1 | cross_venue | cross_venue_basis_bps | low | 164 | 0.0457 | -0.0210 | -0.0708 | -1.3443 |
| fold2 | BONK1MUSDC | H1 | imbalance | wobi25_mean | low | 1451 | 0.4043 | -0.0185 | 0.0173 | -2.8322 |
| fold2 | BONK1MUSDC | H1 | microprice | abs_snapshot_microprice_offset_bps_mean | high | 623 | 0.1736 | 0.0399 | -0.0615 | 3.6504 |
| fold2 | BONK1MUSDC | H1 | spread_liquidity | depth_x_low_rv_proxy | high | 162 | 0.0451 | 0.1894 | -0.1126 | 17.7574 |
| fold3 | BONK1MUSDC | H1 | activity | book_ticker_count | low | 1829 | 0.4239 | -0.0393 | 0.0102 | -3.1463 |
| fold3 | BONK1MUSDC | H1 | combined | depth_x_low_rv_proxy AND abs_cross_venue_basis_bps AND wobi5_minus_wobi25 | high AND high AND high | 96 | 0.0222 | -0.0985 | -0.0479 | -10.5657 |
| fold3 | BONK1MUSDC | H1 | context_only | ctx_bonk_beta_sol_240m | low | 2346 | 0.5437 | 0.0634 | -0.0981 | 5.3903 |
| fold3 | BONK1MUSDC | H1 | cross_venue | abs_cross_venue_basis_bps | high | 1204 | 0.2790 | -0.0685 | 0.0642 | -7.7909 |
| fold3 | BONK1MUSDC | H1 | imbalance | wobi5_minus_wobi25 | high | 1661 | 0.3849 | -0.0049 | -0.0033 | 0.4856 |
| fold3 | BONK1MUSDC | H1 | microprice | abs_microprice_offset_bps_mean | high | 980 | 0.2271 | -0.0008 | -0.0241 | 0.5669 |
| fold3 | BONK1MUSDC | H1 | spread_liquidity | depth_x_low_rv_proxy | high | 1312 | 0.3041 | 0.0133 | -0.0880 | 2.2671 |
| fold2 | BONK1MUSDT | H1 | activity | snapshot_count | low | 1503 | 0.4188 | 0.0243 | -0.0352 | 2.2135 |
| fold2 | BONK1MUSDT | H1 | combined | snapshot_spread_bps_median AND abs_cross_venue_spread_diff_bps AND snapshot_count | high AND high AND low | 0 | 0.0000 | n/a | n/a | n/a |
| fold2 | BONK1MUSDT | H1 | context_only | ctx_bonk_beta_sol_240m | low | 813 | 0.2265 | 0.0684 | 0.0005 | 11.7416 |
| fold2 | BONK1MUSDT | H1 | cross_venue | abs_cross_venue_spread_diff_bps | high | 0 | 0.0000 | n/a | n/a | n/a |
| fold2 | BONK1MUSDT | H1 | imbalance | trade_flow_imbalance | low | 951 | 0.2650 | 0.0137 | -0.0154 | 2.3966 |
| fold2 | BONK1MUSDT | H1 | microprice | abs_snapshot_microprice_offset_bps_mean | high | 701 | 0.1953 | -0.0019 | -0.0149 | -0.4050 |
| fold2 | BONK1MUSDT | H1 | spread_liquidity | snapshot_spread_bps_median | high | 1044 | 0.2909 | -0.0491 | 0.0496 | -5.8579 |
| fold3 | BONK1MUSDT | H1 | activity | book_ticker_count | low | 2511 | 0.5813 | -0.0067 | -0.0263 | -0.0526 |
| fold3 | BONK1MUSDT | H1 | combined | spread_x_rv_1h AND book_ticker_count AND abs_cross_venue_basis_bps | low AND low AND high | 478 | 0.1106 | -0.1406 | 0.1051 | -13.1474 |
| fold3 | BONK1MUSDT | H1 | context_only | ctx_bonk_beta_sol_240m | low | 2339 | 0.5414 | 0.0653 | -0.0997 | 5.2306 |
| fold3 | BONK1MUSDT | H1 | cross_venue | abs_cross_venue_basis_bps | high | 1204 | 0.2787 | -0.0690 | 0.0652 | -8.1275 |
| fold3 | BONK1MUSDT | H1 | imbalance | wobi5_minus_wobi25 | high | 1639 | 0.3794 | -0.0192 | -0.0032 | -1.3050 |
| fold3 | BONK1MUSDT | H1 | microprice | snapshot_microprice_offset_bps_mean | high | 1548 | 0.3583 | 0.0063 | -0.0209 | 1.2533 |
| fold3 | BONK1MUSDT | H1 | spread_liquidity | spread_x_rv_1h | low | 2517 | 0.5826 | -0.0340 | -0.0096 | -2.4315 |
| fold2 | BONK1MUSDC | H4 | activity | snapshot_count | low | 211 | 0.0588 | 0.1546 | -0.0115 | 14.8424 |
| fold2 | BONK1MUSDC | H4 | combined | depth_x_low_rv_proxy AND snapshot_count AND abs_cross_venue_spread_diff_bps | high AND low AND high | 0 | 0.0000 | n/a | n/a | n/a |
| fold2 | BONK1MUSDC | H4 | context_only | ctx_bonk_corr_sol_240m | low | 139 | 0.0387 | 0.0209 | 0.2172 | 7.3018 |
| fold2 | BONK1MUSDC | H4 | cross_venue | abs_cross_venue_spread_diff_bps | high | 0 | 0.0000 | n/a | n/a | n/a |
| fold2 | BONK1MUSDC | H4 | imbalance | abs_trade_flow_imbalance | high | 921 | 0.2566 | 0.0072 | 0.0024 | 1.1289 |
| fold2 | BONK1MUSDC | H4 | microprice | abs_snapshot_microprice_offset_bps_mean | high | 623 | 0.1736 | 0.0607 | -0.0328 | 9.9393 |
| fold2 | BONK1MUSDC | H4 | spread_liquidity | depth_x_low_rv_proxy | high | 162 | 0.0451 | 0.3015 | -0.1321 | 35.0038 |
| fold3 | BONK1MUSDC | H4 | activity | snapshot_count | low | 1059 | 0.2454 | 0.1284 | -0.0761 | 30.3276 |
| fold3 | BONK1MUSDC | H4 | combined | cross_venue_activity_ratio AND depth_x_low_rv_proxy AND snapshot_count | high AND high AND low | 297 | 0.0688 | 0.1574 | -0.0594 | 33.4600 |
| fold3 | BONK1MUSDC | H4 | context_only | ctx_bonk_beta_sol_240m | low | 2346 | 0.5437 | 0.0710 | -0.0837 | 15.3865 |
| fold3 | BONK1MUSDC | H4 | cross_venue | cross_venue_activity_ratio | high | 2672 | 0.6192 | 0.0072 | 0.0070 | 0.5187 |
| fold3 | BONK1MUSDC | H4 | imbalance | top_depth_imbalance_ratio | low | 1288 | 0.2985 | 0.0188 | 0.0006 | 3.1926 |
| fold3 | BONK1MUSDC | H4 | microprice | abs_microprice_offset_bps_mean | high | 980 | 0.2271 | 0.0164 | 0.0062 | 3.1094 |
| fold3 | BONK1MUSDC | H4 | spread_liquidity | depth_x_low_rv_proxy | high | 1312 | 0.3041 | 0.0527 | -0.0049 | 11.8723 |
| fold2 | BONK1MUSDT | H4 | activity | snapshot_count | low | 1503 | 0.4188 | 0.0539 | -0.0068 | 5.8743 |
| fold2 | BONK1MUSDT | H4 | combined | snapshot_spread_bps_median AND snapshot_count AND abs_cross_venue_spread_diff_bps | high AND low AND high | 0 | 0.0000 | n/a | n/a | n/a |
| fold2 | BONK1MUSDT | H4 | context_only | ctx_bonk_rv_4h_bps | low | 15 | 0.0042 | 0.3020 | -0.2889 | 76.0671 |
| fold2 | BONK1MUSDT | H4 | cross_venue | abs_cross_venue_spread_diff_bps | high | 0 | 0.0000 | n/a | n/a | n/a |
| fold2 | BONK1MUSDT | H4 | imbalance | top_depth_imbalance_ratio | low | 1109 | 0.3090 | 0.0396 | -0.0049 | 2.6496 |
| fold2 | BONK1MUSDT | H4 | microprice | abs_snapshot_microprice_offset_bps_mean | high | 701 | 0.1953 | 0.0296 | 0.0092 | 0.8641 |
| fold2 | BONK1MUSDT | H4 | spread_liquidity | snapshot_spread_bps_median | high | 1044 | 0.2909 | -0.0418 | 0.0750 | -7.8120 |
| fold3 | BONK1MUSDT | H4 | activity | book_ticker_count | low | 2511 | 0.5813 | 0.0219 | -0.0017 | 5.3907 |
| fold3 | BONK1MUSDT | H4 | combined | spread_x_rv_1h AND book_ticker_count AND cross_venue_activity_ratio | low AND low AND low | 1182 | 0.2736 | -0.0327 | 0.0667 | -1.5422 |
| fold3 | BONK1MUSDT | H4 | context_only | ctx_bonk_beta_sol_240m | low | 2339 | 0.5414 | 0.0714 | -0.0849 | 15.5254 |
| fold3 | BONK1MUSDT | H4 | cross_venue | cross_venue_activity_ratio | low | 2674 | 0.6190 | 0.0086 | 0.0074 | 0.4543 |
| fold3 | BONK1MUSDT | H4 | imbalance | top_depth_imbalance_ratio | low | 1174 | 0.2718 | 0.0440 | -0.0134 | 8.6565 |
| fold3 | BONK1MUSDT | H4 | microprice | abs_microprice_offset_bps_mean | high | 949 | 0.2197 | 0.1094 | -0.0436 | 25.6307 |
| fold3 | BONK1MUSDT | H4 | spread_liquidity | spread_x_rv_1h | low | 2517 | 0.5826 | -0.0300 | 0.0584 | -1.6928 |

## Short-Horizon Bucket Probe

| family | horizon_label | barrier_bps | rows | median_selected_share | median_resid_edge | median_lower_edge |
| --- | --- | --- | --- | --- | --- | --- |
| combined | 15m | 20 | 1677 | 0.0757 | 0.0290 | 0.0261 |
| spread_liquidity | 15m | 20 | 3829 | 0.2752 | 0.0253 | -0.0117 |
| microprice | 15m | 20 | 4970 | 0.3139 | 0.0136 | -0.0034 |
| imbalance | 15m | 20 | 5723 | 0.3719 | 0.0113 | 0.0060 |
| activity | 15m | 20 | 5759 | 0.3909 | 0.0081 | -0.0085 |
| cross_venue | 15m | 20 | 5360 | 0.2789 | -0.0039 | 0.0107 |
| spread_liquidity | 15m | 30 | 1995 | 0.1470 | 0.0201 | -0.0574 |
| microprice | 15m | 30 | 4970 | 0.3139 | 0.0136 | -0.0120 |
| imbalance | 15m | 30 | 5723 | 0.3719 | 0.0113 | 0.0026 |
| activity | 15m | 30 | 5759 | 0.3909 | 0.0081 | -0.0482 |
| cross_venue | 15m | 30 | 6270 | 0.3132 | -0.0134 | 0.0182 |
| combined | 15m | 30 | 798 | 0.0427 | -0.0202 | -0.0388 |
| imbalance | 30m | 20 | 5990 | 0.3822 | 0.0149 | 0.0025 |
| microprice | 30m | 20 | 5076 | 0.3283 | 0.0133 | 0.0023 |
| spread_liquidity | 30m | 20 | 3509 | 0.2744 | 0.0064 | -0.0010 |
| activity | 30m | 20 | 6723 | 0.5026 | -0.0007 | 0.0045 |
| cross_venue | 30m | 20 | 6720 | 0.4781 | -0.0161 | -0.0085 |
| combined | 30m | 20 | 1379 | 0.0873 | -0.0220 | 0.0164 |
| activity | 30m | 30 | 5953 | 0.4133 | 0.0295 | -0.0333 |
| imbalance | 30m | 30 | 5990 | 0.3822 | 0.0149 | 0.0004 |
| microprice | 30m | 30 | 4987 | 0.3159 | 0.0107 | -0.0039 |
| spread_liquidity | 30m | 30 | 3509 | 0.2744 | 0.0064 | -0.0212 |
| combined | 30m | 30 | 1369 | 0.0861 | -0.0152 | -0.0149 |
| cross_venue | 30m | 30 | 3782 | 0.2789 | -0.0227 | 0.0249 |
| spread_liquidity | 5m | 20 | 3212 | 0.2330 | 0.0259 | -0.0308 |
| combined | 5m | 20 | 2538 | 0.1833 | 0.0245 | -0.0181 |
| microprice | 5m | 20 | 4829 | 0.3137 | 0.0239 | -0.0085 |
| imbalance | 5m | 20 | 5811 | 0.3821 | 0.0191 | -0.0035 |
| activity | 5m | 20 | 5140 | 0.3321 | 0.0019 | -0.0427 |
| cross_venue | 5m | 20 | 8071 | 0.5589 | -0.0012 | 0.0018 |
| combined | 5m | 30 | 1671 | 0.0830 | 0.0415 | -0.0148 |
| spread_liquidity | 5m | 30 | 2092 | 0.1032 | 0.0339 | -0.0217 |
| microprice | 5m | 30 | 4829 | 0.3137 | 0.0239 | -0.0068 |
| imbalance | 5m | 30 | 5811 | 0.3821 | 0.0191 | 0.0003 |
| cross_venue | 5m | 30 | 5447 | 0.2889 | 0.0013 | -0.0106 |
| activity | 5m | 30 | 8298 | 0.4801 | -0.0048 | -0.0181 |

## Interpretation Guardrails

- A family contributes only when `context + family` improves proper scores versus `context_only`; top-bucket lift alone is secondary.
- Short-horizon rows are included as feasibility/decay diagnostics, not as the main context-controlled ranking.
- `combined` can show the ceiling of all L2 information, but the single-family winner is the cleaner attribution answer.
- `reported_buy_share` and `trade_flow_imbalance` remain exchange-reported fields, not confirmed taker side semantics.

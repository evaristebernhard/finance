# BONK V3 Tree Modeling Report

- `run_tag`: `20260513_bullish_l2_basket_price_v1`
- 本报告只做 shallow tree / boosted-tree diagnostics，不输出交易规则，也不声称 alpha。
- 目标是检验 L2 特征在控制 Binance market/meme/SOL 与 Bullish common-mode 后，是否还能给 path label 增量。
- 主标签: `upper_first` at `100bps`; 主窗口: `1h` 与 `4h`; USDC/USDT 分开报告。

## Outputs

- Metrics CSV: `date\bonk_v1_tree_model_metrics_20260513_bullish_l2_basket_price_v1.csv`
- Stability CSV: `date\bonk_v1_tree_model_stability_20260513_bullish_l2_basket_price_v1.csv`
- Feature importance CSV: `date\bonk_v1_tree_model_importance_20260513_bullish_l2_basket_price_v1.csv`
- Phase non-overlap CSV: `date\bonk_v1_tree_model_phase_metrics_20260513_bullish_l2_basket_price_v1.csv`
- Candidate gate overlap CSV: `date\bonk_v1_tree_model_gate_overlap_20260513_bullish_l2_basket_price_v1.csv`
- Panel parquet: `data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet`

## Data Slice

- Rows used after filters: `79,795`.
- Symbols: `BONK1MUSDC, BONK1MUSDT`.
- Horizons: `1h, 4h`.
- Filters: `label_status=ok`, `barrier_bps=100`, `horizon_hours in [1,4]`.

## Main Paired Read

Baseline is the same tree family with context-only features. Candidate is context+L2.
Negative `delta_log_loss` and `delta_brier` mean the L2-augmented tree improved proper scores.

| tree_family | symbol | horizon_hours | fold | rows_candidate | proper_score_pass | delta_log_loss | delta_brier | delta_top_decile_lift | delta_upper_edge_minus_lower_edge | delta_path_width_lift_bps | delta_daily_spearman_ic |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lightgbm | BONK1MUSDC | 1 | fold2 | 60 | no | 0.0041 | -0.0038 | 0.1667 | 0.0000 | 46.37 | -0.0824 |
| lightgbm | BONK1MUSDC | 1 | fold3 | 72 | no | 0.0117 | 0.0060 | -0.1250 | 0.0000 | -9.7894 | 0.1385 |
| lightgbm | BONK1MUSDC | 4 | fold2 | 15 | yes | -0.1321 | -0.0457 | 0.0000 | 0.0000 | 0.0000 | 0.4000 |
| lightgbm | BONK1MUSDC | 4 | fold3 | 18 | yes | -0.0058 | -0.0012 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| lightgbm | BONK1MUSDT | 1 | fold2 | 60 | no | 0.0379 | 0.0055 | -0.1667 | -0.1667 | -33.51 | -0.1633 |
| lightgbm | BONK1MUSDT | 1 | fold3 | 72 | no | 0.0449 | 0.0255 | -0.1250 | -0.1250 | -5.3514 | 0.1610 |
| lightgbm | BONK1MUSDT | 4 | fold2 | 15 | yes | -0.1222 | -0.0313 | 0.0000 | 0.0000 | 0.0000 | 0.2571 |
| lightgbm | BONK1MUSDT | 4 | fold3 | 18 | no | 0.0161 | 0.0022 | 0.0000 | 0.0000 | -22.76 | -0.1429 |
| xgboost | BONK1MUSDC | 1 | fold2 | 60 | no | -0.0070 | 0.0003 | 0.0000 | 0.0000 | 0.0000 | 0.0139 |
| xgboost | BONK1MUSDC | 1 | fold3 | 72 | no | -0.0005 | 0.0007 | 0.1250 | 0.2500 | -8.1776 | 0.1186 |
| xgboost | BONK1MUSDC | 4 | fold2 | 15 | yes | -0.0535 | -0.0210 | 0.5000 | 1.0000 | 3.7888 | 0.2000 |
| xgboost | BONK1MUSDC | 4 | fold3 | 18 | yes | -0.0073 | -0.0032 | 0.0000 | 0.0000 | 17.85 | -0.0857 |
| xgboost | BONK1MUSDT | 1 | fold2 | 60 | yes | -0.0063 | -0.0005 | 0.0000 | 0.0000 | 0.0000 | 0.0117 |
| xgboost | BONK1MUSDT | 1 | fold3 | 72 | no | 0.0361 | 0.0175 | -0.1250 | 0.0000 | -16.09 | 0.2872 |
| xgboost | BONK1MUSDT | 4 | fold2 | 15 | yes | -0.0592 | -0.0210 | 0.0000 | 0.0000 | 0.0000 | 0.2571 |
| xgboost | BONK1MUSDT | 4 | fold3 | 18 | no | 0.0187 | 0.0083 | -0.5000 | -1.0000 | -35.84 | -0.0571 |

## L2-Only Sanity

This compares L2-only trees with context-only trees. A positive read here means L2 carries standalone state information, even if context+L2 integration is noisy.

| tree_family | symbol | horizon_hours | fold | rows_candidate | proper_score_pass | delta_log_loss | delta_brier | delta_top_decile_lift | delta_upper_edge_minus_lower_edge |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lightgbm | BONK1MUSDC | 1 | fold2 | 60 | yes | -0.3246 | -0.0406 | 0.3333 | 0.6667 |
| lightgbm | BONK1MUSDC | 1 | fold3 | 72 | no | 0.0555 | 0.0270 | -0.1250 | 0.0000 |
| lightgbm | BONK1MUSDC | 4 | fold2 | 15 | yes | -0.3025 | -0.0733 | 0.0000 | 0.0000 |
| lightgbm | BONK1MUSDC | 4 | fold3 | 18 | yes | -0.1362 | -0.0611 | 0.5000 | 1.0000 |
| lightgbm | BONK1MUSDT | 1 | fold2 | 60 | yes | -0.2565 | -0.0249 | 0.0000 | 0.0000 |
| lightgbm | BONK1MUSDT | 1 | fold3 | 72 | no | 0.0378 | 0.0238 | 0.0000 | -0.1250 |
| lightgbm | BONK1MUSDT | 4 | fold2 | 15 | no | -0.0563 | 0.0048 | 0.0000 | -0.5000 |
| lightgbm | BONK1MUSDT | 4 | fold3 | 18 | no | 0.0085 | 0.0027 | 0.0000 | 0.5000 |
| xgboost | BONK1MUSDC | 1 | fold2 | 60 | yes | -0.2178 | -0.0352 | 0.1667 | 0.3333 |
| xgboost | BONK1MUSDC | 1 | fold3 | 72 | no | 0.0073 | 0.0032 | 0.0000 | 0.0000 |
| xgboost | BONK1MUSDC | 4 | fold2 | 15 | yes | -0.1310 | -0.0412 | 0.5000 | 1.0000 |
| xgboost | BONK1MUSDC | 4 | fold3 | 18 | yes | -0.0740 | -0.0361 | -0.5000 | -0.5000 |
| xgboost | BONK1MUSDT | 1 | fold2 | 60 | yes | -0.1986 | -0.0318 | 0.3333 | 0.1667 |
| xgboost | BONK1MUSDT | 1 | fold3 | 72 | no | 0.0526 | 0.0256 | 0.1250 | 0.1250 |
| xgboost | BONK1MUSDT | 4 | fold2 | 15 | yes | -0.0631 | -0.0161 | 0.5000 | 1.0000 |
| xgboost | BONK1MUSDT | 4 | fold3 | 18 | no | 0.0813 | 0.0365 | -0.5000 | -1.0000 |

## Phase-Rotated Non-Overlap

Phase rows rotate the non-overlap offset. They are sensitivity checks, not extra independent samples.

| tree_family | symbol | horizon_hours | fold | phase_count | proper_score_pass_rate | median_delta_log_loss | median_delta_brier | median_delta_upper_edge_minus_lower_edge |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lightgbm | BONK1MUSDC | 1 | fold1 | 60 | 0.1667 | 0.0184 | 0.0036 | 0.0000 |
| lightgbm | BONK1MUSDC | 1 | fold2 | 60 | 0.0833 | 0.0166 | 0.0001 | 0.0000 |
| lightgbm | BONK1MUSDC | 1 | fold3 | 60 | 0.5333 | -0.0082 | -0.0004 | 0.1250 |
| lightgbm | BONK1MUSDC | 4 | fold1 | 240 | 0.1042 | 0.0670 | 0.0201 | 0.0000 |
| lightgbm | BONK1MUSDC | 4 | fold2 | 240 | 0.5500 | -0.0388 | -0.0035 | 0.0000 |
| lightgbm | BONK1MUSDC | 4 | fold3 | 240 | 0.6708 | -0.0205 | -0.0080 | 0.0000 |
| lightgbm | BONK1MUSDT | 1 | fold1 | 60 | 0.2000 | 0.0194 | 0.0028 | 0.0000 |
| lightgbm | BONK1MUSDT | 1 | fold2 | 60 | 0.0000 | 0.0603 | 0.0058 | -0.1667 |
| lightgbm | BONK1MUSDT | 1 | fold3 | 60 | 0.0333 | 0.0571 | 0.0289 | 0.1250 |
| lightgbm | BONK1MUSDT | 4 | fold1 | 240 | 0.0250 | 0.1862 | 0.0439 | 0.0000 |
| lightgbm | BONK1MUSDT | 4 | fold2 | 240 | 0.6625 | -0.0684 | -0.0123 | 0.0000 |
| lightgbm | BONK1MUSDT | 4 | fold3 | 240 | 0.3583 | 0.0216 | 0.0086 | 0.0000 |
| xgboost | BONK1MUSDC | 1 | fold1 | 60 | 0.0833 | 0.0037 | 0.0012 | 0.0000 |
| xgboost | BONK1MUSDC | 1 | fold2 | 60 | 0.4333 | -0.0034 | 0.0001 | 0.0000 |
| xgboost | BONK1MUSDC | 1 | fold3 | 60 | 0.4167 | -0.0037 | 0.0008 | 0.0000 |
| xgboost | BONK1MUSDC | 4 | fold1 | 240 | 0.3292 | 0.0160 | -0.0014 | 0.0000 |
| xgboost | BONK1MUSDC | 4 | fold2 | 240 | 0.3708 | 0.0134 | 0.0070 | 0.0000 |
| xgboost | BONK1MUSDC | 4 | fold3 | 240 | 0.5917 | -0.0090 | -0.0033 | 0.0000 |
| xgboost | BONK1MUSDT | 1 | fold1 | 60 | 0.1167 | 0.0080 | 0.0010 | 0.0000 |
| xgboost | BONK1MUSDT | 1 | fold2 | 60 | 0.3167 | 0.0001 | 0.0003 | 0.0000 |
| xgboost | BONK1MUSDT | 1 | fold3 | 60 | 0.0000 | 0.0495 | 0.0230 | 0.1250 |
| xgboost | BONK1MUSDT | 4 | fold1 | 240 | 0.1125 | 0.0915 | 0.0207 | 0.0000 |
| xgboost | BONK1MUSDT | 4 | fold2 | 240 | 0.3875 | 0.0165 | 0.0079 | 0.0000 |
| xgboost | BONK1MUSDT | 4 | fold3 | 240 | 0.2250 | 0.0254 | 0.0127 | 0.0000 |

## Feature Importance

Importance is model gain/importance normalized inside each fold fit, then averaged. It is a locator for follow-up probes, not causal attribution.

Feature-group importance in context+L2 trees:

| model | symbol | horizon_hours | feature_group | mean_group_importance |
| --- | --- | --- | --- | --- |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | context | 0.9193 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | spread_liquidity | 0.0696 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | cross_venue | 0.0088 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | book_pressure | 0.0015 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | activity | 0.0008 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | reported_flow | 0.0000 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | context | 0.7860 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | spread_liquidity | 0.1989 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | cross_venue | 0.0148 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | book_pressure | 0.0002 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | activity | 0.0000 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | reported_flow | 0.0000 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | context | 0.8889 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | spread_liquidity | 0.0983 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | cross_venue | 0.0102 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | book_pressure | 0.0014 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | activity | 0.0012 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | reported_flow | 0.0000 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | context | 0.7575 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | spread_liquidity | 0.2120 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | cross_venue | 0.0300 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | book_pressure | 0.0004 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | activity | 0.0001 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | reported_flow | 0.0000 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | context | 0.7710 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | spread_liquidity | 0.1559 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | cross_venue | 0.0480 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | activity | 0.0215 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | book_pressure | 0.0037 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | reported_flow | 0.0000 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | context | 0.6774 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | spread_liquidity | 0.2932 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | cross_venue | 0.0294 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | activity | 0.0000 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | book_pressure | 0.0000 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | reported_flow | 0.0000 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | context | 0.7424 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | spread_liquidity | 0.2084 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | cross_venue | 0.0420 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | activity | 0.0038 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | book_pressure | 0.0032 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | reported_flow | 0.0000 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | context | 0.5938 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | spread_liquidity | 0.3172 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | cross_venue | 0.0880 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | activity | 0.0010 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | book_pressure | 0.0000 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | reported_flow | 0.0000 |

Top individual features:

| model | symbol | horizon_hours | feature | feature_group | folds_seen | mean_normalized_importance |
| --- | --- | --- | --- | --- | --- | --- |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | ctx_bonk_rv_12h_bps | context | 3 | 0.1502 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | ctx_bonk_corr_sol_240m | context | 3 | 0.0683 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | ctx_bonk_beta_meme_240m | context | 3 | 0.0580 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | bullish_cross_abs_ret_mean_bps | context | 3 | 0.0486 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | ctx_bonk_rv_12h_bps | context | 3 | 0.1804 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | ctx_bonk_corr_sol_240m | context | 3 | 0.0912 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | depth25_total_notional_median | spread_liquidity | 3 | 0.0771 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | ctx_bonk_beta_sol_240m | context | 3 | 0.0739 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | ctx_bonk_rv_12h_bps | context | 3 | 0.1384 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | ctx_bonk_corr_sol_240m | context | 3 | 0.0617 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | bullish_cross_abs_ret_mean_bps | context | 3 | 0.0529 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | ctx_bonk_corr_market_240m | context | 3 | 0.0453 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | ctx_bonk_rv_12h_bps | context | 3 | 0.1926 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | depth25_total_notional_median | spread_liquidity | 3 | 0.0845 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | ctx_bonk_corr_sol_240m | context | 3 | 0.0843 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | ctx_bonk_beta_sol_240m | context | 3 | 0.0689 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | ctx_bonk_corr_sol_240m | context | 3 | 0.0452 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | bullish_cross_abs_ret_mean_bps | context | 3 | 0.0408 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | ctx_bonk_rv_12h_bps | context | 3 | 0.0371 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | ctx_meme_ret_60m_bps | context | 3 | 0.0369 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | depth25_total_notional_median | spread_liquidity | 3 | 0.0700 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | ctx_bonk_rv_12h_bps | context | 3 | 0.0531 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | ctx_market_rv_1h_bps | context | 3 | 0.0459 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | snapshot_spread_bps_median | spread_liquidity | 3 | 0.0457 |

## Candidate Gate Overlap

This checks whether the trees concentrate their top-decile predictions in the hand-built V3 gates. It is a consistency diagnostic.

| model | symbol | horizon_hours | gate | folds_seen | mean_top_minus_all_share | mean_gate_upper_rate | mean_gate_lower_rate | mean_gate_median_future_resid_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | depth_high | 3 | -0.0351 | 0.1359 | 0.1029 | 4.9106 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | depth_high | 3 | -0.0787 | 0.1359 | 0.1029 | 4.9106 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | depth_high+rv_low | 3 | 0.0092 | 0.0708 | 0.0842 | 9.3595 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | depth_high+rv_low | 3 | -0.0374 | 0.0708 | 0.0842 | 9.3595 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | depth_high+rv_low+cv_spread | 3 | 0.0096 | 0.0611 | 0.1080 | 12.87 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | depth_high+rv_low+cv_spread | 3 | -0.0173 | 0.0611 | 0.1080 | 12.87 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | depth_high+rv_low+snapshot_microprice | 3 | 0.0052 | 0.0686 | 0.1044 | 9.1682 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | depth_high+rv_low+snapshot_microprice | 3 | -0.0199 | 0.0686 | 0.1044 | 9.1682 |
| context_plus_l2_lightgbm | BONK1MUSDC | 1 | rv_low | 3 | -0.0068 | 0.0865 | 0.0816 | 7.5576 |
| context_plus_l2_xgboost | BONK1MUSDC | 1 | rv_low | 3 | -0.1356 | 0.0865 | 0.0816 | 7.5576 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | depth_high | 3 | 0.0087 | 0.4713 | 0.2856 | 21.82 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | depth_high | 3 | -0.0069 | 0.4713 | 0.2856 | 21.82 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | depth_high+rv_low | 3 | 0.0104 | 0.4989 | 0.2477 | 24.77 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | depth_high+rv_low | 3 | -0.0024 | 0.4989 | 0.2477 | 24.77 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | depth_high+rv_low+cv_spread | 3 | -0.0043 | 0.5077 | 0.2518 | 38.20 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | depth_high+rv_low+cv_spread | 3 | -0.0082 | 0.5077 | 0.2518 | 38.20 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | depth_high+rv_low+snapshot_microprice | 3 | 0.0046 | 0.4797 | 0.2551 | 24.33 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | depth_high+rv_low+snapshot_microprice | 3 | 0.0020 | 0.4797 | 0.2551 | 24.33 |
| context_plus_l2_lightgbm | BONK1MUSDC | 4 | rv_low | 3 | 0.0176 | 0.4846 | 0.2674 | 28.51 |
| context_plus_l2_xgboost | BONK1MUSDC | 4 | rv_low | 3 | 0.0048 | 0.4846 | 0.2674 | 28.51 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | depth_high | 3 | -0.0534 | 0.1414 | 0.1033 | 5.2122 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | depth_high | 3 | -0.0672 | 0.1414 | 0.1033 | 5.2122 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | depth_high+rv_low | 3 | -0.0179 | 0.0536 | 0.0742 | 10.11 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | depth_high+rv_low | 3 | -0.0316 | 0.0536 | 0.0742 | 10.11 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | depth_high+rv_low+cv_spread | 3 | -0.0247 | 0.0530 | 0.0900 | 11.04 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | depth_high+rv_low+cv_spread | 3 | -0.0336 | 0.0530 | 0.0900 | 11.04 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | depth_high+rv_low+snapshot_microprice | 3 | -0.0155 | 0.0565 | 0.0861 | 10.95 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | depth_high+rv_low+snapshot_microprice | 3 | -0.0197 | 0.0565 | 0.0861 | 10.95 |
| context_plus_l2_lightgbm | BONK1MUSDT | 1 | rv_low | 3 | 0.0080 | 0.0853 | 0.0879 | 7.4283 |
| context_plus_l2_xgboost | BONK1MUSDT | 1 | rv_low | 3 | -0.0466 | 0.0853 | 0.0879 | 7.4283 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | depth_high | 3 | -0.0254 | 0.4830 | 0.2810 | 26.69 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | depth_high | 3 | -0.0301 | 0.4830 | 0.2810 | 26.69 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | depth_high+rv_low | 3 | -0.0238 | 0.5096 | 0.2476 | 32.28 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | depth_high+rv_low | 3 | -0.0264 | 0.5096 | 0.2476 | 32.28 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | depth_high+rv_low+cv_spread | 3 | -0.0282 | 0.5200 | 0.2599 | 42.49 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | depth_high+rv_low+cv_spread | 3 | -0.0230 | 0.5200 | 0.2599 | 42.49 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | depth_high+rv_low+snapshot_microprice | 3 | -0.0038 | 0.5057 | 0.2472 | 35.08 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | depth_high+rv_low+snapshot_microprice | 3 | -0.0113 | 0.5057 | 0.2472 | 35.08 |
| context_plus_l2_lightgbm | BONK1MUSDT | 4 | rv_low | 3 | -0.0065 | 0.4841 | 0.2791 | 29.09 |
| context_plus_l2_xgboost | BONK1MUSDT | 4 | rv_low | 3 | 0.0012 | 0.4841 | 0.2791 | 29.09 |

## Interpretation

Fold2/3 stride-H proper-score wins for context+L2 tree vs context-only tree: `7/16`. Median delta logloss is `-0.0031` and median delta brier is `-0.0001`. Best paired non-overlap slice is `lightgbm` BONK1MUSDC H4 fold2 with delta logloss `-0.1321` and delta brier `-0.0457`. For the active H4 USDT gates, strongest top-decile concentration is `context_plus_l2_xgboost` / `depth_high+rv_low+cv_spread` with top-minus-all share `-2.3%`. If proper-score wins are weak but gate concentration/path-width lift is visible, read the result as a regime-local state detector rather than a durable directional model.

## Guardrails

- Do not read this as an entry/exit rule or a return promise.
- `reported_buy_share` and `trade_flow_imbalance` remain exchange-reported side fields; they are not interpreted as taker buy/sell.
- Future market/meme/SOL fields, future return, MFE/MAE, residual labels, and first-passage labels are outcomes/diagnostics only, never predictors.
- The window is short (`2026-04-29..2026-05-12`); regime-local candidates can be useful, but they should be re-tested on the next available window.

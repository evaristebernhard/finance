# BONK CEX V3 Gate Distillation Probe

Status: 2026-05-13. This is a read-only gate-membership distillation probe over the canonical BONK L2/context panel. It is not an outcome model, trading rule, or execution plan.

## Inputs And Outputs

Input panel:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Output files:

```text
date/bonk_v3_gate_distillation_metrics.csv
date/bonk_v3_gate_distillation_outcome_stats.csv
date/bonk_v3_gate_distillation_importance.csv
date/bonk_v3_gate_distillation_thresholds.csv
date/bonk_v3_gate_distillation_completion.json
```

## Method

- Gates are fit with fold train-tertile thresholds and then applied to validation rows.
- `cv_spread_selected` resolves to `cross_venue_spread_diff_bps=high` for BONK1MUSDT and `low` for BONK1MUSDC.
- Models predict gate membership from raw L2/context columns only; outcome columns are used only after prediction to summarize selected rows.
- Predicted gate rows are the top validation probabilities sized to the train gate share for that fold/symbol/horizon/gate.

## H4 Best Model By Gate

| symbol | gate | model | rows | gate rows | AUC | acc | precision | actual resid edge | predicted resid edge | pred upper edge | pred lower edge |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDC | cv_spread_selected | decision_tree_depth2 | 11503 | 4697 | 1.000 | 97.7% | 95.5% | 5.8% | 3.9% | -1.8% | -0.9% |
| BONK1MUSDT | cv_spread_selected | decision_tree_depth2 | 11509 | 4698 | 1.000 | 97.7% | 95.6% | 5.8% | 3.9% | -1.6% | -1.0% |
| BONK1MUSDC | depth_high | decision_tree_depth2 | 11503 | 2268 | 1.000 | 86.5% | 59.3% | 9.5% | 8.0% | -6.2% | -3.7% |
| BONK1MUSDT | depth_high | lightgbm_depth3 | 11509 | 2393 | 1.000 | 87.5% | 62.4% | 12.6% | 5.5% | -3.5% | -2.8% |
| BONK1MUSDT | depth_high+rv_low | lightgbm_depth3 | 11509 | 1317 | 1.000 | 94.6% | 68.0% | 23.0% | 19.2% | 1.4% | -8.4% |
| BONK1MUSDC | depth_high+rv_low | lightgbm_depth3 | 11503 | 1218 | 1.000 | 93.7% | 62.5% | 19.1% | 14.0% | 0.4% | -6.3% |
| BONK1MUSDT | depth_high+rv_low+cv_spread | lightgbm_depth3 | 11509 | 796 | 1.000 | 96.6% | 69.2% | 27.4% | 22.7% | 1.6% | -7.4% |
| BONK1MUSDC | depth_high+rv_low+cv_spread | lightgbm_depth3 | 11503 | 483 | 1.000 | 97.8% | 66.5% | 27.9% | 23.7% | 0.9% | -9.3% |
| BONK1MUSDC | rv_low | decision_tree_depth2 | 11503 | 3630 | 1.000 | 86.5% | 74.1% | 18.7% | 12.1% | 1.1% | -9.0% |
| BONK1MUSDT | rv_low | decision_tree_depth2 | 11509 | 3603 | 1.000 | 86.7% | 74.0% | 18.9% | 12.3% | 1.1% | -8.6% |

## H4 Top Distillation Features

| gate | model | top features |
| --- | --- | --- |
| cv_spread_selected | decision_tree_depth2 | cross_venue_spread_diff_bps gate |
| cv_spread_selected | decision_tree_depth3 | cross_venue_spread_diff_bps gate |
| cv_spread_selected | lightgbm_depth3 | cross_venue_spread_diff_bps gate, spread_bps_median, top_depth_bid_notional_median |
| depth_high | decision_tree_depth2 | top_depth_total_notional_median gate, ctx_sol_ret_240m_bps, ctx_bonk_beta_sol_60m |
| depth_high | decision_tree_depth3 | top_depth_total_notional_median gate, ctx_sol_ret_240m_bps, ctx_bonk_beta_sol_60m |
| depth_high | lightgbm_depth3 | top_depth_total_notional_median gate, top_depth_ask_notional_median, top_depth_bid_notional_median |
| depth_high+rv_low | decision_tree_depth2 | ctx_bonk_rv_1h_bps gate, top_depth_total_notional_median gate, trade_notional_quote_sum |
| depth_high+rv_low | decision_tree_depth3 | ctx_bonk_rv_1h_bps gate, top_depth_total_notional_median gate, trade_notional_quote_sum |
| depth_high+rv_low | lightgbm_depth3 | top_depth_total_notional_median gate, ctx_bonk_rv_1h_bps gate, ctx_bonk_rv_15m_bps |
| depth_high+rv_low+cv_spread | decision_tree_depth2 | cross_venue_spread_diff_bps gate, top_depth_total_notional_median gate, ctx_bonk_rv_1h_bps gate |
| depth_high+rv_low+cv_spread | decision_tree_depth3 | ctx_bonk_rv_1h_bps gate, cross_venue_spread_diff_bps gate, top_depth_total_notional_median gate |
| depth_high+rv_low+cv_spread | lightgbm_depth3 | cross_venue_spread_diff_bps gate, top_depth_total_notional_median gate, ctx_bonk_rv_1h_bps gate |
| rv_low | decision_tree_depth2 | ctx_bonk_rv_1h_bps gate |
| rv_low | decision_tree_depth3 | ctx_bonk_rv_1h_bps gate |
| rv_low | lightgbm_depth3 | ctx_bonk_rv_1h_bps gate, ctx_bonk_rv_4h_bps, ctx_bonk_rv_15m_bps |

## Read

The easiest gate to distill overall is `cv_spread_selected` on `BONK1MUSDC` H1 with `decision_tree_depth2` AUC 1.000.
Decision-tree depth is intentionally shallow, so high AUC here means the hand gate is mechanically expressible from a small number of raw state variables. The outcome columns remain downstream diagnostics: compare `actual_gate_*` with `pred_gate_*` in the outcome CSV before treating any distilled gate as more than a state classifier.

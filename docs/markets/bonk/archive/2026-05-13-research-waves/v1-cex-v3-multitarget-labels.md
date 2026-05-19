# BONK CEX V3 Multitarget Label Probe

Status: 2026-05-13. This is a read-only diagnostic over the existing BONK V3 L2/context panel. It is not a trading rule, not an execution plan, and not an alpha claim.

## Inputs And Outputs

Input panel:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date/bonk_v3_multitarget_label_selection_summary.csv
date/bonk_v3_multitarget_label_target_correlations.csv
date/bonk_v3_multitarget_label_score_correlations.csv
date/bonk_v3_multitarget_label_completion.json
```

## Method

- Primary slice: `label_status=ok`, `barrier_bps=100`, horizons `1,4`.
- Manual gates reuse the existing fold train-to-validation tertile convention for depth, BONK RV, cross-venue spread, and microprice gates.
- Model top-deciles are diagnostic HistGradientBoosting models trained separately per fold, symbol, horizon, and candidate target.
- Candidate targets are `upper_first`, `lower_first`, `not_lower_first`, `residual_positive`, and raw-return-positive.
- For every gate/top-decile, the probe reports `upper_first`, `lower_first`, `not_lower_first`, `residual_positive`, median future residual, median raw return, and median path width.

## Target Mismatch Read

The core mismatch is that a selector can look good under `not_lower_first` or residual-positive while still not being a clean `upper_first` selector. This matters because the active gate family has often improved by reducing lower-first outcomes and widening path movement, not by creating a large standalone upper-first edge.

Fold3 H4 BONK1MUSDT focus:

| selection_type | selector_name | selected_rows | upper_first_rate | lower_first_rate | not_lower_first_rate | residual_positive_rate | median_future_resid_bps | median_future_return_bps | median_path_width_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manual_gate | depth_high+rv_low | 703 | 30.4% | 42.0% | 58.0% | 52.1% | 4.7950 | -2.0779 | 180.7 |
| manual_gate | depth_high+rv_low+cv_spread | 473 | 37.2% | 36.8% | 63.2% | 61.9% | 19.72 | 24.23 | 180.7 |
| model_top_decile | top_decile_not_lower_first_flag | 432 | 28.5% | 39.4% | 60.6% | 66.9% | 21.75 | 7.9646 | 176.2 |
| model_top_decile | top_decile_raw_return_positive_flag | 432 | 20.4% | 46.1% | 53.9% | 37.5% | -19.44 | -45.37 | 173.4 |
| model_top_decile | top_decile_residual_positive_flag | 433 | 46.9% | 24.2% | 75.8% | 55.0% | 13.87 | 48.69 | 172.4 |
| model_top_decile | top_decile_upper_first_flag | 432 | 27.3% | 59.3% | 40.7% | 17.8% | -48.23 | -90.17 | 203.2 |

Representative model top-deciles:

| fold | symbol | horizon_hours | selector_name | upper_first_rate | lower_first_rate | not_lower_first_rate | residual_positive_rate | median_future_resid_bps | median_future_return_bps | median_path_width_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | BONK1MUSDC | 1 | top_decile_lower_first_flag | 29.0% | 6.4% | 93.6% | 49.0% | -1.2728 | -11.63 | 102.3 |
| fold2 | BONK1MUSDC | 1 | top_decile_not_lower_first_flag | 16.4% | 3.3% | 96.7% | 62.4% | 8.8485 | 14.15 | 105.1 |
| fold2 | BONK1MUSDC | 1 | top_decile_raw_return_positive_flag | 15.0% | 18.9% | 81.1% | 63.0% | 13.94 | 14.15 | 108.5 |
| fold2 | BONK1MUSDC | 1 | top_decile_residual_positive_flag | 25.1% | 23.1% | 76.9% | 52.1% | 2.3416 | 12.60 | 119.9 |
| fold2 | BONK1MUSDC | 1 | top_decile_upper_first_flag | 27.0% | 29.0% | 71.0% | 48.5% | -1.4961 | 13.75 | 127.3 |
| fold3 | BONK1MUSDC | 1 | top_decile_lower_first_flag | 43.1% | 34.7% | 65.3% | 57.2% | 11.66 | 14.52 | 298.5 |
| fold3 | BONK1MUSDC | 1 | top_decile_not_lower_first_flag | 2.1% | 2.1% | 97.9% | 60.9% | 3.5405 | -2.7640 | 61.71 |
| fold3 | BONK1MUSDC | 1 | top_decile_raw_return_positive_flag | 12.0% | 6.2% | 93.8% | 53.5% | 1.4571 | 7.6048 | 67.48 |
| fold3 | BONK1MUSDC | 1 | top_decile_residual_positive_flag | 10.2% | 10.9% | 89.1% | 50.7% | 0.3650 | 4.5042 | 71.24 |
| fold3 | BONK1MUSDC | 1 | top_decile_upper_first_flag | 11.3% | 14.1% | 85.9% | 33.6% | -15.52 | -11.65 | 84.86 |
| fold2 | BONK1MUSDT | 1 | top_decile_lower_first_flag | 34.8% | 12.5% | 87.5% | 53.8% | 8.1472 | -0.7156 | 113.0 |
| fold2 | BONK1MUSDT | 1 | top_decile_not_lower_first_flag | 21.7% | 14.8% | 85.2% | 61.8% | 12.21 | 13.36 | 110.2 |

## Target Correlations

Spearman correlations among target views make the mismatch explicit. `not_lower_first` is a path-survival label, not the same object as `upper_first`; residual-positive and raw return are closer to directional return diagnostics but still do not encode first-passage order.

| symbol | horizon_hours | variable_a | variable_b | spearman | pair_rows |
| --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 1 | not_lower_first_flag | path_width_bps | -0.4552 | 20012 |
| BONK1MUSDC | 1 | not_lower_first_flag | residual_positive_flag | 0.3527 | 20012 |
| BONK1MUSDC | 4 | not_lower_first_flag | path_width_bps | -0.2903 | 19833 |
| BONK1MUSDC | 4 | not_lower_first_flag | residual_positive_flag | 0.4555 | 19833 |
| BONK1MUSDT | 1 | not_lower_first_flag | path_width_bps | -0.4552 | 20065 |
| BONK1MUSDT | 1 | not_lower_first_flag | residual_positive_flag | 0.3529 | 20065 |
| BONK1MUSDT | 4 | not_lower_first_flag | path_width_bps | -0.2862 | 19885 |
| BONK1MUSDT | 4 | not_lower_first_flag | residual_positive_flag | 0.4551 | 19885 |

## Feature And Score Correlations

Manual gates and model scores are useful as state detectors only when their correlations line up with the intended target. A positive relation to residual-positive plus a weaker or unstable relation to `upper_first` is evidence of target mismatch, not confirmation of a long rule.

| symbol | horizon_hours | target | score | spearman | pair_rows |
| --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 1 | lower_first_flag | gate_depth_high+rv_low | -0.0844 | 11503 |
| BONK1MUSDC | 1 | residual_positive_flag | gate_depth_high+rv_low | 0.0183 | 11503 |
| BONK1MUSDC | 1 | upper_first_flag | gate_depth_high+rv_low | -0.0878 | 11503 |
| BONK1MUSDC | 1 | lower_first_flag | gate_depth_high+rv_low+cv_spread | -0.0664 | 11503 |
| BONK1MUSDC | 1 | residual_positive_flag | gate_depth_high+rv_low+cv_spread | 0.0358 | 11503 |
| BONK1MUSDC | 1 | upper_first_flag | gate_depth_high+rv_low+cv_spread | -0.0431 | 11503 |
| BONK1MUSDC | 1 | lower_first_flag | model_score_not_lower_first_flag | -0.1515 | 11503 |
| BONK1MUSDC | 1 | residual_positive_flag | model_score_not_lower_first_flag | 0.0093 | 11503 |
| BONK1MUSDC | 1 | upper_first_flag | model_score_not_lower_first_flag | -0.1635 | 11503 |
| BONK1MUSDC | 1 | lower_first_flag | model_score_residual_positive_flag | -0.0408 | 11503 |
| BONK1MUSDC | 1 | residual_positive_flag | model_score_residual_positive_flag | 0.0174 | 11503 |
| BONK1MUSDC | 1 | upper_first_flag | model_score_residual_positive_flag | -0.0752 | 11503 |
| BONK1MUSDC | 1 | lower_first_flag | model_score_upper_first_flag | 0.0802 | 11503 |
| BONK1MUSDC | 1 | residual_positive_flag | model_score_upper_first_flag | -0.0846 | 11503 |
| BONK1MUSDC | 1 | upper_first_flag | model_score_upper_first_flag | 0.0222 | 11503 |
| BONK1MUSDC | 4 | lower_first_flag | gate_depth_high+rv_low | -0.0368 | 11503 |
| BONK1MUSDC | 4 | residual_positive_flag | gate_depth_high+rv_low | 0.0602 | 11503 |
| BONK1MUSDC | 4 | upper_first_flag | gate_depth_high+rv_low | -0.0490 | 11503 |
| BONK1MUSDC | 4 | lower_first_flag | gate_depth_high+rv_low+cv_spread | -0.0425 | 11503 |
| BONK1MUSDC | 4 | residual_positive_flag | gate_depth_high+rv_low+cv_spread | 0.0767 | 11503 |
| BONK1MUSDC | 4 | upper_first_flag | gate_depth_high+rv_low+cv_spread | -0.0117 | 11503 |
| BONK1MUSDC | 4 | lower_first_flag | model_score_not_lower_first_flag | -0.1720 | 11503 |
| BONK1MUSDC | 4 | residual_positive_flag | model_score_not_lower_first_flag | 0.1501 | 11503 |
| BONK1MUSDC | 4 | upper_first_flag | model_score_not_lower_first_flag | 0.0299 | 11503 |

## Bottom Line

The active BONK V3 candidates should be tracked as state/quality gates until the next window shows that the same selectors improve the exact target intended for execution. For now, `upper_first`, `not_lower_first`, residual-positive, raw return, and path width must stay separate columns in every gate/model readout.

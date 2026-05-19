# BONK V3 Gated Multi-Target Model

- `run_tag`: `20260513_bullish_l2_basket_price_v1`
- 本报告只做 gated model diagnostics，不输出交易规则，也不声称 alpha。
- 手工 gate 是 baseline/regime；模型只在 gate 内排序或校准。
- Multi-target heads: `upper_first`, `lower_first`, `residual_positive`.
- Composite score: `p_residual - p_lower + 0.25 * p_upper`.

## Main H4 USDT Gate Read

| fold | gate | model | base_rows | selected_rows | selected_share | upper_edge | lower_edge | upper_minus_lower_edge | residual_positive_edge | median_future_resid_edge_bps | path_width_edge_bps | score_spearman_future_resid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | depth_high+rv_low | manual_gate_all_rows | 3589 | 42 | 0.0117 | 0.1158 | -0.0508 | 0.1666 | 0.3020 | 29.31 | -41.76 | n/a |
| fold2 | depth_high+rv_low | score_not_lower | 42 | 9 | 0.2143 | -0.2698 | 0.3175 | -0.5873 | 0.0000 | 2.1700 | -0.0000 | 0.3252 |
| fold2 | depth_high+rv_low | score_resid_minus_lower_plus_upper | 42 | 9 | 0.2143 | -0.3810 | 0.4286 | -0.8095 | 0.0000 | 2.1700 | -0.0000 | -0.0515 |
| fold2 | depth_high+rv_low | score_residual | 42 | 9 | 0.2143 | -0.1587 | 0.2063 | -0.3651 | 0.0000 | 12.00 | -0.0000 | -0.0243 |
| fold2 | depth_high+rv_low | score_upper | 42 | 9 | 0.2143 | -0.1587 | 0.0952 | -0.2540 | 0.0000 | -8.9837 | 0.0000 | -0.4234 |
| fold2 | depth_high+rv_low+cv_spread | manual_gate_all_rows | 3589 | 18 | 0.0050 | 0.0682 | 0.0444 | 0.0238 | 0.3020 | 37.29 | -41.76 | n/a |
| fold2 | depth_high+rv_low+cv_spread | skipped_small_gate | 18 | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| fold3 | depth_high+rv_low | manual_gate_all_rows | 4320 | 660 | 0.1528 | -0.0711 | 0.0005 | -0.0716 | 0.0966 | 21.86 | -17.46 | n/a |
| fold3 | depth_high+rv_low | score_not_lower | 660 | 132 | 0.2000 | -0.2697 | 0.2152 | -0.4848 | 0.0152 | 4.4455 | -4.5245 | 0.3247 |
| fold3 | depth_high+rv_low | score_resid_minus_lower_plus_upper | 660 | 132 | 0.2000 | -0.0803 | 0.0485 | -0.1288 | 0.0682 | 14.78 | -4.5245 | 0.3020 |
| fold3 | depth_high+rv_low | score_residual | 660 | 132 | 0.2000 | 0.0939 | -0.2091 | 0.3030 | 0.1364 | 19.85 | -4.5245 | 0.1650 |
| fold3 | depth_high+rv_low | score_upper | 660 | 132 | 0.2000 | -0.0500 | 0.0485 | -0.0985 | -0.1136 | -22.50 | 10.97 | -0.0967 |
| fold3 | depth_high+rv_low+cv_spread | manual_gate_all_rows | 4320 | 407 | 0.0942 | 0.0122 | -0.0695 | 0.0817 | 0.2252 | 40.29 | -19.73 | n/a |
| fold3 | depth_high+rv_low+cv_spread | score_not_lower | 407 | 82 | 0.2015 | -0.3833 | 0.4218 | -0.8051 | -0.1803 | -40.22 | -2.2567 | 0.0072 |
| fold3 | depth_high+rv_low+cv_spread | score_resid_minus_lower_plus_upper | 407 | 82 | 0.2015 | -0.2370 | 0.3730 | -0.6099 | -0.0828 | -13.99 | -2.2567 | -0.0545 |
| fold3 | depth_high+rv_low+cv_spread | score_residual | 407 | 82 | 0.2015 | -0.1272 | 0.0193 | -0.1465 | -0.0340 | -11.13 | -2.2567 | -0.0475 |
| fold3 | depth_high+rv_low+cv_spread | score_upper | 407 | 82 | 0.2015 | -0.0418 | 0.2023 | -0.2441 | -0.0096 | -9.0092 | 2.2677 | -0.2395 |

## Phase-Rotated Gate Read

Phase rows rotate the stride-H offset. For H4, read medians and pass rates, not a single phase.

| fold | gate | model | phases | median_selected_rows | median_residual_edge | median_lower_edge | median_future_resid_edge_bps | positive_resid_phase_rate | lower_suppression_phase_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | depth_high+rv_low | manual_gate_all_rows | 40 | 1.0000 | 0.3333 | -0.2667 | 28.55 | 1.0000 | 0.7500 |
| fold2 | depth_high+rv_low+cv_spread | manual_gate_all_rows | 18 | 1.0000 | 0.3333 | -0.2333 | 34.56 | 1.0000 | 0.6667 |
| fold3 | depth_high+rv_low | manual_gate_all_rows | 238 | 3.0000 | 0.1111 | 0.0000 | 17.40 | 0.6429 | 0.4412 |
| fold3 | depth_high+rv_low | score_not_lower | 180 | 1.0000 | 0.3333 | 0.0000 | 0.0000 | 0.7000 | 0.4556 |
| fold3 | depth_high+rv_low | score_resid_minus_lower_plus_upper | 180 | 1.0000 | 0.3333 | -0.3333 | 0.0000 | 0.7222 | 0.5111 |
| fold3 | depth_high+rv_low | score_residual | 180 | 1.0000 | 0.3333 | -0.3333 | 0.0000 | 0.6056 | 0.6222 |
| fold3 | depth_high+rv_low | score_upper | 180 | 1.0000 | -0.3333 | 0.0000 | 0.0000 | 0.4500 | 0.3778 |
| fold3 | depth_high+rv_low+cv_spread | manual_gate_all_rows | 215 | 2.0000 | 0.3056 | -0.0833 | 41.29 | 0.7535 | 0.5256 |

## Head Quality

| fold | gate | target | train_rows | val_rows | train_positive_rate | val_positive_rate | log_loss | brier | auc | model_fit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | all | target_lower_first | 10056 | 3589 | 0.2920 | 0.2889 | 1.0084 | 0.3714 | 0.5723 | 1 |
| fold2 | all | target_residual_positive | 10056 | 3589 | 0.4564 | 0.6980 | 1.0078 | 0.3788 | 0.4614 | 1 |
| fold2 | all | target_upper_first | 10056 | 3589 | 0.3766 | 0.5985 | 0.9876 | 0.3595 | 0.4086 | 1 |
| fold2 | cv_spread_selected | target_lower_first | 3557 | 1210 | 0.2783 | 0.3438 | 0.8810 | 0.3285 | 0.5662 | 1 |
| fold2 | cv_spread_selected | target_residual_positive | 3557 | 1210 | 0.4768 | 0.6983 | 0.8973 | 0.3367 | 0.6373 | 1 |
| fold2 | cv_spread_selected | target_upper_first | 3557 | 1210 | 0.3450 | 0.5554 | 0.8583 | 0.3181 | 0.4126 | 1 |
| fold2 | depth_high | target_lower_first | 3352 | 388 | 0.2067 | 0.2603 | 1.0236 | 0.3845 | 0.4690 | 1 |
| fold2 | depth_high | target_residual_positive | 3352 | 388 | 0.5033 | 0.8376 | 1.0586 | 0.4000 | 0.4006 | 1 |
| fold2 | depth_high | target_upper_first | 3352 | 388 | 0.3759 | 0.6263 | 0.9896 | 0.3683 | 0.3892 | 1 |
| fold2 | depth_high+rv_low | target_lower_first | 1505 | 42 | 0.1435 | 0.2381 | 2.3506 | 0.6816 | 0.2344 | 1 |
| fold2 | depth_high+rv_low | target_residual_positive | 1505 | 42 | 0.5721 | 1.0000 | 1.1895 | 0.4762 | n/a | 1 |
| fold2 | depth_high+rv_low | target_upper_first | 1505 | 42 | 0.3801 | 0.7143 | 1.4997 | 0.5197 | 0.4056 | 1 |
| fold2 | depth_high+rv_low+snapshot_microprice | target_lower_first | 772 | 26 | 0.1334 | 0.3077 | 1.9795 | 0.6116 | 0.2222 | 1 |
| fold2 | depth_high+rv_low+snapshot_microprice | target_residual_positive | 772 | 26 | 0.5699 | 1.0000 | 1.2334 | 0.4837 | n/a | 1 |
| fold2 | depth_high+rv_low+snapshot_microprice | target_upper_first | 772 | 26 | 0.3899 | 0.6538 | 1.2914 | 0.4625 | 0.1340 | 1 |
| fold2 | rv_low | target_lower_first | 3347 | 162 | 0.1736 | 0.2531 | 1.7761 | 0.5947 | 0.4892 | 1 |
| fold2 | rv_low | target_residual_positive | 3347 | 162 | 0.5763 | 1.0000 | 0.9126 | 0.3367 | n/a | 1 |
| fold2 | rv_low | target_upper_first | 3347 | 162 | 0.4099 | 0.6420 | 1.3606 | 0.4555 | 0.4581 | 1 |
| fold3 | all | target_lower_first | 14365 | 4320 | 0.2970 | 0.4282 | 0.7529 | 0.2626 | 0.5789 | 1 |
| fold3 | all | target_residual_positive | 14365 | 4320 | 0.5171 | 0.4185 | 0.9117 | 0.3343 | 0.5621 | 1 |
| fold3 | all | target_upper_first | 14365 | 4320 | 0.4429 | 0.3711 | 0.7879 | 0.2947 | 0.4440 | 1 |
| fold3 | cv_spread_selected | target_lower_first | 5058 | 1467 | 0.3041 | 0.3340 | 0.8042 | 0.2707 | 0.5341 | 1 |
| fold3 | cv_spread_selected | target_residual_positive | 5058 | 1467 | 0.5328 | 0.5706 | 0.7109 | 0.2515 | 0.5662 | 1 |
| fold3 | cv_spread_selected | target_upper_first | 5058 | 1467 | 0.4069 | 0.4465 | 0.7279 | 0.2667 | 0.4536 | 1 |
| fold3 | depth_high | target_lower_first | 4788 | 940 | 0.2274 | 0.4043 | 0.9063 | 0.3115 | 0.4839 | 1 |
| fold3 | depth_high | target_residual_positive | 4788 | 940 | 0.5459 | 0.5160 | 0.7796 | 0.2853 | 0.5916 | 1 |
| fold3 | depth_high | target_upper_first | 4788 | 940 | 0.4137 | 0.3298 | 0.7954 | 0.2988 | 0.3042 | 1 |
| fold3 | depth_high+rv_low | target_lower_first | 2308 | 660 | 0.1681 | 0.4288 | 0.8573 | 0.2958 | 0.5109 | 1 |
| fold3 | depth_high+rv_low | target_residual_positive | 2308 | 660 | 0.5867 | 0.5152 | 0.8341 | 0.3054 | 0.5778 | 1 |
| fold3 | depth_high+rv_low | target_upper_first | 2308 | 660 | 0.3969 | 0.3000 | 0.8805 | 0.3318 | 0.4370 | 1 |
| fold3 | depth_high+rv_low+cv_spread | target_lower_first | 1081 | 407 | 0.1610 | 0.3587 | 0.9913 | 0.3343 | 0.3007 | 1 |
| fold3 | depth_high+rv_low+cv_spread | target_residual_positive | 1081 | 407 | 0.6133 | 0.6437 | 0.6775 | 0.2410 | 0.4956 | 1 |
| fold3 | depth_high+rv_low+cv_spread | target_upper_first | 1081 | 407 | 0.3719 | 0.3833 | 0.7330 | 0.2681 | 0.4487 | 1 |
| fold3 | depth_high+rv_low+snapshot_microprice | target_lower_first | 1177 | 289 | 0.1648 | 0.3702 | 0.8737 | 0.3049 | 0.4607 | 1 |
| fold3 | depth_high+rv_low+snapshot_microprice | target_residual_positive | 1177 | 289 | 0.5752 | 0.5709 | 0.7397 | 0.2676 | 0.5790 | 1 |
| fold3 | depth_high+rv_low+snapshot_microprice | target_upper_first | 1177 | 289 | 0.4019 | 0.3426 | 0.8213 | 0.3078 | 0.3993 | 1 |
| fold3 | rv_low | target_lower_first | 4786 | 1822 | 0.1935 | 0.4254 | 0.7596 | 0.2575 | 0.6243 | 1 |
| fold3 | rv_low | target_residual_positive | 4786 | 1822 | 0.5980 | 0.4665 | 1.0955 | 0.3888 | 0.4450 | 1 |
| fold3 | rv_low | target_upper_first | 4786 | 1822 | 0.4315 | 0.3315 | 0.8310 | 0.3123 | 0.5935 | 1 |

## Interpretation Guardrails

- A good gated model should improve residual-positive rate or lower-first suppression inside a frozen gate; it does not need to maximize `upper_first` alone.
- Small gates in fold2/fold3 can have very few H4 phase rows, so phase distributions matter more than one top-decile read.
- If a model only improves full-minute rows but fails phase-rotated rows, classify it as overlap/regime diagnostic.
- `reported_buy_share` and `trade_flow_imbalance` remain exchange-reported side fields, not confirmed taker buy/sell.

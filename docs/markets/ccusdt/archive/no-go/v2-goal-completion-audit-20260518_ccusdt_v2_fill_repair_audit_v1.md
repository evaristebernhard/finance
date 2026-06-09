# CCUSDT V2 Goal Completion Audit

Status: `20260518_ccusdt_v2_fill_repair_audit_v1`.

Guardrail: `research_only_fill_repair_audit_no_execution_recommendation_no_alpha_claim`.

Objective: systematize the observed CCUSDT/CEX L2 short-horizon microstructure edge into an executable research framework with strict walk-forward validation, cost pressure, matched controls, mathematical decomposition, entry-quality, exit-shape, and risk-control models, and stable real-cost `>2` bps capture.

## Completion Checklist

| requirement | status | evidence | detail |
| --- | --- | --- | --- |
| strict_walk_forward_framework | partial_pass | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | V2 framework emits expanding folds and fold-valid scorecards, but current execution realism is only a focused post-framework proxy. |
| cost_pressure_and_realistic_cost_ladder | partial_pass | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | Framework has realistic proxy and +2bps stress; L2 practical fill economics are negative. |
| matched_controls_and_residual_controls | partial_pass | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | 4 rows pass enough controls for research_continue, but no promoted row exists. |
| mathematical_decomposition | partial_pass | docs/markets/ccusdt/v2-executable-research-framework.md | Entry/exit/risk decomposition is specified and framework artifacts exist; decomposition is still proxy-label based. |
| entry_quality_model | partial_pass | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_quote_transition_labels_20260518_ccusdt_v2_framework_v1.csv | Fold-valid logistic entry-quality bins exist, but they do not produce fill-aware execution pass. |
| exit_shape_model | partial_pass | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | Quote-transition and path-shape diagnostics exist; no executable exit after real fill is validated. |
| risk_control_model | partial_pass | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | Stop/risk diagnostics exist on proxy path labels; L2 practical filled tails remain poor. |
| stable_after_real_cost_gt_2bps_capture | fail | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_v1.csv | All focused practical L2 queue rows are no-go; filled-net and per-signal net are negative. |
| filter_low_quality_entries | incomplete | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_v1.csv | Current fill-aware repair scan found a post-hoc diagnostic only; no promotable walk-forward filter yet. |
| control_left_tail_risk | incomplete | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_v1.csv | Proxy risk controls exist, but practical filled p10/tail metrics fail for most rows. |
| promotion_or_completion | not_achieved | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | Promoted rows: 0. L2 all no-go: True. Any post-hoc repair pass: False. |

## Practical L2 Queue Evidence

| trigger_class | entry_quality_bin | signals | fill_rate | filled_net_mean_bps | filled_net_p10_bps | per_signal_net_mean_bps | l2_queue_fill_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_event_active | mid | 72 | 0.0833 | -12.0666 | -15.7472 | -1.0056 | l2_queue_fill_no_go |
| tfi_follow_flat | high | 508 | 0.0413 | -2.1469 | -22.0504 | -0.0887 | l2_queue_fill_no_go |
| tfi_long_flat | high | 195 | 0.0308 | -15.6430 | -39.6959 | -0.4813 | l2_queue_fill_no_go |
| tfi_short_flat | high | 391 | 0.0435 | -0.0877 | -21.7321 | -0.0038 | l2_queue_fill_no_go |
| tfi_short_stale25 | low | 38 | 0.0526 | -23.3479 | -33.3388 | -1.2288 | l2_queue_fill_no_go |

## Fill-Aware Repair Scan

This scan is post-hoc on validation-side practical fill rows. It is useful for triage, but a positive row would still need a new walk-forward run before promotion.

| trigger_class | entry_quality_bin | best_filter_expr | signals | fill_rate | filled_net_mean_bps | filled_net_p10_bps | per_signal_net_mean_bps | all_execution_gates_pass | repair_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_short_flat | high | microprice_dev_bps <= 2.897298059e-05 | 157 | 0.0446 | 13.2441 | -20.1367 | 0.5905 | False | no_simple_fill_filter_repair |
| tfi_follow_flat | high | trade_window_count >= 2 | 143 | 0.0559 | 10.1039 | -11.8768 | 0.5653 | False | no_simple_fill_filter_repair |
| tfi_long_flat | high | batch_rows <= 365 | 44 | 0.0227 | -0.0542 | -0.0542 | -0.0012 | False | no_simple_fill_filter_repair |
| tfi_event_active | mid | hour_bucket >= 14 | 30 | 0.0333 | -3.1998 | -3.1998 | -0.1067 | False | no_simple_fill_filter_repair |
| tfi_short_stale25 | low | entry_quality_score >= 0.3071526324 | 30 | 0.0333 | -10.8592 | -10.8592 | -0.3620 | False | no_simple_fill_filter_repair |

## Top Diagnostic Filters

| trigger_class | entry_quality_bin | filter_expr | signals | fill_rate | filled_net_mean_bps | filled_net_p10_bps | per_signal_net_mean_bps | all_execution_gates_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_short_flat | high | microprice_dev_bps <= 2.897298059e-05 | 157 | 0.0446 | 13.2441 | -20.1367 | 0.5905 | False |
| tfi_short_flat | high | signed_microprice_dev_bps >= -2.897298059e-05 | 157 | 0.0446 | 13.2441 | -20.1367 | 0.5905 | False |
| tfi_short_flat | high | queue_imbalance_1 <= 4.667495834e-05 | 157 | 0.0446 | 13.2441 | -20.1367 | 0.5905 | False |
| tfi_short_flat | high | signed_queue_imbalance_1 >= -4.667495834e-05 | 157 | 0.0446 | 13.2441 | -20.1367 | 0.5905 | False |
| tfi_short_flat | high | entry_quality_score >= 0.5888077406 | 79 | 0.0506 | 11.2600 | -14.9845 | 0.5701 | False |
| tfi_follow_flat | high | trade_window_count >= 2 | 143 | 0.0559 | 10.1039 | -11.8768 | 0.5653 | False |
| tfi_short_flat | high | past_event_25_bps <= -0.3169320973 | 79 | 0.0506 | 11.0345 | -5.6913 | 0.5587 | False |
| tfi_follow_flat | high | entry_quality_score >= 0.5901350178 | 102 | 0.0490 | 10.5880 | -13.3045 | 0.5190 | False |
| tfi_short_flat | high | entry_spread_bps >= 2.941955223 | 79 | 0.0253 | 20.2864 | -0.6513 | 0.5136 | False |
| tfi_short_flat | high | mlofi_roll10_l25 <= -0.9998033836 | 79 | 0.0759 | 6.4831 | -9.9822 | 0.4924 | False |
| tfi_short_flat | high | signed_mlofi_roll10_l25 >= 0.9998033836 | 79 | 0.0759 | 6.4831 | -9.9822 | 0.4924 | False |
| tfi_follow_flat | high | mlofi_roll10_l25 <= -0.999803848 | 102 | 0.0490 | 9.9038 | -7.7690 | 0.4855 | False |
| tfi_follow_flat | high | signed_mlofi_roll10_l25 >= 0.9997701369 | 102 | 0.0490 | 9.9038 | -7.7690 | 0.4855 | False |
| tfi_short_flat | high | queue_imbalance_1 <= 0.6815023546 | 235 | 0.0468 | 10.3308 | -20.0245 | 0.4836 | False |
| tfi_short_flat | high | signed_queue_imbalance_1 >= -0.6815023546 | 235 | 0.0468 | 10.3308 | -20.0245 | 0.4836 | False |
| tfi_follow_flat | high | hour_bucket <= 5 | 111 | 0.0631 | 7.4439 | -17.1839 | 0.4694 | False |
| tfi_follow_flat | high | past_event_25_bps <= -0.3164887601 | 102 | 0.0392 | 11.5168 | -4.8533 | 0.4516 | False |
| tfi_follow_flat | high | entry_spread_bps >= 1.949279742 | 203 | 0.0345 | 11.9629 | -13.1529 | 0.4125 | False |
| tfi_short_flat | high | mlofi_roll10_l1 <= -0.6692398452 | 79 | 0.0759 | 5.3322 | -13.4349 | 0.4050 | False |
| tfi_short_flat | high | signed_mlofi_roll10_l1 >= 0.6692398452 | 79 | 0.0759 | 5.3322 | -13.4349 | 0.4050 | False |
| tfi_follow_flat | high | entry_spread_bps >= 2.611682185 | 102 | 0.0196 | 19.0368 | -2.9005 | 0.3733 | False |
| tfi_follow_flat | high | entry_quality_score >= 0.5624623203 | 203 | 0.0493 | 7.4834 | -8.5411 | 0.3686 | False |
| tfi_short_flat | high | queue_imbalance_5 <= 0.1669248094 | 235 | 0.0426 | 8.4566 | -20.0526 | 0.3599 | False |
| tfi_short_flat | high | signed_queue_imbalance_5 >= -0.1669248094 | 235 | 0.0426 | 8.4566 | -20.0526 | 0.3599 | False |
| tfi_follow_flat | high | mlofi_roll10_l1 <= -0.9015060987 | 102 | 0.0490 | 7.2679 | -15.3687 | 0.3563 | False |
| tfi_short_flat | high | hour_bucket <= 4 | 79 | 0.0506 | 6.9933 | -17.0066 | 0.3541 | False |
| tfi_short_flat | high | trade_window_count >= 2 | 115 | 0.0696 | 5.0221 | -28.5282 | 0.3494 | False |
| tfi_follow_flat | high | batch_rows <= 365 | 111 | 0.0180 | 19.0368 | -2.9005 | 0.3430 | False |
| tfi_short_flat | high | hour_bucket <= 10 | 167 | 0.0359 | 9.0212 | -21.1777 | 0.3241 | False |
| tfi_short_flat | high | abs_past_event_25_bps >= 0.3082946681 | 157 | 0.0318 | 9.2971 | -5.6265 | 0.2961 | False |

## Decision

The active goal is not complete. The research framework is substantially systematized, but the explicit `stable real-cost >2bps capture` requirement is not satisfied by current L2 queue-fill evidence.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_repair_filters_20260518_ccusdt_v2_fill_repair_audit_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_fill_repair_audit_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_fill_repair_audit.py
```

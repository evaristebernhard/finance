# CCUSDT V2 Goal Completion Audit

Status: `20260518_ccusdt_v2_fill_repair_audit_all_practical_v1`.

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
| stable_after_real_cost_gt_2bps_capture | fail | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv | All practical L2 queue scorecard rows are no-go; filled-net and per-signal net are negative. |
| taker_or_crossing_fallback | fail | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv | Taker promote-gate rows: 0; crossing does not rescue current candidates. |
| execution_failure_decomposition | fail | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.csv | Best practical maker per-signal net is -0.0038 bps versus the 2 bps target. |
| structural_queue_release_pivot | fail | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv | Queue-release promote-gate rows: 0; best mean is -1.7573 bps. |
| liquidity_envelope_universe_pivot | fail | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv | Envelope status: liquidity_envelope_no_go; depth-support day rate: 0.0000; best practical maker fill rate: 0.1176. |
| filter_low_quality_entries | incomplete | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv | Current fill-aware repair scan found a post-hoc diagnostic only; no promotable walk-forward filter yet. |
| control_left_tail_risk | incomplete | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv | Proxy risk controls exist, but practical filled p10/tail metrics fail for most rows. |
| promotion_or_completion | not_achieved | C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | Promoted rows: 0. L2 all no-go: True. Taker gate rows: 0. Queue-release gate rows: 0. Liquidity envelope status: liquidity_envelope_no_go. Any post-hoc repair pass: False. |

## Practical L2 Queue Evidence

| fold | trigger_class | entry_quality_bin | signals | fill_rate | filled_net_mean_bps | filled_net_p10_bps | per_signal_net_mean_bps | l2_queue_fill_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | tfi_event_active | high | 31 | 0.0968 | -7.1554 | -9.5309 | -0.6925 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_event_active | low | 21 | 0.0952 | -1.0078 | -5.5937 | -0.0960 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_event_active | mid | 9 | 0.0000 |  |  |  | l2_queue_fill_no_go |
| expanding_fold1 | tfi_follow_flat | high | 317 | 0.0410 | -3.4957 | -9.4823 | -0.1434 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_follow_flat | low | 186 | 0.0215 | -2.1763 | -6.1250 | -0.0468 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_follow_flat | mid | 250 | 0.0400 | -8.2162 | -12.7807 | -0.3286 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_long_flat | high | 129 | 0.0388 | -5.4936 | -8.9930 | -0.2129 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_long_flat | low | 140 | 0.0143 | -3.3448 | -4.4207 | -0.0478 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_long_flat | mid | 134 | 0.0448 | -7.9794 | -21.0357 | -0.3573 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_flat | high | 188 | 0.0585 | -3.8339 | -6.7114 | -0.2243 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_flat | low | 88 | 0.0795 | -4.9726 | -9.2363 | -0.3956 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_flat | mid | 132 | 0.0152 | -5.3782 | -8.0807 | -0.0815 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_stale25 | high | 5 | 0.0000 |  |  |  | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_stale25 | low | 17 | 0.1176 | -1.0078 | -5.5937 | -0.1186 | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_stale25 | mid | 5 | 0.0000 |  |  |  | l2_queue_fill_no_go |
| expanding_fold2 | tfi_event_active | high | 56 | 0.0536 | -2.2653 | -10.4318 | -0.1214 | l2_queue_fill_no_go |
| expanding_fold2 | tfi_event_active | low | 37 | 0.0000 |  |  |  | l2_queue_fill_no_go |
| expanding_fold2 | tfi_event_active | mid | 28 | 0.0000 |  |  |  | l2_queue_fill_no_go |
| expanding_fold2 | tfi_follow_flat | high | 337 | 0.0356 | -23.9536 | -95.5339 | -0.8529 | l2_queue_fill_no_go |
| expanding_fold2 | tfi_follow_flat | low | 298 | 0.0336 | -5.5247 | -12.8272 | -0.1854 | l2_queue_fill_no_go |

## Taker And Execution Decomposition

| fold | trigger_class | entry_quality_bin | entries | taker_net_mean_bps | taker_net_plus2_mean_bps | taker_promote_gate | fail_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_event_active | mid | 72 | 4.7331 | 2.7331 | False | sample,controls,tail,risk |
| expanding_fold3 | tfi_short_stale25 | high | 54 | 3.4582 | 1.4582 | False | sample,controls,tail,risk |
| expanding_fold3 | tfi_short_stale25 | mid | 39 | 2.9771 | 0.9771 | False | sample,controls,tail,risk |
| expanding_fold3 | tfi_short_stale25 | low | 38 | 2.9104 | 0.9104 | False | sample,tail,risk |
| expanding_fold2 | tfi_short_flat | mid | 206 | 1.9542 | -0.0458 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_follow_flat | high | 508 | 1.0685 | -0.9315 | False | economics,plus2_stress,tail,risk |
| expanding_fold3 | tfi_event_active | high | 85 | 1.0613 | -0.9387 | False | sample,economics,plus2_stress,controls,tail |
| expanding_fold2 | tfi_event_active | mid | 28 | 0.9593 | -1.0407 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_short_flat | low | 129 | 0.9160 | -1.0840 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.8717 | -1.1283 | False | sample,economics,plus2_stress,tail |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.7313 | -1.2687 | False | sample,economics,plus2_stress,tail,risk |
| expanding_fold1 | tfi_short_stale25 | mid | 5 | 0.7034 | -1.2966 | False | sample,economics,plus2_stress,controls,tail,risk |

| fold | trigger_class | entry_quality_bin | fill_rate | filled_net_mean_bps | per_signal_net_mean_bps | maker_gap_to_target_bps | maker_failure_mode |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 0.0435 | -0.0877 | -0.0038 | 2.0038 | filled_net_nonpositive |
| expanding_fold2 | tfi_long_flat | low | 0.0070 | -2.0000 | -0.0141 | 2.0141 | filled_net_nonpositive |
| expanding_fold2 | tfi_short_flat | mid | 0.0388 | -0.9986 | -0.0388 | 2.0388 | filled_net_nonpositive |
| expanding_fold2 | tfi_follow_flat | mid | 0.0206 | -2.0947 | -0.0432 | 2.0432 | filled_net_nonpositive |
| expanding_fold1 | tfi_follow_flat | low | 0.0215 | -2.1763 | -0.0468 | 2.0468 | filled_net_nonpositive |
| expanding_fold1 | tfi_long_flat | low | 0.0143 | -3.3448 | -0.0478 | 2.0478 | filled_net_nonpositive |
| expanding_fold1 | tfi_short_flat | mid | 0.0152 | -5.3782 | -0.0815 | 2.0815 | filled_net_nonpositive |
| expanding_fold3 | tfi_follow_flat | high | 0.0413 | -2.1469 | -0.0887 | 2.0887 | filled_net_nonpositive |
| expanding_fold1 | tfi_event_active | low | 0.0952 | -1.0078 | -0.0960 | 2.0960 | filled_net_nonpositive |
| expanding_fold2 | tfi_long_flat | high | 0.0292 | -3.3493 | -0.0978 | 2.0978 | filled_net_nonpositive |
| expanding_fold1 | tfi_short_stale25 | low | 0.1176 | -1.0078 | -0.1186 | 2.1186 | filled_net_nonpositive |
| expanding_fold2 | tfi_event_active | high | 0.0536 | -2.2653 | -0.1214 | 2.1214 | filled_net_nonpositive |

## Structural Queue-Release Pivot

This lightweight pivot tests book-ticker queue-release continuation as a structurally different signal family. It is diagnostic only and does not promote execution.

| fold | release_side | horizon_sec | threshold_quantile | entries | net_mean_bps | net_plus2_mean_bps | net_cvar10_bps | signal_minus_random_p50_bps | pivot_promote_gate | queue_release_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | bid_release_short | 10.0000 | 0.9900 | 1095 | -1.7573 | -3.7573 | -17.8620 | 1.6947 | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 10.0000 | 0.9750 | 2019 | -2.1439 | -4.1439 | -16.2783 | 1.4907 | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 5.0000 | 0.9900 | 1095 | -2.4283 | -4.4283 | -15.6422 | 1.2129 | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 5.0000 | 0.9750 | 2019 | -2.5906 | -4.5906 | -12.9567 | 1.1189 | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 10.0000 | 0.9900 | 1386 | -2.6770 | -4.6770 | -20.8114 | 1.0068 | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 10.0000 | 0.9750 | 2401 | -2.6835 | -4.6835 | -18.2414 | 1.1183 | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 5.0000 | 0.9900 | 1030 | -2.7139 | -4.7139 | -12.7655 | 1.1480 | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 10.0000 | 0.9900 | 1030 | -2.7720 | -4.7720 | -17.9464 | 0.9351 | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 5.0000 | 0.9900 | 1386 | -2.7741 | -4.7741 | -16.2365 | 0.9298 | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 5.0000 | 0.9750 | 2401 | -2.8752 | -4.8752 | -14.0631 | 0.8829 | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 10.0000 | 0.9750 | 1898 | -3.1350 | -5.1350 | -15.8504 | 0.6973 | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 5.0000 | 0.9750 | 1898 | -3.2021 | -5.2021 | -11.6109 | 0.7060 | False | queue_release_no_go |

## Liquidity Envelope Pivot

This execution-first screen checks whether CCUSDT itself supports the target notional and practical fill profile before more alpha mining.

| symbol | dates | target_notional_quote | median_daily_median_spread_bps | median_daily_top_depth_p05_quote | depth_support_day_rate | best_practical_maker_fill_rate | best_practical_maker_per_signal_net_bps | taker_promote_rows | envelope_pre_alpha_gate | liquidity_envelope_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CCUSDT | 17 | 100.0000 | 2.0148 | 0.0952 | 0.0000 | 0.1176 | -0.0038 | 0 | False | liquidity_envelope_no_go |

## Fill-Aware Repair Scan

This scan is post-hoc on validation-side practical fill rows. It is useful for triage, but a positive row would still need a new walk-forward run before promotion.

| fold | trigger_class | entry_quality_bin | best_filter_expr | signals | fill_rate | filled_net_mean_bps | filled_net_p10_bps | per_signal_net_mean_bps | all_execution_gates_pass | repair_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | microprice_dev_bps <= 2.897298059e-05 | 157 | 0.0446 | 13.2441 | -20.1367 | 0.5905 | False | no_simple_fill_filter_repair |
| expanding_fold3 | tfi_follow_flat | high | trade_window_count >= 2 | 143 | 0.0559 | 10.1039 | -11.8768 | 0.5653 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_short_flat | mid | microprice_dev_bps >= 0.6210653535 | 42 | 0.0476 | 7.9838 | 0.5070 | 0.3802 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_event_active | high | mlofi_roll10_l1 >= -0.01492503902 | 34 | 0.0588 | 3.4299 | 2.6571 | 0.2018 | False | no_simple_fill_filter_repair |
| expanding_fold1 | tfi_follow_flat | mid | entry_quality_score <= 0.4659765998 | 50 | 0.0200 | 8.2281 | 8.2281 | 0.1646 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_short_flat | high | entry_spread_bps <= 1.289457398 | 44 | 0.0682 | 2.1312 | 0.4436 | 0.1453 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_follow_flat | low | past_event_25_bps >= 0.3202387834 | 60 | 0.0833 | 1.6883 | -5.2488 | 0.1407 | False | no_simple_fill_filter_repair |
| expanding_fold1 | tfi_follow_flat | low | entry_spread_bps <= 1.343183345 | 39 | 0.0256 | 4.7245 | 4.7245 | 0.1211 | False | no_simple_fill_filter_repair |
| expanding_fold3 | tfi_short_flat | mid | queue_imbalance_5 >= 0.9056171614 | 40 | 0.0250 | 4.3464 | 4.3464 | 0.1087 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_follow_flat | mid | frames_since_mid_change >= 3 | 59 | 0.0508 | 1.8362 | -0.5882 | 0.0934 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_long_flat | high | hour_bucket <= 4 | 31 | 0.0323 | 2.4639 | 2.4639 | 0.0795 | False | no_simple_fill_filter_repair |
| expanding_fold3 | tfi_follow_flat | low | queue_imbalance_5 >= 0.9231525879 | 67 | 0.0149 | 4.3464 | 4.3464 | 0.0649 | False | no_simple_fill_filter_repair |
| expanding_fold1 | tfi_follow_flat | high | signed_mlofi_roll10_l25 <= -5.017739394e-05 | 64 | 0.0156 | 4.0539 | 4.0539 | 0.0633 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_long_flat | mid | entry_spread_bps <= 2.564432349 | 61 | 0.0328 | 0.5125 | -2.5942 | 0.0168 | False | no_simple_fill_filter_repair |
| expanding_fold3 | tfi_long_flat | high | batch_rows <= 365 | 44 | 0.0227 | -0.0542 | -0.0542 | -0.0012 | False | no_simple_fill_filter_repair |
| expanding_fold2 | tfi_long_flat | low | all focused practical-scenario entries | 142 | 0.0070 | -2.0000 | -2.0000 | -0.0141 | False | no_simple_fill_filter_repair |
| expanding_fold1 | tfi_long_flat | low | batch_rows >= 364 | 132 | 0.0076 | -2.0000 | -2.0000 | -0.0152 | False | no_simple_fill_filter_repair |
| expanding_fold1 | tfi_short_flat | high | queue_imbalance_1 >= 0.636495414 | 75 | 0.0133 | -1.3307 | -1.3307 | -0.0177 | False | no_simple_fill_filter_repair |
| expanding_fold1 | tfi_short_flat | mid | batch_rows >= 366 | 107 | 0.0093 | -2.0000 | -2.0000 | -0.0187 | False | no_simple_fill_filter_repair |
| expanding_fold1 | tfi_long_flat | high | trade_window_count <= 1 | 95 | 0.0105 | -2.0000 | -2.0000 | -0.0211 | False | no_simple_fill_filter_repair |

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
| tfi_short_flat | mid | microprice_dev_bps >= 0.6210653535 | 42 | 0.0476 | 7.9838 | 0.5070 | 0.3802 | False |
| tfi_short_flat | mid | signed_microprice_dev_bps <= -0.6210653535 | 42 | 0.0476 | 7.9838 | 0.5070 | 0.3802 | False |
| tfi_follow_flat | high | entry_spread_bps >= 2.611682185 | 102 | 0.0196 | 19.0368 | -2.9005 | 0.3733 | False |
| tfi_follow_flat | high | entry_quality_score >= 0.5624623203 | 203 | 0.0493 | 7.4834 | -8.5411 | 0.3686 | False |
| tfi_short_flat | high | queue_imbalance_5 <= 0.1669248094 | 235 | 0.0426 | 8.4566 | -20.0526 | 0.3599 | False |
| tfi_short_flat | high | signed_queue_imbalance_5 >= -0.1669248094 | 235 | 0.0426 | 8.4566 | -20.0526 | 0.3599 | False |
| tfi_follow_flat | high | mlofi_roll10_l1 <= -0.9015060987 | 102 | 0.0490 | 7.2679 | -15.3687 | 0.3563 | False |
| tfi_short_flat | high | hour_bucket <= 4 | 79 | 0.0506 | 6.9933 | -17.0066 | 0.3541 | False |
| tfi_short_flat | mid | entry_quality_score >= 0.5168364234 | 42 | 0.0476 | 7.3390 | -0.6537 | 0.3495 | False |
| tfi_short_flat | high | trade_window_count >= 2 | 115 | 0.0696 | 5.0221 | -28.5282 | 0.3494 | False |

## Decision

The active goal is not complete. The research framework is substantially systematized, but the explicit `stable real-cost >2bps capture` requirement is not satisfied by current L2 queue-fill evidence.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_repair_filters_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_fill_repair_audit.py --l2-queue-run-tag 20260518_ccusdt_v2_l2_queue_fill_all_practical_v1 --queue-release-run-tag 20260518_ccusdt_v2_queue_release_pivot_fast_v1 --liquidity-envelope-run-tag 20260518_ccusdt_v2_liquidity_envelope_audit_v1 --run-tag 20260518_ccusdt_v2_fill_repair_audit_all_practical_v1
```

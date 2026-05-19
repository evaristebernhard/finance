# CCUSDT V2 Framework Run

Status: `20260518_ccusdt_v2_framework_v1` from source panel `20260517_ccusdt_fixed_factors_v3`.

Guardrail: `research_only_v2_framework_no_execution_recommendation_no_alpha_claim`.

This is a fold-valid research framework run. It is not queue-position fill evidence, not a live execution simulation, not trading advice, and not an alpha claim.

## Scope

- Trigger classes: `tfi_short_flat, tfi_long_flat, tfi_follow_flat, tfi_short_stale25, tfi_event_active`.
- Folds: `expanding_fold1, expanding_fold2, expanding_fold3`.
- Validation entries with path labels: `6447`.
- Cost proxy: `toy_maker_light + 2bps`, with scorecard retaining execution-realism no-go.

## Scorecard

| fold | trigger_class | entry_quality_bin | entries | net_realistic_mean_bps | net_realistic_plus2_mean_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | residual_net_mean_bps | top10_net_share_of_total_net | sample_pass | economics_pass | controls_pass | residual_pass | tail_pass | risk_pass | execution_realism_pass | scorecard_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_stale25 | low | 38 | 2.8540 | 0.8540 | 0.0100 | 2.1879 | 3.1062 | 1.1792 | False | True | True | True | False | False | False | research_continue_needs_cost_tail_or_risk_repair |
| expanding_fold3 | tfi_follow_flat | high | 508 | 1.0518 | -0.9482 | 0.0000 | 2.7949 | 0.9169 | 3.7639 | True | False | True | True | False | False | False | research_continue_needs_cost_tail_or_risk_repair |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.8973 | -1.1027 | 0.0000 | 2.3911 | 0.9587 | 4.2913 | False | False | True | True | False | True | False | research_continue_needs_cost_tail_or_risk_repair |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.7035 | -1.2965 | 0.0100 | 2.9888 | 0.5518 | 5.8697 | False | False | True | True | False | False | False | research_continue_needs_cost_tail_or_risk_repair |
| expanding_fold3 | tfi_event_active | mid | 72 | 4.7892 | 2.7892 | 0.0900 | 1.2808 | 4.7788 | 1.5381 | False | True | False | True | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_short_stale25 | high | 54 | 3.4950 | 1.4950 | 0.5900 | -0.1208 | 3.4929 | 1.9989 | False | True | False | True | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_short_stale25 | mid | 39 | 3.0857 | 1.0857 | 0.3100 | 0.8346 | 3.2063 | 1.8969 | False | True | False | True | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_short_flat | mid | 206 | 2.0549 | 0.0549 | 0.0350 | 1.2148 | 1.7336 | 1.4527 | False | True | False | True | False | False | False | research_only_not_promoted |
| expanding_fold1 | tfi_short_stale25 | mid | 5 | 1.0830 | -0.9170 | 1.0000 | -0.1010 | 0.7250 | 0.7672 | False | False | False | True | True | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_event_active | mid | 28 | 1.0821 | -0.9179 | 0.0250 | 1.3299 | 0.9399 | 2.4415 | False | False | False | True | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_event_active | high | 85 | 1.0086 | -0.9914 | 0.2700 | 0.3891 | 0.8069 | 3.8888 | False | False | False | True | False | True | False | research_only_not_promoted |
| expanding_fold3 | tfi_short_flat | low | 129 | 1.0006 | -0.9994 | 0.0500 | 1.1491 | 0.8153 | 3.8179 | False | False | False | True | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_short_stale25 | low | 31 | 0.5313 | -1.4687 | 0.5900 | -0.1117 | 0.6074 | 3.3904 | False | False | False | True | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_event_active | low | 53 | 0.3455 | -1.6545 | 0.0150 | 1.5931 | 0.5948 | 8.7863 | False | False | False | True | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_long_flat | mid | 99 | 0.2218 | -1.7782 | 0.0000 | 4.1985 | -0.1819 | 18.4892 | False | False | True | False | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_follow_flat | low | 298 | 0.1830 | -1.8170 | 0.0950 | 0.6887 | 0.0261 | 14.1683 | False | False | False | True | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_follow_flat | mid | 286 | 0.1264 | -1.8736 | 0.0000 | 2.1315 | -0.0707 | 25.8106 | False | False | True | False | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_follow_flat | low | 335 | -0.0252 | -2.0252 | 0.0000 | 2.1980 | -0.3177 |  | False | False | True | False | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_long_flat | low | 199 | -0.0339 | -2.0339 | 0.0000 | 3.9958 | -0.8261 |  | False | False | True | False | False | False | False | research_only_not_promoted |
| expanding_fold1 | tfi_event_active | low | 21 | -0.1475 | -2.1475 | 0.7100 | -0.1669 | -0.3955 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_follow_flat | mid | 291 | -0.2523 | -2.2523 | 0.0050 | 1.1704 | -0.5472 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_event_active | low | 37 | -0.3377 | -2.3377 | 0.8350 | -0.4331 | -0.1712 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_long_flat | mid | 102 | -0.3905 | -2.3905 | 0.1350 | 1.0810 | -0.6150 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_long_flat | high | 137 | -0.5484 | -2.5484 | 0.0000 | 2.2346 | -0.7701 |  | False | False | True | False | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_event_active | high | 56 | -0.7590 | -2.7590 | 0.5800 | -0.0953 | -0.7037 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold1 | tfi_short_stale25 | low | 17 | -0.7922 | -2.7922 | 0.7350 | -0.2062 | -0.8887 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold1 | tfi_event_active | high | 31 | -0.7953 | -2.7953 | 0.4800 | 0.0749 | -0.6409 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold3 | tfi_short_flat | mid | 196 | -0.9078 | -2.9078 | 0.2000 | 0.7155 | -1.0482 |  | False | False | False | False | False | False | False | research_only_not_promoted |
| expanding_fold2 | tfi_follow_flat | high | 337 | -1.2110 | -3.2110 | 0.1400 | 0.7495 | -1.5223 |  | False | False | False | False | False | True | False | research_only_not_promoted |
| expanding_fold2 | tfi_long_flat | low | 142 | -1.2309 | -3.2309 | 0.0150 | 1.4214 | -1.6381 |  | False | False | False | False | False | False | False | research_only_not_promoted |

## Entry Quality

| fold | trigger_class | entry_quality_bin | entry_quality_model | entries | net_realistic_mean_bps | net_realistic_plus2_mean_bps | gt_2bps_rate | cost_cross_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_event_active | mid | logistic_entry_quality | 72 | 4.7892 | 2.7892 | 0.3889 | 0.5000 |
| expanding_fold3 | tfi_short_stale25 | high | logistic_entry_quality | 54 | 3.4950 | 1.4950 | 0.3519 | 0.4074 |
| expanding_fold3 | tfi_short_stale25 | mid | logistic_entry_quality | 39 | 3.0857 | 1.0857 | 0.4615 | 0.5897 |
| expanding_fold3 | tfi_short_stale25 | low | logistic_entry_quality | 38 | 2.8540 | 0.8540 | 0.5263 | 0.5526 |
| expanding_fold2 | tfi_short_flat | mid | logistic_entry_quality | 206 | 2.0549 | 0.0549 | 0.3641 | 0.5000 |
| expanding_fold1 | tfi_short_stale25 | mid | logistic_entry_quality | 5 | 1.0830 | -0.9170 | 0.4000 | 0.8000 |
| expanding_fold2 | tfi_event_active | mid | logistic_entry_quality | 28 | 1.0821 | -0.9179 | 0.3571 | 0.5000 |
| expanding_fold3 | tfi_follow_flat | high | logistic_entry_quality | 508 | 1.0518 | -0.9482 | 0.3622 | 0.4685 |
| expanding_fold3 | tfi_event_active | high | logistic_entry_quality | 85 | 1.0086 | -0.9914 | 0.4118 | 0.5059 |
| expanding_fold3 | tfi_short_flat | low | logistic_entry_quality | 129 | 1.0006 | -0.9994 | 0.3721 | 0.5116 |
| expanding_fold3 | tfi_short_flat | high | logistic_entry_quality | 391 | 0.8973 | -1.1027 | 0.3708 | 0.4629 |
| expanding_fold3 | tfi_long_flat | high | logistic_entry_quality | 195 | 0.7035 | -1.2965 | 0.3282 | 0.4308 |
| expanding_fold2 | tfi_short_stale25 | low | logistic_entry_quality | 31 | 0.5313 | -1.4687 | 0.3226 | 0.4516 |
| expanding_fold3 | tfi_event_active | low | logistic_entry_quality | 53 | 0.3455 | -1.6545 | 0.4717 | 0.4906 |
| expanding_fold3 | tfi_long_flat | mid | logistic_entry_quality | 99 | 0.2218 | -1.7782 | 0.3131 | 0.4040 |
| expanding_fold2 | tfi_follow_flat | low | logistic_entry_quality | 298 | 0.1830 | -1.8170 | 0.3356 | 0.4597 |
| expanding_fold3 | tfi_follow_flat | mid | logistic_entry_quality | 286 | 0.1264 | -1.8736 | 0.3077 | 0.4336 |
| expanding_fold3 | tfi_follow_flat | low | logistic_entry_quality | 335 | -0.0252 | -2.0252 | 0.3731 | 0.4597 |
| expanding_fold3 | tfi_long_flat | low | logistic_entry_quality | 199 | -0.0339 | -2.0339 | 0.3819 | 0.4925 |
| expanding_fold1 | tfi_event_active | low | logistic_entry_quality | 21 | -0.1475 | -2.1475 | 0.3333 | 0.6190 |

## Matched Controls

| fold | trigger_class | entry_quality_bin | entries | signal_mean_bps | matched_random_mean_p50_bps | matched_random_mean_p95_bps | prob_random_mean_ge_signal | signal_minus_random_p50_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_long_flat | mid | 99 | 0.2218 | -3.9767 | -1.6795 | 0.0000 | 4.1985 |
| expanding_fold3 | tfi_long_flat | low | 199 | -0.0339 | -4.0296 | -2.3045 | 0.0000 | 3.9958 |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.7035 | -2.2854 | -0.4306 | 0.0100 | 2.9888 |
| expanding_fold3 | tfi_follow_flat | high | 508 | 1.0518 | -1.7431 | -0.6876 | 0.0000 | 2.7949 |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.8973 | -1.4938 | -0.3260 | 0.0000 | 2.3911 |
| expanding_fold2 | tfi_long_flat | high | 137 | -0.5484 | -2.7830 | -1.5989 | 0.0000 | 2.2346 |
| expanding_fold3 | tfi_follow_flat | low | 335 | -0.0252 | -2.2231 | -1.3629 | 0.0000 | 2.1980 |
| expanding_fold3 | tfi_short_stale25 | low | 38 | 2.8540 | 0.6661 | 2.3424 | 0.0100 | 2.1879 |
| expanding_fold3 | tfi_follow_flat | mid | 286 | 0.1264 | -2.0051 | -0.8277 | 0.0000 | 2.1315 |
| expanding_fold3 | tfi_event_active | low | 53 | 0.3455 | -1.2476 | -0.1068 | 0.0150 | 1.5931 |
| expanding_fold2 | tfi_long_flat | low | 142 | -1.2309 | -2.6524 | -1.6101 | 0.0150 | 1.4214 |
| expanding_fold2 | tfi_event_active | mid | 28 | 1.0821 | -0.2477 | 0.6242 | 0.0250 | 1.3299 |
| expanding_fold3 | tfi_event_active | mid | 72 | 4.7892 | 3.5085 | 5.2051 | 0.0900 | 1.2808 |
| expanding_fold2 | tfi_short_flat | mid | 206 | 2.0549 | 0.8401 | 1.9737 | 0.0350 | 1.2148 |
| expanding_fold1 | tfi_follow_flat | low | 186 | -1.9499 | -3.1585 | -2.2846 | 0.0050 | 1.2087 |
| expanding_fold2 | tfi_follow_flat | mid | 291 | -0.2523 | -1.4228 | -0.6692 | 0.0050 | 1.1704 |
| expanding_fold3 | tfi_short_flat | low | 129 | 1.0006 | -0.1485 | 0.9557 | 0.0500 | 1.1491 |
| expanding_fold2 | tfi_long_flat | mid | 102 | -0.3905 | -1.4716 | 0.0680 | 0.1350 | 1.0810 |
| expanding_fold2 | tfi_short_stale25 | high | 31 | -3.9019 | -4.9171 | -3.1494 | 0.2000 | 1.0152 |
| expanding_fold1 | tfi_short_flat | mid | 132 | -3.0803 | -4.0550 | -3.3066 | 0.0100 | 0.9747 |

## Risk Read

| fold | trigger_class | entry_quality_bin | stop_bps | entries | stop_hit_rate | delta_net_mean_bps | delta_cvar10_bps | stop_given_fixed_cost_winner_rate | save_to_kill_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold2 | tfi_short_flat | low | 5.0000 | 190 | 0.2684 | 0.6511 | 18.6214 | 0.0263 | 5.6000 |
| expanding_fold3 | tfi_long_flat | low | 5.0000 | 199 | 0.3065 | 0.6627 | 16.9796 | 0.0352 | 4.4286 |
| expanding_fold2 | tfi_short_flat | high | 5.0000 | 219 | 0.2511 | 0.3226 | 15.0771 | 0.0365 | 3.5000 |
| expanding_fold3 | tfi_long_flat | mid | 5.0000 | 99 | 0.2727 | -0.7348 | 14.7668 | 0.0505 | 2.0000 |
| expanding_fold2 | tfi_short_flat | low | 8.0000 | 190 | 0.1789 | 0.4893 | 14.6152 | 0.0211 | 3.0000 |
| expanding_fold2 | tfi_follow_flat | high | 5.0000 | 337 | 0.2285 | 0.3166 | 14.4937 | 0.0267 | 3.6667 |
| expanding_fold3 | tfi_event_active | high | 5.0000 | 85 | 0.2706 | 0.8673 | 14.3327 | 0.0235 | 8.0000 |
| expanding_fold3 | tfi_short_stale25 | low | 5.0000 | 38 | 0.2368 | 0.9978 | 13.5940 | 0.0263 | 4.0000 |
| expanding_fold2 | tfi_short_flat | high | 8.0000 | 219 | 0.1598 | 0.1569 | 13.2851 | 0.0228 | 3.0000 |
| expanding_fold3 | tfi_short_stale25 | mid | 5.0000 | 39 | 0.3590 | 0.0901 | 13.0087 | 0.0769 | 2.3333 |
| expanding_fold3 | tfi_long_flat | mid | 8.0000 | 99 | 0.1616 | -0.6147 | 12.9712 | 0.0202 | 3.5000 |
| expanding_fold2 | tfi_short_flat | low | 12.0000 | 190 | 0.1105 | 0.4106 | 12.4663 | 0.0158 | 3.0000 |
| expanding_fold3 | tfi_long_flat | low | 8.0000 | 199 | 0.1960 | 0.4673 | 12.3992 | 0.0151 | 6.6667 |
| expanding_fold2 | tfi_follow_flat | high | 8.0000 | 337 | 0.1276 | 0.4595 | 12.0956 | 0.0178 | 2.5000 |
| expanding_fold3 | tfi_follow_flat | mid | 5.0000 | 286 | 0.2727 | 0.5486 | 11.8090 | 0.0175 | 7.6000 |
| expanding_fold3 | tfi_event_active | low | 5.0000 | 53 | 0.3019 | 0.5187 | 11.6194 | 0.0566 | 3.0000 |
| expanding_fold3 | tfi_event_active | high | 8.0000 | 85 | 0.2235 | 0.6570 | 11.4072 | 0.0118 | 12.0000 |
| expanding_fold3 | tfi_long_flat | low | 12.0000 | 199 | 0.1307 | 0.5389 | 11.2649 | 0.0101 | 7.0000 |
| expanding_fold3 | tfi_short_flat | high | 5.0000 | 391 | 0.3197 | -0.2857 | 11.2453 | 0.0307 | 5.2500 |
| expanding_fold3 | tfi_long_flat | mid | 12.0000 | 99 | 0.1515 | -0.5124 | 10.7454 | 0.0101 | 6.0000 |

## Decision

Execution status remains no-go because this run still uses a snapshot-frame factor panel and no queue/fill/latency model. Rows that pass research controls are candidates for one further execution-realism pass, not deployable strategies.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_quote_transition_labels_20260518_ccusdt_v2_framework_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_residual_controls_20260518_ccusdt_v2_framework_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_matched_controls_20260518_ccusdt_v2_framework_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_entry_quality_bins_20260518_ccusdt_v2_framework_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_exit_shape_20260518_ccusdt_v2_framework_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_risk_control_20260518_ccusdt_v2_framework_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_summary_20260518_ccusdt_v2_framework_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_research_framework.py --matched-random-iters 200
```

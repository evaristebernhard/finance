# CCUSDT TFI OOS Decay Check: 2026-05-17

Status: `20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1`.

Guardrail: `research_only_oos_decay_check_locked_prior_no_execution_recommendation_no_alpha_claim`.

This check applies locked Fold3 TFI thresholds, mutually-exclusive positive-EV buckets, and the existing weak-overlay strategy weights to the OOS day. It does not optimize on 2026-05-17.

## Locked Inputs

- OOS panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1\derived\ccusdt_v1_fixed_event_factor_panel\run_tag=20260518_ccusdt_fixed_factors_oos_day20260517_v1`.
- Historical entries: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv`.
- Historical mutual buckets: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`.
- Eligible buckets: `tfi_follow_flat+tfi_long_flat, tfi_follow_flat+tfi_long_flat+tfi_event_active, tfi_follow_flat+tfi_short_flat, tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active, tfi_long_flat`.
- Overlay: `weak_overlay_rank12`, frames_since_mid_change high 10%, historical threshold `59.8000`.
- Trigger thresholds: `{"tfi_event_active": [-1.0, 1.0], "tfi_follow_flat": [-1.0, 1.0], "tfi_long_flat": [-1.0, 1.0], "tfi_short_flat": [-1.0, 1.0], "tfi_short_stale25": [-1.0, 1.0]}`.

## OOS Bucket Readout

| membership_set | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | net_median_bps | net_p90_bps | gt2_rate | cost_hit_rate | total_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_follow_flat+tfi_long_flat | 72 | 4.3214 | 2.1244 | 2.1970 | 2.9550 | 11.7616 | 0.5278 | 0.4444 | 158.1841 |
| tfi_follow_flat+tfi_short_flat | 104 | 3.2161 | 2.1369 | 1.0793 | -0.2752 | 12.9602 | 0.4135 | 0.5192 | 112.2438 |
| tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 12 | 7.3161 | 2.1137 | 5.2024 | 7.5700 | 11.6453 | 0.6667 | 0.3333 | 62.4289 |
| tfi_follow_flat+tfi_long_flat+tfi_event_active | 9 | 7.5557 | 2.1717 | 5.3840 | 3.7240 | 16.5928 | 0.6667 | 0.3333 | 48.4564 |
| tfi_long_flat+tfi_event_active | 1 | 46.8538 | 1.4911 | 45.3627 | 45.3627 | 45.3627 | 1.0000 | 0.0000 | 45.3627 |
| tfi_short_stale25+tfi_event_active | 1 | 6.4950 | 2.6237 | 3.8712 | 3.8712 | 3.8712 | 1.0000 | 0.0000 | 3.8712 |
| tfi_short_flat | 4 | 2.4990 | 2.1367 | 0.3623 | 2.4901 | 12.9306 | 0.5000 | 0.2500 | 1.4494 |
| tfi_long_flat | 2 | -22.6857 | 1.8955 | -24.5812 | -24.5812 | -5.8464 | 0.0000 | 1.0000 | -49.1625 |

## Decay Comparison

| scope | entries | exposure_units | total_weighted_net_bps | weighted_mean_net_bps | weighted_median_net_bps | weighted_gt2_rate | cost_hit_rate | positive_net_bps | negative_net_bps | total_net_bps | net_mean_bps | net_median_bps | gt2_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold1_weighted_reference |  |  | -420.1420 | -0.9214 |  | 0.2873 | 0.6831 |  |  |  |  |  |  |
| fold3_weighted_reference |  |  | 3168.6474 | 3.6909 |  | 0.4843 | 0.4950 |  |  |  |  |  |  |
| oos_2026_05_17_weighted_locked | 199.0000 | 122.0000 | 280.9097 | 2.3025 | 2.7684 | 0.5123 | 0.4508 | 630.7880 | -349.8783 |  |  |  |  |
| eligible_union | 199.0000 |  |  |  |  |  | 0.4774 | 948.9177 | -616.7670 | 332.1506 | 1.6691 | 1.2687 | 0.4774 |

## Interpretation

- Decision: `right_tail_still_present`.
- Weighted OOS mean: `2.3025` bps versus Fold3 `3.6909` bps and Fold1 `-0.9214` bps.
- Weighted OOS cost-hit rate: `0.4508` versus Fold3 `0.4950`.
- OOS equal-union net p90: `11.8395` bps; net median `1.2687` bps.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_entries_20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_buckets_20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_union_20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_summary_20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_oos_decay_check.py --oos-source-run-tag 20260518_ccusdt_fixed_factors_oos_day20260517_v1 --oos-date 2026-05-17 --run-tag 20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1
```

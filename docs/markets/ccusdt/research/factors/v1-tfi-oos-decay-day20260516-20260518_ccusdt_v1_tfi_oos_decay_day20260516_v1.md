# CCUSDT TFI OOS Decay Check: 2026-05-16

Status: `20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1`.

Guardrail: `research_only_oos_decay_check_locked_prior_no_execution_recommendation_no_alpha_claim`.

This check applies locked Fold3 TFI thresholds, mutually-exclusive positive-EV buckets, and the existing weak-overlay strategy weights to the OOS day. It does not optimize on 2026-05-16.

## Locked Inputs

- OOS panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1\derived\ccusdt_v1_fixed_event_factor_panel\run_tag=20260518_ccusdt_fixed_factors_oos_day20260516_v1`.
- Historical entries: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv`.
- Historical mutual buckets: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`.
- Eligible buckets: `tfi_follow_flat+tfi_long_flat, tfi_follow_flat+tfi_long_flat+tfi_event_active, tfi_follow_flat+tfi_short_flat, tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active, tfi_long_flat`.
- Overlay: `weak_overlay_rank12`, frames_since_mid_change high 10%, historical threshold `59.8000`.
- Trigger thresholds: `{"tfi_event_active": [-1.0, 1.0], "tfi_follow_flat": [-1.0, 1.0], "tfi_long_flat": [-1.0, 1.0], "tfi_short_flat": [-1.0, 1.0], "tfi_short_stale25": [-1.0, 1.0]}`.

## OOS Bucket Readout

| membership_set | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | net_median_bps | net_p90_bps | gt2_rate | cost_hit_rate | total_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_follow_flat+tfi_long_flat+tfi_event_active | 8 | 7.9032 | 2.0098 | 5.8934 | 1.5256 | 27.8511 | 0.5000 | 0.5000 | 47.1470 |
| tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 17 | 3.3662 | 1.9809 | 1.3853 | -0.6831 | 8.7763 | 0.4118 | 0.5882 | 23.5499 |
| tfi_short_stale25+tfi_event_active | 1 | 23.6657 | 2.1053 | 21.5603 | 21.5603 | 21.5603 | 1.0000 | 0.0000 | 21.5603 |
| tfi_long_flat+tfi_event_active | 1 | 0.0000 | 2.6588 | -2.6588 | -2.6588 | -2.6588 | 0.0000 | 1.0000 | -2.6588 |
| tfi_long_flat | 15 | 1.8163 | 2.3661 | -0.5498 | -0.1680 | 10.7514 | 0.4667 | 0.5333 | -8.2477 |
| tfi_short_flat+tfi_short_stale25+tfi_event_active | 1 | -13.3914 | 3.0087 | -16.4001 | -16.4001 | -16.4001 | 0.0000 | 1.0000 | -16.4001 |
| tfi_short_flat | 15 | 0.9217 | 2.0788 | -1.1571 | -1.1641 | 7.8586 | 0.2667 | 0.6667 | -17.3569 |
| tfi_follow_flat+tfi_short_flat | 111 | 1.7064 | 2.0653 | -0.3589 | -1.1576 | 11.8119 | 0.3964 | 0.5676 | -39.8364 |
| tfi_follow_flat+tfi_long_flat | 110 | 1.1384 | 2.1831 | -1.0447 | -1.3300 | 18.0743 | 0.4000 | 0.5636 | -114.9157 |

## Decay Comparison

| scope | entries | exposure_units | total_weighted_net_bps | weighted_mean_net_bps | weighted_median_net_bps | weighted_gt2_rate | cost_hit_rate | positive_net_bps | negative_net_bps | total_net_bps | net_mean_bps | net_median_bps | gt2_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold1_weighted_reference |  |  | -420.1420 | -0.9214 |  | 0.2873 | 0.6831 |  |  |  |  |  |  |
| fold3_weighted_reference |  |  | 3168.6474 | 3.6909 |  | 0.4843 | 0.4950 |  |  |  |  |  |  |
| oos_2026_05_16_weighted_locked | 261.0000 | 163.0000 | 39.2337 | 0.2407 | -0.8355 | 0.4141 | 0.5613 | 727.1193 | -687.8857 |  |  |  |  |
| eligible_union | 261.0000 |  |  |  |  |  | 0.5632 | 1195.3842 | -1287.6872 | -92.3030 | -0.3537 | -1.1584 | 0.4061 |

## Interpretation

- Decision: `partial_decay_trade_smaller`.
- Weighted OOS mean: `0.2407` bps versus Fold3 `3.6909` bps and Fold1 `-0.9214` bps.
- Weighted OOS cost-hit rate: `0.5613` versus Fold3 `0.4950`.
- OOS equal-union net p90: `14.5887` bps; net median `-1.1584` bps.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_entries_20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_buckets_20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_union_20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_summary_20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_oos_decay_check.py --run-tag 20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1
```

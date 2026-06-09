# CCUSDT TFI OOS Decay Check: 2026-05-18

Status: `20260519_ccusdt_v1_tfi_oos_decay_day20260518_v1`.

Guardrail: `research_only_oos_decay_check_locked_prior_no_execution_recommendation_no_alpha_claim`.

This check applies locked Fold3 TFI thresholds, mutually-exclusive positive-EV buckets, and the existing weak-overlay strategy weights to the OOS day. It does not optimize on 2026-05-18.

## Locked Inputs

- OOS panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1\derived\ccusdt_v1_fixed_event_factor_panel\run_tag=20260519_ccusdt_fixed_factors_oos_day20260518_v1`.
- Historical entries: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv`.
- Historical mutual buckets: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`.
- Eligible buckets: `tfi_follow_flat+tfi_long_flat, tfi_follow_flat+tfi_long_flat+tfi_event_active, tfi_follow_flat+tfi_short_flat, tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active, tfi_long_flat`.
- Overlay: `weak_overlay_rank12`, frames_since_mid_change high 10%, historical threshold `59.8000`.
- Trigger thresholds: `{"tfi_event_active": [-1.0, 1.0], "tfi_follow_flat": [-1.0, 1.0], "tfi_long_flat": [-1.0, 1.0], "tfi_short_flat": [-1.0, 1.0], "tfi_short_stale25": [-1.0, 1.0]}`.

## OOS Bucket Readout

| membership_set | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | net_median_bps | net_p90_bps | gt2_rate | cost_hit_rate | total_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 21 | 5.9514 | 2.0874 | 3.8641 | -0.1675 | 16.7386 | 0.4286 | 0.5238 | 81.1459 |
| tfi_long_flat | 14 | 7.3377 | 2.3077 | 5.0300 | 3.8984 | 17.5268 | 0.6429 | 0.2143 | 70.4199 |
| tfi_follow_flat+tfi_long_flat | 85 | 2.6565 | 2.1637 | 0.4928 | -1.0000 | 11.5898 | 0.4000 | 0.5765 | 41.8875 |
| tfi_short_stale25+tfi_event_active | 1 | 27.7646 | 1.8173 | 25.9474 | 25.9474 | 25.9474 | 1.0000 | 0.0000 | 25.9474 |
| tfi_short_flat | 11 | 4.1655 | 2.0621 | 2.1034 | -0.6687 | 11.2038 | 0.4545 | 0.5455 | 23.1375 |
| tfi_follow_flat+tfi_long_flat+tfi_event_active | 8 | 2.9895 | 1.8813 | 1.1082 | -0.4279 | 6.9750 | 0.3750 | 0.6250 | 8.8656 |
| tfi_long_flat+tfi_event_active | 1 | 9.0002 | 2.5000 | 6.5002 | 6.5002 | 6.5002 | 1.0000 | 0.0000 | 6.5002 |
| tfi_event_active | 1 | 5.8563 | 2.3013 | 3.5550 | 3.5550 | 3.5550 | 1.0000 | 0.0000 | 3.5550 |
| tfi_follow_flat+tfi_short_flat | 176 | 0.8980 | 2.1158 | -1.2178 | -1.9852 | 10.7045 | 0.3409 | 0.6420 | -214.3290 |

## Decay Comparison

| scope | entries | exposure_units | total_weighted_net_bps | weighted_mean_net_bps | weighted_median_net_bps | weighted_gt2_rate | cost_hit_rate | positive_net_bps | negative_net_bps | total_net_bps | net_mean_bps | net_median_bps | gt2_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold1_weighted_reference |  |  | -420.1420 | -0.9214 |  | 0.2873 | 0.6831 |  |  |  |  |  |  |
| fold3_weighted_reference |  |  | 3168.6474 | 3.6909 |  | 0.4843 | 0.4950 |  |  |  |  |  |  |
| oos_2026_05_18_weighted_locked | 304.0000 | 191.0000 | 127.0371 | 0.6651 | -1.0000 | 0.3848 | 0.5864 | 718.7397 | -591.7026 |  |  |  |  |
| eligible_union | 304.0000 |  |  |  |  |  | 0.5954 | 1056.4907 | -1068.5008 | -12.0101 | -0.0395 | -1.4983 | 0.3783 |

## Interpretation

- Decision: `partial_decay_trade_smaller`.
- Weighted OOS mean: `0.6651` bps versus Fold3 `3.6909` bps and Fold1 `-0.9214` bps.
- Weighted OOS cost-hit rate: `0.5864` versus Fold3 `0.4950`.
- OOS equal-union net p90: `11.3205` bps; net median `-1.4983` bps.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_entries_20260519_ccusdt_v1_tfi_oos_decay_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_buckets_20260519_ccusdt_v1_tfi_oos_decay_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_union_20260519_ccusdt_v1_tfi_oos_decay_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_oos_decay_summary_20260519_ccusdt_v1_tfi_oos_decay_day20260518_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_oos_decay_check.py --oos-source-run-tag 20260519_ccusdt_fixed_factors_oos_day20260518_v1 --oos-date 2026-05-18 --run-tag 20260519_ccusdt_v1_tfi_oos_decay_day20260518_v1
```

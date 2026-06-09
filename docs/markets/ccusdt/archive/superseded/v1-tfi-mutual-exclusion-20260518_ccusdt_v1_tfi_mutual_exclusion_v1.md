# CCUSDT V1 TFI Mutual Exclusion

Status: `20260518_ccusdt_v1_tfi_mutual_exclusion_v1`.

Guardrail: `research_only_tfi_mutual_exclusion_no_execution_recommendation_no_alpha_claim`.

This report decomposes the TFI family by exact entry-level membership. It is a structure-understanding artifact, not an execution recommendation.

## Objective

Clarify whether the profitable TFI structures are separate effects, parent/child states, or overlapping views of the same entries.

## Scope

- Source entries: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv`.
- Unique entry keys: `3052`.
- Structures: `tfi_follow_flat, tfi_short_flat, tfi_long_flat, tfi_short_stale25, tfi_event_active`.

## Fold3 Mutual Buckets

| membership_set | entries | gross_mean_bps | gross_median_bps | cost_mean_bps | net_mean_bps | net_median_bps | net_cvar10_bps | mfe_mean_bps | mae_mean_bps | total_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 114 | 7.8982 | 4.9748 | 2.0179 | 5.8804 | 2.8471 | -19.5182 | 13.4878 | -4.1613 | 670.3600 |
| tfi_follow_flat+tfi_long_flat+tfi_event_active | 66 | 4.9561 | 4.3946 | 1.9579 | 2.9983 | 2.2486 | -31.2816 | 13.5602 | -4.6662 | 197.8854 |
| tfi_long_flat | 35 | 4.7475 | 3.3744 | 2.0738 | 2.6736 | 0.9939 | -38.6522 | 14.5640 | -6.8464 | 93.5768 |
| tfi_short_flat+tfi_short_stale25+tfi_event_active | 2 | 4.9437 | 4.9437 | 2.5035 | 2.4401 | 2.4401 | 0.7160 | 12.8780 | 4.6208 | 4.8803 |
| tfi_follow_flat+tfi_long_flat | 390 | 4.2218 | 1.2993 | 2.0602 | 2.1615 | -0.6752 | -28.4731 | 10.9730 | -5.9043 | 843.0004 |
| tfi_follow_flat+tfi_short_flat | 559 | 4.0249 | 1.5847 | 2.0414 | 1.9835 | -0.5124 | -21.5747 | 10.3630 | -4.4998 | 1108.7730 |
| tfi_long_flat+tfi_event_active | 2 | 3.6964 | 3.6964 | 1.7302 | 1.9662 | 1.9662 | -1.3263 | 3.8568 | 0.0000 | 3.9323 |
| tfi_short_stale25+tfi_event_active | 15 | 2.3546 | 2.9332 | 2.0691 | 0.2855 | 0.1407 | -17.1534 | 8.4664 | -5.0890 | 4.2827 |
| tfi_event_active | 11 | 0.9067 | 1.2655 | 2.0409 | -1.1342 | -0.6836 | -19.5524 | 10.4204 | -7.2178 | -12.4765 |
| tfi_short_flat | 41 | 0.9042 | 0.0000 | 2.1236 | -1.2194 | -1.9271 | -27.5980 | 11.5444 | -6.5185 | -49.9957 |

## Fold3 Pairwise Overlap

| left_trigger | right_trigger | left_entries | right_entries | overlap_entries | left_overlap_rate | right_overlap_rate | overlap_net_mean_bps | overlap_gross_mean_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tfi_follow_flat | tfi_short_flat | 1129 | 716 | 673 | 0.5961 | 0.9399 | 2.6436 | 4.6810 |
| tfi_short_flat | tfi_follow_flat | 716 | 1129 | 673 | 0.9399 | 0.5961 | 2.6436 | 4.6810 |
| tfi_follow_flat | tfi_long_flat | 1129 | 493 | 456 | 0.4039 | 0.9249 | 2.2826 | 4.3281 |
| tfi_long_flat | tfi_follow_flat | 493 | 1129 | 456 | 0.9249 | 0.4039 | 2.2826 | 4.3281 |
| tfi_event_active | tfi_follow_flat | 210 | 1129 | 180 | 0.8571 | 0.1594 | 4.8236 | 6.8194 |
| tfi_follow_flat | tfi_event_active | 1129 | 210 | 180 | 0.1594 | 0.8571 | 4.8236 | 6.8194 |
| tfi_event_active | tfi_short_stale25 | 210 | 131 | 131 | 0.6238 | 1.0000 | 5.1872 | 7.2183 |
| tfi_short_stale25 | tfi_event_active | 131 | 210 | 131 | 1.0000 | 0.6238 | 5.1872 | 7.2183 |
| tfi_event_active | tfi_short_flat | 210 | 716 | 116 | 0.5524 | 0.1620 | 5.8210 | 7.8473 |
| tfi_short_flat | tfi_event_active | 716 | 210 | 116 | 0.1620 | 0.5524 | 5.8210 | 7.8473 |
| tfi_short_flat | tfi_short_stale25 | 716 | 131 | 116 | 0.1620 | 0.8855 | 5.8210 | 7.8473 |
| tfi_short_stale25 | tfi_short_flat | 131 | 716 | 116 | 0.8855 | 0.1620 | 5.8210 | 7.8473 |
| tfi_follow_flat | tfi_short_stale25 | 1129 | 131 | 114 | 0.1010 | 0.8702 | 5.8804 | 7.8982 |
| tfi_short_stale25 | tfi_follow_flat | 131 | 1129 | 114 | 0.8702 | 0.1010 | 5.8804 | 7.8982 |
| tfi_event_active | tfi_long_flat | 210 | 493 | 68 | 0.3238 | 0.1379 | 2.9679 | 4.9191 |
| tfi_long_flat | tfi_event_active | 493 | 210 | 68 | 0.1379 | 0.3238 | 2.9679 | 4.9191 |
| tfi_long_flat | tfi_short_flat | 493 | 716 | 0 | 0.0000 | 0.0000 |  |  |
| tfi_long_flat | tfi_short_stale25 | 493 | 131 | 0 | 0.0000 | 0.0000 |  |  |
| tfi_short_flat | tfi_long_flat | 716 | 493 | 0 | 0.0000 | 0.0000 |  |  |
| tfi_short_stale25 | tfi_long_flat | 131 | 493 | 0 | 0.0000 | 0.0000 |  |  |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_membership_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pairwise_overlap_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_exclusion_summary_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_mutual_exclusion.py --run-tag 20260518_ccusdt_v1_tfi_mutual_exclusion_v1
```

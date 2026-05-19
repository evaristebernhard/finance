# CCUSDT V1 TFI Small Path Manager

Status: `20260519_ccusdt_v1_tfi_small_path_manager_v1`.

Guardrail: `research_only_small_price_path_manager_no_execution_recommendation`.

## Model

This is a small path manager, not a fitted entry model. It uses only:

$$
H_t=\max_{u\le t}R_u,\qquad D_t=H_t-R_t,\qquad A_t=t-\tau_H.
$$

The primary rule `pm_11_drawdown_h4_peakguard` applies the manager only to
`11_r5_frames` entries. This keeps it as high-exposure insurance rather
than a universal exit overlay. Its active rule is:

$$
\tau=\inf\{t:\ H_t\ge4,\ D_t\ge\max(2,0.35H_t)\}
$$

For small releases, it requires the peak not to be an opening flicker:

$$
H_t<8\Rightarrow \tau_H\ge1.5.
$$

The broader ablation `pm_drawdown_plateau` also tests:

$$
\tau=\inf\{t:\ H_t\ge10,\ A_t\ge8,\ R_t/H_t\ge0.85\}
$$

The broader ablation `pm_full_tiny` also tests, conservatively:

$$
\tau=\inf\{t\ge20:\ H_t<3,\ R_t\le0\}.
$$

Otherwise it exits at 60s. The ablations show whether plateau harvest
and no-release timeout help or simply cut right tail.

All totals below are C=0 mid-price path gross multiplied by the stored
`target_exposure`. `total_c1` and `total_c2` subtract 1 or 2 bps pressure
per unit exposure, but the main comparison is the C=0 delta versus fixed 60s.

## Scorecard

| policy | family | total_c0 | total_c1 | total_c2 | delta_vs_60s | worst_day | positive_days | q90_gross | right_tail_retention_q90 | cvar05_gross | single_worst_weighted | mean_exit_sec | managed_entries | managed_rate | action_exit_rate | saved_loser_pnl | killed_winner_pnl | save_kill_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pm_11_drawdown_h4_peakguard | small_path_manager | 9554.1874 | 8079.9374 | 6605.6874 | 649.4284 | 27.1656 | 12 | 19.7710 | 0.9966 | -30.8392 | -193.6578 | 58.8648 | 151 | 0.1038 | 0.0282 | 1276.6092 | 809.6130 | 1.5768 |
| pm_11_drawdown_h4 | small_path_manager | 9363.2397 | 7888.9897 | 6414.7397 | 458.4807 | 27.1656 | 12 | 19.6961 | 0.9928 | -30.8392 | -193.6578 | 58.7754 | 151 | 0.1038 | 0.0289 | 1276.6092 | 1000.5607 | 1.2759 |
| pm_11_drawdown_h4_start5s | small_path_manager | 9359.8794 | 7885.6294 | 6411.3794 | 455.1203 | 27.1656 | 12 | 19.6961 | 0.9928 | -30.8392 | -193.6578 | 58.7820 | 151 | 0.1038 | 0.0289 | 1276.6092 | 1003.9211 | 1.2716 |
| pm_11_drawdown_only | small_path_manager | 9204.3122 | 7730.0622 | 6255.8122 | 299.5532 | 27.1656 | 12 | 19.6961 | 0.9928 | -30.9822 | -235.9674 | 58.8820 | 151 | 0.1038 | 0.0261 | 1043.5948 | 926.4738 | 1.1264 |
| pm_drawdown_only | small_path_manager | 8920.7590 | 7446.5090 | 5972.2590 | 16.0000 | 23.5687 | 12 | 18.0749 | 0.9111 | -25.9627 | -235.9674 | 51.9635 | 1455 | 1.0000 | 0.2371 | 1531.2861 | 1764.8968 | 0.8676 |
| fixed_60s | fixed | 8904.7590 | 7430.5090 | 5956.2590 | 0.0000 | 27.1656 | 12 | 19.8383 | 1.0000 | -32.0188 | -235.9674 | 59.6103 | 0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |  |
| pm_full_tiny | small_path_manager | 8160.7921 | 6686.5421 | 5212.2921 | -743.9669 | 25.4756 | 12 | 13.6436 | 0.6877 | -17.6394 | -235.9674 | 33.0754 | 1455 | 1.0000 | 0.7402 | 2847.4018 | 4298.7170 | 0.6624 |
| pm_drawdown_plateau | small_path_manager | 8078.4804 | 6604.2304 | 5129.9804 | -826.2787 | 25.3229 | 12 | 16.0797 | 0.8105 | -25.3588 | -235.9674 | 47.5545 | 1455 | 1.0000 | 0.3711 | 1713.6398 | 3385.3607 | 0.5062 |
| fixed_30s | fixed | 7446.9709 | 5972.7209 | 4498.4709 | -1457.7881 | 27.1526 | 12 | 13.6567 | 0.6884 | -21.6494 | -204.3548 | 29.5766 | 0 | 0.0000 | 0.0000 | 3312.2830 | 5477.2577 | 0.6047 |

## Primary Case Decomposition

| path_case_class | entries | total_c0 | baseline_total_c0 | delta_vs_60s | gross_positive_rate | mean_exit_sec | managed_rate | no_release_timeout_rate | release_drawdown_rate | peak_age_harvest_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 00_non_case | 738 | 10016.3019 | 10454.4421 | -438.1403 | 0.8753 | 58.8649 | 0.1152 | 0.0000 | 0.0285 | 0.0000 |
| 01_no_release_flat | 558 | -1812.0376 | -1812.0376 | 0.0000 | 0.2724 | 59.6133 | 0.0806 | 0.0000 | 0.0000 | 0.0000 |
| 02_fast_release_reversal | 41 | -330.5047 | -936.2399 | 605.7351 | 0.0732 | 54.7147 | 0.1220 | 0.0000 | 0.1220 | 0.0000 |
| 03_large_release_plateau_decay | 25 | 653.1056 | 306.4902 | 346.6153 | 0.4800 | 55.0514 | 0.2000 | 0.0000 | 0.2000 | 0.0000 |
| 04_late_release_collapse | 93 | 1027.3223 | 892.1041 | 135.2182 | 0.6129 | 57.2274 | 0.1183 | 0.0000 | 0.1075 | 0.0000 |

## Primary Exit Reasons

| exit_reason | rate |
| --- | --- |
| fixed_60s | 0.9718 |
| release_drawdown | 0.0282 |

## Worst Primary Daily Deltas

| date | entries | total_c0 | baseline_total_c0 | delta_vs_60s | mean_exit_sec | managed_rate | no_release_timeout_rate | release_drawdown_rate | peak_age_harvest_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-15 | 218 | 2785.9589 | 2891.6063 | -105.6473 | 58.7955 | 0.1101 | 0.0000 | 0.0321 | 0.0000 |
| 2026-05-04 | 49 | 44.0142 | 44.0142 | 0.0000 | 59.6521 | 0.0408 | 0.0000 | 0.0000 | 0.0000 |
| 2026-05-07 | 35 | 60.1936 | 60.1936 | 0.0000 | 59.5859 | 0.0571 | 0.0000 | 0.0000 | 0.0000 |
| 2026-05-06 | 53 | 27.1656 | 27.1656 | 0.0000 | 59.5753 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 2026-05-13 | 103 | 103.2617 | 103.2617 | 0.0000 | 59.6127 | 0.0485 | 0.0000 | 0.0000 | 0.0000 |
| 2026-05-08 | 43 | 217.2628 | 217.2628 | 0.0000 | 59.6186 | 0.0465 | 0.0000 | 0.0000 | 0.0000 |
| 2026-05-05 | 117 | 281.3393 | 254.3442 | 26.9951 | 59.4796 | 0.0855 | 0.0000 | 0.0085 | 0.0000 |
| 2026-05-11 | 166 | 591.9515 | 495.4438 | 96.5076 | 59.4004 | 0.0602 | 0.0000 | 0.0060 | 0.0000 |
| 2026-05-10 | 121 | 439.3825 | 338.8099 | 100.5725 | 57.7733 | 0.1405 | 0.0000 | 0.0661 | 0.0000 |
| 2026-05-09 | 170 | 635.6214 | 505.9301 | 129.6913 | 58.8902 | 0.1471 | 0.0000 | 0.0176 | 0.0000 |
| 2026-05-12 | 120 | 1047.5066 | 883.3834 | 164.1232 | 58.8365 | 0.1917 | 0.0000 | 0.0500 | 0.0000 |
| 2026-05-14 | 260 | 3320.5293 | 3083.3433 | 237.1859 | 57.9973 | 0.1192 | 0.0000 | 0.0577 | 0.0000 |

## Primary Examples

| example_side | date | entry_row | path_case_class | cell | direction_label | target_exposure | baseline_gross60 | policy_gross | delta_weighted_vs_60s | exit_reason | exit_sec | H_exit | D_exit | peak_age_exit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| saved_vs_60s | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | 11_r5_frames | short | 10.0000 | -9.5281 | 14.0108 | 235.3889 | release_drawdown | 41.8205 | 24.4572 | 10.4464 | 29.1167 |
| saved_vs_60s | 2026-05-14 | 2377379 | 02_fast_release_reversal | 11_r5_frames | short | 10.0000 | -23.5967 | -0.2953 | 233.0144 | release_drawdown | 18.7370 | 4.7260 | 5.0213 | 15.5153 |
| saved_vs_60s | 2026-05-09 | 1615412 | 02_fast_release_reversal | 11_r5_frames | short | 8.0000 | -27.8923 | -10.0376 | 142.8370 | release_drawdown | 5.5048 | 12.5612 | 22.5989 | 0.7997 |
| saved_vs_60s | 2026-05-12 | 2039581 | 02_fast_release_reversal | 11_r5_frames | short | 8.0000 | -17.3956 | -0.0000 | 139.1650 | release_drawdown | 16.4519 | 7.1534 | 7.1534 | 12.3954 |
| saved_vs_60s | 2026-05-14 | 2334597 | 04_late_release_collapse | 11_r5_frames | long | 2.0000 | -59.7053 | 7.5133 | 134.4371 | release_drawdown | 33.8114 | 13.5198 | 6.0065 | 11.2037 |
| saved_vs_60s | 2026-05-11 | 1955577 | 03_large_release_plateau_decay | 11_r5_frames | short | 8.0000 | 7.2311 | 19.2945 | 96.5076 | release_drawdown | 32.6863 | 30.1641 | 10.8696 | 29.1522 |
| saved_vs_60s | 2026-05-10 | 1785626 | 04_late_release_collapse | 11_r5_frames | short | 8.0000 | -10.5497 | 1.2795 | 94.6337 | release_drawdown | 37.4663 | 8.3197 | 7.0402 | 9.0208 |
| saved_vs_60s | 2026-05-15 | 2540829 | 04_late_release_collapse | 11_r5_frames | long | 2.0000 | -42.9424 | -4.7623 | 76.3603 | release_drawdown | 23.3133 | 7.2978 | 12.0600 | 17.1099 |
| saved_vs_60s | 2026-05-14 | 2414246 | 02_fast_release_reversal | 11_r5_frames | short | 8.0000 | -11.0308 | -3.0653 | 63.7235 | release_drawdown | 21.3117 | 6.1335 | 9.1988 | 19.7102 |
| saved_vs_60s | 2026-05-12 | 2053599 | 04_late_release_collapse | 11_r5_frames | short | 8.0000 | 0.9485 | 8.8563 | 63.2621 | release_drawdown | 51.3779 | 21.5217 | 12.6654 | 5.6117 |
| saved_vs_60s | 2026-05-10 | 1781104 | 04_late_release_collapse | 11_r5_frames | long | 4.0000 | -7.6014 | 5.3809 | 51.9291 | release_drawdown | 30.0189 | 10.4425 | 5.0617 | 1.0994 |
| saved_vs_60s | 2026-05-14 | 2386172 | 00_non_case | 11_r5_frames | long | 2.0000 | -17.9925 | 5.7873 | 47.5595 | release_drawdown | 46.2333 | 10.9626 | 5.1753 | 40.1290 |
| killed_vs_60s | 2026-05-15 | 2583437 | 04_late_release_collapse | 11_r5_frames | long | 4.0000 | 69.7360 | 20.2961 | -197.7596 | release_drawdown | 26.9121 | 38.6238 | 18.3277 | 1.6006 |
| killed_vs_60s | 2026-05-14 | 2327008 | 00_non_case | 11_r5_frames | short | 10.0000 | 12.4584 | 0.3037 | -121.5473 | release_drawdown | 15.4087 | 8.5065 | 8.2028 | 8.1034 |
| killed_vs_60s | 2026-05-14 | 2322885 | 00_non_case | 11_r5_frames | long | 2.0000 | 38.2362 | -7.7895 | -92.0514 | release_drawdown | 12.4058 | 6.2272 | 14.0167 | 0.3012 |
| killed_vs_60s | 2026-05-14 | 2362632 | 04_late_release_collapse | 11_r5_frames | long | 2.0000 | 4.7316 | -36.4493 | -82.3619 | release_drawdown | 47.3247 | 17.4368 | 53.8861 | 16.0102 |
| killed_vs_60s | 2026-05-14 | 2379419 | 00_non_case | 11_r5_frames | short | 8.0000 | 5.0480 | -4.7488 | -78.3743 | release_drawdown | 25.3146 | 6.5332 | 11.2820 | 11.6061 |
| killed_vs_60s | 2026-05-14 | 2340079 | 00_non_case | 11_r5_frames | short | 8.0000 | 10.9676 | 5.1776 | -46.3196 | release_drawdown | 25.0099 | 9.7484 | 4.5707 | 6.9050 |
| killed_vs_60s | 2026-05-12 | 1968116 | 00_non_case | 11_r5_frames | short | 8.0000 | 4.5823 | -0.9162 | -43.9883 | release_drawdown | 39.0004 | 4.8879 | 5.8041 | 0.3629 |
| killed_vs_60s | 2026-05-14 | 2400106 | 00_non_case | 11_r5_frames | short | 10.0000 | 5.9972 | 2.0986 | -38.9858 | release_drawdown | 26.6125 | 8.0970 | 5.9984 | 26.3129 |
| killed_vs_60s | 2026-05-10 | 1792601 | 00_non_case | 11_r5_frames | long | 4.0000 | 5.8192 | 0.3234 | -21.9834 | release_drawdown | 10.3324 | 4.5263 | 4.2030 | 3.4041 |
| killed_vs_60s | 2026-05-10 | 1676923 | 00_non_case | 11_r5_frames | long | 4.0000 | 7.3364 | 2.2334 | -20.4121 | release_drawdown | 35.6364 | 12.7555 | 10.5221 | 1.5014 |
| killed_vs_60s | 2026-05-10 | 1795464 | 00_non_case | 11_r5_frames | long | 4.0000 | 5.8506 | 1.6255 | -16.9004 | release_drawdown | 24.3930 | 8.7746 | 7.1491 | 8.0961 |
| killed_vs_60s | 2026-05-10 | 1678625 | 00_non_case | 11_r5_frames | long | 2.0000 | 14.0665 | 7.0357 | -14.0616 | release_drawdown | 17.2149 | 12.7885 | 5.7528 | 1.4025 |

## Day Status

| date | status | entries | simulated_entries | panel_rows |
| --- | --- | --- | --- | --- |
| 2026-05-04 | ok | 49 | 49 | 164451 |
| 2026-05-05 | ok | 117 | 117 | 203093 |
| 2026-05-06 | ok | 53 | 53 | 153744 |
| 2026-05-07 | ok | 35 | 35 | 142238 |
| 2026-05-08 | ok | 43 | 43 | 141979 |
| 2026-05-09 | ok | 170 | 170 | 138327 |
| 2026-05-10 | ok | 121 | 121 | 138177 |
| 2026-05-11 | ok | 166 | 166 | 143431 |
| 2026-05-12 | ok | 120 | 120 | 157429 |
| 2026-05-13 | ok | 103 | 103 | 149542 |
| 2026-05-14 | ok | 260 | 260 | 177047 |
| 2026-05-15 | ok | 218 | 218 | 165044 |

## Read

- The manager should be judged by case transfer, not only total PnL.
- If `release_drawdown` saves `fast_release_reversal` but kills too much
  `non_case`, the drawdown threshold is too tight.
- If `peak_age_harvest` improves `large_release_plateau_decay` without
  damaging `late_release_collapse`, the release/decay framing is working.
- The no-release timeout is the most suspect component because some genuine
  right tail arrives late; keep it only if the ablation supports it.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\docs\markets\ccusdt\v1-tfi-small-path-manager-20260519_ccusdt_v1_tfi_small_path_manager_v1.md`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_small_path_manager_events_20260519_ccusdt_v1_tfi_small_path_manager_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_small_path_manager_scorecard_20260519_ccusdt_v1_tfi_small_path_manager_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_small_path_manager_case_summary_20260519_ccusdt_v1_tfi_small_path_manager_v1.csv`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_small_path_manager.py
```

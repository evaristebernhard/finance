# CCUSDT Tail And Stop Deep Dive

Status: `20260517_ccusdt_tail_stop_deep_dive_v1` from source panel `20260517_ccusdt_fixed_factors_v3`.

Guardrail: `research_only_per_entry_tail_stop_diagnostics_no_execution_recommendation_no_alpha_claim`.

This is a per-entry research diagnostic over a snapshot-frame factor panel. It is not queue-position fill evidence, not a live execution simulation, not trading advice, and not an alpha claim.

## Scope

- Per-entry rows: `6447` across `15` fold/trigger groups.
- Trigger focus: `tfi_follow_flat`, `tfi_short_flat`, `tfi_long_flat`, `tfi_short_stale25`, `tfi_event_active`.
- Horizon: fixed `60s` entries, first signal per `60s` bucket.
- Stop-only levels: `5, 8, 12, 20` bps with `0s, 5s, 10s` grace.

## Research Read

This pass changes the read in two ways. First, stop-only is not just random table noise, but it is also not an execution rule. It is a path classifier: when a path quickly reaches adverse excursion, the recovery probability and the killed-winner rate decide whether a stop helps. Second, the large-sample right-tail rows are not single-trade illusions, but they are still tail-cluster dependent and cost-thin.

For large-sample flat TFI in `expanding_fold3`, immediate `5` bps stop is mostly a left-tail repair that costs expectancy. `tfi_follow_flat` improves CVaR by `10.0795` bps, but mean falls by `-0.4815` bps and median falls to `-1.1599` bps; save/kill is only `0.7539`. `tfi_short_flat` is similar: CVaR improves by `8.8736` bps, but mean falls by `-0.3158` bps and median falls to `-1.1610` bps. A `20` bps catastrophic stop does not solve this; it still reduces mean in fold3 and barely helps or worsens CVaR for `tfi_short_flat`.

`tfi_short_stale25` is different but still not clean. In `expanding_fold3`, `5` bps stop improves mean by `0.4003` bps and CVaR by `8.6865` bps, with save/kill `1.4223`. But it turns the baseline median from `2.5130` bps into `-0.1816` bps. That means the stop is not a free risk overlay; it converts the state from a positive-median sparse entry into a distribution that needs the remaining right tail. The `20` bps catastrophic stop is actively bad for this state: mean delta `-0.8533` bps, CVaR delta `-2.9121` bps, save/kill `0.1320`.

The fat-tail read is more nuanced than "one winner did it." Large-sample fold3 rows survive removal of the largest `10` net winners: `tfi_follow_flat` stays at `1.6158` bps and `tfi_short_flat` stays at `1.2101` bps. They flip only after removing about `57` and `36` top winners respectively. So there is a broader right-tail cluster. But the top `10%` net winners still exceed total net profit (`1.5327x` and `1.5397x`), so the edge is still paid by the upper tail offsetting many losers, not by stable central tendency.

`tfi_short_stale25` fold3 survives the largest `10` winners by only `0.1255` bps and flips after `14` winners. Fold2 stale25 flips after the single largest winner. This is the central reason it should be kept as a sparse state hypothesis rather than promoted.

Cost stress is a hard constraint. Fold2 flat TFI fails at `+2` bps added cost, while fold3 flat TFI fails at `+3` bps. Fold3 `stale25` keeps positive mean even at `+5` bps, but median becomes negative by `+3` bps and fold2 fails at `+1` bps. This says `stale25` has local payoff intensity, but not yet cross-fold cost robustness.

Matched random controls are encouraging: all fold2/fold3 target rows beat date/filter/direction matched random entries. For fold3, matched-random median means are negative (`-1.9471` for `tfi_follow_flat`, `-1.7487` for `tfi_short_flat`, `-1.8433` for `tfi_short_stale25`), while signal means are positive. This supports a real signal-state interaction, though it does not solve execution realism.

Quote-transition rates are high (`94%..97%`), so the 60s edge is not simply "no quote transition at all." But first mid-transition gross mean is only around `1.23..2.45` bps for the main fold2/fold3 rows, below the full fixed-horizon mean for the stronger rows. The payoff therefore looks like post-transition continuation / quote-release path shape, not just first-tick movement.

Current decision: continue one narrow verification pass, not strategy optimization. The next pass should model adverse excursion and recovery as features, run quote-transition-only and residualized labels, and apply stricter cost curves. Stop tuning should stop unless it is framed as "what path state predicts failed recovery?"

## Per-Entry Summary
| fold | trigger_class | entries | net_mean_bps | net_median_bps | net_cvar10_bps | has_mid_transition_rate | top5_net_share_of_total_net | top10pct_net_share_of_total_net | winner_count_to_cover_total_net | day_boot_mean_p05_bps | day_boot_prob_mean_gt0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | tfi_short_stale25 | 27 | 1.3312 | 2.7485 | -9.0805 | 0.9630 | 1.0157 | 0.7232 | 5.0000 | 1.0939 | 1.0000 |
| expanding_fold1 | tfi_event_active | 61 | 1.2920 | -0.4953 | -8.5640 | 0.9508 | 0.8039 | 1.0107 | 7.0000 | 0.2284 | 0.9835 |
| expanding_fold1 | tfi_follow_flat | 753 | -1.2151 | -1.6821 | -12.6999 | 0.9416 |  |  |  | -1.6439 | 0.0000 |
| expanding_fold1 | tfi_long_flat | 403 | -1.2886 | -1.6767 | -14.9234 | 0.9504 |  |  |  | -2.0447 | 0.0000 |
| expanding_fold1 | tfi_short_flat | 408 | -1.3581 | -1.8395 | -10.6765 | 0.9387 |  |  |  | -1.7689 | 0.0000 |
| expanding_fold2 | tfi_event_active | 121 | 1.7959 | -0.0261 | -15.4654 | 0.9504 | 0.9795 | 1.4742 | 6.0000 | 0.9645 | 1.0000 |
| expanding_fold2 | tfi_follow_flat | 926 | 1.5389 | -0.6801 | -20.3268 | 0.9514 | 0.3035 | 1.9185 | 29.0000 | 0.4477 | 0.9955 |
| expanding_fold2 | tfi_short_flat | 615 | 1.3572 | -0.5155 | -24.6313 | 0.9545 | 0.3910 | 2.1281 | 19.0000 | 0.4661 | 1.0000 |
| expanding_fold2 | tfi_long_flat | 381 | 1.2395 | -1.0000 | -15.0721 | 0.9528 | 0.8815 | 2.2683 | 7.0000 | -0.1691 | 0.8960 |
| expanding_fold2 | tfi_short_stale25 | 73 | 0.1424 | -0.5163 | -16.8257 | 0.9452 | 8.2174 | 11.4348 | 1.0000 | -0.7565 | 0.5985 |
| expanding_fold3 | tfi_short_stale25 | 131 | 5.1872 | 2.5130 | -19.3756 | 0.9542 | 0.7242 | 1.1273 | 11.0000 | 1.1595 | 0.9785 |
| expanding_fold3 | tfi_event_active | 210 | 4.1374 | 2.2123 | -23.9016 | 0.9619 | 0.5689 | 1.1612 | 16.0000 | 1.1360 | 0.9775 |
| expanding_fold3 | tfi_follow_flat | 1129 | 2.4978 | -0.3967 | -24.4160 | 0.9663 | 0.2241 | 1.5327 | 52.0000 | 0.6672 | 0.9815 |
| expanding_fold3 | tfi_short_flat | 716 | 2.4218 | -0.3931 | -21.7657 | 0.9637 | 0.3051 | 1.5397 | 33.0000 | 0.6074 | 0.9860 |
| expanding_fold3 | tfi_long_flat | 493 | 2.3091 | -0.6709 | -29.8047 | 0.9696 | 0.4258 | 1.7587 | 19.0000 | -0.6113 | 0.9405 |

## Cost Stress
| fold | trigger_class | cost_adder_bps | entries | net_mean_bps | net_median_bps | A_cost_cross_rate | B_winner_excess_bps | D_loser_shortfall_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | tfi_event_active | 0.0000 | 61 | 1.2920 | -0.4953 | 0.4918 | 5.7346 | 3.0073 |
| expanding_fold1 | tfi_event_active | 1.0000 | 61 | 0.2920 | -1.4953 | 0.4754 | 4.9318 | 3.9128 |
| expanding_fold1 | tfi_event_active | 2.0000 | 61 | -0.7080 | -2.4953 | 0.4754 | 3.9318 | 4.9128 |
| expanding_fold1 | tfi_event_active | 3.0000 | 61 | -1.7080 | -3.4953 | 0.4098 | 3.4728 | 5.3058 |
| expanding_fold1 | tfi_event_active | 5.0000 | 61 | -3.7080 | -5.4953 | 0.2131 | 3.6792 | 5.7087 |
| expanding_fold1 | tfi_follow_flat | 0.0000 | 753 | -1.2151 | -1.6821 | 0.2855 | 5.6087 | 3.9421 |
| expanding_fold1 | tfi_follow_flat | 1.0000 | 753 | -2.2151 | -2.6821 | 0.2776 | 4.7605 | 4.8951 |
| expanding_fold1 | tfi_follow_flat | 2.0000 | 753 | -3.2151 | -3.6821 | 0.2523 | 4.1744 | 5.7089 |
| expanding_fold1 | tfi_follow_flat | 3.0000 | 753 | -4.2151 | -4.6821 | 0.2019 | 4.0613 | 6.3083 |
| expanding_fold1 | tfi_follow_flat | 5.0000 | 753 | -6.2151 | -6.6821 | 0.0983 | 5.2565 | 7.4653 |
| expanding_fold1 | tfi_long_flat | 0.0000 | 403 | -1.2886 | -1.6767 | 0.2978 | 5.7791 | 4.2854 |
| expanding_fold1 | tfi_long_flat | 1.0000 | 403 | -2.2886 | -2.6767 | 0.2903 | 4.9184 | 5.2369 |
| expanding_fold1 | tfi_long_flat | 2.0000 | 403 | -3.2886 | -3.6767 | 0.2457 | 4.7038 | 5.8913 |
| expanding_fold1 | tfi_long_flat | 3.0000 | 403 | -4.2886 | -4.6767 | 0.1935 | 4.8033 | 6.4706 |
| expanding_fold1 | tfi_long_flat | 5.0000 | 403 | -6.2886 | -6.6767 | 0.0943 | 6.6890 | 7.6396 |
| expanding_fold1 | tfi_short_flat | 0.0000 | 408 | -1.3581 | -1.8395 | 0.2574 | 5.2376 | 3.6438 |
| expanding_fold1 | tfi_short_flat | 1.0000 | 408 | -2.3581 | -2.8395 | 0.2475 | 4.4363 | 4.5934 |
| expanding_fold1 | tfi_short_flat | 2.0000 | 408 | -3.3581 | -3.8395 | 0.2402 | 3.5545 | 5.5434 |
| expanding_fold1 | tfi_short_flat | 3.0000 | 408 | -4.3581 | -4.8395 | 0.1961 | 3.2146 | 6.2051 |
| expanding_fold1 | tfi_short_flat | 5.0000 | 408 | -6.3581 | -6.8395 | 0.0931 | 3.6874 | 7.3899 |
| expanding_fold1 | tfi_short_stale25 | 0.0000 | 27 | 1.3312 | 2.7485 | 0.5926 | 4.6083 | 3.4354 |
| expanding_fold1 | tfi_short_stale25 | 1.0000 | 27 | 0.3312 | 1.7485 | 0.5556 | 3.9145 | 4.1479 |
| expanding_fold1 | tfi_short_stale25 | 2.0000 | 27 | -0.6688 | 0.7485 | 0.5556 | 2.9145 | 5.1479 |
| expanding_fold1 | tfi_short_stale25 | 3.0000 | 27 | -1.6688 | -0.2515 | 0.4815 | 2.2744 | 5.3303 |
| expanding_fold1 | tfi_short_stale25 | 5.0000 | 27 | -3.6688 | -2.2515 | 0.1852 | 2.3017 | 5.0257 |
| expanding_fold2 | tfi_event_active | 0.0000 | 121 | 1.7959 | -0.0261 | 0.4959 | 8.8853 | 5.1773 |
| expanding_fold2 | tfi_event_active | 1.0000 | 121 | 0.7959 | -1.0261 | 0.4793 | 8.1880 | 6.0095 |
| expanding_fold2 | tfi_event_active | 2.0000 | 121 | -0.2041 | -2.0261 | 0.4628 | 7.4508 | 6.7991 |
| expanding_fold2 | tfi_event_active | 3.0000 | 121 | -1.2041 | -3.0261 | 0.4298 | 6.9510 | 7.3500 |
| expanding_fold2 | tfi_event_active | 5.0000 | 121 | -3.2041 | -5.0261 | 0.2810 | 8.1484 | 7.6408 |
| expanding_fold2 | tfi_follow_flat | 0.0000 | 926 | 1.5389 | -0.6801 | 0.4503 | 10.8553 | 6.0936 |
| expanding_fold2 | tfi_follow_flat | 1.0000 | 926 | 0.5389 | -1.6801 | 0.4341 | 10.2441 | 6.9067 |
| expanding_fold2 | tfi_follow_flat | 2.0000 | 926 | -0.4611 | -2.6801 | 0.4136 | 9.7256 | 7.6462 |
| expanding_fold2 | tfi_follow_flat | 3.0000 | 926 | -1.4611 | -3.6801 | 0.3769 | 9.6148 | 8.1604 |
| expanding_fold2 | tfi_follow_flat | 5.0000 | 926 | -3.4611 | -5.6801 | 0.2441 | 12.3100 | 8.5529 |
| expanding_fold2 | tfi_long_flat | 0.0000 | 381 | 1.2395 | -1.0000 | 0.4121 | 10.1890 | 5.0332 |
| expanding_fold2 | tfi_long_flat | 1.0000 | 381 | 0.2395 | -2.0000 | 0.3937 | 9.6415 | 5.8657 |
| expanding_fold2 | tfi_long_flat | 2.0000 | 381 | -0.7605 | -3.0000 | 0.3596 | 9.5023 | 6.5228 |
| expanding_fold2 | tfi_long_flat | 3.0000 | 381 | -1.7605 | -4.0000 | 0.3386 | 9.0499 | 7.2944 |
| expanding_fold2 | tfi_long_flat | 5.0000 | 381 | -3.7605 | -6.0000 | 0.2021 | 12.5354 | 7.8881 |

## Top Winner Removal
| fold | trigger_class | removed_top_net_winners | remaining_entries | net_mean_bps | net_median_bps | win_rate |
| --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | tfi_event_active | 0 | 61 | 1.2920 | -0.4953 | 0.4918 |
| expanding_fold1 | tfi_event_active | 1 | 60 | 1.0249 | -0.4958 | 0.4833 |
| expanding_fold1 | tfi_event_active | 3 | 58 | 0.6125 | -0.5788 | 0.4655 |
| expanding_fold1 | tfi_event_active | 5 | 56 | 0.2759 | -0.6620 | 0.4464 |
| expanding_fold1 | tfi_event_active | 10 | 51 | -0.3628 | -0.8306 | 0.3922 |
| expanding_fold1 | tfi_follow_flat | 0 | 753 | -1.2151 | -1.6821 | 0.2855 |
| expanding_fold1 | tfi_follow_flat | 1 | 752 | -1.3452 | -1.6821 | 0.2846 |
| expanding_fold1 | tfi_follow_flat | 3 | 750 | -1.4313 | -1.7568 | 0.2827 |
| expanding_fold1 | tfi_follow_flat | 5 | 748 | -1.4833 | -1.8321 | 0.2807 |
| expanding_fold1 | tfi_follow_flat | 10 | 743 | -1.6065 | -1.8382 | 0.2759 |
| expanding_fold1 | tfi_long_flat | 0 | 403 | -1.2886 | -1.6767 | 0.2978 |
| expanding_fold1 | tfi_long_flat | 1 | 402 | -1.5322 | -1.6778 | 0.2960 |
| expanding_fold1 | tfi_long_flat | 3 | 400 | -1.6945 | -1.6798 | 0.2925 |
| expanding_fold1 | tfi_long_flat | 5 | 398 | -1.7848 | -1.7560 | 0.2889 |
| expanding_fold1 | tfi_long_flat | 10 | 393 | -1.9626 | -1.8382 | 0.2799 |
| expanding_fold1 | tfi_short_flat | 0 | 408 | -1.3581 | -1.8395 | 0.2574 |
| expanding_fold1 | tfi_short_flat | 1 | 407 | -1.4061 | -1.8395 | 0.2555 |
| expanding_fold1 | tfi_short_flat | 3 | 405 | -1.5004 | -1.8400 | 0.2519 |
| expanding_fold1 | tfi_short_flat | 5 | 403 | -1.5923 | -1.8400 | 0.2481 |
| expanding_fold1 | tfi_short_flat | 10 | 398 | -1.7550 | -1.8405 | 0.2387 |
| expanding_fold1 | tfi_short_stale25 | 0 | 27 | 1.3312 | 2.7485 | 0.5926 |
| expanding_fold1 | tfi_short_stale25 | 1 | 26 | 0.9942 | 2.5750 | 0.5769 |
| expanding_fold1 | tfi_short_stale25 | 3 | 24 | 0.4145 | 1.2083 | 0.5417 |
| expanding_fold1 | tfi_short_stale25 | 5 | 22 | -0.0257 | -0.2407 | 0.5000 |
| expanding_fold1 | tfi_short_stale25 | 10 | 17 | -1.3022 | -0.8322 | 0.3529 |
| expanding_fold2 | tfi_event_active | 0 | 121 | 1.7959 | -0.0261 | 0.4959 |
| expanding_fold2 | tfi_event_active | 1 | 120 | 0.8556 | -0.1908 | 0.4917 |
| expanding_fold2 | tfi_event_active | 3 | 118 | 0.3740 | -0.4206 | 0.4831 |
| expanding_fold2 | tfi_event_active | 5 | 116 | 0.0384 | -0.4856 | 0.4741 |
| expanding_fold2 | tfi_event_active | 10 | 111 | -0.6290 | -0.5152 | 0.4505 |
| expanding_fold2 | tfi_follow_flat | 0 | 926 | 1.5389 | -0.6801 | 0.4503 |
| expanding_fold2 | tfi_follow_flat | 1 | 925 | 1.4166 | -0.6801 | 0.4497 |
| expanding_fold2 | tfi_follow_flat | 3 | 923 | 1.2235 | -0.6803 | 0.4485 |
| expanding_fold2 | tfi_follow_flat | 5 | 921 | 1.0777 | -0.6803 | 0.4473 |
| expanding_fold2 | tfi_follow_flat | 10 | 916 | 0.7449 | -0.6848 | 0.4443 |
| expanding_fold2 | tfi_long_flat | 0 | 381 | 1.2395 | -1.0000 | 0.4121 |
| expanding_fold2 | tfi_long_flat | 1 | 380 | 0.9411 | -1.0000 | 0.4105 |
| expanding_fold2 | tfi_long_flat | 3 | 378 | 0.4961 | -1.0000 | 0.4074 |
| expanding_fold2 | tfi_long_flat | 5 | 376 | 0.1488 | -1.0780 | 0.4043 |
| expanding_fold2 | tfi_long_flat | 10 | 371 | -0.3481 | -1.1600 | 0.3962 |
| expanding_fold2 | tfi_short_flat | 0 | 615 | 1.3572 | -0.5155 | 0.4667 |
| expanding_fold2 | tfi_short_flat | 1 | 614 | 1.2305 | -0.5159 | 0.4658 |
| expanding_fold2 | tfi_short_flat | 3 | 612 | 1.0112 | -0.5178 | 0.4641 |
| expanding_fold2 | tfi_short_flat | 5 | 610 | 0.8333 | -0.5881 | 0.4623 |
| expanding_fold2 | tfi_short_flat | 10 | 605 | 0.4667 | -0.6780 | 0.4579 |
| expanding_fold2 | tfi_short_stale25 | 0 | 73 | 0.1424 | -0.5163 | 0.4247 |
| expanding_fold2 | tfi_short_stale25 | 1 | 72 | -0.1533 | -0.5866 | 0.4167 |
| expanding_fold2 | tfi_short_stale25 | 3 | 70 | -0.6643 | -0.6668 | 0.4000 |
| expanding_fold2 | tfi_short_stale25 | 5 | 68 | -1.1032 | -0.6774 | 0.3824 |
| expanding_fold2 | tfi_short_stale25 | 10 | 63 | -2.0173 | -0.6815 | 0.3333 |
| expanding_fold3 | tfi_event_active | 0 | 210 | 4.1374 | 2.2123 | 0.5238 |
| expanding_fold3 | tfi_event_active | 1 | 209 | 3.4108 | 1.9116 | 0.5215 |
| expanding_fold3 | tfi_event_active | 3 | 207 | 2.4581 | 1.6529 | 0.5169 |
| expanding_fold3 | tfi_event_active | 5 | 205 | 1.8270 | 0.7895 | 0.5122 |
| expanding_fold3 | tfi_event_active | 10 | 200 | 0.8164 | -0.0201 | 0.5000 |
| expanding_fold3 | tfi_follow_flat | 0 | 1129 | 2.4978 | -0.3967 | 0.4827 |
| expanding_fold3 | tfi_follow_flat | 1 | 1128 | 2.3479 | -0.4038 | 0.4823 |
| expanding_fold3 | tfi_follow_flat | 3 | 1126 | 2.1064 | -0.4610 | 0.4813 |
| expanding_fold3 | tfi_follow_flat | 5 | 1124 | 1.9468 | -0.5118 | 0.4804 |
| expanding_fold3 | tfi_follow_flat | 10 | 1119 | 1.6158 | -0.5242 | 0.4781 |

## Stop Deep Read
| fold | trigger_class | stop_bps | grace_sec | stop_hit_rate | delta_net_mean_bps | delta_cvar10_bps | stop_net_median_bps | hit_recover_to_cost_rate | hit_stop_better_rate | hit_final_above_stop_rate | save_to_kill_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | tfi_event_active | 5.0000 | 0 | 0.0984 | -0.1059 | -0.2204 | -0.4953 | 0.0000 | 0.3333 | 0.3333 | 0.6144 |
| expanding_fold1 | tfi_event_active | 5.0000 | 5 | 0.0984 | -0.1059 | -0.2204 | -0.4953 | 0.0000 | 0.3333 | 0.3333 | 0.6144 |
| expanding_fold1 | tfi_event_active | 20.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | -0.4953 |  |  |  |  |
| expanding_fold1 | tfi_event_active | 20.0000 | 5 | 0.0000 | 0.0000 | 0.0000 | -0.4953 |  |  |  |  |
| expanding_fold1 | tfi_follow_flat | 5.0000 | 0 | 0.1793 | -0.2110 | 2.4148 | -1.8406 | 0.0370 | 0.3630 | 0.4444 | 0.6380 |
| expanding_fold1 | tfi_follow_flat | 5.0000 | 5 | 0.1753 | -0.1754 | 2.4310 | -1.8405 | 0.0303 | 0.3636 | 0.4394 | 0.6797 |
| expanding_fold1 | tfi_follow_flat | 20.0000 | 0 | 0.0106 | 0.0603 | 0.5974 | -1.6821 | 0.0000 | 0.7500 | 0.2500 | 2.1702 |
| expanding_fold1 | tfi_follow_flat | 20.0000 | 5 | 0.0106 | 0.0603 | 0.5974 | -1.6821 | 0.0000 | 0.7500 | 0.2500 | 2.1702 |
| expanding_fold1 | tfi_long_flat | 5.0000 | 0 | 0.1811 | -0.1311 | 3.9332 | -1.8400 | 0.0411 | 0.5068 | 0.3973 | 0.8099 |
| expanding_fold1 | tfi_long_flat | 5.0000 | 5 | 0.1787 | -0.1135 | 3.9483 | -1.8400 | 0.0417 | 0.5000 | 0.4028 | 0.8313 |
| expanding_fold1 | tfi_long_flat | 20.0000 | 0 | 0.0199 | 0.1420 | 1.3961 | -1.6767 | 0.0000 | 0.7500 | 0.1250 | 3.1234 |
| expanding_fold1 | tfi_long_flat | 20.0000 | 5 | 0.0199 | 0.1420 | 1.3961 | -1.6767 | 0.0000 | 0.7500 | 0.1250 | 3.1234 |
| expanding_fold1 | tfi_short_flat | 5.0000 | 0 | 0.1838 | -0.2276 | 1.3200 | -1.8415 | 0.0267 | 0.2800 | 0.4533 | 0.4843 |
| expanding_fold1 | tfi_short_flat | 5.0000 | 5 | 0.1789 | -0.1793 | 1.3362 | -1.8412 | 0.0137 | 0.2877 | 0.4384 | 0.5439 |
| expanding_fold1 | tfi_short_flat | 20.0000 | 0 | 0.0025 | -0.0290 | -0.2888 | -1.8395 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| expanding_fold1 | tfi_short_flat | 20.0000 | 5 | 0.0025 | -0.0290 | -0.2888 | -1.8395 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| expanding_fold1 | tfi_short_stale25 | 5.0000 | 0 | 0.0741 | 0.1118 | 1.0059 | 2.7485 | 0.0000 | 0.5000 | 0.0000 |  |
| expanding_fold1 | tfi_short_stale25 | 5.0000 | 5 | 0.0741 | 0.1118 | 1.0059 | 2.7485 | 0.0000 | 0.5000 | 0.0000 |  |
| expanding_fold1 | tfi_short_stale25 | 20.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | 2.7485 |  |  |  |  |
| expanding_fold1 | tfi_short_stale25 | 20.0000 | 5 | 0.0000 | 0.0000 | 0.0000 | 2.7485 |  |  |  |  |
| expanding_fold2 | tfi_event_active | 5.0000 | 0 | 0.1653 | 0.4178 | 4.7606 | -0.3556 | 0.0500 | 0.4500 | 0.3000 | 3.0740 |
| expanding_fold2 | tfi_event_active | 5.0000 | 5 | 0.1653 | 0.4178 | 4.7606 | -0.3556 | 0.0500 | 0.4500 | 0.3000 | 3.0740 |
| expanding_fold2 | tfi_event_active | 20.0000 | 0 | 0.0165 | 0.0427 | 0.3973 | -0.0261 | 0.0000 | 0.5000 | 0.0000 |  |
| expanding_fold2 | tfi_event_active | 20.0000 | 5 | 0.0165 | 0.0427 | 0.3973 | -0.0261 | 0.0000 | 0.5000 | 0.0000 |  |
| expanding_fold2 | tfi_follow_flat | 5.0000 | 0 | 0.2149 | -0.1305 | 8.6406 | -1.0780 | 0.1457 | 0.4673 | 0.4070 | 0.8884 |
| expanding_fold2 | tfi_follow_flat | 5.0000 | 5 | 0.2127 | -0.1889 | 7.8475 | -1.0000 | 0.1421 | 0.4721 | 0.4010 | 0.8395 |
| expanding_fold2 | tfi_follow_flat | 20.0000 | 0 | 0.0324 | 0.2334 | 3.0509 | -0.6803 | 0.0667 | 0.4333 | 0.5333 | 1.9510 |
| expanding_fold2 | tfi_follow_flat | 20.0000 | 5 | 0.0324 | 0.1915 | 2.6334 | -0.6803 | 0.0667 | 0.4333 | 0.5333 | 1.7498 |
| expanding_fold2 | tfi_long_flat | 5.0000 | 0 | 0.2100 | -0.4311 | 4.1015 | -1.1693 | 0.0875 | 0.4750 | 0.3625 | 0.5517 |
| expanding_fold2 | tfi_long_flat | 5.0000 | 5 | 0.2073 | -0.4059 | 4.1596 | -1.1685 | 0.0886 | 0.4937 | 0.3418 | 0.5685 |
| expanding_fold2 | tfi_long_flat | 20.0000 | 0 | 0.0184 | -0.0208 | -0.2028 | -1.0000 | 0.0000 | 0.2857 | 0.5714 | 0.7304 |
| expanding_fold2 | tfi_long_flat | 20.0000 | 5 | 0.0184 | -0.0078 | -0.0762 | -1.0000 | 0.0000 | 0.2857 | 0.5714 | 0.8987 |
| expanding_fold2 | tfi_short_flat | 5.0000 | 0 | 0.2309 | 0.0704 | 11.9666 | -1.1600 | 0.1761 | 0.4930 | 0.4155 | 1.0524 |
| expanding_fold2 | tfi_short_flat | 5.0000 | 5 | 0.2293 | -0.0426 | 10.6565 | -1.1565 | 0.1702 | 0.4894 | 0.4184 | 0.9690 |
| expanding_fold2 | tfi_short_flat | 20.0000 | 0 | 0.0472 | 0.2740 | 5.0741 | -0.6768 | 0.1379 | 0.4138 | 0.5517 | 1.5303 |
| expanding_fold2 | tfi_short_flat | 20.0000 | 5 | 0.0472 | 0.2029 | 4.3683 | -0.6768 | 0.1379 | 0.4138 | 0.5517 | 1.3816 |
| expanding_fold2 | tfi_short_stale25 | 5.0000 | 0 | 0.1644 | 0.6038 | 5.5389 | -0.5163 | 0.0000 | 0.5833 | 0.2500 | 5.1579 |
| expanding_fold2 | tfi_short_stale25 | 5.0000 | 5 | 0.1644 | 0.6038 | 5.5389 | -0.5163 | 0.0000 | 0.5833 | 0.2500 | 5.1579 |
| expanding_fold2 | tfi_short_stale25 | 20.0000 | 0 | 0.0274 | 0.0708 | 0.6456 | -0.5163 | 0.0000 | 0.5000 | 0.0000 |  |
| expanding_fold2 | tfi_short_stale25 | 20.0000 | 5 | 0.0274 | 0.0708 | 0.6456 | -0.5163 | 0.0000 | 0.5000 | 0.0000 |  |
| expanding_fold3 | tfi_event_active | 5.0000 | 0 | 0.2857 | 0.6267 | 11.1965 | -0.2171 | 0.1333 | 0.6167 | 0.3000 | 1.5987 |
| expanding_fold3 | tfi_event_active | 5.0000 | 5 | 0.2857 | 0.5737 | 10.7887 | -0.2171 | 0.1333 | 0.6167 | 0.3000 | 1.5347 |
| expanding_fold3 | tfi_event_active | 20.0000 | 0 | 0.0667 | -0.4857 | 0.1158 | 0.4283 | 0.2857 | 0.4286 | 0.5000 | 0.4687 |
| expanding_fold3 | tfi_event_active | 20.0000 | 5 | 0.0667 | -0.4857 | 0.1158 | 0.4283 | 0.2857 | 0.4286 | 0.5000 | 0.4687 |
| expanding_fold3 | tfi_follow_flat | 5.0000 | 0 | 0.2985 | -0.4815 | 10.0795 | -1.1599 | 0.1691 | 0.4866 | 0.4332 | 0.7539 |
| expanding_fold3 | tfi_follow_flat | 5.0000 | 5 | 0.2967 | -0.4534 | 9.5071 | -1.1556 | 0.1642 | 0.4806 | 0.4358 | 0.7647 |
| expanding_fold3 | tfi_follow_flat | 20.0000 | 0 | 0.0700 | -0.4261 | 0.8829 | -0.6709 | 0.1392 | 0.4304 | 0.5316 | 0.5290 |
| expanding_fold3 | tfi_follow_flat | 20.0000 | 5 | 0.0691 | -0.2916 | 0.5804 | -0.6709 | 0.1282 | 0.4359 | 0.5256 | 0.6267 |
| expanding_fold3 | tfi_long_flat | 5.0000 | 0 | 0.2941 | -0.3785 | 13.9287 | -1.1631 | 0.1931 | 0.4897 | 0.4414 | 0.8392 |
| expanding_fold3 | tfi_long_flat | 5.0000 | 5 | 0.2941 | -0.5258 | 12.5291 | -1.1631 | 0.1931 | 0.4828 | 0.4483 | 0.7843 |
| expanding_fold3 | tfi_long_flat | 20.0000 | 0 | 0.0832 | -0.5238 | 3.4073 | -0.6834 | 0.1463 | 0.4634 | 0.5122 | 0.6046 |
| expanding_fold3 | tfi_long_flat | 20.0000 | 5 | 0.0811 | -0.1864 | 3.0006 | -0.6756 | 0.1250 | 0.4750 | 0.5000 | 0.8156 |
| expanding_fold3 | tfi_short_flat | 5.0000 | 0 | 0.3115 | -0.3158 | 8.8736 | -1.1610 | 0.1480 | 0.4933 | 0.4126 | 0.8037 |
| expanding_fold3 | tfi_short_flat | 5.0000 | 5 | 0.3087 | -0.1954 | 8.7376 | -1.1570 | 0.1403 | 0.4887 | 0.4118 | 0.8701 |
| expanding_fold3 | tfi_short_flat | 20.0000 | 0 | 0.0615 | -0.2260 | -0.0219 | -0.5408 | 0.1136 | 0.4318 | 0.5227 | 0.5808 |
| expanding_fold3 | tfi_short_flat | 20.0000 | 5 | 0.0615 | -0.2462 | -0.2228 | -0.5408 | 0.1136 | 0.4318 | 0.5227 | 0.5606 |
| expanding_fold3 | tfi_short_stale25 | 5.0000 | 0 | 0.3130 | 0.4003 | 8.6865 | -0.1816 | 0.1463 | 0.5366 | 0.3415 | 1.4223 |
| expanding_fold3 | tfi_short_stale25 | 5.0000 | 5 | 0.3130 | 0.3152 | 8.0579 | -0.1816 | 0.1463 | 0.5366 | 0.3415 | 1.3185 |
| expanding_fold3 | tfi_short_stale25 | 20.0000 | 0 | 0.0687 | -0.8533 | -2.9121 | 0.7160 | 0.3333 | 0.3333 | 0.5556 | 0.1320 |
| expanding_fold3 | tfi_short_stale25 | 20.0000 | 5 | 0.0687 | -0.8533 | -2.9121 | 0.7160 | 0.3333 | 0.3333 | 0.5556 | 0.1320 |

## Adverse Excursion Recovery
| fold | trigger_class | adverse_level_bps | touch_rate | touched_entries | touched_final_net_mean_bps | touched_recover_to_cost_rate | touched_positive_net_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | tfi_event_active | 5.0000 | 0.0984 | 6 | -8.0751 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_event_active | 8.0000 | 0.0656 | 4 | -9.7673 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_event_active | 20.0000 | 0.0000 | 0 |  |  |  |
| expanding_fold1 | tfi_follow_flat | 5.0000 | 0.1793 | 135 | -7.9284 | 0.0370 | 0.0370 |
| expanding_fold1 | tfi_follow_flat | 8.0000 | 0.0598 | 45 | -14.8958 | 0.0222 | 0.0222 |
| expanding_fold1 | tfi_follow_flat | 20.0000 | 0.0106 | 8 | -33.1952 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_long_flat | 5.0000 | 0.1811 | 73 | -8.7759 | 0.0411 | 0.0411 |
| expanding_fold1 | tfi_long_flat | 8.0000 | 0.0670 | 27 | -17.1221 | 0.0370 | 0.0370 |
| expanding_fold1 | tfi_long_flat | 20.0000 | 0.0199 | 8 | -34.8218 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_short_flat | 5.0000 | 0.1838 | 75 | -7.3177 | 0.0267 | 0.0267 |
| expanding_fold1 | tfi_short_flat | 8.0000 | 0.0588 | 24 | -11.7882 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_short_flat | 20.0000 | 0.0025 | 1 | -9.5133 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_short_stale25 | 5.0000 | 0.0741 | 2 | -10.6743 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_short_stale25 | 8.0000 | 0.0741 | 2 | -10.6743 | 0.0000 | 0.0000 |
| expanding_fold1 | tfi_short_stale25 | 20.0000 | 0.0000 | 0 |  |  |  |
| expanding_fold2 | tfi_event_active | 5.0000 | 0.1653 | 20 | -12.0448 | 0.0500 | 0.0500 |
| expanding_fold2 | tfi_event_active | 8.0000 | 0.1074 | 13 | -14.5844 | 0.0769 | 0.0769 |
| expanding_fold2 | tfi_event_active | 20.0000 | 0.0165 | 2 | -28.3199 | 0.0000 | 0.0000 |
| expanding_fold2 | tfi_follow_flat | 5.0000 | 0.2149 | 199 | -8.8901 | 0.1457 | 0.1457 |
| expanding_fold2 | tfi_follow_flat | 8.0000 | 0.1199 | 111 | -13.7444 | 0.1261 | 0.1261 |
| expanding_fold2 | tfi_follow_flat | 20.0000 | 0.0324 | 30 | -34.5325 | 0.0667 | 0.0667 |
| expanding_fold2 | tfi_long_flat | 5.0000 | 0.2100 | 80 | -7.1679 | 0.0875 | 0.0875 |
| expanding_fold2 | tfi_long_flat | 8.0000 | 0.0997 | 38 | -12.0670 | 0.0789 | 0.0789 |
| expanding_fold2 | tfi_long_flat | 20.0000 | 0.0184 | 7 | -30.6511 | 0.0000 | 0.0000 |
| expanding_fold2 | tfi_short_flat | 5.0000 | 0.2309 | 142 | -10.1582 | 0.1761 | 0.1761 |
| expanding_fold2 | tfi_short_flat | 8.0000 | 0.1431 | 88 | -14.3062 | 0.1591 | 0.1591 |
| expanding_fold2 | tfi_short_flat | 20.0000 | 0.0472 | 29 | -32.2744 | 0.1379 | 0.1379 |
| expanding_fold2 | tfi_short_stale25 | 5.0000 | 0.1644 | 12 | -13.6624 | 0.0000 | 0.0000 |
| expanding_fold2 | tfi_short_stale25 | 8.0000 | 0.1096 | 8 | -16.8257 | 0.0000 | 0.0000 |
| expanding_fold2 | tfi_short_stale25 | 20.0000 | 0.0274 | 2 | -28.3199 | 0.0000 | 0.0000 |
| expanding_fold3 | tfi_event_active | 5.0000 | 0.2857 | 60 | -11.6214 | 0.1333 | 0.1333 |
| expanding_fold3 | tfi_event_active | 8.0000 | 0.2048 | 43 | -15.2605 | 0.1163 | 0.1163 |
| expanding_fold3 | tfi_event_active | 20.0000 | 0.0667 | 14 | -19.1698 | 0.2857 | 0.2857 |
| expanding_fold3 | tfi_follow_flat | 5.0000 | 0.2985 | 337 | -8.3829 | 0.1691 | 0.1691 |
| expanding_fold3 | tfi_follow_flat | 8.0000 | 0.1931 | 218 | -11.5224 | 0.1468 | 0.1468 |
| expanding_fold3 | tfi_follow_flat | 20.0000 | 0.0700 | 79 | -20.3894 | 0.1392 | 0.1392 |
| expanding_fold3 | tfi_long_flat | 5.0000 | 0.2941 | 145 | -9.4084 | 0.1931 | 0.1931 |
| expanding_fold3 | tfi_long_flat | 8.0000 | 0.1988 | 98 | -12.7088 | 0.1531 | 0.1531 |
| expanding_fold3 | tfi_long_flat | 20.0000 | 0.0832 | 41 | -21.9620 | 0.1463 | 0.1463 |
| expanding_fold3 | tfi_short_flat | 5.0000 | 0.3115 | 223 | -8.3914 | 0.1480 | 0.1480 |
| expanding_fold3 | tfi_short_flat | 8.0000 | 0.1941 | 139 | -11.8793 | 0.1367 | 0.1367 |
| expanding_fold3 | tfi_short_flat | 20.0000 | 0.0615 | 44 | -21.7364 | 0.1136 | 0.1136 |
| expanding_fold3 | tfi_short_stale25 | 5.0000 | 0.3130 | 41 | -9.9137 | 0.1463 | 0.1463 |
| expanding_fold3 | tfi_short_stale25 | 8.0000 | 0.1985 | 26 | -12.9863 | 0.1538 | 0.1538 |
| expanding_fold3 | tfi_short_stale25 | 20.0000 | 0.0687 | 9 | -12.7994 | 0.3333 | 0.3333 |

## Matched Random
| fold | trigger_class | entries | signal_mean_bps | matched_random_mean_p50_bps | matched_random_mean_p95_bps | prob_random_mean_ge_signal | signal_minus_random_p50_bps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | tfi_event_active | 61 | 1.2920 | -1.8342 | -0.5193 | 0.0000 | 3.1262 |
| expanding_fold1 | tfi_follow_flat | 753 | -1.2151 | -2.0840 | -1.7677 | 0.0000 | 0.8689 |
| expanding_fold1 | tfi_long_flat | 403 | -1.2886 | -2.0797 | -1.6613 | 0.0000 | 0.7911 |
| expanding_fold1 | tfi_short_flat | 408 | -1.3581 | -2.0757 | -1.6105 | 0.0180 | 0.7176 |
| expanding_fold1 | tfi_short_stale25 | 27 | 1.3312 | -2.1910 | -0.5431 | 0.0040 | 3.5223 |
| expanding_fold2 | tfi_event_active | 121 | 1.7959 | -2.1500 | -0.1452 | 0.0060 | 3.9459 |
| expanding_fold2 | tfi_follow_flat | 926 | 1.5389 | -2.1420 | -1.6149 | 0.0000 | 3.6809 |
| expanding_fold2 | tfi_long_flat | 381 | 1.2395 | -1.8143 | -0.9970 | 0.0000 | 3.0538 |
| expanding_fold2 | tfi_short_flat | 615 | 1.3572 | -2.2995 | -1.6458 | 0.0000 | 3.6567 |
| expanding_fold2 | tfi_short_stale25 | 73 | 0.1424 | -2.3505 | -0.7733 | 0.0100 | 2.4929 |
| expanding_fold3 | tfi_event_active | 210 | 4.1374 | -1.7159 | 0.5010 | 0.0000 | 5.8534 |
| expanding_fold3 | tfi_follow_flat | 1129 | 2.4978 | -1.9471 | -1.3198 | 0.0000 | 4.4449 |
| expanding_fold3 | tfi_long_flat | 493 | 2.3091 | -2.1661 | -1.2406 | 0.0000 | 4.4752 |
| expanding_fold3 | tfi_short_flat | 716 | 2.4218 | -1.7487 | -1.0956 | 0.0000 | 4.1705 |
| expanding_fold3 | tfi_short_stale25 | 131 | 5.1872 | -1.8433 | -0.0774 | 0.0000 | 7.0305 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_stop_events_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_summary_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_cost_stress_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_topk_removal_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_stop_summary_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_adverse_excursion_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_day_leaveout_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_matched_random_20260517_ccusdt_tail_stop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tail_stop_deep_dive_summary_20260517_ccusdt_tail_stop_deep_dive_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_tail_stop_deep_dive.py
```

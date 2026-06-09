# CCUSDT V1 TFI Mutual Strategy Optimization

Status: `20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1`.

Guardrail: `research_only_mutual_bucket_strategy_optimization_no_execution_recommendation_no_alpha_claim`.

This is a strategy-optimization prototype on already mutually-exclusive positive-EV TFI buckets. It allows cost-dragged entries and does not reject a bucket because its cost-adjusted median is negative.

## Scope

- Selection fold for eligible buckets and optimization ranking: `expanding_fold3`.
- Eligible bucket rule: `total_net_bps > 90` and `net_mean_bps > 0`.
- Target label for hit-rate reporting: `net > 2`.
- Base bucket weights searched: `0.5,1.0,1.5,2.0`.
- Eligible buckets: `tfi_follow_flat+tfi_long_flat, tfi_follow_flat+tfi_long_flat+tfi_event_active, tfi_follow_flat+tfi_short_flat, tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active, tfi_long_flat`.

## Readout

The optimization keeps every eligible positive-EV bucket available. Bucket-grid variants tune relative weight from `0.5x` to `2.0x`; weak-signal variants apply a sizing boost to entries selected by previously measured weak entry-time lift rows. No hard filter is applied.

Practical read: the strongest recent-fold form is to keep the broad `follow+short` and `follow+long` buckets at reduced size, overweight the clean `follow+short+stale25+event_active` child, and treat weak entry-time signals as sizing boosts only. Fold1 remains negative for this family, so the optimized result is a recent-regime usable prototype, not a three-fold stable final strategy.

## Best Fold3 Variants

| variant | variant_kind | entries | exposure_units | total_weighted_net_bps | weighted_mean_net_bps | weighted_median_net_bps | weighted_gt2_rate | cost_hit_rate | weighted_cvar10_net_bps | max_drawdown_bps_units | top10_share_of_total_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| weak_overlay_rank12 | weak_signal_sizing | 1164 | 858.5000 | 3168.6474 | 3.6909 | 0.7618 | 0.4843 | 0.4950 | -23.1757 | -303.4879 | 1.2601 |
| weak_overlay_rank06 | weak_signal_sizing | 1164 | 770.0000 | 2645.5364 | 3.4358 | -0.1810 | 0.4766 | 0.5019 | -23.5563 | -248.8633 | 1.3133 |
| weak_overlay_rank11 | weak_signal_sizing | 1164 | 775.7500 | 2622.7832 | 3.3810 | -0.1816 | 0.4737 | 0.5047 | -23.6446 | -265.1008 | 1.3119 |
| weak_overlay_rank09 | weak_signal_sizing | 1164 | 762.0000 | 2552.7482 | 3.3501 | -0.1816 | 0.4721 | 0.5059 | -24.2157 | -242.8630 | 1.3400 |
| weak_overlay_rank10 | weak_signal_sizing | 1164 | 764.7500 | 2544.5846 | 3.3273 | -0.1816 | 0.4730 | 0.5054 | -23.6306 | -248.2498 | 1.3180 |
| weak_overlay_rank02 | weak_signal_sizing | 1164 | 755.0000 | 2496.3090 | 3.3064 | -0.1816 | 0.4722 | 0.5060 | -23.8114 | -248.8633 | 1.3260 |
| weak_overlay_rank05 | weak_signal_sizing | 1164 | 753.7500 | 2473.9604 | 3.2822 | -0.1816 | 0.4720 | 0.5061 | -23.8114 | -248.8633 | 1.3334 |
| weak_overlay_rank08 | weak_signal_sizing | 1164 | 758.0000 | 2484.2554 | 3.2774 | -0.1816 | 0.4720 | 0.5059 | -23.8925 | -247.8897 | 1.3393 |
| bucket_grid_rank01 | bucket_weight_grid | 1164 | 753.0000 | 2462.3378 | 3.2700 | -0.1816 | 0.4714 | 0.5066 | -23.8114 | -248.8633 | 1.3364 |
| weak_overlay_rank03 | weak_signal_sizing | 1164 | 753.0000 | 2462.3378 | 3.2700 | -0.1816 | 0.4714 | 0.5066 | -23.8114 | -248.8633 | 1.3364 |
| weak_overlay_rank01 | weak_signal_sizing | 1164 | 753.2500 | 2460.5035 | 3.2665 | -0.1816 | 0.4713 | 0.5068 | -23.8114 | -248.8633 | 1.3374 |
| weak_overlay_rank04 | weak_signal_sizing | 1164 | 753.2500 | 2460.5035 | 3.2665 | -0.1816 | 0.4713 | 0.5068 | -23.8114 | -248.8633 | 1.3374 |
| bucket_grid_rank03 | bucket_weight_grid | 1164 | 786.0000 | 2561.2805 | 3.2586 | -0.1816 | 0.4726 | 0.5057 | -24.1424 | -255.0105 | 1.3324 |
| weak_overlay_rank07 | weak_signal_sizing | 1164 | 754.0000 | 2456.0675 | 3.2574 | -0.1816 | 0.4715 | 0.5066 | -23.8296 | -247.8897 | 1.3399 |
| bucket_grid_rank02 | bucket_weight_grid | 1164 | 770.5000 | 2509.1262 | 3.2565 | -0.1816 | 0.4718 | 0.5062 | -24.0222 | -250.5451 | 1.3449 |
| bucket_grid_rank06 | bucket_weight_grid | 1164 | 819.0000 | 2660.2232 | 3.2481 | -0.1816 | 0.4737 | 0.5049 | -24.5134 | -265.0559 | 1.3328 |
| bucket_grid_rank05 | bucket_weight_grid | 1164 | 803.5000 | 2608.0689 | 3.2459 | -0.1816 | 0.4729 | 0.5053 | -24.5991 | -260.2686 | 1.3449 |
| bucket_grid_rank04 | bucket_weight_grid | 1164 | 788.0000 | 2555.9146 | 3.2435 | -0.1816 | 0.4721 | 0.5057 | -24.6167 | -255.8031 | 1.3574 |
| bucket_grid_rank10 | bucket_weight_grid | 1164 | 852.0000 | 2759.1659 | 3.2385 | -0.1816 | 0.4748 | 0.5041 | -24.7905 | -275.1012 | 1.3331 |
| bucket_grid_rank09 | bucket_weight_grid | 1164 | 836.5000 | 2707.0116 | 3.2361 | -0.1816 | 0.4740 | 0.5045 | -24.8775 | -270.3139 | 1.3448 |
| bucket_grid_rank08 | bucket_weight_grid | 1164 | 821.0000 | 2654.8573 | 3.2337 | -0.1816 | 0.4732 | 0.5049 | -24.9666 | -265.5267 | 1.3569 |
| bucket_grid_rank07 | bucket_weight_grid | 1164 | 805.5000 | 2602.7030 | 3.2312 | -0.1816 | 0.4724 | 0.5053 | -24.9862 | -261.0612 | 1.3695 |
| bucket_grid_rank12 | bucket_weight_grid | 1164 | 869.5000 | 2805.9543 | 3.2271 | -0.1810 | 0.4750 | 0.5037 | -25.1337 | -280.3593 | 1.3447 |
| bucket_grid_rank13 | bucket_weight_grid | 1164 | 854.0000 | 2753.8000 | 3.2246 | -0.1816 | 0.4742 | 0.5041 | -25.2920 | -275.5720 | 1.3564 |
| bucket_grid_rank11 | bucket_weight_grid | 1164 | 838.5000 | 2701.6457 | 3.2220 | -0.1816 | 0.4735 | 0.5045 | -25.3148 | -270.7847 | 1.3685 |
| bucket_grid_rank15 | bucket_weight_grid | 1164 | 887.0000 | 2852.7427 | 3.2162 | -0.1810 | 0.4752 | 0.5034 | -25.5278 | -285.6173 | 1.3559 |
| bucket_grid_rank14 | bucket_weight_grid | 1164 | 871.5000 | 2800.5884 | 3.2135 | -0.1810 | 0.4745 | 0.5037 | -25.6208 | -280.8301 | 1.3676 |
| bucket_grid_rank16 | bucket_weight_grid | 1164 | 904.5000 | 2899.5311 | 3.2057 | -0.1810 | 0.4754 | 0.5030 | -25.9065 | -290.8754 | 1.3363 |
| bucket_grid_rank17 | bucket_weight_grid | 1164 | 696.0000 | 2127.1578 | 3.0563 | -0.2316 | 0.4677 | 0.5093 | -24.1040 | -220.4014 | 1.3908 |
| bucket_grid_rank18 | bucket_weight_grid | 1164 | 729.0000 | 2226.1005 | 3.0536 | -0.2262 | 0.4691 | 0.5082 | -24.5224 | -230.1250 | 1.3740 |

## Cross-Fold Scorecard

| variant | variant_kind | optimization_status | weighted_mean_net_bps_expanding_fold1 | weighted_mean_net_bps_expanding_fold2 | weighted_mean_net_bps_expanding_fold3 | positive_fold_count | min_fold_mean_bps | total_weighted_net_bps_expanding_fold3 | weighted_cvar10_net_bps_expanding_fold3 | max_drawdown_bps_units_expanding_fold3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| weak_overlay_rank12 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -0.9214 | 1.1220 | 3.6909 | 2 | -0.9214 | 3168.6474 | -23.1757 | -303.4879 |
| weak_overlay_rank06 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0634 | 1.2056 | 3.4358 | 2 | -1.0634 | 2645.5364 | -23.5563 | -248.8633 |
| weak_overlay_rank11 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0902 | 1.1627 | 3.3810 | 2 | -1.0902 | 2622.7832 | -23.6446 | -265.1008 |
| weak_overlay_rank09 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0564 | 1.1301 | 3.3501 | 2 | -1.0564 | 2552.7482 | -24.2157 | -242.8630 |
| weak_overlay_rank10 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0902 | 1.2090 | 3.3273 | 2 | -1.0902 | 2544.5846 | -23.6306 | -248.2498 |
| weak_overlay_rank02 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0618 | 1.2057 | 3.3064 | 2 | -1.0618 | 2496.3090 | -23.8114 | -248.8633 |
| weak_overlay_rank05 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0580 | 1.1916 | 3.2822 | 2 | -1.0580 | 2473.9604 | -23.8114 | -248.8633 |
| weak_overlay_rank08 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0822 | 1.1683 | 3.2774 | 2 | -1.0822 | 2484.2554 | -23.8925 | -247.8897 |
| bucket_grid_rank01 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.0634 | 1.2020 | 3.2700 | 2 | -1.0634 | 2462.3378 | -23.8114 | -248.8633 |
| weak_overlay_rank03 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0859 | 1.1925 | 3.2700 | 2 | -1.0859 | 2462.3378 | -23.8114 | -248.8633 |
| weak_overlay_rank01 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0686 | 1.2009 | 3.2665 | 2 | -1.0686 | 2460.5035 | -23.8114 | -248.8633 |
| weak_overlay_rank04 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0859 | 1.1709 | 3.2665 | 2 | -1.0859 | 2460.5035 | -23.8114 | -248.8633 |
| bucket_grid_rank03 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.9780 | 1.3272 | 3.2586 | 2 | -0.9780 | 2561.2805 | -24.1424 | -255.0105 |
| weak_overlay_rank07 | weak_signal_sizing | recent_usable_prototype_fold1_weak | -1.0707 | 1.1785 | 3.2574 | 2 | -1.0707 | 2456.0675 | -23.8296 | -247.8897 |
| bucket_grid_rank02 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.1179 | 1.0884 | 3.2565 | 2 | -1.1179 | 2509.1262 | -24.0222 | -250.5451 |
| bucket_grid_rank06 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.8987 | 1.4428 | 3.2481 | 2 | -0.8987 | 2660.2232 | -24.5134 | -265.0559 |
| bucket_grid_rank05 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.0330 | 1.2144 | 3.2459 | 2 | -1.0330 | 2608.0689 | -24.5991 | -260.2686 |
| bucket_grid_rank04 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.1691 | 0.9812 | 3.2435 | 2 | -1.1691 | 2555.9146 | -24.6167 | -255.8031 |
| bucket_grid_rank10 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.8249 | 1.5498 | 3.2385 | 2 | -0.8249 | 2759.1659 | -24.7905 | -275.1012 |
| bucket_grid_rank09 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.9541 | 1.3311 | 3.2361 | 2 | -0.9541 | 2707.0116 | -24.8775 | -270.3139 |
| bucket_grid_rank08 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.0849 | 1.1078 | 3.2337 | 2 | -1.0849 | 2654.8573 | -24.9666 | -265.5267 |
| bucket_grid_rank07 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.2174 | 0.8800 | 3.2312 | 2 | -1.2174 | 2602.7030 | -24.9862 | -261.0612 |
| bucket_grid_rank12 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.8805 | 1.4393 | 3.2271 | 2 | -0.8805 | 2805.9543 | -25.1337 | -280.3593 |
| bucket_grid_rank13 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.0064 | 1.2253 | 3.2246 | 2 | -1.0064 | 2753.8000 | -25.2920 | -275.5720 |
| bucket_grid_rank11 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.1339 | 1.0070 | 3.2220 | 2 | -1.1339 | 2701.6457 | -25.3148 | -270.7847 |
| bucket_grid_rank15 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.9330 | 1.3344 | 3.2162 | 2 | -0.9330 | 2852.7427 | -25.5278 | -285.6173 |
| bucket_grid_rank14 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.0559 | 1.1249 | 3.2135 | 2 | -1.0559 | 2800.5884 | -25.6208 | -280.8301 |
| bucket_grid_rank16 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.9829 | 1.2348 | 3.2057 | 2 | -0.9829 | 2899.5311 | -25.9065 | -290.8754 |
| bucket_grid_rank17 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.1287 | 1.2560 | 3.0563 | 2 | -1.1287 | 2127.1578 | -24.1040 | -220.4014 |
| bucket_grid_rank18 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.0384 | 1.3860 | 3.0536 | 2 | -1.0384 | 2226.1005 | -24.5224 | -230.1250 |
| bucket_grid_rank20 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -0.9547 | 1.5055 | 3.0512 | 2 | -0.9547 | 2325.0432 | -24.8317 | -240.1703 |
| bucket_grid_rank19 | bucket_weight_grid | recent_usable_prototype_fold1_weak | -1.1826 | 1.1341 | 3.0469 | 2 | -1.1826 | 2173.9462 | -24.6189 | -225.6595 |
| full_bucket_equal_1x | baseline | recent_usable_prototype_fold1_weak | -1.2713 | 1.3858 | 2.5031 | 2 | -1.2713 | 2913.5956 | -24.9520 | -344.5384 |

## Selected Weights

| variant | variant_kind | membership_set | base_weight | overlay_feature | overlay_direction | overlay_share | overlay_boost | overlay_scope | overlay_membership_set |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_bucket_equal_1x | baseline | tfi_follow_flat+tfi_long_flat | 1.0000 |  |  |  |  |  |  |
| full_bucket_equal_1x | baseline | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.0000 |  |  |  |  |  |  |
| full_bucket_equal_1x | baseline | tfi_follow_flat+tfi_short_flat | 1.0000 |  |  |  |  |  |  |
| full_bucket_equal_1x | baseline | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 1.0000 |  |  |  |  |  |  |
| full_bucket_equal_1x | baseline | tfi_long_flat | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank01 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank01 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank01 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank01 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank01 | bucket_weight_grid | tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank02 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank02 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank02 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank02 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank02 | bucket_weight_grid | tfi_long_flat | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank03 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank03 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank03 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank03 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank03 | bucket_weight_grid | tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank04 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank04 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank04 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank04 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank04 | bucket_weight_grid | tfi_long_flat | 1.5000 |  |  |  |  |  |  |
| bucket_grid_rank05 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank05 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank05 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank05 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank05 | bucket_weight_grid | tfi_long_flat | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank06 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank06 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.5000 |  |  |  |  |  |  |
| bucket_grid_rank06 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank06 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank06 | bucket_weight_grid | tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank07 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank07 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank07 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank07 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank07 | bucket_weight_grid | tfi_long_flat | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank08 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank08 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank08 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank08 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank08 | bucket_weight_grid | tfi_long_flat | 1.5000 |  |  |  |  |  |  |
| bucket_grid_rank09 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank09 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.5000 |  |  |  |  |  |  |
| bucket_grid_rank09 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank09 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank09 | bucket_weight_grid | tfi_long_flat | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank10 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank10 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank10 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank10 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank10 | bucket_weight_grid | tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank11 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank11 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank11 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank11 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank11 | bucket_weight_grid | tfi_long_flat | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank12 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank12 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank12 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank12 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank12 | bucket_weight_grid | tfi_long_flat | 1.0000 |  |  |  |  |  |  |
| bucket_grid_rank13 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank13 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.5000 |  |  |  |  |  |  |
| bucket_grid_rank13 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank13 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank13 | bucket_weight_grid | tfi_long_flat | 1.5000 |  |  |  |  |  |  |
| bucket_grid_rank14 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank14 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 1.5000 |  |  |  |  |  |  |
| bucket_grid_rank14 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank14 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank14 | bucket_weight_grid | tfi_long_flat | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank15 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank15 | bucket_weight_grid | tfi_follow_flat+tfi_long_flat+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank15 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat | 0.5000 |  |  |  |  |  |  |
| bucket_grid_rank15 | bucket_weight_grid | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 2.0000 |  |  |  |  |  |  |
| bucket_grid_rank15 | bucket_weight_grid | tfi_long_flat | 1.5000 |  |  |  |  |  |  |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_strategy_variants_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_strategy_scorecard_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_strategy_weights_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_strategy_summary_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_mutual_strategy_opt.py --run-tag 20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1
```

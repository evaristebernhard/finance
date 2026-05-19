# CCUSDT V1 TFI Mutual Entry Lift

Status: `20260518_ccusdt_v1_tfi_mutual_entry_lift_v1`.

Guardrail: `research_only_mutual_bucket_entry_lift_no_execution_recommendation_no_alpha_claim`.

This report works inside already mutually-exclusive positive-EV TFI buckets. It does not discard a bucket because `net_median` is negative. The question is whether entry-time variables can improve the chance of `net > 2 bps` or capture the right tail better than simply trading the whole positive-EV bucket.

## Scope

- Fold: `expanding_fold3`.
- Target: `fixed_net_maker_bps > 2`.
- Positive-EV bucket rule: `total_net_bps > 90` and `net_mean_bps > 0`.
- Eligible buckets: `tfi_follow_flat+tfi_long_flat, tfi_follow_flat+tfi_long_flat+tfi_event_active, tfi_follow_flat+tfi_short_flat, tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active, tfi_long_flat`.

## Baseline Buckets

| scope | membership_set | entries | net_mean_bps | net_median_bps | gt_target_rate | total_net_bps | top10_net_bps | left10_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eligible_union | ALL_POSITIVE_EV_BUCKETS | 1164 | 2.5031 | -0.3931 | 0.4579 | 2913.5956 | 4496.9991 | -2919.3782 |
| bucket | tfi_follow_flat+tfi_long_flat | 390 | 2.1615 | -0.6752 | 0.4385 | 843.0004 | 1590.3098 | -1110.4493 |
| bucket | tfi_follow_flat+tfi_long_flat+tfi_event_active | 66 | 2.9983 | 2.2486 | 0.5000 | 197.8854 | 242.8914 | -218.9709 |
| bucket | tfi_follow_flat+tfi_short_flat | 559 | 1.9835 | -0.5124 | 0.4526 | 1108.7730 | 1767.1318 | -1208.1822 |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 114 | 5.8804 | 2.8471 | 0.5175 | 670.3600 | 706.9549 | -234.2181 |
| bucket | tfi_long_flat | 35 | 2.6736 | 0.9939 | 0.4857 | 93.5768 | 165.9145 | -154.6089 |

## Ranking Readout

- Strict rank signals: `0`.
- Weak diagnostic rank signals: `30`.

A strict row must beat exposure on top-tail capture, lift `P(net>2)` by `>1.5x`, retain at least `85%` total net, retain at least `80%` top-tail net, reduce left-tail loss by at least `25%`, and improve selected mean by `>1` bps.

If no strict row appears for a bucket, the correct read is not to filter it away. The bucket remains the statistical entry unit; ranking can be used only as a sizing diagnostic until walk-forward proof exists.

## Best Diagnostic Rows

| scope | membership_set | feature | select_direction | select_share | entries_selected | target_rate_all | target_rate_selected | target_lift | net_per_entry_lift_bps | total_net_retention | top_tail_count_capture_rate | left_tail_reduction | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bucket | tfi_long_flat | abs_past_event_25_bps | low | 0.1000 | 4 | 0.4857 | 0.7500 | 1.5441 | 23.9262 | 1.1370 | 0.5000 | 0.9689 | weak_rank_signal |
| bucket | tfi_long_flat | entry_hour | low | 0.1000 | 4 | 0.4857 | 0.7500 | 1.5441 | 8.5857 | 0.4813 | 0.2500 | 0.9938 | weak_rank_signal |
| bucket | tfi_long_flat | past_event_25_bps | low | 0.2000 | 7 | 0.4857 | 0.7143 | 1.4706 | 6.1015 | 0.6564 | 0.2500 | 0.8645 | weak_rank_signal |
| bucket | tfi_long_flat | entry_spread_bps | low | 0.2000 | 7 | 0.4857 | 0.7143 | 1.4706 | 0.8727 | 0.2653 | 0.2500 | 0.7828 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | entry_spread_bps | low | 0.1000 | 12 | 0.5175 | 0.7500 | 1.4492 | 7.2707 | 0.2354 | 0.3333 | 0.9197 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_long_flat+tfi_event_active | trade_window_count | high | 0.1000 | 7 | 0.5000 | 0.7143 | 1.4286 | 15.9110 | 0.6689 | 0.4286 | 0.9664 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat | frames_since_mid_change | low | 0.1000 | 56 | 0.4526 | 0.6429 | 1.4204 | 1.8268 | 0.1924 | 0.1429 | 0.9046 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_long_flat | entry_spread_bps | low | 0.2000 | 78 | 0.4385 | 0.5897 | 1.3450 | 4.2954 | 0.5974 | 0.3333 | 0.8673 | weak_rank_signal |
| eligible_union | ALL_POSITIVE_EV_BUCKETS | frames_since_mid_change | high | 0.1000 | 117 | 0.4579 | 0.6154 | 1.3439 | 4.5499 | 0.2832 | 0.1624 | 0.9347 | weak_rank_signal |
| bucket | tfi_long_flat | trade_window_count | low | 0.3000 | 11 | 0.4857 | 0.6364 | 1.3102 | 11.7651 | 1.6973 | 0.7500 | 0.8990 | weak_rank_signal |
| bucket | tfi_long_flat | entry_spread_bps | low | 0.3000 | 11 | 0.4857 | 0.6364 | 1.3102 | 1.8434 | 0.5310 | 0.5000 | 0.6160 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | trade_window_count | high | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 2.3087 | 0.1466 | 0.1667 | 0.9562 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | abs_feature_value_max | high | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | abs_feature_value_max | low | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | direction_aligned_feature_mean | high | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | direction_aligned_feature_mean | low | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | past_event_25_bps | high | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | past_event_25_bps | low | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | abs_past_event_25_bps | high | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | abs_past_event_25_bps | low | 0.1000 | 12 | 0.5175 | 0.6667 | 1.2881 | 1.6381 | 0.1346 | 0.1667 | 0.9519 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | entry_spread_bps | low | 0.3000 | 35 | 0.5175 | 0.6571 | 1.2697 | 1.1892 | 0.3691 | 0.5000 | 0.7045 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | entry_spread_bps | low | 0.2000 | 23 | 0.5175 | 0.6522 | 1.2601 | 1.7139 | 0.2606 | 0.4167 | 0.7956 | weak_rank_signal |
| bucket | tfi_long_flat | trade_window_count | low | 0.5000 | 18 | 0.4857 | 0.6111 | 1.2582 | 7.2209 | 1.9033 | 0.7500 | 0.7138 | weak_rank_signal |
| bucket | tfi_long_flat | entry_hour | low | 0.5000 | 18 | 0.4857 | 0.6111 | 1.2582 | 4.3855 | 1.3579 | 1.0000 | 0.5352 | weak_rank_signal |
| eligible_union | ALL_POSITIVE_EV_BUCKETS | trade_window_count | low | 0.1000 | 117 | 0.4579 | 0.5726 | 1.2506 | 1.3184 | 0.1535 | 0.1026 | 0.9009 | weak_rank_signal |
| eligible_union | ALL_POSITIVE_EV_BUCKETS | frames_since_mid_change | low | 0.1000 | 117 | 0.4579 | 0.5641 | 1.2319 | 1.0156 | 0.1413 | 0.1282 | 0.9002 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_long_flat | trade_window_count | high | 0.1000 | 39 | 0.4385 | 0.5385 | 1.2281 | 7.4066 | 0.4427 | 0.2308 | 0.8266 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_long_flat | entry_spread_bps | low | 0.1000 | 39 | 0.4385 | 0.5385 | 1.2281 | 6.5164 | 0.4015 | 0.1538 | 0.9576 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_long_flat | frames_since_mid_change | low | 0.1000 | 39 | 0.4385 | 0.5385 | 1.2281 | 1.3278 | 0.1614 | 0.1282 | 0.9412 | weak_rank_signal |
| bucket | tfi_follow_flat+tfi_short_flat | trade_window_count | low | 0.1000 | 56 | 0.4526 | 0.5536 | 1.2231 | 1.3454 | 0.1681 | 0.1429 | 0.8867 | weak_rank_signal |
| bucket | tfi_long_flat | entry_spread_bps | low | 0.1000 | 4 | 0.4857 | 0.7500 | 1.5441 | -2.1736 | 0.0214 | 0.2500 | 0.7896 | keep_full_bucket_no_filter |
| bucket | tfi_long_flat | abs_past_event_25_bps | low | 0.5000 | 18 | 0.4857 | 0.6111 | 1.2582 | 4.4032 | 1.3613 | 0.5000 | 0.6124 | keep_full_bucket_no_filter |
| bucket | tfi_long_flat | entry_spread_bps | low | 0.5000 | 18 | 0.4857 | 0.6111 | 1.2582 | 2.9258 | 1.0771 | 0.5000 | 0.5357 | keep_full_bucket_no_filter |
| bucket | tfi_long_flat | past_event_25_bps | low | 0.5000 | 18 | 0.4857 | 0.6111 | 1.2582 | 2.8201 | 1.0568 | 0.5000 | 0.5440 | keep_full_bucket_no_filter |
| bucket | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | frames_since_mid_change | high | 0.7000 | 80 | 0.5175 | 0.6250 | 1.2076 | 0.3682 | 0.7457 | 0.6667 | 0.4253 | keep_full_bucket_no_filter |
| bucket | tfi_follow_flat+tfi_long_flat+tfi_event_active | entry_hour | low | 0.3000 | 20 | 0.5000 | 0.6000 | 1.2000 | 4.7369 | 0.7818 | 0.5714 | 0.8833 | keep_full_bucket_no_filter |
| bucket | tfi_follow_flat+tfi_long_flat | trade_window_count | high | 0.2000 | 78 | 0.4385 | 0.5256 | 1.1988 | 2.4006 | 0.4221 | 0.2564 | 0.7311 | keep_full_bucket_no_filter |
| eligible_union | ALL_POSITIVE_EV_BUCKETS | abs_feature_value_max | high | 0.1000 | 117 | 0.4579 | 0.5470 | 1.1946 | 0.4555 | 0.1188 | 0.1197 | 0.9129 | keep_full_bucket_no_filter |
| eligible_union | ALL_POSITIVE_EV_BUCKETS | abs_feature_value_max | low | 0.1000 | 117 | 0.4579 | 0.5470 | 1.1946 | 0.4555 | 0.1188 | 0.1197 | 0.9129 | keep_full_bucket_no_filter |
| eligible_union | ALL_POSITIVE_EV_BUCKETS | direction_aligned_feature_mean | high | 0.1000 | 117 | 0.4579 | 0.5470 | 1.1946 | 0.4555 | 0.1188 | 0.1197 | 0.9129 | keep_full_bucket_no_filter |

## Leakage Audit

| column | entry_time_allowed | reason |
| --- | --- | --- |
| fixed_gross_bps | False | outcome/path/cost-after-exit information |
| fixed_cost_maker_bps | False | outcome/path/cost-after-exit information |
| fixed_cost_taker_bps | False | outcome/path/cost-after-exit information |
| fixed_cost_wide_bps | False | outcome/path/cost-after-exit information |
| fixed_net_maker_bps | False | outcome/path/cost-after-exit information |
| fixed_net_taker_bps | False | outcome/path/cost-after-exit information |
| fixed_net_wide_bps | False | outcome/path/cost-after-exit information |
| fixed_cross_maker | False | outcome/path/cost-after-exit information |
| fixed_cross_taker | False | outcome/path/cost-after-exit information |
| mfe_bps | False | outcome/path/cost-after-exit information |
| mae_bps | False | outcome/path/cost-after-exit information |
| has_mid_transition | False | outcome/path/cost-after-exit information |
| has_quote_transition | False | outcome/path/cost-after-exit information |
| mid_transition_count | False | outcome/path/cost-after-exit information |
| quote_transition_count | False | outcome/path/cost-after-exit information |
| first_mid_transition_hold_sec | False | outcome/path/cost-after-exit information |
| first_quote_transition_hold_sec | False | outcome/path/cost-after-exit information |
| first_mid_transition_gross_bps | False | outcome/path/cost-after-exit information |
| first_quote_transition_gross_bps | False | outcome/path/cost-after-exit information |
| final_exit_row | False | outcome/path/cost-after-exit information |
| final_hold_sec | False | outcome/path/cost-after-exit information |
| abs_feature_value_max | True | known at entry or bucket membership state |
| direction_aligned_feature_mean | True | known at entry or bucket membership state |
| entry_spread_bps | True | known at entry or bucket membership state |
| trade_window_count | True | known at entry or bucket membership state |
| frames_since_mid_change | True | known at entry or bucket membership state |
| past_event_25_bps | True | known at entry or bucket membership state |
| abs_past_event_25_bps | True | known at entry or bucket membership state |
| entry_hour | True | known at entry or bucket membership state |
| tfi_follow_flat | True | known at entry or bucket membership state |
| tfi_short_flat | True | known at entry or bucket membership state |
| tfi_long_flat | True | known at entry or bucket membership state |
| tfi_short_stale25 | True | known at entry or bucket membership state |
| tfi_event_active | True | known at entry or bucket membership state |
| membership_set | True | known at entry or bucket membership state |
| direction | True | known at entry or bucket membership state |
| side | True | known at entry or bucket membership state |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_entry_lift_baseline_20260518_ccusdt_v1_tfi_mutual_entry_lift_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_entry_lift_scan_20260518_ccusdt_v1_tfi_mutual_entry_lift_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_entry_lift_leakage_20260518_ccusdt_v1_tfi_mutual_entry_lift_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_mutual_entry_lift_summary_20260518_ccusdt_v1_tfi_mutual_entry_lift_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_mutual_entry_lift.py --run-tag 20260518_ccusdt_v1_tfi_mutual_entry_lift_v1
```

# CCUSDT Taker/Wait Value Diagnostic v0.1

Guardrail: `research_only_no_runtime_label_dependency_top_of_book_taker_only`.

This diagnostic compares crossing immediately with waiting a short delay and then crossing at top of book while keeping the same fixed terminal horizon:

```text
G_i(delta, H) = Y_i^wait(delta, H) - Y_i^now(H)
              = entry_cross_repair_i(delta) - signed_mid_move_to_wait_i(delta)
```

Future executable labels are diagnostic labels only. Runner/Bot/Monitor are not changed, maker/passive queue alpha remains paused, and no `date/`, scored entry, PnL, MFE, or MAE files are read as runtime input.

## Scope

- symbol: `CCUSDT`
- dates: `2026-05-16..2026-05-18`
- source_scope: `both`
- waits_sec: `[1, 2, 3, 5, 10, 20]`
- horizons_sec: `[5, 20, 60]`
- candidate_count: `44930`
- panel_rows: `629020`
- max_abs_decomposition_error_bps: `0.000000000005`
- out_dir: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\taker_wait_value_diagnostic\ccusdt_2026-05-16_2026-05-18_v0_1`

## Readout

- `wait_better` means waiting improves fixed-terminal executable value after paying top-of-book spread at the delayed entry.
- `cross_now_better` means waiting loses more release than it saves in spread/crossing cost.
- `skip_candidate` means neither now nor delayed entry has positive executable economics for that row.
- `entry_cross_repair_bps` is the spread/crossing improvement from waiting; `signed_mid_move_to_wait_bps` is the release missed before delayed entry.
- If `signed_mid_move_to_wait_bps < 0`, the delayed entry benefited because price moved against the intended side before entry. This is `adverse_preentry_move_benefit`, not clean spread repair.

## Main Conclusion

There is no clean, promoted spread-repair wait rule in this first pass. The current q70/idle01_g1 fast-entry cohort mostly wants to cross immediately when the stale-release structure is valid; positive wait surfaces are mainly either skip/mirage rows or adverse pre-entry movement rows that would require a separate runtime predictor.

## Clean Spread-Repair Wait Candidates

These rows require positive executable value, stable daily gain, and gain dominated by entry crossing repair rather than by price moving against the intended side before delayed entry.

_No rows._

## Adverse Pre-Entry Move Wait Surfaces

These rows can look like wait value, but the gain is dominated by the mid moving against the intended side before the delayed cross. They are diagnostic evidence for a possible pre-entry adverse-move predictor, not a spread-repair admission rule.

| source | family_id | variant_id | cell | wait_sec | horizon_sec | n | mean_now_exec_bps | mean_wait_exec_bps | weighted_mean_wait_gain_bps | mean_entry_cross_repair_bps | mean_signed_mid_move_to_wait_bps | aggregate_wait_mechanism | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_dedup | fast_q70_idle01_g1 | fast_entry_fixed60_taker | 10_r5_only | 20 | 60 | 9 | -4.1994 | 0.3982 | 4.5976 | 0.8521 | -3.7455 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 5 | 60 | 54 | -0.1977 | 2.9130 | 3.1107 | -0.1615 | -3.2722 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 3 | 60 | 54 | -0.1977 | 2.2459 | 2.4437 | -0.1318 | -2.5755 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 10 | 60 | 54 | -0.1977 | 2.0515 | 2.2492 | -0.0771 | -2.3263 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 20 | 60 | 54 | -0.1977 | 1.8918 | 2.0895 | 0.0222 | -2.0673 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 1 | 60 | 54 | -0.1977 | 1.6908 | 1.8886 | -0.0502 | -1.9388 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 2 | 60 | 54 | -0.1977 | 1.5495 | 1.7472 | -0.1538 | -1.9010 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 5 | 60 | 38 | 0.2375 | 1.4834 | 1.2460 | 0.0763 | -1.1696 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 5 | 20 | 38 | -1.2170 | 0.0290 | 1.2460 | 0.0763 | -1.1696 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 10 | 60 | 38 | 0.2375 | 1.4823 | 1.2448 | 0.1201 | -1.1247 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 10 | 20 | 38 | -1.2170 | 0.0279 | 1.2448 | 0.1201 | -1.1247 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 3 | 60 | 38 | 0.2375 | 1.0999 | 0.8624 | 0.0172 | -0.8452 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 2 | 60 | 38 | 0.2375 | 1.0986 | 0.8611 | -0.0067 | -0.8678 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 1 | 60 | 38 | 0.2375 | 0.9030 | 0.6655 | -0.0254 | -0.6909 | adverse_preentry_move_benefit | 0.3333 |

## Executable Wait Surfaces

These rows have positive wait value and at least one positive mean executable label. They are not promoted policies; they are the first places where waiting is economically plausible rather than merely losing less.

| source | family_id | variant_id | cell | wait_sec | horizon_sec | n | mean_now_exec_bps | mean_wait_exec_bps | weighted_mean_wait_gain_bps | mean_entry_cross_repair_bps | mean_signed_mid_move_to_wait_bps | aggregate_wait_mechanism | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_dedup | fast_q70_idle01_g1 | fast_entry_fixed60_taker | 10_r5_only | 20 | 60 | 9 | -4.1994 | 0.3982 | 4.5976 | 0.8521 | -3.7455 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 5 | 60 | 54 | -0.1977 | 2.9130 | 3.1107 | -0.1615 | -3.2722 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 3 | 60 | 54 | -0.1977 | 2.2459 | 2.4437 | -0.1318 | -2.5755 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 10 | 60 | 54 | -0.1977 | 2.0515 | 2.2492 | -0.0771 | -2.3263 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 20 | 60 | 54 | -0.1977 | 1.8918 | 2.0895 | 0.0222 | -2.0673 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 1 | 60 | 54 | -0.1977 | 1.6908 | 1.8886 | -0.0502 | -1.9388 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 2 | 60 | 54 | -0.1977 | 1.5495 | 1.7472 | -0.1538 | -1.9010 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 5 | 60 | 38 | 0.2375 | 1.4834 | 1.2460 | 0.0763 | -1.1696 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 5 | 20 | 38 | -1.2170 | 0.0290 | 1.2460 | 0.0763 | -1.1696 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 10 | 60 | 38 | 0.2375 | 1.4823 | 1.2448 | 0.1201 | -1.1247 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 10 | 20 | 38 | -1.2170 | 0.0279 | 1.2448 | 0.1201 | -1.1247 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 3 | 60 | 38 | 0.2375 | 1.0999 | 0.8624 | 0.0172 | -0.8452 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 2 | 60 | 38 | 0.2375 | 1.0986 | 0.8611 | -0.0067 | -0.8678 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 1 | 60 | 38 | 0.2375 | 0.9030 | 0.6655 | -0.0254 | -0.6909 | adverse_preentry_move_benefit | 0.3333 |

## Cross-Now Surfaces

| source | family_id | variant_id | cell | wait_sec | horizon_sec | n | mean_now_exec_bps | mean_wait_exec_bps | weighted_mean_wait_gain_bps | mean_entry_cross_repair_bps | mean_signed_mid_move_to_wait_bps | aggregate_wait_mechanism | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_dedup | fast_q70_idle01_g1 | fast_entry_fixed60_taker | 00_none | 10 | 20 | 9 | 4.5967 | -0.2675 | -4.8642 | -0.1029 | 4.7613 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 5 | 60 | 3 | 7.1127 | 2.7786 | -4.3340 | -0.2026 | 4.1315 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 10 | 60 | 3 | 7.1127 | 2.7786 | -4.3340 | -0.2026 | 4.1315 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 20 | 60 | 3 | 7.1127 | 2.7786 | -4.3340 | -0.0917 | 4.2423 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 5 | 20 | 3 | 2.1880 | -2.1460 | -4.3340 | -0.2026 | 4.1315 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 10 | 20 | 3 | 2.1880 | -2.1460 | -4.3340 | -0.2026 | 4.1315 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 20 | 60 | 83 | 4.2171 | 0.3035 | -3.9135 | -0.0465 | 3.8671 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 10 | 60 | 83 | 4.2171 | 0.6379 | -3.5791 | -0.1448 | 3.4344 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 10 | 20 | 83 | 1.8373 | -1.7419 | -3.5791 | -0.1448 | 3.4344 | missed_release_loss | 0.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 20 | 60 | 478 | 0.4547 | -2.5681 | -3.0228 | -0.2790 | 2.7437 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 5 | 60 | 83 | 4.2171 | 1.2392 | -2.9779 | -0.0607 | 2.9172 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 5 | 20 | 83 | 1.8373 | -1.1406 | -2.9779 | -0.0607 | 2.9172 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 3 | 20 | 83 | 1.8373 | -0.8890 | -2.7263 | -0.0653 | 2.6609 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 3 | 60 | 83 | 4.2171 | 1.4908 | -2.7263 | -0.0653 | 2.6609 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 3 | 5 | 83 | 0.8732 | -1.8530 | -2.7263 | -0.0653 | 2.6609 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 2 | 20 | 83 | 1.8373 | -0.8576 | -2.6949 | -0.0692 | 2.6257 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 2 | 60 | 83 | 4.2171 | 1.5222 | -2.6949 | -0.0692 | 2.6257 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 2 | 5 | 83 | 0.8732 | -1.8217 | -2.6949 | -0.0692 | 2.6257 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 1 | 60 | 83 | 4.2171 | 1.6677 | -2.5493 | -0.1325 | 2.4169 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 1 | 20 | 83 | 1.8373 | -0.7121 | -2.5493 | -0.1325 | 2.4169 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_event_stale25 |  | 1 | 5 | 83 | 0.8732 | -1.6761 | -2.5493 | -0.1325 | 2.4169 | missed_release_loss | 0.0000 |
| all_dedup | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 10 | 20 | 28 | 0.5129 | -1.8493 | -2.3623 | -0.1392 | 2.2231 | missed_release_loss | 0.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 10 | 20 | 478 | 0.8894 | -1.3382 | -2.2276 | -0.2703 | 1.9574 | missed_release_loss | 0.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 10 | 60 | 478 | 0.4547 | -1.7730 | -2.2276 | -0.2703 | 1.9574 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 2 | 5 | 3 | 1.9664 | -0.1515 | -2.1179 | -0.4238 | 1.6941 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 3 | 5 | 3 | 1.9664 | -0.1515 | -2.1179 | -0.4238 | 1.6941 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 2 | 20 | 3 | 2.1880 | 0.0702 | -2.1179 | -0.4238 | 1.6941 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 3 | 20 | 3 | 2.1880 | 0.0702 | -2.1179 | -0.4238 | 1.6941 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 2 | 60 | 3 | 7.1127 | 4.9948 | -2.1179 | -0.4238 | 1.6941 | missed_release_loss | 0.0000 |
| all_dedup | S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 |  | 3 | 60 | 3 | 7.1127 | 4.9948 | -2.1179 | -0.4238 | 1.6941 | missed_release_loss | 0.0000 |

## Skip / Spread-Cost Mirage Surfaces

| source | family_id | variant_id | cell | wait_sec | horizon_sec | n | mean_now_exec_bps | mean_wait_exec_bps | weighted_mean_wait_gain_bps | mean_entry_cross_repair_bps | mean_signed_mid_move_to_wait_bps | aggregate_wait_mechanism | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 5 | 20 | 54 | -4.2973 | -1.1866 | 3.1107 | -0.1615 | -3.2722 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 3 | 5 | 54 | -5.6859 | -3.2422 | 2.4437 | -0.1318 | -2.5755 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 3 | 20 | 54 | -4.2973 | -1.8537 | 2.4437 | -0.1318 | -2.5755 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 10 | 20 | 54 | -4.2973 | -2.0481 | 2.2492 | -0.0771 | -2.3263 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 1 | 20 | 54 | -4.2973 | -2.4088 | 1.8886 | -0.0502 | -1.9388 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 1 | 5 | 54 | -5.6859 | -3.7973 | 1.8886 | -0.0502 | -1.9388 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 2 | 20 | 54 | -4.2973 | -2.5501 | 1.7472 | -0.1538 | -1.9010 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 2 | 5 | 54 | -5.6859 | -3.9387 | 1.7472 | -0.1538 | -1.9010 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 20 | 60 | 5575 | -3.7009 | -2.1852 | 1.5157 | 0.1460 | -1.3697 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 10 | 60 | 5575 | -3.7009 | -2.4172 | 1.2836 | 0.1280 | -1.1557 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 10 | 20 | 5575 | -3.7594 | -2.4758 | 1.2836 | 0.1280 | -1.1557 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 5 | 60 | 5575 | -3.7009 | -2.7897 | 0.9112 | 0.1132 | -0.7980 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 5 | 20 | 5575 | -3.7594 | -2.8482 | 0.9112 | 0.1132 | -0.7980 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 3 | 20 | 38 | -1.2170 | -0.3545 | 0.8624 | 0.0172 | -0.8452 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 3 | 5 | 38 | -3.7834 | -2.9210 | 0.8624 | 0.0172 | -0.8452 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 2 | 20 | 38 | -1.2170 | -0.3559 | 0.8611 | -0.0067 | -0.8678 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 2 | 5 | 38 | -3.7834 | -2.9223 | 0.8611 | -0.0067 | -0.8678 | adverse_preentry_move_benefit | 0.6667 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 1 | 5 | 38 | -3.7834 | -3.1178 | 0.6655 | -0.0254 | -0.6909 | adverse_preentry_move_benefit | 0.3333 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | 1 | 20 | 38 | -1.2170 | -0.5514 | 0.6655 | -0.0254 | -0.6909 | adverse_preentry_move_benefit | 0.3333 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 3 | 60 | 5575 | -3.7009 | -3.0625 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 3 | 20 | 5575 | -3.7594 | -3.1210 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 3 | 5 | 5575 | -3.2205 | -2.5822 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 2 | 60 | 5575 | -3.7009 | -3.1931 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 2 | 20 | 5575 | -3.7594 | -3.2516 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 2 | 5 | 5575 | -3.2205 | -2.7128 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 1 | 60 | 5575 | -3.7009 | -3.3727 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 1 | 20 | 5575 | -3.7594 | -3.4313 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 1.0000 |
| all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | 1 | 5 | 5575 | -3.2205 | -2.8924 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 1.0000 |
| all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | 20 | 60 | 747 | -1.8805 | -1.7431 | 0.1375 | 0.6649 | 0.5275 | indifferent | 0.6667 |
| all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | 2 | 5 | 747 | -3.2880 | -3.1862 | 0.1018 | 0.2576 | 0.1558 | indifferent | 0.3333 |

## Source-Specific Executable Top Rows

| source | family_id | variant_id | cell | wait_sec | horizon_sec | n | weighted_mean_wait_gain_bps | mean_entry_cross_repair_bps | mean_signed_mid_move_to_wait_bps | aggregate_wait_mechanism | skip_rate | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| structure_candidate | S3_liquidity_vacuum_release | S3_vacuum_recent_breakout |  | 1 | 60 | 87 | -0.2928 | 0.1171 | 0.4099 | missed_release_loss | 0.5057 | 0.6667 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 1 | 60 | 1869 | -0.3952 | -0.1497 | 0.2455 | missed_release_loss | 0.5655 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 1 | 20 | 1869 | -0.3952 | -0.1497 | 0.2455 | missed_release_loss | 0.6517 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 1 | 60 | 1872 | -0.4003 | -0.1588 | 0.2415 | missed_release_loss | 0.5700 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_vacuum_recent_breakout |  | 2 | 60 | 87 | -0.4113 | 0.1251 | 0.5363 | missed_release_loss | 0.5057 | 0.3333 |
| structure_candidate | S3_liquidity_vacuum_release | S3_vacuum_recent_breakout |  | 3 | 60 | 87 | -0.4864 | 0.1729 | 0.6594 | missed_release_loss | 0.5057 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_queue_confirm |  | 1 | 60 | 4564 | -0.5910 | -0.0051 | 0.5859 | missed_release_loss | 0.5390 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_microprice_confirm |  | 1 | 60 | 4593 | -0.5929 | -0.0019 | 0.5910 | missed_release_loss | 0.5386 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 2 | 20 | 1869 | -0.6316 | -0.2096 | 0.4220 | missed_release_loss | 0.6506 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 2 | 60 | 1869 | -0.6316 | -0.2096 | 0.4220 | missed_release_loss | 0.5607 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 2 | 60 | 1872 | -0.6543 | -0.2234 | 0.4309 | missed_release_loss | 0.5652 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_vacuum_recent_breakout |  | 5 | 60 | 87 | -0.6615 | 0.2178 | 0.8792 | missed_release_loss | 0.5057 | 0.0000 |
| structure_candidate | S1_active_flow_stale_release | S1_tfi_follow_flat |  | 1 | 60 | 821 | -0.7489 | -0.0183 | 0.7305 | missed_release_loss | 0.5566 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 3 | 20 | 1869 | -0.8323 | -0.2597 | 0.5726 | missed_release_loss | 0.6490 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 3 | 60 | 1869 | -0.8323 | -0.2597 | 0.5726 | missed_release_loss | 0.5607 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 3 | 60 | 1872 | -0.8356 | -0.2587 | 0.5768 | missed_release_loss | 0.5636 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 1 | 60 | 425 | -0.8368 | -0.1270 | 0.7098 | missed_release_loss | 0.5529 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 1 | 20 | 425 | -0.8368 | -0.1270 | 0.7098 | missed_release_loss | 0.6447 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_queue_confirm |  | 2 | 60 | 4564 | -0.8565 | -0.0119 | 0.8446 | missed_release_loss | 0.5353 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_microprice_confirm |  | 2 | 60 | 4593 | -0.8579 | -0.0087 | 0.8492 | missed_release_loss | 0.5349 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_queue_confirm |  | 3 | 60 | 4564 | -1.0215 | -0.0165 | 1.0049 | missed_release_loss | 0.5342 | 0.0000 |
| structure_candidate | S1_active_flow_stale_release | S1_tfi_follow_flat |  | 2 | 60 | 821 | -1.0254 | -0.0110 | 1.0144 | missed_release_loss | 0.5530 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_microprice_confirm |  | 3 | 60 | 4593 | -1.0286 | -0.0134 | 1.0153 | missed_release_loss | 0.5341 | 0.0000 |
| structure_candidate | S1_active_flow_stale_release | S1_tfi_follow_flat |  | 3 | 60 | 821 | -1.0437 | -0.0217 | 1.0220 | missed_release_loss | 0.5518 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | 5 | 60 | 1872 | -1.0668 | -0.3137 | 0.7532 | missed_release_loss | 0.5609 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 2 | 20 | 425 | -1.1664 | -0.1561 | 1.0103 | missed_release_loss | 0.6424 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 2 | 60 | 425 | -1.1664 | -0.1561 | 1.0103 | missed_release_loss | 0.5482 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 5 | 20 | 1869 | -1.2020 | -0.3037 | 0.8982 | missed_release_loss | 0.6501 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi |  | 5 | 60 | 1869 | -1.2020 | -0.3037 | 0.8982 | missed_release_loss | 0.5607 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 3 | 20 | 425 | -1.2294 | -0.1839 | 1.0455 | missed_release_loss | 0.6376 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 3 | 60 | 425 | -1.2294 | -0.1839 | 1.0455 | missed_release_loss | 0.5482 | 0.0000 |
| fast_entry | fast_q70_idle01_g1 | fast_entry_fixed60_taker | 00_none | 1 | 20 | 199 | -1.2515 | -0.6713 | 0.6121 | missed_release_loss | 0.5176 | 0.0000 |
| fast_entry | fast_q70_idle01_g1 | fast_entry_fixed60_taker | 00_none | 1 | 5 | 199 | -1.2515 | -0.6713 | 0.6121 | missed_release_loss | 0.6583 | 0.0000 |
| fast_entry | fast_q70_idle01_g1 | fast_entry_fixed60_taker | 00_none | 1 | 60 | 199 | -1.2515 | -0.6713 | 0.6121 | missed_release_loss | 0.5126 | 0.0000 |
| structure_candidate | S1_active_flow_stale_release | S1_tfi_follow_flat |  | 5 | 60 | 821 | -1.2725 | -0.0234 | 1.2491 | missed_release_loss | 0.5530 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_queue_confirm |  | 5 | 60 | 4564 | -1.3177 | -0.0162 | 1.3016 | missed_release_loss | 0.5335 | 0.0000 |
| structure_candidate | S2_flow_book_confirmation | S2_tfi_microprice_confirm |  | 5 | 60 | 4593 | -1.3242 | -0.0138 | 1.3104 | missed_release_loss | 0.5332 | 0.0000 |
| structure_candidate | S3_liquidity_vacuum_release | S3_vacuum_recent_breakout |  | 20 | 60 | 87 | -1.3951 | 0.3758 | 1.7709 | missed_release_loss | 0.5057 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 5 | 20 | 425 | -1.5052 | -0.1991 | 1.3061 | missed_release_loss | 0.6424 | 0.0000 |
| structure_candidate | S6_execution_cost_admission | S6_s1_low_spread_admission |  | 5 | 60 | 425 | -1.5052 | -0.1991 | 1.3061 | missed_release_loss | 0.5482 | 0.0000 |

## Policy Candidate Rows

| summary_scope | source | family_id | variant_id | cell | candidate_rule | policy_status | wait_sec | horizon_sec | n | weighted_mean_wait_gain_bps | mean_entry_cross_repair_bps | mean_signed_mid_move_to_wait_bps | aggregate_wait_mechanism | median_wait_gain_bps | positive_day_frac | min_day_weighted_wait_gain_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 5 | 20 | 54 | 3.1107 | -0.1615 | -3.2722 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 18.6159 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 3 | 5 | 54 | 2.4437 | -0.1318 | -2.5755 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 6.0815 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 3 | 20 | 54 | 2.4437 | -0.1318 | -2.5755 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 6.0815 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 10 | 20 | 54 | 2.2492 | -0.0771 | -2.3263 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 5.5880 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 1 | 20 | 54 | 1.8886 | -0.0502 | -1.9388 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -3.2526 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 1 | 5 | 54 | 1.8886 | -0.0502 | -1.9388 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -3.2526 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 2 | 20 | 54 | 1.7472 | -0.1538 | -1.9010 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -8.4670 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_depth_collapse_tfi |  | skip_unexecutable_candidate | skip_candidate | 2 | 5 | 54 | 1.7472 | -0.1538 | -1.9010 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -8.4670 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 20 | 60 | 5575 | 1.5157 | 0.1460 | -1.3697 | adverse_preentry_move_benefit | 0.6479 | 1.0000 | 1681.7838 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 20 | 60 | 5575 | 1.5157 | 0.1460 | -1.3697 | adverse_preentry_move_benefit | 0.6479 | 1.0000 | 1681.7838 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 10 | 60 | 5575 | 1.2836 | 0.1280 | -1.1557 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1680.0865 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 10 | 60 | 5575 | 1.2836 | 0.1280 | -1.1557 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1680.0865 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 10 | 20 | 5575 | 1.2836 | 0.1280 | -1.1557 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1680.0865 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 10 | 20 | 5575 | 1.2836 | 0.1280 | -1.1557 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1680.0865 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 5 | 60 | 5575 | 0.9112 | 0.1132 | -0.7980 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1301.2023 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 5 | 60 | 5575 | 0.9112 | 0.1132 | -0.7980 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1301.2023 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 5 | 20 | 5575 | 0.9112 | 0.1132 | -0.7980 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1301.2023 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 5 | 20 | 5575 | 0.9112 | 0.1132 | -0.7980 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 1301.2023 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 20 | 38 | 0.8624 | 0.0172 | -0.8452 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -11.8736 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 5 | 38 | 0.8624 | 0.0172 | -0.8452 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -11.8736 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 20 | 38 | 0.8611 | -0.0067 | -0.8678 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -12.5312 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 5 | 38 | 0.8611 | -0.0067 | -0.8678 | adverse_preentry_move_benefit | 0.0000 | 0.6667 | -12.5312 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 5 | 38 | 0.6655 | -0.0254 | -0.6909 | adverse_preentry_move_benefit | 0.0000 | 0.3333 | -5.2990 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_continuation_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 20 | 38 | 0.6655 | -0.0254 | -0.6909 | adverse_preentry_move_benefit | 0.0000 | 0.3333 | -5.2990 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 60 | 5575 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 810.9501 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 60 | 5575 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 810.9501 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 20 | 5575 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 810.9501 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 20 | 5575 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 810.9501 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 5 | 5575 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 810.9501 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 3 | 5 | 5575 | 0.6384 | 0.1053 | -0.5331 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 810.9501 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 60 | 5575 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 556.3419 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 60 | 5575 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 556.3419 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 20 | 5575 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 556.3419 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 20 | 5575 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 556.3419 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 5 | 5575 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 556.3419 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 2 | 5 | 5575 | 0.5078 | 0.1027 | -0.4051 | adverse_preentry_move_benefit | 0.0000 | 1.0000 | 556.3419 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 60 | 5575 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 0.0000 | 1.0000 | 349.3079 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 60 | 5575 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 0.0000 | 1.0000 | 349.3079 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 20 | 5575 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 0.0000 | 1.0000 | 349.3079 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 20 | 5575 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 0.0000 | 1.0000 | 349.3079 |
| all_dedup | all_dedup | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 5 | 5575 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 0.0000 | 1.0000 | 349.3079 |
| source_specific | structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test |  | skip_unexecutable_candidate | skip_candidate | 1 | 5 | 5575 | 0.3282 | 0.0794 | -0.2488 | wait_better_other | 0.0000 | 1.0000 | 349.3079 |
| all_dedup | all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | skip_unexecutable_candidate | skip_candidate | 20 | 60 | 747 | 0.1375 | 0.6649 | 0.5275 | indifferent | 0.0000 | 0.6667 | -122.6101 |
| all_dedup | all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | skip_unexecutable_candidate | skip_candidate | 2 | 5 | 747 | 0.1018 | 0.2576 | 0.1558 | indifferent | 0.0000 | 0.3333 | -78.7803 |
| all_dedup | all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | skip_unexecutable_candidate | skip_candidate | 2 | 20 | 747 | 0.1018 | 0.2576 | 0.1558 | indifferent | 0.0000 | 0.3333 | -78.7803 |
| all_dedup | all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | skip_unexecutable_candidate | skip_candidate | 2 | 60 | 747 | 0.1018 | 0.2576 | 0.1558 | indifferent | 0.0000 | 0.3333 | -78.7803 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_vacuum_recent_breakout |  | skip_unexecutable_candidate | skip_candidate | 1 | 5 | 52 | 0.0668 | 0.0820 | 0.0152 | indifferent | 0.0000 | 0.6667 | -9.5670 |
| all_dedup | all_dedup | S3_liquidity_vacuum_release | S3_vacuum_recent_breakout |  | skip_unexecutable_candidate | skip_candidate | 1 | 20 | 52 | 0.0668 | 0.0820 | 0.0152 | indifferent | 0.0000 | 0.6667 | -9.5670 |
| all_dedup | all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | skip_unexecutable_candidate | skip_candidate | 10 | 20 | 747 | 0.0637 | 0.5218 | 0.4581 | indifferent | 0.0000 | 0.3333 | -95.2931 |
| all_dedup | all_dedup | S7_volatility_decay_risk | S7_spread_shock_breakout |  | skip_unexecutable_candidate | skip_candidate | 10 | 60 | 747 | 0.0637 | 0.5218 | 0.4581 | indifferent | 0.0000 | 0.3333 | -95.2931 |

## Runtime Feature Buckets

| source | family_id | variant_id | factor | factor_bin | wait_sec | horizon_sec | n | weighted_mean_wait_gain_bps | mean_entry_cross_repair_bps | mean_signed_mid_move_to_wait_bps | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth_quote_min | q4 | 20 | 60 | 1115 | 2.4660 | 0.2852 | -2.1809 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q2 | 20 | 60 | 1115 | 2.2648 | 0.0722 | -2.1926 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q2 | 20 | 60 | 1115 | 2.0236 | 0.0984 | -1.9252 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth_quote_min | q4 | 10 | 20 | 1115 | 1.9800 | 0.2697 | -1.7103 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth_quote_min | q4 | 10 | 60 | 1115 | 1.9800 | 0.2697 | -1.7103 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q1 | 20 | 60 | 1115 | 1.9548 | 0.1434 | -1.8113 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q4 | 20 | 60 | 1115 | 1.9542 | 0.4393 | -1.5149 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q4 | 20 | 60 | 1115 | 1.9542 | 0.4393 | -1.5149 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q2 | 10 | 20 | 1115 | 1.7880 | 0.0815 | -1.7065 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q2 | 10 | 60 | 1115 | 1.7880 | 0.0815 | -1.7065 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q2 | 20 | 60 | 1115 | 1.7698 | 0.1477 | -1.6220 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q3 | 20 | 60 | 1115 | 1.7366 | 0.1599 | -1.5767 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q1 | 10 | 20 | 1115 | 1.7195 | 0.1292 | -1.5903 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q1 | 10 | 60 | 1115 | 1.7195 | 0.1292 | -1.5903 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q4 | 20 | 60 | 1115 | 1.6983 | 0.1574 | -1.5409 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q5 | 20 | 60 | 1115 | 1.6665 | 0.7237 | -0.9428 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q5 | 20 | 60 | 1115 | 1.6665 | 0.7237 | -0.9428 | 1.0000 |
| structure_candidate | S7_volatility_decay_risk | S7_spread_shock_breakout | trade_flow_imbalance | q3 | 20 | 60 | 146 | 1.6343 | 0.8954 | -0.7389 | 0.6667 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q4 | 10 | 60 | 1115 | 1.6281 | 0.3644 | -1.2637 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q4 | 10 | 60 | 1115 | 1.6281 | 0.3644 | -1.2637 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q4 | 10 | 20 | 1115 | 1.6281 | 0.3644 | -1.2637 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q4 | 10 | 20 | 1115 | 1.6281 | 0.3644 | -1.2637 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q2 | 10 | 60 | 1115 | 1.6093 | 0.0970 | -1.5123 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q2 | 10 | 20 | 1115 | 1.6093 | 0.0970 | -1.5123 | 1.0000 |
| structure_candidate | S7_volatility_decay_risk | S7_past_event_continuation | trade_flow_imbalance | q3 | 20 | 60 | 295 | 1.6028 | 0.1843 | -1.4186 | 0.6667 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q3 | 20 | 60 | 1115 | 1.5342 | 0.1346 | -1.3996 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q5 | 20 | 60 | 1115 | 1.5221 | 0.1350 | -1.3871 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | cell | missing | 20 | 60 | 5575 | 1.5157 | 0.1460 | -1.3697 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | capacity_source | missing | 20 | 60 | 5575 | 1.5157 | 0.1460 | -1.3697 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth_quote_min | q4 | 5 | 60 | 1115 | 1.5120 | 0.2374 | -1.2746 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth_quote_min | q4 | 5 | 20 | 1115 | 1.5120 | 0.2374 | -1.2746 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q3 | 20 | 60 | 1115 | 1.5115 | 0.1337 | -1.3778 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q3 | 20 | 60 | 1115 | 1.5031 | -0.0538 | -1.5569 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q5 | 20 | 60 | 1115 | 1.4897 | 0.1548 | -1.3348 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q4 | 20 | 60 | 1115 | 1.4814 | 0.1462 | -1.3352 | 1.0000 |
| structure_candidate | S7_volatility_decay_risk | S7_spread_shock_breakout | frames_since_mid_change | q1 | 20 | 60 | 257 | 1.4757 | 0.8614 | -0.6144 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth_quote_min | q3 | 20 | 60 | 1115 | 1.4674 | 0.1010 | -1.3665 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q2 | 10 | 20 | 1115 | 1.4528 | 0.1410 | -1.3117 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | trade_flow_imbalance | q2 | 10 | 60 | 1115 | 1.4528 | 0.1410 | -1.3117 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q3 | 10 | 20 | 1115 | 1.4422 | -0.0217 | -1.4639 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q3 | 10 | 60 | 1115 | 1.4422 | -0.0217 | -1.4639 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q4 | 20 | 60 | 1115 | 1.4418 | 0.3290 | -1.1128 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q4 | 10 | 60 | 1115 | 1.4398 | 0.1535 | -1.2863 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q4 | 10 | 20 | 1115 | 1.4398 | 0.1535 | -1.2863 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q3 | 10 | 20 | 1115 | 1.4213 | 0.1447 | -1.2765 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q3 | 10 | 60 | 1115 | 1.4213 | 0.1447 | -1.2765 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q5 | 10 | 20 | 1115 | 1.4185 | 0.5935 | -0.8250 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q5 | 10 | 20 | 1115 | 1.4185 | 0.5935 | -0.8250 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q5 | 10 | 60 | 1115 | 1.4185 | 0.5935 | -0.8250 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q5 | 10 | 60 | 1115 | 1.4185 | 0.5935 | -0.8250 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q3 | 10 | 20 | 1115 | 1.4087 | 0.1456 | -1.2631 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q3 | 10 | 60 | 1115 | 1.4087 | 0.1456 | -1.2631 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q4 | 10 | 60 | 1115 | 1.3993 | 0.3028 | -1.0965 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | top_depth | q4 | 10 | 20 | 1115 | 1.3993 | 0.3028 | -1.0965 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q3 | 10 | 60 | 1115 | 1.3785 | 0.1257 | -1.2528 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | frames_since_mid_change | q3 | 10 | 20 | 1115 | 1.3785 | 0.1257 | -1.2528 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q4 | 5 | 60 | 1115 | 1.3477 | 0.3057 | -1.0420 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q4 | 5 | 60 | 1115 | 1.3477 | 0.3057 | -1.0420 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_spread_bps | q4 | 5 | 20 | 1115 | 1.3477 | 0.3057 | -1.0420 | 1.0000 |
| structure_candidate | S4_absorption_failed_continuation | S4_absorption_reversal_test | entry_cross_bps | q4 | 5 | 20 | 1115 | 1.3477 | 0.3057 | -1.0420 | 1.0000 |

## Interpretation

- Rows where wait gain is positive because `entry_cross_repair_bps` dominates are admission candidates: wait for quote/spread repair before crossing.
- Rows where wait gain is positive because `signed_mid_move_to_wait_bps` is negative are not spread repair. They say the market moved against the intended side before the delayed entry, so promotion would require a separate runtime-safe adverse-move predictor.
- Rows where wait gain is negative because `signed_mid_move_to_wait_bps` dominates are cross-now candidates: the structure releases before the delayed entry.
- Rows with positive mid/release intuition but non-positive `now_exec_bps` and `wait_exec_bps` are spread-cost mirages, not executable taker alpha.
- Any candidate from this report still requires strict replay/profile-equivalence before promotion.

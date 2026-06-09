# CCUSDT TFI Mechanism Attribution Diagnostic

Status: `ccusdt_tfi_mechanism_attribution_v0_1`.

Boundary: research-only. Inputs are `decision_frame_v1`, `quote_frame_v1`, `trade_event_v1`, and `l2_level_update_v1`; labels are diagnostic-only and must not enter Runner/Bot runtime.

This is an attribution audit, not a strategy mutation. It explains the current legacy TFI entries with L2 mechanism evidence and only emits possible veto hypotheses for later isolated tests.

## Setup

- symbol: `CCUSDT`
- dates: `2026-05-16..2026-05-18`
- baseline entries: `764`
- actual attributed entries: `504`
- L2 event-state rows: `378908`
- mechanism-frame rows: `378905`
- output: `systems\ccusdt_replay_exchange\runs\tfi_mechanism_attribution\ccusdt_2026-05-16_2026-05-18_v0_1`

## How To Read This

- `mechanism_label` is the dominant explanation for an existing TFI entry, not a new entry rule.
- `top_of_book_executable_60s_bps` uses taker entry/exit quotes; `mid_return_60s_bps` is shown only to expose spread-cost mirages.
- `net_weighted_bps_removed_if_vetoed` is the baseline contribution of rows matching that candidate. If it is positive, vetoing those rows would have removed profit in this window.
- The L2 event state is built by processing every L2 update but storing one compressed row per `local_ts_us` batch, with add/cancel/trade-consumed quantities summed inside the batch.

## Mechanism Summary

| mechanism_label | n | mean_exec60_bps | mean_mid60_bps | hit_rate_exec60 | net_weighted_bps |
| --- | --- | --- | --- | --- | --- |
| execution_cost_failure | 236 | 0.8456 | 3.0594 | 0.4661 | 193.9724 |
| flow_continuation | 103 | 3.1125 | 5.2202 | 0.5728 | 180.8789 |
| withdrawal_trap_like | 100 | 1.2808 | 2.8572 | 0.5100 | 151.9536 |
| unclassified | 65 | 0.1115 | 2.0678 | 0.4000 | 18.4344 |

## Win/Loss Breakdown

| outcome_bucket | mechanism_label | n | share | mean_exec60_bps | net_weighted_bps |
| --- | --- | --- | --- | --- | --- |
| loss | execution_cost_failure | 126 | 0.2500 | -5.9959 | -385.8256 |
| loss | flow_continuation | 44 | 0.0873 | -5.2562 | -124.9121 |
| loss | unclassified | 39 | 0.0774 | -7.5435 | -137.9937 |
| loss | withdrawal_trap_like | 49 | 0.0972 | -8.7986 | -221.5333 |
| win | execution_cost_failure | 110 | 0.2183 | 8.6823 | 579.7980 |
| win | flow_continuation | 59 | 0.1171 | 9.3535 | 305.7910 |
| win | unclassified | 26 | 0.0516 | 11.5940 | 156.4281 |
| win | withdrawal_trap_like | 51 | 0.1012 | 10.9649 | 373.4869 |

## Candidate Veto Rules

| rule_id | n | mean_exec60_bps | hit_rate_exec60 | net_weighted_bps_removed_if_vetoed | estimated_net_delta_if_vetoed | status |
| --- | --- | --- | --- | --- | --- | --- |
| legacy_tfi_short_trap_long_veto | 113 | 1.8154 | 0.5221 | 246.1416 | -246.1416 | candidate_veto_not_supported_in_this_window |
| legacy_tfi_short_absorption_long_veto | 113 | 1.8154 | 0.5221 | 246.1416 | -246.1416 | candidate_veto_not_supported_in_this_window |
| legacy_tfi_long_trap_short_veto | 49 | 1.8051 | 0.5714 | 48.8520 | -48.8520 | candidate_veto_not_supported_in_this_window |
| legacy_tfi_long_absorption_short_veto | 49 | 1.8051 | 0.5714 | 48.8520 | -48.8520 | candidate_veto_not_supported_in_this_window |
| execution_quality_bad_veto | 236 | 0.8456 | 0.4661 | 193.9724 | -193.9724 | candidate_veto_not_supported_in_this_window |

## Interpretation

- This diagnostic attributes the old TFI entries; it does not create new strategy entries.
- Promising veto rules in this run: `0`. A zero value means the first pass did not find a mechanism bucket that can be safely removed on this evidence alone.
- Veto rows are candidates only. They need isolated follow-up tests before any runtime policy change.
- In this window, several trap/absorption/execution-quality buckets still have positive aggregate contribution, so they are better treated as attribution buckets than immediate filters.
- `R5` remains a risk/sizing memory; it is not used here to explain the current L2 mechanism.

## Next Isolated Tests

1. Test exactly one veto at a time against the same baseline entry set.
2. Require improvement in executable return, not only mid return.
3. Reject any veto that removes positive weighted contribution on two or more days.
4. Only after a stable veto exists should it be considered for a fast strategy profile; independent L2 entry is a later problem.

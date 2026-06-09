# CCUSDT maker-first exit L2 queue diagnostic

This fast-line diagnostic streams canonical `l2_level_update_v1` for selected maker-first exit events and estimates displayed queue depletion at the posted touch.

It is not a strict private-order fill simulator. Same-price displayed-size decreases can include cancellations, so this is a queue-pressure diagnostic between the trade-only proxy and the future strict Runner maker lifecycle.

## Scope

- Events: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_first_exit_policy_q70_idle01_g1_warmup_strict_20260516_18_20260522\maker_first_exit_events.parquet`
- Attempts: `110`
- L2 rows read: `138797819`
- L2 matched depletion rows: `137`
- Output directory: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_l2_queue_q70_idle01_g1_warmup_strict_20260516_18_20260522`

## Summary

| exit_profile_source | date | gate_name | maker_attempts | exposure | trade_queue_fill_rate | l2_queue_fill_rate | trade_queue_weighted_delta | l2_queue_weighted_delta | l2_saved_spread | l2_missed_decay | l2_adverse_selection |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | spread_q90 | 12 | 6.8750 | 0.0000 | 0.0000 | 0.8406 | 0.8406 | 0.0000 | -0.8406 | 0.0000 |
| fixed30_livecoherent | 2026-05-17 | spread_q90 | 17 | 9.8750 | 0.1765 | 0.0000 | -0.1180 | 1.9293 | 0.0000 | 5.7250 | 0.0000 |
| fixed30_livecoherent | 2026-05-18 | spread_q90 | 22 | 11.1250 | 0.0455 | 0.0000 | 8.8813 | 9.3735 | 0.0000 | -7.1593 | 0.0000 |
| fixed45_livecoherent | 2026-05-16 | spread_q90 | 17 | 8.5000 | 0.0588 | 0.0000 | -1.2315 | -0.4803 | 0.0000 | 2.7334 | 0.0000 |
| fixed45_livecoherent | 2026-05-17 | spread_q80_same_flow_q70 | 42 | 27.5000 | 0.1429 | 0.0714 | 14.5433 | 33.4538 | 1.2178 | 2.4315 | 1.2174 |

## Readout

If L2 depletion materially disagrees with the trade-queue proxy, maker-first exit must stay diagnostic-only until strict Runner maker orders can model post-only ack, cancel, fallback, and private fill causality.

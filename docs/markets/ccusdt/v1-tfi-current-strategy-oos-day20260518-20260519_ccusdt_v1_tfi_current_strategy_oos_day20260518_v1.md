# CCUSDT V1 TFI Current Strategy OOS

Status: `20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1`.

Guardrail: `research_only_locked_strategy_oos_no_execution_recommendation`.

OOS date: `2026-05-18`.

This applies locked strategy variants to the new OOS day. It does not
optimize gamma or thresholds on 2026-05-18.

## Entry Universe

| cell | entries | base_exposure | fixed60_gross | manager_gross |
| --- | --- | --- | --- | --- |
| 00_none | 112 | 59.0000 | 194.7861 | 204.7793 |
| 01_frames_only | 10 | 17.5000 | 32.2478 | 32.2478 |
| 10_r5_only | 168 | 88.5000 | 342.3972 | 344.1636 |
| 11_r5_frames | 14 | 26.0000 | 66.0415 | 68.0384 |

Watcher triggered rows: `0`.

## Cleaner q70 Result

| pressure_bps | capacity_policy | desired_total | actual_total | exact_simple_bp_units | approx_account_simple_return | actual_vs_global_gain | desired_max_concurrent | actual_max_concurrent | clipped_legs | skipped_legs | leg_worst |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | global_downscale | 415.5299 | 332.4239 | 333.0758 | 0.0338 | 0.0000 | 3.7500 | 3.0000 | 294 | 0 | -16.9582 |
| 0.0000 | online_fifo_clip | 415.5299 | 415.8276 | 416.6424 | 0.0425 | 83.4037 | 3.7500 | 3.0000 | 3 | 1 | -21.1977 |
| 0.0000 | priority_arrival_clip | 415.5299 | 415.8276 | 416.6424 | 0.0425 | 83.4037 | 3.7500 | 3.0000 | 3 | 1 | -21.1977 |
| 0.0000 | raw_no_cap | 415.5299 | 415.5299 | 416.3447 | 0.0424 | 83.1060 | 3.7500 | 3.7500 | 0 | 0 | -21.1977 |
| 1.0000 | global_downscale | 255.9049 | 204.7239 | 205.3488 | 0.0207 | 0.0000 | 3.7500 | 3.0000 | 294 | 0 | -18.4582 |
| 1.0000 | online_fifo_clip | 255.9049 | 257.7026 | 258.4837 | 0.0261 | 52.9787 | 3.7500 | 3.0000 | 3 | 1 | -23.0727 |
| 1.0000 | priority_arrival_clip | 255.9049 | 257.7026 | 258.4837 | 0.0261 | 52.9787 | 3.7500 | 3.0000 | 3 | 1 | -23.0727 |
| 1.0000 | raw_no_cap | 255.9049 | 255.9049 | 256.6861 | 0.0259 | 51.1810 | 3.7500 | 3.7500 | 0 | 0 | -23.0727 |
| 2.0000 | global_downscale | 96.2799 | 77.0239 | 77.6347 | 0.0077 | 0.0000 | 3.7500 | 3.0000 | 294 | 0 | -19.9582 |
| 2.0000 | online_fifo_clip | 96.2799 | 99.5776 | 100.3407 | 0.0100 | 22.5537 | 3.7500 | 3.0000 | 3 | 1 | -24.9477 |
| 2.0000 | priority_arrival_clip | 96.2799 | 99.5776 | 100.3407 | 0.0100 | 22.5537 | 3.7500 | 3.0000 | 3 | 1 | -24.9477 |
| 2.0000 | raw_no_cap | 96.2799 | 96.2799 | 97.0434 | 0.0097 | 19.2560 | 3.7500 | 3.7500 | 0 | 0 | -24.9477 |

## C0 Variant Comparison

| variant | capacity_policy | desired_total | actual_total | exact_simple_bp_units | approx_account_simple_return | actual_vs_global_gain | desired_max_concurrent | actual_max_concurrent | clipped_legs | skipped_legs | leg_worst |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| anchor_q70_old_shape | global_downscale | 833.4642 | 125.0196 | 125.2174 | 0.0126 | 0.0000 | 20.0000 | 3.0000 | 304 | 0 | -16.9582 |
| anchor_q70_old_shape | online_fifo_clip | 833.4642 | 503.2391 | 504.1105 | 0.0516 | 378.2195 | 20.0000 | 3.0000 | 16 | 5 | -33.9163 |
| clean_q70_low_concurrency | global_downscale | 415.5299 | 332.4239 | 333.0758 | 0.0338 | 0.0000 | 3.7500 | 3.0000 | 294 | 0 | -16.9582 |
| clean_q70_low_concurrency | online_fifo_clip | 415.5299 | 415.8276 | 416.6424 | 0.0425 | 83.4037 | 3.7500 | 3.0000 | 3 | 1 | -21.1977 |
| high_gamma_q70_capacity | global_downscale | 1340.0012 | 160.8001 | 161.0661 | 0.0162 | 0.0000 | 25.0000 | 3.0000 | 304 | 0 | -16.9582 |
| high_gamma_q70_capacity | online_fifo_clip | 1340.0012 | 791.8087 | 793.3304 | 0.0824 | 631.0086 | 25.0000 | 3.0000 | 23 | 7 | -33.9163 |

## Interpretation

- `actual_total` is weighted log-bp units, i.e. sum of exposure times log-bps.
- `exact_simple_bp_units` converts each leg by `exp(unit/10000)-1` before weighting.
- `approx_account_simple_return` treats the total log-bp units as if it were an account log return; it is an intuition aid, not a margin-account simulator.
- `online_fifo_clip` is the first implementable 3x capacity model; `global_downscale` is the conservative lower bound.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_current_oos_summary_20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_current_oos_unit_entries_20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_current_oos_manager_events_20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_current_oos_watcher_events_20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.csv`

# CCUSDT Microstructure Factor Diagnostic v0.1

Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.

## Scope

- symbol: `CCUSDT`
- from_date: `2026-05-16`
- to_date: `2026-05-18`
- source: `both`
- horizon_sec: `60`
- release_sec: `10`
- out_dir: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\microstructure_factor_diagnostic\ccusdt_2026-05-16_2026-05-18_both_v0_1_scoped`

This report is a diagnostic table generator output. Future path labels are used only as labels; they must not enter Runner or Bot runtime.

Aggregation semantics:

- `aggregation_scope=pooled` means one quantile cut and one summary over the full requested date window.
- `aggregation_scope=daily` means the same statistic was computed on a single day. Do not compare pooled and daily rows as if they were the same estimator.

## Status Counts

| scope | source | status | rows |
|---|---|---|---:|
| daily | decision_frame_v1 | control_only_no_direction | 24 |
| daily | decision_frame_v1 | decay_lower_for_top_bucket_not_promoted | 42 |
| daily | decision_frame_v1 | decay_risk_higher_for_top_bucket | 39 |
| daily | decision_frame_v1 | diagnostic_positive_not_promoted | 101 |
| daily | decision_frame_v1 | spread_cost_mirage_or_negative_executable | 81 |
| daily | decision_frame_v1 | weak_or_negative | 61 |
| daily | fixed_event_panel | control_only_no_direction | 30 |
| daily | fixed_event_panel | decay_lower_for_top_bucket_not_promoted | 72 |
| daily | fixed_event_panel | decay_risk_higher_for_top_bucket | 135 |
| daily | fixed_event_panel | diagnostic_positive_not_promoted | 331 |
| daily | fixed_event_panel | insufficient_data | 360 |
| daily | fixed_event_panel | spread_cost_mirage_or_negative_executable | 207 |
| daily | fixed_event_panel | weak_or_negative | 83 |
| pooled | decision_frame_v1 | control_only_no_direction | 8 |
| pooled | decision_frame_v1 | decay_lower_for_top_bucket_not_promoted | 14 |
| pooled | decision_frame_v1 | decay_risk_higher_for_top_bucket | 13 |
| pooled | decision_frame_v1 | diagnostic_positive_not_promoted | 32 |
| pooled | decision_frame_v1 | spread_cost_mirage_or_negative_executable | 27 |
| pooled | decision_frame_v1 | weak_or_negative | 22 |
| pooled | fixed_event_panel | control_only_no_direction | 10 |
| pooled | fixed_event_panel | decay_lower_for_top_bucket_not_promoted | 25 |
| pooled | fixed_event_panel | decay_risk_higher_for_top_bucket | 44 |
| pooled | fixed_event_panel | diagnostic_positive_not_promoted | 114 |
| pooled | fixed_event_panel | insufficient_data | 120 |
| pooled | fixed_event_panel | spread_cost_mirage_or_negative_executable | 69 |
| pooled | fixed_event_panel | weak_or_negative | 24 |

## Top Pooled Diagnostic Rows

| window | source | factor | label | n | mean | median | top-bottom | cvar05 | daily sign | status |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 2026-05-16..2026-05-18 | fixed_event_panel | OFI_L1__r10_log_ratio | top_of_book_executable_60s | 375627 | -0.6855 | -0.6687 | 1.2442 | -30.2003 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | OFI_L1__r10_z | top_of_book_executable_60s | 375627 | -0.7085 | -1.2900 | 1.9204 | -32.5105 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | OFI_L1__r10_delta | top_of_book_executable_60s | 375627 | -0.7113 | -1.2958 | 1.8926 | -33.1238 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__raw | top_of_book_executable_60s | 375633 | -0.7125 | -1.2958 | 1.8959 | -33.1238 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | OFI_L1__r10_energy_delta_side | top_of_book_executable_60s | 375627 | -0.7678 | -1.2993 | 1.8242 | -34.2005 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r5_delta | top_of_book_executable_60s | 376987 | -0.8075 | -1.2979 | 1.7410 | -33.1370 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r5_z | top_of_book_executable_60s | 376987 | -0.8243 | -1.2976 | 1.7071 | -33.1778 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r10_log_ratio | top_of_book_executable_60s | 377812 | -0.8389 | -1.2958 | 1.0665 | -32.3454 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r5_energy_delta_side | top_of_book_executable_60s | 376987 | -0.8413 | -1.2984 | 1.6903 | -33.4387 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r5_log_ratio | top_of_book_executable_60s | 376987 | -0.8475 | -1.2975 | 1.1923 | -32.9725 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r10_z | top_of_book_executable_60s | 377812 | -0.9069 | -1.3010 | 1.5594 | -33.0820 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r10_delta | top_of_book_executable_60s | 377812 | -0.9222 | -1.3017 | 1.5344 | -33.3001 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L25__r5_log_ratio | top_of_book_executable_60s | 367275 | -0.9641 | -1.3041 | 1.1397 | -31.6404 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | OFI_L1__r5_energy_delta_side | top_of_book_executable_60s | 370939 | -0.9882 | -1.2975 | 1.8455 | -35.0674 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | OFI_L1__r5_delta | top_of_book_executable_60s | 370939 | -0.9918 | -1.2956 | 1.8145 | -34.4433 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | MLOFI_L1__r10_energy_delta_side | top_of_book_executable_60s | 377812 | -0.9925 | -1.3032 | 1.4648 | -33.9606 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | OFI_L1__r5_z | top_of_book_executable_60s | 370939 | -0.9927 | -1.2900 | 1.8177 | -33.9958 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | queue_imbalance_5__r10_log_ratio | top_of_book_executable_60s | 378820 | -0.9953 | -1.2950 | 0.9472 | -35.4145 | 1.0000 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | queue_imbalance_5__r10_z | top_of_book_executable_60s | 378820 | -0.9953 | -1.2950 | 0.8790 | -35.4145 | 0.6667 | spread_cost_mirage_or_negative_executable |
| 2026-05-16..2026-05-18 | fixed_event_panel | queue_imbalance_5__r10_delta | top_of_book_executable_60s | 378820 | -0.9953 | -1.2950 | 0.7524 | -35.4145 | 0.6667 | spread_cost_mirage_or_negative_executable |

## Data Boundary

- Full trade-flow diagnostics require `trade_event_v1`; current canonical CSV coverage is known through `2026-05-18`.
- Quote-only recent windows must not be mixed with full TFI/OFI/MLOFI evidence.
- `fixed_event_panel` rows come from derived research panels and remain diagnostics, not runtime inputs.

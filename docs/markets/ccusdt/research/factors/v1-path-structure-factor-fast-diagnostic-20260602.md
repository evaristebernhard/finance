# CCUSDT Path-Structure Factor Fast Diagnostic v0.1

Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.

## Scope

- symbol: `CCUSDT`
- dates: `2026-05-16..2026-05-18`
- source: `both`
- windows_sec: `[30, 60, 120]`
- mid_horizons_sec: `[20, 60]`
- release_sec: `10`
- executable_horizon_sec: `60`
- factor_count: `30`
- event_panel_rows: `757810`
- max_label_validity_drop_count: `237`
- out_dir: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\path_structure_factor_fast_diagnostic\ccusdt_2026-05-16_2026-05-18_both_v0_1`

This diagnostic tests medium-horizon path operators. `fixed_event_panel` rows are research evidence only; they do not prove Bot runtime reconstructability.

## Status Counts

| aggregation_scope | source_layer | status | rows |
| --- | --- | --- | --- |
| daily | decision_frame_v1 | cost_gate_only | 126 |
| daily | decision_frame_v1 | decay_risk_only | 112 |
| daily | decision_frame_v1 | diagnostic_positive | 432 |
| daily | decision_frame_v1 | spread_cost_mirage | 185 |
| daily | decision_frame_v1 | weak_or_negative | 414 |
| daily | fixed_event_panel | cost_gate_only | 126 |
| daily | fixed_event_panel | decay_risk_only | 136 |
| daily | fixed_event_panel | research_panel_only | 388 |
| daily | fixed_event_panel | spread_cost_mirage | 184 |
| daily | fixed_event_panel | weak_or_negative | 435 |
| pooled | decision_frame_v1 | cost_gate_only | 42 |
| pooled | decision_frame_v1 | decay_risk_only | 41 |
| pooled | decision_frame_v1 | diagnostic_positive | 135 |
| pooled | decision_frame_v1 | spread_cost_mirage | 63 |
| pooled | decision_frame_v1 | weak_or_negative | 142 |
| pooled | fixed_event_panel | cost_gate_only | 42 |
| pooled | fixed_event_panel | decay_risk_only | 45 |
| pooled | fixed_event_panel | research_panel_only | 108 |
| pooled | fixed_event_panel | spread_cost_mirage | 63 |
| pooled | fixed_event_panel | weak_or_negative | 165 |

## Executable Layer Readout

| source_layer | status | rows |
| --- | --- | --- |
| decision_frame_v1 | spread_cost_mirage | 63 |
| fixed_event_panel | spread_cost_mirage | 63 |

No pooled top-of-book row has both positive top-bucket mean and positive top-bottom lift. In this pass, the largest executable lifts are mostly `spread_cost_mirage`: the bucket loses less, but does not yet produce positive taker economics.

## Top Executable Diagnostic Rows

| source_layer | factor_id | window_sec | label | n | mean | top_bottom | spearman | daily_sign_rate | runtime_status | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| decision_frame_v1 | pressure_exhaustion_gap | 30 | top_of_book_executable_60s | 214794 | -0.8559 | 1.4453 | 0.0494 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | pressure_to_price_efficiency | 120 | top_of_book_executable_60s | 321141 | -1.5949 | 1.4138 | 0.0204 | 1.0000 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | pressure_exhaustion_gap | 60 | top_of_book_executable_60s | 278735 | -0.9630 | 1.3961 | 0.0428 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | price_path_acceleration | 30 | top_of_book_executable_60s | 180489 | -1.4554 | 1.3794 | 0.0445 | 1.0000 | decision_frame_safe | spread_cost_mirage |
| fixed_event_panel | price_path_acceleration | 30 | top_of_book_executable_60s | 180487 | -1.4554 | 1.3707 | 0.0443 | 1.0000 | research_panel_only | spread_cost_mirage |
| decision_frame_v1 | pressure_price_alignment_ratio | 120 | top_of_book_executable_60s | 335936 | -2.2329 | 1.2035 | 0.0125 | 0.3333 | decision_frame_safe | spread_cost_mirage |
| fixed_event_panel | pressure_to_price_efficiency | 120 | top_of_book_executable_60s | 346443 | -1.7713 | 1.1907 | 0.0190 | 0.6667 | research_panel_only | spread_cost_mirage |
| decision_frame_v1 | pressure_exhaustion_gap | 120 | top_of_book_executable_60s | 329671 | -0.7663 | 1.1778 | 0.0343 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | vacuum_release_energy | 30 | top_of_book_executable_60s | 260940 | -0.9252 | 1.1570 | 0.0544 | 1.0000 | decision_frame_safe_top_of_book_proxy | spread_cost_mirage |
| fixed_event_panel | signed_price_path_ratio | 30 | top_of_book_executable_60s | 252724 | -1.0600 | 1.1318 | 0.0315 | 1.0000 | research_panel_only | spread_cost_mirage |
| fixed_event_panel | pressure_exhaustion_gap | 120 | top_of_book_executable_60s | 378661 | -1.2564 | 1.0858 | 0.0333 | 0.6667 | research_panel_only | spread_cost_mirage |
| fixed_event_panel | pressure_price_alignment_ratio | 120 | top_of_book_executable_60s | 358321 | -2.1998 | 1.0810 | 0.0164 | 0.6667 | research_panel_only | spread_cost_mirage |
| decision_frame_v1 | signed_price_path_ratio | 30 | top_of_book_executable_60s | 252704 | -1.0600 | 1.0677 | 0.0295 | 1.0000 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | absorption_failure_structure | 120 | top_of_book_executable_60s | 269632 | -1.4040 | 1.0355 | 0.0380 | 1.0000 | decision_frame_safe | spread_cost_mirage |
| fixed_event_panel | executable_structure_score | 120 | top_of_book_executable_60s | 346443 | -1.1605 | 0.9853 | 0.0369 | 0.6667 | research_panel_only | spread_cost_mirage |
| fixed_event_panel | pressure_exhaustion_gap | 60 | top_of_book_executable_60s | 378661 | -1.1081 | 0.9514 | 0.0384 | 0.6667 | research_panel_only | spread_cost_mirage |
| fixed_event_panel | opposite_depth_giveway_ratio | 120 | top_of_book_executable_60s | 378598 | -1.3740 | 0.9439 | 0.0296 | 0.6667 | research_panel_only | spread_cost_mirage |
| fixed_event_panel | executable_structure_score | 60 | top_of_book_executable_60s | 308280 | -1.4562 | 0.9343 | 0.0369 | 1.0000 | research_panel_only | spread_cost_mirage |
| decision_frame_v1 | pressure_price_alignment_ratio | 60 | top_of_book_executable_60s | 281344 | -1.9485 | 0.8913 | 0.0064 | 0.3333 | decision_frame_safe | spread_cost_mirage |
| fixed_event_panel | executable_structure_score | 30 | top_of_book_executable_60s | 249542 | -1.5320 | 0.8364 | 0.0278 | 1.0000 | research_panel_only | spread_cost_mirage |
| fixed_event_panel | pressure_exhaustion_gap | 30 | top_of_book_executable_60s | 378477 | -1.2010 | 0.7844 | 0.0433 | 0.6667 | research_panel_only | spread_cost_mirage |
| fixed_event_panel | signed_price_path_ratio | 120 | top_of_book_executable_60s | 350374 | -1.4861 | 0.7547 | 0.0084 | 0.6667 | research_panel_only | spread_cost_mirage |
| decision_frame_v1 | pressure_to_price_efficiency | 60 | top_of_book_executable_60s | 270220 | -1.6042 | 0.7533 | 0.0095 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| fixed_event_panel | signed_price_path_ratio | 60 | top_of_book_executable_60s | 311478 | -1.4858 | 0.7487 | 0.0292 | 0.6667 | research_panel_only | spread_cost_mirage |
| decision_frame_v1 | signed_price_path_ratio | 60 | top_of_book_executable_60s | 311471 | -1.4858 | 0.7443 | 0.0284 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | opposite_depth_giveway_ratio | 120 | top_of_book_executable_60s | 378629 | -1.5340 | 0.7405 | 0.0308 | 0.6667 | decision_frame_safe_top_of_book_proxy | spread_cost_mirage |
| decision_frame_v1 | signed_price_path_ratio | 120 | top_of_book_executable_60s | 350558 | -1.4855 | 0.7206 | 0.0071 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | price_path_acceleration | 60 | top_of_book_executable_60s | 249905 | -1.5425 | 0.7186 | 0.0346 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| fixed_event_panel | price_path_acceleration | 60 | top_of_book_executable_60s | 249884 | -1.5423 | 0.6991 | 0.0341 | 0.6667 | research_panel_only | spread_cost_mirage |
| decision_frame_v1 | executable_structure_score | 60 | top_of_book_executable_60s | 308392 | -1.7401 | 0.6069 | 0.0252 | 1.0000 | decision_frame_safe_top_of_book_proxy | spread_cost_mirage |
| decision_frame_v1 | vacuum_release_energy | 60 | top_of_book_executable_60s | 320784 | -1.5248 | 0.5551 | 0.0422 | 0.6667 | decision_frame_safe_top_of_book_proxy | spread_cost_mirage |
| decision_frame_v1 | absorption_failure_structure | 60 | top_of_book_executable_60s | 200599 | -2.0250 | 0.5528 | 0.0234 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | cost_repair_release_combo | 30 | top_of_book_executable_60s | 251802 | -2.0585 | 0.5362 | 0.0185 | 0.6667 | decision_frame_safe | spread_cost_mirage |
| decision_frame_v1 | vacuum_release_structure | 60 | top_of_book_executable_60s | 270183 | -1.7266 | 0.5298 | 0.0212 | 0.6667 | decision_frame_safe_top_of_book_proxy | spread_cost_mirage |
| fixed_event_panel | cost_repair_release_combo | 30 | top_of_book_executable_60s | 251740 | -2.0572 | 0.5097 | 0.0175 | 0.6667 | research_panel_only | spread_cost_mirage |

## Best Conditional Lifts

| source_layer | factor_id | window_sec | control_name | control_bucket | n | mean | top_bottom | runtime_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| decision_frame_v1 | pressure_price_alignment_ratio | 120 | tfi_bucket | q1 | 113419 | -2.0293 | 3.2016 | decision_frame_safe |
| decision_frame_v1 | price_path_acceleration | 30 | tfi_bucket | q1 | 63401 | -0.5919 | 3.1969 | decision_frame_safe |
| fixed_event_panel | price_path_acceleration | 30 | tfi_bucket | q1 | 63395 | -0.5919 | 3.1761 | research_panel_only |
| decision_frame_v1 | pressure_exhaustion_gap | 60 | tfi_bucket | q1 | 96600 | 0.3675 | 2.8249 | decision_frame_safe |
| decision_frame_v1 | pressure_exhaustion_gap | 120 | tfi_bucket | q1 | 111773 | 0.5645 | 2.6133 | decision_frame_safe |
| decision_frame_v1 | pressure_price_alignment_ratio | 120 | activity_bucket | q1 | 111050 | -1.9712 | 2.6045 | decision_frame_safe |
| fixed_event_panel | opposite_depth_giveway_ratio | 120 | tfi_bucket | q1 | 126296 | -0.2839 | 2.5848 | research_panel_only |
| decision_frame_v1 | pressure_exhaustion_gap | 30 | spread_bucket | q1 | 63836 | 1.2231 | 2.5768 | decision_frame_safe |
| decision_frame_v1 | pressure_exhaustion_gap | 60 | activity_bucket | q1 | 89965 | 0.2790 | 2.4379 | decision_frame_safe |
| fixed_event_panel | opposite_depth_giveway_ratio | 120 | activity_bucket | q1 | 126234 | -0.4411 | 2.4288 | research_panel_only |
| fixed_event_panel | pressure_exhaustion_gap | 120 | ofi_bucket | q2 | 126237 | -0.3071 | 2.4100 | research_panel_only |
| fixed_event_panel | pressure_price_alignment_ratio | 120 | tfi_bucket | q1 | 120804 | -2.2725 | 2.4034 | research_panel_only |
| decision_frame_v1 | price_path_acceleration | 30 | activity_bucket | q1 | 60459 | -1.1397 | 2.3999 | decision_frame_safe |
| fixed_event_panel | pressure_price_alignment_ratio | 120 | ofi_bucket | q2 | 117417 | -2.0057 | 2.3847 | research_panel_only |
| fixed_event_panel | executable_structure_score | 30 | tfi_bucket | q1 | 88708 | -0.3750 | 2.3612 | research_panel_only |
| fixed_event_panel | price_path_acceleration | 30 | activity_bucket | q1 | 60474 | -1.1397 | 2.3584 | research_panel_only |
| decision_frame_v1 | pressure_exhaustion_gap | 120 | activity_bucket | q1 | 109054 | 0.5314 | 2.2596 | decision_frame_safe |
| decision_frame_v1 | cost_allowed_trend_structure | 30 | activity_bucket | q2 | 72279 | -0.3170 | 2.2256 | decision_frame_safe |
| decision_frame_v1 | absorption_failure_structure | 120 | tfi_bucket | q1 | 91501 | -0.4530 | 2.2114 | decision_frame_safe |
| fixed_event_panel | executable_structure_score | 30 | activity_bucket | q1 | 79922 | -0.2063 | 2.1980 | research_panel_only |
| decision_frame_v1 | pressure_exhaustion_gap | 30 | spread_bucket | q3 | 75966 | -1.0854 | 2.1828 | decision_frame_safe |
| decision_frame_v1 | pressure_price_alignment_ratio | 120 | spread_bucket | q1 | 108621 | -1.2486 | 2.1801 | decision_frame_safe |
| decision_frame_v1 | pressure_exhaustion_gap | 60 | spread_bucket | q3 | 95281 | -1.1471 | 2.1620 | decision_frame_safe |
| fixed_event_panel | pressure_to_price_efficiency | 120 | mlofi_bucket | q3 | 117539 | -0.2992 | 2.1523 | research_panel_only |
| fixed_event_panel | cost_allowed_trend_structure | 30 | activity_bucket | q2 | 72264 | -0.3170 | 2.1272 | research_panel_only |
| fixed_event_panel | signed_price_path_ratio | 120 | mlofi_bucket | q3 | 118879 | -0.9857 | 2.0774 | research_panel_only |
| fixed_event_panel | pressure_price_alignment_ratio | 120 | activity_bucket | q1 | 119424 | -2.0646 | 2.0609 | research_panel_only |
| decision_frame_v1 | pressure_exhaustion_gap | 120 | spread_bucket | q3 | 109441 | -0.8469 | 2.0514 | decision_frame_safe |
| fixed_event_panel | pressure_exhaustion_gap | 120 | spread_bucket | q3 | 126141 | -1.4388 | 1.9832 | research_panel_only |
| fixed_event_panel | pressure_to_price_efficiency | 120 | activity_bucket | q1 | 115181 | -1.2044 | 1.9744 | research_panel_only |

## Interpretation Rules

- `diagnostic_positive` means the factor survived the diagnostic estimator, not that it is a strategy input.
- `research_panel_only` means the evidence uses fixed-event derived fields and must be reconstructed or rejected before runtime use.
- `spread_cost_mirage` means mid/release evidence exists but top-of-book taker economics are non-positive.
- `decay_risk_only` and `cost_gate_only` are controls or gates, not standalone alpha.

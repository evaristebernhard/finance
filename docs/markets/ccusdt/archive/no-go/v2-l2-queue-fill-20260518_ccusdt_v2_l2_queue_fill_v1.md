# CCUSDT V2 L2 Queue Fill

Status: `20260518_ccusdt_v2_l2_queue_fill_v1` from framework run `20260518_ccusdt_v2_framework_v1`.

Guardrail: `research_only_l2_queue_fill_no_execution_recommendation_no_alpha_claim`.

This pass uses local Bullish `incremental_book_L2` same-price amount decreases as queue-ahead pressure, while requiring subsequent opposite-side trades to fill the simulated maker order. It is stricter than crediting all L2 decreases as fills and less optimistic than midpoint labels.

## Scope

- Focus entries: `1204`.
- Event rows: `97524`.
- Latency ms: `0,250,1000`.
- Fill timeout ms: `1000,5000,10000`.
- Order notionals quote: `50,100,250`.
- Fee stress bps: `0,2,5`.
- L2 chunk rows: `750000`.

## L2 Queue Scorecard

| fold | trigger_class | entry_quality_bin | signals | fill_rate | avg_fill_ratio | filled_net_mean_bps | filled_net_p10_bps | per_signal_net_mean_bps | break_even_fee_for_2bps_mean | fill_pass | net_pass | fee_budget_pass | tail_pass | l2_queue_fill_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.0435 | 0.0448 | -0.0877 | -21.7321 | -0.0038 | -0.0877 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold3 | tfi_follow_flat | high | 508 | 0.0413 | 0.0425 | -2.1469 | -22.0504 | -0.0887 | -2.1469 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold3 | tfi_event_active | mid | 72 | 0.0833 | 0.0833 | -12.0666 | -15.7472 | -1.0056 | -12.0666 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.0308 | 0.0313 | -15.6430 | -39.6959 | -0.4813 | -15.6430 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold3 | tfi_short_stale25 | low | 38 | 0.0526 | 0.0526 | -23.3479 | -33.3388 | -1.2288 | -23.3479 | False | False | False | False | l2_queue_fill_no_go |

## Practical Scenario Queue Decomposition

| fold | trigger_class | entry_quality_bin | signals | fill_rate | avg_fill_ratio | queue_ahead_p50_base | queue_drain_l2_decrease_mean_base | queue_drain_trade_mean_base | own_fill_trade_mean_base | filled_net_mean_bps | per_signal_net_mean_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.0435 | 0.0448 | 29.7961 | 86.6759 | 8.1860 | 27.5478 | -0.0877 | -0.0038 |
| expanding_fold3 | tfi_follow_flat | high | 508 | 0.0413 | 0.0425 | 33.1325 | 66.0523 | 9.7171 | 26.2789 | -2.1469 | -0.0887 |
| expanding_fold3 | tfi_event_active | mid | 72 | 0.0833 | 0.0833 | 23.1352 | 5.2387 | 15.1382 | 51.2133 | -12.0666 | -1.0056 |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.0308 | 0.0313 | 19.6315 | 31.2342 | 3.6879 | 19.7636 | -15.6430 | -0.4813 |
| expanding_fold3 | tfi_short_stale25 | low | 38 | 0.0526 | 0.0526 | 21.8522 | 17.0180 | 0.7849 | 32.7022 | -23.3479 | -1.2288 |

## Top Scenario Rows

| fold | trigger_class | entry_quality_bin | latency_ms | fill_timeout_ms | order_notional_quote | fee_stress_bps | signals | fill_rate | filled_net_mean_bps | per_signal_net_mean_bps | break_even_fee_for_2bps_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 250.0000 | 0.0000 | 508 | 0.0020 | 22.9782 | 0.0452 | 20.9782 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 250.0000 | 0.0000 | 391 | 0.0026 | 22.9782 | 0.0588 | 20.9782 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 250.0000 | 2.0000 | 391 | 0.0026 | 20.9782 | 0.0537 | 20.9782 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 250.0000 | 2.0000 | 508 | 0.0020 | 20.9782 | 0.0413 | 20.9782 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 250.0000 | 5.0000 | 508 | 0.0020 | 17.9782 | 0.0354 | 20.9782 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 250.0000 | 5.0000 | 391 | 0.0026 | 17.9782 | 0.0460 | 20.9782 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 100.0000 | 0.0000 | 391 | 0.0102 | 6.9566 | 0.0712 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 50.0000 | 0.0000 | 391 | 0.0102 | 6.9566 | 0.0712 | 4.9566 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 50.0000 | 0.0000 | 508 | 0.0098 | 5.1765 | 0.0510 | 3.1765 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 100.0000 | 0.0000 | 508 | 0.0098 | 5.1765 | 0.0510 | 3.1765 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 50.0000 | 2.0000 | 391 | 0.0102 | 4.9566 | 0.0507 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 100.0000 | 2.0000 | 391 | 0.0102 | 4.9566 | 0.0507 | 4.9566 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 50.0000 | 0.0000 | 508 | 0.0020 | 4.3474 | 0.0086 | 2.3474 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 100.0000 | 0.0000 | 508 | 0.0020 | 4.3474 | 0.0086 | 2.3474 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 100.0000 | 0.0000 | 391 | 0.0486 | 3.7205 | 0.1808 | 1.7205 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 50.0000 | 0.0000 | 391 | 0.0486 | 3.7205 | 0.1808 | 1.7205 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 100.0000 | 2.0000 | 508 | 0.0098 | 3.1765 | 0.0313 | 3.1765 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 50.0000 | 2.0000 | 508 | 0.0098 | 3.1765 | 0.0313 | 3.1765 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 5000.0000 | 50.0000 | 0.0000 | 391 | 0.0486 | 2.6707 | 0.1298 | 0.6707 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 5000.0000 | 100.0000 | 0.0000 | 391 | 0.0486 | 2.6707 | 0.1298 | 0.6707 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 100.0000 | 2.0000 | 508 | 0.0020 | 2.3474 | 0.0046 | 2.3474 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 50.0000 | 2.0000 | 508 | 0.0020 | 2.3474 | 0.0046 | 2.3474 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 50.0000 | 5.0000 | 391 | 0.0102 | 1.9566 | 0.0200 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 100.0000 | 5.0000 | 391 | 0.0102 | 1.9566 | 0.0200 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 250.0000 | 5000.0000 | 100.0000 | 0.0000 | 391 | 0.0435 | 1.9123 | 0.0831 | -0.0877 |
| expanding_fold3 | tfi_short_flat | high | 250.0000 | 5000.0000 | 50.0000 | 0.0000 | 391 | 0.0435 | 1.9123 | 0.0831 | -0.0877 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 250.0000 | 0.0000 | 391 | 0.0358 | 1.8482 | 0.0662 | -0.1518 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 50.0000 | 2.0000 | 391 | 0.0486 | 1.7205 | 0.0836 | 1.7205 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 100.0000 | 2.0000 | 391 | 0.0486 | 1.7205 | 0.0836 | 1.7205 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 5000.0000 | 250.0000 | 0.0000 | 391 | 0.0307 | 1.4721 | 0.0452 | -0.5279 |

## Decision

This remains research-only. A row still needs real fee tier, measured latency, order acknowledgements or live/paper fills, and walk-forward continuation before executable status.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_events_20260518_ccusdt_v2_l2_queue_fill_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_l2_queue_fill.py
```

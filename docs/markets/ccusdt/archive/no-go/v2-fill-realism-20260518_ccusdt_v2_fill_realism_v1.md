# CCUSDT V2 Fill Realism

Status: `20260518_ccusdt_v2_fill_realism_v1` from framework run `20260518_ccusdt_v2_framework_v1`.

Guardrail: `research_only_fill_realism_no_execution_recommendation_no_alpha_claim`.

This pass estimates maker top-of-book fill plausibility from local Bullish `book_ticker` and `trades`. It is still not a production queue simulator and does not assert a real fee tier.

## Scope

- Focus entries: `1204`.
- Latency ms: `0,250,1000`.
- Fill timeout ms: `1000,5000,10000`.
- Order notionals quote: `50,100,250`.
- Fee stress bps: `0,2,5`.

## Fill Scorecard

| fold | trigger_class | entry_quality_bin | signals | fill_rate | filled_net_mean_bps | per_signal_net_mean_bps | break_even_fee_for_2bps_mean | fill_pass | net_pass | fee_budget_pass | fill_realism_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.0435 | -0.0877 | -0.0038 | -0.0877 | False | False | False | fill_realism_no_go |
| expanding_fold3 | tfi_follow_flat | high | 508 | 0.0413 | -2.1469 | -0.0887 | -2.1469 | False | False | False | fill_realism_no_go |
| expanding_fold3 | tfi_event_active | mid | 72 | 0.0833 | -12.0666 | -1.0056 | -12.0666 | False | False | False | fill_realism_no_go |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.0308 | -15.6430 | -0.4813 | -15.6430 | False | False | False | fill_realism_no_go |
| expanding_fold3 | tfi_short_stale25 | low | 38 | 0.0526 | -23.3479 | -1.2288 | -23.3479 | False | False | False | fill_realism_no_go |

## Top Scenario Rows

| fold | trigger_class | entry_quality_bin | latency_ms | fill_timeout_ms | order_notional_quote | fee_stress_bps | signals | fill_rate | filled_net_mean_bps | per_signal_net_mean_bps | break_even_fee_for_2bps_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 250.0000 | 0.0000 | 391 | 0.0026 | 22.9782 | 0.0588 | 20.9782 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 250.0000 | 0.0000 | 508 | 0.0020 | 22.9782 | 0.0452 | 20.9782 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 250.0000 | 2.0000 | 508 | 0.0020 | 20.9782 | 0.0413 | 20.9782 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 250.0000 | 2.0000 | 391 | 0.0026 | 20.9782 | 0.0537 | 20.9782 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 250.0000 | 5.0000 | 391 | 0.0026 | 17.9782 | 0.0460 | 20.9782 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 250.0000 | 5.0000 | 508 | 0.0020 | 17.9782 | 0.0354 | 20.9782 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 100.0000 | 0.0000 | 391 | 0.0102 | 6.9566 | 0.0712 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 50.0000 | 0.0000 | 391 | 0.0102 | 6.9566 | 0.0712 | 4.9566 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 100.0000 | 0.0000 | 508 | 0.0098 | 5.1765 | 0.0510 | 3.1765 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 50.0000 | 0.0000 | 508 | 0.0098 | 5.1765 | 0.0510 | 3.1765 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 50.0000 | 2.0000 | 391 | 0.0102 | 4.9566 | 0.0507 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 100.0000 | 2.0000 | 391 | 0.0102 | 4.9566 | 0.0507 | 4.9566 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 50.0000 | 0.0000 | 508 | 0.0020 | 4.3474 | 0.0086 | 2.3474 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 100.0000 | 0.0000 | 508 | 0.0020 | 4.3474 | 0.0086 | 2.3474 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 50.0000 | 0.0000 | 391 | 0.0460 | 3.7605 | 0.1731 | 1.7605 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 100.0000 | 0.0000 | 391 | 0.0460 | 3.7605 | 0.1731 | 1.7605 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 250.0000 | 0.0000 | 391 | 0.0332 | 3.3984 | 0.1130 | 1.3984 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 50.0000 | 2.0000 | 508 | 0.0098 | 3.1765 | 0.0313 | 3.1765 |
| expanding_fold3 | tfi_follow_flat | high | 0.0000 | 1000.0000 | 100.0000 | 2.0000 | 508 | 0.0098 | 3.1765 | 0.0313 | 3.1765 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 5000.0000 | 100.0000 | 0.0000 | 391 | 0.0486 | 2.6707 | 0.1298 | 0.6707 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 5000.0000 | 50.0000 | 0.0000 | 391 | 0.0486 | 2.6707 | 0.1298 | 0.6707 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 50.0000 | 2.0000 | 508 | 0.0020 | 2.3474 | 0.0046 | 2.3474 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 1000.0000 | 100.0000 | 2.0000 | 508 | 0.0020 | 2.3474 | 0.0046 | 2.3474 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 50.0000 | 5.0000 | 391 | 0.0102 | 1.9566 | 0.0200 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 1000.0000 | 100.0000 | 5.0000 | 391 | 0.0102 | 1.9566 | 0.0200 | 4.9566 |
| expanding_fold3 | tfi_short_flat | high | 250.0000 | 5000.0000 | 50.0000 | 0.0000 | 391 | 0.0435 | 1.9123 | 0.0831 | -0.0877 |
| expanding_fold3 | tfi_short_flat | high | 250.0000 | 5000.0000 | 100.0000 | 0.0000 | 391 | 0.0435 | 1.9123 | 0.0831 | -0.0877 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 100.0000 | 2.0000 | 391 | 0.0460 | 1.7605 | 0.0810 | 1.7605 |
| expanding_fold3 | tfi_short_flat | high | 1000.0000 | 5000.0000 | 50.0000 | 2.0000 | 391 | 0.0460 | 1.7605 | 0.0810 | 1.7605 |
| expanding_fold3 | tfi_short_flat | high | 0.0000 | 5000.0000 | 250.0000 | 0.0000 | 391 | 0.0307 | 1.4721 | 0.0452 | -0.5279 |

## Decision

Use this as an execution-realism filter only. A row can leave research-no-go only after this proxy is replaced or confirmed by a full incremental-book queue replay, real fee tier, and latency/fill evidence.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_realism_events_20260518_ccusdt_v2_fill_realism_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_realism_summary_20260518_ccusdt_v2_fill_realism_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_realism_scorecard_20260518_ccusdt_v2_fill_realism_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_fill_realism_summary_20260518_ccusdt_v2_fill_realism_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_fill_realism.py
```

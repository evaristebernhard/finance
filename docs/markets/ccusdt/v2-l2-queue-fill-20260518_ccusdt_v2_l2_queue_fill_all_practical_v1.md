# CCUSDT V2 L2 Queue Fill

Status: `20260518_ccusdt_v2_l2_queue_fill_all_practical_v1` from framework run `20260518_ccusdt_v2_framework_v1`.

Guardrail: `research_only_l2_queue_fill_no_execution_recommendation_no_alpha_claim`.

This pass uses local Bullish `incremental_book_L2` same-price amount decreases as queue-ahead pressure, while requiring subsequent opposite-side trades to fill the simulated maker order. It is stricter than crediting all L2 decreases as fills and less optimistic than midpoint labels.

## Scope

- Focus entries: `6447`.
- Event rows: `6447`.
- Latency ms: `250`.
- Fill timeout ms: `5000`.
- Order notionals quote: `100`.
- Fee stress bps: `2`.
- L2 chunk rows: `750000`.

## L2 Queue Scorecard

| fold | trigger_class | entry_quality_bin | signals | fill_rate | avg_fill_ratio | filled_net_mean_bps | filled_net_p10_bps | per_signal_net_mean_bps | break_even_fee_for_2bps_mean | fill_pass | net_pass | fee_budget_pass | tail_pass | l2_queue_fill_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.0435 | 0.0448 | -0.0877 | -21.7321 | -0.0038 | -0.0877 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold2 | tfi_short_flat | mid | 206 | 0.0388 | 0.0389 | -0.9986 | -6.2082 | -0.0388 | -0.9986 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_event_active | low | 21 | 0.0952 | 0.0952 | -1.0078 | -5.5937 | -0.0960 | -1.0078 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_stale25 | low | 17 | 0.1176 | 0.1176 | -1.0078 | -5.5937 | -0.1186 | -1.0078 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold2 | tfi_long_flat | low | 142 | 0.0070 | 0.0076 | -2.0000 | -2.0000 | -0.0141 | -2.0000 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold2 | tfi_follow_flat | mid | 291 | 0.0206 | 0.0206 | -2.0947 | -7.7126 | -0.0432 | -2.0947 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold3 | tfi_follow_flat | high | 508 | 0.0413 | 0.0425 | -2.1469 | -22.0504 | -0.0887 | -2.1469 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold1 | tfi_follow_flat | low | 186 | 0.0215 | 0.0215 | -2.1763 | -6.1250 | -0.0468 | -2.1763 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold2 | tfi_event_active | high | 56 | 0.0536 | 0.0550 | -2.2653 | -10.4318 | -0.1214 | -2.2653 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_long_flat | low | 140 | 0.0143 | 0.0143 | -3.3448 | -4.4207 | -0.0478 | -3.3448 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold2 | tfi_long_flat | high | 137 | 0.0292 | 0.0295 | -3.3493 | -7.9329 | -0.0978 | -3.3493 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_follow_flat | high | 317 | 0.0410 | 0.0410 | -3.4957 | -9.4823 | -0.1434 | -3.4957 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold2 | tfi_long_flat | mid | 102 | 0.0392 | 0.0392 | -3.7047 | -8.2210 | -0.1453 | -3.7047 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_flat | high | 188 | 0.0585 | 0.0593 | -3.8339 | -6.7114 | -0.2243 | -3.8339 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_flat | low | 88 | 0.0795 | 0.0795 | -4.9726 | -9.2363 | -0.3956 | -4.9726 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_short_flat | mid | 132 | 0.0152 | 0.0152 | -5.3782 | -8.0807 | -0.0815 | -5.3782 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_long_flat | high | 129 | 0.0388 | 0.0388 | -5.4936 | -8.9930 | -0.2129 | -5.4936 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold2 | tfi_follow_flat | low | 298 | 0.0336 | 0.0339 | -5.5247 | -12.8272 | -0.1854 | -5.5247 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_event_active | high | 31 | 0.0968 | 0.0968 | -7.1554 | -9.5309 | -0.6925 | -7.1554 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold3 | tfi_long_flat | mid | 99 | 0.0707 | 0.0717 | -7.5617 | -10.9803 | -0.5347 | -7.5617 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold1 | tfi_long_flat | mid | 134 | 0.0448 | 0.0448 | -7.9794 | -21.0357 | -0.3573 | -7.9794 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold1 | tfi_follow_flat | mid | 250 | 0.0400 | 0.0406 | -8.2162 | -12.7807 | -0.3286 | -8.2162 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold3 | tfi_follow_flat | mid | 286 | 0.0490 | 0.0512 | -10.0897 | -15.8327 | -0.4939 | -10.0897 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold3 | tfi_long_flat | low | 199 | 0.0553 | 0.0579 | -11.4983 | -23.3835 | -0.6356 | -11.4983 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold3 | tfi_follow_flat | low | 335 | 0.0507 | 0.0507 | -11.7787 | -28.3647 | -0.5977 | -11.7787 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold3 | tfi_event_active | high | 85 | 0.0588 | 0.0588 | -11.8747 | -21.5954 | -0.6985 | -11.8747 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold3 | tfi_event_active | mid | 72 | 0.0833 | 0.0833 | -12.0666 | -15.7472 | -1.0056 | -12.0666 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold3 | tfi_short_stale25 | high | 54 | 0.0741 | 0.0741 | -12.3320 | -15.4941 | -0.9135 | -12.3320 | False | False | False | True | l2_queue_fill_no_go |
| expanding_fold3 | tfi_short_flat | mid | 196 | 0.0663 | 0.0666 | -13.5409 | -25.8914 | -0.8981 | -13.5409 | False | False | False | False | l2_queue_fill_no_go |
| expanding_fold2 | tfi_short_stale25 | high | 31 | 0.0323 | 0.0323 | -13.6558 | -13.6558 | -0.4405 | -13.6558 | False | False | False | True | l2_queue_fill_no_go |

## Practical Scenario Queue Decomposition

| fold | trigger_class | entry_quality_bin | signals | fill_rate | avg_fill_ratio | queue_ahead_p50_base | queue_drain_l2_decrease_mean_base | queue_drain_trade_mean_base | own_fill_trade_mean_base | filled_net_mean_bps | per_signal_net_mean_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.0435 | 0.0448 | 29.7961 | 86.6759 | 8.1860 | 27.5478 | -0.0877 | -0.0038 |
| expanding_fold2 | tfi_short_flat | mid | 206 | 0.0388 | 0.0389 | 190.0055 | 73.9097 | 15.8291 | 25.1273 | -0.9986 | -0.0388 |
| expanding_fold1 | tfi_event_active | low | 21 | 0.0952 | 0.0952 | 139.6367 | 156.8698 | 47.2701 | 64.2641 | -1.0078 | -0.0960 |
| expanding_fold1 | tfi_short_stale25 | low | 17 | 0.1176 | 0.1176 | 79.9330 | 187.4917 | 58.3925 | 79.3851 | -1.0078 | -0.1186 |
| expanding_fold2 | tfi_long_flat | low | 142 | 0.0070 | 0.0076 | 497.6426 | 85.3471 | 2.9162 | 4.8840 | -2.0000 | -0.0141 |
| expanding_fold2 | tfi_follow_flat | mid | 291 | 0.0206 | 0.0206 | 319.4436 | 78.5665 | 6.1223 | 13.2308 | -2.0947 | -0.0432 |
| expanding_fold3 | tfi_follow_flat | high | 508 | 0.0413 | 0.0425 | 33.1325 | 66.0523 | 9.7171 | 26.2789 | -2.1469 | -0.0887 |
| expanding_fold1 | tfi_follow_flat | low | 186 | 0.0215 | 0.0215 | 270.0618 | 112.4973 | 9.2062 | 14.4831 | -2.1763 | -0.0468 |
| expanding_fold2 | tfi_event_active | high | 56 | 0.0536 | 0.0550 | 15.7435 | 35.9542 | 26.1123 | 35.3135 | -2.2653 | -0.1214 |
| expanding_fold1 | tfi_long_flat | low | 140 | 0.0143 | 0.0143 | 611.9421 | 134.6293 | 9.6527 | 9.5897 | -3.3448 | -0.0478 |
| expanding_fold2 | tfi_long_flat | high | 137 | 0.0292 | 0.0295 | 45.3426 | 43.2215 | 8.7127 | 18.8970 | -3.3493 | -0.0978 |
| expanding_fold1 | tfi_follow_flat | high | 317 | 0.0410 | 0.0410 | 764.3080 | 142.0765 | 27.7382 | 27.5244 | -3.4957 | -0.1434 |
| expanding_fold2 | tfi_long_flat | mid | 102 | 0.0392 | 0.0392 | 282.6408 | 46.0900 | 21.7328 | 25.8680 | -3.7047 | -0.1453 |
| expanding_fold1 | tfi_short_flat | high | 188 | 0.0585 | 0.0593 | 532.2812 | 79.9974 | 43.2740 | 39.8096 | -3.8339 | -0.2243 |
| expanding_fold1 | tfi_short_flat | low | 88 | 0.0795 | 0.0795 | 913.0889 | 160.4234 | 60.4088 | 53.4830 | -4.9726 | -0.3956 |
| expanding_fold1 | tfi_short_flat | mid | 132 | 0.0152 | 0.0152 | 1385.5900 | 144.1204 | 1.0728 | 10.2110 | -5.3782 | -0.0815 |
| expanding_fold1 | tfi_long_flat | high | 129 | 0.0388 | 0.0388 | 481.8242 | 125.1661 | 16.1886 | 26.0243 | -5.4936 | -0.2129 |
| expanding_fold2 | tfi_follow_flat | low | 298 | 0.0336 | 0.0339 | 51.8885 | 29.7477 | 12.1890 | 21.7745 | -5.5247 | -0.1854 |
| expanding_fold1 | tfi_event_active | high | 31 | 0.0968 | 0.0968 | 272.9251 | 50.5687 | 33.0876 | 65.0627 | -7.1554 | -0.6925 |
| expanding_fold3 | tfi_long_flat | mid | 99 | 0.0707 | 0.0717 | 34.9159 | 49.8863 | 17.9796 | 45.1446 | -7.5617 | -0.5347 |
| expanding_fold1 | tfi_long_flat | mid | 134 | 0.0448 | 0.0448 | 1031.6061 | 140.7628 | 51.2562 | 30.1959 | -7.9794 | -0.3573 |
| expanding_fold1 | tfi_follow_flat | mid | 250 | 0.0400 | 0.0406 | 1032.7229 | 138.2965 | 35.8365 | 27.3616 | -8.2162 | -0.3286 |
| expanding_fold3 | tfi_follow_flat | mid | 286 | 0.0490 | 0.0512 | 40.3589 | 54.1676 | 15.1619 | 32.0195 | -10.0897 | -0.4939 |
| expanding_fold3 | tfi_long_flat | low | 199 | 0.0553 | 0.0579 | 82.9295 | 84.1042 | 22.3359 | 36.3044 | -11.4983 | -0.6356 |
| expanding_fold3 | tfi_follow_flat | low | 335 | 0.0507 | 0.0507 | 36.1368 | 63.7179 | 13.8883 | 31.9393 | -11.7787 | -0.5977 |
| expanding_fold3 | tfi_event_active | high | 85 | 0.0588 | 0.0588 | 20.3265 | 23.0896 | 3.3282 | 36.7942 | -11.8747 | -0.6985 |
| expanding_fold3 | tfi_event_active | mid | 72 | 0.0833 | 0.0833 | 23.1352 | 5.2387 | 15.1382 | 51.2133 | -12.0666 | -1.0056 |
| expanding_fold3 | tfi_short_stale25 | high | 54 | 0.0741 | 0.0741 | 16.2097 | 3.3604 | 9.3099 | 46.7953 | -12.3320 | -0.9135 |
| expanding_fold3 | tfi_short_flat | mid | 196 | 0.0663 | 0.0666 | 56.4811 | 61.0307 | 20.3947 | 41.3640 | -13.5409 | -0.8981 |
| expanding_fold2 | tfi_short_stale25 | high | 31 | 0.0323 | 0.0323 | 67.3379 | 3.7977 | 14.0923 | 20.9007 | -13.6558 | -0.4405 |

## Top Scenario Rows

| fold | trigger_class | entry_quality_bin | latency_ms | fill_timeout_ms | order_notional_quote | fee_stress_bps | signals | fill_rate | filled_net_mean_bps | per_signal_net_mean_bps | break_even_fee_for_2bps_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 391 | 0.0435 | -0.0877 | -0.0038 | -0.0877 |
| expanding_fold2 | tfi_short_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 206 | 0.0388 | -0.9986 | -0.0388 | -0.9986 |
| expanding_fold1 | tfi_event_active | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 21 | 0.0952 | -1.0078 | -0.0960 | -1.0078 |
| expanding_fold1 | tfi_short_stale25 | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 17 | 0.1176 | -1.0078 | -0.1186 | -1.0078 |
| expanding_fold2 | tfi_long_flat | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 142 | 0.0070 | -2.0000 | -0.0141 | -2.0000 |
| expanding_fold2 | tfi_follow_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 291 | 0.0206 | -2.0947 | -0.0432 | -2.0947 |
| expanding_fold3 | tfi_follow_flat | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 508 | 0.0413 | -2.1469 | -0.0887 | -2.1469 |
| expanding_fold1 | tfi_follow_flat | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 186 | 0.0215 | -2.1763 | -0.0468 | -2.1763 |
| expanding_fold2 | tfi_event_active | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 56 | 0.0536 | -2.2653 | -0.1214 | -2.2653 |
| expanding_fold1 | tfi_long_flat | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 140 | 0.0143 | -3.3448 | -0.0478 | -3.3448 |
| expanding_fold2 | tfi_long_flat | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 137 | 0.0292 | -3.3493 | -0.0978 | -3.3493 |
| expanding_fold1 | tfi_follow_flat | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 317 | 0.0410 | -3.4957 | -0.1434 | -3.4957 |
| expanding_fold2 | tfi_long_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 102 | 0.0392 | -3.7047 | -0.1453 | -3.7047 |
| expanding_fold1 | tfi_short_flat | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 188 | 0.0585 | -3.8339 | -0.2243 | -3.8339 |
| expanding_fold1 | tfi_short_flat | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 88 | 0.0795 | -4.9726 | -0.3956 | -4.9726 |
| expanding_fold1 | tfi_short_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 132 | 0.0152 | -5.3782 | -0.0815 | -5.3782 |
| expanding_fold1 | tfi_long_flat | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 129 | 0.0388 | -5.4936 | -0.2129 | -5.4936 |
| expanding_fold2 | tfi_follow_flat | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 298 | 0.0336 | -5.5247 | -0.1854 | -5.5247 |
| expanding_fold1 | tfi_event_active | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 31 | 0.0968 | -7.1554 | -0.6925 | -7.1554 |
| expanding_fold3 | tfi_long_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 99 | 0.0707 | -7.5617 | -0.5347 | -7.5617 |
| expanding_fold1 | tfi_long_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 134 | 0.0448 | -7.9794 | -0.3573 | -7.9794 |
| expanding_fold1 | tfi_follow_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 250 | 0.0400 | -8.2162 | -0.3286 | -8.2162 |
| expanding_fold3 | tfi_follow_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 286 | 0.0490 | -10.0897 | -0.4939 | -10.0897 |
| expanding_fold3 | tfi_long_flat | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 199 | 0.0553 | -11.4983 | -0.6356 | -11.4983 |
| expanding_fold3 | tfi_follow_flat | low | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 335 | 0.0507 | -11.7787 | -0.5977 | -11.7787 |
| expanding_fold3 | tfi_event_active | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 85 | 0.0588 | -11.8747 | -0.6985 | -11.8747 |
| expanding_fold3 | tfi_event_active | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 72 | 0.0833 | -12.0666 | -1.0056 | -12.0666 |
| expanding_fold3 | tfi_short_stale25 | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 54 | 0.0741 | -12.3320 | -0.9135 | -12.3320 |
| expanding_fold3 | tfi_short_flat | mid | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 196 | 0.0663 | -13.5409 | -0.8981 | -13.5409 |
| expanding_fold2 | tfi_short_stale25 | high | 250.0000 | 5000.0000 | 100.0000 | 2.0000 | 31 | 0.0323 | -13.6558 | -0.4405 | -13.6558 |

## Decision

This remains research-only. A row still needs real fee tier, measured latency, order acknowledgements or live/paper fills, and walk-forward continuation before executable status.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_events_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_l2_queue_fill.py
```

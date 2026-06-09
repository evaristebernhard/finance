# CCUSDT V2 Queue Release Pivot

Status: `20260518_ccusdt_v2_queue_release_pivot_fast_v1`.

Guardrail: `research_only_queue_release_pivot_no_execution_recommendation_no_alpha_claim`.

This is a lightweight `book_ticker` prototype for the queue-release continuation pivot. It is not an executable strategy.

## Scope

- Event rows: `38264`.
- Summary rows: `24`.
- Horizons sec: `5,10`.
- Threshold quantiles: `0.975,0.99`.
- Fee stress bps: `2.0`.

## Scorecard

| fold | release_side | horizon_sec | threshold_quantile | entries | net_mean_bps | net_plus2_mean_bps | net_median_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | sample_pass | economics_pass | controls_pass | pivot_promote_gate | queue_release_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | bid_release_short | 10.0000 | 0.9900 | 1095 | -1.7573 | -3.7573 | -2.6492 | 0.0000 | 1.6947 | True | False | False | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 10.0000 | 0.9750 | 2019 | -2.1439 | -4.1439 | -2.6527 | 0.0000 | 1.4907 | True | False | False | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 5.0000 | 0.9900 | 1095 | -2.4283 | -4.4283 | -2.6518 | 0.0000 | 1.2129 | True | False | False | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 5.0000 | 0.9750 | 2019 | -2.5906 | -4.5906 | -2.6587 | 0.0000 | 1.1189 | True | False | False | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 10.0000 | 0.9900 | 1386 | -2.6770 | -4.6770 | -2.6402 | 0.0000 | 1.0068 | True | False | False | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 10.0000 | 0.9750 | 2401 | -2.6835 | -4.6835 | -2.6506 | 0.0000 | 1.1183 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 5.0000 | 0.9900 | 1030 | -2.7139 | -4.7139 | -2.6887 | 0.0000 | 1.1480 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 10.0000 | 0.9900 | 1030 | -2.7720 | -4.7720 | -2.6868 | 0.0000 | 0.9351 | True | False | False | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 5.0000 | 0.9900 | 1386 | -2.7741 | -4.7741 | -2.6430 | 0.0000 | 0.9298 | True | False | False | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 5.0000 | 0.9750 | 2401 | -2.8752 | -4.8752 | -2.6526 | 0.0000 | 0.8829 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 10.0000 | 0.9750 | 1898 | -3.1350 | -5.1350 | -3.2820 | 0.0000 | 0.6973 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 5.0000 | 0.9750 | 1898 | -3.2021 | -5.2021 | -3.2869 | 0.0000 | 0.7060 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | bid_release_short | 10.0000 | 0.9900 | 989 | -3.3249 | -5.3249 | -3.3450 | 0.0000 | 0.7573 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | bid_release_short | 5.0000 | 0.9900 | 989 | -3.4499 | -5.4499 | -3.3476 | 0.0000 | 0.6328 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | bid_release_short | 10.0000 | 0.9900 | 960 | -3.4960 | -5.4960 | -3.2829 | 0.0000 | 0.5246 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | bid_release_short | 10.0000 | 0.9750 | 2102 | -3.5678 | -5.5678 | -3.3524 | 0.0000 | 0.5527 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | bid_release_short | 10.0000 | 0.9750 | 1814 | -3.5893 | -5.5893 | -3.2950 | 0.0000 | 0.3934 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | ask_release_long | 10.0000 | 0.9900 | 1102 | -3.5924 | -5.5924 | -3.3530 | 0.0000 | 0.5212 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | ask_release_long | 10.0000 | 0.9750 | 2336 | -3.6158 | -5.6158 | -3.3587 | 0.0000 | 0.4983 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | bid_release_short | 5.0000 | 0.9750 | 2102 | -3.6441 | -5.6441 | -3.3547 | 0.0000 | 0.4709 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | ask_release_long | 5.0000 | 0.9750 | 2336 | -3.7087 | -5.7087 | -3.3633 | 0.0000 | 0.4075 | True | False | False | False | queue_release_no_go |
| expanding_fold1 | ask_release_long | 5.0000 | 0.9900 | 1102 | -3.7382 | -5.7382 | -3.3539 | 0.0000 | 0.3924 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | bid_release_short | 5.0000 | 0.9900 | 960 | -3.7463 | -5.7463 | -3.2842 | 0.0500 | 0.2501 | True | False | False | False | queue_release_no_go |
| expanding_fold2 | bid_release_short | 5.0000 | 0.9750 | 1814 | -3.7806 | -5.7806 | -3.3021 | 0.0000 | 0.2277 | True | False | False | False | queue_release_no_go |

## Decision

No queue-release prototype row passed the combined sample, economics, stress, control, median, and risk gates.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_events_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_controls_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_fast_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_queue_release_pivot.py --run-tag 20260518_ccusdt_v2_queue_release_pivot_fast_v1
```

# CCUSDT V2 Queue Release Pivot

Status: `20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1`.

Guardrail: `research_only_queue_release_pivot_no_execution_recommendation_no_alpha_claim`.

This is a lightweight `book_ticker` prototype for the queue-release continuation pivot. It is not an executable strategy.

## Scope

- Symbol: `BTCUSDC`.
- Data root: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1`.
- Event rows: `1023`.
- Summary rows: `18`.
- Horizons sec: `1,5,10`.
- Threshold quantiles: `0.99`.
- Candidate prefilter quantile: `0.95`.
- Fee stress bps: `2.0`.

## Scorecard

| fold | release_side | horizon_sec | threshold_quantile | entries | net_mean_bps | net_plus2_mean_bps | net_median_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | sample_pass | economics_pass | controls_pass | pivot_promote_gate | queue_release_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | bid_release_short | 10.0000 | 0.9900 | 53 | -1.7210 | -3.7210 | -1.9752 | 0.1200 | 0.2821 | False | False | False | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 1.0000 | 0.9900 | 44 | -1.8988 | -3.8988 | -2.0123 | 0.1800 | 0.0613 | False | False | False | False | queue_release_no_go |
| expanding_fold2 | bid_release_short | 10.0000 | 0.9900 | 30 | -1.9119 | -3.9119 | -2.0498 | 0.4000 | 0.0723 | False | False | False | False | queue_release_no_go |
| expanding_fold2 | bid_release_short | 5.0000 | 0.9900 | 30 | -1.9454 | -3.9454 | -2.0125 | 0.3200 | 0.0992 | False | False | False | False | queue_release_no_go |
| expanding_fold1 | bid_release_short | 1.0000 | 0.9900 | 53 | -1.9482 | -3.9482 | -2.0123 | 0.3600 | 0.0202 | False | False | False | False | queue_release_no_go |
| expanding_fold2 | bid_release_short | 1.0000 | 0.9900 | 30 | -1.9586 | -3.9586 | -2.0123 | 0.4000 | 0.0214 | False | False | False | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 5.0000 | 0.9900 | 53 | -1.9785 | -3.9785 | -1.9877 | 0.5000 | -0.0016 | False | False | False | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 10.0000 | 0.9900 | 74 | -1.9787 | -3.9787 | -2.0187 | 0.2800 | 0.1010 | False | False | False | False | queue_release_no_go |
| expanding_fold3 | bid_release_short | 1.0000 | 0.9900 | 53 | -1.9853 | -3.9853 | -2.0124 | 0.5400 | -0.0086 | False | False | False | False | queue_release_no_go |
| expanding_fold1 | ask_release_long | 1.0000 | 0.9900 | 87 | -2.0087 | -4.0087 | -2.0124 | 0.6600 | -0.0264 | False | False | False | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 5.0000 | 0.9900 | 44 | -2.0352 | -4.0352 | -2.0125 | 0.7800 | -0.1991 | False | False | False | False | queue_release_no_go |
| expanding_fold1 | ask_release_long | 5.0000 | 0.9900 | 87 | -2.0439 | -4.0439 | -2.0123 | 0.7200 | -0.1088 | False | False | False | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 5.0000 | 0.9900 | 74 | -2.0757 | -4.0757 | -2.0126 | 0.7000 | -0.0831 | False | False | False | False | queue_release_no_go |
| expanding_fold3 | ask_release_long | 1.0000 | 0.9900 | 74 | -2.0836 | -4.0836 | -2.0124 | 0.9600 | -0.0667 | False | False | False | False | queue_release_no_go |
| expanding_fold1 | ask_release_long | 10.0000 | 0.9900 | 87 | -2.2227 | -4.2227 | -2.0124 | 0.7600 | -0.1629 | False | False | False | False | queue_release_no_go |
| expanding_fold1 | bid_release_short | 10.0000 | 0.9900 | 53 | -2.2490 | -4.2490 | -2.0123 | 0.8200 | -0.2332 | False | False | False | False | queue_release_no_go |
| expanding_fold1 | bid_release_short | 5.0000 | 0.9900 | 53 | -2.2503 | -4.2503 | -2.0123 | 0.9400 | -0.2967 | False | False | False | False | queue_release_no_go |
| expanding_fold2 | ask_release_long | 10.0000 | 0.9900 | 44 | -2.6286 | -4.6286 | -2.0000 | 0.9600 | -0.7034 | False | False | False | False | queue_release_no_go |

## Decision

No queue-release prototype row passed the combined sample, economics, stress, control, median, and risk gates.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_events_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_controls_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_queue_release_pivot.py --data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1 --symbol BTCUSDC --run-tag 20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1 --quantiles "0.99" --horizons-sec "1,5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 50 --candidate-prefilter-quantile 0.95
```

# CCUSDT V2 Cross-Market Lead/Lag Pivot

Status: `20260518_ccusdt_v2_cross_market_lead_lag_btc_smoke_v1`.

Guardrail: `research_only_cross_market_lead_lag_no_execution_recommendation_no_alpha_claim`.

## Inputs

- Target: `CCUSDT` from `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1`.
- Leaders: `BTCUSDC` from `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1`.
- Threshold quantiles: `0.99`.
- Horizons sec: `5,10`.
- Fee stress bps: `2.0`.
- Matched-random iters: `5`.
- Control selected cap: `500`.
- Control pool cap: `20000`.

## Decision

Promote-gate rows: `0`.

This is a structural cross-market diagnostic, not an execution recommendation. A row must pass sample, economics, stress, matched-random, reversed-side, median, and left-tail gates before it can move to heavier execution research.

Best row:

```text
leader/trigger/fold/horizon: BTCUSDC / leader_ret_5s_follow / expanding_fold3 / 5s
entries:                     1165
gross_mean_bps:              0.8212
cost_mean_bps:               3.9493
net_mean_bps:                -3.1282
net_median_bps:              -3.2919
signal_minus_random_p50_bps: 0.7482
signal_minus_reversed_bps:   1.6423
status:                      cross_market_no_go
```

## Scorecard

| leader_symbol | fold | trigger_class | horizon_sec | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | net_plus2_mean_bps | net_median_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | signal_minus_reversed_bps | sample_pass | economics_pass | controls_pass | cross_market_promote_gate | cross_market_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDC | expanding_fold3 | leader_ret_5s_follow | 5 | 1165 | 0.8212 | 3.9493 | -3.1282 | -5.1282 | -3.2919 | 0.0000 | 0.7482 | 1.6423 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_ret_5s_follow | 10 | 1165 | 0.7880 | 3.9229 | -3.1350 | -5.1350 | -3.2672 | 0.0000 | 0.4089 | 1.5759 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_5s_follow | 10 | 670 | 0.8470 | 4.1156 | -3.2686 | -5.2686 | -3.3716 | 0.0000 | 0.4953 | 1.6940 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_ret_1s_follow | 10 | 2921 | 0.6239 | 3.9511 | -3.3272 | -5.3272 | -3.3011 | 0.0000 | 0.5496 | 1.2479 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_ret_1s_follow | 5 | 2921 | 0.5474 | 3.9615 | -3.4141 | -5.4141 | -3.7605 | 0.0000 | 0.3620 | 1.0948 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_1s_follow | 10 | 1924 | 0.5905 | 4.1564 | -3.5658 | -5.5658 | -3.9185 | 0.0000 | 0.5196 | 1.1811 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_5s_follow | 5 | 670 | 0.5180 | 4.1052 | -3.5872 | -5.5872 | -3.3764 | 0.0000 | 0.3902 | 1.0360 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_5s_follow | 10 | 2021 | 0.5112 | 4.1003 | -3.5892 | -5.5892 | -3.3633 | 0.0000 | 0.4181 | 1.0223 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_1s_follow | 10 | 4897 | 0.3105 | 4.1221 | -3.8116 | -5.8116 | -4.0090 | 0.0000 | 0.1408 | 0.6209 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_1s_follow | 5 | 1924 | 0.3437 | 4.1571 | -3.8135 | -5.8135 | -3.9267 | 0.0000 | 0.3235 | 0.6873 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_5s_follow | 5 | 2021 | 0.2178 | 4.0969 | -3.8791 | -5.8791 | -4.0045 | 0.0000 | 0.0578 | 0.4357 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_1s_follow | 5 | 4899 | 0.1690 | 4.1147 | -3.9457 | -5.9457 | -4.0135 | 0.0000 | 0.0896 | 0.3380 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 10 | 31932 | 0.0196 | 4.0180 | -3.9984 | -5.9984 | -3.9337 | 0.0000 | 0.2252 | 0.0392 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 5 | 31936 | 0.0041 | 4.0169 | -4.0127 | -6.0127 | -3.9339 | 0.6000 | -0.0692 | 0.0083 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_trade_flow_5s_follow | 5 | 30746 | -0.0381 | 4.1043 | -4.1424 | -6.1424 | -3.9490 | 0.4000 | 0.0643 | -0.0762 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_trade_flow_5s_follow | 10 | 30745 | -0.0399 | 4.1078 | -4.1476 | -6.1476 | -3.9490 | 0.8000 | -0.1215 | -0.0798 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | lag_residual_5s_follow | 5 | 1299 | 0.0266 | 4.1963 | -4.1697 | -6.1697 | -4.0171 | 0.0000 | 0.0890 | 0.0532 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_trade_flow_5s_follow | 5 | 31383 | -0.0069 | 4.1927 | -4.1996 | -6.1996 | -4.0255 | 1.0000 | -0.0718 | -0.0138 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_microprice_follow | 5 | 949 | -0.1116 | 4.0926 | -4.2042 | -6.2042 | -3.9583 | 1.0000 | -0.1216 | -0.2232 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_trade_flow_5s_follow | 10 | 31382 | -0.0202 | 4.1926 | -4.2127 | -6.2127 | -4.0246 | 0.4000 | 0.0227 | -0.0403 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | lag_residual_5s_follow | 10 | 1299 | -0.0244 | 4.1924 | -4.2168 | -6.2168 | -4.0161 | 0.0000 | 0.3195 | -0.0488 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_microprice_follow | 10 | 949 | -0.1895 | 4.0823 | -4.2718 | -6.2718 | -4.0230 | 1.0000 | -0.1292 | -0.3790 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_microprice_follow | 5 | 2031 | -0.3337 | 3.9933 | -4.3270 | -6.3270 | -3.9503 | 1.0000 | -0.4348 | -0.6675 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_microprice_follow | 10 | 2031 | -0.3348 | 3.9941 | -4.3289 | -6.3289 | -3.9493 | 0.8000 | -0.0807 | -0.6695 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_microprice_follow | 5 | 1366 | -0.1567 | 4.2019 | -4.3586 | -6.3586 | -4.0423 | 0.8000 | -0.0577 | -0.3135 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_microprice_follow | 10 | 1366 | -0.2219 | 4.2041 | -4.4260 | -6.4260 | -4.0426 | 1.0000 | -0.2985 | -0.4438 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | lag_residual_5s_follow | 5 | 2760 | -0.2706 | 4.2116 | -4.4823 | -6.4823 | -4.5576 | 0.0000 | 0.1401 | -0.5412 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | lag_residual_5s_follow | 10 | 2759 | -0.4180 | 4.2014 | -4.6194 | -6.6194 | -4.5690 | 0.0000 | 0.2953 | -0.8360 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | lag_residual_5s_follow | 5 | 3612 | -0.5782 | 4.1760 | -4.7542 | -6.7542 | -4.6192 | 0.4000 | 0.0663 | -1.1564 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | lag_residual_5s_follow | 10 | 3612 | -0.8931 | 4.1423 | -5.0354 | -7.0354 | -5.0109 | 1.0000 | -0.4868 | -1.7862 | True | False | False | False | cross_market_no_go |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_events_20260518_ccusdt_v2_cross_market_lead_lag_btc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_controls_20260518_ccusdt_v2_cross_market_lead_lag_btc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_summary_20260518_ccusdt_v2_cross_market_lead_lag_btc_smoke_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_cross_market_lead_lag.py --target-data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1 --leader-data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1 --target-symbol CCUSDT --leaders "BTCUSDC" --run-tag 20260518_ccusdt_v2_cross_market_lead_lag_btc_smoke_v1 --threshold-quantiles "0.99" --horizons-sec "5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 5 --control-selected-cap 500 --control-pool-cap 20000
```

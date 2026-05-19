# CCUSDT V2 Cross-Market Lead/Lag Pivot

Status: `20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1`.

Guardrail: `research_only_cross_market_lead_lag_no_execution_recommendation_no_alpha_claim`.

## Inputs

- Target: `CCUSDT` from `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1`.
- Leaders: `BTCUSDC,ETHUSDC,SOLUSDC` from `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1`.
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
leader/trigger/fold/horizon: SOLUSDC / leader_ret_5s_follow / expanding_fold3 / 10s
entries:                     1569
gross_mean_bps:              0.9865
cost_mean_bps:               3.9243
net_mean_bps:                -2.9377
net_median_bps:              -3.2672
signal_minus_random_p50_bps: 1.3079
signal_minus_reversed_bps:   1.9731
status:                      cross_market_no_go
```

## Scorecard

| leader_symbol | fold | trigger_class | horizon_sec | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | net_plus2_mean_bps | net_median_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | signal_minus_reversed_bps | sample_pass | economics_pass | controls_pass | cross_market_promote_gate | cross_market_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SOLUSDC | expanding_fold3 | leader_ret_5s_follow | 10 | 1569 | 0.9865 | 3.9243 | -2.9377 | -4.9377 | -3.2672 | 0.0000 | 1.3079 | 1.9731 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold3 | leader_ret_5s_follow | 10 | 1106 | 0.8211 | 3.9220 | -3.1009 | -5.1009 | -3.2560 | 0.0000 | 0.5824 | 1.6422 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold2 | leader_ret_5s_follow | 10 | 635 | 0.9919 | 4.1124 | -3.1206 | -5.1206 | -3.3744 | 0.0000 | 0.8156 | 1.9837 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_ret_5s_follow | 5 | 1165 | 0.8212 | 3.9493 | -3.1282 | -5.1282 | -3.2919 | 0.0000 | 0.7482 | 1.6423 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_ret_5s_follow | 10 | 1165 | 0.7880 | 3.9229 | -3.1350 | -5.1350 | -3.2672 | 0.0000 | 0.4089 | 1.5759 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold3 | leader_ret_5s_follow | 5 | 1569 | 0.7905 | 3.9293 | -3.1388 | -5.1388 | -3.3002 | 0.0000 | 0.7183 | 1.5810 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold3 | leader_ret_1s_follow | 10 | 2619 | 0.6972 | 3.9585 | -3.2613 | -5.2613 | -3.3010 | 0.0000 | 0.2757 | 1.3943 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold3 | leader_ret_1s_follow | 10 | 3709 | 0.6986 | 3.9635 | -3.2648 | -5.2648 | -3.3035 | 0.0000 | 0.4589 | 1.3973 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_5s_follow | 10 | 670 | 0.8470 | 4.1156 | -3.2686 | -5.2686 | -3.3716 | 0.0000 | 0.4953 | 1.6940 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold3 | leader_ret_5s_follow | 5 | 1106 | 0.6734 | 3.9473 | -3.2739 | -5.2739 | -3.2944 | 0.0000 | 0.8111 | 1.3467 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold3 | leader_ret_1s_follow | 5 | 2619 | 0.6475 | 3.9559 | -3.3083 | -5.3083 | -3.3036 | 0.0000 | 0.6420 | 1.2951 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_ret_1s_follow | 10 | 2921 | 0.6239 | 3.9511 | -3.3272 | -5.3272 | -3.3011 | 0.0000 | 0.5496 | 1.2479 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_ret_1s_follow | 5 | 2921 | 0.5474 | 3.9615 | -3.4141 | -5.4141 | -3.7605 | 0.0000 | 0.3620 | 1.0948 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold2 | leader_ret_5s_follow | 5 | 635 | 0.7039 | 4.1233 | -3.4194 | -5.4194 | -3.9192 | 0.0000 | 0.6648 | 1.4077 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold3 | leader_ret_1s_follow | 5 | 3709 | 0.5124 | 3.9671 | -3.4547 | -5.4547 | -3.7909 | 0.0000 | 0.4443 | 1.0248 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold2 | leader_ret_1s_follow | 10 | 1750 | 0.6307 | 4.1262 | -3.4955 | -5.4955 | -3.3773 | 0.0000 | 0.5059 | 1.2614 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold2 | leader_ret_5s_follow | 10 | 1934 | 0.5890 | 4.1165 | -3.5275 | -5.5275 | -3.9154 | 0.0000 | 0.3446 | 1.1779 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_1s_follow | 10 | 1924 | 0.5905 | 4.1564 | -3.5658 | -5.5658 | -3.9185 | 0.0000 | 0.5196 | 1.1811 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_5s_follow | 5 | 670 | 0.5180 | 4.1052 | -3.5872 | -5.5872 | -3.3764 | 0.0000 | 0.3902 | 1.0360 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_5s_follow | 10 | 2021 | 0.5112 | 4.1003 | -3.5892 | -5.5892 | -3.3633 | 0.0000 | 0.4181 | 1.0223 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold2 | leader_ret_1s_follow | 10 | 4103 | 0.4886 | 4.0872 | -3.5986 | -5.5986 | -3.9036 | 0.0000 | 0.5680 | 0.9772 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold1 | leader_ret_5s_follow | 10 | 1906 | 0.4220 | 4.0706 | -3.6487 | -5.6487 | -3.3562 | 0.0000 | 0.3572 | 0.8439 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold2 | leader_ret_5s_follow | 5 | 1934 | 0.4219 | 4.1280 | -3.7061 | -5.7061 | -3.9228 | 0.0000 | 0.2917 | 0.8438 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold2 | leader_ret_1s_follow | 5 | 1750 | 0.4151 | 4.1220 | -3.7068 | -5.7068 | -3.9209 | 0.0000 | 0.1564 | 0.8303 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold1 | leader_ret_5s_follow | 10 | 2377 | 0.3313 | 4.0725 | -3.7412 | -5.7412 | -3.3631 | 0.0000 | 0.2775 | 0.6626 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold2 | leader_ret_1s_follow | 5 | 4103 | 0.3398 | 4.0961 | -3.7563 | -5.7563 | -3.9215 | 0.0000 | 0.3239 | 0.6796 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold1 | leader_ret_5s_follow | 5 | 2377 | 0.2633 | 4.0578 | -3.7945 | -5.7945 | -3.3717 | 0.0000 | 0.1325 | 0.5267 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_1s_follow | 10 | 4897 | 0.3105 | 4.1221 | -3.8116 | -5.8116 | -4.0090 | 0.0000 | 0.1408 | 0.6209 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold2 | leader_ret_1s_follow | 5 | 1924 | 0.3437 | 4.1571 | -3.8135 | -5.8135 | -3.9267 | 0.0000 | 0.3235 | 0.6873 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold1 | leader_ret_5s_follow | 5 | 1906 | 0.2394 | 4.0640 | -3.8246 | -5.8246 | -3.3694 | 0.0000 | 0.1990 | 0.4789 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold1 | leader_ret_1s_follow | 10 | 4572 | 0.2758 | 4.1290 | -3.8532 | -5.8532 | -4.0111 | 0.2000 | 0.1746 | 0.5516 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold2 | leader_microprice_follow | 10 | 1994 | 0.2084 | 4.0734 | -3.8650 | -5.8650 | -3.9359 | 0.0000 | 0.1882 | 0.4169 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_5s_follow | 5 | 2021 | 0.2178 | 4.0969 | -3.8791 | -5.8791 | -4.0045 | 0.0000 | 0.0578 | 0.4357 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold1 | leader_ret_1s_follow | 10 | 6406 | 0.2260 | 4.1127 | -3.8867 | -5.8867 | -4.0100 | 0.0000 | 0.0915 | 0.4520 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold1 | leader_ret_1s_follow | 5 | 4572 | 0.1881 | 4.1238 | -3.9357 | -5.9357 | -4.0135 | 0.0000 | 0.1268 | 0.3762 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold1 | leader_ret_1s_follow | 5 | 4899 | 0.1690 | 4.1147 | -3.9457 | -5.9457 | -4.0135 | 0.0000 | 0.0896 | 0.3380 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold1 | leader_ret_1s_follow | 5 | 6407 | 0.1480 | 4.1049 | -3.9570 | -5.9570 | -4.0131 | 0.0000 | 0.1368 | 0.2959 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold2 | leader_microprice_follow | 5 | 1994 | 0.1309 | 4.0895 | -3.9586 | -5.9586 | -3.9409 | 0.6000 | -0.0868 | 0.2618 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 10 | 31350 | 0.0231 | 3.9911 | -3.9680 | -5.9680 | -3.8994 | 0.8000 | -0.0917 | 0.0462 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold2 | leader_microprice_follow | 10 | 905 | 0.0031 | 3.9990 | -3.9959 | -5.9959 | -3.9182 | 0.4000 | 0.0829 | 0.0063 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 10 | 31932 | 0.0196 | 4.0180 | -3.9984 | -5.9984 | -3.9337 | 0.0000 | 0.2252 | 0.0392 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 5 | 32765 | 0.0017 | 4.0064 | -4.0047 | -6.0047 | -3.9265 | 0.6000 | -0.0281 | 0.0034 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold3 | leader_microprice_follow | 5 | 1567 | 0.0362 | 4.0412 | -4.0050 | -6.0050 | -3.9276 | 0.2000 | 0.1074 | 0.0723 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold3 | leader_microprice_follow | 10 | 1566 | 0.0226 | 4.0345 | -4.0119 | -6.0119 | -3.9017 | 0.6000 | -0.0103 | 0.0452 | True | False | False | False | cross_market_no_go |
| BTCUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 5 | 31936 | 0.0041 | 4.0169 | -4.0127 | -6.0127 | -3.9339 | 0.6000 | -0.0692 | 0.0083 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 5 | 31353 | -0.0302 | 3.9932 | -4.0233 | -6.0233 | -3.9104 | 0.2000 | 0.0510 | -0.0603 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold3 | leader_trade_flow_5s_follow | 10 | 32762 | -0.0348 | 4.0057 | -4.0405 | -6.0405 | -3.9298 | 0.8000 | -0.1960 | -0.0696 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold3 | leader_microprice_follow | 10 | 1417 | 0.0171 | 4.0617 | -4.0446 | -6.0446 | -3.9542 | 1.0000 | -0.3358 | 0.0342 | True | False | False | False | cross_market_no_go |
| SOLUSDC | expanding_fold1 | lag_residual_5s_follow | 5 | 1540 | 0.1223 | 4.1710 | -4.0486 | -6.0486 | -4.0093 | 0.0000 | 0.2000 | 0.2446 | True | False | False | False | cross_market_no_go |
| ETHUSDC | expanding_fold1 | lag_residual_5s_follow | 5 | 1447 | 0.0983 | 4.1514 | -4.0531 | -6.0531 | -4.0121 | 0.8000 | -0.0264 | 0.1965 | True | False | False | False | cross_market_no_go |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_events_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_controls_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_cross_market_summary_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_cross_market_lead_lag.py --target-data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1 --leader-data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1 --target-symbol CCUSDT --leaders "BTCUSDC,ETHUSDC,SOLUSDC" --run-tag 20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1 --threshold-quantiles "0.99" --horizons-sec "5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 5 --control-selected-cap 500 --control-pool-cap 20000
```

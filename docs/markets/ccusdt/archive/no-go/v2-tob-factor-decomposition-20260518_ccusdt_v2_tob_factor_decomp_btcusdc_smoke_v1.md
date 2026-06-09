# CCUSDT V2 Top-Of-Book Factor Decomposition

Status: `20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1`.

Guardrail: `research_only_tob_factor_decomposition_no_execution_recommendation_no_alpha_claim`.

## Decision

Promote-gate rows in source scorecard: `0`.

The top rows show small positive gross movement at best, but the gross move is far below the cost plus `2` bps hurdle.

## Decomposition

| fold | trigger_class | horizon_sec | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | required_gross_for_net2_mean_bps | gross_shortfall_to_net2_mean_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | tob_factor_promote_gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | obi_follow | 10 | 2254 | 0.5944 | 2.0125 | -1.4181 | 4.0125 | -3.4181 | 0.0000 | 0.5872 | False |
| expanding_fold3 | obi_follow | 10 | 1788 | 0.5560 | 2.0127 | -1.4567 | 4.0127 | -3.4567 | 0.0000 | 0.5745 | False |
| expanding_fold2 | obi_follow | 10 | 1706 | 0.5018 | 2.0125 | -1.5107 | 4.0125 | -3.5107 | 0.0000 | 0.5062 | False |
| expanding_fold1 | obi_follow | 5 | 2254 | 0.4165 | 2.0125 | -1.5960 | 4.0125 | -3.5960 | 0.0000 | 0.4092 | False |
| expanding_fold3 | obi_follow | 5 | 1788 | 0.3600 | 2.0126 | -1.6526 | 4.0126 | -3.6526 | 0.0000 | 0.3481 | False |
| expanding_fold2 | obi_follow | 5 | 1707 | 0.3088 | 2.0125 | -1.7037 | 4.0125 | -3.7037 | 0.0000 | 0.2937 | False |
| expanding_fold1 | obi_follow | 1 | 2254 | 0.1262 | 2.0125 | -1.8862 | 4.0125 | -3.8862 | 0.0000 | 0.1285 | False |
| expanding_fold3 | obi_follow | 1 | 1788 | 0.1101 | 2.0126 | -1.9025 | 4.0126 | -3.9025 | 0.0000 | 0.1159 | False |
| expanding_fold2 | obi_follow | 1 | 1708 | 0.0749 | 2.0125 | -1.9375 | 4.0125 | -3.9375 | 0.0000 | 0.0754 | False |
| expanding_fold3 | trade_flow_follow_5s | 1 | 31937 | -0.0071 | 2.0127 | -2.0197 | 4.0127 | -4.0197 | 1.0000 | -0.0074 | False |
| expanding_fold3 | trade_flow_follow_10s | 1 | 17749 | -0.0071 | 2.0126 | -2.0198 | 4.0126 | -4.0198 | 1.0000 | -0.0085 | False |
| expanding_fold2 | trade_flow_follow_10s | 1 | 22400 | -0.0122 | 2.0125 | -2.0247 | 4.0125 | -4.0247 | 1.0000 | -0.0131 | False |
| expanding_fold2 | trade_flow_follow_5s | 1 | 30748 | -0.0159 | 2.0125 | -2.0285 | 4.0125 | -4.0285 | 1.0000 | -0.0168 | False |
| expanding_fold1 | trade_flow_follow_10s | 1 | 18716 | -0.0178 | 2.0125 | -2.0303 | 4.0125 | -4.0303 | 1.0000 | -0.0178 | False |
| expanding_fold3 | trade_flow_follow_5s | 5 | 31936 | -0.0205 | 2.0127 | -2.0332 | 4.0127 | -4.0332 | 1.0000 | -0.0257 | False |
| expanding_fold1 | trade_flow_follow_5s | 1 | 31383 | -0.0223 | 2.0125 | -2.0348 | 4.0125 | -4.0348 | 1.0000 | -0.0231 | False |
| expanding_fold3 | trade_flow_follow_10s | 5 | 17749 | -0.0249 | 2.0126 | -2.0376 | 4.0126 | -4.0376 | 1.0000 | -0.0281 | False |
| expanding_fold3 | trade_flow_follow_5s | 10 | 31932 | -0.0268 | 2.0127 | -2.0395 | 4.0127 | -4.0395 | 1.0000 | -0.0345 | False |
| expanding_fold3 | trade_flow_follow_10s | 10 | 17745 | -0.0330 | 2.0127 | -2.0457 | 4.0127 | -4.0457 | 1.0000 | -0.0428 | False |
| expanding_fold2 | trade_flow_follow_10s | 5 | 22398 | -0.0352 | 2.0125 | -2.0477 | 4.0125 | -4.0477 | 1.0000 | -0.0357 | False |
| expanding_fold2 | trade_flow_follow_5s | 5 | 30746 | -0.0433 | 2.0125 | -2.0558 | 4.0125 | -4.0558 | 1.0000 | -0.0462 | False |
| expanding_fold2 | trade_flow_follow_10s | 10 | 22398 | -0.0584 | 2.0125 | -2.0709 | 4.0125 | -4.0709 | 1.0000 | -0.0617 | False |
| expanding_fold1 | trade_flow_follow_10s | 5 | 18715 | -0.0599 | 2.0125 | -2.0724 | 4.0125 | -4.0724 | 1.0000 | -0.0629 | False |
| expanding_fold2 | trade_flow_follow_5s | 10 | 30745 | -0.0619 | 2.0125 | -2.0744 | 4.0125 | -4.0744 | 1.0000 | -0.0673 | False |
| expanding_fold1 | trade_flow_follow_5s | 5 | 31382 | -0.0693 | 2.0125 | -2.0818 | 4.0125 | -4.0818 | 1.0000 | -0.0689 | False |
| expanding_fold1 | trade_flow_follow_10s | 10 | 18714 | -0.0980 | 2.0125 | -2.1105 | 4.0125 | -4.1105 | 1.0000 | -0.0981 | False |
| expanding_fold1 | trade_flow_follow_5s | 10 | 31382 | -0.1021 | 2.0125 | -2.1146 | 4.0125 | -4.1146 | 1.0000 | -0.1000 | False |
| expanding_fold3 | microprice_follow | 1 | 2031 | -0.1327 | 2.0205 | -2.1532 | 4.0205 | -4.1532 | 1.0000 | -0.1207 | False |
| expanding_fold2 | microprice_follow | 1 | 949 | -0.1460 | 2.0205 | -2.1664 | 4.0205 | -4.1664 | 1.0000 | -0.1399 | False |
| expanding_fold1 | microprice_follow | 1 | 1366 | -0.1711 | 2.0198 | -2.1909 | 4.0198 | -4.1909 | 1.0000 | -0.1642 | False |
| expanding_fold1 | ret_reversal_5s | 1 | 2021 | -0.3121 | 2.0130 | -2.3251 | 4.0130 | -4.3251 | 1.0000 | -0.3100 | False |
| expanding_fold2 | ret_reversal_5s | 1 | 670 | -0.3286 | 2.0129 | -2.3415 | 4.0129 | -4.3415 | 1.0000 | -0.3254 | False |
| expanding_fold2 | microprice_follow | 5 | 949 | -0.3569 | 2.0194 | -2.3763 | 4.0194 | -4.3763 | 1.0000 | -0.3331 | False |
| expanding_fold3 | microprice_follow | 5 | 2031 | -0.3644 | 2.0195 | -2.3839 | 4.0195 | -4.3839 | 1.0000 | -0.3265 | False |
| expanding_fold3 | ret_reversal_5s | 1 | 1165 | -0.3941 | 2.0133 | -2.4074 | 4.0133 | -4.4074 | 1.0000 | -0.3891 | False |
| expanding_fold1 | microprice_follow | 5 | 1366 | -0.4355 | 2.0191 | -2.4546 | 4.0191 | -4.4546 | 1.0000 | -0.3923 | False |
| expanding_fold3 | microprice_follow | 10 | 2031 | -0.5153 | 2.0192 | -2.5345 | 4.0192 | -4.5345 | 1.0000 | -0.4593 | False |
| expanding_fold2 | microprice_follow | 10 | 949 | -0.5383 | 2.0191 | -2.5574 | 4.0191 | -4.5574 | 1.0000 | -0.4575 | False |
| expanding_fold1 | microprice_follow | 10 | 1366 | -0.5716 | 2.0189 | -2.5905 | 4.0189 | -4.5905 | 1.0000 | -0.4915 | False |
| expanding_fold1 | ret_reversal_5s | 5 | 2021 | -0.6806 | 2.0130 | -2.6936 | 4.0130 | -4.6936 | 1.0000 | -0.6948 | False |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tob_factor_decomposition_20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tob_factor_decomposition_20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_tob_factor_decomposition.py --source-run-tag 20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1 --run-tag 20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1
```

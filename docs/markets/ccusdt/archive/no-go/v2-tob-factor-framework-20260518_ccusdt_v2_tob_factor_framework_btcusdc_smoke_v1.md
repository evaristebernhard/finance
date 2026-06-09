# CCUSDT V2 Top-Of-Book Factor Framework

Status: `20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1`.

Guardrail: `research_only_tob_factor_framework_no_execution_recommendation_no_alpha_claim`.

This is a symbol-parameterized top-of-book diagnostic. It is not an executable strategy and does not replace incremental-L2 queue validation.

## Scope

- Symbol: `BTCUSDC`.
- Data root: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1`.
- Panel rows: `1468771`.
- Event rows: `500628`.
- Scorecard rows: `45`.
- Threshold quantiles: `0.99`.
- Horizons sec: `1,5,10`.
- Fee stress bps: `2.0`.
- Matched-random iters: `10`.

## Decision

Promote-gate rows: `0`.

No top-of-book factor row passed the combined sample, economics, stress, matched-control, median, and risk gates.

## Scorecard

| fold | trigger_class | horizon_sec | threshold_quantile | entries | net_mean_bps | net_plus2_mean_bps | net_median_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | sample_pass | economics_pass | controls_pass | tob_factor_promote_gate | tob_factor_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | obi_follow | 10 | 0.9900 | 2254 | -1.4181 | -3.4181 | -1.7538 | 0.0000 | 0.5872 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | obi_follow | 10 | 0.9900 | 1788 | -1.4567 | -3.4567 | -1.8013 | 0.0000 | 0.5745 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | obi_follow | 10 | 0.9900 | 1706 | -1.5107 | -3.5107 | -1.8885 | 0.0000 | 0.5062 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | obi_follow | 5 | 0.9900 | 2254 | -1.5960 | -3.5960 | -1.9260 | 0.0000 | 0.4092 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | obi_follow | 5 | 0.9900 | 1788 | -1.6526 | -3.6526 | -1.9505 | 0.0000 | 0.3481 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | obi_follow | 5 | 0.9900 | 1707 | -1.7037 | -3.7037 | -1.9749 | 0.0000 | 0.2937 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | obi_follow | 1 | 0.9900 | 2254 | -1.8862 | -3.8862 | -2.0123 | 0.0000 | 0.1285 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | obi_follow | 1 | 0.9900 | 1788 | -1.9025 | -3.9025 | -2.0123 | 0.0000 | 0.1159 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | obi_follow | 1 | 0.9900 | 1708 | -1.9375 | -3.9375 | -2.0123 | 0.0000 | 0.0754 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | trade_flow_follow_5s | 1 | 0.9900 | 31937 | -2.0197 | -4.0197 | -2.0124 | 1.0000 | -0.0074 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | trade_flow_follow_10s | 1 | 0.9900 | 17749 | -2.0198 | -4.0198 | -2.0124 | 1.0000 | -0.0085 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | trade_flow_follow_10s | 1 | 0.9900 | 22400 | -2.0247 | -4.0247 | -2.0124 | 1.0000 | -0.0131 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | trade_flow_follow_5s | 1 | 0.9900 | 30748 | -2.0285 | -4.0285 | -2.0124 | 1.0000 | -0.0168 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | trade_flow_follow_10s | 1 | 0.9900 | 18716 | -2.0303 | -4.0303 | -2.0124 | 1.0000 | -0.0178 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | trade_flow_follow_5s | 5 | 0.9900 | 31936 | -2.0332 | -4.0332 | -2.0124 | 1.0000 | -0.0257 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | trade_flow_follow_5s | 1 | 0.9900 | 31383 | -2.0348 | -4.0348 | -2.0124 | 1.0000 | -0.0231 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | trade_flow_follow_10s | 5 | 0.9900 | 17749 | -2.0376 | -4.0376 | -2.0124 | 1.0000 | -0.0281 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | trade_flow_follow_5s | 10 | 0.9900 | 31932 | -2.0395 | -4.0395 | -2.0124 | 1.0000 | -0.0345 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | trade_flow_follow_10s | 10 | 0.9900 | 17745 | -2.0457 | -4.0457 | -2.0124 | 1.0000 | -0.0428 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | trade_flow_follow_10s | 5 | 0.9900 | 22398 | -2.0477 | -4.0477 | -2.0124 | 1.0000 | -0.0357 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | trade_flow_follow_5s | 5 | 0.9900 | 30746 | -2.0558 | -4.0558 | -2.0124 | 1.0000 | -0.0462 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | trade_flow_follow_10s | 10 | 0.9900 | 22398 | -2.0709 | -4.0709 | -2.0124 | 1.0000 | -0.0617 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | trade_flow_follow_10s | 5 | 0.9900 | 18715 | -2.0724 | -4.0724 | -2.0124 | 1.0000 | -0.0629 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | trade_flow_follow_5s | 10 | 0.9900 | 30745 | -2.0744 | -4.0744 | -2.0124 | 1.0000 | -0.0673 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | trade_flow_follow_5s | 5 | 0.9900 | 31382 | -2.0818 | -4.0818 | -2.0124 | 1.0000 | -0.0689 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | trade_flow_follow_10s | 10 | 0.9900 | 18714 | -2.1105 | -4.1105 | -2.0125 | 1.0000 | -0.0981 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | trade_flow_follow_5s | 10 | 0.9900 | 31382 | -2.1146 | -4.1146 | -2.0125 | 1.0000 | -0.1000 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | microprice_follow | 1 | 0.9900 | 2031 | -2.1532 | -4.1532 | -2.0251 | 1.0000 | -0.1207 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | microprice_follow | 1 | 0.9900 | 949 | -2.1664 | -4.1664 | -2.0249 | 1.0000 | -0.1399 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | microprice_follow | 1 | 0.9900 | 1366 | -2.1909 | -4.1909 | -2.0250 | 1.0000 | -0.1642 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | ret_reversal_5s | 1 | 0.9900 | 2021 | -2.3251 | -4.3251 | -2.0615 | 1.0000 | -0.3100 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | ret_reversal_5s | 1 | 0.9900 | 670 | -2.3415 | -4.3415 | -2.0999 | 1.0000 | -0.3254 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | microprice_follow | 5 | 0.9900 | 949 | -2.3763 | -4.3763 | -2.0616 | 1.0000 | -0.3331 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | microprice_follow | 5 | 0.9900 | 2031 | -2.3839 | -4.3839 | -2.0870 | 1.0000 | -0.3265 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | ret_reversal_5s | 1 | 0.9900 | 1165 | -2.4074 | -4.4074 | -2.1238 | 1.0000 | -0.3891 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | microprice_follow | 5 | 0.9900 | 1366 | -2.4546 | -4.4546 | -2.1350 | 1.0000 | -0.3923 | True | False | False | False | tob_factor_no_go |
| expanding_fold3 | microprice_follow | 10 | 0.9900 | 2031 | -2.5345 | -4.5345 | -2.1632 | 1.0000 | -0.4593 | True | False | False | False | tob_factor_no_go |
| expanding_fold2 | microprice_follow | 10 | 0.9900 | 949 | -2.5574 | -4.5574 | -2.1590 | 1.0000 | -0.4575 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | microprice_follow | 10 | 0.9900 | 1366 | -2.5905 | -4.5905 | -2.2341 | 1.0000 | -0.4915 | True | False | False | False | tob_factor_no_go |
| expanding_fold1 | ret_reversal_5s | 5 | 0.9900 | 2021 | -2.6936 | -4.6936 | -2.3446 | 1.0000 | -0.6948 | True | False | False | False | tob_factor_no_go |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tob_factor_panel_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tob_factor_events_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tob_factor_controls_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tob_factor_scorecard_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tob_factor_summary_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_tob_factor_framework.py --data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1 --symbol BTCUSDC --run-tag 20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1 --threshold-quantiles "0.99" --horizons-sec "1,5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 10
```

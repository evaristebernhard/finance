# CCUSDT V2 Absorption/Replenishment Reversal Pivot

Status: `20260518_ccusdt_v2_absorption_reversal_btcusdc_v1`.

Guardrail: `research_only_absorption_reversal_pivot_no_execution_recommendation_no_alpha_claim`.

This is a structurally new entry diagnostic: large aggressive flow that fails to move price and is met by visible top-of-book replenishment. It is not an execution recommendation and does not replace L2 queue/fill validation.

## Scope

- Symbol: `BTCUSDC`.
- Data root: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1`.
- Panel rows: `1468771`.
- Event rows: `59301`.
- Scorecard rows: `54`.
- Threshold quantiles: `0.95,0.975,0.99`.
- Horizons sec: `1,5,10`.
- Fee stress bps: `2.0`.
- Absorption ret quantile: `0.5`.
- Max absorption ret bps: `1.0`.
- Matched-random iters: `50`.
- Min entries: `200`.

## Decision

Promote-gate rows: `0`.

No absorption/replenishment row passed the combined sample, economics, stress, matched-control, median, and risk gates.

## Scorecard

| fold | trigger_class | horizon_sec | threshold_quantile | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | net_plus2_mean_bps | net_median_bps | matched_random_prob_ge_signal | signal_minus_random_p50_bps | sample_pass | economics_pass | controls_pass | absorption_promote_gate | absorption_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | buy_absorption_short | 10 | 0.9750 | 1279 | 0.4497 | 2.0129 | -1.5631 | -3.5631 | -1.8519 | 0.0000 | 0.4848 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 10 | 0.9500 | 2516 | 0.4328 | 2.0128 | -1.5801 | -3.5801 | -1.8642 | 0.0000 | 0.4328 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 5 | 0.9900 | 493 | 0.3755 | 2.0130 | -1.6375 | -3.6375 | -1.8657 | 0.0000 | 0.3918 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 10 | 0.9900 | 493 | 0.3743 | 2.0129 | -1.6386 | -3.6386 | -1.7437 | 0.0000 | 0.4335 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 5 | 0.9750 | 1279 | 0.3462 | 2.0129 | -1.6667 | -3.6667 | -1.9630 | 0.0000 | 0.3539 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 5 | 0.9500 | 2516 | 0.3435 | 2.0128 | -1.6694 | -3.6694 | -1.9630 | 0.0000 | 0.3487 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 5 | 0.9900 | 251 | 0.3297 | 2.0130 | -1.6833 | -3.6833 | -2.0000 | 0.0000 | 0.2915 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 10 | 0.9900 | 241 | 0.3187 | 2.0127 | -1.6940 | -3.6940 | -1.9377 | 0.0000 | 0.3558 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 5 | 0.9900 | 416 | 0.3149 | 2.0130 | -1.6982 | -3.6982 | -1.9815 | 0.0000 | 0.3140 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 1 | 0.9900 | 493 | 0.3049 | 2.0129 | -1.7080 | -3.7080 | -2.0000 | 0.0000 | 0.3146 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 10 | 0.9500 | 2754 | 0.2883 | 2.0128 | -1.7244 | -3.7244 | -1.8643 | 0.0000 | 0.3153 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 10 | 0.9500 | 1369 | 0.2787 | 2.0127 | -1.7340 | -3.7340 | -1.9875 | 0.0000 | 0.3262 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 5 | 0.9500 | 2754 | 0.2723 | 2.0128 | -1.7405 | -3.7405 | -1.9383 | 0.0000 | 0.2825 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 10 | 0.9750 | 1026 | 0.2698 | 2.0132 | -1.7434 | -3.7434 | -1.8943 | 0.0000 | 0.2910 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 10 | 0.9500 | 1992 | 0.2487 | 2.0132 | -1.7645 | -3.7645 | -1.9437 | 0.0000 | 0.2525 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 10 | 0.9750 | 650 | 0.2441 | 2.0127 | -1.7686 | -3.7686 | -1.9507 | 0.0000 | 0.3328 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 5 | 0.9750 | 1026 | 0.2274 | 2.0132 | -1.7858 | -3.7858 | -1.9875 | 0.0000 | 0.2390 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 10 | 0.9750 | 1395 | 0.2176 | 2.0128 | -1.7952 | -3.7952 | -1.9137 | 0.0200 | 0.2310 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 1 | 0.9900 | 416 | 0.2122 | 2.0132 | -1.8010 | -3.8010 | -2.0123 | 0.0000 | 0.2088 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 10 | 0.9900 | 416 | 0.2073 | 2.0130 | -1.8057 | -3.8057 | -1.8425 | 0.0200 | 0.2040 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 5 | 0.9750 | 1395 | 0.1983 | 2.0128 | -1.8145 | -3.8145 | -1.9751 | 0.0000 | 0.2095 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 1 | 0.9750 | 1279 | 0.1955 | 2.0129 | -1.8174 | -3.8174 | -2.0122 | 0.0000 | 0.1998 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 1 | 0.9750 | 1395 | 0.1945 | 2.0128 | -1.8183 | -3.8183 | -2.0123 | 0.0000 | 0.1967 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 5 | 0.9750 | 712 | 0.1889 | 2.0128 | -1.8238 | -3.8238 | -2.0123 | 0.0000 | 0.1728 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 10 | 0.9500 | 1406 | 0.1874 | 2.0127 | -1.8254 | -3.8254 | -2.0000 | 0.0000 | 0.1444 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 5 | 0.9500 | 1406 | 0.1856 | 2.0128 | -1.8272 | -3.8272 | -2.0123 | 0.0000 | 0.1621 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 5 | 0.9500 | 1992 | 0.1808 | 2.0132 | -1.8324 | -3.8324 | -2.0000 | 0.0000 | 0.1838 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 1 | 0.9900 | 522 | 0.1756 | 2.0128 | -1.8372 | -3.8372 | -2.0123 | 0.0000 | 0.1824 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 5 | 0.9500 | 1369 | 0.1723 | 2.0127 | -1.8404 | -3.8404 | -2.0000 | 0.0000 | 0.1985 | True | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 5 | 0.9500 | 1665 | 0.1703 | 2.0131 | -1.8428 | -3.8428 | -2.0123 | 0.0000 | 0.1964 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 1 | 0.9500 | 2754 | 0.1637 | 2.0128 | -1.8491 | -3.8491 | -2.0123 | 0.0000 | 0.1652 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 1 | 0.9500 | 2516 | 0.1564 | 2.0129 | -1.8565 | -3.8565 | -2.0123 | 0.0000 | 0.1542 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 1 | 0.9750 | 1026 | 0.1554 | 2.0133 | -1.8579 | -3.8579 | -2.0123 | 0.0000 | 0.1576 | True | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 10 | 0.9500 | 1665 | 0.1367 | 2.0131 | -1.8764 | -3.8764 | -2.0000 | 0.0000 | 0.1826 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 10 | 0.9900 | 251 | 0.1275 | 2.0128 | -1.8853 | -3.8853 | -1.9752 | 0.4000 | 0.0300 | True | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 1 | 0.9500 | 1992 | 0.1171 | 2.0133 | -1.8962 | -3.8962 | -2.0123 | 0.0000 | 0.1161 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 5 | 0.9750 | 650 | 0.1104 | 2.0127 | -1.9023 | -3.9023 | -1.9875 | 0.0200 | 0.1334 | True | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 1 | 0.9500 | 1665 | 0.1077 | 2.0132 | -1.9055 | -3.9055 | -2.0124 | 0.0000 | 0.1141 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 10 | 0.9900 | 522 | 0.0937 | 2.0128 | -1.9191 | -3.9191 | -2.0061 | 0.3600 | 0.0847 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 10 | 0.9750 | 712 | 0.0915 | 2.0127 | -1.9212 | -3.9212 | -2.0000 | 0.3000 | 0.0437 | True | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 1 | 0.9750 | 787 | 0.0879 | 2.0132 | -1.9253 | -3.9253 | -2.0124 | 0.0000 | 0.0905 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 1 | 0.9900 | 251 | 0.0866 | 2.0129 | -1.9264 | -3.9264 | -2.0123 | 0.0000 | 0.0839 | True | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 5 | 0.9900 | 522 | 0.0843 | 2.0128 | -1.9285 | -3.9285 | -2.0000 | 0.0600 | 0.0906 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 1 | 0.9500 | 1406 | 0.0801 | 2.0128 | -1.9327 | -3.9327 | -2.0124 | 0.0000 | 0.0789 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 1 | 0.9500 | 1369 | 0.0788 | 2.0127 | -1.9340 | -3.9340 | -2.0124 | 0.0000 | 0.0815 | True | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 5 | 0.9750 | 787 | 0.0699 | 2.0131 | -1.9432 | -3.9432 | -2.0123 | 0.0400 | 0.1118 | True | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 1 | 0.9750 | 712 | 0.0694 | 2.0129 | -1.9435 | -3.9435 | -2.0124 | 0.0000 | 0.0648 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 1 | 0.9750 | 650 | 0.0671 | 2.0127 | -1.9457 | -3.9457 | -2.0124 | 0.0000 | 0.0715 | True | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 1 | 0.9900 | 241 | 0.0309 | 2.0127 | -1.9819 | -3.9819 | -2.0124 | 0.2200 | 0.0232 | True | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 1 | 0.9900 | 293 | 0.0260 | 2.0133 | -1.9873 | -3.9873 | -2.0124 | 0.2400 | 0.0187 | True | False | False | False | absorption_no_go |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_panel_20260518_ccusdt_v2_absorption_reversal_btcusdc_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_events_20260518_ccusdt_v2_absorption_reversal_btcusdc_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_controls_20260518_ccusdt_v2_absorption_reversal_btcusdc_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_btcusdc_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_summary_20260518_ccusdt_v2_absorption_reversal_btcusdc_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_absorption_reversal_pivot.py --data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1 --symbol BTCUSDC --run-tag 20260518_ccusdt_v2_absorption_reversal_btcusdc_v1 --threshold-quantiles "0.95,0.975,0.99" --horizons-sec "1,5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --absorption-ret-quantile 0.5 --max-absorption-ret-bps 1 --matched-random-iters 50 --min-entries 200
```

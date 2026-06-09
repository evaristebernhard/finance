# CCUSDT V2 Absorption/Replenishment Reversal Pivot

Status: `20260518_ccusdt_v2_absorption_reversal_pivot_v1`.

Guardrail: `research_only_absorption_reversal_pivot_no_execution_recommendation_no_alpha_claim`.

This is a structurally new entry diagnostic: large aggressive flow that fails to move price and is met by visible top-of-book replenishment. It is not an execution recommendation and does not replace L2 queue/fill validation.

## Scope

- Symbol: `CCUSDT`.
- Data root: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1`.
- Panel rows: `1555177`.
- Event rows: `5001`.
- Scorecard rows: `72`.
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
| expanding_fold3 | buy_absorption_short | 10 | 0.9900 | 26 | 3.9939 | 4.3044 | -0.3104 | -2.3104 | -4.7634 | 0.0000 | 4.0505 | False | False | True | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 5 | 0.9900 | 16 | 3.7269 | 4.4548 | -0.7279 | -2.7279 | -3.6765 | 0.0000 | 3.6843 | False | False | True | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 10 | 0.9900 | 16 | 3.4133 | 4.4336 | -1.0203 | -3.0203 | -3.3463 | 0.0000 | 3.3325 | False | False | True | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 10 | 0.9900 | 46 | 3.0967 | 4.2394 | -1.1427 | -3.1427 | -2.6423 | 0.0000 | 3.0274 | False | False | True | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 10 | 0.9750 | 84 | 2.8045 | 4.3653 | -1.5608 | -3.5608 | -4.4414 | 0.0000 | 2.7348 | False | False | True | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 10 | 0.9750 | 90 | 2.6644 | 4.3475 | -1.6831 | -3.6831 | -4.2536 | 0.0000 | 2.6609 | False | False | True | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 10 | 0.9900 | 9 | 2.1026 | 4.6319 | -2.5294 | -4.5294 | -5.1493 | 0.0800 | 2.1415 | False | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 5 | 0.9900 | 46 | 1.5945 | 4.1758 | -2.5813 | -4.5813 | -4.1688 | 0.0600 | 1.5097 | False | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 10 | 0.9500 | 151 | 1.7986 | 4.4009 | -2.6023 | -4.6023 | -4.4362 | 0.0000 | 1.7004 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 10 | 0.9750 | 22 | 1.9723 | 4.6747 | -2.7025 | -4.7025 | -3.9460 | 0.0200 | 1.9993 | False | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 5 | 0.9750 | 90 | 1.5301 | 4.2738 | -2.7436 | -4.7436 | -4.5030 | 0.0000 | 1.4976 | False | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 5 | 0.9900 | 43 | 2.0121 | 4.7885 | -2.7765 | -4.7765 | -4.0395 | 0.0000 | 1.8530 | False | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 10 | 0.9500 | 160 | 1.1625 | 4.4079 | -3.2453 | -5.2453 | -4.5650 | 0.0000 | 1.3043 | False | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 10 | 0.9900 | 43 | 1.3496 | 4.7158 | -3.3661 | -5.3661 | -4.4242 | 0.1200 | 2.0308 | False | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 5 | 0.9750 | 84 | 0.7245 | 4.3255 | -3.6010 | -5.6010 | -4.9985 | 0.1800 | 0.6882 | False | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 5 | 0.9750 | 42 | 0.7914 | 4.5122 | -3.7207 | -5.7207 | -5.3435 | 0.0200 | 1.0102 | False | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 5 | 0.9500 | 160 | 0.5283 | 4.3936 | -3.8654 | -5.8654 | -4.5627 | 0.0400 | 0.4691 | False | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 5 | 0.9500 | 151 | 0.3636 | 4.3947 | -4.0311 | -6.0311 | -4.6032 | 0.3400 | 0.2352 | False | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 5 | 0.9900 | 26 | 0.1926 | 4.2342 | -4.0415 | -6.0415 | -4.7852 | 0.2800 | 0.4021 | False | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 1 | 0.9750 | 84 | 0.0131 | 4.4390 | -4.4259 | -6.4259 | -4.9805 | 0.6400 | -0.1000 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 5 | 0.9750 | 22 | 0.2481 | 4.6852 | -4.4371 | -6.4371 | -5.1494 | 0.4600 | 0.1911 | False | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 10 | 0.9750 | 42 | 0.1116 | 4.5517 | -4.4401 | -6.4401 | -5.3435 | 0.1800 | 0.3688 | False | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 10 | 0.9750 | 78 | 0.1178 | 4.5869 | -4.4690 | -6.4690 | -4.5552 | 0.3000 | 0.6326 | False | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 1 | 0.9500 | 151 | 0.0232 | 4.5505 | -4.5273 | -6.5273 | -4.9781 | 0.6600 | -0.1212 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 10 | 0.9500 | 42 | 0.1255 | 4.7475 | -4.6219 | -6.6219 | -5.1537 | 0.7000 | -0.2188 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 5 | 0.9900 | 9 | -0.1398 | 4.5618 | -4.7016 | -6.7016 | -5.1495 | 0.5400 | -0.0705 | False | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 5 | 0.9750 | 78 | -0.0677 | 4.6468 | -4.7145 | -6.7145 | -4.6356 | 0.4600 | 0.0359 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 1 | 0.9750 | 22 | -0.1267 | 4.6852 | -4.8119 | -6.8119 | -5.1454 | 0.5600 | -0.0819 | False | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 1 | 0.9750 | 90 | -0.3623 | 4.4808 | -4.8430 | -6.8430 | -4.6304 | 0.8200 | -0.3304 | False | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 5 | 0.9500 | 72 | -0.0850 | 4.7778 | -4.8628 | -6.8628 | -5.3716 | 0.5600 | -0.0683 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 1 | 0.9500 | 42 | -0.1623 | 4.8021 | -4.9644 | -6.9644 | -5.1494 | 0.7800 | -0.1936 | False | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 1 | 0.9900 | 46 | -0.5904 | 4.4146 | -5.0049 | -7.0049 | -4.5740 | 0.9600 | -0.7236 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | buy_absorption_short | 5 | 0.9750 | 22 | -0.4009 | 4.6203 | -5.0212 | -7.0212 | -5.1446 | 0.7600 | -0.4682 | False | False | False | False | absorption_no_go |
| expanding_fold2 | sell_absorption_long | 1 | 0.9500 | 160 | -0.5218 | 4.5697 | -5.0915 | -7.0915 | -4.6869 | 1.0000 | -0.6472 | False | False | False | False | absorption_no_go |
| expanding_fold3 | buy_absorption_short | 1 | 0.9900 | 26 | -0.6619 | 4.4969 | -5.1587 | -7.1587 | -4.5671 | 0.9800 | -0.8702 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | buy_absorption_short | 1 | 0.9500 | 39 | -0.8769 | 4.2953 | -5.1722 | -7.1722 | -4.6139 | 1.0000 | -0.8947 | False | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 1 | 0.9500 | 213 | -0.8431 | 4.3518 | -5.1949 | -7.1949 | -4.6009 | 1.0000 | -0.8440 | True | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 10 | 0.9500 | 72 | -0.5470 | 4.7261 | -5.2731 | -7.2731 | -5.3628 | 0.8800 | -0.5211 | False | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 10 | 0.9500 | 157 | -0.7348 | 4.5699 | -5.3047 | -7.3047 | -5.1982 | 0.7800 | -0.6168 | False | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 1 | 0.9900 | 16 | -0.8584 | 4.4543 | -5.3127 | -7.3127 | -4.6836 | 1.0000 | -0.8345 | False | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 5 | 0.9500 | 157 | -0.7464 | 4.6179 | -5.3642 | -7.3642 | -5.1952 | 0.9400 | -0.6405 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 5 | 0.9500 | 42 | -0.6714 | 4.6995 | -5.3709 | -7.3709 | -5.1496 | 0.8800 | -0.6423 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | buy_absorption_short | 1 | 0.9750 | 22 | -0.8772 | 4.5199 | -5.3971 | -7.3971 | -4.9124 | 0.9600 | -0.7280 | False | False | False | False | absorption_no_go |
| expanding_fold4_oos | sell_absorption_long | 1 | 0.9900 | 9 | -0.7700 | 4.6318 | -5.4018 | -7.4018 | -5.1495 | 0.8800 | -0.5541 | False | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 1 | 0.9750 | 42 | -0.6718 | 4.7360 | -5.4079 | -7.4079 | -5.3570 | 1.0000 | -0.6707 | False | False | False | False | absorption_no_go |
| expanding_fold2 | buy_absorption_short | 1 | 0.9500 | 157 | -0.7565 | 4.7214 | -5.4779 | -7.4779 | -5.1351 | 0.9800 | -0.6923 | False | False | False | False | absorption_no_go |
| expanding_fold1 | buy_absorption_short | 1 | 0.9500 | 72 | -0.6355 | 4.8946 | -5.5300 | -7.5300 | -5.3670 | 1.0000 | -0.7179 | False | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 5 | 0.9750 | 122 | -1.2523 | 4.3205 | -5.5729 | -7.5729 | -4.5037 | 0.9600 | -1.3720 | False | False | False | False | absorption_no_go |
| expanding_fold1 | sell_absorption_long | 10 | 0.9500 | 102 | -0.9022 | 4.6993 | -5.6015 | -7.6015 | -5.3376 | 1.0000 | -0.9884 | False | False | False | False | absorption_no_go |
| expanding_fold3 | sell_absorption_long | 1 | 0.9750 | 122 | -1.2429 | 4.4257 | -5.6686 | -7.6686 | -4.9862 | 1.0000 | -1.2492 | False | False | False | False | absorption_no_go |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_panel_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_events_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_controls_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_absorption_reversal_summary_20260518_ccusdt_v2_absorption_reversal_pivot_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_absorption_reversal_pivot.py --data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt\v1 --symbol CCUSDT --run-tag 20260518_ccusdt_v2_absorption_reversal_pivot_v1 --threshold-quantiles "0.95,0.975,0.99" --horizons-sec "1,5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --absorption-ret-quantile 0.5 --max-absorption-ret-bps 1 --matched-random-iters 50 --min-entries 200
```

# CCUSDT TFI 前验识别：短窗口在线检测

Status: `20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1`.

Guardrail: `research_only_strict_pretrade_identification_no_execution_recommendation_no_alpha_claim`.

Cost mode: `zero_fee`.

If cost mode is `zero_fee`, the upstream path label is rebuilt before scoring as `net := gross` and `cost := 0`; all rolling detectors and gates in this report are then recomputed from those zero-fee prior labels.

这份报告严格区分后验解释和前验识别。每个 entry 的 score 只允许使用：entry 前可见字段，以及在该 entry 时间之前已经过 60s timeout、可闭合的历史 entry 标签。当前 entry 的未来 `gross/net` 只在评估阶段使用。

执行权重口径使用已锁定的 `weak_overlay_rank12`：base bucket weights 加上 entry 前可见的 `frames_since_mid_change` 高 10% overlay，历史 Fold3 阈值为 `59.8000`。

## 方法

对每个新 entry，取此前已经闭合的 last-N entries，N 为 `5/10/20/30/50/100`，计算：

```text
roll_mean_net_N
roll_gross_cost_ratio_N = mean(X) / mean(C)
roll_gt2_rate_N = P(Y > 2bps)
roll_pos_abs_ratio_N = sum(Y+) / abs(sum(Y-))
roll_pi_N = (roll_mean_net_N - Fold1_mean) / (Fold3_mean - Fold1_mean)
```

这不是用当天最终结果反推状态，而是在每个 entry 前只看已闭合样本。它对应实盘里的一个很短 regime detector。

## OOS Baseline

| scope | entries | exposure_units | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate | pos_over_abs_neg |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OOS_2026_05_16 | 261 | 163.0000 | 380.6898 | 2.3355 | 0.4571 | 0.4080 | 1.7234 |
| OOS_2026_05_17 | 199 | 122.0000 | 541.4113 | 4.4378 | 0.5574 | 0.3402 | 3.1768 |
| OOS_combined | 460 | 285.0000 | 922.1011 | 3.2354 | 0.5000 | 0.3789 | 2.1899 |

## 短窗口 Detector：OOS Combined Top

| gate | entries | select_rate | exposure_units | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate | pos_over_abs_neg | gt2_lift_vs_baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gate_r5_and_frames_q90 | 26 | 0.0565 | 43.5000 | 355.6935 | 8.1769 | 0.6437 | 0.1724 | 13.2809 | 1.2874 |
| gate_frames_q90 | 37 | 0.0804 | 66.0000 | 407.0254 | 6.1671 | 0.5682 | 0.2348 | 7.7065 | 1.1364 |
| gate_frames_q80 | 68 | 0.1478 | 89.0000 | 490.7881 | 5.5145 | 0.5506 | 0.2978 | 5.2572 | 1.1011 |
| gate_r5_and_spread_low_q25 | 60 | 0.1304 | 45.5000 | 209.2958 | 4.5999 | 0.4945 | 0.3297 | 4.4301 | 0.9890 |
| gate_spread_low_q25 | 104 | 0.2261 | 76.0000 | 318.6254 | 4.1924 | 0.4868 | 0.3421 | 3.4909 | 0.9737 |
| gate_r_n5 | 256 | 0.5565 | 163.0000 | 675.4510 | 4.1439 | 0.5123 | 0.3650 | 3.0242 | 1.0245 |
| gate_pibe_n5 | 287 | 0.6239 | 184.5000 | 757.0076 | 4.1030 | 0.5312 | 0.3577 | 2.7280 | 1.0623 |
| gate_r_n10 | 336 | 0.7304 | 214.0000 | 877.7041 | 4.1014 | 0.5070 | 0.3645 | 2.9105 | 1.0140 |
| gate_hot_n5 | 306 | 0.6652 | 199.0000 | 791.4312 | 3.9770 | 0.5226 | 0.3518 | 2.8404 | 1.0452 |
| gate_r5_or_frames_q90 | 267 | 0.5804 | 185.5000 | 726.7830 | 3.9180 | 0.5013 | 0.3639 | 2.9889 | 1.0027 |
| gate_pibe_n20 | 343 | 0.7457 | 219.0000 | 854.5057 | 3.9019 | 0.4977 | 0.3767 | 2.7371 | 0.9954 |
| gate_pi2_n5 | 218 | 0.4739 | 132.0000 | 514.9685 | 3.9013 | 0.5189 | 0.3864 | 2.4275 | 1.0379 |
| gate_pi2_n50 | 240 | 0.5217 | 143.0000 | 545.5142 | 3.8148 | 0.5035 | 0.3986 | 2.6607 | 1.0070 |
| gate_pibe_n10 | 297 | 0.6457 | 188.5000 | 714.0140 | 3.7879 | 0.5040 | 0.3740 | 2.5881 | 1.0080 |
| gate_pi2_n10 | 223 | 0.4848 | 135.5000 | 497.4936 | 3.6715 | 0.5166 | 0.3948 | 2.3234 | 1.0332 |
| gate_r_n20 | 395 | 0.8587 | 248.5000 | 885.8283 | 3.5647 | 0.4970 | 0.3783 | 2.4637 | 0.9940 |
| gate_hot_n20 | 364 | 0.7913 | 231.5000 | 811.3442 | 3.5047 | 0.4968 | 0.3780 | 2.3925 | 0.9935 |
| gate_hot_n10 | 311 | 0.6761 | 196.5000 | 687.7425 | 3.5000 | 0.5038 | 0.3766 | 2.3908 | 1.0076 |
| gate_pibe_n50 | 340 | 0.7391 | 210.5000 | 736.7231 | 3.4999 | 0.5012 | 0.3729 | 2.5565 | 1.0024 |
| gate_pi2_n100 | 276 | 0.6000 | 175.5000 | 602.6491 | 3.4339 | 0.4957 | 0.3675 | 2.7090 | 0.9915 |

## 短窗口 + 当前队列状态交叉

| scope | gate | entries | select_rate | exposure_units | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OOS_2026_05_16 | gate_r5_and_frames_q90 | 14 | 0.0536 | 26.5000 | 151.0505 | 5.7000 | 0.4717 | 0.2453 |
| OOS_2026_05_16 | gate_frames_q90 | 21 | 0.0805 | 40.0000 | 217.0255 | 5.4256 | 0.5000 | 0.2500 |
| OOS_2026_05_16 | gate_frames_q80 | 43 | 0.1648 | 54.0000 | 226.7960 | 4.1999 | 0.4815 | 0.3333 |
| OOS_2026_05_16 | gate_spread_low_q25 | 63 | 0.2414 | 50.0000 | 170.9947 | 3.4199 | 0.4400 | 0.3400 |
| OOS_2026_05_16 | gate_r5_or_frames_q90 | 151 | 0.5785 | 106.5000 | 326.6008 | 3.0667 | 0.4507 | 0.3944 |
| OOS_2026_05_17 | gate_r5_and_frames_q90 | 12 | 0.0603 | 17.0000 | 204.6430 | 12.0378 | 0.9118 | 0.0588 |
| OOS_2026_05_17 | gate_frames_q80 | 25 | 0.1256 | 35.0000 | 263.9921 | 7.5426 | 0.6571 | 0.2429 |
| OOS_2026_05_17 | gate_frames_q90 | 16 | 0.0804 | 26.0000 | 190.0000 | 7.3077 | 0.6731 | 0.2115 |
| OOS_2026_05_17 | gate_spread_low_q25 | 41 | 0.2060 | 26.0000 | 147.6307 | 5.6781 | 0.5769 | 0.3462 |
| OOS_2026_05_17 | gate_r5_or_frames_q90 | 116 | 0.5829 | 79.0000 | 400.1822 | 5.0656 | 0.5696 | 0.3228 |
| OOS_combined | gate_r5_and_frames_q90 | 26 | 0.0565 | 43.5000 | 355.6935 | 8.1769 | 0.6437 | 0.1724 |
| OOS_combined | gate_frames_q90 | 37 | 0.0804 | 66.0000 | 407.0254 | 6.1671 | 0.5682 | 0.2348 |
| OOS_combined | gate_frames_q80 | 68 | 0.1478 | 89.0000 | 490.7881 | 5.5145 | 0.5506 | 0.2978 |
| OOS_combined | gate_spread_low_q25 | 104 | 0.2261 | 76.0000 | 318.6254 | 4.1924 | 0.4868 | 0.3421 |
| OOS_combined | gate_r5_or_frames_q90 | 267 | 0.5804 | 185.5000 | 726.7830 | 3.9180 | 0.5013 | 0.3639 |

## 分日 Top

| scope | gate | entries | select_rate | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OOS_2026_05_16 | gate_r5_and_frames_q90 | 14 | 0.0536 | 151.0505 | 5.7000 | 0.4717 | 0.2453 |
| OOS_2026_05_16 | gate_frames_q90 | 21 | 0.0805 | 217.0255 | 5.4256 | 0.5000 | 0.2500 |
| OOS_2026_05_16 | gate_frames_q80 | 43 | 0.1648 | 226.7960 | 4.1999 | 0.4815 | 0.3333 |
| OOS_2026_05_16 | gate_spread_low_q25 | 63 | 0.2414 | 170.9947 | 3.4199 | 0.4400 | 0.3400 |
| OOS_2026_05_16 | gate_pibe_n20 | 171 | 0.6552 | 379.0658 | 3.3251 | 0.4430 | 0.4123 |
| OOS_2026_05_16 | gate_hot_n5 | 160 | 0.6130 | 345.4026 | 3.1688 | 0.4541 | 0.3899 |
| OOS_2026_05_16 | gate_r5_or_frames_q90 | 151 | 0.5785 | 326.6008 | 3.0667 | 0.4507 | 0.3944 |
| OOS_2026_05_16 | gate_r5_and_spread_low_q25 | 34 | 0.1303 | 86.8067 | 3.0458 | 0.3860 | 0.3860 |
| OOS_2026_05_16 | gate_pibe_n10 | 157 | 0.6015 | 295.3119 | 2.9239 | 0.4455 | 0.4208 |
| OOS_2026_05_16 | gate_r_n10 | 179 | 0.6858 | 339.7219 | 2.9161 | 0.4464 | 0.4034 |
| OOS_2026_05_16 | gate_pibe_n5 | 153 | 0.5862 | 282.9442 | 2.8294 | 0.4400 | 0.4250 |
| OOS_2026_05_16 | gate_r_n5 | 144 | 0.5517 | 260.6258 | 2.8024 | 0.4355 | 0.4140 |
| OOS_2026_05_16 | gate_hot_n10 | 160 | 0.6130 | 279.9382 | 2.7047 | 0.4493 | 0.4106 |
| OOS_2026_05_16 | gate_pi2_n10 | 105 | 0.4023 | 166.5989 | 2.6656 | 0.4480 | 0.4960 |
| OOS_2026_05_16 | gate_r_n20 | 202 | 0.7739 | 344.5817 | 2.6609 | 0.4324 | 0.4247 |
| OOS_2026_05_16 | gate_pi2_n5 | 99 | 0.3793 | 158.9609 | 2.6493 | 0.4083 | 0.4750 |
| OOS_2026_05_16 | gate_hot_n20 | 180 | 0.6897 | 290.7384 | 2.4849 | 0.4316 | 0.4274 |
| OOS_2026_05_16 | gate_r_n30 | 203 | 0.7778 | 301.2283 | 2.3351 | 0.4302 | 0.4380 |
| OOS_2026_05_16 | gate_hot_n30 | 183 | 0.7011 | 273.1921 | 2.3250 | 0.4340 | 0.4213 |
| OOS_2026_05_16 | gate_pibe_n30 | 166 | 0.6360 | 229.5378 | 2.2394 | 0.4146 | 0.4829 |
| OOS_2026_05_16 | gate_pibe_n50 | 146 | 0.5594 | 201.7251 | 2.2168 | 0.4231 | 0.4176 |
| OOS_2026_05_16 | gate_pi2_n100 | 94 | 0.3602 | 113.6760 | 1.7762 | 0.3984 | 0.4219 |
| OOS_2026_05_16 | gate_pi2_n50 | 89 | 0.3410 | 84.5548 | 1.7434 | 0.3711 | 0.5258 |
| OOS_2026_05_16 | gate_pi2_n20 | 89 | 0.3410 | 92.4291 | 1.7116 | 0.3796 | 0.5278 |
| OOS_2026_05_16 | gate_r_n50 | 208 | 0.7969 | 205.2422 | 1.5549 | 0.4280 | 0.4394 |
| OOS_2026_05_16 | gate_hot_n50 | 208 | 0.7969 | 205.2422 | 1.5549 | 0.4280 | 0.4394 |
| OOS_2026_05_16 | gate_r_n100 | 229 | 0.8774 | 209.6326 | 1.4558 | 0.4410 | 0.4306 |
| OOS_2026_05_16 | gate_hot_n100 | 229 | 0.8774 | 209.6326 | 1.4558 | 0.4410 | 0.4306 |
| OOS_2026_05_16 | gate_pibe_n100 | 126 | 0.4828 | 96.4749 | 1.2059 | 0.3937 | 0.4437 |
| OOS_2026_05_16 | gate_pi2_n30 | 95 | 0.3640 | 59.0128 | 1.0828 | 0.3670 | 0.4954 |

## Entry-Time Static Feature Gates

这些 gate 只用当前 entry 前字段，阈值来自历史样本分位数，不用 OOS 结果调参。

| gate | entries | select_rate | hist_threshold | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| static_frames_since_mid_change_high_q0.9 | 37 | 0.0804 | 31.0000 | 407.0254 | 6.1671 | 0.5682 | 0.2348 |
| static_frames_since_mid_change_high_q0.8 | 68 | 0.1478 | 4.0000 | 490.7881 | 5.5145 | 0.5506 | 0.2978 |
| static_past_event_25_bps_abs_low_q0.5 | 191 | 0.4152 | 0.3123 | 637.0600 | 4.2330 | 0.5216 | 0.3555 |
| static_entry_spread_bps_low_q0.25 | 104 | 0.2261 | 1.2987 | 318.6254 | 4.1924 | 0.4868 | 0.3421 |
| static_trade_window_count_low_q0.5 | 343 | 0.7457 | 1.0000 | 778.5963 | 3.5471 | 0.4806 | 0.3850 |
| static_entry_spread_bps_low_q0.5 | 241 | 0.5239 | 2.0094 | 532.9858 | 3.3733 | 0.4747 | 0.3703 |
| static_trade_window_count_high_q0.75 | 460 | 1.0000 | 1.0000 | 922.1011 | 3.2354 | 0.5000 | 0.3789 |

## 结论

短窗口前验识别有初步信号：最高精度 gate `gate_r5_and_frames_q90` 在 OOS combined 选择 26 entries，weighted mean `8.1769` bps，gt2 rate `0.6437`，相对 baseline gt2 lift `1.2874`。 覆盖更大的纯短窗口 detector 是 `gate_r_n5`，选择 256 entries，weighted mean `4.1439` bps；这更适合做状态 sizing。这说明 regime 识别可能确实很短，但高精度 gate 样本很少；它应作为 sizing/quality layer，不应替代全部互斥 bucket。

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_scored_entries_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_gate_scorecard_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_static_feature_scorecard_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_identification_summary_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1.json`

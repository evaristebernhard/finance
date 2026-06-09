# CCUSDT TFI 前验识别：短窗口在线检测

Status: `20260518_ccusdt_v1_tfi_pretrade_identification_v1`.

Guardrail: `research_only_strict_pretrade_identification_no_execution_recommendation_no_alpha_claim`.

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
| OOS_2026_05_16 | 261 | 163.0000 | 39.2337 | 0.2407 | 0.4141 | 0.5613 | 1.0570 |
| OOS_2026_05_17 | 199 | 122.0000 | 280.9097 | 2.3025 | 0.5123 | 0.4508 | 1.8029 |
| OOS_combined | 460 | 285.0000 | 320.1434 | 1.1233 | 0.4561 | 0.5140 | 1.3085 |

## 短窗口 Detector：OOS Combined Top

| gate | entries | select_rate | exposure_units | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate | pos_over_abs_neg | gt2_lift_vs_baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gate_r5_and_frames_q90 | 27 | 0.0587 | 44.0000 | 252.9276 | 5.7484 | 0.5568 | 0.4432 | 4.9822 | 1.2207 |
| gate_frames_q90 | 37 | 0.0804 | 66.0000 | 273.6677 | 4.1465 | 0.5379 | 0.4621 | 3.6134 | 1.1792 |
| gate_frames_q80 | 68 | 0.1478 | 89.0000 | 307.5672 | 3.4558 | 0.5281 | 0.4719 | 2.6789 | 1.1577 |
| gate_spread_low_q25 | 104 | 0.2261 | 76.0000 | 182.3316 | 2.3991 | 0.4868 | 0.5132 | 1.9978 | 1.0673 |
| gate_r_n5 | 250 | 0.5435 | 161.5000 | 372.7340 | 2.3080 | 0.4892 | 0.4799 | 1.7442 | 1.0724 |
| gate_combo_n5 | 250 | 0.5435 | 161.5000 | 372.7340 | 2.3080 | 0.4892 | 0.4799 | 1.7442 | 1.0724 |
| gate_r5_or_frames_q90 | 260 | 0.5652 | 183.5000 | 393.4740 | 2.1443 | 0.4905 | 0.4823 | 1.7259 | 1.0752 |
| gate_pibe_n5 | 284 | 0.6174 | 185.0000 | 386.2961 | 2.0881 | 0.4919 | 0.4784 | 1.6690 | 1.0784 |
| gate_r5_and_spread_low_q25 | 65 | 0.1413 | 51.0000 | 104.5489 | 2.0500 | 0.5000 | 0.5000 | 1.7611 | 1.0962 |
| gate_pi2_n5 | 215 | 0.4674 | 134.0000 | 264.0147 | 1.9703 | 0.4776 | 0.4851 | 1.5538 | 1.0471 |
| gate_rho_n5 | 261 | 0.5674 | 167.0000 | 324.1796 | 1.9412 | 0.4880 | 0.4820 | 1.5800 | 1.0699 |
| gate_rho_n10 | 279 | 0.6065 | 173.5000 | 323.0297 | 1.8618 | 0.4870 | 0.4813 | 1.5487 | 1.0677 |
| gate_r_n10 | 279 | 0.6065 | 173.5000 | 323.0297 | 1.8618 | 0.4870 | 0.4813 | 1.5487 | 1.0677 |
| gate_combo_n10 | 279 | 0.6065 | 173.5000 | 323.0297 | 1.8618 | 0.4870 | 0.4813 | 1.5487 | 1.0677 |
| gate_pibe_n20 | 338 | 0.7348 | 216.5000 | 387.9630 | 1.7920 | 0.4573 | 0.5104 | 1.5663 | 1.0025 |
| gate_pi2_n10 | 223 | 0.4848 | 134.0000 | 217.8525 | 1.6258 | 0.4813 | 0.4851 | 1.4306 | 1.0553 |
| gate_hot_n5 | 243 | 0.5283 | 152.5000 | 247.2831 | 1.6215 | 0.4623 | 0.5049 | 1.4599 | 1.0135 |
| gate_hot_n20 | 252 | 0.5478 | 164.5000 | 266.5165 | 1.6202 | 0.4286 | 0.5471 | 1.4937 | 0.9396 |
| gate_pibe_n10 | 297 | 0.6457 | 188.0000 | 297.8467 | 1.5843 | 0.4628 | 0.5027 | 1.4636 | 1.0145 |
| gate_rho_n20 | 312 | 0.6783 | 197.5000 | 311.2267 | 1.5758 | 0.4304 | 0.5418 | 1.4663 | 0.9435 |

## 短窗口 + 当前队列状态交叉

| scope | gate | entries | select_rate | exposure_units | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OOS_2026_05_16 | gate_r5_and_frames_q90 | 14 | 0.0536 | 25.0000 | 129.9631 | 5.1985 | 0.3800 | 0.6200 |
| OOS_2026_05_16 | gate_frames_q90 | 21 | 0.0805 | 40.0000 | 139.8300 | 3.4957 | 0.4500 | 0.5500 |
| OOS_2026_05_16 | gate_frames_q80 | 43 | 0.1648 | 54.0000 | 119.4324 | 2.2117 | 0.4444 | 0.5556 |
| OOS_2026_05_16 | gate_spread_low_q25 | 63 | 0.2414 | 50.0000 | 82.6585 | 1.6532 | 0.4400 | 0.5600 |
| OOS_2026_05_16 | gate_r5_or_frames_q90 | 138 | 0.5287 | 101.5000 | 97.8747 | 0.9643 | 0.4236 | 0.5567 |
| OOS_2026_05_17 | gate_r5_and_frames_q90 | 13 | 0.0653 | 19.0000 | 122.9646 | 6.4718 | 0.7895 | 0.2105 |
| OOS_2026_05_17 | gate_frames_q80 | 25 | 0.1256 | 35.0000 | 188.1348 | 5.3753 | 0.6571 | 0.3429 |
| OOS_2026_05_17 | gate_frames_q90 | 16 | 0.0804 | 26.0000 | 133.8377 | 5.1476 | 0.6731 | 0.3269 |
| OOS_2026_05_17 | gate_spread_low_q25 | 41 | 0.2060 | 26.0000 | 99.6731 | 3.8336 | 0.5769 | 0.4231 |
| OOS_2026_05_17 | gate_r5_or_frames_q90 | 122 | 0.6131 | 82.0000 | 295.5993 | 3.6049 | 0.5732 | 0.3902 |
| OOS_combined | gate_r5_and_frames_q90 | 27 | 0.0587 | 44.0000 | 252.9276 | 5.7484 | 0.5568 | 0.4432 |
| OOS_combined | gate_frames_q90 | 37 | 0.0804 | 66.0000 | 273.6677 | 4.1465 | 0.5379 | 0.4621 |
| OOS_combined | gate_frames_q80 | 68 | 0.1478 | 89.0000 | 307.5672 | 3.4558 | 0.5281 | 0.4719 |
| OOS_combined | gate_spread_low_q25 | 104 | 0.2261 | 76.0000 | 182.3316 | 2.3991 | 0.4868 | 0.5132 |
| OOS_combined | gate_r5_or_frames_q90 | 260 | 0.5652 | 183.5000 | 393.4740 | 2.1443 | 0.4905 | 0.4823 |

## 分日 Top

| scope | gate | entries | select_rate | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OOS_2026_05_16 | gate_r5_and_frames_q90 | 14 | 0.0536 | 129.9631 | 5.1985 | 0.3800 | 0.6200 |
| OOS_2026_05_16 | gate_frames_q90 | 21 | 0.0805 | 139.8300 | 3.4957 | 0.4500 | 0.5500 |
| OOS_2026_05_16 | gate_frames_q80 | 43 | 0.1648 | 119.4324 | 2.2117 | 0.4444 | 0.5556 |
| OOS_2026_05_16 | gate_spread_low_q25 | 63 | 0.2414 | 82.6585 | 1.6532 | 0.4400 | 0.5600 |
| OOS_2026_05_16 | gate_hot_n20 | 116 | 0.4444 | 100.8536 | 1.3013 | 0.3613 | 0.6194 |
| OOS_2026_05_16 | gate_pibe_n20 | 170 | 0.6513 | 135.2098 | 1.1913 | 0.4097 | 0.5683 |
| OOS_2026_05_16 | gate_rho_n10 | 145 | 0.5556 | 95.3645 | 1.0715 | 0.4326 | 0.5337 |
| OOS_2026_05_16 | gate_r_n10 | 145 | 0.5556 | 95.3645 | 1.0715 | 0.4326 | 0.5337 |
| OOS_2026_05_16 | gate_combo_n10 | 145 | 0.5556 | 95.3645 | 1.0715 | 0.4326 | 0.5337 |
| OOS_2026_05_16 | gate_r_n5 | 131 | 0.5019 | 88.0078 | 1.0174 | 0.3988 | 0.5780 |
| OOS_2026_05_16 | gate_combo_n5 | 131 | 0.5019 | 88.0078 | 1.0174 | 0.3988 | 0.5780 |
| OOS_2026_05_16 | gate_pi2_n5 | 97 | 0.3716 | 63.5282 | 1.0165 | 0.3760 | 0.5920 |
| OOS_2026_05_16 | gate_r5_or_frames_q90 | 138 | 0.5287 | 97.8747 | 0.9643 | 0.4236 | 0.5567 |
| OOS_2026_05_16 | gate_pibe_n5 | 150 | 0.5747 | 96.4109 | 0.9593 | 0.4030 | 0.5721 |
| OOS_2026_05_16 | gate_hot_n10 | 116 | 0.4444 | 68.9861 | 0.9515 | 0.4414 | 0.5241 |
| OOS_2026_05_16 | gate_hot_n5 | 125 | 0.4789 | 75.2354 | 0.9231 | 0.3804 | 0.5951 |
| OOS_2026_05_16 | gate_rho_n5 | 133 | 0.5096 | 73.7459 | 0.8428 | 0.4000 | 0.5771 |
| OOS_2026_05_16 | gate_rho_n20 | 155 | 0.5939 | 80.1903 | 0.8019 | 0.3500 | 0.6250 |
| OOS_2026_05_16 | gate_r_n20 | 155 | 0.5939 | 80.1903 | 0.8019 | 0.3500 | 0.6250 |
| OOS_2026_05_16 | gate_combo_n20 | 155 | 0.5939 | 80.1903 | 0.8019 | 0.3500 | 0.6250 |
| OOS_2026_05_16 | gate_pi2_n10 | 106 | 0.4061 | 40.4534 | 0.6421 | 0.3968 | 0.5635 |
| OOS_2026_05_16 | gate_pibe_n10 | 157 | 0.6015 | 63.3705 | 0.6306 | 0.4030 | 0.5622 |
| OOS_2026_05_16 | gate_r5_and_spread_low_q25 | 38 | 0.1456 | 20.2632 | 0.6049 | 0.4328 | 0.5672 |
| OOS_2026_05_16 | gate_rho_n30 | 152 | 0.5824 | 46.0775 | 0.5008 | 0.3913 | 0.5870 |
| OOS_2026_05_16 | gate_r_n30 | 152 | 0.5824 | 46.0775 | 0.5008 | 0.3913 | 0.5870 |
| OOS_2026_05_16 | gate_combo_n30 | 152 | 0.5824 | 46.0775 | 0.5008 | 0.3913 | 0.5870 |
| OOS_2026_05_16 | gate_pibe_n30 | 167 | 0.6398 | 43.1754 | 0.4112 | 0.3857 | 0.5952 |
| OOS_2026_05_16 | gate_hot_n30 | 126 | 0.4828 | 30.1486 | 0.3967 | 0.4211 | 0.5658 |
| OOS_2026_05_16 | gate_pibe_n50 | 144 | 0.5517 | 20.4570 | 0.2325 | 0.4148 | 0.5682 |
| OOS_2026_05_16 | gate_rho_n50 | 124 | 0.4751 | 13.9096 | 0.1932 | 0.3889 | 0.5972 |

## Entry-Time Static Feature Gates

这些 gate 只用当前 entry 前字段，阈值来自历史样本分位数，不用 OOS 结果调参。

| gate | entries | select_rate | hist_threshold | weighted_total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| static_frames_since_mid_change_high_q0.9 | 37 | 0.0804 | 31.0000 | 273.6677 | 4.1465 | 0.5379 | 0.4621 |
| static_frames_since_mid_change_high_q0.8 | 68 | 0.1478 | 4.0000 | 307.5672 | 3.4558 | 0.5281 | 0.4719 |
| static_entry_spread_bps_low_q0.25 | 104 | 0.2261 | 1.2987 | 182.3316 | 2.3991 | 0.4868 | 0.5132 |
| static_past_event_25_bps_abs_low_q0.5 | 191 | 0.4152 | 0.3123 | 319.9334 | 2.1258 | 0.4784 | 0.4950 |
| static_entry_spread_bps_low_q0.5 | 241 | 0.5239 | 2.0094 | 237.5917 | 1.5037 | 0.4652 | 0.5285 |
| static_trade_window_count_low_q0.5 | 343 | 0.7457 | 1.0000 | 319.0232 | 1.4534 | 0.4419 | 0.5330 |
| static_trade_window_count_high_q0.75 | 460 | 1.0000 | 1.0000 | 320.1434 | 1.1233 | 0.4561 | 0.5140 |

## 结论

短窗口前验识别有初步信号：最高精度 gate `gate_r5_and_frames_q90` 在 OOS combined 选择 27 entries，weighted mean `5.7484` bps，gt2 rate `0.5568`，相对 baseline gt2 lift `1.2207`。 覆盖更大的纯短窗口 detector 是 `gate_r_n5`，选择 250 entries，weighted mean `2.3080` bps；这更适合做状态 sizing。这说明 regime 识别可能确实很短，但高精度 gate 样本很少；它应作为 sizing/quality layer，不应替代全部互斥 bucket。

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_gate_scorecard_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_static_feature_scorecard_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_identification_summary_20260518_ccusdt_v1_tfi_pretrade_identification_v1.json`

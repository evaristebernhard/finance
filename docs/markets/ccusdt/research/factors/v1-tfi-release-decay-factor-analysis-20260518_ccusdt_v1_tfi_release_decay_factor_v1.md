# CCUSDT TFI Release/Decay Factor Analysis

Status: `20260518_ccusdt_v1_tfi_release_decay_factor_v1`.

Guardrail: `research_only_release_decay_factor_analysis_no_execution_recommendation`.

This report replaces the blunt 60s terminal read with a path read: whether an entry releases first, and whether that release decays before the 60s mark.

## Labels

For entry direction $s_i$, signed path is:

$$
R_i(\tau)=s_i\,10^4\log\frac{M_{t_i+\tau}}{M_{t_i}}.
$$

Release and decay labels are:

$$
\mathrm{MFE}_i(h)=\max_{0<\tau\le h}R_i(\tau),\qquad D_i(60)=\mathrm{MFE}_i(60)-R_i(60).
$$

The key failure mode is:

$$
\mathrm{MFE}_i(10)\ge 5\ \mathrm{bps},\qquad R_i(60)<0.
$$

## Scope

- Rebuilt path entries: `1455`.
- Rebuilt dates: `2026-05-04, 2026-05-05, 2026-05-06, 2026-05-07, 2026-05-08, 2026-05-09, 2026-05-10, 2026-05-11, 2026-05-12, 2026-05-13, 2026-05-14, 2026-05-15`.
- Missing panel dates are skipped; in this workspace v3 panel is present through `2026-05-15`.

## Main Read

1. Mean MFE is `2.5668` bps at 5s, `3.6668` bps at 10s, and `9.9293` bps at 60s.
2. Mean 60s terminal return is `4.2577` bps, while mean 60s decay from peak is `5.6716` bps.
3. `P(MFE_10>=5bps)` is `0.2694`; `P(MFE_10>=5bps and R_60<0)` is `0.0632`.
4. Best entry-time release factor by absolute Spearman is `log_opp_depth25_quote` with Spearman `-0.2998` against `MFE_10`.
5. Conditional on early release, best entry-time decay factor is `log_opp_depth25_quote` with Spearman `-0.1986` against `D_60`.
6. Conditional on early release, best early-path decay factor is `signed_tfi_mean_5_20s` with Spearman `-0.3370` against `D_60`.

Interpretation: this is still mostly factor analysis, not a complicated latent model. The important shift is that the factor target is no longer only $R(60)$. We now ask which factors predict `release`, and which factors warn that release is already decaying.

The first-principles read is simple:

- Low opposite-side depth / low absorption threshold predicts faster release. This shows up as negative Spearman for `log_opp_depth25_quote`, `log_opp_depth5_quote`, and `Theta_t` against `MFE_10`.
- The same low-depth condition also predicts larger decay after early release. That means part of the edge is a liquidity-vacuum release, not necessarily persistent order-flow continuation.
- After release has happened, the useful dynamic factor is sustained signed flow from 5s to 20s. Higher `signed_tfi_mean_5_20s`, `signed_mlofi5_mean_5_20s`, and `signed_ofi_mean_5_20s` correspond to lower `D_60`.
- Queue imbalance is more ambiguous than flow: in this pass, high signed queue imbalance after release is associated with more decay, so queue shape alone should not be treated as continuation without replenishment/depletion context.

## Entry Factors For 10s Release

| feature | rows | spearman | bottom_target_mean | top_target_mean | top_minus_bottom_target | feature_q20 | feature_q80 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| log_opp_depth25_quote | 1455 | -0.2998 | 8.2530 | 1.3906 | -6.8624 | 7.0009 | 7.8066 |
| log_opp_depth5_quote | 1455 | -0.2890 | 8.1999 | 1.3763 | -6.8236 | 2.6847 | 6.2842 |
| Theta_t | 1455 | -0.2424 | 7.9548 | 1.9182 | -6.0366 | -3.0978 | -0.0090 |
| closed20_energy | 1455 | 0.2404 | 2.0108 | 6.3234 | 4.3125 | 89.1643 | 262.4731 |
| closed10_energy | 1455 | 0.2220 | 1.7888 | 5.9896 | 4.2008 | 43.4120 | 134.2929 |
| bad_state_score | 1455 | -0.2186 | 6.0858 | 1.6546 | -4.4312 | -0.1559 | 0.0070 |
| good_state_score | 1455 | 0.2186 | 1.6546 | 6.0858 | 4.4312 | -0.0070 | 0.1559 |
| vacuum_score | 1455 | 0.2155 | 1.6378 | 5.7497 | 4.1119 | 0.5332 | 0.6510 |
| closed5_energy | 1455 | 0.2136 | 2.3384 | 6.2739 | 3.9354 | 19.0019 | 68.5202 |
| est_gt2_rate | 1405 | 0.2044 | 1.9080 | 5.0351 | 3.1271 | 0.3089 | 0.5084 |
| absorption_score | 1455 | -0.1921 | 6.0449 | 1.7159 | -4.3290 | 0.3519 | 0.5217 |
| frames_since_mid_change | 1455 | 0.1649 | 3.3325 | 4.3378 | 1.0053 | 0.0000 | 31.0000 |
| est_mean_net | 1405 | 0.1563 | 2.7326 | 4.5567 | 1.8241 | -0.6464 | 2.9080 |
| closed20_delta | 1455 | 0.1414 | 2.8661 | 5.4836 | 2.6175 | -15.7869 | 98.9893 |
| release_score | 1455 | 0.1397 | 2.0208 | 6.5134 | 4.4926 | 0.4678 | 0.5791 |
| past_release_raw | 1455 | -0.1366 | 3.7123 | 1.5350 | -2.1772 | -0.0000 | 0.3213 |
| lambda_prior_top_u | 1406 | 0.1358 | 3.1823 | 4.0439 | 0.8616 | 0.0237 | 0.0359 |
| closed20_score_abs | 1455 | 0.1315 | 2.6906 | 4.9372 | 2.2466 | -1.5377 | 6.6666 |
| est_cvar05_net | 1405 | -0.1306 | 4.9970 | 2.0982 | -2.8989 | -36.6249 | -15.6807 |
| P_t | 1455 | -0.1239 | 3.7123 | 2.9206 | -0.7917 | -0.0000 | 0.1017 |

## Entry Factors For 60s Decay After Early Release

| feature | rows | spearman | bottom_target_mean | top_target_mean | top_minus_bottom_target | feature_q20 | feature_q80 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| log_opp_depth25_quote | 392 | -0.1986 | 16.6921 | 4.3025 | -12.3895 | 6.2612 | 7.5214 |
| bad_state_score | 392 | -0.1921 | 14.9038 | 5.7216 | -9.1822 | -0.1835 | -0.0370 |
| good_state_score | 392 | 0.1921 | 5.7216 | 14.9038 | 9.1822 | 0.0370 | 0.1835 |
| log_opp_depth5_quote | 392 | -0.1853 | 12.8247 | 4.8383 | -7.9865 | 2.3347 | 5.9284 |
| vacuum_score | 392 | 0.1709 | 5.0680 | 11.8048 | 6.7368 | 0.5596 | 0.6700 |
| closed20_energy | 392 | 0.1680 | 5.3487 | 12.9986 | 7.6499 | 116.1378 | 337.4742 |
| Theta_t | 392 | -0.1649 | 12.1540 | 5.1722 | -6.9818 | -3.4164 | -0.2895 |
| closed5_energy | 392 | 0.1642 | 5.2635 | 13.7796 | 8.5161 | 24.6836 | 91.0961 |
| closed10_energy | 392 | 0.1639 | 3.9411 | 13.3752 | 9.4341 | 55.3682 | 172.0256 |
| closed20_delta | 392 | 0.1414 | 4.4428 | 10.9655 | 6.5227 | -9.5159 | 125.7581 |
| release_score | 392 | 0.1405 | 6.8892 | 12.7683 | 5.8791 | 0.4939 | 0.5966 |
| closed20_score_abs | 392 | 0.1242 | 4.3165 | 11.1113 | 6.7948 | -0.8372 | 8.0133 |
| frames_since_mid_change | 392 | -0.1237 | 10.1830 | 4.6247 | -5.5582 | 0.0000 | 41.8000 |
| est_cvar05_net | 387 | -0.1206 | 9.9078 | 6.8269 | -3.0809 | -43.3785 | -16.7465 |
| microprice_raw_aligned | 392 | 0.1199 | 5.7860 | 10.7398 | 4.9539 | -0.6105 | 0.8945 |
| obi5_raw_aligned | 392 | 0.1168 | 8.1129 | 12.3353 | 4.2224 | -0.8971 | 0.9120 |
| absorption_score | 392 | -0.1155 | 12.0431 | 5.9380 | -6.1051 | 0.3316 | 0.4931 |
| closed5_delta | 392 | 0.1135 | 6.2114 | 11.7654 | 5.5540 | 4.4102 | 51.8667 |
| trade_window_count | 392 | 0.1133 | 8.4111 | 11.3407 | 2.9297 | 1.0000 | 2.0000 |
| closed10_delta | 392 | 0.0862 | 6.9389 | 10.5720 | 3.6332 | -1.7970 | 83.3023 |

## Early-Path Factors For 60s Decay After Early Release

| feature | rows | spearman | bottom_target_mean | top_target_mean | top_minus_bottom_target | feature_q20 | feature_q80 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| signed_tfi_mean_5_20s | 309 | -0.3370 | 16.5746 | 7.7918 | -8.7828 | -0.0906 | 1.0000 |
| signed_mlofi5_mean_5_20s | 392 | -0.2883 | 17.5486 | 5.6987 | -11.8499 | -2.3023 | 28.5604 |
| signed_mlofi25_mean_5_20s | 392 | -0.2760 | 17.0611 | 7.3229 | -9.7382 | -7.4027 | 47.5765 |
| signed_ofi_mean_5_20s | 392 | -0.2647 | 16.8701 | 6.4599 | -10.4103 | -4.7518 | 48.1305 |
| signed_mlofi5_mean_0_10s | 392 | -0.2628 | 15.8975 | 5.2446 | -10.6529 | 1.0612 | 60.7200 |
| signed_mlofi25_mean_0_10s | 392 | -0.2603 | 16.3261 | 4.8812 | -11.4449 | 18.0147 | 97.6886 |
| signed_qi5_mean_5_20s | 392 | 0.2552 | 6.2638 | 16.1516 | 9.8878 | -0.9339 | 0.0894 |
| signed_qi25_mean_5_20s | 392 | 0.2037 | 8.9658 | 17.5405 | 8.5746 | -0.3638 | 0.0546 |
| signed_tfi_mean_0_10s | 390 | -0.1914 | 9.1758 | 8.4081 | -0.7677 | 1.0000 | 1.0000 |
| signed_mlofi5_mean_0_5s | 392 | -0.1882 | 13.2096 | 5.2204 | -7.9892 | 0.0004 | 77.1930 |
| signed_mlofi5_mean_0_3s | 392 | -0.1864 | 12.6747 | 4.3628 | -8.3119 | -0.0000 | 97.6923 |
| signed_ofi_mean_0_10s | 392 | -0.1843 | 14.0798 | 6.4459 | -7.6339 | 0.7875 | 93.3912 |
| ret_5_20s | 392 | -0.1806 | 17.7796 | 9.9023 | -7.8773 | 5.1077 | 16.7738 |
| signed_mlofi25_mean_0_5s | 392 | -0.1798 | 14.7458 | 8.0968 | -6.6489 | 0.8490 | 119.3515 |
| trade_notional_sum_5_20s | 392 | 0.1792 | 5.2914 | 14.1580 | 8.8667 | 0.0000 | 7529.9814 |
| signed_qi5_mean_0_10s | 392 | 0.1791 | 5.1600 | 14.6506 | 9.4906 | -0.9198 | 0.0833 |
| signed_mlofi25_mean_0_3s | 392 | -0.1668 | 11.3555 | 5.1103 | -6.2452 | 0.0000 | 158.3828 |
| signed_ofi_mean_0_3s | 392 | -0.1475 | 12.3904 | 6.3780 | -6.0124 | 0.0000 | 107.8501 |
| signed_qi5_mean_0_5s | 392 | 0.1346 | 6.2615 | 14.4707 | 8.2092 | -0.9230 | 0.1949 |
| signed_mlofi25_mean_0_1s | 383 | -0.1334 | 11.0751 | 6.0788 | -4.9963 | 0.0000 | 243.3243 |

## Buckets With Release-Then-Decay Risk

| view | bucket | entries | final_60_mean | mfe_10_mean | decay_60_mean | release_ge5_10_rate | release10_then_loss60_rate | frontload_10_60_mean | target_pnl |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cell_x_direction_x_frames | 01_frames_only|long|q70_85 | 20 | 1.8899 | 5.7128 | 7.8116 | 0.4000 | 0.2000 | 0.7044 | -0.2723 |
| cell_x_direction_x_frames | 01_frames_only|short|q90_95 | 22 | 1.8516 | 4.4100 | 6.3596 | 0.5000 | 0.1818 | 0.5978 | -3.3662 |
| cell_x_direction_x_frames | 11_r5_frames|short|q70_85 | 21 | 13.8663 | 7.0111 | 8.9855 | 0.3810 | 0.1429 | 0.4875 | 1992.8030 |
| cell_x_direction_x_frames_x_delta10 | 10_r5_only|short|q0_50|s80_100 | 155 | 5.9318 | 5.3284 | 8.4349 | 0.3548 | 0.1226 | 0.4384 | 227.1776 |
| quality_x_state | high|chop | 188 | 4.8447 | 4.0440 | 5.6757 | 0.3298 | 0.1117 | 0.5064 | 1914.9470 |
| cell_x_direction_x_frames_x_delta10 | 10_r5_only|short|q0_50|s0_20 | 56 | 3.3994 | 2.8994 | 5.6412 | 0.2679 | 0.1071 | 0.2490 | 29.1713 |
| cell_x_direction_x_frames_x_delta10 | 10_r5_only|short|q70_85|s80_100 | 29 | 5.2175 | 3.4441 | 7.9699 | 0.3448 | 0.1034 | 0.4112 | 2.4251 |
| quality_x_state | neutral|vacuum | 39 | 4.5860 | 3.6343 | 7.1612 | 0.3590 | 0.1026 | 0.4008 | 38.2602 |
| cell_x_direction | 01_frames_only|long | 61 | 4.4680 | 4.1220 | 4.1697 | 0.3443 | 0.0984 | 0.6214 | 35.9148 |
| quality_side | high | 513 | 5.7704 | 4.6769 | 6.6450 | 0.3606 | 0.0955 | 0.4876 | 5235.7012 |
| quality_x_state | high|vacuum | 249 | 5.3723 | 5.0384 | 7.4705 | 0.3936 | 0.0924 | 0.5137 | 2795.1747 |
| cell_x_direction_x_frames_x_delta10 | 10_r5_only|short|q0_50|s60_80 | 102 | 4.1208 | 3.9162 | 6.2643 | 0.2843 | 0.0882 | 0.3997 | 83.6828 |
| quality_x_state | high|release | 59 | 11.7298 | 6.4420 | 7.6945 | 0.4237 | 0.0847 | 0.4157 | 516.6397 |
| dominant_latent_state | vacuum | 638 | 4.8220 | 4.6909 | 6.9348 | 0.3401 | 0.0846 | 0.4931 | 3084.2767 |
| cell_x_direction_x_frames | 10_r5_only|short|q0_50 | 479 | 4.2164 | 3.6634 | 5.7250 | 0.2651 | 0.0814 | 0.4117 | 393.8556 |
| quality_x_state | reduce|vacuum | 350 | 4.4568 | 4.5615 | 6.5284 | 0.3000 | 0.0771 | 0.4874 | 250.8418 |
| cell_x_direction_x_frames | 10_r5_only|long|q70_85 | 65 | 2.8796 | 4.8724 | 8.7105 | 0.2615 | 0.0769 | 0.4724 | 21.7483 |
| quality_side | neutral | 80 | 4.0926 | 3.6400 | 5.7172 | 0.3000 | 0.0750 | 0.5012 | 40.8805 |
| cell | 01_frames_only | 147 | 4.0459 | 4.0116 | 3.9575 | 0.3469 | 0.0748 | 0.6450 | 109.8111 |
| cell_x_direction_x_frames_x_delta10 | 10_r5_only|long|q0_50|s60_80 | 84 | 5.9386 | 3.9870 | 3.5376 | 0.2976 | 0.0714 | 0.4828 | 121.8394 |
| cell_x_direction | 10_r5_only|short | 660 | 4.1440 | 3.6843 | 5.9198 | 0.2682 | 0.0697 | 0.4279 | 618.4764 |
| direction | short | 832 | 4.4695 | 3.7759 | 5.6298 | 0.2837 | 0.0673 | 0.4602 | 4843.3337 |
| cell_x_direction_x_frames_x_delta10 | 10_r5_only|long|q0_50|s80_100 | 75 | 7.3037 | 4.3966 | 6.7376 | 0.2800 | 0.0667 | 0.4045 | 150.8204 |
| cell | 10_r5_only | 1157 | 3.9609 | 3.4940 | 5.9387 | 0.2446 | 0.0631 | 0.4180 | 911.9752 |
| dominant_latent_state | chop | 510 | 3.3126 | 2.8977 | 5.0287 | 0.2118 | 0.0588 | 0.4392 | 1953.1516 |
| cell_x_direction | 11_r5_frames|short | 86 | 7.6901 | 4.3217 | 5.2272 | 0.3372 | 0.0581 | 0.4759 | 4150.9610 |
| cell_x_direction | 01_frames_only|short | 86 | 3.7466 | 3.9333 | 3.8070 | 0.3488 | 0.0581 | 0.6611 | 73.8963 |
| direction | long | 623 | 3.9748 | 3.5211 | 5.7274 | 0.2504 | 0.0578 | 0.4509 | 1017.2132 |
| cell_x_direction | 10_r5_only|long | 497 | 3.7176 | 3.2413 | 5.9638 | 0.2133 | 0.0543 | 0.4045 | 293.4989 |
| cell | 11_r5_frames | 151 | 6.7381 | 4.6554 | 5.2939 | 0.3841 | 0.0530 | 0.5282 | 4838.7605 |

## Examples

| example_type | date | entry_row | cell | direction_label | frames_q_bin | delta10_bin | net | target_exposure | final_60s_bps | mfe_10s_bps | mfe_60s_bps | decay_60s_bps | ret_0_5s | signed_qi5_mean_0_5s | release_flow_sum_0_5s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| release_then_decay | 2026-05-09 | 1555985 | 10_r5_only | short | q0_50 | s80_100 | -114.5798 | 0.3750 | -112.1265 | 5.8508 | 5.8508 | 117.9774 | -8.4451 | 0.3978 | 0.0000 |
| release_then_decay | 2026-05-15 | 2538506 | 10_r5_only | long | q0_50 | s20_40 | -61.7856 | 0.3750 | -58.5424 | 5.1022 | 25.1669 | 83.7092 | -1.9140 | 0.4901 | 0.0000 |
| release_then_decay | 2026-05-13 | 2240987 | 10_r5_only | long | q50_70 | s20_40 | -66.7026 | 0.3750 | -64.4258 | 5.7208 | 5.7208 | 70.1466 | 5.7208 | -0.9193 | 0.0000 |
| release_then_decay | 2026-05-09 | 1556075 | 10_r5_only | short | q0_50 | s80_100 | -47.4346 | 0.3750 | -44.9788 | 18.1783 | 18.1783 | 63.1571 | -7.1324 | 0.3362 | 0.0000 |
| release_then_decay | 2026-05-15 | 2580340 | 10_r5_only | short | q70_85 | s60_80 | -35.2015 | 0.3750 | -43.7927 | 11.0572 | 12.0056 | 55.7983 | -0.0000 | 0.9414 | 0.0000 |
| release_then_decay | 2026-05-15 | 2454616 | 10_r5_only | short | q70_85 | s80_100 | -37.1803 | 0.3750 | -35.1473 | 6.8075 | 17.7683 | 52.9157 | 6.8075 | 0.0566 | 0.0000 |
| release_then_decay | 2026-05-15 | 2540829 | 11_r5_frames | long | q70_85 | s80_100 | -45.0547 | 2.0000 | -42.9424 | 7.2978 | 7.9321 | 50.8745 | 6.9806 | 0.6381 | 0.0000 |
| release_then_decay | 2026-05-13 | 2215898 | 10_r5_only | long | q50_70 | s60_80 | -15.1313 | 0.3750 | -13.1454 | 19.0301 | 30.8237 | 43.9691 | -7.8851 | 0.8970 | 0.0000 |
| release_then_decay | 2026-05-12 | 2060868 | 01_frames_only | long | q70_85 | s60_80 | -13.2332 | 0.1250 | -10.9455 | 31.8027 | 31.8027 | 42.7482 | 25.0651 | 0.5128 | 0.0000 |
| release_then_decay | 2026-05-14 | 2354424 | 10_r5_only | long | q0_50 | s20_40 | -52.0144 | 0.3750 | -17.6761 | 18.5412 | 23.6191 | 41.2952 | 12.2650 | -0.9566 | 0.0000 |
| release_then_decay | 2026-05-09 | 1615412 | 11_r5_frames | short | q70_85 | s80_100 | -30.3023 | 8.0000 | -27.8923 | 12.5612 | 12.5612 | 40.4535 | 12.5612 | -0.1714 | 0.0000 |
| release_then_decay | 2026-05-14 | 2328726 | 10_r5_only | short | q0_50 | s80_100 | -33.4819 | 0.3750 | -30.9645 | 7.6040 | 7.6040 | 38.5685 | 7.6040 | -0.0007 | 0.0000 |
| release_then_decay | 2026-05-14 | 2346538 | 10_r5_only | long | q0_50 | s0_20 | -13.9499 | 0.3750 | -12.0464 | 13.2343 | 24.3496 | 36.3959 | 0.0000 | 0.9159 | 0.0000 |
| release_then_decay | 2026-05-15 | 2453815 | 10_r5_only | short | q0_50 | s0_20 | -15.3716 | 0.3750 | -12.9051 | 17.6248 | 23.2124 | 36.1176 | 17.6248 | -0.9471 | 0.0000 |
| release_then_decay | 2026-05-14 | 2336374 | 10_r5_only | long | q70_85 | s80_100 | -13.5295 | 0.3750 | -11.7748 | 23.5081 | 23.5081 | 35.2830 | 19.8951 | 0.2222 | 0.0000 |
| release_then_decay | 2026-05-14 | 2361187 | 11_r5_frames | short | q90_95 | s60_80 | -12.0165 | 10.0000 | -9.5281 | 24.1586 | 24.4572 | 33.9852 | 18.4865 | -0.6559 | 0.0000 |
| release_then_decay | 2026-05-15 | 2535962 | 10_r5_only | short | q0_50 | s60_80 | -4.2769 | 0.3750 | -2.1846 | 30.0085 | 30.0085 | 32.1931 | 0.3121 | 0.9728 | 0.0000 |
| release_then_decay | 2026-05-14 | 2325151 | 10_r5_only | short | q0_50 | s40_60 | -25.2617 | 0.3750 | -23.4982 | 8.5585 | 8.5585 | 32.0567 | -11.6034 | 0.8400 | 0.0000 |
| release_then_decay | 2026-05-14 | 2301841 | 10_r5_only | short | q0_50 | s80_100 | -21.8103 | 0.3750 | -20.0156 | 11.4555 | 11.4555 | 31.4711 | -6.9941 | -0.3562 | 0.0000 |
| release_then_decay | 2026-05-10 | 1775309 | 10_r5_only | long | q70_85 | s80_100 | -18.9435 | 0.3750 | -16.3697 | 14.4586 | 14.4586 | 30.8283 | 8.8034 | -0.7053 | 0.0000 |
| release_then_decay | 2026-05-14 | 2366486 | 10_r5_only | short | q0_50 | s0_20 | -8.4779 | 0.3750 | -6.1583 | 11.4469 | 24.3770 | 30.5353 | 11.4469 | -0.8494 | 0.0000 |
| release_then_decay | 2026-05-14 | 2386172 | 11_r5_frames | long | q85_90 | s80_100 | -19.7547 | 2.0000 | -17.9925 | 10.9626 | 10.9626 | 28.9550 | 6.7008 | 0.0234 | 0.0000 |
| release_then_decay | 2026-05-15 | 2444981 | 10_r5_only | short | q50_70 | s60_80 | -12.6274 | 0.3750 | -10.7328 | 7.4601 | 17.9137 | 28.6465 | 5.9677 | -0.7109 | 0.0000 |
| release_then_decay | 2026-05-15 | 2444979 | 10_r5_only | short | q0_50 | s60_80 | -12.6274 | 0.3750 | -10.7328 | 7.4601 | 17.9137 | 28.6465 | 5.9677 | -0.7530 | 0.0000 |
| release_then_decay | 2026-05-15 | 2541317 | 10_r5_only | long | q0_50 | s80_100 | -9.6002 | 0.3750 | -7.0075 | 6.3662 | 21.3108 | 28.3183 | 0.3184 | -0.2278 | 0.0000 |
| release_then_decay | 2026-05-14 | 2353872 | 01_frames_only | short | q90_95 | s0_20 | -12.1987 | 0.6250 | -9.8550 | 13.7535 | 17.3445 | 27.1995 | 13.4543 | -0.9097 | 0.0000 |
| release_then_decay | 2026-05-11 | 1948284 | 10_r5_only | short | q0_50 | s60_80 | -15.3975 | 0.3750 | -13.6395 | 13.3544 | 13.3544 | 26.9938 | 8.4962 | -0.8958 | 0.0000 |
| release_then_decay | 2026-05-11 | 1955798 | 01_frames_only | long | q85_90 | s80_100 | -16.0686 | 0.1250 | -14.1645 | 11.7383 | 11.7383 | 25.9028 | 4.5164 | -0.4414 | 0.0000 |
| release_then_decay | 2026-05-12 | 1958476 | 10_r5_only | short | q0_50 | s60_80 | -8.3546 | 0.3750 | -6.7418 | 18.7171 | 18.7171 | 25.4590 | 12.5765 | 0.1231 | 0.0000 |
| release_then_decay | 2026-05-14 | 2391387 | 10_r5_only | short | q0_50 | s80_100 | -16.6059 | 0.3750 | -14.2422 | 10.9227 | 10.9227 | 25.1649 | 10.0120 | -0.2584 | 0.0000 |

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_release_decay_paths_20260518_ccusdt_v1_tfi_release_decay_factor_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_release_decay_factor_scorecard_20260518_ccusdt_v1_tfi_release_decay_factor_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_release_decay_buckets_20260518_ccusdt_v1_tfi_release_decay_factor_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_release_decay_examples_20260518_ccusdt_v1_tfi_release_decay_factor_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_release_decay_summary_20260518_ccusdt_v1_tfi_release_decay_factor_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_release_decay_factor_analysis.py
```

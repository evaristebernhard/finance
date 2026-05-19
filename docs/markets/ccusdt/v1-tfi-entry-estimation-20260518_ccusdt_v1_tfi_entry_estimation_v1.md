# CCUSDT TFI Entry-Level Estimation

Status: `20260518_ccusdt_v1_tfi_entry_estimation_v1`.

Guardrail: `strict_asof_entry_level_factor_estimation_no_future_labels_no_execution_recommendation`.

This report estimates each candidate entry from observable factor buckets using only labels available before the entry timestamp.

## Estimator

For entry `i` at time `t_i`, the admissible history is:

$$
\mathcal{H}_{t_i}=\{j:\ label\_available\_ts_j\le t_i\}.
$$

For a bucket `A(x_i)`, raw estimates are:

$$
\mu_A=\mathbb{E}[r\mid A],\quad p_A=\mathbb{P}(r>2\mathrm{bps}\mid A),\quad L_A=\operatorname{CVaR}_{5\%}(r\mid A).
$$

The reported estimate uses hierarchical shrinkage to the parent bucket:

$$
\widehat\mu_A=\lambda_A\bar r_A+(1-\lambda_A)\widehat\mu_{\pi(A)},\quad \lambda_A=\frac{n_A}{n_A+k}.
$$

The hierarchy is:

`global -> cell -> cell_direction -> cell_direction_q -> cell_direction_q_delta10/energy10/z10 -> cell_direction_q_delta10_energy10`.

## Main Read

1. Active entries scored: `1715`; entries with strict estimates: `1665`.
2. Best realized quality class by weighted mean: `strong_positive` with `7.5693` bps.
3. Worst realized quality class by weighted mean: `insufficient_history` with `-0.4087` bps.
4. Worst day remains `2026-05-13` with total `-58.2736` under target exposure.
5. Core high-quality classes (`strong_positive + positive_right_tail_fragile`) have total `6217.7640`, weighted mean `5.7432` bps, and worst daily total `-51.7118`.
6. Reduce-side classes (`weak_positive_mean + avoid_or_reduce + insufficient_history`) have total `610.3905`, weighted mean `0.9891` bps, and worst daily total `-117.1437`.

## Diagnostics

| view | entry_quality_class | est_mean_decile | cell | entries | exposure | total_net | weighted_mean_net | mean_net | median_net | gt2_rate | cvar05_net | tail_share90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| entry_quality_class | strong_positive |  |  | 252 | 590.5000 | 4469.6945 | 7.5693 | 4.1353 | 2.1032 | 0.5040 | -32.8345 | 1.1141 |
| entry_quality_class | positive_right_tail_fragile |  |  | 344 | 492.1250 | 1748.0695 | 3.5521 | 3.3469 | 0.0785 | 0.4884 | -24.4512 | 1.1830 |
| entry_quality_class | positive_balanced |  |  | 102 | 44.1250 | 139.1427 | 3.1534 | 2.4899 | 0.2161 | 0.4902 | -16.1501 | 0.9839 |
| entry_quality_class | avoid_or_reduce |  |  | 498 | 374.2500 | 513.6467 | 1.3725 | 1.2795 | -1.1699 | 0.3916 | -38.0442 | 2.6802 |
| entry_quality_class | weak_positive_mean |  |  | 469 | 217.3750 | 107.1658 | 0.4930 | 1.2270 | -0.6819 | 0.4286 | -38.9381 | 2.6831 |
| entry_quality_class | insufficient_history |  |  | 50 | 25.5000 | -10.4220 | -0.4087 | -1.6911 | -1.5053 | 0.2800 | -25.3049 |  |
| est_mean_decile |  | d9 |  | 166 | 216.7500 | 2453.8275 | 11.3210 | 4.9471 | 2.5945 | 0.5301 | -29.3259 | 0.9726 |
| est_mean_decile |  | d8 |  | 167 | 164.8750 | 1653.9158 | 10.0313 | 3.9719 | 2.7117 | 0.5150 | -29.1397 | 1.1158 |
| est_mean_decile |  | d5 |  | 167 | 288.0000 | 1024.1937 | 3.5562 | 3.5444 | -0.6783 | 0.4431 | -25.7599 | 1.1600 |
| est_mean_decile |  | d6 |  | 166 | 138.2500 | 424.7986 | 3.0727 | 2.4670 | 0.9878 | 0.4880 | -29.5906 | 1.5819 |
| est_mean_decile |  | d1 |  | 167 | 64.0000 | 184.7167 | 2.8862 | 2.9657 | -0.3556 | 0.4491 | -15.8834 | 1.1207 |
| est_mean_decile |  | d10 |  | 167 | 307.3750 | 705.7860 | 2.2962 | 2.7735 | 1.9116 | 0.4970 | -29.1618 | 1.1080 |
| est_mean_decile |  | d2 |  | 166 | 146.2500 | 334.5336 | 2.2874 | 2.8395 | -1.3260 | 0.3976 | -38.8972 | 1.6549 |
| est_mean_decile |  | d4 |  | 166 | 141.5000 | 226.0277 | 1.5974 | 0.9801 | -0.6755 | 0.4217 | -37.5501 | 2.8274 |
| est_mean_decile |  | d7 |  | 166 | 86.6250 | -4.7682 | -0.0550 | -0.2194 | -1.3233 | 0.3795 | -28.3948 |  |
| est_mean_decile |  | d3 |  | 167 | 164.7500 | -25.3121 | -0.1536 | -2.2874 | -1.8004 | 0.3293 | -57.5630 |  |
| est_mean_decile |  | missing |  | 50 | 25.5000 | -10.4220 | -0.4087 | -1.6911 | -1.5053 | 0.2800 | -25.3049 |  |
| cell_x_quality | positive_balanced |  | 11_r5_frames | 2 | 6.0000 | 74.9179 | 12.4863 | 10.6679 | 10.6679 | 1.0000 | 5.2129 | 0.7557 |
| cell_x_quality | strong_positive |  | 11_r5_frames | 88 | 520.0000 | 4219.4449 | 8.1143 | 7.4740 | 3.7977 | 0.5795 | -33.2154 | 0.8897 |
| cell_x_quality | weak_positive_mean |  | 01_frames_only | 33 | 8.1250 | 53.2777 | 6.5573 | 4.5512 | 3.7246 | 0.5455 | -16.1243 | 0.6449 |
| cell_x_quality | positive_right_tail_fragile |  | 10_r5_only | 207 | 85.5000 | 335.1684 | 3.9201 | 4.3231 | 1.4537 | 0.4976 | -25.7364 | 1.0551 |
| cell_x_quality | positive_right_tail_fragile |  | 11_r5_frames | 51 | 362.0000 | 1367.3585 | 3.7772 | 3.2759 | 3.1794 | 0.5686 | -25.3224 | 1.1956 |
| cell_x_quality | strong_positive |  | 10_r5_only | 164 | 70.5000 | 250.2496 | 3.5496 | 2.3437 | 0.1469 | 0.4634 | -30.6257 | 1.5548 |
| cell_x_quality | insufficient_history |  | 11_r5_frames | 2 | 8.0000 | 22.2088 | 2.7761 | 2.7761 | 2.7761 | 0.5000 | -1.0000 | 1.1801 |
| cell_x_quality | positive_balanced |  | 01_frames_only | 13 | 3.2500 | 8.0136 | 2.4657 | 1.8446 | -0.8322 | 0.4615 | -12.8288 | 1.3319 |
| cell_x_quality | avoid_or_reduce |  | 01_frames_only | 13 | 4.7500 | 10.3188 | 2.1724 | 3.5920 | 3.2213 | 0.5385 | -10.5595 | 0.6493 |
| cell_x_quality | positive_balanced |  | 10_r5_only | 87 | 34.8750 | 56.2112 | 1.6118 | 2.3983 | -0.2267 | 0.4828 | -16.6250 | 1.0025 |
| cell_x_quality | avoid_or_reduce |  | 11_r5_frames | 29 | 194.0000 | 275.4986 | 1.4201 | 1.8426 | 0.1140 | 0.4828 | -9.6994 | 0.8816 |
| cell_x_quality | avoid_or_reduce |  | 10_r5_only | 456 | 175.5000 | 227.8294 | 1.2982 | 1.1778 | -1.4096 | 0.3816 | -40.1457 | 3.0398 |
| cell_x_quality | positive_right_tail_fragile |  | 01_frames_only | 86 | 44.6250 | 45.5426 | 1.0206 | 1.0394 | -0.5888 | 0.4186 | -18.9288 | 2.3382 |
| cell_x_quality | weak_positive_mean |  | 10_r5_only | 430 | 161.2500 | 162.8456 | 1.0099 | 1.0099 | -0.8384 | 0.4209 | -40.5804 | 3.3325 |
| cell_x_quality | insufficient_history |  | 01_frames_only | 12 | 4.0000 | -2.1566 | -0.5391 | -0.7370 | -0.8318 | 0.4167 | -15.0392 |  |
| cell_x_quality | insufficient_history |  | 10_r5_only | 36 | 13.5000 | -30.4742 | -2.2574 | -2.2574 | -1.6798 | 0.2222 | -30.4377 |  |
| cell_x_quality | weak_positive_mean |  | 11_r5_frames | 6 | 48.0000 | -108.9575 | -2.2699 | -1.4988 | -0.6800 | 0.3333 | -9.6953 |  |

## Daily Quality Attribution

| date | entry_quality_class | entries | exposure | total_net | weighted_mean_net | mean_net | gt2_rate | cvar05_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-04 | insufficient_history | 49 | 25.2500 | -6.6622 | -0.2638 | -1.4187 | 0.2857 | -23.8882 |
| 2026-05-05 | avoid_or_reduce | 103 | 90.7500 | 36.8657 | 0.4062 | -0.5677 | 0.3398 | -18.2847 |
| 2026-05-05 | insufficient_history | 1 | 0.2500 | -3.7598 | -15.0392 | -15.0392 | 0.0000 | -15.0392 |
| 2026-05-05 | positive_balanced | 1 | 0.2500 | 1.4398 | 5.7592 | 5.7592 | 1.0000 | 5.7592 |
| 2026-05-05 | positive_right_tail_fragile | 9 | 3.3750 | 3.2809 | 0.9721 | 0.9721 | 0.3333 | -4.3801 |
| 2026-05-05 | weak_positive_mean | 3 | 1.1250 | 0.2663 | 0.2367 | 0.2367 | 0.3333 | -3.1962 |
| 2026-05-06 | avoid_or_reduce | 45 | 16.8750 | -18.0273 | -1.0683 | -1.0683 | 0.3111 | -11.4709 |
| 2026-05-06 | positive_balanced | 5 | 1.6250 | -0.9724 | -0.5984 | -1.3688 | 0.2000 | -7.5499 |
| 2026-05-06 | positive_right_tail_fragile | 1 | 0.5000 | 2.2920 | 4.5839 | 4.5839 | 1.0000 | 4.5839 |
| 2026-05-06 | weak_positive_mean | 2 | 0.7500 | 3.9690 | 5.2920 | 5.2920 | 0.5000 | -1.6707 |
| 2026-05-07 | avoid_or_reduce | 29 | 30.1250 | -17.9636 | -0.5963 | -1.3928 | 0.3103 | -11.6719 |
| 2026-05-07 | positive_right_tail_fragile | 6 | 2.1250 | 2.7964 | 1.3160 | -0.5088 | 0.3333 | -6.5797 |
| 2026-05-08 | avoid_or_reduce | 31 | 25.1250 | 148.4945 | 5.9102 | 2.2675 | 0.3548 | -8.8783 |
| 2026-05-08 | positive_right_tail_fragile | 7 | 2.5000 | 5.2418 | 2.0967 | 2.0209 | 0.5714 | -6.6486 |
| 2026-05-08 | weak_positive_mean | 5 | 1.8750 | 1.5675 | 0.8360 | 0.8360 | 0.4000 | -8.2142 |
| 2026-05-09 | avoid_or_reduce | 85 | 42.6250 | 179.7839 | 4.2178 | 4.4369 | 0.5647 | -75.0446 |
| 2026-05-09 | positive_right_tail_fragile | 53 | 123.0000 | -51.7118 | -0.4204 | 3.9392 | 0.4717 | -30.5908 |
| 2026-05-09 | weak_positive_mean | 32 | 58.0000 | -59.0015 | -1.0173 | 3.5232 | 0.4688 | -47.1740 |
| 2026-05-10 | avoid_or_reduce | 33 | 37.2500 | -102.8882 | -2.7621 | 0.8095 | 0.3333 | -13.1565 |
| 2026-05-10 | positive_balanced | 7 | 2.6250 | -0.6863 | -0.2614 | -0.2614 | 0.2857 | -10.5940 |
| 2026-05-10 | positive_right_tail_fragile | 40 | 58.8750 | 134.2073 | 2.2795 | 4.3915 | 0.5000 | -11.7010 |
| 2026-05-10 | strong_positive | 9 | 10.6250 | 66.3370 | 6.2435 | 11.3600 | 0.8889 | -2.4509 |
| 2026-05-10 | weak_positive_mean | 32 | 11.6250 | -14.2554 | -1.2263 | -1.2141 | 0.2812 | -32.5539 |
| 2026-05-11 | avoid_or_reduce | 35 | 62.8750 | 101.7146 | 1.6177 | 1.7789 | 0.4000 | -12.9341 |
| 2026-05-11 | positive_balanced | 19 | 7.1250 | 12.3794 | 1.7375 | 1.7375 | 0.4211 | -13.7755 |
| 2026-05-11 | positive_right_tail_fragile | 34 | 18.2500 | 43.2246 | 2.3685 | 1.7706 | 0.4706 | -15.7534 |
| 2026-05-11 | strong_positive | 19 | 14.0000 | 24.0056 | 1.7147 | 2.9924 | 0.5789 | -23.0086 |
| 2026-05-11 | weak_positive_mean | 59 | 20.7500 | 45.9636 | 2.2151 | 2.1672 | 0.4576 | -24.5869 |
| 2026-05-12 | avoid_or_reduce | 9 | 20.6250 | 92.6441 | 4.4918 | -0.0358 | 0.2222 | -3.2759 |
| 2026-05-12 | positive_balanced | 12 | 5.6250 | 16.9184 | 3.0077 | 4.6681 | 0.5000 | -15.3841 |
| 2026-05-12 | positive_right_tail_fragile | 41 | 113.1250 | 388.5683 | 3.4349 | 2.6500 | 0.5366 | -16.0121 |
| 2026-05-12 | strong_positive | 23 | 35.1250 | 56.6737 | 1.6135 | 2.3057 | 0.5217 | -14.1921 |
| 2026-05-12 | weak_positive_mean | 35 | 11.5000 | -31.0600 | -2.7009 | -2.7281 | 0.2857 | -25.8352 |
| 2026-05-13 | avoid_or_reduce | 23 | 8.6250 | -38.7515 | -4.4929 | -4.4929 | 0.1304 | -29.5281 |
| 2026-05-13 | positive_balanced | 1 | 1.5000 | -23.9288 | -15.9525 | -15.9525 | 0.0000 | -15.9525 |
| 2026-05-13 | positive_right_tail_fragile | 17 | 37.1250 | 16.9759 | 0.4573 | -3.2678 | 0.2353 | -35.1630 |
| 2026-05-13 | strong_positive | 11 | 8.5000 | 27.0307 | 3.1801 | 2.8364 | 0.4545 | -9.2864 |
| 2026-05-13 | weak_positive_mean | 51 | 19.1250 | -39.5999 | -2.0706 | -2.3715 | 0.2941 | -39.3546 |
| 2026-05-14 | avoid_or_reduce | 39 | 14.6250 | 84.5797 | 5.7832 | 5.7832 | 0.5128 | -51.5771 |
| 2026-05-14 | positive_balanced | 15 | 5.3750 | 17.7019 | 3.2934 | 3.0892 | 0.5333 | -21.8103 |
| 2026-05-14 | positive_right_tail_fragile | 68 | 93.5000 | 1111.0800 | 11.8832 | 6.2981 | 0.5147 | -33.0169 |
| 2026-05-14 | strong_positive | 71 | 163.8750 | 1164.3750 | 7.1053 | 3.4896 | 0.4648 | -34.6105 |
| 2026-05-14 | weak_positive_mean | 67 | 24.2500 | 78.1218 | 3.2215 | 3.7161 | 0.5075 | -53.7158 |
| 2026-05-15 | avoid_or_reduce | 26 | 9.7500 | 4.3170 | 0.4428 | 0.4428 | 0.3462 | -56.1319 |
| 2026-05-15 | positive_balanced | 20 | 6.6250 | 18.0285 | 2.7213 | 2.6163 | 0.5000 | -14.7412 |
| 2026-05-15 | positive_right_tail_fragile | 39 | 23.6250 | 51.7865 | 2.1920 | 3.4510 | 0.5128 | -25.2866 |
| 2026-05-15 | strong_positive | 65 | 176.3750 | 2189.5373 | 12.4141 | 6.0214 | 0.5077 | -35.0570 |
| 2026-05-15 | weak_positive_mean | 68 | 25.2500 | 137.6469 | 5.4514 | 5.4345 | 0.5882 | -26.4881 |
| 2026-05-16 | avoid_or_reduce | 25 | 9.3750 | 15.9383 | 1.7001 | 1.7001 | 0.4800 | -10.8189 |
| 2026-05-16 | positive_balanced | 5 | 1.7500 | 4.7514 | 2.7151 | 2.8459 | 0.6000 | -3.6975 |
| 2026-05-16 | positive_right_tail_fragile | 16 | 9.5000 | 12.5299 | 1.3189 | 1.8505 | 0.5625 | -14.7960 |
| 2026-05-16 | strong_positive | 28 | 105.2500 | 475.3762 | 4.5166 | -0.5016 | 0.3571 | -41.2430 |
| 2026-05-16 | weak_positive_mean | 64 | 24.0000 | -17.7431 | -0.7393 | -0.7393 | 0.3594 | -30.7042 |
| 2026-05-17 | avoid_or_reduce | 15 | 5.6250 | 26.9395 | 4.7893 | 4.7893 | 0.4667 | -6.3473 |
| 2026-05-17 | positive_balanced | 17 | 11.6250 | 93.5107 | 8.0439 | 4.1716 | 0.6471 | -3.2707 |
| 2026-05-17 | positive_right_tail_fragile | 13 | 6.6250 | 27.7976 | 4.1959 | 2.8241 | 0.5385 | -14.9765 |
| 2026-05-17 | strong_positive | 26 | 76.7500 | 466.3591 | 6.0763 | 6.6788 | 0.5769 | -14.7315 |
| 2026-05-17 | weak_positive_mean | 51 | 19.1250 | 1.2907 | 0.0675 | 0.0675 | 0.4706 | -42.5985 |

## Current Bucket Snapshot

| level | key | raw_hist_n | raw_mean_net | raw_gt2_rate | raw_cvar05_net | raw_tail_share90 | shrunk_mean_net | shrunk_gt2_rate | shrunk_cvar05_net | shrink_lambda |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cell_direction_q_delta10_energy10 | 10_r5_only|long|q50_70|s80_100|s80_100 | 14.0000 | 28.4605 | 0.7143 | -21.7517 | 0.6821 | 11.5530 | 0.5386 | -29.5975 | 0.3590 |
| cell_direction_q_energy10 | 10_r5_only|long|q50_70|s80_100 | 22.0000 | 18.1601 | 0.5455 | -39.1794 | 0.8450 | 9.6094 | 0.4895 | -36.4197 | 0.4681 |
| cell_direction_q_delta10_energy10 | 11_r5_frames|short|q70_85|s20_40|s60_80 | 2.0000 | 77.5798 | 0.5000 | -0.8375 | 1.0054 | 7.6771 | 0.4447 | -31.5353 | 0.0741 |
| cell_direction_q_energy10 | 11_r5_frames|short|q70_85|s60_80 | 5.0000 | 34.9649 | 0.6000 | -0.8375 | 0.8923 | 7.5649 | 0.4669 | -28.4655 | 0.1667 |
| cell_direction_q_delta10 | 11_r5_frames|short|q70_85|s20_40 | 4.0000 | 41.6005 | 0.5000 | -0.8375 | 0.9375 | 7.5353 | 0.4485 | -29.4182 | 0.1379 |
| cell_direction_q_z10 | 11_r5_frames|short|q70_85|s20_40 | 4.0000 | 41.6005 | 0.5000 | -0.8375 | 0.9375 | 7.5353 | 0.4485 | -29.4182 | 0.1379 |
| cell_direction_q_delta10 | 10_r5_only|long|q50_70|s80_100 | 21.0000 | 13.7502 | 0.5714 | -45.5782 | 1.1691 | 7.4103 | 0.5001 | -39.2809 | 0.4565 |
| cell_direction_q_z10 | 10_r5_only|short|q70_85|s40_60 | 17.0000 | 13.6778 | 0.5294 | -15.2369 | 0.7696 | 6.7772 | 0.4763 | -26.4001 | 0.4048 |
| cell_direction_q_z10 | 10_r5_only|long|q50_70|s80_100 | 22.0000 | 12.0457 | 0.5000 | -45.5782 | 1.2739 | 6.7474 | 0.4682 | -39.4149 | 0.4681 |
| cell_direction_q | 11_r5_frames|short|q70_85 | 24.0000 | 11.4478 | 0.4583 | -28.3199 | 1.1128 | 6.6708 | 0.4491 | -31.2134 | 0.4898 |
| cell_direction_q_delta10_energy10 | 10_r5_only|short|q70_85|s40_60|s80_100 | 4.0000 | 31.5630 | 0.5000 | -8.1847 | 0.9557 | 6.1508 | 0.4485 | -30.4316 | 0.1379 |
| cell_direction_q_delta10 | 11_r5_frames|short|q85_90|s80_100 | 9.0000 | 16.7179 | 0.8889 | -0.8419 | 0.4367 | 5.9583 | 0.5590 | -25.2164 | 0.2647 |
| cell_direction_q_delta10_energy10 | 11_r5_frames|short|q85_90|s80_100|s80_100 | 9.0000 | 16.7179 | 0.8889 | -0.8419 | 0.4367 | 5.9583 | 0.5590 | -25.2164 | 0.2647 |
| cell_direction_q_delta10_energy10 | 10_r5_only|short|q50_70|s0_20|s80_100 | 5.0000 | 23.6525 | 1.0000 | 4.3497 | 0.6480 | 5.6795 | 0.5335 | -27.6010 | 0.1667 |
| cell_direction_q_energy10 | 10_r5_only|long|q0_50|s80_100 | 91.0000 | 6.5840 | 0.5275 | -37.9866 | 0.9286 | 5.6144 | 0.5087 | -37.1255 | 0.7845 |
| cell_direction_q_z10 | 11_r5_frames|short|q85_90|s80_100 | 9.0000 | 15.2069 | 0.8889 | -14.4415 | 0.4801 | 5.5583 | 0.5590 | -28.8163 | 0.2647 |
| cell_direction_q_energy10 | 11_r5_frames|short|q85_90|s80_100 | 11.0000 | 13.1812 | 0.8182 | -8.4403 | 0.7577 | 5.4754 | 0.5557 | -26.1840 | 0.3056 |
| cell_direction_q_energy10 | 10_r5_only|short|q50_70|s80_100 | 33.0000 | 8.0349 | 0.6364 | -20.2555 | 0.8345 | 5.4702 | 0.5518 | -26.1761 | 0.5690 |
| cell_direction_q_delta10_energy10 | 10_r5_only|long|q0_50|s60_80|s80_100 | 12.0000 | 12.3671 | 0.6667 | -3.0195 | 0.6139 | 5.4196 | 0.5137 | -23.9463 | 0.3243 |
| cell_direction_q_delta10 | 10_r5_only|short|q70_85|s40_60 | 12.0000 | 12.0929 | 0.5000 | -15.2369 | 1.0507 | 5.3307 | 0.4596 | -27.9087 | 0.3243 |
| cell_direction_q_energy10 | 10_r5_only|short|q70_85|s80_100 | 39.0000 | 7.0711 | 0.5385 | -34.8337 | 0.8806 | 5.1234 | 0.5001 | -34.5046 | 0.6094 |
| cell_direction | 11_r5_frames|short | 101.0000 | 5.4498 | 0.5446 | -21.7280 | 1.0138 | 4.7822 | 0.5239 | -24.1612 | 0.8016 |
| cell_direction_q_z10 | 10_r5_only|long|q0_50|s80_100 | 79.0000 | 5.6046 | 0.5063 | -31.0301 | 0.8140 | 4.7585 | 0.4904 | -31.7419 | 0.7596 |
| cell_direction_q_delta10 | 11_r5_frames|long|q85_90|s80_100 | 7.0000 | 14.1447 | 0.8571 | -19.7547 | 0.3729 | 4.7229 | 0.5314 | -30.8769 | 0.2188 |
| cell | 11_r5_frames | 178.0000 | 5.0343 | 0.5562 | -28.4984 | 0.9335 | 4.6711 | 0.5419 | -29.1749 | 0.8768 |
| cell_direction_q_z10 | 10_r5_only|long|q50_70|s40_60 | 19.0000 | 7.8926 | 0.4211 | -25.2147 | 0.7673 | 4.5927 | 0.4320 | -30.2013 | 0.4318 |
| cell_direction_q_delta10_energy10 | 10_r5_only|long|q0_50|s40_60|s80_100 | 3.0000 | 24.9536 | 1.0000 | 4.2187 | 0.7180 | 4.5351 | 0.5002 | -29.8972 | 0.1071 |
| cell_direction_q_z10 | 11_r5_frames|short|q70_85|s60_80 | 2.0000 | 34.5290 | 1.0000 | 2.7117 | 0.9607 | 4.4881 | 0.4817 | -31.2724 | 0.0741 |
| cell_direction_q_energy10 | 11_r5_frames|long|q95_99|s80_100 | 2.0000 | 33.5466 | 0.5000 | -0.8411 | 1.0125 | 4.4153 | 0.4447 | -31.5356 | 0.0741 |
| cell_direction_q_delta10_energy10 | 11_r5_frames|long|q95_99|s80_100|s80_100 | 2.0000 | 33.5466 | 0.5000 | -0.8411 | 1.0125 | 4.4153 | 0.4447 | -31.5356 | 0.0741 |
| cell_direction_q_delta10_energy10 | 10_r5_only|long|q0_50|s80_100|s80_100 | 52.0000 | 5.5306 | 0.5385 | -40.4511 | 1.0698 | 4.4118 | 0.5066 | -38.3537 | 0.6753 |
| cell_direction_q | 11_r5_frames|long|q99_100 | 6.0000 | 13.9465 | 0.5000 | -2.6073 | 0.7875 | 4.3806 | 0.4518 | -27.9169 | 0.1935 |
| cell_direction_q_delta10_energy10 | 11_r5_frames|long|q99_100|s60_80|s80_100 | 2.0000 | 32.5265 | 0.5000 | -0.8412 | 1.0129 | 4.3398 | 0.4447 | -31.5356 | 0.0741 |
| cell_direction_q_energy10 | 11_r5_frames|long|q99_100|s80_100 | 2.0000 | 32.5265 | 0.5000 | -0.8412 | 1.0129 | 4.3398 | 0.4447 | -31.5356 | 0.0741 |
| cell_direction_q_z10 | 10_r5_only|short|q0_50|s80_100 | 151.0000 | 4.6271 | 0.5364 | -40.8485 | 0.9947 | 4.2660 | 0.5228 | -39.8745 | 0.8580 |
| cell_direction_q_energy10 | 11_r5_frames|short|q95_99|s20_40 | 3.0000 | 21.1936 | 1.0000 | 10.0939 | 0.5704 | 4.1322 | 0.5002 | -29.2678 | 0.1071 |
| cell_direction_q_delta10_energy10 | 10_r5_only|long|q0_50|s0_20|s80_100 | 14.0000 | 7.6854 | 0.3571 | -13.9499 | 1.0587 | 4.0953 | 0.4104 | -26.7968 | 0.3590 |
| cell_direction_q_delta10 | 11_r5_frames|long|q99_100|s60_80 | 3.0000 | 20.8153 | 0.3333 | -2.6073 | 1.0552 | 4.0917 | 0.4288 | -30.6286 | 0.1071 |
| cell_direction_q_z10 | 11_r5_frames|long|q99_100|s60_80 | 3.0000 | 20.8153 | 0.3333 | -2.6073 | 1.0552 | 4.0917 | 0.4288 | -30.6286 | 0.1071 |
| cell_direction_q_delta10_energy10 | 10_r5_only|short|q0_50|s60_80|s40_60 | 29.0000 | 5.8154 | 0.4828 | -14.5683 | 0.5943 | 4.0883 | 0.4631 | -23.5604 | 0.5370 |

## Interpretation

- `strong_positive` means prior bucket mean is above `2` bps, right-tail rate is better than global, and left tail is not worse than global.
- `positive_right_tail_fragile` means expected value is positive but top-tail dependence is high; these entries can be profitable while still fragile.
- `avoid_or_reduce` is a statistical estimate class, not a proof that the signal has no value; it says this exact as-of bucket did not justify full exposure.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_entry_estimates_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_entry_estimator_diagnostics_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_entry_estimator_daily_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_entry_bucket_snapshot_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_entry_estimation_summary_20260518_ccusdt_v1_tfi_entry_estimation_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_entry_estimation.py
```

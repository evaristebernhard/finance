# CCUSDT V1 TFI Path Casebook Classes

Status: `20260519_ccusdt_v1_tfi_path_casebook_v1`.

Guardrail: `research_only_path_casebook_no_execution_recommendation`.

Input: `C:/Users/jiang/Desktop/finance_chain_full_handoff_20260508_r2/date/ccusdt_v1_tfi_release_decay_paths_20260518_ccusdt_v1_tfi_release_decay_factor_v1.csv`.

## Purpose

This report classifies entries by path mechanism, not by whether the
60s terminal result is negative. A profitable entry can still be a
case if it has the same release/decay geometry as a losing entry.

The path object is:

$$
R_i(t)=10^4s_i\log\frac{M_{t_i+t}}{M_{t_i}},
$$

with:

$$
H_i(t)=\max_{0<u\le t}R_i(u),\quad
D_i(t)=H_i(t)-R_i(t),\quad
E_i(t)=\frac{R_i(t)}{H_i(t)+\epsilon}.
$$

## Rules

The classes are deliberately simple and mutually exclusive:

1. `01_no_release_flat`: \(H_{60}<3\).
2. `03_large_release_plateau_decay`: \(H_{20}\ge10,\ E_{20}\ge0.75,\ \tau_H\le20,\ D_{60}\ge10\).
3. `04_late_release_collapse`: \(H_{60}\ge5,\ \tau_H\ge20,\ D_{60}\ge8\).
4. `02_fast_release_reversal`: \(H_{60}\ge4,\ \tau_H\le5,\ D_{60}\ge8\).

Priority is the order above. The plateau class is checked before the
fast-release class so that large moves that remain alive through 20s
are not mixed with immediate flash reversals.

## Headline

Total entries: `1455`.

Path cases: `717` (49.28% of entries).

Weighted gross 60s total, all entries: `8904.7590`.

Weighted gross 60s total, path cases: `-1549.6831`.

Weighted gross 60s total, non-cases: `10454.4421`.

The weighted gross metric uses the stored `target_exposure` and raw
\(R_{60}\). It is a path-severity lens, not a fresh sizing proposal.

## Class Summary

| path_case_class | entries | entry_share | gross60_positive_rate | gross60_weighted_total | R60_mean | H60_mean | tau_H60_mean | D60_mean | exposure_mean | worst_weighted_gross60 | best_weighted_gross60 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 00_non_case | 738 | 0.5072 | 0.8767 | 10454.4421 | 11.2886 | 14.1808 | 32.4042 | 2.8921 | 1.0728 | -40.7565 | 1262.3036 |
| 01_no_release_flat | 558 | 0.3835 | 0.2724 | -1812.0376 | -4.1829 | 0.5571 | 10.2813 | 4.7400 | 0.8757 | -193.6578 | 20.7779 |
| 02_fast_release_reversal | 41 | 0.0282 | 0.0732 | -936.2399 | -15.7895 | 8.5615 | 2.3309 | 24.3510 | 1.4451 | -235.9674 | 3.1462 |
| 03_large_release_plateau_decay | 25 | 0.0172 | 0.4000 | 306.4902 | -2.1507 | 20.5044 | 11.4459 | 22.6550 | 1.8000 | -95.2806 | 189.4239 |
| 04_late_release_collapse | 93 | 0.0639 | 0.5914 | 892.1041 | 9.6677 | 30.1854 | 36.5043 | 20.5176 | 0.9637 | -119.4105 | 550.8599 |

## Worst Daily Case Buckets

| date | path_case_class | entries | gross60_positive_rate | gross60_weighted_total | R60_mean | H60_mean | D60_mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | 01_no_release_flat | 57 | 0.2281 | -574.1298 | -8.0482 | 0.6342 | 8.6824 |
| 2026-05-15 | 01_no_release_flat | 55 | 0.2000 | -408.0164 | -7.3517 | 0.3788 | 7.7305 |
| 2026-05-14 | 02_fast_release_reversal | 16 | 0.0625 | -401.9225 | -14.8244 | 9.2893 | 24.1137 |
| 2026-05-09 | 02_fast_release_reversal | 5 | 0.0000 | -285.0999 | -37.7046 | 9.8202 | 47.5248 |
| 2026-05-12 | 01_no_release_flat | 45 | 0.2444 | -269.7115 | -4.2892 | 0.6552 | 4.9444 |
| 2026-05-14 | 01_no_release_flat | 63 | 0.2698 | -228.2526 | -6.6026 | 0.6684 | 7.2710 |
| 2026-05-12 | 02_fast_release_reversal | 4 | 0.0000 | -155.2225 | -17.3814 | 5.6505 | 23.0319 |
| 2026-05-13 | 01_no_release_flat | 63 | 0.2540 | -111.3037 | -3.5590 | 0.3409 | 3.8999 |
| 2026-05-14 | 03_large_release_plateau_decay | 10 | 0.3000 | -109.8120 | -4.8278 | 19.7314 | 24.5592 |
| 2026-05-11 | 01_no_release_flat | 60 | 0.3167 | -72.8078 | -2.5076 | 0.6882 | 3.1957 |
| 2026-05-10 | 01_no_release_flat | 49 | 0.3265 | -55.1783 | -2.9671 | 0.6844 | 3.6515 |
| 2026-05-10 | 04_late_release_collapse | 12 | 0.5833 | -41.7918 | 14.9471 | 32.0969 | 17.1498 |
| 2026-05-13 | 02_fast_release_reversal | 5 | 0.2000 | -37.9872 | -17.3745 | 7.3312 | 24.7057 |
| 2026-05-05 | 01_no_release_flat | 59 | 0.2712 | -33.6986 | -2.5068 | 0.5696 | 3.0764 |
| 2026-05-05 | 02_fast_release_reversal | 1 | 0.0000 | -30.3700 | -3.0370 | 5.0637 | 8.1007 |
| 2026-05-04 | 01_no_release_flat | 35 | 0.4286 | -24.2523 | -1.8307 | 0.6559 | 2.4865 |
| 2026-05-06 | 01_no_release_flat | 31 | 0.3226 | -23.1385 | -2.0482 | 0.4772 | 2.5254 |
| 2026-05-07 | 01_no_release_flat | 20 | 0.1000 | -13.2248 | -1.8873 | 0.2883 | 2.1755 |
| 2026-05-15 | 02_fast_release_reversal | 3 | 0.0000 | -10.8964 | -7.6376 | 7.1077 | 14.7453 |
| 2026-05-11 | 02_fast_release_reversal | 3 | 0.0000 | -5.9038 | -5.2478 | 5.3730 | 10.6208 |

## Case Classes By Cell

| path_case_class | cell | entries | gross60_positive_rate | gross60_weighted_total | R60_mean | H60_mean | D60_mean | exposure_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01_no_release_flat | 01_frames_only | 59 | 0.4915 | -52.8399 | -1.7646 | 0.9937 | 2.7583 | 0.3919 |
| 01_no_release_flat | 10_r5_only | 454 | 0.2313 | -860.4978 | -4.6443 | 0.4617 | 5.1060 | 0.3998 |
| 01_no_release_flat | 11_r5_frames | 45 | 0.4000 | -898.6999 | -2.6981 | 0.9476 | 3.6457 | 6.3111 |
| 02_fast_release_reversal | 01_frames_only | 7 | 0.2857 | -13.9463 | -4.8920 | 9.3352 | 14.2272 | 0.3036 |
| 02_fast_release_reversal | 10_r5_only | 29 | 0.0345 | -205.4068 | -18.2819 | 8.6219 | 26.9038 | 0.4526 |
| 02_fast_release_reversal | 11_r5_frames | 5 | 0.0000 | -716.8868 | -16.5905 | 7.1276 | 23.7181 | 8.8000 |
| 03_large_release_plateau_decay | 01_frames_only | 2 | 0.5000 | -1.0669 | -4.2675 | 20.6660 | 24.9335 | 0.1250 |
| 03_large_release_plateau_decay | 10_r5_only | 18 | 0.3333 | -33.8589 | -5.0161 | 18.2872 | 23.3034 | 0.3750 |
| 03_large_release_plateau_decay | 11_r5_frames | 5 | 0.6000 | 341.4160 | 9.0118 | 28.4214 | 19.4096 | 7.6000 |
| 04_late_release_collapse | 01_frames_only | 4 | 0.0000 | -20.0495 | -8.5218 | 15.0082 | 23.5301 | 0.5938 |
| 04_late_release_collapse | 10_r5_only | 78 | 0.6282 | 335.1184 | 11.4570 | 31.0043 | 19.5472 | 0.3750 |
| 04_late_release_collapse | 11_r5_frames | 11 | 0.5455 | 577.0352 | 3.5943 | 29.8977 | 26.3034 | 5.2727 |

## Examples

Each class keeps both the worst and best weighted examples. The best
examples are important because they show that the class is a mechanism,
not just a losing-label filter.

| path_case_class | example_side | date | entry_row | cell | direction_label | target_exposure | R5 | R10 | R20 | R60 | H60 | tau_H60 | D60 | weighted_gross60 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01_no_release_flat | best_weighted_gross60 | 2026-05-09 | 1601635 | 11_r5_frames | short | 8.0000 | 1.2724 | 1.2724 | 1.2724 | 1.2724 | 1.2724 | 2.4031 | 0.0000 | 10.1794 |
| 01_no_release_flat | best_weighted_gross60 | 2026-05-08 | 1462675 | 11_r5_frames | short | 8.0000 | 0.3432 | 0.3432 | 0.3432 | 1.3727 | 1.3727 | 55.8311 | 0.0000 | 10.9818 |
| 01_no_release_flat | best_weighted_gross60 | 2026-05-09 | 1597888 | 11_r5_frames | short | 10.0000 | -0.0000 | -0.0000 | 0.9660 | 1.2880 | 1.2880 | 27.2147 | 0.0000 | 12.8800 |
| 01_no_release_flat | best_weighted_gross60 | 2026-05-05 | 957318 | 11_r5_frames | short | 10.0000 | 0.3358 | 1.3432 | 1.3432 | 1.6791 | 1.6791 | 7.2538 | 0.0000 | 16.7906 |
| 01_no_release_flat | best_weighted_gross60 | 2026-05-11 | 1897558 | 11_r5_frames | short | 8.0000 | -0.3246 | -0.3246 | -0.3246 | 2.5972 | 2.5972 | 56.8246 | 0.0000 | 20.7779 |
| 01_no_release_flat | worst_weighted_gross60 | 2026-05-09 | 1604781 | 11_r5_frames | short | 8.0000 | 2.2623 | 2.2623 | -11.3040 | -24.2072 | 2.2623 | 0.0997 | 26.4696 | -193.6578 |
| 01_no_release_flat | worst_weighted_gross60 | 2026-05-15 | 2577885 | 11_r5_frames | short | 8.0000 | -0.0000 | -0.0000 | 0.3128 | -12.5039 | 0.6256 | 10.4073 | 13.1295 | -100.0313 |
| 01_no_release_flat | worst_weighted_gross60 | 2026-05-09 | 1642948 | 11_r5_frames | short | 8.0000 | -0.0000 | 0.3215 | 0.3215 | -12.2104 | 0.3215 | 5.7078 | 12.5319 | -97.6832 |
| 01_no_release_flat | worst_weighted_gross60 | 2026-05-12 | 2032427 | 11_r5_frames | short | 10.0000 | -0.0000 | -0.0000 | -0.0000 | -7.1563 | -0.0000 | 0.1158 | 7.1563 | -71.5630 |
| 01_no_release_flat | worst_weighted_gross60 | 2026-05-09 | 1580108 | 11_r5_frames | short | 10.0000 | -0.0000 | -0.0000 | -0.0000 | -7.0851 | -0.0000 | 0.9115 | 7.0851 | -70.8512 |
| 02_fast_release_reversal | best_weighted_gross60 | 2026-05-09 | 1667833 | 01_frames_only | short | 0.5000 | 4.4830 | 3.5222 | 3.5222 | -2.2408 | 5.7642 | 0.2992 | 8.0050 | -1.1204 |
| 02_fast_release_reversal | best_weighted_gross60 | 2026-05-14 | 2388173 | 10_r5_only | long | 0.3750 | 12.2839 | 12.2839 | -11.6837 | -1.2292 | 12.5908 | 3.6008 | 13.8200 | -0.4610 |
| 02_fast_release_reversal | best_weighted_gross60 | 2026-05-13 | 2198194 | 01_frames_only | long | 0.1250 | 14.0045 | 14.0045 | 8.4702 | 5.5390 | 14.0045 | 4.0120 | 8.4655 | 0.6924 |
| 02_fast_release_reversal | best_weighted_gross60 | 2026-05-14 | 2326533 | 01_frames_only | long | 0.1250 | 6.6879 | 5.7762 | 1.2163 | 6.9918 | 20.6574 | 2.0086 | 13.6656 | 0.8740 |
| 02_fast_release_reversal | best_weighted_gross60 | 2026-05-10 | 1714347 | 10_r5_only | short | 0.3750 | 21.3110 | 24.8672 | 14.5253 | 8.3898 | 27.1309 | 3.1007 | 18.7411 | 3.1462 |
| 02_fast_release_reversal | worst_weighted_gross60 | 2026-05-14 | 2377379 | 11_r5_frames | short | 10.0000 | 4.7260 | 4.7260 | -5.9044 | -23.5967 | 4.7260 | 3.2216 | 28.3228 | -235.9674 |
| 02_fast_release_reversal | worst_weighted_gross60 | 2026-05-09 | 1615412 | 11_r5_frames | short | 8.0000 | 12.5612 | 2.5110 | 2.5110 | -27.8923 | 12.5612 | 4.7051 | 40.4535 | -223.1382 |
| 02_fast_release_reversal | worst_weighted_gross60 | 2026-05-12 | 2039581 | 11_r5_frames | short | 8.0000 | 7.1534 | 7.1534 | 0.3109 | -17.3956 | 7.1534 | 4.0565 | 24.5490 | -139.1650 |
| 02_fast_release_reversal | worst_weighted_gross60 | 2026-05-14 | 2414246 | 11_r5_frames | short | 8.0000 | 6.1335 | 6.1335 | 6.1335 | -11.0308 | 6.1335 | 1.6015 | 17.1642 | -88.2461 |
| 02_fast_release_reversal | worst_weighted_gross60 | 2026-05-09 | 1555985 | 10_r5_only | short | 0.3750 | -8.4451 | -14.6121 | -14.6121 | -112.1265 | 5.8508 | 0.5105 | 117.9774 | -42.0475 |
| 03_large_release_plateau_decay | best_weighted_gross60 | 2026-05-15 | 2584006 | 10_r5_only | long | 0.3750 | 23.6537 | 19.2426 | 18.9275 | 11.0454 | 23.6537 | 3.7033 | 12.6084 | 4.1420 |
| 03_large_release_plateau_decay | best_weighted_gross60 | 2026-05-09 | 1571805 | 10_r5_only | short | 0.3750 | -0.0000 | 20.1249 | 25.8823 | 13.7317 | 25.8823 | 12.3077 | 12.1507 | 5.1494 |
| 03_large_release_plateau_decay | best_weighted_gross60 | 2026-05-11 | 1955577 | 11_r5_frames | short | 8.0000 | 30.1641 | 30.1641 | 30.1641 | 7.2311 | 30.1641 | 3.5340 | 22.9330 | 57.8488 |
| 03_large_release_plateau_decay | best_weighted_gross60 | 2026-05-15 | 2462724 | 11_r5_frames | short | 8.0000 | -0.0000 | -0.0000 | 35.5380 | 23.6780 | 37.9726 | 11.8095 | 14.2946 | 189.4239 |
| 03_large_release_plateau_decay | best_weighted_gross60 | 2026-05-15 | 2462725 | 11_r5_frames | short | 8.0000 | -0.0000 | -0.0000 | 35.5380 | 23.6780 | 37.9726 | 11.7101 | 14.2946 | 189.4239 |
| 03_large_release_plateau_decay | worst_weighted_gross60 | 2026-05-14 | 2361187 | 11_r5_frames | short | 10.0000 | 18.4865 | 24.1586 | 24.4572 | -9.5281 | 24.4572 | 12.7038 | 33.9852 | -95.2806 |
| 03_large_release_plateau_decay | worst_weighted_gross60 | 2026-05-15 | 2580340 | 10_r5_only | short | 0.3750 | -0.0000 | 11.0572 | 12.0056 | -43.7927 | 12.0056 | 15.0074 | 55.7983 | -16.4223 |
| 03_large_release_plateau_decay | worst_weighted_gross60 | 2026-05-14 | 2391387 | 10_r5_only | short | 0.3750 | 10.0120 | 10.9227 | 10.9227 | -14.2422 | 10.9227 | 9.6218 | 25.1649 | -5.3408 |
| 03_large_release_plateau_decay | worst_weighted_gross60 | 2026-05-14 | 2391064 | 10_r5_only | short | 0.3750 | 11.2597 | 11.2597 | 11.2597 | -12.7660 | 11.2597 | 3.9013 | 24.0257 | -4.7872 |
| 03_large_release_plateau_decay | worst_weighted_gross60 | 2026-05-14 | 2346538 | 10_r5_only | long | 0.3750 | 0.0000 | 12.9337 | 18.3428 | -12.0464 | 24.3496 | 16.3072 | 36.3959 | -4.5174 |
| 04_late_release_collapse | best_weighted_gross60 | 2026-05-09 | 1604520 | 10_r5_only | short | 0.3750 | 13.1501 | 70.4421 | 52.0600 | 70.4421 | 115.7349 | 32.2227 | 45.2929 | 26.4158 |
| 04_late_release_collapse | best_weighted_gross60 | 2026-05-10 | 1777588 | 10_r5_only | short | 0.3750 | 4.1050 | 5.6843 | 5.6843 | 73.8315 | 94.5259 | 43.6854 | 20.6944 | 27.6868 |
| 04_late_release_collapse | best_weighted_gross60 | 2026-05-14 | 2368945 | 11_r5_frames | short | 8.0000 | 12.2843 | 12.2843 | 12.2843 | 8.1879 | 17.2608 | 22.7137 | 9.0730 | 65.5028 |
| 04_late_release_collapse | best_weighted_gross60 | 2026-05-15 | 2583437 | 11_r5_frames | long | 4.0000 | 0.6450 | 0.6450 | 0.6450 | 69.7360 | 115.4266 | 55.3366 | 45.6906 | 278.9438 |
| 04_late_release_collapse | best_weighted_gross60 | 2026-05-14 | 2337243 | 11_r5_frames | short | 8.0000 | 0.6020 | 0.6020 | 11.7447 | 68.8575 | 79.4698 | 51.1233 | 10.6123 | 550.8599 |
| 04_late_release_collapse | worst_weighted_gross60 | 2026-05-14 | 2334597 | 11_r5_frames | long | 2.0000 | 0.0000 | 0.3006 | 0.3006 | -59.7053 | 13.5198 | 22.6077 | 73.2251 | -119.4105 |
| 04_late_release_collapse | worst_weighted_gross60 | 2026-05-15 | 2540829 | 11_r5_frames | long | 2.0000 | 6.9806 | 7.2978 | 7.2978 | -42.9424 | 7.9321 | 36.9245 | 50.8745 | -85.8848 |
| 04_late_release_collapse | worst_weighted_gross60 | 2026-05-10 | 1785626 | 11_r5_frames | short | 8.0000 | 0.3199 | 0.3199 | 0.3199 | -10.5497 | 8.3197 | 28.4455 | 18.8694 | -84.3976 |
| 04_late_release_collapse | worst_weighted_gross60 | 2026-05-14 | 2357217 | 11_r5_frames | short | 10.0000 | -0.0000 | -0.0000 | 0.2979 | -3.8718 | 7.1518 | 43.4274 | 11.0236 | -38.7176 |
| 04_late_release_collapse | worst_weighted_gross60 | 2026-05-10 | 1781104 | 11_r5_frames | long | 4.0000 | 5.0644 | 5.0644 | 5.0644 | -7.6014 | 10.4425 | 28.9195 | 18.0440 | -30.4057 |

## Interpretation

- `01_no_release_flat` is mostly an entry/size problem: the entry did not
  receive a meaningful favorable price release within 60s.
- `02_fast_release_reversal` is the closest to the canonical flash/transient
  pathology: peak arrives very early and the terminal giveback is large.
- `03_large_release_plateau_decay` is not simply bad. It can be positive
  in aggregate, but it shows the exact window where profit has already
  been released and then remains exposed to reversal.
- `04_late_release_collapse` contains many profitable entries. The issue is
  not entry invalidity; it is that fixed 60s holding mixes late peak
  capture with late giveback.

The next useful programming step is not a larger model. It is to test
whether simple path actions map to these classes: reduce no-release
exposure, protect fast transients quickly, and harvest plateau/late
release after the peak stops improving.

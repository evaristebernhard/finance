# CCUSDT V1 TFI Watcher-Aware Pareto

Status: `20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1`.

Guardrail: `research_only_watcher_aware_pareto_no_execution_recommendation`.

## Scope

This is the historical Pareto pass for the restrained rule family:

```text
full scored four-cell universe
-> pm_11_drawdown_h4_peakguard where rebuilt
-> fixed60 fallback where path is not rebuilt
-> optional post-exit watcher where rebuilt
-> gamma sizing by mutually exclusive cell, including 00
```

The optimized historical universe is now the full scored universe:
`3365` entries from `2026-05-04` to `2026-05-17`.

Cell counts:

| cell | entries |
| --- | --- |
| 00_none | 1234 |
| 01_frames_only | 135 |
| 10_r5_only | 1796 |
| 11_r5_frames | 200 |

Path overlay coverage:

| path_overlay_source | entries |
| --- | --- |
| fixed60_fallback | 1910 |
| path_manager_rebuilt | 1455 |

`00_none` is intentionally included in the sizing universe. Where no
path-manager/watch rebuild exists, it uses the fixed60 zero-fee payoff
as a fallback rather than disappearing from concurrency and gamma risk.

## Main Result

At the full anchor:

```text
manager_only                 total 13277.3761
manager_plus_q70_watcher     total 13799.5700
q70 watcher delta            total 522.1939
anchor q70 scaled100         2299.9283
anchor q70 max concurrency   18.0000
```

The 100-budget + 3x Pareto should now be read as a four-cell sizing
problem, not an A/B-only watcher problem. The cleaner q70 scaled leader is:

```text
strategy      manager_plus_q70_watcher
variant       grid_g00_1.25_g10_0.75_g01_0_g11_0.75
gamma         (00=1.2500, 10=0.7500, 01=0.0000, 11=0.7500)
raw total     6042.8705
scaled100     5371.4405
worst day     8.2022
entry worst   -76.0697
max conc      3.3750
```

At that q70 leader, contribution by cell is:

| cell | entries | exposure | total | mean | worst_entry |
| --- | --- | --- | --- | --- | --- |
| 00_none | 1234 | 793.7500 | 1935.3368 | 2.4382 | -76.0697 |
| 01_frames_only | 135 | 0.0000 | 0.0000 |  | 0.0000 |
| 10_r5_only | 1796 | 700.5000 | 2279.9815 | 3.2548 | -54.7924 |
| 11_r5_frames | 200 | 234.0000 | 1827.5522 | 7.8101 | -36.3108 |

The q65 sensitivity has a slightly higher scaled value:

```text
q65 best scaled100 5418.2873
q70 best scaled100 5371.4405
difference         46.8468
```

That small gap is not enough evidence to promote q65; it is still the
recall sensitivity. Under a 1bps pressure term, the q70 leader remains
near the same balanced low-concurrency point; under 2bps pressure, q70
moves toward much lower broad `00` and higher `11`, which is the warning
that weak/broad exposure becomes expensive once non-fee pressure is added:

```text
C=1 q70 leader grid_g00_1.25_g10_0.75_g01_0_g11_0.75, scaled100 3832.8849
C=2 q70 leader grid_g00_0_g10_1.25_g01_0.75_g11_1.5, scaled100 1999.7536
```

## Model

The full anchor exposure is decomposed as:

$$
w_i^{anchor}=b_i\gamma^{anchor}_{c_i},\qquad
\gamma^{anchor}_{00}=1,\ \gamma^{anchor}_{10}=0.75,\ \gamma^{anchor}_{01}=0.25,\ \gamma^{anchor}_{11}=4.
$$

Pareto only changes:

$$
w_i=b_i\gamma_{c_i},\qquad c_i\in\{00,10,01,11\}.
$$

For watcher variants, per-unit path payoff is:

$$
y_i=R_i^{manager}+1_{\{trigger\}}R_i^{reentry}.
$$

Pressure tests subtract one cost unit per opened leg:

$$
y_i(c)=R_i^{manager}-c+1_{\{trigger\}}(R_i^{reentry}-c).
$$

## Anchor Rule Comparison

| pressure_bps | strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | entries | exposure | total | mean | worst_day | entry_worst | max_concurrent_exposure | cap_by_exchange_leverage | feasible_cap_100 | scaled_total_100 | watch_trigger_count | watch_trigger_weighted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | fixed60 | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 12615.5996 | 4.7761 | 47.4094 | -235.9674 | 18.0000 | 0.1667 | 0.1667 | 2102.5999 | 0 | 0.0000 |
| 0.0000 | manager_only | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 13277.3761 | 5.0267 | 47.4094 | -193.6578 | 18.0000 | 0.1667 | 0.1667 | 2212.8960 | 0 | 0.0000 |
| 0.0000 | manager_plus_impulse | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 13498.3143 | 5.1103 | 47.4094 | -193.6578 | 18.0000 | 0.1667 | 0.1667 | 2249.7191 | 1 | 220.9383 |
| 0.0000 | manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 14080.6509 | 5.3308 | 47.4094 | -193.6578 | 18.0000 | 0.1667 | 0.1667 | 2346.7751 | 5 | 803.2748 |
| 0.0000 | manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 13799.5700 | 5.2244 | 47.4094 | -193.6578 | 18.0000 | 0.1667 | 0.1667 | 2299.9283 | 3 | 522.1939 |
| 1.0000 | fixed60 | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 9974.2246 | 3.7761 | -48.2156 | -245.9674 | 18.0000 | 0.1667 | 0.1667 | 1662.3708 | 0 | 0.0000 |
| 1.0000 | manager_only | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 10636.0011 | 4.0267 | -48.2156 | -201.6578 | 18.0000 | 0.1667 | 0.1667 | 1772.6668 | 0 | 0.0000 |
| 1.0000 | manager_plus_impulse | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 10852.9393 | 4.1088 | -48.2156 | -201.6578 | 18.0000 | 0.1667 | 0.1667 | 1808.8232 | 1 | 216.9383 |
| 1.0000 | manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 11407.2759 | 4.3187 | -48.2156 | -201.6578 | 18.0000 | 0.1667 | 0.1667 | 1901.2126 | 5 | 771.2748 |
| 1.0000 | manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 11144.1950 | 4.2191 | -48.2156 | -201.6578 | 18.0000 | 0.1667 | 0.1667 | 1857.3658 | 3 | 508.1939 |
| 2.0000 | fixed60 | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 7332.8496 | 2.7761 | -143.8406 | -255.9674 | 18.0000 | 0.1667 | 0.1667 | 1222.1416 | 0 | 0.0000 |
| 2.0000 | manager_only | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 7994.6261 | 3.0267 | -143.8406 | -209.6578 | 18.0000 | 0.1667 | 0.1667 | 1332.4377 | 0 | 0.0000 |
| 2.0000 | manager_plus_impulse | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 8207.5643 | 3.1073 | -143.8406 | -209.6578 | 18.0000 | 0.1667 | 0.1667 | 1367.9274 | 1 | 212.9383 |
| 2.0000 | manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 8733.9009 | 3.3066 | -143.8406 | -209.6578 | 18.0000 | 0.1667 | 0.1667 | 1455.6501 | 5 | 739.2748 |
| 2.0000 | manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 8488.8200 | 3.2138 | -143.8406 | -209.6578 | 18.0000 | 0.1667 | 0.1667 | 1414.8033 | 3 | 494.1939 |

## Top C0 Historical Variants By 100-Budget Scaled Total

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | entries | exposure | total | mean | worst_day | entry_worst | max_concurrent_exposure | cap_by_exchange_leverage | feasible_cap_100 | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 3230 | 1728.2500 | 6095.5732 | 3.5270 | 8.2022 | -76.0697 | 3.3750 | 0.8889 | 0.8889 | 5418.2873 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 3230 | 1728.2500 | 6042.8705 | 3.4965 | 8.2022 | -76.0697 | 3.3750 | 0.8889 | 0.8889 | 5371.4405 | 3 |
| manager_plus_impulse | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 3230 | 1728.2500 | 5986.3851 | 3.4638 | 8.2022 | -76.0697 | 3.3750 | 0.8889 | 0.8889 | 5321.2312 | 1 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 3365 | 2213.3750 | 8155.4407 | 3.6846 | 44.4010 | -76.0697 | 4.6250 | 0.6486 | 0.6486 | 5290.0156 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1 | 1.2500 | 1.0000 | 0.5000 | 1.0000 | 3365 | 2155.5000 | 7931.0667 | 3.6795 | 34.3695 | -76.0697 | 4.5000 | 0.6667 | 0.6667 | 5287.3778 | 5 |
| manager_only | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 3230 | 1728.2500 | 5944.9592 | 3.4399 | 8.2022 | -76.0697 | 3.3750 | 0.8889 | 0.8889 | 5284.4081 | 0 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_0.75 | 1.0000 | 0.7500 | 0.5000 | 0.7500 | 3365 | 1685.2500 | 6157.2539 | 3.6536 | 30.2874 | -60.8558 | 3.5000 | 0.8571 | 0.8571 | 5277.6462 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.25_g11_0.75 | 1.0000 | 0.7500 | 0.2500 | 0.7500 | 3365 | 1627.3750 | 5932.8799 | 3.6457 | 20.2558 | -60.8558 | 3.3750 | 0.8889 | 0.8889 | 5273.6710 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.5_g01_0.25_g11_0.5 | 0.7500 | 0.5000 | 0.2500 | 0.5000 | 3365 | 1157.1250 | 4159.0670 | 3.5943 | 16.1737 | -45.6418 | 2.3750 | 1.2632 | 1.2632 | 5253.5584 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.5_g01_0_g11_0.5 | 0.7500 | 0.5000 | 0.0000 | 0.5000 | 3230 | 1099.2500 | 3934.6930 | 3.5794 | 6.1421 | -45.6418 | 2.2500 | 1.3333 | 1.3333 | 5246.2573 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 3365 | 2213.3750 | 8085.1705 | 3.6529 | 44.4010 | -76.0697 | 4.6250 | 0.6486 | 0.6486 | 5244.4349 | 3 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1 | 1.2500 | 1.0000 | 0.5000 | 1.0000 | 3365 | 2155.5000 | 7860.7965 | 3.6469 | 34.3695 | -76.0697 | 4.5000 | 0.6667 | 0.6667 | 5240.5310 | 3 |
| manager_plus_q70_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_0.75 | 1.0000 | 0.7500 | 0.5000 | 0.7500 | 3365 | 1685.2500 | 6104.5512 | 3.6223 | 30.2874 | -60.8558 | 3.5000 | 0.8571 | 0.8571 | 5232.4725 | 3 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0.25_g11_0.75 | 1.2500 | 0.7500 | 0.2500 | 0.7500 | 3365 | 1786.1250 | 6319.9472 | 3.5384 | 18.2337 | -76.0697 | 3.6250 | 0.8276 | 0.8276 | 5230.3011 | 5 |
| manager_plus_q70_watcher | grid_g00_1_g10_0.75_g01_0.25_g11_0.75 | 1.0000 | 0.7500 | 0.2500 | 0.7500 | 3365 | 1627.3750 | 5880.1772 | 3.6133 | 20.2558 | -60.8558 | 3.3750 | 0.8889 | 0.8889 | 5226.8242 | 3 |
| manager_plus_q70_watcher | grid_g00_0.75_g10_0.5_g01_0.25_g11_0.5 | 0.7500 | 0.5000 | 0.2500 | 0.5000 | 3365 | 1157.1250 | 4123.9319 | 3.5639 | 16.1737 | -45.6418 | 2.3750 | 1.2632 | 1.2632 | 5209.1772 | 3 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.25 | 1.2500 | 1.2500 | 1.0000 | 1.2500 | 3365 | 2582.7500 | 9766.5602 | 3.7815 | 60.5368 | -91.3207 | 5.6250 | 0.5333 | 0.5333 | 5208.8321 | 5 |
| manager_plus_q70_watcher | grid_g00_0.75_g10_0.5_g01_0_g11_0.5 | 0.7500 | 0.5000 | 0.0000 | 0.5000 | 3230 | 1099.2500 | 3899.5579 | 3.5475 | 6.1421 | -45.6418 | 2.2500 | 1.3333 | 1.3333 | 5199.4105 | 3 |
| manager_plus_impulse | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 3365 | 2213.3750 | 8009.8566 | 3.6188 | 44.4010 | -76.0697 | 4.6250 | 0.6486 | 0.6486 | 5195.5827 | 1 |
| manager_plus_impulse | grid_g00_1.25_g10_1_g01_0.5_g11_1 | 1.2500 | 1.0000 | 0.5000 | 1.0000 | 3365 | 2155.5000 | 7785.4826 | 3.6119 | 34.3695 | -76.0697 | 4.5000 | 0.6667 | 0.6667 | 5190.3217 | 1 |

## Pareto Frontier C0

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | daily_cvar20 | entry_cvar05 | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 6095.5732 | 3.5270 | 8.2022 | 42.6206 | -15.0940 | 5418.2873 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 8155.4407 | 3.6846 | 44.4010 | 66.6111 | -18.2424 | 5290.0156 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1 | 1.2500 | 1.0000 | 0.5000 | 1.0000 | 7931.0667 | 3.6795 | 34.3695 | 60.4384 | -17.6976 | 5287.3778 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_0.75 | 1.0000 | 0.7500 | 0.5000 | 0.7500 | 6157.2539 | 3.6536 | 30.2874 | 49.7253 | -13.8752 | 5277.6462 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.25_g11_0.75 | 1.0000 | 0.7500 | 0.2500 | 0.7500 | 5932.8799 | 3.6457 | 20.2558 | 43.5527 | -13.3856 | 5273.6710 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.5_g01_0.25_g11_0.5 | 0.7500 | 0.5000 | 0.2500 | 0.5000 | 4159.0670 | 3.5943 | 16.1737 | 32.8395 | -9.5489 | 5253.5584 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.5_g01_0_g11_0.5 | 0.7500 | 0.5000 | 0.0000 | 0.5000 | 3934.6930 | 3.5794 | 6.1421 | 26.6669 | -9.5390 | 5246.2573 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0.25_g11_0.75 | 1.2500 | 0.7500 | 0.2500 | 0.7500 | 6319.9472 | 3.5384 | 18.2337 | 48.7932 | -14.8638 | 5230.3011 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.25 | 1.2500 | 1.2500 | 1.0000 | 1.2500 | 9766.5602 | 3.7815 | 60.5368 | 78.2563 | -21.3359 | 5208.8321 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.5_g01_0_g11_0.5 | 1.0000 | 0.5000 | 0.0000 | 0.5000 | 4321.7604 | 3.4354 | 4.1201 | 31.9074 | -11.1628 | 5186.1124 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.75_g11_1 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 7768.3734 | 3.7809 | 46.4231 | 61.3705 | -16.9475 | 5178.9156 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.75_g01_0.5_g11_0.75 | 0.7500 | 0.7500 | 0.5000 | 0.7500 | 5770.1865 | 3.7800 | 32.3094 | 44.4847 | -12.5599 | 5129.0547 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_0.75_g11_1.25 | 1.2500 | 1.2500 | 0.7500 | 1.2500 | 9542.1862 | 3.7793 | 50.5052 | 72.0837 | -20.7377 | 5089.1660 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.5_g11_1 | 1.0000 | 1.0000 | 0.5000 | 1.0000 | 7543.9994 | 3.7781 | 36.3915 | 55.1979 | -16.3681 | 5029.3329 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_0.5_g01_0.25_g11_0.5 | 0.5000 | 0.5000 | 0.2500 | 0.5000 | 3771.9997 | 3.7781 | 18.1958 | 27.5989 | -8.1840 | 5029.3329 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1.25_g01_1_g11_1.25 | 1.0000 | 1.2500 | 1.0000 | 1.2500 | 9379.4929 | 3.8694 | 62.5588 | 73.0157 | -20.1339 | 5002.3962 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.5_g01_1_g11_1.5 | 1.2500 | 1.5000 | 1.0000 | 1.5000 | 11153.3057 | 3.8536 | 66.6409 | 83.7289 | -23.9100 | 4957.0248 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.75_g01_0.25_g11_0.75 | 0.7500 | 0.7500 | 0.2500 | 0.7500 | 5545.8125 | 3.7762 | 22.2779 | 38.3121 | -12.0262 | 4929.6111 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_1_g01_0.75_g11_1 | 0.7500 | 1.0000 | 0.7500 | 1.0000 | 7381.3060 | 3.8934 | 48.4452 | 56.1299 | -15.7558 | 4920.8707 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_1_g11_1 | 1.2500 | 1.0000 | 1.0000 | 1.0000 | 8379.8148 | 3.6895 | 54.4326 | 72.7837 | -18.8458 | 4905.2574 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1.25_g01_0.75_g11_1.25 | 1.0000 | 1.2500 | 0.7500 | 1.2500 | 9155.1189 | 3.8692 | 52.5273 | 66.8431 | -19.5306 | 4882.7301 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.5_g01_0.75_g11_1.5 | 1.2500 | 1.5000 | 0.7500 | 1.5000 | 10928.9317 | 3.8531 | 56.6094 | 77.5562 | -23.3327 | 4857.3030 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_1_g11_1.25 | 1.2500 | 1.0000 | 1.0000 | 1.2500 | 9006.5664 | 3.8338 | 56.5214 | 75.9979 | -19.3390 | 4803.5021 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0.75_g11_1 | 1.2500 | 0.7500 | 0.7500 | 1.0000 | 7395.4469 | 3.7353 | 40.3856 | 64.3526 | -16.3802 | 4797.0466 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_1.25_g01_1_g11_1.25 | 0.7500 | 1.2500 | 1.0000 | 1.2500 | 8992.4255 | 3.9697 | 64.5809 | 67.7751 | -19.0622 | 4795.9603 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.75_g01_0.75_g11_0.75 | 0.7500 | 0.7500 | 0.7500 | 0.7500 | 5994.5606 | 3.7835 | 42.3410 | 50.6574 | -13.1713 | 4795.6485 | 5 |
| manager_plus_q65_watcher | all1 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 7992.7474 | 3.7835 | 56.4547 | 67.5432 | -17.5617 | 4795.6485 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_0.5_g01_0.5_g11_0.5 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 3996.3737 | 3.7835 | 28.2273 | 33.7716 | -8.7808 | 4795.6485 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.75_g11_0.75 | 1.0000 | 0.7500 | 0.7500 | 0.7500 | 6381.6279 | 3.6610 | 40.3189 | 55.8979 | -14.4641 | 4786.2209 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1.5_g01_1_g11_1.5 | 1.0000 | 1.5000 | 1.0000 | 1.5000 | 10766.2383 | 3.9357 | 68.6630 | 78.4883 | -22.7814 | 4784.9948 | 5 |

## Pressure Sensitivity

Top C=1:

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 4361.3232 | 2.5235 | -68.7978 | 3876.7317 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 5934.0657 | 2.6810 | -51.8490 | 3849.1237 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1 | 1.2500 | 1.0000 | 0.5000 | 1.0000 | 5767.5667 | 2.6757 | -59.5055 | 3845.0445 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 4311.9955 | 2.4950 | -68.7978 | 3832.8849 | 3 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_0.75 | 1.0000 | 0.7500 | 0.5000 | 0.7500 | 4466.0039 | 2.6501 | -43.3376 | 3828.0033 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.25 | 1.2500 | 1.2500 | 1.0000 | 1.2500 | 7173.8102 | 2.7776 | -50.2132 | 3826.0321 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.25_g11_0.75 | 1.0000 | 0.7500 | 0.2500 | 0.7500 | 4299.5049 | 2.6420 | -50.9942 | 3821.7821 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 5868.2955 | 2.6513 | -51.8490 | 3806.4620 | 3 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.75_g11_1 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 5705.7484 | 2.7770 | -41.7019 | 3803.8323 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1 | 1.2500 | 1.0000 | 0.5000 | 1.0000 | 5701.7965 | 2.6452 | -59.5055 | 3801.1977 | 3 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.5_g01_0.25_g11_0.5 | 0.7500 | 0.5000 | 0.2500 | 0.5000 | 2997.9420 | 2.5909 | -34.8263 | 3786.8742 | 5 |
| manager_plus_q70_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_0.75 | 1.0000 | 0.7500 | 0.5000 | 0.7500 | 4416.6762 | 2.6208 | -43.3376 | 3785.7225 | 3 |

Top C=2:

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_0_g10_1.25_g01_0.75_g11_1.5 | 0.0000 | 1.2500 | 0.7500 | 1.5000 | 4591.3510 | 2.5379 | -224.0532 | 2040.6005 | 5 |
| manager_plus_q70_watcher | grid_g00_0_g10_1.25_g01_0.75_g11_1.5 | 0.0000 | 1.2500 | 0.7500 | 1.5000 | 4499.4457 | 2.4871 | -224.0532 | 1999.7536 | 3 |
| manager_plus_q65_watcher | grid_g00_0_g10_1_g01_0.75_g11_1.25 | 0.0000 | 1.0000 | 0.7500 | 1.2500 | 3831.6056 | 2.5585 | -192.2703 | 1992.8224 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_1_g01_1_g11_1.5 | 0.2500 | 1.0000 | 1.0000 | 1.5000 | 4476.5486 | 2.4977 | -204.2019 | 1989.5771 | 5 |
| manager_plus_q65_watcher | grid_g00_0_g10_1_g01_0.5_g11_1.25 | 0.0000 | 1.0000 | 0.5000 | 1.2500 | 3722.9815 | 2.5859 | -170.7210 | 1985.5902 | 5 |
| manager_plus_q65_watcher | grid_g00_0_g10_2_g01_1_g11_2.5 | 0.0000 | 2.0000 | 1.0000 | 2.5000 | 7445.9631 | 2.5859 | -341.4420 | 1985.5902 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_1.5_g01_1_g11_2 | 0.2500 | 1.5000 | 1.0000 | 2.0000 | 5996.0395 | 2.4826 | -267.7678 | 1982.8529 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_0.75_g01_1_g11_1.25 | 0.2500 | 0.7500 | 1.0000 | 1.2500 | 3716.8031 | 2.5101 | -172.4190 | 1982.2950 | 5 |
| manager_plus_q65_watcher | grid_g00_0_g10_0.75_g01_0.5_g11_1 | 0.0000 | 0.7500 | 0.5000 | 1.0000 | 2963.2361 | 2.6264 | -138.9381 | 1975.4907 | 5 |
| manager_plus_q65_watcher | grid_g00_0_g10_1.5_g01_1_g11_2 | 0.0000 | 1.5000 | 1.0000 | 2.0000 | 5926.4721 | 2.6264 | -277.8761 | 1975.4907 | 5 |
| manager_plus_q65_watcher | grid_g00_0_g10_1_g01_1_g11_1.5 | 0.0000 | 1.0000 | 1.0000 | 1.5000 | 4406.9812 | 2.6979 | -214.3103 | 1958.6583 | 5 |
| manager_plus_q65_watcher | grid_g00_0_g10_0.5_g01_0.5_g11_0.75 | 0.0000 | 0.5000 | 0.5000 | 0.7500 | 2203.4906 | 2.6979 | -107.1551 | 1958.6583 | 5 |

## Strategy Summary

| strategy | best_scaled_variant | best_scaled_total_100 | best_scaled_raw_total | best_scaled_worst_day | best_scaled_entry_worst | best_scaled_max_concurrent | anchor_total | anchor_scaled_total_100 | anchor_watch_triggers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 5418.2873 | 6095.5732 | 8.2022 | -76.0697 | 3.3750 | 14080.6509 | 2346.7751 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 5371.4405 | 6042.8705 | 8.2022 | -76.0697 | 3.3750 | 13799.5700 | 2299.9283 | 3 |
| manager_plus_impulse | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 5321.2312 | 5986.3851 | 8.2022 | -76.0697 | 3.3750 | 13498.3143 | 2249.7191 | 1 |
| manager_only | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 5284.4081 | 5944.9592 | 8.2022 | -76.0697 | 3.3750 | 13277.3761 | 2212.8960 | 0 |
| fixed60 | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 5173.9749 | 5820.7217 | 8.2022 | -76.0697 | 3.3750 | 12615.5996 | 2102.5999 | 0 |

## Cell Summary

| strategy | cell | entries | base_exposure | base_weighted_total | base_mean | positive_unit_rate | unit_worst | unit_cvar05 | watch_triggers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed60 | 00_none | 1234 | 635.0000 | 1548.2694 | 2.4382 | 0.5575 | -121.7115 | -26.6744 | 0 |
| fixed60 | 01_frames_only | 135 | 231.5000 | 900.7889 | 3.8911 | 0.6667 | -33.8377 | -16.0805 | 0 |
| fixed60 | 10_r5_only | 1796 | 934.0000 | 3039.9754 | 3.2548 | 0.5663 | -146.1132 | -30.7267 | 0 |
| fixed60 | 11_r5_frames | 200 | 312.0000 | 2140.5379 | 6.8607 | 0.7300 | -59.7053 | -25.0913 | 0 |
| manager_only | 00_none | 1234 | 635.0000 | 1548.2694 | 2.4382 | 0.5575 | -121.7115 | -26.6744 | 0 |
| manager_only | 01_frames_only | 135 | 231.5000 | 897.4961 | 3.8769 | 0.6741 | -33.8377 | -16.0805 | 0 |
| manager_only | 10_r5_only | 1796 | 934.0000 | 3039.9754 | 3.2548 | 0.5663 | -146.1132 | -30.7267 | 0 |
| manager_only | 11_r5_frames | 200 | 312.0000 | 2306.1878 | 7.3916 | 0.7400 | -36.4493 | -14.8676 | 0 |
| manager_plus_q70_watcher | 00_none | 1234 | 635.0000 | 1548.2694 | 2.4382 | 0.5575 | -121.7115 | -26.6744 | 0 |
| manager_plus_q70_watcher | 01_frames_only | 135 | 231.5000 | 897.4961 | 3.8769 | 0.6741 | -33.8377 | -16.0805 | 0 |
| manager_plus_q70_watcher | 10_r5_only | 1796 | 934.0000 | 3039.9754 | 3.2548 | 0.5663 | -146.1132 | -30.7267 | 0 |
| manager_plus_q70_watcher | 11_r5_frames | 200 | 312.0000 | 2436.7362 | 7.8101 | 0.7500 | -36.4493 | -14.8676 | 3 |

## Walk-Forward Sanity

This walk-forward chooses among `manager_only`, `manager_plus_impulse`,
and `manager_plus_q70_watcher` using only prior dates. It is a sanity
check, not a final live selection rule.

| test_date | chosen_strategy | chosen_variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | test_total | test_mean | test_watch_trigger_count | anchor_q70_total | manager_anchor_total | anchor_q70_delta_vs_manager |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | manager_only | grid_g00_0.75_g10_0.5_g01_0.25_g11_0.5 | 0.7500 | 0.5000 | 0.2500 | 0.5000 | 455.5299 | 4.6841 | 0 | 867.8752 | 867.8752 | 0.0000 |
| 2026-05-10 | manager_only | grid_g00_0.75_g10_0.5_g01_0.25_g11_0.5 | 0.7500 | 0.5000 | 0.2500 | 0.5000 | 260.2746 | 3.3967 | 0 | 597.3795 | 597.3795 | 0.0000 |
| 2026-05-11 | manager_only | grid_g00_0.75_g10_0.5_g01_0.25_g11_0.5 | 0.7500 | 0.5000 | 0.2500 | 0.5000 | 297.1169 | 2.5752 | 0 | 854.7620 | 854.7620 | 0.0000 |
| 2026-05-12 | manager_only | grid_g00_1.25_g10_1_g01_0.5_g11_1 | 1.2500 | 1.0000 | 0.5000 | 1.0000 | 567.2935 | 3.6336 | 0 | 1036.0113 | 1036.0113 | 0.0000 |
| 2026-05-13 | manager_only | grid_g00_1.25_g10_1.25_g01_0.75_g11_1.25 | 1.2500 | 1.2500 | 0.7500 | 1.2500 | 212.4790 | 1.1024 | 0 | 287.1568 | 287.1568 | 0.0000 |
| 2026-05-14 | manager_only | grid_g00_1.25_g10_0.75_g01_0.5_g11_0.75 | 1.2500 | 0.7500 | 0.5000 | 0.7500 | 1451.7595 | 6.7056 | 0 | 4190.9081 | 3889.6525 | 301.2557 |
| 2026-05-15 | manager_plus_q70_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 1290.6396 | 8.3133 | 1 | 3085.0320 | 2864.0938 | 220.9383 |
| 2026-05-16 | manager_plus_q70_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 263.0807 | 1.8741 | 0 | 756.9663 | 756.9663 | 0.0000 |
| 2026-05-17 | manager_plus_q70_watcher | grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | 1.2500 | 0.7500 | 0.0000 | 0.7500 | 487.6552 | 4.5897 | 0 | 1113.7769 | 1113.7769 | 0.0000 |

## Q70 Watcher Trigger Rows

| date | entry_row | cell | direction_label | base_weight | target_exposure | policy_gross | watch_final_pnl_watcher_q70_absorb_reclaim2 | unit_manager_plus_q70_watcher | watch_mode_watcher_q70_absorb_reclaim2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-14 | 2322885 | 11_r5_frames | long | 0.5000 | 2.0000 | -7.7895 | 43.8440 | 36.0545 | absorb_reclaim |
| 2026-05-14 | 2379419 | 11_r5_frames | short | 2.0000 | 8.0000 | -4.7488 | 26.6959 | 21.9472 | absorb_reclaim |
| 2026-05-15 | 2583437 | 11_r5_frames | long | 1.0000 | 4.0000 | 20.2961 | 55.2346 | 75.5306 | impulse_5s |

## Read

- The q70 watcher is useful at the full anchor only through the rows whose
  path was rebuilt; `00` contributes sizing and concurrency, not watcher
  triggers.
- `gamma00` is now a real optimized branch. If the leader reduces it, that
  is a sizing conclusion; if it keeps it, the broad baseline is carrying
  real historical PnL under the current fallback.
- q65 remains a sensitivity row only. If it tops raw totals, that does not
  make it the rule; it is closer to recall-chasing.
- This pass is historical. The next useful validation is OOS path rebuild
  and checking whether the fixed60 fallback for `00` is still acceptable,
  not adding more watcher predicates.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_unit_entries_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_variants_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_frontier_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_daily_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_walkforward_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_policy_summary_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_leverage_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_cell_summary_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_summary_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_watcher_pareto.py
```

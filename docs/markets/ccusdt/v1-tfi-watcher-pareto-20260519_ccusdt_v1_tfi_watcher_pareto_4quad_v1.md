# CCUSDT V1 TFI Watcher-Aware Pareto

Status: `20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1`.

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
anchor q70 scaled100         5366.4994
anchor q70 max concurrency   18.0000
```

The 100-budget + 7x Pareto should now be read as a four-cell sizing
problem, not an A/B-only watcher problem. The cleaner q70 scaled leader is:

```text
strategy      manager_plus_q70_watcher
variant       grid_g00_1.25_g10_1_g01_0.75_g11_1.25
gamma         (00=1.2500, 10=1.0000, 01=0.7500, 11=1.2500)
raw total     8694.3546
scaled100     10819.6413
worst day     46.4898
entry worst   -76.0697
max conc      5.6250
```

At that q70 leader, contribution by cell is:

| cell | entries | exposure | total | mean | worst_entry |
| --- | --- | --- | --- | --- | --- |
| 00_none | 1234 | 793.7500 | 1935.3368 | 2.4382 | -76.0697 |
| 01_frames_only | 135 | 173.6250 | 673.1221 | 3.8769 | -63.4456 |
| 10_r5_only | 1796 | 934.0000 | 3039.9754 | 3.2548 | -73.0566 |
| 11_r5_frames | 200 | 390.0000 | 3045.9203 | 7.8101 | -60.5181 |

The q65 sensitivity has a slightly higher scaled value:

```text
q65 best scaled100 10928.9505
q70 best scaled100 10819.6413
difference         109.3092
```

That small gap is not enough evidence to promote q65; it is still the
recall sensitivity. Under a 1bps pressure term, the q70 leader remains
near the same balanced low-concurrency point; under 2bps pressure, q70
moves toward much lower broad `00` and higher `11`, which is the warning
that weak/broad exposure becomes expensive once non-fee pressure is added:

```text
C=1 q70 leader grid_g00_1.25_g10_1_g01_0.75_g11_1.25, scaled100 7962.7079
C=2 q70 leader grid_g00_0.5_g10_2_g01_0.75_g11_5, scaled100 3682.8210
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
| 0.0000 | fixed60 | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 12615.5996 | 4.7761 | 47.4094 | -235.9674 | 18.0000 | 0.3889 | 0.3889 | 4906.0665 | 0 | 0.0000 |
| 0.0000 | manager_only | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 13277.3761 | 5.0267 | 47.4094 | -193.6578 | 18.0000 | 0.3889 | 0.3889 | 5163.4240 | 0 | 0.0000 |
| 0.0000 | manager_plus_impulse | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 13498.3143 | 5.1103 | 47.4094 | -193.6578 | 18.0000 | 0.3889 | 0.3889 | 5249.3445 | 1 | 220.9383 |
| 0.0000 | manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 14080.6509 | 5.3308 | 47.4094 | -193.6578 | 18.0000 | 0.3889 | 0.3889 | 5475.8087 | 5 | 803.2748 |
| 0.0000 | manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 13799.5700 | 5.2244 | 47.4094 | -193.6578 | 18.0000 | 0.3889 | 0.3889 | 5366.4994 | 3 | 522.1939 |
| 1.0000 | fixed60 | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 9974.2246 | 3.7761 | -48.2156 | -245.9674 | 18.0000 | 0.3889 | 0.3889 | 3878.8651 | 0 | 0.0000 |
| 1.0000 | manager_only | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 10636.0011 | 4.0267 | -48.2156 | -201.6578 | 18.0000 | 0.3889 | 0.3889 | 4136.2226 | 0 | 0.0000 |
| 1.0000 | manager_plus_impulse | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 10852.9393 | 4.1088 | -48.2156 | -201.6578 | 18.0000 | 0.3889 | 0.3889 | 4220.5875 | 1 | 216.9383 |
| 1.0000 | manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 11407.2759 | 4.3187 | -48.2156 | -201.6578 | 18.0000 | 0.3889 | 0.3889 | 4436.1628 | 5 | 771.2748 |
| 1.0000 | manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 11144.1950 | 4.2191 | -48.2156 | -201.6578 | 18.0000 | 0.3889 | 0.3889 | 4333.8536 | 3 | 508.1939 |
| 2.0000 | fixed60 | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 7332.8496 | 2.7761 | -143.8406 | -255.9674 | 18.0000 | 0.3889 | 0.3889 | 2851.6637 | 0 | 0.0000 |
| 2.0000 | manager_only | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 7994.6261 | 3.0267 | -143.8406 | -209.6578 | 18.0000 | 0.3889 | 0.3889 | 3109.0212 | 0 | 0.0000 |
| 2.0000 | manager_plus_impulse | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 8207.5643 | 3.1073 | -143.8406 | -209.6578 | 18.0000 | 0.3889 | 0.3889 | 3191.8306 | 1 | 212.9383 |
| 2.0000 | manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 8733.9009 | 3.3066 | -143.8406 | -209.6578 | 18.0000 | 0.3889 | 0.3889 | 3396.5170 | 5 | 739.2748 |
| 2.0000 | manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | 1.0000 | 0.7500 | 0.2500 | 4.0000 | 3365 | 2641.3750 | 8488.8200 | 3.2138 | -143.8406 | -209.6578 | 18.0000 | 0.3889 | 0.3889 | 3301.2078 | 3 | 494.1939 |

## Top C0 Historical Variants By 100-Budget Scaled Total

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | entries | exposure | total | mean | worst_day | entry_worst | max_concurrent_exposure | cap_by_exchange_leverage | feasible_cap_100 | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 3365 | 2291.3750 | 8782.1924 | 3.8327 | 46.4898 | -76.0697 | 5.6250 | 1.2444 | 1.2444 | 10928.9505 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.75_g11_1 | 1.0000 | 0.7500 | 0.7500 | 1.0000 | 3365 | 1821.1250 | 7008.3795 | 3.8484 | 42.4077 | -63.4456 | 4.5000 | 1.5556 | 1.5556 | 10901.9237 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 3365 | 2291.3750 | 8694.3546 | 3.7944 | 46.4898 | -76.0697 | 5.6250 | 1.2444 | 1.2444 | 10819.6413 | 3 |
| manager_plus_q70_watcher | grid_g00_1_g10_0.75_g01_0.75_g11_1 | 1.0000 | 0.7500 | 0.7500 | 1.0000 | 3365 | 1821.1250 | 6938.1093 | 3.8098 | 42.4077 | -63.4456 | 4.5000 | 1.5556 | 1.5556 | 10792.6145 | 3 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.2500 | 1.0000 | 1.5000 | 3365 | 2660.7500 | 10393.3119 | 3.9062 | 62.6255 | -91.3207 | 6.7500 | 1.0370 | 1.0370 | 10778.2493 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 3365 | 2213.3750 | 8155.4407 | 3.6846 | 44.4010 | -76.0697 | 4.6250 | 1.5135 | 1.3146 | 10721.0101 | 5 |
| manager_plus_impulse | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 3365 | 2291.3750 | 8600.2122 | 3.7533 | 46.4898 | -76.0697 | 5.6250 | 1.2444 | 1.2444 | 10702.4863 | 1 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.25 | 1.2500 | 1.2500 | 1.0000 | 1.2500 | 3365 | 2582.7500 | 9766.5602 | 3.7815 | 60.5368 | -91.3207 | 5.6250 | 1.2444 | 1.0950 | 10694.7877 | 5 |
| manager_plus_impulse | grid_g00_1_g10_0.75_g01_0.75_g11_1 | 1.0000 | 0.7500 | 0.7500 | 1.0000 | 3365 | 1821.1250 | 6862.7954 | 3.7684 | 42.4077 | -63.4456 | 4.5000 | 1.5556 | 1.5556 | 10675.4595 | 1 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.2500 | 1.0000 | 1.5000 | 3365 | 2660.7500 | 10287.9065 | 3.8665 | 62.6255 | -91.3207 | 6.7500 | 1.0370 | 1.0370 | 10668.9401 | 3 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1.25 | 1.2500 | 1.0000 | 0.5000 | 1.2500 | 3365 | 2233.5000 | 8557.8183 | 3.8316 | 36.4582 | -76.0697 | 5.6250 | 1.2444 | 1.2444 | 10649.7295 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_1_g11_1.25 | 1.2500 | 1.0000 | 1.0000 | 1.2500 | 3365 | 2349.2500 | 9006.5664 | 3.8338 | 56.5214 | -84.5942 | 5.6250 | 1.2444 | 1.1821 | 10646.7905 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.75_g11_1 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 3365 | 2054.6250 | 7768.3734 | 3.7809 | 46.4231 | -73.0566 | 4.5000 | 1.5556 | 1.3688 | 10633.3630 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 3365 | 2213.3750 | 8085.1705 | 3.6529 | 44.4010 | -76.0697 | 4.6250 | 1.5135 | 1.3146 | 10628.6340 | 3 |
| manager_only | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 3365 | 2291.3750 | 8531.1690 | 3.7232 | 46.4898 | -76.0697 | 5.6250 | 1.2444 | 1.2444 | 10616.5659 | 0 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.25 | 1.2500 | 1.2500 | 1.0000 | 1.2500 | 3365 | 2582.7500 | 9678.7225 | 3.7474 | 60.5368 | -91.3207 | 5.6250 | 1.2444 | 1.0950 | 10598.6017 | 3 |
| manager_only | grid_g00_1_g10_0.75_g01_0.75_g11_1 | 1.0000 | 0.7500 | 0.7500 | 1.0000 | 3365 | 1821.1250 | 6807.5608 | 3.7381 | 42.4077 | -63.4456 | 4.5000 | 1.5556 | 1.5556 | 10589.5391 | 0 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_1 | 1.0000 | 0.7500 | 0.5000 | 1.0000 | 3365 | 1763.2500 | 6784.0055 | 3.8474 | 32.3761 | -60.8558 | 4.5000 | 1.5556 | 1.5556 | 10552.8975 | 5 |
| manager_plus_impulse | grid_g00_1.25_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.2500 | 1.0000 | 1.5000 | 3365 | 2660.7500 | 10174.9357 | 3.8241 | 62.6255 | -91.3207 | 6.7500 | 1.0370 | 1.0370 | 10551.7851 | 1 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_0.75_g11_1.5 | 1.2500 | 1.2500 | 0.7500 | 1.5000 | 3365 | 2602.8750 | 10168.9378 | 3.9068 | 52.5939 | -91.3207 | 6.7500 | 1.0370 | 1.0370 | 10545.5652 | 5 |

## Pareto Frontier C0

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | daily_cvar20 | entry_cvar05 | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 8782.1924 | 3.8327 | 46.4898 | 69.8252 | -18.7355 | 10928.9505 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.75_g11_1 | 1.0000 | 0.7500 | 0.7500 | 1.0000 | 7008.3795 | 3.8484 | 42.4077 | 59.1121 | -14.9572 | 10901.9237 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.2500 | 1.0000 | 1.5000 | 10393.3119 | 3.9062 | 62.6255 | 81.4704 | -21.8309 | 10778.2493 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 8155.4407 | 3.6846 | 44.4010 | 66.6111 | -18.2424 | 10721.0101 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.25 | 1.2500 | 1.2500 | 1.0000 | 1.2500 | 9766.5602 | 3.7815 | 60.5368 | 78.2563 | -21.3359 | 10694.7877 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1.25 | 1.2500 | 1.0000 | 0.5000 | 1.2500 | 8557.8183 | 3.8316 | 36.4582 | 63.6526 | -18.1907 | 10649.7295 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_1_g11_1.25 | 1.2500 | 1.0000 | 1.0000 | 1.2500 | 9006.5664 | 3.8338 | 56.5214 | 75.9979 | -19.3390 | 10646.7905 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.75_g11_1 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 7768.3734 | 3.7809 | 46.4231 | 61.3705 | -16.9475 | 10633.3630 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_1 | 1.0000 | 0.7500 | 0.5000 | 1.0000 | 6784.0055 | 3.8474 | 32.3761 | 52.9394 | -14.3683 | 10552.8975 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_0.75_g11_1.5 | 1.2500 | 1.2500 | 0.7500 | 1.5000 | 10168.9378 | 3.9068 | 52.5939 | 75.2978 | -21.2335 | 10545.5652 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.75_g01_0.5_g11_0.75 | 0.7500 | 0.7500 | 0.5000 | 0.7500 | 5770.1865 | 3.7800 | 32.3094 | 44.4847 | -12.5599 | 10530.9884 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_0.75_g11_1.25 | 1.2500 | 1.2500 | 0.7500 | 1.2500 | 9542.1862 | 3.7793 | 50.5052 | 72.0837 | -20.7377 | 10449.0888 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.75_g11_1.25 | 1.0000 | 1.0000 | 0.7500 | 1.2500 | 8395.1250 | 3.9365 | 48.5118 | 64.5846 | -17.4447 | 10447.2667 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.5_g01_0.5_g11_0.75 | 0.7500 | 0.5000 | 0.5000 | 0.7500 | 5010.1927 | 3.8749 | 28.2940 | 42.2263 | -10.5965 | 10391.5108 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1.25_g01_1_g11_1.5 | 1.0000 | 1.2500 | 1.0000 | 1.5000 | 10006.2445 | 3.9993 | 64.6476 | 76.2298 | -20.6327 | 10376.8462 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.5_g11_1 | 1.0000 | 1.0000 | 0.5000 | 1.0000 | 7543.9994 | 3.7781 | 36.3915 | 55.1979 | -16.3681 | 10326.2394 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_0.5_g01_0.25_g11_0.5 | 0.5000 | 0.5000 | 0.2500 | 0.5000 | 3771.9997 | 3.7781 | 18.1958 | 27.5989 | -8.1840 | 10326.2394 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.75_g01_0.75_g11_1 | 0.7500 | 0.7500 | 0.7500 | 1.0000 | 6621.3122 | 3.9830 | 44.4298 | 53.8715 | -13.6722 | 10299.8190 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1.25_g01_1_g11_1.25 | 1.0000 | 1.2500 | 1.0000 | 1.2500 | 9379.4929 | 3.8694 | 62.5588 | 73.0157 | -20.1339 | 10270.9329 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_1_g11_1.25 | 1.0000 | 1.0000 | 1.0000 | 1.2500 | 8619.4990 | 3.9349 | 58.5434 | 70.7573 | -18.0583 | 10189.2327 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.5_g01_1_g11_1.5 | 1.2500 | 1.5000 | 1.0000 | 1.5000 | 11153.3057 | 3.8536 | 66.6409 | 83.7289 | -23.9100 | 10177.7761 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1_g01_0.5_g11_1.25 | 1.0000 | 1.0000 | 0.5000 | 1.2500 | 8170.7510 | 3.9382 | 38.4803 | 58.4120 | -16.8666 | 10168.0457 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1.25_g01_0.75_g11_1.5 | 1.0000 | 1.2500 | 0.7500 | 1.5000 | 9781.8705 | 4.0022 | 54.6160 | 70.0572 | -20.0296 | 10144.1620 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_0.75_g01_0.25_g11_0.75 | 0.7500 | 0.7500 | 0.2500 | 0.7500 | 5545.8125 | 3.7762 | 22.2779 | 38.3121 | -12.0262 | 10121.4904 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_1_g01_0.75_g11_1 | 0.7500 | 1.0000 | 0.7500 | 1.0000 | 7381.3060 | 3.8934 | 48.4452 | 56.1299 | -15.7558 | 10103.5445 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.75_g11_0.75 | 1.0000 | 0.7500 | 0.7500 | 0.7500 | 6381.6279 | 3.6610 | 40.3189 | 55.8979 | -14.4641 | 10058.4178 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_1.25_g01_0.75_g11_1.25 | 1.0000 | 1.2500 | 0.7500 | 1.2500 | 9155.1189 | 3.8692 | 52.5273 | 66.8431 | -19.5306 | 10025.2341 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_1_g11_1.5 | 1.2500 | 1.0000 | 1.0000 | 1.5000 | 9633.3180 | 3.9688 | 58.6101 | 79.2120 | -19.8370 | 9990.1076 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_0.75_g01_0.75_g11_1.25 | 1.2500 | 0.7500 | 0.7500 | 1.2500 | 8022.1985 | 3.8983 | 42.4744 | 67.5668 | -16.8742 | 9983.1804 | 5 |
| manager_plus_q65_watcher | grid_g00_0.75_g10_1.25_g01_1_g11_1.5 | 0.7500 | 1.2500 | 1.0000 | 1.5000 | 9619.1771 | 4.1051 | 66.6696 | 70.9893 | -19.5683 | 9975.4430 | 5 |

## Pressure Sensitivity

Top C=1:

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 6480.8174 | 2.8284 | -51.6352 | 8065.0172 | 5 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.2500 | 1.0000 | 1.5000 | 7720.5619 | 2.9016 | -49.9995 | 8006.5086 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 6398.6046 | 2.7925 | -51.6352 | 7962.7079 | 3 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.75_g11_1 | 1.0000 | 0.7500 | 0.7500 | 1.0000 | 5179.2545 | 2.8440 | -35.4673 | 7928.9705 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.2500 | 1.0000 | 1.5000 | 7621.9065 | 2.8646 | -49.9995 | 7904.1994 | 3 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.5_g11_1.25 | 1.2500 | 1.0000 | 0.5000 | 1.2500 | 6314.3183 | 2.8271 | -59.2918 | 7857.8184 | 5 |
| manager_plus_impulse | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 6307.5872 | 2.7528 | -51.6352 | 7849.4418 | 1 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_0.75_g11_1.5 | 1.2500 | 1.2500 | 0.7500 | 1.5000 | 7554.0628 | 2.9022 | -57.6561 | 7833.8429 | 5 |
| manager_plus_q70_watcher | grid_g00_1_g10_0.75_g01_0.75_g11_1 | 1.0000 | 0.7500 | 0.7500 | 1.0000 | 5113.4843 | 2.8079 | -35.4673 | 7828.2822 | 3 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1.25_g01_1_g11_1.25 | 1.2500 | 1.2500 | 1.0000 | 1.2500 | 7173.8102 | 2.7776 | -50.2132 | 7802.2207 | 5 |
| manager_plus_q65_watcher | grid_g00_1_g10_0.75_g01_0.5_g11_1 | 1.0000 | 0.7500 | 0.5000 | 1.0000 | 5012.7555 | 2.8429 | -43.1239 | 7797.6197 | 5 |
| manager_plus_impulse | grid_g00_1.25_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.2500 | 1.0000 | 1.5000 | 7512.6857 | 2.8235 | -49.9995 | 7790.9333 | 1 |

Top C=2:

| strategy | variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_0.5_g10_2_g01_0.75_g11_5 | 0.5000 | 2.0000 | 0.7500 | 5.0000 | 12143.9899 | 3.0986 | -304.5825 | 3778.1302 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_1.5_g01_0.75_g11_4 | 0.5000 | 1.5000 | 0.7500 | 4.0000 | 9690.9958 | 3.0862 | -240.0353 | 3768.7206 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_1.25_g01_0.5_g11_3 | 0.2500 | 1.2500 | 0.5000 | 3.0000 | 7352.8041 | 3.0920 | -195.3395 | 3764.1159 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_2_g01_1_g11_5 | 0.5000 | 2.0000 | 1.0000 | 5.0000 | 12252.6140 | 3.0809 | -326.1318 | 3756.9517 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_1_g01_0.5_g11_2.5 | 0.2500 | 1.0000 | 0.5000 | 2.5000 | 6126.3070 | 3.0809 | -163.0659 | 3756.9517 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_2_g01_0.75_g11_5 | 0.2500 | 2.0000 | 0.7500 | 5.0000 | 12074.4226 | 3.2110 | -314.6908 | 3756.4870 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_1_g01_0.75_g11_3 | 0.5000 | 1.0000 | 0.7500 | 3.0000 | 7238.0016 | 3.0655 | -175.4882 | 3753.0379 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_1.5_g01_1_g11_4 | 0.5000 | 1.5000 | 1.0000 | 4.0000 | 9799.6198 | 3.0643 | -261.5846 | 3746.2520 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_0.75_g01_0.5_g11_2 | 0.2500 | 0.7500 | 0.5000 | 2.0000 | 4899.8099 | 3.0643 | -130.7923 | 3746.2520 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_1.5_g01_0.75_g11_4 | 0.2500 | 1.5000 | 0.7500 | 4.0000 | 9621.4284 | 3.2272 | -250.1437 | 3741.6666 | 5 |
| manager_plus_q65_watcher | grid_g00_0.5_g10_0.75_g01_0.75_g11_2.5 | 0.5000 | 0.7500 | 0.7500 | 2.5000 | 6011.5045 | 3.0490 | -143.2146 | 3740.4917 | 5 |
| manager_plus_q65_watcher | grid_g00_0.25_g10_0.5_g01_0.5_g11_1.5 | 0.2500 | 0.5000 | 0.5000 | 1.5000 | 3673.3128 | 3.0371 | -98.5187 | 3728.5420 | 5 |

## Strategy Summary

| strategy | best_scaled_variant | best_scaled_total_100 | best_scaled_raw_total | best_scaled_worst_day | best_scaled_entry_worst | best_scaled_max_concurrent | anchor_total | anchor_scaled_total_100 | anchor_watch_triggers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 10928.9505 | 8782.1924 | 46.4898 | -76.0697 | 5.6250 | 14080.6509 | 5475.8087 | 5 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 10819.6413 | 8694.3546 | 46.4898 | -76.0697 | 5.6250 | 13799.5700 | 5366.4994 | 3 |
| manager_plus_impulse | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 10702.4863 | 8600.2122 | 46.4898 | -76.0697 | 5.6250 | 13498.3143 | 5249.3445 | 1 |
| manager_only | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 10616.5659 | 8531.1690 | 46.4898 | -76.0697 | 5.6250 | 13277.3761 | 5163.4240 | 0 |
| fixed60 | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 10361.9615 | 8326.5762 | 46.4898 | -76.0697 | 5.6250 | 12615.5996 | 4906.0665 | 0 |

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
| 2026-05-10 | manager_only | grid_g00_1.25_g10_0.5_g01_0.5_g11_0.75 | 1.2500 | 0.5000 | 0.5000 | 0.7500 | 347.9709 | 3.3378 | 0 | 597.3795 | 597.3795 | 0.0000 |
| 2026-05-11 | manager_only | grid_g00_1.25_g10_0.5_g01_0.5_g11_0.75 | 1.2500 | 0.5000 | 0.5000 | 0.7500 | 371.2921 | 2.3518 | 0 | 854.7620 | 854.7620 | 0.0000 |
| 2026-05-12 | manager_only | grid_g00_1.25_g10_1_g01_1_g11_1.5 | 1.2500 | 1.0000 | 1.0000 | 1.5000 | 769.2801 | 4.1165 | 0 | 1036.0113 | 1036.0113 | 0.0000 |
| 2026-05-13 | manager_only | grid_g00_1.25_g10_1_g01_1_g11_1.5 | 1.2500 | 1.0000 | 1.0000 | 1.5000 | 211.2314 | 1.1266 | 0 | 287.1568 | 287.1568 | 0.0000 |
| 2026-05-14 | manager_only | grid_g00_1.25_g10_1_g01_0.75_g11_1 | 1.2500 | 1.0000 | 0.7500 | 1.0000 | 1841.4391 | 6.9488 | 0 | 4190.9081 | 3889.6525 | 301.2557 |
| 2026-05-15 | manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 1902.2845 | 8.6664 | 1 | 3085.0320 | 2864.0938 | 220.9383 |
| 2026-05-16 | manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 415.4810 | 2.3034 | 0 | 756.9663 | 756.9663 | 0.0000 |
| 2026-05-17 | manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1.25 | 1.2500 | 1.0000 | 0.7500 | 1.2500 | 631.5400 | 4.6868 | 0 | 1113.7769 | 1113.7769 | 0.0000 |

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

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_unit_entries_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_variants_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_frontier_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_daily_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_walkforward_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_policy_summary_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_leverage_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_cell_summary_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_summary_20260519_ccusdt_v1_tfi_watcher_pareto_4quad_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_watcher_pareto.py
```

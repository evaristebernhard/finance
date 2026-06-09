# CCUSDT V1 TFI Watcher-Aware Pareto

Status: `20260519_ccusdt_v1_tfi_watcher_pareto_v1`.

Guardrail: `research_only_watcher_aware_pareto_no_execution_recommendation`.

## Scope

This is the historical Pareto pass for the restrained rule family:

```text
base A/B entry universe
-> pm_11_drawdown_h4_peakguard
-> optional post-exit watcher
-> gamma sizing by mutually exclusive cell
```

The optimized historical universe is the path-managed casebook universe:
`1455` entries from `2026-05-04` to `2026-05-15`.

It does not include `00_none`; this branch is testing the A/B structure
for which path manager and post-exit watcher features have been rebuilt.

## Main Result

At the old anchor:

```text
manager_only                 total 9554.1874
manager_plus_q70_watcher     total 10076.3813
q70 watcher delta            total 522.1939
anchor q70 scaled100         3526.7335
anchor q70 max concurrency   20.0000
```

But the historical 100-budget + 7x Pareto does not like the old
\(\gamma_{11}=4\) anchor. The cleaner q70 scaled leader is:

```text
strategy      manager_plus_q70_watcher
variant       grid_g10_1_g01_0.75_g11_1
gamma         (10=1.0000, 01=0.7500, 11=1.0000)
raw total     5156.4430
scaled100     7058.1482
worst day     -48.6497
entry worst   -73.0566
max conc      5.0000
```

The q65 sensitivity has a slightly higher scaled value:

```text
q65 best scaled100 7154.3341
q70 best scaled100 7058.1482
difference         96.1860
```

That small gap is not enough evidence to promote q65; it is still the
recall sensitivity. Under a 1bps pressure term, the best q70 row shifts
toward `gamma01=0`, which is exactly the expected warning that extra
re-entry legs and weaker stale-only exposure should not be over-loved:

```text
C=1 q70 leader grid_g10_1.5_g01_0_g11_1.5, scaled100 4911.5721
```

## Model

The old anchor exposure is decomposed as:

$$
w_i^{old}=b_i\gamma^{old}_{c_i},\qquad
\gamma^{old}_{10}=0.75,\ \gamma^{old}_{01}=0.25,\ \gamma^{old}_{11}=4.
$$

Pareto only changes:

$$
w_i=b_i\gamma_{c_i},\qquad c_i\in\{10,01,11\}.
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

| pressure_bps | strategy | variant | entries | exposure | total | mean | worst_day | entry_worst | max_concurrent_exposure | cap_by_exchange_leverage | feasible_cap_100 | scaled_total_100 | watch_trigger_count | watch_trigger_weighted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | fixed60 | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 8904.7590 | 6.0402 | 27.1656 | -235.9674 | 20.0000 | 0.3500 | 0.3500 | 3116.6657 | 0 | 0.0000 |
| 0.0000 | manager_only | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 9554.1874 | 6.4807 | 27.1656 | -193.6578 | 20.0000 | 0.3500 | 0.3500 | 3343.9656 | 0 | 0.0000 |
| 0.0000 | manager_plus_impulse | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 9775.1257 | 6.6306 | 27.1656 | -193.6578 | 20.0000 | 0.3500 | 0.3500 | 3421.2940 | 1 | 220.9383 |
| 0.0000 | manager_plus_q65_watcher | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 10357.4622 | 7.0256 | 27.1656 | -193.6578 | 20.0000 | 0.3500 | 0.3500 | 3625.1118 | 5 | 803.2748 |
| 0.0000 | manager_plus_q70_watcher | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 10076.3813 | 6.8349 | 27.1656 | -193.6578 | 20.0000 | 0.3500 | 0.3500 | 3526.7335 | 3 | 522.1939 |
| 1.0000 | fixed60 | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 7430.5090 | 5.0402 | 7.4156 | -245.9674 | 20.0000 | 0.3500 | 0.3500 | 2600.6782 | 0 | 0.0000 |
| 1.0000 | manager_only | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 8079.9374 | 5.4807 | 7.4156 | -201.6578 | 20.0000 | 0.3500 | 0.3500 | 2827.9781 | 0 | 0.0000 |
| 1.0000 | manager_plus_impulse | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 8296.8757 | 5.6279 | 7.4156 | -201.6578 | 20.0000 | 0.3500 | 0.3500 | 2903.9065 | 1 | 216.9383 |
| 1.0000 | manager_plus_q65_watcher | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 8851.2122 | 6.0039 | 7.4156 | -201.6578 | 20.0000 | 0.3500 | 0.3500 | 3097.9243 | 5 | 771.2748 |
| 1.0000 | manager_plus_q70_watcher | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 8588.1313 | 5.8254 | 7.4156 | -201.6578 | 20.0000 | 0.3500 | 0.3500 | 3005.8460 | 3 | 508.1939 |
| 2.0000 | fixed60 | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 5956.2590 | 4.0402 | -46.4883 | -255.9674 | 20.0000 | 0.3500 | 0.3500 | 2084.6907 | 0 | 0.0000 |
| 2.0000 | manager_only | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 6605.6874 | 4.4807 | -46.4883 | -209.6578 | 20.0000 | 0.3500 | 0.3500 | 2311.9906 | 0 | 0.0000 |
| 2.0000 | manager_plus_impulse | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 6818.6257 | 4.6251 | -46.4883 | -209.6578 | 20.0000 | 0.3500 | 0.3500 | 2386.5190 | 1 | 212.9383 |
| 2.0000 | manager_plus_q65_watcher | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 7344.9622 | 4.9822 | -46.4883 | -209.6578 | 20.0000 | 0.3500 | 0.3500 | 2570.7368 | 5 | 739.2748 |
| 2.0000 | manager_plus_q70_watcher | anchor_old_0p75_0p25_4 | 1455 | 1474.2500 | 7099.8813 | 4.8159 | -46.4883 | -209.6578 | 20.0000 | 0.3500 | 0.3500 | 2484.9585 | 3 | 494.1939 |

## Top C0 Historical Variants By 100-Budget Scaled Total

| strategy | variant | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | entries | exposure | total | mean | worst_day | entry_worst | max_concurrent_exposure | cap_by_exchange_leverage | feasible_cap_100 | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g10_1_g01_0.75_g11_1 | 1.0000 | 0.7500 | 1.0000 | 1455 | 1022.2500 | 5226.7132 | 5.1130 | -48.6497 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 7154.3341 | 5 |
| manager_plus_q70_watcher | grid_g10_1_g01_0.75_g11_1 | 1.0000 | 0.7500 | 1.0000 | 1455 | 1022.2500 | 5156.4430 | 5.0442 | -48.6497 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 7058.1482 | 3 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_1_g11_1.5 | 1.5000 | 1.0000 | 1.5000 | 1455 | 1503.7500 | 7724.1269 | 5.1366 | -68.5090 | -109.5849 | 7.5000 | 0.9333 | 0.9125 | 7048.5322 | 5 |
| manager_plus_impulse | grid_g10_1_g01_0.75_g11_1 | 1.0000 | 0.7500 | 1.0000 | 1455 | 1022.2500 | 5081.1291 | 4.9705 | -48.6497 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 6955.0583 | 1 |
| manager_plus_q70_watcher | grid_g10_1.5_g01_1_g11_1.5 | 1.5000 | 1.0000 | 1.5000 | 1455 | 1503.7500 | 7618.7216 | 5.0665 | -68.5090 | -109.5849 | 7.5000 | 0.9333 | 0.9125 | 6952.3462 | 3 |
| manager_only | grid_g10_1_g01_0.75_g11_1 | 1.0000 | 0.7500 | 1.0000 | 1455 | 1022.2500 | 5025.8945 | 4.9165 | -48.6497 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 6879.4532 | 0 |
| manager_plus_impulse | grid_g10_1.5_g01_1_g11_1.5 | 1.5000 | 1.0000 | 1.5000 | 1455 | 1503.7500 | 7505.7507 | 4.9914 | -68.5090 | -109.5849 | 7.5000 | 0.9333 | 0.9125 | 6849.2564 | 1 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0.75_g11_1.5 | 1.5000 | 0.7500 | 1.5000 | 1455 | 1444.5000 | 7492.2411 | 5.1867 | -59.5779 | -109.5849 | 7.5000 | 0.9333 | 0.9125 | 6836.9284 | 5 |
| manager_plus_q65_watcher | grid_g10_1_g01_0.5_g11_1 | 1.0000 | 0.5000 | 1.0000 | 1455 | 963.0000 | 4994.8274 | 5.1867 | -39.7186 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 6836.9284 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_1_g11_2 | 2.0000 | 1.0000 | 2.0000 | 1455 | 1926.0000 | 9989.6548 | 5.1867 | -79.4372 | -146.1132 | 10.0000 | 0.7000 | 0.6844 | 6836.9284 | 5 |
| manager_only | grid_g10_1.5_g01_1_g11_1.5 | 1.5000 | 1.0000 | 1.5000 | 1455 | 1503.7500 | 7422.8989 | 4.9363 | -68.5090 | -109.5849 | 7.5000 | 0.9333 | 0.9125 | 6773.6512 | 0 |
| manager_plus_q70_watcher | grid_g10_2_g01_1_g11_2 | 2.0000 | 1.0000 | 2.0000 | 1455 | 1926.0000 | 9849.1143 | 5.1138 | -79.4372 | -146.1132 | 10.0000 | 0.7000 | 0.6844 | 6740.7424 | 3 |
| manager_plus_q70_watcher | grid_g10_1.5_g01_0.75_g11_1.5 | 1.5000 | 0.7500 | 1.5000 | 1455 | 1444.5000 | 7386.8357 | 5.1138 | -59.5779 | -109.5849 | 7.5000 | 0.9333 | 0.9125 | 6740.7424 | 3 |
| manager_plus_q70_watcher | grid_g10_1_g01_0.5_g11_1 | 1.0000 | 0.5000 | 1.0000 | 1455 | 963.0000 | 4924.5572 | 5.1138 | -39.7186 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 6740.7424 | 3 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.75_g11_2 | 2.0000 | 0.7500 | 2.0000 | 1455 | 1866.7500 | 9757.7689 | 5.2271 | -70.5061 | -146.1132 | 10.0000 | 0.7000 | 0.6844 | 6678.2255 | 5 |
| fixed60 | grid_g10_1_g01_0.75_g11_1 | 1.0000 | 0.7500 | 1.0000 | 1455 | 1022.2500 | 4863.5374 | 4.7577 | -48.6497 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 6657.2185 | 0 |
| manager_plus_impulse | grid_g10_1.5_g01_0.75_g11_1.5 | 1.5000 | 0.7500 | 1.5000 | 1455 | 1444.5000 | 7273.8649 | 5.0356 | -59.5779 | -109.5849 | 7.5000 | 0.9333 | 0.9125 | 6637.6526 | 1 |
| manager_plus_impulse | grid_g10_2_g01_1_g11_2 | 2.0000 | 1.0000 | 2.0000 | 1455 | 1926.0000 | 9698.4865 | 5.0356 | -79.4372 | -146.1132 | 10.0000 | 0.7000 | 0.6844 | 6637.6526 | 1 |
| manager_plus_impulse | grid_g10_1_g01_0.5_g11_1 | 1.0000 | 0.5000 | 1.0000 | 1455 | 963.0000 | 4849.2432 | 5.0356 | -39.7186 | -73.0566 | 5.0000 | 1.4000 | 1.3688 | 6637.6526 | 1 |
| manager_plus_q65_watcher | grid_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.0000 | 1.5000 | 1455 | 1352.7500 | 7108.8464 | 5.2551 | -53.1538 | -91.3207 | 7.5000 | 0.9333 | 0.9333 | 6634.9233 | 5 |

## Pareto Frontier C0

| strategy | variant | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | daily_cvar20 | entry_cvar05 | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g10_1_g01_0.75_g11_1 | 1.0000 | 0.7500 | 1.0000 | 5226.7132 | 5.1130 | -48.6497 | 9.3924 | -20.6714 | 7154.3341 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_1_g11_1.5 | 1.5000 | 1.0000 | 1.5000 | 7724.1269 | 5.1366 | -68.5090 | 12.6935 | -30.4462 | 7048.5322 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0.75_g11_1.5 | 1.5000 | 0.7500 | 1.5000 | 7492.2411 | 5.1867 | -59.5779 | 9.9032 | -29.3980 | 6836.9284 | 5 |
| manager_plus_q65_watcher | grid_g10_1_g01_0.5_g11_1 | 1.0000 | 0.5000 | 1.0000 | 4994.8274 | 5.1867 | -39.7186 | 6.6022 | -19.5987 | 6836.9284 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_1_g11_2 | 2.0000 | 1.0000 | 2.0000 | 9989.6548 | 5.1867 | -79.4372 | 13.2043 | -39.1973 | 6836.9284 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.75_g11_2 | 2.0000 | 0.7500 | 2.0000 | 9757.7689 | 5.2271 | -70.5061 | 10.4141 | -38.2660 | 6678.2255 | 5 |
| manager_plus_q65_watcher | grid_g10_1.25_g01_1_g11_1.5 | 1.2500 | 1.0000 | 1.5000 | 7108.8464 | 5.2551 | -53.1538 | 17.4842 | -27.1243 | 6634.9233 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0.5_g11_1.5 | 1.5000 | 0.5000 | 1.5000 | 7260.3552 | 5.2412 | -50.6468 | 7.1130 | -28.5422 | 6625.3245 | 5 |
| manager_plus_q65_watcher | grid_g10_1_g01_0.25_g11_1 | 1.0000 | 0.2500 | 1.0000 | 4762.9415 | 5.2702 | -30.7875 | 3.8119 | -18.8670 | 6519.5226 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.5_g11_2 | 2.0000 | 0.5000 | 2.0000 | 9525.8830 | 5.2702 | -61.5750 | 7.6238 | -37.7340 | 6519.5226 | 5 |
| manager_plus_q65_watcher | grid_g10_0.75_g01_0.75_g11_1 | 0.7500 | 0.7500 | 1.0000 | 4611.4328 | 5.2929 | -33.2945 | 13.8774 | -17.4178 | 6456.0059 | 5 |
| manager_plus_q65_watcher | all1 | 1.0000 | 1.0000 | 1.0000 | 5458.5991 | 5.0472 | -57.5809 | 12.1827 | -21.9149 | 6452.6878 | 5 |
| manager_plus_q65_watcher | grid_g10_1.25_g01_0.75_g11_1.5 | 1.2500 | 0.7500 | 1.5000 | 6876.9606 | 5.3166 | -44.2227 | 14.6940 | -26.0142 | 6418.4965 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0.25_g11_1.5 | 1.5000 | 0.2500 | 1.5000 | 7028.4694 | 5.3005 | -41.7157 | 4.3227 | -28.1557 | 6413.7207 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.25_g11_2 | 2.0000 | 0.2500 | 2.0000 | 9293.9972 | 5.3162 | -52.6439 | 4.8335 | -37.4443 | 6360.8197 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0_g11_1.5 | 1.5000 | 0.0000 | 1.5000 | 6796.5835 | 5.3654 | -32.7846 | 1.5325 | -29.5866 | 6202.1169 | 5 |
| manager_plus_q65_watcher | r5_only_1 | 1.0000 | 0.0000 | 1.0000 | 4531.0557 | 5.3654 | -21.8564 | 1.0216 | -19.7244 | 6202.1169 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0_g11_2 | 2.0000 | 0.0000 | 2.0000 | 9062.1113 | 5.3654 | -43.7127 | 2.0433 | -39.4488 | 6202.1169 | 5 |
| manager_plus_q65_watcher | grid_g10_1.25_g01_0.5_g11_1.5 | 1.2500 | 0.5000 | 1.5000 | 6645.0747 | 5.3839 | -35.2915 | 11.9037 | -25.0222 | 6202.0697 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_1_g11_2.5 | 2.0000 | 1.0000 | 2.5000 | 11024.6216 | 5.3877 | -59.6549 | 23.2966 | -41.1938 | 6173.7881 | 5 |
| manager_plus_q65_watcher | grid_g10_0.75_g01_0.5_g11_1 | 0.7500 | 0.5000 | 1.0000 | 4379.5469 | 5.3935 | -24.3634 | 11.3929 | -16.2213 | 6131.3657 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_1_g11_2 | 1.5000 | 1.0000 | 2.0000 | 8759.0938 | 5.3935 | -48.7267 | 22.7858 | -32.4427 | 6131.3657 | 5 |
| manager_plus_q65_watcher | grid_g10_1_g01_1_g11_1.5 | 1.0000 | 1.0000 | 1.5000 | 6493.5660 | 5.4034 | -37.7985 | 21.2046 | -23.8892 | 6060.6616 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.75_g11_2.5 | 2.0000 | 0.7500 | 2.5000 | 10792.7358 | 5.4317 | -50.7238 | 20.5064 | -40.2625 | 6043.9320 | 5 |
| manager_plus_q65_watcher | grid_g10_1.25_g01_0.25_g11_1.5 | 1.2500 | 0.2500 | 1.5000 | 6413.1889 | 5.4580 | -26.3604 | 9.1135 | -24.5096 | 5985.6429 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0.75_g11_2 | 1.5000 | 0.7500 | 2.0000 | 8527.2079 | 5.4496 | -39.7956 | 19.9956 | -31.3945 | 5969.0456 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.5_g11_2.5 | 2.0000 | 0.5000 | 2.5000 | 10560.8499 | 5.4783 | -41.7927 | 17.7161 | -39.7305 | 5914.0759 | 5 |
| manager_plus_q65_watcher | grid_g10_1_g01_0.75_g11_1.5 | 1.0000 | 0.7500 | 1.5000 | 6261.6801 | 5.4807 | -28.8674 | 19.0263 | -22.6649 | 5844.2348 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0.5_g11_2 | 1.5000 | 0.5000 | 2.0000 | 8295.3221 | 5.5100 | -30.8645 | 17.2053 | -30.5387 | 5806.7255 | 5 |
| manager_plus_q65_watcher | grid_g10_0.75_g01_0.25_g11_1 | 0.7500 | 0.2500 | 1.0000 | 4147.6610 | 5.5100 | -15.4322 | 8.6026 | -15.2694 | 5806.7255 | 5 |

## Pressure Sensitivity

Top C=1:

| strategy | variant | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0_g11_1.5 | 1.5000 | 0.0000 | 1.5000 | 5517.8335 | 4.3559 | -108.5346 | 5000.9866 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0_g11_2 | 2.0000 | 0.0000 | 2.0000 | 7357.1113 | 4.3559 | -144.7127 | 5000.9866 | 5 |
| manager_plus_q65_watcher | r5_only_1 | 1.0000 | 0.0000 | 1.0000 | 3678.5557 | 4.3559 | -72.3564 | 5000.9866 | 5 |
| manager_plus_q70_watcher | grid_g10_1.5_g01_0_g11_1.5 | 1.5000 | 0.0000 | 1.5000 | 5419.1782 | 4.2780 | -108.5346 | 4911.5721 | 3 |
| manager_plus_q70_watcher | grid_g10_2_g01_0_g11_2 | 2.0000 | 0.0000 | 2.0000 | 7225.5709 | 4.2780 | -144.7127 | 4911.5721 | 3 |
| manager_plus_q70_watcher | r5_only_1 | 1.0000 | 0.0000 | 1.0000 | 3612.7854 | 4.2780 | -72.3564 | 4911.5721 | 3 |
| manager_plus_q65_watcher | grid_g10_1.25_g01_0.25_g11_1.5 | 1.2500 | 0.2500 | 1.5000 | 5226.1889 | 4.4478 | -100.9854 | 4877.7763 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.5_g11_2.5 | 2.0000 | 0.5000 | 2.5000 | 8613.0999 | 4.4680 | -165.7927 | 4823.3359 | 5 |
| manager_plus_impulse | grid_g10_1.5_g01_0_g11_1.5 | 1.5000 | 0.0000 | 1.5000 | 5309.9573 | 4.1918 | -108.5346 | 4812.5818 | 1 |
| manager_plus_impulse | r5_only_1 | 1.0000 | 0.0000 | 1.0000 | 3539.9715 | 4.1918 | -72.3564 | 4812.5818 | 1 |
| manager_plus_impulse | grid_g10_2_g01_0_g11_2 | 2.0000 | 0.0000 | 2.0000 | 7079.9431 | 4.1918 | -144.7127 | 4812.5818 | 1 |
| manager_plus_q70_watcher | grid_g10_1.25_g01_0.25_g11_1.5 | 1.2500 | 0.2500 | 1.5000 | 5127.5335 | 4.3639 | -100.9854 | 4785.6980 | 3 |

Top C=2:

| strategy | variant | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | total | mean | worst_day | scaled_total_100 | watch_trigger_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g10_1.25_g01_0_g11_2 | 1.2500 | 0.0000 | 2.0000 | 4712.2699 | 3.8125 | -136.6470 | 3298.5889 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0_g11_2.5 | 1.5000 | 0.0000 | 2.5000 | 5812.0172 | 3.8560 | -161.7199 | 3254.7296 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0_g11_3 | 2.0000 | 0.0000 | 3.0000 | 7225.0451 | 3.7445 | -223.1481 | 3237.7804 | 5 |
| manager_plus_q65_watcher | grid_g10_1_g01_0_g11_1.5 | 1.0000 | 0.0000 | 1.5000 | 3612.5225 | 3.7445 | -111.5740 | 3237.7804 | 5 |
| manager_plus_q70_watcher | grid_g10_1.25_g01_0_g11_2 | 1.2500 | 0.0000 | 2.0000 | 4589.7294 | 3.7134 | -136.6470 | 3212.8106 | 3 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.75_g11_4 | 2.0000 | 0.7500 | 4.0000 | 9138.1364 | 3.8923 | -283.6268 | 3198.3477 | 5 |
| manager_plus_q65_watcher | grid_g10_0.75_g01_0.25_g11_1.5 | 0.7500 | 0.2500 | 1.5000 | 3412.6279 | 3.9091 | -102.8999 | 3185.1194 | 5 |
| manager_plus_q65_watcher | grid_g10_1.5_g01_0.5_g11_3 | 1.5000 | 0.5000 | 3.0000 | 6825.2558 | 3.9091 | -205.7998 | 3185.1194 | 5 |
| manager_plus_q70_watcher | grid_g10_1.5_g01_0_g11_2.5 | 1.5000 | 0.0000 | 2.5000 | 5658.8417 | 3.7544 | -161.7199 | 3168.9513 | 3 |
| manager_plus_q65_watcher | grid_g10_1.25_g01_0.5_g11_2.5 | 1.2500 | 0.5000 | 2.5000 | 5725.5085 | 3.8824 | -180.7269 | 3168.0445 | 5 |
| manager_plus_q65_watcher | grid_g10_2_g01_0.5_g11_4 | 2.0000 | 0.5000 | 4.0000 | 9024.7505 | 3.9435 | -255.9457 | 3158.6627 | 5 |
| manager_plus_q65_watcher | milder_1_0p25_2 | 1.0000 | 0.2500 | 2.0000 | 4512.3752 | 3.9435 | -127.9728 | 3158.6627 | 5 |

## Strategy Summary

| strategy | best_scaled_variant | best_scaled_total_100 | best_scaled_raw_total | best_scaled_worst_day | best_scaled_entry_worst | best_scaled_max_concurrent | anchor_total | anchor_scaled_total_100 | anchor_watch_triggers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g10_1_g01_0.75_g11_1 | 7154.3341 | 5226.7132 | -48.6497 | -73.0566 | 5.0000 | 10357.4622 | 3625.1118 | 5 |
| manager_plus_q70_watcher | grid_g10_1_g01_0.75_g11_1 | 7058.1482 | 5156.4430 | -48.6497 | -73.0566 | 5.0000 | 10076.3813 | 3526.7335 | 3 |
| manager_plus_impulse | grid_g10_1_g01_0.75_g11_1 | 6955.0583 | 5081.1291 | -48.6497 | -73.0566 | 5.0000 | 9775.1257 | 3421.2940 | 1 |
| manager_only | grid_g10_1_g01_0.75_g11_1 | 6879.4532 | 5025.8945 | -48.6497 | -73.0566 | 5.0000 | 9554.1874 | 3343.9656 | 0 |
| fixed60 | grid_g10_1_g01_0.75_g11_1 | 6657.2185 | 4863.5374 | -48.6497 | -73.0566 | 5.0000 | 8904.7590 | 3116.6657 | 0 |

## Cell Summary

| strategy | cell | entries | base_exposure | base_weighted_total | base_mean | positive_unit_rate | unit_worst | unit_cvar05 | watch_triggers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed60 | 01_frames_only | 147 | 237.0000 | 927.5434 | 3.9137 | 0.6871 | -33.8377 | -15.5596 | 0 |
| fixed60 | 10_r5_only | 1157 | 604.0000 | 2461.1219 | 4.0747 | 0.5704 | -146.1132 | -34.3362 | 0 |
| fixed60 | 11_r5_frames | 151 | 240.5000 | 1706.7579 | 7.0967 | 0.7020 | -59.7053 | -28.2795 | 0 |
| manager_only | 01_frames_only | 147 | 237.0000 | 927.5434 | 3.9137 | 0.6871 | -33.8377 | -15.5596 | 0 |
| manager_only | 10_r5_only | 1157 | 604.0000 | 2461.1219 | 4.0747 | 0.5704 | -146.1132 | -34.3362 | 0 |
| manager_only | 11_r5_frames | 151 | 240.5000 | 1869.1150 | 7.7718 | 0.7219 | -36.4493 | -15.5357 | 0 |
| manager_plus_q70_watcher | 01_frames_only | 147 | 237.0000 | 927.5434 | 3.9137 | 0.6871 | -33.8377 | -15.5596 | 0 |
| manager_plus_q70_watcher | 10_r5_only | 1157 | 604.0000 | 2461.1219 | 4.0747 | 0.5704 | -146.1132 | -34.3362 | 0 |
| manager_plus_q70_watcher | 11_r5_frames | 151 | 240.5000 | 1999.6635 | 8.3146 | 0.7351 | -36.4493 | -15.5357 | 3 |

## Walk-Forward Sanity

This walk-forward chooses among `manager_only`, `manager_plus_impulse`,
and `manager_plus_q70_watcher` using only prior dates. It is a sanity
check, not a final live selection rule.

| test_date | chosen_strategy | chosen_variant | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | test_total | test_mean | test_watch_trigger_count | anchor_q70_total | manager_anchor_total | anchor_q70_delta_vs_manager |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | manager_only | grid_g10_1.5_g01_0.75_g11_1.5 | 1.5000 | 0.7500 | 1.5000 | 888.1984 | 4.8635 | 0 | 635.6214 | 635.6214 | 0.0000 |
| 2026-05-10 | manager_only | grid_g10_1_g01_1_g11_1.5 | 1.0000 | 1.0000 | 1.5000 | 336.4254 | 3.5413 | 0 | 439.3825 | 439.3825 | 0.0000 |
| 2026-05-11 | manager_only | grid_g10_1_g01_1_g11_1.5 | 1.0000 | 1.0000 | 1.5000 | 519.9403 | 4.2618 | 0 | 591.9515 | 591.9515 | 0.0000 |
| 2026-05-12 | manager_only | grid_g10_1_g01_1_g11_1.5 | 1.0000 | 1.0000 | 1.5000 | 592.0526 | 4.7459 | 0 | 1047.5066 | 1047.5066 | 0.0000 |
| 2026-05-13 | manager_only | grid_g10_1_g01_1_g11_1.5 | 1.0000 | 1.0000 | 1.5000 | -37.7985 | -0.4097 | 0 | 103.2617 | 103.2617 | 0.0000 |
| 2026-05-14 | manager_only | grid_g10_1_g01_0.75_g11_1.5 | 1.0000 | 0.7500 | 1.5000 | 1841.5902 | 8.7590 | 0 | 3621.7849 | 3320.5293 | 301.2557 |
| 2026-05-15 | manager_plus_q70_watcher | grid_g10_1_g01_0.75_g11_1.5 | 1.0000 | 0.7500 | 1.5000 | 1712.0722 | 9.8183 | 1 | 3006.8972 | 2785.9589 | 220.9383 |

## Q70 Watcher Trigger Rows

| date | entry_row | cell | direction_label | base_weight | target_exposure | policy_gross | watch_final_pnl_watcher_q70_absorb_reclaim2 | unit_manager_plus_q70_watcher | watch_mode_watcher_q70_absorb_reclaim2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-14 | 2322885 | 11_r5_frames | long | 0.5000 | 2.0000 | -7.7895 | 43.8440 | 36.0545 | absorb_reclaim |
| 2026-05-14 | 2379419 | 11_r5_frames | short | 2.0000 | 8.0000 | -4.7488 | 26.6959 | 21.9472 | absorb_reclaim |
| 2026-05-15 | 2583437 | 11_r5_frames | long | 1.0000 | 4.0000 | 20.2961 | 55.2346 | 75.5306 | impulse_5s |

## Read

- The q70 watcher is useful at the old anchor: it adds a small number of
  second entries and raises the anchor total without reopening the known
  bad controls.
- The historical scaled leader lowers `gamma11` sharply versus the old
  anchor. This says the old high-11 sizing is the binding risk issue,
  even after the watcher improves path management.
- q65 remains a sensitivity row only. If it tops raw totals, that does not
  make it the rule; it is closer to recall-chasing.
- This pass is historical and path-managed-universe only. The next useful
  validation is OOS path-manager/watch rebuild, not adding more watcher
  predicates.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_unit_entries_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_variants_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_frontier_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_daily_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_walkforward_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_policy_summary_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_leverage_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_cell_summary_20260519_ccusdt_v1_tfi_watcher_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_watcher_pareto_summary_20260519_ccusdt_v1_tfi_watcher_pareto_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_watcher_pareto.py
```

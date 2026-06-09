# CCUSDT ExitControllerV1 residual pressure diagnostic

This diagnostic tests the first-principles hypothesis that wait value comes from residual order-flow pressure, not from a price-shape rule.

\[
Y_{0:T}=\int_0^T \mu_u du + \int_0^T \sigma_u dW_u - C,
\qquad \mu_u \approx \lambda_u X_u.
\]

At an exit decision, the runtime-safe question is whether the remaining pressure stock \(X_t\) and its persistence still imply positive residual impact.

## Scope

- Input panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_q70_idle01_g1_20260505_18_20260522\conditional_wait_exit_panel.parquet`
- Pressure panel rows: `9856`
- Long panel rows: `49280`
- Output directory: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_residual_pressure_q70_idle01_g1_20260505_18_20260522`

## Pressure Features

- `pre_notional_imbalance_{1s,2s,5s}`: signed same-side active notional imbalance before exit.
- `pressure_persistence_1s_vs_5s`: recent pressure stock relative to the 5s stock.
- `impact_per_1k_notional_5s`: recent mid impact per 1k signed notional.
- `impact_exhaustion_ratio`: pre-exit giveback divided by `abs(recent_mid_alpha_5s_bps)+1bp`, capped at `10`, so near-zero alpha cannot dominate.
- `residual_pressure_score`: simple pre-exit composite of 1s/2s/5s pressure plus signed top-depth support.
- `pressure_exhaustion_score`: `path_d_bps/(path_h_bps+1bp)`, capped at `10`, minus pressure support; high means giveback dominates remaining pressure.

## Residual Pressure / Exhaustion Buckets

| exit_profile_source | ttl_sec | factor | factor_bin | n | exposure | weighted_mean_wait_value_bps | weighted_sum_wait_value_bps | wait_positive_rate | cvar10_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 0.5000 | pressure_exhaustion_score | q1 | 493 | 289.8750 | 0.1864 | 54.0276 | 0.0669 | -1.1102 | 0.7143 | -4.9844 |
| fixed30_livecoherent | 0.5000 | pressure_exhaustion_score | q2 | 493 | 317.3750 | -0.0030 | -0.9409 | 0.0122 | -0.4034 | 0.1429 | -2.5312 |
| fixed30_livecoherent | 0.5000 | pressure_exhaustion_score | q3 | 492 | 313.1250 | -0.0263 | -8.2331 | 0.0183 | -0.6457 | 0.1667 | -3.8365 |
| fixed30_livecoherent | 0.5000 | pressure_exhaustion_score | q4 | 493 | 288.2500 | 0.0216 | 6.2269 | 0.0304 | -3.9770 | 0.3571 | -19.9712 |
| fixed30_livecoherent | 0.5000 | pressure_exhaustion_score | q5 | 493 | 285.8750 | -0.1590 | -45.4590 | 0.0527 | -2.3086 | 0.2857 | -20.1682 |
| fixed30_livecoherent | 0.5000 | residual_pressure_score | q1 | 493 | 301.2500 | -0.2880 | -86.7566 | 0.0365 | -2.9812 | 0.1429 | -25.4576 |
| fixed30_livecoherent | 0.5000 | residual_pressure_score | q2 | 493 | 294.2500 | -0.0434 | -12.7660 | 0.0223 | -0.7941 | 0.2857 | -6.7247 |
| fixed30_livecoherent | 0.5000 | residual_pressure_score | q3 | 492 | 292.3750 | -0.0452 | -13.2188 | 0.0142 | -1.0001 | 0.2857 | -9.4562 |
| fixed30_livecoherent | 0.5000 | residual_pressure_score | q4 | 493 | 303.8750 | -0.0290 | -8.8224 | 0.0162 | -0.5500 | 0.2857 | -8.2399 |
| fixed30_livecoherent | 0.5000 | residual_pressure_score | q5 | 493 | 302.7500 | 0.4201 | 127.1852 | 0.0913 | -3.1195 | 0.7857 | -18.5960 |
| fixed30_livecoherent | 1.0000 | pressure_exhaustion_score | q1 | 493 | 289.8750 | 0.1926 | 55.8385 | 0.0892 | -2.5990 | 0.6429 | -9.0362 |
| fixed30_livecoherent | 1.0000 | pressure_exhaustion_score | q2 | 493 | 317.3750 | 0.0347 | 10.9991 | 0.0284 | -0.4162 | 0.5714 | -2.5312 |
| fixed30_livecoherent | 1.0000 | pressure_exhaustion_score | q3 | 492 | 313.1250 | -0.0778 | -24.3695 | 0.0244 | -1.3785 | 0.3333 | -16.0641 |
| fixed30_livecoherent | 1.0000 | pressure_exhaustion_score | q4 | 493 | 288.2500 | -0.1661 | -47.8887 | 0.0507 | -4.3837 | 0.2143 | -19.7284 |
| fixed30_livecoherent | 1.0000 | pressure_exhaustion_score | q5 | 493 | 285.8750 | -0.1367 | -39.0708 | 0.0669 | -3.5458 | 0.2857 | -23.6028 |
| fixed30_livecoherent | 1.0000 | residual_pressure_score | q1 | 493 | 301.2500 | -0.3359 | -101.1811 | 0.0527 | -4.0153 | 0.1429 | -35.1565 |
| fixed30_livecoherent | 1.0000 | residual_pressure_score | q2 | 493 | 294.2500 | -0.0538 | -15.8315 | 0.0284 | -1.2285 | 0.2857 | -7.5863 |
| fixed30_livecoherent | 1.0000 | residual_pressure_score | q3 | 492 | 292.3750 | -0.0582 | -17.0132 | 0.0244 | -1.5329 | 0.3571 | -9.2100 |
| fixed30_livecoherent | 1.0000 | residual_pressure_score | q4 | 493 | 303.8750 | -0.0039 | -1.1815 | 0.0365 | -1.1822 | 0.3571 | -8.4611 |
| fixed30_livecoherent | 1.0000 | residual_pressure_score | q5 | 493 | 302.7500 | 0.2996 | 90.7159 | 0.1176 | -4.3644 | 0.7857 | -13.4377 |
| fixed30_livecoherent | 2.0000 | pressure_exhaustion_score | q1 | 493 | 289.8750 | 0.1603 | 46.4686 | 0.1136 | -4.0841 | 0.5000 | -9.5962 |
| fixed30_livecoherent | 2.0000 | pressure_exhaustion_score | q2 | 493 | 317.3750 | 0.1410 | 44.7359 | 0.0406 | -0.7739 | 0.5714 | -7.2128 |
| fixed30_livecoherent | 2.0000 | pressure_exhaustion_score | q3 | 492 | 313.1250 | -0.0012 | -0.3741 | 0.0447 | -1.9580 | 0.5000 | -5.4918 |
| fixed30_livecoherent | 2.0000 | pressure_exhaustion_score | q4 | 493 | 288.2500 | -0.0027 | -0.7750 | 0.0811 | -5.3670 | 0.3571 | -35.5450 |
| fixed30_livecoherent | 2.0000 | pressure_exhaustion_score | q5 | 493 | 285.8750 | -0.2297 | -65.6636 | 0.0974 | -6.1262 | 0.2143 | -19.8581 |
| fixed30_livecoherent | 2.0000 | residual_pressure_score | q1 | 493 | 301.2500 | -0.2325 | -70.0407 | 0.0872 | -4.5721 | 0.3571 | -35.1517 |
| fixed30_livecoherent | 2.0000 | residual_pressure_score | q2 | 493 | 294.2500 | 0.0517 | 15.2110 | 0.0446 | -1.8931 | 0.4286 | -9.1324 |
| fixed30_livecoherent | 2.0000 | residual_pressure_score | q3 | 492 | 292.3750 | -0.0800 | -23.3996 | 0.0467 | -2.8598 | 0.4286 | -18.1375 |
| fixed30_livecoherent | 2.0000 | residual_pressure_score | q4 | 493 | 303.8750 | 0.0540 | 16.3989 | 0.0568 | -1.7389 | 0.5714 | -9.9180 |
| fixed30_livecoherent | 2.0000 | residual_pressure_score | q5 | 493 | 302.7500 | 0.2848 | 86.2222 | 0.1420 | -7.3459 | 0.5000 | -9.9345 |
| fixed30_livecoherent | 5.0000 | pressure_exhaustion_score | q1 | 493 | 289.8750 | 0.1820 | 52.7501 | 0.1684 | -5.9145 | 0.5000 | -18.3897 |
| fixed30_livecoherent | 5.0000 | pressure_exhaustion_score | q2 | 493 | 317.3750 | 0.2470 | 78.3770 | 0.0953 | -2.4889 | 0.4286 | -8.7102 |
| fixed30_livecoherent | 5.0000 | pressure_exhaustion_score | q3 | 492 | 313.1250 | 0.1345 | 42.1098 | 0.0915 | -4.7659 | 0.6667 | -28.8032 |
| fixed30_livecoherent | 5.0000 | pressure_exhaustion_score | q4 | 493 | 288.2500 | -0.0001 | -0.0219 | 0.1298 | -8.1568 | 0.6429 | -37.6270 |
| fixed30_livecoherent | 5.0000 | pressure_exhaustion_score | q5 | 493 | 285.8750 | -0.5146 | -147.1098 | 0.1562 | -10.9584 | 0.2857 | -49.0866 |
| fixed30_livecoherent | 5.0000 | residual_pressure_score | q1 | 493 | 301.2500 | -0.4047 | -121.9157 | 0.1460 | -7.2607 | 0.2857 | -41.2857 |
| fixed30_livecoherent | 5.0000 | residual_pressure_score | q2 | 493 | 294.2500 | 0.0655 | 19.2790 | 0.0913 | -4.6966 | 0.4286 | -29.6055 |
| fixed30_livecoherent | 5.0000 | residual_pressure_score | q3 | 492 | 292.3750 | -0.0797 | -23.2885 | 0.1098 | -6.4206 | 0.5000 | -21.3356 |
| fixed30_livecoherent | 5.0000 | residual_pressure_score | q4 | 493 | 303.8750 | 0.1557 | 47.3111 | 0.1075 | -3.0339 | 0.7143 | -10.5379 |
| fixed30_livecoherent | 5.0000 | residual_pressure_score | q5 | 493 | 302.7500 | 0.3459 | 104.7193 | 0.1866 | -11.6094 | 0.6429 | -40.9673 |
| fixed30_livecoherent | 10.0000 | pressure_exhaustion_score | q1 | 493 | 289.8750 | 0.2377 | 68.8980 | 0.2028 | -7.8375 | 0.5000 | -21.5051 |
| fixed30_livecoherent | 10.0000 | pressure_exhaustion_score | q2 | 493 | 317.3750 | 0.3123 | 99.1206 | 0.1481 | -5.0272 | 0.5714 | -10.9435 |
| fixed30_livecoherent | 10.0000 | pressure_exhaustion_score | q3 | 492 | 313.1250 | 0.3889 | 121.7820 | 0.1382 | -8.8054 | 0.8333 | 0.0000 |
| fixed30_livecoherent | 10.0000 | pressure_exhaustion_score | q4 | 493 | 288.2500 | -0.1945 | -56.0790 | 0.1907 | -12.4641 | 0.5000 | -54.9917 |
| fixed30_livecoherent | 10.0000 | pressure_exhaustion_score | q5 | 493 | 285.8750 | -0.2713 | -77.5642 | 0.2110 | -13.1903 | 0.3571 | -62.5009 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q1 | 493 | 301.2500 | -0.1218 | -36.7020 | 0.2008 | -8.7702 | 0.2857 | -68.2940 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q2 | 493 | 294.2500 | 0.0982 | 28.8936 | 0.1582 | -10.0805 | 0.3571 | -51.3447 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q3 | 492 | 292.3750 | -0.2682 | -78.4214 | 0.1504 | -10.8182 | 0.3571 | -27.3331 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q4 | 493 | 303.8750 | 0.2712 | 82.4082 | 0.1420 | -5.7167 | 0.7143 | -11.7556 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q5 | 493 | 302.7500 | 0.5284 | 159.9791 | 0.2394 | -14.0246 | 0.6429 | -44.6036 |
| fixed45_livecoherent | 0.5000 | pressure_exhaustion_score | q1 | 493 | 284.2500 | 0.1174 | 33.3689 | 0.0609 | -1.4178 | 0.7143 | -11.2287 |
| fixed45_livecoherent | 0.5000 | pressure_exhaustion_score | q2 | 493 | 305.3750 | -0.0024 | -0.7251 | 0.0041 | -0.1159 | 0.3333 | -3.2150 |
| fixed45_livecoherent | 0.5000 | pressure_exhaustion_score | q3 | 492 | 307.5000 | 0.0741 | 22.7767 | 0.0102 | -0.2623 | 0.5000 | -4.6784 |
| fixed45_livecoherent | 0.5000 | pressure_exhaustion_score | q4 | 493 | 266.0000 | -0.1058 | -28.1397 | 0.0446 | -2.0134 | 0.2857 | -24.3635 |
| fixed45_livecoherent | 0.5000 | pressure_exhaustion_score | q5 | 493 | 283.7500 | 0.0465 | 13.1870 | 0.0487 | -1.2095 | 0.3571 | -7.9327 |
| fixed45_livecoherent | 0.5000 | residual_pressure_score | q1 | 493 | 294.0000 | -0.0921 | -27.0661 | 0.0487 | -1.6735 | 0.1429 | -10.1904 |
| fixed45_livecoherent | 0.5000 | residual_pressure_score | q2 | 493 | 294.7500 | -0.0045 | -1.3231 | 0.0101 | -0.3952 | 0.3571 | -4.6784 |
| fixed45_livecoherent | 0.5000 | residual_pressure_score | q3 | 492 | 290.7500 | 0.0382 | 11.0993 | 0.0203 | -0.1439 | 0.2857 | -0.3049 |
| fixed45_livecoherent | 0.5000 | residual_pressure_score | q4 | 493 | 291.2500 | 0.0501 | 14.5985 | 0.0183 | -0.7411 | 0.4286 | -12.3648 |
| fixed45_livecoherent | 0.5000 | residual_pressure_score | q5 | 493 | 276.1250 | 0.1563 | 43.1591 | 0.0710 | -2.0652 | 0.6429 | -16.4461 |
| fixed45_livecoherent | 1.0000 | pressure_exhaustion_score | q1 | 493 | 284.2500 | 0.1157 | 32.8802 | 0.0791 | -2.2169 | 0.6429 | -23.2372 |
| fixed45_livecoherent | 1.0000 | pressure_exhaustion_score | q2 | 493 | 305.3750 | 0.0272 | 8.3009 | 0.0162 | -0.2305 | 0.5000 | -1.5750 |
| fixed45_livecoherent | 1.0000 | pressure_exhaustion_score | q3 | 492 | 307.5000 | 0.1850 | 56.8785 | 0.0183 | -0.5602 | 0.5000 | -8.6227 |
| fixed45_livecoherent | 1.0000 | pressure_exhaustion_score | q4 | 493 | 266.0000 | -0.1309 | -34.8062 | 0.0588 | -3.1043 | 0.3571 | -30.5759 |
| fixed45_livecoherent | 1.0000 | pressure_exhaustion_score | q5 | 493 | 283.7500 | 0.0616 | 17.4889 | 0.0710 | -2.8527 | 0.2857 | -9.6460 |
| fixed45_livecoherent | 1.0000 | residual_pressure_score | q1 | 493 | 294.0000 | -0.0502 | -14.7588 | 0.0649 | -2.5767 | 0.2143 | -9.8866 |
| fixed45_livecoherent | 1.0000 | residual_pressure_score | q2 | 493 | 294.7500 | -0.0427 | -12.5836 | 0.0203 | -1.1698 | 0.4286 | -8.3834 |
| fixed45_livecoherent | 1.0000 | residual_pressure_score | q3 | 492 | 290.7500 | 0.1581 | 45.9659 | 0.0427 | -0.5551 | 0.5000 | -0.7568 |
| fixed45_livecoherent | 1.0000 | residual_pressure_score | q4 | 493 | 291.2500 | 0.0716 | 20.8599 | 0.0284 | -1.2448 | 0.5000 | -13.6454 |
| fixed45_livecoherent | 1.0000 | residual_pressure_score | q5 | 493 | 276.1250 | 0.1494 | 41.2589 | 0.0872 | -3.4183 | 0.7143 | -18.6647 |
| fixed45_livecoherent | 2.0000 | pressure_exhaustion_score | q1 | 493 | 284.2500 | 0.0530 | 15.0757 | 0.1055 | -3.0996 | 0.7857 | -31.2300 |
| fixed45_livecoherent | 2.0000 | pressure_exhaustion_score | q2 | 493 | 305.3750 | 0.0334 | 10.2109 | 0.0304 | -0.7173 | 0.5000 | -2.8176 |
| fixed45_livecoherent | 2.0000 | pressure_exhaustion_score | q3 | 492 | 307.5000 | 0.1994 | 61.3266 | 0.0325 | -1.1254 | 0.5000 | -15.7822 |
| fixed45_livecoherent | 2.0000 | pressure_exhaustion_score | q4 | 493 | 266.0000 | -0.1115 | -29.6690 | 0.0974 | -5.5141 | 0.5000 | -42.2561 |
| fixed45_livecoherent | 2.0000 | pressure_exhaustion_score | q5 | 493 | 283.7500 | -0.1376 | -39.0361 | 0.0872 | -4.6204 | 0.3571 | -25.4963 |
| fixed45_livecoherent | 2.0000 | residual_pressure_score | q1 | 493 | 294.0000 | -0.1487 | -43.7158 | 0.0730 | -4.3744 | 0.2143 | -10.4135 |
| fixed45_livecoherent | 2.0000 | residual_pressure_score | q2 | 493 | 294.7500 | -0.0442 | -13.0300 | 0.0487 | -2.0165 | 0.5714 | -16.0266 |
| fixed45_livecoherent | 2.0000 | residual_pressure_score | q3 | 492 | 290.7500 | 0.1820 | 52.9096 | 0.0650 | -1.1564 | 0.6429 | -2.5669 |
| fixed45_livecoherent | 2.0000 | residual_pressure_score | q4 | 493 | 291.2500 | 0.1127 | 32.8146 | 0.0568 | -1.9569 | 0.4286 | -15.6613 |
| fixed45_livecoherent | 2.0000 | residual_pressure_score | q5 | 493 | 276.1250 | -0.0401 | -11.0703 | 0.1095 | -5.5727 | 0.6429 | -34.9430 |

## Best Pressure Buckets

| exit_profile_source | ttl_sec | factor | factor_bin | n | exposure | weighted_mean_wait_value_bps | weighted_sum_wait_value_bps | cvar10_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed60_taker | 10.0000 | recent_mid_alpha_5s_bps | q5 | 493 | 290.2500 | 1.2414 | 360.3054 | -9.6523 | 0.7143 | -26.5990 |
| stopping_rule_v1 | 10.0000 | recent_mid_alpha_5s_bps | q5 | 493 | 290.7500 | 1.2133 | 352.7639 | -9.7034 | 0.7143 | -26.5990 |
| fixed60_taker | 10.0000 | capture_pressure_gap_bps | q1 | 493 | 292.3750 | 1.0299 | 301.1215 | -7.4390 | 0.7857 | -12.7027 |
| stopping_rule_v1 | 10.0000 | capture_pressure_gap_bps | q1 | 493 | 292.6250 | 1.0004 | 292.7451 | -7.4390 | 0.7857 | -12.7027 |
| fixed60_taker | 10.0000 | residual_pressure_score | q5 | 493 | 277.1250 | 0.9667 | 267.9087 | -10.8174 | 0.7857 | -8.5086 |
| stopping_rule_v1 | 10.0000 | residual_pressure_score | q5 | 493 | 278.3750 | 0.9408 | 261.8957 | -10.8174 | 0.7857 | -8.5086 |
| stopping_rule_v1 | 10.0000 | pre_notional_imbalance_5s | q5 | 493 | 286.2500 | 0.8983 | 257.1457 | -12.0293 | 0.7143 | -10.3270 |
| fixed60_taker | 10.0000 | pre_notional_imbalance_5s | q5 | 493 | 287.3750 | 0.8831 | 253.7761 | -12.5153 | 0.7143 | -7.7158 |
| fixed30_livecoherent | 10.0000 | pressure_reversal_1s_vs_5s | q4 | 493 | 306.7500 | 0.8013 | 245.8051 | -13.4838 | 1.0000 | 0.4786 |
| fixed30_livecoherent | 10.0000 | exit_spread_bps | q4 | 493 | 304.0000 | 0.7812 | 237.4795 | -6.9371 | 0.5714 | -16.7322 |
| fixed45_livecoherent | 10.0000 | pressure_reversal_1s_vs_5s | q4 | 493 | 304.7500 | 0.7266 | 221.4278 | -12.4183 | 0.6667 | -11.9869 |
| fixed30_livecoherent | 10.0000 | pressure_persistence_1s_vs_5s | q5 | 493 | 296.2500 | 0.6876 | 203.7053 | -12.0424 | 0.5000 | -26.0243 |
| fixed30_livecoherent | 10.0000 | pre_notional_imbalance_1s | q5 | 493 | 296.2500 | 0.6876 | 203.7053 | -12.0424 | 0.5000 | -26.0243 |
| fixed60_taker | 10.0000 | pressure_exhaustion_score | q1 | 493 | 286.3750 | 0.7103 | 203.4239 | -7.5380 | 0.8571 | -10.5683 |
| fixed60_taker | 10.0000 | impact_per_1k_notional_5s | q5 | 493 | 284.0000 | 0.7118 | 202.1633 | -11.1908 | 0.6429 | -38.7835 |
| stopping_rule_v1 | 10.0000 | impact_per_1k_notional_5s | q5 | 493 | 282.8750 | 0.6920 | 195.7414 | -10.9535 | 0.6429 | -38.7835 |
| fixed45_livecoherent | 10.0000 | exit_spread_bps | q5 | 493 | 294.1250 | 0.6520 | 191.7824 | -7.1273 | 0.7143 | -34.7268 |
| fixed60_taker | 10.0000 | pre_notional_imbalance_2s | q5 | 493 | 282.3750 | 0.6680 | 188.6328 | -11.0323 | 0.6429 | -28.9315 |
| fixed60_taker | 10.0000 | pressure_persistence_2s_vs_5s | q5 | 493 | 282.3750 | 0.6680 | 188.6328 | -11.0323 | 0.6429 | -28.9315 |
| stopping_rule_v1 | 10.0000 | pressure_exhaustion_score | q1 | 493 | 286.3750 | 0.6559 | 187.8452 | -7.5380 | 0.8571 | -10.5683 |

## Current Policy Shape, Descriptive Same-Day Approximation

| exit_profile_source | ttl_sec | n | exposure | weighted_mean_wait_value_bps | weighted_sum_wait_value_bps | mean_residual_pressure_score | mean_pressure_exhaustion_score | cvar10_wait_value_bps | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 5.0000 | 449 | 289.5000 | 0.5620 | 162.6927 | 0.0518 | -0.0682 | -2.9718 | 0.7857 |
| fixed45_livecoherent | 5.0000 | 252 | 144.8750 | 0.7528 | 109.0685 | 0.0289 | 1.7592 | -3.2380 | 0.6429 |

## Prior-Bin OOS Sanity From 2026-05-16

| exit_profile_source | ttl_sec | factor | factor_bin | n | exposure | weighted_mean_wait_value_bps | weighted_sum_wait_value_bps | cvar10_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 10.0000 | pressure_exhaustion_score | q1 | 350 | 217.1250 | 0.4060 | 88.1432 | -4.9612 | 1.0000 | 10.2399 |
| fixed30_livecoherent | 5.0000 | pressure_exhaustion_score | q1 | 350 | 217.1250 | 0.2602 | 56.4968 | -1.5698 | 1.0000 | 11.1003 |
| fixed60_taker | 10.0000 | residual_pressure_score | q5 | 101 | 51.2500 | 1.0430 | 53.4517 | -6.9147 | 1.0000 | 15.0668 |
| fixed45_livecoherent | 10.0000 | residual_pressure_score | q5 | 103 | 57.7500 | 0.7378 | 42.6060 | -5.8633 | 1.0000 | 3.9508 |
| fixed45_livecoherent | 10.0000 | pressure_exhaustion_score | q1 | 310 | 193.2500 | 0.2166 | 41.8644 | -5.7629 | 0.6667 | -28.7531 |
| fixed60_taker | 5.0000 | residual_pressure_score | q5 | 101 | 51.2500 | 0.5920 | 30.3383 | -4.5367 | 1.0000 | 3.8643 |
| fixed60_taker | 10.0000 | pressure_exhaustion_score | q5 | 104 | 52.7500 | 0.5567 | 29.3658 | -8.7189 | 0.6667 | -21.9431 |
| stopping_rule_v1 | 10.0000 | residual_pressure_score | q5 | 93 | 46.0000 | 0.6273 | 28.8548 | -7.2903 | 0.6667 | -2.9679 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q4 | 83 | 54.7500 | 0.5131 | 28.0926 | -6.6505 | 0.6667 | -1.0934 |
| fixed60_taker | 10.0000 | pressure_exhaustion_score | q1 | 277 | 173.5000 | 0.1539 | 26.7102 | -8.1908 | 0.6667 | -21.2503 |
| fixed60_taker | 5.0000 | pressure_exhaustion_score | q5 | 104 | 52.7500 | 0.4793 | 25.2824 | -6.1916 | 0.6667 | -18.4982 |
| fixed45_livecoherent | 5.0000 | pressure_exhaustion_score | q1 | 310 | 193.2500 | 0.1278 | 24.7048 | -2.8558 | 0.6667 | -48.9074 |
| fixed45_livecoherent | 5.0000 | residual_pressure_score | q5 | 103 | 57.7500 | 0.4128 | 23.8364 | -6.6712 | 0.6667 | -12.1857 |
| fixed30_livecoherent | 5.0000 | residual_pressure_score | q4 | 83 | 54.7500 | 0.4228 | 23.1486 | -4.4606 | 1.0000 | 0.1983 |
| stopping_rule_v1 | 10.0000 | residual_pressure_score | q2 | 105 | 63.2500 | 0.2992 | 18.9263 | -5.0517 | 0.6667 | -7.6954 |
| stopping_rule_v1 | 5.0000 | pressure_exhaustion_score | q5 | 103 | 51.8750 | 0.3277 | 16.9974 | -6.6134 | 0.6667 | -30.8621 |
| fixed60_taker | 10.0000 | residual_pressure_score | q2 | 103 | 62.2500 | 0.1914 | 11.9143 | -5.2264 | 0.3333 | -4.8034 |
| stopping_rule_v1 | 10.0000 | pressure_exhaustion_score | q1 | 274 | 172.3750 | 0.0646 | 11.1314 | -8.1908 | 0.3333 | -26.4761 |
| stopping_rule_v1 | 10.0000 | pressure_exhaustion_score | q5 | 103 | 51.8750 | 0.2103 | 10.9113 | -9.6210 | 0.6667 | -42.0295 |
| stopping_rule_v1 | 5.0000 | residual_pressure_score | q5 | 93 | 46.0000 | 0.2146 | 9.8719 | -6.3731 | 0.6667 | -10.4021 |
| stopping_rule_v1 | 10.0000 | residual_pressure_score | q3 | 88 | 52.1250 | 0.1539 | 8.0233 | -6.2708 | 0.6667 | -17.6631 |
| fixed60_taker | 5.0000 | pressure_exhaustion_score | q1 | 277 | 173.5000 | 0.0452 | 7.8474 | -5.4397 | 0.6667 | -9.5752 |
| fixed45_livecoherent | 10.0000 | residual_pressure_score | q3 | 95 | 55.1250 | 0.1290 | 7.1117 | -5.7881 | 0.6667 | -3.9327 |
| stopping_rule_v1 | 5.0000 | residual_pressure_score | q3 | 88 | 52.1250 | 0.1267 | 6.6055 | -5.4923 | 0.3333 | -16.2718 |
| fixed30_livecoherent | 5.0000 | residual_pressure_score | q1 | 113 | 69.6250 | 0.0330 | 2.2951 | -4.9098 | 0.3333 | -5.3679 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q3 | 96 | 58.0000 | 0.0344 | 1.9945 | -12.9041 | 0.6667 | -4.3074 |
| stopping_rule_v1 | 5.0000 | residual_pressure_score | q2 | 105 | 63.2500 | 0.0269 | 1.7008 | -3.9223 | 0.6667 | -12.2375 |
| fixed45_livecoherent | 5.0000 | residual_pressure_score | q4 | 89 | 53.5000 | 0.0263 | 1.4092 | -6.5846 | 0.3333 | -18.0013 |
| stopping_rule_v1 | 5.0000 | pressure_exhaustion_score | q1 | 274 | 172.3750 | 0.0011 | 0.1851 | -5.4397 | 0.6667 | -12.0646 |
| fixed30_livecoherent | 10.0000 | residual_pressure_score | q1 | 113 | 69.6250 | 0.0006 | 0.0390 | -6.5842 | 0.6667 | -3.6785 |

## Interpretation

The pressure hypothesis is only partially supported here. High residual-pressure buckets often have better wait value, and high exhaustion buckets are usually worse, but the currently selected conservative wait shape has only mild average residual pressure. So the existing wait overlay should still be treated as a coarse exit-timing gate, not yet as a true latent residual-pressure controller.

The next non-overfit step is not to add many more handcrafted pattern flags. It is to test whether a small prior-date pressure admission rule can improve the existing wait overlay without increasing left-tail cost, using only pre-exit pressure state.

## Files

- Pressure panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_residual_pressure_q70_idle01_g1_20260505_18_20260522\exit_residual_pressure_panel.parquet`
- Long panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_residual_pressure_q70_idle01_g1_20260505_18_20260522\exit_residual_pressure_long_panel.parquet`
- Factor summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_residual_pressure_q70_idle01_g1_20260505_18_20260522\exit_residual_pressure_factor_summary.csv`
- Prior-bin OOS summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_residual_pressure_q70_idle01_g1_20260505_18_20260522\exit_residual_pressure_prior_bin_oos_summary.csv`
- Summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_residual_pressure_q70_idle01_g1_20260505_18_20260522\summary.json`

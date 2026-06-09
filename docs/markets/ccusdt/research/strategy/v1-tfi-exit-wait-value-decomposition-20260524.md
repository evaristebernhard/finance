# CCUSDT exit wait-value decomposition

This diagnostic asks what a wait-before-crossing exit actually earns.

\[
W_t(\tau)
= q\,10^4\log\frac{m_{t+\tau}}{m_t}
+ \left(\kappa_t-\kappa_{t+\tau}\right)
+ \epsilon_t.
\]

Here \(q=+1\) for long exits and \(q=-1\) for short exits. For a long, \(\kappa=10^4\log(m/bid)\); for a short, \(\kappa=10^4\log(ask/m)\).

## Scope

- Input panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_residual_pressure_q70_idle01_g1_20260505_18_20260522\exit_residual_pressure_long_panel.parquet`
- Selected wait events: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_policy_q70_idle01_g1_m010_20260516_18_20260522\conditional_wait_events.parquet`
- Decomposition rows: `49280`
- Max absolute reconstruction error: `0.00000000` bps
- Output directory: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_wait_value_decomposition_q70_idle01_g1_20260505_18_20260524`

## Selected Wait Policy Decomposition

- Total selected wait delta: `68.3173` weighted bp-units.
- Mid component: `47.3169`.
- Crossing/spread component: `21.0004`.

| exit_profile_source | ttl_sec | n | exposure | weighted_wait_value_bps | weighted_mid_component_bps | weighted_cross_component_bps | cvar10_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 5.0000 | 85 | 56.7500 | 39.5357 | 27.3347 | 12.2010 | -1.3821 | 1.0000 | 2.5190 |
| fixed45_livecoherent | 5.0000 | 62 | 35.0000 | 28.7816 | 19.9823 | 8.7994 | -3.6391 | 0.6667 | -0.4803 |

## Selected Wait By Day

| exit_profile_source | date | n | exposure | weighted_wait_value_bps | weighted_mid_component_bps | weighted_cross_component_bps | cvar10_wait_value_bps | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | 26 | 17.3750 | 2.5190 | 0.3578 | 2.1613 | -1.1099 | 2.5190 |
| fixed30_livecoherent | 2026-05-17 | 29 | 20.8750 | 19.0566 | 12.5442 | 6.5124 | -3.0365 | 19.0566 |
| fixed30_livecoherent | 2026-05-18 | 30 | 18.5000 | 17.9600 | 14.4327 | 3.5273 | 0.0000 | 17.9600 |
| fixed45_livecoherent | 2026-05-16 | 17 | 8.5000 | -0.4803 | -3.9445 | 3.4642 | -3.9485 | -0.4803 |
| fixed45_livecoherent | 2026-05-17 | 26 | 17.6250 | 28.9107 | 25.1754 | 3.7353 | -2.3799 | 28.9107 |
| fixed45_livecoherent | 2026-05-18 | 19 | 8.8750 | 0.3512 | -1.2487 | 1.5999 | -5.2186 | 0.3512 |

## All Wait Opportunities By TTL

| exit_profile_source | ttl_sec | n | exposure | weighted_wait_value_bps | weighted_mid_component_bps | weighted_cross_component_bps | cvar10_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 0.5000 | 2464 | 1494.5000 | 5.6214 | 0.3683 | 5.2531 | -1.7095 | 0.5000 | -23.6573 |
| fixed30_livecoherent | 1.0000 | 2464 | 1494.5000 | -44.4914 | -55.8191 | 11.3277 | -2.4946 | 0.4286 | -40.5565 |
| fixed30_livecoherent | 2.0000 | 2464 | 1494.5000 | 24.3918 | 9.0766 | 15.3152 | -3.7267 | 0.5714 | -37.3367 |
| fixed30_livecoherent | 5.0000 | 2464 | 1494.5000 | 26.1053 | 2.2984 | 23.8068 | -6.9565 | 0.5000 | -59.7417 |
| fixed30_livecoherent | 10.0000 | 2464 | 1494.5000 | 156.1575 | 168.3186 | -12.1611 | -10.1923 | 0.5714 | -63.5943 |
| fixed45_livecoherent | 0.5000 | 2464 | 1446.8750 | 40.4677 | 38.5576 | 1.9101 | -1.0160 | 0.4286 | -24.6025 |
| fixed45_livecoherent | 1.0000 | 2464 | 1446.8750 | 80.7423 | 79.0546 | 1.6877 | -1.8147 | 0.5714 | -32.0653 |
| fixed45_livecoherent | 2.0000 | 2464 | 1446.8750 | 17.9081 | 16.4695 | 1.4386 | -3.0520 | 0.7143 | -45.7179 |
| fixed45_livecoherent | 5.0000 | 2464 | 1446.8750 | 162.9725 | 166.1296 | -3.1571 | -5.6136 | 0.7143 | -100.9860 |
| fixed45_livecoherent | 10.0000 | 2464 | 1446.8750 | 287.8510 | 273.3476 | 14.5035 | -8.9589 | 0.6429 | -70.6255 |
| fixed60_taker | 0.5000 | 2464 | 1450.6250 | -54.8149 | -50.1967 | -4.6182 | -0.9813 | 0.1429 | -19.8322 |
| fixed60_taker | 1.0000 | 2464 | 1450.6250 | -66.6981 | -59.5850 | -7.1130 | -1.6721 | 0.2857 | -14.4528 |
| fixed60_taker | 2.0000 | 2464 | 1450.6250 | -173.4959 | -166.8084 | -6.6875 | -3.3819 | 0.2143 | -72.0512 |
| fixed60_taker | 5.0000 | 2464 | 1450.6250 | -44.6472 | -34.5697 | -10.0774 | -6.1533 | 0.4286 | -47.6733 |
| fixed60_taker | 10.0000 | 2464 | 1450.6250 | 41.1441 | 56.9187 | -15.7746 | -9.6584 | 0.3571 | -65.8783 |
| stopping_rule_v1 | 0.5000 | 2464 | 1450.6250 | -56.0930 | -53.1391 | -2.9538 | -0.9997 | 0.1429 | -19.8322 |
| stopping_rule_v1 | 1.0000 | 2464 | 1450.6250 | -67.5221 | -63.5166 | -4.0055 | -1.6564 | 0.2857 | -13.5332 |
| stopping_rule_v1 | 2.0000 | 2464 | 1450.6250 | -168.5437 | -165.1677 | -3.3760 | -3.2892 | 0.2143 | -72.0512 |
| stopping_rule_v1 | 5.0000 | 2464 | 1450.6250 | -58.8642 | -54.1729 | -4.6912 | -6.1357 | 0.4286 | -59.0916 |
| stopping_rule_v1 | 10.0000 | 2464 | 1450.6250 | -10.0958 | 3.2120 | -13.3078 | -9.7713 | 0.3571 | -106.2812 |

## Prior-Exhaustion OOS Decomposition From 2026-05-16

| exit_profile_source | ttl_sec | pressure_exhaustion_prior_bin | n | exposure | weighted_wait_value_bps | weighted_mid_component_bps | weighted_cross_component_bps | cvar10_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 5.0000 | q1 | 350 | 217.1250 | 56.4968 | 50.9905 | 5.5062 | -1.5698 | 1.0000 | 11.1003 |
| fixed30_livecoherent | 5.0000 | q4 | 60 | 34.5000 | -24.6124 | -25.2757 | 0.6632 | -7.9725 | 0.3333 | -12.8342 |
| fixed30_livecoherent | 5.0000 | q5 | 94 | 52.3750 | -72.8069 | -71.9307 | -0.8762 | -16.2201 | 0.0000 | -38.5828 |
| fixed45_livecoherent | 5.0000 | q1 | 310 | 193.2500 | 24.7048 | 34.5645 | -9.8596 | -2.8558 | 0.6667 | -48.9074 |
| fixed45_livecoherent | 5.0000 | q3 | 5 | 4.1250 | -1.4717 | -1.9621 | 0.4903 | -3.9246 | 0.0000 | -1.4717 |
| fixed45_livecoherent | 5.0000 | q4 | 99 | 56.8750 | -53.4292 | -54.4052 | 0.9760 | -11.2811 | 0.0000 | -35.6987 |
| fixed45_livecoherent | 5.0000 | q5 | 90 | 45.7500 | -15.1125 | -15.3689 | 0.2564 | -6.3988 | 0.3333 | -16.3799 |

## Interpretation

The current selected wait overlay is not just spread recovery. Most of its gain comes from favorable mid continuation, while a smaller but meaningful part comes from cheaper crossing after waiting.

The exhaustion diagnostic is therefore better interpreted as a mid-continuation guard: low exhaustion means the favorable move has not fully decayed, while high exhaustion means waiting mostly inherits adverse mid movement. The crossing term matters, but it is not large enough by itself to explain the selected wait gain.

## Files

- Decomposition panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_wait_value_decomposition_q70_idle01_g1_20260505_18_20260524\exit_wait_value_decomposition_panel.parquet`
- TTL summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_wait_value_decomposition_q70_idle01_g1_20260505_18_20260524\exit_wait_value_decomposition_ttl_summary.csv`
- Selected aggregate: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_wait_value_decomposition_q70_idle01_g1_20260505_18_20260524\exit_wait_value_decomposition_selected_aggregate.csv`
- Prior-exhaustion OOS summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_wait_value_decomposition_q70_idle01_g1_20260505_18_20260524\exit_wait_value_decomposition_prior_exhaustion_oos.csv`
- Summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\exit_wait_value_decomposition_q70_idle01_g1_20260505_18_20260524\summary.json`

# CCUSDT q70 idle01_g1 maker-first exit opportunity

This is an offline execution diagnostic for existing-position exits only. It does not study maker entry, and it does not read `date/`, scored entries, future labels, MFE/MAE, or root research scripts as runtime inputs.

## Model

At an exit decision time \(t\), compare immediate taker exit \(Y^T_t\) with a passive touch exit \(Y^M_t\). For a long position, taker sells bid and maker posts sell at ask; for a short position, taker buys ask and maker posts buy at bid.

\[
\Delta^{spread}_t = Y^M_t - Y^T_t.
\]

For TTL \(\tau\), the maker-first controller has two risks: no fill followed by fallback decay, and fill-side adverse selection. The diagnostic estimates the signed decomposition

\[
\mathbb E[\Delta_t(\tau)] \approx p_t(\tau)\Delta^{spread}_t - (1-p_t(\tau))L^{unfilled}_t(\tau) - A^{selection}_t(\tau).
\]

`touch_trade_proxy_v1` fills when any opposite aggressor trade reaches the posted touch. `queue_ahead_trade_proxy_v1` additionally requires cumulative opposite trade quantity to consume the displayed top-of-book queue ahead. The second proxy is deliberately harsher.

## Scope

- Symbol: `CCUSDT`
- Dates: `2026-05-16..2026-05-18`
- Candidate profiles: `fixed30_livecoherent, fixed45_livecoherent, fixed60_taker, stopping_rule_v1`
- Candidate exits with actual exposure: `2016`
- Panel rows: `6048`
- Output directory: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_opportunity_q70_idle01_g1_20260516_18_20260522`

## Readout

- Global queue-ahead maker-first is not promoted: best whole-profile row is `fixed30_livecoherent / TTL=1.0s`, weighted delta `-18.1118` bp-units, mean `-0.0596` bps, positive-day fraction `0.3333`.
- Positive whole-profile queue rows: `0` out of `12`. The full-sample controller should therefore remain direct taker unless a narrow runtime-safe gate is used.
- Strongest queue-aware factor bucket is `fixed30_livecoherent / TTL=5.0s / exit_spread_bps=q5`, n `101`, exposure `64.7500`, fill rate `0.0792`, delta sum `21.0057`, selection-adjusted sum `18.6150`, positive-day fraction `1.0000`.
- This is a diagnostic bucket read, not a live rule: factor thresholds must be re-expressed as prior-date/runtime-safe gates before `maker_first_exit_v1` can be enabled.

## TTL Summary

| exit_profile_source | ttl_sec | fill_model | n | exposure | fill_rate | weighted_mean_spread_term_bps | weighted_mean_unfilled_decay_term_bps | weighted_mean_selection_term_bps | weighted_mean_delta_vs_taker_bps | weighted_sum_delta_vs_taker_bps | positive_day_frac | min_day_delta_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 504 | 304.0000 | 0.0159 | 0.0222 | 0.0817 | 0.0166 | -0.0596 | -18.1118 | 0.3333 | -20.3088 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 504 | 304.0000 | 0.0159 | 0.0222 | 0.0817 | 0.0166 | -0.0596 | -18.1118 | 0.3333 | -20.3088 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 504 | 304.0000 | 0.0476 | 0.0672 | 0.1477 | 0.0451 | -0.0804 | -24.4523 | 0.3333 | -24.9920 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 504 | 304.0000 | 0.0476 | 0.0672 | 0.1477 | 0.0451 | -0.0804 | -24.4523 | 0.3333 | -24.9920 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 504 | 304.0000 | 0.0853 | 0.1325 | 0.4460 | 0.1786 | -0.3135 | -95.2934 | 0.0000 | -47.7117 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 504 | 304.0000 | 0.0933 | 0.1583 | 0.4876 | 0.1944 | -0.3293 | -100.1136 | 0.0000 | -47.7117 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 504 | 300.0000 | 0.0218 | 0.0545 | 0.1753 | 0.0899 | -0.1209 | -36.2658 | 0.3333 | -35.7696 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 504 | 300.0000 | 0.0218 | 0.0545 | 0.1753 | 0.0899 | -0.1209 | -36.2658 | 0.3333 | -35.7696 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 504 | 300.0000 | 0.0397 | 0.1008 | 0.1966 | 0.1486 | -0.0958 | -28.7433 | 0.6667 | -36.3314 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 504 | 300.0000 | 0.0397 | 0.1008 | 0.1966 | 0.1486 | -0.0958 | -28.7433 | 0.6667 | -36.3314 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 504 | 300.0000 | 0.0774 | 0.1863 | 0.5398 | 0.2364 | -0.3535 | -106.0644 | 0.0000 | -100.2322 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 504 | 300.0000 | 0.0813 | 0.1927 | 0.5398 | 0.2300 | -0.3472 | -104.1495 | 0.0000 | -100.2322 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 504 | 298.6250 | 0.0198 | 0.0408 | 0.1456 | 0.0494 | -0.1048 | -31.2923 | 0.0000 | -15.6842 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 504 | 298.6250 | 0.0198 | 0.0408 | 0.1456 | 0.0494 | -0.1048 | -31.2923 | 0.0000 | -15.6842 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 504 | 298.6250 | 0.0317 | 0.0562 | 0.2095 | 0.0878 | -0.1533 | -45.7789 | 0.3333 | -38.4033 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 504 | 298.6250 | 0.0337 | 0.0627 | 0.2147 | 0.0865 | -0.1520 | -45.3877 | 0.3333 | -38.4033 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 504 | 298.6250 | 0.0754 | 0.1452 | 0.4832 | 0.2137 | -0.3381 | -100.9528 | 0.0000 | -64.8444 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 504 | 298.6250 | 0.0813 | 0.1586 | 0.4917 | 0.2088 | -0.3331 | -99.4837 | 0.3333 | -64.6028 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 504 | 298.6250 | 0.0159 | 0.0333 | 0.1359 | 0.0445 | -0.1026 | -30.6360 | 0.0000 | -13.5332 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 504 | 298.6250 | 0.0159 | 0.0333 | 0.1359 | 0.0445 | -0.1026 | -30.6360 | 0.0000 | -13.5332 |
| stopping_rule_v1 | 2.0000 | queue_trade_proxy_v1 | 504 | 298.6250 | 0.0278 | 0.0524 | 0.1795 | 0.0783 | -0.1272 | -37.9789 | 0.3333 | -25.8035 |
| stopping_rule_v1 | 2.0000 | touch_trade_proxy_v1 | 504 | 298.6250 | 0.0298 | 0.0589 | 0.1848 | 0.0769 | -0.1259 | -37.5877 | 0.3333 | -25.8035 |
| stopping_rule_v1 | 5.0000 | queue_trade_proxy_v1 | 504 | 298.6250 | 0.0754 | 0.1495 | 0.4426 | 0.2138 | -0.2931 | -87.5245 | 0.0000 | -50.1109 |
| stopping_rule_v1 | 5.0000 | touch_trade_proxy_v1 | 504 | 298.6250 | 0.0813 | 0.1629 | 0.4511 | 0.2089 | -0.2882 | -86.0554 | 0.3333 | -49.8694 |

## Day Stability

| exit_profile_source | date | ttl_sec | fill_model | n | exposure | fill_rate | weighted_sum_delta_vs_taker_bps | weighted_mean_delta_vs_taker_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | 1.0000 | queue_trade_proxy_v1 | 149 | 91.7500 | 0.0067 | -20.3088 | -0.2213 |
| fixed30_livecoherent | 2026-05-17 | 1.0000 | queue_trade_proxy_v1 | 143 | 83.8750 | 0.0070 | 3.7348 | 0.0445 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | queue_trade_proxy_v1 | 212 | 128.3750 | 0.0283 | -1.5379 | -0.0120 |
| fixed30_livecoherent | 2026-05-16 | 1.0000 | touch_trade_proxy_v1 | 149 | 91.7500 | 0.0067 | -20.3088 | -0.2213 |
| fixed30_livecoherent | 2026-05-17 | 1.0000 | touch_trade_proxy_v1 | 143 | 83.8750 | 0.0070 | 3.7348 | 0.0445 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | touch_trade_proxy_v1 | 212 | 128.3750 | 0.0283 | -1.5379 | -0.0120 |
| fixed30_livecoherent | 2026-05-16 | 2.0000 | queue_trade_proxy_v1 | 149 | 91.7500 | 0.0537 | -24.9920 | -0.2724 |
| fixed30_livecoherent | 2026-05-17 | 2.0000 | queue_trade_proxy_v1 | 143 | 83.8750 | 0.0350 | -0.3908 | -0.0047 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | queue_trade_proxy_v1 | 212 | 128.3750 | 0.0519 | 0.9305 | 0.0072 |
| fixed30_livecoherent | 2026-05-16 | 2.0000 | touch_trade_proxy_v1 | 149 | 91.7500 | 0.0537 | -24.9920 | -0.2724 |
| fixed30_livecoherent | 2026-05-17 | 2.0000 | touch_trade_proxy_v1 | 143 | 83.8750 | 0.0350 | -0.3908 | -0.0047 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | touch_trade_proxy_v1 | 212 | 128.3750 | 0.0519 | 0.9305 | 0.0072 |
| fixed30_livecoherent | 2026-05-16 | 5.0000 | queue_trade_proxy_v1 | 149 | 91.7500 | 0.0940 | -47.7117 | -0.5200 |
| fixed30_livecoherent | 2026-05-17 | 5.0000 | queue_trade_proxy_v1 | 143 | 83.8750 | 0.0979 | -46.9937 | -0.5603 |
| fixed30_livecoherent | 2026-05-18 | 5.0000 | queue_trade_proxy_v1 | 212 | 128.3750 | 0.0708 | -0.5880 | -0.0046 |
| fixed30_livecoherent | 2026-05-16 | 5.0000 | touch_trade_proxy_v1 | 149 | 91.7500 | 0.0940 | -47.7117 | -0.5200 |
| fixed30_livecoherent | 2026-05-17 | 5.0000 | touch_trade_proxy_v1 | 143 | 83.8750 | 0.0979 | -46.9937 | -0.5603 |
| fixed30_livecoherent | 2026-05-18 | 5.0000 | touch_trade_proxy_v1 | 212 | 128.3750 | 0.0896 | -5.4082 | -0.0421 |
| fixed45_livecoherent | 2026-05-16 | 1.0000 | queue_trade_proxy_v1 | 149 | 91.3750 | 0.0201 | -35.7696 | -0.3915 |
| fixed45_livecoherent | 2026-05-17 | 1.0000 | queue_trade_proxy_v1 | 143 | 84.0000 | 0.0070 | -1.5821 | -0.0188 |
| fixed45_livecoherent | 2026-05-18 | 1.0000 | queue_trade_proxy_v1 | 212 | 124.6250 | 0.0330 | 1.0860 | 0.0087 |
| fixed45_livecoherent | 2026-05-16 | 1.0000 | touch_trade_proxy_v1 | 149 | 91.3750 | 0.0201 | -35.7696 | -0.3915 |
| fixed45_livecoherent | 2026-05-17 | 1.0000 | touch_trade_proxy_v1 | 143 | 84.0000 | 0.0070 | -1.5821 | -0.0188 |
| fixed45_livecoherent | 2026-05-18 | 1.0000 | touch_trade_proxy_v1 | 212 | 124.6250 | 0.0330 | 1.0860 | 0.0087 |
| fixed45_livecoherent | 2026-05-16 | 2.0000 | queue_trade_proxy_v1 | 149 | 91.3750 | 0.0336 | -36.3314 | -0.3976 |
| fixed45_livecoherent | 2026-05-17 | 2.0000 | queue_trade_proxy_v1 | 143 | 84.0000 | 0.0490 | 4.2780 | 0.0509 |
| fixed45_livecoherent | 2026-05-18 | 2.0000 | queue_trade_proxy_v1 | 212 | 124.6250 | 0.0377 | 3.3102 | 0.0266 |
| fixed45_livecoherent | 2026-05-16 | 2.0000 | touch_trade_proxy_v1 | 149 | 91.3750 | 0.0336 | -36.3314 | -0.3976 |
| fixed45_livecoherent | 2026-05-17 | 2.0000 | touch_trade_proxy_v1 | 143 | 84.0000 | 0.0490 | 4.2780 | 0.0509 |
| fixed45_livecoherent | 2026-05-18 | 2.0000 | touch_trade_proxy_v1 | 212 | 124.6250 | 0.0377 | 3.3102 | 0.0266 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | queue_trade_proxy_v1 | 149 | 91.3750 | 0.0738 | -100.2322 | -1.0969 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | queue_trade_proxy_v1 | 143 | 84.0000 | 0.0909 | -1.1351 | -0.0135 |
| fixed45_livecoherent | 2026-05-18 | 5.0000 | queue_trade_proxy_v1 | 212 | 124.6250 | 0.0708 | -4.6971 | -0.0377 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | touch_trade_proxy_v1 | 149 | 91.3750 | 0.0738 | -100.2322 | -1.0969 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | touch_trade_proxy_v1 | 143 | 84.0000 | 0.0979 | -0.8917 | -0.0106 |
| fixed45_livecoherent | 2026-05-18 | 5.0000 | touch_trade_proxy_v1 | 212 | 124.6250 | 0.0755 | -3.0256 | -0.0243 |
| fixed60_taker | 2026-05-16 | 1.0000 | queue_trade_proxy_v1 | 149 | 92.7500 | 0.0268 | -4.5257 | -0.0488 |
| fixed60_taker | 2026-05-17 | 1.0000 | queue_trade_proxy_v1 | 143 | 82.6250 | 0.0070 | -15.6842 | -0.1898 |
| fixed60_taker | 2026-05-18 | 1.0000 | queue_trade_proxy_v1 | 212 | 123.2500 | 0.0236 | -11.0823 | -0.0899 |
| fixed60_taker | 2026-05-16 | 1.0000 | touch_trade_proxy_v1 | 149 | 92.7500 | 0.0268 | -4.5257 | -0.0488 |
| fixed60_taker | 2026-05-17 | 1.0000 | touch_trade_proxy_v1 | 143 | 82.6250 | 0.0070 | -15.6842 | -0.1898 |
| fixed60_taker | 2026-05-18 | 1.0000 | touch_trade_proxy_v1 | 212 | 123.2500 | 0.0236 | -11.0823 | -0.0899 |
| fixed60_taker | 2026-05-16 | 2.0000 | queue_trade_proxy_v1 | 149 | 92.7500 | 0.0336 | 10.9744 | 0.1183 |
| fixed60_taker | 2026-05-17 | 2.0000 | queue_trade_proxy_v1 | 143 | 82.6250 | 0.0280 | -38.4033 | -0.4648 |
| fixed60_taker | 2026-05-18 | 2.0000 | queue_trade_proxy_v1 | 212 | 123.2500 | 0.0330 | -18.3500 | -0.1489 |
| fixed60_taker | 2026-05-16 | 2.0000 | touch_trade_proxy_v1 | 149 | 92.7500 | 0.0403 | 11.3656 | 0.1225 |
| fixed60_taker | 2026-05-17 | 2.0000 | touch_trade_proxy_v1 | 143 | 82.6250 | 0.0280 | -38.4033 | -0.4648 |
| fixed60_taker | 2026-05-18 | 2.0000 | touch_trade_proxy_v1 | 212 | 123.2500 | 0.0330 | -18.3500 | -0.1489 |
| fixed60_taker | 2026-05-16 | 5.0000 | queue_trade_proxy_v1 | 149 | 92.7500 | 0.1007 | -0.3883 | -0.0042 |
| fixed60_taker | 2026-05-17 | 5.0000 | queue_trade_proxy_v1 | 143 | 82.6250 | 0.0420 | -64.8444 | -0.7848 |
| fixed60_taker | 2026-05-18 | 5.0000 | queue_trade_proxy_v1 | 212 | 123.2500 | 0.0802 | -35.7201 | -0.2898 |
| fixed60_taker | 2026-05-16 | 5.0000 | touch_trade_proxy_v1 | 149 | 92.7500 | 0.1074 | 0.0029 | 0.0000 |
| fixed60_taker | 2026-05-17 | 5.0000 | touch_trade_proxy_v1 | 143 | 82.6250 | 0.0490 | -64.6028 | -0.7819 |
| fixed60_taker | 2026-05-18 | 5.0000 | touch_trade_proxy_v1 | 212 | 123.2500 | 0.0849 | -34.8837 | -0.2830 |
| stopping_rule_v1 | 2026-05-16 | 1.0000 | queue_trade_proxy_v1 | 149 | 92.7500 | 0.0268 | -4.5257 | -0.0488 |
| stopping_rule_v1 | 2026-05-17 | 1.0000 | queue_trade_proxy_v1 | 143 | 82.6250 | 0.0000 | -13.5332 | -0.1638 |
| stopping_rule_v1 | 2026-05-18 | 1.0000 | queue_trade_proxy_v1 | 212 | 123.2500 | 0.0189 | -12.5771 | -0.1020 |
| stopping_rule_v1 | 2026-05-16 | 1.0000 | touch_trade_proxy_v1 | 149 | 92.7500 | 0.0268 | -4.5257 | -0.0488 |
| stopping_rule_v1 | 2026-05-17 | 1.0000 | touch_trade_proxy_v1 | 143 | 82.6250 | 0.0000 | -13.5332 | -0.1638 |
| stopping_rule_v1 | 2026-05-18 | 1.0000 | touch_trade_proxy_v1 | 212 | 123.2500 | 0.0189 | -12.5771 | -0.1020 |
| stopping_rule_v1 | 2026-05-16 | 2.0000 | queue_trade_proxy_v1 | 149 | 92.7500 | 0.0336 | 10.9744 | 0.1183 |
| stopping_rule_v1 | 2026-05-17 | 2.0000 | queue_trade_proxy_v1 | 143 | 82.6250 | 0.0210 | -25.8035 | -0.3123 |
| stopping_rule_v1 | 2026-05-18 | 2.0000 | queue_trade_proxy_v1 | 212 | 123.2500 | 0.0283 | -23.1499 | -0.1878 |
| stopping_rule_v1 | 2026-05-16 | 2.0000 | touch_trade_proxy_v1 | 149 | 92.7500 | 0.0403 | 11.3656 | 0.1225 |
| stopping_rule_v1 | 2026-05-17 | 2.0000 | touch_trade_proxy_v1 | 143 | 82.6250 | 0.0210 | -25.8035 | -0.3123 |
| stopping_rule_v1 | 2026-05-18 | 2.0000 | touch_trade_proxy_v1 | 212 | 123.2500 | 0.0283 | -23.1499 | -0.1878 |
| stopping_rule_v1 | 2026-05-16 | 5.0000 | queue_trade_proxy_v1 | 149 | 92.7500 | 0.1007 | -0.3883 | -0.0042 |
| stopping_rule_v1 | 2026-05-17 | 5.0000 | queue_trade_proxy_v1 | 143 | 82.6250 | 0.0490 | -50.1109 | -0.6065 |
| stopping_rule_v1 | 2026-05-18 | 5.0000 | queue_trade_proxy_v1 | 212 | 123.2500 | 0.0755 | -37.0253 | -0.3004 |
| stopping_rule_v1 | 2026-05-16 | 5.0000 | touch_trade_proxy_v1 | 149 | 92.7500 | 0.1074 | 0.0029 | 0.0000 |
| stopping_rule_v1 | 2026-05-17 | 5.0000 | touch_trade_proxy_v1 | 143 | 82.6250 | 0.0559 | -49.8694 | -0.6036 |
| stopping_rule_v1 | 2026-05-18 | 5.0000 | touch_trade_proxy_v1 | 212 | 123.2500 | 0.0802 | -36.1889 | -0.2936 |

## Cell Readout

| exit_profile_source | ttl_sec | fill_model | cell | n | exposure | fill_rate | weighted_sum_delta_vs_taker_bps | weighted_mean_selection_adjusted_delta_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 24 | 32.2500 | 0.0000 | 2.4511 | 0.0760 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 23 | 37.0000 | 0.0000 | -1.1709 | -0.0316 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 240 | 95.6250 | 0.0125 | -3.7102 | -0.0748 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 00_none | 217 | 139.1250 | 0.0230 | -15.6819 | -0.1243 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 24 | 32.2500 | 0.0000 | 2.4511 | 0.0760 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 23 | 37.0000 | 0.0000 | -1.1709 | -0.0316 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 240 | 95.6250 | 0.0125 | -3.7102 | -0.0748 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 00_none | 217 | 139.1250 | 0.0230 | -15.6819 | -0.1243 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 11_r5_frames | 24 | 32.2500 | 0.0000 | 2.4511 | 0.0760 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 01_frames_only | 23 | 37.0000 | 0.0000 | -1.1709 | -0.0316 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 00_none | 217 | 139.1250 | 0.0415 | -8.5544 | -0.0946 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 10_r5_only | 240 | 95.6250 | 0.0625 | -17.1782 | -0.2750 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 11_r5_frames | 24 | 32.2500 | 0.0000 | 2.4511 | 0.0760 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 01_frames_only | 23 | 37.0000 | 0.0000 | -1.1709 | -0.0316 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 00_none | 217 | 139.1250 | 0.0415 | -8.5544 | -0.0946 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 10_r5_only | 240 | 95.6250 | 0.0625 | -17.1782 | -0.2750 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 11_r5_frames | 24 | 32.2500 | 0.1250 | 14.8942 | 0.2878 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 10_r5_only | 240 | 95.6250 | 0.0875 | -24.0962 | -0.4294 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 01_frames_only | 23 | 37.0000 | 0.0000 | -34.3181 | -0.9275 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 00_none | 217 | 139.1250 | 0.0876 | -51.7733 | -0.6000 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 11_r5_frames | 24 | 32.2500 | 0.1250 | 14.8942 | 0.2878 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 10_r5_only | 240 | 95.6250 | 0.0917 | -26.0620 | -0.4705 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 01_frames_only | 23 | 37.0000 | 0.0435 | -35.9447 | -1.0154 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 00_none | 217 | 139.1250 | 0.0968 | -53.0011 | -0.6177 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 29 | 38.6250 | 0.0690 | 6.8207 | -0.0751 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 18 | 28.5000 | 0.0000 | 0.0000 | 0.0000 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 248 | 98.6250 | 0.0202 | -0.2331 | -0.0351 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 00_none | 209 | 134.2500 | 0.0191 | -42.8534 | -0.4236 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 29 | 38.6250 | 0.0690 | 6.8207 | -0.0751 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 18 | 28.5000 | 0.0000 | 0.0000 | 0.0000 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 248 | 98.6250 | 0.0202 | -0.2331 | -0.0351 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 00_none | 209 | 134.2500 | 0.0191 | -42.8534 | -0.4236 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 11_r5_frames | 29 | 38.6250 | 0.0690 | 6.8207 | -0.0751 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 10_r5_only | 248 | 98.6250 | 0.0403 | -0.5604 | -0.0961 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 01_frames_only | 18 | 28.5000 | 0.0000 | -1.6398 | -0.0575 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 00_none | 209 | 134.2500 | 0.0383 | -33.3637 | -0.4419 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 11_r5_frames | 29 | 38.6250 | 0.0690 | 6.8207 | -0.0751 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 10_r5_only | 248 | 98.6250 | 0.0403 | -0.5604 | -0.0961 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 01_frames_only | 18 | 28.5000 | 0.0000 | -1.6398 | -0.0575 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 00_none | 209 | 134.2500 | 0.0383 | -33.3637 | -0.4419 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 11_r5_frames | 29 | 38.6250 | 0.1034 | 8.8025 | -0.1784 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 10_r5_only | 248 | 98.6250 | 0.0685 | -16.7589 | -0.3793 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 00_none | 209 | 134.2500 | 0.0909 | -48.9599 | -0.6223 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 01_frames_only | 18 | 28.5000 | 0.0000 | -49.1481 | -1.7245 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 11_r5_frames | 29 | 38.6250 | 0.1034 | 8.8025 | -0.1784 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 10_r5_only | 248 | 98.6250 | 0.0726 | -16.5155 | -0.3743 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 00_none | 209 | 134.2500 | 0.0957 | -47.2884 | -0.5974 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 01_frames_only | 18 | 28.5000 | 0.0000 | -49.1481 | -1.7245 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0333 | 1.5822 | -0.1867 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0233 | -0.1082 | -0.0423 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0000 | -3.8007 | -0.1246 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0151 | -28.9656 | -0.2392 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0333 | 1.5822 | -0.1867 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0233 | -0.1082 | -0.0423 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0000 | -3.8007 | -0.1246 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0151 | -28.9656 | -0.2392 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0333 | 1.5822 | -0.1867 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0000 | -7.0640 | -0.2316 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0310 | -18.4515 | -0.2960 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0352 | -21.8456 | -0.2161 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0333 | 1.5822 | -0.1867 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0000 | -7.0640 | -0.2316 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0310 | -18.4515 | -0.2960 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0402 | -21.4544 | -0.2100 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0667 | 7.7301 | -0.5785 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0588 | -6.3557 | -0.1646 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0698 | -27.2744 | -0.4402 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0854 | -75.0528 | -0.7222 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0667 | 7.7301 | -0.5785 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0588 | -6.3557 | -0.1646 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0736 | -27.0328 | -0.4355 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0955 | -73.8252 | -0.7033 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0333 | 3.4880 | -0.1353 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0155 | 1.0801 | -0.0159 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0000 | -3.8007 | -0.1246 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0151 | -31.4034 | -0.2580 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 30 | 37.1250 | 0.0333 | 3.4880 | -0.1353 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 258 | 101.2500 | 0.0155 | 1.0801 | -0.0159 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 17 | 30.5000 | 0.0000 | -3.8007 | -0.1246 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 00_none | 199 | 129.7500 | 0.0151 | -31.4034 | -0.2580 |

## Strongest Factor Buckets

| exit_profile_source | ttl_sec | fill_model | factor | factor_bin | n | exposure | fill_rate | weighted_mean_delta_vs_taker_bps | weighted_mean_selection_adjusted_delta_bps | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q5 | 101 | 60.7500 | 0.0495 | 0.1612 | 0.1481 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q5 | 101 | 63.1250 | 0.0396 | 0.1291 | 0.1243 | 1.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q5 | 101 | 63.1250 | 0.0396 | 0.1291 | 0.1243 | 1.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q5 | 101 | 57.7500 | 0.0099 | 0.1195 | 0.1339 | 1.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q4 | 101 | 60.2500 | 0.0396 | 0.1330 | 0.1061 | 1.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q4 | 101 | 64.0000 | 0.0198 | 0.0902 | 0.0890 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q1 | 101 | 57.3750 | 0.0198 | 0.0580 | 0.0794 | 1.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q4 | 101 | 66.1250 | 0.0198 | 0.0162 | 0.0351 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q5 | 101 | 64.7500 | 0.0198 | 0.0572 | 0.0341 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q2 | 101 | 61.8750 | 0.0099 | 0.0791 | 0.0198 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q5 | 101 | 67.1250 | 0.0099 | 0.0000 | 0.0061 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q4 | 101 | 61.5000 | 0.0099 | 0.0203 | 0.0041 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q3 | 100 | 58.0000 | 0.0400 | 0.0523 | 0.0000 | 1.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q3 | 100 | 57.8750 | 0.0000 | -0.0030 | -0.0030 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q3 | 100 | 57.8750 | 0.0000 | -0.0030 | -0.0030 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q3 | 100 | 55.3750 | 0.0000 | -0.0032 | -0.0032 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q1 | 101 | 63.5000 | 0.0297 | -0.0122 | -0.0083 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q4 | 101 | 62.7500 | 0.0000 | -0.0130 | -0.0130 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q2 | 101 | 67.0000 | 0.0099 | -0.0003 | -0.0153 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q4 | 101 | 60.0000 | 0.0297 | -0.0121 | -0.0301 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q4 | 101 | 60.0000 | 0.0297 | -0.0121 | -0.0301 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q4 | 101 | 59.6250 | 0.0198 | -0.0353 | -0.0452 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q3 | 100 | 59.1250 | 0.0000 | -0.0485 | -0.0485 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q3 | 100 | 59.3750 | 0.0200 | -0.0553 | -0.0815 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q2 | 101 | 55.5000 | 0.0198 | -0.1280 | -0.1059 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q1 | 101 | 65.3750 | 0.0000 | -0.0928 | -0.0928 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q3 | 100 | 59.0000 | 0.0100 | -0.0465 | -0.1086 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q2 | 101 | 56.5000 | 0.0099 | -0.0938 | -0.1283 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q1 | 101 | 63.3750 | 0.0297 | -0.1380 | -0.1188 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q1 | 101 | 66.2500 | 0.0099 | -0.0621 | -0.1174 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q3 | 100 | 61.1250 | 0.0000 | -0.1305 | -0.1305 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q2 | 101 | 59.3750 | 0.0099 | -0.0858 | -0.1475 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q2 | 101 | 59.3750 | 0.0099 | -0.0858 | -0.1475 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q2 | 101 | 60.1250 | 0.0198 | -0.1474 | -0.1488 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q4 | 101 | 60.5000 | 0.0198 | -0.1446 | -0.1543 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q3 | 100 | 56.6250 | 0.0200 | -0.1228 | -0.1727 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q2 | 101 | 53.7500 | 0.0198 | -0.1574 | -0.1864 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q5 | 101 | 61.6250 | 0.0099 | -0.1083 | -0.1678 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q1 | 101 | 64.6250 | 0.0099 | -0.1701 | -0.1640 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q1 | 101 | 60.8750 | 0.0297 | -0.1564 | -0.1897 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q5 | 101 | 53.3750 | 0.0000 | -0.3020 | -0.3020 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q1 | 101 | 63.6250 | 0.0000 | -0.3186 | -0.3186 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q1 | 101 | 63.6250 | 0.0000 | -0.3186 | -0.3186 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q2 | 101 | 59.1250 | 0.0099 | -0.2852 | -0.3472 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q5 | 101 | 64.0000 | 0.0099 | -0.4571 | -0.5144 | 0.0000 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | recent_mid_alpha_5s_bps | q5 | 101 | 60.7500 | 0.0495 | 0.1612 | 0.1481 | 0.6667 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | same_flow_imbalance_5s | q5 | 101 | 63.1250 | 0.0396 | 0.1291 | 0.1243 | 1.0000 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | same_minus_opposite_qty_5s | q5 | 101 | 63.1250 | 0.0396 | 0.1291 | 0.1243 | 1.0000 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | signed_top_depth_imbalance | q5 | 101 | 57.7500 | 0.0099 | 0.1195 | 0.1339 | 1.0000 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | path_h_bps | q4 | 101 | 60.2500 | 0.0396 | 0.1330 | 0.1061 | 1.0000 |

## Interpretation Rule

A maker-first exit is not promoted by spread saving alone. A bucket is interesting only when it has enough sample, stable positive days, and positive selection-adjusted value under the queue-ahead proxy. If only the touch proxy works while the queue proxy fails, the result is a fill-optimism warning, not a strategy.

The next implementation step is `maker_first_exit_v1` only if these tables show a simple runtime-safe gate where queue-aware expected value remains positive after decay and selection.

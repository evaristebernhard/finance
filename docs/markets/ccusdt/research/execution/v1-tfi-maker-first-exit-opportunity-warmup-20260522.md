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
- Dates: `2026-05-05..2026-05-18`
- Candidate profiles: `fixed30_livecoherent, fixed45_livecoherent, fixed60_taker, stopping_rule_v1`
- Candidate exits with actual exposure: `9856`
- Panel rows: `29568`
- Output directory: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_opportunity_q70_idle01_g1_20260505_18_20260522`

## Readout

- Global queue-ahead maker-first is not promoted: best whole-profile row is `fixed45_livecoherent / TTL=1.0s`, weighted delta `-57.7696` bp-units, mean `-0.0399` bps, positive-day fraction `0.3571`.
- Positive whole-profile queue rows: `0` out of `12`. The full-sample controller should therefore remain direct taker unless a narrow runtime-safe gate is used.
- Strongest queue-aware factor bucket is `fixed45_livecoherent / TTL=5.0s / path_d_bps=q1`, n `493`, exposure `280.7500`, fill rate `0.0629`, delta sum `30.9445`, selection-adjusted sum `35.6966`, positive-day fraction `1.0000`.
- This is a diagnostic bucket read, not a live rule: factor thresholds must be re-expressed as prior-date/runtime-safe gates before `maker_first_exit_v1` can be enabled.

## TTL Summary

| exit_profile_source | ttl_sec | fill_model | n | exposure | fill_rate | weighted_mean_spread_term_bps | weighted_mean_unfilled_decay_term_bps | weighted_mean_selection_term_bps | weighted_mean_delta_vs_taker_bps | weighted_sum_delta_vs_taker_bps | positive_day_frac | min_day_delta_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 2464 | 1494.5000 | 0.0276 | 0.0520 | 0.1635 | 0.1150 | -0.1116 | -166.7262 | 0.1429 | -42.8176 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 2464 | 1494.5000 | 0.0288 | 0.0546 | 0.1654 | 0.1170 | -0.1109 | -165.6959 | 0.1429 | -42.8176 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 2464 | 1494.5000 | 0.0459 | 0.0826 | 0.2312 | 0.1790 | -0.1486 | -222.0228 | 0.1429 | -60.5055 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 2464 | 1494.5000 | 0.0483 | 0.0884 | 0.2379 | 0.1805 | -0.1495 | -223.3877 | 0.1429 | -60.1056 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 2464 | 1494.5000 | 0.0901 | 0.1654 | 0.4596 | 0.2820 | -0.2941 | -439.5827 | 0.1429 | -102.8423 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 2464 | 1494.5000 | 0.0978 | 0.1877 | 0.4859 | 0.2909 | -0.2982 | -445.6596 | 0.1429 | -101.8824 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 2464 | 1446.8750 | 0.0268 | 0.0529 | 0.0928 | 0.0834 | -0.0399 | -57.7696 | 0.3571 | -35.7696 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 2464 | 1446.8750 | 0.0284 | 0.0557 | 0.0945 | 0.0837 | -0.0388 | -56.1654 | 0.3571 | -35.7696 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 2464 | 1446.8750 | 0.0463 | 0.0916 | 0.1852 | 0.1138 | -0.0936 | -135.3956 | 0.5714 | -73.4153 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 2464 | 1446.8750 | 0.0487 | 0.0981 | 0.2023 | 0.1255 | -0.1041 | -150.6833 | 0.5714 | -73.4153 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 2464 | 1446.8750 | 0.0925 | 0.1849 | 0.3887 | 0.2850 | -0.2038 | -294.9448 | 0.3571 | -130.4637 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 2464 | 1446.8750 | 0.1006 | 0.2033 | 0.4092 | 0.2892 | -0.2059 | -297.8729 | 0.3571 | -130.0824 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 2464 | 1450.6250 | 0.0207 | 0.0349 | 0.1121 | 0.0338 | -0.0771 | -111.8848 | 0.1429 | -21.2333 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 2464 | 1450.6250 | 0.0244 | 0.0454 | 0.1174 | 0.0198 | -0.0720 | -104.4110 | 0.2143 | -16.5575 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 2464 | 1450.6250 | 0.0377 | 0.0642 | 0.2710 | 0.0674 | -0.2068 | -299.9582 | 0.1429 | -84.1804 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 2464 | 1450.6250 | 0.0426 | 0.0776 | 0.2705 | 0.0569 | -0.1929 | -279.8368 | 0.1429 | -81.6682 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 2464 | 1450.6250 | 0.0893 | 0.1693 | 0.4305 | 0.1885 | -0.2613 | -379.0438 | 0.1429 | -79.0240 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 2464 | 1450.6250 | 0.0982 | 0.1963 | 0.4415 | 0.1794 | -0.2453 | -355.7920 | 0.2143 | -70.9276 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 2464 | 1450.6250 | 0.0199 | 0.0334 | 0.1101 | 0.0328 | -0.0767 | -111.2285 | 0.1429 | -21.2333 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 2464 | 1450.6250 | 0.0235 | 0.0438 | 0.1154 | 0.0187 | -0.0715 | -103.7547 | 0.2143 | -16.5575 |
| stopping_rule_v1 | 2.0000 | queue_trade_proxy_v1 | 2464 | 1450.6250 | 0.0369 | 0.0634 | 0.2648 | 0.0654 | -0.2014 | -292.1582 | 0.1429 | -84.1804 |
| stopping_rule_v1 | 2.0000 | touch_trade_proxy_v1 | 2464 | 1450.6250 | 0.0418 | 0.0768 | 0.2644 | 0.0550 | -0.1875 | -272.0369 | 0.1429 | -81.6682 |
| stopping_rule_v1 | 5.0000 | queue_trade_proxy_v1 | 2464 | 1450.6250 | 0.0893 | 0.1701 | 0.4222 | 0.1885 | -0.2520 | -365.6155 | 0.1429 | -79.0240 |
| stopping_rule_v1 | 5.0000 | touch_trade_proxy_v1 | 2464 | 1450.6250 | 0.0982 | 0.1972 | 0.4332 | 0.1794 | -0.2360 | -342.3638 | 0.2143 | -70.9276 |

## Day Stability

| exit_profile_source | date | ttl_sec | fill_model | n | exposure | fill_rate | weighted_sum_delta_vs_taker_bps | weighted_mean_delta_vs_taker_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-05 | 1.0000 | queue_trade_proxy_v1 | 243 | 131.2500 | 0.0288 | -1.0200 | -0.0078 |
| fixed30_livecoherent | 2026-05-06 | 1.0000 | queue_trade_proxy_v1 | 143 | 81.2500 | 0.0000 | -3.2695 | -0.0402 |
| fixed30_livecoherent | 2026-05-07 | 1.0000 | queue_trade_proxy_v1 | 54 | 33.3750 | 0.0000 | 0.0000 | 0.0000 |
| fixed30_livecoherent | 2026-05-08 | 1.0000 | queue_trade_proxy_v1 | 68 | 43.7500 | 0.0294 | 2.1245 | 0.0486 |
| fixed30_livecoherent | 2026-05-09 | 1.0000 | queue_trade_proxy_v1 | 199 | 129.1250 | 0.0352 | -23.3326 | -0.1807 |
| fixed30_livecoherent | 2026-05-10 | 1.0000 | queue_trade_proxy_v1 | 177 | 100.3750 | 0.0226 | -2.3029 | -0.0229 |
| fixed30_livecoherent | 2026-05-11 | 1.0000 | queue_trade_proxy_v1 | 233 | 130.5000 | 0.0258 | -30.1377 | -0.2309 |
| fixed30_livecoherent | 2026-05-12 | 1.0000 | queue_trade_proxy_v1 | 169 | 118.5000 | 0.0355 | -19.3334 | -0.1632 |
| fixed30_livecoherent | 2026-05-13 | 1.0000 | queue_trade_proxy_v1 | 169 | 109.7500 | 0.0237 | -42.8176 | -0.3901 |
| fixed30_livecoherent | 2026-05-14 | 1.0000 | queue_trade_proxy_v1 | 278 | 172.8750 | 0.0360 | -13.5485 | -0.0784 |
| fixed30_livecoherent | 2026-05-15 | 1.0000 | queue_trade_proxy_v1 | 227 | 139.7500 | 0.0617 | -14.9767 | -0.1072 |
| fixed30_livecoherent | 2026-05-16 | 1.0000 | queue_trade_proxy_v1 | 149 | 91.7500 | 0.0067 | -20.3088 | -0.2213 |
| fixed30_livecoherent | 2026-05-17 | 1.0000 | queue_trade_proxy_v1 | 143 | 83.8750 | 0.0070 | 3.7348 | 0.0445 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | queue_trade_proxy_v1 | 212 | 128.3750 | 0.0283 | -1.5379 | -0.0120 |
| fixed30_livecoherent | 2026-05-05 | 1.0000 | touch_trade_proxy_v1 | 243 | 131.2500 | 0.0288 | -1.0200 | -0.0078 |
| fixed30_livecoherent | 2026-05-06 | 1.0000 | touch_trade_proxy_v1 | 143 | 81.2500 | 0.0000 | -3.2695 | -0.0402 |
| fixed30_livecoherent | 2026-05-07 | 1.0000 | touch_trade_proxy_v1 | 54 | 33.3750 | 0.0000 | 0.0000 | 0.0000 |
| fixed30_livecoherent | 2026-05-08 | 1.0000 | touch_trade_proxy_v1 | 68 | 43.7500 | 0.0294 | 2.1245 | 0.0486 |
| fixed30_livecoherent | 2026-05-09 | 1.0000 | touch_trade_proxy_v1 | 199 | 129.1250 | 0.0402 | -22.9327 | -0.1776 |
| fixed30_livecoherent | 2026-05-10 | 1.0000 | touch_trade_proxy_v1 | 177 | 100.3750 | 0.0282 | -2.0645 | -0.0206 |
| fixed30_livecoherent | 2026-05-11 | 1.0000 | touch_trade_proxy_v1 | 233 | 130.5000 | 0.0300 | -29.7456 | -0.2279 |
| fixed30_livecoherent | 2026-05-12 | 1.0000 | touch_trade_proxy_v1 | 169 | 118.5000 | 0.0355 | -19.3334 | -0.1632 |
| fixed30_livecoherent | 2026-05-13 | 1.0000 | touch_trade_proxy_v1 | 169 | 109.7500 | 0.0237 | -42.8176 | -0.3901 |
| fixed30_livecoherent | 2026-05-14 | 1.0000 | touch_trade_proxy_v1 | 278 | 172.8750 | 0.0360 | -13.5485 | -0.0784 |
| fixed30_livecoherent | 2026-05-15 | 1.0000 | touch_trade_proxy_v1 | 227 | 139.7500 | 0.0617 | -14.9767 | -0.1072 |
| fixed30_livecoherent | 2026-05-16 | 1.0000 | touch_trade_proxy_v1 | 149 | 91.7500 | 0.0067 | -20.3088 | -0.2213 |
| fixed30_livecoherent | 2026-05-17 | 1.0000 | touch_trade_proxy_v1 | 143 | 83.8750 | 0.0070 | 3.7348 | 0.0445 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | touch_trade_proxy_v1 | 212 | 128.3750 | 0.0283 | -1.5379 | -0.0120 |
| fixed30_livecoherent | 2026-05-05 | 2.0000 | queue_trade_proxy_v1 | 243 | 131.2500 | 0.0370 | -0.6089 | -0.0046 |
| fixed30_livecoherent | 2026-05-06 | 2.0000 | queue_trade_proxy_v1 | 143 | 81.2500 | 0.0210 | -2.6704 | -0.0329 |
| fixed30_livecoherent | 2026-05-07 | 2.0000 | queue_trade_proxy_v1 | 54 | 33.3750 | 0.0000 | 0.0000 | 0.0000 |
| fixed30_livecoherent | 2026-05-08 | 2.0000 | queue_trade_proxy_v1 | 68 | 43.7500 | 0.0294 | -5.0883 | -0.1163 |
| fixed30_livecoherent | 2026-05-09 | 2.0000 | queue_trade_proxy_v1 | 199 | 129.1250 | 0.0503 | -60.5055 | -0.4686 |
| fixed30_livecoherent | 2026-05-10 | 2.0000 | queue_trade_proxy_v1 | 177 | 100.3750 | 0.0339 | 36.7954 | 0.3666 |
| fixed30_livecoherent | 2026-05-11 | 2.0000 | queue_trade_proxy_v1 | 233 | 130.5000 | 0.0386 | -40.2833 | -0.3087 |
| fixed30_livecoherent | 2026-05-12 | 2.0000 | queue_trade_proxy_v1 | 169 | 118.5000 | 0.0473 | -17.7260 | -0.1496 |
| fixed30_livecoherent | 2026-05-13 | 2.0000 | queue_trade_proxy_v1 | 169 | 109.7500 | 0.0473 | -48.7762 | -0.4444 |
| fixed30_livecoherent | 2026-05-14 | 2.0000 | queue_trade_proxy_v1 | 278 | 172.8750 | 0.0612 | -30.4055 | -0.1759 |
| fixed30_livecoherent | 2026-05-15 | 2.0000 | queue_trade_proxy_v1 | 227 | 139.7500 | 0.0749 | -28.3018 | -0.2025 |
| fixed30_livecoherent | 2026-05-16 | 2.0000 | queue_trade_proxy_v1 | 149 | 91.7500 | 0.0537 | -24.9920 | -0.2724 |
| fixed30_livecoherent | 2026-05-17 | 2.0000 | queue_trade_proxy_v1 | 143 | 83.8750 | 0.0350 | -0.3908 | -0.0047 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | queue_trade_proxy_v1 | 212 | 128.3750 | 0.0519 | 0.9305 | 0.0072 |
| fixed30_livecoherent | 2026-05-05 | 2.0000 | touch_trade_proxy_v1 | 243 | 131.2500 | 0.0370 | -0.6089 | -0.0046 |
| fixed30_livecoherent | 2026-05-06 | 2.0000 | touch_trade_proxy_v1 | 143 | 81.2500 | 0.0210 | -2.6704 | -0.0329 |
| fixed30_livecoherent | 2026-05-07 | 2.0000 | touch_trade_proxy_v1 | 54 | 33.3750 | 0.0000 | 0.0000 | 0.0000 |
| fixed30_livecoherent | 2026-05-08 | 2.0000 | touch_trade_proxy_v1 | 68 | 43.7500 | 0.0294 | -5.0883 | -0.1163 |
| fixed30_livecoherent | 2026-05-09 | 2.0000 | touch_trade_proxy_v1 | 199 | 129.1250 | 0.0553 | -60.1056 | -0.4655 |
| fixed30_livecoherent | 2026-05-10 | 2.0000 | touch_trade_proxy_v1 | 177 | 100.3750 | 0.0452 | 37.7555 | 0.3761 |
| fixed30_livecoherent | 2026-05-11 | 2.0000 | touch_trade_proxy_v1 | 233 | 130.5000 | 0.0472 | -43.4160 | -0.3327 |
| fixed30_livecoherent | 2026-05-12 | 2.0000 | touch_trade_proxy_v1 | 169 | 118.5000 | 0.0473 | -17.7260 | -0.1496 |
| fixed30_livecoherent | 2026-05-13 | 2.0000 | touch_trade_proxy_v1 | 169 | 109.7500 | 0.0533 | -48.3683 | -0.4407 |
| fixed30_livecoherent | 2026-05-14 | 2.0000 | touch_trade_proxy_v1 | 278 | 172.8750 | 0.0612 | -30.4055 | -0.1759 |
| fixed30_livecoherent | 2026-05-15 | 2.0000 | touch_trade_proxy_v1 | 227 | 139.7500 | 0.0749 | -28.3018 | -0.2025 |
| fixed30_livecoherent | 2026-05-16 | 2.0000 | touch_trade_proxy_v1 | 149 | 91.7500 | 0.0537 | -24.9920 | -0.2724 |
| fixed30_livecoherent | 2026-05-17 | 2.0000 | touch_trade_proxy_v1 | 143 | 83.8750 | 0.0350 | -0.3908 | -0.0047 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | touch_trade_proxy_v1 | 212 | 128.3750 | 0.0519 | 0.9305 | 0.0072 |
| fixed30_livecoherent | 2026-05-05 | 5.0000 | queue_trade_proxy_v1 | 243 | 131.2500 | 0.0700 | -16.2452 | -0.1238 |
| fixed30_livecoherent | 2026-05-06 | 5.0000 | queue_trade_proxy_v1 | 143 | 81.2500 | 0.0490 | -7.2086 | -0.0887 |
| fixed30_livecoherent | 2026-05-07 | 5.0000 | queue_trade_proxy_v1 | 54 | 33.3750 | 0.0370 | 1.8750 | 0.0562 |
| fixed30_livecoherent | 2026-05-08 | 5.0000 | queue_trade_proxy_v1 | 68 | 43.7500 | 0.0588 | -6.3402 | -0.1449 |
| fixed30_livecoherent | 2026-05-09 | 5.0000 | queue_trade_proxy_v1 | 199 | 129.1250 | 0.0854 | -102.8423 | -0.7965 |
| fixed30_livecoherent | 2026-05-10 | 5.0000 | queue_trade_proxy_v1 | 177 | 100.3750 | 0.0960 | 29.6873 | 0.2958 |
| fixed30_livecoherent | 2026-05-11 | 5.0000 | queue_trade_proxy_v1 | 233 | 130.5000 | 0.0901 | -50.4950 | -0.3869 |
| fixed30_livecoherent | 2026-05-12 | 5.0000 | queue_trade_proxy_v1 | 169 | 118.5000 | 0.1124 | -9.5478 | -0.0806 |
| fixed30_livecoherent | 2026-05-13 | 5.0000 | queue_trade_proxy_v1 | 169 | 109.7500 | 0.0710 | -29.4144 | -0.2680 |
| fixed30_livecoherent | 2026-05-14 | 5.0000 | queue_trade_proxy_v1 | 278 | 172.8750 | 0.1295 | -77.0487 | -0.4457 |
| fixed30_livecoherent | 2026-05-15 | 5.0000 | queue_trade_proxy_v1 | 227 | 139.7500 | 0.1189 | -76.7093 | -0.5489 |
| fixed30_livecoherent | 2026-05-16 | 5.0000 | queue_trade_proxy_v1 | 149 | 91.7500 | 0.0940 | -47.7117 | -0.5200 |
| fixed30_livecoherent | 2026-05-17 | 5.0000 | queue_trade_proxy_v1 | 143 | 83.8750 | 0.0979 | -46.9937 | -0.5603 |
| fixed30_livecoherent | 2026-05-18 | 5.0000 | queue_trade_proxy_v1 | 212 | 128.3750 | 0.0708 | -0.5880 | -0.0046 |
| fixed30_livecoherent | 2026-05-05 | 5.0000 | touch_trade_proxy_v1 | 243 | 131.2500 | 0.0741 | -15.8277 | -0.1206 |
| fixed30_livecoherent | 2026-05-06 | 5.0000 | touch_trade_proxy_v1 | 143 | 81.2500 | 0.0490 | -7.2086 | -0.0887 |
| fixed30_livecoherent | 2026-05-07 | 5.0000 | touch_trade_proxy_v1 | 54 | 33.3750 | 0.0370 | 1.8750 | 0.0562 |
| fixed30_livecoherent | 2026-05-08 | 5.0000 | touch_trade_proxy_v1 | 68 | 43.7500 | 0.0588 | -6.3402 | -0.1449 |
| fixed30_livecoherent | 2026-05-09 | 5.0000 | touch_trade_proxy_v1 | 199 | 129.1250 | 0.0955 | -101.8824 | -0.7890 |
| fixed30_livecoherent | 2026-05-10 | 5.0000 | touch_trade_proxy_v1 | 177 | 100.3750 | 0.1130 | 30.4090 | 0.3030 |
| fixed30_livecoherent | 2026-05-11 | 5.0000 | touch_trade_proxy_v1 | 233 | 130.5000 | 0.1073 | -52.2538 | -0.4004 |
| fixed30_livecoherent | 2026-05-12 | 5.0000 | touch_trade_proxy_v1 | 169 | 118.5000 | 0.1124 | -9.5478 | -0.0806 |
| fixed30_livecoherent | 2026-05-13 | 5.0000 | touch_trade_proxy_v1 | 169 | 109.7500 | 0.0769 | -29.0065 | -0.2643 |
| fixed30_livecoherent | 2026-05-14 | 5.0000 | touch_trade_proxy_v1 | 278 | 172.8750 | 0.1403 | -79.4485 | -0.4596 |

## Cell Readout

| exit_profile_source | ttl_sec | fill_model | cell | n | exposure | fill_rate | weighted_sum_delta_vs_taker_bps | weighted_mean_selection_adjusted_delta_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 136 | 167.6250 | 0.0221 | 7.0954 | -0.0621 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 1195 | 466.1250 | 0.0293 | -39.7691 | -0.2736 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 123 | 201.5000 | 0.0000 | -46.8655 | -0.2326 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | 00_none | 1010 | 659.2500 | 0.0297 | -87.1869 | -0.2334 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 136 | 167.6250 | 0.0221 | 7.0954 | -0.0621 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 1195 | 466.1250 | 0.0301 | -39.5307 | -0.2726 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 123 | 201.5000 | 0.0000 | -46.8655 | -0.2326 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | 00_none | 1010 | 659.2500 | 0.0317 | -86.3951 | -0.2369 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 11_r5_frames | 136 | 167.6250 | 0.0441 | 9.8649 | -0.3144 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 01_frames_only | 123 | 201.5000 | 0.0000 | -60.4767 | -0.3001 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 00_none | 1010 | 659.2500 | 0.0396 | -85.3703 | -0.2569 |
| fixed30_livecoherent | 2.0000 | queue_trade_proxy_v1 | 10_r5_only | 1195 | 466.1250 | 0.0561 | -86.0408 | -0.4440 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 11_r5_frames | 136 | 167.6250 | 0.0441 | 9.8649 | -0.3144 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 01_frames_only | 123 | 201.5000 | 0.0000 | -60.4767 | -0.3001 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 10_r5_only | 1195 | 466.1250 | 0.0577 | -85.0807 | -0.4409 |
| fixed30_livecoherent | 2.0000 | touch_trade_proxy_v1 | 00_none | 1010 | 659.2500 | 0.0436 | -87.6953 | -0.2646 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 11_r5_frames | 136 | 167.6250 | 0.1176 | 23.7755 | -0.3217 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 01_frames_only | 123 | 201.5000 | 0.0244 | -92.1995 | -0.5437 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 10_r5_only | 1195 | 466.1250 | 0.0979 | -119.9730 | -0.6131 |
| fixed30_livecoherent | 5.0000 | queue_trade_proxy_v1 | 00_none | 1010 | 659.2500 | 0.0851 | -251.1857 | -0.6246 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 11_r5_frames | 136 | 167.6250 | 0.1250 | 24.0182 | -0.3188 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 01_frames_only | 123 | 201.5000 | 0.0407 | -96.8497 | -0.5899 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 10_r5_only | 1195 | 466.1250 | 0.1038 | -119.2891 | -0.6214 |
| fixed30_livecoherent | 5.0000 | touch_trade_proxy_v1 | 00_none | 1010 | 659.2500 | 0.0941 | -253.5390 | -0.6348 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 102 | 156.3750 | 0.0392 | 22.4393 | 0.1145 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 1320 | 516.3750 | 0.0288 | 5.6460 | -0.0966 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 157 | 197.2500 | 0.0446 | -24.0660 | -0.3554 |
| fixed45_livecoherent | 1.0000 | queue_trade_proxy_v1 | 00_none | 885 | 576.8750 | 0.0192 | -61.7890 | -0.1324 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 102 | 156.3750 | 0.0392 | 22.4393 | 0.1145 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 1320 | 516.3750 | 0.0303 | 6.1278 | -0.0947 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 157 | 197.2500 | 0.0446 | -24.0660 | -0.3554 |
| fixed45_livecoherent | 1.0000 | touch_trade_proxy_v1 | 00_none | 885 | 576.8750 | 0.0215 | -60.6665 | -0.1319 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 01_frames_only | 102 | 156.3750 | 0.0392 | 1.9978 | -0.0162 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 10_r5_only | 1320 | 516.3750 | 0.0523 | -19.3228 | -0.2130 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 11_r5_frames | 157 | 197.2500 | 0.0573 | -33.2112 | -0.3286 |
| fixed45_livecoherent | 2.0000 | queue_trade_proxy_v1 | 00_none | 885 | 576.8750 | 0.0362 | -84.8594 | -0.2128 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 01_frames_only | 102 | 156.3750 | 0.0392 | 1.9978 | -0.0162 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 10_r5_only | 1320 | 516.3750 | 0.0538 | -18.6103 | -0.2125 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 11_r5_frames | 157 | 197.2500 | 0.0573 | -33.2112 | -0.3286 |
| fixed45_livecoherent | 2.0000 | touch_trade_proxy_v1 | 00_none | 885 | 576.8750 | 0.0407 | -100.8596 | -0.2690 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 01_frames_only | 102 | 156.3750 | 0.0980 | -31.0014 | -0.3601 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 11_r5_frames | 157 | 197.2500 | 0.1019 | -53.6562 | -0.6920 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 10_r5_only | 1320 | 516.3750 | 0.0932 | -99.8933 | -0.4610 |
| fixed45_livecoherent | 5.0000 | queue_trade_proxy_v1 | 00_none | 885 | 576.8750 | 0.0893 | -110.3939 | -0.4792 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 01_frames_only | 102 | 156.3750 | 0.0980 | -31.0014 | -0.3601 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 11_r5_frames | 157 | 197.2500 | 0.1083 | -52.4740 | -0.6801 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 10_r5_only | 1320 | 516.3750 | 0.1023 | -93.6867 | -0.4430 |
| fixed45_livecoherent | 5.0000 | touch_trade_proxy_v1 | 00_none | 885 | 576.8750 | 0.0972 | -120.7107 | -0.5150 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.0237 | -4.8541 | -0.0592 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.0192 | -19.1960 | -0.1229 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0065 | -39.0313 | -0.2566 |
| fixed60_taker | 1.0000 | queue_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0190 | -48.8034 | -0.1065 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.0268 | -4.8367 | -0.0592 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.0192 | -19.1960 | -0.1229 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0194 | -37.8658 | -0.2441 |
| fixed60_taker | 1.0000 | touch_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0223 | -42.5125 | -0.0628 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.0192 | -17.0065 | -0.1101 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.0420 | -45.8023 | -0.1936 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0368 | -106.3622 | -0.2414 |
| fixed60_taker | 2.0000 | queue_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0194 | -130.7872 | -0.7509 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.0192 | -17.0065 | -0.1101 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.0451 | -47.4496 | -0.2090 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0424 | -86.0100 | -0.1722 |
| fixed60_taker | 2.0000 | touch_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0387 | -129.3708 | -0.7356 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.0962 | 15.1618 | -0.1731 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0774 | -55.1515 | -0.4129 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.0971 | -79.9074 | -0.3840 |
| fixed60_taker | 5.0000 | queue_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0792 | -259.1466 | -0.6005 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.1154 | 17.1265 | -0.1501 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0968 | -55.1277 | -0.4051 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.1024 | -92.6955 | -0.4335 |
| fixed60_taker | 5.0000 | touch_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0903 | -225.0954 | -0.5036 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.0222 | -3.6659 | -0.0540 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.0192 | -19.1960 | -0.1229 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0065 | -37.1255 | -0.2464 |
| stopping_rule_v1 | 1.0000 | queue_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0190 | -51.2411 | -0.1106 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 10_r5_only | 1308 | 511.8750 | 0.0252 | -3.6484 | -0.0539 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 01_frames_only | 104 | 170.8750 | 0.0192 | -19.1960 | -0.1229 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 11_r5_frames | 155 | 185.2500 | 0.0194 | -35.9600 | -0.2338 |
| stopping_rule_v1 | 1.0000 | touch_trade_proxy_v1 | 00_none | 897 | 582.6250 | 0.0223 | -44.9503 | -0.0670 |

## Strongest Factor Buckets

| exit_profile_source | ttl_sec | fill_model | factor | factor_bin | n | exposure | fill_rate | weighted_mean_delta_vs_taker_bps | weighted_mean_selection_adjusted_delta_bps | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q2 | 493 | 304.5000 | 0.0101 | -0.0022 | -0.0096 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q2 | 493 | 304.5000 | 0.0101 | -0.0022 | -0.0096 | 0.3333 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q2 | 493 | 300.7500 | 0.0142 | 0.0263 | -0.0207 | 0.6667 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q5 | 493 | 307.6250 | 0.0101 | -0.0163 | -0.0230 | 0.2857 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q4 | 493 | 284.8750 | 0.0203 | 0.0227 | -0.0335 | 0.4286 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q2 | 493 | 299.5000 | 0.0203 | -0.0728 | -0.0546 | 0.4286 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q1 | 493 | 299.7500 | 0.0183 | -0.0006 | -0.0589 | 0.4000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q5 | 493 | 303.7500 | 0.0223 | -0.0279 | -0.0634 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q4 | 493 | 321.8750 | 0.0345 | -0.0285 | -0.0679 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q4 | 493 | 294.0000 | 0.0183 | -0.0639 | -0.0773 | 0.4286 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q4 | 493 | 297.3750 | 0.0406 | 0.0050 | -0.0795 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q3 | 492 | 308.8750 | 0.0183 | -0.0528 | -0.0806 | 0.4286 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q1 | 493 | 276.8750 | 0.0203 | -0.0378 | -0.0920 | 0.3571 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q2 | 493 | 310.5000 | 0.0284 | -0.0513 | -0.0836 | 0.2500 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q5 | 493 | 292.8750 | 0.0304 | 0.0290 | -0.0916 | 0.6429 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q3 | 492 | 302.3750 | 0.0163 | -0.0720 | -0.0945 | 0.2500 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q3 | 492 | 302.3750 | 0.0163 | -0.0720 | -0.0945 | 0.2500 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q4 | 493 | 308.1250 | 0.0162 | -0.0701 | -0.0969 | 0.2000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q4 | 493 | 308.1250 | 0.0162 | -0.0701 | -0.0969 | 0.2000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q2 | 493 | 298.7500 | 0.0162 | -0.1082 | -0.1137 | 0.2857 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q4 | 493 | 304.3750 | 0.0203 | -0.0945 | -0.1271 | 0.0000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q3 | 492 | 301.3750 | 0.0183 | -0.0532 | -0.1369 | 0.4286 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q5 | 493 | 295.3750 | 0.0061 | -0.1050 | -0.1475 | 0.5714 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q3 | 492 | 302.3750 | 0.0183 | -0.1484 | -0.1628 | 0.2143 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q3 | 492 | 300.7500 | 0.0285 | -0.1264 | -0.1747 | 0.4286 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q1 | 493 | 288.8750 | 0.0304 | -0.0930 | -0.1913 | 0.2143 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q3 | 492 | 309.1250 | 0.0325 | -0.1574 | -0.2087 | 0.2000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q1 | 493 | 311.0000 | 0.0162 | -0.1170 | -0.2079 | 0.4286 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q2 | 493 | 297.0000 | 0.0284 | -0.1865 | -0.2468 | 0.3571 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q3 | 492 | 306.1250 | 0.0203 | -0.1228 | -0.2649 | 0.2000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q3 | 492 | 295.7500 | 0.0325 | -0.1758 | -0.2828 | 0.2857 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q1 | 493 | 278.1250 | 0.0162 | -0.2754 | -0.3079 | 0.2143 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q1 | 493 | 278.1250 | 0.0162 | -0.2754 | -0.3079 | 0.2143 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q4 | 493 | 304.0000 | 0.0264 | -0.0441 | -0.2922 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q2 | 493 | 291.0000 | 0.0284 | -0.2023 | -0.3070 | 0.2857 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | exit_spread_bps | q2 | 493 | 302.1250 | 0.0264 | -0.2185 | -0.3035 | 0.2143 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q5 | 493 | 293.5000 | 0.0609 | -0.2235 | -0.3581 | 0.2857 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | signed_top_depth_imbalance | q4 | 493 | 298.8750 | 0.0345 | -0.1403 | -0.3523 | 0.2143 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | recent_mid_alpha_5s_bps | q1 | 493 | 289.7500 | 0.0223 | -0.1473 | -0.3713 | 0.2857 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | maker_queue_ahead_qty | q1 | 493 | 302.3750 | 0.0446 | -0.1221 | -0.4926 | 0.3571 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_flow_imbalance_5s | q5 | 493 | 301.3750 | 0.0791 | -0.1529 | -0.6360 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | same_minus_opposite_qty_5s | q5 | 493 | 301.3750 | 0.0791 | -0.1529 | -0.6360 | 0.5000 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_d_bps | q5 | 493 | 290.2500 | 0.0385 | -0.3736 | -0.7615 | 0.2143 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | path_h_bps | q5 | 493 | 294.8750 | 0.0446 | -0.3705 | -0.7926 | 0.0714 |
| fixed30_livecoherent | 1.0000 | queue_trade_proxy_v1 | decision_frames_since_mid_change | q1 | 493 | 285.2500 | 0.0751 | -0.3305 | -0.8765 | 0.2857 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | same_flow_imbalance_5s | q2 | 493 | 304.5000 | 0.0122 | -0.0009 | -0.0070 | 0.3333 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | same_minus_opposite_qty_5s | q2 | 493 | 304.5000 | 0.0122 | -0.0009 | -0.0070 | 0.3333 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | recent_mid_alpha_5s_bps | q2 | 493 | 300.7500 | 0.0162 | 0.0276 | -0.0180 | 0.6667 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | decision_frames_since_mid_change | q5 | 493 | 307.6250 | 0.0101 | -0.0163 | -0.0230 | 0.2857 |
| fixed30_livecoherent | 1.0000 | touch_trade_proxy_v1 | path_d_bps | q4 | 493 | 284.8750 | 0.0223 | 0.0241 | -0.0307 | 0.4286 |

## Interpretation Rule

A maker-first exit is not promoted by spread saving alone. A bucket is interesting only when it has enough sample, stable positive days, and positive selection-adjusted value under the queue-ahead proxy. If only the touch proxy works while the queue proxy fails, the result is a fill-optimism warning, not a strategy.

The next implementation step is `maker_first_exit_v1` only if these tables show a simple runtime-safe gate where queue-aware expected value remains positive after decay and selection.

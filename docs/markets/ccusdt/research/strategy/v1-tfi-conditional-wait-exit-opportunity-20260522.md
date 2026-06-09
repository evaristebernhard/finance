# CCUSDT q70 idle01_g1 conditional wait exit opportunity

This diagnostic removes maker execution entirely. It compares immediate taker exit with wait-then-taker exit:

\[
W_t(\tau)=Y^T_{t+\tau}-Y^T_t.
\]

Runtime-safe bucket features are measured at or before the exit decision. Post-exit flow and reclaim fields are diagnostic labels only.

## Scope

- Dates: `2026-05-05..2026-05-18`
- Exit profiles: `fixed30_livecoherent, fixed45_livecoherent, fixed60_taker, stopping_rule_v1`
- Actual exit candidates: `9856`
- Panel rows: `49280`
- TTL seconds: `[0.5, 1.0, 2.0, 5.0, 10.0]`
- Output directory: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_q70_idle01_g1_20260505_18_20260522`

## Readout

- Whole-profile wait timing is a diagnostic surface, not a strategy by itself.
- Strongest runtime-safe bucket: `fixed60_taker / TTL=10.0s / recent_mid_alpha_5s_bps=q5`, n `493`, weighted sum `360.3054`, positive-day fraction `0.7143`, worst day `-26.5990`.

## TTL Summary

| exit_profile_source | ttl_sec | n | exposure | wait_positive_rate | weighted_mean_wait_value_bps | weighted_sum_wait_value_bps | weighted_mean_delay_loss_bps | worst_wait_value_bps | cvar10_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 0.5000 | 2464 | 1494.5000 | 0.0361 | 0.0038 | 5.6214 | 0.1632 | -27.2984 | -1.7095 | 0.5000 | -23.6573 |
| fixed30_livecoherent | 1.0000 | 2464 | 1494.5000 | 0.0519 | -0.0298 | -44.4914 | 0.2300 | -36.7110 | -2.4946 | 0.4286 | -40.5565 |
| fixed30_livecoherent | 2.0000 | 2464 | 1494.5000 | 0.0755 | 0.0163 | 24.3918 | 0.3396 | -48.4791 | -3.7267 | 0.5714 | -37.3367 |
| fixed30_livecoherent | 5.0000 | 2464 | 1494.5000 | 0.1282 | 0.0175 | 26.1053 | 0.6494 | -54.5225 | -6.9565 | 0.5000 | -59.7417 |
| fixed30_livecoherent | 10.0000 | 2464 | 1494.5000 | 0.1782 | 0.1045 | 156.1575 | 1.0449 | -63.0241 | -10.1923 | 0.5714 | -63.5943 |
| fixed45_livecoherent | 0.5000 | 2464 | 1446.8750 | 0.0337 | 0.0280 | 40.4677 | 0.0973 | -34.0453 | -1.0160 | 0.4286 | -24.6025 |
| fixed45_livecoherent | 1.0000 | 2464 | 1446.8750 | 0.0487 | 0.0558 | 80.7423 | 0.1775 | -37.1795 | -1.8147 | 0.5714 | -32.0653 |
| fixed45_livecoherent | 2.0000 | 2464 | 1446.8750 | 0.0706 | 0.0124 | 17.9081 | 0.3088 | -49.9681 | -3.0520 | 0.7143 | -45.7179 |
| fixed45_livecoherent | 5.0000 | 2464 | 1446.8750 | 0.1242 | 0.1126 | 162.9725 | 0.5581 | -52.6352 | -5.6136 | 0.7143 | -100.9860 |
| fixed45_livecoherent | 10.0000 | 2464 | 1446.8750 | 0.1948 | 0.1989 | 287.8510 | 0.9898 | -51.4856 | -8.9589 | 0.6429 | -70.6255 |
| fixed60_taker | 0.5000 | 2464 | 1450.6250 | 0.0264 | -0.0378 | -54.8149 | 0.1061 | -40.2749 | -0.9813 | 0.1429 | -19.8322 |
| fixed60_taker | 1.0000 | 2464 | 1450.6250 | 0.0442 | -0.0460 | -66.6981 | 0.1851 | -21.2709 | -1.6721 | 0.2857 | -14.4528 |
| fixed60_taker | 2.0000 | 2464 | 1450.6250 | 0.0666 | -0.1196 | -173.4959 | 0.3691 | -57.5854 | -3.3819 | 0.2143 | -72.0512 |
| fixed60_taker | 5.0000 | 2464 | 1450.6250 | 0.1295 | -0.0308 | -44.6472 | 0.6145 | -54.4565 | -6.1533 | 0.4286 | -47.6733 |
| fixed60_taker | 10.0000 | 2464 | 1450.6250 | 0.1887 | 0.0284 | 41.1441 | 1.0886 | -46.0891 | -9.6584 | 0.3571 | -65.8783 |
| stopping_rule_v1 | 0.5000 | 2464 | 1450.6250 | 0.0268 | -0.0387 | -56.0930 | 0.1081 | -40.2749 | -0.9997 | 0.1429 | -19.8322 |
| stopping_rule_v1 | 1.0000 | 2464 | 1450.6250 | 0.0442 | -0.0465 | -67.5221 | 0.1851 | -21.2709 | -1.6564 | 0.2857 | -13.5332 |
| stopping_rule_v1 | 2.0000 | 2464 | 1450.6250 | 0.0670 | -0.1162 | -168.5437 | 0.3651 | -57.5854 | -3.2892 | 0.2143 | -72.0512 |
| stopping_rule_v1 | 5.0000 | 2464 | 1450.6250 | 0.1291 | -0.0406 | -58.8642 | 0.6144 | -54.4565 | -6.1357 | 0.4286 | -59.0916 |
| stopping_rule_v1 | 10.0000 | 2464 | 1450.6250 | 0.1883 | -0.0070 | -10.0958 | 1.1067 | -46.0891 | -9.7713 | 0.3571 | -106.2812 |

## Day Stability

| exit_profile_source | date | ttl_sec | n | exposure | weighted_sum_wait_value_bps | weighted_mean_wait_value_bps | weighted_sum_delay_loss_bps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-05 | 0.5000 | 243 | 131.2500 | -3.8583 | -0.0294 | 5.5458 |
| fixed30_livecoherent | 2026-05-06 | 0.5000 | 143 | 81.2500 | -0.7499 | -0.0092 | 8.1862 |
| fixed30_livecoherent | 2026-05-07 | 0.5000 | 54 | 33.3750 | 0.4278 | 0.0128 | 0.0000 |
| fixed30_livecoherent | 2026-05-08 | 0.5000 | 68 | 43.7500 | 3.8340 | 0.0876 | 0.8452 |
| fixed30_livecoherent | 2026-05-09 | 0.5000 | 199 | 129.1250 | 10.1150 | 0.0783 | 33.9289 |
| fixed30_livecoherent | 2026-05-10 | 0.5000 | 177 | 100.3750 | -18.4577 | -0.1839 | 27.5386 |
| fixed30_livecoherent | 2026-05-11 | 0.5000 | 233 | 130.5000 | 10.7811 | 0.0826 | 41.6096 |
| fixed30_livecoherent | 2026-05-12 | 0.5000 | 169 | 118.5000 | -22.0875 | -0.1864 | 27.1399 |
| fixed30_livecoherent | 2026-05-13 | 0.5000 | 169 | 109.7500 | -23.6573 | -0.2156 | 31.9461 |
| fixed30_livecoherent | 2026-05-14 | 0.5000 | 278 | 172.8750 | 30.2076 | 0.1747 | 12.7305 |
| fixed30_livecoherent | 2026-05-15 | 0.5000 | 227 | 139.7500 | 35.8692 | 0.2567 | 18.2747 |
| fixed30_livecoherent | 2026-05-16 | 0.5000 | 149 | 91.7500 | -14.2396 | -0.1552 | 19.4857 |
| fixed30_livecoherent | 2026-05-17 | 0.5000 | 143 | 83.8750 | 3.4910 | 0.0416 | 5.5102 |
| fixed30_livecoherent | 2026-05-18 | 0.5000 | 212 | 128.3750 | -6.0541 | -0.0472 | 11.1134 |
| fixed30_livecoherent | 2026-05-05 | 1.0000 | 243 | 131.2500 | 6.7060 | 0.0511 | 8.8260 |
| fixed30_livecoherent | 2026-05-06 | 1.0000 | 143 | 81.2500 | -3.2695 | -0.0402 | 10.7058 |
| fixed30_livecoherent | 2026-05-07 | 1.0000 | 54 | 33.3750 | 0.0000 | 0.0000 | 0.0000 |
| fixed30_livecoherent | 2026-05-08 | 1.0000 | 68 | 43.7500 | 7.6599 | 0.1751 | 0.8452 |
| fixed30_livecoherent | 2026-05-09 | 1.0000 | 199 | 129.1250 | -3.4277 | -0.0265 | 41.9467 |
| fixed30_livecoherent | 2026-05-10 | 1.0000 | 177 | 100.3750 | 1.5815 | 0.0158 | 30.5493 |
| fixed30_livecoherent | 2026-05-11 | 1.0000 | 233 | 130.5000 | -6.0337 | -0.0462 | 45.3924 |
| fixed30_livecoherent | 2026-05-12 | 1.0000 | 169 | 118.5000 | -21.5754 | -0.1821 | 28.6305 |
| fixed30_livecoherent | 2026-05-13 | 1.0000 | 169 | 109.7500 | -40.5565 | -0.3695 | 50.2982 |
| fixed30_livecoherent | 2026-05-14 | 1.0000 | 278 | 172.8750 | 2.9892 | 0.0173 | 48.6313 |
| fixed30_livecoherent | 2026-05-15 | 1.0000 | 227 | 139.7500 | 29.3158 | 0.2098 | 33.4804 |
| fixed30_livecoherent | 2026-05-16 | 1.0000 | 149 | 91.7500 | -20.7017 | -0.2256 | 25.9479 |
| fixed30_livecoherent | 2026-05-17 | 1.0000 | 143 | 83.8750 | 3.3277 | 0.0397 | 5.6736 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | 212 | 128.3750 | -0.5069 | -0.0039 | 12.8520 |
| fixed30_livecoherent | 2026-05-05 | 2.0000 | 243 | 131.2500 | 4.1757 | 0.0318 | 12.4396 |
| fixed30_livecoherent | 2026-05-06 | 2.0000 | 143 | 81.2500 | -2.2496 | -0.0277 | 14.6450 |
| fixed30_livecoherent | 2026-05-07 | 2.0000 | 54 | 33.3750 | 0.0000 | 0.0000 | 0.0000 |
| fixed30_livecoherent | 2026-05-08 | 2.0000 | 68 | 43.7500 | 0.4471 | 0.0102 | 8.0580 |
| fixed30_livecoherent | 2026-05-09 | 2.0000 | 199 | 129.1250 | -8.5976 | -0.0666 | 83.9429 |
| fixed30_livecoherent | 2026-05-10 | 2.0000 | 177 | 100.3750 | 29.0937 | 0.2898 | 23.9856 |
| fixed30_livecoherent | 2026-05-11 | 2.0000 | 233 | 130.5000 | -23.7681 | -0.1821 | 63.8747 |
| fixed30_livecoherent | 2026-05-12 | 2.0000 | 169 | 118.5000 | 28.1210 | 0.2373 | 32.2478 |
| fixed30_livecoherent | 2026-05-13 | 2.0000 | 169 | 109.7500 | -37.3367 | -0.3402 | 63.2274 |
| fixed30_livecoherent | 2026-05-14 | 2.0000 | 278 | 172.8750 | 15.5816 | 0.0901 | 75.2111 |
| fixed30_livecoherent | 2026-05-15 | 2.0000 | 227 | 139.7500 | 37.5955 | 0.2690 | 58.1684 |
| fixed30_livecoherent | 2026-05-16 | 2.0000 | 149 | 91.7500 | -24.8552 | -0.2709 | 40.8571 |
| fixed30_livecoherent | 2026-05-17 | 2.0000 | 143 | 83.8750 | 5.3846 | 0.0642 | 14.0362 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | 212 | 128.3750 | 0.7999 | 0.0062 | 16.9023 |
| fixed30_livecoherent | 2026-05-05 | 5.0000 | 243 | 131.2500 | -15.2458 | -0.1162 | 37.2139 |
| fixed30_livecoherent | 2026-05-06 | 5.0000 | 143 | 81.2500 | -7.2057 | -0.0887 | 21.7804 |
| fixed30_livecoherent | 2026-05-07 | 5.0000 | 54 | 33.3750 | 2.2137 | 0.0663 | 0.4209 |
| fixed30_livecoherent | 2026-05-08 | 5.0000 | 68 | 43.7500 | -0.5447 | -0.0124 | 12.2873 |
| fixed30_livecoherent | 2026-05-09 | 5.0000 | 199 | 129.1250 | -59.7417 | -0.4627 | 145.6226 |
| fixed30_livecoherent | 2026-05-10 | 5.0000 | 177 | 100.3750 | 27.8913 | 0.2779 | 42.6109 |
| fixed30_livecoherent | 2026-05-11 | 5.0000 | 233 | 130.5000 | 14.8571 | 0.1138 | 100.9461 |
| fixed30_livecoherent | 2026-05-12 | 5.0000 | 169 | 118.5000 | 51.0152 | 0.4305 | 36.0398 |
| fixed30_livecoherent | 2026-05-13 | 5.0000 | 169 | 109.7500 | -14.7249 | -0.1342 | 78.7562 |
| fixed30_livecoherent | 2026-05-14 | 5.0000 | 278 | 172.8750 | 43.6733 | 0.2526 | 179.3022 |
| fixed30_livecoherent | 2026-05-15 | 5.0000 | 227 | 139.7500 | 24.8401 | 0.1777 | 127.1565 |
| fixed30_livecoherent | 2026-05-16 | 5.0000 | 149 | 91.7500 | -26.8342 | -0.2925 | 73.6418 |
| fixed30_livecoherent | 2026-05-17 | 5.0000 | 143 | 83.8750 | -19.3686 | -0.2309 | 81.8377 |
| fixed30_livecoherent | 2026-05-18 | 5.0000 | 212 | 128.3750 | 5.2803 | 0.0411 | 32.8487 |
| fixed30_livecoherent | 2026-05-05 | 10.0000 | 243 | 131.2500 | -25.1316 | -0.1915 | 81.5256 |
| fixed30_livecoherent | 2026-05-06 | 10.0000 | 143 | 81.2500 | -18.9144 | -0.2328 | 35.7549 |
| fixed30_livecoherent | 2026-05-07 | 10.0000 | 54 | 33.3750 | 0.9195 | 0.0276 | 4.2479 |
| fixed30_livecoherent | 2026-05-08 | 10.0000 | 68 | 43.7500 | -4.5658 | -0.1044 | 19.5577 |
| fixed30_livecoherent | 2026-05-09 | 10.0000 | 199 | 129.1250 | -51.2349 | -0.3968 | 190.1157 |
| fixed30_livecoherent | 2026-05-10 | 10.0000 | 177 | 100.3750 | 40.9278 | 0.4077 | 73.9607 |
| fixed30_livecoherent | 2026-05-11 | 10.0000 | 233 | 130.5000 | 53.1650 | 0.4074 | 118.8250 |
| fixed30_livecoherent | 2026-05-12 | 10.0000 | 169 | 118.5000 | 15.4683 | 0.1305 | 102.8868 |
| fixed30_livecoherent | 2026-05-13 | 10.0000 | 169 | 109.7500 | -63.5943 | -0.5794 | 135.2955 |
| fixed30_livecoherent | 2026-05-14 | 10.0000 | 278 | 172.8750 | 106.4011 | 0.6155 | 319.9454 |
| fixed30_livecoherent | 2026-05-15 | 10.0000 | 227 | 139.7500 | 103.4390 | 0.7402 | 199.1703 |
| fixed30_livecoherent | 2026-05-16 | 10.0000 | 149 | 91.7500 | 1.0242 | 0.0112 | 95.5204 |
| fixed30_livecoherent | 2026-05-17 | 10.0000 | 143 | 83.8750 | -25.3786 | -0.3026 | 108.7459 |
| fixed30_livecoherent | 2026-05-18 | 10.0000 | 212 | 128.3750 | 23.6321 | 0.1841 | 76.1029 |
| fixed45_livecoherent | 2026-05-05 | 0.5000 | 243 | 125.3750 | 1.8370 | 0.0147 | 3.6019 |
| fixed45_livecoherent | 2026-05-06 | 0.5000 | 143 | 75.8750 | 13.3427 | 0.1759 | 1.4339 |
| fixed45_livecoherent | 2026-05-07 | 0.5000 | 54 | 33.1250 | 0.0000 | 0.0000 | 0.0000 |
| fixed45_livecoherent | 2026-05-08 | 0.5000 | 68 | 40.5000 | -0.2327 | -0.0057 | 1.6917 |
| fixed45_livecoherent | 2026-05-09 | 0.5000 | 199 | 122.0000 | -1.6255 | -0.0133 | 17.1821 |
| fixed45_livecoherent | 2026-05-10 | 0.5000 | 177 | 92.3750 | -3.9650 | -0.0429 | 8.6152 |
| fixed45_livecoherent | 2026-05-11 | 0.5000 | 233 | 127.3750 | 9.1462 | 0.0718 | 10.6880 |
| fixed45_livecoherent | 2026-05-12 | 0.5000 | 169 | 113.0000 | -9.8693 | -0.0873 | 10.5864 |
| fixed45_livecoherent | 2026-05-13 | 0.5000 | 169 | 108.1250 | 14.1177 | 0.1306 | 0.0000 |
| fixed45_livecoherent | 2026-05-14 | 0.5000 | 278 | 168.3750 | 45.7523 | 0.2717 | 9.7948 |

## Cell Readout

| exit_profile_source | ttl_sec | cell | n | exposure | weighted_sum_wait_value_bps | weighted_mean_wait_value_bps | worst_wait_value_bps | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 0.5000 | 10_r5_only | 1195 | 466.1250 | 32.3000 | 0.0693 | -24.9035 | 0.4286 |
| fixed30_livecoherent | 0.5000 | 11_r5_frames | 136 | 167.6250 | 17.9876 | 0.1073 | 0.0000 | 0.4286 |
| fixed30_livecoherent | 0.5000 | 00_none | 1010 | 659.2500 | -11.2597 | -0.0171 | -27.2984 | 0.4286 |
| fixed30_livecoherent | 0.5000 | 01_frames_only | 123 | 201.5000 | -33.4064 | -0.1658 | -7.1566 | 0.0714 |
| fixed30_livecoherent | 1.0000 | 10_r5_only | 1195 | 466.1250 | 36.4019 | 0.0781 | -36.7110 | 0.5000 |
| fixed30_livecoherent | 1.0000 | 11_r5_frames | 136 | 167.6250 | 24.5942 | 0.1467 | -3.7994 | 0.5000 |
| fixed30_livecoherent | 1.0000 | 01_frames_only | 123 | 201.5000 | -46.8655 | -0.2326 | -6.5062 | 0.2143 |
| fixed30_livecoherent | 1.0000 | 00_none | 1010 | 659.2500 | -58.6221 | -0.0889 | -30.3269 | 0.2857 |
| fixed30_livecoherent | 2.0000 | 11_r5_frames | 136 | 167.6250 | 71.4809 | 0.4264 | -6.3404 | 0.5714 |
| fixed30_livecoherent | 2.0000 | 10_r5_only | 1195 | 466.1250 | 39.9737 | 0.0858 | -48.1434 | 0.4286 |
| fixed30_livecoherent | 2.0000 | 00_none | 1010 | 659.2500 | -26.5861 | -0.0403 | -48.4791 | 0.4286 |
| fixed30_livecoherent | 2.0000 | 01_frames_only | 123 | 201.5000 | -60.4767 | -0.3001 | -8.5309 | 0.2143 |
| fixed30_livecoherent | 5.0000 | 11_r5_frames | 136 | 167.6250 | 137.5870 | 0.8208 | -8.4170 | 0.5714 |
| fixed30_livecoherent | 5.0000 | 10_r5_only | 1195 | 466.1250 | 83.3014 | 0.1787 | -33.3245 | 0.4286 |
| fixed30_livecoherent | 5.0000 | 01_frames_only | 123 | 201.5000 | -72.4187 | -0.3594 | -18.2715 | 0.1429 |
| fixed30_livecoherent | 5.0000 | 00_none | 1010 | 659.2500 | -122.3644 | -0.1856 | -54.5225 | 0.5000 |
| fixed30_livecoherent | 10.0000 | 10_r5_only | 1195 | 466.1250 | 168.1814 | 0.3608 | -54.4170 | 0.6429 |
| fixed30_livecoherent | 10.0000 | 11_r5_frames | 136 | 167.6250 | 142.3676 | 0.8493 | -21.5234 | 0.4286 |
| fixed30_livecoherent | 10.0000 | 00_none | 1010 | 659.2500 | -69.5845 | -0.1056 | -63.0241 | 0.5000 |
| fixed30_livecoherent | 10.0000 | 01_frames_only | 123 | 201.5000 | -84.8069 | -0.4209 | -24.3546 | 0.2143 |
| fixed45_livecoherent | 0.5000 | 10_r5_only | 1320 | 516.3750 | 36.5248 | 0.0707 | -12.4758 | 0.6429 |
| fixed45_livecoherent | 0.5000 | 01_frames_only | 102 | 156.3750 | 15.6232 | 0.0999 | 0.0000 | 0.1429 |
| fixed45_livecoherent | 0.5000 | 11_r5_frames | 157 | 197.2500 | 5.3765 | 0.0273 | -34.0453 | 0.2143 |
| fixed45_livecoherent | 0.5000 | 00_none | 885 | 576.8750 | -17.0567 | -0.0296 | -22.2557 | 0.4286 |
| fixed45_livecoherent | 1.0000 | 10_r5_only | 1320 | 516.3750 | 67.0713 | 0.1299 | -22.9938 | 0.5000 |
| fixed45_livecoherent | 1.0000 | 01_frames_only | 102 | 156.3750 | 24.5671 | 0.1571 | 0.0000 | 0.2857 |
| fixed45_livecoherent | 1.0000 | 11_r5_frames | 157 | 197.2500 | 21.9676 | 0.1114 | -34.0453 | 0.2857 |
| fixed45_livecoherent | 1.0000 | 00_none | 885 | 576.8750 | -32.8638 | -0.0570 | -37.1795 | 0.5000 |
| fixed45_livecoherent | 2.0000 | 10_r5_only | 1320 | 516.3750 | 78.9479 | 0.1529 | -42.0859 | 0.6429 |
| fixed45_livecoherent | 2.0000 | 11_r5_frames | 157 | 197.2500 | 17.6627 | 0.0895 | -11.9161 | 0.3571 |
| fixed45_livecoherent | 2.0000 | 01_frames_only | 102 | 156.3750 | 6.5365 | 0.0418 | -4.2277 | 0.2857 |
| fixed45_livecoherent | 2.0000 | 00_none | 885 | 576.8750 | -85.2390 | -0.1478 | -49.9681 | 0.5000 |
| fixed45_livecoherent | 5.0000 | 11_r5_frames | 157 | 197.2500 | 84.1488 | 0.4266 | -11.9161 | 0.5000 |
| fixed45_livecoherent | 5.0000 | 10_r5_only | 1320 | 516.3750 | 57.9296 | 0.1122 | -52.6352 | 0.5714 |
| fixed45_livecoherent | 5.0000 | 00_none | 885 | 576.8750 | 25.4197 | 0.0441 | -42.9364 | 0.5000 |
| fixed45_livecoherent | 5.0000 | 01_frames_only | 102 | 156.3750 | -4.5256 | -0.0289 | -19.6592 | 0.5000 |
| fixed45_livecoherent | 10.0000 | 10_r5_only | 1320 | 516.3750 | 141.9116 | 0.2748 | -30.6169 | 0.6429 |
| fixed45_livecoherent | 10.0000 | 11_r5_frames | 157 | 197.2500 | 116.1004 | 0.5886 | -24.9993 | 0.4286 |
| fixed45_livecoherent | 10.0000 | 00_none | 885 | 576.8750 | 15.7522 | 0.0273 | -51.4856 | 0.5714 |
| fixed45_livecoherent | 10.0000 | 01_frames_only | 102 | 156.3750 | 14.0869 | 0.0901 | -19.6592 | 0.4286 |
| fixed60_taker | 0.5000 | 10_r5_only | 1308 | 511.8750 | 11.2716 | 0.0220 | -13.2722 | 0.5000 |
| fixed60_taker | 0.5000 | 01_frames_only | 104 | 170.8750 | -16.5882 | -0.0971 | -4.5527 | 0.0714 |
| fixed60_taker | 0.5000 | 00_none | 897 | 582.6250 | -23.3277 | -0.0400 | -15.3738 | 0.2857 |
| fixed60_taker | 0.5000 | 11_r5_frames | 155 | 185.2500 | -26.1706 | -0.1413 | -40.2749 | 0.1429 |
| fixed60_taker | 1.0000 | 10_r5_only | 1308 | 511.8750 | 25.1393 | 0.0491 | -14.0845 | 0.6429 |
| fixed60_taker | 1.0000 | 01_frames_only | 104 | 170.8750 | -17.9771 | -0.1052 | -4.5527 | 0.1429 |
| fixed60_taker | 1.0000 | 11_r5_frames | 155 | 185.2500 | -33.3570 | -0.1801 | -16.5901 | 0.1429 |
| fixed60_taker | 1.0000 | 00_none | 897 | 582.6250 | -40.5032 | -0.0695 | -21.2709 | 0.3571 |
| fixed60_taker | 2.0000 | 10_r5_only | 1308 | 511.8750 | 24.0508 | 0.0470 | -19.7381 | 0.6429 |
| fixed60_taker | 2.0000 | 01_frames_only | 104 | 170.8750 | -11.0384 | -0.0646 | -4.5527 | 0.2143 |
| fixed60_taker | 2.0000 | 00_none | 897 | 582.6250 | -64.0446 | -0.1099 | -36.3372 | 0.2857 |
| fixed60_taker | 2.0000 | 11_r5_frames | 155 | 185.2500 | -122.4637 | -0.6611 | -57.5854 | 0.1429 |
| fixed60_taker | 5.0000 | 10_r5_only | 1308 | 511.8750 | 76.9251 | 0.1503 | -46.0891 | 0.6429 |
| fixed60_taker | 5.0000 | 01_frames_only | 104 | 170.8750 | 64.0610 | 0.3749 | -5.1226 | 0.4286 |
| fixed60_taker | 5.0000 | 11_r5_frames | 155 | 185.2500 | -40.4080 | -0.2181 | -54.3775 | 0.5000 |
| fixed60_taker | 5.0000 | 00_none | 897 | 582.6250 | -145.2252 | -0.2493 | -54.4565 | 0.2857 |
| fixed60_taker | 10.0000 | 10_r5_only | 1308 | 511.8750 | 155.2985 | 0.3034 | -46.0891 | 0.6429 |
| fixed60_taker | 10.0000 | 01_frames_only | 104 | 170.8750 | 48.7887 | 0.2855 | -12.9836 | 0.5714 |
| fixed60_taker | 10.0000 | 11_r5_frames | 155 | 185.2500 | -45.1121 | -0.2435 | -31.2682 | 0.5000 |
| fixed60_taker | 10.0000 | 00_none | 897 | 582.6250 | -117.8310 | -0.2022 | -37.3787 | 0.2857 |
| stopping_rule_v1 | 0.5000 | 10_r5_only | 1308 | 511.8750 | 10.0267 | 0.0196 | -13.2722 | 0.5000 |
| stopping_rule_v1 | 0.5000 | 01_frames_only | 104 | 170.8750 | -16.5882 | -0.0971 | -4.5527 | 0.0714 |
| stopping_rule_v1 | 0.5000 | 11_r5_frames | 155 | 185.2500 | -23.7660 | -0.1283 | -40.2749 | 0.2143 |
| stopping_rule_v1 | 0.5000 | 00_none | 897 | 582.6250 | -25.7655 | -0.0442 | -15.3738 | 0.2857 |
| stopping_rule_v1 | 1.0000 | 10_r5_only | 1308 | 511.8750 | 24.8472 | 0.0485 | -14.0845 | 0.5714 |
| stopping_rule_v1 | 1.0000 | 01_frames_only | 104 | 170.8750 | -17.9771 | -0.1052 | -4.5527 | 0.1429 |
| stopping_rule_v1 | 1.0000 | 11_r5_frames | 155 | 185.2500 | -31.4512 | -0.1698 | -16.5901 | 0.2143 |
| stopping_rule_v1 | 1.0000 | 00_none | 897 | 582.6250 | -42.9410 | -0.0737 | -21.2709 | 0.3571 |
| stopping_rule_v1 | 2.0000 | 10_r5_only | 1308 | 511.8750 | 36.9360 | 0.0722 | -18.8444 | 0.6429 |
| stopping_rule_v1 | 2.0000 | 01_frames_only | 104 | 170.8750 | -11.0384 | -0.0646 | -4.5527 | 0.2143 |
| stopping_rule_v1 | 2.0000 | 00_none | 897 | 582.6250 | -73.8834 | -0.1268 | -36.3372 | 0.2857 |
| stopping_rule_v1 | 2.0000 | 11_r5_frames | 155 | 185.2500 | -120.5579 | -0.6508 | -57.5854 | 0.2143 |
| stopping_rule_v1 | 5.0000 | 10_r5_only | 1308 | 511.8750 | 69.7414 | 0.1362 | -46.0891 | 0.6429 |
| stopping_rule_v1 | 5.0000 | 01_frames_only | 104 | 170.8750 | 64.0610 | 0.3749 | -5.1226 | 0.4286 |
| stopping_rule_v1 | 5.0000 | 11_r5_frames | 155 | 185.2500 | -38.0034 | -0.2051 | -54.3775 | 0.5000 |
| stopping_rule_v1 | 5.0000 | 00_none | 897 | 582.6250 | -154.6631 | -0.2655 | -54.4565 | 0.2857 |
| stopping_rule_v1 | 10.0000 | 10_r5_only | 1308 | 511.8750 | 147.5835 | 0.2883 | -46.0891 | 0.6429 |
| stopping_rule_v1 | 10.0000 | 01_frames_only | 104 | 170.8750 | 48.7887 | 0.2855 | -12.9836 | 0.5714 |
| stopping_rule_v1 | 10.0000 | 11_r5_frames | 155 | 185.2500 | -42.7075 | -0.2305 | -31.2682 | 0.5000 |
| stopping_rule_v1 | 10.0000 | 00_none | 897 | 582.6250 | -163.7604 | -0.2811 | -39.4893 | 0.2857 |

## Runtime-Safe Factor Buckets

| exit_profile_source | ttl_sec | factor | factor_bin | n | exposure | weighted_sum_wait_value_bps | weighted_mean_wait_value_bps | positive_day_frac | min_day_wait_sum_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed60_taker | 10.0000 | recent_mid_alpha_5s_bps | q5 | 493 | 290.2500 | 360.3054 | 1.2414 | 0.7143 | -26.5990 |
| stopping_rule_v1 | 10.0000 | recent_mid_alpha_5s_bps | q5 | 493 | 290.7500 | 352.7639 | 1.2133 | 0.7143 | -26.5990 |
| stopping_rule_v1 | 10.0000 | same_minus_opposite_qty_5s | q5 | 493 | 286.2500 | 257.1457 | 0.8983 | 0.7143 | -10.3270 |
| stopping_rule_v1 | 10.0000 | same_flow_imbalance_5s | q5 | 493 | 286.2500 | 257.1457 | 0.8983 | 0.7143 | -10.3270 |
| fixed60_taker | 10.0000 | same_flow_imbalance_5s | q5 | 493 | 287.3750 | 253.7761 | 0.8831 | 0.7143 | -7.7158 |
| fixed60_taker | 10.0000 | same_minus_opposite_qty_5s | q5 | 493 | 287.3750 | 253.7761 | 0.8831 | 0.7143 | -7.7158 |
| fixed45_livecoherent | 10.0000 | path_h_bps | q5 | 493 | 291.1250 | 251.6140 | 0.8643 | 0.6429 | -67.1287 |
| fixed30_livecoherent | 10.0000 | exit_spread_bps | q4 | 493 | 304.0000 | 237.4795 | 0.7812 | 0.5714 | -16.7322 |
| fixed30_livecoherent | 10.0000 | decision_frames_since_mid_change | q1 | 493 | 285.2500 | 206.8302 | 0.7251 | 0.6429 | -40.6015 |
| fixed60_taker | 10.0000 | decision_frames_since_mid_change | q1 | 493 | 277.6250 | 199.0141 | 0.7168 | 0.7143 | -31.8004 |
| fixed45_livecoherent | 10.0000 | exit_spread_bps | q5 | 493 | 294.1250 | 191.7824 | 0.6520 | 0.7143 | -34.7268 |
| fixed60_taker | 10.0000 | path_h_bps | q5 | 493 | 286.3750 | 189.3480 | 0.6612 | 0.5000 | -59.1089 |
| fixed45_livecoherent | 10.0000 | decision_frames_since_mid_change | q1 | 493 | 279.8750 | 184.4300 | 0.6590 | 0.5000 | -41.9061 |
| fixed45_livecoherent | 10.0000 | decision_frames_since_mid_change | q2 | 493 | 292.1250 | 179.0119 | 0.6128 | 0.5714 | -21.7810 |
| fixed45_livecoherent | 10.0000 | recent_mid_alpha_5s_bps | q5 | 493 | 292.2500 | 176.3040 | 0.6033 | 0.7143 | -42.0885 |
| fixed45_livecoherent | 10.0000 | signed_top_depth_imbalance | q3 | 492 | 285.1250 | 176.1910 | 0.6179 | 0.6429 | -19.9947 |
| stopping_rule_v1 | 10.0000 | decision_frames_since_mid_change | q1 | 493 | 276.6250 | 173.6598 | 0.6278 | 0.7143 | -31.8004 |
| fixed45_livecoherent | 10.0000 | same_minus_opposite_qty_5s | q5 | 493 | 294.0000 | 166.5928 | 0.5666 | 0.6429 | -58.3604 |
| fixed45_livecoherent | 10.0000 | same_flow_imbalance_5s | q5 | 493 | 294.0000 | 166.5928 | 0.5666 | 0.6429 | -58.3604 |
| stopping_rule_v1 | 10.0000 | path_h_bps | q5 | 493 | 285.1250 | 162.7469 | 0.5708 | 0.4286 | -59.1089 |
| fixed45_livecoherent | 10.0000 | exit_spread_bps | q3 | 492 | 289.3750 | 161.0385 | 0.5565 | 0.6429 | -37.9442 |
| fixed45_livecoherent | 5.0000 | exit_spread_bps | q3 | 492 | 289.3750 | 144.7588 | 0.5002 | 0.5000 | -19.3517 |
| fixed45_livecoherent | 10.0000 | same_flow_imbalance_5s | q3 | 492 | 300.1250 | 143.9258 | 0.4796 | 1.0000 | 23.9508 |
| fixed45_livecoherent | 10.0000 | same_minus_opposite_qty_5s | q3 | 492 | 300.1250 | 143.9258 | 0.4796 | 1.0000 | 23.9508 |
| fixed30_livecoherent | 5.0000 | exit_spread_bps | q4 | 493 | 304.0000 | 143.6503 | 0.4725 | 0.5000 | -7.8071 |
| fixed30_livecoherent | 10.0000 | signed_top_depth_imbalance | q5 | 493 | 292.8750 | 137.8844 | 0.4708 | 0.5000 | -19.7556 |
| fixed45_livecoherent | 5.0000 | exit_spread_bps | q5 | 493 | 294.1250 | 136.8310 | 0.4652 | 0.7857 | -2.4880 |
| fixed45_livecoherent | 5.0000 | same_flow_imbalance_5s | q5 | 493 | 294.0000 | 132.2068 | 0.4497 | 0.7143 | -35.6176 |
| fixed45_livecoherent | 5.0000 | same_minus_opposite_qty_5s | q5 | 493 | 294.0000 | 132.2068 | 0.4497 | 0.7143 | -35.6176 |
| fixed60_taker | 5.0000 | decision_frames_since_mid_change | q2 | 493 | 284.1250 | 125.7432 | 0.4426 | 0.7143 | -26.5991 |
| fixed45_livecoherent | 5.0000 | path_h_bps | q5 | 493 | 291.1250 | 125.0327 | 0.4295 | 0.5000 | -91.6073 |
| fixed45_livecoherent | 10.0000 | path_d_bps | q3 | 492 | 306.8750 | 123.3511 | 0.4020 | 0.8000 | -28.7531 |
| fixed30_livecoherent | 10.0000 | decision_frames_since_mid_change | q4 | 493 | 294.0000 | 122.9591 | 0.4182 | 0.6429 | -10.3361 |
| fixed30_livecoherent | 10.0000 | path_d_bps | q2 | 493 | 310.5000 | 122.4274 | 0.3943 | 1.0000 | 7.6012 |
| fixed30_livecoherent | 5.0000 | path_d_bps | q2 | 493 | 310.5000 | 121.4743 | 0.3912 | 1.0000 | 21.7550 |
| stopping_rule_v1 | 5.0000 | decision_frames_since_mid_change | q2 | 493 | 285.0000 | 120.0294 | 0.4212 | 0.7857 | -27.1375 |
| fixed30_livecoherent | 10.0000 | same_minus_opposite_qty_5s | q5 | 493 | 301.3750 | 118.4881 | 0.3932 | 0.5714 | -23.5649 |
| fixed30_livecoherent | 10.0000 | same_flow_imbalance_5s | q5 | 493 | 301.3750 | 118.4881 | 0.3932 | 0.5714 | -23.5649 |
| fixed30_livecoherent | 0.5000 | same_minus_opposite_qty_5s | q5 | 493 | 301.3750 | 113.5034 | 0.3766 | 0.6429 | -18.5960 |
| fixed30_livecoherent | 0.5000 | same_flow_imbalance_5s | q5 | 493 | 301.3750 | 113.5034 | 0.3766 | 0.6429 | -18.5960 |
| fixed45_livecoherent | 5.0000 | signed_top_depth_imbalance | q1 | 493 | 303.5000 | 112.0561 | 0.3692 | 0.5714 | -9.1468 |
| fixed60_taker | 10.0000 | exit_spread_bps | q5 | 493 | 299.1250 | 110.2460 | 0.3686 | 0.5714 | -11.8310 |
| fixed45_livecoherent | 5.0000 | path_d_bps | q2 | 493 | 306.3750 | 108.1844 | 0.3531 | 1.0000 | 4.3562 |
| fixed30_livecoherent | 5.0000 | same_minus_opposite_qty_5s | q3 | 492 | 302.3750 | 107.1516 | 0.3544 | 0.7500 | -0.6224 |
| fixed30_livecoherent | 5.0000 | same_flow_imbalance_5s | q3 | 492 | 302.3750 | 107.1516 | 0.3544 | 0.7500 | -0.6224 |
| fixed30_livecoherent | 10.0000 | exit_spread_bps | q5 | 493 | 303.7500 | 107.1504 | 0.3528 | 0.7143 | -32.9183 |
| fixed45_livecoherent | 10.0000 | recent_mid_alpha_5s_bps | q3 | 492 | 297.6250 | 103.8070 | 0.3488 | 0.7500 | -10.4053 |
| fixed45_livecoherent | 5.0000 | same_flow_imbalance_5s | q3 | 492 | 300.1250 | 102.6309 | 0.3420 | 0.7500 | -3.2527 |
| fixed45_livecoherent | 5.0000 | same_minus_opposite_qty_5s | q3 | 492 | 300.1250 | 102.6309 | 0.3420 | 0.7500 | -3.2527 |
| fixed60_taker | 10.0000 | decision_frames_since_mid_change | q2 | 493 | 284.1250 | 102.5033 | 0.3608 | 0.5714 | -45.0658 |
| fixed45_livecoherent | 10.0000 | exit_spread_bps | q4 | 493 | 302.5000 | 102.0191 | 0.3373 | 0.6429 | -11.8584 |
| fixed45_livecoherent | 5.0000 | path_d_bps | q3 | 492 | 306.8750 | 99.3960 | 0.3239 | 0.8000 | -48.9074 |
| stopping_rule_v1 | 10.0000 | exit_spread_bps | q5 | 493 | 295.7500 | 98.9295 | 0.3345 | 0.5714 | -21.4213 |
| fixed30_livecoherent | 5.0000 | recent_mid_alpha_5s_bps | q3 | 492 | 306.1250 | 98.8229 | 0.3228 | 0.6000 | -4.3541 |
| fixed30_livecoherent | 10.0000 | path_h_bps | q5 | 493 | 294.8750 | 97.4725 | 0.3306 | 0.5000 | -60.9021 |
| fixed45_livecoherent | 10.0000 | signed_top_depth_imbalance | q1 | 493 | 303.5000 | 96.2915 | 0.3173 | 0.5000 | -22.4102 |
| fixed30_livecoherent | 10.0000 | recent_mid_alpha_5s_bps | q3 | 492 | 306.1250 | 94.7511 | 0.3095 | 0.6000 | -8.5471 |
| fixed30_livecoherent | 10.0000 | path_h_bps | q4 | 493 | 321.8750 | 93.0564 | 0.2891 | 0.7857 | -17.5043 |
| fixed45_livecoherent | 2.0000 | path_d_bps | q3 | 492 | 306.8750 | 91.3854 | 0.2978 | 1.0000 | 1.5176 |
| fixed30_livecoherent | 10.0000 | same_flow_imbalance_5s | q3 | 492 | 302.3750 | 89.8630 | 0.2972 | 0.7500 | -1.8625 |
| fixed30_livecoherent | 10.0000 | same_minus_opposite_qty_5s | q3 | 492 | 302.3750 | 89.8630 | 0.2972 | 0.7500 | -1.8625 |
| fixed45_livecoherent | 10.0000 | path_d_bps | q1 | 493 | 280.7500 | 88.7933 | 0.3163 | 0.5000 | -8.8044 |
| fixed45_livecoherent | 5.0000 | decision_frames_since_mid_change | q1 | 493 | 279.8750 | 85.1280 | 0.3042 | 0.5000 | -37.4886 |
| fixed30_livecoherent | 5.0000 | signed_top_depth_imbalance | q5 | 493 | 292.8750 | 84.6360 | 0.2890 | 0.5714 | -3.2703 |
| fixed30_livecoherent | 2.0000 | exit_spread_bps | q4 | 493 | 304.0000 | 83.9831 | 0.2763 | 0.6429 | -12.4626 |
| fixed30_livecoherent | 5.0000 | decision_frames_since_mid_change | q4 | 493 | 294.0000 | 83.2502 | 0.2832 | 0.5000 | -9.1357 |
| stopping_rule_v1 | 10.0000 | decision_frames_since_mid_change | q2 | 493 | 285.0000 | 82.3827 | 0.2891 | 0.6429 | -61.4314 |
| fixed30_livecoherent | 5.0000 | path_h_bps | q4 | 493 | 321.8750 | 81.4546 | 0.2531 | 0.7143 | -12.6393 |
| fixed45_livecoherent | 5.0000 | recent_mid_alpha_5s_bps | q5 | 493 | 292.2500 | 80.4118 | 0.2751 | 0.5714 | -33.4368 |
| fixed45_livecoherent | 1.0000 | path_d_bps | q3 | 492 | 306.8750 | 79.1790 | 0.2580 | 0.8000 | -0.2391 |
| fixed45_livecoherent | 10.0000 | path_d_bps | q2 | 493 | 306.3750 | 79.0830 | 0.2581 | 0.8000 | -59.4246 |
| fixed45_livecoherent | 10.0000 | decision_frames_since_mid_change | q3 | 492 | 282.2500 | 78.4913 | 0.2781 | 0.6429 | -37.9290 |
| fixed30_livecoherent | 10.0000 | signed_top_depth_imbalance | q1 | 493 | 311.0000 | 76.7606 | 0.2468 | 0.6429 | -39.2300 |
| fixed45_livecoherent | 10.0000 | signed_top_depth_imbalance | q5 | 493 | 274.7500 | 75.3877 | 0.2744 | 0.7857 | -41.6104 |
| fixed45_livecoherent | 5.0000 | decision_frames_since_mid_change | q3 | 492 | 282.2500 | 74.8125 | 0.2651 | 0.6429 | -43.5670 |
| fixed30_livecoherent | 10.0000 | path_d_bps | q4 | 493 | 284.8750 | 72.8682 | 0.2558 | 0.4286 | -18.9377 |
| stopping_rule_v1 | 5.0000 | signed_top_depth_imbalance | q2 | 493 | 293.3750 | 68.0801 | 0.2321 | 0.5714 | -16.8732 |
| fixed60_taker | 5.0000 | signed_top_depth_imbalance | q2 | 493 | 294.8750 | 67.8369 | 0.2301 | 0.5714 | -16.8732 |
| fixed45_livecoherent | 0.5000 | exit_spread_bps | q5 | 493 | 294.1250 | 67.8012 | 0.2305 | 0.8571 | 0.0000 |
| fixed30_livecoherent | 5.0000 | same_minus_opposite_qty_5s | q5 | 493 | 301.3750 | 67.0347 | 0.2224 | 0.5000 | -24.2086 |

## Post-Exit Diagnostic Labels

| exit_profile_source | ttl_sec | factor | factor_bin | n | exposure | weighted_sum_wait_value_bps | weighted_mean_wait_value_bps | positive_day_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed45_livecoherent | 10.0000 | post_wait_reclaim_bps | q5 | 493 | 278.5000 | 1379.3171 | 4.9527 | 1.0000 |
| fixed30_livecoherent | 10.0000 | post_same_flow_imbalance | q5 | 493 | 294.6250 | 1373.0819 | 4.6604 | 1.0000 |
| fixed30_livecoherent | 10.0000 | post_same_minus_opposite_qty | q5 | 493 | 294.6250 | 1373.0819 | 4.6604 | 1.0000 |
| fixed45_livecoherent | 10.0000 | post_same_minus_opposite_qty | q5 | 493 | 281.0000 | 1370.5054 | 4.8772 | 1.0000 |
| fixed45_livecoherent | 10.0000 | post_same_flow_imbalance | q5 | 493 | 281.0000 | 1370.5054 | 4.8772 | 1.0000 |
| fixed30_livecoherent | 10.0000 | post_wait_reclaim_bps | q5 | 493 | 282.2500 | 1361.2439 | 4.8228 | 1.0000 |
| fixed60_taker | 10.0000 | post_same_minus_opposite_qty | q5 | 493 | 288.6250 | 1352.9097 | 4.6874 | 1.0000 |
| fixed60_taker | 10.0000 | post_same_flow_imbalance | q5 | 493 | 288.6250 | 1352.9097 | 4.6874 | 1.0000 |
| fixed60_taker | 10.0000 | post_wait_reclaim_bps | q5 | 493 | 290.7500 | 1351.3196 | 4.6477 | 0.9286 |
| stopping_rule_v1 | 10.0000 | post_same_minus_opposite_qty | q5 | 493 | 290.5000 | 1328.8588 | 4.5744 | 1.0000 |
| stopping_rule_v1 | 10.0000 | post_same_flow_imbalance | q5 | 493 | 290.5000 | 1328.8588 | 4.5744 | 1.0000 |
| stopping_rule_v1 | 10.0000 | post_wait_reclaim_bps | q5 | 493 | 290.8750 | 1308.6787 | 4.4991 | 0.8571 |
| fixed30_livecoherent | 5.0000 | post_wait_reclaim_bps | q5 | 493 | 281.0000 | 765.3983 | 2.7238 | 1.0000 |
| fixed45_livecoherent | 5.0000 | post_same_flow_imbalance | q5 | 493 | 284.5000 | 737.1025 | 2.5909 | 1.0000 |
| fixed45_livecoherent | 5.0000 | post_same_minus_opposite_qty | q5 | 493 | 284.5000 | 737.1025 | 2.5909 | 1.0000 |
| fixed30_livecoherent | 5.0000 | post_same_flow_imbalance | q5 | 493 | 291.3750 | 709.5693 | 2.4352 | 1.0000 |
| fixed30_livecoherent | 5.0000 | post_same_minus_opposite_qty | q5 | 493 | 291.3750 | 709.5693 | 2.4352 | 1.0000 |
| fixed45_livecoherent | 5.0000 | post_wait_reclaim_bps | q5 | 493 | 279.1250 | 692.6422 | 2.4815 | 0.9286 |
| fixed60_taker | 5.0000 | post_same_minus_opposite_qty | q5 | 493 | 285.0000 | 601.0475 | 2.1089 | 0.9286 |
| fixed60_taker | 5.0000 | post_same_flow_imbalance | q5 | 493 | 285.0000 | 601.0475 | 2.1089 | 0.9286 |
| fixed60_taker | 5.0000 | post_wait_reclaim_bps | q5 | 493 | 285.7500 | 593.7468 | 2.0779 | 0.9286 |
| stopping_rule_v1 | 5.0000 | post_same_minus_opposite_qty | q5 | 493 | 285.6250 | 586.3148 | 2.0527 | 0.8571 |
| stopping_rule_v1 | 5.0000 | post_same_flow_imbalance | q5 | 493 | 285.6250 | 586.3148 | 2.0527 | 0.8571 |
| stopping_rule_v1 | 5.0000 | post_wait_reclaim_bps | q5 | 493 | 285.2500 | 577.5235 | 2.0246 | 0.9286 |
| fixed45_livecoherent | 10.0000 | post_wait_peak_giveback_bps | q3 | 492 | 311.2500 | 566.2185 | 1.8192 | 1.0000 |
| fixed30_livecoherent | 10.0000 | post_wait_peak_giveback_bps | q3 | 492 | 311.8750 | 529.4228 | 1.6975 | 1.0000 |
| fixed60_taker | 10.0000 | post_wait_peak_giveback_bps | q4 | 493 | 299.3750 | 508.5814 | 1.6988 | 1.0000 |
| stopping_rule_v1 | 10.0000 | post_wait_peak_giveback_bps | q4 | 493 | 299.1250 | 480.6835 | 1.6070 | 1.0000 |
| fixed30_livecoherent | 10.0000 | post_wait_peak_giveback_bps | q4 | 493 | 307.0000 | 476.3435 | 1.5516 | 1.0000 |
| stopping_rule_v1 | 10.0000 | post_wait_peak_giveback_bps | q3 | 492 | 300.2500 | 464.1022 | 1.5457 | 1.0000 |
| fixed60_taker | 10.0000 | post_wait_peak_giveback_bps | q3 | 492 | 300.2500 | 464.1022 | 1.5457 | 1.0000 |
| fixed45_livecoherent | 10.0000 | post_wait_peak_giveback_bps | q4 | 493 | 301.2500 | 417.3959 | 1.3855 | 1.0000 |
| fixed30_livecoherent | 2.0000 | post_wait_reclaim_bps | q5 | 493 | 290.0000 | 393.3314 | 1.3563 | 0.9231 |
| fixed30_livecoherent | 2.0000 | post_same_flow_imbalance | q5 | 493 | 289.5000 | 385.8935 | 1.3330 | 1.0000 |
| fixed30_livecoherent | 2.0000 | post_same_minus_opposite_qty | q5 | 493 | 289.5000 | 385.8935 | 1.3330 | 1.0000 |
| fixed30_livecoherent | 10.0000 | post_wait_peak_giveback_bps | q2 | 493 | 307.5000 | 357.7887 | 1.1635 | 1.0000 |
| fixed45_livecoherent | 2.0000 | post_wait_reclaim_bps | q5 | 493 | 283.6250 | 357.6761 | 1.2611 | 0.9286 |
| fixed45_livecoherent | 2.0000 | post_same_flow_imbalance | q5 | 493 | 286.3750 | 327.8929 | 1.1450 | 0.7857 |
| fixed45_livecoherent | 2.0000 | post_same_minus_opposite_qty | q5 | 493 | 286.3750 | 327.8929 | 1.1450 | 0.7857 |
| fixed45_livecoherent | 5.0000 | post_wait_peak_giveback_bps | q3 | 492 | 312.8750 | 316.0200 | 1.0101 | 1.0000 |
| fixed45_livecoherent | 10.0000 | post_wait_peak_giveback_bps | q2 | 493 | 284.6250 | 302.6448 | 1.0633 | 1.0000 |
| fixed30_livecoherent | 5.0000 | post_wait_peak_giveback_bps | q3 | 492 | 318.5000 | 283.9719 | 0.8916 | 1.0000 |
| stopping_rule_v1 | 10.0000 | post_wait_peak_giveback_bps | q2 | 493 | 292.8750 | 263.0433 | 0.8981 | 1.0000 |
| fixed60_taker | 10.0000 | post_wait_peak_giveback_bps | q2 | 493 | 292.8750 | 263.0433 | 0.8981 | 1.0000 |
| fixed45_livecoherent | 5.0000 | post_wait_peak_giveback_bps | q4 | 493 | 302.8750 | 257.5716 | 0.8504 | 1.0000 |
| fixed30_livecoherent | 5.0000 | post_wait_peak_giveback_bps | q2 | 493 | 303.0000 | 234.6252 | 0.7743 | 1.0000 |
| fixed30_livecoherent | 1.0000 | post_same_flow_imbalance | q5 | 493 | 287.6250 | 221.4228 | 0.7698 | 0.9231 |
| fixed30_livecoherent | 1.0000 | post_same_minus_opposite_qty | q5 | 493 | 287.6250 | 221.4228 | 0.7698 | 0.9231 |
| fixed60_taker | 5.0000 | post_wait_peak_giveback_bps | q4 | 493 | 302.5000 | 221.3723 | 0.7318 | 1.0000 |
| stopping_rule_v1 | 5.0000 | post_wait_peak_giveback_bps | q4 | 493 | 302.5000 | 210.8848 | 0.6971 | 1.0000 |
| stopping_rule_v1 | 5.0000 | post_wait_peak_giveback_bps | q3 | 492 | 313.7500 | 203.7892 | 0.6495 | 1.0000 |
| fixed60_taker | 5.0000 | post_wait_peak_giveback_bps | q3 | 492 | 313.7500 | 203.7892 | 0.6495 | 1.0000 |
| fixed45_livecoherent | 1.0000 | post_same_flow_imbalance | q5 | 493 | 290.1250 | 197.9282 | 0.6822 | 0.8571 |
| fixed45_livecoherent | 1.0000 | post_same_minus_opposite_qty | q5 | 493 | 290.1250 | 197.9282 | 0.6822 | 0.8571 |
| fixed30_livecoherent | 5.0000 | post_wait_peak_giveback_bps | q4 | 493 | 305.2500 | 196.7054 | 0.6444 | 1.0000 |
| fixed45_livecoherent | 1.0000 | post_wait_reclaim_bps | q5 | 493 | 288.1250 | 180.1580 | 0.6253 | 0.9286 |
| fixed45_livecoherent | 10.0000 | post_wait_peak_giveback_bps | q1 | 493 | 264.2500 | 171.8770 | 0.6504 | 1.0000 |
| fixed30_livecoherent | 0.5000 | post_same_minus_opposite_qty | q5 | 493 | 290.8750 | 166.2644 | 0.5716 | 0.9231 |
| fixed30_livecoherent | 0.5000 | post_same_flow_imbalance | q5 | 493 | 290.8750 | 166.2644 | 0.5716 | 0.9231 |
| fixed60_taker | 2.0000 | post_same_minus_opposite_qty | q5 | 493 | 281.0000 | 159.6971 | 0.5683 | 0.7692 |

## Files

- Panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_q70_idle01_g1_20260505_18_20260522\conditional_wait_exit_panel.parquet`
- TTL summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_q70_idle01_g1_20260505_18_20260522\conditional_wait_exit_ttl_summary.csv`
- Factor summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_q70_idle01_g1_20260505_18_20260522\conditional_wait_exit_factor_summary.csv`
- Manifest: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_q70_idle01_g1_20260505_18_20260522\summary.json`

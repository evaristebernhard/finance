# CCUSDT TFI 2026-05-09 High/Chop Deep Dive

Status: `20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1`.

Guardrail: `research_only_0509_high_chop_accident_diagnostic_no_execution_recommendation`.

This report deep-dives the `2026-05-09` high/chop accident group in the CCUSDT V1 TFI branch. It is a diagnostic, not an execution recommendation.

## Definitions

The focus set is:

$$
\mathcal A=\{i:d_i=\mathrm{2026-05-09},\ q_i=\mathrm{high},\ z_i=\mathrm{chop}\}.
$$

Contribution is measured with the already cost-adjusted entry net and target exposure:

$$
G(S)=\sum_{i\in S}\gamma_i r_i,\qquad \kappa_1=\frac{\max_{i\in S}|\gamma_i r_i|}{|G(S)|}.
$$

The signed path around an entry is:

$$
R_i(\tau)=s_i\,10^4\log\frac{M_{t_i+\tau}}{M_{t_i}},\qquad s_i=+1\ (\mathrm{long}),\ s_i=-1\ (\mathrm{short}).
$$

## Main Read

1. The high/chop focus set has `9` entries and total target PnL `-233.6197` bps-equivalent exposure units.
2. The largest absolute contributor is `entry_row=1615412` with target PnL `-242.4187` and target exposure `8.0000`.
3. The top-1 concentration is `1.0377`. Since this is above `1`, the single row explains more than all of the focus loss; the remaining focus entries sum to `8.7990`.
4. This is not a broad high/chop failure: `other_days_high_chop` is `2727.6779`, while `2026-05-09 high_non_chop` is `181.9079`.
5. The more precise accident surface is the matched `11_r5_frames / short / q70_85 / delta10=s80_100` bucket. On `2026-05-09` it has `6` entries, total PnL `-642.9602`, and `gt2_rate` `0.0000`; excluding `2026-05-09`, the same bucket is `1405.8597`.

So the clean read is: `2026-05-09 high/chop` is one oversized `11` loss, but that row belongs to a same-day `11/short/q70_85/high-delta` bucket inversion. The bad day is not random noise only, and also not enough evidence to ban the bucket globally.

## Focus Entries

| entry_row | entry_event_index | cell | direction_label | frames_q_bin | delta10_bin | energy10_bin | z10_bin | net | gross | cost | target_exposure | target_pnl | mfe_bps | mae_bps | dominant_latent_state | chop_score | release_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1615412 | 77580 | 11_r5_frames | short | q70_85 | s80_100 | s80_100 | s80_100 | -30.3023 | -27.8923 | 2.4101 | 8.0000 | -242.4187 | 12.5612 | -29.4569 | chop | 0.6773 | 0.5509 |
| 1628339 | 90507 | 10_r5_only | short | q0_50 | s80_100 | s80_100 | s80_100 | -35.1325 | -33.1760 | 1.9565 | 0.3750 | -13.1747 | 1.2782 | -33.1760 | chop | 0.6268 | 0.5285 |
| 1616101 | 78269 | 10_r5_only | short | q0_50 | s80_100 | s80_100 | s80_100 | -13.5245 | -11.8981 | 1.6264 | 0.3750 | -5.0717 | 11.9122 | -24.7196 | chop | 0.6627 | 0.5888 |
| 1634224 | 96392 | 10_r5_only | short | q0_50 | s80_100 | s60_80 | s80_100 | -1.3193 | -0.0000 | 1.3193 | 0.3750 | -0.4947 | 0.3193 | -0.0000 | chop | 0.5544 | 0.4827 |
| 1620046 | 82214 | 10_r5_only | short | q70_85 | s0_20 | s80_100 | s0_20 | -1.1565 | 0.9393 | 2.0958 | 0.3750 | -0.4337 | 5.6370 | 0.6262 | chop | 0.7048 | 0.3980 |
| 1640588 | 102756 | 10_r5_only | short | q0_50 | s80_100 | s60_80 | s80_100 | 2.8276 | 5.1037 | 2.2761 | 0.3750 | 1.0603 | 5.1037 | -0.0000 | chop | 0.6128 | 0.4639 |
| 1643093 | 105261 | 10_r5_only | short | q0_50 | s80_100 | s80_100 | s80_100 | 12.6653 | 15.1123 | 2.4470 | 0.3750 | 4.7495 | 15.4341 | -0.0000 | chop | 0.7043 | 0.4185 |
| 1615992 | 78160 | 10_r5_only | short | q0_50 | s80_100 | s80_100 | s80_100 | 18.7322 | 21.2979 | 2.5657 | 0.3750 | 7.0246 | 21.6115 | -0.0000 | chop | 0.7520 | 0.4862 |
| 1612239 | 74407 | 10_r5_only | short | q0_50 | s80_100 | s80_100 | s80_100 | 40.3718 | 42.7758 | 2.4040 | 0.3750 | 15.1394 | 43.0887 | -0.0000 | chop | 0.7222 | 0.3769 |

## Matched Controls

| group | entries | exposure | total_pnl | weighted_mean_net | net_mean | net_median | gt2_rate | mfe_mean | mae_mean | chop_score_mean | release_score_mean | X_t_mean | log_U_t_mean | C_confirm_t_mean | D_divergence_t_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| focus_0509_high_chop | 9 | 11.0000 | -233.6197 | -21.2382 | -0.7598 | -1.1565 | 0.4444 | 12.9940 | -9.6363 | 0.6686 | 0.4772 | -76.2870 | -74.7917 | 146.2981 | -222.5851 |
| focus_without_top1 | 8 | 3.0000 | 8.7990 | 2.9330 | 2.9330 | 0.8355 | 0.5000 | 13.0481 | -7.1587 | 0.6675 | 0.4679 | -86.3434 | -85.1165 | 153.0592 | -239.4026 |
| disaster_row | 1 | 8.0000 | -242.4187 | -30.3023 | -30.3023 | -30.3023 | 0.0000 | 12.5612 | -29.4569 | 0.6773 | 0.5509 | 4.1638 | 7.8066 | 92.2091 | -88.0452 |
| 0509_high_non_chop | 44 | 112.0000 | 181.9079 | 1.6242 | 4.9004 | -0.6805 | 0.4773 | 12.7905 | -3.2828 | 0.4427 | 0.5616 | 91.8227 | 93.6845 | 123.9739 | -32.1512 |
| 0509_reduce_chop | 32 | 12.0000 | -38.6654 | -3.2221 | -3.2221 | -1.5616 | 0.4375 | 8.3816 | -9.3266 | 0.6761 | 0.5045 | -52.3784 | -51.7650 | 647.5389 | -699.9173 |
| other_days_high_chop | 223 | 501.5000 | 2727.6779 | 5.4390 | 3.0767 | -0.5127 | 0.4484 | 10.1931 | -3.6496 | 0.6390 | 0.5074 | -2.7565 | -1.9454 | 263.0763 | -265.8328 |
| all_high_chop | 232 | 512.5000 | 2494.0582 | 4.8665 | 2.9279 | -0.5140 | 0.4483 | 10.3018 | -3.8818 | 0.6401 | 0.5062 | -5.6090 | -4.7713 | 258.5461 | -264.1551 |
| same_delta_bucket_all_days | 13 | 104.0000 | 762.8995 | 7.3356 | 7.3356 | -1.4835 | 0.3846 | 21.2025 | -6.0779 | 0.5523 | 0.5486 | 23.7487 | 26.2514 | 131.6924 | -107.9437 |
| same_delta_bucket_0509 | 6 | 48.0000 | -642.9602 | -13.3950 | -13.3950 | -10.7824 | 0.0000 | 2.7900 | -11.9912 | 0.5259 | 0.5742 | 40.9185 | 43.5238 | 226.7339 | -185.8154 |
| same_delta_bucket_ex0509 | 7 | 56.0000 | 1405.8597 | 25.1046 | 25.1046 | 5.6000 | 0.7143 | 36.9847 | -1.0093 | 0.5750 | 0.5267 | 9.0317 | 11.4466 | 50.2283 | -41.1966 |
| same_full_strength_bucket_all_days | 11 | 88.0000 | 237.5836 | 2.6998 | 2.6998 | -7.0497 | 0.3636 | 17.7173 | -7.1829 | 0.5465 | 0.5400 | 24.2662 | 26.5573 | 74.9581 | -50.6919 |
| same_full_strength_bucket_0509 | 5 | 40.0000 | -637.5049 | -15.9376 | -15.9376 | -13.8531 | 0.0000 | 3.0935 | -14.3894 | 0.5304 | 0.5605 | 40.3584 | 42.6608 | 121.2149 | -80.8565 |
| same_full_strength_bucket_ex0509 | 6 | 48.0000 | 875.0885 | 18.2310 | 18.2310 | 5.3129 | 0.6667 | 29.9038 | -1.1776 | 0.5599 | 0.5229 | 10.8560 | 13.1378 | 36.4108 | -25.5548 |

## Same-Bucket Daily

| bucket | date | entries | exposure | total_pnl | net_mean | net_median | mfe_mean | mae_mean | chop_score_mean | release_score_mean | X_t_mean | log_U_t_mean | C_confirm_t_mean | D_divergence_t_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| same_delta_bucket | 2026-05-09 | 6 | 48.0000 | -642.9602 | -13.3950 | -10.7824 | 2.7900 | -11.9912 | 0.5259 | 0.5742 | 40.9185 | 43.5238 | 226.7339 | -185.8154 |
| same_delta_bucket | 2026-05-10 | 1 | 8.0000 | -56.3977 | -7.0497 | -7.0497 | 6.3719 | -5.0946 | 0.5874 | 0.5696 | 10.7520 | 13.5270 | 168.2312 | -157.4791 |
| same_delta_bucket | 2026-05-11 | 1 | 8.0000 | 40.2055 | 5.0257 | 5.0257 | 30.1641 | 7.2311 | 0.4289 | 0.5137 | 28.0123 | 28.5170 | -5.3581 | 33.3704 |
| same_delta_bucket | 2026-05-14 | 4 | 32.0000 | 1377.2518 | 43.0391 | 51.0123 | 53.7034 | -2.3005 | 0.6186 | 0.5170 | 4.1695 | 6.8610 | 42.8743 | -38.7047 |
| same_delta_bucket | 2026-05-15 | 1 | 8.0000 | 44.8001 | 5.6000 | 5.6000 | 7.5431 | 0.0000 | 0.5342 | 0.5357 | 7.7794 | 10.6379 | 17.2277 | -9.4482 |
| same_full_strength_bucket | 2026-05-09 | 5 | 40.0000 | -637.5049 | -15.9376 | -13.8531 | 3.0935 | -14.3894 | 0.5304 | 0.5605 | 40.3584 | 42.6608 | 121.2149 | -80.8565 |
| same_full_strength_bucket | 2026-05-10 | 1 | 8.0000 | -56.3977 | -7.0497 | -7.0497 | 6.3719 | -5.0946 | 0.5874 | 0.5696 | 10.7520 | 13.5270 | 168.2312 | -157.4791 |
| same_full_strength_bucket | 2026-05-11 | 1 | 8.0000 | 40.2055 | 5.0257 | 5.0257 | 30.1641 | 7.2311 | 0.4289 | 0.5137 | 28.0123 | 28.5170 | -5.3581 | 33.3704 |
| same_full_strength_bucket | 2026-05-14 | 3 | 24.0000 | 846.4806 | 35.2700 | 35.6781 | 45.1146 | -3.0673 | 0.6030 | 0.5062 | 6.1975 | 8.7150 | 12.7880 | -6.5906 |
| same_full_strength_bucket | 2026-05-15 | 1 | 8.0000 | 44.8001 | 5.6000 | 5.6000 | 7.5431 | 0.0000 | 0.5342 | 0.5357 | 7.7794 | 10.6379 | 17.2277 | -9.4482 |

## Path Shape

The disaster row was not instantly hopeless. It had a fast favorable excursion, then a full reversal within the same 60-second label horizon:


| entry_row | path_scope | cell | direction_label | net | target_exposure | target_pnl | pre_60s_signed_bps | post_60s_final_bps | post_60s_mfe_bps | post_60s_mae_bps | time_to_mfe_sec | time_to_mae_sec | post_qi5_mean | post_mlofi5_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1615412 | focus_and_same_delta_bucket_0509 | 11_r5_frames | short | -30.3023 | 8.0000 | -242.4187 | 26.0822 | -27.8923 | 12.5612 | -29.4569 | 4.7051 | 53.4413 | -0.2946 | -0.2190 |
| 1604781 | same_delta_bucket_0509 | 11_r5_frames | short | -26.3375 | 8.0000 | -210.6999 | -3.5541 | -24.2072 | 2.2623 | -24.2072 | 0.0997 | 48.7307 | -0.6871 | 16.9264 |
| 1642948 | same_delta_bucket_0509 | 11_r5_frames | short | -13.8531 | 8.0000 | -110.8245 | -0.9645 | -12.2104 | 0.3215 | -12.2104 | 5.7078 | 53.3701 | 0.1500 | 22.5386 |
| 1567080 | same_delta_bucket_0509 | 11_r5_frames | short | -7.7117 | 8.0000 | -61.6937 | 8.3155 | -5.7528 | -0.0000 | -6.0723 | 1.0033 | 28.6062 | -0.9209 | 0.1268 |
| 1628339 | focus_0509_high_chop | 10_r5_only | short | -35.1325 | 0.3750 | -13.1747 | -5.1112 | -33.1760 | 1.2782 | -33.1760 | 3.0032 | 50.8392 | -0.2351 | 56.4646 |
| 1644666 | same_delta_bucket_0509 | 11_r5_frames | short | -1.4835 | 8.0000 | -11.8681 | -5.8005 | 0.3223 | 0.3223 | -0.0000 | 49.8417 | 0.1983 | 0.1599 | -6.1532 |
| 1601635 | same_delta_bucket_0509 | 11_r5_frames | short | -0.6819 | 8.0000 | -5.4553 | -4.7702 | 1.2724 | 1.2724 | -0.0000 | 2.4031 | 0.1004 | -0.1600 | -0.3098 |
| 1616101 | focus_0509_high_chop | 10_r5_only | short | -13.5245 | 0.3750 | -5.0717 | -13.1497 | -11.8981 | 11.9122 | -24.7196 | 24.0085 | 50.9308 | 0.4609 | 10.9314 |
| 1634224 | focus_0509_high_chop | 10_r5_only | short | -1.3193 | 0.3750 | -0.4947 | -6.0644 | -0.0000 | 0.3193 | -0.0000 | 16.5158 | 0.1006 | 0.3201 | 0.0000 |
| 1620046 | focus_0509_high_chop | 10_r5_only | short | -1.1565 | 0.3750 | -0.4337 | 1.2524 | 0.9393 | 5.6370 | 0.6262 | 16.2840 | 23.4178 | 0.1589 | -9.1998 |
| 1640588 | focus_0509_high_chop | 10_r5_only | short | 2.8276 | 0.3750 | 1.0603 | -0.3189 | 5.1037 | 5.1037 | -0.0000 | 51.9972 | 0.1011 | 0.9324 | -5.7378 |
| 1643093 | focus_0509_high_chop | 10_r5_only | short | 12.6653 | 0.3750 | 4.7495 | 7.0710 | 15.1123 | 15.4341 | -0.0000 | 46.5545 | 0.1009 | 0.4270 | -30.4590 |
| 1615992 | focus_0509_high_chop | 10_r5_only | short | 18.7322 | 0.3750 | 7.0246 | 7.5117 | 21.2979 | 21.6115 | -0.0000 | 9.9063 | 0.0992 | 0.2284 | -10.4401 |
| 1612239 | focus_0509_high_chop | 10_r5_only | short | 40.3718 | 0.3750 | 15.1394 | 34.6437 | 42.7758 | 43.0887 | -0.0000 | 47.8322 | 0.0989 | 0.9166 | -14.0500 |

## Mechanism Hypotheses

1. **Concentration hypothesis**: the focus loss is primarily a sizing problem. `gamma_11` gives a single row exposure `8`, so one path reversal dominates the apparent regime failure.
2. **Same-bucket inversion hypothesis**: the local bad surface is not all high/chop. It is `11_r5_frames / short / q70_85 / delta10=s80_100` on `2026-05-09`, where every same-day matched row is negative.
3. **Exit-shape hypothesis**: the disaster row reaches positive MFE before the large MAE. That points more toward take-profit/trailing-risk research than an entry-only veto.
4. **Weak evidence warning**: the matched bucket is tiny. Excluding `2026-05-09`, the same bucket is strongly positive, mostly because of `2026-05-14`. A global ban would be post-hoc and likely destroys real right-tail exposure.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_0509_high_chop_entries_20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_0509_high_chop_controls_20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_0509_high_chop_same_bucket_20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_0509_high_chop_path_summary_20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_0509_high_chop_path_samples_20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_0509_high_chop_summary_20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_0509_high_chop_deep_dive.py
```

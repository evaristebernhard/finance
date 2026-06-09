# CCUSDT TFI Latent-State Diagnostic Panel

Status: `20260518_ccusdt_v1_tfi_latent_state_panel_v1`.

Guardrail: `research_only_prior_proxy_latent_state_diagnostic_no_execution_recommendation`.

This pass builds prior-date percentile proxies for release, absorption, exhaustion, liquidity vacuum, and chop, then checks whether the proxy mix helps explain the daily inversion variable:

$$
I_d=G_{high,d}-G_{reduce,d}.
$$

Here `high = strong_positive + positive_right_tail_fragile`, while `reduce = weak_positive_mean + avoid_or_reduce + insufficient_history` from the strict as-of entry estimator.

## Main Read

1. Entry-level latent panel rows: `1715`.
2. `2026-05-09` has `I_d=-172.4942`; `2026-05-13` has `I_d=122.3579`.
3. Best sign screen: `reduce_chop_exposure_share` with sign accuracy `0.8182` and Spearman `0.0000`.
4. Best rank-aligned contradiction screen: `high_release_exposure_share` with sign accuracy `0.6000` and Spearman `-0.5636`.
5. Scores that correctly distinguish both contradiction days: `16`; with `|Spearman| >= 0.30`: `4`.

## Contradiction Days

| date | all_total_net | high_total_net | reduce_total_net | I_high_minus_reduce | high_release_score | high_absorption_score | high_exhaustion_score | high_vacuum_score | high_chop_score | state_gap_bad_high_minus_reduce | pred_I_from_state_gap | pred_I_from_good_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | 69.0706 | -51.7118 | 120.7824 | -172.4942 | 0.5598 | 0.4775 | 0.4764 | 0.5968 | 0.4967 | -0.0113 | 1 | 1 |
| 2026-05-13 | -58.2736 | 44.0065 | -78.3514 | 122.3579 | 0.4591 | 0.4670 | 0.4993 | 0.5855 | 0.6299 | 0.0453 | -1 | -1 |

## Score Tests

| score | direction | centering | rows | spearman_I | sign_accuracy | 2026-05-09_score | 2026-05-09_centered_score | 2026-05-09_pred_sign | 2026-05-09_actual_sign | 2026-05-13_score | 2026-05-13_centered_score | 2026-05-13_pred_sign | 2026-05-13_actual_sign | distinguishes_0509_0513 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reduce_chop_exposure_share | positive_means_positive_I | expanding_prior_date_median | 11 | 0.0000 | 0.8182 | 0.1193 | -0.0422 | -1 | -1 | 0.6667 | 0.4113 | 1 | 1 | True |
| high_release_score | positive_means_negative_I | expanding_prior_date_median | 10 | -0.2848 | 0.8000 | 0.5598 | 0.0742 | -1 | -1 | 0.4591 | -0.0612 | 1 | 1 | True |
| reduce_release_exposure_share | positive_means_negative_I | expanding_prior_date_median | 11 | -0.0727 | 0.7273 | 0.3565 | 0.2100 | -1 | -1 | 0.0541 | -0.0199 | 1 | 1 | True |
| high_release_exposure_share | positive_means_negative_I | expanding_prior_date_median | 10 | -0.5636 | 0.6000 | 0.3089 | 0.3089 | -1 | -1 | 0.0000 | -0.0373 | 1 | 1 | True |
| state_gap_release_high_minus_reduce | positive_means_negative_I | expanding_prior_date_median | 10 | 0.1273 | 0.6000 | 0.0055 | 0.0030 | -1 | -1 | -0.0377 | -0.0435 | 1 | 1 | True |
| high_good_pressure_combo | positive_means_negative_I | expanding_prior_date_median | 10 | -0.1152 | 0.6000 | 0.5783 | 0.0504 | -1 | -1 | 0.5223 | -0.0260 | 1 | 1 | True |
| high_release_vacuum_minus_abs_exh_chop | positive_means_negative_I | expanding_prior_date_median | 10 | 0.0788 | 0.6000 | 0.0948 | 0.0820 | -1 | -1 | -0.0098 | -0.0692 | 1 | 1 | True |
| high_bad_state_score | positive_means_positive_I | expanding_prior_date_median | 10 | -0.0788 | 0.6000 | -0.0948 | -0.0820 | -1 | -1 | 0.0098 | 0.0692 | 1 | 1 | True |
| state_gap_exhaustion_high_minus_reduce | positive_means_positive_I | expanding_prior_date_median | 10 | 0.0667 | 0.6000 | -0.0117 | -0.0185 | -1 | -1 | 0.0333 | 0.0335 | 1 | 1 | True |
| reduce_vacuum_score | positive_means_negative_I | expanding_prior_date_median | 11 | -0.2091 | 0.5455 | 0.5898 | 0.0340 | -1 | -1 | 0.5626 | -0.0272 | 1 | 1 | True |
| reduce_vacuum_exposure_share | positive_means_negative_I | expanding_prior_date_median | 11 | -0.0273 | 0.5455 | 0.4124 | 0.1115 | -1 | -1 | 0.2523 | -0.1222 | 1 | 1 | True |
| high_vacuum_exposure_share | positive_means_negative_I | expanding_prior_date_median | 10 | 0.3939 | 0.5000 | 0.5965 | 0.0181 | -1 | -1 | 0.1616 | -0.3847 | 1 | 1 | True |
| high_vacuum_score | positive_means_negative_I | expanding_prior_date_median | 10 | 0.2848 | 0.5000 | 0.5968 | 0.0093 | -1 | -1 | 0.5855 | -0.0058 | 1 | 1 | True |
| reduce_release_score | positive_means_negative_I | expanding_prior_date_median | 11 | -0.2455 | 0.4545 | 0.5543 | 0.0535 | -1 | -1 | 0.4968 | -0.0158 | 1 | 1 | True |
| high_bad_pressure_combo | positive_means_positive_I | expanding_prior_date_median | 10 | -0.4545 | 0.4000 | 0.4836 | -0.0315 | -1 | -1 | 0.5321 | 0.0363 | 1 | 1 | True |
| state_gap_absorption_high_minus_reduce | positive_means_positive_I | expanding_prior_date_median | 10 | -0.4303 | 0.4000 | -0.0085 | -0.0249 | -1 | -1 | 0.0348 | 0.0298 | 1 | 1 | True |
| reduce_chop_score | positive_means_positive_I | expanding_prior_date_median | 11 | 0.2364 | 0.8182 | 0.4916 | 0.0029 | 1 | -1 | 0.5843 | 0.0843 | 1 | 1 | False |
| high_chop_exposure_share | positive_means_positive_I | expanding_prior_date_median | 10 | 0.2970 | 0.8000 | 0.0894 | 0.0600 | 1 | -1 | 0.8384 | 0.6825 | 1 | 1 | False |
| high_absorption_score | positive_means_negative_I | expanding_prior_date_median | 10 | -0.2121 | 0.8000 | 0.4775 | -0.0914 | 1 | -1 | 0.4670 | -0.0322 | 1 | 1 | False |
| reduce_absorption_score | positive_means_negative_I | expanding_prior_date_median | 11 | -0.3273 | 0.7273 | 0.4861 | -0.0660 | 1 | -1 | 0.4323 | -0.0677 | 1 | 1 | False |

## Dominant State On Contradiction Days

| date | quality_side | dominant_latent_state | entries | exposure | total_net | weighted_mean_net |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | high | release | 9 | 38.0000 | 158.4286 | 4.1692 |
| 2026-05-09 | high | vacuum | 32 | 73.3750 | 25.9752 | 0.3540 |
| 2026-05-09 | high | absorption | 3 | 0.6250 | -2.4959 | -3.9934 |
| 2026-05-09 | high | chop | 9 | 11.0000 | -233.6197 | -21.2382 |
| 2026-05-09 | reduce | release | 19 | 35.8750 | 79.2893 | 2.2102 |
| 2026-05-09 | reduce | vacuum | 49 | 41.5000 | 35.2755 | 0.8500 |
| 2026-05-09 | reduce | absorption | 12 | 9.3750 | 23.0015 | 2.4535 |
| 2026-05-09 | reduce | exhaustion | 5 | 1.8750 | 21.8815 | 11.6702 |
| 2026-05-09 | reduce | chop | 32 | 12.0000 | -38.6654 | -3.2221 |
| 2026-05-13 | high | vacuum | 10 | 7.3750 | 28.0061 | 3.7974 |
| 2026-05-13 | high | chop | 18 | 38.2500 | 16.0004 | 0.4183 |
| 2026-05-13 | neutral | release | 1 | 1.5000 | -23.9288 | -15.9525 |
| 2026-05-13 | reduce | release | 4 | 1.5000 | -2.8446 | -1.8964 |
| 2026-05-13 | reduce | absorption | 2 | 0.7500 | -4.0784 | -5.4378 |
| 2026-05-13 | reduce | vacuum | 18 | 7.0000 | -33.8834 | -4.8405 |
| 2026-05-13 | reduce | chop | 50 | 18.5000 | -37.5450 | -2.0295 |

## Quality X State

| quality_side | entry_quality_class | dominant_latent_state | entries | exposure | total_net | weighted_mean_net | mean_release_score | mean_absorption_score | mean_exhaustion_score | mean_vacuum_score | mean_chop_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| high | strong_positive | release | 22 | 28.7500 | 319.4474 | 11.1112 | 0.5939 | 0.3243 | 0.3601 | 0.5533 | 0.5650 |
| high | strong_positive | vacuum | 119 | 281.1250 | 2787.5988 | 9.9159 | 0.5085 | 0.3865 | 0.4397 | 0.6060 | 0.5358 |
| high | positive_right_tail_fragile | release | 43 | 51.2500 | 291.5674 | 5.6891 | 0.5909 | 0.4417 | 0.4088 | 0.5438 | 0.5073 |
| high | positive_right_tail_fragile | chop | 121 | 231.8750 | 1131.4100 | 4.8794 | 0.5077 | 0.4035 | 0.4717 | 0.5716 | 0.6345 |
| high | strong_positive | chop | 111 | 280.6250 | 1362.6483 | 4.8558 | 0.5150 | 0.3888 | 0.4559 | 0.5895 | 0.6439 |
| high | positive_right_tail_fragile | exhaustion | 3 | 0.6250 | 1.4368 | 2.2988 | 0.3901 | 0.6277 | 0.6812 | 0.5682 | 0.6203 |
| high | positive_right_tail_fragile | absorption | 15 | 5.0000 | 8.5898 | 1.7180 | 0.4850 | 0.6169 | 0.4873 | 0.5700 | 0.4172 |
| high | positive_right_tail_fragile | vacuum | 162 | 203.3750 | 315.0656 | 1.5492 | 0.5297 | 0.4414 | 0.4683 | 0.6185 | 0.5125 |
| neutral | positive_balanced | chop | 44 | 21.1250 | 94.0592 | 4.4525 | 0.4929 | 0.4408 | 0.4569 | 0.5634 | 0.6461 |
| neutral | positive_balanced | vacuum | 46 | 17.7500 | 62.4716 | 3.5195 | 0.5257 | 0.4194 | 0.4476 | 0.6376 | 0.4908 |
| neutral | positive_balanced | absorption | 7 | 2.2500 | -0.5774 | -0.2566 | 0.3975 | 0.6902 | 0.5579 | 0.5193 | 0.4640 |
| neutral | positive_balanced | release | 5 | 3.0000 | -16.8107 | -5.6036 | 0.5807 | 0.3752 | 0.3329 | 0.5328 | 0.5325 |
| reduce | weak_positive_mean | exhaustion | 6 | 2.2500 | 21.6998 | 9.6443 | 0.4339 | 0.4909 | 0.6346 | 0.5489 | 0.5595 |
| reduce | avoid_or_reduce | absorption | 76 | 52.2500 | 124.0405 | 2.3740 | 0.4619 | 0.6498 | 0.5212 | 0.5472 | 0.4531 |
| reduce | avoid_or_reduce | release | 39 | 33.1250 | 77.7781 | 2.3480 | 0.5841 | 0.4847 | 0.4358 | 0.5373 | 0.5191 |
| reduce | avoid_or_reduce | vacuum | 179 | 134.1250 | 259.6320 | 1.9357 | 0.5223 | 0.4947 | 0.4906 | 0.6357 | 0.4338 |
| reduce | weak_positive_mean | absorption | 10 | 3.7500 | 5.9471 | 1.5859 | 0.4557 | 0.6125 | 0.5126 | 0.5784 | 0.4426 |
| reduce | weak_positive_mean | release | 35 | 41.6250 | 57.1861 | 1.3738 | 0.6011 | 0.4312 | 0.4032 | 0.5505 | 0.5183 |
| reduce | weak_positive_mean | chop | 196 | 71.7500 | 27.3584 | 0.3813 | 0.4937 | 0.4197 | 0.4690 | 0.5596 | 0.6411 |
| reduce | avoid_or_reduce | chop | 184 | 147.2500 | 55.3449 | 0.3759 | 0.5117 | 0.4308 | 0.4822 | 0.5637 | 0.6362 |
| reduce | weak_positive_mean | vacuum | 222 | 98.0000 | -5.0256 | -0.0513 | 0.5354 | 0.4394 | 0.4674 | 0.6491 | 0.4909 |
| reduce | insufficient_history | release | 49 | 25.2500 | -6.6622 | -0.2638 | 0.5000 | 0.5000 | 0.5000 | 0.5000 | 0.5000 |
| reduce | avoid_or_reduce | exhaustion | 20 | 7.5000 | -3.1487 | -0.4198 | 0.4375 | 0.5424 | 0.6534 | 0.5562 | 0.5709 |
| reduce | insufficient_history | absorption | 1 | 0.2500 | -3.7598 | -15.0392 | 0.4486 | 0.6501 | 0.5695 | 0.6271 | 0.5816 |

## Interpretation

- A useful prior proxy does not need to maximize PnL in this pass; it first needs to give the correct sign for the two opposite cases: `2026-05-09` and `2026-05-13`.
- If a proxy only explains `2026-05-13`, it is probably an entry-quality or weak-bucket sizing proxy.
- If it also explains `2026-05-09`, it is closer to a true latent-regime proxy, because `2026-05-09` is the high/`11` inversion case.
- These scores are percentile diagnostics over existing pre-trade proxies. They are not calibrated posteriors and should not be used directly as live sizing.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_latent_state_panel_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_latent_state_daily_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_latent_state_quality_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_latent_state_score_tests_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_latent_state_summary_20260518_ccusdt_v1_tfi_latent_state_panel_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_latent_state_panel.py
```

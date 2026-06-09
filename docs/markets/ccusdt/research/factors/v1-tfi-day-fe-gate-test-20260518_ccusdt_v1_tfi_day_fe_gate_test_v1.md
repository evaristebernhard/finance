# CCUSDT TFI Gate Day Fixed-Effect Test

Status: `20260518_ccusdt_v1_tfi_day_fe_gate_test_v1`.

Guardrail: `research_only_day_fixed_effect_gate_test_no_execution_recommendation_no_alpha_claim`.

Test target:

$$
Y_{d,i}=\alpha_d+\beta_A A_{d,i}+\beta_B B_{d,i}+\beta_{AB}A_{d,i}B_{d,i}+\varepsilon_{d,i}.
$$

Here \(A=\mathbf{1}\{R_5>1\}\), \(B=\mathbf{1}\{frames\_since\_mid\_change\ge q90\}\). The regression is WLS using the locked strategy exposure weight.

## Coefficients

| model | term | coef_bps | robust_se_bps | t_stat | n | weight_sum |
| --- | --- | --- | --- | --- | --- | --- |
| day_fe_main_interaction | intercept | -1.5030 | 1.2101 | -1.2420 | 460 | 285.0000 |
| day_fe_main_interaction | day_0517 | 1.9806 | 1.2665 | 1.5639 | 460 | 285.0000 |
| day_fe_main_interaction | A_r5 | 1.5787 | 1.3396 | 1.1785 | 460 | 285.0000 |
| day_fe_main_interaction | B_frames_q90 | 1.8155 | 2.1698 | 0.8367 | 460 | 285.0000 |
| day_fe_main_interaction | A_x_B | 3.0019 | 3.2597 | 0.9209 | 460 | 285.0000 |

No-day-FE reference:

| model | term | coef_bps | robust_se_bps | t_stat | n | weight_sum |
| --- | --- | --- | --- | --- | --- | --- |
| no_day_fe_main_interaction | intercept | -0.7225 | 1.0351 | -0.6980 | 460 | 285.0000 |
| no_day_fe_main_interaction | A_r5 | 1.7421 | 1.3496 | 1.2908 | 460 | 285.0000 |
| no_day_fe_main_interaction | B_frames_q90 | 1.6652 | 2.1598 | 0.7710 | 460 | 285.0000 |
| no_day_fe_main_interaction | A_x_B | 3.0635 | 3.2692 | 0.9371 | 460 | 285.0000 |

## 2x2 Cells

| segment | A_r5 | B_frames_q90 | entries | exposure | total_net_bps | weighted_mean_net_bps | weighted_gt2_rate | cost_hit_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OOS_2026_05_16 | 0 | 0 | 123 | 61.5000 | -58.6411 | -0.9535 | 0.3984 | 0.5691 |
| OOS_2026_05_16 | 0 | 1 | 7 | 15.0000 | 9.8669 | 0.6578 | 0.5667 | 0.4333 |
| OOS_2026_05_16 | 1 | 0 | 117 | 61.5000 | -41.9553 | -0.6822 | 0.4065 | 0.5610 |
| OOS_2026_05_16 | 1 | 1 | 14 | 25.0000 | 129.9631 | 5.1985 | 0.3800 | 0.6200 |
| OOS_2026_05_17 | 0 | 0 | 77 | 40.0000 | -14.6896 | -0.3672 | 0.3875 | 0.5750 |
| OOS_2026_05_17 | 0 | 1 | 3 | 7.0000 | 10.8732 | 1.5533 | 0.3571 | 0.6429 |
| OOS_2026_05_17 | 1 | 0 | 106 | 56.0000 | 161.7616 | 2.8886 | 0.5268 | 0.4196 |
| OOS_2026_05_17 | 1 | 1 | 13 | 19.0000 | 122.9646 | 6.4718 | 0.7895 | 0.2105 |
| OOS_combined | 0 | 0 | 200 | 101.5000 | -73.3307 | -0.7225 | 0.3941 | 0.5714 |
| OOS_combined | 0 | 1 | 10 | 22.0000 | 20.7401 | 0.9427 | 0.5000 | 0.5000 |
| OOS_combined | 1 | 0 | 223 | 117.5000 | 119.8063 | 1.0196 | 0.4638 | 0.4936 |
| OOS_combined | 1 | 1 | 27 | 44.0000 | 252.9276 | 5.7484 | 0.5568 | 0.4432 |

## Permutation Check

Null: within each day, the future net labels are exchangeable with respect to the gates. This preserves day-level distribution and gate counts, and asks whether the observed interaction is unusually high.

| test | n_perm | observed_beta_A_x_B | perm_mean | perm_std | perm_p95 | perm_p99 | p_right_tail | p_two_sided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| within_day_shuffle_y | 5000 | 3.0019 | -0.1248 | 5.6714 | 9.4168 | 14.2769 | 0.2765 | 0.5799 |

## Read

- Day-FE interaction beta: `3.0019` bps.
- Robust t-stat: `0.9209`.
- Within-day permutation right-tail p-value: `0.2765`.
- Cell DiD, combined: `3.0635` bps; day-FE exposure-weighted day DiD: `3.1438` bps.

Result: the interaction remains positive after day fixed effects, but permutation evidence is not strong enough for a hard statistical claim. Treat it as a promising local-state effect that needs more OOS days.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_day_fe_gate_coefficients_20260518_ccusdt_v1_tfi_day_fe_gate_test_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_day_fe_gate_cells_20260518_ccusdt_v1_tfi_day_fe_gate_test_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_day_fe_gate_permutation_20260518_ccusdt_v1_tfi_day_fe_gate_test_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_day_fe_gate_summary_20260518_ccusdt_v1_tfi_day_fe_gate_test_v1.json`

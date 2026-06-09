# CCUSDT TFI Interpretable Grid Pareto

Status: `20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1`.

Guardrail: `research_only_interpretable_grid_walk_forward_pareto_no_execution_recommendation_no_alpha_claim`.

## Model Family

$$
w_t=b_t\cdot\gamma_{A_tB_t}\cdot\psi_t\cdot\phi_t
$$

$$
A_t=\mathbf{1}\{R_5>1\},\quad B_t=\mathbf{1}\{F_t\ge q_{90}\}
$$

Strength scaler:

$$
\psi_t\in\left\{1,\ \mathbf{1}\{M_t\ge Q_q^{train}(M)\},\ \psi_{\min}+(1-\psi_{\min})\operatorname{clip}\frac{M_t-Q_l^{train}}{Q_h^{train}-Q_l^{train}}\right\}
$$

Recent-loss suppressor:

$$
\phi_t=\operatorname{clip}\left(1-\eta\operatorname{clip}\frac{L_t-Q_{75}^{train}(L)}{Q_{90}^{train}(L)-Q_{75}^{train}(L)},\phi_{\min},1\right)
$$

Every train quantile is estimated only from prior dates in the main trading universe \((A_t\lor B_t)\).

## Old Main Policy Anchor

| variant_id | gamma10 | gamma01 | gamma11 | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_0.75_g01_0.25_g11_4__strength_none__loss_none | 0.7500 | 0.2500 | 4.0000 | 6808.4686 | 4.4171 | -58.2736 | 5.3985 | -58.2736 | 8 | 1418 |

## Risk-Score Leaders

| variant_id | gamma10 | gamma01 | gamma11 | strength_kind | strength_metric | strength_q_low | strength_floor | loss_kind | loss_eta | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | risk_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed10_score_abs | 0.3000 | 0.0000 | none | 0.0000 | 9001.3476 | 5.0248 | 12.8156 | 62.8010 | 0.0000 | 9 | 9001.3476 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed10_delta | 0.3000 | 0.0000 | none | 0.0000 | 8992.1508 | 5.0144 | 12.8156 | 62.8010 | 0.0000 | 9 | 8992.1508 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 1.2500 | 0.5000 | 5.0000 | hard | closed10_score_abs | 0.3000 | 0.0000 | none | 0.0000 | 8910.4685 | 5.0310 | 18.2004 | 64.2972 | 0.0000 | 9 | 8910.4685 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 1.2500 | 0.5000 | 5.0000 | hard | closed10_delta | 0.3000 | 0.0000 | none | 0.0000 | 8901.2717 | 5.0205 | 18.2004 | 59.6333 | 0.0000 | 9 | 8901.2717 |
| g00_0_g10_1.25_g01_0.25_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 1.2500 | 0.2500 | 5.0000 | hard | closed10_score_abs | 0.3000 | 0.0000 | none | 0.0000 | 8819.5895 | 5.0372 | 23.5851 | 57.4569 | 0.0000 | 9 | 8819.5895 |
| g00_0_g10_1.25_g01_0.25_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 1.2500 | 0.2500 | 5.0000 | hard | closed10_delta | 0.3000 | 0.0000 | none | 0.0000 | 8810.3927 | 5.0266 | 23.5851 | 52.7930 | 0.0000 | 9 | 8810.3927 |
| g00_0_g10_1.25_g01_0_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 1.2500 | 0.0000 | 5.0000 | hard | closed10_score_abs | 0.3000 | 0.0000 | none | 0.0000 | 8728.7105 | 5.0437 | 28.9698 | 50.6167 | 0.0000 | 9 | 8728.7105 |
| g00_0_g10_1.25_g01_0_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 1.2500 | 0.0000 | 5.0000 | hard | closed10_delta | 0.3000 | 0.0000 | none | 0.0000 | 8719.5137 | 5.0329 | 28.9698 | 45.9528 | 0.0000 | 9 | 8719.5137 |
| g00_0_g10_1_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 1.0000 | 0.7500 | 5.0000 | hard | closed10_score_abs | 0.3000 | 0.0000 | none | 0.0000 | 8684.4348 | 5.1979 | 32.7438 | 36.0797 | 0.0000 | 9 | 8684.4348 |
| g00_0_g10_1_g01_0.75_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 1.0000 | 0.7500 | 5.0000 | hard | closed10_delta | 0.3000 | 0.0000 | none | 0.0000 | 8676.2642 | 5.1868 | 31.9533 | 32.3485 | 0.0000 | 9 | 8676.2642 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.2__loss_none | 1.2500 | 0.5000 | 5.0000 | hard | closed10_score_abs | 0.2000 | 0.0000 | none | 0.0000 | 8688.0630 | 4.5484 | -5.9465 | 73.9966 | -5.9465 | 8 | 8628.5982 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.2__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed10_score_abs | 0.2000 | 0.0000 | none | 0.0000 | 8755.9422 | 4.5166 | -13.5365 | 66.6767 | -13.5365 | 8 | 8620.5777 |
| g00_0_g10_1.25_g01_0.25_g11_5__hard_closed10_score_abs_ge_q0.2__loss_none | 1.2500 | 0.2500 | 5.0000 | hard | closed10_score_abs | 0.2000 | 0.0000 | none | 0.0000 | 8620.1839 | 4.5812 | 1.6435 | 81.3166 | 0.0000 | 9 | 8620.1839 |
| g00_0_g10_1_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 1.0000 | 0.5000 | 5.0000 | hard | closed10_score_abs | 0.3000 | 0.0000 | none | 0.0000 | 8593.5558 | 5.2066 | 20.3503 | 29.2394 | 0.0000 | 9 | 8593.5558 |
| g00_0_g10_1_g01_0.5_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 1.0000 | 0.5000 | 5.0000 | hard | closed10_delta | 0.3000 | 0.0000 | none | 0.0000 | 8585.3852 | 5.1954 | 12.8880 | 25.5082 | 0.0000 | 9 | 8585.3852 |

## Total Leaders

| variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 9123.4940 | 4.1449 | -167.3131 | -16.2844 | -167.3131 | 8 | 2201.1250 |
| g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 9022.0597 | 4.1936 | -139.6038 | 1.1584 | -139.6038 | 8 | 2151.3750 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 9001.3476 | 5.0248 | 12.8156 | 62.8010 | 0.0000 | 9 | 1791.3750 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 8992.1508 | 5.0144 | 12.8156 | 62.8010 | 0.0000 | 9 | 1793.2500 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 8963.3930 | 4.2355 | -73.0906 | 34.5714 | -73.0906 | 8 | 2116.2500 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 8926.2150 | 4.3023 | -85.6649 | 15.6587 | -85.6649 | 8 | 2074.7500 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 8923.9538 | 4.2678 | -72.5666 | 34.8334 | -72.5666 | 8 | 2091.0000 |
| g00_0_g10_1.25_g01_0.25_g11_5__strength_none__loss_none | 8920.6255 | 4.2446 | -111.8946 | 18.6013 | -111.8946 | 8 | 2101.6250 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 8910.4685 | 5.0310 | 18.2004 | 64.2972 | 0.0000 | 9 | 1771.1250 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_delta_ge_q0.3__loss_none | 8901.2717 | 5.0205 | 18.2004 | 59.6333 | 0.0000 | 9 | 1773.0000 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 8896.0004 | 4.3002 | -85.6649 | 15.6587 | -85.6649 | 8 | 2068.7500 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 8888.8924 | 4.3014 | -85.1718 | 22.4539 | -85.1718 | 8 | 2066.5000 |

## Worst-Day Leaders

| variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.4__loss_none | 7194.7811 | 4.4269 | 81.4643 | 82.4052 | 0.0000 | 9 | 1625.2500 |
| g00_0_g10_1.25_g01_0_g11_4__hard_closed10_score_abs_ge_q0.4__loss_none | 5828.4931 | 4.2497 | 80.2647 | 91.2833 | 0.0000 | 9 | 1371.5000 |
| g00_0_g10_1.25_g01_0_g11_4__hard_closed10_delta_ge_q0.4__loss_none | 5926.8808 | 4.3203 | 79.5983 | 98.6729 | 0.0000 | 9 | 1371.8750 |
| g00_0_g10_1.25_g01_0.25_g11_4__hard_closed10_delta_ge_q0.4__loss_none | 5994.7084 | 4.3190 | 78.0822 | 94.4523 | 0.0000 | 9 | 1388.0000 |
| g00_0_g10_1.25_g01_0.5_g11_4__hard_closed10_delta_ge_q0.4__loss_none | 6062.5360 | 4.3177 | 76.5661 | 90.2318 | 0.0000 | 9 | 1404.1250 |
| g00_0_g10_1.25_g01_0.75_g11_4__hard_closed10_delta_ge_q0.4__loss_none | 6130.3637 | 4.3164 | 75.0500 | 86.0113 | 0.0000 | 9 | 1420.2500 |
| g00_0_g10_1.25_g01_0.25_g11_4__hard_closed10_score_abs_ge_q0.4__loss_none | 5891.9865 | 4.2427 | 74.4144 | 84.8957 | 0.0000 | 9 | 1388.7500 |
| g00_0_g10_1.25_g01_0.5_g11_5__ramp_closed10_score_abs_q0.3_0.5_floor0__loss_none | 7089.1528 | 4.4746 | 71.7433 | 75.6528 | 0.0000 | 9 | 1584.3164 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_delta_ge_q0.4__loss_none | 7126.9534 | 4.4291 | 71.5184 | 80.8948 | 0.0000 | 9 | 1609.1250 |
| g00_0_g10_1.25_g01_0.5_g11_4__hard_closed10_score_abs_ge_q0.4__loss_none | 5955.4800 | 4.2358 | 68.5641 | 78.5081 | 0.0000 | 9 | 1406.0000 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_score_abs_q0.3_0.5_floor0__loss_none | 7160.5384 | 4.4728 | 68.2712 | 74.2008 | 0.0000 | 9 | 1600.9190 |
| g00_0_g10_1.25_g01_0.5_g11_5__ramp_closed10_delta_q0.3_0.5_floor0__loss_none | 7225.9294 | 4.5276 | 67.6226 | 73.0438 | 0.0000 | 9 | 1595.9560 |

## Pareto Frontier: Total vs Worst Day

| pareto_rank_total_desc | variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 9123.4940 | 4.1449 | -167.3131 | -16.2844 | -167.3131 | 8 | 2201.1250 |
| 2 | g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 9022.0597 | 4.1936 | -139.6038 | 1.1584 | -139.6038 | 8 | 2151.3750 |
| 3 | g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 9001.3476 | 5.0248 | 12.8156 | 62.8010 | 0.0000 | 9 | 1791.3750 |
| 4 | g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 8910.4685 | 5.0310 | 18.2004 | 64.2972 | 0.0000 | 9 | 1771.1250 |
| 5 | g00_0_g10_1.25_g01_0.25_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 8819.5895 | 5.0372 | 23.5851 | 57.4569 | 0.0000 | 9 | 1750.8750 |
| 6 | g00_0_g10_1.25_g01_0_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 8728.7105 | 5.0437 | 28.9698 | 50.6167 | 0.0000 | 9 | 1730.6250 |
| 7 | g00_0_g10_1_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.3__loss_none | 8684.4348 | 5.1979 | 32.7438 | 36.0797 | 0.0000 | 9 | 1670.7500 |
| 8 | g00_0_g10_1_g01_0_g11_5__hard_closed10_score_abs_ge_q0.2__loss_none | 8226.1823 | 4.7757 | 33.1088 | 71.4091 | 0.0000 | 9 | 1722.5000 |
| 9 | g00_0_g10_1_g01_0_g11_5__hard_closed10_delta_ge_q0.2__loss_none | 8221.4947 | 4.7897 | 37.0600 | 70.2614 | 0.0000 | 9 | 1716.5000 |
| 10 | g00_0_g10_0.75_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.2__loss_none | 8035.8183 | 4.8735 | 41.8043 | 43.0174 | 0.0000 | 9 | 1648.8750 |
| 11 | g00_0_g10_1.25_g01_0.5_g11_5__ramp_closed10_delta_q0.2_0.5_floor0__loss_none | 7781.2155 | 4.6419 | 43.4629 | 72.0676 | 0.0000 | 9 | 1676.3049 |
| 12 | g00_0_g10_1.25_g01_0.5_g11_5__ramp_closed10_score_abs_q0.2_0.5_floor0__loss_none | 7717.7259 | 4.5921 | 46.5386 | 74.5605 | 0.0000 | 9 | 1680.6556 |
| 13 | g00_0_g10_1.25_g01_0.25_g11_5__ramp_closed10_delta_q0.2_0.5_floor0__loss_none | 7706.1724 | 4.6493 | 48.9284 | 67.2508 | 0.0000 | 9 | 1657.4812 |
| 14 | g00_0_g10_1.25_g01_0.25_g11_5__ramp_closed10_score_abs_q0.2_0.5_floor0__loss_none | 7643.8933 | 4.6009 | 51.3466 | 80.4427 | 0.0000 | 9 | 1661.3954 |
| 15 | g00_0_g10_1.25_g01_0_g11_5__ramp_closed10_delta_q0.2_0.5_floor0__loss_none | 7631.1293 | 4.6569 | 54.3938 | 62.4341 | 0.0000 | 9 | 1638.6574 |
| 16 | g00_0_g10_1.25_g01_0_g11_5__ramp_closed10_score_abs_q0.2_0.5_floor0__loss_none | 7570.0608 | 4.6099 | 56.1545 | 79.5634 | 0.0000 | 9 | 1642.1352 |
| 17 | g00_0_g10_1_g01_0.75_g11_5__ramp_closed10_score_abs_q0.2_0.5_floor0__loss_none | 7480.1842 | 4.7202 | 56.3432 | 57.7303 | 0.0000 | 9 | 1584.7159 |
| 18 | g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.3_0.5_floor0__loss_none | 7297.9640 | 4.5257 | 64.2826 | 72.8307 | 0.0000 | 9 | 1612.5704 |
| 19 | g00_0_g10_1.25_g01_0.5_g11_5__ramp_closed10_delta_q0.3_0.5_floor0__loss_none | 7225.9294 | 4.5276 | 67.6226 | 73.0438 | 0.0000 | 9 | 1595.9560 |
| 20 | g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.4__loss_none | 7194.7811 | 4.4269 | 81.4643 | 82.4052 | 0.0000 | 9 | 1625.2500 |

## Read

This is an interpretable frontier, not a black-box model. The old coefficient vector is included as an anchor, but the frontier lets the absolute-strength scaler and recent-loss suppressor compete jointly with the four state gammas.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_variants_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_pareto_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_daily_top_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv`

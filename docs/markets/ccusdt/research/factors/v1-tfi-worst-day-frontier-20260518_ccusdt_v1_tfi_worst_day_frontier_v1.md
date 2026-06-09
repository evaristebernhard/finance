# CCUSDT TFI Worst-Day Frontier

Status: `20260518_ccusdt_v1_tfi_worst_day_frontier_v1`.

Guardrail: `research_only_pretrade_worst_day_frontier_no_execution_recommendation_no_alpha_claim`.

## Decomposition

$$
R_5=\frac{P_5}{N_5},\quad \Delta_5=P_5-N_5,\quad E_5=P_5+N_5,\quad \rho_5=\frac{\Delta_5}{E_5+\epsilon}
$$

`R5` is a shape ratio. `Delta5` is absolute cushion; `E5` is recent realized energy. A high ratio with low absolute cushion should not get the same risk budget as high ratio with large cushion.

Target policy for this frontier:

$$
(\gamma_{00},\gamma_{10},\gamma_{01},\gamma_{11})=(0,0.75,0.25,4)
$$

## Baseline

| gate | test_days | positive_days | entries | exposure | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no_extra_gate | 9 | 8 | 1418 | 1541.3750 | 6808.4686 | 4.4171 | -58.2736 | 5.3985 | -58.2736 |

## Best Worst-Day Frontier

| gate | test_days | positive_days | entries | exposure | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| closed10_score_abs_ge_q0.2 | 9 | 9 | 1218 | 1380.3750 | 6583.6006 | 4.7694 | 23.6722 | 52.8567 | 0.0000 |
| closed5_delta_ge_q0.3_and_energy_ge_q0.1 | 9 | 9 | 1111 | 1309.2500 | 6410.2836 | 4.8961 | 23.6318 | 28.5189 | 0.0000 |
| closed5_delta_ge_q0.4_and_energy_ge_q0.1 | 9 | 9 | 1012 | 1191.1250 | 5820.3711 | 4.8864 | 20.2087 | 20.2374 | 0.0000 |
| closed5_delta_ge_q0.3 | 9 | 9 | 1142 | 1337.3750 | 6542.6817 | 4.8922 | 14.1354 | 22.9432 | 0.0000 |
| closed5_delta_ge_q0.4 | 9 | 9 | 1026 | 1211.2500 | 5918.7110 | 4.8864 | 13.7095 | 17.6405 | 0.0000 |
| closed10_delta_ge_q0.2 | 9 | 9 | 1205 | 1374.1250 | 6570.4846 | 4.7816 | 13.7046 | 47.7516 | 0.0000 |
| closed5_score_abs_ge_q0.3 | 9 | 9 | 1115 | 1303.6250 | 6355.6164 | 4.8753 | 12.8663 | 19.2507 | 0.0000 |
| closed5_score_abs_ge_q0.4 | 9 | 9 | 987 | 1133.6250 | 5310.4195 | 4.6845 | 6.8577 | 10.8127 | 0.0000 |
| closed5_score_abs_ge_q0.2 | 9 | 9 | 1217 | 1417.6250 | 6657.2580 | 4.6961 | 1.5644 | 28.5941 | 0.0000 |
| closed5_rho_ge_q0.3 | 9 | 9 | 1076 | 1234.3750 | 5313.1813 | 4.3043 | 0.4826 | 17.5448 | 0.0000 |
| closed5_rho_ge_q0.2 | 9 | 8 | 1204 | 1397.3750 | 6391.4719 | 4.5739 | -1.3990 | 19.0091 | -1.3990 |
| closed5_delta_ge_q0.3_and_energy_ge_q0.3 | 9 | 8 | 1012 | 1206.3750 | 6483.8370 | 5.3746 | -4.3543 | 10.2183 | -4.3543 |

## Balanced Frontier

| gate | test_days | positive_days | entries | exposure | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | frontier_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| closed10_score_abs_ge_q0.3 | 9 | 8 | 1116 | 1284.1250 | 6756.9347 | 5.2619 | -13.1677 | 12.2758 | -13.1677 | 18.5124 |
| closed10_score_abs_ge_q0.2 | 9 | 9 | 1218 | 1380.3750 | 6583.6006 | 4.7694 | 23.6722 | 52.8567 | 0.0000 | 18.4101 |
| closed10_delta_ge_q0.3 | 9 | 8 | 1116 | 1285.7500 | 6750.6034 | 5.2503 | -18.7644 | 9.4774 | -18.7644 | 18.3762 |
| closed5_delta_ge_q0.2_and_energy_ge_q0.3 | 9 | 7 | 1056 | 1247.2500 | 6555.4437 | 5.2559 | -4.4566 | -4.1273 | -4.4566 | 18.2777 |
| closed5_delta_ge_q0.3 | 9 | 9 | 1142 | 1337.3750 | 6542.6817 | 4.8922 | 14.1354 | 22.9432 | 0.0000 | 18.2603 |
| closed5_delta_ge_q0.3_and_energy_ge_q0.3 | 9 | 8 | 1012 | 1206.3750 | 6483.8370 | 5.3746 | -4.3543 | 10.2183 | -4.3543 | 18.2552 |
| closed10_delta_ge_q0.2 | 9 | 9 | 1205 | 1374.1250 | 6570.4846 | 4.7816 | 13.7046 | 47.7516 | 0.0000 | 18.1966 |
| closed5_delta_ge_q0.3_and_energy_ge_q0.1 | 9 | 9 | 1111 | 1309.2500 | 6410.2836 | 4.8961 | 23.6318 | 28.5189 | 0.0000 | 18.1894 |
| closed5_delta_ge_q0.1_and_energy_ge_q0.3 | 9 | 7 | 1111 | 1295.5000 | 6623.6387 | 5.1128 | -8.7114 | -6.1922 | -8.7114 | 18.1859 |
| closed5_score_abs_ge_q0.2 | 9 | 9 | 1217 | 1417.6250 | 6657.2580 | 4.6961 | 1.5644 | 28.5941 | 0.0000 | 18.0419 |
| closed5_energy_ge_q0.3 | 9 | 7 | 1180 | 1323.8750 | 6683.6199 | 5.0485 | -20.7492 | -14.9804 | -20.7492 | 18.0008 |
| closed5_delta_ge_q0.3_and_energy_ge_q0.2 | 9 | 8 | 1072 | 1266.1250 | 6439.4550 | 5.0860 | -4.6225 | 12.0972 | -4.6225 | 17.8724 |

## Worst Date Diagnostics: 2026-05-13

| date | cell | entries | exposure | total_net | mean_net | mean_closed5_delta | mean_closed5_energy | mean_closed5_rho | low_abs_cushion_share | low_energy_share | high_recent_loss_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-13 | 10_r5_only | 78 | 31.5000 | -110.3517 | -3.5032 | 12.7410 | 31.4264 | 0.3821 | 0.0897 | 0.1154 | 0.3462 |
| 2026-05-13 | 01_frames_only | 20 | 9.3750 | -27.7092 | -2.9556 | -16.1876 | 45.7730 | -0.5206 | 1.0000 | 0.1500 | 0.7000 |
| 2026-05-13 | 11_r5_frames | 5 | 34.0000 | 79.7873 | 2.3467 | 21.6066 | 43.1800 | 0.5411 | 0.0000 | 0.0000 | 0.4000 |

## Fragility Thresholds

| closed5_delta_q25_train | closed5_energy_q25_train | closed5_loss_abs_max_q75_train |
| --- | --- | --- |
| 1.6254 | 15.6390 | 7.0997 |

## Read

The largest failure mode is not that `R5` is false; it is that `R5` has no absolute scale. The proposed next layer is therefore a risk-budget scaler based on `Delta5` and `E5`, not a replacement for the TFI state.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_worst_day_frontier_20260518_ccusdt_v1_tfi_worst_day_frontier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_worst_day_daily_20260518_ccusdt_v1_tfi_worst_day_frontier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_worst_day_diagnostics_20260518_ccusdt_v1_tfi_worst_day_frontier_v1.csv`

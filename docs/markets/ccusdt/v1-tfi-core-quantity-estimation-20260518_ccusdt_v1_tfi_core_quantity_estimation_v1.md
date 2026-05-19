# CCUSDT TFI Core Quantity Estimation

Status: `20260518_ccusdt_v1_tfi_core_quantity_estimation_v1`.

Guardrail: `research_only_core_quantity_estimation_no_execution_recommendation_no_alpha_claim`.

This report estimates pressure/absorption quantities for the TFI branch. The quantities are computed from current and prior order-book/order-flow state; future gross/net labels are used only after the fact to inspect payoff shape.

## Model

The working first-principles model is:

$$
r_{t,t+h}=d_t\lambda_t\left(X_t-\Theta_t\right)^++\epsilon_t,
$$

where $d_t\in\{-1,+1\}$ is the entry direction, $X_t$ is accumulated same-direction flow pressure, $\Theta_t$ is the same-side book's absorption threshold, and $\lambda_t$ is pressure-to-price conversion.

Estimated quantities:

- $X_t=z(d_t\cdot EMA_{25}(TFI_t))$.
- $\Theta_t=0.8z(oppDepth_5)+0.5z(oppReplenish)+0.3z(spread)-0.7z(oppDepletion)$.
- $\log U_t=X_t-\Theta_t$, so $U_t=\exp(\log U_t)$ is a robust-scale release ratio.
- $A_t=X_t+0.7z(oppReplenish)+0.4z(oppDepth_5)-0.7(P_t)^+-0.3z(oppDepletion)$.
- $E_t=(P_t)^++0.5z(spread)+0.3z(liquidityShock)-0.6(X_t)^+$.
- $C_t=0.6z(d_tMLOFI_{1})+0.4z(d_tOFI_1)$.

Here $P_t=z(d_t r_{t-25,t})$ is already-released same-direction price movement. Normalization uses expanding prior panel rows by date and direction; if insufficient, it falls back to the same-direction panel distribution.

## Scope

- Entry rows: `3365`.
- Date range: `2026-05-04` to `2026-05-17`.
- Merged event-panel coverage: `1.0000`.
- Short entries: `1875`; long entries: `1490`.

## Main Read

1. The strongest positive diagnostic is `lambda_prior_top_u` with top-bottom net `2.6073` bps and Spearman `0.0689`.
2. The best joint bucket is `cell_11_low_U`: entries `70`, mean net `9.0915` bps, q90 `23.0514` bps, CVaR5 `-37.9333` bps.
3. Directional conversion remains asymmetric: short mean net `1.8462` bps versus long mean net `0.9838` bps in this entry universe.
4. These are state estimates, not a final strategy. The useful next step is to use $X_t,\Theta_t,U_t,A_t,E_t,C_t$ as decomposition controls around the existing TFI cells, while not assuming that high $U_t$ or high $C_t$ alone is sufficient.

## Single-Quantity Scorecard

| feature | rows | spearman_net | top_entries | top_mean_net_bps | bottom_mean_net_bps | top_bottom_net_bps | top_gt2_rate | top_cvar05_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lambda_prior_top_u | 3205 | 0.0689 | 775 | 3.2735 | 0.6663 | 2.6073 | 0.4735 | -36.4589 |
| log_U_t | 3365 | 0.0623 | 673 | 1.6011 | -0.9170 | 2.5180 | 0.3982 | -40.6242 |
| X_t | 3365 | 0.0555 | 673 | 1.5711 | -0.7962 | 2.3673 | 0.3938 | -40.1255 |
| A_absorption_t | 3365 | 0.0524 | 673 | 1.5303 | -0.6923 | 2.2227 | 0.3863 | -40.1255 |
| D_divergence_t | 3365 | 0.0266 | 673 | 1.0333 | 0.6408 | 0.3925 | 0.3804 | -39.3816 |
| release_score_t | 3365 | -0.0027 | 673 | 1.4535 | 1.4168 | 0.0366 | 0.3358 | -30.8805 |
| C_confirm_t | 3365 | -0.0161 | 673 | 0.7206 | 2.0409 | -1.3203 | 0.3210 | -29.4236 |
| E_exhaustion_t | 3365 | -0.0508 | 673 | 0.1575 | 1.6604 | -1.5029 | 0.3388 | -32.9004 |
| Theta_t | 3365 | -0.1447 | 673 | -0.2688 | 5.4801 | -5.7489 | 0.2972 | -20.7689 |

## Joint Buckets

| bucket | entries | short_entries | long_entries | exposure | net_mean_bps | net_median_bps | gt2_rate | q90_net_bps | cvar05_net_bps | total_weighted_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cell_11_low_U | 70 | 40 | 30 | 112.0000 | 9.0915 | 5.3145 | 0.6000 | 23.0514 | -37.9333 | 1018.2504 |
| cell_11_low_A | 83 | 50 | 33 | 136.5000 | 8.7698 | 4.5627 | 0.5783 | 31.4074 | -36.2624 | 1197.0771 |
| cell_11_low_C | 91 | 45 | 46 | 134.5000 | 6.3503 | 2.8443 | 0.5275 | 18.4717 | -29.2911 | 854.1158 |
| cell_11_low_Theta | 128 | 80 | 48 | 213.0000 | 5.6609 | 3.4505 | 0.5547 | 22.5181 | -32.4252 | 1205.7653 |
| low_Theta | 673 | 403 | 270 | 482.0000 | 5.4801 | 3.2637 | 0.5527 | 28.0789 | -47.3607 | 2641.4202 |
| cell_11_all | 178 | 101 | 77 | 284.5000 | 5.1410 | 3.2773 | 0.5562 | 17.6266 | -28.4984 | 1462.6178 |
| cell_11_high_Theta | 32 | 12 | 20 | 43.5000 | 4.4859 | 3.1731 | 0.5312 | 11.7943 | -6.9956 | 195.1366 |
| high_X_low_Theta | 601 | 362 | 239 | 371.0000 | 2.5962 | -0.6760 | 0.4526 | 22.0651 | -41.3322 | 963.2010 |
| low_C_confirm | 673 | 365 | 308 | 450.0000 | 2.0409 | -0.8412 | 0.4027 | 14.8049 | -37.3359 | 918.3910 |
| low_E | 673 | 398 | 275 | 388.5000 | 1.6604 | -1.1714 | 0.3952 | 18.0972 | -40.1255 | 645.0763 |
| high_U | 673 | 402 | 271 | 394.0000 | 1.6011 | -1.1685 | 0.3982 | 18.0972 | -40.6242 | 630.8232 |
| high_X | 673 | 400 | 273 | 390.5000 | 1.5711 | -1.1699 | 0.3938 | 18.0972 | -40.1255 | 613.5217 |
| cell_11_high_A | 37 | 19 | 18 | 55.5000 | 1.4400 | 3.6375 | 0.6486 | 10.5538 | -20.0953 | 79.9188 |
| high_U_low_E | 1010 | 585 | 425 | 597.5000 | 1.4372 | -1.0000 | 0.4040 | 16.5399 | -37.2394 | 858.7476 |
| high_U_confirmed | 139 | 78 | 61 | 91.0000 | 1.2931 | -0.2027 | 0.4532 | 24.1004 | -54.6789 | 117.6745 |
| high_U_low_confirm | 723 | 412 | 311 | 406.5000 | 1.2399 | -1.3197 | 0.3859 | 15.5145 | -36.2700 | 504.0108 |
| cell_11_high_U | 38 | 19 | 19 | 56.5000 | 1.1277 | 3.0823 | 0.5789 | 10.4651 | -20.0953 | 63.7127 |
| high_C_confirm | 673 | 337 | 336 | 350.0000 | 0.7206 | -1.6547 | 0.3210 | 10.6376 | -29.4236 | 252.2081 |
| high_E | 673 | 355 | 318 | 341.0000 | 0.1575 | -1.6547 | 0.3388 | 10.5255 | -32.9004 | 53.7205 |
| low_U_or_exhausted | 1035 | 528 | 507 | 523.5000 | -0.0383 | -1.6483 | 0.3304 | 10.9634 | -31.0981 | -20.0530 |

## Direction Split

| direction | entries | exposure | net_mean_bps | net_median_bps | gt2_rate | q90_net_bps | cvar05_net_bps | median_X_t | median_Theta_t | median_log_U_t | median_E_exhaustion_t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| -1.0000 | 1875.0000 | 1336.5000 | 1.8462 | -1.0000 | 0.4064 | 15.2166 | -28.5289 | 11.1536 | -0.3509 | 12.8981 | -6.7972 |
| 1.0000 | 1490.0000 | 776.0000 | 0.9838 | -1.1684 | 0.3725 | 12.1270 | -32.8583 | 9.3840 | -0.2841 | 10.1544 | -5.5226 |

## Prior Lambda Estimates

| date | direction | prior_entries | lambda_top_u_gross_per_logu | lambda_top_x_gross_per_x | top_u_mean_gross | top_x_mean_gross |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-08 | -1 | 378 | 0.0184 | 0.0177 | 1.1851 | 1.1318 |
| 2026-05-08 | 1 | 402 | 0.0104 | 0.0105 | 0.7236 | 0.7236 |
| 2026-05-09 | -1 | 432 | 0.0223 | 0.0240 | 1.6051 | 1.7161 |
| 2026-05-09 | 1 | 456 | 0.0122 | 0.0105 | 0.9638 | 0.8232 |
| 2026-05-10 | -1 | 626 | 0.0283 | 0.0284 | 3.6893 | 3.6656 |
| 2026-05-10 | 1 | 541 | 0.0352 | 0.0372 | 3.0005 | 3.1443 |
| 2026-05-11 | -1 | 748 | 0.0359 | 0.0331 | 4.5076 | 4.1217 |
| 2026-05-11 | 1 | 652 | 0.0335 | 0.0345 | 2.9512 | 3.0139 |
| 2026-05-12 | -1 | 958 | 0.0315 | 0.0309 | 3.6735 | 3.5683 |
| 2026-05-12 | 1 | 783 | 0.0366 | 0.0372 | 3.0227 | 3.0510 |
| 2026-05-13 | -1 | 1092 | 0.0346 | 0.0353 | 3.7715 | 3.8036 |
| 2026-05-13 | 1 | 869 | 0.0328 | 0.0317 | 2.7419 | 2.6259 |
| 2026-05-14 | -1 | 1236 | 0.0358 | 0.0358 | 3.6507 | 3.6129 |
| 2026-05-14 | 1 | 973 | 0.0337 | 0.0325 | 2.6895 | 2.5681 |
| 2026-05-15 | -1 | 1451 | 0.0395 | 0.0401 | 3.8243 | 3.8305 |
| 2026-05-15 | 1 | 1139 | 0.0432 | 0.0430 | 3.2133 | 3.1604 |
| 2026-05-16 | -1 | 1631 | 0.0411 | 0.0416 | 3.7141 | 3.7112 |
| 2026-05-16 | 1 | 1274 | 0.0545 | 0.0548 | 3.8694 | 3.8394 |
| 2026-05-17 | -1 | 1759 | 0.0410 | 0.0407 | 3.5331 | 3.4690 |
| 2026-05-17 | 1 | 1407 | 0.0498 | 0.0517 | 3.3596 | 3.4352 |

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_core_quantity_scored_entries_20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_core_quantity_scorecard_20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_core_quantity_joint_bins_20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_core_quantity_direction_20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_core_quantity_lambda_20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_core_quantity_summary_20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_core_quantity_estimation.py
```

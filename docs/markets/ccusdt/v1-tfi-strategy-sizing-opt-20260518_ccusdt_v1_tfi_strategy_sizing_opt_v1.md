# CCUSDT TFI Strategy Sizing Optimization

Status: `20260518_ccusdt_v1_tfi_strategy_sizing_opt_v1`.

Guardrail: `research_only_walk_forward_sizing_optimization_no_execution_recommendation_no_alpha_claim`.

State layers:

$$
\gamma_t = \begin{cases}
\gamma_2, & R_5>1,\ frames\ge q90 \\
\gamma_1, & R_5>1 \\
\gamma_0, & \mathrm{otherwise}
\end{cases}
$$

The walk-forward loop chooses \((\gamma_0,\gamma_1,\gamma_2)\) using only prior dates, then evaluates the next date.

## In-Sample Variant Frontier

| variant | gamma0_base | gamma1_broad | gamma2_strict | entries | exposure | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_day_count | risk_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| grid_g0_0_g1_0.75_g2_4 | 0.0000 | 0.7500 | 4.0000 | 1558 | 1679.1250 | 6852.3011 | 4.0809 | -30.5644 | -20.8621 | -32.0219 | 10 | 13.5642 |
| grid_g0_0_g1_1_g2_4 | 0.0000 | 1.0000 | 4.0000 | 1558 | 1859.5000 | 7186.2444 | 3.8646 | -67.3483 | -36.3562 | -67.3483 | 10 | 13.4572 |
| grid_g0_0_g1_1.25_g2_4 | 0.0000 | 1.2500 | 4.0000 | 1558 | 2039.8750 | 7520.1878 | 3.6866 | -104.1322 | -53.5674 | -104.1322 | 10 | 13.3884 |
| grid_g0_0_g1_1.5_g2_4 | 0.0000 | 1.5000 | 4.0000 | 1558 | 2220.2500 | 7854.1311 | 3.5375 | -140.9161 | -70.8856 | -140.9161 | 9 | 13.3485 |
| grid_g0_0_g1_2_g2_4 | 0.0000 | 2.0000 | 4.0000 | 1558 | 2581.0000 | 8522.0177 | 3.3018 | -214.4840 | -105.5219 | -214.4840 | 9 | 13.3313 |
| grid_g0_0.25_g1_2_g2_4 | 0.2500 | 2.0000 | 4.0000 | 3365 | 2857.6250 | 8630.1479 | 3.0200 | -228.5646 | -125.3316 | -228.5646 | 9 | 13.0632 |
| grid_g0_0.25_g1_0.75_g2_4 | 0.2500 | 0.7500 | 4.0000 | 3365 | 1955.7500 | 6960.4312 | 3.5590 | -44.6451 | -39.2848 | -69.9326 | 10 | 13.0560 |
| grid_g0_0.25_g1_1_g2_4 | 0.2500 | 1.0000 | 4.0000 | 3365 | 2136.1250 | 7294.3746 | 3.4148 | -81.4290 | -56.4941 | -83.7579 | 9 | 13.0210 |
| grid_g0_0.25_g1_1.5_g2_4 | 0.2500 | 1.5000 | 4.0000 | 3365 | 2496.8750 | 7962.2612 | 3.1889 | -154.9968 | -90.9128 | -154.9968 | 9 | 13.0136 |
| grid_g0_0.25_g1_1.25_g2_4 | 0.2500 | 1.2500 | 4.0000 | 3365 | 2316.5000 | 7628.3179 | 3.2930 | -118.2129 | -73.7035 | -118.2129 | 9 | 13.0085 |
| grid_g0_0.5_g1_2_g2_4 | 0.5000 | 2.0000 | 4.0000 | 3365 | 3134.2500 | 8738.2780 | 2.7880 | -242.6452 | -146.9870 | -242.6452 | 9 | 12.8448 |
| grid_g0_0.5_g1_1.5_g2_4 | 0.5000 | 1.5000 | 4.0000 | 3365 | 2773.5000 | 8070.3913 | 2.9098 | -169.0774 | -112.5682 | -187.8225 | 9 | 12.7482 |
| grid_g0_0.5_g1_1.25_g2_4 | 0.5000 | 1.2500 | 4.0000 | 3365 | 2593.1250 | 7736.4480 | 2.9834 | -132.2935 | -95.3589 | -165.5881 | 9 | 12.7126 |
| grid_g0_0.5_g1_1_g2_4 | 0.5000 | 1.0000 | 4.0000 | 3365 | 2412.7500 | 7402.5047 | 3.0681 | -95.5096 | -78.1495 | -143.3537 | 9 | 12.6880 |
| grid_g0_0.75_g1_2_g2_4 | 0.7500 | 2.0000 | 4.0000 | 3365 | 3410.8750 | 8846.4081 | 2.5936 | -256.7258 | -168.6424 | -291.8870 | 9 | 12.6641 |
| grid_g0_0.5_g1_0.75_g2_4 | 0.5000 | 0.7500 | 4.0000 | 3365 | 2232.3750 | 7068.5614 | 3.1664 | -66.6893 | -60.9402 | -121.1193 | 9 | 12.5974 |
| grid_g0_0.75_g1_1.5_g2_4 | 0.7500 | 1.5000 | 4.0000 | 3365 | 3050.1250 | 8178.5215 | 2.6814 | -183.1580 | -134.2236 | -247.4182 | 9 | 12.5334 |
| grid_g0_1_g1_2_g2_4 | 1.0000 | 2.0000 | 4.0000 | 3365 | 3687.5000 | 8954.5382 | 2.4283 | -270.8065 | -190.2977 | -351.4828 | 9 | 12.5125 |
| grid_g0_0.75_g1_1.25_g2_4 | 0.7500 | 1.2500 | 4.0000 | 3365 | 2869.7500 | 7844.5781 | 2.7335 | -146.3741 | -117.0143 | -225.1839 | 9 | 12.4763 |
| grid_g0_0.75_g1_1_g2_4 | 0.7500 | 1.0000 | 4.0000 | 3365 | 2689.3750 | 7510.6348 | 2.7927 | -109.5902 | -99.8049 | -202.9495 | 9 | 12.4263 |

## Walk-Forward Daily Choices

| test_date | chosen_variant | gamma0_base | gamma1_broad | gamma2_strict | test_entries | test_exposure | test_total_net | test_mean_net | locked_total_net | broad_total_net | strict_total_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | locked_baseline_all_1x | 1.0000 | 1.0000 | 1.0000 | 279 | 186.5000 | 433.8814 | 2.3264 | 433.8814 | 298.7676 | -50.0932 |
| 2026-05-10 | grid_g0_0_g1_1.25_g2_4 | 0.0000 | 1.2500 | 4.0000 | 113 | 141.8750 | 160.1470 | 1.1288 | 140.4206 | 136.6390 | -3.8733 |
| 2026-05-11 | grid_g0_0_g1_1.25_g2_4 | 0.0000 | 1.2500 | 4.0000 | 148 | 150.2500 | 293.5900 | 1.9540 | 129.4728 | 175.6024 | 26.9407 |
| 2026-05-12 | grid_g0_0_g1_2_g2_2 | 0.0000 | 2.0000 | 2.0000 | 104 | 163.0000 | 218.3945 | 1.3398 | 284.1158 | 109.1973 | 127.1995 |
| 2026-05-13 | grid_g0_0_g1_2_g2_4 | 0.0000 | 2.0000 | 4.0000 | 83 | 118.0000 | -214.4840 | -1.8177 | -183.5113 | -127.1888 | 19.9468 |
| 2026-05-14 | grid_g0_0_g1_0.75_g2_4 | 0.0000 | 0.7500 | 4.0000 | 243 | 294.8750 | 2398.6443 | 8.1344 | 1227.0443 | 868.9802 | 537.5105 |
| 2026-05-15 | grid_g0_0_g1_0.75_g2_4 | 0.0000 | 0.7500 | 4.0000 | 204 | 236.0000 | 2371.6698 | 10.0494 | 1293.7137 | 974.0626 | 504.9609 |
| 2026-05-16 | grid_g0_0_g1_0.75_g2_4 | 0.0000 | 0.7500 | 4.0000 | 131 | 146.1250 | 488.3859 | 3.3422 | 39.2337 | 88.0078 | 129.9631 |
| 2026-05-17 | grid_g0_0_g1_0.75_g2_4 | 0.0000 | 0.7500 | 4.0000 | 119 | 118.0000 | 613.1794 | 5.1964 | 280.9097 | 284.7261 | 122.9646 |

## Policy Summary

| policy | days | positive_days | total_net | exposure | mean_net | worst_day_net | daily_cvar20 | max_drawdown | daily_sharpe_like |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| walk_forward_chosen | 9 | 8 | 6763.4084 | 1554.6250 | 4.3505 | -214.4840 | -27.1685 | -214.4840 | 0.7865 |
| recommended_state_boost_0_0p75_4 | 9 | 8 | 6707.0343 | 1491.6250 | 4.4965 | -30.5644 | 15.3543 | -30.5644 | 0.7801 |
| balanced_three_layer_0p5_1p25_2p5 | 9 | 8 | 5698.6355 | 1774.6250 | 3.2112 | -162.2137 | 2.8171 | -162.2137 | 0.8094 |
| mid_state_boost_0_0p75_2p5 | 9 | 8 | 4583.7550 | 1100.8750 | 4.1637 | -60.4847 | 17.6081 | -60.4847 | 0.8012 |
| conservative_three_layer_0p25_1_2 | 9 | 8 | 4433.4354 | 1307.5000 | 3.3908 | -121.3226 | 6.1942 | -121.3226 | 0.8154 |
| capped_state_boost_0_1_2 | 9 | 8 | 4224.3138 | 1120.5000 | 3.7700 | -107.2420 | 12.7618 | -107.2420 | 0.8258 |
| locked_baseline_all_1x | 9 | 8 | 3645.2806 | 1608.0000 | 2.2670 | -183.5113 | -72.1388 | -183.5113 | 0.7863 |
| broad_only_1x | 9 | 8 | 2808.7942 | 860.0000 | 3.2660 | -127.1888 | -19.5905 | -127.1888 | 0.8482 |
| strict_only_1x | 9 | 7 | 1415.5196 | 260.5000 | 5.4339 | -50.0932 | -26.9833 | -3.8733 | 0.7283 |

## Leverage Caps

These caps are dimensionless multipliers under a bp-unit loss budget. They are not account-level trading advice; map them to actual notional only after fill/slippage and exchange margin constraints.

| policy | loss_budget_bps_units | conservative_cap_min | cap_by_worst_day | cap_by_worst_entry | cap_by_entry_cvar05 | worst_day_net | entry_worst_pnl | entry_cvar05 | total_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strict_only_1x | 100.0000 | 1.6070 | 1.9963 | 1.6070 | 2.4382 | -50.0932 | -62.2293 | -41.0130 | 1415.5196 |
| conservative_three_layer_0p25_1_2 | 100.0000 | 0.8035 | 0.8242 | 0.8035 | 4.1423 | -121.3226 | -124.4585 | -24.1413 | 4433.4354 |
| capped_state_boost_0_1_2 | 100.0000 | 0.8035 | 0.9325 | 0.8035 | 2.7710 | -107.2420 | -124.4585 | -36.0881 | 4224.3138 |
| broad_only_1x | 100.0000 | 0.7862 | 0.7862 | 1.3450 | 3.8612 | -127.1888 | -74.3507 | -25.8987 | 2808.7942 |
| mid_state_boost_0_0p75_2p5 | 100.0000 | 0.6428 | 1.6533 | 0.6428 | 2.6703 | -60.4847 | -155.5731 | -37.4496 | 4583.7550 |
| balanced_three_layer_0p5_1p25_2p5 | 100.0000 | 0.6165 | 0.6165 | 0.6428 | 3.2114 | -162.2137 | -155.5731 | -31.1389 | 5698.6355 |
| locked_baseline_all_1x | 100.0000 | 0.5449 | 0.5449 | 1.1376 | 4.1735 | -183.5113 | -87.9076 | -23.9609 | 3645.2806 |
| recommended_state_boost_0_0p75_4 | 100.0000 | 0.4017 | 3.2718 | 0.4017 | 1.8354 | -30.5644 | -248.9170 | -54.4830 | 6707.0343 |
| walk_forward_chosen | 100.0000 | 0.4017 | 0.4662 | 0.4017 | 2.2686 | -214.4840 | -248.9170 | -44.0809 | 6763.4084 |

## Read

The best simple state-sizing policy is gamma=(0, 0.75, 4): skip non-broad, keep broad small, and boost strict. It improves risk-normalized daily PnL, but its leverage cap is constrained by strict single-entry left tail. Strict-only has high mean but low coverage; it is best treated as an add-on boost, not a standalone strategy. Leverage should be capped by worst-day/CVaR, not by mean return.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_variants_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_walkforward_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_daily_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_summary_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v1.json`

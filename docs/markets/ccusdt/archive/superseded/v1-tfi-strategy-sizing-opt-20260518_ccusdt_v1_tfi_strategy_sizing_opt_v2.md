# CCUSDT TFI Strategy Sizing Optimization

Status: `20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2`.

Guardrail: `research_only_walk_forward_sizing_optimization_no_execution_recommendation_no_alpha_claim`.

Mutually exclusive state layers:

$$
A_t=\mathbf{1}\{R_5>1\},\quad B_t=\mathbf{1}\{F_t\ge q_{90}\},\quad \gamma_t=\gamma_{A_tB_t}
$$

$$
\begin{array}{c|cc}
 & B_t=0 & B_t=1 \\
\hline
A_t=0 & \gamma_{00} & \gamma_{01} \\
A_t=1 & \gamma_{10} & \gamma_{11}
\end{array}
$$

The walk-forward loop chooses \((\gamma_{00},\gamma_{10},\gamma_{01},\gamma_{11})\) using only prior dates, then evaluates the next date.

## Mutually Exclusive Cell Stats

| scope | cell | A_r5 | B_frames_q90 | entries | exposure | total_net | mean_net | gt2_exposure_rate | cost_hit_exposure_rate | positive_day_count | days | positive_day_rate | worst_day_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_scored_dates | 00_none | 0 | 0 | 1650 | 847.5000 | -27.4639 | -0.0324 | 0.3440 | 0.6206 | 6 | 14 | 0.4286 | -118.7353 |
| all_scored_dates | 01_frames_only | 0 | 1 | 157 | 259.0000 | 459.9844 | 1.7760 | 0.4672 | 0.5251 | 11 | 14 | 0.7857 | -110.8369 |
| all_scored_dates | 10_r5_only | 1 | 0 | 1380 | 721.5000 | 1335.7733 | 1.8514 | 0.4213 | 0.5475 | 7 | 14 | 0.5000 | -147.1356 |
| all_scored_dates | 11_r5_frames | 1 | 1 | 178 | 284.5000 | 1462.6178 | 5.1410 | 0.5518 | 0.4341 | 10 | 13 | 0.7692 | -50.0932 |
| walkforward_test_9d | 00_none | 0 | 0 | 1059 | 549.0000 | 430.7494 | 0.7846 | 0.4217 | 0.5464 | 6 | 9 | 0.6667 | -78.2444 |
| walkforward_test_9d | 01_frames_only | 0 | 1 | 114 | 199.0000 | 405.7370 | 2.0389 | 0.4598 | 0.5302 | 7 | 9 | 0.7778 | -110.8369 |
| walkforward_test_9d | 10_r5_only | 1 | 0 | 1142 | 599.5000 | 1393.2746 | 2.3241 | 0.4404 | 0.5263 | 6 | 9 | 0.6667 | -147.1356 |
| walkforward_test_9d | 11_r5_frames | 1 | 1 | 162 | 260.5000 | 1415.5196 | 5.4339 | 0.5643 | 0.4203 | 7 | 9 | 0.7778 | -50.0932 |

## In-Sample Variant Frontier

| variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | entries | exposure | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_day_count | risk_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| three_layer_recommended_0_0p75_0_4 | 0.0000 | 0.7500 | 0.0000 | 4.0000 | 1558 | 1679.1250 | 6852.3011 | 4.0809 | -30.5644 | -20.8621 | -32.0219 | 10 | 13.5642 |
| four_cell_recommended_0_0p5_0p25_4 | 0.0000 | 0.5000 | 0.2500 | 4.0000 | 1715 | 1563.5000 | 6633.3539 | 4.2426 | -21.4897 | -16.5963 | -21.4897 | 10 | 13.5040 |
| grid_g00_0_g10_1_g01_0_g11_4 | 0.0000 | 1.0000 | 0.0000 | 4.0000 | 1558 | 1859.5000 | 7186.2444 | 3.8646 | -67.3483 | -36.3562 | -67.3483 | 10 | 13.4572 |
| grid_g00_0_g10_0.5_g01_0_g11_4 | 0.0000 | 0.5000 | 0.0000 | 4.0000 | 1558 | 1498.7500 | 6518.3578 | 4.3492 | -25.9423 | -16.0885 | -25.9423 | 11 | 13.4017 |
| grid_g00_0_g10_1.25_g01_0_g11_4 | 0.0000 | 1.2500 | 0.0000 | 4.0000 | 1558 | 2039.8750 | 7520.1878 | 3.6866 | -104.1322 | -53.5674 | -104.1322 | 10 | 13.3884 |
| grid_g00_0_g10_0.75_g01_0.25_g11_4 | 0.0000 | 0.7500 | 0.2500 | 4.0000 | 1715 | 1743.8750 | 6967.2972 | 3.9953 | -58.2736 | -28.7265 | -58.2736 | 10 | 13.3658 |
| grid_g00_0_g10_1.5_g01_0_g11_4 | 0.0000 | 1.5000 | 0.0000 | 4.0000 | 1558 | 2220.2500 | 7854.1311 | 3.5375 | -140.9161 | -70.8856 | -140.9161 | 9 | 13.3485 |
| grid_g00_0_g10_2_g01_0_g11_4 | 0.0000 | 2.0000 | 0.0000 | 4.0000 | 1558 | 2581.0000 | 8522.0177 | 3.3018 | -214.4840 | -105.5219 | -214.4840 | 9 | 13.3313 |
| grid_g00_0_g10_0.5_g01_0.5_g11_4 | 0.0000 | 0.5000 | 0.5000 | 4.0000 | 1715 | 1628.2500 | 6748.3500 | 4.1445 | -49.1990 | -22.3014 | -49.1990 | 10 | 13.2931 |
| grid_g00_0_g10_1_g01_0.25_g11_4 | 0.0000 | 1.0000 | 0.2500 | 4.0000 | 1715 | 1924.2500 | 7301.2405 | 3.7943 | -95.0576 | -44.2206 | -95.0576 | 10 | 13.2741 |
| grid_g00_0_g10_1.25_g01_0.25_g11_4 | 0.0000 | 1.2500 | 0.2500 | 4.0000 | 1715 | 2104.6250 | 7635.1839 | 3.6278 | -131.8415 | -61.3373 | -131.8415 | 10 | 13.2168 |
| grid_g00_0.25_g10_2_g01_0_g11_4 | 0.2500 | 2.0000 | 0.0000 | 4.0000 | 3208 | 2792.8750 | 8515.1518 | 3.0489 | -200.8554 | -117.0694 | -270.0393 | 9 | 13.2048 |
| grid_g00_0_g10_1.5_g01_0.25_g11_4 | 0.0000 | 1.5000 | 0.2500 | 4.0000 | 1715 | 2285.0000 | 7969.1272 | 3.4876 | -168.6254 | -78.6554 | -168.6254 | 10 | 13.1858 |
| grid_g00_0.25_g10_1_g01_0_g11_4 | 0.2500 | 1.0000 | 0.0000 | 4.0000 | 3208 | 2071.3750 | 7179.3785 | 3.4660 | -53.7198 | -48.2320 | -140.4695 | 9 | 13.1851 |
| grid_g00_0_g10_2_g01_0.25_g11_4 | 0.0000 | 2.0000 | 0.2500 | 4.0000 | 1715 | 2645.7500 | 8637.0138 | 3.2645 | -242.1932 | -113.2917 | -242.1932 | 9 | 13.1811 |
| four_cell_stale_half_0_0p75_0p5_4 | 0.0000 | 0.7500 | 0.5000 | 4.0000 | 1715 | 1808.6250 | 7082.2933 | 3.9158 | -85.9829 | -36.5909 | -85.9829 | 10 | 13.1736 |
| grid_g00_0.25_g10_1.25_g01_0_g11_4 | 0.2500 | 1.2500 | 0.0000 | 4.0000 | 3208 | 2251.7500 | 7513.3218 | 3.3367 | -90.5037 | -65.4413 | -172.8619 | 9 | 13.1649 |
| grid_g00_0.25_g10_1.5_g01_0_g11_4 | 0.2500 | 1.5000 | 0.0000 | 4.0000 | 3208 | 2432.1250 | 7847.2651 | 3.2265 | -127.2876 | -82.6507 | -205.2544 | 9 | 13.1640 |
| grid_g00_0.5_g10_2_g01_0_g11_4 | 0.5000 | 2.0000 | 0.0000 | 4.0000 | 3208 | 3004.7500 | 8508.2858 | 2.8316 | -187.2268 | -130.4627 | -367.9231 | 9 | 13.1140 |
| grid_g00_0_g10_1_g01_0.5_g11_4 | 0.0000 | 1.0000 | 0.5000 | 4.0000 | 1715 | 1989.0000 | 7416.2366 | 3.7286 | -122.7668 | -52.0850 | -122.7668 | 10 | 13.0956 |

## Walk-Forward Daily Choices

| test_date | chosen_variant | gamma00_none | gamma10_r5_only | gamma01_frames_only | gamma11_r5_frames | test_entries | test_exposure | test_total_net | test_mean_net | locked_total_net | broad_total_net | stale_total_net | strict_total_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | grid_g00_0_g10_0.5_g01_1_g11_4 | 0.0000 | 0.5000 | 1.0000 | 4.0000 | 170 | 221.5000 | 5.2485 | 0.0237 | 433.8814 | 298.7676 | -18.9024 | -50.0932 |
| 2026-05-10 | grid_g00_0_g10_1.5_g01_1_g11_3 | 0.0000 | 1.5000 | 1.0000 | 3.0000 | 121 | 149.7500 | 170.4424 | 1.1382 | 140.4206 | 136.6390 | -32.5793 | -3.8733 |
| 2026-05-11 | grid_g00_0_g10_1.5_g01_1_g11_3 | 0.0000 | 1.5000 | 1.0000 | 3.0000 | 166 | 180.5000 | 335.9295 | 1.8611 | 129.4728 | 175.6024 | 59.0556 | 26.9407 |
| 2026-05-12 | grid_g00_0_g10_2_g01_1_g11_4 | 0.0000 | 2.0000 | 1.0000 | 4.0000 | 120 | 261.0000 | 586.5861 | 2.2475 | 284.1158 | 109.1973 | 240.9921 | 127.1995 |
| 2026-05-13 | grid_g00_0_g10_2_g01_1_g11_4 | 0.0000 | 2.0000 | 1.0000 | 4.0000 | 103 | 155.5000 | -325.3208 | -2.0921 | -183.5113 | -127.1888 | -90.8900 | 19.9468 |
| 2026-05-14 | three_layer_recommended_0_0p75_0_4 | 0.0000 | 0.7500 | 0.0000 | 4.0000 | 243 | 294.8750 | 2398.6443 | 8.1344 | 1227.0443 | 868.9802 | 766.3667 | 537.5105 |
| 2026-05-15 | three_layer_recommended_0_0p75_0_4 | 0.0000 | 0.7500 | 0.0000 | 4.0000 | 204 | 236.0000 | 2371.6698 | 10.0494 | 1293.7137 | 974.0626 | 623.5463 | 504.9609 |
| 2026-05-16 | three_layer_recommended_0_0p75_0_4 | 0.0000 | 0.7500 | 0.0000 | 4.0000 | 131 | 146.1250 | 488.3859 | 3.3422 | 39.2337 | 88.0078 | 139.8300 | 129.9631 |
| 2026-05-17 | three_layer_recommended_0_0p75_0_4 | 0.0000 | 0.7500 | 0.0000 | 4.0000 | 119 | 118.0000 | 613.1794 | 5.1964 | 280.9097 | 284.7261 | 133.8377 | 122.9646 |

## Policy Summary

| policy | days | positive_days | total_net | exposure | mean_net | worst_day_net | daily_cvar20 | max_drawdown | daily_sharpe_like |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| four_cell_stale_full_0_0p75_1_4 | 9 | 8 | 7112.7713 | 1690.6250 | 4.2072 | -141.4013 | -40.1082 | -141.4013 | 0.7628 |
| four_cell_stale_half_0_0p75_0p5_4 | 9 | 8 | 6909.9028 | 1591.1250 | 4.3428 | -85.9829 | -5.2225 | -85.9829 | 0.7714 |
| three_layer_recommended_0_0p75_0_4 | 9 | 8 | 6707.0343 | 1491.6250 | 4.4965 | -30.5644 | 15.3543 | -30.5644 | 0.7801 |
| walk_forward_chosen | 9 | 8 | 6644.7653 | 1763.2500 | 3.7685 | -325.3208 | -160.0361 | -325.3208 | 0.7536 |
| four_cell_recommended_0_0p5_0p25_4 | 9 | 7 | 6460.1499 | 1391.5000 | 4.6426 | -21.4897 | -19.8172 | -21.4897 | 0.7613 |
| four_cell_milder_0_0p75_0p5_2p5 | 9 | 8 | 4786.6234 | 1200.3750 | 3.9876 | -115.9031 | -17.2776 | -115.9031 | 0.7866 |
| conservative_four_cell_0p25_1_0p25_2 | 9 | 8 | 4433.4354 | 1307.5000 | 3.3908 | -121.3226 | 6.1942 | -121.3226 | 0.8154 |
| capped_four_cell_0_1_0p5_2 | 9 | 8 | 4427.1823 | 1220.0000 | 3.6288 | -162.6604 | -22.1239 | -162.6604 | 0.8078 |
| locked_baseline_all_1x | 9 | 8 | 3645.2806 | 1608.0000 | 2.2670 | -183.5113 | -72.1388 | -183.5113 | 0.7863 |
| broad_only_1x | 9 | 8 | 2808.7942 | 860.0000 | 3.2660 | -127.1888 | -19.5905 | -127.1888 | 0.8482 |
| stale_only_1x | 9 | 6 | 1821.2565 | 459.5000 | 3.9636 | -90.8900 | -61.7347 | -90.8900 | 0.6763 |
| strict_only_1x | 9 | 7 | 1415.5196 | 260.5000 | 5.4339 | -50.0932 | -26.9833 | -53.9665 | 0.7283 |

## Leverage Caps

These caps are dimensionless multipliers under a bp-unit loss budget. They are not account-level trading advice; map them to actual notional only after fill/slippage and exchange margin constraints.

| policy | loss_budget_bps_units | conservative_cap_min | cap_by_worst_day | cap_by_worst_entry | cap_by_entry_cvar05 | worst_day_net | entry_worst_pnl | entry_cvar05 | total_net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strict_only_1x | 100.0000 | 1.6070 | 1.9963 | 1.6070 | 2.4382 | -50.0932 | -62.2293 | -41.0130 | 1415.5196 |
| stale_only_1x | 100.0000 | 1.1002 | 1.1002 | 1.1376 | 2.3309 | -90.8900 | -87.9076 | -42.9014 | 1821.2565 |
| conservative_four_cell_0p25_1_0p25_2 | 100.0000 | 0.8035 | 0.8242 | 0.8035 | 4.1423 | -121.3226 | -124.4585 | -24.1413 | 4433.4354 |
| broad_only_1x | 100.0000 | 0.7862 | 0.7862 | 1.3450 | 3.8612 | -127.1888 | -74.3507 | -25.8987 | 2808.7942 |
| four_cell_milder_0_0p75_0p5_2p5 | 100.0000 | 0.6428 | 0.8628 | 0.6428 | 2.7116 | -115.9031 | -155.5731 | -36.8790 | 4786.6234 |
| capped_four_cell_0_1_0p5_2 | 100.0000 | 0.6148 | 0.6148 | 0.8035 | 2.8433 | -162.6604 | -124.4585 | -35.1703 | 4427.1823 |
| locked_baseline_all_1x | 100.0000 | 0.5449 | 0.5449 | 1.1376 | 4.1735 | -183.5113 | -87.9076 | -23.9609 | 3645.2806 |
| four_cell_recommended_0_0p5_0p25_4 | 100.0000 | 0.4017 | 4.6534 | 0.4017 | 2.0514 | -21.4897 | -248.9170 | -48.7482 | 6460.1499 |
| four_cell_stale_half_0_0p75_0p5_4 | 100.0000 | 0.4017 | 1.1630 | 0.4017 | 1.9117 | -85.9829 | -248.9170 | -52.3086 | 6909.9028 |
| four_cell_stale_full_0_0p75_1_4 | 100.0000 | 0.4017 | 0.7072 | 0.4017 | 1.8222 | -141.4013 | -248.9170 | -54.8772 | 7112.7713 |
| three_layer_recommended_0_0p75_0_4 | 100.0000 | 0.4017 | 3.2718 | 0.4017 | 1.8354 | -30.5644 | -248.9170 | -54.4830 | 6707.0343 |
| walk_forward_chosen | 100.0000 | 0.3074 | 0.3074 | 0.4017 | 1.7647 | -325.3208 | -248.9170 | -56.6653 | 6644.7653 |

## Read

The cleaner simple state-sizing policy is four-cell gamma=(0, 0.5, 0.25, 4): skip 00, keep 10 small, trade 01 at small size, and boost 11. The old three-layer gamma=(0, 0.75, 0, 4) was too coarse because it silenced the 01 stale-queue state. The 01 cell has 114 entries, mean 2.0389 bps, and positive days 7/9 in the walk-forward test window. Strict 11 has high mean but low coverage; it is best treated as an add-on boost, not a standalone strategy. Leverage should be capped by worst-day/CVaR, not by mean return.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_variants_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_walkforward_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_daily_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_cells_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_strategy_sizing_summary_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.json`

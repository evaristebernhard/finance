# CCUSDT TFI Exit Walk-Forward Check

Status: `20260518_ccusdt_v1_tfi_exit_walkforward_v1`.

Guardrail: `walk_forward_exit_validation_research_only_no_execution_recommendation`.

This is a frozen-candidate walk-forward validation, not an exit optimizer. Test days are evaluated once after prior-date training.

## Design

- Entry universe: existing V1 TFI latent-state entries with local v3 fixed-event panel paths.
- Earliest train window: 5 prior dates.
- Test dates: `2026-05-09, 2026-05-10, 2026-05-11, 2026-05-12, 2026-05-13, 2026-05-14, 2026-05-15`.
- Baseline: `fixed_60s` on the same entries and same toy maker-light cost model.
- Candidate families: fixed timeout, TP+timeout, single-factor flow-confirmed hold, and exposure cap.
- Flow thresholds are prior-date quantiles among prior entries with `MFE_10 >= 5bps`.

The signed path is:

$$
R_i(\tau)=s_i10^4\log\frac{M_{t_i+\tau}}{M_{t_i}}.
$$

TP exits are first-hit mid-price barriers and should be read as a research proxy, not guaranteed executable fills.

## Main Read

Baseline `fixed_60s`: total `5713.5706`, worst day `-59.0662`, CVaR5 `-37.7702`, q90 `21.8468`.
Best risk-score candidate: `flow_hold_signed_ofi_mean_5_20s_q50_exit20s` with total `6790.1403`, worst day `-42.6939`, delta total vs original fixed60 `1076.5696`, and right-tail retention `0.8520`.

Verdict:

- `fixed_30s` is the cleanest simple risk-control baseline: all `7/7` test days are positive and worst day improves, but total PnL drops materially and q90 right-tail retention is only about two thirds of `fixed_60s`.
- TP+timeout is not supported in this pass. It protects some losers but kills too much right tail; every TP variant underperforms `fixed_60s` on total PnL.
- The best flow-confirmed hold candidates improve total and worst day, but they are path-dependent hypotheses, not promoted rules. They require the `5s..20s` flow window and therefore must be evaluated with explicit decision timing and execution assumptions.
- Exposure caps alone are not a repair here: they cut important winners and can worsen worst-day PnL.

A candidate should not be trusted merely because it ranks high here. Promotion requires fresh OOS days and execution-aware fill/cost checks.

## Fixed Timeout

| policy | entries | total_pnl | stress_total_pnl | delta_vs_original_fixed60_total | mean_net | median_net | q90_net | cvar05_net | worst_day | positive_days | right_tail_retention_q90 | top10_winner_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_10s | 1158 | 2172.3889 | -371.1111 | -3541.1817 | 0.8042 | -1.3037 | 8.9791 | -14.3111 | -91.6570 | 6 | 0.4110 | 0.6999 |
| fixed_20s | 1158 | 4224.5851 | 1681.0851 | -1488.9856 | 1.6487 | -0.8384 | 11.5474 | -22.0219 | -34.3120 | 6 | 0.5286 | 0.5841 |
| fixed_30s | 1158 | 4403.5926 | 1860.0926 | -1309.9780 | 1.9971 | -0.6763 | 14.7858 | -25.8938 | 9.3507 | 7 | 0.6768 | 0.6275 |
| fixed_60s | 1158 | 5713.5706 | 3170.0706 | 0.0000 | 2.8738 | -0.3560 | 21.8468 | -37.7702 | -59.0662 | 6 | 1.0000 | 0.8053 |

## TP + Timeout

| policy | entries | total_pnl | stress_total_pnl | delta_vs_original_fixed60_total | mean_net | median_net | q90_net | cvar05_net | worst_day | positive_days | right_tail_retention_q90 | top10_winner_share | trigger_rate | mean_exit_horizon_sec | saved_loser_pnl | killed_winner_pnl |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tp10_timeout20s | 1158 | 1743.7014 | -799.7986 | -3969.8692 | 0.3749 | -0.6817 | 7.9360 | -20.3347 | -35.9780 | 6 | 0.3633 | 0.4012 | 0.2133 | 17.3950 | 3993.7688 | 8009.0192 |
| tp10_timeout30s | 1158 | 1398.1468 | -1145.3532 | -4315.4238 | 0.3601 | -0.1840 | 8.0329 | -24.0801 | -1.6525 | 6 | 0.3677 | 0.5209 | 0.2556 | 25.0384 | 3565.4788 | 7888.4197 |
| tp8_timeout20s | 1158 | 1249.0896 | -1294.4104 | -4464.4811 | -0.0339 | -0.6795 | 5.8860 | -20.1692 | -38.0783 | 6 | 0.2694 | 0.4539 | 0.2340 | 17.0574 | 3904.4870 | 8354.6498 |
| tp8_timeout30s | 1158 | 1161.7905 | -1381.7095 | -4551.7802 | -0.0538 | 0.0466 | 5.9502 | -23.3950 | -2.3589 | 6 | 0.2724 | 0.4935 | 0.2841 | 24.4592 | 3469.9437 | 7989.2678 |
| tp10_timeout60s | 1158 | 823.5240 | -1719.9760 | -4890.0466 | -0.1101 | 2.7069 | 8.0835 | -34.2801 | -97.0094 | 5 | 0.3700 | 0.9818 | 0.3497 | 45.7650 | 1285.9088 | 6317.8515 |
| tp5_timeout30s | 1158 | 383.0982 | -2160.4018 | -5330.4724 | -0.5460 | 2.0838 | 3.2461 | -20.7004 | -101.1425 | 4 | 0.1486 | 0.8980 | 0.4870 | 19.5669 | 3640.0663 | 8858.7162 |
| tp5_timeout20s | 1158 | 213.0207 | -2330.4793 | -5500.5500 | -0.5990 | -0.3030 | 3.2317 | -19.3002 | -121.9539 | 3 | 0.1479 | 1.6150 | 0.4275 | 14.1962 | 3815.1004 | 9193.9112 |
| tp8_timeout60s | 1158 | 194.0902 | -2349.4098 | -5519.4804 | -0.7001 | 2.9856 | 6.0686 | -34.1058 | -145.7161 | 5 | 0.2778 | 3.1341 | 0.3808 | 44.2651 | 1369.8480 | 6988.8097 |
| tp5_timeout60s | 1158 | -442.7441 | -2986.2441 | -6156.3148 | -0.9450 | 2.5624 | 3.3529 | -29.1077 | -364.3052 | 2 | 0.1535 |  | 0.5941 | 33.1966 | 2220.4102 | 8409.1969 |

## Flow-Confirmed Hold

| policy | entries | total_pnl | stress_total_pnl | delta_vs_original_fixed60_total | mean_net | median_net | q90_net | cvar05_net | worst_day | positive_days | right_tail_retention_q90 | top10_winner_share | trigger_rate | mean_exit_horizon_sec | saved_loser_pnl | killed_winner_pnl | save_kill_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flow_hold_signed_ofi_mean_5_20s_q50_exit20s | 1158 | 6790.1403 | 4246.6403 | 1076.5696 | 3.0293 | 1.3798 | 18.6127 | -32.9242 | -42.6939 | 6 | 0.8520 | 0.6846 | 0.1606 | 53.5751 | 1156.5016 | 363.5716 | 3.1809 |
| flow_hold_signed_ofi_mean_5_20s_q30_exit20s | 1158 | 6565.7877 | 4022.2877 | 852.2170 | 3.0308 | 0.5620 | 20.0114 | -33.5791 | -37.4292 | 6 | 0.9160 | 0.7080 | 0.1097 | 55.6131 | 853.1618 | 266.8180 | 3.1975 |
| flow_hold_signed_mlofi5_mean_5_20s_q50_exit20s | 1158 | 6365.8576 | 3822.3576 | 652.2870 | 3.0033 | 1.2002 | 18.6127 | -32.8649 | -36.6914 | 6 | 0.8520 | 0.7160 | 0.1572 | 53.7133 | 1089.7375 | 727.4709 | 1.4980 |
| flow_hold_signed_ofi_mean_5_20s_q50_exit30s | 1158 | 6370.0586 | 3826.5586 | 656.4880 | 2.9183 | 0.8180 | 18.6127 | -34.0349 | -47.2433 | 6 | 0.8520 | 0.7223 | 0.1606 | 55.1813 | 783.2944 | 387.2663 | 2.0226 |
| flow_hold_signed_ofi_mean_5_20s_q30_exit30s | 1158 | 6231.5647 | 3688.0647 | 517.9940 | 2.9395 | 0.2057 | 20.0736 | -34.6051 | -41.9786 | 6 | 0.9188 | 0.7384 | 0.1097 | 56.7098 | 520.6256 | 235.8478 | 2.2075 |
| flow_hold_signed_mlofi5_mean_5_20s_q50_exit30s | 1158 | 6068.7511 | 3525.2511 | 355.1805 | 2.8517 | 0.6800 | 18.5924 | -34.0349 | -41.3833 | 6 | 0.8510 | 0.7425 | 0.1572 | 55.2850 | 730.0123 | 628.3574 | 1.1618 |
| flow_hold_signed_mlofi5_mean_5_20s_q30_exit20s | 1158 | 5937.9281 | 3394.4281 | 224.3575 | 2.9129 | -0.1813 | 20.1932 | -33.7094 | -36.7526 | 6 | 0.9243 | 0.7676 | 0.0881 | 56.4767 | 512.1381 | 503.7546 | 1.0166 |
| flow_hold_signed_mlofi5_mean_5_20s_q30_exit30s | 1158 | 5715.0785 | 3171.5785 | 1.5079 | 2.7958 | -0.0257 | 19.6679 | -34.7915 | -41.3833 | 6 | 0.9003 | 0.7884 | 0.0881 | 57.3575 | 282.9527 | 439.1705 | 0.6443 |
| flow_hold_signed_tfi_mean_5_20s_q30_exit30s | 1158 | 5267.9708 | 2724.4708 | -445.5998 | 2.7123 | 0.3799 | 19.0597 | -36.5134 | -39.4275 | 6 | 0.8724 | 0.7664 | 0.1649 | 55.0518 | 781.3993 | 1467.7044 | 0.5324 |
| flow_hold_signed_tfi_mean_5_20s_q30_exit20s | 1158 | 5069.4277 | 2525.9277 | -644.1429 | 2.5169 | 0.8180 | 18.0016 | -36.0336 | -34.8145 | 6 | 0.8240 | 0.7274 | 0.1649 | 53.4024 | 877.0938 | 1804.0110 | 0.4862 |

## Exposure Cap

| policy | entries | total_pnl | stress_total_pnl | delta_vs_original_fixed60_total | mean_net | median_net | q90_net | cvar05_net | worst_day | positive_days | right_tail_retention_q90 | top10_winner_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_60s_cap2 | 1158 | 2400.8798 | 1049.3798 | -3312.6908 | 2.8738 | -0.3560 | 21.8468 | -37.7702 | -105.6131 | 6 | 1.0000 | 0.5584 |
| fixed_60s_cap4 | 1158 | 3539.7470 | 1788.2470 | -2173.8236 | 2.8738 | -0.3560 | 21.8468 | -37.7702 | -93.9764 | 6 | 1.0000 | 0.6886 |

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_exit_walkforward_paths_20260518_ccusdt_v1_tfi_exit_walkforward_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_exit_walkforward_events_20260518_ccusdt_v1_tfi_exit_walkforward_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_exit_walkforward_scorecard_20260518_ccusdt_v1_tfi_exit_walkforward_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_exit_walkforward_daily_20260518_ccusdt_v1_tfi_exit_walkforward_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_exit_walkforward_summary_20260518_ccusdt_v1_tfi_exit_walkforward_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_exit_walkforward.py
```

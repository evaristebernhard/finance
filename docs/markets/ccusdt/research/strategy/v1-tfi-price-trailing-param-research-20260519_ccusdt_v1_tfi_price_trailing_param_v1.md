# CCUSDT TFI Price-Only Trailing Parameter Research

Status: `20260519_ccusdt_v1_tfi_price_trailing_param_v1`.

Guardrail: `price_only_trailing_parameter_research_walk_forward_no_execution_recommendation`.

This pass tests a simple price-path trailing idea and intentionally does not use order-flow, depth, or latent-state factors for exit.

## Rule

Signed path, running high, and drawdown:

$$
R_i(t)=s_i10^4\log\frac{M_{t_i+t}}{M_{t_i}},\quad H_i(t)=\max_{0<u\le t}R_i(u),\quad D_i(t)=H_i(t)-R_i(t).
$$

The release threshold is prior-date only:

$$
r_i=\max(c_i+m,\ Q_p^{train}(H_{10})).
$$

If release occurs within the activation window, trailing exits when:

$$
D_i(t)\ge \max(c_i+m,\ \eta H_i(t)).
$$

Otherwise the entry exits at 60s. This is still a mid-path research proxy, not an executable fill model.

## Design

- Test dates: `2026-05-09, 2026-05-10, 2026-05-11, 2026-05-12, 2026-05-13, 2026-05-14, 2026-05-15`.
- Margin: `1.0000` bps.
- Fixed baselines: `20s`, `30s`, `60s`.
- Trailing grid: `p in {60,70,80}%`, `eta in {0.30,0.50}`, activation window `10s/20s`.

## Main Read

Baseline `fixed_60s`: total `5713.5706`, worst day `-59.0662`, q90 `21.8468`, CVaR5 `-37.7702`.
Best candidate: `trail_p80_eta30_act10s` with total `6162.1109`, worst day `-39.5948`, delta total `448.5403`, q90 retention `0.8232`.

The main read is not that `10s` or `p80` is magic. It is that a release must first clear a prior-date, cost-aware threshold, and only then a trailing drawdown can cut fast release/decay paths. This avoids a fixed `10bps` posterior threshold while still testing the same economic idea.

Read this as parameter research only. A trailing rule can be considered interesting only if it improves worst day/CVaR while keeping enough right tail and does not rely on tiny activation rates.

## Fixed Baselines

| policy | entries | total_pnl | delta_vs_original_fixed60_total | mean_net | median_net | q90_net | cvar05_net | worst_day | positive_days | right_tail_retention_q90 | top10_winner_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_20s | 1158 | 4224.5851 | -1488.9856 | 1.6487 | -0.8384 | 11.5474 | -22.0219 | -34.3120 | 6 | 0.5286 | 0.5841 |
| fixed_30s | 1158 | 4403.5926 | -1309.9780 | 1.9971 | -0.6763 | 14.7858 | -25.8938 | 9.3507 | 7 | 0.6768 | 0.6275 |
| fixed_60s | 1158 | 5713.5706 | 0.0000 | 2.8738 | -0.3560 | 21.8468 | -37.7702 | -59.0662 | 6 | 1.0000 | 0.8053 |

## Price-Only Trailing Candidates

| policy | entries | total_pnl | delta_vs_original_fixed60_total | mean_net | median_net | q90_net | cvar05_net | worst_day | positive_days | right_tail_retention_q90 | top10_winner_share | release_quantile | eta | activation_horizon | activated_rate | trailing_exit_rate | mean_exit_sec | saved_loser_pnl | killed_winner_pnl | save_kill_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| trail_p80_eta30_act10s | 1158 | 6162.1109 | 448.5403 | 2.7503 | -0.1813 | 17.9849 | -32.9019 | -39.5948 | 6 | 0.8232 | 0.7371 | 0.8000 | 0.3000 | 10.0000 | 0.2893 | 0.1684 | 53.3624 | 1170.9219 | 850.9139 | 1.3761 |
| trail_p80_eta50_act10s | 1158 | 6081.0208 | 367.4502 | 2.6730 | -0.2374 | 18.2555 | -32.9699 | -39.8594 | 6 | 0.8356 | 0.7566 | 0.8000 | 0.5000 | 10.0000 | 0.2893 | 0.1468 | 54.2742 | 1066.9515 | 750.0480 | 1.4225 |
| trail_p70_eta30_act10s | 1158 | 5883.8235 | 170.2529 | 2.6497 | -0.3622 | 17.8713 | -31.0671 | -33.3425 | 6 | 0.8180 | 0.7529 | 0.7000 | 0.3000 | 10.0000 | 0.3696 | 0.2081 | 51.7826 | 1498.2227 | 1449.0729 | 1.0339 |
| trail_p60_eta30_act10s | 1158 | 5880.0798 | 166.5091 | 2.6411 | -0.3640 | 17.8713 | -31.0671 | -33.3425 | 6 | 0.8180 | 0.7534 | 0.6000 | 0.3000 | 10.0000 | 0.3765 | 0.2124 | 51.7192 | 1498.3939 | 1455.2277 | 1.0297 |
| trail_p80_eta30_act20s | 1158 | 5882.5932 | 169.0225 | 2.7331 | -0.1887 | 17.6656 | -30.7948 | -37.7790 | 6 | 0.8086 | 0.7738 | 0.8000 | 0.3000 | 20.0000 | 0.4111 | 0.2193 | 51.9236 | 1296.0656 | 1279.9324 | 1.0126 |
| trail_p70_eta50_act10s | 1158 | 5770.0804 | 56.5097 | 2.5522 | -0.4491 | 17.9798 | -31.1364 | -33.6071 | 6 | 0.8230 | 0.7801 | 0.7000 | 0.5000 | 10.0000 | 0.3696 | 0.1839 | 52.7160 | 1394.2524 | 1376.1397 | 1.0132 |
| trail_p70_eta30_act20s | 1158 | 5766.6416 | 53.0710 | 2.6536 | -0.3696 | 17.5383 | -29.5574 | -31.5876 | 6 | 0.8028 | 0.7707 | 0.7000 | 0.3000 | 20.0000 | 0.4957 | 0.2608 | 50.3340 | 1614.1834 | 1697.0752 | 0.9512 |
| trail_p60_eta30_act20s | 1158 | 5766.4104 | 52.8398 | 2.6531 | -0.3696 | 17.5383 | -29.5574 | -31.5876 | 6 | 0.8028 | 0.7708 | 0.6000 | 0.3000 | 20.0000 | 0.4991 | 0.2625 | 50.3187 | 1614.1834 | 1697.0752 | 0.9512 |
| trail_p60_eta50_act10s | 1158 | 5768.9657 | 55.3951 | 2.5496 | -0.5087 | 17.9798 | -31.1364 | -33.6071 | 6 | 0.8230 | 0.7803 | 0.6000 | 0.5000 | 10.0000 | 0.3765 | 0.1874 | 52.6858 | 1394.4235 | 1380.5609 | 1.0100 |
| trail_p80_eta50_act20s | 1158 | 5770.0672 | 56.4966 | 2.6463 | -0.2493 | 17.8699 | -30.8641 | -38.0436 | 6 | 0.8180 | 0.7966 | 0.8000 | 0.5000 | 20.0000 | 0.4111 | 0.1883 | 53.0849 | 1191.3337 | 1184.5954 | 1.0057 |
| trail_p70_eta50_act20s | 1158 | 5655.8492 | -57.7215 | 2.5708 | -0.5119 | 17.5688 | -29.6344 | -31.8522 | 6 | 0.8042 | 0.7959 | 0.7000 | 0.5000 | 20.0000 | 0.4957 | 0.2280 | 51.5469 | 1509.4515 | 1600.0047 | 0.9434 |
| trail_p60_eta50_act20s | 1158 | 5655.6180 | -57.9527 | 2.5703 | -0.5119 | 17.5688 | -29.6344 | -31.8522 | 6 | 0.8042 | 0.7959 | 0.6000 | 0.5000 | 20.0000 | 0.4991 | 0.2297 | 51.5316 | 1509.4515 | 1600.0047 | 0.9434 |

## Best Candidate Daily Check

`trail_p80_eta30_act10s` improves versus `fixed_60s` on every test date, but it does not make every day profitable. The remaining worst day is still negative, so this is a risk-shaping candidate, not a solved live rule.

| date | entries | best_pnl | fixed60_pnl | fixed30_pnl | best_delta_vs_60s | activated_rate | trailing_exit_rate | mean_exit_sec |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-09 | 170 | 158.2932 | 63.9497 | 64.2769 | 94.3434 | 0.3059 | 0.1588 | 53.5689 |
| 2026-05-10 | 121 | 97.9499 | 81.2542 | 247.8684 | 16.6957 | 0.2810 | 0.1488 | 53.5983 |
| 2026-05-11 | 166 | 316.9144 | 229.7879 | 207.4389 | 87.1265 | 0.2289 | 0.1325 | 55.1178 |
| 2026-05-12 | 120 | 669.2186 | 532.5240 | 679.2718 | 136.6946 | 0.2833 | 0.1333 | 55.4762 |
| 2026-05-13 | 103 | -39.5948 | -59.0662 | 9.3507 | 19.4714 | 0.1262 | 0.0777 | 55.9931 |
| 2026-05-14 | 260 | 2542.2119 | 2464.4816 | 1473.2205 | 77.7303 | 0.4000 | 0.2654 | 49.3390 |
| 2026-05-15 | 218 | 2417.1177 | 2400.6394 | 1722.1654 | 16.4783 | 0.2752 | 0.1606 | 54.1259 |

## Release Thresholds

The train-only release threshold stays in a narrow few-bps range. That is important: the rule is measuring early path release above cost/noise, not waiting for a rare `10bps` event.

| date | train_release_threshold | mean_release_sec |
| --- | --- | --- |
| 2026-05-09 | 4.0847 | 2.5645 |
| 2026-05-10 | 4.7235 | 2.5736 |
| 2026-05-11 | 5.0713 | 3.2994 |
| 2026-05-12 | 5.1172 | 2.5633 |
| 2026-05-13 | 5.3963 | 3.1909 |
| 2026-05-14 | 5.1903 | 3.2131 |
| 2026-05-15 | 5.9133 | 3.3186 |

## Interpretation

- `fixed_30s` is the cleanest left-tail baseline, with `7/7` positive days, but it gives up too much right tail: total is lower by about `1310` PnL units versus `fixed_60s` and q90 retention is only about `0.677`.
- The best price-only trailing point keeps materially more right tail than `fixed_30s` and improves `fixed_60s` total by about `449`, but it still cuts q90 from about `21.85` to `17.98` bps.
- The parameter surface is not wildly unstable: all 12 trailing variants improve CVaR5 versus `fixed_60s`, but only the strict `p80/act10s` variants clearly improve total PnL.
- This remains a mid-price first-hit proxy. A live implementation would still need latency, order type, and fill assumptions before it can be treated as executable.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_price_trailing_base_paths_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_price_trailing_events_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_price_trailing_scorecard_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_price_trailing_daily_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_price_trailing_summary_20260519_ccusdt_v1_tfi_price_trailing_param_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_price_trailing_param_research.py
```

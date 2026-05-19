# CCUSDT V1 TFI Capacity Manager

Status: `20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1`.

Guardrail: `research_only_capacity_manager_no_execution_recommendation`.

## Scope

This pass fixes the watcher-aware four-cell signal model and tests
capacity allocation under a `3x` total exposure cap.

```text
raw_no_cap: target exposures without leverage cap
global_downscale: multiply every leg by L / max_concurrency
online_fifo_clip: keep old legs, new legs take remaining capacity
priority_arrival_clip: same as FIFO, but same-timestamp legs sort by cell priority
priority_replace_terminal_proxy: diagnostic only; replaces lower-priority open capacity using terminal PnL proxy
```

Mathematically, this is a capacity-allocation test, not another entry
filter. Target leg exposure is `w_i = b_i gamma_cell`; the executable
constraint is an overlap constraint:

$$
\sum_{i:t_i\le t<u_i}\widetilde w_i\le L_{max}=3.
$$

So `global_downscale` is only a conservative lower bound:

$$
s=\min\left(1,{3\over \max_t\sum_{i:t_i\le t<u_i}w_i}\right),
\qquad \widetilde w_i=sw_i.
$$

The online clip keeps full size except when the current open book is
actually crowded:

$$
\widetilde w_i=\min\left(w_i,3-L(t_i^-)\right).
$$

## Main Read

For the current 3x q70 Pareto leader, global scaling is conservative:

| capacity_policy | desired_total | actual_total | actual_vs_global_gain | desired_max_concurrent | actual_max_concurrent | clipped_legs | skipped_legs | positive_pnl_lost | negative_pnl_avoided | worst_day | leg_worst |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| raw_no_cap | 6042.8705 | 6042.8705 | 671.4301 | 3.3750 | 3.3750 | 0 | 0 | 0.0000 | 0.0000 | 8.2022 | -76.0697 |
| global_downscale | 6042.8705 | 5371.4405 | 0.0000 | 3.3750 | 3.0000 | 3233 | 0 | 1140.6238 | 469.1938 | 7.2908 | -67.6175 |
| online_fifo_clip | 6042.8705 | 6038.2000 | 666.7596 | 3.3750 | 3.0000 | 4 | 0 | 5.3988 | 0.7283 | 8.2022 | -76.0697 |
| priority_arrival_clip | 6042.8705 | 6038.2000 | 666.7596 | 3.3750 | 3.0000 | 4 | 0 | 5.3988 | 0.7283 | 8.2022 | -76.0697 |
| priority_replace_terminal_proxy | 6042.8705 | 6038.2000 | 666.7596 | 3.3750 | 3.0000 | 4 | 0 | 5.3988 | 0.7283 | 8.2022 | -76.0697 |

## Pressure Sanity

The same low-concurrency q70 point is almost unaffected by the 3x cap,
but pressure still matters because every held leg pays the stress term.

| pressure_bps | capacity_policy | desired_total | actual_total | actual_vs_global_gain | actual_max_concurrent | worst_day | leg_worst | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | online_fifo_clip | 6042.8705 | 6038.2000 | 666.7596 | 3.0000 | 8.2022 | -76.0697 | 4 | 0 |
| 0.0000 | priority_arrival_clip | 6042.8705 | 6038.2000 | 666.7596 | 3.0000 | 8.2022 | -76.0697 | 4 | 0 |
| 0.0000 | global_downscale | 6042.8705 | 5371.4405 | 0.0000 | 3.0000 | 7.2908 | -67.6175 | 3233 | 0 |
| 1.0000 | online_fifo_clip | 4311.9955 | 4308.0750 | 475.1901 | 3.0000 | -68.7978 | -76.6947 | 4 | 0 |
| 1.0000 | priority_arrival_clip | 4311.9955 | 4308.0750 | 475.1901 | 3.0000 | -68.7978 | -76.6947 | 4 | 0 |
| 1.0000 | global_downscale | 4311.9955 | 3832.8849 | 0.0000 | 3.0000 | -61.1536 | -68.1731 | 3233 | 0 |
| 2.0000 | online_fifo_clip | 2581.1205 | 2577.9500 | 283.6207 | 3.0000 | -145.7978 | -77.3197 | 4 | 0 |
| 2.0000 | priority_arrival_clip | 2581.1205 | 2577.9500 | 283.6207 | 3.0000 | -145.7978 | -77.3197 | 4 | 0 |
| 2.0000 | global_downscale | 2581.1205 | 2294.3294 | 0.0000 | 3.0000 | -129.5981 | -68.7286 | 3233 | 0 |

Top implementable rows by pressure:

| pressure_bps | strategy | variant | capacity_policy | actual_total | desired_total | actual_vs_global_gain | actual_max_concurrent | worst_day | leg_worst | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 12659.8801 | 21447.8160 | 9800.1713 | 3.0000 | 67.8536 | -146.1132 | 242 | 26 |
| 0.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 12659.8801 | 21447.8160 | 9800.1713 | 3.0000 | 67.8536 | -146.1132 | 242 | 26 |
| 0.0000 | manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 12556.9297 | 21096.4649 | 9744.0677 | 3.0000 | 67.8536 | -146.1132 | 240 | 26 |
| 0.0000 | manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 12556.9297 | 21096.4649 | 9744.0677 | 3.0000 | 67.8536 | -146.1132 | 240 | 26 |
| 0.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | online_fifo_clip | 12466.5411 | 21223.4420 | 9636.7489 | 3.0000 | 62.9181 | -146.1132 | 225 | 26 |
| 1.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 9277.6301 | 16954.5660 | 7017.0213 | 3.0000 | -64.6215 | -147.1132 | 242 | 26 |
| 1.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 9277.6301 | 16954.5660 | 7017.0213 | 3.0000 | -64.6215 | -147.1132 | 242 | 26 |
| 1.0000 | manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 9180.6797 | 16625.7149 | 6963.9177 | 3.0000 | -64.6215 | -147.1132 | 240 | 26 |
| 1.0000 | manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 9180.6797 | 16625.7149 | 6963.9177 | 3.0000 | -64.6215 | -147.1132 | 240 | 26 |
| 1.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | online_fifo_clip | 9129.9161 | 16788.0670 | 6891.5072 | 3.0000 | -66.9223 | -147.1132 | 225 | 26 |
| 2.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 5895.3801 | 12461.3160 | 4233.8713 | 3.0000 | -263.6749 | -148.1132 | 242 | 26 |
| 2.0000 | manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 5895.3801 | 12461.3160 | 4233.8713 | 3.0000 | -263.6749 | -148.1132 | 242 | 26 |
| 2.0000 | manager_plus_q65_watcher | grid_g00_1_g10_2_g01_1_g11_5 | online_fifo_clip | 5817.7230 | 12391.7487 | 4165.4898 | 3.0000 | -276.3156 | -148.1132 | 224 | 26 |
| 2.0000 | manager_plus_q65_watcher | grid_g00_1_g10_2_g01_1_g11_5 | priority_arrival_clip | 5817.7230 | 12391.7487 | 4165.4898 | 3.0000 | -276.3156 | -148.1132 | 224 | 26 |
| 2.0000 | manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 5804.4297 | 12154.9649 | 4183.7677 | 3.0000 | -263.6749 | -148.1132 | 240 | 26 |

## C0 Implementable Capacity Leaders

These rows exclude `raw_no_cap` and the replacement proxy. They are the
rules that can be read as direct capacity-management diagnostics.

| strategy | variant | capacity_policy | actual_total | desired_total | actual_vs_global_gain | actual_max_concurrent | worst_day | leg_worst | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 12659.8801 | 21447.8160 | 9800.1713 | 3.0000 | 67.8536 | -146.1132 | 242 | 26 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 12659.8801 | 21447.8160 | 9800.1713 | 3.0000 | 67.8536 | -146.1132 | 242 | 26 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 12556.9297 | 21096.4649 | 9744.0677 | 3.0000 | 67.8536 | -146.1132 | 240 | 26 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 12556.9297 | 21096.4649 | 9744.0677 | 3.0000 | 67.8536 | -146.1132 | 240 | 26 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | online_fifo_clip | 12466.5411 | 21223.4420 | 9636.7489 | 3.0000 | 62.9181 | -146.1132 | 225 | 26 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | priority_arrival_clip | 12466.5411 | 21223.4420 | 9636.7489 | 3.0000 | 62.9181 | -146.1132 | 225 | 26 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | online_fifo_clip | 12363.5907 | 20872.0909 | 9580.6452 | 3.0000 | 62.9181 | -146.1132 | 223 | 26 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | priority_arrival_clip | 12363.5907 | 20872.0909 | 9580.6452 | 3.0000 | 62.9181 | -146.1132 | 223 | 26 |
| manager_plus_q65_watcher | grid_g00_1_g10_2_g01_1_g11_5 | online_fifo_clip | 12272.7230 | 21060.7487 | 9464.6232 | 3.0000 | 65.9222 | -146.1132 | 224 | 26 |
| manager_plus_q65_watcher | grid_g00_1_g10_2_g01_1_g11_5 | priority_arrival_clip | 12272.7230 | 21060.7487 | 9464.6232 | 3.0000 | 65.9222 | -146.1132 | 224 | 26 |
| manager_plus_q70_watcher | grid_g00_1_g10_2_g01_1_g11_5 | online_fifo_clip | 12169.7725 | 20709.3976 | 9408.5195 | 3.0000 | 65.9222 | -146.1132 | 222 | 26 |
| manager_plus_q70_watcher | grid_g00_1_g10_2_g01_1_g11_5 | priority_arrival_clip | 12169.7725 | 20709.3976 | 9408.5195 | 3.0000 | 65.9222 | -146.1132 | 222 | 26 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | online_fifo_clip | 8133.1985 | 8155.4407 | 2843.1829 | 3.0000 | 44.4010 | -76.0697 | 13 | 1 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | priority_arrival_clip | 8133.1985 | 8155.4407 | 2843.1829 | 3.0000 | 44.4010 | -76.0697 | 13 | 1 |
| manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | online_fifo_clip | 8126.3131 | 14080.6509 | 5779.5380 | 3.0000 | 41.8920 | -72.8987 | 172 | 19 |
| manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | priority_arrival_clip | 8126.3131 | 14080.6509 | 5779.5380 | 3.0000 | 41.8920 | -72.8987 | 172 | 19 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | online_fifo_clip | 8062.9283 | 8085.1705 | 2818.4934 | 3.0000 | 44.4010 | -76.0697 | 13 | 1 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | priority_arrival_clip | 8062.9283 | 8085.1705 | 2818.4934 | 3.0000 | 44.4010 | -76.0697 | 13 | 1 |
| manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | online_fifo_clip | 8023.3627 | 13799.5700 | 5723.4343 | 3.0000 | 41.8920 | -72.8987 | 170 | 19 |
| manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | priority_arrival_clip | 8023.3627 | 13799.5700 | 5723.4343 | 3.0000 | 41.8920 | -72.8987 | 170 | 19 |

## C0 Replacement Proxy Leaders

`priority_replace_terminal_proxy` is separated because it reallocates
open capacity using terminal-PnL information. It is useful for measuring
possible capacity loss, but it is not a live rule.

| strategy | variant | capacity_policy | actual_total | desired_total | actual_vs_global_gain | actual_max_concurrent | worst_day | leg_worst | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_replace_terminal_proxy | 12742.1297 | 21447.8160 | 9882.4209 | 3.0000 | 67.6842 | -146.1132 | 258 | 43 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_1_g11_5 | priority_replace_terminal_proxy | 12639.1792 | 21096.4649 | 9826.3173 | 3.0000 | 67.6842 | -146.1132 | 256 | 43 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | priority_replace_terminal_proxy | 12549.3240 | 21223.4420 | 9719.5317 | 3.0000 | 62.9181 | -146.1132 | 241 | 43 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_2_g01_0.75_g11_5 | priority_replace_terminal_proxy | 12446.3735 | 20872.0909 | 9663.4281 | 3.0000 | 62.9181 | -146.1132 | 239 | 43 |
| manager_plus_q65_watcher | grid_g00_1_g10_2_g01_1_g11_5 | priority_replace_terminal_proxy | 12364.8267 | 21060.7487 | 9556.7268 | 3.0000 | 65.9222 | -146.1132 | 240 | 42 |
| manager_plus_q70_watcher | grid_g00_1_g10_2_g01_1_g11_5 | priority_replace_terminal_proxy | 12261.8762 | 20709.3976 | 9500.6232 | 3.0000 | 65.9222 | -146.1132 | 238 | 42 |
| manager_plus_q65_watcher | anchor_full_1_0p75_0p25_4 | priority_replace_terminal_proxy | 8172.3915 | 14080.6509 | 5825.6163 | 3.0000 | 41.8920 | -72.8987 | 189 | 36 |
| manager_plus_q65_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | priority_replace_terminal_proxy | 8136.2357 | 8155.4407 | 2846.2201 | 3.0000 | 44.4010 | -76.0697 | 13 | 1 |
| manager_plus_q70_watcher | anchor_full_1_0p75_0p25_4 | priority_replace_terminal_proxy | 8069.4410 | 13799.5700 | 5769.5127 | 3.0000 | 41.8920 | -72.8987 | 187 | 36 |
| manager_plus_q70_watcher | grid_g00_1.25_g10_1_g01_0.75_g11_1 | priority_replace_terminal_proxy | 8065.9655 | 8085.1705 | 2821.5306 | 3.0000 | 44.4010 | -76.0697 | 13 | 1 |

## Raw Max Versus Capacity

| variant | capacity_policy | desired_total | actual_total | actual_vs_global_gain | desired_max_concurrent | actual_max_concurrent | clipped_legs | skipped_legs | worst_day | leg_worst |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| anchor_full_1_0p75_0p25_4 | global_downscale | 13799.5700 | 2299.9283 | 0.0000 | 18.0000 | 3.0000 | 3368 | 0 | 7.9016 | -32.2763 |
| anchor_full_1_0p75_0p25_4 | online_fifo_clip | 13799.5700 | 8023.3627 | 5723.4343 | 18.0000 | 3.0000 | 170 | 19 | 41.8920 | -72.8987 |
| anchor_full_1_0p75_0p25_4 | priority_arrival_clip | 13799.5700 | 8023.3627 | 5723.4343 | 18.0000 | 3.0000 | 170 | 19 | 41.8920 | -72.8987 |
| anchor_full_1_0p75_0p25_4 | priority_replace_terminal_proxy | 13799.5700 | 8069.4410 | 5769.5127 | 18.0000 | 3.0000 | 187 | 36 | 41.8920 | -72.8987 |
| anchor_full_1_0p75_0p25_4 | raw_no_cap | 13799.5700 | 13799.5700 | 11499.6417 | 18.0000 | 18.0000 | 0 | 0 | 47.4094 | -193.6578 |
| grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | global_downscale | 6042.8705 | 5371.4405 | 0.0000 | 3.3750 | 3.0000 | 3233 | 0 | 7.2908 | -67.6175 |
| grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | online_fifo_clip | 6042.8705 | 6038.2000 | 666.7596 | 3.3750 | 3.0000 | 4 | 0 | 8.2022 | -76.0697 |
| grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | priority_arrival_clip | 6042.8705 | 6038.2000 | 666.7596 | 3.3750 | 3.0000 | 4 | 0 | 8.2022 | -76.0697 |
| grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | priority_replace_terminal_proxy | 6042.8705 | 6038.2000 | 666.7596 | 3.3750 | 3.0000 | 4 | 0 | 8.2022 | -76.0697 |
| grid_g00_1.25_g10_0.75_g01_0_g11_0.75 | raw_no_cap | 6042.8705 | 6042.8705 | 671.4301 | 3.3750 | 3.3750 | 0 | 0 | 8.2022 | -76.0697 |
| grid_g00_1.25_g10_2_g01_1_g11_5 | global_downscale | 21096.4649 | 2812.8620 | 0.0000 | 22.5000 | 3.0000 | 3368 | 0 | 13.8552 | -32.2763 |
| grid_g00_1.25_g10_2_g01_1_g11_5 | online_fifo_clip | 21096.4649 | 12556.9297 | 9744.0677 | 22.5000 | 3.0000 | 240 | 26 | 67.8536 | -146.1132 |
| grid_g00_1.25_g10_2_g01_1_g11_5 | priority_arrival_clip | 21096.4649 | 12556.9297 | 9744.0677 | 22.5000 | 3.0000 | 240 | 26 | 67.8536 | -146.1132 |
| grid_g00_1.25_g10_2_g01_1_g11_5 | priority_replace_terminal_proxy | 21096.4649 | 12639.1792 | 9826.3173 | 22.5000 | 3.0000 | 256 | 43 | 67.6842 | -146.1132 |
| grid_g00_1.25_g10_2_g01_1_g11_5 | raw_no_cap | 21096.4649 | 21096.4649 | 18283.6029 | 22.5000 | 22.5000 | 0 | 0 | 103.9141 | -242.0723 |

## Cell Capacity Loss

| capacity_policy | cell | desired_total | actual_total | desired_exposure | actual_exposure | clipped_exposure | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| raw_no_cap | 00_none | 1935.3368 | 1935.3368 | 793.7500 | 793.7500 | 0.0000 | 0 | 0 |
| raw_no_cap | 10_r5_only | 2279.9815 | 2279.9815 | 700.5000 | 700.5000 | 0.0000 | 0 | 0 |
| raw_no_cap | 11_r5_frames | 1827.5522 | 1827.5522 | 236.6250 | 236.6250 | 0.0000 | 0 | 0 |
| global_downscale | 00_none | 1935.3368 | 1720.2994 | 793.7500 | 705.5556 | 88.1944 | 1234 | 0 |
| global_downscale | 10_r5_only | 2279.9815 | 2026.6503 | 700.5000 | 622.6667 | 77.8333 | 1796 | 0 |
| global_downscale | 11_r5_frames | 1827.5522 | 1624.4908 | 236.6250 | 210.3333 | 26.2917 | 203 | 0 |
| online_fifo_clip | 00_none | 1935.3368 | 1931.2755 | 793.7500 | 793.3750 | 0.3750 | 3 | 0 |
| online_fifo_clip | 10_r5_only | 2279.9815 | 2279.9815 | 700.5000 | 700.5000 | 0.0000 | 0 | 0 |
| online_fifo_clip | 11_r5_frames | 1827.5522 | 1826.9430 | 236.6250 | 236.2500 | 0.3750 | 1 | 0 |
| priority_arrival_clip | 00_none | 1935.3368 | 1931.2755 | 793.7500 | 793.3750 | 0.3750 | 3 | 0 |
| priority_arrival_clip | 10_r5_only | 2279.9815 | 2279.9815 | 700.5000 | 700.5000 | 0.0000 | 0 | 0 |
| priority_arrival_clip | 11_r5_frames | 1827.5522 | 1826.9430 | 236.6250 | 236.2500 | 0.3750 | 1 | 0 |
| priority_replace_terminal_proxy | 00_none | 1935.3368 | 1931.2755 | 793.7500 | 793.3750 | 0.3750 | 3 | 0 |
| priority_replace_terminal_proxy | 10_r5_only | 2279.9815 | 2279.9815 | 700.5000 | 700.5000 | 0.0000 | 0 | 0 |
| priority_replace_terminal_proxy | 11_r5_frames | 1827.5522 | 1826.9430 | 236.6250 | 236.2500 | 0.3750 | 1 | 0 |

## Largest Clipped Legs

| date | entry_row | cell | leg_kind | desired_exposure | actual_exposure | unit | capacity_pnl_delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-05-14 | 2328507 | 00_none | base | 0.6250 | 0.5000 | 25.8764 | 3.2345 |
| 2026-05-13 | 2116077 | 00_none | base | 2.5000 | 2.3750 | 12.4411 | 1.5551 |
| 2026-05-13 | 2121742 | 11_r5_frames | base | 1.5000 | 1.1250 | 1.6244 | 0.6092 |
| 2026-05-11 | 1868795 | 00_none | base | 2.5000 | 2.3750 | -5.8268 | -0.7283 |

## Interpretation

- `global_downscale` is a conservative lower bound because one peak interval
  scales down every leg in history.
- `online_fifo_clip` is closer to implementable capacity management: only
  crowded arrivals are clipped.
- `priority_replace_terminal_proxy` is not an execution rule yet. It is a
  diagnostic upper/proxy because replacing an open leg needs path PnL at
  the replacement timestamp.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_capacity_manager_summary_20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_capacity_manager_cell_20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_capacity_manager_daily_20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_capacity_manager_clipped_legs_20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_capacity_manager_summary_20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_capacity_manager.py
```

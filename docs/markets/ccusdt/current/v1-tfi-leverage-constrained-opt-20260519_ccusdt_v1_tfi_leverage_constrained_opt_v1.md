# CCUSDT V1 TFI Leverage-Constrained Optimization

Status: `20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1`.

Guardrail: `research_only_leverage_constrained_strategy_no_execution_recommendation`.

## Question

This pass asks whether `01_frames_only` was removed because it lacks edge,
or because the old cell-level gamma model let crowded intervals punish all
`01` entries globally.

The leverage constraint is modeled directly:

$$
L(t)=\sum_{i:t_i\le t<u_i}\widetilde w_i\le K,\qquad K=3.
$$

The candidate structure is:

$$
w_i^{core}=b_i\gamma_{c_i}^{core},\qquad c_i\in\{00,10,11\},
$$

$$
w_i^{01}=\mathbf 1_{\{c_i=01\}}\min\left(
b_i\gamma_{01},\ [K-L(t_i^-)-m]_+
\right).
$$

`m` is an idle-capacity reserve. This is deliberately modest: it does not
use terminal PnL, and it does not replace already-open 01 exposure.

## Core Baseline

| dataset | pressure_bps | actual_total | exact_simple_bp_units | approx_account_simple_return | worst_day | positive_days | days | leg_worst | actual_max_concurrent | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| historical | 0.0000 | 6038.2000 | 6059.3525 | 0.8291 | 8.2022 | 14 | 14 | -76.0697 | 3.0000 | 4 | 0 |
| historical | 1.0000 | 4308.0750 | 4328.7081 | 0.5385 | -68.7978 | 11 | 14 | -76.6947 | 3.0000 | 4 | 0 |
| historical | 2.0000 | 2577.9500 | 2598.2368 | 0.2941 | -145.7978 | 8 | 14 | -77.3197 | 3.0000 | 4 | 0 |
| oos_2026_05_18 | 0.0000 | 415.8276 | 416.6424 | 0.0425 | 415.8276 | 1 | 1 | -21.1977 | 3.0000 | 3 | 1 |
| oos_2026_05_18 | 1.0000 | 257.7026 | 258.4837 | 0.0261 | 257.7026 | 1 | 1 | -23.0727 | 3.0000 | 3 | 1 |
| oos_2026_05_18 | 2.0000 | 99.5776 | 100.3407 | 0.0100 | 99.5776 | 1 | 1 | -24.9477 | 3.0000 | 3 | 1 |

## Historical C0 Idle-01 Sleeve

| candidate | gamma01_frames_only | reserve | actual_total | delta_vs_core | worst_day | positive_days | days | leg_worst | actual_max_concurrent | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| idle01_g1_r0 | 1.0000 | 0.0000 | 6907.5648 | 869.3648 | 48.3285 | 14 | 14 | -84.5942 | 3.0000 | 29 | 1 |
| idle01_g1_r0.25 | 1.0000 | 0.2500 | 6902.9457 | 864.7457 | 48.3285 | 14 | 14 | -84.5942 | 3.0000 | 29 | 1 |
| idle01_g1_r0.5 | 1.0000 | 0.5000 | 6896.9761 | 858.7761 | 48.3285 | 14 | 14 | -84.5942 | 3.0000 | 32 | 9 |
| idle01_g0.75_r0 | 0.7500 | 0.0000 | 6719.8637 | 681.6637 | 38.2969 | 14 | 14 | -76.0697 | 3.0000 | 12 | 1 |
| idle01_g0.75_r0.25 | 0.7500 | 0.2500 | 6715.0973 | 676.8973 | 38.2969 | 14 | 14 | -76.0697 | 3.0000 | 13 | 1 |
| idle01_g0.75_r0.5 | 0.7500 | 0.5000 | 6710.3309 | 672.1309 | 38.2969 | 14 | 14 | -76.0697 | 3.0000 | 13 | 2 |
| idle01_g0.5_r0.5 | 0.5000 | 0.5000 | 6498.9948 | 460.7948 | 28.2653 | 14 | 14 | -76.0697 | 3.0000 | 6 | 2 |
| idle01_g0.5_r0.25 | 0.5000 | 0.2500 | 6495.8688 | 457.6688 | 28.2653 | 14 | 14 | -76.0697 | 3.0000 | 6 | 1 |
| idle01_g0.5_r0 | 0.5000 | 0.0000 | 6492.7428 | 454.5428 | 28.2653 | 14 | 14 | -76.0697 | 3.0000 | 6 | 1 |
| idle01_g0.25_r0.5 | 0.2500 | 0.5000 | 6255.8878 | 217.6878 | 18.2337 | 14 | 14 | -76.0697 | 3.0000 | 5 | 2 |
| idle01_g0.25_r0.25 | 0.2500 | 0.2500 | 6252.7618 | 214.5618 | 18.2337 | 14 | 14 | -76.0697 | 3.0000 | 5 | 1 |
| idle01_g0.25_r0 | 0.2500 | 0.0000 | 6249.6359 | 211.4358 | 18.2337 | 14 | 14 | -76.0697 | 3.0000 | 4 | 1 |

Conservative sleeve rows requiring non-negative worst day, all positive
days, and single-leg worst better than `-100`:

| candidate | actual_total | delta_vs_core | worst_day | leg_worst | actual_max_concurrent | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| idle01_g1_r0 | 6907.5648 | 869.3648 | 48.3285 | -84.5942 | 3.0000 | 29 | 1 |
| idle01_g1_r0.25 | 6902.9457 | 864.7457 | 48.3285 | -84.5942 | 3.0000 | 29 | 1 |
| idle01_g1_r0.5 | 6896.9761 | 858.7761 | 48.3285 | -84.5942 | 3.0000 | 32 | 9 |
| idle01_g0.75_r0 | 6719.8637 | 681.6637 | 38.2969 | -76.0697 | 3.0000 | 12 | 1 |
| idle01_g0.75_r0.25 | 6715.0973 | 676.8973 | 38.2969 | -76.0697 | 3.0000 | 13 | 1 |
| idle01_g0.75_r0.5 | 6710.3309 | 672.1309 | 38.2969 | -76.0697 | 3.0000 | 13 | 2 |
| idle01_g0.5_r0.5 | 6498.9948 | 460.7948 | 28.2653 | -76.0697 | 3.0000 | 6 | 2 |
| idle01_g0.5_r0.25 | 6495.8688 | 457.6688 | 28.2653 | -76.0697 | 3.0000 | 6 | 1 |
| idle01_g0.5_r0 | 6492.7428 | 454.5428 | 28.2653 | -76.0697 | 3.0000 | 6 | 1 |
| idle01_g0.25_r0.5 | 6255.8878 | 217.6878 | 18.2337 | -76.0697 | 3.0000 | 5 | 2 |

## OOS 2026-05-18 C0 Check

| candidate | gamma01_frames_only | reserve | actual_total | delta_vs_core | exact_simple_bp_units | approx_account_simple_return | leg_worst | actual_max_concurrent | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| clean_core_only | 0.0000 | 0.0000 | 415.8276 | 0.0000 | 416.6424 | 0.0425 | -21.1977 | 3.0000 | 3 | 1 |
| idle01_g0.25_r0 | 0.2500 | 0.0000 | 430.1744 | 14.3467 | 430.9932 | 0.0440 | -21.1977 | 3.0000 | 3 | 1 |
| idle01_g0.5_r0 | 0.5000 | 0.0000 | 444.5211 | 28.6935 | 445.3441 | 0.0455 | -21.1977 | 3.0000 | 3 | 1 |
| idle01_g0.75_r0 | 0.7500 | 0.0000 | 458.8678 | 43.0402 | 459.6949 | 0.0470 | -21.1977 | 3.0000 | 3 | 1 |
| idle01_g1_r0 | 1.0000 | 0.0000 | 472.5926 | 56.7649 | 473.4236 | 0.0484 | -21.1977 | 3.0000 | 4 | 1 |

## Core Displacement

This asks whether the recovered `01` PnL mainly consumes idle leverage or
pushes out core exposure.

| dataset | candidate | core_exposure_base | core_exposure_after | core_exposure_delta | sleeve01_actual_exposure | core_displacement_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| historical | idle01_g0.25_r0 | 1730.1250 | 1729.6250 | -0.5000 | 57.8750 | 0.0086 |
| historical | idle01_g0.5_r0 | 1730.1250 | 1729.1250 | -1.0000 | 115.2500 | 0.0087 |
| historical | idle01_g0.75_r0 | 1730.1250 | 1728.6250 | -1.5000 | 168.1250 | 0.0089 |
| historical | idle01_g1_r0 | 1730.1250 | 1726.0000 | -4.1250 | 216.7500 | 0.0190 |
| oos_2026_05_18 | idle01_g0.25_r0 | 158.1250 | 158.1250 | 0.0000 | 4.3750 | -0.0000 |
| oos_2026_05_18 | idle01_g0.5_r0 | 158.1250 | 158.1250 | 0.0000 | 8.7500 | -0.0000 |
| oos_2026_05_18 | idle01_g0.75_r0 | 158.1250 | 158.1250 | 0.0000 | 13.1250 | -0.0000 |
| oos_2026_05_18 | idle01_g1_r0 | 158.1250 | 158.0000 | -0.1250 | 17.5000 | 0.0071 |

## Pressure References

| candidate | pressure_bps | actual_total | delta_vs_core | worst_day | leg_worst | positive_days | days | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| clean_core_only | 0.0000 | 6038.2000 | 0.0000 | 8.2022 | -76.0697 | 14 | 14 | 4 | 0 |
| idle01_g0.5_r0 | 0.0000 | 6492.7428 | 454.5428 | 28.2653 | -76.0697 | 14 | 14 | 6 | 1 |
| pressure_c2_shape_fifo | 0.0000 | 7598.5237 | 1560.3236 | 23.3630 | -91.3207 | 14 | 14 | 96 | 15 |
| clean_core_only | 1.0000 | 4308.0750 | 0.0000 | -68.7978 | -76.6947 | 11 | 14 | 4 | 0 |
| idle01_g0.5_r0 | 1.0000 | 4648.3678 | 340.2928 | -53.4847 | -76.6947 | 11 | 14 | 6 | 1 |
| pressure_c2_shape_fifo | 1.0000 | 5851.1487 | 1543.0736 | -95.6987 | -91.9457 | 11 | 14 | 96 | 15 |
| clean_core_only | 2.0000 | 2577.9500 | 0.0000 | -145.7978 | -77.3197 | 8 | 14 | 4 | 0 |
| idle01_g0.5_r0 | 2.0000 | 2803.9928 | 226.0428 | -135.2347 | -77.3197 | 9 | 14 | 6 | 1 |
| pressure_c2_shape_fifo | 2.0000 | 4103.7737 | 1525.8236 | -221.4487 | -92.5707 | 9 | 14 | 96 | 15 |

OOS 2026-05-18 pressure check:

| candidate | pressure_bps | actual_total | delta_vs_core | exact_simple_bp_units | approx_account_simple_return | leg_worst | clipped_legs | skipped_legs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| clean_core_only | 0.0000 | 415.8276 | 0.0000 | 416.6424 | 0.0425 | -21.1977 | 3 | 1 |
| idle01_g0.5_r0 | 0.0000 | 444.5211 | 28.6935 | 445.3441 | 0.0455 | -21.1977 | 3 | 1 |
| idle01_g1_r0 | 0.0000 | 472.5926 | 56.7649 | 473.4236 | 0.0484 | -21.1977 | 4 | 1 |
| clean_core_only | 1.0000 | 257.7026 | 0.0000 | 258.4837 | 0.0261 | -23.0727 | 3 | 1 |
| idle01_g0.5_r0 | 1.0000 | 277.6461 | 19.9435 | 278.4329 | 0.0282 | -23.0727 | 3 | 1 |
| idle01_g1_r0 | 1.0000 | 297.0926 | 39.3899 | 297.8850 | 0.0302 | -23.0727 | 4 | 1 |
| clean_core_only | 2.0000 | 99.5776 | 0.0000 | 100.3407 | 0.0100 | -24.9477 | 3 | 1 |
| idle01_g0.5_r0 | 2.0000 | 110.7711 | 11.1935 | 111.5384 | 0.0111 | -24.9477 | 3 | 1 |
| idle01_g1_r0 | 2.0000 | 121.5926 | 22.0149 | 122.3640 | 0.0122 | -24.9477 | 4 | 1 |

## Cell Contribution Snapshot

| candidate | cell | actual_total | actual_exposure | clipped_exposure |
| --- | --- | --- | --- | --- |
| clean_core_only | 00_none | 1931.2755 | 793.3750 | 0.3750 |
| clean_core_only | 10_r5_only | 2279.9815 | 700.5000 | 0.0000 |
| clean_core_only | 11_r5_frames | 1826.9430 | 236.2500 | 0.3750 |
| idle01_g0.25_r0 | 00_none | 1918.3373 | 792.8750 | 0.8750 |
| idle01_g0.25_r0 | 01_frames_only | 224.3740 | 57.8750 | 0.0000 |
| idle01_g0.25_r0 | 10_r5_only | 2279.9815 | 700.5000 | 0.0000 |
| idle01_g0.25_r0 | 11_r5_frames | 1826.9430 | 236.2500 | 0.3750 |
| idle01_g0.5_r0 | 00_none | 1930.8182 | 792.3750 | 1.3750 |
| idle01_g0.5_r0 | 01_frames_only | 455.0000 | 115.2500 | 0.5000 |
| idle01_g0.5_r0 | 10_r5_only | 2279.9815 | 700.5000 | 0.0000 |
| idle01_g0.5_r0 | 11_r5_frames | 1826.9430 | 236.2500 | 0.3750 |

## Interpretation

- `01` is not a dead cell; this script only changes whether it receives idle capacity.
- `gamma01=0` is a coarse global deletion; the sleeve version asks whether spare leverage can recover part of it.
- `core_idle01` is implementable as an admission rule, but it is still not a full margin-account or fill simulator.
- C=0 is the zero venue-fee baseline; C=1/C=2 remain pressure reserves.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_leverage_constrained_summary_20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_leverage_constrained_daily_20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_leverage_constrained_cell_20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_leverage_constrained_clipped_20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.csv`

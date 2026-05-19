# CCUSDT TFI Interpretable Grid Pareto

Status: `20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1`.

Guardrail: `research_only_interpretable_grid_walk_forward_pareto_no_execution_recommendation_no_alpha_claim`.

Cost mode: `stored_net`.

Scored entries: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_pretrade_scored_entries_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv`.

For the full zero-fee pipeline, first regenerate the scored entries with `ccusdt_v1_tfi_pretrade_identification.py --cost-mode zero_fee`, then run this Pareto script with `--scored-entries <that file> --cost-mode stored_net`. In that mode, `stored_net` already means the upstream label is `net := gross` and `cost := 0`, with rolling detectors and `R5` recomputed upstream.

This models the current Bullish CC/USDT promotional fee assumption only; it does not prove fill, latency, queue, or adverse-selection costs are zero.

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

## Main Read

Old anchor total `10172.4902`, worst day `144.1005`, positive days `9`.
Risk-score leader `g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none`: total `13928.6844`, mean `5.8417`, worst day `169.9167`, positive days `9`.
Worst-day leader `g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none`: total `13401.3408`, mean `5.9311`, worst day `272.6684`.

The frontier is still a sizing and selection research surface. `C=0` only removes the explicit fee/cost label from this replay; it does not remove spread crossing, fill probability, latency, or adverse-selection risk from a live implementation.

## Old Main Policy Anchor

| variant_id | gamma10 | gamma01 | gamma11 | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_0.75_g01_0.25_g11_4__strength_none__loss_none | 0.7500 | 0.2500 | 4.0000 | 10172.4902 | 6.1091 | 144.1005 | 245.8066 | 0.0000 | 9 | 1627 |

## Risk-Score Leaders

| variant_id | gamma10 | gamma01 | gamma11 | strength_kind | strength_metric | strength_q_low | strength_floor | loss_kind | loss_eta | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | risk_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 1.2500 | 0.7500 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13928.6844 | 5.8417 | 169.9167 | 340.4157 | 0.0000 | 9 | 13928.6844 |
| g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 1.2500 | 0.5000 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13732.9537 | 5.8751 | 177.5580 | 343.7357 | 0.0000 | 9 | 13732.9537 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13574.7523 | 6.0521 | 211.2932 | 331.3061 | 0.0000 | 9 | 13574.7523 |
| g00_0_g10_1.25_g01_0.25_g11_5__strength_none__loss_none | 1.2500 | 0.2500 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13537.2229 | 5.9098 | 185.1994 | 347.0557 | 0.0000 | 9 | 13537.2229 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.5000 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13474.1637 | 6.0640 | 211.2932 | 335.9860 | 0.0000 | 9 | 13474.1637 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed10_score_abs | 0.1000 | 0.0000 | none | 0.0000 | 13401.3408 | 5.9311 | 272.6684 | 390.9705 | 0.0000 | 9 | 13401.3408 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed10_delta | 0.1000 | 0.0000 | none | 0.0000 | 13390.1441 | 5.9311 | 272.6684 | 390.9705 | 0.0000 | 9 | 13390.1441 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.1_0.5_floor0.5__loss_none | 1.2500 | 0.7500 | 5.0000 | ramp | closed10_delta | 0.1000 | 0.5000 | none | 0.0000 | 13387.3960 | 6.0417 | 185.1867 | 340.3108 | 0.0000 | 9 | 13387.3960 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed5_score_abs | 0.1000 | 0.0000 | none | 0.0000 | 13386.8922 | 6.0169 | 211.2932 | 331.3061 | 0.0000 | 9 | 13386.8922 |
| g00_0_g10_1.25_g01_0.25_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.2500 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13373.5751 | 6.0761 | 211.2932 | 340.6658 | 0.0000 | 9 | 13373.5751 |
| g00_0_g10_1.25_g01_0_g11_5__strength_none__loss_none | 1.2500 | 0.0000 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13341.4922 | 5.9461 | 192.8407 | 350.3757 | 0.0000 | 9 | 13341.4922 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 1.2500 | 0.5000 | 5.0000 | hard | closed5_score_abs | 0.1000 | 0.0000 | none | 0.0000 | 13286.3036 | 6.0286 | 211.2932 | 335.9860 | 0.0000 | 9 | 13286.3036 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.2_0.5_floor0.5__loss_none | 1.2500 | 0.7500 | 5.0000 | ramp | closed10_delta | 0.2000 | 0.5000 | none | 0.0000 | 13286.2647 | 6.1073 | 177.0537 | 332.4262 | 0.0000 | 9 | 13286.2647 |
| g00_0_g10_1.25_g01_0_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.0000 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13272.9865 | 6.0885 | 211.2932 | 345.3456 | 0.0000 | 9 | 13272.9865 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_score_abs_q0.1_0.5_floor0.5__loss_none | 1.2500 | 0.7500 | 5.0000 | ramp | closed10_score_abs | 0.1000 | 0.5000 | none | 0.0000 | 13270.8050 | 6.0195 | 180.2215 | 337.8029 | 0.0000 | 9 | 13270.8050 |

## Total Leaders

| variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 13928.6844 | 5.8417 | 169.9167 | 340.4157 | 0.0000 | 9 | 2384.3750 |
| g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 13732.9537 | 5.8751 | 177.5580 | 343.7357 | 0.0000 | 9 | 2337.5000 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13574.7523 | 6.0521 | 211.2932 | 331.3061 | 0.0000 | 9 | 2243.0000 |
| g00_0_g10_1.25_g01_0.25_g11_5__strength_none__loss_none | 13537.2229 | 5.9098 | 185.1994 | 347.0557 | 0.0000 | 9 | 2290.6250 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13474.1637 | 6.0640 | 211.2932 | 335.9860 | 0.0000 | 9 | 2222.0000 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13401.3408 | 5.9311 | 272.6684 | 390.9705 | 0.0000 | 9 | 2259.5000 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 13390.1441 | 5.9311 | 272.6684 | 390.9705 | 0.0000 | 9 | 2257.6250 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.1_0.5_floor0.5__loss_none | 13387.3960 | 6.0417 | 185.1867 | 340.3108 | 0.0000 | 9 | 2215.8379 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 13386.8922 | 6.0169 | 211.2932 | 331.3061 | 0.0000 | 9 | 2224.8750 |
| g00_0_g10_1.25_g01_0.25_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13373.5751 | 6.0761 | 211.2932 | 340.6658 | 0.0000 | 9 | 2201.0000 |
| g00_0_g10_1.25_g01_0_g11_5__strength_none__loss_none | 13341.4922 | 5.9461 | 192.8407 | 350.3757 | 0.0000 | 9 | 2243.7500 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 13286.3036 | 6.0286 | 211.2932 | 335.9860 | 0.0000 | 9 | 2203.8750 |

## Worst-Day Leaders

| variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13401.3408 | 5.9311 | 272.6684 | 390.9705 | 0.0000 | 9 | 2259.5000 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 13390.1441 | 5.9311 | 272.6684 | 390.9705 | 0.0000 | 9 | 2257.6250 |
| g00_0_g10_1_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 12743.4362 | 6.0802 | 263.3930 | 356.4649 | 0.0000 | 9 | 2095.8750 |
| g00_0_g10_1_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 12735.0848 | 6.0795 | 263.3930 | 356.4649 | 0.0000 | 9 | 2094.7500 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13224.0488 | 5.9504 | 257.3004 | 382.9915 | 0.0000 | 9 | 2222.3750 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 13211.8423 | 5.9516 | 257.3004 | 382.9915 | 0.0000 | 9 | 2219.8750 |
| g00_0_g10_0.75_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 12085.5316 | 6.2546 | 254.1175 | 321.9593 | 0.0000 | 9 | 1932.2500 |
| g00_0_g10_0.75_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 12080.0255 | 6.2530 | 254.1175 | 321.9593 | 0.0000 | 9 | 1931.8750 |
| g00_0_g10_1_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 12566.1443 | 6.1038 | 248.0250 | 348.4860 | 0.0000 | 9 | 2058.7500 |
| g00_0_g10_1_g01_0.5_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 12556.7830 | 6.1044 | 248.0250 | 348.4860 | 0.0000 | 9 | 2057.0000 |
| g00_0_g10_0.5_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 11427.6270 | 6.4613 | 244.8420 | 287.4537 | 0.0000 | 9 | 1768.6250 |
| g00_0_g10_0.5_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 11424.9662 | 6.4584 | 244.8420 | 287.4537 | 0.0000 | 9 | 1769.0000 |

## Pareto Frontier: Total vs Worst Day

| pareto_rank_total_desc | variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 13928.6844 | 5.8417 | 169.9167 | 340.4157 | 0.0000 | 9 | 2384.3750 |
| 2 | g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 13732.9537 | 5.8751 | 177.5580 | 343.7357 | 0.0000 | 9 | 2337.5000 |
| 3 | g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13574.7523 | 6.0521 | 211.2932 | 331.3061 | 0.0000 | 9 | 2243.0000 |
| 4 | g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13401.3408 | 5.9311 | 272.6684 | 390.9705 | 0.0000 | 9 | 2259.5000 |

## Read

This is an interpretable frontier, not a black-box model. The old coefficient vector is included as an anchor, but the frontier lets the absolute-strength scaler and recent-loss suppressor compete jointly with the four state gammas.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_variants_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_pareto_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_daily_top_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.csv`

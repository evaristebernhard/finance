# CCUSDT TFI Interpretable Grid Pareto

Status: `20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_v1`.

Guardrail: `research_only_interpretable_grid_walk_forward_pareto_no_execution_recommendation_no_alpha_claim`.

Cost mode: `zero_fee`.

If `cost_mode=zero_fee`, the evaluation label is `net := gross` and `cost := 0`, and the `R5` cell gate is recomputed from zero-fee prior closed labels. This models the current Bullish CC/USDT promotional fee assumption only; it does not prove fill, latency, queue, or adverse-selection costs are zero.

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

Old anchor total `10165.2463`, worst day `144.1005`, positive days `9`.
Risk-score leader `g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none`: total `13916.6113`, mean `5.8412`, worst day `169.9167`, positive days `9`.
Worst-day leader `g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none`: total `13389.2677`, mean `5.9307`, worst day `272.6684`.

The frontier is still a sizing and selection research surface. `C=0` only removes the explicit fee/cost label from this replay; it does not remove spread crossing, fill probability, latency, or adverse-selection risk from a live implementation.

## Old Main Policy Anchor

| variant_id | gamma10 | gamma01 | gamma11 | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_0.75_g01_0.25_g11_4__strength_none__loss_none | 0.7500 | 0.2500 | 4.0000 | 10165.2463 | 6.1089 | 144.1005 | 245.8066 | 0.0000 | 9 | 1624 |

## Risk-Score Leaders

| variant_id | gamma10 | gamma01 | gamma11 | strength_kind | strength_metric | strength_q_low | strength_floor | loss_kind | loss_eta | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | risk_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 1.2500 | 0.7500 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13916.6113 | 5.8412 | 169.9167 | 340.4157 | 0.0000 | 9 | 13916.6113 |
| g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 1.2500 | 0.5000 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13720.8806 | 5.8746 | 177.5580 | 343.7357 | 0.0000 | 9 | 13720.8806 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13562.6792 | 6.0517 | 211.2932 | 331.3061 | 0.0000 | 9 | 13562.6792 |
| g00_0_g10_1.25_g01_0.25_g11_5__strength_none__loss_none | 1.2500 | 0.2500 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13525.1498 | 5.9094 | 185.1994 | 347.0557 | 0.0000 | 9 | 13525.1498 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.5000 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13462.0906 | 6.0637 | 211.2932 | 335.9860 | 0.0000 | 9 | 13462.0906 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed10_score_abs | 0.1000 | 0.0000 | none | 0.0000 | 13389.2677 | 5.9307 | 272.6684 | 390.9705 | 0.0000 | 9 | 13389.2677 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed10_delta | 0.1000 | 0.0000 | none | 0.0000 | 13378.0710 | 5.9307 | 272.6684 | 390.9705 | 0.0000 | 9 | 13378.0710 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.1_0.5_floor0.5__loss_none | 1.2500 | 0.7500 | 5.0000 | ramp | closed10_delta | 0.1000 | 0.5000 | none | 0.0000 | 13375.4077 | 6.0409 | 185.1867 | 340.3108 | 0.0000 | 9 | 13375.4077 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 1.2500 | 0.7500 | 5.0000 | hard | closed5_score_abs | 0.1000 | 0.0000 | none | 0.0000 | 13374.8191 | 6.0166 | 211.2932 | 331.3061 | 0.0000 | 9 | 13374.8191 |
| g00_0_g10_1.25_g01_0.25_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.2500 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13361.5020 | 6.0758 | 211.2932 | 340.6658 | 0.0000 | 9 | 13361.5020 |
| g00_0_g10_1.25_g01_0_g11_5__strength_none__loss_none | 1.2500 | 0.0000 | 5.0000 | none | none |  | 1.0000 | none | 0.0000 | 13329.4191 | 5.9457 | 192.8407 | 350.3757 | 0.0000 | 9 | 13329.4191 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.2_0.5_floor0.5__loss_none | 1.2500 | 0.7500 | 5.0000 | ramp | closed10_delta | 0.2000 | 0.5000 | none | 0.0000 | 13274.3203 | 6.1065 | 177.0537 | 332.4262 | 0.0000 | 9 | 13274.3203 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 1.2500 | 0.5000 | 5.0000 | hard | closed5_score_abs | 0.1000 | 0.0000 | none | 0.0000 | 13274.2305 | 6.0283 | 211.2932 | 335.9860 | 0.0000 | 9 | 13274.2305 |
| g00_0_g10_1.25_g01_0_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 1.2500 | 0.0000 | 5.0000 | hard | closed5_delta | 0.1000 | 0.0000 | none | 0.0000 | 13260.9134 | 6.0882 | 211.2932 | 345.3456 | 0.0000 | 9 | 13260.9134 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_score_abs_q0.1_0.5_floor0.5__loss_none | 1.2500 | 0.7500 | 5.0000 | ramp | closed10_score_abs | 0.1000 | 0.5000 | none | 0.0000 | 13259.0206 | 6.0191 | 180.2215 | 337.8029 | 0.0000 | 9 | 13259.0206 |

## Total Leaders

| variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 13916.6113 | 5.8412 | 169.9167 | 340.4157 | 0.0000 | 9 | 2382.5000 |
| g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 13720.8806 | 5.8746 | 177.5580 | 343.7357 | 0.0000 | 9 | 2335.6250 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13562.6792 | 6.0517 | 211.2932 | 331.3061 | 0.0000 | 9 | 2241.1250 |
| g00_0_g10_1.25_g01_0.25_g11_5__strength_none__loss_none | 13525.1498 | 5.9094 | 185.1994 | 347.0557 | 0.0000 | 9 | 2288.7500 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13462.0906 | 6.0637 | 211.2932 | 335.9860 | 0.0000 | 9 | 2220.1250 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13389.2677 | 5.9307 | 272.6684 | 390.9705 | 0.0000 | 9 | 2257.6250 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 13378.0710 | 5.9307 | 272.6684 | 390.9705 | 0.0000 | 9 | 2255.7500 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.1_0.5_floor0.5__loss_none | 13375.4077 | 6.0409 | 185.1867 | 340.3108 | 0.0000 | 9 | 2214.1405 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_score_abs_ge_q0.1__loss_none | 13374.8191 | 6.0166 | 211.2932 | 331.3061 | 0.0000 | 9 | 2223.0000 |
| g00_0_g10_1.25_g01_0.25_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13361.5020 | 6.0758 | 211.2932 | 340.6658 | 0.0000 | 9 | 2199.1250 |
| g00_0_g10_1.25_g01_0_g11_5__strength_none__loss_none | 13329.4191 | 5.9457 | 192.8407 | 350.3757 | 0.0000 | 9 | 2241.8750 |
| g00_0_g10_1.25_g01_0.75_g11_5__ramp_closed10_delta_q0.2_0.5_floor0.5__loss_none | 13274.3203 | 6.1065 | 177.0537 | 332.4262 | 0.0000 | 9 | 2173.8014 |

## Worst-Day Leaders

| variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13389.2677 | 5.9307 | 272.6684 | 390.9705 | 0.0000 | 9 | 2257.6250 |
| g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 13378.0710 | 5.9307 | 272.6684 | 390.9705 | 0.0000 | 9 | 2255.7500 |
| g00_0_g10_1_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 12733.7777 | 6.0800 | 263.3930 | 356.4649 | 0.0000 | 9 | 2094.3750 |
| g00_0_g10_1_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 12725.4263 | 6.0793 | 263.3930 | 356.4649 | 0.0000 | 9 | 2093.2500 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13211.9757 | 5.9500 | 257.3004 | 382.9915 | 0.0000 | 9 | 2220.5000 |
| g00_0_g10_1.25_g01_0.5_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 13199.7692 | 5.9512 | 257.3004 | 382.9915 | 0.0000 | 9 | 2218.0000 |
| g00_0_g10_0.75_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 12078.2878 | 6.2545 | 254.1175 | 321.9593 | 0.0000 | 9 | 1931.1250 |
| g00_0_g10_0.75_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 12072.7817 | 6.2529 | 254.1175 | 321.9593 | 0.0000 | 9 | 1930.7500 |
| g00_0_g10_1_g01_0.5_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 12556.4858 | 6.1035 | 248.0250 | 348.4860 | 0.0000 | 9 | 2057.2500 |
| g00_0_g10_1_g01_0.5_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 12547.1245 | 6.1042 | 248.0250 | 348.4860 | 0.0000 | 9 | 2055.5000 |
| g00_0_g10_0.5_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 11422.7978 | 6.4613 | 244.8420 | 287.4537 | 0.0000 | 9 | 1767.8750 |
| g00_0_g10_0.5_g01_0.75_g11_5__hard_closed10_delta_ge_q0.1__loss_none | 11420.1370 | 6.4584 | 244.8420 | 287.4537 | 0.0000 | 9 | 1768.2500 |

## Pareto Frontier: Total vs Worst Day

| pareto_rank_total_desc | variant_id | total_net | mean_net | worst_day_net | daily_cvar20 | max_drawdown | positive_days | exposure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | g00_0_g10_1.25_g01_0.75_g11_5__strength_none__loss_none | 13916.6113 | 5.8412 | 169.9167 | 340.4157 | 0.0000 | 9 | 2382.5000 |
| 2 | g00_0_g10_1.25_g01_0.5_g11_5__strength_none__loss_none | 13720.8806 | 5.8746 | 177.5580 | 343.7357 | 0.0000 | 9 | 2335.6250 |
| 3 | g00_0_g10_1.25_g01_0.75_g11_5__hard_closed5_delta_ge_q0.1__loss_none | 13562.6792 | 6.0517 | 211.2932 | 331.3061 | 0.0000 | 9 | 2241.1250 |
| 4 | g00_0_g10_1.25_g01_0.75_g11_5__hard_closed10_score_abs_ge_q0.1__loss_none | 13389.2677 | 5.9307 | 272.6684 | 390.9705 | 0.0000 | 9 | 2257.6250 |

## Read

This is an interpretable frontier, not a black-box model. The old coefficient vector is included as an anchor, but the frontier lets the absolute-strength scaler and recent-loss suppressor compete jointly with the four state gammas.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_variants_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_pareto_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_interpretable_grid_daily_top_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_v1.csv`

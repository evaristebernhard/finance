# CCUSDT CKS-L1 OFI Diagnostic

Status: `ccusdt_cks_l1_ofi_diagnostic_v0_1`.

Boundary: research-only. The diagnostic reads canonical quote/decision/trade/L2 data and optional baseline entries only for overlay; labels are diagnostic-only and must not enter Runner/Bot runtime.

## Core Formula

For completed best bid/ask states before and after an L2 event batch:

```text
e_n = 1{P_B[n] >= P_B[n-1]} q_B[n]
    - 1{P_B[n] <= P_B[n-1]} q_B[n-1]
    - 1{P_A[n] <= P_A[n-1]} q_A[n]
    + 1{P_A[n] >= P_A[n-1]} q_A[n-1]
```

Positive OFI means best-bid demand strengthened or best-ask supply weakened. Negative OFI means the opposite.

## Setup

- symbol: `CCUSDT`
- dates: `2026-05-16..2026-05-18`
- event rows: `378908`
- decision panel rows: `1515620`
- output: `systems\ccusdt_replay_exchange\runs\cks_ofi_l1_diagnostic\ccusdt_2026-05-16_2026-05-18_v0_1`
- primary 1s OFI status: `spread_cost_mirage`

## Factor Summary

| window_ms | factor | factor_class | n | spearman_mid | spearman_exec | top_bottom_mid_bps | top_bottom_exec_bps | daily_sign_rate | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5000 | ofi_l1_z | cks_l1_total | 378905 | 0.1046 | 0.0793 | 3.0757 | -0.5856 | 0.0000 | spread_cost_mirage |
| 5000 | ofi_l1_raw | cks_l1_total | 378905 | 0.1121 | 0.0875 | 3.0323 | -0.6200 | 0.0000 | spread_cost_mirage |
| 1000 | ofi_l1_z | cks_l1_total | 378905 | 0.0840 | 0.0735 | 2.4552 | -0.8529 | 0.0000 | spread_cost_mirage |
| 1000 | ofi_l1_raw | cks_l1_total | 378905 | 0.0942 | 0.0981 | 2.4233 | -0.8679 | 0.0000 | spread_cost_mirage |
| 50 | ofi_l1_notional_norm | cks_l1_total | 378905 | 0.0736 | 0.1079 | 1.8812 | -0.9126 | 0.0000 | spread_cost_mirage |
| 50 | ofi_l1_depth_norm | cks_l1_total | 378905 | 0.0736 | 0.1080 | 1.8787 | -0.9140 | 0.0000 | spread_cost_mirage |
| 200 | ofi_l1_notional_norm | cks_l1_total | 378905 | 0.0765 | 0.1082 | 1.8660 | -0.9157 | 0.0000 | spread_cost_mirage |
| 200 | ofi_l1_depth_norm | cks_l1_total | 378905 | 0.0765 | 0.1083 | 1.8587 | -0.9193 | 0.0000 | spread_cost_mirage |
| 1000 | ofi_l1_depth_norm | cks_l1_total | 378905 | 0.0858 | 0.1113 | 1.9412 | -0.9214 | 0.0000 | spread_cost_mirage |
| 1000 | ofi_l1_notional_norm | cks_l1_total | 378905 | 0.0858 | 0.1113 | 1.9362 | -0.9239 | 0.0000 | spread_cost_mirage |
| 5000 | ofi_l1_notional_norm | cks_l1_total | 378905 | 0.0985 | 0.1037 | 2.1202 | -0.9289 | 0.0000 | spread_cost_mirage |
| 5000 | ofi_l1_depth_norm | cks_l1_total | 378905 | 0.0985 | 0.1038 | 2.1151 | -0.9318 | 0.0000 | spread_cost_mirage |
| 200 | ofi_l1_z | cks_l1_total | 378905 | 0.0665 | 0.0660 | 1.9479 | -1.0830 | 0.0000 | spread_cost_mirage |
| 200 | ofi_l1_raw | cks_l1_total | 378905 | 0.0797 | 0.0934 | 1.9065 | -1.0933 | 0.0000 | spread_cost_mirage |
| 50 | ofi_l1_raw | cks_l1_total | 378905 | 0.0747 | 0.0924 | 1.8257 | -1.1180 | 0.0000 | spread_cost_mirage |
| 50 | ofi_l1_z | cks_l1_total | 378905 | 0.0644 | 0.0733 | 1.7804 | -1.1440 | 0.0000 | spread_cost_mirage |
| 50 | ofi_l5_research_only | l5_research_only | 378905 | 0.0325 | 0.0581 | 1.2314 | -1.4108 | 0.0000 | spread_cost_mirage |
| 200 | ofi_l5_research_only | l5_research_only | 378905 | 0.0329 | 0.0545 | 1.1949 | -1.4279 | 0.0000 | spread_cost_mirage |
| 1000 | ofi_l5_research_only | l5_research_only | 378905 | 0.0321 | 0.0447 | 1.0415 | -1.5361 | 0.0000 | spread_cost_mirage |
| 5000 | ofi_l5_research_only | l5_research_only | 378905 | 0.0218 | 0.0081 | 0.6137 | -1.8508 | 0.0000 | spread_cost_mirage |

## OFI vs TFI Cells

| window_ms | tfi_ofi_cell | n | mean_mid60_bps | mean_exec60_bps | hit_rate_exec60 | worst_day_exec60_bps |
| --- | --- | --- | --- | --- | --- | --- |
| 50 | OFI_only_quote_pressure | 45659 | 0.3025 | -1.4577 | 0.3212 | -2.0748 |
| 50 | TFI_against_OFI | 4459 | -0.8555 | -2.8516 | 0.3046 | -4.6303 |
| 50 | TFI_aligned_OFI | 11844 | 4.4207 | 2.2005 | 0.5455 | 1.7549 |
| 50 | TFI_only_active_pressure | 24818 | 0.5963 | -1.8098 | 0.3697 | -2.2037 |
| 50 | TFI_strong_OFI_weak | 3619 | 2.9992 | 0.8966 | 0.4946 | -0.4259 |
| 50 | TFI_weak_OFI_strong | 634 | 4.3455 | 2.0371 | 0.4890 | 0.1675 |
| 50 | weak_or_mixed | 287872 | 0.3049 | -2.0139 | 0.2628 | -2.0683 |
| 200 | OFI_only_quote_pressure | 53347 | 0.5023 | -1.2682 | 0.3291 | -1.8138 |
| 200 | TFI_against_OFI | 5269 | -0.9106 | -2.8728 | 0.3105 | -4.6222 |
| 200 | TFI_aligned_OFI | 16192 | 3.4511 | 1.2053 | 0.5117 | 0.2356 |
| 200 | TFI_only_active_pressure | 19418 | 0.5329 | -1.9025 | 0.3566 | -2.2403 |
| 200 | TFI_strong_OFI_weak | 3861 | 2.6723 | 0.4638 | 0.4716 | -0.6019 |
| 200 | TFI_weak_OFI_strong | 833 | 3.4249 | 1.0989 | 0.4466 | -1.4295 |
| 200 | weak_or_mixed | 279985 | 0.2993 | -2.0012 | 0.2613 | -2.0604 |
| 1000 | OFI_only_quote_pressure | 79562 | 0.7139 | -1.0650 | 0.3361 | -1.7277 |
| 1000 | TFI_against_OFI | 5422 | -0.9600 | -2.9287 | 0.3148 | -5.0327 |
| 1000 | TFI_aligned_OFI | 28664 | 2.4347 | 0.1509 | 0.4659 | -0.8200 |
| 1000 | TFI_only_active_pressure | 7189 | 0.4196 | -2.1017 | 0.3266 | -2.4676 |
| 1000 | TFI_strong_OFI_weak | 3465 | 1.3758 | -1.0072 | 0.4130 | -1.3575 |
| 1000 | TFI_weak_OFI_strong | 1268 | 1.4269 | -0.9267 | 0.4069 | -1.8608 |
| 1000 | weak_or_mixed | 253335 | 0.3170 | -1.9710 | 0.2577 | -2.0676 |
| 5000 | OFI_only_quote_pressure | 156535 | 0.7845 | -1.0744 | 0.3253 | -1.5534 |
| 5000 | TFI_against_OFI | 4941 | -0.9698 | -3.2194 | 0.3078 | -7.3453 |
| 5000 | TFI_aligned_OFI | 38291 | 2.1813 | -0.1075 | 0.4455 | -0.6012 |
| 5000 | TFI_only_active_pressure | 244 | 0.5899 | -1.9399 | 0.3689 | -3.3516 |
| 5000 | TFI_strong_OFI_weak | 1264 | 1.8661 | -0.6239 | 0.3987 | -1.4633 |
| 5000 | TFI_weak_OFI_strong | 1468 | -0.7292 | -3.1117 | 0.3542 | -3.7420 |
| 5000 | weak_or_mixed | 176162 | 0.3909 | -2.0399 | 0.2470 | -2.2638 |

## Channel Summary

| window_ms | factor | factor_class | top_bottom_mid_bps | top_bottom_exec_bps | status |
| --- | --- | --- | --- | --- | --- |
| 5000 | ofi_l1_raw | total | 3.0323 | -0.6200 | spread_cost_mirage |
| 1000 | ofi_l1_raw | total | 2.4233 | -0.8679 | spread_cost_mirage |
| 200 | ofi_l1_raw | total | 1.9065 | -1.0933 | spread_cost_mirage |
| 50 | ofi_l1_raw | total | 1.8257 | -1.1180 | spread_cost_mirage |
| 50 | ofi_add_l1 | add |  |  | not_supported_insufficient_variation |
| 200 | ofi_add_l1 | add |  |  | not_supported_insufficient_variation |
| 1000 | ofi_add_l1 | add |  |  | not_supported_insufficient_variation |
| 5000 | ofi_add_l1 | add |  |  | not_supported_insufficient_variation |
| 50 | ofi_cancel_l1 | cancel |  |  | not_supported_insufficient_variation |
| 200 | ofi_cancel_l1 | cancel |  |  | not_supported_insufficient_variation |
| 1000 | ofi_cancel_l1 | cancel |  |  | not_supported_insufficient_variation |
| 5000 | ofi_cancel_l1 | cancel |  |  | not_supported_insufficient_variation |
| 50 | ofi_consume_l1 | consume |  |  | not_supported_insufficient_variation |
| 200 | ofi_consume_l1 | consume |  |  | not_supported_insufficient_variation |
| 1000 | ofi_consume_l1 | consume |  |  | not_supported_insufficient_variation |
| 5000 | ofi_consume_l1 | consume |  |  | not_supported_insufficient_variation |
| 5000 | ofi_residual_l1 | residual | 2.2912 | -0.9382 | spread_cost_mirage |
| 1000 | ofi_residual_l1 | residual | 1.7551 | -1.1714 | spread_cost_mirage |
| 200 | ofi_residual_l1 | residual | 1.3614 | -1.3435 | spread_cost_mirage |
| 50 | ofi_l5_research_only | l5_research_only | 1.2314 | -1.4108 | spread_cost_mirage |
| 200 | ofi_l5_research_only | l5_research_only | 1.1949 | -1.4279 | spread_cost_mirage |
| 50 | ofi_residual_l1 | residual | 1.1767 | -1.4303 | spread_cost_mirage |
| 1000 | ofi_l5_research_only | l5_research_only | 1.0415 | -1.5361 | spread_cost_mirage |
| 5000 | ofi_l5_research_only | l5_research_only | 0.6137 | -1.8508 | spread_cost_mirage |
| 5000 | ofi_quote_move_l1 | quote_move | 0.5397 | -1.8922 | spread_cost_mirage |
| 1000 | ofi_quote_move_l1 | quote_move | 0.3299 | -2.0008 | spread_cost_mirage |
| 200 | ofi_quote_move_l1 | quote_move | 0.2320 | -2.0518 | explanatory_valid |
| 50 | ofi_quote_move_l1 | quote_move | 0.2058 | -2.0659 | explanatory_valid |

## Candidate Rules

| rule_id | n | mean_mid60_bps | mean_exec60_bps | status | runtime_action |
| --- | --- | --- | --- | --- | --- |
| OFI_only_quote_pressure_w50 | 45659 | 0.3025 | -1.4577 | spread_cost_mirage | none_research_only |
| TFI_against_OFI_w50 | 4459 | -0.8555 | -2.8516 | veto_candidate | none_research_only |
| TFI_aligned_OFI_w50 | 11844 | 4.4207 | 2.2005 | confirmation_candidate | none_research_only |
| TFI_strong_OFI_weak_w50 | 3619 | 2.9992 | 0.8966 | tfi_only_control | none_research_only |
| TFI_weak_OFI_strong_w50 | 634 | 4.3455 | 2.0371 | independent_entry_watchlist | none_research_only |
| OFI_only_quote_pressure_w200 | 53347 | 0.5023 | -1.2682 | spread_cost_mirage | none_research_only |
| TFI_against_OFI_w200 | 5269 | -0.9106 | -2.8728 | veto_candidate | none_research_only |
| TFI_aligned_OFI_w200 | 16192 | 3.4511 | 1.2053 | confirmation_candidate | none_research_only |
| TFI_strong_OFI_weak_w200 | 3861 | 2.6723 | 0.4638 | tfi_only_control | none_research_only |
| TFI_weak_OFI_strong_w200 | 833 | 3.4249 | 1.0989 | independent_entry_watchlist | none_research_only |
| OFI_only_quote_pressure_w1000 | 79562 | 0.7139 | -1.0650 | spread_cost_mirage | none_research_only |
| TFI_against_OFI_w1000 | 5422 | -0.9600 | -2.9287 | veto_candidate | none_research_only |
| TFI_aligned_OFI_w1000 | 28664 | 2.4347 | 0.1509 | confirmation_candidate | none_research_only |
| TFI_strong_OFI_weak_w1000 | 3465 | 1.3758 | -1.0072 | spread_cost_mirage | none_research_only |
| TFI_weak_OFI_strong_w1000 | 1268 | 1.4269 | -0.9267 | spread_cost_mirage | none_research_only |
| OFI_only_quote_pressure_w5000 | 156535 | 0.7845 | -1.0744 | spread_cost_mirage | none_research_only |
| TFI_against_OFI_w5000 | 4941 | -0.9698 | -3.2194 | veto_candidate | none_research_only |
| TFI_aligned_OFI_w5000 | 38291 | 2.1813 | -0.1075 | spread_cost_mirage | none_research_only |
| TFI_strong_OFI_weak_w5000 | 1264 | 1.8661 | -0.6239 | spread_cost_mirage | none_research_only |
| TFI_weak_OFI_strong_w5000 | 1468 | -0.7292 | -3.1117 | not_supported_executable_negative | none_research_only |

## Interpretation Rules

- `explanatory_valid` means OFI describes same/near-window price movement; it is not enough for trading.
- `predictive_mid_valid` means mid labels improve before crossing cost.
- `executable_valid` means top-of-book taker labels also survive.
- `spread_cost_mirage` means mid improves but crossing destroys the result.
- `confirmation_candidate` / `veto_candidate` / `independent_entry_watchlist` are research labels only.

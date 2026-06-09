# CCUSDT Microstructure Tree Diagnostic v0.1

Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.

## Scope

- symbol: `CCUSDT`
- from_date: `2026-05-16`
- to_date: `2026-05-18`
- source: `decision_frame`
- fold_mode: `leave_one_day_out`
- horizon_sec: `60`
- release_sec: `10`
- max_train_rows: `120000`
- model: `{'type': 'ExtraTreesRegressor_pair_long_short', 'n_estimators': 48, 'max_depth': 5, 'min_samples_leaf': 500, 'max_features': 0.7, 'random_state': 20260601}`
- out_dir: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\microstructure_tree_diagnostic\ccusdt_2026-05-16_2026-05-18_decision_frame_leave_one_day_out_v0_1`

Interpretation: each tree predicts long-side and short-side future values separately from runtime-safe feature columns. The chosen diagnostic side is the side with higher predicted value. These future values are labels only; they are not runtime inputs.

## OOS Metrics

| label | test date | train dates | n train | n test | edge rho | side rho | top mean | top-bottom | cvar05 | long share |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| decay_avoidance_60s_after_mfe | 2026-05-16 | 2026-05-17,2026-05-18 | 82115 | 132317 | 0.0918 | 0.0593 | 0.1652 | 3.8266 | -30.1779 | 0.5190 |
| decay_avoidance_60s_after_mfe | 2026-05-17 | 2026-05-16,2026-05-18 | 87950 | 114813 | 0.0241 | 0.0502 | -0.4649 | 1.1992 | -23.7023 | 0.3296 |
| decay_avoidance_60s_after_mfe | 2026-05-18 | 2026-05-16,2026-05-17 | 82377 | 131531 | 0.0167 | 0.0676 | 0.0091 | 1.1714 | -19.4822 | 0.4328 |
| decay_avoidance_60s_after_mfe | ALL_OOS | leave_one_day_out |  | 378661 | 0.0411 | 0.0503 | -0.2139 | 1.8969 | -24.2452 | 0.4316 |
| mid_terminal_60s | 2026-05-16 | 2026-05-17,2026-05-18 | 82115 | 132317 | 0.0420 | 0.0708 | 1.2892 | 1.1969 | -32.2033 | 0.5207 |
| mid_terminal_60s | 2026-05-17 | 2026-05-16,2026-05-18 | 87950 | 114813 | 0.0365 | 0.0651 | 1.1796 | 1.0782 | -31.5915 | 0.3298 |
| mid_terminal_60s | 2026-05-18 | 2026-05-16,2026-05-17 | 82377 | 131531 | 0.0473 | 0.0853 | 1.4591 | 1.4314 | -20.0253 | 0.4538 |
| mid_terminal_60s | ALL_OOS | leave_one_day_out |  | 378661 | 0.0393 | 0.0676 | 1.2644 | 1.2895 | -28.1618 | 0.4396 |
| release_mfe_10s | 2026-05-16 | 2026-05-17,2026-05-18 | 82175 | 132381 | 0.3109 | 0.1349 | 3.8360 | 3.0598 | 0.0000 | 0.5143 |
| release_mfe_10s | 2026-05-17 | 2026-05-16,2026-05-18 | 87996 | 114917 | 0.2564 | 0.1410 | 2.4257 | 1.8698 | 0.0000 | 0.4610 |
| release_mfe_10s | 2026-05-18 | 2026-05-16,2026-05-17 | 82433 | 131607 | 0.2038 | 0.1317 | 1.8787 | 1.2608 | 0.0000 | 0.6003 |
| release_mfe_10s | ALL_OOS | leave_one_day_out |  | 378905 | 0.2546 | 0.1347 | 2.7526 | 1.9876 | 0.0000 | 0.5280 |
| top_of_book_executable_60s | 2026-05-16 | 2026-05-17,2026-05-18 | 82115 | 132317 | 0.1056 | 0.0687 | -1.0806 | 1.4706 | -37.3397 | 0.4715 |
| top_of_book_executable_60s | 2026-05-17 | 2026-05-16,2026-05-18 | 87950 | 114813 | 0.0889 | 0.0569 | -1.3479 | 0.7326 | -37.0968 | 0.3329 |
| top_of_book_executable_60s | 2026-05-18 | 2026-05-16,2026-05-17 | 82377 | 131531 | 0.1633 | 0.0701 | -0.4465 | 2.4180 | -22.4815 | 0.4816 |
| top_of_book_executable_60s | ALL_OOS | leave_one_day_out |  | 378661 | 0.1184 | 0.0605 | -0.9738 | 1.4700 | -33.0486 | 0.4330 |

## Top Feature Importances

### decay_avoidance_60s_after_mfe

| feature | mean importance |
|---|---:|
| `past_event_25_bps__r10_log_ratio` | 0.105948 |
| `past_event_25_bps__r5_log_ratio` | 0.103946 |
| `TFI__raw` | 0.089827 |
| `queue_imbalance_1__r10_log_ratio` | 0.046969 |
| `past_event_25_bps__r5_z` | 0.043587 |
| `TFI__r10_log_ratio` | 0.039099 |
| `spread_bps__raw` | 0.038646 |
| `queue_imbalance_1__r5_log_ratio` | 0.037571 |
| `TFI__r10_delta` | 0.033919 |
| `TFI__r10_z` | 0.032132 |
| `queue_imbalance_1__r5_z` | 0.030096 |
| `queue_imbalance_1__raw` | 0.029867 |

### mid_terminal_60s

| feature | mean importance |
|---|---:|
| `past_event_25_bps__r5_log_ratio` | 0.178225 |
| `past_event_25_bps__r10_log_ratio` | 0.152241 |
| `queue_imbalance_1__raw` | 0.069073 |
| `spread_bps__raw` | 0.046752 |
| `TFI__raw` | 0.043876 |
| `frames_since_mid_change__raw` | 0.041999 |
| `past_event_25_bps__r5_z` | 0.034214 |
| `queue_imbalance_1__r5_z` | 0.034114 |
| `queue_imbalance_1__r5_energy_delta_side` | 0.032087 |
| `queue_imbalance_1__r5_delta` | 0.030841 |
| `queue_imbalance_1__r10_delta` | 0.030138 |
| `queue_imbalance_1__r10_z` | 0.029033 |

### release_mfe_10s

| feature | mean importance |
|---|---:|
| `TFI__raw` | 0.204849 |
| `past_event_25_bps__r5_log_ratio` | 0.063208 |
| `TFI__r5_z` | 0.060122 |
| `TFI__r10_log_ratio` | 0.052832 |
| `TFI__r10_delta` | 0.051640 |
| `TFI__r5_delta` | 0.045123 |
| `past_event_25_bps__r5_z` | 0.042140 |
| `TFI__r5_log_ratio` | 0.041497 |
| `TFI__r5_energy_delta_side` | 0.040460 |
| `past_event_25_bps__raw` | 0.037466 |
| `past_event_25_bps__r5_energy_delta_side` | 0.037231 |
| `past_event_25_bps__r10_z` | 0.034410 |

### top_of_book_executable_60s

| feature | mean importance |
|---|---:|
| `spread_bps__raw` | 0.239716 |
| `past_event_25_bps__r5_log_ratio` | 0.124224 |
| `past_event_25_bps__r10_log_ratio` | 0.114815 |
| `queue_imbalance_1__raw` | 0.057427 |
| `top_depth_quote_min__raw` | 0.037512 |
| `TFI__raw` | 0.036949 |
| `queue_imbalance_1__r5_z` | 0.032097 |
| `past_event_25_bps__r5_z` | 0.029980 |
| `past_event_25_bps__r10_z` | 0.028174 |
| `queue_imbalance_1__r5_energy_delta_side` | 0.027393 |
| `queue_imbalance_1__r5_delta` | 0.025540 |
| `frames_since_mid_change__raw` | 0.024997 |

## Boundary

- Tree outputs are diagnostics for non-linear interaction structure.
- Runner still must not read labels; Bot still must not read `date/` or derived future diagnostics.
- A positive release model does not imply executable edge; top-of-book executable labels must be checked separately.

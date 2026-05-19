# MON/USDC V1 Path-Regime Report

Status: `20260511_path_regime_v1` from source `20260511_reconstruct_v1` and features `20260511_factor_map_v1`.

这份报告只重打 path-label 并生成 regime summary；不使用 RPC，不修改 raw data，也不声称这是可执行交易规则。价格参考仍使用 minute VWAP/reference，入场点固定为事件后 1 分钟。

## 成本与 Barrier

- 成本公式：`C_e = 2f + 2eta + g_e + rho_e`
- 默认参数：one-way fee `30` bps，one-way slippage `25` bps，risk buffer `25` bps
- baseline barrier：`B+ = B- = C_e + 0.5 * sigma_e`
- `5m/15m/1h` 使用 `trailing_realized_vol_1h`，`3h/6h` 使用 `trailing_realized_vol_6h`

## Coverage

- execution rows: `2147000`
- physical rows: `2147000`
- joined research events: `2147000`
- missing physical rows: `0`
- minute price rows: `125368`
- label rows written: `10735000`

## Baseline Summary

| Horizon | Rows | dead_zone | tradable_path | continuation | reversal | risk_first | Median Cost bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 15m | 2147000 | 90.82% | 7.68% | 3.89% | 3.79% | 1.49% | 135.9290 |
| 1h | 2147000 | 59.67% | 36.84% | 18.33% | 18.51% | 3.45% | 135.9290 |
| 3h | 2147000 | 25.50% | 71.41% | 35.43% | 35.98% | 2.92% | 135.9290 |
| 5m | 2147000 | 98.63% | 1.02% | 0.54% | 0.48% | 0.35% | 135.9290 |
| 6h | 2147000 | 12.74% | 85.70% | 42.58% | 43.11% | 1.28% | 135.9290 |

## Barrier Sensitivity

| Profile | Horizon | Rows | dead_zone | tradable_path | risk_first |
| --- | --- | ---: | ---: | ---: | ---: |
| cost_only | 15m | 2147000 | 90.82% | 9.17% | 0.00% |
| cost_only | 1h | 2147000 | 59.67% | 40.29% | 0.00% |
| cost_only | 3h | 2147000 | 25.50% | 74.33% | 0.00% |
| cost_only | 5m | 2147000 | 98.63% | 1.37% | 0.00% |
| cost_only | 6h | 2147000 | 12.74% | 86.97% | 0.00% |
| vol_half | 15m | 2147000 | 90.82% | 7.68% | 1.49% |
| vol_half | 1h | 2147000 | 59.67% | 36.84% | 3.45% |
| vol_half | 3h | 2147000 | 25.50% | 71.41% | 2.92% |
| vol_half | 5m | 2147000 | 98.63% | 1.02% | 0.35% |
| vol_half | 6h | 2147000 | 12.74% | 85.70% | 1.28% |
| vol_one | 15m | 2147000 | 90.82% | 6.44% | 2.72% |
| vol_one | 1h | 2147000 | 59.67% | 33.69% | 6.60% |
| vol_one | 3h | 2147000 | 25.50% | 68.57% | 5.76% |
| vol_one | 5m | 2147000 | 98.63% | 0.80% | 0.57% |
| vol_one | 6h | 2147000 | 12.74% | 84.33% | 2.64% |

## Outputs

- `date/mon_usdc_v1_path_regime_summary_20260511_path_regime_v1.csv`
- `date/mon_usdc_v1_path_regime_sensitivity_20260511_path_regime_v1.csv`
- `date/mon_usdc_v1_path_regime_completion_20260511_path_regime_v1.json`
- `data/mon_usdc/v1/derived/mon_usdc_event_path_regime_labels/dt=20260511-p/mon_usdc_mon_usdc_event_path_regime_labels_20260511_path_regime_v1_h5m.parquet`
- `data/mon_usdc/v1/derived/mon_usdc_event_path_regime_labels/dt=20260511-p/mon_usdc_mon_usdc_event_path_regime_labels_20260511_path_regime_v1_h15m.parquet`
- `data/mon_usdc/v1/derived/mon_usdc_event_path_regime_labels/dt=20260511-p/mon_usdc_mon_usdc_event_path_regime_labels_20260511_path_regime_v1_h1h.parquet`
- `data/mon_usdc/v1/derived/mon_usdc_event_path_regime_labels/dt=20260511-p/mon_usdc_mon_usdc_event_path_regime_labels_20260511_path_regime_v1_h3h.parquet`
- `data/mon_usdc/v1/derived/mon_usdc_event_path_regime_labels/dt=20260511-p/mon_usdc_mon_usdc_event_path_regime_labels_20260511_path_regime_v1_h6h.parquet`

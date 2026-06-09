# CCUSDT Factor Method Sweep

Status: `20260517_ccusdt_method_sweep_v1` from source panel `20260517_ccusdt_fixed_factors_v3`.

Guardrail: `research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim`.

This report is a broad diagnostic sweep over the fixed snapshot-frame orderbook panel. It is not queue-position fill evidence, not a live execution simulation, and not an alpha claim.

## Scope

- Panel rows loaded: `2,606,830`.
- Candidate features: `72`.
- Forward targets: `11` across event-count and wall-clock horizons.
- Statistical sample rows: `220,000`; MI sample rows: `30,000`; model sample rows: `120,000`.

Methods tried: Pearson, Spearman, decile top-bottom, decile monotonicity, directional AUC, mutual information, chronological split stability, daily sign consistency, within-day shuffle controls, reversed-time controls, past-return leakage probes, Ridge, Huber, histogram gradient boosting, random forest, logistic direction classifiers, and LightGBM when installed.

## Data Semantics

| Metric | Value |
| --- | --- |
| days | 17 |
| rows | 2,606,830 |
| snapshot rate | 100.00% |
| median daily distinct mids | 674 |
| median quote-change rate | 3.80% |
| median top-size-change rate | 84.63% |
| median trade-present rate | 9.64% |
| max stable quote run | 1353 frames / 1153.3s |
| max stable mid run | 1353 frames / 1153.3s |

The important read is that CCUSDT is a snapshot-frame panel: long unchanged best bid/ask runs are common, while top-of-book sizes and depth can keep drifting. Event-count labels therefore mix actual quote changes with many zero-return frames.

## Target Activity

| Target | Rows | Nonzero | Abs P90 bps | Abs P99 bps |
| --- | --- | --- | --- | --- |
| fwd_time_900s_bps | 2580984 | 98.19% | 48.6438 | 145.5170 |
| fwd_event_500_bps | 2598330 | 95.20% | 25.6764 | 71.8533 |
| fwd_time_300s_bps | 2598099 | 95.16% | 26.9090 | 82.1623 |
| fwd_event_250_bps | 2602580 | 89.96% | 18.3854 | 49.5613 |
| fwd_time_60s_bps | 2605069 | 75.62% | 12.4415 | 38.6316 |
| fwd_event_70_bps | 2605640 | 67.11% | 8.5553 | 26.2972 |
| fwd_event_25_bps | 2606405 | 42.26% | 5.5058 | 16.9884 |
| fwd_time_10s_bps | 2606520 | 35.43% | 5.0658 | 17.7279 |
| fwd_event_10_bps | 2606660 | 24.43% | 1.6790 | 11.1700 |
| fwd_event_5_bps | 2606745 | 15.22% | 0.3415 | 6.8766 |
| fwd_event_1_bps | 2606813 | 4.22% | 0.0000 | 3.7458 |

## Top Single-Factor Diagnostics

| Target | Feature | Family | Spearman | AUC | Top-Bottom bps | MI | Score |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fwd_event_25_bps | trade_flow_imbalance | trade_arrival | 0.2685 | 0.6512 | 2.2128 | 0.051848 | 39.84 |
| fwd_time_10s_bps | trade_flow_imbalance | trade_arrival | 0.2475 | 0.6405 | 2.1375 | 0.062414 | 37.05 |
| fwd_event_10_bps | trade_flow_imbalance | trade_arrival | 0.2253 | 0.6342 | 1.2405 | 0.066006 | 32.72 |
| fwd_event_70_bps | trade_flow_imbalance | trade_arrival | 0.1841 | 0.5981 | 2.7564 | 0.044199 | 29.71 |
| fwd_time_60s_bps | trade_flow_imbalance | trade_arrival | 0.1437 | 0.5720 | 3.6670 | 0.031801 | 25.94 |
| fwd_event_250_bps | trade_flow_imbalance | trade_arrival | 0.1045 | 0.5429 | 3.8191 | 0.032376 | 20.88 |
| fwd_time_10s_bps | mlofi_roll10_l1 | MLOFI | 0.0883 | 0.5726 | 1.1288 | 0.047544 | 20.54 |
| fwd_event_25_bps | mlofi_roll10_l1 | MLOFI | 0.0887 | 0.5685 | 1.1173 | 0.055244 | 20.53 |
| fwd_event_70_bps | mlofi_roll10_l1 | MLOFI | 0.0736 | 0.5454 | 1.6636 | 0.062947 | 18.95 |
| fwd_time_10s_bps | mlofi_roll10_l25 | MLOFI | 0.0777 | 0.5638 | 1.2157 | 0.060132 | 18.79 |
| fwd_time_10s_bps | mlofi_roll10_l10 | MLOFI | 0.0760 | 0.5620 | 1.1098 | 0.061730 | 18.49 |
| fwd_event_25_bps | mlofi_roll10_l25 | MLOFI | 0.0785 | 0.5603 | 1.1712 | 0.065650 | 18.06 |

## Stability

| Target | Feature | Validation IC | Forward IC | Daily Sign | Score |
| --- | --- | --- | --- | --- | --- |
| fwd_event_25_bps | trade_flow_imbalance | 0.2445 | 0.3017 | 100.00% | 38.34 |
| fwd_time_10s_bps | trade_flow_imbalance | 0.2240 | 0.2757 | 100.00% | 35.50 |
| fwd_event_10_bps | trade_flow_imbalance | 0.1836 | 0.2701 | 100.00% | 33.09 |
| fwd_event_70_bps | trade_flow_imbalance | 0.1774 | 0.1905 | 100.00% | 27.20 |
| fwd_time_60s_bps | trade_flow_imbalance | 0.1678 | 0.1370 | 100.00% | 22.98 |
| fwd_event_5_bps | trade_flow_imbalance | 0.0868 | 0.1595 | 88.24% | 19.92 |
| fwd_event_25_bps | trade_arrival_alignment | 0.0993 | 0.1452 | 88.24% | 19.54 |
| fwd_event_250_bps | trade_flow_imbalance | 0.1265 | 0.1116 | 94.12% | 18.84 |
| fwd_time_10s_bps | trade_arrival_alignment | 0.0891 | 0.1299 | 82.35% | 17.66 |
| fwd_event_25_bps | mlofi_roll10_l2 | 0.0746 | 0.1259 | 100.00% | 17.55 |

## Negative Controls

| Target | Feature | Control | Control IC | Original IC | Abs Ratio |
| --- | --- | --- | --- | --- | --- |
| fwd_event_25_bps | trade_flow_imbalance | past_return_leakage_probe | 0.7485 | 0.2685 | 2.79 |
| fwd_time_10s_bps | trade_flow_imbalance | past_return_leakage_probe | 0.7223 | 0.2475 | 2.92 |
| fwd_event_10_bps | trade_flow_imbalance | past_return_leakage_probe | 0.7921 | 0.2253 | 3.52 |
| fwd_event_70_bps | trade_flow_imbalance | past_return_leakage_probe | 0.5998 | 0.1841 | 3.26 |
| fwd_time_60s_bps | trade_flow_imbalance | past_return_leakage_probe | 0.4675 | 0.1437 | 3.25 |
| fwd_event_250_bps | trade_flow_imbalance | past_return_leakage_probe | 0.3716 | 0.1045 | 3.55 |
| fwd_time_10s_bps | mlofi_roll10_l1 | past_return_leakage_probe | 0.3238 | 0.0883 | 3.67 |
| fwd_event_25_bps | mlofi_roll10_l1 | past_return_leakage_probe | 0.2916 | 0.0887 | 3.29 |
| fwd_event_70_bps | mlofi_roll10_l1 | past_return_leakage_probe | 0.0619 | 0.0736 | 0.84 |
| fwd_time_10s_bps | mlofi_roll10_l25 | past_return_leakage_probe | 0.4452 | 0.0777 | 5.73 |

Controls near the original score are treated as artifact warnings. In this panel, past-return and reversed-time controls are especially useful because slow quote changes can make state variables look predictive in both directions of time.

## Model Readout

| Target | Model | Kind | Rows | Forward IC | AUC | Top-Bottom bps |
| --- | --- | --- | --- | --- | --- | --- |
| fwd_event_25_bps | lightgbm_direction | classification | 18986 | 0.1894 | 0.6466 | 3.0254 |
| fwd_event_25_bps | random_forest_direction | classification | 18986 | 0.1922 | 0.6352 | 2.5183 |
| fwd_event_25_bps | hist_gradient_boosting_direction | classification | 18986 | 0.1687 | 0.6346 | 3.0159 |
| fwd_event_25_bps | logistic_l2_direction | classification | 18986 | 0.1534 | 0.6217 | 2.8900 |
| fwd_event_25_bps | random_forest_regression | regression | 35283 | 0.1100 | 0.5736 | 2.3246 |
| fwd_event_70_bps | random_forest_direction | classification | 27965 | 0.1027 | 0.5650 | 2.4385 |
| fwd_event_70_bps | huber_regression | regression | 35270 | 0.0834 | 0.5636 | 2.5379 |
| fwd_event_25_bps | hist_gradient_boosting_regression | regression | 35283 | 0.0893 | 0.5620 | 1.4897 |
| fwd_event_25_bps | lightgbm_regression | regression | 35283 | 0.0916 | 0.5620 | 1.7500 |
| fwd_event_25_bps | ridge_regression | regression | 35283 | 0.0930 | 0.5613 | 1.9850 |

## Output Tables

- `date\ccusdt_v1_factor_method_sweep_quality_20260517_ccusdt_method_sweep_v1.csv`
- `date\ccusdt_v1_factor_method_sweep_targets_20260517_ccusdt_method_sweep_v1.csv`
- `date\ccusdt_v1_factor_method_sweep_single_factor_20260517_ccusdt_method_sweep_v1.csv`
- `date\ccusdt_v1_factor_method_sweep_stability_20260517_ccusdt_method_sweep_v1.csv`
- `date\ccusdt_v1_factor_method_sweep_negative_controls_20260517_ccusdt_method_sweep_v1.csv`
- `date\ccusdt_v1_factor_method_sweep_models_20260517_ccusdt_method_sweep_v1.csv`
- `date\ccusdt_v1_factor_method_sweep_summary_20260517_ccusdt_method_sweep_v1.json`

## Current Read

Best single-factor score is `trade_flow_imbalance` on `fwd_event_25_bps`, but CCUSDT must be read as a snapshot-frame diagnostic panel. Most promising stable diagnostic: `trade_flow_imbalance on fwd_event_25_bps (forward IC 0.3017)`. Model readout: `lightgbm_direction on fwd_event_25_bps (AUC 0.6466, IC 0.1894)`. Artifact warnings from controls: `60` high-ratio rows. Treat MLOFI/depth/trade-arrival findings as information structure to inspect, not as executable fill evidence.

## Reproduce

```powershell
python scripts/ccusdt_factor_method_sweep.py
```

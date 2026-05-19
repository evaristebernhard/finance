# BONK CEX V3 Leakage Audit

Status: 2026-05-13. Read-only audit over the canonical BONK V3 label/context panel and current V3 scripts.

## Inputs And Outputs

Input panel:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date/bonk_v3_leakage_audit_static_scan.csv
date/bonk_v3_leakage_audit_panel_checks.csv
date/bonk_v3_leakage_audit_label_mismatches.csv
date/bonk_v3_leakage_audit_fold_thresholds.csv
date/bonk_v3_leakage_audit_findings.csv
date/bonk_v3_leakage_audit_summary.json
```

## Summary

- High issues: 1
- Medium issues: 0
- Low notes: 3

## Findings

| severity | issue | file:line | detail |
| --- | --- | --- | --- |
| high | future_return_reconstructs_from_future_price | `crates/cex_l2_research/src/report.rs:1679` | max_abs_diff_bps=200.077; label builder accepts idx+horizon row when timestamp delta is not shorter than horizon, so missing minutes can make the final-return timestamp later than exact horizon |
| low | fold_thresholds_train_only_verified | `scripts/bonk_v3_*.py` | computed fold split has no overlap and minimum embargo is 721 minutes |
| low | leaky_threshold_counterfactual | `date/bonk_v3_leakage_audit_fold_thresholds.csv` | largest absolute train-cut vs all-to-validation-cut delta is 72.9144; nonzero deltas mean global thresholds would leak regime information |
| low | same_minute_context_present | `data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet` | trailing context columns are same-minute features by construction; valid only if decision time is after minute close |

## Passing Panel Checks

| check | rows | detail |
| --- | ---: | --- |
| duplicate_panel_keys | 482760 | duplicate rows by symbol,timestamp_us,horizon_hours,barrier_bps |
| ok_label_rows_available | 482760 | ok rows at barrier 100: 118553 |
| future_context_excludes_current_h1 | 19941 | max_exclude_diff=2.27374e-13; include_current_better_rows=0 |
| future_context_excludes_current_h4 | 19490 | max_exclude_diff=9.66338e-13; include_current_better_rows=0 |
| future_context_excludes_current_h12 | 18530 | max_exclude_diff=2.27374e-12; include_current_better_rows=0 |

## Threshold Leakage Counterfactual

| gate component | factor | max all-to-val cut delta | min embargo minutes |
| --- | --- | ---: | ---: |
| cv_spread_high | `cross_venue_spread_diff_bps` | 0.0952772 | 721 |
| cv_spread_low | `cross_venue_spread_diff_bps` | 0.0951957 | 721 |
| depth_high | `top_depth_total_notional_median` | 72.9144 | 721 |
| microprice_low | `microprice_offset_bps_mean` | 0.0377504 | 721 |
| rv_low | `ctx_bonk_rv_1h_bps` | 3.8635 | 721 |
| snapshot_microprice_low | `snapshot_microprice_offset_bps_mean` | 0.0662602 | 721 |

## Read

The static predictor lists used by the current tree/gate V3 scripts do not include direct future or label columns as predictors. The panel does intentionally carry future label/residual columns, so downstream scripts must continue to keep `TARGET_COLUMNS`, `BASE_COLUMNS`, and outcome diagnostics out of model feature lists.

The concrete high-severity label issue is horizon drift in path labels when L2 minute rows are missing: `future_return_bps` can reflect the `idx + horizon_minutes` row rather than the exact timestamp horizon. This is label quality risk, not predictor leakage.

The remaining residual risk is timing semantics: L2 and context predictors are minute-bar features, so they are only valid for a decision made after the minute has closed. The future-context reconstruction check verifies the future BONK context target excludes the current minute.

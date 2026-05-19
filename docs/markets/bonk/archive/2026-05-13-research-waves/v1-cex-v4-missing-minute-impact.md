# BONK CEX V4 Missing-Minute Impact

Status: 2026-05-13. Run tag: `20260513_bullish_l2_basket_price_v1`.

This is a data-quality impact audit for the V4 orderbook research queue. It does not promote a trading rule.

## Inputs And Outputs

Inputs:

```text
data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_path_labels/bonk_path_labels_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date/bonk_v4_missing_minute_impact_20260513_bullish_l2_basket_price_v1_symbol_quality.csv
date/bonk_v4_missing_minute_impact_20260513_bullish_l2_basket_price_v1_gap_runs.csv
date/bonk_v4_missing_minute_impact_20260513_bullish_l2_basket_price_v1_label_impact.csv
date/bonk_v4_missing_minute_impact_20260513_bullish_l2_basket_price_v1_gate_impact.csv
date/bonk_v4_missing_minute_impact_20260513_bullish_l2_basket_price_v1_summary.json
```

## Method

- Missing minutes are measured on the observed Bullish L2 minute state, per symbol, against a one-minute grid between each symbol's first and last observed minute.
- Label drift is measured by comparing each ok label against the exact timestamp endpoint and the row-offset endpoint implied by the existing labels.
- A near-horizon endpoint is considered available if any observed minute is within `5` minutes of the exact target timestamp.
- Gate exposure uses the same fold splits and train-side tertile gates as the V3 gate diagnostics.

## BONK Minute Coverage

| symbol | observed_minutes | expected_minutes | missing_minutes | coverage_rate | gap_run_count | max_gap_missing_minutes | sparse_l2_rate | low_update_rate | zero_trade_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 20103 | 20160 | 57 | 99.72% | 3 | 27 | 0.25% | 0.47% | 2.32% |
| BONK1MUSDT | 20127 | 20160 | 33 | 99.84% | 5 | 19 | 0.03% | 0.11% | 30.62% |

## Sparse Symbols

| symbol | observed_minutes | expected_minutes | missing_minutes | coverage_rate | sparse_l2_rate | zero_trade_rate | median_book_ticker_count | median_snapshot_count | median_trade_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WIFUSDC | 78 | 11992 | 11914 | 0.65% | 100.00% | 100.00% | 1.000 | 0.000 | 0.000 |
| SHIB1MUSDC | 78 | 11991 | 11913 | 0.65% | 100.00% | 100.00% | 1.000 | 0.000 | 0.000 |
| PEPE1MUSDC | 78 | 11990 | 11912 | 0.65% | 100.00% | 100.00% | 1.000 | 0.000 | 0.000 |
| DOGEUSDC | 18986 | 20161 | 1175 | 94.17% | 7.92% | 99.07% | 9.000 | 13.000 | 0.000 |
| PENGUUSDC | 19407 | 20161 | 754 | 96.26% | 2.93% | 0.48% | 21.000 | 21.000 | 24.000 |
| SUIUSDC | 20046 | 20161 | 115 | 99.43% | 7.60% | 81.34% | 15.000 | 66.000 | 0.000 |
| BONK1MUSDC | 20103 | 20160 | 57 | 99.72% | 0.25% | 2.32% | 63.000 | 69.000 | 12.000 |
| SOLUSDC | 20119 | 20161 | 42 | 99.79% | 0.39% | 2.13% | 74.000 | 91.000 | 36.000 |
| BONK1MUSDT | 20127 | 20160 | 33 | 99.84% | 0.03% | 30.62% | 79.000 | 89.000 | 1.000 |
| ETHUSDC | 20130 | 20161 | 31 | 99.85% | 0.12% | 1.34% | 107.0 | 159.0 | 50.000 |
| BTCUSDC | 20130 | 20160 | 30 | 99.85% | 0.07% | 0.27% | 116.0 | 155.0 | 88.000 |

## Label Horizon Drift

| symbol | horizon_hours | selected_rows | exact_endpoint_missing_rate | near_endpoint_missing_rate | row_offset_drift_rate | exact_return_mismatch_rate | affected_exact_or_near_rate | median_abs_exact_return_diff_bps | p95_abs_exact_return_diff_bps | max_row_offset_drift_minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 1 | 20012 | 0.44% | 0.13% | 0.60% | 0.28% | 0.60% | 0.000 | 0.000 | 46.000 |
| BONK1MUSDC | 4 | 19833 | 0.18% | 0.01% | 1.98% | 1.88% | 1.98% | 0.000 | 0.000 | 46.000 |
| BONK1MUSDC | 12 | 19353 | 0.15% | 0.01% | 4.51% | 4.39% | 4.51% | 0.000 | 0.000 | 46.000 |
| BONK1MUSDT | 1 | 20065 | 0.17% | 0.05% | 0.62% | 0.44% | 0.62% | 0.000 | 0.000 | 22.000 |
| BONK1MUSDT | 4 | 19885 | 0.06% | 0.01% | 1.99% | 1.87% | 1.99% | 0.000 | 0.000 | 22.000 |
| BONK1MUSDT | 12 | 19405 | 0.06% | 0.01% | 4.51% | 4.41% | 4.51% | 0.000 | 0.000 | 22.000 |

## Active Gate Exposure

| fold | gate | base_rows | selected_rows | selected_share | selected_affected_exact_or_near_rows | selected_affected_exact_or_near_rate | affected_exact_or_near_rate_lift | selected_row_offset_drift_nonzero_rows | selected_exact_return_mismatch_rows | selected_exact_endpoint_missing_rows | selected_near_endpoint_missing_rows | selected_near_observed_gap_rate | near_observed_gap_rate_lift | selected_sparse_l2_minute_rate | sparse_l2_minute_rate_lift | selected_zero_trade_minute_rate | zero_trade_minute_rate_lift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | depth_high+rv_low | 3589 | 42 | 1.17% | 0 | 0.00% | 0.000 | 0 | 0 | 0 | 0 | 0.00% | 0.000 | 0.00% | n/a | 16.67% | 0.634 |
| fold2 | depth_high+rv_low+cv_spread | 3589 | 18 | 0.50% | 0 | 0.00% | 0.000 | 0 | 0 | 0 | 0 | 0.00% | 0.000 | 0.00% | n/a | 22.22% | 0.845 |
| fold3 | depth_high+rv_low | 4320 | 660 | 15.28% | 0 | 0.00% | n/a | 0 | 0 | 0 | 0 | 0.00% | n/a | 0.00% | 0.000 | 21.36% | 0.813 |
| fold3 | depth_high+rv_low+cv_spread | 4320 | 407 | 9.42% | 0 | 0.00% | n/a | 0 | 0 | 0 | 0 | 0.00% | n/a | 0.00% | 0.000 | 22.36% | 0.851 |

## Read

- The primary fold2/fold3 BONK1MUSDT H4 active gates have `0` affected rows out of `1127` selected rows (`0.00%`). Exact endpoints are missing for `0` selected rows; near endpoints are missing for `0` selected rows.
- `label_impact` was computed over `120690` barrier-100 path-label rows, then merged back to the gate panel by symbol, minute, and horizon.
- Sparse non-BONK symbols are mostly cross-section/context coverage constraints; do not use them as evidence that BONK gates are robust.

## Robust Conclusions

- BONK1MUSDC and BONK1MUSDT have high observed-minute coverage across the analyzed window, so the main gate rows are not built on broadly empty minute grids.
- Sparse-symbol issues are obvious and separable: PEPE1MUSDC, SHIB1MUSDC, and WIFUSDC are too thin for cross-section placebo reads in this window.
- Active gate missingness can be audited directly from the panel; the new `gate_impact` output gives row counts rather than relying on visual inspection.

## Data-Quality-Sensitive Conclusions

- Existing path labels are row-offset labels, so missing minutes can move the effective endpoint later than the exact timestamp horizon.
- H4 gate conclusions remain quality-sensitive until exact endpoint labels are rebuilt and the gate diagnostics are rerun from those labels.
- Any edge concentrated in rows with exact-horizon mismatch, missing near endpoints, or unusually sparse current-minute L2 state should stay in `research_state`, not `validation_candidate`.

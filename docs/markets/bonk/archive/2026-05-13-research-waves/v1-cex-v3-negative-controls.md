# BONK V3 Gate Negative Controls

Status: 2026-05-13. This is a robustness probe over the existing BONK V3 panel. It does not output trading rules, entries, exits, sizing, or alpha claims.

## Inputs And Outputs

Inputs:

```text
data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date\bonk_v3_gate_negative_controls_20260513_bullish_l2_basket_price_v1_folds.csv
date\bonk_v3_gate_negative_controls_20260513_bullish_l2_basket_price_v1_random_phase.csv
date\bonk_v3_gate_negative_controls_20260513_bullish_l2_basket_price_v1_summary.csv
date\bonk_v3_gate_negative_controls_20260513_bullish_l2_basket_price_v1_completion.json
docs\markets\bonk\v1-cex-v3-negative-controls.md
```

## Method

- `run_tag`: `20260513_bullish_l2_basket_price_v1`.
- Slice: `BONK1MUSDC` / `BONK1MUSDT`, `4h`, `100 bps`, `label_status=ok`.
- Focus gates: USDT `depth_high+rv_low`, USDT `depth_high+rv_low+cv_spread`, plus USDC mirror watch gates.
- Gate thresholds are low/high tertile cuts fit on the train side of each fold, then applied to validation rows.
- Summary decisions use fold2/fold3 only. Fold rows include fold1 for audit.
- Random phase control uses `200` circular-shift replicates per gate/fold with deterministic seed `20260513`.
- Effective sample count is the selected row count after one row per 4h stride.

## Actual Fold2/Fold3 Gates

| gate | status | rows | eff | share | resid edge | dir edge | rand p95 | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC_H4_depth_high_rv_low | watch_mirror_base_gate | 675 | 4 | 8.5% | 6.3% | -10.0% | 21.4% | fail_not_above_random_phase_controls |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | watch_mirror_combo_gate | 321 | 3 | 4.1% | 22.4% | 10.0% | 25.3% | fail_sparse_actual_gate |
| BONK1MUSDT_H4_depth_high_rv_low | active_base_gate | 760 | 4 | 9.6% | 11.7% | -4.1% | 27.4% | fail_not_above_random_phase_controls |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | active_combo_gate | 499 | 3 | 6.3% | 20.6% | 5.8% | 24.2% | fail_sparse_actual_gate |


## Time-Shift Controls

| gate | control | detail | rows | resid edge | actual-control | read |
| --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-1440m | 293 | 4.8% | 1.4% | mixed_actual_only_slightly_above_time_shift_future |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-240m | 655 | 17.5% | -11.2% | fail_time_shift_future_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-720m | 489 | 4.5% | 1.7% | mixed_actual_only_slightly_above_time_shift_future |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_past | features_shifted_by_1440m | 454 | -12.3% | 18.6% | pass_actual_above_time_shift_past |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_past | features_shifted_by_240m | 668 | 9.5% | -3.2% | fail_time_shift_past_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_past | features_shifted_by_720m | 567 | 15.4% | -9.2% | fail_time_shift_past_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | time_shift_future | features_shifted_by_-1440m | 87 | 4.4% | 18.0% | pass_actual_above_time_shift_future |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | time_shift_future | features_shifted_by_-240m | 313 | 26.9% | -4.5% | fail_time_shift_future_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | time_shift_future | features_shifted_by_-720m | 213 | 17.4% | 5.0% | mixed_actual_only_slightly_above_time_shift_future |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | time_shift_past | features_shifted_by_1440m | 275 | -9.8% | 32.2% | pass_actual_above_time_shift_past |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | time_shift_past | features_shifted_by_240m | 321 | 16.5% | 5.9% | pass_actual_above_time_shift_past |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | time_shift_past | features_shifted_by_720m | 305 | 15.6% | 6.8% | pass_actual_above_time_shift_past |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-1440m | 286 | 4.0% | 7.7% | pass_actual_above_time_shift_future |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-240m | 744 | 20.4% | -8.7% | fail_time_shift_future_matches_or_beats_actual |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-720m | 530 | 8.9% | 2.8% | mixed_actual_only_slightly_above_time_shift_future |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_past | features_shifted_by_1440m | 561 | -11.5% | 23.2% | pass_actual_above_time_shift_past |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_past | features_shifted_by_240m | 757 | 11.4% | 0.3% | mixed_actual_only_slightly_above_time_shift_past |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_past | features_shifted_by_720m | 660 | 16.6% | -4.9% | fail_time_shift_past_matches_or_beats_actual |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | time_shift_future | features_shifted_by_-1440m | 144 | 1.0% | 19.6% | pass_actual_above_time_shift_future |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | time_shift_future | features_shifted_by_-240m | 483 | 25.8% | -5.2% | fail_time_shift_future_matches_or_beats_actual |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | time_shift_future | features_shifted_by_-720m | 320 | 16.2% | 4.4% | mixed_actual_only_slightly_above_time_shift_future |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | time_shift_past | features_shifted_by_1440m | 420 | -8.3% | 29.0% | pass_actual_above_time_shift_past |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | time_shift_past | features_shifted_by_240m | 499 | 16.4% | 4.2% | mixed_actual_only_slightly_above_time_shift_past |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | time_shift_past | features_shifted_by_720m | 466 | 15.0% | 5.7% | pass_actual_above_time_shift_past |


## Symbol / Quote Placebos

| placebo gate | detail | rows | eff | resid edge | actual-control | read |
| --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low_wrong_quote_same_bucket | same_bucket_expression_from_BONK1MUSDC_on_BONK1MUSDT | 0 | 0 | n/a | n/a | insufficient_control_rows |
| BONK1MUSDC_H4_depth_high_rv_low_wrong_quote_same_bucket | same_bucket_expression_from_BONK1MUSDC_on_BONK1MUSDT | 760 | 4 | 11.7% | -5.4% | fail_symbol_quote_placebo_matches_or_beats_actual |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high_wrong_quote_same_bucket | same_bucket_expression_from_BONK1MUSDT_on_BONK1MUSDC | 0 | 0 | n/a | n/a | insufficient_control_rows |
| BONK1MUSDT_H4_depth_high_rv_low_wrong_quote_same_bucket | same_bucket_expression_from_BONK1MUSDT_on_BONK1MUSDC | 675 | 4 | 6.3% | 5.4% | pass_actual_above_symbol_quote_placebo |


## Control Failures

| gate | control | detail | resid edge | actual-control | read |
| --- | --- | --- | --- | --- | --- |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-240m | 17.5% | -11.2% | fail_time_shift_future_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_past | features_shifted_by_240m | 9.5% | -3.2% | fail_time_shift_past_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low | time_shift_past | features_shifted_by_720m | 15.4% | -9.2% | fail_time_shift_past_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low_cv_low | time_shift_future | features_shifted_by_-240m | 26.9% | -4.5% | fail_time_shift_future_matches_or_beats_actual |
| BONK1MUSDC_H4_depth_high_rv_low_wrong_quote_same_bucket | symbol_quote_placebo | same_bucket_expression_from_BONK1MUSDC_on_BONK1MUSDT | 11.7% | -5.4% | fail_symbol_quote_placebo_matches_or_beats_actual |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_future | features_shifted_by_-240m | 20.4% | -8.7% | fail_time_shift_future_matches_or_beats_actual |
| BONK1MUSDT_H4_depth_high_rv_low | time_shift_past | features_shifted_by_720m | 16.6% | -4.9% | fail_time_shift_past_matches_or_beats_actual |
| BONK1MUSDT_H4_depth_high_rv_low_cv_high | time_shift_future | features_shifted_by_-240m | 25.8% | -5.2% | fail_time_shift_future_matches_or_beats_actual |


## Interpretation

- Passing random phase controls means the actual gate residual edge is above the 95th percentile of random circular feature shifts. It is still a robustness diagnostic, not a tradability test.
- Time-shift failures are especially important here: if stale or future-shifted gate features match the actual gate, the gate may be a slow regime proxy rather than a precise L2 state.
- Symbol/quote placebo failures mean the same bucket expression also works on the opposite quote. That supports a common BONK/regime read more than a venue-specific directional read.
- Sparse effective counts remain visible because 4h labels are highly overlapping; the effective fold2/fold3 selected count is far smaller than raw minute rows.

## Bottom Line

Use this table as a promotion blocker. A BONK gate should not graduate from research-state candidate to model candidate unless it clears random phase controls, avoids strong time-shift/placebo matches, and keeps enough fold3/effective selected rows.

# BONK CEX V3 Path-Width Capture Analysis

Status: 2026-05-13. This note is a diagnostic read of path-width capture only. It does not define trading rules, entry/exit logic, sizing, or alpha claims.

## Inputs And Output

Inputs:

```text
date/bonk_v3_residual_path_factor_summary.csv
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
date/bonk_v3_candidate_factor_book.csv
```

Output:

```text
date/bonk_v3_path_width_capture_summary.csv
```

The output has `378` rows: `3 folds * 2 symbols * 3 horizons * 21 candidate-book factors`. It ranks factors inside each `fold/symbol/horizon` group.

## Method

Primary label view is `100 bps` first-passage. For each candidate-book factor, symbol, horizon, and fold:

- Fit high/low bucket cuts on the training side of the fold using the same V3 tertile style: unique finite training values, rounded 1/3 and 2/3 quantile indexes.
- Apply those cuts to the fold validation rows from the panel.
- Compute `path_width_bps = mfe_up_bps - mae_down_bps`.
- Compute `any_hit_rate` from `upper_first/lower_first/both_or_ambiguous`.
- Compute direction as `upper_first_rate - lower_first_rate`.
- Compare the candidate book's `selected_bucket` against the opposite bucket.

Ranking score:

```text
selected_minus_opposite_path_width_median_bps
+ 80 * selected_minus_opposite_any_hit_rate
- 60 * abs(selected_minus_opposite_upper_minus_lower_first_rate)
```

This is only a sorting diagnostic. For direct high-vs-low reading, use the CSV columns:

```text
high_minus_low_path_width_median_bps
high_minus_low_any_hit_rate
high_minus_low_upper_minus_lower_first_rate
```

If `selected_bucket=low`, then `selected_minus_opposite_*` is `low - high`; the raw `high_minus_low_*` columns keep the original sign.

## Class Counts

| class | rows |
| --- | ---: |
| `opposite_bucket_captures_path` | 164 |
| `mixed_or_direction_sensitive` | 70 |
| `low_sample` | 51 |
| `any_hit_capture_not_direction` | 29 |
| `path_width_capture_not_direction` | 25 |
| `path_width_only_no_any_hit_lift` | 18 |
| `direction_sensitive_any_hit` | 11 |
| `path_width_plus_direction` | 10 |

`path_width_capture_not_direction` requires positive selected-vs-opposite path width and small direction gap, with either any-hit lift or saturated 12h any-hit. `any_hit_capture_not_direction` requires positive any-hit lift and direction gap within 8pp. Rows with large direction-gap deltas are kept separate as `path_width_plus_direction` or `direction_sensitive_any_hit`.

## Main Read

The cleanest non-direction path-width capture is not the previous active 4h direction book. It is mostly:

- BONK1MUSDC 1h activity/count high buckets, especially `trade_count=high`, which is clean across all three folds.
- 1h cross-venue microprice disagreement buckets on both symbols, smaller but consistently any-hit oriented rather than direction oriented.
- 12h saturated-any-hit path-width states, where any-hit is already near full at 100 bps and the useful read is path width, not direction. Examples are fold3 `top_depth_total_notional_median=high` and fold2 `bullish_common_mode_score=low`.

The 4h layer is less clean. Fold2 `bullish_common_mode_score=low` and fold3 `cross_venue_microprice_disagreement_bps` widen paths, but their direction gaps are above the 8pp non-direction cutoff, so they are classified as path-width plus direction-sensitive, not pure path-width capture.

## Top Row Per Fold/Symbol/Horizon

| fold | symbol/H | #1 selected bucket | class | sel-op path bps | sel-op any | sel-op dir |
| --- | --- | --- | --- | ---: | ---: | ---: |
| fold1 | BONK1MUSDC 1h | `snapshot_count`=high | `path_width_capture_not_direction` | 70.8 | 37.1pp | 3.6pp |
| fold1 | BONK1MUSDC 4h | `depth_imbalance_25_mean`=low | `any_hit_capture_not_direction` | 13.3 | 3.9pp | 4.1pp |
| fold1 | BONK1MUSDC 12h | `ctx_bonk_rv_1h_bps`=low | `path_width_only_no_any_hit_lift` | 136.9 | -0.4pp | 34.6pp |
| fold1 | BONK1MUSDT 1h | `cross_venue_basis_bps`=high | `low_sample` | 31.0 | 19.9pp | 7.2pp |
| fold1 | BONK1MUSDT 4h | `cross_venue_activity_ratio`=high | `any_hit_capture_not_direction` | 4.0 | 6.8pp | 0.2pp |
| fold1 | BONK1MUSDT 12h | `ctx_bonk_rv_1h_bps`=low | `path_width_only_no_any_hit_lift` | 137.0 | -0.1pp | 36.5pp |
| fold2 | BONK1MUSDC 1h | `trade_count`=high | `path_width_capture_not_direction` | 90.3 | 43.0pp | 0.9pp |
| fold2 | BONK1MUSDC 4h | `bullish_common_mode_score`=low | `path_width_plus_direction` | 70.6 | 9.5pp | 15.1pp |
| fold2 | BONK1MUSDC 12h | `bullish_common_mode_score`=low | `path_width_capture_not_direction` | 55.5 | 0.1pp | 1.5pp |
| fold2 | BONK1MUSDT 1h | `cross_venue_microprice_disagreement_bps`=low | `any_hit_capture_not_direction` | 8.1 | 10.0pp | -3.2pp |
| fold2 | BONK1MUSDT 4h | `bullish_common_mode_score`=low | `path_width_plus_direction` | 68.4 | 9.4pp | 14.8pp |
| fold2 | BONK1MUSDT 12h | `bullish_common_mode_score`=low | `path_width_capture_not_direction` | 54.0 | 0.0pp | 1.7pp |
| fold3 | BONK1MUSDC 1h | `trade_count`=high | `path_width_capture_not_direction` | 161.6 | 51.1pp | 2.4pp |
| fold3 | BONK1MUSDC 4h | `cross_venue_microprice_disagreement_bps`=high | `path_width_plus_direction` | 36.1 | 4.2pp | 11.1pp |
| fold3 | BONK1MUSDC 12h | `cross_venue_activity_ratio`=high | `path_width_only_no_any_hit_lift` | 150.9 | -0.3pp | 12.2pp |
| fold3 | BONK1MUSDT 1h | `bullish_common_mode_score`=high | `path_width_plus_direction` | 97.7 | 44.4pp | 9.1pp |
| fold3 | BONK1MUSDT 4h | `cross_venue_microprice_disagreement_bps`=low | `path_width_plus_direction` | 36.2 | 4.1pp | 10.8pp |
| fold3 | BONK1MUSDT 12h | `trade_notional_quote_sum`=high | `path_width_capture_not_direction` | 176.3 | 0.2pp | -5.1pp |

## Strongest Non-Direction Rows

| rank key | selected bucket | status | class | path bps | any | dir |
| --- | --- | --- | --- | ---: | ---: | ---: |
| fold3 BONK1MUSDC 1h | `trade_count`=high | `diagnostic_only` | `path_width_capture_not_direction` | 161.6 | 51.1pp | 2.4pp |
| fold3 BONK1MUSDT 12h | `trade_notional_quote_sum`=high | `exploratory` | `path_width_capture_not_direction` | 176.3 | 0.2pp | -5.1pp |
| fold2 BONK1MUSDC 1h | `trade_count`=high | `diagnostic_only` | `path_width_capture_not_direction` | 90.3 | 43.0pp | 0.9pp |
| fold3 BONK1MUSDC 12h | `top_depth_total_notional_median`=high | `watch` | `path_width_capture_not_direction` | 115.8 | -0.4pp | -2.9pp |
| fold3 BONK1MUSDT 12h | `top_depth_total_notional_median`=high | `watch` | `path_width_capture_not_direction` | 115.1 | -0.8pp | 5.0pp |
| fold1 BONK1MUSDC 1h | `snapshot_count`=high | `exploratory` | `path_width_capture_not_direction` | 70.8 | 37.1pp | 3.6pp |
| fold1 BONK1MUSDC 1h | `book_ticker_count`=high | `exploratory` | `path_width_capture_not_direction` | 57.9 | 33.4pp | 6.0pp |
| fold1 BONK1MUSDC 1h | `trade_count`=high | `diagnostic_only` | `path_width_capture_not_direction` | 53.8 | 28.8pp | 6.6pp |
| fold1 BONK1MUSDC 12h | `cross_venue_activity_ratio`=high | `diagnostic_only` | `path_width_capture_not_direction` | 56.6 | 0.0pp | 2.2pp |
| fold2 BONK1MUSDC 12h | `bullish_common_mode_score`=low | `diagnostic_only` | `path_width_capture_not_direction` | 55.5 | 0.1pp | 1.5pp |
| fold1 BONK1MUSDT 12h | `cross_venue_activity_ratio`=low | `diagnostic_only` | `path_width_capture_not_direction` | 55.8 | -0.1pp | 1.8pp |
| fold2 BONK1MUSDT 12h | `bullish_common_mode_score`=low | `diagnostic_only` | `path_width_capture_not_direction` | 54.0 | 0.0pp | 1.7pp |

## Candidate Book Active Rows

The two active candidates in the prior candidate book do not show selected-bucket path-width capture in this analysis. Their selected bucket is usually narrower than the opposite bucket.

| fold | symbol/H | selected bucket | rank | class | path bps | any | dir |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| fold1 | BONK1MUSDT 4h | `ctx_bonk_rv_1h_bps`=low | 14 | `opposite_bucket_captures_path` | -11.9 | -16.1pp | 26.6pp |
| fold2 | BONK1MUSDT 4h | `ctx_bonk_rv_1h_bps`=low | 14 | `opposite_bucket_captures_path` | -44.9 | -0.3pp | 16.6pp |
| fold3 | BONK1MUSDT 4h | `ctx_bonk_rv_1h_bps`=low | 15 | `opposite_bucket_captures_path` | -175.6 | -5.1pp | -7.6pp |
| fold1 | BONK1MUSDT 4h | `top_depth_total_notional_median`=high | 16 | `opposite_bucket_captures_path` | -17.1 | -15.5pp | 21.9pp |
| fold2 | BONK1MUSDT 4h | `top_depth_total_notional_median`=high | 13 | `opposite_bucket_captures_path` | -44.9 | -0.4pp | 8.3pp |
| fold3 | BONK1MUSDT 4h | `top_depth_total_notional_median`=high | 13 | `opposite_bucket_captures_path` | -54.9 | -11.0pp | -1.6pp |

## High Vs Low Bucket Notes

- `high_minus_low_path_width_median_bps > 0` means the high bucket had wider realized future path.
- `high_minus_low_path_width_median_bps < 0` means the low bucket had wider realized future path.
- The largest clean positive high-minus-low examples are fold3 BONK1MUSDT 12h `trade_notional_quote_sum=high` at about `+176 bps`, fold3 BONK1MUSDC 1h `trade_count=high` at about `+162 bps`, and fold3 12h `top_depth_total_notional_median=high` at about `+115 bps` on both symbols.
- Clean low-bucket path-width examples include fold2 12h `bullish_common_mode_score=low`, with high-minus-low around `-54` to `-55 bps`.

## Bottom Line

For path-width capture rather than direction, keep the analysis centered on movement-state diagnostics: 1h activity/count states, 1h cross-venue microprice disagreement, and 12h saturated-any-hit width states. The 4h rows often contain direction-sensitive components and should not be described as pure path-width. The prior active 4h candidate rows are not path-width capture rows under their selected buckets.

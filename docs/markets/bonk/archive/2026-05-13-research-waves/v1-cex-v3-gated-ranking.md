# BONK CEX V3 Gated Ranking Probe

Status: 2026-05-13T12:09:59Z. Research-only gate-internal ranking diagnostics; no trading rule, execution plan, or alpha claim.

## Inputs And Outputs

- Input panel: `data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet`
- Phase rows: `date\bonk_v3_gated_rank_phase.csv`
- Summary: `date\bonk_v3_gated_rank_summary.csv`
- Model heads: `date\bonk_v3_gated_rank_heads.csv`
- Importance: `date\bonk_v3_gated_rank_importance.csv`
- Completion: `date\bonk_v3_gated_rank_completion.json`

## Method

- Scope: `BONK1MUSDT`, `H4`, `100 bps`, `label_status=ok`.
- Manual gates are fit on train folds only and then frozen on validation folds.
- Models train only inside each manual gate. Validation ranking selects the top score fraction inside the same gate.
- Gate-only baseline is all rows inside the frozen gate for each phase; model rows are compared against that internal baseline.
- Targets/diagnostics: `residual_positive`, `not_lower_first`, `future_resid_mkt_meme_sol_bps`, and `upper_minus_lower`.
- Phase rotation uses every 240-minute offset; phase rows with fewer than the configured minimum gate rows are skipped.

## Verdict

No score clears the strict fold2/fold3 gate-only baseline test.

## Fold2/Fold3 Winners

_No rows._

## Best Fold2/Fold3 Reads

| fold | gate | model | phases | sel rows | resid edge | resid pass | not lower | future resid | upper-lower | beats |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | depth_high+rv_low | lgbm_shallow_not_lower_first | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | lgbm_shallow_residual_positive | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | linear_composite_directional | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | linear_composite_resid_notlower | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | logistic_not_lower_first | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | logistic_residual_positive | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | raw_cv_spread_high | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | raw_depth_low_rv_proxy | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | raw_neg_rv_1h | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | raw_neg_snapshot_microprice | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | raw_reported_buy_share | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | ridge_future_resid | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | ridge_upper_minus_lower | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | xgb_shallow_not_lower_first | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low | xgb_shallow_residual_positive | 40 | 40 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_not_lower_first | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_residual_positive | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | linear_composite_directional | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | linear_composite_resid_notlower | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | logistic_not_lower_first | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | logistic_residual_positive | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | raw_cv_spread_high | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | raw_depth_low_rv_proxy | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | raw_neg_rv_1h | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | raw_neg_snapshot_microprice | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | raw_reported_buy_share | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | ridge_future_resid | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | ridge_upper_minus_lower | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | xgb_shallow_not_lower_first | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold2 | depth_high+rv_low+snapshot_microprice | xgb_shallow_residual_positive | 24 | 24 | 0.0% | 0.0% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | lgbm_shallow_not_lower_first | 238 | 302 | 0.0% | 48.3% | 0.0% | 0.277 | 0.0% | no |
| fold3 | depth_high+rv_low | lgbm_shallow_residual_positive | 238 | 302 | 0.0% | 37.8% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | linear_composite_directional | 238 | 302 | 0.0% | 29.4% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | linear_composite_resid_notlower | 238 | 302 | 0.0% | 34.0% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | logistic_not_lower_first | 238 | 302 | 0.0% | 37.4% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | raw_cv_spread_high | 238 | 302 | 0.0% | 47.9% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | raw_depth_low_rv_proxy | 238 | 302 | 0.0% | 42.4% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | raw_neg_rv_1h | 238 | 302 | 0.0% | 42.0% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | raw_neg_snapshot_microprice | 238 | 302 | 0.0% | 35.7% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | raw_reported_buy_share | 238 | 302 | 0.0% | 39.1% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | ridge_future_resid | 238 | 302 | 0.0% | 34.0% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | ridge_upper_minus_lower | 238 | 302 | 0.0% | 26.1% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | xgb_shallow_not_lower_first | 238 | 302 | 0.0% | 44.1% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | xgb_shallow_residual_positive | 238 | 302 | 0.0% | 34.9% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low | logistic_residual_positive | 238 | 302 | 0.0% | 22.3% | 0.0% | -2.940 | -5.0% | no |
| fold3 | depth_high+rv_low+cv_spread | lgbm_shallow_not_lower_first | 215 | 232 | 0.0% | 17.2% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | lgbm_shallow_residual_positive | 215 | 232 | 0.0% | 12.6% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | linear_composite_directional | 215 | 232 | 0.0% | 20.0% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | linear_composite_resid_notlower | 215 | 232 | 0.0% | 22.3% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | logistic_not_lower_first | 215 | 232 | 0.0% | 20.9% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | logistic_residual_positive | 215 | 232 | 0.0% | 16.7% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | raw_cv_spread_high | 215 | 232 | 0.0% | 24.2% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | raw_depth_low_rv_proxy | 215 | 232 | 0.0% | 15.8% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | raw_neg_rv_1h | 215 | 232 | 0.0% | 18.1% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | raw_neg_snapshot_microprice | 215 | 232 | 0.0% | 22.8% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | raw_reported_buy_share | 215 | 232 | 0.0% | 25.1% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | ridge_future_resid | 215 | 232 | 0.0% | 25.6% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | ridge_upper_minus_lower | 215 | 232 | 0.0% | 14.4% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | xgb_shallow_not_lower_first | 215 | 232 | 0.0% | 19.1% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+cv_spread | xgb_shallow_residual_positive | 215 | 232 | 0.0% | 15.8% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_not_lower_first | 175 | 178 | 0.0% | 22.9% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_residual_positive | 175 | 178 | 0.0% | 18.9% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | linear_composite_directional | 175 | 178 | 0.0% | 16.6% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | linear_composite_resid_notlower | 175 | 178 | 0.0% | 20.0% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | logistic_not_lower_first | 175 | 178 | 0.0% | 18.9% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | logistic_residual_positive | 175 | 178 | 0.0% | 17.7% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | raw_cv_spread_high | 175 | 178 | 0.0% | 24.0% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | raw_depth_low_rv_proxy | 175 | 178 | 0.0% | 23.4% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | raw_neg_rv_1h | 175 | 178 | 0.0% | 19.4% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | raw_neg_snapshot_microprice | 175 | 178 | 0.0% | 21.7% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | raw_reported_buy_share | 175 | 178 | 0.0% | 20.6% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | ridge_future_resid | 175 | 178 | 0.0% | 21.1% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | ridge_upper_minus_lower | 175 | 178 | 0.0% | 13.7% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | xgb_shallow_not_lower_first | 175 | 178 | 0.0% | 23.4% | 0.0% | 0.000 | 0.0% | no |
| fold3 | depth_high+rv_low+snapshot_microprice | xgb_shallow_residual_positive | 175 | 178 | 0.0% | 21.7% | 0.0% | 0.000 | 0.0% | no |

## Head Diagnostics

| fold | gate | model | target | family | train | val | auc | rho |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold2 | depth_high+rv_low | lgbm_shallow_not_lower_first | not_lower_first | lightgbm_shallow | 1505 | 42 | 0.398 | n/a |
| fold2 | depth_high+rv_low | lgbm_shallow_residual_positive | residual_positive | lightgbm_shallow | 1505 | 42 | n/a | n/a |
| fold2 | depth_high+rv_low | logistic_not_lower_first | not_lower_first | linear_logistic | 1505 | 42 | 0.159 | n/a |
| fold2 | depth_high+rv_low | logistic_residual_positive | residual_positive | linear_logistic | 1505 | 42 | n/a | n/a |
| fold2 | depth_high+rv_low | ridge_future_resid | future_resid | linear_ridge | 1505 | 42 | n/a | 0.064 |
| fold2 | depth_high+rv_low | ridge_upper_minus_lower | upper_minus_lower | linear_ridge | 1505 | 42 | n/a | -0.234 |
| fold2 | depth_high+rv_low | xgb_shallow_not_lower_first | not_lower_first | xgboost_shallow | 1505 | 42 | 0.467 | n/a |
| fold2 | depth_high+rv_low | xgb_shallow_residual_positive | residual_positive | xgboost_shallow | 1505 | 42 | n/a | n/a |
| fold2 | depth_high+rv_low+cv_spread | skipped_small_gate | all | skip | 744 | 18 | n/a | n/a |
| fold2 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_not_lower_first | not_lower_first | lightgbm_shallow | 772 | 26 | 0.188 | n/a |
| fold2 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_residual_positive | residual_positive | lightgbm_shallow | 772 | 26 | n/a | n/a |
| fold2 | depth_high+rv_low+snapshot_microprice | logistic_not_lower_first | not_lower_first | linear_logistic | 772 | 26 | 0.097 | n/a |
| fold2 | depth_high+rv_low+snapshot_microprice | logistic_residual_positive | residual_positive | linear_logistic | 772 | 26 | n/a | n/a |
| fold2 | depth_high+rv_low+snapshot_microprice | ridge_future_resid | future_resid | linear_ridge | 772 | 26 | n/a | 0.033 |
| fold2 | depth_high+rv_low+snapshot_microprice | ridge_upper_minus_lower | upper_minus_lower | linear_ridge | 772 | 26 | n/a | -0.618 |
| fold2 | depth_high+rv_low+snapshot_microprice | xgb_shallow_not_lower_first | not_lower_first | xgboost_shallow | 772 | 26 | 0.062 | n/a |
| fold2 | depth_high+rv_low+snapshot_microprice | xgb_shallow_residual_positive | residual_positive | xgboost_shallow | 772 | 26 | n/a | n/a |
| fold3 | depth_high+rv_low | lgbm_shallow_not_lower_first | not_lower_first | lightgbm_shallow | 2308 | 660 | 0.525 | n/a |
| fold3 | depth_high+rv_low | lgbm_shallow_residual_positive | residual_positive | lightgbm_shallow | 2308 | 660 | 0.574 | n/a |
| fold3 | depth_high+rv_low | logistic_not_lower_first | not_lower_first | linear_logistic | 2308 | 660 | 0.546 | n/a |
| fold3 | depth_high+rv_low | logistic_residual_positive | residual_positive | linear_logistic | 2308 | 660 | 0.379 | n/a |
| fold3 | depth_high+rv_low | ridge_future_resid | future_resid | linear_ridge | 2308 | 660 | n/a | -0.028 |
| fold3 | depth_high+rv_low | ridge_upper_minus_lower | upper_minus_lower | linear_ridge | 2308 | 660 | n/a | -0.321 |
| fold3 | depth_high+rv_low | xgb_shallow_not_lower_first | not_lower_first | xgboost_shallow | 2308 | 660 | 0.504 | n/a |
| fold3 | depth_high+rv_low | xgb_shallow_residual_positive | residual_positive | xgboost_shallow | 2308 | 660 | 0.559 | n/a |
| fold3 | depth_high+rv_low+cv_spread | lgbm_shallow_not_lower_first | not_lower_first | lightgbm_shallow | 1081 | 407 | 0.303 | n/a |
| fold3 | depth_high+rv_low+cv_spread | lgbm_shallow_residual_positive | residual_positive | lightgbm_shallow | 1081 | 407 | 0.398 | n/a |
| fold3 | depth_high+rv_low+cv_spread | logistic_not_lower_first | not_lower_first | linear_logistic | 1081 | 407 | 0.437 | n/a |
| fold3 | depth_high+rv_low+cv_spread | logistic_residual_positive | residual_positive | linear_logistic | 1081 | 407 | 0.487 | n/a |
| fold3 | depth_high+rv_low+cv_spread | ridge_future_resid | future_resid | linear_ridge | 1081 | 407 | n/a | 0.126 |
| fold3 | depth_high+rv_low+cv_spread | ridge_upper_minus_lower | upper_minus_lower | linear_ridge | 1081 | 407 | n/a | -0.465 |
| fold3 | depth_high+rv_low+cv_spread | xgb_shallow_not_lower_first | not_lower_first | xgboost_shallow | 1081 | 407 | 0.325 | n/a |
| fold3 | depth_high+rv_low+cv_spread | xgb_shallow_residual_positive | residual_positive | xgboost_shallow | 1081 | 407 | 0.498 | n/a |
| fold3 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_not_lower_first | not_lower_first | lightgbm_shallow | 1177 | 289 | 0.467 | n/a |
| fold3 | depth_high+rv_low+snapshot_microprice | lgbm_shallow_residual_positive | residual_positive | lightgbm_shallow | 1177 | 289 | 0.578 | n/a |
| fold3 | depth_high+rv_low+snapshot_microprice | logistic_not_lower_first | not_lower_first | linear_logistic | 1177 | 289 | 0.409 | n/a |
| fold3 | depth_high+rv_low+snapshot_microprice | logistic_residual_positive | residual_positive | linear_logistic | 1177 | 289 | 0.448 | n/a |
| fold3 | depth_high+rv_low+snapshot_microprice | ridge_future_resid | future_resid | linear_ridge | 1177 | 289 | n/a | 0.180 |
| fold3 | depth_high+rv_low+snapshot_microprice | ridge_upper_minus_lower | upper_minus_lower | linear_ridge | 1177 | 289 | n/a | -0.302 |
| fold3 | depth_high+rv_low+snapshot_microprice | xgb_shallow_not_lower_first | not_lower_first | xgboost_shallow | 1177 | 289 | 0.456 | n/a |
| fold3 | depth_high+rv_low+snapshot_microprice | xgb_shallow_residual_positive | residual_positive | xgboost_shallow | 1177 | 289 | 0.647 | n/a |

## Availability

- Optional model notes: all optional model imports available


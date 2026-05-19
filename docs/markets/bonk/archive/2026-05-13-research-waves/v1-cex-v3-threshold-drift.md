# BONK CEX V3 Threshold Drift Diagnostics

Status: 2026-05-13. This is a research diagnostic, not a trading rule, execution plan, or alpha claim.

## Inputs And Outputs

- Panel: `data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet`
- Fold CSV: `date/bonk_v3_gate_threshold_drift_20260513_bullish_l2_basket_price_v1_fold.csv`
- Day CSV: `date/bonk_v3_gate_threshold_drift_20260513_bullish_l2_basket_price_v1_day.csv`
- Phase CSV: `date/bonk_v3_gate_threshold_drift_20260513_bullish_l2_basket_price_v1_phase.csv`
- Threshold CSV: `date/bonk_v3_gate_threshold_drift_20260513_bullish_l2_basket_price_v1_thresholds.csv`
- Fold2/Fold3 comparison CSV: `date/bonk_v3_gate_threshold_drift_20260513_bullish_l2_basket_price_v1_fold2_fold3.csv`
- Summary JSON: `date/bonk_v3_gate_threshold_drift_20260513_bullish_l2_basket_price_v1_summary.json`

## Method

- Each fold freezes low/high tertile thresholds on the train side, then applies them unchanged to validation.
- `cv_spread_selected` is symbol-specific: high for BONK1MUSDT and low for BONK1MUSDC.
- Diagnostics are emitted by fold, validation day, and phase-rotated non-overlap minute bucket.
- Outcome edges are validation selected-rate minus validation baseline-rate inside the same fold/day/phase slice.

## Executive Read

`depth_high+rv_low` moves from 1.6% to 16.3% validation share and residual edge 30.2% to 10.2%; `depth_high+rv_low+cv_spread` moves from 0.7% to 10.9% validation share and residual edge 30.2% to 20.1%.

The drift read explains part of the tree/gate disagreement: the hand gates are fixed tertile states, but their validation coverage and selected context can move sharply across folds. A tree trained on `upper_first` logloss can then rank away from a gate that still behaves as residual or lower-first suppression in one regime, especially when fold3 changes the selected context.

## H4 BONK1MUSDT Gate Drift

| gate | share f2 | share f3 | d share | resid f2 | resid f3 | d resid | lower f2 | lower f3 | regime | outcome |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| depth_high | 10.8% | 21.8% | 10.9% | 14.0% | 9.7% | -4.2% | -2.9% | -2.4% | selected_regime_shift:common_mode | outcome_near_stable |
| rv_low | 6.0% | 46.2% | 40.2% | 29.3% | 5.9% | -23.4% | -5.6% | -1.2% | selected_regime_shift:common_mode | residual_edge_fades |
| cv_spread_selected | 36.9% | 41.4% | 4.5% | 0.4% | 11.7% | 11.3% | 4.6% | -6.9% | selected_regime_near_stable | residual_edge_improves |
| snapshot_microprice_low | 32.1% | 23.3% | -8.8% | 0.1% | 8.7% | 8.6% | 1.1% | -4.9% | selected_regime_near_stable | outcome_near_stable |
| microprice_low | 33.6% | 25.0% | -8.6% | -0.2% | 6.7% | 6.9% | 1.8% | -3.6% | selected_regime_near_stable | outcome_near_stable |
| depth_high+rv_low | 1.6% | 16.3% | 14.7% | 30.2% | 10.2% | -20.0% | -7.8% | -0.9% | selected_regime_shift:common_mode | residual_edge_fades_and_lower_first_worsens |
| depth_high+rv_low+cv_spread | 0.7% | 10.9% | 10.2% | 30.2% | 20.1% | -10.1% | 1.9% | -6.0% | selected_regime_shift:common_mode | residual_edge_fades |
| depth_high+rv_low+snapshot_microprice | 1.0% | 7.2% | 6.2% | 30.2% | 15.8% | -14.4% | -0.3% | -6.6% | selected_regime_shift:common_mode | residual_edge_fades |

## Context Controls

| gate | share f2 | share f3 | d share | resid f2 | resid f3 | regime |
| --- | --- | --- | --- | --- | --- | --- |
| ctx_meme_ret_60m_high | 30.6% | 29.7% | -0.8% | -5.5% | 4.1% | selected_regime_near_stable |
| ctx_sol_ret_60m_high | 40.0% | 33.8% | -6.2% | -6.4% | 2.5% | selected_regime_near_stable |
| common_mode_high | 31.3% | 20.8% | -10.5% | 5.0% | -10.4% | selected_regime_near_stable |

## Day And Phase Checks

- Day rows written: `1,140`.
- Phase rows written with `15` minute phase step: `7,752`.

| fold | gate | phases | share min | share med | share max | med resid |
| --- | --- | --- | --- | --- | --- | --- |
| fold1 | depth_high+rv_low | 16 | 6.7% | 13.3% | 26.7% | 43.3% |
| fold1 | depth_high+rv_low+cv_spread | 16 | 0.0% | 6.7% | 20.0% | 43.3% |
| fold2 | depth_high+rv_low | 16 | 0.0% | 0.0% | 7.1% | 33.3% |
| fold2 | depth_high+rv_low+cv_spread | 16 | 0.0% | 0.0% | 7.1% | 35.7% |
| fold3 | depth_high+rv_low | 16 | 0.0% | 16.7% | 27.8% | 19.4% |
| fold3 | depth_high+rv_low+cv_spread | 16 | 0.0% | 8.3% | 27.8% | 22.2% |

## Interpretation

- If fold3 coverage changes while selected context medians move, the same hand threshold is no longer selecting the same market state.
- If residual edge survives but upper/lower path edge flips, the gate is a state filter rather than an `upper_first` classifier.
- If phase coverage is wide, one stride-H top-decile model slice is too brittle to judge whether the tree recovered the gate.

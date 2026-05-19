# BONK CEX V3 Candidate Combination / Gate Analysis

Status: 2026-05-13. This is a research-candidate combination analysis over the existing BONK V3 artifacts. It is not a trading rule, not an execution plan, and not an alpha claim.

## Inputs And Outputs

Inputs:

```text
date/bonk_v3_candidate_factor_deep_dive.csv
date/bonk_v3_recent_regime_edge_summary.csv
date/bonk_v3_residual_path_factor_summary.csv
date/bonk_v1_model_metrics_20260513_bullish_l2_basket_price_v1.csv
```

Supporting panel read for exact AND-gate co-occurrence:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Output CSV:

```text
date/bonk_v3_candidate_combo_gate_summary.csv
```

## Method

- Primary label view: `100 bps` first-passage labels, validation folds `fold1/fold2/fold3`.
- Gate buckets use the same train-to-validation convention as the controlled factor tests: each fold fits low/high tertile cuts on the train side, then applies the selected bucket to the validation side.
- Core gates tested here are `top_depth_total_notional_median=high`, `ctx_bonk_rv_1h_bps=low`, symbol-specific `cross_venue_spread_diff_bps` (`high` for BONK1MUSDT, `low` for BONK1MUSDC), and `snapshot_microprice_offset_bps_mean=low`.
- `edge_residual` means selected gate residual-positive rate minus the clean baseline residual-positive rate. It is a candidate-health statistic, not expected return.
- Complementarity is measured as combo `edge_residual` minus the strongest single component edge for the same symbol/horizon.

## Executive Read

The useful H4 structure is: `top_depth high + low RV` first, then cross-venue spread as the cleaner additive gate. On BONK1MUSDT H4, `depth_high+rv_low` reaches 19.9% residual edge with 5.5% incremental edge over the best single component. Adding cross-venue spread lifts that to 25.4%, with 11.0% incremental edge and 796 selected rows.

Microprice is complementary, but less clean. `depth_high+rv_low+snapshot_microprice` reaches 23.4% residual edge, but the source microprice candidates are placebo/path-width sensitive. Read it as a confirmation or diagnostic gate, not as a standalone promotion.

The quad gate is not better research hygiene even though the in-sample residual edge is high. `depth_high+rv_low+cv_spread+snapshot_microprice` has only 291 H4 BONK1MUSDT rows (2.5%) and is classified as `retired_sparse_quad_gate`. Too many filters make the result easier to overfit.

USDC has a useful mirror but not an active priority. BONK1MUSDC H4 `depth_high+rv_low+cv_spread` has 25.9% residual edge and 11.8% incremental edge, but source statuses and non-overlap support are weaker, so it stays watch.

Model support stays diagnostic-only: fold2/3 non-overlap proper-score wins are `3/8`, and all fold3 proper-score rows fail. The gate taxonomy below therefore promotes research priority only, not tradability.

## Active Gates

| gate | symbol | rows | share | resid edge | increment | fold3 | taxonomy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| depth_high+rv_low | BONK1MUSDT | 1317 | 11.4% | 19.9% | 5.5% | 10.2% | active_base_gate |
| rv_low | BONK1MUSDT | 3603 | 31.3% | 14.4% | 0.0% | 5.9% | active_single_state |
| depth_high | BONK1MUSDT | 2393 | 20.8% | 12.6% | 0.0% | 9.7% | active_single_state |
| depth_high+rv_low+cv_spread | BONK1MUSDT | 796 | 6.9% | 25.4% | 11.0% | 20.1% | active_combo_gate |


Active here means priority next-window research gate. It does not mean entry/exit logic. Source-active single components are included for audit; the active AND-gates are the base H4 USDT `depth+RV` state and its cross-venue-spread extension.

## H4 BONK1MUSDT Complementarity

| gate | status | rows | share | resid | upper | lower | upper-lower | increment | fold3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| depth_high | active | 2393 | 20.8% | 12.6% | 0.5% | -6.6% | 7.1% | 0.0% | 9.7% |
| rv_low | active | 3603 | 31.3% | 14.4% | 0.0% | -5.9% | 5.9% | 0.0% | 5.9% |
| cv_spread_selected | watch | 4698 | 40.8% | 6.0% | 0.1% | -1.6% | 1.6% | 0.0% | 11.7% |
| snapshot_microprice_low | watch | 3320 | 28.8% | 3.6% | 0.9% | -1.8% | 2.7% | 0.0% | 8.7% |
| depth_high+rv_low | active | 1317 | 11.4% | 19.9% | -0.7% | -9.8% | 9.1% | 5.5% | 10.2% |
| depth_high+rv_low+cv_spread | active | 796 | 6.9% | 25.4% | 1.8% | -11.0% | 12.9% | 11.0% | 20.1% |
| depth_high+rv_low+snapshot_microprice | watch | 642 | 5.6% | 23.4% | 1.9% | -13.5% | 15.4% | 9.0% | 15.8% |
| depth_high+rv_low+cv_spread+snapshot_microprice | retired | 291 | 2.5% | 31.1% | 3.8% | -13.8% | 17.6% | 16.7% | 29.0% |


Read the table carefully: much of the improvement comes from suppressing lower-first outcomes, not from a large standalone upper-first edge. That is why the correct wording is gate/state candidate, not long signal.

## USDC Mirror

| gate | status | rows | resid | increment | fold3 | read |
| --- | --- | --- | --- | --- | --- | --- |
| depth_high+rv_low | watch | 1218 | 15.1% | 1.0% | 4.0% | watch_depth_rv_combo |
| depth_high+rv_low+cv_spread | watch | 483 | 25.9% | 11.8% | 22.0% | watch_mirror_combo_gate |
| depth_high+rv_low+snapshot_microprice | watch | 691 | 15.6% | 1.5% | 5.2% | watch_depth_rv_combo |
| depth_high+rv_low+cv_spread+snapshot_microprice | retired | 205 | 31.7% | 17.5% | 30.4% | retired_sparse_combo |


USDC mirrors the H4 state but remains watch. It is useful for cross-symbol consistency checks and for seeing whether the same venue-state phenomenon appears with the opposite spread-diff bucket.

## Gate Taxonomy

| status | count | meaning |
| --- | ---: | --- |
| active | 4 | priority H4 candidate gates to pre-register in the next window; no trade rule. |
| watch | 57 | diagnostic, mirror, path-width, or confirmation gates; useful for validation design but not priority direction. |
| retired | 35 | short-horizon direction, sparse quad, or non-overlap-fragile gates kept for audit/history only. |

Specific taxonomy reads:

- `active_base_gate`: H4 BONK1MUSDT `top_depth high + low RV`; this is the cleanest two-factor state.
- `active_combo_gate`: H4 BONK1MUSDT `top_depth high + low RV + cross-venue spread`; strongest additive candidate.
- `watch_microprice_confirm_gate`: microprice helps as confirmation, but source placebo/path-width flags block promotion.
- `watch_mirror_combo_gate`: USDC mirror is useful for robustness checks but not active.
- `watch_path_width_only`: 12h gates remain movement/path-width candidates; directional reading is retired because residual path flips across Fold2/Fold3.
- `retired_short_horizon_direction`: 1h gates are too thin and often improve by reducing lower-first, not adding upper-first.
- `retired_sparse_combo`: quad gates have attractive residual numbers but too few rows for priority validation.

## Bottom Line

`top_depth high` and `low RV` are complementary as a base H4 gate. Cross-venue spread is the better additive third gate. Microprice is useful as a watch-level confirmation layer, but it should not be allowed to turn a candidate into a rule. The next validation should pre-register the active H4 USDT gates and separately track USDC mirror/watch and 12h path-width behavior.

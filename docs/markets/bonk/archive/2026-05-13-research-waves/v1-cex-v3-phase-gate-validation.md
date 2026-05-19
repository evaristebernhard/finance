# BONK CEX V3 Phase Gate Validation

Status: 2026-05-13T11:27:15Z. This is a read-only validation of hand-built BONK V3 gates under phase-rotated non-overlap. It is not a trading rule, not an execution plan, and not an alpha claim.

## Inputs And Outputs

Input panel:

```text
data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date\bonk_v3_phase_gate_validation_phase_rows.csv
date\bonk_v3_phase_gate_validation_fold_summary.csv
date\bonk_v3_phase_gate_validation_gate_summary.csv
date\bonk_v3_phase_gate_validation_summary.json
```

## Method

- Scope: canonical BONK L2 label/context panel, `100 bps` labels, `H1/H4`, `label_status=ok`.
- Splits: fold thresholds are fit only on train rows ending at each fold's train cutoff, then applied to that fold's validation rows.
- Gate construction: the hand-built depth, RV, cross-venue spread, and microprice gates from the V3 combo work are evaluated as single and AND gates.
- Phase design: for each validation fold/symbol/horizon/gate, every phase offset is evaluated with period `horizon * 60` minutes, so H1 has 60 phase rows and H4 has 240 phase rows per fold.
- Per phase, the script compares selected rows against non-selected rows for upper/lower rates, residual-positive rate, median future residual, and path width.
- Summaries report median, IQR, and pass-rate across eligible phases. A phase is eligible when it has at least `3` selected rows and at least one non-selected row.

## Executive Read

The table below is the phase-averaged view, not a single stride phase. It is meant to expose offset luck: a gate that only works in one phase should show weak pass-rate or sparse eligible phases.

## H4 BONK1MUSDT Focus

| gate | rows | eligible phases | sel share | resid edge | resid pass | median resid edge | dir pass | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| depth_high | 2393 | 459 | 20.0% | 20.0% | 71.7% | 29.156 | 59.7% | phase_supported_directional_candidate |
| rv_low | 3603 | 480 | 38.9% | 29.5% | 82.7% | 36.341 | 55.6% | phase_supported_directional_candidate |
| depth_high+rv_low | 1317 | 244 | 11.1% | 25.8% | 73.8% | 34.436 | 58.2% | phase_supported_directional_candidate |
| depth_high+rv_low+cv_spread | 796 | 92 | 6.7% | 26.7% | 83.7% | 41.096 | 63.0% | phase_supported_directional_candidate |
| depth_high+rv_low+snapshot_microprice | 642 | 58 | 5.6% | 26.7% | 72.4% | 36.319 | 65.5% | too_sparse_for_phase_read |
| depth_high+rv_low+cv_spread+snapshot_microprice | 291 | 11 | 0.0% | 26.7% | 72.7% | 47.465 | 81.8% | too_sparse_for_phase_read |


## Positive Or Watch Reads

| gate | rows | eligible phases | sel share | resid edge | resid pass | median resid edge | dir pass | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cv_spread+snapshot_microprice | 911 | 88 | 6.7% | 14.3% | 56.8% | 15.215 | 51.1% | mixed_positive_phase_watch |
| depth_high+cv_spread+snapshot_microprice | 369 | 62 | 3.1% | 10.7% | 59.7% | 4.906 | 58.1% | mixed_positive_phase_watch |
| cv_spread+snapshot_microprice | 1333 | 198 | 11.1% | 9.2% | 58.1% | 15.000 | 51.0% | mixed_positive_phase_watch |
| rv_low+snapshot_microprice | 1135 | 124 | 11.7% | 7.8% | 65.3% | 6.159 | 45.2% | mixed_positive_phase_watch |
| snapshot_microprice_low | 3320 | 632 | 27.8% | 7.1% | 54.0% | 7.876 | 51.4% | mixed_positive_phase_watch |
| snapshot_microprice_low | 2876 | 581 | 26.7% | 6.7% | 53.5% | 7.825 | 49.2% | mixed_positive_phase_watch |
| depth_high+snapshot_microprice | 1334 | 164 | 11.1% | 6.2% | 57.9% | 3.264 | 48.8% | mixed_positive_phase_watch |
| depth_high+rv_low+snapshot_microprice | 691 | 118 | 6.7% | 5.5% | 61.9% | 3.084 | 43.2% | mixed_positive_phase_watch |
| depth_high | 2393 | 177 | 20.8% | 5.5% | 63.8% | 4.870 | 58.8% | mixed_positive_phase_watch |
| depth_high | 2268 | 178 | 20.8% | 5.4% | 58.4% | 3.729 | 52.2% | mixed_positive_phase_watch |
| microprice_low | 3458 | 649 | 27.8% | 5.4% | 52.4% | 4.830 | 49.3% | mixed_positive_phase_watch |
| cv_spread_selected | 4698 | 180 | 41.7% | 4.8% | 61.7% | 4.795 | 47.2% | mixed_positive_phase_watch |
| rv_low | 3603 | 173 | 38.3% | 4.8% | 56.6% | 6.372 | 52.0% | mixed_positive_phase_watch |
| depth_high+rv_low | 1218 | 121 | 12.5% | 4.6% | 61.2% | 4.072 | 48.8% | mixed_positive_phase_watch |
| depth_high+snapshot_microprice | 1243 | 167 | 10.0% | 4.5% | 57.5% | 4.848 | 54.5% | mixed_positive_phase_watch |
| cv_spread_selected | 4697 | 180 | 41.7% | 4.0% | 61.1% | 4.322 | 46.1% | mixed_positive_phase_watch |
| rv_low | 3630 | 175 | 38.3% | 3.7% | 58.3% | 6.408 | 52.6% | mixed_positive_phase_watch |
| cv_spread+snapshot_microprice | 911 | 157 | 8.3% | 2.6% | 54.8% | 3.951 | 49.0% | mixed_positive_phase_watch |
| snapshot_microprice_low | 3320 | 180 | 28.3% | 2.3% | 55.6% | 2.240 | 56.7% | mixed_positive_phase_watch |
| microprice_low | 3271 | 636 | 27.2% | 1.9% | 51.3% | 3.994 | 50.8% | mixed_positive_phase_watch |


## Fold Detail For Core H4 USDT Gates

| fold | gate | rows | eligible phases | resid edge | resid pass | median resid edge | read |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fold1 | depth_high+rv_low | 557 | 99 | 40.0% | 91.9% | 38.485 | phase_supported_directional_candidate |
| fold2 | depth_high+rv_low | 57 | 0 | n/a | n/a | n/a | too_sparse_for_phase_read |
| fold3 | depth_high+rv_low | 703 | 145 | 14.3% | 61.4% | 27.658 | phase_supported_state_candidate |
| fold1 | depth_high+rv_low+cv_spread | 297 | 26 | 33.3% | 96.2% | 39.160 | too_sparse_for_phase_read |
| fold2 | depth_high+rv_low+cv_spread | 26 | 0 | n/a | n/a | n/a | too_sparse_for_phase_read |
| fold3 | depth_high+rv_low+cv_spread | 473 | 66 | 26.7% | 78.8% | 43.643 | phase_supported_directional_candidate |


## Status Counts

- `mixed_positive_phase_watch`: 22
- `phase_fragile_or_negative`: 2
- `phase_supported_directional_candidate`: 22
- `phase_supported_state_candidate`: 10
- `too_sparse_for_phase_read`: 8

## Interpretation

- `resid edge` is selected residual-positive rate minus non-selected residual-positive rate, summarized by median across eligible phases.
- `median resid edge` is selected median future residual minus non-selected median future residual, in bps, summarized by median across eligible phases.
- `dir pass` checks whether selected upper-rate edge minus lower-rate edge is positive. A residual state can pass without being a clean directional signal.
- H4 phase rows remain thin because each phase has only one row per four-hour stride. This validator is a robustness screen, not proof of independence across phases.

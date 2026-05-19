# CCUSDT Fixed Event-Defined OFI/MLOFI

Status: 2026-05-17. Run tag: `20260517_ccusdt_fixed_factors_v3`.

Guardrail: `research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim`.

## Scope

This pass starts from local `bullish_incremental_book_L2` and `bullish_trades` raw CSV.GZ files. It does not download raw data, delete raw files, or treat prior snapshot-factor mining conclusions as discovery evidence.

The event layer distinguishes full snapshot batches from incremental updates. Snapshot batches rebuild the book at each timestamp and compute OFI/MLOFI from the previous completed book to the current completed book.

## Coverage

- Completed symbol-days: `17/17`.
- Event panel rows: `2606830`.
- Low-confidence execute/cancel split symbol-days: `0`.
- Fixed feature definitions per fold: `105`.
- Factor params rows: `315`.
- Path ranking rows: `1512`.
- Stability rows: `290687`.
- Negative control rows: `310` across `4` control types.
- Spearman diagnostic rows: `510`.

## Event Definitions

- New price with positive amount is `limit_add/create`.
- Size increase at an existing price is `replenish/add`.
- Size decrease or zero amount is queue depletion, split into executable and cancellation/withdrawal using nearby trades.
- Trade side is taker-side: `buy` consumes asks and `sell` consumes bids.
- Spearman diagnostics use `dlog_mid_{t,t+h}` and are separate from profit or fill-realism overlays.
- If day-level matched depletion rate is below 60%, execute/cancel split is marked `low_confidence`; aggregate depletion/replenish factors remain usable diagnostics.

## Factor Families

Main ranked families are CKS best-level OFI, XGH-style MLOFI at levels `1/2/3/5/10/25`, depth-normalized/rolling event-time MLOFI, quote/queue imbalance, microprice deviation, queue depletion, replenish, cancellation/withdrawal, trade-arrival alignment, liquidity-shock resiliency, and cross-venue MLOFI lead-lag. Each base feature is tested as raw, absolute, positive-part, negative-part, and signed-square variants, giving a fixed reusable 100+ feature surface. Depth slope/curvature is intentionally not promoted here.

## Top Path Diagnostics

Rows shown here must clear same-gate/same-side negative controls; control-dominated candidates stay in the CSV but are not promoted in this table.

| fold | symbol | feature | gate | side | horizon_events | selected | fav-adv | side_ret_bps | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| auto_expanding_3 | CCUSDT | mlofi_roll10_l1 | high_train_q80 | long | 70 | 128796 | 0.1197 | 1.0126 | 3.5660 |
| auto_expanding_3 | CCUSDT | pos__mlofi_roll10_l1 | high_train_q80 | long | 70 | 128796 | 0.1197 | 1.0126 | 3.5660 |
| auto_expanding_3 | CCUSDT | signed_sq__mlofi_roll10_l1 | high_train_q80 | long | 70 | 128796 | 0.1197 | 1.0126 | 3.5660 |
| auto_expanding_3 | CCUSDT | mlofi_roll10_l1 | low_train_q20 | short | 70 | 129600 | 0.0914 | 0.9722 | 3.4623 |
| auto_expanding_3 | CCUSDT | signed_sq__mlofi_roll10_l1 | low_train_q20 | short | 70 | 129600 | 0.0914 | 0.9722 | 3.4623 |
| auto_expanding_2 | CCUSDT | mlofi_roll10_l1 | low_train_q20 | short | 70 | 116595 | 0.0968 | 0.6558 | 2.8569 |
| auto_expanding_2 | CCUSDT | signed_sq__mlofi_roll10_l1 | low_train_q20 | short | 70 | 116595 | 0.0968 | 0.6558 | 2.8569 |
| auto_expanding_3 | CCUSDT | pos__mlofi_roll10_l1 | low_train_q20 | short | 70 | 210873 | 0.0562 | 0.7026 | 2.4605 |
| auto_expanding_2 | CCUSDT | pos__mlofi_roll10_l1 | low_train_q20 | short | 70 | 217316 | 0.0760 | 0.5075 | 2.2615 |
| auto_expanding_2 | CCUSDT | mlofi_roll10_l1 | high_train_q80 | long | 70 | 122904 | 0.0798 | 0.5915 | 2.2482 |

## Controls And Read

Negative controls include within-day shuffled event time, reversed-sign gate, future-shift placebo, and same-state opposite-side checks where candidates are available. The single-market CCUSDT run has no wrong-symbol control; `wrong_symbol_same_factor` is only available for multi-symbol runs. Candidates that do not clearly separate from controls are classified as window/cost artifacts.

Profit/after-cost overlay was not run for this panel; Spearman and path diagnostics are information tests only, not realized PnL evidence.

## Output Tables

- `date/ccusdt_v1_fixed_event_factors_quality_20260517_ccusdt_fixed_factors_v3.csv`
- `date/ccusdt_v1_fixed_event_factors_factor_params_20260517_ccusdt_fixed_factors_v3.csv`
- `date/ccusdt_v1_fixed_event_factors_path_ranking_20260517_ccusdt_fixed_factors_v3.csv`
- `date/ccusdt_v1_fixed_event_factors_stability_20260517_ccusdt_fixed_factors_v3.csv`
- `date/ccusdt_v1_fixed_event_factors_negative_controls_20260517_ccusdt_fixed_factors_v3.csv`
- `date/ccusdt_v1_fixed_event_factors_spearman_20260517_ccusdt_fixed_factors_v3.csv`
- `date/ccusdt_v1_fixed_event_factors_episode_overlay_20260517_ccusdt_fixed_factors_v3.csv`

## Reproduce

```powershell
cargo run -p cex_l2_research --bin tardis_bullish_fixed_factor_panel --release -- --data-root data/ccusdt/v1 --date-dir date --doc-dir docs/markets/ccusdt --output-prefix ccusdt_v1_fixed_event_factors --panel-dataset ccusdt_v1_fixed_event_factor_panel --report-name v1-fixed-event-orderbook-factors-v3.md --market-label "CCUSDT" --from-date 2026-04-29 --to-date 2026-05-15 --symbols CCUSDT --run-tag 20260517_ccusdt_fixed_factors_v3 --part-rows 25000 --trade-match-window-us 2000000 --cross-venue-tolerance-us 2000000
```

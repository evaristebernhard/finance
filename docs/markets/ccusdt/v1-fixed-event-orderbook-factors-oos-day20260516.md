# CCUSDT Fixed Event-Defined OFI/MLOFI

Status: 2026-05-17. Run tag: `20260518_ccusdt_fixed_factors_oos_day20260516_v1`.

Guardrail: `research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim`.

## Scope

This pass starts from local `bullish_incremental_book_L2` and `bullish_trades` raw CSV.GZ files. It does not download raw data, delete raw files, or treat prior snapshot-factor mining conclusions as discovery evidence.

The event layer distinguishes full snapshot batches from incremental updates. Snapshot batches rebuild the book at each timestamp and compute OFI/MLOFI from the previous completed book to the current completed book.

## Coverage

- Completed symbol-days: `1/1`.
- Event panel rows: `132382`.
- Low-confidence execute/cancel split symbol-days: `0`.
- Fixed feature definitions per fold: `105`.
- Factor params rows: `0`.
- Path ranking rows: `0`.
- Stability rows: `0`.
- Negative control rows: `0` across `0` control types.
- Spearman diagnostic rows: `0`.

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

_No path rows survived the top-table selected-row and control-separation filters._

## Controls And Read

Negative controls include wrong-symbol same-factor, within-day shuffled event time, reversed-sign gate, future-shift placebo, and same-state opposite-side checks where candidates are available. Candidates that do not clearly separate from controls are classified as window/cost artifacts.

Profit/after-cost overlay was not run for this panel; Spearman and path diagnostics are information tests only, not realized PnL evidence.

## Output Tables

- `date/ccusdt_v1_fixed_event_factors_oos_day20260516_quality_20260518_ccusdt_fixed_factors_oos_day20260516_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260516_factor_params_20260518_ccusdt_fixed_factors_oos_day20260516_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260516_path_ranking_20260518_ccusdt_fixed_factors_oos_day20260516_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260516_stability_20260518_ccusdt_fixed_factors_oos_day20260516_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260516_negative_controls_20260518_ccusdt_fixed_factors_oos_day20260516_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260516_spearman_20260518_ccusdt_fixed_factors_oos_day20260516_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260516_episode_overlay_20260518_ccusdt_fixed_factors_oos_day20260516_v1.csv`

## Reproduce

```bash
cargo run -p cex_l2_research --bin tardis_bullish_fixed_factor_panel --release -- --data-root data\ccusdt\v1 --date-dir date --doc-dir docs\markets\ccusdt --output-prefix ccusdt_v1_fixed_event_factors_oos_day20260516 --panel-dataset ccusdt_v1_fixed_event_factor_panel --report-name v1-fixed-event-orderbook-factors-oos-day20260516.md --market-label "CCUSDT" --from-date 2026-05-16 --to-date 2026-05-16 --symbols CCUSDT --run-tag 20260518_ccusdt_fixed_factors_oos_day20260516_v1
```

# CCUSDT Fixed Event-Defined OFI/MLOFI

Status: 2026-05-17. Run tag: `20260519_ccusdt_fixed_factors_oos_day20260518_v1`.

Guardrail: `research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim`.

## Scope

This pass starts from local `bullish_incremental_book_L2` and `bullish_trades` raw CSV.GZ files. It does not download raw data, delete raw files, or treat prior snapshot-factor mining conclusions as discovery evidence.

The event layer distinguishes full snapshot batches from incremental updates. Snapshot batches rebuild the book at each timestamp and compute OFI/MLOFI from the previous completed book to the current completed book.

## Coverage

- Completed symbol-days: `1/1`.
- Completed with quality warnings: `0`.
- Event panel rows: `131608`.
- Low-confidence execute/cancel split symbol-days: `0`.
- Fixed feature definitions per fold: `105`.
- Factor params rows: `315`.
- Path ranking rows: `1242`.
- Stability rows: `38864`.
- Negative control rows: `320` across `4` control types.
- Spearman diagnostic rows: `336`.

## Event Definitions

- New price with positive amount is `limit_add/create`.
- Size increase at an existing price is `replenish/add`.
- Size decrease or zero amount is queue depletion, split into executable and cancellation/withdrawal using same-side trades observed in the trailing local-time window.
- Trade side is taker-side: `buy` consumes asks and `sell` consumes bids.
- Spearman diagnostics use `dlog_mid_{t,t+h}` and are separate from profit or fill-realism overlays.
- If day-level matched depletion rate is below 60%, execute/cancel split is marked `low_confidence`; aggregate depletion/replenish factors remain usable diagnostics.

## Factor Families

Main ranked families are CKS best-level OFI, XGH-style MLOFI at levels `1/2/3/5/10/25`, depth-normalized/rolling event-time MLOFI, quote/queue imbalance, microprice deviation, queue depletion, replenish, cancellation/withdrawal, trade-arrival alignment, liquidity-shock resiliency, and cross-venue MLOFI lead-lag. Each base feature is tested as raw, absolute, positive-part, negative-part, and signed-square variants, giving a fixed reusable 100+ feature surface. Depth slope/curvature is intentionally not promoted here.

## Top Path Diagnostics

Rows shown here must clear same-gate/same-side negative controls; control-dominated candidates stay in the CSV but are not promoted in this table.

| fold | symbol | feature | gate | side | horizon_events | selected | fav-adv | side_ret_bps | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| auto_expanding_2 | CCUSDT | pos__queue_imbalance_25 | high_train_q80 | long | 40 | 2378 | 0.0820 | 1.2446 | 2.9722 |
| auto_expanding_1 | CCUSDT | mlofi_combo | low_train_q20 | short | 40 | 5095 | 0.0803 | 0.8790 | 2.7443 |
| auto_expanding_1 | CCUSDT | mlofi_norm_l1 | low_train_q20 | short | 40 | 4943 | 0.0882 | 0.7618 | 2.6523 |
| auto_expanding_1 | CCUSDT | ofi_l1_depth_norm | low_train_q20 | short | 40 | 4943 | 0.0882 | 0.7618 | 2.6523 |
| auto_expanding_3 | CCUSDT | queue_imbalance_1 | low_train_q20 | short | 40 | 3282 | 0.1164 | 0.7151 | 2.5699 |
| auto_expanding_3 | CCUSDT | mlofi_norm_l1 | low_train_q20 | short | 40 | 2434 | 0.0678 | 1.0878 | 2.4383 |
| auto_expanding_3 | CCUSDT | ofi_l1_depth_norm | low_train_q20 | short | 40 | 2434 | 0.0678 | 1.0878 | 2.4383 |
| auto_expanding_2 | CCUSDT | pos__queue_imbalance_5 | high_train_q80 | long | 40 | 1992 | 0.0602 | 1.1075 | 2.2974 |
| auto_expanding_3 | CCUSDT | mlofi_combo | low_train_q20 | short | 40 | 2505 | 0.0383 | 1.1766 | 2.1740 |
| auto_expanding_2 | CCUSDT | queue_imbalance_1 | low_train_q20 | short | 40 | 6090 | 0.0721 | 0.4917 | 1.8553 |

## Controls And Read

Negative controls include within-day shuffled event time and future-shift placebo as required promotion checks; wrong-symbol same-factor is also applied when another symbol is available. Reversed-sign gate and same-state opposite-side checks remain diagnostic. Candidates that do not clearly separate from controls are classified as window/cost artifacts.

Profit/after-cost overlay was not run for this panel; Spearman and path diagnostics are information tests only, not realized PnL evidence.

## Output Tables

- `date/ccusdt_v1_fixed_event_factors_oos_day20260518_quality_20260519_ccusdt_fixed_factors_oos_day20260518_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260518_factor_params_20260519_ccusdt_fixed_factors_oos_day20260518_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260518_path_ranking_20260519_ccusdt_fixed_factors_oos_day20260518_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260518_stability_20260519_ccusdt_fixed_factors_oos_day20260518_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260518_negative_controls_20260519_ccusdt_fixed_factors_oos_day20260518_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260518_spearman_20260519_ccusdt_fixed_factors_oos_day20260518_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_oos_day20260518_episode_overlay_20260519_ccusdt_fixed_factors_oos_day20260518_v1.csv`

## Reproduce

```bash
cargo run -p cex_l2_research --bin tardis_bullish_fixed_factor_panel --release -- --data-root data/ccusdt/v1 --date-dir date --doc-dir docs/markets/ccusdt --output-prefix ccusdt_v1_fixed_event_factors_oos_day20260518 --panel-dataset ccusdt_v1_fixed_event_factor_panel --report-name v1-fixed-event-orderbook-factors-oos-day20260518.md --market-label "CCUSDT" --from-date 2026-05-18 --to-date 2026-05-18 --symbols CCUSDT --run-tag 20260519_ccusdt_fixed_factors_oos_day20260518_v1 --part-rows 25000 --trade-match-window-us 2000000 --cross-venue-tolerance-us 2000000
```

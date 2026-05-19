# CCUSDT Fixed Event-Defined OFI/MLOFI

Status: 2026-05-17. Run tag: `20260517_ccusdt_fixed_factors_v2`.

Superseded: go directly to `v1-fixed-event-orderbook-factors-v3.md` / run tag `20260517_ccusdt_fixed_factors_v3`. V2 fixed the snapshot replay artifact but still included a top-path table affected by future-trade/control issues.

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
- Stability rows: `289015`.
- Negative control rows: `306` across `4` control types.
- Spearman diagnostic rows: `540`.

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

Audit caveat: this table is not a candidate-ranking table. The leading `trade_arrival_alignment` paths are caveated because the current feature/control construction used future trades and needs repair before those rows can be interpreted. Remaining MLOFI/orderbook-state rows are diagnostic screens only.

| fold | symbol | feature | gate | side | horizon_events | selected | fav-adv | side_ret_bps | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| auto_expanding_3 | CCUSDT | pos__trade_arrival_alignment | high_train_q80 | long | 70 | 60244 | 0.2074 | 1.6371 | 5.9417 |
| auto_expanding_3 | CCUSDT | pos__trade_arrival_alignment | high_train_q80 | long | 35 | 60244 | 0.2036 | 1.5059 | 5.3407 |
| auto_expanding_3 | CCUSDT | mlofi_roll10_l25 | high_train_q80 | long | 70 | 122305 | 0.1879 | 0.9070 | 4.0729 |
| auto_expanding_3 | CCUSDT | pos__mlofi_roll10_l25 | high_train_q80 | long | 70 | 122305 | 0.1879 | 0.9070 | 4.0729 |
| auto_expanding_3 | CCUSDT | pos__trade_arrival_alignment | high_train_q80 | long | 14 | 60244 | 0.1788 | 1.1208 | 3.9472 |
| auto_expanding_3 | CCUSDT | mlofi_roll10_l1 | high_train_q80 | long | 70 | 128796 | 0.1197 | 1.0126 | 3.5660 |
| auto_expanding_3 | CCUSDT | pos__mlofi_roll10_l1 | high_train_q80 | long | 70 | 128796 | 0.1197 | 1.0126 | 3.5660 |
| auto_expanding_3 | CCUSDT | signed_sq__mlofi_roll10_l1 | high_train_q80 | long | 70 | 128796 | 0.1197 | 1.0126 | 3.5660 |
| auto_expanding_3 | CCUSDT | mlofi_roll10_l25 | high_train_q80 | long | 35 | 122305 | 0.1746 | 0.8251 | 3.5287 |
| auto_expanding_3 | CCUSDT | pos__mlofi_roll10_l25 | high_train_q80 | long | 35 | 122305 | 0.1746 | 0.8251 | 3.5287 |

## Controls And Read

Negative controls include wrong-symbol same-factor, within-day shuffled event time, reversed-sign gate, future-shift placebo, and same-state opposite-side checks where candidates are available. Candidates that do not clearly separate from controls are classified as window/cost artifacts.

Follow-up audit read: do not promote the current top path. `trade_arrival_alignment` must be rebuilt without future-trade leakage/control ambiguity before it can be ranked. Profit/after-cost overlay was not run for this panel; `dlog_mid` Spearman and path diagnostics are information tests only, not realized PnL evidence.

## Output Tables

- `date/ccusdt_v1_fixed_event_factors_quality_20260517_ccusdt_fixed_factors_v2.csv`
- `date/ccusdt_v1_fixed_event_factors_factor_params_20260517_ccusdt_fixed_factors_v2.csv`
- `date/ccusdt_v1_fixed_event_factors_path_ranking_20260517_ccusdt_fixed_factors_v2.csv`
- `date/ccusdt_v1_fixed_event_factors_stability_20260517_ccusdt_fixed_factors_v2.csv`
- `date/ccusdt_v1_fixed_event_factors_negative_controls_20260517_ccusdt_fixed_factors_v2.csv`
- `date/ccusdt_v1_fixed_event_factors_spearman_20260517_ccusdt_fixed_factors_v2.csv`
- `date/ccusdt_v1_fixed_event_factors_episode_overlay_20260517_ccusdt_fixed_factors_v2.csv`

## Reproduce

```bash
cargo run -p cex_l2_research --bin tardis_bullish_fixed_factor_panel --release -- --data-root data\ccusdt\v1 --date-dir date --doc-dir docs\markets\ccusdt --output-prefix ccusdt_v1_fixed_event_factors --panel-dataset ccusdt_v1_fixed_event_factor_panel --report-name v1-fixed-event-orderbook-factors-v2.md --market-label "CCUSDT" --from-date 2026-04-29 --to-date 2026-05-15 --symbols CCUSDT --run-tag 20260517_ccusdt_fixed_factors_v2
```

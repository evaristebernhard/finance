# CCUSDT Fixed Event-Defined OFI/MLOFI

Status: 2026-05-17. Run tag: `20260517_ccusdt_fixed_factors_v1`.

Superseded: go directly to `v1-fixed-event-orderbook-factors-v3.md` / run tag `20260517_ccusdt_fixed_factors_v3`. This first pass treated continuous Bullish snapshot batches as incremental updates, producing replay artifacts in OFI/MLOFI diagnostics.

Guardrail: `research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim`.

## Scope

This pass starts from local `bullish_incremental_book_L2` and `bullish_trades` raw CSV.GZ files. It does not download raw data, delete raw files, or treat prior snapshot-factor mining conclusions as discovery evidence.

The event layer defines queue events directly from raw price-level updates. Snapshot batches reset the local book and are retained for continuity/quality, but are excluded from factor ranking.

## Coverage

- Completed symbol-days: `17/17`.
- Event panel rows: `2606830`.
- Low-confidence execute/cancel split symbol-days: `17`.
- Fixed feature definitions per fold: `105`.
- Factor params rows: `315`.
- Path ranking rows: `2436`.
- Stability rows: `219608`.
- Negative control rows: `320` across `4` control types.

## Event Definitions

- New price with positive amount is `limit_add/create`.
- Size increase at an existing price is `replenish/add`.
- Size decrease or zero amount is queue depletion, split into executable and cancellation/withdrawal using nearby trades.
- Trade side is taker-side: `buy` consumes asks and `sell` consumes bids.
- If day-level matched depletion rate is below 60%, execute/cancel split is marked `low_confidence`; aggregate depletion/replenish factors remain usable diagnostics.

## Factor Families

Main ranked families are CKS best-level OFI, XGH-style MLOFI at levels `1/2/3/5/10/25`, depth-normalized/rolling event-time MLOFI, quote/queue imbalance, microprice deviation, queue depletion, replenish, cancellation/withdrawal, trade-arrival alignment, liquidity-shock resiliency, and cross-venue MLOFI lead-lag. Each base feature is tested as raw, absolute, positive-part, negative-part, and signed-square variants, giving a fixed reusable 100+ feature surface. Depth slope/curvature is intentionally not promoted here.

## Top Path Diagnostics

| fold | symbol | feature | gate | side | horizon_events | selected | fav-adv | side_ret_bps | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| auto_expanding_3 | CCUSDT | microprice_dev_bps | high_train_q80 | long | 130 | 3910 | 0.4844 | 7.0435 | 20.8260 |
| auto_expanding_3 | CCUSDT | signed_sq__microprice_dev_bps | high_train_q80 | long | 130 | 3910 | 0.4844 | 7.0435 | 20.8260 |
| auto_expanding_3 | CCUSDT | queue_imbalance_1 | high_train_q80 | long | 130 | 3833 | 0.4800 | 7.0163 | 20.7075 |
| auto_expanding_3 | CCUSDT | signed_sq__queue_imbalance_1 | high_train_q80 | long | 130 | 3833 | 0.4800 | 7.0163 | 20.7075 |
| auto_expanding_3 | CCUSDT | microprice_dev_bps | high_train_q80 | long | 65 | 3910 | 0.4036 | 4.2218 | 13.7926 |
| auto_expanding_3 | CCUSDT | signed_sq__microprice_dev_bps | high_train_q80 | long | 65 | 3910 | 0.4036 | 4.2218 | 13.7926 |
| auto_expanding_3 | CCUSDT | queue_imbalance_1 | high_train_q80 | long | 65 | 3833 | 0.3992 | 4.1795 | 13.6062 |
| auto_expanding_3 | CCUSDT | signed_sq__queue_imbalance_1 | high_train_q80 | long | 65 | 3833 | 0.3992 | 4.1795 | 13.6062 |
| auto_expanding_3 | CCUSDT | queue_imbalance_5 | high_train_q80 | long | 130 | 1817 | 0.3335 | 3.4672 | 11.3921 |
| auto_expanding_3 | CCUSDT | signed_sq__queue_imbalance_5 | high_train_q80 | long | 130 | 1817 | 0.3335 | 3.4672 | 11.3921 |

## Controls And Read

Negative controls include wrong-symbol same-factor, within-day shuffled event time, reversed-sign gate, future-shift placebo, and same-state opposite-side checks where candidates are available. Candidates that do not clearly separate from controls are classified as window/cost artifacts.

No V1 path is promoted. The conservative read is replay-artifact reference only; execution/usability and directional-alpha claims should be based on later corrected diagnostics plus a separate profit/after-cost overlay.

## Output Tables

- `date/ccusdt_v1_fixed_event_factors_quality_20260517_ccusdt_fixed_factors_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_factor_params_20260517_ccusdt_fixed_factors_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_path_ranking_20260517_ccusdt_fixed_factors_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_stability_20260517_ccusdt_fixed_factors_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_negative_controls_20260517_ccusdt_fixed_factors_v1.csv`
- `date/ccusdt_v1_fixed_event_factors_episode_overlay_20260517_ccusdt_fixed_factors_v1.csv`

## Reproduce

```bash
cargo run -p cex_l2_research --bin tardis_bullish_fixed_factor_panel --release -- --data-root data\ccusdt\v1 --date-dir date --doc-dir docs\markets\ccusdt --output-prefix ccusdt_v1_fixed_event_factors --panel-dataset ccusdt_v1_fixed_event_factor_panel --report-name v1-fixed-event-orderbook-factors.md --market-label "CCUSDT" --from-date 2026-04-29 --to-date 2026-05-15 --symbols CCUSDT --run-tag 20260517_ccusdt_fixed_factors_v1
```

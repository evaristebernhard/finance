# BONK V10c Event-Defined OFI/MLOFI

Status: 2026-05-15. Run tag: `20260514_bonk_v10_stage1_pilot`.

Guardrail: `research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim`.

## Scope

This pass starts from local `bullish_incremental_book_L2` and `bullish_trades` raw CSV.GZ files. It does not download raw data, rerun V10 replay, delete raw files, or treat V10/V10b snapshot-factor mining conclusions as discovery evidence.

The event layer defines queue events directly from raw price-level updates. Snapshot batches reset the local book and are retained for continuity/quality, but are excluded from factor ranking.

## Coverage

- Completed symbol-days: `14/14`.
- Event panel rows: `1945574`.
- Low-confidence execute/cancel split symbol-days: `14`.
- Factor params rows: `126`.
- Path ranking rows: `697`.
- Stability rows: `622366`.
- Negative control rows: `400` across `5` control types.

## Event Definitions

- New price with positive amount is `limit_add/create`.
- Size increase at an existing price is `replenish/add`.
- Size decrease or zero amount is queue depletion, split into executable and cancellation/withdrawal using nearby trades.
- Trade side is taker-side: `buy` consumes asks and `sell` consumes bids.
- If day-level matched depletion rate is below 60%, execute/cancel split is marked `low_confidence`; aggregate depletion/replenish factors remain usable diagnostics.

## Factor Families

Main ranked families are CKS best-level OFI, XGH-style MLOFI at levels `1/2/3/5/10/25`, depth-normalized/rolling event-time MLOFI, quote/queue imbalance, microprice deviation, queue depletion, replenish, cancellation/withdrawal, trade-arrival alignment, liquidity-shock resiliency, and cross-venue MLOFI lead-lag. Depth slope/curvature is intentionally not promoted here.

## Top Path Diagnostics

| fold | symbol | feature | gate | side | horizon_events | selected | fav-adv | side_ret_bps | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold1 | BONK1MUSDC | mlofi_norm_l10 | high_train_q80 | long | 30 | 4123 | 0.1317 | 0.6772 | 1.3959 |
| fold1 | BONK1MUSDC | queue_imbalance_25 | high_train_q80 | long | 30 | 9251 | 0.0945 | 0.5218 | 0.3354 |
| fold1 | BONK1MUSDC | mlofi_norm_l10 | high_train_q80 | long | 15 | 4123 | 0.1004 | 0.4015 | 0.3300 |
| fold1 | BONK1MUSDC | mlofi_norm_l5 | high_train_q80 | long | 30 | 6746 | 0.0854 | 0.4788 | -0.0990 |
| fold1 | BONK1MUSDC | mlofi_norm_l10 | high_train_q80 | long | 10 | 4123 | 0.0810 | 0.2847 | -0.3141 |
| fold1 | BONK1MUSDC | mlofi_roll10_l5 | high_train_q80 | long | 30 | 6098 | 0.0690 | 0.3626 | -0.5431 |
| fold1 | BONK1MUSDC | queue_imbalance_25 | high_train_q80 | long | 15 | 9251 | 0.0610 | 0.2637 | -0.7805 |
| fold1 | BONK1MUSDC | mlofi_norm_l5 | high_train_q80 | long | 15 | 6746 | 0.0621 | 0.2614 | -0.8438 |
| fold1 | BONK1MUSDC | mlofi_norm_l3 | high_train_q80 | long | 30 | 10785 | 0.0498 | 0.2541 | -1.1217 |
| fold1 | BONK1MUSDC | mlofi_roll10_l5 | high_train_q80 | long | 15 | 6098 | 0.0502 | 0.1922 | -1.1809 |

## Controls And Read

Negative controls include wrong-symbol same-factor, within-day shuffled event time, reversed-sign gate, future-shift placebo, and same-state opposite-side checks where candidates are available. Candidates that do not clearly separate from controls are classified as window/cost artifacts.

No stable after-cost overlay candidate is promoted; the conservative read is execution/usability filter > directional alpha.

## Output Tables

- `date/bonk_v10c_event_ofi_quality_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10c_event_ofi_factor_params_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10c_event_ofi_path_ranking_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10c_event_ofi_stability_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10c_event_ofi_negative_controls_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10c_event_ofi_episode_overlay_20260514_bonk_v10_stage1_pilot.csv`

## Reproduce

```bash
cargo run -p cex_l2_research --bin bonk_v10c_event_ofi_panel --release
```

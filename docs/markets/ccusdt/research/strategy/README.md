# Strategy Reports

This folder keeps reports about turning factor evidence into policy: four-cell
membership, capacity, leverage, watcher, path manager, conditional wait, and
exit timing.

Runtime warning: strategy reports are not the source of truth for what the Bot
currently does. Read
`docs/markets/ccusdt/current/CURRENT_STRATEGY_PLAIN.md` first. Many files here
describe research参考, failed branches, or follow-up hypotheses. In particular,
`Delta_bps/Energy_bps`, OFI/MLOFI, dynamic L2 path prediction, deep learning,
maker work, and capacity curves have not entered current CC runtime control
unless a runtime profile explicitly says so.

Do not compare strategy totals unless policy, capacity, exit, fill, latency, and
transport profiles match.

## New Family Discovery

- `v1-microstructure-structure-family-map-20260601.md`: first-principles structure-family map. It reclassifies the old four-cell policy as `S1 active-flow stale-release`, defines how factors can play different roles across structure families, and sets the composition model for future multi-structure strategy research.
- `v1-structure-family-fast-research-20260601.md`: first fast evidence pass for S1/S2/S3/S4/S6/S7 over `2026-05-16..2026-05-18`. It reports release, decay, top-of-book executable labels, spread-cost mirages, and role classification; `S5 post-release exit/wait` is explicitly deferred to a path study.
- `v1-event-regime-discovery-20260601.md`: fast decision-frame scan for event/regime families outside the existing TFI/R5 tuning loop. It evaluates spread shock, depth collapse, trade burst, quote refresh, sweep-after-quiet, absorption/reversal, volatility expansion, and vacuum families using executable taker labels.
- `v1-multicoin-candidate-screen-20260602.md`: no-download reread of the historical Bullish symbol-volatility screen. It recommends `ETHFIUSDC/IOTAUSDT/NIGHTUSDT/SUIUSDC` as the first non-BTC/ETH/SOL migration basket and keeps major symbols as efficiency controls.
- `v1-multicoin-entry-trigger-pilot-20260602.md`: first migration pilot after downloading/building ETHFIUSDC and IOTAUSDT decision frames. ETHFIUSDC shows positive executable evidence across two days; IOTAUSDT is positive but only one evaluated day. SUIUSDC and NIGHTUSDT are ingestion-incomplete in this pass.
- `v1-ethfiusdc-r5-delta-energy-group-analysis-20260602.md`: corrective ETHFIUSDC audit showing that binary `R5` cells are too lossy; `Delta`, `Energy`, and `Z` materially change the interpretation, especially for `10_r5_only` and high-memory-strength states.
- `v1-ethfiusdc-structure-combo-strategy-20260602.md`: ETHFIUSDC v0.1 structure-combo fast strategy diagnostic. It tests E0 episode compression, fixed-small sizing, memory sizing, path labels, cost stress, side-flip control, and matched-time control.
- `v1-ccusdt-memory-strength-pareto-control-20260603.md`: CCUSDT research-only Pareto control pass that injects reconstructed `Delta_bps`, `Energy_bps`, and `Z_bps` into exposure sizing over existing fast candidates. It finds old control still wins at zero stress, while memory-strength controls dominate under +1/+2/+3bps pressure.

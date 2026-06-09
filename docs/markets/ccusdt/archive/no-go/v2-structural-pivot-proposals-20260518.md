# CCUSDT V2 Structural Pivot Proposals

Status: 2026-05-18.

Guardrail: `research_only_no_execution_recommendation_no_alpha_claim`.

Skill used: `strategy-pivot-designer`, because the current CCUSDT iteration loop is stalled by execution cost defeat, queue-fill failure, and tail concentration. These are structural failures; parameter tuning is not an appropriate next step.

## Stagnation Diagnosis

| trigger | evidence | interpretation |
| --- | --- | --- |
| `cost_defeat` | all-practical maker best per-signal net is `-0.0038` bps versus `2` bps target | observed information edge is too thin or inaccessible after real execution |
| `execution_fill_failure` | `45/45` all-practical L2 queue bins are no-go | maker queue access does not monetize the signal |
| `tail_concentration` | top-tail share failures across candidate rows | winners are clustered rather than stable |
| `weak_internal_controls` | best taker row fails sample, controls, tail, and risk | immediate crossing does not rescue the strategy |

## Pivot Drafts

| rank | draft | pivot type | why it is structurally different |
| --- | --- | --- | --- |
| 1 | `pivot_drafts/research_only/ccusdt_v2_pivot_queue_release_continuation.yaml` | assumption inversion | waits for queue-release evidence instead of entering before fill |
| 2 | `pivot_drafts/research_only/ccusdt_v2_pivot_cross_market_lead_lag.yaml` | archetype switch | uses external information leadership instead of single-venue TFI |
| 3 | `pivot_drafts/research_only/ccusdt_v2_pivot_liquidity_envelope_universe.yaml` | objective reframe | screens execution envelope before alpha mining |

## Non-Pivots

These should not be treated as valid next work:

- Re-tuning TP/SL grids on current TFI candidates.
- Re-labeling the same rows with a more optimistic maker assumption.
- Selecting post-hoc feature filters from validation-side fill outcomes.
- Treating the `tfi_event_active/mid` taker mean as tradable despite failed controls.

## Recommended Next Choice

The most direct CCUSDT-specific pivot is `queue_release_continuation`, because it inverts the failed assumption: instead of predicting that queue movement will happen after entry, it waits until queue movement is observable and then tests whether quote release continues.

The highest-confidence practical pivot is `liquidity_envelope_universe`, because current evidence suggests CCUSDT itself may be the wrong execution envelope for this style of edge.

## First Pivot Prototype Result

The lightweight `book_ticker` queue-release prototype is documented in:

```text
docs/markets/ccusdt/v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_fast_v1.md
```

It emitted:

```text
date/ccusdt_v2_queue_release_events_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_controls_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_fast_v1.json
```

Readout: `0/24` scorecard rows passed local gates. The best row was `expanding_fold3 / bid_release_short / 10s / q=0.99` with `1095` entries and `-1.7573` bps net mean. It beat matched random by about `1.69` bps, but still failed economics, stress, median, and promotion gates.

## Cross-Market Lead/Lag Smoke Result

The first BTC/ETH/SOL-to-CCUSDT cross-market smoke is documented in:

```text
docs/markets/ccusdt/v2-cross-market-lead-lag-20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.md
```

It emitted:

```text
date/ccusdt_v2_cross_market_events_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv
date/ccusdt_v2_cross_market_controls_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv
date/ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv
date/ccusdt_v2_cross_market_summary_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.json
```

Readout: `0/90` scorecard rows passed local gates. The best row was `SOLUSDC / leader_ret_5s_follow / expanding_fold3 / 10s` with `1569` entries, gross mean `0.9865` bps, cost mean `3.9243` bps, and net mean `-2.9377` bps. It beat the capped matched-random p50 by `1.3079` bps and the reversed-side control by `1.9731` bps, but those margins remain below or barely under the `2` bps control gate and economics are still negative after cost.

## Absorption/Replenishment Reversal Result

The structurally new failed-breakout pivot is documented in:

```text
docs/markets/ccusdt/v2-absorption-reversal-pivot-20260518_ccusdt_v2_absorption_reversal_pivot_v1.md
```

It emitted:

```text
date/ccusdt_v2_absorption_reversal_panel_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_events_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_controls_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_summary_20260518_ccusdt_v2_absorption_reversal_pivot_v1.json
```

Readout: `0/72` scorecard rows passed local gates. The best gross row was `expanding_fold3 / buy_absorption_short / 10s / q=0.99` with gross mean `3.9939` bps, but cost mean `4.3044` bps left net mean at `-0.3104` bps and median at `-4.7634` bps. The available `2026-05-16` OOS fold was small-sample and negative. This is useful as a structural failure decomposition, not a promotable entry mechanism.

## External Venue Inventory Result

The local external-venue inventory is documented in:

```text
docs/markets/ccusdt/v2-external-venue-inventory-20260518_ccusdt_v2_external_venue_inventory_v1.md
```

It emitted:

```text
date/ccusdt_v2_external_venue_inventory_20260518_ccusdt_v2_external_venue_inventory_v1.csv
date/ccusdt_v2_external_venue_inventory_20260518_ccusdt_v2_external_venue_inventory_v1.json
```

Readout: local files have CCUSDT L2 only on `bullish`. The only other venue detected is `binance`, but the available files are coarse `1m` spot klines under the BONK research tree, not synchronized CCUSDT/CC-related L2. The true external-venue version of the cross-market pivot is therefore data-blocked locally.

## Tardis External Metadata Probe Result

The metadata-only Tardis external venue probe is documented in:

```text
docs/markets/ccusdt/v2-tardis-external-metadata-probe-20260518_ccusdt_v2_tardis_external_metadata_probe_v1.md
```

It emitted:

```text
date/ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.csv
date/ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.json
```

Readout: Tardis metadata has CC orderbook symbols on `binance-futures`, `bybit`, `kucoin`, and `okex`, but the current API key has `0` accessible external CC L2 venues. Bullish is accessible, but it is the target venue already used by the local CCUSDT path. The external-venue lead/lag pivot is therefore blocked by both local file inventory and current Tardis access.

## External Acquisition Gate Result

The no-download external acquisition gate is documented in:

```text
docs/markets/ccusdt/v2-external-acquisition-plan-20260518_ccusdt_v2_external_acquisition_plan_v1.md
```

It emitted:

```text
date/ccusdt_v2_external_acquisition_manifest_20260518_ccusdt_v2_external_acquisition_plan_v1.csv
date/ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json
```

Readout: the gate converted the external metadata candidates into `255` manifest rows across `binance-futures`, `bybit`, `kucoin`, and `okex`, but every row is `blocked_access` and `planned_rows=0`. If external access is granted later, the same manifest path can advance to the metadata/Range size probe before any dataset body download.

## Stop/Pivot Gate Result

The current machine-readable stop/pivot gate is documented in:

```text
docs/markets/ccusdt/v2-stop-pivot-gate-20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.md
```

It emitted:

```text
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.csv
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.json
```

Readout: `14` critical gates fail and the decision is `stop_current_ccusdt_path_pivot_or_new_data_required`. The blocked research modes are TP/SL grid retuning on current candidates, post-hoc fill filters, maker/taker assumption switching without new execution evidence, same-venue cross-market tuning without external data or a new mechanism, absorption-threshold tuning on the same validation rows, and alpha search before the execution envelope passes.

## Liquidity Envelope Prototype Result

The execution-first CCUSDT liquidity-envelope audit is documented in:

```text
docs/markets/ccusdt/v2-liquidity-envelope-audit-20260518_ccusdt_v2_liquidity_envelope_audit_v1.md
```

It emitted:

```text
date/ccusdt_v2_liquidity_envelope_daily_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv
date/ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv
date/ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_liquidity_envelope_audit_v1.json
```

Readout: CCUSDT is `liquidity_envelope_no_go` for the current `$100` target-notional version of this edge family. The median daily median spread is `2.0148` bps, the median daily 5th-percentile top-of-book depth is only `0.0952` quote, and `0/17` days pass the top-depth support gate. Existing practical maker/taker evidence also fails: best practical maker fill rate is `11.76%`, best maker per-signal net is `-0.0038` bps, and taker promote-gate rows are `0`.

## Local Universe Inventory Result

The local Bullish L2 universe inventory is documented in:

```text
docs/markets/ccusdt/v2-local-universe-inventory-20260518_ccusdt_v2_local_universe_inventory_v1.md
```

It emitted:

```text
date/ccusdt_v2_local_bullish_universe_inventory_20260518_ccusdt_v2_local_universe_inventory_v1.csv
date/ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_v1.json
```

Readout: this handoff currently has only one local Bullish core L2-ready symbol, `CCUSDT`, with `17` common `book_ticker`, `trades`, and `incremental_book_L2` dates. The `liquidity_envelope_universe` pivot is therefore framework-ready but data-blocked locally; it needs additional Bullish symbols before it can become a real selection pass.

## Current Local Universe Inventory Result

The current local Bullish inventory is documented in:

```text
docs/markets/ccusdt/v2-local-universe-inventory-20260518_ccusdt_v2_local_universe_inventory_current_v1.md
```

It emitted:

```text
date/ccusdt_v2_local_bullish_universe_inventory_20260518_ccusdt_v2_local_universe_inventory_current_v1.csv
date/ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_current_v1.json
```

Readout: the local universe inventory blocker is resolved for the small-tier path: `6` symbols are core-L2-ready (`CCUSDT`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, `SUIUSDC`, `WIFUSDC`). This does not unlock execution by itself because the small-tier and full-universe liquidity-envelope screens still have `0` candidates at the target `$100` notional.

## Bullish Universe Preflight Result

The dry-run Tardis metadata preflight for the next data step is documented in:

```text
docs/markets/ccusdt/v2-universe-preflight-20260518_ccusdt_v2_universe_preflight_v1.md
```

It emitted:

```text
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_universe_preflight_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_universe_preflight_v1.csv
```

Readout: no files were downloaded. The preflight planned `561` file jobs for `11` metadata-available Bullish symbols over `2026-04-29..2026-05-15`: `CCUSDT`, `BTCUSDC`, `ETHUSDC`, `SOLUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, `WIFUSDC`, `SUIUSDC`, `BONK1MUSDC`, and `BONK1MUSDT`. `APTUSDC`, `ARBUSDC`, and `OPUSDC` were missing from Bullish metadata.

## Bullish Universe Size Smoke Result

The bounded metadata/Range size smoke is documented in:

```text
docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_smoke_v1.md
```

It emitted:

```text
date/ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_universe_size_probe_smoke_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_smoke_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_smoke_v1.json
```

Readout: the first-date smoke probe checked `33` planned files (`11` symbols x `3` core L2 data families) and found `33/33` available with an estimated `3.61` GB for that single date. `ETHUSDC` and `BTCUSDC` incremental L2 dominate the sample. This confirms the full universe data step should be staged by symbol/date and disk budget before any alpha search.

## OOS Days Size Probe Result

The no-download OOS days probe is documented in:

```text
docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_oos_days_size_probe_v1.md
```

It emitted:

```text
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_days_preflight_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_oos_days_preflight_v1.csv
date/ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_oos_days_size_probe_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json
```

Readout: `2026-05-16` is available for all six current core-L2 symbols and core data families; `2026-05-17` is not yet available. The available day is about `0.24` GB.

The available OOS day was then downloaded and screened:

```text
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_oos_day20260516_download_v1.csv
docs/markets/ccusdt/v2-universe-liquidity-envelope-20260518_ccusdt_v2_oos_day20260516_envelope_v1.md
date/ccusdt_v2_universe_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_envelope_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_envelope_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json
```

Follow-up readout: the 18-day small-tier envelope still has `0` pre-alpha candidates. `DOGEUSDC` fails spread and activity; `SUIUSDC` fails spread, depth, and activity; `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC` remain effectively empty/unreadable for envelope purposes.

The same OOS CCUSDT files were also copied into the canonical `data/ccusdt/v1` tree and the CCUSDT envelope was rerun:

```text
docs/markets/ccusdt/v2-liquidity-envelope-audit-20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.md
date/ccusdt_v2_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.csv
date/ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.csv
date/ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json
```

Canonical CCUSDT readout: `liquidity_envelope_no_go` over `18` days. The OOS-data unlock was tested for both the small-tier universe and CCUSDT itself, and does not advance to alpha modeling.

## Bullish Small-Tier Size Probe Result

The full-window small-tier metadata/Range size probe is documented in:

```text
docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_small_tier_v1.md
```

It emitted:

```text
date/ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.json
```

Readout: `SUIUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC` across `17` dates and `3` core L2 data families returned `255/255` available files with an estimated `0.40` GB total. `SUIUSDC` and `DOGEUSDC` carry nearly all nontrivial bytes; `PEPE/SHIB/WIF` are metadata-available but appear near-empty and need row validation if downloaded. This is the current practical pilot tier for the universe-envelope pivot.

No pivot is executable until it passes the same V2 gates:

- purged walk-forward;
- matched controls;
- residual controls;
- real cost ladder;
- practical maker/taker execution evidence;
- tail and risk gates;
- stable real-cost `>2` bps capture.

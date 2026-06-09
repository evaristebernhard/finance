# CCUSDT V2 Current Execution No-Go Handoff

Status: 2026-05-18.

Guardrail: `research_framework_only_no_execution_recommendation_no_alpha_claim`.

This handoff summarizes the current CCUSDT/CEX L2 short-horizon microstructure research state after the V2 framework, all-practical maker queue-fill audit, fill-aware repair scan, taker fallback audit, execution failure decomposition, queue-release pivot, liquidity-envelope audit, BTCUSDC top-of-book factor decomposition, BTC/ETH/SOL-to-CCUSDT cross-market lead/lag smoke, local external-venue inventory, and Tardis external metadata feasibility probe.

## Bottom Line

The research framework is now systematized, but the active objective is not achieved.

Current candidates should be treated as `execution_no_go`:

- No framework row is promoted.
- All practical maker queue-fill rows are no-go.
- No simple fill-aware entry filter repairs execution.
- Taker/crossing fallback does not pass combined gates.
- The best maker per-signal execution result is negative, not near the `2` bps target.
- CCUSDT fails the execution-first liquidity envelope for the `$100` target notional.
- The original local Bullish L2 inventory had only one core-ready symbol, so the first universe step downloaded and screened additional symbols before alpha mining.
- Tardis/Bullish dry-run metadata preflight found 11 schedulable symbols for a future universe download.
- A bounded first-day size probe found 33/33 planned files available and estimated 3.61 GB for one date, so the full universe download should be staged.
- A small-tier full-window size probe found 255/255 planned files available for five lighter symbols, with only about 0.40 GB estimated.
- The small-tier full L2 pilot downloaded 255/255 files, but no small-tier symbol passed the pre-alpha liquidity envelope.
- A remaining-tier top-of-book/trades download added BTC/ETH/SOL/BONK coverage, but the `$100` universe envelope still found 0 candidates.
- Target-notional sensitivity found only `BTCUSDC` as a pre-alpha liquidity candidate at `$10` and `$5`; this is capacity screening, not an alpha result.
- The current local Bullish inventory is multi-symbol core-L2 ready with `6` symbols (`CCUSDT`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, `SUIUSDC`, `WIFUSDC`); the blocker is no longer local inventory for this tier, but the failed execution envelope and alpha diagnostics.
- A no-download OOS availability probe for `2026-05-16..2026-05-17` found `2026-05-16` available for the six core-L2 symbols and `2026-05-17` not yet available. A standalone `2026-05-17` follow-up probe still found `0/18` core L2 files available. The available `2026-05-16` files were downloaded, but the updated 18-day small-tier envelope still found `0` pre-alpha candidates, and the canonical 18-day CCUSDT liquidity envelope remains `liquidity_envelope_no_go`.
- OOS notional sensitivity did not unlock the path: canonical CCUSDT still fails at `$10`, and the OOS small-tier set still has `0` candidates at both `$10` and `$5`.
- The first BTCUSDC top-of-book queue-release fast diagnostic also found `0` promote-gate rows, so BTC small-notional capacity has not become executable evidence.
- The first BTCUSDC top-of-book factor smoke found `0` promote-gate rows as well; best after-cost mean remained negative.
- The BTCUSDC top-of-book gross/cost decomposition shows the best gross move is only `0.5944` bps versus about `4.0125` bps required to clear fee stress plus the `+2` bps target.
- The BTC/ETH/SOL-to-CCUSDT cross-market lead/lag smoke found `0` promote-gate rows; best net row was `SOLUSDC / leader_ret_5s_follow / 10s` with gross `0.9865` bps, cost `3.9243` bps, and net `-2.9377` bps.
- The absorption/replenishment reversal pivot tested a structurally new failed-breakout entry mechanism over the canonical CCUSDT window plus the available `2026-05-16` OOS fold; it found `0/72` promote rows. Best gross mean was `3.9939` bps, but best net mean remained negative at `-0.3104` bps after cost.
- Local external-venue inventory is data-blocked for the true cross-venue version: CCUSDT L2 exists only on Bullish locally; Binance files are coarse `1m` klines and do not provide synchronized CCUSDT L2.
- Tardis metadata shows CC orderbook symbols on external venues (`binance-futures`, `bybit`, `kucoin`, `okex`), but the current API access has `0` accessible external CC L2 venues; only Bullish is accessible under the checked key.
- The external acquisition gate materialized those external metadata candidates into a no-download manifest with `255` rows, but all rows are `blocked_access` and `planned_rows=0`.
- The refreshed stop/pivot gate is active: `14` critical gates fail, so the current CCUSDT path should not continue via TP/SL retuning, post-hoc filters, maker/taker assumption switching, same-venue cross-market tuning, or absorption-threshold tuning without new data/access/mechanism.

Do not continue by tuning TP/SL grids, narrowing post-hoc filters, or switching between maker/taker assumptions on the same candidates.

## Hard Evidence

| branch | artifact | result |
| --- | --- | --- |
| Framework scorecard | `date/ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv` | `0` promoted rows; `4` research-continue rows only |
| Focused maker proxy | `date/ccusdt_v2_fill_realism_scorecard_20260518_ccusdt_v2_fill_realism_v1.csv` | `5/5` focused rows no-go |
| Focused L2 queue fill | `date/ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_v1.csv` | `5/5` focused rows no-go |
| All-practical L2 queue fill | `date/ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv` | `45/45` framework bins no-go over `6447` entries |
| Fill-aware repair | `date/ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv` | `0/3741` post-hoc filters pass execution gates |
| Taker fallback | `date/ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv` | `45/45` bins no-go; `0` taker promote-gate rows |
| Execution decomposition | `date/ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.csv` | best maker per-signal net `-0.0038` bps versus `2` bps target |
| Queue-release pivot prototype | `date/ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv` | `0/24` rows pass; best mean `-1.7573` bps |
| Liquidity envelope audit | `date/ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv` | `liquidity_envelope_no_go`; median daily median spread `2.0148` bps; `0/17` days pass `$100` top-depth support |
| Local universe inventory | `date/ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_v1.json` | `single_or_no_symbol_only`; only `CCUSDT` is local core L2-ready |
| Universe preflight | `date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_universe_preflight_v1.json` | dry-run only; 11 planned symbols, 3 missing symbols, 561 planned file jobs |
| Universe size probe | `date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_smoke_v1.json` | bounded first-day smoke; 33/33 files available; 3.61 GB estimated |
| Small-tier size probe | `date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.json` | full-window metadata/Range probe; 255/255 files available; 0.40 GB estimated |
| Small-tier download | `date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_small_tier_download_v1.json` | 255/255 files written; 153 downloaded, 102 empty |
| Post-download local inventory | `date/ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_after_small_tier_v1.json` | `multi_symbol_ready` by core L2 path coverage; row-level envelope still required |
| Small-tier liquidity envelope | `date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_small_tier_v1.csv` | 0/5 pre-alpha candidates |
| Current local Bullish inventory | `date/ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_current_v1.json` | `multi_symbol_ready`; `6` core-L2-ready symbols: `CCUSDT,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,SUIUSDC,WIFUSDC` |
| OOS days size probe | `date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json` | 36 planned files probed for `2026-05-16..2026-05-17`; 18 available, 18 missing, 0 errors, 0.24 GB estimated |
| OOS day 2026-05-17 standalone size probe | `date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.json` | 18 planned files probed; 0 available, 18 missing, 0 errors, 0.00 GB estimated |
| OOS day 2026-05-16 download | `date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json` | 18 files written for six core-L2 symbols; 12 downloaded, 6 empty |
| OOS day 2026-05-16 envelope | `date/ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json` | 18-day small-tier screen; 0 pre-alpha candidates |
| CCUSDT OOS liquidity envelope | `date/ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json` | 18-day canonical CCUSDT screen; `liquidity_envelope_no_go` |
| OOS target-notional sensitivity | `date/ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.json`; `date/ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.json`; `date/ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.json` | CCUSDT `$10` remains no-go; small-tier `$10/$5` candidates: none |
| Remaining-tier size probe | `date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1.json` | 253/255 available, 2 probe errors, 52.64 GB estimated for full L2 |
| Remaining-tier top-of-book/trades download | `date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_remaining_tob_trades_download_v1.json` | 170/170 downloaded |
| Full local top-of-book universe envelope | `date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.csv` | 0/10 candidates at `$100`; BTC/ETH/SOL/BONK fail depth, DOGE fails spread/activity |
| Target-notional sensitivity | `date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1.csv` | only `BTCUSDC` passes pre-alpha envelope at `$10`; same candidate set at `$5` |
| BTCUSDC queue-release fast diagnostic | `date/ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv` | 18 rows; 0 promote-gate rows; best mean `-1.7210` bps |
| BTCUSDC top-of-book factor smoke | `date/ccusdt_v2_tob_factor_scorecard_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv` | 45 rows; 0 promote-gate rows; best mean `-1.4181` bps |
| BTCUSDC top-of-book gross/cost decomposition | `date/ccusdt_v2_tob_factor_decomposition_20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.csv` | 45 rows; 0 promote-gate rows; best gross mean `0.5944` bps; best gross shortfall to net `+2` bps is `-3.4181` bps |
| Cross-market lead/lag BTC/ETH/SOL smoke | `date/ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv` | 90 rows; 0 promote-gate rows; best net mean `-2.9377` bps |
| Absorption/replenishment reversal pivot | `date/ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv` | 72 rows; 0 promote-gate rows; best gross mean `3.9939` bps; best net mean `-0.3104` bps |
| External venue inventory | `date/ccusdt_v2_external_venue_inventory_20260518_ccusdt_v2_external_venue_inventory_v1.json` | `external_venue_ccusdt_l2_data_blocked`; CCUSDT L2 venues locally: `bullish` only |
| Tardis external metadata probe | `date/ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.json` | `external_tardis_cc_l2_metadata_blocked`; external CC L2 metadata: `binance-futures,bybit,kucoin,okex`; accessible external CC L2: none |
| External acquisition gate | `date/ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json` | `external_acquisition_blocked_by_access`; `255` manifest rows, `0` planned rows, `255` blocked-access rows |
| Stop/pivot gate after absorption reversal | `date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.json` | `stop_current_ccusdt_path_pivot_or_new_data_required`; `14` failed gates |
| Updated completion audit after absorption reversal | `date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_absorption_reversal_v1.json` | `completion_status=not_achieved`; includes universe/OOS continuation, BTC diagnostics, TOB decomposition, cross-market smoke, absorption reversal, local external-venue inventory, Tardis metadata feasibility, external acquisition gate, and stop/pivot gate |
| Completion audit | `date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.json` | `completion_status=not_achieved` |

## Current Best Rows

### Maker Practical

Best all-practical maker queue row:

```text
fold/trigger/bin:  expanding_fold3 / tfi_short_flat / high
signals:           391
fill_rate:         4.35%
filled_net_mean:   -0.0877 bps
per_signal_net:    -0.0038 bps
target:            +2.0000 bps
```

At the current fill rate, this row would need about `46` bps mean net on filled orders to reach `2` bps per signal. The observed filled mean is nonpositive.

### Taker Fallback

Best taker-mean row:

```text
fold/trigger/bin:  expanding_fold3 / tfi_event_active / mid
entries:           72
taker_mean:        4.7331 bps
taker_plus2_mean:  2.7331 bps
failures:          sample, controls, tail, risk
```

This row is diagnostic only. It fails matched controls and promotion gates.

## Reproduce

Core framework:

```powershell
python scripts/ccusdt_v2_research_framework.py --matched-random-iters 200
```

Focused maker proxy:

```powershell
python scripts/ccusdt_v2_fill_realism.py
```

Focused L2 queue fill:

```powershell
python scripts/ccusdt_v2_l2_queue_fill.py
```

All-practical L2 queue fill:

```powershell
python scripts/ccusdt_v2_l2_queue_fill.py --run-tag 20260518_ccusdt_v2_l2_queue_fill_all_practical_v1 --latency-ms 250 --fill-timeout-ms 5000 --order-notional-quote 100 --fee-stress-bps 2 --include-status "research_continue_needs_cost_tail_or_risk_repair,research_only_not_promoted"
```

Taker fallback:

```powershell
python scripts/ccusdt_v2_taker_fallback_audit.py
```

Execution failure decomposition:

```powershell
python scripts/ccusdt_v2_execution_failure_decomposition.py
```

Current completion audit:

```powershell
python scripts/ccusdt_v2_fill_repair_audit.py --l2-queue-run-tag 20260518_ccusdt_v2_l2_queue_fill_all_practical_v1 --run-tag 20260518_ccusdt_v2_fill_repair_audit_all_practical_v1
```

Liquidity envelope audit:

```powershell
python scripts/ccusdt_v2_liquidity_envelope_audit.py --run-tag 20260518_ccusdt_v2_liquidity_envelope_audit_v1
```

Local universe inventory:

```powershell
python scripts/ccusdt_v2_local_universe_inventory.py --run-tag 20260518_ccusdt_v2_local_universe_inventory_v1
python scripts/ccusdt_v2_local_universe_inventory.py --run-tag 20260518_ccusdt_v2_local_universe_inventory_current_v1
```

Universe preflight dry-run:

```powershell
python scripts/bonk_bullish_l2_download.py --dry-run --data-root data\ccusdt_universe\v1 --from-date 2026-04-29 --to-date 2026-05-15 --data-types book_ticker,trades,incremental_book_L2 --symbols "CCUSDT,BTCUSDC,ETHUSDC,SOLUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,SUIUSDC,APTUSDC,ARBUSDC,OPUSDC,BONK1MUSDC,BONK1MUSDT" --run-tag 20260518_ccusdt_v2_universe_preflight_v1 --workers 1
```

Universe size smoke probe:

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260518_ccusdt_v2_universe_size_probe_smoke_v1 --max-jobs 33 --workers 8 --timeout-seconds 15
```

OOS days preflight and no-download size probe:

```powershell
python scripts/bonk_bullish_l2_download.py --dry-run --data-root data\ccusdt_universe\v1 --from-date 2026-05-16 --to-date 2026-05-17 --data-types book_ticker,trades,incremental_book_L2 --symbols "CCUSDT,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,SUIUSDC,WIFUSDC" --run-tag 20260518_ccusdt_v2_oos_days_preflight_v1 --workers 1
python scripts/ccusdt_v2_universe_size_probe.py --manifest-csv date\bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_oos_days_preflight_v1.csv --run-tag 20260518_ccusdt_v2_oos_days_size_probe_v1 --workers 8 --timeout-seconds 30
python scripts/bonk_bullish_l2_download.py --dry-run --data-root data\ccusdt_universe\v1 --from-date 2026-05-17 --to-date 2026-05-17 --data-types book_ticker,trades,incremental_book_L2 --symbols "CCUSDT,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,SUIUSDC,WIFUSDC" --run-tag 20260518_ccusdt_v2_oos_day20260517_preflight_v1 --workers 1
python scripts/ccusdt_v2_universe_size_probe.py --manifest-csv date\bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_oos_day20260517_preflight_v1.csv --run-tag 20260518_ccusdt_v2_oos_day20260517_size_probe_v1 --workers 8 --timeout-seconds 30
python scripts/bonk_bullish_l2_download.py --data-root data\ccusdt_universe\v1 --from-date 2026-05-16 --to-date 2026-05-16 --data-types book_ticker,trades,incremental_book_L2 --symbols "CCUSDT,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,SUIUSDC,WIFUSDC" --run-tag 20260518_ccusdt_v2_oos_day20260516_download_v1 --workers 4 --min-free-gb 2
python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root data\ccusdt_universe\v1 --symbols "DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,SUIUSDC,WIFUSDC" --target-notional-quote 100 --run-tag 20260518_ccusdt_v2_oos_day20260516_envelope_v1
python scripts/ccusdt_v2_liquidity_envelope_audit.py --data-root data\ccusdt\v1 --symbol CCUSDT --run-tag 20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1
python scripts/ccusdt_v2_liquidity_envelope_audit.py --data-root data\ccusdt\v1 --symbol CCUSDT --target-notional-quote 10 --run-tag 20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1
python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root data\ccusdt_universe\v1 --symbols "DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,SUIUSDC,WIFUSDC" --target-notional-quote 10 --run-tag 20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1
python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root data\ccusdt_universe\v1 --symbols "DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,SUIUSDC,WIFUSDC" --target-notional-quote 5 --run-tag 20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1
```

Small-tier full-window size probe:

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260518_ccusdt_v2_universe_size_probe_small_tier_v1 --symbols "SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC" --workers 8 --timeout-seconds 15
```

Small-tier full L2 download:

```powershell
python scripts/bonk_bullish_l2_download.py --data-root data\ccusdt_universe\v1 --from-date 2026-04-29 --to-date 2026-05-15 --data-types book_ticker,trades,incremental_book_L2 --symbols "SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC" --run-tag 20260518_ccusdt_v2_small_tier_download_v1 --workers 4 --min-free-gb 2
```

Remaining-tier size probe:

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1 --symbols "BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT" --workers 8 --timeout-seconds 15
```

Remaining-tier top-of-book/trades download:

```powershell
python scripts/bonk_bullish_l2_download.py --data-root data\ccusdt_universe\v1 --from-date 2026-04-29 --to-date 2026-05-15 --data-types book_ticker,trades --symbols "BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT" --run-tag 20260518_ccusdt_v2_remaining_tob_trades_download_v1 --workers 4 --min-free-gb 10
```

Universe liquidity envelope:

```powershell
python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root data\ccusdt_universe\v1 --symbols "BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT,SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC" --run-tag 20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1
python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root data\ccusdt_universe\v1 --symbols "BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT,SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC" --target-notional-quote 10 --run-tag 20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1
```

BTCUSDC queue-release fast diagnostic:

```powershell
python scripts/ccusdt_v2_queue_release_pivot.py --data-root data\ccusdt_universe\v1 --symbol BTCUSDC --run-tag 20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1 --quantiles "0.99" --horizons-sec "1,5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 50 --candidate-prefilter-quantile 0.95
```

BTCUSDC top-of-book factor smoke:

```powershell
python scripts/ccusdt_v2_tob_factor_framework.py --data-root data\ccusdt_universe\v1 --symbol BTCUSDC --run-tag 20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1 --threshold-quantiles "0.99" --horizons-sec "1,5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 10
```

BTCUSDC top-of-book gross/cost decomposition:

```powershell
python scripts/ccusdt_v2_tob_factor_decomposition.py --source-run-tag 20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1 --run-tag 20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1
```

BTC/ETH/SOL-to-CCUSDT cross-market lead/lag smoke:

```powershell
python scripts/ccusdt_v2_cross_market_lead_lag.py --target-data-root data\ccusdt\v1 --leader-data-root data\ccusdt_universe\v1 --target-symbol CCUSDT --leaders "BTCUSDC,ETHUSDC,SOLUSDC" --run-tag 20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1 --threshold-quantiles "0.99" --horizons-sec "5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 5 --control-selected-cap 500 --control-pool-cap 20000
```

Absorption/replenishment reversal pivot:

```powershell
python scripts/ccusdt_v2_absorption_reversal_pivot.py --data-root data\ccusdt\v1 --symbol CCUSDT --run-tag 20260518_ccusdt_v2_absorption_reversal_pivot_v1 --threshold-quantiles "0.95,0.975,0.99" --horizons-sec "1,5,10" --fee-stress-bps 2 --entry-bucket-sec 10 --matched-random-iters 50 --min-entries 200
```

External venue inventory:

```powershell
python scripts/ccusdt_v2_external_venue_inventory.py --run-tag 20260518_ccusdt_v2_external_venue_inventory_v1
```

Tardis external metadata feasibility:

```powershell
python scripts/ccusdt_v2_tardis_external_metadata_probe.py --run-tag 20260518_ccusdt_v2_tardis_external_metadata_probe_v1
```

External acquisition gate:

```powershell
python scripts/ccusdt_v2_external_acquisition_plan.py --run-tag 20260518_ccusdt_v2_external_acquisition_plan_v1
```

Stop/pivot gate:

```powershell
python scripts/ccusdt_v2_stop_pivot_gate.py --run-tag 20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1
python scripts/ccusdt_v2_goal_completion_audit_universe.py --run-tag 20260518_ccusdt_v2_goal_completion_audit_absorption_reversal_v1
```

## Valid Next Work

Only continue CCUSDT execution research if one of these changes:

- New out-of-sample days materially change fill/economics.
- Real venue fee tier, live/paper order acknowledgements, or measured latency contradict the queue-fill proxy.
- A structurally different entry mechanism is introduced and re-run through the same framework.
- The instrument universe is broadened to a venue/symbol with better queue accessibility and right-tail monetization.
- BTCUSDC continuation introduces a new mechanism; current top-of-book factor tuning alone is blocked by a gross/cost shortfall of about `3.42` bps even in the best row.
- Cross-market continuation uses new accessible external venue CC L2 data, or a materially different leader mechanism, and then passes the same gates; the BTC/ETH/SOL same-venue smoke is not enough and is currently cost-defeated.

Research-only structural pivots are drafted in:

```text
docs/markets/ccusdt/v2-structural-pivot-proposals-20260518.md
docs/markets/ccusdt/pivot_drafts/research_only/
date/ccusdt_v2_pivot_manifest_20260518.json
```

The first queue-release prototype was also tested:

```text
docs/markets/ccusdt/v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_fast_v1.md
```

It remains no-go and does not justify full incremental-L2 build-out unless new design constraints are added.

The first liquidity-envelope audit was also tested:

```text
docs/markets/ccusdt/v2-liquidity-envelope-audit-20260518_ccusdt_v2_liquidity_envelope_audit_v1.md
```

It confirms CCUSDT itself is a poor execution envelope for the current target-notional version of this edge family; future universe work should screen spread/depth/fillability before alpha mining.

The local universe inventory was also tested:

```text
docs/markets/ccusdt/v2-local-universe-inventory-20260518_ccusdt_v2_local_universe_inventory_v1.md
```

It found only one local Bullish core L2-ready symbol: `CCUSDT`. A true universe pivot therefore needs additional symbol data before it can search for a better execution envelope.

The Bullish universe preflight was also tested:

```text
docs/markets/ccusdt/v2-universe-preflight-20260518_ccusdt_v2_universe_preflight_v1.md
```

It is a dry-run only. It found `11` schedulable symbols for the same window and core L2 data families, but no new local files were downloaded.

The Bullish universe size smoke was also tested:

```text
docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_smoke_v1.md
```

It uses metadata/one-byte Range probes only. The first-date sample found `33/33` planned files available and estimated `3.61` GB, dominated by `ETHUSDC` and `BTCUSDC` incremental L2 files. Full sizing or download should be run as a deliberate batch step.

The small-tier full-window size probe was also tested:

```text
docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_small_tier_v1.md
```

It found `255/255` files available for `SUIUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC`, with about `0.40` GB total. This is the current practical pilot tier for a future universe-envelope download.

The first real universe continuation is documented in:

```text
docs/markets/ccusdt/v2-universe-envelope-continuation-20260518.md
```

At `$100` target notional, the expanded local top-of-book universe still has `0` pre-alpha liquidity candidates. At `$10` and `$5`, only `BTCUSDC` passes the spread/depth/activity envelope. Existing V2 framework and L2 queue scripts remain CCUSDT-bound, so a BTC continuation requires either symbol-parameterizing the framework or building a BTC-specific factor panel before any `>2` bps objective can be retested.

The first BTC-specific top-of-book queue-release fast diagnostic was also tested:

```text
docs/markets/ccusdt/v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.md
```

It has `0` promote-gate rows and a best mean of `-1.7210` bps, so BTC small-notional capacity alone does not justify downloading BTC incremental L2.

The first BTC top-of-book factor smoke was also tested:

```text
docs/markets/ccusdt/v2-tob-factor-framework-20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.md
```

It has `0` promote-gate rows and a best mean of `-1.4181` bps, despite a clean sample pass on `obi_follow / 10s`. Economics and stress gates remain false.

Otherwise, the current CCUSDT candidate set should be archived as a well-instrumented no-go, not optimized further.

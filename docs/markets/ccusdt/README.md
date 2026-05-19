# CCUSDT Docs Index

Status: 2026-05-19. CCUSDT is the current Bullish/Tardis CEX L2 pivot after the BONK short-horizon factor work showed instrument-envelope issues. These notes are research diagnostics only, not trading rules or execution recommendations.

## Current First Read

The current V1 TFI branch is path-first. Do not start from aggregate Pareto
tables alone. The central mechanism is fast release followed by possible decay
inside the fixed 60s label horizon.

Read in this order:

1. [V1 current TFI strategy handoff](v1-current-tfi-strategy-handoff-20260518.md)
2. [V1 TFI current research map](v1-tfi-current-research-map-20260519.md)
3. [V1 TFI 2026-05-09 high/chop deep dive](v1-tfi-0509-high-chop-deep-dive-20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.md)
4. [V1 TFI release/decay factor analysis](v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md)
5. [V1 TFI exit walk-forward check](v1-tfi-exit-walkforward-20260518_ccusdt_v1_tfi_exit_walkforward_v1.md)
6. [V1 TFI price-only trailing parameter research](v1-tfi-price-trailing-param-research-20260519_ccusdt_v1_tfi_price_trailing_param_v1.md)
7. [V1 TFI watcher-aware 3x four-quadrant Pareto](v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md)
8. [V1 TFI 3x capacity manager](v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md)
9. [V1 TFI leverage-constrained optimization](v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md)
10. [V1 TFI 2026-05-18 current-strategy OOS check](v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md)
11. [V1 TFI zero-fee four-quadrant sizing Pareto 7x sensitivity](v1-tfi-strategy-sizing-opt-20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.md)

Canonical accident to remember: `entry_row=1615412` reached `+12.5612bps`
MFE in `4.7051s`, then ended near `-27.8923bps` at 60s; with exposure `8`,
that became `-242.4187` PnL units. This is a release/decay and sizing problem,
not merely an entry-quality problem.

Zero fee is the current venue-fee baseline, not a discarded assumption. Robust
strategy work should evaluate:

$$
y_i(c)=R_i(\tau_i^{exit})-C_{fee,i}-c,\qquad C_{fee,i}=0,\quad c>0,
$$

so the stress term reserves room for spread/fill/latency/adverse-selection and
path-decay uncertainty.

## Current And Reference Reports

The current branch is V1 TFI path-first research. V2 items below are retained
as execution/no-go references, not as the active modeling path.

- [V1 current TFI strategy handoff](v1-current-tfi-strategy-handoff-20260518.md): latest active CCUSDT branch; four-cell TFI state sizing plus absolute-strength Pareto optimization. Start here for the current strategy state.
- [V1 TFI current research map](v1-tfi-current-research-map-20260519.md): current path-first map; keeps the `1615412` fast-release/decay accident visible and states the modeling order: entry, release, decay hazard, exit, then sizing.
- [V1 TFI latent state taxonomy](v1-tfi-latent-state-taxonomy-20260518_ccusdt_v1_tfi_latent_state_taxonomy_v1.md): mechanism taxonomy for release, absorption, exhaustion, liquidity vacuum, chop, and weak-bucket overtrade; frames the next pass as regime-state estimation rather than another entry-threshold tweak.
- [V1 TFI latent-state diagnostic panel](v1-tfi-latent-state-panel-20260518_ccusdt_v1_tfi_latent_state_panel_v1.md): entry-level prior-proxy panel and expanding-prior daily score tests for distinguishing `I_d = G_high - G_reduce`, including the `2026-05-09` vs `2026-05-13` contradiction.
- [V1 TFI 2026-05-09 high/chop deep dive](v1-tfi-0509-high-chop-deep-dive-20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.md): isolates the 5/09 high/chop accident group; shows the focus loss is dominated by one oversized `11` row while the more precise matched bucket is `11_r5_frames / short / q70_85 / delta10=s80_100` on that date.
- [V1 TFI release/decay factor analysis](v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md): rebuilds multi-horizon paths for TFI entries and separates release from post-release decay; low opposite depth predicts fast release, while sustained 5-20s signed flow predicts lower decay.
- [V1 TFI exit walk-forward check](v1-tfi-exit-walkforward-20260518_ccusdt_v1_tfi_exit_walkforward_v1.md): frozen-candidate walk-forward validation of fixed timeouts, TP+timeout, flow-confirmed hold, and exposure caps versus locked 60s; flow gate is promising but not promoted without fresh OOS/execution checks.
- [V1 TFI price-only trailing parameter research](v1-tfi-price-trailing-param-research-20260519_ccusdt_v1_tfi_price_trailing_param_v1.md): small walk-forward parameter pass for release-trigger plus trailing stop; best `p80/eta30/act10s` candidate improves `fixed_60s` total and worst day while retaining about `82%` of q90, but remains a mid-price proxy rather than executable guidance.
- [V1 TFI watcher-aware 3x four-quadrant Pareto](v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md): current sizing/Pareto pass using the full `00/10/01/11` universe, path-manager/watch overlays where rebuilt, fixed60 fallback elsewhere, zero venue fee, and a 3x CC/USDT margin cap. Cleaner q70 scaled leader is `gamma00=1.25, gamma10=0.75, gamma01=0, gamma11=0.75`, raw total `6042.8705`, max concurrency `3.375`, scaled100 `5371.4405`.
- [V1 TFI 3x capacity manager](v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md): turns the 3x cap into an online overlap-allocation diagnostic. For the cleaner q70 point, `global_downscale` is `5371.4405` but online FIFO/arrival clip reaches `6038.2000` with only `4` clipped legs; high-gamma rows can reach larger totals but have more skipped/clipped legs and larger single-leg tail.
- [V1 TFI leverage-constrained optimization](v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md): treats the 3x cap as part of the strategy rather than a final scale. It keeps the cleaner q70 core and adds `01_frames_only` as an idle-capacity sleeve. Historical C=0 core-only is `6038.2000`; `idle01_g1_r0` is `6907.5648` with delta `+869.3648`, worst day `+48.3285`, positive days `14/14`, and only `1.90%` core-displacement ratio. 2026-05-18 OOS C=0 improves `415.8276 -> 472.5926`.
- [V1 TFI 2026-05-18 current-strategy OOS check](v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md): applies the locked cleaner q70 3x current strategy to the newly downloaded 2026-05-18 data without optimizing on that day. Cleaner q70 C=0 online FIFO clip has `304` entries, actual total `415.8276` weighted log-bp units, exact simple bp-units `416.6424`, approximate account simple return `4.2459%`, max concurrency `3.0`, clipped legs `3`, skipped legs `1`; under pressure `C=1` total is `257.7026` and `C=2` total is `99.5776`.
- [V1 TFI R5+Q factor decomposition](v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md): plain factor decomposition of `R5/Delta/E/Z`, frames quantile `Q`, cell/direction interactions, and worst-day composition-vs-payoff attribution.
- [V1 TFI entry-level estimation](v1-tfi-entry-estimation-20260518_ccusdt_v1_tfi_entry_estimation_v1.md): strict as-of entry estimates for `E[r|x]`, `P(r>2bps|x)`, right-tail dependence, `CVaR`, quality classes, and daily quality attribution.
- [V1 TFI interpretable grid Pareto](v1-tfi-interpretable-grid-pareto-20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.md): `16960`-candidate interpretable grid over four-cell gamma, absolute-strength gate/ramp, and recent-loss suppressor; key Pareto leader uses `closed10_score_abs >= Q30_train`.
- [V1 TFI zero-fee four-quadrant sizing Pareto 7x sensitivity](v1-tfi-strategy-sizing-opt-20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.md): earlier C=0 rerun for the old `00/10/01/11` sizing framework, with `gamma00` allowed and a 60s-concurrency 7x diagnostic. Treat this as sensitivity unless CC/USDT actually has a 7x venue cap; the current watcher-aware branch uses 3x.
- [V1 TFI worst-day frontier](v1-tfi-worst-day-frontier-20260518_ccusdt_v1_tfi_worst_day_frontier_v1.md): mathematical decomposition of `R5` into `Delta/E/Z` and prior-only worst-day gating.
- [V1 TFI strategy sizing opt v2](v1-tfi-strategy-sizing-opt-20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.md): four-cell sizing split for `00/10/01/11`; confirms `01` stale-only should not be silently folded into base.
- [V1 classic LOB stylized factors](v1-lob-stylized-factors-20260518_ccusdt_v1_lob_stylized_factors_v1.md): independent BTC-style LOB factor pass on CCUSDT; static book shape is mostly state/regime material, while dynamic trade-flow/MLOFI remains the strongest diagnostic family.
- [V1 TFI core quantity estimation](v1-tfi-core-quantity-estimation-20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.md): first-principles estimates of pressure stock `X`, absorption threshold `Theta`, release ratio `U`, absorption/exhaustion scores, and prior conversion `lambda`.
- [V2 current execution no-go handoff](v2-current-execution-no-go-handoff.md): latest consolidated status, hard evidence, reproduce commands, and valid next-work conditions.
- [V2 structural pivot proposals](v2-structural-pivot-proposals-20260518.md): research-only structurally different pivots after current candidates hit execution no-go.
- [V2 queue-release pivot prototype](v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_fast_v1.md): lightweight book-ticker test of the direct queue-release continuation pivot.
- [V2 liquidity envelope audit](v2-liquidity-envelope-audit-20260518_ccusdt_v2_liquidity_envelope_audit_v1.md): execution-first screen of CCUSDT spread, top-of-book depth support, trade arrival, practical maker fill, and taker fallback evidence.
- [V2 local universe inventory](v2-local-universe-inventory-20260518_ccusdt_v2_local_universe_inventory_v1.md): local Bullish L2 path inventory for the liquidity-envelope universe pivot.
- [V2 current local universe inventory](v2-local-universe-inventory-20260518_ccusdt_v2_local_universe_inventory_current_v1.md): current local Bullish inventory; `6` core-L2-ready symbols, but execution envelope still fails.
- [V2 Bullish universe preflight](v2-universe-preflight-20260518_ccusdt_v2_universe_preflight_v1.md): dry-run Tardis metadata preflight for the next multi-symbol Bullish L2 acquisition step.
- [V2 Bullish universe size probe](v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_smoke_v1.md): bounded metadata/Range smoke probe for first-day universe download sizing.
- [V2 OOS days size probe](v2-universe-size-probe-20260518_ccusdt_v2_oos_days_size_probe_v1.md): no-download availability probe for `2026-05-16..2026-05-17`; `2026-05-16` was available and then downloaded, `2026-05-17` is not yet available.
- [V2 OOS day 2026-05-17 availability probe](v2-universe-size-probe-20260518_ccusdt_v2_oos_day20260517_size_probe_v1.md): standalone no-download follow-up; `0/18` core L2 files available, so no new OOS unlock.
- [V2 OOS day 2026-05-16 envelope](v2-universe-liquidity-envelope-20260518_ccusdt_v2_oos_day20260516_envelope_v1.md): 18-day small-tier envelope after adding the available OOS day; still `0` pre-alpha candidates.
- [V2 CCUSDT OOS liquidity envelope](v2-liquidity-envelope-audit-20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.md): canonical 18-day CCUSDT envelope after adding 2026-05-16; still `liquidity_envelope_no_go`.
- [V2 OOS target-notional sensitivity](v2-universe-liquidity-envelope-20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.md): smaller-notional follow-up; CCUSDT `$10` and small-tier `$10/$5` still produce no usable pre-alpha candidate.
- [V2 Bullish universe size probe small tier](v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_small_tier_v1.md): full-window size probe for the small candidate tier before pilot download.
- [V2 universe envelope continuation](v2-universe-envelope-continuation-20260518.md): post-download universe screen; `$100` remains no-go and only `BTCUSDC` passes pre-alpha capacity at `$10`/`$5`.
- [V2 Bullish universe size probe remaining tier](v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1.md): full-window size probe for BTC/ETH/SOL/BONK remaining-tier data.
- [V2 universe liquidity envelope full top-of-book universe](v2-universe-liquidity-envelope-20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.md): 10-symbol top-of-book/trades envelope at the original `$100` target notional.
- [V2 BTCUSDC queue-release fast diagnostic](v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.md): BTC small-notional structural prefilter; `0` promote-gate rows.
- [V2 BTCUSDC top-of-book factor smoke](v2-tob-factor-framework-20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.md): 1s BTC top-of-book/trade factor scan; `0` promote-gate rows.
- [V2 BTCUSDC top-of-book gross/cost decomposition](v2-tob-factor-decomposition-20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.md): decomposes BTC TOB factor rows into gross, cost, net, and `+2` bps shortfall; still `0` promote-gate rows.
- [V2 BTC/ETH/SOL-to-CCUSDT cross-market lead/lag smoke](v2-cross-market-lead-lag-20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.md): structural lead/lag pivot using large-symbol leaders; `0` promote-gate rows.
- [V2 absorption/replenishment reversal pivot](v2-absorption-reversal-pivot-20260518_ccusdt_v2_absorption_reversal_pivot_v1.md): structurally new failed-breakout/replenishment entry diagnostic; `0/72` promote rows, best net mean still negative after cost.
- [V2 external venue inventory](v2-external-venue-inventory-20260518_ccusdt_v2_external_venue_inventory_v1.md): local data inventory for true cross-venue lead/lag; external CCUSDT L2 is data-blocked.
- [V2 Tardis external metadata probe](v2-tardis-external-metadata-probe-20260518_ccusdt_v2_tardis_external_metadata_probe_v1.md): metadata-only access feasibility check for external CC orderbook venues; external metadata exists, but accessible external CC L2 is `0`.
- [V2 external acquisition plan](v2-external-acquisition-plan-20260518_ccusdt_v2_external_acquisition_plan_v1.md): no-download manifest gate for external CC L2 candidates; `255` rows are blocked by access and `planned_rows=0`.
- [V2 stop/pivot gate after absorption reversal](v2-stop-pivot-gate-20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.md): machine-readable stop gate; `14` critical gates fail and the current CCUSDT path requires new data/access/instrument/mechanism before continuing.
- [V2 goal completion audit after absorption reversal](v2-goal-completion-audit-20260518_ccusdt_v2_goal_completion_audit_absorption_reversal_v1.md): prompt-to-artifact audit including universe, OOS, BTC diagnostics, gross/cost decomposition, cross-market smoke, absorption reversal, local external-venue inventory, Tardis metadata feasibility, external acquisition gate, and stop/pivot gate; still `not_achieved`.
- [Executable research framework v2](v2-executable-research-framework.md): strict walk-forward, cost-pressure, matched-control, and mathematical-decomposition framework for turning the observed CCUSDT L2 edge into entry-quality, exit-shape, and risk-control research models.
- [V2 framework run](v2-framework-run-20260518_ccusdt_v2_framework_v1.md): first executable-framework scorecard with quote-transition labels, residual controls, matched controls, entry-quality bins, exit-shape, and risk-control diagnostics.
- [V2 fill realism](v2-fill-realism-20260518_ccusdt_v2_fill_realism_v1.md): top-of-book maker fill proxy over local Bullish `book_ticker` and `trades` for the v2 repair candidates.
- [V2 L2 queue fill](v2-l2-queue-fill-20260518_ccusdt_v2_l2_queue_fill_v1.md): incremental-book same-price queue-pressure proxy for the v2 repair candidates.
- [V2 all-practical L2 queue fill](v2-l2-queue-fill-20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.md): practical scenario across all `45` framework scorecard bins and `6447` validation entries.
- [V2 goal completion audit](v2-goal-completion-audit-20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.md): prompt-to-artifact audit plus all-practical fill-aware post-hoc repair scan.
- [V2 taker fallback audit](v2-taker-fallback-audit-20260518_ccusdt_v2_taker_fallback_audit_v1.md): crossing/taker-style cost audit after maker queue-fill no-go.
- [V2 execution failure decomposition](v2-execution-failure-decomposition-20260518_ccusdt_v2_execution_failure_decomp_v1.md): mathematical decomposition of the maker/taker execution shortfall versus the `2` bps target.
- [CCUSDT replay workbench](v1-replay-workbench.md): default market in the generic local Rust API + Next.js replay UI.
- [Fixed event-orderbook factors v3](v1-fixed-event-orderbook-factors-v3.md): corrected snapshot-rebuild factor surface with past-only trade alignment, fold-valid controls, control-filtered path table, and `dlog_mid` Spearman diagnostics.
- [Factor method sweep](v1-factor-method-sweep.md): broad snapshot-frame diagnostic sweep across event/time targets, single-factor IC/AUC/MI, stability, negative controls, and linear/tree/LightGBM models.
- [Strategy research overlay](v1-strategy-research.md): toy replay conversion of factor opportunities into walk-forward rules with cost stress, stale/event filters, and controls.
- [Signal path math](v1-signal-path-math.md): trigger taxonomy, cost-threshold crossing, entry refinement, stop-only/delayed-stop diagnostics, and targeted `8/5`, `12/5`, `12/8` barrier increment decomposition.
- [Tail and stop deep dive](v1-tail-stop-deep-dive.md): per-entry rebuild of core TFI entries, top-winner removal, cost stress, matched random, adverse-excursion recovery, and stop-only path diagnostics.

## Superseded References

- [CCUSDT archive](archive/README.md): non-current diagnostics and superseded reports moved out of the main read path.
- [Fixed event-orderbook factors v2](archive/superseded/v1-fixed-event-orderbook-factors-v2.md): superseded transition pass; go to v3 for the current corrected panel.
- [Fixed event-orderbook factors v1](archive/superseded/v1-fixed-event-orderbook-factors.md): superseded first pass; go to v3 for the current corrected panel.
- [Zero-fee interpretable-grid diagnostics](archive/diagnostics/v1-tfi-interpretable-grid-pareto-20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.md): archived only because this is not the current four-quadrant branch; zero-fee itself remains the current venue-fee baseline.

## Current Data Window

Local Tardis Bullish raw coverage for `CCUSDT`:

- `incremental_book_L2`: complete for `2026-04-29..2026-05-18`
- `book_ticker`: complete for `2026-04-29..2026-05-18`
- `trades`: complete for `2026-04-29..2026-05-18`
- `book_snapshot_25`: complete for `2026-04-29..2026-05-15`

The fixed-factor panel is stored under:

```text
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260517_ccusdt_fixed_factors_v1
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260517_ccusdt_fixed_factors_v2
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260517_ccusdt_fixed_factors_v3
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260518_ccusdt_fixed_factors_oos_day20260516_v1
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260518_ccusdt_fixed_factors_oos_day20260517_v1
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260519_ccusdt_fixed_factors_oos_day20260518_v1
```

Primary output tables are:

```text
date/ccusdt_v1_fixed_event_factors_quality_20260517_ccusdt_fixed_factors_v3.csv
date/ccusdt_v1_fixed_event_factors_factor_params_20260517_ccusdt_fixed_factors_v3.csv
date/ccusdt_v1_fixed_event_factors_path_ranking_20260517_ccusdt_fixed_factors_v3.csv
date/ccusdt_v1_fixed_event_factors_stability_20260517_ccusdt_fixed_factors_v3.csv
date/ccusdt_v1_fixed_event_factors_negative_controls_20260517_ccusdt_fixed_factors_v3.csv
date/ccusdt_v1_fixed_event_factors_spearman_20260517_ccusdt_fixed_factors_v3.csv
date/ccusdt_v1_factor_method_sweep_single_factor_20260517_ccusdt_method_sweep_v1.csv
date/ccusdt_v1_factor_method_sweep_stability_20260517_ccusdt_method_sweep_v1.csv
date/ccusdt_v1_factor_method_sweep_negative_controls_20260517_ccusdt_method_sweep_v1.csv
date/ccusdt_v1_factor_method_sweep_models_20260517_ccusdt_method_sweep_v1.csv
date/ccusdt_v1_strategy_research_candidates_20260517_ccusdt_strategy_research_v1.csv
date/ccusdt_v1_strategy_research_controls_20260517_ccusdt_strategy_research_v1.csv
date/ccusdt_v1_strategy_research_summary_20260517_ccusdt_strategy_research_v1.json
date/ccusdt_v1_signal_path_math_fixed_20260517_ccusdt_signal_path_math_v1.csv
date/ccusdt_v1_signal_path_math_barrier_20260517_ccusdt_signal_path_math_v1.csv
date/ccusdt_v1_signal_path_math_entry_refinement_20260517_ccusdt_signal_path_math_v1.csv
date/ccusdt_v1_signal_path_math_stop_policy_20260517_ccusdt_signal_path_math_v1.csv
date/ccusdt_v1_signal_path_math_summary_20260517_ccusdt_signal_path_math_v1.json
date/ccusdt_v1_tail_stop_deep_dive_summary_20260517_ccusdt_tail_stop_deep_dive_v1.csv
date/ccusdt_v1_tail_stop_deep_dive_stop_summary_20260517_ccusdt_tail_stop_deep_dive_v1.csv
date/ccusdt_v1_tail_stop_deep_dive_cost_stress_20260517_ccusdt_tail_stop_deep_dive_v1.csv
date/ccusdt_v1_tail_stop_deep_dive_topk_removal_20260517_ccusdt_tail_stop_deep_dive_v1.csv
date/ccusdt_v1_tail_stop_deep_dive_matched_random_20260517_ccusdt_tail_stop_deep_dive_v1.csv
date/ccusdt_v2_quote_transition_labels_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_residual_controls_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_matched_controls_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_entry_quality_bins_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_exit_shape_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_risk_control_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_summary_20260518_ccusdt_v2_framework_v1.json
date/ccusdt_v2_fill_realism_events_20260518_ccusdt_v2_fill_realism_v1.csv
date/ccusdt_v2_fill_realism_summary_20260518_ccusdt_v2_fill_realism_v1.csv
date/ccusdt_v2_fill_realism_scorecard_20260518_ccusdt_v2_fill_realism_v1.csv
date/ccusdt_v2_fill_realism_summary_20260518_ccusdt_v2_fill_realism_v1.json
date/ccusdt_v2_l2_queue_fill_events_20260518_ccusdt_v2_l2_queue_fill_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_v1.csv
date/ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_v1.json
date/ccusdt_v2_l2_queue_fill_events_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv
date/ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.json
date/ccusdt_v2_fill_repair_filters_20260518_ccusdt_v2_fill_repair_audit_v1.csv
date/ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_v1.csv
date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_fill_repair_audit_v1.json
date/ccusdt_v2_fill_repair_filters_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv
date/ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv
date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.json
date/ccusdt_v2_taker_fallback_summary_20260518_ccusdt_v2_taker_fallback_audit_v1.csv
date/ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv
date/ccusdt_v2_taker_fallback_summary_20260518_ccusdt_v2_taker_fallback_audit_v1.json
date/ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.csv
date/ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.json
date/ccusdt_v2_queue_release_events_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_controls_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_fast_v1.csv
date/ccusdt_v2_queue_release_summary_20260518_ccusdt_v2_queue_release_pivot_fast_v1.json
date/ccusdt_v2_absorption_reversal_panel_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_events_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_controls_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv
date/ccusdt_v2_absorption_reversal_summary_20260518_ccusdt_v2_absorption_reversal_pivot_v1.json
date/ccusdt_v2_liquidity_envelope_daily_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv
date/ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv
date/ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_liquidity_envelope_audit_v1.json
date/ccusdt_v2_local_bullish_universe_inventory_20260518_ccusdt_v2_local_universe_inventory_v1.csv
date/ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_v1.json
date/ccusdt_v2_local_bullish_universe_inventory_20260518_ccusdt_v2_local_universe_inventory_current_v1.csv
date/ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_current_v1.json
date/ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.csv
date/ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.json
date/ccusdt_v2_external_acquisition_manifest_20260518_ccusdt_v2_external_acquisition_plan_v1.csv
date/ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_v1.csv
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_v1.json
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_oos_day20260517_probe_v1.csv
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_oos_day20260517_probe_v1.json
date/ccusdt_v2_goal_completion_checklist_20260518_ccusdt_v2_goal_completion_audit_oos_day20260517_probe_v1.csv
date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_oos_day20260517_probe_v1.json
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.csv
date/ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.json
date/ccusdt_v2_goal_completion_checklist_20260518_ccusdt_v2_goal_completion_audit_absorption_reversal_v1.csv
date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_absorption_reversal_v1.json
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_universe_preflight_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_universe_preflight_v1.csv
date/ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_universe_size_probe_smoke_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_smoke_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_smoke_v1.json
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_days_preflight_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_oos_days_preflight_v1.csv
date/ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_oos_days_size_probe_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260517_preflight_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_oos_day20260517_preflight_v1.csv
date/ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.json
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_oos_day20260516_download_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_envelope_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_envelope_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json
date/ccusdt_v2_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.csv
date/ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.csv
date/ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json
date/ccusdt_v2_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.csv
date/ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.csv
date/ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.json
date/ccusdt_v2_universe_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.json
date/ccusdt_v2_universe_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.json
date/ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.csv
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.json
```

## Current Read

V3 fixes the continuous-snapshot replay bug from V1 and the future-trade/control issues found after V2. The method sweep shows the strongest short-horizon diagnostics are trade-flow and MLOFI/orderbook-state rows, but past-return leakage probes are often stronger than forward tests.

The strategy overlay promotes `trade_flow_imbalance` as the only primary strategy-research thread, with MLOFI/book-pressure as secondary confirmation material. The signal path math pass shows the main 60s TFI rows are cost-threshold/right-tail rows: large-sample rows can clear toy maker-light cost `C`, but only with thin mean, negative median, and heavy top-tail dependence. `tfi_short_stale25` is the cleanest new state-conditioned row in fold3 and may be a useful sparse quote-release state, but it is not yet stable across folds: fold3 has `131` entries with `5.1872` bps net mean and `2.5130` bps median, while fold2 has only `0.1424` bps net mean and negative median, and fold1 has only `27` entries.

The tail/stop deep dive sharpens this read. Large-sample fold3 flat TFI is not one-trade luck: `tfi_follow_flat` remains positive after removing the largest `10` net winners, and only flips after roughly `57`; `tfi_short_flat` flips after roughly `36`. But the top `10%` net winners still exceed total net profit, so this remains a right-tail cluster edge, not a stable central-tendency edge. `tfi_short_stale25` fold3 survives the largest `10` winners by only `0.1255` bps and flips after `14`; fold2 stale25 flips after the single largest winner.

Current decision: do not promote and do not keep tuning hard TP/SL grids. Continue only with a narrow quote-transition/residualized-control pass that tries to prove a large-sample right-tail family can still cover stricter costs, while carrying `stale25` as a separate sparse-state hypothesis. Stop-only should be treated as adverse-excursion/recovery diagnostics, not as a rule search. If the edge remains fold3-specific, small-sample, or dependent on top-tail concentration above roughly `85%`, stop or pivot rather than strategy-optimize.

The v2 framework makes that next pass explicit: it requires fold-valid entry-quality, exit-shape, and risk-control models, matched controls by stale/activity/spread/recent-return state, residual quote-transition labels, and true after-cost scorecards before any executable status can be considered.

The first v2 framework run generated `45` scorecard rows from `6447` validation entries, with matched and residual controls scored at the `entry_quality_bin` level. No row was promoted. Four rows remain `research_continue`: fold3 `tfi_follow_flat/high`, `tfi_long_flat/high`, `tfi_short_flat/high`, and `tfi_short_stale25/low`. They each pass matched-control and residual checks, but fail one or more hard gates such as sample size, `>2` bps economics, `+2` bps stress, tail concentration, risk control, and execution realism. The best economic row was `expanding_fold3 / tfi_event_active / mid` with `4.7892` bps realistic-proxy net mean and `2.7892` bps after an extra `+2` bps hurdle, but it failed bin-level matched control, sample size, tail concentration, and execution realism. Current status remains research-continue for targeted repair, execution-no-go.

The first fill-realism probe added a stricter execution read. It tested `1204` focused entries across `0/250/1000ms` latency, `1s/5s/10s` fill windows, `50/100/250` quote notional, and `0/2/5` bps fee stress. In the practical scorecard scenario (`250ms`, `5s`, `100` quote notional, `2` bps fee stress), all five focused rows were `fill_realism_no_go`: fill rates were only about `3.08%..8.33%`, filled-net means were negative, and per-signal net was negative. Some zero-latency one-second scenarios show positive filled-net means, but fill rates around `0.2%..1%` are too sparse to count as stable capture.

The incremental-L2 queue-pressure pass reached the same execution decision with a stricter queue model. It used same-price `incremental_book_L2` decreases to advance queue ahead, but still required opposite-side trades at/through the posted price to fill the simulated order. In the practical scenario, all five focused rows were `l2_queue_fill_no_go`: fill rates remained about `3.08%..8.33%`, filled-net means ranged from about `-0.09` to `-23.35` bps, and per-signal net stayed negative. This reinforces execution-no-go; queue pressure exists, but not enough to convert the observed information edge into stable after-cost capture.

The all-practical L2 queue pass removes the focused-candidate coverage caveat. It tested the practical scenario across all `45` framework scorecard bins and all `6447` validation entries. Every bin was `l2_queue_fill_no_go`; the best per-signal result was still negative at about `-0.0038` bps (`expanding_fold3 / tfi_short_flat / high`).

The goal completion audit confirms the active objective is not achieved. The all-practical post-hoc fill-aware repair scan tested `3741` simple entry-time filters; `0` passed all execution gates. The best diagnostic filters lifted filled-sample means for `tfi_short_flat/high` and `tfi_follow_flat/high`, but fill rates stayed around `4%..6%` and the best per-signal net was only about `0.59` bps. This is useful as a failure decomposition, not a promotable rule.

The taker fallback audit closes the obvious crossing-cost branch after maker fill no-go. It scored all `45` framework bins with `fixed_net_taker_bps` and inherited sample/control/residual/tail/risk gates. All `45` rows were `taker_fallback_no_go`. The best mean row, `expanding_fold3 / tfi_event_active / mid`, had `4.73` bps taker mean and `2.73` bps after an extra `+2` bps stress, but failed sample size, matched controls, tail concentration, and risk gates.

The execution failure decomposition makes the no-go arithmetic explicit. For maker execution, `per_signal_net_bps = fill_rate * E[net_bps | filled]`; the best practical maker row is only `-0.0038` bps per signal versus the `2` bps target. At its current `4.35%` fill rate, it would need about `46` bps mean net on filled orders to reach target, while its observed filled mean is slightly negative. Taker has no promote-gate rows.

The first structural pivot prototype also failed. The queue-release continuation prototype tested top-of-book amount depletion at unchanged best price using `book_ticker`, with walk-forward thresholds, `5/10s` horizons, taker-style cost, and matched random controls. It produced `24` scorecard rows and `0` promote-gate rows; the best mean row was still negative at about `-1.76` bps.

The liquidity-envelope audit makes the universe-pivot rationale explicit. On the local `2026-04-29..2026-05-15` CCUSDT window, the median daily median spread is about `2.01` bps, the median daily 5th-percentile top-of-book depth is only about `0.095` quote, and `0/17` days support the `$100` top-depth gate at the required row rate. Combined with the all-practical L2 result (`45/45` no-go rows, best maker fill rate `11.76%`, best per-signal net `-0.0038` bps) and taker fallback (`0` promote rows), CCUSDT itself fails the execution-first envelope for this edge family.

The local universe inventory shows that this handoff currently has only one Bullish core L2-ready local symbol: `ccusdt / CCUSDT`, with `17` common `book_ticker`, `trades`, and `incremental_book_L2` dates. Local universe screening therefore cannot yet prove a better instrument; it requires additional multi-symbol Bullish L2 data before the `liquidity_envelope_universe` pivot can become a real selection pass.

The Bullish universe preflight is the next data-acquisition bridge. In dry-run mode, Tardis metadata accepted `11` scheduled symbols for the CCUSDT V2 window and data families: `CCUSDT`, `BTCUSDC`, `ETHUSDC`, `SOLUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, `WIFUSDC`, `SUIUSDC`, `BONK1MUSDC`, and `BONK1MUSDT`. `APTUSDC`, `ARBUSDC`, and `OPUSDC` were missing from Bullish metadata.

The universe size probe adds a bounded download-cost read. A first-date smoke probe over the `11` planned symbols and `3` core L2 data families found `33/33` files available and estimated `3.61` GB for that one date. This confirms the full `17`-day basket should be staged deliberately rather than downloaded blindly.

The OOS-days probe checks whether the `new_out_of_sample_days` unlock is available without downloading dataset bodies. For `CCUSDT`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, `SUIUSDC`, and `WIFUSDC`, `2026-05-16` is available across `book_ticker`, `trades`, and `incremental_book_L2`; `2026-05-17` was unavailable in the combined probe and remains unavailable in the standalone follow-up (`0/18` files available). The available `2026-05-16` day was downloaded (`12` non-empty files and `6` empty files), then the small-tier envelope was rerun over the 18-day window. It still found `0` pre-alpha candidates. The same OOS CCUSDT files were copied into the canonical `data/ccusdt/v1` tree and the CCUSDT envelope was rerun over 18 days; it remains `liquidity_envelope_no_go`. Smaller notional does not rescue the branch: CCUSDT `$10` remains no-go, and the OOS small-tier set has no candidates at `$10` or `$5`. This OOS unlock does not advance to alpha modeling.

The small-tier full-window size probe found a practical pilot set: `SUIUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC` across all `17` dates and `3` core L2 data families total only about `0.40` GB by Range metadata. `SUIUSDC` contributes about `0.354` GB and `DOGEUSDC` about `0.049` GB; `PEPE/SHIB/WIF` are metadata-available but near-empty by byte size and need row validation if downloaded.

The first expanded-universe continuation is also no-go. The current local Bullish inventory is multi-symbol core-L2 ready with `6` symbols: `CCUSDT`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, `SUIUSDC`, and `WIFUSDC`. At the original `$100` notional, the 10-symbol Bullish top-of-book/trades envelope has `0` pre-alpha candidates. At `$10` and `$5`, only `BTCUSDC` passes the first capacity screen, but the BTC queue-release diagnostic has `0` promote rows and the BTC top-of-book factor smoke has `0` promote rows. The follow-up gross/cost decomposition makes the arithmetic explicit: the best BTC row has about `0.5944` bps gross mean versus about `4.0125` bps required to clear fee stress plus the `+2` bps target, leaving about `-3.4181` bps gross shortfall.

The first BTC/ETH/SOL-to-CCUSDT cross-market smoke also fails. It tests the remaining structural pivot without new downloads by treating large-symbol top-of-book/trade features as external leaders for CCUSDT. The best row has `0.9865` bps gross mean, `3.9243` bps cost mean, and `-2.9377` bps net mean, with `0/90` promote-gate rows. This suggests leader information may move CCUSDT directionally, but not enough to survive the current CCUSDT execution envelope.

The absorption/replenishment reversal pivot tests a structurally new failed-breakout mechanism on the canonical CCUSDT window plus the available `2026-05-16` OOS fold. It builds a per-second top-of-book/trade panel, fits aggressive-flow thresholds on train folds only, then selects large buy/sell pressure that fails to move price and is met by visible same-side replenishment. It produced `72` scorecard rows and `0` promote rows. The best gross row had about `3.9939` bps, but its net mean was still `-0.3104` bps after cost; OOS rows were small-sample and negative. This closes the obvious absorption/reversal structural mechanism unless new data, execution evidence, or a different instrument changes the envelope.

The external-venue inventory closes the obvious local-data question. CCUSDT L2 is available locally only on `bullish`. The only non-Bullish venue files found are `binance_spot_klines` from the BONK research tree, and those are `1m` klines rather than synchronized CCUSDT/CC-related L2. The follow-up Tardis metadata probe shows that external CC orderbook symbols exist on `binance-futures`, `bybit`, `kucoin`, and `okex`, but the current API access has `0` accessible external CC L2 venues. The external acquisition plan materializes this into `255` no-download manifest rows, all `blocked_access` with `planned_rows=0`. The refreshed stop/pivot gate after the absorption/reversal structural test still blocks continued tuning of the current CCUSDT path unless new external data/access, new out-of-sample days, a better execution-envelope instrument, or a structurally new mechanism unlocks the framework. A true cross-venue lead/lag continuation therefore requires new external venue access/data before it can be tested under the same gates.

## Go / No-Go Criteria

Go for the next research stage only if quote-transition or residual targets confirm true post-signal quote movement, the signal survives recent-return and matched-random controls, stale/event-active regimes are separated, cost `C` remains positive under maker-light and reasonable stress, and stop-only improves left tail without killing cost winners.

No-go for execution if results depend on midpoint labels, stale snapshot blending, small fold3-only states, top-tail concentration, weak controls, or optimistic cost assumptions. Current status is research-continue, execution-no-go.

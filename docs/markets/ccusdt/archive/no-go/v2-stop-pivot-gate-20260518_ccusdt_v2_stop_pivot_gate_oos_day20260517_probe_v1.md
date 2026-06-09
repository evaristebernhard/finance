# CCUSDT V2 Stop/Pivot Gate

Status: `20260518_ccusdt_v2_stop_pivot_gate_oos_day20260517_probe_v1`.

Guardrail: `research_only_stop_pivot_gate_no_execution_recommendation_no_alpha_claim`.

## Decision

Decision: `stop_current_ccusdt_path_pivot_or_new_data_required`.

The current CCUSDT execution path should not continue by tuning the same candidate family. Resume only if one of the explicit unlock conditions is satisfied and then rerun the same walk-forward, cost, control, tail, and execution gates.

## Gate Checklist

| gate | evidence | observed | pass_condition | status | unlock_condition |
| --- | --- | --- | --- | --- | --- |
| current_framework_promotion | ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv | promoted_rows=0 best_net_realistic_mean_bps=4.7892 | promoted_rows > 0 and promoted rows clear real-cost +2 bps gates | fail | introduce a new mechanism or new out-of-sample data, then rerun the V2 framework. |
| practical_maker_execution | ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv | non_no_go_rows=0 best_per_signal_net_bps=-0.0038 | at least one practical L2 queue-fill row is non-no-go and exceeds +2 bps per signal | fail | do not retune maker assumptions; require measured latency/fee/fill evidence or a new entry mechanism. |
| fill_aware_repair | ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv | execution_pass_rows=0 | at least one pre-declared entry-quality repair passes execution gates | fail | do not add more post-hoc filters on the same candidate family. |
| taker_fallback | ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv | taker_promote_rows=0 best_taker_mean_bps=4.7331 | at least one taker row passes sample, controls, tail, risk, and cost gates | fail | do not switch to crossing unless fee/spread assumptions or signal mechanism materially change. |
| ccusdt_liquidity_envelope | ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv | status=liquidity_envelope_no_go | CCUSDT passes target-notional spread, depth, activity, and execution envelope | fail | continue only with a smaller validated notional, a different instrument, or new liquidity regime evidence. |
| bullish_universe_envelope | ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.csv | target100_candidates=0 | at least one local universe symbol passes the $100 pre-alpha execution envelope | fail | screen a broader venue/symbol universe before any alpha search. |
| btcusdc_structural_followup | ccusdt_v2_queue_release_scorecard_*; ccusdt_v2_tob_factor_scorecard_* | btc_queue_promote=0 btc_tob_promote=0 | BTCUSDC small-notional diagnostics promote at least one structurally different row | fail | do not expand BTC incremental L2 until a top-of-book mechanism clears gates. |
| same_venue_cross_market | ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv | cross_market_promote_rows=0 best_net_mean_bps=-2.9377 | at least one leader row survives controls and real-cost +2 bps gates | fail | same-venue leaders are not enough; require external venue data or a materially stronger leader mechanism. |
| external_cc_l2_acquisition | ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json | planned_rows=0 blocked_access_rows=255 | planned_rows > 0 so size probe/download can proceed | fail | obtain Tardis access for at least one external CC orderbook venue, then run size probe before download. |
| new_oos_days_unlock_state | ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json | available_rows=18 missing_rows=18 total_gb=0.2436 | new OOS files are downloaded, rebuilt, and pass the same V2 gates | unlock_followed_up_failed_envelope | do not proceed to alpha modeling from the OOS day unless the envelope produces pre-alpha candidates. |
| oos_day20260517_availability | ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.json | planned=18 available=0 missing=18 errors=0 total_gb=0.0000 | new OOS day has accessible non-empty core L2 files before download/envelope follow-up | not_available | wait for the day to become available, or test a different new day/instrument through the same no-download gate. |
| oos_day20260516_envelope | bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json | download_counts={'downloaded': 12, 'empty': 6} pre_alpha_candidates= | OOS day produces at least one pre-alpha liquidity candidate before alpha modeling | fail | requires a new OOS/instrument envelope pass before framework modeling. |
| ccusdt_oos_day20260516_liquidity_envelope | ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json | status=liquidity_envelope_no_go | canonical CCUSDT OOS-expanded window passes the execution envelope | fail | requires CCUSDT or a replacement instrument to pass execution envelope before alpha modeling. |
| oos_target_notional_sensitivity | ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.json | ccusdt_target10=liquidity_envelope_no_go small_target10= small_target5= | smaller target notional produces a pre-alpha candidate before modeling | fail | requires smaller-notional envelope pass before alpha modeling. |
| active_goal_completion | ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_universe_continuation_v1.json | completion_status=not_achieved | completion_status == achieved | fail | do not mark the active goal complete until the prompt-to-artifact audit passes. |

## Blocked Research Modes

- `tp_sl_grid_retuning_on_current_candidates`
- `post_hoc_fill_filters_on_same_validation_entries`
- `maker_taker_assumption_switching_without_new_execution_evidence`
- `same_venue_cross_market_tuning_without_external_data_or_new_mechanism`
- `alpha_search_before_execution_envelope_passes`

## Allowed Unlocks

- `new_accessible_external_cc_l2_data_then_size_probe_download_cross_venue_framework`
- `new_out_of_sample_or_new_instrument_day_that_passes_pre_alpha_envelope_then_full_v2_framework_and_execution_audit`
- `new_instrument_or_venue_that_passes_execution_envelope_before_alpha_search`
- `structurally_new_entry_mechanism_then_same_walk_forward_cost_control_tail_gates`

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_oos_day20260517_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_oos_day20260517_probe_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_stop_pivot_gate.py --run-tag 20260518_ccusdt_v2_stop_pivot_gate_oos_day20260517_probe_v1
```

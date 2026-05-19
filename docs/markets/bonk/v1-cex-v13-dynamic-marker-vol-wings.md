# BONK V13 Dynamic Marker / Vol Wings

- generated_at: `2026-05-15T10:26:39Z`
- run_tag: `20260514_bonk_v10_stage1_pilot`
- guardrail: `research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim`
- stance: research-only; no trading advice, no execution recommendation, no alpha claim.

## Inputs

- V10c panel files: `86`
- V10c panel rows read: `1945574`
- usable rows: `1945574`
- folds from V10 filter params: `6`
- validation watch signals: `5279`
- features: `mlofi_norm_l10,mlofi_norm_l5,queue_imbalance_25,trade_arrival_alignment,liquidity_shock_score`

## Primary Status

- primary_status: `maker_net_not_positive_after_cost`
- candidate_key: `feature_gate_all_folds_symbols|all|all|mlofi_norm_l5|low_gate_short_pressure|short`
- fills: `153`
- dynamic maker net mean: `-0.9711` bps
- dynamic gross mean: `1.3603` bps
- control_abs_ge_base_abs_rate: `0.8750`
- max_date_share: `0.4455`
- max_symbol_share: `0.5386`

## V12 Frozen Baseline

- V12 best key: `fold2|BONK1MUSDT|shock_q99|v11_trade_flow_shock|pullback_618|patient_vol_15x_range_075|struct60s|wait300s|timeout3600s`
- V12 fills: `16`
- V12 maker net mean: `0.6421` bps
- V12 gross mean: `3.5669` bps
- V12 stop-loss gross mean: `-19.3327` bps
- V13 also writes a paired `frozen_marker` negative control from the same V10c signals, so the dynamic marker comparison is same-signal and not just cross-report.

## Top Dynamic vs Frozen Rows

| scope | feature | gate | side | fills | dyn_net | frozen_net | dyn_tail | frozen_tail | date_share | control_rate |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| feature_gate_all_folds_symbols | mlofi_norm_l5 | low_gate_short_pressure | short | 153 | -0.9711 | -2.9313 | -1.3339 | -1.3342 | 0.4455 | 0.8750 |
| feature_gate_all_folds_symbols | queue_imbalance_25 | low_gate_short_pressure | short | 159 | -1.1996 | -2.5998 | -1.3085 | -1.3087 | 0.3540 | 0.8750 |
| feature_gate_all_folds_symbols | liquidity_shock_score | low_gate_short_pressure | short | 437 | -1.5420 | -2.6060 | -1.3385 | -1.3387 | 0.3263 | 0.7500 |
| feature_gate_all_folds_symbols | trade_arrival_alignment | low_gate_short_pressure | short | 414 | -2.1451 | -2.6373 | -1.3350 | -1.3364 | 0.3279 | 0.6250 |
| feature_gate_all_folds_symbols | mlofi_norm_l10 | low_gate_short_pressure | short | 117 | -3.1590 | -3.1593 | -1.3293 | -1.3306 | 0.5785 | 0.5000 |
| feature_gate_all_folds_symbols | liquidity_shock_score | high_gate_long_pressure | long | 0 | NA | NA | NA | NA | 0.3311 | NA |
| feature_gate_all_folds_symbols | mlofi_norm_l10 | high_gate_long_pressure | long | 0 | NA | NA | NA | NA | 0.3571 | NA |
| feature_gate_all_folds_symbols | mlofi_norm_l5 | high_gate_long_pressure | long | 0 | NA | NA | NA | NA | 0.3696 | NA |

## Negative Controls

- control types written: `frozen_marker,random_marker_same_move_count,side_flip,timestamp_shift_minus_60s,timestamp_shift_plus_60s,upper_lower_swap,vol_state_shuffle_within_date,wrong_symbol_marker,wrong_symbol_same_time`
- Required controls are present: frozen marker, random marker same move count, vol-state shuffle, wrong-symbol marker, upper/lower swap, side flip, timestamp shifts, and wrong-symbol same-time.

## Mechanics Fixed From V12

- Dynamic marker recomputes `center_t`, `sigma_t`, `vol_state`, and `marker_t` on every event while the setup is active.
- Entry price is `marker_t`; diagnostics explicitly record touch-row mid so marker-fill semantics are auditable.
- Marker moves only when the update exceeds `max(0.25 * sigma_t, spread_bps, tick_floor)` and each move adds queue reset penalty.
- Wings update every event after entry; TP can trail favorably, SL only tightens, and `SL/TP <= 1.5` is enforced.
- If TP and SL are both hit in the same event, adverse-first is applied.

## Outputs

- trades: `date/bonk_v13_dynamic_marker_trades_20260514_bonk_v10_stage1_pilot.csv`
- summary: `date/bonk_v13_dynamic_marker_summary_20260514_bonk_v10_stage1_pilot.csv`
- negative_controls: `date/bonk_v13_dynamic_marker_negative_controls_20260514_bonk_v10_stage1_pilot.csv`
- failure_report: `date/bonk_v13_dynamic_marker_failure_report_20260514_bonk_v10_stage1_pilot.csv`
- diagnostics: `date/bonk_v13_dynamic_marker_diagnostics_20260514_bonk_v10_stage1_pilot.csv`
- diagnostic rows: `5279`
# BONK V14 Queue-Reactive First-Passage State Policy

- generated_at: `2026-05-15T11:21:52Z`
- run_tag: `20260514_bonk_v10_stage1_pilot`
- guardrail: `research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim`
- stance: research-only; no trading advice, no execution recommendation, no alpha claim.

## Inputs

- V10c panel files: `86`
- V10c panel rows read: `1945574`
- usable rows: `1945574`
- folds from V10 filter params: `6`
- train label rows: `168000`
- calibration rows: `30840`
- validation decision rows: `72000`
- validation entered setup rows: `0`

## Primary Status

- primary_status: `hard_fail_fills_lt_500`
- evidence: `setups=0 fills=0 maker_net=NA stress_net=NA control_rate=NA`
- fills: `0`
- maker_net_bps_mean: `NA`
- stress_maker_net_bps_mean: `NA`
- winsorized_top1_maker_net_bps_mean: `NA`
- max_date_share: `NA`
- max_symbol_share: `NA`
- control_abs_ge_base_abs_rate: `NA`

## Model Mechanics

- V14 labels are generated only inside each fold train window with `label_source_phase=train`.
- State buckets combine causal MLOFI tensor pressure, depth curvature, microprice drift/deviation, spread/liquidity, depletion/replenish/cancel pressure, trade-flow imbalance, liquidity shock, event-time RV, cross-symbol lagged pressure, and toxicity proxy.
- Calibration estimates `P_fill`, side-specific favorable first-passage `P_up_first`, adverse `P_down_first`, timeout probability, expected gross/net, stress net, and tail ES from train labels only.
- Validation replay is frozen: every validation event enumerates `(side,d,U,D,H)`, resolves support through exact/parent/root fallback, and enters only if support, expected net, fill probability, and first-passage gates pass.
- Same-event TP/SL collision is adverse-first; fill price is the marker, not the touch-row mid.

## Negative Controls

- controls written: `timestamp_shift_minus_300s,timestamp_shift_minus_60s,timestamp_shift_minus_30s,timestamp_shift_minus_5s,timestamp_shift_plus_5s,timestamp_shift_plus_30s,timestamp_shift_plus_60s,timestamp_shift_plus_300s,side_flip,wrong_symbol_same_time,wrong_symbol_lagged_state,surface_shuffle,skew_flip,wrong_date_surface,future_vol_leak_test,random_marker_same_support,upper_lower_swap`
- Required controls include timestamp shifts +/-5s/+/-30s/+/-60s/+/-300s, side flip, wrong-symbol same-time, wrong-symbol lagged-state, surface shuffle, skew flip, wrong-date surface, future-vol leak test, random marker same support, and upper/lower swap.
- `future_vol_leak_test` is explicitly marked `control_only=true` and is never used in base calibration or validation decisions.

## Outputs

- train_labels: `date/bonk_v14_state_policy_train_labels_20260514_bonk_v10_stage1_pilot.csv`
- calibration: `date/bonk_v14_state_policy_calibration_20260514_bonk_v10_stage1_pilot.csv`
- params: `date/bonk_v14_state_policy_params_20260514_bonk_v10_stage1_pilot.csv`
- valid_decisions: `date/bonk_v14_state_policy_valid_decisions_20260514_bonk_v10_stage1_pilot.csv`
- valid_trades: `date/bonk_v14_state_policy_valid_trades_20260514_bonk_v10_stage1_pilot.csv`
- summary: `date/bonk_v14_state_policy_summary_20260514_bonk_v10_stage1_pilot.csv`
- negative_controls: `date/bonk_v14_state_policy_negative_controls_20260514_bonk_v10_stage1_pilot.csv`
- diagnostics: `date/bonk_v14_state_policy_diagnostics_20260514_bonk_v10_stage1_pilot.csv`
- failure_report: `date/bonk_v14_state_policy_failure_report_20260514_bonk_v10_stage1_pilot.csv`
- manifest: `date/bonk_v14_state_policy_manifest_20260514_bonk_v10_stage1_pilot.csv`
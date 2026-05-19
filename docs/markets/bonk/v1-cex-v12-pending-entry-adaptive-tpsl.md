# BONK V12 Pending Entry Adaptive TP/SL

Status: 2026-05-15T09:31:14Z.
Run tag: `20260514_bonk_v10_stage1_pilot`.
Fee bps: `2.0000`.

research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim

## Primary Status

`insufficient_fills`

best validation candidate maker_net=0.642118 fills=16 fill_rate=0.6957

## What Changed Versus V11

- V11 entered immediately and exited after a fixed horizon.
- V12 treats trade-flow shock as a watch state, waits for a valid entry zone, and exits by first hit of adaptive take-profit, stop-loss, or timeout.
- No-fill setups are counted rather than forced into bad trades.

## Output Counts

- potential rows: `1945574`
- candidate grid rows: `2592`
- selected frozen configs: `12`
- validation setup/trade rows: `1194`
- summary rows: `12`
- negative-control rows: `60`

## Best Validation Candidate

- `fold2` `BONK1MUSDT` `shock_q99` `v11_trade_flow_shock|pullback_618|patient_vol_15x_range_075|struct60s|wait300s|timeout3600s`
- setups=`23`, fills=`16`, fill_rate=`0.6957`
- maker_net_bps_mean=`0.642118`, win_rate=`0.8750`, max_date_share=`0.8125`
- control_abs_ge_base_abs_rate=`0.8000`, control_separated=`false`

## Artifacts

- `date/bonk_v12_pending_entry_candidates_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v12_pending_entry_trades_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v12_pending_entry_summary_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v12_pending_entry_negative_controls_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v12_pending_entry_failure_report_20260514_bonk_v10_stage1_pilot.csv`

## Interpretation Boundary

This is still a research diagnostic. A positive row would mean the patient translation is worth validating, not that the strategy is deployable.

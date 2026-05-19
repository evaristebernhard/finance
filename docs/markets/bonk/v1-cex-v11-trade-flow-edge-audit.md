# BONK V11 Trade-Flow Edge Audit

Status: 2026-05-15T08:29:29Z.
Run tag: `20260514_bonk_v10_stage1_pilot`.
Fee bps: `2.0000`.

research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim

## Primary Status

`gross_edge_too_thin`

best candidate BONK1MUSDC|shock_q99|cooldown_300s|horizon_60s has maker_net_mean=-0.007751 over 131 rows

## Input And Data Checks

- potential rows: `1945574`
- quality rows: `14`
- excluded missing mid/spread/fill rows: `0` / `0` / `0`
- data quality blockers: `0`

## Audit Outputs

- side alignment rows: `6` -> `date/bonk_v11_trade_flow_side_alignment_20260514_bonk_v10_stage1_pilot.csv`
- event study rows: `192` -> `date/bonk_v11_trade_flow_event_study_20260514_bonk_v10_stage1_pilot.csv`
- sparse anchor rows: `4892` -> `date/bonk_v11_trade_flow_sparse_anchors_20260514_bonk_v10_stage1_pilot.csv`
- after-cost rows: `9784` -> `date/bonk_v11_trade_flow_after_cost_20260514_bonk_v10_stage1_pilot.csv`
- negative-control rows: `39136` -> `date/bonk_v11_trade_flow_negative_controls_20260514_bonk_v10_stage1_pilot.csv`
- failure report: `date/bonk_v11_trade_flow_failure_report_20260514_bonk_v10_stage1_pilot.csv`

## Top Diagnostics

- top shock event-study row: `fold2` `BONK1MUSDC` `shock_q99` horizon `900` mean signed gross `8.100840` selected `422`
- best single after-cost row: `fold2` `BONK1MUSDC` `shock_q95` cooldown `60` horizon `60` maker net `211.233393`

## Interpretation Boundary

V11 tests whether V10 trade-flow shocks can become sparse, cost-aware, and control-separated events under a fixed 2 bps cost. It does not expand the window, train a richer model, or convert the result into an execution recommendation.

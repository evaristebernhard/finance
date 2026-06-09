# CCUSDT V2 Universe Liquidity Envelope Audit

Status: `20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1`.

Guardrail: `research_only_universe_liquidity_envelope_no_execution_recommendation_no_alpha_claim`.

Objective branch: screen the downloaded small-tier Bullish universe before any entry-quality, exit-shape, or risk-control modeling. This is not an alpha claim or execution recommendation.

## Decision

Pre-alpha liquidity candidates: `1`.

At least one symbol passes the first spread/depth/activity envelope and can be queued for symbol-specific execution modeling.

## Scorecard

| symbol | dates | median_daily_median_spread_bps | median_daily_p95_spread_bps | median_daily_top_depth_p05_quote | depth_support_day_rate | median_trade_rows_per_day | mean_top_trade_notional_rate_per_min | pre_alpha_gate | failed_gates | universe_liquidity_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDC | 17 | 0.0125 | 0.0127 | 14.7372 | 1.0000 | 217411.0000 | 252769.3629 | True |  | pre_alpha_liquidity_candidate |
| DOGEUSDC | 17 | 35.7143 | 45.3515 | 3611.5922 | 1.0000 | 17.0000 | 28.6341 | False | spread,activity | spread_and_activity_no_go |
| SUIUSDC | 17 | 8.7510 | 16.2954 | 19.3180 | 1.0000 | 491.0000 | 150.4621 | False | spread,activity | spread_and_activity_no_go |
| ETHUSDC | 17 | 0.0434 | 0.0866 | 6.5027 | 0.0000 | 125333.0000 | 53014.2690 | False | depth | depth_no_go |
| SOLUSDC | 17 | 0.0113 | 0.0227 | 0.5799 | 0.0000 | 99895.0000 | 10612.7341 | False | depth | depth_no_go |
| BONK1MUSDT | 17 | 1.5146 | 3.0381 | 0.4705 | 0.0000 | 3131.0000 | 280.9102 | False | depth | depth_no_go |
| BONK1MUSDC | 17 | 2.9036 | 3.0483 | 1.1329 | 0.0000 | 27912.0000 | 1048.7642 | False | spread,depth | spread_and_depth_no_go |
| PEPE1MUSDC | 0 |  |  |  |  |  |  | False | coverage,spread,depth,activity | missing_or_unreadable_data_no_go |
| SHIB1MUSDC | 0 |  |  |  |  |  |  | False | coverage,spread,depth,activity | missing_or_unreadable_data_no_go |
| WIFUSDC | 0 |  |  |  |  |  |  | False | coverage,spread,depth,activity | missing_or_unreadable_data_no_go |

## Thresholds

- target_notional_quote: `10.0`
- max_median_spread_bps: `2.0`
- max_p95_spread_bps: `5.0`
- min_depth_support_row_rate: `0.95`
- min_depth_support_day_rate: `0.95`
- min_dates: `10`
- min_median_trade_rows: `100`
- min_quote_match_rate: `0.8`
- min_top_trade_notional_rate_per_min: `100.0`

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_liquidity_envelope_daily_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1 --symbols "BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT,SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC" --target-notional-quote 10 --run-tag 20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1
```

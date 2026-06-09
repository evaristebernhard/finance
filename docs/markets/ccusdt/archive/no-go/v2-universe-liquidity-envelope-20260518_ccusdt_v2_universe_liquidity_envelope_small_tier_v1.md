# CCUSDT V2 Universe Liquidity Envelope Audit

Status: `20260518_ccusdt_v2_universe_liquidity_envelope_small_tier_v1`.

Guardrail: `research_only_universe_liquidity_envelope_no_execution_recommendation_no_alpha_claim`.

Objective branch: screen the downloaded small-tier Bullish universe before any entry-quality, exit-shape, or risk-control modeling. This is not an alpha claim or execution recommendation.

## Decision

Pre-alpha liquidity candidates: `0`.

No downloaded symbol passes the first spread/depth/activity envelope, so alpha mining should remain blocked until a better execution universe is available.

## Scorecard

| symbol | dates | median_daily_median_spread_bps | median_daily_p95_spread_bps | median_daily_top_depth_p05_quote | depth_support_day_rate | median_trade_rows_per_day | mean_top_trade_notional_rate_per_min | pre_alpha_gate | failed_gates | universe_liquidity_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DOGEUSDC | 17 | 35.7143 | 45.3515 | 3611.5922 | 1.0000 | 17.0000 | 28.6341 | False | spread,activity | spread_and_activity_no_go |
| SUIUSDC | 17 | 8.7510 | 16.2954 | 19.3180 | 0.0000 | 491.0000 | 150.4621 | False | spread,depth,activity | spread_depth_activity_no_go |
| PEPE1MUSDC | 0 |  |  |  |  |  |  | False | coverage,spread,depth,activity | missing_or_unreadable_data_no_go |
| SHIB1MUSDC | 0 |  |  |  |  |  |  | False | coverage,spread,depth,activity | missing_or_unreadable_data_no_go |
| WIFUSDC | 0 |  |  |  |  |  |  | False | coverage,spread,depth,activity | missing_or_unreadable_data_no_go |

## Thresholds

- target_notional_quote: `100.0`
- max_median_spread_bps: `2.0`
- max_p95_spread_bps: `5.0`
- min_depth_support_row_rate: `0.95`
- min_depth_support_day_rate: `0.95`
- min_dates: `10`
- min_median_trade_rows: `100`
- min_quote_match_rate: `0.8`
- min_top_trade_notional_rate_per_min: `100.0`

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_liquidity_envelope_daily_20260518_ccusdt_v2_universe_liquidity_envelope_small_tier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_small_tier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_universe_liquidity_envelope_small_tier_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\ccusdt_universe\v1 --symbols "SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC" --run-tag 20260518_ccusdt_v2_universe_liquidity_envelope_small_tier_v1
```

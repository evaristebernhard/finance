# CCUSDT V2 External Venue Inventory

Status: `20260518_ccusdt_v2_external_venue_inventory_v1`.

Guardrail: `research_only_external_venue_inventory_no_execution_recommendation_no_alpha_claim`.

## Decision

Decision: `external_venue_ccusdt_l2_data_blocked`.

Local data does not contain CCUSDT L2 on an external venue. The cross-market pivot can use same-venue Bullish leaders and coarse Binance 1m context, but not a synchronized external CCUSDT/CC-related L2 market from current local files.

## Summary

- inventory_rows: `42`
- venues: `binance,bullish`
- ccusdt_l2_venues: `bullish`
- external_ccusdt_l2_ready: `False`
- same_venue_leader_symbols: `BONK1MUSDC,BONK1MUSDT,BTCUSDC,CCUSDT,DOGEUSDC,ETHUSDC,PEPE1MUSDC,SHIB1MUSDC,SOLUSDC,SUIUSDC,WIFUSDC`
- binance_kline_symbols: `APTUSDT,ARBUSDT,BONKUSDT,BTCUSDT,DOGEUSDT,ETHUSDT,OPUSDT,PENGUUSDT,PEPEUSDT,SHIBUSDT,SOLUSDT,SUIUSDT,WIFUSDT`

## Inventory

| market_root | venue | dataset | data_type | symbol | date_count | first_date | last_date | file_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bonk | binance | binance_spot_klines | spot_klines_1m | APTUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | ARBUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | BONKUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | BTCUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | DOGEUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | ETHUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | OPUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | PENGUUSDT | 14 | 2026-04-29 | 2026-05-12 | 14 |
| bonk | binance | binance_spot_klines | spot_klines_1m | PEPEUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | SHIBUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | SOLUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | SUIUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| bonk | binance | binance_spot_klines | spot_klines_1m | WIFUSDT | 1 | 2026-05-12 | 2026-05-12 | 1 |
| ccusdt | bullish | bullish_book_snapshot_25 | book_snapshot_25 | CCUSDT | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | BONK1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | BONK1MUSDT | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | BTCUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt | bullish | bullish_book_ticker | book_ticker | CCUSDT | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | DOGEUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | ETHUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | PEPE1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | SHIB1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | SOLUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | SUIUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_book_ticker | book_ticker | WIFUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt | bullish | bullish_incremental_book_L2 | incremental_book_L2 | CCUSDT | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_incremental_book_L2 | incremental_book_L2 | DOGEUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_incremental_book_L2 | incremental_book_L2 | PEPE1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_incremental_book_L2 | incremental_book_L2 | SHIB1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_incremental_book_L2 | incremental_book_L2 | SUIUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_incremental_book_L2 | incremental_book_L2 | WIFUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | BONK1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | BONK1MUSDT | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | BTCUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt | bullish | bullish_trades | trades | CCUSDT | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | DOGEUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | ETHUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | PEPE1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | SHIB1MUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | SOLUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | SUIUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |
| ccusdt_universe | bullish | bullish_trades | trades | WIFUSDC | 17 | 2026-04-29 | 2026-05-15 | 17 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_external_venue_inventory_20260518_ccusdt_v2_external_venue_inventory_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_external_venue_inventory_20260518_ccusdt_v2_external_venue_inventory_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_external_venue_inventory.py --run-tag 20260518_ccusdt_v2_external_venue_inventory_v1
```

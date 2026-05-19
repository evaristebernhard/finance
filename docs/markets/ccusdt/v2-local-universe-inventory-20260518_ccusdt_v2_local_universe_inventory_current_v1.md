# CCUSDT V2 Local Bullish Universe Inventory

Status: `20260518_ccusdt_v2_local_universe_inventory_current_v1`.

Guardrail: `research_only_local_universe_inventory_no_download_no_execution_recommendation`.

Objective branch: determine whether the local workspace has a multi-symbol Bullish L2 universe for the liquidity-envelope pivot. This pass only inventories paths; it does not download or inspect private data.

## Decision

Local universe status: `multi_symbol_ready`.

A local multi-symbol core L2 universe exists. The next step is to run the liquidity-envelope audit per symbol before any symbol-level alpha mining.

## Inventory

| market | symbol | book_ticker_dates | trades_dates | incremental_book_L2_dates | book_snapshot_25_dates | common_core_dates | common_core_first_date | common_core_last_date | core_l2_ready | full_l2_ready |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ccusdt | CCUSDT | 17 | 17 | 17 | 17 | 17 | 2026-04-29 | 2026-05-15 | True | True |
| ccusdt_universe | DOGEUSDC | 17 | 17 | 17 | 0 | 17 | 2026-04-29 | 2026-05-15 | True | False |
| ccusdt_universe | PEPE1MUSDC | 17 | 17 | 17 | 0 | 17 | 2026-04-29 | 2026-05-15 | True | False |
| ccusdt_universe | SHIB1MUSDC | 17 | 17 | 17 | 0 | 17 | 2026-04-29 | 2026-05-15 | True | False |
| ccusdt_universe | SUIUSDC | 17 | 17 | 17 | 0 | 17 | 2026-04-29 | 2026-05-15 | True | False |
| ccusdt_universe | WIFUSDC | 17 | 17 | 17 | 0 | 17 | 2026-04-29 | 2026-05-15 | True | False |
| ccusdt_universe | BONK1MUSDC | 17 | 17 | 0 | 0 | 0 |  |  | False | False |
| ccusdt_universe | BONK1MUSDT | 17 | 17 | 0 | 0 | 0 |  |  | False | False |
| ccusdt_universe | BTCUSDC | 17 | 17 | 0 | 0 | 0 |  |  | False | False |
| ccusdt_universe | ETHUSDC | 17 | 17 | 0 | 0 | 0 |  |  | False | False |
| ccusdt_universe | SOLUSDC | 17 | 17 | 0 | 0 | 0 |  |  | False | False |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_local_bullish_universe_inventory_20260518_ccusdt_v2_local_universe_inventory_current_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_current_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_local_universe_inventory.py --run-tag 20260518_ccusdt_v2_local_universe_inventory_current_v1
```

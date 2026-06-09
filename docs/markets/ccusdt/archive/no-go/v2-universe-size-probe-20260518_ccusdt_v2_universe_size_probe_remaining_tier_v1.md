# CCUSDT V2 Bullish Universe Size Probe

Status: `20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1`.

Guardrail: `research_only_universe_size_probe_metadata_or_range_no_body_download_no_execution_recommendation`.

This is a metadata/one-byte Range size probe over the dry-run universe manifest. It estimates download size without downloading dataset bodies; Range GET is used only when HEAD is not usable.

## Decision

Probed `255` planned files: `253` available, `0` missing, `2` errors. Estimated total size is `52.64` GB.

This makes the universe pivot data step explicit, but it is still not evidence of an executable edge.

## Size Summary

| symbol | data_type | files | available_files | missing_files | error_files | gb |
| --- | --- | --- | --- | --- | --- | --- |
| BTCUSDC | ALL | 51 | 50 |  |  | 18.2852 |
| ETHUSDC | ALL | 51 | 51 |  |  | 17.4803 |
| SOLUSDC | ALL | 51 | 51 |  |  | 7.5243 |
| BONK1MUSDT | ALL | 51 | 51 |  |  | 5.3508 |
| BONK1MUSDC | ALL | 51 | 50 |  |  | 3.9988 |
| BTCUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0627 |
| ETHUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0517 |
| BONK1MUSDT | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0368 |
| SOLUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0361 |
| BONK1MUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0259 |
| BTCUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 18.1597 |
| ETHUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 17.3907 |
| SOLUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 7.4610 |
| BONK1MUSDT | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 5.3127 |
| BONK1MUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 3.9644 |
| BTCUSDC | trades | 17 | 16 | 0.0000 | 1.0000 | 0.0627 |
| ETHUSDC | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0379 |
| SOLUSDC | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0273 |
| BONK1MUSDC | trades | 17 | 16 | 0.0000 | 1.0000 | 0.0085 |
| BONK1MUSDT | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0013 |

## Probe Status

| probe_status | http_status | rows |
| --- | --- | --- |
| available | 200.0000 | 15 |
| available | 206.0000 | 238 |
| error |  | 2 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1 --symbols "BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT" --workers 8 --timeout-seconds 15
```

# CCUSDT V2 Bullish Universe Size Probe

Status: `20260518_ccusdt_v2_universe_size_probe_smoke_v1`.

Guardrail: `research_only_universe_size_probe_metadata_or_range_no_body_download_no_execution_recommendation`.

This is a metadata/one-byte Range size probe over the dry-run universe manifest. It estimates download size without downloading dataset bodies; Range GET is used only when HEAD is not usable.

## Decision

Probed `33` planned files: `33` available, `0` missing, `0` errors. Estimated total size is `3.61` GB.

This makes the universe pivot data step explicit, but it is still not evidence of an executable edge.

## Size Summary

| symbol | data_type | files | available_files | missing_files | error_files | gb |
| --- | --- | --- | --- | --- | --- | --- |
| ETHUSDC | ALL | 3 | 3 |  |  | 1.2595 |
| BTCUSDC | ALL | 3 | 3 |  |  | 1.2195 |
| SOLUSDC | ALL | 3 | 3 |  |  | 0.3341 |
| BONK1MUSDT | ALL | 3 | 3 |  |  | 0.3110 |
| CCUSDT | ALL | 3 | 3 |  |  | 0.2496 |
| BONK1MUSDC | ALL | 3 | 3 |  |  | 0.2215 |
| SUIUSDC | ALL | 3 | 3 |  |  | 0.0144 |
| DOGEUSDC | ALL | 3 | 3 |  |  | 0.0039 |
| SHIB1MUSDC | ALL | 3 | 3 |  |  | 0.0000 |
| PEPE1MUSDC | ALL | 3 | 3 |  |  | 0.0000 |
| WIFUSDC | ALL | 3 | 3 |  |  | 0.0000 |
| BTCUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0041 |
| ETHUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0028 |
| BONK1MUSDT | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0023 |
| CCUSDT | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0022 |
| BONK1MUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0016 |
| SOLUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0014 |
| DOGEUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0005 |
| SUIUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0003 |
| SHIB1MUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| PEPE1MUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| WIFUSDC | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| ETHUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 1.2545 |
| BTCUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 1.2108 |
| SOLUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.3316 |
| BONK1MUSDT | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.3086 |
| CCUSDT | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.2472 |
| BONK1MUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.2196 |
| SUIUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.0141 |
| DOGEUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.0034 |
| PEPE1MUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| SHIB1MUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| WIFUSDC | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| BTCUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0046 |
| ETHUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0022 |
| SOLUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0010 |
| BONK1MUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0004 |
| CCUSDT | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0001 |
| BONK1MUSDT | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0001 |
| SUIUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| DOGEUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| PEPE1MUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| SHIB1MUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| WIFUSDC | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |

## Probe Status

| probe_status | http_status | rows |
| --- | --- | --- |
| available | 200 | 6 |
| available | 206 | 27 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_universe_size_probe_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_smoke_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_smoke_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260518_ccusdt_v2_universe_size_probe_smoke_v1 --max-jobs 33 --workers 8 --timeout-seconds 15
```

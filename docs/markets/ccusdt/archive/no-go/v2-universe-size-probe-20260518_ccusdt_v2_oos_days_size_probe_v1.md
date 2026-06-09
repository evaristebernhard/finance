# CCUSDT V2 Bullish Universe Size Probe

Status: `20260518_ccusdt_v2_oos_days_size_probe_v1`.

Guardrail: `research_only_universe_size_probe_metadata_or_range_no_body_download_no_execution_recommendation`.

This is a metadata/one-byte Range size probe over the dry-run universe manifest. It estimates download size without downloading dataset bodies; Range GET is used only when HEAD is not usable.

## Decision

Probed `36` planned files: `18` available, `18` missing, `0` errors. Estimated total size is `0.24` GB.

This makes the universe pivot data step explicit, but it is still not evidence of an executable edge.

## Size Summary

| symbol | data_type | files | available_files | missing_files | error_files | gb |
| --- | --- | --- | --- | --- | --- | --- |
| CCUSDT | ALL | 6 | 3 |  |  | 0.2200 |
| SUIUSDC | ALL | 6 | 3 |  |  | 0.0209 |
| DOGEUSDC | ALL | 6 | 3 |  |  | 0.0027 |
| SHIB1MUSDC | ALL | 6 | 3 |  |  | 0.0000 |
| PEPE1MUSDC | ALL | 6 | 3 |  |  | 0.0000 |
| WIFUSDC | ALL | 6 | 3 |  |  | 0.0000 |
| CCUSDT | book_ticker | 2 | 1 | 1.0000 | 0.0000 | 0.0019 |
| SUIUSDC | book_ticker | 2 | 1 | 1.0000 | 0.0000 | 0.0004 |
| DOGEUSDC | book_ticker | 2 | 1 | 1.0000 | 0.0000 | 0.0002 |
| SHIB1MUSDC | book_ticker | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| PEPE1MUSDC | book_ticker | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| WIFUSDC | book_ticker | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| CCUSDT | incremental_book_L2 | 2 | 1 | 1.0000 | 0.0000 | 0.2180 |
| SUIUSDC | incremental_book_L2 | 2 | 1 | 1.0000 | 0.0000 | 0.0205 |
| DOGEUSDC | incremental_book_L2 | 2 | 1 | 1.0000 | 0.0000 | 0.0025 |
| PEPE1MUSDC | incremental_book_L2 | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| SHIB1MUSDC | incremental_book_L2 | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| WIFUSDC | incremental_book_L2 | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| CCUSDT | trades | 2 | 1 | 1.0000 | 0.0000 | 0.0001 |
| SUIUSDC | trades | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| DOGEUSDC | trades | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| PEPE1MUSDC | trades | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| SHIB1MUSDC | trades | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |
| WIFUSDC | trades | 2 | 1 | 1.0000 | 0.0000 | 0.0000 |

## Probe Status

| probe_status | http_status | rows |
| --- | --- | --- |
| available | 200 | 6 |
| available | 206 | 12 |
| missing | 400 | 18 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_oos_days_size_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260518_ccusdt_v2_oos_days_size_probe_v1 --workers 8 --timeout-seconds 30
```

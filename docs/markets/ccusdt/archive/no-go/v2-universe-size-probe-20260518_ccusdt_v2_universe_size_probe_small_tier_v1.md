# CCUSDT V2 Bullish Universe Size Probe

Status: `20260518_ccusdt_v2_universe_size_probe_small_tier_v1`.

Guardrail: `research_only_universe_size_probe_metadata_or_range_no_body_download_no_execution_recommendation`.

This is a metadata/one-byte Range size probe over the dry-run universe manifest. It estimates download size without downloading dataset bodies; Range GET is used only when HEAD is not usable.

## Decision

Probed `255` planned files: `255` available, `0` missing, `0` errors. Estimated total size is `0.40` GB.

This makes the universe pivot data step explicit, but it is still not evidence of an executable edge.

## Size Summary

| symbol | data_type | files | available_files | missing_files | error_files | gb |
| --- | --- | --- | --- | --- | --- | --- |
| SUIUSDC | ALL | 51 | 51 |  |  | 0.3536 |
| DOGEUSDC | ALL | 51 | 51 |  |  | 0.0492 |
| SHIB1MUSDC | ALL | 51 | 51 |  |  | 0.0000 |
| PEPE1MUSDC | ALL | 51 | 51 |  |  | 0.0000 |
| WIFUSDC | ALL | 51 | 51 |  |  | 0.0000 |
| SUIUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0085 |
| DOGEUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0048 |
| SHIB1MUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| PEPE1MUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| WIFUSDC | book_ticker | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| SUIUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 0.3449 |
| DOGEUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 0.0444 |
| PEPE1MUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| SHIB1MUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| WIFUSDC | incremental_book_L2 | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| SUIUSDC | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0002 |
| DOGEUSDC | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| PEPE1MUSDC | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| SHIB1MUSDC | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |
| WIFUSDC | trades | 17 | 17 | 0.0000 | 0.0000 | 0.0000 |

## Probe Status

| probe_status | http_status | rows |
| --- | --- | --- |
| available | 200 | 111 |
| available | 206 | 144 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_files_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_small_tier_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260518_ccusdt_v2_universe_size_probe_small_tier_v1 --symbols "SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC" --workers 8 --timeout-seconds 15
```

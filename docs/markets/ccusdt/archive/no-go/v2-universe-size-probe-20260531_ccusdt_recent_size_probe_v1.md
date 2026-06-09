# CCUSDT V2 Bullish Universe Size Probe

Status: `20260531_ccusdt_recent_size_probe_v1`.

Guardrail: `research_only_universe_size_probe_metadata_or_range_no_body_download_no_execution_recommendation`.

This is a metadata/one-byte Range size probe over the dry-run universe manifest. It estimates download size without downloading dataset bodies; Range GET is used only when HEAD is not usable.

## Decision

Probed `36` planned files: `36` available, `0` missing, `0` errors. Estimated total size is `2.66` GB.

This makes the universe pivot data step explicit, but it is still not evidence of an executable edge.

## Size Summary

| symbol | data_type | files | available_files | missing_files | error_files | gb |
| --- | --- | --- | --- | --- | --- | --- |
| CCUSDT | ALL | 36 | 36 |  |  | 2.6564 |
| CCUSDT | book_ticker | 12 | 12 | 0.0000 | 0.0000 | 0.0244 |
| CCUSDT | incremental_book_L2 | 12 | 12 | 0.0000 | 0.0000 | 2.6306 |
| CCUSDT | trades | 12 | 12 | 0.0000 | 0.0000 | 0.0014 |

## Probe Status

| probe_status | http_status | rows |
| --- | --- | --- |
| available | 206 | 36 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_files_20260531_ccusdt_recent_size_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260531_ccusdt_recent_size_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260531_ccusdt_recent_size_probe_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260531_ccusdt_recent_size_probe_v1 --symbols "CCUSDT" --data-types "book_ticker,trades,incremental_book_L2" --workers 8 --timeout-seconds 30
```

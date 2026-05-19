# CCUSDT V2 Bullish Universe Size Probe

Status: `20260519_ccusdt_oos_day20260518_size_probe_v1`.

Guardrail: `research_only_universe_size_probe_metadata_or_range_no_body_download_no_execution_recommendation`.

This is a metadata/one-byte Range size probe over the dry-run universe manifest. It estimates download size without downloading dataset bodies; Range GET is used only when HEAD is not usable.

## Decision

Probed `3` planned files: `3` available, `0` missing, `0` errors. Estimated total size is `0.23` GB.

This makes the universe pivot data step explicit, but it is still not evidence of an executable edge.

## Size Summary

| symbol | data_type | files | available_files | missing_files | error_files | gb |
| --- | --- | --- | --- | --- | --- | --- |
| CCUSDT | ALL | 3 | 3 |  |  | 0.2315 |
| CCUSDT | book_ticker | 1 | 1 | 0.0000 | 0.0000 | 0.0021 |
| CCUSDT | incremental_book_L2 | 1 | 1 | 0.0000 | 0.0000 | 0.2292 |
| CCUSDT | trades | 1 | 1 | 0.0000 | 0.0000 | 0.0001 |

## Probe Status

| probe_status | http_status | rows |
| --- | --- | --- |
| available | 206 | 3 |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_files_20260519_ccusdt_oos_day20260518_size_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260519_ccusdt_oos_day20260518_size_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_universe_size_probe_summary_20260519_ccusdt_oos_day20260518_size_probe_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --run-tag 20260519_ccusdt_oos_day20260518_size_probe_v1 --workers 3 --timeout-seconds 30
```

# CCUSDT V2 External Acquisition Plan

Status: `20260518_ccusdt_v2_external_acquisition_plan_v1`.

Guardrail: `research_only_external_acquisition_plan_no_download_no_execution_recommendation_no_alpha_claim`.

## Decision

Decision: `external_acquisition_blocked_by_access`.

This is a no-download acquisition gate. It converts the Tardis external metadata probe into a dataset manifest, but rows stay `blocked_access` until the API key has requested access for an external CC L2 venue.

## Summary

- metadata_decision: `external_tardis_cc_l2_metadata_blocked`
- cc_external_l2_metadata_exchanges: `binance-futures,bybit,kucoin,okex`
- cc_accessible_external_l2_metadata_exchanges: ``
- manifest_rows: `255`
- planned_rows: `0`
- blocked_access_rows: `255`
- candidate_exchanges: `binance-futures,bybit,kucoin,okex`
- candidate_symbols: `CC-USDC,CC-USDT,CCUSDT,ccusdt`

## Manifest Status

| exchange | symbol | status | rows |
| --- | --- | --- | --- |
| binance-futures | ccusdt | blocked_access | 51 |
| bybit | CCUSDT | blocked_access | 51 |
| kucoin | CC-USDT | blocked_access | 51 |
| okex | CC-USDC | blocked_access | 51 |
| okex | CC-USDT | blocked_access | 51 |

## Next Gate

When `planned_rows > 0`, run the metadata/Range size probe against this manifest before any dataset body download:

```powershell
python scripts/ccusdt_v2_universe_size_probe.py --manifest-csv C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_external_acquisition_manifest_20260518_ccusdt_v2_external_acquisition_plan_v1.csv --run-tag 20260518_ccusdt_v2_external_acquisition_plan_v1_size_probe --workers 8 --timeout-seconds 30
```

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_external_acquisition_manifest_20260518_ccusdt_v2_external_acquisition_plan_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_external_acquisition_plan.py --run-tag 20260518_ccusdt_v2_external_acquisition_plan_v1
```

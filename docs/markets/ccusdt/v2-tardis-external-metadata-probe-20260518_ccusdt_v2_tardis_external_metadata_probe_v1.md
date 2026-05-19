# CCUSDT V2 Tardis External Metadata Probe

Status: `20260518_ccusdt_v2_tardis_external_metadata_probe_v1`.

Guardrail: `research_only_tardis_external_metadata_probe_no_download_no_execution_recommendation_no_alpha_claim`.

## Decision

Decision: `external_tardis_cc_l2_metadata_blocked`.

This is metadata-only. It does not download dataset bodies and does not print the Tardis API key.

## Summary

- exchanges_checked: `bullish,binance,binance-futures,bybit,bybit-futures,okex,okex-futures,kucoin,gate-io,mexc,coinbase`
- target_symbols: `ccusdt,ccusdc,cc-usdt,cc-usdc,CCUSDT,CCUSDC`
- cc_l2_metadata_exchanges: `binance-futures,bullish,bybit,kucoin,okex`
- cc_external_l2_metadata_exchanges: `binance-futures,bybit,kucoin,okex`
- cc_accessible_l2_metadata_exchanges: `bullish`
- cc_accessible_external_l2_metadata_exchanges: ``

## Probe Rows

| exchange | external_exchange | metadata_http_status | requested_exchange_access | symbol_count | matched_symbols | cc_symbol_present | has_l2_channel | metadata_error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bullish | False | 200 | True | 1715 | CCUSDC,CCUSDT | True | True |  |
| binance | True | 200 | False | 3290 |  | False | True |  |
| binance-futures | True | 200 | False | 843 | ccusdt | True | True |  |
| bybit | True | 200 | False | 1556 | CCUSDT | True | True |  |
| bybit-futures | True | 400 | False | 0 |  | False | False | {
  "code": 100,
  "message": "Invalid 'exchange' param provided: 'bybit-futures'. Did you mean 'bitget-futures'? Allowed values: 'bitmex', 'deribit', 'binance-futures', 'binance-delivery', 'binance-european-options', 'binance', 'ftx', 'oke |
| okex | True | 200 | False | 2069 | CC-USDC,CC-USDT | True | True |  |
| okex-futures | True | 200 | False | 5722 |  | False | True |  |
| kucoin | True | 200 | False | 2445 | CC-USDT | True | True |  |
| gate-io | True | 200 | False | 5715 |  | False | True |  |
| mexc | True | 400 | False | 0 |  | False | False | {
  "code": 100,
  "message": "Invalid 'exchange' param provided: 'mexc'. Allowed values: 'bitmex', 'deribit', 'binance-futures', 'binance-delivery', 'binance-european-options', 'binance', 'ftx', 'okex-futures', 'okex-options', 'okex-swap', |
| coinbase | True | 200 | False | 885 |  | False | True |  |

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_tardis_external_metadata_probe.py --run-tag 20260518_ccusdt_v2_tardis_external_metadata_probe_v1
```

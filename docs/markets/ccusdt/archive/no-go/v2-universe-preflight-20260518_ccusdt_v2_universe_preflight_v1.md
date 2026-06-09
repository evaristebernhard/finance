# CCUSDT V2 Bullish Universe Preflight

Status: `20260518_ccusdt_v2_universe_preflight_v1`.

Guardrail: `research_only_universe_preflight_dry_run_no_download_no_execution_recommendation`.

This is a dry-run metadata preflight for the `liquidity_envelope_universe` pivot. It uses the existing Bullish/Tardis downloader in `--dry-run` mode, so it does not download L2 files or print private credentials.

## Decision

The local workspace still has only `CCUSDT`, but Tardis/Bullish metadata preflight found a schedulable 11-symbol candidate set for a future universe-envelope download over `2026-04-29..2026-05-15`.

This is not evidence of an executable edge. It only proves the next data acquisition step can be specified.

## Requested Symbols

| status | symbols | file jobs |
| --- | --- | --- |
| planned | `CCUSDT`, `BTCUSDC`, `ETHUSDC`, `SOLUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, `WIFUSDC`, `SUIUSDC`, `BONK1MUSDC`, `BONK1MUSDT` | `561` |
| missing | `APTUSDC`, `ARBUSDC`, `OPUSDC` | `153` |

Each planned symbol has `17` dates x `3` data types:

```text
book_ticker
trades
incremental_book_L2
```

## Artifacts

```text
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_universe_preflight_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_universe_preflight_v1.csv
```

The artifact prefix is inherited from the older generic Bullish downloader. The run tag is CCUSDT V2-specific.

## Reproduce

```powershell
python scripts/bonk_bullish_l2_download.py --dry-run --data-root data\ccusdt_universe\v1 --from-date 2026-04-29 --to-date 2026-05-15 --data-types book_ticker,trades,incremental_book_L2 --symbols "CCUSDT,BTCUSDC,ETHUSDC,SOLUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,SUIUSDC,APTUSDC,ARBUSDC,OPUSDC,BONK1MUSDC,BONK1MUSDT" --run-tag 20260518_ccusdt_v2_universe_preflight_v1 --workers 1
```

## Next Gate

The next executable universe step is a deliberate download, not alpha mining:

1. Download the 11 planned symbols for `book_ticker`, `trades`, and `incremental_book_L2`.
2. Run `scripts/ccusdt_v2_local_universe_inventory.py` against `data/ccusdt_universe/v1` to confirm local multi-symbol coverage.
3. Run the liquidity-envelope audit per symbol before applying entry-quality, exit-shape, or risk-control models.

The active objective remains not achieved until at least one symbol passes the execution envelope and then passes the full V2 walk-forward, cost, matched-control, tail, and risk gates with stable real-cost `>2` bps capture.

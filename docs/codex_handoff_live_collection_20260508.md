# Codex Handoff: Live CHOG Collection Status

Status: 2026-05-08, after continuing the memecoin strategy-first collection on the Windows handoff copy.

Read this file first in a fresh Codex session, then read:

```text
docs/chog_memecoin_collection_strategy.md
docs/chog_v1_backfill_runbook.md
docs/codex_handoff_memecoin_strategy.md
```

## Current Objective

Keep extending CHOG v1 history with the strategy-first path:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

Do not run full `block_header_sample` unless the user explicitly asks for full per-block chain research. The active goal is memecoin strategy features, so `event_block_headers` is the intended header dataset.

## Current Data Coverage

The current clean, quality-checked memecoin path covers about five days:

```text
continuous blocks: 71907947..72992946
approx blocks: 1,085,000
latest closed day tag: day20260502
```

Closed windows:

```text
day20260502: 71907947..72123946
day20260503: 72123947..72339946
day20260504: 72339947..72555946
day20260505: 72555947..72771946
existing verified window: 72771947..72992946
```

Latest successful quality check:

```text
raw.erc20_transfer_logs: rows=8301
raw.main_pool_swap_logs: rows=1927
raw.dex_pool_swap_logs: rows=3486
raw.tx_receipts: rows=3167
raw.event_block_headers: rows=3699
derived.memecoin_event_features: rows=3486
derived.memecoin_hourly_features: rows=404
quality check passed: files=3550 rows=246897
```

Next historical window if the user asks to continue:

```text
FROM=71691947
TO=71907946
DAY_TAG=day20260501
SHARD_SIZE=18000
MAX_PARALLEL_LOG_SHARDS=4
```

## Receipt Collector Optimization

`crate/src/bin/receipt_sample.rs` has been optimized during this continuation.

New behavior and options:

```text
--rpc-batch-size N
  Default: 50.
  Groups receipt and transaction body RPCs into JSON-RPC batch HTTP requests.

--receipt-only
  Fetches only eth_getTransactionReceipt and leaves transaction-body-only columns empty.
  This is enough for current memecoin features because they use receipt_status, gas_used,
  effective_gas_price, and event/header timestamps.
```

Validation already run:

```text
cargo fmt --manifest-path crate/Cargo.toml
cargo test --manifest-path crate/Cargo.toml --bin receipt_sample
cargo build --manifest-path crate/Cargo.toml --bin receipt_sample
cargo test --manifest-path crate/Cargo.toml
```

All tests passed.

Observed receipt timing:

```text
full receipt + tx body, day20260503: 415 tx took about 6.5 minutes
receipt-only, day20260502: 418 tx took about 2.5 minutes
```

Recommendation for the current strategy path:

```text
Use --receipt-only for future daily windows unless the user specifically needs nonce,
input, value, max_fee_per_gas, max_priority_fee_per_gas, or other transaction body fields.
```

## Operational Lessons

Use conservative collection defaults:

```text
logs: 12 shards per day, 18,000 blocks each, max 4 parallel shards
log chunk size: CHOG_LOG_RANGE_BLOCKS=1000
event headers: batch-size 200
receipts: single process, max-txs 200, batch-size 50, rpc-batch-size 50
```

Important Windows/PowerShell lesson:

```text
Always pass an absolute --data-root when using Start-Job.
```

One early PowerShell helper accidentally wrote temporary successful `day20260505` transfer/main outputs under:

```text
C:\Users\jiang\Documents\data\chog\v1
```

The canonical project data root remains:

```text
C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\data\chog\v1
```

Do not delete the stray `Documents\data\chog\v1` directory unless the user confirms.

`dex_rebuild memecoin-features` currently writes current-window derived parts but does not delete older memecoin derived parts. After each successful rebuild, remove stale `derived/memecoin_event_features` and `derived/memecoin_hourly_features` parts from older min-block windows, then rerun:

```text
crate/target/debug/chog_quality_check --data-root data/chog/v1
```

The latest canonical memecoin derived parts have min block `71907951`.

## Daily Continuation Checklist

For the next day:

```text
1. Run transfer_sample shards.
2. Run v3_swap_sample shards.
3. Run dex_swap_collect shards.
4. Run event_header_sample dry-run, then fetch missing event headers.
5. Run receipt_sample dry-run.
6. If queue > 0, run receipt_sample with --receipt-only:

   --max-txs 25 --batch-size 25 --rpc-batch-size 25 --receipt-only
   then rounds of:
   --max-txs 200 --batch-size 50 --rpc-batch-size 50 --receipt-only

7. Rebuild memecoin features.
8. Remove stale memecoin derived parts from prior min-block windows.
9. Run chog_quality_check and only continue if it passes.
```

After a day passes quality check, the following historical window is:

```text
NEXT_TO=$((FROM - 1))
NEXT_FROM=$((FROM - 216000))
```

On PowerShell, do the same arithmetic explicitly and keep absolute paths.

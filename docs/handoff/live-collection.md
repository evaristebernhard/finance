# Codex Handoff: Live CHOG Collection Status

Note: this is a data-collection handoff for the older CHOG/MON path. For current BONK frontend/backend docs, start with [Engineering Docs](../engineering/README.md). For factor-analysis navigation, start with [Research Docs](../research/README.md).

Status: 2026-05-10, after reaching about thirty CHOG historical day windows, completing the latest MON/USDC 26-day range quality check, and optimizing the MON/USDC tx body collector on the Windows handoff copy.

Read this file first in a fresh Codex session, then read:

```text
docs/runbooks/chog-memecoin-collection.md
docs/runbooks/chog-v1-backfill.md
docs/handoff/memecoin-strategy.md
```

## Current Objective

Keep extending CHOG v1 history with the strategy-first path:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

Do not run full `block_header_sample` unless the user explicitly asks for full per-block chain research. The active goal is memecoin strategy features, so `event_block_headers` is the intended header dataset.

## MON/USDC Pivot

The latest user direction is to move executable strategy research toward MON/USDC because CHOG liquidity is too small for first-pass execution work. Keep CHOG as a factor/phenomenon research dataset, but use MON/USDC for the next market microstructure data path.

New MON/USDC v1 swap-only entry point:

```text
scripts/mon_usdc_v1_swap_sample.py
```

Rust MON/USDC V1 collector path is now implemented separately from CHOG:

```text
Cargo.toml
crates/finance_chain_core
crates/mon_usdc_collectors
data/mon_usdc/v1
```

Rust bins:

```text
mon_usdc_pool_snapshot
mon_usdc_swap_collect
mon_usdc_event_header_sample
mon_usdc_receipt_sample
mon_usdc_quality_check
mon_usdc_tx_body_sample
mon_usdc_receipt_log_bundle
mon_usdc_pool_state_sample
mon_usdc_trace_sample
mon_usdc_enriched_rebuild
```

Latest range-scoped Rust V1 coverage:

```text
completed range: 54574455..60190454
pool_swap_logs: 634009
event_block_headers: 383994
tx_receipts: 493760
missing_event_headers: 0
missing_receipts: 0
range quality check passed: files=33013 rows=1511798
```

Notes:

```text
DexScreener timed out locally, so pool_snapshots was seeded from the fixed top4 list.
Uniswap v3, Pancake v3, and both TraderJoe/LFJ v2.2 pools produced live rows.
TraderJoe/LFJ v2.2 pools use getTokenX()/getTokenY() metadata and packed Liquidity Book Swap amounts.
Earlier 592099 swap-row estimate was superseded by the local range-scoped quality result 634009.
Earlier ten-day continuation quality check reported zero_amount_swaps=2 for retained Uniswap v3 dust events with zero MON delta.
```

Current artifacts:

```text
date/mon_usdc_pool_candidates_20260509.csv
date/mon_usdc_v1_swaps_sample_20260509.csv
docs/markets/mon-usdc/v1-data-plan.md
docs/markets/mon-usdc/v1-factor-analysis.md
docs/markets/mon-usdc/v1-enrichment-report.md
```

Current fixed top4 pool set:

```text
Uniswap v3: 0x659bD0BC4167BA25c62E05656F78043E7eD4a9da
Pancake v3: 0x63e48B725540A3Db24ACF6682a29f877808C53F2
TraderJoe/LFJ v2.2: 0x5AFD3EC861f6104af26e8755aBcc1f876de77620
TraderJoe/LFJ v2.2: 0x5E60BC3F7a7303BC4dfE4dc2220bdC90bc04fE22
```

Important implementation note:

```text
Pancake v3 on Monad uses extended Swap topic
0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83
with seven data words. Parse the first five words like v3 deltas/price/liquidity/tick.

TraderJoe/LFJ v2.2 uses Liquidity Book Swap topic
0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70
and packed bytes32 amount fields. Decode X from the low 128 bits and Y from the high
128 bits; pool base delta > 0 remains sell_base, < 0 remains buy_base.
```

## MON/USDC Enrichment / Tx Body Collector Status

The next executable-strategy path is the 87-day MON/USDC enrichment pass:

```text
raw/pool_swap_logs
  -> raw/tx_bodies
  -> raw/tx_receipt_logs + raw/tx_receipt_log_summaries
  -> derived labels/features
  -> sampled pool state and traces
```

The first optimization was applied to `mon_usdc_tx_body_sample`:

```text
--workers N added; CLI default remains 1
scripts/run_mon_usdc_enrichment.ps1 defaults tx bodies to 4 workers
orchestrator tx body defaults: --batch-size 50 --rpc-batch-size 50
queue cache: data/mon_usdc/v1/_work/mon_usdc_tx_body_queue_v1_<from>_<to>.tsv
each worker owns its own reqwest blocking client and RPC URL rotation state
each completed chunk writes immediately to raw/tx_bodies with unchanged schema
checkpoint now includes workers, queued, written, failed, rows_per_sec, completed_chunks
reruns still dedupe against existing raw/tx_bodies, not only checkpoint state
```

Validation from this engineering pass:

```text
cargo fmt --all --manifest-path Cargo.toml: passed
cargo test -p mon_usdc_collectors -p mon_usdc_research: passed
cargo build --release -p mon_usdc_collectors -p mon_usdc_research: passed
canonical raw/tx_bodies existing files: 331
canonical existing tx body hashes observed in dry-run: 26,000
copied-root RPC smoke 73365455..73366454: 81 tx bodies, 2 parquet parts, 0 failed rows, about 32 rows/sec
copied-root rerun dry-run: queued hashes after dedupe = 0
```

Canonical tx body collection has now resumed with bounded batches:

```text
full-window dry-run 54574468..73366454:
  source swap txs in cache: 1,701,634
  existing tx body hashes before canonical continuation: 26,000
  queued hashes after dedupe: 1,675,634
  queue cache: data/mon_usdc/v1/_work/mon_usdc_tx_body_queue_v1_54574468_73366454.tsv

canonical --max-txs 1000: rows written=1,000, failed=0, rows/sec=107.75, parts=20
canonical --max-txs 10000: rows written=10,000, failed=0, rows/sec=41.87, parts=200
canonical --max-txs 20000: rows written=20,000, failed=0, rows/sec=71.63, parts=401
canonical --max-txs 50000: rows written=50,000, failed=0, rows/sec=79.98, parts=1001
canonical --max-txs 100000: rows written=100,000, failed=0, rows/sec=218.92, parts=2005
canonical --max-txs 250000: rows written=250,000, failed=0, rows/sec=190.83, parts=5015
canonical --max-txs 500000: rows written=500,000, failed=0, rows/sec=155.01, parts=10031
canonical --max-txs 744634: rows written=744,634, failed=0, rows/sec=126.36, parts=14926

latest dry-run after drain:
  source swap txs in cache: 1,701,634
  existing tx body hashes: 1,701,634
  queued hashes after dedupe: 0
  raw/tx_bodies parquet files: 33,930
```

Tx bodies now have full queue coverage for `54574468..73366454`. The next
enrichment continuation should move to `mon_usdc_receipt_log_bundle`; rerun tx
body dry-run only if new swap logs are added or the data root changes.

## Latest Factor Research Status

2026-05-09 also added an event-level, cost-aware factor research layer on top of
`derived/memecoin_event_features`. This is research only, not a trading rule.

New scripts:

```text
scripts/chog_cost_aware_event_factor_research.py
scripts/chog_event_factor_phenomena_analysis.py
```

New reports:

```text
docs/research/chog/2026-05-09-cost-aware-event-factors.md
docs/research/chog/2026-05-09-event-factor-phenomena.md
```

New CSV outputs:

```text
date/chog_event_cost_labels_20260509.csv
date/chog_first_principles_factor_scores_20260509.csv
date/chog_cost_aware_ml_summary_20260509.csv
date/chog_event_factor_phenomena_20260509.csv
date/chog_event_factor_path_profiles_20260509.csv
date/chog_event_factor_daily_concentration_20260509.csv
date/chog_event_factor_untradable_reasons_20260509.csv
```

Current research stance:

```text
Continue event-level, first-principles factor analysis.
Do not start maker/LP/two-sided quoting research unless the user explicitly redirects.
```

Main result:

```text
nad-fun / CHOG-MON is still the core pool, about 95.84% of CHOG volume.
Taker directional labels are heavily constrained by the 2% round-trip main-pool fee.
5m/15m gross edges are too thin after costs.
large_buy_p90 is the clearest candidate phenomenon: a 6h delayed-continuation slice,
with about 2.94% gross and 0.94% net at 0 bps extra slippage, but negative after
100 bps per-side stress.
The positive 6h large-buy result is date-concentrated, especially around 2026-04-10
and 2026-04-24, so it is a candidate phenomenon rather than a robust signal.
Small quote events, low prior activity, and high gas/share-of-notional are now
explicitly marked as untradable/noisy samples.
```

## Current Data Coverage

The current clean, quality-checked memecoin path covers about thirty days:

```text
continuous blocks: 66507947..72992946
approx blocks: 6,485,000
oldest completed day tag: day20260407
```

Closed windows:

```text
day20260407: 66507947..66723946
day20260408: 66723947..66939946
day20260409: 66939947..67155946
day20260410: 67155947..67371946
day20260411: 67371947..67587946
day20260412: 67587947..67803946
day20260413: 67803947..68019946
day20260414: 68019947..68235946
day20260415: 68235947..68451946
day20260416: 68451947..68667946
day20260417: 68667947..68883946
day20260418: 68883947..69099946
day20260419: 69099947..69315946
day20260420: 69315947..69531946
day20260421: 69531947..69747946
day20260422: 69747947..69963946
day20260423: 69963947..70179946
day20260424: 70179947..70395946
day20260425: 70395947..70611946
day20260426: 70611947..70827946
day20260427: 70827947..71043946
day20260428: 71043947..71259946
day20260429: 71259947..71475946
day20260430: 71475947..71691946
day20260501: 71691947..71907946
day20260502: 71907947..72123946
day20260503: 72123947..72339946
day20260504: 72339947..72555946
day20260505: 72555947..72771946
existing verified window: 72771947..72992946
```

Latest successful quality check:

```text
raw.erc20_transfer_logs: rows=47049
raw.main_pool_swap_logs: rows=11207
raw.dex_pool_swap_logs: rows=18795
raw.tx_receipts: rows=15687
raw.event_block_headers: rows=22001
derived.memecoin_event_features: rows=18795
derived.memecoin_hourly_features: rows=2226
quality check passed: files=15719 rows=359208
```

Next historical window if the user asks to continue:

```text
FROM=66291947
TO=66507946
DAY_TAG=day20260406
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

The Windows helper used for the ten-day continuation is:

```text
scripts/run_chog_memecoin_days.ps1
```

It loads `.env.chog.local`, runs 12 log shards/day with max 4 parallel shards, fetches
event headers, drains receipt-only queues, rebuilds memecoin features, removes stale
memecoin derived parts, and runs quality checks. It also supports `-StartPhase` for
resuming a partially completed day; do not blindly rerun completed deterministic log
parts for the same day, because a different `fetched_at` can conflict with existing
Parquet part contents.

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

The latest canonical memecoin derived parts have min block `66509017`.

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

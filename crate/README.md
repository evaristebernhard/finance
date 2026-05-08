# CHOG Prices

Fetch CHOG hourly USD prices on Monad for the recent `7 * 24` hours.

Data source: DeFiLlama coin prices API.

```bash
cargo run --manifest-path crate/Cargo.toml
```

The default output is:

```text
date/chog_prices_7d_1h.csv
```

The CSV always contains exactly one row per hour. DeFiLlama can return sparse raw
price points for small tokens, so the program maps those points to a strict
hourly grid. It also fetches an extra 24 hours before the requested window so
the first row can use an earlier source price when one is available:

- `observed`: the API returned a source price inside that hour.
- `forward_fill`: no source price existed in that hour, so the previous observed
  price was carried forward.
- `back_fill_initial`: only used at the beginning of the window if the first
  source price is after the first requested hour.

Useful options:

```bash
cargo run --manifest-path crate/Cargo.toml -- --hours 168
cargo run --manifest-path crate/Cargo.toml -- --output date/chog_prices_7d_1h.csv
cargo run --manifest-path crate/Cargo.toml -- --coin monad:0x350035555e10d9afaf1566aaebfced5ba6c27777
```

## CHOG v1 RPC log collectors

The CHOG v1 low-frequency on-chain collectors are:

```bash
cargo run --manifest-path crate/Cargo.toml --bin transfer_sample
cargo run --manifest-path crate/Cargo.toml --bin v3_swap_sample
```

Both collectors keep the old default behavior when `--append` and `--resume`
are omitted: they scan the recent `--blocks` window and overwrite the output
CSV. For production data collection, use append + resume:

```bash
cargo run --manifest-path crate/Cargo.toml --bin transfer_sample -- \
  --blocks 20000 \
  --append \
  --resume \
  --output date/chog_transfer_logs_20k_blocks.csv

cargo run --manifest-path crate/Cargo.toml --bin v3_swap_sample -- \
  --blocks 20000 \
  --append \
  --resume \
  --output date/chog_main_pool_swaps_20k_blocks.csv
```

Shared options:

- `--from-block <u64>` explicitly sets the first block and takes priority over
  `--resume` and `--blocks`.
- `--to-block <u64>` explicitly sets the final block. If omitted, the collector
  uses the latest block observed at run start.
- `--resume` starts from `last_completed_block + 1` when the checkpoint exists.
  If there is no checkpoint, it falls back to the recent `--blocks` window.
- `--checkpoint <path>` overrides the checkpoint path. The default is
  `<output>.checkpoint.json`.
- `--append` appends CSV rows and dedupes by
  `(block_number, transaction_hash, log_index)`.

Each successful `eth_getLogs` chunk is written and flushed before the checkpoint
is advanced. The run manifest is appended at `date/chog_collection_runs.csv`.

## CHOG v1 Parquet collection

The formal CHOG v1 data root is:

```text
data/chog/v1/
```

Legacy CSV files under `date/` are left in place as samples. New collection data
is partitioned as:

```text
data/chog/v1/raw/<dataset>/dt=YYYY-MM-DD/*.parquet
data/chog/v1/_checkpoints/<collector>.json
data/chog/v1/_schemas/<dataset>.json
```

Datasets written by the current collectors:

- `main_pool_swap_logs`
- `dex_pool_swap_logs`
- `erc20_transfer_logs`
- `dex_pairs_snapshots`
- `tx_receipts`
- `block_headers`
- `event_block_headers`
- `prices_hourly`
- `collection_runs`

Derived datasets:

- `dex_pool_swap_hourly`
- `dex_swap_factors`
- `memecoin_event_features`
- `memecoin_hourly_features`

Build all collector binaries before using the orchestrator from cron:

```bash
cargo build --manifest-path crate/Cargo.toml --bins
```

For 30-day history, do not run a one-shot `--lookback-days 30` backfill against
the formal data root. Use the
[daily shard runbook](../docs/chog_v1_backfill_runbook.md) and the
[memecoin strategy collection path](../docs/chog_memecoin_collection_strategy.md)
instead.

For a fresh Codex session, start with
[the handoff note](../docs/codex_handoff_memecoin_strategy.md).

The old one-shot backfill form is useful only for dry-runs or very small
isolated smoke roots:

```bash
cargo run --manifest-path crate/Cargo.toml --bin chog_collect -- \
  --mode backfill \
  --lookback-days 30 \
  --data-root /tmp/chog-v1-smoke \
  --dry-run
```

Run one incremental pass:

```bash
cargo run --manifest-path crate/Cargo.toml --bin chog_collect -- \
  --mode incremental \
  --data-root data/chog/v1
```

The incremental command fixes `latest` at run start and passes that block to the
RPC collectors. Transfer and swap collectors resume from their CHOG v1
checkpoints. The default header path is `--header-mode event`, which writes only
headers for local CHOG event blocks to `raw/event_block_headers`. DexScreener
has no historical endpoint, so it only creates append-only snapshots from the
time this collector starts. Receipts are fetched for CHOG pool transaction hashes
by default and use local log timestamps before falling back to event headers or
RPC.

Individual Parquet collector examples:

```bash
cargo run --manifest-path crate/Cargo.toml --bin transfer_sample -- \
  --format parquet --append --resume --data-root data/chog/v1

cargo run --manifest-path crate/Cargo.toml --bin v3_swap_sample -- \
  --format parquet --append --resume --data-root data/chog/v1

cargo run --manifest-path crate/Cargo.toml --bin dex_swap_collect -- \
  --append --resume --data-root data/chog/v1

cargo run --manifest-path crate/Cargo.toml --bin block_header_sample -- \
  --resume --data-root data/chog/v1

cargo run --manifest-path crate/Cargo.toml --bin event_header_sample -- \
  --data-root data/chog/v1 --from-block 100 --to-block 200

cargo run --manifest-path crate/Cargo.toml --bin dex_snapshot -- \
  --format parquet --data-root data/chog/v1

cargo run --manifest-path crate/Cargo.toml --bin receipt_sample -- \
  --from-data-root --source-scope chog-pool-txs --timestamp-source local-first \
  --data-root data/chog/v1

cargo run --manifest-path crate/Cargo.toml -- \
  --format parquet --data-root data/chog/v1 --hours 720
```

Run local Parquet quality checks after a backfill or after at least one day of
incremental runs:

```bash
cargo run --manifest-path crate/Cargo.toml --bin chog_quality_check -- \
  --data-root data/chog/v1
```

Rebuild derived all-pool DEX hourly tables from local Parquet:

```bash
cargo run --manifest-path crate/Cargo.toml --bin dex_rebuild -- \
  --data-root data/chog/v1 hourly
```

Build trade-level DEX factors and a small exploratory factor report. This uses
only local swap logs and treats the next same-pool swap log return as the target:

```bash
cargo run --manifest-path crate/Cargo.toml --bin dex_rebuild -- \
  --data-root data/chog/v1 factors --top 20
```

Use `--dry-run` to inspect planned part paths, or `--json` for a machine-readable
factor report.

Build memecoin strategy event/hourly features from local swap logs, receipts,
and event headers:

```bash
cargo run --manifest-path crate/Cargo.toml --bin dex_rebuild -- \
  --data-root data/chog/v1 memecoin-features
```

Run a basic local analysis report over the current raw and derived data:

```bash
cargo run --manifest-path crate/Cargo.toml --bin chog_analyze -- \
  --data-root data/chog/v1 --top 10
```

Use `--json` when the report should be consumed by another tool.

Operational templates are in `crate/ops/`:

- `chog_collect.cron`: 15-minute cron entry.
- `chog-collect.service` and `chog-collect.timer`: systemd timer pair.

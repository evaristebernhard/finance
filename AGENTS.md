# AGENTS.md

This repo is a private CHOG/Monad data-collection workspace. Read this file first in every new Codex session so the user does not need to restate the current plan.

## Current Goal

Move CHOG v1 collection from full per-block header backfill to a memecoin strategy-first path:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

The latest live handoff is in:

```text
docs/codex_handoff_live_collection_20260508.md
```

The supporting strategy/runbook handoff is in:

```text
docs/codex_handoff_memecoin_strategy.md
docs/chog_memecoin_collection_strategy.md
docs/chog_v1_backfill_runbook.md
```

Start by reading the live handoff and those docs before making changes.

## Important Local Context

- This handoff copy has been running on a stronger Windows machine. If moved back to the Raspberry Pi-class machine, avoid heavy `cargo build --bins`, `cargo test`, or large RPC/data jobs unless the user explicitly asks.
- `cargo test --manifest-path crate/Cargo.toml` passed after the receipt batching/receipt-only optimization.
- `cargo build --manifest-path crate/Cargo.toml --bin receipt_sample` passed after the receipt optimization.
- Local git is intended for categorized checkpoint commits. Keep private `.env*` ignored.
- Current clean memecoin-path coverage is about five days: `71907947..72992946`.
- The user wants self-use zip archives to include local `.env*` and `data/`. Do not assume zips must be sanitized unless the user asks for a shareable package.

## Implemented Code Path

Key files:

```text
crate/src/bin/event_header_sample.rs
crate/src/bin/receipt_sample.rs
crate/src/bin/chog_collect.rs
crate/src/bin/dex_rebuild.rs
crate/src/bin/chog_quality_check.rs
crate/src/memecoin_features.rs
crate/src/lib.rs
```

Implemented behavior:

```text
chog_collect --header-mode event|full|skip
event is default
event_header_sample writes raw/event_block_headers
receipt_sample defaults to --source-scope chog-pool-txs
receipt_sample defaults to --timestamp-source local-first
receipt_sample supports --rpc-batch-size and --receipt-only
dex_rebuild memecoin-features writes derived/memecoin_event_features and derived/memecoin_hourly_features
chog_quality_check includes the new raw/derived datasets
```

## Packaging

There are two package intents:

```text
finance_chain_memecoin_strategy_20260508.zip
```

This earlier package is a small source/docs snapshot and intentionally excludes `data/`, private env files, `.git/`, and `crate/target/`.

For the user's own migration/archive package, create a full handoff zip that includes local `.env*`, `data/`, `date/`, source, docs, scripts, and lightweight root metadata, while excluding:

```text
.git/
crate/target/
existing .zip/.tar/.tar.gz archives
```

Suggested command pattern:

```bash
zip -r finance_chain_full_handoff_YYYYMMDD.zip \
  AGENTS.md crate docs scripts data date \
  .env.local.example .env.chog.local.example .gitignore rpc.txt rpc.monad.capacity.tsv github_monad_alchemy_repos.txt \
  -x 'crate/target/*' '.git/*' '*.zip' '*.tar' '*.tar.gz'
```

If real private env files such as `.env.chog.local` exist, include them only for the user's self-use archive and do not print their contents.

## Next Validation

If changing code, validate with:

```bash
cargo fmt --manifest-path crate/Cargo.toml
cargo test --manifest-path crate/Cargo.toml
```

For the next data continuation, use:

```text
FROM=71691947
TO=71907946
DAY_TAG=day20260501
```

Receipts should usually use `--receipt-only --rpc-batch-size 50` for memecoin feature collection unless the user needs transaction body fields.

## Safety

- Do not print private RPC keys, env contents, OpenAI tokens, or browser session JSON.
- Do not delete `data/` or existing archives unless the user explicitly asks.
- Do not run destructive Git commands.
- Preserve existing user data and local generated datasets.

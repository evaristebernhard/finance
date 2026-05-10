# AGENTS.md

This repo is a private CHOG/Monad data-collection workspace. Read this file first in every new Codex session so the user does not need to restate the current plan.

## Current Goal

Move CHOG v1 collection from full per-block header backfill to a memecoin strategy-first path:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

The latest live handoff is in:

```text
docs/handoff/live-collection.md
```

The supporting strategy/runbook handoff is in:

```text
docs/handoff/memecoin-strategy.md
docs/runbooks/chog-memecoin-collection.md
docs/runbooks/chog-v1-backfill.md
```

The human-readable docs index is in `docs/README.md`. Start by reading the live handoff and those docs before making changes.

## Important Local Context

- This handoff copy has been running on a stronger Windows machine. If moved back to the Raspberry Pi-class machine, avoid heavy `cargo build --bins`, `cargo test`, or large RPC/data jobs unless the user explicitly asks.
- `cargo test --manifest-path crate/Cargo.toml` passed after the receipt batching/receipt-only optimization.
- `cargo build --manifest-path crate/Cargo.toml --bin receipt_sample` passed after the receipt optimization.
- Local git is intended for categorized checkpoint commits. Keep private `.env*` ignored.
- Current clean memecoin-path coverage is about thirty days: `66507947..72992946`.
- Latest event-factor research artifacts are:
  - `docs/research/chog/2026-05-09-cost-aware-event-factors.md`
  - `docs/research/chog/2026-05-09-event-factor-phenomena.md`
  - `date/chog_event_cost_labels_20260509.csv`
  - `date/chog_first_principles_factor_scores_20260509.csv`
  - `date/chog_cost_aware_ml_summary_20260509.csv`
  - `date/chog_event_factor_phenomena_20260509.csv`
  - `date/chog_event_factor_path_profiles_20260509.csv`
  - `date/chog_event_factor_daily_concentration_20260509.csv`
  - `date/chog_event_factor_untradable_reasons_20260509.csv`
- Current factor-research stance: continue event-level, first-principles factor analysis; do not start maker/LP/two-sided quoting research unless the user explicitly redirects. The main observed phenomenon is `large_buy_p90` as a 6h delayed-continuation candidate, not an immediate trading rule.
- Latest user direction: pivot executable strategy research toward MON/USDC instead of CHOG because CHOG liquidity is too small. The first Python sampler remains at `scripts/mon_usdc_v1_swap_sample.py`, and a Rust V1 collector path now exists in `crates/mon_usdc_collectors`.
- Latest MON/USDC v1 artifacts:
  - `docs/markets/mon-usdc/v1-data-plan.md`
  - `docs/markets/mon-usdc/v1-factor-analysis.md`
  - `date/mon_usdc_pool_candidates_20260509.csv`
  - `date/mon_usdc_v1_swaps_sample_20260509.csv`
  - `data/mon_usdc/v1/raw/pool_snapshots`
  - `data/mon_usdc/v1/raw/pool_swap_logs`
  - `data/mon_usdc/v1/raw/event_block_headers`
  - `data/mon_usdc/v1/raw/tx_receipts`
  - Initial top pools: Uniswap v3 `0x659bD0BC4167BA25c62E05656F78043E7eD4a9da`, Pancake v3 `0x63e48B725540A3Db24ACF6682a29f877808C53F2`, TraderJoe v2.2 `0x5AFD3EC861f6104af26e8755aBcc1f876de77620`, and TraderJoe v2.2 `0x5E60BC3F7a7303BC4dfE4dc2220bdC90bc04fE22`.
  - Pancake v3 on Monad uses an extended Swap topic `0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83`, not the standard Uniswap v3 Swap topic.
  - TraderJoe/LFJ v2.2 uses Liquidity Book metadata (`getTokenX()` / `getTokenY()`) and Swap topic `0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70`; `bytes32` amounts are decoded as X in the low 128 bits and Y in the high 128 bits.
  - Latest range-scoped Rust MON/USDC result completed `54574455..60190454`: `pool_swap_logs=634009`, `event_block_headers=383994`, `tx_receipts=493760`, `missing_event_headers=0`, `missing_receipts=0`, and `mon_usdc_quality_check` passed with `files=33013 rows=1511798`. An earlier `592099` swap-row estimate was superseded by the local range-scoped quality result `634009`.
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
scripts/run_chog_memecoin_days.ps1
Cargo.toml
crates/finance_chain_core
crates/mon_usdc_collectors
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
target/
existing .zip/.tar/.tar.gz archives
```

Suggested command pattern:

```bash
zip -r finance_chain_full_handoff_YYYYMMDD.zip \
  AGENTS.md Cargo.toml crate crates docs scripts data date \
  .env.local.example .env.chog.local.example .gitignore rpc.txt rpc.monad.capacity.tsv github_monad_alchemy_repos.txt \
  -x 'crate/target/*' 'target/*' '.git/*' '*.zip' '*.tar' '*.tar.gz'
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
FROM=66291947
TO=66507946
DAY_TAG=day20260406
```

Receipts should usually use `--receipt-only --rpc-batch-size 50` for memecoin feature collection unless the user needs transaction body fields.

## Safety

- Do not print private RPC keys, env contents, OpenAI tokens, or browser session JSON.
- Do not delete `data/` or existing archives unless the user explicitly asks.
- Do not run destructive Git commands.
- Preserve existing user data and local generated datasets.

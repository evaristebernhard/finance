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

The human-readable docs index is in `docs/README.md`. Start there when the task is documentation or orientation.

## Documentation Organization Note

Latest documentation direction from the user: keep frontend/backend engineering,
historical research, and factor analysis separated. For BONK UI/API work, start
with:

```text
docs/engineering/README.md
docs/markets/bonk/v1-replay-workbench.md
docs/markets/bonk/README.md
```

For factor research, start with:

```text
docs/research/README.md
```

Treat older CHOG and MON/USDC handoffs as collection/research references unless
the user explicitly asks to continue those data paths.

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
  - `docs/markets/mon-usdc/v1-enrichment-report.md`
  - `date/mon_usdc_pool_candidates_20260509.csv`
  - `date/mon_usdc_v1_swaps_sample_20260509.csv`
  - `data/mon_usdc/v1/raw/pool_snapshots`
  - `data/mon_usdc/v1/raw/pool_swap_logs`
  - `data/mon_usdc/v1/raw/event_block_headers`
  - `data/mon_usdc/v1/raw/tx_receipts`
  - `data/mon_usdc/v1/raw/tx_bodies`
  - `data/mon_usdc/v1/_work`
  - Initial top pools: Uniswap v3 `0x659bD0BC4167BA25c62E05656F78043E7eD4a9da`, Pancake v3 `0x63e48B725540A3Db24ACF6682a29f877808C53F2`, TraderJoe v2.2 `0x5AFD3EC861f6104af26e8755aBcc1f876de77620`, and TraderJoe v2.2 `0x5E60BC3F7a7303BC4dfE4dc2220bdC90bc04fE22`.
  - Pancake v3 on Monad uses an extended Swap topic `0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83`, not the standard Uniswap v3 Swap topic.
  - TraderJoe/LFJ v2.2 uses Liquidity Book metadata (`getTokenX()` / `getTokenY()`) and Swap topic `0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70`; `bytes32` amounts are decoded as X in the low 128 bits and Y in the high 128 bits.
  - Latest range-scoped Rust MON/USDC result completed `54574455..60190454`: `pool_swap_logs=634009`, `event_block_headers=383994`, `tx_receipts=493760`, `missing_event_headers=0`, `missing_receipts=0`, and `mon_usdc_quality_check` passed with `files=33013 rows=1511798`. An earlier `592099` swap-row estimate was superseded by the local range-scoped quality result `634009`.
- MON/USDC tx body collector engineering status:
  - `mon_usdc_tx_body_sample` now supports `--workers`; CLI default is `1`.
  - `scripts/run_mon_usdc_enrichment.ps1` defaults tx bodies to `--workers 4 --batch-size 50 --rpc-batch-size 50`.
  - Queue cache lives in `data/mon_usdc/v1/_work/mon_usdc_tx_body_queue_v1_<from>_<to>.tsv`.
  - Full-window dry-run for `54574468..73366454` now succeeds using the compact TSV queue cache: `source swap txs=1701634`.
  - Canonical `raw/tx_bodies` is drained for the full `54574468..73366454` queue: all bounded batches plus `--max-txs 744634` completed with `0` failed rows.
  - Latest dry-run after drain: `source swap txs=1701634`, `existing tx body hashes=1701634`, `queued hashes after dedupe=0`, `raw/tx_bodies parquet files=33930`.
  - Validation passed: `cargo fmt --all --manifest-path Cargo.toml`, `cargo test -p mon_usdc_collectors -p mon_usdc_research`, and `cargo build --release -p mon_usdc_collectors -p mon_usdc_research`.
  - Copied-root RPC smoke for `73365455..73366454` wrote 81 tx bodies into `target/tmp`, 2 parquet parts, 0 failed rows, about 32 rows/sec, and rerun dry-run queued 0.
  - Next enrichment continuation should move to `mon_usdc_receipt_log_bundle`; tx bodies no longer need more collection for this window unless new swap logs are added.
- Latest CCUSDT/CEX L2 V1 TFI strategy-optimization status:
  - Start with `docs/markets/ccusdt/v1-current-tfi-strategy-handoff-20260518.md`.
  - This is the active CCUSDT branch from the latest conversation; it supersedes the older v2 execution no-go framing for current TFI strategy work unless the user explicitly redirects back to v2.
  - Current model family:
    - `A_t = 1{R5 > 1}` where `R5` uses only entries already closed before the current entry.
    - `B_t = 1{frames_since_mid_change >= q90}`.
    - Four mutually exclusive cells: `00`, `10`, `01`, `11`.
    - Final size: `w_t = b_t * gamma_{A_tB_t} * psi_t * phi_t`.
    - `R5` is only a shape ratio; decompose it into `Delta_k=P_k-N_k`, `E_k=P_k+N_k`, and `Z_k=Delta_k/sqrt(E_k+eps)`.
  - Do not discard states only because `net_median < 0`; net median is already cost-adjusted and this branch is right-tail/left-tail-control oriented.
  - Latest interpretable grid/Pareto search tested `16960` candidates with prior-date quantile thresholds only:
    - Old anchor `gamma10=0.75`, `gamma01=0.25`, `gamma11=4`: total `6808.4686`, mean `4.4171bps`, worst day `-58.2736`, positive days `8/9`.
    - Pareto/risk-score leader `gamma10=1.25`, `gamma01=0.75`, `gamma11=5`, with `closed10_score_abs >= Q30_train`: total `9001.3476`, mean `5.0248bps`, worst day `+12.8156`, positive days `9/9`.
    - More conservative point `gamma10=1.25`, `gamma01=0.25`, `gamma11=5`, same strength gate: total `8819.5895`, mean `5.0372bps`, worst day `+23.5851`, positive days `9/9`.
    - No-strength high-gamma point has total `9123.4940` but worst day `-167.3131`, so absolute-strength gating is structural.
  - Latest scripts:
    - `scripts/ccusdt_v1_tfi_interpretable_grid_pareto.py`
    - `scripts/ccusdt_v1_tfi_worst_day_frontier.py`
    - `scripts/ccusdt_v1_tfi_strategy_sizing_opt.py`
    - `scripts/ccusdt_v1_tfi_pretrade_identification.py`
    - `scripts/ccusdt_v1_tfi_momentum_conversion_math.py`
  - Latest reports:
    - `docs/markets/ccusdt/v1-tfi-interpretable-grid-pareto-20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.md`
    - `docs/markets/ccusdt/v1-tfi-worst-day-frontier-20260518_ccusdt_v1_tfi_worst_day_frontier_v1.md`
    - `docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.md`
  - Important caveat: the daily Pareto leader has a larger single-entry left tail (`entry_worst_pnl` about `-311.1463`); next work should add a single-entry risk cap and test new OOS days before live use.
- Latest CCUSDT/CEX L2 V2 execution-research status:
  - Start with `docs/markets/ccusdt/v2-current-execution-no-go-handoff.md`.
  - Current active objective is not achieved: the framework is systematized, but stable real-cost `>2bps` capture is not present.
  - Key docs:
    - `docs/markets/ccusdt/v2-executable-research-framework.md`
    - `docs/markets/ccusdt/v2-goal-completion-audit-20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.md`
    - `docs/markets/ccusdt/v2-l2-queue-fill-20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.md`
    - `docs/markets/ccusdt/v2-taker-fallback-audit-20260518_ccusdt_v2_taker_fallback_audit_v1.md`
    - `docs/markets/ccusdt/v2-execution-failure-decomposition-20260518_ccusdt_v2_execution_failure_decomp_v1.md`
    - `docs/markets/ccusdt/v2-structural-pivot-proposals-20260518.md`
    - `docs/markets/ccusdt/v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_fast_v1.md`
    - `docs/markets/ccusdt/v2-liquidity-envelope-audit-20260518_ccusdt_v2_liquidity_envelope_audit_v1.md`
    - `docs/markets/ccusdt/v2-local-universe-inventory-20260518_ccusdt_v2_local_universe_inventory_v1.md`
    - `docs/markets/ccusdt/v2-universe-preflight-20260518_ccusdt_v2_universe_preflight_v1.md`
    - `docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_smoke_v1.md`
    - `docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_small_tier_v1.md`
  - Hard no-go evidence:
    - Framework scorecard: `0` promoted rows; `4` research-continue rows only.
    - All-practical L2 queue fill: `45/45` framework bins no-go over `6447` validation entries.
    - Fill-aware repair scan: `0/3741` post-hoc filters pass execution gates.
    - Taker fallback: `45/45` bins no-go; `0` taker promote-gate rows.
    - Execution decomposition: best maker per-signal net is `-0.0038bps` versus the `2bps` target.
    - Queue-release pivot prototype: `0/24` rows pass; best mean is `-1.7573bps`.
    - Liquidity-envelope audit: `liquidity_envelope_no_go`; median daily median spread is `2.0148bps`; `0/17` days pass `$100` top-depth support.
    - Local Bullish L2 universe inventory: `single_or_no_symbol_only`; only `CCUSDT` is local core L2-ready, so universe selection is data-blocked locally.
    - Bullish universe preflight dry-run: `11` metadata-available scheduled symbols, `3` missing requested symbols, `561` planned file jobs, no files downloaded.
    - Bullish universe size smoke: first date `33/33` planned files available, estimated `3.61GB`; full universe data step should be staged deliberately.
    - Small-tier universe size probe: `SUIUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC` full-window core L2 totals about `0.40GB`; `SUIUSDC`/`DOGEUSDC` are the practical pilot candidates, while `PEPE/SHIB/WIF` look near-empty and need row validation.
  - Do not continue CCUSDT by tuning TP/SL grids, narrowing post-hoc filters, or switching maker/taker assumptions on the same candidates. Only resume if new out-of-sample days, real venue fee/fill/latency evidence, a structurally different signal, or a broader instrument universe is introduced.
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

# Finance Chain Docs

Human-readable docs entry point. In a fresh Codex session, read [AGENTS.md](../AGENTS.md) first, then use this page to choose the right lane.

## Frontend / Backend

- [Engineering docs](engineering/README.md): generic market replay backend, frontend, endpoints, local AI proxy, and data inputs.
- [CCUSDT replay workbench](markets/ccusdt/v1-replay-workbench.md): default product/runbook doc for the local replay UI and Rust API.
- [BONK replay workbench](markets/bonk/v1-replay-workbench.md): older BONK market wiring kept as a selectable replay surface.

## Factor Analysis

- [Research docs](research/README.md): factor-analysis index split across BONK, MON/USDC, and CHOG.
- [BONK research index](markets/bonk/README.md): current BONK docs grouped by engineering, factor analysis, and historical research.
- [MON/USDC research index](markets/mon-usdc/README.md): prior Monad DEX/on-chain factor and enrichment line.

## Historical Research

- [BONK legacy V1/V6/V7/V8/V9 docs](markets/bonk/archive/2026-05-13-to-14-legacy-cex-v1-v9/README.md)
- [BONK archived V3/V4/V5 research waves](markets/bonk/archive/2026-05-13-research-waves/README.md)
- [CHOG early research archive](research/README.md#historical-research)
- [Workspace archive index](../archive/README.md)

## Data Collection Runbooks

- [Live collection status](handoff/live-collection.md): older CHOG/MON handoff and collector status.
- [Memecoin strategy handoff](handoff/memecoin-strategy.md): CHOG strategy-first path and implementation notes.
- [CHOG memecoin collection](runbooks/chog-memecoin-collection.md): event-driven `logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check`.
- [CHOG v1 backfill](runbooks/chog-v1-backfill.md): day-window operating runbook and full-header escape path.

## Market Indexes

- [Market research index](markets/README.md)
- [CCUSDT](markets/ccusdt/README.md)
- [BONK](markets/bonk/README.md)
- [MON/USDC](markets/mon-usdc/README.md)
- [BTC/ETH options sample](markets/btc/v1-options-regime-report.md)

## Reference

- [Workspace cleanup map](handoff/workspace-cleanup-20260519.md): current dirty-worktree domain map and suggested checkpoint buckets.
- [CHOG data inventory](reference/chog-data-inventory.md)
- [Monad RPC probe](reference/monad-rpc-probe.md)
- [date output policy](../date/README.md)
- [Generated-output cleanup manifest](../archive/archive_manifest_2026-05-15_cleanup.csv)

# MON/USDC V1 Research Index

Status: 2026-05-16. MON/USDC is an earlier Monad DEX/on-chain research line. Keep these reports available for enrichment, factor-map, and path-regime reference; current frontend/backend engineering docs are under [engineering](../../engineering/README.md). Reports here are research diagnostics, not trading rules or execution instructions.

## Start Here

- [V1 data plan](v1-data-plan.md): pool set, raw data layout, Rust collector path, and enrichment plan.
- [V1 enrichment report](v1-enrichment-report.md): `20260511_reconstruct_v1` coverage, receipt-log bundle coverage, derived paths, pool-state samples, and trace samples.
- [V1 factor map](v1-factor-map.md): gross factor families, tradability diagnostics, and split-aware factor evaluation.
- [V1 path-regime report](v1-path-regime-report.md): path/barrier sensitivity built from the reconstructed execution panel.
- [V1.5 Binance order book dynamics](v1-cex-orderbook-report.md): CEX orderbook/trade-flow context joined to DEX events.

## Collection And Enrichment

- [V1 data plan](v1-data-plan.md): fixed top pools, collector commands, and data-root conventions.
- [V1 enrichment report](v1-enrichment-report.md): tx bodies, receipt log bundles, derived execution panel, pool state, and traces.
- [Live order book collector](v1-live-orderbook-collector.md): local Binance L2 collector notes and strict L2 mode.
- [Tardis access notes](v1-tardis-access.md): API-key status and historical L2 access constraints.

## Factor And Path Research

- [V1 factor analysis](v1-factor-analysis.md): 86-87 day raw coverage, gross forward return single-factor study.
- [V1 math factor design](v1-math-factor-design.md): path labels, triple-barrier framing, tradability-first factor families.
- [V1 factor expression search](v1-factor-expression-search.md): expression-search run from `20260511_reconstruct_v1`.
- [V1 factor map](v1-factor-map.md): factor-family map and cost/tradability diagnostics.
- [V1 path-regime report](v1-path-regime-report.md): path-regime and barrier readout.

## CEX Context

- [V1 CEX dynamics](v1-cex-dynamics-report.md): Binance futures market-state and reference lag context.
- [V1.5 order book dynamics](v1-cex-orderbook-report.md): bookDepth/aggTrades coverage and joined DEX-CEX panel.

## Current Data Notes

- Fixed top pools: Uniswap v3, Pancake v3, and two TraderJoe/LFJ v2.2 MON/USDC pools.
- Pancake v3 on Monad uses extended Swap topic `0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83`.
- TraderJoe/LFJ v2.2 uses Liquidity Book metadata and Swap topic `0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70`.
- Full-window tx bodies for `54574468..73366454` were drained in the canonical `raw/tx_bodies` queue; if new swap logs are added, rerun dry-run before any continuation.

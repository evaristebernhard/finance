# BONK Docs Index

Status: 2026-05-16. BONK docs are split into frontend/backend engineering, factor-analysis diagnostics, and historical research. Everything here is research or local tooling, not a trading rule, execution instruction, sizing rule, or alpha claim.

## Frontend / Backend

- [BONK replay workbench](v1-replay-workbench.md): older BONK market wiring for manual replay, book-state price/order-book inspection, factor drilldowns, local AI commentary, and simulated orders.
- [Engineering docs](../../engineering/README.md): generic market replay backend/frontend run commands, file map, endpoints, local AI proxy, and data inputs. CCUSDT is now the default market.

Key local files:

```text
backend/Cargo.toml
backend/src/main.rs
frontend/package.json
frontend/components/ReplayWorkbench.tsx
frontend/lib/api.ts
frontend/lib/types.ts
frontend/app/api/local-ai/route.ts
```

## Factor Analysis

Read these when continuing research on factor behavior, validation failures, path diagnostics, or UI-side factor inspection.

- [Replay workbench factor inspector](v1-replay-workbench.md): local factor board, lead/lag correlations, scatter, normalized overlays, LaTeX formulas, and stale-source caveats.
- [Tardis Bullish volatility symbol screen](../../research/bonk/2026-05-16-tardis-bullish-volatility-symbol-screen.md): candidate selection by realized volatility, range, spread, and price scale.
- [V10c event-defined OFI/MLOFI](v1-cex-v10c-event-defined-ofi-mlofi.md): event panel construction, MLOFI/queue diagnostics, and factor validation.
- [V10 dynamic orderbook analysis](v1-cex-v10-dynamic-orderbook-analysis.md): dynamic data quality, orderbook state, and path diagnostics.
- [V10b path-conditioned dynamic factor mining](v1-cex-v10b-path-conditioned-dynamic-factor-mining.md): path-conditioned feature mining and stability checks.
- [V11 trade-flow edge audit](v1-cex-v11-trade-flow-edge-audit.md): trade-flow side semantics, sparse anchors, after-cost audit, and controls.
- [V12 pending entry baseline](v1-cex-v12-pending-entry-adaptive-tpsl.md): frozen-marker baseline kept as a comparator.
- [V13 dynamic marker / vol wings](v1-cex-v13-dynamic-marker-vol-wings.md): dynamic-marker run, mechanics fixed from V12, and negative controls.
- [V14 state policy](v1-cex-v14-state-policy.md): hard-failed state-policy run with zero validation setups.
- [V15 structural pivot plan](v1-cex-v15-structural-pivot-plan.md): pivot diagnosis after V14.
- [V15A shadow acceptance surface](v1-cex-v15a-shadow-acceptance-surface.md): non-entry diagnostic separating mechanical collapse from weak-after-cost states.
- [V15 native order-wall microstructure](v1-cex-v15-native-order-wall-analysis.md): native order-wall diagnostics and controls.
- [V15 Longbridge-style microstructure](v1-cex-v15-longbridge-microstructure-analysis.md): spread, liquidity, wall, and order-flow pressure readout.
- [V15 technical-analysis skill report](v1-cex-v15-technical-analysis-skill-report.md): classical technical-analysis diagnostics as a research lens.
- [V15 Fibonacci / RSI / book levels](v1-cex-v15-fibonacci-rsi-book-levels.md): level diagnostics and plots.

## Historical Research

- [V10 reconstruction and path report](v1-cex-v10-reconstruction-and-path-report.md): canonical V10 stage-1 replay inventory and reconstruction status.
- [V10 data spec and reconstruction plan](../../research/bonk/v10-data-spec-and-reconstruction-plan.md): reconstruction rules, artifact expectations, and continuation notes.
- [Legacy CEX V1/V6/V7/V8/V9 docs](archive/2026-05-13-to-14-legacy-cex-v1-v9/README.md): older root-level BONK docs moved out of the active index.
- [Archived V3/V4/V5 research waves](archive/2026-05-13-research-waves/README.md): earlier exploratory diagnostics already archived.

## Active Outputs

The compatibility output root is still `date/` because existing Rust and Python tools default there. Treat it as a working output directory, not a long-term archive. Current BONK files intentionally kept in `date/` include:

```text
bonk_v10_*_20260514_bonk_v10_stage1_pilot.*
bonk_v10b_path_conditioned_*_20260514_bonk_v10_stage1_pilot.*
bonk_v10c_event_ofi_*_20260514_bonk_v10_stage1_pilot.*
bonk_v11_trade_flow_*_20260514_bonk_v10_stage1_pilot.*
bonk_v12_pending_entry_*_20260514_bonk_v10_stage1_pilot.*
bonk_v13_dynamic_marker_*_20260514_bonk_v10_stage1_pilot.*
bonk_v14_state_policy_*_20260514_bonk_v10_stage1_pilot.*
bonk_v15_*_20260515_bonk_v10_stage1_pilot.*
```

See [date README](../../../date/README.md) and [archive manifest](../../../archive/archive_manifest_2026-05-15_cleanup.csv) for cleanup/archive policy.

## Current Read

The workbench is the engineering surface for inspecting the fixed V10 stage-1 pilot. The factor/research read remains cautious: V13 fixed several mechanics from V12, but the signal layer was still too weak after costs and controls. V15A then showed the frozen validation acceptance surface mechanically collapsing before entry selection. Use the UI to inspect and understand factor behavior; do not promote factor flashes to strategy rules without after-cost validation, controls, sample size, and out-of-sample evidence.

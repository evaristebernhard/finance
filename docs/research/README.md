# Research Docs

Status: 2026-05-16. This page separates current factor-analysis material from historical research and archives.

## Factor Analysis

### BONK

- [BONK replay workbench factor inspector](../markets/bonk/v1-replay-workbench.md): UI-side factor inspection, local correlations, lead/lag tables, LaTeX formulas, and source caveats.
- [Tardis Bullish volatility symbol screen](bonk/2026-05-16-tardis-bullish-volatility-symbol-screen.md): short-horizon candidate selection by realized volatility, range, spread, and price scale.
- [V10c event-defined OFI/MLOFI](../markets/bonk/v1-cex-v10c-event-defined-ofi-mlofi.md): event panel, OFI/MLOFI/queue diagnostics, and factor validation.
- [V10 dynamic orderbook analysis](../markets/bonk/v1-cex-v10-dynamic-orderbook-analysis.md): data quality, orderbook state, and path diagnostics.
- [V10b path-conditioned dynamic factor mining](../markets/bonk/v1-cex-v10b-path-conditioned-dynamic-factor-mining.md): path-conditioned feature mining and stability checks.
- [V11 trade-flow edge audit](../markets/bonk/v1-cex-v11-trade-flow-edge-audit.md): trade-flow side semantics, sparse anchors, controls, and after-cost read.
- [V13 dynamic marker / vol wings](../markets/bonk/v1-cex-v13-dynamic-marker-vol-wings.md): dynamic-marker mechanics and negative controls.
- [V14 state policy](../markets/bonk/v1-cex-v14-state-policy.md): hard-failed state-policy run kept as a failure reference.
- [V15 structural pivot plan](../markets/bonk/v1-cex-v15-structural-pivot-plan.md): pivot diagnosis after V14.
- [V15A shadow acceptance surface](../markets/bonk/v1-cex-v15a-shadow-acceptance-surface.md): validation acceptance collapse and weak-after-cost split.
- [V15 native order-wall microstructure](../markets/bonk/v1-cex-v15-native-order-wall-analysis.md): native order-wall diagnostics.
- [V15 Longbridge-style microstructure](../markets/bonk/v1-cex-v15-longbridge-microstructure-analysis.md): spread, liquidity, order-flow pressure, and wall readout.
- [V15 technical-analysis skill report](../markets/bonk/v1-cex-v15-technical-analysis-skill-report.md): technical-analysis lens over the replay artifacts.
- [V15 Fibonacci / RSI / book levels](../markets/bonk/v1-cex-v15-fibonacci-rsi-book-levels.md): level diagnostics and control plots.

### MON/USDC

- [V1 factor analysis](../markets/mon-usdc/v1-factor-analysis.md): 86-87 day raw coverage and gross forward return single-factor study.
- [V1 math factor design](../markets/mon-usdc/v1-math-factor-design.md): path labels, triple barriers, and tradability-first factor families.
- [V1 factor expression search](../markets/mon-usdc/v1-factor-expression-search.md): expression-search run from `20260511_reconstruct_v1`.
- [V1 factor map](../markets/mon-usdc/v1-factor-map.md): factor-family map and cost/tradability diagnostics.
- [V1 path-regime report](../markets/mon-usdc/v1-path-regime-report.md): path-regime and barrier readout.

### CCUSDT

- [V1 signal path math](../markets/ccusdt/v1-signal-path-math.md): trigger taxonomy, cost-threshold crossing, MFE/MAE, controls, and targeted barrier increment decomposition.
- [V1 strategy research overlay](../markets/ccusdt/v1-strategy-research.md): toy replay strategy conversion of CCUSDT factor opportunities with walk-forward folds, cost stress, stale/event filters, and controls.
- [V1 factor method sweep](../markets/ccusdt/v1-factor-method-sweep.md): Bullish/Tardis snapshot-frame factor diagnostics across event/time labels, IC/AUC/MI, controls, and model checks.
- [V1 fixed event-orderbook factors v3](../markets/ccusdt/v1-fixed-event-orderbook-factors-v3.md): corrected fixed OFI/MLOFI factor panel and path diagnostics.

### CHOG

- [2026-05-09 cost-aware event factors](chog/2026-05-09-cost-aware-event-factors.md)
- [2026-05-09 event factor phenomena](chog/2026-05-09-event-factor-phenomena.md)
- [2026-05-08 factor decomposition v2](chog/2026-05-08-factor-decomposition-v2.md)
- [2026-05-08 ML factor analysis](chog/2026-05-08-ml-factor-analysis.md)
- [2026-05-08 supervised factor research](chog/2026-05-08-supervised-factor-research.md)

## Historical Research

- [BONK legacy CEX V1/V6/V7/V8/V9 docs](../markets/bonk/archive/2026-05-13-to-14-legacy-cex-v1-v9/README.md)
- [BONK archived V3/V4/V5 research waves](../markets/bonk/archive/2026-05-13-research-waves/README.md)
- [BONK V10 data spec and reconstruction plan](bonk/v10-data-spec-and-reconstruction-plan.md)
- [CHOG memecoin first analysis](chog/2026-05-08-memecoin-first-analysis.md)
- [CHOG early extended data analysis](chog/archive/early-extended-data-analysis.md)
- [CHOG early main pool swap analysis](chog/archive/early-main-pool-swap-analysis.md)
- [CHOG early onchain math analysis](chog/archive/early-onchain-math-analysis.md)
- [CHOG early preliminary factor analysis](chog/archive/early-preliminary-factor-analysis.md)
- [CHOG external absorption framework](chog/framework/external-absorption-plan.md)

## Output Archives

- [Workspace archive index](../../archive/README.md)
- [Generated-output cleanup manifest](../../archive/archive_manifest_2026-05-15_cleanup.csv)
- [date output policy](../../date/README.md)

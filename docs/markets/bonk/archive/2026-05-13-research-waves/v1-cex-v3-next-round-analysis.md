# BONK V3 Next-Round Parallel Analysis

Status: 2026-05-13. This memo summarizes the second parallel analysis round over `20260513_bullish_l2_basket_price_v1`. It is not a trading rule, not an execution plan, and not an alpha claim.

## Outputs Reviewed

```text
docs/markets/bonk/v1-cex-v3-negative-controls.md
docs/markets/bonk/v1-cex-v3-threshold-drift.md
docs/markets/bonk/v1-cex-v3-gated-ranking.md
docs/markets/bonk/v1-cex-v3-factor-ic-decay.md
docs/markets/bonk/v1-cex-v3-cross-section-placebo.md
docs/markets/bonk/v1-cex-v3-gross-edge.md
docs/markets/bonk/v1-cex-v3-short-horizon-probe.md
docs/markets/bonk/v1-cex-v3-leakage-audit.md
```

## Main Read

The strongest current object is still a BONK1MUSDT H4 state, not a polished model:

```text
depth_high + rv_low
depth_high + rv_low + cv_spread
```

The newer checks make the interpretation sharper and more cautious. The state has real-looking residual/path behavior and survives rough cost math on paper, but it fails enough negative controls that it should be treated as a slow regime candidate rather than a precise microstructure timing signal.

## What Got Stronger

Cross-section is supportive. The raw `depth_high+rv_low` state is not unique to BONK, but after meme-basket adjustment BONK is the only full-coverage target with positive relative-meme median return in the primary gate. BONK1MUSDT H4 shows `23.5 bps` median return, `+8.8 bps` relative to meme basket, and `+9.0%` upper-minus-lower. DOGE has strong raw upper-minus-lower at `+9.7%`, but not positive versus meme basket.

Gross edge is not instantly killed by spread. H4 `depth_high+rv_low+cv_spread` shows about `38.9 bps` gross median and `33.6 bps` after a rough `1x spread + 2 bps fee + small slippage` stress. H4 `depth_high+rv_low` shows about `21.4 bps` gross and `17.8 bps` stress net. H1 is mostly spread-fragile.

Spearman/IC finally adds useful texture. The strongest robust rank diagnostics are not exotic: H1 `ctx_bonk_rv_1h_bps` ranks path width with IC around `0.38`, H4 `spread_bps_median` ranks future residual return around `0.30`, and low RV ranks H4 residual return negatively around `-0.28`. Depth IC decays from about `0.14` at lag 0 to `0.03` at 60m, which is more like a fading state signal than permanent drift.

Short horizon is feasible without new raw data. Existing L2 state and Binance kline context can derive 5m/15m/30m labels with strong coverage. For 5m, 100bps is too wide; 20/30bps barriers are the right microstructure-decay probe.

## What Got Weaker

Negative controls are the biggest blocker. On fold2/fold3, BONK1MUSDT H4 `depth_high+rv_low` has `11.7%` residual edge but does not beat random phase p95 (`27.4%`). The `depth_high+rv_low+cv_spread` gate has `20.6%` residual edge, but effective selected count is only `3`. Several 240m/720m time-shift controls match or beat the actual gates, pointing to slow regime persistence.

Threshold drift is large. BONK1MUSDT H4 `depth_high+rv_low` validation share jumps from `1.6%` in fold2 to `16.3%` in fold3 while residual edge fades from `30.2%` to `10.2%`. The cv-spread combo jumps from `0.7%` to `10.9%`. This explains why generic trees can reject the hand gate: the same frozen threshold selects different regimes across folds.

Gate-internal modeling is not ready. Shallow LightGBM/XGBoost, logistic/ridge heads, and raw heuristics do not beat the gate-only baseline under strict fold2/fold3 phase-rotated H4 diagnostics. The model layer is currently weaker than the state definition.

Leakage audit found no direct future/label predictor leak, and train-only thresholds are verified, but it did find a label-quality issue: `future_return_bps` can drift from exact `t+horizon` when L2 minutes are missing. The path labels should be rebuilt or audited with timestamp-exact endpoint semantics before leaning on exact future-return IC or gross-return numbers.

## Working Interpretation

The current candidate is a BONK relative-strength state inside a quiet/high-depth market regime. It is probably not a fast, standalone L2 alpha. The plausible story is:

- High depth means the venue can absorb or reveal interest without immediately widening.
- Low BONK RV marks a quieter state where lower-first path risk is suppressed.
- Cross-venue spread adds a state filter that improves fold3 residual and lower-first behavior.
- The same ingredients are partly common-mode, so meme/market controls are mandatory.

This is still useful. Short-half-life factors do not need to be eternal; they need a reason, a target, and controls. Here the reason is plausible, but the current evidence says the right next object is a frozen-state retest plus short-horizon labels, not a heavier global model.

## Next Experiments

1. Rebuild path labels with timestamp-exact horizon endpoints and rerun the key IC/gross-edge checks.
2. Add 5m/15m/30m labels with 20/30bps barriers; test whether spread/depth/cross-venue effects decay quickly.
3. Freeze H4 USDT `depth_high+rv_low` and `depth_high+rv_low+cv_spread` as state candidates, but require negative-control pass before promotion.
4. Keep cross-section placebo mandatory: BONK must stay positive relative to meme basket, not just raw positive.
5. Stop adding second-stage gate-internal ML until the manual gate beats negative controls or more windows are available.
6. Use Spearman IC as a ranking lens, but keep first-passage path labels as the main path-risk lens.

## Decision State

Current status: research candidate, not model candidate.

Most useful next code work: fix/rebuild exact labels, add short-horizon label generation to the canonical Rust/Python pipeline, then rerun IC/decay and gate controls.

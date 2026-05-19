# BONK V3 Modeling Synthesis

Status: 2026-05-13. This memo summarizes the gated/tree/multitarget diagnostics over `20260513_bullish_l2_basket_price_v1`. It is not a trading rule, not an execution plan, and not an alpha claim.

## Outputs Reviewed

```text
docs/markets/bonk/v1-cex-tree-modeling-report.md
docs/markets/bonk/v1-cex-v3-gated-multitarget-model.md
docs/markets/bonk/v1-cex-v3-gate-distillation.md
docs/markets/bonk/v1-cex-v3-phase-gate-validation.md
docs/markets/bonk/v1-cex-v3-multitarget-labels.md
```

Supporting CSVs:

```text
date/bonk_v1_tree_model_metrics_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v3_gated_multitarget_metrics_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v3_gated_multitarget_phase_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v3_gate_distillation_outcome_stats.csv
date/bonk_v3_phase_gate_validation_gate_summary.csv
date/bonk_v3_multitarget_label_selection_summary.csv
```

## Main Read

The earlier global tree model was not really testing the hand-built gates. It optimized `upper_first` logloss, while the strongest manual gates mostly act as residual/path-state filters and lower-first suppressors.

For `BONK1MUSDT H4`:

| gate | fold | rows | upper edge | lower edge | residual edge | median future residual edge |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `depth_high+rv_low` | fold2 | 42 | +11.6pp | -5.1pp | +30.2pp | +29.3 bps |
| `depth_high+rv_low` | fold3 | 660 | -7.1pp | +0.1pp | +9.7pp | +21.9 bps |
| `depth_high+rv_low+cv_spread` | fold2 | 18 | +6.8pp | +4.4pp | +30.2pp | +37.3 bps |
| `depth_high+rv_low+cv_spread` | fold3 | 407 | +1.2pp | -7.0pp | +22.5pp | +40.3 bps |

So the additive cross-venue gate is still the cleaner H4 USDT state in fold3: it improves residual-positive and suppresses lower-first, with only modest standalone upper-first lift.

## Tree Model Read

Global `context+L2` boosted trees are mixed:

- Fold2/3 stride-H proper-score wins vs context-only: `7/16`.
- Median delta logloss: `-0.0031`.
- Median delta Brier: `-0.0001`.

But `L2-only` trees were stronger than `context+L2` in the tree report. That says L2 has state information, while naive context+L2 mixing can bury it under regime/context noise.

## Gate Distillation

The hand gates are mechanically expressible by shallow trees. This is expected but useful: it confirms the gates are simple state definitions, not obscure model artifacts.

For H4 gates, distilled `lightgbm_depth3` roughly preserves the actual gate effect:

- `depth_high+rv_low`: actual residual edge around `+30.2pp` in fold2 and `+10.2pp` in fold3; distilled predicted rows keep positive residual edge in the better shallow model.
- `depth_high+rv_low+cv_spread`: actual residual edge around `+33.4pp` in fold1 and remains strong in aggregate; shallow models identify the gate variables directly.

Distillation should be used to audit whether the gate can be represented, not as an outcome model.

## Phase Validation

Phase-rotated validation is more favorable to the manual H4 USDT gates than the single fixed stride row:

| gate | eligible phases | median residual edge | residual pass | median future residual edge | direction pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| `depth_high` | 459 | +20.0pp | 71.7% | +29.2 bps | 59.7% |
| `rv_low` | 480 | +29.5pp | 82.7% | +36.3 bps | 55.6% |
| `depth_high+rv_low` | 244 | +25.8pp | 73.8% | +34.4 bps | 58.2% |
| `depth_high+rv_low+cv_spread` | 92 | +26.7pp | 83.7% | +41.1 bps | 63.0% |

This supports the gate as a regime/state candidate, but phase rows are still thin. The correct conclusion is “pre-register and retest,” not “trade rule.”

## Multi-Target Read

The label probe shows why `upper_first` alone is misleading. In fold3 H4 USDT:

| selector | upper | lower | not lower | residual positive | median residual | median raw return |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `depth_high+rv_low` | 30.4% | 42.0% | 58.0% | 52.1% | +4.8 bps | -2.1 bps |
| `depth_high+rv_low+cv_spread` | 37.2% | 36.8% | 63.2% | 61.9% | +19.7 bps | +24.2 bps |
| top-decile `upper_first` model | 27.3% | 59.3% | 40.7% | 17.8% | -48.2 bps | -90.2 bps |
| top-decile `residual_positive` model | 46.9% | 24.2% | 75.8% | 55.0% | +13.9 bps | +48.7 bps |

The useful ML target is closer to residual-positive / lower-first avoidance than raw `upper_first`.

## Gated Model Read

The first gated multi-target model did not improve the best manual gate by much. Inside `depth_high+rv_low+cv_spread`, fold3 top-20% model selections generally worsened residual and lower-first metrics versus taking the gate as a whole.

That is a practical finding: the current strongest object is the gate/state itself. Gate-inside ranking needs either more data, better target design, or a stricter feature set.

## Working Hypothesis

The current H4 USDT candidate is:

```text
depth_high + rv_low
depth_high + rv_low + cv_spread
```

Interpretation:

- `depth_high` marks venue capacity / liquidity state.
- `rv_low` marks a quiet regime where lower-first paths are less punishing.
- `cv_spread` adds cross-venue state and improves the cleaner fold3 read.

This is a regime-local path-state hypothesis, not a durable directional alpha claim.

## Next Modeling Plan

1. Freeze H4 USDT `depth_high+rv_low` and `depth_high+rv_low+cv_spread` as pre-registered gates for the next available window.
2. Keep USDC mirror as watch only.
3. Promote residual-positive and lower-first suppression to first-class targets.
4. Use global trees for diagnostics, not promotion.
5. Use gated models only if they beat the manual gate baseline inside the same frozen gate.
6. Report phase distributions, not one fixed non-overlap phase.
7. Do not use MLP until there is more window diversity and the gate/target definitions stabilize.


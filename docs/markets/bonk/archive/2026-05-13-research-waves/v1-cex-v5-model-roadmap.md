# BONK CEX V5 Model / ML Roadmap

Status: 2026-05-13. This is a post-V4 modeling roadmap over the existing BONK Bullish L2 + Binance context research line. It is not a trading rule, not an execution plan, not a sizing rule, and not an alpha claim.

## Recommendation

Do not escalate BONK to a heavier ML program yet. The next V5 path should be:

```text
canonical exact labels -> frozen state/rule retest -> short-label decay/capacity checks -> small interpretable models only if the frozen state survives
```

The current best object is still a state:

```text
BONK1MUSDT H4 depth_high + rv_low
BONK1MUSDT H4 depth_high + rv_low + cv_spread
```

V4 sharpened the interpretation: this is a deep/quiet orderbook regime with cross-venue state information and small displayed-depth capacity. It is not yet a clean global model signal, not a gate-internal ranking signal, and not a reason to add MLP capacity.

## Evidence To Carry Forward

Reviewed source memos:

```text
docs/markets/bonk/v1-cex-v3-modeling-synthesis.md
docs/markets/bonk/v1-cex-v3-next-round-analysis.md
docs/markets/bonk/v1-cex-v3-negative-controls.md
docs/markets/bonk/v1-cex-v3-gated-ranking.md
docs/markets/bonk/v1-cex-v4-orderbook-synthesis.md
docs/markets/bonk/v1-cex-v4-orderbook-family-ablation.md
docs/markets/bonk/v1-cex-v4-short-horizon-orderbook.md
docs/markets/bonk/v1-cex-v4-orderbook-capacity.md
docs/markets/bonk/v1-cex-v4-regime-state-taxonomy.md
docs/markets/bonk/v1-cex-v4-exact-label-audit.md
```

Key facts:

- Gate-internal ML failed the strict test: shallow LightGBM/XGBoost, logistic/ridge heads, raw heuristics, and linear composites did not beat the gate-only baseline inside the frozen H4 USDT gates.
- The cross-venue family is the cleanest incremental orderbook family after context controls. It is useful as a venue-state / basis-convergence control, not as a standalone lead-lag direction story.
- The combined all-orderbook feature set overfits. In V4 family ablation, the combined family had the weakest after-context read, while small selected families were more interpretable.
- Short labels are feasible. Existing data supports 5m/15m/30m labels with 20/30 bps barriers and strong coverage, but V4 reads them as microstructure decay/capacity diagnostics rather than execution-ready signals.
- Exact labels do not explain away the active H4 state, but canonical research should still migrate to exact endpoint semantics before any model promotion.
- Capacity is the hard constraint. H4 active gates have nonzero but small displayed-depth envelopes: top-of-book is effectively zero, 5-level depth is around 50 quote, and 25-level wide-stress envelope is around 500 quote.

## Model Family Decision

| family | V5 decision | why |
| --- | --- | --- |
| Rule/state gates | Primary path | The best evidence is state-like: deep depth, low RV, and selected cross-venue spread state. This is interpretable and matches capacity diagnostics. |
| Shallow linear models | Continue as diagnostics | Logistic/ridge models are useful for calibration, residual-positive / not-lower-first baselines, and feature sign checks. They are not yet promotion models. |
| Shallow trees | Continue as audit tools | Depth-2/3 trees can verify that gates are mechanically simple and expose threshold drift. Avoid treating boosted trees as alpha engines until the frozen state passes controls. |
| Ranking / gate-internal ML | Pause | V3 gated ranking did not beat the gate-only baseline. Restart only after more windows or after the frozen state clears negative controls. |
| Combined feature models | Reject for now | Combined orderbook features overfit and weaken attribution. Keep a small whitelist: context, depth/RV, selected cross-venue, spread/activity for short horizons. |
| MLP / deep models | Defer | MLP is unjustified while data is short-window, labels overlap, capacity is tiny, and shallow/gate baselines are unbeaten. |

## V5 Research Path

1. Canonicalize labels.

Move timestamp-exact H1/H4/H12 and 5m/15m/30m labels into the canonical pipeline. The exact-label audit says old labels are not materially wrong for this slice, but model work should not depend on prototype label semantics.

2. Freeze the state definition.

Pre-register only these H4 USDT states for the next window:

```text
depth_high + rv_low
depth_high + rv_low + cv_spread
```

Thresholds must be train-side only. Do not tune new cross-venue variants on validation rows.

3. Retest before modeling.

The frozen state must be checked against:

- random phase controls,
- 240m/720m/1440m time shifts,
- quote/symbol placebos,
- meme / market / SOL relative controls,
- missing-minute impact,
- displayed-depth stress,
- lower-first and drawdown path risk.

4. Use short labels for decay and feasibility.

Short labels should answer:

- Does the same state decay from 5m to 15m to 30m?
- Are spread/depth/activity buckets signs of movement intensity or direction?
- Does any short-horizon candidate survive stress-net capacity?

They should not be converted into a fast trading rule unless they also clear the same negative-control and capacity checks.

5. Keep the model stack small.

The default V5 model suite should be:

```text
state/rule baseline
logistic_l2 residual_positive
logistic_l2 not_lower_first
ridge future_residual_bps
tree_depth2 residual_positive
tree_depth2 not_lower_first
optional shallow LightGBM/XGBoost only as a diagnostic ceiling
```

Every model must be compared against the frozen state baseline on the same rows, same phase rotations, and same capacity columns.

## Acceptance Criteria For Adding MLP

Add an MLP only after all criteria below pass. Failing any one keeps MLP out of scope.

1. Label and split readiness:
   - timestamp-exact labels are canonical,
   - train/validation/test windows are frozen before fitting,
   - at least one genuinely later window exists beyond the current 2026-04-29..2026-05-12 sample,
   - overlapping-label evaluation reports both raw rows and stride/effective counts.

2. Baseline survival:
   - the frozen H4 USDT state passes negative controls or has clearly documented failures that disappear in the later window,
   - cross-venue remains incremental after context controls without becoming a post-hoc direction story,
   - short-label diagnostics agree with the H4 state instead of contradicting it.

3. Shallow model ceiling:
   - the fixed shallow suite is rerun first,
   - at least one shallow model beats the state-only baseline out-of-window on proper scores and path diagnostics,
   - gate-internal ranking beats the gate-only baseline before any deeper gate-internal model is tried.

4. Capacity relevance:
   - selected rows keep a nonzero stress-net displayed-depth envelope,
   - top-of-book limitations, 5/25-level depth, lower-first rate, and drawdown are reported next to every model metric,
   - the model does not win only in rows whose feasible quote envelope is effectively zero.

5. MLP design constraint:
   - architecture is pre-registered and small, for example one or two hidden layers with strong L2/dropout,
   - input features are whitelisted families, not the combined all-orderbook dump,
   - calibration and probability monotonicity are checked against logistic baselines,
   - feature ablation shows the MLP is using stable families, not memorizing fold/time state.

6. Promotion threshold:
   - MLP must beat the best shallow baseline in the later window, not just fold2/fold3 of the current window,
   - improvement must show in both proper scores and economic/path diagnostics: residual-positive, not-lower-first, median future residual, lower-first rate, stress-net capacity, and drawdown,
   - no negative-control or placebo variant may match or beat the MLP selection.

## Practical V5 Output Spec

The next modeling report should contain one table per candidate with these columns:

```text
candidate
family
symbol
horizon
barrier_bps
selected_rows
effective_rows
selected_share
residual_positive_edge
not_lower_first_edge
median_future_resid_bps
upper_minus_lower
lower_first_rate
drawdown_median_bps
stress_net_median_bps
d5_capacity_envelope
d25_wide_stress_envelope
proper_score_delta_vs_context
proper_score_delta_vs_state
negative_control_status
placebo_status
decision
```

Decision values should stay simple:

```text
research_state
diagnostic_only
blocked_by_controls
blocked_by_capacity
blocked_by_baseline
ready_for_next_window_retest
```

## Bottom Line

For small-capacity BONK, the highest-value work after V4 is not a larger model. It is a cleaner state-validation loop with exact labels, frozen gates, short-horizon decay checks, and capacity-aware reporting.

MLP should be treated as a late-stage diagnostic only after the frozen state and shallow baselines survive later-window validation. Until then, V5 should continue with rule/state models plus small shallow baselines, with cross-venue kept as a controlled family and combined feature dumps avoided.

# BONK CEX V4 Orderbook Research Plan

Status: 2026-05-13. This plan synthesizes the BONK V3 L2, tree, gated, negative-control, short-horizon, gross-edge, and leakage diagnostics. It is a research plan only: no trading rule, no execution instruction, no sizing rule, and no alpha claim.

## Current Read

The useful BONK orderbook object is not a global predictive model yet. It is a small set of state filters, led by `BONK1MUSDT H4 depth_high + rv_low` and `depth_high + rv_low + cv_spread`, that may describe a quiet, high-depth, cross-venue-aware market state. These gates have plausible residual/path behavior and rough mid-to-mid friction room, but they remain blocked by negative controls, threshold drift, phase sensitivity, and incomplete execution modeling.

Use orderbook data going forward for three separate questions:

1. Is this a stable state filter after market and meme controls?
2. Does the state create enough path width and lower-first suppression to deserve execution-cost work?
3. Do any short-horizon orderbook features have fast decay, or are they only slow regime persistence?

## Data Contract

Keep the current Bullish L2 minute panel as the canonical research surface, but rebuild path labels before promotion:

- Use timestamp-exact horizon endpoints for `future_return_bps`; do not rely on row-index offsets when L2 minutes are missing.
- Preserve first-passage labels with `upper_first`, `lower_first`, `both_or_ambiguous`, `mfe_up_bps`, `mae_down_bps`, `path_width_bps`, and exact endpoint return.
- Maintain symbols separately for `BONK1MUSDC` and `BONK1MUSDT`; do not pool them until side semantics, spread, and venue roles are explicitly normalized.
- Keep Binance/meme/SOL context features strictly t-and-earlier.
- If V4 scripts produce outputs, treat them as append-only inputs for synthesis; do not overwrite them.

## State Filters

Primary frozen candidates for the next validation window:

| id | symbol | horizon | gate | intended read |
| --- | --- | ---: | --- | --- |
| `h4_usdt_depth_rv` | BONK1MUSDT | 4h | `depth_high + rv_low` | quiet/high-depth state |
| `h4_usdt_depth_rv_cv` | BONK1MUSDT | 4h | `depth_high + rv_low + cv_spread` | quiet/high-depth plus cross-venue state |

Watch-only mirrors:

- BONK1MUSDC versions of the same gates.
- H4 `snapshot_microprice_low` only as a path-risk or lower-first diagnostic.
- H1 activity/count and cross-venue microprice disagreement only as path-width diagnostics, not direction.

Do not reselect thresholds on validation data. Thresholds must be fit on train-side folds and then frozen for the validation window.

## Path Labels

Use separate label families instead of forcing all evidence into `upper_first`:

| family | horizons | barriers | purpose |
| --- | --- | --- | --- |
| Direction/path-risk | 1h, 4h | 100 bps | main first-passage read; H4 is primary |
| Short microstructure | 5m, 15m, 30m | 20, 30 bps | decay and fast timing checks |
| Movement/path-width | 1h, 4h, 12h | 50, 100 bps | movement-state diagnostics |
| Residual state | 1h, 4h | exact future residual return | market/meme/SOL-adjusted state quality |

`12h` remains regime/path-width context only. `100 bps` is too sparse for 5m and mostly too sparse for 15m; do not use it as the primary short-horizon microstructure target.

## Cross-Venue Controls

Every orderbook result must be reported against:

- Market, meme basket, SOL, and BONK realized-volatility context.
- Bullish common-mode state across BONK/meme symbols where available.
- USDC/USDT basis, absolute basis, spread difference, activity share, and microprice disagreement.
- Cross-section placebo versus other meme symbols where coverage allows.

Cross-venue basis and spread variables should first be interpreted as convergence, routing, liquidity, or movement-state diagnostics. They only become lead-lag candidates if signed residual effects survive lag, phase, and cross-section controls.

## Execution And Capacity

Mid-to-mid labels are not executable fills. Promotion requires an explicit execution/capacity table with:

- Median and p10 displayed top-depth capacity at small participation assumptions such as 5% and 10%.
- Spread floor, fee assumption, and slippage stress reported separately.
- Lower-first rate, median adverse excursion, and path-width for selected rows.
- Gate share and selected-row count by fold and by phase.
- A check that high-depth gates are not merely selecting stale or already-favorable paths.

Current gross-edge reads are capacity-limited on paper, not viable execution evidence. H1 gates are mostly spread-fragile; H4 gates deserve cost-aware validation first.

## Modeling Use

Use trees as diagnostics, not promotion engines:

- Shallow trees can audit whether hand gates are simple and reproducible.
- Global `context+L2` trees must beat context-only on proper scores before model language is allowed.
- Gate-internal models must beat the manual gate baseline inside the same frozen gate.
- Residual-positive and lower-first suppression are first-class targets; `upper_first` alone is insufficient.

No MLP or high-capacity model until there are more independent windows and the frozen gate passes negative controls.

## Negative Controls

A candidate is blocked if any of these remain true:

- Random phase p95 beats the actual gate on fold2/fold3 residual edge.
- Time-shift/placebo gates at 240m or 720m match the actual gate without a documented regime-persistence interpretation.
- Fold2/fold3 threshold drift changes selected share by more than 3x without preserving residual and lower-first behavior.
- Cross-section placebo shows the same effect across meme symbols but BONK relative-to-meme is not positive.
- Exact-label rebuild materially weakens gross edge, residual edge, or IC.

## Promotion Rules

Statuses:

| status | required evidence |
| --- | --- |
| `research_state` | plausible mechanism and positive controlled diagnostic, but controls incomplete |
| `validation_candidate` | frozen gate passes exact labels, fold2/fold3 residual edge, lower-first, phase, and cross-section checks |
| `execution_research_candidate` | validation candidate plus rough friction and capacity table survives stress |
| `model_candidate` | context+L2 or gated model beats context-only/manual-gate baseline on proper scores and target-specific metrics |
| `discard_or_wait` | unstable, post-hoc, capacity too thin, label-quality dependent, or placebo-dominated |

Concrete promotion from current state to `validation_candidate` requires all of:

- Same frozen H4 USDT gate works on the next available window without threshold reselection.
- Positive median residual return and positive residual-positive edge in fold2/fold3 or next-window validation.
- Lower-first rate is not worse than the fold/window baseline; preferred improvement is at least 5 percentage points.
- Phase-rotated median residual edge remains positive, and at least 60% of eligible phases are positive.
- Random-phase and time-shift controls do not beat the actual gate.
- BONK return remains positive relative to meme basket inside the gate.
- Selected rows are not too sparse: at least 300 selected minutes for H4 gate-level diagnostics, or explicitly marked `too_sparse`.

Promotion to `execution_research_candidate` additionally requires:

- Stress net after spread, fee, and small slippage remains positive on median selected rows.
- Capacity at 5% of p10 displayed depth is not negligible for the intended research size.
- Lower-first and drawdown do not dominate the stress-net read.
- Results are reported separately for USDC and USDT with venue-specific spread/capacity.

## Collect More L2 Data Decision

Collect more BONK L2 data only if the current window plus exact-label rebuild leaves at least one frozen state worth validating. The minimum go/no-go criteria:

Go collect more L2 if all are true:

- Exact-label rebuild does not invalidate H4 `depth_high + rv_low` or `depth_high + rv_low + cv_spread`.
- At least one H4 USDT gate has positive residual edge, positive median residual return, and non-worse lower-first behavior after controls.
- Negative-control failure is explainable as slow regime persistence rather than pure phase luck, or improves after exact labels.
- Rough friction table still shows positive median stress net for H4, even if capacity-limited.
- Short-horizon labels show feasible coverage for 5m/15m 20/30bps tests without requiring new raw data first.

Do not collect more L2 yet if:

- Exact labels erase the H4 residual/gross edge.
- The only surviving evidence is overlapping full-minute labels.
- Candidate gates require reselected thresholds, dates, symbols, or barriers to look good.
- Cross-section placebo shows broad meme/common-mode movement with no BONK-relative advantage.
- Execution/capacity stress is negative or too sparse even before a stricter fill model.

## Next Work Order

1. Rebuild exact endpoint labels for 1h/4h and rerun H4 gate diagnostics.
2. Add 5m/15m/30m labels at 20/30bps for microstructure decay.
3. Rerun negative controls, threshold drift, phase-rotated non-overlap, and cross-section placebo on frozen gates.
4. Produce an execution/capacity table using displayed orderbook depth and explicit spread/fee/slippage assumptions.
5. Decide whether to collect the next L2 window using the go/no-go criteria above.

Bottom line: V4 should turn orderbook data into a controlled validation queue. The current best object is an H4 BONK1MUSDT state filter; the next collection decision should depend on exact labels, negative controls, and capacity-aware stress, not on a better-looking global model.

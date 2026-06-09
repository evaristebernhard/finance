# CCUSDT V2 Executable Research Framework

Status: 2026-05-18.

Guardrail: `research_framework_only_no_execution_recommendation_no_alpha_claim`.

This document turns the observed CCUSDT/Bullish CEX L2 short-horizon microstructure edge into an executable research framework. It is not a trading rule, live execution simulation, fill model, sizing rule, or alpha claim. The current state remains research-continue and execution-no-go.

## Objective

Build a walk-forward research system that can identify CCUSDT L2 entry states with true after-cost right-tail expectancy above `2` bps, while rejecting low-quality entries and controlling left-tail risk.

The framework must separate four questions that earlier v1 reports partly mixed:

- Is the entry signal real after recent-return, stale-quote, spread, and activity controls?
- Does the signal survive realistic cost pressure instead of only toy midpoint labels?
- Is the payoff a stable path shape or a fragile top-tail cluster?
- Can exit and risk logic improve left tail without destroying the winners that pay for the edge?

## Current Evidence Read

The primary research thread is still `trade_flow_imbalance` (`TFI`). `MLOFI`, queue pressure, and book-pressure composites are confirmation and state features until they independently survive the same controls.

Known useful states from v1:

| family | current role | evidence | blocker |
| --- | --- | --- | --- |
| `tfi_follow_flat` | large-sample right-tail candidate | fold2/fold3 positive after maker-light cost and beats matched random | negative median, top-tail dependent, cost-thin |
| `tfi_short_flat` | large-sample right-tail candidate | similar fold2/fold3 behavior and survives top-10 removal in fold3 | negative median and fails with modest added cost |
| `tfi_short_stale25` | sparse quote-release hypothesis | fold3 mean/median attractive and matched random clean | fold-sensitive, sparse, fold2 weak |
| `tfi_event_active` | state-conditioned candidate | better central tendency in fold3 | still needs residual and day-level proof |
| `MLOFI/book_pressure` | confirmation layer | informative in method/factor sweeps | not promoted as standalone entry |

The current edge should be treated as a right-tail cluster edge, not a central-tendency rule. That is acceptable only if the tail is systematic, repeatable, and still positive after stricter costs and controls.

## Research DAG

```text
raw Tardis L2/events
  -> snapshot/event factor panel
  -> past-only candidate features
  -> purged walk-forward folds
  -> entry candidates
  -> quote-transition and residual labels
  -> cost-stressed path labels
  -> matched controls
  -> entry-quality model
  -> exit-shape model
  -> risk-control model
  -> scorecard and promote/stop decision
```

Every stage writes fold/date-level artifacts. No threshold, scaler, model, filter, feature ranking, or stop choice may be fitted on the validation side.

## Data Contract

The current source panel is:

```text
data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel/run_tag=20260517_ccusdt_fixed_factors_v3/
```

Minimum columns for v2:

| group | required fields |
| --- | --- |
| identity | `date`, `symbol`, `local_timestamp`, `event_index`, `is_snapshot_batch` |
| quote state | `best_bid_price`, `best_ask_price`, `mid_price`, `spread_bps`, `microprice`, `microprice_dev_bps` |
| book pressure | `queue_imbalance_*`, `ofi_*`, `mlofi_*`, visible depth fields |
| trade flow | `trade_window_count`, `trade_buy_amount`, `trade_sell_amount`, `trade_notional_quote`, `trade_flow_imbalance` |
| state filters | stale-mid frames, quote-change flags, trade-present flags, spread buckets, recent-return buckets |
| path labels | fixed horizon, first quote transition, max favorable excursion, max adverse excursion, recovery after adverse touch |

Panel caveat: the current replay is `factor_panel_only`. It is valid for information diagnostics, but it is not queue-position fill evidence. Execution promotion requires a separate event-level fill simulator or live/paper fill evidence.

## Walk-Forward Contract

Use daily expanding folds first, then add rolling folds after the sample grows.

Required fold rules:

- Train side fits all quantiles, scalers, feature rankings, residual models, control buckets, and model parameters.
- Validation side is untouched except for applying train-fitted objects.
- Use non-overlap entry buckets by horizon. A `60s` label cannot create overlapping independent entries.
- Add an embargo of at least the maximum modeled exit horizon after train windows when feasible.
- Report per-fold, per-date, and leave-one-day-out results. A candidate that only works in one validation day remains diagnostic.

Promotion requires at least two adjacent validation folds with the same signed mechanism, not just one fold3 pocket.

## Cost Contract

Net edge is measured after an all-in cost hurdle:

```text
net_i = side_i * 10000 * log(exit_price_i / entry_price_i) - cost_i
```

`cost_i` must include the chosen entry/exit price convention, spread treatment, fees, fill uncertainty, queue/latency allowance, and stress adders. The v1 `toy_maker_light` cost is a research lower bound, not a promotion cost.

Required cost ladder:

| cost layer | purpose |
| --- | --- |
| `midpoint_diagnostic` | information-only label, never promotable |
| `maker_light` | lower-bound research hurdle |
| `taker_or_spread` | unfavorable spread/fee sanity check |
| `wide_stress` | stress condition for gross-only failures |
| `realistic_plus_1/2/3/5bps` | robustness curve for promotion gating |

Minimum economic gate for execution research:

- Mean after realistic cost is greater than `2` bps in each promoted fold.
- Day bootstrap p05 of mean is positive or explainably near zero with high sample count.
- Added `+2` bps stress does not flip the family negative in the main fold pair.
- Median may be slightly negative for a right-tail family, but it cannot keep worsening as filters are tightened.

## Matched Controls

Negative controls must be fold-valid and matched on state, not only shuffled globally.

Required controls:

| control | match dimensions |
| --- | --- |
| reversed side | same timestamp and filter state, opposite side |
| shifted signal | same date, shifted by train-chosen event/time offset |
| past-return gate | same target horizon, using recent returns instead of the signal |
| matched random | date, side, stale bucket, trade-present flag, spread bucket, recent-return bucket, event-activity bucket, hour bucket |
| residual target | target residualized on spread, recent return, stale state, activity, and volatility |

Promotion threshold:

- `Pr(random_mean >= signal_mean) < 5%` for matched random.
- Signal mean exceeds matched-random p50 by at least `2` bps after cost.
- Reversed-side and shifted controls do not reproduce the same signed edge.
- Residual labels keep the same signed mechanism.

## Mathematical Decomposition

Entry quality uses the cost-threshold decomposition already introduced in v1:

```text
A = Pr(gross_i > cost_i)
B = E[gross_i - cost_i | gross_i > cost_i]
D = E[cost_i - gross_i | gross_i <= cost_i]
E = A * B - (1 - A) * D
```

The entry model should improve `E` by increasing `A`, increasing `B`, or lowering `D`. A filter that only increases mean by deleting most entries must also improve fold stability and controls.

Exit-shape decomposition:

```text
barrier_delta
  = tp_save_giveback
  - tp_clip_right_tail
  + sl_save_left_tail
  - sl_kill_recovery
  + race_effect
  - delta_cost
```

Stop/risk diagnostics:

```text
stop_value
  = left_tail_saved
  - recovery_killed
  - right_tail_killed
  - extra_cost_or_latency
```

Good risk control improves CVaR and drawdown while keeping mean flat or better. A stop that makes the median look better by clipping the right tail is not a usable exit unless it also preserves the cost-crossing winners.

## Model Layers

### Entry-Quality Model

Goal: score whether an entry is likely to clear `realistic_cost + 2bps`.

Allowed features:

- `trade_flow_imbalance` state and direction.
- MLOFI/orderbook pressure features as confirmation.
- stale length, trade-present flag, event activity, spread bucket, recent return, volatility, and hour bucket.
- path-independent quote state available at entry time only.

Forbidden features:

- future trade windows.
- target horizon returns.
- post-entry quote transitions.
- fold validation quantiles or scalers.

Model stack:

| layer | role |
| --- | --- |
| quantile gate baseline | reproduce v1 candidate families |
| logistic or calibrated tree | interpretable entry-quality probability |
| monotone/light GBM probe | nonlinear interaction discovery |
| quality bins | low/medium/high entry buckets for rejection logic |

Entry rejection is successful only if low-quality bins lose or underperform controls while high-quality bins keep after-cost edge.

### Exit-Shape Model

Goal: classify whether a path is continuation, quote release, adverse-and-recover, or failed recovery.

Outputs:

- first quote transition direction and delay.
- continuation after first transition.
- maximum adverse excursion before profit.
- recovery probability after `5/8/12/20` bps adverse touch.
- timeout quality at `10s/30s/60s`.

Exit selection rules:

- Fixed horizon remains the benchmark.
- Stop-only is allowed as risk control if CVaR improves and mean cost is near zero or positive.
- Delayed catastrophic stop is allowed only if it improves left tail without killing cost-crossing winners.
- Hard TP/SL grids stay deprecated unless decomposition proves TP giveback saving exceeds right-tail clipping.

### Risk-Control Model

Goal: suppress left-tail states before entry or during early path monitoring.

Risk features:

- spread widening.
- stale-to-active transition quality.
- event burst rate.
- recent adverse movement.
- high microprice dislocation against side.
- abnormal depth vacuum or top-size churn.

Risk acceptance:

- CVaR10 improves by at least `5` bps for the target family.
- Mean falls by less than `0.5` bps, or improves.
- `stop_given_fixed_cost_winner_rate` remains below `10%` for large-sample families.
- save-to-kill ratio is above `1.0`, preferably above `1.5` for sparse states.

## Scorecard Gates

| gate | pass threshold |
| --- | --- |
| data integrity | no future features, no stale blending bug, fold-side transforms only |
| sample size | large family `>= 500` entries per promoted fold, sparse state `>= 100` with leave-one-day-out proof |
| economics | realistic net mean `> 2` bps after cost |
| cost stress | main family survives `+2` bps added cost |
| controls | matched random p-value `< 5%`, residual target still positive |
| stability | at least two adjacent validation folds or clear out-of-sample extension |
| tail concentration | top `10%` winners do not exceed `85%` of total net for promotion; if above, keep as right-tail research only |
| left tail | CVaR improves or is explicitly bounded without killing winners |
| execution realism | queue/fill/latency model exists before any executable status |

Any failure keeps the candidate in research-only status.

## Next Work Packages

1. Quote-transition and residual-label pass:
   Build labels for first true bid/ask/mid transition, post-transition continuation, and residual returns after stale/activity/recent-return controls.

2. Matched-control upgrade:
   Replace broad random controls with state-matched controls on date, side, stale bucket, spread bucket, trade-present, recent return, event activity, and hour.

3. Entry-quality model:
   Train fold-valid entry scores for `tfi_follow_flat`, `tfi_short_flat`, `tfi_short_stale25`, and `tfi_event_active`; produce quality-bin tables and rejection curves.

4. Exit-shape and risk-control model:
   Model adverse excursion and recovery before choosing any stop. Stop tuning remains diagnostic unless the decomposition passes.

5. Execution realism gap:
   Decide whether to build event-level queue replay, live paper capture, or vendor L2 reconstruction before any strategy promotion.

## Required Artifacts

Next v2 run should emit:

```text
date/ccusdt_v2_quote_transition_labels_<run_tag>.csv
date/ccusdt_v2_residual_controls_<run_tag>.csv
date/ccusdt_v2_matched_controls_<run_tag>.csv
date/ccusdt_v2_entry_quality_bins_<run_tag>.csv
date/ccusdt_v2_exit_shape_<run_tag>.csv
date/ccusdt_v2_risk_control_<run_tag>.csv
date/ccusdt_v2_scorecard_<run_tag>.csv
date/ccusdt_v2_summary_<run_tag>.json
docs/markets/ccusdt/v2-framework-run-<run_tag>.md
```

## Current Decision

Continue exactly one narrow v2 verification branch. Do not optimize hard TP/SL parameters, do not promote sparse fold3-only rows, and do not treat midpoint profitability as executable edge. The research survives only if the same TFI/state mechanism clears strict walk-forward, realistic costs, matched controls, residual labels, and left-tail controls with true after-cost profit above `2` bps.

## First Run Status

The first v2 framework run is documented in:

```text
docs/markets/ccusdt/v2-framework-run-20260518_ccusdt_v2_framework_v1.md
```

It emitted all required v2 artifacts for `20260518_ccusdt_v2_framework_v1`:

```text
date/ccusdt_v2_quote_transition_labels_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_residual_controls_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_matched_controls_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_entry_quality_bins_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_exit_shape_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_risk_control_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv
date/ccusdt_v2_summary_20260518_ccusdt_v2_framework_v1.json
```

Readout: no row passed promotion. Bin-level controls leave four `research_continue` rows: fold3 `tfi_follow_flat/high`, `tfi_long_flat/high`, `tfi_short_flat/high`, and `tfi_short_stale25/low`. These rows pass matched-control and residual checks but fail one or more hard gates: sample size, `>2` bps economics, `+2` bps stress, tail concentration, risk control, and execution realism. `tfi_event_active` in `expanding_fold3 / mid` showed the strongest after-cost mean, but failed bin-level matched control, sample size, tail concentration, and execution realism. The correct next step is targeted cost/tail/risk repair or execution-realism data, not strategy promotion.

The first execution-realism proxy is documented in:

```text
docs/markets/ccusdt/v2-fill-realism-20260518_ccusdt_v2_fill_realism_v1.md
```

It emitted:

```text
date/ccusdt_v2_fill_realism_events_20260518_ccusdt_v2_fill_realism_v1.csv
date/ccusdt_v2_fill_realism_summary_20260518_ccusdt_v2_fill_realism_v1.csv
date/ccusdt_v2_fill_realism_scorecard_20260518_ccusdt_v2_fill_realism_v1.csv
date/ccusdt_v2_fill_realism_summary_20260518_ccusdt_v2_fill_realism_v1.json
```

Fill-realism readout: all five focused rows were `fill_realism_no_go` under the practical scorecard scenario (`250ms` latency, `5s` fill window, `100` quote notional, `2` bps fee stress). Fill rates were too low and filled-net means were negative. This does not replace full incremental-book queue replay, but it strengthens the current execution-no-go decision.

The first incremental-L2 queue-pressure proxy is documented in:

```text
docs/markets/ccusdt/v2-l2-queue-fill-20260518_ccusdt_v2_l2_queue_fill_v1.md
```

It emitted:

```text
date/ccusdt_v2_l2_queue_fill_events_20260518_ccusdt_v2_l2_queue_fill_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_v1.csv
date/ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_v1.json
```

L2 queue readout: all five focused rows were `l2_queue_fill_no_go` under the same practical scenario. The model credits same-price `incremental_book_L2` amount decreases toward queue-ahead depletion, but requires subsequent opposite-side trades to fill the simulated maker order. Fill rates stayed around `3.08%..8.33%`; filled-net means were negative, and per-signal net remained negative. Queue-pressure evidence therefore does not rescue the current candidates.

The goal completion audit and fill-aware repair scan are documented in:

```text
docs/markets/ccusdt/v2-goal-completion-audit-20260518_ccusdt_v2_fill_repair_audit_v1.md
```

It emitted:

```text
date/ccusdt_v2_fill_repair_filters_20260518_ccusdt_v2_fill_repair_audit_v1.csv
date/ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_v1.csv
date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_fill_repair_audit_v1.json
```

Audit readout: the objective is not complete. The framework, controls, decomposition, entry-quality bins, exit-shape diagnostics, and risk diagnostics are present at research/proxy level, but the explicit stable real-cost `>2` bps capture gate fails. The post-hoc fill-aware repair scan tested `497` simple entry-time filters and found `0` rows that pass all execution gates. Best diagnostic filters improved filled-sample means but still had low fill rates and sub-`1` bps per-signal net.

The all-scorecard practical L2 queue pass is documented in:

```text
docs/markets/ccusdt/v2-l2-queue-fill-20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.md
```

It emitted:

```text
date/ccusdt_v2_l2_queue_fill_events_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv
date/ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv
date/ccusdt_v2_l2_queue_fill_summary_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.json
```

All-practical L2 readout: the practical scenario (`250ms`, `5s`, `100` quote notional, `2` bps fee stress) was run across all `45` framework scorecard bins and `6447` validation entries. Every bin was `l2_queue_fill_no_go`. The best per-signal net was still negative (`-0.0038` bps for `expanding_fold3 / tfi_short_flat / high`).

The all-practical completion audit is documented in:

```text
docs/markets/ccusdt/v2-goal-completion-audit-20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.md
```

It emitted:

```text
date/ccusdt_v2_fill_repair_filters_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv
date/ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv
date/ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.json
```

All-practical audit readout: the objective remains not achieved. The post-hoc fill-aware repair scan tested `3741` simple entry-time filters and found `0` rows that pass all execution gates. The best diagnostic filter reached only about `0.59` bps per signal, far below the required stable real-cost `>2` bps capture.

The taker fallback audit is documented in:

```text
docs/markets/ccusdt/v2-taker-fallback-audit-20260518_ccusdt_v2_taker_fallback_audit_v1.md
```

It emitted:

```text
date/ccusdt_v2_taker_fallback_summary_20260518_ccusdt_v2_taker_fallback_audit_v1.csv
date/ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv
date/ccusdt_v2_taker_fallback_summary_20260518_ccusdt_v2_taker_fallback_audit_v1.json
```

Taker fallback readout: crossing the spread does not rescue the current candidates. All `45` framework bins were `taker_fallback_no_go`. The strongest taker-mean row was `expanding_fold3 / tfi_event_active / mid` with `4.73` bps mean and `2.73` bps after `+2` bps stress, but it still failed sample size, matched controls, tail concentration, and risk gates.

The execution failure decomposition is documented in:

```text
docs/markets/ccusdt/v2-execution-failure-decomposition-20260518_ccusdt_v2_execution_failure_decomp_v1.md
```

It emitted:

```text
date/ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.csv
date/ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.json
```

Failure-decomposition readout: the maker practical identity is `per_signal_net_bps = fill_rate * E[net_bps | filled]`. The best practical maker row is `-0.0038` bps per signal, versus the `2` bps target. At its current fill rate, it would need roughly `46` bps mean net on filled orders to hit target, but its observed filled mean is nonpositive. Combined with the taker fallback no-go, the current CCUSDT candidates should be treated as execution-no-go rather than further optimized.

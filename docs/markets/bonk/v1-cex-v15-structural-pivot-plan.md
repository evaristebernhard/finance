# BONK V15 Structural Pivot Plan

Status: 2026-05-15. Built with `strategy-pivot-designer` after V14 hard-failed.

Guardrail: `research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim`.

## Skill Run

Inputs added for the skill:

- `date/bonk_v15_pivot_iteration_history_20260515_bonk_v10_stage1_pilot.json`
- `date/bonk_v15_pivot_source_strategy_20260515_bonk_v10_stage1_pilot.yaml`

Skill output:

- diagnosis: `date/bonk_v15_pivot_skill_20260515_bonk_v10_stage1_pilot/pivot_diagnosis_bonk_cex_v10_to_v14_queue_reactive_state_policy_20260515_140500.json`
- manifest: `date/bonk_v15_pivot_skill_20260515_bonk_v10_stage1_pilot/pivot_manifest_bonk_cex_v10_to_v14_queue_reactive_state_policy_20260515_140507.json`
- report: `date/bonk_v15_pivot_skill_20260515_bonk_v10_stage1_pilot/pivot_report_bonk_cex_v10_to_v14_queue_reactive_state_policy_20260515_140507.md`

Diagnosis:

```text
recommendation: pivot
score trajectory: [30, 27, 29, 21]
triggers:
  cost_defeat: expectancy=0.000, profit_factor=0.00, slippage_tested=true
  tail_risk: Risk Management score=4 <= 5
```

The generic skill proposals were `earnings_drift_pead`, `volatility_contraction`, and `statistical_pairs`. For this CEX L2 microstructure project, those map to event-delayed confirmation, liquidity-contraction release, and cross-symbol relative pressure.

## V14 Failure Read

V14 did not fail because a single threshold was slightly too strict. It failed because the calibrated state-policy skeleton did not transfer into validation:

| Check | Evidence |
| --- | ---: |
| validation decision rows | 72,000 |
| entered setups | 0 |
| `expected_net_below_fee_plus_one` skips | 71,962 |
| `insufficient_support` skips | 38 |
| validation `expected_net_bps` avg / max / min | -0.5227 / 0 / -3 |
| validation `p_fill` avg / max | 0.0324 / 0.1864 |
| validation `p_up_first` avg / max | 0 / 0 |
| validation `p_down_first` avg | 0.6538 |

Calibration also warned against trusting the few optimistic train buckets. Only 19 calibration rows had `e_net_bps > 0`; the top rows mostly had support `1`, and the transferable validation surface still produced zero entries.

Interpretation:

```text
The next step is not tuning V14 constants.
The next step is changing the objective and architecture.
```

## Pivot Candidates

Candidate table: `date/bonk_v15_structural_pivot_candidates_20260515_bonk_v10_stage1_pilot.csv`.

### V15A Shadow Acceptance Surface

This is the first recommended pass. It reframes V14 from entry selection into a tradeability diagnostic:

```text
state -> p_fill, p_up_first, p_down_first, expected_net, support
```

No entries are created in this pass. The output should explain where `p_up_first` collapses to zero, whether that is caused by label construction, marker placement, side semantics, or real adverse selection.

Success for this diagnostic is not positive PnL. Success is a non-empty, auditable validation surface with support, controls, and first-passage probabilities that do not collapse mechanically.

### V15B Delayed Event Confirmation

This adapts the skill's `earnings_drift_pead` pivot to event time. Instead of entering at the same marker touch that defines the state, wait for 5s/30s/60s post-event confirmation from MLOFI, trade-flow alignment, or microprice drift, then evaluate first-passage after that confirmation timestamp.

Why: V10c had stable event-defined OFI/MLOFI diagnostics, but V14's same-state first-passage produced `p_up_first=0` in validation. Delaying confirmation tests whether the usable information arrives after the event rather than at the marker.

### V15C Cross-Symbol Relative Pressure

This adapts the skill's `statistical_pairs` pivot. Treat `BONK1MUSDC` versus `BONK1MUSDT` as the base object rather than using wrong-symbol checks only as controls. The question becomes whether relative pressure, spread, or lead-lag states have cleaner control separation than single-symbol directional entries.

Why: V10b already showed cross-venue queue/OFI forcing as path-explanatory, but wrong-symbol controls were too close. Making the cross-symbol relation explicit is a cleaner test than pretending it is a nuisance control.

### V15D Liquidity-Contraction Release

This adapts the skill's `volatility_contraction` pivot. Restrict analysis to low crossed-cleanup, stable liquidity hours, then test whether rare queue imbalance or MLOFI release events have a better after-cost path than all `usable_watch` hours.

Why: V10 showed data quality was good enough for diagnostics, but all hours were `usable_watch`, not `high_trust`, due to crossed-cleanup intensity. V15D makes data-quality state part of the hypothesis instead of a footnote.

## Recommended Next Order

1. Build V15A first. It diagnoses the V14 collapse without inventing a new trading rule.
2. If V15A shows non-mechanical first-passage surfaces, test V15B and V15C as separate branches.
3. Use V15D as a quality/regime overlay, not as a standalone direction signal, until it separates from timestamp and shuffled controls.

Hard gates stay unchanged:

```text
fills >= 500
maker_net_bps_mean > 0
stress_maker_net_bps_mean > 0
control_abs_ge_base_abs_rate < 0.50
max_date_share <= 0.35
leave_one_day_min_net_bps > 0
```

## Bottom Line

V14 closes the current queue-reactive first-passage skeleton. The evidence points to a structural pivot: first diagnose the acceptance surface, then test delayed confirmation and cross-symbol relative pressure as separate research branches.

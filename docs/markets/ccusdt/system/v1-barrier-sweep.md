# CCUSDT Barrier Sweep

Status: `20260517_ccusdt_barrier_sweep_smoke2` from source panel `20260517_ccusdt_fixed_factors_v3`.

Guardrail: `research_only_barrier_sweep_no_execution_recommendation_no_alpha_claim`.

This is a triple-barrier toy replay overlay. It is not queue-position fill evidence, not live execution simulation, not trading advice, and not an alpha claim.

## Scope

- Panel rows loaded: `2606830`.
- Entry specs tested: `1`.
- Timeouts: `10s`.
- Upper barriers: `2.0` bps.
- Lower barriers: `2.0` bps.
- Account scale column uses `100.00` quote notional.
- Entries are flat-to-flat: after an entry, later signals are ignored until the barrier exit.

## Data Read

| Metric | Value |
| --- | --- |
| median quote-change rate | 3.80% |
| median trade-present rate | 9.64% |
| median spread | 2.0051 bps |
| p95 spread median-by-day | 4.0059 bps |

## Top Toy-Mid Barrier Rows

| fold | feature | policy | filter | timeout_sec | upper_bps | lower_bps | settlement | entries | gross_mean_bps | tp_rate | sl_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | trade_flow_imbalance | follow_extremes | past25_abs_le_0p5bps | 10 | 2.0000 | 2.0000 | observed_mid | 1393 | 1.6338 | 0.3920 | 0.1070 | 3.5966 |
| expanding_fold2 | trade_flow_imbalance | follow_extremes | past25_abs_le_0p5bps | 10 | 2.0000 | 2.0000 | observed_mid | 1099 | 1.4756 | 0.3185 | 0.0846 | 3.1876 |
| expanding_fold1 | trade_flow_imbalance | follow_extremes | past25_abs_le_0p5bps | 10 | 2.0000 | 2.0000 | observed_mid | 858 | 0.5984 | 0.1876 | 0.0653 | 1.6285 |

## Toy-Cost Survivors

No rows.

## Wide-Stress Survivors

No row survived `toy_wide_stress`.

## Gross-Only Cost Failures

No rows.

## Strategy Read

- Barrier survivor rows: `0`; by fold/cost: none.
- Read: if the best rows choose tight upper barriers and still have negative medians, the prior fixed-time edge is mostly right-tail capture. If barrier rows improve median net, upper/lower exits are adding useful path control.

## Controls

| control | rows | median_entries | median_net_mean_bps | p90_abs_net_mean_bps |
| --- | --- | --- | --- | --- |
| base_toy_mid_barrier | 1 | 1393.0000 | 1.6338 | 1.6338 |
| reversed_side | 1 | 1393.0000 | -1.6338 | 1.6338 |
| past_return_gate | 1 | 24024.0000 | -0.0141 | 0.0141 |
| within_day_shifted_signal | 1 | 12651.0000 | 0.0059 | 0.0059 |

If `past_return_gate` or `within_day_shifted_signal` stays close to the base rows, the barrier result is still a state-persistence artifact warning rather than a clean strategy candidate.

## Current Read

This barrier sweep is a path-shape filter, not an execution model. Any promoted row still needs a quote-transition-only and fillability pass before it can leave research status.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_barrier_sweep_quality_20260517_ccusdt_barrier_sweep_smoke2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_barrier_sweep_entry_specs_20260517_ccusdt_barrier_sweep_smoke2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_barrier_sweep_candidates_20260517_ccusdt_barrier_sweep_smoke2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_barrier_sweep_controls_20260517_ccusdt_barrier_sweep_smoke2.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_barrier_sweep_summary_20260517_ccusdt_barrier_sweep_smoke2.json`

## Reproduce

```powershell
python scripts/ccusdt_barrier_sweep.py
```

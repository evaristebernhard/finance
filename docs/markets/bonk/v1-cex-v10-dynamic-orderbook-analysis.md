# BONK V10 Dynamic Orderbook Analysis

Status: 2026-05-15. Fixed-window research diagnostics for `run_tag=20260514_bonk_v10_stage1_pilot`.

Guardrail: this report is diagnostics only. It is not trading advice, not an execution recommendation, and not an alpha claim.

## Scope

This analysis uses existing V10 outputs only:

```text
window: 2026-05-06 .. 2026-05-12
symbols: BONK1MUSDC, BONK1MUSDT
replay_state_manifest: 14/14 completed
raw download: not run
heavy replay: not run
```

The analysis script is:

```text
scripts/bonk_v10_dynamic_orderbook_analysis.py
```

It reads only necessary columns from large V10 CSVs with chunked pandas passes and writes compact outputs under:

```text
date/bonk_v10_dynamic_orderbook_analysis_*_20260514_bonk_v10_stage1_pilot.*
```

## Output Tables

| table | rows | purpose |
| --- | ---: | --- |
| `date/bonk_v10_dynamic_orderbook_analysis_quality_hourly_20260514_bonk_v10_stage1_pilot.csv` | 336 | symbol/date/hour replay quality and book-state trust tier |
| `date/bonk_v10_dynamic_orderbook_analysis_quality_daily_20260514_bonk_v10_stage1_pilot.csv` | 14 | daily replay rows, spread, cleanup, schema, and single-day concentration |
| `date/bonk_v10_dynamic_orderbook_analysis_state_hourly_20260514_bonk_v10_stage1_pilot.csv` | 336 | potential, queue pressure, imbalance, flow alignment, microprice diagnostics |
| `date/bonk_v10_dynamic_orderbook_analysis_state_summary_20260514_bonk_v10_stage1_pilot.csv` | 2 | symbol-level state summary |
| `date/bonk_v10_dynamic_orderbook_analysis_filter_hourly_20260514_bonk_v10_stage1_pilot.csv` | 200 | purged fold/filter bucket distribution |
| `date/bonk_v10_dynamic_orderbook_analysis_path_hourly_20260514_bonk_v10_stage1_pilot.csv` | 2,988 | hourly path diagnostics by symbol/anchor/side/execution |
| `date/bonk_v10_dynamic_orderbook_analysis_path_summary_20260514_bonk_v10_stage1_pilot.csv` | 36 | path summary by symbol/anchor/side/execution |
| `date/bonk_v10_dynamic_orderbook_analysis_negative_controls_20260514_bonk_v10_stage1_pilot.csv` | 72 | side-flip and deterministic phase controls |
| `date/bonk_v10_dynamic_orderbook_analysis_spearman_horizon_20260514_bonk_v10_stage1_pilot.csv` | 72 | horizon decay and rank-stability diagnostics |
| `date/bonk_v10_dynamic_orderbook_analysis_blockers_20260514_bonk_v10_stage1_pilot.csv` | 4 | next blockers before modeling |
| `date/bonk_v10_dynamic_orderbook_analysis_summary_20260514_bonk_v10_stage1_pilot.md` | n/a | generated compact summary |

## Layer 1: Data Quality And Market State

Replay coverage is now sufficient for fixed-pilot research:

```text
completed replay state files: 14/14
dynamic quality coverage rows: 14
multilevel_schema_ok: 14/14
failure blockers: none
top_of_book_coverage: 1.0 across daily rows
```

Symbol-level quality:

| symbol | replay rows | avg daily median spread bps | avg top-of-book coverage | avg crossed cleanup per 10k replay rows | max same-symbol day share |
| --- | ---: | ---: | ---: | ---: | ---: |
| `BONK1MUSDC` | 869,537 | 1.4108 | 1.0000 | 3,856.6 | 0.156 |
| `BONK1MUSDT` | 1,076,037 | 1.4108 | 1.0000 | 2,536.2 | 0.163 |

All 336 symbol-hour rows landed in `usable_watch`, not `high_trust`. The reason is not missing top-of-book coverage or abnormal spread; it is elevated crossed-level cleanup. The worst cleanup windows were concentrated in specific active hours:

| symbol | date/hour UTC | replay rows | median spread bps | crossed cleanup per 10k | imbalance high-rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `BONK1MUSDC` | `2026-05-12T09:00:00Z` | 7,366 | 1.3774 | 14,633.5 | 0.157 |
| `BONK1MUSDC` | `2026-05-10T18:00:00Z` | 11,500 | 1.2467 | 13,640.0 | 0.769 |
| `BONK1MUSDC` | `2026-05-08T19:00:00Z` | 9,300 | 1.3744 | 11,841.9 | 0.585 |
| `BONK1MUSDT` | `2026-05-12T09:00:00Z` | 7,719 | 1.3771 | 10,864.1 | 0.176 |
| `BONK1MUSDT` | `2026-05-10T18:00:00Z` | 10,962 | 1.2475 | 9,599.5 | 0.774 |

Interpretation:

```text
The fixed pilot is good enough for dynamic orderbook research diagnostics.
It is not clean enough to treat every replay hour as equally reliable.
The main data-quality watch item is crossed-book cleanup during high-activity hours, especially 2026-05-10 and 2026-05-12.
```

There is no obvious single-day dominance problem: max same-symbol daily replay share is about `16.3%`, below the `20%` warning threshold used by the script. Still, validation should stay day-aware because rows inside each day/hour are mechanically dependent.

## Layer 2: Dynamic Orderbook Structure

The strongest and cleanest dynamic structure is trade-flow imbalance. It has the largest short-horizon rank association and a monotone decay profile:

| symbol | feature | horizon | mean Spearman | abs Spearman | sign |
| --- | --- | ---: | ---: | ---: | --- |
| `BONK1MUSDT` | `trade_flow_imbalance` | 30s | 0.1507 | 0.1507 | positive |
| `BONK1MUSDC` | `trade_flow_imbalance` | 30s | 0.1404 | 0.1404 | positive |
| `BONK1MUSDT` | `trade_flow_imbalance` | 60s | 0.1126 | 0.1126 | positive |
| `BONK1MUSDC` | `trade_flow_imbalance` | 60s | 0.1058 | 0.1058 | positive |
| `BONK1MUSDC` | `trade_flow_imbalance` | 300s | 0.0550 | 0.0550 | positive |
| `BONK1MUSDT` | `trade_flow_imbalance` | 300s | 0.0547 | 0.0547 | positive |
| `BONK1MUSDT` | `trade_flow_imbalance` | 900s | 0.0504 | 0.0504 | positive |

That looks like a real microstructure state in the replay data: short horizon first, decaying with time, same sign across symbols.

Other potential/filter states are less clean:

| symbol | potential rows | tight spread rate | imbalance abs high-rate | trade-flow alignment rate | flow-potential corr | micro-potential corr | filter flow-high-abs rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `BONK1MUSDC` | 869,537 | 0.999993 | 0.0623 | 0.2158 | 0.8684 | -0.0641 | 0.1821 |
| `BONK1MUSDT` | 1,076,037 | 0.999999 | 0.0569 | 0.0192 | 0.8746 | 0.0525 | 0.0216 |

Interpretation:

```text
spread regime is stable context, not a useful discriminator here: almost every row is tight-spread.
depth imbalance is present but sparse; high absolute imbalance appears in roughly 5.7%-6.2% of rows.
trade_flow_imbalance is structurally meaningful.
net_potential is not yet clean as a signed state because flow-potential correlation is high while sign alignment is weak, especially on BONK1MUSDT.
microprice/potential correlation is small and unstable in sign.
```

The high `flow_potential_corr` plus low sign-alignment rate is a warning. It suggests the potential function is absorbing trade-flow magnitude, but its sign semantics are not yet reliably aligned with the trade-flow direction. That can produce state labels that look structured but behave like noisy or cost-sensitive triggers when converted into paths.

Filter-state distribution is also asymmetric by symbol:

```text
BONK1MUSDC: net_high 28.2%, net_low 20.1%, flow_high_abs 18.2%
BONK1MUSDT: net_high 31.5%, net_low 18.7%, flow_high_abs 2.2%
spread_wide: near zero for both symbols
```

So the stable structure is not a broad "orderbook potential" bundle. It is narrower:

```text
most stable: trade_flow_imbalance
usable context: tight spread, depth/imbalance regime, queue cleanup intensity
needs repair: signed net_potential, microprice-potential mapping, filter bucket symmetry
likely noise/cost illusion: states that fire often in tight-spread regimes but do not survive after-cost path diagnostics
```

## Layer 3: Path And Stability Diagnostics

Path diagnostics are the weak layer. All execution models are negative after costs in aggregate:

| execution model | configs | avg net bps mean | profit factor mean | win rate mean | path trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| `maker_light` | 12 | -2.3714 | 0.4848 | 0.4802 | 350,016 |
| `taker_spread` | 12 | -3.0553 | 0.3828 | 0.4802 | 350,016 |
| `wide_stress` | 12 | -9.7400 | 0.0189 | 0.1631 | 350,016 |

The least-bad path configs are still negative. Example top rows by average net bps:

```text
BONK1MUSDT microprice_flow short maker_light: avg_net_bps=-1.7629, profit_factor=0.5687
BONK1MUSDC microprice_flow long maker_light: avg_net_bps=-1.8802, profit_factor=0.5547
BONK1MUSDC microprice_flow short maker_light: avg_net_bps=-1.9147, profit_factor=0.5450
```

Negative controls do not provide a clean separation:

| control type | rows | control abs >= base abs rate | same sign as base rate | control minus base PnL mean |
| --- | ---: | ---: | ---: | ---: |
| `deterministic_phase_sign_proxy` | 36 | 0.875 | 1.000 | -21.149 |
| `side_flip_proxy` | 36 | 0.875 | 1.000 | -42.314 |

Because the base paths are already negative, this does not mean controls found a better exploitable structure. It means the path layer is not cleanly separating state logic from cost/path construction effects. The controls often preserve or worsen the same negative direction, which is exactly the failure mode a negative-control test should expose.

Dominant exit reason by path-hour group:

```text
take_profit: 1872 groups
stop_loss: 834 groups
timeout: 282 groups
```

This is not enough to rescue the path layer. Frequent take-profit dominance can coexist with negative average net bps when costs, queue penalties, and stop-loss tails dominate the path economics.

## Answers To The Four Questions

### 1. Is dynamic orderbook data quality sufficient?

Yes for fixed-window research diagnostics. No for treating all hours as equally clean path evidence.

Evidence:

```text
14/14 replay completed
14/14 multilevel schema ok
top-of-book coverage 1.0
median spreads around 1.41 bps
no single-day dominance above 20%
```

But all hours are `usable_watch`, not `high_trust`, because crossed-level cleanup is high during several active windows. The most credible use right now is state discovery and diagnostics with hour/day quality flags. The least credible use is aggressive path conversion without cleanup-aware gating.

### 2. Which microstructure states are most stable?

Most stable:

```text
trade_flow_imbalance at 30s and 60s, positive on both symbols, decaying by horizon.
```

Useful context:

```text
tight spread regime, replay rows, depth_5/depth_25, imbalance high-rate, crossed cleanup rate.
```

Weak or unstable:

```text
signed net_potential, because sign alignment with trade flow is weak.
microprice-potential relationship, because correlations are small and inconsistent.
spread-wide filters, because almost no rows are wide-spread in this pilot.
```

### 3. Which states disappear or fail under negative controls?

The path-level state package fails the negative-control gate. Since base path results are already after-cost negative, the right language is not "the edge disappears"; the right language is:

```text
the path result is not cleanly separated from controls,
and controls often preserve or worsen the same negative PnL direction.
```

The states most exposed by this are:

```text
microprice_flow path triggers,
energy_replenish path triggers,
pressure_break path triggers,
and signed net_potential-derived anchor logic.
```

The raw trade-flow imbalance ranking remains the most stable diagnostic feature, but the current path construction does not convert it into robust after-cost behavior.

### 4. What is the current bottleneck?

Primary bottleneck:

```text
path construction and cost pressure.
```

Secondary bottleneck:

```text
state definition, especially signed potential semantics and filter selectivity.
```

Data quality is not the primary blocker anymore. It is a watch item because crossed cleanup is high in active hours, but replay coverage and schema coverage are adequate for diagnostics.

## Must-Fix Blockers Before Modeling

From `date/bonk_v10_dynamic_orderbook_analysis_blockers_20260514_bonk_v10_stage1_pilot.csv`:

| blocker | severity | evidence | required next action |
| --- | --- | --- | --- |
| `weak_trade_flow_alignment` | medium | `min_trade_flow_alignment_rate=0.019` | revisit potential sign conventions and trade-flow alignment before modeling |
| `after_cost_path_fragility` | high | `maker_light_avg_net_bps_mean=-2.3714` | fix state selectivity/path construction before adding model complexity |
| `negative_controls_not_cleanly_separated` | high | `control_abs_ge_base_abs_rate_mean=0.875` | treat path results as unstable until controls are structurally separated |
| `research_guardrail` | info | diagnostics only | do not promote this to trading advice, execution rules, or alpha claims |

Concrete next engineering steps:

1. Keep the fixed pilot and do not expand the window until the state/path contract is cleaner.
2. Add cleanup-aware quality gates so high crossed-cleanup hours are flagged or separately evaluated.
3. Rework signed potential semantics so `net_potential` sign aligns with trade-flow direction or is explicitly treated as magnitude-only.
4. Tighten anchor/path selectivity; current path generation fires too often relative to cost pressure.
5. Require negative controls to separate cleanly before any downstream modeling step treats a state as robust.

## Bottom Line

The V10 replay layer is now usable for dynamic orderbook research. The strongest observed structure is short-horizon `trade_flow_imbalance`. The bottleneck has moved downstream: signed potential/filter states and path construction are not yet robust under costs and negative controls.

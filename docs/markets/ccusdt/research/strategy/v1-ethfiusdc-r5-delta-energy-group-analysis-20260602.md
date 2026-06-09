# ETHFIUSDC R5 / Delta / Energy Group Analysis

Status: `research_note_20260602`.

Boundary: research-only. This note does not modify Runner, Bot, Monitor, or
runtime policy. It audits the existing ETHFIUSDC old four-cell fast migration:

```text
systems/ccusdt_replay_exchange/runs/experiments/
  ethfiusdc_old_fourcell_idle01_g1_fixed60_taker_q70_20260525_31_rustdf_v0_1
```

## Why This Note Exists

The first ETHFIUSDC four-cell migration report grouped entries by the old
binary cell:

```text
A_t = 1{R5_t >= 1}
B_t = 1{frames_since_mid_change_t >= threshold}
cell = (A_t, B_t)
```

That grouping is incomplete. `R5` is only a shape ratio:

```text
R5 = P / (N + eps)
```

It does not preserve absolute scale. The correct memory group must also inspect:

```text
Delta_bps = P - N
Energy_bps = P + N
Z_bps = Delta_bps / sqrt(Energy_bps + eps)
```

where `P` is the sum of positive bps in the last five closed shadow outcomes
and `N` is the absolute sum of negative bps in those outcomes.

## Reconstruction Method

The fast strategy output saved `a_r5_raw`, but did not save
`positive_bps`, `negative_abs_bps`, `Delta`, `Energy`, or `Z` per entry.
This note reconstructs the five-closed-outcome memory from:

```text
entries.parquet
exits.parquet
```

using the same pretrade principle:

```text
only outcomes closed before the current entry are allowed in memory.
```

The reconstruction is an audit approximation. It matches the saved `a_r5_raw`
closely in mean absolute error, with a few high-ratio differences caused by
very small denominators and event-order edge cases. The group-level conclusions
are therefore more reliable than individual reconstructed ratio equality.

## Main Correction

The statement "R5 does not dominate on ETHFIUSDC" was too coarse. The more
precise statement is:

```text
R5 alone is incomplete;
R5 + Delta/Energy separates useful memory from low-scale or stale memory;
but ETHFIUSDC still does not support blindly treating 11_r5_frames as the
highest-quality cell.
```

## Accepted Entries By Cell

These rows use actual accepted entries from the old four-cell fast run.

| cell | n | mean executable bps | median executable bps | hit rate | weighted bps | mean Delta bps | mean Energy bps | mean Z |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `10_r5_only` | 519 | 3.9992 | 2.5950 | 55.68% | 790.0280 | 39.8924 | 68.5768 | 4.7179 |
| `00_none` | 365 | 2.6867 | 2.5060 | 50.68% | 612.9078 | 34.0484 | 62.9161 | 4.2514 |
| `01_frames_only` | 201 | 3.6172 | 2.5984 | 57.21% | 583.2486 | 33.3263 | 54.3480 | 4.5230 |
| `11_r5_frames` | 256 | 1.8854 | 2.5880 | 54.30% | 289.0639 | 37.2649 | 62.1597 | 4.6373 |

The key observation is that `10_r5_only` is genuinely strong, but
`11_r5_frames` is not automatically stronger than `10`. Therefore the ETHFI
state does not behave like a monotone ladder:

```text
00 < 10 < 11
```

## Energy Tertiles

Across accepted entries with five closed outcomes available:

| Energy bucket | n | mean executable bps | median executable bps | hit rate | weighted bps | mean Delta bps | mean Energy bps |
|---|---:|---:|---:|---:|---:|---:|---:|
| low | 446 | 2.8534 | 2.4894 | 50.22% | 641.2555 | 19.3500 | 31.8840 |
| mid | 445 | 3.1505 | 2.6168 | 56.18% | 845.7248 | 36.8342 | 59.4553 |
| high | 445 | 3.5822 | 4.9727 | 56.63% | 789.9652 | 54.5124 | 100.2783 |

Energy is not a perfect quality score, but it fixes an important defect of
ratio-only `R5`: high-energy memories have larger median executable return and
better hit rate than low-energy memories.

## Delta Tertiles

Across accepted entries with five closed outcomes available:

| Delta bucket | n | mean executable bps | median executable bps | hit rate | weighted bps | mean Delta bps | mean Energy bps |
|---|---:|---:|---:|---:|---:|---:|---:|
| low | 446 | 2.8000 | 2.5465 | 52.69% | 707.3056 | 0.1613 | 53.7035 |
| mid | 445 | 2.6472 | 2.5823 | 55.06% | 568.5695 | 35.6520 | 51.7851 |
| high | 445 | 4.1390 | 2.6168 | 55.28% | 1001.0703 | 74.9264 | 86.0800 |

High `Delta_bps` is the strongest simple memory-strength readout in this audit.
This supports the earlier CCUSDT correction: ratio should be decomposed into
absolute cushion and realized energy.

## Cell Crossed With Delta

The most important conditional view:

| cell | Delta bucket | n | mean executable bps | hit rate | weighted bps |
|---|---|---:|---:|---:|---:|
| `10_r5_only` | low | 155 | 1.7265 | 49.03% | 100.3545 |
| `10_r5_only` | mid | 198 | 4.2332 | 59.60% | 326.0079 |
| `10_r5_only` | high | 166 | 5.8420 | 57.23% | 363.6656 |
| `11_r5_frames` | low | 73 | 1.9836 | 52.05% | 53.4329 |
| `11_r5_frames` | mid | 118 | 0.8239 | 52.54% | 67.6023 |
| `11_r5_frames` | high | 65 | 3.7021 | 60.00% | 168.0287 |
| `01_frames_only` | low | 69 | 4.5368 | 57.97% | 226.4367 |
| `01_frames_only` | mid | 54 | 1.5777 | 57.41% | 76.5670 |
| `01_frames_only` | high | 78 | 4.2157 | 56.41% | 280.2449 |

Interpretation:

```text
10_r5_only + high Delta is the cleanest old-four-cell memory state.
11_r5_frames only becomes respectable again at high Delta.
frames alone can still work, so frames should not be treated merely as a
weak version of R5.
```

## R5 Greater Than One, Split By Energy

Among entries where reconstructed `R5 >= 1`:

| bucket | n | mean executable bps | median executable bps | hit rate | weighted bps | mean Delta bps | mean Energy bps |
|---|---:|---:|---:|---:|---:|---:|---:|
| low Energy | 389 | 2.5507 | 2.5553 | 52.70% | 439.8960 | 26.1316 | 43.9830 |
| high Energy | 389 | 4.2762 | 5.0075 | 58.87% | 694.0259 | 51.4901 | 89.2720 |

This is the cleanest answer to the criticism. The binary `R5>=1` condition is
not enough. Conditional on `R5>=1`, high-energy memories are materially better
than low-energy memories.

## Financial Interpretation

`R5` answers:

```text
Did the last five closed shadow outcomes have more favorable than unfavorable
path shape?
```

`Delta` answers:

```text
How much net favorable cushion did that memory contain?
```

`Energy` answers:

```text
How much realized movement was present in that memory at all?
```

For ETHFIUSDC, the alpha center still appears to be the direct E0 active-flow
release trigger, but the sizing/state layer should not use `R5` alone. It
should use a low-degree memory tuple:

```text
M_t = (R5_t, Delta5_t, Energy5_t, Z5_t, frames_t)
```

The old four-cell model projected this tuple down to only:

```text
(1{R5 >= 1}, 1{frames >= threshold})
```

That projection is too lossy for migration analysis.

## Updated Strategy Hypothesis

The next ETHFIUSDC fast strategy comparison should test:

```text
E0_RELEASE_BASE
  entry: E0 trigger
  admission: prior-day q70 spread
  exit: fixed60 taker

E0_RELEASE_MEMORY_SIZED
  entry: same E0 trigger
  sizing:
    base size for E0
    boost for 10_r5_only with high Delta/Energy
    smaller or neutral size for 11 unless Delta is high
    preserve frames-only as its own sleeve, not as inferior R5
```

Do not promote this directly. Required controls remain:

```text
side-flip control
matched same-hour/spread/activity control
extra taker slippage stress
strict multi-day warm-start replay
```

## Bottom Line

The corrected conclusion is:

```text
R5 is useful, but R5 alone is not the factor.
Delta/Energy/Z are required to interpret the memory state.
ETHFIUSDC's best old-memory region is closer to
10_r5_only + high Delta/Energy than to blindly boosting 11_r5_frames.
```


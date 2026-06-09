# ETHFIUSDC Old Four-Cell Migration Test

Status: `research_result_20260602`.

Boundary: research-only. This test does not modify Runner, Bot, Monitor, or
runtime policy. Inputs are ETHFIUSDC raw Bullish trades/L2, canonical
quote_frame, and Rust-built `decision_frame_v1` cache.

## Question

The first ETHFIUSDC entry-trigger diagnostic showed that the simple
`E0_old_tfi_flat_q70` trigger is positive after top-of-book taker crossing.
This document tests the stronger migration question:

```text
Does the old CCUSDT four-cell + leverage/capacity strategy still work on
ETHFIUSDC, or was the E0 result only a loose trigger effect?
```

## Data

- Symbol: `ETHFIUSDC`
- Window: `2026-05-25..2026-05-31`
- Prior-day spread admission source: `2026-05-24..2026-05-30`
- Decision frame builder:
  `crates/cex_l2_research/src/bin/ccusdt_rust_decision_frame_cache.rs`
- Validated frames: `718019` rows over `2026-05-24..2026-05-31`

Admission thresholds:

```text
systems/ccusdt_replay_exchange/runs/admission_thresholds/
  ethfiusdc_entry_spread_q70_20260525_31_20260602.json
```

The prior-day q70 half-spread thresholds are about `2.57..2.72 bps`. This is
high versus CCUSDT, so all reported executable results must be interpreted as
surviving a large round-trip crossing burden.

## Fast Strategy Profile

Run:

```text
systems/ccusdt_replay_exchange/runs/experiments/
  ethfiusdc_old_fourcell_idle01_g1_fixed60_taker_q70_20260525_31_rustdf_v0_1
```

Profile:

```text
policy        = old_tfi_four_cell_shadow_v1
capacity      = core_idle01
idle01_gamma  = 1.0
leverage_cap  = 3.0
admission     = prior-day entry_spread_q70_v1
exit          = fixed60_taker
fill          = quote_frame top-of-book taker cross
fee_bps       = 0
```

## Main Result

| metric | value |
|---|---:|
| total entries | 1754 |
| actual entries after admission/capacity | 1341 |
| admission rejected | 413 |
| exits | 1754 |
| net weighted bps | 2275.2482 |
| positive days | 6 / 7 |
| worst day net weighted bps | -3.8940 |
| worst actual leg net bps | -55.5136 |
| max open exposure | 2.5 |

This is positive but materially smaller than the loose E0 trigger diagnostic.
The reason is not crossing arithmetic; it is structure/capacity selection. E0
counts every qualifying trigger independently, while the four-cell strategy has
closed-entry R5 state, fixed lot lifecycle, admission rejection, and capacity
clipping.

## Daily Result

| date | entries | accepted | actual exposure | net weighted bps |
|---|---:|---:|---:|---:|
| 2026-05-25 | 142 | 129 | 85.375 | 76.8211 |
| 2026-05-26 | 293 | 260 | 143.750 | 438.3071 |
| 2026-05-27 | 392 | 392 | 204.000 | 714.8913 |
| 2026-05-28 | 374 | 190 | 97.500 | 200.3757 |
| 2026-05-29 | 253 | 253 | 138.000 | 758.9899 |
| 2026-05-30 | 103 | 66 | 34.375 | 89.7573 |
| 2026-05-31 | 197 | 51 | 32.250 | -3.8940 |

## Cell Attribution

| cell | n | exposure | mean unit bps | weighted bps | hit |
|---|---:|---:|---:|---:|---:|
| `10_r5_only` | 519 | 196.875 | 3.9992 | 790.0280 | 55.68% |
| `00_none` | 365 | 228.125 | 2.6867 | 612.9078 | 50.68% |
| `01_frames_only` | 201 | 158.000 | 3.6172 | 583.2486 | 57.21% |
| `11_r5_frames` | 256 | 152.250 | 1.8854 | 289.0639 | 54.30% |

The migrated structure is not "only 11 works". On ETHFIUSDC, the strongest
contributor is `10_r5_only`, and the idle `01_frames_only` sleeve is also
meaningfully positive. This differs from the intuition that the full four-cell
structure should simply concentrate profit into `11_r5_frames`.

## Comparison With E0

The E0 trigger diagnostic on the same `2026-05-25..2026-05-31` window:

| trigger | n | mean executable 60s | positive days |
|---|---:|---:|---:|
| `E0_old_tfi_flat_q70` | 3278 | 2.7994 bps | 7 / 7 |

E0 is an entry trigger:

```text
abs(TFI) >= 1
abs(past_event_25_bps) <= 0.5
entry_cross_bps <= prior-day q70
fixed60 top-of-book taker label
```

It is not the full four-cell strategy. The four-cell migration has fewer actual
entries because it adds stateful closed-entry memory, capacity, and fixed lot
lifecycle. Therefore:

```text
E0 answers: "is the basic stale active-flow release present?"
Four-cell answers: "does the old CCUSDT stateful sizing/exposure machinery
transfer to this symbol?"
```

For ETHFIUSDC, the first answer is stronger than the second.

## Runner Cross-Check

A single-day Runner panel-sparse-fast-clock check was run for `2026-05-29`:

```text
systems/ccusdt_replay_exchange/runs/
  ethfiusdc_old_fourcell_runner_panel_20260529
```

Summary:

| metric | value |
|---|---:|
| panel frames sent | 90722 |
| intents/orders/fills | 506 / 506 / 506 |
| arrival_quote_lag_count | 0 |
| final realized PnL | 0.077765 |

The `506` fills correspond to `253` entry/exit pairs, matching the fast
strategy's `2026-05-29` entry count.

The strict consistency check found `253` matched entry timestamps and `5`
capacity/cell mismatches. These first mismatches are expected because the fast
run is a continuous seven-day run and therefore carries closed-entry R5 state
into `2026-05-29`, while the single-day Runner run starts from empty state.
This confirms a research requirement:

```text
Any strict migration check for old four-cell/R5 must either warm up or resume
Bot-owned state across day boundaries.
```

## Interpretation

ETHFIUSDC appears easier than CCUSDT for the base stale active-flow trigger:
the raw E0 structure survives unusually high top-of-book crossing. However, the
old CCUSDT four-cell machinery does not simply dominate E0. It remains positive
but reduces the candidate set and changes attribution.

Working hypothesis:

```text
CCUSDT needed R5/frames to organize noisy release.
ETHFIUSDC has a more direct active-flow stale-release effect, so R5/frames are
useful as capacity/sleeve language but not necessarily the alpha center.
```

## Next Research Gate

Before considering any promotion:

1. Run side-flip and matched-time controls for E0 and four-cell.
2. Run a strict multi-day/warm-start panel check so R5 state is continuous.
3. Compare `E0 trigger + simple capacity` against old four-cell machinery.
4. Evaluate extra taker pressure/slippage beyond displayed top-of-book.


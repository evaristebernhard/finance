# CCUSDT TFI Structure Multicoin Entry Trigger Pilot

Status: `research_pilot_20260602`. Research-only; no Runner/Bot/Monitor changes.

## Scope

This pilot tests whether the CCUSDT-style active-flow/stale-release entry
family has any portability to other Bullish symbols. It deliberately excludes
BTC/ETH/SOL from the first alpha-discovery basket because they are efficiency
controls, not good first-pass discovery instruments.

Requested first basket:

```text
ETHFIUSDC
IOTAUSDT
NIGHTUSDT
SUIUSDC
```

Actual usable first diagnostic:

```text
ETHFIUSDC: usable, 2026-05-29..2026-05-30 evaluated, 2026-05-28 used as prior threshold day.
IOTAUSDT: usable for 2026-05-29 only, 2026-05-28 used as prior threshold day.
SUIUSDC: raw download present, but canonical quote build failed on empty bid_price.
NIGHTUSDT: raw L2 incomplete in the interrupted download; skipped.
```

## Data Built

Downloaded raw data under:

```text
data/ccusdt/v1/external/
```

Canonical and decision-frame layers built:

| symbol | canonical status | decision_frame status | evaluated dates |
|---|---|---|---|
| `ETHFIUSDC` | quote/trade/L2 validate ok for `2026-05-28..2026-05-30` | 270,094 rows | `2026-05-29..2026-05-30` |
| `IOTAUSDT` | quote/trade/L2 validate ok for `2026-05-28..2026-05-29`; `2026-05-30` validate fails with EOF | 265,211 rows for first two days | `2026-05-29` |
| `SUIUSDC` | quote build failed: empty `bid_price` in raw book_ticker | not built | none |

Diagnostic outputs:

```text
systems/ccusdt_replay_exchange/runs/entry_trigger_family_diagnostic/
  ethfiusdc_2026-05-29_2026-05-30_multicoin_v0_1/
  iotausdt_2026-05-29_2026-05-29_multicoin_v0_1/
```

Per-symbol reports:

```text
docs/markets/ccusdt/research/strategy/v1-multicoin-entry-trigger-ethfiusdc-20260602.md
docs/markets/ccusdt/research/strategy/v1-multicoin-entry-trigger-iotausdt-20260602.md
```

## ETHFIUSDC Readout

The ETHFIUSDC first pass is meaningfully positive after top-of-book taker
spread.

Key rows:

| variant | n | mean exec 60s | mean mid 60s | hit rate | positive days |
|---|---:|---:|---:|---:|---:|
| `E0_old_tfi_flat_q70` | 781 | 4.9683 bps | 9.6359 bps | 58.39% | 2/2 |
| `E3_stale_giveway_release_z_w30_q80` | 154 | 6.5155 bps | 11.5740 bps | 68.18% | 2/2 |
| `E2_mild_pressure_giveway_l_w60_q80` | 419 | 6.0076 bps | 10.4103 bps | 57.04% | 2/2 |
| `E5_static_low_depth_control_q30` | 4,927 | 5.0381 bps | 9.6260 bps | 53.54% | 2/2 |

Capacity approximation:

| variant | actual entries | net weighted bps | mean unit net | positive days |
|---|---:|---:|---:|---:|
| `E5_static_low_depth_control_q30` | 3,435 | 5,273.0654 | 4.0936 | 2/2 |
| `E1_tfi_giveway_confirm_l_w30_q70` | 3,765 | 4,312.9162 | 3.0547 | 2/2 |
| `E1_tfi_giveway_confirm_l_w60_q70` | 3,601 | 4,244.0409 | 3.1429 | 2/2 |

Interpretation:

```text
ETHFIUSDC is a real migration candidate.
```

The old active-flow flat trigger itself is positive, and adding stale/giveway
can produce stronger unit rows. This is not enough for promotion because the
window is only two evaluated days and the report lacks matched controls, but it
is enough to justify a longer ETHFIUSDC-specific walk-forward diagnostic.

## IOTAUSDT Readout

IOTAUSDT is positive but weaker and only has one evaluated day in this pass.

Key rows:

| variant | n | mean exec 60s | mean mid 60s | hit rate | positive days |
|---|---:|---:|---:|---:|---:|
| `E0_old_tfi_flat_q70` | 729 | 0.6794 bps | 4.6350 bps | 43.76% | 1/1 |
| `E2_mild_pressure_giveway_z_w60_q80` | 380 | 6.8224 bps | 10.4328 bps | 57.11% | 1/1 |
| `E2_mild_pressure_giveway_l_w60_q80` | 382 | 6.0115 bps | 9.5531 bps | 53.93% | 1/1 |
| `E5_static_low_depth_control_q30` | 6,025 | 1.4567 bps | 5.1865 bps | 44.55% | 1/1 |

Capacity approximation:

| variant | actual entries | net weighted bps | mean unit net | positive days |
|---|---:|---:|---:|---:|
| `E1_tfi_giveway_confirm_l_w60_q70` | 3,240 | 3,483.3305 | 2.8669 | 1/1 |
| `E1_tfi_giveway_confirm_z_w60_q70` | 3,173 | 3,368.7493 | 2.8312 | 1/1 |
| `E1_tfi_giveway_confirm_l_w30_q70` | 3,193 | 3,202.0105 | 2.6742 | 1/1 |

Interpretation:

```text
IOTAUSDT is a possible migration candidate, but current evidence is too short.
```

The old trigger is positive but thin after spread. Giveway-confirmation rows
look better, but this is a one-day read and must not be promoted.

## What This Means

This pass changes the strategic read:

```text
The TFI/stale-release structure is not obviously CCUSDT-only.
```

ETHFIUSDC in particular shows positive top-of-book executable evidence across
two days. That is materially different from pure book-giveway on CCUSDT, where
mid edge was positive but executable edge was negative every day.

However, the pilot is still only a migration screen. It does not yet prove a
multi-coin strategy because:

- ETHFIUSDC has only two evaluated days.
- IOTAUSDT has only one evaluated day.
- No matched-random, side-flip, or same-time control has been run.
- Capacity logic is a reused approximation, not a symbol-specific portfolio
  allocator.
- The baseline overlap table is CCUSDT-specific and should be ignored for
  cross-symbol interpretation.

## Next Step

Do not broaden to many symbols yet. The next high-value step is:

```text
ETHFIUSDC 7-14 day walk-forward diagnostic
```

Required outputs:

```text
mid vs executable labels
old E0 active-flow flat trigger
E2/E3 giveway/stale variants
matched controls by date/hour/spread/trade activity
daily sign rate
tail/CVaR
capacity concentration
```

If ETHFIUSDC remains positive after controls, then add one more symbol
(`IOTAUSDT` or `NIGHTUSDT`) rather than jumping to a broad universe.


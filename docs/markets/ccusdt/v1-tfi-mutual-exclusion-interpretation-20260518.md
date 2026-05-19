# CCUSDT V1 TFI Mutual-Exclusion Interpretation

Status: `20260518_ccusdt_v1_tfi_mutual_exclusion_interpretation_v1`.

Guardrail: research-only structure interpretation. This is not an execution recommendation.

## Core Formula

For entry `i`, let `s_i` be the signal-aligned direction, where long continuation has `s_i = +1` and short continuation has `s_i = -1`.

```text
r_i(h) = 10000 * log(mid_{i+h} / mid_i)
G_i(h) = s_i * r_i(h)
N_i(h) = G_i(h) - C_i
Edge(S) = E[G_i(h) | i in S]
Tradable(S) = E[N_i(h) | i in S]
```

The key distinction is:

```text
positive gross median + roughly 2 bps cost can become negative net median
```

So a negative net median in the large flat TFI rows is not evidence that the price signal vanished. It says the central move is often smaller than the crossing/maker-light cost proxy, while the right tail still carries the mean.

## Trigger Meaning

The TFI family is best read as a delayed quote-release / continuation phenomenon:

- `trade_flow_imbalance` extreme means aggressive flow is one-sided.
- `past25_abs_le_0p5bps` means recent mid movement was nearly flat, so the flow has not yet been fully released into price.
- `stale_mid_ge25` means the quote/mid has been stale long enough for pressure to accumulate.
- `trade_present_stale_mid_ge25` means trades are active while the quote is stale, which is a stronger quote-catchup state.

Financially, this is not "momentum after price already moved". It is closer to:

```text
one-sided tape pressure + flat/stale mid = latent imbalance
if the quote catches up after entry, fixed-horizon gross return becomes positive
```

The competing explanation is absorption: the tape pressure is real, but resting liquidity absorbs it and price does not release. The mutually-exclusive buckets tell us which states are release-like and which are absorption/noise-like.

## Parent-Child Map

Fold3 entry-level overlap shows this hierarchy:

```text
TFI delayed-release family
├─ tfi_follow_flat: aggregate parent view of flat TFI continuation
│  ├─ tfi_short_flat: sell-pressure child
│  │  └─ tfi_short_stale25 + tfi_event_active: high-quality stale/active short release state
│  └─ tfi_long_flat: buy-pressure child
│     └─ tfi_event_active: long-side active quote-catchup slice
└─ exact-entry residuals caused by first-entry-per-bucket timing and non-parent state slices
```

Important overlap facts:

| Relation | Fold3 overlap read |
| --- | --- |
| `short_flat` inside `follow_flat` | `673 / 716 = 93.99%` |
| `long_flat` inside `follow_flat` | `456 / 493 = 92.49%` |
| `event_active` inside `follow_flat` | `180 / 210 = 85.71%` |
| `short_stale25` inside `event_active` | `131 / 131 = 100.00%` |
| `short_stale25` inside `short_flat` | `116 / 131 = 88.55%` |
| `long_flat` vs `short_flat` | `0` overlap |
| `long_flat` vs `short_stale25` | `0` overlap |

This means the original structures should not be "thrown away". They should be read as different coordinates on the same phenomenon:

- `follow_flat` is the parent aggregate.
- `short_flat` and `long_flat` are directional children.
- `event_active` is a state slice, not an unrelated strategy.
- `short_stale25` is a high-quality nested child discovered while decomposing the parent family.

## Fold3 Mutually-Exclusive Contribution

Fold3 has `1129` parent `follow_flat` entries, but its economic contribution is not homogeneous.

| Mutually-exclusive bucket | Entries | Gross mean | Gross median | Net mean | Net median | Total net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `follow+short` | 559 | 4.0249 | 1.5847 | 1.9835 | -0.5124 | 1108.7730 |
| `follow+long` | 390 | 4.2218 | 1.2993 | 2.1615 | -0.6752 | 843.0004 |
| `follow+short+stale25+event_active` | 114 | 7.8982 | 4.9748 | 5.8804 | 2.8471 | 670.3600 |
| `follow+long+event_active` | 66 | 4.9561 | 4.3946 | 2.9983 | 2.2486 | 197.8854 |
| `long` only | 35 | 4.7475 | 3.3744 | 2.6736 | 0.9939 | 93.5768 |
| `short+stale25+event_active` | 2 | 4.9437 | 4.9437 | 2.4401 | 2.4401 | 4.8803 |
| `stale25+event_active` | 15 | 2.3546 | 2.9332 | 0.2855 | 0.1407 | 4.2827 |
| `long+event_active` | 2 | 3.6964 | 3.6964 | 1.9662 | 1.9662 | 3.9323 |
| `event_active` only | 11 | 0.9067 | 1.2655 | -1.1342 | -0.6836 | -12.4765 |
| `short` only | 41 | 0.9042 | 0.0000 | -1.2194 | -1.9271 | -49.9957 |

The total net across these fold3 mutually-exclusive buckets is `2864.2186` bps. Positive buckets contribute `2926.6909` bps; the two negative unique buckets subtract only `62.4723` bps.

The largest total-net buckets are the broad `follow+short` and `follow+long` leaves. They have positive gross means and positive gross medians, but negative net medians because their median gross move is around `1.3..1.6` bps and average cost is around `2.04..2.06` bps. That is a cost-threshold issue, not proof that the signal has no information.

The cleanest entry-quality bucket is `follow+short+stale25+event_active`: `114` entries, `7.8982` bps gross mean, `4.9748` bps gross median, `5.8804` bps net mean, and `2.8471` bps net median. This is the approximately `130`-entry short stale/event structure in its high-overlap core.

## Right-Tail Source

The fold3 source summary confirms that the broad structures are right-tail mean structures. The top `10%` net winners exceed total net profit in every TFI row below, which means the rest of the distribution is a cost drag or loss drag against those winners.

| Structure | Entries | Net mean | Net median | Gross mean | Top 10% net / total net | Winners to cover total net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `tfi_follow_flat` | 1129 | 2.4978 | -0.3967 | 4.5385 | 1.5327 | 52 |
| `tfi_short_flat` | 716 | 2.4218 | -0.3931 | 4.4655 | 1.5397 | 33 |
| `tfi_long_flat` | 493 | 2.3091 | -0.6709 | 4.3553 | 1.7587 | 19 |
| `tfi_event_active` | 210 | 4.1374 | 2.2123 | 6.1432 | 1.1612 | 16 |
| `tfi_short_stale25` | 131 | 5.1872 | 2.5130 | 7.2183 | 1.1273 | 11 |

This is why "filtering away the right tail" breaks the phenomenon. The task is not to delete the right tail; it is to distinguish release tails from bad entries, preserve the release path, and cut failed-release left tails.

## What Each Structure Means

`tfi_follow_flat`

This is the broad family: signed TFI extreme while recent mid return is flat. Its financial meaning is "pressure exists, price has not yet released". It is useful as a parent sample and as a detector of the latent imbalance regime. It is not clean enough as one homogeneous execution rule because the central net is cost-compressed and the mean is right-tail heavy.

`tfi_short_flat`

This is the sell-pressure side of the same family. It is mostly inside `follow_flat` and disjoint from `long_flat`. Its broad leaf `follow+short` creates the largest fold3 total net, but net median is slightly negative after cost. Meaning: there is real short-side continuation information, but many entries are too small after cost unless the release extends.

`tfi_long_flat`

This is the buy-pressure side. It should not be discarded. It is mostly inside `follow_flat`, disjoint from `short_flat`, and its broad leaf contributes `843.0004` bps total net in fold3. The `long`-only residual has positive net mean and positive net median, but only `35` entries and a large left tail, so it is a state to understand rather than a standalone rule.

`tfi_event_active`

This is not a separate fourth strategy in the additive sense. It is a state overlay: trades are occurring while the quote/mid is stale. When it overlaps the parent/directional TFI structure, quality improves. When it appears alone, it is weak: `11` fold3 unique entries have negative net mean. Meaning: event activity helps only when paired with directional imbalance; activity alone is not the edge.

`tfi_short_stale25`

This is the high-quality nested child. It is fully inside `event_active`, mostly inside `short_flat`, and mostly inside `follow_flat`. It represents short-side quote release after a stale mid. Unlike the broad flat family, its gross median is large enough to survive the cost proxy in fold3. It should be carried as a child hypothesis, not dismissed as a random later filter.

## First-Principles Read

The observed structure is:

```text
TFI extreme says pressure direction
flat/stale mid says pressure has not yet been paid out
event-active stale tape says quote update may be delayed
future aligned mid move measures release
cost decides whether the release is tradable
```

So the research object is not simply "find TFI entries". It is:

```text
separate release states from absorption states
preserve the right tail that pays for cost
remove low-quality unique/event-only entries
control left-tail cases where quote release fails or reverses
```

That also explains the previous confusion:

- The original large structures did show information edge on gross movement.
- Their net medians became negative mostly because cost is larger than the typical central move.
- The right tail is not a nuisance to filter away; it is the current source of net mean.
- The `~130` entry stale/event short structure is a nested high-quality state inside the original family.
- A mutually-exclusive decomposition should keep all structures as labels, but avoid double-counting parent and child entries as independent strategies.

## Research Implication

The next clean model should be hierarchical:

```text
parent: flat TFI latent-imbalance regime
side: short vs long continuation child
state: stale/event-active quote-catchup child
quality: release-like vs absorption-like entry
exit/risk: preserve right-tail release while cutting failed-release left tail
```

This is a better representation than treating `follow_flat`, `short_flat`, `long_flat`, `event_active`, and `short_stale25` as five unrelated candidates.

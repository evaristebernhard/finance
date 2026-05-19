# BONK CEX V3 Cross-Venue Convergence Opportunity Analysis

Status: 2026-05-13. This is a diagnostic opportunity analysis for BONK1MUSDC / BONK1MUSDT convergence. It does not output executable trading rules, entries, exits, sizing, or an alpha claim.

## Inputs / Outputs

Inputs:

```text
date/bonk_v3_cross_venue_leadlag_summary.csv
date/bonk_v3_cross_venue_probe.csv
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Output:

```text
date/bonk_v3_cross_venue_convergence_opportunity.csv
docs/markets/bonk/v1-cex-v3-cross-venue-convergence-opportunity.md
```

Sample:

```text
pair panel rows: 59195
validation rows: 34509
time span: 2026-04-29T00:00:00Z .. 2026-05-12T22:59:00Z
barrier: 100 bps
horizons: 1h, 4h, 12h
```

## Method

The panel is rebuilt into paired BONK1MUSDC / BONK1MUSDT rows by timestamp and horizon. The convergence target is the actual horizon-end basis:

```text
basis_t = (USDC mid / USDT mid - 1) * 10_000
basis_compression_bps = abs(basis_t) - abs(basis_t+h)
relative_reversion_bps = -sign(basis_t) * (future_return_USDC - future_return_USDT)
```

Positive compression means the USDC/USDT basis narrowed. Positive relative reversion means the rich venue later underperformed the cheap venue on a relative basis. Directional BONK movement is reported separately as the pair-mean future return/residual and is not counted as convergence PnL.

Cost is a deliberately simple L2 proxy:

```text
entry-to-mid pair cost = (USDC spread + USDT spread) / 2
closed two-leg roundtrip spread cost = USDC spread + USDT spread
extra cost stress = 1/2/5 bps per execution * 4 executions
```

This cost proxy excludes exchange fees, borrow/funding, queue priority, latency, impact, partial fill, and inventory constraints. If the spread-only roundtrip is not covered, the result is not execution-ready.

## Lead-Lag Evidence Check

| H | abs-basis vs compression Spearman | high-low compression bps | abs-basis vs relative reversion Spearman | high-low relative reversion bps | abs-basis vs directional residual Spearman | high-low directional residual bps | same-sign folds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1h | 0.602 | 1.082 | 0.479 | 0.747 | -0.029 | -0.641 | 3 |
| 4h | 0.622 | 1.141 | 0.508 | 0.825 | -0.082 | -10.316 | 3 |
| 12h | 0.649 | 1.193 | 0.598 | 1.133 | -0.044 | -25.828 | 3 |

Read: abs basis is a strong convergence-state variable in validation folds: compression Spearman is about 0.60 to 0.65, and the high-vs-low compression delta is only about 1.1 to 1.2 bps. The relative reversion evidence is also consistent, but it is still bps-scale. Directional residual evidence is weak and unstable compared with convergence evidence.

## Probe Cross-Check

| H | signed-basis low compression flag | signed-basis mid compression flag | signed-basis high compression flag |
| --- | --- | --- | --- |
| 1h | 64.1% | 13.2% | 60.0% |
| 4h | 64.1% | 13.3% | 60.0% |
| 12h | 64.1% | 13.2% | 60.0% |

The original probe is mainly a fold-level guardrail. It supports the idea that cross-venue state matters, but it is signed-basis and flag based; the bps opportunity sizing below comes from the lead-lag summary and the rebuilt panel.

## Bps Opportunity Sizing

| H | diagnostic slice | abs-basis lower bound bps | rows | mean compression bps | median compression bps | mean relative reversion bps | median roundtrip spread cost bps | mean net after roundtrip spread bps | roundtrip cover rate | mean net to mid bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1h | top_10pct | 1.549 | 1152 | 1.003 | 0.799 | 1.163 | 3.987 | -2.765 | 1.6% | -0.881 |
| 1h | top_5pct | 2.022 | 577 | 1.225 | 1.370 | 1.304 | 4.051 | -2.547 | 3.1% | -0.661 |
| 1h | top_1pct | 2.712 | 116 | 2.085 | 2.134 | 2.282 | 3.102 | -1.531 | 12.9% | 0.277 |
| 4h | top_10pct | 1.549 | 1152 | 1.063 | 0.810 | 1.268 | 3.987 | -2.706 | 1.7% | -0.822 |
| 4h | top_5pct | 2.022 | 577 | 1.329 | 1.386 | 1.474 | 4.051 | -2.444 | 3.3% | -0.557 |
| 4h | top_1pct | 2.712 | 116 | 2.205 | 2.217 | 2.438 | 3.102 | -1.411 | 15.5% | 0.397 |
| 12h | top_10pct | 1.549 | 1152 | 1.226 | 1.321 | 1.606 | 3.987 | -2.632 | 2.5% | -0.703 |
| 12h | top_5pct | 2.022 | 577 | 1.878 | 1.609 | 1.951 | 4.051 | -2.107 | 6.2% | -0.114 |
| 12h | top_1pct | 2.712 | 116 | 2.889 | 2.914 | 2.943 | 3.102 | -1.018 | 27.5% | 0.935 |

Read: the gross convergence opportunity exists, but it is small. In validation, top-decile abs-basis slices show roughly 1.0 to 1.2 bps of mean compression, and even top-1% slices are only about 2 to 3 bps gross. The observed two-book roundtrip spread proxy is around 4 bps, so the spread-only closed-pair net remains negative in every horizon/slice shown.

## Cost Coverage

| H | median roundtrip spread bps | top-1% mean compression bps | top-1% net to mid bps | top-1% net roundtrip bps | top-1% net +1bp/exec bps | top-1% roundtrip cover rate |
| --- | --- | --- | --- | --- | --- | --- |
| 1h | 4.200 | 2.085 | 0.277 | -1.531 | -5.531 | 12.9% |
| 4h | 4.200 | 2.205 | 0.397 | -1.411 | -5.411 | 15.5% |
| 12h | 4.200 | 2.889 | 0.935 | -1.018 | -5.018 | 27.5% |

The most generous mark-to-mid view can become positive in the extreme tail, but a closed two-leg roundtrip is still negative on average before any explicit fee or latency/impact stress. Adding only 1 bps per execution subtracts another 4 bps from the pair roundtrip, which decisively removes the apparent bps-scale edge.

## Convergence PnL vs Directional PnL

| H | diagnostic slice | convergence compression bps | relative reversion bps | directional pair-mean return bps | directional pair-mean residual bps |
| --- | --- | --- | --- | --- | --- |
| 1h | top_10pct | 1.003 | 1.163 | -5.277 | -8.877 |
| 1h | top_1pct | 2.085 | 2.282 | -15.407 | -7.353 |
| 4h | top_10pct | 1.063 | 1.268 | -30.333 | -33.610 |
| 4h | top_1pct | 2.205 | 2.438 | -51.129 | -30.866 |
| 12h | top_10pct | 1.226 | 1.606 | -21.957 | -33.901 |
| 12h | top_1pct | 2.889 | 2.943 | 49.788 | 11.498 |

The directional pair-mean return/residual can be much larger than the convergence bps, but it is common BONK movement, not cross-venue convergence PnL. Counting that movement as convergence would mix a relative-value diagnostic with outright BONK direction. This analysis keeps them separate.

## Conclusion

BONK USDC/USDT cross-venue convergence is real as a diagnostic phenomenon: larger abs basis tends to compress, and the rich-vs-cheap venue differential tends to revert. The scale is the problem. The expected compression is around 1 bps in broad high-basis slices and only a few bps in the extreme tail, while observed two-leg roundtrip spread cost is about 4 bps before fees, impact, latency, borrow/funding, or inventory constraints.

So the conservative read is: useful for convergence monitoring, venue-state labeling, and later cost-aware validation; not enough to call an executable spread/cost-covered opportunity in this sample, and not a directional BONK rule.

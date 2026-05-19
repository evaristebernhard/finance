# BONK CEX V3 Factor Decay / Horizon Sensitivity

Status: 2026-05-13. This note summarizes candidate factor decay and horizon sensitivity for the existing BONK CEX V3 research panel. It is a research triage artifact only: no trading rule, no threshold rule, no sizing rule, and no alpha claim.

## Inputs and Outputs

Inputs:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
date/bonk_v3_candidate_factor_deep_dive.csv
date/bonk_v3_recent_regime_edge_summary.csv
```

Output CSV:

```text
date/bonk_v3_factor_decay_horizon_summary.csv
```

Important limitation: the current panel has 1h/4h/12h labels, not 5m/15m labels. The 5m/15m recommendations below are inferred from the existing 1h/4h/12h residual/path-width shape plus mechanism priors. They are not measured short-horizon performance.

## Method

- Start from the 22 active/watch rows in `date/bonk_v3_candidate_factor_deep_dive.csv`.
- Use `residual_edge`, primary 100bps edge, recent fold edge, placebo ratio, and `path_width_flag_rate` from the deep dive.
- Add panel-level 100bps path shape by `symbol + horizon_hours`: residual median, absolute residual median, path-width median, path-width p90, first-any hit rate, and upper-minus-lower first-passage rate.
- Add recent/regime-local attributes from `date/bonk_v3_recent_regime_edge_summary.csv`: fold locality, best regime gate, recent rolling48 max residual, max regime improvement, and Fold3 all-control health.
- Classify each row into a decay action class:
  - `required_5m_15m_leadlag`
  - `required_5m_15m_microstructure`
  - `optional_5m_15m_depth_decay`
  - `optional_15m_decay_sanity`
  - `no_5m_15m_regime_only`
  - diagnostic-only variants

## Executive Read

The panel-level horizon shape is monotonic: 1h has thin path width, 4h has tradable movement width, and 12h is mostly regime/path state. At 100bps, median path width is about 88bps at 1h, 192bps at 4h, and 346bps at 12h for both BONK1MUSDC and BONK1MUSDT.

This makes the current candidate book split cleanly:

- Cross-venue spread-diff rows need 5m/15m lead-lag decay before any directional wording. A true venue lead should decay fast; otherwise the current 4h/12h evidence is common regime or venue staleness.
- Microprice rows need 5m/15m microstructure decay before accepting the 4h/12h read. Current rows have placebo/path-width sensitivity, so the safer read is book-pressure diagnostic.
- Top-depth rows are mostly 4h/12h liquidity-regime candidates. 15m is useful as an optional execution sanity check, but the main signal surface is not 5m.
- Low BONK RV context rows should stay 4h/12h regime gates. Short decay is not the right validation question.
- Activity rows remain participation/path-width diagnostics and should not be prioritized as short-horizon direction candidates.

## Panel Horizon Baseline

Primary 100bps panel read:

| symbol | h | abs resid med bps | path width med bps | 100bps any hit | upper-lower |
| --- | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDC | 1 | 23.2 | 87.6 | 27.7% | 0.8% |
| BONK1MUSDC | 4 | 45.6 | 191.3 | 75.7% | 8.6% |
| BONK1MUSDC | 12 | 80.4 | 345.8 | 98.0% | 13.8% |
| BONK1MUSDT | 1 | 23.3 | 88.5 | 27.9% | 0.8% |
| BONK1MUSDT | 4 | 45.4 | 192.2 | 76.1% | 8.5% |
| BONK1MUSDT | 12 | 79.9 | 345.8 | 98.0% | 13.8% |

Read: 1h is too thin to infer 5m/15m decay from. 4h is the first horizon with enough path-width to support regime-local research. 12h almost always touches a 100bps barrier, so it is more regime/path-width than precise direction.

## Candidate Decay Summary

| mech | symbol | h | factor | bucket | status | resid | path flag | shape | decay class |
| --- | --- | ---: | --- | --- | --- | ---: | ---: | --- | --- |
| activity | BONK1MUSDT | 1 | trade_notional_quote_sum | low | watch | 0.6% | 15.3% | 1h_only_candidate | low_priority_5m_15m_diagnostic_only |
| activity | BONK1MUSDT | 4 | snapshot_count | low | watch | 3.9% | 3.7% | 4h_only_candidate | no_5m_15m_diagnostic_only |
| spread | BONK1MUSDC | 1 | top_depth_total_notional_median | high | watch | 3.2% | 2.7% | slow_build_1h_to_12h | optional_5m_15m_depth_decay |
| spread | BONK1MUSDC | 4 | top_depth_total_notional_median | high | watch | 8.3% | 4.7% | slow_build_1h_to_12h | optional_15m_decay_sanity |
| spread | BONK1MUSDC | 12 | top_depth_total_notional_median | high | watch | 12.5% | 3.4% | slow_build_1h_to_12h | no_5m_15m_regime_only |
| spread | BONK1MUSDT | 1 | top_depth_total_notional_median | high | watch | 3.7% | 1.6% | slow_build_1h_to_12h | optional_5m_15m_depth_decay |
| spread | BONK1MUSDT | 4 | top_depth_total_notional_median | high | active_candidate | 11.7% | 2.7% | slow_build_1h_to_12h | optional_15m_decay_sanity |
| spread | BONK1MUSDT | 12 | top_depth_total_notional_median | high | watch | 15.5% | 1.6% | slow_build_1h_to_12h | no_5m_15m_regime_only |
| microprice | BONK1MUSDC | 12 | snapshot_microprice_offset_bps_mean | low | watch | 4.2% | 7.6% | 12h_only_candidate | required_5m_15m_microstructure |
| microprice | BONK1MUSDT | 4 | snapshot_microprice_offset_bps_mean | low | watch | 3.5% | 10.6% | slow_build_4h_to_12h_no_active_1h | required_5m_15m_microstructure |
| microprice | BONK1MUSDT | 4 | microprice_offset_bps_mean | low | watch | 2.6% | 10.8% | slow_build_4h_to_12h_no_active_1h | required_5m_15m_microstructure |
| microprice | BONK1MUSDT | 12 | snapshot_microprice_offset_bps_mean | low | watch | 4.4% | 4.5% | slow_build_4h_to_12h_no_active_1h | required_5m_15m_microstructure |
| microprice | BONK1MUSDT | 12 | microprice_offset_bps_mean | low | watch | 3.1% | 4.4% | slow_build_4h_to_12h_no_active_1h | required_5m_15m_microstructure |
| cross-venue | BONK1MUSDC | 4 | cross_venue_spread_diff_bps | low | watch | 5.3% | 7.9% | 4h_peak_no_active_1h | required_5m_15m_leadlag |
| cross-venue | BONK1MUSDC | 12 | cross_venue_spread_diff_bps | low | watch | 4.7% | 5.8% | 4h_peak_no_active_1h | required_5m_15m_leadlag |
| cross-venue | BONK1MUSDT | 1 | cross_venue_spread_diff_bps | high | watch | 1.8% | 11.6% | 4h_peak_with_1h_support | required_5m_15m_leadlag |
| cross-venue | BONK1MUSDT | 4 | cross_venue_spread_diff_bps | high | watch | 5.2% | 7.7% | 4h_peak_with_1h_support | required_5m_15m_leadlag |
| cross-venue | BONK1MUSDT | 12 | cross_venue_spread_diff_bps | high | watch | 4.7% | 5.1% | 4h_peak_with_1h_support | required_5m_15m_leadlag |
| context | BONK1MUSDC | 4 | ctx_bonk_rv_1h_bps | low | watch | 14.7% | 2.6% | slow_build_4h_to_12h_no_active_1h | no_5m_15m_regime_only |
| context | BONK1MUSDC | 12 | ctx_bonk_rv_1h_bps | low | watch | 16.9% | 0.5% | slow_build_4h_to_12h_no_active_1h | no_5m_15m_regime_only |
| context | BONK1MUSDT | 4 | ctx_bonk_rv_1h_bps | low | active_candidate | 15.0% | 2.2% | slow_build_4h_to_12h_no_active_1h | no_5m_15m_regime_only |
| context | BONK1MUSDT | 12 | ctx_bonk_rv_1h_bps | low | watch | 16.9% | 0.5% | slow_build_4h_to_12h_no_active_1h | no_5m_15m_regime_only |

Action counts:

| decay class | rows | read |
| --- | ---: | --- |
| `required_5m_15m_microstructure` | 5 | Must test fast decay before describing microprice as directional. |
| `required_5m_15m_leadlag` | 5 | Must test fast lead-lag before describing cross-venue dislocation as directional. |
| `optional_5m_15m_depth_decay` | 2 | Useful for execution timing, but depth remains regime-led. |
| `optional_15m_decay_sanity` | 2 | 4h depth is the main surface; 15m is a sanity check. |
| `no_5m_15m_regime_only` | 6 | Keep as 4h/12h regime gates. |
| diagnostic-only variants | 2 | Do not prioritize as directional decay candidates. |

## Mechanism Notes

### Cross-Venue

Cross-venue spread-diff has the clearest need for 5m/15m work. The USDT high bucket has 1h/4h/12h candidate support, but residual edge peaks around 4h and path-width flags remain visible. The USDC low bucket only appears at 4h/12h in active/watch rows.

Conservative read: this is not yet a lead-lag signal. Add 5m/15m labels and require the same signed bucket to work before venue-staleness or common-regime explanations are relaxed.

### Microprice

Microprice and snapshot microprice low buckets show 4h/12h support, especially BONK1MUSDT, but placebo ratios and path-width flags are the blocker. Because microprice is a microstructure variable, a real directional effect should have a short decay footprint.

Conservative read: add 5m/15m first. If short decay is absent, keep these rows as book-pressure/path-width diagnostics rather than direction.

### Spread / Depth

`top_depth_total_notional_median=high` is the cleanest structural family. Both symbols have a slow-build profile from 1h to 12h, and path-width flag rates are low. This supports a liquidity-regime read more than a fast-entry read.

Conservative read: keep 4h as the primary research horizon and 12h as regime confirmation. Add 15m only as an optional sanity check for execution timing, not as the core validation gate.

### Context

`ctx_bonk_rv_1h_bps=low` is a regime gate. It has high 4h/12h residual edge and low path-width flags, but placebo sensitivity means it should not be marketed as standalone direction.

Conservative read: no 5m/15m priority. Validate the same low-RV gate at 4h/12h in the next window.

### Activity

Activity rows are weak. The 1h low-notional row has tiny residual edge and the largest path-width flag rate in the active/watch set. The 4h low snapshot-count row is mixed and remains a participation diagnostic.

Conservative read: do not prioritize activity for short-horizon directional decay. Only revisit 5m/15m if the question is specifically quiet-state path widening.

## Next Validation Plan

1. Add 5m/15m labels for cross-venue spread-diff and microprice rows first.
2. Keep depth/top-liquidity validation anchored at 4h, with optional 15m decay as an execution sanity check.
3. Keep low BONK RV as a 4h/12h regime gate; do not spend short-horizon budget there first.
4. In the next window, pre-register the exact `symbol + factor + bucket + horizon` from the CSV. A candidate only advances if residual edge survives without path-width/placebo becoming the main explanation.

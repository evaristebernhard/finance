# BONK CEX V3 Path Profit Sanity

Status: 2026-05-13T10:29:46Z. This is a gross opportunity and visible-spread sanity check for BONK V3 path candidates. It is research-only: not a profit promise, not a trading rule, not an execution plan, and not an alpha claim.

## Inputs and Outputs

Inputs:

- `date/bonk_v3_candidate_factor_deep_dive.csv`
- `date/bonk_v3_recent_regime_edge_summary.csv`
- `date/bonk_v3_residual_path_factor_summary.csv`
- `date/bonk_v1_cex_l2_summary_20260513_bullish_l2_basket_price_v1.csv`

Output CSV:

- `date/bonk_v3_path_profit_sanity.csv`

## Method

Candidate universe is the current `active` / `watch` set from `bonk_v3_recent_regime_edge_summary.csv`: 26 candidates, status_counts={'watch': 21, 'active': 5}. Of those, 22 rows are present in the candidate deep dive; 4 recent-only rows are exploratory spread candidates.

Gross bps opportunity is a deliberately simple diagnostic:

```text
gross_bps_opportunity = edge_residual_for_gross * barrier_bps
```

`edge_residual_for_gross` is the bucket-row-weighted `100 bps` controlled-fold residual edge from the recent/regime summary. The CSV also keeps Fold3-only gross, deep-dive gross where available, fold stability, placebo/path-width flags, and path-label context.

Path-width capture scenarios are not expected PnL. They ask what `5%`, `10%`, or `20%` capture of the Fold3 median path width would look like before fees, queue position, fill risk, adverse selection, and slippage:

```text
path_width_capture_Xpct_bps = fold3_path_width_median_bps * X%
```

Spread sanity uses the median displayed Bullish spread from the L2 summary. `round_trip_spread_bps_est` is set equal to one displayed spread, approximating half-spread entry plus half-spread exit around mid. This is only a first visible-cost screen; venue fees, market impact, latency, rejects, inventory, borrow/funding, and implementation details are not included.

## L2 Spread Baseline

| Symbol | State rows | First ts | Last ts | Median spread bps | Trades |
| --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 20103 | 2026-04-29T00:00:00Z | 2026-05-12T23:59:00Z | 2.74 | 388533 |
| BONK1MUSDT | 20127 | 2026-04-29T00:00:00Z | 2026-05-12T23:59:00Z | 1.59 | 45839 |

## Executive Read

At the `100 bps` barrier, spread sanity buckets are: `{'gross_2_to_5x_spread_before_fees_slippage': 13, 'gross_gt_5x_spread_before_fees_slippage': 8, 'gross_1_to_2x_spread_thin_before_fees_slippage': 4, 'gross_below_median_round_trip_spread': 1}`. Path classes at the same barrier are: `{'regime_flip_not_stable_direction': 21, 'path_width_state_not_direction': 5}`.

The visible-spread check is not the blocker for many 4h/12h candidates: several gross scenarios are above the median displayed spread. The blocker is interpretation. The residual/path summary says 4h and 12h are mostly `regime_flip_not_stable_direction`; the path is wide, but the Fold2-to-Fold3 direction flips. That makes these path-width/regime candidates, not direction rules.

The weakest rows remain short-horizon or low-edge rows where `edge_residual * barrier` does not clear median spread. Those should stay diagnostics unless a future pre-registered window improves both residual edge and non-overlap evidence.

## Active Candidate Sanity, 100 bps

| Candidate | Score | Gross bps | Gross - spread | Fold3 gross bps | Read |
| --- | --- | --- | --- | --- | --- |
| BONK1MUSDT 4h top_depth_total_notional_median=high | 70.4 | 12.61 | 11.02 | 9.74 | gross scenario clears displayed-spread-only check; 5pct Fold3 path-width capture also clears displayed spread; path data says regime/path-width, not stable direction |
| BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | 68.8 | 14.41 | 12.82 | 5.96 | gross scenario clears displayed-spread-only check; 5pct Fold3 path-width capture also clears displayed spread; path data says regime/path-width, not stable direction |
| BONK1MUSDT 4h cross_venue_spread_diff_bps=high | 66.4 | 5.98 | 4.39 | 11.70 | gross scenario has some displayed-spread room but remains execution-sensitive; 5pct Fold3 path-width capture also clears displayed spread; path data says regime/path-width, not stable direction |
| BONK1MUSDT 4h snapshot_microprice_offset_bps_mean=low | 64.6 | 3.58 | 2.00 | 8.70 | gross scenario has some displayed-spread room but remains execution-sensitive; 5pct Fold3 path-width capture also clears displayed spread; path data says regime/path-width, not stable direction |
| BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | 64.4 | 14.08 | 11.34 | 5.74 | gross scenario clears displayed-spread-only check; 5pct Fold3 path-width capture also clears displayed spread; path data says regime/path-width, not stable direction |

## Top Gross Minus Spread, 100 bps

| Status | Symbol | H | Candidate | Edge residual | Gross bps | Spread bps | Gross - spread | Fold3 gross | Path class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| watch | BONK1MUSDT | 12h | ctx_bonk_rv_1h_bps=low | 19.1% | 19.06 | 1.59 | 17.48 | 18.22 | regime_flip_not_stable_direction |
| watch | BONK1MUSDC | 12h | ctx_bonk_rv_1h_bps=low | 19.1% | 19.08 | 2.74 | 16.34 | 18.38 | regime_flip_not_stable_direction |
| watch | BONK1MUSDT | 12h | top_depth_total_notional_median=high | 17.7% | 17.68 | 1.59 | 16.09 | 25.42 | regime_flip_not_stable_direction |
| watch | BONK1MUSDT | 4h | spread_bps_last=high | 16.8% | 16.83 | 1.59 | 15.24 | n/a | regime_flip_not_stable_direction |
| active | BONK1MUSDT | 4h | ctx_bonk_rv_1h_bps=low | 14.4% | 14.41 | 1.59 | 12.82 | 5.96 | regime_flip_not_stable_direction |
| active | BONK1MUSDC | 4h | ctx_bonk_rv_1h_bps=low | 14.1% | 14.08 | 2.74 | 11.34 | 5.74 | regime_flip_not_stable_direction |
| active | BONK1MUSDT | 4h | top_depth_total_notional_median=high | 12.6% | 12.61 | 1.59 | 11.02 | 9.74 | regime_flip_not_stable_direction |
| watch | BONK1MUSDC | 12h | top_depth_total_notional_median=high | 13.7% | 13.70 | 2.74 | 10.97 | 15.42 | regime_flip_not_stable_direction |
| watch | BONK1MUSDC | 4h | spread_bps_last=high | 12.4% | 12.38 | 2.74 | 9.64 | n/a | regime_flip_not_stable_direction |
| watch | BONK1MUSDC | 4h | top_depth_total_notional_median=high | 8.3% | 8.28 | 2.74 | 5.55 | 3.75 | regime_flip_not_stable_direction |

## Thin Rows, 100 bps

These rows fail even the visible-spread-only screen. This does not prove they are impossible, but it does mean the current gross diagnostic has no room for fees/slippage/model error.

| Status | Symbol | H | Candidate | Gross bps | Spread bps | Read |
| --- | --- | --- | --- | --- | --- | --- |
| watch | BONK1MUSDT | 1h | trade_notional_quote_sum=low | 0.53 | 1.59 | gross_below_median_round_trip_spread |

## Path-Width Capture Scenarios

| Symbol | H | Spread bps | Fold3 path width bps | 5% capture | 10% capture | 20% capture | Path class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 1h | 2.74 | 92.9 | 4.64 | 9.29 | 18.58 | path_width_state_not_direction |
| BONK1MUSDT | 1h | 1.59 | 93.5 | 4.68 | 9.35 | 18.71 | path_width_state_not_direction |
| BONK1MUSDC | 4h | 2.74 | 198.2 | 9.91 | 19.82 | 39.63 | regime_flip_not_stable_direction |
| BONK1MUSDT | 4h | 1.59 | 198.2 | 9.91 | 19.82 | 39.64 | regime_flip_not_stable_direction |
| BONK1MUSDC | 12h | 2.74 | 364.6 | 18.23 | 36.46 | 72.91 | regime_flip_not_stable_direction |
| BONK1MUSDT | 12h | 1.59 | 364.5 | 18.23 | 36.45 | 72.91 | regime_flip_not_stable_direction |

Read this table as a feasibility envelope, not a strategy. A path-width capture number clearing spread only says the future high-low range was wide enough in aggregate; it says nothing about whether an executable order could enter, exit, size, avoid adverse selection, or know the path direction in advance.

## Bottom Line

- The cleanest gross-vs-spread rows are 4h/12h context, depth, and some recent cross-venue/microprice states, but the path evidence remains regime-local.
- 12h rows have attractive gross/path-width arithmetic but heavy overlap and direction flip risk; they should be path-width/regime-state candidates, not directional entries.
- 1h candidates are mostly thin after the visible-spread screen, except as movement or tail diagnostics.
- No row in this report is a return forecast. Advancing any candidate requires a pre-registered next-window test with the same symbol, factor, bucket, horizon, barrier, and regime gate, plus explicit fee/slippage/fill modeling.

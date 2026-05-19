# BONK CEX V3 Candidate Factor Deep Dive

Status: 2026-05-13. This note uses the `20260513_bullish_l2_basket_price_v1` V3 candidate book and controlled factor tests. It ranks active/watch research candidates only. Every row is a `candidate`, not a trading rule, not a production signal, and not an alpha claim.

## Inputs and Outputs

Inputs:

- `date/bonk_v3_candidate_factor_book.csv`
- `date/bonk_v3_candidate_factor_book_summary.json`
- `date/bonk_v1_controlled_factor_tests_20260513_bullish_l2_basket_price_v1.csv`

Output CSV:

- `date/bonk_v3_candidate_factor_deep_dive.csv`

## Method

- Universe: only `active_candidate` and `watch` rows from the V3 candidate book; rows=22, status_counts={'watch': 20, 'active_candidate': 2}.
- Recent fold: `fold3`, defined by the source summary as the highest numeric fold suffix in controlled factor tests.
- Join key: `symbol + horizon_hours + factor_family + factor + selected_bucket/factor_bucket`.
- Primary barrier for deep-dive diagnostics: `100` bps. All-barrier weighted metrics are also kept in the CSV.
- Weighting: controlled-test rows are weighted by `bucket_rows` when aggregating residual edge, placebo, positive-share, and red-flag rates.
- CSV sort order: mechanism order `activity -> spread -> microprice -> cross-venue -> context`, then symbol, horizon, recent fold, placebo/path-width red-flag rank, candidate score.

Red-flag thresholds used here:

- Placebo: `clear <0.75x`, `watch >=0.75x`, `medium >=1.0x`, `high >=1.5x`, where x is `abs(placebo_edge_upper) / abs(edge_residual)`.
- Path-width: `clear <5%`, `watch >=5%`, `medium >=10%`, `high >=25%` or source `path_width_flag=true`.
- Forward split and non-overlap are retained as supporting stability flags, but they do not promote any row into a trading rule.

## Executive Read

- Active/watch mechanism mix: activity=2, spread=6, microprice=5, cross-venue=5, context=4.
- The two active candidates are both 4h BONK1MUSDT: `top_depth_total_notional_median=high` and `ctx_bonk_rv_1h_bps=low`. The spread/depth row is cleaner because placebo is below 0.75x. The context/RV row is useful but placebo-sensitive, so it should be read as regime utility first.
- Cross-venue spread-diff candidates have visible recent fold support at 4h/12h, but most have placebo ratios above 1.0x and several have path-width watch rates. Treat them as venue-dislocation diagnostics until lag/placebo validation can show a lead-lag mechanism.
- Microprice-offset low buckets are repeatedly positive in the recent fold, especially BONK1MUSDT 4h/12h, but placebo ratios are mostly 1.25x to 1.64x. That blocks alpha wording; these stay book-pressure diagnostics.
- Activity candidates are weakest and path-width-sensitive: low `trade_notional_quote_sum` at 1h has a 15.3% path-width flag rate, so it is more likely a movement-width or quiet-state candidate than a directional rule.
- No active/watch row has source `path_width_flag=true`, but several exceed the 5% or 10% watch thresholds. The absence of a high path-width flag is not enough to call directionality clean.

Flag distribution in this deep dive:

- Placebo flags: {'medium_placebo_ge_1_0x': 10, 'high_placebo_ge_1_5x': 5, 'watch_placebo_ge_0_75x': 4, 'clear_placebo_lt_0_75x': 3}
- Path-width flags: {'clear_path_width_lt_5pct': 13, 'watch_path_width_ge_5pct': 5, 'medium_path_width_ge_10pct': 4}

## Top Rows by Candidate Score

| rank | status | mechanism | symbol | h | factor=bucket | score | residual | recent fold | placebo | path-width | read |
| ---: | --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- |
| 1 | active_candidate | spread | BONK1MUSDT | 4 | top_depth_total_notional_median=high | 70.4 | 0.1166 | 0.0843 | 0.57x clear_placebo_lt_0_75x | 2.7% clear_path_width_lt_5pct | priority_research_candidate |
| 2 | active_candidate | context | BONK1MUSDT | 4 | ctx_bonk_rv_1h_bps=low | 68.8 | 0.1505 | 0.0435 | 1.21x medium_placebo_ge_1_0x | 2.2% clear_path_width_lt_5pct | regime_utility_candidate |
| 3 | watch | cross-venue | BONK1MUSDT | 4 | cross_venue_spread_diff_bps=high | 66.4 | 0.0525 | 0.1117 | 1.10x medium_placebo_ge_1_0x | 7.7% watch_path_width_ge_5pct | confounded_watch_candidate |
| 4 | watch | microprice | BONK1MUSDT | 4 | snapshot_microprice_offset_bps_mean=low | 64.6 | 0.0352 | 0.0819 | 1.38x medium_placebo_ge_1_0x | 10.6% medium_path_width_ge_10pct | path_width_watch_candidate |
| 5 | watch | context | BONK1MUSDC | 4 | ctx_bonk_rv_1h_bps=low | 64.4 | 0.1474 | 0.0416 | 1.20x medium_placebo_ge_1_0x | 2.6% clear_path_width_lt_5pct | regime_utility_candidate |
| 6 | watch | cross-venue | BONK1MUSDC | 4 | cross_venue_spread_diff_bps=low | 61.8 | 0.0528 | 0.1127 | 1.29x medium_placebo_ge_1_0x | 7.9% watch_path_width_ge_5pct | confounded_watch_candidate |
| 7 | watch | spread | BONK1MUSDT | 1 | top_depth_total_notional_median=high | 61.4 | 0.0372 | 0.0359 | 0.87x watch_placebo_ge_0_75x | 1.6% clear_path_width_lt_5pct | watch_research_candidate |
| 8 | watch | context | BONK1MUSDC | 12 | ctx_bonk_rv_1h_bps=low | 61.2 | 0.1688 | 0.1411 | 1.60x high_placebo_ge_1_5x | 0.5% clear_path_width_lt_5pct | regime_utility_candidate |

## Mechanism-Sorted Deep Dive

| sort | mechanism | status | symbol | h | factor=bucket | score | fold3 edge | 100bps fold3 | placebo | path-width | stability | conservative read |
| ---: | --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| 1 | activity | watch | BONK1MUSDT | 1 | trade_notional_quote_sum=low | 49.4 | 0.0286 | 0.0286 | 0.64x | 15.3% | fwd_min=-0.0028, non_overlap=-0.0039 | path_width_watch_candidate |
| 2 | activity | watch | BONK1MUSDT | 4 | snapshot_count=low | 52.9 | 0.0149 | 0.0149 | 1.28x | 3.7% | fwd_min=-0.0296, non_overlap=0.0275 | confounded_watch_candidate |
| 3 | spread | watch | BONK1MUSDC | 1 | top_depth_total_notional_median=high | 48.7 | 0.0189 | 0.0189 | 1.86x | 2.7% | fwd_min=-0.0540, non_overlap=-0.0632 | confounded_watch_candidate |
| 4 | spread | watch | BONK1MUSDC | 4 | top_depth_total_notional_median=high | 58.3 | 0.0277 | 0.0277 | 0.96x | 4.7% | fwd_min=-0.0616, non_overlap=-0.1291 | watch_research_candidate |
| 5 | spread | watch | BONK1MUSDC | 12 | top_depth_total_notional_median=high | 57.2 | 0.1307 | 0.1307 | 0.84x | 3.4% | fwd_min=-0.0296, non_overlap=0.0143 | watch_research_candidate |
| 6 | spread | watch | BONK1MUSDT | 1 | top_depth_total_notional_median=high | 61.4 | 0.0359 | 0.0359 | 0.87x | 1.6% | fwd_min=-0.0564, non_overlap=-0.0302 | watch_research_candidate |
| 7 | spread | active_candidate | BONK1MUSDT | 4 | top_depth_total_notional_median=high | 70.4 | 0.0843 | 0.0843 | 0.57x | 2.7% | fwd_min=-0.0717, non_overlap=-0.0249 | priority_research_candidate |
| 8 | spread | watch | BONK1MUSDT | 12 | top_depth_total_notional_median=high | 57.1 | 0.2230 | 0.2230 | 0.92x | 1.6% | fwd_min=-0.0215, non_overlap=0.0310 | watch_research_candidate |
| 9 | microprice | watch | BONK1MUSDC | 12 | snapshot_microprice_offset_bps_mean=low | 58.2 | 0.0653 | 0.0653 | 1.41x | 7.6% | fwd_min=-0.0070, non_overlap=0.0534 | confounded_watch_candidate |
| 10 | microprice | watch | BONK1MUSDT | 4 | snapshot_microprice_offset_bps_mean=low | 64.6 | 0.0819 | 0.0819 | 1.38x | 10.6% | fwd_min=-0.0232, non_overlap=-0.0043 | path_width_watch_candidate |
| 11 | microprice | watch | BONK1MUSDT | 4 | microprice_offset_bps_mean=low | 58.7 | 0.0618 | 0.0618 | 1.26x | 10.8% | fwd_min=-0.0230, non_overlap=0.0233 | path_width_watch_candidate |
| 12 | microprice | watch | BONK1MUSDT | 12 | snapshot_microprice_offset_bps_mean=low | 57.5 | 0.1220 | 0.1220 | 1.51x | 4.5% | fwd_min=-0.0109, non_overlap=0.1661 | confounded_watch_candidate |
| 13 | microprice | watch | BONK1MUSDT | 12 | microprice_offset_bps_mean=low | 50.8 | 0.0933 | 0.0933 | 1.64x | 4.4% | fwd_min=-0.0127, non_overlap=0.1336 | confounded_watch_candidate |
| 14 | cross-venue | watch | BONK1MUSDC | 4 | cross_venue_spread_diff_bps=low | 61.8 | 0.1127 | 0.1127 | 1.29x | 7.9% | fwd_min=-0.0323, non_overlap=0.0904 | confounded_watch_candidate |
| 15 | cross-venue | watch | BONK1MUSDC | 12 | cross_venue_spread_diff_bps=low | 54.5 | 0.1446 | 0.1446 | 1.12x | 5.8% | fwd_min=-0.0374, non_overlap=0.2897 | confounded_watch_candidate |
| 16 | cross-venue | watch | BONK1MUSDT | 1 | cross_venue_spread_diff_bps=high | 54.7 | 0.0374 | 0.0374 | 0.67x | 11.6% | fwd_min=-0.0279, non_overlap=-0.0126 | path_width_watch_candidate |
| 17 | cross-venue | watch | BONK1MUSDT | 4 | cross_venue_spread_diff_bps=high | 66.4 | 0.1117 | 0.1117 | 1.10x | 7.7% | fwd_min=-0.0318, non_overlap=-0.0006 | confounded_watch_candidate |
| 18 | cross-venue | watch | BONK1MUSDT | 12 | cross_venue_spread_diff_bps=high | 54.5 | 0.1447 | 0.1447 | 1.11x | 5.1% | fwd_min=-0.0373, non_overlap=0.1769 | confounded_watch_candidate |
| 19 | context | watch | BONK1MUSDC | 4 | ctx_bonk_rv_1h_bps=low | 64.4 | 0.0416 | 0.0416 | 1.20x | 2.6% | fwd_min=-0.0759, non_overlap=-0.0211 | regime_utility_candidate |
| 20 | context | watch | BONK1MUSDC | 12 | ctx_bonk_rv_1h_bps=low | 61.2 | 0.1411 | 0.1411 | 1.60x | 0.5% | fwd_min=0.0058, non_overlap=0.1132 | regime_utility_candidate |
| 21 | context | active_candidate | BONK1MUSDT | 4 | ctx_bonk_rv_1h_bps=low | 68.8 | 0.0435 | 0.0435 | 1.21x | 2.2% | fwd_min=-0.0774, non_overlap=0.0260 | regime_utility_candidate |
| 22 | context | watch | BONK1MUSDT | 12 | ctx_bonk_rv_1h_bps=low | 60.9 | 0.1400 | 0.1400 | 1.59x | 0.5% | fwd_min=0.0045, non_overlap=0.1131 | regime_utility_candidate |

## Mechanism Notes

### Activity

- Only BONK1MUSDT survives into watch. Both rows are low-activity buckets. The 1h low-notional row has the highest path-width watch rate in the active/watch set, so the conservative reading is quiet-state/path-width, not direction.

### Spread

- `top_depth_total_notional_median=high` is the cleanest structural family. BONK1MUSDT 4h is the only high-score active candidate with placebo below 0.75x, and the 12h USDT row has the strongest recent fold edge. This is still liquidity-regime evidence, not an execution rule.

### Microprice

- Low microprice-offset buckets recur across 4h/12h, especially on BONK1MUSDT. The issue is not lack of recent edge; the issue is placebo sensitivity and moderate path-width contamination. Keep these as diagnostics until a stricter lag/placebo design survives.

### Cross-Venue

- Spread-diff candidates look structurally interesting and recent fold support is visible, but placebo ratios near or above 1.0x mean the first hypothesis should be common liquidity/regime persistence or venue staleness, not directional lead-lag.

### Context

- Low BONK realized volatility is a high-residual context state at 4h and 12h. Because it is itself a market-state control, it should be used as a regime gate candidate. The 4h USDT active row remains candidate-only due to placebo >1.0x.

## Next Validation Gates

A candidate should only advance if the next window was pre-registered with the same symbol/factor/bucket/horizon and passes all of the following:

- Recent-fold residual edge remains positive, including the `100` bps barrier view.
- Placebo ratio drops below 1.0x or has a documented regime-persistence explanation.
- Path-width flag rate stays below the candidate-specific watch threshold, or the candidate is explicitly reclassified as path-width/regime utility.
- Non-overlap evidence stays positive after market/meme/SOL/BONK RV controls.

Until then, every row in the CSV remains a research candidate only: no entry/exit, no sizing, no production signal, no alpha claim.

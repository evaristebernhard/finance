# BONK CEX V3 Recent / Regime-Local Edge Analysis

- `run_tag`: `20260513_bullish_l2_basket_price_v1`
- Scope: candidate health decomposition only; no trading rule, no alpha claim.
- Inputs: `data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet`, `date\bonk_v1_controlled_factor_tests_20260513_bullish_l2_basket_price_v1.csv`, `date\bonk_v1_model_metrics_20260513_bullish_l2_basket_price_v1.csv`
- Output CSV: `date\bonk_v3_recent_regime_edge_summary.csv`
- Primary read uses `100 bps` first-passage labels. Date/48h rows use diagnostic full-window tertile buckets; fold rows use the existing train-threshold controlled tests.

## Executive Read

The V3 book has `126` candidates after this recent/regime-local pass: `5` active, `21` watch, `100` retired.
Active means priority research state for the next validation window, not an executable signal. The stronger evidence is regime/state information: low BONK realized-volatility gates, 4h depth/liquidity state, and fold3 cross-venue spread state. Directional stability remains weak.

Key conclusions:

- `context+L2` model support is Fold2-local: proper-score wins occur in Fold2 for `BONK1MUSDC` 1h/4h and `BONK1MUSDT` 4h; Fold3 has lift in places but fails proper scores.
- The cleanest recent factor-health pattern is not all-window stability. It is regime-local: several candidates are weak or reversed in all-control fold rows, then become useful inside `ctx_*`, common-mode, or cross-venue gates.
- 12h candidates are downgraded to watch/retired diagnostics because this two-week panel has heavy overlap and no model support; do not treat 12h rows as directional edge.
- Reported trade-flow fields stay conservative because Bullish side semantics probes show material reverse/share ambiguity, especially for `BONK1MUSDC`.

## Status Candidates

| candidate_status | candidate_score | candidate | fold_locality | effective_folds | directional_effective_folds | best_regime_gate | recent_rolling48_max_edge_residual |
|---|---|---|---|---|---|---|---|
| active | 70.4 | BONK1MUSDT 4h top_depth_total_notional_median=high | cross_fold_effective | fold1,fold2,fold3 | fold1,fold2 | fold1:ctx_sol_ret_60m_bps=high | 16.1% |
| active | 68.8 | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | cross_fold_effective | fold1,fold2,fold3 | fold1,fold2 | fold3:bullish_common_mode_score=high | 5.4% |
| active | 66.4 | BONK1MUSDT 4h cross_venue_spread_diff_bps=high | mixed_fold_effective | fold1,fold3 | fold3 | fold3:ctx_bonk_rv_1h_bps=mid | 10.5% |
| active | 64.6 | BONK1MUSDT 4h snapshot_microprice_offset_bps_mean=low | mixed_fold_effective | fold1,fold3 | fold1,fold3 | fold1:ctx_sol_ret_60m_bps=high | 6.9% |
| active | 64.4 | BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | cross_fold_effective | fold1,fold2,fold3 | fold1,fold2 | fold3:bullish_common_mode_score=high | 5.5% |

Watch list head:

| candidate_status | candidate_score | candidate | fold_locality | effective_folds | best_regime_gate | recent_rolling48_max_edge_residual |
|---|---|---|---|---|---|---|
| watch | 61.8 | BONK1MUSDC 4h cross_venue_spread_diff_bps=low | mixed_fold_effective | fold1,fold3 | fold3:ctx_bonk_rv_1h_bps=mid | 10.6% |
| watch | 61.4 | BONK1MUSDT 1h top_depth_total_notional_median=high | mixed_fold_effective | fold1,fold2 | fold3:bullish_common_mode_score=high | 3.2% |
| watch | 61.2 | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | cross_fold_effective | fold1,fold2,fold3 | fold3:bullish_common_mode_score=high | 27.8% |
| watch | 60.9 | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | cross_fold_effective | fold1,fold2,fold3 | fold3:bullish_common_mode_score=high | 27.3% |
| watch | 58.7 | BONK1MUSDT 4h microprice_offset_bps_mean=low | fold3_only | fold3 | fold1:ctx_sol_ret_60m_bps=high | 5.4% |
| watch | 58.3 | BONK1MUSDC 4h top_depth_total_notional_median=high | cross_fold_effective | fold1,fold2,fold3 | fold3:bullish_common_mode_score=high | 11.0% |
| watch | 58.2 | BONK1MUSDC 12h snapshot_microprice_offset_bps_mean=low | mixed_fold_effective | fold1,fold3 | fold3:bullish_common_mode_score=high | 9.0% |
| watch | 57.5 | BONK1MUSDT 12h snapshot_microprice_offset_bps_mean=low | fold3_only | fold3 | fold2:ctx_bonk_rel_meme_bps=low | 11.8% |
| watch | 57.2 | BONK1MUSDC 12h top_depth_total_notional_median=high | cross_fold_effective | fold1,fold2,fold3 | fold3:bullish_common_mode_score=high | 22.2% |
| watch | 57.1 | BONK1MUSDT 12h top_depth_total_notional_median=high | cross_fold_effective | fold1,fold2,fold3 | fold3:bullish_common_mode_score=high | 33.5% |
| watch | 54.7 | BONK1MUSDT 1h cross_venue_spread_diff_bps=high | fold3_only | fold3 | fold2:ctx_market_ret_60m_bps=low | 3.3% |
| watch | 54.5 | BONK1MUSDT 12h cross_venue_spread_diff_bps=high | fold3_only | fold3 | fold2:ctx_market_ret_60m_bps=low | 14.9% |
| watch | 54.5 | BONK1MUSDC 12h cross_venue_spread_diff_bps=low | fold3_only | fold3 | fold2:ctx_market_ret_60m_bps=low | 15.0% |
| watch | 53.9 | BONK1MUSDT 4h spread_bps_last=high | mixed_fold_effective | fold1 | fold1:bullish_common_mode_score=low | 39.2% |
| watch | 52.9 | BONK1MUSDT 4h snapshot_count=low | mixed_fold_effective | fold1,fold2 | fold1:bullish_common_mode_score=low | 2.8% |

## Fold Decomposition

Fold-local candidates are the important read: if a candidate is only alive in Fold2 or Fold3, it should be pre-registered as a regime-local validation item rather than promoted as stable edge.

- Fold2-only effective candidates: `14`.
| candidate_status | candidate_score | candidate | best_regime_gate | max_regime_improvement |
|---|---|---|---|---|
| watch | 48.7 | BONK1MUSDC 1h top_depth_total_notional_median=high | fold3:ctx_bonk_rv_1h_bps=mid | 10.8% |
| retired | 39.2 | BONK1MUSDC 4h trade_count=low | fold1:ctx_meme_ret_60m_bps=high | 1.9% |
| retired | 37.5 | BONK1MUSDT 1h snapshot_microprice_offset_bps_mean=high | fold2:ctx_bonk_rel_meme_bps=high | 5.1% |
| retired | 36.4 | BONK1MUSDT 1h wobi5_mean=high | fold2:bullish_common_mode_score=mid | 4.5% |
| retired | 34.9 | BONK1MUSDC 1h snapshot_microprice_offset_bps_mean=high | fold2:bullish_common_mode_score=mid | 5.1% |
| retired | 34.0 | BONK1MUSDT 1h microprice_offset_bps_mean=high | fold2:ctx_bonk_rel_meme_bps=high | 4.9% |
| retired | 33.5 | BONK1MUSDC 1h trade_notional_quote_sum=low | fold2:ctx_sol_ret_60m_bps=low | 8.3% |
| retired | 32.0 | BONK1MUSDC 4h snapshot_count=low | fold2:ctx_market_ret_60m_bps=mid | 2.1% |
| retired | 29.9 | BONK1MUSDT 4h trade_notional_quote_sum=high | fold3:bullish_common_mode_score=mid | 8.9% |
| retired | 27.1 | BONK1MUSDT 4h wobi5_minus_wobi25=high | fold1:ctx_meme_ret_60m_bps=low | 4.3% |

- Fold3-only effective candidates: `30`.
| candidate_status | candidate_score | candidate | best_regime_gate | max_regime_improvement |
|---|---|---|---|---|
| watch | 58.7 | BONK1MUSDT 4h microprice_offset_bps_mean=low | fold1:ctx_sol_ret_60m_bps=high | 4.1% |
| watch | 57.5 | BONK1MUSDT 12h snapshot_microprice_offset_bps_mean=low | fold2:ctx_bonk_rel_meme_bps=low | 4.0% |
| watch | 54.7 | BONK1MUSDT 1h cross_venue_spread_diff_bps=high | fold2:ctx_market_ret_60m_bps=low | 5.0% |
| watch | 54.5 | BONK1MUSDT 12h cross_venue_spread_diff_bps=high | fold2:ctx_market_ret_60m_bps=low | 4.7% |
| watch | 54.5 | BONK1MUSDC 12h cross_venue_spread_diff_bps=low | fold2:ctx_market_ret_60m_bps=low | 4.6% |
| watch | 50.8 | BONK1MUSDT 12h microprice_offset_bps_mean=low | fold2:ctx_bonk_rel_meme_bps=low | 4.5% |
| retired | 46.5 | BONK1MUSDT 1h cross_venue_basis_bps=high | fold3:ctx_meme_ret_60m_bps=high | 13.5% |
| retired | 45.6 | BONK1MUSDT 12h cross_venue_basis_bps=high | fold3:bullish_common_mode_score=mid | 27.3% |
| retired | 43.8 | BONK1MUSDT 4h bullish_common_mode_score=low | fold2:ctx_sol_ret_60m_bps=low | 8.8% |
| retired | 41.6 | BONK1MUSDC 12h cross_venue_basis_bps=high | fold3:bullish_common_mode_score=mid | 29.7% |
| retired | 39.8 | BONK1MUSDC 1h cross_venue_basis_bps=high | fold3:ctx_meme_ret_60m_bps=high | 14.3% |
| retired | 39.7 | BONK1MUSDT 12h depth_imbalance_25_mean=low | fold3:ctx_bonk_rv_1h_bps=low | 9.0% |

- Fold2+Fold3/recent-only effective candidates: `1`.
| candidate_status | candidate_score | candidate | fold_locality | best_regime_gate |
|---|---|---|---|---|
| retired | 41.2 | BONK1MUSDC 12h snapshot_count=low | fold2_fold3_only | fold3:ctx_meme_ret_60m_bps=low |

Best all-control fold rows among active/watch candidates:

| fold | candidate_status | candidate | segment_health | edge_residual | edge_upper | upper_edge_minus_lower_edge | non_overlap_edge_upper |
|---|---|---|---|---|---|---|---|
| fold1 | active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | directional_positive | 24.2% | 2.6% | 15.4% | 4.4% |
| fold1 | active | BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | directional_positive | 23.7% | 2.8% | 16.0% | -2.2% |
| fold1 | watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | directional_positive | 20.1% | 12.1% | 24.4% | 20.0% |
| fold1 | watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | directional_positive | 19.9% | 12.0% | 24.2% | 20.0% |
| fold1 | watch | BONK1MUSDT 4h spread_bps_last=high | residual_only | 16.8% | -2.7% | 7.7% | -40.0% |
| fold1 | active | BONK1MUSDT 4h top_depth_total_notional_median=high | directional_positive | 14.6% | 3.7% | 15.4% | 10.0% |
| fold2 | active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | directional_positive | 29.3% | 6.2% | 12.5% | n/a |
| fold2 | active | BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | directional_positive | 29.2% | 6.4% | 13.7% | n/a |
| fold2 | watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | directional_positive | 20.1% | 10.3% | 20.6% | n/a |
| fold2 | watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | directional_positive | 20.0% | 9.1% | 18.1% | n/a |
| fold2 | watch | BONK1MUSDC 4h top_depth_total_notional_median=high | directional_positive | 15.8% | 5.3% | 11.9% | -40.0% |
| fold2 | active | BONK1MUSDT 4h top_depth_total_notional_median=high | directional_positive | 14.0% | 2.8% | 5.6% | -40.0% |
| fold3 | watch | BONK1MUSDT 12h top_depth_total_notional_median=high | directional_positive | 25.4% | 0.7% | 2.1% | -16.7% |
| fold3 | watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | directional_positive | 18.4% | 0.9% | 2.2% | 8.3% |
| fold3 | watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | directional_positive | 18.2% | 0.8% | 2.0% | 8.3% |
| fold3 | watch | BONK1MUSDT 12h cross_venue_spread_diff_bps=high | directional_positive | 15.7% | 7.2% | 14.4% | 33.3% |
| fold3 | watch | BONK1MUSDC 12h cross_venue_spread_diff_bps=low | directional_positive | 15.7% | 7.4% | 14.7% | 33.3% |
| fold3 | watch | BONK1MUSDC 12h top_depth_total_notional_median=high | residual_only | 15.4% | -1.8% | -3.5% | n/a |

## Daily And 48h Rolling Decomposition

The date and 48h views show concentration rather than smooth persistence. This is why V3 should label the result recent/regime-local.

Top 48h rolling residual edges among active/watch candidates:

| candidate_status | candidate | segment_id | segment_health | bucket_rows | edge_residual | edge_upper | upper_edge_minus_lower_edge | median_resid_future_return_bps |
|---|---|---|---|---|---|---|---|---|
| watch | BONK1MUSDC 4h spread_bps_last=high | roll48_2026-05-10_to_2026-05-11 | directional_positive | 64 | 46.6% | 52.2% | 86.0% | 27.693 |
| watch | BONK1MUSDC 4h spread_bps_last=high | roll48_2026-05-09_to_2026-05-10 | directional_positive | 200 | 41.3% | 52.5% | 86.2% | 28.594 |
| watch | BONK1MUSDT 4h spread_bps_last=high | roll48_2026-05-10_to_2026-05-11 | directional_positive | 365 | 39.2% | 28.9% | 59.6% | 61.261 |
| watch | BONK1MUSDT 4h spread_bps_median=high | roll48_2026-05-10_to_2026-05-11 | directional_positive | 450 | 39.0% | 32.6% | 60.2% | 60.179 |
| active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | roll48_2026-05-05_to_2026-05-06 | directional_positive | 673 | 38.8% | 32.2% | 57.7% | 55.350 |
| active | BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | roll48_2026-05-05_to_2026-05-06 | directional_positive | 676 | 38.1% | 32.2% | 57.3% | 55.050 |
| watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | roll48_2026-05-05_to_2026-05-06 | directional_positive | 666 | 33.7% | 29.4% | 58.8% | 170.347 |
| watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | roll48_2026-05-05_to_2026-05-06 | directional_positive | 666 | 33.5% | 29.3% | 58.6% | 168.938 |
| watch | BONK1MUSDT 12h top_depth_total_notional_median=high | roll48_2026-05-10_to_2026-05-11 | directional_positive | 639 | 33.5% | 13.2% | 26.3% | 110.882 |
| watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | roll48_2026-05-06_to_2026-05-07 | directional_positive | 234 | 31.9% | 18.4% | 36.8% | 187.540 |
| watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | roll48_2026-05-06_to_2026-05-07 | directional_positive | 234 | 31.8% | 17.6% | 35.1% | 187.167 |
| active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | roll48_2026-05-06_to_2026-05-07 | directional_positive | 237 | 30.1% | 15.1% | 29.9% | 78.455 |

Top daily residual edges among active/watch candidates:

| candidate_status | candidate | segment_id | segment_health | bucket_rows | edge_residual | edge_upper | upper_edge_minus_lower_edge | median_resid_future_return_bps |
|---|---|---|---|---|---|---|---|---|
| watch | BONK1MUSDC 4h spread_bps_last=high | 2026-05-09 | directional_positive | 136 | 46.9% | 64.9% | 112.0% | 28.900 |
| watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | 2026-05-05 | directional_positive | 521 | 39.0% | 23.8% | 47.5% | 164.032 |
| watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | 2026-05-05 | directional_positive | 521 | 38.7% | 23.8% | 47.7% | 162.840 |
| active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | 2026-05-06 | directional_positive | 148 | 38.2% | 25.8% | 42.6% | 42.155 |
| active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | 2026-05-05 | directional_positive | 525 | 38.1% | 28.6% | 51.2% | 57.028 |
| active | BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | 2026-05-05 | directional_positive | 525 | 37.8% | 28.9% | 51.5% | 57.457 |
| active | BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | 2026-05-06 | directional_positive | 151 | 36.3% | 24.6% | 39.7% | 40.997 |
| watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | 2026-05-07 | directional_positive | 89 | 35.5% | 15.3% | 30.5% | 181.800 |
| watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | 2026-05-07 | directional_positive | 89 | 35.3% | 13.4% | 26.7% | 182.414 |
| watch | BONK1MUSDC 4h spread_bps_last=high | 2026-05-10 | directional_positive | 64 | 33.4% | 40.2% | 60.4% | 27.693 |
| watch | BONK1MUSDT 4h spread_bps_median=high | 2026-05-10 | directional_positive | 371 | 30.7% | 24.8% | 43.7% | 77.685 |
| watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | 2026-05-10 | directional_positive | 626 | 30.3% | 12.3% | 24.6% | 159.837 |

## Best Regime Gates

A candidate is marked `regime_local_flag=true` when fold support is recent-only, daily/48h support is concentrated, or the best controlled regime bucket materially improves over all-control evidence.

| candidate_status | candidate | fold | gate | segment_health | bucket_rows | edge_residual | edge_upper | upper_edge_minus_lower_edge | note |
|---|---|---|---|---|---|---|---|---|---|
| retired | BONK1MUSDC 12h spread_bps_median=high | fold1 | ctx_bonk_rv_1h_bps=high | directional_positive | 178 | 45.9% | 25.5% | 51.0% | best regime gate; residual_edge_improvement_vs_all=0.3224 |
| watch | BONK1MUSDT 12h top_depth_total_notional_median=high | fold3 | bullish_common_mode_score=high | directional_positive | 75 | 45.5% | 8.5% | 17.1% | best regime gate; residual_edge_improvement_vs_all=0.2009 |
| active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | fold3 | bullish_common_mode_score=high | directional_positive | 79 | 43.3% | 13.1% | 32.8% | best regime gate; residual_edge_improvement_vs_all=0.3732 |
| active | BONK1MUSDC 4h ctx_bonk_rv_1h_bps=low | fold3 | bullish_common_mode_score=high | directional_positive | 79 | 41.8% | 13.2% | 33.0% | best regime gate; residual_edge_improvement_vs_all=0.3605 |
| retired | BONK1MUSDC 12h spread_bps_last=high | fold1 | ctx_bonk_rv_1h_bps=high | directional_positive | 186 | 41.6% | 20.2% | 40.3% | best regime gate; residual_edge_improvement_vs_all=0.2745 |
| watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | fold3 | bullish_common_mode_score=high | directional_positive | 79 | 39.1% | 23.3% | 46.5% | best regime gate; residual_edge_improvement_vs_all=0.2074 |
| watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | fold3 | bullish_common_mode_score=high | directional_positive | 79 | 38.5% | 23.1% | 46.2% | best regime gate; residual_edge_improvement_vs_all=0.2032 |
| watch | BONK1MUSDT 12h ctx_bonk_rv_1h_bps=low | fold1 | bullish_common_mode_score=low | directional_positive | 451 | 37.9% | 23.1% | 46.2% | best regime gate; residual_edge_improvement_vs_all=0.1780 |
| watch | BONK1MUSDC 12h ctx_bonk_rv_1h_bps=low | fold1 | bullish_common_mode_score=low | directional_positive | 452 | 37.7% | 22.7% | 45.4% | best regime gate; residual_edge_improvement_vs_all=0.1775 |
| watch | BONK1MUSDC 12h top_depth_total_notional_median=high | fold3 | bullish_common_mode_score=high | directional_positive | 97 | 31.9% | 17.2% | 34.4% | best regime gate; residual_edge_improvement_vs_all=0.1646 |
| retired | BONK1MUSDT 12h spread_bps_last=high | fold1 | bullish_common_mode_score=low | directional_positive | 161 | 31.7% | 20.3% | 40.6% | best regime gate; residual_edge_improvement_vs_all=0.1519 |
| active | BONK1MUSDT 4h ctx_bonk_rv_1h_bps=low | fold2 | ctx_meme_ret_60m_bps=low | directional_positive | 82 | 30.2% | 29.2% | 53.2% | best regime gate; residual_edge_improvement_vs_all=0.0085 |

## Model Metrics Read

| fold | symbol | H | proper | d_logloss | d_brier | d_lift |
|---|---|---|---|---|---|---|
| fold2 | BONK1MUSDC | 1h | pass | -0.0026 | -0.0019 | 16.7% |
| fold2 | BONK1MUSDC | 4h | pass | -0.0472 | -0.0199 | 0.0% |
| fold2 | BONK1MUSDT | 1h | fail | 0.0213 | 0.0019 | 16.7% |
| fold2 | BONK1MUSDT | 4h | pass | -0.0135 | -0.0111 | 0.0% |
| fold3 | BONK1MUSDC | 1h | fail | 0.0070 | 0.0040 | 0.0% |
| fold3 | BONK1MUSDC | 4h | fail | 0.0541 | 0.0198 | 0.0% |
| fold3 | BONK1MUSDT | 1h | fail | 0.0223 | 0.0060 | 12.5% |
| fold3 | BONK1MUSDT | 4h | fail | 0.0606 | 0.0252 | 50.0% |

The model layer does not rescue Fold3: `context+L2` can improve top-decile lift in Fold3, but proper scores degrade. This makes Fold3 candidates useful as recent phenomena to validate, not stable prediction claims.

## Status Rules

- `active`: priority research candidate for the next window; horizon is 1h/4h, score is high, and recent fold/model/48h evidence is present.
- `watch`: mixed or regime-local candidate; useful for diagnostics, path-width, or gate design, but not strong enough to prioritize as a directional state.
- `retired`: no enough recent fold/model/rolling support for V3 priority; can remain in raw CSV history but should not drive the next validation plan.

## Next Validation

Pre-register only active/watch candidates that have explicit `best_regime_gate` or fold-locality in the CSV. In the next date batch, validate the same factor, bucket, horizon, barrier, and regime gate without reselecting dates or thresholds. A candidate fails if Fold3-style local support does not reappear under the declared gate, or if it only widens both upper/lower paths while being described as directional.

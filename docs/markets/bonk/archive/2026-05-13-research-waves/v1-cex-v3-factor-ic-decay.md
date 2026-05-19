# BONK V3 Factor IC / Decay Probe

Status: 2026-05-13. This is a Spearman/rank diagnostic over the existing BONK V3 panel. It is not a trading rule, not an execution plan, and not an alpha claim.

## Inputs And Outputs

Input:

```text
data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date\bonk_v3_factor_ic_decay_detail_20260513_bullish_l2_basket_price_v1.csv
date\bonk_v3_factor_ic_decay_summary_20260513_bullish_l2_basket_price_v1.csv
date\bonk_v3_factor_ic_decay_completion_20260513_bullish_l2_basket_price_v1.json
```

## Method

- Scope: `BONK1MUSDC/BONK1MUSDT`, `100 bps`, horizons `1h/4h/12h`, `label_status=ok`.
- Spearman IC is computed by validation fold, fold/day, and fold/phase; phase rows are a sensitivity view, not independent evidence.
- Lagged features use prior minute-bar values (`5m/15m/60m`) within the same symbol/horizon group.
- Outcomes include raw future return, residual future return, upper/lower/not-lower first-passage encodings, residual-positive, and path width.
- IC is a ranking diagnostic; path labels remain more directly relevant for first-passage questions.

## Strongest Robust IC Rows

| symbol | horizon_hours | factor_group | factor | lag_minutes | outcome | median_ic | fold2_3_median_ic | robust_ic_score | decay_vs_lag0_abs_ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDT | 1 | context | ctx_bonk_rv_1h_bps | 0 | path_width_bps | 0.3803 | 0.4105 | 0.3777 | 1.0000 |
| BONK1MUSDC | 1 | context | ctx_bonk_rv_1h_bps | 0 | path_width_bps | 0.3811 | 0.4100 | 0.3738 | 1.0000 |
| BONK1MUSDT | 4 | spread_liquidity | spread_bps_median | 0 | future_resid_mkt_meme_sol_bps | 0.3007 | 0.2862 | 0.3041 | 1.0000 |
| BONK1MUSDT | 4 | spread_liquidity | spread_bps_median | 0 | target_not_lower_first | 0.2095 | 0.2087 | 0.2675 | 1.0000 |
| BONK1MUSDT | 4 | context | ctx_bonk_rv_1h_bps | 0 | future_resid_mkt_meme_sol_bps | -0.2786 | -0.2363 | 0.2604 | 1.0000 |
| BONK1MUSDC | 4 | context | ctx_bonk_rv_1h_bps | 0 | future_resid_mkt_meme_sol_bps | -0.2786 | -0.2363 | 0.2586 | 1.0000 |
| BONK1MUSDC | 12 | context | ctx_bonk_rv_1h_bps | 5 | future_resid_mkt_meme_sol_bps | -0.3362 | -0.2887 | 0.2445 | 1.0076 |
| BONK1MUSDC | 12 | context | ctx_bonk_rv_1h_bps | 0 | future_resid_mkt_meme_sol_bps | -0.3355 | -0.3095 | 0.2438 | 1.0000 |
| BONK1MUSDT | 12 | context | ctx_bonk_rv_1h_bps | 5 | future_resid_mkt_meme_sol_bps | -0.3370 | -0.2886 | 0.2434 | 1.0072 |
| BONK1MUSDT | 12 | context | ctx_bonk_rv_1h_bps | 0 | future_resid_mkt_meme_sol_bps | -0.3357 | -0.3091 | 0.2426 | 1.0000 |
| BONK1MUSDC | 12 | context | ctx_bonk_rv_1h_bps | 15 | future_resid_mkt_meme_sol_bps | -0.3226 | -0.2586 | 0.2411 | 1.0190 |
| BONK1MUSDT | 12 | context | ctx_bonk_rv_1h_bps | 15 | future_resid_mkt_meme_sol_bps | -0.3232 | -0.2583 | 0.2402 | 1.0181 |
| BONK1MUSDT | 1 | context | ctx_bonk_rv_1h_bps | 5 | path_width_bps | 0.3586 | 0.4086 | 0.2336 | 0.9429 |
| BONK1MUSDC | 1 | context | ctx_bonk_rv_1h_bps | 5 | path_width_bps | 0.3599 | 0.4090 | 0.2329 | 0.9445 |
| BONK1MUSDT | 12 | context | ctx_bonk_rv_1h_bps | 60 | future_resid_mkt_meme_sol_bps | -0.2796 | -0.2515 | 0.2246 | 0.9108 |
| BONK1MUSDC | 12 | context | ctx_bonk_rv_1h_bps | 60 | future_resid_mkt_meme_sol_bps | -0.2802 | -0.2516 | 0.2246 | 0.9091 |


## Strongest BONK1MUSDT Rank Diagnostics

| horizon_hours | factor | outcome | median_ic | fold2_3_median_ic | positive_group_rate | n_groups |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ctx_bonk_rv_1h_bps | path_width_bps | 0.3803 | 0.4105 | 1.0000 | 49 |
| 4 | spread_bps_median | future_resid_mkt_meme_sol_bps | 0.3007 | 0.2862 | 0.8525 | 61 |
| 4 | bullish_common_mode_score | path_width_bps | 0.0817 | 0.0230 | 0.6923 | 13 |
| 4 | ctx_bonk_rv_1h_bps | future_resid_mkt_meme_sol_bps | -0.2786 | -0.2363 | 0.1148 | 61 |
| 4 | spread_bps_last | target_not_lower_first | 0.2617 | 0.1979 | 1.0000 | 13 |
| 4 | spread_bps_last | future_resid_mkt_meme_sol_bps | 0.2590 | 0.2537 | 0.9231 | 13 |
| 4 | spread_bps_median | target_not_lower_first | 0.2095 | 0.2087 | 0.8197 | 61 |
| 1 | bullish_common_mode_score | path_width_bps | 0.1995 | 0.1995 | 0.6923 | 13 |
| 1 | snapshot_count | path_width_bps | 0.2277 | 0.1878 | 1.0000 | 13 |
| 1 | top_depth_total_notional_median | path_width_bps | -0.2183 | -0.2002 | 0.0204 | 49 |
| 4 | ctx_bonk_rv_1h_bps | path_width_bps | 0.2071 | 0.2219 | 0.8525 | 61 |
| 4 | spread_bps_median | path_width_bps | -0.1964 | -0.2429 | 0.1639 | 61 |
| 4 | bullish_first_eigen_share_60m | path_width_bps | 0.1288 | 0.0692 | 0.6923 | 13 |
| 4 | cross_venue_spread_diff_bps | path_width_bps | 0.1071 | 0.1142 | 0.6721 | 61 |
| 4 | snapshot_count | future_resid_mkt_meme_sol_bps | -0.1670 | -0.1282 | 0.3077 | 13 |
| 4 | ctx_bonk_rv_1h_bps | target_not_lower_first | -0.1260 | -0.0885 | 0.2623 | 61 |


## H4 Active-Factor Decay

| factor | lag_minutes | median_ic | fold2_3_median_ic | positive_group_rate | n_groups |
| --- | --- | --- | --- | --- | --- |
| cross_venue_spread_diff_bps | 0 | 0.0175 | 0.0175 | 0.5410 | 61 |
| cross_venue_spread_diff_bps | 5 | -0.0471 | -0.0720 | 0.4615 | 13 |
| cross_venue_spread_diff_bps | 15 | -0.0257 | -0.0445 | 0.3846 | 13 |
| cross_venue_spread_diff_bps | 60 | -0.0165 | 0.0132 | 0.4615 | 13 |
| ctx_bonk_rv_1h_bps | 0 | -0.2786 | -0.2363 | 0.1148 | 61 |
| ctx_bonk_rv_1h_bps | 5 | -0.1870 | -0.1716 | 0.2308 | 13 |
| ctx_bonk_rv_1h_bps | 15 | -0.1775 | -0.1765 | 0.2308 | 13 |
| ctx_bonk_rv_1h_bps | 60 | -0.1564 | -0.1418 | 0.3077 | 13 |
| top_depth_total_notional_median | 0 | 0.1429 | 0.0980 | 0.6721 | 61 |
| top_depth_total_notional_median | 5 | 0.0674 | 0.0655 | 0.6923 | 13 |
| top_depth_total_notional_median | 15 | 0.0539 | 0.0512 | 0.6923 | 13 |
| top_depth_total_notional_median | 60 | 0.0340 | 0.0272 | 0.6923 | 13 |


## Read

Spearman is useful here, but it should not replace first-passage/path diagnostics. The IC view tells us whether a factor ranks future residual/path outcomes monotonically; the path-label view tells us whether the selected path hits upper/lower barriers in the useful order.

For the current BONK work, a factor is more interesting when it has the same sign across fold2/fold3, degrades under lag, and also improves residual-positive or lower-first suppression in the path tables. If the IC remains similar at 60m lag, read it as a slow regime proxy rather than precise microstructure timing.

## Caveats

- Daily validation groups are few because the window is only `2026-04-29..2026-05-12`.
- Lagged rows assume minute-step continuity; missing L2 minutes can make a `60` row lag differ from exact wall-clock 60 minutes.
- Existing first-passage labels are reused as-is; this report does not rebuild labels or audit exchange execution feasibility.
- No automatic trading rule or alpha claim is inferred from positive IC.

# BONK V8b Exploratory Factor Mining

Status: generated 2026-05-14T04:50:24Z. Canonical input run tag: `20260513_bullish_l2_basket_price_v1`.

Research diagnostic only: no trading advice, no execution recommendation, no sizing rule, and no alpha claim.

## Isolation Guardrails

- This is an independent Python-only V8b track.
- It reads existing local parquet/CSV data only and does not download data.
- It does not modify the Rust canonical pipeline.
- It writes only `bonk_v8b_*` date artifacts plus this markdown report.
- Candidate ranking uses after-cost `$100` episode PnL under `maker_light` and `taker_spread`; model AUC and label edges are diagnostics only.

## Inputs

- L2 state: `data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet`
- Label/context panel: `data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet`
- Binance price context: `data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet`
- Bullish covariance state: `data/bonk/v1/derived/bonk_cex_covariance_state/bonk_cex_covariance_state_20260513_bullish_l2_basket_price_v1.parquet`

## Validation Design

All thresholds, percentile-rank scalers, model scores, and mined combinations are fit on the train side of each purged walk-forward fold before being applied to validation.

| fold | train end | validation |
| --- | --- | --- |
| fold1 | 2026-05-02T23:59:00Z | 2026-05-03T12:00:00Z to 2026-05-05T23:59:00Z |
| fold2 | 2026-05-05T23:59:00Z | 2026-05-06T12:00:00Z to 2026-05-08T23:59:00Z |
| fold3 | 2026-05-08T23:59:00Z | 2026-05-09T12:00:00Z to 2026-05-12T11:59:00Z |

## Feature Surface

The miner combines price momentum/reversal/breakout/volume, L2 state changes, trade-flow bursts, USDC/USDT cross-venue state, Bullish covariance, Binance BTC/ETH/SOL/meme/alt context, lead-lag pressure, resonance, liquidity fragility, and current cost-state proxies.

| feature_family | features |
| --- | --- |
| l2_event_sequence | 30 |
| bonk_price_context | 7 |
| binance_basket_context | 7 |
| btc_eth_sol_context | 7 |
| trade_flow | 7 |
| usdc_usdt_cross_venue | 6 |
| symbolic_interaction | 5 |
| bullish_basket_covariance | 4 |
| other | 3 |
| liquidity_fragility | 2 |
| cost_adjusted_execution_state | 2 |

## Model And Search Diagnostics

LightGBM and RandomForest are used to discover useful feature families and train-only model-score gates. A combinatorial search then creates simple rank-threshold interactions from train-selected features and directions. Final ranking below is not based on AUC.

| feature_family | feature | importance |
| --- | --- | --- |
| bullish_basket_covariance | bullish_cross_abs_ret_mean_bps | 55.0278 |
| l2_event_sequence | spread_bps_median | 37.2929 |
| bullish_basket_covariance | bullish_avg_corr_60m | 33.3495 |
| bullish_basket_covariance | bullish_first_eigen_share_60m | 29.4359 |
| l2_event_sequence | depth25_total_notional_median | 29.0411 |
| l2_event_sequence | spread_bps_last | 27.5426 |
| cost_adjusted_execution_state | current_taker_cost_bps | 24.8692 |
| l2_event_sequence | depth_bid_notional_25_median | 20.6979 |
| bonk_price_context | ctx_bonk_ret_60m_bps | 16.0944 |
| bullish_basket_covariance | bullish_common_mode_score_v8b | 13.0932 |
| binance_basket_context | ctx_market_ret_60m_bps | 12.2589 |
| l2_event_sequence | depth_ask_notional_25_median | 11.8599 |
| btc_eth_sol_context | ctx_btc_ret_60m_bps | 9.5897 |
| usdc_usdt_cross_venue | cross_venue_spread_diff_bps | 8.9393 |

## Candidate Ranking

Sorted only by `maker_light + taker_spread` after-cost `$100` episode PnL on validation folds.

| rank | candidate_id | symbol | tp_bps | sl_bps | timeout_minutes | rank_pnl_quote | maker_light_pnl_quote | taker_spread_pnl_quote | total_trade_count_both_models | fold2_fold3_stability | failure_flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 75 | 20 | 60 | 1.5142 | 0.8236 | 0.6906 | 14 | fold2_and_fold3_nonnegative | low_trade_count\|single_day_dependent |
| 2 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 75 | 20 | 120 | 1.5142 | 0.8236 | 0.6906 | 14 | fold2_and_fold3_nonnegative | low_trade_count\|single_day_dependent |
| 3 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 100 | 20 | 60 | 1.5142 | 0.8236 | 0.6906 | 14 | fold2_and_fold3_nonnegative | low_trade_count\|single_day_dependent |
| 4 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 100 | 20 | 120 | 1.5142 | 0.8236 | 0.6906 | 14 | fold2_and_fold3_nonnegative | low_trade_count\|single_day_dependent |
| 5 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 75 | 20 | 60 | 0.6965 | 0.4949 | 0.2015 | 20 | fold2_and_fold3_nonnegative | single_day_dependent |
| 6 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 75 | 20 | 120 | 0.6965 | 0.4949 | 0.2015 | 20 | fold2_and_fold3_nonnegative | single_day_dependent |
| 7 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 100 | 20 | 60 | 0.6965 | 0.4949 | 0.2015 | 20 | fold2_and_fold3_nonnegative | single_day_dependent |
| 8 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 100 | 20 | 120 | 0.6965 | 0.4949 | 0.2015 | 20 | fold2_and_fold3_nonnegative | single_day_dependent |
| 9 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 75 | 20 | 60 | 0.4075 | 0.4359 | -0.0284 | 32 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent |
| 10 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 75 | 20 | 120 | 0.4075 | 0.4359 | -0.0284 | 32 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent |
| 11 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 100 | 20 | 60 | 0.4075 | 0.4359 | -0.0284 | 32 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent |
| 12 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 100 | 20 | 120 | 0.4075 | 0.4359 | -0.0284 | 32 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent |
| 13 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 75 | 20 | 60 | 0.0753 | 0.1492 | -0.0739 | 18 | fold2_and_fold3_nonnegative | low_trade_count\|maker_only_positive |
| 14 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 75 | 20 | 120 | 0.0753 | 0.1492 | -0.0739 | 18 | fold2_and_fold3_nonnegative | low_trade_count\|maker_only_positive |
| 15 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 100 | 20 | 60 | 0.0753 | 0.1492 | -0.0739 | 18 | fold2_and_fold3_nonnegative | low_trade_count\|maker_only_positive |
| 16 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 100 | 20 | 120 | 0.0753 | 0.1492 | -0.0739 | 18 | fold2_and_fold3_nonnegative | low_trade_count\|maker_only_positive |
| 17 | combo_1165a63f_spread_bps_last_high | BONK1MUSDC | 100 | 20 | 60 | 0.0543 | 0.4114 | -0.3571 | 60 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl |
| 18 | combo_1165a63f_spread_bps_last_high | BONK1MUSDC | 100 | 20 | 120 | 0.0543 | 0.4114 | -0.3571 | 60 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl |

## Distilled Simple Candidate Gates

These are simple gate shapes that could be translated into the main V8 Rust replay for further testing. They are not trading rules, not execution recommendations, and not alpha claims.

| rank | candidate_id | symbol | rust_pipeline_candidate_gate | rank_pnl_quote | fold2_fold3_stability | failure_flags | read_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | spread_bps_median >= train_rank_high AND cross_venue_spread_diff_bps <= train_rank_low | 1.5142 | fold2_and_fold3_nonnegative | low_trade_count\|single_day_dependent | exploratory_positive_after_cost_read_not_alpha_claim |
| 5 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | spread_bps_median >= train_rank_high AND spread_bps_last >= train_rank_high AND ctx_bonk_ret_... | 0.6965 | fold2_and_fold3_nonnegative | single_day_dependent | exploratory_positive_after_cost_read_not_alpha_claim |
| 9 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | spread_bps_median >= train_rank_high AND current_taker_cost_bps >= train_rank_high | 0.4075 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent | exploratory_positive_after_cost_read_not_alpha_claim |
| 13 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | bullish_first_eigen_share_60m >= train_rank_high AND spread_bps_median >= train_rank_high AND... | 0.0753 | fold2_and_fold3_nonnegative | low_trade_count\|maker_only_positive | exploratory_positive_after_cost_read_not_alpha_claim |
| 17 | combo_1165a63f_spread_bps_last_high | BONK1MUSDC | spread_bps_last >= train_rank_high AND ctx_bonk_ret_60m_bps >= train_rank_high AND current_ta... | 0.0543 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl | exploratory_positive_after_cost_read_not_alpha_claim |
| 19 | combo_a910eea4_bullish_first_eigen_share_60m_high | BONK1MUSDC | bullish_first_eigen_share_60m >= train_rank_high AND spread_bps_last >= train_rank_high AND a... | 0.0008 | fold2_and_fold3_nonnegative | low_trade_count\|maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl | exploratory_positive_after_cost_read_not_alpha_claim |
| 23 | combo_8a586cf8_spread_bps_median_high | BONK1MUSDC | spread_bps_median >= train_rank_high AND spread_bps_last >= train_rank_high AND current_taker... | -0.0297 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|after_cost_pnl_nonpositive | diagnostic_only_after_cost_negative_or_fragile |
| 29 | combo_a9a5593e_bullish_cross_abs_ret_mean_bps_low | BONK1MUSDC | bullish_cross_abs_ret_mean_bps <= train_rank_low AND spread_bps_median >= train_rank_high AND... | -0.1767 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|after_cost_pnl_nonpositive | diagnostic_only_after_cost_negative_or_fragile |
| 33 | combo_d2cba0af_spread_bps_median_high | BONK1MUSDT | spread_bps_median >= train_rank_high AND spread_bps_last >= train_rank_high AND cross_venue_s... | -0.2655 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|after_cost_pnl_nonpositive | diagnostic_only_after_cost_negative_or_fragile |
| 37 | combo_66320d82_spread_bps_last_high | BONK1MUSDC | spread_bps_last >= train_rank_high AND current_taker_cost_bps >= train_rank_high | -0.3283 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|after_cost_pnl_nonpositive | diagnostic_only_after_cost_negative_or_fragile |
| 41 | combo_6b40d9ed_current_taker_cost_bps_high | BONK1MUSDT | current_taker_cost_bps >= train_rank_high AND cross_venue_spread_diff_bps <= train_rank_low | -0.3812 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|after_cost_pnl_nonpositive | diagnostic_only_after_cost_negative_or_fragile |
| 45 | combo_c42ebf17_spread_bps_last_high | BONK1MUSDT | spread_bps_last >= train_rank_high AND current_taker_cost_bps >= train_rank_high AND cross_ve... | -0.4207 | fold2_and_fold3_nonnegative | maker_only_positive\|single_day_dependent\|after_cost_pnl_nonpositive | diagnostic_only_after_cost_negative_or_fragile |

## Failure Diagnostics

| rank | candidate_id | symbol | rank_pnl_quote | failure_flags | maker_light_pnl_quote | taker_spread_pnl_quote | fold2_pnl_quote_both_models | fold3_pnl_quote_both_models | max_single_day_abs_pnl_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0000 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 1.5142 | low_trade_count\|single_day_dependent | 0.8236 | 0.6906 | 0.0000 | 0.0000 | 1.0000 |
| 2.0000 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 1.5142 | low_trade_count\|single_day_dependent | 0.8236 | 0.6906 | 0.0000 | 0.0000 | 1.0000 |
| 3.0000 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 1.5142 | low_trade_count\|single_day_dependent | 0.8236 | 0.6906 | 0.0000 | 0.0000 | 1.0000 |
| 4.0000 | combo_7467f6bc_spread_bps_median_high | BONK1MUSDT | 1.5142 | low_trade_count\|single_day_dependent | 0.8236 | 0.6906 | 0.0000 | 0.0000 | 1.0000 |
| 5.0000 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 0.6965 | single_day_dependent | 0.4949 | 0.2015 | 0.0000 | 0.0000 | 1.0000 |
| 6.0000 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 0.6965 | single_day_dependent | 0.4949 | 0.2015 | 0.0000 | 0.0000 | 1.0000 |
| 7.0000 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 0.6965 | single_day_dependent | 0.4949 | 0.2015 | 0.0000 | 0.0000 | 1.0000 |
| 8.0000 | combo_e21d38ed_spread_bps_median_high | BONK1MUSDC | 0.6965 | single_day_dependent | 0.4949 | 0.2015 | 0.0000 | 0.0000 | 1.0000 |
| 9.0000 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 0.4075 | maker_only_positive\|single_day_dependent | 0.4359 | -0.0284 | 0.0000 | 0.0000 | 1.0000 |
| 10.0000 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 0.4075 | maker_only_positive\|single_day_dependent | 0.4359 | -0.0284 | 0.0000 | 0.0000 | 1.0000 |
| 11.0000 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 0.4075 | maker_only_positive\|single_day_dependent | 0.4359 | -0.0284 | 0.0000 | 0.0000 | 1.0000 |
| 12.0000 | combo_073e7baf_spread_bps_median_high | BONK1MUSDC | 0.4075 | maker_only_positive\|single_day_dependent | 0.4359 | -0.0284 | 0.0000 | 0.0000 | 1.0000 |
| 13.0000 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 0.0753 | low_trade_count\|maker_only_positive | 0.1492 | -0.0739 | 0.0753 | 0.0000 | 0.5062 |
| 14.0000 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 0.0753 | low_trade_count\|maker_only_positive | 0.1492 | -0.0739 | 0.0753 | 0.0000 | 0.5062 |
| 15.0000 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 0.0753 | low_trade_count\|maker_only_positive | 0.1492 | -0.0739 | 0.0753 | 0.0000 | 0.5062 |
| 16.0000 | combo_b45b83a4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 0.0753 | low_trade_count\|maker_only_positive | 0.1492 | -0.0739 | 0.0753 | 0.0000 | 0.5062 |
| 17.0000 | combo_1165a63f_spread_bps_last_high | BONK1MUSDC | 0.0543 | maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl | 0.4114 | -0.3571 | 0.0000 | 0.0000 | 1.0000 |
| 18.0000 | combo_1165a63f_spread_bps_last_high | BONK1MUSDC | 0.0543 | maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl | 0.4114 | -0.3571 | 0.0000 | 0.0000 | 1.0000 |
| 19.0000 | combo_a910eea4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 0.0008 | low_trade_count\|maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl | 0.0150 | -0.0142 | 0.0008 | 0.0000 | 1.0000 |
| 20.0000 | combo_a910eea4_bullish_first_eigen_share_60m_high | BONK1MUSDC | 0.0008 | low_trade_count\|maker_only_positive\|single_day_dependent\|drawdown_large_vs_pnl | 0.0150 | -0.0142 | 0.0008 | 0.0000 | 1.0000 |

## Outputs

- candidate_daily: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_candidate_daily.csv`
- candidate_folds: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_candidate_folds.csv`
- candidate_rank: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_candidate_rank.csv`
- candidate_summary: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_candidate_summary.csv`
- completion: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_completion.json`
- distilled_gates: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_distilled_gates.csv`
- failure_diagnostics: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_failure_diagnostics.csv`
- feature_catalog: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_feature_catalog.csv`
- feature_importance: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_feature_importance.csv`
- report: `docs/markets/bonk/v1-cex-v8b-exploratory-factor-mining.md`
- trades: `date/bonk_v8b_exploratory_factor_mining_20260513_bullish_l2_basket_price_v1_v8b_r2_trades.csv`

## Read

- Treat V8b as exploratory factor mining only.
- Any gate that looks interesting here still needs canonical Rust replay, sensitivity checks, and explicit failure review.
- Negative or fragile after-cost rows are retained because they are useful diagnostics for cost, turnover, fold dependence, and single-day dependence.

Rows mined: `39718`. Feature columns considered by models: `80`.

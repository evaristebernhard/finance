# BONK V7 Dynamic Context Resonance Probe

Status: 2026-05-13T15:33:42Z. Run tag: `20260513_bullish_l2_basket_price_v1`.

Research diagnostic only: no trading rule, no execution instruction, no sizing rule, and no alpha claim.

## Inputs

- Price context: `data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet`
- Covariance state: `data/bonk/v1/derived/bonk_cex_covariance_state/bonk_cex_covariance_state_20260513_bullish_l2_basket_price_v1.parquet`
- L2 label/context panel: `data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet`
- V6 trades: `date/bonk_v6_episode_backtest_20260513_bullish_l2_basket_price_v1_trades.csv`
- V6 summary: `date/bonk_v6_episode_backtest_20260513_bullish_l2_basket_price_v1_summary.csv`

## Dynamic Feature Idea

The probe treats public market context as a live state vector, not a static bucket. It builds trailing-only:

- acceleration: 5m return minus one third of 15m return, plus 15m versus 60m variants;
- resonance: current BONK sign alignment with meme, SOL, and BTC, weighted by live 60m correlations;
- lead/lag pressure: prior market/meme/SOL/BTC movement minus current BONK movement, interpreted as catch-up pressure;
- covariance crowding: Bullish 60m average correlation/eigen-share/common-mode score;
- L2 impulse: microprice, WOBI, depth imbalance, and trade-flow impulse from the BONK L2 panel.

## Top Candidate Gates

| fold | symbol | gate_id | rows | coverage | direction_edge | resid_pos_edge | median_future_resid_bps | median_l2_impulse_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold1 | BONK1MUSDC | dyn_btc_lead_cv_support | 59 | 0.0164 | 0.5154 | 0.2349 | 22.1764 | 0.7460 |
| fold2 | BONK1MUSDT | dyn_resonance_plus_cv_micro | 69 | 0.0192 | 0.2412 | -0.0023 | 44.7676 | 0.6610 |
| fold2 | BONK1MUSDC | dyn_resonance_plus_cv_micro | 113 | 0.0315 | 0.1495 | -0.0088 | 41.6730 | 0.7210 |
| fold3 | BONK1MUSDT | dyn_resonance_plus_cv_micro | 73 | 0.0169 | 0.1257 | -0.0076 | -26.1066 | 0.7808 |
| fold2 | BONK1MUSDT | dyn_meme_sol_btc_accel_l2_impulse | 88 | 0.0245 | 0.1223 | 0.0748 | 54.5072 | 0.7480 |
| fold3 | BONK1MUSDC | dyn_resonance_plus_cv_micro | 104 | 0.0241 | 0.1053 | 0.0043 | -10.0074 | 0.7264 |
| fold2 | BONK1MUSDC | dyn_resonant_quiet_depth | 77 | 0.0215 | 0.0789 | 0.1840 | 63.8130 | -0.6446 |
| fold2 | BONK1MUSDT | dyn_sol_lead_microprice | 449 | 0.1251 | 0.0757 | 0.0303 | 48.3072 | 0.8491 |
| fold1 | BONK1MUSDT | dyn_resonant_quiet_depth | 85 | 0.0236 | 0.0750 | 0.0473 | 4.0337 | -0.3721 |
| fold2 | BONK1MUSDT | dyn_resonant_quiet_depth | 87 | 0.0242 | 0.0583 | 0.1296 | 68.7723 | -0.5455 |
| fold3 | BONK1MUSDT | dyn_resonant_quiet_depth | 56 | 0.0130 | 0.0572 | 0.0458 | -9.3792 | -0.5090 |
| fold2 | BONK1MUSDC | dyn_meme_sol_btc_accel_l2_impulse | 127 | 0.0354 | 0.0437 | 0.0332 | 47.1922 | 0.7343 |
| fold1 | BONK1MUSDT | dyn_meme_sol_btc_accel_l2_impulse | 75 | 0.0208 | 0.0397 | 0.0128 | 4.8234 | 0.7682 |
| fold1 | BONK1MUSDT | dyn_market_accel_not_overheated | 189 | 0.0525 | 0.0302 | 0.2839 | 16.2649 | -0.1914 |

## V6 Overlay Read

| overlay_scope | execution_model | dyn_resonance_score_bucket | dyn_risk_accel_score_bucket | dyn_leadlag_catchup_pressure_bps_bucket | l2_impulse_score_bucket | trades | avg_net_bps | win_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| execution_model+bullish_common_mode_score_bucket | maker_light |  |  |  |  | 758 | -0.8469 | 0.3760 |
| execution_model+dyn_resonance_score_bucket | maker_light | mid |  |  |  | 1120 | -0.9922 | 0.3929 |
| execution_model+dyn_risk_accel_score_bucket | maker_light |  | high |  |  | 966 | -1.0480 | 0.3892 |
| execution_model+l2_impulse_score_bucket | maker_light |  |  |  | low | 1246 | -1.1014 | 0.3852 |
| execution_model+dyn_leadlag_catchup_pressure_bps_bucket | maker_light |  |  | low |  | 868 | -1.1108 | 0.3825 |
| execution_model+bullish_common_mode_score_bucket | maker_light |  |  |  |  | 955 | -1.3786 | 0.3853 |
| execution_model+dyn_leadlag_catchup_pressure_bps_bucket | maker_light |  |  | mid |  | 1045 | -1.5503 | 0.3770 |
| execution_model+dyn_resonance_score_bucket | maker_light | low |  |  |  | 1110 | -1.7618 | 0.3505 |
| execution_model+dyn_risk_accel_score_bucket | maker_light |  | mid |  |  | 857 | -1.7669 | 0.3757 |
| execution_model+l2_impulse_score_bucket | maker_light |  |  |  | mid | 341 | -1.7702 | 0.3607 |
| execution_model+bullish_common_mode_score_bucket | maker_light |  |  |  |  | 107 | -1.7971 | 0.3271 |
| execution_model+dyn_risk_accel_score_bucket | maker_light |  | low |  |  | 818 | -1.9297 | 0.3337 |

## Read

- The useful object is dynamic conjunction, not standalone context: acceleration/resonance only becomes interesting when the BONK book also shows impulse or depth support.
- V6 maker/taker rows remain negative in aggregate, so dynamic gates should be treated as next-round filters for research replay, not execution promotion.
- Lead/lag should be interpreted as catch-up pressure and regime synchronization, not proof that BTC/SOL/meme mechanically lead BONK.
- The best next test is to wire the strongest V7 gate candidates into the episode backtest as additional entry filters and require fold-stable net improvement under maker-light and taker-spread.

## Outputs

- Dynamic features: `date/bonk_v7_dynamic_context_features_20260513_bullish_l2_basket_price_v1.csv`
- Gate candidates: `date/bonk_v7_dynamic_context_gate_candidates_20260513_bullish_l2_basket_price_v1.csv`
- V6 overlay: `date/bonk_v7_dynamic_context_v6_overlay_20260513_bullish_l2_basket_price_v1.csv`
- Summary JSON: `date/bonk_v7_dynamic_context_summary_20260513_bullish_l2_basket_price_v1.json`

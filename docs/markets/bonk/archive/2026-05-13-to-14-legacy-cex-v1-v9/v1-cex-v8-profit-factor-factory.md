# BONK V8 Profit-First Factor Factory

Status: 2026-05-14T05:23:52Z. Run tag: `20260513_bullish_l2_basket_price_v1`. Output tag: `20260513_bullish_l2_basket_price_v1`.

Research infrastructure only: no trading advice, no execution recommendation, and no alpha claim.

## Scope

- Used existing local BONK/Bullish/Binance derived data only; no new raw data pull.
- Rust is the canonical path for the V8 factor panel, train-fitted gate thresholds/weights, executable episode labels, and after-cost backtest.
- Exploratory symbolic patterns were distilled back into simple Rust gates under `exploratory_distilled` and rerun through the canonical episode backtest.
- The objective is low-frequency `$100`-notional episodes after cost, not statistical significance.
- Factor panel rows: `40230`. Factor universe size: `121`. Factor audit rows: `7260`.
- Episode trades: `371632`. Daily rows: `107520`. Summary rows: `43008`.

## Resume Contract

- Manifest: `date/bonk_v8_profit_factor_factory_20260513_bullish_l2_basket_price_v1_manifest.json`
- Checkpoint: `date/bonk_v8_profit_factor_factory_20260513_bullish_l2_basket_price_v1_checkpoint.json`
- Steps are `factor_panel -> factor_audit -> episode_backtest -> report`; completed steps are skipped on resume when outputs still exist.

## Factor Families

- `basis_disagreement`: `6` factors
- `breakout_range`: `8` factors
- `common_mode`: `4` factors
- `depth_shape`: `7` factors
- `event_sequence`: `7` factors
- `flow_burst`: `6` factors
- `interaction`: `7` factors
- `l2_delta`: `20` factors
- `lead_lag`: `6` factors
- `liquidity_adjusted`: `4` factors
- `price_momentum`: `7` factors
- `price_reversal`: `5` factors
- `relative_strength`: `11` factors
- `resonance`: `7` factors
- `volatility`: `7` factors
- `volume_burst`: `5` factors
- `weighted_combo_seed`: `4` factors

## Primary Target-Frequency Candidate Ranking

| rank | execution | candidate | symbol | tp/sl/to | total $ | avg $/day | win | pf | tr/day | max DD | fold/freq read |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/30/20 | 1.1554 | 0.1155 | 55.6% | 1.34 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 2 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/30/30 | 1.1554 | 0.1155 | 55.6% | 1.34 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 3 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/30/60 | 1.1554 | 0.1155 | 55.6% | 1.34 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 4 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/30/10 | 1.1554 | 0.1155 | 55.6% | 1.34 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 5 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 100/30/30 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 6 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 75/30/10 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 7 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 75/30/20 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 8 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 100/30/20 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 9 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 75/30/30 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 10 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 100/30/60 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 11 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 75/30/60 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 12 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 100/30/10 | 1.0847 | 0.1085 | 55.6% | 1.32 | 4.50 | 0.6196 | fold2/3 ok, target freq |
| 13 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/20/20 | 0.8220 | 0.0822 | 51.1% | 1.26 | 4.50 | 0.7441 | fold2/3 ok, target freq |
| 14 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/20/30 | 0.8220 | 0.0822 | 51.1% | 1.26 | 4.50 | 0.7441 | fold2/3 ok, target freq |
| 15 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/20/60 | 0.8220 | 0.0822 | 51.1% | 1.26 | 4.50 | 0.7441 | fold2/3 ok, target freq |
| 16 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 50/20/10 | 0.8220 | 0.0822 | 51.1% | 1.26 | 4.50 | 0.7441 | fold2/3 ok, target freq |
| 17 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 75/20/20 | 0.7513 | 0.0751 | 51.1% | 1.23 | 4.50 | 0.7441 | fold2/3 ok, target freq |
| 18 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 100/20/10 | 0.7513 | 0.0751 | 51.1% | 1.23 | 4.50 | 0.7441 | fold2/3 ok, target freq |
| 19 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 75/20/30 | 0.7513 | 0.0751 | 51.1% | 1.23 | 4.50 | 0.7441 | fold2/3 ok, target freq |
| 20 | maker_light | `btc_market_lead_book_support` | BONK1MUSDT | 75/20/60 | 0.7513 | 0.0751 | 51.1% | 1.23 | 4.50 | 0.7441 | fold2/3 ok, target freq |

## Upper Bound And Stress

- `mid_research` is reported only as an upper bound.
- `maker_light` and `taker_spread` are the primary rows.
- `wide_stress` is the downside stress row.

## Diagnostics

- Validation passed: `true`; duplicate trade ids `0`, missing exits `0`, daily/trade PnL diff `0.00000000`, non-overlap violations `0`, cost monotonic violations `0`.
- Fold stability rows: `10752`. Parameter sensitivity rows: `168`. Single-day dependence rows: `10752`. Failure diagnostic rows: `10752`.

## Exploratory Model Layer

Python exploration reads the Rust V8 factor panel and is discovery-only: LightGBM, RandomForest, and symbolic pair scans suggest interpretable interactions, while executable candidates are tested only after being expressed as Rust gates and rerun through the canonical episode backtest.
- Exploratory model metrics: `date/bonk_v8_exploratory_model_metrics_20260513_bullish_l2_basket_price_v1.csv`
- Exploratory feature importance: `date/bonk_v8_exploratory_feature_importance_20260513_bullish_l2_basket_price_v1.csv`
- Exploratory symbolic candidates: `date/bonk_v8_exploratory_symbolic_candidates_20260513_bullish_l2_basket_price_v1.csv`
- Distilled Rust gate group: `exploratory_distilled`.

## Outputs

- factor panel: `data/bonk/v1/derived/bonk_v8_factor_panel/bonk_v8_factor_panel_20260513_bullish_l2_basket_price_v1.parquet`
- factor catalog: `date/bonk_v8_factor_catalog_20260513_bullish_l2_basket_price_v1.csv`
- factor audit: `date/bonk_v8_factor_audit_20260513_bullish_l2_basket_price_v1.csv`
- candidate gates: `date/bonk_v8_candidate_gates_20260513_bullish_l2_basket_price_v1.csv`
- trades: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_trades.csv`
- daily: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_daily.csv`
- summary: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_summary.csv`
- exit reasons: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_exit_reasons.csv`
- fold stability: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_fold_stability.csv`
- non-overlap: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_non_overlap.csv`
- parameter sensitivity: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_parameter_sensitivity.csv`
- single-day dependence: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_single_day_dependence.csv`
- failure diagnostics: `date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_failure_diagnostics.csv`
- completion: `date/bonk_v8_profit_factor_factory_20260513_bullish_l2_basket_price_v1_completion.json`
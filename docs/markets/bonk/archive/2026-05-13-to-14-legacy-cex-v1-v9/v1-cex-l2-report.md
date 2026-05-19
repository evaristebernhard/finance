# BONK Bullish L2 + CEX Regime 报告 v1

- `run_tag`: `20260513_bullish_l2_basket_price_v1`
- 实现：Rust streaming gzip CSV 聚合；Python 脚本保留作 baseline/回滚。
- 数据源：Tardis downloadable CSV，exchange=`bullish`。
- 当前版本只使用 `book_snapshot_25`、`book_ticker`、`trades`，没有使用 `incremental_book_L2`。
- Bullish `BONK1M*` 价格按每 1M BONK 报价保存，同时派生 `price_per_token = price / 1_000_000`。
- `trades.side` 暂记为 exchange-reported side；未在本报告中断言 taker buy/sell 语义。
- 本报告只评价数据质量和现象稳定性入口，不输出交易规则，也不声称 alpha。
- State/covariance symbols: `BONK1MUSDC,BONK1MUSDT,BTCUSDC,DOGEUSDC,ETHUSDC,PENGUUSDC,PEPE1MUSDC,SHIB1MUSDC,SOLUSDC,SUIUSDC,WIFUSDC`；summary/factor tests 聚焦 path-labeled symbols。
- Rust report elapsed: `63.76s`。
- Price context status: `available`；run_tag=`20260513_bullish_l2_basket_price_v1`。

## 输出文件

- L2 state parquet: `data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet`
- Covariance state parquet: `data/bonk/v1/derived/bonk_cex_covariance_state/bonk_cex_covariance_state_20260513_bullish_l2_basket_price_v1.parquet`
- Path labels parquet: `data/bonk/v1/derived/bonk_path_labels/bonk_path_labels_20260513_bullish_l2_basket_price_v1.parquet`
- Quality CSV: `date/bonk_v1_cex_l2_quality_20260513_bullish_l2_basket_price_v1.csv`
- Summary CSV: `date/bonk_v1_cex_l2_summary_20260513_bullish_l2_basket_price_v1.csv`
- Factor tests CSV: `date/bonk_v1_cex_l2_factor_tests_20260513_bullish_l2_basket_price_v1.csv`
- Stability CSV: `date/bonk_v1_cex_l2_stability_20260513_bullish_l2_basket_price_v1.csv`
- Kline price context parquet: `data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet`
- Kline price context summary CSV: `date/bonk_v1_cex_price_context_summary_20260513_bullish_l2_basket_price_v1.csv`

## 覆盖与质量

| symbol | state rows | raw files | raw rows | first ts | last ts | median price/1M | median price/token | median spread bps | trades | abnormal spread rows | future missing 12h/100bps |
|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| BONK1MUSDC | 20103 | 42 | 3334900 | 2026-04-29T00:00:00Z | 2026-05-12T23:59:00Z | 6.549000 | 0.000006549000 | 2.74 | 388533 | 0 | 750 |
| BONK1MUSDT | 20127 | 42 | 3758343 | 2026-04-29T00:00:00Z | 2026-05-12T23:59:00Z | 6.546500 | 0.000006546500 | 1.59 | 45839 | 0 | 722 |

- Raw file errors: `0`；empty raw files: `84`。
- Label horizons: `[1, 4, 12]` hours; fixed first-passage barriers: `[50, 100, 200, 300]` bps。
- 最后 H 小时样本会被标成 `future_missing`，避免用不存在的未来路径。

## Kline Price Context

- 价格背景层只使用 Binance public spot 1m kline；它用于 market/meme/SOL 对照，不作为交易规则或 alpha 证据。
- Context rows: `262080`；available symbols: `BONKUSDT,BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,PEPEUSDT,SHIBUSDT,WIFUSDT,SUIUSDT,APTUSDT,ARBUSDT,OPUSDT,PENGUUSDT`；missing symbols: `none`。
| context | coverage | total return bps | BONK relative bps |
|---|---:|---:|---:|
| BTC/ETH/SOL market | 100.0% | 541.29 | 737.68 |
| meme basket | 100.0% | 1066.45 | 212.53 |
| SOL | 100.0% | 1148.57 | 130.40 |
- BONK total return over context window: `1278.98` bps。

## 因子诊断快读

| symbol | H | factor | high rows | high upper first | baseline upper | edge | median factor |
|---|---:|---|---:|---:|---:|---:|---:|
| BONK1MUSDC | 1h | `snapshot_count` | 6670 | 21.9% | 14.2% | 7.7% | 89.0000 |
| BONK1MUSDC | 1h | `trade_count` | 6670 | 21.5% | 14.2% | 7.3% | 31.0000 |
| BONK1MUSDC | 1h | `book_ticker_count` | 6670 | 18.3% | 14.2% | 4.1% | 73.0000 |
| BONK1MUSDC | 1h | `trade_notional_quote_sum` | 6670 | 18.3% | 14.2% | 4.0% | 4037.0389 |
| BONK1MUSDC | 1h | `wobi25_mean` | 6670 | 16.9% | 14.2% | 2.7% | 0.0454 |
| BONK1MUSDC | 1h | `depth_imbalance_25_mean` | 6670 | 16.9% | 14.2% | 2.7% | 0.0454 |
| BONK1MUSDC | 4h | `snapshot_count` | 6611 | 45.6% | 42.2% | 3.4% | 89.0000 |
| BONK1MUSDC | 4h | `trade_count` | 6611 | 45.3% | 42.2% | 3.2% | 31.0000 |
| BONK1MUSDC | 4h | `trade_notional_quote_sum` | 6611 | 44.6% | 42.2% | 2.5% | 4053.5320 |
| BONK1MUSDC | 4h | `wobi25_mean` | 6611 | 44.1% | 42.2% | 1.9% | 0.0459 |
| BONK1MUSDC | 4h | `depth_imbalance_25_mean` | 6611 | 44.1% | 42.2% | 1.9% | 0.0459 |
| BONK1MUSDC | 4h | `spread_bps_median` | 6611 | 44.1% | 42.2% | 1.9% | 3.1878 |
| BONK1MUSDC | 12h | `spread_bps_median` | 6451 | 60.8% | 55.9% | 4.9% | 3.1888 |
| BONK1MUSDC | 12h | `spread_bps_last` | 6451 | 59.9% | 55.9% | 4.0% | 3.1878 |
| BONK1MUSDC | 12h | `snapshot_count` | 6451 | 52.3% | 55.9% | -3.5% | 89.0000 |
| BONK1MUSDC | 12h | `trade_count` | 6451 | 53.0% | 55.9% | -2.9% | 31.0000 |
| BONK1MUSDC | 12h | `wobi25_mean` | 6451 | 53.5% | 55.9% | -2.4% | 0.0454 |
| BONK1MUSDC | 12h | `depth_imbalance_25_mean` | 6451 | 53.5% | 55.9% | -2.4% | 0.0454 |
| BONK1MUSDT | 1h | `snapshot_count` | 6688 | 19.3% | 14.3% | 5.0% | 128.0000 |
| BONK1MUSDT | 1h | `book_ticker_count` | 6688 | 17.7% | 14.3% | 3.4% | 110.0000 |
| BONK1MUSDT | 1h | `microprice_offset_bps_mean` | 6688 | 11.9% | 14.3% | -2.4% | 0.4812 |
| BONK1MUSDT | 1h | `wobi25_mean` | 6688 | 16.4% | 14.3% | 2.1% | 0.0486 |
| BONK1MUSDT | 1h | `depth_imbalance_25_mean` | 6688 | 16.4% | 14.3% | 2.1% | 0.0486 |
| BONK1MUSDT | 1h | `trade_count` | 6688 | 15.9% | 14.3% | 1.6% | 4.0000 |
| BONK1MUSDT | 4h | `spread_bps_median` | 6628 | 47.4% | 42.3% | 5.1% | 2.7689 |
| BONK1MUSDT | 4h | `spread_bps_last` | 6628 | 47.0% | 42.3% | 4.7% | 2.8563 |
| BONK1MUSDT | 4h | `microprice_offset_bps_mean` | 6628 | 40.4% | 42.3% | -1.9% | 0.4793 |
| BONK1MUSDT | 4h | `snapshot_count` | 6628 | 43.8% | 42.3% | 1.5% | 128.0000 |
| BONK1MUSDT | 4h | `book_ticker_count` | 6628 | 43.7% | 42.3% | 1.4% | 110.0000 |
| BONK1MUSDT | 4h | `wobi25_mean` | 6628 | 43.7% | 42.3% | 1.4% | 0.0491 |
| BONK1MUSDT | 12h | `spread_bps_median` | 6468 | 64.5% | 55.9% | 8.6% | 2.7724 |
| BONK1MUSDT | 12h | `spread_bps_last` | 6468 | 63.1% | 55.9% | 7.2% | 2.8719 |
| BONK1MUSDT | 12h | `snapshot_count` | 6468 | 52.4% | 55.9% | -3.5% | 128.0000 |
| BONK1MUSDT | 12h | `wobi25_mean` | 6468 | 52.7% | 55.9% | -3.2% | 0.0484 |
| BONK1MUSDT | 12h | `depth_imbalance_25_mean` | 6468 | 52.7% | 55.9% | -3.2% | 0.0484 |
| BONK1MUSDT | 12h | `trade_count` | 6468 | 53.7% | 55.9% | -2.2% | 4.0000 |

## 稳定性检查入口

报告和 CSV 已显式输出四类稳定性检查入口：

- `non_overlap`: 按 horizon stride 抽样，降低重叠标签自相关。
- `placebo_shift`: 因子整体滞后 60 分钟后重测，排查伪相关。
- `forward_split`: 前半窗口和后半窗口分别计算 high-bucket edge。
- `barrier_sensitivity`: 50/100/200/300 bps barrier 的 baseline first-passage 变化。

- Stability checks present: `barrier_sensitivity,forward_split,full_sample_reference,non_overlap,placebo_shift`。
# MON/USDC V1 CEX Dynamics Report

状态: `20260512_cex_dynamics_futures_v2`。

这份报告把研究重心从链上单事件切到 `CEX anchor -> DEX lag/dislocation -> path stopping labels`。它不运行 RPC、不重采链上 raw data、不声称已经得到可执行套利策略。已发现 Binance USD-M futures `MONUSDT` kline，本次使用 futures `MONUSDT` 作为 MON anchor；CEX basket 仍用于市场状态压缩。

## 数据覆盖

- Binance spot kline CSV files: `210`
- Binance spot kline rows: `2160000`
- Binance USD-M futures kline CSV files: `13`
- Binance USD-M futures kline rows: `142560`
- Binance aggTrade CSV files: `0`
- Binance aggTrade rows: `0`
- ignored non-CSV files: `227`
- CEX symbols available: `APTUSDT, ARBUSDT, BNBUSDT, BONKUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, MONUSDT, OPUSDT, PEPEUSDT, SEIUSDT, SHIBUSDT, SOLUSDT, SUIUSDT, TIAUSDT, WIFUSDT`
- minute reference rows: `125368`
- event price rows: `2147018`
- market-state rows: `152533`
- DEX lag panel rows: `2147000`

## Market-State Summary

| Frequency | Rows | CEX Factor Rows | Anchor Source | compressed_range | positive_cusum | Median Realized Vol bps |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| 1h | 2091 | 2091 | binance_um_futures_monusdt | 53.80% | 88.14% | 110.7428 |
| 1m | 125368 | 125368 | binance_um_futures_monusdt | 24.89% | 49.89% | 109.7941 |
| 5m | 25074 | 25074 | binance_um_futures_monusdt | 27.43% | 57.47% | 109.7992 |

## DEX-CEX / Reference Lag Summary

| Group | Value | Rows | Priced Rows | Median Abs Dislocation bps | Cost-Adjusted Positive | Best Lag min | Best Lag Corr |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| overall | all | 2147000 | 2147000 | 13.1724 | 0.24% | 0 | 0.0989 |
| pool | 0x5afd3ec861f6104af26e8755abcc1f876de77620 | 623940 | 623940 | 13.1628 | 0.29% | 0 | 0.0724 |
| pool | 0x5e60bc3f7a7303bc4dfe4dc2220bdc90bc04fe22 | 271931 | 271931 | 14.6397 | 0.24% | 0 | 0.1032 |
| pool | 0x63e48b725540a3db24acf6682a29f877808c53f2 | 1030483 | 1030483 | 12.6524 | 0.18% | 0 | 0.2801 |
| pool | 0x659bd0bc4167ba25c62e05656f78043e7ed4a9da | 220646 | 220646 | 14.1458 | 0.34% | 0 | 0.0795 |

## 研究解释

- `MKT/L1/MEME/SIZE_ROT/LIQ/avg_corr` 是低算力 CEX 状态压缩，不是机器学习模型。
- 如果 `anchor_source = binance_um_futures_monusdt`，`dislocation_bps` 表示 DEX pool 相对 Binance USD-M futures MONUSDT 的偏离。
- 如果 `anchor_source = dex_minute_reference_fallback`，`dislocation_bps` 表示单池价格相对聚合 minute reference 的偏离，不是相对 Binance 的真实偏离。
- 订单簿因子放到 v2/live collector；v1 不回补历史 order book，也不信 raw depth 单独作为阻力。
- `barrier_first_hit`、`compressed_range`、`positive_cusum_regime` 是价格序列停时标签，用来替代过于平的固定 future return。

## 输出

- `data/mon_usdc/v1/derived/mon_usdc_cex_market_state/dt=20260512-c/mon_usdc_mon_usdc_cex_market_state_20260512_cex_dynamics_futures_v2.parquet`
- `data/mon_usdc/v1/derived/mon_usdc_cex_dex_lag_panel/dt=20260512-c/mon_usdc_mon_usdc_cex_dex_lag_panel_20260512_cex_dynamics_futures_v2.parquet`
- `date/mon_usdc_v1_cex_dynamics_summary_20260512_cex_dynamics_futures_v2.csv`
- `date/mon_usdc_v1_cex_dex_lag_summary_20260512_cex_dynamics_futures_v2.csv`
- `date/mon_usdc_v1_cex_dynamics_completion_20260512_cex_dynamics_futures_v2.json`

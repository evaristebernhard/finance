# MON/USDC V1.5 Binance Order Book Dynamics Report

状态: `20260512_orderbook_v1`。

这份报告使用 Binance public data 的 USD-M futures `MONUSDT` 免费历史数据：`bookDepth` 粗深度快照与 `aggTrades` 主动成交流。它不是逐笔全量 L2，也不能直接计算严格 OFI；更精细的 `depth/depthSnapshot/bookTicker` 需要 live collector 或 Tardis/Crypto Lake 路线。

## 数据覆盖

- expected days: `100`
- bookDepth CSV files: `99`
- bookDepth rows: `3178224`
- bookDepth snapshots: `264852`
- orderbook state rows: `136916`
- aggTrades CSV files: `13`
- aggTrade rows: `5404053`
- trade-flow state rows: `142486`
- DEX lag rows: `2147000`
- joined panel rows: `2147000`
- missing bookDepth days: `2026-05-11`
- missing aggTrade days: `2026-05-11`

## Futures Basis 背景

- common trade/mark rows: `142560`
- median trade-mark basis: `0.0000` bps
- median abs trade-mark basis: `1.4894` bps
- p90 abs trade-mark basis: `6.0644` bps
- median premium index: `-1.8766` bps
- p90 abs premium index: `13.2436` bps

## Overall 结果

- depth coverage: `100.00%`
- trade-flow coverage: `99.98%`
- median abs DEX-CEX dislocation: `13.1723` bps
- cost-adjusted positive rate: `0.24%`

## Regime Summary

| Group | Value | Rows | Depth Coverage | Trade Coverage | Median Abs Dislocation bps | Median Trade Imbalance | Cost-Adjusted Positive |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| depth_vacuum | false | 1807441 | 100.00% | 99.98% | 13.3060 | 0.0075 | 0.23% |
| depth_vacuum | true | 339559 | 100.00% | 99.97% | 12.5067 | 0.0189 | 0.29% |
| overall | all | 2147000 | 100.00% | 99.98% | 13.1723 | 0.0090 | 0.24% |
| trade_imbalance_sign | balanced | 151248 | 100.00% | 100.00% | 13.7843 | 0.0013 | 0.36% |
| trade_imbalance_sign | buy_pressure | 1010195 | 100.00% | 100.00% | 12.5245 | 0.3971 | 0.25% |
| trade_imbalance_sign | missing | 416 | 100.00% | 0.00% | 9.6939 |  | 0.00% |
| trade_imbalance_sign | sell_pressure | 985141 | 100.00% | 100.00% | 13.7750 | -0.3948 | 0.21% |
| wall_side | ask_wall | 47516 | 100.00% | 100.00% | 11.3000 | -0.0013 | 0.48% |
| wall_side | balanced | 10672 | 100.00% | 99.88% | 12.8622 | -0.0354 | 0.15% |
| wall_side | bid_wall | 2088812 | 100.00% | 99.98% | 13.2200 | 0.0093 | 0.23% |

## Factor Tests

| Factor | Target | N | Spearman | High-Low Mean | High Positive Rate |
| --- | --- | ---: | ---: | ---: | ---: |
| burst_trade_count | abs_dislocation_bps | 2146584 | 0.1304 | 6.5311 | 100.00% |
| total_trade_quote | abs_dislocation_bps | 2146584 | 0.1095 | 5.3168 | 100.00% |
| sweep_intensity | abs_dislocation_bps | 2146584 | -0.0918 | -4.4076 | 100.00% |
| max_trade_quote | abs_dislocation_bps | 2146584 | 0.0798 | 4.2327 | 100.00% |
| depth_imbalance_5pct | abs_dislocation_bps | 2147000 | -0.0606 | -3.4891 | 100.00% |
| wall_asymmetry | abs_dislocation_bps | 2147000 | 0.0606 | 3.4893 | 100.00% |
| trade_imbalance | abs_dislocation_bps | 2146584 | -0.0528 | -0.4659 | 100.00% |
| ask_notional_depth | abs_dislocation_bps | 2147000 | 0.0435 | 0.7868 | 100.00% |
| depth_imbalance_3pct | abs_dislocation_bps | 2147000 | -0.0189 | -1.9576 | 100.00% |
| depth_imbalance_1pct | abs_dislocation_bps | 2147000 | 0.0165 | -0.3482 | 100.00% |
| liquidity_slope | abs_dislocation_bps | 2147000 | 0.0039 | -0.6355 | 100.00% |
| bid_notional_depth | abs_dislocation_bps | 2147000 | -0.0021 | -1.4431 | 100.00% |

## 研究解释

- `percentage < 0` 视为 bid-side depth，`percentage > 0` 视为 ask-side depth；`1pct/3pct/5pct` 使用对应范围内最大 cumulative notional，避免重复相加。
- `depth_imbalance = (bid - ask) / (bid + ask)`，正值表示 bid depth 更厚；`wall_asymmetry = log(ask_5pct / bid_5pct)`，正值表示 ask wall 更厚。
- DEX event join 使用 `source_ts <= event_timestamp` 的最近 `bookDepth` 快照；`aggTrades` 使用上一完整分钟，避免当前分钟偷看未来。
- `liquidity_vacuum` 是 `1pct` 双边 depth 处在全样本底部 20% 的状态标签。
- 这仍是解释性研究，不是可执行交易规则；若粗深度/成交流没有解释力，上更复杂模型也大概率只是拟合噪声。

## 输出

- `data/mon_usdc/v1/derived/mon_usdc_cex_orderbook_state/dt=20260512-o/mon_usdc_mon_usdc_cex_orderbook_state_20260512_orderbook_v1.parquet`
- `data/mon_usdc/v1/derived/mon_usdc_cex_trade_flow_state/dt=20260512-o/mon_usdc_mon_usdc_cex_trade_flow_state_20260512_orderbook_v1.parquet`
- `data/mon_usdc/v1/derived/mon_usdc_cex_dex_orderbook_lag_panel/dt=20260512-o/mon_usdc_mon_usdc_cex_dex_orderbook_lag_panel_20260512_orderbook_v1.parquet`
- `date/mon_usdc_v1_cex_orderbook_summary_20260512_orderbook_v1.csv`
- `date/mon_usdc_v1_cex_orderbook_factor_tests_20260512_orderbook_v1.csv`
- `date/mon_usdc_v1_cex_orderbook_completion_20260512_orderbook_v1.json`

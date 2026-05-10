# CHOG Memecoin 第一版数据分析

状态: 2026-05-08。基于当前 `data/chog/v1` 里已经质量检查通过的 memecoin 路径数据，以及 `date/chog_prices_476h_1h.csv` 小时价格序列。

本报告是第一版研究结论，不是交易信号。当前可做的是识别市场结构、流量解释力和候选因子方向；还不够做稳健实盘判断。

## 1. 数据范围

| 指标 | 值 |
| --- | --- |
| event feature rows | 18,795 |
| hourly pool feature rows | 2,226 |
| unique txs | 15,422 |
| pools / DEXes | 5 / 4 |
| event block window | 66509017..72992679 |
| event time window | 2026-04-07T07:44:45Z -> 2026-05-07T08:56:00Z |
| price hours | 476 (299 observed, 177 forward_fill) |
| price time window | 2026-04-17T06:00:00Z -> 2026-05-07T01:00:00Z |

本次脚本产物:

```text
date/chog_memecoin_v1_pool_summary_20260508.csv
date/chog_memecoin_v1_daily_summary_20260508.csv
date/chog_memecoin_v1_hourly_market_features_20260508.csv
date/chog_memecoin_v1_factor_tests_20260508.csv
```

复现命令:

```bash
python scripts/analyze_chog_memecoin_v1.py
```

价格样本从 `2026-04-17T06:00:00Z` 到 `2026-05-07T01:00:00Z`，累计收益约 `79.33%`。价格样本和链上小时特征重叠 `476` 个小时。

## 2. 核心结论

1. CHOG 仍然是高度主池驱动市场。`nad-fun` 主池占 `71.57%` 的 swap 事件和 `95.84%` 的 CHOG 成交量，其他池子更多是补充流动性。
2. 事件笔数偏卖出，但金额只轻微偏净买入。全样本 `buy_chog=505.49M`，`sell_chog=502.14M`，净买入 `3.35M`，只占总成交 `0.33%`。因此单看 buy/sell count 会误导。
3. 成交额极度肥尾。Top 1% swap 贡献 `31.89%` 的 CHOG 成交量，top 5% 贡献 `65.13%`。后续因子要区分“大单冲击”和“小单噪声”。
4. 同小时解释力强，预测力还弱。`net_buy_chog` 对同小时价格收益 Spearman IC 为 `0.494`；但未来收益里最强的单因子 Spearman 也只有 `0.155` 左右，第一版只能作为候选方向。

## 3. 池子结构

| DEX | Pool | Quote | Events | Event Share | CHOG Volume | Volume Share | Net Buy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| nad-fun | 0x116e7d...d7d8f1 | MON | 13451 | 71.57% | 965.75M | 95.84% | 3.46M |
| atlantis-dex | 0xbfca90...5c4959 | MON | 2700 | 14.37% | 40.64M | 4.03% | -143.17k |
| noxa | 0xd215a9...15b772 | USDC | 707 | 3.76% | 563.33k | 0.06% | 6.03k |
| uniswap | 0xde4c4a...4a7a6d | MON | 1648 | 8.77% | 545.30k | 0.05% | 17.51k |
| noxa | 0xd23e06...0cb305 | MON | 289 | 1.54% | 133.39k | 0.01% | 591.58 |

解释:

- `nad-fun` 主池占绝大多数真实成交量，适合作为 CHOG 市场方向的主因子来源。
- `atlantis-dex` 事件数不低，但成交量只占 `4.03%`，更多反映碎片化交易。
- 其他池子事件占比高于成交量占比，说明小额交易比较多，不能用事件数直接代表市场冲击。

## 4. 日级流量

成交量最高的日期:

| Date | Events | CHOG Volume | Net Buy | Net/Volume |
| --- | --- | --- | --- | --- |
| 2026-04-10 | 1398 | 111.50M | 11.81M | 10.59% |
| 2026-04-11 | 902 | 74.25M | -2.29M | -3.09% |
| 2026-04-09 | 809 | 61.81M | -11.70M | -18.93% |
| 2026-05-06 | 1004 | 59.15M | 6.61M | 11.17% |
| 2026-04-12 | 712 | 53.22M | -5.76M | -10.82% |

净买入/净卖出最极端的日期:

| Side | Date | Events | Net Buy | CHOG Volume | Net/Volume |
| --- | --- | --- | --- | --- | --- |
| net buy | 2026-04-10 | 1398 | 11.81M | 111.50M | 10.59% |
| net buy | 2026-04-24 | 999 | 8.21M | 48.29M | 17.00% |
| net buy | 2026-05-06 | 1004 | 6.61M | 59.15M | 11.17% |
| net buy | 2026-04-22 | 542 | 3.65M | 22.47M | 16.23% |
| net buy | 2026-05-07 | 384 | 3.61M | 15.10M | 23.91% |
| net sell | 2026-04-09 | 809 | -11.70M | 61.81M | -18.93% |
| net sell | 2026-04-12 | 712 | -5.76M | 53.22M | -10.82% |
| net sell | 2026-04-18 | 430 | -5.32M | 40.90M | -13.01% |
| net sell | 2026-04-27 | 556 | -4.37M | 18.65M | -23.46% |
| net sell | 2026-04-15 | 533 | -3.39M | 42.01M | -8.06% |

解释:

- `2026-05-06` 是当前样本里成交量最高日，且净买入明显，和价格样本末端的上行阶段一致。
- `2026-04-24` 同时是高成交和强净买入日，属于后续需要重点回放的上涨冲击样本。
- `2026-04-18`、`2026-04-12`、`2026-04-27` 是较强净卖出日，适合作为风险控制样本。

## 5. 大单集中度

按单笔 `chog_amount` 看成交集中度:

| Bucket | Threshold | Events | Volume Share |
| --- | --- | --- | --- |
| top 50% | 2.26k | 9398 | 99.66% |
| top 10% | 110.00k | 1901 | 80.64% |
| top 5% | 237.19k | 940 | 65.13% |
| top 1% | 872.77k | 188 | 31.89% |

最大单笔交易:

| Time | DEX | Direction | CHOG | Quote | Tx |
| --- | --- | --- | --- | --- | --- |
| 2026-04-18T19:53:41Z | nad-fun | sell_chog | 10.02M | 212.43k | 0x5b6ad1...0d3995 |
| 2026-04-12T20:25:07Z | nad-fun | sell_chog | 8.77M | 235.93k | 0xc68d89...b42caf |
| 2026-05-06T21:26:15Z | nad-fun | buy_chog | 6.08M | 303.59k | 0x9905ff...1a6793 |
| 2026-04-09T00:59:44Z | nad-fun | sell_chog | 5.55M | 153.42k | 0xfc808e...bd6be8 |
| 2026-05-06T07:06:46Z | nad-fun | sell_chog | 5.35M | 188.65k | 0x74a15a...b0a8cf |
| 2026-04-29T01:02:41Z | nad-fun | buy_chog | 5.05M | 177.12k | 0x51e28d...b306d0 |
| 2026-04-10T00:41:32Z | nad-fun | sell_chog | 4.84M | 120.20k | 0x3d2445...47bd8a |
| 2026-04-27T17:09:36Z | nad-fun | sell_chog | 4.75M | 159.18k | 0x37669e...984025 |

解释:

大单占比太高，所以后续信号最好拆成:

```text
large_trade_net_flow
small_trade_count_imbalance
large_trade_follow_through
large_sell_absorption
```

而不是只用总 `net_buy_chog`。

## 6. 价格与链上因子

同小时相关性只能说明解释力，不能当预测:

| Factor | N | Pearson | Spearman | Top-Bottom |
| --- | --- | --- | --- | --- |
| net_buy_chog | 475 | 0.555 | 0.494 | 3.49% |
| net_flow_ratio | 475 | 0.299 | 0.392 | 2.45% |
| buy_event_ratio | 475 | 0.053 | 0.151 | 0.46% |
| events | 475 | 0.148 | 0.060 | 0.74% |
| active_blocks | 475 | 0.135 | 0.055 | 0.67% |
| pools | 475 | 0.086 | 0.046 | 0.70% |

未来收益候选因子:

| Factor | Target | N | Pearson | Spearman | Top-Bottom |
| --- | --- | --- | --- | --- | --- |
| priority_fee_gwei_mean | fwd_24h | 452 | -0.013 | 0.155 | 4.63% |
| effective_gas_gwei_mean | fwd_24h | 452 | -0.013 | 0.155 | 4.63% |
| log_chog_volume | fwd_24h | 452 | 0.137 | 0.137 | 4.70% |
| net_buy_chog | fwd_3h | 473 | 0.126 | 0.125 | 1.85% |
| effective_gas_gwei_mean | fwd_12h | 464 | -0.004 | 0.120 | 2.57% |
| priority_fee_gwei_mean | fwd_12h | 464 | -0.004 | 0.120 | 2.57% |
| events | fwd_24h | 452 | 0.086 | 0.110 | 3.29% |
| active_blocks | fwd_24h | 452 | 0.088 | 0.108 | 2.52% |
| buy_event_ratio | fwd_12h | 464 | 0.110 | 0.108 | 2.74% |
| log_chog_volume | fwd_1h | 475 | -0.060 | -0.079 | -0.45% |

第一版解读:

- `net_buy_chog` 对同小时收益解释力最强，符合 swap 是价格发现源的直觉。
- 对未来 3h，`net_buy_chog` 有弱正相关，top/bottom 三分位差约 `1.85%`。
- 24h 上 `log_chog_volume` 和事件活跃度偏正，像“波动扩张后趋势延续”，但样本仍短。
- gas/priority fee 的 12h/24h Spearman 偏正，但 Pearson 接近 0，可能是 regime 或时间趋势，不应单独使用。

## 7. 下一版建议

1. 在 memecoin features 里加入大单分层: top 1%、top 5%、固定 CHOG/USD 阈值。
2. 增加池子流动性和成交额 USD 标准化，构建 `net_buy_usd / liquidity_usd`。
3. 把价格小时序列继续向前补到 `2026-04-12`，否则前五天链上数据不能进入因子检验。
4. 做事件后路径研究: 大额买入/卖出后的 1h、3h、6h、24h 平均路径。
5. 分开测试主池和非主池，避免小池事件数污染主池成交量信号。

## 8. 局限

- 价格样本只有 476 小时，其中 `177` 小时是 forward fill。
- 链上样本覆盖 25 天，但价格可检验窗口从 `2026-04-17T06:00:00Z` 才开始。
- 当前只做单因子 IC 和三分位差，没有做费用、滑点、容量、成交延迟和 out-of-sample。
- `quote_amount` 主要是 MON，不是统一 USD；报告里成交量排序主要用 CHOG 数量。

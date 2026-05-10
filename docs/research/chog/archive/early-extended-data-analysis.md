# CHOG 扩展数据分析

数据范围:

| 文件 | 内容 |
| --- | --- |
| `date/chog_prices_476h_1h.csv` | 约 19.8 天小时价格 |
| `date/chog_dex_pairs_snapshot.csv` | DexScreener 当前池子快照 |
| `date/chog_transfer_logs_20k_blocks.csv` | Monad 最近 20k block 的 CHOG transfer logs |
| `date/chog_transfer_hourly_20k_blocks.csv` | transfer logs 小时汇总 |
| `date/chog_pool_flow_20k_blocks.csv` | 已知池子 CHOG 流入/流出 |
| `date/chog_tx_summary_20k_blocks.csv` | transaction 级 CHOG transfer 汇总 |

## 1. 价格路径

`chog_prices_476h_1h.csv` 覆盖:

```text
2026-04-16T19:00:00Z -> 2026-05-06T14:00:00Z
```

基础统计:

```text
rows = 476
observed = 291
forward_fill = 185
fill_pct = 38.87%

start_price = 0.000960763840
end_price = 0.001462409850
return = 52.21%
min_price = 0.000638212623
max_price = 0.001569971548
```

收益统计:

```text
hourly_mean_return = 0.1497%
hourly_median_return = 0.0000%
hourly_std = 3.5452%
q05 = -5.70%
q95 = 5.74%
skew = 1.1715
kurtosis = 10.4582
2sigma_jumps = 32
return_ac1 = -0.0480
abs_return_ac1 = -0.0037
trend_efficiency = 0.0467
```

趋势效率定义:

```text
trend_efficiency = abs(sum(log_return_t)) / sum(abs(log_return_t))
```

`0.0467` 很低。也就是说，虽然 19.8 天累计涨了约 52%，但绝大多数路径长度都消耗在震荡和跳跃里，不是平滑趋势。

最大回撤:

```text
max_drawdown = -37.84%
drawdown_start = 2026-04-25T22:00:00Z
drawdown_end = 2026-04-29T20:00:00Z
```

滚动 24 小时:

```text
best_24h_return = 65.20% at 2026-04-24T20:00:00Z
worst_24h_return = -26.12% at 2026-04-28T08:00:00Z
latest_24h_return = 16.47% at 2026-05-06T14:00:00Z
```

结论:

1. 价格序列有强肥尾，跳跃是主导项。
2. 单独价格动量很弱，短周期自相关接近 0。
3. 当前更像“高噪声跳跃上涨”，不是趋势跟踪友好的走势。

## 2. DEX 市场结构

DexScreener 快照显示 CHOG 当前几乎是单池市场:

```text
pairs = 10
total_liquidity_usd = 125,722.09
total_h24_volume_usd = 67,309.47
h24_buys = 457
h24_sells = 744
h24_count_imbalance = -0.2390
```

集中度:

```text
liquidity_hhi = 0.8909
effective_liquidity_pools = 1.12
volume_hhi = 0.9364
effective_volume_pools = 1.07
```

HHI 接近 1 表示高度集中。有效池子数约为 1，说明后续做因子时，主池的 swap、reserve、MEV 基本就代表了 CHOG 市场。

主池:

```text
dex = nad-fun
pair = 0x116e7D070f1888B81E1E0324F56d6746B2D7d8f1
quote = MON
liquidity_share = 94.23%
volume_share = 96.72%
volume_h24_to_liquidity = 0.550
h24_count_imbalance = -0.328
```

价格分散:

```text
liquidity_weighted_price = 0.001433383180
volume_weighted_snapshot_price = 0.001433144061
raw_pair_price_dispersion = 11.38%
liquidity_weighted_abs_deviation = 0.0515%
```

解释:

1. 裸看各池价格最大最小差异有 11.38%，但大部分偏离来自极小流动性池。
2. 按流动性加权后，价格偏离只有 0.0515%，说明有效市场价格主要由主池决定。
3. 24h 卖出笔数多于买入笔数，但价格仍上涨。这说明 buy/sell count 不能直接当作资金流。可能是买单平均规模更大、买单冲击更强，或小额卖单数量更多。

## 3. Transfer Logs 微观结构

20k block 样本覆盖:

```text
2026-05-06T13:43:59Z -> 2026-05-06T15:56:31Z
```

基础统计:

```text
logs = 252
transactions = 114
unique_addresses = 95
total_chog_transferred = 14,780,600.618566
median_transfer = 486.312073
p90_transfer = 94,978.089391
p99_transfer = 1,206,990.354631
max_transfer = 1,314,231.657917
```

集中度:

```text
top10_tx_volume_share = 88.90%
sender_hhi = 0.0986
receiver_hhi = 0.1047
multi_log_txs = 43
pool_related_txs = 101
```

解释:

1. transfer volume 极度集中，top 10 transactions 占 88.90%。
2. 中位数只有 486 CHOG，但 p99 超过 120 万 CHOG，这是典型肥尾链上行为。
3. 43 个交易含 3 条以上 CHOG transfer，说明路由、多跳、池子交互很多。
4. 101/114 个交易和已知池子有关，说明这个样本主要反映交易/路由，而非普通钱包转账。

重要限制:

Transfer logs 会重复记录路由中的中间流转，`total_chog_transferred` 不是真实成交量。更可靠的是看已知池子地址的 CHOG 净流入/净流出。

## 4. 池子方向流

对 CHOG/MON 或 CHOG/USDC 池子:

```text
CHOG transfer to pool   -> 通常表示卖出 CHOG
CHOG transfer from pool -> 通常表示买入 CHOG
```

20k block 聚合:

```text
pool_in_chog = 2,718,266.400578
pool_out_chog = 705,362.542091
net_to_pools_chog = 2,012,903.858487
net_to_pools_usd ~= 2,943.69
```

按主池:

```text
nad-fun MON:
  pool_in_chog = 2,605,038.199198
  pool_out_chog = 681,805.729863
  net_to_pool_chog = 1,923,232.469334
  net_to_pool_usd ~= 2,812.55
  net_to_pool_usd / main_pool_liquidity = 2.37%
```

短窗小时流:

| hour_utc | logs | txs | unique | pool_in_chog | pool_out_chog | net_to_pools_chog | price_return |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-05-06T13:00:00Z | 55 | 24 | 40 | 1,109,629.11 | 129,135.56 | 980,493.55 | -3.84% |
| 2026-05-06T14:00:00Z | 145 | 65 | 70 | 1,465,461.30 | 440,727.43 | 1,024,733.87 | -3.13% |
| 2026-05-06T15:00:00Z | 52 | 25 | 30 | 143,175.99 | 135,499.55 | 7,676.44 | price missing |

这个局部窗口里，池子净流入 CHOG 为正，价格对应小时下跌，方向上是匹配的。但只有 2 个有价格的小时，不能当成统计结论，只能当成一个可继续验证的方向。

## 5. 可以形成的因子

### 5.1 Pool Sell Pressure

定义:

```text
PoolSellPressure_t =
    (CHOG_to_pool_t - CHOG_from_pool_t) * P_t / LiquidityUSD_t
```

解释:

1. 大于 0 表示 CHOG 净流入池子，通常是卖压。
2. 小于 0 表示 CHOG 净流出池子，通常是买压。
3. 除以流动性是为了比较不同时间和不同池子的冲击强度。

当前 20k block:

```text
overall_pool_sell_pressure ~= 2.34% of total liquidity
main_pool_sell_pressure ~= 2.37% of main pool liquidity
```

这是一个比 DexScreener buy/sell count 更接近真实方向压力的变量。

### 5.2 Flow Concentration

定义:

```text
TxVolumeTopShare_t = sum(top_k_tx_volume_t) / total_transfer_volume_t
```

当前:

```text
top10_tx_volume_share = 88.90%
```

含义:

如果大部分链上流量由少数交易贡献，价格行为更可能由大户、路由、套利或 MEV 主导，而不是散户广泛情绪。

### 5.3 Pool Dominance

定义:

```text
PoolDominance_t = main_pool_volume_t / total_volume_t
```

当前 DexScreener 快照:

```text
main_pool_volume_share = 96.72%
main_pool_liquidity_share = 94.23%
```

含义:

做 CHOG 因子时，主池数据优先级最高。其他池子更多用于检查价格偏离和套利空间。

### 5.4 Count-Flow Divergence

DexScreener 24h:

```text
h24_count_imbalance = -0.2390
price_24h_change ~= +10% to +12%
```

这说明卖出笔数占优，但价格上涨。可以定义:

```text
CountPriceDivergence_t = sign(PriceReturn_t) - sign(CountImbalance_t)
```

如果价格涨、count imbalance 却为负，说明:

1. 买单平均金额可能大于卖单。
2. 买单发生在更薄的流动性位置。
3. 有套利或路由使 buy/sell count 失真。

这个分歧本身可能是情绪结构的一部分。

## 6. 初步判断

当前数据支持几个相对稳的判断:

1. CHOG 是单主池市场。主池 nad-fun 决定了绝大部分价格发现。
2. 价格路径肥尾，跳跃驱动明显。不要用简单动量直接下结论。
3. DEX 快照显示过去 24h 卖出笔数更多，但价格仍涨，说明笔数指标太粗。
4. 20k block 的 transfer 样本显示短窗 CHOG 净流入池子，和 13:00、14:00 UTC 小时价格下跌方向一致。
5. transfer volume 高度集中，少数交易支配大部分流量。后续必须做 transaction-level 和 address-level 标签，否则容易把路由/MEV 当成散户情绪。

## 7. 下一步最有价值的数据

接下来不应该继续只扩价格。优先级应该是:

1. 抓主池 swap logs，直接拿 `amount_in/amount_out` 和 swap 方向。
2. 抓主池 reserve 或 slot0，算每笔交易前后价格冲击。
3. 给地址打标签: pool、router、LP、普通钱包、疑似 searcher。
4. 用 `PoolSellPressure_t` 对齐未来 `1h/3h/6h` return，验证是否有预测力。
5. 把 DexScreener 快照定时采集，构造 h1/h6/h24 的时间序列，而不是单点快照。

如果只能先做一个因子，我会做:

```text
MainPoolSellPressure_1h =
    (CHOG_to_main_pool_1h - CHOG_from_main_pool_1h)
    * Price_1h
    / MainPoolLiquidityUSD
```

然后检验:

```text
future_return_{t,1h/3h/6h}
    = alpha + beta * MainPoolSellPressure_t + eps_t
```

预期符号:

```text
beta < 0
```

也就是主池 CHOG 净流入越强，未来收益越差。

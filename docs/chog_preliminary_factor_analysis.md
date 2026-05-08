# CHOG 初步因子分析

本报告使用当前已有数据做初步因子筛选。结论只适合指导下一步采集和建模，不适合直接交易。

计划主入口: [CHOG external 框架吸收计划](./chog_external_absorption_plan.md)。

## 1. 数据

| 数据 | 文件 | 样本 |
| --- | --- | ---: |
| 小时价格 | `date/chog_prices_476h_1h.csv` | 476 小时 |
| 价格因子检验 | `date/chog_price_factor_tests_476h.csv` | 价格类特征 |
| 主池 swap | `date/chog_main_pool_swaps_100k_blocks.csv` | 171 swaps |
| 主池 swap 小时汇总 | `date/chog_main_pool_swaps_hourly_100k_blocks.csv` | 12 小时 |
| transfer 小时汇总 | `date/chog_transfer_hourly_100k_blocks.csv` | 12 小时 |
| 链上小时特征 | `date/chog_flow_features_100k_blocks.csv` | 12 小时 |
| 链上因子检验 | `date/chog_onchain_factor_tests_100k.csv` | 链上流因子 |

价格数据窗口:

```text
2026-04-17T06:00:00Z -> 2026-05-07T01:00:00Z
```

100k block 链上窗口:

```text
swap:     2026-05-06T15:36:29Z -> 2026-05-07T02:25:05Z
transfer: 2026-05-06T15:33:11Z -> 2026-05-07T02:37:28Z
```

## 2. 方法

价格因子用 476 小时样本测试:

```text
factor_t -> future_return_{t,h}
h in {1h, 3h, 6h, 12h, 24h}
```

指标:

```text
Pearson IC
Spearman IC
top tercile return - bottom tercile return
```

链上因子用 100k block 的 12 小时样本测试:

```text
factor_t -> future_return_{t,h}
h in {1h, 2h, 3h, 6h}
```

链上样本太短，所以只看方向，不看显著性。

## 3. 价格类因子

### 3.1 短周期偏反转

1h 到 12h horizon 上，短中期 momentum 多数是负 IC。

代表结果:

| factor | target | Spearman IC | top-bottom |
| --- | ---: | ---: | ---: |
| `mom_12h` | 1h | -0.114 | -0.28% |
| `mom_12h` | 6h | -0.151 | -1.55% |
| `drawdown_24h` | 1h | -0.117 | -0.35% |
| `ma_gap_24h` | 1h | -0.110 | -0.36% |

解释:

短期涨多了，未来 1-6 小时反而偏弱；短期跌深了，未来有一定反弹倾向。这个符合 memecoin 高频噪声和流动性冲击后的均值回归。

### 3.2 24h horizon 上动量/波动反而偏正

24h 未来收益上，部分趋势和波动因子转正。

| factor | target | Spearman IC | top-bottom |
| --- | ---: | ---: | ---: |
| `vol_24h` | 24h | +0.257 | +6.40% |
| `mom_24h` | 24h | +0.214 | +4.80% |
| `ma_gap_24h` | 24h | +0.148 | +4.93% |
| `vol_12h` | 24h | +0.175 | +7.00% |

解释:

CHOG 这种币在日级别上更像“波动扩张 + 趋势延续”。短周期是冲击回撤，拉长到 24h 又出现动量。

### 3.3 长周期过热有反转

`mom_72h`、`mom_120h` 对未来 12h/24h 多为负。

| factor | target | Spearman IC | top-bottom |
| --- | ---: | ---: | ---: |
| `mom_120h` | 12h | -0.240 | -4.74% |
| `mom_120h` | 24h | -0.243 | -7.48% |
| `mom_72h` | 24h | -0.236 | -7.18% |

解释:

太长窗口的涨幅更像“过热”而不是趋势。适合做风险控制，不适合追涨。

## 4. 链上因子

100k block 主池 swap:

```text
swap_rows = 171
swap_hours = 12
buy_swaps = 58
sell_swaps = 113
buy_chog = 10,331,120.83
sell_chog = 5,990,932.17
net_buy_chog = 4,340,188.66
```

核心现象:

```text
卖出笔数更多，但金额是净买入。
```

这说明 `buy/sell count` 不能直接当作情绪指标。CHOG 过去这段更像“大额买单 + 多个小额卖单”的结构。

### 4.1 同小时解释力很强

主池净买入与同小时价格收益高度一致:

| factor | same-hour return corr |
| --- | ---: |
| `main_net_buy_chog` | +0.971 |
| `main_pool_sell_pressure` | -0.975 |
| `main_chog_volume` | +0.854 |
| `transfer_main_net_to_pool_chog` | -0.971 |

定义:

```text
main_pool_sell_pressure =
    (sell_chog - buy_chog) * price_usd / main_pool_liquidity_usd
```

所以:

```text
sell_pressure < 0 表示净买入 CHOG
sell_pressure > 0 表示净卖出 CHOG
```

解释:

swap logs 对当前小时价格变动解释力强，这是正常的，因为它直接就是价格发现。

### 4.2 未来 1-3h 出现反向

链上因子对未来收益的结果:

| factor | target | n | Spearman IC | top-bottom |
| --- | ---: | ---: | ---: | ---: |
| `main_pool_sell_pressure` | fwd_1h | 10 | +0.406 | +2.42% |
| `main_pool_sell_pressure` | fwd_2h | 9 | +0.667 | +7.59% |
| `main_pool_sell_pressure` | fwd_3h | 8 | +0.476 | +10.86% |
| `main_net_buy_chog` | fwd_1h | 10 | -0.406 | -2.42% |
| `main_net_buy_chog` | fwd_2h | 9 | -0.667 | -7.59% |
| `main_net_buy_chog` | fwd_3h | 8 | -0.476 | -10.86% |

这个方向和“净买入后继续涨”的趋势假设相反。更合理的解释是:

1. 大额净买入推动同小时上涨。
2. 之后 1-3 小时出现冲击回撤或获利了结。
3. DeFiLlama 小时价格有稀疏/延迟，可能放大这个反向。
4. 样本只有 8-10 个点，不能下统计结论。

因此，当前链上初步结论不是“追净买入”，而是:

```text
主池净买入是同小时价格冲击因子；
对未来 1-3h 可能更像短期反转因子。
```

### 4.3 活跃度可能是短期过热

`main_swaps`、`main_chog_volume` 对未来 3h 多为负:

| factor | target | n | Spearman IC | top-bottom |
| --- | ---: | ---: | ---: | ---: |
| `main_swaps` | fwd_3h | 8 | -0.707 | -12.93% |
| `main_chog_volume` | fwd_3h | 8 | -0.619 | -9.80% |
| `transfer_logs` | fwd_3h | 8 | -0.571 | -9.80% |

解释:

短窗口内，活跃度高更像情绪冲顶，而不是稳定趋势启动。但这仍需更多小时验证。

## 5. 初步可用因子

### A. 短周期反转因子

```text
ShortReversal_t = -mom_12h_t
```

用途:

```text
预测 1h/3h/6h
```

当前证据:

```text
mom_12h -> fwd_6h Spearman IC = -0.151
```

### B. 日级波动扩张因子

```text
VolExpansion_t = vol_24h_t
```

用途:

```text
预测 24h
```

当前证据:

```text
vol_24h -> fwd_24h Spearman IC = +0.257
top-bottom = +6.40%
```

### C. 长周期过热因子

```text
Overheat_t = mom_72h_t 或 mom_120h_t
```

用途:

```text
风险控制 / 减仓信号
```

当前证据:

```text
mom_120h -> fwd_24h Spearman IC = -0.243
top-bottom = -7.48%
```

### D. 主池冲击反转因子

```text
MainPoolImpact_t =
    (buy_chog_t - sell_chog_t) * price_usd_t / main_pool_liquidity_usd_t
```

用途:

```text
解释同小时价格；
测试未来 1h/2h/3h 是否反转。
```

对象边界:

```text
MainPoolImpact_t 是 G_t impact proxy summary，
不是资金流真值，也不是 q_t/r_t/kappa_t/u_t/p_t 的直接观测；
后者只能作为 proxy/posterior summary 进入后续框架。
```

当前证据:

```text
same-hour corr = +0.971
fwd_2h Spearman IC = -0.667
```

注意: 链上样本只有 12 小时，暂时不能放进正式模型。

## 6. 组合假设

更合理的初步模型不是单因子，而是 horizon 分层:

### 1h-6h

```text
ExpectedReturn_short =
    a
  - b1 * mom_12h
  - b2 * MainPoolImpact
  - b3 * main_chog_volume
```

含义:

短期追涨容易被反杀，大额买入冲击后可能回撤。

### 24h

```text
ExpectedReturn_24h =
    a
  + b1 * vol_24h
  + b2 * mom_24h
  - b3 * mom_120h
```

含义:

日级别上，波动扩张和 24h 动量偏正；但 72h/120h 过热要扣分。

## 7. 当前判断

1. 价格因子里，短周期反转比短周期动量更可信。
2. 24h 维度上，波动扩张和 24h 动量有正向迹象。
3. 长周期涨幅过大后，未来 12h/24h 反而偏弱。
4. 主池 swap 是目前最有价值的链上数据，明显优于 transfer 和 buy/sell count。
5. 主池净买入解释同小时上涨，但未来 1-3h 暂时表现为反转，不是趋势延续。

## 8. 下一步

下一步按 [CHOG external 框架吸收计划](./chog_external_absorption_plan.md) 的 V1 顺序推进。当前因子结论只作为 proxy 候选，不直接升级为策略真值。

1. 给 `v3_swap_sample` 做 checkpoint/resume。
2. 定时化 DexScreener snapshot，形成 `liquidity_usd_t`。
3. 生成 `proxy-observations.jsonl` 草案 schema。
4. 加 receipt/gas outcome 数据面。
5. 做 sender/recipient 的 router/searcher 标签。
6. 用 walk-forward 验证 MainPoolImpact、volume、conflict proxy。

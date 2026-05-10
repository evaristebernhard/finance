# CHOG 链上情绪与价格的数学分析

数据文件: `date/chog_prices_7d_1h.csv`

本文档只做数学和建模层面的分析。当前已有数据只有 7 天小时价格，因此不能真正“找因子”。但如果假设市场情绪一定会在链上留下痕迹，那么合理做法是把情绪视为不可直接观测的潜变量，再用链上交易、流动性、持仓、gas、MEV/OEV、预言机偏离等可观测变量去估计它。

## 1. 价格序列能说明什么

令小时价格为 `P_t`，简单收益为:

```text
r_t = P_t / P_{t-1} - 1
```

对数收益为:

```text
l_t = log(P_t / P_{t-1})
```

当前 CHOG 样本为 168 个小时点，其中 138 个是原始观测，30 个是前值填充。

| 指标 | 数值 |
| --- | ---: |
| 7 天收益 | 49.91% |
| 最低价 | 0.000856528931 |
| 最高价 | 0.001569971548 |
| 高低价振幅 | 83.29% |
| 小时均值收益 | 0.3111% |
| 小时收益标准差 | 3.7561% |
| 最大 1 小时上涨 | 20.51% |
| 最大 1 小时下跌 | -12.96% |
| 最大回撤 | -25.44% |
| lag-1 收益自相关 | -0.0307 |
| abs return lag-1 自相关 | 0.1237 |
| 收益偏度 | 1.0831 |
| 收益峰度 | 9.8797 |
| 2 sigma 跳跃次数 | 13 |

解释:

1. `lag-1` 收益自相关接近 0，说明单独看价格，短周期动量不明显。
2. `abs return` 自相关为正，说明波动有轻微聚集。
3. 峰度接近 10，说明收益分布有明显肥尾。memecoin 的价格变化主要由少数跳跃小时贡献。
4. 趋势效率约为 0.108:

```text
trend_efficiency = abs(sum(l_t)) / sum(abs(l_t))
```

这个值很低，说明虽然 7 天总收益很高，但路径并不平滑，更多是震荡和跳跃共同形成。

## 2. 情绪作为潜变量

设链上情绪为 `S_t`，它不能被直接观测，但能通过链上行为投影出来:

```text
S_t = w_1 X_{flow,t} + w_2 X_{wallet,t} + w_3 X_{lp,t}
    + w_4 X_{gas,t} + w_5 X_{mev,t} + w_6 X_{oracle,t} + eps_t
```

未来收益标签可以定义为:

```text
y_{t,h} = log(P_{t+h} / P_t)
```

然后做一个最小的线性检验:

```text
y_{t,h} = alpha + beta' Z_t + eps_t
```

其中 `Z_t` 是链上特征的标准化向量。对 memecoin 这种肥尾资产，不建议用普通 z-score，建议用 robust z-score:

```text
Z(x_t) = (x_t - median(x)) / MAD(x)
MAD(x) = median(|x_t - median(x)|)
```

## 3. 链上交易情绪因子

### 3.1 主动买卖压力

在 AMM 里，可以按 swap 方向识别主动买入和主动卖出。令 `BuyVol_t` 是一小时内主动买入 CHOG 的美元量，`SellVol_t` 是主动卖出 CHOG 的美元量。

```text
OFI_t = (BuyVol_t - SellVol_t) / (BuyVol_t + SellVol_t)
```

`OFI_t` 接近 1 表示买盘主导，接近 -1 表示卖盘主导。

更进一步可以看价格冲击后的延续性:

```text
ToxicFlow_t = sign(OFI_t) * log(P_{t+1} / P_t)
```

如果大额买入后价格继续涨，说明买盘可能是信息型买盘。如果大额买入后价格回落，说明更像短期情绪冲击或被套利。

### 3.2 交易强度

一小时交易量可以用对数强度处理:

```text
VolIntensity_t = Z(log(1 + VolumeUSD_t))
```

交易笔数强度:

```text
TxIntensity_t = Z(log(1 + SwapCount_t))
```

新钱包参与度:

```text
NewBuyerRatio_t = NewBuyers_t / ActiveBuyers_t
```

情绪上行阶段通常会出现:

```text
OFI_t > 0
VolIntensity_t > 0
NewBuyerRatio_t > 0
```

如果价格上涨但 `NewBuyerRatio_t` 不上升，可能只是老地址自成交、做市或小圈子推价。

## 4. 流动性与持仓结构

### 4.1 LP 压力

设 AMM 池子的美元流动性为 `L_t`:

```text
LPChange_t = log(L_t / L_{t-1})
```

同样的买盘，在低流动性下会造成更大的价格冲击。可以定义单位成交量冲击:

```text
ImpactPerVolume_t = abs(log(P_t / P_{t-1})) / VolumeUSD_t
```

如果 `LPChange_t < 0` 且 `ImpactPerVolume_t` 上升，说明流动性撤退，价格更容易被少量资金推动。

### 4.2 持仓集中度

令第 `i` 个地址持仓占比为 `s_i`，Herfindahl 指数:

```text
HHI_t = sum_i s_i^2
```

`HHI_t` 越高，筹码越集中。可以配合大户净流量:

```text
WhaleFlow_t = WhaleBuyUSD_t - WhaleSellUSD_t
```

一个危险组合是:

```text
PriceUp_t > 0
HHI_t 上升
WhaleFlow_t < 0
```

这表示价格上涨但大户在派发。

## 5. AMM 数学: 情绪如何变成价格

对常数乘积 AMM:

```text
x * y = k
```

其中 `x` 是 CHOG 储备，`y` 是报价资产储备。忽略手续费时，池内价格近似为:

```text
P_pool = y / x
```

当主动买入 CHOG 时，交易者向池子加入 `dy`，取走 `dx`，价格上升。价格冲击可以近似写成:

```text
PriceImpact_t = P_after / P_before - 1
```

如果同样的 `dy` 在不同时间产生不同冲击，主要来自:

1. 池子深度变化。
2. 交易路径变化。
3. MEV/searcher 插入交易。
4. 外部市场价格变化导致套利。

所以仅看价格不够，必须同时看 swap 事件、池子储备和交易排序。

## 6. MEV 指标

MEV 会把“情绪”从普通交易放大成链上可见结构。对 memecoin，最常见的是 sandwich、backrun arbitrage 和抢跑流动性变化。

### 6.1 Sandwich 压力

如果同一个 searcher 在同一 block 内围绕用户交易做:

```text
buy/searcher -> user swap -> sell/searcher
```

或反方向结构，就可以标记为疑似 sandwich。

定义:

```text
SandwichRatio_t = SandwichedVolumeUSD_t / TotalSwapVolumeUSD_t
```

如果 `SandwichRatio_t` 上升，说明散户情绪交易变多，且交易保护较差。它不一定看涨，但通常表示情绪热度上升。

### 6.2 Backrun 套利强度

每次大 swap 后，如果同 block 或后续几个 block 出现套利交易，把池价拉回外部参考价，可以估计:

```text
ArbProfit_t = Revenue_t - InputCost_t - GasCost_t - Fee_t
```

聚合成小时指标:

```text
MEVProfitRate_t = ArbProfitUSD_t / VolumeUSD_t
```

如果 `MEVProfitRate_t` 上升，说明价格发现不连续，市场情绪或流动性正在制造套利空间。

### 6.3 Gas/priority fee 情绪

定义 CHOG 相关交易的 gas 溢价:

```text
GasPremium_t = median(PriorityFee_CHOG_t) / median(PriorityFee_chain_t) - 1
```

当 `GasPremium_t`、`SwapCount_t`、`OFI_t` 同时上升时，通常比单独价格上涨更能代表链上 FOMO。

## 7. 预言机与 OEV

预言机不是情绪本身，但预言机偏离、更新延迟和更新后套利会反映市场压力。如果 CHOG 被任何借贷、永续、结构化产品、指数或链上风控系统引用，就必须把 oracle 纳入分析。

### 7.1 Oracle 偏离

设链上池价为 `P_pool,t`，预言机价格为 `P_oracle,t`:

```text
OracleDeviation_t = (P_pool,t - P_oracle,t) / P_oracle,t
```

绝对偏离:

```text
AbsOracleDeviation_t = abs(OracleDeviation_t)
```

更新延迟:

```text
OracleLag_t = BlockTime_t - OracleUpdatedAt_t
```

如果:

```text
AbsOracleDeviation_t 高
OracleLag_t 高
VolumeIntensity_t 高
```

说明链上价格已经移动，但 oracle 尚未充分反映。这会吸引套利、清算或 OEV 竞争。

### 7.2 OEV

OEV 是 oracle update 触发的可提取价值。粗略定义:

```text
OEV_t = max(Value_after_update_t - Value_before_update_t - ExecutionCost_t, 0)
```

如果涉及清算:

```text
LiquidationOEV_t = max(LiquidationBonus_t - GasCost_t - BidCost_t, 0)
```

如果涉及 AMM 套利:

```text
OracleArbOEV_t = max(ArbRevenue_t - SwapCost_t - GasCost_t, 0)
```

对 memecoin 来说，OEV 是否重要取决于 CHOG 有没有被 oracle 引用。如果没有直接 oracle，可以退一步看“参考价格偏离”:

```text
ReferenceDeviation_t = (P_pool,t - TWAP_t) / TWAP_t
```

其中 `TWAP_t` 可以来自多个池子的成交量加权价格。

## 8. 一个可执行的综合情绪分数

先不要直接上复杂机器学习。样本小、噪声大，先做可解释分数:

```text
SentimentScore_t =
    0.25 * Z(OFI_t)
  + 0.15 * Z(log(1 + VolumeUSD_t))
  + 0.15 * Z(NewBuyerRatio_t)
  + 0.10 * Z(GasPremium_t)
  + 0.10 * Z(-LPChange_t)
  + 0.10 * Z(MEVProfitRate_t)
  + 0.10 * Z(AbsOracleDeviation_t)
  + 0.05 * Z(WhaleFlow_t)
```

这个分数的含义:

1. 买盘、成交、活跃地址代表直接情绪。
2. gas 溢价代表抢交易意愿。
3. LP 撤退代表价格脆弱性。
4. MEV 利润代表链上价格发现的不连续。
5. oracle 偏离代表外部系统尚未同步的压力。
6. 大户流量用于判断上涨是否被派发。

然后测试:

```text
future_return_{t,h} = alpha + beta * SentimentScore_t + eps_t
```

如果 `beta > 0` 且在多个 horizon 上稳定，才说明这个情绪分数可能有预测力。建议 horizon 至少测试:

```text
h in {1h, 3h, 6h, 12h, 24h}
```

## 9. 对 CHOG 下一步最该补的数据

当前价格序列不够。要让上面的模型落地，至少需要这些小时级表:

1. `swaps_1h`: buy volume、sell volume、swap count、unique buyers、unique sellers。
2. `liquidity_1h`: pool reserves、TVL、LP add/remove、price impact。
3. `holders_1h`: holder count、top holder share、HHI、whale net flow。
4. `gas_1h`: CHOG 交易 priority fee、全链 median priority fee、gas premium。
5. `mev_1h`: sandwich volume、backrun count、estimated MEV profit。
6. `oracle_1h`: oracle price、pool TWAP、deviation、update lag、OEV estimate。

最终合成表:

```text
date/chog_onchain_features_1h.csv
```

每行一个小时:

```text
hour_utc, price, return_1h, volume_usd, ofi, lp_change,
new_buyer_ratio, hhi, whale_flow, gas_premium,
sandwich_ratio, mev_profit_rate, oracle_deviation,
oracle_lag, sentiment_score
```

## 10. 结论

价格本身只告诉我们 CHOG 在 7 天内上涨约 50%，但路径噪声极大，最大回撤超过 25%，收益分布肥尾，单纯价格动量没有明显稳定性。

真正有价值的分析应该转向链上微观结构。memecoin 的情绪不会凭空存在，它会反映为主动买盘、交易强度、新钱包涌入、gas 溢价、LP 撤退、MEV 利润扩大、oracle/TWAP 偏离和大户流量变化。

数学上最稳的路线不是直接预测价格，而是先构造可解释的 `SentimentScore_t`，再检验它对未来 `1h/3h/6h/12h/24h` 收益的解释力。如果这个分数只在样本内有效，或者换一天就失效，那它只是噪声。如果它能跨窗口、跨 memecoin、跨池子保持方向一致，才值得继续做成因子。

# CHOG 主池 Swap 数据分析

本轮新增主池 Uniswap V3-style `Swap` logs。相比 ERC-20 `Transfer` logs，Swap logs 能直接给出方向和数量，因此是后续做因子的优先数据。

计划主入口: [CHOG external 框架吸收计划](../framework/external-absorption-plan.md)。

## 新增文件

| 文件 | 内容 |
| --- | --- |
| `date/chog_main_pool_swaps_20k_blocks.csv` | 主池原始 Swap logs |
| `date/chog_main_pool_swaps_hourly_20k_blocks.csv` | 主池 Swap 小时汇总 |
| `date/chog_main_pool_swap_tx_summary_20k_blocks.csv` | 主池 Swap transaction 汇总 |
| `date/chog_flow_features_20k_blocks.csv` | 价格、主池 swap、transfer 合并小时特征 |

主池:

```text
pair = 0x116e7D070f1888B81E1E0324F56d6746B2D7d8f1
token0 = CHOG
token1 = MON
fee = 10000
event = Swap(address,address,int256,int256,uint160,uint128,int24)
topic0 = 0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67
```

在这个池子里:

```text
amount0 < 0 -> pool 给出 CHOG -> buy_chog
amount0 > 0 -> pool 收到 CHOG -> sell_chog
```

## 当前 20k block 样本

窗口:

```text
swap_window = 2026-05-07T00:18:39Z -> 2026-05-07T02:25:05Z
transfer_window = 2026-05-07T00:15:15Z -> 2026-05-07T02:25:05Z
```

主池 swap:

```text
swap_logs = 51
buy_swaps = 15
sell_swaps = 36
count_imbalance = -0.4118

buy_chog = 2,251,492.448691
sell_chog = 841,030.455117
net_buy_chog = 1,410,461.993574

chog_volume = 3,092,522.903808
mon_volume = 160,451.246521
avg_price_mon_per_chog = 0.05188361
main_pool_liquidity_usd = 126,434.24
```

关键点:

1. 笔数是卖出占优: 15 买 / 36 卖。
2. 金额是买入占优: 净买入约 141 万 CHOG。
3. 这解释了 DexScreener 上“卖出笔数多，但价格上涨”的矛盾。

## 小时级结构

| hour_utc | swaps | buy/sell | net_buy_chog | return_1h | main_pool_sell_pressure |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-05-07T00:00:00Z | 10 | 2/8 | 364,936.48 | 0.09% | -0.00459 |
| 2026-05-07T01:00:00Z | 30 | 8/22 | 1,237,518.78 | 4.21% | -0.01623 |
| 2026-05-07T02:00:00Z | 11 | 5/6 | -191,993.26 | NA | NA |

定义:

```text
main_pool_sell_pressure =
    (sell_chog - buy_chog) * price_usd / main_pool_liquidity_usd
```

所以:

```text
main_pool_sell_pressure < 0 -> 净买入 CHOG
main_pool_sell_pressure > 0 -> 净卖出 CHOG
```

解释:

1. 00:00 和 01:00 UTC 都是卖出笔数更多，但净买入 CHOG。
2. 01:00 UTC 净买入更强，对应小时价格上涨 4.21%。
3. 02:00 UTC 出现净卖出 CHOG，但 DeFiLlama 价格还没有 02:00 小时点，所以暂时无法对齐收益。

## Transfer 与 Swap 的关系

`chog_flow_features_20k_blocks.csv` 中可以看到:

| hour_utc | swap_net_buy_chog | transfer_net_to_pools_chog |
| --- | ---: | ---: |
| 2026-05-07T00:00:00Z | 364,936.48 | -397,172.46 |
| 2026-05-07T01:00:00Z | 1,237,518.78 | -1,292,052.97 |
| 2026-05-07T02:00:00Z | -191,993.26 | 386,680.07 |

这两列方向基本互为镜像:

```text
swap_net_buy_chog > 0
=> CHOG 从池子流出
=> transfer_net_to_pools_chog < 0
```

Transfer 数据可以用于补充多池流，但主池方向应该优先信任 Swap logs。

## 大额交易

按 CHOG 数量排序的 top transactions:

```text
0xd204...0e78f buy_chog 640,924.09 CHOG
0x4f75...579  buy_chog 614,268.54 CHOG
0xce7a...3e74 buy_chog 563,037.23 CHOG
0x36e4...d412 sell_chog 209,591.98 CHOG
0x15ba...2953 sell_chog 136,000.00 CHOG
```

说明当前窗口的净买入主要由少数大额买单贡献，而不是大量小买单贡献。

## 因子含义

之前提出的核心因子现在可以直接从 Swap logs 计算:

```text
MainPoolSellPressure_1h =
    (sell_chog_1h - buy_chog_1h)
    * price_usd_1h
    / main_pool_liquidity_usd
```

预期:

```text
MainPoolSellPressure_1h 越高，未来收益越差。
MainPoolSellPressure_1h 越低，未来收益越好。
```

当前两个可对齐小时:

```text
00:00 sell_pressure = -0.00459, return_1h = 0.09%
01:00 sell_pressure = -0.01623, return_1h = 4.21%
```

样本仍然很短，但方向符合预期。

## 数据面升级方向

主池 Swap logs 后续不应只停留在 buy/sell 汇总，而应升级为 `theta_pool / MainPoolImpact / opportunity decay` 数据面:

| 对象 | 当前来源 | 作用 | 强度 |
| --- | --- | --- | --- |
| `theta_pool` | `sqrtPriceX96`、`tick`、`liquidity`、`amount0/amount1` | 表达主池局部几何 | `G_t` proxy summary |
| `MainPoolImpact` | buy/sell CHOG、价格、`liquidity_usd_t` | 表达单位流动性冲击 | `G_t` impact proxy |
| `opportunity decay` | 冲击后池价、外部价格、未来收益 | 衡量机会或价格偏离消失速度 | `G_t` opportunity proxy |

这里的 `MainPoolImpact` 是主池冲击 proxy，不是资金流真值；也不直接给出 `q_t/r_t/kappa_t/u_t/p_t`，这些对象只能作为 proxy/posterior summary 进入后续框架。

## 下一步

按 [CHOG external 框架吸收计划](../framework/external-absorption-plan.md) 的 V1 顺序推进:

1. 给 `v3_swap_sample` 做 checkpoint/resume。
2. 定时化 DexScreener snapshot，形成 `liquidity_usd_t`。
3. 生成 `proxy-observations.jsonl` 草案 schema。
4. 加 receipt/gas outcome 数据面。
5. 做 sender/recipient 的 router/searcher 标签。
6. 用 walk-forward 验证 MainPoolImpact、volume、conflict proxy。

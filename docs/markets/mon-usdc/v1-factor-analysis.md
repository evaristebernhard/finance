# MON/USDC V1 因子分析

状态: 2026-05-09。重计算逻辑已经迁移到 Rust release binary；Python 入口只负责自动构建/调用 release Rust、读取小型 summary/CSV，并渲染这份 Markdown。本报告只做 gross forward return 单因子研究，不输出交易规则，不做 ML。

复现命令:

```bash
python scripts/mon_usdc_v1_factor_analysis.py --data-root data/mon_usdc/v1 --run-tag 20260509
```

执行路径:

```text
C:/Users/jiang/Desktop/finance_chain_full_handoff_20260508_r2/target/release/mon_usdc_factor_analysis.exe
```

Derived cache: `hit`，schema=`1`，raw_hash=`520497f286b28426`，raw_files=`120109`。

输出:

```text
date/mon_usdc_v1_pool_summary_20260509.csv
date/mon_usdc_v1_hourly_market_features_20260509.csv
date/mon_usdc_v1_hourly_factor_tests_20260509.csv
date/mon_usdc_v1_event_factor_tests_20260509.csv
date/mon_usdc_v1_factor_analysis_summary_20260509.json
docs/markets/mon-usdc/v1-factor-analysis.md
```

## 1. 数据范围和质量

| 指标 | 值 |
| --- | --- |
| raw pool_swap_logs rows | 1,513,009 |
| dedup swap rows | 1,513,009 |
| clean swap rows | 1,513,003 |
| excluded dust/invalid swaps | 6 |
| raw event_block_headers rows | 845,553 |
| raw tx_receipts rows | 1,207,874 |
| unique swap txs / blocks | 1,207,874 / 845,553 |
| clean block window | 60190486..73366454 |
| clean time window | 2026-03-09T01:46:35Z -> 2026-05-09T02:22:34Z |
| calendar span | 61.02 days |
| 1m price rows | 87,877 (80,240 observed, 7,637 ffill) |
| hourly price rows | 1,466 (1,466 observed, 0 ffill) |

质量状态: `passed`。`missing_event_headers=0`，`missing_receipts=0`，`receipt_request_status_errors=0`。链上失败 receipt 行 `0`，保留在 gas/success rate 统计里。

清洗规则只排除 `base_abs<=0`、`quote_abs<=0`、`price_quote_per_base<=0` 或 removed 的 swap。排除明细:

| 原因 | 行数 |
| --- | --- |
| base_abs_nonpositive | 4 |
| quote_abs_nonpositive | 2 |

## 2. 池子结构

| DEX | Family | Pool | Events | Quote Volume | Share | Net Buy MON | Receipt Success |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pancakeswap | pancake_v3 | 0x63e48b...8c53f2 | 748,668 | 226.21M | 60.36% | 20.11M | 100.00% |
| uniswap | v3 | 0x659bd0...d4a9da | 155,318 | 91.68M | 24.46% | 48.61M | 100.00% |
| traderjoe | lb_v22 | 0x5afd3e...e77620 | 422,044 | 48.66M | 12.98% | 11.45M | 100.00% |
| traderjoe | lb_v22 | 0x5e60bc...04fe22 | 186,973 | 8.23M | 2.20% | 1.35M | 100.00% |

解释: Pancake v3、Uniswap v3 和两个 TraderJoe/LFJ v2.2 池都进入统一 `base=MON`、`quote=USDC` 口径。池子 CSV 同时保留 raw/clean 行数，方便检查 dust 排除是否只集中在特定池。

## 3. 小时级链路

小时级 panel 用 clean swap 聚合 VWAP、成交强度、方向流、活跃块、池数量、receipt success rate 和 gas。forward target 使用小时 VWAP forward fill 后的 `fwd_1h/3h/6h/12h/24h`，尾部样本自然减少；`fwd_24h` 最大可检验样本数为 `1,442`。

绝对 Spearman 排名前列的小时级单因子测试:

| Factor | Target | N | Spearman | Top-Bottom | Top >0 |
| --- | --- | --- | --- | --- | --- |
| net_flow_ratio | fwd_1h | 1,465 | 0.4781 | 1.07% | 73.92% |
| buy_event_ratio | fwd_1h | 1,465 | 0.4515 | 0.99% | 71.25% |
| net_flow_ratio | fwd_3h | 1,463 | 0.2489 | 1.10% | 63.58% |
| buy_event_ratio | fwd_3h | 1,463 | 0.2285 | 1.01% | 61.93% |
| net_flow_ratio | fwd_6h | 1,460 | 0.1614 | 0.98% | 60.66% |
| buy_event_ratio | fwd_6h | 1,460 | 0.1430 | 0.81% | 58.47% |
| net_flow_ratio | fwd_12h | 1,454 | 0.0899 | 0.77% | 56.64% |
| events | fwd_12h | 1,454 | -0.0879 | -0.50% | 47.20% |
| events | fwd_24h | 1,442 | -0.0837 | -0.71% | 51.67% |
| quote_volume | fwd_12h | 1,454 | -0.0828 | -0.63% | 46.78% |
| log_quote_volume | fwd_12h | 1,454 | -0.0828 | -0.63% | 46.78% |
| quote_volume | fwd_24h | 1,442 | -0.0788 | -1.03% | 51.59% |

## 4. 事件级链路

事件级 target 使用 1-minute VWAP 序列作为参考价，并测试 `fwd_5m/15m/1h/3h/6h`。因子只来自当前事件字段: 方向、成交规模、gas、同块事件密度。`fwd_6h` 最大可检验事件样本数为 `1,506,757`。

绝对 Spearman 排名前列的事件级单因子测试:

| Factor | Target | N | Spearman | Top-Bottom | Top >0 |
| --- | --- | --- | --- | --- | --- |
| is_buy_base | fwd_5m | 1,512,940 | 0.0974 | 0.08% | 53.50% |
| is_buy_base | fwd_15m | 1,512,825 | 0.0534 | 0.08% | 51.55% |
| is_buy_base | fwd_1h | 1,512,302 | 0.0283 | 0.08% | 50.45% |
| is_buy_base | fwd_3h | 1,509,460 | 0.0166 | 0.08% | 47.24% |
| gas_used | fwd_6h | 1,506,757 | 0.0136 | 0.12% | 48.14% |
| is_buy_base | fwd_6h | 1,506,757 | 0.0108 | 0.06% | 48.16% |
| gas_used | fwd_3h | 1,509,460 | 0.0104 | 0.04% | 47.06% |
| header_event_log_count | fwd_6h | 1,506,757 | -0.0099 | -0.12% | 47.29% |
| effective_gas_gwei | fwd_6h | 1,506,757 | -0.0078 | -0.08% | 48.11% |
| base_abs | fwd_3h | 1,509,460 | 0.0077 | 0.00% | 46.94% |
| log_base_abs | fwd_3h | 1,509,460 | 0.0077 | 0.00% | 46.94% |
| header_event_log_count | fwd_3h | 1,509,460 | -0.0073 | -0.05% | 46.61% |
| same_block_event_count | fwd_6h | 1,506,757 | -0.0063 | -0.12% | 47.47% |
| base_abs | fwd_6h | 1,506,757 | 0.0062 | -0.02% | 47.99% |

## 5. 当前结论

1. 数据链路已经能从 raw swaps、event headers、receipts 直接生成池子汇总、小时级市场 panel 和事件级 forward-return tests。
2. 本轮只做 gross forward return 的单因子切分，尚未接入真实池费、tick liquidity、滑点和执行延迟，因此结果只用于候选现象筛选。
3. 小时级结果更偏 regime/流量解释，事件级结果更适合后续拆解方向、成交规模、gas 和同块拥挤的微观结构现象。
4. 下一步如果继续研究，应先做事件现象拆解和成本模型，而不是直接把这些行解释成可执行交易规则。

## 6. 产物行数

```text
pool_summary=4
hourly_market=1466
hourly_factor_tests=35
event_factor_tests=45
```

# MON/USDC V1 因子分析

状态: 2026-05-10。重计算逻辑已经迁移到 Rust release binary；Python 入口只负责自动构建/调用 release Rust、读取小型 summary/CSV，并渲染这份 Markdown。本报告扩到本地约 86-87 天三件套 raw 覆盖，只做 gross forward return 单因子研究，不输出交易规则，不做 ML。

复现命令:

```bash
python scripts/mon_usdc_v1_factor_analysis.py --data-root data/mon_usdc/v1 --run-tag 20260510_86d --force-derived
```

执行路径:

```text
C:/Users/jiang/Desktop/finance_chain_full_handoff_20260508_r2/target/release/mon_usdc_factor_analysis.exe
```

Derived cache 状态: `forced_rebuilt`，schema=`3`，raw_hash=`76fe477e43111486`，raw_files=`153326`。

输出:

```text
date/mon_usdc_v1_pool_summary_20260510_86d.csv
date/mon_usdc_v1_hourly_market_features_20260510_86d.csv
date/mon_usdc_v1_hourly_factor_tests_20260510_86d.csv
date/mon_usdc_v1_event_factor_tests_20260510_86d.csv
date/mon_usdc_v1_factor_analysis_summary_20260510_86d.json
docs/markets/mon-usdc/v1-factor-analysis.md
```

## 1. 数据范围和质量

| 指标 | 值 |
| --- | --- |
| raw pool_swap_logs rows | 2,147,018 |
| dedup swap rows | 2,147,018 |
| clean swap rows | 2,147,000 |
| excluded dust/invalid swaps | 18 |
| raw event_block_headers rows | 1,229,547 |
| raw tx_receipts rows | 1,701,634 |
| unique swap txs / blocks | 1,701,634 / 1,229,547 |
| clean block window | 54574468..73366454 |
| clean time window | 2026-02-11T00:55:43Z -> 2026-05-09T02:22:34Z |
| calendar span | 87.06 days |
| 1m price rows | 125,368 (115,183 observed, 10,185 ffill) |
| hourly price rows | 2,091 (2,091 observed, 0 ffill) |

质量状态: `passed`。`missing_event_headers=0`，`missing_receipts=0`，`receipt_request_status_errors=0`。链上失败 receipt 行 `0`，保留在 gas/success rate 统计里。

清洗规则只排除 `base_abs<=0`、`quote_abs<=0`、`price_quote_per_base<=0` 或 removed 的 swap。排除明细:

| 原因 | 行数 |
| --- | --- |
| base_abs_nonpositive | 9 |
| quote_abs_nonpositive | 9 |

## 2. 池子结构

| DEX | Family | Pool | Events | Quote Volume | Share | Net Buy MON | Receipt Success |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pancakeswap | pancake_v3 | 0x63e48b...8c53f2 | 1,030,483 | 286.09M | 57.77% | 25.35M | 100.00% |
| uniswap | v3 | 0x659bd0...d4a9da | 220,646 | 129.10M | 26.07% | 48.35M | 100.00% |
| traderjoe | lb_v22 | 0x5afd3e...e77620 | 623,940 | 69.94M | 14.12% | -6.92M | 100.00% |
| traderjoe | lb_v22 | 0x5e60bc...04fe22 | 271,931 | 10.10M | 2.04% | 689.45k | 100.00% |

解释: Pancake v3、Uniswap v3 和两个 TraderJoe/LFJ v2.2 池都进入统一 `base=MON`、`quote=USDC` 口径。池子 CSV 同时保留 raw/clean 行数，方便检查 dust 排除是否只集中在特定池。

## 3. 小时级链路

小时级 panel 用 clean swap 聚合 VWAP、成交强度、方向流、rolling net flow、池/Dex quote share、HHI、活跃块、receipt success rate、priority fee、gas/base fee ratio 和 realized volatility。forward target 使用下一小时 VWAP 作为入场参考，避免同小时 flow 与当前小时 VWAP 共享信息；`fwd_24h` 最大可检验样本数为 `2,066`。

绝对 Spearman 排名前列的小时级单因子测试:

| Factor | Target | N | Spearman | Top-Bottom | Top >0 |
| --- | --- | --- | --- | --- | --- |
| momentum_24h | fwd_24h | 2,042 | -0.1183 | -1.66% | 44.76% |
| net_flow_ratio_24h | fwd_24h | 2,043 | -0.0925 | -1.16% | 49.34% |
| top_dex_quote_share | fwd_24h | 2,066 | -0.0834 | -1.05% | 46.68% |
| top_pool_quote_share | fwd_24h | 2,066 | -0.0834 | -1.05% | 46.68% |
| momentum_24h | fwd_12h | 2,054 | -0.0814 | -0.79% | 46.23% |
| events_per_active_block | fwd_24h | 2,066 | -0.0736 | -0.97% | 50.81% |
| events | fwd_24h | 2,066 | -0.0688 | -0.62% | 50.22% |
| dex_quote_hhi | fwd_24h | 2,066 | -0.0679 | -0.74% | 48.37% |
| pool_quote_hhi | fwd_24h | 2,066 | -0.0626 | -0.72% | 48.37% |
| net_flow_ratio_24h | fwd_12h | 2,055 | -0.0607 | -0.55% | 47.56% |
| active_blocks | fwd_24h | 2,066 | -0.0577 | -0.28% | 51.38% |
| momentum_6h | fwd_3h | 2,081 | -0.0574 | -0.09% | 44.08% |

## 4. 事件级链路

事件级 target 使用 1-minute VWAP 序列作为参考价，并从事件后的下一分钟 VWAP 开始计 forward return，避免事件所在分钟 VWAP 吃到当前事件本身；因子只来自当前事件字段: 方向、成交规模、signed quote flow、gas、priority fee、gas/base fee ratio 和同块事件密度。`fwd_6h` 最大可检验事件样本数为 `2,140,750`。

绝对 Spearman 排名前列的事件级单因子测试:

| Factor | Target | N | Spearman | Top-Bottom | Top >0 |
| --- | --- | --- | --- | --- | --- |
| signed_quote_flow | fwd_5m | 2,146,911 | -0.0195 | -0.01% | 48.32% |
| signed_quote_flow | fwd_15m | 2,146,811 | -0.0169 | -0.02% | 48.30% |
| gas_used | fwd_6h | 2,140,750 | 0.0169 | 0.12% | 48.39% |
| is_buy_base | fwd_5m | 2,146,911 | -0.0159 | -0.01% | 48.60% |
| is_sell_base | fwd_5m | 2,146,911 | 0.0159 | 0.01% | 50.53% |
| gas_to_base_fee_ratio | fwd_6h | 2,140,750 | -0.0135 | -0.11% | 47.75% |
| priority_fee_gwei | fwd_6h | 2,140,750 | -0.0135 | -0.11% | 47.75% |
| effective_gas_gwei | fwd_6h | 2,140,750 | -0.0135 | -0.11% | 47.75% |
| is_buy_base | fwd_15m | 2,146,811 | -0.0129 | -0.01% | 48.60% |
| is_sell_base | fwd_15m | 2,146,811 | 0.0129 | 0.01% | 49.89% |
| gas_used | fwd_3h | 2,143,442 | 0.0125 | 0.05% | 46.90% |
| header_event_log_count | fwd_3h | 2,143,442 | -0.0122 | -0.04% | 45.73% |
| header_event_log_count | fwd_6h | 2,140,750 | -0.0121 | -0.08% | 47.07% |
| signed_quote_flow | fwd_1h | 2,146,270 | -0.0117 | -0.02% | 48.19% |

## 5. 当前结论

1. 数据链路已经能从 raw swaps、event headers、receipts 直接生成池子汇总、小时级市场 panel 和事件级 forward-return tests。
2. 本轮只做 gross forward return 的单因子切分，尚未接入真实池费、tick liquidity、滑点和执行延迟，因此结果只用于候选现象筛选。
3. 小时级结果更偏 regime/流量/池结构解释，事件级结果更适合后续拆解方向、成交规模、gas 和同块拥挤的微观结构现象。
4. 下一步如果继续研究，应先做事件现象拆解和成本模型，而不是直接把这些行解释成可执行交易规则。

## 6. 产物行数

```text
pool_summary=4
hourly_market=2091
hourly_factor_tests=120
event_factor_tests=65
```

# CHOG 可解释因子分解 v2

状态: 2026-05-08。本报告只使用当前本地数据，没有继续采集新链上数据，也没有引入新的 Python 依赖。目标是把弱单因子拆成可解释的 1-6h 因子族，而不是直接产出交易规则。

复现命令:

```bash
python scripts/decompose_chog_factors_v2.py
```

输出文件:

```text
date/chog_factor_panel_v2_20260508.csv
date/chog_factor_decomposition_scores_20260508.csv
date/chog_large_trade_event_study_20260508.csv
date/chog_factor_interaction_tests_20260508.csv
docs/research/chog/2026-05-08-factor-decomposition-v2.md
```

## 1. 数据窗口

| Metric | Value |
| --- | --- |
| event feature rows | 18,795 |
| hourly feature rows | 2,226 |
| price hours | 476 |
| factor panel rows | 476 |
| event hours inside price window | 476 |
| event block window | 66509017..72992679 |
| event time window | 2026-04-07T07:44:45Z -> 2026-05-07T08:56:00Z |
| price time window | 2026-04-17T06:00:00Z -> 2026-05-07T01:00:00Z |

价格序列共有 `476` 小时，其中 observed `299` 小时、forward fill `177` 小时。链上事件从 `2026-04-12` 开始，但可做价格目标检验的窗口从 `2026-04-17T06:00:00Z` 才开始；因此 `2026-04-12` 到价格起点前的链上样本只用于阈值校准和市场结构识别。

## 2. 泄漏控制

- 目标只包含 `fwd_1h`、`fwd_3h`、`fwd_6h`；`return_1h` 只保留为解释力/基准参考。
- 大单阈值、small trade 阈值和主池识别来自 `pre_price_events`，校准事件数 `7,114`，早于第一个价格小时 `2026-04-17T06:00:00Z`。
- 面板中所有因子只使用当前小时及以前可观察信息；未来收益只在评分阶段作为 target。
- regime rank 使用 expanding percentile，当前小时之前/当前小时的历史分布滚动更新，不用未来小时分位。

主池校准结果: `nad-fun` / `0x116e7d...d7d8f1` / quote `MON`。

阈值:

| Bucket | Calibration Quantile | Threshold CHOG |
| --- | --- | --- |
| p01 | 0.99 | 1.00M |
| p05 | 0.95 | 300.64k |
| p10 | 0.9 | 149.67k |
| small | 0.5 | 5.18k |

## 3. 候选因子评分

评分口径: Pearson IC、Spearman IC、top-bottom 三分位差、`P(top return > bottom return)` hit rate，并附加 residual future return IC。Residual target 先由 `return_1h + log_chog_volume + events` 解释，再计算新因子与 residual 的 IC。稳健性列为去除最高成交量日 `2026-05-06` 后的 Spearman。

Top 10 非基准候选:

| Factor | Group | Target | N | Spearman | Resid Spearman | Top-Bottom | Hit Rate | Ex Top Day | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| non_main_net_flow | main_pool_absorption | fwd_3h | 473 | 0.1582 | 0.1819 | 1.90% | 59.40% | 0.2012 | stable |
| main_vs_other_divergence | main_pool_absorption | fwd_3h | 473 | -0.1545 | -0.1597 | -2.02% | 39.01% | -0.1760 | stable |
| large_p10_volume_share | large_trade_impact | fwd_1h | 475 | -0.1467 | 0.0009 | -1.12% | 43.38% | -0.1359 | stable |
| non_main_flow_pressure | main_pool_absorption | fwd_3h | 473 | 0.1414 | 0.1515 | 1.59% | 59.51% | 0.1784 | stable |
| small_net_flow | small_trade_noise | fwd_6h | 470 | 0.1399 | 0.1361 | 2.90% | 59.76% | 0.1377 | stable |
| large_p10_buy_count | impact_path_proxy | fwd_1h | 475 | -0.1321 | -0.0084 | -0.37% | 45.26% | -0.1237 | stable |
| large_p10_buy_flow | impact_path_proxy | fwd_1h | 475 | -0.1255 | 0.0055 | -0.38% | 44.86% | -0.1123 | stable |
| net_buy_chog | standardized_pressure | fwd_3h | 473 | 0.1253 | 0.1463 | 1.85% | 58.41% | 0.1626 | stable |
| main_pool_net_flow | main_pool_absorption | fwd_3h | 473 | 0.1250 | 0.1458 | 1.64% | 57.28% | 0.1620 | stable |
| main_minus_non_main_net_flow | main_pool_absorption | fwd_3h | 473 | 0.1233 | 0.1436 | 1.75% | 57.81% | 0.1597 | stable |

基准参考:

| Factor | Group | Target | N | Spearman | Resid Spearman | Top-Bottom | Hit Rate | Ex Top Day | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| return_1h | baseline_reference | fwd_1h | 474 | -0.0846 | 0.0683 | -0.42% | 43.94% | -0.0780 | stable |
| log_chog_volume | baseline_reference | fwd_1h | 475 | -0.0793 | 0.0688 | -0.45% | 45.01% | -0.0529 | stable |
| events | baseline_reference | fwd_3h | 473 | 0.0640 | 0.0119 | 0.76% | 53.83% | 0.0834 | stable |
| events | baseline_reference | fwd_6h | 470 | 0.0461 | -0.0235 | 0.87% | 51.35% | 0.0409 | stable |
| log_chog_volume | baseline_reference | fwd_3h | 473 | 0.0295 | -0.0046 | 0.12% | 52.05% | 0.0613 | stable |
| events | baseline_reference | fwd_1h | 475 | -0.0275 | 0.0213 | -0.03% | 47.77% | -0.0117 | stable |

Residual IC 排名前列:

| Factor | Group | Target | N | Spearman | Resid Spearman | Top-Bottom | Hit Rate | Ex Top Day | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| non_main_net_flow | main_pool_absorption | fwd_3h | 473 | 0.1582 | 0.1819 | 1.90% | 59.40% | 0.2012 | stable |
| main_vs_other_divergence | main_pool_absorption | fwd_3h | 473 | -0.1545 | -0.1597 | -2.02% | 39.01% | -0.1760 | stable |
| non_main_flow_pressure | main_pool_absorption | fwd_3h | 473 | 0.1414 | 0.1515 | 1.59% | 59.51% | 0.1784 | stable |
| net_buy_chog | standardized_pressure | fwd_3h | 473 | 0.1253 | 0.1463 | 1.85% | 58.41% | 0.1626 | stable |
| main_pool_net_flow | main_pool_absorption | fwd_3h | 473 | 0.1250 | 0.1458 | 1.64% | 57.28% | 0.1620 | stable |
| main_minus_non_main_net_flow | main_pool_absorption | fwd_3h | 473 | 0.1233 | 0.1436 | 1.75% | 57.81% | 0.1597 | stable |
| small_net_flow | small_trade_noise | fwd_6h | 470 | 0.1399 | 0.1361 | 2.90% | 59.76% | 0.1377 | stable |
| large_p05_net_flow | large_trade_impact | fwd_3h | 473 | 0.1078 | 0.1253 | 1.01% | 55.93% | 0.1326 | stable |

## 4. 交互测试

交互只做可解释切片，不做黑盒拟合:

- 大单净买入 x volume regime
- 大单净买入 x gas regime
- 主池净流 x 非主池背离
- 净买入压力 x 前一小时价格涨跌

Top 5 交互切片:

| Interaction | Condition | Target | N | Spearman | Top-Bottom | Hit Rate |
| --- | --- | --- | --- | --- | --- | --- |
| main_pool_flow_x_non_main_divergence | non_main_opposes_main | fwd_6h | 64 | -0.2095 | -4.06% | 36.36% |
| large_net_flow_x_volume_regime | high_volume | fwd_3h | 148 | 0.1586 | 2.87% | 59.57% |
| main_pool_flow_x_non_main_divergence | non_main_opposes_main | fwd_3h | 64 | -0.1551 | -1.56% | 42.42% |
| main_pool_flow_x_non_main_divergence | non_main_same_or_zero | fwd_3h | 409 | 0.1504 | 2.14% | 59.80% |
| net_buy_x_previous_price | prev_price_up | fwd_3h | 151 | -0.1451 | -1.47% | 41.25% |

## 5. 大单冲击后路径

事件研究按小时聚合: 当前小时出现校准大单买/卖后，看未来 1h/3h/6h 平均收益、相对无条件收益的差异，以及买单后上涨/卖单后下跌的 directional follow-through rate。

| Event | Target | Hours | Events | Avg Return | Follow Rate | Excess |
| --- | --- | --- | --- | --- | --- | --- |
| large_buy_p01 | fwd_1h | 26 | 33 | -1.67% | 23.08% | -1.86% |
| large_sell_p01 | fwd_1h | 29 | 30 | -1.42% | 44.83% | -1.60% |
| large_sell_p10 | fwd_6h | 190 | 359 | 0.87% | 45.79% | -0.23% |
| large_sell_p05 | fwd_6h | 130 | 190 | 0.84% | 46.15% | -0.26% |
| large_buy_p05 | fwd_6h | 107 | 184 | 0.79% | 51.40% | -0.31% |
| large_sell_p01 | fwd_3h | 29 | 30 | -0.75% | 58.62% | -1.31% |
| large_buy_p05 | fwd_3h | 108 | 184 | 0.71% | 50.00% | 0.16% |
| large_sell_p01 | fwd_6h | 28 | 30 | -0.68% | 57.14% | -1.78% |
| large_buy_p10 | fwd_6h | 187 | 414 | 0.55% | 51.34% | -0.55% |
| large_sell_p05 | fwd_1h | 132 | 190 | -0.47% | 36.36% | -0.66% |

## 6. 失败或不稳定因子

下面这些因子要么绝对 Spearman 很低，要么去掉最高成交量日后符号/强度不稳。本轮不把它们标为有效，只作为后续数据扩展后的观察对象。

| Factor | Group | Target | N | Spearman | Resid Spearman | Top-Bottom | Hit Rate | Ex Top Day | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| effective_gas_gwei_mean | regime | fwd_3h | 473 | 0.0287 | 0.0024 | 0.40% | 52.09% | 0.0467 | stable |
| priority_fee_gwei_mean | regime | fwd_3h | 473 | 0.0287 | 0.0024 | 0.40% | 52.09% | 0.0467 | stable |
| large_p10_flow_pressure | large_trade_impact | fwd_1h | 475 | -0.0286 | -0.0017 | -0.17% | 44.41% | -0.0357 | stable |
| small_tx_dispersion | small_trade_noise | fwd_1h | 465 | 0.0285 | 0.0031 | 0.59% | 53.28% | 0.0212 | stable |
| net_buy_pressure | standardized_pressure | fwd_3h | 473 | 0.0276 | 0.0416 | 0.31% | 52.79% | 0.0639 | stable |
| net_buy_usd_pressure | standardized_pressure | fwd_3h | 473 | 0.0276 | 0.0416 | 0.31% | 52.79% | 0.0639 | stable |
| large_p10_sell_count | impact_path_proxy | fwd_6h | 470 | -0.0270 | -0.0600 | 0.01% | 48.04% | 0.0019 | stable |
| large_p05_net_flow_z24 | large_trade_impact | fwd_6h | 465 | 0.0263 | 0.0415 | -0.10% | 51.53% | 0.0631 | stable |
| active_blocks | regime | fwd_1h | 475 | -0.0257 | 0.0083 | 0.24% | 50.46% | -0.0104 | stable |
| net_buy_pressure_z72 | standardized_pressure | fwd_3h | 456 | 0.0251 | 0.0425 | 0.15% | 51.73% | 0.0552 | stable |
| net_buy_pressure_z24 | standardized_pressure | fwd_6h | 465 | 0.0246 | 0.0359 | 0.43% | 50.81% | 0.0305 | stable |
| small_tx_dispersion | small_trade_noise | fwd_3h | 463 | -0.0234 | -0.0037 | 0.24% | 49.84% | -0.0538 | stable |

## 7. 当前读法

1. 这一版最有价值的不是单个 IC 数字，而是把流量拆成大单、小单、主池/非主池、gas/volume regime 和标准化压力后，能看到哪些解释力只是成交量/趋势代理。
2. 大单相关变量需要和 regime 一起看；单独的大单净流容易被最高成交日影响。
3. 主池吸收因子比全市场事件数更贴近 CHOG 的真实价格发现，但仍要继续扩展样本确认。
4. 小单噪声类因子可用于过滤环境，不宜直接当方向信号。

## 8. 局限

- 价格样本缺到 `2026-04-12`，导致最早几天链上事件无法进入 fwd-return 评分。
- 476 小时样本仍短，尤其 6h 目标有效样本只有尾部扣除后的小时数。
- `quote_amount` 混有 MON/USDC 等 quote，面板的 USD 标准化主要依赖 CHOG 价格，不等同完整池子美元流动性。
- 本报告没有考虑交易费用、滑点、容量、成交延迟和 out-of-sample。

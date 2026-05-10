# CHOG 成本感知一阶原理事件因子研究

状态: 2026-05-09。输入只使用本地 `derived/memecoin_event_features`，不继续采集链上数据。本报告目标是筛选候选因子族，不生成交易规则。

复现命令:

```bash
python scripts/chog_cost_aware_event_factor_research.py
```

输出:

```text
date/chog_event_cost_labels_20260509.csv
date/chog_first_principles_factor_scores_20260509.csv
date/chog_cost_aware_ml_summary_20260509.csv
docs/research/chog/2026-05-09-cost-aware-event-factors.md
```

## 1. 样本和主池

事件特征共 `18,795` 行，时间从 `2026-04-07T07:44:45Z` 到 `2026-05-07T08:56:00Z`。本轮只把 `nad-fun / CHOG-MON` 主池事件作为可入场信号，非主池事件只进入历史窗口特征。

自动识别主池: `nad-fun` / `0x116e7d...d7d8f1` / quote `MON`，事件 `13,451`，成交量占比 `95.84%`，事件占比 `71.57%`。

有效 label `59,933` 行，其中可交易样本占 `58.81%`。不可交易样本定义为信号名义金额过小、前 15m 主池活跃/成交不足或双边 gas 超过 5%，它们保留在 label 文件里但不进入因子/ML 主评分。

## 2. Label 和成本

- entry: 信号后下一个主池 swap，严格晚于 signal time。
- exit: horizon 前最近一个主池 swap，严格晚于 entry。
- horizons: `5m`, `15m`, `1h`, `3h`, `6h`。
- fee: 主池 `fee=10000`，按 1% one-way，round trip 2%。
- gas: 使用信号前 15m gas 成本中位数估计双边 gas，占信号 quote notional 的比例。
- slippage stress: `0bps`, `50bps`, `100bps`, `200bps` per side。

0 bps slippage 下的 gross vs net:

| Horizon | Tradable/Valid | Gross Mean | Net Mean | Gross >0 | Net >0 | Net >2% |
| --- | --- | --- | --- | --- | --- | --- |
| 5m | 5,070/7,737 | -0.16% | -2.36% | 45.76% | 15.52% | 4.22% |
| 15m | 7,093/11,896 | 0.02% | -2.20% | 45.65% | 18.78% | 8.18% |
| 1h | 7,688/13,402 | 0.21% | -2.02% | 48.23% | 26.13% | 15.19% |
| 3h | 7,699/13,449 | 0.16% | -2.06% | 51.60% | 35.04% | 23.81% |
| 6h | 7,699/13,449 | 1.48% | -0.75% | 53.12% | 41.28% | 31.55% |

100 bps per-side slippage 下:

| Horizon | Tradable/Valid | Gross Mean | Net Mean | Gross >0 | Net >0 | Net >2% |
| --- | --- | --- | --- | --- | --- | --- |
| 5m | 5,070/7,737 | -0.16% | -4.36% | 45.76% | 4.22% | 1.76% |
| 15m | 7,093/11,896 | 0.02% | -4.20% | 45.65% | 8.18% | 4.72% |
| 1h | 7,688/13,402 | 0.21% | -4.02% | 48.23% | 15.19% | 9.61% |
| 3h | 7,699/13,449 | 0.16% | -4.06% | 51.60% | 23.81% | 16.05% |
| 6h | 7,699/13,449 | 1.48% | -2.75% | 53.12% | 31.55% | 24.38% |

## 3. Gross 看起来有效但扣成本失效

下面这些行的有利桶 gross return 为正，但扣 2% fee、gas 和对应滑点后 net return 不再为正。这是本轮最重要的否决结果。

| Factor | Family | Horizon | Slip | Bucket | Gross | Net | Net >0 | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| large_trade_volume_share_15m | liquidity_impact | 6h | 100 | high_decile | 2.95% | -1.26% | 37.92% | gross_only_cost_failed |
| current_large_buy_p90 | liquidity_impact | 6h | 100 | true | 2.94% | -1.06% | 38.03% | gross_only_cost_failed |
| all_event_density_per_min_5m | attention_crowding | 6h | 100 | high_decile | 2.89% | -1.30% | 39.39% | gross_only_cost_failed |
| log_main_quote_volume_15m | liquidity_impact | 6h | 100 | high_decile | 2.49% | -1.74% | 44.94% | gross_only_cost_failed |
| small_trade_count_share_15m | noise_filter | 6h | 100 | high_decile | 2.34% | -1.87% | 28.39% | gross_only_cost_failed |
| current_is_buy | baseline_event_side | 6h | 100 | true | 2.22% | -1.94% | 35.51% | gross_only_cost_failed |
| current_is_sell | baseline_event_side | 6h | 100 | false | 2.22% | -1.94% | 35.51% | gross_only_cost_failed |
| log_main_quote_volume_1h | liquidity_impact | 6h | 100 | high_decile | 2.19% | -2.04% | 36.49% | gross_only_cost_failed |
| log_main_quote_volume_1h | liquidity_impact | 6h | 0 | high_decile | 2.19% | -0.04% | 44.81% | gross_only_cost_failed |
| current_is_large_trade_p90 | liquidity_impact | 6h | 100 | true | 2.16% | -1.84% | 34.25% | gross_only_cost_failed |
| small_count_imbalance_15m | noise_filter | 6h | 100 | high_decile | 2.09% | -2.19% | 33.83% | gross_only_cost_failed |
| small_count_imbalance_15m | noise_filter | 6h | 0 | high_decile | 2.09% | -0.19% | 46.20% | gross_only_cost_failed |

## 4. 能跨过 2% round-trip fee 的事件类型

只看 0 bps slippage，也就是已经扣 2% 主池费和 gas、但未额外施加滑点压力。能留下正 net 的事件类型如下；如果行很少，说明事件形态本身不足以覆盖 taker 成本。

| Factor | Family | Horizon | Slip | Bucket | Gross | Net | Net >0 | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_large_buy_p90 | liquidity_impact | 6h | 0 | true | 2.94% | 0.94% | 46.37% | barely_positive_after_cost |
| current_is_large_trade_p90 | liquidity_impact | 6h | 0 | true | 2.16% | 0.16% | 43.12% | barely_positive_after_cost |

## 5. 更像风控过滤器的因子

这些变量的解释价值主要在“不买/退出/过滤”，而不是方向做多。小单、低活跃和拥挤/gas 环境在扣费后尤其容易吞掉 gross 边际。

| Factor | Family | Horizon | Slip | Bucket | Gross | Net | Net >0 | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_event_density_per_min_15m | attention_crowding | 15m | 0 | high_decile | -0.17% | -2.38% | 24.65% | failed_or_filter_only |
| all_event_density_per_min_5m | attention_crowding | 15m | 0 | high_decile | -0.12% | -2.30% | 22.26% | failed_or_filter_only |
| log_main_quote_volume_15m | liquidity_impact | 15m | 0 | low_decile | -0.12% | -2.28% | 11.27% | failed_or_filter_only |
| log_main_quote_volume_1h | liquidity_impact | 5m | 0 | high_decile | -0.03% | -2.27% | 20.51% | failed_or_filter_only |
| log_main_quote_volume_15m | liquidity_impact | 5m | 0 | low_decile | -0.13% | -2.27% | 10.26% | failed_or_filter_only |
| small_count_imbalance_15m | noise_filter | 15m | 0 | high_decile | -0.00% | -2.25% | 14.49% | failed_or_filter_only |
| all_event_density_per_min_5m | attention_crowding | 5m | 0 | low_decile | -0.07% | -2.25% | 15.23% | failed_or_filter_only |
| main_event_density_per_min_15m | attention_crowding | 5m | 0 | low_decile | -0.00% | -2.22% | 14.24% | failed_or_filter_only |
| non_main_volume_share_15m | main_pool_absorption | 15m | 0 | high_decile | 0.01% | -2.21% | 16.06% | gross_only_cost_failed |
| all_event_density_per_min_15m | attention_crowding | 5m | 0 | low_decile | -0.02% | -2.21% | 14.46% | failed_or_filter_only |
| current_is_sell | baseline_event_side | 5m | 0 | false | -0.04% | -2.19% | 17.61% | failed_or_filter_only |
| main_event_density_per_min_15m | attention_crowding | 3h | 0 | low_decile | 0.07% | -2.19% | 29.11% | gross_only_cost_failed |

## 6. Walk-forward ML 筛选

ML 只用于候选因子筛选。每个 fold 只用训练段做特征选择、winsorize、median fill、标准化和 top-decile 预测阈值；测试段只按训练阈值判定 top bucket。模型覆盖 Ridge/ElasticNet/Logistic 基准，RandomForest 作为非线性提示；若本机已安装 LightGBM/XGBoost，则只在 100 bps、1h/3h/6h regression 上做轻量提示。

Top OOS rows:

| Horizon | Slip | Model | Target | N | Top N | Top Mean | Lift | Hit | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6h | 0 | logistic | >0% | 6415 | 245 | 5.52% | 6.61% | 76.33% | possible_candidate |
| 6h | 0 | logistic | >2% | 6415 | 282 | 4.29% | 5.38% | 70.92% | possible_candidate |
| 6h | 0 | random_forest | regression | 6415 | 454 | 4.15% | 5.24% | 79.96% | possible_candidate |
| 6h | 100 | random_forest_classifier | >0% | 6415 | 259 | 4.02% | 7.11% | 65.64% | possible_candidate |
| 6h | 100 | xgboost | regression | 6415 | 296 | 3.63% | 6.72% | 60.14% | possible_candidate |
| 6h | 0 | elastic_net | regression | 6415 | 240 | 3.60% | 4.70% | 60.83% | possible_candidate |
| 6h | 100 | lightgbm | regression | 6415 | 347 | 2.97% | 6.06% | 65.13% | possible_candidate |
| 6h | 100 | logistic | >0% | 6415 | 282 | 2.29% | 5.38% | 57.09% | possible_candidate |
| 6h | 100 | random_forest | regression | 6415 | 454 | 2.15% | 5.24% | 61.23% | possible_candidate |
| 3h | 0 | random_forest | regression | 6415 | 165 | 2.10% | 4.04% | 62.42% | possible_candidate |
| 6h | 0 | ridge | regression | 6415 | 261 | 1.86% | 2.95% | 60.15% | possible_candidate |
| 6h | 100 | elastic_net | regression | 6415 | 240 | 1.60% | 4.70% | 53.33% | barely_positive |

失败/负向 OOS rows:

| Horizon | Slip | Model | Target | N | Top N | Top Mean | Lift | Hit | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5m | 200 | logistic | >5% | 1690 | 102 | -6.64% | 0.21% | 0.00% | failed_after_cost |
| 15m | 200 | logistic | >5% | 5910 | 477 | -6.33% | -0.05% | 1.47% | failed_after_cost |
| 5m | 200 | logistic | >0% | 4225 | 388 | -6.14% | 0.30% | 0.77% | failed_after_cost |
| 5m | 200 | logistic | >2% | 4225 | 515 | -6.06% | 0.38% | 2.14% | failed_after_cost |
| 1h | 200 | logistic | >5% | 6405 | 461 | -5.77% | 0.45% | 8.68% | failed_after_cost |
| 15m | 200 | logistic | >0% | 5910 | 359 | -5.74% | 0.54% | 5.01% | failed_after_cost |
| 5m | 200 | elastic_net | regression | 4225 | 308 | -5.72% | 0.71% | 0.97% | failed_after_cost |
| 5m | 200 | ridge | regression | 4225 | 276 | -5.68% | 0.76% | 0.36% | failed_after_cost |
| 15m | 200 | logistic | >2% | 5910 | 545 | -5.68% | 0.61% | 5.87% | failed_after_cost |
| 1h | 200 | logistic | >2% | 6405 | 384 | -5.27% | 0.95% | 8.85% | failed_after_cost |

## 7. 不可交易或失败的因子族

按 0 bps slippage 聚合，`cost_failed` 表示 gross 有正边际但扣费后失效的测试数。

| Family | Tests | Cost Failed | Mean Net | Best Net | Candidates |
| --- | --- | --- | --- | --- | --- |
| main_pool_absorption | 30 | 21 | -1.86% | -0.43% | 0 |
| baseline_event_side | 10 | 6 | -1.48% | 0.06% | 0 |
| noise_filter | 10 | 8 | -1.40% | 0.13% | 0 |
| attention_crowding | 30 | 23 | -1.48% | 0.70% | 0 |
| liquidity_impact | 45 | 36 | -1.19% | 2.92% | 1 |

## 8. 当前结论

1. 小时级 IC 的乐观读法被成本明显压缩；事件级 label 显示，2% round-trip fee 是主约束，额外 100 bps per-side slippage 会继续降低 positive rate。
2. gross 有效但 net 失效的因子需要直接淘汰，尤其是只靠短 horizon 微小反弹的事件形态。
3. 更适合继续扩数据验证的候选因子族: `liquidity_impact`。
4. 小单噪声、低活跃窗口、拥挤/gas regime 更适合作为风控过滤器；负方向信号只解释为不买/退出，不假设可做空。
5. 由于没有可靠逐事件流动性曲线，本轮没有伪造 AMM impact，只输出滑点 stress。下一步应继续扩主池事件样本，并把真实池流动性曲线接入后重跑。

# CHOG 监督学习因子研究

状态: 2026-05-09。基于 30 天 memecoin 数据重建后的 `date/chog_factor_panel_v2_20260508.csv`，用监督学习补充因子分析。

这份报告只用于研究候选因子稳定性，不是交易规则。样本仍只有 `476` 个小时，且价格序列从 2026-04-17 才开始，所以早期链上数据主要影响校准和市场结构。

复现命令:

```bash
python scripts/ml_chog_supervised_factor_models.py
```

输出:

```text
date/chog_ml_supervised_oos_predictions_20260508.csv
date/chog_ml_supervised_feature_importance_20260508.csv
date/chog_ml_supervised_model_summary_20260508.csv
docs/research/chog/2026-05-08-supervised-factor-research.md
```

## 1. 方法

- 输入特征: 清洗后的 `86` 个数值因子。
- 目标: `fwd_1h`、`fwd_3h`、`fwd_6h`。
- 切分: expanding `TimeSeriesSplit`，每个 fold 只用训练段选择 top `30` 个 Spearman 因子。
- 模型: Ridge、ElasticNet、RandomForest、LightGBM、XGBoost。
- 评分: OOS Spearman、Pearson、预测值三分位 top-bottom future return。

生成 OOS 预测点数量: `5,875`。

## 2. OOS 模型结果

| Target | Model | N | Spearman | Pearson | Top-Bottom |
| --- | --- | --- | --- | --- | --- |
| fwd_1h | lightgbm | 395 | -0.0916 | -0.1078 | -0.85% |
| fwd_6h | random_forest | 390 | -0.0784 | -0.0986 | -1.84% |
| fwd_3h | elastic_net | 390 | 0.0716 | 0.0761 | 0.77% |
| fwd_3h | ridge | 390 | 0.0654 | 0.0595 | 0.65% |
| fwd_1h | elastic_net | 395 | -0.0604 | -0.0324 | -0.22% |
| fwd_6h | elastic_net | 390 | -0.0545 | -0.0153 | -1.82% |
| fwd_6h | lightgbm | 390 | -0.0496 | -0.0771 | -0.86% |
| fwd_3h | random_forest | 390 | 0.0453 | 0.0619 | 0.34% |
| fwd_1h | random_forest | 395 | -0.0421 | -0.0410 | -0.13% |
| fwd_1h | xgboost | 395 | -0.0353 | -0.0561 | -0.37% |
| fwd_1h | ridge | 395 | -0.0345 | -0.0169 | 0.25% |
| fwd_6h | ridge | 390 | -0.0214 | -0.0193 | -0.32% |

## 3. 跨模型稳定因子

下面按 fold 内特征重要性做归一化，再统计跨模型/target 的稳定分数。它不等于可交易 alpha，但能提示哪些原始变量值得手工重构。

| Feature | Model-Targets | Mean Score | Max Score |
| --- | --- | --- | --- |
| main_pool_flow_pressure_z24 | 10 | 0.2389 | 0.8892 |
| main_vs_other_divergence | 15 | 0.3542 | 0.7874 |
| non_main_net_flow | 15 | 0.2685 | 0.6932 |
| avg_price_quote_per_chog | 5 | 0.4109 | 0.6916 |
| large_p05_flow_pressure_z24 | 15 | 0.2430 | 0.5643 |
| small_volume | 10 | 0.1966 | 0.4376 |
| large_p10_flow_pressure | 10 | 0.1499 | 0.4271 |
| net_buy_chog | 15 | 0.1550 | 0.4036 |
| large_p10_count_share | 15 | 0.1076 | 0.3978 |
| net_buy_chog_z72 | 15 | 0.1212 | 0.3619 |
| small_net_flow | 10 | 0.1310 | 0.3574 |
| large_p10_volume_share | 15 | 0.1590 | 0.3571 |
| large_p05_flow_pressure | 15 | 0.1164 | 0.3479 |
| large_p05_net_flow_z72 | 15 | 0.2076 | 0.3458 |
| net_buy_chog_z24 | 15 | 0.1451 | 0.3345 |
| small_trade_mean | 10 | 0.1135 | 0.3119 |
| large_p01_volume | 10 | 0.0646 | 0.3114 |
| large_p05_net_flow_x_high_gas | 15 | 0.1439 | 0.3004 |

## 4. 分目标重要因子

### fwd_1h

| Feature | Models | Mean Score | Max Score |
| --- | --- | --- | --- |
| main_vs_other_divergence | 5 | 0.2879 | 0.5493 |
| non_main_net_flow | 5 | 0.2714 | 0.4184 |
| large_p10_count_share | 5 | 0.2428 | 0.3978 |
| net_buy_chog_z72 | 5 | 0.1618 | 0.3619 |
| small_trade_mean | 5 | 0.1748 | 0.3119 |
| large_p01_volume | 5 | 0.1188 | 0.3114 |
| gas_used_mean | 5 | 0.2173 | 0.2983 |
| large_p05_flow_pressure_z24 | 5 | 0.1870 | 0.2941 |
### fwd_3h

| Feature | Models | Mean Score | Max Score |
| --- | --- | --- | --- |
| main_pool_flow_pressure_z24 | 5 | 0.3604 | 0.8892 |
| main_vs_other_divergence | 5 | 0.4518 | 0.7874 |
| non_main_net_flow | 5 | 0.3424 | 0.6932 |
| large_p05_flow_pressure_z24 | 5 | 0.2779 | 0.5643 |
| large_p10_flow_pressure | 5 | 0.2710 | 0.4271 |
| net_buy_chog | 5 | 0.2695 | 0.4036 |
| large_p05_flow_pressure | 5 | 0.1842 | 0.3479 |
| net_buy_chog_z24 | 5 | 0.2217 | 0.3345 |
### fwd_6h

| Feature | Models | Mean Score | Max Score |
| --- | --- | --- | --- |
| avg_price_quote_per_chog | 5 | 0.4109 | 0.6916 |
| large_p05_flow_pressure_z24 | 5 | 0.2641 | 0.5361 |
| main_vs_other_divergence | 5 | 0.3230 | 0.4377 |
| small_volume | 5 | 0.2675 | 0.4376 |
| small_net_flow | 5 | 0.1853 | 0.3574 |
| large_p10_volume_share | 5 | 0.2295 | 0.3571 |
| large_p05_net_flow_z72 | 5 | 0.2855 | 0.3458 |
| non_main_net_flow | 5 | 0.1918 | 0.3158 |


## 5. 当前读法

1. 监督学习没有给出强 OOS alpha；最高 Spearman 仍是弱信号级别，应继续当研究线索。
2. 能跨模型出现的变量比单次 IC 排名更值得看，尤其是和大单占比、主池压力、短期动量/反转有关的变量。
3. Ridge/ElasticNet 适合看线性方向，树模型适合发现非线性切片；两者共同出现的特征优先进入下一版手写因子。
4. 后续应该把 top 特征重构成少数稳定因子，再用按日期切开的 train/validation 做确认。

# CHOG 机器学习因子分析

状态: 2026-05-09。基于 `date/chog_factor_panel_v2_20260508.csv` 做第一版机器学习/因子分解研究，新增依赖见 `requirements-ml.txt`。

这份报告仍是研究稿，不是交易规则。样本只有 `476` 个小时，时间跨度短，所有结论都应等继续补齐 30 天以上数据后复测。

复现命令:

```bash
python scripts/ml_chog_factor_analysis.py
```

输出:

```text
date/chog_ml_factor_loadings_20260508.csv
date/chog_ml_factor_scores_20260508.csv
date/chog_ml_factor_model_tests_20260508.csv
docs/research/chog/2026-05-08-ml-factor-analysis.md
```

## 1. 输入和清洗

原始面板行数 `476`，数值列经缺失率、常数列、极端相关过滤后保留 `86` 个候选因子；高相关剔除 `15` 个。每列做 1%/99% winsorize、median fill、z-score。

目标收益:

| Target | Valid Rows | Mean | Std |
| --- | --- | --- | --- |
| fwd_1h | 475 | 0.19% | 3.66% |
| fwd_3h | 473 | 0.55% | 6.00% |
| fwd_6h | 470 | 1.10% | 8.09% |

## 2. EFA 适配度

KMO overall: `0.8442`。

Bartlett p-value: `0.0000`。

相关矩阵前 8 个特征值:

| Rank | Eigenvalue |
| --- | --- |
| 1 | 25.1854 |
| 2 | 18.9217 |
| 3 | 6.3329 |
| 4 | 4.3216 |
| 5 | 3.7997 |
| 6 | 2.9833 |
| 7 | 2.3939 |
| 8 | 2.3445 |

本轮按 Kaiser rule 并上限裁剪，提取 `6` 个 varimax 旋转因子。KMO 若偏低，说明这些链上因子不是典型心理量表式 latent factor，更适合当“流量/波动/拥堵/池子结构”几个可解释簇来用。

## 3. EFA 因子载荷

| Factor | Top Loadings |
| --- | --- |
| efa_factor_1 | large_p10_volume (0.96), chog_volume (0.94), large_p05_count (0.93), large_p05_volume (0.92), large_p10_count (0.91), quote_volume (0.90) |
| efa_factor_2 | large_p05_net_flow (0.95), large_p10_net_flow (0.95), large_p05_net_flow_z72 (0.92), large_p05_net_flow_x_high_volume (0.91), net_buy_chog (0.91), net_buy_usd_at_price (0.89) |
| efa_factor_3 | main_pool_flow_pressure (-0.94), main_pool_flow_pressure_z72 (-0.94), net_buy_pressure_z72 (-0.94), net_buy_pressure (-0.94), main_pool_flow_pressure_z24 (-0.93), net_buy_pressure_z24 (-0.93) |
| efa_factor_4 | large_p01_volume_share (0.76), large_p01_count (0.75), large_p01_volume (0.72), large_p01_count_share (0.69), large_p01_sell_count (0.66), large_p01_sell_flow (0.65) |
| efa_factor_5 | small_sell_count (-0.77), events (-0.75), sell_events (-0.71), small_buy_count (-0.71), buy_events (-0.68), active_block_regime_rank (-0.64) |
| efa_factor_6 | large_p01_net_flow (0.70), large_p01_flow_pressure (0.65), large_p01_count_imbalance (0.65), large_p01_buy_flow (0.52), large_p01_buy_count (0.47), large_p01_sell_flow (-0.38) |

读法:

1. 同一 factor 里绝对载荷高的变量可以看作一个市场状态簇。
2. 正负号本身不重要，重要的是同簇变量方向是否稳定；换样本后 factor 符号可能整体翻转。
3. 高 communality 的变量更适合被低维因子解释，低 communality 的变量更适合作为单独特征保留。

## 4. PCA 参考

| Component | Explained | Cumulative |
| --- | --- | --- |
| pca_1 | 29.29% | 29.29% |
| pca_2 | 22.00% | 51.29% |
| pca_3 | 7.36% | 58.65% |
| pca_4 | 5.03% | 63.68% |
| pca_5 | 4.42% | 68.09% |
| pca_6 | 3.47% | 71.56% |

PCA 解释方差主要说明“链上变量之间有多少冗余”，不直接代表预测力。若前几个 PCA 已解释大部分方差，后续建模可以先压缩再做稳健性测试。

## 5. IC / 机器学习检验

评分包含两类:

1. `unsupervised_score_ic`: 直接看 EFA/PCA score 与未来收益的相关和三分位差。
2. `time_series_oos_prediction`: 用 expanding time split 做 out-of-sample 预测，模型包括 Ridge、RandomForest、LightGBM。

当前绝对 Spearman 排名前列:

| Type | Model | Features | Target | N | Spearman | Top-Bottom |
| --- | --- | --- | --- | --- | --- | --- |
| unsupervised_score_ic | efa | efa_factor_1 | fwd_1h | 475 | -0.1203 | -0.48% |
| unsupervised_score_ic | efa | efa_factor_2 | fwd_3h | 473 | 0.1199 | 1.59% |
| unsupervised_score_ic | efa | efa_factor_5 | fwd_3h | 473 | -0.1087 | -1.66% |
| time_series_oos_prediction | random_forest | raw_standardized_factors | fwd_6h | 390 | -0.1049 | -2.11% |
| unsupervised_score_ic | pca | pca_4 | fwd_3h | 473 | -0.1007 | -1.24% |
| unsupervised_score_ic | pca | pca_6 | fwd_6h | 470 | 0.0984 | 1.56% |
| unsupervised_score_ic | efa | efa_factor_5 | fwd_6h | 470 | -0.0977 | -2.29% |
| unsupervised_score_ic | pca | pca_7 | fwd_1h | 475 | -0.0923 | -0.57% |
| unsupervised_score_ic | pca | pca_4 | fwd_6h | 470 | -0.0914 | -1.97% |
| unsupervised_score_ic | pca | pca_1 | fwd_1h | 475 | -0.0891 | -0.69% |
| unsupervised_score_ic | pca | pca_7 | fwd_3h | 473 | -0.0856 | -0.81% |
| unsupervised_score_ic | pca | pca_2 | fwd_3h | 473 | 0.0843 | 1.11% |

## 6. 当前结论

1. 这组链上变量确实有明显共线性，低维压缩是必要的；否则很多“新因子”只是成交量、活跃度和大单流量的重复表达。
2. EFA/PCA 更适合先做因子族归纳，再回到可解释变量设计，而不是直接把 factor score 当交易信号。
3. out-of-sample ML 检验如果强度明显低于 full-sample IC，说明当前样本容易被少数高成交小时支配。
4. 下一步最好继续补历史窗口，然后把训练/验证按日期切开，确认大单、主池、gas regime 是否跨窗口稳定。

## 7. 后续研究建议

1. 把 `efa_factor_*` 分数并回 hourly panel，作为 regime/filter 候选。
2. 对 top loading 变量做人工重构，形成更少、更稳的手写因子，比如 `activity_regime`、`large_flow_pressure`、`main_pool_absorption`。
3. 至少补到 30 天以上后再重跑本脚本，并比较 factor loading 是否换组。
4. LightGBM/RandomForest 只看特征重要性和非线性提示，不要在当前短样本上直接调参追高 IC。

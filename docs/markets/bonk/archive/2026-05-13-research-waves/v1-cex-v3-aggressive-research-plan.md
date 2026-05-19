# BONK CEX V3 激进研究计划草案

状态: 2026-05-13。本文基于当前 `20260513_bullish_l2_basket_price_v1` 产物，定义一版更激进但不自欺的 BONK CEX L2 研究计划。本文只用于候选现象排序、数据需求设计和下一轮验证，不输出交易规则，也不声称 alpha。

## 立场

V1/V2 的保守结论仍然有效:

```text
BONK Bullish L2 里有可见状态信息。
两周窗口太短，且 BONK 当期相对市场较强。
部分 L2/activity/spread 现象被 market regime、label overlap、placebo shift 和 forward split 不稳污染。
context+L2 non-overlap 稳定胜出只有 3/8，不能声称稳定可交易 alpha。
```

V3 的变化不是放松诚实标准，而是放宽研究对象:

```text
允许短半衰期因子。
允许 recent/regime-local edge 作为研究对象。
允许 path-width / movement-state 本身成为价值。
允许用 reasoned candidate score 排序候选，而不是要求第一天就全样本稳定。
```

V3 的红线也更明确:

```text
不输出入场、出场、仓位、挂单、止损、止盈规则。
不把候选分数解释成胜率、收益率或 alpha。
不把回测内局部 edge 解释成未来可交易边。
不把同时提高 upper 与 lower first-passage 的状态解释成方向性。
```

## 当前依据

当前引用产物:

```text
docs/markets/bonk/v1-cex-regime-plan.md
docs/markets/bonk/v1-cex-l2-report.md
docs/markets/bonk/v1-cex-l2-analysis.md
docs/markets/bonk/v1-cex-modeling-report.md

data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_covariance_state/bonk_cex_covariance_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_path_labels/bonk_path_labels_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet

date/bonk_v1_cex_l2_quality_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_cex_l2_summary_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_cex_l2_factor_tests_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_cex_l2_stability_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_cex_price_context_summary_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_controlled_factor_tests_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_model_metrics_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_model_stability_20260513_bullish_l2_basket_price_v1.csv
```

当前事实底座:

```text
L2 window: 2026-04-29..2026-05-12
path-labeled symbols: BONK1MUSDC, BONK1MUSDT
BONK1MUSDC state rows: 20,103
BONK1MUSDT state rows: 20,127
BONK1MUSDC median spread: 2.74 bps
BONK1MUSDT median spread: 1.59 bps
BONK1MUSDC trades: 388,533
BONK1MUSDT trades: 45,839
Binance spot kline context symbols: 13
context missing minutes: 0
```

当前研究读法:

```text
BONK1MUSDC 的 1h activity/count 变量更突出。
BONK1MUSDT 的 4h/12h spread 变量更突出。
activity 更像 attention/participation state。
spread 更像 liquidity/volatility regime。
controlled_factor_tests 已显式标记 path_width_not_direction、market_wide_move_likely、regime_persistence_confounded。
modeling report 显示 context+L2 还没有跨 fold 稳定压过 context-only。
```

## V3 目标

V3 不问“有没有可以立刻交易的规则”，而问四个更早期的问题:

```text
1. 哪些状态值得继续收集更长窗口？
2. 哪些状态只在 recent/regime-local 条件下有解释力？
3. 哪些状态不是方向因子，但能解释未来 path-width？
4. 哪些候选即使不稳定，也足够有结构感，值得下一轮预注册验证？
```

V3 输出应是 candidate registry，而不是 strategy registry。

## Candidate 定义

一个 V3 candidate 至少包含:

```text
candidate_id
run_tag
symbol
factor_family
factor_name
factor_transform
bucket_or_score_rule
horizon
barrier
regime_gate
half_life_assumption
label_target
evidence_summary
failure_modes
next_validation_window
status
```

`status` 只允许:

```text
research_candidate
path_width_candidate
regime_utility_candidate
discard_or_wait
```

不允许出现:

```text
tradable_alpha
production_signal
entry_rule
execution_rule
```

## Reasoned Candidate Score

V3 可以引入 `reasoned_candidate_score`，用于决定先研究谁。它不是模型预测概率，也不是收益预期。

建议分数拆成 100 分:

| component | max | 含义 |
| --- | ---: | --- |
| effect_shape | 20 | edge/residual/median future return 是否方向一致，是否不是单个离群点撑起 |
| local_regime_fit | 15 | 是否能被明确 regime gate 解释，而不是事后挑日期 |
| half_life_plausibility | 10 | 因子半衰期是否与盘口机制匹配 |
| path_width_value | 15 | 是否能解释未来 MFE/MAE 宽度、upper/lower first-passage 强度或波动状态 |
| controlled_residual | 15 | 控制 market/meme/SOL/BONK RV 后是否仍有残余信息 |
| stability_floor | 10 | non-overlap、forward split、placebo shift 是否至少没有完全反向 |
| parsimony | 5 | 因子是否简单、可复述、可复现 |
| data_quality | 5 | 是否覆盖足够、无明显空文件/异常 spread/side 语义缺口 |
| falsifiability | 5 | 是否能定义下一轮具体失败条件 |

扣分项:

```text
-20: market_wide_move_likely 且没有 residual 支撑
-20: placebo_shift 后仍强，且解释只是 minute-level 因果
-20: forward_split 一边强一边反向，且没有 regime gate
-15: upper 与 lower 同时上升，却被写成方向因子
-15: bucket_rows 太小，无法支持候选排序
-10: 候选依赖 Bullish trade side 语义，但 side 语义仍未确认
```

解释等级:

| score | interpretation |
| ---: | --- |
| 75..100 | priority research candidate, 需要下一窗口预注册验证 |
| 55..74 | useful diagnostic candidate, 先做 regime/path-width 拆解 |
| 35..54 | weak candidate, 等更多数据或换 label |
| 0..34 | discard_or_wait |

## 短半衰期因子

V3 允许短半衰期，但必须把“短”写进假设。不能用 1h/4h/12h 的 label 结果，倒推一个没定义的高频交易规则。

短半衰期候选优先来自:

```text
snapshot_count
book_ticker_count
trade_count
trade_notional_quote_sum
wobi25_mean
depth_imbalance_25_mean
microprice_offset_bps_mean
cross_venue_activity_ratio
cross_venue_spread_diff_bps
```

建议半衰期 buckets:

```text
5m, 15m, 30m, 60m, 240m
```

验证方法:

```text
1. 对候选因子做 lag sweep: 0m, 5m, 15m, 30m, 60m。
2. 估计 edge 或 residual IC 随 lag 衰减的形状。
3. 如果 0m 强、60m 消失，可以保留为短半衰期候选。
4. 如果 60m placebo 仍强，应降级为 regime persistence，而不是 minute-level 因果。
5. 如果半衰期短于可执行/可复现的数据频率，只能保留为 microstructure phenomenon。
```

## Recent / Regime-Local Edge

V3 允许 recent/regime-local edge，但它必须是显式条件，不是事后挑最好日期。

允许的 regime gates:

```text
ctx_market_ret_60m_bps
ctx_meme_ret_60m_bps
ctx_sol_ret_60m_bps
ctx_bonk_rel_meme_bps
ctx_bonk_rv_1h_bps
bullish_common_mode_score
symbol-specific spread/liquidity bucket
cross-venue activity/spread bucket
```

局部 edge 的合格写法:

```text
在 BONK 相对 meme 强、且 BONK RV 高、且 Bullish common mode 不过强的状态下，
某 activity candidate 对 1h/50bps path-width 或 residual upper label 有研究价值。
```

不合格写法:

```text
最近两天这个因子赚钱，所以它是 alpha。
```

recent candidate 的验证顺序:

```text
1. 先声明 regime gate。
2. 再在当前窗口内计算局部证据。
3. 给出 failure mode。
4. 在下一批日期上只验证已声明 gate，不重新挑 gate。
```

## Path-Width 作为价值

V3 明确承认 path-width 也是价值。一个状态如果能识别“未来更会动”，即使方向不稳，也值得进入候选库。

path-width candidate 关注:

```text
upper_first_rate 与 lower_first_rate 是否同时抬升
median_mfe_up_bps 与 median_mae_down_bps 是否同时变宽
fixed barrier 下 first-passage rate 是否升高
volatility-adjusted barrier 下是否仍有区分度
```

path-width 的价值定义:

```text
它可以帮助理解何时市场进入高运动宽度状态。
它可以帮助筛选后续方向因子的适用窗口。
它可以帮助解释 spread/activity 为什么看起来有 edge。
它不能单独变成买入或卖出规则。
```

`date/bonk_v1_controlled_factor_tests_20260513_bullish_l2_basket_price_v1.csv` 中的 `path_width_not_direction` 应被视为正确信号标签，而不是失败标签。失败只发生在把它误读成方向 alpha 时。

## 候选研究线

### A. Activity / Attention

核心字段:

```text
snapshot_count
book_ticker_count
trade_count
trade_notional_quote_sum
```

当前动机:

```text
BONK1MUSDC 1h activity/count high bucket 在当前报告中最突出。
BONK1MUSDT 也有 quote activity，但弱于 USDC。
activity 可能表示 attention、参与度、数据更新强度或局部活跃 regime。
```

V3 处理:

```text
先按 short half-life candidate 处理。
重点看 5m/15m/30m/60m decay。
若 upper/lower 都抬升，归为 path_width_candidate。
若控制 market/meme/SOL 后 residual 仍稳定，再保留 direction candidate 资格。
```

### B. Spread / Liquidity Stress

核心字段:

```text
spread_bps_median
spread_bps_last
```

当前动机:

```text
BONK1MUSDT 4h/12h spread diagnostics 最清楚。
BONK1MUSDC 12h spread 也有可见结果。
该类更像 volatility/liquidity state，而不是方向因子。
```

V3 处理:

```text
默认进入 path_width_candidate。
必须对 BONK RV、market/meme/SOL momentum、Bullish common mode 做控制。
如果只在高 RV 下有效，应写成 high-vol liquidity regime，而不是 spread alpha。
```

### C. Cross-Venue State

核心字段:

```text
cross_venue_spread_diff_bps
cross_venue_activity_ratio
```

当前动机:

```text
BONK1MUSDC 与 BONK1MUSDT 是同一资产的不同流动性切面。
USDT top-of-book spread 更窄，USDC 成交更活跃。
两者差异可能包含 venue-local congestion、attention 或 liquidity routing 信息。
```

V3 处理:

```text
优先做 regime_utility_candidate。
若 cross-venue 状态能解释 path-width，先记录为市场状态变量。
除非能证明一边领先另一边，且通过 lag/placebo 检查，否则不写成 directional lead-lag。
```

### D. Context-Residual State

核心字段:

```text
ctx_market_ret_60m_bps
ctx_meme_ret_60m_bps
ctx_sol_ret_60m_bps
ctx_bonk_rel_meme_bps
ctx_bonk_rv_1h_bps
bullish_common_mode_score
```

当前动机:

```text
BONK 当前窗口相对 BTC/ETH/SOL、meme basket、SOL 都偏强。
这使 L2 continuation 更有研究意义，也提高 regime artifact 风险。
```

V3 处理:

```text
所有方向候选必须先通过 context-residual 解读。
市场状态本身可以作为 regime gate。
如果 L2 候选只是在强市场里跟随 market-wide move，则降级为 market_wide_move_likely。
```

### E. Model-Diagnostic Candidates

核心产物:

```text
date/bonk_v1_model_metrics_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_model_stability_20260513_bullish_l2_basket_price_v1.csv
```

当前动机:

```text
context+L2 在 Fold 2/3 non-overlap 上稳定胜出只有 3/8。
局部 top-decile lift 有亮点，但不足以声明 alpha。
```

V3 处理:

```text
把 model score 当作 candidate ranker，不当作交易预测器。
候选必须解释 feature family、regime gate 和失败模式。
如果模型只在某一 fold 强，保留为 recent/regime-local candidate，等待下一窗口验证。
```

## 验证阶梯

V3 采用五级验证:

| level | 名称 | 通过标准 | 输出 |
| --- | --- | --- | --- |
| L0 | data sanity | 覆盖、异常、单位、side 语义记录清楚 | usable dataset |
| L1 | phenomenon | 全样本或分桶里有可复现形状 | research_candidate |
| L2 | controlled phenomenon | 控制 market/meme/SOL/RV 后仍有残余或明确降级为 regime | scored_candidate |
| L3 | local validation | 预声明 regime gate 后在下一日期窗口仍有方向一致或 path-width 一致 | validation_candidate |
| L4 | execution research gate | 仍不输出规则，只允许进入独立执行成本/可成交性研究 | execution_research_candidate |

任何 candidate 都可以在任一级被降级为:

```text
path_width_candidate
regime_utility_candidate
discard_or_wait
```

## 停止条件

以下情况直接停止方向解释:

```text
1. upper 与 lower first-passage 同时上升，且 upper_edge_minus_lower_edge 不稳定。
2. placebo_shift 后效果不减，且没有 regime persistence 解释。
3. forward_split 一半为正、一半为负，且没有预声明 regime gate。
4. controlled_residual 与 raw edge 方向冲突。
5. candidate 只依赖一个日期、一个 symbol 或一个极小 bucket。
6. Bullish trade side 语义未确认，却把 trade flow 写成 taker buy/sell。
```

以下情况允许保留为非方向价值:

```text
1. 明确提高 future path-width。
2. 明确识别 high RV / high activity / liquidity stress 状态。
3. 明确帮助解释 BONK1MUSDC 与 BONK1MUSDT 的 venue-local 差异。
4. 明确帮助定义下一轮数据采集优先级。
```

## 建议新增产物

后续如果实现 V3，不直接改旧报告，新增:

```text
date/bonk_v1_reasoned_candidate_scores_<run_tag>.csv
date/bonk_v1_candidate_decay_tests_<run_tag>.csv
date/bonk_v1_regime_local_edges_<run_tag>.csv
date/bonk_v1_path_width_candidates_<run_tag>.csv
docs/markets/bonk/v1-cex-v3-candidate-score-report.md
```

建议 `reasoned_candidate_scores` 字段:

```text
run_tag
candidate_id
symbol
factor_family
factor_name
horizon
barrier
regime_gate
half_life_bucket
label_target
effect_shape_score
local_regime_fit_score
half_life_plausibility_score
path_width_value_score
controlled_residual_score
stability_floor_score
parsimony_score
data_quality_score
falsifiability_score
penalty_total
reasoned_candidate_score
status
notes
```

## 下一轮执行顺序

建议只做研究输出，不做交易规则:

```text
1. 从现有 panel 和 controlled_factor_tests 生成 candidate registry。
2. 对 activity/cross-venue 因子做 lag/decay sweep。
3. 对 spread/activity 因子增加 path-width 专表。
4. 对所有方向候选增加 context-residual 和 regime-local 摘要。
5. 写出 candidate score report。
6. 下一批日期到达后，用预声明 candidate list 做 forward validation。
```

## 最终验收口径

V3 成功不是因为找到 alpha，而是因为它能把候选分清楚:

```text
哪些像短半衰期盘口现象。
哪些像 regime-local edge。
哪些只是 path-width / volatility state。
哪些只是 market-wide confounding。
哪些值得下一窗口预注册验证。
哪些应该停止。
```

只要还没有跨窗口、跨 regime、扣除成本和可成交性后的独立验证，所有输出都必须停留在 research candidate 层。

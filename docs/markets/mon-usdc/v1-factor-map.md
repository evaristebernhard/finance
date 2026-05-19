# MON/USDC V1 因子地图

状态: `20260511_factor_map_v1`，source run 为 `20260511_reconstruct_v1`。

本报告只用于探索研究。它不使用 RPC、不修改 raw data，也不声称已经得到真实 pool fee、真实 slippage 或可执行 capacity。Net labels 使用 `30` one-way fee bps，并使用每侧 `0/25/100` bps 的 stress grid。

## 覆盖率

- 执行面板行数: `2147000`
- 研究样本行数: `2147000` (`A_observed + B_reconstructed`)
- 仅覆盖率行数: `0` (`C_price_only`)
- physical feature 行数: `2147000`
- cost label 行数: `2147000`
- factor candidate 行数: `2147000`
- gross factor-map 行数: `210`
- tradability diagnostic 行数: `35`
- eval workers: `2`，请求值 `2`
- cache 复用: `physical=false, cost=false, candidates=false`

## 验证

日期按时间顺序切分为 discovery、validation 和 forward 窗口。仅使用 discovery 窗口的 quantiles 定义 factor buckets、volatility regimes 和 quote-notional buckets；validation 是排序检验切分，forward 只用于确认。

## 因子地图

主表是围绕 `market_gross, side_gross` targets 的 gross-return factor map。这里可以把每个 candidate factor，包括 gas、quote size、liquidity pressure 和 crowding，放到未来 gross returns 上检验。`side_gross_return_*` 问的是事件方向是否延续；`market_gross_return_*` 问的是事件后价格本身上涨还是下跌。

### cross_pool_dislocation

| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 41 | dislocation_over_log_quote_abs | regime_filter | market_gross | market_gross_return_5m | 590741 | 0.016549 | 0.000018 |
| 46 | dislocation_over_vol_1h | regime_filter | market_gross | market_gross_return_5m | 590741 | 0.014504 | 0.000084 |
| 48 | dislocation_over_vol_6h | regime_filter | market_gross | market_gross_return_5m | 590741 | 0.013656 | -0.000003 |
| 50 | dislocation_over_log_quote_abs | regime_filter | market_gross | market_gross_return_6h | 590741 | 0.011922 | 0.000222 |
| 53 | dislocation_over_vol_6h | regime_filter | market_gross | market_gross_return_1h | 590741 | -0.011222 | -0.000855 |
| 57 | dislocation_over_vol_1h | regime_filter | market_gross | market_gross_return_1h | 590741 | -0.010390 | -0.000640 |

### crowding_quality

| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 1 | pool_quote_hhi | quality_filter | market_gross | market_gross_return_3h | 590741 | -0.094196 | -0.013245 |
| 10 | pool_quote_hhi | quality_filter | market_gross | market_gross_return_1h | 590741 | -0.045460 | -0.003097 |
| 12 | pool_quote_hhi | quality_filter | market_gross | market_gross_return_6h | 590741 | -0.042412 | -0.013294 |
| 13 | pool_quote_hhi | quality_filter | market_gross | market_gross_return_15m | 590741 | -0.041568 | -0.000510 |
| 40 | pool_quote_hhi | quality_filter | market_gross | market_gross_return_5m | 590741 | -0.016660 | -0.000056 |
| 79 | crowding | quality_filter | side_gross | side_gross_return_5m | 590741 | -0.008491 | -0.000601 |

### event_size

| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 51 | log1p_quote_abs | event_continuation_candidate | side_gross | side_gross_return_5m | 590741 | -0.011382 | -0.000076 |
| 52 | sqrt_quote_abs | event_continuation_candidate | side_gross | side_gross_return_5m | 590741 | -0.011382 | -0.000076 |
| 76 | log1p_quote_abs | event_continuation_candidate | side_gross | side_gross_return_15m | 590741 | -0.008684 | -0.000066 |
| 77 | sqrt_quote_abs | event_continuation_candidate | side_gross | side_gross_return_15m | 590741 | -0.008684 | -0.000066 |
| 128 | log1p_quote_abs | event_continuation_candidate | side_gross | side_gross_return_1h | 590741 | -0.003583 | 0.000032 |
| 129 | sqrt_quote_abs | event_continuation_candidate | side_gross | side_gross_return_1h | 590741 | -0.003583 | 0.000032 |

### execution_cost

| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 59 | gas_over_quote_abs | execution_filter | market_gross | market_gross_return_6h | 590741 | -0.010369 | 0.000625 |
| 60 | gas_pressure | execution_filter | market_gross | market_gross_return_6h | 590741 | -0.010369 | 0.000625 |
| 142 | gas_over_quote_abs | execution_filter | side_gross | side_gross_return_3h | 590741 | -0.002932 | -0.000106 |
| 143 | gas_pressure | execution_filter | side_gross | side_gross_return_3h | 590741 | -0.002932 | -0.000106 |
| 145 | gas_over_quote_abs | execution_filter | side_gross | side_gross_return_15m | 590741 | 0.002781 | 0.000081 |
| 146 | gas_pressure | execution_filter | side_gross | side_gross_return_15m | 590741 | 0.002781 | 0.000081 |

### liquidity_capacity

| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 3 | flow_over_sqrt_liquidity | capacity_filter | side_gross | side_gross_return_6h | 351116 | 0.070741 | 0.002062 |
| 4 | flow_over_liquidity | capacity_filter | side_gross | side_gross_return_6h | 351116 | 0.063370 | 0.003222 |
| 11 | flow_over_sqrt_liquidity | capacity_filter | side_gross | side_gross_return_1h | 351116 | 0.042452 | 0.000368 |
| 14 | flow_over_liquidity | capacity_filter | side_gross | side_gross_return_1h | 351116 | 0.040705 | 0.000387 |
| 17 | quote_abs_over_log_liquidity | capacity_filter | side_gross | side_gross_return_5m | 351116 | -0.034616 | -0.000317 |
| 18 | liquidity_pressure | capacity_filter | side_gross | side_gross_return_5m | 351116 | -0.033047 | -0.000373 |

### signed_flow

| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 6 | signed_quote_flow | directional_alpha_candidate | side_gross | side_gross_return_6h | 590741 | 0.047141 | 0.001838 |
| 7 | signed_quote_flow_over_log_abs | directional_alpha_candidate | side_gross | side_gross_return_6h | 590741 | 0.047141 | 0.001838 |
| 8 | signed_quote_flow_times_log_abs | directional_alpha_candidate | side_gross | side_gross_return_6h | 590741 | 0.047141 | 0.001838 |
| 22 | signed_quote_flow | directional_alpha_candidate | market_gross | market_gross_return_5m | 590741 | -0.030453 | -0.000186 |
| 23 | signed_quote_flow_over_log_abs | directional_alpha_candidate | market_gross | market_gross_return_5m | 590741 | -0.030453 | -0.000186 |
| 24 | signed_quote_flow_times_log_abs | directional_alpha_candidate | market_gross | market_gross_return_5m | 590741 | -0.030453 | -0.000186 |

### volatility_regime

| Rank | Factor | Role | Target Kind | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: |
| 2 | trailing_realized_vol_6h | regime_filter | market_gross | market_gross_return_3h | 590741 | -0.079384 | -0.002543 |
| 5 | trailing_realized_vol_1h | regime_filter | market_gross | market_gross_return_3h | 590741 | -0.055618 | -0.005244 |
| 9 | trailing_realized_vol_6h | regime_filter | market_gross | market_gross_return_6h | 590741 | -0.046018 | -0.008770 |
| 15 | trailing_realized_vol_1h | regime_filter | market_gross | market_gross_return_6h | 590741 | -0.037718 | -0.009462 |
| 16 | trailing_realized_vol_1h | regime_filter | market_gross | market_gross_return_1h | 590741 | 0.035370 | -0.000218 |
| 44 | trailing_realized_vol_6h | regime_filter | market_gross | market_gross_return_1h | 590741 | -0.015467 | -0.000933 |


## 可交易性诊断

诊断表保留 cost、notional 和 liquidity-pressure 机制的 net-return 视角: `gas_over_quote_abs`、`gas_pressure`、`log1p_quote_abs`、`sqrt_quote_abs`、`quote_abs_over_liquidity`、`quote_abs_over_log_liquidity`、`liquidity_pressure`。这些行用于解释执行可行性和 label 敏感性。`gas_over_quote_abs` 没有被丢弃: 它仍保留在 gross factor map 中，但不能和扣除 gas 的 net labels 混在一起作为 alpha ranking，因为这种关系有一部分是机械性的。

| Rank | Factor | Family | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | gas_over_quote_abs | execution_cost | net_return_5m_slip25bps | 590741 | -0.387157 | -10.091400 |
| 2 | gas_pressure | execution_cost | net_return_5m_slip25bps | 590741 | -0.387157 | -10.091400 |
| 3 | log1p_quote_abs | event_size | net_return_5m_slip25bps | 590741 | 0.359175 | 10.141910 |
| 4 | sqrt_quote_abs | event_size | net_return_5m_slip25bps | 590741 | 0.359175 | 10.141910 |
| 5 | gas_over_quote_abs | execution_cost | net_return_15m_slip25bps | 590741 | -0.336943 | -10.091354 |
| 6 | gas_pressure | execution_cost | net_return_15m_slip25bps | 590741 | -0.336943 | -10.091354 |
| 7 | log1p_quote_abs | event_size | net_return_15m_slip25bps | 590741 | 0.318803 | 10.141920 |
| 8 | sqrt_quote_abs | event_size | net_return_15m_slip25bps | 590741 | 0.318803 | 10.141920 |
| 9 | gas_over_quote_abs | execution_cost | net_return_1h_slip25bps | 590741 | -0.283280 | -10.091494 |
| 10 | gas_pressure | execution_cost | net_return_1h_slip25bps | 590741 | -0.283280 | -10.091494 |
| 11 | log1p_quote_abs | event_size | net_return_1h_slip25bps | 590741 | 0.270855 | 10.142017 |
| 12 | sqrt_quote_abs | event_size | net_return_1h_slip25bps | 590741 | 0.270855 | 10.142017 |

## 阶段耗时

| 阶段 | 耗时 ms | 复用 cache |
| --- | ---: | --- |
| 读取 execution source 行 | 10205 | false |
| 读取 path 和 pool-state source 行 | 9102 | false |
| 生成 physical features | 85924 | false |
| 生成 cost labels | 44310 | false |
| 生成 factor candidates | 68736 | false |
| 评估 factor expressions | 757150 | false |
| 写出 outputs | 162432 | false |

## 输出

- `date/mon_usdc_v1_factor_expression_summary_20260511_factor_map_v1.csv`
- `date/mon_usdc_v1_tradability_diagnostics_20260511_factor_map_v1.csv`
- `date/mon_usdc_v1_factor_role_summary_20260511_factor_map_v1.csv`
- `date/mon_usdc_v1_factor_stability_20260511_factor_map_v1.csv`
- `date/mon_usdc_v1_factor_bucket_profiles_20260511_factor_map_v1.csv`
- `date/mon_usdc_v1_factor_split_summary_20260511_factor_map_v1.csv`
- `date/mon_usdc_v1_factor_search_completion_20260511_factor_map_v1.json`

# MON/USDC V1 因子表达式搜索

状态: `20260511_factor_expr_v1`，source run 为 `20260511_reconstruct_v1`。

本报告只用于探索研究。它不使用 RPC、不修改 raw data，也不声称已经得到真实 pool fee、真实 slippage 或可执行 capacity。Net labels 使用 `30` one-way fee bps，并使用每侧 `0/25/100` bps 的 stress grid。

## 覆盖率

- 执行面板行数: `2147000`
- 研究样本行数: `2147000` (`A_observed + B_reconstructed`)
- 仅覆盖率行数: `0` (`C_price_only`)
- physical feature 行数: `2147000`
- cost label 行数: `2147000`
- factor candidate 行数: `2147000`

## 验证

日期按时间顺序切分为 discovery、validation 和 forward 窗口。仅使用 discovery 窗口的 quantiles 定义 factor buckets、volatility regimes 和 quote-notional buckets；validation 是排序检验切分，forward 只用于确认。

第一轮里较大的 top-bottom 值主要反映 cost/notional filter 行为，尤其是 gas share 与小额 quote trades 的关系。应把它们视为 tradability filters 的诊断结果，而不是 directional alpha。

| Rank | Factor | Target | Validation N | Validation Spearman | Validation Top-Bottom |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | gas_over_quote_abs | net_return_5m_slip25bps | 590741 | -0.387157 | -10.091400 |
| 2 | log1p_quote_abs | net_return_5m_slip25bps | 590741 | 0.359175 | 10.141910 |
| 3 | sqrt_quote_abs | net_return_5m_slip25bps | 590741 | 0.359175 | 10.141910 |
| 4 | gas_over_quote_abs | net_return_15m_slip25bps | 590741 | -0.336943 | -10.091354 |
| 5 | log1p_quote_abs | net_return_15m_slip25bps | 590741 | 0.318803 | 10.141920 |
| 6 | sqrt_quote_abs | net_return_15m_slip25bps | 590741 | 0.318803 | 10.141920 |
| 7 | gas_over_quote_abs | net_return_1h_slip25bps | 590741 | -0.283280 | -10.091494 |
| 8 | log1p_quote_abs | net_return_1h_slip25bps | 590741 | 0.270855 | 10.142017 |
| 9 | sqrt_quote_abs | net_return_1h_slip25bps | 590741 | 0.270855 | 10.142017 |
| 10 | gas_over_quote_abs | net_return_3h_slip25bps | 590741 | -0.248834 | -10.091541 |
| 11 | log1p_quote_abs | net_return_3h_slip25bps | 590741 | 0.240290 | 10.142306 |
| 12 | sqrt_quote_abs | net_return_3h_slip25bps | 590741 | 0.240290 | 10.142306 |

## 输出

- `date/mon_usdc_v1_factor_expression_summary_20260511_factor_expr_v1.csv`
- `date/mon_usdc_v1_factor_stability_20260511_factor_expr_v1.csv`
- `date/mon_usdc_v1_factor_bucket_profiles_20260511_factor_expr_v1.csv`
- `date/mon_usdc_v1_factor_split_summary_20260511_factor_expr_v1.csv`
- `date/mon_usdc_v1_factor_search_completion_20260511_factor_expr_v1.json`

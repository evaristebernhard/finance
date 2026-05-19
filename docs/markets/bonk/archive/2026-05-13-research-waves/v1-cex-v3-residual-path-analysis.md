# BONK CEX V3 Residual / Path-Width Analysis

状态: 2026-05-13。本文是 `bonk_v3_residual_path_probe` 的二级解读，只用于研究分层，不输出交易规则、阈值规则或 alpha 声明。

## 输入与输出

输入:

```text
date/bonk_v3_residual_path_probe.csv
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

输出:

```text
date/bonk_v3_residual_path_factor_summary.csv
docs/markets/bonk/v1-cex-v3-residual-path-analysis.md
```

数据底座: panel 行数 `482,760`，`label_status=ok` 行数 `474,212`，probe summary 行数 `96`。窗口覆盖 BONK1MUSDC 与 BONK1MUSDT，horizon 为 1h/4h/12h，barrier 为 50/100/200/300 bps。

## 方法说明

核心读数:

```text
residual_median_bps = median(future_resid_mkt_meme_sol_bps)
abs_residual_median_bps = median(abs(future_resid_mkt_meme_sol_bps))
path_width_median_bps = median(mfe_up_bps - mae_down_bps)
first_any_hit_rate = upper_first/lower_first/both_or_ambiguous 的合计率
upper_minus_lower_first_rate = first_upper_rate - first_lower_rate
```

`date/bonk_v3_residual_path_factor_summary.csv` 重新从 parquet 计算了 corrected unordered path-hit。原因是 parquet 里的 `barrier_bps` 是 unsigned integer，直接做负号容易把 `lower_path_hit` 变成无符号下溢读数；本报告以 `first_any_hit_rate` 和 corrected unordered any-path 为准。当前 panel 中 corrected unordered any-path 与 first-any 对齐，说明 first-passage 标签和 MFE/MAE 阈值是一致的。

## Headline

结论很干净: 方向不是稳定现象，path-width 是稳定得多的现象。

Fold2 显示明显的正 residual 与 upper-first 偏向，尤其 4h/12h；Fold3 同一批 horizon 反转为负 residual 与 lower-first 偏向。这个 flip 在 BONK1MUSDC 与 BONK1MUSDT 上几乎同步，因此更像 BONK/Bullish/common regime 变化，不像单一 quote venue 的独立方向信息。

path-width 没有同样失效。Fold3 虽然方向翻负，4h/12h 的 abs residual、path_width 和 any-hit 仍然高，所以更适合作为 movement-state / volatility-path 研究对象，而不是 directional alpha。

## Fold2 -> Fold3, 100 bps Barrier

以下数值为 BONK1MUSDC 与 BONK1MUSDT 的均值，用来展示 regime flip 的形状。

| horizon | residual median bps | abs residual median bps | path width median bps | first any-hit | upper-lower first |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1h | 7.8 -> -3.4 | 32.6 -> 26.5 | 116.2 -> 93.2 | 44.6% -> 34.3% | +7.0pp -> -2.6pp |
| 4h | 40.5 -> -17.5 | 58.5 -> 51.0 | 240.5 -> 198.2 | 88.5% -> 79.7% | +31.0pp -> -5.7pp |
| 12h | 130.8 -> -59.0 | 136.9 -> 107.8 | 420.1 -> 364.5 | 100.0% -> 99.7% | +36.8pp -> -7.2pp |

读法:

```text
1h: Fold2 有轻微正 residual，Fold3 小幅转负；方向太薄，更多是短周期 movement/tail。
4h: Fold2 +40 bps residual 与 upper-first 明显占优，Fold3 变成 -17 bps residual 与 lower-first 小幅占优。
12h: Fold2 +131 bps residual 很强，Fold3 变成 -59 bps；但 any-hit 仍接近 100%，path-width 仍非常宽。
```

## 200 bps Barrier Check

200 bps 更能区分“路径宽”与“方向”。

| horizon | first any-hit | upper-lower first | path width median bps | abs residual median bps |
| --- | ---: | ---: | ---: | ---: |
| 1h | 7.9% -> 9.6% | +2.5pp -> +0.2pp | 116.2 -> 93.2 | 32.6 -> 26.5 |
| 4h | 37.2% -> 37.2% | +15.6pp -> -9.8pp | 240.5 -> 198.2 | 58.5 -> 51.0 |
| 12h | 82.9% -> 70.2% | +44.7pp -> -8.4pp | 420.1 -> 364.5 | 136.9 -> 107.8 |

读法:

```text
1h/200bps: hit 率只有约 8% -> 9.6%，方向差几乎不可用，只能作为尾部诊断。
4h/200bps: hit 率稳定在约 37%，但 upper-lower 从 +15.6pp 翻到 -9.8pp，是 regime-local direction，不是稳定方向。
12h/200bps: hit 率仍高，Fold2 上行 first-passage 很强，Fold3 方向翻负；这是最强的 path-width/regime flip 组合。
```

## Horizon 分层

| horizon | residual sign flip rows | first-direction flip rows | avg Fold2 -> Fold3 residual | avg Fold2 -> Fold3 path width |
| --- | ---: | ---: | ---: | ---: |
| 1h | 8/8 | 4/8 | 7.8 -> -3.4 | 116.2 -> 93.2 |
| 4h | 8/8 | 8/8 | 40.5 -> -17.5 | 240.5 -> 198.2 |
| 12h | 8/8 | 8/8 | 130.8 -> -59.0 | 420.1 -> 364.5 |

1h 的 residual 量级小，50/100 bps any-hit 有 activity/path 信息，但 200/300 bps 已经偏尾部。它不适合作为方向候选。

4h 是中等 path-width 状态: 100/200 bps hit 率有研究价值，但 Fold2/Fold3 的 upper-lower first 明确翻转。方向只能写成 regime-local phenomenon。

12h 是最强 path-width 状态: abs residual 和 path_width 最大，200/300 bps 仍有可观 any-hit。它同时也是最明显的 Fold2/Fold3 方向翻转，所以应优先作为 path-width / regime-state candidate，而不是 continuation/reversal 方向规则。

## 方向还是 Path-Width

可以保留为方向现象的只有很窄的表述:

```text
Fold2 局部 regime 内，4h/12h residual 为正且 upper-first 占优。
Fold3 局部 regime 内，4h/12h residual 为负且 lower-first 占优。
```

这不是跨 regime 稳定方向。只要把 Fold2 与 Fold3 连起来看，directional read 就失效。

可以保留为 path-width / movement-state 的现象更强:

```text
12h path_width median: Fold2 约 420 bps，Fold3 约 365 bps。
12h/100bps first any-hit: Fold2/Fold3 都约 100%。
12h/200bps first any-hit: Fold2 约 83%，Fold3 约 70%。
4h/100bps first any-hit: Fold2 约 89%，Fold3 约 80%。
```

这些读数即使在方向翻转后仍存在，因此更像“未来路径会很宽/会触发 barrier”的状态变量。

## Summary CSV 分类

`date/bonk_v3_residual_path_factor_summary.csv` 的 `phenomenon_class` 分布:

| class | rows |
| --- | ---: |
| `low_hit_tail_diagnostic_only` | 4 |
| `path_width_state_not_direction` | 4 |
| `regime_flip_not_stable_direction` | 16 |

分类口径:

```text
regime_flip_not_stable_direction: residual 与 first-passage 方向在 Fold2/Fold3 翻转。
path_width_state_not_direction: hit/path-width 明显，但方向弱或不稳。
low_hit_tail_diagnostic_only: hit 率太低，只能看作尾部诊断。
```

## 下一步

下一轮不要从这份结果直接写交易规则。更合适的延续是:

```text
1. 把 12h path-width 作为预注册 movement-state candidate。
2. 把 4h/100-200bps 作为 regime-local path-width candidate。
3. 把 Fold2/Fold3 regime gate 显式化，优先测试 ctx_market/meme/SOL、BONK relative strength、RV/common-mode。
4. 对方向候选要求下一窗口预注册验证；没有通过前，只保留为 regime-local phenomenon。
```

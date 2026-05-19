# BONK CEX V3 Profit Risk Red Flags

状态: 2026-05-13。本文从反方/风控角度重读所有 `date/bonk_v3_*` CSV/JSON 与 `docs/markets/bonk/*v3*.md`。输出配套机器表:

```text
date/bonk_v3_profit_risk_red_flags.csv
```

本文只讨论为什么 V3 的 gross bps / residual bps 不能直接解释成可交易利润，不输出交易规则、仓位、阈值或 alpha 声明。

## Executive Skeptic Read

当前 V3 book 有 126 行: `active_candidate=2`, `watch=20`, `exploratory=67`, `diagnostic_only=37`。从 profit queue 看，只有一条可以保留为下一窗口预注册验证对象:

```text
BONK1MUSDT H4 top_depth_total_notional_median=high
```

即使这一条也不能称为 profit candidate。它只是 placebo 最干净的研究候选，但最新 rolling 48h median residual 已经转为 `-63.2 bps`，non-overlap upper edge 为 `-0.0249`，Fold3 model proper-score pass rate 为 `0%`。它必须先过下一窗口验证，再讨论执行成本。

其余 active/watch 行应从 profit queue 直接降级为 regime/path-width/cross-venue diagnostic。104 条 exploratory/diagnostic 行已经低于 profit queue，只保留历史或诊断价值。

## Why Gross Bps Gets Eaten

`v1-cex-v3-aggressive-research-plan.md` 记录的 L2 window 是 `2026-04-29..2026-05-12`，median spread 为:

| symbol | median spread |
| --- | ---: |
| BONK1MUSDC | 2.74 bps |
| BONK1MUSDT | 1.59 bps |

这只是 spread floor，不包含 taker fee、maker/taker selection、queue miss、slippage、latency、partial fill 和 adverse selection。V3 输入没有实测 execution-cost table，所以任何 gross bps 都必须先扣掉至少 round-trip spread floor，再扣未知 fees/slippage。

更大的问题是这些 bps 不是成交 PnL。多数表里的 `edge_residual` 是 first-passage 或 residual-rate edge，不是净收益。`recent_regime_edge_summary` 里的 `median_resid_future_return_bps` 也只是标签侧未来残差中位数，不等于可以在 bid/ask 里成交的收益。

最新 rolling 48h 是最刺眼的反方信号: active/watch 的 `latest_rolling48_median_resid_bps` 全部为负。部分代表行:

| candidate | latest rolling residual | latest future return | read |
| --- | ---: | ---: | --- |
| BONK1MUSDT H4 top_depth_total_notional_median=high | -63.2 bps | -146.3 bps | best row still fails latest path |
| BONK1MUSDT H4 ctx_bonk_rv_1h_bps=low | -71.0 bps | -147.7 bps | regime state flipped |
| BONK1MUSDC H12 ctx_bonk_rv_1h_bps=low | -269.2 bps | -502.5 bps | 12h overlap/regime risk |
| BONK1MUSDT H12 top_depth_total_notional_median=high | -259.1 bps | -493.7 bps | path-width, not direction |

If the latest slice is negative before costs, spread/fees/slippage do not need to be large to erase the historical gross edge.

## Core Red Flags

Spread and fee risk: median spread is already 1.59 to 2.74 bps. A taker round trip plus adverse selection can easily consume 1h edges, and V3 has no fee/slippage measurement.

Slippage and selection risk: `top_depth_total_notional_median=high` is a state variable, not a guarantee that a selected signal can fill at displayed top depth. If high-depth buckets are selected after observing favorable paths, execution will arrive in worse queue states.

Overlap risk: 4h and 12h labels overlap heavily. `model_validation_design` explicitly says phase rows are smoke-level, not independent alpha evidence; 4h phase stride median is only 15 to 18 rows per phase.

Regime flip risk: `residual_path_factor_summary` shows Fold2 to Fold3 direction reversal:

| horizon | residual median bps | upper-lower first |
| --- | ---: | ---: |
| 1h | 7.8 -> -3.4 | +7.0pp -> -2.6pp |
| 4h | 40.5 -> -17.5 | +31.0pp -> -5.7pp |
| 12h | 130.8 -> -59.0 | +36.8pp -> -7.2pp |

The path remains wide, but direction flips. That is movement-state evidence, not stable profit direction.

Placebo risk: in the active/watch deep dive, only 3 of 22 rows have placebo below 0.75x. Ten rows are `medium_placebo_ge_1_0x` and five are `high_placebo_ge_1_5x`.

Cross-venue risk: cross-venue basis/spread variables are strongest for basis compression and movement/path-width, not for proven lead-lag PnL. Same-window convergence can be stale quote selection, not executable arbitrage.

Side semantics risk: `BONK1MUSDC` reported side is mostly reversed versus quote-rule side, while `BONK1MUSDT` is mixed/inconclusive. Any signed-flow profit story must use quote-rule inferred side, not raw reported side.

Model risk: phase/model probes do not rescue Fold3. The summary has only `6/24` paired proper-score passes and `3/8` Fold2/Fold3 passes; Fold3 non-overlap proper-score support is effectively absent for the active H4 rows.

## Direct Downgrades

The CSV marks direct profit downgrades explicitly. Active/watch downgrades are:

| decision | rows | examples | reason |
| --- | ---: | --- | --- |
| `direct_downgrade_to_regime_utility_validate_gate_if_retained` | 4 | `ctx_bonk_rv_1h_bps=low` at 4h/12h | context/RV is a regime gate, not entry PnL; placebo and latest rolling flip |
| `direct_downgrade_to_cross_venue_diagnostic_validate_lead_lag_if_retained` | 4 | `cross_venue_spread_diff_bps` at 4h/12h | convergence/path-width diagnostic; lead-lag not proven |
| `direct_downgrade_to_path_width_or_diagnostic` | 8 | microprice rows, activity rows, 1h cross-venue | placebo/path-width/participation state |
| `direct_downgrade_due_thin_1h_cost_and_overlap` | 2 | 1h top-depth rows | 1h gross is too thin after spread/fees/slippage |
| `direct_downgrade_to_path_width_liquidity_regime_validate_if_retained` | 2 | 12h top-depth rows | big path movement, but overlap and regime flip dominate |
| `direct_downgrade_to_liquidity_diagnostic` | 1 | BONK1MUSDC H4 top-depth | non-overlap negative, latest rolling negative |

All 104 `exploratory`/`diagnostic_only` rows are marked `already_downgraded_by_book_keep_as_history_or_diagnostic`.

## Next-Window Validation Required

The only row that survives as a narrow profit-research validation item is:

| candidate | why not killed immediately | must pass next |
| --- | --- | --- |
| BONK1MUSDT H4 `top_depth_total_notional_median=high` | best placebo profile among active rows, cross-fold effect exists | same symbol/factor/bucket/horizon, no threshold reselection, latest rolling residual positive, non-overlap edge positive, Fold3 direction not flipped, explicit spread/fee/slippage haircut |

Several rows can be validated only as non-profit diagnostics if the research queue wants them:

| group | validation scope |
| --- | --- |
| `ctx_bonk_rv_1h_bps=low` | validate as explicit regime gate only |
| 12h top-depth rows | validate as movement/path-width state only |
| 4h/12h `cross_venue_spread_diff_bps` | validate lagged lead-lag/convergence after costs; same-window basis compression is insufficient |

Failure condition for all of them: if the next window needs reselected dates, reselected buckets, looser spread assumptions, or overlapping labels to look good, the candidate stays downgraded.

## Bottom Line

V3 found useful market phenomena, not executable profit. The cleanest read is:

```text
gross/residual bps -> regime/path-width/candidate evidence
net profit -> unproven until pre-registered next-window and cost-aware validation
```

For now, treat BONK V3 as a risk map and validation queue, not a strategy queue.

#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Runtime Promotion：从研究因子到策略候选

本章给出因子进入策略的专业化检查路径。

== Promotion ladder

#definition("Promotion ladder", [
  因子 promotion 需要依次通过：mechanism plausibility、runtime measurability、offline association、matched-control evidence、tail risk profile、execution sensitivity、capacity sensitivity、OOS/pressure validation。
])

任何跳过 runtime measurability 的因子，即使历史收益再高，也只能 diagnostic。任何跳过 execution 的 mid-edge，都不能声称可交易。

更形式化地，promotion 是一个交集条件：

$ "Promote"(X)=M(X) and R(X) and A(X) and C(X) and T(X) and E(X) and K(X) $

其中 $M$ 是 mechanism plausibility，$R$ 是 runtime measurability，$A$ 是 association/matched-control evidence，$C$ 是 cost/execution evidence，$T$ 是 tail evidence，$E$ 是 external/OOS sanity，$K$ 是 capacity feasibility。任何一项失败，都应记录失败层，而不是简单写“因子不行”。

#proposition("Promotion is monotone in evidence layers, not in PnL", [
  历史 PnL 增加不必然提高 promotion status。若新增收益来自 oracle、profile mismatch、capacity displacement 或单日右尾集中，promotion status 反而应降低。
])

== Profile manifest

每个 run 必须记录：

- policy_profile。
- capacity_profile。
- exit_profile。
- fill_profile。
- latency_profile。
- transport_profile。
- data/cache manifest。

否则不同 profile 的数字不可比较。

#assumption("Profile hard boundary", [
  不同 `policy_profile`、`capacity_profile`、`exit_profile`、`fill_profile`、`latency_profile` 或 `transport_profile` 的结果不得直接比较总 PnL。必须先说明差异来自哪个 profile 层。
])

== Runtime candidate 当前分层

当前更接近 core candidate 的对象：

- TFI / rolling trade imbalance。
- R5/R10 with Delta/Energy/Z。
- frames_since_mid_change as state condition。
- spread/depth as execution and condition。
- capacity state。

Guard / condition：

- QI。
- OFI/MLOFI。
- vacuum。
- residual pressure。
- exhaustion。

Diagnostic labels：

- release。
- decay。
- MFE/MAE。
- CVaR/tail_share。
- oracle exit。

#remark("Diagnostic label 的价值", [
  Diagnostic-only 不等于无价值。MFE/decay/path casebook 是机制发现的核心；它们只是不能直接作为 runtime feature。
])

== 因子状态表

当前 CCUSDT 因子系统可给出如下专业状态：

- `TFI` / rolling trade imbalance：core impulse candidate。需要继续做 normalization 与 matched-control 增量。
- `R5/R10`：path-memory candidate。必须伴随 Delta/Energy/Z，不能单独当 quality score。
- `frames_since_mid_change`：staleness condition。不是单独 alpha，但与 R5 有 interaction value。
- `spread`：execution/admission/control variable。对 taker strategy 是硬成本。
- `depth` / vacuum：release condition。不能直接推广为 continuation。
- `QI`：control/condition。standalone alpha weak。
- `OFI/MLOFI`：dynamic book sidecar。适合研究 absorption/refill，不应未验证就抢主线。
- residual pressure：diagnostic/guard component。单独不稳。
- exhaustion：hold guard candidate。更接近 continuation guard，但仍需严格 runtime test。
- q60/q65 thresholds：sensitivity。当前不作为主线 promotion。
- oracle MFE/decay/path labels：diagnostic-only。

== Promotion checklist

进入下一轮策略优化前，应逐项回答：

1. 因子是否是 $cal(F)_t$ 可测？
2. 其金融对象是 pressure、depth、memory、staleness、execution、capacity 还是 path-state？
3. 是否存在 matched-control 增量，而不只是 composition effect？
4. 是否报告了 conditional distribution，而不只是 mean？
5. 是否在 prior-date threshold 下仍成立？
6. 是否能通过 fast-vs-strict decision identity 对齐？
7. strict taker 后的差异是否被 spread/latency/depth 分解？
8. 3x capacity 下 actual exposure 是否仍合理？
9. 左尾 case 是否有机制解释，而不是被均值掩盖？
10. 所有 label 是否与 runtime feature 分离？

== 本章结论

专业化因子研究的终点不是最大化一张历史表，而是构建可测、可解释、可估计、可执行、可归因的策略候选。对于 CCUSDT，下一轮最自然的问题是：用 Delta/Energy/Z 改善 R5 质量识别，用 small stopping-time manager 处理 release/decay，用 execution/capacity decomposition 保证 fast 与 strict 口径一致。

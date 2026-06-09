#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Execution、Capacity 与 Worst-Day Attribution

本章讨论策略结果如何从因子证据中分解出来。专业因子分析必须区分 alpha、execution、capacity 与 tail。

== Execution decomposition

Fast mid-edge 到 strict taker PnL 的分解：

$ "PnL"^"strict" = "PnL"^"mid" - C^"entry spread" - C^"exit spread" - C^"latency" - C^"depth" - C^"pressure" $

#definition("Execution evidence", [
  Execution evidence 是在给定相同 entries、side、weights 与 capacity decision 下，fill profile、latency profile 与 market arrival state 对收益的影响。它不能与 alpha evidence 混淆。
])

若 strict taker net 明显低于 fast mid PnL，首先应分解 spread/crossing，而不是否定 entry factor。

更细的 per-entry decomposition 可写为：

$ y_i^"strict" = w_i^"act" (R_i^"mid" - c_i^"entry" - c_i^"exit" - c_i^"lat" - c_i^"depth" - c_i^"pressure") $

其中 $R_i^"mid"$ 是 mid-to-mid path label；$c^"entry"$ 与 $c^"exit"$ 是 crossing spread；$c^"lat"$ 是 observed quote 到 arrival quote 的移动；$c^"depth"$ 是订单扫深度的 VWAP slippage；$c^"pressure"$ 是为了 stress test 引入的额外惩罚。

#proposition("Fee-free taker still has crossing loss", [
  若买入以 ask 成交、卖出以 bid 成交，则即使 fee 为零，round-trip 仍支付 bid-ask spread。显式手续费 $C_"fee"=0$ 只删除 fee term，不删除 crossing term。
])

这条命题是当前策略优化的核心限制之一。对 spread 不友好的盘口强行 taker crossing，可能把 mid edge 大幅削薄；这不是交易所收费，而是价格优先队列的基本代价。

== Deterministic strict replay

Strict replay 的 execution path 应是纯函数：

$ ("fills","portfolio","events")=F(cal(M),pi,theta) $

其中 $cal(M)$ 是 canonical market stream，$pi$ 是策略，$theta$ 是 profile 参数。Wall-clock bridge timing 只能进入 diagnostics，不能影响 deterministic arrival quote、fill price 或 portfolio state。

#assumption("Transport invariance", [
  在 deterministic profile 下，strict_event、batched_public_barrier_v1 与 panel_sparse_fast_clock_v1 若产生同一 decision identity，则 execution hash 与 portfolio hash 必须一致。否则 transport layer 泄漏进了交易语义。
])

这个假设把工程优化和研究语义分开。加速可以改变 transport cost，不能改变 arrival observation rule。

== Capacity constraint

3x capacity constraint：

$ L(t)=sum_{i:t_i<=t<tau_i} w_i^"act" <= 3 $

online clipping：

$ w_i^"act"=min(w_i^"req", max(0, 3-L(t_i^-)-m)) $

Capacity 改变每个因子的 actual exposure。`01_frames_only` 作为全局 gamma 可能挤占 core，但作为 idle sleeve 可能增加收益。

#evidence("Leverage constrained optimization", [
  q70 core-only online total 约 6038.2000；`idle01_g1_r0` total 约 6907.5648，delta 约 +869.3648。2026-05-18 OOS C=0 中 core-only 约 415.8276，idle01_g1_r0 约 472.5926。该证据说明 capacity role 会改变因子价值。
])

== Core 与 idle sleeve

当前更合理的 capacity interpretation 是：

- core cells `00`、`10`、`11` 先占用基础 capacity。
- `01_frames_only` 不以全局 gamma 与 core 竞争，而作为 idle-capacity sleeve。
- 每个 entry 记录 requested exposure、actual exposure、clipped exposure、capacity source。

这把优化问题从“哪个 gamma 最大”转化为“当核心 exposure 未用满时，是否存在低相关的增量 sleeve”。在数学上，策略不再只优化 $sum_i w_i r_i$，而是优化受约束的在线分配：

$ max sum_i w_i^"act" r_i, quad 0<=w_i^"act"<=w_i^"req", quad sum_{i in "open"} w_i^"act"<=3 $

并且 $w_i^"act"$ 必须由到达时 ledger 决定，不能回看未来 concurrency peak。

#remark("Global downscale is conservative diagnostic", [
  用全历史最大并发对所有 leg 做统一 downscale 是保守下界，不是实际 online allocator。真实策略应使用 FIFO/arrival clipping，并报告 skipped/clipped legs。
])

== Worst-day attribution

令 day $D$ 的收益按 cell 分解：

$ P_D=sum_c n_{D,c} bar(r)_{D,c} $

可粗略分为 composition effect 与 payoff decay：

$ C_D=sum_c (n_{D,c}-n_c^*) bar(r)_c $

$ Q_D=sum_c n_{D,c}(bar(r)_{D,c}-bar(r)_c) $

Composition problem 应考虑 admission/capacity；payoff decay problem 应考虑 regime/exit/pressure。

#evidence("Worst-day decomposition", [
  Factor decomposition 报告中 worst target-policy day 是 2026-05-13，total 约 -58.2736，composition effect 约 -77.1500，payoff decay 约 -39.8510。说明 worst day 不是单一 entry filter 问题。
])

== Four evidence layers

一个专业 summary 至少要拆成四张表：

- alpha evidence：mid-path 或 event-time label 的条件分布。
- execution evidence：taker/maker、spread、latency、depth 后的净收益。
- capacity evidence：requested vs actual exposure、clipping、skips、residual positions。
- tail evidence：CVaR、worst entry、worst day、casebook class。

若只报告总 PnL，优化器会偏好偶然避开左尾或偶然命中右尾的配置；若只报告 strict PnL，又可能把执行成本误判为因子无效。分层报告是减少错误结论的唯一办法。

== 本章结论

策略 total 是多个层的合成结果。因子 promotion 必须报告 alpha evidence、execution evidence、capacity evidence 与 tail evidence。否则优化会把执行问题误诊为因子问题，把容量问题误诊为 entry 问题。

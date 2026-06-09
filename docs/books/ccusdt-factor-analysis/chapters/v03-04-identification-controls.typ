#import "../styles.typ": definition, assumption, proposition, remark, evidence

= 识别、控制变量与 Matched Estimand

上一章定义了 factor 与 label，但这还不够。专业因子分析必须回答一个更尖锐的问题：观察到的收益差异到底来自因子本身，还是来自 day regime、entry cell、spread、depth、event intensity、capacity overlap 或已有价格动量？本章给出 CCUSDT 因子研究的识别语言。

== Association 与 estimand

令 $X_i$ 为 entry $i$ 的候选因子，$Y_i$ 为未来 label。最弱的证据是无条件相关：

$ "Assoc"(X,Y)=E[Y|X=1]-E[Y|X=0] $

这个对象在探索阶段有价值，但不能直接解释为因子增量。更接近策略研究的问题是：在同一类市场状态下，打开这个因子条件，收益分布如何变化？

#definition("Matched-control estimand", [
  给定控制状态 $C_i$，因子 $X$ 的控制增量定义为
  $
    Delta_X(c)=E[Y_i|X_i=1,C_i=c]-E[Y_i|X_i=0,C_i=c].
  $
  总体增量不是简单平均，而应按目标策略会遇到的状态分布 $w(c)$ 聚合：
  $
    Delta_X^w=sum_c w(c) Delta_X(c).
  $
])

这里 $w(c)$ 的选择很重要。若用历史样本频率，得到的是 retrospective estimand；若用 live policy 的触发状态频率，得到的是 policy-relevant estimand。两者不同，特别是在 capacity profile 改变 entry composition 时。

== 控制状态的最小集合

CCUSDT v1 TFI 主线至少需要以下控制变量：

- calendar/day：控制日内 regime 与样本集中。
- side：long 与 short 的 order-flow condition 不完全对称。
- trigger cell：`00_none`、`10_r5_only`、`01_frames_only`、`11_r5_frames`。
- spread bucket：控制 crossing cost 与 liquidity state。
- top/depth bucket：控制 release denominator 与 depth sweep condition。
- event intensity：控制活跃度，不把高活动误认成 alpha。
- `past_event_25_bps` 或相似 past move：控制短期动量与已经发生的价格释放。
- capacity state：控制 open exposure 与 clipping。

#definition("Control state", [
  本书把 $C_i$ 定义为 entry 前可见的 nuisance state。它不是策略一定要使用的信号，而是为了识别 $X_i$ 的增量必须匹配或分层的状态。典型形式为
  $
    C_i=(D_i,S_i,G_i,Q_i,I_i,P_i,L_i),
  $
  分别表示 day、side、cell、spread bucket、depth/queue bucket、past-event state、leverage/capacity state。
])

注意 `past_event_25_bps` 的位置。它不是 future label，而是 entry 前已经发生的 event-time price movement，因此可以作为控制变量或 runtime-safe state。它用于回答：候选因子是否只是复述了刚刚已经发生的价格变化？

== Conditional comparability

Matched-control 分析需要一个弱识别假设。它不是说市场可以被完全随机化，而是说在足够细的控制状态下，剩余差异更接近候选因子增量。

#assumption("Conditional comparability", [
  对控制状态 $C=c$ 内的样本，$X=1$ 与 $X=0$ 的 entry 在主要 nuisance dimensions 上具有可比性。换言之，未控制的 regime 差异不能系统性解释 $Y$ 的差异。
])

这个假设无法从数学上自动证明，只能通过诊断弱化风险：比较 day distribution、side distribution、spread/depth distribution、past_event distribution 和 event-intensity distribution；若差异过大，应降级为 association evidence。

#remark("Matched controls 不是因果承诺", [
  CEX LOB 是适应性系统，不满足实验随机化。Matched-control estimand 是内部研究的识别纪律，不是强因果证明。它的作用是防止把 composition effect 和 factor effect 混为一谈。
])

== 支持集与 overlap

若某个因子只在少数状态中出现，则 $Delta_X(c)$ 无法在其他状态识别。定义状态 $c$ 的 overlap：

$ o(c)=min("Pr"(X=1|C=c), "Pr"(X=0|C=c)) $

当 $o(c)$ 接近零时，matched-control estimate 主要依赖 extrapolation。短周期因子常见问题是高 TFI、高 event intensity、低 depth 同时出现，导致单因子增量难以分开。

#proposition("No-overlap buckets cannot identify marginal effect", [
  若在某控制状态 $c$ 中 $"Pr"(X=1|C=c)=1$ 或 $"Pr"(X=0|C=c)=1$，则仅凭该状态内样本无法估计 $Delta_X(c)$。该状态只能用于描述 conditional outcome，不能用于识别 $X$ 的边际增量。
])

这对四象限尤其重要。`11_r5_frames` 本身是复合状态，不能再把 `R5>1` 与 `frames>=q90` 当作完全可分的两个独立因子。它更适合被解释为 interaction cell，然后在 cell 内研究 release/decay、spread、depth、flow continuation 的增量。

== 因子、控制变量与执行变量的分层

同一个字段在不同研究问题中有不同身份。`spread` 可以是：

- execution cost variable：衡量 taker crossing 成本。
- control variable：确保高 TFI 组和低 TFI 组 liquidity state 可比。
- admission variable：过滤特别不友好的 entry。
- label component：在 fast-vs-strict 分解中作为 cost attribution。

这不矛盾，但每次研究必须声明角色。若一个变量既用于定义 entry，又用于匹配 controls，还用于解释 PnL 差异，报告必须拆清楚。

#definition("Variable role map", [
  对任意变量 $Z$，本书要求标注其角色：
  factor input、control state、execution state、capacity state、future label、diagnostic-only label 或 artifact metadata。未标注角色的变量不应进入 promotion discussion。
])

== 当前证据约束

#evidence("Worst-day attribution as identification warning", [
  Factor decomposition 报告中 worst target-policy day 2026-05-13 的 total 约 -58.2736，同时存在 composition effect 约 -77.1500 与 payoff decay 约 -39.8510。这说明最差日不能被单一 entry factor 解释，需要同时控制 entry composition 与 path payoff change。
])

#evidence("Static queue weakness as control lesson", [
  LOB stylized factor 报告中 static `obi_1` standalone AUC 约 0.5094，接近无方向区分能力。但它仍可作为 liquidity/control state 使用。弱 alpha 不等于弱 control value。
])

== 实证流程

本书建议的 matched-control 因子流程为：

1. 先做 unconditional scan，只用于发现候选机制。
2. 固定候选变量的 runtime role 和 label role。
3. 构造 $C_i$，至少包含 day、side、cell、spread、depth、event intensity、past_event 和 capacity。
4. 检查 overlap support，删除或合并 no-overlap fine bucket。
5. 报告 conditional mean、median、CVaR、tail_share 和 day dispersion。
6. 对同一候选做 fast mid、strict taker、capacity clipped 三种归因。
7. 若结果依赖未来 label 或 oracle path，降级为 diagnostic。

== 本章结论

因子研究不是寻找“历史上收益最高的列”，而是估计 $F_{Y|X,C}$ 的可识别差异。`past_event`、spread、depth、event intensity 和 capacity state 是保护识别的控制层。没有 controls 的收益表只能作为探索；有 controls 但没有 runtime measurability 的结果只能作为诊断；两者都通过后，才有资格进入策略候选。


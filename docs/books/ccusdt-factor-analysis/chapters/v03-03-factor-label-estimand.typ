#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Part II：因子、Label 与估计对象

本章定义因子分析的统计对象。一个专业因子研究不是问“某列是否赚钱”，而是问一个可测统计量如何改变未来收益分布，以及这种关系是否能在控制状态下被识别。

== 因子与 Label

#definition("Factor and label", [
  因子 $X_n$ 是 $cal(F)_n$ 可测统计量。Label $Y_{n,T}$ 是未来路径泛函，例如 $R_{n,T}$、$H_n(T)$、$D_n(T)$、strict taker net 或 path class。因子用于 runtime decision；label 用于估计与诊断。
])

这一定义要求每个变量先被分类。`spread` 是 factor 或 execution state；`MFE10` 是 label；`post-entry observed drawdown` 在 entry 后某时刻可以成为 exit-state factor；`future decay60` 仍是 label。

== Conditional distribution

仅估计 $E[Y|X]$ 不够。右尾策略和左尾风险要求估计条件分布：

$ F_{Y|X,C}(y|x,c)="Pr"(Y<=y | X=x, C=c) $

其中 $C$ 是控制状态，例如 day、cell、spread bucket、depth bucket、past-event move、capacity state。

#definition("Factor effect estimand", [
  对二值因子 $X$，控制状态 $C=c$ 下的 matched-control estimand 为 $Delta_X(c)=E[Y|X=1,C=c]-E[Y|X=0,C=c]$。对连续因子，可用 quantile spread、rank IC 或 conditional partial effect 替代。
])

这个定义避免把 day regime 或 cell composition 当成因子效果。若 high TFI 样本大多出现在趋势日，则 naive mean 可能高估 TFI 本身的增量。

== 多目标 label

同一因子可对应不同 label：

- `fwd_event_25_bps`：短 event-time response。
- `fwd_time_60s_bps`：fixed holding outcome。
- `MFE10`：early release。
- `decay60`：peak giveback。
- strict taker net：execution-adjusted outcome。

#remark("Label-specific validity", [
  因子在某个 label 上弱，不代表机制无效。`log_opp_depth25_quote` 可以强解释 early release，同时弱解释 60s continuation；这说明该因子属于 release family，而非 hold-value family。
])

== Tail-aware estimands

右尾策略需要 tail-aware 统计量。定义：

$ "CVaR"_alpha(Y)=E[Y | Y<=q_alpha(Y)] $

$ "tail_share"_q = sum_i Y_i^+ 1{Y_i>=Q_q(Y)} / (sum_i Y_i^+ + epsilon) $

CVaR 描述左尾，tail_share 描述右尾集中度。两者必须和 mean/median 同时报告。

#proposition("Median negativity is not a rejection criterion", [
  存在分布 $Y$ 使 $"median"(Y)<0$ 且 $E[Y]>0$。因此 `net_median < 0` 不是丢弃 right-tail factor family 的充分条件。
])

证明：令 $Y=-1$ 的概率为 0.7，$Y=4$ 的概率为 0.3，则 median 为 -1，而期望为 0.5。短周期右尾策略常具有类似结构，区别只在于实际分布更肥尾且受成本影响。

== 识别问题

因子研究的识别问题至少包括：

- selection：触发组是否集中在特定 day/regime。
- overlap：多个因子高度共线。
- look-ahead：future label 是否进入 feature。
- execution confounding：mid-edge 是否被 spread/depth 吞噬。
- capacity confounding：高并发是否改变实际 exposure。

#assumption("可解释 promotion", [
  一个因子进入策略候选前，必须给出机制定位、runtime measurability、matched-control evidence、tail risk profile 和 execution/capacity sensitivity。单一 aggregate total 不足以 promotion。
])

== 本章结论

专业因子分析的对象是 $F_{Y|X,C}$，而不是单列收益均值。Factor 是当时可见统计量，label 是未来路径泛函；matched controls 识别增量，CVaR 与 tail_share 识别分布形状，execution 与 capacity 决定可实现性。


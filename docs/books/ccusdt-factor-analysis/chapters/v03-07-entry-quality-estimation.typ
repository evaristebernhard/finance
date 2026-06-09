#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Entry-Quality Estimation

本章将 entry-quality 建模为条件分布估计问题，而不是简单的 entry filter。目标是估计某个 entry 在 as-of 信息下的收益分布、右尾和左尾。

== Entry-quality 的多对象定义

Entry quality 至少包括三个目标：

$ Q_i^"release" = "Pr"(H_i(tau_0)>h | cal(F)_{t_i}) $

$ Q_i^"hold" = E[R_i(T) | H_i(tau_0)>h, cal(F)_{t_i+u}] $

$ Q_i^"risk" = "CVaR"_alpha(R_i(T) | cal(F)_{t_i}) $

第一个对象是 release probability，第二个是 release 后 hold value，第三个是 left-tail risk。固定 60s return 将三者混合，因此不能单独解释 entry。

这三个对象的可测时间不同。$Q_i^"release"$ 是 entry-time 对未来 release 的预测；$Q_i^"hold"$ 在 release 已经发生后才有意义；$Q_i^"risk"$ 可以在 entry-time 估计，也可以在 entry 后随 path 更新。因此，一个单一 entry filter 不可能同时最优解决 admission、hold 和 exit。

#definition("Entry-quality estimator", [
  Entry-quality estimator 是一个 as-of 估计器 $hat(g)(X_i)$，输出当前 entry 的条件均值、tail risk 或 quality class。它的训练 label 可以是未来路径，但 runtime 输入必须是 $cal(F)_{t_i}$ 可测特征。
])

== As-of feature vector

可接受的 entry-time feature vector 可写为：

$ X_i=(X_i^"flow",X_i^"book",X_i^"memory",X_i^"stale",X_i^"exec",X_i^"capacity") $

其中：

- $X^"flow"$：TFI、rolling trade imbalance、event intensity。
- $X^"book"$：spread、depth、QI、OFI/MLOFI summary。
- $X^"memory"$：R5/R10、Delta/Energy/Z。
- $X^"stale"$：frames_since_mid_change、time since last mid change。
- $X^"exec"$：entry_cross_bps、top-of-book depth、arrival-risk proxy。
- $X^"capacity"$：open exposure、idle capacity、cell overlap。

#proposition("Entry quality is conditional on execution profile", [
  同一 entry 的 mid-path quality 与 taker-execution quality 可以不同。若 spread 或 depth 不友好，entry-time alpha 为正也可能在 strict taker round-trip 中变成低质量 entry。
])

这解释了为什么“零手续费”仍不够。显式 fee 为零只移除了 $C_"fee"$；entry ask、exit bid、latency movement 和 depth sweep 仍然决定 realized quality。

== Shrinkage hierarchy

对 CCUSDT 样本，合理层级为：

`global -> cell -> cell_direction -> cell_direction_quantile -> fine bucket`

估计器：

$ hat(mu)_A=lambda_A bar(r)_A+(1-lambda_A)hat(mu)_{pi(A)} $

$ lambda_A=n_A/(n_A+k) $

该估计不是预测模型炫技，而是最小化 small bucket overfit 的必要结构。

#assumption("As-of training", [
  对 entry $i$ 的估计，只能使用 $t_j+T<t_i$ 的历史 label 或 prior-date 训练结果。若使用同日未来 entry 的结果，则 estimator 不满足 prequential requirement。
])

== Quality class 与 action 分离

设 $K_i$ 是 quality class。策略 action 不是 $K_i$ 本身，而是：

$ a_i = pi(X_i,K_i,L_i^-,theta) $

其中 $L_i^-$ 是 entry 前 capacity ledger。一个 class 可以导致 full size、reduced size、idle-capacity-only 或 no trade。若把 class 直接等同交易指令，会把估计层和执行层耦合，导致后续无法解释容量变化。

== Quality class 的解释

`strong_positive`、`positive_right_tail_fragile`、`avoid_or_reduce` 等 class 是估计摘要，不是交易指令。一个 `avoid_or_reduce` class 可能表示样本不足、左尾较差、执行成本敏感或均值不足；它不证明 underlying structure 无价值。

#evidence("Entry estimation evidence", [
  报告显示 active entries 约 1715，strict estimates 约 1665。`strong_positive` 252 entries，weighted mean 约 7.5693；`positive_right_tail_fragile` weighted mean 约 3.5521。这支持 entry-level estimation，但不允许把 class 直接等同策略。
])

== Right-tail 与 net median

右尾策略的核心是：

$ E[Y]=p_+ E[Y|Y>0]+p_- E[Y|Y<=0] $

若 $p_-$ 较大但损失小，$p_+$ 较小但收益大，则 median 可以为负而期望为正。因此 `net_median < 0` 不足以删除结构。更重要的是 tail_share、CVaR 与 right-tail state identification。

#proposition("Median rejection fallacy", [
  对已扣成本收益 $Y$，$"median"(Y)<0$ 不蕴含 $E[Y]<=0$，也不蕴含策略不可用。若右尾可由 runtime-safe state 条件化识别，负 median 结构仍可能是正 EV candidate。
])

== Estimation failure modes

Entry-quality estimator 的主要失败机制包括：

- sample leakage：训练 label 包含当前或未来日期。
- bucket overfit：fine bucket 样本过小但未 shrink。
- class-action confusion：把 diagnostic class 当成交易规则。
- execution omission：只估 mid label，不估 strict taker net。
- tail under-reporting：只报告 mean，不报告 CVaR 与 worst entry。
- regime concentration：右尾集中在少数日。

#remark("机器学习不是首要答案", [
  机器学习模型可以作为估计器，但不能替代信息边界、控制变量、分布估计和执行分解。若基础 estimand 不清楚，更复杂的模型只会更快地学习泄漏或 regime artifact。
])

== 当前可用的专业判断

当前 entry estimation 支持三个谨慎结论。第一，entry-level quality 差异存在，不能把所有触发等权看待。第二，quality class 需要作为 sizing/admission 的输入，而不是直接删除结构。第三，右尾识别仍未完全解决，尤其是 fast release reversal 与 late continuation 的区分仍依赖 path-state 研究。

== 本章结论

Entry-quality 估计应输出分布性描述，而不只是一个均值。Shrinkage、CVaR、tail_share 与 as-of 训练是必要组件。现有 CCUSDT 证据支持 entry-level 质量差异存在，但 promotion 必须继续经过 runtime reconstruction、execution cost 与 capacity 检验。

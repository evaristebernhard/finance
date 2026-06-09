#import "../styles.typ": definition, assumption, proposition, remark, evidence

= 条件分布、Shrinkage 与 Tail Risk

本章建立 entry-level estimation 的数学语言。CCUSDT 样本存在小 bucket、右尾、路径依赖和 day regime，因此不能只看 naive bucket mean。

== 分层估计对象

令 $A$ 表示一个分组节点，例如 cell、cell+direction、cell+direction+quantile。目标是估计：

$ mu_A=E[Y|i in A] $

直接使用 $bar(r)_A$ 的问题是方差大，尤其当 $n_A$ 小或收益肥尾时。

#definition("Hierarchical shrinkage estimator", [
  给定节点 $A$ 与父节点 $pi(A)$，定义 $hat(mu)_A=lambda_A bar(r)_A+(1-lambda_A)hat(mu)_{pi(A)}$，其中 $lambda_A=n_A/(n_A+k)$。$k$ 是收缩强度。
])

直观上，样本多时相信本组，样本少时回到父层级。这个估计量不是为了复杂，而是为了抵抗 small-bucket selection bias。

从 bias-variance 角度看，$bar(r)_A$ 的方差近似随 $1/n_A$ 下降，但收益分布肥尾会使有效样本量小于名义样本量。Shrinkage 的作用是牺牲少量偏差，显著降低小 bucket 方差。若 $A$ 是 `cell+direction+quantile+day` 这样的细分节点，直接使用 $bar(r)_A$ 往往会把少数 outlier 当成稳定结构。

#proposition("Shrinkage is a risk control, not smoothing decoration", [
  当 $n_A$ 小且 $Y$ 具有肥尾时，$bar(r)_A$ 的均方误差可能高于向父节点收缩的估计量。因而 shrinkage 是 entry-quality estimation 的风险控制组件，而不是为了让表格更平滑。
])

== 分布估计而非均值估计

令 $Q_alpha(A)$ 为节点 $A$ 内收益的 $alpha$ 分位，$L_alpha(A)$ 为左尾均值：

$ Q_alpha(A)=inf {y: F_A(y)>=alpha} $

$ L_alpha(A)=E[Y | Y<=Q_alpha(A), i in A] $

若两个 bucket 具有相同均值，但一个 bucket 左尾更厚，另一个 bucket 右尾更集中，它们对策略的含义完全不同。短周期策略尤其如此，因为 exposure 与 leverage 会把 tail shape 放大。

#definition("Distributional entry estimate", [
  一个完整的 entry estimate 至少包含 $(hat(mu),hat(q)_10,hat(q)_50,hat(q)_90,hat("CVaR")_alpha,hat("tail_share")_q,n,n_"eff")$，并记录 day dispersion 和 worst-entry contribution。
])

这里 $n_"eff"$ 可以粗略理解为在自相关、同日集中和重叠 entry 后的有效样本量。若一天贡献了大部分右尾，名义 sample size 并不能代表稳定性。

== Entry quality class

Entry quality class 不是交易指令，而是估计摘要。一个 class 应至少记录：

- count 与 effective sample size。
- mean、median、CVaR。
- tail_share。
- day dispersion。
- worst entry。
- execution/capacity sensitivity。

#evidence("Entry estimation", [
  Entry estimation 报告中 active entries 约 1715，strict estimates 约 1665。`strong_positive` 有 252 entries，weighted mean 约 7.5693；`positive_right_tail_fragile` weighted mean 约 3.5521。`avoid_or_reduce` 是统计估计 class，不是证明结构无价值。
])

== Right-tail fragility

右尾结构的核心不是“每笔都赚钱”，而是少数大右尾是否可被 runtime-safe proxy 识别。如果识别不出来，策略可能只能承受全组噪音；如果识别出来，就可以控制 exposure 或 admission。

#remark("Tail-share 的双重含义", [
  高 tail_share 既可能是 convexity，也可能是 overfit outlier。必须结合跨日分布、case mechanism、matched controls 和 pressure sensitivity 判断。
])

右尾脆弱性可以写为：

$ "Fragility"_q = {sum_{i in "Top"_q} Y_i^+}/{sum_i Y_i^+ + epsilon} $

若 $"Fragility"_q$ 过高，并且 top entries 集中在单日或单一 case mechanism，则 promotion 应被延后。反之，若右尾来自多个日期、多个相似 path mechanism，且左尾可被 stopping rule 或 capacity clipping 控制，则 negative median 不应成为 rejection。

== CVaR 与杠杆

设 $Y_i=w_i R_i$ 为 exposure-weighted outcome。左尾风险随 $w_i$ 放大。若一个 cell 的 alpha mean 为正，但 CVaR 很差，应该首先问左尾来自：

- bad entry。
- fast release reversal。
- late decay。
- execution cost。
- over-sizing。

这比直接删除 cell 更有信息。

#assumption("Tail attribution before deletion", [
  删除一个 cell 或 factor family 前，应先把其左尾拆为 entry failure、release failure、decay failure、execution failure、capacity amplification。若主要问题是 exit 或 sizing，删除 entry factor 可能是错误归因。
])

== Day dispersion 与 regime concentration

设 day-level outcome 为 $Y_D=sum_{i in D}Y_i$。一个候选因子可以有正总收益，但集中在少数日：

$ "HHI" = sum_D (Y_D^+ / (sum_{D'} Y_{D'}^+ + epsilon))^2 $

高 HHI 表示右尾日集中。它不自动否定策略，但会降低 live confidence，因为未来不一定重复同一 regime。

#evidence("Right-tail and day evidence", [
  Entry estimation 报告中的 `positive_right_tail_fragile` weighted mean 仍为正，但名称已经提示：该类结构需要 tail_share、day dispersion 和 pressure sensitivity 共同判断，不能只看 mean。
])

== 本章结论

Entry quality estimation 必须从条件分布出发。Shrinkage 解决小样本，CVaR 描述左尾，tail_share 描述右尾集中，quality class 只是统计摘要。对 CCUSDT 主线而言，`net_median < 0` 不足以丢弃结构；关键是 right-tail 可识别性和 left-tail controllability。

#import "../styles.typ": definition, assumption, proposition, remark, evidence

= 因子失效机制 Taxonomy

本章把“失败因子”形式化。失败不是无用，它限制了理论空间，并防止后验 overfit。

== Failure 的四种含义

一个因子“效果不好”至少有四种不同含义：

- measurement failure：变量没有准确测量想要的市场对象。
- identification failure：变量有效果，但与 nuisance state 无法分开。
- runtime failure：变量依赖未来 label 或不可稳定在线重建。
- execution failure：mid edge 存在，但 strict fill 后被成本吞噬。

#definition("Factor failure", [
  因子失败是某个候选统计量在 measurement、identification、runtime、execution、capacity 或 tail 其中一层未通过 promotion gate。失败层不同，后续处理也不同：降级为 control、改估计量、延后 promotion、或彻底拒绝。
])

这一定义避免“均值低就删除”的粗暴做法。静态盘口可以失败为 alpha，但保留为 control；residual pressure 可以失败为单因子，但保留为 exhaustion component；oracle 可以作为 upper bound，但拒绝进入 runtime。

== Static snapshot failure

静态盘口因子失败机制：

- visible liquidity can cancel。
- snapshot lacks aggressive flow。
- high queue may be support or inventory defense。
- past price movement confounding。

因此静态 QI/OBI 不应作为主 direction alpha promoted，而应作为 control、condition 或 execution variable。

#evidence("QI/OBI status", [
  Static `obi_1` standalone direction evidence 弱，但 QI、depth 与 spread 仍对 execution、matching controls、vacuum/release 和 L2 depth fill 有价值。因此其状态应为 condition/control，而不是 promoted alpha。
])

== Vacuum failure

Low opposite depth 属于 release factor。其失效在于：

$ "low depth" -> "high impact conditional on flow" $

但不推出：

$ "low depth" -> "positive R60" $

#proposition("Vacuum does not imply continuation", [
  若后续 signed flow support 为零或 opposite liquidity rapidly refills，则 low opposite depth 可以提高 early MFE，同时不提高甚至降低 fixed-horizon return。
])

Vacuum 的专业表述是 denominator state：它放大给定 flow 的 price impact。若 numerator $X_t$ 不持续，或者 $Theta_t$ 很快因 refill 上升，vacuum 对 hold value 的解释会消失。

== Ratio failure

R5 ratio failure 来自 scale invariance：比例不识别 energy。解决方式不是删除 R5，而是拆解 Delta/Energy/Z，并在 matched controls 中检验。

== Threshold sensitivity failure

q60/q65/q70 是阈值，不是机制。降低 threshold 增加 recall，也增加 false positive 与 overfit 风险。当前 q65/q60 应视为 sensitivity，而非主线。

#remark("阈值不是解释", [
  若一个结果只能被表述为“q65 比 q70 历史收益更高”，而不能说明 q65 额外捕获了哪类机制，则该阈值不应 promoted。
])

== Residual pressure failure

Residual pressure alone 不稳，因为 post-release flow 可能是 continuation，也可能是 terminal chase。它必须与 path high、drawdown、time since peak、spread/depth 和 exhaustion 一起解释。

== Oracle failure

Oracle failure 是最危险的失败：结果看起来极好，但不可执行。所有使用 future MFE、future decay、future productive retrigger 的规则必须被标记为 diagnostic-only。

== Capacity failure

Capacity failure 指某个 cell 或 gamma 在 raw exposure 下有收益，但在 3x online FIFO clipping 后无法实现，或通过挤占更高质量 exposure 取得表面收益。该问题不是 alpha 强弱，而是 overlap allocator 问题。

#proposition("Capacity can reverse factor ranking", [
  若两个因子族在时间上高度重叠，则提高其中一个族的 requested exposure 会降低另一个族的 actual exposure。因而 raw total ranking 不一定等于 capacity-constrained ranking。
])

这解释了 `01_frames_only` 的历史误读。它作为全局 gamma 可能被优化器丢弃，但作为 idle-capacity sleeve 有正增量。失败的是容量角色设计，不一定是因子本身。

== Execution failure

Execution failure 指 mid-price label 为正，但 taker crossing、arrival quote movement、depth sweep 或 pressure 后 net edge 消失。对零显式 fee venue 也一样：fee 为零不代表 spread cost 为零。

#evidence("Fast vs strict gap", [
  当前 strict-taker 对齐后，fast mid edge 到 strict taker round-trip net 的差异主要来自 entry/exit spread 与 quote movement。该结果应被解释为 execution evidence，而不是直接否定 entry alpha。
])

== Promotion status vocabulary

本书使用以下状态词：

- promoted candidate：通过 runtime、matched-control、tail、execution、capacity 的候选。
- research candidate：机制明确，但证据或稳定性不足。
- diagnostic：只能解释机制或 upper bound，不能进 runtime。
- control/condition：非主 alpha，但可用于匹配、过滤或 sizing。
- rejected：机制、可测性或执行现实性不成立。

== 本章结论

失败因子应被降级而非遗忘：静态盘口降级为 control/execution，vacuum 降级为 release predictor，residual pressure 降级为 guard component，q60/q65 降级为 sensitivity，oracle 降级为 upper bound。

#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Part III：LOB 因子族与 TFI 主线

本章把订单簿原语转化为因子族，并解释为什么 dynamic order-flow 在 CCUSDT 上比 static snapshot 更接近可用方向信息。

== Static LOB factor family

静态 LOB 因子是当前订单簿状态函数：

$ X_t^"static"=g(B_t,A_t) $

包括 spread、top depth、25-level depth、QI、microprice、OBI 等。

#definition("Queue imbalance", [
  Top-level queue imbalance 定义为 $"QI"_t=(B_t-A_t)/(B_t+A_t+epsilon)$，其中 $B_t$ 与 $A_t$ 是选定层级上的 bid/ask depth。
])

QI 的机制是 visible queue asymmetry。但 visible queue 可以撤单，且不包含 aggressive flow，因此 standalone direction power 通常有限。

== Dynamic flow factor family

Dynamic flow 因子使用事件窗口：

$ "TFI"_t(W)=sum_{j in W(t)} sigma_j q_j $

其中 $sigma_j$ 是 trade sign，$q_j$ 是成交量。方向化版本为 $d_t "TFI"_t$。

#proposition("TFI 的机制定位", [
  TFI 是 price-impact numerator 的测度，而 depth 是 denominator 的测度。因此 TFI 主要解释 directional pressure，depth/vacuum 主要解释 release efficiency。
])

这个命题不是说 TFI 一定赚钱，而是说它在机制方程中的位置清楚：

$ "impact" approx "signed aggressive flow" / "opposite depth" $

== Trade sign、normalization 与 measurement error

TFI 的质量首先取决于 trade sign。理想情况下，交易所直接给出 aggressor side；否则需要用 price relative to quote、tick rule 或 L2 update 推断。令观测 sign 为 $hat(sigma)_j$，真实 sign 为 $sigma_j$，则 TFI measurement error 为：

$ eta_t=sum_{j in W(t)} (hat(sigma)_j-sigma_j) q_j $

若 sign error 与价格变化独立，主要增加噪声；若 sign error 在快速 release 阶段系统性偏向某一边，则会制造虚假 continuation 或虚假 reversal。

#assumption("Trade sign observability", [
  CCUSDT runtime TFI 应优先使用交易所可见的成交方向字段；若某数据源只能推断 aggressor side，必须在 feature manifest 中标记 sign inference method，并在 parity diagnostic 中报告 sign mismatch rate。
])

TFI 还需要 normalization。原始 $sum sigma q$ 对交易量尺度敏感；notional TFI、z-scored TFI、signed flow share 分别回答不同问题：

$ "TFI"^"notional"_t=sum_{j in W(t)} sigma_j p_j q_j $

$ "ShareTFI"_t={sum sigma_j q_j}/{sum q_j+epsilon} $

$ "ZTFI"_t={sum sigma_j q_j}/{sqrt(sum q_j^2+epsilon)} $

原始 TFI 更像冲击的数量；share TFI 更像方向纯度；ZTFI 更像强度调整后的 imbalance。若只看一个版本，很容易把高活动、强方向和大数量混为一谈。

#remark("TFI 不是单一因子", [
  `TFI` 至少包含窗口长度、成交量单位、normalization、方向化方式和更新 clock 五个设计选择。报告中必须写清楚是哪一个统计量，而不是只写 TFI。
])

== Depth、vacuum 与 Theta

Depth 不是方向预测器，而是 impact threshold。一个简化的局部模型可以写成：

$ r_{t,t+h}=d_t lambda_t (X_t-Theta_t)^+ + epsilon_t $

其中 $X_t$ 是方向化 flow strength，$Theta_t$ 是当时 liquidity/absorption threshold，$lambda_t$ 是 release efficiency。低 opposite depth 或 vacuum 可以降低 $Theta_t$，但如果 $X_t$ 很快衰竭，或者 refill 迅速发生，$R_{60}$ 仍可能很差。

#definition("Vacuum", [
  Vacuum 是低 opposite-side liquidity state。它测量给定主动流下的 release efficiency，而不测量未来主动流是否持续。因此 vacuum 属于 release factor 或 condition，不是 continuation factor。
])

#evidence("Core quantity form", [
  Core quantity estimation 报告把局部收益写成 $r=d lambda (X-Theta)^+ + epsilon$。这个形式说明需要同时估计 signal strength、threshold、release efficiency、cost 与 decay，不能只看单一 TFI 或单一 depth。
])

== OFI 与 MLOFI

OFI/MLOFI 介于 static stock 与 trade flow 之间。OFI 测量 top-level liquidity supply 的变化，MLOFI 扩展到多档：

$ "MLOFI"_t=sum_l w_l "OFI"_{t,l} $

它们可能解释 absorption、refill、liquidity wall shift，但也带来 book-reconstruction 和 collinearity 风险。

#remark("MLOFI 的当前定位", [
  MLOFI 具有机制意义，但不应在当前主线中抢占 TFI/R5+Q 的核心位置。它更适合成为 release/decay 或 execution sidecar，用 matched controls 检验增量。
])

更正式地，OFI 可以被视为 supply-side flow：

$ "OFI"_t = Delta q_t^b 1{Delta b_t>=0} - Delta q_t^a 1{Delta a_t<=0} + "price-level terms" $

多档 MLOFI 用 $w_l$ 把不同价差距离的 liquidity update 聚合。靠近 top-of-book 的 update 更直接影响 immediate fill 与 microprice；远端 update 更像 liquidity regime。权重 $w_l$ 因此不是纯技术参数，而是对 impact horizon 的建模选择。

== Factor family decomposition

当前 CCUSDT 因子族可以按测量对象分为五层：

- pressure numerator：TFI、rolling trade imbalance、signed notional flow。
- impact denominator：opposite depth、top depth、25-level depth、vacuum。
- supply dynamics：OFI、MLOFI、refill/cancel/add rate。
- state memory：R5/R10、Delta/Energy/Z、frames_since_mid_change。
- execution friction：spread、arrival quote movement、depth slippage。

#proposition("Static weakness does not imply LOB irrelevance", [
  若 static queue imbalance 对 direction label 弱，只能说明 visible stock 不是强 standalone alpha。它不能推出 depth、spread、OFI/MLOFI 在 release、execution、matched controls 或 exit guard 中无价值。
])

== 实证约束

#evidence("Static vs dynamic", [
  CCUSDT LOB report 显示 dynamic `trade_flow_imbalance` 对 `fwd_event_25_bps` 的 IC 约 0.2768、AUC 约 0.6217、top-bottom 约 2.8332bps。静态最佳 snapshot row `obi_1` 在 `fwd_time_60s_bps` 上 Spearman 约 0.0366、AUC 约 0.5094。该证据支持 dynamic flow > static queue 作为方向主线。
])

== 失效机制

TFI 的主要失效机制：

- late signal：成交确认发生在 price release 之后。
- absorption：aggressive flow 被 replenishing liquidity 吸收。
- release without continuation：TFI 触发 early MFE，但 60s label 被 decay 吞噬。
- event intensity confounding：高 TFI 可能只是高活动状态。

Static depth 的主要失效机制：

- visible depth 可撤。
- low depth 只说明 impact denominator 小，不说明 future flow 持续。
- high depth 可能是支撑，也可能是将被打穿的 liquidity。

== 本章结论

CCUSDT 当前证据支持以 dynamic signed flow 为 entry impulse 核心，以 depth/spread/L2 作为 condition、execution 和 release efficiency 变量。静态盘口不是无用，而是不应作为 standalone direction alpha promoted。

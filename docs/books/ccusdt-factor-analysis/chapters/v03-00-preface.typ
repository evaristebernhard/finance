#import "../styles.typ": definition, assumption, proposition, remark, evidence

= 序章：从因子解释到因子测度理论

本版的目标不是降低门槛，而是提高论证质量。订单簿基础仍然保留，但不再占据正文主线；正文从市场状态、信息集、因子统计量、未来路径泛函、估计对象和失效机制开始。读者如果尚未熟悉 bid/ask、maker/taker、depth、spread，可先读附录 A，再回到正文。

本书研究的问题可以表述为：在 Bullish `CCUSDT` 的 CEX 限价订单簿中，哪些由交易所可见事件生成的统计量，能够解释 entry quality、release speed、decay risk、execution cost 与 capacity overlap，并且在严格 runtime 信息边界下可被策略使用？

#definition("因子分析对象", [
  因子不是收益表中的列名，而是定义在市场信息集上的统计量。给定时刻 $t$ 的可见信息 $cal(F)_t$，一个 runtime-safe 因子必须满足 $X_t=f(cal(F)_t)$。未来收益、MFE、MAE、decay、oracle exit 和 PnL 是未来路径泛函，不属于 $cal(F)_t$。
])

这个定义把本书和普通“指标解释”区分开。我们并不关心某个字段是否在历史 CSV 中存在，而关心它是否是一个合法的、可解释的、可估计的、可复现的测度对象。`TFI` 测量 aggressive trade flow；`depth` 测量 price impact denominator；`frames_since_mid_change` 测量 mid staleness；`R5` 测量已关闭历史 entry 的 path-shape memory；`exhaustion` 测量 entry 后已发生路径中的衰竭状态。它们位于不同层级，不能互相替代。

== 本书的专业化改写

v0.2 的问题是语言过度教学化，数学对象被后置，导致书稿像入门讲义而不是专业因子研究专著。v0.3 采用以下结构：

- Part I：Market Microstructure Preliminaries。形式化定义订单簿状态、事件流、event time、clock time、filtration。
- Part II：Factor Measurement Theory。定义因子、label、matched-control estimand、conditional distribution、tail risk 和 runtime measurability。
- Part III：CCUSDT TFI Factor System。系统化 TFI、R5/R10、Delta/Energy/Z、frames、entry-quality shrinkage、release/decay、residual pressure、exhaustion、execution/capacity。
- Appendix：保留 v0.2 的基础概念解释，但降级为 beginner appendix。

#assumption("研究语境", [
  本书默认读者愿意接受基本条件期望、分布、估计量、收缩估计和 stopping time 的语言。对订单簿术语不熟悉不是问题；对数学建模语言完全回避，则不适合本书主线。
])

== 四类证据必须分离

短周期策略最容易混淆四类证据：

- alpha evidence：因子是否解释 mid path 或方向收益。
- execution evidence：crossing spread、depth slippage、latency 后是否还保留收益。
- capacity evidence：多个 entry 重叠时，实际 exposure 是否被 clipping。
- tail evidence：右尾是否真实，左尾是否可控。

把这四类证据混成一个 total，会导致错误诊断。比如 fast mid edge 被 strict taker execution cost 吃掉，并不自动说明 entry 因子无效；`1615412` 的 R60 很差，也不等于 `11_r5_frames` 没有 release edge；`01_frames_only` 作为主容量竞争者可能弱，但作为 idle-capacity sleeve 可能有正增量。

#proposition("总收益不可直接解释因子机制", [
  设策略收益可分解为 $Y_i = A_i - C_i - D_i + K_i$，其中 $A_i$ 表示 entry alpha component，$C_i$ 表示 execution cost，$D_i$ 表示 post-release decay，$K_i$ 表示 capacity/sizing contribution。仅观察 $Y_i$ 的均值或中位数，不能识别 $A_i$ 是否为正。
])

直观证明很简单：若 $A_i>0$ 但 $C_i+D_i$ 更大，则 $Y_i<0$；反之，若 $A_i$ 弱但 capacity 恰好避开左尾，总收益也可能为正。因子分析必须先定位每个变量解释的是 $A$、$C$、$D$ 还是 $K$。

== 本书的基本纪律

本书不把 `net_median < 0` 作为删除结构的充分条件。median 描述分布中位点，而右尾结构的价值取决于右尾可捕获性、左尾约束、capacity overlap 和 execution cost。一个 already cost-adjusted 的 net median 为负，可能只是说明多数 entry 小负；若少数右尾可由 runtime-safe 状态识别，结构仍有价值。

#remark("右尾结构的基本判断", [
  对 right-tail factor family，最低要求不是 median 为正，而是：右尾机制可解释、跨日不集中、left-tail 有 CVaR 约束、capacity 不把左尾放大、strict execution 后 edge 不被完全吞噬。
])

== 本书如何使用既有报告

本书引用既有 CCUSDT 报告作为 evidence layer，而不是把大表复制进正文。关键证据包括：LOB stylized factors、TFI factor decomposition、entry estimation、release/decay analysis、core quantity estimation、residual pressure diagnostic、exit wait decomposition、path casebook、leverage constrained optimization 等。所有引用路径集中在文末 evidence map。

#evidence("当前主要事实", [
  Dynamic `trade_flow_imbalance` 在 `fwd_event_25_bps` 上的 IC 约 0.2768、AUC 约 0.6217，明显强于静态盘口。`log_opp_depth25_quote` 对 early release 的 Spearman 约 -0.2998。`closed5_energy` 是强 metric spread 变量之一。`1615412` 在 4.7051s 达到 MFE +12.5612bps 后，R60 变为 -27.8923bps，是 release/decay+sizing 问题，而非简单 bad entry。
])

== 阅读路径

如果目标是理解机制，从第 1 章读到第 11 章。如果目标是查术语，先读附录 A。如果目标是继续研究，重点读第 3、4、7、8、10、11 章，因为它们定义了可执行因子与研究 label 的边界。


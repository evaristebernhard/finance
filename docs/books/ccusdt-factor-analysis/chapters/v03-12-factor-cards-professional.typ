#import "../styles.typ": definition, proposition, remark, evidence

= 核心因子卡片：测量对象、失效机制与 Runtime 边界

本章不是入门词典，而是专业研究卡片。每个因子按同一格式归档：定义、测量对象、估计对象、失效机制、runtime 边界。这样做的目的，是防止同一个变量在不同报告中被误当成 alpha、control、execution 或 label。

== TFI

#definition("TFI", [
  $ "TFI"_t(W)=sum_{j in W(t)} sigma_j q_j $，其中 $sigma_j$ 是 aggressor sign，$q_j$ 是成交数量或 quote notional。
])

测量对象：主动成交压力，即 price-impact numerator。估计对象：在控制 spread、depth、event intensity、past_event 和 cell 后，TFI quantile 对 future event-time 或 clock-time path 的条件分布影响。

失效机制：late signal、absorption、event intensity confounding、sign error、release 后 flow 不持续。Runtime 边界：只能使用已到达的 trade stream；不能使用未来成交、未来 price response 或同日后验 threshold。

#evidence("TFI status", [
  Dynamic `trade_flow_imbalance` 对 `fwd_event_25_bps` 的 IC 约 0.2768、AUC 约 0.6217，是当前 direction impulse 主线。
])

== Spread

定义：$s_t=(a_t-b_t)/m_t*10^4$。测量对象：立刻 crossing 的最小 friction。估计对象：entry admission、execution cost、matched-control liquidity state。

失效机制：若把 spread 当成 alpha，会混淆成本与方向；若 fast backtest 忽略 spread，会高估 taker net。Runtime 边界：spread 是 quote-visible state，可以 runtime-safe 使用，但不能用未来 exit spread 做 entry filter。

#proposition("Spread is not a fee", [
  Spread 是价格队列结构产生的 crossing cost，不是交易所显式 fee。$C_"fee"=0$ 不会移除 spread term。
])

== Depth 与 vacuum

Depth 测量可成交数量；vacuum 是 low opposite-depth state。测量对象：impact denominator 与 release efficiency。估计对象：给定 flow 下 early release probability，而不是 standalone continuation。

失效机制：低 depth 可能快速 refill；高 depth 可能撤单；visible depth 不代表 hidden liquidity 或未来 flow。Runtime 边界：top depth 来自 quote，multi-level depth 需要 L2 book builder；若 book reconstruction 不稳定，多档 depth 只能 diagnostic。

== QI

定义：$ "QI"=(B-A)/(B+A+epsilon)$。测量对象：visible queue asymmetry。估计对象：liquidity support、matched-control state、可能的 absorption condition。

失效机制：queue 可撤，且 QI 不包含 aggressive flow。当前 standalone alpha evidence 弱。Runtime 边界：可 runtime-safe，但更适合 control/condition，不适合作为主 direction alpha。

== OFI 与 MLOFI

OFI 测量 top-of-book supply change，MLOFI 聚合多档 liquidity update：

$ "MLOFI"_t=sum_l w_l "OFI"_{t,l} $

测量对象：流动性供给动态，包括 refill、cancel、add、wall shift。估计对象：absorption、release/decay、exit guard 和 depth fill condition。

失效机制：book update 噪声、price-level alignment、weight choice、与 TFI/depth 高共线。Runtime 边界：需要在线 L2 builder；不能从研究 panel 直接读后验 L2 summary。

== Frames since mid change

`frames_since_mid_change` 测量 mid staleness。估计对象：价格尚未更新的局部状态，以及与 R5/TFI 的 interaction。

失效机制：staleness 不是 alpha 本身。它可能表示 latent pressure，也可能表示无交易、低活动或报价僵滞。Runtime 边界：可由 quote stream 在线维护；threshold 必须 prior-date 或 prequential。

#remark("Frames 的正确位置", [
  frames 是 state condition，不是单独收益来源。它的价值通常来自与 R5、TFI、spread/depth 的 interaction。
])

== R5/R10

R5/R10 是 closed-entry path-shape memory：

$ R_{i,k}=P_{i,k}/(N_{i,k}+epsilon) $

测量对象：最近合法 closed entries 的路径形状。估计对象：局部环境是否处于有利 release/hold pattern。失效机制：ratio inflation、low energy、regime break、decision clock mismatch。Runtime 边界：只允许 $t_j+60s<t_i$ 的 closed entries。

== Delta、Energy、Z

定义：

$ Delta=P-N, quad E=P+N, quad Z=Delta/sqrt(E+epsilon) $

测量对象：净优势、路径活动总强度、能量调整后的净优势。估计对象：R5/R10 的质量分解。

失效机制：Z 不是严格正态统计量；Energy 高可能来自剧烈双向震荡，不一定是可交易趋势。Runtime 边界：与 R5 相同，必须来自 closed-entry state。

== Past-event movement

`past_event_25_bps` 测量 entry 前最近 event-time price move。测量对象：已发生的短期动量或释放。估计对象：控制候选因子是否只是复述刚发生的价格变化。

失效机制：若作为 alpha 直接使用，可能追逐已释放 move；若不作为 control，又会高估 TFI/frames 的增量。Runtime 边界：past_event 是 runtime-safe，因为它只使用过去事件；future_event 不是。

== Release

Release 是 entry 后有利路径高点：

$ H_i(T)=max_{0<u<=T}R_i(u) $

测量对象：signal 是否转化为 price movement。估计对象：early MFE、time-to-release、release probability。失效机制：release 可以很快回吐；不能等同 hold value。Runtime 边界：entry-time release 是 future label，只能训练/诊断；entry 后 running high 是 exit-state factor。

== Decay

Decay 是高点回吐：

$ D_i(T)=H_i(T)-R_i(T) $

测量对象：release 后收益未被保留的部分。估计对象：exit timing、hold risk、fixed-horizon label 的误差来源。失效机制：decay label 后验；不能作为 entry-time input。Runtime 边界：已发生 drawdown 可用于 stopping rule，未来 decay 不可用。

== Residual pressure

Residual pressure 试图测量 release 后剩余同向压力。测量对象：post-release continuation support。估计对象：wait value、hold guard、exit delay。

失效机制：单独不稳，可能把 terminal chase 当成 continuation。Runtime 边界：只可使用 release 后已经观察到的 flow、spread、depth 和 path state；不可使用未来 productive wait label。

== Exhaustion

Exhaustion 是 drawdown、flow decay、time since peak 和 support weakening 的组合。测量对象：release 后动能衰竭。估计对象：是否继续等待或提前退出。

失效机制：过度保守会 overcut right tail，尤其是多脉冲 continuation case。Runtime 边界：可作为 exit guard，不应作为 entry-time future label。

#evidence("Exhaustion status", [
  Residual-pressure diagnostic 显示 residual pressure alone 不稳；low exhaustion 更像 mid-continuation guard。当前状态是 research candidate，不是最终 exit policy。
])

== CVaR 与 tail_share

CVaR 测量左尾条件平均损失；tail_share 测量右尾收益集中度。测量对象：收益分布形状，而不是市场微观结构本身。估计对象：right-tail strategy 的可承受性。

失效机制：样本小、day concentration、outlier dominance。Runtime 边界：它们通常是 label summary，不是实时 signal；但历史估计可进入 sizing/admission，只要 prequential 生成。

== Capacity state

Capacity state 包含 open exposure、idle capacity、cell overlap、clipped/skipped legs。测量对象：组合层可用杠杆，而不是单笔 alpha。

失效机制：用 raw total 解释因子，忽略 concurrency；用 global downscale 替代 online allocator；让低质量 sleeve 挤占 core。Runtime 边界：capacity ledger 是 private state，必须在线维护，不能回看未来最大并发。

== 本章结论

因子卡片的目的不是增加术语，而是固定变量角色。TFI 是 pressure numerator；depth/vacuum 是 impact denominator；frames 是 staleness condition；R5/R10 是 path-memory；Delta/Energy/Z 是 ratio repair；release/decay 是 path label；residual pressure/exhaustion 是 exit-state research；CVaR/tail_share 是 distribution diagnostics；capacity state 是 portfolio constraint。只有角色清楚，策略优化才不会把不同层的问题混在一起。


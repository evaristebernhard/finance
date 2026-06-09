#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Part I：订单簿状态过程

本章形式化定义 CEX limit order book 的状态变量。目标不是写一个完整市场微观结构理论，而是给 CCUSDT 因子研究提供可复用的最小数学语言。

== 订单簿状态

令 $t$ 表示交易所事件时间或本地归并后的 observation time。订单簿状态可写为：

$ B_t = { (p_l^b, q_l^b) }_{l=1}^{L_t^b}, quad A_t = { (p_l^a, q_l^a) }_{l=1}^{L_t^a} $

其中 bid side 价格满足 $p_1^b >= p_2^b >= ...$，ask side 价格满足 $p_1^a <= p_2^a <= ...$。best bid 与 best ask 分别为：

$ b_t=p_1^b, quad a_t=p_1^a $

mid 与 spread 定义为：

$ m_t=(a_t+b_t)/2, quad s_t=(a_t-b_t)/m_t*10^4 $

#definition("LOB state", [
  CCUSDT 的可见 LOB state 是由 quote frame 与 L2 level updates 可重建的价格-数量序列。top-of-book state 只包含 $(b_t,q_t^b,a_t,q_t^a)$；depth-aware state 还包含多档 $(p_l,q_l)$。
])

这个定义直接决定哪些因子可 runtime。`spread`、top depth、mid change 来自 top-of-book；multi-level depth、QI、OFI/MLOFI、depth sweep fill 需要 L2 book builder。若没有 L2 或 book reconstruction 不稳定，多档因子只能降级为 offline diagnostic。

== Spread、Depth 与成交边界

Spread 是最基本的 executable friction。若策略以 taker buy 入场，价格不是 $m_t$，而是 $a_t$ 或更高；若以 taker sell 入场，价格是 $b_t$ 或更低。top-of-book crossing cost 近似为 half spread：

$ C_t^"entry" approx s_t/2 $

若订单数量超过 best level depth，则需要 depth sweep。令做多订单数量为 $Q$，ask side cumulative depth 为：

$ D_t^a(p)=sum_{l:p_l^a<=p} q_l^a $

fill price 是满足 $D_t^a(p)>=Q$ 的价格区间上的 VWAP。这个对象是 execution model，而不是 alpha 因子。

#proposition("零手续费不推出零执行成本", [
  即使 $C_"fee"=0$，taker round-trip 的 expected crossing cost 通常不为零。若 entry 与 exit 均使用 top-of-book taker，且 depth slippage 与 latency 忽略，round-trip crossing cost 近似为 $(s_"entry"+s_"exit")/2$。
])

这解释了为什么 fast mid-edge 与 strict taker net 会明显不同。Bullish 上显式 fee 为零时，仍必须把 spread、arrival quote movement、depth slippage 和 adverse selection 作为独立成本源记录。

== Static state 与 dynamic state

静态盘口因子是 $g(B_t,A_t)$，例如 QI、spread、depth。动态 order-flow 因子是事件窗口上的统计量，例如 TFI、OFI、MLOFI：

$ X_t^"dyn" = h( e_{t-k+1}, ..., e_t ) $

其中 $e_t$ 是 trade 或 book update event。

#remark("静态盘口的识别限制", [
  静态 LOB snapshot 描述 visible liquidity stock，而非未来 aggressive flow。它可以解释 impact denominator 和 execution condition，但作为 standalone direction predictor 通常较弱。
])

#evidence("CCUSDT LOB stylized facts", [
  Median daily median spread 约 2.0050bps；median p05 top depth quote 约 7.1607；median 25-level depth quote 约 3843.3042。静态 `obi_1` 在 `fwd_time_60s_bps` 上 Spearman 约 0.0366、AUC 约 0.5094，弱于 dynamic trade-flow factor。
])

== Event time 与 clock time

微观结构研究至少有两个时间尺度。Clock time 用秒定义 horizon，例如 $R_i(60s)$；event time 用事件个数定义 horizon，例如 `fwd_event_25_bps`。它们的差异不是实现细节，而是估计对象差异。

若市场活跃，25 个事件可能发生在很短时间内；若市场冷清，同样 25 个事件可能跨越更长时间。event-time label 更接近 immediate microstructure response，clock-time label 更接近持仓暴露和 decay risk。

#definition("Path functional", [
  给定 entry time $t_i$ 与方向 $d_i$，clock-time path 定义为 $R_i(u)=d_i(m_{t_i+u}-m_{t_i})/m_{t_i}*10^4$。Event-time path 则把 $u$ 替换为事件索引增量。两类 path functional 不可混用。
])

== 本章结论

订单簿状态过程给出三个基本约束：第一，mid 是研究价格，不是成交价格；第二，depth 是 impact denominator，但不是 continuation guarantee；第三，event-time 与 clock-time label 估计的不是同一个对象。后续所有因子必须说明自己是 top-of-book、multi-level book、trade-flow、path state 还是 execution state 的函数。


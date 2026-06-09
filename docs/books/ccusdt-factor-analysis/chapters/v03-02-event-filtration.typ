#import "../styles.typ": definition, assumption, proposition, remark, evidence

= 事件流、Filtration 与 Runtime 可测性

本章给出本书最重要的形式化边界：因子必须是当时信息集的可测函数，未来路径变量只能作为 label 或 diagnostic。

== 市场事件流

令 $e_n$ 表示按本地时间归并后的第 $n$ 个 market event。事件类型包括：

- quote frame：best bid/ask 与数量。
- trade event：成交价格、数量、方向。
- L2 update：某个价格层级的数量更新。
- private event：order ack/reject、fill、portfolio update。

定义事件 filtration：

$ cal(F)_n^"mkt" = sigma(e_1^"mkt", ..., e_n^"mkt") $

$ cal(F)_n^"bot" = cal(F)_n^"mkt" union cal(F)_n^"private" union cal(S)_n^"bot" $

其中 $cal(S)_n^"bot"$ 是 bot 自己在线维护的状态，例如 rolling TFI、frames、closed-entry R5 state、open exposure。

#definition("Runtime-safe factor", [
  因子 $X_n$ 称为 runtime-safe，当且仅当存在函数 $f$ 使 $X_n=f(cal(F)_n^"bot")$。若 $X_n$ 依赖 $e_{n+k}$、未来 mid、未来 fill、未来 MFE/MAE 或未来 PnL，则不是 runtime-safe。
])

== Label 的不可测性

未来收益是路径泛函：

$ R_{n,T}=d_n(m_{n+T}-m_n)/m_n*10^4 $

MFE 与 decay 是：

$ H_n(T)=max_{0<u<=T} R_n(u), quad D_n(T)=H_n(T)-R_n(T) $

在 entry time $n$，这些对象依赖未来 mid path，因此通常不属于 $cal(F)_n$。

#proposition("Future label 不满足 entry-time 可测性", [
  若存在 $u>0$ 使 $m_{n+u}$ 不是 $cal(F)_n$ 可测，则 $R_{n,T}$、$H_n(T)$、$D_n(T)$ 不是 $cal(F)_n$ 可测。因此它们不能作为 entry-time runtime input。
])

证明思路：$R_{n,T}$ 是 $m_{n+T}$ 的非平凡函数；$H_n(T)$ 和 $D_n(T)$ 依赖整个未来路径。除非未来价格在 $cal(F)_n$ 下退化为已知常数，否则这些变量不可在 entry time 观察。

#remark("诊断与策略输入的分离", [
  不可测不等于无用。Future labels 是训练、诊断、验收、casebook 分类和 oracle upper bound 的核心对象；它们只是不能进入 runtime signal。
])

== Decision clock

一个策略不仅由因子值决定，也由何时评估决定。旧四象限研究有固定 panel decision clock；若 runtime bot 在每个 trade event 上评估，就会产生新的策略族。因此每个 intent 必须绑定 observed event：

$ "intent"_i = (n_i, t_i, X_{n_i}, pi, theta) $

其中 $n_i$ 是 observed sequence，$X_{n_i}$ 是当时 feature snapshot，$pi$ 是 policy profile，$theta$ 是参数。

#assumption("Decision-frame equivalence", [
  从旧 panel 迁移到 runtime bot 时，必须先证明 online decision_frame 与 reference panel 在 timestamp、cell、side、weight、feature snapshot 上等价。否则 PnL 差异无法归因于 execution。
])

== Latency 与 arrival observation

若 deterministic latency profile 给定延迟 $ell$，order arrival time 定义为：

$ t_i^"arr" = t_i^"obs" + ell $

arrival quote 必须由 canonical market stream 唯一确定，例如 first local timestamp greater-or-equal target 或 last-known-book rule。wall/bridge timing 不得影响 deterministic replay 的 fill price。

== 本章结论

Runtime-safe 是因子能否进入策略的必要条件。`TFI`、spread、depth、frames、prequential R5 可以成为 runtime-safe 因子；future return、MFE、decay、path class、oracle exit 只能是 label 或 diagnostic。这个边界比任何回测收益数字都更基础。

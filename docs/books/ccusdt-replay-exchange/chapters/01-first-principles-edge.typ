= 从第一性原理定义 edge

== 问题

在 CCUSDT 的 TFI 研究里，最容易犯的错误是把一个固定持有期的结果当成策略本身。比如一笔 entry 在 5 秒内已经有明显正向 release，但 60 秒后回落为负。如果只看 60 秒 terminal label，它会被误读成 bad entry；但从交易角度看，它可能是 good entry 加 bad exit。

因此第一性原理不是问：

```text
60 秒后是否为正？
```

而是问：

```text
给定当时可见信息，是否存在一个可执行的进入、退出和风险控制，使成本后收益为正？
```

== 路径收益

对第 $i$ 笔候选 entry，令方向为 $s_i in {-1, +1}$，中间价为 $M_t$。最基本的 signed mid path 是：

$
R_i(tau) = s_i 10^4 log(M_(t_i + tau) / M_(t_i)).
$

固定 60 秒收益只是路径上的一个点：

$
y_i(60) = R_i(60) - C_i.
$

真正的路径对象至少要包含峰值和回撤：

$
H_i(h) = max_(0 < u <= h) R_i(u),
$

$
D_i(h) = H_i(h) - R_i(h).
$

所以核心分解是：

```text
entry edge -> release -> post-release decay
```

而不是：

```text
entry score -> 60s PnL
```

这就是 1615412 这个事故必须一直放在手边的原因。它的 MFE 在 4.7051 秒达到约 `+12.5612bps`，但 60 秒时约为 `-27.8923bps`。如果 exposure 是 `8`，这个固定持有期错误会放大成约 `-242.4` 的 PnL 单位。

== 成本不是手续费

当前 venue fee baseline 可以是：

$
C_("fee", i) = 0.
$

但零手续费不等于零成本。真实可执行目标应写成：

$
y_i(c) = R_i(tau_i^"exit") - C_("fee", i) - c,
$

其中 $c > 0$ 是压力项，代表 spread crossing、fill uncertainty、latency、adverse selection 和 post-release decay 的保守预算。

这也是为什么「C=0 之后策略有利润」不能直接等价为「实盘可以按 mid 收益捕获」。Taker entry/exit 会把 mid edge 拆成：

```text
alpha movement
- entry crossing
- exit crossing
- latency / depth / pressure
```

== 停时视角

退出不是固定时间标签，而是一个停时问题。令当前退出 decision time 为 $t$，等待 $tau$ 后 crossing 的增量为：

$
W_t(tau) = Y^T_(t + tau) - Y^T_t.
$

最新 wait-value decomposition 把它精确拆成：

$
W_t(tau)
= q 10^4 log(m_(t + tau) / m_t)
+ (kappa_t - kappa_(t + tau))
+ epsilon_t.
$

其中第一项是 mid continuation，第二项是 crossing/spread improvement。当前选中的 wait overlay 总计 `+68.3173` weighted bp-units，其中 `+47.3169` 来自 mid continuation，`+21.0004` 来自 crossing 改善。这说明当前等待收益主要不是「spread 等窄一点」，而是「低 exhaustion 时 mid 还没有死」。

== 工程映射

第一性原理最终要落到系统对象：

```text
R_i(tau)        -> path label / diagnostic only
H_i, D_i        -> release/decay diagnostic
W_t(tau)        -> exit controller diagnostic
C_fee, c        -> fee profile / pressure profile
entry/exit cost -> fast-vs-strict attribution
tau_i^exit      -> exit_profile
```

策略 runtime 不能读取未来路径、MFE、MAE、PnL label。它只能读取 exchange-visible stream 或 market-derived cache，在当时构造 feature state，再发出 intent。

== 当前证据

当前工作区已经形成几个稳固事实。

- 60 秒 label 会混淆 release 和 decay。
- `net_median < 0` 不能作为丢弃结构的理由，因为右尾与容量/退出管理仍可能有价值。
- Taker execution cost 很真实；zero fee 只消除显式手续费，不消除 spread。
- 退出 wait overlay 的收益主要来自 mid continuation，其次才是 crossing 改善。
- 高 exhaustion bucket 的 wait 往往继承 adverse mid movement，而不是获得 spread recovery。

== 未解决问题

第一章结束时，真正的问题还没有解决：

```text
如何用 runtime-safe state 判断 release 是否还在继续？
如何把 exit controller 接入 strict Runner order lifecycle？
如何在 3x 杠杆和重叠信号下分配 exposure？
如何区分可执行 edge 和 mid-only illusion？
```

后续章节就是围绕这些问题展开。


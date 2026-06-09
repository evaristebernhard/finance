= 因子语言与 Python 研究循环

== 问题

因子不是策略。因子是把微观结构状态压缩成可讨论、可检验、可迁移的语言。CCUSDT 这条线的核心教训是：如果因子直接在旧 fixed panel 或未来 label 上成立，但在线 Bot 无法从 exchange-visible events 还原，那么它不能进入 runtime。

因此本章的核心边界是：

```text
offline diagnostic 可以读 label
runtime strategy 只能读 market/private stream
```

== TFI 与四象限

当前主结构围绕两个二值状态展开：

$
A_t = I("R5"_t > 1),
$

$
B_t = I(F_t >= Q),
$

其中 $"R5"$ 是 prequential 的最近已关闭 entry 形态比，$F_t$ 是 `frames_since_mid_change`，$Q$ 通常取 prior-safe high quantile。二者形成四个互斥 cell：

```text
00_none
10_r5_only
01_frames_only
11_r5_frames
```

最初容易误解的是：`R5` 不是万能质量分。它更像 path shape ratio。更稳妥的拆法是：

$
Delta_k = P_k - N_k,
$

$
E_k = P_k + N_k,
$

$
Z_k = Delta_k / sqrt(E_k + epsilon).
$

这里 $Delta$ 表示方向性，$E$ 表示证据量，$Z$ 表示标准化强度。只用 ratio 很容易在分母小、样本少、状态稀疏时制造错觉。

== Python 研究循环

Python 在本项目里不是为了替代交易内核，而是为了快速建立研究回路：

```text
canonical data
  -> decision_frame cache
  -> offline diagnostic
  -> candidate rule
  -> fast backtest
  -> strict replay audit
```

这个循环的优点是快，缺点是容易偷看未来。因此每个 Python diagnostic 都必须标清字段角色：

```text
runtime-safe feature
post-trade diagnostic label
future/oracle label
profile/config metadata
```

如果一个字段只能在 entry 之后知道，它可以出现在报告里，但不能成为 Bot 的输入。

== Panel 与 Online 的差别

旧 fixed factor panel 的价值是让研究开始，但它不是实盘接口。真正的在线策略必须从：

```text
market_quote
market_trade
optional market_l2_update
account_snapshot
order_ack / fill
```

还原 feature state。

这就是 `decision_frame_v1` 的作用：它是 market-derived 的中间层，既能支持 fast backtest，也能作为 online builder 的 parity target。它不能包含 future label、PnL、MFE、MAE 或 scored entries。

从数学上说，panel row 和 online state 的区别是 filtrations：

$
X_t in F_t
$

才允许进入 runtime。若某个变量依赖 $t + tau$ 之后的信息，则它属于：

$
F_(t + tau) - F_t,
$

只能作为 label 或验收指标。

== 当前因子教训

当前因子研究已经给出几个清楚结论。

第一，静态盘口不会单独给出强 edge。动态 order-flow、TFI、MLOFI、release/decay 才是主要解释方向。

第二，`01_frames_only` 不是天然无用。它在高并发全局 gamma 模型里会被挤掉，但在 3x 杠杆约束下，如果作为 idle-capacity sleeve，可以用剩余容量而不显著挤占 core。

第三，`net_median` 为负不能直接扔。当前分支的目标不是只吃中位数，而是识别右尾、控制左尾、处理容量和退出。

第四，watcher 和 post-exit re-trigger 不能反过来证明第一次 exit 错了。它只说明自然退出之后，是否出现新的 runtime-safe 触发机会。

== 工程映射

因子研究对应的工程层如下：

```text
factor formula       -> Python diagnostic
runtime-safe subset  -> online feature state
decision_frame       -> cache + parity target
shadow policy        -> Bot-owned lifecycle
R5                   -> persisted closed-entry state
cell membership      -> capacity allocator input
```

Python 策略 Bot 的责任不是读取研究结果，而是在线维护状态机。Runner 的责任不是算 TFI，而是保证市场事件、订单、成交、portfolio 的因果链真实。

== 未解决问题

下一步因子研究应该更少追求复杂表达式，更重视状态解释。

```text
残余压力是否真的预测 continuation？
exhaustion 是否能 runtime-safe 地过滤 bad wait？
entry spread q70 是否只是执行保护，还是隐含状态选择？
L2 summary 应该以什么形式进入 Bot，而不泄漏未来？
```

这几个问题不该只靠新因子命名解决，而要通过 fast/strict 双轨回测和 prior-date rule 检验。

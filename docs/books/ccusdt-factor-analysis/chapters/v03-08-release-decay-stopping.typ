#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Release、Decay 与 Stopping-Time Formulation

本章形式化 fixed-horizon label 的局限，并把 exit/hold 问题写成 stopping-time 问题。

== Path functionals

对 entry $i$，方向化 path：

$ R_i(u)=d_i(m_{t_i+u}-m_{t_i})/m_{t_i}*10^4 $

定义：

$ H_i(T)=max_{0<u<=T} R_i(u) $

$ L_i(T)=min_{0<u<=T} R_i(u) $

$ D_i(T)=H_i(T)-R_i(T) $

其中 $H$ 是 MFE，$L$ 是 MAE，$D$ 是 decay。

#definition("Release and decay", [
  Release 描述 entry signal 是否转化为有利路径高点；decay 描述高点到 horizon 的回吐。它们是 future path labels，但 entry 后已发生的 partial path 可成为 exit-state factor。
])

还可以定义 release time：

$ tau_i^H(h)=inf {u>0: R_i(u)>=h} $

若该集合为空，则 $tau_i^H(h)=infinity$。这个对象回答“达到某个有利阈值需要多快”。对于 fast release reversal，$tau_i^H(h)$ 很小，但 $D_i(T)$ 很大；对于 no_release_flat，$tau_i^H(h)$ 可能不存在；对于 late_release_collapse，$tau_i^H(h)$ 较晚且终点回吐。

== Fixed-horizon 混淆

固定 horizon label $R_i(60)$ 同时包含 entry signal、release speed、hold value、decay risk 与 execution profile。若 $H_i(10)$ 很高但 $R_i(60)$ 很低，固定 label 会把一个可释放 entry 判为失败。

#evidence("Release/decay statistics", [
  Release/decay 报告中，1455 个 rebuilt path entries 的 mean MFE5 约 2.5668bps，MFE10 约 3.6668bps，MFE60 约 9.9293bps；mean R60 约 4.2577bps，mean decay60 约 5.6716bps。这说明市场经常给过更高路径值，但 fixed60 不一定保留。
])

== 1615412 case

`2026-05-09 / entry_row=1615412 / 11_r5_frames / short` 在 4.7051s 达到 MFE +12.5612bps，R60 为 -27.8923bps，decay60 约 40.4535bps。exposure=8 时 target PnL 约 -242.4187。

该 case 的机制解释是：entry early release 存在；失败来自 release/decay + sizing，而不是简单 bad entry。

#proposition("Fast release reversal is not an entry-only failure", [
  若存在 $u<T$ 使 $H_i(u)>h$，但 $R_i(T)<0$ 且 $D_i(T)$ 很大，则该 entry 同时包含成功的 release component 和失败的 hold/exit component。用 $R_i(T)$ 单独标记 bad entry 会产生机制误分类。
])

这也是 path-first 主线的核心。我们不是否认 fixed60 label，而是说 fixed60 是多个机制的投影。投影可以用于统一比较，但不能作为唯一解释。

== Stopping time

Exit rule 必须是 stopping time：

$ {tau_i <= u} in cal(F)_{t_i+u} $

Oracle exit：

$ tau_i^*="arg max"_{0<u<=T} R_i(u) $

不是 stopping time，因为依赖未来路径。

#proposition("Oracle upper bound 与 runtime rule 的分离", [
  若 exit rule 使用 $max_{0<u<=T} R_i(u)$ 或 future productive label，则它只能作为 upper bound diagnostic，不能作为 runtime strategy。合法 exit manager 必须只使用已发生的 $H_i(u)$、drawdown、flow、spread、depth 与 private state。
])

== Candidate stopping families

当前适合研究的小停时族包括：

- fixed horizon：$tau=T$，作为 baseline。
- left-tail cap：若 $R_i(u)<=-a$ 则退出。
- peak drawdown：若 $H_i(u)>=h$ 且 $H_i(u)-R_i(u)>=d(H_i(u))$ 则退出。
- flow-confirmed hold：若 release 后 signed flow 与 queue support 仍同向，则延迟退出。
- exhaustion guard：若 drawdown、time since peak 和 flow decay 同时高，则退出或不等待。

这些规则必须只使用 entry 后已经发生的路径。`H_i(u)` 在时刻 $t_i+u$ 是可见的；$H_i(T)$ 在 entry time 不可见。这个差异是 stopping-time 建模的全部关键。

#definition("Path-state factor", [
  Path-state factor 是 entry 之后、当前时刻之前可观察的路径统计量，例如 current PnL、running high $H_i(u)$、drawdown $H_i(u)-R_i(u)$、time since peak、post-release flow、post-release spread/depth。它可以用于 exit，不可以用于 entry-time label 泄漏。
])

== Residual pressure 与 exhaustion

Residual pressure 试图测量 release 后剩余方向力，但单独不稳。Exhaustion 更接近 hold guard：

$ X_{i,u}^"exh" approx D_i(u)/(H_i(u)+1"bp") - P_{i,u}^"support" $

其中 $P^"support"$ 可由 post-release signed flow 或 queue support 表示。

#evidence("Exhaustion evidence", [
  Residual pressure diagnostic 中，pressure panel rows 约 9856，long panel 约 49280。Residual pressure alone 不稳定；low exhaustion q1 在 OOS prior-bin fixed30 TTL=5 中 total 约 +56.4968，high exhaustion q5 约 -72.8069。Exit wait decomposition 中 selected wait overlay total 约 +68.3173，mid component +47.3169。
])

== Path casebook as mechanism labels

Path casebook 将 entries 分为 non_case、no_release_flat、fast_release_reversal、large_release_plateau_decay、late_release_collapse 等。这些类别不是策略输入，而是机制标签。它们回答：

- 是否发生 release。
- release 是否过快回落。
- 是否出现 plateau 后 decay。
- 是否存在 late continuation。
- fixed horizon 的失败来自 entry 还是 exit。

#evidence("Path casebook distribution", [
  Path casebook 报告中，1455 entries 里 non_case 738、no_release_flat 558、fast_release_reversal 41、large_release_plateau_decay 25、late_release_collapse 93。分类本身包括 profitable entries，因此 case 不是 losing label。
])

== Watcher 的严格位置

Post-exit watcher 只回答一个问题：自然退出后，是否出现新的 runtime-safe 触发，允许重新入场。它不能被解释为“第一次退出错了”。如果 watcher 用的是 exit 后 5s 内已经观察到的 flow、queue 和 reclaim，它是新的 entry condition；如果用 future profitable retrigger label，它就是 oracle。

#evidence("Post-exit watcher", [
  q70 cleaner watcher 有 3 个 triggers，weighted final 约 +522.1939，negative triggers 0；q65 有 5 个 triggers，weighted final 约 +803.2748。当前结论是 q70 更干净，q65 是 sensitivity，不是 live-ready promotion。
])

== 失效机制

Path manager 的主要风险是 overcut right tail。`2583437` 是典型：dormant vacuum -> first release -> drawdown/reset -> multi-pulse continuation。简单 drawdown exit 会错过后续右尾。因此 stopping rule 必须同时报告 rescue cases 与 overcut cases。

== 本章结论

Release/decay 分解将 entry alpha 与 exit timing 分开。合法 exit 是 stopping time；oracle 只能诊断。Low opposite depth 解释 release，sustained flow 与 exhaustion 更接近 continuation/hold value。

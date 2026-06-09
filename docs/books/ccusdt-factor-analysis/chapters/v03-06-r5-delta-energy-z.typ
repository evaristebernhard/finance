#import "../styles.typ": definition, assumption, proposition, remark, evidence

= R5/R10、Delta/Energy/Z 与 Path-Shape Memory

本章形式化当前主线中的 R5/R10。核心结论是：R5 是 shape ratio，不是 quality score；必须拆解为 direction、energy 与 standardized imbalance。

== Prequential R5

令 $cal(I)_i$ 为 entry $i$ 之前已经关闭的历史 entry 集合。若 label horizon 为 60s，则合法历史集合必须满足：

$ cal(I)_i={j: t_j+60s < t_i} $

定义最近 $k$ 个合法 closed entries 的有利 mass 与不利 mass：

$ P_{i,k}=sum_{j in "last-k"(cal(I)_i)} P_j, quad N_{i,k}=sum_{j in "last-k"(cal(I)_i)} N_j $

Rk 为：

$ R_{i,k}=P_{i,k}/(N_{i,k}+epsilon) $

#definition("Prequential shape ratio", [
  $R_{i,k}$ 是 entry $i$ 时刻由已关闭历史 entry 生成的 path-shape ratio。若使用尚未 closed 的 entry 或同日未来 entry，则该变量不满足 runtime measurability。
])

一个严格在线实现只需要维护 closed-entry 队列。每当 entry $j$ 到达 $t_j+60s$ 后，其 path mass 才进入候选队列；当 entry $i$ 触发时，从队列尾部取最近 $k$ 个 closed entries 计算 $P,N,Delta,E,Z$。这意味着 R5 的更新时间不是每个 market event，而是每个 entry close event。

#proposition("R5 clock is a closed-entry clock", [
  R5/R10 的合法更新 clock 由 entry closure 决定，而不是 market-event clock。若 market stream 已经推进到 $t_i$，但某个历史 entry 的 60s horizon 尚未结束，则该 entry 不能贡献给 $R_{i,k}$。
])

这个命题解释了为什么“翻译旧策略”会产生新的策略族：若 runtime bot 在每个 trade event 上重算并触发，而旧研究只在 fixed panel decision clock 上触发，两者不仅触发次数不同，R5 state 的更新点也可能不同。

== Ratio 的不可识别性

比例隐藏规模。$P=2,N=1$ 与 $P=200,N=100$ 都给出近似 $R=2$，但前者统计厚度极低，后者表示强 path energy。仅使用 ratio 会把 low-energy noise 与 high-energy regime 混为同一状态。

#proposition("Rk 不识别 path energy", [
  对任意 $c>0$，$(P,N)$ 与 $(c P,c N)$ 给出相同 $R=P/(N+epsilon)$ 的近似值，但二者的估计方差与 regime 含义不同。因此 $R$ 不能单独作为质量测度。
])

更严重的是，当 $N$ 接近零时，R 会爆炸。若 $P=1,N=0.05$，R 约为 20，但绝对 path mass 很低；若 $P=12,N=6$，R 只有 2，却可能代表更稳定的局部环境。此时 ratio 最高的 entry 不一定质量最高。

#remark("Ratio inflation", [
  R5 的高值可能来自两种机制：真实净优势增加，或 denominator 过小。只有结合 $Delta$、$E$、$Z$，才能区分 high-quality memory 与 low-energy ratio inflation。
])

== Delta、Energy、Z

定义：

$ Delta_{i,k}=P_{i,k}-N_{i,k} $

$ E_{i,k}=P_{i,k}+N_{i,k} $

$ Z_{i,k}=Delta_{i,k}/sqrt(E_{i,k}+epsilon) $

Delta 测量净优势；Energy 测量 path 活动总强度；Z 测量能量调整后的净优势。三者合起来比 Rk 更适合解释“最近局部环境是否真的有可用形状记忆”。

#remark("Z 的解释边界", [
  $Z_k$ 不是正态假设下的严格 z-statistic。微观结构收益具有肥尾、自相关和 regime dependence。这里的 $sqrt(E)$ 标准化只是一种尺度修正。
])

== R5 与 R10 的差异

R5 更短，反应快，但方差高；R10 更稳，但更容易混合 regime。可以把二者写成同一历史核的不同 bandwidth：

$ M_{i,k}=sum_{r=1}^k omega_{r,k} V_{i-r} $

其中 $V_j$ 是 closed-entry path statistic，R5 相当于窄核，R10 相当于宽核。若局部 regime 半衰期短，R10 会滞后；若 regime 噪声大，R5 会过度反应。

#definition("Path-memory bandwidth", [
  $k$ 是 path-memory bandwidth。小 $k$ 提高适应速度，降低统计稳定性；大 $k$ 提高稳定性，降低 regime responsiveness。R5/R10 的比较应被解释为 bandwidth trade-off，而不是谁天然更优。
])

实际研究中，R5/R10 应与 event intensity 和 day regime 一起看。若一天中的 entry 非常密集，最近 5 个 closed entries 可能只覆盖很短 clock time；若 entry 稀疏，R5 可能跨越较长市场状态。这个差异会影响 R5 的金融含义。

== 与 frames 的交互

四象限定义：

$ A_i=1{R_{i,5}>1}, quad B_i=1{F_i>=q_90} $

其中 $F_i$ 是 `frames_since_mid_change`。四个互斥 cell 为 `00_none`、`10_r5_only`、`01_frames_only`、`11_r5_frames`。

金融解释：

- `10`：path-shape memory 支持，但没有 high staleness。
- `01`：high staleness，但 path memory 不支持。
- `11`：path-shape memory 与 staleness 同时支持。
- `00`：baseline，不等于无价值。

#evidence("Four-cell decomposition", [
  TFI factor decomposition 报告中，`11_r5_frames` mean 约 5.1410、total 约 5850.4711；`10_r5_only` mean 约 1.8514；`01_frames_only` mean 约 1.7760。`closed5_energy` metric spread 约 10.2597bps，支持将 R5 拆成 ratio 与 energy 维度。
])

== Gamma 与 cell value 的区别

四象限策略中的 $gamma$ 是 sizing coefficient，而不是 cell alpha 的定义。若在 3x capacity 下直接提高某个 gamma，收益变化可能来自三件事：

- 该 cell 的单位 exposure payoff 更高。
- 它挤占了其他 cell 的 capacity。
- 它改变了左尾 exposure 的时间重叠。

因此，gamma 搜索结果不能直接解释为“该因子更强”。对于 `01_frames_only`，早期全局 gamma 会在高并发状态中与 core cell 竞争，导致它被优化目标丢掉；idle-capacity sleeve 的重定义表明，`01` 在不挤占 core 时仍可能有增量。

#evidence("Idle sleeve interpretation", [
  Leverage-constrained optimization 报告显示，`01_frames_only` 作为 idle-capacity sleeve 时，历史 C=0 从 core-only 6038.2000 提升到 `idle01_g1_r0` 6907.5648；2026-05-18 OOS 从 415.8276 提升到 472.5926。该结果说明 capacity role 改变了因子解释。
])

== 失效机制

R5 family 的失效机制包括：

- low-energy ratio inflation。
- recent closed entries 与当前 regime 断裂。
- prequential state 更新错误导致 leakage。
- cell-level mean 被 exit/capacity/execution 混淆。
- high `11` exposure 放大 release/decay 左尾。

`1615412` 是关键反例：它属于 `11_r5_frames`，早期 MFE 强，但固定 60s 结果极差。该 case 不能证明 `11` entry 没有 alpha，只能证明 `11` 需要 path management 与 sizing control。

更精确地说，`1615412` 的信息是：R5+frames 对 release 可能有效，但 fixed60 hold value 条件不足。若把它当成 bad entry 删除，会错过“entry 有效、exit 失败、sizing 过重”这一机制分解；若把它当成继续加杠杆的证据，则会放大左尾。

== 本章结论

R5/R10 的价值在于提供局部 path-shape memory，但 ratio 必须与 Delta、Energy、Z 一起解释。frames 是 staleness condition，而非 alpha 本身。四象限是分解语言，不是最终策略。

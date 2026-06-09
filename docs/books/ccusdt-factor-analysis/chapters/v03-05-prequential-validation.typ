#import "../styles.typ": definition, assumption, proposition, remark, evidence

= Prequential Estimation、Walk-Forward 与 Threshold Discipline

短周期因子研究最容易在时间方向上犯错：用同日未来样本设阈值、用未关闭 entry 更新 R5、用全样本 quantile 选择 admission gate，或者在知道 OOS 结果后重命名策略。本章把这些问题统一成 prequential 估计协议。

== Prequential order

对 entry 序列 $i=1,2,...$，任何 runtime state 都必须按时间递推。若 label horizon 为 $T$，entry $j$ 只有在 $t_j+T<t_i$ 时，才能影响 entry $i$ 的 closed-entry state。

#definition("Prequential estimator", [
  估计器 $hat(theta)_i$ 称为 prequential，当且仅当存在递推函数 $U$，使
  $
    hat(theta)_i=U(hat(theta)_{i-1}, Z_j: t_j+T<t_i),
  $
  且不使用任何 $t_i$ 之后才可见的 label、fill、path 或 summary。
])

R5/R10 是典型例子。若把尚未 60s closed 的 entry 放入最近历史集合，R5 会变成一种未来信息泄漏。这个错误在数字上可能只改变少数触发，但语义上已经不是同一策略。

== Threshold as estimator

`q70`、`q90`、`frames threshold`、`entry_spread_q70` 都不是自然常数，而是由历史数据估计出的阈值。设阈值为：

$ hat(q)_i(p)=Q_p({Z_j: t_j < t_i, j in cal(T)_i}) $

其中 $cal(T)_i$ 是训练窗口。若 $hat(q)$ 用全样本或 OOS 日数据估计，则策略的 admission boundary 发生 look-ahead。

#assumption("Prior-threshold discipline", [
  所有 quantile threshold 必须来自 prior-date 或 strictly pre-entry training window。若为了 sensitivity 报告 q60/q65/q70，主线 promotion 只能使用事先锁定的阈值族。
])

这正是 q60/q65 不能轻易提升为主线的原因。它们可以说明阈值敏感性，但若机制解释不变，仅因历史收益更高而降低阈值，就是过拟合路径。

== Walk-forward 的估计对象

Walk-forward 不是仪式，而是估计时间稳定性。对日期 $D$，训练集为 $cal(H)_D$，测试集为当日 entries：

$ hat(pi)_D = "Train"(cal(H)_D), quad Y_D="Eval"(hat(pi)_D, cal(E)_D) $

若每天重新优化并报告同一组历史日的总收益，则估计对象是 adaptive hindsight protocol；若先锁定参数再评估后续日，则估计对象才接近 live deploy protocol。

#remark("单日 OOS 的解释边界", [
  2026-05-18 OOS 能提供 fresh-day sanity，但不能单独证明稳定 edge。它可以证明 pipeline 与口径没立即崩坏，不能证明未来 regime 持续。
])

== Multiple testing 与 family lock

因子研究尝试大量变量时，即使每个变量都 runtime-safe，也会产生 selection bias。解决方式不是停止探索，而是区分 candidate discovery 与 locked evaluation。

#definition("Candidate family lock", [
  Candidate family lock 是指在进入正式评估前，先固定变量集合、阈值生成方式、capacity profile、exit profile、fill profile、latency profile 和评价指标。锁定后只能报告结果，不能再用 OOS 表现修改同一 family 的定义。
])

这条纪律可以解释为什么“更复杂的 exit controller”未必更专业。若 exit rule 是从少数失败案例逐步雕刻出来，但没有 family lock 与 matched controls，它可能只是把 casebook 变成策略。

== State boundary

Bot-owned state 需要明确边界。对日期 $D$ 的运行，状态文件应包含：

- `state_after_date`。
- `last_seen_ts_us`。
- `next_expected_date`。
- closed-entry R5/R10 sufficient statistics。
- pending shadow entries。
- policy params hash。
- data/cache manifest hash。

#proposition("State reuse without boundary is leakage risk", [
  若一个 state file 被独立用于多个非连续日期，或者跳过中间市场事件仍继续使用 closed-entry memory，则 R5/R10 不再对应同一个 prequential process。该 run 的 shadow entries 不能与连续 replay 结果直接比较。
])

== Fast 与 strict 的一致性对象

Fast line 与 strict sim-live line 的目标不同。Fast line 用 typed cache 与 mid/近似执行快速扫描参数；strict line 验证 exchange-style stream、latency、fill、private feedback 与 event log。它们必须共享 decision identity：

$ I_i=(t_i,n_i,"cell"_i,"side"_i,w_i^"req",w_i^"act") $

只要 $I_i$ 不一致，PnL 差异就不能归因于 execution。只有 entries、capacity、lot lifecycle 对齐后，fast-vs-strict 差异才可分解为 entry spread、exit spread、latency、depth、pressure。

== 当前证据约束

#evidence("5/16-5/18 shadow audit target", [
  当前系统把 2026-05-16、2026-05-17、2026-05-18 的 shadow audit 作为在线翻译验收，目标 entry counts 分别为 261、199、304。该验收的意义不是证明策略好，而是证明 runtime-safe decision_frame 与研究口径一致。
])

#evidence("2026-05-18 OOS capacity check", [
  锁定 cleaner q70 3x 策略在 2026-05-18 的 C=0 online FIFO clip 约 304 entries，core-only total 约 415.8276；`idle01_g1_r0` 约 472.5926。该证据依赖具体 capacity profile，不能与无容量约束或 7x sensitivity 误比较。
])

== 本章结论

Prequential discipline 是把研究表翻译成策略的核心。阈值、R5 state、entry cache、capacity ledger、profile manifest 都必须按时间生成。否则，回测仍可能有漂亮数字，但它不再回答“明天实盘时能看到什么”。


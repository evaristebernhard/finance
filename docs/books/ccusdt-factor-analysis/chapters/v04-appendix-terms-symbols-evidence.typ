#import "../styles.typ": note, factor

= 附录：术语表、符号表、因子卡片与证据路径

== 术语表

- 主动成交流不平衡（Trade Flow Imbalance, TFI）：窗口内主动买入减主动卖出的净流量。
- 路径形状比率（R5/R10）：最近已关闭 entry 的有利路径质量与不利路径质量之比。
- 净优势（Delta）：$Delta=P-N$。
- 路径能量（Energy）：$E=P+N$。
- 能量调整净优势（Z）：$Z=Delta / sqrt(E+epsilon)$。
- 停滞帧数（frames_since_mid_change）：中间价连续不变的 quote frame 数。
- 对手方深度（opposite depth）：信号方向要穿过的对手盘深度。
- 真空（vacuum）：对手方深度低、价格容易释放的状态。
- 释放（release）：entry 后价格快速沿信号方向移动。
- 衰减（decay）：释放后的收益回吐。
- 条件风险价值（CVaR）：最差分位中的平均损失。
- 右尾贡献（tail_share）：总收益中由高分位收益贡献的比例。
- 运行时安全（runtime-safe）：下单时可由当时可见信息计算。
- 未来标签（future label）：entry 后才知道的收益或路径变量。
- 快速回测（fast backtest）：用 decision frame cache 快速评估策略。
- 严格回放（strict replay）：用 Runner/Bot 模拟实盘数据流和成交。

== 符号表

- $a_t$：卖一价。
- $b_t$：买一价。
- $m_t$：中间价，$m_t=(a_t+b_t)/2$。
- $s_t$：价差基点，$s_t=(a_t-b_t)/m_t times 10000$。
- $q_t^a,q_t^b$：卖一数量、买一数量。
- $d_i$：entry 方向，做多为 +1，做空为 -1。
- $R_i(u)$：entry 后 $u$ 时间的方向化收益。
- $"MFE"_i(T)$：$T$ 内最大有利波动。
- $"MAE"_i(T)$：$T$ 内最大不利波动。
- $"Decay"_i(T)$：$"MFE"_i(T)-R_i(T)$。
- $cal(F)_t$：时间 $t$ 的可见信息集。
- $tau$：运行时停时或退出时间。

== 因子卡片索引

#factor("TFI", [
  中文主名：主动成交流不平衡。测量对象：主动流分子。可运行时：是，若成交方向可见或可在线推断。主要失败：迟到、被吸收、释放后回吐、活动度混淆。
])

#factor("Depth / Vacuum", [
  中文主名：对手方深度 / 真空。测量对象：冲击分母和释放条件。可运行时：一档可直接使用，多档依赖 L2。主要失败：真空不保证延续。
])

#factor("R5/R10", [
  中文主名：路径形状比率。测量对象：最近已关闭 entry 的路径记忆。可运行时：是，但必须预序贯。主要失败：低能量比例膨胀、状态断裂、退出混淆。
])

#factor("frames_since_mid_change", [
  中文主名：停滞帧数。测量对象：中间价停滞或潜在压力。可运行时：是。主要失败：它不是独立 alpha，必须和主动流、路径记忆、价差一起解释。
])

#factor("CVaR / tail_share", [
  中文主名：左尾约束 / 右尾贡献。测量对象：收益分布形状。可运行时：不是 entry 因子本身，而是离线估计和 promotion gate。
])

== 证据路径

本书只摘关键事实，不复制大表。主要证据层如下：

1. `docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md`
2. `docs/markets/ccusdt/v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md`
3. `docs/markets/ccusdt/v1-tfi-entry-estimation-20260518_ccusdt_v1_tfi_entry_estimation_v1.md`
4. `docs/markets/ccusdt/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md`
5. `docs/markets/ccusdt/v1-lob-stylized-factors-20260518_ccusdt_v1_lob_stylized_factors_v1.md`
6. `docs/markets/ccusdt/v1-tfi-core-quantity-estimation-20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.md`
7. `docs/markets/ccusdt/v1-tfi-exit-residual-pressure-diagnostic-20260524.md`
8. `docs/markets/ccusdt/v1-tfi-exit-wait-value-decomposition-20260524.md`
9. `docs/markets/ccusdt/v1-tfi-path-casebook-20260519_ccusdt_v1_tfi_path_casebook_v1.md`
10. `docs/markets/ccusdt/v1-tfi-small-path-manager-20260519_ccusdt_v1_tfi_small_path_manager_v1.md`
11. `docs/markets/ccusdt/v1-tfi-post-exit-watcher-20260519_ccusdt_v1_tfi_post_exit_watcher_v1.md`
12. `docs/markets/ccusdt/v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md`

== Promotion checklist

- 因子是否只依赖当时可见信息？
- threshold 是否来自 prior-date？
- R5 是否只使用已关闭 entry？
- 是否区分中间价收益和 taker 成交收益？
- 是否分解 entry spread、exit spread、latency、depth、capacity？
- `net_median < 0` 是否被错误当成删除理由？
- q60/q65 是否只是 sensitivity？
- oracle 是否只用于诊断上界？


#import "../styles.typ": definition, proposition, evidence

= Appendix B：符号、命题与证据地图

== 符号表

- $a_t,b_t$：best ask / best bid。
- $m_t$：mid price。
- $s_t$：spread in bps。
- $d_i$：entry direction。
- $R_i(T)$：方向化 horizon return。
- $H_i(T)$：MFE。
- $L_i(T)$：MAE。
- $D_i(T)$：decay。
- $cal(F)_t$：time-$t$ 可见信息集。
- $X_t$：runtime-safe factor。
- $Y_{t,T}$：future label。
- $C$：matched-control state。
- $P_k,N_k$：Rk 的有利/不利 path mass。
- $Delta_k,E_k,Z_k$：Rk decomposition。
- $tau$：stopping time。
- $"past_event_25_bps"$：entry 前 event-time price move control，属于 runtime-safe past state。
- $Theta_t$：局部 liquidity / absorption threshold。
- $lambda_t$：release efficiency。
- $"vacuum"_t$：low opposite-depth state。
- $L(t)$：当前 open exposure。
- $w_i^"req", w_i^"act"$：requested / actual exposure。

== 因子术语表

- TFI：trade flow imbalance，主动成交流的方向化统计量。
- R5/R10：最近 5/10 个合法 closed entries 的 path-shape memory。
- Delta：有利 path mass 与不利 path mass 的差。
- Energy：有利与不利 path mass 的总强度。
- Z：Energy-adjusted Delta。
- frames：mid price 自上次变化以来的 quote frame 数。
- spread：best ask 与 best bid 的 bps 差。
- depth：给定价位或多档中的可成交数量。
- QI：queue imbalance，bid/ask 可见队列不平衡。
- OFI：order flow imbalance，top-of-book supply change。
- MLOFI：multi-level OFI，多档 liquidity update 聚合。
- release：entry signal 转化为有利路径高点。
- decay：MFE 高点到 horizon 终点的回吐。
- residual pressure：release 后剩余方向力的诊断统计。
- exhaustion：drawdown、flow decay 与支撑弱化组合出的衰竭状态。
- CVaR：左尾条件平均损失。
- tail_share：右尾收益贡献集中度。
- net_median：已扣给定成本后的收益中位数，不是删除结构的充分条件。

== 命题列表

#proposition("P1 Runtime measurability", [
  Future return、MFE、decay、oracle exit 不是 entry-time $cal(F)_t$ 可测对象，不能进入 runtime signal。
])

#proposition("P2 Rk decomposition", [
  $R_k=P_k/(N_k+epsilon)$ 不识别 path energy；必须结合 $Delta_k=P_k-N_k$、$E_k=P_k+N_k$、$Z_k=Delta_k/sqrt(E_k+epsilon)$。
])

#proposition("P3 Median rejection fallacy", [
  `net_median < 0` 不蕴含结构无价值。Right-tail factor family 必须用 tail_share、CVaR、capacity 与 execution profile 共同评估。
])

#proposition("P4 Vacuum does not imply continuation", [
  Low opposite depth 可以提高 release probability，但不保证 fixed-horizon continuation。
])

#proposition("P5 Total PnL is not factor mechanism", [
  Aggregate PnL 混合 alpha、execution、capacity 与 tail。因子 promotion 必须分层归因。
])

== Evidence map

#evidence("Current research map", [
  `docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md` 记录当前 path-first 主线、R5 shape-ratio caveat、canonical failure case、path manager、watcher、capacity 与 OOS day。
])

#evidence("Factor decomposition", [
  `docs/markets/ccusdt/v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md`：`closed5_energy` metric spread 约 10.2597bps；`11_r5_frames` mean 约 5.1410；worst day 2026-05-13 包含 composition 与 payoff decay。
])

#evidence("Entry estimation", [
  `docs/markets/ccusdt/v1-tfi-entry-estimation-20260518_ccusdt_v1_tfi_entry_estimation_v1.md`：active entries 1715；strict estimates 1665；`strong_positive` 252 entries，weighted mean 7.5693。
])

#evidence("Release/decay", [
  `docs/markets/ccusdt/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md`：mean MFE5 2.5668，MFE10 3.6668，MFE60 9.9293，R60 4.2577，decay60 5.6716；`log_opp_depth25_quote` Spearman -0.2998。
])

#evidence("LOB stylized factors", [
  `docs/markets/ccusdt/v1-lob-stylized-factors-20260518_ccusdt_v1_lob_stylized_factors_v1.md`：dynamic trade_flow_imbalance 强于 static book factor；median spread 约 2.0050bps。
])

#evidence("Core quantity estimation", [
  `docs/markets/ccusdt/v1-tfi-core-quantity-estimation-20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.md`：核心形式 $r=d lambda (X-Theta)^+ + epsilon$；low Theta 与 lambda prior state 有解释价值。
])

#evidence("Residual pressure", [
  `docs/markets/ccusdt/v1-tfi-exit-residual-pressure-diagnostic-20260524.md`：residual pressure alone 不稳，exhaustion 更像 hold guard。
])

#evidence("Exit wait decomposition", [
  `docs/markets/ccusdt/v1-tfi-exit-wait-value-decomposition-20260524.md`：selected wait overlay total 约 +68.3173，mid component +47.3169，crossing component +21.0004。
])

#evidence("Path and capacity reports", [
  Path casebook、small path manager、post-exit watcher、leverage-constrained optimization 共同说明：case 是 mechanism 而非 losing label；`01_frames_only` 作为 idle-capacity sleeve 有增量；q65 是 sensitivity，不是主线。
])

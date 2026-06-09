= 附录 A：符号表与证据地图

== 核心符号

- $M_t$：mid price。
- $s_i$：entry 方向，取 $+1$ 或 $-1$。
- $R_i(tau)$：第 $i$ 笔 entry 在 horizon $tau$ 的 signed mid return。
- $H_i(h)$：窗口 $h$ 内最大有利路径收益。
- $D_i(h)$：从峰值回撤到窗口终点的 decay。
- $C_("fee")$：显式交易手续费。
- $c$：压力项，代表 spread、fill、latency、adverse selection、path decay reserve。
- $A_t$：`R5 > 1` 的二值状态。
- $B_t$：`frames_since_mid_change >= Q` 的二值状态。
- $W_t(tau)$：当前退出等待 $tau$ 后再 crossing 的增量价值。
- $kappa_t$：退出 crossing cost，相对 mid 的 taker cost。
- $w_t$：目标 exposure。
- $sum_j w_j(t) <= 3$：3x leverage cap 下的在线容量约束。

== 证据地图

当前书稿引用的主要证据层如下。

```text
docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md
docs/markets/ccusdt/v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md
docs/markets/ccusdt/v1-tfi-entry-estimation-20260518_ccusdt_v1_tfi_entry_estimation_v1.md
docs/markets/ccusdt/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md
docs/markets/ccusdt/v1-tfi-path-casebook-20260519_ccusdt_v1_tfi_path_casebook_v1.md
docs/markets/ccusdt/v1-tfi-small-path-manager-20260519_ccusdt_v1_tfi_small_path_manager_v1.md
docs/markets/ccusdt/v1-tfi-post-exit-watcher-20260519_ccusdt_v1_tfi_post_exit_watcher_v1.md
docs/markets/ccusdt/v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md
docs/markets/ccusdt/v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md
docs/markets/ccusdt/v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md
docs/markets/ccusdt/v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md
docs/markets/ccusdt/v1-tfi-conditional-wait-exit-opportunity-20260522.md
docs/markets/ccusdt/v1-tfi-exit-controller-v1-conditional-wait-m010-20260522.md
docs/markets/ccusdt/v1-tfi-exit-residual-pressure-diagnostic-20260524.md
docs/markets/ccusdt/v1-tfi-exit-wait-value-decomposition-20260524.md
systems/ccusdt_replay_exchange/docs/architecture.md
systems/ccusdt_replay_exchange/docs/event_contracts.md
systems/ccusdt_replay_exchange/docs/execution_model.md
systems/ccusdt_replay_exchange/docs/next-stage-three-process-design.md
```

== 运行边界

本书反复使用一个边界：

```text
diagnostic/report layer may read labels
strategy runtime must only read exchange-visible events
Runner owns clock/fill/portfolio/event log
Monitor is read-only
```

任何未来章节如果提出新规则，都必须说明它属于哪一层。

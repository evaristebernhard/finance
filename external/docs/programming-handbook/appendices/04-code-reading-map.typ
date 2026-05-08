#import "../styles.typ": *

= 附录 D 代码阅读地图

#chapter_problem[
  这一附录把全仓库最推荐的阅读顺序压成一张地图，方便你在正文结束后独立回读。
]

== D.1 零基础推荐顺序

```text
第一圈：main.rs
第二圈：domain/state.rs + objects.rs + evidence.rs
第三圈：state/builder.rs + validation.rs + compressed.rs
第四圈：projection/route.rs + synthetic.rs
第五圈：strategy/policy.rs + bellman.rs + eval/*
第六圈：tests + fixtures
```

== D.2 按问题回查

#anchor_table((
  [`我想知道输入从哪里来`], [`monad-mev-rpc` + `monad-mev-observation`],
  [`我想知道 primitive 怎么构造`], [`monad-mev-state/src/builder.rs`],
  [`我想知道为什么 projection 不能进 primitive`], [`monad-mev-domain/src/state.rs` + `monad-mev-state/src/validation.rs`],
  [`我想知道策略怎么做 act/wait/abort`], [`monad-mev-strategy/src/bellman.rs` + `policy.rs`],
  [`我想知道 artifact 为什么长这样`], [`monad-mev-cli/src/main.rs` + 本册附录 C],
  [`我想知道整条链能不能跑`], [`crates/monad-mev-cli/src/main.rs` 的 smoke test]
))

== D.3 按 artifact 回查

```text
看到 decision-state.json
  -> main.rs run_build_decision_state
  -> state/builder.rs
  -> projection/synthetic.rs
  -> state/compressed.rs

看到 decision.json
  -> strategy/policy.rs

看到 execution.json
  -> eval/execution.rs

看到 replay.json
  -> eval/replay.rs
```

== D.4 按字段追踪

#anchor_table((
  [`reserve0 / reserve1`], [`rpc snapshot -> RawObservation.payload -> StateBuilder -> PrimitiveStateView.g_t -> theta_pool / reserve_budget`],
  [`commit_phase`], [`NormalizedExecEvent(kind=commit_state_update) -> aggregate_events -> market_view -> PrimitiveStateView.m_t`],
  [`effective_gas_price_hint`], [`TxnOutcomeObservation -> aggregate_events -> FeePrimitiveView.effective_gas_price_hint`],
  [`gamma_t`], [`PrimitiveStateView + RouteCandidate + seed -> build_synthetic_projection_state -> ProjectionStateView.gamma_t -> CompressedDecisionState.gamma_t`],
  [`suggested_size`], [`visible depth -> reserve_budget -> seeded calibration -> CompressedDecisionState.suggested_size`],
  [`action`], [`CompressedDecisionState -> PaperBellmanPolicy::decide -> StrategyDecision.action`],
  [`realized_pnl`], [`ExecutionRecord.realized_pnl_hint + events + seed -> replay_execution -> ReplayReport.realized_pnl`]
))

== D.5 按“我卡住了哪里”回查

- 如果你卡在“字段从哪来”，优先查本附录 D.4。
- 如果你卡在“为什么要分 crate”，回到正文第 3 章。
- 如果你卡在“为什么不能塞进 primitive”，回到正文第 4 章和第 7 章。
- 如果你卡在“为什么这个数不是真值”，回到正文第 8 章与附录 C。

#chapter_summary[
  代码阅读地图的核心思想很简单：不要平铺式扫文件，而要带着问题、带着 artifact、带着闭环顺序回读。
]

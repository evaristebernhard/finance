#import "../styles.typ": *

= 07 `monad-mev-state`：从观测到 primitive，再到压缩态

#chapter_problem[
  这一章是整本编程教材的中轴。如果你读不懂 `monad-mev-state`，就无法真正回答“观测如何变成策略输入”。本章要解决的是：`StateBuilder`、validation 和 `compress_decision_state` 分别承担什么职责？
]

#reading_goal[
  你要把 `build_from_rpc_snapshot`、`aggregate_events`、`validate_primitive_state`、`validate_projection_state`、`compress_decision_state` 串成一条连续的理解链。
]

== 7.1 `monad-mev-state` 的三块职责

这个 crate 的 `lib.rs` 很像一个目录：

```rust
pub mod builder;
pub mod compressed;
pub mod validation;

pub use builder::StateBuilder;
pub use compressed::compress_decision_state;
pub use validation::{validate_primitive_state, validate_projection_state, StateValidationError};
```

也就是说，本 crate 一共做三件事：

1. 从观测构造 primitive
2. 把 primitive 与 projection 压成 decision state
3. 用 validation 守住边界

== 7.2 `StateBuilder::build_from_rpc_snapshot`

`builder.rs` 里最关键的入口是：

```rust
pub fn build_from_rpc_snapshot(
    raw: &RawObservation,
    events: &[NormalizedExecEvent],
) -> Result<PrimitiveStateView, StateBuilderError>
```

这个签名已经暴露了很多信息：

- 输入不是 `AmmSnapshotEnvelope`，而是更一般的 `RawObservation`
- 同时接收 normalized events
- 输出是 `PrimitiveStateView`

也就是说，builder 的工作是“解释原始观测”，不是“采集观测”。

== 7.3 event aggregate：先做局部聚合

builder 没有直接把每条 event 一条条塞进 primitive，而是先通过 `aggregate_events(events)` 得到中间汇总：

- `commit_phase`
- `commit_updates`
- `recent_outcomes`
- `access_observations`
- `shared_accounts`
- `shared_storage_slots`
- `touched_accounts`
- `touched_storage_slots`
- `effective_gas_price_hint`

这一步对新手很重要，因为它展示了一个常见工程模式：

```text
原始事件 -> 聚合统计 -> primitive 字段
```

而不是：

```text
原始事件 -> 直接变成 Bellman 输入
```

== 7.4 primitive 是怎样被填进去的

`build_from_rpc_snapshot` 内部会：

- 先从 `raw.payload` 解析出 `AmmSnapshotEnvelope`
- 再按 `Cpmm` 或 `Clmm` 选择 `g_t` 的字段
- 然后根据事件 aggregate 构造 `m_t / c_t / r_t / e_t / f_t`

例如 CPMM 情况下，`g_t` 会重点填：

- `family`
- `pool_address`
- `token0`
- `token1`
- `reserve0`
- `reserve1`

CLMM 情况下则重点填：

- `sqrt_price_x96`
- `tick`
- `liquidity`
- `pool_fee`

== 7.5 validation：先防止越级，再考虑方便

`validation.rs` 的职责特别适合教学，因为它不做复杂算法，只做“边界守卫”。

例如：

```rust
for forbidden in ["gamma_t", "p_t", "u_t", "q_t", "kappa_t"] {
    if contains_key(&json, forbidden) {
        return Err(StateValidationError::ForbiddenPrimitiveField(
            forbidden.to_string(),
        ));
    }
}
```

这段代码直白地告诉你：primitive state 里不能混入 projection 键。

另一边，`validate_projection_state` 还会检查：

```rust
if projection.is_some_and(|value| value.role != ObjectRole::Projection)
```

也就是说，projection 不仅要有值，还要保住“我是 projection”这个角色标签。

#crossrefbox[
  如果理论册告诉你“不能把 #gamma、#qt、#rt、#kappat、#ut、#pt 写成 primitive”，那么 validation crate 就是在工程上真正执行这条规则。
]

== 7.6 `compress_decision_state`

`compressed.rs` 是另一个必读文件。它的逻辑可以粗略理解成：

```text
primitive + projection + route
  -> family / pool_address / route_id / theta_pool / theta_route
  -> gamma/q/r/kappa/u/p
  -> reserve_budget / suggested_size / gas_limit / bid / max_fee / penalties
  -> CompressedDecisionState
```

这里特别值得注意两点：

1. `theta_pool` 和 `theta_route` 是压缩坐标，不是协议字段。
2. `reserve_budget`、`suggested_size`、`gas_limit` 等字段很多都被明确标记为 `CalibrationTarget` 或 modeling assumption。

== 7.7 为什么 state crate 里同时有“构造”和“压缩”

新手可能会问：既然 `compress_decision_state` 已经接近策略层了，为什么它还留在 `monad-mev-state`？

一个合理理解是：它仍然在做“状态组织”，只是从 primitive 进一步压到策略友好的 reduced-form 输入。真正做 action selection 的职责，还是留给 `monad-mev-strategy`。

#codewalk[
  本章最推荐精读的三段代码：

  1. `StateBuilder::build_from_rpc_snapshot`
  2. `aggregate_events`
  3. `compress_decision_state`

  你会在这三段里看到完整的“观测 -> primitive -> decision input”组织方式。
]

#source_map_box[
  ```text
  RawObservation + NormalizedExecEvent
    -> StateBuilder::build_from_rpc_snapshot
      -> PrimitiveStateView
        -> validate_primitive_state
          -> plan_amm_routes / build_synthetic_projection_state
            -> validate_projection_state
              -> compress_decision_state
                -> CompressedDecisionState
  ```
]

#artifactbox[
  当你看到 `decision-state.json` 里的：

  - `family`
  - `theta_pool`
  - `theta_route`
  - `gamma_t`
  - `reserve_budget`
  - `gas_limit`

  就应该立刻想到：这些不是直接从一个地方读出来的，而是 `compressed.rs` 按对象地位逐步拼起来的。
]

#checkpoint[
  你现在应该能解释：

  - `StateBuilder` 为什么接收 raw observation 和 normalized events 两类输入。
  - `aggregate_events` 为什么先把事件变成局部统计，再去构 primitive。
  - `validation` 为什么是硬边界守卫，不是“可有可无的检查”。
]

#exercise[
  1. 在 `builder.rs` 中找出 `market_view`、`competition_view`、`reserve_view`、`execution_view`，各用一句话说明它们分别构造哪个 primitive 分量。
  2. 在 `validation.rs` 中说明：为什么 primitive validation 会禁止 `gamma_t`，而 projection validation 会检查 `role`。
  3. 在 `compressed.rs` 中找出 `reserve_budget` 和 `suggested_size` 的生成逻辑，并说明它们为什么属于 calibration / compressed input，而不是 primitive。
]

#chapter_summary[
  `monad-mev-state` 是闭环的结构转换层。它把观测整理成 primitive，再把 primitive 与 projection 压成策略输入，同时用 validation 强制执行对象边界。
]

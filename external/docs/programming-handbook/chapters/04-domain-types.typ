#import "../styles.typ": *

= 04 `monad-mev-domain`：核心类型系统

#chapter_problem[
  如果没有统一类型语言，后面每个 crate 都会用自己的 JSON 结构和命名方式表达研究对象。本章要解决的是：`monad-mev-domain` 如何把研究对象地位编码成 Rust 类型边界？
]

#reading_goal[
  你要重点读懂 `PrimitiveStateView`、`ProjectionStateView`、`CompressedDecisionState`、`DecisionInput`、`ObservedObject`、`Projection` 和 `Evidence`，并能解释为什么它们必须分开。
]

== 4.1 先看 domain 的导出面

`crates/monad-mev-domain/src/lib.rs` 很短，但非常关键：

```rust
pub mod action;
pub mod evidence;
pub mod execution;
pub mod objects;
pub mod route;
pub mod state;
```

这说明 `domain` 并不负责流程，而是负责“闭环里交换哪些对象”。

#anchor_table((
  [`state.rs`], [primitive、projection 与 compressed decision state],
  [`objects.rs`], [对象地位、证据、弱代理与 decision input 包装],
  [`action.rs`], [策略动作与诊断信息],
  [`execution.rs`], [paper execution record],
  [`route.rs`], [route candidate 与 oracle metadata],
  [`evidence.rs`], [证据来源与观测强度]
))

== 4.2 `Evidence`：先标记来源，再谈值

对新读者来说，`Evidence` 最重要的意义不是“又多套了一层结构”，而是：任何值都必须带着来源。

```rust
pub enum EvidenceKind {
    CurrentRepoCode,
    OfficialExternal,
    ModelingAssumption,
}
```

再配合：

```rust
pub enum ObservationStrength {
    Direct,
    EventReconstructed,
    RpcWeakProxy,
    Latent,
}
```

于是每个字段不只是“有个数”，还知道：

- 证据来自当前仓库代码、外部官方资料，还是建模假设。
- 这个值是直接观测、事件重建、RPC 弱代理，还是 latent。

== 4.3 `ObservedObject`、`Projection`、`DecisionInput`

这三个包装类型是新手最容易嫌“繁琐”的地方，但它们恰好是防漂移核心。

```rust
pub struct ObservedObject<T> {
    pub name: String,
    pub role: ObjectRole,
    pub strength: ObservationStrength,
    pub value: T,
    pub evidence: Evidence,
    pub sources: Vec<SourceRef>,
    pub assumptions: Vec<String>,
}
```

注意这里连 primitive 字段都不是裸值，而是“值 + 角色 + 强度 + 来源 + 假设”。

`Projection<T>` 则允许：

```rust
pub value: Option<T>
```

这很重要，因为研究对象可以“被承认存在，但暂未识别具体数值”。

== 4.4 `PrimitiveStateView` 与 `ProjectionStateView`

`state.rs` 里最值得反复看的不是某个算法，而是类型分层：

```rust
pub struct PrimitiveStateView {
    pub g_t: Option<GeometryPrimitiveView>,
    pub m_t: Option<MarketPrimitiveView>,
    pub c_t: Option<CompetitionPrimitiveView>,
    pub r_t: Option<ReservePrimitiveView>,
    pub e_t: Option<ExecutionPrimitiveView>,
    pub f_t: Option<FeePrimitiveView>,
}
```

与之对应：

```rust
pub struct ProjectionStateView {
    pub gamma_t: Option<Projection<f64>>,
    pub p_t: Option<Projection<f64>>,
    pub u_t: Option<Projection<f64>>,
    pub q_t: Option<Projection<f64>>,
    pub r_t: Option<Projection<f64>>,
    pub kappa_t: Option<Projection<f64>>,
}
```

这段代码几乎就是研究边界的直接实现：

- `PrimitiveStateView` 只装 `G/M/C/R/E/F`
- `ProjectionStateView` 才装 #gamma、#pt、#ut、#qt、#rt、#kappat

#misconception[
  很多新手会觉得“既然最后都要送进策略，为什么不全部放一个大 struct 里？”答案是：一旦这么做，读者就无法从类型层面看出哪个值是 direct fact，哪个值只是 synthetic projection。
]

== 4.5 `CompressedDecisionState` 为什么面向策略

策略层通常不直接消费完整 primitive，也不直接消费完整 projection。中间要有一个“压缩但不失真值标签”的对象：

```rust
pub struct CompressedDecisionState {
    pub selected_route: Option<RouteCandidate>,
    pub family: Option<DecisionInput<String>>,
    pub theta_pool: Option<DecisionInput<String>>,
    pub theta_route: Option<DecisionInput<String>>,
    pub gamma_t: Option<DecisionInput<f64>>,
    ...
}
```

这里最关键的设计不是字段名，而是所有字段仍然是 `DecisionInput<T>`，而不是裸 `f64` 或 `String`。所以策略输入仍保留 evidence、role、strength。

== 4.6 route、action、execution

`domain` 还统一了后续层需要的对象：

- `RouteCandidate`：路线候选
- `StrategyDecision`：策略动作、理由、诊断
- `ExecutionRecord`：paper execution 记录

比如策略动作是：

```rust
pub enum PolicyAction {
    Act,
    Wait,
    Abort,
}
```

这很简洁，但足以支撑后面策略与回放层的闭环。

#codewalk[
  推荐先把 `domain` 读成一张“类型地图”：

  ```text
  observation -> PrimitiveStateView
  primitive + projection -> CompressedDecisionState
  decision state -> StrategyDecision
  strategy decision -> ExecutionRecord
  execution record -> ReplayReport / PnlReport / RiskReport
  ```
]

#artifactbox[
  当你看到 artifact 中出现：

  - `role`
  - `strength`
  - `evidence`
  - `assumptions`

  不要把它当成“额外噪音”。这正是 `domain` crate 想保住的工程语义：值不是孤立数字，值必须带着它的认识论标签。
]

#checkpoint[
  你现在应该能解释：

  - 为什么 `PrimitiveStateView` 和 `ProjectionStateView` 必须分开。
  - 为什么 `CompressedDecisionState` 仍然保留 `DecisionInput<T>` 包装。
  - 为什么 `EvidenceKind` 和 `ObservationStrength` 是硬边界，而不是文档装饰。
]

#exercise[
  1. 在 `objects.rs` 里找出 `ObservedObject<T>` 与 `Projection<T>` 的字段差异，并解释这些差异反映了什么对象地位差别。
  2. 在 `state.rs` 里找出 `CompressedDecisionState` 中至少 5 个字段，并按“几何 / projection / 执行参数”分类。
  3. 打开 `action.rs` 和 `execution.rs`，说明为什么 `StrategyDecision` 与 `ExecutionRecord` 需要是两个不同的类型，而不是一个对象硬塞到底。
]

#chapter_summary[
  `monad-mev-domain` 的真正任务不是“放公共 struct”，而是把研究边界变成类型边界。只要读懂这个 crate，后面所有流程 crate 都会变得容易理解。
]

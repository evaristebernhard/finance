#import "../styles.typ": *

= 08 `monad-mev-projection`：route 与 synthetic projection

#chapter_problem[
  一旦进入 projection 层，新手最容易把“策略很想要这些量”误读为“协议已经直接给出了这些量”。本章要解决的问题是：route planner 和 synthetic engine 到底在做什么，以及它们怎样显式保留弱代理与建模假设边界？
]

#reading_goal[
  你要读懂 `plan_amm_routes` 与 `build_synthetic_projection_state`，并能解释为什么这个 crate 既重要，又必须特别谨慎。
]

== 8.1 `lib.rs` 已经给了全部目录

`monad-mev-projection/src/lib.rs` 非常短：

```rust
pub mod route;
pub mod synthetic;

pub use route::plan_amm_routes;
pub use synthetic::build_synthetic_projection_state;
```

这说明本 crate 现在有两件主要工作：

1. 生成 AMM-first 的 route candidates
2. 根据 primitive 与 route 生成 synthetic projection

== 8.2 route planner：先给 Bellman 一个路径上下文

`route.rs` 的 `plan_amm_routes` 大致做了：

```text
从 primitive.g_t 读 family / pool / token0 / token1
  -> 根据可见几何估一个 mid price
  -> 生成 forward / reverse 两个 RouteCandidate
```

所以 route planner 现在不是“全链路由器”，而是 v1 的 AMM-first 候选构造器。

它生成的 `RouteCandidate` 至少包含：

- `route_id`
- `family`
- `direction`
- `token_in`
- `token_out`
- `legs`
- `synthetic_mid_price`
- `oracle_metadata`

== 8.3 synthetic engine：显式承认“这些量是构造出来的”

`synthetic.rs` 的命名已经很诚实：`build_synthetic_projection_state`。

它会生成：

- `gamma_t`
- `p_t`
- `u_t`
- `q_t`
- `r_t`
- `kappa_t`

但关键不只是“生成了值”，而是每个值都带着说明。例如：

```rust
p_t: Some(projection(
    "p_t",
    Some(p_t),
    ObservationStrength::Latent,
    "seeded synthetic verification probability",
    vec!["p_t is not directly observed in v1".to_string()],
)),
```

这段代码非常值得新手细读，因为它体现了两个工程伦理：

1. 给了值
2. 同时明确承认“这个值不是直接观测”

== 8.4 为什么 #gamma 也不能随便当 primitive

在这个 crate 中，`gamma_t` 的强度往往是 `RpcWeakProxy`，其 anchor 也会写成 synthetic gross opportunity from rpc geometry and synthetic oracle。

这意味着：

- 它依赖可见 pool geometry
- 但还叠加了 synthetic oracle context
- 所以不能被写成“协议直接给出的毛机会”

#misconception[
  “既然代码里已经算出了 `gamma_t`，那它就是事实。”这是典型误读。代码里算出了值，并不等于协议里存在这个字段；更不等于这个值已经通过强观测识别。
]

== 8.5 projection crate 为什么必须保留证据边界

如果这个 crate 只返回：

```text
gamma = 1.2
q = 0.7
r = 0.9
```

后面的策略层就会天然把这些数看成同层真值。当前实现之所以还专门使用 `Projection<T>`、`Evidence`、`ObservationStrength`，就是为了阻止这种误解。

== 8.6 route 与 projection 的关系

当前 `build_synthetic_projection_state` 不直接从空气里生成数值，而是依赖：

- primitive 可见深度
- route 的 `synthetic_mid_price`
- seed

这说明 projection 层至少承认：机会量和概率量必须依赖某个路径上下文。

#codewalk[
  推荐把这个 crate 读成两步：

  ```text
  plan_amm_routes
    -> 先给出一组可执行机会候选

  build_synthetic_projection_state
    -> 再在选定 route 上构造 v1 的 projection
  ```

  这种“两步走”对后续替换 synthetic engine 很重要，因为 route planner 和 projection engine 可以分别演化。
]

#source_map_box[
  ```text
  PrimitiveStateView
    -> plan_amm_routes
      -> Vec<RouteCandidate>
        -> select_route (CLI)
          -> build_synthetic_projection_state
            -> ProjectionStateView
  ```
]

#artifactbox[
  看到 `projection_state` 时，请按下面方式读：

  - `gamma_t`：机会投影，通常依赖可见几何和 synthetic oracle context
  - `p_t/u_t/q_t/r_t/kappa_t`：当前 v1 下仍是 latent 或 reduced-form proxy
  - `role` 必须是 `projection`
  - `strength` 反映它到底是弱代理还是 latent
]

#checkpoint[
  你现在应该能解释：

  - route planner 为什么只提供 AMM-first 候选，而不是全协议最优路由。
  - `build_synthetic_projection_state` 为什么在函数名里就强调 synthetic。
  - 为什么 projection crate 必须同时产出数值和证据边界。
]

#exercise[
  1. 在 `route.rs` 中找出 forward / reverse 两个 route candidate 的生成逻辑，并解释它们共享了哪些信息。
  2. 在 `synthetic.rs` 中找出至少两个明确写着“not directly observed in v1”或“reduced-form proxy”的地方，并解释这些注释为什么重要。
  3. 用一句话说明：为什么 route planner 和 synthetic engine 应该是两个函数，而不是一坨混在一起。
]

#chapter_summary[
  `monad-mev-projection` 负责把 primitive state 推到更接近策略的表示，但它始终要承认：很多关键量目前仍然是 synthetic、proxy 或 latent，而不是协议真值。
]

#import "../styles.typ": *

= 03 Workspace 总图

#chapter_problem[
  如果你不知道为什么项目要拆成八个 crate，就很容易把任何一个局部 crate 误看成“整个系统”。本章解决的问题是：这个 workspace 到底怎样按研究主线分层？
]

#reading_goal[
  你要能复述每个 crate 的职责、输入输出和它在闭环中的位置，并知道这种分层不是工程洁癖，而是为了避免对象漂移。
]

== 3.1 Cargo workspace 的第一层地图

根目录 `Cargo.toml` 把成员 crate 固定为：

```text
monad-mev-domain
monad-mev-rpc
monad-mev-observation
monad-mev-state
monad-mev-projection
monad-mev-strategy
monad-mev-eval
monad-mev-cli
```

可以先把它理解成八个角色：

- `domain`：统一类型语言
- `rpc`：RPC 观测适配器
- `observation`：原始观测与 normalized event
- `state`：从观测构 primitive，再压成 decision 输入
- `projection`：route 与 synthetic projection
- `strategy`：Bellman 风格决策
- `eval`：paper execution、replay、PnL、risk
- `cli`：把前面所有能力串成一个闭环

== 3.2 为什么不是一个超大 crate

如果全写在一个 crate 里，会有两个问题：

1. 研究对象边界容易糊掉。
2. 新读者不知道哪些代码是“类型”、哪些是“数据适配”、哪些是“策略”。

相反，现在的拆法几乎是在用 crate 边界表达研究流程：

```text
观测
  -> state
  -> projection
  -> strategy
  -> eval
```

而 `domain` 在中间提供通用类型，`cli` 在最外层做编排。

#crossrefbox[
  这与理论册里的“合法顺序”是一致的。crate 边界不是任意拆分，而是在工程上落实：观测层不能反向定义 primitive，策略层不能跳过前面几层。
]

== 3.3 先看 crate 导出，而不是先看内部细节

读一个 crate 时，先看 `src/lib.rs` 最划算。比如：

```rust
pub mod route;
pub mod synthetic;

pub use route::plan_amm_routes;
pub use synthetic::build_synthetic_projection_state;
```

这已经告诉你：

- 这个 crate 主要有两块能力。
- 对外最重要的 API 就是 `plan_amm_routes` 和 `build_synthetic_projection_state`。

== 3.4 workspace 是如何被 `main.rs` 用起来的

真正把各 crate 串起来的地方在 `crates/monad-mev-cli/src/main.rs` 顶部：

```rust
use monad_mev_eval::{
    pnl_from_replay, replay_execution, risk_from_replay, PaperExecutor, ReplayReport,
};
use monad_mev_observation::{
    read_normalized_exec_events, write_normalized_exec_events, JsonlObservationStore,
    ObservationStore, RawObservation,
};
use monad_mev_projection::{build_synthetic_projection_state, plan_amm_routes};
```

这里不要只把它当作一串 import。它其实是在说：

- CLI 会调用 eval、observation、projection 这些 crate。
- CLI 自己不重新定义这些逻辑，它只负责装配流程。

#codewalk[
  读 workspace 时，一个很有用的习惯是：先看每个 crate 的 `lib.rs` 导出了什么，再回到 `main.rs` 看 CLI 实际用了哪些导出。这样会比一开始就钻进函数体更清晰。
]

#source_map_box[
  ```text
  monad-mev-cli
    -> 读取输入 / 分发命令
    -> 调 monad-mev-rpc 获取 snapshot
    -> 调 monad-mev-observation 读写 JSONL
    -> 调 monad-mev-state 构 primitive / decision state
    -> 调 monad-mev-projection 构 route / projection
    -> 调 monad-mev-strategy 做决策
    -> 调 monad-mev-eval 做执行 / 回放 / 评估
  ```
]

== 3.5 当前仓库不是生产执行系统

crate 结构里一个很重要的“缺席”也值得注意：没有 signer crate，没有 nonce manager，没有 broadcast pipeline，没有钱包或密钥管理模块。

这不是缺功能忘了写，而是当前阶段刻意不做。因为整个 workspace 的目标是 research-valid closed loop，而不是 production trading stack。

#warningbox[
  以后如果你看到有人想在当前层次里直接加入私钥、广播、链上交易执行，要先问：这会不会把研究册与代码册共同强调的边界打破？
]

#commandbox[
  现在就可以用 CLI 名字反向记 crate 分层：

  ```text
  snapshot          -> rpc + observation
  ingest-events     -> observation
  build-state       -> state
  build-decision-state -> state + projection
  plan-route        -> projection
  decide            -> strategy
  paper-execute     -> eval
  replay / eval     -> eval
  ```
]

#checkpoint[
  你现在应该能解释：

  - 为什么这套仓库拆成八个 crate。
  - 为什么 `domain` 与 `cli` 一个在最底层类型语言、一个在最外层流程编排。
  - 为什么当前没有 live trading 基础设施不是“功能缺失”，而是阶段边界。
]

#exercise[
  1. 打开根目录 `Cargo.toml`，把八个成员 crate 抄下来，并给每个 crate 写一句职责说明。
  2. 随机选择两个 crate 的 `src/lib.rs`，总结它们对外导出的最重要函数或类型。
  3. 只看 `main.rs` 顶部 `use` 列表，不看函数体，推断 CLI 最可能串起了哪几层流程。
]

#chapter_summary[
  workspace 的拆分本身就是教材。它把研究顺序变成工程顺序：先有类型与观测，再有状态与投影，再有策略与评估，最后由 CLI 装配为闭环。
]

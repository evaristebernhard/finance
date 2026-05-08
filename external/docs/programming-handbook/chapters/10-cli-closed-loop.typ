#import "../styles.typ": *

= 10 `monad-mev-cli`：从 `main.rs` 走完整个闭环

#chapter_problem[
  到目前为止我们已经分 crate 学过每一层，但新手仍然容易“不知道从哪里把它们串起来”。本章要解决的问题就是：`main.rs` 如何把整个 workspace 编排成一个可运行的研究闭环？
]

#reading_goal[
  你要把 CLI 看成编排器：知道每个子命令调用哪个 crate、读写什么文件、输出什么 artifact，并能从 `run_build_decision_state` 追完整条主流程。
]

== 10.1 先看命令表

`main.rs` 里最显眼的枚举之一是：

```rust
enum Commands {
    Snapshot(SnapshotArgs),
    BuildState(BuildStateArgs),
    IngestEvents(IngestEventsArgs),
    BuildDecisionState(BuildDecisionStateArgs),
    PlanRoute(PlanRouteArgs),
    Decide(DecideArgs),
    PaperExecute(PaperExecuteArgs),
    Replay(ReplayArgs),
    Eval(EvalArgs),
}
```

这基本就是当前研究闭环的目录。

== 10.2 `main` 函数真的很像调度器

`main` 做的事情并不复杂：

```rust
let cli = Cli::parse();
match cli.command {
    Commands::Snapshot(args) => run_snapshot(args).await,
    ...
}
```

所以读 CLI 的关键，不是研究 `main` 自己，而是追每个 `run_*` 函数。

== 10.3 最关键的函数：`run_build_decision_state`

这可能是整份 `main.rs` 最值得精读的函数，因为它串起了：

- snapshot 读取
- events 读取
- primitive builder
- route planning
- projection builder
- validation
- decision state compression

调用链大致是：

```text
load_snapshot_envelope
  -> load_events
    -> raw_observation_from_snapshot
      -> StateBuilder::build_from_rpc_snapshot
        -> validate_primitive_state
          -> plan_amm_routes
            -> select_route
              -> build_synthetic_projection_state
                -> validate_projection_state
                  -> compress_decision_state
                    -> write_json_output
```

如果你能从头到尾复述这条链，就已经抓住当前 workspace 的主心骨了。

== 10.4 CLI 如何管理文件输入输出

`main.rs` 里有几组辅助函数特别适合新手学习：

- `load_snapshot_envelope`
- `load_events`
- `load_primitive_state`
- `load_decision_state`
- `load_decision_artifact`
- `write_json_output`

这些函数展示了一个很重要的工程模式：CLI 负责把磁盘文件和内存类型互相转换，但不重复实现领域逻辑。

== 10.5 为什么 `run_snapshot` 特别像“适配器桥梁”

`run_snapshot` 会：

1. 解析命令行参数
2. 构造 RPC config
3. 调 `AmmSnapshotService::snapshot`
4. 写 JSON 输出
5. 再把结果包装成 `RawObservation`
6. 写进 `JsonlObservationStore`

所以一个 CLI 命令并不总是只做一件事；它有时也负责把相邻层连接起来。

== 10.6 `end_to_end_closed_loop_smoke` 是最短教程

很多读者会忽略 `main.rs` 结尾的 smoke test，但它实际上是“最短版教案”：

- 写 fixture 到临时目录
- ingest events
- build decision state
- decide
- paper execute
- replay
- eval
- 断言产物包含 `pnl` 和 `risk`

这几乎就是一条可执行的教程目录。

#codewalk[
  如果你时间很少，读 CLI 的优先级可以缩成：

  1. `enum Commands`
  2. `run_build_decision_state`
  3. `run_decide`
  4. `run_paper_execute`
  5. `run_replay`
  6. `end_to_end_closed_loop_smoke`
]

#source_map_box[
  ```text
  CLI args
    -> run_*
      -> workspace crates
        -> typed artifact
          -> write_json_output
            -> file / stdout
  ```
]

#commandbox[
  这一章最值得自己完整跑一遍的命令链是：

  ```powershell
  cargo run -p monad-mev-cli -- ingest-events --input data/fixtures/normalized-events.fixture.jsonl --output data/derived/events.jsonl
  cargo run -p monad-mev-cli -- build-decision-state --snapshot data/fixtures/cpmm-snapshot.fixture.json --events data/derived/events.jsonl --seed 7 --output data/derived/decision-state.json
  cargo run -p monad-mev-cli -- decide --state data/derived/decision-state.json --output data/derived/decision.json
  cargo run -p monad-mev-cli -- paper-execute --decision data/derived/decision.json --seed 7 --output data/derived/execution.json
  cargo run -p monad-mev-cli -- replay --execution data/derived/execution.json --events data/derived/events.jsonl --seed 7 --output data/derived/replay.json
  cargo run -p monad-mev-cli -- eval --replay data/derived/replay.json
  ```
]

#artifactbox[
  `run_decide` 的输出不是裸 `StrategyDecision`，而是：

  ```text
  DecisionArtifact {
    state,
    decision,
  }
  ```

  这样后续 `paper-execute` 才不需要重新猜测 decision 当时依赖了哪个状态对象。
]

== 10.7 一个完整的 CPMM 闭环阅读案例

如果你只想选一个案例把整条链走通，推荐使用：

- `data/fixtures/cpmm-snapshot.fixture.json`
- `data/fixtures/normalized-events.fixture.jsonl`
- `seed = 7`

按这组输入跑完后，可以用下面的顺序回看：

```text
cpmm-snapshot.fixture.json
  -> build-decision-state
    -> 看 primitive_state.g_t.reserve0 / reserve1
    -> 看 route_candidates
    -> 看 projection_state.gamma_t / q_t / r_t / kappa_t
    -> 看 decision_state.theta_pool / reserve_budget / suggested_size
  -> decide
    -> 看 action / rationale / diagnostics
  -> paper-execute
    -> 看 expected_pnl / realized_pnl_hint / fill_probability
  -> replay
    -> 看 matched_events / realized_pnl / notes
  -> eval
    -> 看 pnl / risk
```

这条案例对新手最有帮助的地方在于：每一步都能回到一个真实文件，而不是停在抽象流程图。

== 10.8 CLI 辅助函数是“数据口岸”

`main.rs` 里那些以 `load_*` 和 `write_json_output` 命名的函数，也值得专门扫一遍。因为它们告诉你：

- 哪些命令直接接收裸 JSON 文件
- 哪些命令接受前一步 artifact
- 哪些命令会兼容不同输入形状

例如 `load_decision_state` 会优先尝试：

- `decision_state`
- `state`
- 或整个 JSON 直接反序列化

这让 CLI 在教学上更友好：你可以把某一步完整输出直接喂给下一步，也可以手工摘出中间状态对象继续实验。

== 10.9 为什么 `main.rs` 适合做“二刷”

第一次读 `main.rs`，你主要是在记流程。第二次回来看时，重点应该变成：

- 哪些地方只做编排
- 哪些地方做轻度桥接
- 哪些地方专门负责文件口岸与错误传播

一旦你能这样读 `main.rs`，你就不再把 CLI 看成“命令堆”，而会把它看成“研究闭环的外部接口定义”。

#checkpoint[
  你现在应该能解释：

  - `main.rs` 为什么更像编排器而不是“逻辑大本营”。
  - `run_build_decision_state` 为什么是理解整条闭环的最佳入口。
  - 为什么 CLI 辅助函数专门负责磁盘文件与内存类型转换。
]

#exercise[
  1. 在 `main.rs` 中找出 `run_snapshot`，用自己的话解释它如何同时连接 `rpc` 与 `observation` 两层。
  2. 画出 `run_build_decision_state` 的函数调用顺序，并标注每一步属于哪个 crate。
  3. 说明 `DecisionArtifact` 为什么比只输出一个 `StrategyDecision` 更适合继续传给 `paper-execute`。
]

#chapter_summary[
  `monad-mev-cli` 是当前 workspace 的外层编排器。它把各 crate 提供的能力串成一个研究闭环，并把中间状态写成可复读、可回放的 artifact。
]

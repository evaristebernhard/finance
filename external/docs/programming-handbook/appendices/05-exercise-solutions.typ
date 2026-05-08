#import "../styles.typ": *

= 附录 E 练习答案与最小修改思路

#chapter_problem[
  这一附录给出正文练习的参考答案。目标不是让读者机械对答案，而是帮助读者校准“我是不是把对象地位、crate 边界和调用链理解对了”。
]

== E.1 第 1 章答案

1. CLI 子命令共有 9 个：`snapshot`、`build-state`、`ingest-events`、`build-decision-state`、`plan-route`、`decide`、`paper-execute`、`replay`、`eval`。
2. `PrimitiveStateView` 承载 primitive，`ProjectionStateView` 承载 projection，`CompressedDecisionState` 面向策略输入。
3. 理论册附录 D 负责解释研究语言、实现语言与 CLI 流程语言的映射；本册负责把这种映射拆成可读的 Rust 代码与调用链。

== E.2 第 2 章答案

1. `observation` crate 主要导出三组东西：事件读写函数与事件类型；`RawObservation`；JSONL store 与存储 trait。
2. `AmmSnapshot` 这样的 `enum` 更好，因为它能在类型层面表达 `Cpmm`、`Clmm`、`NotYetSupported` 是不同分支。
3. `Result<()>` 能把 IO、解析、校验失败返回给上层；如果只返回 `()`，错误就无法沿 CLI 主流程传播。

== E.3 第 3 章答案

1. 八个成员 crate 依次承担：统一类型、RPC 适配、观测输入、状态构造、projection、策略、评估、CLI 编排。
2. 例如 `monad-mev-projection` 对外导出 `plan_amm_routes` 与 `build_synthetic_projection_state`；`monad-mev-eval` 对外导出 `PaperExecutor`、`replay_execution`、`pnl_from_replay`、`risk_from_replay`。
3. 只看 `use` 列表也能推断 CLI 会装配 observation、state、projection、strategy 与 eval。

== E.4 第 4 章答案

1. `ObservedObject<T>` 的 `value` 是必有值的；`Projection<T>` 的 `value` 是 `Option<T>`，因为 projection 允许“对象存在但暂未识别数值”。
2. `CompressedDecisionState` 中可分为：几何与路线字段（`family`、`pool_address`、`route_id`、`theta_pool`、`theta_route`）；projection 字段（`gamma_t`、`p_t`、`u_t`、`q_t`、`r_t`、`kappa_t`）；执行参数（`reserve_budget`、`suggested_size`、`gas_limit`、`bid`、`max_fee`）。
3. `StrategyDecision` 描述策略想做什么；`ExecutionRecord` 描述 paper executor 假设执行后会怎样，两者阶段不同。

== E.5 第 5 章答案

1. `CommitStateUpdate` 更偏向 `M_t`，`AccessObservation` 更偏向 `C_t/E_t`，`TxnOutcomeObservation` 会增强 `R_t/F_t` 一部分信息。
2. `ObservationStore` 只要求 `append`，因为当前阶段关注的是追加式记录原始观测，而不是复杂查询系统。
3. observation 层负责记录与标准化“看见了什么”，state 层才负责解释“这些观测如何组织成 primitive”。

== E.6 第 6 章答案

1. `CpmmSnapshot` 重点是 reserves；`ClmmSnapshot` 重点是 tick、liquidity、sqrt price、fee。这对应了不同 pool 几何。
2. `eth_chain_id` 返回链 ID，`eth_block_number` 返回块高，`eth_call` 返回某次合约调用的原始字节结果。
3. `AmmSnapshotEnvelope` 是唯一 snapshot carrier，因为 workspace 明确要求所有 RPC-only snapshot 通过同一 schema 进入后续 state builder。

== E.7 第 7 章答案

1. `market_view` 构造 `m_t`，`competition_view` 构造 `c_t`，`reserve_view` 构造 `r_t`，`execution_view` 构造 `e_t`。
2. primitive validation 禁止 `gamma_t` 等键混入 primitive；projection validation 则确保 projection 保留 `ObjectRole::Projection`。
3. `reserve_budget` 与 `suggested_size` 来自可见深度压缩和 seeded calibration，所以属于压缩态输入，不是 primitive 直接事实。

== E.8 第 8 章答案

1. forward / reverse route 共享 family、pool、token 对、visible geometry，但方向相反、`token_in/out` 反向、`synthetic_mid_price` 也会反向调整。
2. `p_t is not directly observed in v1`、`q_t remains a reduced-form proxy in v1` 这类文字在提醒读者：这些值当前不是机制真值。
3. route planner 与 synthetic engine 分离，可以把“机会候选生成”和“投影估计”两个责任解耦。

== E.9 第 9 章答案

1. `score_act` 依赖 `gamma_t`、`q_t`、`u_t`、`r_t`、`kappa_t`、gas 与 penalty 字段，它们大多来自 projection 或 compressed decision input。
2. 只有 `Act` 需要 `ExecutionIntent`，因为 `Wait` 与 `Abort` 不生成执行参数。
3. `TxnOutcomeObservation` 会增加 success 计数，`AccessObservation` 会增加 conflict 计数，两者共同影响 replay multiplier。

== E.10 第 10 章答案

1. `run_snapshot` 通过 `AmmSnapshotService` 读取 snapshot，再包装成 `RawObservation` 写入 observation store，所以它连接了 rpc 与 observation。
2. `run_build_decision_state` 依次调用 snapshot 读取、event 读取、state builder、primitive validation、route planner、projection builder、projection validation、decision state compression、JSON 输出。
3. `DecisionArtifact` 把策略输入状态和策略输出绑定在一起，方便后续执行层保持上下文一致。

== E.11 第 11 章答案

1. 例如 `builder::tests::builds_cpmm_state_from_raw_observation_and_events`：输入是 fixture snapshot 与三条 normalized events，调用 `StateBuilder::build_from_rpc_snapshot`，断言 reserve、commit phase 与 gas price hint。
2. `cpmm-snapshot.fixture.json` 更适合教学 reserves 几何；`clmm-snapshot.fixture.json` 更适合教学 tick / liquidity / sqrt price 几何。
3. CLI smoke test 是最短实践总复习，因为它把整条闭环串成一次可执行实验。

== E.12 第 12 章答案

1. 给 primitive 增字段时，通常先看 `domain/state.rs`、`state/builder.rs`、相关 validation 文件，以及对应 CLI / test 文件。
2. 给 `CompressedDecisionState` 增 penalty 字段，至少会牵动 `domain`、`state`、`strategy`、`cli` 和测试。
3. artifact 只是结果表现形式；真正的语义先存在于类型与构造逻辑里，所以它通常不是第一步。

== E.13 最小修改思路

推荐的新手修改顺序：

```text
定对象地位
  -> 改 domain 类型
    -> 改 builder / projection / strategy 逻辑
      -> 改 CLI 输出
        -> 改测试与 fixture
```

三条常见提醒：

- 如果字段来自直接观测，优先考虑 primitive。
- 如果字段是建模构造或 reduced-form 量，优先考虑 projection 或 compressed input。
- 如果你发现自己“为了方便”想把 projection 塞进 primitive，先停下来重审对象地位。

== E.14 两个额外的修改演练

演练一：给 primitive 增加 direct observation 字段

```text
先确认数据面里真有它
  -> 改 domain/state.rs
    -> 改 builder.rs 填值
      -> 跑或补 state 相关测试
        -> 再看 build-state / build-decision-state artifact 是否合理
```

演练二：给 decision state 增加新的 paper penalty

```text
先判断它是不是 modeling assumption
  -> 改 CompressedDecisionState
    -> 改 compress_decision_state
      -> 改 strategy 读取逻辑
        -> 改 CLI artifact 输出与 smoke test
```

这两个演练的共同点是：都从对象地位出发，而不是从“我想先改哪个 JSON 文件”出发。

#chapter_summary[
  练习答案的真正用途，是帮你把“会看代码”升级为“知道为什么这段代码必须这样分层，以及小改动应该从哪里入手”。
]

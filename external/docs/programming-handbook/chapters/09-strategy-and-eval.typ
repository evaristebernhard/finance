#import "../styles.typ": *

= 09 `monad-mev-strategy` 与 `monad-mev-eval`

#chapter_problem[
  当前读者已经看到了 primitive、projection 和 compressed decision state。下一步自然会问：策略怎么用这些输入做 `act / wait / abort`？执行、回放和评估又如何形成研究闭环？这就是本章要解决的问题。
]

#reading_goal[
  你要读懂 `BellmanKernel`、`PaperBellmanPolicy`、`PaperExecutor`、`replay_execution`、`pnl_from_replay`、`risk_from_replay` 的职责分工。
]

== 9.1 strategy crate：先算分，再选动作

`monad-mev-strategy` 的结构非常清楚：

```rust
pub mod bellman;
pub mod policy;
```

`bellman.rs` 负责评分，`policy.rs` 负责根据评分选动作。

== 9.2 `BellmanKernel` 是一步分数器

`score_act` 会读取：

- `gamma_t`
- `q_t`
- `u_t`
- `r_t`
- `kappa_t`
- `loss_penalty`
- `gas_limit`
- `bid`
- `max_fee`

再算出一个 synthetic act score。

这里一个非常好的阅读习惯是：把代码和理论册里的 one-step 收益式对应起来。你会发现它不是原封不动抄公式，而是做了 paper v1 的简化。

== 9.3 `PaperBellmanPolicy`

`policy.rs` 进一步把三个分数组装成一个决策：

```rust
let action = match (act_score, wait_score) {
    (Some(act), Some(wait)) if act > wait && act > 0.0 => PolicyAction::Act,
    (_, Some(wait)) if wait >= 0.0 => PolicyAction::Wait,
    _ => PolicyAction::Abort,
};
```

也就是说，当前策略层不是一个全动态规划求解器，而是一个 paper closed loop 下的可解释决策规则。

== 9.4 `ExecutionIntent` 与 `StrategyDecision`

策略层的输出不是直接“发交易”，而是：

- `action`
- `rationale`
- `intent`
- `diagnostics`

其中 `intent` 只在 `Act` 时出现。它会带上：

- route
- size
- gas_limit
- bid
- max_fee

这说明策略层输出的是“执行意图”，而不是已经广播的链上交易。

== 9.5 `PaperExecutor`

`monad-mev-eval/src/execution.rs` 里的 `PaperExecutor` 会把 `StrategyDecision` 与 `CompressedDecisionState` 变成 `ExecutionRecord`。

关键点有两个：

1. 它依赖 seed 产生可复现实验结果。
2. 它明确写着：

```rust
notes: vec!["paper execution only; no signer or broadcast".to_string()],
```

这条备注不是装饰，它是在 artifact 层再次声明边界。

== 9.6 replay、PnL、risk

`replay_execution` 会读取：

- `ExecutionRecord`
- `NormalizedExecEvent` 列表
- `seed`

然后根据 event 数量和类型给 `realized_pnl_hint` 乘一个 paper adjustment。

之后：

- `pnl_from_replay` 生成 `PnlReport`
- `risk_from_replay` 生成 `RiskReport`

这三步合起来，构成研究意义上的“执行后评估链”。

#misconception[
  不要把 `ReplayReport` 里的 `realized_pnl` 当成真实账户盈亏。当前 replay 使用的是 seeded paper adjustment，它服务于策略比较和研究验证，不是生产记账。
]

== 9.7 为什么 strategy 与 eval 分成两个 crate

这是很典型的工程边界：

- strategy 回答：在当前状态下应该做什么？
- eval 回答：如果按这个 paper 决策执行并回放，会得到怎样的研究结果？

如果把两者混成一个 crate，读者会更难看出“决策”和“事后评估”是两件事。

#codewalk[
  本章推荐的最短阅读链：

  ```text
  BellmanKernel::score_act / score_wait / score_abort
    -> PaperBellmanPolicy::decide
      -> PaperExecutor::execute
        -> replay_execution
          -> pnl_from_replay / risk_from_replay
  ```
]

#source_map_box[
  ```text
  CompressedDecisionState
    -> PaperBellmanPolicy
      -> StrategyDecision
        -> PaperExecutor
          -> ExecutionRecord
            -> replay_execution
              -> ReplayReport
                -> PnlReport / RiskReport
  ```
]

#artifactbox[
  对应 artifact 的阅读顺序应是：

  1. `decision.json`：策略层做了什么，为什么这么做
  2. `execution.json`：paper executor 假设执行后会怎样
  3. `replay.json`：把事件与 execution record 合起来重新估计结果
  4. `eval` 输出：把 replay 压成 PnL 与 risk
]

#checkpoint[
  你现在应该能解释：

  - `BellmanKernel` 和 `PaperBellmanPolicy` 的分工。
  - 为什么 `StrategyDecision` 不是直接可广播交易。
  - 为什么 `PaperExecutor`、replay、PnL、risk 一起构成“研究闭环的后半段”。
]

#exercise[
  1. 打开 `bellman.rs`，列出 `score_act` 依赖的核心字段，并说明它们大多来自哪一层对象。
  2. 在 `policy.rs` 中找出 `Act` 产生 `ExecutionIntent` 的逻辑，并解释为什么 `Wait` 与 `Abort` 不需要这部分数据。
  3. 在 `replay.rs` 中说明 `TxnOutcomeObservation` 与 `AccessObservation` 分别如何影响 replay adjustment。
]

#chapter_summary[
  strategy 与 eval 共同构成当前仓库的决策后半段：前者根据 compressed state 给出 paper policy，后者在不进入 live trading 的前提下完成执行、回放与评估。
]

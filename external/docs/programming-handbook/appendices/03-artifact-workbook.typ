#import "../styles.typ": *

= 附录 C Artifact 阅读手册

#chapter_problem[
  学会跑命令还不够，你还需要学会读 artifact。本附录把当前闭环里最重要的几个输出文件逐个拆开。
]

== C.1 `decision-state.json`

这是最值得精读的 artifact 之一，因为它把：

- primitive state
- route candidates
- projection state
- compressed decision state

集中放在一起。

阅读顺序建议：

1. 先看 `primitive_state`
2. 再看 `route_candidates`
3. 再看 `projection_state`
4. 最后看 `decision_state`

关键问题：

- 哪些字段来自直接观测？
- 哪些字段是 projection？
- 哪些字段是压缩出来供策略使用的？

== C.2 `decision.json`

这是 `DecisionArtifact`：

```text
state
decision
```

读法：

- `state` 是策略当时看到的输入
- `decision` 是策略给出的输出
- 两者绑定在一起，避免后面执行层失去上下文

== C.3 `execution.json`

这是 `ExecutionRecord`。重点看：

- `accepted`
- `expected_pnl`
- `realized_pnl_hint`
- `fill_probability`
- `notes`

尤其要看 `notes`，它会再次提醒你当前只是 paper execution。

== C.4 `replay.json`

这里最关键的字段是：

- `matched_events`
- `success`
- `realized_pnl`
- `notes`

不要把 `realized_pnl` 当成生产真值。先看 `notes` 里是否写着 seeded paper adjustment，再决定如何解释它。

== C.5 `eval`

最终 `eval` 输出会把 replay 压成：

- `pnl`
- `risk`

这一步适合比较不同 seed、不同 decision state 或不同 route 条件下的研究输出。

== C.6 统一阅读口诀

```text
先问对象地位
  -> 再问来源 crate
    -> 再问写出它的 CLI 命令
      -> 最后再解释数值本身
```

== C.7 一个“从前往后”的 artifact 案例

下面给出一个推荐的 artifact 回读次序。假设你刚跑完：

```powershell
cargo run -p monad-mev-cli -- build-decision-state --snapshot data/fixtures/cpmm-snapshot.fixture.json --events data/derived/events.jsonl --seed 7 --output data/derived/decision-state.json
```

读 `decision-state.json` 时，不要从头到尾顺序扫，而按下面次序看：

1. `primitive_state.metadata`
2. `primitive_state.g_t`
3. `primitive_state.m_t/c_t/r_t/e_t/f_t`
4. `route_candidates`
5. `projection_state`
6. `decision_state`

理由是：

- metadata 先告诉你观测来自哪里
- `g_t` 先给你局部几何
- 其他 primitive 再给你事件增强信息
- route 让你知道后面 projection 依赖哪条路径
- projection 才开始给出 `gamma/q/r/kappa/u/p`
- decision state 最后才是策略输入压缩

== C.8 一个“从后往前”的 artifact 案例

如果你已经拿到了 `decision.json`，推荐反向追踪：

```text
decision.action / rationale / diagnostics
  -> 去看 state.gamma_t / q_t / r_t / kappa_t
    -> 去看 primitive_state.g_t / m_t / e_t / f_t
      -> 去看输入 snapshot 与 events
```

这是非常重要的学习动作，因为策略结果永远不是凭空出现的。你必须能把一个动作反向追到它所依赖的 primitive 与 projection。

== C.9 artifact 阅读时最常见的三个坑

- 只看数值，不看 `role/strength/evidence`
- 只看最终 `decision`，不回看 `state`
- 看到 `realized_pnl` 就当真实收益，不去看 `notes`

#chapter_summary[
  当前闭环的 artifact 不是一堆调试文件，而是研究型代码最重要的可读接口。会读 artifact，等于真正打通了“类型 -> 流程 -> 输出”的最后一公里。
]

#import "../styles.typ": *

= 附录 F 端到端案例复盘

#chapter_problem[
  这一附录把整条闭环重新压成一个“带问题阅读”的案例。它的用途不是重复正文，而是帮助你在跑完命令后，知道应该按什么顺序回读代码与 artifact。
]

== F.1 案例输入

本附录默认使用：

- `data/fixtures/cpmm-snapshot.fixture.json`
- `data/fixtures/normalized-events.fixture.jsonl`
- `seed = 7`

选择这组输入的原因很简单：CPMM 几何最容易读，event fixture 也足够短，适合做第一次完整复盘。

== F.2 第一轮：只看输入，不看代码

先只读两个输入文件：

```text
cpmm snapshot
  -> pool_address
  -> chain_id / block_number
  -> token0 / token1
  -> reserve0 / reserve1

normalized events
  -> commit_state_update
  -> access_observation
  -> txn_outcome_observation
```

这一步你应该先能回答：

- 几何来自哪里？
- 事件增强来自哪里？
- 哪些信息还明显不存在？

例如你此时看不到：

- 真正识别出来的 #qt
- 真正识别出来的 #ut
- 真正识别出来的 #rt

这会为后面的 projection 阅读打预防针。

== F.3 第二轮：只看 `build-decision-state`

然后只跑：

```powershell
cargo run -p monad-mev-cli -- build-decision-state --snapshot data/fixtures/cpmm-snapshot.fixture.json --events data/derived/events.jsonl --seed 7 --output data/derived/decision-state.json
```

此时建议只看 `decision-state.json`，并分四块阅读：

1. `primitive_state`
2. `route_candidates`
3. `projection_state`
4. `decision_state`

每一块要问的问题分别是：

- primitive：哪些字段由 snapshot 或 event 直接支撑？
- route：当前只生成了什么样的候选？
- projection：哪些量已经有值，但明说是 synthetic / latent？
- decision state：策略到底拿到了哪些压缩输入？

== F.4 第三轮：回到代码找装配位置

现在再回到 `main.rs` 看 `run_build_decision_state`，你会发现它不是一个“大黑盒”，而是一个非常可分解的装配流程：

```text
load_snapshot_envelope
load_events
raw_observation_from_snapshot
StateBuilder::build_from_rpc_snapshot
validate_primitive_state
plan_amm_routes
build_synthetic_projection_state
validate_projection_state
compress_decision_state
write_json_output
```

复盘时，一个很有用的问题是：这个调用链里哪一步是在“解释观测”，哪一步是在“建模”，哪一步是在“压缩给策略”？

== F.5 第四轮：再走决策与评估

接着跑：

```powershell
cargo run -p monad-mev-cli -- decide --state data/derived/decision-state.json --output data/derived/decision.json
cargo run -p monad-mev-cli -- paper-execute --decision data/derived/decision.json --seed 7 --output data/derived/execution.json
cargo run -p monad-mev-cli -- replay --execution data/derived/execution.json --events data/derived/events.jsonl --seed 7 --output data/derived/replay.json
cargo run -p monad-mev-cli -- eval --replay data/derived/replay.json
```

这一轮推荐的阅读顺序不是时间顺序，而是：

```text
decision.json
  -> execution.json
    -> replay.json
      -> eval
```

因为你首先想知道策略到底做了什么，然后才关心 paper execution 假设怎样发生，最后再看 replay 和 eval 如何把它压成研究输出。

== F.6 这个案例最该带走什么

做完一轮完整复盘后，你应该能把当前闭环概括成一句工程语言：

```text
局部可观测输入
  -> 先组织成 primitive
    -> 再生成 route 与 synthetic projection
      -> 再压成 decision state
        -> 再由 paper policy / paper execution / replay / eval 形成研究闭环
```

同时你也应该能明确说出：这条链的哪些地方是 direct fact，哪些地方是 modeling assumption。

#chapter_summary[
  这份案例复盘的目的，是让你把正文里分章节学到的东西重新压回一条真实命令链。能独立完成这条复盘，才算真正读通了当前 workspace。
]

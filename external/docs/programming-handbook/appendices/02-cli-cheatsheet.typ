#import "../styles.typ": *

= 附录 B CLI 命令速查表

#chapter_problem[
  这一附录把当前 CLI 闭环压缩成一页命令地图，方便读者一边跑命令，一边回看正文中讲过的 crate 与 artifact。
]

== B.1 研究闭环命令

#anchor_table((
  [`snapshot`], [通过 RPC 读取池局部状态，并写出 snapshot / raw observation],
  [`ingest-events`], [读取 normalized event JSONL，再写出规范化输出],
  [`build-state`], [把 snapshot 与 events 解释成 primitive state],
  [`build-decision-state`], [构 primitive、route、projection 与 decision state],
  [`plan-route`], [只从 primitive state 规划 route candidates],
  [`decide`], [从 decision state 生成策略决策],
  [`paper-execute`], [把决策转成 paper execution record],
  [`replay`], [把 execution 与 events 结合成 replay report],
  [`eval`], [从 replay 生成 PnL 与 risk]
))

== B.2 最常用命令链

```powershell
cargo run -p monad-mev-cli -- ingest-events --input data/fixtures/normalized-events.fixture.jsonl --output data/derived/events.jsonl
cargo run -p monad-mev-cli -- build-decision-state --snapshot data/fixtures/cpmm-snapshot.fixture.json --events data/derived/events.jsonl --seed 7 --output data/derived/decision-state.json
cargo run -p monad-mev-cli -- decide --state data/derived/decision-state.json --output data/derived/decision.json
cargo run -p monad-mev-cli -- paper-execute --decision data/derived/decision.json --seed 7 --output data/derived/execution.json
cargo run -p monad-mev-cli -- replay --execution data/derived/execution.json --events data/derived/events.jsonl --seed 7 --output data/derived/replay.json
cargo run -p monad-mev-cli -- eval --replay data/derived/replay.json
```

== B.3 怎么记命令顺序

```text
先把输入整理好
  -> 再构状态
    -> 再做决策
      -> 再做 paper 执行
        -> 再回放
          -> 再评估
```

== B.4 什么时候用 `build-state`

如果你只想学习 primitive 构造，不想一下子跳到 projection 和决策层，可以先跑：

```powershell
cargo run -p monad-mev-cli -- build-state --input data/fixtures/cpmm-snapshot.fixture.json --events data/derived/events.jsonl
```

这非常适合和第 7 章一起阅读。

#chapter_summary[
  CLI 速查表的用途不是替代正文，而是帮你在实操时快速定位：这个命令对应哪个 crate、生成哪个 artifact、落在闭环的哪一层。
]

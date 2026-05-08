#import "../styles.typ": *

= 05 `monad-mev-observation`：观测层

#chapter_problem[
  当前仓库的第一层真实输入不是 Bellman，也不是 projection，而是观测。本章要解决的问题是：`monad-mev-observation` 到底收什么、写什么、导出什么，以及为什么观测层不能反向定义 primitive？
]

#reading_goal[
  你要读懂 `RawObservation`、`NormalizedExecEvent`、JSONL store 和事件读写函数，并能解释 observation crate 为什么被放在 state 之前。
]

== 5.1 `RawObservation`：最原始的壳

`raw.rs` 很短：

```rust
pub struct RawObservation {
    pub observed_at: DateTime<Utc>,
    pub adapter: String,
    pub source_kind: String,
    pub object_name: String,
    pub block: BlockReference,
    pub payload: Value,
}
```

可以先把它理解成：还没被 state builder 解释的“原始观测容器”。

注意最后一项是：

```rust
pub payload: Value
```

这意味着 observation 层允许保留原始 JSON 载荷，但并不声称已经把它升级成 primitive。

== 5.2 normalized event 为什么单独成层

`events.rs` 定义了三类标准化事件：

- `CommitStateUpdate`
- `AccessObservation`
- `TxnOutcomeObservation`

以及总包装：

```rust
pub struct NormalizedExecEvent {
    pub observed_at: DateTime<Utc>,
    pub block: BlockReference,
    pub source_kind: String,
    pub source: SourceRef,
    pub event: NormalizedExecEventKind,
}
```

这说明当前 workspace 的策略不是“直接把上游复杂事件系统链接进来”，而是先变成文件化、MIT-friendly 的 JSONL 规范输入。

== 5.3 JSONL store：append-only 观测日志

`store.rs` 里最重要的接口是：

```rust
pub trait ObservationStore {
    fn append(&self, observation: &RawObservation) -> Result<PathBuf, ObservationStoreError>;
}
```

现在默认实现是 `JsonlObservationStore`。这说明 observation 层当前重点是：

- 记录原始观测
- 允许追加
- 方便后续 state builder 消费

而不是在这一层做复杂建模。

== 5.4 为什么 observation 不能直接定义 primitive

这是本章最核心的边界。你可能会想：既然 normalized event 已经很结构化了，为什么不在 observation crate 里直接生成 `PrimitiveStateView`？

原因是：

1. observation 只负责“看见什么”。
2. primitive builder 负责“如何把看见的东西组织成 `G/M/C/R/E/F`”。

这两件事不能混在一起。

#crossrefbox[
  理论册把“观测”和“推断 / 压缩态”严格分开。当前工程里，`monad-mev-observation` 和 `monad-mev-state` 的 crate 边界正是在实现这件事。
]

== 5.5 真实 fixture 长什么样

当前 `data/fixtures/normalized-events.fixture.jsonl` 可以直接当教学样例：

```json
{"event":{"kind":"commit_state_update","phase":"verified","block_hash":"0xabc"}}
{"event":{"kind":"access_observation","tx_hash":"0x01","account":"0xaaaaaaaa...","storage_slots":["0x01","0x02"]}}
{"event":{"kind":"txn_outcome_observation","tx_hash":"0x01","success":true,"gas_used":21000,"effective_gas_price":100}}
```

从读代码角度，最值得注意的不是具体值，而是：

- 已经按 `kind` 分类
- 带了 `block`、`source_kind`、`source`
- 可以直接被 `read_normalized_exec_events` 顺序读入

#codewalk[
  `monad-mev-observation/src/lib.rs` 的导出几乎就是本 crate 的教学目录：

  ```rust
  pub use events::{read_normalized_exec_events, write_normalized_exec_events, ...};
  pub use raw::RawObservation;
  pub use store::{JsonlObservationStore, ObservationStore, ObservationStoreError};
  ```

  先记住这三块：读写事件、原始观测、存储。
]

#source_map_box[
  ```text
  CLI snapshot
    -> RawObservation
    -> JsonlObservationStore::append

  CLI ingest-events
    -> read_normalized_exec_events
    -> write_normalized_exec_events

  后续 build-state / build-decision-state
    -> 读取 RawObservation / NormalizedExecEvent
    -> 交给 monad-mev-state 解释
  ```
]

#commandbox[
  最适合本章的实操命令是：

  ```powershell
  cargo run -p monad-mev-cli -- ingest-events `
    --input data/fixtures/normalized-events.fixture.jsonl `
    --output data/derived/events.jsonl
  ```

  运行后重点不是“文件成功写出”本身，而是要问：为什么 CLI 此时只做事件标准化读写，而不直接构 primitive？
]

#checkpoint[
  你现在应该能解释：

  - `RawObservation` 为什么是原始观测壳，而不是 primitive。
  - `NormalizedExecEvent` 为什么是 observation 层的标准化输入。
  - 为什么 JSONL store 采用 append-only 思路。
]

#exercise[
  1. 打开 `events.rs`，把三类 normalized event 抄下来，并说明它们大致会增强哪几个 primitive 分量。
  2. 打开 `store.rs`，解释 `ObservationStore` trait 为什么只要求 `append`。
  3. 用一句话说明：为什么 observation 层负责“看见什么”，而不是负责“Bellman 需要什么”。
]

#chapter_summary[
  `monad-mev-observation` 是闭环的观测入口。它负责把原始载荷与标准化事件保留下来，但不会越级替 state builder 做 primitive 解释。
]

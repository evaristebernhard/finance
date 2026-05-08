#import "../styles.typ": *

= 01 如何读这本书

#chapter_problem[
  新读者最容易犯的第一个错误，不是看不懂语法，而是把三种语言混在一起：研究语言、实现语言、CLI 流程语言。本章先把这三层拆开，否则后面看任何 crate 都会漂移。
]

#reading_goal[
  你要能说清楚：什么是研究对象，什么是 Rust 类型，什么是 CLI 命令；并且知道为什么一本“编程教材”仍然必须服从对象地位与证据边界。
]

== 1.1 三种语言不是一回事

这套仓库里同时存在三种语言：

- *研究语言*：#st、#at、#gt、#mt、#ct、#rtstate、#et、#ft，以及由它们诱导出的 #gamma、#qt、#rt、#kappat、#ut、#pt。
- *实现语言*：Rust 的 `struct`、`enum`、`trait`、crate 导出、函数签名。
- *流程语言*：CLI 子命令、JSON artifact 文件、fixture 和 smoke test。

#misconception[
  如果你看到 `decision-state.json` 里有 `gamma_t`、`q_t`、`r_t`，就把它们当成“链上已经给出的值”，那就是把流程语言误当研究真值。相反，如果你只会背 #st 和 #gamma 却不知道它们在 Rust 里落到什么类型，也无法真正读懂仓库。
]

== 1.2 代码阅读的最小顺序

本册不按文件夹乱扫，而是按闭环走：

```text
main.rs
  -> 先看命令把哪些步骤串起来
  -> 再看 domain 里这些步骤交换什么类型
  -> 再看 state / projection / strategy / eval 分别补哪一层
  -> 最后回看 test 与 fixture，确认整条链能跑通
```

#source_map_box[
  ```text
  第 1 轮：crates/monad-mev-cli/src/main.rs
  第 2 轮：crates/monad-mev-domain/src/state.rs
  第 3 轮：crates/monad-mev-state/src/builder.rs
  第 4 轮：crates/monad-mev-projection/src/*.rs
  第 5 轮：crates/monad-mev-strategy + monad-mev-eval
  第 6 轮：tests / fixtures / artifact
  ```
]

== 1.3 代码书为什么仍要讲对象地位

这里有一个很重要的第一性原则：代码不是独立于研究对象存在的。当前 workspace 专门把 `PrimitiveStateView`、`ProjectionStateView`、`CompressedDecisionState` 分开，就是为了把“对象地位”编码进类型边界。

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

上面这段的重点不只是“Rust 里有个结构体”，而是：primitive 只承载 `G/M/C/R/E/F`。这条边界不是排版偏好，而是研究约束。

#codewalk[
  第一轮读代码时，不要先问“这段 Rust 语法怎么写”，先问三个问题：

  1. 这个类型在研究语言里对应什么对象？
  2. 这个对象是 primitive、projection、proxy 还是 calibration target？
  3. 这个字段来自直接观测、事件重建、RPC 弱代理还是建模假设？
]

== 1.4 artifact 是理解代码的捷径

CLI 的价值在于把静态类型变成可读 artifact。比如 `build-decision-state` 之后你会看到：

- primitive state
- route candidates
- projection state
- decision state

这其实是一条非常好的学习路径：先看 artifact 长什么样，再回到代码问“是谁把它组装出来的”。

#artifactbox[
  后面每一章都会反复使用同一个阅读公式：

  ```text
  看到一个 artifact 字段
    -> 先问它属于哪一层对象
    -> 再问它来自哪个 crate
    -> 最后问它是由哪个命令写出来的
  ```
]

#crossrefbox[
  本章对应理论册的“阅读路线与对象地位”和“附录 D”。理论册负责说明为什么必须区分三层语言；本册负责把这种区分映射到 crate、类型和命令。
]

#checkpoint[
  你现在应该能解释：

  - 为什么同一个仓库里会同时出现研究语言、实现语言、CLI 流程语言。
  - 为什么 `decision-state.json` 里的标量不能自动当成协议真值。
  - 为什么本册先从 `main.rs` 开始，而不是先从某个局部文件开始。
]

#exercise[
  1. 打开 `crates/monad-mev-cli/src/main.rs`，找出一共有几个 CLI 子命令，并把它们按闭环顺序写下来。
  2. 打开 `crates/monad-mev-domain/src/state.rs`，指出哪个类型承载 primitive，哪个类型承载 projection，哪个类型面向策略。
  3. 找到理论册里提到“附录 D”的位置，并用一句话说明它和这本编程书的分工差别。
]

#chapter_summary[
  学代码之前先固定认识论：研究对象不是 JSON 键，Rust 类型也不是自动等于研究真值。之后每读一个 crate，都要把它放回“对象地位 + 类型边界 + CLI 流程”三件事里理解。
]

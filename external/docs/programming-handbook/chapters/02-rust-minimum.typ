#import "../styles.typ": *

= 02 Rust 最小前导

#chapter_problem[
  本章不打算把 Rust 语言完整教一遍，只解决一个更现实的问题：为了读懂这个 workspace，你最低限度必须认识哪些 Rust 概念？
]

#reading_goal[
  你要会读 `struct`、`enum`、`impl`、`trait`、`Option`、`Result`、derive、模块与测试；至于生命周期深水区、unsafe 和宏系统内部细节，本册默认不展开。
]

== 2.1 crate、module、文件

先看最外层。这个项目是一个 Cargo workspace，里面有多个 crate。可以先把它想成：

```text
workspace
  -> 多个小工程（crate）
  -> 每个 crate 再按 module 分文件
```

在 Rust 里：

- *crate* 可以粗略理解为“一个可单独编译、可导出的工程单元”。
- *module* 是 crate 内部的命名空间与分文件组织方式。

例如：

```rust
pub mod events;
pub mod raw;
pub mod registry;
pub mod store;
```

这表示当前 crate 把实现拆在多个模块里。

== 2.2 `struct`：把一组字段放在一起

如果你以前只写过脚本语言，可以先把 `struct` 理解成“有固定字段的命名记录”。例如：

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

这不是“随便塞键值对”的动态对象，而是一张固定接口表。后面的代码看到 `RawObservation`，就知道至少有这些字段。

== 2.3 `enum`：一组互斥分支

`enum` 可以先理解成“有标签的几种可能”。比如：

```rust
pub enum PolicyAction {
    Act,
    Wait,
    Abort,
}
```

它表达的是：一个决策动作只能是三种之一，不能同时是 `Act` 和 `Wait`。

再复杂一点的例子是带数据的 `enum`：

```rust
pub enum AmmSnapshot {
    Cpmm(CpmmSnapshot),
    Clmm(ClmmSnapshot),
    NotYetSupported { family: String },
}
```

这里的重点是：不同 pool 家族对应不同内部数据结构。

== 2.4 `impl` 和关联函数

Rust 里很多“类方法式”写法都来自 `impl`。比如：

```rust
impl AmmSnapshotService {
    pub fn new(config: RpcConfig) -> Result<Self, AmmSnapshotError> { ... }

    pub async fn snapshot(
        &self,
        request: AmmSnapshotRequest,
    ) -> Result<AmmSnapshotEnvelope, AmmSnapshotError> { ... }
}
```

可以先把它理解成：`AmmSnapshotService` 这个类型有哪些能力。

== 2.5 `trait`：一组能力接口

`trait` 对零基础读者最直观的理解是“接口”：

```rust
pub trait StrategyPolicy {
    fn decide(&self, state: &CompressedDecisionState) -> StrategyDecision;
}
```

这意味着：只要某个类型实现了这个 trait，它就能接受一个决策态并产出策略决策。

== 2.6 `Option` 与 `Result`

这两个类型是本仓库最常见的阅读障碍，但其实目的很朴素。

- `Option<T>`：这个值“可能有，也可能没有”。
- `Result<T, E>`：这个操作“可能成功返回 `T`，也可能失败返回错误 `E`”。

例如：

```rust
pub family: Option<DecisionInput<String>>
```

意思不是“family 很不重要”，而是：当前数据面下，这个字段可能暂时拿不到。

再看函数签名：

```rust
fn load_decision_state(path: &Path) -> Result<CompressedDecisionState>
```

意思是：从文件加载决策态可能成功，也可能因为读文件或解析 JSON 失败而报错。

== 2.7 derive：让类型自动获得常见能力

本仓库大量使用：

```rust
#[derive(Clone, Debug, Serialize, Deserialize)]
```

可以先粗略理解成：

- `Clone`：可以复制
- `Debug`：可以调试打印
- `Serialize` / `Deserialize`：可以和 JSON 互转

这里的重点不是语法炫技，而是 artifact 工作流离不开 `serde` 的序列化能力。

== 2.8 测试函数

读这套仓库时，不要忽略 `#[cfg(test)]` 块。测试往往是最短的教学样例：

```rust
#[test]
fn end_to_end_closed_loop_smoke() { ... }
```

因为测试会用最短路径把：

- 输入 fixture
- 调用函数
- 断言输出

三件事连起来。

#codewalk[
  读一个不熟悉的 Rust 文件时，建议先找四个东西：

  1. 顶部 `use` 了哪些类型。
  2. 导出了哪些 `struct` / `enum` / `trait`。
  3. `impl` 里提供了哪些方法。
  4. 底部测试如何最小化地调用它。
]

#source_map_box[
  ```text
  Cargo workspace
    -> crate
      -> src/lib.rs 或 src/main.rs
        -> mod / pub use
          -> struct / enum / trait / impl
            -> tests
  ```
]

#commandbox[
  第一个最值得自己运行的命令不是任意 CLI 子命令，而是：

  ```powershell
  cargo test --workspace
  ```

  因为它会告诉你：哪些 crate 有单测、哪些文件提供 smoke test、整条研究闭环是否当前可运行。
]

#checkpoint[
  你现在应该能解释：

  - `struct` 和 `enum` 在这套仓库里分别承担什么角色。
  - 为什么 `Option` 常常表示“当前数据面暂不支持”，而不是“字段不重要”。
  - 为什么测试文件对新手是理解代码最快的入口之一。
]

#exercise[
  1. 在 `crates/monad-mev-observation/src/lib.rs` 里，找出它导出了哪些类型或函数，并按“事件 / 原始观测 / 存储”分组。
  2. 在 `crates/monad-mev-rpc/src/amm_snapshot.rs` 里找一个 `enum`，解释它为什么比随便塞一个 JSON 更适合表达不同 family。
  3. 在 `crates/monad-mev-cli/src/main.rs` 里找一个返回 `Result<()>` 的函数，说明它为什么不能简单返回 `()`。
]

#chapter_summary[
  到这里你不需要“学完 Rust”，但已经足够读这套仓库：crate 和 module 负责分层，`struct`/`enum` 负责表达类型边界，`Option`/`Result` 负责表达不确定性与错误，测试负责给你最短运行样例。
]

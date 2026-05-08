#import "../styles.typ": *

= 附录 A Rust 速查表

#chapter_problem[
  这一附录不是完整 Rust 手册，只收录本仓库阅读过程中最常见、最必要的概念与读法。
]

== A.1 最常见语法

#anchor_table((
  [`struct`], [固定字段的数据结构，常用来表达 artifact、state、record],
  [`enum`], [互斥分支的数据结构，常用来表达 family、动作、事件 kind],
  [`impl`], [给某个类型实现方法],
  [`trait`], [一组能力接口，例如策略接口、存储接口],
  [`Option<T>`], [值可能存在，也可能不存在],
  [`Result<T, E>`], [操作可能成功，也可能失败],
  [`pub`], [对外可见],
  [`#[derive(...)]`], [自动生成常用能力，如序列化、复制、调试打印],
  [`#[cfg(test)]`], [只在测试编译中启用],
  [`use ...`], [把外部类型或函数引入当前作用域]
))

== A.2 本仓库最值得记住的读法

- 看到 `Option<...>`，先想“当前数据面可能拿不到”。
- 看到 `Result<...>`，先想“读文件、解析 JSON、RPC 请求、校验都可能失败”。
- 看到 `pub use ...`，先想“这个 crate 想对外暴露什么”。
- 看到测试，先想“这是最短样例，不是附属品”。

== A.3 一些常见代码片段

```rust
pub struct ExecutionRecord {
    pub metadata: ObservationMetadata,
    pub decision: StrategyDecision,
    pub seed: u64,
    pub accepted: bool,
    pub expected_pnl: f64,
}
```

读法：

- 这是一个固定形状的记录对象
- 会被序列化成 artifact
- 字段顺序不重要，字段语义重要

```rust
pub trait StrategyPolicy {
    fn decide(&self, state: &CompressedDecisionState) -> StrategyDecision;
}
```

读法：

- 这是策略接口
- 输入是压缩态
- 输出是决策

== A.4 初学者最常见误解

- 误解一：`Option` 表示“不重要”
  纠正：它通常表示“当前数据面下可能缺失”
- 误解二：`enum` 比 JSON 麻烦
  纠正：它让分支边界更清楚，也更适合编译期检查
- 误解三：看不懂函数体就说明读不懂文件
  纠正：先看签名、导出、测试，往往比先看函数体更有效

#chapter_summary[
  Rust 速查的目的不是让你会写语言特性大全，而是让你有能力稳定阅读当前 workspace 的类型、函数和测试。
]

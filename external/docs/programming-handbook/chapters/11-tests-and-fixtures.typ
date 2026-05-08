#import "../styles.typ": *

= 11 测试与 fixture：闭环为什么能稳定教学

#chapter_problem[
  编程教材如果没有稳定输入，新手就只能对着抽象函数干看。本章解决的问题是：当前仓库的测试和 fixture 如何为教学提供最小可重复环境？
]

#reading_goal[
  你要读懂 fixture 文件、crate 内单测和 CLI smoke test 的配合方式，并知道为什么它们对“研究型代码阅读”尤其重要。
]

== 11.1 fixture 是可控世界

当前 `data/fixtures/` 下最常用的文件有：

- `cpmm-snapshot.fixture.json`
- `clmm-snapshot.fixture.json`
- `normalized-events.fixture.jsonl`

它们的作用是：给你一个可重复、不会变动的“局部世界”，这样你学习 state builder、projection、decision、eval 时不会被实时链上变化干扰。

== 11.2 单元测试往往是最短代码阅读样例

例如 `builder.rs` 里的测试会：

- 读取 `cpmm-snapshot.fixture.json`
- 构造三条 normalized event
- 调 `StateBuilder::build_from_rpc_snapshot`
- 断言 `reserve0`、`commit_phase`、`effective_gas_price_hint`

这比直接阅读长函数体更友好，因为它告诉你：

```text
给定什么输入
  -> 应该得到什么关键字段
```

== 11.3 smoke test 是整条闭环的活地图

`main.rs` 的 `end_to_end_closed_loop_smoke` 几乎等价于一节实践课：

```text
fixture snapshot
  -> fixture events
    -> ingest-events
      -> build-decision-state
        -> decide
          -> paper-execute
            -> replay
              -> eval
```

并且它最后会断言输出包含：

- `"pnl"`
- `"risk"`

这比纯文字说明更能证明闭环确实存在。

== 11.4 各 crate 测什么

现在的测试分布大致是：

- `observation`：事件读写、JSONL append
- `rpc`：ABI 编解码、header 解析、mock RPC 交互
- `state`：primitive 构建与 validation
- `projection`：synthetic engine 的 seed 确定性
- `cli`：端到端 smoke

这是一种很适合教学的分布，因为它同时覆盖：

- 局部正确性
- 跨 crate 连通性

== 11.5 为什么研究仓库更需要 fixture

对生产系统来说，很多时候可以直接连真实环境做集成验证。但对研究型仓库，尤其是当前仍然 paper-only 的系统，fixture 更重要，因为它让你能稳定讨论：

- 一个观测怎样被解释
- 一个 projection 怎样被生成
- 一个决策怎样被回放

而不是被实时世界噪音带着跑。

#codewalk[
  推荐把测试读成“最小教学样例”，不是“额外负担”：

  - 想学单个 crate，就先读对应 crate 的测试。
  - 想学整条闭环，就先读 CLI smoke test。
  - 想学 artifact 形状，就先跑 smoke 再看输出文件。
]

#source_map_box[
  ```text
  fixture file
    -> crate unit test
      -> assert key field

  fixture file
    -> CLI smoke test
      -> assert end-to-end artifact
  ```
]

#commandbox[
  本章推荐直接运行：

  ```powershell
  cargo test --workspace
  ```

  然后按测试名反向定位：

  - 哪个测试在验证 observation
  - 哪个测试在验证 rpc
  - 哪个测试在验证 state
  - 哪个测试在验证 projection
  - 哪个测试在验证 CLI 闭环
]

#artifactbox[
  如果你在学习时不知道一个字段“正常应该长什么样”，优先去找：

  1. 对应 fixture
  2. 对应测试断言
  3. 对应 CLI 输出

  这三者合起来，比读一长串文档描述更可靠。
]

#checkpoint[
  你现在应该能解释：

  - fixture 文件为什么是教学环境的核心。
  - 单元测试与 smoke test 在教学上的分工。
  - 为什么研究型闭环尤其需要稳定、可复现的样例输入。
]

#exercise[
  1. 选择一个 crate 的单元测试，写出它的输入、调用函数和断言目标。
  2. 打开 `cpmm-snapshot.fixture.json` 和 `clmm-snapshot.fixture.json`，说明它们分别更适合教学哪类几何差异。
  3. 用一句话说明：为什么 CLI smoke test 是整本编程教材最短的“实践总复习”。
]

#chapter_summary[
  fixture 与测试让这套仓库成为可教学的研究代码，而不只是“能跑的一堆模块”。对零基础读者来说，它们是最稳定、最可靠的学习锚点。
]

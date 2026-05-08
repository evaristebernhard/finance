#import "../handbook/styles.typ": *
#import "../handbook/notation.typ": *
#import "styles.typ": *

#set document(
  title: "Monad MEV Rust 配套编程教材",
  author: "monad_mev research workspace",
)
#set page(paper: "a4", margin: (x: 26mm, y: 26mm), numbering: "1")
#set text(font: ("Microsoft YaHei", "SimSun", "Arial"), lang: "zh", size: 11.6pt)
#set heading(numbering: "1.1")
#set par(justify: true, leading: 0.92em)
#show heading.where(level: 1): it => [
  #pagebreak(weak: true)
  #it
]
#show link: underline
#show raw.where(block: true): it => block(
  width: 100%,
  fill: rgb("#f8f8f8"),
  stroke: 0.45pt + rgb("#dddddd"),
  inset: 8pt,
  radius: 4pt,
  it,
)

#align(center)[
  #text(size: 22pt, weight: "bold")[Monad MEV Rust 配套编程教材]

  #v(8pt)
  #text(size: 13pt)[面向 Rust 零基础读者的 workspace 代码阅读与动手手册]

  #v(16pt)
  #text(size: 10pt)[目标：读懂当前仓库的 paper closed loop，而不是泛泛学习 Rust 语法]
]

#v(18pt)
#factbox[
  这本书与理论教材并列，不替代理论教材。理论册回答“研究对象是什么、对象地位如何区分”；本册回答“这些对象在 Rust 里如何表示、如何流动、如何被 CLI 组织成 artifact”。
]

#warningbox[
  本册仍然遵守同一条反漂移约束：不得把 RPC-only 快照写成机制真值，不得把 synthetic projection 写成协议直接给定，不得把 paper execution 误解为 live trading。
]

#reading_goal[
  读完本册，读者应能自己从 `crates/monad-mev-cli/src/main.rs` 出发，追踪到 `PrimitiveStateView`、`ProjectionStateView`、`CompressedDecisionState`、`StrategyDecision`、`ExecutionRecord` 与 `ReplayReport`，并能解释每一步为什么存在、边界在哪里。
]

#crossrefbox[
  理论对象与数学公式请配合阅读 `docs/handbook/main.typ`，尤其是“附录 D. 从研究对象到当前代码与 CLI 的映射”。本册会反复引用那一册，但不会把数学推导重写一遍。
]

#pagebreak()
#outline(title: [目录], indent: auto)

#include "chapters/01-how-to-read.typ"
#include "chapters/02-rust-minimum.typ"
#include "chapters/03-workspace-map.typ"
#include "chapters/04-domain-types.typ"
#include "chapters/05-observation-layer.typ"
#include "chapters/06-rpc-adapter.typ"
#include "chapters/07-state-builder.typ"
#include "chapters/08-projection-layer.typ"
#include "chapters/09-strategy-and-eval.typ"
#include "chapters/10-cli-closed-loop.typ"
#include "chapters/11-tests-and-fixtures.typ"
#include "chapters/12-safe-small-changes.typ"

#include "appendices/01-rust-cheatsheet.typ"
#include "appendices/02-cli-cheatsheet.typ"
#include "appendices/03-artifact-workbook.typ"
#include "appendices/04-code-reading-map.typ"
#include "appendices/05-exercise-solutions.typ"
#include "appendices/06-end-to-end-walkthrough.typ"
#include "appendices/07-field-extension-checklist.typ"

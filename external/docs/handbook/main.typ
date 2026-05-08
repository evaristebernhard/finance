// Monad + AMM 第一性原理工程教材
// 主入口：typst compile docs/handbook/main.typ target/monad-amm-engineering-handbook.pdf

#import "notation.typ": *

#set document(
  title: "Monad + AMM 第一性原理工程教材",
  author: "monad_mev research workspace",
)
#set page(paper: "a4", margin: (x: 27mm, y: 27mm), numbering: "1")
#set text(font: ("Microsoft YaHei", "SimSun", "Arial"), lang: "zh", size: 12.5pt)
#set heading(numbering: "1.1")
#set par(justify: true, leading: 1.02em)
#show heading.where(level: 1): it => [
  #pagebreak(weak: true)
  #it
]
#show link: underline
#show raw.where(block: true): it => block(
  width: 100%,
  fill: rgb("#f7f7f7"),
  stroke: 0.45pt + rgb("#dedede"),
  inset: 8pt,
  radius: 4pt,
  it,
)

#let callout(title, fill, stroke, body) = block(
  width: 100%,
  fill: fill,
  stroke: 0.8pt + stroke,
  inset: 9pt,
  radius: 5pt,
)[
  *#title* \
  #body
]

#let factbox(body) = callout("事实", rgb("#eef6ff"), rgb("#7aa7d9"), body)
#let assumptionbox(body) = callout("建模假设", rgb("#fff7e8"), rgb("#dfad52"), body)
#let examplebox(body) = callout("数值例", rgb("#eefaf1"), rgb("#7ab883"), body)
#let warningbox(body) = callout("反漂移提醒", rgb("#fff0f0"), rgb("#d97979"), body)
#let intuitionbox(body) = callout("第一性直觉", rgb("#f4f0ff"), rgb("#9b85d6"), body)
#let misconception(body) = callout("常见误解", rgb("#fff9ef"), rgb("#d7a86b"), body)
#let chapter_problem(body) = callout("本章真正要解决的问题", rgb("#f7fbff"), rgb("#99badd"), body)
#let chapter_summary(body) = callout("小结", rgb("#f8fff8"), rgb("#94c994"), body)
#let exercise(body) = callout("练习题", rgb("#f7f7ff"), rgb("#9999d9"), body)

#let paramcard(
  symbol,
  name,
  unit,
  role,
  evidence,
  observable,
  example,
  source,
  risk,
) = block(width: 100%)[
  #table(
    columns: (22%, 78%),
    inset: 6pt,
    stroke: 0.45pt + rgb("#c9c9c9"),
    fill: (x, y) => if x == 0 { rgb("#f3f3f3") } else { none },
    [符号], [#symbol],
    [中文名], [#name],
    [单位], [#unit],
    [对象地位], [#role],
    [证据来源], [#evidence],
    [是否直接可观测], [#observable],
    [数值示例], [#example],
    [第一性来源], [#source],
    [估错影响], [#risk],
  )
]

#let evidence_note(body) = callout("证据边界", rgb("#f1fbfa"), rgb("#77aba6"), body)

#align(center)[
  #text(size: 22pt, weight: "bold")[Monad + AMM 第一性原理工程教材]

  #v(8pt)
  #text(size: 13pt)[从 block 数组到 Monad-native AMM MEV 控制问题]

  #v(18pt)
  #text(size: 10pt)[目标读者：只知道“区块链是 block 的数组”，但愿意一步一步学数学建模]
]

#v(20pt)
#factbox[
  本教材的证据只来自三类：当前仓库代码、外部官方资料、建模假设。凡是 `Gamma/q/r/kappa/u/p` 这类量，都必须说明它是 projection、proxy 或 calibration target，不能写成 primitive 或协议真值。
]

#warningbox[
  本教材不教学 live trading、签名、广播、private key、nonce manager 或任何实盘资金执行。本仓库当前闭环是 paper execution，用于研究可复现的建模、决策、回放和评估。
]

#factbox[
  另有一册独立的 Rust 配套编程教材：`docs/programming-handbook/main.typ`。理论册负责对象地位、数学与证据边界；编程册负责 crate 分层、Rust 类型、调用链、CLI 与 artifact 阅读。
]

#pagebreak()
#outline(title: [目录], indent: auto)
#pagebreak()

= 阅读路线与对象地位

这本教材不是把公式堆给读者，而是按第一性原理回答一条链：

```text
block 数组
  -> transaction 改变 state
  -> EVM/Monad execution 产生事件
  -> AMM pool 用不变量报价
  -> 套利机会从 pool geometry 中出现
  -> Monad 机制决定机会是否可执行
  -> primitive state 压缩成 decision state
  -> Bellman 比较 act / wait / abort
  -> paper execution / replay / PnL / risk 评估
```

#intuitionbox[
  第一性原理不是“从很高级的公式开始”。第一性原理是先问：这个对象为什么必须存在？它由什么更基本的对象生成？它能不能被直接观察？如果不能，它只是 projection、proxy，还是 calibration target？
]

== 如何读本书的数学语言

这本教材以后不再把 #qt、#rt、#kappat、#ut、#pt、#gamma 这些对象写成反引号代码样式。原因很简单：它们不是文件名，也不是 JSON 键，它们是数学对象。

#factbox[
  #protocol_lang \
  #research_lang \
  #impl_lang
]

默认约定如下：

- 状态写成 #st，动作写成 #at。
- 六个 primitive 分量写成 #gt、#mt、#ct、#rtstate、#et、#ft。
- 由状态与动作诱导出的对象写成 #gamma、#qt、#rt、#kappat、#ut、#pt。
- 压缩态坐标写成 #thetapool 与 #thetaroute。
- 价值函数和一步收益写成 #vt 与 #jt。

#warningbox[
  只有在以下情况才保留反引号：文件路径、CLI 命令、JSON 键、代码块、协议枚举值，或者明确在讨论“错误写法/旧写法”时。正文叙述里的研究对象一律按数学对象排版。
]

#include "chapters/01-block-state-machine.typ"
#include "chapters/02-evm-execution.typ"
#include "chapters/03-monad-not-just-fast.typ"
#include "chapters/04-block-events-verified-output.typ"
#include "chapters/05-gas-reserve-survival.typ"
#include "chapters/06-amm-first-principles.typ"
#include "chapters/07-cpmm-complete-math.typ"
#include "chapters/08-amm-families.typ"
#include "chapters/09-mev-executable-opportunity.typ"
#include "chapters/10-unified-kernel.typ"
#include "chapters/11-projection-parameter-modeling.typ"
#include "chapters/12-bellman-paper-loop.typ"
#include "appendices/notation-glossary.typ"
#include "appendices/monad-casebook.typ"
#include "appendices/cpmm-workbook.typ"
#include "appendices/implementation-mapping.typ"
#include "appendices/artifact-workbook.typ"
#include "appendices/bellman-workbook.typ"
#include "appendices/modeling-mistakes.typ"
#include "appendices/blockstate-workbook.typ"
#include "appendices/reserve-workbook.typ"
#include "appendices/end-to-end-casebook.typ"
#include "appendices/glossary.typ"
#include "appendices/exercise-solutions.typ"

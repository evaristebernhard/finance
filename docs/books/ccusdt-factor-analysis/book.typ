#set document(
  title: "CCUSDT 第一性原理因子分析 v0.4",
  author: "Jiang / Codex",
)

#set page(
  paper: "a4",
  margin: (left: 22mm, right: 22mm, top: 20mm, bottom: 22mm),
  numbering: "1",
)

#set text(
  font: "Microsoft YaHei",
  size: 11.2pt,
  lang: "zh",
)

#set par(
  justify: true,
  leading: 1.05em,
  first-line-indent: 1.4em,
)

#set heading(numbering: none)

#show raw: set text(font: "Consolas", size: 9pt)
#show link: underline

#align(center)[
  #v(32mm)
  #text(size: 23pt, weight: "bold")[CCUSDT 第一性原理因子分析]

  #v(7mm)
  #text(size: 13pt)[中文推导式专业讲义：从订单簿机制到主动流与路径记忆]

  #v(14mm)
  #text(size: 10pt)[v0.4 / 2026-05-31]

  #v(4mm)
  #text(size: 9pt)[市场现象 -> 订单簿机制 -> 数学对象 -> 因子定义 -> 策略边界]
]

#pagebreak()

#outline(title: "目录", depth: 1)

#pagebreak()

#include "chapters/v04-00-why-rewrite.typ"
#pagebreak()

#include "chapters/v04-01-exchange-minimal-model.typ"
#pagebreak()

#include "chapters/v04-02-orderbook-spread-depth.typ"
#pagebreak()

#include "chapters/v04-03-zero-fee-spread-cost.typ"
#pagebreak()

#include "chapters/v04-04-why-price-moves.typ"
#pagebreak()

#include "chapters/v04-05-events-to-factors.typ"
#pagebreak()

#include "chapters/v04-06-tfi.typ"
#pagebreak()

#include "chapters/v04-07-depth-vacuum-release.typ"
#pagebreak()

#include "chapters/v04-08-r5-delta-energy-z.typ"
#pagebreak()

#include "chapters/v04-09-four-cells-capacity.typ"
#pagebreak()

#include "chapters/v04-10-entry-quality-distribution.typ"
#pagebreak()

#include "chapters/v04-11-release-decay-stopping.typ"
#pagebreak()

#include "chapters/v04-12-failed-factors-discipline.typ"
#pagebreak()

#include "chapters/v04-13-factor-to-strategy.typ"
#pagebreak()

#include "chapters/v04-appendix-terms-symbols-evidence.typ"
#pagebreak()

#include "references.typ"

#set document(
  title: "CCUSDT Replay Exchange 研究专著",
  author: "Jiang / Codex",
)

#set page(
  paper: "a4",
  margin: (left: 24mm, right: 24mm, top: 22mm, bottom: 24mm),
  numbering: "1",
)

#set text(
  font: "Microsoft YaHei",
  size: 10.5pt,
  lang: "zh",
)

#set par(
  justify: true,
  leading: 0.72em,
)

#set heading(numbering: "1.1")

#align(center)[
  #v(34mm)
  #text(size: 24pt, weight: "bold")[CCUSDT Replay Exchange 研究专著]

  #v(7mm)
  #text(size: 13pt)[从微观结构因子到本地交易所回放内核]

  #v(14mm)
  #text(size: 10pt)[v0.1 / 2026-05-31]

  #v(4mm)
  #text(size: 9pt)[面向未来自己与新 Codex 的研究手册]
]

#pagebreak()

#outline(title: "目录")

#pagebreak()

#include "chapters/00-preface.typ"
#pagebreak()

#include "chapters/01-first-principles-edge.typ"
#pagebreak()

#include "chapters/02-factor-python-loop.typ"
#pagebreak()

#include "chapters/03-replay-exchange-backtest.typ"
#pagebreak()

#include "chapters/04-remaining-outline.typ"
#pagebreak()

#include "references.typ"


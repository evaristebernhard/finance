#set document(
  title: "CCUSDT Replay Exchange 工程代码导读 v0.1",
  author: "Jiang / Codex",
)

#set page(
  paper: "a4",
  margin: (left: 22mm, right: 22mm, top: 20mm, bottom: 22mm),
  numbering: "1",
)

#set text(
  font: "Microsoft YaHei",
  size: 11.1pt,
  lang: "zh",
)

#set par(
  justify: true,
  leading: 1.05em,
  first-line-indent: 1.3em,
)

#set heading(numbering: none)
#show raw: set text(font: "Consolas", size: 8.8pt)
#show link: underline

#align(center)[
  #v(32mm)
  #text(size: 23pt, weight: "bold")[CCUSDT Replay Exchange 工程代码导读]

  #v(7mm)
  #text(size: 13pt)[从文件树到 fast backtest、Python Bot、Rust Runner 与事件日志]

  #v(14mm)
  #text(size: 10pt)[v0.1 / 2026-05-31]

  #v(4mm)
  #text(size: 9pt)[面向 Python 会一点、Rust 不熟的未来自己与新 Codex]
]

#pagebreak()

#outline(title: "目录", depth: 1)

#pagebreak()

#include "chapters/00-why-hard.typ"
#pagebreak()

#include "chapters/01-engineering-map.typ"
#pagebreak()

#include "chapters/02-data-lineage.typ"
#pagebreak()

#include "chapters/03-fast-backtest.typ"
#pagebreak()

#include "chapters/04-decision-frame-cache.typ"
#pagebreak()

#include "chapters/05-bot-owned-state.typ"
#pagebreak()

#include "chapters/06-python-bot.typ"
#pagebreak()

#include "chapters/07-rust-runner.typ"
#pagebreak()

#include "chapters/08-strict-lifecycle.typ"
#pagebreak()

#include "chapters/09-fast-vs-strict.typ"
#pagebreak()

#include "chapters/10-event-log.typ"
#pagebreak()

#include "chapters/11-experiment-routes.typ"
#pagebreak()

#include "chapters/12-do-not-edit-wrong-place.typ"
#pagebreak()

#include "chapters/appendix-entrypoints.typ"

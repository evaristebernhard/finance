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
#let evidence_note(body) = callout("证据边界", rgb("#f1fbfa"), rgb("#77aba6"), body)

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

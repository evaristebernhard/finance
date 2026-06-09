#let note(title, body) = block(
  fill: rgb("#f6f8fa"),
  inset: 8pt,
  radius: 3pt,
  stroke: rgb("#d0d7de"),
)[
  #text(weight: "bold")[#title]
  #body
]

#let factor(title, body) = block(
  inset: (x: 7pt, y: 6pt),
  stroke: (left: 2pt + rgb("#57606a")),
  fill: rgb("#fbfbfc"),
)[
  #text(weight: "bold")[#title]
  #body
]

#let formal(kind, title, body) = block(
  inset: (x: 8pt, y: 7pt),
  radius: 2pt,
  stroke: rgb("#8c959f"),
  fill: rgb("#f6f8fa"),
)[
  #text(weight: "bold")[#kind: #title]
  #body
]

#let definition(title, body) = formal("定义", title, body)
#let assumption(title, body) = formal("假设", title, body)
#let proposition(title, body) = formal("命题", title, body)
#let remark(title, body) = formal("备注", title, body)
#let evidence(title, body) = formal("证据", title, body)

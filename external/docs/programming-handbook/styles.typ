#import "../handbook/styles.typ": callout as handbook_callout, factbox as handbook_factbox, assumptionbox as handbook_assumptionbox, examplebox as handbook_examplebox, warningbox as handbook_warningbox, intuitionbox as handbook_intuitionbox, misconception as handbook_misconception, chapter_problem as handbook_chapter_problem, chapter_summary as handbook_chapter_summary, exercise as handbook_exercise, evidence_note as handbook_evidence_note
#import "../handbook/notation.typ": st as handbook_st, at as handbook_at, gt as handbook_gt, mt as handbook_mt, ct as handbook_ct, rtstate as handbook_rtstate, et as handbook_et, ft as handbook_ft, gamma as handbook_gamma, gammaof as handbook_gammaof, qt as handbook_qt, qof as handbook_qof, rt as handbook_rt, rof as handbook_rof, kappat as handbook_kappat, kappaof as handbook_kappaof, ut as handbook_ut, pt as handbook_pt, thetapool as handbook_thetapool, thetaroute as handbook_thetaroute, vt as handbook_vt, jt as handbook_jt, bt as handbook_bt, kt as handbook_kt, protocol_lang as handbook_protocol_lang, research_lang as handbook_research_lang, impl_lang as handbook_impl_lang

#let callout = handbook_callout
#let factbox = handbook_factbox
#let assumptionbox = handbook_assumptionbox
#let examplebox = handbook_examplebox
#let warningbox = handbook_warningbox
#let intuitionbox = handbook_intuitionbox
#let misconception = handbook_misconception
#let chapter_problem = handbook_chapter_problem
#let chapter_summary = handbook_chapter_summary
#let exercise = handbook_exercise
#let evidence_note = handbook_evidence_note

#let st = handbook_st
#let at = handbook_at
#let gt = handbook_gt
#let mt = handbook_mt
#let ct = handbook_ct
#let rtstate = handbook_rtstate
#let et = handbook_et
#let ft = handbook_ft
#let gamma = handbook_gamma
#let gammaof = handbook_gammaof
#let qt = handbook_qt
#let qof = handbook_qof
#let rt = handbook_rt
#let rof = handbook_rof
#let kappat = handbook_kappat
#let kappaof = handbook_kappaof
#let ut = handbook_ut
#let pt = handbook_pt
#let thetapool = handbook_thetapool
#let thetaroute = handbook_thetaroute
#let vt = handbook_vt
#let jt = handbook_jt
#let bt = handbook_bt
#let kt = handbook_kt
#let protocol_lang = handbook_protocol_lang
#let research_lang = handbook_research_lang
#let impl_lang = handbook_impl_lang

#let reading_goal(body) = handbook_callout("本章阅读目标", rgb("#f7fbff"), rgb("#93b7da"), body)
#let codewalk(body) = handbook_callout("代码阅读例", rgb("#eef7ff"), rgb("#7ea6d4"), body)
#let source_map_box(body) = handbook_callout("调用链 / 源码地图", rgb("#f7f7ff"), rgb("#8f8fd7"), body)
#let commandbox(body) = handbook_callout("CLI 实操", rgb("#eefaf1"), rgb("#7bb687"), body)
#let artifactbox(body) = handbook_callout("Artifact 读法", rgb("#f9f6ff"), rgb("#a185d7"), body)
#let checkpoint(body) = handbook_callout("你现在应该能解释什么", rgb("#f8fff8"), rgb("#94c994"), body)
#let changetask(body) = handbook_callout("最小改动任务", rgb("#fff8ef"), rgb("#d9a56c"), body)
#let crossrefbox(body) = handbook_callout("与理论教材的关系", rgb("#eef8fb"), rgb("#77aaa6"), body)

#let anchor_table(rows) = block(width: 100%)[
  #table(
    columns: (30%, 70%),
    inset: 6pt,
    stroke: 0.45pt + rgb("#cbcbcb"),
    fill: (x, y) => if y == 0 { rgb("#f2f2f2") } else { none },
    [代码锚点], [用途],
    ..rows
  )
]

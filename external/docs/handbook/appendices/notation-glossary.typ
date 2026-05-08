#import "../styles.typ": *
#import "../notation.typ": *

= 附录 A. 符号表：如何读本书的数学对象

#chapter_problem[
  这个附录专门解决“看到 #qt、#rt、#kappat 这种符号时到底该怎么读”的问题。它不是普通术语表，而是对象地位索引表。
]

#table(
  columns: (14%, 18%, 16%, 18%, 34%),
  inset: 6pt,
  stroke: 0.45pt + rgb("#c9c9c9"),
  fill: (x, y) => if y == 0 { rgb("#f3f3f3") } else { none },
  [符号], [中文名], [对象地位], [是否直接可观测], [如何理解],
  [#st], [统一核状态], [primitive], [否], [读作“时刻 t 的研究状态”，由六类 primitive 分量组成。],
  [#at], [动作], [control variable], [由策略选择], [读作“策略在时刻 t 做什么”。],
  [#gt], [机会几何状态], [primitive], [部分可观测], [池状态、路径、价格锚来源等。],
  [#mt], [提交态与执行推进状态], [primitive], [部分事件重建], [候选块推进、verified 路径和 output 成立背景。],
  [#ct], [竞争与传播环境], [primitive], [通常不可完整直接观测], [leader reachability、对手、传播视角等。],
  [#rtstate], [reserve/admissibility/survival 状态], [primitive], [部分规则可核对], [预算、delegation、admissibility 与 survival 来源。],
  [#et], [访问结构与冲突环境], [primitive], [部分事件重建], [account/storage access、热点与冲突来源。],
  [#ft], [费用状态], [primitive], [较多字段可直接观测], [base fee、bid、max fee cap 相关状态。],
  [#gamma], [毛机会投影], [projection], [否], [由几何、路径、规模和价格锚诱导。],
  [#qt], [入链概率投影], [projection / calibration], [否], [动作被 timely included 的 belief。],
  [#rt], [survival 投影], [projection / calibration], [否], [动作 included 后 survive 的 belief。],
  [#kappat], [冲突摩擦投影], [projection / calibration], [否], [冲突、热点与重执行造成的额外损失。],
  [#ut], [verified output 成立投影], [projection / calibration], [否], [当前 output 最终成立且一致的概率。],
  [#pt], [canonical 概率投影], [projection / calibration], [否], [当前候选路径最终成为 canonical 的概率。],
  [#thetapool], [pool-level 几何坐标], [reduced-form summary], [部分可读], [把不同 AMM 家族的 pool state 压成统一接口。],
  [#thetaroute], [route-level 上下文], [reduced-form summary], [通常不可完整直接读取], [router、vault、hook 和价格锚上下文。],
  [#jt], [一步收益对象], [derived object], [否], [给定状态和动作后的一步 act 价值。],
  [#vt], [价值函数], [derived object], [否], [比较 act/wait/abort 的 Bellman 对象。],
  [#kt], [转移核], [primitive model object], [否], [描述状态和收益如何随机转移。],
  [#bt], [belief], [derived object], [否], [在不完全信息下对世界状态的概率信念。],
)

#warningbox[
  如果一个对象是 projection，就不要把它写成协议字段；如果一个对象是 primitive，就不要因为暂时难观测而把它从研究对象中删除。
]

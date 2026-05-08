#import "../styles.typ": *
#import "../notation.typ": *

= 9. MEV 套利从毛机会到可执行机会

#chapter_problem[
  本章解释为什么套利不是“看到 #gamma 大于 0 就下单”。毛机会必须经过传播、验证、reserve、冲突和成本过滤，才会变成可执行机会。
]

== 9.1 从毛机会开始

设你已经通过 AMM 和外部价格计算得到：

```text
Gamma = 10
```

如果世界完全静止、没有别人、没有费用、没有失败风险，那么 10 就是收益。但真实世界不是这样。

== 9.2 第一性推导：为什么要乘上概率、减去摩擦

真正的一步收益可以写成：

$J_t = q_t times (u_t times r_t times Gamma_t - c_t - (1 - u_t times r_t) times L_t) - kappa_t$

这个公式不是“凭空更复杂”，而是逐层回答：

- #gamma：理论毛机会有多大？
- #qt：我能不能及时进入相关 block/world？
- #ut：当前可见 output 最终会不会被验证成立？
- #rt：进入后还能不能 survive？
- `c_t`：即便成功也要付多少钱？
- `L_t`：失败时会损失什么？
- #kappat：冲突、重执行和热点访问会额外吃掉多少？

这条式子真正做的不是“把一堆参数乘起来”，而是强迫我们承认三件事：

```text
毛机会 != 成功收益
成功收益 != 最终收益
最终收益 != 行动价值
```

#examplebox[
  例 1：同样的 $Gamma=10$，不同执行环境。

  ```text
  情形 A: q=0.8, u=0.9, r=0.9, c=2, L=3, kappa=0.5
  情形 B: q=0.3, u=0.6, r=0.7, c=2, L=3, kappa=2.0
  ```

  两个世界里的 “可执行机会” 完全不同。
]

#examplebox[
  例 2：只看 #gamma 会错。

  若 $Gamma=4, c=1, q=0.9, u=0.9, r=0.95, kappa=0.2$，可能值得 act。

  若 $Gamma=8, c=1, q=0.2, u=0.4, r=0.5, kappa=2$，可能反而不值得。
]

== 9.3 参数卡

#paramcard(
  [#qof($a$)],
  [入链概率],
  [概率，0 到 1],
  [projection / calibration target],
  [外部机制说明 + 建模假设 + proxy],
  [不能直接完整观测],
  [$q_t = 0.7$],
  [由 #mt/#ct 和动作 $a$ 共同诱导。],
  [高估会让策略错误相信“只要发出去就能进”。],
)

#paramcard(
  [#kappaof($a$)],
  [冲突摩擦损失],
  [收益单位],
  [projection / calibration target],
  [access event + 建模假设],
  [不能直接完整观测],
  [$kappa_t = 1.2$],
  [由热点账户、storage overlap、重执行等摩擦诱导。],
  [低估会在拥挤机会中系统性亏损。],
)

== 9.4 从毛机会到可执行机会的流程图

```text
AMM geometry
  -> Gamma
  -> inclusion filter (q)
  -> block/output filter (u)
  -> reserve/survival filter (r)
  -> deduct gas and failure loss
  -> deduct friction (kappa)
  -> act value
```

很多入门教程在 #gamma 这一步就停下来了，而本项目真正研究的是这条完整链条。

== 9.5 为什么 #kappat 不该被当作“小误差”

如果冲突只是在极少数情况下出现，把它吞进噪声也许还能容忍。  
但热点账户、storage overlap、局部拥挤和重执行会系统性出现，所以 #kappat 不是小装饰项，而是结构性对象。

== 9.6 对象地位

这里最重要的是不要把公式项混成一类：

- #gamma / #qt / #rt / #kappat / #ut 是 projection 或 calibration target。
- $c_t$ 的一部分可由 #ft 和动作直接算。
- `L_t` 往往是建模损失函数。
- 背后的 primitive 是 `G/M/C/R/E/F`。

#misconception[
  误解：#gamma 已经代表“机会最终有多好”。

  纠正：#gamma 只代表几何上的毛机会。可执行机会必须经过 #qt / #ut / #rt / #kappat / $c / L$ 的过滤。
]

#warningbox[
  反漂移提醒：#qt / #rt / #kappat / #ut 经常需要 synthetic 或校准输入。教材中必须把它们标成 projection/proxy/calibration，不能写成协议直接给定。
]

== 9.7 小结

#chapter_summary[
  MEV 套利从“有价差”到“值得 act”之间，还隔着传播、验证、survival、冲突和成本。这就是为什么本项目研究的是端到端套利系统，而不是某一个 AMM 公式。
]

== 9.8 练习题

#exercise[
  1. 概念题：为什么 #gamma 不能代表最终收益？

  2. 计算题：$Gamma=6, q=0.5, u=0.8, r=0.75, c=1, L=2, kappa=0.5$，求一步分数。

  3. 概念题：#kappat 更主要回指 #gt、#mt 还是 #et/#ct？

  4. 工程题：当前 CLI 哪一步开始把 primitive state 压成 decision state？
]

#import "../styles.typ": *
#import "../notation.typ": *

= 11. projection 与参数建模：为什么 #gamma/#qt/#rt/#kappat/#ut/#pt 不是 primitive

#chapter_problem[
  本章进一步解决“这些投影量到底该怎么组织”的问题。仅仅说它们不是 primitive 还不够，我们还要说明它们分别是 projection、proxy 还是 calibration target，以及它们如何从参数链条进入 Bellman。
]

== 11.1 三层参数链

参数建模总页给出统一分解：

$theta = (theta_("proto"), theta_("env"), theta_("cal"))$

其中：

- `theta_proto`：当前仓库代码或外部机制资料支撑的结构。
- `theta_env`：环境过程，如传播、对手、价格锚。
- `theta_cal`：最终通过数据、仿真或经验校准的对象。

== 11.2 从 primitive 到投影

统一链条是：

```text
primitive state (G/M/C/R/E/F)
  -> family/state compression
  -> projection / proxy
  -> compressed decision state
  -> Bellman score
```

例如：

- #gt -> `(f_t, theta_pool, theta_route)` -> #gammaof($P$, $x$)
- (#mt, #ct) -> `nu_t` -> #qof($a$)
- #rtstate -> `b_t, e_t` -> #rof($a$)
- (#et, #ct) -> `h_t, zeta_t` -> #kappaof($a$)

#examplebox[
  例 1：#qof($a$) 的来源不是“直接读取 txpool”。

  更合理写法是：

  ```text
  传播结构 + 竞争环境 + 动作 a
    -> inclusion belief
    -> q_t(a)
  ```

  provider 的 `txpool_*` 最多是弱代理。
]

#examplebox[
  例 2：#rof($a$) 的来源不是“我感觉大概 0.9”。

  更合理写法是：

  ```text
  reserve 规则事实 + 当前预算状态 + 动作 a
    -> admissibility / survival 结构
    -> r_t(a)
  ```
]

== 11.3 proxy 和 calibration target 为什么都不能偷换成真值

当你说“这个值先由 synthetic engine 提供”，真正的意思是：

```text
我们还没有更强观测，
所以先用一个明确标记过假设来源的值，
把研究闭环跑通。
```

这和“协议已经给出这个值”完全不同。

proxy 的第一性问题是：

```text
我是不是在用一个弱观测对象代替真实机制对象？
```

calibration target 的第一性问题是：

```text
这个值是不是只能通过回放、仿真、实验或经验拟合来选择？
```

== 11.4 参数卡

#paramcard(
  [`theta_("proto")`],
  [协议与实现给定结构],
  [结构化参数组],
  [parameter category],
  [当前仓库代码 + 官方资料],
  [部分可直接验证],
  [`reserve rule`, `commit state`, `pool family`],
  [先分清机制给定的部分，才能知道哪些还要估。],
  [若把协议给定和环境输入混在一起，会使校准无边界。],
)

#paramcard(
  [`theta_("env")`],
  [环境过程参数],
  [随机过程或情景轴],
  [parameter category],
  [外部机制说明 + 建模假设],
  [通常不能直接完整观测],
  [`leader reachability`, `competitor bid distribution`],
  [很多关键不确定性不在协议代码里，而在环境中。],
  [漏掉环境输入会把 projection 伪装成协议真值。],
)

#paramcard(
  [`theta_("cal")`],
  [最终校准对象],
  [需要实验、回放或数据拟合的参数],
  [calibration target],
  [建模假设 + 数据/仿真],
  [不能直接观测],
  [`synthetic q/r/kappa/u` 的标定值],
  [校准阶段是把模型接回数据，而不是宣称协议直接给出参数。],
  [若不显式标记校准对象，读者会误把示例数值当真值。],
)

== 11.5 decision state 为什么还要带 evidence / role / strength

如果压缩态里只剩：

```text
Gamma = 10
q = 0.7
r = 0.9
```

读者会本能地以为这三个数属于同一层、同样可靠。  
所以当前 workspace 设计强调：

```text
value + evidence + role + strength + assumptions
```

不是为了格式好看，而是为了阻止对象地位在压缩阶段丢失。

== 11.6 常见误解

#misconception[
  误解：只要一个数值最后要进 Bellman，它就必须出现在 primitive state 里。

  纠正：Bellman 输入通常是压缩态。压缩态可以包含 projection 和 calibration 数值，但这些数值的对象地位不会因此升级为 primitive。
]

#warningbox[
  反漂移提醒：synthetic engine 给出的 `q/r/kappa/u/p/Gamma` 只能写成 `ModelingAssumption`、`Latent`、`RpcWeakProxy` 或其他明确标签，不能写成协议直接给定。
]

== 11.7 小结

#chapter_summary[
  本章的核心不是“多加几个参数”，而是把每个参数重新放回：协议给定、环境输入、最终校准这条链里。只有这样，decision state 才不会变成“看起来很精确、实际上没有对象边界”的黑箱向量。
]

== 11.8 练习题

#exercise[
  1. 概念题：`theta_proto`、`theta_env`、`theta_cal` 的区别是什么？

  2. 概念题：为什么 provider `txpool_*` 最多只能作为 #qt 的弱代理？

  3. 工程题：当前手册中哪一章解释了 #gamma/#qt/#rt/#kappat/#ut/#pt 不是 primitive？

  4. 反思题：为什么 compressed decision state 需要保留 evidence/role/strength？
]

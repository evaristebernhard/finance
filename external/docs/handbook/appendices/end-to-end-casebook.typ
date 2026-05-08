#import "../styles.typ": *
#import "../notation.typ": *

= 附录 I. 端到端案例：从 snapshot 到 eval 读懂一条完整研究闭环

#chapter_problem[
  这一附录把当前仓库的研究闭环走一遍，目标是让读者看到：从 pool snapshot、normalized events、decision state、Bellman decision 到 replay/eval，每一步到底在研究哪类对象。
]

== I.1 第一步：snapshot 解决什么问题

`snapshot` 读取的是局部可观测 pool state。  
它回答：

```text
当前 AMM 几何长什么样？
```

它不会直接回答：

```text
这笔交易会不会入链？
会不会 survive？
会不会冲突？
```

== I.2 第二步：ingest-events 解决什么问题

`ingest-events` 引入 normalized execution event 文件。  
它的作用是增强：

- #mt 的可见性。
- #et 的可见性。
- #rtstate 的局部识别。

它仍然不会直接产出 #qt/#rt/#kappat/#ut/#pt 的真值。

== I.3 第三步：build-decision-state 为什么是桥梁

`build-decision-state` 是当前闭环里最关键的一步，因为它完成了：

```text
primitive state
  + route candidate
  + synthetic / reduced-form projection
  ->
compressed decision state
```

这意味着策略层不再直接吃 raw observation，而是吃经过对象地位整理后的输入。

== I.4 一个教学用压缩态例子

假设压缩态里有：

```text
family = cpmm
theta_pool = ...
theta_route = ...
Gamma = 10
q = 0.7
r = 0.9
u = 0.8
kappa = 1.2
gas_limit = 180000
bid = 5
max_fee = 30
```

正确读法：

- `family/theta_*`：几何与路径上下文。
- #gamma/#qt/#rt/#ut/#kappat：projection 或 calibration。
- `gas_limit/bid/max_fee`：动作参数或策略建议。

错误读法：

```text
这些都是链上直接给出的真值字段
```

== I.5 第四步：decide 真正在比较什么

`decide` 不是“看一个数字大不大”，而是在比较：

- act
- wait
- abort

其核心输入不是某一个 pool 价格，而是整条 decision state。

== I.6 第五步：paper-execute 为什么仍然重要

虽然 `paper-execute` 不做实盘执行，但它完成两件关键事情：

1. 生成可复现的执行记录。
2. 为 replay/eval 准备研究对象。

这使得策略不再停留在纸面公式，而能形成可回放、可比较、可评估的实验链。

== I.7 第六步：replay 为什么不是“再跑一次”

`replay` 的意义不是重复执行，而是：

```text
在给定 event / seed / route 的条件下，
复算某次决策在该研究世界里的结果
```

这一步是识别和校准的基础，因为它把事后结果和事前决策连接起来。

== I.8 第七步：eval 为什么重要

`eval` 给出：

- PnL
- risk

它让整个研究链条不只停在“我会做什么”，而走到“这样做之后表现如何”。

== I.9 这条闭环到底学到了什么

如果你能完整理解：

```text
snapshot
 -> events
 -> primitive
 -> projection
 -> decision state
 -> decide
 -> paper-execute
 -> replay
 -> eval
```

你就已经理解了本项目的第一性主线：

```text
从观测走到决策，再走到评估
```

#chapter_summary[
  这个端到端案例的目的是把所有章节收束成一条具体流程。只要读者能顺着这条链说清楚“每一步输入是什么、对象地位是什么、输出又是什么”，教材就真正开始发挥作用了。
]

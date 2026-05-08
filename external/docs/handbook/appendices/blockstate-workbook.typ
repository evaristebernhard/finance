#import "../styles.typ": *
#import "../notation.typ": *

= 附录 G. Block-state 推理工作册：你在每个时刻到底知道什么

#chapter_problem[
  这一附录训练读者区分：事件事实、状态重建、belief 和事后结果。目标不是增加新术语，而是把“我到底知道什么”训练到足够敏感。
]

== G.1 只看到 `BlockStart`

观测：

```text
t1: BlockStart(A)
```

你能确认什么？

- `A` 已进入某条执行/推进路径。
- 你开始获得关于相关世界分支的信息。

你不能确认什么？

- 不能确认 #pt = 1。
- 不能确认 #ut = 1。
- 不能确认 `A` 已经等于最终真实世界。

== G.2 看到 `BlockQC`

观测：

```text
t1: BlockStart(A)
t2: BlockQC(A)
```

相较上一题，信息增强了：  
你知道 `A` 在推进结构中更进一步。  
但这仍然不是 verified。

== G.3 同高度两个候选块

观测：

```text
t1: BlockStart(A)
t2: BlockStart(B)
t3: BlockQC(A)
```

问题：

1. 为什么“同高度存在多个候选块”对策略是重要信息？
2. 为什么此时同一个 AMM 机会不能被看成“固定收益数字”？

== G.4 事前 belief 与事后校准

设在 `t3` 时刻，你估计：

```text
p_t(A) = 0.7
u_t(A) = 0.65
```

后来看到：

```text
t4: BlockFinalized(A)
t5: BlockVerified(A)
```

你现在可以做的是：

- 用事后结果校准早先的估计。

你不该做的是：

- 回过头假装 `t3` 时刻根本没有不确定性。

== G.5 provider 视角与机制视角

若某 provider 告诉你：

```text
finalized
```

这可以作为很有价值的运营信息，但它不自动等于完整 commit-state 结构。  
教材里必须把这类对象放在 proxy 或辅助视角，而不是直接写成机制真值。

== G.6 一个综合案例

```text
t1: BlockStart(A)
t2: BlockStart(B)
t3: BlockQC(A)
t4: provider still shows pending local view
t5: BlockFinalized(A)
```

你在 `t3` 的任务不是写一句“世界已确定”，而是判断：

- 当前信息是否足以提高 #pt？
- 当前 output 的 #ut 是否随之提高？
- provider pending 视图属于事实、proxy 还是校准线索？

#chapter_summary[
  只要你持续区分“事实 / 重建 / proxy / belief”，Block-state 这一层就不会再显得像抽象黑箱，而会变成可推理的对象结构。
]

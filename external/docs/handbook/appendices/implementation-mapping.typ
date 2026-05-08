#import "../styles.typ": *
#import "../notation.typ": *

= 附录 D. 从研究对象到当前代码与 CLI 的映射

#chapter_problem[
  这一附录解释研究语言、实现语言和流程语言之间的关系。否则读者很容易把 CLI 输出误当理论 primitive，或者把理论 projection 误当协议字段。
]

== D.1 三套语言

- 协议语言：合约字段、事件名、文件路径、JSON 键。
- 研究语言：#st、#at、#gamma、#qt、#rt、#kappat、#ut、#pt 等对象。
- 实现语言：Rust 类型、CLI 命令、artifact 文件。

== D.2 当前 CLI 主线

```text
snapshot
  -> ingest-events
  -> build-decision-state
  -> decide
  -> paper-execute
  -> replay
  -> eval
```

=== 它们分别做什么

1. `snapshot`：读取局部可观测池状态。
2. `ingest-events`：引入 normalized execution events。
3. `build-decision-state`：把 primitive、route、projection 压成策略输入。
4. `decide`：比较 act / wait / abort。
5. `paper-execute`：生成执行记录。
6. `replay`：复算结果。
7. `eval`：生成 PnL 和 risk。

== D.3 为什么输出里要保留 evidence / role / strength

如果输出只剩下：

```json
{ "Gamma": 10, "q": 0.7, "r": 0.9 }
```

读者会默认这三个数是同层真值。  
而当前设计保留 evidence/role/strength，正是为了把对象地位嵌回 artifact。

== D.4 正确读 artifact 的方式

当你看到：

```text
family
theta_pool
Gamma
q
r
u
kappa
gas_limit
bid
max_fee
```

正确读法是：

- `family/theta_*`：几何与路径上下文。
- #gamma/#qt/#rt/#ut/#kappat：投影或 calibration。
- `gas_limit/bid/max_fee`：策略相关输入。

== D.5 为什么当前闭环对学习更好

paper closed loop 把高风险基础设施问题先拿掉，让你先看清：

- primitive 怎么构造。
- projection 怎么生成。
- Bellman 怎么比较动作。
- replay 和 eval 如何形成研究验证链。

#chapter_summary[
  这个附录的目标是把研究对象、实现类型和 CLI 流程钉在一起。只有这三层对应清楚，读者才不会混淆“世界是什么”“代码怎么表示”“流程怎么跑”。
]

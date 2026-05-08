#import "../styles.typ": *
#import "../notation.typ": *

= 附录 H. Reserve 与动作集工作册：什么时候动作根本不该进优化问题

#chapter_problem[
  这个附录训练读者把“低收益动作”和“不可行动作”严格分开。前者仍属于优化问题，后者应该在动作集阶段就被排除。
]

== H.1 简单预算检查

给定：

```text
b = 90
c_gas = 30
m1 = 20
m2 = 15
```

则：

$30 + 20 + 15 = 65 <= 90$

该动作可行。

== H.2 刚好触边界

给定：

```text
b = 90
c_gas = 40
m1 = 25
m2 = 25
```

则：

$40 + 25 + 25 = 90$

动作在边界上仍可行，但安全边际为零。

== H.3 明显不可行

给定：

```text
b = 90
c_gas = 50
m1 = 25
m2 = 25
```

则：

$50 + 25 + 25 = 100 > 90$

此时问题不是“收益变低”，而是“动作根本不在 admissible set 中”。

== H.4 同样 #gamma，不同 budget

设两个搜索者都看到：

```text
Gamma = 8
```

但：

```text
A: b=120, c_gas=45, m1=20, m2=10
B: b=70,  c_gas=45, m1=20, m2=10
```

则 A 的动作可能可行，B 的动作在预算层面已出局。  
这说明“同一个机会”不自动对应“同一个可行动作集合”。

== H.5 为什么 budget feasible 不等于 survive

即便预算可行，动作也不一定 survive。  
因为 #rt 还吸收了：

- admissibility 之外的状态条件。
- 执行后状态是否仍满足规则。
- 机会是否在执行路径中消失。

所以：

```text
budget feasible
  !=
survival guaranteed
```

== H.6 综合例子

设：

```text
Gamma = 10
q = 0.8
u = 0.8
r = 0.7
kappa = 1
L = 2
```

比较两个场景：

```text
场景 A: c_gas = 2, budget 足够
场景 B: c_gas = 5, budget 不足
```

场景 A 中 act 仍可能为正；场景 B 中动作甚至不该进入比较。

#chapter_summary[
  这个工作册的目标是把“先过规则门槛，再谈收益”训练成习惯。只要这一步不出错，读者对 #rtstate、#rt 和可行动作集合的理解就不会漂移。
]

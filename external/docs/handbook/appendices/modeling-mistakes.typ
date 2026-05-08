#import "../styles.typ": *
#import "../notation.typ": *

= 附录 F. 常见错误建模方式与纠正

#chapter_problem[
  这一附录集中列出本项目最常见的建模漂移点。很多错误不是公式不会算，而是对象地位错了、证据边界错了、数学语言错了。
]

== F.1 错误一：把数学对象写成代码对象

错误写法：

```text
`q_t`
`r_t(a)`
`Gamma`
```

这会让读者潜意识里把它们当成：

- 配置项
- JSON 键
- 协议字段

而不是研究对象。

正确做法：

- 正文叙述里用 #qt、#rt、#gamma。
- 只有在讨论错误写法、文件路径、CLI、JSON 时才保留反引号。

== F.2 错误二：把能读到的字段当成全部研究对象

错误逻辑：

```text
RPC 里能读到 reserve0/reserve1
所以研究对象只需要 reserve0/reserve1
```

正确逻辑：

```text
研究对象先于数据面
如果 block state、传播、reserve、冲突会改变行动价值，
即使暂时不能完整观测，也必须保留对应 primitive
```

== F.3 错误三：把 #gamma 当成最终收益

错误逻辑：

```text
Gamma > 0
所以 act
```

正确逻辑：

```text
Gamma
  -> q / u / r 过滤
  -> 扣 gas / L / kappa
  -> 再比较 wait / abort
```

== F.4 错误四：把 #qt 当作协议直接给定

错误逻辑：

```text
我看到了 txpool 或 provider pending 视图
所以我知道 q
```

正确逻辑：

```text
provider 视图最多是弱代理
q_t(a) 仍是由传播与竞争结构诱导的 projection
```

== F.5 错误五：把 #rt 当作“经验感觉值”

错误逻辑：

```text
r_t(a) 大概写 0.9 就行
```

正确逻辑：

```text
先问 reserve / admissibility / survival 结构来自什么规则与状态，
再决定如何构造投影或校准值
```

== F.6 错误六：把 #kappat 当作小噪声

错误逻辑：

```text
冲突只是偶发误差
```

正确逻辑：

```text
热点账户、storage overlap、重执行
在局部拥挤机会里会系统性出现
因此 kappa_t 不能被平均掉
```

== F.7 错误七：把 synthetic calibration 写成协议事实

错误逻辑：

```text
当前代码里给了 q=0.7
```

正确逻辑：

```text
当前 workspace 用 synthetic engine / modeling assumption
生成了一个例子值 q=0.7
```

== F.8 错误八：把 paper execution 当实盘执行

错误逻辑：

```text
CLI 已有 paper-execute
所以已经是交易机器人
```

正确逻辑：

```text
当前闭环解决的是研究问题：
观测 -> 状态 -> 投影 -> 决策 -> 回放 -> 评估
不是 live signer/broadcaster/executor
```

== F.9 这个附录怎么用

建议读法：

1. 每读完一章，对照本附录检查自己有没有犯相应漂移。
2. 每看到一个数值，先问它是事实、projection、proxy 还是 calibration。
3. 每看到一个公式，先问它回答的是“世界是什么”，还是“世界诱导出什么”。

#chapter_summary[
  错误建模最常见的根源不是数学太少，而是对象地位混乱。只要持续区分事实、假设、proxy、projection 和 calibration，本教材的主线就不会漂移。
]

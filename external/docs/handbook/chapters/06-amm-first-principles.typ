#import "../styles.typ": *
#import "../notation.typ": *

= 6. AMM 从第一性原理开始：为什么池子能报价

#chapter_problem[
  本章不先背 CPMM 公式，而是从“没有做市商怎么办”推导出 AMM 为什么需要池子、流动性和不变量。
]

== 6.1 没有 AMM 的双人交易

在传统交易里，Alice 想用 X 换 Y，需要找到 Bob：

```text
Alice: wants to sell X
Bob: wants to buy X and sell Y
```

如果 Bob 不在线，交易无法发生。如果市场很薄，Alice 必须接受很差价格。

AMM 的想法是：让合约池永远站在另一边报价。

```text
Pool = {
  X reserve,
  Y reserve,
  pricing rule,
}
```

#examplebox[
  例 1：没有池子。

  Alice 想卖 10 X，但没有买家，交易价格无法形成。
]

#examplebox[
  例 2：有池子。

  池子持有 `X=1000, Y=1000`。Alice 可以随时向池子放入 X，按规则取出 Y。
]

== 6.2 第一性推导：为什么需要不变量

如果池子随便报价，流动性会被瞬间掏空。因此需要规则约束交易前后状态。这个规则就是不变量。

CPMM 的不变量是：

$x dot y = k$

Stable AMM 和 weighted AMM 使用不同几何，但第一性问题相同：

```text
如何让池子在任何交易规模下都能给出一致报价？
如何让价格随库存变化自动调整？
如何避免一笔交易把池子免费掏空？
```

== 6.3 边际价格、平均价格、滑点

如果交易很小，你关心边际价格；如果交易很大，你关心平均价格。

```text
边际价格：下一点点交易的价格
平均价格：整笔交易的总输入 / 总输出
滑点：平均价格相对初始边际价格变差多少
```

#paramcard(
  [`slippage`],
  [滑点],
  [百分比或价格差],
  [projection，来自 #gt],
  [AMM 数学 + 当前 pool state],
  [由状态和交易规模计算，不是独立链上字段],
  [`初始价=1, 平均成交=1.02, 滑点=2%`],
  [交易改变池子库存，库存变化改变后续报价。],
  [低估滑点会高估 #gamma 和最优规模。],
)

== 6.4 为什么库存会自动变成价格

如果池子持有库存，就必须回答一个问题：

```text
当有人拿走一部分 Y、放入一部分 X 后，
下一位交易者为什么不能继续按原价成交？
```

第一性答案是：因为库存本身就是约束。  
一旦库存变化，池子“还能拿出多少另一种资产”这个事实就变了，所以报价也必须随之变化。

这意味着价格在 AMM 里不是外部贴在池子上的标签，而是：

```text
pool state 的函数
```

#examplebox[
  数值例：池子中 `X=1000, Y=1000` 时，边际上接近 1:1。

  若一笔大交易拿走很多 Y，则池里剩余的 Y 更稀缺。若下一位交易者还能按旧价格继续买 Y，池子会被快速掏空。因此价格必须上升。
]

== 6.5 为什么需要外部价格锚

池子只知道自己内部愿意怎么换。套利者要知道的是：

```text
池内价格和外部参考价格的差
```

所以 #gamma 从来都不是“只靠池子自己就能吐出来”的字段。  
更准确的理解是：

```text
pool geometry
  + route context
  + outside reference
  -> gross opportunity
```

因此 #gamma 是 projection，而不是 primitive。

== 6.6 AMM 在本项目中的对象地位

AMM pool state 属于 #gt 的一部分。AMM 机会不是 primitive，而是投影：

$Gamma_t(P, x) = g_Gamma(s_t, P, x)$

$P$ 是路径，`x` 是规模。不同 pool 家族通过 #thetapool 和 #thetaroute 进入 #gamma。

#warningbox[
  反漂移提醒：AMM 公式可以直接来自协议数学，但套利毛机会 #gamma 仍然是 projection，因为它还依赖路径、规模、外部价格锚和建模边界。
]

== 6.7 常见误解

#misconception[
  误解：AMM 价格就是 `reserve_y / reserve_x`，所以所有交易都按这个价格成交。

  纠正：`reserve_y / reserve_x` 更像初始边际价格。大额交易会沿曲线移动，平均成交价会更差。
]

== 6.8 对象地位回收

#factbox[
  本章最重要的对象地位关系是：

  - reserves、liquidity、tick、weights 等属于 #gt 的局部状态。
  - 滑点和 #gamma 是由这些状态与交易规模诱导出来的对象。
  - 如果教材把 #gamma 写成和 JSON 字段一样的样子，读者就会自然误解为“直接可读值”。
]

== 6.9 小结

#chapter_summary[
  AMM 的第一性问题是“没有对手方时如何持续报价”。答案是：用池子提供库存，用不变量定义可接受交易，用库存变化自动调整价格。
]

== 6.10 练习题

#exercise[
  1. 概念题：为什么 AMM 需要不变量？

  2. 概念题：边际价格和平均价格有什么区别？

  3. 计算题：若初始价格为 1，平均成交价格为 1.05，滑点是多少？

  4. 工程题：在 `external/amm-official` 中找到 Uniswap v2 的本地锚点目录。
]

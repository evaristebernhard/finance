#import "../styles.typ": *
#import "../notation.typ": *

= 8. CLMM / Stable / Weighted / Hooked AMM 的几何差异

#chapter_problem[
  本章回答：为什么不能把所有 AMM 都写成 CPMM？如果 AMM 家族的几何不同，那么投影 #gamma 和压缩坐标 #thetapool / #thetaroute 就必须分家族建模。
]

== 8.1 CLMM：集中流动性

CLMM 代表是 Uniswap v3 风格池。本地官方锚点包括：

- `external/amm-official/uniswap-v3-core/contracts/UniswapV3Pool.sol`
- `external/amm-official/uniswap-v3-core/contracts/libraries/TickMath.sol`

CLMM 的价格结构主要由：

- `sqrtPriceX96`
- tick
- active liquidity
- liquidity by tick
- fee tier

决定。

#examplebox[
  例 1：CLMM 局部流动性。

  当前价格在 tick 0，active liquidity = 1,000,000。

  如果小额交易不跨 tick，曲线可近似平滑；一旦跨越 tick，下一段 liquidity 变化，价格响应会突然改变。
]

== 8.2 Stable：近锚定曲线

Stable AMM 代表是 Curve stableswap 和 Balancer StablePool。本地锚点包括：

- `external/amm-official/curve-core/contracts/amm/stableswap`
- `external/amm-official/balancer-v3-monorepo/pkg/pool-stable/contracts/StablePool.sol`

其核心对象不只是 reserves，而是：

- balances
- amplification
- peg / rate state

#examplebox[
  例 2：stable 池的直觉。

  对 USDC/USDT 这类接近锚定的资产，小额交易时曲线很平，滑点非常低；一旦把池子打偏很多，曲线会迅速变陡。
]

== 8.3 Weighted：多资产权重池

Weighted pool 由 balance vector 和 normalized weights 决定几何。例如：

```text
Token A weight = 80%
Token B weight = 20%
```

这意味着相同 balance 下，价格响应和 50/50 双资产池不同。

== 8.4 Hooked CLMM：路径上下文变强

Uniswap v4 风格 hooked CLMM 在 CLMM 基础上增加：

- hook callbacks
- dynamic fee
- callback-induced state

这使得 #thetaroute 变得重要，因为同一池状态下，不同 hook/route 可能导出不同成本和冲突结构。

== 8.5 为什么需要家族化坐标

统一写法是：

$Gamma_t(P, x; f_t, theta_t^("pool"), theta_t^("route"))$

其中：

- `f_t`：协议家族标签。
- `theta_pool`：pool-level geometry。
- `theta_route`：route-level context。

#paramcard(
  [`f_t`],
  [协议家族标签],
  [离散集合标签],
  [compressed state / reduced-form summary],
  [协议类型 + 当前观测],
  [通常可从 pool family 识别],
  [`cpmm`, `clmm`, `stable`, `weighted`, `hooked-clmm`],
  [先知道你面对的是哪类几何，才谈压缩和最优控制。],
  [错误家族分类会让整个 #gamma 模型失效。],
)

#paramcard(
  [`theta_t^("pool")`],
  [pool-level 几何坐标],
  [向量或结构体],
  [reduced-form summary / proxy],
  [协议状态 + 建模压缩],
  [部分字段可直接读取，整体坐标需压缩],
  [`cpmm: reserves`; `clmm: tick+liquidity`; `stable: amplification+balances`],
  [不同 AMM 家族进入统一控制模型的接口。],
  [压缩过度会抹掉关键几何特征。],
)

== 8.6 同一个“买 10 单位”，在不同家族里为什么不是同一问题

对 CPMM 来说，“买 10 单位”主要意味着沿同一条光滑曲线移动。  
对 CLMM 来说，它可能意味着：

- 仍停留在当前 tick 区间。
- 或者跨过一个 tick 边界，进入另一段 liquidity。

对 stable AMM 来说，它可能意味着：

- 还在锚定附近的低滑点区。
- 或者已把池子打到更陡区间。

对 weighted AMM 来说，它还同时受权重影响。

#examplebox[
  反例：如果把所有 AMM 都用“当前 reserves 的比例”来估价，在 CPMM 局部也许还能凑合，在 CLMM 和 stable 上会迅速失真，因为价格响应结构已经不同。
]

== 8.7 哪些可以统一，哪些不能统一

可统一的：

- 都有 pool state。
- 都需要 pricing rule。
- 都可以比较链上价格与外部锚。
- 都会随规模增大出现曲率成本。

不能强行统一的：

- 局部坐标。
- 滑点曲线形状。
- route-level 上下文复杂度。
- dynamic fee / hook / vault 的外溢方式。

== 8.8 常见误解

#misconception[
  误解：CLMM 只是“更高级的 CPMM”，所以仍然可以用同一个 `A_t/B_t` 解释。

  纠正：CLMM 的几何本质是分段 liquidity 和 tick 结构，只有在极局部范围才可能近似二次化。
]

#warningbox[
  反漂移提醒：本版教材不展开 CLOB、intent、aggregator。它们只能作为“本版不覆盖的 venue”边界说明，不能被塞回 AMM #gamma 中。
]

== 8.9 对象地位回收

#factbox[
  家族化建模的意义不是“把公式写复杂”，而是承认不同 AMM 家族的几何对象本来就不同。  
  `f_t + theta_pool + theta_route` 的存在，是为了保存差异，而不是为了装饰公式。
]

== 8.10 小结

#chapter_summary[
  不同 AMM 家族有不同几何，因此统一建模的关键不是“强行统一公式”，而是保留 `f_t + theta_pool + theta_route` 这套家族化接口。
]

== 8.11 练习题

#exercise[
  1. 概念题：为什么 CLMM 的关键对象不是 `(reserve0, reserve1)`？

  2. 概念题：stable AMM 为什么在锚定附近滑点更低？

  3. 概念题：为什么 weighted pool 不能简单当成 50/50 的 CPMM？

  4. 工程题：在 `external/amm-official` 中指出一个 stable 池和一个 weighted 池锚点路径。
]

# 第一性原理下的投影结构建模

## 目的
恢复并统一前面已经得到的第一性原理推导，但把它们放回 unified kernel 主线之下。  

这篇文档的角色不是重新定义主模型，而是说明：

$$
\text{在 unified kernel 给定后，哪些常见量可以由机制、代码与环境过程结构性推出。}
$$

## 重要限定
以下公式与分解是**建模推导**，不等于代码中的逐行协议实现。  
特别是 `q_t(a)` 和 `r_t(a)` 的展开，必须同时区分：

- 当前仓库代码已经给出的行为事实
- 依赖外部机制说明的结构假设
- 为了进入控制问题而做的 reduced-form 抽象

## 与主线的关系
统一核的 primitive 仍然只有：

$$
s_t=(G_t,M_t,C_t,R_t,E_t,F_t),\qquad
a_t=(P_t,x_t,\ell_t,\pi_t,\overline F_t,d_t),
$$

以及

$$
\mathcal K_t(ds',dy\mid s_t,a_t),\qquad
b_t=\Pr(s_t\mid\mathcal F_t^{\mathrm{obs}}).
$$

这篇文档只推导这些对象诱导出来的 projection 与局部坐标：

- $p_t,u_t$
- $q_t(a)$
- $r_t(a)$
- $\kappa_t(a)$
- $\Gamma_t(P,x)$

如果需要“参数定义 -> 当前仓库已验证 / 外部机制说明 -> 环境输入 -> 校准对象”的连续主链，请先读 [参数建模总页](./30-parameter-map.md)。  
本页只保留更密的推导。

## 一、哪些量应该先由第一性原理决定
更合理的分层是：

$$
\theta=(\theta_{\mathrm{proto}},\theta_{\mathrm{env}},\theta_{\mathrm{cal}}),
$$

其中：

- $\theta_{\mathrm{proto}}$：当前仓库代码与外部机制资料直接给定的结构
- $\theta_{\mathrm{env}}$：环境过程，需要作为随机过程或情景轴进入
- $\theta_{\mathrm{cal}}$：以后再由真实观测校准的对象

在本项目里，更适合放进 $\theta_{\mathrm{proto}}$ 的包括：

- block-related execution event 与 commit-state 重建
- reserve-balance 规则与 revision gating
- access tracking 与 tx-level execution event
- base fee 相关 header 事实

而下面这些当前仍需要更多外部共识资料或环境输入：

- local mempool / future leaders / forwarding / retry
- 竞争者群体与出价分布
- 外部价格锚与订单流环境

## 二、block / verification 投影：$p_t,u_t$
对应 [参数建模总页](./30-parameter-map.md) 中的“block / verification 参数组”。

### 当前仓库已验证
当前工作区可直接核对：

- `BlockQC / BlockFinalized / BlockVerified`
- `CommitStateBlockBuilder` 对 `Proposed / Voted / Finalized / Verified` 的重建

### 1. canonical 概率
对当前候选块 $b$，定义：

$$
p_t(b)=\Pr(b\text{ 最终 canonical}\mid \mathcal F_t^{\mathrm{obs}}).
$$

这不是任意自由参数，而是 block-state 机制的吸收概率投影：

$$
p_t = g_p(s_t),
$$

其中主要回指到 $M_t$。

### 2. output / verification 概率
设当前本地可见 execution output 为 $X_b^{\mathrm{loc}}$，最终 verified output 为 $X_b^{\mathrm{ver}}$。则

$$
u_t(b)
=
\Pr\left(X_b^{\mathrm{loc}}=X_b^{\mathrm{ver}},\ b\text{ canonical}\mid \mathcal F_t^{\mathrm{obs}}\right).
$$

常用分解是：

$$
u_t(b)=p_t(b)\,d_t(b),
$$

其中

$$
d_t(b)
=
\Pr\left(X_b^{\mathrm{loc}}=X_b^{\mathrm{ver}}\mid b\text{ canonical},\mathcal F_t^{\mathrm{obs}}\right).
$$

也就是说，$u_t$ 不是独立 primitive，而是 $M_t$ 中 block state 与 output verification 子结构的投影。

## 三、传播-入链投影：$q_t(a)$
对应 [参数建模总页](./30-parameter-map.md) 中的“propagation / inclusion 参数组”。

### 重要限定
这一节的传播结构主要依赖外部共识资料与建模抽象。  
当前 execution 仓库能确认的是边界条件，而不是完整传播机制。

对动作 $a$，定义：

$$
q_t(a)=\Pr(\mathrm{included}\mid s_t,a).
$$

在 local mempool / leader-path 机制下，可把每次尝试索引为

$$
(m,j),\qquad m=1,\dots,K,\ \ j=1,\dots,N,
$$

其中：

- $m$：第 $m$ 轮重发
- $j$：该轮里的第 $j$ 个 future leader

定义事件

$$
E_{m,j}=A_{m,j}\cap B_{m,j}\cap C_{m,j}\cap D_{m,j},
$$

分别表示：

- $A_{m,j}$：消息在截止前送达
- $B_{m,j}$：通过本地检查与接受
- $C_{m,j}$：未在提块前被驱逐
- $D_{m,j}$：最终被 leader 选入块

则：

$$
q_t(a)
=
\Pr\left(\bigcup_{m=1}^{K}\bigcup_{j=1}^{N}E_{m,j}\,\middle|\, s_t,a\right).
$$

在条件独立近似下：

$$
q_t(a)
\approx
1-\prod_{m=1}^{K}\prod_{j=1}^{N}(1-e_{m,j}),
\qquad
e_{m,j}:=\Pr(E_{m,j}\mid s_t,a).
$$

这里的结构意义在于：  
`q_t(a)` 是用来表达传播与竞争如何进入控制问题的建模对象，而不是当前仓库可直接读取的协议真值。

## 四、reserve / survival 投影：$r_t(a)$
对应 [参数建模总页](./30-parameter-map.md) 中的“reserve / survival 参数组”。

### 当前仓库已验证
当前代码能直接支撑：

- reserve tracking 的 revision gating
- delegated account 限制
- pending-block 与当前块环境检查
- init selfdestruct exemption
- max reserve 当前的占位逻辑

### 建模抽象
定义：

$$
r_t(a)=\Pr(\mathrm{survive}\mid s_t,a,\mathrm{included}).
$$

在 Monad 风格 reserve 结构下，更自然的分解是：

$$
r_t(a)=\chi_t(a)\,\rho_t(a),
$$

其中：

- $\chi_t(a)$：admissibility
- $\rho_t(a)$：执行后是否满足 reserve survival 规则

这条分解的意义是把“当前代码给出的 reserve 规则事实”压成控制模型里的 survival projection，而不是声称代码里已经有名为 `r_t(a)` 的字段。

## 五、冲突摩擦投影：$\kappa_t(a)$
对应 [参数建模总页](./30-parameter-map.md) 中的“conflict / friction 参数组”。

定义：

$$
\kappa_t(a)=\mathbb E[\mathrm{friction\ loss}\mid s_t,a].
$$

当前仓库给出的强锚点来自：

- `AccountAccess`
- `StorageAccess`
- `TxnReject`
- `TxnCallFrame`
- `TxnEvmOutput`

它们让访问重叠、执行路径和失败轨迹具备更强可见性，但损失函数本身仍需要建模和校准。

## 六、AMM 投影：$\Gamma_t(P,x)$
对应 [参数建模总页](./30-parameter-map.md) 中的“机会几何参数组”。

对路径 $P$ 与规模 $x$，定义：

$$
\Gamma_t(P,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})=g_\Gamma(s_t;P,x).
$$

这一节保留 AMM 几何推导的意义，在于说明：

- 机会几何应被当作 $G_t$ 的 projection
- 它进入控制问题前，会被 Monad 机制产生的 `q_t/r_t/\kappa_t/u_t` 重写

因此，AMM edge 并不是直接进入决策，而是先通过 unified kernel 被过滤和压缩。

### 1. `cpmm`：常数乘积基线
这一类由 `Uniswap v2` 风格双资产常数乘积池代表。  
当前本地锚点包括：

- `external/amm-official/uniswap-v2-core/contracts/UniswapV2Pair.sol`
- `external/monad-official/protocols/testnet/Uniswap.json`

这类池最自然的 pool-level 状态是：

- reserves
- swap fee
- price cumulative

因此，`cpmm` 允许直接使用局部二次基线：

$$
\Gamma_t(P,x)\approx A_t x-B_t x^2.
$$

这里的 `A_t,B_t` 是零阶近似最干净的坐标，所以它们应该被保留，但仅限这类家族或局部化情形。

### 2. `clmm`：集中流动性家族
这一类由 `Uniswap v3 / Capricorn` 风格池代表。  
当前本地锚点包括：

- `external/amm-official/uniswap-v3-core/contracts/UniswapV3Pool.sol`
- `external/amm-official/uniswap-v3-core/contracts/libraries/TickMath.sol`
- `external/amm-official/uniswap-v3-core/contracts/libraries/Oracle.sol`
- `external/monad-official/protocols/mainnet/capricorn.jsonc`

这类池的几何核心不再是单一 reserve pair，而是：

- `sqrtPriceX96`
- current tick
- active liquidity
- liquidity by tick
- fee tier
- oracle state

因此，`clmm` 不能再被默认压成统一的 `A_t/B_t`。  
更自然的做法是把这些量装入

$$
\theta_t^{\mathrm{pool}}
$$

并允许只在某个局部价格段内再做二次近似。

### 3. `stable`：近锚定曲线家族
这一类由 `Curve` 与 `Balancer StablePool` 共同代表。  
当前本地锚点包括：

- `external/amm-official/curve-core/contracts/amm/stableswap`
- `external/amm-official/curve-core/contracts/amm/twocryptoswap`
- `external/amm-official/curve-core/contracts/amm/tricryptoswap`
- `external/amm-official/balancer-v3-monorepo/pkg/pool-stable/contracts/StablePool.sol`
- `external/monad-official/protocols/mainnet/curve.jsonc`
- `external/monad-official/protocols/mainnet/balancer.jsonc`

这类家族的关键不是二元常数乘积，而是：

- balances
- amplification
- peg / rate state
- pool subtype

其中 `Curve` 至少还应区分：

- `stableswap`
- `twocrypto`
- `tricrypto`

因此，`stable` 更适合写成“平坦段 + 远端弯曲段”的家族化 geometry，而不是预设单一二次式。

### 4. `weighted`：多资产加权家族
这一类由 `Balancer WeightedPool` 代表。  
当前本地锚点包括：

- `external/amm-official/balancer-v3-monorepo/pkg/pool-weighted/contracts/WeightedPool.sol`
- `external/monad-official/protocols/mainnet/balancer.jsonc`

这类池的核心状态是：

- balance vector
- normalized weights
- swap fee
- vault scaling

由于价格曲线由多资产权重共同决定，`weighted` 不能被当作二元常数乘积的简单变体。  
更合理的方式是把权重与 vault-level 处理装入

$$
\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}
$$

再由统一的 $\Gamma_t$ 黑箱化进入控制问题。

### 5. `hooked-clmm`：带 hooks / dynamic fee 的 CLMM
这一类由 `Uniswap v4` 核心设计代表。  
当前本地锚点包括：

- `external/amm-official/uniswap-v4-core/src/PoolManager.sol`
- `external/amm-official/uniswap-v4-core/src/interfaces/IHooks.sol`
- `external/amm-official/uniswap-v4-core/src/libraries/LPFeeLibrary.sol`
- `external/monad-official/protocols/testnet/Uniswap.json`

这类家族在 `clmm` 基础上额外引入：

- hook callbacks
- dynamic fee
- callback-induced state
- manager / unlock style route context

因此，它不仅会改写 $\Gamma_t$，还会外溢到：

- $c_t(a)$：fee 与 gas 路径
- $\kappa_t(a)$：hook / callback 引发的状态访问与冲突结构
- 某些失败语义与 route-level constraint

所以 `hooked-clmm` 更不应被强行压成统一 `A_t/B_t`。

### 6. 非 AMM 排除项
本地协议清单中的 `Clober` 是 fully on-chain CLOB。  
它不是 AMM 机会几何的一部分，因此：

- 若研究范围只限 AMM，应当显式排除
- 若研究所有 venue，则应在 $G_t$ 中单列非 AMM 分支，而不是把它塞回 $\Gamma_t^{\mathrm{amm}}$

## 直觉解释
第一性原理的价值，不在于把所有量都升成主状态，而在于先把它们从“自由参数”改写成：

$$
\text{由当前仓库事实、外部机制说明、环境过程和统一核共同诱导出来的对象}.
$$

这正是统一主线之后，第一性原理推导应该被保留的方式。

## 下一步
在阅读顺序上，这一页应放在：

- [参数建模总页](./30-parameter-map.md)

之后、

- [数据来源与校准边界](./31-data-sources-and-availability.md)

之前。这样先看清结构，再讨论观测与校准。

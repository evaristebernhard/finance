# 参数建模总页

## 目的
这一页恢复整套研究里原本连续的参数建模主链。  
它回答的不是“对象分几层”，而是下面这条完整链条：

$$
\text{参数是什么}
\to
\text{当前仓库已验证 / 依赖外部机制说明}
\to
\text{哪些由第一性结构推出}
\to
\text{哪些需要环境输入}
\to
\text{哪些最后再校准}
$$

在这一版中：

- [统一核主模型](../20-core-model/20-monad-mev-main-model.md) 仍然是唯一主模型
- 本页是 unified kernel 下的**参数建模总页**
- [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md) 是这些参数进入控制问题后的压缩落点
- [第一性原理下的投影结构建模](./36-first-principles-projection-derivations.md) 是公式更密的推导附页

## 参数建模总原则
统一采用三层分解：

$$
\theta=(\theta_{\mathrm{proto}},\theta_{\mathrm{env}},\theta_{\mathrm{cal}})
$$

其中：

- $\theta_{\mathrm{proto}}$：由当前仓库代码或外部机制资料支撑的结构
- $\theta_{\mathrm{env}}$：环境过程，需要作为随机过程、情景轴或对手环境进入
- $\theta_{\mathrm{cal}}$：最终需要由观测或实验校准的对象

同时，每个参数组都按下面的固定模板处理：

1. 在 unified kernel 中的角色：primitive / projection / reduced-form / calibration target
2. 主要回指到哪个 kernel 状态分量
3. 当前仓库已验证什么
4. 依赖外部机制说明什么
5. 哪部分由第一性结构推出
6. 哪部分需要环境输入
7. 哪部分以后才校准
8. 在 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中如何进入压缩状态或 Bellman

## 一、机会几何参数组
### 对象
$$
f_t,\quad \theta_t^{\mathrm{pool}},\quad \theta_t^{\mathrm{route}},\quad \Gamma_t(P,x),\quad M_{\max,t},\quad E_{\mathrm{cycle},t}
$$

### 角色
- $\Gamma_t(P,x)$：projection
- $f_t$：协议家族标签
- $\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}$：$\Gamma_t$ 的家族化 reduced-form 坐标
- $M_{\max,t},E_{\mathrm{cycle},t}$：$G_t$ 的 reduced-form summary

### 回指
这一组主要回指到 unified kernel 中的

$$
G_t
$$

### 当前仓库已验证
当前仓库没有直接给出跨协议 AMM 几何参数。  
它能支撑的是：后续若把池状态、路径和交易结果映射进研究模型，这些量应被视为 $G_t$ 的 projection 或 summary，而不是新的 primitive。

但当前工作区已经提供了足够强的协议家族锚点：

- `Uniswap v2`：常数乘积双资产池
- `Uniswap v3`：集中流动性池
- `Uniswap v4`：带 hooks / dynamic fee 的 CLMM
- `Balancer`：至少分 `WeightedPool / StablePool / Vault`
- `Curve`：至少分 `Stableswap / Twocrypto / Tricrypto`
- Monad 协议清单里还出现了 `Capricorn` 与 `Clober`

因此，下一层建模不应再把全部 AMM 压成单一 `A_t,B_t`。

### 依赖外部机制说明
不同 AMM 协议的定价规则、手续费规则、路径组合约束与外部价格锚，大多来自链上协议本身及外部市场数据，而不是当前 execution 仓库。

### 协议家族映射表
| 家族 | 本地锚点 | Monad 协议清单锚点 | 核心状态 | 核心结构参数 | 是否允许 `A/B` 局部化 |
| --- | --- | --- | --- | --- | --- |
| `cpmm` | `external/amm-official/uniswap-v2-core/contracts/UniswapV2Pair.sol` | `external/monad-official/protocols/testnet/Uniswap.json` | reserves、累计价格 | reserve vector、swap fee、price cumulative | 是，天然基线 |
| `clmm` | `external/amm-official/uniswap-v3-core/contracts/UniswapV3Pool.sol`、`.../TickMath.sol`、`.../Oracle.sol` | `external/monad-official/protocols/mainnet/capricorn.jsonc` 与 `.../testnet/Uniswap.json` | `sqrtPriceX96`、tick、active liquidity、position、oracle | fee tier、liquidity by tick、oracle state | 仅局部允许 |
| `stable` | `external/amm-official/curve-core/contracts/amm/stableswap`、`.../twocryptoswap`、`.../tricryptoswap`、`external/amm-official/balancer-v3-monorepo/pkg/pool-stable/contracts/StablePool.sol` | `external/monad-official/protocols/mainnet/curve.jsonc` 与 `.../balancer.jsonc` | balances、peg/rate state、subtype | amplification、pool subtype、swap fee | 仅局部允许 |
| `weighted` | `external/amm-official/balancer-v3-monorepo/pkg/pool-weighted/contracts/WeightedPool.sol` | `external/monad-official/protocols/mainnet/balancer.jsonc` | balance vector、weights | normalized weights、swap fee、vault scaling | 一般不建议 |
| `hooked-clmm` | `external/amm-official/uniswap-v4-core/src/PoolManager.sol`、`.../interfaces/IHooks.sol`、`.../libraries/LPFeeLibrary.sol` | `external/monad-official/protocols/testnet/Uniswap.json` | clmm 核心状态 + hook context | hooks、dynamic fee、callback-induced state | 仅极局部允许 |

这里额外明确两点：

- `Capricorn` 按 `Uniswap-v3 风格 CLMM` 处理
- `Clober` 是 fully on-chain CLOB，不进入 AMM 机会几何家族

### 第一性结构推出
第一性层面，路径机会函数写成：

$$
\Gamma_t(P,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})=g_\Gamma(s_t;P,x)
$$

其中：

$$
f_t\in\{\text{cpmm},\text{clmm},\text{stable},\text{weighted},\text{hooked-clmm}\}
$$

这表示：

- 机会几何首先按协议家族分层
- 再由 pool-level 与 route-level 状态进入统一投影
- `A_t,B_t` 只在 `cpmm` 或某个具体家族的局部近似里出现

若只看 `cpmm` 基线或局部二次化情形，才可以进一步写成

$$
\Gamma_t(P,x)\approx A_t x-B_t x^2.
$$

### 环境输入
主要来自：

- 外部价格锚
- 外生订单流
- 流动性迁移
- 路径上的真实协议组成
- router / vault / hook 选择
- 协议家族内部的费率与状态配置

### 校准对象
最终要校准的是：

- 协议家族标签 $f_t$ 的经验占比与机会分布
- $\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}$ 的时间序列特征
- 若局部化到 `cpmm` 或近似二次段，再校准 $A_t,B_t$
- 路径级 gross opportunity 的经验分布
- $M_{\max,t},E_{\mathrm{cycle},t}$ 的时间序列特征

### 在压缩 Bellman 中的落点
在 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中，这一组进入：

$$
(f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})
$$

并定义

$$
\Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}).
$$

若研究只临时退回到 `cpmm` 或局部近似，也可再额外写成：

$$
\Gamma_t(x)=A_t x-B_t x^2,
$$

但这不再是全体 AMM 的统一压缩写法。

## 二、block / verification 参数组
### 对象
$$
p_t,\quad u_t
$$

### 角色
- $p_t$：projection
- $u_t$：projection

### 回指
主要回指到

$$
M_t
$$

### 当前仓库已验证
当前仓库可直接核对：

- `BlockStart / BlockReject / BlockQC / BlockFinalized / BlockVerified` 事件类型
- 由 `CommitStateBlockBuilder` 重建的 `Proposed / Voted / Finalized / Verified`
- finalized 时未被保留 proposal 的 `abandoned` 结果

### 依赖外部机制说明
更完整的共识推进逻辑、canonical 形成细节、message arrival 与 fault 风险仍依赖外部共识仓库或官方资料。  
因此，`p_t` 和 `u_t` 不能被写成 execution 仓库直接暴露的真值字段。

### 第一性结构推出
它们不是自由参数，而是机制投影：

$$
p_t=g_p(s_t),
\qquad
u_t=g_u(s_t).
$$

在局部分解里，

$$
u_t=p_t d_t
$$

其中 $d_t$ 表示条件验证一致性。

### 环境输入
主要是：

- message arrival / fault 风险
- 局部可见 block / output 信息质量

### 校准对象
最终要校准的是：

- state 升级时的经验保留率
- output 可见性与最终验证的一致性

### 在压缩 Bellman 中的落点
在 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中，这一组压缩进入：

$$
u_t
$$

其中 $p_t$ 若需要可继续展开，否则被吸收到 $u_t$ 中。

## 三、propagation / inclusion 参数组
### 对象
$$
\nu_t,\quad q_t(a)
$$

### 角色
- $q_t(a)$：projection
- $\nu_t$：对 $M_t,C_t$ 的 reduced-form 压缩状态

### 回指
主要回指到

$$
M_t,\qquad C_t
$$

### 当前仓库已验证
当前 execution 仓库能明确给出的，是传播机制的**边界条件**：

- execution daemon 是本地执行服务
- execution daemon 不承担网络身份
- 当前仓库没有直接实现 `leader path`、`future leaders`、`forwarding / retry` 的完整机制说明

### 依赖外部机制说明
`local mempool / future leaders / forwarding / retry / inclusion race` 的具体制度结构，不能再写成当前 execution 仓库已直接给出。  
这部分应明确降级为外部共识资料或外部官方说明。

### 第一性结构推出
入链投影写成：

$$
q_t(a)=\Pr(\mathrm{included}\mid s_t,a)=g_q(a;\nu_t).
$$

### 环境输入
主要来自：

- 网络时延与链路质量
- 对手 bid 分布
- local visibility
- leader 可达性

### 校准对象
最终要校准的是：

- $\nu_t$ 的经验分布
- 入链延迟
- 在给定 bid / gas limit 下的 inclusion behavior

### 在压缩 Bellman 中的落点
在 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中，这一组进入：

$$
\nu_t,
\qquad
q_t(a)=g_q(a;\nu_t).
$$

## 四、reserve / survival 参数组
### 对象
$$
b_t,\quad e_t,\quad r_t(a)
$$

### 角色
- $r_t(a)$：projection
- $b_t,e_t$：对 $R_t$ 的 reduced-form 压缩状态

### 回指
主要回指到

$$
R_t
$$

### 当前仓库已验证
当前代码与文档锚点可以直接支撑：

- reserve tracking 的 revision gating
- delegated account 限制
- parent / grandparent / current block 环境检查
- init selfdestruct exemption
- `get_max_reserve` 当前的默认 `10 MON` 占位逻辑

这些都来自 `external/monad-official/monad/category/execution/monad/reserve_balance.cpp`。

### 依赖外部机制说明
若要把更完整的 reserve economics、账户语义和系统级制度写全，仍需要外部协议上下文。  
但这不影响当前仓库已经给出一批足够强的 reserve 规则事实。

### 第一性结构推出
更自然的结构分解是：

$$
r_t(a)=\chi_t(a)\rho_t(a),
$$

其中：

- $\chi_t(a)$：admissibility
- $\rho_t(a)$：execution survival

### 环境输入
主要来自：

- 当前 inflight obligations 的实现环境
- 账户活动模式
- 交易簇的时序与叠加

### 校准对象
最终要校准的是：

- reserve slack 的经验分布
- exception 实际可用性
- survival 相关经验频率

### 在压缩 Bellman 中的落点
在 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中，这一组进入：

$$
b_t,\qquad e_t,\qquad r_t(a)=g_r(a;b_t,e_t).
$$

## 五、conflict / friction 参数组
### 对象
$$
h_t,\quad \zeta_t,\quad \kappa_t(a)
$$

### 角色
- $\kappa_t(a)$：projection
- $h_t,\zeta_t$：对 $E_t,C_t$ 的 reduced-form 压缩状态

### 回指
主要回指到

$$
E_t,\qquad C_t
$$

### 当前仓库已验证
当前 execution event schema 已经给出：

- `AccountAccess`
- `StorageAccess`
- `TxnReject`
- `TxnEvmOutput`
- `TxnCallFrame`

因此，访问结构、冲突相关事件和执行过程轨迹在当前仓库中已经存在较强锚点。

### 依赖外部机制说明
完整的竞争环境、热点分布形成机制和最终损失函数仍依赖外部市场环境与建模假设。  
所以 `\kappa_t(a)` 仍是 projection，不是代码里可直接读取的标量。

### 第一性结构推出
更自然的写法是：

$$
\kappa_t(a)=\mathbb E[\mathrm{friction\ loss}\mid s_t,a].
$$

### 环境输入
主要来自：

- 热点账户 / slot 分布
- 交易类型混合
- 对手与用户流量在热点上的叠加

### 校准对象
最终要校准的是：

- 热点 measure
- overlap 频率
- re-execution 成本与损失弹性

### 在压缩 Bellman 中的落点
在 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中，这一组进入：

$$
h_t,\qquad \zeta_t,\qquad \kappa_t(a)=g_\kappa(a;h_t,\zeta_t).
$$

## 六、fee 参数组
### 对象
$$
F_t
$$

### 角色
- $F_t$：primitive

### 回指
直接属于 unified kernel 状态：

$$
F_t \subset s_t
$$

### 当前仓库已验证
block header、transaction header 与 reconstructed block 可以给出 base fee 相关字段；因此 `F_t` 是当前工作区里较稳的直接观测对象。

### 依赖外部机制说明
如果要完整写出 fee dynamics 的制度背景，仍需要外部协议上下文；但这不影响 `F_t` 在研究里作为 primitive 被保留。

### 第一性结构推出
这里的结构性重点不是再把它投影化，而是说明：

$$
F_t
$$

不是背景常数，而是 kernel 内生状态。

### 环境输入
主要来自：

- aggregate demand
- block-level gas pressure

### 校准对象
最终要校准的是：

- fee 状态过程
- 它与机会排序、act / wait / abort 边界的联动

### 在压缩 Bellman 中的落点
在 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中，$F_t$ 直接保留在压缩状态中，并进入：

$$
c_t(a)=\ell_t\cdot \min(F_t+\pi_t,\overline F_t).
$$

## 七、从统一核到压缩 Bellman
整条参数建模链最终汇总为：

$$
(G_t,M_t,C_t,R_t,E_t,F_t)
\to
(f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}},u_t,\nu_t,b_t,e_t,h_t,\zeta_t,F_t)
$$

其中：

- $G_t \to (f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})$
- $M_t \to u_t$
- $(M_t,C_t)\to \nu_t$
- $R_t \to (b_t,e_t)$
- $(E_t,C_t)\to (h_t,\zeta_t)$
- $F_t \to F_t$

而对应的投影函数写成：

$$
q_t(a)=g_q(a;\nu_t),
\qquad
r_t(a)=g_r(a;b_t,e_t),
\qquad
\kappa_t(a)=g_\kappa(a;h_t,\zeta_t).
$$

于是 [25-minimal-bellman-system.md](../20-core-model/25-minimal-bellman-system.md) 中的压缩状态

$$
\bigl(f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}},u_t,\nu_t,b_t,e_t,h_t,\zeta_t,F_t\bigr)
$$

就不再是“凭空给定的低维向量”，而是这条参数建模链的落点。

## 直觉解释
这一页真正要恢复的是：

$$
\text{参数建模不是列参数，}
\quad
\text{而是把每个量都放回“当前仓库已验证 / 外部机制说明 / 环境输入 / 最终校准”的链条里。}
$$

## 与主线的关系
本页是 unified kernel 之下的参数建模总页。  
它不替代主模型，但应当成为后续 Bellman 压缩、第一性推导、proxy 构造和校准程序的共同入口。

## 下一步
按建议顺序继续读：

1. [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md)
2. [第一性原理下的投影结构建模](./36-first-principles-projection-derivations.md)
3. [数据来源与校准边界](./31-data-sources-and-availability.md)

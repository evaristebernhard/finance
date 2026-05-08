# 符号与术语表

## 目的
统一全套文档中的符号角色，并明确：

1. 哪些量是 unified kernel 的 primitive
2. 哪些量只是 kernel 的投影
3. 哪些量只是 reduced-form summary 或校准目标
4. 哪些量当前仓库可以直接核对，哪些只能依赖外部资料或建模抽象

## 一、主线 primitive
统一核模型中，只有下面这些对象属于 primitive。

### 1. 状态
$$
s_t=(G_t,M_t,C_t,R_t,E_t,F_t)
$$

其中：

- $G_t$：AMM 图、池状态、外部价格锚与机会几何来源
- $M_t$：Monad 提交态、leader window、execution-stage 相关状态
- $C_t$：竞争流、局部可见订单与传播环境
- $R_t$：reserve / delegation / authority / emptying-exception 相关状态
- $E_t$：访问结构、热点、冲突与重执行环境
- $F_t$：base fee 状态

### 2. 动作
$$
a_t=(P_t,x_t,\ell_t,\pi_t,\overline F_t,d_t)
$$

其中：

- $P_t$：路径或机会选择
- $x_t$：规模
- $\ell_t$：gas limit
- $\pi_t$：priority 竞价
- $\overline F_t$：max fee cap
- $d_t\in\{\text{act},\text{wait},\text{abort}\}$：离散决策

### 3. 转移核与收益
$$
\mathcal K_t(ds',dy\mid s_t,a_t)
$$

这里：

- $s'$：下一期状态
- $y$：当期 realized payoff

### 4. belief
$$
b_t=\Pr(s_t\mid \mathcal F_t^{\mathrm{obs}})
$$

### 5. 价值函数
$$
V_t(b_t)=\sup_{a_t}\left\{\mathbb E[y_t\mid b_t,a_t]+\beta\,\mathbb E[V_{t+1}(b_{t+1})\mid b_t,a_t]\right\}
$$

## 二、核心符号标签表
全项目默认使用下表来标注核心状态分量和常见投影：

| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| `M_t` | 事件重建 + 研究latent | 当前仓库代码 + 外部官方资料 | `external/monad-official/monad/rust/crates/monad-exec-events/src/events/mod.rs`；`monad-bft` / 外部共识资料 | primitive |
| `C_t` | 研究latent | 外部官方资料 + 建模假设 | 外部共识资料、市场结构假设 | primitive |
| `R_t` | 可直接观测 + 事件重建 + 研究latent | 当前仓库代码 + 建模假设 | `external/monad-official/monad/category/execution/monad/reserve_balance.cpp` | primitive |
| `E_t` | 事件重建 + 研究latent | 当前仓库代码 + 建模假设 | `external/monad-official/monad/rust/crates/monad-exec-events/src/events/mod.rs` | primitive |
| `F_t` | 可直接观测 | 当前仓库代码 | `external/monad-official/monad/rust/crates/monad-exec-events/src/block.rs` | primitive |
| `p_t` | 研究latent | 建模假设 | 主模型页、block-state 页 | projection |
| `u_t` | 研究latent | 建模假设 | 主模型页、block-state 页 | projection |
| `q_t(a)` | 研究latent | 外部官方资料 + 建模假设 | propagation 页、参数页、推导页 | projection |
| `r_t(a)` | 研究latent | 当前仓库代码 + 建模假设 | reserve 页、参数页、推导页 | projection |
| `\kappa_t(a)` | 研究latent | 当前仓库代码 + 建模假设 | Execution Events 页、参数页、推导页 | projection |
| `\Gamma_t(P,x)` | 研究latent | 建模假设 | 主模型页、参数页、推导页 | projection |
| `f_t` | 研究latent | 当前代码锚点 + 建模假设 | 参数页、Bellman 页、推导页 | 协议家族标签 |
| `\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}` | 研究latent | 当前代码锚点 + 建模假设 | 参数页、Bellman 页、推导页 | 几何压缩坐标 |

## 三、kernel 的常见投影
下面这些量经常出现，但从这一版开始都不再属于 primitive。

### 1. AMM 与机会投影
$$
\Gamma_t(P,x)=g_\Gamma(s_t;P,x)
$$

它表示在给定路径与规模下，由 $G_t$ 诱导出来的机会几何或 gross opportunity。  
它不是链上直接观测值，而是由池状态、价格锚和路径选择组合出来的 projection。

从这一版开始，$\Gamma_t$ 默认按协议家族理解为：

$$
\Gamma_t(P,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})
$$

其中：

- $f_t\in\{\text{cpmm},\text{clmm},\text{stable},\text{weighted},\text{hooked-clmm}\}$
- $\theta_t^{\mathrm{pool}}$：pool 家族内部的几何状态
- $\theta_t^{\mathrm{route}}$：路径、router、vault、hook 等 route-level 上下文

`A_t,B_t` 不再代表全部 AMM，只保留为 `cpmm` 或局部化近似时的辅助坐标。

### 2. 入链投影
$$
q_t(a)=\Pr(\mathrm{included}\mid s_t,a)
$$

它是 $M_t,C_t$ 与动作 $a$ 的联合投影。  
当前仓库没有一个可以直接读取的 `q_t` 结构体；它需要外部机制说明和经验校准。

### 3. 生存投影
$$
r_t(a)=\Pr(\mathrm{survive}\mid s_t,a,\mathrm{included})
$$

它主要由 $R_t$ 与动作 $a$ 诱导。  
当前仓库可以提供 reserve-balance 规则事实，但 `r_t(a)` 本身仍是 projection。

### 4. 冲突摩擦投影
$$
\kappa_t(a)=\mathbb E[\mathrm{friction\ loss}\mid s_t,a]
$$

它主要由 $E_t,C_t$ 与动作 $a$ 诱导。  
Execution Events 可以给访问轨迹和冲突相关事件，但不能直接给出完整损失函数。

### 5. block / verification 投影
$$
u_t=g_u(s_t),
\qquad
p_t=g_p(s_t)
$$

其中：

- $p_t$：branch / canonical 相关 projection
- $u_t$：execution output / verification 相关 projection

事件流可以帮助重建 block commit state，但 `p_t` 和 `u_t` 仍属于 belief / projection 层。

## 四、reduced-form summary
下面这些对象允许出现，但只能出现在观测压缩、代理估计或经验层中：

- $M_{\max,t}$
- $E_{\mathrm{cycle},t}$
- 压缩 belief 向量
- 各类 proxy、feature、factor、estimand

例如：

$$
\tilde b_t=\psi(b_t)
$$

可以把完整 belief 压缩成低维 summary，但这类压缩量不再反过来定义主模型。

### 压缩 Bellman 状态
在 [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md) 中，常用压缩状态写成：

$$
(f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}},u_t,\nu_t,b_t,e_t,h_t,\zeta_t,F_t).
$$

这组量是 reduced-form 压缩状态，不是 unified kernel primitive。  
它们的来源与角色由 [参数建模总页](../30-identification-and-data/30-parameter-map.md) 统一说明。

若只讨论 `cpmm` 或某个单一 pool 的局部二次近似，也可以进一步写成：

$$
(A_t,B_t,u_t,\nu_t,b_t,e_t,h_t,\zeta_t,F_t),
$$

但这只是更窄情形下的局部化坐标。

## 五、常见对象与来源的对应关系
为避免不同页面改义，统一采用下面的回指规则：

- $\Gamma_t(P,x)$：回指到 $G_t$
- $q_t(a)$：回指到 $M_t,C_t$
- $r_t(a)$：回指到 $R_t$
- $\kappa_t(a)$：回指到 $E_t,C_t$
- $u_t,p_t$：回指到 $M_t$
- $M_{\max,t},E_{\mathrm{cycle},t}$：回指到 $G_t$ 的 reduced-form summary
- $f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}$：回指到 $G_t$ 的协议家族几何状态

## 六、AMM 家族标签
为避免把所有 DEX/AMM 机会压成同一条曲线，统一采用下面的协议家族标签：

- `cpmm`：常数乘积双资产池，例如 `Uniswap v2` 风格
- `clmm`：集中流动性池，例如 `Uniswap v3 / Capricorn`
- `stable`：稳定币或近锚定曲线家族，内部可再细分 `stableswap / twocrypto / tricrypto`
- `weighted`：多资产加权池，例如 `Balancer Weighted`
- `hooked-clmm`：带 hooks 或动态 fee 的 CLMM，例如 `Uniswap v4`

同时明确：

- `Clober` 这类 fully on-chain CLOB 不属于 AMM 几何家族
- 如果研究对象扩大到所有可套利 venue，应在 $G_t$ 中单列非 AMM 分支

## 七、符号使用规则
- 只有 `s_t / a_t / \mathcal K_t / y_t / b_t / V_t` 属于主线 primitive
- `p/u/r/q/\kappa/\Gamma/M_{\max}/E_{\mathrm{cycle}}` 全部视为派生量
- 任何页面若使用派生量，必须说明其来自哪个状态分量或哪个投影
- 任何页面若使用压缩态，必须说明它属于 reduced-form 层，而非 canonical state
- 任何页面若写“协议给定”，必须进一步说明是“当前仓库已验证”还是“依赖外部官方资料”
- 任何页面若写 `A_t,B_t`，必须明确它们只代表 `cpmm` 或局部近似坐标，而不是全部 AMM 的统一参数

## 与主线的关系
后续所有页面都应遵守这里的角色分层，不应再把派生量写回主线 primitive。

## 下一步
继续读 [统一核主模型](../20-core-model/20-monad-mev-main-model.md)。

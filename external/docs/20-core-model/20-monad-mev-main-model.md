# 统一核主模型

## 目的
这一章是整套研究的唯一理论中心。  
它只做一件事：定义 Monad-native AMM 控制问题的 canonical primitive，并把其他常见量全部降级为该模型的投影、压缩或校准对象。

## canonical primitive
### 一、状态
统一状态写成

$$
s_t=(G_t,M_t,C_t,R_t,E_t,F_t).
$$

这里：

- $G_t$：AMM 图、池状态、外部价格锚与机会几何来源
- $M_t$：Monad 提交态、leader window、execution-stage 相关状态
- $C_t$：竞争流、局部可见订单与传播环境
- $R_t$：reserve / delegation / authority / emptying-exception 相关状态
- $E_t$：访问结构、热点、冲突与重执行环境
- $F_t$：base fee 状态

需要特别强调的是：  
这里的 `s_t` **不是代码中的现成结构体**，而是研究层状态组织。  
它把当前仓库已经能验证的执行事实、依赖外部共识资料的机制说明、以及仍需校准的 latent 对象放进同一个控制问题里。

### 二、状态分量的当前证据基础
| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| `G_t` | 可直接观测 + 研究latent | 当前链上事实 + 建模假设 | 池状态、价格锚、路径构造 | primitive |
| `M_t` 的 block-state 部分 | 事件重建 | 当前仓库代码 | `external/monad-official/monad/rust/crates/monad-exec-events/src/events/mod.rs` 与 `.../block_builder/commit_state/mod.rs` | primitive |
| `M_t` 的 leader-window 部分 | 研究latent | 外部官方资料 | `monad-bft` / 外部共识资料 | primitive |
| `C_t` | 研究latent | 外部官方资料 + 建模假设 | 外部传播机制说明、市场竞争假设 | primitive |
| `R_t` | 可直接观测 + 研究latent | 当前仓库代码 + 建模假设 | `external/monad-official/monad/category/execution/monad/reserve_balance.cpp` | primitive |
| `E_t` | 事件重建 + 研究latent | 当前仓库代码 + 建模假设 | `external/monad-official/monad/rust/crates/monad-exec-events/src/events/mod.rs` | primitive |
| `F_t` | 可直接观测 | 当前仓库代码 | `external/monad-official/monad/rust/crates/monad-exec-events/src/block.rs` | primitive |

### 三、动作
动作写成

$$
a_t=(P_t,x_t,\ell_t,\pi_t,\overline F_t,d_t),
$$

其中：

- $P_t$：路径或机会选择
- $x_t$：规模
- $\ell_t$：gas limit
- $\pi_t$：priority 竞价
- $\overline F_t$：max fee cap
- $d_t\in\{\text{act},\text{wait},\text{abort}\}$：离散决策

### 四、转移核
统一转移核写成

$$
\mathcal K_t(ds',dy\mid s_t,a_t),
$$

它一次性生成：

- 下一期状态 $s'$
- 当期 realized payoff $y$

因此，主模型不再把“是否入链、是否 survive、是否发生冲突重执行”分别写成平行 primitive，而把它们都交给同一个 kernel 生成。

### 五、belief
交易者面对的是部分观测，因此 canonical belief 为

$$
b_t=\Pr(s_t\mid \mathcal F_t^{\mathrm{obs}}).
$$

完整 belief 是主线对象；任何压缩态都属于 reduced-form 层。

## kernel 诱导的常见投影
下面这些量允许继续使用，但从这一版开始都不是 primitive，而是 kernel 投影。

### 1. AMM 几何投影
$$
\Gamma_t(P,x)=g_\Gamma(s_t;P,x)
$$

它表示在路径 $P$ 和规模 $x$ 下，由 $G_t$ 诱导出的 gross opportunity。

### 2. 入链投影
$$
q_t(a)=\Pr(\mathrm{included}\mid s_t,a)
$$

它主要由 $M_t,C_t$ 与动作 $a$ 诱导。  
当前仓库没有可以直接读取的 `q_t` 真值；它属于外部机制说明与经验校准共同支撑的 projection。

### 3. 生存投影
$$
r_t(a)=\Pr(\mathrm{survive}\mid s_t,a,\mathrm{included})
$$

它主要由 $R_t$ 与动作 $a$ 诱导。  
当前仓库可以直接给出 reserve-balance 规则事实，但 `r_t(a)` 本身仍是 projection。

### 4. 冲突摩擦投影
$$
\kappa_t(a)=\mathbb E[\mathrm{friction\ loss}\mid s_t,a]
$$

它主要由 $E_t,C_t$ 与动作 $a$ 诱导。  
Execution Events 可以增强访问与冲突结构可见性，但不会直接给出完整损失函数。

### 5. block / verification 投影
$$
u_t=g_u(s_t),
\qquad
p_t=g_p(s_t)
$$

它们刻画提交态与 output verification 相关的 kernel 投影。  
当前仓库可以事件重建 block commit state，但 `p_t` 和 `u_t` 仍属于 belief / projection 层。

## 目标函数
对任意 belief $b_t$ 和动作 $a_t$，主模型的目标是最大化：

$$
\mathbb E[y_t\mid b_t,a_t].
$$

因此价值函数定义为

$$
V_t(b_t)=
\sup_{a_t\in\mathcal A(b_t)}
\left\{
\mathbb E[y_t\mid b_t,a_t]
\;+\;
\beta\,\mathbb E[V_{t+1}(b_{t+1})\mid b_t,a_t]
\right\}.
$$

其中 $\mathcal A(b_t)$ 是 belief 下可行动作集合。  
该集合的 Monad 特化，例如 reserve 与 gas 约束，会在 [Reserve 子结构与可行动作集](./23-reserve-constrained-control-k3.md) 中展开。

## 投影分解的常用写法
虽然 kernel 是唯一 primitive，但在分析时，常常把一步期望收益分解为：

$$
J_t(b_t,a_t)=\mathbb E[y_t\mid b_t,a_t].
$$

在局部展开里，可写成

$$
J_t(b_t,a_t)
=
q_t(a_t)\Big[u_t\,r_t(a_t)\,\Gamma_t(P_t,x_t)-(1-u_t\,r_t(a_t))L_t(a_t)-c_t(a_t)\Big]
-\kappa_t(a_t),
$$

其中：

- $\Gamma_t$ 是 AMM 机会投影
- $q_t,r_t,\kappa_t,u_t$ 都是 kernel 投影
- $L_t(a_t)$ 是失败或误判带来的损失函数
- $c_t(a_t)$ 是费用与 upfront budget 占用

这条式子只是投影分解，不是对主线 primitive 的替代定义。

## 基本假设
### 1. 主线先于 reduced-form
完整 kernel、状态与 belief 先定义，压缩态后定义。

### 2. 主线先于数据
RPC-only、Execution Events、结构仿真只负责看见、压缩或校准主线中的对象，不能反向定义主线。

### 3. 局部展开必须可回指
任何常见量，例如 `q/r/\kappa/u/p/\Gamma`，若被单独分析，都必须能回指到

$$
(s_t,a_t,\mathcal K_t)
$$

中的某个状态分量或投影。

### 4. 证据等级必须显式声明
任何页面若说“协议给定”或“代码给定”，都必须进一步说明：

- 是当前仓库代码直接可验证
- 还是依赖外部共识资料
- 或者只是研究层近似与校准对象

## 与主线的关系
本页是全套文档中唯一的主模型页。  
后续页面只能：

- 解释这套模型的观测结构
- 解释这套模型的控制结构
- 展开这套模型中的特定子结构
- 为这套模型提供识别与校准方案

## 数据前提 / 识别边界
主模型本身不依赖某一特定数据面。  
区别只在于：

- 你能否直接观测到某些状态分量
- 你是否只能构造 projection proxy
- 你是否可以把某些 proxy 升级为事件重建或更强识别对象

## 下一步
先读 [观测、belief 与 reduced-form 压缩](./21-state-space-and-observation.md)，再看控制和 reserve 子结构。

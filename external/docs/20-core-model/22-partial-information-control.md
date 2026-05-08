# 控制分解：路径、规模与出价

## 目的
说明在统一核主模型下，控制问题应如何分解为路径、规模与出价三层，而不是把 “act / wait / abort” 与各种派生量混写成新的主模型。

## 核心对象
统一动作为

$$
a_t=(P_t,x_t,\ell_t,\pi_t,\overline F_t,d_t),
$$

其中：

- $d_t\in\{\text{act},\text{wait},\text{abort}\}$
- $P_t$：路径、venue 选择与协议家族上下文
- $x_t$：规模
- $(\ell_t,\pi_t,\overline F_t)$：gas / fee 相关决策

从这一版开始，`P_t` 不再只表示“几跳路径”，而是默认包含：

- 路由本身
- 该路由所处的协议家族
- router / vault / hook 等会改写机会几何的上下文

## 控制问题
在 unified kernel 下，控制问题始终写成

$$
V_t(b_t)=
\sup_{a_t\in\mathcal A(b_t)}
\left\{
\mathbb E[y_t\mid b_t,a_t]
\;+\;
\beta\,\mathbb E[V_{t+1}(b_{t+1})\mid b_t,a_t]
\right\}.
$$

真正被优化的是 kernel 生成的 realized payoff，而不是某个单独的平行模块。

## 常用分解
为便于分析，动作可拆成三层：

### 1. 离散层
是否：

- `act`
- `wait`
- `abort`

### 2. 机会层
若 `act`，选择：

$$
P_t,\qquad x_t
$$

### 3. 出价层
若 `act`，再选择：

$$
\ell_t,\qquad \pi_t,\qquad \overline F_t
$$

这种分解是对 unified action 的局部展开，不是新的主模型。

## 投影视角下的一步收益
在局部展开里，常把

$$
\mathbb E[y_t\mid b_t,a_t]
$$

写成更直观的形式：

$$
J_t(b_t,a_t)
=
q_t(a_t)\Big[u_t\,r_t(a_t)\,\Gamma_t(P_t,x_t;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})-(1-u_t\,r_t(a_t))L_t(a_t)-c_t(a_t)\Big]
-\kappa_t(a_t).
$$

这条式子把主线里的 kernel 拆成了：

- 机会投影 $\Gamma_t$
- 入链投影 $q_t$
- 生存投影 $r_t$
- block / verification 投影 $u_t$
- 冲突摩擦投影 $\kappa_t$

这里的 $\Gamma_t$ 默认已经是协议家族特定几何，而不是单一 AMM 曲线。  
也就是说，控制问题里真正被比较的是：

$$
\text{给定协议家族、路径与 route-level 上下文之后的机会几何。}
$$

它的意义在于帮助理解，而不是替代主线。

## 直觉解释
控制问题的重点不是“有没有 edge”，而是：

$$
\text{在当前观测与当前 Monad 机制状态下，应该现在 act，还是继续 wait，还是直接 abort。}
$$

也就是说，真正的边界始终是 unified kernel 下的动作边界，而不是某个单一 score threshold。

## 与主线的关系
本页只负责把 unified action 拆开解释，方便后续投影分析与策略比较。  
它不引入新的 primitive state，也不把 `q/r/\kappa/u` 升回主线。

## 数据前提 / 识别边界
这套控制结构允许：

- 先在 reduced-form 下使用压缩投影
- 后续再用更强观测层替换对应投影

因此控制问题先于具体识别器而成立。

## 经验含义
经验层最重要的任务不是“复刻 Bellman 全貌”，而是尽快回答：

1. 哪些动作边界在数据上是可见的
2. 哪些投影最影响 act / wait / abort
3. 哪些出价变量系统性改变机会排序

## 下一步
继续读 [Reserve 子结构与可行动作集](./23-reserve-constrained-control-k3.md)。

# 最小 Bellman 系统与状态压缩

## 目的
在 unified kernel 主模型之下，恢复一套可直接用于推导、比较静态和经验校准的 reduced-form 最小 Bellman 系统。

这篇文档的地位是：

$$
\text{统一核主模型}
\to
\text{reduced-form 状态压缩}
\to
\text{最小 Bellman 系统}.
$$

它不是新的主模型页，而是 unified kernel 的从属压缩层。  
本页中的每个压缩状态量，都应回指到 [参数建模总页](../30-identification-and-data/30-parameter-map.md) 中的来源与角色，而不是被理解为凭空给定。

## 1. 最小状态
把原来分散的对象压成

$$
s_t
=
\bigl(
 f_t,\,
 \theta_t^{\mathrm{pool}},\,
 \theta_t^{\mathrm{route}},\,
 u_t,\,
 \nu_t,\,
 b_t,\,
 e_t,\,
 h_t,\,
\zeta_t,\,
F_t
\bigr)
$$

其中：

- $f_t$：当前机会对应的协议家族标签
  $$
  f_t\in\{\text{cpmm},\text{clmm},\text{stable},\text{weighted},\text{hooked-clmm}\}
  $$
- $\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}$：机会几何的压缩坐标，定义 gross opportunity
  $$
  \Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})
  $$
  这里：
  - $\theta_t^{\mathrm{pool}}$ 表示 pool 家族内部的几何状态
  - $\theta_t^{\mathrm{route}}$ 表示路径、router、vault、hook 等 route-level 上下文
  - $A_t,B_t$ 不再代表全部 AMM，只在 `cpmm` 或局部二次近似时作为辅助坐标使用
- $u_t$：当前可见 execution output 最终被验证并成立的概率  
  这里把前面的共识与验证层压成一个量；若要拆开，也可以写成
  $$
  u_t=p_t d_t
  $$
  其中 $p_t$ 是 canonical probability，$d_t$ 是条件验证一致性概率。
- $\nu_t$：传播-入链状态，决定
  $$
  q_t(a)=g_q(a;\nu_t)
  $$
- $b_t$：当前 reserve slack
- $e_t$：emptying exception / delegation 可用性状态
- $h_t$：局部冲突强度
- $\zeta_t$：冲突损失弹性
- $F_t$：当前 base fee

于是：

$$
r_t(a)=g_r(a;b_t,e_t),
\qquad
\kappa_t(a)=g_\kappa(a;h_t,\zeta_t)
$$

这里的关键是：  
`q,r,\kappa` 不再是独立参数，而是压缩状态诱导出来的状态函数。

### 压缩状态的来源回指
这组压缩状态统一来自 [参数建模总页](../30-identification-and-data/30-parameter-map.md)：

- $f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}$：协议家族机会几何参数组
- $u_t$：block / verification 参数组
- $\nu_t$：propagation / inclusion 参数组
- $b_t,e_t$：reserve / survival 参数组
- $h_t,\zeta_t$：conflict / friction 参数组
- $F_t$：fee 参数组

## 2. 动作集合
令 `act` 动作为

$$
a_t=(P_t,x_t,\ell_t,\pi_t,\overline F_t)
$$

其中：

- $P_t$：路径、venue 选择与协议家族上下文
- $x_t$：交易规模
- $\ell_t$：gas limit
- $\pi_t$：priority bid
- $\overline F_t$：max fee cap

则可行动作集合写成

$$
\mathcal A(s_t)
=
\left\{
(x,\ell,\pi,\overline F):
\ell \cdot \min(F_t+\pi,\overline F)\le b_t
\right\}
$$

这是 reserve / gas 约束在 Bellman 里的最小投影。  
若 sender 当前不能使用 exception，则这个集合还要再被 $e_t$ 缩小。

## 3. 一步收益
若采取 `act` 动作 $a=(P,x,\ell,\pi,\overline F)$，定义 gas 成本：

$$
c_t(a)=\ell \cdot \min(F_t+\pi,\overline F)
$$

gross opportunity 为：

$$
\Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})
$$

则一步期望收益写成：

$$
J_t^{\mathrm{act}}(s_t,a)
=
q_t(a)
\left[
u_t r_t(a)\Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})
-
c_t(a)
-
\bigl(1-u_t r_t(a)\bigr)L_t(a)
\right]
-
\kappa_t(a)
$$

解释如下：

- $q_t(a)$：交易是否及时入链并生效
- $u_t r_t(a)$：即便入链，机会是否最终成立并 survive
- $L_t(a)$：押错、revert、错过真实世界状态时的损失
- $\kappa_t(a)$：冲突-重执行带来的额外摩擦

## 4. 最小 Bellman 递推
定义三个动作：`abort / wait / act`。

则：

$$
V_t(s_t)
=
\max
\left\{
V_t^{\mathrm{abort}}(s_t),
V_t^{\mathrm{wait}}(s_t),
V_t^{\mathrm{act}}(s_t)
\right\}
$$

其中：

$$
V_t^{\mathrm{abort}}(s_t)=0
$$

$$
V_t^{\mathrm{wait}}(s_t)
=
-
K_t^{\mathrm{wait}}(s_t)
+
\beta\,
\mathbb E\!\left[
V_{t+1}(s_{t+1})
\mid s_t,\mathrm{wait}
\right]
$$

$$
V_t^{\mathrm{act}}(s_t)
=
\sup_{a\in\mathcal A(s_t)}
\left\{
J_t^{\mathrm{act}}(s_t,a)
+
\beta\,
\mathbb E\!\left[
V_{t+1}(s_{t+1})
\mid s_t,a
\right]
\right\}
$$

这就是最小可用 Bellman 系统。

## 5. `act` 之后的状态转移
`act` 后的转移核自然分成三种情形：

- `miss`：没入链
- `success`：入链且最终成立
- `fail`：入链但最终不成立或不 survive

因此：

$$
\mathbb P(\cdot\mid s_t,a)
=
\bigl(1-q_t(a)\bigr)P_t^{\mathrm{miss}}
+
q_t(a)u_t r_t(a)P_t^{\mathrm{succ}}
+
q_t(a)\bigl(1-u_t r_t(a)\bigr)P_t^{\mathrm{fail}}
$$

这一步很重要，因为它说明：

- $q_t$ 控制“有没有机会进入真实世界”
- $u_t r_t$ 控制“进入后是不是真成功”
- 三条路径会把 reserve、冲突、机会状态带到不同的下一期

## 6. 一个很干净的 `act` 阈值
如果先看 one-step myopic 比较，`act` 相对 `abort` 的条件是

$$
J_t^{\mathrm{act}}(s_t,a)\ge 0
$$

即

$$
q_t(a)
\left[
u_t r_t(a)\Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})
-
c_t(a)
-
\bigl(1-u_t r_t(a)\bigr)L_t(a)
\right]
\ge
\kappa_t(a)
$$

整理得：

$$
q_t(a)
\left[
u_t r_t(a)\bigl(\Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})+L_t(a)\bigr)
-
\bigl(c_t(a)+L_t(a)\bigr)
\right]
\ge
\kappa_t(a)
$$

所以最小成功概率阈值是：

$$
u_t
\ge
u_t^\ast(a)
=
\frac{
c_t(a)+L_t(a)+\kappa_t(a)/q_t(a)
}{
r_t(a)\bigl(\Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})+L_t(a)\bigr)
}
$$

这条式子把几层东西彻底分开了：

- $q_t$ 越低，阈值越高
- $r_t$ 越低，阈值越高
- $\kappa_t$ 越高，阈值越高
- gross opportunity 越大，阈值越低

如果再把 `wait` 的期权价值加进去，阈值只会更高。

## 7. 最优规模为什么会被 Monad 机制压缩
在统一 Bellman 外壳下，不同协议家族都通过

$$
\Gamma_t(P_t,x;f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}})
$$

进入控制问题。  
如果进一步只讨论 `cpmm` 或某个具体家族的局部二次近似，则可临时写成：

$$
\Gamma_t(x)=A_t x-B_t x^2
$$

这里的 `A_t,B_t` 是局部基线坐标，不再代表全部 AMM 的统一参数。

并做一个最简近似：

- $q_t,r_t,u_t$ 在局部对 $x$ 近似常数
- $c_t(a)=\gamma_{0,t}+\gamma_{1,t}x$
- $L_t(a)=\lambda_{0,t}+\lambda_{1,t}x$
- $\kappa_t(a)=\kappa_{0,t}+\kappa_{1,t}x$

则 `act` 的目标变成：

$$
J_t(x)
=
q_t
\left[
u_t r_t(A_t x-B_t x^2)
-
(\gamma_{0,t}+\gamma_{1,t}x)
-
(1-u_t r_t)(\lambda_{0,t}+\lambda_{1,t}x)
\right]
-
(\kappa_{0,t}+\kappa_{1,t}x)
$$

一阶条件给出：

$$
x_t^\ast
=
\frac{
u_t r_t A_t
-
\gamma_{1,t}
-
(1-u_t r_t)\lambda_{1,t}
-
\kappa_{1,t}/q_t
}{
2u_t r_t B_t
}
$$

这条式子直接告诉你：

$$
u_t\downarrow,\quad
q_t\downarrow,\quad
r_t\downarrow,\quad
\kappa_{1,t}\uparrow
\;\Longrightarrow\;
x_t^\ast\downarrow
$$

所以 Monad 机制并不只是“改变 capture probability”，它会系统性压缩最优规模。

## 8. 真正还需要环境提供的，只剩什么
在这个 Bellman 里，协议层已经固定了很多东西。  
真正还需要环境提供或校准的，主要是下面四类：

$$
\xi_t
=
(f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}},\nu_t,h_t,\zeta_t)
$$

更细地说：

- $f_t,\theta_t^{\mathrm{pool}},\theta_t^{\mathrm{route}}$：机会几何家族与局部坐标，来自 pool 类型、路由结构、外部价格环境与协议数学
- $\nu_t$：传播-竞争状态，来自网络时延、leader 可达性、对手 bid 分布
- $h_t$：冲突强度，来自热点账户 / slot 分布
- $\zeta_t$：冲突损失弹性，来自重执行延迟、机会寿命、失败代价

而下面这些是协议 / 状态诱导出来的，不该再当自由参数喂进去：

- $q_t = g_q(a;\nu_t)$
- $r_t = g_r(a;b_t,e_t)$
- $\kappa_t = g_\kappa(a;h_t,\zeta_t)$
- $u_t$ 来自 block state 与 execution verification 状态

## 9. 这套最小系统的意义
现在模型已经从“很多参数没数据”变成了：

$$
\text{协议给定状态转移}
+
\text{少量环境输入}
\to
\text{最优 act / wait / abort 决策}
$$

这一步最重要，因为它说明后面要做的不是“继续列参数”，而是：

1. 决定哪些状态必须保留进 Bellman
2. 决定哪些环境输入需要校准
3. 决定哪些子模型还要再细化

## 与主线的关系
本页是 unified kernel 的 reduced-form 压缩层。  
它保留了第一性原理之后最重要的低维控制对象，但不替代 unified kernel 作为唯一主模型。

同时，它也不解释“这些参数为何如此建模”。  
参数的角色、来源、协议给定部分、环境输入部分与校准位置，统一回到 [参数建模总页](../30-identification-and-data/30-parameter-map.md) 与 [第一性原理下的投影结构建模](../30-identification-and-data/36-first-principles-projection-derivations.md)。

## 下一步
继续读：

- [参数建模总页](../30-identification-and-data/30-parameter-map.md)
- [第一性原理下的投影结构建模](../30-identification-and-data/36-first-principles-projection-derivations.md)

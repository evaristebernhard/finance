# Reserve 子结构与可行动作集

## 目的
把 Monad 的 reserve / gas 规则写成 unified kernel 中的一个显式子结构，并说明它如何进入可行动作集，而不是另起一条平行主线。

## 核心对象
在统一状态里，reserve 相关对象被归入

$$
R_t.
$$

为了贴近 Monad 机制，可把它进一步写成一组 reserve 子状态：

$$
R_t=(\mathcal R_t,m_t^{(1)},m_t^{(2)},e_t^{\mathrm{exc}},d_t^{\mathrm{del}},\dots).
$$

其中：

- $\mathcal R_t$：当前可用 reserve-style budget
- $m_t^{(1)},m_t^{(2)}$：前两块遗留 obligations
- $e_t^{\mathrm{exc}}$：emptying exception 相关状态
- $d_t^{\mathrm{del}}$：delegation / authority 相关状态

## 成本与可行动作集
在 Monad 风格的局部展开里，单笔 upfront cost 写成

$$
c_t(a_t)=\ell_t\cdot \min(F_t+\pi_t,\overline F_t).
$$

于是 reserve 子结构诱导的可行动作集合可写为

$$
\mathcal A_R(s_t)=
\left\{
a_t:
c_t(a_t)+m_t^{(1)}+m_t^{(2)}\le \mathcal R_t
\text{，且满足 exception / delegation 约束}
\right\}.
$$

主模型中的可行动作集合是

$$
\mathcal A(s_t)\subseteq \mathcal A_R(s_t),
$$

也即 reserve 子结构只是 unified admissibility map 的一部分。

## 状态更新
若采取 act 动作，在最简单的滚动三块写法中，

$$
m_{t+1}^{(1)}=c_t(a_t),
\qquad
m_{t+1}^{(2)}=m_t^{(1)}.
$$

更一般地，这个更新由 unified kernel 生成；上式只是在 Monad `k=3` 约束下的局部化表示。

## 为什么它不是独立主线
reserve 子结构的重要性在于它会同时影响：

- 可行动作集
- 生存投影 $r_t(a)$
- 路径与规模排序

但它并不构成新的主模型，因为它始终是

$$
R_t \subset s_t
$$

中的一个子结构。

## 直觉解释
reserve 规则的真正作用，不是单纯提高 fee，而是把一部分动作直接逐出可行域。  
因此 Monad 上的 gas / reserve 机制不是“成本背景”，而是控制问题的一部分。

## 与主线的关系
本页是 unified kernel 的一个 Monad-specific 子结构页。  
它只说明：

1. $R_t$ 里装了什么
2. $R_t$ 如何约束 $\mathcal A(s_t)$
3. $R_t$ 如何进入 $r_t(a)$ 和 budget 相关比较静态

## 数据前提 / 识别边界
- $F_t$ 可以较稳地由链上数据给出
- $\ell_t,\pi_t,\overline F_t$ 可由交易字段给出
- 更贴近协议的 $\mathcal R_t,e_t^{\mathrm{exc}},d_t^{\mathrm{del}}$ 需要更细的账户与状态信息

## 经验含义
这一页直接服务于下面几类问题：

1. 预算约束如何改变机会排序
2. 高 fee / 紧 budget 时最优规模如何收缩
3. reserve 相关状态如何提高 wait / abort 的占比

## 下一步
继续读 [统一核命题与可检验推论](./24-propositions-and-testable-claims.md)。

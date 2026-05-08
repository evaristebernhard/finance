# 观测、belief 与 reduced-form 压缩

## 目的
说明在统一核主模型下，部分观测如何进入问题，以及为什么压缩 belief 是经验层的需要，而不是主线 primitive 的替代品。

## 核心对象
统一核中的隐藏状态是

$$
s_t=(G_t,M_t,C_t,R_t,E_t,F_t),
$$

交易者观测到的是某种观测过程

$$
O_t.
$$

因此 belief 定义为

$$
b_t=\Pr(s_t\mid \mathcal F_t^{\mathrm{obs}}).
$$

## 观测结构
理论上，可以把观测过程写成一个观测核：

$$
\mathcal Q_t(dO_t\mid s_t,a_{t-1}).
$$

于是，belief 更新由

$$
\mathcal K_t(ds',dy\mid s_t,a_t)
$$

与

$$
\mathcal Q_{t+1}(dO_{t+1}\mid s_{t+1},a_t)
$$

共同决定。

抽象地写，

$$
b_{t+1}=\mathcal U(b_t,O_{t+1},a_t),
$$

其中 $\mathcal U$ 是由 kernel 与 observation kernel 诱导出的过滤算子。

## 主线与压缩的边界
从这一版开始，下面的区分必须保持稳定：

### 一、主线对象
- $s_t$
- $a_t$
- $\mathcal K_t$
- $b_t$

### 二、reduced-form 压缩对象
例如：

$$
\tilde b_t=\psi(b_t)
$$

它可以压缩成若干 summary statistic，但它不再替代 canonical belief。

这意味着像

$$
(p_t,u_t,r_t,q_t,\kappa_t,M_{\max,t},E_{\mathrm{cycle},t},F_t,\dots)
$$

这样的低维向量，只能出现在 reduced-form 层，而不再被视为主线 primitive。

## 常见压缩量的来源
在统一核视角下，常见 summary statistic 的来源统一写成：

- $p_t=g_p(b_t)$
- $u_t=g_u(b_t)$
- $q_t(a)=g_q(b_t,a)$
- $r_t(a)=g_r(b_t,a)$
- $\kappa_t(a)=g_\kappa(b_t,a)$
- $M_{\max,t}=g_M(b_t)$
- $E_{\mathrm{cycle},t}=g_E(b_t)$

这里的重点不是它们的数值形式，而是它们不再拥有和 $s_t$ 并列的地位。

## 直觉解释
过去容易混乱的地方，是把：

- 主状态
- 投影
- 压缩 belief

混成同一层来写。  
统一核之后，更自然的顺序是：

$$
s_t
\;\to\;
b_t
\;\to\;
\tilde b_t
\;\to\;
\text{proxy / estimand}.
$$

## 与主线的关系
本页只解释 unified kernel 在部分观测下如何进入 belief-driven control。  
它不重新定义主模型，也不引入新的 primitive state。

## 数据前提 / 识别边界
- RPC-only：通常只能直接支持压缩后的 reduced-form 对象
- Execution Events：可以让部分投影更贴近 kernel 结构
- 结构仿真：可以帮助研究 $\mathcal U$ 的局部行为与 summary statistic 的稳定性

## 经验含义
经验层真正要决定的不是“主模型是什么”，而是：

1. 观测到哪些量
2. belief 被压缩成哪些 summary
3. 哪些 summary 足以支撑第一版控制与识别

## 下一步
继续读 [控制分解：路径、规模与出价](./22-partial-information-control.md)。

# 统一核命题与可检验推论

## 目的
把 unified kernel 主模型在经验层最重要的理论推论集中整理，但不把这些命题再写成 competing mainline。

## 核心对象
本页默认以下对象都已由主模型给出：

$$
s_t,\qquad a_t,\qquad \mathcal K_t,\qquad b_t,\qquad V_t.
$$

常见投影如

$$
\Gamma_t,\ q_t,\ r_t,\ \kappa_t,\ u_t,\ p_t
$$

都被视为 kernel 的从属对象。

## 命题一：等待的信息价值命题
若

$$
\mathbb E[V_{t+1}(b_{t+1})\mid b_t,\text{wait}]
>
\sup_{a_t\in\mathcal A^{\mathrm{act}}(b_t)} \mathbb E[y_t\mid b_t,a_t],
$$

则最优动作是 `wait`。  
这说明提交态升级、传播状态改善或冲突风险下降本身具有信息价值。

## 命题二：状态升级的投影稳定化命题
若 Monad 提交态从较早层级升级到较稳定层级，则与 block / verification 相关的投影应更稳定。  
经验上，这通常表现为：

- $p_t$ 的代理上升或波动下降
- $u_t$ 的代理上升或波动下降

## 命题三：reserve 子结构重排命题
在其他条件不变时，若 $R_t$ 表示的 reserve slack 收缩，则可行动作集收缩，且高 upfront cost 动作更容易被逐出最优动作集。

## 命题四：冲突敏感路径排序命题
在 gross opportunity 相近时，若两条路径对应的访问与冲突环境差异显著，则低 $\kappa_t$ 路径更可能成为最优路径。  
这说明在 Monad 上，路径排序不再只由 AMM edge 决定。

## 命题五：压缩 belief 的有效性命题
若某组 low-dimensional summary 已足以近似解释动作边界与 realized outcome，则它可以被视为 unified belief 的有效 reduced-form 压缩；否则应回退到更丰富的状态摘要。

## 直觉解释
这些命题共同表达的是：

$$
\text{AMM 机会会被 Monad 机制通过 kernel 重写成一个条件控制问题，而不是一个静态 edge 排序问题。}
$$

## 与主线的关系
本页不定义新的理论骨架，只把主线中最值得检验的推论集中列出，方便后续识别、实验与校准工作逐条对应。

## 数据前提 / 识别边界
这些命题都允许：

- 先在 reduced-form 层做 proxy 检验
- 后续在更强观测层下升级检验强度

## 下一步
先读 [最小 Bellman 系统与状态压缩](./25-minimal-bellman-system.md)，再回到 [投影与估计对象图](../30-identification-and-data/30-parameter-map.md)，把这些命题对应到 projection、summary 与 calibration target。

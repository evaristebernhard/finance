# Local Mempool 与 Leader-Path

## 目的
说明为什么 Monad 上的可执行性不是“看见机会就一定能打”，而要单独建模传播结构与入块概率。

## 证据分层速览
本页需要先明确一条边界：  
**它主要依赖外部共识仓库或外部官方资料，不是当前 execution 仓库可以直接验证的机制页。**

| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| `execution daemon` 无网络能力 | 可直接观测 | 当前仓库代码 | `external/monad-official/monad/docs/overview.md` | 机制边界条件 |
| `local mempool / future leaders / forwarding / retry` | 研究latent | 外部官方资料 | `monad-bft` / 外部共识资料 | $M_t,C_t$ 的机制背景 |
| `\Lambda_t` | 研究latent | 建模假设 | 本页、主模型页 | 传播环境局部坐标 |
| `q_t(a \mid \Lambda_t)` | 研究latent | 外部官方资料 + 建模假设 | 参数页、推导页 | 入链 projection |
| pending 可见性 / provider 暴露的 `txpool_*` | RPC弱代理 | 外部基础设施实现 | 特定 provider 或 indexer | 弱观测 proxy |

## 核心对象
把当前传播结构记为

$$
\Lambda_t,
$$

并定义动作 $a$ 的成功纳入概率

$$
q_t(a\mid \Lambda_t).
$$

这里的关键不是声称 `\Lambda_t` 已经在当前仓库中有现成结构体，而是说明：  
一旦把 execution 代码、外部共识机制和实际基础设施环境一起放进控制问题，传播结构就不能再被当作普通误差项。

## 当前仓库能确认什么
当前工作区里的 execution 仓库能较明确地告诉我们：

- execution daemon 是本地执行服务
- 它本身不承载网络身份
- 它本身不负责公开网络传播机制

这意味着：

$$
\text{传播、leader-path 与 future-leader 可达性不应被误写成 execution 仓库已直接给定的代码事实。}
$$

## 机制含义
在外部共识资料所描述的传播环境下，研究上更自然的 reduced-form 写法是：

$$
\Pr(\text{动作 }a\text{ 在当前窗口被及时纳入并生效}\mid \mathcal F_t^{\mathrm{obs}}).
$$

因此，即使两个参与者在同一时刻识别到同一个机会，他们面对的

$$
q_t(a\mid \Lambda_t)
$$

也可能不同。

这里的不同来自：

- 能否及时把动作送达有效 leader
- 在竞争与容量约束下是否被选中
- 在传播窗口内是否拥有足够可见性

## 直觉解释
这件事意味着 Monad 上的竞争不是单纯“谁更快看到价差”，而是：

$$
\text{谁更快看到} \times \text{谁更能把动作送到有效 leader}.
$$

因此，传播结构不是噪声，而是主模型的一部分。

## 与主线的关系
这篇文档提供的是 unified kernel 中 $C_t$ 与部分 $M_t$ 的局部机制背景。  
其中：

- $\Lambda_t$ 可被视为传播环境的局部坐标
- $q_t(a)$ 是由 $M_t,C_t$ 与动作共同诱导出的入链投影

因此，传播结构属于主线状态的一部分，而不是普通误差项。

## 数据前提 / 识别边界
- 当前 execution 仓库：只能给出“传播机制不在这里直接落地”的边界事实
- RPC-only：pending 可见性、provider 暴露的 `txpool_*` 或自建 indexer 只能作为弱代理，**不是**协议保证、也不是默认可用接口
- 强版本：若要更强识别 `q_t(a)`，仍需要外部共识资料、provider 行为说明或更细的传播观测

## 下一步
接着读 [Gas Pricing 与 Reserve Balance](./12-gas-pricing-and-reserve-balance.md)。

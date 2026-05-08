# 统一核下的估计程序

## 目的
说明在 unified kernel 主模型下，估计程序应遵守什么顺序，避免再次把方法层写成 competing mainline。

## 核心原则
估计程序必须服从下面这个顺序：

$$
\text{主线 primitive}
\to
\text{参数建模链}
\to
\text{压缩 Bellman}
\to
\text{观测与压缩}
\to
\text{校准与估计}.
$$

如果跳过前两步，直接进入 proxy、因子或机器学习，研究会再次打偏。

## 当前仓库可立即开展的输入物
在当前工作区里，最先应该交付的不是复杂估计器，而是 5 个输入物：

1. **事件到模型映射表**  
   把 `BlockQC / BlockFinalized / BlockVerified / TxnReject / TxnEvmOutput / TxnCallFrame / AccountAccess / StorageAccess` 回接到 `M_t / R_t / E_t` 及其 projection。
2. **reserve 规则摘要表**  
   把 revision gating、delegated account 限制、pending-block 检查、selfdestruct exemption、max reserve 占位逻辑整理成结构化摘要。
3. **RPC proxy 清单**  
   明确哪些是稳定链上事实，哪些只是 `latest / safe / finalized` 或 provider-specific pending proxy。
4. **外部共识未知项列表**  
   明确 `leader path / future leaders / forwarding / retry / canonical probability` 中哪些部分当前工作区不能直接验证。
5. **弱观测后验推断表**  
   把 RPC、Envio、Alchemy、Dune、receipts、traces 等可得数据分成 observed facts、weak proxies、latent states 与 posterior summaries，明确哪些对象可直接观测，哪些只能后验反演。

这 5 个输入物如果没有先固定，后面的 reduced-form 和估计器会缺少对象基础。

## 估计顺序
### Step 0：先固定主线与对象层级
先固定：

- primitive 是什么
- projection 是什么
- summary 是什么
- calibration target 是什么
- 哪些对象当前仓库可验证
- 哪些对象依赖外部资料

这一层未完成时，不应进入任何具体估计器争论。

### Step 1：先完成参数建模链
先经过 [参数建模总页](./30-parameter-map.md) 明确：

- 参数定义
- 当前仓库已验证部分
- 外部机制说明部分
- 环境输入部分
- 校准对象部分

若这一层没有完成，后面的 proxy 和估计器会失去对象基础。

### Step 2：再进入压缩 Bellman
把参数链条明确映射到 [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md)，确认：

- 哪些量进入压缩状态
- 哪些量作为状态函数进入 Bellman
- 哪些量不应再作为自由参数单独喂入

### Step 3：再恢复或近似 $G_t$ 的市场几何
优先得到：

- 路径级 gross opportunity
- 局部几何展开
- 图结构 summary

这一步的目的是让 $\Gamma_t(P,x)$ 及其 summary 有可计算基础。

### Step 4：再构造 kernel projection 的观测层
在 RPC-only 或更强数据面下，优先构造：

- block-state 事件重建与 `p_t/u_t` 的弱观测
- `q_t(a)` 的 provider-specific proxy
- `r_t(a)` 的 survival proxy
- `\kappa_t(a)` 的访问结构 proxy

如果当前阶段不运行全节点，也不依赖原生 Execution Events，则应优先进入 [弱观测后验推断：无节点阶段的数据策略](./37-weak-observation-posterior-inference.md)。  
这一步不是把 weak proxy 写成强观测，而是构造：

$$
\Pr(M_t,E_t,R_t\mid O_{1:t})
$$

并从后验中派生服务 Bellman 的 reduced-form summary。

### Step 5：再做控制相关比较静态
优先回答：

- act / wait / abort 的边界如何移动
- reserve 子结构如何改变可行域
- 冲突与传播如何改变路径排序

### Step 6：再做后验过滤与校准
在对象映射稳定后，无节点阶段的核心估计路线不再是“等强观测齐全”，而是：

- state-space filtering
- EM / variational filtering
- weak-to-strong calibration
- small strong-labeled sample distillation

若需要先把这一阶段写成严格的 inverse problem、identification 与 robust Bellman，再来安排算法顺序，请先读 [弱观测逆问题、识别与鲁棒 Bellman](./39-weak-observation-inverse-problem-and-robust-bellman.md)。

这些方法只允许服务 $M_t,E_t,R_t$ 的 posterior inference，不能反向定义 primitive。

### Step 7：最后才做更复杂表示学习
包括：

- 因子与 representation learning
- 更高阶动态或频域分析
- 非结构化预测模型

这些方法只能建立在前面对象映射与 posterior validation 已经稳定的前提上。

## 方法的定位
### 一、时域与事件研究
用于研究 unified kernel 投影在状态升级、传播变化、冲突变化下的比较静态。

### 二、reduced-form 动态
用于描述某些 summary 的演化，而不是替代 unified kernel。

### 三、弱观测后验推断
用于在没有原生 Execution Events 的阶段，把可得 observed facts 和 weak proxies 组织成 $M_t,E_t,R_t$ 的 posterior belief。

### 四、机器学习
用于压缩、预测或辅助校准 projection，不用于重新定义主模型。

## 直觉解释
估计程序真正服务的是：

$$
\text{怎样看见 unified kernel 的边际对象，及其如何进入控制问题。}
$$

而不是：

$$
\text{用方法反向创造一个新的主线。}
$$

## 与主线的关系
本页是 unified kernel 的方法伴随页。  
它只安排顺序，不重新定义理论骨架。

## 下一步
若当前阶段不跑全节点，请先读 [弱观测后验推断：无节点阶段的数据策略](./37-weak-observation-posterior-inference.md)。  
若需要做结构比较静态与压力测试，请读 [结构仿真伴随层](./35-structural-simulation-layer.md)。

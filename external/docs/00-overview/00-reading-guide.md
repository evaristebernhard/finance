# 阅读指南

## 目的
这套文档从这一版开始只保留一条理论主线：

$$
\text{统一状态-动作-转移核模型}
$$

全套文档都必须围绕这条主线组织。  
后续出现的 AMM 几何、`q/r/\kappa/u/p`、代理变量、仿真轴、估计器，都不再被视为并列主线，而只被视为：

1. 主线的原语
2. 主线的投影
3. 主线的 reduced-form 压缩
4. 主线的识别、校准与实验配套

## 统一标签约定
从这一版开始，每一页开头都应优先回答三件事：

1. 哪些对象当前仓库可以直接核对
2. 哪些对象依赖外部官方资料或共识侧仓库
3. 哪些对象只是研究层的 latent state、projection 或校准目标

统一采用下面两组标签：

- 对象类型：`可直接观测`、`事件重建`、`RPC弱代理`、`研究latent`
- 证据来源：`当前仓库代码`、`外部官方资料`、`建模假设`

后续机制页、主模型页、数据页都默认使用同一个通用表头：

| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |

其中：

- `当前状态` 用来说明该对象现在是可直接观测、事件重建、RPC 弱代理还是研究 latent
- `当前锚点/外部锚点` 用来明确读者应该去哪个代码路径、外部仓库或页面核对

## 唯一主线
唯一 canonical 模型定义在 [统一核主模型](../20-core-model/20-monad-mev-main-model.md)。

该页定义且仅定义下面五类 primitive：

- 状态：
  $$
  s_t=(G_t,M_t,C_t,R_t,E_t,F_t)
  $$
- 动作：
  $$
  a_t=(P_t,x_t,\ell_t,\pi_t,\overline F_t,d_t)
  $$
- 观测后的 belief：
  $$
  b_t=\Pr(s_t\mid \mathcal F_t^{\mathrm{obs}})
  $$
- 转移核：
  $$
  \mathcal K_t(ds',dy\mid s_t,a_t)
  $$
- 价值函数：
  $$
  V_t(b_t)=\sup_{a_t}\left\{\mathbb E[y_t\mid b_t,a_t]+\beta\,\mathbb E[V_{t+1}(b_{t+1})\mid b_t,a_t]\right\}
  $$

除了这些对象，其他常见量都不再当作主线 primitive。

## 阅读层级
建议按下面顺序阅读，并把每一层的职责严格分开。

### 第一层：协议与市场原语
这些页面只负责给统一核提供原语，不定义新的主模型：

1. [项目总图](./01-project-map.md)
2. [符号与术语表](./02-notation-and-glossary.md)
3. [Block States 与投机执行](../10-monad-mechanism/10-block-states-and-speculative-execution.md)
4. [Local Mempool 与 Leader-Path](../10-monad-mechanism/11-local-mempool-and-leader-path.md)
5. [Gas Pricing 与 Reserve Balance](../10-monad-mechanism/12-gas-pricing-and-reserve-balance.md)

说明：

- 这一层优先交代对象的证据等级
- 不是所有机制都能在当前 execution 仓库中直接验证
- 若对象依赖外部共识资料，页面必须显式标注

### 第二层：统一核主模型
这一层只定义 canonical state、action、kernel 与 Bellman：

6. [统一核主模型](../20-core-model/20-monad-mev-main-model.md)

说明：

- `s_t` 是研究层状态组织，不是代码里的现成结构体
- 主模型必须接受“当前仓库代码 + 外部机制说明 + 建模 latent”混合供给

### 第三层：主线的从属展开
这一层只能解释主线，不允许再引入 competing mainline：

7. [观测、belief 与 reduced-form 压缩](../20-core-model/21-state-space-and-observation.md)
8. [控制分解：路径、规模与出价](../20-core-model/22-partial-information-control.md)
9. [Reserve 子结构与可行动作集](../20-core-model/23-reserve-constrained-control-k3.md)
10. [统一核命题与可检验推论](../20-core-model/24-propositions-and-testable-claims.md)
11. [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md)
说明：这是参数进入控制问题后的压缩 Bellman 落点页。
12. [参数建模总页](../30-identification-and-data/30-parameter-map.md)
说明：这是“参数定义 -> 当前仓库已验证 / 外部机制说明 -> 环境输入 -> 校准对象”的主伴随页。
13. [第一性原理下的投影结构建模](../30-identification-and-data/36-first-principles-projection-derivations.md)
说明：这是参数建模总页对应的公式更密推导附页。

### 第四层：观测、识别与校准
这一层只回答“如何看见主线中的对象”，不重新定义主线：

14. [数据来源与校准边界](../30-identification-and-data/31-data-sources-and-availability.md)
15. [RPC-only reduced-form 层](../30-identification-and-data/32-rpc-only-proxy-layer.md)
16. [Execution Events 强观测层](../30-identification-and-data/33-execution-events-strong-layer.md)
17. [弱观测后验推断](../30-identification-and-data/37-weak-observation-posterior-inference.md)
说明：这是无节点阶段的数据策略页，用可得事实与弱代理反演 $M_t/E_t/R_t$ 的 posterior summary。
18. [弱观测逆问题、识别与鲁棒 Bellman](../30-identification-and-data/39-weak-observation-inverse-problem-and-robust-bellman.md)
说明：这是弱观测后验推断的严格数学化 companion note，把问题定义、识别边界与 robust Bellman 写成 formal problem。
19. [近头实时数据 API 提供清单](../30-identification-and-data/38-near-head-realtime-api-checklist.md)
说明：这是面向实现与协作的 API handover 页，固定当前仓库最少需要哪些 RPC、near-head 和 traces/indexer 访问。
20. [结构仿真伴随层](../30-identification-and-data/35-structural-simulation-layer.md)
21. [统一核下的估计程序](../30-identification-and-data/34-estimation-program.md)

说明：

- RPC-only 只保留稳定链上事实与 provider-specific proxy
- Execution Events 负责把部分对象从弱代理升级为事件重建或强观测
- 弱观测后验推断承认部分数据可得、强状态不可得，并把两者通过 belief / calibration 连接
- 形式化逆问题页负责把无节点阶段的问题严格写成 inverse problem、identification 与 robust Bellman
- 近头实时 API 清单负责把“想要什么数据”收缩成可 handover、可申请、可验证的访问合同
- 识别层不得反向改写主模型 primitive

## 实现入口
研究主文档与实现代码现在统一保留在当前 workspace。  
RPC-only 数据抓取不再作为独立项目存在，而是当前工作区内部的 adapter crate：

- [实现边界与 workspace adapter](./03-implementation-repos.md)
- `crates/monad-mev-rpc`
- `cargo run -p monad-mev-cli -- snapshot ...`

## 数学渲染约定
- 行内公式使用 `$...$`
- 块公式使用 `$$...$$`
- 不在 Markdown 表格里放复杂公式
- Mermaid 节点中不直接写 LaTeX

## 主线一句话概括
本项目真正研究的是：

$$
\text{在 Monad 的提交态、传播、reserve 与冲突机制下，AMM 图上的机会如何被统一核模型重写为最优 act / wait / abort 控制问题。}
$$

## 与主线的关系
本页只负责导航，并显式声明：  
**只有 `20-monad-mev-main-model.md` 是主模型页。**

## 下一步
先读 [项目总图](./01-project-map.md)，再进入机制原语层与统一核主模型。

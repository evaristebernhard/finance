# 数据来源与校准边界

## 目的
说明在 unified kernel 主模型下，数据层到底负责什么，以及它不能负责什么。

这篇文档只回答：

$$
\text{哪些数据面可以观测、重建、压缩或校准 kernel 中的对象？}
$$

它不再承担主模型定义职责。

## 核心原则
主线先于数据而存在。  
数据层只能做四件事：

1. 直接观测主线中的稳定对象
2. 事件重建主线中的部分状态
3. 构造主线投影的 reduced-form 弱代理
4. 校准环境过程与局部展开

因此，数据层不能反向决定：

- primitive state 是什么
- canonical belief 是什么
- 统一转移核是什么

## 数据层级
### A. 直接链上事实层
这层只保留较稳定、可重复取得的链上事实，例如：

- block / txn header 字段
- base fee、gas limit、priority fee、max fee cap
- receipt、状态延续、日志等已落链结果

### B. RPC-only reduced-form 层
这层主要支持：

- $G_t$ 的市场结构 summary
- $F_t$ 的较稳定观测
- 某些 `p/u/r/q/\kappa` 的弱代理

但这层不应再把 `latest / safe / finalized` 或 `txpool_*` 写成稳定协议真值。

### C. Execution Events 强观测层
这层主要支持：

- block-related event 与 commit-state 重建
- tx-level execution 过程
- account / storage access 结构

这层让部分对象从“弱代理”升级为“事件重建”或“更强观测”。

### D. 结构仿真伴随层
这不是观测层，而是校准与局部理解层。  
它的任务是：

- 研究 unified kernel 的比较静态
- 检查某些 projection 的局部单调性
- 在真实数据不足时给出压力测试与 regime sweep

## 数据与对象的映射
| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| `F_t` | 可直接观测 | 当前仓库代码 | block / txn header | primitive |
| block-related event 与 commit state | 事件重建 | 当前仓库代码 | exec event schema 与 block builder | $M_t$ 的局部坐标 |
| pending 可见性、`txpool_*` | RPC弱代理 | 外部基础设施实现 | 特定 provider / indexer | `q_t(a)` 的弱代理 |
| `AccountAccess / StorageAccess` | 事件重建 | 当前仓库代码 | exec event schema | $E_t$ 的局部坐标 |
| `p_t/u_t/q_t/r_t/\kappa_t` | 研究latent | 建模假设 | 主模型页、参数页 | projection |

## 当前边界
如果当前只能使用 RPC-only，那么更合理的做法是：

$$
\text{先保留稳定链上事实}
\quad\to\quad
\text{再构造 provider-specific proxy}
\quad\to\quad
\text{最后再判断哪些对象值得升级到事件层}.
$$

如果后续有 Execution Events，则可以把部分 projection 从弱代理升级为：

- block-state 的事件重建
- 访问结构的强观测
- tx-level 过程的更细状态约束

## 直觉解释
这一层最容易犯的错误，是把“数据里能看见什么”误写成“主模型里有什么”。  
统一核之后，应当反过来：

$$
\text{先有主模型}
\quad\to\quad
\text{再问当前仓库、外部资料和数据层能看见其中哪一部分}.
$$

## 与主线的关系
本页是统一核主模型的校准与观测边界说明页，不再和主模型竞争总纲地位。

## 下一步
继续读 [RPC-only reduced-form 层](./32-rpc-only-proxy-layer.md) 与 [Execution Events 强观测层](./33-execution-events-strong-layer.md)。

# RPC-only reduced-form 层

## 目的
说明在没有强事件流时，如何仅依赖 authenticated RPC / indexer 去构造 unified kernel 投影的 reduced-form 版本。

这篇文档不再把 RPC-only 结果写成主模型本身，而只把它视为：

$$
\text{对 kernel projection 的弱观测与近似压缩}.
$$

## 证据分层速览
| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| header / receipt / log / base fee 等已落链事实 | 可直接观测 | 当前链上数据 | RPC / indexer | 直接事实 |
| `latest / safe / finalized` | RPC弱代理 | RPC 提供方实现 | 特定 RPC 行为 | block-state 的极粗运营代理 |
| pending 可见性、`txpool_*` | RPC弱代理 | 外部基础设施实现 | 特定 provider / indexer | `q_t(a)` 的弱代理 |
| `p_t^{proxy}, u_t^{proxy}, r_t^{proxy}, q_t^{proxy}, \kappa_t^{proxy}` | RPC弱代理 | 建模假设 | 本页、参数页 | reduced-form proxy |

## 核心对象
RPC-only 层主要面向下面这些投影的 reduced-form 近似：

$$
p_t^{\mathrm{proxy}},\qquad
u_t^{\mathrm{proxy}},\qquad
r_t^{\mathrm{proxy}},\qquad
q_t^{\mathrm{proxy}},\qquad
\kappa_t^{\mathrm{proxy}}.
$$

同时，它能较稳地支撑 $G_t$ 和 $F_t$ 的部分 summary。

## RPC-only 能稳定支撑什么
RPC-only 最可靠的是“已经落链”的事实，而不是机制内部状态：

- block / txn header 字段
- base fee、gas limit、priority fee、max fee cap
- receipt、状态延续、日志
- 某些 trace 或 access-list 风格的派生信息

## 典型近似
### 一、block / verification 近似
`latest / safe / finalized` 只能用来构造非常粗的运营代理：

$$
p_t^{\mathrm{proxy}},\qquad
u_t^{\mathrm{proxy}}
$$

但它们**不能**再被写成对 `Proposed / Voted / Finalized / Verified` 的一一对应映射。

### 二、survival 近似
利用 receipt、状态延续与后续块结果，可对

$$
r_t(a)
$$

给出 reduced-form proxy。

### 三、inclusion 近似
利用 pending 可见性、入链延迟和 provider-specific 的 pending 接口，可对

$$
q_t(a)
$$

给出弱形式 proxy。

这里要特别保守：

- `txpool_*` 不是协议承诺
- 不同 provider 可能根本不暴露 pending 视图
- 即便暴露，也只能当作基础设施视角的弱代理

### 四、冲突近似
利用 access list、trace overlap、热点合约重叠，可对

$$
\kappa_t(a)
$$

给出 reduced-form proxy。

## RPC-only 的定位
RPC-only 的任务不是“重建整个 kernel”，而是尽快回答下面三个问题：

1. 哪些 projection 已经能在数据上工作
2. 哪些 projection 目前只能以 provider-specific proxy 形式进入
3. 哪些 projection 值得以后升级到更强观测层

## 与主线的关系
RPC-only 不定义 unified kernel，只为 unified kernel 的投影提供第一版 reduced-form 观测。

## 失败模式
最常见的失败方式有：

1. 把 proxy 当作 primitive 真值
2. 把 `latest / safe / finalized` 过度解释成 commit-state 精确映射
3. 把 provider-specific 的 `txpool_*` 当作协议保证
4. 在观测受限时仍然强行构造过细对象

## 下一步
如需更强观测，请继续读 [Execution Events 强观测层](./33-execution-events-strong-layer.md)。

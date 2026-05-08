# Execution Events 强观测层

## 目的
说明当数据从 RPC-only 升级到节点级事件流后，unified kernel 中的哪些投影与子结构可以被更强地观测。

重点不是把事件流当作“更多日志”，而是明确：

$$
\text{Execution Events 如何把若干对象从弱代理升级为事件重建或更强观测。}
$$

## 当前仓库里的直接锚点
当前工作区里的 `external/monad-official/monad` 已经提供了 execution event schema 以及 block commit-state builder。  
因此，这一页不是纯概念页，而是能直接回指到代码锚点的识别页。

## 核心对象
Execution Events 的价值主要体现在三类增强：

### 1. 对 $M_t$ 的增强
它可以更贴近地观测：

- block state 推进
- output 生成与验证相关过程

因此可增强：

$$
p_t,\qquad u_t
$$

相关投影的识别强度。

### 2. 对 $E_t$ 的增强
借助：

- `AccountAccess`
- `StorageAccess`
- `TxnReject`
- `TxnCallFrame`

可以把冲突与访问结构从粗 summary 升级为更贴近 kernel 的对象，从而增强：

$$
\kappa_t(a)
$$

的识别强度。

### 3. 对 $R_t$ 与执行过程的增强
借助 tx-level event sequence，可以更细地观察：

- effect 的形成与结束
- 某些 reject / revert / output 路径
- survival 相关执行结果

从而增强：

$$
r_t(a)
$$

的识别强度。

## 事件到模型对象映射表
| 事件类型 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| `BlockQC` | 可直接观测 | 当前仓库代码 | `external/monad-official/monad/rust/crates/monad-exec-events/src/events/mod.rs` | 将 proposal 升级到 `Voted`，支撑 $M_t$ |
| `BlockFinalized` | 可直接观测 | 当前仓库代码 | 同上 | 将 proposal 升级到 `Finalized`，支撑 $M_t$ |
| `BlockVerified` | 可直接观测 | 当前仓库代码 | 同上 | 将 finalized proposal 升级到 `Verified`，支撑 $M_t$ 与 `u_t` |
| `TxnReject` | 可直接观测 | 当前仓库代码 | 同上 | 执行失败 / reject 路径的过程观测，支撑 $R_t$ / `r_t(a)` |
| `TxnEvmOutput` | 可直接观测 | 当前仓库代码 | 同上 | tx-level output 过程观测，支撑 $R_t$ / `u_t` |
| `TxnCallFrame` | 可直接观测 | 当前仓库代码 | 同上 | 更细执行路径与调用栈观测，支撑 $R_t$ / $E_t$ |
| `AccountAccess` | 可直接观测 | 当前仓库代码 | 同上 | 账户访问结构，支撑 $E_t$ / `\kappa_t(a)` |
| `StorageAccess` | 可直接观测 | 当前仓库代码 | 同上 | slot 访问结构，支撑 $E_t$ / `\kappa_t(a)` |

## 事件重建层
除了单条事件外，当前仓库还提供了 block commit-state 重建逻辑。  
这使得我们可以从事件流进一步得到：

- `Proposed`
- `Voted`
- `Finalized`
- `Verified`
- `abandoned`

因此，Execution Events 不只是“更丰富的日志流”，而是一个能把 block-state 直接拉到研究对象层的重建入口。

## 与 RPC-only 的区别
RPC-only 的世界更像是：

$$
\text{“已经落在链上的 reduced-form 事实”}
$$

Execution Events 的世界更像是：

$$
\text{“kernel 正在展开时的过程性观测”}.
$$

## 与主线的关系
Execution Events 不是一个新模型。  
它的作用始终是：

- 让 unified kernel 的某些投影更清晰
- 让某些 reduced-form 近似更少依赖 proxy
- 把少数对象从弱代理升级为事件重建

主模型本身不因 Execution Events 而改变。

## 失败模式
最常见的失败方式有：

1. 把事件流只当作更多日志，而不回接到 unified kernel
2. 只做事件堆积，不做 projection 映射
3. 忽略 block commit-state 的可重建性
4. 把强观测层误写成新的理论主线

## 下一步
回到 [统一核下的估计程序](./34-estimation-program.md)，看强观测如何进入估计与校准。

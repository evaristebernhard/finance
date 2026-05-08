# Block States 与投机执行

## 目的
说明为什么 Monad 上的 MEV 问题不是普通单层确认问题，而必须从 block commit state 与 execution event 的分层状态出发。

## 证据分层速览
这页先回答三件事：

1. 当前仓库能直接核对什么  
   `BlockStart / BlockReject / BlockQC / BlockFinalized / BlockVerified` 这些 execution events，以及由它们重建出来的 `Proposed / Voted / Finalized / Verified`。
2. 哪些对象依赖外部资料  
   更完整的共识细节、leader 选择与网络视角仍依赖 `monad-bft` 或外部官方资料。
3. 哪些对象只是研究 latent  
   `p_t`、`u_t` 这类概率量属于 belief / projection，不是事件流里的直接字段。

| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| `BlockStart / BlockReject / BlockQC / BlockFinalized / BlockVerified` | 可直接观测 | 当前仓库代码 | `external/monad-official/monad/rust/crates/monad-exec-events/src/events/mod.rs` | event layer |
| `Proposed / Voted / Finalized / Verified` | 事件重建 | 当前仓库代码 | `external/monad-official/monad/rust/crates/monad-exec-events/src/block_builder/commit_state/mod.rs` | $M_t$ 的局部坐标 |
| `abandoned` 候选块 | 事件重建 | 当前仓库代码 | 同上 `CommitStateBlockUpdate.abandoned` | branch pruning 事实 |
| `p_t` | 研究latent | 建模假设 | 主模型页、参数页 | block / canonical projection |
| `u_t` | 研究latent | 建模假设 | 主模型页、参数页 | verification projection |

## 核心对象
候选块身份与提交态写成：

$$
B_t=(n,\mathrm{id}),
\qquad
S_t\in\{\mathrm{Proposed},\mathrm{Voted},\mathrm{Finalized},\mathrm{Verified},\dagger\}.
$$

这里需要先区分两层：

- 事件层：当前仓库的 execution event schema 会发出 `BlockStart / BlockReject / BlockQC / BlockFinalized / BlockVerified`
- 建模层：研究里把这些事件整合成候选块状态机，并把死亡分支记成 $\dagger$

## 先事件、后状态
对于当前工作区里的 execution 代码，更稳妥的起点不是概率，而是离散事件：

- `BlockStart`：某个候选块开始执行
- `BlockReject`：某个候选块被拒绝或未继续沿当前分支推进
- `BlockQC`：候选块升级到 `Voted`
- `BlockFinalized`：候选块升级到 `Finalized`
- `BlockVerified`：对应高度的 finalized proposal 被升级到 `Verified`

在 `CommitStateBlockBuilder` 的重建逻辑里：

- 执行完成的块先进入 `Proposed`
- 收到 `BlockQC` 后进入 `Voted`
- 收到 `BlockFinalized` 后进入 `Finalized`
- 收到 `BlockVerified` 后进入 `Verified`
- 同高度下未被 finalized 的其他 proposal 会进入 `abandoned`

因此，对同一高度 $n$，允许存在多个候选块：

$$
\mathcal B_n=\{b_1,b_2,\dots\}.
$$

每个候选块在建模层经历状态机

$$
\mathrm{Proposed}\to \mathrm{Voted}\to \mathrm{Finalized}\to \mathrm{Verified},
$$

并允许在中途死亡：

$$
\mathrm{Proposed}\to \dagger,\qquad
\mathrm{Voted}\to \dagger.
$$

这里的 $\dagger$ 不是 event schema 中的显式枚举，而是对 `BlockReject`、分支放弃和 finalized 时的 `abandoned` 结果做的研究层压缩记号。

## 再进入概率对象
在明确离散事件与重建状态之后，才更自然地导出两个概率对象：

$$
p_t=\Pr(B_t\text{ 最终 canonical}\mid \mathcal F_t^{\mathrm{obs}})
$$

和

$$
u_t=\Pr(\text{当前 execution output 最终被 verified}\mid \mathcal F_t^{\mathrm{obs}}).
$$

它们的地位是：

- `BlockQC / Finalized / Verified` 是当前仓库可观测或可重建的事实
- `p_t / u_t` 是研究者在部分观测条件下对这些事实做出的 belief / projection

因此，本页不再把 `p_t` 和 `u_t` 当作第一入口，而是把它们放回事件层之后。

## 直觉解释
在 Monad 上，“当前看到的块”并不是单一且确定的世界。  
你先看到的是一串事件和一个可重建的 commit state，而不是一个已经确定的 canonical 真相。

所以 searcher 面对的是一个**多层真相**：

- 事件层面：当前发生了什么
- 状态重建层面：块目前处于什么 commit state
- belief 层面：这条分支最终会不会成为 canonical、当前 output 会不会 survive 到 verified

## 与主线的关系
这篇文档提供的是 unified kernel 中 $M_t$ 的局部坐标与机制背景。  
其中：

- execution event 与 commit state 构成 $M_t$ 的可观测或可重建部分
- `p_t`、`u_t` 是从这些事实进一步诱导出来的 projection

因此，它服务于主线，但不再单独定义主线状态。

## 数据前提 / 识别边界
- Execution Events：可以直接提供 block-related events，并可重建 `Proposed / Voted / Finalized / Verified`
- RPC-only：`latest / safe / finalized` 只能当作极粗的运营代理，**不能**再写成对 `Proposed / Voted / Finalized` 的一一对应
- 外部资料：更完整的共识推进细节与 canonical 形成逻辑仍需参考外部共识仓库或官方资料

## 下一步
继续阅读 [Local Mempool 与 Leader-Path](./11-local-mempool-and-leader-path.md)。

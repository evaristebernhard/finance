# 弱观测后验推断：无节点阶段的数据策略

## 目的
本页把“无节点数据”从无奈兜底提升为一条正式研究路线。

它回答的问题不是：

$$
\text{如何把 RPC-only 写成强观测？}
$$

而是：

$$
\text{在没有原生 Execution Events 的情况下，如何用可得弱观测反演 } M_t,E_t,R_t \text{ 的后验分布？}
$$

因此，本页不替代 [Execution Events 强观测层](./33-execution-events-strong-layer.md)。  
它负责定义：

$$
\text{Observed facts}
\to
\text{Weak proxies}
\to
\text{Latent states}
\to
\text{Posterior summaries}
\to
\text{Bellman inputs}.
$$

## 当前判断
当前阶段同时承认两件事：

1. **有些数据是可以低成本拿到的。**  
   例如 RPC snapshot、Envio logs、receipts、Dune traces、Alchemy near-head signals。
2. **强过程状态仍然拿不到。**  
   例如完整的 `BlockQC / BlockFinalized / BlockVerified` 原生事件流、`AccountAccess / StorageAccess` 原生访问流、`TxnCallFrame / TxnEvmOutput` 原生执行过程。

这两件事不能相互覆盖：

- 不能因为部分数据可得，就把 weak proxy 写成 primitive truth。
- 也不能因为强观测缺失，就退回到“只能跑 RPC 骨架”的消极路线。

正确路线是：

$$
\text{可得事实}
\quad+\quad
\text{结构约束}
\quad+\quad
\text{后验推断}
\quad\Rightarrow\quad
\tilde b_t
$$

其中 $\tilde b_t$ 是 canonical belief $b_t$ 的 reduced-form posterior summary，而不是新的 primitive。

## 证据分层表
| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| RPC AMM snapshot | 可直接观测 | 当前仓库代码 + 外部 RPC | `crates/monad-mev-rpc` | 支撑 $G_t$ 的局部几何 |
| Envio / Dune / DEX logs | 可直接观测 | 外部 indexer / 链上日志 | Envio、Dune、DEX event logs | 支撑 $G_t$ 历史与 log co-occurrence proxy |
| receipts / block headers | 可直接观测 | RPC / indexer | tx receipt、block header | 支撑 $F_t$ 与 outcome fact |
| Alchemy near-head signals | RPC弱代理 | 外部 provider | `monadNewHeads / monadLogs` | $M_t$ 的 near-head proxy |
| trace-derived call / access proxy | RPC弱代理 | Dune traces / debug traces | trace call frame、touched contract proxy | $E_t/R_t$ 的弱代理 |
| 原生 `AccountAccess / StorageAccess` | 事件重建 | 当前仓库代码 + Execution Events | event ring / sidecar | $E_t$ 强观测，当前无节点阶段不可得 |
| 原生 block commit-state events | 事件重建 | 当前仓库代码 + Execution Events | `BlockQC / Finalized / Verified` | $M_t$ 强观测，当前无节点阶段不可得 |
| $p_t,u_t,q_t,r_t,\kappa_t$ | 研究latent | 建模假设 + 校准 | 本页、参数页、估计程序 | projection / posterior summary |

## 四层对象
### 1. Observed facts
Observed facts 是当前可较稳定取得的数据，不需要伪装成更强对象：

- RPC snapshot：`cpmm` reserves、`clmm` active-band 状态、block metadata。
- Envio logs / DEX events：swap、mint、burn、sync、transfer 等合约事件。
- receipts：success、gas used、effective gas price、tx hash、block inclusion。
- Dune traces / debug traces：call frame、revert、部分执行路径。
- Alchemy near-head signals：provider 视角下的 proposed / speculative logs / near-head block signals。

这些对象可以直接进入数据层，但进入模型时仍需标注来源与强度。

### 2. Weak proxies
Weak proxies 是从 observed facts 中构造的弱推断坐标：

- near-head block proxy：由 `monadNewHeads / monadLogs / newHeads / receipts continuity` 组合得到。
- trace-derived access proxy：由 traces、call frames、contract touch、same-tx path 得到。
- log co-occurrence conflict proxy：由同块、同池、同路径或同 router 日志共现得到。
- receipt outcome proxy：由 success、gas used、effective gas price、revert/fail trace 得到。
- opportunity disappearance proxy：由后续 pool state、外部价格与 route opportunity 消失速度得到。

这些 proxy 可以服务 posterior inference，但不能直接写成原生 Execution Events。

特别地：

- Envio logs 不得直接写成 `AccessObservation`。
- trace-derived access 若进入后续实现，应显式降级为 proxy artifact。
- near-head provider signal 不得直接写成原生 `BlockVerified`。

### 3. Latent states
无节点阶段的关键 latent state 是：

$$
M_t,\qquad E_t,\qquad R_t.
$$

这里：

- $M_t$：commit / verification / visible execution state 的不可完整观测部分。
- $E_t$：账户、slot、call-path、热点与冲突结构的不可完整观测部分。
- $R_t$：reserve / admissibility / survival 过程的不可完整观测部分。

这些对象仍是 primitive 的组成部分，但在无节点阶段不能被直接完整观测，只能通过 posterior belief 进入策略层。

### 4. Posterior summaries
策略层不直接消费完整 posterior。它需要 reduced-form summary，例如：

$$
\tilde p_t,\quad \tilde u_t,\quad \tilde q_t(a),\quad \tilde r_t(a),\quad \tilde \kappa_t(a).
$$

这里加上 $\tilde{\cdot}$ 是为了提醒：它们是后验 summary，不是机制真值。

进入 Bellman 时，它们仍然必须保持：

- role：projection
- strength：RPC 弱代理、latent 或 calibration target
- evidence：observed facts + modeling assumptions

## $M_t$：near-head posterior state machine
无节点阶段的 $M_t$ 不应写成原生 commit-state 重建，而应写成 provider-assisted posterior。

建议状态集合为：

```text
unseen
  -> proposed_proxy
  -> voted_proxy
  -> finalized_proxy
  -> verified_proxy
  -> dropped
```

### 输入
- Alchemy `monadNewHeads`
- Alchemy `monadLogs`
- 普通 `newHeads`
- receipts / logs consistency
- block continuity
- provider cross-check

### 结构约束
若外部官方资料给出普通阶段推进的 lag 关系，可以作为 transition prior；但这个 prior 不能被写成观测事实。

### 输出
输出不是单一 phase，而是：

$$
\Pr(M_t=\text{phase}\mid O_{1:t})
$$

以及低维 summary：

- phase confidence
- drop risk
- visible execution confidence
- receipt/log consistency score

### 映射到 Bellman
由 $M_t$ posterior 派生：

$$
\tilde p_t=g_p(\tilde b_t),
\qquad
\tilde u_t=g_u(\tilde b_t).
$$

这些仍是 projection。

## $E_t$：冲突图 posterior
无节点阶段的 $E_t$ 不应退化成“有没有日志”。  
更合适的结构是冲突图：

$$
\mathcal G_t^{\mathrm{conflict}}
=
(\mathcal V_t,\mathcal E_t).
$$

### 节点
可包括：

- pool
- router
- token
- tx
- address proxy
- trace call target
- route candidate

### 边
可由以下弱观测生成：

- 同块日志共现
- 同 route / pool 重叠
- trace call target 重叠
- gas spike 共振
- same-block tx cluster
- opportunity decay 共振

### 输出
输出 posterior summary：

- hotspot score
- overlap score
- contention density
- route crowding score
- expected friction loss proxy

### 映射到 Bellman
由 $E_t$ posterior 派生：

$$
\tilde\kappa_t(a)
=
g_\kappa(\tilde b_t,a).
$$

它不能被写成直接观测的 $\kappa_t(a)$。

## $R_t$：survival hazard posterior
无节点阶段的 $R_t$ 应从结果与路径条件反推。

### 输入
- receipts success / failure
- gas used
- effective gas price
- route size
- execution delay
- revert/fail traces
- opportunity disappearance
- same-path congestion

### 模型
建议先用 hazard 视角：

$$
\lambda_t(a)
=
\Pr(\mathrm{non\mbox{-}survival}\mid O_{1:t},a)
$$

或：

$$
\tilde r_t(a)
=
\Pr(\mathrm{survive}\mid O_{1:t},a).
$$

### 输出
- survival probability
- failure hazard
- opportunity decay score
- gas / reserve stress proxy

### 映射到 Bellman
由 $R_t$ posterior 派生：

$$
\tilde r_t(a)=g_r(\tilde b_t,a).
$$

## 联合后验优先，而不是逐项硬估
本页不建议先分别硬估：

$$
p_t,\ u_t,\ q_t,\ r_t,\ \kappa_t.
$$

更合理的方式是先构造联合对象：

$$
\Pr(y_t,\mathrm{included},\mathrm{survive},\mathrm{conflict},\mathrm{delay}
\mid O_{1:t},a_t)
$$

再从联合后验中派生 reduced-form summary。

这样做的原因是：

- $q_t$ 与 $M_t,C_t$ 耦合
- $r_t$ 与 $R_t,E_t$ 耦合
- $\kappa_t$ 与 $E_t,C_t$ 耦合
- $p_t,u_t$ 与 $M_t$ 耦合

逐项拟合容易把同一类不确定性重复计算或错误归因。

## 小样本强观测校准
如果未来短期拿到 Execution Events sidecar 数据，本页路线不应被推翻，而应被校准。

做法是：

$$
\text{small strong-labeled sample}
\to
\text{teacher / calibration target}
\to
\text{weak-data posterior model}
$$

强观测样本用于：

- 校准 near-head proxy 的 phase transition
- 校准 log / trace proxy 与真实 access overlap 的偏差
- 校准 survival hazard 与真实 reject / output event 的关系

这比长期依赖重节点更现实，也更符合无节点阶段的数据策略。

## 验证路径
弱观测后验推断必须接受 out-of-sample 检验。

### 1. $M_t$ proxy 验证
检查：

- near-head proxy 是否预测后续 receipt/log consistency
- `dropped` 风险是否对应后续 block / receipt 不一致
- phase confidence 是否解释策略等待价值

### 2. $E_t$ conflict proxy 验证
检查：

- hotspot score 是否解释 failed tx、gas anomaly、replay loss
- route crowding 是否解释 opportunity decay
- trace-derived overlap 是否比 log co-occurrence 更有预测力

### 3. $R_t$ hazard 验证
检查：

- survival probability 是否解释 replay / eval 中的 non-survival
- hazard score 是否随 gas stress、route size、delay 单调变化
- 该模型是否在不同 pool family / regime 中保持方向一致

## 失败标准
以下情况必须触发降级：

1. 某个 proxy 对 out-of-sample 结果没有解释力。  
   它应降级为 exploratory feature，不进入 Bellman 主输入。
2. 某个 provider signal 与落链事实频繁冲突。  
   它应从 state transition prior 降级为弱提示。
3. 某个 log / trace proxy 被误用为原生 access event。  
   必须从 `AccessObservation` 语义中移除，转入 proxy artifact。
4. posterior summary 无法稳定改善 act / wait / abort 边界。  
   它不应替代更简单的 baseline。

## 与现有 Rust 接口的关系
当前不修改 `NormalizedExecEvent` schema。

现有三类事件继续表示：

- `CommitStateUpdate`
- `AccessObservation`
- `TxnOutcomeObservation`

它们只能承接已经被明确规范化的事件输入。  
无节点弱观测 posterior 不应直接塞进这些类型。

若未来进入实现阶段，应优先新增平行 artifact，例如：

```text
posterior-state.json
proxy-observations.jsonl
belief-summary.json
```

而不是扩充或重写现有 normalized event schema。

## 与主线的关系
本页是 [观测、belief 与 reduced-form 压缩](../20-core-model/21-state-space-and-observation.md) 在无节点数据条件下的经验落点。

它服务：

- [参数建模总页](./30-parameter-map.md)
- [数据来源与校准边界](./31-data-sources-and-availability.md)
- [弱观测逆问题、识别与鲁棒 Bellman](./39-weak-observation-inverse-problem-and-robust-bellman.md)
- [统一核下的估计程序](./34-estimation-program.md)
- [结构仿真伴随层](./35-structural-simulation-layer.md)
- [近头实时数据 API 提供清单](./38-near-head-realtime-api-checklist.md)

它不替代：

- unified kernel 主模型
- Execution Events 强观测层
- Bellman 决策层

## 下一步
若需要先把无节点阶段严格写成问题定义、识别边界与鲁棒 Bellman，请先读 [弱观测逆问题、识别与鲁棒 Bellman](./39-weak-observation-inverse-problem-and-robust-bellman.md)。  
若当前阶段需要继续准备实现输入，请再读 [近头实时数据 API 提供清单](./38-near-head-realtime-api-checklist.md)。  
然后继续读 [统一核下的估计程序](./34-estimation-program.md)，把本页的 posterior objects 接入估计顺序。若需要对比强观测上限，回到 [Execution Events 强观测层](./33-execution-events-strong-layer.md)。

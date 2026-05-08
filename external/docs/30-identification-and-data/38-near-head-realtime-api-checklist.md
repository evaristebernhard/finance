# 近头实时数据 API 提供清单

## 目的
本页不是新的数据模型页，而是一份面向实现与协作的 API 交付清单。

它回答的问题是：

$$
\text{若当前阶段不跑 full node，}
\text{为了把现有仓库可消化的数据面喂满，最少需要哪些 API 访问？}
$$

这里的关键约束是：

- 当前仓库优先服务 `RPC snapshot + normalized events`
- 当前阶段优先服务近头实时
- 当前阶段不要求节点侧原生 Execution Events
- 当前阶段不重写现有 Rust schema

因此，本页的目标不是索要“所有能想到的数据”，而是固定一份：

$$
\text{最小但足够的 API handover contract}.
$$

## 当前仓库真正可消化的数据面
结合当前代码，仓库现在直接能吃的是两类输入：

### 1. RPC snapshot
当前 `crates/monad-mev-rpc` 实际依赖的方法只有：

- `eth_chainId`
- `eth_blockNumber`
- `eth_call`

并通过 `eth_call` 读取：

- `token0()`
- `token1()`
- `decimals()`
- `getReserves()`
- `fee()`
- `liquidity()`
- `slot0()`

这足以支撑：

- `cpmm` snapshot
- `clmm` snapshot

### 2. normalized execution events
当前 `crates/monad-mev-observation` 只接受三类规范化事件：

- `CommitStateUpdate`
- `AccessObservation`
- `TxnOutcomeObservation`

其中：

- `CommitStateUpdate` 只需要 `phase` 与 `block_hash`
- `AccessObservation` 只需要 `tx_hash`、`account`、`storage_slots`
- `TxnOutcomeObservation` 只需要 `tx_hash`、`success`、`gas_used`、`effective_gas_price`

这意味着：

- 近头 provider 信号可以用于 `M_t` proxy 研究
- receipts 可以直接服务 `TxnOutcomeObservation`
- traces / indexer 数据可服务 `E_t/R_t` weak proxy
- 但它们不应被直接伪装成原生 Execution Events

## 必需 API
### A. 标准 RPC：必须有 1 组 HTTPS endpoint
这一组是整个数据面最底层的必需访问。

#### 必需方法
- `eth_chainId`
- `eth_blockNumber`
- `eth_call`
- `eth_getLogs`
- `eth_getTransactionReceipt`
- `eth_getBlockByNumber` 或 `eth_getBlockByHash`

#### 强烈推荐方法
- `eth_getBlockReceipts`

#### 用途
- `eth_call`：供当前 `AmmSnapshotEnvelope` 构造 `cpmm/clmm` snapshot。
- `eth_getLogs`：供 pool logs、DEX events、落链事实校验与历史几何重建。
- `eth_getTransactionReceipt` / `eth_getBlockReceipts`：供 `TxnOutcomeObservation`、receipt consistency、gas outcome 校验。
- `eth_getBlockByNumber` / `eth_getBlockByHash`：供 block metadata、continuity 与头部校验。

#### 最低 handover
实现方至少需要：

- 1 个 RPC HTTPS URL
- 认证方式（API key、header、basic auth 等）
- 速率限制说明
- 是否支持 `eth_getBlockReceipts`

### B. Alchemy WebSocket：必须有 1 组 WSS endpoint
这一组服务近头实时，主要面向 $M_t$ proxy 而不是原生强观测。

#### 必需订阅
- `monadNewHeads`
- `monadLogs`

#### 可选保留
- `newHeads`
- `logs`

#### 用途
- 用 `monadNewHeads` 构造 near-head block proxy state machine。
- 用 `monadLogs` 补 speculative / near-head logs 视角。
- 用普通 `newHeads/logs` 做 provider cross-check。

#### 约束
Alchemy near-head 信号的语义应固定为：

- provider-assisted proxy
- 不直接写成 `BlockQC / BlockFinalized / BlockVerified`
- phase 命名必须带 `_proxy`

#### 最低 handover
实现方至少需要：

- 1 个 WSS URL
- 认证方式
- 已开通 `monadNewHeads / monadLogs`
- 订阅速率、断线重连与限制说明

### C. traces / indexer API：必须有 1 组可导出接口
这一组服务 $E_t/R_t$ 的 weak proxy 与历史/准实时补充。

#### 最低能力
- 按 `tx` 查询 traces 或 call frames
- 按 `block` 查询 traces 或 call frames
- 按 `address` 或目标 pool/filter 导出事件流

#### 推荐能力
- tx-level call traces
- revert / fail traces
- touched contracts / call targets
- pool swap / mint / burn / sync / transfer event export

#### 用途
- 研究级 `E_t/R_t` weak proxy
- log co-occurrence
- trace-derived access proxy
- survival hazard proxy
- `G_t` 历史几何与 route context 补全

#### 最低 handover
实现方至少需要：

- 请求基地址
- 认证方式
- trace 查询接口说明
- DEX / pool event 导出接口说明
- 速率限制
- 分页方式
- 输出格式（JSON、CSV、Parquet 等）
- 过滤能力（按 tx / block / address / topic）

## 交付给实现方的固定访问项
后续若由你统一收集并交给实现方，建议固定为三组交付物：

1. **标准 RPC**
   - 1 个 HTTPS URL
   - API key / header / auth 方式
   - 是否支持 `eth_getBlockReceipts`

2. **Alchemy near-head**
   - 1 个 WSS URL
   - 已开通 `monadNewHeads / monadLogs`
   - reconnect / rate-limit 说明

3. **traces / indexer**
   - 1 份 API 文档或凭证说明
   - trace 导出入口
   - DEX / pool event 导出入口
   - 速率、延迟、分页、格式说明

若 traces 不是实时 API，而是准实时导出，也可接受；但必须补齐：

- 延迟
- 分页方式
- 导出格式
- 地址 / tx / block 过滤能力

## 对当前仓库的映射
### 当前仓库可直接消化
#### RPC snapshot
- `eth_call + eth_chainId + eth_blockNumber`
- 直接进入 `snapshot` 命令与 `AmmSnapshotEnvelope`
- 支撑 `cpmm/clmm` 的 `G_t` 局部几何

#### outcome 事实
- receipts / gas / success
- 可直接映射 `TxnOutcomeObservation`

### 当前仓库可作为研究输入，但不应直接混写
#### near-head proxy
- `monadNewHeads / monadLogs`
- 服务 `M_t` proxy state machine 与 posterior inference
- 当前不应直接落成原生 `CommitStateUpdate` 真值

#### traces / call frames / touched contracts
- 服务 `E_t/R_t` proxy research
- 当前不应直接落成原生 `AccessObservation`

#### Envio / DEX logs
- 服务 `G_t` 历史几何、route context、log co-occurrence proxy
- 当前不应把普通 logs 误写成原生 account/storage access

## 严格禁止
以下混写必须明确禁止：

1. 把普通 logs 直接写成 `AccessObservation`
2. 把 Alchemy near-head phase 直接写成原生 `BlockVerified`
3. 把 traces/indexer proxy 伪装成 Execution Events 真值
4. 把 provider-specific speculative signal 写成协议直接给定

## 接入级检查
### 标准 RPC
必须成功返回：

- `eth_chainId`
- `eth_blockNumber`
- `eth_call`

推荐继续验证：

- `eth_getLogs`
- `eth_getTransactionReceipt`
- `eth_getBlockByNumber`
- `eth_getBlockReceipts`

### Alchemy WSS
必须验证：

- 能订阅 `monadNewHeads`
- 能订阅 `monadLogs`
- 断线后是否支持稳定重连

### traces / indexer
必须验证：

- 能按目标 tx 返回 trace
- 能按目标 pool 地址返回 event export
- 输出能被稳定分页与重复下载

## 仓库对齐检查
### snapshot 检查
标准 RPC 应足以生成当前：

- `cpmm` snapshot
- `clmm` snapshot

### outcome 检查
receipt 字段应足以映射：

```text
TxnOutcomeObservation {
  tx_hash,
  success,
  gas_used,
  effective_gas_price
}
```

### near-head 检查
Alchemy 信号应足以支持：

- `M_t` 的 near-head proxy research
- `CommitStateUpdate` 的 proxy phase 研究

但不得污染现有 schema 的真值语义。

## 边界检查
任何 traces / logs / near-head provider signal 在进入研究流程时，都应先被标记为：

- observed facts，或
- weak proxies

而不是：

- 原生强观测
- primitive truth
- 已完成的 commit-state reconstruction

## 当前阶段的最小优先级
若某项 API 一时拿不到，优先级下降顺序固定为：

1. 先牺牲 `eth_getBlockReceipts`
2. 再牺牲 traces 的实时性
3. 最后才牺牲 Alchemy near-head

原因是：

- `eth_getTransactionReceipt` 可以部分兜底 `eth_getBlockReceipts`
- traces 可先用准实时 / 批处理导出支撑研究
- Alchemy near-head 对 $M_t$ proxy 是当前最关键的实时信号

## 与主线的关系
本页是 [弱观测后验推断：无节点阶段的数据策略](./37-weak-observation-posterior-inference.md) 的实施清单页。  
它不重新定义数据模型，只把：

- 当前仓库真正可消化的数据面
- 近头实时优先的 API 需求
- handover 时必须说清的访问项

固定成一份可执行的输入合同。

## 下一步
若当前阶段先做无节点 posterior inference，请先按本页准备 API 访问，再回到 [弱观测后验推断](./37-weak-observation-posterior-inference.md) 组织 observed facts、weak proxies 与 posterior summaries。若以后进入更强观测层，再回到 [Execution Events 强观测层](./33-execution-events-strong-layer.md)。

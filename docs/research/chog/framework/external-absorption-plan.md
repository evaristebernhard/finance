# CHOG external 框架吸收计划

## 1. 目的

本文是 CHOG 后续链上研究的主入口。目标不是立刻修改采集器或模型代码，而是先把 `external/docs` 里的统一核、弱观测、posterior inference 与 Bellman 压缩框架，落到 CHOG 当前已经有的数据面和下一步工程路线里。

本阶段只做三件事：

1. 明确哪些 CHOG 数据是 observed facts，哪些只能作为 weak proxy。
2. 固定 `G_t / M_t / E_t / R_t / F_t` 到 CHOG v1 数据对象的边界。
3. 为后续实现 checkpoint、定时快照、`proxy-observations.jsonl`、receipt/gas outcome、router/searcher 标签和 walk-forward 验证统一命名。

外部理论来源保持在 `external/docs` 下，CHOG-specific 结论只写在 `docs/` 下，避免把通用研究框架污染成某一个 token 的分析笔记。

## 2. 从 external 吸收什么

### 2.1 统一状态边界

`external/docs/20-core-model/20-monad-mev-main-model.md` 把研究层状态写成：

```text
s_t = (G_t, M_t, C_t, R_t, E_t, F_t)
```

CHOG v1 先吸收其中五类对象：

| 对象 | external 角色 | CHOG v1 使用方式 | CHOG v1 强度 |
| --- | --- | --- | --- |
| `G_t` | AMM 图、池状态、外部价格锚与机会几何来源 | 主池 swap 几何、价格、流动性、路径上下文 | observed facts + proxy summary |
| `M_t` | Monad 提交态、leader window、execution-stage 状态 | receipt/log continuity、near-head 或落链后状态一致性 | weak proxy / posterior summary |
| `E_t` | 访问结构、热点、冲突与重执行环境 | 同块、同 tx、同池、同 router 的冲突图 proxy | weak proxy / posterior summary |
| `R_t` | reserve / delegation / authority / survival 相关状态 | receipt outcome、revert、gas used、admissibility 结果 | weak proxy / posterior summary |
| `F_t` | base fee 状态 | block header、receipt、effective gas price | observed fact |

`C_t` 在 CHOG v1 中不单独建模为强对象。竞争流、传播和对手行为先通过 router/searcher 标签、pending/near-head provider 数据以及 conflict proxy 进入 `q_t` 和 `kappa_t` 的 proxy 或 posterior summary。

### 2.2 Observed facts -> weak proxies -> posterior summaries

`external/docs/30-identification-and-data/37-weak-observation-posterior-inference.md` 的核心路线是：

```text
Observed facts
-> Weak proxies
-> Latent states
-> Posterior summaries
-> Bellman inputs
```

CHOG 文档后续统一采用这条证据链。具体含义：

- observed facts：价格点、DexScreener 快照字段、已落链 Transfer logs、已落链主池 Swap logs、receipt/header 字段。
- weak proxy：由 observed facts 派生的卖压、冲击、机会衰减、冲突共现、router/searcher 标签、gas/outcome 指标。
- latent states：`M_t / E_t / R_t` 的不可完整观测部分。
- posterior summary：进入策略层的低维 summary，例如 `p_t / u_t / q_t / r_t / kappa_t` 的 proxy posterior。

### 2.3 Projection 不能写成 primitive truth

`q_t / r_t / kappa_t / u_t / p_t` 在 CHOG v1 文档里一律只能写成 proxy 或 posterior summary，不能写成 primitive truth。

允许的写法：

```text
q_t proxy
r_t proxy
kappa_t proxy
u_t posterior summary
p_t posterior summary
```

禁止的写法：

```text
q_t truth (禁止；只能写成 proxy 或 posterior summary)
r_t observed (禁止；只能写成 proxy 或 posterior summary)
kappa_t directly measured (禁止；只能写成 proxy 或 posterior summary)
u_t protocol field (禁止；只能写成 proxy 或 posterior summary)
p_t chain fact (禁止；只能写成 proxy 或 posterior summary)
```

### 2.4 Bellman 压缩只作为后续接口

`external/docs/20-core-model/25-minimal-bellman-system.md` 给出的最小 Bellman 系统是压缩层，不是 CHOG 当前数据本身。CHOG v1 只需要先准备可回指的数据对象：

| Bellman 输入 | CHOG v1 对应 | 当前定位 |
| --- | --- | --- |
| `theta_pool` | 主池 tick、sqrtPriceX96、amount0/amount1、liquidity proxy | `G_t` proxy summary |
| `theta_route` | router、pair、quote token、路径标签 | `G_t / C_t` proxy summary |
| `MainPoolImpact` | `(buy_chog - sell_chog) * price_usd / liquidity_usd_t` | `G_t` impact proxy |
| opportunity decay | 冲击后池价、外部价格和收益的回归速度 | `G_t` opportunity proxy |
| gas/outcome | receipt success、gas used、effective gas price、revert | `F_t` fact + `R_t` proxy |
| conflict graph | 同块/同 tx/同池/同 router 共现 | `E_t / C_t` weak proxy |

## 3. CHOG 当前数据映射

### 3.1 当前 observed facts

| 数据 | 当前文件 | evidence | role | strength |
| --- | --- | --- | --- | --- |
| 小时价格 | `date/chog_prices_476h_1h.csv` | DeFiLlama chart API，部分 forward fill | 外部价格锚、收益标签 | observed fact with fill flags |
| DexScreener 池子快照 | `date/chog_dex_pairs_snapshot.csv` | DexScreener token pairs API | 当前池子、流动性、成交量、buy/sell count | observed snapshot |
| ERC-20 Transfer logs | `date/chog_transfer_logs_20k_blocks.csv`、`date/chog_transfer_logs_100k_blocks.csv` | Monad RPC `eth_getLogs` | token 流转、池子净流入 proxy | observed logs; swap direction weak proxy |
| 主池 v3 Swap logs | `date/chog_main_pool_swaps_20k_blocks.csv`、`date/chog_main_pool_swaps_100k_blocks.csv` | Monad RPC `eth_getLogs` on main pool | 主池方向、数量、局部价格几何 | observed logs; strongest current `G_t` input |
| 主池小时汇总 | `date/chog_main_pool_swaps_hourly_100k_blocks.csv` | Swap logs 聚合 | `MainPoolImpact`、volume、短期冲击 | proxy summary |
| 链上小时特征 | `date/chog_flow_features_100k_blocks.csv` | price + swap + transfer join | walk-forward 特征表 | derived proxy table |

### 3.2 当前事实边界

已可比较稳地说：

1. CHOG 流动性和成交高度集中在 nad-fun 的 CHOG/MON 主池。
2. DexScreener 的 buy/sell count 是笔数，不是资金流。
3. Transfer logs 能描述 CHOG token 流转，但不能直接等同 swap。
4. 主池 Swap logs 当前是识别 CHOG 买卖方向和规模最强的数据面。
5. 主池净买入能解释同小时价格冲击，但未来 1-3h 的方向只能作为小样本待验证 proxy。

仍不能说：

1. buy/sell count 代表真实资金净流。
2. Transfer 到池子就是完整 swap 成交量。
3. `q_t / r_t / kappa_t / u_t / p_t` 已经被 CHOG 当前数据直接观测；这些对象只能作为 proxy 或 posterior summary。
4. router/searcher、冲突图、gas outcome 已经足够支持策略层。

### 3.3 CHOG v1 对象命名

后续文档和实现优先使用这些对象名：

| 对象名 | 定义 | 回指 |
| --- | --- | --- |
| `theta_pool` | 主池局部几何：tick、sqrtPriceX96、amount0/amount1、liquidity proxy | `G_t` proxy summary |
| `MainPoolImpact_t` | `(buy_chog_t - sell_chog_t) * price_usd_t / liquidity_usd_t` | `G_t` impact proxy |
| `MainPoolSellPressure_t` | `(sell_chog_t - buy_chog_t) * price_usd_t / liquidity_usd_t` | `G_t` impact proxy |
| `liquidity_usd_t` | 定时 DexScreener snapshot 或池状态派生的流动性序列 | `G_t` observed/proxy summary |
| `ReceiptOutcome_t` | success、gas used、effective gas price、revert/fail trace | `F_t` fact + `R_t` proxy |
| `RouterSearcherTag` | sender/recipient/router/searcher/ordinary wallet 标签 | `C_t / E_t` proxy |
| `ConflictGraphProxy_t` | 同块、同 tx、同池、同 router 的共现图 | `E_t / C_t` weak proxy |
| `OpportunityDecay_t` | 主池冲击后机会或价格偏离的消失速度 | `G_t` opportunity proxy |

## 4. V1 文档先行路线

### 阶段 1：固定主池 `G_t` 几何

主池 Swap logs 应升级为 `theta_pool / MainPoolImpact / opportunity decay` 数据面，而不只是 buy/sell 汇总。

最小字段：

```text
block_number
block_timestamp
tx_hash
log_index
sender
recipient
amount0
amount1
sqrtPriceX96
liquidity
tick
buy_chog
sell_chog
price_before_proxy
price_after_proxy
impact_proxy
```

### 阶段 2：把流动性从快照变成时间序列

`main_pool_liquidity_usd` 不能长期使用单次快照。需要定时 DexScreener snapshot，形成：

```text
liquidity_usd_t
volume_usd_t
h1_buy_count_t
h1_sell_count_t
pair_share_t
```

这些字段是 observed snapshot time series，但进入模型时仍是 `G_t` 的 proxy summary。

### 阶段 3：统一 proxy observation artifact

新增 `proxy-observations.jsonl` 草案 schema，用来承接弱观测：

```json
{
  "token": "CHOG",
  "chain": "monad",
  "time": "2026-05-07T00:00:00Z",
  "object": "MainPoolImpact_t",
  "value": 0.0123,
  "evidence": ["main_pool_swap_logs", "dexscreener_snapshot"],
  "role": "G_t impact proxy",
  "strength": "observed facts -> proxy summary",
  "notes": "not primitive truth"
}
```

### 阶段 4：补 receipt/gas outcome

从 receipt/header 获取：

```text
status
gas_used
effective_gas_price
block_base_fee
tx_type
max_fee_per_gas
max_priority_fee_per_gas
```

其中 base fee 和 receipt 字段是 `F_t` / outcome fact；它们对 `R_t` 的 survival/admissibility 只能形成 proxy 或 posterior summary。

### 阶段 5：补 router/searcher 标签

对 swap `sender/recipient`、transfer `from/to`、同 tx 多日志路径和大额地址做标签：

```text
main_pool
known_pair
router
searcher_proxy
ordinary_wallet_proxy
lp_or_mint_burn_proxy
unknown
```

这些标签服务 `theta_route`、`ConflictGraphProxy_t` 和 `kappa_t` proxy，不是身份真值。

### 阶段 6：walk-forward 验证

验证对象先限制为：

```text
MainPoolImpact_t
main_chog_volume_t
ConflictGraphProxy_t
liquidity_usd_t
ReceiptOutcome_t
```

验证方式：

```text
feature_t -> future_return_{t,h}
h in {1h, 2h, 3h, 6h, 24h}
walk-forward split
```

只有经过 walk-forward 仍稳定的对象，才允许进入更正式的 posterior summary 或 Bellman 输入讨论。

## 5. 后续实现任务清单

按顺序执行：

1. 给 `v3_swap_sample` 做 checkpoint/resume。
2. 定时化 DexScreener snapshot，形成 `liquidity_usd_t`。
3. 生成 `proxy-observations.jsonl` 草案 schema。
4. 加 receipt/gas outcome 数据面。
5. 做 sender/recipient 的 router/searcher 标签。
6. 用 walk-forward 验证 MainPoolImpact、volume、conflict proxy。

## 6. 边界与失败模式

明确禁止：

1. 把 buy/sell count 当资金流。
2. 把 transfer 当 swap。
3. 把 `q_t / r_t / kappa_t / u_t / p_t` 当真值；这些对象只能写成 proxy 或 posterior summary。
4. 把 RPC-only 的 near-head 或 pending 行为当协议保证。
5. 把 router/searcher 标签当身份真值。
6. 在没有 checkpoint/resume 前继续扩大公共 RPC 扫描窗口并覆盖旧输出。
7. 在没有 `liquidity_usd_t` 前把单次 DexScreener 流动性快照当全样本分母。

常见失败模式：

1. 同小时解释力被误读成未来预测力。
2. 小样本 memecoin 跳跃被过拟合成稳定因子。
3. 多跳路由导致 Transfer volume 被重复计算。
4. 大额买单冲击和后续回撤被混成同一个趋势信号。
5. 冲突、gas、receipt outcome 缺失时，过早讨论 `q_t / r_t / kappa_t / u_t / p_t` 的数值；数值化前必须先有 proxy evidence 或 posterior summary 定义。

本计划的原则是：先把 observed facts、proxy、posterior summary 的边界写清楚，再实现采集和验证。

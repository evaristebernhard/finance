# CHOG 数据清单

当前 CHOG 文档使用的核心数据已扩展为: 价格序列、DEX 池子快照、Monad RPC transfer logs、主池 v3 Swap logs、全池 swap logs、CHOG 事件块 headers、tx receipts/gas、memecoin 策略特征。

计划主入口: [CHOG external 框架吸收计划](../research/chog/framework/external-absorption-plan.md)。

运行手册: [CHOG v1 30 天 Backfill Runbook](../runbooks/chog-v1-backfill.md)。

当前默认采集路径: [CHOG Memecoin 策略优先采集路径](../runbooks/chog-memecoin-collection.md)。

## 文件

| 文件 | 内容 | 行数 | evidence | role | strength |
| --- | --- | ---: | --- | --- | --- |
| `date/chog_prices_476h_1h.csv` | DeFiLlama 小时价格，约 19.8 天 | 477 | DeFiLlama chart API，含 `fill_method` | 外部价格锚、收益标签 | observed fact with fill flags |
| `date/chog_dex_pairs_snapshot.csv` | DexScreener 当前 CHOG 交易池快照 | 11 | DexScreener token pairs API | 当前池子、流动性、成交量、buy/sell count | observed snapshot |
| `date/chog_collection_runs.csv` | CHOG v1 采集运行清单 | 仅新增运行追加 | collector 本地运行记录 | checkpoint/resume 审计 | operational metadata |
| `date/chog_transfer_logs_recent.csv` | Monad 最近 5,000 block 的 CHOG Transfer logs | 33 | Monad RPC `eth_getLogs` | token 流转、池子净流入 proxy | observed logs; swap direction weak proxy |
| `date/chog_transfer_logs_20k_blocks.csv` | Monad 最近 20,000 block 的 CHOG Transfer logs | 253 | Monad RPC `eth_getLogs` | token 流转、池子净流入 proxy | observed logs; swap direction weak proxy |
| `date/chog_main_pool_swaps_20k_blocks.csv` | 主池 Uniswap V3-style Swap logs | 52 | Monad RPC `eth_getLogs` on main pool | 主池方向、数量、局部价格几何 | observed logs; strongest current `G_t` input |
| `date/chog_main_pool_swaps_100k_blocks.csv` | 更长窗口主池 Swap logs | 172 | Monad RPC `eth_getLogs` on main pool | `theta_pool`、`MainPoolImpact`、volume | observed logs; `G_t` proxy summary |
| `date/chog_main_pool_swaps_hourly_100k_blocks.csv` | 主池 Swap 小时汇总 | 13 | Swap logs 聚合 | 小时冲击、volume、sell pressure | derived proxy table |
| `date/chog_flow_features_100k_blocks.csv` | 价格、swap、transfer 合并小时特征 | 13 | price + swap + transfer join | walk-forward 候选特征 | derived proxy table |

## 数据源

### DeFiLlama

用于价格历史:

```text
https://coins.llama.fi/chart/monad:0x350035555e10d9afaf1566aaebfced5ba6c27777
```

限制:

1. 单次最多 500 个 data points。
2. 小币种价格点是稀疏的，不保证每小时都有原始观测。
3. 当前代码会映射到严格小时网格，并用 `fill_method` 标记填充方式。

### DexScreener

用于当前池子快照:

```text
https://api.dexscreener.com/token-pairs/v1/monad/0x350035555e10d9afaf1566aaebfced5ba6c27777
```

可用字段:

1. h1/h6/h24 buy/sell count。
2. h1/h6/h24 volume。
3. liquidity、FDV、market cap。
4. price change。
5. pair address、DEX、quote token。

限制:

1. 这是快照，不是历史逐小时序列。
2. buy/sell 是笔数，不是方向成交量。
3. 不包含每笔 swap 的完整路径。

证据边界:

```text
DexScreener snapshot 是 observed snapshot；
h1/h6/h24 buy/sell count 只能作为活跃度或方向弱线索，
不能当作资金流真值。
```

### Monad RPC

RPC:

```text
https://rpc.monad.xyz
```

已验证:

```text
eth_chainId = 0x8f
```

用于抓取 CHOG ERC-20 Transfer logs:

```text
eth_getLogs
address = 0x350035555e10d9afaf1566aaebfced5ba6c27777
topic0 = Transfer(address,address,uint256)
```

用于抓取主池 v3 Swap logs:

```text
eth_getLogs
address = 0x116e7D070f1888B81E1E0324F56d6746B2D7d8f1
topic0 = Swap(address,address,int256,int256,uint160,uint128,int24)
```

限制:

1. 公共 RPC 的 `eth_getLogs` 单次范围需要实测；正式 backfill runbook 当前使用公共 RPC 池和 500-block chunk。
2. 长窗口必须分页；当前采集器按 `--log-range-blocks` 写入并在每个成功 chunk 后更新 checkpoint。
3. Transfer logs 不是 swap logs，需要结合池子地址推断买卖方向。

证据边界:

```text
Transfer logs 是 observed logs；
transfer-to-pool / transfer-from-pool 只能形成 swap direction weak proxy。
```

主池 Swap logs 是当前最强的 `G_t` observed input，但聚合后的 `MainPoolImpact`、`MainPoolSellPressure` 和 `OpportunityDecay` 仍是 proxy summary。

### CHOG v1 采集底座

当前默认底座是 memecoin 策略优先路径: logs、事件块 headers、CHOG 池交易 receipts、event/hourly features。router/searcher 标签、DexScreener 时间序列和更严格 walk-forward 验证尚未纳入本轮数据证据。

两个 RPC log 采集器共享以下语义:

1. `--from-block` 优先级最高；显式传入时不依赖 checkpoint 起点。
2. `--to-block` 未传时，使用运行开始时的 latest block。
3. `--resume` 且 checkpoint 存在时，从 `last_completed_block + 1` 继续；checkpoint 不存在时退回 recent `--blocks` 窗口。
4. `--append` 追加 CSV，并用 `(block_number, transaction_hash, log_index)` 去重；不传 `--append` 时保留覆盖写兼容行为。
5. 默认 checkpoint 路径是 `<output>.checkpoint.json`，schema 包含 `version`、`collector`、`chain`、`address`、`topic0`、`from_block`、`to_block`、`last_completed_block`、`rows_written`、`output`、`updated_at_utc`。
6. `date/chog_collection_runs.csv` 只记录采集运行元数据，不改变历史样本 CSV 的证据含义。

新增 Parquet 数据集:

```text
raw/event_block_headers
derived/memecoin_event_features
derived/memecoin_hourly_features
```

`raw/event_block_headers` 只覆盖 CHOG 本地事件所在 blocks；全量 `raw/block_headers` 不再是默认 backfill 输入。

## 当前关键数字

### 约 19.8 天价格

`date/chog_prices_476h_1h.csv`:

```text
rows = 476
observed = 291
forward_fill = 185
window = 2026-04-16T19:00:00Z -> 2026-05-06T14:00:00Z
start_price = 0.000960763840
end_price = 0.001462409850
return = 52.21%
min_price = 0.000638212623
max_price = 0.001569971548
hourly_std = 3.55%
```

### DEX 池子快照

`date/chog_dex_pairs_snapshot.csv`:

```text
pairs = 10
total_liquidity_usd = 125,722.09
total_h24_volume_usd = 67,309.47
h24_buys = 457
h24_sells = 744
h24_count_imbalance = -0.239
```

主池:

```text
dex = nad-fun
pair = 0x116e7D070f1888B81E1E0324F56d6746B2D7d8f1
quote = MON
liquidity_usd = 118,472.24
h24_volume_usd = 65,103.90
liquidity_share = 94.23%
volume_share = 96.72%
h24_buys/sells = 196/387
h24_price_change = 11.68%
```

解释:

1. CHOG 流动性和成交几乎都集中在 nad-fun 的 CHOG/MON 主池。
2. 过去 24 小时按笔数看是卖出占优，但价格仍上涨，说明卖出笔数多不等价于卖出金额占优。
3. 后续必须抓 swap amount，不能只看 buys/sells count。

### 20k block transfer logs

`date/chog_transfer_logs_20k_blocks.csv`:

```text
logs = 252
transactions = 114
unique_addresses = 95
window = 2026-05-06T13:43:59Z -> 2026-05-06T15:56:31Z
total_chog_transferred = 14,780,600.618566
median_transfer = 486.312073
p90_transfer = 94,978.089391
max_transfer = 1,314,231.657917
```

按小时:

```text
2026-05-06T13:00:00Z: 55 logs
2026-05-06T14:00:00Z: 145 logs
2026-05-06T15:00:00Z: 52 logs
```

已知池子相关 CHOG 流量:

```text
nad-fun MON:
  pool_in_chog = 2,605,038.199198
  pool_out_chog = 681,805.729863
  net_to_pool = 1,923,232.469334

atlantis-dex MON:
  pool_in_chog = 102,569.266317
  pool_out_chog = 20,479.630363
  net_to_pool = 82,089.635954

uniswap MON:
  pool_in_chog = 6,214.152834
  pool_out_chog = 1,938.392606
  net_to_pool = 4,275.760228
```

在 CHOG/MON 池里，CHOG 转入池子通常对应卖出 CHOG，CHOG 从池子转出通常对应买入 CHOG。因此这个窗口内主池 transfer 层面更偏净卖出。

### 100k block 主池 Swap logs

`date/chog_main_pool_swaps_100k_blocks.csv`:

```text
swap_rows = 171
swap_hours = 12
buy_swaps = 58
sell_swaps = 113
buy_chog = 10,331,120.83
sell_chog = 5,990,932.17
net_buy_chog = 4,340,188.66
```

解释:

1. 主池 Swap logs 直接给出方向和数量，是当前最强的 CHOG `G_t` 数据面。
2. 卖出笔数更多，但金额是净买入，说明 buy/sell count 不能当资金流。
3. 小时汇总可以形成 `MainPoolImpact` 和 `MainPoolSellPressure` proxy，但不能直接推出 `q_t/r_t/kappa_t/u_t/p_t`；这些对象只能后续作为 proxy/posterior summary 定义。

## 新增采集器

DEX 快照:

```bash
cargo run --manifest-path crate/Cargo.toml --bin dex_snapshot
```

Transfer logs:

```bash
cargo run --manifest-path crate/Cargo.toml --bin transfer_sample -- --blocks 20000 --output date/chog_transfer_logs_20k_blocks.csv
```

推荐正式采集命令:

```bash
cargo run --manifest-path crate/Cargo.toml --bin transfer_sample -- --blocks 20000 --append --resume --output date/chog_transfer_logs_20k_blocks.csv
```

主池 Swap logs:

```bash
cargo run --manifest-path crate/Cargo.toml --bin v3_swap_sample
```

推荐正式采集命令:

```bash
cargo run --manifest-path crate/Cargo.toml --bin v3_swap_sample -- --blocks 20000 --append --resume --output date/chog_main_pool_swaps_20k_blocks.csv
```

更长价格:

```bash
cargo run --manifest-path crate/Cargo.toml -- --hours 476 --output date/chog_prices_476h_1h.csv
```

## 下一步

下一步不再只按“继续补数据”描述，而按 [CHOG external 框架吸收计划](../research/chog/framework/external-absorption-plan.md) 的 V1 顺序推进。当前所有 projection 类对象都必须保留 proxy/posterior summary 语义，尤其是 `q_t/r_t/kappa_t/u_t/p_t`。

1. 用 `--append --resume` 持续运行 `transfer_sample` 和 `v3_swap_sample`，优先扩大 CHOG v1 observed log 窗口。
2. 定时化 DexScreener snapshot，形成 `liquidity_usd_t`。
3. 生成 `proxy-observations.jsonl` 草案 schema。
4. 加 receipt/gas outcome 数据面。
5. 做 sender/recipient 的 router/searcher 标签。
6. 用 walk-forward 验证 MainPoolImpact、volume、conflict proxy。

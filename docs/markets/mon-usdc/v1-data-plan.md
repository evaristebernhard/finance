# MON/USDC V1 数据计划

状态: 2026-05-10，已按 Rust V1 26 天 range-scoped quality check 和 tx body collector 工程化结果更新。

## 为什么转向

CHOG 的事件因子更适合作为研究样本，不适合作为第一阶段可执行市场。MON/USDC 的池子明显更深，且 USDC 计价让净收益、盘口冲击、库存风险和资金费率都更容易建模。

## 池子发现

- 候选池 CSV: `date/mon_usdc_pool_candidates_20260509.csv`
- MON token: `0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A`
- USDC token: `0x754704Bc059F8C67012fEd69BC8A327a5aafb603`

| rank | dex | family | pair | liquidity_usd | volume_h24_usd | h24 txns |
| ---: | --- | --- | --- | ---: | ---: | ---: |
| 1 | uniswap | v3 | `0x659bD0...D4a9da` | 1,797,632.54 | 2,219,847.79 | 3,160 |
| 2 | pancakeswap | v3 | `0x63e48B...8C53F2` | 567,277.15 | 6,132,113.36 | 14,257 |
| 3 | traderjoe | v2 | `0x5AFD3E...e77620` | 90,173.36 | 592,468.46 | 6,939 |
| 4 | traderjoe | v2 | `0x5E60BC...04fE22` | 73,142.87 | 174,822.47 | 3,054 |
| 5 | uniswap | v3 | `0xC33e9E...CB00D8` | 25,343.40 | 5,849.18 | 192 |
| 6 | pancakeswap | v3 | `0xB98979...322361` | 25,104.44 | 3,221.73 | 164 |
| 7 | pancakeswap | v3 | `0x85717A...Fea0f7` | 13,164.76 | 37,746.91 | 913 |
| 8 | nad-fun | unknown | `0x878750...BC1e52` | 11,284.85 | 3,578.49 | 369 |

## V1 采集形态

本版只做 swap-only:

- 从 DexScreener 发现 MON/USDC 池。
- 对选中的池直接抓 `eth_getLogs`，topic 覆盖 Uniswap V2/V3 Swap、Pancake v3 扩展 Swap、TraderJoe/LFJ v2.2 Liquidity Book Swap。
- 用 `token0()` / `token1()` 或 Liquidity Book `getTokenX()` / `getTokenY()` / `decimals()` 解析真实池内顺序，避免把 DexScreener base/quote 误当 AMM token0/token1。
- 输出方向只定义为 `buy_base` / `sell_base`，先不假设 maker/挂单，也不做 CHOG 那套高成本 taker 因子。

## 样本结果

- Swap CSV: `date/mon_usdc_v1_swaps_sample_20260509.csv`
- Block window: `73144838`..`73360837`
- 选中池子: 4
- Swap 行数: 17,405
- 方向计数: buy_mon=9,157, sell_mon=8,248
- 解码名义成交额: 8,349,356.42 USDC

| pool | dex | rows | usdc_abs | buy | sell |
| --- | --- | ---: | ---: | ---: | ---: |
| `0x63e48b...8c53f2` | pancakeswap | 14,244 | 6,128,342.44 | 7,517 | 6,727 |
| `0x659bd0...d4a9da` | uniswap | 3,161 | 2,221,013.97 | 1,640 | 1,521 |

## Rust V1 数据根

Rust V1 已把 MON/USDC 做成独立 market 数据根，而不是塞进 `data/chog/v1`:

```text
data/mon_usdc/v1/raw/pool_swap_logs
data/mon_usdc/v1/raw/event_block_headers
data/mon_usdc/v1/raw/tx_receipts
data/mon_usdc/v1/raw/pool_snapshots
```

新增根 `Cargo.toml` workspace，但保留现有 CHOG package 在 `crate/`，旧命令 `cargo --manifest-path crate/Cargo.toml ...` 已回归测试通过。

新增 package:

```text
crates/finance_chain_core
crates/mon_usdc_collectors
```

MON/USDC bins:

```text
mon_usdc_pool_snapshot
mon_usdc_swap_collect
mon_usdc_event_header_sample
mon_usdc_receipt_sample
mon_usdc_quality_check
mon_usdc_tx_body_sample
mon_usdc_receipt_log_bundle
mon_usdc_pool_state_sample
mon_usdc_trace_sample
mon_usdc_enriched_rebuild
```

核心 swap schema 使用通用命名:

```text
base_symbol=MON
quote_symbol=USDC
base_abs
quote_abs
price_quote_per_base
direction=buy_base|sell_base
```

## 最新 26 天区间质量结果

最新本地 range-scoped quality 结果覆盖了早先 `592099` swap-row 估计。

```text
completed range: 54574455..60190454
pool_swap_logs: 634009
event_block_headers: 383994
tx_receipts: 493760
missing_event_headers: 0
missing_receipts: 0
range quality passed: files=33013 rows=1511798
```

## Rust V1 实盘采集运行

DexScreener API 在本机连接超时，因此 pool snapshot 本轮用计划中固定 top4 写入:

```bash
target/debug/mon_usdc_pool_snapshot --data-root data/mon_usdc/v1 --known-top4-only
```

随后执行:

```bash
target/debug/mon_usdc_swap_collect --blocks 216000 --data-root data/mon_usdc/v1 --log-range-blocks 1000 --log-batch-size 8
target/debug/mon_usdc_swap_collect --from-block 73150455 --to-block 73366454 --data-root data/mon_usdc/v1 --log-range-blocks 1000 --log-batch-size 8 --checkpoint-suffix traderjoe-backfill --pool-address 0x5AFD3EC861f6104af26e8755aBcc1f876de77620 --pool-address 0x5E60BC3F7a7303BC4dfE4dc2220bdC90bc04fE22
target/debug/mon_usdc_event_header_sample --data-root data/mon_usdc/v1 --batch-size 200
target/debug/mon_usdc_receipt_sample --from-data-root --data-root data/mon_usdc/v1 --batch-size 250 --rpc-batch-size 50 --receipt-only
target/debug/mon_usdc_quality_check --data-root data/mon_usdc/v1
```

结果:

```text
block window: 73150455..73366454
resolved pools: 4 total, with 2 TraderJoe/LFJ pools backfilled by explicit address
TraderJoe/LFJ backfill rows: 10,035
pool_swap_logs: 27,503 rows
unique swap txs: 22,593
unique swap blocks: 14,765
event_block_headers: 14,765 rows
tx_receipts: 22,593 rows
quality check passed: files=630 rows=64,872
missing_event_headers=0
missing_receipts=0
```

按池和方向汇总:

| pool | dex | direction | rows | quote_abs | median price_quote_per_base |
| --- | --- | --- | ---: | ---: | ---: |
| `0x63e48b...8c53f2` | pancakeswap | buy_base | 7,579 | 3,181,378 USDC | 0.033076 |
| `0x63e48b...8c53f2` | pancakeswap | sell_base | 6,757 | 2,989,472 USDC | 0.033075 |
| `0x5afd3e...e77620` | traderjoe | buy_base | 3,631 | 276,998 USDC | 0.033130 |
| `0x5afd3e...e77620` | traderjoe | sell_base | 3,345 | 321,743 USDC | 0.033090 |
| `0x5e60bc...04fe22` | traderjoe | buy_base | 1,585 | 90,510 USDC | 0.033108 |
| `0x5e60bc...04fe22` | traderjoe | sell_base | 1,474 | 83,015 USDC | 0.033109 |
| `0x659bd0...d4a9da` | uniswap | buy_base | 1,647 | 1,257,254 USDC | 0.033092 |
| `0x659bd0...d4a9da` | uniswap | sell_base | 1,485 | 949,433 USDC | 0.032847 |

池子总计:

| pool | dex | family | rows | quote_abs | median price_quote_per_base |
| --- | --- | --- | ---: | ---: | ---: |
| `0x63e48b...8c53f2` | pancakeswap | pancake_v3 | 14,336 | 6,170,850 USDC | 0.033075 |
| `0x5afd3e...e77620` | traderjoe | lb_v22 | 6,976 | 598,742 USDC | 0.033114 |
| `0x5e60bc...04fe22` | traderjoe | lb_v22 | 3,059 | 173,524 USDC | 0.033109 |
| `0x659bd0...d4a9da` | uniswap | v3 | 3,132 | 2,206,688 USDC | 0.032983 |

TraderJoe/LFJ 实现说明:

```text
Swap topic: 0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70
Metadata fallback: getTokenX() / getTokenY()
Packed bytes32 amounts: X is low 128 bits, Y is high 128 bits
Pool MON delta > 0 => sell_base; pool MON delta < 0 => buy_base
price_quote_per_base = USDC_abs / MON_abs
```

## Rust V1 10 天续采

第一轮一天 top4 运行后，数据根继续向前扩展了十个 216,000-block 窗口:

```text
requested continuation window: 70990455..73150454
combined collection window: 70990455..73366454
observed swap block range: 70990475..73366454
pool_swap_logs: 255,910 rows
unique swap txs: 207,576
unique swap blocks: 133,418
event_block_headers: 133,418 rows
tx_receipts: 207,576 rows
quality check passed: files=6,909 rows=596,940
missing_event_headers=0
missing_receipts=0
zero_amount_swaps=2
```

这两行 zero-amount 是保留的 raw Uniswap v3 dust 事件，MON delta 为 0、USDC delta 为 1 micro-USDC。quality check 将它们报告为 `zero_amount_swaps=2`，但不把它们视为价格或方向解码失败。

当前池子总计:

| pool | dex | family | rows | quote_abs | median price_quote_per_base |
| --- | --- | --- | ---: | ---: | ---: |
| `0x63e48b...8c53f2` | pancakeswap | pancake_v3 | 128,570 | 47,252,130 USDC | 0.030307 |
| `0x5afd3e...e77620` | traderjoe | lb_v22 | 68,573 | 7,294,198 USDC | 0.030126 |
| `0x5e60bc...04fe22` | traderjoe | lb_v22 | 30,687 | 1,713,963 USDC | 0.030203 |
| `0x659bd0...d4a9da` | uniswap | v3 | 28,080 | 20,744,527 USDC | 0.030384 |

运行说明:

```text
Swap logs were collected as ten independent day windows with checkpoint suffixes mon-usdc-prev10-d01..d10-20260509.
Event headers were also fetched by day window; batch-size 500 worked on this machine/RPC.
Receipt collection used four queue shards via --shard-index/--shard-count and rpc-batch-size 100.
Receipt dry-run after sharding: queued hashes after dedupe = 0.
```

验证:

```bash
cargo fmt --all
cargo test -p finance_chain_core -p mon_usdc_collectors
cargo test --manifest-path crate/Cargo.toml
cargo build -p mon_usdc_collectors
target/debug/mon_usdc_quality_check --data-root data/mon_usdc/v1
```

策略研究上应先研究可执行微观结构因子: 成交强度、买卖冲击、短周期波动、池间价差、gas/拥挤和库存偏移。CHOG 的第一性原理因子框架可以复用，但成本模型要换成 MON/USDC 的真实池 fee、tick liquidity 和下单方式。

## V1 Enrichment 层

状态: 2026-05-10，已为 87 天 enrichment pass 加入实现框架。第一项工程优化是 tx body collector 路径。

Enrichment 路径在不改变 `raw/tx_receipts` 的前提下，扩展现有 raw swap/header/receipt 数据带:

```text
raw/pool_swap_logs
  -> raw/tx_bodies
  -> raw/tx_receipt_logs + raw/tx_receipt_log_summaries
  -> derived/event_price_path_labels
  -> derived/tx_execution_path_labels
  -> derived/cross_pool_dislocation_features
  -> sampled raw/pool_state_samples + raw/pool_liquidity_windows
  -> sampled raw/debug_trace_summaries + raw/debug_trace_calls
  -> completion report
```

新增 collector bins:

```text
mon_usdc_tx_body_sample
mon_usdc_receipt_log_bundle
mon_usdc_pool_state_sample
mon_usdc_trace_sample
mon_usdc_enriched_rebuild
```

2026-05-10 优化后的 tx body collector 行为:

```text
mon_usdc_tx_body_sample --workers N
  CLI default remains 1 for compatibility.
  scripts/run_mon_usdc_enrichment.ps1 defaults to 4 workers.

--batch-size 50 --rpc-batch-size 50
  Conservative orchestrator defaults chosen before restarting canonical collection.

data/mon_usdc/v1/_work/mon_usdc_tx_body_queue_v1_<from>_<to>.tsv
  Compact cached queue built from raw/pool_swap_logs.
  Final dedupe still scans existing raw/tx_bodies, so the current 331 parquet files remain valid.

checkpoint fields
  workers, queued, written, failed, rows_per_sec, completed_chunks.
```

collector 现在会把去重后的队列切成互不重叠的稳定 chunk，并为每个 worker 分配独立 HTTP client 和 RPC URL rotation 状态；每个完成的 chunk 会立即写盘。重跑不依赖 checkpoint completion，而是重建或复用 queue cache，并跳过 `raw/tx_bodies` 中已经存在的 hash。

小窗口 source scan 也会在文件名带 trailing block range 时裁剪 swap parquet 文件。这主要服务 smoke test 和 resume；首次 full-window cache build 仍可能有较重 I/O。

全覆盖目标:

```text
tx bodies: eth_getTransactionByHash for every unique swap tx
receipt log bundle: eth_getTransactionReceipt with complete logs for every unique swap tx
event_price_path_labels: every clean swap event
tx_execution_path_labels: every clean swap tx represented in the clean event set
cross_pool_dislocation_features: every clean swap event
```

抽样目标:

```text
pool_state_samples: at most 20,000 selected event blocks, pre/event block sides
pool_liquidity_windows: local active tick/bin windows for sampled event pools
debug traces: at most 25,000 selected swap txs via debug_traceTransaction callTracer
```

默认 Windows orchestrator:

```powershell
scripts/run_mon_usdc_enrichment.ps1 `
  -DataRoot data/mon_usdc/v1 `
  -FromBlock 54574468 `
  -ToBlock 73366454 `
  -RunTag 20260510_87d
```

该脚本的 tx body 阶段现在调用:

```text
target/release/mon_usdc_tx_body_sample --workers 4 --batch-size 50 --rpc-batch-size 50
```

完成产物:

```text
date/mon_usdc_v1_enrichment_completion_20260510_87d.json
date/mon_usdc_v1_enrichment_coverage_20260510_87d.csv
date/mon_usdc_v1_path_label_summary_20260510_87d.csv
date/mon_usdc_v1_price_path_label_summary_20260510_87d.csv
date/mon_usdc_v1_cross_pool_dislocation_summary_20260510_87d.csv
date/mon_usdc_v1_pool_state_sample_summary_20260510_87d.csv
date/mon_usdc_v1_trace_sample_summary_20260510_87d.csv
docs/markets/mon-usdc/v1-enrichment-report.md
```

最新 tx body 验证摘要:

```text
cargo fmt --all --manifest-path Cargo.toml: passed
cargo test -p mon_usdc_collectors -p mon_usdc_research: passed
cargo build --release -p mon_usdc_collectors -p mon_usdc_research: passed
copied-root RPC smoke 73365455..73366454: 81 rows, 2 parts, 0 failed rows, about 32 rows/sec
copied-root rerun dry-run: queued hashes after dedupe = 0
full-window dry-run 54574468..73366454: source swap txs=1,701,634, initial queued after dedupe=1,675,634
canonical tx body drain completed: 1k + 10k + 20k + 50k + 100k + 250k + 500k + 744,634 rows, all with 0 failed rows
latest dry-run after drain: source swap txs=1,701,634, existing tx body hashes=1,701,634, queued after dedupe=0
raw/tx_bodies parquet files after drain: 33,930
```

完成语义:

```text
base_enrichment_passed=true only when tx bodies and receipt log summaries both cover all unique swap txs with zero request errors.
sample_enrichment_passed=true when sampled failures are zero or explicitly classified in the report.
debug_traceTransaction is provider-dependent; unsupported tracing should be recorded as a classified sampled capability failure, not as a base-data failure.
```

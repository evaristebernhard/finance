# MON/USDC V1 Data Plan

Status: 2026-05-10, updated after the Rust V1 26-day range-scoped quality check.

## Why Pivot

CHOG 的事件因子更适合作为研究样本，不适合作为第一阶段可执行市场。MON/USDC 的池子明显更深，且 USDC 计价让净收益、盘口冲击、库存风险和资金费率都更容易建模。

## Pool Discovery

- Candidate CSV: `date/mon_usdc_pool_candidates_20260509.csv`
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

## V1 Collection Shape

本版只做 swap-only:

- 从 DexScreener 发现 MON/USDC 池。
- 对选中的池直接抓 `eth_getLogs`，topic 覆盖 Uniswap V2/V3 Swap、Pancake v3 扩展 Swap、TraderJoe/LFJ v2.2 Liquidity Book Swap。
- 用 `token0()` / `token1()` 或 Liquidity Book `getTokenX()` / `getTokenY()` / `decimals()` 解析真实池内顺序，避免把 DexScreener base/quote 误当 AMM token0/token1。
- 输出方向只定义为 `buy_base` / `sell_base`，先不假设 maker/挂单，也不做 CHOG 那套高成本 taker 因子。

## Sample Result

- Swap CSV: `date/mon_usdc_v1_swaps_sample_20260509.csv`
- Block window: `73144838`..`73360837`
- Selected pools: 4
- Swap rows: 17,405
- Direction counts: buy_mon=9,157, sell_mon=8,248
- Decoded notional: 8,349,356.42 USDC

| pool | dex | rows | usdc_abs | buy | sell |
| --- | --- | ---: | ---: | ---: | ---: |
| `0x63e48b...8c53f2` | pancakeswap | 14,244 | 6,128,342.44 | 7,517 | 6,727 |
| `0x659bd0...d4a9da` | uniswap | 3,161 | 2,221,013.97 | 1,640 | 1,521 |

## Rust V1 Data Root

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

## Latest 26-Day Range Quality Result

The latest local range-scoped quality result supersedes an earlier `592099` swap-row estimate.

```text
completed range: 54574455..60190454
pool_swap_logs: 634009
event_block_headers: 383994
tx_receipts: 493760
missing_event_headers: 0
missing_receipts: 0
range quality passed: files=33013 rows=1511798
```

## Rust V1 Live Run

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

Pool summary:

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

Pool totals:

| pool | dex | family | rows | quote_abs | median price_quote_per_base |
| --- | --- | --- | ---: | ---: | ---: |
| `0x63e48b...8c53f2` | pancakeswap | pancake_v3 | 14,336 | 6,170,850 USDC | 0.033075 |
| `0x5afd3e...e77620` | traderjoe | lb_v22 | 6,976 | 598,742 USDC | 0.033114 |
| `0x5e60bc...04fe22` | traderjoe | lb_v22 | 3,059 | 173,524 USDC | 0.033109 |
| `0x659bd0...d4a9da` | uniswap | v3 | 3,132 | 2,206,688 USDC | 0.032983 |

TraderJoe/LFJ implementation notes:

```text
Swap topic: 0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70
Metadata fallback: getTokenX() / getTokenY()
Packed bytes32 amounts: X is low 128 bits, Y is high 128 bits
Pool MON delta > 0 => sell_base; pool MON delta < 0 => buy_base
price_quote_per_base = USDC_abs / MON_abs
```

## Rust V1 10-Day Continuation

After the first one-day top4 run, the data root was extended by ten prior
216,000-block windows:

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

The two zero-amount rows are retained raw Uniswap v3 dust events with zero MON
delta and 1 micro-USDC delta. They are reported by quality check as
`zero_amount_swaps=2`, but not treated as price/direction decode failures.

Current pool totals:

| pool | dex | family | rows | quote_abs | median price_quote_per_base |
| --- | --- | --- | ---: | ---: | ---: |
| `0x63e48b...8c53f2` | pancakeswap | pancake_v3 | 128,570 | 47,252,130 USDC | 0.030307 |
| `0x5afd3e...e77620` | traderjoe | lb_v22 | 68,573 | 7,294,198 USDC | 0.030126 |
| `0x5e60bc...04fe22` | traderjoe | lb_v22 | 30,687 | 1,713,963 USDC | 0.030203 |
| `0x659bd0...d4a9da` | uniswap | v3 | 28,080 | 20,744,527 USDC | 0.030384 |

Operational notes:

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

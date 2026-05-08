# CHOG Memecoin 策略优先采集路径

状态: 2026-05-08，已落实到 `crate` CLI。

这份文档替代旧 runbook 里默认全量拉 `block_headers` 的做法。旧 collector 仍保留，但默认 backfill/incremental 路径改为围绕 CHOG 交易事件补最小必要数据。

新 Codex 接手时先读 [Codex Handoff: Memecoin Strategy Collection](./codex_handoff_memecoin_strategy.md)，里面记录了已改文件、已验证项、树莓派上暂停的重型验证和下一步 smoke 计划。

## 背景

一天 Monad 大约有 216,000 个 block。旧路径的 `block_header_sample` 会逐块拉 header，主要成本来自:

```text
216k eth_getBlockByNumber/day
```

当前因子和策略分析主要消费 swap、transfer、receipt/gas 和事件所在块的 base fee，不需要全量逐块 `block_headers`。因此默认路径改为:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

只有研究全链拥堵、逐块 gas regime 或非 CHOG 事件窗口时，才显式跑 full headers。

## 默认采集路径

### 1. Logs

继续用 RPC log collectors:

```bash
crate/target/debug/transfer_sample
crate/target/debug/v3_swap_sample
crate/target/debug/dex_swap_collect
```

默认 `chog_collect` 的 log chunk 已调到 1000 blocks。也可以用本地环境变量覆盖:

```bash
CHOG_LOG_RPCS="https://private-1,https://private-2,https://rpc.monad.xyz"
CHOG_LOG_RANGE_BLOCKS=1000
```

`CHOG_LOG_RPCS` 只供 log collectors 使用；header/receipt RPC 仍走 `--rpc-url` 或 `--header-rpc-url`。

### 2. Event headers

新增 collector:

```bash
crate/target/debug/event_header_sample \
  --data-root data/chog/v1 \
  --from-block "$FROM" \
  --to-block "$TO" \
  --batch-size 200
```

它从本地 raw logs 发现唯一事件块:

```text
raw/main_pool_swap_logs
raw/dex_pool_swap_logs
raw/erc20_transfer_logs
```

然后只请求缺失的事件块 header，写入:

```text
raw/event_block_headers
```

核心字段复用 `block_headers`，并增加:

```text
event_log_count
event_tx_count
source_datasets
```

Dry-run 会输出本地唯一事件块数量、已存在 event headers 数量、缺失数量和预计 RPC batch 数:

```bash
crate/target/debug/event_header_sample \
  --data-root data/chog/v1 \
  --from-block "$FROM" \
  --to-block "$TO" \
  --dry-run
```

### 3. Receipts

`receipt_sample` 的默认 source scope 已改为 CHOG 池交易:

```bash
crate/target/debug/receipt_sample \
  --data-root data/chog/v1 \
  --from-data-root \
  --source-scope chog-pool-txs \
  --timestamp-source local-first
```

2026-05-08 运行经验: 当前 memecoin features 只消费 receipt outcome/gas 字段，后续日窗口建议加:

```bash
--rpc-batch-size 50 --receipt-only
```

`--rpc-batch-size` 使用 JSON-RPC batch 降低 HTTP 往返；`--receipt-only` 跳过 `eth_getTransactionByHash`，只取 `eth_getTransactionReceipt`。如果后续研究需要 nonce、input、value、max fee 等交易 body 字段，再去掉 `--receipt-only`。

`--source-scope` 可选:

```text
chog-pool-txs  main_pool_swap_logs + dex_pool_swap_logs
main-pool      main_pool_swap_logs
all-token      erc20_transfer_logs + main_pool_swap_logs + dex_pool_swap_logs
```

`--timestamp-source local-first` 的顺序:

```text
source log block_timestamp
raw/event_block_headers block_timestamp
RPC eth_getBlockByNumber fallback
```

`tx_receipts` schema 没有破坏性变更。

### 4. Memecoin features

新增 rebuild subcommand:

```bash
crate/target/debug/dex_rebuild \
  --data-root data/chog/v1 \
  memecoin-features
```

输出:

```text
derived/memecoin_event_features
derived/memecoin_hourly_features
```

事件级特征包括:

```text
swap direction
CHOG amount
quote amount
price_quote_per_chog
signed_chog_flow
receipt_status
gas_used
effective_gas_price
base_fee_per_gas
priority_fee_per_gas_proxy
same_block_pool_event_count
```

小时级特征包括:

```text
volume
net buy flow
unique tx count
active block count
gas mean/median
effective gas mean/median
priority fee proxy mean/median
receipt success rate
```

Dry-run:

```bash
crate/target/debug/dex_rebuild \
  --data-root data/chog/v1 \
  memecoin-features \
  --dry-run
```

### 5. Quality check

`chog_quality_check` 已纳入:

```text
raw/event_block_headers
derived/memecoin_event_features
derived/memecoin_hourly_features
```

运行:

```bash
crate/target/debug/chog_quality_check \
  --data-root data/chog/v1
```

## Orchestrator

默认:

```bash
crate/target/debug/chog_collect \
  --mode backfill \
  --data-root data/chog/v1
```

等价于 header mode `event`:

```bash
--header-mode event
```

`chog_collect` 的相关默认行为:

```text
log_range_blocks = CHOG_LOG_RANGE_BLOCKS or 1000
log RPCs = --log-rpc-url or CHOG_LOG_RPCS or --rpc-url
header_mode = event
event header batch size = 200
receipt source scope = chog-pool-txs
receipt timestamp source = local-first
memecoin-features rebuild = enabled
quality check = enabled
```

可选开关:

```bash
--header-mode full
--header-mode skip
--skip-receipts
--skip-memecoin-features
--skip-quality-check
```

## Full headers 逃生路径

需要全链逐块 gas/header 数据时显式运行:

```bash
crate/target/debug/chog_collect \
  --mode backfill \
  --data-root data/chog/v1 \
  --header-mode full
```

或直接跑旧 collector:

```bash
crate/target/debug/block_header_sample \
  --from-block "$FROM" \
  --to-block "$TO" \
  --data-root data/chog/v1 \
  --part-blocks 1000 \
  --batch-size 200
```

不要把 `block_header_sample` 重新放回默认 memecoin backfill，除非目标明确需要全链逐块样本。

## 验证清单

已覆盖的单元测试:

```text
event block discovery window/filter/skip
receipt source-scope selection
local-first timestamp avoids RPC timestamp fallback
memecoin event/hourly feature aggregation
```

常规回归:

```bash
cargo test --manifest-path crate/Cargo.toml
cargo build --manifest-path crate/Cargo.toml --bins
```

建议 smoke:

```bash
DATA_ROOT=/tmp/chog-v1-smoke

crate/target/debug/transfer_sample ...
crate/target/debug/v3_swap_sample ...
crate/target/debug/dex_swap_collect ...
crate/target/debug/event_header_sample --data-root "$DATA_ROOT" --from-block "$FROM" --to-block "$TO"
crate/target/debug/receipt_sample --data-root "$DATA_ROOT" --from-data-root
crate/target/debug/dex_rebuild --data-root "$DATA_ROOT" memecoin-features
crate/target/debug/chog_quality_check --data-root "$DATA_ROOT"
```

期望 event headers 请求量显著小于窗口 block 数；在稀疏交易窗口里目标是至少少一个数量级，通常远大于 20x。

## 安全说明

不要把私有 RPC、Alchemy key、OpenAI 会话 token 或浏览器导出的 session JSON 写入仓库。`.env.chog.local` 仍是本地私密配置入口。

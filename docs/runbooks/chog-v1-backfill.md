# CHOG v1 30 天 Backfill Runbook

这份文档记录 2026-05-07 的一天窗口实测经验，并把后续 30 天历史数据的跑法固定下来。目标是慢慢补齐正式 Parquet 数据，不追求一次命令跑完 30 天。

更新: memecoin 策略默认路径已从“全量逐块 `block_headers`”改为“事件块 `event_block_headers` + local-first receipts + memecoin features”。新路径见 [CHOG Memecoin 策略优先采集路径](./chog-memecoin-collection.md)。本 runbook 里的 full header 命令只作为全链逐块研究的逃生路径保留。

## 当前状态

最新 live 状态见 [Codex Handoff: Live CHOG Collection Status](../handoff/live-collection.md)。

2026-05-09 继续采集后，memecoin 策略路径已经质量检查通过到约三十天连续窗口:

```text
66507947..72992946
```

最新质量检查核心计数:

```text
raw.main_pool_swap_logs: rows=11207
raw.dex_pool_swap_logs: rows=18795
raw.erc20_transfer_logs: rows=47049
raw.tx_receipts: rows=15687
raw.event_block_headers: rows=22001
derived.memecoin_event_features: rows=18795
derived.memecoin_hourly_features: rows=2226
quality check passed: files=15719 rows=359208
```

下一段历史窗口:

```text
FROM=66291947
TO=66507946
DAY_TAG=day20260406
```

Receipts 当前建议用 `--receipt-only --rpc-batch-size 50`，因为当前 memecoin features 只需要 receipt outcome/gas 字段，实测比完整 `eth_getTransactionByHash` 路径更快。

正式数据目录:

```text
data/chog/v1
```

已验证连续窗口:

```text
66507947..72992946
```

其中 `72771947..72987946` 是较早完成的约一天窗口，`72987947..72992946` 是此前 5,000-block 正式 slice。2026-05-09 本地质量检查结果:

```text
raw.main_pool_swap_logs: files=3855 rows=11207 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.dex_pool_swap_logs: files=5028 rows=18795 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.erc20_transfer_logs: files=4529 rows=47049 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.dex_pairs_snapshots: files=3 rows=33 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.tx_receipts: files=685 rows=15687 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.block_headers: files=222 rows=221000 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.event_block_headers: files=60 rows=22001 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.prices_hourly: files=2 rows=24 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
raw.collection_runs: files=1269 rows=1269 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
derived.dex_pool_swap_hourly: files=2 rows=100 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
derived.dex_swap_factors: files=2 rows=1022 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
derived.memecoin_event_features: files=31 rows=18795 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
derived.memecoin_hourly_features: files=31 rows=2226 duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
quality check passed: files=15719 rows=359208
```

当前 memecoin 路径最早已推进到 `day20260407`，下一段从 `day20260406` 继续。Shard checkpoint 保留在 `data/chog/v1/_checkpoints/*day20260407*.json` 等文件中，用于审计和重跑具体 shard。

## RPC 经验

高吞吐 backfill 不要把所有请求都压到同一个 provider。

| 用途 | 默认选择 | 参数 | 经验 |
| --- | --- | --- | --- |
| Transfer logs | mx/g7 Alchemy 优先，公共 RPC 兜底 | `--log-range-blocks "$CHOG_LOG_RANGE_BLOCKS"` | `rpc.monad.capacity.tsv` 显示 mx/g7 可跑 1000-block `eth_getLogs` |
| Swap logs | mx/g7 Alchemy 优先，公共 RPC 兜底 | `--log-range-blocks "$CHOG_LOG_RANGE_BLOCKS"` | 与 transfer 同策略 |
| Event headers | header/receipt RPC | `event_header_sample --batch-size 200` | 只补本地 CHOG 事件块，默认路径 |
| Full block headers | `https://rpc1.monad.xyz` | `block_header_sample --batch-size 200` | 仅全链逐块 gas/header 研究时显式跑 |
| Receipts | 私有 RPC 或小速率公共 RPC | `--source-scope chog-pool-txs --timestamp-source local-first` | 默认只补 CHOG 池交易 outcome |
| Dex snapshot | DexScreener | 每轮追加当前快照 | 没有历史接口，不伪造历史 |
| Prices | DeFiLlama | 不按 day 重复跑 | 已有 part 不要反复写同名窗口 |

已知不适合高并发 headers 的情况:

1. Alchemy 在 headers 并发下触发 CUPS 429。
2. `https://rpc.monad.xyz` 触发约 25 requests/second 限制。
3. `https://rpc2.monad.xyz` 曾触发 rate limit。
4. `https://rpc3.monad.xyz` 曾拒绝 50-size batch。
5. dRPC batch 100 可用，但 batch 200 免费层失败。
6. monadinfra 禁用 batch header 方法。
7. huginn 和 Tenderly 在测试时 TLS/连接不稳定。

## 本地配置

私有 RPC 不写进文档正文。用本地 env 文件承载:

```bash
cp .env.chog.local.example .env.chog.local
```

编辑 `.env.chog.local` 后，在每次运行前加载:

```bash
source .env.chog.local
```

`.env.chog.local` 已被 `.gitignore` 忽略。模板提供变量结构；复制后按本地可用 key 调整。

先构建采集二进制:

```bash
cargo build --manifest-path crate/Cargo.toml --bins
```

## 一天窗口执行模板

一天按约 `216,000` blocks 估算。每次手动固定 `FROM` 和 `TO`，避免动态 latest 导致窗口重叠。

当前下一段历史窗口从这里开始:

```bash
FROM=66291947
TO=66507946
DAY_TAG=day20260406
SHARD_SIZE=18000
LOG_DIR="/tmp/chog-v1-${DAY_TAG}"
mkdir -p "$LOG_DIR"
source .env.chog.local
```

准备 log RPC 参数。`CHOG_LOG_RPCS` 在 `.env.chog.local` 中按 mx/g7 优先、公共 RPC 兜底排序:

```bash
: "${CHOG_LOG_RANGE_BLOCKS:=1000}"
if ! declare -p CHOG_LOG_RPCS >/dev/null 2>&1; then
  CHOG_LOG_RPCS=("${CHOG_PUBLIC_LOG_RPCS[@]}")
fi

LOG_RPC_ARGS=()
for rpc in "${CHOG_LOG_RPCS[@]}"; do
  LOG_RPC_ARGS+=(--rpc-url "$rpc")
done
```

并行跑 transfer logs:

```bash
pids=()
for i in $(seq 0 11); do
  s_from=$((FROM + i * SHARD_SIZE))
  s_to=$((s_from + SHARD_SIZE - 1))
  if [ "$s_to" -gt "$TO" ]; then s_to=$TO; fi

  suffix=$(printf '%s-s%02d' "$DAY_TAG" "$i")
  log=$(printf '%s/transfer-s%02d.log' "$LOG_DIR" "$i")
  (
    crate/target/debug/transfer_sample \
      --format parquet \
      --append \
      --from-block "$s_from" \
      --to-block "$s_to" \
      --log-range-blocks "$CHOG_LOG_RANGE_BLOCKS" \
      --data-root "$CHOG_DATA_ROOT" \
      --checkpoint-suffix "$suffix" \
      "${LOG_RPC_ARGS[@]}"
  ) >"$log" 2>&1 &
  pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then status=1; fi
done
if [ "$status" -ne 0 ]; then
  echo "one or more transfer shards failed" >&2
  false
fi
```

并行跑主池 swap logs:

```bash
pids=()
for i in $(seq 0 11); do
  s_from=$((FROM + i * SHARD_SIZE))
  s_to=$((s_from + SHARD_SIZE - 1))
  if [ "$s_to" -gt "$TO" ]; then s_to=$TO; fi

  suffix=$(printf '%s-s%02d' "$DAY_TAG" "$i")
  log=$(printf '%s/swap-s%02d.log' "$LOG_DIR" "$i")
  (
    crate/target/debug/v3_swap_sample \
      --format parquet \
      --append \
      --from-block "$s_from" \
      --to-block "$s_to" \
      --log-range-blocks "$CHOG_LOG_RANGE_BLOCKS" \
      --data-root "$CHOG_DATA_ROOT" \
      --checkpoint-suffix "$suffix" \
      "${LOG_RPC_ARGS[@]}"
  ) >"$log" 2>&1 &
  pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then status=1; fi
done
if [ "$status" -ne 0 ]; then
  echo "one or more swap shards failed" >&2
  false
fi
```

默认只补事件块 headers:

```bash
crate/target/debug/event_header_sample \
  --from-block "$FROM" \
  --to-block "$TO" \
  --batch-size 200 \
  --batch-throttle-ms 0 \
  --data-root "$CHOG_DATA_ROOT" \
  --checkpoint-suffix "${DAY_TAG}-event-headers" \
  --rpc-url "$CHOG_HEADER_RPC"
```

只有需要全链逐块 gas/header 研究时，才跑 full block headers。先单节点长跑，不并发打 header RPC:

```bash
crate/target/debug/block_header_sample \
  --from-block "$FROM" \
  --to-block "$TO" \
  --part-blocks 1000 \
  --batch-size 200 \
  --batch-throttle-ms 0 \
  --data-root "$CHOG_DATA_ROOT" \
  --checkpoint-suffix "${DAY_TAG}-headers" \
  --rpc-url "$CHOG_HEADER_RPC"
```

补当前 Dex snapshot:

```bash
crate/target/debug/dex_snapshot \
  --format parquet \
  --data-root "$CHOG_DATA_ROOT"
```

Receipts 默认只补 CHOG 池交易，并优先使用本地 log/event header 时间戳。大窗口仍建议先 dry-run 再小批量跑。

Prices 不按 day 重复跑。需要完整 30 天价格时，单独跑一次更大 `--hours` 窗口；如果遇到同名 Parquet 冲突，不要手动覆盖，先确认是否需要增加价格 collector 的版本化输出策略。

## Receipts backlog 补数

`receipt_sample` 会从 swap/transfer 数据里扫描唯一 transaction hash，并排除已有 `tx_receipts` hash。RPC 或网络错误会让当前 batch 失败退出，不会写 `request_status=error` 行；链上真实空结果仍会写 `missing_receipt`、`missing_transaction` 或 `missing`。

优先在本地 `.env.chog.local` 配 `ALCHEMY_RPC`。命令不需要把私有 URL 写在 shell history 里；collector 会自动读取环境变量或 repo 根目录的 `.env.chog.local`，再用传入的公共 RPC 做兜底。

先看队列:

```bash
source .env.chog.local

crate/target/debug/receipt_sample \
  --from-data-root \
  --source-scope chog-pool-txs \
  --timestamp-source local-first \
  --data-root "$CHOG_DATA_ROOT" \
  --dry-run
```

先烟测 25 条，不并发:

```bash
crate/target/debug/receipt_sample \
  --from-data-root \
  --source-scope chog-pool-txs \
  --timestamp-source local-first \
  --max-txs 25 \
  --batch-size 25 \
  --data-root "$CHOG_DATA_ROOT"

crate/target/debug/chog_quality_check --data-root "$CHOG_DATA_ROOT"
```

烟测通过后，每轮 200 条、batch 50。每轮结束后都看剩余队列并跑质量检查:

```bash
crate/target/debug/receipt_sample \
  --from-data-root \
  --source-scope chog-pool-txs \
  --timestamp-source local-first \
  --max-txs 200 \
  --batch-size 50 \
  --data-root "$CHOG_DATA_ROOT"

crate/target/debug/receipt_sample \
  --from-data-root \
  --source-scope chog-pool-txs \
  --timestamp-source local-first \
  --data-root "$CHOG_DATA_ROOT" \
  --dry-run

crate/target/debug/chog_quality_check --data-root "$CHOG_DATA_ROOT"
```

补完条件:

```text
queued hashes after dedupe: 0
tx_receipts: ... duplicate_keys=0 request_status_errors=0 utc_errors=0 dt_errors=0
```

不要并发跑 receipts。Alchemy CUPS 和公共 RPC 限流都可能导致整批失败；失败后保持 data root 不动，重跑同一命令。

## Dex snapshot 15 分钟定时

DexScreener snapshot 没有历史接口，必须从现在开始累计。15 分钟定时只跑专用命令，不用 `chog_collect incremental` 代替，避免默认牵连 receipts、prices、logs。

手动验证一次:

```bash
source .env.chog.local

crate/target/debug/dex_snapshot \
  --format parquet \
  --data-root "$CHOG_DATA_ROOT"
```

systemd 模板:

```text
crate/ops/chog-dex-snapshot.service
crate/ops/chog-dex-snapshot.timer
```

安装方式:

```bash
sudo cp crate/ops/chog-dex-snapshot.service /etc/systemd/system/
sudo cp crate/ops/chog-dex-snapshot.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chog-dex-snapshot.timer
systemctl list-timers chog-dex-snapshot.timer
```

不用 systemd 时，把 `crate/ops/chog_dex_snapshot.cron` 的单行合并进当前 crontab，不要覆盖已有任务。

## Prices 720h 暂缓

Receipts 补完前先不写 720h 正式价格窗口。已有 24h price part 和未来 720h 窗口可能覆盖同一小时；在写正式数据前，先补 duplicate-hour 检查，或明确读取时按 `(token, timestamp)` 取最新/指定 collector part 的 canonical 规则。

## 中断恢复

Log shard 中断后，重跑同一个 collector、同一个 `from/to` 和同一个 `--checkpoint-suffix`。已有相同 part 会跳过，相同 `(block_number, transaction_hash, log_index)` 不应产生质量检查重复。

Event header 中断后直接用同一个窗口和 suffix 重跑；已存在的 `event_block_headers` 会按 block_number 跳过。Full header 中断才使用旧 collector resume:

```bash
crate/target/debug/event_header_sample \
  --from-block "$FROM" \
  --to-block "$TO" \
  --batch-size 200 \
  --batch-throttle-ms 0 \
  --data-root "$CHOG_DATA_ROOT" \
  --checkpoint-suffix "${DAY_TAG}-event-headers" \
  --rpc-url "$CHOG_HEADER_RPC"

crate/target/debug/block_header_sample \
  --resume \
  --to-block "$TO" \
  --part-blocks 1000 \
  --batch-size 200 \
  --batch-throttle-ms 0 \
  --data-root "$CHOG_DATA_ROOT" \
  --checkpoint-suffix "${DAY_TAG}-headers" \
  --rpc-url "$CHOG_HEADER_RPC"
```

如果某个 RPC 连续失败，保持已落盘数据不动，只换 RPC 参数重跑同一命令。不要删除正式 data root。

## 每天完成后的检查

每天窗口完成后必须跑:

```bash
crate/target/debug/dex_rebuild \
  --data-root "$CHOG_DATA_ROOT" \
  memecoin-features

crate/target/debug/chog_quality_check --data-root "$CHOG_DATA_ROOT"
```

再看关键 checkpoint 和文件数:

```bash
grep -E 'from_block|to_block|last_completed_block|rows_written|updated_at_utc' \
  "$CHOG_DATA_ROOT/_checkpoints/event_header_sample--${DAY_TAG}-event-headers.json"

find "$CHOG_DATA_ROOT/raw" -name '*.parquet' | sort | wc -l
```

质量检查通过后，再进入下一天。下一天窗口按下面方式向历史倒推:

```bash
NEXT_TO=$((FROM - 1))
NEXT_FROM=$((FROM - 216000))
```

30 天目标约 30 个 day window。保持窗口不重叠，记录每次 `FROM`、`TO`、`DAY_TAG` 和 quality check 输出。

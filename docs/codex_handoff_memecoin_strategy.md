# Codex Handoff: Memecoin Strategy Collection

状态: 2026-05-08。给新开的 Codex 先读最新 live handoff: [Codex Handoff: Live CHOG Collection Status](./codex_handoff_live_collection_20260508.md)，再读这份和 [CHOG Memecoin 策略优先采集路径](./chog_memecoin_collection_strategy.md)。

最新进展补充:

```text
clean memecoin-path coverage: 71907947..72992946, about five days
latest closed day tag: day20260502
next historical window: day20260501, 71691947..71907946
receipt_sample now supports --rpc-batch-size and --receipt-only
recommended receipt mode for memecoin features: --receipt-only --rpc-batch-size 50
latest quality check passed: files=3550 rows=246897
```

## 当前用户意图

把 CHOG v1 backfill 从“全量逐块 block headers”改成“策略优先、事件驱动”:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

主要目标是减少 RPC header 请求量，优先服务 memecoin 策略研究。

## 已完成代码改动

新增:

```text
crate/src/bin/event_header_sample.rs
crate/src/memecoin_features.rs
docs/chog_memecoin_collection_strategy.md
docs/codex_handoff_memecoin_strategy.md
```

修改:

```text
crate/src/bin/chog_collect.rs
crate/src/bin/receipt_sample.rs
crate/src/bin/dex_rebuild.rs
crate/src/bin/chog_quality_check.rs
crate/src/lib.rs
crate/README.md
docs/chog_v1_backfill_runbook.md
docs/chog_data_inventory.md
```

核心行为:

```text
chog_collect --header-mode event|full|skip
event is default
event_header_sample writes raw/event_block_headers
receipt_sample defaults to --source-scope chog-pool-txs
receipt_sample defaults to --timestamp-source local-first
dex_rebuild memecoin-features writes derived/memecoin_event_features and derived/memecoin_hourly_features
chog_quality_check includes the new raw/derived datasets
```

## 已完成验证

在文档更新前，已成功跑过:

```bash
cargo fmt --manifest-path crate/Cargo.toml
cargo test --manifest-path crate/Cargo.toml
```

测试通过内容包括:

```text
event block discovery window/filter/skip existing event headers
receipt source-scope selection
local-first timestamp avoids RPC timestamp fallback
memecoin event/hourly feature aggregation
existing library/bin unit tests
```

注意: 后续尝试 `cargo build --manifest-path crate/Cargo.toml --bins` 时，用户指出树莓派负载吃紧并中断。不要在这台机器上继续重型 Cargo 构建，除非用户明确要求。

## 当前打包产物

已生成源码/文档快照:

```text
finance_chain_memecoin_strategy_20260508.zip
```

包含:

```text
crate/src
crate/Cargo.toml
crate/Cargo.lock
crate/README.md
docs
scripts
.env*.example
.gitignore
```

不包含:

```text
crate/target
data
.git
large historical archives
private env files
```

## Git 状态

用户要求“开一下 git”。已在 `/home/chao/finance_chain` 执行:

```bash
git init
```

尚未 add/commit。新 Codex 可以用:

```bash
git status --short
```

确认未跟踪文件，再由用户决定是否提交。

## 下一步建议

在更强机器或用户允许时继续:

```bash
cargo build --manifest-path crate/Cargo.toml --bins
```

然后做 CLI dry-run:

```bash
crate/target/debug/event_header_sample \
  --data-root /tmp/chog-v1-empty \
  --from-block 1 \
  --to-block 10 \
  --dry-run

crate/target/debug/receipt_sample \
  --data-root /tmp/chog-v1-empty \
  --source-scope chog-pool-txs \
  --timestamp-source local-first \
  --dry-run

crate/target/debug/dex_rebuild \
  --data-root /tmp/chog-v1-empty \
  memecoin-features \
  --dry-run
```

如果要验证 `chog_collect --dry-run`，注意它仍会在启动时固定 latest block，因此需要可用 RPC/network:

```bash
crate/target/debug/chog_collect \
  --mode backfill \
  --from-block "$FROM" \
  --to-block "$TO" \
  --data-root /tmp/chog-v1-smoke \
  --header-mode event \
  --skip-dex-snapshot \
  --skip-prices \
  --dry-run
```

## Smoke 计划

在非树莓派环境跑小窗口:

```text
1. transfer_sample
2. v3_swap_sample
3. dex_swap_collect, if latest dex snapshot exists
4. event_header_sample
5. receipt_sample --source-scope chog-pool-txs --timestamp-source local-first
6. dex_rebuild memecoin-features
7. chog_quality_check
```

验收:

```text
raw/event_block_headers rows << window block count
receipt_sample does not make timestamp RPC calls when log/event header timestamp is available
derived/memecoin_event_features has gas/base_fee/priority_fee fields populated where source data exists
derived/memecoin_hourly_features aggregates volume, net buy flow, gas mean/median, active blocks, receipt success rate
```

## 安全边界

不要把私有 RPC、Alchemy key、OpenAI 会话 token 或浏览器 session JSON 写入仓库或 zip。`.env.chog.local` 仍只做本地私密配置，不应打包。

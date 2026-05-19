# Codex Handoff: Memecoin Strategy Collection

Note: this is a CHOG/MON data-collection and strategy-research handoff. For current BONK frontend/backend docs, start with [Engineering Docs](../engineering/README.md). For factor-analysis navigation, start with [Research Docs](../research/README.md).

状态: 2026-05-10。给新开的 Codex 先读最新 live handoff: [Codex Handoff: Live CHOG Collection Status](./live-collection.md)，再读这份和 [CHOG Memecoin 策略优先采集路径](../runbooks/chog-memecoin-collection.md)。

最新进展补充:

```text
clean memecoin-path coverage: 66507947..72992946, about thirty days
oldest completed day tag: day20260407
next historical window: day20260406, 66291947..66507946
receipt_sample now supports --rpc-batch-size and --receipt-only
recommended receipt mode for memecoin features: --receipt-only --rpc-batch-size 50
latest quality check passed: files=15719 rows=359208
```

## 最新因子研究补充

状态: 2026-05-09。已在 30 天 `derived/memecoin_event_features` 上完成事件级、成本感知、第一性原理因子研究，并补了一版事件现象拆解。当前用户明确希望继续研究事件因子和原理现象，暂时不展开 maker/LP/双向挂单路径。

新增脚本:

```text
scripts/chog_cost_aware_event_factor_research.py
scripts/chog_event_factor_phenomena_analysis.py
```

新增报告:

```text
docs/research/chog/2026-05-09-cost-aware-event-factors.md
docs/research/chog/2026-05-09-event-factor-phenomena.md
```

新增数据输出:

```text
date/chog_event_cost_labels_20260509.csv
date/chog_first_principles_factor_scores_20260509.csv
date/chog_cost_aware_ml_summary_20260509.csv
date/chog_event_factor_phenomena_20260509.csv
date/chog_event_factor_path_profiles_20260509.csv
date/chog_event_factor_daily_concentration_20260509.csv
date/chog_event_factor_untradable_reasons_20260509.csv
```

关键结论:

```text
1. nad-fun / CHOG-MON 主池约占 CHOG 成交量 95.84%，仍是事件因子主研究对象。
2. 保守 taker 方向研究被 2% round-trip 主池费强烈约束；5m/15m gross 边际太薄，扣成本后基本失效。
3. large_buy_p90 是当前最值得继续验证的事件现象，不是即时交易规则:
   6h gross 约 2.94%，0 bps extra-slippage net 约 0.94%，100 bps per-side stress 后转负。
4. large_buy_p90 的正向 6h 结果存在日期集中，尤其 2026-04-10 和 2026-04-24，需要扩数据验证跨日期稳定性。
5. 小额 quote、低活跃窗口、gas 占名义金额过高会制造异常 net label，已在 untradable reasons 输出中单独标记。
6. 小单噪声、低活跃、拥挤/gas regime 更适合作为过滤层，不应直接当方向信号。
```

复现命令:

```bash
python scripts/chog_cost_aware_event_factor_research.py
python scripts/chog_event_factor_phenomena_analysis.py
```

## 当前用户意图

把 CHOG v1 backfill 从“全量逐块 block headers”改成“策略优先、事件驱动”:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

主要目标是减少 RPC header 请求量，优先服务 memecoin 策略研究。

## MON/USDC V1 方向

最新用户判断: CHOG 流动性太小，继续把它当作事件因子/现象研究样本可以，但可执行策略研究先转向 MON/USDC。

已新增轻量 swap-only 脚本:

```text
scripts/mon_usdc_v1_swap_sample.py
```

脚本行为:

```text
1. 通过 DexScreener token-pairs API 发现 MON/USDC 候选池。
2. 选流动性最高的池，默认 top 2。
3. 用 RPC `eth_getLogs` 抓 swap logs。
4. 通过 `token0()` / `token1()` / `decimals()` 解析真实池顺序。
5. 输出 `buy_mon` / `sell_mon`、MON 数量、USDC 名义金额和 USDC/MON 价格。
```

已生成:

```text
date/mon_usdc_pool_candidates_20260509.csv
date/mon_usdc_v1_swaps_sample_20260509.csv
docs/markets/mon-usdc/v1-data-plan.md
docs/markets/mon-usdc/v1-factor-analysis.md
```

Rust V1 已新增独立 workspace/package:

```text
Cargo.toml
crates/finance_chain_core
crates/mon_usdc_collectors
data/mon_usdc/v1
```

2026-05-10 补充: MON/USDC enrichment 路径已开始工程化，第一步是优化
`mon_usdc_tx_body_sample`，先不要继续大规模裸跑旧单线程采集。
当前 tx body collector 支持:

```text
--workers N
data/mon_usdc/v1/_work/mon_usdc_tx_body_queue_v1_<from>_<to>.tsv
scripts/run_mon_usdc_enrichment.ps1 默认 --workers 4 --batch-size 50 --rpc-batch-size 50
```

已验证:

```text
cargo fmt --all --manifest-path Cargo.toml
cargo test -p mon_usdc_collectors -p mon_usdc_research
cargo build --release -p mon_usdc_collectors -p mon_usdc_research
copied-root RPC smoke 73365455..73366454: 81 rows, 2 parts, 0 failed rows
```

Canonical `raw/tx_bodies` 这轮没有继续大规模写入；已有 331 个 parquet
文件保留。恢复前先跑 full-window dry-run，再做 `--max-txs 1000` 和
10k/20k smoke。

最新 range-scoped live coverage:

```text
completed range: 54574455..60190454
pool_swap_logs: 634009
event_block_headers: 383994
tx_receipts: 493760
missing_event_headers=0
missing_receipts=0
range quality passed: files=33013 rows=1511798
```

注意: 本机 DexScreener API 超时，Rust pool snapshot 这轮用固定 top4 写入。Uniswap v3、Pancake v3 和两个 TraderJoe/LFJ v2.2 top 池都已产出 rows。TraderJoe/LFJ v2.2 通过 `getTokenX()` / `getTokenY()` 和 Liquidity Book packed Swap amounts 解码。早先 `592099` swap-row 估计已被本地 range-scoped quality 结果 `634009` 覆盖；十天续采 quality check 中 `zero_amount_swaps=2` 是保留的 Uniswap v3 零 MON delta dust 事件。

当前固定 top4:

```text
Uniswap v3 MON/USDC: 0x659bD0BC4167BA25c62E05656F78043E7eD4a9da
Pancake v3 MON/USDC: 0x63e48B725540A3Db24ACF6682a29f877808C53F2
TraderJoe/LFJ v2.2 MON/USDC: 0x5AFD3EC861f6104af26e8755aBcc1f876de77620
TraderJoe/LFJ v2.2 MON/USDC: 0x5E60BC3F7a7303BC4dfE4dc2220bdC90bc04fE22
Pancake v3 使用扩展 Swap topic:
0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83
TraderJoe/LFJ v2.2 使用 Liquidity Book Swap topic:
0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70
```

下一步如果扩大采集，应新建独立数据根，例如 `data/mon_usdc/v1`，不要把 MON/USDC 实验数据塞进 `data/chog/v1`。

## 已完成代码改动

新增:

```text
crate/src/bin/event_header_sample.rs
crate/src/memecoin_features.rs
docs/runbooks/chog-memecoin-collection.md
docs/handoff/memecoin-strategy.md
```

修改:

```text
crate/src/bin/chog_collect.rs
crate/src/bin/receipt_sample.rs
crate/src/bin/dex_rebuild.rs
crate/src/bin/chog_quality_check.rs
crate/src/lib.rs
crate/README.md
docs/runbooks/chog-v1-backfill.md
docs/reference/chog-data-inventory.md
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

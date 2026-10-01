# Polymarket 研究系统重构蓝图（系统化落地版）

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 把当前分散的 Polymarket 研究脚本体系化为一套支持“下一步策略研究”的稳定研究平台：统一数据、统一 claim 模型、统一因子输出、统一 join 逻辑、统一 execution realism 约束、统一报告产物。

**Architecture:** 采用“raw market data -> normalized events -> claim graph -> factor tables -> join/scoring -> execution realism -> research reports”的流水线。保持现有可运行脚本继续可用，但逐步把它们变成薄 CLI，底层迁移到 `scripts/polymarket/` 模块树。

**Tech Stack:** Python 3.12, local CSV/JSON/SQLite/Parquet artifacts, Polymarket public Gamma/CLOB/Data API, existing repo test style (`tests/test_polymarket_*.py`).

---

## A. 为什么这次要系统化，而不是继续加脚本

当前系统已经证明三件事：

1. 独立 EV 有价值
   - `scripts/polymarket_binance_close_signal_scan.py`
   - `scripts/polymarket_binance_close_ensemble.py`
   已经能筛出 threshold / close-settled claim 的候选。

2. Wallet flow 有价值，但更像 overlay
   - `scripts/polymarket_wallet_factor_probe.py`
   产出的是行为层信号、拥挤度、容量、rule ambiguity、delayed-copy proxy，不是完整 alpha 主体。

3. 当前最明显的瓶颈是 join 粒度太低
   - `scripts/polymarket_combined_strategy_join.py`
   主要按 token_id 精确 join，这会错过“同 underlying / 同方向 / 相近期限 / 逻辑相关 claim”的更高层关系。

所以，下一步研究不该只是继续添加 scanner，而是要把研究系统升级为：

```text
binary-claim pricing
+ claim graph consistency
+ smart-money / flow overlays
+ book-aware execution realism
+ reproducible research artifacts
```

---

## B. 重构的总原则

### B1. 不推翻已有脚本，先抽内核

现有脚本已经带来真实研究产物，不应该大爆炸重写。

原则：
- 第一步抽公共函数/数据模型
- 第二步保留旧 CLI，内部调用新模块
- 第三步再新增新的 claim-aware / execution-aware 入口

### B2. claim_id 成为研究主索引，token_id 降级为执行细节

今后所有关键表都应支持同时带：
- `token_id`
- `market_id`
- `condition_id`
- `claim_id`
- `underlying`

其中：
- 研究/组合优先按 `claim_id`
- 下钻到 book/trade/execution 再按 `token_id`

### B3. 产物优先于终端输出

每次运行都必须产出：
- machine-readable artifact（CSV/JSON/SQLite/Parquet）
- human-readable summary（Markdown）

不要把关键信息只留在 stdout。

### B4. execution realism 先打标签，再做硬过滤

早期不建议直接用 execution 模型把候选全部过滤没。
先做：
- fill realism score
- slippage risk tag
- stale-book risk tag
- queue uncertainty tag

等积累结果后再升级为 hard gate。

---

## C. 现状清点（基于当前仓库）

### C1. 当前脚本族

价格/EV：
- `scripts/polymarket_binance_close_signal_scan.py`
- `scripts/polymarket_binance_close_ensemble.py`
- `scripts/polymarket_binance_close_settlement_verify.py`
- `scripts/xrp_polymarket_vanilla_probe.py`

wallet / copyflow：
- `scripts/polymarket_wallet_factor_probe.py`
- `scripts/polymarket_copyflow_collect.py`
- `scripts/polymarket_copyflow_book_replay.py`
- `scripts/polymarket_delayed_copy_paper_strategy.py`
- `scripts/polymarket_delayed_copy_parameter_sweep.py`

deterministic baskets：
- `scripts/polymarket_range_basket_arbitrage_scan.py`
- `scripts/polymarket_negrisk_basket_arbitrage_scan.py`

join / combine：
- `scripts/polymarket_combined_strategy_join.py`

### C2. 当前测试族

- `tests/test_polymarket_binance_close_ensemble.py`
- `tests/test_polymarket_combined_strategy_join.py`
- `tests/test_polymarket_copyflow_forward.py`

### C3. 当前设计线索

从脚本与文档中已经存在的可复用概念：
- `MarketCase`
- `BinanceState`
- `Trade`
- `MarketMeta`
- `BookStats`
- `BookFill`
- wallet copyability / delay-robust edge
- robust EV across vol lookbacks
- VWAP replay against collected books
- rule ambiguity / liquidity / capacity / crowd exit risk

这些都说明系统已有雏形，只是结构还没统一。

---

## D. 目标目录结构（建议版）

```text
scripts/
  polymarket/
    __init__.py
    config.py
    utils/
      io.py
      http.py
      time.py
      ids.py
      mathx.py
      text_parse.py
    ingest/
      gamma_fetch.py
      clob_fetch.py
      data_fetch.py
      cache_layout.py
    normalize/
      event_schema.py
      market_normalizer.py
      trade_normalizer.py
      book_normalizer.py
      validate_events.py
    claims/
      claim_model.py
      claim_mapper.py
      claim_graph.py
      claim_consistency.py
      claim_family_rules.py
    factors/
      ev_close.py
      ev_ensemble.py
      wallet_flow.py
      copyflow.py
      microstructure.py
      mlofi.py
      pin_proxy.py
      basket_range.py
      basket_negrisk.py
    join/
      token_join.py
      claim_join.py
      combined_score.py
      reject_reasons.py
      candidate_rank.py
    execution/
      book_store.py
      book_replay.py
      queue_model.py
      latency_model.py
      fill_simulator.py
      realism_score.py
    reports/
      summary.py
      tables.py
      run_manifest.py
      markdown.py

scripts/
  polymarket_binance_close_signal_scan.py
  polymarket_binance_close_ensemble.py
  polymarket_wallet_factor_probe.py
  polymarket_combined_strategy_join.py
  polymarket_copyflow_collect.py
  polymarket_copyflow_book_replay.py
  polymarket_range_basket_arbitrage_scan.py
  polymarket_negrisk_basket_arbitrage_scan.py

output/
  polymarket/
    raw/
    normalized/
    claims/
    factors/
    joins/
    execution/
    reports/

docs/markets/onchain/
  polymarket-research-system-blueprint.md
  polymarket-normalized-event-spec.md
  polymarket-claim-graph-spec.md
  polymarket-execution-research-spec.md

tests/
  test_polymarket_normalize_events.py
  test_polymarket_claim_mapper.py
  test_polymarket_claim_graph.py
  test_polymarket_token_join.py
  test_polymarket_claim_join.py
  test_polymarket_execution_book_store.py
  test_polymarket_execution_fill_simulator.py
```

说明：
- 顶层旧脚本继续保留，避免破坏现有 workflow。
- 新模块放入 `scripts/polymarket/`，让旧 CLI 逐步只做 argparse + orchestration。

---

## E. 统一数据模型（必须先做）

### E1. RawArtifact

用途：记录任何原始 API 响应的来源与存档路径。

建议字段：
- `source`: gamma|clob|data|binance
- `endpoint`: `/markets` / `/book` / `/trades` ...
- `request_params_json`
- `fetch_ts_utc`
- `response_path`
- `sha256`
- `http_status`

落地：
- JSON sidecar 或 run manifest 中记录

### E2. NormalizedEvent

这是系统最重要的统一事件格式。

建议 dataclass / schema 字段：
- `event_type`
  - `market_snapshot`
  - `book_snapshot`
  - `book_delta`
  - `trade`
  - `order_snapshot`
  - `disconnect`
  - `reconnect`
  - `gap_detected`
  - `resolution_update`
- `market_id`
- `condition_id`
- `token_id`
- `claim_id`
- `underlying`
- `claim_family`
- `direction`
- `side`
- `price_tick`
- `price`
- `qty`
- `server_ts`
- `local_ts`
- `seq`
- `source`
- `order_id`
- `client_order_id`
- `raw_ref`
- `meta_json`

说明：
- `price_tick` 供 execution / LOB 使用
- `price` 供报表和人工阅读使用
- `claim_id` 允许后续直接 join factor tables

### E3. ClaimNode

建议字段：
- `claim_id`
- `market_id`
- `condition_id`
- `token_id`
- `title`
- `question`
- `underlying`
- `family`
  - `threshold`
  - `range_bucket`
  - `up_down_window`
  - `winner_take_all`
  - `binary_generic`
- `direction`
  - `bullish`
  - `bearish`
  - `neutral`
  - `discrete_outcome`
- `window_start_ts`
- `window_end_ts`
- `settle_ts`
- `lower_bound`
- `upper_bound`
- `threshold`
- `outcome_label`
- `settlement_rule_text`
- `rule_ambiguity_score`

### E4. ClaimEdge

建议字段：
- `edge_type`
  - `implies`
  - `mutually_exclusive`
  - `collectively_exhaustive`
  - `same_underlying_same_horizon`
  - `nearby_horizon`
  - `directional_support`
- `src_claim_id`
- `dst_claim_id`
- `weight`
- `reason`
- `strict`

### E5. FactorRow

所有因子层输出都要归一到这个形状。

建议字段：
- `run_id`
- `factor_family`
- `factor_name`
- `market_id`
- `token_id`
- `claim_id`
- `underlying`
- `asof_ts`
- `score`
- `edge_cents`
- `expected_profit_usd`
- `confidence`
- `liquidity_score`
- `capacity_usd`
- `rule_risk_score`
- `execution_dependency`
- `notes`

### E6. CandidateRow

join 输出统一为候选表。

建议字段：
- `candidate_id`
- `run_id`
- `market_id`
- `token_id`
- `claim_id`
- `underlying`
- `outcome`
- `join_mode`
- `ev_score`
- `wallet_score`
- `microstructure_score`
- `claim_graph_score`
- `execution_realism_score`
- `rule_penalty`
- `combined_score`
- `reject_reason`
- `accepted`

---

## F. 模块设计细化

## F1. utils 层

### 目标
统一当前散落在多个脚本中的重复逻辑。

### 需要抽出的重复功能
从当前脚本可见重复点：
- `safe_float`
- `safe_int`
- `parse_json_list`
- `http_get_json`
- `write_csv`
- `read_csv`
- ISO 时间转换
- Polymarket double-encoded JSON 解析
- 重试 / backoff

### 建议文件
- `scripts/polymarket/utils/http.py`
  - `http_get_json(...)`
  - `http_get_bytes(...)`
  - `retryable_get(...)`
- `scripts/polymarket/utils/io.py`
  - `read_csv_rows(...)`
  - `write_csv_rows(...)`
  - `write_json(...)`
  - `read_json(...)`
- `scripts/polymarket/utils/time.py`
  - `parse_iso_ts(...)`
  - `iso_ts(...)`
  - `now_utc_iso(...)`
- `scripts/polymarket/utils/text_parse.py`
  - `parse_json_list(...)`
  - `parse_money(...)`
  - `infer_symbol(...)`

### 第一收益
减少重复 bug，后续所有模块共享同一套解析行为。

---

## F2. ingest 层

### 目标
把“现抓现算”升级为“可缓存、可回放、可审计的数据输入”。

### 关键接口
- `fetch_gamma_markets(...)`
- `fetch_clob_book(token_id, ...)`
- `fetch_data_trades(...)`
- `save_raw_artifact(...)`

### 文件职责
- `gamma_fetch.py`
  - 市场发现、event/market metadata
- `clob_fetch.py`
  - book snapshots、maybe price history / best bid-ask
- `data_fetch.py`
  - public trades、open interest 等
- `cache_layout.py`
  - 统一 raw artifact 路径

### 建议 raw 存储布局
```text
output/polymarket/raw/
  gamma/YYYYMMDD/<run_id>/markets_page_001.json
  clob/YYYYMMDD/<run_id>/book_<token_id>.json
  data/YYYYMMDD/<run_id>/trades_page_001.json
```

### 注意事项
- 不要只保留“清洗后结果”，raw 一定要落盘
- 每个 raw 文件最好配 sidecar manifest

---

## F3. normalize 层

### 目标
把 raw API 响应转成研究统一输入，避免每个因子脚本自己重新 parse。

### 需要解决的问题
- Gamma 的字段很多是 JSON string inside JSON
- 不同 API 对时间、id、字段名不统一
- 同一个 token/market 在不同 API 中 key 体系不同

### 文件职责
- `event_schema.py`
  - schema 定义与字段校验
- `market_normalizer.py`
  - 把 gamma market/event 元数据映射成标准 market/claim 记录
- `trade_normalizer.py`
  - 把 public trades 映射成标准 trade events
- `book_normalizer.py`
  - 把 orderbook snapshot 映射为 normalized book events / top levels
- `validate_events.py`
  - event monotonicity、missing fields、id consistency 检查

### 输出物
- `normalized_markets.csv`
- `normalized_claims.csv`
- `normalized_trades.csv`
- `normalized_books.csv`
- `normalized_events.jsonl`

### 备注
早期可以只做 snapshot normalization，不急着做 websocket delta 流。

---

## F4. claims 层

### 目标
把“问题文本”升级为“结构化 claim”。

### 这是最关键的新能力
当前策略研究下一步最依赖这层，因为 token-level join 已经不够用。

### 需要识别的 claim family
1. threshold
   - `BTC above 64000 on June 9?`
2. range_bucket
   - `BTC price on June 9?` 某桶
3. up_down_window
   - `BTC Up or Down - 15m`
4. winner_take_all / NegRisk
   - exactly-one-winner family
5. binary_generic
   - 暂时不能结构化解析的二元 claim

### 核心文件
- `claim_model.py`
  - `ClaimNode`, `ClaimEdge`
- `claim_mapper.py`
  - question/description -> structured claim
- `claim_family_rules.py`
  - family-specific parse rules
- `claim_graph.py`
  - build graph
- `claim_consistency.py`
  - no-arb / implication / sum-to-one 检查

### 首批必须支持的规则
- `BTC > 66k` implies `BTC > 64k`
- 同一 winner-take-all 组内 mutually exclusive
- 同一 range bucket set sum(prob) ~= 1
- up/down short-window 只做 directional support，不强做 strict implication

### 输出物
- `claim_nodes.csv`
- `claim_edges.csv`
- `claim_graph.json`
- `claim_consistency_report.md`

---

## F5. factors 层

### 目标
让每种信号源独立演进，但都能统一 join。

### F5.1 EV family

#### 来源
- `scripts/polymarket_binance_close_signal_scan.py`
- `scripts/polymarket_binance_close_ensemble.py`

#### 重构目标
- 把 parsing / pricing / filtering / output 拆开

#### 建议文件
- `factors/ev_close.py`
  - 单 lookback、单 market fair prob
- `factors/ev_ensemble.py`
  - 多 lookback 合并、robust min gates

#### 输出物
- `output/polymarket/factors/ev/signals_<run_id>.csv`
- `output/polymarket/factors/ev/ensemble_<run_id>.csv`

### F5.2 wallet flow family

#### 来源
- `scripts/polymarket_wallet_factor_probe.py`
- `scripts/polymarket_delayed_copy_paper_strategy.py`
- `scripts/polymarket_delayed_copy_parameter_sweep.py`

#### 重构目标
拆成四层：
1. public trade ingestion
2. wallet scoring
3. market suitability
4. candidate generation

#### 建议文件
- `factors/wallet_flow.py`
- `factors/copyflow.py`

#### 输出物
- `wallet_scores.csv`
- `market_suitability.csv`
- `follow_candidates.csv`
- `trade_edges.csv`

### F5.3 microstructure family

#### 目标
将当前“spread/capacity/book_ok”这类字段升级为独立因子族。

#### 建议文件
- `factors/microstructure.py`
  - spread
  - depth
  - top-of-book imbalance
  - book freshness
- `factors/mlofi.py`
  - 后续接入 multi-level imbalance
- `factors/pin_proxy.py`
  - informed-flow proxy，不急着做学术版 PIN

#### 早期能做的最小因子
- `spread_cents`
- `available_notional_usd`
- `depth_1k_ok`
- `book_age_seconds`
- `extreme_price_flag`
- `crowd_exit_risk`

### F5.4 deterministic basket family

#### 来源
- `scripts/polymarket_range_basket_arbitrage_scan.py`
- `scripts/polymarket_negrisk_basket_arbitrage_scan.py`

#### 重构目标
把这类“结构性 no-arb / basket”研究也输出为标准 `FactorRow`。

#### 建议文件
- `factors/basket_range.py`
- `factors/basket_negrisk.py`

---

## F6. join 层

### 目标
统一组合逻辑，支持两代 join：
- token join（保留现有）
- claim join（下一代）

### 关键文件
- `token_join.py`
- `claim_join.py`
- `combined_score.py`
- `reject_reasons.py`
- `candidate_rank.py`

### token join 模式（兼容模式）
按：
- `token_id`
- `outcome`

### claim join 模式（新主线）
按：
- `underlying`
- `direction`
- `claim_family`
- `horizon proximity`
- `claim graph edges`

### combined_score 建议拆分
当前已有：
- ev_score
- smart_flow_score
- momentum_score
- microstructure_score
- rule_penalty

升级建议：
- `ev_score`
- `wallet_flow_score`
- `microstructure_score`
- `claim_graph_score`
- `execution_realism_score`
- `rule_penalty`
- `crowding_penalty`

### reject reasons 要标准化
建议枚举：
- `not_ev_candidate`
- `no_same_token_flow`
- `no_claim_level_confirmation`
- `opposite_claim_flow`
- `weak_microstructure`
- `execution_unrealistic`
- `high_rule_risk`
- `insufficient_capacity`
- `combined_score_too_low`

### 输出物
- `combined_candidates.csv`
- `combined_summary.json`
- `combined_summary.md`
- `reject_breakdown.csv`

---

## F7. execution 层

### 目标
把 CopyFlow 的 book replay 能力扩展成“通用执行现实性研究层”。

### 当前已有可复用基础
- `scripts/polymarket_copyflow_book_replay.py`
  - SQLite book store
  - nearest snapshot
  - VWAP fill
  - insufficient depth / no fresh book 检查
- `tests/test_polymarket_copyflow_forward.py`
  已经验证：
  - snapshot persist
  - nearest book retrieval
  - ask/bid VWAP fill
  - signal -> closed ledger

### 说明
这是当前最接近 execution layer 的真实内核，应优先抽模块，不应废弃。

### 建议文件
- `execution/book_store.py`
  - 抽出 SQLite schema / persist / query
- `execution/book_replay.py`
  - nearest snapshot / level retrieval
- `execution/fill_simulator.py`
  - VWAP fill / partial fill / max book age
- `execution/queue_model.py`
  - 先放接口，后续再加 maker queue model
- `execution/latency_model.py`
  - constant latency / stress latency tags
- `execution/realism_score.py`
  - 汇总 execution realism 标签

### 第一阶段不做什么
- 不做 live trading
- 不做复杂 maker FIFO queue 恢复
- 不强依赖 websocket delta 历史流

### 第一阶段先做什么
- 对所有 candidate 计算：
  - nearest book age
  - top-of-book spread
  - 1k / 5k / 10k VWAP fill feasibility
  - stale book risk
  - execution realism score

---

## F8. reports 层

### 目标
统一每次运行的研究产物。

### 必须有的 artifact
- `manifest.json`
- `summary.md`
- `summary.json`
- `*.csv`

### 推荐 run 目录结构
```text
output/polymarket/reports/<run_id>/
  manifest.json
  summary.md
  summary.json
  factors/
  joins/
  execution/
```

### manifest 建议字段
- `run_id`
- `started_at_utc`
- `finished_at_utc`
- `git_branch`（如可得）
- `source_scripts`
- `input_paths`
- `output_paths`
- `parameters`
- `counts`

---

## G. 从现有脚本到新模块的迁移映射

### G1. `polymarket_binance_close_signal_scan.py`

保留职责：
- CLI 入口
- 参数解析
- 调用 EV pipeline

迁移出去的内容：
- HTTP helper -> `utils/http.py`
- parse helper -> `utils/text_parse.py`
- market classification -> `claims/claim_mapper.py`
- fair-prob calculation -> `factors/ev_close.py`
- CSV writing -> `utils/io.py`

### G2. `polymarket_binance_close_ensemble.py`

保留职责：
- 组合多个 lookback run
- 输出汇总 artifact

迁移出去的内容：
- grouping/robust gates -> `factors/ev_ensemble.py`
- summary formatting -> `reports/summary.py`

### G3. `polymarket_wallet_factor_probe.py`

保留职责：
- CLI orchestration

迁移出去的内容：
- public trade fetch -> `ingest/data_fetch.py`
- market metadata build -> `normalize/market_normalizer.py`
- category/rule scoring -> `claims/claim_mapper.py` + `factors/wallet_flow.py`
- capacity/book stats -> `factors/microstructure.py`
- output writing -> `reports/tables.py`

### G4. `polymarket_copyflow_book_replay.py`

保留职责：
- CLI / self-test / backward compatibility

迁移出去的内容：
- schema -> `execution/book_store.py`
- fill -> `execution/fill_simulator.py`
- replay ledger -> `execution/book_replay.py`

### G5. `polymarket_combined_strategy_join.py`

保留职责：
- CLI 入口
- 兼容旧 token join mode

迁移出去的内容：
- score functions -> `join/combined_score.py`
- claim-aware matching -> `join/claim_join.py`
- reject reasons -> `join/reject_reasons.py`
- summary writing -> `reports/summary.py`

---

## H. 面向下一步策略研究的三条主线

### H1. 主线一：Claim-aware EV + wallet overlay

这是最优先主线。

目标：
- 不再要求 wallet flow 与 EV 必须同 token_id
- 允许通过 claim graph 做支持关系：
  - same underlying
  - same direction
  - nearby horizon
  - implication-compatible

最先支持的市场：
- BTCUSDT threshold close claims
- ETHUSDT threshold close claims
- BTC/ETH short-horizon up/down claims

### H2. 主线二：Execution realism tagging

目标：
- 候选不只看 edge，也看能不能拿到

最先支持：
- 1k/5k VWAP feasibility
- stale-book detection
- spread penalty
- depth insufficiency tag

### H3. 主线三：Deterministic basket / no-arb family

目标：
- 把 range buckets / NegRisk 候选纳入同一框架
- 作为与 EV family 并列的研究支线

---

## I. 分阶段实施计划（真正可执行）

### Phase 0：文档/接口冻结（半天到 1 天）

**Objective:** 冻结统一数据模型与目录约定，避免后续返工。

**Files:**
- Create: `docs/markets/onchain/polymarket-normalized-event-spec.md`
- Create: `docs/markets/onchain/polymarket-claim-graph-spec.md`
- Create: `docs/markets/onchain/polymarket-execution-research-spec.md`

**Deliverables:**
- event schema 文档
- claim graph 文档
- execution realism 文档

**Validation:**
- 所有后续模块都能引用这三份 spec

### Phase 1：抽 utils / io / http 公共层（1 天）

**Objective:** 先消除重复工具代码。

**Files likely to change:**
- Create: `scripts/polymarket/utils/*.py`
- Modify: `scripts/polymarket_binance_close_signal_scan.py`
- Modify: `scripts/polymarket_wallet_factor_probe.py`
- Modify: `scripts/polymarket_copyflow_book_replay.py`

**Validation:**
- 现有 3 个核心脚本行为不变
- 现有 tests 继续通过

### Phase 2：抽 execution 内核（1 天）

**Objective:** 把 copyflow book replay 升级为通用 execution package。

**Files likely to change:**
- Create: `scripts/polymarket/execution/book_store.py`
- Create: `scripts/polymarket/execution/fill_simulator.py`
- Create: `scripts/polymarket/execution/book_replay.py`
- Modify: `scripts/polymarket_copyflow_book_replay.py`
- Modify: `tests/test_polymarket_copyflow_forward.py`

**Validation:**
- 现有 `test_polymarket_copyflow_forward.py` 仍通过
- 新模块可直接被 import 使用

### Phase 3：建立 claim mapper / claim graph（1-2 天）

**Objective:** 让 threshold / range / up-down 首批进入统一 claim 结构。

**Files likely to change:**
- Create: `scripts/polymarket/claims/*.py`
- Create: `tests/test_polymarket_claim_mapper.py`
- Create: `tests/test_polymarket_claim_graph.py`

**Validation:**
- BTC/ETH threshold examples 可成功 map
- implication edges 正确生成
- range buckets 可标记为 mutually exclusive / exhaustive

### Phase 4：重构 EV family（1 天）

**Objective:** 让 EV 输出标准 `FactorRow`。

**Files likely to change:**
- Create: `scripts/polymarket/factors/ev_close.py`
- Create: `scripts/polymarket/factors/ev_ensemble.py`
- Modify: `scripts/polymarket_binance_close_signal_scan.py`
- Modify: `scripts/polymarket_binance_close_ensemble.py`
- Modify: `tests/test_polymarket_binance_close_ensemble.py`

**Validation:**
- 旧输出还能产出
- 新输出包含 `claim_id`

### Phase 5：重构 wallet/microstructure family（1-2 天）

**Objective:** wallet flow、book stats、capacity、rule ambiguity 标准化。

**Files likely to change:**
- Create: `scripts/polymarket/factors/wallet_flow.py`
- Create: `scripts/polymarket/factors/microstructure.py`
- Modify: `scripts/polymarket_wallet_factor_probe.py`

**Validation:**
- `wallet_scores.csv`
- `market_suitability.csv`
- `follow_candidates.csv`
  继续产出，且每行带 `claim_id`

### Phase 6：实现 claim join（1 天）

**Objective:** 在保留 token join 的同时，新增 claim-aware join。

**Files likely to change:**
- Create: `scripts/polymarket/join/*.py`
- Modify: `scripts/polymarket_combined_strategy_join.py`
- Create: `tests/test_polymarket_claim_join.py`

**Validation:**
- 支持 `--join-mode token`
- 支持 `--join-mode claim`
- 输出 reject reason breakdown

### Phase 7：统一 run artifacts / reports（半天到 1 天）

**Objective:** 所有研究运行进入同一 artifact 结构。

**Files likely to change:**
- Create: `scripts/polymarket/reports/*.py`
- Modify: 各 CLI 脚本

**Validation:**
- 每次运行自动写 manifest / summary / tables

---

## J. 每一阶段的测试策略

### J1. 单元测试

先补这些最小测试：
- `test_safe_float_and_parse_json_list`
- `test_claim_mapper_threshold_market`
- `test_claim_mapper_up_down_market`
- `test_claim_graph_implication_edges`
- `test_ev_factor_row_contains_claim_id`
- `test_wallet_factor_rows_contain_claim_id`
- `test_claim_join_accepts_related_claim_support`
- `test_fill_simulator_flags_insufficient_depth`

### J2. 回归测试

保留现有核心回归：
- `tests/test_polymarket_binance_close_ensemble.py`
- `tests/test_polymarket_combined_strategy_join.py`
- `tests/test_polymarket_copyflow_forward.py`

### J3. Golden artifact 测试

建议为 claim mapping / join 增加小型固定输入夹具：
- synthetic BTC threshold market
- synthetic BTC up/down market
- synthetic range bucket family
- synthetic winner-take-all family

---

## K. 下一步策略研究将如何受益

完成这次系统化后，下一步研究就能自然升级为：

### K1. 从 token-level join 升级到 claim-level join

可以研究：
- “短周期 BTC Up flow 是否支持日内 close-threshold claim？”
- “range buckets 与 threshold claims 是否存在 implied CDF 不一致？”
- “同一 underlying 上多个 claim family 是否给出一致方向？”

### K2. 从静态 edge 升级到 execution-aware edge

可以研究：
- “这个 edge 在 1k / 5k notional 下是否还能成立？”
- “同样的 candidate，在 stale book 风险下是否该降权？”

### K3. 从单策略脚本升级到可比较研究平台

可以直接比较：
- EV-only
- EV + wallet
- EV + claim graph
- EV + microstructure
- EV + wallet + claim graph + execution realism

---

## L. 风险与取舍

### L1. 不要一开始就做太复杂的 live-grade engine

当前目标是研究系统，不是交易系统。
所以先做：
- snapshot-based execution realism
- claim-aware join
- factor normalization

而不是：
- 全量 websocket engine
- 真正下单器
- 复杂 maker queue 恢复

### L2. 不要一次性迁移全部脚本

优先顺序应是：
1. execution 内核抽取
2. claim graph
3. EV / wallet 标准化
4. join 升级
5. 报表统一

### L3. claim mapping 要允许 unknown family

不要因为无法完美解析所有市场，就卡住系统。
先支持：
- threshold
- range bucket
- up/down window
- winner-take-all

其余暂时落 `binary_generic`。

---

## M. 最终验收标准

当以下条件都满足时，说明蓝图已真正“支持下一步策略研究”：

1. 任一候选都可以追溯到：
   - raw artifact
   - normalized claim
   - factor rows
   - join decision
   - execution realism tags

2. 同一 underlying 的不同 claim family 可以一起研究
   - threshold
   - range bucket
   - up/down

3. 现有脚本仍可跑
   - 不牺牲当前研究连续性

4. 新输出具备统一格式
   - `claim_id`
   - `run_id`
   - `manifest`
   - `summary`

5. 新 join 能解释“为什么接受/拒绝”
   - 不只是一个分数

---

## N. 建议的第一批具体交付件

按研究价值排序，建议先完成这 6 个交付件：

1. `scripts/polymarket/execution/book_store.py`
2. `scripts/polymarket/execution/fill_simulator.py`
3. `scripts/polymarket/claims/claim_mapper.py`
4. `scripts/polymarket/claims/claim_graph.py`
5. `scripts/polymarket/join/claim_join.py`
6. `docs/markets/onchain/polymarket-claim-graph-spec.md`

这是因为它们直接支撑：
- claim-aware 组合研究
- execution-aware 候选评估

---

## O. 实施建议（给下一轮执行）

执行时不要按“模块大章”推进，而要按“最小可验证切片”推进：

推荐切片顺序：
1. 抽 execution SQLite/store，不改行为
2. 抽 VWAP fill simulator，不改行为
3. 为 threshold 市场建立 claim mapper
4. 为 threshold claims 建 implication graph
5. 把 EV rows 带上 claim_id
6. 把 wallet rows 带上 claim_id
7. 在 combined join 中新增 `--join-mode claim`
8. 给 claim join 增加 reject reason 输出
9. 统一 report manifest

每一步都应配测试并保持旧脚本可运行。

---

## P. 结论

这次系统化重构的核心，不是把 Polymarket 研究“工程化得更漂亮”，而是把研究对象从“单 token 机会”升级为“结构化 claims 组合机会”，同时把 execution realism 显式纳入研究闭环。

如果按这个蓝图落地，下一步你就能系统研究：
- claim-level EV 与 flow 的一致性
- 跨 claim family 的 directional support
- execution-constrained candidate ranking
- range/NegRisk/no-arb 与 threshold EV 的统一比较

这将明显比当前“脚本并列 + token 精确 join”的形态更适合进入更深的策略研究阶段。

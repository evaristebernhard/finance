# Polymarket 研究系统重构蓝图

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 将当前分散的 Polymarket 研究脚本重构成“数据层 → claim/market 规范层 → 因子层 → 组合/回放层 → 验证层”的模块化研究系统。

**Architecture:** 以 claim graph 为主索引、以 normalized event 为统一数据接口、以 book-aware execution 为约束层。现有脚本先不推翻重写，而是按能力拆分：采集/规范化、EV、wallet flow、microstructure、claim graph join、回放与验证。最终所有策略输出统一落到可追踪的 CSV/JSON/Markdown artifact。

**Tech Stack:** Python 3.12, CSV/JSON/Parquet, Polymarket public APIs, existing scripts/tests, local output artifacts.

---

## 0. 当前基线（保留不动）

现有可复用资产：
- `scripts/polymarket_binance_close_signal_scan.py`
- `scripts/polymarket_binance_close_ensemble.py`
- `scripts/polymarket_wallet_factor_probe.py`
- `scripts/polymarket_combined_strategy_join.py`
- `scripts/polymarket_copyflow_collect.py`
- `scripts/polymarket_copyflow_book_replay.py`
- `scripts/polymarket_delayed_copy_paper_strategy.py`
- `scripts/polymarket_range_basket_arbitrage_scan.py`
- `scripts/polymarket_negrisk_basket_arbitrage_scan.py`
- `tests/test_polymarket_*.py`
- `docs/markets/onchain/polymarket-*.md`

当前已知问题：
- token_id 级 join 太严格，wallet flow 和 EV 经常不在同一 token 上。
- 缺少统一的 normalized event schema。
- 缺少 claim graph / underlying graph。
- 缺少 book-aware fill simulation 的统一出口。
- 缺少单一 research artifact 目录约定。

---

## 1. 目标目录结构

建议新增/整理为以下模块：

```text
scripts/polymarket/
  ingest/
  normalize/
  claims/
  factors/
  join/
  execution/
  reports/
  utils/

docs/markets/onchain/
  polymarket-research-system-blueprint.md
  polymarket-claim-graph-spec.md
  polymarket-normalized-event-spec.md

output/polymarket/
  raw/
  normalized/
  claims/
  factors/
  joins/
  execution/
  reports/

tests/
  test_polymarket_normalize_*.py
  test_polymarket_claim_graph_*.py
  test_polymarket_execution_*.py
```

如果暂时不想重排目录，也可以先保留当前顶层脚本，但内部按上述模块拆分成导入层。

---

## 2. 模块蓝图

### 2.1 ingest：原始数据接入

职责：
- 拉取 Gamma / CLOB / Data API 数据
- 保存 raw response
- 统一缓存策略
- 为后续 normalize 提供输入

建议文件：
- `scripts/polymarket/ingest/gamma_fetch.py`
- `scripts/polymarket/ingest/clob_fetch.py`
- `scripts/polymarket/ingest/data_fetch.py`
- `scripts/polymarket/ingest/cache_layout.py`

输出目录：
- `output/polymarket/raw/gamma/`
- `output/polymarket/raw/clob/`
- `output/polymarket/raw/data/`

关键数据：
- market discovery response
- orderbook snapshot
- trades
- resolution / status metadata

---

### 2.2 normalize：统一事件规范

职责：
- 把 raw API 响应变成统一事件流
- 保留 local_ts / server_ts / seq / source
- 记录 gap / disconnect / snapshot_reload
- 生成可 replay 的 parquet/csv/jsonl

建议文件：
- `scripts/polymarket/normalize/event_schema.py`
- `scripts/polymarket/normalize/market_normalizer.py`
- `scripts/polymarket/normalize/book_normalizer.py`
- `scripts/polymarket/normalize/trade_normalizer.py`
- `scripts/polymarket/normalize/validate_events.py`

建议 event schema：
- `event_type`
- `market_id`
- `condition_id`
- `token_id`
- `underlying`
- `claim_family`
- `direction`
- `side`
- `price_tick`
- `qty`
- `server_ts`
- `local_ts`
- `seq`
- `source`
- `order_id`
- `client_order_id`
- `raw_ref`

输出目录：
- `output/polymarket/normalized/events/`
- `output/polymarket/normalized/books/`
- `output/polymarket/normalized/trades/`

---

### 2.3 claims：claim 规范层 / 图结构层

职责：
- 把 market 映射到 claim family
- 建立 underlying、direction、horizon、threshold/range 的统一描述
- 构建 implication / mutual exclusion / equivalence 图
- 让 token-level 研究升级为 claim-level 研究

建议文件：
- `scripts/polymarket/claims/claim_model.py`
- `scripts/polymarket/claims/claim_graph.py`
- `scripts/polymarket/claims/claim_mapper.py`
- `scripts/polymarket/claims/claim_consistency.py`

建议核心对象：
- `ClaimNode`
  - `claim_id`
  - `underlying`
  - `family`
  - `direction`
  - `horizon`
  - `lower_bound`
  - `upper_bound`
  - `token_id`
- `ClaimEdge`
  - `A => B`
  - `A xor B`
  - `A + B = 1`
  - `A overlaps B`

输出目录：
- `output/polymarket/claims/claim_graph.json`
- `output/polymarket/claims/claim_map.csv`
- `output/polymarket/claims/claim_edges.csv`

---

### 2.4 factors：EV / wallet / microstructure 因子层

职责：
- 每类因子独立产出可 join 的标准表
- 统一字段命名
- 统一置信度与风险标签

建议拆分：
- `scripts/polymarket/factors/binance_close_ev.py`
- `scripts/polymarket/factors/wallet_flow.py`
- `scripts/polymarket/factors/microstructure.py`
- `scripts/polymarket/factors/mlofi.py`
- `scripts/polymarket/factors/pin_proxy.py`
- `scripts/polymarket/factors/vol_regime.py`

对应现有脚本迁移关系：
- `polymarket_binance_close_signal_scan.py` → EV base
- `polymarket_binance_close_ensemble.py` → EV ensemble
- `polymarket_wallet_factor_probe.py` → wallet_flow
- `polymarket_copyflow_*` → wallet/copyflow family
- `polymarket_range_basket_arbitrage_scan.py` / `polymarket_negrisk_basket_arbitrage_scan.py` → deterministic basket family

标准输出字段建议：
- `market_id`
- `token_id`
- `claim_id`
- `factor_name`
- `factor_score`
- `factor_edge`
- `factor_confidence`
- `liquidity_score`
- `rule_risk_score`
- `capacity_usd`
- `notes`

输出目录：
- `output/polymarket/factors/ev/`
- `output/polymarket/factors/wallet/`
- `output/polymarket/factors/microstructure/`

---

### 2.5 join：组合与筛选层

职责：
- 把 EV、wallet、momentum、microstructure、claim graph 合并
- 输出统一 candidate 表
- 支持 token-level join 与 claim-level join 两种模式

建议文件：
- `scripts/polymarket/join/token_join.py`
- `scripts/polymarket/join/claim_join.py`
- `scripts/polymarket/join/combined_score.py`
- `scripts/polymarket/join/reject_reasons.py`

建议把当前 `scripts/polymarket_combined_strategy_join.py` 拆成：
- 读取层
- score 计算层
- reject reason 层
- report 层

建议 join 模式：
- `exact_token`
- `same_underlying_same_direction`
- `claim_implication`
- `horizon_nearby`

输出目录：
- `output/polymarket/joins/token_join/`
- `output/polymarket/joins/claim_join/`

---

### 2.6 execution：book-aware 研究执行层

职责：
- 不做真实下单，只做可执行性评估
- 估计 fill probability / slippage / queue wait / cancel miss
- 为候选打上 execution realism 标签

建议文件：
- `scripts/polymarket/execution/book_simulator.py`
- `scripts/polymarket/execution/queue_model.py`
- `scripts/polymarket/execution/latency_model.py`
- `scripts/polymarket/execution/fill_report.py`

建议最小模型：
- 保守队列模型
- 概率队列模型
- taker depth consumption
- IOC / partial fill / slippage cap

输出目录：
- `output/polymarket/execution/fill_reports/`
- `output/polymarket/execution/latency_sweeps/`

---

### 2.7 reports：研究报告层

职责：
- 将每次研究运行输出 markdown/json/csv 总结
- 固定报表结构，便于对比版本

建议文件：
- `scripts/polymarket/reports/write_summary.py`
- `scripts/polymarket/reports/write_tables.py`
- `scripts/polymarket/reports/write_dashboard_links.py`

建议报告类型：
- EV ensemble report
- wallet probe report
- claim join report
- execution realism report
- final candidate report

输出目录：
- `output/polymarket/reports/<run_id>/summary.md`
- `output/polymarket/reports/<run_id>/summary.json`
- `output/polymarket/reports/<run_id>/*.csv`

---

## 3. 推荐数据流

```text
raw API / websocket
  -> ingest
  -> normalized events
  -> claim mapper
  -> factor builders
  -> token join / claim join
  -> execution realism filters
  -> report artifacts
```

核心原则：
- 因子和执行分离
- claim 作为第一类索引
- token_id 只是实现细节，不是研究主索引

---

## 4. 现有脚本的重构建议

### 保留为入口层
- `scripts/polymarket_binance_close_ensemble.py`
- `scripts/polymarket_combined_strategy_join.py`
- `scripts/polymarket_wallet_factor_probe.py`

### 逐步拆分为库函数
- 把纯计算逻辑搬到 `scripts/polymarket/*/*.py`
- CLI 只负责参数解析、文件路径、调用、输出

### 现有测试的迁移方向
- `tests/test_polymarket_binance_close_ensemble.py`
- `tests/test_polymarket_combined_strategy_join.py`
- `tests/test_polymarket_copyflow_forward.py`

新增测试建议：
- `tests/test_polymarket_claim_graph.py`
- `tests/test_polymarket_normalize_events.py`
- `tests/test_polymarket_execution_model.py`

---

## 5. 建议的第一阶段落地顺序

### Task 1：定义 normalized event schema
- 先写 schema 文档
- 再写校验函数
- 再让一个最小脚本输出标准事件

### Task 2：定义 claim graph
- 先建立 claim node / edge 数据结构
- 再把现有 BTC/ETH threshold 市场映射进去
- 再输出 claim join 的可用索引

### Task 3：把 combined join 改成 claim-aware join
- 保留 token join
- 新增 claim join
- 把 reject reason 拆成 claim-level 解释

### Task 4：加 execution realism filter
- 先做保守 fill/latency 模型
- 只给候选加标，不直接过滤掉太多信号

### Task 5：统一报告目录
- 每次 run 都写入 `output/polymarket/reports/<run_id>/`
- 保证复盘可追踪

---

## 6. 验证标准

重构成功的最低标准：
- 任意一个候选都能追溯到：原始市场 → normalized event → claim node → factor rows → join decision → execution assumption
- token-level 和 claim-level 的结果能并存比较
- 报表能解释 reject reason，而不是只给一个分数
- 新加入的 claim graph 不破坏现有 EV / wallet 脚本

---

## 7. 主要风险

- claim 映射规则如果过度手工化，会引入主观偏差
- 过早做复杂 execution simulation 可能拖慢研究节奏
- 如果 schema 不先统一，后面所有 join 都会越来越脆弱
- 现有脚本很多是可运行原型，重构时要避免一次性大改导致研究中断

---

## 8. 结论

这套重构的核心不是“把脚本变多”，而是把研究对象从 token 级别提升到 claim 级别，并把执行约束显式化。最终你要的是一个可重复、可解释、可比较的 Polymarket 研究系统，而不是一堆彼此独立的扫描器。

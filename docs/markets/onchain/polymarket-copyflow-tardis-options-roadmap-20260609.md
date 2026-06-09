# Polymarket CopyFlow + Tardis/Options/Price-Structure Strategy Roadmap

Date: 2026-06-09

Scope: 在已有 Polymarket CopyFlow 回测基础上，设计下一步数据工程与可叠加策略因子。重点包括：持续采集、historical CLOB VWAP 回测、crypto/up-down 独立 EV gate、Tardis 期权结构、价格结构、basket/NegRisk 结构。

边界：只读研究与 forward paper；不读取私钥、不签名、不下单。

## 1. 当前项目里已经有的资产

### 1.1 Polymarket CopyFlow 线

已有脚本：

```text
scripts/polymarket_wallet_factor_probe.py
scripts/polymarket_delayed_copy_paper_strategy.py
scripts/polymarket_delayed_copy_parameter_sweep.py
```

已完成 deep 回测报告：

```text
docs/markets/onchain/polymarket-copyflow-backtest-20260608.md
```

核心发现：

```text
copy > fade
entry_delay=30s, exit_delay=300s 是当前样本最稳结构
edge 主要集中在 crypto/up-down 类型市场
当前 fill 是 next-trade proxy，不是 historical CLOB VWAP
```

### 1.2 Polymarket crypto-close 独立 EV 线

已有脚本：

```text
scripts/polymarket_binance_close_signal_scan.py
scripts/polymarket_binance_close_settlement_verify.py
```

作用：

```text
解析 Polymarket crypto close/up-down/range 市场
用 Binance 价格和短期 realized volatility 建简单 fair probability
比较 CLOB ask 与 model probability
settlement 后用 Binance 1m close 验证 paper PnL
```

这条线可以作为 CopyFlow 的 independent EV gate。

### 1.3 Polymarket basket/结构套利线

已有脚本：

```text
scripts/polymarket_range_basket_arbitrage_scan.py
scripts/polymarket_negrisk_basket_arbitrage_scan.py
```

作用：

```text
range basket: 买所有 YES 或所有 NO，检查互斥区间价格是否偏离
NegRisk basket: 多结果事件中买所有 YES，检查 fee-adjusted edge
```

这不是跟单策略，但可以做 portfolio layer 或 signal quality layer：如果某事件整体 basket 已经 mispriced，CopyFlow 进入该事件时的含义和风险不同。

### 1.4 Tardis/Deribit 期权结构线

已有 Rust 下载器：

```text
crates/btc_research/src/bin/tardis_deribit_snapshot_fetch.rs
crates/btc_research/src/tardis_deribit.rs
```

已有 Python regime 报告：

```text
scripts/btc_options_regime_report.py
docs/markets/btc/v1-options-regime-report.md
```

Tardis key 现有权限文档：

```text
docs/markets/mon-usdc/v1-tardis-access.md
```

已记录权限：

```text
deribit academic 2025-04-11 -> 2026-07-12
bybit-options academic 2025-04-11 -> 2026-07-12
binance-european-options academic 2025-04-11 -> 2026-07-12
okex-options academic 2025-04-11 -> 2026-07-12
huobi-dm-options academic 2025-04-11 -> 2026-07-12
bullish academic 2026-04-29 -> 2026-07-12
```

当前没有：

```text
binance-futures historical data-feed 权限
```

所以 Tardis 目前最适合补：

```text
BTC/ETH/major crypto options surface
market-wide risk regime
short-horizon implied move / skew / term structure
```

不适合直接补 Binance futures 历史 L2，除非之后购买对应权限。

## 2. CopyFlow 必须先升级的数据工程

### 2.1 持续采集器

建议新增：

```text
scripts/polymarket_copyflow_collect.py
```

保存到：

```text
data/polymarket/copyflow_v1/polymarket_copyflow.sqlite
```

或者先写到：

```text
output/polymarket_copyflow_forward_<date>/
```

注意：项目 AGENTS.md 说不要修改 `data/`，所以初版建议先写 `output/`。等确认长期采集再迁到 `data/`。

采集频率：

```text
recent trades: every 30s
tracked wallet activity: every 30-60s
candidate CLOB books: every 10-30s for active candidate assets
Gamma market metadata: every 5-15m
```

核心表：

```text
trades_raw
wallet_activity_raw
markets_raw
asset_books
asset_book_levels
tracked_wallets
collector_state
```

关键字段：

```text
ingest_ts_utc
source_ts_utc
condition_id
asset/token_id
wallet
side
outcome
price
size
tx_hash/order_id if available
book_bid/ask levels
market slug/title/category/end_ts/rules
```

### 2.2 Historical CLOB VWAP 回测器

建议新增：

```text
scripts/polymarket_copyflow_book_replay.py
```

把当前：

```text
entry = next_public_trade_price + cost
exit = next_public_trade_price - cost
```

升级为：

```text
entry_time = signal_time + entry_delay
entry = ask VWAP from historical book snapshot near entry_time
exit_time = signal_time + exit_delay
exit = bid VWAP from historical book snapshot near exit_time
```

必要 guard：

```text
max_book_age_seconds <= 10 or 30
max_slippage_cents
min_bid_ask_depth_usd
market/wallet/asset notional caps
no future book leakage
```

输出：

```text
paper_ledger.csv
book_fill_diagnostics.csv
skip_reasons.csv
summary.json
summary.md
```

### 2.3 Forward paper runner

建议新增：

```text
scripts/polymarket_copyflow_forward_paper.py
```

逻辑：

```text
1. 每次新 wallet BUY signal 进入队列
2. 到 entry_time 查历史 book snapshot 做 paper fill
3. 到 exit_time 查历史 book snapshot 做 paper exit
4. 到 settlement 后可再做 resolved PnL 验证
5. 每日输出策略状态和 PnL
```

这个是进入 live dry-run 前的必要阶段。

## 3. 可以叠加的策略内容

### 3.1 期权结构：Tardis Deribit options regime gate

这是最值得加的外部数据层。

已有 `btc_options_regime_report.py` 能构造：

```text
atm_iv
skew_25d
term_slope
term_stress
iv_richness_12h
iv_rv_ratio_12h
implied_move_12h_bps
vol_premium_gap_12h_bps
atm_iv_change_1h
skew_25d_change_1h
term_slope_change_1h
compression_rel_to_rv_6h
```

用于 Polymarket crypto/up-down 的方式：

#### A. Volatility gate

如果 Polymarket 是 BTC/ETH/SOL/XRP 的 close/up-down/range 市场，价格是否会跨 threshold 很大程度由短期波动决定。

可做：

```text
if implied_move_to_threshold_ratio is too low:
    reject CopyFlow long-shot buys
if IV rising + term_stress high:
    allow breakout/up-down flow with wider target
if IV/RV too rich and realized compressed:
    downweight chasing late wallet flow
```

核心变量：

```text
distance_to_threshold_bps = abs(log(threshold / spot)) * 10000
implied_move_to_threshold = implied_move_horizon_bps / distance_to_threshold_bps
rv_move_to_threshold = trailing_rv_horizon_bps / distance_to_threshold_bps
```

#### B. Directional skew gate

Skew 不是直接预测方向，但能表达 tail demand。

可做：

```text
BTC/ETH put skew rising -> down/up market中的 DOWN side CopyFlow 更可信
call wing bid rising or skew flattening -> UP side CopyFlow 更可信
skew 与 CopyFlow 方向冲突 -> 降仓或过滤
```

#### C. Event risk / term-structure gate

近端 IV 明显高于远端：

```text
term_stress = front_atm_iv - next_atm_iv
```

如果 term_stress 极高，说明短期事件风险或行情压力强：

```text
适合：短时 up/down/range breakout 类 Polymarket
不适合：低价差的小 edge 机械跟单
```

#### D. Vol compression breakout

已有报告里有：

```text
compressed_range_6h
compression_rel_to_rv_6h
```

可做：

```text
价格压缩 + IV/term 开始上行 + wallet flow 同向
=> CopyFlow 加分
价格已经释放大波动 + IV 回落
=> CopyFlow 减分，避免追尾
```

### 3.2 价格结构：Binance/underlying close-market EV gate

已有 `polymarket_binance_close_signal_scan.py` 使用简化 lognormal/短期波动模型。

下一步应增强成：

```text
scripts/polymarket_crypto_close_ev_panel.py
```

因子：

```text
spot_to_threshold_bps
minutes_to_settle
realized_vol_15m/1h/3h/6h/12h
trend_15m/1h/3h
range_position_6h
micro_momentum_5m
distance_to_liquidation/round-number level
prob_model_yes
model_edge_cents = prob_model_side - ask_price - fee/slippage
```

CopyFlow 入场 gate：

```text
only enter if:
  CopyFlow prior edge positive
  model_edge_cents > threshold
  market book VWAP executable
  no rule ambiguity
```

这比纯跟单更合理。

### 3.3 Polymarket event structure / basket layer

已有 basket scanners 可以变成结构过滤器。

#### A. Range basket arbitrage

对于 “BTC price on date?” 这种多区间事件：

```text
sum(YES asks) < 1 - fee buffer => all-YES basket positive
sum(NO asks) < N-1 - fee buffer => all-NO basket positive
```

用途：

```text
直接结构套利候选
或 CopyFlow 的 event-level mispricing context
```

#### B. NegRisk basket

对互斥多结果事件：

```text
buy all YES cost < 1 payout
```

用途：

```text
低方向风险结构机会
也能识别某事件整体价格是否混乱
```

#### C. Conditional complement check

二元市场应近似：

```text
YES ask + NO ask >= 1 + fees
YES bid + NO bid <= 1 - fees
```

偏离可用于：

```text
market quality score
execution sanity check
avoid bad books
```

### 3.4 Cross-market probability consistency

对同一标的/同一 settle time，Polymarket 常有：

```text
above X
below X
range A-B
up/down
```

可以构造一条 implied CDF：

```text
P(S_T > K) from above markets
P(A <= S_T < B) from range markets
```

检查：

```text
monotonicity violation
range mass negative or too large
CDF jump inconsistency
Polymarket implied vol vs Deribit implied vol
```

这比单独看某个钱包更稳。

策略用途：

```text
若 CopyFlow 买入的 bucket 同时被 CDF consistency 支持 -> 加分
若 CopyFlow 买入导致 local CDF 明显扭曲 -> 可能 fade or avoid
```

### 3.5 Wallet flow 的二阶内容

不要只看单个钱包买了什么，可以加：

```text
wallet_cluster_consensus: 多个高质量 wallet 是否同向
leader_lag: wallet A 后 wallet B 是否跟随
crowding_score: 同一资产短时是否过多 smart wallets 同向
flow_acceleration: 最近 5m/15m smart wallet net buy 是否加速
wallet_specialization_match: wallet 历史强项 category 是否匹配当前市场
```

入场逻辑从：

```text
某 wallet 买 -> 跟
```

改成：

```text
CopyFlow score + independent EV + event structure + book execution + regime
```

### 3.6 盘口/微观结构内容

Polymarket CLOB 本身可做：

```text
spread_cents
depth_100/500/1000 USD
book_imbalance
bid/ask replenishment
quote age
book volatility
VWAP slippage curve
```

Tardis 如果之后有 futures L2 权限，可以补 underlying microstructure：

```text
underlying order flow imbalance
basis/perp funding context
liquidation-like burst proxy
trade intensity spike
```

但当前 Tardis 权限没有 Binance futures historical feed，所以这块短期应靠 Binance public/live 或自建采集。

## 4. 推荐策略优先级

### Priority 1: CopyFlow + book-aware forward paper

目标：证明当前 +4% 到 +10% proxy edge 在真实 book VWAP 下是否还存在。

实现：

```text
polymarket_copyflow_collect.py
polymarket_copyflow_book_replay.py
polymarket_copyflow_forward_paper.py
```

判定标准：

```text
>= 1-2 周 forward paper
>= 100 closed paper trades
positive after VWAP/slippage/fee
copy still > fade
PnL not dominated by one wallet or one event
```

### Priority 2: CopyFlow + crypto close EV gate

目标：只交易 wallet flow 和独立价格模型都支持的 crypto/up-down/range 市场。

复用：

```text
polymarket_binance_close_signal_scan.py
polymarket_binance_close_settlement_verify.py
```

新增：

```text
polymarket_crypto_close_ev_panel.py
```

判定标准：

```text
CopyFlow-only vs EV-only vs CopyFlow+EV 三组 forward paper
组合组应提高 PF、降低 drawdown、减少弱交易
```

### Priority 3: Tardis options regime gate

目标：用 BTC/ETH options surface 判断当前 Polymarket crypto flow 是“值得追”还是“容易被波动/价差吃掉”。

复用：

```text
cargo run -p btc_research --bin tardis_deribit_snapshot_fetch -- ...
python scripts/btc_options_regime_report.py -- ...
```

新增：

```text
scripts/tardis_options_regime_panel.py
scripts/polymarket_copyflow_join_options_regime.py
```

优先因子：

```text
iv_rv_ratio_horizon
implied_move_to_threshold
term_stress
skew_25d_change_1h
compression_rel_to_rv_6h
```

### Priority 4: Basket/structure arbitrage and CDF consistency

目标：找低方向风险结构机会，或给 CopyFlow 市场打 event-level quality score。

复用：

```text
polymarket_range_basket_arbitrage_scan.py
polymarket_negrisk_basket_arbitrage_scan.py
```

新增：

```text
scripts/polymarket_crypto_event_cdf_consistency.py
```

判定标准：

```text
发现可执行 basket edge
或证明 CDF consistency score 能过滤 CopyFlow 差交易
```

## 5. 具体组合策略草案

### Strategy A: CopyFlow + EV Gate

```text
candidate = wallet BUY signal
if wallet_prior_edge <= 0: reject
if wallet_prior_trades < 5: reject
if book_vwap_edge <= min_edge: reject
if crypto_close_model_edge <= 1.5c: reject
if market_rule_ambiguity high: reject
stake = base * wallet_quality * min(model_edge/5c, 2)
exit = 300s book VWAP or settlement depending market type
```

适合：

```text
BTC/ETH/SOL/XRP up/down/above/below/range close markets
```

### Strategy B: Options-Regime-Gated CopyFlow

```text
candidate = CopyFlow signal on BTC/ETH market
join nearest Deribit options regime state
if implied_move_to_threshold < 0.8 and side is OTM breakout: reject
if term_stress high and flow direction aligns with skew/trend: allow
if IV/RV extreme rich and no price momentum: reduce stake
```

适合：

```text
短到中等 horizon crypto close markets
```

### Strategy C: Event-Structure First, CopyFlow Second

```text
scan event basket/CDF consistency
find underpriced bucket or inconsistent CDF segment
if high-quality wallet flow enters same bucket/side within window:
    paper enter
else:
    just alert/no trade
```

适合：

```text
多区间 range markets
NegRisk/multi-outcome events
```

### Strategy D: Smart-Wallet Consensus, not Single-Wallet Follow

```text
score(asset, 5m) = weighted net buy from eligible wallets
weights = wallet prior edge * specialization * decay robustness * anti-one-hit
enter only when:
  consensus_score high
  no crowding blowoff
  EV gate positive
  book capacity ok
```

适合：

```text
减少单钱包 lucky trade 和 hidden hedge 风险
```

## 6. 实施顺序

### Week 0: 工程基础

1. 新增 CopyFlow forward collector，先写 output/。
2. 保存 CLOB book snapshots 和 trades/activity 去重状态。
3. 写 historical CLOB VWAP fill 函数。
4. 加 self-test：book VWAP、多档消耗、no-future-leakage。

### Week 1: Forward paper

1. 每 30-60 秒跑 collector。
2. 每 5 分钟跑 paper updater。
3. 每日输出：copy/fade、EV-gated、non-gated 对照。
4. 不做 live。

### Week 2: EV gate

1. 把 crypto close scanner 输出改成 reusable panel。
2. 对每个 CopyFlow signal join 最近 EV state。
3. 回测/forward 对比 CopyFlow-only vs EV-only vs combined。

### Week 3: Tardis options regime

1. 用 Deribit Tardis 下载至少 30 天 BTC/ETH options snapshots。
2. 生成 5m options regime panel。
3. Join 到 Polymarket crypto markets。
4. 做分桶与 walk-forward，不直接上 ML。

### Week 4: Structure/CDF layer

1. 扩展 range/NegRisk scanner。
2. 建 event-level quality score。
3. 检查它是否能过滤 CopyFlow 亏损样本。

## 7. 当前我建议的最终方向

最值得推进的不是单纯跟单，而是：

```text
Polymarket Crypto Event Strategy =
  CopyFlow smart-wallet consensus
  + historical CLOB executable VWAP
  + Binance/underlying independent close EV
  + Tardis options regime gate
  + basket/CDF consistency sanity check
```

如果要排序：

```text
1. 先做 book-aware forward paper，验证 proxy edge 是否还在。
2. 再加 crypto close EV gate，提高信号质量。
3. 再加 Tardis options regime，决定什么时候追/不追。
4. 最后做 basket/CDF consistency，增加结构性机会和风控。
```

这条路线比“跟某个钱包”更像可交易系统，也更能利用项目里已有的 Tardis API、options regime、Binance close verification 和 Polymarket basket scanners。

## 8. 已验证命令

本轮检查通过：

```text
cargo check -p btc_research --bin tardis_deribit_snapshot_fetch
python scripts/btc_options_regime_report.py --help
python scripts/polymarket_binance_close_signal_scan.py --self-test
python scripts/polymarket_range_basket_arbitrage_scan.py --self-test
python scripts/polymarket_negrisk_basket_arbitrage_scan.py --self-test
```

输出均正常，其中三个 Polymarket scanner self-test 返回 `self-test ok`。

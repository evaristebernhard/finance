# Polymarket 跟单因子策略研究

Date: 2026-06-08

Scope: 基于本项目已有代码、文档和一次只读 smoke run，研究 Polymarket 上“跟单策略”以及“把跟单当成指标，结合别的数据”的可落地方向。

边界：

- 只读研究；不读取私钥、不读 `.env`、不签名、不下单。
- 跟单不能直接等于策略。当前结论是：跟单更适合作为一个 flow / smart-wallet 指标，必须叠加市场规则、盘口容量、价差、延迟和独立概率/赔率判断。
- 任何正收益回测行都只能作为 forward-paper hypothesis，不是 live edge。

## 1. 项目里已经有的相关资产

### 1.1 Polymarket 钱包因子线

已有脚本：

```text
scripts/polymarket_wallet_factor_probe.py
scripts/polymarket_delayed_copy_paper_strategy.py
scripts/polymarket_delayed_copy_parameter_sweep.py
```

对应文档：

```text
docs/markets/onchain/polymarket-wallet-factor-lab-20260607.md
docs/markets/onchain/polylens-external-repos-20260608.md
docs/markets/onchain/strategy-factor-scout-20260607.md
```

`polymarket_wallet_factor_probe.py` 已经实现了 v0 钱包因子扫描：

```text
public trades/activity/books
-> wallet_scores.csv
-> market_suitability.csv
-> follow_candidates.csv
-> trade_edges.csv
```

主要输入是 Polymarket 公共接口：

- Data API `/trades`：全局近期公开成交。
- Data API `/activity`：seed wallet 的公开活动。
- Gamma API `/events`：市场/事件元数据、规则、流动性、token id。
- CLOB API `/book`：当前 order book。

### 1.2 已有 wallet/copy 因子定义

当前 v0 已经有这些核心特征：

```text
ProxyEdge_{k,d} = P_next_trade(asset, t_k + d) - P_entry,k

CopyDecay_w(300s)
  = mean(ProxyEdge_{w,0s}) - mean(ProxyEdge_{w,300s})

DelayRobustEdge_w
  = min(mean(ProxyEdge_{w,30s}),
        mean(ProxyEdge_{w,120s}),
        mean(ProxyEdge_{w,300s}))

CategorySpecialization_w
  = max_c Sharpe(ProxyEdge_{w,c,300s})
    - Sharpe(ProxyEdge_{w,not-c,300s})

OneHitWonderPenalty_w
  = max(PositiveProxyPnL_w) / sum(PositiveProxyPnL_w)

LiquidityAdjustedCopyEdge
  = mean(ProxyEdge_{w,300s})
    / max(current_spread_cents + slippage_1k_cents, 0.01)
```

这些定义基本正确地把“钱包是否值得跟”拆成：

- 延迟后还剩多少 edge；
- 是不是一笔 lucky win；
- 是否有类别专长；
- 当前盘口是否有容量；
- 规则是否容易误判；
- 当前价差/滑点会不会吃光边际。

### 1.3 已有 paper 策略层

`polymarket_delayed_copy_paper_strategy.py` 已经实现一个因果 paper ledger：

```text
For a wallet BUY at time t:
  entry = P_next_trade(t + entry_delay) + entry_cost
  exit  = P_next_trade(t + exit_delay) - exit_cost
  shares = stake_usd / entry
  pnl = shares * (exit - entry)
```

关键因果保护：

```text
决策层只使用在 signal time 之前已经 matured 的 prior wallet records。
```

这点很重要：它避免了用未来 wallet 表现来决定当前是否跟单。

## 2. 本次实际 smoke run

我运行了：

```text
python scripts/polymarket_wallet_factor_probe.py \
  --trade-limit 1000 \
  --wallet-history-wallets 20 \
  --wallet-history-limit 100 \
  --top-wallets 40 \
  --book-token-limit 30 \
  --output-dir output/polymarket_wallet_factor_probe_smoke_20260608
```

脚本成功写出：

```text
C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\output\polymarket_wallet_factor_probe_smoke_20260608
```

结果摘要：

```text
Global recent trades parsed: 1000
Wallet activity trades parsed: 2000
Merged unique trades used for factors: 2855
Time span UTC: 2026-06-07T02:04:00+00:00 -> 2026-06-08T15:19:09+00:00
Wallets scored: 40
Eligible wallets after 5m/one-hit/min-count filters: 3
Markets/assets scored: 343
Markets with 1k capacity under slippage threshold: 12
Follow candidates: 40
BUY trade edge rows: 2444
Book errors: 4
```

再运行了 paper 策略：

```text
python scripts/polymarket_delayed_copy_paper_strategy.py \
  --probe-output-dir output/polymarket_wallet_factor_probe_smoke_20260608 \
  --output-dir output/polymarket_delayed_copy_paper_smoke_20260608 \
  --category all \
  --entry-delay-seconds 30 \
  --exit-delay-seconds 300 \
  --min-prior-trades 2 \
  --min-prior-mean-net-edge-cents 0.0 \
  --min-prior-win-rate 0.5
```

结果：

```text
Input rows: 2444
Closed paper trades: 0
Deployed notional USD: 0
Net PnL USD: 0
Skip counts:
  unclosed_or_invalid_delay_proxy: 2322
  prior_edge_too_low: 77
  not_enough_prior_trades: 39
  entry_price_filter: 6
```

这说明在这一小段近期样本里，5 分钟 delayed-copy paper 条件太短/数据太浅，大多数候选还没有可评价的 delayed proxy。

又运行参数扫：

```text
python scripts/polymarket_delayed_copy_parameter_sweep.py \
  --probe-output-dir output/polymarket_wallet_factor_probe_smoke_20260608 \
  --output-dir output/polymarket_delayed_copy_sweep_smoke_20260608 \
  --category all \
  --min-closed-trades-for-rank 1 \
  --top-n 10
```

结果中最靠前的配置也亏损：

```text
Best displayed configs:
  direction=copy, entry=30s, exit=120s, prior_n=8
  closed trades=4
  net_pnl=-314.201 USD
  ROI=-0.7855
  win_rate=0
```

结论：当前 smoke 样本不支持“直接盲跟单”。

## 3. 直接跟单为什么危险

从项目已有文档和本次 run 看，直接跟单至少有五类风险：

1. 延迟风险

```text
leader 成交价 -> 我们看到公开成交 -> 我们读取数据 -> 我们下单 -> 实际成交
```

如果 edge 在 30s/120s/300s 内衰减，leader 有 edge，follower 没 edge。

2. 盘口成本

Polymarket outcome token 的价差和深度经常不稳定。`market_suitability.csv` 里虽然有 343 个 asset，但本次只有 12 个满足 1k capacity under slippage threshold。

3. 幸存者偏差 / one-hit wonder

样本里的 top wallet 有些只有 1 笔可评价买入，edge 看起来很高但 one-hit penalty=1，不能信。

4. 市场规则风险

很多市场有规则歧义、resolution source、50-50、cancel/delay 等特殊条款。钱包可能懂规则，也可能只是押注；跟单者如果不懂规则，无法判断 EV。

5. hidden hedge / inventory

公开 wallet 成交不等于该用户完整风险敞口。可能有 off-chain hedge、多个钱包、对冲腿或 maker inventory。

所以直接策略不应是：

```text
看到 smart wallet BUY -> 立刻 BUY 同 outcome
```

而应是：

```text
smart-wallet flow 是一个候选事件 / 因子；
只有当独立 EV、盘口容量、规则清晰度、延迟曲线都通过时才进入 paper trade。
```

## 4. 推荐策略：CopyFlow 作为指标，而不是盲跟

### 4.1 目标

建立一个 Polymarket CopyFlow 因子，用于给市场/outcome 打分：

```text
CopyFlowScore(asset, t)
= smart_wallet_quality
  * recent_smart_buy_pressure
  * category_fit
  * delay_survival
  * liquidity_quality
  * rule_safety
  * anti_crowding
```

它输出的不是订单，而是：

```text
asset/outcome 当前是否值得进入候选池。
```

### 4.2 因子分层

#### A. 钱包质量层

```text
wallet_delay_robust_edge_cents
wallet_copy_decay_300s_cents
wallet_one_hit_penalty
wallet_buy_eval_count_300s
wallet_category_specialization
wallet_profit_factor_proxy
wallet_max_drawdown_proxy
wallet_trade_count
wallet_market_count
```

准入建议：

```text
buy_eval_count_300s >= 20       # 当前 v0 默认 3 太浅，可用于 smoke，但不能用于 live
one_hit_penalty <= 0.50-0.75
min(mean edge at 30/120/300s) > total_cost_cents
category specialization > 0, 或至少该类别历史 edge 为正
```

#### B. 当前 smart flow 层

对每个 asset/outcome 聚合最近窗口：

```text
smart_buy_notional_5m / 30m / 2h
smart_sell_notional_5m / 30m / 2h
net_smart_flow = smart_buy - smart_sell
unique_smart_wallet_count
flow_concentration = max_wallet_flow / total_smart_flow
repeat_buy_session_count
leader_entry_price_gap_to_current
```

推荐信号不是单个 wallet，而是多钱包一致性：

```text
2-5 个高质量钱包在同一 outcome 上 30-120 分钟内同向买入
> 单个钱包大买一笔
```

#### C. 市场/规则层

```text
rule_ambiguity_score
market_resolution_time
category
end_date / time_to_resolution
description_contains_50_50_or_cancel_or_delayed
market_type: binary / range / neg-risk basket
```

过滤建议：

```text
rule_ambiguity_score < 4.0
avoid 50-50 / ambiguous / cancelled / delayed unless manually reviewed
avoid near-resolution markets unless settlement rule and data source are deterministic
```

#### D. 盘口执行层

```text
best_bid
best_ask
spread_cents
ask_depth_usd
capacity_1000_ok
capacity_1000_slippage_cents
capacity_5000_ok
crowd_exit_risk
```

硬门槛：

```text
expected_edge_cents > spread_cents + 2 * slippage_cents + safety_buffer
capacity_1000_ok == True for 1k sleeve
stake <= 10-20% of ask depth near target price
```

#### E. 独立 EV 层

这是从“跟单指标”走向“策略”的关键。CopyFlow 只能告诉我们可能有人有信息，不能告诉我们当前价格是否便宜。

对于不同市场类型要有不同独立 EV 模型：

1. Crypto close / above / below 市场

项目已有：

```text
scripts/polymarket_binance_close_signal_scan.py
scripts/polymarket_binance_close_settlement_verify.py
```

用 Binance 价格和波动估计：

```text
P(S_T > K)
```

然后比较 Polymarket ask。

2. Range basket / mutually-exclusive 市场

项目已有：

```text
scripts/polymarket_range_basket_arbitrage_scan.py
scripts/polymarket_negrisk_basket_arbitrage_scan.py
```

只信 CLOB asks，不信 Gamma display probabilities。

3. 非 crypto 新闻/政治/体育市场

v0 不建议自动交易。可以 paper alert，但需要外部概率模型或人工规则审查。

## 5. 策略形态建议

### Strategy 1: CopyFlow + Independent EV Gate

适合：crypto close / price above / price range 等有外部价格源的市场。

流程：

```text
1. 监听 recent trades/activity。
2. 计算 wallet quality。
3. 对 asset/outcome 聚合 CopyFlowScore。
4. 若 CopyFlowScore 进入 top decile，进入候选池。
5. 用独立模型计算 p_model。
6. 从 CLOB book 计算可成交 avg_fill_price 和 fees。
7. 只在以下条件成立时 paper enter:

   p_model - avg_fill_price
   > fee_cents + spread_cents + slippage_cents + safety_buffer

8. 用真实延迟和 book snapshot 记录 paper fill。
9. 到 resolution 或预设 exit rule 后结算。
```

最小门槛：

```text
wallet_quality_n >= 20 matured trades
unique_smart_wallet_count >= 2, or one wallet has long stable category edge
capacity_1000_ok == True
rule_ambiguity_score < 4
edge_cents >= 2 * total_cost_cents
```

### Strategy 2: CopyFlow as Alert, Not Auto Entry

适合：政治、体育、天气、娱乐、OpenAI/tech 新闻类市场。

流程：

```text
1. CopyFlowScore 异常升高。
2. 输出 alert：哪个钱包、哪个 outcome、最近买入均价、当前 ask、盘口深度、规则摘要。
3. 人工或 LLM due diligence 检查：resolution source、新闻、是否已有价格反应。
4. 只记录 paper decision，不自动执行。
```

这条线更适合现在先做，因为本次 top candidates 集中在 Elon tweet count 这类规则型市场，盲跟风险很高。

### Strategy 3: Fade Bad Wallets / Crowded Late Flow

直接跟单不行时，可以反过来用作反向指标：

```text
FadeScore(asset,t)
= bad_wallet_buy_pressure
  + late_crowding_pressure
  + high_spread
  + leader_entry_far_better_than_current
```

但 fade 需要能交易 opposite outcome 或 No/Yes 对腿，执行更复杂。v0 可以 paper-only。

## 6. 应该补的代码

### 6.1 长周期本地状态库

当前 probe 是 one-shot CSV，不能稳定评估 wallet persistence。建议新增 SQLite：

```text
output/polymarket_copy_lab/state.sqlite
```

表：

```text
raw_trades
wallet_activity
market_meta
book_snapshots
wallet_daily_scores
asset_copyflow_snapshots
paper_orders
paper_fills
paper_resolutions
```

### 6.2 CopyFlow 聚合器

新增脚本建议：

```text
scripts/polymarket_copyflow_signal_scan.py
```

输入：

```text
wallet_scores.csv
follow_candidates.csv
market_suitability.csv
latest CLOB books
optional independent model outputs
```

输出：

```text
copyflow_signals.csv
copyflow_alerts.md
copyflow_snapshot.json
```

核心字段：

```text
asset
condition_id
title
outcome
category
current_best_ask
spread_cents
capacity_1000_ok
rule_ambiguity_score
smart_buy_notional_30m
unique_smart_wallets_30m
weighted_wallet_edge_300s
flow_concentration
copyflow_score
independent_model_prob
ev_cents_after_cost
action: observe / paper_enter / reject
reject_reason
```

### 6.3 Forward paper cron

每天或每小时跑：

```text
probe -> copyflow_signal_scan -> paper_strategy -> settlement verifier
```

但至少需要 2 周 forward paper，再谈 live。

## 7. 当前结论

1. 这个项目已经有 Polymarket 跟单研究的骨架，不需要从零开始。

2. 本次 smoke run 验证了脚本能跑通，也暴露了关键事实：小样本近期数据不支持盲跟；参数扫出来的可成交 paper 行也亏损。

3. 最稳的方向不是“跟单策略”，而是：

```text
CopyFlow as factor
+ market suitability
+ CLOB executable cost
+ independent probability / deterministic basket model
+ causal paper ledger
```

4. 可先落地的策略优先级：

```text
P1: CopyFlow + crypto close independent EV gate
P2: CopyFlow alert for rule-heavy non-crypto markets
P3: Fade bad/crowded wallets paper-only
```

5. 当前不能 live。下一步应该是把 one-shot probe 变成持续 forward-paper evaluator，并用至少两周样本检验：

```text
delay curve
category specialization persistence
wallet rank stability
edge after spread/slippage/fees
capacity decay
resolution/settlement correctness
```

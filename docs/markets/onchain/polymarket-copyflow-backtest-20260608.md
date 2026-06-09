# Polymarket CopyFlow Delayed-Copy Backtest

Date: 2026-06-08

Scope: 回测 `docs/markets/onchain/polymarket-copyflow-strategy-20260608.md` 中的 CopyFlow / delayed-copy 钱包跟单因子策略。只读公共数据，不下单，不读取私钥。

## 1. 数据下载

使用项目已有脚本扩大样本：

```text
python scripts/polymarket_wallet_factor_probe.py \
  --trade-limit 6000 \
  --wallet-history-wallets 80 \
  --wallet-history-limit 300 \
  --top-wallets 120 \
  --gamma-event-limit 120 \
  --book-token-limit 120 \
  --sleep-ms 25 \
  --http-timeout 15 \
  --output-dir output/polymarket_wallet_factor_probe_deep_20260608
```

一次更大的尝试：

```text
--trade-limit 10000 --wallet-history-wallets 120 --wallet-history-limit 500 --book-token-limit 250
```

跑了 16 分钟仍未写出文件，被中止；因此采用 6000/80/300/120 的 deep run。

输出：

```text
output/polymarket_wallet_factor_probe_deep_20260608
```

数据摘要：

```text
Recent public trades requested: 6000
Global recent trades parsed: 2858
Wallet activity seed wallets requested: 80
Wallet activity trades parsed: 23466
Merged unique trades used for factors: 25272
Time span UTC: 2026-05-31T02:35:31+00:00 -> 2026-06-08T15:46:42+00:00
Gamma active events requested: 120
Orderbook token limit: 120
Book errors: 49
Wallets scored: 120
Eligible wallets after 5m/one-hit/min-count filters: 45
Markets/assets scored: 1718
Markets with 1k capacity under slippage threshold: 51
Follow candidates: 1479
BUY trade edge rows: 22170
```

重要边界：

- `/trades` 公共接口在 paging-window 上提前停止，所以请求 6000 只拿到 2858 条全局 recent trades。
- 钱包 activity 补了 23466 条，因此整体样本覆盖约 8 天。
- `trade_edges.csv` 的 delayed price 是同 outcome 的 next public trade proxy，不是历史盘口成交保证。
- 当前 book 是 live book，不是历史 entry 时刻 book。

## 2. 回测引擎

使用：

```text
scripts/polymarket_delayed_copy_paper_strategy.py
```

策略方程：

```text
For a wallet BUY at time t:
  entry = P_next_trade(t + entry_delay) + entry_cost
  exit  = P_next_trade(t + exit_delay) - exit_cost
  shares = stake_usd / entry
  pnl = shares * (exit - entry)
```

因果保护：

```text
当前 signal 只能使用 signal time 之前已经 matured 的 wallet prior records。
```

默认资金/仓位参数：

```text
capital_usd = 10000
stake_usd = 100
max_stake_usd = 100
max_open_notional_usd = 2000
max_wallet_open_notional_usd = 300
max_market_open_notional_usd = 300
entry_cost_cents = 0.5
exit_cost_cents = 0.5
safety_cost_cents = 0.5
fallback_spread_cents = 1.0
min_total_cost_cents = 1.5
```

## 3. Baseline 回测

命令：

```text
python scripts/polymarket_delayed_copy_paper_strategy.py \
  --probe-output-dir output/polymarket_wallet_factor_probe_deep_20260608 \
  --output-dir output/polymarket_delayed_copy_paper_deep_20260608_baseline \
  --category all \
  --entry-delay-seconds 30 \
  --exit-delay-seconds 300 \
  --min-prior-trades 3 \
  --min-prior-mean-net-edge-cents 0 \
  --min-prior-win-rate 0.5 \
  --max-prior-one-hit-penalty 0.75
```

结果：

```text
Input rows: 22170
Closed paper trades: 79
Entry/exit delay seconds: 30 / 300
Direction: copy
Category filter: all
Deployed notional USD: 7900
Net PnL USD: +320.1003
ROI on deployed: +4.0519%
Win rate: 58.23%
Average net edge: 3.1119 cents/share
Profit factor: 1.3553
Max closed-trade drawdown: 232.6823 USD
```

Skip counts：

```text
unclosed_or_invalid_delay_proxy: 15668
prior_edge_too_low: 3653
not_enough_prior_trades: 1505
entry_price_filter: 452
prior_win_rate_too_low: 415
wallet_open_cap: 174
dedupe_window: 117
market_open_cap: 104
prior_one_hit_too_high: 3
```

Baseline 分类表现：

```text
crypto: 69 trades, pnl +265.66, ROI +3.85%, win 60.9%
sports: 9 trades, pnl +57.62, ROI +6.40%, win 44.4%
other: 1 trade, pnl -3.18, ROI -3.18%, win 0%
```

Baseline wallet 集中度：

```text
0x75cc3b63a2... 6 trades, pnl +143.24, ROI +23.9%, win 100%
0x9dd794023e... 27 trades, pnl +91.81, ROI +3.4%, win 59.3%
0x2aa856f784... 9 trades, pnl +85.11, ROI +9.5%, win 77.8%
```

最差 wallet：

```text
0x5108dd238a... 6 trades, pnl -99.60, ROI -16.6%
0x06dc51826b... 3 trades, pnl -92.32, ROI -30.8%
0xa8ccda0419... 6 trades, pnl -60.14, ROI -10.0%
```

Baseline 的实际入场集中在最后约 1.5 小时：

```text
first signal: 2026-06-08T14:08:19+00:00
last signal:  2026-06-08T15:38:31+00:00
```

这意味着它虽然使用 8 天 wallet history 建 prior，但真正 closed paper trades 主要来自近期高频 up/down 市场；不能当作长期稳健证据。

## 4. 手工配置对比

### 4.1 宽松版本

```text
entry=30s, exit=300s
min_prior_trades=2
min_prior_mean_net_edge_cents=-2
min_prior_win_rate=0.4
max_prior_one_hit_penalty=1.0
```

| category | trades | pnl | ROI | win | PF / note |
|---|---:|---:|---:|---:|---|
| all | 109 | +276.13 | +2.53% | 50.46% | PF 1.2167 |
| crypto | 92 | +289.08 | +3.14% | 56.52% | PF 1.2904 |
| sports | 16 | -68.19 | -4.26% | 25.00% | PF 0.7790 |
| politics | 2 | -12.76 | -6.38% | 0.00% | PF 0 |

结论：宽松过滤增加交易数，但降低质量；edge 主要来自 crypto/up-down 类，sports/politics 不稳。

### 4.2 严格版本，不同 exit horizon

统一：

```text
entry=30s
min_prior_trades=5
min_prior_mean_net_edge_cents=0.5
min_prior_win_rate=0.55
max_prior_one_hit_penalty=0.75
```

| exit | trades | pnl | ROI | win | PF | max DD |
|---:|---:|---:|---:|---:|---:|---:|
| 120s | 106 | +180.86 | +1.71% | 45.28% | 1.0840 | 1108.94 |
| 300s | 49 | +182.70 | +3.73% | 57.14% | 1.2032 | 235.48 |
| 1800s | 6 | -140.63 | -23.44% | 50.00% | 0.3929 | 231.64 |

结论：当前样本里 300s exit 明显优于 120s 和 1800s。120s 交易多但 drawdown 很大；1800s 样本太少且亏。

### 4.3 Copy vs Fade

统一：

```text
entry=30s, exit=300s
min_prior_trades=3
min_prior_mean_net_edge_cents=0
min_prior_win_rate=0.5
max_prior_one_hit_penalty=0.75
```

| direction | trades | pnl | ROI | win | PF | max DD |
|---|---:|---:|---:|---:|---:|---:|
| copy | 79 | +320.10 | +4.05% | 58.23% | 1.3553 | 232.68 |
| fade | 95 | -965.04 | -10.16% | 27.37% | 0.3373 | 1160.00 |

结论：在这个样本上，fade 明显不可用；wallet flow 不是反向指标。

## 5. Focused 参数扫

完整大 sweep 太慢，跑了 focused sweep：

```text
python scripts/polymarket_delayed_copy_parameter_sweep.py \
  --probe-output-dir output/polymarket_wallet_factor_probe_deep_20260608 \
  --output-dir output/polymarket_delayed_copy_sweep_deep_20260608_focused \
  --category all \
  --directions copy,fade \
  --entry-delays 30,120 \
  --exit-delays 120,300 \
  --min-prior-trades-list 2,3,5,8 \
  --min-prior-mean-net-edge-cents-list=-2,0,0.5,1.5 \
  --min-prior-win-rates 0.4,0.5,0.6 \
  --max-prior-one-hit-penalties 0.75,1.0 \
  --min-closed-trades-for-rank 5 \
  --top-n 30
```

配置数：576。

分组表现：

```text
(copy, entry=30, exit=300): 96 configs, best +808.03, median +112.80, positive 62/96
(copy, entry=30, exit=120): 96 configs, best +372.37, median -334.51, positive 19/96
(copy, entry=120, exit=300): 96 configs, best +185.03, median -50.75, positive 39/96
(fade, entry=30, exit=300): 96 configs, best +47.95, median -523.41, positive 12/96
(fade, entry=120, exit=300): 96 configs, best -223.91, median -572.75, positive 0/96
(fade, entry=30, exit=120): 96 configs, best -959.19, median -1252.00, positive 0/96
```

Top focused sweep config：

```text
Direction: copy
Entry delay: 30s
Exit delay: 300s
min_prior_trades: 5
min_prior_mean_net_edge_cents: 0.0
min_prior_win_rate: 0.4
max_prior_one_hit_penalty: 0.75
Closed trades: 83
Net PnL: +808.03 USD
ROI on deployed: +9.7354%
Win rate: 60.24%
Profit factor: 1.9483
Max closed-trade drawdown: 229.73 USD
```

复跑 best config：

```text
output/polymarket_delayed_copy_paper_deep_20260608_best_sweep_replay
```

Best config 分类表现：

```text
crypto: 73 trades, pnl +634.53, ROI +8.69%, win 64.4%
sports: 7 trades, pnl +205.77, ROI +29.4%, win 42.9%
other: 3 trades, pnl -32.27, ROI -10.8%, win 0%
```

Best config top wallets：

```text
0x62d728fb3d... 4 trades, pnl +276.11, ROI +69.0%, win 100%
0xa42f127d7e... 3 trades, pnl +171.41, ROI +57.1%, win 33.3%
0x9dd794023e... 30 trades, pnl +157.35, ROI +5.2%, win 56.7%
0x75cc3b63a2... 6 trades, pnl +124.04, ROI +20.7%, win 100%
0x57f2faf2eb... 11 trades, pnl +79.76, ROI +7.3%, win 45.5%
```

Best config 时间跨度：

```text
first signal: 2026-06-05T18:21:46+00:00
last signal:  2026-06-08T15:40:25+00:00
```

## 6. 结论

### 6.1 当前回测支持什么？

当前 expanded backtest 支持一个弱结论：

```text
Polymarket delayed-copy wallet flow 在最近约 8 天样本中，
用 causal prior wallet stats 过滤后，copy 方向有正 paper edge；
最稳的结构是 entry_delay=30s, exit_delay=300s。
```

其中 baseline：

```text
79 trades, +320.10 USD, ROI +4.05%, PF 1.36
```

focused sweep best：

```text
83 trades, +808.03 USD, ROI +9.74%, PF 1.95
```

### 6.2 当前不支持什么？

不支持 live，也不支持“盲跟所有 smart wallet”。原因：

1. 回测 fill 是 next-public-trade proxy，不是历史 CLOB book fill。
2. 当前 orderbook depth 是 live snapshot，不是每个历史 signal 的 book snapshot。
3. 交易集中在短周期 up/down 市场，尤其 crypto 类；跨类别泛化未知。
4. best config 是 sweep 后挑出来的，存在参数选择偏差。
5. Top PnL 有 wallet 集中度和少数大赢 trade，样本还不够长。
6. `/trades` 公共接口分页有限，global recent trades 只拿到 2858 条。
7. 未做 settlement verification；当前是 exit-proxy paper，不是 resolved PnL。

### 6.3 策略形态建议

当前最合理版本不是最终交易器，而是 forward-paper 策略：

```text
CopyFlow delayed-copy paper strategy v1:
  direction = copy
  entry_delay = 30s
  exit_delay = 300s
  min_prior_trades = 5
  min_prior_mean_net_edge_cents = 0.0
  min_prior_win_rate = 0.4-0.5
  max_prior_one_hit_penalty = 0.75
  category focus = crypto/up-down first
  stake = 100 USD paper
```

必须继续叠加：

```text
historical book snapshot collection
capacity-at-entry simulation
independent EV for crypto close/up-down markets
settlement verification
wallet concentration cap
out-of-sample forward paper
```

## 7. 下一步

建议立刻做两个工程补丁：

1. 持续采集器

```text
scripts/polymarket_copyflow_collect.py
```

每 30-60 秒保存：

```text
recent trades
wallet activity for tracked wallets
CLOB book snapshots for candidate assets
market metadata
```

存 SQLite 或 partitioned CSV。

2. 历史 book-aware 回测器

把当前：

```text
entry = next_public_trade_price + cost
```

升级成：

```text
entry = historical CLOB ask VWAP at signal_time + entry_delay
exit  = historical CLOB bid VWAP at exit_time
```

只有这个版本还能保留正收益，才值得讨论小额 live dry-run。

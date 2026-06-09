# Polymarket Smart Money / Polylens Wallet Research Framework

Date: 2026-06-09

Scope: read-only wallet and market intelligence research. No private keys, no signing, no order placement.

## 0. Core View

Wallet intelligence is valuable, but direct copy-trading is the wrong primitive.

Correct framing:

```text
wallet flow = behavioral / information factor
```

Incorrect framing:

```text
smart wallet bought YES => blindly buy YES
```

A Polylens-like system should answer:

```text
Who seems informed?
In which market types?
At what horizon?
How much of the edge survives public latency and CLOB execution?
Is the flow independent, clustered, or exit liquidity seeking?
```

## 1. Why Polylens-Style Copying Can Fail

### 1.1 Leader edge is not follower edge

Leader PnL:

```text
leader_exit - leader_entry
```

Follower PnL:

```text
follower_exit_bid - follower_entry_ask - fee - slippage
```

These are not the same trade.

### 1.2 Public signal latency

The follower sees trades after public API delay and after the first price impact:

```text
leader buys 0.42
public trade appears
followers buy 0.48-0.55
```

This latency converts smart-flow alpha into worse odds.

### 1.3 Hidden hedges and split wallets

A visible wallet may be:

```text
market maker
basket arbitrageur
inventory rebalancer
multi-wallet cluster
hedged elsewhere
```

Copying one visible leg can copy the wrong net exposure.

### 1.4 One-hit selection bias

A wallet can look brilliant because one large trade won. Penalize:

```text
low matured trade count
high single-trade PnL share
category hopping
recent-only luck
```

### 1.5 Crowding and exit-liquidity risk

If a wallet is visible to many followers, the signal can become self-defeating:

```text
leader buys
followers chase
price rises
leader sells into followers
```

### 1.6 Rule-risk mismatch

The wallet may understand a contract rule better than the follower model. Non-crypto markets need rule due diligence before any automatic action.

## 2. Reference Designs To Borrow From External Polylens-Like Repos

Previously mapped design references:

```text
KSonny4/trader_evaluator
YOPHackathon/PolyCopy
Gonzih/poly-scout
gavindumas-gif/polymarket-smart-money-tracker
darrnhard/polymarket-smart-money
NYTEMODEONLY/polyterm
nimoolee/polymarket-radar
gozuray/Cluster-Analyzer
```

Useful ideas to incorporate locally:

```text
long-term wallet tracking
copy fidelity / follower slippage metrics
wallet exclusion reasons
consensus smart-money maps
local SQLite raw/normalized separation
cluster risk / funding graph penalties
CLOB-first market suitability
alert history and health checks
```

Do not blindly port:

```text
execution/signing/custody
unverified ROI rankings
LLM-only due diligence
copy-trading loops without historical book replay
```

## 3. Wallet Factor Taxonomy

### 3.1 Causal performance factors

Use only matured prior records at signal time.

```text
prior_matured_trades_5m
prior_mean_edge_5m_cents
prior_median_edge_5m_cents
prior_win_rate_5m
prior_profit_factor_5m
prior_drawdown_5m
prior_one_hit_penalty
```

Multiple horizons:

```text
30s
120s
300s
1800s
settlement
```

### 3.2 Delay robustness

A wallet is useful only if edge survives follower latency:

```text
edge_at_0s
edge_at_30s
edge_at_120s
edge_decay_slope
half_life_seconds
```

### 3.3 Category specialization

Wallets often specialize:

```text
crypto close
crypto up/down
politics
sports
macro/economics
range buckets
NegRisk/winner sets
```

Score per category, not globally.

### 3.4 Execution quality

```text
average entry spread
average ask depth at signal
price impact of wallet trade
leader_entry_gap_to_follower_ask
capacity_100_ok
capacity_1000_ok
```

### 3.5 Flow behavior

```text
burst buying
DCA sessions
repeat buys after adverse move
adds into strength vs weakness
sell/exit behavior
pre-settlement holding behavior
```

### 3.6 Independence / clustering

```text
same funding source
same timing bursts
same market basket
copy hierarchy leader/follower relation
unique independent smart wallets
flow concentration
```

Clustered wallets should not count as independent confirmation.

## 4. Smart Money Score v2

A better wallet score should be decomposed, not single opaque ROI.

```text
smart_score =
  causal_edge_score
+ delay_robustness_score
+ category_specialization_score
+ execution_survivability_score
+ consistency_score
- one_hit_penalty
- crowding_penalty
- cluster_penalty
- rule_risk_penalty
```

Example factor stack:

```text
causal_edge_score             = clipped mean prior 300s edge
consistency_score             = win rate and median edge agreement
delay_robustness_score        = min(edge_30s, edge_120s, edge_300s)
execution_survivability_score = historical book VWAP edge after spread/slippage
one_hit_penalty               = top_trade_pnl_share
cluster_penalty               = correlated wallets / shared funding / same burst
crowding_penalty              = followers arrive after wallet and worsen price
```

## 5. From Wallet Signal To Trade Candidate

Wallet flow alone should not open trades. It should join with independent EV.

Preferred candidate rule:

```text
independent_ev_positive
AND wallet_flow_same_direction_positive
AND CLOB executable cost OK
AND rule risk acceptable
AND signal not stale/crowded
```

For crypto binary markets:

```text
Binance-close EV ensemble positive
+ smart wallets same-side net buy
+ no extreme spread/depth issue
+ settlement clear
```

For non-crypto markets:

```text
smart wallet flow -> alert / due diligence
not automatic trade
```

## 6. Research Outputs

### 6.1 Wallet table

```text
wallet
category
matured_trade_count
mean_edge_30s
mean_edge_120s
mean_edge_300s
settlement_edge
win_rate
profit_factor
one_hit_penalty
delay_half_life
best_category
cluster_id
cluster_penalty
```

### 6.2 Flow table

```text
market_id
token_id
time_window
smart_buy_notional
smart_sell_notional
net_smart_notional
unique_smart_wallets
flow_concentration
leader_entry_price_range
latest_flow_age_seconds
```

### 6.3 Candidate table

```text
claim_id
wallet_flow_score
independent_ev_score
book_execution_score
rule_risk_score
combined_score
reject_reason
```

## 7. Tests Against Polylens Failure

A wallet factor is not trusted unless it passes:

```text
walk-forward causality
minimum matured trades
one-hit penalty
copy-vs-fade comparison
exit horizon stability
historical CLOB VWAP replay
category-specific OOS test
cluster independence test
settlement verification where applicable
```

## 8. Immediate Engineering Plan

1. Upgrade wallet scoring:

```text
add category-specific wallet panels
add delay half-life
add one-hit contribution share
add leader/follower slippage estimate
```

2. Join wallet flow with binary EV:

```text
ensemble_signals.csv
+ recent smart flow by token_id
=> combined_candidates.csv
```

3. Build alert ledger:

```text
record each candidate at decision time
later attach CLOB exit and settlement result
```

## 9. Final Principle

Polylens should be an intelligence layer, not an autopilot.

```text
Smart money tells us where to look.
Binary option math tells us whether the price is wrong.
CLOB replay tells us whether we could actually get paid.
```

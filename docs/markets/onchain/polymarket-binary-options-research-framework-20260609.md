# Polymarket YES/NO Binary Options Research Framework

Date: 2026-06-09

Scope: read-only research. No private keys, no signing, no order placement.

## 0. Thesis

Polymarket YES/NO shares are not just prediction-market quotes. They are bounded-payoff binary claims:

```text
YES = 1{event happens}
NO  = 1{event does not happen}
```

For price-settled crypto markets, a YES share is close to a cash-or-nothing digital option:

```text
YES(K,T) = 1{S_T > K}
NO(K,T)  = 1{S_T <= K}
```

That opens a deeper strategy space than simple smart-wallet copying:

```text
independent probability modeling
+ implied distribution extraction
+ no-arbitrage consistency
+ CLOB microstructure
+ settlement-rule risk
+ behavioral smart-money overlays
```

## 1. Why This Is Deeper Than CopyFlow

CopyFlow asks:

```text
Who bought this outcome?
```

Binary option research asks:

```text
What mathematical claim is this outcome?
What is its fair probability under external data?
What logical constraints must related claims satisfy?
Where does the executable CLOB violate those constraints after fees/slippage?
```

The latter can produce strategies even when wallet data is noisy or crowded.

## 2. Claim Types On Polymarket

Polymarket markets can be classified into mathematical claim families.

### 2.1 Threshold digital

Examples:

```text
Bitcoin above $64,000 on June 9?
Ethereum above $1,800 on June 9?
```

Payoff:

```text
YES = 1{S_T > K}
NO  = 1{S_T <= K}
```

Research tools:

```text
realized-vol probability
implied-vol probability
strike monotonicity
digital skew
settlement verification
```

### 2.2 Range bucket

Examples:

```text
Bitcoin price on June 9?
XRP price on June 10?
```

Payoff:

```text
bucket_i = 1{a_i <= S_T < b_i}
```

Constraints:

```text
sum_i P(bucket_i) = 1
bucket_i and bucket_j are mutually exclusive
```

Strategies:

```text
buy all YES if sum executable asks < 1 - fees
buy all NO if sum executable asks < N - 1 - fees
compare bucket CDF with threshold markets
```

### 2.3 Up/down interval

Examples:

```text
Bitcoin Up or Down - 15m window
```

Payoff often depends on close-to-close or start/end prices:

```text
YES/Up = 1{S_end > S_start}
```

Research tools:

```text
very short horizon vol
microstructure drift
latency-sensitive order flow
CopyFlow as flow confirmation
```

### 2.4 NegRisk / winner-take-all set

Examples:

```text
Election winner
Fed decision
F1 champion
```

If exhaustive and exactly one YES resolves:

```text
sum_i P(outcome_i) = 1
```

Strategy:

```text
buy all YES if total executable cost + fee < 1
```

But this requires strong completeness checks:

```text
event detail not truncated
Other/catch-all leg active if relevant
detail_market_count == executable legs or explicitly explained
stale/settled markets rejected
```

### 2.5 Logical implication graph

Examples:

```text
BTC > 66k implies BTC > 64k
candidate wins nomination implies candidate remains active
team wins tournament implies team wins semifinal
```

Constraint:

```text
P(A) <= P(B) if A implies B
```

Strategy family:

```text
claim graph no-arb scanner
```

## 3. Pricing Framework For Crypto Digital Markets

### 3.1 Realized-vol lognormal model

For threshold claim:

```text
P(S_T > K) = Phi((log(S_now) - log(K)) / (sigma_1m * sqrt(minutes_to_T)))
```

This is what the current scanner approximates.

Weaknesses:

```text
vol lookback sensitivity
jumps/fat tails
intraday seasonality
event-time volatility
near-expiry microstructure
```

### 3.2 Ensemble model

Preferred next step:

```text
P_60m
P_180m
P_360m
robust_min_expected_pnl
robust_min_edge
```

Only promote rows that survive multiple volatility assumptions.

### 3.3 Options-implied model

Use Deribit/Tardis options surface:

```text
BTC/ETH implied vol
risk-neutral distribution
digital probability from option smile
```

Compare:

```text
Polymarket executable probability
vs realized-vol probability
vs Deribit implied probability
```

A robust edge is strongest when both realized-vol and options-implied models agree.

## 4. Implied CDF From Polymarket Itself

For same underlying and maturity:

```text
YES(K) = P(S_T > K)
CDF(K) = 1 - YES(K)
```

No-arb conditions:

```text
YES(K_low) >= YES(K_high)
NO(K_low) <= NO(K_high)
```

If violated on executable CLOB prices, possible structures:

```text
buy lower-strike YES / sell higher-strike YES if supported
buy lower-strike YES + buy higher-strike NO variants
range-bucket synthetic checks
```

Practical issue:

```text
Polymarket may not support clean shorting in the same way as option venues,
so many theoretical arbitrages become either maker quotes, mint/redeem flows,
or require complementary YES/NO baskets.
```

## 5. YES/NO Parity

For one binary market:

```text
YES + NO = 1
```

Executable checks:

```text
YES_ask + NO_ask < 1 - fee_buffer  => buy both, deterministic payout
YES_bid + NO_bid > 1 + fee_buffer  => sell/redeem path if operationally available
```

Because execution mechanics matter, parity should be split into:

```text
buy-side parity: executable with normal CLOB buys
sell-side parity: needs inventory / merge / redeem / short path analysis
```

## 6. Microstructure Research

Each binary market has a probability orderbook:

```text
YES bid/ask
NO bid/ask
synthetic YES from NO = 1 - NO
parity width
spread in probability cents
depth at $100/$1k notional
book staleness
trade impact
```

Features:

```text
yes_mid = (yes_bid + yes_ask) / 2
no_implied_yes_mid = 1 - (no_bid + no_ask) / 2
parity_pressure = yes_mid - no_implied_yes_mid
spread_cents = yes_ask - yes_bid
ask_depth_100_usd_ok
bid_depth_exit_ok
```

Research questions:

```text
Do stale thin books explain most apparent edge?
Does parity pressure mean-revert?
Do smart wallets buy into thin ask ladders or wait for depth?
Does edge disappear after one public print?
```

## 7. Settlement Rule Risk

A market is not only math. It is also a contract.

Rule-risk features:

```text
settlement source clarity
single external reference vs committee/news judgment
timezone/candle ambiguity
outage/cancellation clauses
50/50 clauses
ambiguous wording
source hierarchy
```

Crypto Binance-close markets are attractive because settlement is relatively mechanical. Politics/news markets need much stronger manual or LLM-assisted rule review.

## 8. Portfolio From Prediction Types Alone

The user hypothesis is plausible:

```text
Maybe Polymarket prediction types themselves contain enough mathematical structure to build a portfolio.
```

A portfolio could allocate across strategy families:

```text
A. independent EV digital threshold trades
B. range bucket no-arb watchdog
C. NegRisk exhaustive basket arbitrage
D. YES/NO parity micro-arbs
E. implication graph inconsistencies
F. smart-money confirmation overlays
```

The edge is not one model. It is a stack of constraints:

```text
external data constraint
+ logical claim constraint
+ no-arb basket constraint
+ microstructure constraint
+ behavioral flow constraint
```

## 9. Proposed Data Model

A unified claim table:

```text
claim_id
market_id
event_id
question
claim_type
underlying
settle_time
strike
lower_bound
upper_bound
outcome
condition_id
token_id
rule_source
rule_risk_score
```

A quote table:

```text
claim_id
timestamp
yes_bid
yes_ask
no_bid
no_ask
yes_depth_100
yes_depth_1000
no_depth_100
no_depth_1000
spread_cents
book_age_seconds
```

A model table:

```text
claim_id
timestamp
model_name
model_probability
expected_profit_usd
edge_cents
stress_min_probability
```

A relation table:

```text
claim_a
claim_b
relation_type
A_implies_B
mutually_exclusive
exhaustive_group_id
```

## 10. Research Roadmap

Priority 1:

```text
Binance-close ensemble runner
settlement verifier
calibration report
```

Priority 2:

```text
binary claim parser for threshold/range/up-down markets
implied CDF and monotonicity scanner
```

Priority 3:

```text
NegRisk and range basket watchdog with strict lifecycle gates
```

Priority 4:

```text
Tardis/Deribit options-implied probability join
```

Priority 5:

```text
claim graph engine for cross-market logical inconsistencies
```

## 11. Promotion Gates

No live/dry-run discussion unless a candidate passes:

```text
public read-only paper record
CLOB executable ask/bid VWAP
fee + slippage + safety buffer
settlement verification
not stale / not already settled
rule risk acceptable
edge robust to model stress
capacity sufficient
```

For Binance-close EV specifically:

```text
positive under 60m/180m/360m vol
robust_min_expected_profit_usd >= 0.50 per 100 USD
robust_min_edge_cents >= 0.25
probability not extreme unless special stress rules pass
post-settlement calibration positive
```

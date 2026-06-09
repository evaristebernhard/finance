# On-Chain Strategy Factor Scout

Date: 2026-06-07

Scope: strategy candidates for roughly 10k USD capital, with preference for
on-chain opportunities, low realized slippage, and data-driven factor research.

This is a research map, not financial advice. Every candidate below needs
paper trading, venue-specific fee checks, and small-size dry runs before risk
capital.

## Executive Take

For 10k USD, the best starting point is not raw MEV or latency-first DEX
arbitrage. Those markets are brutally competed, gas/priority fees matter, and
the edge window is often too short for a small independent setup.

The most realistic lanes are:

1. Funding/basis spread monitor across perp venues.
2. CEX-DEX or DEX-CEX price-dislocation scanner with strict no-trade filters.
3. On-chain wallet/copy-trade signal research, but only as a filtered signal,
   not blind mirroring.
4. Prediction-market relative value/copy-trade research if we want a slower
   on-chain edge with visible order books and public wallet history.
5. LP/rebalance/LVR-aware liquidity provision as a slower portfolio sleeve,
   not the first active trading bot.

The likely first build should be a scanner, not an auto-trader:

```text
funding + OI + premium + liquidity + slippage quote + wallet/flow catalyst
-> candidate score
-> paper execution record
-> only then small live sizing
```

## Capital Constraints

With 10k USD, we should avoid strategies that require:

- large inventory on multiple CEXs and chains;
- competing per-block against MEV searchers;
- large swaps in thin meme-token pools;
- holding long-tail tokens with impossible exit liquidity;
- leverage high enough that funding/basis noise liquidates the hedge.

10k is enough for:

- 1k-3k test legs on deep perp venues;
- small cross-venue basis trades;
- copy-trade paper portfolios;
- quote/slippage scanners;
- limited Solana/EVM spot execution through aggregators;
- high-quality data collection.

## Strategy Families

### 1. Funding / Basis Spread Arbitrage

Hypothesis:

```text
When perp funding or basis is meaningfully different across venues, a
delta-neutral long/short pair can harvest the spread if funding persistence
exceeds fees, borrow costs, and slippage.
```

Why it fits 10k:

- Lower turnover than HFT.
- Can trade on deep pairs.
- On-chain perp venues expose funding/open-interest state.
- Can start as a scanner and paper ledger.

Venues/data:

- Hyperliquid, dYdX, GMX, Jupiter Perps, Binance/Bybit/OKX as hedge references.
- GMX docs note funding depends on long/short open-interest imbalance and that
  near-live market state is available through `/markets/info`.
- dYdX and most perp venues use funding to pull perp price toward spot.

Core factors:

```text
funding_spread_8h = funding_receive_leg - funding_pay_leg
annualized_funding_spread
mark_index_premium_bps
premium_reversion_speed
open_interest_imbalance
OI_change_5m / OI_change_1h
funding_persistence_3_intervals
venue_depth_at_1k_3k_5k
fee_plus_slippage_roundtrip_bps
borrow_cost_if_spot_hedged
liquidation_buffer
```

Entry sketch:

```text
enter if:
  expected funding over holding horizon
  > 2 * total roundtrip cost
  and OI/depth supports target size
  and funding has persisted for N observations
  and mark premium is not already violently reverting
```

Exit sketch:

```text
exit when funding spread compresses, hedge drift exceeds budget, liquidity
degrades, or holding horizon expires.
```

Risks:

- Funding can flip.
- Hedge legs can de-sync.
- Perp venues have liquidation/ADL/counterparty risk.
- Small caps show huge funding but exit liquidity is often fake.

Priority: high.

### 2. CEX-DEX / DEX-CEX Dislocation Scanner

Hypothesis:

```text
On-chain pools can lag CEX prices, especially for fresh listings, narrative
rotations, chain-specific liquidity shocks, and bridge delays.
```

Why it fits 10k:

- We do not need to win every opportunity.
- Scanner can focus on slower, wider, lower-frequency opportunities.
- CEX leg can provide low-slippage hedge if token is listed.

Core factors:

```text
dex_mid_vs_cex_mid_bps
quote_price_impact_for_size
route_hop_count
pool_depth_near_mid
pool_fee_bps
gas_or_priority_fee_bps
bridge_required_flag
time_since_cex_listing
onchain_volume_5m / 1h
pool_reserve_imbalance
oracle_deviation
slippage_quote_decay_after_5s
```

Execution rule:

```text
trade only if executable quote edge > all-in cost + safety buffer
```

For 10k, useful sizes to quote:

```text
250 USD, 500 USD, 1000 USD, 2500 USD
```

Avoid:

- routes with bridges in the execution loop;
- long-tail meme pools with one-sided exit;
- opportunities that only exist before gas/priority fee;
- pools where our own quote has more than 30-50% of the apparent edge as price
  impact.

Priority: high as scanner, medium as auto execution.

### 3. On-Chain Wallet / Copy-Trade Signal Research

Hypothesis:

```text
Some public wallets repeatedly enter good trades before broader attention, but
blind copying is usually worse than using wallet behavior as a signal.
```

Why not blind copy:

- Execution lag makes fills worse.
- Wallets can split activity across many addresses.
- Leaderboards overfit lucky concentrated bets.
- Copying only visible wins breaks the original strategy distribution.
- Some wallets intentionally create misleading flow.

Wallet factors:

```text
realized_pnl_after_fees
max_drawdown
win_rate_by_token_type
median_hold_time
profit_factor
avg_entry_market_cap
avg_entry_liquidity
copyable_delay_seconds
price_move_between_leader_entry_and_our_possible_entry
position_sizing_consistency
wallet_cluster_overlap
token_exit_liquidity_after_entry
number_of_distinct_tokens
category_specialization
```

Copyable wallet filters:

```text
hold_time_median > 10-30 min
entry_size not so large that the wallet itself moves the pool
not mostly one lucky win
positive PnL after simulated delayed copy
does not buy illiquid tokens before dumping into copiers
```

Execution:

```text
first paper-copy every signal with a realistic delay and quote slippage;
then allocate tiny live size only to wallets whose delayed-copy equity curve is
still positive.
```

Priority: medium. Good as a signal source; dangerous as blind automation.

### 4. Prediction-Market Relative Value / Copy Research

Hypothesis:

```text
Prediction markets have public order books and public wallets; edge may come
from cross-venue pricing, category specialization, or slower information
processing rather than crypto microstructure.
```

Why it fits 10k:

- Slower than DEX MEV.
- Public wallet history is auditable.
- Order books are often shallower but position sizes can be controlled.

Core factors:

```text
polymarket_price_vs_reference_probability
cross_venue_price_gap
orderbook_depth_to_1pct
market_resolution_time
wallet_category_skill
wallet_entry_price_gap_to_current
news_latency
crowding_of_copied_wallet
```

Candidate:

```text
Use wallet flow as an alert, but enter only if our independent probability
model still sees EV after current spread.
```

Priority: medium-high if we want non-crypto-beta edges.

### 5. LVR-Aware Liquidity Provision / Rebalancing

Hypothesis:

```text
LP returns improve when we enter pools with favorable fee/rebalance dynamics and
avoid toxic flow windows.
```

Why it is slower:

- No need to race every block.
- Can be researched from pool states and price paths.

Core factors:

```text
fee_apr_realized
volume_to_liquidity
external_price_volatility
pool_price_vs_reference
impermanent_loss_proxy
loss_versus_rebalancing_proxy
toxic_flow_share
range_width
rebalance_frequency
gas_drag
```

For 10k:

- Treat as a small sleeve.
- Prefer deep pools and short experiments.
- Avoid new-token pools unless the whole point is high-risk farming.

Priority: medium-low for active trading, medium for portfolio yield research.

### 6. Raw MEV / Atomic DEX Arbitrage

Hypothesis:

```text
Atomic arbitrage exists when DEX prices differ enough to cover gas, fees,
bundle bid, and failure/revert cost.
```

Why it is not first choice for 10k:

- Very competitive.
- Latency and private order flow matter.
- Searchers bid away much of the profit.
- Need robust simulation and bundle submission.

Useful as reference:

- Uniswap V3 flash-swap examples show the mechanics of atomic arbitrage.
- Flashbots/MEV-Share docs and repos show private execution/searcher patterns.
- HackMD MEV notes are useful for conceptual background.

Priority: low for immediate capital deployment; high for learning.

## Factor Pool

### Market Structure

```text
spread_bps
depth_1k_5k_10k
quote_price_impact
route_hop_count
pool_fee_bps
maker/taker_fee_bps
gas_bps
priority_fee_bps
venue_latency_ms
oracle_update_lag
```

### Flow / Positioning

```text
funding_rate
funding_spread
open_interest
OI_imbalance
OI_velocity
long_short_ratio
mark_index_premium
liquidation_cluster_distance
large_wallet_net_flow
DEX_buy_sell_imbalance
CEX_deposit_withdraw_flow
```

### Wallet / Copy

```text
wallet_realized_pnl
wallet_profit_factor
wallet_max_drawdown
wallet_hold_time_median
wallet_trade_count
wallet_token_diversity
wallet_entry_liquidity
wallet_price_impact_created
wallet_copy_delay_edge
wallet_cluster_count
wallet_same_token_reentry_rate
```

### Execution Safety

```text
expected_edge_bps
all_in_cost_bps
edge_to_cost_ratio
slippage_quote_decay
failed_tx_rate
partial_fill_risk
bridge_required
withdrawal_delay
venue_withdrawal_risk
liquidation_buffer
max_position_pct_of_depth
```

## Initial Ranking For 10k USD

1. Funding/basis spread scanner.
2. DEX/CEX executable quote scanner.
3. Wallet/copy-trade paper simulator.
4. Prediction-market relative-value scanner.
5. LP/LVR research sleeve.
6. Raw MEV arbitrage learning track.

## First Build Proposal

Build a read-only scanner with three modules:

```text
Module A: perp funding/basis
  venues: Hyperliquid, GMX, dYdX, Binance/Bybit references
  output: funding spread tickets

Module B: DEX quote vs reference
  venues: Jupiter/Solana first, then Base/Uniswap/Aerodrome
  output: executable quote edge at 250/500/1000/2500 USD

Module C: wallet signal lab
  track candidate wallets
  simulate delayed copy with realistic quote/slippage
  output: copyable-wallet score
```

Do not execute automatically until:

```text
paper PnL > costs for at least 2-4 weeks
drawdown is understood
entry/exit logs are reproducible
live quote slippage matches simulation
```

## References

- Crypto arbitrage overview: https://degen0x.com/learn/crypto-arbitrage-strategies-guide-2026/
- dYdX funding explainer: https://defi-explained.dev/dydx/funding-rates/
- GMX fees/funding docs: https://docs.gmx.io/docs/trading/fees/
- GMX API overview: https://docs.gmx.io/docs/api/overview/
- GMX market API notes: https://docs.gmx.io/docs/api/rest-api/markets/
- Jupiter Swap API docs: https://dev.jup.ag/docs
- Jupiter quote endpoint via bloXroute docs: https://docs.bloxroute.com/solana/trader-api/api-endpoints/jupiter/quotes
- CoinMarketCap smart-money tracking overview: https://coinmarketcap.com/academy/article/how-to-track-smart-money-in-the-crypto-space
- Polymarket API docs: https://docs.polymarket.com/api-reference
- HackMD Arbiter / LP LVR notes: https://hackmd.io/%40arbiter/HyqTeyafyl
- HackMD MEV overview: https://hackmd.io/%400xapriori/r1stc3zPi
- Flashbots MEV-Share repo: https://github.com/flashbots/mev-share
- Uniswap V3 flash swap guide: https://developers.uniswap.org/docs/protocols/v3/guides/flash-swaps/getting-started

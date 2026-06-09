# Cross-Asset Factor Watchlist - 2026-06-07

Purpose: collect 100 candidate factors recently discussed or implied in public crypto/on-chain and equity research/sharing from roughly 2026-03-07 to 2026-06-07. This is a research shelf, not a live strategy list.

## Read This First

- Treat every factor as untrusted until it survives our own backtest with fees, slippage, borrow/funding, gas, failed fills, and delisted/dead tokens.
- For 10k USD capital, first priority is low-slippage, low-operational-risk signals: funding/basis, executable quote spreads, wallet/copy-trade paper simulation, and liquid equity/ETF factors.
- "Shared recently" means the factor theme appeared in recent articles, papers, HackMD/X/Reddit/GitHub/tooling pages, or public market reports. Some formula names are older academic factors, but included because they were explicitly re-discussed in recent 2026 materials.

## Recent Source Anchors

- On-chain cycle metrics: [CoinView, 2026-05-21](https://coinguan.com/en/articles/onchain-metrics-6.html), [Coinbase Charting Crypto Q2 2026](https://ctf-images-01.coinbasecdn.net/k3n74unfin40/6T2gPNDvHvBpf246ziwYTW/81039d2975a8c36c9e475c06a24a4455/Charting_Crypto_2Q26.pdf), [Bitcoin Mastery, 2026-05-05](https://www.bitcoin-mastery.com/article/bitcoin-onchain-metrics-guide-2026).
- Funding/basis: [Mithril, 2026-05-01](https://www.mithril.money/blog/funding-rate-arbitrage-passive-income-perp-dex), [Maxy Tools Funding Farm](https://maxy.tools/funding), [FundARB](https://fundarb.vercel.app/), [GitHub funding-rates topic](https://github.com/topics/funding-rates).
- DeFi yield and agents: [Ethena optimal-control paper, 2026-05-11](https://arxiv.org/abs/2605.11263), [DeFi yield aggregators paper, 2026-05-22](https://arxiv.org/abs/2605.23298), [DeFi agents paper, 2026-05-27](https://arxiv.org/abs/2605.29174).
- Prediction markets and copy-trade: [3EV HackMD, updated 2026-03-27](https://hackmd.io/4DqbpxrrQ3qNiH8xJVU6Ow), [Polymarket API](https://docs.polymarket.com/api-reference), recent X posts on Polymarket wallet/copy analysis.
- DEX/MEV execution risk: [DEX arb scanner Reddit discussion, 2026-04-26](https://www.reddit.com/r/CryptoTradingBot/comments/1sw0f2g/we_spent_9_months_building_a_dex_arbitrage_scanner/), [Base L2 MEV HackMD](https://hackmd.io/%40Devpablo/Hyxf3JuGwWl), [UniswapX HackMD](https://hackmd.io/enreCCCNS4qztCe-VOxmcg).
- Equity factors: [NBER Mosaics of Predictability, Apr/May 2026](https://www.nber.org/papers/w35158), [SSRN Intramonth Momentum Cycle, 2026-03-23](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6426026), [SSRN Emerging Markets six-factor paper, 2026-04-20](https://papers.ssrn.com/sol3/Delivery.cfm/6584161.pdf?abstractid=6584161&mirid=1&type=2), [LSEG Equity Factor Insights April 2026](https://www.lseg.com/en/ftse-russell/market-insights/equity-factor/april-2026), [SSGA May 2026](https://www.ssga.com/sg/en/institutional/insights/systematic-active-monthly-may-2026), [Nasdaq May 2026 review](https://www.nasdaq.com/articles/may-2026-review-and-outlook), [J.P. Morgan Factor Views 2Q 2026](https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/portfolio-insights/factor-views.pdf).

## Priority Legend

- P1: build first, likely useful for scanner/backtest.
- P2: useful after data plumbing.
- P3: research-only or high false-positive risk.

## 100 Candidate Factors

| ID | Area | Factor | Measurement sketch | Priority | Main risk |
|---:|---|---|---|---|---|
| 001 | On-chain cycle | MVRV ratio | Market value / realized value, z-scored by asset history | P2 | Slow regime signal, bad for intraday timing |
| 002 | On-chain cycle | MVRV z-score | Distance of market cap from realized cap normalized by historical std | P2 | Cycle fitting and BTC dominance bias |
| 003 | On-chain cycle | NUPL state | Net unrealized profit/loss bucket, e.g. capitulation/fear/hope/greed | P2 | Lagging ownership layer |
| 004 | On-chain cycle | SOPR reset | Spent output profit ratio below/above 1, plus slope | P2 | UTXO labels and exchange batching noise |
| 005 | On-chain cycle | Short-term holder SOPR | SOPR for young coins or short-term holder cohort | P2 | Harder data availability |
| 006 | On-chain cycle | Realized price distance | Spot / realized price minus 1 | P2 | Better for sizing than entry |
| 007 | On-chain cycle | Supply in profit band | Percent supply in profit vs rolling z-score bands | P2 | Top/bottom bands change by cycle |
| 008 | On-chain cycle | Dormancy flow | Coin-days destroyed adjusted by market cap | P3 | Sparse, slow, chain-specific |
| 009 | On-chain cycle | HODL-wave shift | Share of supply moving from old to young cohorts | P3 | Interpretation is ambiguous |
| 010 | On-chain cycle | Miner reserve pressure | Miner reserves / miner outflow change | P3 | Mostly BTC-specific |
| 011 | CEX/on-chain flow | Exchange netflow | Inflow minus outflow to labeled CEX wallets | P1 | Wallet labeling errors |
| 012 | CEX/on-chain flow | Exchange reserve drawdown | Rolling change in CEX balances | P1 | Custody migration false positives |
| 013 | CEX/on-chain flow | Whale-to-exchange intensity | Large deposits to exchanges as pct of volume | P1 | Whales may hedge, not sell |
| 014 | CEX/on-chain flow | Exchange outflow dispersion | Number of unique withdrawal addresses and concentration | P2 | Airdrop/custody redistribution |
| 015 | CEX/on-chain flow | Stablecoin exchange inflow | Net stablecoin deposits to exchanges | P1 | Could be collateral, not spot buying |
| 016 | CEX/on-chain flow | Stablecoin supply growth | Change in circulating USDT/USDC/PYUSD/FDUSD supply | P2 | Macro/corporate issuance lag |
| 017 | CEX/on-chain flow | Stablecoin dry-powder ratio | Stablecoin market cap / crypto market cap | P2 | Regime dependent |
| 018 | CEX/on-chain flow | Bridge-to-CEX lag | Bridge inflows followed by CEX deposits within N hours | P2 | Requires entity clustering |
| 019 | CEX/on-chain flow | Deposit age destruction | Age/value of coins deposited to exchange | P2 | UTXO limited for BTC-like chains |
| 020 | CEX/on-chain flow | ETF/custody wallet divergence | ETF issuer custody flow vs whale exchange flow | P2 | Custody wallet tagging |
| 021 | Wallet/copy | Smart-wallet net accumulation | Net buys of historically profitable wallets | P1 | Address rotation and crowding |
| 022 | Wallet/copy | Wallet PnL persistence | Rank-correlation of wallet PnL across rolling windows | P1 | Survivorship bias |
| 023 | Wallet/copy | Wallet profit factor | Gross wins / gross losses after fees | P1 | Hidden off-chain hedges |
| 024 | Wallet/copy | Wallet win rate by market type | Win rate split by perps, memecoins, prediction, blue chips | P1 | Aggregated win rate hides specialization |
| 025 | Wallet/copy | Wallet holding-period edge | Median holding time of winners vs losers | P1 | Hard to infer intent |
| 026 | Wallet/copy | Leverage discipline | Avg leverage, liquidation distance, margin usage | P1 | Venue-specific data |
| 027 | Wallet/copy | Overtrading penalty | Trades per day vs risk-adjusted PnL | P1 | Market maker wallets look noisy |
| 028 | Wallet/copy | Copy decay curve | Simulated PnL with 15s/60s/5m/30m delay | P1 | Needs honest execution model |
| 029 | Wallet/copy | First-100 buyer quality | New token early buyers scored by past PnL and rug exposure | P2 | Heavy survivorship/rug bias |
| 030 | Wallet/copy | Wallet cluster co-buy | Multiple high-quality wallets buying same asset within window | P2 | Coordinated shill clusters |
| 031 | Wallet/copy | Address freshness risk | New/rotated address share in a wallet cluster | P2 | Good traders rotate too |
| 032 | Wallet/copy | Anti-smart-money signal | Fade wallets with stable negative expectancy | P2 | Negative expectancy may be hedged |
| 033 | Perps/funding | Funding rate level | Current funding annualized by venue and symbol | P1 | Current rate may not settle |
| 034 | Perps/funding | Cross-venue funding spread | Long low/negative funding venue, short high funding venue | P1 | Basis divergence and liquidation |
| 035 | Perps/funding | Net funding after fees | Funding spread minus taker/maker fees and expected slippage | P1 | Fee tier assumptions |
| 036 | Perps/funding | Funding stability half-life | How long positive spreads persist historically | P1 | Regime shifts |
| 037 | Perps/funding | Next-funding timing | Expected return conditional on minutes to funding timestamp | P1 | Crowded unwind |
| 038 | Perps/funding | Spot-perp basis | Perp mid / spot mid minus 1 | P1 | Funding can reverse |
| 039 | Perps/funding | Perp-perp basis | Mid price spread between two perp venues | P1 | Withdrawal/collateral constraints |
| 040 | Perps/funding | Borrow-rate adjusted carry | Funding income minus spot borrow/financing cost | P1 | Borrow availability changes |
| 041 | Perps/orderflow | Open interest delta | OI change over 5m/1h/1d with price direction | P1 | OI is not side-specific |
| 042 | Perps/orderflow | OI / volume crowding | Open interest divided by rolling volume | P1 | False crowding in quiet markets |
| 043 | Perps/orderflow | Funding/OI divergence | High OI with neutralizing funding or vice versa | P2 | Ambiguous positioning |
| 044 | Perps/orderflow | Liquidation cluster distance | Distance to high notional liquidation bands | P1 | Heatmaps are estimates |
| 045 | Perps/orderflow | Long-short account ratio | Account or top-trader L/S ratios by venue | P2 | Retail-heavy and noisy |
| 046 | Perps/orderflow | Taker CVD | Rolling taker-buy minus taker-sell quantity | P1 | Needs trade data, not L2 proxy |
| 047 | Perps/orderflow | CVD-price divergence | Price makes high/low not confirmed by CVD | P2 | Divergence can persist |
| 048 | DEX/arb | Executable DEX-CEX spread | Best DEX quote vs CEX executable quote after all costs | P1 | Quotes stale before fill |
| 049 | DEX/arb | Route edge after gas | Multi-hop route edge minus estimated gas and priority fee | P1 | Gas bidding competition |
| 050 | DEX/arb | AMM reserve imbalance | Pool price vs reference mid, adjusted by depth | P1 | Arbitraged quickly |
| 051 | DEX/arb | Price impact slope | Slippage curve for 1k/5k/10k notional | P1 | Nonlinear route splitting |
| 052 | DEX/arb | Quote staleness | Milliseconds since reserve snapshot or quote timestamp | P1 | Infrastructure-dependent |
| 053 | DEX/arb | Revert/fail probability | Historical failure rate by route, token, gas regime | P1 | Sparse route history |
| 054 | DEX/arb | Mempool pending imbalance | Pending swaps net direction in target pool | P3 | Private flow missing |
| 055 | DEX/arb | Sandwich risk score | Pool liquidity, victim size, slippage tolerance, gas regime | P2 | Private orderflow opacity |
| 056 | DEX/arb | Route concentration | Herfindahl share of route liquidity across pools | P2 | Route APIs may hide alternatives |
| 057 | DEX/arb | 3-hop decay | Simulated edge minus live fill edge for multi-hop paths | P1 | Requires execution logs |
| 058 | DEX/arb | Oracle/TWAP deviation | Spot pool price vs oracle/TWAP/reference index | P2 | Oracle lag and manipulation |
| 059 | DEX/arb | Private relay availability | Expected inclusion/fill advantage via private route | P3 | Access and trust assumptions |
| 060 | DeFi yield | Lending APY spread | Supply APY difference for same asset across protocols | P1 | Incentive APY and risk not equal |
| 061 | DeFi yield | Borrow-supply carry | Borrow low on A, lend high on B after collateral cost | P2 | Liquidation and oracle risk |
| 062 | DeFi yield | Utilization kink distance | Current utilization distance to rate-model kink | P1 | Sudden utilization spikes |
| 063 | DeFi yield | Stablecoin depeg spread | Stablecoin price deviation vs liquidity and redemption route | P1 | Tail risk, not free money |
| 064 | DeFi yield | Liquidation queue pressure | Borrow positions near liquidation by collateral asset | P2 | Requires protocol-level state |
| 065 | DeFi yield | TVL flow momentum | Protocol/chain TVL inflow over 1d/7d/30d | P2 | Mercenary incentives |
| 066 | DeFi yield | Incentive-adjusted APR quality | Organic fees/APR share vs token emissions share | P1 | Token rewards can dump |
| 067 | DeFi yield | Protocol revenue / TVL | Fees or revenue divided by TVL | P2 | Revenue definitions differ |
| 068 | LP | LP fee APR minus LVR | Fee income minus loss-versus-rebalancing estimate | P1 | Needs high-quality pool data |
| 069 | LP | Concentrated range pressure | Price distance to LP range boundaries and liquidity cliffs | P2 | Range inventory risk |
| 070 | LP | Emission dilution pressure | Upcoming emissions/unlocks relative to float and volume | P2 | Schedule changes |
| 071 | Token/event | Token unlock overhang | Unlock notional / 30d dollar volume / free float | P1 | OTC/vesting exceptions |
| 072 | Token/event | Airdrop claim sell pressure | Claimable amount, claimed pct, CEX deposits after claim | P1 | Claim behavior can be nonlinear |
| 073 | Token/event | New listing momentum | Return/volume pattern after CEX listing or perp launch | P2 | Pump-and-dump risk |
| 074 | Token/event | Upbit/Korea listing impulse | Korea venue listing news plus kimchi premium | P2 | Liquidity fragmentation |
| 075 | Token/event | Sector relative strength | Token return vs sector basket, e.g. AI/RWA/DePIN/L2/perp DEX | P1 | Narrative overfitting |
| 076 | Token/event | Developer activity surprise | GitHub commits/releases vs trailing baseline | P3 | Easy to game |
| 077 | Token/event | Governance catalyst | Proposal voting, fee switch, buyback, emission change | P2 | Governance failure |
| 078 | Token/event | Buyback/revenue support | Protocol buybacks or fee burns vs market cap | P2 | Revenue cyclicality |
| 079 | Token/event | Hack/exploit contagion | Exposure graph to exploited protocol, bridge, oracle, stablecoin | P1 | News and labels lag |
| 080 | Token/event | Treasury accumulation | DAO/corporate treasury net buys/sells of token or ETH/BTC | P2 | Treasury moves may be symbolic |
| 081 | Prediction | Cross-market probability spread | Same event probability across Polymarket/Kalshi/venue clones | P1 | Fees, settlement, rules mismatch |
| 082 | Prediction | YES/NO sum mispricing | YES best ask + NO best ask below or above 1 after fees | P1 | Fill and resolution risk |
| 083 | Prediction | Stale news reaction | Price move delay after timestamped external news | P1 | Latency competition |
| 084 | Prediction | Last-minute volume imbalance | Net aggressive flow near event close/resolution | P2 | Manipulation and late info |
| 085 | Prediction | Top-trader category edge | Wallet PnL by category, e.g. sports, politics, crypto 15m | P1 | Category regime changes |
| 086 | Prediction | Wallet specialization entropy | Lower entropy across categories may indicate real specialization | P2 | Small sample |
| 087 | Prediction | Depth-adjusted probability gap | Edge divided by order-book depth and slippage | P1 | Thin books look attractive |
| 088 | Prediction | Resolution ambiguity risk | Text/rule ambiguity score, oracle dependence, dispute history | P1 | Non-priceable tail risk |
| 089 | US equity | 12-1 momentum | 12-month return excluding last month | P1 | Momentum crashes |
| 090 | US equity | 1-month reversal | Prior 1-month return, cross-sectional negative signal | P1 | Tax/month-end/calendar effects |
| 091 | US equity | 52-week high proximity | Price / 52w high | P1 | Crowded breakout false starts |
| 092 | US equity | Intramonth momentum cycle | WML exposure only in pre-turn-of-month window | P1 | Calendar anomaly decay |
| 093 | US equity | Earnings surprise | Standardized unexpected earnings or post-earnings drift | P1 | Announcement timing/data quality |
| 094 | US equity | Earnings revision | Analyst EPS estimate upgrades/downgrades over 1m/3m | P1 | Analyst herding |
| 095 | US equity | Earnings-price value | Earnings yield, E/P, with sector neutralization | P1 | Value traps |
| 096 | US equity | Book-to-market value | Book equity / market cap | P2 | Accounting staleness |
| 097 | US equity | Gross profitability | Gross profit / assets or sales | P1 | Sector bias |
| 098 | US equity | Quality stability | ROE stability, accruals, leverage, earnings volatility | P1 | Mega-cap concentration |
| 099 | US equity | Low volatility / beta | Low realized volatility or low market beta | P1 | Rate-sensitive drawdowns |
| 100 | US equity | Low-volume predictability | Return predictability stronger in low trading-volume stocks | P2 | Capacity and transaction costs |

## First Filters I Would Apply

1. Keep P1 only for the first coding pass: 56 factors.
2. Split into four buckets: funding/basis, wallet/copy, executable spreads, and US equity liquid factors.
3. Reject anything whose gross edge is below twice estimated transaction cost.
4. For wallet/copy factors, require a delay curve. A signal that only works at zero-latency is not a signal for us.
5. For DEX arb factors, require live-paper fills, not reserve-snapshot backtests.
6. For US equities, test sector-neutral and market-neutral versions before making directional claims.

## Most Interesting Starting Subset

- Funding spread: 033-040.
- True order flow: 041-047.
- Wallet copy lab: 021-028.
- Executable quote scanner: 048-053 and 057.
- Prediction market relative value: 081-088.
- US equity liquid starter pack: 089-095, 097-099.

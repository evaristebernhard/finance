# Polymarket NegRisk Basket Arbitrage

Date: 2026-06-08

This is the second prediction-market strategy lane after the wallet delayed-copy
paper ledger. It is more structural: instead of predicting a market, it scans
multi-outcome NegRisk events for all-YES basket mispricing.

The scanner is read-only. It never signs orders or touches private keys.

## Core Idea

For a truly exhaustive multi-outcome event where exactly one outcome resolves
YES, buying one YES share in every outcome costs:

\[
C = \sum_i p_i + \sum_i f_i
\]

where the taker fee for leg \(i\) is estimated from the market's Gamma
`feeSchedule`:

\[
f_i = q_i \cdot r_i \cdot p_i(1-p_i)
\]

For one basket share, the payout is \(1\). Therefore:

\[
\text{edge} = 1 - C
\]

For target payout \(Q\):

\[
\text{PnL} = Q - \sum_i \text{fill_cost}_i - \sum_i \text{fee}_i
\]

The practical scanner must also verify:

- the Gamma event is actually `negRisk`;
- the event detail is not truncated;
- any `Other`/catch-all outcome is active and executable;
- every required YES token has enough CLOB ask depth;
- the fee-adjusted edge is still positive.

## Script

```powershell
python scripts/polymarket_negrisk_basket_arbitrage_scan.py --self-test
```

Small live scan:

```powershell
python scripts/polymarket_negrisk_basket_arbitrage_scan.py --output-dir output/polymarket_negrisk_basket_arbitrage_scan_20260608_fee_schedule_smoke --event-limit 25 --candidate-limit 8 --book-event-limit 3 --target-payout-usd 100 --min-gamma-edge-cents -10 --http-timeout 15 --sleep-ms 20
```

Outputs:

```text
event_baskets.csv
basket_legs.csv
summary.json
summary.md
```

## Important Bug Found And Fixed

The first live scan found an apparent fee-adjusted positive subset:

```text
Presidential Election Winner 2028
36 active outcomes
target payout: 100 USD
fee-adjusted active-subset profit: +2.71 USD
```

That was not a real arbitrage.

Reason: the high-level Gamma `/events` list only included 36 markets, but the
full event detail contained 128 markets, including an `Other` outcome. The
`Other` market was not an active executable leg in the book scan. Therefore the
36-leg basket is only an active subset, not an exhaustive set. If an unbought
outcome wins, the basket is not protected.

The scanner now records:

```text
detail_market_count
has_other_market
has_active_other_leg
executable_exhaustive
tradable_candidate
```

Only rows with `tradable_candidate=True` should be considered real basket
arbitrage candidates.

## 2026-06-08 Fixed Smoke Result

Run:

```powershell
python scripts/polymarket_negrisk_basket_arbitrage_scan.py --output-dir output/polymarket_negrisk_basket_arbitrage_scan_20260608_fee_schedule_smoke --event-limit 25 --candidate-limit 8 --book-event-limit 3 --target-payout-usd 100 --min-gamma-edge-cents -10 --http-timeout 15 --sleep-ms 20
```

Result:

- Candidate events: 8.
- Live book events requested: 3.
- Fee-adjusted non-negative live subsets: 1.
- Executable exhaustive fee-adjusted candidates: 0.

Top row after the fix:

```text
Presidential Election Winner 2028
num_outcomes loaded for active legs: 36
full detail_market_count: 128
has_other_market: True
has_active_other_leg: False
executable_exhaustive: False
tradable_candidate: False
active-subset target_profit_usd: +2.7067
```

This is exactly the right behavior: the scanner preserves the interesting
mispricing signal, but refuses to call it executable arbitrage.

## Strategy Status

Current status: promising scanner, no live-ready positive basket found in the
small 2026-06-08 smoke sample.

This lane is still better than wallet-copy for capital deployment because a
true positive row would be structural rather than behavioral. The next useful
step is to run the scanner repeatedly and alert only when:

```text
tradable_candidate=True
target_profit_usd > execution_buffer
min_available_shares >= target_payout_usd
book_error_count = 0
```

Suggested buffer before any live discussion:

```text
target_edge_cents >= 1.0
target_profit_usd >= 1.00 per 100 USD payout
```

## Next Implementation Step

Add a scheduled forward collector:

```text
poll Gamma events
-> fetch full event detail for NegRisk candidates
-> fetch CLOB asks for only plausible positive Gamma-edge events
-> append immutable scan rows
-> alert only for tradable_candidate=True
```

That would turn this from a one-shot research script into a real arbitrage
watcher.

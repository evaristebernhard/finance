# Polymarket Strategy Research Fresh Scan - 2026-06-09

Generated after commit `c8ecdeee`.

Scope: read-only public data. No private keys, no signing, no orders.

The goal of this pass was to avoid being locked into the earlier CopyFlow idea and compare three distinct strategy families:

1. Structural NegRisk / multi-outcome baskets.
2. Deterministic range baskets.
3. Binance-close independent EV signals.

## Commit Baseline

Committed strategy toolkit:

```text
c8ecdeee feat: add polymarket strategy research toolkit
```

Verification before commit passed:

```text
self-test ok x8
uvx pytest tests/test_polymarket_copyflow_forward.py -q
3 passed in 0.31s
```

The commit intentionally excluded unrelated dirty worktree state such as `rpc.txt`, `date/` deletions, CCUSDT replay exchange changes, `.gitmodules`, and external repo checkouts.

## Fresh Scans Run

### NegRisk broad scan

```bash
python scripts/polymarket_negrisk_basket_arbitrage_scan.py \
  --output-dir output/polymarket_negrisk_basket_arbitrage_scan_20260609_broad \
  --event-limit 150 \
  --candidate-limit 40 \
  --book-event-limit 15 \
  --target-payout-usd 100 \
  --min-gamma-edge-cents -15 \
  --min-book-edge-cents -5 \
  --include-heuristic-events \
  --http-timeout 20 \
  --sleep-ms 25
```

Summary:

```text
Candidate events: 40
Live book events requested: 15
Fee-adjusted non-negative live subsets: 4
Executable exhaustive fee-adjusted candidates: 3
```

Top rows from the scanner:

| rank | title | evidence | tradable | target_profit_usd | concern |
|---:|---|---|---|---:|---|
| 1 | What price will Ethereum hit on June 8? | heuristic_exhaustive_candidate | True | +98.7161 | already/near settled; heuristic; detail markets exceed executable legs |
| 2 | What price will Bitcoin hit on June 8? | heuristic_exhaustive_candidate | True | +98.5021 | already/near settled; heuristic; detail markets exceed executable legs |
| 3 | Bab el-Mandeb Strait effectively closed by...? | heuristic_exhaustive_candidate | True | +40.8073 | heuristic; detail markets exceed executable legs |
| 4 | Presidential Election Winner 2028 | event_negRisk | False | +0.3008 | real NegRisk signal but not executable exhaustive: 128 detail markets vs 36 active legs |

Interpretation:

- The top `tradable=True` rows are not strategy candidates yet. They are scanner false-positive / stale-market stress tests.
- The important research finding is that high apparent basket edge can come from stale/near-settled markets or incomplete event-detail handling.
- The real native NegRisk row with positive subset edge remains `Presidential Election Winner 2028`, but it is still correctly rejected because the full event detail has many more markets than executable active legs.

Decision:

```text
Structural baskets are still the highest-quality strategy family, but the scanner needs stronger rule and lifecycle gates before alerts:
- reject events whose end/settlement time is already past or too close;
- require native event_negRisk for execution-grade basket alerts;
- require detail_market_count == executable leg count, or an explicit explainable active-set rule;
- treat heuristic_exhaustive_candidate as research-only;
- separately model stale/near-settled markets because they create huge false edges.
```

### Range basket broad scan

```bash
python scripts/polymarket_range_basket_arbitrage_scan.py \
  --output-dir output/polymarket_range_basket_arbitrage_scan_20260609_broad \
  --event-limit 220 \
  --page-size 100 \
  --book-event-limit 25 \
  --target-shares 100 \
  --min-markets 3 \
  --max-markets 40 \
  --min-profit-usd -5 \
  --http-timeout 20 \
  --sleep-ms 25
```

Summary:

```text
Range events: 3
Live book events requested: 25
Buy-all-YES non-negative candidates: 0
Buy-all-NO non-negative candidates: 0
```

Top rows:

| title | buckets | best direction | best_profit_usd |
|---|---:|---|---:|
| Bitcoin price on June 9? | 11 | buy_all_yes | -8.2825 |
| Ethereum price on June 9? | 11 | buy_all_yes | -21.5550 |
| XRP price on June 10? | 11 | buy_all_yes | -97.3366 |

Then a wider `--query price` scan:

```text
Range events: 5
Buy-all-YES non-negative candidates: 0
Buy-all-NO non-negative candidates: 0
```

Top rows:

| title | best_profit_usd |
|---|---:|
| Bitcoin price on June 9? | -8.5144 |
| Bitcoin price on June 10? | -21.7435 |
| Ethereum price on June 9? | -25.7488 |
| Solana price on June 9? | -36.5226 |
| XRP price on June 10? | -171.423 |

Interpretation:

- Gamma/display probabilities can show attractive all-No/all-Yes inconsistencies, but executable CLOB asks eliminate them.
- Range-basket arbitrage is worth monitoring but not worth spending most research time on unless an alert loop finds real CLOB-positive baskets.

Decision:

```text
Keep range basket as a watchdog, not as the primary strategy.
```

### Binance-close independent EV scans

Broad 360-minute volatility lookback:

```bash
python scripts/polymarket_binance_close_signal_scan.py \
  --output-dir output/polymarket_binance_close_signal_scan_20260609_broad \
  --event-limit 180 \
  --market-limit 120 \
  --book-token-limit 120 \
  --target-notional-usd 100 \
  --vol-lookback-minutes 360 \
  --min-minutes-to-settle 5 \
  --max-hours-to-settle 48 \
  --min-edge-cents -2 \
  --min-expected-profit-usd -1 \
  --http-timeout 20 \
  --sleep-ms 25
```

Summary:

```text
Server time UTC: 2026-06-09T05:50:54+00:00
Parsed markets: 34
Signal rows: 68
Candidate rows: 16
Symbols: BTCUSDT, ETHUSDT
```

Top row:

```text
BTC Jun 10 > 66000 YES
model_prob: 0.102685
avg_price: 0.0811597
expected_profit_usd: +20.0913 per 100 USD notional
ROI: +20.09%
```

Intraday 60-minute volatility lookback:

```bash
python scripts/polymarket_binance_close_signal_scan.py \
  --output-dir output/polymarket_binance_close_signal_scan_20260609_intraday \
  --event-limit 180 \
  --market-limit 120 \
  --book-token-limit 120 \
  --target-notional-usd 100 \
  --vol-lookback-minutes 60 \
  --min-minutes-to-settle 5 \
  --max-hours-to-settle 12 \
  --min-edge-cents -2 \
  --min-expected-profit-usd -1 \
  --http-timeout 20 \
  --sleep-ms 25
```

Summary:

```text
Server time UTC: 2026-06-09T05:59:10+00:00
Parsed markets: 23
Signal rows: 46
Candidate rows: 9
Symbols: BTCUSDT, ETHUSDT
```

Robust positives that were positive under both 60m and 360m volatility assumptions:

| min expected PnL | 60m PnL | 360m PnL | symbol | side | market |
|---:|---:|---:|---|---|---|
| +0.996 | +9.620 | +0.996 | BTCUSDT | No | Bitcoin above $64,000 on June 9? |
| +0.855 | +0.940 | +0.855 | BTCUSDT | Yes | Bitcoin above $60,000 on June 9? |
| +0.186 | +0.186 | +0.186 | BTCUSDT | Yes | Bitcoin above $58,000 on June 9? |
| +0.186 | +0.186 | +0.186 | ETHUSDT | No | Ethereum above $1,900 on June 9? |
| +0.154 | +2.176 | +0.154 | ETHUSDT | Yes | Ethereum above $1,600 on June 9? |
| +0.093 | +0.093 | +0.093 | ETHUSDT | Yes | Ethereum above $1,500 on June 9? |

Rows that flipped sign between 60m and 360m lookbacks:

| 60m PnL | 360m PnL | side | market |
|---:|---:|---|---|
| +6.953 | -1.677 | Yes | Bitcoin above $62,000 on June 9? |
| +0.717 | -0.267 | No | Bitcoin above $66,000 on June 9? |
| +0.459 | -0.237 | No | Ethereum above $1,800 on June 9? |

Interpretation:

- The Binance-close lane is currently more actionable than CopyFlow because it has an independent settlement variable and explicit model-vs-CLOB ask edge.
- However, several attractive rows are highly volatility-assumption sensitive.
- The most robust rows are either deep ITM/OTM low-edge rows or moderate BTC/ETH close thresholds with positive edge under both short and long volatility windows.

Decision:

```text
Promote Binance-close EV to the primary next research lane, but not live execution.
Add settlement verification and multi-vol ensemble gates before any dry-run:
- require positive expected PnL under 60m, 180m, and 360m volatility;
- require edge_cents >= 0.25 and expected_profit_usd >= 0.50 per 100 USD;
- reject rows with probability too close to 0 or 1 unless fee-adjusted edge survives a conservative stress haircut;
- after settlement, record realized outcome and compare calibration by bucket.
```

## Strategy Ranking After This Pass

1. `Binance-close independent EV` - best near-term research target.
   - Reason: explicit external reference price, independent EV, measurable settlement.
   - Weakness: model calibration and volatility-regime sensitivity.

2. `Structural NegRisk baskets` - best eventual low-model-risk strategy.
   - Reason: true positive row would be deterministic.
   - Weakness: event completeness and stale/near-settled false positives are dangerous.

3. `CopyFlow` - useful as a behavioral factor, not a standalone strategy.
   - Reason: prior backtest showed positive delayed-copy edge.
   - Weakness: executable fill realism still needs forward book collection.

4. `Range baskets` - watchdog only for now.
   - Reason: all recent executable CLOB baskets are negative after fees.

## Next Implementation Suggestions

Priority A: build a close-EV ensemble paper runner.

```text
scan rows with 60m/180m/360m volatility
join rows by market/outcome
require all-model positive or robust-min positive
write ensemble_signals.csv
later run settlement verifier and produce calibration report
```

Priority B: harden NegRisk scanner.

```text
add event end-time/freshness gate
separate native event_negRisk from heuristic candidates
reject detail_market_count != executable leg count unless a rule explicitly proves inactive legs are impossible
mark already-settled / stale high-profit rows as false-positive diagnostics
```

Priority C: keep CopyFlow collector running.

```text
CopyFlow is not abandoned, but it should become a confirmation factor or wallet-flow regime feature layered onto independent EV rows.
```

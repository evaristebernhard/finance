# Polymarket Binance Close And Range Basket Notes

Date: 2026-06-08

This note records two read-only Polymarket strategy lanes:

- short-horizon Binance-close probability signals;
- deterministic basket checks for mutually-exclusive price-range markets.

No wallet secrets are used. No orders are signed or submitted.

## Lane 1: Binance Close Probability Signal

Script:

```powershell
python scripts/polymarket_binance_close_signal_scan.py --self-test
python scripts/polymarket_binance_close_settlement_verify.py --self-test
```

The scanner targets markets whose rules resolve from the Binance 1-minute
final close. It estimates:

\[
P(S_T > K)
\]

from current Binance Vision price and recent 1-minute log-return volatility,
then compares that probability with live Polymarket CLOB ask depth:

\[
\text{expected\_profit}
= q \cdot p_\text{model} - C_\text{fill} - F_\text{taker}.
\]

The fee model is:

\[
F_\text{taker}
= q \cdot r \cdot a(1-a),
\]

where \(q\) is shares, \(r\) is the market fee rate, and \(a\) is the fill
price.

Smoke run:

```powershell
python scripts/polymarket_binance_close_signal_scan.py --output-dir output/polymarket_binance_close_signal_scan_20260608_smoke --event-limit 100 --market-limit 40 --book-token-limit 40 --target-notional-usd 100 --vol-lookback-minutes 180 --min-edge-cents 0 --min-expected-profit-usd 0 --http-timeout 20 --sleep-ms 40
```

Result at Binance server time `2026-06-08T14:00:01Z`:

- Parsed markets: 40.
- Signal rows: 80.
- Candidate rows: 5.
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT.
- Top expected paper PnL was only `+$0.5865` per `100 USD` target notional.

Top candidate rows:

| rank | symbol | side | question | model_prob | avg_price | expected_profit_usd |
|---:|---|---|---|---:|---:|---:|
| 1 | ETHUSDT | Yes | Ethereum above 1600 on June 8 | 0.999311 | 0.993000 | 0.586537 |
| 2 | ETHUSDT | No | Ethereum above 1800 on June 8 | 0.999994 | 0.997000 | 0.279348 |
| 3 | BTCUSDT | Yes | Bitcoin above 64000 on June 8 | 0.406357 | 0.389000 | 0.184936 |
| 4 | BTCUSDT | Yes | Bitcoin above 62000 on June 8 | 0.982958 | 0.979786 | 0.182267 |
| 5 | BTCUSDT | Yes | Bitcoin above 60000 on June 8 | 0.999997 | 0.999000 | 0.092835 |

Settlement verification:

```powershell
python scripts/polymarket_binance_close_settlement_verify.py --signals-csv output/polymarket_binance_close_signal_scan_20260608_smoke/signals.csv --output-dir output/polymarket_binance_close_signal_scan_20260608_smoke --http-timeout 20 --sleep-ms 0
```

Verifier result at `2026-06-08T14:06:12Z`:

- Rows: 80.
- Settled rows: 0.
- Pending rows: 80.
- Candidate rows: 5.
- Required re-run time: after `2026-06-08T16:01:00Z`.

Status: not live-ready. The current edge is thin and needs post-settlement
paper verification before any execution discussion.

## Lane 2: Mutually-Exclusive Range Basket

Script:

```powershell
python scripts/polymarket_range_basket_arbitrage_scan.py --self-test
```

For an exhaustive event with \(N\) mutually-exclusive buckets where exactly one
bucket resolves Yes:

\[
\text{buy\_all\_yes\_profit}
= Q - \sum_i C^\text{yes}_i - \sum_i F^\text{yes}_i.
\]

Buying all No shares is also deterministic:

\[
\text{buy\_all\_no\_profit}
= (N-1)Q - \sum_i C^\text{no}_i - \sum_i F^\text{no}_i.
\]

This matters for markets like `XRP price on June 10?`, because the visible
web probabilities can look inconsistent while executable CLOB asks are not
actually positive.

Run:

```powershell
python scripts/polymarket_range_basket_arbitrage_scan.py --output-dir output/polymarket_range_basket_arbitrage_scan_20260608_xrp_jun10_slugfast --slug xrp-price-on-june-10-2026 --book-event-limit 1 --target-shares 100 --http-timeout 20 --sleep-ms 0
```

Result:

- Event: `XRP price on June 10?`.
- Buckets: 11.
- Target: 100 shares per bucket.
- Buy-all-YES CLOB best-ask sum: `4.281`.
- Buy-all-NO CLOB best-ask sum: `10.732`.
- Buy-all-YES fee-adjusted paper PnL: `-335.7913 USD`.
- Buy-all-NO fee-adjusted paper PnL: `-79.1406 USD`.
- Non-negative executable candidates: 0.

Important observation:

- Gamma `outcomePrices` implied a positive all-No edge of about `+130.9`
  cents per 1-share basket.
- Live CLOB asks reversed that signal: the executable all-No basket lost
  about `7.914` cents per payout dollar after fees.

Therefore the screenshot-style range market is not an executable arbitrage
unless the live CLOB ask basket, not the displayed probabilities, is positive.

## Current Gate

Only promote a row from research to live discussion if all of the following
are true:

- CLOB asks are complete for every required leg.
- Fee-adjusted profit is positive after a safety buffer.
- Minimum available shares cover the target size.
- No leg has a book error.
- For probability signals, at least one forward settlement batch has verified
  realized paper PnL.

Suggested starting buffers:

```text
range basket: target_profit_usd >= 1.00 per basket run
close signal: expected_profit_usd >= 0.25 per 100 USD and edge_cents >= 0.25
```

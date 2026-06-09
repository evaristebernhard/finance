# Polymarket Wallet Factor Lab

Date: 2026-06-07

This is the first implementation lane for Polymarket wallet copyability
research. It is read-only and paper-only: no private keys, no authenticated
trade routes, and no live orders.

## What Was Built

Script:

```powershell
python scripts/polymarket_wallet_factor_probe.py
```

Default output directory:

```text
output/polymarket_wallet_factor_probe/
```

Tables:

- `wallet_scores.csv`: wallet-level copyability proxies.
- `market_suitability.csv`: market/outcome liquidity, ambiguity, and capacity.
- `follow_candidates.csv`: recent buy trades that pass v0 filters.
- `trade_edges.csv`: BUY trade rows with delayed next-trade price proxies for
  causal paper simulation.
- `summary.md`: run summary and top rows.
- `raw_snapshot.json`: compact metadata and top rows.

## Public Data Inputs

- Polymarket Data API `/trades`: recent public trades with
  `proxyWallet`, `side`, `asset`, `conditionId`, `size`, `price`, `timestamp`,
  `title`, `slug`, `eventSlug`, and `outcome`.
- Polymarket Data API `/activity`: per-wallet public trade history for seed
  wallets selected from the recent global trade stream.
- Polymarket Gamma API `/events`: active event/market metadata, tags,
  descriptions, end dates, liquidity, prices, and CLOB token IDs.
- Polymarket CLOB API `/book`: current order book snapshot for selected outcome
  tokens.

The script does not call authenticated endpoints and does not read `.env`,
private keys, or browser sessions.

## V0 Factor Definitions

For a wallet `w`, trade `k`, asset/outcome token `a`, and delay `d`:

```text
ProxyEdge_{k,d} = P_next_trade(a, t_k + d) - P_entry,k
```

Only BUY trades are emitted as copy candidates in v0. SELL trades are kept in
wallet behavior counts, but simple copying of SELLs would require position or
opposite-outcome logic that v0 intentionally avoids.

Wallet copy-decay:

```text
CopyDecay_w(300s)
  = mean(ProxyEdge_{w,0s}) - mean(ProxyEdge_{w,300s})
```

Delay-robust edge:

```text
DelayRobustEdge_w
  = min(mean(ProxyEdge_{w,30s}),
        mean(ProxyEdge_{w,120s}),
        mean(ProxyEdge_{w,300s}))
```

Category specialization:

```text
CategorySpecialization_w
  = max_c Sharpe(ProxyEdge_{w,c,300s})
    - Sharpe(ProxyEdge_{w,not-c,300s})
```

One-hit penalty:

```text
OneHitWonderPenalty_w
  = max(PositiveProxyPnL_w) / sum(PositiveProxyPnL_w)
```

Current-book capacity for notional `q`:

```text
CapacityOK(q) =
  enough current ask depth for q
  and average fill slippage <= max_capacity_slippage_cents
```

Liquidity-adjusted copy edge:

```text
LiquidityAdjustedCopyEdge
  = mean(ProxyEdge_{w,300s})
    / max(current_spread_cents + slippage_1k_cents, 0.01)
```

## Default Risk Filters

- `CopyPnL(5m)` proxy must be positive.
- Wallet must have at least three 5-minute-evaluable BUY trades.
- One-hit penalty must be `<= 0.75`.
- Rule ambiguity score must be below `4.0`.
- Candidate rows require current `capacity_1000_ok=True` by default. Use
  `--allow-unknown-capacity` only for diagnostics.
- Candidate rows are only BUY trades from the latest 24h sample.

## Run Profiles

Fast smoke:

```powershell
python scripts/polymarket_wallet_factor_probe.py --trade-limit 500 --book-token-limit 20
```

No orderbook collection:

```powershell
python scripts/polymarket_wallet_factor_probe.py --trade-limit 5000 --skip-books
```

More serious public scan:

```powershell
python scripts/polymarket_wallet_factor_probe.py --trade-limit 10000 --wallet-history-wallets 80 --wallet-history-limit 300 --top-wallets 100 --book-token-limit 150
```

Self-test:

```powershell
python scripts/polymarket_wallet_factor_probe.py --self-test
```

Paper strategy layer:

```powershell
python scripts/polymarket_delayed_copy_paper_strategy.py --probe-output-dir output/polymarket_wallet_factor_probe
python scripts/polymarket_delayed_copy_parameter_sweep.py --probe-output-dir output/polymarket_wallet_factor_probe
```

## Known Limitations

- Historical order books are not available from the public CLOB API unless we
  collect them ourselves or use a third-party archive.
- The delayed price is a next-public-trade proxy, not a guaranteed executable
  fill.
- The public `/trades` endpoint may stop paging before the requested trade
  limit; v0 records the actual parsed count in `summary.md`.
- Current orderbook depth may not represent depth at historical signal time.
- Address-level quote lifecycle, maker identity, and hidden off-chain hedges are
  not reconstructed.
- This is a research scanner; it should run for at least two weeks of paper
  records before any live-trade discussion.

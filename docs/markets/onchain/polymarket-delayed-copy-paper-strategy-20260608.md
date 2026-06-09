# Polymarket Delayed-Copy Paper Strategy

Date: 2026-06-08

This is the first causal paper-ledger layer on top of the Polymarket wallet
factor probe. It is still read-only and paper-only: no private keys, no signed
orders, no live execution.

## Artifacts

Scripts:

```powershell
python scripts/polymarket_wallet_factor_probe.py --self-test
python scripts/polymarket_delayed_copy_paper_strategy.py --self-test
python scripts/polymarket_delayed_copy_parameter_sweep.py --probe-output-dir output/polymarket_wallet_factor_probe_20260608_smoke
```

New probe output:

```text
output/polymarket_wallet_factor_probe_20260608_smoke/trade_edges.csv
```

Paper outputs from this run:

```text
output/polymarket_delayed_copy_paper_strategy_20260608_smoke/
output/polymarket_delayed_copy_paper_strategy_20260608_fade_smoke/
output/polymarket_delayed_copy_parameter_sweep_20260608_smoke/
output/polymarket_delayed_copy_paper_strategy_20260608_top_sweep_config/
output/polymarket_delayed_copy_paper_strategy_20260608_top_sweep_config_marketcap100/
```

## Math

For a wallet BUY signal at time \(t\), outcome token \(a\), entry delay
\(d_{in}\), and exit delay \(d_{out}\):

\[
P_{in} = P_{\text{next trade}}(a, t+d_{in}), \qquad
P_{out} = P_{\text{next trade}}(a, t+d_{out})
\]

Copy mode buys the same outcome:

\[
\text{edge}_{copy} = 100(P_{out} - P_{in}) - C
\]

Fade mode approximates buying the binary complement:

\[
\text{edge}_{fade} = 100((1-P_{out}) - (1-P_{in})) - C
                 = 100(P_{in} - P_{out}) - C
\]

For stake \(S\), executed prices \(E_{in}\) and \(E_{out}\):

\[
\text{shares} = \frac{S}{E_{in}}, \qquad
\text{PnL} = \text{shares}(E_{out} - E_{in})
\]

The decision rule is causal: at signal time \(t\), wallet history only includes
prior rows whose \(t_i+d_{out} \le t\). The current signal's future price is
used only to close the paper ledger row, not to decide entry.

## 2026-06-08 Smoke Result

Input scan:

```powershell
python scripts/polymarket_wallet_factor_probe.py --output-dir output/polymarket_wallet_factor_probe_20260608_smoke --trade-limit 500 --wallet-history-wallets 20 --wallet-history-limit 100 --top-wallets 50 --book-token-limit 20 --http-timeout 20 --sleep-ms 60
```

The command hit the 120s shell timeout after writing files, but the output
directory contained a complete summary and `trade_edges.csv`.

Counts:

- Merged trades used for factors: 2361.
- BUY trade edge rows: 2326.
- Follow candidates under old strict capacity filter: 0.
- Book errors: 7.

Baseline copy, 30s entry and 120s exit:

```powershell
python scripts/polymarket_delayed_copy_paper_strategy.py --probe-output-dir output/polymarket_wallet_factor_probe_20260608_smoke --output-dir output/polymarket_delayed_copy_paper_strategy_20260608_smoke --entry-delay-seconds 30 --exit-delay-seconds 120 --category crypto --min-prior-trades 3 --min-prior-mean-net-edge-cents 0.5 --min-prior-win-rate 0.55 --max-prior-one-hit-penalty 0.75 --stake-usd 100 --max-stake-usd 100
```

Result:

- Closed paper trades: 3.
- Net PnL: -166.83 USD.
- ROI on deployed notional: -55.61%.
- Win rate: 0%.

Baseline fade with the same risk filters:

- Closed paper trades: 6.
- Net PnL: -48.52 USD.
- ROI on deployed notional: -8.09%.
- Win rate: 66.67%.

Exploratory sweep best row:

- Direction: fade.
- Entry/exit: 30s / 120s.
- Prior trades: 2.
- Prior mean net edge: at least 5 cents.
- Prior win-rate: at least 50%.
- Max one-hit penalty: 1.0.
- Closed paper trades: 6.
- Net PnL: +35.19 USD.
- ROI on deployed notional: +5.87%.
- Profit factor: 1.37.

That row is not robust enough to trade. The profit mostly came from three
same-time, same-market wallet signals. When single-market open exposure was
cut from 300 USD to 100 USD, the same configuration became:

- Closed paper trades: 3.
- Net PnL: -57.86 USD.
- ROI on deployed notional: -19.29%.

## Current Conclusion

The profitable-looking result is a fragile hypothesis, not a verified edge.
The useful signal from this run is more specific:

```text
short-horizon crypto Up/Down markets may contain fadeable wallet bursts,
but wallet-cluster concentration and one-hit dependence dominate the edge.
```

The next forward-paper version should therefore use:

- `direction=fade`, not blind copy.
- Entry delay 30s and exit delay 120s as the first hypothesis.
- Single-market exposure cap of 100 USD until cluster risk is measured.
- Minimum prior sample materially above two trades before any live discussion.
- Explicit cluster penalty for wallets entering the same condition within the
  same minute.
- Actual complement token book checks before treating \(1-P\) as executable.
- At least 50 closed forward-paper trades before calling the strategy
  investable.

## Next Implementation Step

The next useful code change is a forward collector that runs the probe on a
schedule and appends immutable paper decisions before outcomes mature:

```text
public trades/books
-> decision snapshot at time t
-> pending paper entries
-> delayed close after d_out
-> daily wallet/cluster report
```

Until that exists, this lane remains a research scanner, not a trading bot.

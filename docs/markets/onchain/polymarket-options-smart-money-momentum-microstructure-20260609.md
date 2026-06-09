# Polymarket Options + Smart Money + Momentum + Microstructure Strategy Pass

Date: 2026-06-09

Scope: read-only research. No private keys, no signing, no orders.

## 1. Goal

This pass combines four strategy layers:

```text
binary option / independent EV
+ smart-money wallet flow
+ short-horizon momentum
+ CLOB microstructure
```

The key principle is that no single layer is enough:

```text
options EV says whether the price is mathematically wrong;
smart money says whether informed flow agrees;
momentum says whether public order flow is moving the same way;
microstructure says whether execution is plausible.
```

## 2. New Joiner

Implemented:

```text
scripts/polymarket_combined_strategy_join.py
tests/test_polymarket_combined_strategy_join.py
```

Inputs:

```text
ensemble_signals.csv      # Binance-close EV ensemble
follow_candidates.csv     # smart-money wallet flow candidates
```

Output:

```text
combined_candidates.csv
summary.json
summary.md
```

Composite score:

```text
combined_score =
  ev_score
+ smart_flow_score
+ momentum_score
+ microstructure_score
- rule_penalty
```

Main reject reasons:

```text
not_ensemble_candidate
no_same_side_smart_flow
opposite_smart_flow
weak_microstructure
high_rule_risk
combined_score_too_low
```

## 3. Fresh Wallet Probe For Join

Run:

```bash
python scripts/polymarket_wallet_factor_probe.py \
  --trade-limit 3000 \
  --wallet-history-wallets 50 \
  --wallet-history-limit 180 \
  --top-wallets 80 \
  --gamma-event-limit 100 \
  --book-token-limit 80 \
  --sleep-ms 25 \
  --http-timeout 18 \
  --output-dir output/polymarket_wallet_factor_probe_20260609_join
```

Summary:

```text
Global recent trades parsed: 3000
Wallet activity trades parsed: 8989
Merged unique trades: 11134
Time span: 2026-06-05T18:49:34Z -> 2026-06-09T07:24:30Z
Wallets scored: 80
Eligible wallets: 23
Markets/assets scored: 1855
Markets with 1k capacity: 30
Follow candidates: 205
BUY trade edge rows: 9149
```

Follow candidate categories:

```text
crypto: 136
sports: 35
other: 30
politics: 4
```

A looser crypto-focused run:

```bash
python scripts/polymarket_wallet_factor_probe.py \
  --trade-limit 2500 \
  --wallet-history-wallets 50 \
  --wallet-history-limit 160 \
  --top-wallets 80 \
  --gamma-event-limit 120 \
  --book-token-limit 80 \
  --sleep-ms 20 \
  --http-timeout 18 \
  --output-dir output/polymarket_wallet_factor_probe_20260609_join_crypto \
  --allow-unknown-capacity \
  --min-wallet-buy-trades 1 \
  --min-5m-edge-cents -5 \
  --max-one-hit-penalty 1.0
```

Produced 574 follow candidates, mostly crypto, but they were mostly short-horizon Up/Down markets rather than the same Binance-close threshold token ids used by the EV ensemble.

## 4. Combined Join Result

Run:

```bash
python scripts/polymarket_combined_strategy_join.py \
  --ensemble-csv output/polymarket_binance_close_ensemble_20260609_live/ensemble_signals.csv \
  --follow-candidates-csv output/polymarket_wallet_factor_probe_20260609_join/follow_candidates.csv \
  --output-dir output/polymarket_combined_strategy_join_20260609 \
  --min-combined-score 0
```

Summary:

```text
Rows: 68
Accepted candidates: 0
Reject counts:
  no_same_side_smart_flow: 68
  not_ensemble_candidate: 66
  combined_score_too_low: 16
```

Top rows were still dominated by options EV and microstructure, with no matching same-side smart-money flow:

| rank | score | reject | ev | smart | momentum | micro | market |
|---:|---:|---|---:|---:|---:|---:|---|
| 1 | 14.53 | no_same_side_smart_flow | 13.37 | 0 | 0 | 1.15 | BTC > 64000 Jun 9 NO |
| 2 | 9.73 | no_same_side_smart_flow | 8.59 | 0 | 0 | 1.14 | BTC > 62000 Jun 9 YES |
| 3 | 6.11 | not_ensemble_candidate;no_same_side_smart_flow | 5.17 | 0 | 0 | 0.94 | BTC > 60000 Jun 10 YES |

## 5. Interpretation

This is an important negative result, not a failure.

The four-factor stack did not produce accepted candidates because the currently strongest smart-money flow is not in the same claim family as the strongest independent EV rows.

Observed mismatch:

```text
EV ensemble candidates:
  BTC/ETH threshold close claims, e.g. BTC above 64000 on Jun 9

Wallet flow candidates:
  mostly short-horizon crypto Up/Down windows, sports, weather, politics
```

Therefore, token-id exact join is too strict for the deeper strategy we want.

The correct next model is not:

```text
same token_id smart flow confirms EV
```

It is:

```text
claim graph / underlying-time join:
  same underlying
  nearby settlement horizon
  logically related direction
  compatible price/momentum implication
```

Example:

```text
wallets buying BTC Up in 3:20-3:25 AM windows
may confirm BTC intraday momentum
which may support BTC above/below threshold claims expiring later
```

But this requires mapping Up/Down claims, threshold claims, and range claims into a shared latent variable:

```text
underlying = BTCUSDT
state variable = S_T or short-horizon return
claim direction = bullish/bearish
expiry / window
```

## 6. Strategy Implication

The combined strategy should evolve from token-level join to claim-level graph join.

### Current v1 join

```text
EV token_id == smart-flow asset
```

Good for exact same market confirmation, but sparse.

### Needed v2 join

```text
same underlying
+ compatible direction
+ time-window overlap / lead-lag relation
+ claim implication relation
```

This unlocks:

```text
options EV + smart money in related Up/Down markets
options EV + range bucket pressure
options EV + YES/NO parity pressure
options EV + microstructure momentum
```

## 7. Next Research Direction

Implement a claim-normalization layer:

```text
scripts/polymarket_claim_graph.py
```

It should parse each market into:

```text
claim_type: threshold_close | range_bucket | up_down | negrisk | other
underlying: BTCUSDT/ETHUSDT/SOLUSDT/...
direction: bullish/bearish/neutral
start_time
settle_time
strike/lower/upper
outcome_token
```

Then build joins at the claim level:

```text
threshold EV row
+ recent Up/Down smart flow on same underlying
+ range bucket implied CDF pressure
+ CLOB microstructure
```

This is the path toward the user's hypothesis:

```text
Polymarket prediction types alone may define enough mathematical constraints to build a portfolio.
```

## 8. Current Actionable Conclusion

Do not trade the combined stack yet.

The best current paper candidates remain pure EV ensemble rows:

```text
BTC > 64000 Jun 9 NO
BTC > 62000 Jun 9 YES
```

But without same-claim smart-money confirmation, they should be treated as independent EV paper candidates only.

For smart money, the most useful next step is not more wallet ranking. It is claim normalization so wallet flow can confirm related claims rather than exact token ids.

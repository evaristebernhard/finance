# Polymarket CopyFlow Forward Collector + Book Replay v1

Date: 2026-06-09

Scope: implement Priority 1 from `docs/markets/onchain/polymarket-copyflow-tardis-options-roadmap-20260609.md`.

Boundary: read-only public data. No private keys, no signing, no live orders.

## Files Added

```text
scripts/polymarket_copyflow_collect.py
scripts/polymarket_copyflow_book_replay.py
tests/test_polymarket_copyflow_forward.py
```

## 1. Forward Collector

Script:

```text
scripts/polymarket_copyflow_collect.py
```

Purpose:

```text
public recent trades
+ tracked wallet activity
+ Gamma market metadata
+ Polymarket CLOB book snapshots
-> SQLite store
```

Default DB:

```text
output/polymarket_copyflow_forward/polymarket_copyflow.sqlite
```

The initial version writes to `output/` rather than `data/` to respect the root AGENTS.md safety rule about not modifying `data/` unless explicitly requested.

Tables:

```text
trades_raw
wallet_activity_raw
markets_raw
asset_books
asset_book_levels
tracked_wallets
collector_state
```

Useful commands:

```bash
# self-test only
python scripts/polymarket_copyflow_collect.py --self-test

# one-shot public collection
python scripts/polymarket_copyflow_collect.py \
  --db-path output/polymarket_copyflow_forward/polymarket_copyflow.sqlite \
  --recent-trade-limit 500 \
  --seed-wallets-from-recent 20 \
  --wallet-limit 50 \
  --wallet-activity-limit 100 \
  --gamma-event-limit 80 \
  --book-asset-limit 80

# loop collection every 60s, bounded to 240 iterations
python scripts/polymarket_copyflow_collect.py \
  --loop \
  --interval-seconds 60 \
  --iterations 240 \
  --db-path output/polymarket_copyflow_forward/polymarket_copyflow.sqlite
```

Notes:

- `--wallet` can be repeated for explicit wallets.
- `--asset` can be repeated for explicit token ids to snapshot books.
- `--seed-wallets-from-recent` tracks active wallets discovered from recent public trades.
- CLOB books are snapshotted into `asset_books` and `asset_book_levels`; this is what replay uses for historical VWAP.

## 2. Historical CLOB VWAP Book Replay

Script:

```text
scripts/polymarket_copyflow_book_replay.py
```

Purpose:

```text
CopyFlow signal rows
+ SQLite historical CLOB snapshots
-> paper ledger with ask VWAP entry and bid VWAP exit
```

Default inputs:

```text
--db-path output/polymarket_copyflow_forward/polymarket_copyflow.sqlite
--signals-csv output/polymarket_wallet_factor_probe_deep_20260608/trade_edges.csv
```

Fill model:

```text
entry_ts = signal_ts + entry_delay_seconds
entry = buy from ask-side VWAP near entry_ts
exit_ts = signal_ts + exit_delay_seconds
exit = sell to bid-side VWAP near exit_ts
```

Freshness guard:

```text
--max-book-age-seconds 30
```

Useful commands:

```bash
# self-test only
python scripts/polymarket_copyflow_book_replay.py --self-test

# replay against collected book DB
python scripts/polymarket_copyflow_book_replay.py \
  --db-path output/polymarket_copyflow_forward/polymarket_copyflow.sqlite \
  --signals-csv output/polymarket_wallet_factor_probe_deep_20260608/trade_edges.csv \
  --output-dir output/polymarket_copyflow_book_replay \
  --entry-delay-seconds 30 \
  --exit-delay-seconds 300 \
  --stake-usd 100 \
  --max-book-age-seconds 30
```

Outputs:

```text
paper_ledger.csv
skipped_signals.csv
summary.json
```

Important limitation:

```text
This replay only works for time windows where the collector has book snapshots.
It should not be used to replay old CopyFlow signals unless historical books were collected at those timestamps.
```

## 3. Tests

Test file:

```text
tests/test_polymarket_copyflow_forward.py
```

Covered behaviors:

```text
collector dedupes trades
collector persists book snapshots and levels
book replay picks nearest fresh snapshot
buy uses ask-side VWAP
sell uses bid-side VWAP
stale/missing books are skipped
CopyFlow signal becomes closed paper ledger when entry/exit books exist
```

Verification run:

```text
python scripts/polymarket_copyflow_collect.py --self-test
python scripts/polymarket_copyflow_book_replay.py --self-test
python -m py_compile scripts/polymarket_copyflow_collect.py scripts/polymarket_copyflow_book_replay.py tests/test_polymarket_copyflow_forward.py
uvx pytest tests/test_polymarket_copyflow_forward.py -q
```

Actual result:

```text
self-test ok
self-test ok
3 passed in 0.16s
```

## 4. Next Step

Run the collector continuously for 1-2 weeks, then compare:

```text
next-trade proxy CopyFlow backtest
vs
historical CLOB VWAP forward replay
```

The strategy should not advance to dry-run unless:

```text
copy still beats fade
VWAP/slippage-adjusted PnL is positive
PnL is not dominated by one wallet/event
book stale/insufficient-depth skips are acceptable
>= 100 closed paper trades or >= 1-2 weeks forward paper
```

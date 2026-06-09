# Strategy Feature State Parity

Status: implemented and validated on `2026-05-18`.

## Boundary

Runner remains exchange infrastructure:

```text
canonical market truth -> virtual clock -> public/private streams -> order ingress
-> latency -> fill -> portfolio -> compact event log
```

Strategy Bot owns feature state:

```text
market_quote / market_trade / optional market_l2_update / private fills
-> online_features.py
-> sparse submit_order / heartbeat checkpoints
```

Runner does not compute TFI, R5, four-cell states, labels, MFE/MAE, or PnL
features. Bot-provided `feature_snapshot` is logged as opaque diagnostic state.

## Snapshot Schema

Bot checkpoints use:

```text
ccusdt_online_feature_snapshot_v1
```

The snapshot includes:

```text
quote: spread_bps, mid_change, mid_change_bps, frames_since_mid_change
trade_flow: rolling trades, buy/sell qty, signed/abs qty, TFI, notional imbalance
l2: optional batch count, level counts, best bid/ask
closed_outcomes: closed-fill-only R5 shape state
four_cell_inputs: A/R5 and B/frames raw inputs
private_state: position/pending/order counters
```

`closed_outcomes` is pretrade-safe because it updates only from completed private
fills already observed by the bot.

## Diagnostic

Same-stream canonical parity:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py --repo-root . --date 2026-05-18
```

Run-log checkpoint parity:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py --repo-root . --date 2026-05-18 --run-dir systems/ccusdt_replay_exchange/runs/<run_id>
```

Checkpoint parity aligns by `feature_snapshot.local_ts_us`, not just by stream
sequence. This matters for `--arrival-mode timer`, where a private fill can occur
between two market events while using the last known quote/book.

## Latest Acceptance

Latest hardening report:

```text
systems/ccusdt_replay_exchange/runs/hardening_reports/hardening_20260520_122923.json
```

Key results:

```text
feature_state_quote_trade.ok = true
feature_state_l2_sample.ok = true
feature_state_run_checkpoints.ok = true
run_checkpoint_checks = 55
run_checkpoint_types = fill:1, heartbeat_interval:53, order_intent:1
```

Remaining limitation: this validates runtime feature inputs and checkpoint
causality. It does not validate market impact, queue priority, or whether a
specific strategy has edge.

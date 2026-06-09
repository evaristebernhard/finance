# Decision Frame And Panel Shadow Parity 2026-05-20

Goal: migrate the old four-cell CCUSDT TFI policy from panel-oracle diagnostics
to a runtime-safe Bot path without letting the Bot read legacy fixed panels,
`date/` scored entries, future labels, PnL, MFE, MAE, or root scripts.

## What Passed

`decision_frame_v1` is now built in:

```text
strategies/python/ccusdt_tfi_core_idle01/decision_frame.py
```

It consumes only exchange-visible trades and L2 updates, groups L2 by
`local_ts_us`, maintains the L2 book, applies the same crossed-book cleanup, and
reconstructs the old fixed-panel decision fields:

```text
local_timestamp
event_index
best_bid/ask price and amount
mid_price
spread_bps
trade_window_count
trade_flow_imbalance
frames_since_mid_change
past_event_25_bps
fwd_time_60s_bucket
```

Full canonical-vs-fixed-panel parity passed:

```text
run: systems/ccusdt_replay_exchange/runs/decision_frame_parity_20260520_142724
dates: 2026-05-16..2026-05-18
frames compared: 378908
row mismatches: 0
field mismatches: 0
```

Per day:

```text
2026-05-16 frames=132382 mismatches=0
2026-05-17 frames=114918 mismatches=0
2026-05-18 frames=131608 mismatches=0
```

## Shadow Policy Translation

`strategy.py` now supports:

```text
--decision-clock panel --shadow-four-cell
```

Panel mode evaluates the shadow policy only when the Bot builds a
`decision_frame_v1` from `market_l2_update`; it no longer evaluates the old
four-cell policy on every quote/trade event.

Direct panel shadow audit passed with diagnostic R5 warmup:

```text
run: systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_155504
dates: 2026-05-16..2026-05-18
entries: 764 / 764
exact timestamp matches: 764 / 764
feature mismatches: 0
```

Per day:

```text
2026-05-16 entries=261 timestamp_matches=261
2026-05-17 entries=199 timestamp_matches=199
2026-05-18 entries=304 timestamp_matches=304
```

Cell totals also match reference:

```text
00_none=305
10_r5_only=398
01_frames_only=21
11_r5_frames=40
```

This direct audit rebuilds decision frames from canonical L2 stream, not from
the legacy fixed panel as runtime input. It took roughly 12 minutes for
2026-05-16..2026-05-18 on this machine, so it should be treated as a slow
mathematical parity gate rather than a per-edit smoke.

## Important Caveats

`--warmup-reference-r5` is diagnostic-only. It seeds the last five closed R5
outcomes from the legacy reference to simulate a bot that had already been
running from the warmup period. Runtime must replace this with one of:

```text
1. replay warmup days through the Bot, or
2. persist Bot-owned closed-outcome state across runs.
```

Without warmup, 2026-05-18 still matches all 304 timestamps and memberships,
but the first two R5 cells are cold-start mismatches.

Runner+Bot stdin/stdout full-day panel audit now passes for the strict 2026-05-18
gate after compact L2 batching and diagnostic R5 warmup:

```text
run: systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_154315
runner run: systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260518_20260520_154315
mode: runner
decision clock: panel
compact L2: true
events seen: 258186
L2 batches seen: 131608
elapsed wall ms: 566812
entries: 304 / 304
exact timestamp matches: 304 / 304
feature mismatches: 0
cell counts: 00_none=112, 10_r5_only=168, 01_frames_only=10, 11_r5_frames=14
```

This proves the real Bot path can reproduce the 2026-05-18 fixed-panel shadow
decisions from canonical market events. It does not yet mean the three-day
Runner+Bot audit is cheap enough for default acceptance; at current bridge
throughput, a full 2026-05-16..2026-05-18 runner audit should be treated as a
long smoke or overnight gate. The direct same-stream audit remains the fast
three-day mathematical parity gate.

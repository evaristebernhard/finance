# CCUSDT Replay Exchange Hardening Report

Date: 2026-05-20.

Scope: verify that the experiment kernel is usable as a strategy-research
substrate before further strategy optimization.

Raw machine-readable output:

```text
systems/ccusdt_replay_exchange/runs/hardening_reports/hardening_20260520_20260520_015903.json
```

## Verdict

```text
PASS
```

The runner/bot/log core passed full-day quote+trade pressure, full-day L2
streaming pressure, deterministic replay comparison, compact event-log causal
audit, and online feature-state validation.

## Full-Day Quote + Trade

Input date:

```text
2026-05-18
```

Two independent Runner Server passes, no bot connected:

```text
events_seen       126578
quote_events_seen 120418
trade_events_seen 6160
final_stream_seq  126577
final_quote_seq   120417
```

Performance:

```text
pass A elapsed 1055 ms, events/sec 119979.147, peak RSS 23.324 MB
pass B elapsed  982 ms, events/sec 128898.167, peak RSS 23.188 MB
```

Determinism:

```text
normalized summaries equal: true
```

The ignored fields for determinism are run identity and port addresses. All
semantic counters and final account state matched.

## Full-Day L2 Streaming

Runner Server with canonical quote+trade+L2, no bot connected:

```text
events_seen       258186
quote_events_seen 120418
trade_events_seen 6160
l2_batches_seen   131608
final_stream_seq  258185
final_quote_seq   120417
```

Performance:

```text
elapsed     205953 ms
events/sec  1253.616
peak RSS       24.078 MB
```

Interpretation:

```text
L2 full-day streaming is bounded-memory for this date.
```

The run processed the full canonical L2 day without loading full-day L2 into a
Vec. Peak RSS stayed close to the quote+trade-only pass despite 131608 L2
batches.

During this test a useful pressure-path issue was found and fixed: when no
public client is connected and log mode is compact, Runner Server now skips
constructing and serializing dense market stream payloads. The exchange state,
book state, risk/fill path, and compact log remain unchanged.

## Compact Event Log Audit

No-order pressure runs:

```text
event_count 2
run_start -> run_end
audit ok true
```

Order-chain smoke:

```text
events_seen        1200
quote_events_seen  1125
trade_events_seen  75
intents_created    1
orders_submitted   1
fills_created      1
bridge_errors      0
```

Validated compact causal chain:

```text
order_intent
order_scheduled
order_arrived
order_ack
fill
```

The validator checks event-id monotonicity, run_start/run_end boundaries,
summary/log event-count agreement, chain order, arrival after target latency,
fill-price existence, slippage fields, and L2 depth sweep fields when present.

## Online Feature State

The Python online TFI state was replayed from canonical exchange-visible events
and compared to an independent same-stream reference.

Quote+trade full day:

```text
events_seen 126578
quote       120418
trade       6160
ok          true
```

Quote+trade with L2 sample:

```text
events_seen 126592
quote       120418
trade       6160
l2          14
l2 rows     5000
ok          true
```

Validated fields:

```text
signed_qty
abs_qty
TFI
spread_bps
mid_change
frames_since_mid_change
rolling_trades
l2_batches_seen
last_l2_bid_levels
last_l2_ask_levels
```

## Current Acceptance State

Passed:

```text
full-day quote+trade runner pressure
full-day L2 streaming bounded-memory pressure
deterministic replay comparison
compact event causal-chain validator
online feature-state validation
runtime leakage boundary scan from prior stage remains clean
```

Known limitation:

```text
full-day L2 with live public subscribers will still serialize dense L2 payloads
for the subscribers. That is correct behavior, but UI/monitor should not
subscribe to dense L2 unless explicitly needed.
```

Next recommended work:

```text
add a strategy experiment manifest format and run matrix
validate latency/slippage distributions under delayed taker IOC
add a small HTML/console monitor view only after experiment manifests are stable
```

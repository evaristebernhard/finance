# Event Contracts

Status: MVP contracts.

## Market Truth

`quote_frame_v1` is the replay clock base for the MVP:

```text
seq,exchange_ts_us,local_ts_us,bid_px,bid_qty,ask_px,ask_qty,mid_px,spread_bps
```

`trade_event_v1` is the canonical trade stream:

```text
seq,trade_id,exchange_ts_us,local_ts_us,side,price,qty,notional_quote
```

`l2_level_update_v1` is the canonical L2 update stream:

```text
seq,exchange_ts_us,local_ts_us,is_snapshot,side,price,qty
```

## Feature Sidecars

`feature_sidecar_v1` may join pretrade-safe values to canonical market time. It
must not include realized future return, post-entry path labels, or strategy PnL.

Future/post-trade outputs belong to `research_label_v1` and are excluded from
strategy runtime by default.

## Exchange Events

`order_event_v1` records accepted/rejected/canceled orders.

`fill_event_v1` records simulated fills.

`portfolio_state_v1` records account, position, equity, and leverage snapshots.

## Run Event Log

Runner output is append-only NDJSON:

```text
runs/<run_id>/events.ndjson
```

Each row uses this envelope:

```text
event_id,run_id,event_type,replay_seq,replay_ts,wall_ts_ms,source,payload
```

The toy runner emits `run_start`, `market_frame`, `portfolio_state`,
`strategy_decision`, `order_intent`, `order_scheduled`, `order_submitted`,
`order_accepted` or `order_rejected`, `fill_created`, `clock_advanced`, and
`run_end`.

The sparse exchange-style Python runner uses this strategy message envelope over
stdin/stdout NDJSON:

```json
{
  "type": "market_quote",
  "channel": "public",
  "run_id": "...",
  "seq": 123,
  "observed_seq": 123,
  "quote_seq": 55,
  "exchange_ts_us": 1779062476207000,
  "local_ts_us": 1779062476433743,
  "payload": {}
}
```

`seq` is the merged public/private stream sequence. `quote_seq` is the latest
canonical quote sequence used for top-of-book pricing. Trade and L2 messages use
their own `exchange_ts_us/local_ts_us`, not the quote timestamp.

The independent Runner Server uses the same envelope over local TCP NDJSON:

```text
public stream   market/control messages
private stream  account/order/fill messages
order ingress   submit_order/cancel_order/heartbeat
state query     read-only HTTP GET /health and /api/state
```

Monitor clients are read-only and connect only to public/private streams. They
may also read the HTTP state endpoint. They must not connect to or know the
order ingress channel.

The current default ports are:

```text
public  127.0.0.1:8801
private 127.0.0.1:8802
order   127.0.0.1:8803
state   optional, for example 127.0.0.1:8804
```

Runtime inputs allowed for Python:

```text
session_start
market_quote
market_trade
market_l2_update
market_batch
account_snapshot
order_ack
order_reject
fill
session_end
```

Runtime outputs allowed from Python:

```text
heartbeat
submit_order
cancel_order
```

`hold` is accepted only for dense compatibility modes. The sparse bot should not
answer every market event.

Sparse runtime outputs may include a diagnostic-only feature snapshot:

```json
{
  "feature_snapshot": {
    "schema_id": "ccusdt_online_feature_snapshot_v1",
    "runtime_safe": true
  }
}
```

Runner treats this as opaque bot-owned state. It may write
`strategy_feature_checkpoint` and `order_intent.feature_snapshot` to the compact
run log, but it must not compute strategy factors or use the snapshot for fills,
risk, clock control, or market truth.

`submit_order` is taker-first in sparse stream v1: `execution_role=taker`,
`kind=market`, `tif=ioc`, `qty>0`. Maker-aware fields are reserved in the
contract (`execution_role=maker_reserved`, `post_only`, `maker_profile_id`,
`queue_model_id`, `max_rest_us`, and `queue_reservation_id`), but the runner
hard-rejects them today. They are schema placeholders for a later maker
lifecycle/queue model, not active maker PnL or queue alpha.

The runner schedules accepted taker intents by timestamp latency and only then
submits to the exchange:

```text
target_arrival_local_ts_us = observed_local_ts_us + effective_latency_us
default arrival = exact virtual timer target using last known quote/book
next-event stress = first market stream event with local_ts_us >= target
deterministic_replay_v1:
  effective_latency_us = latency_us
  wall clock is recorded only, never fill-affecting

wall_latency_pressure_v1:
  effective_latency_us = latency_us + wall_latency_staleness
  wall_latency_staleness = bridge_wall_latency_us * wall_latency_speedup
```

The two latency profiles are mutually exclusive. In deterministic replay, a late
Python response may increase `arrival_stream_lag`, but it must not change the
selected `arrival_quote` for the same `observed_local_ts_us + latency_us`
target. The deterministic audit gate requires `arrival_quote_lag=0` when
`latency_us=0` and `arrival_mode=timer`. Private order/fill/account stream
messages use the virtual arrival stream sequence; the actual stream sequence at
which Python was drained is recorded only as `drain_stream_seq`.

Private order/fill events include observed quote, arrival quote, fill price,
arrival spread, base latency, effective latency, optional wall-latency virtual
staleness, and latency slippage. Future labels, scored entries, PnL, MFE, and
MAE must not be runtime inputs.

Strict sparse runs may also emit `run_progress` from Runner. It is operational
heartbeat only:

```text
events_seen,max_events,final_stream_seq,pending_intents,counters,elapsed_wall_ms,event_rate_per_s
```

`run_progress` is allowed in compact logs because it does not enter the trading
path, does not affect the virtual clock, and carries no strategy labels. Runner
also periodically flushes `events.ndjson`; the flush cadence is reported in
`summary.timing_ms` together with market-read, bridge-write, bridge-drain,
order/fill, and progress timing.

`market_batch` is a transport optimization, not a new market truth. Its payload
is either `batched_public_v1` or `batched_public_barrier_v1` and contains
exchange-visible events in the exact order Runner would otherwise send them:

```json
{
  "type": "market_batch",
  "channel": "public",
  "seq": 1499,
  "payload": {
    "schema_id": "batched_public_v1",
    "seq_start": 1000,
    "seq_end": 1499,
    "events": []
  }
}
```

The bot must process `payload.events` sequentially and bind every intent to the
inner event's `observed_seq` and `observed_local_ts_us`. Runner still resolves
arrival/fill from the retained canonical observation window. A batch mode is
valid only if it passes a transport-equivalence gate against `strict_event`.

`batched_public_barrier_v1` adds a private-feedback barrier. The bot must stop
inside the batch when it emits `submit_order`, `submit_orders`, or
`cancel_order`, attach `consumed_seq` and `consumed_local_ts_us`, and leave the
remaining suffix unconsumed. Runner executes deterministic arrival/fill/private
events, then replays the suffix after the private feedback has been sent. If the
bot consumes the whole batch without an actionable response, it must emit
`batch_done` so Runner knows the batch is closed and does not race ahead on
wall-clock timing.

`panel_sparse_v1` is a strict-audit acceleration transport. It does not replace
`strict_event` or `batched_public_barrier_v1` as truth gates. Runner still reads
canonical quote/trade/L2 market truth, owns the virtual clock, arrival quote,
fill, portfolio, and event log; only the public payload sent to the bot is
sparse. Instead of every raw market event, Runner sends `market_decision_frame`
events derived from the validated `decision_frame_v1` cache:

```json
{
  "type": "market_decision_frame",
  "channel": "public",
  "payload": {
    "schema_id": "panel_sparse_v1",
    "decision_frame": {
      "schema_id": "decision_frame_v1",
      "runtime_safe": true,
      "local_ts_us": 1779062636310942,
      "observed_seq": 1144,
      "mid": 0.154065,
      "spread_bps": 0.6490766884,
      "trade_flow_imbalance": -1.0,
      "trade_window_count": 1,
      "frames_since_mid_change": 0.0,
      "past_event_25_bps": 0.3245436106,
      "fwd_time_60s_bucket": 3
    },
    "audit": {
      "source": "decision_frame_v1_parquet_cache",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1",
      "field_hash_sha256": "...",
      "cache_file_sha256": "...",
      "source_canonical": {}
    }
  }
}
```

`fwd_time_60s_bucket` in this runtime frame is the old panel bucket key used for
first-per-60s trigger de-duplication. It is not a forward-return label and does
not expose PnL, MFE, MAE, or post-entry path. The bot may evaluate the four-cell
shadow policy only on these frames, and every intent is still bound to
`observed_seq/observed_local_ts_us`. Runner resolves deterministic arrival/fill
from its retained canonical observation window. A `panel_sparse_v1` run is valid
only if it passes transport-equivalence against the full-stream truth gates.

`panel_sparse_fast_clock_v1` has the same public `market_decision_frame` shape,
but narrows Runner's internal clock source for the top-of-book strict audit:

```text
decision_frame_v1 cache -> decision clock
quote_frame_v1 last-known index -> timer arrival quote and fill price
full L2 stream -> not read
```

This mode is valid only with `top_of_book_taker_ioc_v1` and deterministic timer
arrival. It is not a replacement for full-stream `strict_event`,
`batched_public_barrier_v1`, or `panel_sparse_v1` when validating online feature
reconstruction, raw stream ordering, maker queue behavior, or L2 depth fills.
For same-timestamp raw events, Runner preserves the first stream seq at that
timestamp as an arrival observation so zero-latency timer fills match the
full-stream gate while still binding intents to the decision frame's own
`observed_seq`.

The important separation is:

```text
strategy intent != exchange order != fill
```

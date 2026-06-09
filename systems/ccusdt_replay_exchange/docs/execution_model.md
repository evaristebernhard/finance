# Execution Model

The sparse Python stream runner is taker-first:

```text
strategy observes event at observed_local_ts_us
runner schedules order for observed_local_ts_us + latency_us
default arrival time is the exact virtual timer target
top-of-book taker IOC market buy fills at latest arrival ask
top-of-book taker IOC market sell fills at latest arrival bid
```

The independent Runner Server uses the same model. The difference is process
ownership: Runner broadcasts public/private TCP NDJSON streams, and the bot sends
orders through a separate TCP ingress socket. Runner still owns virtual time,
latency, risk, fills, portfolio, and compact event logs.

Order arrival has two explicit modes:

```text
--arrival-mode timer       default research mode
--arrival-mode next-event  conservative stress mode
```

In `timer` mode:

```text
arrival_local_ts_us = observed_local_ts_us + effective_latency_us
fill state = last known quote/book before that virtual timer instant
```

If the timer fires between two market events, Runner fills before applying the
next market event. This is the realistic replay baseline for taker IOC.

In `next-event` mode:

```text
arrival_local_ts_us = first market event local_ts_us >= timer target
```

This intentionally adds market-event gap overshoot. It is useful as a harsh
latency stress test, not as the default research benchmark.

The console monitor is outside this path. It subscribes to public/private
streams only, aggregates state for display, and cannot submit orders.

The stream runner writes the full causal chain:

```text
order_intent -> order_scheduled -> order_arrived -> order_ack/order_reject
-> fill -> portfolio_state_on_change
```

`latency_slippage_bps` is signed as adverse slippage:

```text
buy  = ln(arrival_ask / observed_ask) * 10000
sell = ln(observed_bid / arrival_bid) * 10000
```

Default clock mode is `deterministic_step`; Python wall time is measured but
does not affect virtual arrival. The deterministic stdio bridge uses a tiny
settle poll so a sparse bot trigger is captured near the event that caused it.
Pressure mode is explicit:

```text
--clock-mode accelerated-async --wall-latency-speedup <k>
effective_latency_us = latency_us + bridge_wall_latency_us * k
```

This is a stress test for slow local strategy code, not the default research
benchmark.

The base exchange fill model remains deliberately small:

- market buy fills at current ask;
- market sell fills at current bid;
- crossing limit orders fill immediately as taker;
- resting limit orders fill when future quotes cross the limit;
- leverage risk is checked before order acceptance;
- fees are configured in basis points.

This model is useful for local paper-exchange plumbing, not queue-position proof.

`l2_taker_depth_v1` is available as an optional fill model:

```powershell
--include-l2 --fill-model l2-depth
```

It maintains a local book from `l2_level_update_v1`. Market buys sweep asks;
market sells sweep bids. Order/fill payloads include VWAP, depth slippage,
partial fill, remaining quantity, levels consumed, and reason. The default
model remains `top_of_book_taker_ioc_v1`.

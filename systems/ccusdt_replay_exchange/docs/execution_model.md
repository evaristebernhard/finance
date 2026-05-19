# Execution Model

The default Python stream runner is taker-first:

```text
strategy observes event at observed_local_ts_us
runner schedules order for observed_local_ts_us + latency_us
arrival frame is first quote with local_ts_us >= target arrival time
taker IOC market buy fills at arrival ask
taker IOC market sell fills at arrival bid
```

The stream runner writes the full causal chain:

```text
order_intent -> order_scheduled -> order_arrived -> order_ack/order_reject
-> fill_created -> portfolio_state
```

`latency_slippage_bps` is signed as adverse slippage:

```text
buy  = ln(arrival_ask / observed_ask) * 10000
sell = ln(observed_bid / arrival_bid) * 10000
```

Default clock mode is `deterministic_step`; Python wall time does not affect
virtual arrival. Pressure mode is explicit:

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

`l2_taker_depth_v1` is currently available as a smoke diagnostic when
`--include-l2 --l2-depth-smoke-qty` is supplied. It maintains a local book from
`l2_level_update_v1` and computes market-buy ask sweeps and market-sell bid
sweeps with VWAP, depth slippage, partial fill, remaining quantity, and reason.
It does not change the default top-of-book IOC fill model yet.

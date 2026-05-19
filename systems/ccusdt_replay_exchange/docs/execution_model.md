# Execution Model

The MVP uses a deliberately small fill model:

- market buy fills at current ask;
- market sell fills at current bid;
- crossing limit orders fill immediately as taker;
- resting limit orders fill when future quotes cross the limit;
- leverage risk is checked before order acceptance;
- fees are configured in basis points.

This model is useful for local paper-exchange plumbing, not queue-position proof.
The next execution upgrade should add latency, partial fills, and an L2 queue
model using `l2_level_update_v1` plus trades.


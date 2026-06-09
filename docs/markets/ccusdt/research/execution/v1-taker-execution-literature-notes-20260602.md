# CCUSDT Taker Execution Literature Notes

Status: `research_only_literature_synthesis_no_runtime_change`.

This note reads source-available optimal-execution papers through one project
question:

```text
When should CCUSDT cross the spread, how much should it cross, and when should it wait?
```

The answer is not a direct trading rule. The useful output is a set of
mathematical objects for the next S5/S6 diagnostic.

## 1. Current Project Problem

Current strict execution baseline is:

```text
top_of_book_taker_ioc_v1
```

For a long entry and exit, the executable return is:

```text
Y_long(u) = 10000 * log(exit_bid(u) / entry_ask)
```

For a short entry and exit:

```text
Y_short(u) = 10000 * log(entry_bid / exit_ask(u))
```

The gap from mid return is:

```text
Y_exe(u) ~= R_mid(u) - entry_cross_cost - exit_cross_cost - depth_or_latency_cost
```

Therefore a factor can explain mid release and still fail as a taker strategy.
This is exactly what recent structure-family diagnostics show: many S2/S3/S7
rows have positive mid/release evidence but become `spread-cost-mirage` after
top-of-book crossing.

The literature suggests that the decision variable should not be binary:

```text
trade / no trade
```

It should be:

```text
how much to cross now
how much to wait or post passively
how long to wait before fallback
```

## 2. Cont and Kukanov: Taker Size as Execution-Risk Control

Source:

```text
literature/taker_execution_sources/cont_kukanov_2012_optimal_order_placement/OrderRouting.tex
```

Their most useful object is an order allocation:

```text
X = (M, L_1, ..., L_K)
```

where `M` is market order quantity and `L_k` are passive limit quantities. In a
single venue adaptation for us:

```text
M_t = quantity crossed now
L_t = quantity left to wait/post
S_t = target quantity to exit or enter
```

Limit fills depend on queue ahead `Q` and future queue outflow `xi`:

```text
fill(L, Q, xi) = (xi - Q)_+ - (xi - Q - L)_+
```

Their expected-cost form can be translated to:

```text
cost(M,L)
  = explicit_cross_cost(M)
  - passive_spread_capture(fill(L,Q,xi))
  + impact_or_slippage(M,L)
  + lambda_u * underfill
  + lambda_o * overfill
```

For CCUSDT, `fee_bps=0` does not remove `explicit_cross_cost` because spread is
still paid. The paper's `lambda_u` is especially important: it is the opportunity
cost of not completing the trade. In our exit setting it corresponds to decay
risk:

```text
lambda_u(X_t) ~= expected decay or adverse move if we do not exit now
```

Project implication:

```text
S6 should not only be a low-spread admission gate.
S6 should estimate cross fraction:

M*_t / S_t = f(spread_t, opposite_depth_t, queue_outflow_hazard_t, decay_risk_t)
```

For now, because the strict model is pure top-of-book taker, the direct use is a
binary approximation:

```text
cross_now if edge_buffer_t > crossing_cost_t + lambda_tail_t
otherwise do not cross or reduce size
```

But the right future form is partial crossing.

## 3. Gueant, Lehalle, Fernandez-Tapia: Passive Exit as Fill-Hazard vs Price-Risk

Source:

```text
literature/taker_execution_sources/gueant_lehalle_fernandez_tapia_2011_limit_order_liquidation/Best_execution_review2.tex
```

The model treats passive order fills as a point process. The fill intensity
falls as the quoted price moves farther from a fair price:

```text
lambda(delta) = A * exp(-k * delta)
```

For CCUSDT exit, translate `delta` as the price improvement requested relative
to immediate crossing:

```text
delta = passive_exit_price - fair_or_touch_price
```

The central tradeoff is:

```text
higher delta -> better fill price but lower fill probability
lower delta  -> faster fill but less spread saving
market order -> guaranteed exit but pays spread immediately
```

Their HJB is too heavy for the first implementation, but the economic threshold
is simple:

```text
wait_value(delta, tau)
  = spread_saving(delta) * P(fill by tau | X_t)
  - decay_loss(tau | X_t)
  - adverse_selection(fill | X_t)
  - fallback_cross_cost(tau | X_t)
```

Project implication:

```text
S5 post-release exit/wait should estimate fill hazard and decay jointly.
```

This also explains our prior maker-first no-go: a positive wait result is not
automatically passive alpha. It must be decomposed into:

```text
delay-only mid continuation
passive spread saving
missed-fill decay
adverse selection after passive fill
fallback crossing cost
```

## 4. Bulthuis et al.: Continuous Market/Limit Control with Fill Uncertainty

Source:

```text
literature/taker_execution_sources/bulthuis_etal_2016_fill_uncertainty_limit_market_orders/Optimal_Execution_v17__July_23_2016_.tex
```

They use two controls over time:

```text
v_t = market order trading rate
L_t = limit order trading rate
```

Position evolves with deterministic depletion plus uncertain passive fills:

```text
dx_t = -v_t dt + (-L_t dt + m(L_t)dZ_t)
```

The useful project idea is not the continuous-time solution itself, but the
separation of costs:

```text
market impact / spread cost
limit fill uncertainty
adverse selection from fill-price correlation
terminal non-liquidation penalty
speed limiter
trade-direction consistency
```

For CCUSDT, this maps cleanly to a constrained exit controller:

```text
cross rate should increase when:
  residual position is large
  time-to-deadline is short
  fill uncertainty is high
  decay risk is high

cross rate should decrease when:
  spread/depth cost is high
  passive fill probability is high
  continuation alpha is favorable
```

Project implication:

```text
Do not treat wait/exit as one fixed horizon.
Treat it as a control with speed limits:

exit_now_qty <= cap_by_spread_depth_risk(X_t)
```

Even in pure taker mode, this supports a staged exit:

```text
partial cross now -> observe quote/flow -> cross remainder or wait
```

## 5. Lee and Lee: Depth-Aware Market Quantity

Source:

```text
literature/taker_execution_sources/lee_lee_2020_liquidity_risk_diffusive_order_book/Hyoeun_Kiseop_ArxivVer.tex
```

Their single-period model chooses:

```text
m = market order quantity
y = passive limit order placement level
M - m = passive quantity
```

They use a supply curve with half-spread `d`, depth `K`, and liquidity slope
`beta`:

```text
S(t,x) = S(t,0) - d - beta * (K + x)^-,    x < 0
```

For a sell market order, the first `K` shares do not walk deeper; beyond `K`,
the execution price worsens. This is directly relevant to future L2-depth fill
profiles, but even with top-of-book taker it gives the right state variable:

```text
order_size / opposite_depth
```

Their objective is expected cash flow over:

```text
initial market order
possible passive limit fill
fallback market order at horizon T
```

Project implication:

```text
S6 should use depth not as alpha, but as execution capacity.
```

The useful diagnostic field is:

```text
depth_saturation_t = requested_qty_t / opposite_top_depth_t
```

For current top-of-book strict mode, we intentionally do not walk L2, so this is
mostly an admission or size cap. For future L2-depth mode, it becomes direct
slippage.

## 6. Toth et al.: Predictable Flow Does Not Mean Large Taker Size

Source:

```text
literature/taker_execution_sources/toth_etal_2014_adaptive_liquidity_taking/Adaptive_Liquidity.tex
```

This paper is important for our TFI/R5 interpretation. It studies persistent
order flow and market efficiency. The key mechanism is asymmetric/adaptive
liquidity:

```text
when order-flow sign is predictable,
liquidity takers reduce market order penetration,
so predictable flow has lower price impact.
```

In their model, the market-order fraction relative to opposite best depth is
random, and the penetration probability depends on:

```text
epsilon_t * predicted_epsilon_t
```

The CCUSDT translation:

```text
high TFI predictability alone is not a reason to increase taker size.
```

Generic flow predictability can already be anticipated by liquidity providers
or fragmented by liquidity takers. What matters for our S1 is more specific:

```text
flow pressure exists
and price has not yet released
and execution cost is still acceptable
```

Project implication:

```text
TFI/R5 should be a pressure-memory primitive, not a size primitive.
Size should shrink when the flow is obvious but price release is no longer latent.
```

This supports the recent structure-family split:

```text
S1 = active-flow stale-release
S2/S3 = confirmation / vacuum
S6 = cost and size gate
S7 = volatility/decay risk
```

## 7. Non-Source Papers Still Worth Reading

No public LaTeX source was found in this pass for these, but they are still
conceptually useful:

| paper | role for CCUSDT |
| --- | --- |
| Harris and Hasbrouck, market vs limit orders | empirical warning that market orders are expensive after accounting for alternatives |
| Obizhaeva and Wang, supply/demand dynamics | resilience model: crossing now changes liquidity, and liquidity later recovers |
| Maglaras, Moallemi, Zheng, queueing LOB execution | queue/arrival-rate state variables for microstructure execution cost |

The Obizhaeva-Wang idea is especially useful for S5:

```text
wait is valuable only if liquidity or quote quality recovers faster than alpha decays.
```

## 8. Project-Level Model Proposal

The literature suggests the next execution model should estimate three objects.

### 8.1 Taker Admission Buffer

For an entry or exit candidate:

```text
edge_buffer_t
  = expected_mid_release_t
  - expected_decay_t
  - entry_cross_cost_t
  - exit_cross_cost_t
  - tail_penalty_t
```

Then:

```text
cross allowed only if edge_buffer_t > 0
```

This is a conservative S6 admission model.

### 8.2 Cross Fraction

If partial crossing is enabled later:

```text
m*_t = argmin_m [
    cross_cost(m, spread_t, depth_t)
  + wait_risk(S_t - m, X_t)
  + tail_penalty(m, X_t)
]
```

For now, top-of-book taker has only:

```text
m*_t in {0, S_t}
```

but diagnostics should already report the continuous proxy:

```text
requested_qty / opposite_depth
```

### 8.3 Exit Wait Value

For an open lot at state `X_t`, compare immediate taker exit to wait:

```text
G(tau | X_t)
  = E[Y_taker_exit(t + tau) - Y_taker_exit(t) | X_t]
  - tail_penalty(tau | X_t)
```

If passive or maker-aware exit is reconsidered:

```text
G_passive(tau, delta | X_t)
  = spread_saving(delta) * P(fill by tau | X_t)
  + delay_only_value(tau | X_t)
  - missed_fill_decay(tau | X_t)
  - adverse_selection(fill | X_t)
  - fallback_cross_cost(tau | X_t)
```

This is the S5 object. It explicitly prevents the old mistake:

```text
positive delayed exit value != passive maker alpha
```

## 9. Immediate Next Diagnostics

The next research pass should not implement full maker execution. It should add
diagnostic fields around existing top-of-book taker strict/fast runs:

```text
entry_cross_cost_bps
exit_cross_cost_bps
opposite_depth_top_quote
depth_saturation
quote_recovery_1s/2s/5s/10s
spread_recovery_1s/2s/5s/10s
post_release_decay_hazard
flow_predictability_score
penetration_or_depth_depletion_proxy
```

Then evaluate:

```text
S6: does cost/depth admission improve executable return without killing S1?
S5: does conditional wait improve exit after release under top-of-book taker?
size: does reducing exposure in obvious-flow/high-cost states improve tail?
```

Promotion remains blocked until:

```text
prior-date rule
fast-vs-strict profile equivalence
top-of-book executable labels
capacity and lot lifecycle audit
no runtime label leakage
```


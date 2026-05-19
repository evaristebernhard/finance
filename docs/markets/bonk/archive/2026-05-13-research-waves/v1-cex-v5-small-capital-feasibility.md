# BONK V5 Small-Capital Feasibility Framing

Status: 2026-05-13. Research-only framing over existing BONK Bullish L2 / Binance context outputs. This is not a trading rule, not an execution plan, not a sizing rule, not a trading recommendation, and not an alpha claim.

## Scope

Question: does a small account, specifically about `$100`, materially change the current BONK CEX/L2 conclusion?

Short answer: it helps only with the absolute capacity concern. It does not change the main research blockers, because fees, spread, slippage, lower-first path risk, and statistical uncertainty are measured in bps or event counts, not in account dollars.

Main inputs reviewed:

```text
docs/markets/bonk/README.md
docs/markets/bonk/v1-cex-v4-orderbook-synthesis.md
docs/markets/bonk/v1-cex-v4-orderbook-capacity.md
docs/markets/bonk/v1-cex-v4-short-horizon-orderbook.md
docs/markets/bonk/v1-cex-v3-gross-edge.md
docs/markets/bonk/v1-cex-v3-negative-controls.md
docs/markets/bonk/v1-cex-v3-threshold-drift.md
docs/markets/bonk/v1-cex-v3-modeling-synthesis.md
docs/markets/bonk/v1-cex-v4-exact-label-audit.md
docs/markets/bonk/v1-cex-v4-cross-venue-dynamics.md
docs/markets/bonk/v1-cex-v4-orderbook-family-ablation.md
```

Supporting outputs:

```text
date/bonk_v3_gross_edge_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v4_orderbook_capacity_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_*.csv
date/bonk_v3_gate_negative_controls_20260513_bullish_l2_basket_price_v1_*.csv
date/bonk_v3_gate_threshold_drift_20260513_bullish_l2_basket_price_v1_*.csv
date/bonk_v4_exact_label_audit_*.csv
```

## Existing BONK Read

The current strongest object remains the `BONK1MUSDT` H4 state:

```text
depth_high + rv_low
depth_high + rv_low + cv_spread
```

The V4 synthesis reads this as a deep/quiet orderbook regime with cross-venue state information, not as a fast standalone direction signal. Exact labels and missing-minute checks do not explain it away, but negative controls, threshold drift, sparse independent counts, and capacity/execution modeling still block promotion beyond research-candidate status.

## What A $100 Account Changes

Small capital changes the absolute notional stress:

| Constraint | Existing read | Effect of `$100` account |
| --- | --- | --- |
| Displayed-depth capacity | H4 top-of-book envelope is effectively `0`; 5-level envelope about `50` quote; 25-level wide-stress envelope about `500` quote. | `$100` is below the 25-level diagnostic envelope and around the 5-level envelope, so absolute book size is less of a blocker than it would be for larger capital. |
| Participation | V4 capacity uses quote buckets and participation screens, not a full fill model. | Smaller order size can reduce book-walk pressure, but it does not guarantee queue priority, fill quality, or stable spread capture. |
| Trade economics | Edge and costs are measured in bps. | Account size does not improve bps edge. A 2 bps fee, a 2-3 bps spread, or 10 bps adverse slippage remains the same percentage drag. |
| Research certainty | H4 gates are selected states with overlapping labels and thin effective fold counts. | Smaller notional does not create more independent observations or fix phase/time-shift failures. |

So `$100` makes the capacity question less immediately disqualifying, but it does not turn the candidate into an executable conclusion.

## Fees And Spread As Percent Of Edge

For a `$100` account, bps can look small in dollars, but the strategy feasibility is still bps-based:

```text
1 bps on $100 = $0.01
10 bps on $100 = $0.10
50 bps on $100 = $0.50
```

The V3 gross-edge probe used rough friction scenarios that subtract spread, a small `2` bps round-trip fee stress, and a stylized small-size slippage stress. Under that rough screen:

| Horizon / gate family | Existing result | Small-capital read |
| --- | --- | --- |
| H1 depth/RV gates | Often `razor_thin_after_costs` or `spread_fragile`; examples include H1 stress nets around `-4.6` to `+2.3` bps. | `$100` does not help; a few bps is only cents and is easily erased by fill quality, fee tier, or a slightly wider spread. |
| H4 depth/RV gates | H4 gates show more gross room. Examples include `depth_high+rv_low+cv_spread` with stress-net reads around `33.6` bps in V3 and H4 capacity gross medians around `32.8` to `45.6` bps in V4 capacity. | The bps room is more meaningful, but still research-only because lower-first and statistical uncertainty remain material. |
| Short 5m/15m/30m orderbook buckets | Many short-horizon candidates have median gross returns from sub-1 bps to low single digits; some 30m spread states show larger diagnostic medians, but many fail stress-net capacity. | Short horizons are especially fragile for `$100`: the absolute expected dollars per decision are tiny, and bps friction dominates. |

The critical point is that `$100` reduces dollar risk and dollar reward together. It does not improve the percentage edge or reduce the percentage cost.

## Expected Trade Count Constraints

The H4 gates have many raw selected minute rows but far fewer independent observations.

Examples from existing reports:

| Evidence item | Existing result | Feasibility implication |
| --- | --- | --- |
| H4 capacity rows | `h4_usdt_depth_rv` has `1215` rows; `h4_usdt_depth_rv_cv` has `676` rows. | These are minute-level selected rows, not independent trades. Repeated minutes inside one H4 path should not be counted as separate evidence. |
| Negative-control effective counts | Fold2/fold3 active gates show only `3-4` effective selected counts after one row per 4h stride. | This is a statistical blocker. Small capital cannot fix thin independent sample count. |
| Threshold drift | `depth_high+rv_low` validation share moved from `1.6%` to `16.3%`; `depth_high+rv_low+cv_spread` moved from `0.7%` to `10.9%`. | The same gate can select very different amounts of time across folds, so expected trade count is regime-dependent. |
| Phase validation | Phase-rotated reads are more favorable, but phase rows are still thin. | A practical research design would need deduped, pre-registered event counts, not every eligible minute as a separate trade. |

For a `$100` account, the natural tendency would be to take more small trades because each trade feels harmless. The reports argue against that interpretation. The evidence is strongest at the slow H4 state level, where overlapping-minute overcounting is a known issue. A feasibility test would need a cooldown/event-definition layer before any trade-count expectation is meaningful.

## Capacity Versus Statistical Uncertainty

Capacity and statistical uncertainty point in opposite directions:

- Capacity: `$100` is small enough that the 25-level displayed-depth envelope is less alarming, and some H4 gates are classified `capacity_research_ok`.
- Statistical uncertainty: the active H4 gates still fail or remain blocked by random-phase, time-shift, symbol/quote placebo, threshold drift, and thin effective-count diagnostics.

This means the account size does not resolve the main conclusion. The current bottleneck is not "can the account fit into the book?" as much as "is this state stable enough to deserve execution testing?"

The V4 orderbook capacity report already says the H4 envelope is not zero but remains small. A `$100` account is inside the scale where a displayed-depth feasibility check is at least plausible, but that is only a research precondition. It is not evidence that the expected value is positive.

## H4 Versus Short Horizon

The `$100` framing reinforces the existing H4-over-short-horizon preference for research:

| Horizon | Existing read | Small-capital implication |
| --- | --- | --- |
| H4 | More gross bps room, stronger regime/state interpretation, but lower-first around `25-27%` for active USDT H4 gates and median drawdown around `57-61` bps in V4 capacity. | If any path deserves future cost-aware validation, it is the H4 state. The account size helps with notional capacity but not path risk or statistical validity. |
| H1 | Mostly spread-fragile or razor-thin after costs. | `$100` does not make a few bps of fragile edge more reliable. |
| 5m/15m/30m | Useful for decay and microstructure diagnostics; many stress-net reads are too small after costs. | Short horizons are the least improved by small capital because the bps edge is often closest to the fee/spread floor and execution timing matters most. |

In plain language: small capital may make H4 capacity less impossible, but it makes short-horizon dollar expectations almost trivial while keeping all the execution uncertainty.

## Execution Risk

A `$100` notional can still face execution risk that the current reports do not model fully:

- Mid-to-mid labels are not executable fills.
- Displayed book depth is not guaranteed fillable depth.
- Top-of-book capacity is effectively zero in the V4 capacity diagnostic, so fills may require walking into deeper levels or waiting.
- Queue position, partial fills, post-only rejection, taker/maker fee tier, order throttling, and minimum order rules are not represented in the research labels.
- Lower-first rates and median adverse excursion remain material even for H4 active gates.
- Cross-venue variables look more like regime/convergence controls than clean lead-lag signals, so they should not be treated as timing instructions.

The result is that `$100` reduces absolute loss per failed execution but does not remove the structural uncertainty in fills and path risk.

## Feasibility Read

| Question | Research answer |
| --- | --- |
| Does `$100` solve capacity? | It partially relaxes absolute capacity, especially versus the 25-level diagnostic envelope. It does not solve top-of-book thinness or fill realism. |
| Does `$100` improve fees/spread as % of edge? | No. Bps costs are unchanged. Short-horizon edges remain especially fragile. |
| Does `$100` allow more trades? | It may allow more small notional attempts mechanically, but the evidence does not support counting overlapping minutes as independent trades. |
| Does `$100` reduce statistical uncertainty? | No. Negative controls, threshold drift, phase sensitivity, and thin effective H4 counts are unchanged. |
| Does `$100` favor H4 or short horizon? | It still favors H4 for future validation because H4 has more gross bps room. Short horizons remain diagnostics, not execution candidates. |
| Does `$100` justify a trading conclusion? | No. The correct status remains research-state / validation queue. |

## Plain-English Conclusion

A `$100` account changes the capacity conversation but not the research conclusion. The BONK H4 state is small enough that a tiny account may fit better into displayed depth than a larger account, but the edge is still measured in bps, the short-horizon signals are still mostly eaten by spread/fee/execution risk, and the strongest H4 candidate is still blocked by statistical uncertainty and path risk. Treat this as a feasibility note for future validation design, not as a reason to trade.

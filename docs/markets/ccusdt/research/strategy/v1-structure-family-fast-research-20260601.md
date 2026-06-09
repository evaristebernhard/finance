# CCUSDT Structure Family Fast Research v0.1

Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.

## Scope

- symbol: `CCUSDT`
- from_date: `2026-05-16`
- to_date: `2026-05-18`
- horizons_sec: `[5, 20, 60]`
- release_sec: `10`
- out_dir: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\structure_family_fast_research\ccusdt_2026-05-16_2026-05-18_decision_frame_v0_1`

This diagnostic reads `decision_frame_v1` plus canonical `quote_frame_v1`. It does not read `date/`, scored entries, future labels, PnL/MFE/MAE files, or strategy runtime state. `S5 post-release exit/wait` is marked as a required second-stage path study.

Important data caveat: this first pass uses decision-frame fields and L1/top-of-book proxies. Bot-owned closed-entry `R5` and full OFI/MLOFI sidecars are not in this path, so S1 is a stale-release proxy and S2 is a queue/microprice confirmation proxy.

## Family Summary

| family | best variant | role | status | n | mean mid60 | mean exe60 | release10 | decay60 | spread cost | median | hit | worst day | daily sign |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 | entry-alpha | entry-alpha-candidate | 66 | 6.6889 | 4.5512 | 3.7874 | -2.9015 | 2.1377 | 2.8736 | 0.5303 | 49.0930 | 1.0000 |
| S2_flow_book_confirmation | S2_tfi_microprice_confirm | entry-alpha | weak-entry-candidate | 4593 | 2.3110 | 0.0549 | 3.1230 | 0.8120 | 2.2561 | -0.6556 | 0.4581 | -699.3329 | 0.3333 |
| S3_liquidity_vacuum_release | S3_vacuum_recent_breakout | release-only | release-only | 87 | 3.6781 | 0.7952 | 2.9270 | -0.7511 | 2.8828 | -1.2958 | 0.4943 | -16.0188 | 0.6667 |
| S4_absorption_failed_continuation | S4_stale_absorption_suppressor | decay-risk | decay-risk-control | 37 | 6.1328 | 3.8962 | 3.5818 | -2.5510 | 2.2366 | -0.6438 | 0.4324 | 17.9500 | 1.0000 |
| S5_post_release_exit_wait | second_stage_not_implemented | exit-wait-candidate | second-stage-path-study-required | 0 |  |  |  |  |  |  |  |  |  |
| S6_execution_cost_admission | S6_s1_low_spread_admission | cost-filter | cost-filter-only | 425 | 2.7526 | 0.8725 | 2.8664 | 0.1138 | 1.8801 | -0.6646 | 0.4447 | 10.6298 | 1.0000 |
| S7_volatility_decay_risk | S7_trade_burst_decay_probe | decay-risk | spread-cost-mirage | 3287 | 1.2667 | -1.1662 | 3.0085 | 1.7418 | 2.4329 | -1.3025 | 0.3915 | -2572.2659 | 0.0000 |

## First-Pass Reading

- `S1 active-flow stale-release`: best variant `S1_tfi_follow_flat_stale31` is `entry-alpha-candidate`. This is still the only family in this pass with a clean entry-alpha read after top-of-book crossing, but it is the narrower stale subset rather than generic TFI.
- `S2 flow-book confirmation`: best executable mean is 0.0549bps, with status `weak-entry-candidate`. The L1 confirmation proxy improves release but does not yet solve median, worst-day, or spread-cost economics.
- `S3 liquidity vacuum`: best row is `release-only`. Thin depth appears to explain fast release, but the robust role remains release/admission research, not direct entry promotion.
- `S4 absorption`: best row is `decay-risk-control`. Treat it as a failed-continuation or suppressor family until larger samples and path-conditioned exit evidence justify otherwise.
- `S6 execution-cost admission`: best row is `cost-filter-only`. Low spread can reduce crossing damage, but it is a gate on another structure rather than a standalone alpha source.
- `S7 volatility / decay-risk`: best row is `spread-cost-mirage`. Its primary use is risk/exclusion or exit urgency, because realized movement and trade bursts are usually eaten by spread and decay.

## Variant Summary

| family | variant | role | n | mean mid60 | mean exe60 | release10 | decay60 | spread cost | median | hit | worst day | status |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| S1_active_flow_stale_release | S1_tfi_follow_flat | entry-alpha | 821 | 2.3776 | 0.1108 | 2.8921 | 0.5145 | 2.2668 | -0.6695 | 0.4385 | -136.8607 | weak-entry-candidate |
| S1_active_flow_stale_release | S1_tfi_event_stale25 | entry-alpha | 83 | 6.3710 | 4.2171 | 3.8172 | -2.5537 | 2.1539 | 2.5945 | 0.5301 | 70.4115 | entry-alpha-candidate |
| S1_active_flow_stale_release | S1_tfi_follow_flat_stale31 | entry-alpha | 66 | 6.6889 | 4.5512 | 3.7874 | -2.9015 | 2.1377 | 2.8736 | 0.5303 | 49.0930 | entry-alpha-candidate |
| S2_flow_book_confirmation | S2_tfi_queue_divergence_control | control | 5551 | 1.2993 | -1.0679 | 2.7018 | 1.4025 | 2.3673 | -1.2984 | 0.3675 | -3740.6560 | spread-cost-mirage |
| S2_flow_book_confirmation | S2_tfi_queue_confirm | entry-alpha | 4564 | 2.2985 | 0.0427 | 3.1163 | 0.8179 | 2.2558 | -0.6556 | 0.4577 | -665.5221 | weak-entry-candidate |
| S2_flow_book_confirmation | S2_tfi_microprice_confirm | entry-alpha | 4593 | 2.3110 | 0.0549 | 3.1230 | 0.8120 | 2.2561 | -0.6556 | 0.4581 | -699.3329 | weak-entry-candidate |
| S3_liquidity_vacuum_release | S3_depth_collapse_tfi | release-only | 1872 | 1.6708 | 0.0452 | 3.0736 | 1.4029 | 1.6256 | -0.6547 | 0.4263 | -377.1848 | release-only |
| S3_liquidity_vacuum_release | S3_low_depth_low_spread_tfi | entry-alpha | 1869 | 1.9536 | 0.2897 | 2.8108 | 0.8572 | 1.6639 | -0.6534 | 0.4286 | -27.5110 | weak-entry-candidate |
| S3_liquidity_vacuum_release | S3_vacuum_recent_breakout | release-only | 87 | 3.6781 | 0.7952 | 2.9270 | -0.7511 | 2.8828 | -1.2958 | 0.4943 | -16.0188 | release-only |
| S4_absorption_failed_continuation | S4_absorption_reversal_test | control | 5575 | -1.3336 | -3.7009 | 1.3038 | 2.6374 | 2.3673 | -3.2717 | 0.2814 | -8354.1808 | control-only |
| S4_absorption_failed_continuation | S4_absorption_continuation_test | decay-risk | 5575 | 1.3336 | -1.0336 | 2.7100 | 1.3764 | 2.3673 | -1.2976 | 0.3681 | -3784.7104 | spread-cost-mirage |
| S4_absorption_failed_continuation | S4_stale_absorption_suppressor | decay-risk | 37 | 6.1328 | 3.8962 | 3.5818 | -2.5510 | 2.2366 | -0.6438 | 0.4324 | 17.9500 | decay-risk-control |
| S6_execution_cost_admission | S6_low_spread_tfi_control | cost-filter | 3784 | 1.4515 | -0.4609 | 2.8250 | 1.3735 | 1.9124 | -1.2892 | 0.4072 | -1436.0769 | spread-cost-mirage |
| S6_execution_cost_admission | S6_s3_low_spread_admission | cost-filter | 1637 | 1.4543 | -0.0811 | 2.9709 | 1.5166 | 1.5354 | -0.6547 | 0.4148 | -300.2119 | spread-cost-mirage |
| S6_execution_cost_admission | S6_s1_low_spread_admission | cost-filter | 425 | 2.7526 | 0.8725 | 2.8664 | 0.1138 | 1.8801 | -0.6646 | 0.4447 | 10.6298 | cost-filter-only |
| S7_volatility_decay_risk | S7_past_event_continuation | decay-risk | 3316 | -0.1397 | -2.3920 | 2.3575 | 2.4972 | 2.2523 | -1.8975 | 0.3163 | -3683.8930 | decay-risk |
| S7_volatility_decay_risk | S7_spread_shock_breakout | decay-risk | 1284 | 1.3393 | -1.8546 | 2.6813 | 1.3420 | 3.1939 | -3.3074 | 0.3442 | -1013.7050 | spread-cost-mirage |
| S7_volatility_decay_risk | S7_trade_burst_decay_probe | decay-risk | 3287 | 1.2667 | -1.1662 | 3.0085 | 1.7418 | 2.4329 | -1.3025 | 0.3915 | -2572.2659 | spread-cost-mirage |

## Interpretation Rules

- `spread-cost-mirage`: positive mid label but non-positive top-of-book taker executable label.
- `release-only`: favorable excursion exists, but executable evidence does not justify entry promotion.
- `release-to-entry-candidate`: a release family also passes the stronger entry-alpha stability checks; none should be promoted without strict replay.
- `cost-filter`: a gate that may veto or scale entries, not create direction by itself.
- `decay-risk`: a regime useful for suppression or exit urgency, not direct entry alpha.
- `decay-risk-control`: positive executable mean exists, but the row is role-classified as risk/control because median, hit-rate, or mechanism is not entry-alpha clean.
- `control-only`: a contrast row used to understand mechanism direction, not a strategy candidate.
- Positive executable evidence still requires later strict replay, capacity, and profile-equivalence checks.

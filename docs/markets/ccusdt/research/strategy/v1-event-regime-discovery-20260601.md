# CCUSDT Event / Regime Discovery v0.1

This is a fast diagnostic for new strategy-family discovery. It does not tune the existing TFI/R5/exit policy and it does not enable maker execution.

## Scope

- Symbol: `CCUSDT`
- Dates: `2026-05-16` .. `2026-05-30`
- Horizons: `5,20,60` seconds
- Refractory: `5000000` us per family/day
- Event rows: `243668`
- Output directory: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\event_regime_discovery\ccusdt_2026-05-16_2026-05-30_v0_1`
- Elapsed wall time: `107640` ms

Labels are computed from top-of-book executable taker prices:

```text
long  executable = 10000 * log(exit_bid / entry_ask)
short executable = 10000 * log(entry_bid / exit_ask)
mid label        = same direction log return on mid
spread cost      = mid label - executable label
```

## Mechanism-Level Map

This section is the first-principles layer: it groups local triggers by the market mechanism they are trying to capture. A mechanism can be economically real on mid but still fail as a taker strategy after crossing spread.

| mechanism | h | positive rows | best family | best status | best mean exe | best median exe | hit | worst day | spread cost | max conc |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|
| absorption_or_overwhelm | 5 | 0 | absorption_continuation | rejected_spread_cost_mirage | -1.8208 | -1.9017 | 0.1374 | -4833.9304 | 2.3872 | 1.0 |
| absorption_or_overwhelm | 20 | 0 | absorption_continuation | rejected_spread_cost_mirage | -1.2704 | -1.2927 | 0.2546 | -3397.6173 | 2.3547 | 4.0 |
| absorption_or_overwhelm | 60 | 0 | absorption_continuation | rejected_spread_cost_mirage | -1.1814 | -1.2867 | 0.3407 | -3784.7104 | 2.3364 | 10.0 |
| depth_collapse_flow | 5 | 0 | depth_collapse_low_spread_continuation | rejected_spread_cost_mirage | -0.4924 | -0.6458 | 0.1602 | -341.6067 | 1.2432 | 1.0 |
| depth_collapse_flow | 20 | 2 | depth_collapse_low_spread_continuation | weak_candidate_strict_required | 0.1207 | -0.6442 | 0.2990 | -246.6715 | 1.4029 | 4.0 |
| depth_collapse_flow | 60 | 2 | depth_collapse_low_spread_continuation | weak_candidate_strict_required | 0.2809 | -0.6429 | 0.3967 | -245.4423 | 1.4783 | 8.0 |
| flow_burst | 5 | 0 | trade_burst_low_spread_continuation | rejected_spread_cost_mirage | -1.0458 | -1.2905 | 0.1783 | -989.8379 | 1.7812 | 1.0 |
| flow_burst | 20 | 0 | trade_burst_low_spread_continuation | rejected_spread_cost_mirage | -0.5840 | -1.2759 | 0.2924 | -782.9959 | 1.8503 | 4.0 |
| flow_burst | 60 | 0 | trade_burst_low_spread_continuation | rejected_spread_cost_mirage | -0.5758 | -1.2834 | 0.3646 | -970.4894 | 1.8838 | 9.0 |
| liquidity_vacuum | 5 | 0 | vacuum_breakout | rejected_spread_cost_mirage | -2.2644 | -3.1464 | 0.2300 | -132.5837 | 3.0411 | 1.0 |
| liquidity_vacuum | 20 | 0 | vacuum_breakout | rejected_spread_cost_mirage | -1.3747 | -3.0042 | 0.3357 | -98.2985 | 2.8862 | 4.0 |
| liquidity_vacuum | 60 | 1 | vacuum_breakout | weak_candidate_strict_required | 0.2619 | -0.6701 | 0.4601 | -112.1241 | 2.7180 | 8.0 |
| quote_refresh_flow | 5 | 0 | quote_refresh_burst_continuation | rejected_spread_cost_mirage | -1.6560 | -1.9165 | 0.1678 | -5449.8567 | 2.3908 | 1.0 |
| quote_refresh_flow | 20 | 0 | quote_refresh_burst_continuation | rejected_spread_cost_mirage | -1.0428 | -1.3091 | 0.2892 | -4209.0130 | 2.3640 | 4.0 |
| quote_refresh_flow | 60 | 0 | quote_refresh_burst_continuation | rejected_spread_cost_mirage | -0.8779 | -1.2923 | 0.3717 | -3974.2007 | 2.3457 | 12.0 |
| spread_shock_reversion_or_breakout | 5 | 0 | spread_shock_breakout | rejected_spread_cost_mirage | -3.0734 | -3.8531 | 0.1306 | -1767.9426 | 3.5866 | 1.0 |
| spread_shock_reversion_or_breakout | 20 | 0 | spread_shock_breakout | rejected_spread_cost_mirage | -2.4949 | -3.6983 | 0.2319 | -1416.0641 | 3.3195 | 4.0 |
| spread_shock_reversion_or_breakout | 60 | 0 | spread_shock_breakout | rejected_spread_cost_mirage | -2.0797 | -3.2368 | 0.3127 | -1372.8118 | 3.1234 | 12.0 |
| sweep_after_quiet | 5 | 0 | sweep_after_quiet_continuation | rejected_spread_cost_mirage | -1.7218 | -1.9434 | 0.1633 | -1442.9691 | 2.4392 | 1.0 |
| sweep_after_quiet | 20 | 0 | sweep_after_quiet_continuation | rejected_spread_cost_mirage | -1.1517 | -1.7979 | 0.2672 | -1260.0793 | 2.3995 | 3.0 |
| sweep_after_quiet | 60 | 0 | sweep_after_quiet_continuation | rejected_spread_cost_mirage | -0.9167 | -1.3007 | 0.3489 | -1278.5128 | 2.3693 | 4.0 |
| volatility_expansion | 5 | 0 | volatility_expansion_breakout | rejected_spread_cost_mirage | -1.8851 | -1.9065 | 0.1131 | -2673.7598 | 2.2359 | 1.0 |
| volatility_expansion | 20 | 0 | volatility_expansion_breakout | rejected_spread_cost_mirage | -1.5458 | -1.3111 | 0.2180 | -2282.3788 | 2.2169 | 4.0 |
| volatility_expansion | 60 | 0 | volatility_expansion_breakout | rejected_spread_cost_mirage | -1.5785 | -1.3135 | 0.3075 | -3628.6385 | 2.1991 | 12.0 |

## Candidate Strategy Families

| status | mechanism | family | horizon | n | mean exe | median exe | hit | worst day | spread cost | max conc | score |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| weak_candidate_strict_required | liquidity_vacuum | vacuum_breakout | 60 | 426 | 0.2619 | -0.6701 | 0.4601 | -112.1241 | 2.7180 | 8.0 | -3.5777 |
| weak_candidate_strict_required | depth_collapse_flow | depth_collapse_low_spread_continuation | 60 | 4512 | 0.2809 | -0.6429 | 0.3967 | -245.4423 | 1.4783 | 7.0 | -8.9008 |
| weak_candidate_strict_required | depth_collapse_flow | depth_collapse_flow_continuation | 60 | 4951 | 0.2319 | -0.6437 | 0.3985 | -291.3473 | 1.5423 | 8.0 | -10.9292 |

None of the selected families is a clean promotion yet. They are positive-mean executable-taker mechanisms that still need strict replay, day split, and capacity validation.

## Rejected Controls

| status | mechanism | family | horizon | n | mean mid | mean exe | hit | spread cost | reason |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| rejected_spread_cost_mirage | liquidity_vacuum | vacuum_breakout | 20 | 426 | 1.5116 | -1.3747 | 0.3357 | 2.8862 | mid label is positive but executable taker label is non-positive |
| rejected_spread_cost_mirage | liquidity_vacuum | vacuum_breakout | 5 | 426 | 0.7767 | -2.2644 | 0.2300 | 3.0411 | mid label is positive but executable taker label is non-positive |
| rejected_spread_cost_mirage | depth_collapse_flow | depth_collapse_low_spread_continuation | 5 | 4512 | 0.7508 | -0.4924 | 0.1602 | 1.2432 | mid label is positive but executable taker label is non-positive |
| rejected_spread_cost_mirage | depth_collapse_flow | depth_collapse_flow_continuation | 5 | 4951 | 0.7182 | -0.6210 | 0.1614 | 1.3392 | mid label is positive but executable taker label is non-positive |
| rejected_negative_edge | liquidity_vacuum | vacuum_reversal | 5 | 426 | -0.7767 | -3.8177 | 0.0915 | 3.0410 | both direction and executable economics are weak |
| rejected_negative_edge | liquidity_vacuum | vacuum_reversal | 20 | 426 | -1.5116 | -4.3977 | 0.1549 | 2.8862 | both direction and executable economics are weak |
| rejected_spread_cost_mirage | flow_burst | trade_burst_low_spread_continuation | 20 | 8932 | 1.2663 | -0.5840 | 0.2924 | 1.8503 | mid label is positive but executable taker label is non-positive |
| rejected_negative_edge | liquidity_vacuum | vacuum_reversal | 60 | 426 | -2.9799 | -5.6978 | 0.2347 | 2.7179 | both direction and executable economics are weak |

## Runtime-Safe Rule Drafts

### vacuum_breakout

- Rule draft: If top depth is thin and spread is wide after a recent mid move, trade with the move; this is the breakout control for vacuum reversal.
- Direction rule: `same_as_recent_mid_move`
- Condition distribution: entry_spread p25/p75=3.0442/3.7945 bps; top_depth p25/p75=65.0767/118.7477; abs_tfi p25/p75=1.0000/1.0000; queue_imbalance p25/p75=-0.6693/0.6667.
- Strict gate: `panel_sparse_fast_clock_ready_top_of_book_taker_only`
- Next strict replay: implement as a sparse admission/intent profile, then compare fast event timestamps, side, entry bid/ask, capacity, fills, and executable PnL decomposition.

### depth_collapse_low_spread_continuation

- Rule draft: If top depth collapses with signed TFI while spread is below rolling median, trade with TFI; this is the taker-viable vacuum subset.
- Direction rule: `same_as_tfi`
- Condition distribution: entry_spread p25/p75=0.6339/1.2532 bps; top_depth p25/p75=14.7221/44.6519; abs_tfi p25/p75=1.0000/1.0000; queue_imbalance p25/p75=-0.7085/0.6840.
- Strict gate: `panel_sparse_fast_clock_ready_top_of_book_taker_only`
- Next strict replay: implement as a sparse admission/intent profile, then compare fast event timestamps, side, entry bid/ask, capacity, fills, and executable PnL decomposition.

### depth_collapse_flow_continuation

- Rule draft: If top depth collapses versus rolling history and TFI is strongly signed, trade with TFI for a short taker horizon.
- Direction rule: `same_as_tfi`
- Condition distribution: entry_spread p25/p75=0.6358/1.2843 bps; top_depth p25/p75=15.1518/49.8859; abs_tfi p25/p75=1.0000/1.0000; queue_imbalance p25/p75=-0.7122/0.6857.
- Strict gate: `panel_sparse_fast_clock_ready_top_of_book_taker_only`
- Next strict replay: implement as a sparse admission/intent profile, then compare fast event timestamps, side, entry bid/ask, capacity, fills, and executable PnL decomposition.

## Full Family Summary

| status | mechanism | family | h | n | mean mid | mean exe | hit | worst day | mean spread cost | p95 conc |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| rejected_spread_cost_mirage | absorption_or_overwhelm | absorption_continuation | 5 | 25286 | 0.5664 | -1.8208 | 0.1374 | -4833.9304 | 2.3872 | 1.0 |
| rejected_spread_cost_mirage | absorption_or_overwhelm | absorption_continuation | 20 | 25286 | 1.0843 | -1.2704 | 0.2546 | -3397.6173 | 2.3547 | 3.0 |
| rejected_spread_cost_mirage | absorption_or_overwhelm | absorption_continuation | 60 | 25286 | 1.1550 | -1.1814 | 0.3407 | -3784.7104 | 2.3364 | 5.0 |
| rejected_negative_edge | absorption_or_overwhelm | absorption_reversal | 5 | 25286 | -0.5664 | -2.9537 | 0.0779 | -7124.5743 | 2.3872 | 1.0 |
| rejected_negative_edge | absorption_or_overwhelm | absorption_reversal | 20 | 25286 | -1.0843 | -3.4389 | 0.1578 | -8798.1828 | 2.3547 | 3.0 |
| rejected_negative_edge | absorption_or_overwhelm | absorption_reversal | 60 | 25286 | -1.1550 | -3.4914 | 0.2751 | -9174.2254 | 2.3364 | 5.0 |
| rejected_spread_cost_mirage | depth_collapse_flow | depth_collapse_flow_continuation | 5 | 4951 | 0.7182 | -0.6210 | 0.1614 | -410.1570 | 1.3392 | 1.0 |
| weak_candidate_strict_required | depth_collapse_flow | depth_collapse_flow_continuation | 20 | 4951 | 1.4942 | 0.0163 | 0.3016 | -353.9123 | 1.4779 | 2.0 |
| weak_candidate_strict_required | depth_collapse_flow | depth_collapse_flow_continuation | 60 | 4951 | 1.7742 | 0.2319 | 0.3985 | -291.3473 | 1.5423 | 3.0 |
| rejected_negative_edge | depth_collapse_flow | depth_collapse_flow_reversal | 5 | 4951 | -0.7182 | -2.0574 | 0.0549 | -1063.0228 | 1.3392 | 1.0 |
| rejected_negative_edge | depth_collapse_flow | depth_collapse_flow_reversal | 20 | 4951 | -1.4942 | -2.9721 | 0.1260 | -1598.2326 | 1.4779 | 2.0 |
| rejected_negative_edge | depth_collapse_flow | depth_collapse_flow_reversal | 60 | 4951 | -1.7742 | -3.3164 | 0.2428 | -2183.8405 | 1.5422 | 3.0 |
| rejected_spread_cost_mirage | depth_collapse_flow | depth_collapse_low_spread_continuation | 5 | 4512 | 0.7508 | -0.4924 | 0.1602 | -341.6067 | 1.2432 | 1.0 |
| weak_candidate_strict_required | depth_collapse_flow | depth_collapse_low_spread_continuation | 20 | 4512 | 1.5236 | 0.1207 | 0.2990 | -246.6715 | 1.4029 | 2.0 |
| weak_candidate_strict_required | depth_collapse_flow | depth_collapse_low_spread_continuation | 60 | 4512 | 1.7592 | 0.2809 | 0.3967 | -245.4423 | 1.4783 | 3.0 |
| rejected_spread_cost_mirage | quote_refresh_flow | quote_refresh_burst_continuation | 5 | 34857 | 0.7348 | -1.6560 | 0.1678 | -5449.8567 | 2.3908 | 1.0 |
| rejected_spread_cost_mirage | quote_refresh_flow | quote_refresh_burst_continuation | 20 | 34857 | 1.3212 | -1.0428 | 0.2892 | -4209.0130 | 2.3640 | 3.0 |
| rejected_spread_cost_mirage | quote_refresh_flow | quote_refresh_burst_continuation | 60 | 34857 | 1.4678 | -0.8779 | 0.3717 | -3974.2007 | 2.3457 | 6.0 |
| rejected_negative_edge | quote_refresh_flow | quote_refresh_burst_reversal | 5 | 34857 | -0.7348 | -3.1256 | 0.0570 | -9437.4858 | 2.3908 | 1.0 |
| rejected_negative_edge | quote_refresh_flow | quote_refresh_burst_reversal | 20 | 34857 | -1.3212 | -3.6853 | 0.1251 | -11610.4229 | 2.3640 | 3.0 |
| rejected_negative_edge | quote_refresh_flow | quote_refresh_burst_reversal | 60 | 34857 | -1.4678 | -3.8136 | 0.2363 | -12677.7105 | 2.3457 | 6.0 |
| rejected_spread_cost_mirage | spread_shock_reversion_or_breakout | spread_shock_breakout | 5 | 6448 | 0.5132 | -3.0734 | 0.1306 | -1767.9426 | 3.5866 | 1.0 |
| rejected_spread_cost_mirage | spread_shock_reversion_or_breakout | spread_shock_breakout | 20 | 6448 | 0.8246 | -2.4949 | 0.2319 | -1416.0641 | 3.3195 | 4.0 |
| rejected_spread_cost_mirage | spread_shock_reversion_or_breakout | spread_shock_breakout | 60 | 6448 | 1.0436 | -2.0797 | 0.3127 | -1372.8118 | 3.1234 | 5.0 |
| rejected_negative_edge | spread_shock_reversion_or_breakout | spread_shock_reversion | 5 | 6448 | -0.5132 | -4.0999 | 0.0541 | -2199.5624 | 3.5866 | 1.0 |
| rejected_negative_edge | spread_shock_reversion_or_breakout | spread_shock_reversion | 20 | 6448 | -0.8246 | -4.1441 | 0.1343 | -2255.7485 | 3.3195 | 4.0 |
| rejected_negative_edge | spread_shock_reversion_or_breakout | spread_shock_reversion | 60 | 6448 | -1.0436 | -4.1670 | 0.2387 | -2724.4044 | 3.1234 | 5.0 |
| rejected_spread_cost_mirage | sweep_after_quiet | sweep_after_quiet_continuation | 5 | 9318 | 0.7173 | -1.7218 | 0.1633 | -1442.9691 | 2.4392 | 1.0 |
| rejected_spread_cost_mirage | sweep_after_quiet | sweep_after_quiet_continuation | 20 | 9318 | 1.2477 | -1.1517 | 0.2672 | -1260.0793 | 2.3995 | 1.0 |
| rejected_spread_cost_mirage | sweep_after_quiet | sweep_after_quiet_continuation | 60 | 9318 | 1.4526 | -0.9167 | 0.3489 | -1278.5128 | 2.3693 | 2.0 |
| rejected_negative_edge | sweep_after_quiet | sweep_after_quiet_reversal | 5 | 9318 | -0.7173 | -3.1565 | 0.0584 | -2299.6871 | 2.4392 | 1.0 |
| rejected_negative_edge | sweep_after_quiet | sweep_after_quiet_reversal | 20 | 9318 | -1.2477 | -3.6472 | 0.1104 | -2722.8451 | 2.3995 | 1.0 |
| rejected_negative_edge | sweep_after_quiet | sweep_after_quiet_reversal | 60 | 9318 | -1.4526 | -3.8219 | 0.2092 | -3165.2986 | 2.3693 | 2.0 |
| rejected_spread_cost_mirage | flow_burst | trade_burst_continuation | 5 | 16519 | 0.7487 | -1.7159 | 0.1824 | -2569.2561 | 2.4646 | 1.0 |
| rejected_spread_cost_mirage | flow_burst | trade_burst_continuation | 20 | 16519 | 1.2699 | -1.1536 | 0.2905 | -2019.2078 | 2.4235 | 2.0 |
| rejected_spread_cost_mirage | flow_burst | trade_burst_continuation | 60 | 16519 | 1.2605 | -1.1340 | 0.3573 | -2572.2659 | 2.3945 | 4.0 |
| rejected_spread_cost_mirage | flow_burst | trade_burst_low_spread_continuation | 5 | 8932 | 0.7353 | -1.0458 | 0.1783 | -989.8379 | 1.7812 | 1.0 |
| rejected_spread_cost_mirage | flow_burst | trade_burst_low_spread_continuation | 20 | 8932 | 1.2663 | -0.5840 | 0.2924 | -782.9959 | 1.8503 | 2.0 |
| rejected_spread_cost_mirage | flow_burst | trade_burst_low_spread_continuation | 60 | 8932 | 1.3080 | -0.5758 | 0.3646 | -970.4894 | 1.8838 | 3.0 |
| rejected_negative_edge | flow_burst | trade_burst_reversal | 5 | 16519 | -0.7487 | -3.2133 | 0.0718 | -4253.6940 | 2.4646 | 1.0 |
| rejected_negative_edge | flow_burst | trade_burst_reversal | 20 | 16519 | -1.2699 | -3.6934 | 0.1347 | -5100.1896 | 2.4235 | 2.0 |
| rejected_negative_edge | flow_burst | trade_burst_reversal | 60 | 16519 | -1.2605 | -3.6550 | 0.2402 | -5227.0968 | 2.3945 | 4.0 |
| rejected_spread_cost_mirage | liquidity_vacuum | vacuum_breakout | 5 | 426 | 0.7767 | -2.2644 | 0.2300 | -132.5837 | 3.0411 | 1.0 |
| rejected_spread_cost_mirage | liquidity_vacuum | vacuum_breakout | 20 | 426 | 1.5116 | -1.3747 | 0.3357 | -98.2985 | 2.8862 | 3.0 |
| weak_candidate_strict_required | liquidity_vacuum | vacuum_breakout | 60 | 426 | 2.9799 | 0.2619 | 0.4601 | -112.1241 | 2.7180 | 4.0 |
| rejected_negative_edge | liquidity_vacuum | vacuum_reversal | 5 | 426 | -0.7767 | -3.8177 | 0.0915 | -224.3399 | 3.0410 | 1.0 |
| rejected_negative_edge | liquidity_vacuum | vacuum_reversal | 20 | 426 | -1.5116 | -4.3977 | 0.1549 | -270.4750 | 2.8862 | 3.0 |
| rejected_negative_edge | liquidity_vacuum | vacuum_reversal | 60 | 426 | -2.9799 | -5.6978 | 0.2347 | -431.7233 | 2.7179 | 4.0 |
| rejected_spread_cost_mirage | volatility_expansion | volatility_expansion_breakout | 5 | 17307 | 0.3508 | -1.8851 | 0.1131 | -2673.7598 | 2.2359 | 1.0 |
| rejected_spread_cost_mirage | volatility_expansion | volatility_expansion_breakout | 20 | 17307 | 0.6710 | -1.5458 | 0.2180 | -2282.3788 | 2.2169 | 4.0 |
| rejected_spread_cost_mirage | volatility_expansion | volatility_expansion_breakout | 60 | 17307 | 0.6206 | -1.5785 | 0.3075 | -3628.6385 | 2.1991 | 7.0 |
| rejected_negative_edge | volatility_expansion | volatility_expansion_reversal | 5 | 17307 | -0.3508 | -2.5867 | 0.0705 | -3300.2213 | 2.2359 | 1.0 |
| rejected_negative_edge | volatility_expansion | volatility_expansion_reversal | 20 | 17307 | -0.6710 | -2.8879 | 0.1556 | -4198.2186 | 2.2169 | 4.0 |
| rejected_negative_edge | volatility_expansion | volatility_expansion_reversal | 60 | 17307 | -0.6206 | -2.8196 | 0.2715 | -4292.4001 | 2.1991 | 7.0 |

## Interpretation

- This pass is deliberately a strategy-family discovery pass, not a promotion gate.
- Positive mid label with negative executable label means the family is likely a spread-cost mirage.
- Positive executable label is not enough for promotion; median, hit rate, worst-day, capacity overlap, and strict replay identity still matter.
- A rejected control is useful evidence: it tells us which intuitive market mechanisms do not survive top-of-book crossing.
- All event triggers here use decision-frame-visible fields. Future labels are diagnostics only and must not enter the Bot.
- Maker execution is intentionally not modeled in this pass.

## Source Manifests

```json
[
  {
    "date": "2026-05-16",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-16\\manifest.json",
      "row_count": 132382,
      "field_hash_sha256": "52f5c34d0f496782bc2fe2fe9e11a4ef53d37430b25276a6a619bd59bed36269",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-16\\part_000001.csv.gz",
    "events_extracted": 16462
  },
  {
    "date": "2026-05-17",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-17\\manifest.json",
      "row_count": 114918,
      "field_hash_sha256": "a02b53a3568e0ce6c3a5901da08d6c0e10fb829f6c9c1ccc5c49a6c3cad678e5",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-17\\part_000001.csv.gz",
    "events_extracted": 16222
  },
  {
    "date": "2026-05-18",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-18\\manifest.json",
      "row_count": 131608,
      "field_hash_sha256": "a74eb8f509317b231d3712523ed1f133d242984379891c36b89f01a4aee94733",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-18\\part_000001.csv.gz",
    "events_extracted": 17217
  },
  {
    "date": "2026-05-19",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-19\\manifest.json",
      "row_count": 128944,
      "field_hash_sha256": "6c73fe562265f4e1f192509faf435627075a9112cd29eba9aa5b80d1a115620d",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-19\\part_000001.csv.gz",
    "events_extracted": 16096
  },
  {
    "date": "2026-05-20",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-20\\manifest.json",
      "row_count": 137029,
      "field_hash_sha256": "4c25807042c26420ab7addac166efd528318ebe4b279f9241eca2b56f1b52312",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-20\\part_000001.csv.gz",
    "events_extracted": 14184
  },
  {
    "date": "2026-05-21",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-21\\manifest.json",
      "row_count": 141844,
      "field_hash_sha256": "9fb79e909c973c81f470b04d1d12739fae07b267c31b852fa6275e416d202796",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-21\\part_000001.csv.gz",
    "events_extracted": 17366
  },
  {
    "date": "2026-05-22",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-22\\manifest.json",
      "row_count": 143035,
      "field_hash_sha256": "146de8396556e6f1305b45ea4de7b90a5fbdda57a8f11911162a1067ae9d372c",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-22\\part_000001.csv.gz",
    "events_extracted": 15819
  },
  {
    "date": "2026-05-23",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-23\\manifest.json",
      "row_count": 138004,
      "field_hash_sha256": "7ec9566ce51904c62b6405dbfa662cd6f945645acc2bc1863416111b88337a10",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-23\\part_000001.csv.gz",
    "events_extracted": 17983
  },
  {
    "date": "2026-05-24",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-24\\manifest.json",
      "row_count": 137325,
      "field_hash_sha256": "4ef51b22b1a0dad2b43ded6ab5c4c6ad234ae51bc0c04d752a10eac8b5257004",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-24\\part_000001.csv.gz",
    "events_extracted": 19841
  },
  {
    "date": "2026-05-25",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-25\\manifest.json",
      "row_count": 118808,
      "field_hash_sha256": "cb05d6f835eb22fcfa05be4d1299dd213087de4a5e5bd28a8f8a160d31d86ebf",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-25\\part_000001.csv.gz",
    "events_extracted": 17297
  },
  {
    "date": "2026-05-26",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-26\\manifest.json",
      "row_count": 130374,
      "field_hash_sha256": "2f3312e066039b54a8221a21f3aacbfdb9ddfd4216c1d2ca7b6a22e4225ebb89",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-26\\part_000001.csv.gz",
    "events_extracted": 16902
  },
  {
    "date": "2026-05-27",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-27\\manifest.json",
      "row_count": 129268,
      "field_hash_sha256": "cc77f4eb908185aa802655f5daa395ade9e6112df181468b919b2cf87dcf5030",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-27\\part_000001.csv.gz",
    "events_extracted": 13817
  },
  {
    "date": "2026-05-28",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-28\\manifest.json",
      "row_count": 130934,
      "field_hash_sha256": "d2400e67dd67cc6bc58407cab170f1f068e9367460dee6423e6ae280fb439ee3",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-28\\part_000001.csv.gz",
    "events_extracted": 13839
  },
  {
    "date": "2026-05-29",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-29\\manifest.json",
      "row_count": 130343,
      "field_hash_sha256": "062e671ca0d57a0be66cc4b38d2698101cb8f9b6474dbed326a58b94840ae63a",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-29\\part_000001.csv.gz",
    "events_extracted": 16210
  },
  {
    "date": "2026-05-30",
    "decision_frame_manifest": {
      "path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical_parquet\\cex\\bullish\\CCUSDT\\decision_frame_v1\\dt=2026-05-30\\manifest.json",
      "row_count": 114770,
      "field_hash_sha256": "9435b04117c4af6fc4900a3f3b87282926325da06faf1ba9f4b41cdcbd326d8e",
      "builder_version": "decision_frame_builder_v1.1_market_derived_cache",
      "schema_version": "decision_frame_v1.parquet.schema_v1"
    },
    "quote_frame_path": "C:\\Users\\jiang\\Desktop\\finance_chain_full_handoff_20260508_r2\\data\\canonical\\cex\\bullish\\CCUSDT\\quote_frame_v1\\dt=2026-05-30\\part_000001.csv.gz",
    "events_extracted": 14413
  }
]
```

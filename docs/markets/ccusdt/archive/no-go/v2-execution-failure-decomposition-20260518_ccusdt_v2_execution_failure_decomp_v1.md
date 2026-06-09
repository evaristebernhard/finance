# CCUSDT V2 Execution Failure Decomposition

Status: `20260518_ccusdt_v2_execution_failure_decomp_v1`.

Guardrail: `research_only_execution_failure_decomposition_no_execution_recommendation_no_alpha_claim`.

Core maker identity:

```text
per_signal_net_bps = fill_rate * E[net_bps | filled]
```

Target per-signal capture: `2.0` bps.

## Maker Practical Gap

| fold | trigger_class | entry_quality_bin | signals | fill_rate | filled_net_mean_bps | per_signal_net_mean_bps | maker_gap_to_target_bps | required_filled_net_at_current_fill_rate_bps | required_fill_rate_at_current_filled_net | maker_failure_mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.0435 | -0.0877 | -0.0038 | 2.0038 | 46.0000 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_long_flat | low | 142 | 0.0070 | -2.0000 | -0.0141 | 2.0141 | 284.0000 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_short_flat | mid | 206 | 0.0388 | -0.9986 | -0.0388 | 2.0388 | 51.5000 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_follow_flat | mid | 291 | 0.0206 | -2.0947 | -0.0432 | 2.0432 | 97.0000 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_follow_flat | low | 186 | 0.0215 | -2.1763 | -0.0468 | 2.0468 | 93.0000 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_long_flat | low | 140 | 0.0143 | -3.3448 | -0.0478 | 2.0478 | 140.0000 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_short_flat | mid | 132 | 0.0152 | -5.3782 | -0.0815 | 2.0815 | 132.0000 |  | filled_net_nonpositive |
| expanding_fold3 | tfi_follow_flat | high | 508 | 0.0413 | -2.1469 | -0.0887 | 2.0887 | 48.3810 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_event_active | low | 21 | 0.0952 | -1.0078 | -0.0960 | 2.0960 | 21.0000 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_long_flat | high | 137 | 0.0292 | -3.3493 | -0.0978 | 2.0978 | 68.5000 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_short_stale25 | low | 17 | 0.1176 | -1.0078 | -0.1186 | 2.1186 | 17.0000 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_event_active | high | 56 | 0.0536 | -2.2653 | -0.1214 | 2.1214 | 37.3333 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_follow_flat | high | 317 | 0.0410 | -3.4957 | -0.1434 | 2.1434 | 48.7692 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_long_flat | mid | 102 | 0.0392 | -3.7047 | -0.1453 | 2.1453 | 51.0000 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_follow_flat | low | 298 | 0.0336 | -5.5247 | -0.1854 | 2.1854 | 59.6000 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_long_flat | high | 129 | 0.0388 | -5.4936 | -0.2129 | 2.2129 | 51.6000 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_short_flat | high | 188 | 0.0585 | -3.8339 | -0.2243 | 2.2243 | 34.1818 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_follow_flat | mid | 250 | 0.0400 | -8.2162 | -0.3286 | 2.3286 | 50.0000 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_long_flat | mid | 134 | 0.0448 | -7.9794 | -0.3573 | 2.3573 | 44.6667 |  | filled_net_nonpositive |
| expanding_fold1 | tfi_short_flat | low | 88 | 0.0795 | -4.9726 | -0.3956 | 2.3956 | 25.1429 |  | filled_net_nonpositive |
| expanding_fold2 | tfi_short_stale25 | high | 31 | 0.0323 | -13.6558 | -0.4405 | 2.4405 | 62.0000 |  | filled_net_nonpositive |
| expanding_fold3 | tfi_short_flat | low | 129 | 0.0310 | -14.4997 | -0.4496 | 2.4496 | 64.5000 |  | filled_net_nonpositive |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.0308 | -15.6430 | -0.4813 | 2.4813 | 65.0000 |  | filled_net_nonpositive |
| expanding_fold3 | tfi_follow_flat | mid | 286 | 0.0490 | -10.0897 | -0.4939 | 2.4939 | 40.8571 |  | filled_net_nonpositive |
| expanding_fold3 | tfi_long_flat | mid | 99 | 0.0707 | -7.5617 | -0.5347 | 2.5347 | 28.2857 |  | filled_net_nonpositive |

## Taker Fallback Context

| fold | trigger_class | entry_quality_bin | taker_net_mean_bps | taker_net_plus2_mean_bps | taker_net_median_bps | top10_taker_share_of_total_net | taker_promote_gate | fail_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_event_active | mid | 4.7331 | 2.7331 | -0.8124 | 1.5591 | False | sample,controls,tail,risk |
| expanding_fold3 | tfi_short_stale25 | high | 3.4582 | 1.4582 | -2.6410 | 1.9111 | False | sample,controls,tail,risk |
| expanding_fold3 | tfi_short_stale25 | mid | 2.9771 | 0.9771 | 1.1782 | 1.9619 | False | sample,controls,tail,risk |
| expanding_fold3 | tfi_short_stale25 | low | 2.9104 | 0.9104 | 2.3919 | 1.1728 | False | sample,tail,risk |
| expanding_fold2 | tfi_short_flat | mid | 1.9542 | -0.0458 | -0.4447 | 1.5256 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_follow_flat | high | 1.0685 | -0.9315 | -2.6043 | 3.7051 | False | economics,plus2_stress,tail,risk |
| expanding_fold3 | tfi_event_active | high | 1.0613 | -0.9387 | 0.5746 | 3.4818 | False | sample,economics,plus2_stress,controls,tail |
| expanding_fold2 | tfi_event_active | mid | 0.9593 | -1.0407 | -0.9405 | 2.7153 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_short_flat | low | 0.9160 | -1.0840 | 0.3753 | 4.1917 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_short_flat | high | 0.8717 | -1.1283 | -2.6078 | 4.4091 | False | sample,economics,plus2_stress,tail |
| expanding_fold3 | tfi_long_flat | high | 0.7313 | -1.2687 | -2.6308 | 5.6745 | False | sample,economics,plus2_stress,tail,risk |
| expanding_fold1 | tfi_short_stale25 | mid | 0.7034 | -1.2966 | 1.3524 | 1.1750 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold2 | tfi_short_stale25 | low | 0.5337 | -1.4663 | -2.0000 | 3.3834 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_event_active | low | 0.3144 | -1.6856 | -1.9998 | 9.8121 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_long_flat | mid | 0.1105 | -1.8895 | -3.2193 | 37.1681 | False | sample,economics,plus2_stress,residual,tail,risk |
| expanding_fold2 | tfi_follow_flat | low | 0.0628 | -1.9372 | -2.6371 | 41.3565 | False | sample,economics,plus2_stress,controls,tail,risk |
| expanding_fold3 | tfi_follow_flat | mid | 0.0606 | -1.9394 | -2.6334 | 53.9153 | False | sample,economics,plus2_stress,residual,tail,risk |
| expanding_fold3 | tfi_long_flat | low | -0.1202 | -2.1202 | -0.7000 |  | False | sample,economics,plus2_stress,residual,tail,risk |
| expanding_fold3 | tfi_follow_flat | low | -0.1314 | -2.1314 | -2.6242 |  | False | sample,economics,plus2_stress,residual,tail,risk |
| expanding_fold1 | tfi_event_active | low | -0.3026 | -2.3026 | 0.7015 |  | False | sample,economics,plus2_stress,controls,residual,tail,risk |

## Decision

Best practical maker per-signal net is `-0.0038` bps, below the `2.0000` bps target. Taker promote gate present: `False`. Current candidates remain execution-no-go.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_execution_failure_decomposition.py --run-tag 20260518_ccusdt_v2_execution_failure_decomp_v1 --target-bps 2
```

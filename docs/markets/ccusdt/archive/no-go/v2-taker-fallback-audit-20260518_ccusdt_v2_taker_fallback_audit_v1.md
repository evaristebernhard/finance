# CCUSDT V2 Taker Fallback Audit

Status: `20260518_ccusdt_v2_taker_fallback_audit_v1` from framework run `20260518_ccusdt_v2_framework_v1`.

Guardrail: `research_only_taker_fallback_no_execution_recommendation_no_alpha_claim`.

This pass asks whether immediate crossing can rescue the signal after maker queue-fill no-go. It uses the framework's `fixed_net_taker_bps` labels and inherits framework controls/risk gates.

## Taker Scorecard

| fold | trigger_class | entry_quality_bin | entries | taker_net_mean_bps | taker_net_plus2_mean_bps | taker_net_median_bps | taker_gt_2bps_rate | top10_taker_share_of_total_net | sample_pass | economics_pass | stress_pass | controls_pass | tail_pass | risk_pass | fail_reasons | taker_fallback_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_event_active | mid | 72 | 4.7331 | 2.7331 | -0.8124 | 0.3889 | 1.5591 | False | True | True | False | False | False | sample,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_short_stale25 | high | 54 | 3.4582 | 1.4582 | -2.6410 | 0.3519 | 1.9111 | False | True | True | False | False | False | sample,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_short_stale25 | mid | 39 | 2.9771 | 0.9771 | 1.1782 | 0.4103 | 1.9619 | False | True | True | False | False | False | sample,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_short_stale25 | low | 38 | 2.9104 | 0.9104 | 2.3919 | 0.5000 | 1.1728 | False | True | True | True | False | False | sample,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_short_flat | mid | 206 | 1.9542 | -0.0458 | -0.4447 | 0.3592 | 1.5256 | False | False | False | False | False | False | sample,economics,plus2_stress,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_follow_flat | high | 508 | 1.0685 | -0.9315 | -2.6043 | 0.3563 | 3.7051 | True | False | False | True | False | False | economics,plus2_stress,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_event_active | high | 85 | 1.0613 | -0.9387 | 0.5746 | 0.4000 | 3.4818 | False | False | False | False | False | True | sample,economics,plus2_stress,controls,tail | taker_fallback_no_go |
| expanding_fold2 | tfi_event_active | mid | 28 | 0.9593 | -1.0407 | -0.9405 | 0.3214 | 2.7153 | False | False | False | False | False | False | sample,economics,plus2_stress,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_short_flat | low | 129 | 0.9160 | -1.0840 | 0.3753 | 0.3566 | 4.1917 | False | False | False | False | False | False | sample,economics,plus2_stress,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_short_flat | high | 391 | 0.8717 | -1.1283 | -2.6078 | 0.3657 | 4.4091 | False | False | False | True | False | True | sample,economics,plus2_stress,tail | taker_fallback_no_go |
| expanding_fold3 | tfi_long_flat | high | 195 | 0.7313 | -1.2687 | -2.6308 | 0.3333 | 5.6745 | False | False | False | True | False | False | sample,economics,plus2_stress,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_short_stale25 | mid | 5 | 0.7034 | -1.2966 | 1.3524 | 0.4000 | 1.1750 | False | False | False | False | False | False | sample,economics,plus2_stress,controls,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_short_stale25 | low | 31 | 0.5337 | -1.4663 | -2.0000 | 0.3226 | 3.3834 | False | False | False | False | False | False | sample,economics,plus2_stress,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_event_active | low | 53 | 0.3144 | -1.6856 | -1.9998 | 0.4340 | 9.8121 | False | False | False | False | False | False | sample,economics,plus2_stress,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_long_flat | mid | 99 | 0.1105 | -1.8895 | -3.2193 | 0.3030 | 37.1681 | False | False | False | True | False | False | sample,economics,plus2_stress,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_follow_flat | low | 298 | 0.0628 | -1.9372 | -2.6371 | 0.3054 | 41.3565 | False | False | False | False | False | False | sample,economics,plus2_stress,controls,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_follow_flat | mid | 286 | 0.0606 | -1.9394 | -2.6334 | 0.3217 | 53.9153 | False | False | False | True | False | False | sample,economics,plus2_stress,residual,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_long_flat | low | 199 | -0.1202 | -2.1202 | -0.7000 | 0.3869 |  | False | False | False | True | False | False | sample,economics,plus2_stress,residual,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_follow_flat | low | 335 | -0.1314 | -2.1314 | -2.6242 | 0.3582 |  | False | False | False | True | False | False | sample,economics,plus2_stress,residual,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_event_active | low | 21 | -0.3026 | -2.3026 | 0.7015 | 0.3333 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_event_active | low | 37 | -0.3362 | -2.3362 | -2.6369 | 0.3243 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_follow_flat | mid | 291 | -0.3989 | -2.3989 | -2.6856 | 0.2887 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_long_flat | mid | 102 | -0.4592 | -2.4592 | -3.2801 | 0.2451 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_long_flat | high | 137 | -0.5692 | -2.5692 | -2.6410 | 0.2555 |  | False | False | False | True | False | False | sample,economics,plus2_stress,residual,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_event_active | high | 31 | -0.8853 | -2.8853 | -2.6711 | 0.3226 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_event_active | high | 56 | -0.8914 | -2.8914 | -1.6685 | 0.3393 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_short_stale25 | low | 17 | -0.9247 | -2.9247 | 0.7015 | 0.3529 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold3 | tfi_short_flat | mid | 196 | -0.9604 | -2.9604 | -2.6512 | 0.2806 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_follow_flat | high | 337 | -1.2321 | -3.2321 | -2.6464 | 0.2997 |  | False | False | False | False | False | True | sample,economics,plus2_stress,controls,residual,tail | taker_fallback_no_go |
| expanding_fold2 | tfi_short_flat | low | 190 | -1.4248 | -3.4248 | -2.6369 | 0.3421 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold2 | tfi_long_flat | low | 142 | -1.4585 | -3.4585 | -2.6403 | 0.2606 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_event_active | mid | 9 | -1.9364 | -3.9364 | -3.3435 | 0.3333 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_follow_flat | low | 186 | -2.1140 | -4.1140 | -3.3469 | 0.2043 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_short_stale25 | high | 5 | -2.4197 | -4.4197 | -2.6711 | 0.2000 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |
| expanding_fold1 | tfi_short_flat | low | 88 | -2.6080 | -4.6080 | -2.6735 | 0.2045 |  | False | False | False | False | False | False | sample,economics,plus2_stress,controls,residual,tail,risk | taker_fallback_no_go |

## Decision

No taker fallback row passes the combined sample, economics, stress, control, tail, and risk gates. Crossing the spread does not rescue the current CCUSDT candidates.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_taker_fallback_summary_20260518_ccusdt_v2_taker_fallback_audit_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_taker_fallback_summary_20260518_ccusdt_v2_taker_fallback_audit_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_taker_fallback_audit.py --run-tag 20260518_ccusdt_v2_taker_fallback_audit_v1
```

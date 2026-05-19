# CCUSDT V1 TFI Post-Exit Re-Trigger Diagnostic

Status: `20260519_ccusdt_v1_tfi_post_exit_retrigger_v1`.

Guardrail: `research_only_post_exit_retrigger_diagnostic_no_execution_recommendation`.

## Question

This pass does not ask whether the first drawdown exit was wrong.
It asks whether, after that exit, a fresh second trigger is observable.

Use post-exit coordinates:

$$
\widetilde R_i(u)=10^4s_i\log\frac{M_{\tau_i+u}}{M_{\tau_i}},
$$

where \(\tau_i\) is the drawdown exit time.

At observation horizon \(g\), define:

$$
Q_i(g)=\frac{1}{g}\int_0^g s_iQI_5(\tau_i+u)\,du,
$$

$$
F_i(g)=\sum_{0<u\le g}s_iTFI(\tau_i+u),
$$

$$
C_i(g)=\widetilde R_i(g)-\min_{0\le u\le g}\widetilde R_i(u).
$$

The strict diagnostic trigger is:

$$
Q_i(5)\ge 0.7,\quad F_i(5)>0,\quad C_i(5)\ge 1.
$$

Here the trade impulse window is strictly post-exit: \(0<u\le g\).

Future return is only a label:

$$
\max_{u\ge g}\left(\widetilde R_i(u)-\widetilde R_i(g)\right)\ge 10,
$$

$$
\widetilde R_i(T)-\widetilde R_i(g)\ge 0.
$$

## Horizon Scorecard

| obs_horizon_sec | entries | predicted_retriggers | productive_labels | true_positive | false_positive | false_negative | precision | recall | reentry_final_pnl | reentry_mfe | mean_future_mfe_pred | mean_future_final_pred |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 41 | 0 | 7 | 0 | 0 | 7 |  | 0.0000 | 0.0000 | 0.0000 |  |  |
| 5 | 41 | 1 | 6 | 1 | 0 | 5 | 1.0000 | 0.1667 | 200.3343 | 383.0968 | 95.7742 | 50.0836 |
| 10 | 41 | 0 | 5 | 0 | 0 | 5 |  | 0.0000 | 0.0000 | 0.0000 |  |  |
| 15 | 41 | 0 | 4 | 0 | 0 | 4 |  | 0.0000 | 0.0000 | 0.0000 |  |  |

## Case Summary At 5s

| path_case_class | entries | predicted_retriggers | productive_labels | post_total_mfe_mean | post_final_mean | exit_signed_qi5_mean | obs_qi_mean | obs_tfi_sum_mean | obs_reclaim_mean | reentry_final_pnl |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 00_non_case | 21 | 0 | 4 | 6.0152 | 4.2702 | 0.4130 | 0.3656 | -7.6935 | 0.6694 | 0.0000 |
| 02_fast_release_reversal | 5 | 0 | 0 | 2.6347 | -13.8433 | 0.8658 | 0.5105 | -7.3937 | 2.5719 | 0.0000 |
| 03_large_release_plateau_decay | 5 | 0 | 0 | 0.0000 | -7.6133 | 0.7780 | 0.8397 | -10.6000 | 0.0624 | 0.0000 |
| 04_late_release_collapse | 10 | 1 | 2 | 15.0824 | -4.6611 | 0.8493 | 0.7174 | -9.9956 | 3.3056 | 200.3343 |

## Examples

| example_group | date | entry_row | path_case_class | direction_label | target_exposure | R_exit | baseline_R60 | post_total_mfe | post_final | obs_signed_qi5_mean_5s | obs_signed_tfi_sum_5s | obs_reclaim_5s | future_mfe_after_5s | future_final_after_5s | rule_retrigger_after_5s | label_productive_after_5s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| predicted_retrigger | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | 20.2961 | 69.7360 | 95.1305 | 49.4399 | 0.8876 | 11.0000 | 1.6094 | 95.7742 | 50.0836 | True | True |
| selected_cases | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | 20.2961 | 69.7360 | 95.1305 | 49.4399 | 0.8876 | 11.0000 | 1.6094 | 95.7742 | 50.0836 | True | True |
| selected_cases | 2026-05-09 | 1615412 | 02_fast_release_reversal | short | 8.0000 | -10.0376 | -27.8923 | 12.8625 | -17.8546 | -0.7975 | -0.9687 | 12.5486 | 0.0000 | -30.4033 | False | False |
| selected_cases | 2026-05-12 | 2039581 | 02_fast_release_reversal | short | 8.0000 | -0.0000 | -17.3956 | 0.3109 | -17.3956 | 0.9480 | -10.0000 | 0.3109 | 0.0000 | -17.7065 | False | False |
| selected_cases | 2026-05-14 | 2334597 | 04_late_release_collapse | long | 2.0000 | 7.5133 | -59.7053 | 0.0000 | -67.2185 | 0.6453 | -21.0000 | 0.0000 | 0.0000 | -49.4782 | False | False |
| selected_cases | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | short | 10.0000 | 14.0108 | -9.5281 | -0.0000 | -23.5389 | 0.6739 | -28.0000 | 0.0000 | 6.2479 | 6.2479 | False | False |
| selected_cases | 2026-05-14 | 2377379 | 02_fast_release_reversal | short | 10.0000 | -0.2953 | -23.5967 | -0.0000 | -23.3014 | 0.9534 | -14.0000 | 0.0000 | 0.0000 | -13.2663 | False | False |
| top_post_exit_mfe | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | 20.2961 | 69.7360 | 95.1305 | 49.4399 | 0.8876 | 11.0000 | 1.6094 | 95.7742 | 50.0836 | True | True |
| top_post_exit_mfe | 2026-05-14 | 2322885 | 00_non_case | long | 2.0000 | -7.7895 | 38.2362 | 46.0257 | 46.0257 | 0.8185 | -2.2607 | 0.3117 | 45.7140 | 45.7140 | False | True |
| top_post_exit_mfe | 2026-05-14 | 2362632 | 04_late_release_collapse | long | 2.0000 | -36.4493 | 4.7316 | 41.4766 | 41.1810 | -0.6123 | -16.3351 | 30.8276 | 10.6490 | 10.3533 | False | True |
| top_post_exit_mfe | 2026-05-09 | 1615412 | 02_fast_release_reversal | short | 8.0000 | -10.0376 | -27.8923 | 12.8625 | -17.8546 | -0.7975 | -0.9687 | 12.5486 | 0.0000 | -30.4033 | False | False |
| top_post_exit_mfe | 2026-05-15 | 2540829 | 04_late_release_collapse | long | 2.0000 | -4.7623 | -42.9424 | 12.6944 | -38.1801 | 0.9363 | -19.0000 | 0.3176 | 13.6471 | -37.2274 | False | False |
| top_post_exit_mfe | 2026-05-14 | 2327008 | 00_non_case | short | 10.0000 | 0.3037 | 12.4584 | 12.1547 | 12.1547 | 0.4672 | 2.0000 | 10.6301 | 5.7753 | 5.7753 | False | False |
| top_post_exit_mfe | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | -4.7488 | 5.0480 | 9.7968 | 9.7968 | 0.9380 | -26.0000 | 0.2962 | 28.4731 | 28.4731 | False | True |
| top_post_exit_mfe | 2026-05-10 | 1678625 | 00_non_case | long | 2.0000 | 7.0357 | 14.0665 | 7.0308 | 7.0308 | 0.0076 | 0.3357 | 0.0000 | 7.0308 | 7.0308 | False | False |
| top_post_exit_mfe | 2026-05-14 | 2383289 | 00_non_case | long | 2.0000 | 11.7260 | 18.0343 | 6.6086 | 6.3083 | 0.9242 | -17.0000 | 0.0000 | 16.5297 | 16.2294 | False | True |
| top_post_exit_mfe | 2026-05-09 | 1611937 | 00_non_case | long | 2.0000 | -0.6262 | 5.9467 | 6.5729 | 6.5729 | 0.9280 | -7.0000 | 0.3131 | 6.2598 | 6.2598 | False | False |
| top_post_exit_mfe | 2026-05-12 | 2070772 | 00_non_case | long | 2.0000 | 0.6577 | 0.0000 | 6.2464 | -0.6577 | 0.3770 | 4.0000 | 0.3289 | 0.0000 | 0.0000 | False | False |
| top_post_exit_mfe | 2026-05-14 | 2340079 | 00_non_case | short | 8.0000 | 5.1776 | 10.9676 | 5.7899 | 5.7899 | 0.6859 | -37.0000 | 0.0000 | 36.5119 | 36.5119 | False | True |

## Read

- `2583437` is a clean strict re-trigger: queue remains favorable, fresh
  same-side trade returns, and price reclaims from the reset low.
- `2377379` has favorable queue after exit, but same-side trade impulse is
  negative; it should not be re-entered by this diagnostic.
- `1615412` shows that post-exit MFE alone is not enough. It briefly bounces,
  but the 5s diagnostic rejects it because queue/flow are not supportive.
- The 5s rule is high precision and low recall on this small set. Treat it
  as a diagnostic witness, not a full re-entry strategy.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_retrigger_events_20260519_ccusdt_v1_tfi_post_exit_retrigger_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_retrigger_horizon_summary_20260519_ccusdt_v1_tfi_post_exit_retrigger_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_retrigger_case_summary_20260519_ccusdt_v1_tfi_post_exit_retrigger_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_retrigger_examples_20260519_ccusdt_v1_tfi_post_exit_retrigger_v1.csv`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_post_exit_retrigger_diagnostic.py
```

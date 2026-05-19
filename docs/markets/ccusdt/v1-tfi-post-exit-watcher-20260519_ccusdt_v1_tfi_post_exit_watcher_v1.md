# CCUSDT V1 TFI Post-Exit Watcher

Status: `20260519_ccusdt_v1_tfi_post_exit_watcher_v1`.

Guardrail: `research_only_post_exit_watcher_no_execution_recommendation`.

## Question

The watcher starts after a drawdown exit from the small path manager.
It does not ask whether the first exit was wrong. It asks whether the
post-exit path prints a new entry event.

Use post-exit coordinates:

$$
\widetilde R_i(u)=10^4s_i\log\frac{M_{\tau_i+u}}{M_{\tau_i}}.
$$

At \(g=5s\):

$$
Q_i(g)=\frac{1}{g}\int_0^g s_iQI_5(\tau_i+u)\,du,\qquad
F_i(g)=\sum_{0<u\le g}s_iTFI(\tau_i+u).
$$

The impulse branch is:

$$
Q_i(5)\ge 0.7,\quad F_i(5)>0,\quad C_i(5)\ge 1.
$$

The absorption branch is:

$$
Q_i(5)\ge q_a,\quad F_i(5)<0,
$$

then wait for a confirmed reclaim from the reset low:

$$
\tau_a=\inf\{u>5:\widetilde R_i(u)-L_i(5)\ge r_a,\ \widetilde R_i(u)\le 5,
\min_{5<v\le u}\widetilde R_i(v)\ge L_i(5)-5,\ T_i-u\ge5\}.
$$

where \(L_i(5)=\min_{0\le v\le5}\widetilde R_i(v)\).
The cap \(\widetilde R_i(u)\le5\) prevents chasing late spikes like `2540829`; the
remaining-time guard prevents opening only at the last print of the path.

## Watcher Parameters

| watcher_policy | absorb_enabled | absorb_qi_threshold | absorb_reclaim_bps | absorb_cancel_extension_bps | absorb_chase_cap_bps | min_remaining_sec |
| --- | --- | --- | --- | --- | --- | --- |
| impulse_only | False |  |  |  |  |  |
| watcher_q70_absorb_reclaim2 | True | 0.7000 | 2.0000 | 5.0000 | 5.0000 | 5.0000 |
| watcher_q65_absorb_reclaim2 | True | 0.6500 | 2.0000 | 5.0000 | 5.0000 | 5.0000 |
| watcher_q65_absorb_reclaim3 | True | 0.6500 | 3.0000 | 5.0000 | 5.0000 | 5.0000 |

## Policy Summary

| watcher_policy | drawdown_exits | triggers | impulse_triggers | absorb_triggers | watch_weighted_final | watch_weighted_mfe | watch_worst_weighted_final | watch_negative_triggers | manager_total | manager_plus_watcher_total | fixed60_total | vs_manager_delta | vs_fixed60_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| impulse_only | 41 | 1 | 1 | 0 | 220.9383 | 403.7008 | 220.9383 | 0 | 9554.1874 | 9775.1257 | 8904.7590 | 220.9383 | 870.3667 |
| watcher_q70_absorb_reclaim2 | 41 | 3 | 1 | 2 | 522.1939 | 704.9564 | 87.6881 | 0 | 9554.1874 | 10076.3813 | 8904.7590 | 522.1939 | 1171.6223 |
| watcher_q65_absorb_reclaim2 | 41 | 5 | 1 | 4 | 803.2748 | 986.0373 | 32.7318 | 0 | 9554.1874 | 10357.4622 | 8904.7590 | 803.2748 | 1452.7032 |
| watcher_q65_absorb_reclaim3 | 41 | 4 | 1 | 3 | 680.5888 | 863.3513 | 23.8060 | 0 | 9554.1874 | 10234.7762 | 8904.7590 | 680.5888 | 1330.0172 |

## Case Summary

| watcher_policy | path_case_class | watch_mode | triggered | weighted_final | weighted_mfe | worst_weighted_final | obs_qi_mean | obs_tfi_sum_mean | obs_R_min_mean | obs_R_end_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| impulse_only | 04_late_release_collapse | impulse_5s | 1 | 220.9383 | 403.7008 | 220.9383 | 0.8876 | 11.0000 | -2.2531 | -0.6437 |
| watcher_q65_absorb_reclaim2 | 00_non_case | absorb_reclaim | 3 | 549.6048 | 549.6048 | 87.6881 | 0.8142 | -21.7536 | -16.5648 | -16.3622 |
| watcher_q65_absorb_reclaim2 | 03_large_release_plateau_decay | absorb_reclaim | 1 | 32.7318 | 32.7318 | 32.7318 | 0.6739 | -28.0000 | -29.7867 | -29.7867 |
| watcher_q65_absorb_reclaim2 | 04_late_release_collapse | impulse_5s | 1 | 220.9383 | 403.7008 | 220.9383 | 0.8876 | 11.0000 | -2.2531 | -0.6437 |
| watcher_q65_absorb_reclaim3 | 00_non_case | absorb_reclaim | 2 | 435.8446 | 435.8446 | 187.4955 | 0.8120 | -31.5000 | -24.8473 | -24.6992 |
| watcher_q65_absorb_reclaim3 | 03_large_release_plateau_decay | absorb_reclaim | 1 | 23.8060 | 23.8060 | 23.8060 | 0.6739 | -28.0000 | -29.7867 | -29.7867 |
| watcher_q65_absorb_reclaim3 | 04_late_release_collapse | impulse_5s | 1 | 220.9383 | 403.7008 | 220.9383 | 0.8876 | 11.0000 | -2.2531 | -0.6437 |
| watcher_q70_absorb_reclaim2 | 00_non_case | absorb_reclaim | 2 | 301.2557 | 301.2557 | 87.6881 | 0.8783 | -14.1303 | -9.4863 | -9.1823 |
| watcher_q70_absorb_reclaim2 | 04_late_release_collapse | impulse_5s | 1 | 220.9383 | 403.7008 | 220.9383 | 0.8876 | 11.0000 | -2.2531 | -0.6437 |

## Examples

| example_group | watcher_policy | date | entry_row | path_case_class | direction_label | target_exposure | watch_triggered | watch_mode | watch_entry_sec | watch_entry_R | watch_final_pnl | watch_weighted_final | watch_mae | obs_signed_qi5_mean | obs_signed_tfi_sum | obs_R_min | obs_R_end | post_final |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| selected_cases | impulse_only | 2026-05-09 | 1615412 | 02_fast_release_reversal | short | 8.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | -0.7975 | -0.9687 | -0.0000 | 12.5486 | -17.8546 |
| selected_cases | impulse_only | 2026-05-14 | 2322885 | 00_non_case | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.8185 | -2.2607 | 0.0000 | 0.3117 | 46.0257 |
| selected_cases | impulse_only | 2026-05-14 | 2340079 | 00_non_case | short | 8.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.6859 | -37.0000 | -30.7220 | -30.7220 | 5.7899 |
| selected_cases | impulse_only | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | short | 10.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.6739 | -28.0000 | -29.7867 | -29.7867 | -23.5389 |
| selected_cases | impulse_only | 2026-05-14 | 2377379 | 02_fast_release_reversal | short | 10.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9534 | -14.0000 | -10.0351 | -10.0351 | -23.3014 |
| selected_cases | impulse_only | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9380 | -26.0000 | -18.9725 | -18.6764 | 9.7968 |
| selected_cases | impulse_only | 2026-05-14 | 2383289 | 00_non_case | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9242 | -17.0000 | -9.9211 | -9.9211 | 6.3083 |
| selected_cases | impulse_only | 2026-05-15 | 2540829 | 04_late_release_collapse | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9363 | -19.0000 | -1.2703 | -0.9527 | -38.1801 |
| selected_cases | impulse_only | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |
| triggered | impulse_only | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-09 | 1615412 | 02_fast_release_reversal | short | 8.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | -0.7975 | -0.9687 | -0.0000 | 12.5486 | -17.8546 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2322885 | 00_non_case | long | 2.0000 | True | absorb_reclaim | 13.1128 | 2.1817 | 43.8440 | 87.6881 | 0.0000 | 0.8185 | -2.2607 | 0.0000 | 0.3117 | 46.0257 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2340079 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 6.3021 | -25.2537 | 31.0436 | 248.3491 | 0.0000 | 0.6859 | -37.0000 | -30.7220 | -30.7220 | 5.7899 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | short | 10.0000 | True | absorb_reclaim | 11.3010 | -26.8121 | 3.2732 | 32.7318 | 0.0000 | 0.6739 | -28.0000 | -29.7867 | -29.7867 | -23.5389 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2377379 | 02_fast_release_reversal | short | 10.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9534 | -14.0000 | -10.0351 | -10.0351 | -23.3014 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 8.3024 | -16.8992 | 26.6959 | 213.5676 | -0.2962 | 0.9380 | -26.0000 | -18.9725 | -18.6764 | 9.7968 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2383289 | 00_non_case | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9242 | -17.0000 | -9.9211 | -9.9211 | 6.3083 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-15 | 2540829 | 04_late_release_collapse | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9363 | -19.0000 | -1.2703 | -0.9527 | -38.1801 |
| selected_cases | watcher_q65_absorb_reclaim2 | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |
| triggered | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2322885 | 00_non_case | long | 2.0000 | True | absorb_reclaim | 13.1128 | 2.1817 | 43.8440 | 87.6881 | 0.0000 | 0.8185 | -2.2607 | 0.0000 | 0.3117 | 46.0257 |
| triggered | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2340079 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 6.3021 | -25.2537 | 31.0436 | 248.3491 | 0.0000 | 0.6859 | -37.0000 | -30.7220 | -30.7220 | 5.7899 |
| triggered | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | short | 10.0000 | True | absorb_reclaim | 11.3010 | -26.8121 | 3.2732 | 32.7318 | 0.0000 | 0.6739 | -28.0000 | -29.7867 | -29.7867 | -23.5389 |
| triggered | watcher_q65_absorb_reclaim2 | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 8.3024 | -16.8992 | 26.6959 | 213.5676 | -0.2962 | 0.9380 | -26.0000 | -18.9725 | -18.6764 | 9.7968 |
| triggered | watcher_q65_absorb_reclaim2 | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-09 | 1615412 | 02_fast_release_reversal | short | 8.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | -0.7975 | -0.9687 | -0.0000 | 12.5486 | -17.8546 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2322885 | 00_non_case | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.8185 | -2.2607 | 0.0000 | 0.3117 | 46.0257 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2340079 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 6.3021 | -25.2537 | 31.0436 | 248.3491 | 0.0000 | 0.6859 | -37.0000 | -30.7220 | -30.7220 | 5.7899 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | short | 10.0000 | True | absorb_reclaim | 11.6033 | -25.9195 | 2.3806 | 23.8060 | 0.0000 | 0.6739 | -28.0000 | -29.7867 | -29.7867 | -23.5389 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2377379 | 02_fast_release_reversal | short | 10.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9534 | -14.0000 | -10.0351 | -10.0351 | -23.3014 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 14.0073 | -13.6401 | 23.4369 | 187.4955 | 0.0000 | 0.9380 | -26.0000 | -18.9725 | -18.6764 | 9.7968 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2383289 | 00_non_case | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9242 | -17.0000 | -9.9211 | -9.9211 | 6.3083 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-15 | 2540829 | 04_late_release_collapse | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9363 | -19.0000 | -1.2703 | -0.9527 | -38.1801 |
| selected_cases | watcher_q65_absorb_reclaim3 | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |
| triggered | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2340079 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 6.3021 | -25.2537 | 31.0436 | 248.3491 | 0.0000 | 0.6859 | -37.0000 | -30.7220 | -30.7220 | 5.7899 |
| triggered | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | short | 10.0000 | True | absorb_reclaim | 11.6033 | -25.9195 | 2.3806 | 23.8060 | 0.0000 | 0.6739 | -28.0000 | -29.7867 | -29.7867 | -23.5389 |
| triggered | watcher_q65_absorb_reclaim3 | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 14.0073 | -13.6401 | 23.4369 | 187.4955 | 0.0000 | 0.9380 | -26.0000 | -18.9725 | -18.6764 | 9.7968 |
| triggered | watcher_q65_absorb_reclaim3 | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-09 | 1615412 | 02_fast_release_reversal | short | 8.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | -0.7975 | -0.9687 | -0.0000 | 12.5486 | -17.8546 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2322885 | 00_non_case | long | 2.0000 | True | absorb_reclaim | 13.1128 | 2.1817 | 43.8440 | 87.6881 | 0.0000 | 0.8185 | -2.2607 | 0.0000 | 0.3117 | 46.0257 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2340079 | 00_non_case | short | 8.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.6859 | -37.0000 | -30.7220 | -30.7220 | 5.7899 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2361187 | 03_large_release_plateau_decay | short | 10.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.6739 | -28.0000 | -29.7867 | -29.7867 | -23.5389 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2377379 | 02_fast_release_reversal | short | 10.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9534 | -14.0000 | -10.0351 | -10.0351 | -23.3014 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 8.3024 | -16.8992 | 26.6959 | 213.5676 | -0.2962 | 0.9380 | -26.0000 | -18.9725 | -18.6764 | 9.7968 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2383289 | 00_non_case | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9242 | -17.0000 | -9.9211 | -9.9211 | 6.3083 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-15 | 2540829 | 04_late_release_collapse | long | 2.0000 | False | none |  |  | 0.0000 | 0.0000 | 0.0000 | 0.9363 | -19.0000 | -1.2703 | -0.9527 | -38.1801 |
| selected_cases | watcher_q70_absorb_reclaim2 | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |
| triggered | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2322885 | 00_non_case | long | 2.0000 | True | absorb_reclaim | 13.1128 | 2.1817 | 43.8440 | 87.6881 | 0.0000 | 0.8185 | -2.2607 | 0.0000 | 0.3117 | 46.0257 |
| triggered | watcher_q70_absorb_reclaim2 | 2026-05-14 | 2379419 | 00_non_case | short | 8.0000 | True | absorb_reclaim | 8.3024 | -16.8992 | 26.6959 | 213.5676 | -0.2962 | 0.9380 | -26.0000 | -18.9725 | -18.6764 | 9.7968 |
| triggered | watcher_q70_absorb_reclaim2 | 2026-05-15 | 2583437 | 04_late_release_collapse | long | 4.0000 | True | impulse_5s | 5.5039 | -5.7947 | 55.2346 | 220.9383 | -0.6441 | 0.8876 | 11.0000 | -2.2531 | -0.6437 | 49.4399 |

## Read

- `impulse_only` is the previous strict witness, but with a conservative
  re-entry mark at the first event at or after 5s.
- `watcher_q70_absorb_reclaim2` is the cleaner watcher: it catches
  `2583437`, `2322885`, and `2379419` while keeping `1615412`,
  `2377379`, and `2540829` closed.
- `watcher_q65_absorb_reclaim2` is the higher-recall watcher. It also
  catches `2340079` and a small positive re-entry in `2361187`, but the
  lower queue threshold should be treated as a research sensitivity, not
  a live setting.
- The absorption branch is not same-side impulse. It is a reset-low reclaim
  rule after adverse trade pressure fails to keep pushing price against
  the original side.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_watcher_events_20260519_ccusdt_v1_tfi_post_exit_watcher_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_watcher_policy_summary_20260519_ccusdt_v1_tfi_post_exit_watcher_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_watcher_case_summary_20260519_ccusdt_v1_tfi_post_exit_watcher_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_post_exit_watcher_examples_20260519_ccusdt_v1_tfi_post_exit_watcher_v1.csv`

## Reproduce

```powershell
python scripts/ccusdt_v1_tfi_post_exit_watcher.py
```

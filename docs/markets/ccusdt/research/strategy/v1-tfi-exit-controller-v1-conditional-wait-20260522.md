# CCUSDT q70 idle01_g1 ExitControllerV1 conditional wait policy

This is the first unified exit-controller prototype. It only enables:

\[
a_t \in \{\text{cross now},\ \text{wait }\tau\text{ then cross}\}.
\]

Maker/post-only fallback is intentionally disabled.

## Rule

For each test date, exit profile, TTL, and predefined runtime-safe gate, train on dates strictly before the test date. Promote wait only if prior evidence satisfies:

\[
\mathbb E[W_t(\tau)\mid X_t] > m
\]

plus positive-day, CVaR, worst-event, and worst-day guards.

## Scope

- Panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_q70_idle01_g1_20260505_18_20260522\conditional_wait_exit_panel.parquet`
- Evaluation dates: `2026-05-16..2026-05-18`
- Margin: `0.0500` bps
- Min train n/exposure: `80` / `40.0000`
- Min prior days / positive-day fraction: `8` / `0.6700`
- Min CVaR10 / worst event / worst day: `-5.0000` / `-60.0000` / `-75.0000`
- Candidate rows: `1260`
- Promoted candidate rows: `74`

## Aggregate

| exit_profile_source | days | selected_wait_days | wait_attempts | wait_attempt_exposure | pure_taker_weighted_net_bps | wait_delta_weighted_bps | wait_controller_weighted_net_bps | wait_weighted_delay_loss_bps | event_worst_wait_value_bps | event_cvar10_wait_value_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 3 | 3 | 85 | 56.7500 | 644.0728 | 39.5357 | 683.6085 | 6.5354 | -5.2077 | -1.3821 |
| fixed45_livecoherent | 3 | 3 | 62 | 35.0000 | 646.4341 | 28.7816 | 675.2157 | 11.5270 | -6.5125 | -3.6391 |
| fixed60_taker | 3 | 1 | 71 | 26.6250 | 545.2394 | -1.4237 | 543.8157 | 7.9560 | -6.6948 | -2.6520 |
| stopping_rule_v1 | 3 | 2 | 189 | 74.2500 | 577.5528 | -1.4309 | 576.1219 | 19.6045 | -13.3378 | -2.6479 |

## Selected Prior-Date Policy

| exit_profile_source | test_date | selected | ttl_sec | gate_name | promote_reason | train_n | train_weighted_mean_wait_value_bps | train_cvar10_wait_value_bps | train_worst_wait_value_bps | train_positive_day_frac | train_min_day_wait_sum_bps | wait_attempts | wait_delta_weighted_bps | wait_controller_weighted_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | True | 5.0000 | path_d_low_q30_spread_q70 | promoted_prior_wait_edge | 352.0000 | 0.4856 | -3.3803 | -11.4207 | 0.7273 | -2.3347 | 26 | 2.5190 | 130.5726 |
| fixed30_livecoherent | 2026-05-17 | True | 5.0000 | path_d_low_q30_spread_q70 | promoted_prior_wait_edge | 379.0000 | 0.4602 | -3.2900 | -11.4207 | 0.7500 | -2.3347 | 29 | 19.0566 | 369.9480 |
| fixed30_livecoherent | 2026-05-18 | True | 5.0000 | path_d_low_q30_spread_q70 | promoted_prior_wait_edge | 407.0000 | 0.4971 | -3.2714 | -11.4207 | 0.7692 | -2.3347 | 30 | 17.9600 | 183.0880 |
| fixed45_livecoherent | 2026-05-16 | True | 5.0000 | spread_q90 | promoted_prior_wait_edge | 196.0000 | 0.8047 | -2.4255 | -6.6475 | 0.7273 | -2.5399 | 17 | -0.4803 | 117.1522 |
| fixed45_livecoherent | 2026-05-17 | True | 5.0000 | path_d_low_q30_spread_q70 | promoted_prior_wait_edge | 325.0000 | 0.5011 | -1.6850 | -9.7478 | 0.9167 | -0.8572 | 26 | 28.9107 | 336.1587 |
| fixed45_livecoherent | 2026-05-18 | True | 5.0000 | spread_q90 | promoted_prior_wait_edge | 226.0000 | 0.8355 | -3.1305 | -9.0980 | 0.6923 | -2.5399 | 19 | 0.3512 | 221.9049 |
| fixed60_taker | 2026-05-16 | True | 2.0000 | cell_10 | promoted_prior_wait_edge | 1050.0000 | 0.0755 | -2.3633 | -18.8444 | 0.7273 | -9.4814 | 71 | -1.4237 | 50.6897 |
| fixed60_taker | 2026-05-17 | False |  | cross_now | no_promoted_prior_gate |  |  |  |  |  |  | 0 | 0.0000 | 249.7340 |
| fixed60_taker | 2026-05-18 | False |  | cross_now | no_promoted_prior_gate |  |  |  |  |  |  | 0 | 0.0000 | 243.3920 |
| stopping_rule_v1 | 2026-05-16 | True | 2.0000 | cell_10 | promoted_prior_wait_edge | 1050.0000 | 0.0755 | -2.3633 | -18.8444 | 0.7273 | -9.4814 | 71 | -1.4237 | 50.6897 |
| stopping_rule_v1 | 2026-05-17 | False |  | cross_now | no_promoted_prior_gate |  |  |  |  |  |  | 0 | 0.0000 | 282.7840 |
| stopping_rule_v1 | 2026-05-18 | True | 2.0000 | cell_10 | promoted_prior_wait_edge | 1190.0000 | 0.0796 | -2.3734 | -18.8444 | 0.6923 | -9.4814 | 118 | -0.0072 | 242.6483 |

## Event Summary

| exit_profile_source | date | gate_name | ttl_sec | wait_attempts | exposure | weighted_wait_value | weighted_delay_loss | worst_wait_value |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | path_d_low_q30_spread_q70 | 5.0000 | 26 | 17.3750 | 2.5190 | 1.2486 | -3.3297 |
| fixed30_livecoherent | 2026-05-17 | path_d_low_q30_spread_q70 | 5.0000 | 29 | 20.8750 | 19.0566 | 5.2867 | -5.2077 |
| fixed30_livecoherent | 2026-05-18 | path_d_low_q30_spread_q70 | 5.0000 | 30 | 18.5000 | 17.9600 | 0.0000 | 0.0000 |
| fixed45_livecoherent | 2026-05-16 | spread_q90 | 5.0000 | 17 | 8.5000 | -0.4803 | 4.9356 | -5.3720 |
| fixed45_livecoherent | 2026-05-17 | path_d_low_q30_spread_q70 | 5.0000 | 26 | 17.6250 | 28.9107 | 2.6774 | -3.2519 |
| fixed45_livecoherent | 2026-05-18 | spread_q90 | 5.0000 | 19 | 8.8750 | 0.3512 | 3.9139 | -6.5125 |
| fixed60_taker | 2026-05-16 | cell_10 | 2.0000 | 71 | 26.6250 | -1.4237 | 7.9560 | -6.6948 |
| stopping_rule_v1 | 2026-05-16 | cell_10 | 2.0000 | 71 | 26.6250 | -1.4237 | 7.9560 | -6.6948 |
| stopping_rule_v1 | 2026-05-18 | cell_10 | 2.0000 | 118 | 47.6250 | -0.0072 | 11.6485 | -13.3378 |

## Boundary

Runtime gates use only exit-decision-visible fields. Post-exit flow, reclaim, wait value, delay loss, and PnL-like outcomes are evaluation labels only.

## Files

- Candidate daily: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_policy_q70_idle01_g1_20260516_18_20260522\conditional_wait_candidate_daily.csv`
- Selected daily: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_policy_q70_idle01_g1_20260516_18_20260522\conditional_wait_selected_daily.csv`
- Events: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_policy_q70_idle01_g1_20260516_18_20260522\conditional_wait_events.parquet`
- Summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\conditional_wait_exit_policy_q70_idle01_g1_20260516_18_20260522\summary.json`

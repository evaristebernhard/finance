# CCUSDT q70 idle01_g1 maker-first exit policy prototype

This is a fast-line, prior-date prototype over the maker exit opportunity panel. It is not a strict Runner maker lifecycle yet.

## Rule

For each test date, exit profile, TTL, and predefined runtime-safe gate, estimate from dates strictly before the test date:

\[
\widehat E[\Delta(\tau)] = \widehat p(\tau)\Delta^{spread} - \widehat L^{unfilled}(\tau) - \widehat A^{selection}(\tau).
\]

The prototype promotes a maker-first exit only if prior sample, exposure, day stability, and margin gates pass. Current-day realized fill/decay labels are used only for evaluation.

## Scope

- Panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_opportunity_q70_idle01_g1_20260516_18_20260522\maker_exit_opportunity_panel.parquet`
- Fill model: `queue_trade_proxy_v1`
- Margin: `0.0500` bps
- Min train n/exposure: `20` / `10.0000`
- Min prior days / positive-day fraction: `1` / `1.0000`
- Candidate rows: `396`
- Promoted candidate rows: `23`

## Selected Prior-Date Policy

| exit_profile_source | test_date | selected | ttl_sec | gate_name | promote_reason | train_n | train_weighted_mean_selection_adjusted_bps | maker_attempts | maker_attempt_exposure | maker_fill_rate | pure_taker_weighted_net_bps | maker_delta_weighted_bps | maker_first_weighted_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 128.0535 | 0.0000 | 128.0535 |
| fixed30_livecoherent | 2026-05-17 | True | 1.0000 | spread_q80_same_flow_q70 | promoted_prior_edge | 27.0000 | 0.2756 | 41 | 26.6250 | 0.0000 | 350.8913 | 4.0808 | 354.9721 |
| fixed30_livecoherent | 2026-05-18 | True | 5.0000 | spread_q80 | promoted_prior_edge | 59.0000 | 0.2934 | 45 | 30.1250 | 0.0444 | 165.1280 | 6.5541 | 171.6820 |
| fixed45_livecoherent | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 117.6324 | 0.0000 | 117.6324 |
| fixed45_livecoherent | 2026-05-17 | True | 5.0000 | spread_q80_same_flow_q70 | promoted_prior_edge | 24.0000 | 0.1786 | 23 | 16.8750 | 0.1739 | 307.2480 | 9.5927 | 316.8407 |
| fixed45_livecoherent | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 221.5537 | 0.0000 | 221.5537 |
| fixed60_taker | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 52.1134 | 0.0000 | 52.1134 |
| fixed60_taker | 2026-05-17 | True | 2.0000 | depth_support_q70 | promoted_prior_edge | 45.0000 | 0.3240 | 43 | 21.8750 | 0.0465 | 249.7340 | -5.4008 | 244.3332 |
| fixed60_taker | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 243.3920 | 0.0000 | 243.3920 |
| stopping_rule_v1 | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 52.1134 | 0.0000 | 52.1134 |
| stopping_rule_v1 | 2026-05-17 | True | 2.0000 | depth_support_q70 | promoted_prior_edge | 45.0000 | 0.3240 | 44 | 20.7500 | 0.0455 | 282.7840 | -1.2106 | 281.5734 |
| stopping_rule_v1 | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 242.6555 | 0.0000 | 242.6555 |

## Aggregate

| exit_profile_source | days | selected_maker_days | maker_attempts | maker_attempt_exposure | pure_taker_weighted_net_bps | maker_delta_weighted_bps | maker_first_weighted_net_bps | saved_spread_weighted_bps | missed_fill_decay_weighted_bps | adverse_selection_weighted_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 3 | 2 | 86 | 56.7500 | 644.0728 | 10.6348 | 654.7077 | 2.9725 | -7.6623 | 1.4928 |
| fixed45_livecoherent | 3 | 1 | 23 | 16.8750 | 646.4341 | 9.5927 | 656.0268 | 11.7826 | 2.1899 | 17.3699 |
| stopping_rule_v1 | 3 | 1 | 44 | 20.7500 | 577.5528 | -1.2106 | 576.3422 | 1.9760 | 3.1866 | 5.9312 |
| fixed60_taker | 3 | 1 | 43 | 21.8750 | 545.2394 | -5.4008 | 539.8386 | 0.8914 | 6.2921 | 7.2986 |

## Promoted Candidate Diagnostics

| exit_profile_source | test_date | ttl_sec | gate_name | train_n | train_exposure | train_fill_rate | train_weighted_mean_selection_adjusted_bps | test_n | maker_attempts | maker_delta_weighted_bps | maker_selection_adjusted_delta_weighted_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-17 | 1.0000 | spread_q80_same_flow_q70 | 27 | 16.7500 | 0.0000 | 0.2756 | 143 | 41 | 4.0808 | 4.0808 |
| fixed30_livecoherent | 2026-05-17 | 1.0000 | spread_q70_same_flow_q70 | 41 | 25.2500 | 0.0000 | 0.1828 | 143 | 41 | 4.0808 | 4.0808 |
| fixed30_livecoherent | 2026-05-17 | 2.0000 | spread_q80 | 30 | 18.3750 | 0.0333 | 0.1421 | 143 | 46 | 3.7457 | 0.3277 |
| fixed30_livecoherent | 2026-05-17 | 5.0000 | spread_q80 | 30 | 18.3750 | 0.0333 | 0.1064 | 143 | 46 | 10.4200 | 0.1668 |
| fixed30_livecoherent | 2026-05-17 | 2.0000 | spread_q70 | 45 | 27.5000 | 0.0444 | 0.1040 | 143 | 46 | 3.7457 | 0.3277 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | spread_q80_same_flow_q70 | 24 | 14.2500 | 0.1250 | 0.1786 | 143 | 23 | 9.5927 | -7.7772 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | spread_q70_same_flow_q70 | 39 | 24.7500 | 0.1026 | 0.1576 | 143 | 42 | 14.5433 | -6.0717 |
| fixed60_taker | 2026-05-17 | 2.0000 | depth_support_q70 | 45 | 26.2500 | 0.0222 | 0.3240 | 143 | 43 | -5.4008 | -12.6994 |
| fixed60_taker | 2026-05-17 | 5.0000 | depth_support_q70 | 45 | 26.2500 | 0.0889 | 0.2655 | 143 | 43 | -21.9041 | -30.1756 |
| fixed60_taker | 2026-05-17 | 2.0000 | recent_alpha_q70 | 129 | 81.6250 | 0.0310 | 0.0525 | 143 | 128 | -24.7451 | -29.5887 |
| fixed60_taker | 2026-05-17 | 1.0000 | spread_q80_same_flow_q70 | 27 | 18.3750 | 0.0000 | 0.0518 | 143 | 46 | -0.9034 | -2.1348 |
| stopping_rule_v1 | 2026-05-17 | 2.0000 | depth_support_q70 | 45 | 26.2500 | 0.0222 | 0.3240 | 143 | 44 | -1.2106 | -7.1418 |
| stopping_rule_v1 | 2026-05-17 | 5.0000 | depth_support_q70 | 45 | 26.2500 | 0.0889 | 0.2655 | 143 | 44 | -16.9043 | -26.6830 |
| stopping_rule_v1 | 2026-05-17 | 2.0000 | recent_alpha_q70 | 129 | 81.6250 | 0.0310 | 0.0525 | 143 | 119 | -18.9788 | -18.9788 |
| stopping_rule_v1 | 2026-05-17 | 1.0000 | spread_q80_same_flow_q70 | 27 | 18.3750 | 0.0000 | 0.0518 | 143 | 42 | -2.1344 | -2.1344 |
| fixed30_livecoherent | 2026-05-18 | 5.0000 | spread_q80 | 59 | 37.8750 | 0.1017 | 0.2934 | 212 | 45 | 6.5541 | 5.0612 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | spread_q80_same_flow_q70 | 54 | 35.0000 | 0.0000 | 0.2485 | 212 | 38 | 4.1913 | 2.6985 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | spread_q70_same_flow_q70 | 80 | 49.6250 | 0.0000 | 0.1753 | 212 | 47 | 2.4379 | 0.9451 |
| fixed30_livecoherent | 2026-05-18 | 1.0000 | spread_q90 | 30 | 17.3750 | 0.0000 | 0.1434 | 212 | 22 | 3.7579 | 3.2657 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | spread_q80 | 59 | 37.8750 | 0.0508 | 0.1097 | 212 | 45 | 4.4192 | 2.9264 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | spread_q80_same_flow_q70 | 54 | 35.0000 | 0.0370 | 0.1053 | 212 | 38 | 4.4250 | 2.9322 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | spread_q70 | 89 | 54.5000 | 0.0449 | 0.0585 | 212 | 54 | 4.7444 | 4.9243 |
| fixed30_livecoherent | 2026-05-18 | 2.0000 | spread_q70_same_flow_q70 | 80 | 49.6250 | 0.0375 | 0.0548 | 212 | 47 | 4.7502 | 4.9301 |

## Readout

The output should be read as a no-leakage gate test, not as optimized strategy evidence. With only `2026-05-16..2026-05-18` in this panel, `2026-05-16` has no prior training data and later days have very thin prior evidence. A positive selected delta is a candidate for a larger warmup-panel rerun; a negative selected delta is a fast no-go for this simple maker-first family.

# CCUSDT q70 idle01_g1 maker-first exit policy prototype

This is a fast-line, prior-date prototype over the maker exit opportunity panel. It is not a strict Runner maker lifecycle yet.

## Rule

For each test date, exit profile, TTL, and predefined runtime-safe gate, estimate from dates strictly before the test date:

\[
\widehat E[\Delta(\tau)] = \widehat p(\tau)\Delta^{spread} - \widehat L^{unfilled}(\tau) - \widehat A^{selection}(\tau).
\]

The prototype promotes a maker-first exit only if prior sample, exposure, day stability, and margin gates pass. Current-day realized fill/decay labels are used only for evaluation.

## Scope

- Panel: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_opportunity_q70_idle01_g1_20260505_18_20260522\maker_exit_opportunity_panel.parquet`
- Evaluation dates: `2026-05-16..2026-05-18`
- Fill model: `queue_trade_proxy_v1`
- Margin: `0.0500` bps
- Min train n/exposure: `80` / `40.0000`
- Min prior days / positive-day fraction: `8` / `0.6700`
- Candidate rows: `396`
- Promoted candidate rows: `8`

## Selected Prior-Date Policy

| exit_profile_source | test_date | selected | ttl_sec | gate_name | promote_reason | train_n | train_weighted_mean_selection_adjusted_bps | maker_attempts | maker_attempt_exposure | maker_fill_rate | pure_taker_weighted_net_bps | maker_delta_weighted_bps | maker_first_weighted_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | True | 5.0000 | spread_q90 | promoted_prior_edge | 196.0000 | 0.3247 | 12 | 6.8750 | 0.0000 | 128.0535 | 0.8406 | 128.8942 |
| fixed30_livecoherent | 2026-05-17 | True | 5.0000 | spread_q90 | promoted_prior_edge | 211.0000 | 0.3103 | 17 | 9.8750 | 0.1765 | 350.8913 | -0.1180 | 350.7733 |
| fixed30_livecoherent | 2026-05-18 | True | 5.0000 | spread_q90 | promoted_prior_edge | 226.0000 | 0.2881 | 22 | 11.1250 | 0.0455 | 165.1280 | 8.8813 | 174.0093 |
| fixed45_livecoherent | 2026-05-16 | True | 5.0000 | spread_q90 | promoted_prior_edge | 196.0000 | 0.2105 | 17 | 8.5000 | 0.0588 | 117.6324 | -1.2315 | 116.4010 |
| fixed45_livecoherent | 2026-05-17 | True | 5.0000 | spread_q80_same_flow_q70 | promoted_prior_edge | 379.0000 | 0.1932 | 42 | 27.5000 | 0.1429 | 307.2480 | 14.5433 | 321.7913 |
| fixed45_livecoherent | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 221.5537 | 0.0000 | 221.5537 |
| fixed60_taker | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 52.1134 | 0.0000 | 52.1134 |
| fixed60_taker | 2026-05-17 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 249.7340 | 0.0000 | 249.7340 |
| fixed60_taker | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 243.3920 | 0.0000 | 243.3920 |
| stopping_rule_v1 | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 52.1134 | 0.0000 | 52.1134 |
| stopping_rule_v1 | 2026-05-17 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 282.7840 | 0.0000 | 282.7840 |
| stopping_rule_v1 | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 242.6555 | 0.0000 | 242.6555 |

## Aggregate

| exit_profile_source | days | selected_maker_days | maker_attempts | maker_attempt_exposure | pure_taker_weighted_net_bps | maker_delta_weighted_bps | maker_first_weighted_net_bps | saved_spread_weighted_bps | missed_fill_decay_weighted_bps | adverse_selection_weighted_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed45_livecoherent | 3 | 2 | 59 | 36.0000 | 646.4341 | 13.3118 | 659.7459 | 16.5307 | 3.2189 | 21.3662 |
| fixed30_livecoherent | 3 | 3 | 51 | 27.8750 | 644.0728 | 9.6039 | 653.6768 | 7.3290 | -2.2749 | 0.8318 |
| fixed60_taker | 3 | 0 | 0 | 0.0000 | 545.2394 | 0.0000 | 545.2394 | 0.0000 | 0.0000 | 0.0000 |
| stopping_rule_v1 | 3 | 0 | 0 | 0.0000 | 577.5528 | 0.0000 | 577.5528 | 0.0000 | 0.0000 | 0.0000 |

## Event-Chain Summary

| exit_profile_source | date | gate_name | maker_attempts | exposure | maker_fill_rate | weighted_delta | weighted_selection_adjusted_delta | saved_spread | missed_decay | adverse_selection |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | spread_q90 | 12 | 6.8750 | 0.0000 | 0.8406 | 0.8406 | 0.0000 | -0.8406 | 0.0000 |
| fixed30_livecoherent | 2026-05-17 | spread_q90 | 17 | 9.8750 | 0.1765 | -0.1180 | -0.4576 | 5.6070 | 5.7250 | 0.3396 |
| fixed30_livecoherent | 2026-05-18 | spread_q90 | 22 | 11.1250 | 0.0455 | 8.8813 | 8.3892 | 1.7220 | -7.1593 | 0.4922 |
| fixed45_livecoherent | 2026-05-16 | spread_q90 | 17 | 8.5000 | 0.0588 | -1.2315 | -1.9826 | 1.5019 | 2.7334 | 0.7512 |
| fixed45_livecoherent | 2026-05-17 | spread_q80_same_flow_q70 | 42 | 27.5000 | 0.1429 | 14.5433 | -6.0717 | 15.0288 | 0.4855 | 20.6150 |

## Promoted Candidate Diagnostics

| exit_profile_source | test_date | ttl_sec | gate_name | train_n | train_exposure | train_fill_rate | train_weighted_mean_selection_adjusted_bps | test_n | maker_attempts | maker_delta_weighted_bps | maker_selection_adjusted_delta_weighted_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | 5.0000 | spread_q90 | 196 | 124.3750 | 0.0714 | 0.3247 | 149 | 12 | 0.8406 | 0.8406 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | spread_q90 | 196 | 116.3750 | 0.0816 | 0.2105 | 149 | 17 | -1.2315 | -1.9826 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | spread_q80_same_flow_q70 | 354 | 211.3750 | 0.0678 | 0.1945 | 149 | 25 | 8.8576 | 2.5452 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | spread_q80 | 392 | 232.3750 | 0.0740 | 0.0690 | 149 | 31 | 6.5797 | -0.4839 |
| fixed45_livecoherent | 2026-05-16 | 1.0000 | spread_q70_same_flow_q70 | 535 | 322.3750 | 0.0187 | 0.0589 | 149 | 38 | 4.1960 | -0.0000 |
| fixed30_livecoherent | 2026-05-17 | 5.0000 | spread_q90 | 211 | 132.8750 | 0.0664 | 0.3103 | 143 | 17 | -0.1180 | -0.4576 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | spread_q80_same_flow_q70 | 379 | 226.0000 | 0.0712 | 0.1932 | 143 | 42 | 14.5433 | -6.0717 |
| fixed30_livecoherent | 2026-05-18 | 5.0000 | spread_q90 | 226 | 141.5000 | 0.0752 | 0.2881 | 212 | 22 | 8.8813 | 8.3892 |

## Readout

The output should be read as a no-leakage gate test, not as optimized strategy evidence. For every test date, promotion uses only panel rows from strictly earlier dates; current-date fill, decay, selection, and PnL columns are evaluation labels only. A positive selected delta is still only a candidate until a stricter fill proxy and mechanism decomposition confirm that the gain comes from passive execution rather than delayed taker fallback. A negative selected delta is a fast no-go for this simple maker-first family.

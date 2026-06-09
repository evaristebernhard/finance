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
- Min train n/exposure: `50` / `25.0000`
- Min prior days / positive-day fraction: `5` / `0.6000`
- Candidate rows: `396`
- Promoted candidate rows: `20`

## Selected Prior-Date Policy

| exit_profile_source | test_date | selected | ttl_sec | gate_name | promote_reason | train_n | train_weighted_mean_selection_adjusted_bps | maker_attempts | maker_attempt_exposure | maker_fill_rate | pure_taker_weighted_net_bps | maker_delta_weighted_bps | maker_first_weighted_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | True | 5.0000 | spread_q90 | promoted_prior_edge | 196.0000 | 0.3247 | 12 | 6.8750 | 0.0000 | 128.0535 | 0.8406 | 128.8942 |
| fixed30_livecoherent | 2026-05-17 | True | 5.0000 | spread_q90 | promoted_prior_edge | 211.0000 | 0.3103 | 17 | 9.8750 | 0.1765 | 350.8913 | -0.1180 | 350.7733 |
| fixed30_livecoherent | 2026-05-18 | True | 5.0000 | spread_q90 | promoted_prior_edge | 226.0000 | 0.2881 | 22 | 11.1250 | 0.0455 | 165.1280 | 8.8813 | 174.0093 |
| fixed45_livecoherent | 2026-05-16 | True | 2.0000 | spread_q90 | promoted_prior_edge | 196.0000 | 0.2607 | 17 | 8.5000 | 0.0588 | 117.6324 | -6.7894 | 110.8431 |
| fixed45_livecoherent | 2026-05-17 | True | 5.0000 | spread_q90 | promoted_prior_edge | 212.0000 | 0.2147 | 12 | 7.1250 | 0.2500 | 307.2480 | 1.8535 | 309.1014 |
| fixed45_livecoherent | 2026-05-18 | True | 5.0000 | spread_q80_same_flow_q70 | promoted_prior_edge | 403.0000 | 0.1484 | 47 | 27.5000 | 0.0426 | 221.5537 | -0.8657 | 220.6880 |
| fixed60_taker | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 52.1134 | 0.0000 | 52.1134 |
| fixed60_taker | 2026-05-17 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 249.7340 | 0.0000 | 249.7340 |
| fixed60_taker | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 243.3920 | 0.0000 | 243.3920 |
| stopping_rule_v1 | 2026-05-16 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 52.1134 | 0.0000 | 52.1134 |
| stopping_rule_v1 | 2026-05-17 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 282.7840 | 0.0000 | 282.7840 |
| stopping_rule_v1 | 2026-05-18 | False |  | direct_taker | no_promoted_prior_gate |  |  | 0 | 0.0000 | 0.0000 | 242.6555 | 0.0000 | 242.6555 |

## Aggregate

| exit_profile_source | days | selected_maker_days | maker_attempts | maker_attempt_exposure | pure_taker_weighted_net_bps | maker_delta_weighted_bps | maker_first_weighted_net_bps | saved_spread_weighted_bps | missed_fill_decay_weighted_bps | adverse_selection_weighted_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 3 | 3 | 51 | 27.8750 | 644.0728 | 9.6039 | 653.6768 | 7.3290 | -2.2749 | 0.8318 |
| fixed60_taker | 3 | 0 | 0 | 0.0000 | 545.2394 | 0.0000 | 545.2394 | 0.0000 | 0.0000 | 0.0000 |
| stopping_rule_v1 | 3 | 0 | 0 | 0.0000 | 577.5528 | 0.0000 | 577.5528 | 0.0000 | 0.0000 | 0.0000 |
| fixed45_livecoherent | 3 | 3 | 76 | 43.1250 | 646.4341 | -5.8016 | 640.6325 | 15.7254 | 21.5270 | 27.1149 |

## Event-Chain Summary

| exit_profile_source | date | gate_name | maker_attempts | exposure | maker_fill_rate | weighted_delta | weighted_selection_adjusted_delta | saved_spread | missed_decay | adverse_selection |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | spread_q90 | 12 | 6.8750 | 0.0000 | 0.8406 | 0.8406 | 0.0000 | -0.8406 | 0.0000 |
| fixed30_livecoherent | 2026-05-17 | spread_q90 | 17 | 9.8750 | 0.1765 | -0.1180 | -0.4576 | 5.6070 | 5.7250 | 0.3396 |
| fixed30_livecoherent | 2026-05-18 | spread_q90 | 22 | 11.1250 | 0.0455 | 8.8813 | 8.3892 | 1.7220 | -7.1593 | 0.4922 |
| fixed45_livecoherent | 2026-05-16 | spread_q90 | 17 | 8.5000 | 0.0588 | -6.7894 | -7.5406 | 1.5019 | 8.2913 | 0.7512 |
| fixed45_livecoherent | 2026-05-17 | spread_q90 | 12 | 7.1250 | 0.2500 | 1.8535 | -14.6951 | 9.7296 | 7.8761 | 16.5485 |
| fixed45_livecoherent | 2026-05-18 | spread_q80_same_flow_q70 | 47 | 27.5000 | 0.0426 | -0.8657 | -10.6809 | 4.4939 | 5.3595 | 9.8152 |

## Promoted Candidate Diagnostics

| exit_profile_source | test_date | ttl_sec | gate_name | train_n | train_exposure | train_fill_rate | train_weighted_mean_selection_adjusted_bps | test_n | maker_attempts | maker_delta_weighted_bps | maker_selection_adjusted_delta_weighted_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | 5.0000 | spread_q90 | 196 | 124.3750 | 0.0714 | 0.3247 | 149 | 12 | 0.8406 | 0.8406 |
| fixed45_livecoherent | 2026-05-16 | 2.0000 | spread_q90 | 196 | 116.3750 | 0.0459 | 0.2607 | 149 | 17 | -6.7894 | -7.5406 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | spread_q90 | 196 | 116.3750 | 0.0816 | 0.2105 | 149 | 17 | -1.2315 | -1.9826 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | spread_q80_same_flow_q70 | 354 | 211.3750 | 0.0678 | 0.1945 | 149 | 25 | 8.8576 | 2.5452 |
| fixed45_livecoherent | 2026-05-16 | 2.0000 | spread_q80_same_flow_q70 | 354 | 211.3750 | 0.0367 | 0.0942 | 149 | 25 | 4.5396 | 0.3436 |
| fixed45_livecoherent | 2026-05-16 | 5.0000 | spread_q80 | 392 | 232.3750 | 0.0740 | 0.0690 | 149 | 31 | 6.5797 | -0.4839 |
| fixed45_livecoherent | 2026-05-16 | 2.0000 | spread_q70_same_flow_q70 | 535 | 322.3750 | 0.0411 | 0.0655 | 149 | 38 | 4.5396 | 0.3436 |
| fixed45_livecoherent | 2026-05-16 | 1.0000 | spread_q80_same_flow_q70 | 354 | 211.3750 | 0.0226 | 0.0596 | 149 | 25 | 4.1960 | -0.0000 |
| fixed45_livecoherent | 2026-05-16 | 1.0000 | spread_q70_same_flow_q70 | 535 | 322.3750 | 0.0187 | 0.0589 | 149 | 38 | 4.1960 | -0.0000 |
| fixed30_livecoherent | 2026-05-17 | 5.0000 | spread_q90 | 211 | 132.8750 | 0.0664 | 0.3103 | 143 | 17 | -0.1180 | -0.4576 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | spread_q90 | 212 | 124.2500 | 0.0802 | 0.2147 | 143 | 12 | 1.8535 | -14.6951 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | spread_q80_same_flow_q70 | 379 | 226.0000 | 0.0712 | 0.1932 | 143 | 42 | 14.5433 | -6.0717 |
| fixed45_livecoherent | 2026-05-17 | 2.0000 | spread_q80_same_flow_q70 | 379 | 226.0000 | 0.0396 | 0.0896 | 143 | 42 | 9.0809 | -4.8698 |
| fixed45_livecoherent | 2026-05-17 | 5.0000 | spread_q80 | 423 | 249.7500 | 0.0780 | 0.0623 | 143 | 46 | 6.2381 | -14.3770 |
| fixed45_livecoherent | 2026-05-17 | 2.0000 | spread_q70_same_flow_q70 | 573 | 346.3750 | 0.0419 | 0.0620 | 143 | 42 | 9.0809 | -4.8698 |
| fixed45_livecoherent | 2026-05-17 | 1.0000 | spread_q70_same_flow_q70 | 573 | 346.3750 | 0.0209 | 0.0548 | 143 | 42 | 4.6167 | -6.0889 |
| fixed30_livecoherent | 2026-05-18 | 5.0000 | spread_q90 | 226 | 141.5000 | 0.0752 | 0.2881 | 212 | 22 | 8.8813 | 8.3892 |
| fixed45_livecoherent | 2026-05-18 | 5.0000 | spread_q80_same_flow_q70 | 403 | 242.5000 | 0.0819 | 0.1484 | 212 | 47 | -0.8657 | -10.6809 |
| fixed45_livecoherent | 2026-05-18 | 2.0000 | spread_q80_same_flow_q70 | 403 | 242.5000 | 0.0447 | 0.0634 | 212 | 47 | 3.1273 | -5.8709 |
| fixed45_livecoherent | 2026-05-18 | 5.0000 | spread_q90 | 226 | 132.3750 | 0.0885 | 0.0591 | 212 | 19 | -0.4659 | -1.2830 |

## Readout

The output should be read as a no-leakage gate test, not as optimized strategy evidence. With only `2026-05-16..2026-05-18` in this panel, `2026-05-16` has no prior training data and later days have very thin prior evidence. A positive selected delta is a candidate for a larger warmup-panel rerun; a negative selected delta is a fast no-go for this simple maker-first family.

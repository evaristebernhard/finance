# BONK CEX V3 Cross-Venue Lead-Lag / Convergence Analysis

状态: 2026-05-13。本文只做 BONK1MUSDC / BONK1MUSDT cross-venue 诊断分析，不输出交易规则，不声称 alpha。

## Inputs / Outputs

输入:

```text
date/bonk_v3_cross_venue_probe.csv
date/bonk_v3_cross_venue_probe_summary.json
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

输出:

```text
date/bonk_v3_cross_venue_leadlag_summary.csv
docs/markets/bonk/v1-cex-v3-cross-venue-analysis.md
```

样本:

```text
panel rows: 59120 paired rows in original probe; rebuilt pair panel rows: 59195
validation fold paired rows: 34509
time span: 2026-04-29T00:00:00Z .. 2026-05-12T22:59:00Z
barrier: 100 bps
horizons: 1h, 4h, 12h
```

## Method

Cross-venue state is rebuilt at each timestamp by pairing `BONK1MUSDC` and `BONK1MUSDT` from the label/context panel. The main features are:

```text
basis_usdc_minus_usdt_bps = (USDC mid/price / USDT mid/price - 1) * 10_000
spread_usdc_minus_usdt_bps = USDC median spread - USDT median spread
usdc_activity_share = USDC activity / (USDC activity + USDT activity)
microprice_usdc_minus_usdt_bps = USDC microprice offset - USDT microprice offset
```

For convergence, this report uses the actual `t + horizon` basis, not the next minute row:

```text
basis_compression_bps = abs(basis_t) - abs(basis_t+h)
positive basis_compression_bps means the USDC/USDT basis narrowed by horizon end.
```

For lead-lag, the report also measures whether the future USDC-minus-USDT return/residual differential moves against the current basis:

```text
basis_reversion_return_diff_bps = -sign(basis_t) * (future_return_USDC - future_return_USDT)
basis_reversion_resid_diff_bps = -sign(basis_t) * (future_resid_USDC - future_resid_USDT)
```

## Original Probe Cross-Check

The original `bonk_v3_cross_venue_probe` already showed weak signed-direction evidence and clearer state/path hints:

| feature | Spearman vs residual | Spearman vs path width |
| --- | --- | --- |
| basis_usdc_minus_usdt_bps | 0.092 | 0.011 |
| spread_usdc_minus_usdt_bps | 0.002 | -0.039 |
| log_activity_usdc_over_usdt | 0.027 | 0.111 |
| usdc_activity_share | 0.027 | 0.111 |
| microprice_usdc_minus_usdt_bps | -0.000 | 0.070 |

The new output keeps that guardrail and separates direction, path-width, basis compression, and venue-differential reversion targets.

## Direction Residual Read

Validation-fold signed residual correlations are small. The strongest 1h requested-family rows are:

| feature | horizon_hours | rows | Spearman | high-low target | same-sign folds | interpretation_tag |
| --- | --- | --- | --- | --- | --- | --- |
| basis_usdc_minus_usdt_bps | 1 | 11497 | 0.037 | 1.042 | 1.000 | weak_direction_evidence |
| usdc_activity_share | 1 | 11497 | 0.026 | 5.287 | 2.000 | weak_direction_evidence |
| spread_usdc_minus_usdt_bps | 1 | 11497 | 0.011 | 2.323 | 2.000 | weak_direction_evidence |
| abs_microprice_disagreement_bps | 1 | 11497 | 0.006 | -0.763 | 2.000 | weak_direction_evidence |
| microprice_usdc_minus_usdt_bps | 1 | 11497 | 0.006 | 2.178 | 2.000 | weak_direction_evidence |

Read: this is not a clean directional factor set. Signed basis has some diagnostic residual correlation, but the effect is small and not enough to promote to a direction rule. Spread/activity/microprice disagreement mostly behave like conditions under which the market later moves differently, not as stable signed BONK residual predictors.

## Path-Width / Movement-State Read

The clearest cross-venue value is movement-state, especially activity share / activity imbalance and microprice disagreement. Top validation rows by absolute Spearman vs future path width:

| feature | horizon_hours | rows | Spearman | high-low path width | fold1_spearman | fold2_spearman | fold3_spearman | interpretation_tag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| log_activity_usdc_over_usdt | 1 | 11503 | 0.195 | 36.448 | -0.025 | 0.090 | 0.081 | venue_state_path_width_candidate |
| usdc_activity_share | 1 | 11503 | 0.195 | 36.534 | -0.025 | 0.090 | 0.081 | venue_state_path_width_candidate |
| log_activity_usdc_over_usdt | 4 | 11503 | 0.163 | 71.546 | -0.012 | 0.110 | 0.114 | venue_state_path_width_candidate |
| usdc_activity_share | 4 | 11503 | 0.163 | 71.551 | -0.012 | 0.110 | 0.114 | venue_state_path_width_candidate |
| usdc_activity_share | 12 | 11503 | 0.153 | 124.748 | -0.039 | 0.095 | 0.218 | venue_state_path_width_candidate |
| log_activity_usdc_over_usdt | 12 | 11503 | 0.153 | 124.833 | -0.038 | 0.095 | 0.218 | venue_state_path_width_candidate |
| abs_microprice_disagreement_bps | 1 | 11503 | -0.130 | -24.012 | -0.082 | -0.083 | -0.123 | venue_state_path_width_candidate |
| microprice_usdc_minus_usdt_bps | 1 | 11503 | 0.116 | 23.641 | 0.100 | 0.070 | 0.104 | venue_state_path_width_candidate |
| microprice_usdc_minus_usdt_bps | 4 | 11503 | 0.083 | 40.069 | 0.038 | 0.041 | 0.119 | venue_state_path_width_candidate |
| abs_microprice_disagreement_bps | 4 | 11503 | -0.080 | -33.749 | -0.035 | -0.054 | -0.081 | venue_state_path_width_candidate |
| basis_usdc_minus_usdt_bps | 12 | 11503 | -0.062 | 26.121 | 0.111 | -0.198 | -0.097 | venue_state_path_width_candidate |
| abs_basis_usdc_minus_usdt_bps | 4 | 11503 | -0.062 | -50.548 | -0.069 | -0.158 | -0.099 | venue_state_path_width_candidate |

Read: high USDC activity share and activity imbalance often line up with wider future paths. That is a useful venue-state diagnostic: it says the market is in a participation / attention / routing state where future movement width changes. It does not say which direction to buy or sell.

## Basis Compression / Convergence Read

Top validation rows by high-low compression delta:

| feature | target | horizon_hours | rows | Spearman | target_low_bucket_mean | target_high_bucket_mean | high-low target | interpretation_tag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| abs_basis_usdc_minus_usdt_bps | basis_compression_bps | 12 | 11423 | 0.649 | -0.653 | 0.540 | 1.193 | basis_convergence_state |
| abs_basis_usdc_minus_usdt_bps | basis_compression_bps | 4 | 11483 | 0.622 | -0.611 | 0.530 | 1.141 | basis_convergence_state |
| abs_basis_usdc_minus_usdt_bps | basis_compression_bps | 1 | 11486 | 0.602 | -0.574 | 0.508 | 1.082 | basis_convergence_state |
| abs_basis_usdc_minus_usdt_bps | basis_compression_flag | 12 | 11423 | 0.650 | 0.013 | 0.765 | 0.752 | basis_convergence_state |
| abs_basis_usdc_minus_usdt_bps | basis_compression_flag | 4 | 11483 | 0.623 | 0.017 | 0.754 | 0.737 | basis_convergence_state |
| abs_basis_usdc_minus_usdt_bps | basis_compression_flag | 1 | 11486 | 0.609 | 0.033 | 0.747 | 0.714 | basis_convergence_state |
| spread_usdc_minus_usdt_bps | basis_compression_bps | 12 | 11423 | 0.217 | -0.254 | 0.172 | 0.426 | convergence_or_regime_diagnostic |
| spread_usdc_minus_usdt_bps | basis_compression_bps | 4 | 11483 | 0.201 | -0.218 | 0.168 | 0.387 | convergence_or_regime_diagnostic |
| spread_usdc_minus_usdt_bps | basis_compression_bps | 1 | 11486 | 0.193 | -0.204 | 0.138 | 0.342 | convergence_or_regime_diagnostic |
| spread_usdc_minus_usdt_bps | basis_compression_flag | 12 | 11423 | 0.259 | 0.317 | 0.656 | 0.339 | convergence_or_regime_diagnostic |
| spread_usdc_minus_usdt_bps | basis_compression_flag | 4 | 11483 | 0.232 | 0.312 | 0.616 | 0.304 | convergence_or_regime_diagnostic |
| spread_usdc_minus_usdt_bps | basis_compression_flag | 1 | 11486 | 0.228 | 0.298 | 0.588 | 0.290 | convergence_or_regime_diagnostic |

Read: absolute basis naturally has the most direct relation with later compression, because larger starting dislocations have more room to narrow. Signed basis is weaker as a directional residual predictor than absolute basis is as a convergence-state variable. Spread and microprice disagreement are better interpreted as local venue stress / disagreement states around convergence, not as one-sided price forecasts.

## Lead-Lag Venue Differential Read

Top validation rows by high-low venue-differential reversion delta:

| feature | target | horizon_hours | rows | Spearman | target_low_bucket_mean | target_high_bucket_mean | high-low target | same-sign folds | interpretation_tag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| abs_basis_usdc_minus_usdt_bps | basis_reversion_return_diff_bps | 12 | 11494 | 0.598 | 0.017 | 1.151 | 1.133 | 3.000 | lead_lag_convergence_diagnostic |
| abs_basis_usdc_minus_usdt_bps | basis_reversion_resid_diff_bps | 12 | 11494 | 0.598 | 0.017 | 1.151 | 1.133 | 3.000 | lead_lag_convergence_diagnostic |
| abs_basis_usdc_minus_usdt_bps | basis_reversion_return_diff_bps | 4 | 11494 | 0.508 | 0.055 | 0.880 | 0.825 | 3.000 | lead_lag_convergence_diagnostic |
| abs_basis_usdc_minus_usdt_bps | basis_reversion_resid_diff_bps | 4 | 11494 | 0.508 | 0.055 | 0.880 | 0.825 | 3.000 | lead_lag_convergence_diagnostic |
| abs_basis_usdc_minus_usdt_bps | basis_reversion_return_diff_bps | 1 | 11497 | 0.479 | 0.033 | 0.780 | 0.747 | 3.000 | lead_lag_convergence_diagnostic |
| abs_basis_usdc_minus_usdt_bps | basis_reversion_resid_diff_bps | 1 | 11497 | 0.479 | 0.033 | 0.780 | 0.747 | 3.000 | lead_lag_convergence_diagnostic |
| spread_usdc_minus_usdt_bps | basis_reversion_resid_diff_bps | 12 | 11494 | 0.231 | 0.399 | 0.862 | 0.463 | 3.000 | lead_lag_convergence_diagnostic |
| spread_usdc_minus_usdt_bps | basis_reversion_return_diff_bps | 12 | 11494 | 0.231 | 0.399 | 0.862 | 0.463 | 3.000 | lead_lag_convergence_diagnostic |
| abs_spread_usdc_minus_usdt_bps | basis_reversion_resid_diff_bps | 12 | 11494 | 0.209 | 0.461 | 0.796 | 0.335 | 3.000 | lead_lag_convergence_diagnostic |
| abs_spread_usdc_minus_usdt_bps | basis_reversion_return_diff_bps | 12 | 11494 | 0.209 | 0.461 | 0.796 | 0.335 | 3.000 | lead_lag_convergence_diagnostic |
| spread_usdc_minus_usdt_bps | basis_reversion_return_diff_bps | 4 | 11494 | 0.170 | 0.352 | 0.651 | 0.299 | 3.000 | lead_lag_convergence_diagnostic |
| spread_usdc_minus_usdt_bps | basis_reversion_resid_diff_bps | 4 | 11494 | 0.170 | 0.352 | 0.651 | 0.299 | 3.000 | lead_lag_convergence_diagnostic |

Read: there is diagnostic evidence of convergence mechanics, especially when the initial basis is large, but it is better described as venue reversion / basis compression than as a tradeable directional lead-lag factor. If USDC is rich versus USDT, the venue differential can later move against that basis, but this is a relative-venue statement, not a BONK direction statement.

## Requested Families Summary

Representative validation rows for the requested families:

| feature | target | horizon_hours | rows | Spearman | high-low target | interpretation_tag |
| --- | --- | --- | --- | --- | --- | --- |
| abs_basis_usdc_minus_usdt_bps | basis_compression_bps | 12 | 11423 | 0.649 | 1.193 | basis_convergence_state |
| abs_basis_usdc_minus_usdt_bps | basis_compression_bps | 4 | 11483 | 0.622 | 1.141 | basis_convergence_state |
| abs_basis_usdc_minus_usdt_bps | basis_compression_bps | 1 | 11486 | 0.602 | 1.082 | basis_convergence_state |
| spread_usdc_minus_usdt_bps | basis_compression_bps | 12 | 11423 | 0.217 | 0.426 | convergence_or_regime_diagnostic |
| spread_usdc_minus_usdt_bps | basis_compression_bps | 4 | 11483 | 0.201 | 0.387 | convergence_or_regime_diagnostic |
| spread_usdc_minus_usdt_bps | basis_compression_bps | 1 | 11486 | 0.193 | 0.342 | convergence_or_regime_diagnostic |
| basis_usdc_minus_usdt_bps | future_resid_pair_mean_bps | 12 | 11494 | 0.251 | 76.156 | direction_diagnostic_weak_keep_testing |
| basis_usdc_minus_usdt_bps | future_resid_pair_mean_bps | 4 | 11494 | 0.137 | 20.268 | direction_diagnostic_weak_keep_testing |
| abs_basis_usdc_minus_usdt_bps | future_resid_pair_mean_bps | 4 | 11494 | -0.082 | -10.316 | weak_direction_evidence |
| abs_microprice_disagreement_bps | future_resid_pair_mean_bps | 12 | 11494 | 0.062 | 30.190 | weak_direction_evidence |
| usdc_activity_share | future_resid_pair_mean_bps | 12 | 11494 | -0.048 | -17.634 | weak_direction_evidence |
| abs_basis_usdc_minus_usdt_bps | future_resid_pair_mean_bps | 12 | 11494 | -0.044 | -25.828 | weak_direction_evidence |
| usdc_activity_share | path_width_pair_mean_bps | 1 | 11503 | 0.195 | 36.534 | venue_state_path_width_candidate |
| usdc_activity_share | path_width_pair_mean_bps | 4 | 11503 | 0.163 | 71.551 | venue_state_path_width_candidate |
| usdc_activity_share | path_width_pair_mean_bps | 12 | 11503 | 0.153 | 124.748 | venue_state_path_width_candidate |
| abs_microprice_disagreement_bps | path_width_pair_mean_bps | 1 | 11503 | -0.130 | -24.012 | venue_state_path_width_candidate |
| abs_microprice_disagreement_bps | path_width_pair_mean_bps | 4 | 11503 | -0.080 | -33.749 | venue_state_path_width_candidate |
| basis_usdc_minus_usdt_bps | path_width_pair_mean_bps | 12 | 11503 | -0.062 | 26.121 | venue_state_path_width_candidate |

## Conclusion

Current BONK cross-venue evidence looks more like `venue-state` than a direction factor.

The useful signal is: USDC/USDT basis, spread difference, activity share, and microprice disagreement describe where liquidity, attention, and price agreement sit across the two Bullish books. These states can explain future path width and basis compression better than they explain signed future residual returns. That makes them useful for regime diagnostics, convergence monitoring, and candidate gating for later research, but not enough to state a standalone directional alpha.

Next validation should pre-register a small set of venue-state hypotheses:

```text
1. abs_basis high -> higher probability/magnitude of basis compression.
2. USDC activity share / activity imbalance high -> wider future path, not necessarily direction.
3. microprice disagreement high -> local disagreement state; test path-width and compression first.
4. spread diff high -> liquidity-stress state; control BONK RV/common mode before any residual interpretation.
```

# BONK V10b Path-Conditioned Dynamic Factor Mining

Status: 2026-05-15. Fixed-window research diagnostics for `run_tag=20260514_bonk_v10_stage1_pilot`.

Guardrail: `research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim`. This is not trading advice, not an execution recommendation, and not an alpha claim.

## Scope

This pass does not redownload raw data, does not rerun replay, and does not delete raw files. It reads the completed V10 replay state parts plus existing potential/filter/path/control artifacts.

Replay coverage evidence:

```text
completed replay state files: 14
symbols: BONK1MUSDC, BONK1MUSDT
dates: 2026-05-06 .. 2026-05-12
```

Quality analysis is used only as a usability filter here. The generic quality tables from V10 are not repeated.

## Outputs

| artifact | exists | bytes |
| --- | --- | --- |
| date\bonk_v10b_path_conditioned_factor_params_20260514_bonk_v10_stage1_pilot.csv | True | 332444 |
| date\bonk_v10b_path_conditioned_factor_ranking_20260514_bonk_v10_stage1_pilot.csv | True | 12484795 |
| date\bonk_v10b_path_conditioned_stability_20260514_bonk_v10_stage1_pilot.csv | True | 1504918 |
| date\bonk_v10b_path_conditioned_negative_controls_20260514_bonk_v10_stage1_pilot.csv | True | 135143 |
| date\bonk_v10b_path_conditioned_episode_ranking_20260514_bonk_v10_stage1_pilot.csv | True | 194482 |
| docs\markets\bonk\v1-cex-v10b-path-conditioned-dynamic-factor-mining.md | True | 9521 |
| date\bonk_v10b_path_conditioned_artifact_manifest_20260514_bonk_v10_stage1_pilot.csv | True | 1571 |
| completed_replay_state_files | 14 | 0 |

## Factor Construction

The factors are trailing-only book-change states over `1s/5s/15s/30s/60s/300s`: multi-level OFI proxies, bid/ask depth deltas, withdrawal/replenish states, spread compression/expansion, microprice drift, WOBI drift, slope/curvature change, queue pressure change, filtered pressure change, trade-flow alignment, and cross-venue forcing alignment.

All feature quantiles, robust scalers, gates, and first-passage barriers are fit on train folds only. Validation rows use those frozen train-fit parameters.

## Path Ranking

| fold | symbol | horizon_seconds | side | feature_name | gate | rows | side_return_bps_mean | favorable_minus_adverse_rate | path_asymmetry_bps_mean | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold1 | BONK1MUSDT | 900 | short | trade_flow_alignment_w60s | low_train_q20 | 138 | 13.5673 | 0.384058 | 18.5287 | 52.8996 |
| fold1 | BONK1MUSDT | 300 | short | trade_flow_alignment_w60s | low_train_q20 | 138 | 10.7141 | 0.362319 | 11.773 | 47.5347 |
| fold1 | BONK1MUSDC | 300 | short | trade_flow_alignment_w60s | low_train_q20 | 1052 | 10.7992 | 0.327947 | 12.1948 | 44.2036 |
| fold1 | BONK1MUSDC | 300 | short | cross_venue_queue_pressure_change_forcing_w60s | high_train_q80 | 5826 | 10.4669 | 0.323893 | 11.9979 | 43.4561 |
| fold1 | BONK1MUSDC | 900 | short | trade_flow_alignment_w60s | low_train_q20 | 1052 | 16.0718 | 0.252852 | 19.2441 | 42.3192 |
| fold1 | BONK1MUSDC | 900 | short | cross_venue_queue_pressure_change_forcing_w60s | high_train_q80 | 5826 | 14.7449 | 0.256093 | 17.8312 | 41.2458 |
| fold1 | BONK1MUSDC | 300 | short | cross_venue_ofi_depth25_forcing_w60s | high_train_q80 | 5853 | 9.84597 | 0.295746 | 11.1334 | 39.9772 |
| fold1 | BONK1MUSDT | 300 | short | cross_venue_queue_pressure_change_forcing_w60s | high_train_q80 | 6912 | 9.37502 | 0.298756 | 10.6378 | 39.7825 |
| fold1 | BONK1MUSDC | 900 | short | cross_venue_ofi_depth25_forcing_w60s | high_train_q80 | 5853 | 14.3747 | 0.238339 | 17.1804 | 39.0676 |
| fold1 | BONK1MUSDT | 900 | short | cross_venue_queue_pressure_change_forcing_w60s | high_train_q80 | 6912 | 12.9385 | 0.240307 | 16.3711 | 37.7878 |
| fold1 | BONK1MUSDT | 300 | short | cross_venue_ofi_depth25_forcing_w60s | high_train_q80 | 7035 | 8.17702 | 0.270505 | 9.28514 | 35.6917 |
| fold1 | BONK1MUSDT | 900 | short | cross_venue_ofi_depth25_forcing_w60s | high_train_q80 | 7035 | 11.9024 | 0.21592 | 14.7461 | 34.2317 |

Interpretation: positive validation path scores are treated as explanatory diagnostics only. They identify which trailing dynamic book-change states line up with first-passage path shape in this pilot; they do not establish an executable rule.

## After-Cost Episode Ranking

| fold | symbol | side | execution_model | timeout_seconds | feature_name | gate | trades | net_bps_mean | win_rate | cost_bps_mean | queue_penalty_bps_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fold1 | BONK1MUSDT | short | maker_light | 300 | trade_flow_alignment_w60s | low_train_q20 | 188 | 0.456378 | 0.728723 | 3.0568 | 0.712969 |
| fold1 | BONK1MUSDT | short | maker_light | 60 | trade_flow_alignment_w60s | low_train_q20 | 188 | 0.17405 | 0.670213 | 3.0568 | 0.712969 |
| fold1 | BONK1MUSDC | short | maker_light | 300 | trade_flow_alignment_w60s | low_train_q20 | 344 | -0.155161 | 0.665698 | 3.06476 | 0.720903 |
| fold1 | BONK1MUSDT | short | taker_spread | 300 | trade_flow_alignment_w60s | low_train_q20 | 188 | -0.218622 | 0.728723 | 3.7318 | 0.712969 |
| fold3 | BONK1MUSDT | short | maker_light | 300 | trade_flow_alignment_w300s | high_train_q80 | 1388 | -0.4264 | 0.643372 | 2.98042 | 0.646399 |
| fold1 | BONK1MUSDT | short | taker_spread | 60 | trade_flow_alignment_w60s | low_train_q20 | 188 | -0.500949 | 0.670213 | 3.7318 | 0.712969 |
| fold1 | BONK1MUSDT | short | maker_light | 300 | cross_venue_queue_pressure_change_forcing_w60s | high_train_q80 | 652 | -0.786375 | 0.639571 | 3.04236 | 0.698563 |
| fold1 | BONK1MUSDT | short | maker_light | 60 | cross_venue_queue_pressure_change_forcing_w60s | high_train_q80 | 652 | -0.791241 | 0.567485 | 3.04236 | 0.698563 |
| fold1 | BONK1MUSDT | short | maker_light | 60 | cross_venue_ofi_depth25_forcing_w60s | high_train_q80 | 640 | -0.800646 | 0.565625 | 3.04365 | 0.699671 |
| fold1 | BONK1MUSDT | short | maker_light | 300 | cross_venue_ofi_depth25_forcing_w60s | high_train_q80 | 640 | -0.810535 | 0.639062 | 3.04365 | 0.699671 |
| fold1 | BONK1MUSDC | short | taker_spread | 300 | trade_flow_alignment_w60s | low_train_q20 | 344 | -0.826287 | 0.665698 | 3.73589 | 0.720903 |
| fold1 | BONK1MUSDC | short | maker_light | 60 | trade_flow_alignment_w60s | low_train_q20 | 344 | -0.949568 | 0.505814 | 3.06476 | 0.720903 |

No stable after-cost candidate survives as a clean result across the episode layer. A few slices can be positive, but they are not stable across fold/symbol/control checks. The more conservative reading is that Bullish L2 is currently more useful as an execution and usability filter than as directional alpha.

## Stability Checks

| group_scope | groups | rows | side_return_bps_mean | favorable_minus_adverse_rate |
| --- | --- | --- | --- | --- |
| date | 4 | 2.68174e+06 | 1.85228 | 0.0371264 |
| fold | 3 | 2.68174e+06 | 2.86066 | 0.0352838 |
| hour | 83 | 2.68174e+06 | -0.207013 | -0.0164572 |
| non_overlap | 2 | 1871 | 3.77772 | 0.116388 |

The stability table checks symbol/date/hour/fold/non-overlap dependence. Strong single-day or hour concentration is treated as a warning rather than as evidence.

## Negative Controls

| group_scope | rows | side_return_bps_mean | favorable_minus_adverse_rate |
| --- | --- | --- | --- |
| reversed_sign | 3.40828e+06 | 1.2553 | 0.00627841 |
| shuffled_within_date | 2.66434e+06 | -0.194178 | -0.0302156 |
| wrong_symbol_same_factor | 2.83335e+06 | 1.94395 | 0.03261 |

Controls include reversed-sign gates, deterministic within-date shuffles, and wrong-symbol same-factor gates. Any candidate that is not clearly separated from these controls is classified as a cost/window artifact.

## Current Read

Dynamic book-change states with the clearest path explanation in this pilot are the short-window trade-flow alignment, queue/OFI, withdrawal/replenish, and cross-venue forcing families. The strongest path rows concentrate in early validation folds, so they are explanatory states, not deployable direction signals.

Path-explanatory states in this run:

- `trade_flow_alignment_w60s` on the low train-fitted gate is the clearest first-passage path explainer in the top rows, especially for short-side 300s/900s validation paths.
- `cross_venue_queue_pressure_change_forcing_w60s` and `cross_venue_ofi_depth25_forcing_w60s` explain some same-direction path shape, but their wrong-symbol controls are not clean enough to call the effect robust.
- Queue/OFI and withdrawal/replenish families are useful as state descriptors; they need fold/hour confirmation before they can be treated as anything stronger.

Cost/window artifacts in this run:

- The spread regime is mostly a usability context, not a directional factor; tight spread alone does not survive path/cost checks.
- The one positive maker-light slice is not stable across folds and symbols, while taker-spread and wide-stress costs remain negative in the episode layer.
- Hour-level stability is weaker than date/fold summaries, so some apparent path score is a window-concentration effect.

States that mostly fire in tight-spread windows but fail after costs or controls are best read as cost/window artifacts. In particular, spread-tight context is useful for filtering replay usability, but it is not by itself directional evidence.

## Reproduce

```bash
python scripts/bonk_v10b_path_conditioned_dynamic_factor_mining.py
```

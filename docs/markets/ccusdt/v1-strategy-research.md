# CCUSDT Strategy Research Overlay

Status: `20260517_ccusdt_strategy_research_v1` from source panel `20260517_ccusdt_fixed_factors_v3`.

Guardrail: `research_only_toy_replay_no_execution_recommendation_no_alpha_claim`.

This is a toy replay research overlay. It is not queue-position fill evidence, not live execution simulation, not trading advice, and not an alpha claim.

## Scope

- Panel rows loaded: `2606830`.
- Dates: `17`.
- Features tested: `11` -> `trade_flow_imbalance, mlofi_roll10_l1, mlofi_roll10_l25, mlofi_roll10_l10, mlofi_roll10_l2, mlofi_roll10_l5, mlofi_roll10_l3, trade_arrival_alignment, combo_trade_mlofi_l1, combo_mlofi_l1_l25, combo_book_pressure`.
- Targets: `fwd_event_25_bps, fwd_event_70_bps, fwd_time_10s_bps, fwd_time_60s_bps`.
- Walk-forward folds: `expanding_fold1, expanding_fold2, expanding_fold3`.
- Quantile gates: `0.80, 0.90`.
- Policy families: `follow_extremes, fade_extremes, long_high, short_low`; activity/stale filters; non-overlap first-entry-per-horizon buckets.
- Toy costs: `toy_mid`, `toy_maker_light`, `toy_taker_spread`, `toy_wide_stress`.

## Data Read

| Metric | Value |
| --- | --- |
| median quote-change rate | 3.80% |
| median top-size-change rate | 84.63% |
| median trade-present rate | 9.64% |
| median spread | 2.0051 bps |
| p95 spread median-by-day | 4.0059 bps |

The important semantic caveat is unchanged: CCUSDT is a snapshot-frame factor panel. A positive toy-mid row can be a valid information diagnostic while still failing as an executable strategy once spread/fee/fill uncertainty is applied.

## Top Toy-Mid Probes

| fold | feature | target | policy | filter | quantile | entries | gross_mean_bps | positive_day_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | trade_flow_imbalance | fwd_event_70_bps | short_low | trade_present | 0.8000 | 4368 | 2.4236 | 1.0000 | 8.1634 |
| expanding_fold3 | trade_flow_imbalance | fwd_time_60s_bps | follow_extremes | past25_abs_le_0p5bps | 0.8000 | 1129 | 4.5385 | 1.0000 | 7.8198 |
| expanding_fold3 | trade_flow_imbalance | fwd_event_70_bps | follow_extremes | trade_present | 0.9000 | 6739 | 1.9624 | 1.0000 | 7.2057 |
| expanding_fold3 | combo_trade_mlofi_l1 | fwd_event_70_bps | follow_extremes | trade_present | 0.9000 | 5702 | 1.9193 | 1.0000 | 7.0694 |
| expanding_fold3 | trade_flow_imbalance | fwd_event_70_bps | follow_extremes | past25_abs_le_0p5bps | 0.8000 | 1313 | 3.7011 | 1.0000 | 6.9143 |
| expanding_fold3 | mlofi_roll10_l25 | fwd_event_70_bps | follow_extremes | trade_present | 0.9000 | 6639 | 1.8538 | 1.0000 | 6.8622 |
| expanding_fold3 | combo_mlofi_l1_l25 | fwd_event_70_bps | follow_extremes | trade_present | 0.9000 | 6639 | 1.8538 | 1.0000 | 6.8622 |
| expanding_fold2 | mlofi_roll10_l5 | fwd_time_60s_bps | follow_extremes | trade_present | 0.9000 | 3812 | 2.1176 | 1.0000 | 6.8463 |
| expanding_fold3 | trade_flow_imbalance | fwd_time_10s_bps | short_low | trade_present | 0.9000 | 6309 | 1.8458 | 1.0000 | 6.8369 |
| expanding_fold2 | mlofi_roll10_l3 | fwd_time_60s_bps | follow_extremes | trade_present | 0.9000 | 3807 | 2.0958 | 1.0000 | 6.7831 |
| expanding_fold2 | trade_flow_imbalance | fwd_event_70_bps | follow_extremes | all | 0.9000 | 5045 | 1.8273 | 1.0000 | 6.7784 |
| expanding_fold3 | mlofi_roll10_l1 | fwd_event_70_bps | follow_extremes | trade_present | 0.9000 | 6062 | 1.7961 | 1.0000 | 6.6797 |

## Toy-Cost Survivors

| fold | feature | target | policy | filter | cost_model | entries | net_mean_bps | positive_day_rate | score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | trade_flow_imbalance | fwd_time_60s_bps | follow_extremes | past25_abs_le_0p5bps | toy_maker_light | 1129 | 2.4978 | 0.7500 | 4.2534 |
| expanding_fold3 | trade_flow_imbalance | fwd_time_60s_bps | short_low | past25_abs_le_0p5bps | toy_maker_light | 716 | 2.4218 | 0.7500 | 3.3981 |
| expanding_fold2 | trade_flow_imbalance | fwd_event_70_bps | long_high | trade_present_stale_mid_ge25 | toy_maker_light | 50 | 3.4679 | 1.0000 | 2.0967 |
| expanding_fold2 | trade_flow_imbalance | fwd_event_70_bps | follow_extremes | trade_present_stale_mid_ge25 | toy_maker_light | 123 | 1.8588 | 1.0000 | 1.9219 |
| expanding_fold3 | trade_flow_imbalance | fwd_time_60s_bps | follow_extremes | stale_mid_ge70 | toy_maker_light | 64 | 3.5886 | 0.7500 | 1.7839 |
| expanding_fold3 | combo_book_pressure | fwd_time_60s_bps | short_low | trade_present_stale_mid_ge25 | toy_maker_light | 111 | 2.6919 | 0.7500 | 1.7683 |
| expanding_fold2 | trade_flow_imbalance | fwd_time_10s_bps | long_high | trade_present_stale_mid_ge25 | toy_maker_light | 52 | 2.2201 | 1.0000 | 1.7160 |
| expanding_fold3 | trade_flow_imbalance | fwd_event_70_bps | follow_extremes | stale_mid_ge70 | toy_maker_light | 65 | 3.2221 | 0.7500 | 1.6617 |
| expanding_fold2 | trade_flow_imbalance | fwd_event_25_bps | long_high | stale_mid_ge25 | toy_maker_light | 51 | 2.0405 | 1.0000 | 1.6517 |
| expanding_fold3 | mlofi_roll10_l1 | fwd_event_70_bps | short_low | trade_present_stale_mid_ge25 | toy_maker_light | 62 | 3.2036 | 0.7500 | 1.6281 |
| expanding_fold2 | trade_flow_imbalance | fwd_time_10s_bps | follow_extremes | stale_mid_ge25 | toy_maker_light | 134 | 1.0482 | 1.0000 | 1.5427 |
| expanding_fold3 | trade_flow_imbalance | fwd_event_70_bps | short_low | stale_mid_ge70 | toy_maker_light | 43 | 3.4130 | 0.7500 | 1.5009 |

## Gross-Only Cost Failures

| fold | feature | target | policy | filter | cost_model | entries | gross_mean_bps | net_mean_bps | avg_cost_bps | research_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | trade_flow_imbalance | fwd_time_60s_bps | short_low | trade_present_stale_mid_ge25 | toy_wide_stress | 131 | 7.2183 | -1.9062 | 9.1245 | gross_only_cost_failed |
| expanding_fold3 | mlofi_roll10_l1 | fwd_time_60s_bps | short_low | trade_present_stale_mid_ge25 | toy_wide_stress | 63 | 7.0294 | -1.6795 | 8.7089 | gross_only_cost_failed |
| expanding_fold3 | combo_trade_mlofi_l1 | fwd_time_60s_bps | follow_extremes | trade_present_stale_mid_ge25 | toy_wide_stress | 60 | 6.7545 | -1.7689 | 8.5233 | gross_only_cost_failed |
| expanding_fold2 | trade_flow_imbalance | fwd_time_60s_bps | long_high | trade_present_stale_mid_ge25 | toy_wide_stress | 49 | 6.3548 | -3.2557 | 9.6105 | gross_only_cost_failed |
| expanding_fold3 | combo_trade_mlofi_l1 | fwd_event_70_bps | follow_extremes | trade_present_stale_mid_ge25 | toy_wide_stress | 61 | 6.2346 | -2.3189 | 8.5535 | gross_only_cost_failed |
| expanding_fold3 | trade_flow_imbalance | fwd_time_60s_bps | follow_extremes | stale_mid_ge25 | toy_wide_stress | 210 | 6.1432 | -2.8798 | 9.0230 | gross_only_cost_failed |
| expanding_fold3 | mlofi_roll10_l2 | fwd_time_60s_bps | short_low | trade_present_stale_mid_ge25 | toy_wide_stress | 41 | 6.1415 | -2.6407 | 8.7822 | gross_only_cost_failed |
| expanding_fold3 | mlofi_roll10_l1 | fwd_event_70_bps | long_high | trade_present_stale_mid_ge25 | toy_wide_stress | 42 | 6.0498 | -2.8390 | 8.8888 | gross_only_cost_failed |
| expanding_fold3 | combo_trade_mlofi_l1 | fwd_time_60s_bps | short_low | trade_present_stale_mid_ge25 | toy_wide_stress | 92 | 5.6631 | -3.1934 | 8.8565 | gross_only_cost_failed |
| expanding_fold2 | trade_flow_imbalance | fwd_event_70_bps | long_high | trade_present_stale_mid_ge25 | toy_wide_stress | 50 | 5.6204 | -3.9897 | 9.6101 | gross_only_cost_failed |
| expanding_fold3 | mlofi_roll10_l1 | fwd_event_70_bps | follow_extremes | trade_present_stale_mid_ge25 | toy_wide_stress | 103 | 5.5973 | -3.1046 | 8.7019 | gross_only_cost_failed |
| expanding_fold3 | trade_flow_imbalance | fwd_time_60s_bps | follow_extremes | stale_mid_ge70 | toy_wide_stress | 64 | 5.5843 | -3.3988 | 8.9831 | gross_only_cost_failed |

## Controls

| control | rows | median_entries | median_net_mean_bps | p90_abs_net_mean_bps |
| --- | --- | --- | --- | --- |
| base_toy_mid | 80 | 87.0000 | 5.1982 | 6.3548 |
| reversed_side | 80 | 87.0000 | -5.1982 | 6.3548 |
| past_return_gate | 80 | 125.0000 | -0.6766 | 3.0161 |
| within_day_shifted_signal | 80 | 87.0000 | 0.2306 | 2.9695 |

If `past_return_gate` or `within_day_shifted_signal` remains strong, the factor opportunity should be read as state persistence or recent-move structure rather than a standalone tradable rule.

## Strategy Read

- Toy-cost survivor rows: `103`; by fold/cost: expanding_fold1/toy_maker_light=4, expanding_fold2/toy_maker_light=42, expanding_fold3/toy_maker_light=25, expanding_fold3/toy_taker_spread=32.
- Best maker-light research probe: `trade_flow_imbalance / fwd_time_60s_bps / follow_extremes / past25_abs_le_0p5bps` in `expanding_fold3`, entries `1129`, net `2.4978` bps, positive-day `75.00%`.
- Best taker-spread research probe: `trade_flow_imbalance / fwd_event_70_bps / follow_extremes / trade_present_stale_mid_ge25` in `expanding_fold3`, entries `213`, net `1.2913` bps, positive-day `75.00%`.
- Survivor concentration by feature: `trade_flow_imbalance`=78, `mlofi_roll10_l1`=12, `combo_trade_mlofi_l1`=7, `combo_book_pressure`=4, `combo_mlofi_l1_l25`=1.
- Conservative read: `trade_flow_imbalance` is the only primary strategy-research thread. MLOFI and book-pressure composites are secondary confirmation/probe material, not standalone strategy evidence.
- Promotion blocker: the passing rows still use midpoint labels over a `factor_panel_only` snapshot panel. Queue priority, partial fills, latency, and real fee tier are not represented.

## Research Decision

The strategy overlay should be read as evidence of mixed regimes, not as a single blended rule. Large-sample `trade_flow_imbalance` rows can clear maker-light toy cost, but they are right-tail candidates: `tfi_follow_flat` and `tfi_short_flat` have enough entries and positive mean, while the signal-path pass shows weak or negative medians and high top-tail concentration.

Smaller stale or active rows can look cleaner. `tfi_short_stale25`, `tfi_event_active`, `mlofi_l1_short_active`, and selected combo rows can show stronger mean or better medians, but these are state candidates. They are not broad rules until they survive fold/date splits, quote-transition labels, and matched controls.

The specific `tfi_short_stale25` read is: useful hypothesis, sparse trigger. Fold3 is the attractive row (`131` entries, `5.1872` bps net mean, `2.5130` bps median, `7.1035` bps control margin), but fold2 is only `0.1424` bps net with negative median and fold1 has only `27` entries. Under stricter cost the buffer is thin: fold3 survives taker-spread but fails wide-stress, while fold2 fails taker-spread. Treat `stale25` as a quote-release state to test, not as a primary entry rule.

The per-entry tail/stop deep dive adds two constraints. Large-sample flat TFI is a broader right-tail cluster rather than one-winner luck, but top `10%` net winners still exceed total net profit, and fold2/fold3 flat rows fail under about `+2..+3` bps extra cost. `stale25` is more payoff-intense in fold3, but it is fragile across folds and after top-winner removal. Stop-only is useful for adverse-excursion/recovery diagnostics, not as a parameter grid to optimize.

Do not keep optimizing hard TP/SL grids from this table. If continued, the research should split regimes explicitly: flat right-tail, stale25, stale70, and event-active. MLOFI/book-pressure should remain confirmation or state diagnostics unless they independently survive the same controls.

## Current Read

There are real factor opportunities worth studying, but none should be promoted to executable strategy status from this overlay alone. The useful next step is a quote-transition/residual-target pass: evaluate only true post-signal quote moves, remove recent-return state explicitly, and keep stale snapshot runs separate from event-active rows. `stale25` should enter that pass as its own sparse state, with day-level leave-one-out and top-winner removal. If large-sample rows cannot keep positive `E` after stricter costs and residual controls, or if only small fold3 states remain, this thread should stop rather than drift into parameter optimization.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_strategy_research_quality_20260517_ccusdt_strategy_research_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_strategy_research_candidates_20260517_ccusdt_strategy_research_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_strategy_research_controls_20260517_ccusdt_strategy_research_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_strategy_research_summary_20260517_ccusdt_strategy_research_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_strategy_research.py
```

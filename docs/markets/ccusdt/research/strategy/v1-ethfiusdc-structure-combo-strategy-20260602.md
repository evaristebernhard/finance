# ETHFIUSDC Structure Combo Strategy v0.1

Status: `research_result_20260602`.

Boundary: research-only. This diagnostic reads `decision_frame_v1` and `quote_frame_v1`; labels are diagnostic-only and must not enter Runner/Bot runtime.

## Setup

- symbol: `ETHFIUSDC`
- dates: `2026-05-25..2026-05-31`
- output: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\ethfi_structure_combo_fast_strategy\ethfiusdc_2026-05-25_2026-05-31_v0_1`
- entry center: `E0 active-flow flat-release`
- default episode compression: `5s`

Raw E0 counts by day:

|date|raw_e0_rows|admission_q70_bps|
|---|---|---|
|2026-05-25|341|2.6961|
|2026-05-26|676|2.6738|
|2026-05-27|932|2.6518|
|2026-05-28|427|2.5826|
|2026-05-29|621|2.7211|
|2026-05-30|160|2.5700|
|2026-05-31|113|2.5840|

## Strategy Variant Summary

|variant_id|entries|actual_entries|total_actual_exposure|mean_unit_exec60_bps|weighted_bps_per_exposure|median_unit_exec60_bps|hit_rate|net_weighted_bps|positive_days|days|worst_day_net_weighted_bps|
|---|---|---|---|---|---|---|---|---|---|---|---|
|A_fixed_small|1507|1507|753.5000|3.2461|3.2461|2.5877|0.5481|2445.9287|6|7|-9.9612|
|B_old_fourcell_reference|1754|1341|None|None|None|None|None|2275.2482|6|7|-3.8940|
|C_memory_sized|1507|1506|1133.7500|3.2516|3.5998|2.5887|0.5485|4081.2388|6|7|-12.6804|

## Path Classes

|path_class|n|mean_executable_return_60s_bps|hit_rate|mean_mid60_bps|mean_release_mfe10_bps|mean_decay60_bps|
|---|---|---|---|---|---|---|
|bad_entry|261|-11.6823|0.0000|-6.9009|0.0000|6.9009|
|fast_release_decay|174|-16.1553|0.0000|-11.3388|7.7104|19.0492|
|good_release_hold|628|14.7157|1.0000|19.3981|9.3629|-10.0352|
|neutral|213|8.6067|0.9296|13.3675|0.5880|-12.7795|
|spread_cost_mirage|231|-1.3972|0.0000|3.3231|3.9178|0.5947|

## Memory Buckets

|memory_bucket|n|mean_executable_return_60s_bps|hit_rate|mean_mid60_bps|mean_release_mfe10_bps|mean_decay60_bps|
|---|---|---|---|---|---|---|
|high_delta|187|4.4056|0.5882|9.1505|5.5356|-3.6149|
|high_delta_high_energy|330|3.5559|0.5212|8.2867|6.4027|-1.8840|
|high_energy|193|4.7334|0.6477|9.4872|6.9527|-2.5345|
|low_memory|792|2.5082|0.5265|7.2329|4.7395|-2.4933|
|not_ready|5|-1.0864|0.4000|3.5288|1.6293|-1.8995|

## Cost Stress

|variant_id|extra_roundtrip_cost_bps|actual_entries|net_weighted_bps_after_stress|mean_unit_bps_after_stress|hit_rate_after_stress|
|---|---|---|---|---|---|
|A_fixed_small|0.0000|1507|2445.9287|3.2461|0.5481|
|A_fixed_small|1.0000|1507|1692.4287|2.2461|0.5481|
|A_fixed_small|2.0000|1507|938.9287|1.2461|0.5481|
|A_fixed_small|3.0000|1507|185.4287|0.2461|0.4585|
|C_memory_sized|0.0000|1506|4081.2388|3.2516|0.5485|
|C_memory_sized|1.0000|1506|2947.4888|2.2516|0.5485|
|C_memory_sized|2.0000|1506|1813.7388|1.2516|0.5485|
|C_memory_sized|3.0000|1506|679.9888|0.2516|0.4588|

## Controls

```text
{
  "matched_hit_rate": 0.3477106834771068,
  "matched_mean_exec60_bps": -3.645402840218074,
  "side_flip_hit_rate": 0.13072329130723293,
  "side_flip_mean_exec60_bps": -12.709879182010127
}
```

## Interpretation

The v0.1 result is E0-centered.

```text
C_memory_sized - A_fixed_small unit lift   = 0.0055 bps
C_memory_sized - A_fixed_small total lift  = 1635.3101 weighted bps
C_memory_sized - A_fixed_small exposure    = 380.2500
```

Memory sizing increases total weighted PnL mostly by allocating more exposure to already-positive E0 episodes. It does not yet prove a new independent alpha layer.

Therefore the first ETHFI strategy should remain `E0 active-flow flat-release` centered. `R5/Delta/Energy/Z` should be treated as sizing/risk state until stricter controls show unit edge improvement.

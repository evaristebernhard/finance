# CCUSDT Memory-Strength Pareto Control v0.1

Status: `research_result_20260603`.

Boundary: research-only. This diagnostic reuses existing fast entry candidates and does not modify Runner, Bot, Monitor, or runtime profiles.

## Setup

- baseline run: `fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260505_18_20260522`
- output: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\memory_strength_pareto_control\ccusdt_20260516_20260518_v0_1`
- R5 reconstruction MAE versus saved `a_r5_raw`: `0.1509035823177569`
- memory object: last five already closed shadow candidates, using `raw_bps_mid_fixed60` for runtime-shape reconstruction.
- control object: `requested_exposure_new = requested_exposure_old * psi(Delta_bps, Energy_bps, Z_bps)`.

## Main Test Scope, Stress 0

|variant_id|family|actual_entries|actual_exposure|net_weighted_bps|weighted_bps_per_exposure|positive_days|worst_day_net_weighted_bps|skipped_entries|
|---|---|---|---|---|---|---|---|---|
|M0_observed_control|baseline|504|298.6250|545.2394|1.8258|3|52.1134|260|
|M3_r5_energy_correct_low0.75_boost1.25|r5_energy_correction|504|282.0938|542.1187|1.9218|3|56.2904|260|
|M3_r5_energy_correct_low0.75_boost1.1|r5_energy_correction|504|279.2250|526.8269|1.8867|3|54.5840|260|
|M3_r5_energy_correct_low0.5_boost1.25|r5_energy_correction|504|264.0000|519.2328|1.9668|3|61.9726|260|
|M2_delta_energy_low0.75_boost1.5|delta_energy|504|265.5312|514.4818|1.9376|3|52.0757|260|
|M4_z_gate_low0.75_boost1.25|z_gate|504|267.3438|506.8112|1.8957|3|41.2326|260|
|M3_r5_energy_correct_low0.5_boost1.1|r5_energy_correction|504|261.1313|503.9410|1.9298|3|60.2662|260|
|M2_delta_energy_low0.75_boost1.25|delta_energy|504|258.5312|499.5906|1.9324|3|44.8824|260|
|M2_delta_energy_low0.75_boost1.1|delta_energy|504|253.8562|482.2513|1.8997|3|40.5665|260|
|M4_z_gate_low0.75_boost1.1|z_gate|504|258.0000|480.5352|1.8625|3|38.9475|260|
|M1_delta_q50_low0.75|delta_gate|504|250.6562|469.7683|1.8742|3|37.6891|260|
|M2_delta_energy_low0.5_boost1.5|delta_energy|504|216.5625|436.1460|2.0139|3|35.5215|260|

## Stress +2 bps

|variant_id|family|actual_entries|actual_exposure|net_weighted_bps|weighted_bps_per_exposure|positive_days|worst_day_net_weighted_bps|skipped_entries|
|---|---|---|---|---|---|---|---|---|
|M2_delta_energy_low0.25_boost1.5|delta_energy|504|167.5938|22.6227|0.1350|1|-70.3453|260|
|M2_delta_energy_low0.25_boost1.25|delta_energy|504|160.5938|21.7315|0.1353|1|-73.3511|260|
|M2_delta_energy_low0.25_boost1.1|delta_energy|504|155.9187|13.7422|0.0881|1|-75.1545|260|
|M1_delta_q50_low0.25|delta_gate|504|152.7188|7.6592|0.0502|1|-76.3568|260|
|M2_delta_energy_low0.5_boost1.5|delta_energy|504|216.5625|3.0210|0.0139|1|-88.7285|260|
|M2_delta_energy_low0.5_boost1.25|delta_energy|504|209.5625|2.1298|0.0102|1|-91.7343|260|
|M2_delta_energy_low0.5_boost1.1|delta_energy|504|204.8875|-5.8595|-0.0286|1|-93.5378|260|
|M3_r5_energy_correct_low0.5_boost1.25|r5_energy_correction|504|264.0000|-8.7672|-0.0332|2|-99.0899|260|
|M1_delta_q50_low0.5|delta_gate|504|201.6875|-11.9425|-0.0592|1|-94.7401|260|
|M2_delta_energy_low0.75_boost1.5|delta_energy|504|265.5312|-16.5807|-0.0624|2|-107.1118|260|
|M2_delta_energy_low0.75_boost1.25|delta_energy|504|258.5312|-17.4719|-0.0676|1|-110.1176|260|
|M4_z_gate_low0.5_boost1.25|z_gate|504|219.4062|-18.0109|-0.0821|1|-103.8991|260|

## Stress Ladder

|stress_bps|best_variant|best_net_weighted_bps|baseline_net_weighted_bps|delta_vs_baseline|best_worst_day|
|---|---|---|---|---|---|
|0.0000|M0_observed_control|545.2394|545.2394|0.0000|52.1134|
|1.0000|M3_r5_energy_correct_low0.75_boost1.25|260.0250|246.6144|13.4105|-30.3346|
|2.0000|M2_delta_energy_low0.25_boost1.5|22.6227|-52.0106|74.6333|-70.3453|
|3.0000|M2_delta_energy_low0.25_boost1.25|-138.8622|-350.6356|211.7734|-115.9136|

## Pareto Frontier

|stress_bps|variant_id|family|net_weighted_bps|weighted_bps_per_exposure|worst_day_net_weighted_bps|positive_days|
|---|---|---|---|---|---|---|
|0.0000|M0_observed_control|baseline|545.2394|1.8258|52.1134|3|
|0.0000|M3_r5_energy_correct_low0.75_boost1.25|r5_energy_correction|542.1187|1.9218|56.2904|3|
|0.0000|M3_r5_energy_correct_low0.5_boost1.25|r5_energy_correction|519.2328|1.9668|61.9726|3|
|0.0000|M2_delta_energy_low0.5_boost1.5|delta_energy|436.1460|2.0139|35.5215|3|
|0.0000|M2_delta_energy_low0.25_boost1.5|delta_energy|357.8102|2.1350|18.9672|3|
|0.0000|M2_delta_energy_low0.25_boost1.25|delta_energy|342.9190|2.1353|11.7739|3|
|1.0000|M3_r5_energy_correct_low0.75_boost1.25|r5_energy_correction|260.0250|0.9218|-30.3346|2|
|1.0000|M3_r5_energy_correct_low0.5_boost1.25|r5_energy_correction|255.2328|0.9668|-18.5586|2|
|1.0000|M2_delta_energy_low0.5_boost1.5|delta_energy|219.5835|1.0139|-26.6035|2|
|1.0000|M2_delta_energy_low0.25_boost1.5|delta_energy|190.2165|1.1350|-25.6890|2|
|1.0000|M2_delta_energy_low0.25_boost1.25|delta_energy|182.3253|1.1353|-30.7886|2|
|2.0000|M2_delta_energy_low0.25_boost1.5|delta_energy|22.6227|0.1350|-70.3453|1|
|2.0000|M2_delta_energy_low0.25_boost1.25|delta_energy|21.7315|0.1353|-73.3511|1|
|2.0000|M3_r5_energy_correct_low0.5_boost1.25|r5_energy_correction|-8.7672|-0.0332|-99.0899|2|
|3.0000|M2_delta_energy_low0.25_boost1.25|delta_energy|-138.8622|-0.8647|-115.9136|1|
|3.0000|M2_delta_energy_low0.25_boost1.5|delta_energy|-144.9710|-0.8650|-115.0015|1|

## Read

- Baseline test total: `545.2394` weighted bps.
- Best stress-0 test total: `M0_observed_control` with `545.2394` weighted bps.
- Delta versus baseline: `0.0000` weighted bps.
- In this pass, memory-strength control did not beat the observed old control on raw stress-0 total.
- This diagnostic is not a strategy promotion. It is a control-function screen before any Bot profile change.
- Any candidate must still pass strict replay identity, L2 depth capacity, and exit/decay diagnostics.

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\memory_strength_pareto_control\ccusdt_20260516_20260518_v0_1\memory_control_event_panel.parquet`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\memory_strength_pareto_control\ccusdt_20260516_20260518_v0_1\variant_summary.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\memory_strength_pareto_control\ccusdt_20260516_20260518_v0_1\variant_daily.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\memory_strength_pareto_control\ccusdt_20260516_20260518_v0_1\pareto_frontier.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\memory_strength_pareto_control\ccusdt_20260516_20260518_v0_1\summary.json`

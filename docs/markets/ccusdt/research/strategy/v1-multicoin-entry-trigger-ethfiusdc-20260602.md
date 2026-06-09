# CCUSDT Entry Trigger Family Diagnostic

Status: `ccusdt_entry_trigger_family_diagnostic_v0_1`.

Boundary: research-only; inputs are decision_frame_v1 and quote_frame_v1; future labels are diagnostic only.

## Setup

- dates: `2026-05-29..2026-05-30`
- trigger variants: `42`
- event rows: `89079`
- baseline: `fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521`

## Top Unit Evidence

|variant_id|family_id|n|mean_exec60_bps|mean_mid60_bps|hit_rate_exec60|positive_days|days|status|
|---|---|---|---|---|---|---|---|---|
|E3_stale_giveway_release_z_w30_q80|E3_stale_giveway_release|154|6.5155|11.5740|0.6818|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w60_q80|E2_mild_pressure_giveway|419|6.0076|10.4103|0.5704|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|441|5.5469|10.0527|0.6122|2|2|unit_positive_all_days|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|66|5.1318|10.1332|0.5758|2|2|unit_positive_all_days|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|4927|5.0381|9.6260|0.5354|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w60_q70|E2_mild_pressure_giveway|649|5.0139|9.3704|0.5578|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w60_q70|E2_mild_pressure_giveway|634|4.9722|9.2975|0.5552|2|2|unit_positive_all_days|
|E0_old_tfi_flat_q70|E0_old_tfi_flat|781|4.9683|9.6359|0.5839|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|532|4.9007|9.0999|0.5489|2|2|unit_positive_all_days|
|E3_stale_giveway_release_z_w30_q70|E3_stale_giveway_release|267|4.8928|9.9380|0.5880|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|567|4.8674|9.1771|0.5820|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w30_q70|E2_mild_pressure_giveway|694|4.6851|9.1140|0.5692|2|2|unit_positive_all_days|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|261|4.6829|9.7263|0.5670|2|2|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|722|4.6647|9.1180|0.5609|2|2|unit_positive_all_days|
|E3_stale_giveway_release_l_w60_q80|E3_stale_giveway_release|97|4.4519|9.4990|0.5258|2|2|unit_positive_all_days|

## Top Capacity Evidence

|variant_id|family_id|actual_entries|net_weighted_bps|mean_unit_net_bps|positive_days|days|
|---|---|---|---|---|---|---|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|3435|5273.0654|4.0936|2|2|
|E1_tfi_giveway_confirm_l_w30_q70|E1_tfi_giveway_confirm|3765|4312.9162|3.0547|2|2|
|E1_tfi_giveway_confirm_l_w60_q70|E1_tfi_giveway_confirm|3601|4244.0409|3.1429|2|2|
|E1_tfi_giveway_confirm_z_w60_q70|E1_tfi_giveway_confirm|3470|3737.1870|2.8720|2|2|
|E1_tfi_giveway_confirm_z_w30_q70|E1_tfi_giveway_confirm|3608|3511.6892|2.5955|2|2|
|E1_tfi_giveway_confirm_l_w60_q80|E1_tfi_giveway_confirm|2614|3432.3110|3.5015|2|2|
|E4_cost_allowed_giveway_l_w60_q70_costq70|E4_cost_allowed_giveway|2925|3375.1879|3.0771|2|2|
|E4_cost_allowed_giveway_l_w30_q70_costq70|E4_cost_allowed_giveway|3182|3344.1395|2.8025|2|2|
|E4_cost_allowed_giveway_l_w30_q70_costq50|E4_cost_allowed_giveway|2974|3323.2789|2.9799|2|2|
|E4_cost_allowed_giveway_l_w60_q70_costq50|E4_cost_allowed_giveway|2759|3284.8017|3.1749|2|2|
|E4_cost_allowed_giveway_l_w60_q80_costq70|E4_cost_allowed_giveway|2373|2974.8268|3.3430|2|2|
|E4_cost_allowed_giveway_l_w60_q80_costq50|E4_cost_allowed_giveway|2231|2806.7044|3.3548|2|2|
|E4_cost_allowed_giveway_z_w60_q70_costq70|E4_cost_allowed_giveway|2713|2788.1446|2.7405|2|2|
|E4_cost_allowed_giveway_z_w60_q70_costq50|E4_cost_allowed_giveway|2565|2700.0079|2.8070|2|2|
|E4_cost_allowed_giveway_z_w30_q70_costq70|E4_cost_allowed_giveway|2889|2647.1639|2.4434|2|2|

## Top Cells

|variant_id|family_id|cell|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|E4_cost_allowed_giveway_z_w30_q80_costq50|E4_cost_allowed_giveway|11_r5_frames|135|7.8032|0.7407|
|E3_stale_giveway_release_l_w60_q80|E3_stale_giveway_release|10_r5_only|1|7.6579|1.0000|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|10_r5_only|1|7.6579|1.0000|
|E1_tfi_giveway_confirm_z_w30_q80|E1_tfi_giveway_confirm|11_r5_frames|147|6.7307|0.6939|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|11_r5_frames|147|6.7307|0.6939|
|E3_stale_giveway_release_z_w30_q80|E3_stale_giveway_release|11_r5_frames|147|6.7307|0.6939|
|E4_cost_allowed_giveway_z_w30_q80_costq70|E4_cost_allowed_giveway|11_r5_frames|147|6.7307|0.6939|
|E2_mild_pressure_giveway_l_w60_q80|E2_mild_pressure_giveway|10_r5_only|323|6.4800|0.5851|
|E4_cost_allowed_giveway_l_w30_q80_costq50|E4_cost_allowed_giveway|11_r5_frames|134|6.2294|0.6940|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|10_r5_only|291|5.8463|0.6014|
|E4_cost_allowed_giveway_z_w30_q70_costq50|E4_cost_allowed_giveway|11_r5_frames|235|5.7522|0.6298|
|E4_cost_allowed_giveway_l_w30_q70_costq50|E4_cost_allowed_giveway|11_r5_frames|230|5.5999|0.6087|
|E4_cost_allowed_giveway_z_w60_q70_costq50|E4_cost_allowed_giveway|11_r5_frames|133|5.5232|0.6090|
|E0_old_tfi_flat_q70|E0_old_tfi_flat|00_none|413|5.3565|0.5666|
|E4_cost_allowed_giveway_l_w60_q70_costq50|E4_cost_allowed_giveway|11_r5_frames|134|5.2462|0.5970|

## New-only Candidates vs Old Baseline

|variant_id|family_id|bucket|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|E3_stale_giveway_release_z_w30_q80|E3_stale_giveway_release|new_only|154|6.5155|0.6818|
|E2_mild_pressure_giveway_l_w60_q80|E2_mild_pressure_giveway|new_only|419|6.0076|0.5704|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|new_only|441|5.5469|0.6122|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|new_only|66|5.1318|0.5758|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|new_only|4927|5.0381|0.5354|
|E2_mild_pressure_giveway_l_w60_q70|E2_mild_pressure_giveway|new_only|649|5.0139|0.5578|
|E2_mild_pressure_giveway_z_w60_q70|E2_mild_pressure_giveway|new_only|634|4.9722|0.5552|
|E0_old_tfi_flat_q70|E0_old_tfi_flat|new_only|781|4.9683|0.5839|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|new_only|532|4.9007|0.5489|
|E3_stale_giveway_release_z_w30_q70|E3_stale_giveway_release|new_only|267|4.8928|0.5880|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|new_only|567|4.8674|0.5820|
|E2_mild_pressure_giveway_z_w30_q70|E2_mild_pressure_giveway|new_only|694|4.6851|0.5692|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|new_only|261|4.6829|0.5670|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|new_only|722|4.6647|0.5609|
|E3_stale_giveway_release_l_w60_q80|E3_stale_giveway_release|new_only|97|4.4519|0.5258|

## Guardrails

- Unit evidence evaluates trigger quality before capacity.
- Capacity evidence is a diagnostic approximation, not Bot promotion.
- Dynamic giveway is compared against static low-depth control.
- Runner, Bot, Monitor, legacy `date/`, scored entries, PnL, MFE, and MAE are not runtime inputs.

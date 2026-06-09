# CCUSDT Entry Trigger Family Diagnostic

Status: `ccusdt_entry_trigger_family_diagnostic_v0_1`.

Boundary: research-only; inputs are decision_frame_v1 and quote_frame_v1; future labels are diagnostic only.

## Setup

- dates: `2026-05-29..2026-05-29`
- trigger variants: `42`
- event rows: `75983`
- baseline: `fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521`

## Top Unit Evidence

|variant_id|family_id|n|mean_exec60_bps|mean_mid60_bps|hit_rate_exec60|positive_days|days|status|
|---|---|---|---|---|---|---|---|---|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|3|19.5557|20.7948|0.3333|1|1|unit_positive_all_days|
|E3_stale_giveway_release_z_w60_q70|E3_stale_giveway_release|4|11.1224|13.7231|0.2500|1|1|unit_positive_all_days|
|E3_stale_giveway_release_l_w60_q80|E3_stale_giveway_release|6|8.4382|10.4368|0.1667|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|380|6.8224|10.4328|0.5711|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w60_q80|E2_mild_pressure_giveway|382|6.0115|9.5531|0.5393|1|1|unit_positive_all_days|
|E3_stale_giveway_release_l_w60_q70|E3_stale_giveway_release|7|5.2074|7.8755|0.1429|1|1|unit_positive_all_days|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|8|4.5373|7.0155|0.5000|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w60_q70|E2_mild_pressure_giveway|666|4.4171|8.0827|0.5210|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|280|4.4078|7.7896|0.5321|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w60_q70|E2_mild_pressure_giveway|656|4.0746|7.7724|0.5122|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w30_q70|E2_mild_pressure_giveway|549|3.9815|7.4523|0.4900|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|590|3.3826|7.0153|0.4898|1|1|unit_positive_all_days|
|E1_tfi_giveway_confirm_z_w60_q80|E1_tfi_giveway_confirm|2547|3.1424|6.9351|0.4550|1|1|unit_positive_all_days|
|E1_tfi_giveway_confirm_z_w30_q80|E1_tfi_giveway_confirm|2425|3.0980|7.0077|0.4586|1|1|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|358|3.0776|6.7350|0.5056|1|1|unit_positive_all_days|

## Top Capacity Evidence

|variant_id|family_id|actual_entries|net_weighted_bps|mean_unit_net_bps|positive_days|days|
|---|---|---|---|---|---|---|
|E1_tfi_giveway_confirm_l_w60_q70|E1_tfi_giveway_confirm|3240|3483.3305|2.8669|1|1|
|E1_tfi_giveway_confirm_z_w60_q70|E1_tfi_giveway_confirm|3173|3368.7493|2.8312|1|1|
|E1_tfi_giveway_confirm_l_w30_q70|E1_tfi_giveway_confirm|3193|3202.0105|2.6742|1|1|
|E1_tfi_giveway_confirm_z_w30_q70|E1_tfi_giveway_confirm|3108|3078.2598|2.6411|1|1|
|E4_cost_allowed_giveway_z_w30_q70_costq70|E4_cost_allowed_giveway|2780|2839.5356|2.7238|1|1|
|E4_cost_allowed_giveway_l_w60_q70_costq70|E4_cost_allowed_giveway|2882|2831.4713|2.6199|1|1|
|E4_cost_allowed_giveway_l_w30_q70_costq70|E4_cost_allowed_giveway|2915|2726.9119|2.4946|1|1|
|E1_tfi_giveway_confirm_z_w60_q80|E1_tfi_giveway_confirm|2119|2692.9399|3.3889|1|1|
|E4_cost_allowed_giveway_z_w60_q70_costq70|E4_cost_allowed_giveway|2787|2585.7276|2.4741|1|1|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|4337|2535.3804|1.5589|1|1|
|E1_tfi_giveway_confirm_z_w30_q80|E1_tfi_giveway_confirm|2157|2503.6925|3.0953|1|1|
|E4_cost_allowed_giveway_l_w60_q70_costq50|E4_cost_allowed_giveway|2363|2492.5125|2.8128|1|1|
|E4_cost_allowed_giveway_z_w30_q70_costq50|E4_cost_allowed_giveway|2235|2414.5996|2.8810|1|1|
|E4_cost_allowed_giveway_z_w60_q80_costq70|E4_cost_allowed_giveway|1871|2333.6830|3.3261|1|1|
|E1_tfi_giveway_confirm_l_w30_q80|E1_tfi_giveway_confirm|2167|2317.8425|2.8523|1|1|

## Top Cells

|variant_id|family_id|cell|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|E1_tfi_giveway_confirm_z_w60_q70|E1_tfi_giveway_confirm|11_r5_frames|3|19.5557|0.3333|
|E1_tfi_giveway_confirm_z_w60_q80|E1_tfi_giveway_confirm|11_r5_frames|3|19.5557|0.3333|
|E2_mild_pressure_giveway_z_w60_q70|E2_mild_pressure_giveway|11_r5_frames|3|19.5557|0.3333|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|11_r5_frames|3|19.5557|0.3333|
|E3_stale_giveway_release_z_w60_q70|E3_stale_giveway_release|11_r5_frames|3|19.5557|0.3333|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|11_r5_frames|3|19.5557|0.3333|
|E4_cost_allowed_giveway_z_w60_q70_costq50|E4_cost_allowed_giveway|11_r5_frames|3|19.5557|0.3333|
|E4_cost_allowed_giveway_z_w60_q70_costq70|E4_cost_allowed_giveway|11_r5_frames|3|19.5557|0.3333|
|E4_cost_allowed_giveway_z_w60_q80_costq50|E4_cost_allowed_giveway|11_r5_frames|3|19.5557|0.3333|
|E4_cost_allowed_giveway_z_w60_q80_costq70|E4_cost_allowed_giveway|11_r5_frames|3|19.5557|0.3333|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|11_r5_frames|3|19.5557|0.3333|
|E1_tfi_giveway_confirm_l_w30_q70|E1_tfi_giveway_confirm|11_r5_frames|6|11.0980|0.6667|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|11_r5_frames|6|11.0980|0.6667|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|11_r5_frames|6|11.0980|0.6667|
|E4_cost_allowed_giveway_l_w30_q70_costq50|E4_cost_allowed_giveway|11_r5_frames|6|11.0980|0.6667|

## New-only Candidates vs Old Baseline

|variant_id|family_id|bucket|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|new_only|3|19.5557|0.3333|
|E3_stale_giveway_release_z_w60_q70|E3_stale_giveway_release|new_only|4|11.1224|0.2500|
|E3_stale_giveway_release_l_w60_q80|E3_stale_giveway_release|new_only|6|8.4382|0.1667|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|new_only|380|6.8224|0.5711|
|E2_mild_pressure_giveway_l_w60_q80|E2_mild_pressure_giveway|new_only|382|6.0115|0.5393|
|E3_stale_giveway_release_l_w60_q70|E3_stale_giveway_release|new_only|7|5.2074|0.1429|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|new_only|8|4.5373|0.5000|
|E2_mild_pressure_giveway_l_w60_q70|E2_mild_pressure_giveway|new_only|666|4.4171|0.5210|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|new_only|280|4.4078|0.5321|
|E2_mild_pressure_giveway_z_w60_q70|E2_mild_pressure_giveway|new_only|656|4.0746|0.5122|
|E2_mild_pressure_giveway_z_w30_q70|E2_mild_pressure_giveway|new_only|549|3.9815|0.4900|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|new_only|590|3.3826|0.4898|
|E1_tfi_giveway_confirm_z_w60_q80|E1_tfi_giveway_confirm|new_only|2547|3.1424|0.4550|
|E1_tfi_giveway_confirm_z_w30_q80|E1_tfi_giveway_confirm|new_only|2425|3.0980|0.4586|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|new_only|358|3.0776|0.5056|

## Guardrails

- Unit evidence evaluates trigger quality before capacity.
- Capacity evidence is a diagnostic approximation, not Bot promotion.
- Dynamic giveway is compared against static low-depth control.
- Runner, Bot, Monitor, legacy `date/`, scored entries, PnL, MFE, and MAE are not runtime inputs.

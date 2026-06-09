# CCUSDT Entry Trigger Family Diagnostic

Status: `ccusdt_entry_trigger_family_diagnostic_v0_1`.

Boundary: research-only; inputs are decision_frame_v1 and quote_frame_v1; future labels are diagnostic only.

## Setup

- dates: `2026-05-25..2026-05-31`
- trigger variants: `42`
- event rows: `314090`
- baseline: `fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521`

## Top Unit Evidence

|variant_id|family_id|n|mean_exec60_bps|mean_mid60_bps|hit_rate_exec60|positive_days|days|status|
|---|---|---|---|---|---|---|---|---|
|E3_stale_giveway_release_z_w30_q80|E3_stale_giveway_release|340|3.6427|8.6418|0.5500|4|7|unit_positive_unstable|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|1966|3.0519|7.5480|0.5412|6|7|unit_positive_unstable|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|23232|3.0406|7.5879|0.5217|6|7|unit_positive_unstable|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|2155|2.9851|7.1650|0.5206|7|7|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|3051|2.9542|7.4007|0.5352|7|7|unit_positive_all_days|
|E3_stale_giveway_release_z_w30_q70|E3_stale_giveway_release|962|2.8846|7.9334|0.5489|5|7|unit_positive_unstable|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|2168|2.8568|7.0692|0.5194|7|7|unit_positive_all_days|
|E0_old_tfi_flat_q70|E0_old_tfi_flat|3278|2.7994|7.4806|0.5363|7|7|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w60_q70|E2_mild_pressure_giveway|2806|2.7459|7.1432|0.5239|7|7|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w60_q70|E2_mild_pressure_giveway|2762|2.7091|7.0550|0.5174|7|7|unit_positive_all_days|
|E2_mild_pressure_giveway_l_w60_q80|E2_mild_pressure_giveway|1792|2.6971|7.1188|0.5106|7|7|unit_positive_all_days|
|E2_mild_pressure_giveway_z_w30_q70|E2_mild_pressure_giveway|2900|2.6782|7.0889|0.5259|6|7|unit_positive_unstable|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|1014|2.5605|7.6137|0.5375|5|7|unit_positive_unstable|
|E3_stale_giveway_release_l_w30_q80|E3_stale_giveway_release|663|2.5246|7.5822|0.5460|5|7|unit_positive_unstable|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|155|2.5186|7.3196|0.5290|4|7|unit_positive_unstable|

## Top Capacity Evidence

|variant_id|family_id|actual_entries|net_weighted_bps|mean_unit_net_bps|positive_days|days|
|---|---|---|---|---|---|---|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|15479|16375.5239|2.8211|6|7|
|E1_tfi_giveway_confirm_l_w30_q70|E1_tfi_giveway_confirm|13515|10756.5945|2.1224|6|7|
|E1_tfi_giveway_confirm_l_w60_q70|E1_tfi_giveway_confirm|13206|10654.2336|2.1514|6|7|
|E1_tfi_giveway_confirm_z_w60_q70|E1_tfi_giveway_confirm|13263|9355.1032|1.8809|6|7|
|E1_tfi_giveway_confirm_z_w30_q70|E1_tfi_giveway_confirm|13596|8808.9861|1.7278|6|7|
|E4_cost_allowed_giveway_l_w30_q70_costq70|E4_cost_allowed_giveway|10793|8322.7731|2.0563|6|7|
|E4_cost_allowed_giveway_l_w60_q70_costq70|E4_cost_allowed_giveway|10060|8019.9035|2.1259|6|7|
|E1_tfi_giveway_confirm_l_w60_q80|E1_tfi_giveway_confirm|8996|7705.8940|2.2842|5|7|
|E4_cost_allowed_giveway_l_w30_q70_costq50|E4_cost_allowed_giveway|9565|7073.4234|1.9720|6|7|
|E4_cost_allowed_giveway_l_w60_q70_costq50|E4_cost_allowed_giveway|8982|6994.0392|2.0765|6|7|
|E1_tfi_giveway_confirm_l_w30_q80|E1_tfi_giveway_confirm|8764|6840.9875|2.0815|6|7|
|E1_tfi_giveway_confirm_z_w60_q80|E1_tfi_giveway_confirm|10352|6706.6949|1.7276|6|7|
|E4_cost_allowed_giveway_z_w60_q70_costq70|E4_cost_allowed_giveway|9676|6603.6148|1.8199|5|7|
|E1_tfi_giveway_confirm_z_w30_q80|E1_tfi_giveway_confirm|10622|6331.2604|1.5895|6|7|
|E4_cost_allowed_giveway_l_w60_q80_costq70|E4_cost_allowed_giveway|7859|6291.0463|2.1346|5|7|

## Top Cells

|variant_id|family_id|cell|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|E3_stale_giveway_release_z_w30_q80|E3_stale_giveway_release|10_r5_only|17|5.7185|0.5882|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|10_r5_only|65|5.3942|0.6308|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|10_r5_only|12|5.0132|0.5000|
|E3_stale_giveway_release_z_w30_q70|E3_stale_giveway_release|10_r5_only|57|4.7987|0.5789|
|E4_cost_allowed_giveway_z_w30_q80_costq50|E4_cost_allowed_giveway|11_r5_frames|264|4.1032|0.5682|
|E1_tfi_giveway_confirm_z_w30_q80|E1_tfi_giveway_confirm|11_r5_frames|323|3.5334|0.5480|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|11_r5_frames|323|3.5334|0.5480|
|E3_stale_giveway_release_z_w30_q80|E3_stale_giveway_release|11_r5_frames|323|3.5334|0.5480|
|E4_cost_allowed_giveway_z_w30_q80_costq70|E4_cost_allowed_giveway|11_r5_frames|323|3.5334|0.5480|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|10_r5_only|1327|3.2362|0.5373|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|10_r5_only|2102|3.2196|0.5371|
|E4_cost_allowed_giveway_z_w30_q70_costq50|E4_cost_allowed_giveway|11_r5_frames|701|3.1940|0.5706|
|E0_old_tfi_flat_q70|E0_old_tfi_flat|00_none|1918|3.1626|0.5417|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|10_r5_only|22976|3.0649|0.5222|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|10_r5_only|2012|3.0331|0.5199|

## New-only Candidates vs Old Baseline

|variant_id|family_id|bucket|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|E3_stale_giveway_release_z_w30_q80|E3_stale_giveway_release|new_only|340|3.6427|0.5500|
|E2_mild_pressure_giveway_l_w30_q80|E2_mild_pressure_giveway|new_only|1966|3.0519|0.5412|
|E5_static_low_depth_control_q30|E5_static_low_depth_control|new_only|23232|3.0406|0.5217|
|E2_mild_pressure_giveway_z_w60_q80|E2_mild_pressure_giveway|new_only|2155|2.9851|0.5206|
|E2_mild_pressure_giveway_l_w30_q70|E2_mild_pressure_giveway|new_only|3051|2.9542|0.5352|
|E3_stale_giveway_release_z_w30_q70|E3_stale_giveway_release|new_only|962|2.8846|0.5489|
|E2_mild_pressure_giveway_z_w30_q80|E2_mild_pressure_giveway|new_only|2168|2.8568|0.5194|
|E0_old_tfi_flat_q70|E0_old_tfi_flat|new_only|3278|2.7994|0.5363|
|E2_mild_pressure_giveway_l_w60_q70|E2_mild_pressure_giveway|new_only|2806|2.7459|0.5239|
|E2_mild_pressure_giveway_z_w60_q70|E2_mild_pressure_giveway|new_only|2762|2.7091|0.5174|
|E2_mild_pressure_giveway_l_w60_q80|E2_mild_pressure_giveway|new_only|1792|2.6971|0.5106|
|E2_mild_pressure_giveway_z_w30_q70|E2_mild_pressure_giveway|new_only|2900|2.6782|0.5259|
|E3_stale_giveway_release_l_w30_q70|E3_stale_giveway_release|new_only|1014|2.5605|0.5375|
|E3_stale_giveway_release_l_w30_q80|E3_stale_giveway_release|new_only|663|2.5246|0.5460|
|E3_stale_giveway_release_z_w60_q80|E3_stale_giveway_release|new_only|155|2.5186|0.5290|

## Guardrails

- Unit evidence evaluates trigger quality before capacity.
- Capacity evidence is a diagnostic approximation, not Bot promotion.
- Dynamic giveway is compared against static low-depth control.
- Runner, Bot, Monitor, legacy `date/`, scored entries, PnL, MFE, and MAE are not runtime inputs.

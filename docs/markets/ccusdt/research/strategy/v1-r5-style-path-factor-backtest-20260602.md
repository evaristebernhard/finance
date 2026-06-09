# CCUSDT R5-style path factor fast backtest

Status: `ccusdt_r5_style_path_factor_backtest_v0_1`.

Boundary: research-only; inputs are decision_frame_v1 and quote_frame_v1; future labels are diagnostic only.

## Setup

- symbol: `CCUSDT`
- dates: `2026-05-16..2026-05-18`
- windows_sec: `[30, 60]`
- threshold_quantiles: `[0.7, 0.8]`
- variants: `36`
- baseline: `fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521`

## Status counts

|status|variants|
|---|---|
|diagnostic_positive_unstable|36|

## Top variants by net weighted bps

|variant_id|actual_entries|net_weighted_bps|mean_unit_net_bps|positive_days|days|worst_day_net_weighted_bps|status|
|---|---|---|---|---|---|---|---|
|absolute_pressure_energy_e_w60_q70|1337|424.1275|0.5157|2|3|-98.3923|diagnostic_positive_unstable|
|absolute_pressure_energy_e_w30_q70|1326|400.3907|0.4907|2|3|-103.7379|diagnostic_positive_unstable|
|absolute_pressure_energy_e_w30_q80|1316|394.3658|0.4749|2|3|-122.2503|diagnostic_positive_unstable|
|pressure_without_price_response_z_w60_q80|1329|393.5404|0.4743|2|3|-126.6137|diagnostic_positive_unstable|
|flow_pressure_memory_z_w60_q80|1329|376.4844|0.4552|2|3|-143.3123|diagnostic_positive_unstable|
|absolute_pressure_energy_e_w60_q80|1324|374.3226|0.4482|2|3|-117.2702|diagnostic_positive_unstable|
|pressure_without_price_response_z_w60_q70|1346|368.8504|0.4590|2|3|-155.9965|diagnostic_positive_unstable|
|flow_pressure_memory_z_w60_q70|1346|365.5482|0.4565|2|3|-159.7751|diagnostic_positive_unstable|
|flow_pressure_memory_z_w30_q80|1347|354.2114|0.4329|2|3|-151.1395|diagnostic_positive_unstable|
|flow_pressure_memory_z_w30_q70|1359|348.7248|0.4355|2|3|-149.8700|diagnostic_positive_unstable|
|pressure_without_price_response_z_w30_q80|1336|343.0875|0.4144|2|3|-152.1917|diagnostic_positive_unstable|
|pressure_without_price_response_z_w30_q70|1355|335.3161|0.4159|2|3|-152.9571|diagnostic_positive_unstable|
|flow_pressure_memory_r_w30_q80|1341|335.2519|0.4075|2|3|-140.7452|diagnostic_positive_unstable|
|flow_pressure_memory_r_w60_q70|1364|334.8476|0.4287|2|3|-90.4129|diagnostic_positive_unstable|
|pressure_without_price_response_r_w30_q80|1340|330.4755|0.4011|2|3|-140.2233|diagnostic_positive_unstable|

## Best cells

|variant_id|cell|actual_entries|net_weighted_bps|mean_unit_net_bps|hit_rate|
|---|---|---|---|---|---|
|cost_allowed_release_memory_z_w60_q80|01_frames_only|64|360.2356|3.9103|0.5156|
|cost_allowed_release_memory_r_w30_q70|01_frames_only|63|352.4682|4.0925|0.5079|
|cost_allowed_release_memory_r_w30_q80|01_frames_only|63|352.4682|4.0925|0.5079|
|cost_allowed_release_memory_z_w30_q70|01_frames_only|65|346.4716|3.8875|0.4923|
|cost_allowed_release_memory_z_w30_q80|01_frames_only|65|346.4716|3.8875|0.4923|
|absolute_pressure_energy_e_w30_q70|01_frames_only|67|345.1585|3.6866|0.4925|
|absolute_pressure_energy_e_w30_q80|01_frames_only|67|345.1585|3.6866|0.4925|
|flow_pressure_memory_z_w60_q80|01_frames_only|62|336.1856|3.7510|0.5000|
|pressure_without_price_response_z_w60_q80|01_frames_only|63|335.8587|3.7266|0.4921|
|flow_pressure_memory_r_w30_q80|01_frames_only|65|332.6980|3.6915|0.4769|
|pressure_without_price_response_r_w30_q80|01_frames_only|65|332.6980|3.6915|0.4769|
|absolute_pressure_energy_e_w60_q70|01_frames_only|66|330.4328|3.6261|0.4848|
|absolute_pressure_energy_e_w60_q80|01_frames_only|66|330.4328|3.6261|0.4848|
|flow_pressure_memory_r_w60_q70|00_none|825|330.0720|0.6448|0.4291|
|flow_pressure_memory_z_w60_q70|01_frames_only|59|328.0762|3.7229|0.4915|
|pressure_without_price_response_z_w60_q70|01_frames_only|59|328.0762|3.7229|0.4915|
|cost_allowed_release_memory_r_w60_q70|01_frames_only|56|324.1059|3.9108|0.5000|
|flow_pressure_memory_z_w30_q80|01_frames_only|65|319.2527|3.5423|0.4769|
|pressure_without_price_response_z_w30_q80|01_frames_only|65|319.2527|3.5423|0.4769|
|cost_allowed_release_memory_r_w60_q80|01_frames_only|58|318.8360|3.7676|0.4828|

## Best memory cells

These rows isolate the cells where the new primitive threshold is active. They are closer to the R5 imitation question than `01_frames_only`.

|variant_id|cell|actual_entries|net_weighted_bps|mean_unit_net_bps|hit_rate|
|---|---|---|---|---|---|
|liquidity_giveway_memory_r_w30_q70|10_r5_only|418|294.5766|1.7826|0.4737|
|liquidity_giveway_memory_r_w60_q80|11_r5_frames|42|209.3307|4.6133|0.5952|
|liquidity_giveway_memory_r_w30_q70|11_r5_frames|46|209.1795|3.7437|0.5435|
|liquidity_giveway_memory_r_w60_q70|11_r5_frames|45|206.9372|4.2449|0.5556|
|liquidity_giveway_memory_r_w30_q80|11_r5_frames|43|206.6979|3.9654|0.5581|
|flow_pressure_memory_r_w60_q70|11_r5_frames|50|197.1480|3.3918|0.5200|
|pressure_without_price_response_r_w60_q70|11_r5_frames|50|197.1480|3.3918|0.5200|
|pressure_without_price_response_r_w30_q70|11_r5_frames|44|195.2558|3.7731|0.5682|
|flow_pressure_memory_r_w30_q70|11_r5_frames|42|194.3169|3.8670|0.5714|
|flow_pressure_memory_r_w60_q80|11_r5_frames|17|142.2080|9.4805|0.8235|
|pressure_without_price_response_r_w60_q80|11_r5_frames|17|142.2080|9.4805|0.8235|
|liquidity_giveway_memory_z_w60_q70|11_r5_frames|29|131.1587|4.3180|0.5172|
|liquidity_giveway_memory_r_w30_q80|10_r5_only|254|128.3878|1.2526|0.4213|
|liquidity_giveway_memory_z_w30_q80|10_r5_only|309|112.4407|0.9399|0.4369|
|liquidity_giveway_memory_z_w30_q70|10_r5_only|429|84.2787|0.5127|0.4499|
|liquidity_giveway_memory_r_w60_q80|10_r5_only|289|78.3337|0.7010|0.4429|
|liquidity_giveway_memory_z_w60_q80|11_r5_frames|16|78.2795|5.2186|0.5625|
|flow_pressure_memory_z_w30_q70|11_r5_frames|13|55.9778|5.8924|0.5385|
|pressure_without_price_response_z_w30_q70|11_r5_frames|13|55.9778|5.8924|0.5385|
|liquidity_giveway_memory_z_w60_q80|10_r5_only|294|53.9686|0.4771|0.4354|

## Comparison vs old q70/R5 baseline

|variant_id|actual_entries|net_weighted_bps|baseline_net_weighted_bps|delta_net_weighted_bps|beats_baseline_net|status|
|---|---|---|---|---|---|---|
|absolute_pressure_energy_e_w60_q70|1337|424.1275|545.2394|-121.1119|False|diagnostic_positive_unstable|
|absolute_pressure_energy_e_w30_q70|1326|400.3907|545.2394|-144.8487|False|diagnostic_positive_unstable|
|absolute_pressure_energy_e_w30_q80|1316|394.3658|545.2394|-150.8736|False|diagnostic_positive_unstable|
|pressure_without_price_response_z_w60_q80|1329|393.5404|545.2394|-151.6990|False|diagnostic_positive_unstable|
|flow_pressure_memory_z_w60_q80|1329|376.4844|545.2394|-168.7550|False|diagnostic_positive_unstable|
|absolute_pressure_energy_e_w60_q80|1324|374.3226|545.2394|-170.9168|False|diagnostic_positive_unstable|
|pressure_without_price_response_z_w60_q70|1346|368.8504|545.2394|-176.3891|False|diagnostic_positive_unstable|
|flow_pressure_memory_z_w60_q70|1346|365.5482|545.2394|-179.6913|False|diagnostic_positive_unstable|
|flow_pressure_memory_z_w30_q80|1347|354.2114|545.2394|-191.0280|False|diagnostic_positive_unstable|
|flow_pressure_memory_z_w30_q70|1359|348.7248|545.2394|-196.5146|False|diagnostic_positive_unstable|
|pressure_without_price_response_z_w30_q80|1336|343.0875|545.2394|-202.1519|False|diagnostic_positive_unstable|
|pressure_without_price_response_z_w30_q70|1355|335.3161|545.2394|-209.9233|False|diagnostic_positive_unstable|
|flow_pressure_memory_r_w30_q80|1341|335.2519|545.2394|-209.9875|False|diagnostic_positive_unstable|
|flow_pressure_memory_r_w60_q70|1364|334.8476|545.2394|-210.3918|False|diagnostic_positive_unstable|
|pressure_without_price_response_r_w30_q80|1340|330.4755|545.2394|-214.7639|False|diagnostic_positive_unstable|

## Interpretation guardrails

- A positive row is not strategy promotion. It means the low-degree primitive deserves a second pass.
- A `spread_cost_mirage` row means the mid path looked useful but top-of-book taker economics rejected it.
- Thresholds are prior-day candidate-distribution quantiles; they are not fitted on same-day labels.
- Runner, Bot, Monitor, scored entries, and legacy `date/` files are not inputs.

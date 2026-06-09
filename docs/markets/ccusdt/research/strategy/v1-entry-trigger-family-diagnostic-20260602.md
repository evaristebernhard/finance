# CCUSDT Entry Trigger Family Diagnostic

Status: `ccusdt_entry_trigger_family_diagnostic_v0_1`.

Boundary: research-only; inputs are decision_frame_v1 and quote_frame_v1; future labels are diagnostic only.

## Setup

- dates: `2026-05-05..2026-05-30`
- trigger variants: `8`
- event rows: `3825458`
- baseline: `fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521`

## Interpretation

`I1_pure_book_giveway` tests whether book-side giveway can be an independent
entry mechanism: side is chosen from bid/ask giveway scores, not from TFI. The
26-day result rejects that hypothesis. All eight variants have positive
`mean_mid60_bps` but negative `mean_exec60_bps`, and every variant has
`positive_days = 0/26` under both unit and capacity evidence.

Financially, pure giveway detects small mid-price release, but the release is
too weak and too noisy to pay the taker spread. The old-baseline overlap rows
are small and sometimes positive, while the `new_only` rows are large and
negative. Therefore the good cases are mostly cases where book giveway happens
to coincide with the old active-flow/stale-release structure; book giveway by
itself should be treated as confirmation, admission, or sizing context rather
than as a standalone directional entry.

## Top Unit Evidence

|variant_id|family_id|n|mean_exec60_bps|mean_mid60_bps|hit_rate_exec60|positive_days|days|status|
|---|---|---|---|---|---|---|---|---|
|I1_pure_book_giveway_l_w30_q80_marginq70|I1_pure_book_giveway|413342|-1.2701|0.4334|0.2457|0|26|spread_cost_mirage|
|I1_pure_book_giveway_l_w30_q70_marginq70|I1_pure_book_giveway|500964|-1.2799|0.4240|0.2451|0|26|spread_cost_mirage|
|I1_pure_book_giveway_l_w60_q80_marginq70|I1_pure_book_giveway|432545|-1.3051|0.3403|0.2342|0|26|spread_cost_mirage|
|I1_pure_book_giveway_l_w60_q70_marginq70|I1_pure_book_giveway|514287|-1.3131|0.3399|0.2358|0|26|spread_cost_mirage|
|I1_pure_book_giveway_z_w60_q70_marginq70|I1_pure_book_giveway|539775|-1.4279|0.3638|0.2816|0|26|spread_cost_mirage|
|I1_pure_book_giveway_z_w60_q80_marginq70|I1_pure_book_giveway|426067|-1.4798|0.3061|0.2766|0|26|spread_cost_mirage|
|I1_pure_book_giveway_z_w30_q80_marginq70|I1_pure_book_giveway|440448|-1.5277|0.2886|0.2890|0|26|spread_cost_mirage|
|I1_pure_book_giveway_z_w30_q70_marginq70|I1_pure_book_giveway|558030|-1.5350|0.2884|0.2932|0|26|spread_cost_mirage|

## Top Capacity Evidence

|variant_id|family_id|actual_entries|net_weighted_bps|mean_unit_net_bps|positive_days|days|
|---|---|---|---|---|---|---|
|I1_pure_book_giveway_l_w60_q80_marginq70|I1_pure_book_giveway|95606|-51807.4167|-1.4450|0|26|
|I1_pure_book_giveway_l_w60_q70_marginq70|I1_pure_book_giveway|107851|-59473.3957|-1.4705|0|26|
|I1_pure_book_giveway_l_w30_q80_marginq70|I1_pure_book_giveway|112573|-63131.2926|-1.4955|0|26|
|I1_pure_book_giveway_z_w60_q80_marginq70|I1_pure_book_giveway|111986|-64772.4853|-1.5424|0|26|
|I1_pure_book_giveway_l_w30_q70_marginq70|I1_pure_book_giveway|127293|-71999.7489|-1.5083|0|26|
|I1_pure_book_giveway_z_w60_q70_marginq70|I1_pure_book_giveway|130011|-77150.7481|-1.5824|0|26|
|I1_pure_book_giveway_z_w30_q80_marginq70|I1_pure_book_giveway|127099|-81594.5338|-1.7119|0|26|
|I1_pure_book_giveway_z_w30_q70_marginq70|I1_pure_book_giveway|142783|-93430.6938|-1.7449|0|26|

## Top Cells

|variant_id|family_id|cell|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|I1_pure_book_giveway_l_w30_q80_marginq70|I1_pure_book_giveway|11_r5_frames|266412|-1.0260|0.2333|
|I1_pure_book_giveway_l_w30_q70_marginq70|I1_pure_book_giveway|11_r5_frames|325362|-1.0478|0.2296|
|I1_pure_book_giveway_l_w60_q80_marginq70|I1_pure_book_giveway|11_r5_frames|278757|-1.1358|0.2196|
|I1_pure_book_giveway_l_w60_q70_marginq70|I1_pure_book_giveway|11_r5_frames|331170|-1.1645|0.2190|
|I1_pure_book_giveway_z_w30_q70_marginq70|I1_pure_book_giveway|11_r5_frames|111951|-1.1784|0.2717|
|I1_pure_book_giveway_z_w30_q80_marginq70|I1_pure_book_giveway|11_r5_frames|80458|-1.2123|0.2708|
|I1_pure_book_giveway_z_w60_q70_marginq70|I1_pure_book_giveway|11_r5_frames|201971|-1.3112|0.2544|
|I1_pure_book_giveway_z_w60_q80_marginq70|I1_pure_book_giveway|11_r5_frames|154636|-1.3580|0.2520|
|I1_pure_book_giveway_z_w60_q70_marginq70|I1_pure_book_giveway|10_r5_only|337804|-1.4977|0.2979|
|I1_pure_book_giveway_z_w60_q80_marginq70|I1_pure_book_giveway|10_r5_only|271431|-1.5491|0.2907|
|I1_pure_book_giveway_l_w60_q70_marginq70|I1_pure_book_giveway|10_r5_only|183117|-1.5819|0.2663|
|I1_pure_book_giveway_z_w30_q80_marginq70|I1_pure_book_giveway|10_r5_only|359990|-1.5982|0.2931|
|I1_pure_book_giveway_l_w60_q80_marginq70|I1_pure_book_giveway|10_r5_only|153788|-1.6120|0.2606|
|I1_pure_book_giveway_z_w30_q70_marginq70|I1_pure_book_giveway|10_r5_only|446079|-1.6244|0.2986|
|I1_pure_book_giveway_l_w30_q70_marginq70|I1_pure_book_giveway|10_r5_only|175602|-1.7099|0.2738|

## New-only Candidates vs Old Baseline

|variant_id|family_id|bucket|n|mean_exec60_bps|hit_rate_exec60|
|---|---|---|---|---|---|
|I1_pure_book_giveway_l_w30_q80_marginq70|I1_pure_book_giveway|new_only|413315|-1.2703|0.2457|
|I1_pure_book_giveway_l_w30_q70_marginq70|I1_pure_book_giveway|new_only|500928|-1.2801|0.2451|
|I1_pure_book_giveway_l_w60_q80_marginq70|I1_pure_book_giveway|new_only|432511|-1.3055|0.2341|
|I1_pure_book_giveway_l_w60_q70_marginq70|I1_pure_book_giveway|new_only|514244|-1.3134|0.2358|
|I1_pure_book_giveway_z_w60_q70_marginq70|I1_pure_book_giveway|new_only|539717|-1.4281|0.2816|
|I1_pure_book_giveway_z_w60_q80_marginq70|I1_pure_book_giveway|new_only|426021|-1.4799|0.2766|
|I1_pure_book_giveway_z_w30_q80_marginq70|I1_pure_book_giveway|new_only|440407|-1.5278|0.2890|
|I1_pure_book_giveway_z_w30_q70_marginq70|I1_pure_book_giveway|new_only|557980|-1.5352|0.2932|

## Guardrails

- Unit evidence evaluates trigger quality before capacity.
- Capacity evidence is a diagnostic approximation, not Bot promotion.
- Dynamic giveway is compared against static low-depth control.
- Runner, Bot, Monitor, legacy `date/`, scored entries, PnL, MFE, and MAE are not runtime inputs.

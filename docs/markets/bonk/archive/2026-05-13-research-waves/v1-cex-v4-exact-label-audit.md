# BONK CEX V4 Exact Label Audit

Status: 2026-05-13T12:56:02Z. Standalone timestamp-exact label audit for BONK1MUSDC/BONK1MUSDT. This is a research prototype, not a trading rule or execution plan.

## Inputs And Outputs

Input panel:

```text
data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date\bonk_v4_exact_label_audit_summary.csv
date\bonk_v4_exact_label_audit_mismatches.csv
date\bonk_v4_exact_label_audit_active_h4_gates.csv
date\bonk_v4_exact_label_audit_completion.json
```

## Method

- Scope: `BONK1MUSDC/BONK1MUSDT`, horizons `H1/H4/H12`, barriers `50/100 bps`.
- Old labels are the panel's existing `label_status`, `barrier_first_hit`, `future_return_bps`, `mfe_up_bps`, and `mae_down_bps`.
- Exact labels are rebuilt from the panel's unique `symbol,timestamp_us,price_per_token` series and require the exact `timestamp_us + horizon` endpoint to exist.
- Barrier path statistics use observed rows between the current timestamp and exact endpoint. Rows without the exact endpoint are marked `future_missing`.
- H4 gate impact reuses the V3 hand-built gate features and fold cutoffs, then compares old and exact labels under a direction-only active read.

## Executive Read

- Overall strict label mismatch rate: `0.2%` (`496` of `241380` rows).
- Overall old-ok rows: `237106`; exact-ok rows: `236684`; both-ok rows: `236684`.
- Future-return mismatch among both-ok rows: `2.2%`; median absolute return diff `0.000` bps.
- Active H4 direction reads changed for `0` of `10` symbol/gate combinations at `100 bps`.
- Mismatch rows written: `5615`.

## Label Mismatch Summary

| symbol | H | bps | rows | old ok | exact ok | strict mismatch | hit mismatch both-ok | return mismatch both-ok | p95 return diff | p95 drift min |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | 1 | 50 | 20103 | 20012 | 19924 | 0.5% | 0.0% | 0.3% | 0.000 | 0.000 |
| BONK1MUSDC | 1 | 100 | 20103 | 20012 | 19924 | 0.4% | 0.0% | 0.3% | 0.000 | 0.000 |
| BONK1MUSDC | 4 | 50 | 20103 | 19833 | 19798 | 0.2% | 0.0% | 1.9% | 0.000 | 0.000 |
| BONK1MUSDC | 4 | 100 | 20103 | 19833 | 19798 | 0.4% | 0.2% | 1.9% | 0.000 | 0.000 |
| BONK1MUSDC | 12 | 50 | 20103 | 19353 | 19324 | 0.1% | 0.0% | 4.4% | 0.000 | 0.000 |
| BONK1MUSDC | 12 | 100 | 20103 | 19353 | 19324 | 0.1% | 0.0% | 4.4% | 0.000 | 0.000 |
| BONK1MUSDT | 1 | 50 | 20127 | 20065 | 20030 | 0.2% | 0.1% | 0.4% | 0.000 | 0.000 |
| BONK1MUSDT | 1 | 100 | 20127 | 20065 | 20030 | 0.2% | 0.0% | 0.4% | 0.000 | 0.000 |
| BONK1MUSDT | 4 | 50 | 20127 | 19885 | 19873 | 0.1% | 0.0% | 1.9% | 0.000 | 0.000 |
| BONK1MUSDT | 4 | 100 | 20127 | 19885 | 19873 | 0.1% | 0.1% | 1.9% | 0.000 | 0.000 |
| BONK1MUSDT | 12 | 50 | 20127 | 19405 | 19393 | 0.1% | 0.0% | 4.4% | 0.000 | 0.000 |
| BONK1MUSDT | 12 | 100 | 20127 | 19405 | 19393 | 0.1% | 0.0% | 4.4% | 0.000 | 0.000 |


## Active H4 Gate Impact

The table below focuses on the previously active BONK1MUSDT H4 gates. `old/exact read` is direction-only, so it is not identical to the earlier V3 residual-state active read.

| gate | old read | exact read | old dir pass | exact dir pass | delta pass | old edge | exact edge | changed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| depth_high | direction_supported_candidate | direction_supported_candidate | 59.7% | 59.5% | -0.2% | 0.133 | 0.133 | False |
| depth_high+rv_low | direction_supported_candidate | direction_supported_candidate | 58.2% | 58.2% | 0.0% | 0.133 | 0.133 | False |
| depth_high+rv_low+cv_spread | direction_supported_candidate | direction_supported_candidate | 63.0% | 63.0% | 0.0% | 0.151 | 0.151 | False |
| rv_low | direction_supported_candidate | direction_supported_candidate | 55.6% | 55.6% | 0.0% | 0.044 | 0.044 | False |


## Changed H4 Direction Reads

n/a


## Recommendation

The timestamp-exact rebuild does not materially change this slice. It is reasonable to keep using the old labels for exploratory ranking, but canonical research should still migrate to timestamp-exact labels before execution work.

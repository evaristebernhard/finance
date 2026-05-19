# BONK CEX V5 Label Canonicalization

Status: 2026-05-13. Plan/prototype contract for moving timestamp-exact H1/H4/H12 labels and 5m/15m/30m 20/30 bps labels into the canonical BONK CEX pipeline.

This is a pipeline contract, not a trading rule, execution plan, sizing rule, or alpha claim.

## Current State

Rust currently owns the canonical BONK CEX build:

```text
crates/cex_l2_research/src/report.rs
  raw Bullish files -> bonk_cex_l2_state
  bonk_cex_l2_state -> bonk_path_labels

crates/cex_l2_research/src/research.rs
  bonk_cex_l2_state + bonk_path_labels + covariance + price_context
  -> bonk_l2_label_context_panel
```

The current Rust path-label builder in `report.rs` is hour-only and row-offset based:

```text
horizons_hours = 1,4,12
barriers_bps = 50,100,200,300
future row = idx + horizon_minutes
status ok if that row is at least horizon_us away
```

That last condition is the weak point. It rejects too-short horizons but can still accept a future row after the exact endpoint if one or more minute rows are missing. The V4 audit showed the damage was small on the tested slice, but canonical execution research should not depend on that accident.

Python V4 has two relevant prototypes:

```text
scripts/bonk_v4_exact_label_audit.py
```

Rebuilds H1/H4/H12 labels from `symbol,timestamp_us,price_per_token`, requires `timestamp_us + horizon` endpoint, and records old row-offset drift/mismatch.

```text
scripts/bonk_v4_short_horizon_orderbook.py
```

Builds 5m/15m/30m labels at 20/30 bps from the L2 state and requires the exact future endpoint to exist.

One caution: `scripts/bonk_v4_orderbook_family_ablation.py` also derives short labels for a local ablation path, but its short helper still uses an offset-style `target_idx = idx + horizon` with a `>= horizon` check. V5 should retire that local label builder and consume canonical labels instead.

## Canonical Output

Add a single long-format label dataset:

```text
data/bonk/v1/derived/bonk_canonical_path_labels/
  bonk_canonical_path_labels_<run_tag>.parquet
```

Optionally replace the existing panel input with:

```text
data/bonk/v1/derived/bonk_canonical_l2_label_context_panel/
  bonk_canonical_l2_label_context_panel_<run_tag>.parquet
```

The old datasets can remain for reproducibility:

```text
derived/bonk_path_labels
derived/bonk_l2_label_context_panel
```

but V5 reports should read only the canonical labels/panel.

## Label Schema

Required canonical label columns:

| column | type | rule |
| --- | --- | --- |
| `run_tag` | string | Source L2 run tag. |
| `label_version` | string | `bonk_v5_timestamp_exact_v1`. |
| `label_family` | string | `long_horizon` or `short_horizon`. |
| `label_source` | string | `rust_canonical`. |
| `endpoint_policy` | string | `timestamp_exact`. |
| `timestamp_utc` | string | UTC minute bucket for the source row. |
| `timestamp_us` | u64 | Minute bucket timestamp. |
| `symbol` | string | `BONK1MUSDC` or `BONK1MUSDT`. |
| `asset` | string | `BONK`. |
| `quote` | string | `USDC` or `USDT`. |
| `horizon_minutes` | u64 | `5,15,30,60,240,720`. |
| `horizon_hours` | f64 nullable | `1,4,12` for long labels; optional fractional value for short labels. |
| `barrier_bps` | u64 | Long: `50,100,200,300`; short: `20,30`. |
| `price_per_token` | f64 nullable | Current minute close used as label anchor. |
| `future_timestamp_us` | u64 | Always `timestamp_us + horizon_minutes * 60_000_000`. |
| `future_timestamp_utc` | string | UTC rendering of `future_timestamp_us`. |
| `future_price_per_token` | f64 nullable | Exact endpoint close. |
| `future_return_bps` | f64 nullable | `ln(future_price / price_per_token) * 10000`. |
| `mfe_up_bps` | f64 nullable | Max path return over `(t, endpoint]`. |
| `mae_down_bps` | f64 nullable | Min path return over `(t, endpoint]`. |
| `path_width_bps` | f64 nullable | `mfe_up_bps - mae_down_bps`. |
| `barrier_first_hit` | string | `upper_first`, `lower_first`, `both_or_ambiguous`, `none`, or `future_missing`. |
| `label_status` | string | `ok`, `future_missing`, or `bad_anchor`. |
| `path_observed_points` | u64 | Number of finite path minute closes in `(t, endpoint]`. |
| `path_missing_points` | u64 | `horizon_minutes - path_observed_points`. |
| `future_ctx_market_return_bps` | f64 nullable | Exact endpoint context return. |
| `future_ctx_meme_return_bps` | f64 nullable | Exact endpoint context return. |
| `future_ctx_sol_return_bps` | f64 nullable | Exact endpoint context return. |
| `future_ctx_bonk_binance_return_bps` | f64 nullable | Exact endpoint Binance BONK return. |
| `future_ctx_common_return_bps` | f64 nullable | Mean of market/meme/SOL context. |
| `future_resid_mkt_meme_sol_bps` | f64 nullable | `future_return_bps - future_ctx_common_return_bps`. |
| `residual_positive_flag` | f64 nullable | `1.0` if residual is positive, `0.0` if nonpositive. |

Derived target columns may be materialized in the panel, not necessarily the raw label parquet:

```text
target_upper_first
target_lower_first
target_not_lower_first
target_residual_positive
target_path_direction_score
day_utc
minute_index
phase
```

## Endpoint Rules

`timestamp_us` is the minute bucket of the state row. `price_per_token` is that row's close. A model may use same-row L2 features only under a bar-close decision convention: the signal is considered available after that minute has closed. A live bar-open convention must lag features by at least one minute.

For every label row:

```text
future_timestamp_us = timestamp_us + horizon_minutes * 60_000_000
```

`label_status=ok` requires:

```text
price_per_token is finite and > 0
future_price_per_token exists exactly at future_timestamp_us
future_price_per_token is finite and > 0
at least one finite path point exists in (timestamp_us, future_timestamp_us]
```

Missing interior minutes do not silently move the endpoint. They are recorded in `path_missing_points`. Downstream strategy reports should either filter to `path_missing_points=0` for strict first-passage work or disclose the completeness threshold they use.

The path interval is open on the anchor and closed on the endpoint:

```text
(t, t + horizon]
```

Barrier ties use the existing semantics:

```text
upper_first
lower_first
both_or_ambiguous
none
future_missing
```

## Leakage Rules

The label builder must not use future rows for any feature or train threshold. It may only use future rows for label columns named with `future_`, path columns, status columns, and targets derived from those columns.

The canonical panel builder should enforce:

```text
feature_timestamp_us <= timestamp_us
train threshold fit rows <= fold.train_end_us
validation rows between fold.val_start_us and fold.val_end_us
no train/validation filter may read label outcomes before selecting rows
```

Context fields split into two families:

```text
ctx_*      trailing/current context, feature side only
future_*  label side only
```

Any Python report that trains models must build feature lists from an allow-list that excludes:

```text
future_*
target_*
label_status
barrier_first_hit
mfe_up_bps
mae_down_bps
path_width_bps
residual_positive_flag
```

unless the script is explicitly evaluating labels, not features.

## Rust/Python Division

Rust should own canonical data products:

```text
bonk_cex_l2_report:
  raw Bullish CSV.gz -> L2 state/covariance
  L2 state -> timestamp-exact canonical labels

bonk_cex_research_panel:
  canonical labels + L2 state + covariance + price_context
  -> canonical label/context panel
```

The Rust label builder should be generalized from `horizon_hours` to `horizon_minutes` and should build a `timestamp_us -> row index` lookup per symbol. It should never use `idx + horizon_minutes` as the authority for endpoint validity.

Python should own exploratory reports only:

```text
V5 report scripts:
  read canonical labels/panel
  run diagnostics, ablations, gates, and model comparisons
  write date/ CSV summaries and docs
```

Python should not rebuild labels in V5 reports except in audit/check scripts. The exact-label audit can stay as a regression test against Rust output.

## Migration Steps

1. Add `LabelSpec { family, horizon_minutes, barrier_bps }` in Rust and expose CLI defaults:

```text
long: 60/240/720 minutes with 50/100/200/300 bps
short: 5/15/30 minutes with 20/30 bps
```

2. Replace `build_path_labels` with a timestamp-indexed canonical builder:

```text
target_ts = timestamp_us + horizon_minutes * MINUTE_US
target_idx = by_timestamp.get(target_ts)
```

3. Write `bonk_canonical_path_labels_<run_tag>.parquet` with the schema above. Keep the old path-label writer only behind an explicit compatibility path.

4. Extend future context calculation from hour-only windows to generic minute horizons:

```text
5,15,30,60,240,720
```

and require exact context endpoints for `future_ctx_*`.

5. Update the panel builder so all Python V5 scripts read canonical labels. The old `horizon_hours` field can stay as a compatibility column, but the join key should be:

```text
symbol, timestamp_us, horizon_minutes, barrier_bps, label_version
```

6. Add a contract check to CI/local validation:

```bash
python scripts/bonk_v5_label_contract_check.py \
  --labels data/bonk/v1/derived/bonk_canonical_path_labels/bonk_canonical_path_labels_<run_tag>.parquet
```

7. Retire Python-local label builders in V5 reports. Keep `bonk_v4_exact_label_audit.py` as an audit reference, and use it only to compare old artifacts or spot-check Rust canonical output.


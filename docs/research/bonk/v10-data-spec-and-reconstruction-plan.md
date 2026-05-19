# BONK V10 Data Spec And Reconstruction Plan

Status: 2026-05-14. This is the V10 stage-1 intake plan for a high-fidelity BONK Bullish order-book reconstruction line. It is research infrastructure only: no trading advice, no execution recommendation, no sizing rule, and no alpha claim.

Canonical pilot run:

```text
run_tag: 20260514_bonk_v10_stage1_pilot
window: 2026-05-06 .. 2026-05-12
symbols: BONK1MUSDC, BONK1MUSDT
artifacts:
  date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_manifest.json
  date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_checkpoint.json
  date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_completion.json
  date/bonk_v10_raw_inventory_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_download_metadata_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_worker_shards_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_potential_state_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_filter_params_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_filter_state_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_anchor_candidates_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_long_short_episode_backtest_20260514_bonk_v10_stage1_pilot_summary.csv
  date/bonk_v10_negative_controls_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_spearman_stability_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_horizon_decay_20260514_bonk_v10_stage1_pilot.csv
  date/bonk_v10_failure_report_20260514_bonk_v10_stage1_pilot.csv
```

## Objective

V10 shifts the BONK line away from static gate iteration and toward executable-path reconstruction. The immediate goal is not another shallow factor pass. The immediate goal is to make the data path faithful enough that the following objects can later be estimated without hand-waving:

```text
queue and depth pressure
cancellation / withdrawal energy
replenish relaxation
spread resistance
microprice and WOBI evolution
trade-flow alignment in event time
potential-function state
movable-anchor long/short episodes
after-cost queue/fill-aware replay
```

The V10 runner added in Rust for this stage is:

```text
cargo run -p cex_l2_research --bin bonk_v10_reconstruction_and_path -- --run-tag 20260514_bonk_v10_stage1_pilot
```

It is resumable at the manifest/checkpoint level and currently covers:

```text
local raw inventory
missing-download planning
parallel worker shard assignment
replay_book_state_files runner
incremental replay preview
replay-derived potential state
train-only threshold fitting with purged validation folds
movable-anchor long/short episode diagnostics
after-cost maker_light / taker_spread / wide_stress path summaries
negative controls
Spearman and horizon-decay diagnostics
failure reporting
completion accounting
```

Those downstream phases are now materialized for completed replay state files. Full-pilot coverage is still pending because only `4/14` pilot incremental shards currently have durable replay `state_parts`; the older `BONK1MUSDC 2026-05-09` state file predates the newer top-25 JSON/depth-geometry schema, while the newer `BONK1MUSDC 2026-05-07`, `2026-05-11`, and `2026-05-12` replay files include it. The runner is canonical, but the current artifacts remain partial-window diagnostics.

## Minimum Required Dataset

The minimum V10 pilot dataset is deliberately narrow: two BONK symbols over a 7-day window, but with enough depth fidelity to stop inferring queue mechanics from coarse aggregates.

| data_type | required now | local pilot status | role in V10 |
| --- | --- | --- | --- |
| `book_snapshot_25` | yes | present `14/14` | shape, slope, curvature, barrier proxies, depth imbalance, spread resistance, microprice scaffolding |
| `book_ticker` | yes | present `14/14` | quote alignment, top-of-book timing, microprice evolution, trade-side inference support |
| `trades` | yes | present `14/14` | trade-flow timing, aggressor proxy construction, path event alignment |
| `incremental_book_L2` | yes, blocking for canonical replay logic, no longer missing in pilot raw | present `14/14`, missing `0/14` | queue-level replay, cancellation/replenish dynamics, local-book evolution, precise potential and fill realism |

Current pilot coverage from `date/bonk_v10_raw_inventory_20260514_bonk_v10_stage1_pilot.csv`:

```text
target shards: 56
present: 56
missing: 0
empty: 0
invalid: 0
incremental_book_L2 present: 14
incremental_book_L2 missing: 0
```

The baseline raw is already substantial:

```text
present compressed raw bytes: 4,332,477,220
fingerprint: 9c498fb863f77432
```

That means the V10 problem is not "no BONK data". The actual blocker is narrower and more useful:

```text
we already have top-25 snapshots, top-of-book ticker, and trades;
we now have the full 14/14 incremental replay shards for the pilot;
the remaining gap is no longer raw coverage, but canonical full-window replay/output logic.
```

Current partial incremental coverage:

```text
BONK1MUSDC: 2026-05-06 .. 2026-05-12 present
BONK1MUSDT: 2026-05-06 .. 2026-05-12 present
remaining missing pilot shards: 0
```

## Exchange And Source Assumptions

Primary exchange/source for V10:

```text
exchange: Bullish
distribution source: Tardis dataset files
layout: data/bonk/v1/external/bullish_<data_type>/symbol=<SYMBOL>/dt=<YYYY-MM-DD>/<SYMBOL>.csv.gz
```

Working assumptions for the current pilot:

1. `book_snapshot_25` is a valid shape state, but not a substitute for queue replay.
2. `book_ticker` is sufficient for quote-rule side inference support and top-of-book event alignment.
3. `trades.side` should still be treated as exchange-reported side until explicitly revalidated against quote timing in the high-fidelity replay.
4. `timestamp` and `local_timestamp` should both be preserved; later reconstruction must prefer a stable event-time convention and audit quote/trade ordering sensitivity.
5. `incremental_book_L2` schema must be verified on the first downloaded pilot shard before any canonical replay assumptions are frozen.
6. Crossed books are expected as a replay edge case and should be cleaned when the exchange fails to publish delete updates consistently.

Observed baseline schema checks in the pilot:

```text
book_snapshot_25: 104 columns, ask_levels=25, bid_levels=25, schema_ok on 14/14 pilot shards
book_ticker: 8 columns, schema_ok on 14/14 pilot shards
trades: 8 columns, schema_ok on 14/14 pilot shards
incremental_book_L2: header verified on live pilot shards; replay still requires crossed-level cleanup and better long-run checkpoint granularity for full-window summaries
```

## Worker Topology

Stage-1 worker topology is intentionally simple and restart-friendly.

```text
worker pool size: 4
shard key: (date, symbol, data_type)
queue file: date/bonk_v10_worker_shards_20260514_bonk_v10_stage1_pilot.csv
```

Current active download queue in the pilot:

| worker | missing shards | estimated compressed MB |
| --- | --- | --- |
| `1` | `0` | `0.0` |
| `2` | `0` | `0.0` |
| `3` | `0` | `0.0` |
| `4` | `0` | `0.0` |

This is based on the documented rule-of-thumb size for Bullish `incremental_book_L2`:

```text
about 277 MB/day/symbol compressed
```

For the 7-day, 2-symbol pilot window, the blocking incremental pull is therefore about:

```text
0 shards * 277 MB ~= 0 MB compressed
```

So the worker download queue for the pilot is now drained.

## Shard Range

Pilot window:

```text
2026-05-06
2026-05-07
2026-05-08
2026-05-09
2026-05-10
2026-05-11
2026-05-12
```

Symbols:

```text
BONK1MUSDC
BONK1MUSDT
```

Planned data types:

```text
book_snapshot_25
book_ticker
trades
incremental_book_L2
```

This creates `56` target shards. The pilot raw window is now complete.

## Retry, Resume, And Checkpoint Rules

V10 stage-1 writes:

```text
manifest:   date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_manifest.json
checkpoint: date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_checkpoint.json
completion: date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_completion.json
```

Current checkpoint steps are:

```text
inventory_local_raw
download_missing
plan_download_metadata
plan_worker_shards
replay_book_state_files
replay_incremental_preview
replay_incremental_full_summary
potential_state
train_purged_filter_state
movable_anchor_path_backtest
negative_controls
spearman_horizon_decay
failure_report
write_completion
```

Resume rules:

1. Reuse completed CSV outputs when the checkpoint step is complete and `--force` is not set.
2. Recompute a step if its output file is missing or if `--no-resume` / `--force` is used.
3. If `--download-missing` is supplied, the runner delegates the download phase to the existing `run_bullish_l2_download(...)` Rust path, then rescans local raw and refreshes inventory/worker planning.
4. Never treat a completed download manifest as proof of usable replay data without a follow-up inventory rescan and schema validation.

## Integrity Checks

Stage-1 integrity checks are intentionally strict for the baseline raw:

1. gzip file opens and samples successfully;
2. header row parses as CSV;
3. sample rows exist;
4. required columns exist for the given data type;
5. `book_snapshot_25` must expose at least `25` ask levels and `25` bid levels;
6. rows that are missing, empty, or schema-invalid are marked actionable in the download plan.

This is enough for intake. It is not enough for canonical replay. Later phases must add:

```text
monotonic local-book evolution checks
cross-check of trade timestamps against quote updates
book replay conservation checks
price-level jump sanity
duplicate / out-of-order event audits
queue depletion / replenish consistency checks
```

The first live replay preview already surfaced one practical rule:

```text
crossed-level cleanup is necessary;
without it, preview spreads turned negative;
with it, median preview spread returned to about 1.39 .. 1.54 bps on the live pilot shards examined so far.
```

The next engineering lesson is runtime shape rather than market semantics:

```text
full-window replay over one large incremental shard can run for tens of millions of raw rows;
therefore file-internal checkpoint progress is mandatory, not optional.
```

The follow-up engineering step now also has direct artifact evidence:

```text
replay_book_state_files can create chunked state_parts before a raw shard finishes;
smoke evidence wrote state_parts/part_000001.csv for BONK1MUSDC 2026-05-06 while still mid-file.
```

## Storage Layout

Raw:

```text
data/bonk/v1/external/bullish_book_snapshot_25/...
data/bonk/v1/external/bullish_book_ticker/...
data/bonk/v1/external/bullish_trades/...
data/bonk/v1/external/bullish_incremental_book_L2/...
```

Generated V10 stage-1 artifacts:

```text
date/bonk_v10_raw_inventory_<run_tag>.csv
date/bonk_v10_download_metadata_<run_tag>.csv
date/bonk_v10_worker_shards_<run_tag>.csv
date/bonk_v10_reconstruction_and_path_<run_tag>_manifest.json
date/bonk_v10_reconstruction_and_path_<run_tag>_checkpoint.json
date/bonk_v10_reconstruction_and_path_<run_tag>_completion.json
date/bonk_v10_incremental_replay_preview_<run_tag>.csv
date/bonk_v10_potential_state_<run_tag>.csv
date/bonk_v10_filter_params_<run_tag>.csv
date/bonk_v10_filter_state_<run_tag>.csv
date/bonk_v10_anchor_candidates_<run_tag>.csv
date/bonk_v10_long_short_episode_backtest_<run_tag>_trades.csv
date/bonk_v10_long_short_episode_backtest_<run_tag>_summary.csv
date/bonk_v10_negative_controls_<run_tag>.csv
date/bonk_v10_spearman_stability_<run_tag>.csv
date/bonk_v10_horizon_decay_<run_tag>.csv
date/bonk_v10_failure_report_<run_tag>.csv
```

The current Rust runner now writes separately versioned outputs for completed replay files:

```text
replayed local book state
potential state
filter state
anchor state
episode trades/summary
negative controls
spearman/stability/decay diagnostics
failure diagnostics
```

## Modeling Stance

V10 is not a tree-model-only project.

The next canonical state is intended to combine:

```text
order-book geometry
potential-function state
queue-reactive memory
Kalman-style latent pressure smoothing
Yau-Yau-inspired nonlinear filtering where justified
movable anchors for long and short episode starts
queue/fill realism before any cost-aware path claim
```

That means the research object changes from "find another static gate" to:

```text
reconstruct the executable path faithfully enough that gates, anchors, and controls stop hallucinating liquidity.
```

## Why This Upgrade Matters

The pilot result already points to the main V9 limitation.

`book_snapshot_25 + book_ticker + trades` is enough to estimate:

```text
shape proxies
depth imbalance
spread states
microprice proxies
activity and trade intensity
```

But it is not enough to estimate with confidence:

```text
queue depletion sequence
cancellation / withdrawal energy in event time
replenish relaxation after a pressure burst
movable-anchor trigger quality under queue drift
fill realism under maker_light / taker_spread / wide_stress stress
```

This is the concrete reason V10 prioritizes `incremental_book_L2` before another factor iteration.

The live partial replay already adds a more precise conclusion:

```text
the replay core can produce sane positive spreads on true incremental BONK data once crossed levels are removed,
but the next bottleneck is now canonical full-window replay/output engineering rather than raw pilot coverage.
```

## Immediate Next Step

The pilot raw queue is drained. The next engineering action is to continue durable replay state generation, one or a few large files at a time:

```text
cargo run -p cex_l2_research --bin bonk_v10_reconstruction_and_path -- ^
  --run-tag 20260514_bonk_v10_stage1_pilot ^
  --max-replay-files 1
```

Then:

1. keep the pilot raw window fixed and canonical;
2. repeat the replay continuation until `replay_book_state_files` reaches `14/14`;
3. refresh potential, filter, anchor, path, control, Spearman, and failure artifacts after each completed replay file;
4. expand beyond the 7-day pilot only after the failure report no longer flags partial replay coverage.

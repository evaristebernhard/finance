# BONK V10 Reconstruction And Path Report

Status: 2026-05-15 downstream recovery. The canonical V10 stage-1 pilot now has `14/14` replay state files completed and refreshed downstream potential, filter, movable-anchor, after-cost path, control, Spearman, horizon-decay, failure, and dynamic-quality diagnostics. These artifacts are research diagnostics only: no trading advice, no execution recommendation, and no alpha claim.

```text
what do we already have locally,
which replay shards have durable state parts,
and what path-quality diagnostics are now available for the fixed 14/14 pilot?
```

Canonical pilot:

```text
run_tag: 20260514_bonk_v10_stage1_pilot
window: 2026-05-06 .. 2026-05-12
symbols: BONK1MUSDC, BONK1MUSDT
```

## Headline Result

The V10 pilot did not fail because BONK lacks volatility or because there is no raw data.

It now finds:

```text
target shards: 56
present baseline/incremental shards: 56
missing shards: 0
empty shards: 0
invalid shards: 0
incremental_book_L2 present: 14
incremental_book_L2 missing: 0
```

So the recovered state is specific:

```text
we already have top-25 snapshots, top-of-book ticker, and trades for the full pilot;
we now have the complete queue-level raw layer for the pilot;
canonical replay state output now covers all 14 incremental files;
the remaining operational caveat is external Windows file locking from unrelated git add -A processes over stale temp files.
```

That is a much better failure mode than "everything is missing", because it tells us where the fidelity gap actually lives.

## Artifact Set

- `date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_manifest.json`
- `date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_checkpoint.json`
- `date/bonk_v10_reconstruction_and_path_20260514_bonk_v10_stage1_pilot_completion.json`
- `date/bonk_v10_raw_inventory_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_download_metadata_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_worker_shards_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_incremental_replay_preview_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_replay_state_manifest_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_incremental_replay_full_summary_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_potential_state_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_filter_params_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_filter_state_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_anchor_candidates_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_long_short_episode_backtest_20260514_bonk_v10_stage1_pilot_trades.csv`
- `date/bonk_v10_long_short_episode_backtest_20260514_bonk_v10_stage1_pilot_summary.csv`
- `date/bonk_v10_negative_controls_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_spearman_stability_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_horizon_decay_20260514_bonk_v10_stage1_pilot.csv`
- `date/bonk_v10_failure_report_20260514_bonk_v10_stage1_pilot.csv`

## Coverage Table

| data_type | BONK1MUSDC | BONK1MUSDT | pilot status |
| --- | --- | --- | --- |
| `book_snapshot_25` | `7/7` present | `7/7` present | ready locally |
| `book_ticker` | `7/7` present | `7/7` present | ready locally |
| `trades` | `7/7` present | `7/7` present | ready locally |
| `incremental_book_L2` | `7/7` present | `7/7` present | raw-complete for the pilot |

Grouped inventory result after draining the pilot raw queue:

```text
book_snapshot_25, present: 14
book_ticker, present: 14
trades, present: 14
incremental_book_L2, present: 14
incremental_book_L2, missing: 0
```

## Baseline Raw Already On Disk

Compressed baseline raw currently available in the pilot:

| symbol + data_type | total MB |
| --- | ---: |
| `BONK1MUSDC book_snapshot_25` | `138.76` |
| `BONK1MUSDC book_ticker` | `10.30` |
| `BONK1MUSDC trades` | `4.54` |
| `BONK1MUSDT book_snapshot_25` | `169.82` |
| `BONK1MUSDT book_ticker` | `13.51` |
| `BONK1MUSDT trades` | `0.61` |

Total present compressed raw:

```text
4,332,491,834 bytes
about 4.33 GB
```

This matters because it means V10 does not need to restart from zero. The local baseline is already strong enough to support:

```text
top-25 shape, slope, curvature proxies
spread and barrier states
microprice and WOBI scaffolding
trade / quote timing alignment work
```

## Schema Sanity

The pilot inventory validates the baseline raw schemas.

For all `14` `book_snapshot_25` shards:

```text
required_schema_ok = true
ask_levels = 25
bid_levels = 25
header_columns = 104
```

The sampled header preview is exactly the kind of structure we want for the baseline shape layer:

```text
exchange|symbol|timestamp|local_timestamp|asks[0].price|asks[0].amount|bids[0].price|bids[0].amount|...
```

For `book_ticker` and `trades`, all pilot shards passed the required-column check as well.

## Incremental Replay Preview

V10 now writes a live replay preview on the locally present incremental shards:

```text
date/bonk_v10_incremental_replay_preview_20260514_bonk_v10_stage1_pilot.csv
```

The preview is intentionally capped at the first `250,000` raw rows per present file while replay semantics are being calibrated.

| date | symbol | raw rows read | replay rows | median spread bps | crossed batches | crossed levels removed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `2026-05-06` | `BONK1MUSDC` | `250000` | `680` | `1.5393` | `117` | `161` |
| `2026-05-06` | `BONK1MUSDT` | `250000` | `680` | `1.5383` | `51` | `65` |
| `2026-05-07` | `BONK1MUSDC` | `250000` | `680` | `1.4700` | `265` | `306` |
| `2026-05-07` | `BONK1MUSDT` | `250000` | `680` | `1.4698` | `200` | `227` |
| `2026-05-08` | `BONK1MUSDC` | `250000` | `680` | `1.4681` | `104` | `129` |
| `2026-05-08` | `BONK1MUSDT` | `250000` | `681` | `1.4711` | `83` | `101` |
| `2026-05-09` | `BONK1MUSDC` | `250000` | `680` | `1.3880` | `288` | `443` |
| `2026-05-09` | `BONK1MUSDT` | `250000` | `680` | `1.3886` | `120` | `218` |

This was a useful failure-and-fix loop in its own right:

1. the first replay preview produced impossible negative spreads;
2. that exposed the need for crossed-level cleanup in the local-book replay;
3. after adding crossed-level removal, replay spreads returned to a sane positive range.

At this point the raw pilot is complete, and the full-window state output is complete for the fixed stage-1 pilot. The prior partial-output state was recovered without redownloading raw data or expanding the window.

The canonical stage-1 pilot now has all `14` replay state files completed:

```text
replay_state_manifest: completed 14/14
replay_full_summary_rows: 14
dynamic_quality_coverage_rows: 14
multilevel_schema_ok: 14/14
failure blockers: none
```

So the pipeline has crossed an important line: it can emit durable intermediate state output mid-shard and then derive downstream path diagnostics from those state parts.

## Replay-Derived Path Diagnostics

The V10 runner now consumes completed replay `state_parts` and writes the next research layers in Rust:

```text
potential_rows: 1,945,574
filter_rows: 1,077,579
anchor_candidates: 36
path_trades: 1,050,048
path_summary_rows: 864
negative_control_rows: 576
spearman_rows: 72
horizon_decay_rows: 72
failure_rows: 1
```

These rows are diagnostics only. They are built with train-only thresholds and purged validation folds, then replayed through `maker_light`, `taker_spread`, and `wide_stress` cost models. The current failure report has no coverage or schema blocker; it only preserves the research guardrail:

```text
research_guardrail: no trading advice, no execution recommendation, no alpha claim
```

Dynamic quality refresh:

```text
date/bonk_v10_dynamic_quality_book_hourly_20260514_bonk_v10_stage1_pilot.csv rows=336
date/bonk_v10_dynamic_quality_book_daily_20260514_bonk_v10_stage1_pilot.csv rows=14
date/bonk_v10_dynamic_quality_potential_hourly_20260514_bonk_v10_stage1_pilot.csv rows=336
date/bonk_v10_dynamic_quality_filter_hourly_20260514_bonk_v10_stage1_pilot.csv rows=166
date/bonk_v10_dynamic_quality_coverage_20260514_bonk_v10_stage1_pilot.csv rows=14
date/bonk_v10_dynamic_quality_artifact_status_20260514_bonk_v10_stage1_pilot.csv rows=10
```

## Worker Download Queue

The missing queue-level pull has already been turned into a 4-worker plan:

| worker | missing shards | estimated compressed MB |
| --- | ---: | ---: |
| `1` | `0` | `0.0` |
| `2` | `0` | `0.0` |
| `3` | `0` | `0.0` |
| `4` | `0` | `0.0` |

The pilot raw queue is now fully drained:

```text
remaining missing pilot shards: 0
```

## What This Says About The Earlier Failure

The right read is not "BONK has no motion".

A more honest read is:

1. BONK clearly has movement.
2. V8/V9 already saw that movement, but mostly through coarse top-of-book / snapshot-derived states.
3. Those states can still flicker into too many entries because they do not fully observe queue depletion, cancellation timing, replenish relaxation, or executable fill drift.
4. Under cost stress, that missing queue detail shows up as turnover and slippage pain.

So the problem is less "insufficient volatility" and more:

```text
insufficient executable-path fidelity relative to the turnover of the candidate states.
```

That is exactly why V10 prioritizes incremental replay before another round of threshold polishing.

## What V10 Is And Is Not

V10 is not a retreat back to tree models.

The intended later phases are:

```text
canonical local-book replay
potential-function state
Kalman and Yau-Yau-style filtered latent pressure variants
movable-anchor long and short episode generation
queue/fill-aware after-cost replay
negative controls
Spearman / stability / horizon-decay diagnostics
failure diagnostics
```

This stage now outputs full fixed-pilot potential/anchor/path diagnostics for the `2026-05-06 .. 2026-05-12` window. It is still a research-only reconstruction report, not a trading rule or alpha claim.

## Immediate Next Action

The raw queue and fixed-pilot replay are complete. The writer has been hardened in `crates/cex_l2_research/src/v10.rs` so Windows runs use unique temp files outside the repo plus bounded rename retries and backup/restore replacement for existing outputs.

The recovery command now completes:

```text
cargo run -p cex_l2_research --bin bonk_v10_reconstruction_and_path -- ^
  --run-tag 20260514_bonk_v10_stage1_pilot ^
  --max-replay-files 1
```

Observed post-recovery caveat:

```text
two stale date/bonk_v10_potential_state_*stage1_pilot*.tmp files remain locked by unrelated git.exe add -A processes;
the recovered writer no longer depends on those date/*.tmp paths.
```

The next gate is to keep the pilot raw window fixed and review the recovered diagnostics. Do not extend the window or rerun heavy replay unless a later audit finds a concrete artifact mismatch.

## Bottom Line

The V10 pilot already produced a useful conclusion:

```text
the BONK line is no longer blocked by pilot raw coverage;
the fixed V10 pilot is no longer blocked by partial replay coverage;
the remaining caveat is operational cleanup of stale temp files after external git add -A locks are released.
```

That is concrete, falsifiable, and worth acting on.

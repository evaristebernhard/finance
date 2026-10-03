# CCUSDT Replay Diagnostics

These scripts are run-after or same-stream diagnostics for the replay exchange
kernel. They are intentionally outside the trading hot path.

```text
audit_event_log.py      validates compact order/fill causal chains and repeat hashes
conditional_wait_exit_opportunity.py builds wait-only ExitControllerV1 opportunity panels
conditional_wait_exit_policy.py tests prior-date wait_tau_then_cross gates over the wait panel
decision_frame_parity.py rebuilds decision_frame_v1 from canonical L2/trades and compares fixed-panel fields
decision_frame_cache.py  builds/validates typed Parquet decision_frame_v1 hot-path cache
exit_wait_value_decomposition.py decomposes wait-exit value into mid continuation and crossing improvement
event_regime_discovery.py discovers structurally new event/regime strategy families from decision_frame cache
fast_strategy_backtest.py runs the fast research backtest from decision_frame cache
fast_vs_strict_consistency.py compares fast entries against strict/direct audit entries and sim-live fills
feature_state_check.py  compares Python online feature state to a same-stream reference
hardening_suite.py      runs pressure, determinism, log-audit, and feature checks
maker_first_exit_policy.py runs prior-date maker-first exit gates over the opportunity panel
maker_exit_wait_vs_maker_decomposition.py decomposes maker-first exit value into wait/fallback versus passive fill
maker_exit_opportunity.py estimates maker-first exit fill hazard, fallback decay, and selection
microstructure_factor_diagnostic.py builds the factor-atlas diagnostic table for TFI, spread/depth, OFI/MLOFI panel factors, release/decay labels, and executable taker labels
microstructure_tree_diagnostic.py runs research-only OOS tree probes over runtime-safe microstructure features
structure_family_fast_research.py compares first-principles structure families from decision_frame cache with mid and top-of-book executable labels
panel_oracle_shadow_audit.py reproduces the old four-cell policy on the fixed-panel decision clock
repeat_run_hash_gate.py compares two deterministic run logs by decision/execution/portfolio hashes
shadow_four_cell_audit.py audits the old TFI four-cell policy as a runtime-safe Bot shadow policy
shadow_state.py         builds Bot-owned shadow R5/lifecycle state from decision_frame cache
taker_exit_gap_decomposition.py decomposes exit G(u)=Y(u)-Y(60) into avoided decay and crossing cost
taker_exit_stopping_diagnostic.py builds runtime-safe taker-exit path panels and labels
```

Boundary rule:

```text
diagnostics may read canonical market truth and runner run directories
diagnostics must not become strategy runtime inputs
```

`event_regime_discovery.py` is the current broad strategy-family discovery
diagnostic. It groups local triggers into first-principles mechanism classes,
computes both mid and executable top-of-book taker labels, and writes:

```text
event_family_summary.csv  every family/horizon row with promotion_status
mechanism_summary.csv     mechanism-level best rows and spread-cost failures
candidate_families.csv    positive-mean executable weak/promote candidates only
rejected_controls.csv     high-scoring controls that fail executable economics
events.parquet            optional per-event labels and observed state
```

Known broad pass:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/event_regime_discovery.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-30 --write-events
```

Known output:

```text
systems/ccusdt_replay_exchange/runs/event_regime_discovery/ccusdt_2026-05-16_2026-05-30_v0_1
event_count=243668
family_summary_rows=54
mechanism_summary_rows=24
candidate_count=3
```

The result is intentionally conservative: the three retained rows are only
weak positive-mean executable candidates, while most intuitive event families
are rejected as spread-cost mirages.

`microstructure_factor_diagnostic.py` is the next factor-analysis table builder
from the microstructure atlas:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/microstructure_factor_diagnostic.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18 --source both
```

It writes:

```text
factor_diagnostics.csv
summary.json
docs/markets/ccusdt/research/factors/v1-microstructure-factor-diagnostic-20260601.md
```

The table separates `mid_terminal_60s`, `release_mfe_10s`,
`decay_60s_after_mfe`, and `top_of_book_executable_60s`. Unsigned spread/depth
rows are marked as `control_only_no_direction`; they are not promoted as alpha.
For `2026-05-19..2026-05-30`, use `--source decision_frame` only unless
trade/L2/fixed-event sources are rebuilt, and keep those rows quote-only.

`microstructure_tree_diagnostic.py` is a small non-linear follow-up for rows
where rank IC is already material. It trains separate long/short shallow tree
regressors by OOS day and reports whether interactions improve release, mid,
and executable labels:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/microstructure_tree_diagnostic.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18 --source fixed_event
```

It writes:

```text
tree_oos_metrics.csv
tree_feature_importance.csv
summary.json
docs/markets/ccusdt/research/factors/v1-microstructure-tree-diagnostic-20260601.md
```

The tree output is still diagnostic only. It may use future path labels as
training labels, but those labels must not enter Runner/Bot runtime.

`structure_family_fast_research.py` is the first structure-family pass after
the four-cell policy was reclassified as `S1 active-flow stale-release` rather
than the whole strategy. It reads `decision_frame_v1` and canonical
`quote_frame_v1`, uses L1 queue/microprice proxies where full OFI/MLOFI are not
available, computes release/decay and top-of-book taker executable labels, and
writes structure-level evidence:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/structure_family_fast_research.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18
```

It writes:

```text
structure_family_summary.csv
structure_variant_summary.csv
structure_event_examples.parquet
summary.json
docs/markets/ccusdt/research/strategy/v1-structure-family-fast-research-20260601.md
```

Known first pass:

```text
output: systems/ccusdt_replay_exchange/runs/structure_family_fast_research/ccusdt_2026-05-16_2026-05-18_decision_frame_v0_1
event_rows: 44,426
variants: 18
families: S1/S2/S3/S4/S5/S6/S7, with S5 marked second-stage
best clean entry-alpha: S1_tfi_follow_flat_stale31, mean executable60 about 4.55bps
main warning: many positive mid/release rows become spread-cost mirages after taker crossing
```

Repeat-run identity is intentionally layered:

```text
decision_hash         timestamp/cell/side/weight/capacity path
execution_hash        arrival quote/fill price/qty/lot lifecycle
portfolio_hash        account mark, position state, order/fill counts
summary_account_hash  final account/PnL bitwise identity
```

In `deterministic_replay_v1`, wall/bridge timing may change
`arrival_stream_lag_count`, but `arrival_quote_lag_count`,
`private_seq_mismatch_count`, and all four hashes must remain stable across
same-profile repeats. In `wall_latency_pressure_v1`, virtual staleness is part
of the profile and PnL/hash drift is expected pressure output.

For cross-transport checks, use transport-equivalence mode:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/repeat_run_hash_gate.py --run-dir-a systems/ccusdt_replay_exchange/runs/<strict_event_run> --run-dir-b systems/ccusdt_replay_exchange/runs/<batched_public_run> --compare-mode transport_equivalence
```

This compares transport-normalized decision/execution/portfolio hashes and the
final account hash. It allows profile/event-count/arrival-stream-lag differences
caused by batching, but still rejects decision, fill, portfolio, and account
drift. It intentionally ignores opaque `feature_snapshot` diagnostics because
private fill feedback can arrive later inside a batch while the emitted
capacity/order/fill decisions remain identical.

Typical local run:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/hardening_suite.py --repo-root . --date 2026-05-18
```

For a completed strategy run, `feature_state_check.py` can also verify compact
run-log checkpoints:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py --repo-root . --date 2026-05-18 --run-dir systems/ccusdt_replay_exchange/runs/<run_id>
```

Checkpoint parity aligns by virtual `feature_snapshot.local_ts_us`, not only by
event sequence, so timer-mode fills between market events are checked against
the last exchange-visible state before the virtual arrival time.

Before trying to translate the old four-cell policy into the live Bot, run the
panel-oracle check:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/panel_oracle_shadow_audit.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18
```

This must stay diagnostic-only. It proves the old fixed-panel clock can match
the research reference exactly; it does not authorize runtime reads of legacy
panel or `date/` files.

Then verify the runtime-safe panel builder and materialize the hot-path cache:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_parity.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py build --repo-root . --from-date 2026-05-16 --to-date 2026-05-18
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py validate --repo-root . --from-date 2026-05-16 --to-date 2026-05-18
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py parity --repo-root . --parity-left raw --parity-right cache --from-date 2026-05-16 --to-date 2026-05-18
python systems/ccusdt_replay_exchange/diagnostics/shadow_four_cell_audit.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18 --mode direct --decision-clock panel --warmup-reference-r5
```

The Parquet cache lives under:

```text
data/canonical_parquet/cex/bullish/CCUSDT/decision_frame_v1/dt=YYYY-MM-DD/
```

It is market-derived and typed. Its manifest records schema version, builder
version, source file hashes, row count, cache file hash, and field hash. Default
validation is shallow and reads Parquet metadata plus manifest fields. Use
`--deep-cache-hash`, `--deep-field-hash`, or `--deep-source-hash` for slower
audit gates.

Known direct canonical pass: `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_155504`
with `764 / 764` entries, `0` feature mismatches, and exact `261 / 199 / 304`
daily entry counts. This is a slow mathematical parity gate because it rebuilds
decision frames from canonical L2.

Known fast Parquet-cache pass: `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_182258`
with `764 / 764` entries, `0` feature mismatches, exact `261 / 199 / 304`
daily entry counts, and about six seconds wall time for the three-day audit.

Bot-owned state persistence is separate from data cache persistence:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/shadow_state.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-16
python systems/ccusdt_replay_exchange/diagnostics/shadow_four_cell_audit.py --repo-root . --warmup-from-date 2026-05-17 --from-date 2026-05-17 --to-date 2026-05-18 --mode direct --decision-clock panel --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-16.json
```

For mixed-horizon or selector experiments, continue the Bot-owned state rather
than rebuilding each day independently:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/shadow_state.py --repo-root . --from-date 2026-05-17 --to-date 2026-05-17 --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/prior_horizon_selector_v1_state_after_dt=2026-05-16.json --fixed-exit-us 30000000
```

Known state resume pass: `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_182539`.
It proves `closed_bps` and pending shadow lifecycle must be replayed
continuously across day boundaries; reloading the same state independently for
each day will create R5 cell mismatches.

For the real Runner+Bot stdin/stdout path, use compact L2. This is slower than
direct parity because it pushes exchange-style public events through the actual
Bot bridge:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/shadow_four_cell_audit.py --repo-root . --from-date 2026-05-18 --to-date 2026-05-18 --mode runner --decision-clock panel --clock-mode accelerated-async --compact-l2 --warmup-reference-r5 --max-events 500000
```

Known strict pass:

```text
run: systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_154315
date: 2026-05-18
entries: 304 / 304
exact timestamp matches: 304 / 304
feature mismatches: 0
cell mismatch: 0
```

`--warmup-reference-r5` is diagnostic-only. It seeds the last five closed R5
outcomes from the legacy reference to mimic a bot that had already run from the
warmup period. Runtime code must replace this with replayed or persisted
closed-outcome state.

The current no-reference fast gate is:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py build --repo-root . --input-layer raw --from-date 2026-05-04 --to-date 2026-05-15
python systems/ccusdt_replay_exchange/diagnostics/shadow_state.py --repo-root . --from-date 2026-05-04 --to-date 2026-05-15
python systems/ccusdt_replay_exchange/diagnostics/shadow_four_cell_audit.py --repo-root . --warmup-from-date 2026-05-16 --from-date 2026-05-16 --to-date 2026-05-18 --mode direct --decision-clock panel --decision-frame-source cache --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-15.json
```

Known pass: `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_233233`
with `764 / 764`, exact `261 / 199 / 304`, `0` feature mismatches, and
`warmup_reference_r5=false`.

Fast baseline backtest:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_strategy_backtest.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18 --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-15.json --leverage-cap 3 --fee-bps 0 --pressure-bps 0 --slippage-bps 0
```

Known C=0 run: `systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520`
with `1157.7814` weighted bps over three days. Known `pressure_bps=2` run:
`systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520_pressure2`
with `348.2814` weighted bps.

For a real entry-fill sim-live gate, run sparse Python with shadow entry trading
enabled:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --repo-root . --symbol CCUSDT --canonical-date 2026-05-18 --run-id sim_live_shadow_entries_20260518_20260520 --max-events 500000 --latency-us 0 --clock-mode deterministic-step --log-mode compact --include-l2 --compact-l2 --l2-batch-size 1000 --strategy-arg=--window-us --strategy-arg=2000000 --strategy-arg=--decision-clock --strategy-arg=panel --strategy-arg=--decision-trade-window-us --strategy-arg=2000000 --strategy-arg=--max-orders --strategy-arg=0 --strategy-arg=--heartbeat-interval-us --strategy-arg=999999999999 --strategy-arg=--shadow-four-cell --strategy-arg=--shadow-frames-threshold --strategy-arg=31 --strategy-arg=--shadow-overlay-threshold --strategy-arg=59.80000000000018 --strategy-arg=--shadow-fixed-exit-us --strategy-arg=60000000 --strategy-arg=--shadow-gamma-preset --strategy-arg=core_q70 --strategy-arg=--shadow-state-in --strategy-arg=systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-17.json --strategy-arg=--shadow-trade-entries --strategy-arg=--shadow-entry-notional --strategy-arg=1.0
```

Known run: `systems/ccusdt_replay_exchange/runs/sim_live_shadow_entries_20260518_20260520`
with `294 / 294 / 294` intents/orders/fills and `bridge_errors=0`.

Then verify event chains and entry-fill decomposition:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py --run-dir systems/ccusdt_replay_exchange/runs/sim_live_shadow_entries_20260518_20260520
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520 --strict-audit-dir systems/ccusdt_replay_exchange/runs/sim_live_shadow_entries_20260518_20260520 --date 2026-05-18 --out-dir systems/ccusdt_replay_exchange/runs/fast_vs_sim_live_20260518_20260520
```

Known consistency result: `294 / 294`, field mismatches `0`, fills matched
`294`, weighted fast-to-sim entry-fill delta `-44.4252bps`. This isolates entry
taker cost while retaining the fast fixed60 mid exit.

For a full taker round-trip sim-live gate, add shadow exit trading:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --repo-root . --symbol CCUSDT --canonical-date 2026-05-18 --run-id sim_live_shadow_roundtrip_20260518_20260520 --max-events 500000 --latency-us 0 --clock-mode deterministic-step --log-mode compact --include-l2 --compact-l2 --l2-batch-size 1000 --strategy-arg=--window-us --strategy-arg=2000000 --strategy-arg=--decision-clock --strategy-arg=panel --strategy-arg=--decision-trade-window-us --strategy-arg=2000000 --strategy-arg=--max-orders --strategy-arg=0 --strategy-arg=--heartbeat-interval-us --strategy-arg=999999999999 --strategy-arg=--shadow-four-cell --strategy-arg=--shadow-frames-threshold --strategy-arg=31 --strategy-arg=--shadow-overlay-threshold --strategy-arg=59.80000000000018 --strategy-arg=--shadow-fixed-exit-us --strategy-arg=60000000 --strategy-arg=--shadow-gamma-preset --strategy-arg=core_q70 --strategy-arg=--shadow-state-in --strategy-arg=systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-17.json --strategy-arg=--shadow-trade-entries --strategy-arg=--shadow-trade-exits --strategy-arg=--shadow-entry-notional --strategy-arg=1.0
```

Known run: `systems/ccusdt_replay_exchange/runs/sim_live_shadow_roundtrip_20260518_20260520`
with `586 / 586 / 586` intents/orders/fills and `bridge_errors=0`.

Then verify event chains and full fill decomposition:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py --run-dir systems/ccusdt_replay_exchange/runs/sim_live_shadow_roundtrip_20260518_20260520
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520 --strict-audit-dir systems/ccusdt_replay_exchange/runs/sim_live_shadow_roundtrip_20260518_20260520 --date 2026-05-18 --strict-source events --out-dir systems/ccusdt_replay_exchange/runs/fast_vs_sim_live_roundtrip_20260518_20260520
```

Known round-trip consistency result: entry intents `294 / 294`, field
mismatches `0`, round trips matched `292`, missing exit intents `2`, weighted
fast shadow raw `406.0404`, weighted sim shadow net `194.6315`, weighted delta
`-211.4088`, mean total taker execution cost `1.2355bps`.

Latest profile-aware 2026-05-18 deterministic strict decomposition:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/fast_profile_core_idle01_g1_fixed60_mid_20260518_20260521 --strict-audit-dir systems/ccusdt_replay_exchange/runs/det_full_20260521_a --date 2026-05-18 --out-dir systems/ccusdt_replay_exchange/runs/fast_vs_strict_det_full_20260521_decomp --compare-mode execution_decomposition
```

Known result:

```text
rows compared: 304 / 304
field mismatches: 0
round trips matched: 303
fast capacity raw: 471.3458 bp-units
strict taker capacity net: 214.6061 bp-units
capacity delta: -256.7397 bp-units
capacity entry spread cost: 63.1741 bp-units
capacity exit spread cost: 193.5656 bp-units
capacity latency/depth/pressure/residual: 0.0000 bp-units
```

`fast_vs_strict_consistency.py` reports both requested-shadow weights and
actual-capacity weights. Use the `weighted_capacity_*` fields when explaining
real traded PnL after clipping; use `weighted_*` shadow fields only when
debugging requested exposure before clipping.

Known batched transport pass:

```text
run: systems/ccusdt_replay_exchange/runs/det_batch_full_span5s_20260521
mode: batched_public_v1, batch_size=512, batch_max_span_us=5,000,000
events: 258,186
public batches: 16,674
orders/fills: 606 / 606
arrival_quote_lag_count: 0
final account hash: identical to det_full_20260521_a
transport_equivalence: ok
fast-vs-batch entries: 304 / 304, mismatches 0
```

Known failed sensitivity: `det_batch_full_20260521_a` with
`batch_max_span_us=30,000,000` produced only `599` fills and a residual
position. Treat this as evidence that private-feedback delay is a real
constraint, not as an acceptable fast mode.

Known causal-barrier transport pass:

```text
run: systems/ccusdt_replay_exchange/runs/det_barrier_full_span60s_20260521
mode: batched_public_barrier_v1, batch_size=512, batch_max_span_us=60,000,000
events: 258,186
public batches: 2,026
barriers: 600
orders/fills: 606 / 606
arrival_quote_lag_count: 0
final account hash: identical to det_full_20260521_a
transport_equivalence: ok
```

The 30s barrier run also passes (`det_barrier_full_span30s_20260521`) with
606 / 606 orders/fills. The suffix requeue counters are expected: they count
market events that were intentionally replayed after private fill/account
feedback, not duplicated market truth.

Known panel-sparse strict-audit transport pass:

```text
run: systems/ccusdt_replay_exchange/runs/det_panel_sparse_full_span60s_20260521
mode: panel_sparse_v1, batch_size=512, batch_max_span_us=60,000,000
events: 258,186
panel frames: 131,608
public batches: 2,007
barriers: 600
capacity decisions: 304
orders/fills: 606 / 606
arrival_quote_lag_count: 0
transport_equivalence: ok versus det_full_20260521_a and det_barrier_full_span60s_20260521
events_per_sec: about 553
```

`panel_sparse_v1` reads the validated `decision_frame_v1` Parquet cache for bot
public input, but Runner still reads canonical quote/trade/L2 truth for virtual
clock, arrival quote, fill, portfolio, and logs. The transport-equivalence
diagnostic normalizes floats to 8 decimals only in transport mode to avoid false
failures from online-vs-Parquet float text round-trips; repeat mode remains
strict.

Known panel-sparse fast-clock strict-audit pass:

```text
run: systems/ccusdt_replay_exchange/runs/det_panel_sparse_fast_clock_full_20260521_seqfix
mode: panel_sparse_fast_clock_v1, batch_size=512, batch_max_span_us=60,000,000
panel frames: 131,608
public batches: 2,007
barriers: 600
capacity decisions: 304
orders/fills: 606 / 606
arrival_quote_lag_count: 0
arrival_stream_lag_count: 1
market_read_ms: 11
total_elapsed_wall_ms: 35,270
events_per_sec: about 3,731
transport_equivalence: ok versus det_panel_sparse_full_span60s_20260521 and det_barrier_full_span60s_20260521
```

`panel_sparse_fast_clock_v1` is intentionally narrower than `panel_sparse_v1`:
it is valid for `top_of_book_taker_ioc_v1` deterministic audit because arrival
and fill need only the quote index. Keep full-stream or `panel_sparse_v1` gates
for L2 depth, maker/queue work, and online feature-reconstruction validation.

## Profile Matrix Report

`profile_matrix_report.py` aggregates fast-vs-strict execution decomposition
over the four current top-of-book strategy profiles:

```text
core_only
idle01_g0.5
idle01_g0.75
idle01_g1
```

It calls `fast_vs_strict_consistency.py` for each profile/day pair, enforces the
profile/data gates, writes `summary.json`, `daily_profile_summary.csv`, and
`profile_totals.csv`, and prints only a compact console summary. Full nested
diagnostics stay in `summary.json`.

Latest three-day matrix:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/profile_matrix_report.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18 --out-dir systems/ccusdt_replay_exchange/runs/profile_matrix_top_of_book_20260516_18_20260521
```

Known result:

```text
output: systems/ccusdt_replay_exchange/runs/profile_matrix_top_of_book_20260516_18_20260521
overall ok: true
rows compared: 764 per profile
entry alignment: 261 / 199 / 304 per day
row mismatches: 0
arrival_quote_lag_count: 0 for every profile/day
latency_slippage / pressure / extra_slippage: 0
```

Totals:

```text
profile        orders/fills  fast_mid   strict_taker  total_cost  entry_cost  exit_cost
core_only      1484/1484     1159.5840  638.2147      521.3693    63.5981    457.7713
idle01_g0.5    1526/1526     1213.9435  649.4415      564.5020    84.3450    480.1569
idle01_g0.75   1526/1526     1241.1232  655.0549      586.0683    94.7185    491.3498
idle01_g1      1526/1526     1263.9560  656.7311      607.2249    105.1749   502.0500
```

Use this matrix as the current strict top-of-book baseline. The economics are
now profile-aware: the idle01 sleeve raises fast mid edge, but top-of-book
taker execution gives most of that increment back through spread crossing,
especially at fixed60 exit.

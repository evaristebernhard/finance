# Runbook

Read the next-stage design before changing runner/bot/monitor architecture:

```text
systems/ccusdt_replay_exchange/docs/next-stage-three-process-design.md
```

Scan catalog:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- catalog scan --repo-root . --symbol CCUSDT
```

Build 2026-05-18 canonical datasets:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical build --dataset quote_frame_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical build --dataset trade_event_v1 --from 2026-05-18 --to 2026-05-18
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical build --dataset l2_level_update_v1 --from 2026-05-18 --to 2026-05-18
```

Validate canonical:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- canonical validate --from 2026-05-18 --to 2026-05-18
```

Serve from canonical quotes:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- serve --canonical-date 2026-05-18 --addr 127.0.0.1:8797
```

Run the deterministic toy runner:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run toy --canonical-date 2026-05-18 --max-frames 200 --latency-frames 1 --qty 10 --hold-frames 20
```

Run the sparse exchange-style Python stream runner:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500 --latency-us 50000
```

Run a short L2 batch with the L2 depth fill model:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 550 --latency-us 0 --include-l2 --l2-max-rows 1000 --l2-batch-size 200 --fill-model l2-depth
```

Run accelerated async pressure mode:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500 --latency-us 50000 --clock-mode accelerated-async --wall-latency-speedup 25
```

Run the independent Runner Server:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run server --canonical-date 2026-05-18 --max-events 900 --latency-us 50000 --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --order-addr 127.0.0.1:8803 --state-addr 127.0.0.1:8804 --startup-wait-ms 1500 --event-sleep-us 2000
```

Run the independent Python bot in another terminal:

```powershell
python systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/tcp_bot.py --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --order-addr 127.0.0.1:8803
```

Run the read-only monitor in a third terminal:

```powershell
npm --prefix systems/ccusdt_replay_exchange/monitor run monitor -- --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --state-url http://127.0.0.1:8804/api/state
```

For post-run compact-log audit, include the run directory:

```powershell
npm --prefix systems/ccusdt_replay_exchange/monitor run monitor -- --public-addr 127.0.0.1:8801 --private-addr 127.0.0.1:8802 --state-url http://127.0.0.1:8804/api/state --run-dir systems/ccusdt_replay_exchange/runs/<run_id>
```

Offline compact-log audit:

```powershell
npm --prefix systems/ccusdt_replay_exchange/monitor run monitor -- --offline-run-dir systems/ccusdt_replay_exchange/runs/<run_id>
```

Run the kernel hardening suite:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/hardening_suite.py --repo-root . --date 2026-05-18
```

Useful individual diagnostics:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py --run-dir systems/ccusdt_replay_exchange/runs/<run_id>
python systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py --repo-root . --date 2026-05-18
python systems/ccusdt_replay_exchange/diagnostics/feature_state_check.py --repo-root . --date 2026-05-18 --include-l2 --l2-max-rows 5000
```

Latest acceptance report:

```text
systems/ccusdt_replay_exchange/docs/hardening-report-20260520.md
```

Run outputs:

```text
systems/ccusdt_replay_exchange/runs/<run_id>/manifest.json
systems/ccusdt_replay_exchange/runs/<run_id>/profile_manifest.json
systems/ccusdt_replay_exchange/runs/<run_id>/events.ndjson
systems/ccusdt_replay_exchange/runs/<run_id>/summary.json
```

## Strategy Profiles

Every fast and sim-live run must name the seven profile boundaries:

```text
policy_profile    strategy decision rule and parameters
capacity_profile  leverage allocator and clipping semantics
exit_profile      shadow/real exit clock and path manager, if any
fill_profile      mid reference vs taker IOC/L2 depth execution
latency_profile   virtual arrival model and latency pressure
transport_profile event transport and clock-driving mode
data_profile      decision-frame cache, quote index, and source manifest identity
```

Each run writes these boundaries to `profile_manifest.json` with a
`profile_manifest_hash`; comparisons should treat the hash/profile fields as
part of the experiment identity, not as optional metadata.

The active 2026-05-18 reproducibility profile is `core_idle01`:

```text
policy_profile: old_tfi_four_cell_shadow_v1, decision_clock=panel
capacity_profile: core_idle01, leverage_cap=3, idle01_gamma in {0,0.5,0.75,1}
exit_profile fast: manager_path or fixed60_mid
exit_profile sim-live: fixed60_taker
fill_profile fast: fast_mid_reference
fill_profile sim-live: top_of_book_taker_ioc_v1
latency_profile sim-live deterministic: deterministic_replay_v1, timer, latency_us=0
latency_profile sim-live pressure: wall_latency_pressure_v1, timer or next-event
transport_profile default strict audit: panel_sparse_fast_clock_v1
data_profile default strict audit: market-derived decision_frame_v1 cache + quote_frame_v1 index
```

Fast and sim-live comparisons must first verify `policy_profile` and
`capacity_profile` match. `exit/fill/latency` differences are allowed only when
the diagnostic explicitly decomposes fast mid edge into taker/latency/slippage
terms. `transport_profile` and `data_profile` must also be present; comparison
tools hard-reject missing profile sections and require compatible
market-derived cache hashes before comparing PnL.

Use `--compare-mode strict_profile` when validating that two runs are literally
the same experiment. That mode hard-rejects `exit_profile`, `fill_profile`,
`latency_profile`, `transport_profile`, and `data_profile` differences. Use the
default decomposition mode only when the goal is to explain fast-mid versus
sim-live-taker execution differences.

The L2 replay iterator treats `local_ts_us` as an atomic panel-clock unit. The
`--l2-batch-size` option is a soft memory cap; it must not split rows that share
the same `local_ts_us`, otherwise `frames_since_mid_change`, snapshot handling,
and four-cell membership drift.

Reproduce the 2026-05-18 old core/idle01 fast profile:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_strategy_backtest.py --repo-root . --from-date 2026-05-18 --to-date 2026-05-18 --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-17.json --gamma-preset core_q70 --capacity-profile core_idle01 --idle01-gamma 1 --exit-profile manager_path --run-id fast_profile_core_idle01_g1_manager
```

Run the sim-live strict gate for the same policy/capacity profile:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500000 --latency-us 0 --arrival-mode timer --log-mode compact --fill-model top-of-book --include-l2 --compact-l2 --run-id sim_live_core_idle01_g1_fixed60 --strategy-arg=--sparse-output --strategy-arg=--window-us --strategy-arg=2000000 --strategy-arg=--decision-clock --strategy-arg=panel --strategy-arg=--decision-trade-window-us --strategy-arg=2000000 --strategy-arg=--max-orders --strategy-arg=0 --strategy-arg=--heartbeat-interval-us --strategy-arg=999999999999 --strategy-arg=--shadow-four-cell --strategy-arg=--shadow-frames-threshold --strategy-arg=31 --strategy-arg=--shadow-overlay-threshold --strategy-arg=59.80000000000018 --strategy-arg=--shadow-fixed-exit-us --strategy-arg=60000000 --strategy-arg=--shadow-gamma-preset --strategy-arg=core_q70 --strategy-arg=--shadow-gamma01-override --strategy-arg=1 --strategy-arg=--shadow-state-in --strategy-arg=systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-17.json --strategy-arg=--shadow-trade-entries --strategy-arg=--shadow-trade-exits --strategy-arg=--shadow-entry-notional --strategy-arg=1.0 --strategy-arg=--shadow-leverage-cap --strategy-arg=3.0 --strategy-arg=--shadow-capacity-profile --strategy-arg=core_idle01 --strategy-arg=--shadow-idle01-gamma --strategy-arg=1 --strategy-arg=--shadow-idle01-reserve --strategy-arg=0
```

Then compare:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/<fast_run_id> --strict-audit-dir systems/ccusdt_replay_exchange/runs/<sim_live_run_id> --date 2026-05-18 --out-dir systems/ccusdt_replay_exchange/runs/<comparison_run_id>
```

The sparse Python runner is the rigorous replay path: it owns the clock, streams
only exchange-style public/private events to Python, schedules returned taker
intents through the timestamp latency queue, submits arrived orders to the
exchange, and writes compact append-only events. Default arrival mode is
`--arrival-mode timer`: arrival occurs at
`observed_local_ts_us + effective_latency_us`, using the last known quote/book
before that virtual timer instant. `--arrival-mode next-event` preserves the old
conservative stress behavior where arrival waits for the first later market
stream event.

`deterministic_replay_v1` and `wall_latency_pressure_v1` are separate latency
profiles. In deterministic replay, Python bridge wall latency is recorded for
timing breakdown only and cannot choose the fill quote. A late Python response
may create nonzero `arrival_stream_lag`, but the deterministic timer
zero-latency gate requires `arrival_quote_lag=0` and
`private_seq_mismatch_count=0`. Private order/fill/account events use the
virtual arrival stream sequence; the actual wall-drain stream sequence is only a
diagnostic field. In wall-latency pressure mode, bridge wall time is
intentionally mapped into virtual staleness and is a stress test, not the
default research baseline.

For repeatability, audit a deterministic run and compare same-profile runs by
stable causal hashes:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py --run-dir systems/ccusdt_replay_exchange/runs/<run_id>
python systems/ccusdt_replay_exchange/diagnostics/repeat_run_hash_gate.py --run-dir-a systems/ccusdt_replay_exchange/runs/<run_a> --run-dir-b systems/ccusdt_replay_exchange/runs/<run_b>
```

The repeat gate compares four independent hashes:

```text
decision_hash         timestamp/cell/side/weight/capacity path
execution_hash        arrival quote/fill price/qty/lot lifecycle
portfolio_hash        account mark, position state, order/fill counts
summary_account_hash  final account/PnL bitwise identity
```

Known full-day deterministic repeat pass: `det_full_20260521_a` versus
`det_full_20260521_b`, with `606` fills, `arrival_quote_lag_count=0`,
different wall-drain lag counts (`54` versus `205`), and matching
decision/execution/portfolio/account hashes.

Strict sparse runs now emit observability without changing deterministic fill
semantics:

```text
run_progress event every 25,000 market events
periodic event-log flush every 5,000 market events
summary.timing_ms market_read / bridge stdin-write / stdout-drain / order-fill / flush breakdown
```

Known smoke: `smoke_sparse_progress_20260521` ran `26,000` events, emitted `1`
`run_progress`, flushed `6` times including final flush, and reported about
`456` events/sec. The dominant cost was
`bridge_stdout_drain_and_response_ms`, because deterministic stdio currently
settles/drains after each event.

Latest fast-vs-strict 2026-05-18 decomposition:

```text
comparison: systems/ccusdt_replay_exchange/runs/fast_vs_strict_det_full_20260521_decomp
fast: fast_profile_core_idle01_g1_fixed60_mid_20260518_20260521
strict: det_full_20260521_a
entry alignment: 304 / 304, field mismatches 0
round trips: 303 matched, 0 missing fills, 3 clipped-weight rows
fast capacity raw: 471.3458 bp-units
strict taker capacity net: 214.6061 bp-units
capacity delta: -256.7397 bp-units
entry spread cost: 63.1741 bp-units
exit spread cost: 193.5656 bp-units
latency/depth/pressure/residual: 0.0000 bp-units in this deterministic top-of-book run
```

Interpretation: this is not fee. With `fee_bps=0`, the loss is crossing the
spread on entry and exit. Exit crossing dominates because fixed60 exits often
hit a wider or less friendly top-of-book than entry.

## Batched Public Stream

`batched_public_v1` is a transport mode for strict replay. It batches public
market events but does not change the deterministic arrival/fill rule:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500000 --latency-us 0 --arrival-mode timer --clock-mode deterministic-step --log-mode compact --fill-model top-of-book --include-l2 --compact-l2 --public-stream-mode batched-public-v1 --public-batch-size 512 --public-batch-max-span-us 5000000 --run-id det_batch_full_span5s_20260521 <same strategy args as strict_event>
```

Acceptance gate:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/repeat_run_hash_gate.py --run-dir-a systems/ccusdt_replay_exchange/runs/det_full_20260521_a --run-dir-b systems/ccusdt_replay_exchange/runs/det_batch_full_span5s_20260521 --compare-mode transport_equivalence
```

Known 2026-05-18 result:

```text
5s span: 606 orders/fills, final account hash identical, transport-equivalence ok
30s span: faster but failed lifecycle equivalence with 599 fills and residual position
```

So `public_batch_max_span_us=5_000_000` is the current safe reference for this
shadow lot lifecycle. Larger spans can delay private fill feedback enough to
change exit-order generation, even when arrival quotes and final fill pricing
remain deterministic. This is exactly why `strict_event` remains the truth gate.

`batched_public_barrier_v1` is the causal-barrier replacement for larger spans:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500000 --latency-us 0 --arrival-mode timer --clock-mode deterministic-step --log-mode compact --fill-model top-of-book --include-l2 --compact-l2 --public-stream-mode batched-public-barrier-v1 --public-batch-size 512 --public-batch-max-span-us 60000000 --run-id det_barrier_full_span60s_20260521 <same strategy args as strict_event>
```

Known 2026-05-18 barrier results:

```text
30s span: 606 orders/fills, arrival_quote_lag_count 0, transport-equivalence ok
60s span: 606 orders/fills, arrival_quote_lag_count 0, transport-equivalence ok
```

The barrier rule is the key difference: if the bot emits an actionable order
inside a batch, it stops and returns `consumed_seq`; Runner sends private
feedback before replaying the unconsumed suffix. If the bot finishes the batch
without an actionable response, it emits `batch_done`. This keeps wall/bridge
timing out of deterministic arrival quotes, fills, portfolio marks, and PnL.

## Panel Sparse Strict Audit

`panel_sparse_v1` is the next hot-path optimization. Runner still consumes the
canonical quote/trade/L2 stream and owns arrival/fill/portfolio, but the Python
bot receives only `market_decision_frame` events built from the validated
`decision_frame_v1` Parquet cache plus audit metadata. It is for strict-audit
acceleration only; it does not replace full `strict_event` or barrier stream
truth gates.

Example full-day command:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500000 --latency-us 0 --arrival-mode timer --clock-mode deterministic-step --log-mode compact --fill-model top-of-book --include-l2 --compact-l2 --public-stream-mode panel-sparse-v1 --public-batch-size 512 --public-batch-max-span-us 60000000 --run-id det_panel_sparse_full_span60s_20260521 <same strategy args as strict_event>
```

Acceptance gates:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/repeat_run_hash_gate.py --run-dir-a systems/ccusdt_replay_exchange/runs/det_full_20260521_a --run-dir-b systems/ccusdt_replay_exchange/runs/det_panel_sparse_full_span60s_20260521 --compare-mode transport_equivalence
python systems/ccusdt_replay_exchange/diagnostics/repeat_run_hash_gate.py --run-dir-a systems/ccusdt_replay_exchange/runs/det_barrier_full_span60s_20260521 --run-dir-b systems/ccusdt_replay_exchange/runs/det_panel_sparse_full_span60s_20260521 --compare-mode transport_equivalence
```

Known 2026-05-18 result:

```text
panel_frames_sent 131608
capacity decisions 304
orders/fills 606
arrival_quote_lag_count 0
transport-equivalence ok versus strict_event and batched_public_barrier_v1
events_per_sec about 553 on the current machine
```

The transport-equivalence hash uses an 8-decimal float normalization for
transport mode only. Repeat-mode hashes remain strict. This avoids false
failures from strict online float construction versus Parquet-cache float
round-trips while still comparing decisions, fills, portfolio state, and final
account under the same economic semantics.

### Panel Sparse Fast Clock

`panel_sparse_fast_clock_v1` is a narrower accelerator for the current
`top_of_book_taker_ioc_v1` strict audit. It uses the validated
`decision_frame_v1` Parquet cache as the decision clock and a `quote_frame_v1`
last-known quote index for deterministic timer arrival/fill. It does not scan
full L2 and is therefore not valid for `l2_taker_depth_v1`, maker queue
research, or online feature-reconstruction validation.

Example full-day command:

```powershell
cargo run --manifest-path systems/quant_replay_engine/Cargo.toml -p quant_replay_cli -- run sparse-python --canonical-date 2026-05-18 --max-events 500000 --latency-us 0 --arrival-mode timer --clock-mode deterministic-step --log-mode compact --fill-model top-of-book --public-stream-mode panel-sparse-fast-clock-v1 --public-batch-size 512 --public-batch-max-span-us 60000000 --run-id det_panel_sparse_fast_clock_full_20260521_seqfix <same strategy args as strict_event>
```

Known 2026-05-18 result:

```text
run det_panel_sparse_fast_clock_full_20260521_seqfix
panel_frames_sent 131608
capacity decisions 304
orders/fills 606 / 606
arrival_quote_lag_count 0
arrival_stream_lag_count 1
market_read_ms 11
total_elapsed_wall_ms 35270
events_per_sec about 3731
transport-equivalence ok versus det_panel_sparse_full_span60s_20260521
transport-equivalence ok versus det_barrier_full_span60s_20260521
```

Current default top-of-book taker strict-audit path:

```text
transport_profile: panel_sparse_fast_clock_v1
fill_profile: top_of_book_taker_ioc_v1
latency_profile: deterministic_replay_v1, timer, latency_us=0
exit_profile strict: fixed60_taker
```

Three-day default strict-audit acceptance output:

```text
matrix: systems/ccusdt_replay_exchange/runs/profile_matrix_top_of_book_20260516_18_20260521
dates: 2026-05-16..2026-05-18
profiles: core_only, idle01_g0.5, idle01_g0.75, idle01_g1
all profile/data gates: ok
all row mismatches: 0
all arrival_quote_lag_count: 0
```

Profile totals:

```text
profile        entries  orders/fills  fast_mid   strict_taker  spread_cost  entry_cost  exit_cost
core_only      764      1484/1484     1159.5840  638.2147      521.3693     63.5981    457.7713
idle01_g0.5    764      1526/1526     1213.9435  649.4415      564.5020     84.3450    480.1569
idle01_g0.75   764      1526/1526     1241.1232  655.0549      586.0683     94.7185    491.3498
idle01_g1      764      1526/1526     1263.9560  656.7311      607.2249     105.1749   502.0500
```

Interpretation: under deterministic top-of-book taker IOC, the fast-mid edge
does not disappear through fees, latency, depth, or pressure in this run. The
entire explained gap is crossing spread on entry and fixed60 exit, with exit
crossing dominating. `core_only` still has 764 aligned candidate entries, but
fewer traded orders because the idle01 sleeve is zero-sized. This matrix is the
current baseline before any future maker, L2-depth, or path-manager
optimization.

The Runner Server path has the same execution semantics, but Python is no longer
a child process. Runner exposes three local TCP NDJSON channels:

```text
public stream   runner -> bot/monitor
private stream  runner -> bot/monitor
order ingress   bot -> runner
state query     monitor -> runner
```

`event_sleep_us` is only a local replay throttle for socket experiments. Monitor
work should remain read-only and consume public/private streams, run files, or
the optional HTTP state-query endpoint without entering the order path. The
console monitor intentionally has no `--order-addr` option.

Validation commands used for this layer:

```powershell
cargo fmt --all --manifest-path systems/quant_replay_engine/Cargo.toml
cargo test --manifest-path systems/quant_replay_engine/Cargo.toml --offline
python -m py_compile systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/strategy.py systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/tcp_bot.py
node --check systems/ccusdt_replay_exchange/monitor/src/console_monitor.mjs
```

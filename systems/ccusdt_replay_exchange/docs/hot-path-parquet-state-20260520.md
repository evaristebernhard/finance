# Hot Path Parquet And State Persistence 2026-05-20

Goal: move strategy experiments off the slow CSV.GZ L2 rebuild path while
preserving market-truth and online-state boundaries.

## Boundary

```text
raw CSV.GZ archive
  -> optional canonical CSV.GZ reference
  -> typed decision_frame_v1 Parquet cache
  -> Bot-owned shadow state
  -> fast shadow audit
  -> Runner+Bot strict gate
```

The Parquet cache is allowed because it is deterministic market-derived state:
trades + L2 updates are replayed through the Bot decision-frame builder. It
does not contain old fixed panels, `date/` scored entries, future labels, PnL,
MFE, or MAE.

## Implemented

`decision_frame_cache.py` now writes typed Parquet:

```text
data/canonical_parquet/cex/bullish/CCUSDT/decision_frame_v1/dt=YYYY-MM-DD/part_000001.parquet
data/canonical_parquet/cex/bullish/CCUSDT/decision_frame_v1/dt=YYYY-MM-DD/manifest.json
```

Manifest fields include:

```text
schema_version
builder_version
input_layer
source hashes
row_count
cache_file_sha256
field_hash_sha256
data_manifest_hash
```

The builder supports:

```text
--input-layer canonical
--input-layer raw
```

`raw` is important for 2026-05-04..2026-05-15 because it bypasses slow
intermediate L2 canonical CSV materialization and builds decision-frame Parquet
directly from raw Bullish trades/L2 files.

## Current Proofs

Raw-vs-cache drift gate for the scoring window:

```text
command: decision_frame_cache.py parity --parity-left raw --parity-right cache --from-date 2026-05-16 --to-date 2026-05-18
rows: 132382 / 114918 / 131608
total rows: 378908
row mismatches: 0
field mismatches: 0
field hashes: identical for all three days
```

Parquet cache built for 2026-05-16..2026-05-18:

```text
rows: 132382 / 114918 / 131608
total rows: 378908
schema: decision_frame_v1.parquet.schema_v1
builder: decision_frame_builder_v1.1_market_derived_cache
```

Fast manifest validation:

```text
command: decision_frame_cache.py validate --from-date 2026-05-16 --to-date 2026-05-18
elapsed: sub-second on this machine
ok: true
```

Deep field hash validation:

```text
command: decision_frame_cache.py validate ... --deep-field-hash
elapsed: about 12 seconds
ok: true
```

Fast shadow audit from Parquet cache:

```text
run: systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_182258
dates: 2026-05-16..2026-05-18
entries: 764 / 764
daily entries: 261 / 199 / 304
feature mismatches: 0
cell totals: 00=305, 10=398, 01=21, 11=40
elapsed wall: about 6 seconds
```

## State Persistence

`shadow_state.py` builds Bot-owned policy state from cached decision frames:

```text
systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=YYYY-MM-DD.json
```

State includes only runtime-safe policy memory:

```text
closed_bps
pending_entries
next_shadow_position_id
policy_params_hash
last_seen_ts_us
last_seen_date
```

It excludes labels, scored entries, PnL/MFE/MAE files, and old panels.

Known state-resume proof:

```text
state: state_after_dt=2026-05-16.json
audit: systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_182539
score dates: 2026-05-17..2026-05-18
entries: 503 / 503
daily entries: 199 / 304
feature mismatches: 0
cell mismatch: 0
reference seed: false
```

Important finding: state must be replayed continuously across day boundaries.
Loading the same `state_after_dt=2026-05-16.json` independently for both
2026-05-17 and 2026-05-18 creates three R5 cell mismatches on 2026-05-18
because 2026-05-17 closed outcomes are missing.

## 2026-05-04..2026-05-15 Warmup Cache

The previous attempt to materialize 2026-05-04..2026-05-15 L2 canonical CSV.GZ
was stopped because it was too slow for the intended hot path. The corrected
path is raw -> decision_frame Parquet directly:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py build --repo-root . --input-layer raw --from-date 2026-05-04 --to-date 2026-05-15
```

Completed result:

```text
dates: 2026-05-04..2026-05-15
input_layer: raw
total frames: 1874502
validate: ok=true for all days
data_manifest_hash_ok: true for all days
single-day build time: about 166s..333s
```

Do not rely on interrupted 2026-05-04..2026-05-06 `l2_level_update_v1` CSV.GZ
outputs as a warmup source unless they are explicitly rebuilt and validated.
The preferred warmup path is `decision_frame_cache.py --input-layer raw`, which
builds decision-frame Parquet directly from raw Bullish market files and skips
the slow intermediate L2 canonical CSV layer.

## No-Reference State Gate

Bot-owned state is now built from the raw-input Parquet warmup cache:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/shadow_state.py --repo-root . --from-date 2026-05-04 --to-date 2026-05-15
```

Completed state:

```text
path: systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-15.json
state_after_date: 2026-05-15
next_expected_date: 2026-05-16
pending_entries: 1
closed_bps: [4.1030821034, 12.6306499472, -11.3672257267, -11.3672257267, -12.0048033625]
data_manifest_hash: b4387c9b910d57d3840136a1b3d012b82f0d323d60f34060b9ffd294bbf0542c
elapsed: about 20.7s
```

No legacy R5 seed gate:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/shadow_four_cell_audit.py --repo-root . --warmup-from-date 2026-05-16 --from-date 2026-05-16 --to-date 2026-05-18 --mode direct --decision-clock panel --decision-frame-source cache --shadow-state-in systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/state_after_dt=2026-05-15.json
```

Completed run:

```text
run: systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_233233
entries: 764 / 764
daily entries: 261 / 199 / 304
feature mismatches: 0
cell totals: 00=305, 10=398, 01=21, 11=40
warmup_reference_r5: false
state boundary guard: passed, next_expected_date=2026-05-16
elapsed by day: about 1.7s / 1.3s / 2.0s
```

The audit rejects non-contiguous state use. For example, loading
`state_after_dt=2026-05-15.json` directly at `2026-05-17` fails with
`shadow_state_boundary_violation`.

## Fast Backtest Baseline

The minimal fast research runner is:

```text
systems/ccusdt_replay_exchange/diagnostics/fast_strategy_backtest.py
```

It reads decision_frame Parquet plus optional Bot-owned state, then runs the
same runtime-safe shadow policy with this execution approximation:

```text
fixed60_mid_exit_capacity_clip_v1
unit net bps =
  direction * log(exit_mid / entry_mid) * 10000
  - fee_bps - pressure_bps - slippage_bps
weighted PnL = unit net bps * actual_exposure
capacity rule = FIFO online clip against leverage_cap
```

Baseline C=0, 3x cap:

```text
run: systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520
entries/exits: 764 / 764
actual_entries: 742
clipped/skipped: 3 / 1
gross = net: 1157.7814 weighted bps
daily net: 263.0807 / 487.6552 / 407.0455
max open exposure: 3.0
elapsed: about 5.4s
```

Pressure sanity with `pressure_bps=2`:

```text
run: systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520_pressure2
net: 348.2814 weighted bps
daily net: -17.6693 / 275.1552 / 90.7955
positive days: 2 / 3
```

This is a fixed60 mid-exit baseline, not the path-manager/watcher strategy.

## Fast Vs Strict

`fast_vs_strict_consistency.py` compares fast backtest shadow entries against a
strict/direct shadow audit run or a sim-live Runner event log.

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520 --strict-audit-dir systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_233233
```

Completed result:

```text
rows compared: 764
fast entries: 764
strict entries: 764
mismatches: 0
fields: local_ts_us, cell, side, membership_set, target_exposure
```

## Sim-Live Entry And Round-Trip Fill Gate

The Bot can now optionally translate shadow entries into real taker IOC orders:

```text
strategy.py --shadow-trade-entries --shadow-entry-notional 1.0
```

This preserves the shadow signal in `order_intent` and causes Runner to emit the
full compact causal chain:

```text
order_intent -> order_scheduled -> order_arrived -> order_ack -> fill
```

It can also translate fixed60 shadow closes into batched taker IOC exit orders:

```text
strategy.py --shadow-trade-exits
```

Completed full-day 2026-05-18 sim-live entry-fill run:

```text
run: systems/ccusdt_replay_exchange/runs/sim_live_shadow_entries_20260518_20260520
state: state_after_dt=2026-05-17.json
events_seen: 258186
quote/trade/L2: 120418 / 6160 / 131608
intents/orders/fills: 294 / 294 / 294
bridge_errors: 0
fill_model: top_of_book_taker_ioc_v1
arrival_mode: timer
clock_mode: deterministic_step
```

Causal log audit:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/audit_event_log.py --run-dir systems/ccusdt_replay_exchange/runs/sim_live_shadow_entries_20260518_20260520
```

Result:

```text
ok: true
event_count: 2663
order chains: 294 complete chains
errors: []
```

Fast-vs-sim-live entry/fill consistency:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520 --strict-audit-dir systems/ccusdt_replay_exchange/runs/sim_live_shadow_entries_20260518_20260520 --date 2026-05-18 --out-dir systems/ccusdt_replay_exchange/runs/fast_vs_sim_live_20260518_20260520
```

Result:

```text
rows compared: 294
fast entries: 294
sim-live order_intents: 294
field mismatches: 0
fills matched: 294
missing fills: 0
weighted fast fixed60 raw bps on traded entries: 406.7478
weighted sim-entry/fast-exit net bps: 362.3226
weighted delta: -44.4252
mean entry execution cost: 0.1680bps
mean observed spread-cross component: 0.1545bps
mean latency slippage component: 0.0135bps
mean residual: approximately 0
```

This is an entry-fill decomposition. It uses real Runner/Bot order/fill events
for entry, then keeps the fast fixed60 mid exit to isolate entry taker execution
cost.

Completed full-day 2026-05-18 sim-live round-trip run:

```text
run: systems/ccusdt_replay_exchange/runs/sim_live_shadow_roundtrip_20260518_20260520
state: state_after_dt=2026-05-17.json
events_seen: 258186
quote/trade/L2: 120418 / 6160 / 131608
intents/orders/fills: 586 / 586 / 586
bridge_errors: 0
fill_model: top_of_book_taker_ioc_v1
arrival_mode: timer
clock_mode: deterministic_step
final equity: 10000.019003
```

Causal log audit:

```text
ok: true
event_count: 4419
order chains: 586 complete chains
errors: []
```

Fast-vs-sim-live round-trip consistency:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/fast_vs_strict_consistency.py --repo-root . --fast-run-dir systems/ccusdt_replay_exchange/runs/experiments/fast_core_q70_20260516_18_20260520 --strict-audit-dir systems/ccusdt_replay_exchange/runs/sim_live_shadow_roundtrip_20260518_20260520 --date 2026-05-18 --strict-source events --out-dir systems/ccusdt_replay_exchange/runs/fast_vs_sim_live_roundtrip_20260518_20260520
```

Result:

```text
entry intents compared: 294 / 294
field mismatches: 0
entry fills matched: 294
round trips matched: 292
missing exit intents: 2
weighted fast shadow raw bps on matched round trips: 406.0404
weighted sim shadow net bps on matched round trips: 194.6315
weighted shadow delta: -211.4088
mean entry execution cost: 0.1567bps
mean exit execution cost: 1.0788bps
mean total execution cost: 1.2355bps
mean latency slippage: about -0.0022bps
```

Interpretation: the decision clock and order-intent layer do not drift
(`294/294`, zero field mismatches). The large PnL delta is mainly execution
semantics: fast baseline exits at fixed60 mid, while sim-live exits cross the
taker top of book. The two missing exits are end-of-run lifecycle boundary
cases, not entry mismatches.

Capacity note: the consistency script reports both shadow target weights and
fast capacity weights. The current sim-live Bot submits shadow target notional;
the fast runner applies leverage clipping separately. This is deliberate for
the present gate: first prove signal/order causality, then wire the same
capacity allocator into the sim-live order path.

## Dual-Track Meaning

Fast strategy backtest answers:

```text
edge shape, parameter scans, pressure sweeps, tail/capacity diagnostics
```

Sim-live replay backtest answers:

```text
exchange-style streams, bridge latency, order arrival, fill realism,
private stream causality, monitor/log trust
```

Both tracks must share the same market-derived base:

```text
raw archive -> typed decision_frame cache -> Bot-owned state -> manifest/registry
```

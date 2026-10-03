# Quant Replay Studio native frontend

`frontend-tauri/` is the current React + Tauri product surface for the
local-first workflow. This directory remains the Slint reference build while
the new desktop shell is migrated and verified.

Start the current product from `frontend-tauri/` with `npm run tauri:dev`.
The Rust replay repository in this directory is still the shared data truth
used by the Tauri commands.

`Run Library` is the default page. `Backtest Setup` creates a Runner contract and
opens `Replay Workbench` when the artifacts are ready.

## Run

From the repository root:

```bash
cargo run --manifest-path frontend/Cargo.toml
```

The `Create Run` action starts the native Rust Runner with 25,000 canonical
events. The Runner writes `manifest.json`, `summary.json`, `events.ndjson`,
and `replay_index.json` under
`systems/quant_replay_engine/runs/<run_id>/`. The Rust repository layer loads
those artifacts and feeds Slint batched cursor snapshots; the UI does not
recompute fills or PnL.

Selecting `L2 depth` enables the Runner's L2 path. Snapshot-heavy L2 data is
shown as a warning in the workbench and never presented as unconditional
queue-replay readiness. The artifact keeps compact batch metadata plus the
current top five bid/ask levels and cumulative quantities, while the canonical
L2 file remains the raw source of truth.

The Run Library reads only `manifest.json` and `summary.json`; it does not scan
`events.ndjson` until a run is opened. The native path performs a 4,096-row L2 preflight at run start. Full strict
validation is still available through the CLI `canonical validate` command;
the hot replay path avoids rescanning the entire compressed file before every
run and caps same-timestamp L2 batches.

Set `QRS_REPO_ROOT` when launching the binary outside the repository checkout.

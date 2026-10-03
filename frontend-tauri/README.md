# Quant Replay Studio — React + Tauri

This is the new desktop product surface. React owns the visual workspace and
Tauri exposes local Runner artifacts through Rust commands. The Runner owns execution outcomes. Replay v2 reads event offsets, keeps in-memory quote/account checkpoints, and serves numeric window, paged row, and event inspection queries. The UI does not recompute fills or execution PnL.

## Run

From this directory:

```bash
npm install
npm run tauri:dev
```

For browser-only layout work:

```bash
npm run dev
```

The desktop shell discovers the repository from its build location. Set
`QRS_REPO_ROOT` when launching the binary from another checkout.

## Product flow

`Run Library → Backtest Setup → Replay Workbench`

Setup parameters include strategy profile, fill model, `delay_time` in
microseconds, fee in basis points, and starting cash. The workbench follows
the React layout that proved more readable: price path, order book, trade
story, signal explanation, arrival view, position/PnL, event tabs, a P&L path,
and the causal/raw-event inspectors.


Replay controls follow Runner event time: 1× means one replay second per wall-clock second, with speeds from 0.25× to 16×. Tauri emits `replay_snapshot_v2` at most every 50 ms. `get_replay_window`, `query_replay_rows`, and `inspect_replay_event` carry the session ID and cursor bound so stale requests cannot reveal later events.

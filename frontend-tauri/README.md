# Quant Replay Studio — React + Tauri

Quant Replay Studio is a **deterministic strategy replay and historical analysis workstation**.

It is not primarily a charting terminal or a summary-statistics backtester. The
product goal is to reproduce a strategy's event-time execution story and make it
possible to answer:

- What did the strategy observe?
- Why did it decide to trade?
- What happened while the order was in flight?
- What book/quote did the order arrive into?
- How was the fill produced?
- Where did the resulting PnL come from?

The active desktop product surface is this directory: React owns the visual
workspace and Tauri exposes local Runner artifacts through Rust commands. The
Runner owns execution outcomes. The UI reads and explains artifacts; it does
not recompute fills or execution PnL.

## Product flow

```text
Experiments
  -> New Experiment
  -> deterministic Runner artifact
  -> Replay Debugger
```

The current UI exposes three product ideas:

1. **Replay** — reproduce the event-time story.
2. **Explain** — trace observation -> signal -> intent -> arrival -> fill -> PnL.
3. **Compare** — planned next milestone: explain why two experiments diverge.

"Compare" is intentionally documented as the next milestone rather than exposed
as a fake working control.

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

## Current replay contract

Setup parameters currently include strategy profile, fill model, `delay_time`
in microseconds, fee in basis points, and starting cash.

The Runner writes:

```text
manifest.json
summary.json
events.ndjson
replay_index.json
```

Replay v2 reads event offsets, keeps in-memory quote/account checkpoints, and
serves numeric windows, paged event rows, causal inspection and raw-event
inspection. Replay controls follow Runner event time: 1x means one replay second
per wall-clock second, with speeds from 0.25x to 16x.

Tauri emits `replay_snapshot_v2` at most every 50 ms.
`get_replay_window`, `query_replay_rows`, and `inspect_replay_event` carry
the session ID and cursor bound so stale requests cannot reveal later events.

## Important current limitation

The product shell is now market-neutral in intent, but the experiment creation
form is still backed by the current CCUSDT pack and a small set of built-in
strategy profiles. General dataset selection, strategy/plugin discovery and A/B
experiment comparison are backend/product milestones, not completed features.

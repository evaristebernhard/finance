# Quant Replay Studio

> **Deterministic Strategy Replay & Historical Analysis**

Quant Replay Studio is a local-first workstation for replaying historical market
sessions and studying how a strategy behaved inside them.

The product is meant to answer:

```text
What did the market look like?
        ->
Where did the strategy act?
        ->
What order actually arrived and filled?
        ->
How did position and PnL evolve?
        ->
What market / signal / execution context surrounded that trade?
```

The event debugger is still important, but it is a drill-down tool. The main
product surface is historical replay and trade analysis.

## Active product

- [React + Tauri frontend](frontend-tauri/README.md)
- [Quant Replay Engine](systems/quant_replay_engine/README.md)
- [Product direction](docs/product/quant-replay-studio.md)
- [Engineering docs](docs/engineering/README.md)

The older Slint UI under `frontend/` is a reference implementation. The old
React workbench is also reference material only: its client-side toy fill
simulation must not be copied into the active product.

## Product flow

```text
Experiments -> New Experiment -> Replay Analysis
```

A Runner execution writes immutable local artifacts. Replay Analysis reads those
artifacts and shows historical price, order-book state, strategy signals, order
and fill markers, account PnL and causal context. The UI does not invent fills
or recompute execution outcomes.

## Run the desktop app

```bash
cd frontend-tauri
npm install
npm run tauri:dev
```

The Rust Runner binary must be built under
`systems/quant_replay_engine/target/debug/`. Set `QRS_REPO_ROOT` when the
desktop app is launched outside this checkout.

## Current scope

The replay engine is market-neutral, while the experiment-creation UI is still
backed by the current CCUSDT pack and a small set of strategy profiles.

The immediate product priorities are:

1. make historical market/trade/PnL review excellent;
2. expose typed signal and execution context instead of hiding it in raw JSON;
3. generalize datasets and strategies through stable contracts;
4. improve attribution and large-run replay.

Automatic experiment comparison is intentionally deferred.

## Repository safety

Do not commit live API credentials. Keep local credentials in ignored env files
and examples as placeholders only.

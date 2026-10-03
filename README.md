# Quant Replay Studio

> **Deterministic Strategy Replay & Historical Analysis**

Quant Replay Studio is a local-first workstation for reproducing and debugging
the causal path from market data to strategy decision, order arrival, fill,
position and PnL.

Instead of stopping at an equity curve, the product is designed to answer:

```text
What did the strategy see?
        ->
Why did it act?
        ->
What changed during latency?
        ->
How was the order filled?
        ->
Where did the PnL come from?
```

## Active product

The current desktop product is:

- [React + Tauri frontend](frontend-tauri/README.md)
- [Quant Replay Engine](systems/quant_replay_engine/README.md)
- [Product direction](docs/product/quant-replay-studio.md)
- [Engineering docs](docs/engineering/README.md)

The older Slint UI under `frontend/` is a reference implementation, not the
active user-facing product.

## Product flow

```text
Experiments -> New Experiment -> Replay Analysis
```

A Runner execution writes immutable local artifacts. The Replay Debugger reads
those artifacts and follows the causal chain without recomputing fills or PnL.

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

The replay engine is market-neutral, while the experiment creation UI is still
backed by the current CCUSDT pack and a small set of strategy profiles.

The next product milestones are dataset/plugin generalization and causal A/B
comparison between experiments. The core Runner does not need to be rewritten.

## Repository safety

Do not commit live API credentials. Keep local credentials in ignored env files
and examples as placeholders only.

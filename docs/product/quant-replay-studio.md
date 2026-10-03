# Quant Replay Studio product direction

## Definition

**Quant Replay Studio is a deterministic strategy replay and historical analysis
workstation.**

The primary question is not only "did this strategy make money?" It is:

> What happened in this historical market, where did the strategy act, what
> actually filled, how did PnL evolve, and what conditions surrounded those
> decisions?

The debugger is a secondary drill-down tool for a selected event.

## Product boundary

Quant Replay Studio should own:

```text
Dataset
  -> Experiment contract
  -> deterministic Runner
  -> causal artifacts
  -> Historical Replay Analysis
  -> Event / causal debugger
```

It should not try to become, at this stage:

- a live broker terminal;
- a TradingView clone;
- a hosted cloud-compute platform;
- a portfolio/account-management product;
- a strategy marketplace.

The local-first boundary is useful because proprietary datasets and strategy code
can stay on the user's machine.

## UI information architecture

The active React + Tauri product uses:

```text
Experiments
New Experiment
Replay Analysis
```

### Experiments

A library of completed Runner artifacts. A user should be able to open a run and
immediately understand the market, strategy, execution model, number of orders
and fills, and run status.

### New Experiment

An experiment is a reproducible contract:

```text
dataset
+ strategy / configuration
+ execution model
+ latency
+ fees
+ initial capital
+ data-quality state
```

The current form is still backed by the CCUSDT pack. Future UI should populate
these fields from dataset and strategy registries instead of hard-coding them.

### Replay Analysis

The main screen should prioritize historical analysis in this order:

1. historical price path;
2. signal / intent / arrival / actual fill markers;
3. order book at the replay cursor;
4. historical fill table;
5. realized / unrealized PnL and equity path;
6. signal strength / threshold / reason;
7. execution conditions such as latency and slippage;
8. causal/raw event inspection only when deeper debugging is needed.

The UI must not fabricate trading opportunities or client-side fills. When it
shows a "historical opportunity", that means a Runner-recorded strategy signal
and its threshold/context in that historical run.

## What to reuse from the legacy React workbench

Useful ideas:

- large central price chart;
- order book on the same screen;
- trade and PnL state visible without opening raw logs;
- factor / research context near the replay cursor;
- terminal-like information density.

Do not reuse:

- client-side order simulation;
- `executablePrice()` as execution truth;
- client-side portfolio/PnL calculations presented as historical outcomes;
- factor rankings that are disconnected from the Runner artifact contract.

## Backend assessment

### Already sufficient

The backend already has the hard core:

- deterministic ordered replay;
- event-time strategy decisions;
- latency queue;
- top-of-book and L2 execution paths;
- exchange/account simulation;
- causal event logging;
- replay indexes and event offsets;
- cursor/session semantics that prevent future-event leakage;
- immutable local run artifacts.

No engine rewrite is needed.

### Backend work still useful

#### 1. Historical analysis queries

Expose typed data needed by the UI instead of forcing React to parse raw JSON:

- signal and threshold;
- strategy reason/context;
- actual fill price and side;
- latency and latency slippage;
- realized/account deltas recorded at fills;
- typed execution attribution;
- account/PnL snapshots.

#### 2. Experiment manifest cleanup

Runs need stable dataset, strategy, execution and quality identity so historical
results remain reproducible and auditable.

#### 3. Dataset / strategy registries

Generalize beyond the current CCUSDT pack while preserving the same Runner
artifact contract.

#### 4. Typed attribution

Promote execution cost, spread cost, fees, latency effects and later
post-fill/adverse-selection metrics into a stable schema.

#### 5. Scale

Large runs need sparse checkpoints and indexes so seeking and historical window
queries stay fast.

## Near-term sequence

```text
1. Historical replay UI and trade review      [current]
2. Typed historical signal/fill queries       [current]
3. Experiment manifest cleanup
4. Dataset / strategy registries
5. Typed attribution improvements
6. Large-run checkpoints/indexes
7. Additional market/asset packs
```

Automatic experiment comparison is intentionally deferred until the historical
single-run workflow is mature.

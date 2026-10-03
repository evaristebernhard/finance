# Quant Replay Studio product direction

## Definition

**Quant Replay Studio is a deterministic strategy replay & debugger.**

The core user problem is not merely "did this strategy make money?" The product
should answer "why did this exact decision become this exact execution and this
exact PnL?"

A useful mental model is a debugger for trading systems: replay the market clock,
stop at an event, inspect the strategy observation, follow the order through
latency and exchange simulation, and inspect the resulting account transition.

## Product boundary

Quant Replay Studio should own:

```text
Dataset
  -> Experiment contract
  -> deterministic Runner
  -> causal artifacts
  -> Replay Debugger
  -> Compare / divergence analysis
```

It should not try to become, at this stage:

- a live broker terminal;
- a TradingView clone;
- a hosted cloud-compute platform;
- a portfolio/account-management product;
- a strategy marketplace.

The local-first boundary is an advantage: proprietary datasets and strategies
can stay on the user's machine.

## UI information architecture

The active React + Tauri product uses:

```text
Experiments
New Experiment
Replay Debugger
```

### Experiments

A library of immutable Runner outputs. The page should communicate the product
thesis immediately:

- **Replay** the exact event-time story.
- **Explain** signal -> intent -> arrival -> fill -> PnL.
- **Compare** two experiments and explain their first meaningful divergence.

### New Experiment

An experiment is a reproducible contract:

```text
dataset
+ strategy version/config
+ execution model
+ latency
+ fees
+ initial capital
+ data-quality state
```

The current UI is still backed by the CCUSDT pack. Future UI should populate
these fields from registries/plugins instead of hard-coding them.

### Replay Debugger

The debugger should prioritize causal questions over dashboard density:

1. What did the strategy observe?
2. Why did it act?
3. What changed before the order arrived?
4. How did the fill model execute it?
5. What account/PnL transition followed?

Raw event JSON remains available, but it is supporting evidence rather than the
main product.

## Backend assessment

### Already strong enough

The current backend already has the difficult core pieces:

- deterministic ordered replay;
- strategy decisions on event time;
- latency queue;
- top-of-book and L2 execution paths;
- exchange/account simulation;
- causal event logging;
- replay index and event offsets;
- cursor/session semantics that prevent future-event leakage;
- local immutable run artifacts.

That is enough to support the deterministic replay/debugger positioning now.

### Backend changes still required

The next work is **generalization, not a rewrite**.

#### 1. Experiment manifest v2

A run needs stable identity fields for dataset, strategy/plugin version,
execution plugin/model, parameters and quality status. Two runs must be
machine-comparable.

#### 2. Plugin contracts

Formalize four boundaries:

```text
DataPlugin
StrategyPlugin
ExecutionPlugin
AnalysisPlugin
```

The first useful version can be manifest/process based; it does not need a
complex dynamic-library ABI.

#### 3. Compare engine

Given run A and run B, align causal timelines and identify:

- same observation, different decision;
- same intent, different arrival state;
- fill vs missed fill;
- different fill price/quantity;
- first account/PnL divergence;
- cumulative attribution delta.

This is likely the most important backend feature after single-run replay.

#### 4. Typed attribution

Promote latency slippage, spread/execution cost, fees, mark movement and later
adverse selection from presentation strings/optional JSON into a stable schema.

#### 5. Dataset registry

Parquet remains the source of replay truth; DuckDB should index discovery,
quality reports and analytics. Dataset states should preserve L1/L2 readiness
rather than a single boolean.

#### 6. Scale

For very large artifacts, keep sparse checkpoints and indexes so seek/window
queries do not require rebuilding state from event zero.

## Near-term sequence

```text
1. Product/UI terminology and docs          [now]
2. Experiment manifest cleanup
3. Dataset registry
4. Plugin contract v1
5. Compare engine v1
6. Typed attribution improvements
7. Additional market/asset plugins
```

The existing Runner/replay core should remain the center of the system.

# Quant Replay Studio — React + Tauri

Quant Replay Studio is a **deterministic strategy replay and historical analysis
workstation**.

The active UI is designed for studying a completed historical strategy run as a
market session, not merely reading summary backtest statistics.

## Main user jobs

### 1. Replay the historical market

Price, book state, strategy signals, orders and fills share one event-time cursor.

### 2. Review what the strategy actually did

The UI shows Runner-recorded signals, intents, arrivals, fills, position and PnL.
It never creates toy fills or recomputes execution results in React.

### 3. Study trade context

A selected signal/order/fill can be inspected together with signal strength,
threshold, quote/book state, latency, slippage, account changes and the raw
causal event chain.

The older React workbench is useful as a layout reference because it placed the
price chart, order book, trade state and research context on one screen. Its
client-side `executablePrice()` / toy portfolio logic is deliberately not part
of the active product.

## Product flow

```text
Experiments
  -> New Experiment
  -> deterministic Runner artifact
  -> Replay Analysis
      -> historical market + fills + PnL
      -> signal / order / execution context
      -> event debugger when needed
```

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

The Runner writes:

```text
manifest.json
summary.json
events.ndjson
replay_index.json
```

Replay v2 provides:

- event-time play / pause / seek;
- bounded price and PnL windows;
- signal/order/fill markers;
- paged historical rows;
- historical fill metrics such as latency slippage and Runner-recorded PnL deltas;
- causal inspection and raw-event inspection.

The UI is cursor-bounded: it must not expose future events while replaying.

## Current limitation

The product shell is market-neutral in intent, but experiment creation is still
wired to the current CCUSDT pack and built-in strategy profiles. Dataset and
strategy registries are future backend/product work.

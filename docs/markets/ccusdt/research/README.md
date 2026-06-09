# CCUSDT Research Index

The research layer is split by question type, not by report date.

Research reports are evidence and hypotheses, not runtime truth. Before using
any report to describe the current strategy, read:

```text
docs/markets/ccusdt/current/CURRENT_STRATEGY_PLAIN.md
```

Do not infer that the Bot implements `Delta_bps/Energy_bps`, OFI/MLOFI,
dynamic L2 path prediction, deep learning, maker logic, or capacity curves just
because they appear in research notes. Those items are research references
unless a runtime file or profile manifest explicitly says otherwise.

## Factors

Use `factors/` to understand what the signal measures:

- Start with `factors/v1-microstructure-factor-atlas-20260601.md` for the
  next factor-analysis map.
- TFI and signed flow.
- R5/R10 as path-shape ratios.
- Delta/Energy/Z decomposition.
- LOB depth, spread, queue, OFI/MLOFI.
- Entry quality, release/decay, pretrade-safe state.

## Strategy

Use `strategy/` to understand how factor evidence becomes a policy:

- Four cells `00/10/01/11`.
- Capacity, leverage, idle `01` sleeve, FIFO clipping.
- Path casebook, watcher, conditional wait, exit timing.
- Fast-vs-strict strategy comparisons.

## Execution

Use `execution/` for fill realism and market-access assumptions:

- Taker IOC and spread cost.
- L2 depth and queue/fill diagnostics.
- Maker-first reports, currently paused as strategy work.
- Execution references that should not be confused with current runtime policy.

## No-Go And Superseded

Use `../archive/no-go/` for v2 branches and no-go evidence. Use
`../archive/superseded/` for reports replaced by later v1 findings. These are
not first-read material.

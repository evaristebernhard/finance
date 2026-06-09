# CCUSDT START HERE

This is the first page for a fresh Codex session working on the current CCUSDT line.

## Current Goal

The default active branch is:

```text
CCUSDT replay exchange / TFI strategy / fast-vs-strict research kernel
```

The work is not just a strategy table. It is a research system:

```text
canonical market truth
-> online feature state
-> sparse strategy intents
-> Runner-owned latency/fill/portfolio
-> compact event log
-> Monitor/read-only explanation
```

## System Boundary

- Runner owns market truth, virtual clock, latency, order arrival, fills, portfolio, and event logs.
- Bot owns online feature state, shadow policy, capacity decisions, and sparse order intents.
- Monitor is read-only. It aggregates run artifacts and live state, but never sends orders.
- Runtime must not read `date/`, scored entries, future labels, PnL/MFE/MAE, or root research scripts.
- Current execution baseline is `top_of_book_taker_ioc_v1`. `fee_bps=0` does not mean zero cost; crossing spread remains a real execution cost.

## Strategy State

- First read the plain runtime truth page before reading research reports:
  `docs/markets/ccusdt/current/CURRENT_STRATEGY_PLAIN.md`.
- Active runtime strategy: a simple TFI state machine, not a deep learning
  model and not a dynamic L2 path model.
- Runtime concepts actually in use: TFI, `past_event_25_bps`, spread/q70
  admission, `frames_since_mid_change`, R5, four cells `00/10/01/11`,
  gamma sizing, 3x capacity ledger, and fixed/simple exit.
- Research-only concepts not yet in CC runtime control: Delta/Energy/Z,
  OFI/MLOFI, dynamic L2 path prediction, maker strategy, and capacity curves.
- Current capacity framing: 3x online exposure ledger with core cells and optional idle `01_frames_only` sleeve.
- Current open research problem: define a real path-distribution prediction
  problem before more gamma tuning or capacity discussion.
- v2 execution research is archived as no-go for now. Do not restart it by tuning TP/SL grids or post-hoc filters on the same candidates.

## Engineering State

- Fast line answers edge, parameters, capacity, tail, and walk-forward style questions.
- Strict line answers replay realism, latency, fill, portfolio, causal event log, and Monitor auditability.
- `panel_sparse_fast_clock_v1` is the strict-audit hot path for top-of-book taker research.
- Full stream / barrier gates still matter for realism validation, L2-depth fill, maker/queue work, and online feature reconstruction.

## Read These 7 Files First

1. `systems/ccusdt_replay_exchange/AGENTS.md`
2. `systems/ccusdt_replay_exchange/README.md`
3. `systems/ccusdt_replay_exchange/docs/runbook.md`
4. `docs/markets/ccusdt/current/CURRENT_STRATEGY_PLAIN.md`
5. `docs/markets/ccusdt/current/v1-current-tfi-strategy-handoff-20260518.md`
6. `docs/markets/ccusdt/current/v1-tfi-current-research-map-20260519.md`
7. `docs/books/ccusdt-engineering-codebook/README.md`

Optional but useful after the first pass:

- `docs/books/ccusdt-data-structure-booklet/README.md`
- `docs/books/ccusdt-replay-exchange/README.md`
- `docs/markets/ccusdt/current/README.md`
- `docs/markets/ccusdt/research/README.md`

## Do Not Start Here

- Do not start from top-level `v1-*.md` or `v2-*.md` files in this folder. They are compatibility stubs after the 2026-06-01 reorganization.
- Do not start from `archive/no-go/` unless the user explicitly asks to resume a no-go branch.
- Do not treat maker-first reports as live-ready. They are execution research references.
- Do not use `date/` outputs, scored entries, or future labels as runtime inputs.

## Recommended Next Task Order

1. If the user asks about code: read the engineering codebook, then inspect the exact Runner/Bot/Monitor files.
2. If the user asks about factors: read `research/factors/v1-microstructure-factor-atlas-20260601.md`, then the factor-analysis book and current research map.
3. If the user asks about Monitor or event logs: read the data-structure booklet and `event_contracts.md`.
4. If the user asks about strategy optimization: compare fast and strict profiles first; do not mix profiles.
5. If the user asks about execution/maker/taker: state that taker IOC is the current baseline and maker work is paused unless explicitly resumed.

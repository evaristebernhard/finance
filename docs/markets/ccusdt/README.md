# CCUSDT Docs Index

Start here for the current CCUSDT research system:

```text
docs/markets/ccusdt/START_HERE.md
```

This directory was reorganized on 2026-06-01 so a fresh Codex session can enter
the current CCUSDT line without reading every historical report.

## Current

- `START_HERE.md`: first page for new sessions.
- `current/`: active v1 TFI path-first handoff, current research map, capacity, watcher, OOS, and strategy baseline reports.
- `current/README.md`: current-file guide.

## Research

- `research/factors/`: microstructure factor atlas, TFI, LOB, R5, Delta/Energy/Z, entry quality, release/decay, pretrade-safe factors.
- `research/strategy/`: four-cell policy, path cases, capacity, leverage, watcher, conditional wait, exit timing.
- `research/execution/`: taker cost, maker-paused research, L2/queue/fill realism references.
- `research/README.md`: how to read the research layer.

## System

- `system/`: market-facing docs that belong with CCUSDT docs rather than source code.
- The source-of-truth system docs remain under `systems/ccusdt_replay_exchange/docs/`.

## Archive

- `archive/superseded/`: reports replaced by later v1 findings.
- `archive/no-go/`: v2 execution/universe branches that are not active unless the user explicitly resumes them.
- `archive/diagnostics/`: older diagnostics kept for reference.

## Compatibility Stubs

Top-level `v1-*.md` and `v2-*.md` files are now short compatibility stubs. Each
contains a `Moved to:` line pointing to the real report.

The move manifest is:

```text
docs/markets/ccusdt/reorg_manifest_20260601.csv
```

Do not edit a top-level stub when updating a report. Edit the moved file.

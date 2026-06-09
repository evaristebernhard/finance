# Factor Reports

This folder keeps reports about CCUSDT factor measurement: TFI, LOB state,
R5/R10, Delta/Energy/Z, entry quality, release/decay, and runtime-safe feature
construction.

Start the next factor-analysis pass here:

```text
docs/markets/ccusdt/research/factors/v1-microstructure-factor-atlas-20260601.md
```

It reframes the current work as a microstructure factor atlas rather than an
R5-only strategy tuning loop. It also records the data boundary:
`quote_frame_v1` is available through `2026-05-30`, while complete
trade-flow/TFI diagnostics should stay on `2026-05-04..2026-05-18` unless the
trade/L2 layers are rebuilt.

For teaching-level explanations, start with:

```text
docs/books/ccusdt-factor-analysis/README.md
```

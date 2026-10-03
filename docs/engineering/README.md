# Engineering Docs

Status: 2026-10-02. The active product surface is the native local-first Quant Replay Studio. The former browser workbench is preserved as an archive.

## Quant Replay Studio

- Native frontend: [frontend/Cargo.toml](../../frontend/Cargo.toml)
- Slint UI: [frontend/ui/main.slint](../../frontend/ui/main.slint)
- Desktop bridge: [frontend/src/main.rs](../../frontend/src/main.rs)
- Replay engine: [quant replay engine](../../systems/quant_replay_engine/Cargo.toml)
- Archived browser prototype: [legacy web workbench](../../archive/legacy_web_workbench/README.md)
- Data platform boundary: [next-stage data platform](../next-stage-data-platform.md)

## Runner and data path

Run the native app from the repo root:

```bash
cargo run --manifest-path frontend/Cargo.toml
```

The button in the native app launches the real local Runner. The active flow
is:

```text
Dataset preflight
  -> canonical event stream
  -> strategy bridge
  -> latency queue / exchange simulator
  -> local run artifacts
  -> Slint Results page
```

The active storage direction is local Parquet plus embedded DuckDB for catalog
and analytics. DuckDB is not placed in the Runner hot path. L2 is a gated
dataset capability: the CLI refuses depth replay when preflight finds no
snapshot, timestamp regressions, or invalid price/quantity rows.

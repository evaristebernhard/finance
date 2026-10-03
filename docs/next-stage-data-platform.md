# Quant Replay Studio data platform boundary

The desktop product should treat data as a local dataset with a quality
contract, not as a database connection that the customer has to operate.

## Default storage

```text
raw vendor files        data/raw/
canonical partitions    data/canonical/<venue>/<symbol>/<date>/*.parquet
embedded index          data/catalog.duckdb
Runner input            sequential chunk / mmap stream
```

Parquet is the source of truth for replay. DuckDB is an embedded query and
catalog layer for dataset browsing, validation reports, filtering, and
analytics. The Runner must not execute SQL per market event; it should receive
an ordered stream of canonical events from a backend adapter.

`systems/quant_replay_engine` now exposes `MarketDataBackend` and a compatibility
`CanonicalFilesBackend`. The current CSV/GZip adapter is deliberately kept
behind this boundary while the Parquet and embedded DuckDB adapters are built.
ClickHouse remains an optional professional/institutional adapter.

## L2 is a gated capability

The dataset browser must not represent L2 as simply present or absent. A
dataset can contain L2 rows and still be unsafe for depth-aware fills. Before
`l2_depth` is selectable, the preflight should establish:

- a usable initial snapshot exists;
- prices are finite and positive, quantities are finite and non-negative;
- exchange and local timestamps do not regress;
- update batches can be ordered deterministically;
- applying the stream does not create a crossed or otherwise invalid book;
- any vendor repair or dropped interval is recorded in the quality report.

The canonical validator now reports snapshot rows, timestamp regressions,
invalid rows, a `reconstructible` flag, and human-readable warnings. A future
Parquet/DuckDB adapter should preserve these fields in the dataset registry.

Recommended product states:

```text
L1 READY          quote/trade replay is safe
L2 READY          depth replay passed preflight
L2 DEGRADED       rows exist, but depth fill is gated with a warning
INVALID           canonical data cannot be replayed deterministically
```

If L2 is degraded, top-of-book replay may still run. The UI should make the
chosen fill model and the exact L2 quality status part of the run manifest.

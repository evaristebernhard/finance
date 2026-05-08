# Data Surface Contract

## Evidence Rules
Every object carried through code must be labeled with:
- `EvidenceKind`
- `ObjectRole`
- `ObservationStrength`

This is a hard boundary, not documentation garnish.

## Current Data Surfaces
- RPC-only AMM snapshot:
  supports direct local geometry for `G_t` and direct block metadata for `F_t`-adjacent fields, via `crates/monad-mev-rpc`.
- Normalized execution-event JSONL:
  supports isolated event reconstruction for parts of `M_t`, `C_t`, `R_t`, and `E_t`, via `crates/monad-mev-observation`.
- Execution Events:
  reserved as an upstream source, but consumed only after normalization into file-based JSONL.
- External prices:
  first pass uses synthetic oracle context while retaining official anchors.

## RPC-only Contract
Under RPC-only:
- `cpmm` reserves and `clmm` active-band state may be direct observations.
- `q_t/r_t/kappa_t/u_t/p_t` must be absent or weak proxies.
- `monad-mev-cli snapshot` writes raw observations into `data/raw/*.jsonl`.
- `AmmSnapshotEnvelope` is the only RPC-only snapshot carrier in the workspace.

Under normalized event ingest:
- the workspace consumes JSONL files of `NormalizedExecEvent`
- no GPL event-ring crate is linked directly into the MIT workspace
- commit/access/outcome fields may upgrade parts of `M_t/C_t/R_t/E_t` from empty to event-reconstructed

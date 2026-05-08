# System Architecture

## Purpose
This workspace implements the first executable closed loop of the project-wide research architecture:

```text
data adapters
  -> raw observations / normalized exec-event files
  -> primitive state builder
  -> AMM-first route planner
  -> seeded synthetic projection builder
  -> compressed decision state
  -> paper Bellman policy
  -> paper execution / replay / eval
```

The key constraint is one-way supply. Lower layers provide typed inputs to higher layers; higher layers do not redefine the research objects.

## Workspace Layout
- `crates/monad-mev-domain`: canonical evidence, role, primitive/projection/decision-state, route, and execution types.
- `crates/monad-mev-rpc`: RPC-only AMM snapshot adapter for `cpmm` and `clmm`; this replaces the former standalone RPC prototype.
- `crates/monad-mev-observation`: raw observation records, append-only JSONL storage, and isolated normalized execution-event ingest.
- `crates/monad-mev-state`: raw observation to primitive state and compressed decision-state builders.
- `crates/monad-mev-projection`: AMM-first route planning and seeded synthetic projections.
- `crates/monad-mev-strategy`: paper Bellman policy.
- `crates/monad-mev-eval`: paper execution, replay, PnL, and risk reports.
- `crates/monad-mev-cli`: `snapshot`, `ingest-events`, `build-decision-state`, `decide`, `paper-execute`, `replay`, and `eval`.

## V1 Boundary
- Supported data surface: RPC-only `cpmm/clmm` snapshots plus normalized execution-event JSONL.
- Strongly unsupported as direct truth in v1: `Gamma`, `q_t`, `r_t`, `kappa_t`, `u_t`, `p_t`.
- Bellman and execution are paper-only in v1; there is no signer or live broadcast path.
- There is no separate RPC project boundary anymore; the adapter boundary is crate-level inside this workspace.

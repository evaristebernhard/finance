# State And Projection Contract

## Primitive State View
`PrimitiveStateView` is partial by design. Missing fields mean “not supported by current data surface,” not zero and not false.

Its fields are restricted to:
- `g_t`
- `m_t`
- `c_t`
- `r_t`
- `e_t`
- `f_t`

## Projection State
`ProjectionStateView` carries:
- `gamma_t`
- `p_t`
- `u_t`
- `q_t`
- `r_t`
- `kappa_t`

These objects are not primitive fields. In v1 they are seeded synthetic or weak-proxy objects with explicit evidence labels.

## Compressed Decision State
`CompressedDecisionState` is the v1 strategy-facing object.
It is not a naked scalar dump; each decision input retains evidence, role, and strength.

## Projection Contract
`Projection<T>` exists even when `value` is `None`.
That represents a typed research object whose value is not currently identified.

For RPC-only:
- `Gamma` may be summarized from local geometry.
- `q_t`, `r_t`, `kappa_t`, `u_t`, `p_t` remain weak proxies or unfilled projections.

## Snapshot Contract
The workspace uses exactly one RPC-only snapshot schema:

- `monad_mev_rpc::AmmSnapshotEnvelope`

`monad-mev-state` must continue to build state from this schema rather than introducing a parallel snapshot carrier.

# monad-amm-rpc Migration Note

`monad-amm-rpc` is no longer maintained as a separate project or duplicated directory.

Its responsibilities have been absorbed into the workspace as:

- `crates/monad-mev-rpc`: RPC client, ABI encoding/decoding, `cpmm/clmm` snapshot logic
- `crates/monad-mev-cli`: `snapshot` and `build-state` user entrypoints
- `data/fixtures/`: canonical snapshot examples
- `docs/architecture/`: current adapter and state contracts

Old names that should no longer appear in active code or docs:

- `monad-amm-rpc`
- `monad-amm-rpc-cli`
- `amm-rpc-core`

The adapter boundary remains, but it is now a crate boundary inside the single workspace.

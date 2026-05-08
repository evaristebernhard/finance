# Upgrade Path

## Next Adapters
1. External price adapter
2. Execution Events adapter
3. Additional AMM family adapters
4. Execution intent adapter
5. Replay and evaluation backends

## Upgrade Rules
- New data surfaces extend adapters and state builders; they do not change canonical primitives.
- New AMM families extend geometry handling in `monad-mev-rpc` and `monad-mev-projection`.
- Strategy may evolve from placeholder policy to Bellman kernels only after stronger state is available.
- Execution may consume `ExecutionIntent` only after replay and evaluation can validate outcomes.
- Historical standalone prototypes should be migrated into workspace crates rather than preserved as parallel projects.

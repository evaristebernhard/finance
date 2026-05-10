# Monad RPC Probe

`rpc.txt` stores Alchemy keys or full RPC URLs, one per line. Use the probe to
check which endpoints can serve Monad mainnet data before starting a larger
collector run:

```bash
scripts/monad_rpc_probe.sh
```

The default table redacts keys and checks:

- `eth_chainId`: expected Monad mainnet chain id is `0x8f`.
- `eth_blockNumber`: confirms the endpoint can read current blocks.
- `eth_getLogs`: confirms the endpoint supports the log path used by the CHOG
  collectors.
- repeated `eth_blockNumber` samples: gives a light latency/success signal.

To pass all currently usable endpoints to an existing collector quickly, use the
cached status file:

```bash
cargo run --manifest-path crate/Cargo.toml --bin chog_collect -- \
  --mode incremental \
  --data-root data/chog/v1 \
  $(scripts/monad_rpc_args.sh)
```

`scripts/monad_rpc_args.sh` does not call the network. It maps the current
`rpc.monad.status.tsv` statuses back to the keys in `rpc.txt`.

Other useful forms:

```bash
scripts/monad_rpc_args.sh --format urls
scripts/monad_rpc_args.sh --format env
scripts/monad_rpc_args.sh --status-file rpc.monad.capacity.tsv --min-blocks 1000 --format urls
scripts/monad_rpc_probe.sh --format csv
scripts/monad_rpc_probe.sh --format status
scripts/monad_rpc_probe.sh --format urls
scripts/monad_rpc_probe.sh --format env
scripts/monad_rpc_probe.sh --samples 10
scripts/monad_rpc_probe.sh --no-logs
```

Refresh the cached status table after adding keys or when endpoint behavior
changes:

```bash
scripts/monad_rpc_probe.sh --format status > rpc.monad.status.tsv
scripts/monad_rpc_probe.sh --format capacity --samples 0 > rpc.monad.capacity.tsv
```

By default the script uses `curl --noproxy '*'`, because this machine currently
has a proxy environment pointing at `192.168.137.1:7890`. Use `--use-proxy` if
that proxy is running and should be used.

## Reading Capacity Signals

Alchemy does not disclose the account plan through a public JSON-RPC call. The
only reliable way to know whether a key belongs to Free, Pay As You Go, or
Enterprise is the owner's Alchemy dashboard. The probe can still classify useful
runtime signals:

- `usable_fast` / `usable`: works for chain, block, and log reads. The plan is
  still unknown.
- `capacity_exceeded`: quota is exhausted. Treat it as a capped app, often a
  free or limited account.
- `rate_limited`: the app is hitting throughput limits. Reduce concurrency or
  rotate more endpoints.
- `network_disabled`: the app exists, but Monad mainnet is not enabled for it.
- `inactive`: the Alchemy app is disabled.

For large CHOG backfills, prefer the usable endpoints with the lowest average
latency, pass several `--rpc-url` values, keep retries enabled, and keep
`--log-range-blocks` conservative enough that `eth_getLogs` does not return huge
payloads.

When a capacity TSV exists, `scripts/monad_rpc_args.sh` can map it back to the
full keys in `rpc.txt` by line number. For the current CHOG backfill, the
1000-block endpoints are the mx and g7 Alchemy apps:

```bash
scripts/monad_rpc_args.sh \
  --status-file rpc.monad.capacity.tsv \
  --min-blocks 1000 \
  --format args
```

## Alchemy Plan Context

As of the current Alchemy docs, Free includes 30M monthly compute units and a
small app limit. Pay As You Go charges by compute units and has higher
throughput; Enterprise is custom. Relevant CHOG collector RPC costs listed by
Alchemy include:

- `eth_chainId`: 0 CU
- `eth_blockNumber`: 10 CU
- `eth_getLogs`: 60 CU
- `eth_getTransactionReceipt`: 20 CU
- `eth_getBlockByNumber`: 20 CU

So log-heavy collection burns quota mainly through `eth_getLogs`, while receipt
hydration adds one `eth_getTransactionReceipt` per transaction.

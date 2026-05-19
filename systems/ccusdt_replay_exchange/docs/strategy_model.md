# Strategy Model

Strategies should not control the exchange clock.

Rigorous replay interaction:

```text
runner clock -> strategy observation -> order intent -> latency queue -> exchange order -> fill/portfolio event
```

The first implemented path is `run toy`, where the runner owns the replay clock
and a deterministic toy strategy emits one entry intent and one exit intent.

HTTP interaction remains useful for manual debugging:

```text
GET /api/state -> strategy decision -> POST /api/orders -> POST /api/step
```

Forbidden interaction:

```text
strategy imports root scripts
strategy reads date/ labels directly
strategy computes available leverage independently
```

The first CCUSDT strategy client should be a small Python prototype under
`strategies/python/ccusdt_tfi_core_idle01/` that reads only exchange state and
pretrade-safe sidecars.

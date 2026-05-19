# Strategy Model

Strategies should run outside the exchange engine.

Allowed interaction:

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


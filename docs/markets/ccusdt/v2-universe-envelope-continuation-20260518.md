# CCUSDT V2 Universe Envelope Continuation

Status: 2026-05-18.

Guardrail: `research_framework_only_no_execution_recommendation_no_alpha_claim`.

This note extends the CCUSDT V2 execution no-go handoff after the first real Bullish multi-symbol data acquisition. It keeps the current objective blocked until a symbol/notional pair can pass execution-envelope gates before alpha mining.

## Decision

The active `>2` bps after-cost objective is still not achieved.

At the original `$100` target notional, the downloaded Bullish universe has `0` pre-alpha liquidity candidates. At smaller top-of-book notional stress, only `BTCUSDC` passes the first envelope:

| target_notional_quote | pre_alpha_candidates | candidate_symbols | interpretation |
| --- | --- | --- | --- |
| 100 | 0 |  | no symbol supports the current target-notional envelope |
| 10 | 1 | `BTCUSDC` | BTC can be considered for symbol-specific modeling only at small notional |
| 5 | 1 | `BTCUSDC` | lower notional does not broaden the candidate set |

This is not an alpha result. It only says BTC top-of-book spread, depth, and activity are sufficient to justify a later BTC-specific research framework if the small notional is economically acceptable.

The first lightweight BTC-specific top-of-book queue-release diagnostic and a broader top-of-book factor smoke were also run after this envelope screen. Both produced `0` promote-gate rows. A gross/cost decomposition of the factor smoke then showed the best gross move is still about `3.42` bps short of fee stress plus the `+2` bps objective, so BTC capacity alone does not yet justify downloading BTC incremental L2.

## Data Acquisition

Small-tier full L2 pilot completed:

```text
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_small_tier_download_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_small_tier_download_v1.csv
```

Result: `255/255` files written under `data/ccusdt_universe/v1/external`, with `153` downloaded non-empty files and `102` empty files. The useful small-tier data is mainly `SUIUSDC` and `DOGEUSDC`; `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC` are metadata-available but effectively empty in this window.

Remaining-tier metadata/Range size probe completed:

```text
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1.json
date/ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_universe_size_probe_remaining_tier_v1.csv
```

Result: `253/255` files available, `2` probe errors, estimated full L2 body size `52.64` GB for `BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT`. The full L2 size is dominated by `BTCUSDC` and `ETHUSDC` incremental books.

Remaining-tier top-of-book/trades download completed:

```text
date/bonk_bullish_l2_download_completion_20260518_ccusdt_v2_remaining_tob_trades_download_v1.json
date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_remaining_tob_trades_download_v1.csv
```

Result: `170/170` files downloaded for `BTCUSDC,ETHUSDC,SOLUSDC,BONK1MUSDC,BONK1MUSDT` across `book_ticker,trades`.

## Envelope Results

Primary `$100` envelope:

```text
date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.csv
docs/markets/ccusdt/v2-universe-liquidity-envelope-20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.md
```

Key rows:

| symbol | dates | median_spread_bps | p05_top_depth_quote | depth_day_rate | failed_gates | status |
| --- | --- | --- | --- | --- | --- | --- |
| BTCUSDC | 17 | 0.0125 | 14.7372 | 0.0000 | depth | depth_no_go |
| ETHUSDC | 17 | 0.0434 | 6.5027 | 0.0000 | depth | depth_no_go |
| SOLUSDC | 17 | 0.0113 | 0.5799 | 0.0000 | depth | depth_no_go |
| BONK1MUSDT | 17 | 1.5146 | 0.4705 | 0.0000 | depth | depth_no_go |
| BONK1MUSDC | 17 | 2.9036 | 1.1329 | 0.0000 | spread,depth | spread_and_depth_no_go |
| DOGEUSDC | 17 | 35.7143 | 3611.5922 | 1.0000 | spread,activity | spread_and_activity_no_go |
| SUIUSDC | 17 | 8.7510 | 19.3180 | 0.0000 | spread,depth,activity | spread_depth_activity_no_go |

Target-notional sensitivity:

```text
date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1.csv
date/ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target5_v1.csv
```

At `$10`, `BTCUSDC` is the only pre-alpha liquidity candidate: median daily median spread `0.0125` bps, median daily p95 spread `0.0127` bps, median daily p05 top-depth `14.7372` quote, and depth support day rate `1.0`. At `$5`, the candidate set is unchanged. `ETHUSDC` improves but still misses the `0.95` depth-support day-rate gate at `$5` with `0.8824`.

## BTC Queue-Release Fast Diagnostic

```text
date/ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv
docs/markets/ccusdt/v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.md
```

This run parameterized the existing top-of-book queue-release pivot to `BTCUSDC`, used the high-release candidate pool (`candidate_prefilter_quantile=0.95`), tested the `0.99` release threshold across `1/5/10s` horizons, applied `2` bps fee stress, and used `50` matched-random iterations as a fast diagnostic.

Result: `18` scorecard rows, `0` promote-gate rows. The best row was `expanding_fold3 / bid_release_short / 10s` with only `53` entries, mean net `-1.7210` bps, median `-1.9752` bps, matched-random probability `0.12`, and promote gate `False`.

## BTC Top-Of-Book Factor Smoke

```text
date/ccusdt_v2_tob_factor_scorecard_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv
docs/markets/ccusdt/v2-tob-factor-framework-20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.md
```

This run built a `1s` BTCUSDC top-of-book/trade panel with `1,468,771` rows, tested `microprice_follow`, `obi_follow`, `trade_flow_follow_5s`, `trade_flow_follow_10s`, and `ret_reversal_5s` at the train-period `0.99` threshold across `1/5/10s` horizons, applied `2` bps fee stress, and used `10` matched-random iterations as a smoke diagnostic.

Result: `45` scorecard rows, `0` promote-gate rows. The best row was `obi_follow / 10s`, with sample pass but mean net still negative at `-1.4181` bps, median `-1.7538` bps, and economics/stress gates false.

## BTC Top-Of-Book Gross/Cost Decomposition

```text
date/ccusdt_v2_tob_factor_decomposition_20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.csv
docs/markets/ccusdt/v2-tob-factor-decomposition-20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.md
```

This run decomposed the BTCUSDC top-of-book factor rows into gross midpoint movement, realized cost pressure, net result, and the gross shortfall to the fee-stress plus `+2` bps hurdle.

Result: `45` rows, `0` promote-gate rows. The best row remained `expanding_fold1 / obi_follow / 10s`: gross mean `0.5944` bps, cost mean `2.0125` bps, net mean `-1.4181` bps, required gross for net `+2` bps `4.0125` bps, and mean gross shortfall `-3.4181` bps.

## Engineering Added

New batch pre-alpha envelope script:

```text
scripts/ccusdt_v2_universe_liquidity_envelope_audit.py
```

It intentionally avoids reading CCUSDT framework, maker, taker, or decomposition scorecards. It only screens local Bullish `book_ticker,trades` by coverage, spread, top-of-book depth, quote-match rate, and trade-arrival notional before any alpha modeling.

Validation:

```powershell
python -m py_compile scripts\ccusdt_v2_universe_liquidity_envelope_audit.py
```

## Valid Next Work

Do not resume CCUSDT TP/SL tuning or fill-aware post-hoc filters.

The next valid branch is either:

1. Treat `$100` target notional as mandatory, and stop this Bullish universe branch because all tested symbols fail the pre-alpha envelope.
2. If `$10` quote notional is economically acceptable, a future branch needs a materially different BTC-specific mechanism; the fast BTC queue-release diagnostic, the first BTC top-of-book factor smoke, and its gross/cost decomposition are all no-go and do not justify downloading `BTCUSDC` incremental L2 by themselves.

Existing V2 framework and L2 queue scripts remain CCUSDT-bound through hardcoded panel paths and `symbol=CCUSDT` raw roots, so a BTC continuation needs parameterization or a new BTC-specific panel builder before the `>2` bps objective can be retested.

# BONK V8 Price And Dynamic Orderbook Plan

Status: planned on 2026-05-13. Canonical input run tag: `20260513_bullish_l2_basket_price_v1`.

This plan is research-only. It will not output trading rules, execution instructions, sizing rules, or alpha claims.

## Goal

Fix the main gap in the current research stack: price sequence factors were treated mostly as background context, while the orderbook factors were too static.

V8 should test classic trailing price factors and dynamic orderbook transitions together:

```text
price event -> book confirmation -> path label -> episode replay
```

The practical goal is lower turnover and cleaner path quality than the V6 static gate replay.

## Inputs

Use existing local data only:

```text
data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
date/bonk_v6_episode_backtest_20260513_bullish_l2_basket_price_v1_*.csv
date/bonk_v7_short_impulse_probe_20260513_bullish_l2_basket_price_v1_*.csv
date/bonk_v7_dynamic_context_*_20260513_bullish_l2_basket_price_v1.*
```

No options data. No full `incremental_book_L2` basket. A small BONK-only incremental L2 sample can be a later follow-up if V8 finds a shape worth reconstructing.

## Classic Price Factors

Compute trailing-only features from Binance 1m context:

- Momentum: `ret_2m`, `ret_5m`, `ret_10m`, `ret_20m`, `ret_30m`, `ret_60m`, `ret_240m`.
- Reversal: negative of the same returns, plus overextension flags after large one-sided moves.
- Volatility: realized volatility `5m/15m/60m/240m`, vol ratio, vol acceleration, quiet-to-active transitions.
- Breakout: close position versus rolling high/low over `15m/60m/240m`, range expansion, distance from breakout.
- Volume: quote-volume surprise versus rolling median/IQR, trade-count surprise, volume-price confirmation.
- Relative strength: BONK minus BTC/ETH/SOL, meme basket, alt basket over `5m/15m/60m/240m`.
- Lead-lag: BTC/SOL/meme move first, BONK lag/catch-up pressure next.
- Resonance: sign agreement and correlation-weighted alignment with SOL and meme names.

## Dynamic L2 Factors

Compute transition features from Bullish 1m L2 state:

- Ask withdrawal: ask depth falls over `1m/2m/5m` while bid depth stays stable or improves.
- Bid withdrawal: bearish mirror for control and possible short-side diagnostics.
- Bid replenish: bid depth rises after or during a positive price impulse.
- Spread compression: spread narrows after prior wide/liquidity-stressed state.
- Microprice impulse: microprice offset moves in the same direction as price.
- WOBI impulse: `wobi5`, `wobi25`, and `wobi5_minus_wobi25` changes.
- Trade burst: trade notional and reported-flow burst.
- Cross-venue disagreement: USDC/USDT spread, basis, activity ratio, and microprice disagreement.

The point is to test book history:

```text
depth_t - depth_{t-k}
spread_t - spread_{t-k}
microprice_t - microprice_{t-k}
price_t - price_{t-k}
```

Static depth alone is not enough.

## Labels

Use short path labels and returns:

- Close-to-close diagnostics: `2m/5m/10m/20m/30m/60m`.
- First-passage labels: `5m/10m/20m/30m` with `20/30/50/75/100bps` barriers.
- Episode replay: open after signal confirmation, exit on gate off, TP, SL, timeout, data gap, or fold end.

Same-minute TP/SL ambiguity should stay worst-case.

## Validation

Use purged walk-forward splits already used by the panel:

```text
fold1 validate 2026-05-03 12:00..2026-05-05 23:59
fold2 validate 2026-05-06 12:00..2026-05-08 23:59
fold3 validate 2026-05-09 12:00..2026-05-12 11:59
```

All thresholds, buckets, scalers, winsor limits, and gate cuts must be fit on train only and applied to validation.

## Outputs

Proposed outputs:

```text
date/bonk_v8_price_factor_audit_20260513_bullish_l2_basket_price_v1_factor_tests.csv
date/bonk_v8_price_factor_audit_20260513_bullish_l2_basket_price_v1_leadlag.csv
date/bonk_v8_price_factor_audit_20260513_bullish_l2_basket_price_v1_gate_candidates.csv
date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_trades.csv
date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_daily.csv
date/bonk_v8_episode_backtest_20260513_bullish_l2_basket_price_v1_summary.csv
docs/markets/bonk/v1-cex-v8-price-orderbook-report.md
```

## Acceptance Read

A V8 candidate is interesting only if it improves the practical failure mode seen in V6:

- fewer trades, ideally low single digits per day rather than dozens;
- better maker-light and taker-spread rows, not just `mid_research`;
- fold2 and fold3 both not obviously bad;
- no dependence on one symbol unless explicitly reported as venue-specific;
- path width and stop-side behavior are visible, not hidden behind mean return;
- price-only, L2-only, and price-plus-L2 views are reported separately.

If price-only explains most of the signal, L2 becomes an execution/liquidity filter. If L2 improves path quality after price controls, then orderbook dynamics deserve a Rust implementation and possibly a small `incremental_book_L2` BONK sample.

# BONK CEX Current State

Status: 2026-05-13. Canonical run tag: `20260513_bullish_l2_basket_price_v1`.

This memo is research-only. It is not a trading rule, execution instruction, sizing rule, or alpha claim.

## What Exists

The current local data stack is usable for a first real research loop:

- Bullish minute L2 state for BONK plus the research basket.
- BONK path labels for `BONK1MUSDC` and `BONK1MUSDT`.
- Bullish basket covariance/common-mode features.
- Binance spot 1m kline context for BONK, BTC, ETH, SOL, meme names, and alt controls.
- A joined L2/label/context panel for controlled tests and modeling probes.
- V6 episode replay outputs for a fixed `$100` notional account.
- V7 dynamic orderbook and dynamic context probes.

The active derived files are:

```text
data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

## What The Earlier Work Says

The original static regime read found a BONK1MUSDT H4 object around:

```text
depth_high + rv_low
depth_high + rv_low + cv_spread
```

That object is not fake in the obvious sense: label checks, missing-minute checks, and several negative controls did not fully erase it. But it behaves more like a regime filter than a complete trading state. When converted into V6 episodes, it overtrades badly:

- `mid_research` is positive only as an upper bound.
- `maker_light`, `taker_spread`, and `wide_stress` are negative in the main grid.
- Gate flicker creates too many short-lived entries.
- Costs dominate because the signal is not selective enough.

So the current conclusion is:

```text
Static L2 regime has shape, but not enough executable selectivity.
```

## What Was Underused

The price sequence was previously used mainly as context and controls. That is not enough. It should also be tested as an independent factor layer:

- short momentum and reversal;
- volatility compression and expansion;
- range breakout and range position;
- volume/quote-volume surprise;
- relative strength versus BTC/ETH/SOL, meme basket, and alt basket;
- lead-lag catch-up after BTC/SOL/meme moves;
- resonance between BONK and the meme/SOL complex.

This matters because a price-only event can define the impulse, while the orderbook decides whether that impulse is tradable or too expensive.

## What Looks More Promising

The V7 probes point toward dynamic events instead of static snapshots:

```text
ask withdrawal + bid support
spread compression + microprice impulse
trade notional burst
market/meme/SOL acceleration + BONK catch-up
cross-venue disagreement + local book impulse
```

These are closer to the actual orderbook idea: liquidity changes over the last `1m/2m/5m`, then price confirms or rejects the move.

## Immediate Research Question

The next pass should test:

```text
Can classic price events plus dynamic L2 transitions reduce trade frequency
and improve 5m/10m/20m/30m path quality after realistic cost stress?
```

That is the V8 task. The target is not to maximize raw bucket edge. The target is to find fewer, cleaner episodes with:

- train-only thresholds;
- validation-only episode replay;
- maker-light and taker-spread stress;
- explicit debounce, minimum hold, exit debounce, and cooldown controls;
- separate `BONK1MUSDC` and `BONK1MUSDT` reporting.

## Open Caveats

- The window is short: `2026-04-29..2026-05-12`.
- Bullish trade side semantics are still treated as exchange-reported side, not confirmed taker buy/sell.
- `incremental_book_L2` has not been used for canonical reconstruction.
- The current price context is Binance spot 1m; it is useful context, not a guarantee of executable Bullish fills.
- Any positive short-window result remains a candidate for next-window validation, not an alpha claim.

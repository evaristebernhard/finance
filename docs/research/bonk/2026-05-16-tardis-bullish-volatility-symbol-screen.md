# Tardis Bullish Volatility Symbol Screen

Status: 2026-05-16. This is a symbol-selection screen for short-horizon factor research. It is not a trading rule or execution recommendation.

## Thesis

The recent BONK short-horizon factor failures may be less about directional prediction and more about the instrument envelope:

```text
short-horizon factor edge must fit inside volatility - spread - fee - tick/price-scale constraints
```

BONK on Bullish is quoted as `BONK1M`. Its daily volatility is not low, but the price scale is high for a meme-style unit: around `6.96`, so a 1% move is roughly `0.07` quote units. This can make the UI/replay feel like a large, blunt instrument for short-horizon factor work.

## Method

Data source:

```text
Tardis downloadable Bullish book_ticker
```

Screen dates:

```text
2026-05-12
2026-05-13
2026-05-14
2026-05-15
```

Metrics:

- `rv_1m_pct`: daily realized volatility from one-minute last-mid log returns.
- `range_pct`: daily `max(mid) / min(mid) - 1`.
- `median_spread_bps`: median `ask - bid` over mid.
- `one_pct_value`: average mid price times `1%`, used as a price-scale proxy.

Outputs:

```text
date/tardis_bullish_volatility_fast_20260516_bullish_vol_screen_v1.csv
date/tardis_bullish_volatility_summary_20260516_bullish_vol_screen_v1.csv
```

## Shortlist

Primary candidates that better match short-horizon factor research:

| Symbol | Read | Avg 1m RV | Avg Range | Median Spread | Avg Mid | 1% Value |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `CCUSDT` | Best clean high-vol screen: high RV/range, low spread, low price scale. | 4.64% | 8.22% | 1.9 bps | 0.159386 | 0.001594 |
| `ETHFIUSDC` | Strong RV/range, moderate spread, manageable price scale. | 4.74% | 8.50% | 4.4 bps | 0.445272 | 0.004453 |
| `SUIUSDC` | Highest RV in the clean group, but spread is near 10 bps. | 4.90% | 7.77% | 9.8 bps | 1.209810 | 0.012098 |
| `IOTAUSDT` | Good low-price candidate with decent RV/range and tolerable spread. | 3.57% | 7.75% | 5.0 bps | 0.061745 | 0.000617 |
| `NIGHTUSDT` | Low price and strong range, but spread is wider. | 3.21% | 7.73% | 8.2 bps | 0.033410 | 0.000334 |
| `VTHOUSDT` | Tiny price scale and acceptable spread, but RV is lower. | 2.34% | 6.48% | 1.7 bps | 0.000587 | 0.000006 |
| `VETUSDT` | Very clean spread and tiny price scale, but lower RV. | 2.06% | 5.78% | 0.1 bps | 0.007392 | 0.000074 |

High-vol but cost-warning candidates:

| Symbol | Read | Avg 1m RV | Avg Range | Median Spread | Avg Mid | 1% Value |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `PENGUUSDT` | Excellent movement, but spread is already a serious hurdle. | 4.85% | 7.62% | 16.9 bps | 0.009301 | 0.000093 |
| `CHZUSDT` | High RV, but spread is too wide for first-pass short-horizon work. | 5.20% | 7.82% | 21.0 bps | 0.043875 | 0.000439 |
| `ENSUSDC` | High movement, but price scale resembles BONK1M and spread is wide. | 4.58% | 8.68% | 20.9 bps | 6.993400 | 0.069934 |

Control / comparison candidates:

| Symbol | Read | Avg 1m RV | Avg Range | Median Spread | Avg Mid | 1% Value |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `BONK1MUSDT` | Current baseline: decent volatility and tight spread, but large price scale. | 3.74% | 7.86% | 1.5 bps | 6.956280 | 0.069563 |
| `BONK1MUSDC` | Same issue as USDT pair, with slightly wider spread. | 3.68% | 7.88% | 2.8 bps | 6.963510 | 0.069635 |
| `SOLUSDC` | Liquid benchmark: tight spread, but too high price scale and lower movement. | 2.54% | 4.91% | 0.0 bps | 92.699800 | 0.926998 |
| `XRPUSDC` | Liquid mid-price benchmark with moderate movement. | 2.54% | 5.81% | 0.7 bps | 1.453880 | 0.014539 |

## Interpretation

The better next research basket is not simply "highest volatility." It should prefer:

```text
high realized/range volatility
low or moderate median spread
small enough price scale that short moves are not mechanically blunt
enough book_ticker coverage for event-time factor panels
```

First-pass basket:

```text
CCUSDT
ETHFIUSDC
SUIUSDC
IOTAUSDT
NIGHTUSDT
VTHOUSDT
VETUSDT
```

Keep `BONK1MUSDT` and `BONK1MUSDC` only as controls. Keep `PENGUUSDT` and `CHZUSDT` as high-volatility stress candidates, but do not start there unless the next analysis explicitly models spread/cost.

## Next Step

Build a small candidate-factor panel from `book_ticker` plus trades for the first-pass basket. The initial objective should be to test whether short-horizon factor diagnostics improve when the instrument has better volatility/scale geometry, not to optimize a trading rule.

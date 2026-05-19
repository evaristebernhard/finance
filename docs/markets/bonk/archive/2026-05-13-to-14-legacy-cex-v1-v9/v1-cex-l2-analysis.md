# BONK Bullish L2 Basket 第一版数据分析

状态: 2026-05-13。本文基于 Rust run tag `20260513_bullish_l2_basket_price_v1`，只评价数据质量、盘口现象和稳定性入口，不输出交易规则，也不声称 alpha。

## 结论摘要

- BONK 第一版 Bullish L2 + Binance spot kline 背景层已经可用。L2 窗口为 `2026-04-29..2026-05-12`，path labels 只覆盖 `BONK1MUSDC` 与 `BONK1MUSDT`。
- Binance spot kline context 覆盖 13 个 symbols，每个 20,160 根 1m bar，`PENGUUSDT` 可用，`missing_minutes=0`。
- BONK 在该窗口相对 BTC/ETH/SOL market basket、meme basket、SOL 都是正相对收益，但这只说明研究窗口处在 BONK 较强的 market state，不构成交易规则。
- Bullish 上 `BONK1MUSDT` 中位 spread 更窄，`BONK1MUSDC` 成交笔数和成交名义额更大。两者更像同一资产的不同流动性切面，而不是可以直接互相替代的单一盘口。
- 因子诊断里，1h 的 activity/count 类变量在 BONK1MUSDC 更突出；4h/12h 的 spread 类变量在 BONK1MUSDT 更突出。但 forward split 和 placebo shift 显示部分信号可能混有行情阶段效应，不能直接上升为策略。

## 数据与覆盖

最新报告和产物:

```text
docs/markets/bonk/v1-cex-l2-report.md
data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_covariance_state/bonk_cex_covariance_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_path_labels/bonk_path_labels_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet
date/bonk_v1_cex_l2_factor_tests_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_cex_l2_stability_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v1_cex_price_context_summary_20260513_bullish_l2_basket_price_v1.csv
```

L2 quality:

| item | value |
| --- | ---: |
| L2 state rows | 159,282 |
| covariance rows | 20,140 |
| path label rows | 482,760 |
| raw quality rows | 462 |
| raw ok files | 378 |
| raw empty files | 84 |
| raw error files | 0 |

The 84 empty raw files are expected in the current Bullish basket: `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC` have empty snapshot/trade segments for part of the window. BONK files have no timestamp monotonic violations, duplicate rows, empty price rows, negative amount rows, or abnormal spread rows.

BONK label summary:

| symbol | state rows | raw rows | median spread bps | trades | trade notional quote | valid label rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDC | 20,103 | 3,334,900 | 2.74 | 388,533 | 48,833,565 | 19,353 |
| BONK1MUSDT | 20,127 | 3,758,343 | 1.59 | 45,839 | 10,430,770 | 19,405 |

Interpretation: USDT has the tighter displayed top-of-book spread, while USDC has much heavier realized trade activity in this Bullish window. Any comparison between the two must keep venue/liquidity mode separate.

## Kline Price Context

The kline context uses Binance public spot 1m data as market-state background. It is not a CEX L2 source and is not used as a trading rule.

| symbol | rows | total return bps | median 1h RV bps | quote volume |
| --- | ---: | ---: | ---: | ---: |
| SUIUSDT | 20,160 | 2,922 | 60.02 | 898,141,647 |
| OPUSDT | 20,160 | 2,271 | 77.73 | 92,267,045 |
| WIFUSDT | 20,160 | 2,108 | 226.88 | 94,955,977 |
| BONKUSDT | 20,160 | 1,279 | 95.02 | 101,239,212 |
| SOLUSDT | 20,160 | 1,149 | 40.19 | 2,972,116,458 |
| DOGEUSDT | 20,160 | 1,037 | 53.86 | 1,687,668,149 |
| BTCUSDT | 20,160 | 534 | 26.30 | 15,806,361,716 |
| ETHUSDT | 20,160 | -59 | 34.22 | 9,575,675,756 |
| PENGUUSDT | 20,160 | -664 | 91.39 | 363,187,375 |

Window-level relative context:

| context | coverage | basket return bps | BONK relative bps |
| --- | ---: | ---: | ---: |
| BTC/ETH/SOL market | 100% | 541 | 738 |
| meme basket | 100% | 1,066 | 213 |
| SOL | 100% | 1,149 | 130 |

Interpretation: BONK was strong even after controlling for broad market, meme basket, and SOL in this short window. That makes L2 continuation diagnostics more interesting, but also raises the risk that positive labels are partly a window regime artifact.

## L2 Factor Diagnostics

The factor tests use first-passage labels with horizons `1h,4h,12h` and barriers `50,100,200,300` bps. The comments below focus on high buckets at the 100 bps barrier.

| symbol | horizon | strongest high-bucket diagnostics | reading |
| --- | --- | --- | --- |
| BONK1MUSDC | 1h | `snapshot_count` edge +7.7%, `trade_count` edge +7.3%, `book_ticker_count` edge +4.1% | Activity and quote update intensity align with short-horizon continuation in this sample. |
| BONK1MUSDC | 4h | `snapshot_count` edge +3.4%, `trade_count` edge +3.2%, `trade_notional_quote_sum` edge +2.5% | The same activity family survives to 4h but with smaller edge. |
| BONK1MUSDC | 12h | `spread_bps_median` edge +4.9%, `spread_bps_last` edge +4.0% | Wider-spread regimes align with longer path movement, but this may be volatility/state rather than directional signal. |
| BONK1MUSDT | 1h | `snapshot_count` edge +5.0%, `book_ticker_count` edge +3.4% | Quote activity is visible, but weaker than USDC. |
| BONK1MUSDT | 4h | `spread_bps_median` edge +5.1%, `spread_bps_last` edge +4.7% | Spread state is the cleanest USDT 4h diagnostic. |
| BONK1MUSDT | 12h | `spread_bps_median` edge +8.6%, `spread_bps_last` edge +7.2% | Strongest raw diagnostic, but also most exposed to overlapping labels and market-state confounding. |

Practical reading: activity/count features look more like short-horizon participation or attention state; spread features look more like volatility/liquidity regime. The current evidence is better framed as a state classifier for future path width and direction balance, not as an execution rule.

## Stability Checks

The stability CSV includes `non_overlap`, `placebo_shift`, `forward_split`, and `barrier_sensitivity`.

Important caveats:

- Forward split is uneven for several 1h activity diagnostics. For example, BONK1MUSDC `snapshot_count` high bucket is much stronger in the second half than first half.
- Placebo shift often remains non-trivial for activity factors, which suggests slow regime persistence or confounding. That is useful, but it weakens any claim that the exact minute-level feature is causal.
- Non-overlap samples are small at 12h because two weeks only gives a small number of independent 12h strides.
- Spread diagnostics are plausibly measuring volatility/liquidity state. They should be tested against kline volatility controls before being interpreted directionally.

The first-pass conclusion is therefore conservative: BONK L2 contains visible state information, but the current two-week window is not enough to claim a stable tradable edge.

## Limits And Next Steps

Known limits:

- Window is short: 14 calendar days.
- First-passage labels overlap heavily before non-overlap filtering.
- Bullish `trades.side` is kept as exchange-reported side. It is not asserted to be taker buy/sell.
- `incremental_book_L2` was not used, so there is no strict queue-level reconstruction or strict OFI.
- Binance spot kline context is cross-exchange background, not Bullish executable context.
- APT/ARB/OP are present in Binance kline context but not in the current Bullish L2 state output.

Next research steps:

- Add market-state controls to factor tests: BONK relative return, meme basket return, SOL return, realized volatility, and rolling beta/correlation buckets.
- Split factor diagnostics by BONK1MUSDC vs BONK1MUSDT venue state before aggregating.
- Confirm Bullish trade side semantics before naming trade flow as taker buy/sell.
- Add volatility-adjusted barriers after the fixed 50/100/200/300 bps checks.
- Keep `incremental_book_L2` out of scope until strict OFI or queue reconstruction becomes necessary.

# BONK V3 Cross-Section Placebo Analysis

Status: 2026-05-13. This is a research-only cross-sectional placebo check for the hand-built BONK H4 depth/liquidity + low-RV gates. It is not a trading rule or an alpha claim.

## Inputs And Outputs

Inputs:

```text
data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date/bonk_v3_cross_section_placebo_gate_summary.csv
date/bonk_v3_cross_section_placebo_gate_fold_summary.csv
date/bonk_v3_cross_section_placebo_symbol_coverage.csv
date/bonk_v3_cross_section_placebo_summary.json
```

## Method

- Primary test: H4 `depth_high+rv_low`, where `depth_high` is the top tertile of available L2 top depth and `rv_low` is the bottom tertile of symbol 1h realized volatility.
- Thresholds are fit on each fold's train-side history and applied to that fold's validation window.
- Non-BONK symbols do not have first-passage path labels here, so outcomes are simple close-to-close future returns from the price-context parquet.
- Common-mode checks subtract timestamp-aligned future baskets: BTC/ETH/SOL market, meme basket, BTC/ETH, and SOL.
- Sparse L2 symbols are kept for audit but marked `sparse_l2_or_outcomes` or `sparse_gate_rows`.

## Executive Read

Primary read: `bonk_more_special_than_placebos`.

The H4 depth-high + low-RV state is not unique as a raw liquidity/quiet-volatility condition: full-coverage placebos also show positive raw upper-minus-lower rates. But BONK is the only full-coverage target in this run whose primary gate remains positive versus the meme basket, so the current evidence leans BONK-specific relative strength rather than pure meme/common-mode.

The strongest raw non-BONK placebo is `DOGEUSDC` with upper-minus-lower `9.7%` and median H4 return `12.8 bps`. The strongest non-BONK relative-meme row is `BTCUSDC` at `-0.3 bps`. PEPE/SHIB/WIF cannot be treated as strong placebos in this run because their L2 state has only a tiny number of rows.

## Primary H4 Gate Comparison

| symbol | status | gate rows | share | upper-lower | median ret bps | rel market bps | rel meme bps | positive folds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BONK1MUSDT | ok | 1318 | 11.5% | 9.0% | 23.5 | 14.4 | 8.8 | 2/3 |
| BONK1MUSDC | ok | 1218 | 10.6% | 4.3% | 17.2 | 9.5 | 2.2 | 2/3 |
| BTCUSDC | ok | 1943 | 16.9% | 2.4% | 10.0 | 6.3 | -0.3 | 2/3 |
| ETHUSDC | ok | 1704 | 14.8% | 0.5% | 3.1 | -8.9 | -13.8 | 1/3 |
| DOGEUSDC | ok | 872 | 8.1% | 9.7% | 12.8 | 3.8 | -13.9 | 1/3 |
| SOLUSDC | ok | 796 | 6.9% | 6.2% | 20.7 | 0.9 | -16.4 | 2/3 |
| PEPE1MUSDC | sparse_gate_rows | 0 | n/a | n/a | n/a | n/a | n/a | 0/3 |
| SHIB1MUSDC | sparse_gate_rows | 0 | n/a | n/a | n/a | n/a | n/a | 0/3 |
| WIFUSDC | sparse_gate_rows | 0 | n/a | n/a | n/a | n/a | n/a | 0/3 |

## Coverage

| L2 symbol | price symbol | outcome rows | status | median depth | median 1h RV bps |
| --- | --- | ---: | --- | ---: | ---: |
| BONK1MUSDC | BONKUSDT | 19863 | ok | 95.6 | 95.0 |
| BONK1MUSDT | BONKUSDT | 19887 | ok | 112.0 | 95.0 |
| BTCUSDC | BTCUSDT | 19890 | ok | 2127.0 | 26.3 |
| DOGEUSDC | DOGEUSDT | 18765 | ok | 21141.5 | 54.9 |
| ETHUSDC | ETHUSDT | 19889 | ok | 660.8 | 34.2 |
| PEPE1MUSDC | PEPEUSDT | 76 | sparse_l2_or_outcomes | n/a | 157.8 |
| SHIB1MUSDC | SHIBUSDT | 76 | sparse_l2_or_outcomes | n/a | 97.6 |
| SOLUSDC | SOLUSDT | 19878 | ok | 18.0 | 40.2 |
| WIFUSDC | WIFUSDT | 76 | sparse_l2_or_outcomes | n/a | 267.2 |

## Bottom Line

BONK looks more special than the available placebos after meme-basket adjustment, but the state itself is not exclusive to BONK. Keep the gate as a BONK-priority validation candidate and keep the market-wide liquidity-state caveat attached.

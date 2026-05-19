# BONK CEX V5 Micro-Capital Capacity

Status: 2026-05-13T14:05:50Z. Research diagnostic only: no trading advice, no execution plan, no sizing rule, and no alpha claim.

## Inputs And Outputs

Inputs:

```text
date/bonk_v4_orderbook_capacity_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v4_orderbook_capacity_20260513_bullish_l2_basket_price_v1.json
date/bonk_v4_short_horizon_orderbook_20260513_bullish_l2_basket_price_v1_factor_ranking.csv
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date/bonk_v5_micro_capital_capacity_20260513_bullish_l2_basket_price_v1_stress.csv
date/bonk_v5_micro_capital_capacity_20260513_bullish_l2_basket_price_v1_summary.csv
date/bonk_v5_micro_capital_capacity_20260513_bullish_l2_basket_price_v1.json
docs/markets/bonk/v1-cex-v5-micro-capital-capacity.md
```

- Panel metadata rows: `482760`.

## Method

- Account lens is `100` quote units, with stressed child orders `5,10,25,50,100`.
- The analysis reuses V4 capacity rows, so depth is side-conservative `min(bid, ask)` for top, 5-level, and 25-level displayed notional.
- Cost assumptions inherit V4: `['spread_only', 'depth_base', 'wide_stress']` with round-trip fee stress from the V4 file plus spread/slippage variants. The headline tables use `wide_stress`.
- A micro order is marked `micro_capacity_ok` only when displayed-depth coverage is at least 90%, p90 participation is at most 10%, and median stress-net return is positive.
- `thin_positive_median` means the median is still positive but p25 net is negative. This is not a green light; it means path risk remains visible.
- Lower-first and drawdown columns are kept beside capacity because a small order can fit displayed depth while still having poor path behavior.

## H4 Active $100 Stress

| gate | depth | $100 cover | $100 p90 part | cost bps | med net | p25 net | lower | dd med | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4_usdt_depth_rv | top | 2.6% | 88.31% | 10.41 | 17.31 | -19.11 | 27.3% | 61.02 | display_depth_fail |
| h4_usdt_depth_rv | depth_5 | 98.1% | 15.98% | 4.68 | 28.53 | -49.39 | 27.3% | 61.02 | crowded_depth |
| h4_usdt_depth_rv | depth_25 | 100.0% | 1.29% | 4.43 | 28.12 | -49.56 | 27.3% | 61.02 | thin_positive_median |
| h4_usdt_depth_rv_cv | top | 4.6% | 88.31% | 10.41 | 17.31 | -19.11 | 25.7% | 57.48 | display_depth_fail |
| h4_usdt_depth_rv_cv | depth_5 | 98.7% | 13.74% | 6.55 | 39.55 | -28.56 | 25.7% | 57.48 | crowded_depth |
| h4_usdt_depth_rv_cv | depth_25 | 100.0% | 1.31% | 6.20 | 39.58 | -30.08 | 25.7% | 57.48 | thin_positive_median |

The H4 active gates are not top-of-book strategies under this diagnostic. At `$100`, top-book coverage is only a small fraction of selected rows. Five-level depth usually covers the order, but `$100` pushes p90 participation above the 10% guardrail. Twenty-five-level displayed depth covers `$100` easily, with p90 participation near 1.3%, but p25 net remains negative and lower-first rates are still about one quarter of selected paths.

## H4 Micro Ladder

| scope | gate | depth | max depth pass | $5 | $25 | $50 | $100 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| h4_active | h4_usdt_depth_rv | top | $0 | display_depth_fail | display_depth_fail | display_depth_fail | display_depth_fail |
| h4_active | h4_usdt_depth_rv | depth_5 | $50 | thin_positive_median | thin_positive_median | thin_positive_median | crowded_depth |
| h4_active | h4_usdt_depth_rv | depth_25 | $100 | thin_positive_median | thin_positive_median | thin_positive_median | thin_positive_median |
| h4_active | h4_usdt_depth_rv_cv | top | $0 | display_depth_fail | display_depth_fail | display_depth_fail | display_depth_fail |
| h4_active | h4_usdt_depth_rv_cv | depth_5 | $50 | thin_positive_median | thin_positive_median | thin_positive_median | crowded_depth |
| h4_active | h4_usdt_depth_rv_cv | depth_25 | $100 | thin_positive_median | thin_positive_median | thin_positive_median | thin_positive_median |
| h4_mirror | h4_usdc_depth_rv_cv_mirror | top | $0 | display_depth_fail | display_depth_fail | display_depth_fail | display_depth_fail |
| h4_mirror | h4_usdc_depth_rv_cv_mirror | depth_5 | $50 | thin_positive_median | thin_positive_median | thin_positive_median | crowded_depth |
| h4_mirror | h4_usdc_depth_rv_cv_mirror | depth_25 | $100 | thin_positive_median | thin_positive_median | thin_positive_median | thin_positive_median |
| h4_mirror | h4_usdc_depth_rv_mirror | top | $0 | display_depth_fail | display_depth_fail | display_depth_fail | display_depth_fail |
| h4_mirror | h4_usdc_depth_rv_mirror | depth_5 | $50 | thin_positive_median | thin_positive_median | thin_positive_median | crowded_depth |
| h4_mirror | h4_usdc_depth_rv_mirror | depth_25 | $100 | thin_positive_median | thin_positive_median | thin_positive_median | thin_positive_median |

The ladder says what survives the mechanical displayed-depth checks, not what should be traded. For the active USDT H4 gates, `$50` is the cleaner five-level ceiling under `wide_stress`; `$100` only looks small when the 25-level book is counted.

## Short-Horizon Candidates

Twenty-five-level `wide_stress`:

| gate | rows | $100 cover | $100 p90 part | med net | p25 net | lower | dd med | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| short_spread_high_BONK1MUSDC_30m_20bps | 450 | 100.0% | 2.87% | 9.16 | -15.69 | 40.2% | 16.05 | thin_positive_median |
| short_spread_high_BONK1MUSDC_30m_30bps | 450 | 100.0% | 2.87% | 9.16 | -15.69 | 25.6% | 16.05 | thin_positive_median |
| short_depth_rv_cv_BONK1MUSDC_30m_20bps | 394 | 100.0% | 1.30% | 0.88 | -24.15 | 37.1% | 15.22 | thin_positive_median |
| short_depth_rv_cv_BONK1MUSDC_30m_30bps | 394 | 100.0% | 1.30% | 0.88 | -24.15 | 25.6% | 15.22 | thin_positive_median |
| short_depth_rv_cv_BONK1MUSDT_30m_20bps | 677 | 100.0% | 1.31% | 0.36 | -24.60 | 38.3% | 16.15 | thin_positive_median |
| short_depth_rv_cv_BONK1MUSDT_30m_30bps | 677 | 100.0% | 1.31% | 0.36 | -24.60 | 25.4% | 16.15 | thin_positive_median |

Five-level `wide_stress`:

| gate | max depth pass | $100 cover | $100 p90 part | med net | read |
| --- | --- | --- | --- | --- | --- |
| short_depth_rv_cv_BONK1MUSDC_30m_20bps | $50 | 99.0% | 13.62% | 1.51 | crowded_depth |
| short_depth_rv_cv_BONK1MUSDC_30m_30bps | $50 | 99.0% | 13.62% | 1.51 | crowded_depth |
| short_depth_rv_cv_BONK1MUSDT_30m_20bps | $50 | 98.7% | 13.73% | 0.81 | crowded_depth |
| short_depth_rv_cv_BONK1MUSDT_30m_30bps | $50 | 98.7% | 13.73% | 0.81 | crowded_depth |
| short_spread_high_BONK1MUSDC_30m_20bps | $10 | 92.2% | 22.73% | 8.07 | crowded_depth |
| short_spread_high_BONK1MUSDC_30m_30bps | $10 | 92.2% | 22.73% | 8.07 | crowded_depth |

Short-horizon candidates are more fragile than the H4 gates. Some have `$100` 25-level coverage, but median net is measured in single-digit bps and p25 net stays negative. At five levels, `$100` often becomes crowded, especially for the USDC spread-high candidate.

## V4 Ranking Context

| gate | factor | rows | dir edge | resid med | score |
| --- | --- | --- | --- | --- | --- |
| short_spread_high_BONK1MUSDC_30m_20bps | spread_bps_last | 440 | 14.3% | 8.18 | 0.58 |
| short_spread_high_BONK1MUSDC_30m_30bps | spread_bps_last | 440 | 10.2% | 8.18 | 0.54 |

The strongest V4 short-horizon rows remain state diagnostics. The V5 read does not promote them into executable signals; it only asks whether small quote orders are mechanically tiny relative to displayed depth.

## What $100 Means

- `$5`, `$10`, and `$25` are micro orders against the 25-level book and usually negligible by p90 participation.
- `$50` is still modest for H4 five-level depth, but short-horizon five-level stress is mixed.
- `$100` equals the whole assumed account. It is small relative to 25-level displayed capacity, but too large to reason about from top-of-book and often too crowded for five-level stress.
- Across all focused gates, `$100` passes the 25-level displayed-depth and median-net checks in `10` of `10` `wide_stress` rows, and all of those are `thin_positive_median` because p25 net is negative.
- Displayed capacity is not realized liquidity. Queue position, hidden liquidity, partial fills, latency, cancel/repost behavior, and market impact outside the snapshot are not modeled here.

## Bottom Line

For a `100` quote account, the mechanical capacity problem is not the 25-level displayed book. The binding constraints are top-of-book fragility, five-level crowding at `$100`, small short-horizon net edge, and persistent lower-first/drawdown risk. Treat `$100` as a full-account stress test, not as a capacity recommendation.

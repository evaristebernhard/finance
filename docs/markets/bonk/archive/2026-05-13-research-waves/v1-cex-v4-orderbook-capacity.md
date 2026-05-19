# BONK CEX V4 Orderbook Capacity Diagnostics

Status: 2026-05-13. This is a displayed-depth execution/capacity refinement over the existing BONK L2 state and path labels. It is not a trading rule, not an execution plan, not a sizing rule, and not an alpha claim.

## Inputs And Outputs

Inputs:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date/bonk_v4_orderbook_capacity_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v4_orderbook_capacity_20260513_bullish_l2_basket_price_v1.json
```

## Method

- H4 rows use the frozen active BONK1MUSDT gates `depth_high + rv_low` and `depth_high + rv_low + cv_spread`; USDC mirrors are included for venue comparison.
- Short-horizon rows use exact 5m/15m/30m endpoint labels at 20/30 bps and orderbook candidates: depth high, spread high, and the H4 state projected onto short labels.
- Gate thresholds are fit on each fold's train side, then applied to validation rows. No threshold is reselected on validation data.
- Depth is side-conservative: `min(bid_depth, ask_depth)` for top, 5-level, and 25-level notional when those columns exist.
- Quote buckets are `5,10,25,50,100,250,500,1000`. A bucket is counted only when displayed depth covers it.
- Scenarios subtract round-trip fee stress of `2` bps plus spread/slippage variants: `spread_only`, `depth_light`, `depth_base`, and `wide_stress`.
- Capacity envelope means the largest quote bucket with at least 90% displayed-depth coverage, positive median net, and p90 displayed-depth participation no higher than 10% under the named depth/scenario. It is a diagnostic ceiling, not a proposed trade size.

## H4 Capacity Envelope

| gate | rows | share | gross med | lower | dd med | top env | d5 env | d25 stress env | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h4_usdt_depth_rv | 1215 | 10.6% | 32.8 | 27.3% | 61.0 | 0.0 | 50.0 | 500.0 | capacity_research_ok |
| h4_usdt_depth_rv_cv | 676 | 5.9% | 45.6 | 25.7% | 57.5 | 0.0 | 50.0 | 500.0 | capacity_research_ok |
| h4_usdc_depth_rv_mirror | 1112 | 9.7% | 23.2 | 29.7% | 67.3 | 0.0 | 50.0 | 500.0 | capacity_research_ok |
| h4_usdc_depth_rv_cv_mirror | 393 | 3.4% | 43.2 | 24.2% | 60.5 | 0.0 | 50.0 | 500.0 | capacity_research_ok |

The H4 active USDT gates still look capacity-limited even when the 25-level book is used. Top-of-book capacity is tiny; the usable diagnostic envelope mostly comes from 5/25 levels and remains sensitive to lower-first and drawdown path risk.

## Short-Horizon Candidates

| gate | rows | gross med | lower | dd med | d25 stress env | status |
| --- | --- | --- | --- | --- | --- | --- |
| short_depth_rv_cv_BONK1MUSDT_30m_20bps | 677 | 6.2 | 38.3% | 16.2 | 500.0 | capacity_research_ok |
| short_depth_rv_cv_BONK1MUSDT_30m_30bps | 677 | 6.2 | 25.4% | 16.2 | 500.0 | capacity_research_ok |
| short_depth_rv_cv_BONK1MUSDC_30m_20bps | 394 | 5.9 | 37.1% | 15.2 | 500.0 | capacity_research_ok |
| short_depth_rv_cv_BONK1MUSDC_30m_30bps | 394 | 5.9 | 25.6% | 15.2 | 500.0 | capacity_research_ok |
| short_spread_high_BONK1MUSDC_30m_20bps | 450 | 16.0 | 40.2% | 16.1 | 250.0 | capacity_research_ok |
| short_spread_high_BONK1MUSDC_30m_30bps | 450 | 16.0 | 25.6% | 16.1 | 250.0 | capacity_research_ok |
| short_spread_high_BONK1MUSDT_5m_20bps | 2689 | 0.7 | 21.4% | 10.0 | 0.0 | too_small_after_stress |
| short_spread_high_BONK1MUSDT_5m_30bps | 2689 | 0.7 | 11.8% | 10.0 | 0.0 | too_small_after_stress |
| short_spread_high_BONK1MUSDT_15m_20bps | 2689 | 2.0 | 41.1% | 18.0 | 0.0 | too_small_after_stress |
| short_spread_high_BONK1MUSDT_15m_30bps | 2689 | 2.0 | 30.1% | 18.0 | 0.0 | too_small_after_stress |
| short_spread_high_BONK1MUSDT_30m_20bps | 2685 | 3.2 | 46.9% | 26.3 | 0.0 | too_small_after_stress |
| short_spread_high_BONK1MUSDT_30m_30bps | 2685 | 3.2 | 39.6% | 26.3 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDT_30m_20bps | 2401 | 3.5 | 44.7% | 20.7 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDT_30m_30bps | 2401 | 3.5 | 32.9% | 20.7 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDT_15m_20bps | 2398 | 1.5 | 34.7% | 13.9 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDT_15m_30bps | 2398 | 1.5 | 21.6% | 13.9 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDT_5m_20bps | 2395 | 0.7 | 14.2% | 8.0 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDT_5m_30bps | 2395 | 0.7 | 6.0% | 8.0 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDC_30m_20bps | 2277 | 1.5 | 44.6% | 21.6 | 0.0 | too_small_after_stress |
| short_depth_high_BONK1MUSDC_30m_30bps | 2277 | 1.5 | 34.9% | 21.6 | 0.0 | too_small_after_stress |

Short horizons have good row coverage, but median gross returns are small. Many rows can pass a displayed-depth bucket on 25 levels while failing to create enough stress-net room. Read these as decay/capacity diagnostics only.

## Too-Small Gates

| gate | rows | share | d25 5% p10 | d25 stress env | reason |
| --- | --- | --- | --- | --- | --- |
| short_depth_rv_cv_BONK1MUSDC_5m_20bps | 392 | 3.4% | 383.4 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_cv_BONK1MUSDC_5m_30bps | 392 | 3.4% | 383.4 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_cv_BONK1MUSDC_15m_20bps | 393 | 3.4% | 383.4 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_cv_BONK1MUSDC_15m_30bps | 393 | 3.4% | 383.4 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_spread_high_BONK1MUSDC_5m_20bps | 450 | 3.9% | 174.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_spread_high_BONK1MUSDC_5m_30bps | 450 | 3.9% | 174.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_spread_high_BONK1MUSDC_15m_20bps | 450 | 3.9% | 174.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_spread_high_BONK1MUSDC_15m_30bps | 450 | 3.9% | 174.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_cv_BONK1MUSDT_5m_20bps | 677 | 5.9% | 380.7 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_cv_BONK1MUSDT_5m_30bps | 677 | 5.9% | 380.7 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_cv_BONK1MUSDT_15m_20bps | 677 | 5.9% | 380.7 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_cv_BONK1MUSDT_15m_30bps | 677 | 5.9% | 380.7 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDC_5m_20bps | 1110 | 9.7% | 383.5 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDC_5m_30bps | 1110 | 9.7% | 383.5 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDC_15m_20bps | 1111 | 9.7% | 383.6 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDC_15m_30bps | 1111 | 9.7% | 383.6 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDC_30m_20bps | 1112 | 9.7% | 383.6 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDC_30m_30bps | 1112 | 9.7% | 383.6 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDT_5m_20bps | 1216 | 10.6% | 387.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDT_5m_30bps | 1216 | 10.6% | 387.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDT_15m_20bps | 1216 | 10.6% | 387.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDT_15m_30bps | 1216 | 10.6% | 387.1 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDT_30m_20bps | 1219 | 10.6% | 387.2 | 0.0 | no 25 quote bucket survives depth_25 wide stress |
| short_depth_rv_BONK1MUSDT_30m_30bps | 1219 | 10.6% | 387.2 | 0.0 | no 25 quote bucket survives depth_25 wide stress |

Too-small here means sparse rows, tiny selected share, insufficient 25-level p10 depth, no 25 quote bucket surviving wide stress, or worse lower-first behavior. It is a filter for research priority, not an execution rejection rule.

## Capacity Status Counts

| status | count |
| --- | ---: |
| capacity_research_ok | 10 |
| too_sparse | 0 |
| thin_rows | 0 |
| thin_gate_share | 0 |
| too_small_capacity | 0 |
| too_small_after_stress | 42 |
| path_risk_gate | 0 |

## Bottom Line

The capacity envelope is not zero, but it is small enough that the H4 active gates remain execution-research candidates only. The too-small line is especially clear at top-of-book; any future validation should keep depth-level, stress-net, and lower-first/drawdown columns next to the signal diagnostics.

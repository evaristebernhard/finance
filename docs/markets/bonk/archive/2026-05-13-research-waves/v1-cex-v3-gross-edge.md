# BONK CEX V3 Gross Edge / Friction Probe

Status: 2026-05-13. This is a rough execution-friction diagnostic over existing BONK V3 path labels and L2 state. It is not a trading rule, not an execution plan, and not an alpha claim.

## Inputs And Outputs

Input panel:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date/bonk_v3_gross_edge_20260513_bullish_l2_basket_price_v1.csv
date/bonk_v3_gross_edge_20260513_bullish_l2_basket_price_v1.json
```

## Method

- Uses `label_status=ok`, `barrier_bps=100`, horizons `H1/H4`, symbols `BONK1MUSDC/BONK1MUSDT`.
- Gates reuse the train-to-validation tertile convention: thresholds are fit on each fold's train side and applied to that fold's validation side.
- Gross edge is summarized from selected rows' `future_return_bps`, with path risk from `lower_first`, `mfe_up_bps`, and absolute `mae_down_bps`.
- Friction scenarios subtract `0`, `0.5x spread`, `1x spread`, `1x spread + 2 bps fee`, and `1x spread + fee + 10% of spread` as a small-size slippage stress.
- Capacity is only a rough top-of-book proxy: `10%` of median top depth and `5%` of p10 top depth. It is not a fill model.

## H4 Gate Friction Read

| symbol | gate | rows | share | gross med | spread | 1x+fee+slip net | lower | dd med | capacity 5% p10 | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDT | depth_high+rv_low+cv_spread+snapshot_microprice | 232 | 2.0% | 51.2 | 2.9 | 46.0 | 25.0% | 58.2 | 17.8 | capacity_limited_on_paper |
| BONK1MUSDT | depth_high+rv_low+cv_spread | 676 | 5.9% | 38.9 | 2.9 | 33.6 | 25.7% | 55.1 | 15.2 | capacity_limited_on_paper |
| BONK1MUSDT | depth_high+rv_low+snapshot_microprice | 582 | 5.1% | 31.1 | 1.5 | 27.5 | 22.7% | 55.4 | 14.9 | capacity_limited_on_paper |
| BONK1MUSDT | depth_high+rv_low | 1215 | 10.6% | 21.4 | 1.5 | 17.8 | 27.3% | 61.2 | 14.5 | capacity_limited_on_paper |
| BONK1MUSDC | depth_high+rv_low+cv_spread+snapshot_microprice | 173 | 1.5% | 48.6 | 2.9 | 43.4 | 25.4% | 64.0 | 16.0 | capacity_limited_on_paper |
| BONK1MUSDC | depth_high+rv_low+cv_spread | 393 | 3.4% | 37.3 | 1.5 | 33.7 | 24.2% | 60.1 | 15.2 | capacity_limited_on_paper |
| BONK1MUSDC | depth_high+rv_low+snapshot_microprice | 629 | 5.5% | 11.8 | 3.0 | 6.6 | 29.4% | 67.7 | 17.0 | capacity_limited_on_paper |
| BONK1MUSDC | depth_high+rv_low | 1112 | 9.7% | 11.1 | 2.9 | 5.9 | 29.7% | 66.8 | 16.1 | capacity_limited_on_paper |

## H1 Gate Friction Read

| symbol | gate | rows | gross med | 1x+fee net | 1x+fee+slip net | lower | dd med | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDT | depth_high+rv_low+snapshot_microprice | 582 | 6.0 | 2.5 | 2.3 | 4.1% | 26.1 | razor_thin_after_costs |
| BONK1MUSDT | depth_high+rv_low+cv_spread+snapshot_microprice | 232 | 7.0 | 2.1 | 1.8 | 3.9% | 22.9 | razor_thin_after_costs |
| BONK1MUSDT | depth_high+rv_low+cv_spread | 676 | 6.6 | 1.7 | 1.4 | 3.1% | 23.1 | razor_thin_after_costs |
| BONK1MUSDT | depth_high+rv_low | 1215 | 2.6 | -0.9 | -1.0 | 4.7% | 26.8 | spread_fragile |
| BONK1MUSDC | depth_high+rv_low+cv_spread | 393 | 3.6 | 0.2 | 0.0 | 3.6% | 24.1 | razor_thin_after_costs |
| BONK1MUSDC | depth_high+rv_low+cv_spread+snapshot_microprice | 173 | 4.2 | -0.7 | -1.0 | 4.6% | 22.6 | spread_fragile |
| BONK1MUSDC | depth_high+rv_low+snapshot_microprice | 629 | 0.8 | -4.2 | -4.5 | 8.7% | 29.3 | spread_fragile |
| BONK1MUSDC | depth_high+rv_low | 1112 | 0.6 | -4.3 | -4.6 | 7.1% | 29.3 | spread_fragile |

## Friction Survivors

Rows below survive the rough `1x spread + fee + small slippage` median-net screen. This is only a research filter; lower-first and capacity still matter.

| symbol | H | gate | gross med | stress net | lower | rows | capacity 10% med |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDT | 4 | depth_high+rv_low+cv_spread+snapshot_microprice | 51.2 | 46.0 | 25.0% | 232 | 46.7 |
| BONK1MUSDC | 4 | depth_high+rv_low+cv_spread+snapshot_microprice | 48.6 | 43.4 | 25.4% | 173 | 40.1 |
| BONK1MUSDC | 4 | depth_high+rv_low+cv_spread | 37.3 | 33.7 | 24.2% | 393 | 39.1 |
| BONK1MUSDT | 4 | depth_high+rv_low+cv_spread | 38.9 | 33.6 | 25.7% | 676 | 42.0 |
| BONK1MUSDT | 4 | depth_high+rv_low+snapshot_microprice | 31.1 | 27.5 | 22.7% | 582 | 39.5 |
| BONK1MUSDT | 4 | depth_high | 30.6 | 26.7 | 28.0% | 2393 | 38.2 |
| BONK1MUSDT | 4 | snapshot_microprice_low | 27.5 | 23.9 | 31.6% | 3320 | 22.2 |
| BONK1MUSDC | 4 | cv_spread_selected | 26.3 | 22.2 | 31.6% | 4093 | 6.8 |
| BONK1MUSDT | 4 | cv_spread_selected | 26.6 | 22.0 | 31.9% | 4095 | 15.9 |
| BONK1MUSDC | 4 | depth_high | 23.1 | 17.9 | 29.9% | 2277 | 41.5 |
| BONK1MUSDT | 4 | depth_high+rv_low | 21.4 | 17.8 | 27.3% | 1215 | 38.7 |
| BONK1MUSDC | 4 | snapshot_microprice_low | 22.6 | 17.4 | 32.3% | 2876 | 30.8 |
| BONK1MUSDT | 4 | rv_low | 17.3 | 13.7 | 31.4% | 3237 | 18.9 |
| BONK1MUSDC | 4 | rv_low | 17.0 | 11.9 | 30.7% | 3239 | 16.5 |
| BONK1MUSDC | 4 | depth_high+rv_low+snapshot_microprice | 11.8 | 6.6 | 29.4% | 629 | 45.3 |
| BONK1MUSDC | 4 | depth_high+rv_low | 11.1 | 5.9 | 29.7% | 1112 | 42.6 |

## Interpretation

The H4 gates have visibly more gross bps than H1. H1 is usually spread-fragile or path-risk dominated once a full spread and small fee are charged. H4 `depth_high+rv_low` style gates can survive simple friction on paper, especially in USDC mirrors and some USDT combinations, but the lower-first rate remains material and the selected capacity is small.

The strongest-looking rows often have the smallest gate share. Treat those as capacity-limited diagnostics: a gate with high median net but only a few hundred selected minutes can vanish under a slightly different phase, fee tier, or fill assumption.

## Caveats

- Mid-to-mid path labels are not executable fills.
- Spread is taken from L2 median spread columns and treated as a simple cost proxy.
- Slippage is a stylized small-size stress, not an order-book walk.
- Fees are configurable and default to a small `2` bps stress.
- Lower-first and drawdown columns are path-risk warnings, not stop-loss logic.
- No promises: these numbers only decide what deserves stricter next-window validation.

## Status Counts

| status | count |
| --- | ---: |
| roughly_viable_on_paper | 0 |
| capacity_limited_on_paper | 16 |
| friction_survives_but_path_risky | 0 |
| razor_thin_after_costs | 4 |
| gross_only | 0 |
| spread_fragile | 12 |
| path_risk_dominates | 0 |
| no_gross_edge | 0 |
| too_sparse | 0 |

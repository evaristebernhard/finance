# BONK CEX V4 Regime State Taxonomy

Status: 2026-05-13T12:42:37Z. This is an interpretive taxonomy over existing BONK L2/orderbook and context data. It is not a trading rule, not an execution plan, and not an alpha claim.

## Inputs And Outputs

Input panel:

```text
data\bonk\v1\derived\bonk_l2_label_context_panel\bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

Outputs:

```text
date\bonk_v4_regime_state_taxonomy_20260513_bullish_l2_basket_price_v1_clusters.csv
date\bonk_v4_regime_state_taxonomy_20260513_bullish_l2_basket_price_v1_state_outcomes.csv
date\bonk_v4_regime_state_taxonomy_20260513_bullish_l2_basket_price_v1_manual_gate_overlap.csv
date\bonk_v4_regime_state_taxonomy_20260513_bullish_l2_basket_price_v1_summary.json
```

## Method

- Scope: `BONK1MUSDC` and `BONK1MUSDT`, `label_status=ok`, `100 bps` labels, `H1/H4`.
- State features: top depth, BONK 1h realized volatility, displayed spread, bullish common-mode score, cross-venue disagreement, and signed cross-venue spread-difference rank.
- Clustering: per-symbol unsupervised clustering over percentile-normalized state features. Outcomes are not used to fit clusters.
- Discretization: every state receives human-readable high/mid/low tags: depth, RV, spread, common-mode, and cross-venue disagreement.
- Manual gate overlay: active V3 H4 gates are evaluated with fold-local train-side tertile thresholds, then mapped into the state clusters.
- Path outcomes are descriptive: upper/lower first-passage rates, residual-positive rate, median residual return, path width, and drawdown.

## Taxonomy

| symbol | state | label | share | depth pct | rv pct | spread pct | common pct | cv disagree pct | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDC | BONK1MUSDC_S6 | thin_volatile_tight_common_on_cv_mixed | 19.5% | 0.27 | 0.81 | 0.29 | 0.78 | 0.35 | thin_volatile_state |
| BONK1MUSDC | BONK1MUSDC_S2 | deep_quiet_normal_spread_common_mid_cv_mixed | 19.4% | 0.76 | 0.23 | 0.38 | 0.40 | 0.35 | active_gate_neighborhood |
| BONK1MUSDC | BONK1MUSDC_S5 | thin_normal_rv_tight_common_off_cv_mixed | 17.9% | 0.31 | 0.40 | 0.15 | 0.24 | 0.37 | mixed_state |
| BONK1MUSDC | BONK1MUSDC_S1 | deep_quiet_wide_common_mid_cv_disagree | 16.0% | 0.86 | 0.27 | 0.88 | 0.50 | 0.80 | deep_quiet_wide_cross_venue_state |
| BONK1MUSDC | BONK1MUSDC_S3 | mid_depth_volatile_wide_common_on_cv_mixed | 13.9% | 0.42 | 0.76 | 0.73 | 0.81 | 0.66 | thin_volatile_state |
| BONK1MUSDC | BONK1MUSDC_S4 | mid_depth_normal_rv_normal_spread_common_off_cv_mixed | 13.3% | 0.35 | 0.62 | 0.59 | 0.26 | 0.52 | mixed_state |
| BONK1MUSDT | BONK1MUSDT_S3 | mid_depth_normal_rv_tight_common_off_cv_mixed | 20.2% | 0.48 | 0.39 | 0.16 | 0.20 | 0.40 | mixed_state |
| BONK1MUSDT | BONK1MUSDT_S1 | deep_quiet_wide_common_off_cv_mixed | 19.1% | 0.82 | 0.25 | 0.82 | 0.33 | 0.40 | deep_quiet_wide_spread_state |
| BONK1MUSDT | BONK1MUSDT_S6 | thin_volatile_tight_common_on_cv_mixed | 18.9% | 0.17 | 0.83 | 0.25 | 0.69 | 0.49 | thin_volatile_state |
| BONK1MUSDT | BONK1MUSDT_S4 | mid_depth_volatile_wide_common_on_cv_aligned | 16.5% | 0.43 | 0.75 | 0.81 | 0.74 | 0.30 | thin_volatile_state |
| BONK1MUSDT | BONK1MUSDT_S2 | deep_quiet_normal_spread_common_mid_cv_disagree | 13.9% | 0.79 | 0.32 | 0.56 | 0.52 | 0.76 | deep_quiet_cross_venue_state |
| BONK1MUSDT | BONK1MUSDT_S5 | thin_normal_rv_normal_spread_common_on_cv_disagree | 11.3% | 0.25 | 0.45 | 0.61 | 0.70 | 0.80 | mixed_state |

## H4 USDT State Outcomes

Validation-fold path outcomes for BONK1MUSDT H4. These rows interpret state behavior; they are not ranked into a strategy.

| state | label | rows | share | resid + | med resid | upper | lower | path width | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BONK1MUSDT_S1 | deep_quiet_wide_common_off_cv_mixed | 1661 | 14.4% | 74.1% | 29.75 | 50.8% | 21.7% | 182.04 | deep_quiet_wide_spread_state |
| BONK1MUSDT_S2 | deep_quiet_normal_spread_common_mid_cv_disagree | 1059 | 9.2% | 65.3% | 18.69 | 50.4% | 21.8% | 188.28 | deep_quiet_cross_venue_state |
| BONK1MUSDT_S5 | thin_normal_rv_normal_spread_common_on_cv_disagree | 816 | 7.1% | 51.2% | 1.24 | 52.9% | 27.3% | 196.27 | mixed_state |
| BONK1MUSDT_S4 | mid_depth_volatile_wide_common_on_cv_aligned | 1906 | 16.6% | 49.8% | -0.15 | 48.5% | 36.2% | 208.29 | thin_volatile_state |
| BONK1MUSDT_S3 | mid_depth_normal_rv_tight_common_off_cv_mixed | 3028 | 26.3% | 47.0% | -5.83 | 36.8% | 45.3% | 198.12 | mixed_state |
| BONK1MUSDT_S6 | thin_volatile_tight_common_on_cv_mixed | 3039 | 26.4% | 45.4% | -8.78 | 50.7% | 35.3% | 227.25 | thin_volatile_state |

## Active Gate Location

Overall active-gate validation read:

| gate | status | rows | share | resid + | med resid | lower | path width |
| --- | --- | --- | --- | --- | --- | --- | --- |
| depth_high+rv_low | active_base_gate | 1317 | 11.4% | 66.1% | 18.79 | 26.8% | 178.16 |
| depth_high+rv_low+cv_spread | active_combo_gate | 796 | 6.9% | 71.0% | 24.43 | 26.4% | 176.62 |

Top active-gate state overlaps:

| gate | state | label | rows | gate share | state capture | resid + | med resid | lower | read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| depth_high+rv_low | BONK1MUSDT_S1 | deep_quiet_wide_common_off_cv_mixed | 692 | 52.5% | 41.7% | 76.4% | 28.80 | 22.5% | deep_quiet_wide_spread_state |
| depth_high+rv_low | BONK1MUSDT_S3 | mid_depth_normal_rv_tight_common_off_cv_mixed | 329 | 25.0% | 10.9% | 35.0% | -22.50 | 51.4% | mixed_state |
| depth_high+rv_low | BONK1MUSDT_S2 | deep_quiet_normal_spread_common_mid_cv_disagree | 293 | 22.2% | 27.7% | 76.8% | 21.20 | 9.6% | deep_quiet_cross_venue_state |
| depth_high+rv_low | BONK1MUSDT_S4 | mid_depth_volatile_wide_common_on_cv_aligned | 3 | 0.2% | 0.2% | 66.7% | 18.16 | 0.0% | thin_volatile_state |
| depth_high+rv_low+cv_spread | BONK1MUSDT_S1 | deep_quiet_wide_common_off_cv_mixed | 653 | 82.0% | 39.3% | 76.9% | 29.73 | 22.4% | deep_quiet_wide_spread_state |
| depth_high+rv_low+cv_spread | BONK1MUSDT_S3 | mid_depth_normal_rv_tight_common_off_cv_mixed | 139 | 17.5% | 4.6% | 43.2% | -16.15 | 46.0% | mixed_state |
| depth_high+rv_low+cv_spread | BONK1MUSDT_S4 | mid_depth_volatile_wide_common_on_cv_aligned | 3 | 0.4% | 0.2% | 66.7% | 18.16 | 0.0% | thin_volatile_state |
| depth_high+rv_low+cv_spread | BONK1MUSDT_S2 | deep_quiet_normal_spread_common_mid_cv_disagree | 1 | 0.1% | 0.1% | 100.0% | 24.47 | 0.0% | deep_quiet_cross_venue_state |

## Interpretation

The active H4 USDT gates sit mostly in deep/quiet states, but the main USDT overlap is the wide-spread version, not the tight-spread version.

- `depth_high + rv_low` is best read as a deep/quiet regime filter, not as a fast orderbook timing signal.
- Adding the signed cross-venue spread component concentrates the active USDT combo inside the wide-spread deep/quiet state, not inside the tight/aligned state.
- States with high depth and low RV are the natural home of the active gate; the value of the taxonomy is to show when that state is tight/aligned versus wide/disagreeing.
- Outcome differences are descriptive and remain blocked by the V3 negative-control findings: phase, time-shift, quote placebo, and exact-label checks still decide whether more data collection is justified.

## State Read Counts

```json
{
  "active_gate_neighborhood": 1,
  "deep_quiet_cross_venue_state": 1,
  "deep_quiet_wide_cross_venue_state": 1,
  "deep_quiet_wide_spread_state": 1,
  "mixed_state": 4,
  "thin_volatile_state": 4
}
```

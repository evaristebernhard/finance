# CCUSDT q70 idle01_g1 maker-first exit completion audit

Status: `maker-first exit no-go; diagnostic/minimal prototype completed`.

This audit checks the requested maker-first exit branch against current
artifacts. It studies exit execution for existing positions only. It does not
study maker entry.

## Requirement Map

| Requirement | Evidence | Status |
| --- | --- | --- |
| Build runtime-safe `maker_exit_opportunity_panel` on fixed30/fixed45/fixed60/stopping exits | `systems/ccusdt_replay_exchange/runs/maker_exit_opportunity_q70_idle01_g1_20260505_18_20260522/summary.json`: `exit_profile_sources = fixed30_livecoherent, fixed45_livecoherent, fixed60_taker, stopping_rule_v1`; `actual_exit_candidates=9856`; `panel_rows=29568`; `ttl_sec=[1,2,5]` | Done |
| Define taker exit, maker touch exit, spread saving, maker fill probability, unfilled decay, adverse selection | `docs/markets/ccusdt/v1-tfi-maker-first-exit-opportunity-warmup-20260522.md` model section and output columns `immediate_taker_net_bps`, `maker_touch_net_bps`, `spread_saving_bps`, `queue_fill`, `unfilled_decay_bps`, `selection_cost_bps` | Done |
| Estimate conditional value by TTL, cell, H/D, spread, depth/imbalance, same/opposite flow, recent mid alpha | Opportunity report sections `TTL Summary`, `Day Stability`, `Cell Readout`, and factor-bucket readouts; generated tables `maker_exit_ttl_summary.csv`, `maker_exit_by_day.csv`, `maker_exit_by_cell.csv`, `maker_exit_factor_summary.csv` | Done |
| Implement prior-date `maker_first_exit_v1` prototype without current-day label leakage | `maker_first_exit_policy.py`; strict warmup run `maker_first_exit_policy_q70_idle01_g1_warmup_strict_20260516_18_20260522`; promotion uses strictly prior dates and current-day labels only for evaluation | Done |
| Output maker event-chain fields | `maker_first_exit_events.parquet` columns include `maker_order_posted`, `maker_filled`, `cancel_reprice`, `taker_fallback`, `saved_spread_bps`, `missed_fill_decay_bps`, `adverse_selection_bps`, `final_net_bps` | Done in fast-line prototype |
| Run L2 replay queue/fill diagnostic on 5/16..5/18 | `maker_exit_l2_queue_q70_idle01_g1_warmup_strict_20260516_18_20260522/summary.json`: `attempts=110`, `l2_rows_read=138797819`, `l2_matched_rows=137` | Done |
| Separate passive maker alpha from waiting/fallback alpha | `v1-tfi-maker-exit-wait-vs-maker-20260522.md` and `maker_exit_wait_vs_maker_overall_summary.csv` decompose `final_delta = delay_only_delta + passive_increment_vs_delay` | Done |
| Decide whether to enter strict Runner maker lifecycle | Wait-vs-maker decomposition shows positive fixed30 result is not passive fill alpha. L2 proxy fill rate is `0%`; fixed30 L2 delta `+12.1434` is entirely `delay_only_delta`, with passive increment `0.0000` | No-go; do not implement strict Runner maker lifecycle for this family |

## Key Results

The global queue-ahead maker-first controller is not promoted. On the warmup
panel, the best whole-profile queue row is still negative:

```text
fixed45_livecoherent / TTL=1s
weighted delta = -57.7696 bp-units
positive-day fraction = 0.3571
positive whole-profile queue rows = 0 / 12
```

The strict prior-date prototype finds only narrow selected attempts:

```text
fixed30: 51 attempts, maker delta +9.6039, selection-adjusted +8.7721
fixed45: 59 attempts, maker delta +13.3118, selection-adjusted -8.0544
fixed60: 0 maker attempts
stopping_rule: 0 maker attempts
```

But the mechanism decomposition rejects maker-first as passive execution alpha:

```text
fixed30 / spread_q90 / TTL=5 / l2_depletion_proxy_v1
attempts = 51
fill_rate = 0.0000
final_delta = +12.1434
delay_only_delta = +12.1434
passive_increment_vs_delay = +0.0000
```

Under the trade-queue proxy, fixed30 remains mostly wait-driven:

```text
final_delta = +9.6039
delay_only_delta = +12.1434
passive_increment_vs_delay = -2.5395
selection-adjusted delta = +8.7721
```

So the current positive fixed30 result is better interpreted as conditional
wait/fallback timing, not as maker execution value.

## Boundary Check

The relevant diagnostic scripts do not import root research scripts and do not
read `date/`, scored entries, future labels, MFE, MAE, or realized PnL as
strategy runtime inputs. The opportunity panel contains realized fill/decay
labels only as offline diagnostic labels; the prior-date policy uses those
labels only from dates strictly before the test date.

## Decision

Do not promote `maker_first_exit_v1` to the strict Runner maker lifecycle for
this q70 `idle01_g1` branch. The minimum maker-first exit framework has done
its job: it found that the apparent improvement is not true passive fill edge.

The next strategy branch should be a small conditional wait/exit-timing
controller, reusing the same exit-decision events, rather than adding maker
order lifecycle complexity.


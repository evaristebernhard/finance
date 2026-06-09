# CCUSDT Signal Path Math

Status: `20260517_ccusdt_signal_path_math_v1` from source panel `20260517_ccusdt_fixed_factors_v3`.

Guardrail: `research_only_signal_path_math_no_execution_recommendation_no_alpha_claim`.

This is a cost-threshold and barrier path-shape diagnostic over a snapshot-frame factor panel. It is not queue-position fill evidence, not a live execution simulation, not trading advice, and not an alpha claim.

## Scope

- Fixed diagnostic rows: `468`.
- Barrier diagnostic rows: `1404`.
- Entry refinement rows: `39`.
- Stop-policy rows: `507`.
- Timeouts: `10s, 30s, 60s`.
- Barrier pairs: `8/5, 12/5, 12/8`.
- Stop levels: `5, 8, 12, 20` bps; grace windows `0s, 5s, 10s`.
- Entry stream uses first signal per 60s bucket; barrier rows compare path exits on that same entry set.

## Research Decision

The current evidence does not support promoting CCUSDT to an executable strategy. It does support one more narrow modeling pass, because the edge is not a single homogeneous rule: it is a mixture of large-sample right-tail states and smaller state-conditioned regimes.

The large-sample candidates that still clear toy maker-light cost `C` are thin. `tfi_follow_flat` in `expanding_fold3` has `1129` entries, `E = 2.4978` bps, control margin `4.5095` bps, and negative median `-0.3967` bps. `tfi_short_flat` in the same fold has `716` entries, `E = 2.4218` bps, control margin `4.3188` bps, and median `-0.3931` bps. The same family weakly repeats in `expanding_fold2`: `tfi_follow_flat` has `926` entries and `E = 1.5389` bps, while `tfi_short_flat` has `615` entries and `E = 1.3572` bps. These rows depend heavily on right-tail capture, with top-10 gross contribution around `87%..90%`.

The cleaner-looking rows are smaller and more regime-specific. `tfi_short_stale25` in `expanding_fold3` has `131` entries, net mean `5.1872` bps, median `2.5130` bps, and control margin `7.1035` bps, but the same trigger is weak in `expanding_fold2` and too small in `expanding_fold1`. Treat it as a potentially useful sparse state hypothesis, not as a stable strategy.

The practical question is therefore not whether more hard TP/SL optimization can improve the table. It already shows that hard TP usually improves comfort while clipping the right tail. The only useful exit work is stop-only or delayed catastrophic-stop diagnostics that improve left tail without destroying mean. For the large `tfi_follow_flat` row, stops improve CVaR but still cost mean; the gentlest versions are delayed catastrophic stops near `20` bps.

Go/no-go for the next pass:

- Continue only if quote-transition-only labels show the edge survives on true post-signal quote moves rather than snapshot-state persistence.
- Continue only if matched-random and residualized controls stay below the signal after conditioning on stale state, trade activity, spread, and recent return.
- Continue only if a large-sample family keeps positive `E` after a stricter cost model, with median no worse than slightly negative and top-tail concentration reduced.
- Stop or pivot if the edge remains limited to fold3-only small states, or if large-sample rows require right-tail concentration above about `85%` to cover `C`.

## Stale25 State Read

`tfi_short_stale25` is the best new state-conditioned entry candidate, but it is not enough evidence for execution. The useful interpretation is: a short-side TFI extreme during a `stale_mid_ge25` state may identify a quote-release condition. The current data says this state can be interesting, but sparse and fold-sensitive.

| fold | entries | net_mean_bps | net_median_bps | net_cvar10_bps | control_margin_bps | top10_gross_share | read |
| --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold1 | 27 | 1.3312 | 2.7485 | -9.0805 | 3.3620 | 0.3365 | too few |
| expanding_fold2 | 73 | 0.1424 | -0.5163 | -16.8257 | 1.4834 | 0.8470 | weak / cost-thin |
| expanding_fold3 | 131 | 5.1872 | 2.5130 | -19.3756 | 7.1035 | 0.8378 | best state candidate |

The cost read is also narrow. For the exact `fwd_time_60s_bps / short_low / trade_present_stale_mid_ge25` row, fold3 survives maker-light and taker-spread costs (`5.1872` and `3.1561` bps net), but fails wide-stress (`-1.9062` bps net, median `-5.0000`). Fold2 is only `0.1424` bps net under maker-light and fails taker-spread. This means the row has information value, but not a robust cost buffer.

Stop-only does not turn `stale25` into an execution rule. In fold3, `5` bps stop-only improves mean from `5.1872` to `5.5875` and CVaR10 from `-19.3756` to `-10.6891`, but it pushes median from `2.5130` to `-0.1816` and stops `8.57%` of fixed cost winners. A `20` bps catastrophic stop is worse (`4.3339` mean, `0.7160` median, `-22.2877` CVaR10). Stops should therefore remain path-risk diagnostics for this state, not strategy promotion evidence.

The per-entry tail/stop deep dive in `v1-tail-stop-deep-dive.md` confirms the same conclusion with recovery diagnostics. For fold3 `stale25`, `5` bps stop has save/kill `1.4223`, but median still drops below zero; `20` bps stop has save/kill only `0.1320`. For fold3 large-sample flat rows, `5` bps stop improves CVaR but reduces mean and median, with save/kill below `1`.

Minimum next validation for `stale25`:

- Use quote-transition-only labels to prove the payoff comes from true post-signal bid/ask/mid movement, not stale snapshot persistence.
- Add matched-random controls matched on stale length, trade-present state, spread bucket, recent return, date/time bucket, and event activity.
- Run day-level leave-one-day-out plus top-winner removal; if the fold3 mean or median collapses after removing the largest `5..10` winners, keep it as a diagnostic only.
- Do not combine `stale25` with MLOFI/book-pressure confirmation until the raw state survives these checks.

## Cost-Threshold Read

| fold | trigger_class | entries | gross_mean_bps | gross_median_bps | net_mean_bps | net_median_bps | cost_cross_rate | winner_excess_mean_bps | loser_shortfall_mean_bps | top10_gross_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold2 | combo_trade_mlofi_long_active | 24 | 11.4446 | 6.4912 | 9.4450 | 4.7767 | 0.6667 | 15.4960 | 2.6571 | 0.6556 |
| expanding_fold3 | tfi_short_stale25 | 131 | 7.2183 | 4.5823 | 5.1872 | 2.5130 | 0.5344 | 17.0199 | 8.3913 | 0.8378 |
| expanding_fold3 | mlofi_l1_short_active | 63 | 7.0294 | 1.5312 | 5.1022 | -0.2344 | 0.4762 | 20.0126 | 8.4528 | 0.9140 |
| expanding_fold3 | tfi_event_active | 210 | 6.1432 | 4.3199 | 4.1374 | 2.2123 | 0.5238 | 15.8603 | 8.7577 | 0.8125 |
| expanding_fold3 | tfi_follow_stale70 | 64 | 5.5843 | 3.6293 | 3.5886 | 1.4584 | 0.5000 | 14.9143 | 7.7372 | 0.7224 |
| expanding_fold3 | combo_book_pressure_short_active | 127 | 5.3735 | 0.6485 | 3.3887 | -1.0000 | 0.4409 | 18.8930 | 8.8400 | 1.1064 |
| expanding_fold3 | tfi_follow_flat | 1129 | 4.5385 | 1.6254 | 2.4978 | -0.3967 | 0.4827 | 13.6072 | 7.8697 | 0.8872 |
| expanding_fold3 | tfi_short_flat | 716 | 4.4655 | 1.6249 | 2.4218 | -0.3931 | 0.4804 | 13.1725 | 7.5197 | 0.8805 |
| expanding_fold3 | combo_trade_mlofi_long_active | 70 | 4.3070 | 3.3395 | 2.3919 | 0.9853 | 0.5000 | 15.0610 | 10.2772 | 0.8797 |
| expanding_fold3 | tfi_long_flat | 493 | 4.3553 | 1.3165 | 2.3091 | -0.6709 | 0.4807 | 14.4673 | 8.9467 | 0.9777 |
| expanding_fold2 | tfi_event_active | 121 | 3.8851 | 2.5972 | 1.7959 | -0.0261 | 0.4959 | 8.8853 | 5.1773 | 0.7408 |
| expanding_fold2 | tfi_follow_flat | 926 | 3.6313 | 1.2813 | 1.5389 | -0.6801 | 0.4503 | 10.8553 | 6.0936 | 0.8709 |
| expanding_fold3 | tfi_short_stale70 | 43 | 3.3867 | 5.3693 | 1.4041 | 3.2637 | 0.5116 | 11.8052 | 9.4923 | 1.0165 |
| expanding_fold1 | tfi_follow_stale70 | 25 | 3.5711 | 4.7624 | 1.3776 | 2.4015 | 0.5600 | 5.0761 | 3.3297 | 0.3992 |

## Entry Refinement

| fold | trigger_class | entries | net_mean_bps | net_median_bps | A_cost_cross_rate | B_winner_excess_bps | D_loser_shortfall_bps | E_edge_bps | control_margin_bps | top10_gross_share | entry_score | research_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | tfi_follow_flat | 1129 | 2.4978 | -0.3967 | 0.4827 | 13.6072 | 7.8697 | 2.4978 | 4.5095 | 0.8872 | 4.8063 | right_tail_entry_candidate |
| expanding_fold3 | tfi_short_stale25 | 131 | 5.1872 | 2.5130 | 0.5344 | 17.0199 | 8.3913 | 5.1872 | 7.1035 | 0.8378 | 4.4310 | mean_median_entry_candidate |
| expanding_fold3 | tfi_short_flat | 716 | 2.4218 | -0.3931 | 0.4804 | 13.1725 | 7.5197 | 2.4218 | 4.3188 | 0.8805 | 3.9168 | right_tail_entry_candidate |
| expanding_fold3 | mlofi_l1_short_active | 63 | 5.1022 | -0.2344 | 0.4762 | 20.0126 | 8.4528 | 5.1022 | 8.8493 | 0.9140 | 3.8953 | right_tail_entry_candidate |
| expanding_fold3 | tfi_event_active | 210 | 4.1374 | 2.2123 | 0.5238 | 15.8603 | 8.7577 | 4.1374 | 3.2807 | 0.8125 | 3.5015 | mean_median_entry_candidate |
| expanding_fold2 | combo_trade_mlofi_long_active | 24 | 9.4450 | 4.7767 | 0.6667 | 15.4960 | 2.6571 | 9.4450 | 4.3050 | 0.6556 | 3.1455 | too_few_entries |
| expanding_fold3 | tfi_long_flat | 493 | 2.3091 | -0.6709 | 0.4807 | 14.4673 | 8.9467 | 2.3091 | 3.9912 | 0.9777 | 3.0353 | right_tail_entry_candidate |
| expanding_fold2 | tfi_follow_flat | 926 | 1.5389 | -0.6801 | 0.4503 | 10.8553 | 6.0936 | 1.5389 | 3.6214 | 0.8709 | 2.9578 | right_tail_entry_candidate |
| expanding_fold3 | tfi_follow_stale70 | 64 | 3.5886 | 1.4584 | 0.5000 | 14.9143 | 7.7372 | 3.5886 | 5.1398 | 0.7224 | 2.5688 | mean_median_entry_candidate |
| expanding_fold2 | tfi_short_flat | 615 | 1.3572 | -0.5155 | 0.4667 | 11.0442 | 7.1189 | 1.3572 | 3.1971 | 0.8995 | 2.2056 | right_tail_entry_candidate |
| expanding_fold3 | combo_book_pressure_short_active | 127 | 3.3887 | -1.0000 | 0.4409 | 18.8930 | 8.8400 | 3.3887 | 2.5320 | 1.1064 | 1.8280 | right_tail_entry_candidate |
| expanding_fold3 | combo_trade_mlofi_long_active | 70 | 2.3919 | 0.9853 | 0.5000 | 15.0610 | 10.2772 | 2.3919 | 3.7618 | 0.8797 | 1.7761 | right_tail_with_positive_median |
| expanding_fold2 | tfi_long_flat | 381 | 1.2395 | -1.0000 | 0.4121 | 10.1890 | 5.0332 | 1.2395 | 3.1288 | 0.9069 | 1.7504 | right_tail_entry_candidate |
| expanding_fold1 | tfi_event_active | 61 | 1.2920 | -0.4953 | 0.4918 | 5.7346 | 3.0073 | 1.2920 | 3.6847 | 0.4486 | 1.3724 | right_tail_entry_candidate |

## Barrier Increment

| fold | trigger_class | upper_bps | lower_bps | entries | tp_rate | sl_rate | timeout_rate | fixed_net_mean_bps | barrier_net_mean_bps | delta_net_mean_bps | fixed_net_median_bps | barrier_net_median_bps | sl_given_fixed_cost_winner_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold2 | combo_book_pressure_short_active | 12.0000 | 5.0000 | 76 | 0.1579 | 0.2632 | 0.5789 | -2.5856 | 0.1289 | 2.7146 | -0.6817 | -0.6798 | 0.0000 |
| expanding_fold2 | combo_book_pressure_short_active | 8.0000 | 5.0000 | 76 | 0.2105 | 0.2500 | 0.5395 | -2.5856 | -0.3605 | 2.2251 | -0.6817 | -0.6774 | 0.0000 |
| expanding_fold2 | combo_book_pressure_short_active | 12.0000 | 8.0000 | 76 | 0.1579 | 0.1447 | 0.6974 | -2.5856 | -0.4461 | 2.1395 | -0.6817 | -0.6798 | 0.0000 |
| expanding_fold2 | mlofi_l1_short_active | 12.0000 | 5.0000 | 44 | 0.2045 | 0.2045 | 0.5909 | -0.0423 | 1.1094 | 1.1517 | -0.6798 | -0.6674 | 0.0000 |
| expanding_fold2 | tfi_short_stale25 | 12.0000 | 5.0000 | 73 | 0.1781 | 0.1507 | 0.6712 | 0.1424 | 1.1437 | 1.0013 | -0.5163 | -0.5152 | 0.0000 |
| expanding_fold1 | combo_book_pressure_short_active | 12.0000 | 5.0000 | 26 | 0.1154 | 0.2308 | 0.6538 | -0.4758 | 0.3864 | 0.8622 | 1.2083 | 1.2083 | 0.0000 |
| expanding_fold1 | tfi_short_stale70 | 12.0000 | 5.0000 | 14 | 0.1429 | 0.0714 | 0.7857 | 0.7022 | 1.3987 | 0.6965 | 1.2083 | 1.2083 | 0.0000 |
| expanding_fold2 | tfi_short_stale25 | 12.0000 | 8.0000 | 73 | 0.1781 | 0.0959 | 0.7260 | 0.1424 | 0.8197 | 0.6773 | -0.5163 | -0.5152 | 0.0000 |
| expanding_fold1 | combo_book_pressure_short_active | 12.0000 | 8.0000 | 26 | 0.1154 | 0.0769 | 0.8077 | -0.4758 | 0.1965 | 0.6723 | 1.2083 | 1.2083 | 0.0000 |
| expanding_fold2 | mlofi_l1_short_active | 12.0000 | 8.0000 | 44 | 0.2045 | 0.1591 | 0.6364 | -0.0423 | 0.6055 | 0.6478 | -0.6798 | -0.6674 | 0.0000 |
| expanding_fold2 | mlofi_l1_short_active | 8.0000 | 5.0000 | 44 | 0.2727 | 0.1818 | 0.5455 | -0.0423 | 0.5919 | 0.6341 | -0.6798 | -0.5713 | 0.0000 |
| expanding_fold1 | mlofi_l1_short_active | 8.0000 | 5.0000 | 6 | 0.0000 | 0.1667 | 0.8333 | 0.7952 | 1.4246 | 0.6294 | 3.2301 | 3.2301 | 0.0000 |
| expanding_fold1 | mlofi_l1_short_active | 12.0000 | 5.0000 | 6 | 0.0000 | 0.1667 | 0.8333 | 0.7952 | 1.4246 | 0.6294 | 3.2301 | 3.2301 | 0.0000 |
| expanding_fold2 | combo_trade_mlofi_short_flat | 12.0000 | 5.0000 | 3022 | 0.1009 | 0.2399 | 0.6592 | -1.6024 | -1.0406 | 0.5619 | -1.6419 | -1.6826 | 0.0700 |

## Decomposition

| fold | trigger_class | upper_bps | lower_bps | tp_save_giveback_bps | tp_clip_right_tail_bps | sl_save_left_tail_bps | sl_kill_recovery_bps | race_effect_mean_bps | delta_cost_mean_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold2 | combo_book_pressure_short_active | 12.0000 | 5.0000 | 0.6636 | 0.5127 | 2.5737 | 0.0006 | 0.3618 | 0.0095 |
| expanding_fold2 | combo_book_pressure_short_active | 8.0000 | 5.0000 | 0.7713 | 1.0242 | 2.5007 | 0.0006 | 0.3965 | 0.0221 |
| expanding_fold2 | combo_book_pressure_short_active | 12.0000 | 8.0000 | 0.6636 | 0.5127 | 2.0425 | 0.0351 | 0.3667 | 0.0187 |
| expanding_fold2 | mlofi_l1_short_active | 12.0000 | 5.0000 | 1.0409 | 0.7037 | 0.8063 | 0.0000 | 0.5206 | -0.0082 |
| expanding_fold2 | tfi_short_stale25 | 12.0000 | 5.0000 | 0.7562 | 0.5338 | 0.7725 | 0.0000 | 0.4426 | -0.0064 |
| expanding_fold1 | combo_book_pressure_short_active | 12.0000 | 5.0000 | 0.2142 | 0.0074 | 0.8520 | 0.1648 | 0.0494 | 0.0318 |
| expanding_fold1 | tfi_short_stale70 | 12.0000 | 5.0000 | 0.3978 | 0.0073 | 0.2698 | 0.0000 | 0.3978 | -0.0363 |
| expanding_fold2 | tfi_short_stale25 | 12.0000 | 8.0000 | 0.7562 | 0.5338 | 0.4700 | 0.0125 | 0.4712 | 0.0026 |
| expanding_fold1 | combo_book_pressure_short_active | 12.0000 | 8.0000 | 0.2142 | 0.0074 | 0.4652 | 0.0000 | 0.2142 | -0.0003 |
| expanding_fold2 | mlofi_l1_short_active | 12.0000 | 8.0000 | 1.0409 | 0.7037 | 0.3984 | 0.0887 | 0.5001 | -0.0008 |

## Stop-Only And Delayed Stop

| fold | trigger_class | stop_policy | stop_bps | grace_sec | entries | stop_hit_rate | fixed_net_mean_bps | stop_net_mean_bps | delta_net_mean_bps | fixed_cvar10_bps | stop_cvar10_bps | delta_cvar10_bps | stop_given_fixed_cost_winner_rate | research_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| expanding_fold3 | combo_trade_mlofi_long_active | stop_only | 5.0000 | 0 | 70 | 0.3000 | 2.3919 | 3.7217 | 1.3298 | -30.4727 | -11.6418 | 18.8309 | 0.0571 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_trade_mlofi_long_active | delayed_stop | 5.0000 | 5 | 70 | 0.3000 | 2.3919 | 3.7217 | 1.3298 | -30.4727 | -11.6418 | 18.8309 | 0.0571 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_trade_mlofi_long_active | delayed_stop | 5.0000 | 10 | 70 | 0.3000 | 2.3919 | 3.4075 | 1.0156 | -30.4727 | -14.5478 | 15.9249 | 0.0571 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_trade_mlofi_long_active | stop_only | 8.0000 | 0 | 70 | 0.2429 | 2.3919 | 3.5612 | 1.1693 | -30.4727 | -15.9380 | 14.5347 | 0.0000 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_trade_mlofi_long_active | delayed_stop | 8.0000 | 5 | 70 | 0.2429 | 2.3919 | 3.5612 | 1.1693 | -30.4727 | -15.9380 | 14.5347 | 0.0000 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_trade_mlofi_long_active | delayed_stop | 8.0000 | 10 | 70 | 0.2429 | 2.3919 | 3.4461 | 1.0542 | -30.4727 | -16.9828 | 13.4899 | 0.0000 | left_tail_improved_low_mean_cost |
| expanding_fold3 | tfi_long_flat | stop_only | 5.0000 | 0 | 493 | 0.2941 | 2.3091 | 1.9306 | -0.3785 | -29.8047 | -15.8760 | 13.9287 | 0.1181 | left_tail_tradeoff |
| expanding_fold3 | combo_trade_mlofi_long_active | stop_only | 12.0000 | 0 | 70 | 0.1571 | 2.3919 | 3.4223 | 1.0304 | -30.4727 | -17.5213 | 12.9514 | 0.0000 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_trade_mlofi_long_active | delayed_stop | 12.0000 | 5 | 70 | 0.1571 | 2.3919 | 3.4223 | 1.0304 | -30.4727 | -17.5213 | 12.9514 | 0.0000 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_trade_mlofi_long_active | delayed_stop | 12.0000 | 10 | 70 | 0.1571 | 2.3919 | 3.4019 | 1.0100 | -30.4727 | -17.7251 | 12.7476 | 0.0000 | left_tail_improved_low_mean_cost |
| expanding_fold3 | mlofi_l1_short_active | stop_only | 5.0000 | 0 | 63 | 0.3175 | 5.1022 | 6.4985 | 1.3963 | -22.1823 | -9.9472 | 12.2350 | 0.0333 | left_tail_improved_low_mean_cost |
| expanding_fold3 | mlofi_l1_short_active | delayed_stop | 5.0000 | 5 | 63 | 0.3175 | 5.1022 | 6.4985 | 1.3963 | -22.1823 | -9.9472 | 12.2350 | 0.0333 | left_tail_improved_low_mean_cost |
| expanding_fold2 | tfi_short_flat | stop_only | 5.0000 | 0 | 615 | 0.2309 | 1.3572 | 1.4276 | 0.0704 | -24.6313 | -12.6646 | 11.9666 | 0.0871 | left_tail_improved_low_mean_cost |
| expanding_fold3 | combo_book_pressure_short_active | stop_only | 5.0000 | 0 | 127 | 0.3701 | 3.3887 | 4.2786 | 0.8899 | -23.4853 | -11.5643 | 11.9210 | 0.0714 | left_tail_improved_low_mean_cost |

## Controls

| control | rows | median_entries | median_net_mean_bps | p90_abs_net_mean_bps |
| --- | --- | --- | --- | --- |
| reversed_side | 117 | 131.0000 | -4.6016 | 7.0274 |
| shifted_500_events | 117 | 133.0000 | -2.1046 | 3.0016 |
| past_return_gate | 117 | 4377.0000 | -2.0664 | 2.4197 |

## Mathematical Read

The primary question is whether each trigger class crosses the maker-light cost threshold, not whether gross return is merely positive. For each class, the fixed rows estimate `A = Pr(X_T > c)`, winner excess, loser shortfall, and top-tail concentration.

Barrier rows should be read as incremental path-shape evidence. A useful barrier needs TP giveback saving plus SL left-tail saving to exceed TP right-tail clipping, SL recovery killing, and any cost increase. The key warning column is `sl_given_fixed_cost_winner_rate`: if it is high, the stop loss kills the samples that already crossed cost.

The entry-refinement table keeps the same `E = A*B - (1-A)*D` objective and adds simple control separation. The stop-policy table has no take-profit leg; it asks whether immediate, delayed, or catastrophic stops improve left-tail/CVaR without paying too much mean-return cost.

Cost `C` is the all-in hurdle used by the toy cost model, not just exchange fee. It stands in for entry/exit spread treatment, fill uncertainty, and a small execution allowance. Rows that only work under maker-light but fail wide-stress should be treated as information diagnostics, not robust strategy evidence.

## Stop Policy Decision

Full TP/SL barriers are not the preferred next path. They often improve median or comfort metrics by clipping both tails, while reducing expected value by cutting the right tail that pays for the strategy.

Stop-only and delayed-stop remain useful only as left-tail control. A stop policy is acceptable for follow-up when it materially improves CVaR, keeps `delta_net_mean_bps` close to zero or positive, and keeps `stop_given_fixed_cost_winner_rate` low. Current top stop rows are diagnostics, not execution rules. Immediate and 5s delayed stops are often similar in the best rows; 10s grace can give back protection.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_signal_path_math_fixed_20260517_ccusdt_signal_path_math_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_signal_path_math_barrier_20260517_ccusdt_signal_path_math_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_signal_path_math_entry_refinement_20260517_ccusdt_signal_path_math_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_signal_path_math_stop_policy_20260517_ccusdt_signal_path_math_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_signal_path_math_summary_20260517_ccusdt_signal_path_math_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_signal_path_math.py
```

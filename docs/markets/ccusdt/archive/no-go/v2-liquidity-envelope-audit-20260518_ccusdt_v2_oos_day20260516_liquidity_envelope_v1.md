# CCUSDT V2 Liquidity Envelope Audit

Status: `20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1`.

Guardrail: `research_only_liquidity_envelope_no_execution_recommendation_no_alpha_claim`.

Objective branch: screen execution envelope before further CCUSDT microstructure alpha mining. This is a research-only instrument-capacity audit, not a trading rule.

## Decision

Envelope status: `liquidity_envelope_no_go`.

CCUSDT does not pass the execution-first gate for this strategy family. The median spread is slightly above the `2` bps gate, the top-of-book depth support for the target notional fails every day, practical maker fill remains far below the required envelope, and no taker row has a promotion gate.

## Scorecard

| symbol | dates | target_notional_quote | median_daily_median_spread_bps | median_daily_p95_spread_bps | median_daily_top_depth_p05_quote | depth_support_day_rate | best_practical_maker_fill_rate | best_practical_maker_per_signal_net_bps | min_required_filled_net_for_2bps_at_current_fill_bps | taker_promote_rows | envelope_pre_alpha_gate | liquidity_envelope_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CCUSDT | 18 | 100.0000 | 2.0174 | 4.0017 | 0.0813 | 0.0000 | 0.1176 | -0.0038 | 17.0000 | 0 | False | liquidity_envelope_no_go |

## Daily Envelope

| date | ticker_rows | trade_rows | median_spread_bps | p95_spread_bps | top_depth_p05_quote | top_depth_ge_target_rate | top_trade_rate_per_min | top_trade_notional_rate_per_min | depth_support_day_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-29 | 123873 | 4573 | 2.0105 | 3.9979 | 0.0952 | 0.0994 | 2.3653 | 529.0363 | False |
| 2026-04-30 | 146783 | 4536 | 2.6288 | 3.9732 | 0.1429 | 0.0786 | 2.1854 | 462.3264 | False |
| 2026-05-01 | 132421 | 3908 | 2.0054 | 4.0056 | 0.1417 | 0.1721 | 1.9070 | 476.3322 | False |
| 2026-05-02 | 117023 | 3836 | 2.6720 | 4.0274 | 0.0459 | 0.1898 | 2.0605 | 550.0601 | False |
| 2026-05-03 | 118521 | 2200 | 2.6722 | 4.0260 | 0.1131 | 0.3644 | 1.1250 | 330.7563 | False |
| 2026-05-04 | 144896 | 2525 | 2.0423 | 4.0573 | 0.1542 | 0.1471 | 1.2743 | 301.2374 | False |
| 2026-05-05 | 178301 | 4438 | 2.0272 | 4.0497 | 0.1027 | 0.1411 | 2.3771 | 595.5998 | False |
| 2026-05-06 | 135730 | 3145 | 2.0241 | 4.0437 | 0.1375 | 0.1567 | 1.7139 | 444.4256 | False |
| 2026-05-07 | 116844 | 1793 | 2.0199 | 4.0822 | 0.1485 | 0.0000 | 0.9479 | 190.8951 | False |
| 2026-05-08 | 120154 | 2689 | 2.0588 | 4.0961 | 0.1095 | 0.0325 | 1.4042 | 314.6495 | False |
| 2026-05-09 | 109107 | 8073 | 2.0148 | 4.0464 | 0.0311 | 0.0057 | 4.3808 | 729.8663 | False |
| 2026-05-10 | 109791 | 5133 | 1.9265 | 3.8590 | 0.0612 | 0.0421 | 2.7702 | 596.6439 | False |
| 2026-05-11 | 118658 | 7344 | 1.9543 | 3.8750 | 0.0674 | 0.0535 | 3.8350 | 743.0565 | False |
| 2026-05-12 | 113539 | 5678 | 1.9493 | 3.7374 | 0.0667 | 0.0000 | 3.0626 | 520.2085 | False |
| 2026-05-13 | 113650 | 4679 | 1.9556 | 3.8996 | 0.0562 | 0.0081 | 2.4980 | 483.9104 | False |
| 2026-05-14 | 109235 | 10724 | 1.8994 | 3.6814 | 0.0620 | 0.0011 | 5.7057 | 923.5693 | False |
| 2026-05-15 | 120861 | 9701 | 1.8586 | 3.6994 | 0.0618 | 0.0025 | 5.3071 | 1011.3834 | False |
| 2026-05-16 | 107156 | 6734 | 2.5082 | 3.9968 | 0.0509 | 0.0159 | 3.6459 | 687.6158 | False |

## Interpretation

- The pre-alpha envelope already fails on spread/depth support for the target notional. The later practical maker-fill and per-signal economics audits fail as well, so this is not merely an alpha-label problem.
- At the best current practical maker fill rate, the decomposition requires a filled-order mean far above the observed filled mean to reach `2` bps per signal.
- This supports the liquidity-envelope universe pivot: future work should screen symbols for fillability and cost capacity before applying the CCUSDT V2 entry-quality/exit-shape/risk-control framework.

## Output Tables

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_liquidity_envelope_daily_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json`

## Reproduce

```powershell
python scripts/ccusdt_v2_liquidity_envelope_audit.py --symbol CCUSDT --run-tag 20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1
```

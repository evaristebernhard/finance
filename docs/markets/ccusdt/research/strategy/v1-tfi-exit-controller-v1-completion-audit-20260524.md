# CCUSDT q70 idle01_g1 ExitControllerV1 completion audit

Status: `diagnostic framework complete; conservative conditional-wait candidate found`.

This audit covers the unified exit execution controller branch where maker is
disabled and the only active actions are:

\[
a_t \in \{\text{cross now},\ \text{wait }\tau\text{ then cross}\}.
\]

Future maker fallback remains an execution extension, not part of this result.

## Requirement Map

| Requirement | Evidence | Status |
| --- | --- | --- |
| Unify fixed30/fixed45/fixed60/stopping, conditional wait, and future maker fallback into one exit controller framing | `docs/markets/ccusdt/v1-tfi-exit-controller-v1-conditional-wait-m010-20260522.md` defines `ExitControllerV1` action space and explicitly disables maker/post-only fallback | Done |
| Build wait-only opportunity panel on all four exit profiles | `systems/ccusdt_replay_exchange/runs/conditional_wait_exit_q70_idle01_g1_20260505_18_20260522/summary.json`: `actual_exit_candidates=9856`, `panel_rows=49280`, profiles `fixed30_livecoherent`, `fixed45_livecoherent`, `fixed60_taker`, `stopping_rule_v1` | Done |
| Define \(Y^T_t\), \(Y(a_t)\), \(\Delta(a_t)\), and \(W_t(\tau)=Y^T_{t+\tau}-Y^T_t\) | `conditional_wait_exit_opportunity.py` writes `immediate_taker_net_bps`, `wait_taker_net_bps`, `wait_value_bps`, and weighted equivalents; report model section states the formula | Done |
| Compare \(\tau=\{0.5,1,2,5,10\}\) | Opportunity summary has `ttl_sec=[0.5,1,2,5,10]`; `conditional_wait_exit_ttl_summary.csv` covers all profile/TTL pairs | Done |
| Bucket by runtime-safe features | Opportunity report and `conditional_wait_exit_factor_summary.csv` cover `cell`, `path_h_bps`, `path_d_bps`, `exit_spread_bps`, `signed_top_depth_imbalance`, pre-exit flow, recent mid alpha, and frames since mid change | Done |
| Keep post-exit flow/reclaim as diagnostic labels only | `conditional_wait_exit_opportunity.py` labels post-exit factors as `post_exit_diagnostic_label`; policy config lists runtime features separately from diagnostic label columns | Done |
| Implement prior-date `conditional_wait_exit_v1` | `conditional_wait_exit_policy.py`; conservative run `conditional_wait_exit_policy_q70_idle01_g1_m010_20260516_18_20260522` trains only on dates strictly before each test date | Done |
| Require prior-only mean edge, day stability, and left-tail controls | Conservative config: margin `0.10bps`, min prior days `8`, positive-day fraction `0.67`, CVaR10 floor `-5bps`, worst-event floor `-60bps`, worst-day floor `-75 bp-units` | Done |
| Compare 5/16..5/18 against pure taker baselines | Conservative aggregate table compares pure taker baseline and wait-controller total for all four profiles | Done |
| Prohibit `date/`, scored entries, future labels as runtime input | New scripts read fast-run exits plus canonical market truth/decision-frame cache. Runtime gates use only exit-decision-visible fields; wait/path outcomes are evaluation labels | Done |

## Main Result

The conservative policy uses `margin_bps=0.10`. This avoids the weak
`fixed60/stopping` waits that appeared under the looser `0.05bps` margin.

```text
pure taker baseline across profiles: 2413.2992
ExitControllerV1 wait delta:           +68.3173
controller total:                      2481.6165
```

Profile split:

```text
fixed30_livecoherent: +39.5357, 85 waits, exposure 56.75
fixed45_livecoherent: +28.7816, 62 waits, exposure 35.00
fixed60_taker:          0.0000, stays cross_now
stopping_rule_v1:       0.0000, stays cross_now
```

Left-tail readout for selected waits:

```text
fixed30: worst wait value -5.2077, CVaR10 -1.3821, delay-loss sum 6.5354
fixed45: worst wait value -6.5125, CVaR10 -3.6391, delay-loss sum 11.5270
```

Selected rule shape:

```text
fixed30: wait 5s when path_d_bps <= prior q30 and exit_spread_bps >= prior q70
fixed45: wait 5s when spread_q90, except 2026-05-17 where path_d_low_q30_spread_q70 wins
fixed60/stopping: no promoted wait gate under margin 0.10
```

## Interpretation

This supports a small, interpretable conditional-wait branch:

\[
E[W_t(5s)\mid X_t]>m
\]

for high-spread or low-giveback exits in the shorter fixed30/fixed45 families.
It does **not** support delaying all exits, nor does it revive maker-first. The
mechanism is exit timing: some exit decisions occur while the local path still
has short residual continuation or favorable fallback drift.

## Remaining Boundary

This is still a fast-line diagnostic/prototype. Before execution promotion, the
same controller should be run through the strict runner so the final accounting
uses real order/fill/lot event chains. That is the next engineering validation,
not part of the completed diagnostic framework.


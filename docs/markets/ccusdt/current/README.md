# CCUSDT Current Line

This folder contains the reports a new Codex should read before touching the
current CCUSDT replay exchange / TFI strategy line.

## First Read

1. `CURRENT_STRATEGY_PLAIN.md`
2. `v1-current-tfi-strategy-handoff-20260518.md`
3. `v1-tfi-current-research-map-20260519.md`
4. `v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md`

`CURRENT_STRATEGY_PLAIN.md` is the runtime truth page. Read it before the
older handoff. The old handoff mixes current runtime facts, historical research,
and follow-up hypotheses; it is useful context, but it is not a precise list of
what the Bot currently implements.

## Current Strategy And Capacity

- `v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md`
- `v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md`
- `v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md`

## Current Path / Exit References

- `v1-tfi-small-path-manager-20260519_ccusdt_v1_tfi_small_path_manager_v1.md`
- `v1-tfi-post-exit-watcher-20260519_ccusdt_v1_tfi_post_exit_watcher_v1.md`

## Current Interpretation

- Active branch: simple v1 TFI runtime state machine plus research diagnostics.
- Taker IOC is the current execution baseline; spread is still a cost even when venue fee is zero.
- Capacity/profile/lot lifecycle must be compared consistently between fast and strict.
- `Delta_bps/Energy_bps`, OFI/MLOFI, dynamic L2 path prediction, and deep
  learning remain research references; they have not entered current CC runtime
  control.
- Maker-first and v2 execution lines are not current unless the user explicitly resumes them.

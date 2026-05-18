# CCUSDT V1 TFI Current Strategy Handoff

Status: 2026-05-18.

This is the current live handoff for the CCUSDT/CEX L2 TFI strategy branch. It supersedes the earlier v2 execution no-go framing for the current conversation. Do not restart from the old "all practical no-go" conclusion unless the user explicitly redirects back to v2 execution-repair work.

## Current Thesis

The useful structure is not a median-positive strategy. Net medians are already cost-adjusted and can remain negative while the right tail is tradable. Do not discard states only because `net_median < 0`.

The current main structure is:

$$
A_t=\mathbf{1}\{R_5(t)>1\},\quad B_t=\mathbf{1}\{F_t\ge q_{90}\}
$$

with mutually exclusive cells:

```text
00 = not R5, not stale
10 = R5 only
01 = stale only
11 = R5 and stale
```

where `F_t = frames_since_mid_change` and `R5` is computed only from entries already closed before the current entry timestamp.

## Key Mathematical Correction

`R5` is only a ratio:

$$
R_k=\frac{P_k}{N_k+\epsilon}
$$

It must be decomposed into absolute strength:

$$
\Delta_k=P_k-N_k,\quad E_k=P_k+N_k,\quad Z_k=\frac{\Delta_k}{\sqrt{E_k+\epsilon}}
$$

The working model family is:

$$
w_t=b_t\cdot\gamma_{A_tB_t}\cdot\psi_t\cdot\phi_t
$$

where:

- `b_t` is the locked base entry weight.
- `gamma_{A_tB_t}` is the four-cell state size.
- `psi_t` is an absolute-strength gate or ramp using `Delta/Z`.
- `phi_t` is an optional recent-loss suppressor.

## Latest Optimized Result

The latest interpretable grid/Pareto search tested `16960` candidates with prior-date quantile thresholds only.

Old anchor:

$$
(\gamma_{10},\gamma_{01},\gamma_{11})=(0.75,0.25,4)
$$

Result over the 9 walk-forward test days:

```text
total_net      = 6808.4686
mean_net       = 4.4171 bps
worst_day_net  = -58.2736
positive_days  = 8/9
entries        = 1418
```

Main Pareto/risk-score leader:

$$
(\gamma_{10},\gamma_{01},\gamma_{11})=(1.25,0.75,5)
$$

with:

$$
closed10\_score\_abs \ge Q_{30}^{train}
$$

Result:

```text
total_net      = 9001.3476
mean_net       = 5.0248 bps
worst_day_net  = 12.8156
positive_days  = 9/9
entries        = 1116
exposure       = 1791.3750
```

More conservative Pareto point:

$$
(\gamma_{10},\gamma_{01},\gamma_{11})=(1.25,0.25,5)
$$

with the same `closed10_score_abs >= Q30 train` gate:

```text
total_net      = 8819.5895
mean_net       = 5.0372 bps
worst_day_net  = 23.5851
positive_days  = 9/9
```

The no-strength high-gamma point reaches higher raw total but has unacceptable daily left tail:

```text
gamma=(1.25,0.75,5), no strength gate
total_net      = 9123.4940
worst_day_net  = -167.3131
```

So the latest conclusion is: absolute-strength gating is structural, not cosmetic.

## Important Caveat

The daily frontier is strong, but single-entry left tail expands when `gamma11=5`:

```text
entry_worst_pnl = -311.1463
entry_cvar05    about -74.65
```

Any live-sizing layer must cap single-entry risk separately. Do not infer account leverage from these gamma multipliers. They are relative strategy size multipliers.

## Latest Documents

Start here:

```text
docs/markets/ccusdt/v1-tfi-interpretable-grid-pareto-20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.md
```

Then read:

```text
docs/markets/ccusdt/v1-tfi-worst-day-frontier-20260518_ccusdt_v1_tfi_worst_day_frontier_v1.md
docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.md
docs/markets/ccusdt/v1-tfi-pretrade-identification-20260518_ccusdt_v1_tfi_pretrade_identification_v1.md
docs/markets/ccusdt/v1-tfi-momentum-conversion-first-principles-20260518_ccusdt_v1_tfi_momentum_conversion_math_v1.md
```

## Latest Scripts

```text
scripts/ccusdt_v1_tfi_interpretable_grid_pareto.py
scripts/ccusdt_v1_tfi_worst_day_frontier.py
scripts/ccusdt_v1_tfi_strategy_sizing_opt.py
scripts/ccusdt_v1_tfi_pretrade_identification.py
scripts/ccusdt_v1_tfi_momentum_conversion_math.py
```

Run latest Pareto search:

```bash
python scripts/ccusdt_v1_tfi_interpretable_grid_pareto.py
```

## Local Output Tables

The `date/` directory is intentionally git-ignored. In this local workspace, latest outputs are:

```text
date/ccusdt_v1_tfi_interpretable_grid_variants_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv
date/ccusdt_v1_tfi_interpretable_grid_pareto_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv
date/ccusdt_v1_tfi_interpretable_grid_daily_top_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv
date/ccusdt_v1_tfi_worst_day_frontier_20260518_ccusdt_v1_tfi_worst_day_frontier_v1.csv
date/ccusdt_v1_tfi_strategy_sizing_*_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.*
date/ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv
```

## Next Recommended Work

1. Add a single-entry risk cap around the Pareto leader.
2. Re-evaluate the Pareto family on new OOS days before live use.
3. Systematically test classic LOB factors only after this checkpoint: depth shape, VWAP liquidity cost, OBI/microprice, OFI/MLOFI, replenishment/cancel intensity, and resiliency.


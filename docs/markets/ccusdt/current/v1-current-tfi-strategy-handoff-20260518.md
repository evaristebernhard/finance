# CCUSDT V1 TFI Current Strategy Handoff

Status: 2026-05-18.

Read first:

```text
docs/markets/ccusdt/current/CURRENT_STRATEGY_PLAIN.md
```

This handoff mixes current runtime facts, historical research evidence, and
follow-up hypotheses. It is not a precise inventory of Bot runtime behavior.
In particular, `Delta/Energy/Z`, Pareto controls, path/exit research, and
maker/execution ideas are research references unless explicitly stated as
implemented in the runtime strategy.

This is the current live handoff for the CCUSDT/CEX L2 TFI strategy branch. It supersedes the earlier v2 execution no-go framing for the current conversation. Do not restart from the old "all practical no-go" conclusion unless the user explicitly redirects back to v2 execution-repair work.

## Current Thesis

The useful structure is not a median-positive strategy. Net medians are already cost-adjusted and can remain negative while the right tail is tradable. Do not discard states only because `net_median < 0`.

The current first-principles map is path-first, not Pareto-first:

```text
docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md
```

Do not forget the canonical failure row:

```text
2026-05-09 / entry_row=1615412 / 11_r5_frames / short
MFE=+12.5612bps at 4.7051s
R_60=-27.8923bps
decay_60=40.4535bps
exposure=8
target_pnl=-242.4187
```

This is the cleanest reminder that the strategy problem is not just entry
selection. A good fast release can become a large fixed-60s loss if sizing is
large and decay is not managed.

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

Under the old explicit-cost label, the conclusion was: absolute-strength gating is structural, not cosmetic.

## Zero-Fee Pareto Rerun

Bullish CC/USDT currently appears to be in a promotional `0/0` maker/taker fee group, so the previous Pareto family was rerun with:

$$
C_{fee}=0,\quad net:=gross
$$

Full rerun means the upstream pretrade scored entries are regenerated first under `C=0`; then Pareto reads those scored entries. This is different from merely replacing `net` inside the Pareto script after the fact.

Current zero-fee four-quadrant report:

```text
docs/markets/ccusdt/v1-tfi-pretrade-identification-20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.md
docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.md
python scripts/ccusdt_v1_tfi_pretrade_identification.py --cost-mode zero_fee --run-tag 20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1
python scripts/ccusdt_v1_tfi_strategy_sizing_opt.py --scored-entries date/ccusdt_v1_tfi_pretrade_scored_entries_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv --max-leverage 7 --hold-seconds 60 --run-tag 20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1
```

This is the correct rerun for the old four-quadrant sizing question because it allows:

$$
\gamma=(\gamma_{00},\gamma_{10},\gamma_{01},\gamma_{11}),\qquad \gamma_{00}\in[0,1].
$$

The earlier zero-fee `interpretable_grid_pareto` report is archived as a side diagnostic because it is not the current answer to this four-quadrant question. That family fixes `gamma00=0` and adds extra gates:

```text
docs/markets/ccusdt/archive/diagnostics/v1-tfi-interpretable-grid-pareto-20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.md
```

Walk-forward mutually exclusive cell stats under `C=0`:

```text
00_none        entries=850   exposure=441.5000  total=1422.2911  mean=3.2215  positive_days=9/9  worst_day=+54.0890
01_frames_only entries=105   exposure=187.5000  total= 782.9229  mean=4.1756  positive_days=7/9  worst_day=-30.5654
10_r5_only     entries=1351  exposure=707.0000  total=2785.7372  mean=3.9402  positive_days=9/9  worst_day=+10.1229
11_r5_frames   entries=171   exposure=272.0000  total=1971.8641  mean=7.2495  positive_days=9/9  worst_day=+35.1862
```

Raw walk-forward chosen policy:

```text
chosen gamma each test day = (1, 2, 1, 4)
total_net                  = 15664.1450
mean_net                   = 5.0029 bps
worst_day_net              = +277.4534
positive_days              = 9/9
max_concurrent_exposure    = 18.0000
cap_by_exchange_leverage   = 0.3889
feasible_cap_min_100budget = 0.3889
scaled_total_feasible      = 6091.6120
```

Highest raw in-sample risk-score variant:

```text
gamma=(1,2,1,4)
total_net                = 17056.4826
mean_net                 = 4.2829 bps
worst_day_net            = +97.5812
max_concurrent_exposure  = 18.0000
cap_by_exchange_leverage = 0.3889
exchange_scaled_total    = 6633.0766
entry_cvar05             = -38.0663
```

After only the 60s-concurrency 7x exchange cap, the highest exchange-scaled Pareto point is not the raw high-gamma point:

```text
locked_baseline_all_1x
total_net                = 7625.0300
max_concurrent_exposure  = 5.0000
cap_by_exchange_leverage = 1.4000
exchange_scaled_total    = 10675.0420
```

Under the combined `100` bp-unit loss budget plus 7x cap, the best simple fixed policy by scaled total is:

```text
locked_baseline_all_1x
total_net             = 6962.8154
feasible_cap_min      = 1.1821
scaled_total_feasible = 8230.8434
```

Next fixed-policy rows under the same combined cap:

```text
broad_only_1x                         scaled_total_feasible = 6512.2130
walk_forward_chosen                   scaled_total_feasible = 6091.6120
conservative_four_cell_0p25_1_0p25_2  scaled_total_feasible = 5662.8203
```

Interpretation: with explicit fee label set to zero, all four cells become usable on the tested window, including `00`. This zero-fee label is the correct current venue-fee baseline, not a misleading assumption. Raw PnL favors high `gamma11` and high `gamma10`, but 7x concurrency normalization makes lower-concurrency policies competitive or better. Since every fixed policy has positive worst-day PnL in this zero-fee test window, the 100 bp-unit daily loss budget does not bind; the combined cap is driven by single-entry left tail and 60s concurrent exposure.

A reasonable strategy should then survive an additional pressure term:

$$
y_i(c)=R_i(\tau_i^{exit})-C_{fee,i}-c,\qquad C_{fee,i}=0,\quad c>0.
$$

The stress term is reserve for spread crossing, maker fill probability, queue position, latency, adverse selection, and path decay; it is not the same as adding back a venue fee that is currently zero.

## Important Caveat

The zero-fee four-quadrant result is strong because explicit venue fee is currently zero, not because the market became execution-free. The main live caveats are:

```text
1. C_fee=0 removes only the explicit maker/taker fee label.
2. 60s-concurrency leverage is a research proxy, not exchange margin accounting.
3. High raw gamma policies hit max_concurrent_exposure=18, so 7x caps them to about 0.3889 global scale.
4. Live sizing should compare raw PnL, exchange-scaled PnL, and loss-budget-scaled PnL separately.
```

Do not infer account leverage directly from gamma multipliers. They are relative strategy size multipliers; account leverage is a separate global scale.

## 2026-05-09 High/Chop Accident Read

Latest deep dive:

```text
docs/markets/ccusdt/v1-tfi-0509-high-chop-deep-dive-20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.md
scripts/ccusdt_v1_tfi_0509_high_chop_deep_dive.py
```

The `2026-05-09 high/chop` group is not a broad high/chop failure. It has `9` entries and total target PnL `-233.6197`, but one `11_r5_frames / short` row (`entry_row=1615412`) contributes `-242.4187` at exposure `8`; removing it leaves the focus group at `+8.7990`.

The more precise accident surface is the matched `11_r5_frames / short / q70_85 / delta10=s80_100` bucket. On `2026-05-09` it has `6` entries, total PnL `-642.9602`, and `0%` `net>2bps`; excluding `2026-05-09`, the same bucket is `+1405.8597`. So do not blanket-ban high/chop or the global bucket. The repair hypothesis is single-entry `11` risk cap plus exit-shape/trailing-risk diagnostics for fast favorable MFE followed by reversal.

## Release/Decay Path Read

Latest release/decay factor pass:

```text
docs/markets/ccusdt/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md
scripts/ccusdt_v1_tfi_release_decay_factor_analysis.py
```

This pass rebuilds paths for `1455` entries on dates where the v3 fixed event panel is local (`2026-05-04..2026-05-15`). It separates:

```text
release = MFE_h
decay   = MFE_60 - R_60
```

Main result: mean `MFE_10=3.6668bps`, mean `R_60=4.2577bps`, mean `decay_60=5.6716bps`; `P(MFE_10>=5bps)=26.94%`, while `P(MFE_10>=5bps and R_60<0)=6.32%`.

Factor interpretation: low opposite-side depth / low `Theta_t` predicts fast release, but also predicts larger decay conditional on early release. That is a liquidity-vacuum release shape. The dynamic decay warning is simpler: after early release, sustained signed flow from `5s` to `20s` matters. `signed_tfi_mean_5_20s`, `signed_mlofi5_mean_5_20s`, and `signed_ofi_mean_5_20s` are the cleanest early-path factors for lower 60s decay. Queue imbalance alone is ambiguous and should not be treated as continuation without flow/replenishment context.

## Exit Walk-Forward Read

Latest frozen-candidate exit validation:

```text
docs/markets/ccusdt/v1-tfi-exit-walkforward-20260518_ccusdt_v1_tfi_exit_walkforward_v1.md
scripts/ccusdt_v1_tfi_exit_walkforward.py
```

Design: local v3 paths rebuilt for `1455` entries; test dates are `2026-05-09..2026-05-15` after `5` prior training dates. Candidate set is fixed in advance: fixed `10/20/30/60s`, TP+timeout, one-factor flow-confirmed hold with prior-date quantile thresholds, and simple exposure caps. Baseline is `fixed_60s`.

Key results:

```text
fixed_60s total = 5713.5706, worst_day = -59.0662, q90 = 21.8468
fixed_30s total = 4403.5926, worst_day = +9.3507, positive_days = 7/7, q90 retention = 0.6768
best flow gate = flow_hold_signed_ofi_mean_5_20s_q50_exit20s
best flow total = 6790.1403, worst_day = -42.6939, q90 retention = 0.8520
```

Interpretation: `fixed_30s` is a clean risk-control baseline but sacrifices too much right tail to be a final answer. TP+timeout is not supported; it kills winners. Flow-confirmed hold is the only family that improves total while retaining much of the right tail, but it is still a path-dependent hypothesis, not a promoted rule. It uses `5s..20s` flow, so the decision time and execution realism must be explicit before live relevance.

## Price-Only Trailing Parameter Read

Latest simple trading-parameter pass:

```text
docs/markets/ccusdt/v1-tfi-price-trailing-param-research-20260519_ccusdt_v1_tfi_price_trailing_param_v1.md
scripts/ccusdt_v1_tfi_price_trailing_param_research.py
```

This pass deliberately removes OFI/MLOFI/depth/latent-state exit factors and tests only signed price path:

$$
R_i(t)=s_i10^4\log\frac{M_{t_i+t}}{M_{t_i}},\quad
H_i(t)=\max_{0<u\le t}R_i(u),\quad
D_i(t)=H_i(t)-R_i(t)
$$

with prior-date release threshold:

$$
r_i=\max(c_i+m,\ Q_p^{train}(H_{10}))
$$

and trailing exit after release:

$$
D_i(t)\ge \max(c_i+m,\ \eta H_i(t)).
$$

Design: `5` prior train days, test dates `2026-05-09..2026-05-15`, fixed `20/30/60s` baselines, and a small grid over `p in {60,70,80}%`, `eta in {0.30,0.50}`, activation `10/20s`.

Best risk-score candidate:

```text
trail_p80_eta30_act10s
entries        = 1158
total_pnl      = 6162.1109
fixed60 total  = 5713.5706
delta_total    = +448.5403
worst_day      = -39.5948
fixed60 worst  = -59.0662
q90 retention  = 0.8232
activated_rate = 28.93%
trail_exit_rate= 16.84%
```

Daily read: it improves versus `fixed_60s` on all `7/7` test dates, but does not make all dates profitable; `2026-05-13` remains negative (`-39.5948`). `fixed_30s` still has the cleanest daily left tail (`7/7` positive days) but loses too much right tail and total PnL. So the price-only trailing rule is a reasonable candidate for release/decay risk shaping, not a solved live-execution rule. The threshold is not a posterior `10bps`: train-only `Q80(H_10)` sits around `4.08..5.91` bps across test dates.

## Latest Documents

Start here:

```text
docs/markets/ccusdt/v1-tfi-pretrade-identification-20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.md
docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md
docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.md
docs/markets/ccusdt/v1-tfi-price-trailing-param-research-20260519_ccusdt_v1_tfi_price_trailing_param_v1.md
docs/markets/ccusdt/v1-tfi-exit-walkforward-20260518_ccusdt_v1_tfi_exit_walkforward_v1.md
docs/markets/ccusdt/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md
docs/markets/ccusdt/v1-tfi-0509-high-chop-deep-dive-20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.md
docs/markets/ccusdt/v1-tfi-latent-state-panel-20260518_ccusdt_v1_tfi_latent_state_panel_v1.md
docs/markets/ccusdt/v1-tfi-latent-state-taxonomy-20260518_ccusdt_v1_tfi_latent_state_taxonomy_v1.md
docs/markets/ccusdt/v1-tfi-entry-estimation-20260518_ccusdt_v1_tfi_entry_estimation_v1.md
docs/markets/ccusdt/v1-tfi-interpretable-grid-pareto-20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.md
```

Then read:

```text
docs/markets/ccusdt/v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md
docs/markets/ccusdt/v1-tfi-worst-day-frontier-20260518_ccusdt_v1_tfi_worst_day_frontier_v1.md
docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.md
docs/markets/ccusdt/v1-tfi-pretrade-identification-20260518_ccusdt_v1_tfi_pretrade_identification_v1.md
docs/markets/ccusdt/v1-tfi-momentum-conversion-first-principles-20260518_ccusdt_v1_tfi_momentum_conversion_math_v1.md
```

## Latest Scripts

```text
scripts/ccusdt_v1_tfi_price_trailing_param_research.py
scripts/ccusdt_v1_tfi_interpretable_grid_pareto.py
scripts/ccusdt_v1_tfi_exit_walkforward.py
scripts/ccusdt_v1_tfi_release_decay_factor_analysis.py
scripts/ccusdt_v1_tfi_0509_high_chop_deep_dive.py
scripts/ccusdt_v1_tfi_latent_state_panel.py
scripts/ccusdt_v1_tfi_entry_estimation.py
scripts/ccusdt_v1_tfi_factor_decomposition.py
scripts/ccusdt_v1_tfi_worst_day_frontier.py
scripts/ccusdt_v1_tfi_strategy_sizing_opt.py
scripts/ccusdt_v1_tfi_pretrade_identification.py
scripts/ccusdt_v1_tfi_momentum_conversion_math.py
```

Run latest Pareto search:

```bash
python scripts/ccusdt_v1_tfi_strategy_sizing_opt.py --scored-entries date/ccusdt_v1_tfi_pretrade_scored_entries_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv --max-leverage 7 --hold-seconds 60 --run-tag 20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1
```

## Local Output Tables

The `date/` directory is intentionally git-ignored. In this local workspace, latest outputs are:

```text
date/ccusdt_v1_tfi_interpretable_grid_variants_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv
date/ccusdt_v1_tfi_interpretable_grid_pareto_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv
date/ccusdt_v1_tfi_interpretable_grid_daily_top_20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.csv
date/ccusdt_v1_tfi_pretrade_scored_entries_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv
date/ccusdt_v1_tfi_pretrade_gate_scorecard_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv
date/ccusdt_v1_tfi_pretrade_static_feature_scorecard_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv
date/ccusdt_v1_tfi_pretrade_identification_summary_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.json
date/ccusdt_v1_tfi_interpretable_grid_variants_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.csv
date/ccusdt_v1_tfi_interpretable_grid_pareto_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.csv
date/ccusdt_v1_tfi_interpretable_grid_daily_top_20260519_ccusdt_v1_tfi_interpretable_grid_pareto_zero_fee_full_v1.csv
date/ccusdt_v1_tfi_price_trailing_base_paths_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv
date/ccusdt_v1_tfi_price_trailing_events_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv
date/ccusdt_v1_tfi_price_trailing_scorecard_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv
date/ccusdt_v1_tfi_price_trailing_daily_20260519_ccusdt_v1_tfi_price_trailing_param_v1.csv
date/ccusdt_v1_tfi_price_trailing_summary_20260519_ccusdt_v1_tfi_price_trailing_param_v1.json
date/ccusdt_v1_tfi_entry_estimates_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv
date/ccusdt_v1_tfi_entry_estimator_diagnostics_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv
date/ccusdt_v1_tfi_entry_estimator_daily_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv
date/ccusdt_v1_tfi_entry_bucket_snapshot_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv
date/ccusdt_v1_tfi_latent_state_panel_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv
date/ccusdt_v1_tfi_latent_state_daily_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv
date/ccusdt_v1_tfi_latent_state_quality_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv
date/ccusdt_v1_tfi_latent_state_score_tests_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv
date/ccusdt_v1_tfi_worst_day_frontier_20260518_ccusdt_v1_tfi_worst_day_frontier_v1.csv
date/ccusdt_v1_tfi_strategy_sizing_*_20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.*
date/ccusdt_v1_tfi_strategy_sizing_*_20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.*
date/ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv
```

## Next Recommended Work

1. Re-evaluate the Pareto family plus the price-only trailing candidate on new OOS days before live use.
2. Add a single-entry risk cap around the Pareto leader; do not infer account leverage from gamma multipliers.
3. If continuing exit work, keep the candidate set small: compare `fixed_60s`, `fixed_30s`, and `trail_p80_eta30_act10s` under explicit latency/fill assumptions rather than expanding another large TP/SL grid.
4. Systematically test classic LOB factors only after this checkpoint: depth shape, VWAP liquidity cost, OBI/microprice, OFI/MLOFI, replenishment/cancel intensity, and resiliency.

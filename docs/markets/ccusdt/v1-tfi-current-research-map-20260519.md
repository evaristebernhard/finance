# CCUSDT V1 TFI Current Research Map

Status: `20260519_path_first_research_map`.

Guardrail: research map only; no execution recommendation.

## First Principle

The current TFI phenomenon should be read as a path problem, not a static
entry-score problem.

For entry direction \(s_i\), define the signed mid path:

$$
R_i(\tau)=s_i10^4\log\frac{M_{t_i+\tau}}{M_{t_i}}.
$$

The 60s label is only one terminal projection:

$$
y_i(60)=R_i(60)-C_i.
$$

But the economic object is:

$$
R_i(60)=H_i(60)-D_i(60),
$$

where:

$$
H_i(h)=\max_{0<u\le h}R_i(u),\qquad D_i(h)=H_i(h)-R_i(h).
$$

So the core decomposition is:

$$
\mathrm{entry\ edge}
\rightarrow
\mathrm{release}
\rightarrow
\mathrm{post\ release\ decay}.
$$

Optimizing only 60s terminal PnL can confuse a good fast-release entry with a
bad 60s holding policy.

## Canonical Failure Case

The row that must stay visible in every handoff is:

```text
date        = 2026-05-09
entry_row   = 1615412
cell        = 11_r5_frames
direction   = short
bucket      = q70_85 / delta10=s80_100
net         = -30.3023 bps
exposure    = 8.0000
target_pnl  = -242.4187
```

Path facts:

```text
MFE           = +12.5612 bps
time_to_MFE   = 4.7051 s
R_60          = -27.8923 bps
MAE           = -29.4569 bps
decay_60      = 40.4535 bps
```

This was not a plain bad-entry example. It released quickly, then decayed hard
inside the fixed 60s horizon. The oversized loss came from:

$$
8\times(-30.3023)\approx -242.4.
$$

Therefore the direct lesson is not "ban high/chop" and not "drop the bucket".
It is:

$$
\mathrm{large\ } \gamma_{11}
\times
\mathrm{fixed\ 60s\ hold}
\times
\mathrm{fast\ release\ then\ decay}
=
\mathrm{left\ tail}.
$$

## Current Document Priority

Read in this order:

1. `v1-current-tfi-strategy-handoff-20260518.md`
2. `v1-tfi-current-research-map-20260519.md`
3. `v1-tfi-0509-high-chop-deep-dive-20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.md`
4. `v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md`
5. `v1-tfi-exit-walkforward-20260518_ccusdt_v1_tfi_exit_walkforward_v1.md`
6. `v1-tfi-price-trailing-param-research-20260519_ccusdt_v1_tfi_price_trailing_param_v1.md`
7. `v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md`
8. `v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md`
9. `v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md`
10. `v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md`
11. `v1-tfi-strategy-sizing-opt-20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.md`

The sizing reports are useful, but they are downstream. They should not be read
as the mechanism.

## Cost Baseline And Pressure

Zero fee is the current venue-fee baseline, not a misleading assumption:

$$
C_{fee,i}=0.
$$

But zero venue fee is not zero execution pressure. The strategy objective should
be tested as:

$$
y_i(c)=R_i(\tau_i^{exit})-C_{fee,i}-c,\qquad c>0,
$$

where \(c\) is a stress reserve for spread crossing, maker fill uncertainty,
queue position, latency, adverse selection, and post-release decay. In other
words, the right comparison is not:

$$
C_{fee}=0 \Rightarrow \mathrm{all\ raw\ edge\ is\ executable}.
$$

The right comparison is:

$$
\mathrm{venue\ baseline}\ C_{fee}=0
\quad\text{and}\quad
\mathrm{robustness\ check}\ c>0.
$$

## Current Mechanism Read

The useful entry states still matter:

$$
A_i=\mathbf{1}\{R_{5,i}>1\},\qquad
B_i=\mathbf{1}\{F_i\ge Q_{90}\}.
$$

But \(A_i,B_i\) identify entry pressure/staleness; they do not decide how long
the release should be held.

The path labels are:

$$
\mathrm{release}_i=\mathbf{1}\{H_i(10)\ge r_i\},
$$

$$
\mathrm{decay}_i=D_i(60)=H_i(60)-R_i(60).
$$

The key empirical facts from the release/decay pass:

```text
mean MFE_10                         = 3.6668 bps
mean R_60                           = 4.2577 bps
mean decay_60                       = 5.6716 bps
P(MFE_10 >= 5bps)                   = 26.94%
P(MFE_10 >= 5bps and R_60 < 0)      = 6.32%
```

Low opposite-side depth predicts faster release, but also larger decay after
release. That is a liquidity-vacuum shape: the book lets price move quickly,
but the move is not always persistent.

After early release, the useful continuation diagnostic is sustained signed
flow from 5s to 20s:

```text
signed_tfi_mean_5_20s
signed_mlofi5_mean_5_20s
signed_ofi_mean_5_20s
```

Queue imbalance alone is ambiguous; it should not be treated as continuation
without flow/replenishment context.

## Path Casebook Classes

Latest report:

```text
docs/markets/ccusdt/v1-tfi-path-casebook-20260519_ccusdt_v1_tfi_path_casebook_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_path_casebook_classes.py
```

This pass treats a case as a path mechanism, not as a losing label. A profitable
entry can still be a case if it has the same release/decay geometry as a losing
entry.

The four simple mutually exclusive case classes are:

$$
\begin{aligned}
\mathrm{no\ release}:&\quad H_{60}<3,\\
\mathrm{large\ plateau}:&\quad H_{20}\ge10,\ E_{20}\ge0.75,\ \tau_H\le20,\ D_{60}\ge10,\\
\mathrm{late\ release}:&\quad H_{60}\ge5,\ \tau_H\ge20,\ D_{60}\ge8,\\
\mathrm{fast\ reversal}:&\quad H_{60}\ge4,\ \tau_H\le5,\ D_{60}\ge8.
\end{aligned}
$$

Current counts on `1455` entries:

```text
non_case                         738 entries, C=0 weighted gross +10454.4421
no_release_flat                  558 entries, C=0 weighted gross  -1812.0376
fast_release_reversal             41 entries, C=0 weighted gross   -936.2399
large_release_plateau_decay       25 entries, C=0 weighted gross   +306.4902
late_release_collapse             93 entries, C=0 weighted gross   +892.1041
```

Important read: `large_release_plateau_decay` and
`late_release_collapse` are not "bad-entry" labels. Both include profitable
entries and are positive in aggregate under the stored exposure lens. The
pathology is that fixed 60s holding leaves released profit exposed to decay.

Canonical row placement:

```text
1615412 -> fast_release_reversal
2377379 -> fast_release_reversal
2361187 -> large_release_plateau_decay
1604781 / 1580108 / 1642948 / 2032427 / 2577885 -> no_release_flat
1785626 / 2334597 / 2540829 -> late_release_collapse
```

## Small Path Manager

Latest report:

```text
docs/markets/ccusdt/v1-tfi-small-path-manager-20260519_ccusdt_v1_tfi_small_path_manager_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_small_path_manager.py
```

The useful result is not a universal exit overlay. Broad path management cuts
too much right tail. The current small candidate is risk-gated:

$$
\mathrm{manage}_i=\mathbf{1}\{\mathrm{cell}_i=11\_r5\_frames\}.
$$

For managed entries only:

$$
\tau=\inf\{t:\ H_t\ge4,\ D_t\ge\max(2,0.35H_t)\}.
$$

To avoid treating an opening flicker as a real small release:

$$
H_t<8\Rightarrow \tau_H\ge1.5.
$$

Current C=0 stored-exposure result:

```text
fixed_60s                         total 8904.7590, q90 retention 1.0000
pm_11_drawdown_h4_peakguard       total 9554.1874, delta +649.4284
                                  q90 retention 0.9966, action exit rate 2.82%
fixed_30s                         total 7446.9709, q90 retention 0.6884
pm_drawdown_plateau               total 8078.4804, overcuts right tail
pm_full_tiny                      total 8160.7921, no-release timeout overcuts right tail
```

Case transfer for `pm_11_drawdown_h4_peakguard`:

```text
non_case                         -438.1403
no_release_flat                     0.0000
fast_release_reversal            +605.7351
large_release_plateau_decay      +346.6153
late_release_collapse            +135.2182
```

Important read: this is a small insurance layer on high-exposure entries, not a
new entry filter. It rescues `1615412`, `2377379`, and `2361187`, but it still
mis-handles some late-release winners, especially `2583437`, where an early
drawdown is followed by a much larger later continuation. That residual class is
the next thing to understand before making the exit more aggressive.

Deep dive for `2583437`:

```text
docs/markets/ccusdt/v1-tfi-2583437-path-deep-dive-20260519.md
```

The special shape is:

$$
\mathrm{dormant\ vacuum}
\rightarrow
\mathrm{first\ release}
\rightarrow
\mathrm{drawdown/reset}
\rightarrow
\mathrm{multi\ pulse\ continuation}.
$$

It has the largest sample-wide \(H_{60}-H_{20}\), at `110.2681bps`.

## Post-Exit Re-Trigger Diagnostic

Latest report:

```text
docs/markets/ccusdt/v1-tfi-post-exit-retrigger-diagnostic-20260519_ccusdt_v1_tfi_post_exit_retrigger_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_post_exit_retrigger_diagnostic.py
```

This pass treats the drawdown exit as natural. The question is not whether
`2583437` should have been held. The question is whether the path gives a new
observable trigger after the exit.

In post-exit coordinates:

$$
\widetilde R_i(u)=10^4s_i\log\frac{M_{\tau_i+u}}{M_{\tau_i}},
$$

where \(\tau_i\) is the drawdown exit time. At observation horizon \(g\):

$$
Q_i(g)=\frac{1}{g}\int_0^g s_iQI_5(\tau_i+u)\,du,
$$

$$
F_i(g)=\sum_{0<u\le g}s_iTFI(\tau_i+u),
$$

$$
C_i(g)=\widetilde R_i(g)-\min_{0\le u\le g}\widetilde R_i(u).
$$

The strict 5s diagnostic is:

$$
Q_i(5)\ge0.7,\qquad F_i(5)>0,\qquad C_i(5)\ge1.
$$

On the `41` drawdown exits from `pm_11_drawdown_h4_peakguard`, it finds:

```text
g=5s: predicted retriggers 1, productive labels 6
      true positive 1, false positive 0, false negative 5
      precision 1.0000, recall 0.1667
      reentry final pnl +200.3343, reentry mfe +383.0968
```

The only strict 5s re-trigger is `2583437`:

```text
obs_signed_qi5_mean_5s    +0.8876
obs_signed_tfi_sum_5s    +11.0000
obs_reclaim_5s            +1.6094
future_mfe_after_5s      +95.7742
future_final_after_5s    +50.0836
```

The important negative controls are:

```text
2377379: queue favorable, but post-exit same-side TFI negative; reject.
1615412: price bounces, but queue/flow are not supportive; reject.
2361187: queue near threshold, but flow/reclaim fail; reject.
```

This should be read as a high-precision diagnostic witness, not a complete
re-entry strategy. The first exit can be correct, and a later re-entry can also
be correct if fresh queue + flow + reclaim reappear.

## Post-Exit Watcher

Latest report:

```text
docs/markets/ccusdt/v1-tfi-post-exit-watcher-20260519_ccusdt_v1_tfi_post_exit_watcher_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_post_exit_watcher.py
```

This pass turns the diagnostic into a small watcher family. It still starts
only after the drawdown exit, so it does not weaken the original exit rule.

The watcher has two branches:

$$
\mathrm{impulse}:
\quad
Q_i(5)\ge0.7,\quad F_i(5)>0,\quad C_i(5)\ge1.
$$

and

$$
\mathrm{absorption}:
\quad
Q_i(5)\ge q_a,\quad F_i(5)<0,
$$

followed by a reset-low reclaim:

$$
\tau_a=
\inf\{u>5:
\widetilde R_i(u)-L_i(5)\ge r_a,
\widetilde R_i(u)\le5,
\min_{5<v\le u}\widetilde R_i(v)\ge L_i(5)-5,
T_i-u\ge5
\}.
$$

Here:

$$
L_i(5)=\min_{0\le v\le5}\widetilde R_i(v).
$$

The cap \(\widetilde R_i(u)\le5\) is important. Without it, the watcher chases
late spikes like `2540829`, which then collapses.

Current result on the `41` drawdown exits:

```text
impulse_only:
  triggers 1, weighted final +220.9383, no negative trigger

watcher_q70_absorb_reclaim2:
  triggers 3 = 1 impulse + 2 absorption
  weighted final +522.1939, weighted MFE +704.9564
  worst trigger +87.6881, negative triggers 0
  manager total 9554.1874 -> 10076.3813

watcher_q65_absorb_reclaim2:
  triggers 5 = 1 impulse + 4 absorption
  weighted final +803.2748, weighted MFE +986.0373
  worst trigger +32.7318, negative triggers 0
  manager total 9554.1874 -> 10357.4622
```

Important controls:

```text
watcher_q70 catches: 2583437, 2322885, 2379419
watcher_q70 rejects: 1615412, 2377379, 2340079, 2361187, 2383289, 2540829

watcher_q65 additionally catches: 2340079, 2361187
watcher_q65 still rejects: 1615412, 2377379, 2383289, 2540829
```

Read:

```text
q70 is the cleaner candidate.
q65 is a recall sensitivity, not a live setting.
```

## Watcher-Aware Pareto

Latest report:

```text
docs/markets/ccusdt/v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_watcher_pareto.py
```

This pass supersedes the earlier A/B-only watcher Pareto. The current pass
uses the full scored four-cell universe:

```text
full scored four-cell universe
-> pm_11_drawdown_h4_peakguard where rebuilt
-> fixed60 fallback where path is not rebuilt
-> optional post-exit watcher where rebuilt
-> gamma sizing by mutually exclusive cell, including 00
```

Scope:

```text
3365 entries
2026-05-04..2026-05-17
00_none          1234
10_r5_only       1796
01_frames_only    135
11_r5_frames      200

path_manager_rebuilt 1455
fixed60_fallback     1910
```

The full anchor decomposes as:

$$
\gamma^{anchor}_{00}=1,\qquad
\gamma^{anchor}_{10}=0.75,\qquad
\gamma^{anchor}_{01}=0.25,\qquad
\gamma^{anchor}_{11}=4.
$$

At the full anchor, q70 watcher still adds the same three second entries,
but the old high-\(11\) sizing remains concurrency/risk constrained:

```text
manager_only                 total 13277.3761
manager_plus_q70_watcher     total 13799.5700
q70 watcher delta            total   522.1939
anchor q70 max concurrency   18.0000
anchor q70 scaled100         2299.9283
```

The cleaner q70 scaled leader is:

```text
strategy   manager_plus_q70_watcher
gamma      gamma00=1.25, gamma10=0.75, gamma01=0.0, gamma11=0.75
raw total  6042.8705
mean       3.4965
worst day +8.2022
entry worst -76.0697
max conc   3.3750
scaled100  5371.4405
```

At that q70 leader, `00` is not garbage exposure; it contributes positive
historical PnL, though only through fixed60 fallback:

```text
00_none          total 1935.3368, mean 2.4382, exposure 793.7500
10_r5_only       total 2279.9815, mean 3.2548, exposure 700.5000
01_frames_only   total    0.0000, mean n/a,    exposure   0.0000
11_r5_frames     total 1827.5522, mean 7.8101, exposure 234.0000
```

The q65 sensitivity has slightly higher scaled value:

```text
q65 best scaled100 5418.2873
q70 best scaled100 5371.4405
difference            46.8468
```

This difference is too small to promote q65. It remains a recall sensitivity.

Pressure behavior changes under the stricter 3x cap: under 1bps pressure, q70
still prefers the same low-concurrency point. Under 2bps pressure, q70 drops
`00` entirely and shifts exposure toward `10/01/11`:

```text
C=1 q70: gamma00=1.25, gamma10=0.75, gamma01=0.0,  gamma11=0.75, scaled100 3832.8849
C=2 q70: gamma00=0.0,  gamma10=1.25, gamma01=0.75, gamma11=1.5,  scaled100 1999.7536
```

Read:

```text
Including 00 was necessary; otherwise gamma optimization was distorted.
The full-anchor raw total is high, but the 3x CC/USDT margin cap crushes it.
The scaled leader wants much lower gamma11 than the old anchor, drops 01 at C=0,
and keeps real gamma00 exposure only while pressure is light.
q65 is still sensitivity, not a promoted live rule.
The next validation should rebuild path-manager/watch on new OOS days and check
whether fixed60 fallback for 00 remains acceptable.
```

## Capacity Manager

Latest report:

```text
docs/markets/ccusdt/v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_capacity_manager.py
```

This pass fixes the watcher-aware four-cell signal model and tests the actual
3x overlap constraint:

$$
L(t)=\sum_{i:t_i\le t<u_i}\widetilde w_i\le3.
$$

The important correction is that `scaled100` was a conservative lower bound,
not the only feasible 3x interpretation. Global scaling uses:

$$
\widetilde w_i
=
w_i\min\left(1,{3\over \max_t\sum_{j:t_j\le t<u_j}w_j}\right),
$$

which punishes every leg because of one crowded interval. Online clipping uses:

$$
\widetilde w_i
=
\min(w_i,3-L(t_i^-)),
$$

so it only cuts arrivals when the book is actually full.

For the cleaner q70 low-concurrency point:

```text
variant             grid_g00_1.25_g10_0.75_g01_0_g11_0.75
raw total           6042.8705
raw max concurrency 3.3750
global_downscale    5371.4405
online_fifo_clip    6038.2000
capacity loss       4.6705 from raw
clipped legs        4
skipped legs        0
worst day           +8.2022
leg worst           -76.0697
```

So under C=0, this point is not really a 5371 strategy; it is a roughly 6038
strategy if capacity is managed online.

For the high-gamma q70 point:

```text
variant             grid_g00_1.25_g10_2_g01_1_g11_5
raw total           21096.4649
raw max concurrency 22.5000
global_downscale     2812.8620
online_fifo_clip    12556.9297
clipped legs          240
skipped legs           26
worst day            +67.8536
leg worst           -146.1132
```

This is why "just open 3x" is not the same as "each signal gets 3x". The
strategy has a capacity allocator:

$$
(\text{entry signal},\ \text{exit path},\ \gamma)
\longrightarrow
\widetilde w_i
\quad\text{subject to}\quad
\max_t L(t)\le3.
$$

Pressure still matters. The low-concurrency q70 point remains positive in
total under pressure, but daily left tail reappears:

```text
C=0 online total 6038.2000, worst day   +8.2022
C=1 online total 4308.0750, worst day  -68.7978
C=2 online total 2577.9500, worst day -145.7978
```

Read:

```text
The 3x problem is capacity management, not signal disappearance.
Global scaled100 is a lower bound.
Online FIFO/arrival clip is the implementable first model.
Replacement proxy is diagnostic only because it uses terminal-PnL information.
High-gamma rows need pressure and single-leg-tail review before promotion.
```

## Leverage-Constrained Optimization

Latest report:

```text
docs/markets/ccusdt/v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_leverage_constrained_opt.py
```

This pass fixes the key modeling error: a global cell coefficient
`gamma01=0` converted a local high-concurrency capacity problem into a global
deletion of `01_frames_only`.

The corrected small model keeps the current q70 core:

```text
gamma00=1.25, gamma10=0.75, gamma11=0.75
```

and adds `01` only as an idle-capacity sleeve:

$$
w_i^{01}
=
\mathbf 1_{\{c_i=01\}}
\min\left(b_i\gamma_{01},\ [3-L(t_i^-)-m]_+\right).
$$

Main C=0 result:

```text
historical core-only total       6038.2000
historical idle01_g1_r0 total    6907.5648
delta                            +869.3648
worst day                        +48.3285
positive days                    14/14
leg worst                        -84.5942
2026-05-18 OOS core-only         415.8276
2026-05-18 OOS idle01_g1_r0      472.5926
OOS delta                        +56.7649
```

The important capacity diagnostic is displacement, not just PnL:

```text
historical idle01_g1_r0 actual 01 exposure 216.7500
core exposure reduction                    -4.1250
core displacement ratio                    1.90%
```

Read:

```text
01 was not a dead cell.
The previous strategy target over-compressed the leverage problem.
Most recovered 01 exposure is idle capacity, not stolen core capacity.
idle01_g1_r0 is an upper sleeve candidate, not a live-ready rule.
```

## 2026-05-18 OOS Check

Latest report:

```text
docs/markets/ccusdt/v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md
```

Script:

```text
scripts/ccusdt_v1_tfi_current_strategy_oos.py
```

This is a locked current-strategy check on newly downloaded 2026-05-18
Bullish `CCUSDT` data. It does not optimize gamma or thresholds on 2026-05-18.

The cleaner q70 low-concurrency policy remains:

```text
gamma00=1.25, gamma10=0.75, gamma01=0, gamma11=0.75
```

Under C=0 and online FIFO 3x capacity clipping:

```text
entries                         304
watcher triggers                  0
actual_total               415.8276 weighted log-bp units
exact_simple_bp_units      416.6424
approx_simple_return         4.2459%
desired max concurrency       3.7500
actual max concurrency        3.0000
clipped legs                  3
skipped legs                  1
leg worst                   -21.1977
```

The log/simple relation is:

$$
G=\sum_i \widetilde w_i r_i^{log},
\qquad
\widehat R_{simple}\approx \exp(G/10^4)-1.
$$

For 2026-05-18:

$$
\exp(415.8276/10^4)-1=0.042459.
$$

Pressure sensitivity on the same locked policy:

```text
C=0 online total 415.8276
C=1 online total 257.7026
C=2 online total  99.5776
```

Read:

```text
The day did not decay to zero.
The cleaner q70 point survived the new OOS day under C=0 and still stayed
positive under 2bps pressure.
The watcher did not trigger, so this day mostly validates the base
entry/path-manager/capacity policy, not post-exit re-entry.
This is still one OOS day and not a live-ready margin-account simulator.
```

## Modeling Order

Future work should follow this order:

1. Entry eligibility:

$$
e_i^{entry}=f(A_i,B_i,\Delta_i,E_i,Z_i).
$$

2. Release detection:

$$
\tau_i^r=\inf\{\tau\le a:R_i(\tau)\ge r_i\}.
$$

3. Decay hazard after release:

$$
\lambda_i(\tau)=
\Pr(D_i(\tau+d)-D_i(\tau)>m\mid \mathcal{F}_{t_i+\tau}).
$$

4. Exit / de-risk rule:

$$
\tau_i^{exit}
=
\min\{\tau_i^r+\delta,\ \inf_{\tau\ge\tau_i^r}D_i(\tau)\ge b_i,\ 60s\}.
$$

5. Post-exit re-trigger:

$$
e_i^{re}(\tau+g)
=
\mathbf{1}\{Q_i(g)\ge q,\ F_i(g)>0,\ C_i(g)\ge c\}.
$$

This is a separate entry event, not a reason to keep holding through the first
drawdown.

6. Sizing:

$$
w_i=b_i\gamma_{A_iB_i}s_i^{global},
$$

with the leverage cap applied after concurrency is computed:

$$
s_i^{global}\max_t \sum_{j:t_j\le t<u_j} b_j\gamma_{A_jB_j}\le 3.
$$

Do not let the sizing layer hide an exit-shape failure.

## Practical Read

Given the zero-fee baseline plus pressure reserve above, the correct workflow is:

$$
C_{fee}=0\ \mathrm{baseline}
\rightarrow
c\in\{0,1,2,\ldots\}\ \mathrm{bps\ evaluation}
\rightarrow
\mathrm{path/exit/sizing\ stability}.
$$

Here \(c=0\) is the baseline read, while \(c>0\) is the robustness read. Therefore
"C=0 Pareto looks good" is not the end of analysis, but it is the right
baseline. The first live research question remains:

```text
Can we catch fast release without giving back too much right tail?
```

The current best answer is not proven, but the only non-silly direction is a
small path-first exit family: fixed 30s as a left-tail baseline, plus
prior-threshold release/trailing or 5s..20s flow-confirmed hold as the candidate
that tries to retain the right tail.

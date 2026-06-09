# CCUSDT Microstructure Factor Atlas

Status: `20260601_microstructure_factor_atlas_v1`.

Guardrail:
`research_only_factor_map_no_strategy_promotion_no_runtime_label_dependency`.

This atlas is the next factor-analysis entry point after the TFI line became too
narrowly summarized as "R5". The purpose is not to propose another local
trigger. The purpose is to define the factor space from first principles, record
what has already been studied, identify the under-explored factor systems, and
set a strict diagnostic protocol before any factor can become a policy input.

Companion strategy-structure map:

```text
docs/markets/ccusdt/research/strategy/v1-microstructure-structure-family-map-20260601.md
```

Use this companion map when the question is not "which primitive is useful?"
but "which market structure is this primitive helping to form?".

First structure-family fast evidence pass:

```text
docs/markets/ccusdt/research/strategy/v1-structure-family-fast-research-20260601.md
```

Use this report when moving from primitive-level factor evidence to
structure-level roles such as `entry-alpha`, `release-only`, `cost-filter`, and
`decay-risk`.

## 0. Current Data Boundary

Current local market-derived coverage is asymmetric:

| layer | available local dates | formal use in this atlas |
| --- | --- | --- |
| `quote_frame_v1` CSV canonical | `2026-05-04` .. `2026-05-30` | spread, mid, quote staleness, top-of-book executable labels |
| `trade_event_v1` CSV canonical | `2026-05-04` .. `2026-05-18` | TFI and trade-flow factors only through `2026-05-18` |
| `l2_level_update_v1` CSV canonical | `2026-05-04` .. `2026-05-06`, `2026-05-16` .. `2026-05-18` | L2 diagnostics only where complete |
| `decision_frame_v1` Parquet cache | `2026-05-04` .. `2026-05-30` | fast decision-clock diagnostics, with source-layer caveats |

Therefore:

```text
2026-05-04..2026-05-18 = full trade-flow factor window.
2026-05-19..2026-05-30 = quote / decision-frame only unless trade/L2 are rebuilt.
```

Do not mix these windows in one headline result. A quote-only recent result is
not evidence about TFI, OFI, or MLOFI.

## 1. First-Principles Object

Let \(\mathcal F_t\) be the exchange-visible filtration at decision time \(t\).
Every runtime-safe factor must be a measurable statistic:

$$
X_t=f(\mathcal F_t).
$$

The research problem is:

$$
\text{which observable states }X_t
\text{ explain release, decay, tail, and execution cost?}
$$

The old fixed-horizon label is only one projection:

$$
R_i(60)=s_i10^4\log\frac{M_{t_i+60s}}{M_{t_i}},
$$

where \(s_i\in\{-1,+1\}\) is the entry direction. The economically relevant
path is:

$$
H_i(h)=\max_{0<u\le h}R_i(u),\qquad
D_i(h)=H_i(h)-R_i(h).
$$

So the factor target must be split:

```text
entry state -> release probability / release speed -> post-release decay
            -> executable crossing cost -> capacity and tail behavior
```

Any factor that only improves \(R_i(60)\) but fails after top-of-book crossing is
a spread-cost mirage, not a strategy input.

## 2. Evidence Classes

This atlas separates four evidence layers:

| evidence class | object | can promote to runtime? | examples |
| --- | --- | --- | --- |
| alpha evidence | future path conditional on current state | only after runtime-safe reconstruction | TFI, Delta/Energy/Z, OFI/MLOFI memory |
| path evidence | release and decay functionals | no; diagnostic labels only | MFE, MAE, time-to-MFE, decay_60 |
| execution evidence | fill and crossing cost under a profile | no as factor; yes as evaluation | entry spread, exit spread, taker IOC net |
| capacity evidence | portfolio effect under online ledger | no as alpha; yes as policy constraint | clipping, FIFO exposure, tail_share |

The promotion rule is:

$$
X_t\in\mathcal F_t,\quad
\text{stable across days},\quad
\text{survives executable labels},\quad
\text{reconstructable inside Bot}.
$$

Oracle fields such as future return, MFE, MAE, realized PnL, scored entries, and
decay labels are diagnostic only. They must not enter Runner or Strategy Bot
runtime.

## 3. Factor System A: Active Trade-Flow Memory

### 3.1 Primitive

The primitive is signed aggressive trading pressure. For a trade \(u\), define a
direction-aligned primitive \(g_u\). For the original TFI branch, \(g_u\) is a
trade-flow imbalance statistic aligned to candidate side \(d_t\).

The important generalization is that R5 is not the center. R5 is one memory
transform applied to one primitive.

For any signed primitive \(g_u\), define the memory operator over the previous
\(k\) closed observations:

$$
P_k(g)=\sum_{u\le k}(d_tg_u)^+,\qquad
N_k(g)=\sum_{u\le k}(-d_tg_u)^+.
$$

Then:

$$
R_k(g)=\frac{P_k(g)}{N_k(g)+\epsilon},
$$

$$
\Delta_k(g)=P_k(g)-N_k(g),\qquad
E_k(g)=P_k(g)+N_k(g),
$$

$$
Z_k(g)=\frac{\Delta_k(g)}{\sqrt{E_k(g)+\epsilon}}.
$$

### 3.2 Interpretation

These four transforms answer different questions:

| transform | question answered | failure mode |
| --- | --- | --- |
| \(R_k\) | is positive evidence larger than negative evidence? | ratio ignores absolute scale |
| \(\Delta_k\) | how much net cushion exists? | can hide noisy high-energy states |
| \(E_k\) | how much total recent activity exists? | high energy can be volatility, not edge |
| \(Z_k\) | is net pressure large relative to activity scale? | assumes square-root normalization is adequate |

The strongest existing warning is that `R5` alone is not a quality score. Prior
factor decomposition found `closed5_energy` stronger than `closed5_ratio`:

```text
closed5_energy top-bottom target-policy mean = 10.2597 bps
closed5_ratio  top-bottom target-policy mean =  4.1139 bps
```

This means the market is not just rewarding a clean ratio. It is also rewarding
absolute realized activity and cushion.

### 3.3 Existing Evidence

Strongly studied:

- `trade_flow_imbalance` as the main dynamic flow family.
- `R5/R10`, `Delta`, `Energy`, `Z`, and `closed*_loss_abs_max`.
- Four cells `00/10/01/11` using R5 and frames.
- Worst-day frontier using `closed5_delta`, `closed5_energy`, and absolute loss.

Important evidence anchors:

- `trade_flow_imbalance` on `fwd_event_25_bps`: forward IC around `0.3017`
  in the method sweep.
- `closed5_energy`: top-bottom `10.2597` bps in the factor decomposition.
- `closed10_score_abs_ge_q0.2`: 9/9 positive test days in the worst-day
  frontier, while preserving most of the TFI structure.

### 3.4 Under-Explored Extensions

Apply the same memory operator to non-TFI primitives:

| candidate primitive \(g\) | factor family | first diagnostic question |
| --- | --- | --- |
| OFI at L1/L5/L25 | `ofi_memory` | does passive book pressure add information beyond TFI? |
| MLOFI at multiple levels | `mlofi_memory` | does multi-level order flow confirm active trades? |
| depth depletion | `depletion_memory` | is the opposite book being consumed or simply thin? |
| replenishment | `replenishment_memory` | is pressure being absorbed after each push? |
| spread widening / compression | `spread_regime_memory` | is apparent momentum just crossing-cost expansion? |
| top-depth collapse | `depth_collapse_memory` | does vacuum predict release or only fragility? |

Priority: high. This is the cleanest way to avoid treating TFI as magical. It
tests whether the useful structure is the primitive itself or the memory
operator applied to exchange-visible microstructure.

## 4. Factor System B: Passive Book State

### 4.1 Primitive

Let best ask/bid be \(a_t,b_t\), mid \(m_t=(a_t+b_t)/2\), and cumulative bid/ask
depth up to level \(K\) be \(D^b_{K,t},D^a_{K,t}\).

Core passive-book factors:

$$
spread_t=10^4\frac{a_t-b_t}{m_t},
$$

$$
QI_{K,t}=\frac{D^b_{K,t}-D^a_{K,t}}{D^b_{K,t}+D^a_{K,t}+\epsilon},
$$

$$
microprice_t=\frac{a_tq^b_{1,t}+b_tq^a_{1,t}}
{q^b_{1,t}+q^a_{1,t}+\epsilon}.
$$

Liquidity cost for buying notional \(\omega\):

$$
LC^+_{\omega,t}=10^4\left(\frac{VWAP^+_{\omega,t}}{m_t}-1\right).
$$

### 4.2 Interpretation

Passive-book factors are often regime variables, not standalone alpha. They
measure the current obstacle and cost surface:

```text
spread      -> immediate crossing tax
depth       -> absorption capacity
QI          -> visible queue skew
microprice  -> top-level imbalance projection
LC          -> size-dependent crossing cost
```

### 4.3 Existing Evidence

The LOB stylized report found static book-shape variables weak as standalone
forward predictors:

```text
best snapshot row: obi_1 on fwd_time_60s_bps
Spearman = 0.0366
AUC      = 0.5094
top-bottom = 1.4401 bps
```

It also found the book to be sparse-moving:

```text
median daily quote-change rate = 0.0426
median daily median spread     = 2.0050 bps
median p95 spread              = 4.0059 bps
```

This explains why passive state can appear meaningful but still be insufficient
as a trigger. A stale quote can mean latent pressure, absorption, or simply a
quiet book.

### 4.4 Under-Explored Extensions

Passive-book factors should be used mainly as controls:

- spread regime before and after the candidate entry;
- opposite-depth percentile and local collapse;
- top-depth concentration versus 25-level reserve;
- depth cliff / convexity around best price;
- quote staleness conditional on active flow.

Priority: medium. These factors are not likely to replace TFI, but they are
essential to stop mid-label mirages and explain taker cost.

## 5. Factor System C: Dynamic Book Flow

### 5.1 Primitive

OFI/MLOFI and queue events describe how the passive book changes, not only what
aggressive trades consume. The fixed event-defined panel already distinguishes:

```text
limit add / replenish
queue depletion
cancellation / withdrawal
trade-matched execution
MLOFI across levels 1/2/3/5/10/25
```

The simplest directional consistency statistic is:

$$
C_t=\operatorname{sign}(TFI_t)\operatorname{sign}(OFI_t\ \text{or}\ MLOFI_t).
$$

More generally:

$$
F^{book}_t=d_t\cdot OFI_t,\qquad
F^{multi}_t=d_t\cdot MLOFI_{K,t}.
$$

### 5.2 Interpretation

Dynamic book flow asks whether active trades are supported by the passive book:

```text
TFI positive, MLOFI positive   -> active pressure and passive book agree
TFI positive, MLOFI negative   -> active trades hit replenishing resistance
TFI quiet, MLOFI strong        -> quote flow without visible taker pressure
```

This is likely more important than raw queue imbalance. Queue imbalance says
what the book looks like; OFI/MLOFI says how it is changing.

### 5.3 Existing Evidence

The fixed event-defined OFI/MLOFI pass is broad but not yet integrated into the
current strategy line. It found:

```text
event panel rows = 2,606,830
feature surface  = 105 fixed definitions
top path diagnostics mostly MLOFI L1
```

The LOB stylized report found MLOFI secondary but real:

```text
mlofi_roll10_l1 on fwd_time_10s_bps:
Spearman = 0.0894
top-bottom = 1.1523 bps
```

This is not enough for execution promotion, but it is enough to justify treating
MLOFI as a confirmation/control family.

### 5.4 Under-Explored Extensions

Highest-priority diagnostics:

1. Apply \(R,\Delta,E,Z\) memory to OFI and MLOFI.
2. Measure TFI-book consistency:
   $$
   \operatorname{sign}(TFI)\operatorname{sign}(MLOFI_K).
   $$
3. Split absorption into two states:
   ```text
   active flow + replenishing opposite book -> absorption holds -> reversal/decay
   active flow + depleting opposite book    -> absorption breaks -> release
   ```
4. Compare top-level MLOFI with deeper-level MLOFI to distinguish surface spoof
   from real depth migration.

Priority: high. This is the most natural "different system but similar
structure" beyond TFI.

## 6. Factor System D: Pressure-To-Price Conversion

### 6.1 Primitive

The core quantity model already frames the price move as:

$$
r_{t,t+h}=d_t\lambda_t(X_t-\Theta_t)^+ + \epsilon_t.
$$

Here:

- \(X_t\) is accumulated same-direction pressure.
- \(\Theta_t\) is the book absorption threshold.
- \(\lambda_t\) is pressure-to-price conversion efficiency.

A direct empirical proxy is:

$$
\widehat\lambda_t(h)=
\frac{d_t\Delta m_{t,t+h}}{|F_t|+\epsilon}.
$$

Absorption proxy:

$$
A^{proxy}_t=
\frac{|F_t|}{|d_t\Delta m_{t-k,t}|+\epsilon}.
$$

Vacuum proxy:

$$
V_t=
\frac{|F_t|}{OppDepth_{K,t}+\epsilon}.
$$

Staleness proxy:

$$
Q^{frames}_t=F_{train}(frames\_since\_mid\_change_t).
$$

### 6.2 Interpretation

The same TFI surface can mean opposite mechanisms:

```text
Release:    pressure converts to quote repricing.
Absorption: pressure is present but absorbed by replenishment.
Vacuum:     thin opposite depth allows fast movement but not persistence.
Chop:       movement exists but alternates too quickly for clean execution.
```

Therefore \(R5+Q\) is not a single edge. It is an observation surface over a
latent state mixture:

$$
r_i\mid x_i,\mathcal H_{t_i}
\sim
\sum_{z\in\mathcal Z}\pi_z(t_i)F_z(r\mid x_i).
$$

### 6.3 Existing Evidence

The core quantity report found:

```text
lambda_prior_top_u top-bottom net = 2.6073 bps
log_U_t top-bottom net            = 2.5180 bps
Theta_t top-bottom net            = -5.7489 bps
cell_11_low_U mean net            = 9.0915 bps
```

The release/decay report found low opposite depth is double-edged:

```text
log_opp_depth25_quote vs MFE_10 Spearman = -0.2998
log_opp_depth25_quote vs D_60 after early release Spearman = -0.1986
```

This is a critical point: vacuum predicts fast release, but it can also predict
decay. Thin depth is not the same as continuation.

### 6.4 Under-Explored Extensions

Priority diagnostics:

- pressure accumulation while mid is stale:
  $$
  S_t=\sum_{u:t-\tau<u\le t,\Delta mid=0} d_t g_u;
  $$
- conversion efficiency after stale pressure:
  $$
  \lambda^{stale}_t
  =\frac{d_t\Delta mid_{next}}{S_t+\epsilon};
  $$
- absorption break versus absorption hold:
  \[
  (F_t \uparrow,\ OppReplenish_t \uparrow,\ \Delta mid=0)
  \]
  should be treated separately from
  \[
  (F_t \uparrow,\ OppDepletion_t \uparrow,\ \Delta mid>0).
  \]
- residual pressure after a move:
  $$
  RP_t(h)=\sum_{u=t}^{t+h}d_tg_u-d_t\Delta mid_{t,t+h},
  $$
  which asks whether pressure remains after the visible price response;
- exhaustion after a release:
  $$
  EX_t(h)=\mathbf 1\{R_t(h)>0,\ RP_t(h)\le 0,\ OppReplenish_t>0\},
  $$
  which should be treated as a continuation guard, not as a standalone alpha.
- `past_event_25_bps` and similar recent-price fields should remain controls:
  they describe already-realized movement and are useful for artifact checks,
  but they are not sufficient evidence of future conversion.

Priority: high, but only after OFI/MLOFI memory is defined clearly.

## 7. Factor System E: Path And Stopping-Time Factors

### 7.1 Primitive

The path object is:

$$
R_i(\tau)=s_i10^4\log\frac{M_{t_i+\tau}}{M_{t_i}}.
$$

Release and decay:

$$
MFE_i(h)=\max_{0<\tau\le h}R_i(\tau),
$$

$$
MAE_i(h)=\min_{0<\tau\le h}R_i(\tau),
$$

$$
D_i(h)=MFE_i(h)-R_i(h).
$$

Time-to-release:

$$
\tau_i(r)=\inf\{\tau>0:R_i(\tau)\ge r\}.
$$

Conditional wait value after a release threshold \(r\):

$$
W_i(u\mid \tau_i(r))=
R_i(\tau_i(r)+u)-R_i(\tau_i(r)).
$$

### 7.2 Interpretation

This family answers a different question from entry:

```text
Was the entry pressure real?
How fast did it release?
After release, did continuation survive?
Was fixed60 holding the source of loss?
```

The key failure example remains `1615412`:

```text
MFE_10      = +12.5612 bps
time_to_MFE = 4.7051 s
R_60        = -27.8923 bps
decay_60    = 40.4535 bps
```

This is not a bad-entry proof. It is a release-then-decay proof.

### 7.3 Existing Evidence

Release/decay diagnostics found:

```text
mean MFE_10                         = 3.6668 bps
mean R_60                           = 4.2577 bps
mean decay_60                       = 5.6716 bps
P(MFE_10 >= 5bps)                   = 26.94%
P(MFE_10 >= 5bps and R_60 < 0)      = 6.32%
```

After early release, sustained signed flow is a stronger decay warning than
static queue imbalance:

```text
signed_tfi_mean_5_20s vs D_60 Spearman = -0.3370
signed_mlofi5_mean_5_20s vs D_60       = -0.2883
signed_ofi_mean_5_20s vs D_60          = -0.2647
```

### 7.4 Under-Explored Extensions

Do not optimize a fixed exit horizon first. Study the stopping problem:

$$
\tau^*=\inf\{t\ge t_i:
\text{continuation probability falls below execution reserve}\}.
$$

Required diagnostics:

- hazard of decay after release;
- conditional wait value by release size and flow confirmation;
- whether OFI/MLOFI memory after release improves hold/exit;
- executable path labels, not only mid labels.

Priority: high for strategy economics, but it should be downstream of factor
measurement. Do not promote a stopping rule built from future MFE/MAE.

## 8. Factor System F: Distribution, Tail, And Execution

### 8.1 Primitive

Entry quality is distributional:

$$
F_{R|X,C}(r)=\mathbb P(R\le r\mid X,C).
$$

The mean is not enough. Useful summaries:

$$
\mu_X=\mathbb E[R\mid X],
$$

$$
CVaR_{5\%,X}=\mathbb E[R\mid R\le q_{5\%}(R),X],
$$

$$
tail\_share_X=
\frac{\sum_{i\in X, R_i\ge q_{90}}R_i}
{\sum_{i\in X}R_i}.
$$

Entry-level shrinkage:

$$
\widehat\mu_A=\lambda_A\bar r_A+(1-\lambda_A)\widehat\mu_{\pi(A)},
\qquad
\lambda_A=\frac{n_A}{n_A+k}.
$$

Execution decomposition for top-of-book taker:

$$
R^{exe}_{long}=10^4\log\frac{b_{exit}}{a_{entry}},
$$

$$
R^{exe}_{short}=10^4\log\frac{b_{entry}}{a_{exit}}.
$$

### 8.2 Interpretation

Zero fee does not mean zero execution cost. The spread is a real crossing tax:

```text
entry at ask, exit at bid for long;
entry at bid, exit at ask for short.
```

Also, `net_median < 0` is not a sufficient reason to discard a structure. A
right-tail strategy can have negative median if the positive tail and capacity
discipline pay for frequent small losses.

### 8.3 Existing Evidence

Entry estimation found that quality classes matter but are not regime-safe:

```text
strong_positive weighted mean       = 7.5693 bps
positive_right_tail_fragile mean    = 3.5521 bps
avoid_or_reduce weighted mean       = 1.3725 bps
```

The current taker strict line has shown that mid edge can be cut heavily by
entry and exit crossing. Therefore every future factor diagnostic must include
both mid labels and executable labels.

### 8.4 Under-Explored Extensions

Promotion should require:

1. distributional stability, not only mean IC;
2. top-of-book executable survival;
3. capacity overlap and clipping accounting;
4. strict replay consistency if used for strategy.

Priority: always on. It is the gate around all other factor systems.

## 9. Candidate Priority Matrix

| priority | candidate | why it matters | current status | first output |
| --- | --- | --- | --- | --- |
| P0 | data boundary manifest | prevents quote-only results from masquerading as TFI evidence | partially known | daily coverage table |
| P1 | OFI/MLOFI memory operators | structurally different from TFI but same memory math | under-integrated | IC/top-bottom by \(R,\Delta,E,Z\) |
| P1 | TFI-book consistency | tests active/passive agreement | under-studied | consistency bucket report |
| P1 | stale pressure conversion | explains frames/Q as latent pressure, not alpha alone | partially studied | stale pressure to next mid move |
| P2 | absorption hold vs break | separates reversal/decay from continuation | hypothesis stage | two-state diagnostic |
| P2 | release decay hazard | replaces fixed60 thinking with stopping-time analysis | partially studied | hazard table after release |
| P2 | spread/depth executable reserve | protects against spread-cost mirages | known problem | mid-vs-exe report |
| P3 | quote-only recent regime check | useful for current market state, not TFI evidence | incomplete | separate quote-only note |

## 10. Fast Diagnostic Contract

The next diagnostic table should use this schema:

```text
factor_family
factor_name
primitive
transform
label
horizon
date_window
n
mean
median
top_bottom
cvar05
daily_sign_rate
mid_minus_executable_bps
runtime_safe
status
source_manifest
```

Labels must be separated:

| label | meaning | promotion role |
| --- | --- | --- |
| `mid_path` | signed mid return or path functional | diagnostic only |
| `top_of_book_executable` | taker executable entry/exit from bid/ask | required screen |
| `strict_taker_realized` | Runner-owned fill/portfolio outcome | final realism gate |

Do not compare a `mid_path` result to a `strict_taker_realized` result without
explicit decomposition.

## 11. Promotion Gate

A factor can move from atlas to strategy candidate only if:

1. It is runtime-safe:
   $$
   X_t=f(\mathcal F_t).
   $$
2. It survives mid and executable labels:
   ```text
   positive mid edge is not enough.
   ```
3. It is not dominated by past-return or reversed-time controls.
4. It is stable across dates and does not depend on one tail day.
5. It can be reconstructed by the Bot from public/private streams or validated
   `decision_frame_v1`.
6. It is profile-explicit: fill profile, latency profile, capacity profile, and
   exit profile are not mixed.

Failure to pass the gate does not mean the factor is useless. It may remain a
regime variable, control, monitor display, or explanatory diagnostic.

## 12. Existing Evidence Map

Read these reports as the current evidence layer:

1. `docs/markets/ccusdt/current/v1-tfi-current-research-map-20260519.md`
2. `docs/markets/ccusdt/current/v1-current-tfi-strategy-handoff-20260518.md`
3. `docs/markets/ccusdt/research/factors/v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md`
4. `docs/markets/ccusdt/research/factors/v1-tfi-entry-estimation-20260518_ccusdt_v1_tfi_entry_estimation_v1.md`
5. `docs/markets/ccusdt/research/factors/v1-tfi-core-quantity-estimation-20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.md`
6. `docs/markets/ccusdt/research/factors/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md`
7. `docs/markets/ccusdt/research/factors/v1-lob-stylized-factors-20260518_ccusdt_v1_lob_stylized_factors_v1.md`
8. `docs/markets/ccusdt/research/factors/v1-fixed-event-orderbook-factors-v3.md`
9. `docs/markets/ccusdt/research/factors/v1-factor-method-sweep.md`
10. `docs/markets/ccusdt/research/factors/v1-tfi-worst-day-frontier-20260518_ccusdt_v1_tfi_worst_day_frontier_v1.md`
11. `docs/markets/ccusdt/research/factors/v1-tfi-latent-state-taxonomy-20260518_ccusdt_v1_tfi_latent_state_taxonomy_v1.md`
12. `docs/markets/ccusdt/research/strategy/v1-event-regime-discovery-20260601.md`

The `event_regime_discovery` report is now a reference scan, not the main next
path. It showed useful spread-cost rejections but did not discover a clean new
strategy family.

## 13. Immediate Next Work

The next implementation should not modify Runner, Bot, or Monitor. It should
use:

```powershell
python systems/ccusdt_replay_exchange/diagnostics/microstructure_factor_diagnostic.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18 --source both
```

This script:

1. reads validated `decision_frame_v1` and available trade/L2 sources;
2. computes the memory operator \(R,\Delta,E,Z\) for TFI, OFI/MLOFI,
   depletion, replenishment, depth collapse, and spread regime where the source
   exists;
3. emits the fast diagnostic contract table above;
4. writes a report that explicitly separates:
   ```text
   full trade-flow window: 2026-05-04..2026-05-18
   quote-only recent window: 2026-05-19..2026-05-30
   ```
5. refuses to produce a unified headline across incompatible data layers.

This keeps the research honest: first define the observable state space, then
measure it, then decide what deserves strategy work.

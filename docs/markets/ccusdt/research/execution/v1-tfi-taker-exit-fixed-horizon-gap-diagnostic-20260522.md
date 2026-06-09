# CCUSDT V1 TFI Taker Exit Fixed-Horizon and Gap Diagnostic

Date: 2026-05-22

Scope:

- Symbol/profile: `CCUSDT`, q70 admission, `core_idle01`, `idle01_g1`.
- Execution model: `top_of_book_taker_ioc_v1`, `fee_bps=0`, deterministic arrival, zero latency.
- Dates: `2026-05-16..2026-05-18`.
- Runtime boundary: strategy/runtime inputs remain market-derived only. The oracle/gap tables below are offline diagnostics and must not be read by the Bot.

## Artifacts

- Fixed60 fast baseline: `systems/ccusdt_replay_exchange/runs/experiments/fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_v2_20260516_18_20260521`
- Fixed30 live-coherent fast: `systems/ccusdt_replay_exchange/runs/experiments/fast_adm_q70_idle01_g1_fixed30_taker_livecoherent_quoteidx_20260516_18_20260522`
- Fixed45 live-coherent fast: `systems/ccusdt_replay_exchange/runs/experiments/fast_adm_q70_idle01_g1_fixed45_taker_livecoherent_quoteidx_20260516_18_20260522`
- Runtime-safe stopping diagnostic: `systems/ccusdt_replay_exchange/runs/taker_exit_runtime_safe_stopping_diag_q70_idle01_g1_20260516_18_20260522`
- Gap decomposition run: `systems/ccusdt_replay_exchange/runs/taker_exit_gap_decomp_q70_idle01_g1_20260516_18_20260522`
- Gap decomposition script: `systems/ccusdt_replay_exchange/diagnostics/taker_exit_gap_decomposition.py`

## Math

For entry \(i\), candidate exit horizon \(u\), and fixed 60s baseline:

\[
Y_i(u)=\alpha_i(u)-c_i^{entry}-c_i^{exit}(u).
\]

The value of exiting at \(u\) instead of 60s is:

\[
G_i(u)=Y_i(u)-Y_i(60)
      =\left[\alpha_i(u)-\alpha_i(60)\right]
       -\left[c_i^{exit}(u)-c_i^{exit}(60)\right].
\]

In the diagnostic output:

\[
G_i(u)
=\texttt{avoided\_alpha\_decay\_bps}
 -\texttt{additional\_exit\_cross\_bps}.
\]

The max absolute reconstruction error in the generated table is:

```text
4.361844219147315e-12 bps
```

So the decomposition closes numerically.

## Fixed-Horizon Validation

Important: `fixed30` and `fixed45` are live-coherent policy profiles, not a pure exit-only overlay. Changing `fixed_exit_us` closes shadow entries earlier, which changes the Bot-owned prequential R5 lifecycle and therefore later cells/weights.

Earlier direct comparison showed that changing the horizon while reusing the old fixed60 state creates material policy drift:

| comparison | timestamp set | cell mismatches | requested exposure mismatches | actual exposure mismatches |
| --- | ---: | ---: | ---: | ---: |
| fixed30 vs fixed60 | same | 220 | 220 | 147 |
| fixed45 vs fixed60 | same | 132 | 132 | 90 |

Therefore the fixed30/fixed45 results below should be read as new coherent strategy families.

Fast executable results:

| exit profile | total bp-units | 2026-05-16 | 2026-05-17 | 2026-05-18 | worst day |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fixed60_taker` | 545.2394 | 52.1134 | 249.7340 | 243.3920 | 52.1134 |
| `stopping_rule_v1` | 577.5528 | 52.1134 | 282.7840 | 242.6555 | 52.1134 |
| `fixed30_taker_livecoherent` | 644.0728 | 128.0535 | 350.8913 | 165.1280 | 128.0535 |
| `fixed45_taker_livecoherent` | 646.4341 | 117.6324 | 307.2480 | 221.5537 | 117.6324 |

Strict/panel-sparse fast-clock validation:

| exit profile | strict bp-units | orders | fills | arrival quote lag | note |
| --- | ---: | ---: | ---: | ---: | --- |
| `fixed60_taker` | 532.4362 | 1008 | 1008 | 0 | prior strict baseline |
| `stopping_rule_v1` | 564.7496 | 1008 | 1008 | 0 | strict consistency passed |
| `fixed30_taker_livecoherent` | 644.0728 | 1008 | 1008 | 0 | strict consistency passed |
| `fixed45_taker_livecoherent` | 646.4341 | 1008 | 1008 | 0 | strict consistency passed |

Execution-cost decomposition, capacity-weighted:

| exit profile | entry cross cost | exit cross cost | total cross cost |
| --- | ---: | ---: | ---: |
| `fixed60_taker` | 85.9473 | 324.0222 | 409.9695 |
| `stopping_rule_v1` | 85.9473 | 338.9430 | 424.8903 |
| `fixed30_taker_livecoherent` | 86.3040 | 299.0671 | 385.3710 |
| `fixed45_taker_livecoherent` | 81.6553 | 301.5419 | 383.1972 |

Interpretation:

- `fixed30` and `fixed45` are not winning by avoiding taker cost only. They also change the live R5 lifecycle.
- Both materially beat fixed60 and `stopping_rule_v1` in strict mode.
- `fixed45` has the best three-day total; `fixed30` has the best worst-day.
- `2026-05-18` is the counterexample: fixed60 remains better than fixed30/fixed45 on that day. A blind shorter horizon is therefore not obviously live-ready.

## Gap Surface

The offline exact-horizon gap surface, using the same 504 admitted positions and actual exposure \(298.625\), is:

| horizon \(u\) | weighted \(G(u)\) | mean \(G(u)\) | avoided alpha decay | additional exit cross |
| ---: | ---: | ---: | ---: | ---: |
| 1s | -594.0695 | -1.9893 | -632.6720 | -38.6025 |
| 2s | -503.1708 | -1.6850 | -539.6090 | -36.4382 |
| 3s | -494.1647 | -1.6548 | -523.1407 | -28.9760 |
| 5s | -431.8089 | -1.4460 | -460.2109 | -28.4021 |
| 10s | -198.9994 | -0.6664 | -223.4835 | -24.4842 |
| 15s | -171.6727 | -0.5749 | -193.7996 | -22.1270 |
| 20s | -95.6717 | -0.3204 | -108.9441 | -13.2724 |
| 30s | +44.6023 | +0.1494 | +29.8703 | -14.7319 |
| 45s | +109.3118 | +0.3661 | +98.2709 | -11.0409 |

This is the first-principles picture:

- Very early exits, 1s to 20s, lose because the trade has not had enough time to release. Even though early exit crossing is often cheaper, lost alpha dominates.
- 30s and 45s become positive because enough post-entry alpha has released while avoiding part of the later decay.
- 45s is the best unconditional exact horizon in this three-day diagnostic.

Day stability is not perfect:

| horizon | 2026-05-16 | 2026-05-17 | 2026-05-18 |
| ---: | ---: | ---: | ---: |
| 20s | -1.8083 | -6.6640 | -87.1994 |
| 30s | +60.7865 | +66.1876 | -82.3718 |
| 45s | +73.9181 | +56.8331 | -21.4394 |

So the message is not "always shorten." It is "60s is often too long, but 5/18 contains states where shortening is harmful."

## Cell Structure

Exact-horizon \(G(u)\) by cell:

| horizon | cell | weighted \(G(u)\) | mean \(G(u)\) | exposure |
| ---: | --- | ---: | ---: | ---: |
| 30s | `00_none` | +114.5071 | +0.8825 | 129.7500 |
| 30s | `01_frames_only` | -5.6743 | -0.1860 | 30.5000 |
| 30s | `10_r5_only` | -28.6344 | -0.2828 | 101.2500 |
| 30s | `11_r5_frames` | -35.5962 | -0.9588 | 37.1250 |
| 45s | `00_none` | +117.7702 | +0.9077 | 129.7500 |
| 45s | `01_frames_only` | +33.9039 | +1.1116 | 30.5000 |
| 45s | `10_r5_only` | -23.8068 | -0.2351 | 101.2500 |
| 45s | `11_r5_frames` | -18.5556 | -0.4998 | 37.1250 |

This is a warning against a one-line exit rule:

- `00_none` likes shorter exits.
- `01_frames_only` likes 45s much more than 30s.
- R5 cells, especially `11_r5_frames`, are hurt by unconditional early exit in the exact-horizon diagnostic.

The live-coherent fixed30/fixed45 totals still improve because the policy state and capacity path also change. That makes the result interesting, but also means the selector must be stateful and replayed, not stitched from independent day tables.

## Runtime-Safe Identifiability

Cost-aware candidate condition:

\[
\mathbb E[\alpha_i(u)-\alpha_i(60)\mid X_u]
>
\mathbb E[c_i^{exit}(u)-c_i^{exit}(60)\mid X_u]+m.
\]

The diagnostic used \(m=0.25\) bps, `min_count=30`, `min_exposure=10`, and at least two positive days when all three days are present.

Top offline diagnostic bins:

| scope | factor | bin | n | exposure | weighted \(G\) | mean \(G\) | avoided alpha | additional cross |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30s | `running_high_taker_net_bps` | q5 | 101 | 61.0000 | +160.4043 | +2.6296 | +2.6050 | -0.0245 |
| 45s | `recent5s_trade_qty_imbalance` | zero | 391 | 239.2500 | +138.2991 | +0.5781 | +0.5356 | -0.0425 |
| 45s | `recent_mid_alpha_5s_bps` | zero | 351 | 214.7500 | +120.6272 | +0.5617 | +0.5065 | -0.0552 |
| 45s | `cell` | `00_none` | 199 | 129.7500 | +117.7702 | +0.9077 | +0.8970 | -0.0107 |
| 30s | `cell` | `00_none` | 199 | 129.7500 | +114.5071 | +0.8825 | +0.8735 | -0.0090 |
| 45s | `running_high_taker_net_bps` | q5 | 101 | 60.1250 | +100.7192 | +1.6752 | +1.5192 | -0.1560 |
| 10s | `recent_mid_alpha_5s_bps` | negative | 52 | 27.6250 | +98.1539 | +3.5531 | +3.3925 | -0.1605 |

Interpretation:

- High realized path profit \(H_u\) is the cleanest release/decay clue. If a position has already released strongly by 30s, fixed60 often gives back edge.
- Flow inactivity around 45s is a plausible exhaustion signal. It is weaker than high \(H_u\), but has much larger exposure.
- Low/medium exit spread bins also look good, which is execution-realistic: early taker exit only makes sense if crossing is not hostile.
- The 10s negative recent-alpha bin has high mean but small exposure; treat it as a diagnostic clue, not a deployable rule.

## Prior-Date Selector Status

A naive one-day selector from the pure fixed-horizon daily table would choose:

- for 2026-05-17: choose 30s because 2026-05-16 fixed30 was best;
- for 2026-05-18: choose 30s because 2026-05-17 fixed30 was best.

But this is not yet a valid executable policy, because a mixed-horizon selector must own a single continuous R5 lifecycle:

\[
S_{d}^{selector}
=F(S_{d-1}^{selector}, h_d).
\]

It cannot reuse `fixed30_state_after_dt` for a day that was actually reached through `fixed60`, and it cannot splice daily PnL from independent full-horizon runs. The next engineering step is therefore a small mixed-horizon policy profile, not another oracle table.

That executable prior-date selector was then run as a continuous state path:

```text
2026-05-16: 60s fallback from state_after_dt=2026-05-15
2026-05-17: 30s, selected from 2026-05-16 fixed-horizon winner
2026-05-18: 30s, selected from 2026-05-17 fixed-horizon winner
```

Selector state artifacts:

- `systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/prior_horizon_selector_v1_state_after_dt=2026-05-16.json`
- `systems/ccusdt_replay_exchange/runs/state/ccusdt_tfi_core_idle01/prior_horizon_selector_v1_state_after_dt=2026-05-17.json`

Fast runs:

- `systems/ccusdt_replay_exchange/runs/experiments/fast_adm_q70_idle01_g1_prior_horizon_selector_v1_20260516_20260522`
- `systems/ccusdt_replay_exchange/runs/experiments/fast_adm_q70_idle01_g1_prior_horizon_selector_v1_20260517_20260522`
- `systems/ccusdt_replay_exchange/runs/experiments/fast_adm_q70_idle01_g1_prior_horizon_selector_v1_20260518_20260522`

Strict runs:

- `systems/ccusdt_replay_exchange/runs/det_fast_clock_adm_q70_idle01_g1_prior_horizon_selector_v1_20260516_20260522`
- `systems/ccusdt_replay_exchange/runs/det_fast_clock_adm_q70_idle01_g1_prior_horizon_selector_v1_20260517_20260522`
- `systems/ccusdt_replay_exchange/runs/det_fast_clock_adm_q70_idle01_g1_prior_horizon_selector_v1_20260518_20260522`

Fast-vs-strict consistency:

- `systems/ccusdt_replay_exchange/runs/fast_vs_strict_prior_horizon_selector_v1_20260516_20260522`
- `systems/ccusdt_replay_exchange/runs/fast_vs_strict_prior_horizon_selector_v1_20260517_20260522`
- `systems/ccusdt_replay_exchange/runs/fast_vs_strict_prior_horizon_selector_v1_20260518_20260522`

Selector results:

| date | selected horizon | entries | orders/fills | fast bp-units | strict bp-units | arrival quote lag | row mismatch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-05-16 | 60s | 261 | 298 | 52.1134 | 47.6171 | 0 | 0 |
| 2026-05-17 | 30s | 199 | 286 | 350.8913 | 350.8913 | 0 | 0 |
| 2026-05-18 | 30s | 304 | 424 | 165.1280 | 165.1280 | 0 | 0 |
| total | mixed | 764 | 1008 | 568.1327 | 563.6364 | 0 | 0 |

Selector execution costs, capacity-weighted:

| item | bp-units |
| --- | ---: |
| entry cross cost | 86.1300 |
| exit cross cost | 315.7017 |
| total cross cost | 401.8317 |

So the prior-date selector is executable and strict-verified, but it is not good enough:

| profile | strict bp-units |
| --- | ---: |
| `fixed60_taker` | 532.4362 |
| `stopping_rule_v1` | 564.7496 |
| `prior_horizon_selector_v1` | 563.6364 |
| `fixed30_taker_livecoherent` | 644.0728 |
| `fixed45_taker_livecoherent` | 646.4341 |

It narrowly improves fixed60, but it essentially ties/slightly loses to `stopping_rule_v1` and misses the main fixed30/fixed45 opportunity. The failure mode is simple: the selector learns from 5/17 that 30s was best, then applies 30s to 5/18, where fixed60 was better. This confirms that a daily winner-take-all selector is too slow and too coarse.

## Verdict

The current evidence says:

1. `fixed60_taker` is likely structurally too long for a meaningful subset of q70 idle01_g1 entries.
2. The improvement is not just fee/crossing; fixed30/fixed45 alter the prequential R5 lifecycle and capacity path.
3. 30s/45s are plausible candidates; 45s has the best three-day total, while 30s has the best worst-day.
4. 5/18 is a real counterexample against blindly shortening every exit.
5. A naive prior-date horizon selector is strict-runnable but too coarse; it gets `563.6364` strict bp-units and fails to switch away from 30s on 5/18.
6. The next candidate should be an intra-day/state-level horizon selector over `{30s,45s,60s}`, with cost-aware gates based on \(H_u\), flow exhaustion, cell, and current exit spread.

Do not promote `stopping_rule_v1` as the final answer. It is strict-runnable and positive, but fixed30/fixed45 show that the larger problem is horizon/state design rather than a complex path stop.

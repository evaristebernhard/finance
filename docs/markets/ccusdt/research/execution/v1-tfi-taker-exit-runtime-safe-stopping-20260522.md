# CCUSDT V1 TFI Taker Exit Runtime-Safe Stopping Diagnostic

Date: 2026-05-22

Scope:

- Symbol/profile: `CCUSDT`, q70 admission, `core_idle01`, `idle01_g1`, `top_of_book_taker_ioc_v1`.
- Dates: `2026-05-16..2026-05-18`.
- Universe: `764` shadow entries, `504` admitted/traded entries, `298.625` actual exposure.
- Runtime restriction: oracle path data is label-only. Bot/runtime inputs are market-derived decision frames plus quote/trade-visible state. No `date/`, scored entries, future PnL, MFE, or MAE are runtime inputs.

## Math

For entry `i` with side `s_i in {+1,-1}`, entry ask/bid execution, and candidate exit time `u`,

```text
Y_i(u) = taker_net_bps(u)
H_i(u) = max_{v <= u} Y_i(v)
D_i(u) = H_i(u) - Y_i(u)
c_out_i(u) = exit_cross_bps(u)
```

The runtime-safe threshold family is:

```text
stop_i(u) =
  1{
    H_i(u) >= h,
    D_i(u) >= max(d0, rho H_i(u)),
    c_out_i(u) <= q_exit
  }
```

with optional emergency decay:

```text
H_i(u) >= h,
D_i(u) >= emergency_d,
recent_mid_alpha_5s_i(u) <= -emergency_decay,
c_out_i(u) <= q_exit + q_emergency_add.
```

The stopping time is the first eligible decision-clock observation after the grid horizons
`{1,2,3,5,10,15,20,30,45}s`; missing prior-date params fall back to fixed 60s.
The diagnostic panel also stores `60s` as a fixed baseline/label point.

## Artifacts

- Diagnostic run: `systems/ccusdt_replay_exchange/runs/taker_exit_runtime_safe_stopping_diag_q70_idle01_g1_20260516_18_20260522`
- Runtime panel: `stopping_panel.parquet`, `5040` rows, runtime-safe columns only.
- Offline labels: `stopping_labels.parquet`, future/oracle/fixed60 labels only.
- Walk-forward params: `stopping_rule_params_by_date.json`.
- Fast executable run: `systems/ccusdt_replay_exchange/runs/experiments/fast_adm_q70_idle01_g1_stopping_rule_v1_quoteidx_20260516_18_20260522`.
- Strict runs:
  - `det_fast_clock_adm_q70_idle01_g1_stopping_rule_v1_20260516_r2_20260522`
  - `det_fast_clock_adm_q70_idle01_g1_stopping_rule_v1_20260517_r2_20260522`
  - `det_fast_clock_adm_q70_idle01_g1_stopping_rule_v1_20260518_r2_20260522`
- Fast-vs-strict consistency:
  - `fast_vs_strict_stopping_rule_v1_20260516_exec_r2_20260522`
  - `fast_vs_strict_stopping_rule_v1_20260517_exec_20260522`
  - `fast_vs_strict_stopping_rule_v1_20260518_exec_r2_20260522`

## Oracle and Walk-Forward Diagnostic

Oracle is an upper bound, not a policy:

| item | weighted bps |
| --- | ---: |
| fixed60 taker baseline | 532.4362 |
| oracle best taker exit | 1785.2785 |
| oracle gain vs fixed60 | 1252.8424 |
| best fixed horizon, 45s | 641.7479 |

Walk-forward threshold search used prior dates only:

| test day | selected rule | test net | fixed60 net | delta | triggered exits |
| --- | --- | ---: | ---: | ---: | ---: |
| 2026-05-17 | `h=3,d0=2,rho=.35,q_exit=2` | 287.0076 | 239.9107 | +47.0968 | 23 |
| 2026-05-18 | `h=10,d0=4,rho=.35,q_exit=2,emergency_decay=4` | 249.8314 | 244.9083 | +4.9231 | 7 |

OOS-fold total:

```text
delta_vs_fixed60 = +52.0199
oracle_capture_ratio = 0.0705
saved_left_tail = +97.1361
overcut_right_tail = -45.1162
```

Interpretation: the oracle says there is large path value, but this very small previsible rule captures only about `7%` of the oracle gap. It is useful as a diagnostic and modest left-tail repair, not a solved exit model.

## Executable Fast and Strict Results

Fast executable, all three days:

| exit profile | fast weighted bps | worst day | notes |
| --- | ---: | ---: | --- |
| `fixed60_taker` | 545.2394 | 47.6171 | old q70 idle01_g1 baseline |
| `peakguard_taker_v1` | 557.8988 | 58.1434 | only `11_r5_frames`, 5 release exits |
| `stopping_rule_v1` | 577.5528 | 52.1134 | prior-date params, 5/16 fixed60 fallback |

Strict executable, all three days:

| exit profile | strict weighted bps | delta vs fixed60 | entry cost | exit cost | worst day |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fixed60_taker` | 532.4362 | 0.0000 | 85.9473 | 324.0222 | 47.6171 |
| `peakguard_taker_v1` | 545.0955 | +12.6593 | 85.9473 | 287.1888 | 58.1434 |
| `stopping_rule_v1` | 564.7496 | +32.3134 | 85.9473 | 338.9430 | 47.6171 |

Strict stopping-rule daily totals:

| date | strict bps | matched round trips | arrival quote lag |
| --- | ---: | ---: | ---: |
| 2026-05-16 | 47.6171 | 149 | 0 |
| 2026-05-17 | 272.9607 | 143 | 0 |
| 2026-05-18 | 244.1718 | 212 | 0 |

Consistency checks:

```text
rows_compared: 261 / 199 / 304
row_mismatch_count: 0 / 0 / 0
profile_check: ok / ok / ok
data_profile_check: ok / ok / ok
missing_entry_fills: 0 / 0 / 0
missing_exit_fills: 0 / 0 / 0
```

Important nuance:

- The panel diagnostic evaluates exact horizon states.
- The executable Bot/Runner evaluates the first decision-clock observation after a horizon. This is still runtime-safe, but it is not exactly the same clock as the oracle-grid panel.
- That is why the diagnostic OOS fold shows `+52.0199`, while the executable fast all-day improvement vs fixed60 is about `+32.3134` strict-equivalent.

## Verdict

`stopping_rule_v1` is now runtime-safe and strict-runnable. It improves the q70 idle01_g1 taker exit baseline in strict mode:

```text
fixed60_taker -> stopping_rule_v1: +32.3134 weighted bps
peakguard_taker_v1 -> stopping_rule_v1: +19.6541 weighted bps
```

But it is not a large capture of the oracle opportunity. The mathematical issue is still a stopping/decay problem under crossing cost:

```text
exit benefit = avoided future decay - additional exit crossing cost - missed continuation.
```

Here the rule saves enough decay to be positive, but it also increases exit crossing cost versus fixed60 (`338.9430` vs `324.0222`). Keep it as a small, explainable candidate and diagnostic baseline; do not promote it as a final exit solution without broader OOS and pressure checks.

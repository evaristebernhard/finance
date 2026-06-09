# Runtime-Safe Four-Cell Shadow Audit

Status: `2026-05-20`.

This pass translates the old CCUSDT four-cell TFI strategy into a Python Bot
shadow policy without enabling real orders.

## Implemented Boundary

The Bot now has a strict online shadow lifecycle:

\[
\text{public quote/trade stream}
\rightarrow
\text{shadow entry}
\rightarrow
\text{fixed 60s online close}
\rightarrow
R_5(t)
\rightarrow
\text{next shadow cell}.
\]

Each shadow entry is now an auditable virtual position with
`shadow_position_id`, `entry_seq`, `entry_ts_us`, `entry_due_ts_us`, trigger
membership, four-cell state, gamma, and target exposure. A shadow position is
closed on the first online event whose `local_ts_us >= entry_due_ts_us`; the
close record carries the original entry context plus `close_seq`, `close_ts_us`,
`held_us`, `exit_lag_us`, and `pnl_bps`. This makes every R5 input traceable to
one prior closed shadow position.

The R5 state is no longer a placeholder and no longer depends on research
labels. It is computed only from shadow entries whose lifecycle close has
already been emitted in Bot event order before a new shadow entry is classified:

\[
R_5(t)=
\frac{\sum_{i\in \mathcal C_5(t)} y_i^+}
{\left|\sum_{i\in \mathcal C_5(t)} y_i^-\right|},
\qquad
\mathcal C_5(t)=\text{last 5 shadow entries closed before the entry decision at }t.
\]

If the denominator is zero, R5 is treated as unavailable rather than infinite.
This matches the conservative prequential spirit of the old scorer.

Runtime inputs remain exchange-visible only:

- `market_quote`
- `market_trade`
- optional private stream events

The Bot does not read `date/`, scored entries, future labels, MFE/MAE, PnL
paths, or root research scripts.

## Validation

Runner bridge smoke:

- Date: `2026-05-18`
- Events: first `5000`
- Runner entries: `32`
- Runner lifecycle closes: `31`
- Compact event audit: `ok=true`
- Feature checkpoint parity with `--window-us 2000000`: `ok=true`
- Current run dir:
  `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260518_20260520_133923`

Direct-online audit uses the same Bot feature module and shadow policy, but
skips the slow stdin/stdout bridge so full days can be checked quickly.

Output:

- `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_133954/summary.json`
- `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_133954/online_triggers.csv`
- `systems/ccusdt_replay_exchange/runs/shadow_four_cell_audit_20260520_133954/online_lifecycle_closes.csv`

## Multi-Day Readout

| date | online entries | research reference | delta | feature mismatches |
| --- | ---: | ---: | ---: | ---: |
| 2026-05-16 | 972 | 261 | +711 | 0 |
| 2026-05-17 | 915 | 199 | +716 | 0 |
| 2026-05-18 | 984 | 304 | +680 | 0 |
| total | 2871 | 764 | +2107 | 0 |

Online cell distribution:

| cell | entries |
| --- | ---: |
| 00_none | 403 |
| 01_frames_only | 628 |
| 10_r5_only | 775 |
| 11_r5_frames | 1065 |

Research reference cell distribution:

| cell | entries |
| --- | ---: |
| 00_none | 305 |
| 01_frames_only | 21 |
| 10_r5_only | 398 |
| 11_r5_frames | 40 |

## Interpretation

The implementation passed the runtime-safety test but failed old-research
trigger parity.

The likely reason is event-grid mismatch:

- the old scorer used the fixed-event factor panel;
- the Bot reacts to exchange-style quote/trade stream events;
- the Bot can trigger immediately after trade events because TFI changes there;
- exact timestamp matches against old scored entries are `0`.

So the result is not ready for real taker IOC entry/exit. The next step is not
PnL. The next step is to decide the runtime decision clock:

1. reproduce the old fixed-event decision grid as an exchange-visible canonical
   stream, then re-run parity;
2. or intentionally define this as a new stream-native policy and audit it as a
   new strategy family.

Until that decision is made, the current shadow policy is a correct online
diagnostic harness, not a live-entry strategy.

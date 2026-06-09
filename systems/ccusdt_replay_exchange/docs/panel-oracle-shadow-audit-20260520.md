# Panel-Oracle Shadow Audit

Status: `2026-05-20`.

This diagnostic proves the old CCUSDT four-cell TFI strategy can be reproduced
on the original fixed-panel decision clock before translating that clock into
the live Bot.

## Boundary

`panel_oracle_shadow_audit.py` is diagnostic-only. It may read:

- legacy fixed factor panel rows;
- old research reference CSVs;
- historical OOS threshold and membership artifacts.

It must not become a runtime Strategy Bot input. Runtime must still rebuild the
same decision frame from exchange-visible quote/trade/L2 events.

## Result

Command:

```powershell
python systems\ccusdt_replay_exchange\diagnostics\panel_oracle_shadow_audit.py --repo-root . --from-date 2026-05-16 --to-date 2026-05-18
```

Output:

- `systems/ccusdt_replay_exchange/runs/panel_oracle_shadow_audit_20260520_140140/summary.json`
- `systems/ccusdt_replay_exchange/runs/panel_oracle_shadow_audit_20260520_140140/panel_oracle_entries.csv`
- `systems/ccusdt_replay_exchange/runs/panel_oracle_shadow_audit_20260520_140140/panel_oracle_mismatches.csv`

The audit passed:

| date | oracle entries | reference entries | timestamp matches | field mismatches |
| --- | ---: | ---: | ---: | ---: |
| 2026-05-16 | 261 | 261 | 261 | 0 |
| 2026-05-17 | 199 | 199 | 199 | 0 |
| 2026-05-18 | 304 | 304 | 304 | 0 |
| total | 764 | 764 | 764 | 0 |

Cell counts also match exactly:

| date | 00 | 10 | 01 | 11 |
| --- | ---: | ---: | ---: | ---: |
| 2026-05-16 | 110 | 130 | 7 | 14 |
| 2026-05-17 | 83 | 100 | 4 | 12 |
| 2026-05-18 | 112 | 168 | 10 | 14 |

## Exact Rules

The reproduced policy uses:

\[
\text{entry}_{c,b}
=
\min\{k\in b:\ g_c(X^{panel}_k)=1\},
\]

where \(c\) is one of the five locked TFI trigger classes and \(b\) is a
60-second fixed-time bucket on the fixed factor panel.

Membership is then merged by exact entry key:

\[
(\text{fold},\text{date},\text{entry\_row}).
\]

The R5 state is prequential:

\[
R_5(t)=
\frac{\sum_{i\in C_5(t)} y_i^+}
{\left|\sum_{i\in C_5(t)} y_i^-\right|},
\qquad
C_5(t)=\text{last 5 entries with }\tau_i+60s<t.
\]

The strict inequality matters: an entry whose 60-second label becomes available
exactly at the current timestamp does not influence the current decision.

The overlay threshold is the locked historical eligible Fold3 threshold:

\[
\text{frames\_since\_mid\_change} \ge 59.80000000000018.
\]

The four-cell frames threshold remains:

\[
\text{frames\_since\_mid\_change} \ge 31.
\]

## Interpretation

This resolves the earlier ambiguity. The stream-native Bot divergence was not
caused by wrong four-cell math. It came from evaluating the old rule on the
wrong decision clock.

The old strategy is:

\[
\text{exchange events}
\rightarrow
\text{fixed panel decision frame}
\rightarrow
\text{four-cell policy}.
\]

The current stream-native shadow policy was:

\[
\text{exchange events}
\rightarrow
\text{quote/trade event clock}
\rightarrow
\text{four-cell policy}.
\]

Those are different strategy families. The next implementation step is a
runtime-safe online panel builder inside the Bot. The Bot should consume only
exchange-visible events, reconstruct `decision_frame_v1`, and evaluate the
shadow policy only on panel-equivalent decision frames.

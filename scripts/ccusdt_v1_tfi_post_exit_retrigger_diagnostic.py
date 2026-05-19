#!/usr/bin/env python
"""Post-exit re-trigger diagnostic for CCUSDT V1 TFI.

This script does not change the exit rule. It asks a narrower question:
after a drawdown exit, can the path produce a fresh, observable second trigger
that would justify a new entry?

The diagnostic is deliberately small:

    latent queue still favorable
    + fresh same-side trade impulse
    + price reclaim from the post-exit reset low

Future returns are used only as labels, not as trigger features.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260519_ccusdt_v1_tfi_post_exit_retrigger_v1"
GUARDRAIL = "research_only_post_exit_retrigger_diagnostic_no_execution_recommendation"
MANAGER_EVENTS = "ccusdt_v1_tfi_small_path_manager_events_20260519_ccusdt_v1_tfi_small_path_manager_v1.csv"
PRIMARY_POLICY = "pm_11_drawdown_h4_peakguard"
US_PER_SECOND = 1_000_000.0
EPS = 1e-12

EVENT_COLS = [
    "event_index",
    "local_timestamp",
    "mid_price",
    "spread_bps",
    "trade_window_count",
    "trade_buy_amount",
    "trade_sell_amount",
    "trade_notional_quote",
    "trade_flow_imbalance",
    "ofi_l1_raw",
    "mlofi_raw_l5",
    "queue_imbalance_5",
    "bid_depth_5",
    "ask_depth_5",
]

OBS_HORIZONS = [3, 5, 10, 15]
PRIMARY_OBS_SEC = 5


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    panel_root: Path
    panel_run_tag: str
    symbol: str
    run_tag: str
    manager_events_name: str

    @property
    def manager_events_csv(self) -> Path:
        return self.date_dir / self.manager_events_name

    @property
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_retrigger_events_{self.run_tag}.csv"

    @property
    def horizon_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_retrigger_horizon_summary_{self.run_tag}.csv"

    @property
    def case_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_retrigger_case_summary_{self.run_tag}.csv"

    @property
    def examples_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_retrigger_examples_{self.run_tag}.csv"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-post-exit-retrigger-diagnostic-{self.run_tag}.md"

    def day_dir(self, date: str) -> Path:
        return self.panel_root / f"run_tag={self.panel_run_tag}" / f"symbol={self.symbol}" / f"dt={date}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument(
        "--panel-root",
        default="data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel",
    )
    parser.add_argument("--panel-run-tag", default="20260517_ccusdt_fixed_factors_v3")
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--manager-events", default=MANAGER_EVENTS)
    parser.add_argument("--primary-policy", default=PRIMARY_POLICY)
    parser.add_argument("--qi-threshold", type=float, default=0.70)
    parser.add_argument("--reclaim-threshold", type=float, default=1.0)
    parser.add_argument("--future-mfe-threshold", type=float, default=10.0)
    parser.add_argument("--future-final-threshold", type=float, default=0.0)
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return ""
    return f"{v:.{digits}f}"


def markdown_table(df: pd.DataFrame, cols: list[str], max_rows: int = 30) -> str:
    cols = [c for c in cols if c in df.columns]
    if not cols or df.empty:
        return "_empty_"
    view = df.loc[:, cols].head(max_rows).copy()
    for col in view.columns:
        if pd.api.types.is_float_dtype(view[col]):
            view[col] = view[col].map(lambda x: fmt(x))
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def load_manager_events(paths: Paths, primary_policy: str) -> pd.DataFrame:
    events = pd.read_csv(paths.manager_events_csv)
    events = events[
        events["policy"].eq(primary_policy) & events["exit_reason"].eq("release_drawdown")
    ].copy()
    numeric_cols = [
        "entry_row",
        "entry_event_index",
        "exit_event_index",
        "exit_sec",
        "policy_gross",
        "baseline_gross60",
        "target_exposure",
        "delta_weighted_vs_60s",
    ]
    for col in numeric_cols:
        if col in events.columns:
            events[col] = pd.to_numeric(events[col], errors="coerce")
    return events.dropna(subset=["entry_row", "exit_event_index", "policy_gross"])


def load_day_panel(paths: Paths, date: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    day_dir = paths.day_dir(date)
    if not day_dir.exists():
        return pd.DataFrame(columns=EVENT_COLS)
    for csv_path in sorted(day_dir.glob("*.csv")):
        frames.append(pd.read_csv(csv_path, usecols=lambda col: col in EVENT_COLS))
    if not frames:
        return pd.DataFrame(columns=EVENT_COLS)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=["event_index", "local_timestamp", "mid_price"]).copy()
    panel["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").astype("int64")
    panel = panel.sort_values(["local_timestamp", "event_index"]).drop_duplicates("event_index", keep="last")
    return panel.reset_index(drop=True)


def locate_event(event_indices: np.ndarray, event_index: int) -> int:
    pos = int(np.searchsorted(event_indices, event_index, side="left"))
    if pos >= len(event_indices):
        pos = len(event_indices) - 1
    if pos > 0 and abs(event_indices[pos] - event_index) > abs(event_indices[pos - 1] - event_index):
        pos -= 1
    return pos


def build_post_exit_path(event: pd.Series, panel: pd.DataFrame) -> pd.DataFrame:
    arrays = {
        col: pd.to_numeric(panel[col], errors="coerce").to_numpy(dtype="float64")
        for col in EVENT_COLS
        if col in panel.columns and col != "event_index"
    }
    event_indices = pd.to_numeric(panel["event_index"], errors="coerce").to_numpy(dtype="int64")
    pos = locate_event(event_indices, int(event["exit_event_index"]))
    side = 1 if str(event["direction_label"]) == "long" else -1
    times = arrays["local_timestamp"]
    mids = arrays["mid_price"]
    t0 = float(times[pos])
    mid0 = float(mids[pos])
    remaining_sec = max(0.0, 60.0 - float(event["exit_sec"]))
    end = int(np.searchsorted(times, t0 + remaining_sec * US_PER_SECOND, side="right"))
    if end <= pos:
        return pd.DataFrame()
    path = panel.iloc[pos:end].copy()
    path["sec_after_exit"] = (pd.to_numeric(path["local_timestamp"], errors="coerce") - t0) / US_PER_SECOND
    path["post_R"] = side * 10_000.0 * np.log(pd.to_numeric(path["mid_price"], errors="coerce").clip(lower=EPS) / max(mid0, EPS))
    path["signed_qi5"] = side * pd.to_numeric(path["queue_imbalance_5"], errors="coerce")
    path["signed_ofi"] = side * pd.to_numeric(path["ofi_l1_raw"], errors="coerce")
    path["signed_mlofi5"] = side * pd.to_numeric(path["mlofi_raw_l5"], errors="coerce")
    path["signed_tfi"] = side * pd.to_numeric(path["trade_flow_imbalance"], errors="coerce")
    buy = pd.to_numeric(path["trade_buy_amount"], errors="coerce").fillna(0.0)
    sell = pd.to_numeric(path["trade_sell_amount"], errors="coerce").fillna(0.0)
    path["signed_trade_amount"] = side * (buy - sell)
    path["target_trade_amount"] = np.where(side > 0, buy, sell)
    path["adverse_trade_amount"] = np.where(side > 0, sell, buy)
    return path


def path_window_features(path: pd.DataFrame, horizon: int) -> dict[str, Any]:
    obs = path[(path["sec_after_exit"] >= 0) & (path["sec_after_exit"] <= horizon)].copy()
    post_obs = obs[obs["sec_after_exit"] > 0].copy()
    future = path[path["sec_after_exit"] >= horizon].copy()
    if obs.empty:
        return {}
    r_end = float(obs["post_R"].iloc[-1])
    trough = float(obs["post_R"].min())
    obs_mfe = float(obs["post_R"].max())
    if future.empty:
        fut_mfe = np.nan
        fut_final = np.nan
        fut_t_mfe = np.nan
    else:
        fut_rel = future["post_R"] - r_end
        fut_mfe = float(fut_rel.max())
        fut_final = float(fut_rel.iloc[-1])
        fut_t_mfe = float(future.loc[fut_rel.idxmax(), "sec_after_exit"] - horizon)

    prefix = f"{horizon}s"
    return {
        f"obs_R_end_{prefix}": r_end,
        f"obs_R_min_{prefix}": trough,
        f"obs_R_max_{prefix}": obs_mfe,
        f"obs_reclaim_{prefix}": r_end - trough,
        f"obs_signed_qi5_mean_{prefix}": float(obs["signed_qi5"].mean()),
        f"obs_signed_ofi_mean_{prefix}": float(obs["signed_ofi"].mean()),
        f"obs_signed_mlofi5_mean_{prefix}": float(obs["signed_mlofi5"].mean()),
        f"obs_signed_tfi_sum_{prefix}": float(post_obs["signed_tfi"].sum(skipna=True)),
        f"obs_signed_tfi_mean_{prefix}": float(post_obs["signed_tfi"].mean()) if not post_obs.empty else np.nan,
        f"obs_signed_trade_amount_sum_{prefix}": float(post_obs["signed_trade_amount"].sum(skipna=True)),
        f"obs_target_trade_amount_sum_{prefix}": float(post_obs["target_trade_amount"].sum(skipna=True)),
        f"obs_adverse_trade_amount_sum_{prefix}": float(post_obs["adverse_trade_amount"].sum(skipna=True)),
        f"obs_trade_notional_sum_{prefix}": float(pd.to_numeric(post_obs["trade_notional_quote"], errors="coerce").sum(skipna=True)),
        f"future_mfe_after_{prefix}": fut_mfe,
        f"future_final_after_{prefix}": fut_final,
        f"future_t_mfe_after_{prefix}": fut_t_mfe,
    }


def build_events(
    manager_events: pd.DataFrame,
    paths: Paths,
    qi_threshold: float,
    reclaim_threshold: float,
    future_mfe_threshold: float,
    future_final_threshold: float,
) -> pd.DataFrame:
    panel_cache: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    for _, event in manager_events.iterrows():
        date = str(event["date"])
        if date not in panel_cache:
            panel_cache[date] = load_day_panel(paths, date)
        panel = panel_cache[date]
        if panel.empty:
            continue
        path = build_post_exit_path(event, panel)
        if path.empty:
            continue
        post_mfe = float(path["post_R"].max())
        post_final = float(path["post_R"].iloc[-1])
        post_t_mfe = float(path.loc[path["post_R"].idxmax(), "sec_after_exit"])
        row = {
            "date": date,
            "entry_row": int(event["entry_row"]),
            "cell": event["cell"],
            "direction_label": event["direction_label"],
            "target_exposure": float(event["target_exposure"]),
            "path_case_class": event.get("path_case_class", "unknown"),
            "exit_sec": float(event["exit_sec"]),
            "exit_event_index": int(event["exit_event_index"]),
            "R_exit": float(event["policy_gross"]),
            "baseline_R60": float(event["baseline_gross60"]),
            "delta_exit_vs_60_weighted": float(event["delta_weighted_vs_60s"]),
            "post_total_mfe": post_mfe,
            "post_final": post_final,
            "post_t_mfe": post_t_mfe,
            "post_total_mfe_weighted": post_mfe * float(event["target_exposure"]),
            "post_final_weighted": post_final * float(event["target_exposure"]),
        }
        exit_row = path.iloc[0]
        row.update(
            {
                "exit_signed_qi5": float(exit_row["signed_qi5"]),
                "exit_signed_ofi": float(exit_row["signed_ofi"]),
                "exit_signed_mlofi5": float(exit_row["signed_mlofi5"]),
                "exit_spread_bps": float(pd.to_numeric(exit_row["spread_bps"], errors="coerce")),
                "exit_trade_notional": float(pd.to_numeric(exit_row["trade_notional_quote"], errors="coerce")),
            }
        )
        for horizon in OBS_HORIZONS:
            row.update(path_window_features(path, horizon))
            prefix = f"{horizon}s"
            row[f"label_productive_after_{prefix}"] = (
                row.get(f"future_mfe_after_{prefix}", np.nan) >= future_mfe_threshold
                and row.get(f"future_final_after_{prefix}", np.nan) >= future_final_threshold
            )
            row[f"rule_retrigger_after_{prefix}"] = (
                row.get(f"obs_signed_qi5_mean_{prefix}", np.nan) >= qi_threshold
                and row.get(f"obs_signed_tfi_sum_{prefix}", np.nan) > 0
                and row.get(f"obs_reclaim_{prefix}", np.nan) >= reclaim_threshold
            )
            row[f"reentry_final_pnl_after_{prefix}"] = (
                row.get(f"future_final_after_{prefix}", np.nan) * float(event["target_exposure"])
                if row[f"rule_retrigger_after_{prefix}"]
                else 0.0
            )
            row[f"reentry_mfe_after_{prefix}"] = (
                row.get(f"future_mfe_after_{prefix}", np.nan) * float(event["target_exposure"])
                if row[f"rule_retrigger_after_{prefix}"]
                else 0.0
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_horizon_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in OBS_HORIZONS:
        prefix = f"{horizon}s"
        pred = events[f"rule_retrigger_after_{prefix}"].astype(bool)
        label = events[f"label_productive_after_{prefix}"].astype(bool)
        tp = pred & label
        fp = pred & ~label
        fn = ~pred & label
        rows.append(
            {
                "obs_horizon_sec": horizon,
                "entries": int(len(events)),
                "predicted_retriggers": int(pred.sum()),
                "productive_labels": int(label.sum()),
                "true_positive": int(tp.sum()),
                "false_positive": int(fp.sum()),
                "false_negative": int(fn.sum()),
                "precision": float(tp.sum() / pred.sum()) if pred.sum() else np.nan,
                "recall": float(tp.sum() / label.sum()) if label.sum() else np.nan,
                "reentry_final_pnl": float(events[f"reentry_final_pnl_after_{prefix}"].sum()),
                "reentry_mfe": float(events[f"reentry_mfe_after_{prefix}"].sum()),
                "mean_future_mfe_pred": float(events.loc[pred, f"future_mfe_after_{prefix}"].mean()) if pred.any() else np.nan,
                "mean_future_final_pred": float(events.loc[pred, f"future_final_after_{prefix}"].mean()) if pred.any() else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_case_summary(events: pd.DataFrame, horizon: int = PRIMARY_OBS_SEC) -> pd.DataFrame:
    prefix = f"{horizon}s"
    return (
        events.groupby("path_case_class", sort=True)
        .agg(
            entries=("entry_row", "size"),
            predicted_retriggers=(f"rule_retrigger_after_{prefix}", "sum"),
            productive_labels=(f"label_productive_after_{prefix}", "sum"),
            post_total_mfe_mean=("post_total_mfe", "mean"),
            post_final_mean=("post_final", "mean"),
            exit_signed_qi5_mean=("exit_signed_qi5", "mean"),
            obs_qi_mean=(f"obs_signed_qi5_mean_{prefix}", "mean"),
            obs_tfi_sum_mean=(f"obs_signed_tfi_sum_{prefix}", "mean"),
            obs_reclaim_mean=(f"obs_reclaim_{prefix}", "mean"),
            reentry_final_pnl=(f"reentry_final_pnl_after_{prefix}", "sum"),
        )
        .reset_index()
    )


def build_examples(events: pd.DataFrame, horizon: int = PRIMARY_OBS_SEC) -> pd.DataFrame:
    prefix = f"{horizon}s"
    predicted = events[events[f"rule_retrigger_after_{prefix}"].astype(bool)].copy()
    top_future = events.nlargest(12, "post_total_mfe").copy()
    selected = events[events["entry_row"].isin([2583437, 1615412, 2377379, 2361187, 2039581, 2334597])].copy()
    frames = []
    if not predicted.empty:
        predicted["example_group"] = "predicted_retrigger"
        frames.append(predicted)
    top_future["example_group"] = "top_post_exit_mfe"
    selected["example_group"] = "selected_cases"
    frames.extend([top_future, selected])
    out = pd.concat(frames, ignore_index=True).drop_duplicates(["example_group", "entry_row"])
    return out.sort_values(["example_group", "post_total_mfe"], ascending=[True, False])


def write_report(
    paths: Paths,
    *,
    events: pd.DataFrame,
    horizon_summary: pd.DataFrame,
    case_summary: pd.DataFrame,
    examples: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    prefix = f"{PRIMARY_OBS_SEC}s"
    selected_cols = [
        "example_group",
        "date",
        "entry_row",
        "path_case_class",
        "direction_label",
        "target_exposure",
        "R_exit",
        "baseline_R60",
        "post_total_mfe",
        "post_final",
        f"obs_signed_qi5_mean_{prefix}",
        f"obs_signed_tfi_sum_{prefix}",
        f"obs_reclaim_{prefix}",
        f"future_mfe_after_{prefix}",
        f"future_final_after_{prefix}",
        f"rule_retrigger_after_{prefix}",
        f"label_productive_after_{prefix}",
    ]
    lines = [
        "# CCUSDT V1 TFI Post-Exit Re-Trigger Diagnostic",
        "",
        f"Status: `{args.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Question",
        "",
        "This pass does not ask whether the first drawdown exit was wrong.",
        "It asks whether, after that exit, a fresh second trigger is observable.",
        "",
        "Use post-exit coordinates:",
        "",
        "$$",
        r"\widetilde R_i(u)=10^4s_i\log\frac{M_{\tau_i+u}}{M_{\tau_i}},",
        "$$",
        "",
        "where \\(\\tau_i\\) is the drawdown exit time.",
        "",
        "At observation horizon \\(g\\), define:",
        "",
        "$$",
        r"Q_i(g)=\frac{1}{g}\int_0^g s_iQI_5(\tau_i+u)\,du,",
        "$$",
        "",
        "$$",
        r"F_i(g)=\sum_{0<u\le g}s_iTFI(\tau_i+u),",
        "$$",
        "",
        "$$",
        r"C_i(g)=\widetilde R_i(g)-\min_{0\le u\le g}\widetilde R_i(u).",
        "$$",
        "",
        "The strict diagnostic trigger is:",
        "",
        "$$",
        rf"Q_i(5)\ge {args.qi_threshold:g},\quad F_i(5)>0,\quad C_i(5)\ge {args.reclaim_threshold:g}.",
        "$$",
        "",
        "Here the trade impulse window is strictly post-exit: \\(0<u\\le g\\).",
        "",
        "Future return is only a label:",
        "",
        "$$",
        rf"\max_{{u\ge g}}\left(\widetilde R_i(u)-\widetilde R_i(g)\right)\ge {args.future_mfe_threshold:g},",
        "$$",
        "",
        "$$",
        rf"\widetilde R_i(T)-\widetilde R_i(g)\ge {args.future_final_threshold:g}.",
        "$$",
        "",
        "## Horizon Scorecard",
        "",
        markdown_table(
            horizon_summary,
            [
                "obs_horizon_sec",
                "entries",
                "predicted_retriggers",
                "productive_labels",
                "true_positive",
                "false_positive",
                "false_negative",
                "precision",
                "recall",
                "reentry_final_pnl",
                "reentry_mfe",
                "mean_future_mfe_pred",
                "mean_future_final_pred",
            ],
        ),
        "",
        "## Case Summary At 5s",
        "",
        markdown_table(
            case_summary,
            [
                "path_case_class",
                "entries",
                "predicted_retriggers",
                "productive_labels",
                "post_total_mfe_mean",
                "post_final_mean",
                "exit_signed_qi5_mean",
                "obs_qi_mean",
                "obs_tfi_sum_mean",
                "obs_reclaim_mean",
                "reentry_final_pnl",
            ],
        ),
        "",
        "## Examples",
        "",
        markdown_table(examples, selected_cols, max_rows=40),
        "",
        "## Read",
        "",
        "- `2583437` is a clean strict re-trigger: queue remains favorable, fresh",
        "  same-side trade returns, and price reclaims from the reset low.",
        "- `2377379` has favorable queue after exit, but same-side trade impulse is",
        "  negative; it should not be re-entered by this diagnostic.",
        "- `1615412` shows that post-exit MFE alone is not enough. It briefly bounces,",
        "  but the 5s diagnostic rejects it because queue/flow are not supportive.",
        "- The 5s rule is high precision and low recall on this small set. Treat it",
        "  as a diagnostic witness, not a full re-entry strategy.",
        "",
        "## Outputs",
        "",
        f"- `{paths.events_csv}`",
        f"- `{paths.horizon_summary_csv}`",
        f"- `{paths.case_summary_csv}`",
        f"- `{paths.examples_csv}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        "python scripts/ccusdt_v1_tfi_post_exit_retrigger_diagnostic.py",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_path(args.date_dir),
        doc_dir=resolve_path(args.doc_dir),
        panel_root=resolve_path(args.panel_root),
        panel_run_tag=args.panel_run_tag,
        symbol=args.symbol,
        run_tag=args.run_tag,
        manager_events_name=args.manager_events,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    manager_events = load_manager_events(paths, args.primary_policy)
    events = build_events(
        manager_events,
        paths,
        qi_threshold=float(args.qi_threshold),
        reclaim_threshold=float(args.reclaim_threshold),
        future_mfe_threshold=float(args.future_mfe_threshold),
        future_final_threshold=float(args.future_final_threshold),
    )
    horizon_summary = build_horizon_summary(events)
    case_summary = build_case_summary(events)
    examples = build_examples(events)

    events.to_csv(paths.events_csv, index=False)
    horizon_summary.to_csv(paths.horizon_summary_csv, index=False)
    case_summary.to_csv(paths.case_summary_csv, index=False)
    examples.to_csv(paths.examples_csv, index=False)
    write_report(
        paths,
        events=events,
        horizon_summary=horizon_summary,
        case_summary=case_summary,
        examples=examples,
        args=args,
    )
    print(f"wrote {paths.events_csv}")
    print(f"wrote {paths.horizon_summary_csv}")
    print(f"wrote {paths.case_summary_csv}")
    print(f"wrote {paths.examples_csv}")
    print(f"wrote {paths.report_md}")
    print(horizon_summary.to_string(index=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Small path manager for CCUSDT V1 TFI.

This is intentionally not a model search. It evaluates a tiny price-path
manager with three transparent actions:

1. protect after release when giveback is too large;
2. harvest when a large peak has gone stale but is still retained;
3. optionally stop no-release paths after 20s.

The output is analyzed by the path casebook classes so we can see which
mechanisms are helped and which right tails are harmed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ccusdt_v1_tfi_price_trailing_param_research import (
    EVENT_COLS,
    EPS,
    US_PER_SECOND,
    load_day_panel,
    locate_entry,
    resolve_repo_path,
)


RUN_TAG = "20260519_ccusdt_v1_tfi_small_path_manager_v1"
GUARDRAIL = "research_only_small_price_path_manager_no_execution_recommendation"
CASEBOOK_FILE = "ccusdt_v1_tfi_path_casebook_events_20260519_ccusdt_v1_tfi_path_casebook_v1.csv"


@dataclass(frozen=True)
class PolicySpec:
    policy: str
    use_drawdown: bool
    use_plateau: bool
    use_no_release: bool
    manage_cell11_only: bool = False
    drawdown_start_sec: float = 0.0
    low_release_peak_min_sec: float = 0.0
    low_release_ceiling_bps: float = 8.0
    release_min_bps: float = 5.0
    drawdown_floor_bps: float = 2.0
    drawdown_frac: float = 0.35
    plateau_min_bps: float = 10.0
    plateau_age_sec: float = 8.0
    plateau_retention: float = 0.85
    no_release_horizon_sec: float = 20.0
    no_release_h_bps: float = 3.0
    no_release_r_ceiling_bps: float = 0.0
    max_hold_sec: float = 60.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument("--casebook-file", default=CASEBOOK_FILE)
    parser.add_argument(
        "--panel-root",
        default="data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel",
    )
    parser.add_argument("--panel-run-tag", default="20260517_ccusdt_fixed_factors_v3")
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    return parser.parse_args()


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


def finite_quantile(values: pd.Series, q: float) -> float:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    return float(np.quantile(arr, q))


def cvar(values: pd.Series, q: float = 0.05) -> float:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    n = max(1, int(np.ceil(len(arr) * q)))
    return float(np.sort(arr)[:n].mean())


def policy_specs() -> list[PolicySpec]:
    return [
        PolicySpec(
            policy="pm_drawdown_only",
            use_drawdown=True,
            use_plateau=False,
            use_no_release=False,
        ),
        PolicySpec(
            policy="pm_11_drawdown_only",
            use_drawdown=True,
            use_plateau=False,
            use_no_release=False,
            manage_cell11_only=True,
        ),
        PolicySpec(
            policy="pm_11_drawdown_h4",
            use_drawdown=True,
            use_plateau=False,
            use_no_release=False,
            manage_cell11_only=True,
            release_min_bps=4.0,
        ),
        PolicySpec(
            policy="pm_11_drawdown_h4_start5s",
            use_drawdown=True,
            use_plateau=False,
            use_no_release=False,
            manage_cell11_only=True,
            release_min_bps=4.0,
            drawdown_start_sec=5.0,
        ),
        PolicySpec(
            policy="pm_11_drawdown_h4_peakguard",
            use_drawdown=True,
            use_plateau=False,
            use_no_release=False,
            manage_cell11_only=True,
            release_min_bps=4.0,
            low_release_peak_min_sec=1.5,
            low_release_ceiling_bps=8.0,
        ),
        PolicySpec(
            policy="pm_drawdown_plateau",
            use_drawdown=True,
            use_plateau=True,
            use_no_release=False,
        ),
        PolicySpec(
            policy="pm_full_tiny",
            use_drawdown=True,
            use_plateau=True,
            use_no_release=True,
        ),
    ]


def load_casebook(path: Path) -> pd.DataFrame:
    entries = pd.read_csv(path)
    numeric_cols = [
        "entry_row",
        "entry_event_index",
        "matched_event_index",
        "target_exposure",
        "R60",
        "H60",
        "D60",
        "weighted_gross60",
    ]
    for col in numeric_cols:
        if col in entries.columns:
            entries[col] = pd.to_numeric(entries[col], errors="coerce")
    entries = entries.dropna(subset=["entry_row", "entry_event_index", "target_exposure"])
    entries["entry_row"] = entries["entry_row"].astype("int64")
    entries["entry_event_index"] = entries["entry_event_index"].astype("int64")
    return entries


def day_dir(panel_root: Path, panel_run_tag: str, symbol: str, date: str) -> Path:
    return panel_root / f"run_tag={panel_run_tag}" / f"symbol={symbol}" / f"dt={date}"


def build_path(entry: pd.Series, arrays: dict[str, np.ndarray]) -> dict[str, Any] | None:
    event_indices = arrays["event_index"]
    times = arrays["local_timestamp"]
    mids = arrays["mid_price"]
    entry_event_index = int(entry["entry_event_index"])
    pos = locate_entry(event_indices, entry_event_index)
    t0 = float(times[pos])
    mid0 = float(mids[pos])
    if not np.isfinite(mid0) or mid0 <= 0:
        return None
    side = 1 if str(entry["direction_label"]) == "long" else -1
    start = int(np.searchsorted(times, t0, side="right"))
    end = int(np.searchsorted(times, t0 + 60.0 * US_PER_SECOND, side="right"))
    if end <= start:
        return None
    idx = np.arange(start, end, dtype="int64")
    hold_sec = (times[idx] - t0) / US_PER_SECOND
    rets = side * 10_000.0 * np.log(np.maximum(mids[idx], EPS) / max(mid0, EPS))
    return {
        "idx": idx,
        "hold_sec": hold_sec,
        "rets": rets,
        "matched_event_index_rebuilt": int(event_indices[pos]),
    }


def fixed_exit(path: dict[str, Any], arrays: dict[str, np.ndarray], horizon_sec: float) -> dict[str, Any]:
    hold_sec = path["hold_sec"]
    rets = path["rets"]
    idx = path["idx"]
    eligible = np.flatnonzero(hold_sec <= horizon_sec)
    pos = int(eligible[-1]) if len(eligible) else len(hold_sec) - 1
    exit_idx = int(idx[pos])
    return {
        "exit_reason": f"fixed_{int(horizon_sec)}s",
        "exit_sec": float(hold_sec[pos]),
        "exit_event_index": int(arrays["event_index"][exit_idx]),
        "policy_gross": float(rets[pos]),
        "H_exit": float(np.max(rets[: pos + 1])),
        "D_exit": float(np.max(rets[: pos + 1]) - rets[pos]),
        "tau_H_exit": float(hold_sec[int(np.argmax(rets[: pos + 1]))]),
        "peak_age_exit": float(hold_sec[pos] - hold_sec[int(np.argmax(rets[: pos + 1]))]),
    }


def path_manager_exit(path: dict[str, Any], arrays: dict[str, np.ndarray], spec: PolicySpec) -> dict[str, Any]:
    hold_sec = path["hold_sec"]
    rets = path["rets"]
    idx = path["idx"]
    h = -np.inf
    peak_sec = np.nan
    exit_pos: int | None = None
    exit_reason = "fixed_60s"
    exit_threshold = np.nan

    for pos, (t, r) in enumerate(zip(hold_sec, rets, strict=False)):
        if t > spec.max_hold_sec:
            break
        if r > h + 1e-12:
            h = float(r)
            peak_sec = float(t)
        d = h - float(r)
        peak_age = float(t) - peak_sec if np.isfinite(peak_sec) else np.nan
        retention = float(r) / (abs(h) + EPS) if np.isfinite(h) else np.nan

        if (
            spec.use_no_release
            and t >= spec.no_release_horizon_sec
            and h < spec.no_release_h_bps
            and r <= spec.no_release_r_ceiling_bps
        ):
            exit_pos = pos
            exit_reason = "no_release_timeout"
            exit_threshold = spec.no_release_h_bps
            break

        if spec.use_drawdown and t >= spec.drawdown_start_sec and h >= spec.release_min_bps:
            if h < spec.low_release_ceiling_bps and peak_sec < spec.low_release_peak_min_sec:
                continue
            threshold = max(spec.drawdown_floor_bps, spec.drawdown_frac * h)
            if d >= threshold:
                exit_pos = pos
                exit_reason = "release_drawdown"
                exit_threshold = threshold
                break

        if (
            spec.use_plateau
            and h >= spec.plateau_min_bps
            and peak_age >= spec.plateau_age_sec
            and retention >= spec.plateau_retention
        ):
            exit_pos = pos
            exit_reason = "peak_age_harvest"
            exit_threshold = spec.plateau_age_sec
            break

    if exit_pos is None:
        fixed = fixed_exit(path, arrays, spec.max_hold_sec)
        fixed.update(
            {
                "exit_reason": "fixed_60s",
                "exit_threshold": np.nan,
                "retention_exit": fixed["policy_gross"] / (abs(fixed["H_exit"]) + EPS),
            }
        )
        return fixed

    exit_idx = int(idx[exit_pos])
    path_slice = rets[: exit_pos + 1]
    peak_pos = int(np.argmax(path_slice))
    h_exit = float(path_slice[peak_pos])
    gross = float(rets[exit_pos])
    return {
        "exit_reason": exit_reason,
        "exit_sec": float(hold_sec[exit_pos]),
        "exit_event_index": int(arrays["event_index"][exit_idx]),
        "policy_gross": gross,
        "H_exit": h_exit,
        "D_exit": float(h_exit - gross),
        "tau_H_exit": float(hold_sec[peak_pos]),
        "peak_age_exit": float(hold_sec[exit_pos] - hold_sec[peak_pos]),
        "retention_exit": gross / (abs(h_exit) + EPS),
        "exit_threshold": float(exit_threshold),
    }


def simulate_entries(
    entries: pd.DataFrame,
    panel_root: Path,
    panel_run_tag: str,
    symbol: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    specs = policy_specs()
    rows: list[dict[str, Any]] = []
    day_rows: list[dict[str, Any]] = []
    for date, group in entries.groupby("date", sort=True):
        panel_path = day_dir(panel_root, panel_run_tag, symbol, str(date))
        panel = load_day_panel(
            type(
                "PanelPaths",
                (),
                {
                    "panel_root": panel_root,
                    "panel_run_tag": panel_run_tag,
                    "symbol": symbol,
                    "day_dir": lambda self, d: panel_root
                    / f"run_tag={panel_run_tag}"
                    / f"symbol={symbol}"
                    / f"dt={d}",
                },
            )(),
            str(date),
        )
        if panel.empty:
            day_rows.append(
                {
                    "date": str(date),
                    "status": "missing_panel",
                    "entries": int(len(group)),
                    "panel_path": str(panel_path),
                    "panel_rows": 0,
                }
            )
            continue
        arrays = {
            col: pd.to_numeric(panel[col], errors="coerce").to_numpy(dtype="float64")
            for col in EVENT_COLS
            if col in panel.columns
        }
        arrays["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").to_numpy(dtype="int64")
        before = len(rows)
        for _, entry in group.iterrows():
            path = build_path(entry, arrays)
            if path is None:
                continue
            base60 = fixed_exit(path, arrays, 60.0)
            base30 = fixed_exit(path, arrays, 30.0)
            common = {
                "date": str(entry["date"]),
                "fold": entry.get("fold"),
                "entry_row": int(entry["entry_row"]),
                "entry_event_index": int(entry["entry_event_index"]),
                "matched_event_index": int(entry.get("matched_event_index", np.nan)),
                "matched_event_index_rebuilt": path["matched_event_index_rebuilt"],
                "cell": entry["cell"],
                "direction_label": entry["direction_label"],
                "target_exposure": float(entry["target_exposure"]),
                "path_case_class": entry.get("path_case_class", "unknown"),
                "is_path_case": bool(entry.get("is_path_case", False)),
                "R5_casebook": float(entry.get("R5", np.nan)),
                "R10_casebook": float(entry.get("R10", np.nan)),
                "R20_casebook": float(entry.get("R20", np.nan)),
                "R60_casebook": float(entry.get("R60", np.nan)),
                "H60_casebook": float(entry.get("H60", np.nan)),
                "D60_casebook": float(entry.get("D60", np.nan)),
                "baseline_gross60": float(base60["policy_gross"]),
                "baseline_gross30": float(base30["policy_gross"]),
            }
            fixed_rows = [
                ("fixed_30s", base30),
                ("fixed_60s", base60),
            ]
            for policy_name, result in fixed_rows:
                row = dict(common)
                row.update(result)
                row["policy"] = policy_name
                row["family"] = "fixed"
                row["managed_by_policy"] = False
                row["weighted_gross"] = row["policy_gross"] * row["target_exposure"]
                row["baseline_weighted_gross60"] = common["baseline_gross60"] * row["target_exposure"]
                row["delta_weighted_vs_60s"] = row["weighted_gross"] - row["baseline_weighted_gross60"]
                rows.append(row)
            for spec in specs:
                managed_by_policy = (not spec.manage_cell11_only) or common["cell"] == "11_r5_frames"
                result = path_manager_exit(path, arrays, spec) if managed_by_policy else dict(base60)
                row = dict(common)
                row.update(result)
                row["policy"] = spec.policy
                row["family"] = "small_path_manager"
                row["use_drawdown"] = spec.use_drawdown
                row["use_plateau"] = spec.use_plateau
                row["use_no_release"] = spec.use_no_release
                row["manage_cell11_only"] = spec.manage_cell11_only
                row["drawdown_start_sec"] = spec.drawdown_start_sec
                row["low_release_peak_min_sec"] = spec.low_release_peak_min_sec
                row["managed_by_policy"] = managed_by_policy
                row["weighted_gross"] = row["policy_gross"] * row["target_exposure"]
                row["baseline_weighted_gross60"] = common["baseline_gross60"] * row["target_exposure"]
                row["delta_weighted_vs_60s"] = row["weighted_gross"] - row["baseline_weighted_gross60"]
                rows.append(row)
        day_rows.append(
            {
                "date": str(date),
                "status": "ok",
                "entries": int(len(group)),
                "simulated_entries": int((len(rows) - before) / (2 + len(specs))),
                "panel_path": str(panel_path),
                "panel_rows": int(len(panel)),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(day_rows)


def build_scorecard(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    exposure_sum = events[events["policy"].eq("fixed_60s")]["target_exposure"].sum()
    for policy, group in events.groupby("policy", sort=False):
        weighted = pd.to_numeric(group["weighted_gross"], errors="coerce")
        baseline = pd.to_numeric(group["baseline_weighted_gross60"], errors="coerce")
        delta = pd.to_numeric(group["delta_weighted_vs_60s"], errors="coerce")
        daily = group.groupby("date", sort=True)["weighted_gross"].sum()
        baseline_daily = group.groupby("date", sort=True)["baseline_weighted_gross60"].sum()
        q90 = finite_quantile(group["policy_gross"], 0.90)
        baseline_q90 = finite_quantile(
            events[events["policy"].eq("fixed_60s")]["policy_gross"], 0.90
        )
        rows.append(
            {
                "policy": policy,
                "family": str(group["family"].iloc[0]),
                "entries": int(len(group)),
                "dates": int(group["date"].nunique()),
                "total_c0": float(weighted.sum()),
                "total_c1": float(weighted.sum() - exposure_sum),
                "total_c2": float(weighted.sum() - 2.0 * exposure_sum),
                "baseline_total_c0": float(baseline.sum()),
                "delta_vs_60s": float(delta.sum()),
                "mean_gross": float(group["policy_gross"].mean()),
                "median_gross": finite_quantile(group["policy_gross"], 0.50),
                "gt2_rate": float((group["policy_gross"] > 2.0).mean()),
                "q90_gross": q90,
                "right_tail_retention_q90": q90 / baseline_q90 if abs(baseline_q90) > EPS else np.nan,
                "cvar05_gross": cvar(group["policy_gross"]),
                "single_worst_weighted": float(weighted.min()),
                "single_cvar05_weighted": cvar(weighted),
                "worst_day": float(daily.min()),
                "baseline_worst_day": float(baseline_daily.min()),
                "positive_days": int((daily > 0).sum()),
                "mean_exit_sec": float(group["exit_sec"].mean()),
                "managed_entries": int(group["managed_by_policy"].fillna(False).sum()),
                "managed_rate": float(group["managed_by_policy"].fillna(False).mean()),
                "action_exit_rate": float(
                    group["exit_reason"]
                    .isin(["no_release_timeout", "release_drawdown", "peak_age_harvest"])
                    .mean()
                ),
                "saved_loser_pnl": float(delta[baseline < 0].clip(lower=0).sum()),
                "killed_winner_pnl": float((-delta[baseline > 0]).clip(lower=0).sum()),
            }
        )
    out = pd.DataFrame(rows)
    out["save_kill_ratio"] = out["saved_loser_pnl"] / out["killed_winner_pnl"].replace(0, np.nan)
    return out.sort_values(["family", "total_c0"], ascending=[True, False]).reset_index(drop=True)


def build_daily(events: pd.DataFrame) -> pd.DataFrame:
    return (
        events.groupby(["policy", "family", "date"], sort=True)
        .agg(
            entries=("entry_row", "size"),
            total_c0=("weighted_gross", "sum"),
            baseline_total_c0=("baseline_weighted_gross60", "sum"),
            delta_vs_60s=("delta_weighted_vs_60s", "sum"),
            mean_exit_sec=("exit_sec", "mean"),
            no_release_timeout_rate=("exit_reason", lambda s: float((s == "no_release_timeout").mean())),
            release_drawdown_rate=("exit_reason", lambda s: float((s == "release_drawdown").mean())),
            peak_age_harvest_rate=("exit_reason", lambda s: float((s == "peak_age_harvest").mean())),
            managed_rate=("managed_by_policy", "mean"),
        )
        .reset_index()
    )


def build_case_summary(events: pd.DataFrame) -> pd.DataFrame:
    return (
        events.groupby(["policy", "family", "path_case_class"], sort=True)
        .agg(
            entries=("entry_row", "size"),
            total_c0=("weighted_gross", "sum"),
            baseline_total_c0=("baseline_weighted_gross60", "sum"),
            delta_vs_60s=("delta_weighted_vs_60s", "sum"),
            mean_gross=("policy_gross", "mean"),
            gross_positive_rate=("policy_gross", lambda s: float((s > 0).mean())),
            mean_exit_sec=("exit_sec", "mean"),
            no_release_timeout_rate=("exit_reason", lambda s: float((s == "no_release_timeout").mean())),
            release_drawdown_rate=("exit_reason", lambda s: float((s == "release_drawdown").mean())),
            peak_age_harvest_rate=("exit_reason", lambda s: float((s == "peak_age_harvest").mean())),
            managed_rate=("managed_by_policy", "mean"),
        )
        .reset_index()
    )


def build_examples(events: pd.DataFrame, policy: str = "pm_11_drawdown_h4_peakguard", n: int = 12) -> pd.DataFrame:
    view = events[events["policy"].eq(policy)].copy()
    saved = view.nlargest(n, "delta_weighted_vs_60s").copy()
    saved["example_side"] = "saved_vs_60s"
    killed = view.nsmallest(n, "delta_weighted_vs_60s").copy()
    killed["example_side"] = "killed_vs_60s"
    return pd.concat([saved, killed], ignore_index=True)


def write_report(
    report_path: Path,
    *,
    date_dir: Path,
    run_tag: str,
    events: pd.DataFrame,
    scorecard: pd.DataFrame,
    daily: pd.DataFrame,
    case_summary: pd.DataFrame,
    examples: pd.DataFrame,
    day_status: pd.DataFrame,
) -> None:
    primary = "pm_11_drawdown_h4_peakguard"
    primary_case = case_summary[case_summary["policy"].eq(primary)].copy()
    primary_case = primary_case.sort_values("path_case_class")
    primary_daily = daily[daily["policy"].eq(primary)].sort_values("delta_vs_60s")
    score_view = scorecard.sort_values("total_c0", ascending=False)
    reason_counts = (
        events[events["policy"].eq(primary)]["exit_reason"]
        .value_counts(normalize=True)
        .rename_axis("exit_reason")
        .reset_index(name="rate")
    )
    example_cols = [
        "example_side",
        "date",
        "entry_row",
        "path_case_class",
        "cell",
        "direction_label",
        "target_exposure",
        "baseline_gross60",
        "policy_gross",
        "delta_weighted_vs_60s",
        "exit_reason",
        "exit_sec",
        "H_exit",
        "D_exit",
        "peak_age_exit",
    ]
    lines = [
        "# CCUSDT V1 TFI Small Path Manager",
        "",
        f"Status: `{run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Model",
        "",
        "This is a small path manager, not a fitted entry model. It uses only:",
        "",
        "$$",
        r"H_t=\max_{u\le t}R_u,\qquad D_t=H_t-R_t,\qquad A_t=t-\tau_H.",
        "$$",
        "",
        "The primary rule `pm_11_drawdown_h4_peakguard` applies the manager only to",
        "`11_r5_frames` entries. This keeps it as high-exposure insurance rather",
        "than a universal exit overlay. Its active rule is:",
        "",
        "$$",
        r"\tau=\inf\{t:\ H_t\ge4,\ D_t\ge\max(2,0.35H_t)\}",
        "$$",
        "",
        "For small releases, it requires the peak not to be an opening flicker:",
        "",
        "$$",
        r"H_t<8\Rightarrow \tau_H\ge1.5.",
        "$$",
        "",
        "The broader ablation `pm_drawdown_plateau` also tests:",
        "",
        "$$",
        r"\tau=\inf\{t:\ H_t\ge10,\ A_t\ge8,\ R_t/H_t\ge0.85\}",
        "$$",
        "",
        "The broader ablation `pm_full_tiny` also tests, conservatively:",
        "",
        "$$",
        r"\tau=\inf\{t\ge20:\ H_t<3,\ R_t\le0\}.",
        "$$",
        "",
        "Otherwise it exits at 60s. The ablations show whether plateau harvest",
        "and no-release timeout help or simply cut right tail.",
        "",
        "All totals below are C=0 mid-price path gross multiplied by the stored",
        "`target_exposure`. `total_c1` and `total_c2` subtract 1 or 2 bps pressure",
        "per unit exposure, but the main comparison is the C=0 delta versus fixed 60s.",
        "",
        "## Scorecard",
        "",
        markdown_table(
            score_view,
            [
                "policy",
                "family",
                "total_c0",
                "total_c1",
                "total_c2",
                "delta_vs_60s",
                "worst_day",
                "positive_days",
                "q90_gross",
                "right_tail_retention_q90",
                "cvar05_gross",
                "single_worst_weighted",
                "mean_exit_sec",
                "managed_entries",
                "managed_rate",
                "action_exit_rate",
                "saved_loser_pnl",
                "killed_winner_pnl",
                "save_kill_ratio",
            ],
        ),
        "",
        "## Primary Case Decomposition",
        "",
        markdown_table(
            primary_case,
            [
                "path_case_class",
                "entries",
                "total_c0",
                "baseline_total_c0",
                "delta_vs_60s",
                "gross_positive_rate",
                "mean_exit_sec",
                "managed_rate",
                "no_release_timeout_rate",
                "release_drawdown_rate",
                "peak_age_harvest_rate",
            ],
        ),
        "",
        "## Primary Exit Reasons",
        "",
        markdown_table(reason_counts, ["exit_reason", "rate"]),
        "",
        "## Worst Primary Daily Deltas",
        "",
        markdown_table(
            primary_daily,
            [
                "date",
                "entries",
                "total_c0",
                "baseline_total_c0",
                "delta_vs_60s",
                "mean_exit_sec",
                "managed_rate",
                "no_release_timeout_rate",
                "release_drawdown_rate",
                "peak_age_harvest_rate",
            ],
        ),
        "",
        "## Primary Examples",
        "",
        markdown_table(examples, example_cols, max_rows=24),
        "",
        "## Day Status",
        "",
        markdown_table(day_status, ["date", "status", "entries", "simulated_entries", "panel_rows"]),
        "",
        "## Read",
        "",
        "- The manager should be judged by case transfer, not only total PnL.",
        "- If `release_drawdown` saves `fast_release_reversal` but kills too much",
        "  `non_case`, the drawdown threshold is too tight.",
        "- If `peak_age_harvest` improves `large_release_plateau_decay` without",
        "  damaging `late_release_collapse`, the release/decay framing is working.",
        "- The no-release timeout is the most suspect component because some genuine",
        "  right tail arrives late; keep it only if the ablation supports it.",
        "",
        "## Outputs",
        "",
        f"- `{report_path}`",
        f"- `{date_dir / f'ccusdt_v1_tfi_small_path_manager_events_{run_tag}.csv'}`",
        f"- `{date_dir / f'ccusdt_v1_tfi_small_path_manager_scorecard_{run_tag}.csv'}`",
        f"- `{date_dir / f'ccusdt_v1_tfi_small_path_manager_case_summary_{run_tag}.csv'}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        "python scripts/ccusdt_v1_tfi_small_path_manager.py",
        "```",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    date_dir = resolve_repo_path(args.date_dir)
    doc_dir = resolve_repo_path(args.doc_dir)
    panel_root = resolve_repo_path(args.panel_root)
    date_dir.mkdir(parents=True, exist_ok=True)
    doc_dir.mkdir(parents=True, exist_ok=True)

    casebook_path = resolve_repo_path(Path(args.date_dir) / args.casebook_file)
    entries = load_casebook(casebook_path)
    events, day_status = simulate_entries(entries, panel_root, args.panel_run_tag, args.symbol)
    if events.empty:
        raise RuntimeError("No path manager events generated.")

    scorecard = build_scorecard(events)
    daily = build_daily(events)
    case_summary = build_case_summary(events)
    examples = build_examples(events)

    events_path = date_dir / f"ccusdt_v1_tfi_small_path_manager_events_{args.run_tag}.csv"
    score_path = date_dir / f"ccusdt_v1_tfi_small_path_manager_scorecard_{args.run_tag}.csv"
    daily_path = date_dir / f"ccusdt_v1_tfi_small_path_manager_daily_{args.run_tag}.csv"
    case_path = date_dir / f"ccusdt_v1_tfi_small_path_manager_case_summary_{args.run_tag}.csv"
    examples_path = date_dir / f"ccusdt_v1_tfi_small_path_manager_examples_{args.run_tag}.csv"
    day_status_path = date_dir / f"ccusdt_v1_tfi_small_path_manager_day_status_{args.run_tag}.csv"
    report_path = doc_dir / f"v1-tfi-small-path-manager-{args.run_tag}.md"

    events.to_csv(events_path, index=False)
    scorecard.to_csv(score_path, index=False)
    daily.to_csv(daily_path, index=False)
    case_summary.to_csv(case_path, index=False)
    examples.to_csv(examples_path, index=False)
    day_status.to_csv(day_status_path, index=False)

    write_report(
        report_path,
        date_dir=date_dir,
        run_tag=args.run_tag,
        events=events,
        scorecard=scorecard,
        daily=daily,
        case_summary=case_summary,
        examples=examples,
        day_status=day_status,
    )

    print(f"wrote {events_path}")
    print(f"wrote {score_path}")
    print(f"wrote {daily_path}")
    print(f"wrote {case_path}")
    print(f"wrote {examples_path}")
    print(f"wrote {day_status_path}")
    print(f"wrote {report_path}")
    print(
        scorecard[
            [
                "policy",
                "total_c0",
                "delta_vs_60s",
                "worst_day",
                "positive_days",
                "q90_gross",
                "right_tail_retention_q90",
                "single_worst_weighted",
                "mean_exit_sec",
                "managed_entries",
                "managed_rate",
                "action_exit_rate",
                "saved_loser_pnl",
                "killed_winner_pnl",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()

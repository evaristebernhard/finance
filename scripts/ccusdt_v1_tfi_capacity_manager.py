#!/usr/bin/env python
"""Capacity manager diagnostics for CCUSDT V1 TFI.

This pass keeps the signal model fixed and asks a smaller question:

    given target exposures w_i = b_i gamma_cell,
    how much PnL is lost when total open exposure is capped at 3x?

The online FIFO and priority clips are implementable from available intervals.
The priority replacement row is a terminal-PnL proxy only: it reallocates
capacity between open intervals without rebuilding the path PnL at the
replacement timestamp.
"""

from __future__ import annotations

import argparse
import heapq
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1"
GUARDRAIL = "research_only_capacity_manager_no_execution_recommendation"
SOURCE_RUN_TAG = "20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1"
MAX_LEVERAGE = 3.0
PRESSURES = [0.0, 1.0, 2.0]
CELL_ORDER = ["00_none", "10_r5_only", "01_frames_only", "11_r5_frames"]
CELL_PRIORITY = {
    "01_frames_only": 1.0,
    "00_none": 2.0,
    "10_r5_only": 3.0,
    "11_r5_frames": 4.0,
}
ANCHOR_VARIANT = "anchor_full_1_0p75_0p25_4"
MAIN_LOW_CONCURRENCY_VARIANT = "grid_g00_1.25_g10_0.75_g01_0_g11_0.75"
HIGH_GAMMA_VARIANT = "grid_g00_1.25_g10_2_g01_1_g11_5"
KEY_VARIANTS = [ANCHOR_VARIANT, MAIN_LOW_CONCURRENCY_VARIANT, HIGH_GAMMA_VARIANT]


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    run_tag: str
    source_run_tag: str

    @property
    def unit_entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_unit_entries_{self.source_run_tag}.csv"

    @property
    def variants_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_variants_{self.source_run_tag}.csv"

    @property
    def summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_capacity_manager_summary_{self.run_tag}.csv"

    @property
    def cell_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_capacity_manager_cell_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_capacity_manager_daily_{self.run_tag}.csv"

    @property
    def clipped_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_capacity_manager_clipped_legs_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_capacity_manager_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-capacity-manager-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--max-leverage", type=float, default=MAX_LEVERAGE)
    parser.add_argument("--top-n", type=int, default=8)
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def fmt(value: Any, digits: int = 4) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return ""
    return f"{v:.{digits}f}"


def markdown_table(df: pd.DataFrame, cols: list[str], max_rows: int = 30) -> str:
    cols = [c for c in cols if c in df.columns]
    if df.empty or not cols:
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


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > 1e-12 else np.nan


def cvar(values: np.ndarray, q: float) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    k = max(1, int(np.ceil(q * len(arr))))
    return float(np.partition(arr, k - 1)[:k].mean())


def max_drawdown(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    curve = np.cumsum(arr)
    peak = np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:]
    return float(np.min(curve - peak))


def max_interval_exposure(starts: np.ndarray, ends: np.ndarray, exposures: np.ndarray) -> float:
    valid = (
        np.isfinite(starts)
        & np.isfinite(ends)
        & np.isfinite(exposures)
        & (ends > starts)
        & (exposures > 0)
    )
    if not np.any(valid):
        return np.nan
    s = starts[valid]
    e = ends[valid]
    w = exposures[valid]
    times = np.concatenate([s, e])
    deltas = np.concatenate([w, -w])
    order_kind = np.concatenate([np.ones_like(w), np.zeros_like(w)])
    order = np.lexsort((order_kind, times))
    running = 0.0
    peak = 0.0
    for idx in order:
        running += float(deltas[idx])
        peak = max(peak, running)
    return peak


def policy_columns(strategy: str) -> tuple[str, str | None]:
    if strategy == "manager_plus_q70_watcher":
        return "unit_manager_plus_q70_watcher", "watcher_q70_absorb_reclaim2"
    if strategy == "manager_plus_q65_watcher":
        return "unit_manager_plus_q65_watcher", "watcher_q65_absorb_reclaim2"
    if strategy == "manager_plus_impulse":
        return "unit_manager_plus_impulse", "impulse_only"
    if strategy == "manager_only":
        return "unit_manager_only", None
    if strategy == "fixed60":
        return "unit_fixed60", None
    raise ValueError(f"Unsupported strategy: {strategy}")


def select_variants(variants: pd.DataFrame, top_n: int) -> pd.DataFrame:
    rows = []
    for pressure in PRESSURES:
        p = variants[variants["pressure_bps"].eq(pressure)].copy()
        for strategy in ["manager_plus_q70_watcher", "manager_plus_q65_watcher"]:
            group = p[p["strategy"].eq(strategy)]
            if group.empty:
                continue
            rows.append(group.sort_values("scaled_total_100", ascending=False).head(top_n))
            rows.append(group.sort_values("total", ascending=False).head(3))
            key_variants = group[group["variant"].isin(KEY_VARIANTS)]
            if not key_variants.empty:
                rows.append(key_variants)
    selected = pd.concat(rows, ignore_index=True)
    key_cols = ["strategy", "variant", "pressure_bps"]
    return selected.drop_duplicates(key_cols).reset_index(drop=True)


def gamma_map(row: pd.Series) -> dict[str, float]:
    return {
        "00_none": float(row["gamma00_none"]),
        "10_r5_only": float(row["gamma10_r5_only"]),
        "01_frames_only": float(row["gamma01_frames_only"]),
        "11_r5_frames": float(row["gamma11_r5_frames"]),
    }


def build_legs(entries: pd.DataFrame, variant: pd.Series) -> pd.DataFrame:
    strategy = str(variant["strategy"])
    pressure = float(variant["pressure_bps"])
    _, watcher_name = policy_columns(strategy)
    gmap = gamma_map(variant)
    work = entries.copy()
    work["gamma"] = work["cell"].map(gmap).astype(float)
    work["desired_exposure"] = work["base_weight"].astype(float) * work["gamma"]
    work = work[work["desired_exposure"] > 0].copy()
    base = pd.DataFrame(
        {
            "date": work["date"].astype(str),
            "entry_row": work["entry_row"].astype("int64"),
            "cell": work["cell"].astype(str),
            "leg_kind": "base",
            "start_ts": pd.to_numeric(work["entry_ts"], errors="coerce"),
            "end_ts": pd.to_numeric(work["entry_end_ts"], errors="coerce"),
            "desired_exposure": work["desired_exposure"].astype(float),
            "unit": pd.to_numeric(work["policy_gross"], errors="coerce") - pressure,
            "direction_label": work["direction_label"].astype(str),
        }
    )
    legs = [base]
    if watcher_name is not None:
        trigger_col = f"watch_trigger_{watcher_name}"
        watch = work[work[trigger_col].astype(bool)].copy()
        if not watch.empty:
            legs.append(
                pd.DataFrame(
                    {
                        "date": watch["date"].astype(str),
                        "entry_row": watch["entry_row"].astype("int64"),
                        "cell": watch["cell"].astype(str),
                        "leg_kind": f"watch_{watcher_name}",
                        "start_ts": pd.to_numeric(watch[f"watch_start_ts_{watcher_name}"], errors="coerce"),
                        "end_ts": pd.to_numeric(watch[f"watch_end_ts_{watcher_name}"], errors="coerce"),
                        "desired_exposure": watch["desired_exposure"].astype(float),
                        "unit": pd.to_numeric(watch[f"watch_final_pnl_{watcher_name}"], errors="coerce") - pressure,
                        "direction_label": watch["direction_label"].astype(str),
                    }
                )
            )
    out = pd.concat(legs, ignore_index=True)
    out = out.dropna(subset=["start_ts", "end_ts", "desired_exposure", "unit"])
    out = out[(out["end_ts"] > out["start_ts"]) & (out["desired_exposure"] > 0)].copy()
    out["priority"] = out["cell"].map(CELL_PRIORITY).astype(float)
    out.loc[out["leg_kind"].str.startswith("watch_"), "priority"] += 0.5
    out["desired_pnl"] = out["desired_exposure"] * out["unit"]
    out["leg_id"] = np.arange(len(out), dtype="int64")
    return out.sort_values(["start_ts", "entry_row", "leg_kind"]).reset_index(drop=True)


def assign_raw(legs: pd.DataFrame, max_leverage: float) -> pd.DataFrame:
    out = legs.copy()
    out["actual_exposure"] = out["desired_exposure"]
    out["capacity_policy"] = "raw_no_cap"
    return out


def assign_global_scale(legs: pd.DataFrame, max_leverage: float) -> pd.DataFrame:
    out = legs.copy()
    peak = max_interval_exposure(
        out["start_ts"].to_numpy(dtype=float),
        out["end_ts"].to_numpy(dtype=float),
        out["desired_exposure"].to_numpy(dtype=float),
    )
    scale = min(1.0, safe_div(max_leverage, peak)) if np.isfinite(peak) else 0.0
    out["actual_exposure"] = out["desired_exposure"] * scale
    out["capacity_policy"] = "global_downscale"
    return out


def assign_fifo_clip(legs: pd.DataFrame, max_leverage: float, *, priority_order: bool) -> pd.DataFrame:
    sort_cols = ["start_ts"]
    ascending = [True]
    if priority_order:
        work = legs.assign(sort_priority=-legs["priority"])
        sort_cols.extend(["sort_priority", "entry_row", "leg_kind"])
        ascending.extend([True, True, True])
    else:
        work = legs.copy()
        sort_cols.extend(["entry_row", "leg_kind"])
        ascending.extend([True, True])
    work = work.sort_values(sort_cols, ascending=ascending).copy()
    actual = np.zeros(len(work), dtype=float)
    heap: list[tuple[float, int, float]] = []
    current = 0.0
    for pos, (_, row) in enumerate(work.iterrows()):
        start = float(row["start_ts"])
        while heap and heap[0][0] <= start:
            _, _, exposure = heapq.heappop(heap)
            current -= exposure
        desired = float(row["desired_exposure"])
        avail = max(0.0, max_leverage - current)
        filled = min(desired, avail)
        if filled > 1e-12:
            heapq.heappush(heap, (float(row["end_ts"]), int(row["leg_id"]), filled))
            current += filled
        actual[pos] = filled
    work["actual_exposure"] = actual
    work["capacity_policy"] = "priority_arrival_clip" if priority_order else "online_fifo_clip"
    return work.drop(columns=[c for c in ["sort_priority"] if c in work.columns]).sort_values("leg_id")


def assign_priority_replace_proxy(legs: pd.DataFrame, max_leverage: float) -> pd.DataFrame:
    work = legs.sort_values(["start_ts", "entry_row", "leg_kind"]).copy()
    records = work.to_dict("records")
    actual: dict[int, float] = {int(r["leg_id"]): 0.0 for r in records}
    active: set[int] = set()
    by_id = {int(r["leg_id"]): r for r in records}
    heap: list[tuple[float, int]] = []
    current = 0.0
    for row in records:
        start = float(row["start_ts"])
        while heap and heap[0][0] <= start:
            _, leg_id = heapq.heappop(heap)
            if leg_id in active:
                current -= actual[leg_id]
                active.remove(leg_id)
        leg_id = int(row["leg_id"])
        desired = float(row["desired_exposure"])
        need = desired
        avail = max(0.0, max_leverage - current)
        take = min(need, avail)
        if take > 1e-12:
            actual[leg_id] += take
            current += take
            need -= take
        if need > 1e-12:
            candidates = sorted(
                [old for old in active if by_id[old]["priority"] < row["priority"] and actual[old] > 1e-12],
                key=lambda old: (by_id[old]["priority"], by_id[old]["unit"]),
            )
            for old in candidates:
                if need <= 1e-12:
                    break
                cut = min(actual[old], need)
                actual[old] -= cut
                actual[leg_id] += cut
                need -= cut
        if actual[leg_id] > 1e-12:
            active.add(leg_id)
            heapq.heappush(heap, (float(row["end_ts"]), leg_id))
    out = work.copy()
    out["actual_exposure"] = out["leg_id"].map(actual).astype(float)
    out["capacity_policy"] = "priority_replace_terminal_proxy"
    return out.sort_values("leg_id")


def summarize_assignment(
    assigned: pd.DataFrame,
    *,
    variant: pd.Series,
    max_leverage: float,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out = assigned.copy()
    out["actual_pnl"] = out["actual_exposure"] * out["unit"]
    out["desired_pnl"] = out["desired_exposure"] * out["unit"]
    out["clipped_exposure"] = out["desired_exposure"] - out["actual_exposure"]
    out["capacity_pnl_delta"] = out["desired_pnl"] - out["actual_pnl"]
    out["positive_pnl_lost"] = np.where(out["unit"] > 0, out["clipped_exposure"] * out["unit"], 0.0)
    out["negative_pnl_avoided"] = np.where(out["unit"] < 0, -out["clipped_exposure"] * out["unit"], 0.0)
    daily = out.groupby("date", sort=True).agg(
        total=("actual_pnl", "sum"),
        desired_total=("desired_pnl", "sum"),
        actual_exposure=("actual_exposure", "sum"),
        desired_exposure=("desired_exposure", "sum"),
        clipped_exposure=("clipped_exposure", "sum"),
        legs=("leg_id", "size"),
    ).reset_index()
    pnl = out["actual_pnl"].to_numpy(dtype=float)
    daily_pnl = daily["total"].to_numpy(dtype=float)
    peak = max_interval_exposure(
        out["start_ts"].to_numpy(dtype=float),
        out["end_ts"].to_numpy(dtype=float),
        out["actual_exposure"].to_numpy(dtype=float),
    )
    desired_peak = max_interval_exposure(
        out["start_ts"].to_numpy(dtype=float),
        out["end_ts"].to_numpy(dtype=float),
        out["desired_exposure"].to_numpy(dtype=float),
    )
    total = float(out["actual_pnl"].sum())
    desired_total = float(out["desired_pnl"].sum())
    row = {
        "strategy": variant["strategy"],
        "variant": variant["variant"],
        "pressure_bps": float(variant["pressure_bps"]),
        "capacity_policy": out["capacity_policy"].iloc[0],
        "gamma00_none": float(variant["gamma00_none"]),
        "gamma10_r5_only": float(variant["gamma10_r5_only"]),
        "gamma01_frames_only": float(variant["gamma01_frames_only"]),
        "gamma11_r5_frames": float(variant["gamma11_r5_frames"]),
        "legs": int(len(out)),
        "entries": int(out["entry_row"].nunique()),
        "desired_total": desired_total,
        "actual_total": total,
        "capacity_pnl_delta": desired_total - total,
        "actual_vs_global_gain": np.nan,
        "desired_exposure": float(out["desired_exposure"].sum()),
        "actual_exposure": float(out["actual_exposure"].sum()),
        "exposure_fill_rate": safe_div(float(out["actual_exposure"].sum()), float(out["desired_exposure"].sum())),
        "clipped_exposure": float(out["clipped_exposure"].sum()),
        "clipped_legs": int((out["clipped_exposure"] > 1e-12).sum()),
        "skipped_legs": int((out["actual_exposure"] <= 1e-12).sum()),
        "partial_legs": int(((out["actual_exposure"] > 1e-12) & (out["clipped_exposure"] > 1e-12)).sum()),
        "positive_pnl_lost": float(out["positive_pnl_lost"].sum()),
        "negative_pnl_avoided": float(out["negative_pnl_avoided"].sum()),
        "desired_max_concurrent": desired_peak,
        "actual_max_concurrent": peak,
        "max_leverage": max_leverage,
        "worst_day": float(daily["total"].min()) if len(daily) else np.nan,
        "best_day": float(daily["total"].max()) if len(daily) else np.nan,
        "positive_day_count": int((daily["total"] > 0).sum()),
        "days": int(len(daily)),
        "daily_cvar20": cvar(daily_pnl, 0.20),
        "max_drawdown": max_drawdown(daily_pnl),
        "leg_worst": float(pnl.min()) if len(pnl) else np.nan,
        "leg_cvar05": cvar(pnl, 0.05),
    }
    cell = out.groupby(["capacity_policy", "cell"], sort=True).agg(
        legs=("leg_id", "size"),
        desired_total=("desired_pnl", "sum"),
        actual_total=("actual_pnl", "sum"),
        desired_exposure=("desired_exposure", "sum"),
        actual_exposure=("actual_exposure", "sum"),
        clipped_exposure=("clipped_exposure", "sum"),
        clipped_legs=("clipped_exposure", lambda s: int((s > 1e-12).sum())),
        skipped_legs=("actual_exposure", lambda s: int((s <= 1e-12).sum())),
    ).reset_index()
    clipped = out[out["clipped_exposure"] > 1e-12].copy().sort_values(
        ["capacity_pnl_delta"], ascending=False
    )
    return row, daily, cell, clipped


def evaluate_variant(entries: pd.DataFrame, variant: pd.Series, max_leverage: float) -> tuple[list[dict[str, Any]], list[pd.DataFrame], list[pd.DataFrame], list[pd.DataFrame]]:
    legs = build_legs(entries, variant)
    assignments = [
        assign_raw(legs, max_leverage),
        assign_global_scale(legs, max_leverage),
        assign_fifo_clip(legs, max_leverage, priority_order=False),
        assign_fifo_clip(legs, max_leverage, priority_order=True),
        assign_priority_replace_proxy(legs, max_leverage),
    ]
    rows = []
    daily_rows = []
    cell_rows = []
    clipped_rows = []
    global_total = np.nan
    for assigned in assignments:
        row, daily, cell, clipped = summarize_assignment(assigned, variant=variant, max_leverage=max_leverage)
        if row["capacity_policy"] == "global_downscale":
            global_total = row["actual_total"]
        rows.append(row)
        for frame in [daily, cell, clipped]:
            frame["strategy"] = variant["strategy"]
            frame["variant"] = variant["variant"]
            frame["pressure_bps"] = float(variant["pressure_bps"])
            frame["capacity_policy"] = row["capacity_policy"]
        daily_rows.append(daily)
        cell_rows.append(cell)
        clipped_rows.append(clipped.head(50))
    for row in rows:
        row["actual_vs_global_gain"] = row["actual_total"] - global_total if np.isfinite(global_total) else np.nan
    return rows, daily_rows, cell_rows, clipped_rows


def write_report(
    paths: Paths,
    *,
    summary: pd.DataFrame,
    cell: pd.DataFrame,
    clipped: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    c0 = summary[summary["pressure_bps"].eq(0)].copy()
    q70_main = c0[
        c0["strategy"].eq("manager_plus_q70_watcher")
        & c0["variant"].eq(MAIN_LOW_CONCURRENCY_VARIANT)
    ].copy()
    policy_order = {
        "raw_no_cap": 0,
        "global_downscale": 1,
        "online_fifo_clip": 2,
        "priority_arrival_clip": 3,
        "priority_replace_terminal_proxy": 4,
    }
    q70_main["_policy_order"] = q70_main["capacity_policy"].map(policy_order).fillna(99)
    q70_main = q70_main.sort_values("_policy_order").drop(columns=["_policy_order"])
    implementable_policies = ["global_downscale", "online_fifo_clip", "priority_arrival_clip"]
    leaders = c0[c0["capacity_policy"].isin(implementable_policies)].sort_values(
        "actual_total", ascending=False
    ).head(20)
    proxy_leaders = c0[c0["capacity_policy"].eq("priority_replace_terminal_proxy")].sort_values(
        "actual_total", ascending=False
    ).head(10)
    pressure_main = summary[
        summary["strategy"].eq("manager_plus_q70_watcher")
        & summary["variant"].eq(MAIN_LOW_CONCURRENCY_VARIANT)
        & summary["capacity_policy"].isin(implementable_policies)
    ].sort_values(["pressure_bps", "actual_total"], ascending=[True, False])
    pressure_leaders = (
        summary[summary["capacity_policy"].isin(implementable_policies)]
        .sort_values(["pressure_bps", "actual_total"], ascending=[True, False])
        .groupby("pressure_bps", as_index=False)
        .head(5)
    )
    raw_vs_capacity = summary[
        summary["variant"].isin(
            [
                MAIN_LOW_CONCURRENCY_VARIANT,
                HIGH_GAMMA_VARIANT,
                ANCHOR_VARIANT,
            ]
        )
        & summary["strategy"].eq("manager_plus_q70_watcher")
        & summary["pressure_bps"].eq(0)
    ].sort_values(["variant", "capacity_policy"])
    lines = [
        "# CCUSDT V1 TFI Capacity Manager",
        "",
        f"Status: `{args.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Scope",
        "",
        "This pass fixes the watcher-aware four-cell signal model and tests",
        f"capacity allocation under a `{float(args.max_leverage):g}x` total exposure cap.",
        "",
        "```text",
        "raw_no_cap: target exposures without leverage cap",
        "global_downscale: multiply every leg by L / max_concurrency",
        "online_fifo_clip: keep old legs, new legs take remaining capacity",
        "priority_arrival_clip: same as FIFO, but same-timestamp legs sort by cell priority",
        "priority_replace_terminal_proxy: diagnostic only; replaces lower-priority open capacity using terminal PnL proxy",
        "```",
        "",
        "Mathematically, this is a capacity-allocation test, not another entry",
        "filter. Target leg exposure is `w_i = b_i gamma_cell`; the executable",
        "constraint is an overlap constraint:",
        "",
        "$$",
        "\\sum_{i:t_i\\le t<u_i}\\widetilde w_i\\le L_{max}=3.",
        "$$",
        "",
        "So `global_downscale` is only a conservative lower bound:",
        "",
        "$$",
        "s=\\min\\left(1,{3\\over \\max_t\\sum_{i:t_i\\le t<u_i}w_i}\\right),",
        "\\qquad \\widetilde w_i=sw_i.",
        "$$",
        "",
        "The online clip keeps full size except when the current open book is",
        "actually crowded:",
        "",
        "$$",
        "\\widetilde w_i=\\min\\left(w_i,3-L(t_i^-)\\right).",
        "$$",
        "",
        "## Main Read",
        "",
        "For the current 3x q70 Pareto leader, global scaling is conservative:",
        "",
        markdown_table(
            q70_main,
            [
                "capacity_policy",
                "desired_total",
                "actual_total",
                "actual_vs_global_gain",
                "desired_max_concurrent",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
                "positive_pnl_lost",
                "negative_pnl_avoided",
                "worst_day",
                "leg_worst",
            ],
            max_rows=10,
        ),
        "",
        "## Pressure Sanity",
        "",
        "The same low-concurrency q70 point is almost unaffected by the 3x cap,",
        "but pressure still matters because every held leg pays the stress term.",
        "",
        markdown_table(
            pressure_main,
            [
                "pressure_bps",
                "capacity_policy",
                "desired_total",
                "actual_total",
                "actual_vs_global_gain",
                "actual_max_concurrent",
                "worst_day",
                "leg_worst",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=20,
        ),
        "",
        "Top implementable rows by pressure:",
        "",
        markdown_table(
            pressure_leaders,
            [
                "pressure_bps",
                "strategy",
                "variant",
                "capacity_policy",
                "actual_total",
                "desired_total",
                "actual_vs_global_gain",
                "actual_max_concurrent",
                "worst_day",
                "leg_worst",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=20,
        ),
        "",
        "## C0 Implementable Capacity Leaders",
        "",
        "These rows exclude `raw_no_cap` and the replacement proxy. They are the",
        "rules that can be read as direct capacity-management diagnostics.",
        "",
        markdown_table(
            leaders,
            [
                "strategy",
                "variant",
                "capacity_policy",
                "actual_total",
                "desired_total",
                "actual_vs_global_gain",
                "actual_max_concurrent",
                "worst_day",
                "leg_worst",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=20,
        ),
        "",
        "## C0 Replacement Proxy Leaders",
        "",
        "`priority_replace_terminal_proxy` is separated because it reallocates",
        "open capacity using terminal-PnL information. It is useful for measuring",
        "possible capacity loss, but it is not a live rule.",
        "",
        markdown_table(
            proxy_leaders,
            [
                "strategy",
                "variant",
                "capacity_policy",
                "actual_total",
                "desired_total",
                "actual_vs_global_gain",
                "actual_max_concurrent",
                "worst_day",
                "leg_worst",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=10,
        ),
        "",
        "## Raw Max Versus Capacity",
        "",
        markdown_table(
            raw_vs_capacity,
            [
                "variant",
                "capacity_policy",
                "desired_total",
                "actual_total",
                "actual_vs_global_gain",
                "desired_max_concurrent",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
                "worst_day",
                "leg_worst",
            ],
            max_rows=30,
        ),
        "",
        "## Cell Capacity Loss",
        "",
        markdown_table(
            cell[
                cell["variant"].eq(MAIN_LOW_CONCURRENCY_VARIANT)
                & cell["strategy"].eq("manager_plus_q70_watcher")
                & cell["pressure_bps"].eq(0)
            ],
            [
                "capacity_policy",
                "cell",
                "desired_total",
                "actual_total",
                "desired_exposure",
                "actual_exposure",
                "clipped_exposure",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=30,
        ),
        "",
        "## Largest Clipped Legs",
        "",
        markdown_table(
            clipped[
                clipped["variant"].eq(MAIN_LOW_CONCURRENCY_VARIANT)
                & clipped["strategy"].eq("manager_plus_q70_watcher")
                & clipped["pressure_bps"].eq(0)
                & clipped["capacity_policy"].eq("online_fifo_clip")
            ].sort_values("capacity_pnl_delta", ascending=False),
            [
                "date",
                "entry_row",
                "cell",
                "leg_kind",
                "desired_exposure",
                "actual_exposure",
                "unit",
                "capacity_pnl_delta",
            ],
            max_rows=20,
        ),
        "",
        "## Interpretation",
        "",
        "- `global_downscale` is a conservative lower bound because one peak interval",
        "  scales down every leg in history.",
        "- `online_fifo_clip` is closer to implementable capacity management: only",
        "  crowded arrivals are clipped.",
        "- `priority_replace_terminal_proxy` is not an execution rule yet. It is a",
        "  diagnostic upper/proxy because replacing an open leg needs path PnL at",
        "  the replacement timestamp.",
        "",
        "## Outputs",
        "",
        f"- `{paths.summary_csv}`",
        f"- `{paths.cell_csv}`",
        f"- `{paths.daily_csv}`",
        f"- `{paths.clipped_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        "python scripts/ccusdt_v1_tfi_capacity_manager.py",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_path(args.date_dir),
        doc_dir=resolve_path(args.doc_dir),
        run_tag=args.run_tag,
        source_run_tag=args.source_run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    entries = pd.read_csv(paths.unit_entries_csv)
    variants = pd.read_csv(paths.variants_csv)
    selected = select_variants(variants, int(args.top_n))

    rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    cell_rows: list[pd.DataFrame] = []
    clipped_rows: list[pd.DataFrame] = []
    for _, variant in selected.iterrows():
        r, d, c, clipped = evaluate_variant(entries, variant, float(args.max_leverage))
        rows.extend(r)
        daily_rows.extend(d)
        cell_rows.extend(c)
        clipped_rows.extend(clipped)

    summary = pd.DataFrame(rows).sort_values(["pressure_bps", "actual_total"], ascending=[True, False])
    daily = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    cell = pd.concat(cell_rows, ignore_index=True) if cell_rows else pd.DataFrame()
    clipped = pd.concat(clipped_rows, ignore_index=True) if clipped_rows else pd.DataFrame()

    summary.to_csv(paths.summary_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    cell.to_csv(paths.cell_csv, index=False)
    clipped.to_csv(paths.clipped_csv, index=False)
    out = {
        "run_tag": args.run_tag,
        "guardrail": GUARDRAIL,
        "source_run_tag": args.source_run_tag,
        "max_leverage": float(args.max_leverage),
        "selected_variants": int(len(selected)),
        "summary_rows": int(len(summary)),
        "outputs": {
            "summary_csv": str(paths.summary_csv),
            "daily_csv": str(paths.daily_csv),
            "cell_csv": str(paths.cell_csv),
            "clipped_csv": str(paths.clipped_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(paths, summary=summary, cell=cell, clipped=clipped, args=args)
    implementable = summary[summary["capacity_policy"].isin(
        ["global_downscale", "online_fifo_clip", "priority_arrival_clip"]
    )].copy()
    main_q70 = implementable[
        implementable["strategy"].eq("manager_plus_q70_watcher")
        & implementable["variant"].eq(MAIN_LOW_CONCURRENCY_VARIANT)
        & implementable["pressure_bps"].eq(0)
    ].sort_values("actual_total", ascending=False).iloc[0]
    print(f"wrote {paths.report_md}")
    print(
        "main_q70_capacity_best "
        f"{main_q70['capacity_policy']} actual={main_q70['actual_total']:.4f} "
        f"desired={main_q70['desired_total']:.4f} max_conc={main_q70['actual_max_concurrent']:.4f}"
    )
    top = implementable[implementable["pressure_bps"].eq(0)].sort_values(
        "actual_total", ascending=False
    ).iloc[0]
    print(
        "top_c0_implementable "
        f"{top['strategy']} {top['variant']} {top['capacity_policy']} "
        f"actual={top['actual_total']:.4f}"
    )


if __name__ == "__main__":
    main()

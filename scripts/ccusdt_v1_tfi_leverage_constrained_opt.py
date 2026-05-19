#!/usr/bin/env python
"""Leverage-constrained strategy optimization for CCUSDT V1 TFI.

This pass treats the 3x cap as part of the strategy, not as a final global
scale. The main candidate keeps the current q70 core and adds 01 as an
idle-capacity sleeve:

    core: 00/10/11 use fixed gamma
    sleeve: 01 is accepted only when spare leverage is available

It is research-only and does not produce execution recommendations.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ccusdt_v1_tfi_capacity_manager import (
    assign_fifo_clip,
    build_legs,
    max_interval_exposure,
    summarize_assignment,
)


RUN_TAG = "20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1"
GUARDRAIL = "research_only_leverage_constrained_strategy_no_execution_recommendation"
HIST_UNIT_ENTRIES = (
    "ccusdt_v1_tfi_watcher_pareto_unit_entries_"
    "20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.csv"
)
OOS_UNIT_ENTRIES = (
    "ccusdt_v1_tfi_current_oos_unit_entries_"
    "20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.csv"
)
MAX_LEVERAGE = 3.0
PRESSURES = [0.0, 1.0, 2.0]

CORE_Q70 = {
    "00_none": 1.25,
    "10_r5_only": 0.75,
    "01_frames_only": 0.0,
    "11_r5_frames": 0.75,
}


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    run_tag: str
    hist_unit_entries_name: str
    oos_unit_entries_name: str

    @property
    def hist_unit_entries_csv(self) -> Path:
        return self.date_dir / self.hist_unit_entries_name

    @property
    def oos_unit_entries_csv(self) -> Path:
        return self.date_dir / self.oos_unit_entries_name

    @property
    def summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_leverage_constrained_summary_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_leverage_constrained_daily_{self.run_tag}.csv"

    @property
    def cell_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_leverage_constrained_cell_{self.run_tag}.csv"

    @property
    def clipped_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_leverage_constrained_clipped_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_leverage_constrained_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-leverage-constrained-opt-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--hist-unit-entries", default=HIST_UNIT_ENTRIES)
    parser.add_argument("--oos-unit-entries", default=OOS_UNIT_ENTRIES)
    parser.add_argument("--max-leverage", type=float, default=MAX_LEVERAGE)
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


def variant_series(name: str, gammas: dict[str, float], pressure: float) -> pd.Series:
    return pd.Series(
        {
            "strategy": "manager_plus_q70_watcher",
            "variant": name,
            "pressure_bps": pressure,
            "gamma00_none": float(gammas.get("00_none", 0.0)),
            "gamma10_r5_only": float(gammas.get("10_r5_only", 0.0)),
            "gamma01_frames_only": float(gammas.get("01_frames_only", 0.0)),
            "gamma11_r5_frames": float(gammas.get("11_r5_frames", 0.0)),
        }
    )


def candidate_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        {
            "candidate": "clean_core_only",
            "family": "core_only",
            "allocator": "core_idle01",
            "reserve": 0.0,
            "gammas": CORE_Q70.copy(),
            "note": "Current cleaner q70 core; 01 is not allocated.",
        }
    ]
    for gamma01 in [0.25, 0.5, 0.75, 1.0]:
        for reserve in [0.0, 0.25, 0.5]:
            gammas = CORE_Q70 | {"01_frames_only": gamma01}
            specs.append(
                {
                    "candidate": f"idle01_g{gamma01:g}_r{reserve:g}",
                    "family": "core_plus_idle01",
                    "allocator": "core_idle01",
                    "reserve": reserve,
                    "gammas": gammas,
                    "note": "01 accepted only from spare leverage after the core.",
                }
            )
    for gamma01 in [0.25, 0.5, 0.75, 1.0]:
        gammas = CORE_Q70 | {"01_frames_only": gamma01}
        specs.append(
            {
                "candidate": f"flat01_fifo_g{gamma01:g}",
                "family": "flat_gamma_fifo",
                "allocator": "online_fifo",
                "reserve": 0.0,
                "gammas": gammas,
                "note": "All cells enter the same FIFO allocator; included as a control.",
            }
        )
    specs.extend(
        [
            {
                "candidate": "anchor_q70_old_shape",
                "family": "reference",
                "allocator": "online_fifo",
                "reserve": 0.0,
                "gammas": {
                    "00_none": 1.0,
                    "10_r5_only": 0.75,
                    "01_frames_only": 0.25,
                    "11_r5_frames": 4.0,
                },
                "note": "Old high-11 anchor under the online cap.",
            },
            {
                "candidate": "high_gamma_capacity",
                "family": "reference",
                "allocator": "online_fifo",
                "reserve": 0.0,
                "gammas": {
                    "00_none": 1.25,
                    "10_r5_only": 2.0,
                    "01_frames_only": 1.0,
                    "11_r5_frames": 5.0,
                },
                "note": "High-gamma capacity reference; not promoted.",
            },
            {
                "candidate": "pressure_c2_shape_fifo",
                "family": "reference",
                "allocator": "online_fifo",
                "reserve": 0.0,
                "gammas": {
                    "00_none": 0.0,
                    "10_r5_only": 1.25,
                    "01_frames_only": 0.75,
                    "11_r5_frames": 1.5,
                },
                "note": "Earlier C=2 scaled-shape reference.",
            },
        ]
    )
    return specs


def assign_core_idle01(legs: pd.DataFrame, max_leverage: float, reserve: float) -> pd.DataFrame:
    """Online allocator where 01 uses only spare leverage after core demand.

    The rule is intentionally modest: it does not use terminal PnL and does not
    replace already-open 01. It only changes the admission priority at entry.
    """

    if legs.empty:
        out = legs.copy()
        out["actual_exposure"] = []
        out["capacity_policy"] = f"core_idle01_reserve_{reserve:g}"
        return out
    work = legs.copy()
    work["is_sleeve"] = work["cell"].eq("01_frames_only")
    work["_sort_is_sleeve"] = work["is_sleeve"].astype(int)
    work = work.sort_values(["start_ts", "_sort_is_sleeve", "entry_row", "leg_kind"]).copy()
    actual = np.zeros(len(work), dtype=float)
    heap: list[tuple[float, int, float]] = []
    current = 0.0
    for pos, (_, row) in enumerate(work.iterrows()):
        start = float(row["start_ts"])
        while heap and heap[0][0] <= start:
            _, _, exposure = heapq.heappop(heap)
            current -= exposure
        desired = float(row["desired_exposure"])
        sleeve_reserve = reserve if bool(row["is_sleeve"]) else 0.0
        avail = max(0.0, max_leverage - current - sleeve_reserve)
        filled = min(desired, avail)
        if filled > 1e-12:
            heapq.heappush(heap, (float(row["end_ts"]), int(row["leg_id"]), filled))
            current += filled
        actual[pos] = filled
    work["actual_exposure"] = actual
    work["capacity_policy"] = f"core_idle01_reserve_{reserve:g}"
    return work.drop(columns=["_sort_is_sleeve"]).sort_values("leg_id").reset_index(drop=True)


def assign_policy(legs: pd.DataFrame, spec: dict[str, Any], max_leverage: float) -> pd.DataFrame:
    allocator = str(spec["allocator"])
    if allocator == "online_fifo":
        return assign_fifo_clip(legs, max_leverage, priority_order=False)
    if allocator == "core_idle01":
        return assign_core_idle01(legs, max_leverage, reserve=float(spec["reserve"]))
    raise ValueError(f"unsupported allocator={allocator}")


def exact_simple_bp_units(assigned: pd.DataFrame) -> float:
    exposure = pd.to_numeric(assigned["actual_exposure"], errors="coerce").to_numpy(dtype=float)
    unit = pd.to_numeric(assigned["unit"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(exposure) & np.isfinite(unit)
    return float(np.sum(exposure[ok] * (np.exp(unit[ok] / 10_000.0) - 1.0) * 10_000.0))


def summarize_true_peak(assigned: pd.DataFrame) -> float:
    return max_interval_exposure(
        pd.to_numeric(assigned["start_ts"], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(assigned["end_ts"], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(assigned["actual_exposure"], errors="coerce").to_numpy(dtype=float),
    )


def evaluate_dataset(
    entries: pd.DataFrame,
    *,
    dataset: str,
    max_leverage: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    cell_rows: list[pd.DataFrame] = []
    clipped_rows: list[pd.DataFrame] = []
    for spec in candidate_specs():
        for pressure in PRESSURES:
            variant = variant_series(str(spec["candidate"]), spec["gammas"], pressure)
            legs = build_legs(entries, variant)
            assigned = assign_policy(legs, spec, max_leverage)
            row, daily, cell, clipped = summarize_assignment(
                assigned,
                variant=variant,
                max_leverage=max_leverage,
            )
            row.update(
                {
                    "dataset": dataset,
                    "candidate": spec["candidate"],
                    "family": spec["family"],
                    "allocator": spec["allocator"],
                    "reserve": float(spec["reserve"]),
                    "note": spec["note"],
                    "actual_max_concurrent_check": summarize_true_peak(assigned),
                    "exact_simple_bp_units": exact_simple_bp_units(assigned),
                    "approx_account_log_return": row["actual_total"] / 10_000.0,
                    "approx_account_simple_return": math.exp(row["actual_total"] / 10_000.0) - 1.0,
                    "positive_days": int((daily["total"] > 0).sum()) if not daily.empty else 0,
                    "days": int(len(daily)),
                }
            )
            rows.append(row)
            for frame in [daily, cell, clipped]:
                frame["dataset"] = dataset
                frame["candidate"] = spec["candidate"]
                frame["family"] = spec["family"]
                frame["allocator"] = spec["allocator"]
                frame["reserve"] = float(spec["reserve"])
                frame["pressure_bps"] = pressure
                frame["capacity_policy"] = row["capacity_policy"]
            daily_rows.append(daily)
            cell_rows.append(cell)
            clipped_rows.append(clipped.head(25))
    return (
        pd.DataFrame(rows),
        pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame(),
        pd.concat(cell_rows, ignore_index=True) if cell_rows else pd.DataFrame(),
        pd.concat(clipped_rows, ignore_index=True) if clipped_rows else pd.DataFrame(),
    )


def add_baseline_deltas(summary: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    out["delta_vs_core"] = np.nan
    out["delta_simple_vs_core"] = np.nan
    key_cols = ["dataset", "pressure_bps"]
    core = out[out["candidate"].eq("clean_core_only")].set_index(key_cols)
    for idx, row in out.iterrows():
        key = (row["dataset"], row["pressure_bps"])
        if key not in core.index:
            continue
        base = core.loc[key]
        out.at[idx, "delta_vs_core"] = float(row["actual_total"] - base["actual_total"])
        out.at[idx, "delta_simple_vs_core"] = float(
            row["exact_simple_bp_units"] - base["exact_simple_bp_units"]
        )
    return out


def select_views(summary: pd.DataFrame) -> dict[str, pd.DataFrame]:
    hist_c0 = summary[summary["dataset"].eq("historical") & summary["pressure_bps"].eq(0.0)].copy()
    oos_c0 = summary[summary["dataset"].eq("oos_2026_05_18") & summary["pressure_bps"].eq(0.0)].copy()
    hist_c1 = summary[summary["dataset"].eq("historical") & summary["pressure_bps"].eq(1.0)].copy()
    hist_c2 = summary[summary["dataset"].eq("historical") & summary["pressure_bps"].eq(2.0)].copy()
    sleeve_c0 = hist_c0[hist_c0["family"].eq("core_plus_idle01")].copy()
    conservative_sleeve = sleeve_c0[
        sleeve_c0["worst_day"].ge(0)
        & sleeve_c0["leg_worst"].ge(-100)
        & sleeve_c0["positive_days"].eq(sleeve_c0["days"])
    ].sort_values(["actual_total", "delta_vs_core"], ascending=False)
    return {
        "hist_c0": hist_c0.sort_values("actual_total", ascending=False),
        "oos_c0": oos_c0.sort_values("actual_total", ascending=False),
        "hist_c1": hist_c1.sort_values("actual_total", ascending=False),
        "hist_c2": hist_c2.sort_values("actual_total", ascending=False),
        "sleeve_c0": sleeve_c0.sort_values("actual_total", ascending=False),
        "conservative_sleeve": conservative_sleeve,
    }


def core_displacement(cell: pd.DataFrame, *, dataset: str, pressure: float) -> pd.DataFrame:
    scope = cell[cell["dataset"].eq(dataset) & cell["pressure_bps"].eq(pressure)].copy()
    core_cells = ["00_none", "10_r5_only", "11_r5_frames"]
    base = scope[scope["candidate"].eq("clean_core_only")]
    if base.empty:
        return pd.DataFrame()
    base_core = float(base[base["cell"].isin(core_cells)]["actual_exposure"].sum())
    rows: list[dict[str, Any]] = []
    for candidate in ["idle01_g0.25_r0", "idle01_g0.5_r0", "idle01_g0.75_r0", "idle01_g1_r0"]:
        cand = scope[scope["candidate"].eq(candidate)]
        if cand.empty:
            continue
        core_exp = float(cand[cand["cell"].isin(core_cells)]["actual_exposure"].sum())
        sleeve_exp = float(cand[cand["cell"].eq("01_frames_only")]["actual_exposure"].sum())
        core_delta = core_exp - base_core
        rows.append(
            {
                "dataset": dataset,
                "pressure_bps": pressure,
                "candidate": candidate,
                "core_exposure_base": base_core,
                "core_exposure_after": core_exp,
                "core_exposure_delta": core_delta,
                "sleeve01_actual_exposure": sleeve_exp,
                "core_displacement_ratio": (-core_delta / sleeve_exp) if sleeve_exp > 1e-12 else np.nan,
            }
        )
    return pd.DataFrame(rows)


def write_report(
    paths: Paths,
    *,
    summary: pd.DataFrame,
    cell: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    views = select_views(summary)
    core_rows = summary[summary["candidate"].eq("clean_core_only")].sort_values(["dataset", "pressure_bps"])
    sleeve_leaders = views["sleeve_c0"].head(12)
    conservative = views["conservative_sleeve"].head(10)
    oos_key = views["oos_c0"][
        views["oos_c0"]["candidate"].isin(
            ["clean_core_only", "idle01_g0.25_r0", "idle01_g0.5_r0", "idle01_g0.75_r0", "idle01_g1_r0"]
        )
    ].sort_values("candidate")
    hist_cell_c0 = cell[
        cell["dataset"].eq("historical")
        & cell["pressure_bps"].eq(0.0)
        & cell["candidate"].isin(["clean_core_only", "idle01_g0.25_r0", "idle01_g0.5_r0"])
    ].sort_values(["candidate", "cell"])
    pressure_refs = summary[
        summary["dataset"].eq("historical")
        & summary["candidate"].isin(["clean_core_only", "pressure_c2_shape_fifo", "idle01_g0.5_r0"])
    ].sort_values(["pressure_bps", "candidate"])
    oos_pressure = summary[
        summary["dataset"].eq("oos_2026_05_18")
        & summary["candidate"].isin(["clean_core_only", "idle01_g0.5_r0", "idle01_g1_r0"])
    ].sort_values(["pressure_bps", "candidate"])
    displacement = pd.concat(
        [
            core_displacement(cell, dataset="historical", pressure=0.0),
            core_displacement(cell, dataset="oos_2026_05_18", pressure=0.0),
        ],
        ignore_index=True,
    )
    lines = [
        "# CCUSDT V1 TFI Leverage-Constrained Optimization",
        "",
        f"Status: `{args.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Question",
        "",
        "This pass asks whether `01_frames_only` was removed because it lacks edge,",
        "or because the old cell-level gamma model let crowded intervals punish all",
        "`01` entries globally.",
        "",
        "The leverage constraint is modeled directly:",
        "",
        "$$",
        "L(t)=\\sum_{i:t_i\\le t<u_i}\\widetilde w_i\\le K,\\qquad K=3.",
        "$$",
        "",
        "The candidate structure is:",
        "",
        "$$",
        "w_i^{core}=b_i\\gamma_{c_i}^{core},\\qquad c_i\\in\\{00,10,11\\},",
        "$$",
        "",
        "$$",
        "w_i^{01}=\\mathbf 1_{\\{c_i=01\\}}\\min\\left(",
        "b_i\\gamma_{01},\\ [K-L(t_i^-)-m]_+",
        "\\right).",
        "$$",
        "",
        "`m` is an idle-capacity reserve. This is deliberately modest: it does not",
        "use terminal PnL, and it does not replace already-open 01 exposure.",
        "",
        "## Core Baseline",
        "",
        markdown_table(
            core_rows,
            [
                "dataset",
                "pressure_bps",
                "actual_total",
                "exact_simple_bp_units",
                "approx_account_simple_return",
                "worst_day",
                "positive_days",
                "days",
                "leg_worst",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
            ],
        ),
        "",
        "## Historical C0 Idle-01 Sleeve",
        "",
        markdown_table(
            sleeve_leaders,
            [
                "candidate",
                "gamma01_frames_only",
                "reserve",
                "actual_total",
                "delta_vs_core",
                "worst_day",
                "positive_days",
                "days",
                "leg_worst",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=12,
        ),
        "",
        "Conservative sleeve rows requiring non-negative worst day, all positive",
        "days, and single-leg worst better than `-100`:",
        "",
        markdown_table(
            conservative,
            [
                "candidate",
                "actual_total",
                "delta_vs_core",
                "worst_day",
                "leg_worst",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=10,
        ),
        "",
        "## OOS 2026-05-18 C0 Check",
        "",
        markdown_table(
            oos_key,
            [
                "candidate",
                "gamma01_frames_only",
                "reserve",
                "actual_total",
                "delta_vs_core",
                "exact_simple_bp_units",
                "approx_account_simple_return",
                "leg_worst",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=20,
        ),
        "",
        "## Core Displacement",
        "",
        "This asks whether the recovered `01` PnL mainly consumes idle leverage or",
        "pushes out core exposure.",
        "",
        markdown_table(
            displacement,
            [
                "dataset",
                "candidate",
                "core_exposure_base",
                "core_exposure_after",
                "core_exposure_delta",
                "sleeve01_actual_exposure",
                "core_displacement_ratio",
            ],
            max_rows=12,
        ),
        "",
        "## Pressure References",
        "",
        markdown_table(
            pressure_refs,
            [
                "candidate",
                "pressure_bps",
                "actual_total",
                "delta_vs_core",
                "worst_day",
                "leg_worst",
                "positive_days",
                "days",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=30,
        ),
        "",
        "OOS 2026-05-18 pressure check:",
        "",
        markdown_table(
            oos_pressure,
            [
                "candidate",
                "pressure_bps",
                "actual_total",
                "delta_vs_core",
                "exact_simple_bp_units",
                "approx_account_simple_return",
                "leg_worst",
                "clipped_legs",
                "skipped_legs",
            ],
            max_rows=20,
        ),
        "",
        "## Cell Contribution Snapshot",
        "",
        markdown_table(
            hist_cell_c0,
            [
                "candidate",
                "cell",
                "actual_total",
                "actual_exposure",
                "clipped_exposure",
                "positive_pnl_lost",
                "negative_pnl_avoided",
            ],
            max_rows=30,
        ),
        "",
        "## Interpretation",
        "",
        "- `01` is not a dead cell; this script only changes whether it receives idle capacity.",
        "- `gamma01=0` is a coarse global deletion; the sleeve version asks whether spare leverage can recover part of it.",
        "- `core_idle01` is implementable as an admission rule, but it is still not a full margin-account or fill simulator.",
        "- C=0 is the zero venue-fee baseline; C=1/C=2 remain pressure reserves.",
        "",
        "## Outputs",
        "",
        f"- `{paths.summary_csv}`",
        f"- `{paths.daily_csv}`",
        f"- `{paths.cell_csv}`",
        f"- `{paths.clipped_csv}`",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_path(args.date_dir),
        doc_dir=resolve_path(args.doc_dir),
        run_tag=args.run_tag,
        hist_unit_entries_name=args.hist_unit_entries,
        oos_unit_entries_name=args.oos_unit_entries,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    hist = pd.read_csv(paths.hist_unit_entries_csv)
    oos = pd.read_csv(paths.oos_unit_entries_csv)
    hist["date"] = hist["date"].astype(str)
    oos["date"] = oos["date"].astype(str)

    hist_summary, hist_daily, hist_cell, hist_clipped = evaluate_dataset(
        hist,
        dataset="historical",
        max_leverage=float(args.max_leverage),
    )
    oos_summary, oos_daily, oos_cell, oos_clipped = evaluate_dataset(
        oos,
        dataset="oos_2026_05_18",
        max_leverage=float(args.max_leverage),
    )
    summary = add_baseline_deltas(pd.concat([hist_summary, oos_summary], ignore_index=True))
    daily = pd.concat([hist_daily, oos_daily], ignore_index=True)
    cell = pd.concat([hist_cell, oos_cell], ignore_index=True)
    clipped = pd.concat([hist_clipped, oos_clipped], ignore_index=True)

    summary = summary.sort_values(
        ["dataset", "pressure_bps", "family", "actual_total"],
        ascending=[True, True, True, False],
    ).reset_index(drop=True)
    summary.to_csv(paths.summary_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    cell.to_csv(paths.cell_csv, index=False)
    clipped.to_csv(paths.clipped_csv, index=False)
    payload = {
        "run_tag": args.run_tag,
        "guardrail": GUARDRAIL,
        "max_leverage": float(args.max_leverage),
        "historical_entries": int(len(hist)),
        "oos_entries": int(len(oos)),
        "candidate_count": int(len(candidate_specs())),
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
    paths.summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(paths, summary=summary, cell=cell, args=args)

    hist_c0 = summary[summary["dataset"].eq("historical") & summary["pressure_bps"].eq(0.0)]
    sleeve = hist_c0[hist_c0["family"].eq("core_plus_idle01")].sort_values("actual_total", ascending=False)
    core = hist_c0[hist_c0["candidate"].eq("clean_core_only")].iloc[0]
    top = sleeve.iloc[0]
    oos_top = summary[
        summary["dataset"].eq("oos_2026_05_18")
        & summary["pressure_bps"].eq(0.0)
        & summary["candidate"].eq(top["candidate"])
    ].iloc[0]
    print(
        "[ccusdt_leverage_opt] "
        f"core_hist={core['actual_total']:.4f} "
        f"top_sleeve={top['candidate']} hist={top['actual_total']:.4f} "
        f"delta={top['delta_vs_core']:.4f} oos={oos_top['actual_total']:.4f} "
        f"report={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()

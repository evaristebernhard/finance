#!/usr/bin/env python
"""Watcher-aware Pareto optimization for CCUSDT V1 TFI.

This pass keeps the rule family small:

    entry universe: full four-cell pretrade scored entries
    exit: pm_11_drawdown_h4_peakguard where rebuilt, fixed60 fallback otherwise
    optional post-exit watcher: impulse_only or q70 absorption watcher where rebuilt

The optimizer only changes transparent cell sizes. It does not add new factors.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1"
GUARDRAIL = "research_only_watcher_aware_pareto_no_execution_recommendation"
PRIMARY_MANAGER = "pm_11_drawdown_h4_peakguard"
MAIN_WATCHER = "watcher_q70_absorb_reclaim2"
US_PER_SECOND = 1_000_000.0
EXCHANGE_MAX_LEVERAGE = 3.0

MANAGER_EVENTS = "ccusdt_v1_tfi_small_path_manager_events_20260519_ccusdt_v1_tfi_small_path_manager_v1.csv"
WATCHER_EVENTS = "ccusdt_v1_tfi_post_exit_watcher_events_20260519_ccusdt_v1_tfi_post_exit_watcher_v1.csv"
SCORED_ENTRIES = "ccusdt_v1_tfi_pretrade_scored_entries_20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv"

FULL_ANCHOR_GAMMA = {
    "00_none": 1.0,
    "10_r5_only": 0.75,
    "01_frames_only": 0.25,
    "11_r5_frames": 4.0,
}
ANCHOR_VARIANT = "anchor_full_1_0p75_0p25_4"
ANCHOR_TUPLE = (
    FULL_ANCHOR_GAMMA["00_none"],
    FULL_ANCHOR_GAMMA["10_r5_only"],
    FULL_ANCHOR_GAMMA["01_frames_only"],
    FULL_ANCHOR_GAMMA["11_r5_frames"],
)

GAMMA00_GRID = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25]
GAMMA10_GRID = [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
GAMMA01_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]
GAMMA11_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
PRESSURES = [0.0, 1.0, 2.0]
MIN_TRAIN_DAYS = 5
CELL_ORDER = ["00_none", "10_r5_only", "01_frames_only", "11_r5_frames"]
CELL_TO_IDX = {cell: idx for idx, cell in enumerate(CELL_ORDER)}


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    run_tag: str
    manager_events_name: str
    watcher_events_name: str
    scored_entries_name: str

    @property
    def manager_events_csv(self) -> Path:
        return self.date_dir / self.manager_events_name

    @property
    def watcher_events_csv(self) -> Path:
        return self.date_dir / self.watcher_events_name

    @property
    def scored_entries_csv(self) -> Path:
        return self.date_dir / self.scored_entries_name

    @property
    def unit_entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_unit_entries_{self.run_tag}.csv"

    @property
    def variants_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_variants_{self.run_tag}.csv"

    @property
    def pareto_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_frontier_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_daily_{self.run_tag}.csv"

    @property
    def walkforward_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_walkforward_{self.run_tag}.csv"

    @property
    def policy_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_policy_summary_{self.run_tag}.csv"

    @property
    def leverage_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_leverage_{self.run_tag}.csv"

    @property
    def cell_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_cell_summary_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_watcher_pareto_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-watcher-pareto-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--manager-events", default=MANAGER_EVENTS)
    parser.add_argument("--watcher-events", default=WATCHER_EVENTS)
    parser.add_argument("--scored-entries", default=SCORED_ENTRIES)
    parser.add_argument("--manager-policy", default=PRIMARY_MANAGER)
    parser.add_argument("--main-watcher", default=MAIN_WATCHER)
    parser.add_argument("--max-leverage", type=float, default=EXCHANGE_MAX_LEVERAGE)
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


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > 1e-12 else np.nan


def cvar(values: np.ndarray | pd.Series, q: float = 0.10) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = np.quantile(arr, q)
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def cvar_np(values: np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    k = max(1, int(np.ceil(q * len(arr))))
    tail = np.partition(arr, k - 1)[:k]
    return float(tail.mean())


def max_drawdown(values: np.ndarray | pd.Series) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    curve = np.cumsum(arr)
    peak = np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:]
    return float(np.min(curve - peak))


def max_drawdown_np(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    curve = np.cumsum(arr)
    peak = np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:]
    return float(np.min(curve - peak))


def finite_min(values: list[float]) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    return float(arr.min())


def cap_for_negative_loss(budget: float, value: float) -> float:
    if not np.isfinite(value) or value >= 0:
        return np.nan
    return safe_div(budget, abs(value))


def load_unit_entries(paths: Paths, manager_policy: str) -> pd.DataFrame:
    scored = pd.read_csv(paths.scored_entries_csv)
    scored["entry_row"] = pd.to_numeric(scored["entry_row"], errors="coerce").astype("int64")
    scored["date"] = scored["date"].astype(str)
    for col in ["entry_ts", "label_available_ts", "net", "gross", "weight"]:
        scored[col] = pd.to_numeric(scored[col], errors="coerce")
    scored["cell"] = np.select(
        [
            scored["gate_r_n5"].astype(bool) & scored["gate_frames_q90"].astype(bool),
            scored["gate_r_n5"].astype(bool) & ~scored["gate_frames_q90"].astype(bool),
            ~scored["gate_r_n5"].astype(bool) & scored["gate_frames_q90"].astype(bool),
        ],
        ["11_r5_frames", "10_r5_only", "01_frames_only"],
        default="00_none",
    )
    base_cols = [
        "date",
        "entry_row",
        "entry_event_index",
        "entry_ts",
        "label_available_ts",
        "cost_mode",
        "cell",
        "weight",
        "net",
        "gross",
        "direction",
    ]
    out = scored[base_cols].copy()
    out = out.rename(columns={"weight": "base_weight"})
    out["direction_label"] = np.where(pd.to_numeric(out["direction"], errors="coerce") > 0, "long", "short")
    out["baseline_gross60"] = out["net"]
    out["policy_gross"] = out["net"]
    out["exit_sec"] = 60.0
    out["path_case_class"] = "not_path_rebuilt"
    out["path_overlay_source"] = "fixed60_fallback"
    out["target_exposure"] = out["base_weight"] * out["cell"].map(FULL_ANCHOR_GAMMA).astype(float)

    manager = pd.read_csv(paths.manager_events_csv)
    manager = manager[manager["policy"].eq(manager_policy)].copy()
    if manager.empty:
        raise RuntimeError(f"No manager rows for policy={manager_policy}")
    for col in [
        "entry_row",
        "target_exposure",
        "baseline_gross60",
        "policy_gross",
        "exit_sec",
        "weighted_gross",
        "baseline_weighted_gross60",
    ]:
        manager[col] = pd.to_numeric(manager[col], errors="coerce")
    manager["entry_row"] = manager["entry_row"].astype("int64")
    manager["date"] = manager["date"].astype(str)
    manager_overlay = manager[
        [
            "date",
            "entry_row",
            "policy_gross",
            "baseline_gross60",
            "exit_sec",
            "path_case_class",
        ]
    ].copy()
    manager_overlay = manager_overlay.rename(
        columns={
            "policy_gross": "manager_policy_gross",
            "baseline_gross60": "manager_baseline_gross60",
            "exit_sec": "manager_exit_sec",
            "path_case_class": "manager_path_case_class",
        }
    )
    out = out.merge(manager_overlay, on=["date", "entry_row"], how="left", validate="one_to_one")
    has_manager = out["manager_policy_gross"].notna()
    out.loc[has_manager, "policy_gross"] = out.loc[has_manager, "manager_policy_gross"]
    out.loc[has_manager, "baseline_gross60"] = out.loc[has_manager, "manager_baseline_gross60"]
    out.loc[has_manager, "exit_sec"] = out.loc[has_manager, "manager_exit_sec"]
    out.loc[has_manager, "path_case_class"] = out.loc[has_manager, "manager_path_case_class"]
    out.loc[has_manager, "path_overlay_source"] = "path_manager_rebuilt"
    out["entry_end_ts"] = out["entry_ts"] + out["exit_sec"].clip(lower=0, upper=60) * US_PER_SECOND
    fallback_end = out["entry_ts"] + 60.0 * US_PER_SECOND
    out["entry_end_ts"] = np.where(
        np.isfinite(out["entry_end_ts"]) & (out["entry_end_ts"] > out["entry_ts"]),
        out["entry_end_ts"],
        fallback_end,
    )

    watcher = pd.read_csv(paths.watcher_events_csv)
    watcher = watcher[watcher["watch_triggered"].astype(str).str.lower().eq("true")].copy()
    if watcher.empty:
        watcher_pivot = pd.DataFrame(columns=["date", "entry_row"])
    else:
        for col in ["entry_row", "watch_final_pnl", "watch_entry_sec", "watch_weighted_final"]:
            watcher[col] = pd.to_numeric(watcher[col], errors="coerce")
        watcher["entry_row"] = watcher["entry_row"].astype("int64")
        watcher_pivot = watcher.pivot_table(
            index=["date", "entry_row"],
            columns="watcher_policy",
            values=["watch_final_pnl", "watch_entry_sec", "watch_mode"],
            aggfunc="first",
        )
        watcher_pivot.columns = [
            f"{a}_{b}" for a, b in watcher_pivot.columns.to_flat_index()
        ]
        watcher_pivot = watcher_pivot.reset_index()

    out = out.merge(watcher_pivot, on=["date", "entry_row"], how="left")
    watcher_names = ["impulse_only", "watcher_q70_absorb_reclaim2", "watcher_q65_absorb_reclaim2"]
    for name in watcher_names:
        pnl_col = f"watch_final_pnl_{name}"
        sec_col = f"watch_entry_sec_{name}"
        mode_col = f"watch_mode_{name}"
        if pnl_col not in out.columns:
            out[pnl_col] = 0.0
            out[sec_col] = np.nan
            out[mode_col] = "none"
        out[pnl_col] = pd.to_numeric(out[pnl_col], errors="coerce").fillna(0.0)
        out[sec_col] = pd.to_numeric(out[sec_col], errors="coerce")
        out[mode_col] = out[mode_col].fillna("none")
        out[f"watch_trigger_{name}"] = out[pnl_col].abs() > 0
        out[f"watch_start_ts_{name}"] = out["entry_ts"] + (
            out["exit_sec"].clip(lower=0, upper=60).fillna(60)
            + out[sec_col].fillna(np.nan)
        ) * US_PER_SECOND
        out[f"watch_end_ts_{name}"] = out["label_available_ts"]

    out["unit_fixed60"] = out["baseline_gross60"]
    out["unit_manager_only"] = out["policy_gross"]
    out["unit_manager_plus_impulse"] = out["policy_gross"] + out["watch_final_pnl_impulse_only"]
    out["unit_manager_plus_q70_watcher"] = out["policy_gross"] + out["watch_final_pnl_watcher_q70_absorb_reclaim2"]
    out["unit_manager_plus_q65_watcher"] = out["policy_gross"] + out["watch_final_pnl_watcher_q65_absorb_reclaim2"]
    out["legs_fixed60"] = 1
    out["legs_manager_only"] = 1
    out["legs_manager_plus_impulse"] = 1 + out["watch_trigger_impulse_only"].astype(int)
    out["legs_manager_plus_q70_watcher"] = 1 + out["watch_trigger_watcher_q70_absorb_reclaim2"].astype(int)
    out["legs_manager_plus_q65_watcher"] = 1 + out["watch_trigger_watcher_q65_absorb_reclaim2"].astype(int)
    return out.sort_values(["date", "entry_ts", "entry_row"]).reset_index(drop=True)


def gamma_grid() -> list[tuple[str, float, float, float, float]]:
    fixed = [
        (ANCHOR_VARIANT, *ANCHOR_TUPLE),
        ("all1", 1.0, 1.0, 1.0, 1.0),
        ("no00_q70_candidate_0_1_0p75_1", 0.0, 1.0, 0.75, 1.0),
        ("balanced_0p5_1_0p75_1", 0.5, 1.0, 0.75, 1.0),
        ("broad_only_1x", 1.0, 0.0, 0.0, 0.0),
        ("r5_only_1", 0.0, 1.0, 0.0, 1.0),
        ("stale_only_1", 0.0, 0.0, 1.0, 1.0),
        ("strict11_only_1", 0.0, 0.0, 0.0, 1.0),
        ("strict11_only_4", 0.0, 0.0, 0.0, 4.0),
        ("milder_1_1_0p25_2", 1.0, 1.0, 0.25, 2.0),
        ("conservative_1_1_0p25_1p5", 1.0, 1.0, 0.25, 1.5),
    ]
    grid = [
        (
            f"grid_g00_{g00:g}_g10_{g10:g}_g01_{g01:g}_g11_{g11:g}",
            g00,
            g10,
            g01,
            g11,
        )
        for g00, g10, g01, g11 in itertools.product(GAMMA00_GRID, GAMMA10_GRID, GAMMA01_GRID, GAMMA11_GRID)
        if g11 >= max(g10, g01)
    ]
    seen: set[tuple[float, float, float, float]] = set()
    out = []
    for name, g00, g10, g01, g11 in [*fixed, *grid]:
        key = (g00, g10, g01, g11)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, g00, g10, g01, g11))
    return out


def gamma_for_cell(
    cell: pd.Series,
    gamma00: float,
    gamma10: float,
    gamma01: float,
    gamma11: float,
) -> np.ndarray:
    return np.select(
        [
            cell.eq("11_r5_frames"),
            cell.eq("10_r5_only"),
            cell.eq("01_frames_only"),
            cell.eq("00_none"),
        ],
        [gamma11, gamma10, gamma01, gamma00],
        default=0.0,
    ).astype(float)


def gamma_vector(gamma00: float, gamma10: float, gamma01: float, gamma11: float) -> np.ndarray:
    return np.asarray([gamma00, gamma10, gamma01, gamma11], dtype=float)


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


def policy_columns(strategy: str) -> tuple[str, str, str | None]:
    unit_col = f"unit_{strategy}"
    legs_col = f"legs_{strategy}"
    if strategy == "manager_plus_impulse":
        return unit_col, legs_col, "impulse_only"
    if strategy == "manager_plus_q70_watcher":
        return unit_col, legs_col, "watcher_q70_absorb_reclaim2"
    if strategy == "manager_plus_q65_watcher":
        return unit_col, legs_col, "watcher_q65_absorb_reclaim2"
    return unit_col, legs_col, None


def interval_profile_for_strategy(df: pd.DataFrame, strategy: str) -> np.ndarray:
    def append_intervals(
        bucket_starts: list[np.ndarray],
        bucket_ends: list[np.ndarray],
        bucket_weights: list[np.ndarray],
        bucket_cells: list[np.ndarray],
        starts: np.ndarray,
        ends: np.ndarray,
        weights: np.ndarray,
        cells: np.ndarray,
    ) -> None:
        valid = (
            np.isfinite(starts)
            & np.isfinite(ends)
            & np.isfinite(weights)
            & (ends > starts)
            & (weights > 0)
            & (cells >= 0)
        )
        if not np.any(valid):
            return
        bucket_starts.append(starts[valid])
        bucket_ends.append(ends[valid])
        bucket_weights.append(weights[valid])
        bucket_cells.append(cells[valid])

    starts = pd.to_numeric(df["entry_ts"], errors="coerce").to_numpy(dtype=float)
    if strategy == "fixed60":
        ends = pd.to_numeric(df["label_available_ts"], errors="coerce").to_numpy(dtype=float)
    else:
        ends = pd.to_numeric(df["entry_end_ts"], errors="coerce").to_numpy(dtype=float)
    weights = pd.to_numeric(df["base_weight"], errors="coerce").to_numpy(dtype=float)
    cells = df["cell"].map(CELL_TO_IDX).fillna(-1).to_numpy(dtype=int)

    all_starts: list[np.ndarray] = []
    all_ends: list[np.ndarray] = []
    all_weights: list[np.ndarray] = []
    all_cells: list[np.ndarray] = []
    append_intervals(all_starts, all_ends, all_weights, all_cells, starts, ends, weights, cells)

    _, _, watcher_name = policy_columns(strategy)
    if watcher_name is not None:
        trigger = df[f"watch_trigger_{watcher_name}"].astype(bool).to_numpy()
        watch_starts = pd.to_numeric(df[f"watch_start_ts_{watcher_name}"], errors="coerce").to_numpy(dtype=float)
        watch_ends = pd.to_numeric(df[f"watch_end_ts_{watcher_name}"], errors="coerce").to_numpy(dtype=float)
        append_intervals(
            all_starts,
            all_ends,
            all_weights,
            all_cells,
            np.where(trigger, watch_starts, np.nan),
            np.where(trigger, watch_ends, np.nan),
            np.where(trigger, weights, 0.0),
            cells,
        )

    if not all_starts:
        return np.empty((0, len(CELL_ORDER)), dtype=float)

    s = np.concatenate(all_starts)
    e = np.concatenate(all_ends)
    w = np.concatenate(all_weights)
    c = np.concatenate(all_cells)
    n = len(w)
    times = np.concatenate([s, e])
    order_kind = np.concatenate([np.ones(n), np.zeros(n)])
    deltas = np.zeros((2 * n, len(CELL_ORDER)), dtype=float)
    row = np.arange(n)
    deltas[row, c] = w
    deltas[row + n, c] = -w
    order = np.lexsort((order_kind, times))
    return np.cumsum(deltas[order], axis=0)


def max_interval_exposure_from_profile(profile: np.ndarray, gamma_vec: np.ndarray) -> float:
    if profile.size == 0:
        return np.nan
    exposure_path = profile @ gamma_vec
    exposure_path = exposure_path[np.isfinite(exposure_path)]
    if not len(exposure_path):
        return np.nan
    return float(np.max(exposure_path))


def interval_exposure_for_strategy(df: pd.DataFrame, strategy: str, exposure: np.ndarray) -> float:
    if strategy == "fixed60":
        starts = pd.to_numeric(df["entry_ts"], errors="coerce").to_numpy(dtype=float)
        ends = pd.to_numeric(df["label_available_ts"], errors="coerce").to_numpy(dtype=float)
        return max_interval_exposure(starts, ends, exposure)

    starts = pd.to_numeric(df["entry_ts"], errors="coerce").to_numpy(dtype=float)
    ends = pd.to_numeric(df["entry_end_ts"], errors="coerce").to_numpy(dtype=float)
    all_starts = [starts]
    all_ends = [ends]
    all_exp = [exposure]
    _, _, watcher_name = policy_columns(strategy)
    if watcher_name is not None:
        trigger = df[f"watch_trigger_{watcher_name}"].astype(bool).to_numpy()
        watch_starts = pd.to_numeric(df[f"watch_start_ts_{watcher_name}"], errors="coerce").to_numpy(dtype=float)
        watch_ends = pd.to_numeric(df[f"watch_end_ts_{watcher_name}"], errors="coerce").to_numpy(dtype=float)
        all_starts.append(np.where(trigger, watch_starts, np.nan))
        all_ends.append(np.where(trigger, watch_ends, np.nan))
        all_exp.append(np.where(trigger, exposure, 0.0))
    return max_interval_exposure(np.concatenate(all_starts), np.concatenate(all_ends), np.concatenate(all_exp))


def prepare_eval_context(
    df: pd.DataFrame,
    *,
    strategy: str,
    pressure_bps: float,
    max_leverage: float,
    scope: str,
    concurrent_profile: np.ndarray | None,
) -> dict[str, Any]:
    unit_col, legs_col, watcher_name = policy_columns(strategy)
    raw_unit_all = pd.to_numeric(df[unit_col], errors="coerce").to_numpy(dtype=float)
    legs_all = pd.to_numeric(df[legs_col], errors="coerce").fillna(1).to_numpy(dtype=float)
    base_all = pd.to_numeric(df["base_weight"], errors="coerce").to_numpy(dtype=float)
    cell_all = df["cell"].map(CELL_TO_IDX).fillna(-1).to_numpy(dtype=int)
    date_codes_all, date_labels = pd.factorize(df["date"].astype(str), sort=True)
    unit_all = raw_unit_all - pressure_bps * legs_all
    valid = (
        np.isfinite(unit_all)
        & np.isfinite(base_all)
        & (base_all > 0)
        & (cell_all >= 0)
        & (date_codes_all >= 0)
    )
    unit = unit_all[valid]
    base = base_all[valid]
    cell = cell_all[valid]
    date_codes = date_codes_all[valid]
    n_dates = len(date_labels)
    daily_cell = np.zeros((n_dates, len(CELL_ORDER)), dtype=float)
    date_cell_exposure = np.zeros((n_dates, len(CELL_ORDER)), dtype=float)
    if len(unit):
        np.add.at(daily_cell, (date_codes, cell), base * unit)
        np.add.at(date_cell_exposure, (date_codes, cell), base)
    cell_exposure = date_cell_exposure.sum(axis=0)
    cell_counts = np.bincount(cell, minlength=len(CELL_ORDER)).astype(float) if len(cell) else np.zeros(len(CELL_ORDER), dtype=float)
    cell_gt2_exposure = np.zeros(len(CELL_ORDER), dtype=float)
    cell_loss_exposure = np.zeros(len(CELL_ORDER), dtype=float)
    if len(cell):
        np.add.at(cell_gt2_exposure, cell[unit > 2.0], base[unit > 2.0])
        np.add.at(cell_loss_exposure, cell[unit <= 0.0], base[unit <= 0.0])
    cell_max_base = np.zeros(len(CELL_ORDER), dtype=float)
    for idx in range(len(CELL_ORDER)):
        vals = base[cell == idx]
        cell_max_base[idx] = float(vals.max()) if len(vals) else 0.0

    trigger_count_by_cell = np.zeros(len(CELL_ORDER), dtype=float)
    trigger_weighted_by_cell = np.zeros(len(CELL_ORDER), dtype=float)
    if watcher_name is not None and len(cell):
        trigger_all = df[f"watch_trigger_{watcher_name}"].astype(bool).to_numpy()[valid]
        watch_unit_all = pd.to_numeric(df[f"watch_final_pnl_{watcher_name}"], errors="coerce").fillna(0.0).to_numpy(dtype=float)[valid]
        trig = trigger_all & np.isfinite(watch_unit_all)
        if np.any(trig):
            np.add.at(trigger_count_by_cell, cell[trig], 1.0)
            np.add.at(trigger_weighted_by_cell, cell[trig], base[trig] * (watch_unit_all[trig] - pressure_bps))

    return {
        "df": df,
        "strategy": strategy,
        "variant_scope": scope,
        "pressure_bps": pressure_bps,
        "max_leverage": max_leverage,
        "watcher_name": watcher_name,
        "unit": unit,
        "base": base,
        "cell": cell,
        "daily_cell": daily_cell,
        "date_cell_exposure": date_cell_exposure,
        "cell_exposure": cell_exposure,
        "cell_counts": cell_counts,
        "cell_gt2_exposure": cell_gt2_exposure,
        "cell_loss_exposure": cell_loss_exposure,
        "cell_max_base": cell_max_base,
        "trigger_count_by_cell": trigger_count_by_cell,
        "trigger_weighted_by_cell": trigger_weighted_by_cell,
        "concurrent_profile": concurrent_profile,
    }


def evaluate_prepared(
    context: dict[str, Any],
    *,
    gamma00: float,
    gamma10: float,
    gamma01: float,
    gamma11: float,
    variant: str,
) -> dict[str, Any]:
    gamma_vec = gamma_vector(gamma00, gamma10, gamma01, gamma11)
    active_cells = gamma_vec > 0
    exposure = float(context["cell_exposure"] @ gamma_vec)
    entries = int(context["cell_counts"][active_cells].sum())
    if entries <= 0 or not np.isfinite(exposure) or exposure <= 0:
        return {
            "strategy": context["strategy"],
            "variant": variant,
            "scope": context["variant_scope"],
            "pressure_bps": context["pressure_bps"],
            "entries": 0,
        }

    daily_net_all = context["daily_cell"] @ gamma_vec
    daily_exposure = context["date_cell_exposure"] @ gamma_vec
    active_days = daily_exposure > 0
    daily_net = daily_net_all[active_days]
    gamma_by_entry = gamma_vec[context["cell"]]
    active_entry = gamma_by_entry > 0
    unit = context["unit"][active_entry]
    pnl = context["base"][active_entry] * gamma_by_entry[active_entry] * context["unit"][active_entry]
    max_concurrent = max_interval_exposure_from_profile(context["concurrent_profile"], gamma_vec)
    exchange_cap = safe_div(context["max_leverage"], max_concurrent)
    total = float(daily_net.sum())
    worst_day = float(daily_net.min()) if len(daily_net) else np.nan
    daily_cvar20 = cvar_np(daily_net, 0.20)
    dd = max_drawdown_np(daily_net)
    entry_worst = float(pnl.min()) if len(pnl) else np.nan
    entry_cvar05 = cvar_np(pnl, 0.05)
    risk_cap_100 = finite_min(
        [
            cap_for_negative_loss(100.0, worst_day),
            cap_for_negative_loss(100.0, daily_cvar20),
            cap_for_negative_loss(100.0, dd),
            cap_for_negative_loss(100.0, entry_worst),
            cap_for_negative_loss(100.0, entry_cvar05),
        ]
    )
    feasible_cap_100 = finite_min([exchange_cap, risk_cap_100])
    trigger_count = int(context["trigger_count_by_cell"][active_cells].sum())
    trigger_weighted = float(context["trigger_weighted_by_cell"] @ gamma_vec)
    return {
        "strategy": context["strategy"],
        "variant": variant,
        "scope": context["variant_scope"],
        "pressure_bps": context["pressure_bps"],
        "gamma00_none": gamma00,
        "gamma10_r5_only": gamma10,
        "gamma01_frames_only": gamma01,
        "gamma11_r5_frames": gamma11,
        "entries": entries,
        "exposure": exposure,
        "total": total,
        "mean": safe_div(total, exposure),
        "median_unit": float(np.median(unit)) if len(unit) else np.nan,
        "gt2_exposure_rate": safe_div(float(context["cell_gt2_exposure"] @ gamma_vec), exposure),
        "loss_exposure_rate": safe_div(float(context["cell_loss_exposure"] @ gamma_vec), exposure),
        "positive_day_count": int((daily_net > 0).sum()),
        "days": int(active_days.sum()),
        "worst_day": worst_day,
        "best_day": float(daily_net.max()) if len(daily_net) else np.nan,
        "daily_cvar20": daily_cvar20,
        "max_drawdown": dd,
        "entry_worst": entry_worst,
        "entry_cvar05": entry_cvar05,
        "entry_cvar10": cvar_np(pnl, 0.10),
        "max_entry_exposure": float(np.max(context["cell_max_base"] * gamma_vec)),
        "max_concurrent_exposure": max_concurrent,
        "cap_by_exchange_leverage": exchange_cap,
        "cap_by_100bp_risk": risk_cap_100,
        "feasible_cap_100": feasible_cap_100,
        "scaled_total_100": total * feasible_cap_100 if np.isfinite(feasible_cap_100) else np.nan,
        "watch_trigger_count": trigger_count,
        "watch_trigger_weighted": trigger_weighted,
        "risk_score": safe_div(total, exposure) + 0.01 * worst_day + 0.02 * daily_cvar20,
    }


def evaluate(
    df: pd.DataFrame,
    *,
    strategy: str,
    gamma00: float,
    gamma10: float,
    gamma01: float,
    gamma11: float,
    variant: str,
    pressure_bps: float,
    max_leverage: float,
    scope: str,
    concurrent_profile: np.ndarray | None = None,
) -> dict[str, Any]:
    unit_col, legs_col, watcher_name = policy_columns(strategy)
    gamma_vec = gamma_vector(gamma00, gamma10, gamma01, gamma11)
    gamma = gamma_for_cell(df["cell"], gamma00, gamma10, gamma01, gamma11)
    exposure = df["base_weight"].to_numpy(dtype=float) * gamma
    raw_unit = pd.to_numeric(df[unit_col], errors="coerce").to_numpy(dtype=float)
    legs = pd.to_numeric(df[legs_col], errors="coerce").fillna(1).to_numpy(dtype=float)
    unit = raw_unit - pressure_bps * legs
    active = np.isfinite(unit) & np.isfinite(exposure) & (exposure > 0)
    active_df = df.loc[df.index[active]].copy()
    exposure = exposure[active]
    unit = unit[active]
    pnl = exposure * unit
    if not len(pnl):
        return {
            "strategy": strategy,
            "variant": variant,
            "scope": scope,
            "pressure_bps": pressure_bps,
            "entries": 0,
        }
    daily = active_df.assign(pnl=pnl, exposure=exposure).groupby("date", sort=True).agg(
        daily_net=("pnl", "sum"),
        daily_exposure=("exposure", "sum"),
        entries=("pnl", "size"),
    )
    trigger_count = 0
    trigger_weighted = 0.0
    if watcher_name is not None:
        trig = active_df[f"watch_trigger_{watcher_name}"].astype(bool).to_numpy()
        trigger_count = int(trig.sum())
        watch_unit = pd.to_numeric(active_df[f"watch_final_pnl_{watcher_name}"], errors="coerce").to_numpy(dtype=float)
        trigger_weighted = float(np.sum(exposure[trig] * (watch_unit[trig] - pressure_bps)))
    max_concurrent = (
        max_interval_exposure_from_profile(concurrent_profile, gamma_vec)
        if concurrent_profile is not None
        else interval_exposure_for_strategy(active_df, strategy, exposure)
    )
    exchange_cap = safe_div(max_leverage, max_concurrent)
    total = float(np.sum(pnl))
    worst_day = float(daily["daily_net"].min())
    entry_worst = float(np.min(pnl))
    entry_cvar05 = cvar(pnl, 0.05)
    daily_cvar20 = cvar(daily["daily_net"].to_numpy(dtype=float), 0.20)
    dd = max_drawdown(daily["daily_net"].to_numpy(dtype=float))
    risk_cap_100 = finite_min(
        [
            cap_for_negative_loss(100.0, worst_day),
            cap_for_negative_loss(100.0, daily_cvar20),
            cap_for_negative_loss(100.0, dd),
            cap_for_negative_loss(100.0, entry_worst),
            cap_for_negative_loss(100.0, entry_cvar05),
        ]
    )
    feasible_cap_100 = finite_min([exchange_cap, risk_cap_100])
    return {
        "strategy": strategy,
        "variant": variant,
        "scope": scope,
        "pressure_bps": pressure_bps,
        "gamma00_none": gamma00,
        "gamma10_r5_only": gamma10,
        "gamma01_frames_only": gamma01,
        "gamma11_r5_frames": gamma11,
        "entries": int(len(pnl)),
        "exposure": float(np.sum(exposure)),
        "total": total,
        "mean": safe_div(total, float(np.sum(exposure))),
        "median_unit": float(np.median(unit)),
        "gt2_exposure_rate": safe_div(float(np.sum(exposure[unit > 2.0])), float(np.sum(exposure))),
        "loss_exposure_rate": safe_div(float(np.sum(exposure[unit <= 0.0])), float(np.sum(exposure))),
        "positive_day_count": int((daily["daily_net"] > 0).sum()),
        "days": int(len(daily)),
        "worst_day": worst_day,
        "best_day": float(daily["daily_net"].max()),
        "daily_cvar20": daily_cvar20,
        "max_drawdown": dd,
        "entry_worst": entry_worst,
        "entry_cvar05": entry_cvar05,
        "entry_cvar10": cvar(pnl, 0.10),
        "max_entry_exposure": float(np.max(exposure)),
        "max_concurrent_exposure": max_concurrent,
        "cap_by_exchange_leverage": exchange_cap,
        "cap_by_100bp_risk": risk_cap_100,
        "feasible_cap_100": feasible_cap_100,
        "scaled_total_100": total * feasible_cap_100 if np.isfinite(feasible_cap_100) else np.nan,
        "watch_trigger_count": trigger_count,
        "watch_trigger_weighted": trigger_weighted,
        "risk_score": safe_div(total, float(np.sum(exposure))) + 0.01 * worst_day + 0.02 * daily_cvar20,
    }


def build_variants(df: pd.DataFrame, max_leverage: float) -> pd.DataFrame:
    strategies = [
        "fixed60",
        "manager_only",
        "manager_plus_impulse",
        "manager_plus_q70_watcher",
        "manager_plus_q65_watcher",
    ]
    rows = []
    profiles = {strategy: interval_profile_for_strategy(df, strategy) for strategy in strategies}
    for strategy in strategies:
        profile = profiles[strategy]
        for pressure in PRESSURES:
            context = prepare_eval_context(
                df,
                strategy=strategy,
                pressure_bps=pressure,
                max_leverage=max_leverage,
                scope="all_history",
                concurrent_profile=profile,
            )
            for name, g00, g10, g01, g11 in gamma_grid():
                rows.append(
                    evaluate_prepared(
                        context,
                        gamma00=g00,
                        gamma10=g10,
                        gamma01=g01,
                        gamma11=g11,
                        variant=name,
                    )
                )
    return pd.DataFrame(rows).sort_values(["pressure_bps", "risk_score", "total"], ascending=[True, False, False])


def pareto_frontier(variants: pd.DataFrame, pressure: float = 0.0) -> pd.DataFrame:
    work = variants[variants["pressure_bps"].eq(pressure)].dropna(
        subset=["total", "mean", "worst_day", "daily_cvar20", "entry_cvar05", "scaled_total_100"]
    ).copy()
    if work.empty:
        return work
    metrics = ["total", "mean", "worst_day", "daily_cvar20", "entry_cvar05", "scaled_total_100"]
    values = work[metrics].to_numpy(dtype=float)
    keep = np.ones(len(work), dtype=bool)
    for i in range(len(work)):
        if not keep[i]:
            continue
        dominated = np.all(values >= values[i], axis=1) & np.any(values > values[i], axis=1)
        dominated[i] = False
        if dominated.any():
            keep[i] = False
    return work.loc[keep].sort_values(["scaled_total_100", "risk_score", "total"], ascending=False)


def build_daily(df: pd.DataFrame, variants: pd.DataFrame, max_leverage: float) -> pd.DataFrame:
    selected = [
        ("fixed60", ANCHOR_VARIANT, *ANCHOR_TUPLE),
        ("manager_only", ANCHOR_VARIANT, *ANCHOR_TUPLE),
        ("manager_plus_impulse", ANCHOR_VARIANT, *ANCHOR_TUPLE),
        ("manager_plus_q70_watcher", ANCHOR_VARIANT, *ANCHOR_TUPLE),
        ("manager_plus_q65_watcher", ANCHOR_VARIANT, *ANCHOR_TUPLE),
    ]
    leader = variants[variants["pressure_bps"].eq(0)].sort_values("scaled_total_100", ascending=False).head(10)
    for _, row in leader.iterrows():
        selected.append(
            (
                str(row["strategy"]),
                str(row["variant"]),
                float(row["gamma00_none"]),
                float(row["gamma10_r5_only"]),
                float(row["gamma01_frames_only"]),
                float(row["gamma11_r5_frames"]),
            )
        )
    seen = set()
    rows = []
    for strategy, variant, g00, g10, g01, g11 in selected:
        key = (strategy, variant, g00, g10, g01, g11)
        if key in seen:
            continue
        seen.add(key)
        gamma = gamma_for_cell(df["cell"], g00, g10, g01, g11)
        exposure = df["base_weight"].to_numpy(dtype=float) * gamma
        unit_col, legs_col, _ = policy_columns(strategy)
        unit = pd.to_numeric(df[unit_col], errors="coerce").to_numpy(dtype=float)
        pnl = exposure * unit
        active = np.isfinite(pnl) & (exposure > 0)
        daily = df.loc[df.index[active]].assign(pnl=pnl[active], exposure=exposure[active]).groupby("date", sort=True).agg(
            total=("pnl", "sum"),
            exposure=("exposure", "sum"),
            entries=("pnl", "size"),
        )
        for date, drow in daily.reset_index().iterrows():
            rows.append(
                {
                    "strategy": strategy,
                    "variant": variant,
                    "date": drow["date"],
                    "gamma00_none": g00,
                    "gamma10_r5_only": g10,
                    "gamma01_frames_only": g01,
                    "gamma11_r5_frames": g11,
                    "entries": int(drow["entries"]),
                    "exposure": float(drow["exposure"]),
                    "total": float(drow["total"]),
                    "mean": safe_div(float(drow["total"]), float(drow["exposure"])),
                }
            )
    return pd.DataFrame(rows)


def choose_train_variant(train: pd.DataFrame, max_leverage: float) -> dict[str, Any]:
    rows = []
    strategies = ["manager_only", "manager_plus_impulse", "manager_plus_q70_watcher"]
    profiles = {strategy: interval_profile_for_strategy(train, strategy) for strategy in strategies}
    contexts = {
        strategy: prepare_eval_context(
            train,
            strategy=strategy,
            pressure_bps=0.0,
            max_leverage=max_leverage,
            scope="train",
            concurrent_profile=profiles[strategy],
        )
        for strategy in strategies
    }
    for strategy, (name, g00, g10, g01, g11) in itertools.product(
        strategies,
        gamma_grid(),
    ):
        row = evaluate_prepared(
            contexts[strategy],
            gamma00=g00,
            gamma10=g10,
            gamma01=g01,
            gamma11=g11,
            variant=name,
        )
        if row["entries"] < 50 or row["days"] < MIN_TRAIN_DAYS:
            continue
        if row["total"] <= 0 or row["mean"] <= 0:
            continue
        if row["positive_day_count"] < max(3, int(np.ceil(0.6 * row["days"]))):
            continue
        rows.append(row)
    if not rows:
        return {
            "strategy": "manager_plus_q70_watcher",
            "variant": ANCHOR_VARIANT,
            "gamma00_none": ANCHOR_TUPLE[0],
            "gamma10_r5_only": ANCHOR_TUPLE[1],
            "gamma01_frames_only": ANCHOR_TUPLE[2],
            "gamma11_r5_frames": ANCHOR_TUPLE[3],
            "selection_status": "fallback_full_anchor_q70",
        }
    table = pd.DataFrame(rows).sort_values(["scaled_total_100", "risk_score", "total"], ascending=False)
    out = table.iloc[0].to_dict()
    out["selection_status"] = "selected_by_train_scaled_total_100"
    return out


def walk_forward(df: pd.DataFrame, max_leverage: float) -> pd.DataFrame:
    dates = sorted(df["date"].astype(str).unique().tolist())
    rows = []
    for i, date in enumerate(dates):
        if i < MIN_TRAIN_DAYS:
            continue
        train = df[df["date"].isin(dates[:i])].copy()
        test = df[df["date"].eq(date)].copy()
        chosen = choose_train_variant(train, max_leverage)
        test_profiles = {
            strategy: interval_profile_for_strategy(test, strategy)
            for strategy in ["manager_only", "manager_plus_impulse", "manager_plus_q70_watcher"]
        }
        test_contexts = {
            strategy: prepare_eval_context(
                test,
                strategy=strategy,
                pressure_bps=0.0,
                max_leverage=max_leverage,
                scope=f"test_{date}",
                concurrent_profile=test_profiles[strategy],
            )
            for strategy in ["manager_only", "manager_plus_impulse", "manager_plus_q70_watcher"]
        }
        test_eval = evaluate_prepared(
            test_contexts[str(chosen["strategy"])],
            gamma00=float(chosen["gamma00_none"]),
            gamma10=float(chosen["gamma10_r5_only"]),
            gamma01=float(chosen["gamma01_frames_only"]),
            gamma11=float(chosen["gamma11_r5_frames"]),
            variant=str(chosen["variant"]),
        )
        anchor_q70 = evaluate_prepared(
            test_contexts["manager_plus_q70_watcher"],
            gamma00=ANCHOR_TUPLE[0],
            gamma10=ANCHOR_TUPLE[1],
            gamma01=ANCHOR_TUPLE[2],
            gamma11=ANCHOR_TUPLE[3],
            variant=ANCHOR_VARIANT,
        )
        manager_anchor = evaluate_prepared(
            test_contexts["manager_only"],
            gamma00=ANCHOR_TUPLE[0],
            gamma10=ANCHOR_TUPLE[1],
            gamma01=ANCHOR_TUPLE[2],
            gamma11=ANCHOR_TUPLE[3],
            variant=ANCHOR_VARIANT,
        )
        rows.append(
            {
                "test_date": date,
                "train_start": dates[0],
                "train_end": dates[i - 1],
                "chosen_strategy": chosen["strategy"],
                "chosen_variant": chosen["variant"],
                "selection_status": chosen["selection_status"],
                "gamma00_none": chosen["gamma00_none"],
                "gamma10_r5_only": chosen["gamma10_r5_only"],
                "gamma01_frames_only": chosen["gamma01_frames_only"],
                "gamma11_r5_frames": chosen["gamma11_r5_frames"],
                "test_total": test_eval["total"],
                "test_mean": test_eval["mean"],
                "test_entries": test_eval["entries"],
                "test_watch_trigger_count": test_eval["watch_trigger_count"],
                "anchor_q70_total": anchor_q70["total"],
                "manager_anchor_total": manager_anchor["total"],
                "anchor_q70_delta_vs_manager": anchor_q70["total"] - manager_anchor["total"],
            }
        )
    return pd.DataFrame(rows)


def summarize_policies(variants: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy, group in variants[variants["pressure_bps"].eq(0)].groupby("strategy", sort=False):
        best_scaled = group.sort_values("scaled_total_100", ascending=False).iloc[0]
        best_total = group.sort_values("total", ascending=False).iloc[0]
        anchor = group[group["variant"].eq(ANCHOR_VARIANT)]
        anchor_row = anchor.iloc[0] if not anchor.empty else None
        rows.append(
            {
                "strategy": strategy,
                "best_scaled_variant": best_scaled["variant"],
                "best_scaled_total_100": float(best_scaled["scaled_total_100"]),
                "best_scaled_raw_total": float(best_scaled["total"]),
                "best_scaled_worst_day": float(best_scaled["worst_day"]),
                "best_scaled_entry_worst": float(best_scaled["entry_worst"]),
                "best_scaled_max_concurrent": float(best_scaled["max_concurrent_exposure"]),
                "best_total_variant": best_total["variant"],
                "best_raw_total": float(best_total["total"]),
                "anchor_total": float(anchor_row["total"]) if anchor_row is not None else np.nan,
                "anchor_scaled_total_100": float(anchor_row["scaled_total_100"]) if anchor_row is not None else np.nan,
                "anchor_watch_triggers": int(anchor_row["watch_trigger_count"]) if anchor_row is not None else 0,
            }
        )
    return pd.DataFrame(rows).sort_values("best_scaled_total_100", ascending=False)


def build_cell_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy in ["fixed60", "manager_only", "manager_plus_q70_watcher"]:
        unit_col, _, watcher_name = policy_columns(strategy)
        for cell, group in df.groupby("cell", sort=True):
            unit = pd.to_numeric(group[unit_col], errors="coerce").to_numpy(dtype=float)
            base_weight = group["base_weight"].to_numpy(dtype=float)
            rows.append(
                {
                    "strategy": strategy,
                    "cell": cell,
                    "entries": int(len(group)),
                    "base_exposure": float(base_weight.sum()),
                    "base_weighted_total": float(np.sum(base_weight * unit)),
                    "base_mean": safe_div(float(np.sum(base_weight * unit)), float(base_weight.sum())),
                    "positive_unit_rate": float(np.mean(unit > 0)),
                    "unit_worst": float(np.min(unit)),
                    "unit_cvar05": cvar(unit, 0.05),
                    "watch_triggers": int(group[f"watch_trigger_{watcher_name}"].sum()) if watcher_name else 0,
                }
            )
    return pd.DataFrame(rows)


def write_report(
    paths: Paths,
    *,
    unit_entries: pd.DataFrame,
    variants: pd.DataFrame,
    pareto: pd.DataFrame,
    daily: pd.DataFrame,
    walk: pd.DataFrame,
    policy_summary: pd.DataFrame,
    cell_summary: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    top_c0 = variants[variants["pressure_bps"].eq(0)].sort_values("scaled_total_100", ascending=False).head(20)
    top_c1 = variants[variants["pressure_bps"].eq(1)].sort_values("scaled_total_100", ascending=False).head(12)
    top_c2 = variants[variants["pressure_bps"].eq(2)].sort_values("scaled_total_100", ascending=False).head(12)
    anchor_q70 = variants[
        variants["strategy"].eq("manager_plus_q70_watcher")
        & variants["variant"].eq(ANCHOR_VARIANT)
        & variants["pressure_bps"].eq(0.0)
    ].iloc[0]
    anchor_manager = variants[
        variants["strategy"].eq("manager_only")
        & variants["variant"].eq(ANCHOR_VARIANT)
        & variants["pressure_bps"].eq(0.0)
    ].iloc[0]
    top_q70 = variants[
        variants["strategy"].eq("manager_plus_q70_watcher")
        & variants["pressure_bps"].eq(0.0)
    ].sort_values("scaled_total_100", ascending=False).iloc[0]
    top_q65 = variants[
        variants["strategy"].eq("manager_plus_q65_watcher")
        & variants["pressure_bps"].eq(0.0)
    ].sort_values("scaled_total_100", ascending=False).iloc[0]
    top_q70_c1 = variants[
        variants["strategy"].eq("manager_plus_q70_watcher")
        & variants["pressure_bps"].eq(1.0)
    ].sort_values("scaled_total_100", ascending=False).iloc[0]
    top_q70_c2 = variants[
        variants["strategy"].eq("manager_plus_q70_watcher")
        & variants["pressure_bps"].eq(2.0)
    ].sort_values("scaled_total_100", ascending=False).iloc[0]
    anchor_rows = variants[
        variants["variant"].eq(ANCHOR_VARIANT)
        & variants["pressure_bps"].isin([0.0, 1.0, 2.0])
        & variants["strategy"].isin(["fixed60", "manager_only", "manager_plus_impulse", "manager_plus_q70_watcher", "manager_plus_q65_watcher"])
    ].sort_values(["pressure_bps", "strategy"])
    q70_triggers = unit_entries[unit_entries["watch_trigger_watcher_q70_absorb_reclaim2"].astype(bool)].copy()
    cell_counts = unit_entries["cell"].value_counts().sort_index()
    path_counts = unit_entries["path_overlay_source"].value_counts().sort_index()
    q70_gamma_map = {
        "00_none": float(top_q70["gamma00_none"]),
        "10_r5_only": float(top_q70["gamma10_r5_only"]),
        "01_frames_only": float(top_q70["gamma01_frames_only"]),
        "11_r5_frames": float(top_q70["gamma11_r5_frames"]),
    }
    q70_contrib = unit_entries.copy()
    q70_contrib["leader_gamma"] = q70_contrib["cell"].map(q70_gamma_map).astype(float)
    q70_contrib["leader_exposure"] = q70_contrib["base_weight"] * q70_contrib["leader_gamma"]
    q70_contrib["leader_pnl"] = q70_contrib["leader_exposure"] * q70_contrib["unit_manager_plus_q70_watcher"]
    q70_cell_contrib = (
        q70_contrib.groupby("cell", sort=True)
        .agg(
            entries=("entry_row", "size"),
            exposure=("leader_exposure", "sum"),
            total=("leader_pnl", "sum"),
            worst_entry=("leader_pnl", "min"),
        )
        .reset_index()
    )
    q70_cell_contrib["mean"] = q70_cell_contrib["total"] / q70_cell_contrib["exposure"]
    lines = [
        "# CCUSDT V1 TFI Watcher-Aware Pareto",
        "",
        f"Status: `{args.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Scope",
        "",
        "This is the historical Pareto pass for the restrained rule family:",
        "",
        "```text",
        "full scored four-cell universe",
        "-> pm_11_drawdown_h4_peakguard where rebuilt",
        "-> fixed60 fallback where path is not rebuilt",
        "-> optional post-exit watcher where rebuilt",
        "-> gamma sizing by mutually exclusive cell, including 00",
        "```",
        "",
        "The optimized historical universe is now the full scored universe:",
        f"`{len(unit_entries)}` entries from `{unit_entries['date'].min()}` to `{unit_entries['date'].max()}`.",
        "",
        "Cell counts:",
        "",
        markdown_table(cell_counts.rename_axis("cell").reset_index(name="entries"), ["cell", "entries"], max_rows=10),
        "",
        "Path overlay coverage:",
        "",
        markdown_table(path_counts.rename_axis("path_overlay_source").reset_index(name="entries"), ["path_overlay_source", "entries"], max_rows=10),
        "",
        "`00_none` is intentionally included in the sizing universe. Where no",
        "path-manager/watch rebuild exists, it uses the fixed60 zero-fee payoff",
        "as a fallback rather than disappearing from concurrency and gamma risk.",
        "",
        "## Main Result",
        "",
        "At the full anchor:",
        "",
        "```text",
        f"manager_only                 total {float(anchor_manager['total']):.4f}",
        f"manager_plus_q70_watcher     total {float(anchor_q70['total']):.4f}",
        f"q70 watcher delta            total {float(anchor_q70['total'] - anchor_manager['total']):.4f}",
        f"anchor q70 scaled100         {float(anchor_q70['scaled_total_100']):.4f}",
        f"anchor q70 max concurrency   {float(anchor_q70['max_concurrent_exposure']):.4f}",
        "```",
        "",
        f"The 100-budget + {float(args.max_leverage):g}x Pareto should now be read as a four-cell sizing",
        "problem, not an A/B-only watcher problem. The cleaner q70 scaled leader is:",
        "",
        "```text",
        f"strategy      {top_q70['strategy']}",
        f"variant       {top_q70['variant']}",
        f"gamma         (00={float(top_q70['gamma00_none']):.4f}, 10={float(top_q70['gamma10_r5_only']):.4f}, 01={float(top_q70['gamma01_frames_only']):.4f}, 11={float(top_q70['gamma11_r5_frames']):.4f})",
        f"raw total     {float(top_q70['total']):.4f}",
        f"scaled100     {float(top_q70['scaled_total_100']):.4f}",
        f"worst day     {float(top_q70['worst_day']):.4f}",
        f"entry worst   {float(top_q70['entry_worst']):.4f}",
        f"max conc      {float(top_q70['max_concurrent_exposure']):.4f}",
        "```",
        "",
        "At that q70 leader, contribution by cell is:",
        "",
        markdown_table(q70_cell_contrib, ["cell", "entries", "exposure", "total", "mean", "worst_entry"], max_rows=10),
        "",
        "The q65 sensitivity has a slightly higher scaled value:",
        "",
        "```text",
        f"q65 best scaled100 {float(top_q65['scaled_total_100']):.4f}",
        f"q70 best scaled100 {float(top_q70['scaled_total_100']):.4f}",
        f"difference         {float(top_q65['scaled_total_100'] - top_q70['scaled_total_100']):.4f}",
        "```",
        "",
        "That small gap is not enough evidence to promote q65; it is still the",
        "recall sensitivity. Under a 1bps pressure term, the q70 leader remains",
        "near the same balanced low-concurrency point; under 2bps pressure, q70",
        "moves toward much lower broad `00` and higher `11`, which is the warning",
        "that weak/broad exposure becomes expensive once non-fee pressure is added:",
        "",
        "```text",
        f"C=1 q70 leader {top_q70_c1['variant']}, scaled100 {float(top_q70_c1['scaled_total_100']):.4f}",
        f"C=2 q70 leader {top_q70_c2['variant']}, scaled100 {float(top_q70_c2['scaled_total_100']):.4f}",
        "```",
        "",
        "## Model",
        "",
        "The full anchor exposure is decomposed as:",
        "",
        "$$",
        r"w_i^{anchor}=b_i\gamma^{anchor}_{c_i},\qquad",
        r"\gamma^{anchor}_{00}=1,\ \gamma^{anchor}_{10}=0.75,\ \gamma^{anchor}_{01}=0.25,\ \gamma^{anchor}_{11}=4.",
        "$$",
        "",
        "Pareto only changes:",
        "",
        "$$",
        r"w_i=b_i\gamma_{c_i},\qquad c_i\in\{00,10,01,11\}.",
        "$$",
        "",
        "For watcher variants, per-unit path payoff is:",
        "",
        "$$",
        r"y_i=R_i^{manager}+1_{\{trigger\}}R_i^{reentry}.",
        "$$",
        "",
        "Pressure tests subtract one cost unit per opened leg:",
        "",
        "$$",
        r"y_i(c)=R_i^{manager}-c+1_{\{trigger\}}(R_i^{reentry}-c).",
        "$$",
        "",
        "## Anchor Rule Comparison",
        "",
        markdown_table(
            anchor_rows,
            [
                "pressure_bps",
                "strategy",
                "variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "entries",
                "exposure",
                "total",
                "mean",
                "worst_day",
                "entry_worst",
                "max_concurrent_exposure",
                "cap_by_exchange_leverage",
                "feasible_cap_100",
                "scaled_total_100",
                "watch_trigger_count",
                "watch_trigger_weighted",
            ],
            max_rows=30,
        ),
        "",
        "## Top C0 Historical Variants By 100-Budget Scaled Total",
        "",
        markdown_table(
            top_c0,
            [
                "strategy",
                "variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "entries",
                "exposure",
                "total",
                "mean",
                "worst_day",
                "entry_worst",
                "max_concurrent_exposure",
                "cap_by_exchange_leverage",
                "feasible_cap_100",
                "scaled_total_100",
                "watch_trigger_count",
            ],
            max_rows=20,
        ),
        "",
        "## Pareto Frontier C0",
        "",
        markdown_table(
            pareto,
            [
                "strategy",
                "variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "total",
                "mean",
                "worst_day",
                "daily_cvar20",
                "entry_cvar05",
                "scaled_total_100",
                "watch_trigger_count",
            ],
            max_rows=30,
        ),
        "",
        "## Pressure Sensitivity",
        "",
        "Top C=1:",
        "",
        markdown_table(
            top_c1,
            [
                "strategy",
                "variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "total",
                "mean",
                "worst_day",
                "scaled_total_100",
                "watch_trigger_count",
            ],
            max_rows=12,
        ),
        "",
        "Top C=2:",
        "",
        markdown_table(
            top_c2,
            [
                "strategy",
                "variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "total",
                "mean",
                "worst_day",
                "scaled_total_100",
                "watch_trigger_count",
            ],
            max_rows=12,
        ),
        "",
        "## Strategy Summary",
        "",
        markdown_table(
            policy_summary,
            [
                "strategy",
                "best_scaled_variant",
                "best_scaled_total_100",
                "best_scaled_raw_total",
                "best_scaled_worst_day",
                "best_scaled_entry_worst",
                "best_scaled_max_concurrent",
                "anchor_total",
                "anchor_scaled_total_100",
                "anchor_watch_triggers",
            ],
            max_rows=20,
        ),
        "",
        "## Cell Summary",
        "",
        markdown_table(
            cell_summary,
            [
                "strategy",
                "cell",
                "entries",
                "base_exposure",
                "base_weighted_total",
                "base_mean",
                "positive_unit_rate",
                "unit_worst",
                "unit_cvar05",
                "watch_triggers",
            ],
            max_rows=20,
        ),
        "",
        "## Walk-Forward Sanity",
        "",
        "This walk-forward chooses among `manager_only`, `manager_plus_impulse`,",
        "and `manager_plus_q70_watcher` using only prior dates. It is a sanity",
        "check, not a final live selection rule.",
        "",
        markdown_table(
            walk,
            [
                "test_date",
                "chosen_strategy",
                "chosen_variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "test_total",
                "test_mean",
                "test_watch_trigger_count",
                "anchor_q70_total",
                "manager_anchor_total",
                "anchor_q70_delta_vs_manager",
            ],
            max_rows=20,
        ),
        "",
        "## Q70 Watcher Trigger Rows",
        "",
        markdown_table(
            q70_triggers,
            [
                "date",
                "entry_row",
                "cell",
                "direction_label",
                "base_weight",
                "target_exposure",
                "policy_gross",
                "watch_final_pnl_watcher_q70_absorb_reclaim2",
                "unit_manager_plus_q70_watcher",
                "watch_mode_watcher_q70_absorb_reclaim2",
            ],
            max_rows=10,
        ),
        "",
        "## Read",
        "",
        "- The q70 watcher is useful at the full anchor only through the rows whose",
        "  path was rebuilt; `00` contributes sizing and concurrency, not watcher",
        "  triggers.",
        "- `gamma00` is now a real optimized branch. If the leader reduces it, that",
        "  is a sizing conclusion; if it keeps it, the broad baseline is carrying",
        "  real historical PnL under the current fallback.",
        "- q65 remains a sensitivity row only. If it tops raw totals, that does not",
        "  make it the rule; it is closer to recall-chasing.",
        "- This pass is historical. The next useful validation is OOS path rebuild",
        "  and checking whether the fixed60 fallback for `00` is still acceptable,",
        "  not adding more watcher predicates.",
        "",
        "## Outputs",
        "",
        f"- `{paths.unit_entries_csv}`",
        f"- `{paths.variants_csv}`",
        f"- `{paths.pareto_csv}`",
        f"- `{paths.daily_csv}`",
        f"- `{paths.walkforward_csv}`",
        f"- `{paths.policy_summary_csv}`",
        f"- `{paths.leverage_csv}`",
        f"- `{paths.cell_summary_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        "python scripts/ccusdt_v1_tfi_watcher_pareto.py",
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
        manager_events_name=args.manager_events,
        watcher_events_name=args.watcher_events,
        scored_entries_name=args.scored_entries,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    unit_entries = load_unit_entries(paths, args.manager_policy)
    variants = build_variants(unit_entries, float(args.max_leverage))
    pareto = pareto_frontier(variants, pressure=0.0)
    daily = build_daily(unit_entries, variants, float(args.max_leverage))
    walk = walk_forward(unit_entries, float(args.max_leverage))
    policy_summary = summarize_policies(variants)
    leverage = variants[
        variants["pressure_bps"].eq(0.0)
        & variants["variant"].eq(ANCHOR_VARIANT)
    ][
        [
            "strategy",
            "variant",
            "pressure_bps",
            "gamma00_none",
            "gamma10_r5_only",
            "gamma01_frames_only",
            "gamma11_r5_frames",
            "max_concurrent_exposure",
            "cap_by_exchange_leverage",
            "cap_by_100bp_risk",
            "feasible_cap_100",
            "scaled_total_100",
            "entry_worst",
            "entry_cvar05",
            "worst_day",
        ]
    ].copy()
    cell_summary = build_cell_summary(unit_entries)

    summary = {
        "run_tag": args.run_tag,
        "guardrail": GUARDRAIL,
        "entries": int(len(unit_entries)),
        "date_start": str(unit_entries["date"].min()),
        "date_end": str(unit_entries["date"].max()),
        "manager_policy": args.manager_policy,
        "main_watcher": args.main_watcher,
        "max_leverage": float(args.max_leverage),
        "variant_count": int(len(variants)),
        "pareto_count_c0": int(len(pareto)),
        "anchor_q70": variants[
            variants["strategy"].eq("manager_plus_q70_watcher")
            & variants["variant"].eq(ANCHOR_VARIANT)
            & variants["pressure_bps"].eq(0.0)
        ].iloc[0].to_dict(),
        "policy_summary": policy_summary.to_dict(orient="records"),
        "outputs": {
            "unit_entries_csv": str(paths.unit_entries_csv),
            "variants_csv": str(paths.variants_csv),
            "pareto_csv": str(paths.pareto_csv),
            "daily_csv": str(paths.daily_csv),
            "walkforward_csv": str(paths.walkforward_csv),
            "policy_summary_csv": str(paths.policy_summary_csv),
            "leverage_csv": str(paths.leverage_csv),
            "cell_summary_csv": str(paths.cell_summary_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }

    unit_entries.to_csv(paths.unit_entries_csv, index=False)
    variants.to_csv(paths.variants_csv, index=False)
    pareto.to_csv(paths.pareto_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    walk.to_csv(paths.walkforward_csv, index=False)
    policy_summary.to_csv(paths.policy_summary_csv, index=False)
    leverage.to_csv(paths.leverage_csv, index=False)
    cell_summary.to_csv(paths.cell_summary_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(
        paths,
        unit_entries=unit_entries,
        variants=variants,
        pareto=pareto,
        daily=daily,
        walk=walk,
        policy_summary=policy_summary,
        cell_summary=cell_summary,
        args=args,
    )
    anchor_q70 = summary["anchor_q70"]
    top = variants[variants["pressure_bps"].eq(0.0)].sort_values("scaled_total_100", ascending=False).iloc[0]
    print(f"wrote {paths.report_md}")
    print(
        "anchor_q70 "
        f"total={anchor_q70['total']:.4f} scaled100={anchor_q70['scaled_total_100']:.4f} "
        f"triggers={anchor_q70['watch_trigger_count']}"
    )
    print(
        "top_c0 "
        f"{top['strategy']} {top['variant']} "
        f"total={top['total']:.4f} scaled100={top['scaled_total_100']:.4f}"
    )


if __name__ == "__main__":
    main()

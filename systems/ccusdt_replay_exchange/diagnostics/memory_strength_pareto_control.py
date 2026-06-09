#!/usr/bin/env python
"""Research-only Pareto diagnostic for CCUSDT memory-strength controls.

This script does not create new entries and does not touch Runner/Bot runtime.
It reuses an existing fast run's shadow entry candidates, reconstructs
pretrade-safe closed-memory strength from already closed candidates, and tests
low-degree exposure control functions based on Delta/Energy/Z.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_BASELINE_RUN = Path(
    "systems/ccusdt_replay_exchange/runs/experiments/"
    "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260505_18_20260522"
)
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/memory_strength_pareto_control")
DEFAULT_REPORT = Path(
    "docs/markets/ccusdt/research/strategy/"
    "v1-ccusdt-memory-strength-pareto-control-20260603.md"
)
EPS = 1e-12


@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    family: str
    low_mult: float = 1.0
    mid_mult: float = 1.0
    high_mult: float = 1.0
    boost_mult: float = 1.0
    delta_q: float = 0.50
    energy_q: float = 0.70
    z_q: float = 0.70


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE_RUN)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--test-from-date", default="2026-05-16")
    parser.add_argument("--test-to-date", default="2026-05-18")
    parser.add_argument("--leverage-cap", type=float, default=3.0)
    parser.add_argument("--stress-bps", default="0,1,2,3")
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    left = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out: list[str] = []
    current = left
    while current <= right:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def finite_quantile(values: pd.Series, q: float) -> float | None:
    clean = pd.to_numeric(values, errors="coerce")
    clean = clean[np.isfinite(clean)]
    if clean.empty:
        return None
    return float(clean.quantile(q))


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_baseline(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    entries_path = run_dir / "entries.parquet"
    exits_path = run_dir / "exits.parquet"
    summary_path = run_dir / "summary.json"
    if not entries_path.exists() or not exits_path.exists():
        raise FileNotFoundError(f"missing entries/exits under {run_dir}")
    entries = pd.read_parquet(entries_path).copy()
    exits = pd.read_parquet(exits_path).copy()
    summary = read_json(summary_path) if summary_path.exists() else {}
    entries = entries.sort_values(["entry_ts_us", "shadow_position_id"]).reset_index(drop=True)
    exits = exits.sort_values(["entry_ts_us", "shadow_position_id"]).reset_index(drop=True)
    return entries, exits, summary


def reconstruct_memory(entries: pd.DataFrame, exits: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct last-5 closed candidate outcomes before each entry."""
    exit_by_position = exits.set_index("shadow_position_id")
    pending: list[tuple[int, int]] = []
    memory: deque[float] = deque(maxlen=5)
    rows: list[dict[str, Any]] = []
    r5_errors: list[float] = []
    for row in entries.itertuples(index=False):
        entry_ts = int(row.entry_ts_us)
        pending.sort(key=lambda item: (item[0], item[1]))
        while pending and pending[0][0] < entry_ts:
            _, position_id = pending.pop(0)
            if position_id not in exit_by_position.index:
                continue
            outcome = optional_float(exit_by_position.loc[position_id, "raw_bps_mid_fixed60"])
            if outcome is not None:
                memory.append(outcome)
        values = list(memory)
        p_bps = sum(value for value in values if value > 0.0)
        n_abs_bps = sum(-value for value in values if value < 0.0)
        delta_bps = p_bps - n_abs_bps
        energy_bps = p_bps + n_abs_bps
        r5 = None if n_abs_bps <= EPS else p_bps / n_abs_bps
        z_bps = delta_bps / math.sqrt(energy_bps + EPS) if energy_bps > EPS else 0.0
        saved_r5 = optional_float(getattr(row, "a_r5_raw", None))
        if saved_r5 is not None and r5 is not None and abs(saved_r5) < 1e6 and abs(r5) < 1e6:
            r5_errors.append(abs(saved_r5 - r5))
        rows.append(
            {
                "shadow_position_id": int(row.shadow_position_id),
                "memory_count": len(values),
                "memory_ready_reconstructed": len(values) >= 5,
                "positive_bps": p_bps,
                "negative_abs_bps": n_abs_bps,
                "delta_bps": delta_bps,
                "energy_bps": energy_bps,
                "z_bps": z_bps,
                "reconstructed_r5": r5,
            }
        )
        pending.append((int(row.due_ts_us), int(row.shadow_position_id)))
    memory_df = pd.DataFrame(rows)
    out = entries.merge(memory_df, on="shadow_position_id", how="left")
    out.attrs["r5_reconstruction_mae"] = float(np.mean(r5_errors)) if r5_errors else None
    return out


def add_prior_thresholds(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for col in [
        "delta_q30",
        "delta_q50",
        "delta_q70",
        "energy_q50",
        "energy_q70",
        "z_q50",
        "z_q70",
    ]:
        out[col] = np.nan
    by_day = {str(day): group for day, group in out.groupby("date")}
    days = sorted(by_day)
    for day in days:
        prev_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        prev = by_day.get(prev_day)
        if prev is None:
            continue
        mask = prev["memory_ready_reconstructed"].astype(bool)
        sample = prev[mask]
        thresholds = {
            "delta_q30": finite_quantile(sample["delta_bps"], 0.30),
            "delta_q50": finite_quantile(sample["delta_bps"], 0.50),
            "delta_q70": finite_quantile(sample["delta_bps"], 0.70),
            "energy_q50": finite_quantile(sample["energy_bps"], 0.50),
            "energy_q70": finite_quantile(sample["energy_bps"], 0.70),
            "z_q50": finite_quantile(sample["z_bps"], 0.50),
            "z_q70": finite_quantile(sample["z_bps"], 0.70),
        }
        for key, value in thresholds.items():
            if value is not None:
                out.loc[out["date"] == day, key] = value
    return out


def variant_specs() -> list[VariantSpec]:
    specs = [VariantSpec("M0_observed_control", "baseline")]
    for low in [0.25, 0.50, 0.75]:
        specs.append(VariantSpec(f"M1_delta_q50_low{low:g}", "delta_gate", low_mult=low))
    for low in [0.25, 0.50, 0.75]:
        for boost in [1.10, 1.25, 1.50]:
            specs.append(
                VariantSpec(
                    f"M2_delta_energy_low{low:g}_boost{boost:g}",
                    "delta_energy",
                    low_mult=low,
                    high_mult=1.0,
                    boost_mult=boost,
                )
            )
    for low in [0.50, 0.75]:
        for boost in [1.10, 1.25]:
            specs.append(
                VariantSpec(
                    f"M3_r5_energy_correct_low{low:g}_boost{boost:g}",
                    "r5_energy_correction",
                    low_mult=low,
                    boost_mult=boost,
                )
            )
    for low in [0.50, 0.75]:
        for boost in [1.10, 1.25]:
            specs.append(
                VariantSpec(
                    f"M4_z_gate_low{low:g}_boost{boost:g}",
                    "z_gate",
                    low_mult=low,
                    boost_mult=boost,
                )
            )
    return specs


def threshold(row: pd.Series, key: str) -> float | None:
    value = optional_float(row.get(key))
    return value


def control_multiplier(row: pd.Series, spec: VariantSpec) -> float:
    if spec.family == "baseline":
        return 1.0
    ready = bool(row.get("memory_ready_reconstructed"))
    if not ready:
        return 1.0
    delta = float(row.get("delta_bps") or 0.0)
    energy = float(row.get("energy_bps") or 0.0)
    z = float(row.get("z_bps") or 0.0)
    r5 = optional_float(row.get("a_r5_raw"))
    delta_q50 = threshold(row, "delta_q50")
    delta_q70 = threshold(row, "delta_q70")
    energy_q50 = threshold(row, "energy_q50")
    energy_q70 = threshold(row, "energy_q70")
    z_q50 = threshold(row, "z_q50")
    z_q70 = threshold(row, "z_q70")
    if spec.family == "delta_gate":
        if delta_q50 is None:
            return 1.0
        return spec.low_mult if delta < delta_q50 else 1.0
    if spec.family == "delta_energy":
        if delta_q50 is None or delta_q70 is None or energy_q70 is None:
            return 1.0
        if delta < delta_q50:
            return spec.low_mult
        if delta >= delta_q70 and energy >= energy_q70:
            return spec.boost_mult
        return 1.0
    if spec.family == "r5_energy_correction":
        if energy_q50 is None or delta_q70 is None or energy_q70 is None:
            return 1.0
        r5_good = r5 is not None and r5 >= 1.0
        if r5_good and energy < energy_q50:
            return spec.low_mult
        if r5_good and delta >= delta_q70 and energy >= energy_q70:
            return spec.boost_mult
        if (not r5_good) and delta >= delta_q70 and energy >= energy_q70:
            return max(0.75, spec.low_mult)
        return 1.0
    if spec.family == "z_gate":
        if z_q50 is None or z_q70 is None:
            return 1.0
        if z < z_q50:
            return spec.low_mult
        if z >= z_q70:
            return spec.boost_mult
        return 1.0
    raise ValueError(f"unknown family: {spec.family}")


def simulate_variant(
    panel: pd.DataFrame,
    exits: pd.DataFrame,
    spec: VariantSpec,
    *,
    leverage_cap: float,
    stress_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    exit_by_position = exits.set_index("shadow_position_id")
    open_positions: deque[tuple[int, int, float]] = deque()
    open_exposure = 0.0
    rows: list[dict[str, Any]] = []
    for entry in panel.sort_values(["entry_ts_us", "shadow_position_id"]).itertuples(index=False):
        entry_ts = int(entry.entry_ts_us)
        while open_positions and open_positions[0][0] <= entry_ts:
            _, position_id, actual = open_positions.popleft()
            open_exposure = max(0.0, open_exposure - actual)
        row = entry._asdict()
        position_id = int(row["shadow_position_id"])
        mult = control_multiplier(pd.Series(row), spec)
        base_requested = max(0.0, float(row.get("requested_exposure") or 0.0))
        requested = base_requested * mult
        accepted = bool(row.get("admission_accepted"))
        before = open_exposure
        if not accepted:
            actual = 0.0
            capacity_source = "admission_reject"
        else:
            free = max(0.0, float(leverage_cap) - before)
            actual = min(requested, free)
            capacity_source = str(row.get("capacity_source") or "core")
        clipped = max(0.0, requested - actual)
        skipped = actual <= EPS and requested > EPS
        after = before + actual
        if actual > EPS:
            open_exposure = after
            exit_ts = int(exit_by_position.loc[position_id, "exit_ts_us"])
            open_positions.append((exit_ts, position_id, actual))
        unit = float(exit_by_position.loc[position_id, "net_bps_after_cost"]) - float(stress_bps)
        rows.append(
            {
                "variant_id": spec.variant_id,
                "family": spec.family,
                "stress_bps": stress_bps,
                "date": row["date"],
                "shadow_position_id": position_id,
                "entry_ts_us": int(row["entry_ts_us"]),
                "cell": row["cell"],
                "side": row["side"],
                "admission_accepted": accepted,
                "control_multiplier": mult,
                "requested_exposure": requested,
                "actual_exposure": actual,
                "clipped_exposure": clipped,
                "skipped": skipped,
                "open_exposure_before": before,
                "open_exposure_after": after,
                "capacity_source": capacity_source,
                "unit_net_bps_after_stress": unit,
                "weighted_net_bps": actual * unit,
                "entry_cross_bps": float(row.get("entry_cross_bps") or 0.0),
                "a_r5_raw": optional_float(row.get("a_r5_raw")),
                "delta_bps": float(row.get("delta_bps") or 0.0),
                "energy_bps": float(row.get("energy_bps") or 0.0),
                "z_bps": float(row.get("z_bps") or 0.0),
                "memory_ready_reconstructed": bool(row.get("memory_ready_reconstructed")),
            }
        )
    out = pd.DataFrame(rows)
    daily = summarize_daily(out)
    return out, daily


def summarize_daily(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (variant_id, stress_bps, day), group in events.groupby(["variant_id", "stress_bps", "date"]):
        actual = group[group["actual_exposure"] > EPS]
        rows.append(
            {
                "variant_id": variant_id,
                "family": str(group["family"].iloc[0]),
                "stress_bps": float(stress_bps),
                "date": day,
                "entries": int(len(group)),
                "actual_entries": int(len(actual)),
                "actual_exposure": float(actual["actual_exposure"].sum()),
                "net_weighted_bps": float(actual["weighted_net_bps"].sum()),
                "mean_unit_net_bps": float(actual["unit_net_bps_after_stress"].mean()) if not actual.empty else 0.0,
                "worst_leg_bps": float(actual["unit_net_bps_after_stress"].min()) if not actual.empty else 0.0,
                "max_open_exposure": float(group["open_exposure_after"].max()) if not group.empty else 0.0,
                "clipped_entries": int((group["clipped_exposure"] > EPS).sum()),
                "skipped_entries": int(group["skipped"].sum()),
            }
        )
    return pd.DataFrame(rows)


def summarize_scope(daily: pd.DataFrame, events: pd.DataFrame, scope: str, days: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    daily_scope = daily[daily["date"].astype(str).isin(days)]
    events_scope = events[events["date"].astype(str).isin(days)]
    for (variant_id, stress_bps), group in daily_scope.groupby(["variant_id", "stress_bps"]):
        ev = events_scope[(events_scope["variant_id"] == variant_id) & (events_scope["stress_bps"] == stress_bps)]
        actual = ev[ev["actual_exposure"] > EPS]
        total_exposure = float(actual["actual_exposure"].sum())
        weighted = float(actual["weighted_net_bps"].sum())
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "family": str(group["family"].iloc[0]),
                "stress_bps": float(stress_bps),
                "days": int(group["date"].nunique()),
                "positive_days": int((group["net_weighted_bps"] > 0.0).sum()),
                "entries": int(group["entries"].sum()),
                "actual_entries": int(group["actual_entries"].sum()),
                "actual_exposure": total_exposure,
                "net_weighted_bps": weighted,
                "weighted_bps_per_exposure": weighted / total_exposure if total_exposure > EPS else 0.0,
                "mean_unit_net_bps": float(actual["unit_net_bps_after_stress"].mean()) if not actual.empty else 0.0,
                "median_unit_net_bps": float(actual["unit_net_bps_after_stress"].median()) if not actual.empty else 0.0,
                "hit_rate": float((actual["unit_net_bps_after_stress"] > 0.0).mean()) if not actual.empty else 0.0,
                "worst_day_net_weighted_bps": float(group["net_weighted_bps"].min()) if not group.empty else 0.0,
                "worst_leg_bps": float(actual["unit_net_bps_after_stress"].min()) if not actual.empty else 0.0,
                "max_open_exposure": float(group["max_open_exposure"].max()) if not group.empty else 0.0,
                "clipped_entries": int(group["clipped_entries"].sum()),
                "skipped_entries": int(group["skipped_entries"].sum()),
            }
        )
    return rows


def pareto_frontier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Maximize total/mean/worst-day while minimizing skipped/clipped."""
    out: list[dict[str, Any]] = []
    for row in rows:
        dominated = False
        for other in rows:
            if row is other:
                continue
            better_or_equal = (
                other["net_weighted_bps"] >= row["net_weighted_bps"] - EPS
                and other["weighted_bps_per_exposure"] >= row["weighted_bps_per_exposure"] - EPS
                and other["worst_day_net_weighted_bps"] >= row["worst_day_net_weighted_bps"] - EPS
                and other["positive_days"] >= row["positive_days"]
                and other["skipped_entries"] <= row["skipped_entries"]
            )
            strictly_better = (
                other["net_weighted_bps"] > row["net_weighted_bps"] + EPS
                or other["weighted_bps_per_exposure"] > row["weighted_bps_per_exposure"] + EPS
                or other["worst_day_net_weighted_bps"] > row["worst_day_net_weighted_bps"] + EPS
                or other["positive_days"] > row["positive_days"]
                or other["skipped_entries"] < row["skipped_entries"]
            )
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            tagged = dict(row)
            tagged["pareto_status"] = "frontier"
            out.append(tagged)
    return sorted(out, key=lambda item: (item["stress_bps"], -item["net_weighted_bps"]))


def markdown_table(rows: list[dict[str, Any]], fields: list[str], max_rows: int = 20) -> str:
    if not rows:
        return "_No rows._"
    lines = ["|" + "|".join(fields) + "|", "|" + "|".join(["---"] * len(fields)) + "|"]
    for row in rows[:max_rows]:
        values = []
        for field in fields:
            value = row.get(field, "")
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("|" + "|".join(values) + "|")
    return "\n".join(lines)


def write_report(
    path: Path,
    *,
    run_dir: Path,
    baseline_summary: dict[str, Any],
    r5_mae: float | None,
    summary_rows: list[dict[str, Any]],
    frontier_rows: list[dict[str, Any]],
    test_scope: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    test0 = [
        row
        for row in summary_rows
        if row["scope"] == test_scope and abs(float(row["stress_bps"])) <= EPS
    ]
    test0 = sorted(test0, key=lambda row: row["net_weighted_bps"], reverse=True)
    stress2 = [
        row
        for row in summary_rows
        if row["scope"] == test_scope and abs(float(row["stress_bps"]) - 2.0) <= EPS
    ]
    stress2 = sorted(stress2, key=lambda row: row["net_weighted_bps"], reverse=True)
    stress_ladder: list[dict[str, Any]] = []
    stress_values = sorted({float(row["stress_bps"]) for row in summary_rows if row["scope"] == test_scope})
    for stress in stress_values:
        rows = [
            row
            for row in summary_rows
            if row["scope"] == test_scope and abs(float(row["stress_bps"]) - stress) <= EPS
        ]
        rows = sorted(rows, key=lambda row: row["net_weighted_bps"], reverse=True)
        base = next((row for row in rows if row["variant_id"] == "M0_observed_control"), None)
        if not rows or base is None:
            continue
        best_row = rows[0]
        stress_ladder.append(
            {
                "stress_bps": stress,
                "best_variant": best_row["variant_id"],
                "best_net_weighted_bps": best_row["net_weighted_bps"],
                "baseline_net_weighted_bps": base["net_weighted_bps"],
                "delta_vs_baseline": best_row["net_weighted_bps"] - base["net_weighted_bps"],
                "best_worst_day": best_row["worst_day_net_weighted_bps"],
            }
        )
    frontier_test = [row for row in frontier_rows if row["scope"] == test_scope]
    baseline = next((row for row in test0 if row["variant_id"] == "M0_observed_control"), None)
    best = test0[0] if test0 else None
    lines = [
        "# CCUSDT Memory-Strength Pareto Control v0.1",
        "",
        "Status: `research_result_20260603`.",
        "",
        "Boundary: research-only. This diagnostic reuses existing fast entry candidates and does not modify Runner, Bot, Monitor, or runtime profiles.",
        "",
        "## Setup",
        "",
        f"- baseline run: `{baseline_summary.get('run_id', run_dir.name)}`",
        f"- output: `{run_dir}`",
        f"- R5 reconstruction MAE versus saved `a_r5_raw`: `{r5_mae}`",
        "- memory object: last five already closed shadow candidates, using `raw_bps_mid_fixed60` for runtime-shape reconstruction.",
        "- control object: `requested_exposure_new = requested_exposure_old * psi(Delta_bps, Energy_bps, Z_bps)`.",
        "",
        "## Main Test Scope, Stress 0",
        "",
        markdown_table(
            test0,
            [
                "variant_id",
                "family",
                "actual_entries",
                "actual_exposure",
                "net_weighted_bps",
                "weighted_bps_per_exposure",
                "positive_days",
                "worst_day_net_weighted_bps",
                "skipped_entries",
            ],
            max_rows=12,
        ),
        "",
        "## Stress +2 bps",
        "",
        markdown_table(
            stress2,
            [
                "variant_id",
                "family",
                "actual_entries",
                "actual_exposure",
                "net_weighted_bps",
                "weighted_bps_per_exposure",
                "positive_days",
                "worst_day_net_weighted_bps",
                "skipped_entries",
            ],
            max_rows=12,
        ),
        "",
        "## Stress Ladder",
        "",
        markdown_table(
            stress_ladder,
            [
                "stress_bps",
                "best_variant",
                "best_net_weighted_bps",
                "baseline_net_weighted_bps",
                "delta_vs_baseline",
                "best_worst_day",
            ],
            max_rows=10,
        ),
        "",
        "## Pareto Frontier",
        "",
        markdown_table(
            frontier_test,
            [
                "stress_bps",
                "variant_id",
                "family",
                "net_weighted_bps",
                "weighted_bps_per_exposure",
                "worst_day_net_weighted_bps",
                "positive_days",
            ],
            max_rows=20,
        ),
        "",
        "## Read",
        "",
    ]
    if baseline and best:
        lines.extend(
            [
                f"- Baseline test total: `{baseline['net_weighted_bps']:.4f}` weighted bps.",
                f"- Best stress-0 test total: `{best['variant_id']}` with `{best['net_weighted_bps']:.4f}` weighted bps.",
                f"- Delta versus baseline: `{best['net_weighted_bps'] - baseline['net_weighted_bps']:.4f}` weighted bps.",
            ]
        )
        if best["variant_id"] == "M0_observed_control":
            lines.append("- In this pass, memory-strength control did not beat the observed old control on raw stress-0 total.")
        else:
            lines.append("- The best row supports testing Delta/Energy as a sizing control rather than as a new entry trigger.")
    lines.extend(
        [
            "- This diagnostic is not a strategy promotion. It is a control-function screen before any Bot profile change.",
            "- Any candidate must still pass strict replay identity, L2 depth capacity, and exit/decay diagnostics.",
            "",
            "## Outputs",
            "",
            f"- `{run_dir / 'memory_control_event_panel.parquet'}`",
            f"- `{run_dir / 'variant_summary.csv'}`",
            f"- `{run_dir / 'variant_daily.csv'}`",
            f"- `{run_dir / 'pareto_frontier.csv'}`",
            f"- `{run_dir / 'summary.json'}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    baseline_run = args.baseline_run_dir
    if not baseline_run.is_absolute():
        baseline_run = repo_root / baseline_run
    if args.out_dir:
        out_dir = args.out_dir if args.out_dir.is_absolute() else repo_root / args.out_dir
    else:
        run_id = f"ccusdt_{args.test_from_date}_{args.test_to_date}_v0_1".replace("-", "")
        out_dir = repo_root / DEFAULT_OUT_ROOT / run_id
    stress_values = [float(item) for item in str(args.stress_bps).split(",") if item.strip()]
    entries, exits, baseline_summary = load_baseline(baseline_run)
    panel = add_prior_thresholds(reconstruct_memory(entries, exits))
    r5_mae = panel.attrs.get("r5_reconstruction_mae")
    all_events: list[pd.DataFrame] = []
    all_daily: list[pd.DataFrame] = []
    for spec in variant_specs():
        for stress in stress_values:
            events, daily = simulate_variant(panel, exits, spec, leverage_cap=args.leverage_cap, stress_bps=stress)
            all_events.append(events)
            all_daily.append(daily)
    events_df = pd.concat(all_events, ignore_index=True)
    daily_df = pd.concat(all_daily, ignore_index=True)
    all_days = set(str(day) for day in panel["date"].unique())
    test_days = set(date_range(args.test_from_date, args.test_to_date))
    summary_rows: list[dict[str, Any]] = []
    summary_rows.extend(summarize_scope(daily_df, events_df, "all_dates", all_days))
    test_scope = f"test_{args.test_from_date}_{args.test_to_date}"
    summary_rows.extend(summarize_scope(daily_df, events_df, test_scope, test_days))
    frontier_rows: list[dict[str, Any]] = []
    for (scope, stress), rows_df in pd.DataFrame(summary_rows).groupby(["scope", "stress_bps"]):
        rows = rows_df.to_dict("records")
        frontier_rows.extend(pareto_frontier(rows))
    out_dir.mkdir(parents=True, exist_ok=True)
    events_df.to_parquet(out_dir / "memory_control_event_panel.parquet", index=False)
    daily_df.to_csv(out_dir / "variant_daily.csv", index=False)
    write_csv(out_dir / "variant_summary.csv", summary_rows)
    write_csv(out_dir / "pareto_frontier.csv", frontier_rows)
    summary = {
        "schema_id": "ccusdt_memory_strength_pareto_control_summary_v0_1",
        "ok": True,
        "baseline_run_dir": str(baseline_run),
        "baseline_run_id": baseline_summary.get("run_id", baseline_run.name),
        "out_dir": str(out_dir),
        "entries": int(len(entries)),
        "exits": int(len(exits)),
        "variant_count": len(variant_specs()),
        "stress_bps": stress_values,
        "test_from_date": args.test_from_date,
        "test_to_date": args.test_to_date,
        "leverage_cap": args.leverage_cap,
        "r5_reconstruction_mae": r5_mae,
        "boundary": "research_only_reweights_existing_fast_candidates_no_runtime_change",
        "outputs": {
            "event_panel": str(out_dir / "memory_control_event_panel.parquet"),
            "variant_summary": str(out_dir / "variant_summary.csv"),
            "variant_daily": str(out_dir / "variant_daily.csv"),
            "pareto_frontier": str(out_dir / "pareto_frontier.csv"),
            "report": str(repo_root / args.report_path),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    write_report(
        report_path,
        run_dir=out_dir,
        baseline_summary=baseline_summary,
        r5_mae=r5_mae,
        summary_rows=summary_rows,
        frontier_rows=frontier_rows,
        test_scope=test_scope,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

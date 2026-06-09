#!/usr/bin/env python
"""Aggregate the q70 entry-spread admission strict-taker experiment."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


DIAG_DIR = Path(__file__).resolve().parent

PROFILES = {
    "core_only": {
        "fast_run_id": "fast_adm_q70_core_only_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_adm_q70_core_only",
        "baseline_strict": 638.2147,
    },
    "idle01_g0.5": {
        "fast_run_id": "fast_adm_q70_idle01_g05_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_adm_q70_idle01_g05",
        "baseline_strict": 649.4415,
    },
    "idle01_g0.75": {
        "fast_run_id": "fast_adm_q70_idle01_g075_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_adm_q70_idle01_g075",
        "baseline_strict": 655.0549,
    },
    "idle01_g1": {
        "fast_run_id": "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_adm_q70_idle01_g1",
        "baseline_strict": 656.7311,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--strict-run-suffix", default="20260521")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    left = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out = []
    current = left
    while current <= right:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def run_consistency(
    repo_root: Path,
    profile: str,
    spec: dict[str, Any],
    day: str,
    out_dir: Path,
    strict_run_suffix: str,
    force: bool,
) -> dict[str, Any]:
    day_compact = day.replace("-", "")
    fast_dir = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / "experiments" / spec["fast_run_id"]
    strict_dir = (
        repo_root
        / "systems"
        / "ccusdt_replay_exchange"
        / "runs"
        / f"{spec['strict_prefix']}_{day_compact}_{strict_run_suffix}"
    )
    pair_dir = out_dir / f"{profile}_{day}"
    summary_path = pair_dir / "summary.json"
    if not summary_path.exists() or force:
        cmd = [
            sys.executable,
            str(DIAG_DIR / "fast_vs_strict_consistency.py"),
            "--repo-root",
            str(repo_root),
            "--fast-run-dir",
            str(fast_dir),
            "--strict-audit-dir",
            str(strict_dir),
            "--date",
            day,
            "--strict-source",
            "events",
            "--out-dir",
            str(pair_dir),
        ]
        subprocess.run(cmd, check=True)
    result = read_json(summary_path)
    result["strict_run"] = read_json(strict_dir / "summary.json")
    return result


def fast_daily_rows(repo_root: Path, run_id: str) -> dict[str, dict[str, Any]]:
    path = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / "experiments" / run_id / "daily.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["date"]: row for row in csv.DictReader(handle)}


def rejected_potential(repo_root: Path, run_id: str) -> dict[str, dict[str, float]]:
    path = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / "experiments" / run_id / "exits.parquet"
    df = pq.read_table(path).to_pandas()
    out: dict[str, dict[str, float]] = {}
    for day, group in df.groupby("date"):
        rejected = group[group["capacity_source"] == "admission_reject"]
        potential = float((rejected["requested_exposure"] * rejected["raw_bps"]).sum()) if len(rejected) else 0.0
        out[str(day)] = {
            "rejected_count": float(len(rejected)),
            "rejected_requested_exposure": float(rejected["requested_exposure"].sum()) if len(rejected) else 0.0,
            "missed_requested_taker_pnl_bps": potential,
            "avoided_requested_loss_bps": max(0.0, -potential),
        }
    return out


def flatten_daily(profile: str, day: str, result: dict[str, Any], fast_daily: dict[str, Any], rejected: dict[str, float]) -> dict[str, Any]:
    fill = result.get("round_trip_fill_pnl_decomposition") or {}
    lag = result.get("arrival_lag_summary") or {}
    strict_run = result.get("strict_run") or {}
    timing = strict_run.get("timing_ms") or {}
    return {
        "profile": profile,
        "date": day,
        "ok": bool(result.get("ok")),
        "rows_compared": result.get("rows_compared"),
        "entries": fast_daily.get("entries"),
        "accepted": fast_daily.get("admission_accepted_entries"),
        "rejected": fast_daily.get("admission_rejected_entries"),
        "actual_entries": sum_actual_entries_placeholder(fast_daily),
        "requested_exposure": fast_daily.get("requested_exposure"),
        "actual_exposure": fast_daily.get("actual_exposure"),
        "clipped_exposure": fast_daily.get("clipped_exposure"),
        "clipped_entries_including_admission": fast_daily.get("clipped_entries"),
        "skipped_entries_including_admission": fast_daily.get("skipped_entries"),
        "strict_taker_bps": fill.get("weighted_sim_capacity_net_bps"),
        "fast_quote_taker_bps": fill.get("weighted_fast_capacity_raw_bps"),
        "fast_vs_strict_delta_bps": fill.get("weighted_capacity_delta_bps"),
        "entry_cost_bps": fill.get("weighted_capacity_entry_execution_cost_bps"),
        "exit_cost_bps": fill.get("weighted_capacity_exit_execution_cost_bps"),
        "total_cost_bps": fill.get("weighted_capacity_total_execution_cost_bps"),
        "arrival_quote_lag_count": lag.get("arrival_quote_lag_count"),
        "arrival_stream_lag_count": lag.get("arrival_stream_lag_count"),
        "orders": strict_run.get("orders_submitted"),
        "fills": strict_run.get("fills_created"),
        "wall_ms": timing.get("total_elapsed_wall_ms"),
        "events_per_sec": timing.get("events_per_sec"),
        **rejected,
    }


def sum_actual_entries_placeholder(row: dict[str, Any]) -> str:
    # daily.csv stores exposure, not actual-entry count. The run-level summary
    # carries the exact count; daily keeps this column explicit rather than
    # silently inventing a proxy.
    return ""


def numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir if args.out_dir.is_absolute() else repo_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    days = date_range(args.from_date, args.to_date)
    daily_rows: list[dict[str, Any]] = []
    nested: dict[str, Any] = {}
    for profile, spec in PROFILES.items():
        fast_daily = fast_daily_rows(repo_root, spec["fast_run_id"])
        rejected_by_day = rejected_potential(repo_root, spec["fast_run_id"])
        nested[profile] = {}
        for day in days:
            result = run_consistency(
                repo_root,
                profile,
                spec,
                day,
                out_dir,
                args.strict_run_suffix,
                args.force,
            )
            nested[profile][day] = result
            daily_rows.append(
                flatten_daily(
                    profile,
                    day,
                    result,
                    fast_daily.get(day, {}),
                    rejected_by_day.get(day, {}),
                )
            )
    totals: list[dict[str, Any]] = []
    core_total = 0.0
    totals_by_profile: dict[str, float] = {}
    for profile, spec in PROFILES.items():
        rows = [row for row in daily_rows if row["profile"] == profile]
        strict_total = sum(numeric(row["strict_taker_bps"]) for row in rows)
        totals_by_profile[profile] = strict_total
        if profile == "core_only":
            core_total = strict_total
        totals.append(
            {
                "profile": profile,
                "ok": all(bool(row["ok"]) for row in rows),
                "rows_compared": sum(int(numeric(row["rows_compared"])) for row in rows),
                "entries": sum(int(numeric(row["entries"])) for row in rows),
                "accepted": sum(int(numeric(row["accepted"])) for row in rows),
                "rejected": sum(int(numeric(row["rejected"])) for row in rows),
                "requested_exposure": sum(numeric(row["requested_exposure"]) for row in rows),
                "actual_exposure": sum(numeric(row["actual_exposure"]) for row in rows),
                "clipped_exposure": sum(numeric(row["clipped_exposure"]) for row in rows),
                "strict_taker_bps": strict_total,
                "strict_delta_vs_core": strict_total - core_total if profile != "core_only" else 0.0,
                "strict_delta_vs_no_admission_same_profile": strict_total - float(spec["baseline_strict"]),
                "fast_quote_taker_bps": sum(numeric(row["fast_quote_taker_bps"]) for row in rows),
                "fast_vs_strict_delta_bps": sum(numeric(row["fast_vs_strict_delta_bps"]) for row in rows),
                "entry_cost_bps": sum(numeric(row["entry_cost_bps"]) for row in rows),
                "exit_cost_bps": sum(numeric(row["exit_cost_bps"]) for row in rows),
                "total_cost_bps": sum(numeric(row["total_cost_bps"]) for row in rows),
                "missed_requested_taker_pnl_bps": sum(numeric(row["missed_requested_taker_pnl_bps"]) for row in rows),
                "avoided_requested_loss_bps": sum(numeric(row["avoided_requested_loss_bps"]) for row in rows),
                "worst_day_strict_taker_bps": min(numeric(row["strict_taker_bps"]) for row in rows),
                "positive_days": sum(1 for row in rows if numeric(row["strict_taker_bps"]) > 0.0),
                "orders": sum(int(numeric(row["orders"])) for row in rows),
                "fills": sum(int(numeric(row["fills"])) for row in rows),
                "arrival_quote_lag_count": sum(int(numeric(row["arrival_quote_lag_count"])) for row in rows),
                "arrival_stream_lag_count": sum(int(numeric(row["arrival_stream_lag_count"])) for row in rows),
            }
        )
    # Recompute deltas after core total is known.
    for row in totals:
        row["strict_delta_vs_core"] = float(row["strict_taker_bps"]) - core_total
    summary = {
        "schema_id": "ccusdt_admission_strategy_report_v1",
        "ok": all(bool(row["ok"]) for row in daily_rows),
        "from_date": args.from_date,
        "to_date": args.to_date,
        "admission_profile": "entry_spread_q70_v1",
        "threshold_source": "prior-day decision_frame spread_bps/2 q70",
        "profiles": list(PROFILES),
        "daily": daily_rows,
        "totals": totals,
        "nested_summary": nested,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(out_dir / "daily.csv", daily_rows)
    write_csv(out_dir / "totals.csv", totals)
    print(json.dumps({k: summary[k] for k in ["schema_id", "ok", "from_date", "to_date", "totals"]}, indent=2))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Aggregate fast-vs-strict profile matrix checks for CCUSDT top-of-book audit."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


DIAG_DIR = Path(__file__).resolve().parent

PROFILES = {
    "core_only": {
        "fast_run_id": "fast_profile_core_only_fixed60_mid_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_core_only",
    },
    "idle01_g0.5": {
        "fast_run_id": "fast_profile_idle01_g05_fixed60_mid_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_idle01_g05",
    },
    "idle01_g0.75": {
        "fast_run_id": "fast_profile_idle01_g075_fixed60_mid_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_idle01_g075",
    },
    "idle01_g1": {
        "fast_run_id": "fast_profile_idle01_g1_fixed60_mid_20260516_18_20260521",
        "strict_prefix": "det_fast_clock_idle01_g1",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--strict-run-suffix", default="20260521_profile")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    left = date.fromisoformat(start)
    right = date.fromisoformat(end)
    days: list[str] = []
    current = left
    while current <= right:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return raw if isinstance(raw, dict) else {}


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
    profile_spec: dict[str, str],
    day: str,
    out_dir: Path,
    strict_run_suffix: str,
    force: bool,
) -> dict[str, Any]:
    day_compact = day.replace("-", "")
    fast_dir = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / "experiments" / profile_spec["fast_run_id"]
    strict_dir = (
        repo_root
        / "systems"
        / "ccusdt_replay_exchange"
        / "runs"
        / f"{profile_spec['strict_prefix']}_{day_compact}_{strict_run_suffix}"
    )
    pair_dir = out_dir / f"{profile}_{day}"
    summary_path = pair_dir / "summary.json"
    if summary_path.exists() and not force:
        result = read_json(summary_path)
        result["strict_run"] = selected_strict_run_summary(strict_dir)
        return result
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
    result["strict_run"] = selected_strict_run_summary(strict_dir)
    return result


def selected_strict_run_summary(strict_dir: Path) -> dict[str, Any]:
    summary_path = strict_dir / "summary.json"
    if not summary_path.exists():
        return {}
    raw = read_json(summary_path)
    timing = raw.get("timing_ms") or {}
    return {
        "run_id": raw.get("run_id"),
        "public_stream_mode": raw.get("public_stream_mode"),
        "fill_model": raw.get("fill_model"),
        "profile_manifest_hash": raw.get("profile_manifest_hash"),
        "events_seen": raw.get("events_seen"),
        "intents_created": raw.get("intents_created"),
        "orders_submitted": raw.get("orders_submitted"),
        "fills_created": raw.get("fills_created"),
        "bridge_errors": raw.get("bridge_errors"),
        "arrival_quote_lag_count": raw.get("arrival_quote_lag_count"),
        "arrival_stream_lag_count": raw.get("arrival_stream_lag_count"),
        "market_read_ms": timing.get("market_read_ms"),
        "total_elapsed_wall_ms": timing.get("total_elapsed_wall_ms"),
        "events_per_sec": timing.get("events_per_sec"),
    }


def flatten_summary(profile: str, day: str, result: dict[str, Any]) -> dict[str, Any]:
    fill = result.get("round_trip_fill_pnl_decomposition") or {}
    entry = result.get("fill_pnl_decomposition") or {}
    lag = result.get("arrival_lag_summary") or {}
    strict_run = result.get("strict_run") or {}
    return {
        "profile": profile,
        "date": day,
        "ok": bool(result.get("ok")),
        "rows_compared": result.get("rows_compared"),
        "fast_entries": result.get("fast_entries"),
        "strict_entries": result.get("strict_entries"),
        "strict_intents_created": strict_run.get("intents_created"),
        "strict_orders_submitted": strict_run.get("orders_submitted"),
        "strict_fills_created": strict_run.get("fills_created"),
        "strict_bridge_errors": strict_run.get("bridge_errors"),
        "row_mismatch_count": result.get("row_mismatch_count"),
        "arrival_quote_lag_count": lag.get("arrival_quote_lag_count"),
        "arrival_stream_lag_count": lag.get("arrival_stream_lag_count"),
        "entry_fills_matched": entry.get("fills_matched"),
        "round_trips_matched": fill.get("round_trips_matched"),
        "fast_capacity_raw_bps": fill.get("weighted_fast_capacity_raw_bps"),
        "strict_capacity_net_bps": fill.get("weighted_sim_capacity_net_bps"),
        "capacity_delta_bps": fill.get("weighted_capacity_delta_bps"),
        "entry_execution_cost_bps": fill.get("weighted_capacity_entry_execution_cost_bps"),
        "exit_execution_cost_bps": fill.get("weighted_capacity_exit_execution_cost_bps"),
        "total_execution_cost_bps": fill.get("weighted_capacity_total_execution_cost_bps"),
        "latency_slippage_bps": fill.get("weighted_capacity_total_latency_slippage_bps"),
        "pressure_bps": fill.get("weighted_capacity_pressure_bps"),
        "extra_slippage_bps": fill.get("weighted_capacity_extra_slippage_bps"),
        "unexplained_delta_bps": fill.get("weighted_capacity_unexplained_delta_bps"),
        "mean_total_execution_cost_bps": fill.get("mean_total_execution_cost_bps"),
        "market_read_ms": strict_run.get("market_read_ms"),
        "total_elapsed_wall_ms": strict_run.get("total_elapsed_wall_ms"),
        "events_per_sec": strict_run.get("events_per_sec"),
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir if args.out_dir.is_absolute() else repo_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    nested: dict[str, Any] = {}
    for profile, spec in PROFILES.items():
        nested[profile] = {}
        for day in date_range(args.from_date, args.to_date):
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
            rows.append(flatten_summary(profile, day, result))
    totals: list[dict[str, Any]] = []
    for profile in PROFILES:
        profile_rows = [row for row in rows if row["profile"] == profile]
        totals.append(
            {
                "profile": profile,
                "ok": all(bool(row["ok"]) for row in profile_rows),
                "rows_compared": sum(int(row["rows_compared"] or 0) for row in profile_rows),
                "fast_entries": sum(int(row["fast_entries"] or 0) for row in profile_rows),
                "strict_entries": sum(int(row["strict_entries"] or 0) for row in profile_rows),
                "strict_intents_created": sum(int(row["strict_intents_created"] or 0) for row in profile_rows),
                "strict_orders_submitted": sum(int(row["strict_orders_submitted"] or 0) for row in profile_rows),
                "strict_fills_created": sum(int(row["strict_fills_created"] or 0) for row in profile_rows),
                "strict_bridge_errors": sum(int(row["strict_bridge_errors"] or 0) for row in profile_rows),
                "fast_capacity_raw_bps": sum(float(row["fast_capacity_raw_bps"] or 0.0) for row in profile_rows),
                "strict_capacity_net_bps": sum(float(row["strict_capacity_net_bps"] or 0.0) for row in profile_rows),
                "capacity_delta_bps": sum(float(row["capacity_delta_bps"] or 0.0) for row in profile_rows),
                "entry_execution_cost_bps": sum(float(row["entry_execution_cost_bps"] or 0.0) for row in profile_rows),
                "exit_execution_cost_bps": sum(float(row["exit_execution_cost_bps"] or 0.0) for row in profile_rows),
                "total_execution_cost_bps": sum(float(row["total_execution_cost_bps"] or 0.0) for row in profile_rows),
                "latency_slippage_bps": sum(float(row["latency_slippage_bps"] or 0.0) for row in profile_rows),
                "pressure_bps": sum(float(row["pressure_bps"] or 0.0) for row in profile_rows),
                "extra_slippage_bps": sum(float(row["extra_slippage_bps"] or 0.0) for row in profile_rows),
                "unexplained_delta_bps": sum(float(row["unexplained_delta_bps"] or 0.0) for row in profile_rows),
            }
        )
    summary = {
        "schema_id": "ccusdt_profile_matrix_report_v1",
        "ok": all(bool(row["ok"]) for row in rows),
        "from_date": args.from_date,
        "to_date": args.to_date,
        "profiles": list(PROFILES),
        "rows": rows,
        "totals": totals,
        "nested_summary": nested,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(out_dir / "daily_profile_summary.csv", rows)
    write_csv(out_dir / "profile_totals.csv", totals)
    console_summary = {
        "schema_id": summary["schema_id"],
        "ok": summary["ok"],
        "from_date": args.from_date,
        "to_date": args.to_date,
        "profiles": list(PROFILES),
        "summary_json": str(out_dir / "summary.json"),
        "daily_profile_summary_csv": str(out_dir / "daily_profile_summary.csv"),
        "profile_totals_csv": str(out_dir / "profile_totals.csv"),
        "totals": totals,
    }
    print(json.dumps(console_summary, indent=2))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

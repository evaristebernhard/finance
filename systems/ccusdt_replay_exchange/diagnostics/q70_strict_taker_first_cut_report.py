#!/usr/bin/env python
"""Aggregate the first q70 strict-taker strategy-optimization cut.

This report intentionally stays on the runtime-safe path:

- strategy input comes from market-derived decision_frame_v1 cache;
- strict fills come from Runner event logs;
- rejected-entry opportunity cost is a quote-frame top-of-book counterfactual,
  not a legacy research label.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


DIAG_DIR = Path(__file__).resolve().parent

PROFILES: dict[str, dict[str, Any]] = {
    "core_only": {
        "fixed_fast": "fast_adm_q70_core_only_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "peak_fast": "fast_adm_q70_core_only_peakguard_taker_quoteidx_v1_20260516_18_20260521",
        "fixed_strict_prefix": "det_fast_clock_adm_q70_core_only",
        "peak_strict_prefix": "det_fast_clock_adm_q70_core_only_peakguard",
        "no_admission_fixed60_strict": 638.2147,
    },
    "idle01_g0.5": {
        "fixed_fast": "fast_adm_q70_idle01_g05_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "peak_fast": "fast_adm_q70_idle01_g05_peakguard_taker_quoteidx_v1_20260516_18_20260521",
        "fixed_strict_prefix": "det_fast_clock_adm_q70_idle01_g05",
        "peak_strict_prefix": "det_fast_clock_adm_q70_idle01_g05_peakguard",
        "no_admission_fixed60_strict": 649.4415,
    },
    "idle01_g0.75": {
        "fixed_fast": "fast_adm_q70_idle01_g075_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "peak_fast": "fast_adm_q70_idle01_g075_peakguard_taker_quoteidx_v1_20260516_18_20260521",
        "fixed_strict_prefix": "det_fast_clock_adm_q70_idle01_g075",
        "peak_strict_prefix": "det_fast_clock_adm_q70_idle01_g075_peakguard",
        "no_admission_fixed60_strict": 655.0549,
    },
    "idle01_g1": {
        "fixed_fast": "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_v2_20260516_18_20260521",
        "peak_fast": "fast_adm_q70_idle01_g1_peakguard_taker_quoteidx_v1_20260516_18_20260521",
        "fixed_strict_prefix": "det_fast_clock_adm_q70_idle01_g1",
        "peak_strict_prefix": "det_fast_clock_adm_q70_idle01_g1_peakguard",
        "no_admission_fixed60_strict": 656.7311,
    },
}

EXIT_PROFILES = {
    "fixed60_taker": {"fast_key": "fixed_fast", "strict_prefix_key": "fixed_strict_prefix"},
    "peakguard_taker_v1": {"fast_key": "peak_fast", "strict_prefix_key": "peak_strict_prefix"},
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
    current = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out: list[str] = []
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


def numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def run_consistency(
    *,
    repo_root: Path,
    out_dir: Path,
    profile: str,
    exit_profile: str,
    fast_run_id: str,
    strict_prefix: str,
    day: str,
    strict_run_suffix: str,
    force: bool,
) -> dict[str, Any]:
    day_compact = day.replace("-", "")
    fast_dir = repo_root / "systems/ccusdt_replay_exchange/runs/experiments" / fast_run_id
    strict_dir = repo_root / "systems/ccusdt_replay_exchange/runs" / f"{strict_prefix}_{day_compact}_{strict_run_suffix}"
    pair_dir = out_dir / "consistency" / exit_profile / f"{profile}_{day}"
    summary_path = pair_dir / "summary.json"
    if force or not summary_path.exists():
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
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    result = read_json(summary_path)
    result["strict_run"] = read_json(strict_dir / "summary.json")
    return result


def fast_daily(repo_root: Path, run_id: str) -> dict[str, dict[str, Any]]:
    path = repo_root / "systems/ccusdt_replay_exchange/runs/experiments" / run_id / "daily.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["date"]: row for row in csv.DictReader(handle)}


def fast_exit_stats(repo_root: Path, run_id: str) -> dict[str, dict[str, float]]:
    path = repo_root / "systems/ccusdt_replay_exchange/runs/experiments" / run_id / "exits.parquet"
    df = pq.read_table(path).to_pandas()
    out: dict[str, dict[str, float]] = {}
    for day, group in df.groupby("date"):
        rejected = group[group["capacity_source"] == "admission_reject"]
        traded = group[group["actual_exposure"] > 1e-12]
        release = traded[traded["exit_reason"] == "release_drawdown"]
        by_reason = Counter(str(item) for item in group["exit_reason"])
        out[str(day)] = {
            "rejected_count": float(len(rejected)),
            "rejected_requested_exposure": float(rejected["requested_exposure"].sum()) if len(rejected) else 0.0,
            "missed_counterfactual_taker_pnl_bps": (
                float((rejected["requested_exposure"] * rejected["raw_bps"]).sum()) if len(rejected) else 0.0
            ),
            "avoided_counterfactual_loss_bps": (
                max(0.0, -float((rejected["requested_exposure"] * rejected["raw_bps"]).sum()))
                if len(rejected)
                else 0.0
            ),
            "release_drawdown_exits": float(len(release)),
            "release_drawdown_actual_exposure": float(release["actual_exposure"].sum()) if len(release) else 0.0,
            "release_drawdown_net_weighted_bps": float(release["net_weighted_bps"].sum()) if len(release) else 0.0,
            "fixed_60s_exits": float(by_reason.get("fixed_60s", 0)),
            "fixed60_mid_zero_actual_rows": float(by_reason.get("fixed60_mid", 0)),
        }
    return out


def strict_lot_audit(strict_run_dir: Path) -> dict[str, Any]:
    path = strict_run_dir / "events.ndjson"
    exit_ids: list[str] = []
    opened_lots: set[str] = set()
    closed_lots: set[str] = set()
    early_exit_ids: set[str] = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = json.loads(line)
                event_type = event.get("event_type")
                payload = event.get("payload") or {}
                if event_type == "order_intent":
                    order = payload.get("order") or {}
                    client_id = str(order.get("client_order_id") or "")
                    if client_id.startswith("shadow-exit-"):
                        exit_ids.append(client_id)
                        signal = payload.get("shadow_signal") or {}
                        for closed in signal.get("closed_now") or []:
                            if numeric(closed.get("held_us")) < numeric(closed.get("fixed_exit_us") or 60_000_000):
                                early_exit_ids.add(client_id)
                elif event_type == "position_opened":
                    lot = (payload.get("position_lot") or {}).get("position_lot_id")
                    if lot:
                        opened_lots.add(str(lot))
                elif event_type in {"position_closed", "position_partial_closed"}:
                    lot = payload.get("position_lot_id")
                    if lot and event_type == "position_closed":
                        closed_lots.add(str(lot))
    return {
        "strict_exit_intents": len(exit_ids),
        "strict_duplicate_exit_intents": len(exit_ids) - len(set(exit_ids)),
        "strict_position_opened": len(opened_lots),
        "strict_position_closed": len(closed_lots),
        "strict_unclosed_lots": len(opened_lots - closed_lots),
        "strict_early_exit_intents": len(early_exit_ids),
    }


def flatten_daily(
    *,
    profile: str,
    exit_profile: str,
    day: str,
    result: dict[str, Any],
    daily: dict[str, Any],
    exit_stats: dict[str, float],
    lot_audit: dict[str, Any],
) -> dict[str, Any]:
    fill = result.get("round_trip_fill_pnl_decomposition") or {}
    lag = result.get("arrival_lag_summary") or {}
    strict_run = result.get("strict_run") or {}
    timing = strict_run.get("timing_ms") or {}
    account = strict_run.get("final_account") or {}
    return {
        "profile": profile,
        "exit_profile": exit_profile,
        "date": day,
        "ok": bool(result.get("ok")),
        "rows_compared": result.get("rows_compared"),
        "entries": daily.get("entries"),
        "accepted": daily.get("admission_accepted_entries"),
        "rejected": daily.get("admission_rejected_entries"),
        "requested_exposure": daily.get("requested_exposure"),
        "actual_exposure": daily.get("actual_exposure"),
        "clipped_exposure": daily.get("clipped_exposure"),
        "clipped_entries": daily.get("clipped_entries"),
        "skipped_entries": daily.get("skipped_entries"),
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
        "residual_qty": account.get("position_qty"),
        "wall_ms": timing.get("total_elapsed_wall_ms"),
        "events_per_sec": timing.get("events_per_sec"),
        **exit_stats,
        **lot_audit,
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir if args.out_dir.is_absolute() else repo_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    days = date_range(args.from_date, args.to_date)

    daily_rows: list[dict[str, Any]] = []
    for profile, spec in PROFILES.items():
        for exit_profile, exit_spec in EXIT_PROFILES.items():
            fast_run_id = spec[exit_spec["fast_key"]]
            strict_prefix = spec[exit_spec["strict_prefix_key"]]
            daily_by_day = fast_daily(repo_root, fast_run_id)
            stats_by_day = fast_exit_stats(repo_root, fast_run_id)
            for day in days:
                result = run_consistency(
                    repo_root=repo_root,
                    out_dir=out_dir,
                    profile=profile,
                    exit_profile=exit_profile,
                    fast_run_id=fast_run_id,
                    strict_prefix=strict_prefix,
                    day=day,
                    strict_run_suffix=args.strict_run_suffix,
                    force=args.force,
                )
                day_compact = day.replace("-", "")
                strict_dir = (
                    repo_root
                    / "systems/ccusdt_replay_exchange/runs"
                    / f"{strict_prefix}_{day_compact}_{args.strict_run_suffix}"
                )
                daily_rows.append(
                    flatten_daily(
                        profile=profile,
                        exit_profile=exit_profile,
                        day=day,
                        result=result,
                        daily=daily_by_day.get(day, {}),
                        exit_stats=stats_by_day.get(day, {}),
                        lot_audit=strict_lot_audit(strict_dir),
                    )
                )

    totals: list[dict[str, Any]] = []
    totals_by_key: dict[tuple[str, str], float] = {}
    for row in daily_rows:
        key = (row["profile"], row["exit_profile"])
        totals_by_key[key] = totals_by_key.get(key, 0.0) + numeric(row["strict_taker_bps"])

    for exit_profile in EXIT_PROFILES:
        core_total = totals_by_key.get(("core_only", exit_profile), 0.0)
        for profile, spec in PROFILES.items():
            rows = [r for r in daily_rows if r["profile"] == profile and r["exit_profile"] == exit_profile]
            strict_total = totals_by_key[(profile, exit_profile)]
            fixed_total = totals_by_key.get((profile, "fixed60_taker"), 0.0)
            totals.append(
                {
                    "profile": profile,
                    "exit_profile": exit_profile,
                    "ok": all(bool(row["ok"]) for row in rows),
                    "rows_compared": sum(int(numeric(row["rows_compared"])) for row in rows),
                    "entries": sum(int(numeric(row["entries"])) for row in rows),
                    "accepted": sum(int(numeric(row["accepted"])) for row in rows),
                    "rejected": sum(int(numeric(row["rejected"])) for row in rows),
                    "requested_exposure": sum(numeric(row["requested_exposure"]) for row in rows),
                    "actual_exposure": sum(numeric(row["actual_exposure"]) for row in rows),
                    "clipped_exposure": sum(numeric(row["clipped_exposure"]) for row in rows),
                    "clipped_entries": sum(int(numeric(row["clipped_entries"])) for row in rows),
                    "skipped_entries": sum(int(numeric(row["skipped_entries"])) for row in rows),
                    "strict_taker_bps": strict_total,
                    "strict_delta_vs_core": strict_total - core_total if profile != "core_only" else 0.0,
                    "strict_delta_vs_fixed60_same_profile": strict_total - fixed_total,
                    "strict_delta_vs_no_admission_fixed60_same_profile": (
                        strict_total - float(spec["no_admission_fixed60_strict"])
                    ),
                    "fast_quote_taker_bps": sum(numeric(row["fast_quote_taker_bps"]) for row in rows),
                    "fast_vs_strict_delta_bps": sum(numeric(row["fast_vs_strict_delta_bps"]) for row in rows),
                    "entry_cost_bps": sum(numeric(row["entry_cost_bps"]) for row in rows),
                    "exit_cost_bps": sum(numeric(row["exit_cost_bps"]) for row in rows),
                    "total_cost_bps": sum(numeric(row["total_cost_bps"]) for row in rows),
                    "missed_counterfactual_taker_pnl_bps": sum(
                        numeric(row["missed_counterfactual_taker_pnl_bps"]) for row in rows
                    ),
                    "avoided_counterfactual_loss_bps": sum(
                        numeric(row["avoided_counterfactual_loss_bps"]) for row in rows
                    ),
                    "release_drawdown_exits": sum(int(numeric(row["release_drawdown_exits"])) for row in rows),
                    "release_drawdown_actual_exposure": sum(
                        numeric(row["release_drawdown_actual_exposure"]) for row in rows
                    ),
                    "release_drawdown_net_weighted_bps": sum(
                        numeric(row["release_drawdown_net_weighted_bps"]) for row in rows
                    ),
                    "worst_day_strict_taker_bps": min(numeric(row["strict_taker_bps"]) for row in rows),
                    "positive_days": sum(1 for row in rows if numeric(row["strict_taker_bps"]) > 0.0),
                    "orders": sum(int(numeric(row["orders"])) for row in rows),
                    "fills": sum(int(numeric(row["fills"])) for row in rows),
                    "arrival_quote_lag_count": sum(int(numeric(row["arrival_quote_lag_count"])) for row in rows),
                    "arrival_stream_lag_count": sum(int(numeric(row["arrival_stream_lag_count"])) for row in rows),
                    "duplicate_exit_intents": sum(int(numeric(row["strict_duplicate_exit_intents"])) for row in rows),
                    "unclosed_lots": sum(int(numeric(row["strict_unclosed_lots"])) for row in rows),
                    "max_abs_residual_qty": max(abs(numeric(row["residual_qty"])) for row in rows),
                }
            )

    write_csv(out_dir / "daily.csv", daily_rows)
    write_csv(out_dir / "totals.csv", totals)
    summary = {
        "schema_id": "ccusdt_q70_strict_taker_first_cut_report_v1",
        "from_date": args.from_date,
        "to_date": args.to_date,
        "admission_profile": "entry_spread_q70_v1",
        "admission_rule": "prior-date q70 entry_cross_bps; entry_cross_bps = entry_spread_bps / 2",
        "exit_profiles": list(EXIT_PROFILES),
        "profiles": list(PROFILES),
        "watcher_q70_interface": {
            "status": "designed_not_enabled",
            "reason": "runtime-safe Q5/L2 sidecar is not exposed to the Bot decision_frame path yet",
            "intended_profile": "watcher_q70_absorb_reclaim2_pending",
            "activation_gate": "decision_frame/L2 sidecar must provide pretrade-safe Q_i(5), post-exit flow, and reclaim state",
        },
        "totals": totals,
        "daily_csv": str(out_dir / "daily.csv"),
        "totals_csv": str(out_dir / "totals.csv"),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

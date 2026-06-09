#!/usr/bin/env python
"""Compare two deterministic sim-live runs by stable causal hashes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir-a", required=True, type=Path)
    parser.add_argument("--run-dir-b", required=True, type=Path)
    parser.add_argument("--allow-empty-orders", action="store_true")
    parser.add_argument(
        "--compare-mode",
        choices=["repeat", "transport_equivalence"],
        default="repeat",
        help=(
            "repeat requires same profile/event count. transport_equivalence compares "
            "transport-normalized causal hashes so strict_event and batched_public_v1 can differ "
            "in envelope/event-count/arrival-stream lag but not decisions, fills, or account."
        ),
    )
    return parser.parse_args()


def audit(run_dir: Path, *, allow_empty_orders: bool) -> dict[str, Any]:
    script = Path(__file__).with_name("audit_event_log.py")
    cmd = [sys.executable, str(script), "--run-dir", str(run_dir)]
    if allow_empty_orders:
        cmd.append("--allow-empty-orders")
    completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"audit failed for {run_dir}:\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


def compare_field(
    left: dict[str, Any],
    right: dict[str, Any],
    field: str,
    errors: list[str],
) -> None:
    if left.get(field) != right.get(field):
        errors.append(f"{field} mismatch: {left.get(field)!r} != {right.get(field)!r}")


def main() -> int:
    args = parse_args()
    left = audit(args.run_dir_a, allow_empty_orders=args.allow_empty_orders)
    right = audit(args.run_dir_b, allow_empty_orders=args.allow_empty_orders)

    errors: list[str] = []
    for label, audit_result in (("left", left), ("right", right)):
        if not audit_result.get("ok"):
            errors.append(f"{label} audit was not ok")
        if int(audit_result.get("arrival_quote_lag_count") or 0) != 0:
            errors.append(
                f"{label} deterministic arrival_quote_lag_count="
                f"{audit_result.get('arrival_quote_lag_count')}"
            )
        if int(audit_result.get("private_seq_mismatch_count") or 0) != 0:
            errors.append(
                f"{label} deterministic private_seq_mismatch_count="
                f"{audit_result.get('private_seq_mismatch_count')}"
            )

    fields = (
        (
            "profile_manifest_hash",
            "decision_hash",
            "execution_hash",
            "portfolio_hash",
            "summary_account_hash",
            "event_count",
        )
        if args.compare_mode == "repeat"
        else (
            "transport_decision_hash",
            "transport_execution_hash",
            "transport_portfolio_hash",
            "transport_summary_account_hash",
        )
    )
    for field in fields:
        compare_field(left, right, field, errors)

    result = {
        "ok": not errors,
        "compare_mode": args.compare_mode,
        "run_dir_a": str(args.run_dir_a).replace("\\", "/"),
        "run_dir_b": str(args.run_dir_b).replace("\\", "/"),
        "profile_manifest_hash": left.get("profile_manifest_hash"),
        "decision_hash": left.get("decision_hash"),
        "execution_hash": left.get("execution_hash"),
        "portfolio_hash": left.get("portfolio_hash"),
        "transport_decision_hash": left.get("transport_decision_hash"),
        "transport_execution_hash": left.get("transport_execution_hash"),
        "transport_portfolio_hash": left.get("transport_portfolio_hash"),
        "summary_account_hash": left.get("summary_account_hash"),
        "transport_summary_account_hash": left.get("transport_summary_account_hash"),
        "deterministic_event_hash": left.get("deterministic_event_hash"),
        "fill_chain_hash": left.get("fill_chain_hash"),
        "event_count": left.get("event_count"),
        "arrival_quote_lag_count_a": left.get("arrival_quote_lag_count"),
        "arrival_quote_lag_count_b": right.get("arrival_quote_lag_count"),
        "arrival_stream_lag_count_a": left.get("arrival_stream_lag_count"),
        "arrival_stream_lag_count_b": right.get("arrival_stream_lag_count"),
        "private_seq_mismatch_count_a": left.get("private_seq_mismatch_count"),
        "private_seq_mismatch_count_b": right.get("private_seq_mismatch_count"),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

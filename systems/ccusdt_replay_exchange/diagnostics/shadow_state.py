#!/usr/bin/env python
"""Build Bot-owned shadow policy state from market-derived decision frames."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any


BOT_DIR = Path(__file__).resolve().parents[1] / "strategies" / "python" / "ccusdt_tfi_core_idle01"
DIAG_DIR = Path(__file__).resolve().parent
for path in [BOT_DIR, DIAG_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from decision_frame_cache import iter_cached_decision_frames, manifest_path, stable_json_hash  # noqa: E402
from shadow_policy import ShadowFourCellPolicy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument(
        "--shadow-state-in",
        type=Path,
        help="Optional previous Bot-owned state. Its next_expected_date must equal --from-date.",
    )
    parser.add_argument("--frames-threshold", type=float, default=31.0)
    parser.add_argument("--overlay-threshold", type=float, default=59.80000000000018)
    parser.add_argument("--fixed-exit-us", type=int, default=60_000_000)
    parser.add_argument("--gamma-preset", default="core_q70")
    parser.add_argument("--progress-interval", type=int, default=50_000)
    parser.add_argument("--out")
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


def next_date(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def cache_manifest_digest(repo_root: Path, symbol: str, day: str) -> dict[str, Any]:
    path = manifest_path(repo_root, symbol, day)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    digest_input = {
        "date": day,
        "schema_version": manifest.get("schema_version"),
        "builder_version": manifest.get("builder_version"),
        "input_layer": manifest.get("input_layer"),
        "row_count": manifest.get("row_count"),
        "field_hash_sha256": manifest.get("field_hash_sha256"),
        "data_manifest_hash": manifest.get("data_manifest_hash"),
        "cache_file_sha256": manifest.get("cache_file_sha256"),
    }
    return {
        "date": day,
        "cache_manifest_hash": stable_json_hash(digest_input),
        **digest_input,
    }


def default_output(repo_root: Path, to_date: str) -> Path:
    return (
        repo_root
        / "systems"
        / "ccusdt_replay_exchange"
        / "runs"
        / "state"
        / "ccusdt_tfi_core_idle01"
        / f"state_after_dt={to_date}.json"
    )


def resolve_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def load_and_guard_state(repo_root: Path, state_path: Path | None, from_date: str) -> dict[str, Any] | None:
    if state_path is None:
        return None
    path = resolve_path(repo_root, state_path)
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError(f"expected state JSON object: {path}")
    if state.get("next_expected_date") != from_date:
        raise ValueError(
            json.dumps(
                {
                    "error": "shadow_state_boundary_violation",
                    "reason": "state must resume exactly at next_expected_date",
                    "state_path": str(path),
                    "state_after_date": state.get("state_after_date") or state.get("last_seen_date"),
                    "state_next_expected_date": state.get("next_expected_date"),
                    "requested_from_date": from_date,
                },
                indent=2,
            )
        )
    return state


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    days = date_range(args.from_date, args.to_date)
    state_in = load_and_guard_state(repo_root, args.shadow_state_in, args.from_date)
    policy = ShadowFourCellPolicy(
        frames_threshold=args.frames_threshold,
        overlay_threshold=args.overlay_threshold,
        fixed_exit_us=args.fixed_exit_us,
        gamma_preset=args.gamma_preset,
    )
    if state_in is not None:
        policy.load_state(state_in)
    per_day: list[dict[str, Any]] = []
    input_manifests: list[dict[str, Any]] = []
    last_seen_ts_us: int | None = None
    start = time.perf_counter()
    for day in days:
        input_manifests.append(cache_manifest_digest(repo_root, args.symbol, day))
        policy.start_new_day()
        frames = 0
        entries = 0
        closes = 0
        day_start = time.perf_counter()
        for frame in iter_cached_decision_frames(repo_root, args.symbol, day):
            signal = policy.on_decision_frame(frame, frames)
            last_seen_ts_us = int(frame.get("local_ts_us") or 0)
            frames += 1
            if signal is not None:
                if signal.get("event_kind") == "shadow_entry":
                    entries += 1
                elif signal.get("event_kind") == "shadow_lifecycle_close":
                    closes += 1
            if args.progress_interval > 0 and frames % args.progress_interval == 0:
                print(
                    f"shadow state build day={day} frames={frames} entries={entries} closes={closes}",
                    file=sys.stderr,
                    flush=True,
                )
        per_day.append(
            {
                "date": day,
                "frames": frames,
                "shadow_entries": entries,
                "shadow_lifecycle_closes": closes,
                "elapsed_wall_ms": int((time.perf_counter() - day_start) * 1000),
            }
        )

    state = policy.export_state(last_seen_ts_us=last_seen_ts_us, last_seen_date=args.to_date)
    data_manifest = {
        "schema_id": "ccusdt_shadow_state_input_manifest_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "input_dataset": "decision_frame_v1_parquet_cache",
        "input_manifests": input_manifests,
        "policy_params_hash": state["policy_params_hash"],
        "state_in": str(args.shadow_state_in) if args.shadow_state_in else None,
        "state_in_data_manifest_hash": (state_in or {}).get("data_manifest_hash"),
    }
    state.update(
        {
            "state_source": "market_derived_decision_frame_parquet_cache_v1",
            "symbol": args.symbol,
            "from_date": args.from_date,
            "to_date": args.to_date,
            "state_after_date": args.to_date,
            "next_expected_date": next_date(args.to_date),
            "data_manifest": data_manifest,
            "data_manifest_hash": stable_json_hash(data_manifest),
            "per_day": per_day,
            "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
        }
    )
    out = Path(args.out) if args.out else default_output(repo_root, args.to_date)
    if not out.is_absolute():
        out = repo_root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "state_path": str(out),
                "schema_id": state["schema_id"],
                "source": state["state_source"],
                "closed_bps": state["closed_bps"],
                "pending_entries": len(state["pending_entries"]),
                "policy_params_hash": state["policy_params_hash"],
                "state_after_date": state["state_after_date"],
                "next_expected_date": state["next_expected_date"],
                "data_manifest_hash": state["data_manifest_hash"],
                "last_seen_ts_us": state["last_seen_ts_us"],
                "per_day": per_day,
                "elapsed_wall_ms": state["elapsed_wall_ms"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Compare fast backtest entries with strict Runner/Bot shadow/order/fill logs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


BASE_COMPARE_FIELDS = [
    "local_ts_us",
    "cell",
    "side",
    "membership_set",
    "target_exposure",
]

CAPACITY_COMPARE_FIELDS = [
    "actual_exposure",
    "clipped_exposure",
    "skipped",
    "capacity_source",
    "idle_capacity_before",
    "core_displacement",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--fast-run-dir", type=Path, required=True)
    parser.add_argument("--strict-audit-dir", type=Path, required=True)
    parser.add_argument("--date")
    parser.add_argument("--strict-source", choices=["auto", "triggers", "events"], default="auto")
    parser.add_argument("--pressure-bps", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--float-tol", type=float, default=1e-9)
    parser.add_argument("--max-mismatches", type=int, default=20)
    parser.add_argument(
        "--compare-mode",
        choices=["execution_decomposition", "strict_profile"],
        default="execution_decomposition",
        help="strict_profile also hard-rejects exit/fill/latency profile differences.",
    )
    parser.add_argument("--out-dir", type=Path)
    return parser.parse_args()


def resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def load_profile_manifest(run_dir: Path) -> tuple[dict[str, Any] | None, str]:
    profile_path = run_dir / "profile_manifest.json"
    if profile_path.exists():
        return read_json(profile_path), "profile_manifest.json"
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None, "missing"
    manifest = read_json(manifest_path)
    args = [str(item) for item in manifest.get("strategy_args") or []]
    if not args:
        return None, "missing_strategy_args"
    return derive_profile_from_strict_manifest(manifest, args), "derived_from_manifest"


def arg_value(args: list[str], flag: str) -> str | None:
    try:
        index = args.index(flag)
    except ValueError:
        return None
    return args[index + 1] if index + 1 < len(args) else None


def arg_float(args: list[str], flag: str) -> float | None:
    raw = arg_value(args, flag)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def derive_profile_from_strict_manifest(manifest: dict[str, Any], args: list[str]) -> dict[str, Any]:
    exchange = manifest.get("exchange_config") or {}
    return {
        "schema_id": "ccusdt_strategy_run_profiles_v1",
        "policy_profile": {
            "name": "old_tfi_four_cell_shadow_v1" if "--shadow-four-cell" in args else "online_tfi_skeleton_v1",
            "decision_clock": arg_value(args, "--decision-clock") or "quote",
            "gamma_preset": arg_value(args, "--shadow-gamma-preset"),
            "gamma01_override": arg_float(args, "--shadow-gamma01-override"),
            "frames_threshold": arg_float(args, "--shadow-frames-threshold"),
            "overlay_threshold": arg_float(args, "--shadow-overlay-threshold"),
            "fixed_exit_us": arg_float(args, "--shadow-fixed-exit-us"),
        },
        "capacity_profile": {
            "name": arg_value(args, "--shadow-capacity-profile") or "fifo_clip",
            "leverage_cap": arg_float(args, "--shadow-leverage-cap") or exchange.get("max_leverage"),
            "idle01_gamma": arg_float(args, "--shadow-idle01-gamma"),
            "idle01_reserve": arg_float(args, "--shadow-idle01-reserve") or 0.0,
        },
        "exit_profile": {
            "name": "fixed60_taker",
            "fixed_exit_us": arg_float(args, "--shadow-fixed-exit-us"),
        },
        "fill_profile": {
            "name": manifest.get("fill_model"),
            "fee_bps": exchange.get("fee_bps"),
        },
        "latency_profile": {
            "name": (
                "deterministic_replay_v1"
                if manifest.get("clock_mode") == "deterministic_step"
                else "wall_latency_pressure_v1"
            ),
            "latency_us": manifest.get("latency_us"),
            "arrival_mode": manifest.get("arrival_mode"),
            "clock_mode": manifest.get("clock_mode"),
            "wall_latency_speedup": manifest.get("wall_latency_speedup"),
        },
    }


def profile_value(profile: dict[str, Any], section: str, key: str) -> Any:
    data = profile.get(section) or {}
    if key in data:
        return data.get(key)
    params = data.get("params") or {}
    if key in params:
        return params.get(key)
    if key == "gamma01_override":
        overrides = params.get("gamma_overrides") or {}
        return overrides.get("01_frames_only")
    if key == "fixed_exit_us":
        return params.get("fixed_exit_us")
    return None


def compare_profiles(
    fast_dir: Path,
    strict_dir: Path,
    tol: float,
    *,
    compare_mode: str,
) -> dict[str, Any]:
    fast_profile, fast_source = load_profile_manifest(fast_dir)
    strict_profile, strict_source = load_profile_manifest(strict_dir)
    if fast_profile is None or strict_profile is None:
        return {
            "ok": False,
            "fast_profile_source": fast_source,
            "strict_profile_source": strict_source,
            "reason": "missing_profile_manifest",
            "mismatches": [],
        }
    checks = [
        ("policy_profile", "name"),
        ("policy_profile", "decision_clock"),
        ("policy_profile", "gamma_preset"),
        ("policy_profile", "gamma01_override"),
        ("policy_profile", "frames_threshold"),
        ("policy_profile", "overlay_threshold"),
        ("policy_profile", "fixed_exit_us"),
        ("capacity_profile", "name"),
        ("capacity_profile", "leverage_cap"),
        ("capacity_profile", "idle01_gamma"),
        ("capacity_profile", "idle01_reserve"),
        ("capacity_profile", "admission_profile"),
        ("capacity_profile", "admission_entry_cross_threshold_bps"),
        ("capacity_profile", "admission_thresholds_json"),
    ]
    required_sections = [
        "policy_profile",
        "capacity_profile",
        "exit_profile",
        "fill_profile",
        "latency_profile",
        "transport_profile",
        "data_profile",
    ]
    if compare_mode == "strict_profile":
        checks.extend(
            [
                ("exit_profile", "name"),
                ("exit_profile", "fixed_exit_us"),
                ("fill_profile", "name"),
                ("fill_profile", "fee_bps"),
                ("latency_profile", "name"),
                ("latency_profile", "latency_us"),
                ("latency_profile", "arrival_mode"),
                ("latency_profile", "clock_mode"),
                ("latency_profile", "wall_latency_speedup"),
                ("transport_profile", "name"),
                ("data_profile", "name"),
            ]
        )
    mismatches = []
    for section in required_sections:
        if not isinstance(fast_profile.get(section), dict):
            mismatches.append({"section": section, "key": "present", "fast": None, "strict": "required"})
        if not isinstance(strict_profile.get(section), dict):
            mismatches.append({"section": section, "key": "present", "fast": "required", "strict": None})
    for section, key in checks:
        left = normalize_profile_compare_value(key, profile_value(fast_profile, section, key))
        right = normalize_profile_compare_value(key, profile_value(strict_profile, section, key))
        if not compare_value(left, right, key, tol):
            mismatches.append(
                {
                    "section": section,
                    "key": key,
                    "fast": left,
                    "strict": right,
                }
            )
    data_check = compare_data_profiles(fast_profile, strict_profile, compare_mode=compare_mode)
    if not data_check["ok"]:
        mismatches.extend(data_check["mismatches"])
    return {
        "ok": not mismatches,
        "fast_profile_source": fast_source,
        "strict_profile_source": strict_source,
        "mismatches": mismatches,
        "fast_execution_profile": {
            "exit_profile": fast_profile.get("exit_profile"),
            "fill_profile": fast_profile.get("fill_profile"),
            "latency_profile": fast_profile.get("latency_profile"),
        },
        "strict_execution_profile": {
            "exit_profile": strict_profile.get("exit_profile"),
            "fill_profile": strict_profile.get("fill_profile"),
            "latency_profile": strict_profile.get("latency_profile"),
        },
        "fast_transport_profile": fast_profile.get("transport_profile"),
        "strict_transport_profile": strict_profile.get("transport_profile"),
        "data_profile_check": data_check,
        "compare_mode": compare_mode,
        "note": (
            "strict_profile hard-rejects policy/capacity/exit/fill/latency/transport/data differences."
            if compare_mode == "strict_profile"
            else "policy and capacity profiles must match exactly; exit/fill/latency/transport profiles are recorded for PnL decomposition; data cache compatibility is still checked."
        ),
    }


def normalize_profile_compare_value(key: str, value: Any) -> Any:
    if key == "decision_clock" and value == "decision_frame_v1":
        return "panel"
    if key.endswith("_json") and isinstance(value, str):
        return value.replace("\\", "/")
    return value


def compare_data_profiles(
    fast_profile: dict[str, Any],
    strict_profile: dict[str, Any],
    *,
    compare_mode: str,
) -> dict[str, Any]:
    fast_hashes = data_profile_cache_hashes(fast_profile.get("data_profile") or {})
    strict_hashes = data_profile_cache_hashes(strict_profile.get("data_profile") or {})
    mismatches: list[dict[str, Any]] = []
    if not fast_hashes:
        mismatches.append(
            {
                "section": "data_profile",
                "key": "cache_hashes",
                "fast": [],
                "strict": sorted(strict_hashes),
            }
        )
    if not strict_hashes:
        mismatches.append(
            {
                "section": "data_profile",
                "key": "cache_hashes",
                "fast": sorted(fast_hashes),
                "strict": [],
            }
        )
    if fast_hashes and strict_hashes:
        if compare_mode == "strict_profile":
            ok = fast_hashes == strict_hashes
        else:
            ok = bool(strict_hashes.issubset(fast_hashes) or fast_hashes.intersection(strict_hashes))
        if not ok:
            mismatches.append(
                {
                    "section": "data_profile",
                    "key": "cache_hash_compatibility",
                    "fast": sorted(fast_hashes),
                    "strict": sorted(strict_hashes),
                }
            )
    return {
        "ok": not mismatches,
        "fast_cache_hashes": sorted(fast_hashes),
        "strict_cache_hashes": sorted(strict_hashes),
        "mismatches": mismatches,
    }


def data_profile_cache_hashes(data_profile: dict[str, Any]) -> set[str]:
    hashes: set[str] = set()
    for key in ("cache_file_sha256", "cache_manifest_hash", "data_manifest_hash"):
        value = data_profile.get(key)
        if isinstance(value, str) and value:
            hashes.add(value)
    manifest = data_profile.get("decision_frame_cache")
    if isinstance(manifest, dict):
        for key in ("cache_file_sha256", "cache_manifest_hash", "data_manifest_hash"):
            value = manifest.get(key)
            if isinstance(value, str) and value:
                hashes.add(value)
    for raw in data_profile.get("input_manifests") or []:
        if not isinstance(raw, dict):
            continue
        for key in ("cache_file_sha256", "cache_manifest_hash", "data_manifest_hash"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                hashes.add(value)
    return hashes


def read_fast_table(path: Path, name: str) -> list[dict[str, Any]]:
    return pq.read_table(path / name).to_pylist()


def read_fast_entries(path: Path, target_date: str | None, only_traded: bool) -> list[dict[str, Any]]:
    rows = []
    exits_by_position = {
        int(raw["shadow_position_id"]): raw
        for raw in read_fast_table(path, "exits.parquet")
        if raw.get("shadow_position_id") is not None
    }
    for raw in read_fast_table(path, "entries.parquet"):
        if target_date and str(raw.get("date")) != target_date:
            continue
        target = float(raw.get("requested_exposure") or 0.0)
        actual = float(raw.get("actual_exposure") or 0.0)
        if only_traded and actual <= 0.0:
            continue
        position_id = int(raw["shadow_position_id"])
        exit_row = exits_by_position.get(position_id, {})
        rows.append(
            {
                "local_ts_us": int(raw.get("entry_ts_us")),
                "cell": str(raw.get("cell")),
                "side": str(raw.get("side")),
                "membership_set": str(raw.get("membership_set")),
                "target_exposure": target,
                "actual_exposure": actual,
                "clipped_exposure": float(raw.get("clipped_exposure") or 0.0),
                "skipped": bool(raw.get("skipped")),
                "admission_profile": str(raw.get("admission_profile") or ""),
                "admission_accepted": raw.get("admission_accepted"),
                "admission_reason": str(raw.get("admission_reason") or ""),
                "entry_cross_bps": optional_float(raw.get("entry_cross_bps")),
                "admission_entry_cross_threshold_bps": optional_float(
                    raw.get("admission_entry_cross_threshold_bps")
                ),
                "capacity_profile": str(raw.get("capacity_profile") or ""),
                "capacity_source": str(raw.get("capacity_source") or ""),
                "idle_capacity_before": optional_float(raw.get("idle_capacity_before")),
                "core_displacement": optional_float(raw.get("core_displacement")) or 0.0,
                "shadow_position_id": position_id,
                "date": str(raw.get("date")),
                "entry_mid": optional_float(raw.get("entry_mid")),
                "exit_mid": optional_float(exit_row.get("exit_mid")),
                "fast_raw_bps": optional_float(exit_row.get("raw_bps")) or optional_float(exit_row.get("raw_bps_mid_fixed60")),
                "fast_net_bps": optional_float(exit_row.get("net_bps_after_cost")),
            }
        )
    rows.sort(key=lambda row: (row["local_ts_us"], row["shadow_position_id"]))
    return rows


def arrival_lag_summary(strict_dir: Path) -> dict[str, Any]:
    events_path = strict_dir / "events.ndjson"
    if not events_path.exists():
        return {"ok": False, "reason": "missing_events"}
    arrived = 0
    quote_lag_count = 0
    stream_lag_count = 0
    quote_lag_max = 0
    stream_lag_max = 0
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if '"event_type":"order_arrived"' not in line:
                continue
            event = json.loads(line)
            raw = event.get("payload") or {}
            arrived += 1
            quote_lag = raw.get("arrival_quote_lag")
            if quote_lag is None:
                arrival_quote = raw.get("arrival_quote") or {}
                observed_quote = raw.get("observed_quote") or {}
                quote_lag = int(arrival_quote.get("seq") or 0) - int(observed_quote.get("seq") or 0)
            stream_lag = int(raw.get("arrival_stream_lag") or 0)
            quote_lag = int(quote_lag or 0)
            if quote_lag != 0:
                quote_lag_count += 1
                quote_lag_max = max(quote_lag_max, quote_lag)
            if stream_lag != 0:
                stream_lag_count += 1
                stream_lag_max = max(stream_lag_max, stream_lag)
    return {
        "ok": True,
        "order_arrived": arrived,
        "arrival_quote_lag_count": quote_lag_count,
        "arrival_quote_lag_max": quote_lag_max,
        "arrival_stream_lag_count": stream_lag_count,
        "arrival_stream_lag_max": stream_lag_max,
    }


def read_strict_entries(path: Path, target_date: str | None) -> tuple[list[dict[str, Any]], str]:
    source = "events" if (path / "events.ndjson").exists() else "triggers"
    if source == "events":
        capacity_rows = read_event_log_capacity_entries(path, target_date)
        if capacity_rows:
            return capacity_rows, source
        pairs = read_event_log_order_pairs(path, target_date)
        rows = [pair["entry"] for pair in pairs.values() if pair.get("entry")]
        rows.sort(key=lambda row: (row["local_ts_us"], row["shadow_position_id"]))
        return rows, source
    return read_trigger_csv_entries(path, target_date), source


def read_trigger_csv_entries(path: Path, target_date: str | None) -> list[dict[str, Any]]:
    rows = []
    with (path / "online_triggers.csv").open("r", newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            if target_date and str(raw.get("date")) != target_date:
                continue
            rows.append(
                {
                    "local_ts_us": int(float(raw.get("local_ts_us") or 0)),
                    "cell": str(raw.get("cell")),
                    "side": "buy" if str(raw.get("direction") or "") == "1" else "sell",
                    "membership_set": str(raw.get("membership_set")),
                    "target_exposure": float(raw.get("target_exposure") or 0.0),
                    "shadow_position_id": int(float(raw.get("shadow_position_id") or 0)),
                    "date": str(raw.get("date")),
                }
            )
    rows.sort(key=lambda row: (row["local_ts_us"], row["shadow_position_id"]))
    return rows


def read_event_log_order_pairs(path: Path, target_date: str | None) -> dict[int, dict[str, Any]]:
    fills_by_intent: dict[int, dict[str, Any]] = {}
    pairs: dict[int, dict[str, Any]] = defaultdict(dict)
    events = read_events(path / "events.ndjson")
    for event in events:
        if event.get("event_type") == "fill":
            inner = inner_payload(event)
            intent = int(inner.get("intent_id") or 0)
            fills_by_intent[intent] = inner
    for event in events:
        event_type = event.get("event_type")
        if event_type != "order_intent":
            continue
        payload = payload_dict(event)
        intent = payload.get("intent") or {}
        shadow = payload.get("shadow_signal") or {}
        if not isinstance(shadow, dict):
            continue
        intent_id = int(intent.get("intent_id") or 0)
        observed_quote = intent.get("observed_quote") or {}
        order = intent.get("order") or {}
        client_order_id = str(order.get("client_order_id") or "")
        if client_order_id.startswith("shadow-entry-"):
            position_id = int(shadow.get("shadow_position_id") or 0)
            local_ts_us = int(shadow.get("entry_ts_us") or shadow.get("local_ts_us") or 0)
            row_date = infer_date_from_ts(local_ts_us)
            if target_date and row_date != target_date:
                continue
            pairs[position_id]["entry"] = {
                "kind": "entry",
                "local_ts_us": local_ts_us,
                "cell": str(shadow.get("cell")),
                "side": str(shadow.get("side")),
                "membership_set": str(shadow.get("membership_set")),
                "target_exposure": float(shadow.get("target_exposure") or 0.0),
                "actual_exposure": optional_float(shadow.get("actual_exposure")),
                "clipped_exposure": optional_float(shadow.get("clipped_exposure")),
                "skipped": bool(shadow.get("skipped")) if shadow.get("skipped") is not None else None,
                "shadow_position_id": position_id,
                "date": row_date,
                "intent_id": intent_id,
                "client_order_id": client_order_id,
                "order_qty": optional_float(order.get("qty")),
                "observed_mid": optional_float(observed_quote.get("mid")),
                "observed_bid": optional_float(observed_quote.get("bid")),
                "observed_ask": optional_float(observed_quote.get("ask")),
                "fill": fills_by_intent.get(intent_id),
            }
            continue
        if not client_order_id.startswith("shadow-exit-"):
            continue
        try:
            position_id = int(client_order_id.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            continue
        close = find_close_for_position(shadow, position_id)
        if close is None:
            continue
        local_ts_us = int(close.get("close_ts_us") or shadow.get("local_ts_us") or 0)
        row_date = infer_date_from_ts(local_ts_us)
        if target_date and row_date != target_date:
            continue
        pairs[position_id]["exit"] = {
            "kind": "exit",
            "local_ts_us": local_ts_us,
            "cell": str(close.get("cell")),
            "side": str(order.get("side")),
            "entry_side": str(close.get("side")),
            "membership_set": str(close.get("membership_set")),
            "target_exposure": float(close.get("target_exposure") or 0.0),
            "shadow_position_id": position_id,
            "date": row_date,
            "intent_id": intent_id,
            "client_order_id": client_order_id,
            "order_qty": optional_float(order.get("qty")),
            "observed_mid": optional_float(observed_quote.get("mid")),
            "observed_bid": optional_float(observed_quote.get("bid")),
            "observed_ask": optional_float(observed_quote.get("ask")),
            "close_mid": optional_float(close.get("close_mid")),
            "fill": fills_by_intent.get(intent_id),
        }
    return dict(pairs)


def read_event_log_capacity_entries(path: Path, target_date: str | None) -> list[dict[str, Any]]:
    rows = []
    seen_keys: set[tuple[int, int]] = set()
    for event in read_events(path / "events.ndjson"):
        if event.get("event_type") != "capacity_decision":
            continue
        payload = payload_dict(event)
        capacity = payload.get("capacity_decision") or {}
        shadow = payload.get("shadow_signal") or {}
        if not isinstance(capacity, dict) or not isinstance(shadow, dict):
            continue
        if shadow.get("event_kind") != "shadow_entry":
            continue
        try:
            position_id = int(capacity.get("shadow_position_id") or shadow.get("shadow_position_id"))
            local_ts_us = int(shadow.get("entry_ts_us") or shadow.get("local_ts_us") or 0)
        except (TypeError, ValueError):
            continue
        row_date = infer_date_from_ts(local_ts_us)
        if target_date and row_date != target_date:
            continue
        key = (position_id, local_ts_us)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(
            {
                "_strict_event_kind": "capacity_decision",
                "local_ts_us": local_ts_us,
                "cell": str(shadow.get("cell")),
                "side": str(shadow.get("side")),
                "membership_set": str(shadow.get("membership_set")),
                "target_exposure": float(capacity.get("requested_exposure") or 0.0),
                "actual_exposure": float(capacity.get("actual_exposure") or 0.0),
                "clipped_exposure": float(capacity.get("clipped_exposure") or 0.0),
                "skipped": bool(capacity.get("skipped")),
                "admission_profile": str(shadow.get("admission_profile") or ""),
                "admission_accepted": shadow.get("admission_accepted"),
                "admission_reason": str(shadow.get("admission_reason") or ""),
                "entry_cross_bps": optional_float(shadow.get("entry_cross_bps")),
                "admission_entry_cross_threshold_bps": optional_float(
                    shadow.get("admission_entry_cross_threshold_bps")
                ),
                "capacity_profile": str(capacity.get("capacity_profile") or ""),
                "capacity_source": str(capacity.get("capacity_source") or ""),
                "idle_capacity_before": optional_float(capacity.get("idle_capacity_before")),
                "core_displacement": optional_float(capacity.get("core_displacement")) or 0.0,
                "open_exposure_before": optional_float(capacity.get("open_exposure_before")),
                "open_exposure_after": optional_float(capacity.get("open_exposure_after")),
                "shadow_position_id": position_id,
                "date": row_date,
                "intent_id": payload.get("intent_id"),
            }
        )
    rows.sort(key=lambda row: (row["local_ts_us"], row["shadow_position_id"]))
    return rows


def find_close_for_position(shadow: dict[str, Any], position_id: int) -> dict[str, Any] | None:
    for close in shadow.get("closed_now") or []:
        try:
            if int(close.get("shadow_position_id") or 0) == position_id:
                return close
        except (TypeError, ValueError):
            continue
    return None


def read_event_log_entries(path: Path, target_date: str | None) -> list[dict[str, Any]]:
    pairs = read_event_log_order_pairs(path, target_date)
    entries = [pair["entry"] for pair in pairs.values() if pair.get("entry")]
    entries.sort(key=lambda row: (row["local_ts_us"], row["shadow_position_id"]))
    return entries


def read_events(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    return out


def payload_dict(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def inner_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = payload_dict(event)
    nested = payload.get("payload")
    return nested if isinstance(nested, dict) else payload


def infer_date_from_ts(local_ts_us: int) -> str:
    # Current CCUSDT data is Asia/Shanghai-local capture time encoded as epoch us.
    # Use UTC date arithmetic only as a stable label fallback; fast rows are still
    # matched by timestamp/position id.
    import datetime as _dt

    return _dt.datetime.fromtimestamp(local_ts_us / 1_000_000, tz=_dt.timezone.utc).date().isoformat()


def compare_value(left: Any, right: Any, field: str, tol: float) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if field in {
        "target_exposure",
        "actual_exposure",
        "clipped_exposure",
        "idle_capacity_before",
        "core_displacement",
        "gamma01_override",
        "frames_threshold",
        "overlay_threshold",
        "fixed_exit_us",
        "leverage_cap",
        "idle01_gamma",
        "idle01_reserve",
    }:
        return abs(float(left) - float(right)) <= tol
    if field == "skipped":
        return bool(left) == bool(right)
    return left == right


def compare_rows(
    fast_rows: list[dict[str, Any]],
    strict_rows: list[dict[str, Any]],
    *,
    compare_fields: list[str],
    float_tol: float,
    max_mismatches: int,
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    field_counts: dict[str, int] = defaultdict(int)
    rows_compared = max(len(fast_rows), len(strict_rows))
    row_mismatch_count = 0
    for index in range(rows_compared):
        fast = fast_rows[index] if index < len(fast_rows) else None
        strict = strict_rows[index] if index < len(strict_rows) else None
        if fast is None or strict is None:
            row_mismatch_count += 1
            if len(mismatches) < max_mismatches:
                mismatches.append(
                    {
                        "row": index + 1,
                        "kind": "row_count_mismatch",
                        "fast_present": fast is not None,
                        "strict_present": strict is not None,
                    }
                )
            continue
        bad_fields = []
        for field in compare_fields:
            if not compare_value(fast.get(field), strict.get(field), field, float_tol):
                bad_fields.append(field)
                field_counts[field] += 1
        if bad_fields:
            row_mismatch_count += 1
            if len(mismatches) < max_mismatches:
                item = {
                    "row": index + 1,
                    "kind": "field_mismatch",
                    "fields": bad_fields,
                    "fast_local_ts_us": fast.get("local_ts_us"),
                    "strict_local_ts_us": strict.get("local_ts_us"),
                    "fast_position_id": fast.get("shadow_position_id"),
                    "strict_position_id": strict.get("shadow_position_id"),
                }
                for field in bad_fields:
                    item[f"fast_{field}"] = fast.get(field)
                    item[f"strict_{field}"] = strict.get(field)
                mismatches.append(item)
    return {
        "ok": row_mismatch_count == 0,
        "rows_compared": rows_compared,
        "fast_entries": len(fast_rows),
        "strict_entries": len(strict_rows),
        "row_mismatch_count": row_mismatch_count,
        "field_mismatch_counts": dict(sorted(field_counts.items())),
        "sample_mismatches": mismatches,
    }


def decompose_entry_fills(
    fast_rows: list[dict[str, Any]],
    strict_rows: list[dict[str, Any]],
    *,
    pressure_bps: float,
    slippage_bps: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    strict_by_position = {int(row["shadow_position_id"]): row for row in strict_rows}
    rows = []
    totals = defaultdict(float)
    missing_fills = 0
    for fast in fast_rows:
        strict = strict_by_position.get(int(fast["shadow_position_id"]))
        if strict is None:
            continue
        fill_payload = strict.get("fill")
        if not isinstance(fill_payload, dict):
            missing_fills += 1
            continue
        fill = fill_payload.get("fill") or {}
        arrival_quote = fill_payload.get("arrival_quote") or {}
        fill_price = optional_float(fill_payload.get("fill_price") or fill.get("price"))
        entry_mid = optional_float(fast.get("entry_mid"))
        exit_mid = optional_float(fast.get("exit_mid"))
        fast_raw_bps = optional_float(fast.get("fast_raw_bps"))
        if fill_price is None or entry_mid is None or exit_mid is None or fast_raw_bps is None:
            missing_fills += 1
            continue
        side = str(fast["side"])
        target = float(fast["target_exposure"])
        entry_execution_cost_bps = signed_entry_cost_bps(side, entry_mid, fill_price)
        latency_slippage_bps = float(fill_payload.get("latency_slippage_bps") or 0.0)
        observed_spread_cross_bps = signed_entry_cost_bps(
            side,
            entry_mid,
            strict["observed_ask"] if side == "buy" else strict["observed_bid"],
        )
        residual_bps = entry_execution_cost_bps - observed_spread_cross_bps - latency_slippage_bps
        sim_entry_fast_exit_bps = signed_exit_from_fill_bps(side, fill_price, exit_mid)
        sim_net_bps = sim_entry_fast_exit_bps - pressure_bps - slippage_bps
        fast_to_sim_delta_bps = sim_net_bps - fast_raw_bps
        row = {
            "date": fast["date"],
            "shadow_position_id": fast["shadow_position_id"],
            "local_ts_us": fast["local_ts_us"],
            "cell": fast["cell"],
            "side": side,
            "membership_set": fast["membership_set"],
            "target_exposure": target,
            "entry_mid": entry_mid,
            "exit_mid": exit_mid,
            "observed_bid": strict.get("observed_bid"),
            "observed_ask": strict.get("observed_ask"),
            "arrival_bid": arrival_quote.get("bid"),
            "arrival_ask": arrival_quote.get("ask"),
            "fill_price": fill_price,
            "fast_raw_bps": fast_raw_bps,
            "sim_entry_fast_exit_bps": sim_entry_fast_exit_bps,
            "pressure_bps": pressure_bps,
            "extra_slippage_bps": slippage_bps,
            "sim_net_bps": sim_net_bps,
            "fast_to_sim_delta_bps": fast_to_sim_delta_bps,
            "entry_execution_cost_bps": entry_execution_cost_bps,
            "observed_spread_cross_bps": observed_spread_cross_bps,
            "latency_slippage_bps": latency_slippage_bps,
            "entry_cost_residual_bps": residual_bps,
            "weighted_fast_raw_bps": target * fast_raw_bps,
            "weighted_sim_net_bps": target * sim_net_bps,
            "weighted_delta_bps": target * fast_to_sim_delta_bps,
            "intent_id": strict.get("intent_id"),
            "client_order_id": strict.get("client_order_id"),
            "actual_latency_us": fill_payload.get("actual_latency_us"),
            "spread_bps_at_arrival": fill_payload.get("spread_bps_at_arrival"),
            "fee_bps": fill_payload.get("fee_bps"),
        }
        rows.append(row)
        for key in [
            "weighted_fast_raw_bps",
            "weighted_sim_net_bps",
            "weighted_delta_bps",
            "entry_execution_cost_bps",
            "observed_spread_cross_bps",
            "latency_slippage_bps",
            "entry_cost_residual_bps",
        ]:
            totals[key] += float(row[key])
    count = len(rows)
    summary = {
        "fills_matched": count,
        "missing_fills": missing_fills,
        "weighted_fast_raw_bps": totals["weighted_fast_raw_bps"],
        "weighted_sim_net_bps": totals["weighted_sim_net_bps"],
        "weighted_delta_bps": totals["weighted_delta_bps"],
        "mean_entry_execution_cost_bps": totals["entry_execution_cost_bps"] / count if count else None,
        "mean_observed_spread_cross_bps": totals["observed_spread_cross_bps"] / count if count else None,
        "mean_latency_slippage_bps": totals["latency_slippage_bps"] / count if count else None,
        "mean_entry_cost_residual_bps": totals["entry_cost_residual_bps"] / count if count else None,
    }
    return summary, rows


def decompose_round_trip_fills(
    fast_rows: list[dict[str, Any]],
    strict_pairs: dict[int, dict[str, Any]],
    *,
    pressure_bps: float,
    slippage_bps: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    totals = defaultdict(float)
    missing_entry_fills = 0
    missing_exit_fills = 0
    missing_exit_intents = 0
    capacity_mismatch = 0
    for fast in fast_rows:
        position_id = int(fast["shadow_position_id"])
        pair = strict_pairs.get(position_id) or {}
        strict_entry = pair.get("entry")
        strict_exit = pair.get("exit")
        if not strict_entry:
            continue
        entry_payload = strict_entry.get("fill")
        if not isinstance(entry_payload, dict):
            missing_entry_fills += 1
            continue
        if not strict_exit:
            missing_exit_intents += 1
            continue
        exit_payload = strict_exit.get("fill")
        if not isinstance(exit_payload, dict):
            missing_exit_fills += 1
            continue

        entry_fill_price = fill_price_from_payload(entry_payload)
        exit_fill_price = fill_price_from_payload(exit_payload)
        entry_mid = optional_float(fast.get("entry_mid"))
        exit_mid = optional_float(fast.get("exit_mid"))
        fast_raw_bps = optional_float(fast.get("fast_raw_bps"))
        if (
            entry_fill_price is None
            or exit_fill_price is None
            or entry_mid is None
            or exit_mid is None
            or fast_raw_bps is None
        ):
            missing_entry_fills += 1
            continue

        side = str(fast["side"])
        exit_side = opposite_side(side)
        target_exposure = float(fast["target_exposure"])
        actual_exposure = float(fast.get("actual_exposure") or 0.0)
        if abs(target_exposure - actual_exposure) > 1e-12:
            capacity_mismatch += 1

        entry_arrival_quote = entry_payload.get("arrival_quote") or {}
        exit_arrival_quote = exit_payload.get("arrival_quote") or {}
        entry_execution_cost_bps = signed_taker_cost_bps(side, entry_mid, entry_fill_price)
        exit_execution_cost_bps = signed_taker_cost_bps(exit_side, exit_mid, exit_fill_price)
        entry_latency_slippage_bps = float(entry_payload.get("latency_slippage_bps") or 0.0)
        exit_latency_slippage_bps = float(exit_payload.get("latency_slippage_bps") or 0.0)
        entry_observed_spread_cross_bps = signed_taker_cost_bps(
            side,
            entry_mid,
            strict_entry["observed_ask"] if side == "buy" else strict_entry["observed_bid"],
        )
        exit_observed_spread_cross_bps = signed_taker_cost_bps(
            exit_side,
            exit_mid,
            strict_exit["observed_ask"] if exit_side == "buy" else strict_exit["observed_bid"],
        )
        entry_cost_residual_bps = (
            entry_execution_cost_bps - entry_observed_spread_cross_bps - entry_latency_slippage_bps
        )
        exit_cost_residual_bps = (
            exit_execution_cost_bps - exit_observed_spread_cross_bps - exit_latency_slippage_bps
        )
        sim_round_trip_gross_bps = signed_round_trip_bps(side, entry_fill_price, exit_fill_price)
        sim_round_trip_net_bps = sim_round_trip_gross_bps - pressure_bps - slippage_bps
        fast_to_sim_delta_bps = sim_round_trip_net_bps - fast_raw_bps
        total_execution_cost_bps = entry_execution_cost_bps + exit_execution_cost_bps
        total_latency_slippage_bps = entry_latency_slippage_bps + exit_latency_slippage_bps
        total_spread_cross_bps = entry_observed_spread_cross_bps + exit_observed_spread_cross_bps
        total_cost_residual_bps = entry_cost_residual_bps + exit_cost_residual_bps
        weighted_shadow_delta_bps = target_exposure * fast_to_sim_delta_bps
        weighted_cost_explained_delta_bps = -target_exposure * (
            total_execution_cost_bps + pressure_bps + slippage_bps
        )
        weighted_capacity_delta_bps = actual_exposure * fast_to_sim_delta_bps
        weighted_capacity_cost_explained_delta_bps = -actual_exposure * (
            total_execution_cost_bps + pressure_bps + slippage_bps
        )

        row = {
            "date": fast["date"],
            "shadow_position_id": position_id,
            "entry_ts_us": fast["local_ts_us"],
            "exit_ts_us": strict_exit.get("local_ts_us"),
            "cell": fast["cell"],
            "side": side,
            "exit_side": exit_side,
            "membership_set": fast["membership_set"],
            "target_exposure": target_exposure,
            "fast_actual_exposure": actual_exposure,
            "capacity_weight_mismatch": abs(target_exposure - actual_exposure) > 1e-12,
            "entry_mid": entry_mid,
            "exit_mid": exit_mid,
            "entry_fill_price": entry_fill_price,
            "exit_fill_price": exit_fill_price,
            "entry_observed_bid": strict_entry.get("observed_bid"),
            "entry_observed_ask": strict_entry.get("observed_ask"),
            "entry_arrival_bid": entry_arrival_quote.get("bid"),
            "entry_arrival_ask": entry_arrival_quote.get("ask"),
            "exit_observed_bid": strict_exit.get("observed_bid"),
            "exit_observed_ask": strict_exit.get("observed_ask"),
            "exit_arrival_bid": exit_arrival_quote.get("bid"),
            "exit_arrival_ask": exit_arrival_quote.get("ask"),
            "fast_raw_bps": fast_raw_bps,
            "sim_round_trip_gross_bps": sim_round_trip_gross_bps,
            "pressure_bps": pressure_bps,
            "extra_slippage_bps": slippage_bps,
            "sim_round_trip_net_bps": sim_round_trip_net_bps,
            "fast_to_sim_delta_bps": fast_to_sim_delta_bps,
            "entry_execution_cost_bps": entry_execution_cost_bps,
            "exit_execution_cost_bps": exit_execution_cost_bps,
            "total_execution_cost_bps": total_execution_cost_bps,
            "entry_observed_spread_cross_bps": entry_observed_spread_cross_bps,
            "exit_observed_spread_cross_bps": exit_observed_spread_cross_bps,
            "total_observed_spread_cross_bps": total_spread_cross_bps,
            "entry_latency_slippage_bps": entry_latency_slippage_bps,
            "exit_latency_slippage_bps": exit_latency_slippage_bps,
            "total_latency_slippage_bps": total_latency_slippage_bps,
            "entry_cost_residual_bps": entry_cost_residual_bps,
            "exit_cost_residual_bps": exit_cost_residual_bps,
            "total_cost_residual_bps": total_cost_residual_bps,
            "weighted_fast_shadow_raw_bps": target_exposure * fast_raw_bps,
            "weighted_fast_capacity_raw_bps": actual_exposure * fast_raw_bps,
            "weighted_sim_shadow_net_bps": target_exposure * sim_round_trip_net_bps,
            "weighted_sim_capacity_net_bps": actual_exposure * sim_round_trip_net_bps,
            "weighted_shadow_delta_bps": weighted_shadow_delta_bps,
            "weighted_capacity_delta_bps": weighted_capacity_delta_bps,
            "weighted_capacity_vs_sim_delta_bps": weighted_capacity_delta_bps,
            "weighted_entry_execution_cost_bps": target_exposure * entry_execution_cost_bps,
            "weighted_exit_execution_cost_bps": target_exposure * exit_execution_cost_bps,
            "weighted_total_execution_cost_bps": target_exposure * total_execution_cost_bps,
            "weighted_entry_observed_spread_cross_bps": target_exposure
            * entry_observed_spread_cross_bps,
            "weighted_exit_observed_spread_cross_bps": target_exposure
            * exit_observed_spread_cross_bps,
            "weighted_total_observed_spread_cross_bps": target_exposure * total_spread_cross_bps,
            "weighted_entry_latency_slippage_bps": target_exposure * entry_latency_slippage_bps,
            "weighted_exit_latency_slippage_bps": target_exposure * exit_latency_slippage_bps,
            "weighted_total_latency_slippage_bps": target_exposure * total_latency_slippage_bps,
            "weighted_entry_cost_residual_bps": target_exposure * entry_cost_residual_bps,
            "weighted_exit_cost_residual_bps": target_exposure * exit_cost_residual_bps,
            "weighted_total_cost_residual_bps": target_exposure * total_cost_residual_bps,
            "weighted_pressure_bps": target_exposure * pressure_bps,
            "weighted_extra_slippage_bps": target_exposure * slippage_bps,
            "weighted_cost_explained_delta_bps": weighted_cost_explained_delta_bps,
            "weighted_unexplained_delta_bps": weighted_shadow_delta_bps
            - weighted_cost_explained_delta_bps,
            "weighted_capacity_entry_execution_cost_bps": actual_exposure
            * entry_execution_cost_bps,
            "weighted_capacity_exit_execution_cost_bps": actual_exposure
            * exit_execution_cost_bps,
            "weighted_capacity_total_execution_cost_bps": actual_exposure
            * total_execution_cost_bps,
            "weighted_capacity_entry_observed_spread_cross_bps": actual_exposure
            * entry_observed_spread_cross_bps,
            "weighted_capacity_exit_observed_spread_cross_bps": actual_exposure
            * exit_observed_spread_cross_bps,
            "weighted_capacity_total_observed_spread_cross_bps": actual_exposure
            * total_spread_cross_bps,
            "weighted_capacity_entry_latency_slippage_bps": actual_exposure
            * entry_latency_slippage_bps,
            "weighted_capacity_exit_latency_slippage_bps": actual_exposure
            * exit_latency_slippage_bps,
            "weighted_capacity_total_latency_slippage_bps": actual_exposure
            * total_latency_slippage_bps,
            "weighted_capacity_entry_cost_residual_bps": actual_exposure
            * entry_cost_residual_bps,
            "weighted_capacity_exit_cost_residual_bps": actual_exposure
            * exit_cost_residual_bps,
            "weighted_capacity_total_cost_residual_bps": actual_exposure * total_cost_residual_bps,
            "weighted_capacity_pressure_bps": actual_exposure * pressure_bps,
            "weighted_capacity_extra_slippage_bps": actual_exposure * slippage_bps,
            "weighted_capacity_cost_explained_delta_bps": weighted_capacity_cost_explained_delta_bps,
            "weighted_capacity_unexplained_delta_bps": weighted_capacity_delta_bps
            - weighted_capacity_cost_explained_delta_bps,
            "entry_intent_id": strict_entry.get("intent_id"),
            "exit_intent_id": strict_exit.get("intent_id"),
            "entry_client_order_id": strict_entry.get("client_order_id"),
            "exit_client_order_id": strict_exit.get("client_order_id"),
            "entry_actual_latency_us": entry_payload.get("actual_latency_us"),
            "exit_actual_latency_us": exit_payload.get("actual_latency_us"),
            "entry_spread_bps_at_arrival": entry_payload.get("spread_bps_at_arrival"),
            "exit_spread_bps_at_arrival": exit_payload.get("spread_bps_at_arrival"),
            "entry_fee_bps": entry_payload.get("fee_bps"),
            "exit_fee_bps": exit_payload.get("fee_bps"),
        }
        rows.append(row)
        for key in [
            "weighted_fast_shadow_raw_bps",
            "weighted_fast_capacity_raw_bps",
            "weighted_sim_shadow_net_bps",
            "weighted_sim_capacity_net_bps",
            "weighted_shadow_delta_bps",
            "weighted_capacity_delta_bps",
            "weighted_capacity_vs_sim_delta_bps",
            "entry_execution_cost_bps",
            "exit_execution_cost_bps",
            "total_execution_cost_bps",
            "entry_observed_spread_cross_bps",
            "exit_observed_spread_cross_bps",
            "total_observed_spread_cross_bps",
            "entry_latency_slippage_bps",
            "exit_latency_slippage_bps",
            "total_latency_slippage_bps",
            "entry_cost_residual_bps",
            "exit_cost_residual_bps",
            "total_cost_residual_bps",
            "weighted_entry_execution_cost_bps",
            "weighted_exit_execution_cost_bps",
            "weighted_total_execution_cost_bps",
            "weighted_entry_observed_spread_cross_bps",
            "weighted_exit_observed_spread_cross_bps",
            "weighted_total_observed_spread_cross_bps",
            "weighted_entry_latency_slippage_bps",
            "weighted_exit_latency_slippage_bps",
            "weighted_total_latency_slippage_bps",
            "weighted_entry_cost_residual_bps",
            "weighted_exit_cost_residual_bps",
            "weighted_total_cost_residual_bps",
            "weighted_pressure_bps",
            "weighted_extra_slippage_bps",
            "weighted_cost_explained_delta_bps",
            "weighted_unexplained_delta_bps",
            "weighted_capacity_entry_execution_cost_bps",
            "weighted_capacity_exit_execution_cost_bps",
            "weighted_capacity_total_execution_cost_bps",
            "weighted_capacity_entry_observed_spread_cross_bps",
            "weighted_capacity_exit_observed_spread_cross_bps",
            "weighted_capacity_total_observed_spread_cross_bps",
            "weighted_capacity_entry_latency_slippage_bps",
            "weighted_capacity_exit_latency_slippage_bps",
            "weighted_capacity_total_latency_slippage_bps",
            "weighted_capacity_entry_cost_residual_bps",
            "weighted_capacity_exit_cost_residual_bps",
            "weighted_capacity_total_cost_residual_bps",
            "weighted_capacity_pressure_bps",
            "weighted_capacity_extra_slippage_bps",
            "weighted_capacity_cost_explained_delta_bps",
            "weighted_capacity_unexplained_delta_bps",
        ]:
            totals[key] += float(row[key])
    count = len(rows)
    summary = {
        "round_trips_matched": count,
        "missing_entry_fills": missing_entry_fills,
        "missing_exit_intents": missing_exit_intents,
        "missing_exit_fills": missing_exit_fills,
        "capacity_weight_mismatch_rows": capacity_mismatch,
        "weighted_fast_shadow_raw_bps": totals["weighted_fast_shadow_raw_bps"],
        "weighted_fast_capacity_raw_bps": totals["weighted_fast_capacity_raw_bps"],
        "weighted_sim_shadow_net_bps": totals["weighted_sim_shadow_net_bps"],
        "weighted_sim_capacity_net_bps": totals["weighted_sim_capacity_net_bps"],
        "weighted_shadow_delta_bps": totals["weighted_shadow_delta_bps"],
        "weighted_capacity_delta_bps": totals["weighted_capacity_delta_bps"],
        "weighted_capacity_vs_sim_delta_bps": totals["weighted_capacity_vs_sim_delta_bps"],
        "weighted_entry_execution_cost_bps": totals["weighted_entry_execution_cost_bps"],
        "weighted_exit_execution_cost_bps": totals["weighted_exit_execution_cost_bps"],
        "weighted_total_execution_cost_bps": totals["weighted_total_execution_cost_bps"],
        "weighted_entry_observed_spread_cross_bps": totals[
            "weighted_entry_observed_spread_cross_bps"
        ],
        "weighted_exit_observed_spread_cross_bps": totals[
            "weighted_exit_observed_spread_cross_bps"
        ],
        "weighted_total_observed_spread_cross_bps": totals[
            "weighted_total_observed_spread_cross_bps"
        ],
        "weighted_entry_latency_slippage_bps": totals["weighted_entry_latency_slippage_bps"],
        "weighted_exit_latency_slippage_bps": totals["weighted_exit_latency_slippage_bps"],
        "weighted_total_latency_slippage_bps": totals["weighted_total_latency_slippage_bps"],
        "weighted_entry_cost_residual_bps": totals["weighted_entry_cost_residual_bps"],
        "weighted_exit_cost_residual_bps": totals["weighted_exit_cost_residual_bps"],
        "weighted_total_cost_residual_bps": totals["weighted_total_cost_residual_bps"],
        "weighted_pressure_bps": totals["weighted_pressure_bps"],
        "weighted_extra_slippage_bps": totals["weighted_extra_slippage_bps"],
        "weighted_cost_explained_delta_bps": totals["weighted_cost_explained_delta_bps"],
        "weighted_unexplained_delta_bps": totals["weighted_unexplained_delta_bps"],
        "weighted_capacity_entry_execution_cost_bps": totals[
            "weighted_capacity_entry_execution_cost_bps"
        ],
        "weighted_capacity_exit_execution_cost_bps": totals[
            "weighted_capacity_exit_execution_cost_bps"
        ],
        "weighted_capacity_total_execution_cost_bps": totals[
            "weighted_capacity_total_execution_cost_bps"
        ],
        "weighted_capacity_entry_observed_spread_cross_bps": totals[
            "weighted_capacity_entry_observed_spread_cross_bps"
        ],
        "weighted_capacity_exit_observed_spread_cross_bps": totals[
            "weighted_capacity_exit_observed_spread_cross_bps"
        ],
        "weighted_capacity_total_observed_spread_cross_bps": totals[
            "weighted_capacity_total_observed_spread_cross_bps"
        ],
        "weighted_capacity_entry_latency_slippage_bps": totals[
            "weighted_capacity_entry_latency_slippage_bps"
        ],
        "weighted_capacity_exit_latency_slippage_bps": totals[
            "weighted_capacity_exit_latency_slippage_bps"
        ],
        "weighted_capacity_total_latency_slippage_bps": totals[
            "weighted_capacity_total_latency_slippage_bps"
        ],
        "weighted_capacity_entry_cost_residual_bps": totals[
            "weighted_capacity_entry_cost_residual_bps"
        ],
        "weighted_capacity_exit_cost_residual_bps": totals[
            "weighted_capacity_exit_cost_residual_bps"
        ],
        "weighted_capacity_total_cost_residual_bps": totals[
            "weighted_capacity_total_cost_residual_bps"
        ],
        "weighted_capacity_pressure_bps": totals["weighted_capacity_pressure_bps"],
        "weighted_capacity_extra_slippage_bps": totals["weighted_capacity_extra_slippage_bps"],
        "weighted_capacity_cost_explained_delta_bps": totals[
            "weighted_capacity_cost_explained_delta_bps"
        ],
        "weighted_capacity_unexplained_delta_bps": totals[
            "weighted_capacity_unexplained_delta_bps"
        ],
        "mean_entry_execution_cost_bps": totals["entry_execution_cost_bps"] / count if count else None,
        "mean_exit_execution_cost_bps": totals["exit_execution_cost_bps"] / count if count else None,
        "mean_total_execution_cost_bps": totals["total_execution_cost_bps"] / count if count else None,
        "mean_entry_observed_spread_cross_bps": (
            totals["entry_observed_spread_cross_bps"] / count if count else None
        ),
        "mean_exit_observed_spread_cross_bps": (
            totals["exit_observed_spread_cross_bps"] / count if count else None
        ),
        "mean_total_observed_spread_cross_bps": (
            totals["total_observed_spread_cross_bps"] / count if count else None
        ),
        "mean_entry_latency_slippage_bps": totals["entry_latency_slippage_bps"] / count if count else None,
        "mean_exit_latency_slippage_bps": totals["exit_latency_slippage_bps"] / count if count else None,
        "mean_total_latency_slippage_bps": totals["total_latency_slippage_bps"] / count if count else None,
        "mean_entry_cost_residual_bps": totals["entry_cost_residual_bps"] / count if count else None,
        "mean_exit_cost_residual_bps": totals["exit_cost_residual_bps"] / count if count else None,
        "mean_total_cost_residual_bps": totals["total_cost_residual_bps"] / count if count else None,
        "weight_note": (
            "shadow weights use target_exposure to match bot order intents; capacity weights use "
            "fast backtest actual_exposure after leverage clipping."
        ),
    }
    return summary, rows


def signed_entry_cost_bps(side: str, entry_mid: float | None, fill_price: float | None) -> float:
    if entry_mid is None or fill_price is None or entry_mid <= 0.0 or fill_price <= 0.0:
        return float("nan")
    if side == "buy":
        return math.log(fill_price / entry_mid) * 10_000.0
    return math.log(entry_mid / fill_price) * 10_000.0


def signed_taker_cost_bps(order_side: str, mid: float | None, fill_price: float | None) -> float:
    return signed_entry_cost_bps(order_side, mid, fill_price)


def signed_exit_from_fill_bps(side: str, fill_price: float, exit_mid: float) -> float:
    if side == "buy":
        return math.log(exit_mid / fill_price) * 10_000.0
    return math.log(fill_price / exit_mid) * 10_000.0


def signed_round_trip_bps(entry_side: str, entry_fill: float, exit_fill: float) -> float:
    if entry_side == "buy":
        return math.log(exit_fill / entry_fill) * 10_000.0
    return math.log(entry_fill / exit_fill) * 10_000.0


def opposite_side(side: str) -> str:
    return "sell" if side == "buy" else "buy"


def fill_price_from_payload(fill_payload: dict[str, Any]) -> float | None:
    fill = fill_payload.get("fill") or {}
    return optional_float(fill_payload.get("fill_price") or fill.get("price"))


def optional_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    table = pa.Table.from_pylist(rows) if rows else pa.table({})
    pq.write_table(table, path, compression="zstd")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    fast_dir = resolve(repo_root, args.fast_run_dir)
    strict_dir = resolve(repo_root, args.strict_audit_dir)
    strict_rows, detected_source = read_strict_entries(strict_dir, args.date)
    if args.strict_source != "auto" and args.strict_source != detected_source:
        raise ValueError(f"requested strict-source={args.strict_source}, detected {detected_source}")
    has_capacity_rows = any(row.get("_strict_event_kind") == "capacity_decision" for row in strict_rows)
    only_traded = detected_source == "events" and not has_capacity_rows
    compare_fields = list(BASE_COMPARE_FIELDS)
    if has_capacity_rows:
        compare_fields.extend(CAPACITY_COMPARE_FIELDS)
    fast_rows = read_fast_entries(fast_dir, args.date, only_traded=only_traded)
    comparison = compare_rows(
        fast_rows,
        strict_rows,
        compare_fields=compare_fields,
        float_tol=args.float_tol,
        max_mismatches=args.max_mismatches,
    )
    profile_check = compare_profiles(
        fast_dir,
        strict_dir,
        args.float_tol,
        compare_mode=args.compare_mode,
    )
    comparison["ok"] = bool(comparison["ok"] and profile_check["ok"])
    fill_summary, fill_rows = ({}, [])
    round_trip_summary, round_trip_rows = ({}, [])
    if detected_source == "events":
        strict_pairs = read_event_log_order_pairs(strict_dir, args.date)
        strict_fill_rows = [pair["entry"] for pair in strict_pairs.values() if pair.get("entry")]
        strict_fill_rows.sort(key=lambda row: (row["local_ts_us"], row["shadow_position_id"]))
        fast_fill_rows = read_fast_entries(fast_dir, args.date, only_traded=True)
        fill_summary, fill_rows = decompose_entry_fills(
            fast_fill_rows,
            strict_fill_rows,
            pressure_bps=args.pressure_bps,
            slippage_bps=args.slippage_bps,
        )
        round_trip_summary, round_trip_rows = decompose_round_trip_fills(
            fast_fill_rows,
            strict_pairs,
            pressure_bps=args.pressure_bps,
            slippage_bps=args.slippage_bps,
        )
    result = {
        **comparison,
        "schema_id": "ccusdt_fast_vs_sim_live_consistency_v1",
        "execution_compare_mode": args.compare_mode,
        "fast_run_dir": str(fast_dir),
        "strict_audit_dir": str(strict_dir),
        "strict_source": detected_source,
        "strict_event_kind": "capacity_decision" if has_capacity_rows else detected_source,
        "date": args.date,
        "compare_fields": compare_fields,
        "profile_check": profile_check,
        "arrival_lag_summary": arrival_lag_summary(strict_dir),
        "fill_pnl_decomposition": fill_summary,
        "round_trip_fill_pnl_decomposition": round_trip_summary,
        "scope_note": (
            "events mode compares traded shadow entry order_intents/fills. "
            "entry_fill_decomposition isolates entry taker cost against the fast fixed60 mid exit; "
            "round_trip_fill_decomposition uses both entry and exit IOC fills when shadow exit orders are present."
        ),
    }
    out_dir = resolve(repo_root, args.out_dir) if args.out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        write_csv(out_dir / "entry_fill_decomposition.csv", fill_rows)
        write_parquet(out_dir / "entry_fill_decomposition.parquet", fill_rows)
        write_csv(out_dir / "round_trip_fill_decomposition.csv", round_trip_rows)
        write_parquet(out_dir / "round_trip_fill_decomposition.parquet", round_trip_rows)
        result["outputs"] = {
            "summary_json": str(out_dir / "summary.json"),
            "entry_fill_decomposition_csv": str(out_dir / "entry_fill_decomposition.csv"),
            "entry_fill_decomposition_parquet": str(out_dir / "entry_fill_decomposition.parquet"),
            "round_trip_fill_decomposition_csv": str(out_dir / "round_trip_fill_decomposition.csv"),
            "round_trip_fill_decomposition_parquet": str(out_dir / "round_trip_fill_decomposition.parquet"),
        }
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

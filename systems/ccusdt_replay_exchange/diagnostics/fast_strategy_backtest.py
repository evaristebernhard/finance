#!/usr/bin/env python
"""Fast CCUSDT strategy backtest over market-derived decision_frame_v1 cache.

This is the fast research line, not the sim-live Runner. It reads only the
typed decision_frame_v1 Parquet cache plus optional Bot-owned shadow state, then
uses the same runtime-safe shadow policy to create entries and fixed60 mid exits.
It never reads legacy date/scored-entry/future-label files as strategy input.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


BOT_DIR = Path(__file__).resolve().parents[1] / "strategies" / "python" / "ccusdt_tfi_core_idle01"
DIAG_DIR = Path(__file__).resolve().parent
for path in [BOT_DIR, DIAG_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from decision_frame_cache import iter_cached_decision_frames, manifest_path, stable_json_hash  # noqa: E402
from execution_runtime import (  # noqa: E402
    CapacityLedger,
    EntrySpreadAdmissionGate,
    STOPPING_RULE_HORIZONS_SEC,
    StoppingRuleParams,
    build_admission_gate,
    build_capacity_allocator,
    build_profile_manifest,
    load_stopping_rule_params_by_date,
    stable_profile_hash,
    stopping_rule_should_exit,
    taker_net_and_exit_cross_bps,
)
from shadow_policy import ShadowFourCellPolicy  # noqa: E402


QUOTE_FRAME_ROOT = Path("data/canonical/cex/bullish")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--shadow-state-in", type=Path)
    parser.add_argument("--frames-threshold", type=float, default=31.0)
    parser.add_argument("--overlay-threshold", type=float, default=59.80000000000018)
    parser.add_argument("--fixed-exit-us", type=int, default=60_000_000)
    parser.add_argument(
        "--exit-profile",
        choices=["fixed60_mid", "fixed60_taker", "manager_path", "peakguard_taker_v1", "stopping_rule_v1"],
        default="fixed60_mid",
    )
    parser.add_argument(
        "--stopping-rule-params-json",
        type=Path,
        help="Date -> prior-trained params for exit_profile=stopping_rule_v1.",
    )
    parser.add_argument("--gamma-preset", default="core_q70")
    parser.add_argument(
        "--gamma01-override",
        type=float,
        help="Override policy gamma for 01_frames_only; used by core_idle01 sleeves.",
    )
    parser.add_argument("--capacity-profile", choices=["fifo_clip", "core_idle01"], default="fifo_clip")
    parser.add_argument("--idle01-gamma", type=float)
    parser.add_argument("--idle01-reserve", type=float, default=0.0)
    parser.add_argument(
        "--admission-profile",
        choices=["none", "entry_spread_q70_v1"],
        default="none",
    )
    parser.add_argument("--admission-entry-cross-threshold-bps", type=float)
    parser.add_argument("--admission-threshold-source", default="")
    parser.add_argument(
        "--admission-thresholds-json",
        type=Path,
        help="Optional mapping of date -> entry_cross_threshold_bps for prior-date admission.",
    )
    parser.add_argument("--leverage-cap", type=float, default=3.0)
    parser.add_argument("--fee-bps", type=float, default=0.0)
    parser.add_argument("--pressure-bps", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--run-id")
    parser.add_argument("--progress-interval", type=int, default=50_000)
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


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def resolve_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def quote_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / QUOTE_FRAME_ROOT / symbol / "quote_frame_v1" / f"dt={day}" / "part_000001.csv.gz"


class QuoteFrameIndex:
    """Canonical quote_frame_v1 lookup matching panel_sparse_fast_clock_v1."""

    def __init__(self, frames: list[dict[str, Any]]) -> None:
        if not frames:
            raise ValueError("quote_frame_v1 index is empty")
        self.frames = frames
        self.local_ts_us = [int(frame["local_ts_us"]) for frame in frames]

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteFrameIndex":
        path = quote_frame_path(repo_root, symbol, day)
        frames: list[dict[str, Any]] = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                bid = optional_float(row.get("bid_px"))
                ask = optional_float(row.get("ask_px"))
                mid = optional_float(row.get("mid_px"))
                local_ts_us = int(row.get("local_ts_us") or 0)
                exchange_ts_us = int(row.get("exchange_ts_us") or 0)
                seq = int(row.get("seq") or len(frames))
                if local_ts_us <= 0 or bid is None or ask is None:
                    continue
                frames.append(
                    {
                        "seq": seq,
                        "exchange_ts_us": exchange_ts_us,
                        "local_ts_us": local_ts_us,
                        "bid_px": bid,
                        "ask_px": ask,
                        "mid_px": mid if mid is not None else 0.5 * (bid + ask),
                        "spread_bps": optional_float(row.get("spread_bps")),
                    }
                )
        return cls(frames)

    def at_or_before(self, local_ts_us: int | None) -> dict[str, Any]:
        if local_ts_us is None:
            return self.frames[0]
        idx = bisect.bisect_right(self.local_ts_us, int(local_ts_us))
        if idx <= 0:
            return self.frames[0]
        return self.frames[idx - 1]


def quote_bid_ask(index: QuoteFrameIndex | None, frame: dict[str, Any]) -> tuple[float | None, float | None]:
    if index is None:
        return frame_bid_ask(frame)
    ts = int(frame.get("local_ts_us") or frame.get("local_timestamp") or 0)
    quote = index.at_or_before(ts)
    return optional_float(quote.get("bid_px")), optional_float(quote.get("ask_px"))


def admission_thresholds_hash(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_admission_thresholds(repo_root: Path, args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    if not args.admission_thresholds_json:
        return {}
    path = resolve_path(repo_root, args.admission_thresholds_json)
    raw = read_json(path)
    rows = raw.get("thresholds", raw)
    if not isinstance(rows, dict):
        raise ValueError("admission thresholds JSON must be an object or contain object field 'thresholds'")
    out: dict[str, dict[str, Any]] = {}
    for day, value in rows.items():
        if isinstance(value, dict):
            threshold = optional_float(
                value.get("entry_cross_threshold_bps")
                if "entry_cross_threshold_bps" in value
                else value.get("threshold_bps")
            )
            source = value.get("threshold_source") or value.get("source")
        else:
            threshold = optional_float(value)
            source = None
        if threshold is None:
            raise ValueError(f"missing admission threshold for {day}")
        out[str(day)] = {
            "entry_cross_threshold_bps": threshold,
            "threshold_source": source or f"{path.name}:{day}",
        }
    return out


def admission_gate_for_day(
    args: argparse.Namespace,
    thresholds: dict[str, dict[str, Any]],
    day: str,
) -> EntrySpreadAdmissionGate:
    if args.admission_profile == "none":
        return build_admission_gate(admission_profile="none")
    row = thresholds.get(day, {})
    threshold = row.get("entry_cross_threshold_bps", args.admission_entry_cross_threshold_bps)
    source = row.get("threshold_source") or args.admission_threshold_source or None
    return build_admission_gate(
        admission_profile=args.admission_profile,
        entry_cross_threshold_bps=threshold,
        threshold_source=source,
    )


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def frame_bid_ask(frame: dict[str, Any]) -> tuple[float | None, float | None]:
    bid = optional_float(frame.get("best_bid_price") or frame.get("bid_px") or frame.get("bid"))
    ask = optional_float(frame.get("best_ask_price") or frame.get("ask_px") or frame.get("ask"))
    return bid, ask


def side_mid_to_taker_bps(
    *,
    side: str,
    direction: int,
    entry_mid: float,
    exit_mid: float,
    entry_bid: float | None,
    entry_ask: float | None,
    exit_bid: float | None,
    exit_ask: float | None,
) -> float:
    if side == "buy":
        entry_fill = entry_ask
        exit_fill = exit_bid
        if entry_fill is None or exit_fill is None or entry_fill <= 0.0 or exit_fill <= 0.0:
            return direction * math.log(exit_mid / entry_mid) * 10_000.0
        return math.log(exit_fill / entry_fill) * 10_000.0
    entry_fill = entry_bid
    exit_fill = exit_ask
    if entry_fill is None or exit_fill is None or entry_fill <= 0.0 or exit_fill <= 0.0:
        return direction * math.log(exit_mid / entry_mid) * 10_000.0
    return math.log(entry_fill / exit_fill) * 10_000.0


@dataclass
class ManagerPathPosition:
    position_id: int
    entry_ts_us: int
    entry_mid: float
    entry_bid: float | None
    entry_ask: float | None
    direction: int
    side: str
    cell: str
    stopping_params: StoppingRuleParams | None = None
    h_bps: float = -math.inf
    peak_sec: float = math.nan
    last_exit_candidate: dict[str, Any] | None = None
    next_horizon_index: int = 0
    last_evaluated_horizon_index: int = -1
    mid_history: list[tuple[int, float]] | None = None

    def update(self, frame: dict[str, Any], exit_profile: str) -> dict[str, Any] | None:
        local_ts_us = int(frame.get("local_ts_us") or frame.get("local_timestamp") or 0)
        if local_ts_us <= self.entry_ts_us:
            return None
        hold_sec = (local_ts_us - self.entry_ts_us) / 1_000_000.0
        mid = optional_float(frame.get("mid_price") or frame.get("mid"))
        if mid is None or mid <= 0.0 or self.entry_mid <= 0.0:
            return None
        bid, ask = frame_bid_ask(frame)
        ret = self.direction * math.log(mid / self.entry_mid) * 10_000.0
        if self.mid_history is None:
            self.mid_history = []
        self.mid_history.append((local_ts_us, mid))
        if hold_sec > 60.0:
            if self.last_exit_candidate is None:
                return None
            return dict(self.last_exit_candidate)
        self.last_exit_candidate = {
            "exit_reason": "fixed_60s",
            "exit_sec": hold_sec,
            "exit_ts_us": local_ts_us,
            "exit_event_index": frame.get("event_index"),
            "exit_mid": mid,
            "exit_bid": bid,
            "exit_ask": ask,
            "policy_gross": ret,
            "H_exit": max(self.h_bps, ret) if math.isfinite(self.h_bps) else ret,
            "D_exit": 0.0,
            "tau_H_exit": hold_sec,
            "exit_threshold": math.nan,
        }
        if exit_profile == "stopping_rule_v1":
            return self._stopping_rule_update(
                frame=frame,
                hold_sec=hold_sec,
                local_ts_us=local_ts_us,
                mid=mid,
                bid=bid,
                ask=ask,
            )
        if exit_profile not in {"manager_path", "peakguard_taker_v1"} or self.cell != "11_r5_frames":
            return None
        if ret > self.h_bps + 1e-12:
            self.h_bps = ret
            self.peak_sec = hold_sec
            self.last_exit_candidate["H_exit"] = self.h_bps
            self.last_exit_candidate["tau_H_exit"] = self.peak_sec
        drawdown = self.h_bps - ret
        self.last_exit_candidate["D_exit"] = drawdown
        if self.h_bps < 4.0:
            return None
        if self.h_bps < 8.0 and self.peak_sec < 1.5:
            return None
        threshold = max(2.0, 0.35 * self.h_bps)
        if drawdown < threshold:
            return None
        return {
            "exit_reason": "release_drawdown",
            "exit_sec": hold_sec,
            "exit_ts_us": local_ts_us,
            "exit_event_index": frame.get("event_index"),
            "exit_mid": mid,
            "exit_bid": bid,
            "exit_ask": ask,
            "policy_gross": ret,
            "H_exit": self.h_bps,
            "D_exit": drawdown,
            "tau_H_exit": self.peak_sec,
            "exit_threshold": threshold,
        }

    def _stopping_rule_update(
        self,
        *,
        frame: dict[str, Any],
        hold_sec: float,
        local_ts_us: int,
        mid: float,
        bid: float | None,
        ask: float | None,
    ) -> dict[str, Any] | None:
        if self.stopping_params is None or self.direction == 0:
            return None
        elapsed_count = 0
        while (
            elapsed_count < len(STOPPING_RULE_HORIZONS_SEC)
            and hold_sec + 1e-9 >= STOPPING_RULE_HORIZONS_SEC[elapsed_count]
        ):
            elapsed_count += 1
        current_index = elapsed_count - 1
        if current_index < 0 or current_index <= self.last_evaluated_horizon_index:
            return None
        self.last_evaluated_horizon_index = current_index
        current_horizon = STOPPING_RULE_HORIZONS_SEC[current_index]
        taker_net, exit_cross = taker_net_and_exit_cross_bps(
            entry_side=self.side,
            entry_bid=self.entry_bid,
            entry_ask=self.entry_ask,
            current_bid=bid,
            current_ask=ask,
            current_mid=mid,
        )
        if taker_net is None or exit_cross is None:
            return None
        if taker_net > self.h_bps + 1e-12:
            self.h_bps = taker_net
            self.peak_sec = hold_sec
        drawdown = self.h_bps - taker_net
        recent_mid_alpha = self._recent_mid_alpha_5s(local_ts_us, mid)
        if not stopping_rule_should_exit(
            high_bps=self.h_bps,
            drawdown_bps=drawdown,
            exit_cross_bps=exit_cross,
            recent_mid_alpha_5s_bps=recent_mid_alpha,
            params=self.stopping_params,
        ):
            return None
        return {
            "exit_reason": "stopping_rule",
            "exit_sec": hold_sec,
            "exit_grid_sec": current_horizon,
            "exit_ts_us": local_ts_us,
            "exit_event_index": frame.get("event_index"),
            "exit_mid": mid,
            "exit_bid": bid,
            "exit_ask": ask,
            "policy_gross": self.direction * math.log(mid / self.entry_mid) * 10_000.0,
            "policy_taker_net_bps": taker_net,
            "H_exit": self.h_bps,
            "D_exit": drawdown,
            "tau_H_exit": self.peak_sec,
            "exit_threshold": max(self.stopping_params.d0, self.stopping_params.rho * max(self.h_bps, 0.0)),
            "exit_cross_bps": exit_cross,
            "recent_mid_alpha_5s_bps": recent_mid_alpha,
            "stopping_rule_params": self.stopping_params.to_dict(),
        }

    def _recent_mid_alpha_5s(self, local_ts_us: int, mid: float) -> float:
        if not self.mid_history:
            return 0.0
        target = local_ts_us - 5_000_000
        previous_mid = self.mid_history[0][1]
        for ts, value in self.mid_history:
            if ts <= target:
                previous_mid = value
            else:
                break
        if previous_mid <= 0.0 or mid <= 0.0:
            return 0.0
        return self.direction * math.log(mid / previous_mid) * 10_000.0


def cache_manifest_digest(repo_root: Path, symbol: str, day: str) -> dict[str, Any]:
    path = manifest_path(repo_root, symbol, day)
    manifest = read_json(path)
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


def load_and_guard_state(repo_root: Path, args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.shadow_state_in:
        return None
    path = resolve_path(repo_root, args.shadow_state_in)
    state = read_json(path)
    if state.get("next_expected_date") != args.from_date:
        raise ValueError(
            json.dumps(
                {
                    "error": "shadow_state_boundary_violation",
                    "reason": "fast backtest state must resume exactly at next_expected_date",
                    "state_path": str(path),
                    "state_after_date": state.get("state_after_date") or state.get("last_seen_date"),
                    "state_next_expected_date": state.get("next_expected_date"),
                    "requested_from_date": args.from_date,
                    "requested_to_date": args.to_date,
                },
                indent=2,
            )
        )
    return state


def process_closed(
    closed_now: list[dict[str, Any]],
    capacity: CapacityLedger,
    actual_by_position: dict[int, dict[str, Any]],
    exits: list[dict[str, Any]],
    daily: dict[str, dict[str, Any]],
    *,
    cost_bps: float,
    exit_profile: str,
    exit_frame: dict[str, Any] | None = None,
    path_result_by_position: dict[int, dict[str, Any]] | None = None,
) -> None:
    for close in closed_now:
        position_id = int(close["shadow_position_id"])
        entry = actual_by_position.pop(position_id, None)
        if entry is None:
            continue
        capacity.close(position_id)
        actual = float(entry["actual_exposure"])
        close_mid = float(close.get("close_mid") or 0.0)
        entry_mid = float(close.get("entry_mid") or entry.get("entry_mid") or 0.0)
        path_result = (path_result_by_position or {}).pop(position_id, None)
        if path_result is not None:
            if exit_profile in {"fixed60_taker", "peakguard_taker_v1", "stopping_rule_v1"}:
                raw_bps = side_mid_to_taker_bps(
                    side=str(close.get("side") or entry.get("side") or ""),
                    direction=int(close.get("direction") or 0),
                    entry_mid=entry_mid,
                    exit_mid=close_mid,
                    entry_bid=optional_float(entry.get("entry_bid")),
                    entry_ask=optional_float(entry.get("entry_ask")),
                    exit_bid=optional_float(path_result.get("exit_bid")),
                    exit_ask=optional_float(path_result.get("exit_ask")),
                )
            else:
                raw_bps = float(path_result.get("policy_gross") or 0.0)
            exit_reason = str(path_result.get("exit_reason") or "manager_path")
            exit_sec = path_result.get("exit_sec")
            close_seq = path_result.get("exit_event_index") or close.get("close_seq")
        elif exit_profile in {"fixed60_taker", "stopping_rule_v1"} and exit_frame is not None:
            exit_bid, exit_ask = frame_bid_ask(exit_frame)
            raw_bps = side_mid_to_taker_bps(
                side=str(close.get("side") or entry.get("side") or ""),
                direction=int(close.get("direction") or 0),
                entry_mid=entry_mid,
                exit_mid=close_mid,
                entry_bid=optional_float(entry.get("entry_bid")),
                entry_ask=optional_float(entry.get("entry_ask")),
                exit_bid=exit_bid,
                exit_ask=exit_ask,
            )
            exit_reason = "fixed60_taker"
            exit_sec = (float(close.get("held_us") or 0.0) / 1_000_000.0)
            close_seq = close.get("close_seq")
        else:
            raw_bps = float(close.get("pnl_bps") or 0.0)
            exit_reason = "fixed60_mid"
            exit_sec = (float(close.get("held_us") or 0.0) / 1_000_000.0)
            close_seq = close.get("close_seq")
        net_bps = raw_bps - cost_bps
        gross_weighted = actual * raw_bps
        net_weighted = actual * net_bps
        day = str(entry["date"])
        row = {
            "date": day,
            "shadow_position_id": position_id,
            "entry_seq": entry.get("entry_seq"),
            "close_seq": close_seq,
            "entry_ts_us": close.get("entry_ts_us"),
            "exit_ts_us": close.get("close_ts_us"),
            "held_us": close.get("held_us"),
            "exit_lag_us": close.get("exit_lag_us"),
            "exit_profile": exit_profile,
            "exit_reason": exit_reason,
            "exit_sec": exit_sec,
            "side": close.get("side"),
            "direction": close.get("direction"),
            "cell": close.get("cell"),
            "membership_set": close.get("membership_set"),
            "entry_mid": entry_mid,
            "exit_mid": close_mid,
            "entry_bid": entry.get("entry_bid"),
            "entry_ask": entry.get("entry_ask"),
            "exit_bid": (
                path_result.get("exit_bid")
                if path_result is not None
                else (frame_bid_ask(exit_frame)[0] if exit_frame is not None else None)
            ),
            "exit_ask": (
                path_result.get("exit_ask")
                if path_result is not None
                else (frame_bid_ask(exit_frame)[1] if exit_frame is not None else None)
            ),
            "requested_exposure": entry["requested_exposure"],
            "actual_exposure": actual,
            "clipped_exposure": entry["clipped_exposure"],
            "skipped": entry["skipped"],
            "open_exposure_before": entry["open_exposure_before"],
            "open_exposure_after": entry["open_exposure_after"],
            "capacity_profile": entry.get("capacity_profile"),
            "capacity_source": entry.get("capacity_source"),
            "idle_capacity_before": entry.get("idle_capacity_before"),
            "core_displacement": entry.get("core_displacement"),
            "raw_bps_mid_fixed60": float(close.get("pnl_bps") or 0.0),
            "raw_bps": raw_bps,
            "fee_bps": entry["fee_bps"],
            "pressure_bps": entry["pressure_bps"],
            "slippage_bps": entry["slippage_bps"],
            "cost_bps": cost_bps,
            "net_bps_after_cost": net_bps,
            "gross_weighted_bps": gross_weighted,
            "net_weighted_bps": net_weighted,
        }
        exits.append(row)
        day_stats = daily.setdefault(day, new_day_stats(day))
        day_stats["exits"] += 1
        day_stats["gross_weighted_bps"] += gross_weighted
        day_stats["net_weighted_bps"] += net_weighted
        if actual > 0.0:
            day_stats["worst_actual_leg_net_bps"] = min(
                day_stats["worst_actual_leg_net_bps"],
                net_weighted,
            )
            day_stats["worst_unit_net_bps"] = min(day_stats["worst_unit_net_bps"], net_bps)


def process_manager_path_frame(
    frame: dict[str, Any],
    quote_index: QuoteFrameIndex | None,
    capacity: CapacityLedger,
    actual_by_position: dict[int, dict[str, Any]],
    manager_positions: dict[int, ManagerPathPosition],
    exits: list[dict[str, Any]],
    daily: dict[str, dict[str, Any]],
    *,
    cost_bps: float,
    exit_profile: str,
) -> None:
    if not manager_positions:
        return
    local_ts_us = int(frame.get("local_ts_us") or frame.get("local_timestamp") or 0)
    mid = optional_float(frame.get("mid_price") or frame.get("mid"))
    if local_ts_us <= 0 or mid is None or mid <= 0.0:
        return
    eval_frame = frame
    if exit_profile == "stopping_rule_v1" and quote_index is not None:
        quote = quote_index.at_or_before(local_ts_us)
        eval_frame = dict(frame)
        eval_frame["best_bid_price"] = quote.get("bid_px")
        eval_frame["best_ask_price"] = quote.get("ask_px")
        eval_frame["mid_price"] = quote.get("mid_px")
        eval_frame["mid"] = quote.get("mid_px")
        eval_frame["spread_bps"] = quote.get("spread_bps")
    to_close: list[tuple[int, dict[str, Any]]] = []
    for position_id, state in list(manager_positions.items()):
        result = state.update(eval_frame, exit_profile)
        if result is not None:
            to_close.append((position_id, result))
    for position_id, result in to_close:
        entry = actual_by_position.get(position_id)
        if entry is None:
            manager_positions.pop(position_id, None)
            continue
        exit_ts_us = int(result.get("exit_ts_us") or local_ts_us)
        exit_mid = float(result.get("exit_mid") or mid)
        exit_quote = quote_index.at_or_before(exit_ts_us) if quote_index is not None else None
        if exit_quote is not None:
            result["exit_bid"] = exit_quote.get("bid_px")
            result["exit_ask"] = exit_quote.get("ask_px")
        close = {
            "shadow_position_id": position_id,
            "entry_seq": entry.get("entry_seq"),
            "close_seq": result.get("exit_event_index") or frame.get("event_index"),
            "entry_ts_us": entry.get("entry_ts_us"),
            "due_ts_us": entry.get("due_ts_us"),
            "close_ts_us": exit_ts_us,
            "held_us": exit_ts_us - int(entry.get("entry_ts_us") or exit_ts_us),
            "exit_lag_us": exit_ts_us - int(entry.get("due_ts_us") or exit_ts_us),
            "entry_mid": entry.get("entry_mid"),
            "close_mid": exit_mid,
            "direction": entry.get("direction"),
            "side": entry.get("side"),
            "direction_label": "long" if int(entry.get("direction") or 0) > 0 else "short",
            "pnl_bps": result.get("policy_gross"),
            "trigger_classes": str(entry.get("trigger_classes") or "").split("+"),
            "membership_set": entry.get("membership_set"),
            "cell": entry.get("cell"),
            "base_weight": entry.get("base_weight"),
            "weak_overlay_weight": entry.get("weak_overlay_weight"),
            "gamma": entry.get("gamma"),
            "target_exposure": entry.get("requested_exposure"),
            "entry_spread_bps": entry.get("entry_spread_bps"),
        }
        process_closed(
            [close],
            capacity,
            actual_by_position,
            exits,
            daily,
            cost_bps=cost_bps,
            exit_profile=exit_profile,
            exit_frame=frame,
            path_result_by_position={position_id: result},
        )
        manager_positions.pop(position_id, None)


def new_day_stats(day: str) -> dict[str, Any]:
    return {
        "date": day,
        "frames": 0,
        "entries": 0,
        "admission_accepted_entries": 0,
        "admission_rejected_entries": 0,
        "exits": 0,
        "requested_exposure": 0.0,
        "actual_exposure": 0.0,
        "clipped_exposure": 0.0,
        "clipped_entries": 0,
        "skipped_entries": 0,
        "gross_weighted_bps": 0.0,
        "net_weighted_bps": 0.0,
        "max_open_exposure": 0.0,
        "worst_actual_leg_net_bps": math.inf,
        "worst_unit_net_bps": math.inf,
    }


def add_entry(
    signal: dict[str, Any],
    day: str,
    capacity: CapacityLedger,
    args: argparse.Namespace,
    actual_by_position: dict[int, dict[str, Any]],
    manager_positions: dict[int, ManagerPathPosition],
    entries: list[dict[str, Any]],
    daily: dict[str, dict[str, Any]],
    frame: dict[str, Any],
    quote_index: QuoteFrameIndex | None,
    admission_gate: EntrySpreadAdmissionGate,
    stopping_params_by_date: dict[str, StoppingRuleParams] | None = None,
) -> None:
    admission = admission_gate.decide(signal).to_dict()
    signal["admission_decision"] = admission
    if admission["accepted"]:
        decision = capacity.decide(signal).to_dict()
    else:
        decision = capacity.reject_decision(signal, capacity_source="admission_reject").to_dict()
    signal["capacity_decision"] = decision
    requested = float(decision["requested_exposure"])
    actual = float(decision["actual_exposure"])
    clipped = float(decision["clipped_exposure"])
    skipped = bool(decision["skipped"])
    position_id = int(signal["shadow_position_id"])
    entry_bid, entry_ask = quote_bid_ask(quote_index, frame)
    entry_mid = signal.get("entry_mid") or frame.get("mid_price") or frame.get("mid")
    row = {
        "date": day,
        "shadow_position_id": position_id,
        "entry_seq": signal.get("observed_seq"),
        "entry_ts_us": signal.get("entry_ts_us") or signal.get("local_ts_us"),
        "due_ts_us": signal.get("entry_due_ts_us"),
        "side": signal.get("side"),
        "direction": signal.get("direction"),
        "cell": signal.get("cell"),
        "membership_set": signal.get("membership_set"),
        "trigger_classes": "+".join(signal.get("trigger_classes") or []),
        "entry_mid": entry_mid,
        "entry_bid": entry_bid,
        "entry_ask": entry_ask,
        "entry_spread_bps": signal.get("entry_spread_bps"),
        "entry_cross_bps": admission.get("entry_cross_bps"),
        "admission_profile": admission.get("admission_profile"),
        "admission_accepted": admission.get("accepted"),
        "admission_reason": admission.get("reason"),
        "admission_entry_cross_threshold_bps": admission.get("entry_cross_threshold_bps"),
        "admission_threshold_source": admission.get("threshold_source"),
        "a_r5_raw": signal.get("a_r5_raw"),
        "a_r5_ready": signal.get("a_r5_ready"),
        "b_frames_ge_q90": signal.get("b_frames_ge_q90"),
        "base_weight": signal.get("base_weight"),
        "weak_overlay_weight": signal.get("weak_overlay_weight"),
        "gamma": signal.get("gamma"),
        "requested_exposure": requested,
        "actual_exposure": actual,
        "clipped_exposure": clipped,
        "skipped": skipped,
        "open_exposure_before": decision["open_exposure_before"],
        "open_exposure_after": decision["open_exposure_after"],
        "leverage_cap": decision["leverage_cap"],
        "capacity_profile": decision.get("capacity_profile"),
        "capacity_source": decision.get("capacity_source"),
        "idle_capacity_before": decision.get("idle_capacity_before"),
        "core_displacement": decision.get("core_displacement"),
        "capacity_reserve": decision.get("reserve"),
        "fee_bps": args.fee_bps,
        "pressure_bps": args.pressure_bps,
        "slippage_bps": args.slippage_bps,
    }
    entries.append(row)
    actual_by_position[position_id] = row
    if actual > 0.0:
        manager_positions[position_id] = ManagerPathPosition(
            position_id=position_id,
            entry_ts_us=int(row["entry_ts_us"] or 0),
            entry_mid=float(entry_mid or 0.0),
            entry_bid=optional_float(entry_bid),
            entry_ask=optional_float(entry_ask),
            direction=int(signal.get("direction") or 0),
            side=str(signal.get("side") or ""),
            cell=str(signal.get("cell") or ""),
            stopping_params=(stopping_params_by_date or {}).get(day),
        )
    day_stats = daily.setdefault(day, new_day_stats(day))
    day_stats["entries"] += 1
    day_stats["admission_accepted_entries"] += 1 if admission.get("accepted") else 0
    day_stats["admission_rejected_entries"] += 0 if admission.get("accepted") else 1
    day_stats["requested_exposure"] += requested
    day_stats["actual_exposure"] += actual
    day_stats["clipped_exposure"] += clipped
    day_stats["clipped_entries"] += 1 if clipped > 1e-12 else 0
    day_stats["skipped_entries"] += 1 if skipped else 0
    day_stats["max_open_exposure"] = max(day_stats["max_open_exposure"], capacity.open_exposure)


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


def clean_daily_rows(daily: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for day in sorted(daily):
        row = dict(daily[day])
        for key in ["worst_actual_leg_net_bps", "worst_unit_net_bps"]:
            if math.isinf(float(row[key])):
                row[key] = None
        rows.append(row)
    return rows


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    days = date_range(args.from_date, args.to_date)
    run_id = args.run_id or f"fast_strategy_backtest_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir = (
        repo_root
        / "systems"
        / "ccusdt_replay_exchange"
        / "runs"
        / "experiments"
        / run_id
    )
    out_dir.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    timing_ms: dict[str, int] = {}
    state_start = time.perf_counter()
    state = load_and_guard_state(repo_root, args)
    timing_ms["state_load_guard_ms"] = int((time.perf_counter() - state_start) * 1000)
    gamma_overrides: dict[str, float] = {}
    if args.gamma01_override is not None:
        gamma_overrides["01_frames_only"] = max(0.0, float(args.gamma01_override))
    elif args.capacity_profile == "core_idle01" and args.idle01_gamma is not None:
        gamma_overrides["01_frames_only"] = max(0.0, float(args.idle01_gamma))
    policy = ShadowFourCellPolicy(
        frames_threshold=args.frames_threshold,
        overlay_threshold=args.overlay_threshold,
        fixed_exit_us=args.fixed_exit_us,
        gamma_preset=args.gamma_preset,
        gamma_overrides=gamma_overrides,
    )
    if state is not None:
        policy.load_state(state)
    entries: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    daily: dict[str, dict[str, Any]] = {}
    actual_by_position: dict[int, dict[str, Any]] = {}
    manager_positions: dict[int, ManagerPathPosition] = {}
    capacity = build_capacity_allocator(
        capacity_profile=args.capacity_profile,
        leverage_cap=args.leverage_cap,
        idle01_gamma=args.idle01_gamma,
        idle01_reserve=args.idle01_reserve,
    )
    cost_bps = float(args.fee_bps + args.pressure_bps + args.slippage_bps)
    admission_thresholds = load_admission_thresholds(repo_root, args)
    admission_threshold_file = (
        resolve_path(repo_root, args.admission_thresholds_json)
        if args.admission_thresholds_json
        else None
    )
    admission_threshold_file_hash = admission_thresholds_hash(admission_threshold_file)
    stopping_params_file = (
        resolve_path(repo_root, args.stopping_rule_params_json)
        if args.stopping_rule_params_json
        else None
    )
    stopping_params_by_date = load_stopping_rule_params_by_date(stopping_params_file)
    manifest_start = time.perf_counter()
    data_manifests = [cache_manifest_digest(repo_root, args.symbol, day) for day in days]
    timing_ms["manifest_read_ms"] = int((time.perf_counter() - manifest_start) * 1000)
    frames_read_ms = 0
    policy_eval_ms = 0
    manager_path_ms = 0

    for day in days:
        admission_gate = admission_gate_for_day(args, admission_thresholds, day)
        quote_index = (
            QuoteFrameIndex.load(repo_root, args.symbol, day)
            if args.exit_profile in {"fixed60_taker", "peakguard_taker_v1", "stopping_rule_v1"}
            else None
        )
        policy.start_new_day()
        day_stats = daily.setdefault(day, new_day_stats(day))
        day_stats["max_open_exposure"] = max(day_stats["max_open_exposure"], capacity.open_exposure)
        seq = 0
        frame_iter = iter_cached_decision_frames(repo_root, args.symbol, day)
        while True:
            read_start = time.perf_counter()
            try:
                frame = next(frame_iter)
            except StopIteration:
                break
            frames_read_ms += int((time.perf_counter() - read_start) * 1_000_000)
            manager_start = time.perf_counter()
            process_manager_path_frame(
                frame,
                quote_index,
                capacity,
                actual_by_position,
                manager_positions,
                exits,
                daily,
                cost_bps=cost_bps,
                exit_profile=args.exit_profile,
            )
            manager_path_ms += int((time.perf_counter() - manager_start) * 1_000_000)
            policy_start = time.perf_counter()
            signal = policy.on_decision_frame(frame, seq)
            policy_eval_ms += int((time.perf_counter() - policy_start) * 1_000_000)
            day_stats["frames"] += 1
            if signal is not None:
                process_closed(
                    signal.get("closed_now") or [],
                    capacity,
                    actual_by_position,
                    exits,
                    daily,
                    cost_bps=cost_bps,
                    exit_profile=args.exit_profile,
                    exit_frame=(
                        quote_index.at_or_before(int(frame.get("local_ts_us") or frame.get("local_timestamp") or 0))
                        if quote_index is not None
                        else frame
                    ),
                )
                for close in signal.get("closed_now") or []:
                    try:
                        manager_positions.pop(int(close["shadow_position_id"]), None)
                    except (KeyError, TypeError, ValueError):
                        pass
                if signal.get("event_kind") == "shadow_entry":
                    signal["entry_mid"] = frame.get("mid_price") or frame.get("mid")
                    add_entry(
                        signal,
                        day,
                        capacity,
                        args,
                        actual_by_position,
                        manager_positions,
                        entries,
                        daily,
                        frame,
                        quote_index,
                        admission_gate,
                        stopping_params_by_date,
                    )
            seq += 1
            if args.progress_interval > 0 and seq % args.progress_interval == 0:
                print(
                    f"fast backtest day={day} frames={seq} entries={day_stats['entries']}",
                    file=sys.stderr,
                    flush=True,
                )

    timing_ms["frame_decode_us"] = frames_read_ms
    timing_ms["policy_eval_us"] = policy_eval_ms
    timing_ms["manager_path_us"] = manager_path_ms
    manifest_build_start = time.perf_counter()
    data_manifest = {
        "schema_id": "ccusdt_fast_backtest_data_manifest_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "input_dataset": "decision_frame_v1_parquet_cache",
        "input_manifests": data_manifests,
    }
    policy_manifest = {
        "schema_id": "ccusdt_fast_backtest_policy_manifest_v1",
        "policy": "old_tfi_four_cell_shadow_v1",
        "policy_profile": "old_tfi_four_cell_shadow_v1",
        "policy_params": policy.policy_params(),
        "policy_params_hash": policy.policy_params_hash(),
        "state_in": str(args.shadow_state_in) if args.shadow_state_in else None,
        "state_in_data_manifest_hash": (state or {}).get("data_manifest_hash"),
    }
    profile_manifest = build_profile_manifest(
        policy_profile={
            "name": "old_tfi_four_cell_shadow_v1",
            "decision_clock": "decision_frame_v1",
            "params": policy.policy_params(),
            "params_hash": policy.policy_params_hash(),
        },
        capacity_profile={
            "name": args.capacity_profile,
            "leverage_cap": args.leverage_cap,
            "idle01_gamma": args.idle01_gamma,
            "idle01_reserve": args.idle01_reserve,
            "admission_profile": args.admission_profile,
            "admission_entry_cross_threshold_bps": args.admission_entry_cross_threshold_bps,
            "admission_threshold_source": args.admission_threshold_source or None,
            "admission_thresholds_json": (
                str(args.admission_thresholds_json) if args.admission_thresholds_json else None
            ),
            "admission_thresholds_sha256": admission_threshold_file_hash,
            "core_cells": ["00_none", "10_r5_only", "11_r5_frames"],
            "idle_cell": "01_frames_only" if args.capacity_profile == "core_idle01" else None,
            "rule": (
                "core cells use ordinary arrival/FIFO capacity; 01 uses only spare idle capacity"
                if args.capacity_profile == "core_idle01"
                else "ordinary arrival/FIFO capacity clip"
            ),
        },
        exit_profile={
            "name": args.exit_profile,
            "fixed_exit_us": args.fixed_exit_us,
            "manager_path_policy": (
                "pm_11_drawdown_h4_peakguard"
                if args.exit_profile in {"manager_path", "peakguard_taker_v1"}
                else None
            ),
            "stopping_rule_params_json": (
                str(args.stopping_rule_params_json) if args.stopping_rule_params_json else None
            ),
            "stopping_rule_dates": sorted(stopping_params_by_date),
        },
        fill_profile={
            "name": (
                "fast_quote_frame_taker_cross"
                if args.exit_profile in {"fixed60_taker", "peakguard_taker_v1", "stopping_rule_v1"}
                else "fast_mid_reference"
            ),
            "quote_source": (
                "canonical quote_frame_v1 at_or_before decision/exit local_ts_us"
                if args.exit_profile in {"fixed60_taker", "peakguard_taker_v1", "stopping_rule_v1"}
                else None
            ),
            "fee_bps": args.fee_bps,
            "pressure_bps": args.pressure_bps,
            "slippage_bps": args.slippage_bps,
        },
        latency_profile={
            "name": "fast_zero_latency_no_queue",
            "latency_us": 0,
        },
        transport_profile={
            "name": "fast_strategy_backtest_v1",
            "decision_frame_source": "decision_frame_v1_parquet_cache",
            "runtime_path": "python_fast_cache_scan",
        },
        data_profile={
            "name": "market_derived_decision_frame_cache_v1",
            "symbol": args.symbol,
            "from_date": args.from_date,
            "to_date": args.to_date,
            "data_manifest_hash": stable_json_hash(data_manifest),
            "state_in": str(args.shadow_state_in) if args.shadow_state_in else None,
            "state_in_data_manifest_hash": (state or {}).get("data_manifest_hash"),
            "input_manifests": data_manifests,
        },
    )
    timing_ms["manifest_build_ms"] = int((time.perf_counter() - manifest_build_start) * 1000)
    output_start = time.perf_counter()
    config = {
        "schema_id": "ccusdt_fast_strategy_backtest_config_v1",
        "run_id": run_id,
        "execution_approximation": f"{args.exit_profile}_{args.capacity_profile}_v1",
        "pnl_semantics": (
            "fixed60_mid: direction*log(exit_mid/entry_mid)*10000; "
            "fixed60_taker/peakguard_taker_v1/stopping_rule_v1: quote_frame_v1 top-of-book cross at entry/exit; "
            "then subtract fee_bps + pressure_bps + slippage_bps and weight by actual exposure"
        ),
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "leverage_cap": args.leverage_cap,
        "capacity_profile": args.capacity_profile,
        "admission_profile": args.admission_profile,
        "admission_entry_cross_threshold_bps": args.admission_entry_cross_threshold_bps,
        "admission_threshold_source": args.admission_threshold_source or None,
        "admission_thresholds_json": (
            str(args.admission_thresholds_json) if args.admission_thresholds_json else None
        ),
        "admission_thresholds_sha256": admission_threshold_file_hash,
        "exit_profile": args.exit_profile,
        "stopping_rule_params_json": (
            str(args.stopping_rule_params_json) if args.stopping_rule_params_json else None
        ),
        "fill_profile": profile_manifest["fill_profile"]["name"],
        "latency_profile": profile_manifest["latency_profile"]["name"],
        "fee_bps": args.fee_bps,
        "pressure_bps": args.pressure_bps,
        "slippage_bps": args.slippage_bps,
        "data_manifest_hash": stable_json_hash(data_manifest),
        "policy_manifest_hash": stable_json_hash(policy_manifest),
        "profile_manifest_hash": profile_manifest["profile_manifest_hash"],
    }
    daily_rows = clean_daily_rows(daily)
    net_total = sum(float(row["net_weighted_bps"]) for row in daily_rows)
    gross_total = sum(float(row["gross_weighted_bps"]) for row in daily_rows)
    summary = {
        "schema_id": "ccusdt_fast_strategy_backtest_summary_v1",
        "ok": True,
        "run_id": run_id,
        "run_dir": str(out_dir),
        "entries": len(entries),
        "exits": len(exits),
        "actual_entries": sum(1 for row in entries if float(row["actual_exposure"]) > 0.0),
        "admission_accepted_entries": sum(1 for row in entries if row.get("admission_accepted")),
        "admission_rejected_entries": sum(
            1 for row in entries if row.get("admission_accepted") is False
        ),
        "skipped_entries": sum(1 for row in entries if row["skipped"]),
        "clipped_entries": sum(1 for row in entries if float(row["clipped_exposure"]) > 1e-12),
        "gross_weighted_bps": gross_total,
        "net_weighted_bps": net_total,
        "profile_manifest_hash": profile_manifest["profile_manifest_hash"],
        "policy_profile": profile_manifest["policy_profile"]["name"],
        "capacity_profile": args.capacity_profile,
        "admission_profile": args.admission_profile,
        "exit_profile": args.exit_profile,
        "fill_profile": profile_manifest["fill_profile"]["name"],
        "latency_profile": profile_manifest["latency_profile"]["name"],
        "positive_days": sum(1 for row in daily_rows if float(row["net_weighted_bps"]) > 0.0),
        "days": len(daily_rows),
        "max_open_exposure": max((float(row["max_open_exposure"]) for row in daily_rows), default=0.0),
        "worst_day_net_weighted_bps": min(
            (float(row["net_weighted_bps"]) for row in daily_rows),
            default=0.0,
        ),
        "worst_actual_leg_net_bps": min(
            (float(row["worst_actual_leg_net_bps"]) for row in daily_rows if row["worst_actual_leg_net_bps"] is not None),
            default=0.0,
        ),
        "open_positions_at_end": len(actual_by_position),
        "open_exposure_at_end": capacity.open_exposure,
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
        "timing_ms": timing_ms,
        "outputs": {
            "config_json": str(out_dir / "config.json"),
            "data_manifest_json": str(out_dir / "data_manifest.json"),
            "policy_manifest_json": str(out_dir / "policy_manifest.json"),
            "profile_manifest_json": str(out_dir / "profile_manifest.json"),
            "summary_json": str(out_dir / "summary.json"),
            "daily_csv": str(out_dir / "daily.csv"),
            "entries_parquet": str(out_dir / "entries.parquet"),
            "exits_parquet": str(out_dir / "exits.parquet"),
        },
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (out_dir / "data_manifest.json").write_text(json.dumps(data_manifest, indent=2), encoding="utf-8")
    (out_dir / "policy_manifest.json").write_text(json.dumps(policy_manifest, indent=2), encoding="utf-8")
    (out_dir / "profile_manifest.json").write_text(json.dumps(profile_manifest, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(out_dir / "daily.csv", daily_rows)
    write_parquet(out_dir / "entries.parquet", entries)
    write_parquet(out_dir / "exits.parquet", exits)
    timing_ms["output_write_ms"] = int((time.perf_counter() - output_start) * 1000)
    summary["elapsed_wall_ms"] = int((time.perf_counter() - start) * 1000)
    summary["timing_ms"] = timing_ms
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

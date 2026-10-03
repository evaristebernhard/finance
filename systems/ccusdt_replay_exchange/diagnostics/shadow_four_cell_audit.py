#!/usr/bin/env python
"""Audit the runtime-safe CCUSDT four-cell shadow policy.

The runtime path is Runner -> Python strategy stdin/stdout -> compact event log.
This diagnostic may read legacy research CSVs only as offline references. The
Bot itself receives only exchange-visible canonical market events.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any


HIST_REFERENCE = (
    "ccusdt_v1_tfi_pretrade_scored_entries_"
    "20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv"
)
OOS_0518_REFERENCE = (
    "ccusdt_v1_tfi_pretrade_scored_entries_"
    "20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--max-events", type=int, default=300_000)
    parser.add_argument("--window-us", type=int, default=2_000_000)
    parser.add_argument("--frames-threshold", type=float, default=31.0)
    parser.add_argument("--overlay-threshold", type=float, default=59.80000000000018)
    parser.add_argument("--fixed-exit-us", type=int, default=60_000_000)
    parser.add_argument("--gamma-preset", default="core_q70")
    parser.add_argument("--run-prefix", default="shadow_four_cell_audit")
    parser.add_argument("--mode", choices=["runner", "direct"], default="runner")
    parser.add_argument("--decision-clock", choices=["quote", "panel"], default="panel")
    parser.add_argument("--clock-mode", choices=["deterministic-step", "accelerated-async"], default="accelerated-async")
    parser.add_argument("--l2-batch-size", type=int, default=1000)
    parser.add_argument("--compact-l2", action="store_true")
    parser.add_argument("--warmup-reference-r5", action="store_true")
    parser.add_argument("--warmup-from-date")
    parser.add_argument("--decision-frame-source", choices=["canonical", "cache"], default="cache")
    parser.add_argument("--progress-interval", type=int, default=50_000)
    parser.add_argument("--shadow-state-in", type=Path)
    parser.add_argument("--skip-run", action="store_true")
    parser.add_argument("--run-dir", action="append", type=Path, default=[])
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


def run_command(command: list[str], cwd: Path, timeout_s: int | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    process = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    if process.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "command": command,
                    "returncode": process.returncode,
                    "stdout_tail": process.stdout[-4000:],
                    "stderr_tail": process.stderr[-4000:],
                },
                indent=2,
            )
        )
    return {"stdout": process.stdout, "stderr": process.stderr, "elapsed_ms": elapsed_ms}


def parse_last_json(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    start = text.rfind("\n{")
    if start >= 0:
        text = text[start + 1 :]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object from runner")
    return parsed


def run_shadow_day(repo_root: Path, args: argparse.Namespace, day: str, timestamp: str) -> dict[str, Any]:
    run_id = f"{args.run_prefix}_{day.replace('-', '')}_{timestamp}"
    command = [
        "cargo",
        "run",
        "--manifest-path",
        "systems/quant_replay_engine/Cargo.toml",
        "-p",
        "quant_replay_cli",
        "--",
        "run",
        "sparse-python",
        "--repo-root",
        ".",
        "--symbol",
        args.symbol,
        "--canonical-date",
        day,
        "--run-id",
        run_id,
        "--max-events",
        str(args.max_events),
        "--latency-us",
        "0",
        "--clock-mode",
        args.clock_mode,
        "--l2-batch-size",
        str(args.l2_batch_size),
        "--strategy-arg=--window-us",
        f"--strategy-arg={args.window_us}",
        "--strategy-arg=--decision-clock",
        f"--strategy-arg={args.decision_clock}",
        "--strategy-arg=--decision-trade-window-us",
        f"--strategy-arg={args.window_us}",
        "--strategy-arg=--max-orders",
        "--strategy-arg=0",
        "--strategy-arg=--heartbeat-interval-us",
        "--strategy-arg=999999999999",
        "--strategy-arg=--shadow-four-cell",
        "--strategy-arg=--shadow-frames-threshold",
        f"--strategy-arg={args.frames_threshold}",
        "--strategy-arg=--shadow-overlay-threshold",
        f"--strategy-arg={args.overlay_threshold}",
        "--strategy-arg=--shadow-fixed-exit-us",
        f"--strategy-arg={args.fixed_exit_us}",
        "--strategy-arg=--shadow-gamma-preset",
        f"--strategy-arg={args.gamma_preset}",
    ]
    if args.warmup_reference_r5:
        seed = seed_closed_bps_for_day(repo_root, day, args.fixed_exit_us)
        if seed:
            command.extend(
                [
                    "--strategy-arg="
                    f"--shadow-seed-closed-bps={','.join(f'{value:.12g}' for value in seed)}",
                ]
            )
    if args.shadow_state_in:
        command.extend(
            [
                "--strategy-arg=--shadow-state-in",
                f"--strategy-arg={str(args.shadow_state_in)}",
            ]
        )
    if args.decision_clock == "panel":
        command.append("--include-l2")
    if args.compact_l2:
        command.append("--compact-l2")
    result = run_command(command, repo_root, timeout_s=600)
    summary = parse_last_json(result["stdout"])
    summary["elapsed_wall_ms"] = result["elapsed_ms"]
    return summary


def strategy_modules(repo_root: Path) -> tuple[Any, Any]:
    path = (
        repo_root
        / "systems"
        / "ccusdt_replay_exchange"
        / "strategies"
        / "python"
        / "ccusdt_tfi_core_idle01"
    )
    sys.path.insert(0, str(path))
    from online_features import OnlineFeatureState
    from shadow_policy import ShadowFourCellPolicy

    return OnlineFeatureState, ShadowFourCellPolicy


def canonical_path(repo_root: Path, symbol: str, dataset: str, day: str) -> Path:
    return (
        repo_root
        / "data"
        / "canonical"
        / "cex"
        / "bullish"
        / symbol
        / dataset
        / f"dt={day}"
        / "part_000001.csv.gz"
    )


def open_rows(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    with gzip.open(path, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


def quote_iter(path: Path) -> Any:
    for row in open_rows(path):
        yield {
            "kind": "quote",
            "local_ts_us": int(row["local_ts_us"]),
            "quote": {
                "bid": float(row["bid_px"]),
                "ask": float(row["ask_px"]),
                "mid": float(row["mid_px"]),
            },
        }


def trade_iter(path: Path) -> Any:
    for row in open_rows(path):
        yield {
            "kind": "trade",
            "local_ts_us": int(row["local_ts_us"]),
            "trade": {
                "local_ts_us": int(row["local_ts_us"]),
                "side": row["side"],
                "price": float(row["price"]),
                "qty": float(row["qty"]),
            },
        }


def next_or_none(iterator: Any) -> Any | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def choose_next(items: list[Any | None]) -> int | None:
    keys: list[tuple[int, tuple[int, int]]] = []
    for idx, item in enumerate(items):
        if item is not None:
            keys.append((idx, (int(item["local_ts_us"]), idx)))
    if not keys:
        return None
    return min(keys, key=lambda pair: pair[1])[0]


def direct_shadow_day(
    repo_root: Path,
    args: argparse.Namespace,
    day: str,
    timestamp: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    OnlineFeatureState, ShadowFourCellPolicy = strategy_modules(repo_root)
    if args.decision_clock == "panel":
        return direct_panel_shadow_day(repo_root, args, day, timestamp, ShadowFourCellPolicy)
    state = OnlineFeatureState(window_us=args.window_us, closed_window=5)
    policy = ShadowFourCellPolicy(
        frames_threshold=args.frames_threshold,
        overlay_threshold=args.overlay_threshold,
        fixed_exit_us=args.fixed_exit_us,
        gamma_preset=args.gamma_preset,
    )
    load_shadow_state_if_requested(repo_root, args, policy)
    q_iter = quote_iter(canonical_path(repo_root, args.symbol, "quote_frame_v1", day))
    t_iter = trade_iter(canonical_path(repo_root, args.symbol, "trade_event_v1", day))
    items = [next_or_none(q_iter), next_or_none(t_iter)]
    entries: list[dict[str, Any]] = []
    closes: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seq = 0
    quote_seq = 0
    trade_count = 0
    quote_count = 0
    start = time.perf_counter()

    def record_signal(signal: dict[str, Any] | None, event_seq: int, local_ts: int) -> None:
        if signal is None:
            return
        kind = signal.get("event_kind")
        counts[str(kind)] += 1
        checkpoint_type = "shadow_four_cell_trigger" if kind == "shadow_entry" else "shadow_lifecycle_close"
        snapshot = state.snapshot(event_seq, local_ts, checkpoint_type)
        if kind == "shadow_entry":
            snapshot["four_cell_inputs"].update(
                {
                    "a_r5_gt_1": signal["a_r5_gt_1"],
                    "r5": signal["a_r5_raw"],
                    "r5_ready": signal["a_r5_ready"],
                    "b_threshold": signal["b_threshold"],
                    "b_frames_ge_threshold": signal["b_frames_ge_q90"],
                    "cell": signal["cell"],
                }
            )
        snapshot["shadow_signal"] = signal
        row = {
            "event_id": event_seq,
            "run_id": f"{args.run_prefix}_{day.replace('-', '')}_{timestamp}_direct",
            "run_dir": "",
            "reason": checkpoint_type,
            **flatten_signal(signal),
            "feature_mismatch_count": feature_mismatch_count(snapshot, signal),
            "date": day,
        }
        if kind == "shadow_entry":
            entries.append(row)
        elif kind == "shadow_lifecycle_close":
            closes.append(row)

    while True:
        idx = choose_next(items)
        if idx is None or seq >= args.max_events:
            break
        item = items[idx]
        assert item is not None
        local_ts_us = int(item["local_ts_us"])
        if item["kind"] == "quote":
            state.observe_envelope({"seq": seq, "local_ts_us": local_ts_us, "quote_seq": quote_seq})
            state.update_quote(item["quote"])
            state.trim(local_ts_us)
            record_signal(policy.on_quote(state, seq, local_ts_us), seq, local_ts_us)
            quote_count += 1
            quote_seq += 1
            items[idx] = next_or_none(q_iter)
        else:
            trade = item["trade"]
            state.observe_envelope({"seq": seq, "local_ts_us": local_ts_us, "quote_seq": quote_seq})
            state.add_trade(
                local_ts_us=int(trade["local_ts_us"]),
                side=str(trade["side"]),
                qty=float(trade["qty"]),
                price=float(trade["price"]),
            )
            state.trim(local_ts_us)
            record_signal(policy.on_quote(state, seq, local_ts_us), seq, local_ts_us)
            trade_count += 1
            items[idx] = next_or_none(t_iter)
        seq += 1
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    summary = {
        "run_id": f"{args.run_prefix}_{day.replace('-', '')}_{timestamp}_direct",
        "run_dir": "",
        "source_label": f"direct_canonical_online_shadow_v1:{args.symbol}:{day}",
        "events_seen": seq,
        "quote_events_seen": quote_count,
        "trade_events_seen": trade_count,
        "event_count": len(entries) + len(closes),
        "intents_created": 0,
        "orders_submitted": 0,
        "fills_created": 0,
        "direct_mode": True,
        "elapsed_wall_ms": elapsed_ms,
    }
    return summary, entries, closes, dict(counts)


def direct_panel_shadow_day(
    repo_root: Path,
    args: argparse.Namespace,
    day: str,
    timestamp: str,
    ShadowFourCellPolicy: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    policy = ShadowFourCellPolicy(
        frames_threshold=args.frames_threshold,
        overlay_threshold=args.overlay_threshold,
        fixed_exit_us=args.fixed_exit_us,
        gamma_preset=args.gamma_preset,
    )
    load_shadow_state_if_requested(repo_root, args, policy)
    entries: list[dict[str, Any]] = []
    closes: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seq = 0
    start = time.perf_counter()

    def record_signal(signal: dict[str, Any] | None, frame: dict[str, Any], event_seq: int) -> None:
        if signal is None:
            return
        kind = signal.get("event_kind")
        counts[str(kind)] += 1
        checkpoint_type = (
            "shadow_four_cell_panel_trigger"
            if kind == "shadow_entry"
            else "shadow_panel_lifecycle_close"
        )
        snapshot = {
            "schema_id": "ccusdt_online_feature_snapshot_v1",
            "runtime_safe": True,
            "checkpoint": checkpoint_type,
            "observed_seq": event_seq,
            "local_ts_us": frame.get("local_ts_us"),
            "decision_frame": frame,
            "four_cell_inputs": {},
        }
        if kind == "shadow_entry":
            snapshot["four_cell_inputs"].update(
                {
                    "a_r5_gt_1": signal["a_r5_gt_1"],
                    "r5": signal["a_r5_raw"],
                    "r5_ready": signal["a_r5_ready"],
                    "b_threshold": signal["b_threshold"],
                    "b_frames_ge_threshold": signal["b_frames_ge_q90"],
                    "cell": signal["cell"],
                }
            )
        snapshot["shadow_signal"] = signal
        row = {
            "event_id": event_seq,
            "run_id": f"{args.run_prefix}_{day.replace('-', '')}_{timestamp}_direct_panel",
            "run_dir": "",
            "reason": checkpoint_type,
            **flatten_signal(signal),
            "entry_event_index": signal.get("entry_event_index"),
            "feature_mismatch_count": feature_mismatch_count(snapshot, signal),
            "date": day,
        }
        if kind == "shadow_entry":
            entries.append(row)
        elif kind == "shadow_lifecycle_close":
            closes.append(row)

    frames = iter_decision_frames_for_args(repo_root, args, day)
    first_frame = next_or_none(frames)
    warmup_seed_count = 0
    if first_frame is not None and args.warmup_reference_r5:
        warmup_seed_count = seed_policy_r5_from_reference(
            repo_root,
            policy,
            first_ts_us=int(first_frame["local_ts_us"]),
            fixed_exit_us=args.fixed_exit_us,
        )

    for frame in prepend_optional(first_frame, frames):
        if seq >= args.max_events:
            break
        signal = policy.on_decision_frame(frame, seq)
        record_signal(signal, frame, seq)
        seq += 1
        if args.progress_interval > 0 and seq % args.progress_interval == 0:
            print(
                f"direct panel audit day={day} source={args.decision_frame_source} frames={seq}",
                file=sys.stderr,
                flush=True,
            )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    summary = {
        "run_id": f"{args.run_prefix}_{day.replace('-', '')}_{timestamp}_direct_panel",
        "run_dir": "",
        "source_label": f"direct_{args.decision_frame_source}_panel_shadow_v1:{args.symbol}:{day}",
        "decision_clock": "panel",
        "decision_frame_source": args.decision_frame_source,
        "events_seen": seq,
        "quote_events_seen": 0,
        "trade_events_seen": 0,
        "l2_decision_frames_seen": seq,
        "event_count": len(entries) + len(closes),
        "intents_created": 0,
        "orders_submitted": 0,
        "fills_created": 0,
        "direct_mode": True,
        "diagnostic_reference_r5_warmup_seed_count": warmup_seed_count,
        "elapsed_wall_ms": elapsed_ms,
    }
    return summary, entries, closes, dict(counts)


def direct_panel_shadow_range(
    repo_root: Path,
    args: argparse.Namespace,
    warmup_dates: list[str],
    score_dates: set[str],
    timestamp: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    _OnlineFeatureState, ShadowFourCellPolicy = strategy_modules(repo_root)
    policy = ShadowFourCellPolicy(
        frames_threshold=args.frames_threshold,
        overlay_threshold=args.overlay_threshold,
        fixed_exit_us=args.fixed_exit_us,
        gamma_preset=args.gamma_preset,
    )
    load_shadow_state_if_requested(repo_root, args, policy)
    runner_summaries: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    closes: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    def record_signal(
        signal: dict[str, Any] | None,
        frame: dict[str, Any],
        event_seq: int,
        day: str,
        score: bool,
    ) -> None:
        if signal is None:
            return
        kind = signal.get("event_kind")
        if not score:
            return
        counts[str(kind)] += 1
        checkpoint_type = (
            "shadow_four_cell_panel_trigger"
            if kind == "shadow_entry"
            else "shadow_panel_lifecycle_close"
        )
        snapshot = {
            "schema_id": "ccusdt_online_feature_snapshot_v1",
            "runtime_safe": True,
            "checkpoint": checkpoint_type,
            "observed_seq": event_seq,
            "local_ts_us": frame.get("local_ts_us"),
            "decision_frame": frame,
            "four_cell_inputs": {},
        }
        if kind == "shadow_entry":
            snapshot["four_cell_inputs"].update(
                {
                    "a_r5_gt_1": signal["a_r5_gt_1"],
                    "r5": signal["a_r5_raw"],
                    "r5_ready": signal["a_r5_ready"],
                    "b_threshold": signal["b_threshold"],
                    "b_frames_ge_threshold": signal["b_frames_ge_q90"],
                    "cell": signal["cell"],
                }
            )
        snapshot["shadow_signal"] = signal
        row = {
            "event_id": event_seq,
            "run_id": f"{args.run_prefix}_{day.replace('-', '')}_{timestamp}_direct_panel_warmup",
            "run_dir": "",
            "reason": checkpoint_type,
            **flatten_signal(signal),
            "entry_event_index": signal.get("entry_event_index"),
            "feature_mismatch_count": feature_mismatch_count(snapshot, signal),
            "date": day,
        }
        if kind == "shadow_entry":
            entries.append(row)
        elif kind == "shadow_lifecycle_close":
            closes.append(row)

    for day in warmup_dates:
        score = day in score_dates
        policy.start_new_day()
        seq = 0
        day_entries_before = len(entries)
        day_closes_before = len(closes)
        start = time.perf_counter()
        for frame in iter_decision_frames_for_args(repo_root, args, day):
            if seq >= args.max_events:
                break
            signal = policy.on_decision_frame(frame, seq)
            record_signal(signal, frame, seq, day, score)
            seq += 1
            if args.progress_interval > 0 and seq % args.progress_interval == 0:
                print(
                    f"direct panel audit day={day} score={score} frames={seq}",
                    file=sys.stderr,
                    flush=True,
                )
        day_entries = len(entries) - day_entries_before
        day_closes = len(closes) - day_closes_before
        runner_summaries.append(
            {
                "run_id": (
                    f"{args.run_prefix}_{day.replace('-', '')}_{timestamp}"
                    "_direct_panel_warmup"
                ),
                "run_dir": "",
                "source_label": (
                    f"direct_{args.decision_frame_source}_panel_shadow_warmup_v1:"
                    f"{args.symbol}:{day}"
                ),
                "decision_clock": "panel",
                "decision_frame_source": args.decision_frame_source,
                "events_seen": seq,
                "quote_events_seen": 0,
                "trade_events_seen": 0,
                "l2_decision_frames_seen": seq,
                "event_count": day_entries + day_closes,
                "intents_created": 0,
                "orders_submitted": 0,
                "fills_created": 0,
                "direct_mode": True,
                "score_day": score,
                "bot_owned_warmup": True,
                "diagnostic_reference_r5_warmup_seed_count": 0,
                "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
            }
        )
    return runner_summaries, entries, closes, dict(counts)


def prepend_optional(first: Any | None, rest: Any) -> Any:
    if first is not None:
        yield first
    yield from rest


def iter_decision_frames_for_args(repo_root: Path, args: argparse.Namespace, day: str) -> Any:
    if args.decision_frame_source == "cache":
        from decision_frame_cache import iter_cached_decision_frames

        return iter_cached_decision_frames(repo_root, args.symbol, day)
    from decision_frame_parity import iter_decision_frames

    return iter_decision_frames(repo_root, args.symbol, day)


def load_shadow_state_if_requested(repo_root: Path, args: argparse.Namespace, policy: Any) -> None:
    if not args.shadow_state_in:
        return
    state = read_shadow_state(repo_root, args.shadow_state_in)
    policy.load_state(state)
    policy.start_new_day()


def read_shadow_state(repo_root: Path, path_arg: Path) -> dict[str, Any]:
    path = path_arg
    if not path.is_absolute():
        path = repo_root / path
    with path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    if not isinstance(state, dict):
        raise ValueError(f"shadow state must be a JSON object: {path}")
    return state


def guard_shadow_state_boundary(
    repo_root: Path,
    args: argparse.Namespace,
    score_dates: list[str],
) -> dict[str, Any] | None:
    if not args.shadow_state_in:
        return None
    state = read_shadow_state(repo_root, args.shadow_state_in)
    expected_start = args.warmup_from_date or args.from_date
    actual_next = state.get("next_expected_date")
    if actual_next != expected_start:
        raise ValueError(
            json.dumps(
                {
                    "error": "shadow_state_boundary_violation",
                    "reason": "Bot-owned R5 state is sequential and must resume exactly at next_expected_date.",
                    "state_path": str(args.shadow_state_in),
                    "state_after_date": state.get("state_after_date") or state.get("last_seen_date"),
                    "state_next_expected_date": actual_next,
                    "requested_start_date": expected_start,
                    "score_from_date": args.from_date,
                    "score_to_date": args.to_date,
                },
                indent=2,
            )
        )
    continuous_direct_range = (
        args.mode == "direct"
        and args.decision_clock == "panel"
        and bool(args.warmup_from_date)
    )
    if len(score_dates) > 1 and not continuous_direct_range:
        raise ValueError(
            json.dumps(
                {
                    "error": "shadow_state_non_continuous_reuse_rejected",
                    "reason": (
                        "A persisted shadow state cannot be loaded independently for multiple "
                        "dates; use --warmup-from-date to replay a continuous range."
                    ),
                    "state_path": str(args.shadow_state_in),
                    "requested_dates": score_dates,
                    "mode": args.mode,
                    "decision_clock": args.decision_clock,
                    "warmup_from_date": args.warmup_from_date,
                },
                indent=2,
            )
        )
    return {
        "state_path": str(args.shadow_state_in),
        "state_after_date": state.get("state_after_date") or state.get("last_seen_date"),
        "next_expected_date": actual_next,
        "data_manifest_hash": state.get("data_manifest_hash"),
        "policy_params_hash": state.get("policy_params_hash"),
        "closed_bps": state.get("closed_bps"),
        "pending_entries": len(state.get("pending_entries") or []),
    }


def seed_policy_r5_from_reference(
    repo_root: Path,
    policy: Any,
    *,
    first_ts_us: int,
    fixed_exit_us: int,
) -> int:
    seed = seed_closed_bps_before_ts(repo_root, first_ts_us, fixed_exit_us)
    for pnl in seed:
        policy.closed.add(pnl)
    return len(seed)


def seed_closed_bps_for_day(repo_root: Path, day: str, fixed_exit_us: int) -> list[float]:
    first_entry_ts = first_reference_entry_ts(repo_root, day)
    if first_entry_ts is None:
        return []
    return seed_closed_bps_before_ts(repo_root, first_entry_ts, fixed_exit_us)


def seed_closed_bps_before_ts(repo_root: Path, first_ts_us: int, fixed_exit_us: int) -> list[float]:
    path = repo_root / "date" / OOS_0518_REFERENCE
    if not path.exists():
        return []
    rows: list[tuple[int, float]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                entry_ts = int(float(row.get("entry_local_timestamp") or 0.0))
                pnl = float(row.get("fixed_gross_bps") or row.get("net") or 0.0)
            except (TypeError, ValueError):
                continue
            if entry_ts + fixed_exit_us < first_ts_us:
                rows.append((entry_ts, pnl))
    rows.sort(key=lambda item: item[0])
    return [pnl for _entry_ts, pnl in rows[-5:]]


def first_reference_entry_ts(repo_root: Path, day: str) -> int | None:
    path = repo_root / "date" / OOS_0518_REFERENCE
    if not path.exists():
        return None
    first: int | None = None
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if str(row.get("date") or "") != day:
                continue
            try:
                entry_ts = int(float(row.get("entry_local_timestamp") or 0.0))
            except (TypeError, ValueError):
                continue
            first = entry_ts if first is None else min(first, entry_ts)
    return first


def load_run_shadow_events(run_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    path = run_dir / "events.ndjson"
    entries: list[dict[str, Any]] = []
    closes: list[dict[str, Any]] = []
    checkpoint_counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event_type") != "strategy_feature_checkpoint":
                continue
            payload = event.get("payload") or {}
            signal = payload.get("shadow_signal")
            if not isinstance(signal, dict):
                signal = ((payload.get("feature_snapshot") or {}).get("shadow_signal") or {})
            if not isinstance(signal, dict) or not signal:
                continue
            kind = signal.get("event_kind")
            checkpoint_counts[str(kind)] += 1
            row = {
                "line_no": line_no,
                "event_id": event.get("event_id"),
                "run_id": event.get("run_id"),
                "run_dir": str(run_dir),
                "reason": payload.get("reason"),
                **flatten_signal(signal),
                "feature_mismatch_count": feature_mismatch_count(payload.get("feature_snapshot") or {}, signal),
            }
            if kind == "shadow_entry":
                entries.append(row)
            elif kind == "shadow_lifecycle_close":
                closes.append(row)
    return entries, closes, dict(checkpoint_counts)


def flatten_signal(signal: dict[str, Any]) -> dict[str, Any]:
    closed = signal.get("closed_outcomes") or {}
    closed_now = signal.get("closed_now") or []
    closed_position_ids = [
        str(item.get("shadow_position_id"))
        for item in closed_now
        if item.get("shadow_position_id") is not None
    ]
    closed_pnl_bps = sum_float(item.get("pnl_bps") for item in closed_now)
    closed_max_exit_lag_us = None
    exit_lags = [
        int(item["exit_lag_us"])
        for item in closed_now
        if item.get("exit_lag_us") not in (None, "")
    ]
    if exit_lags:
        closed_max_exit_lag_us = max(exit_lags)
    return {
        "date": "",
        "event_kind": signal.get("event_kind"),
        "observed_seq": signal.get("observed_seq"),
        "local_ts_us": signal.get("local_ts_us"),
        "shadow_position_id": signal.get("shadow_position_id"),
        "entry_ts_us": signal.get("entry_ts_us"),
        "entry_due_ts_us": signal.get("entry_due_ts_us"),
        "fixed_exit_us": signal.get("fixed_exit_us"),
        "membership_set": signal.get("membership_set"),
        "trigger_classes": "+".join(signal.get("trigger_classes") or []),
        "direction": signal.get("direction"),
        "direction_label": signal.get("direction_label"),
        "cell": signal.get("cell"),
        "feature_value": signal.get("feature_value"),
        "trade_window_count": signal.get("trade_window_count"),
        "trade_buy_qty": signal.get("trade_buy_qty"),
        "trade_sell_qty": signal.get("trade_sell_qty"),
        "abs_qty": signal.get("abs_qty"),
        "past_event_25_bps": signal.get("past_event_25_bps"),
        "frames_since_mid_change": signal.get("frames_since_mid_change"),
        "entry_spread_bps": signal.get("entry_spread_bps"),
        "a_r5_gt_1": signal.get("a_r5_gt_1"),
        "a_r5_raw": signal.get("a_r5_raw"),
        "a_r5_ready": signal.get("a_r5_ready"),
        "b_frames_ge_q90": signal.get("b_frames_ge_q90"),
        "base_weight": signal.get("base_weight"),
        "overlay_boost": signal.get("overlay_boost"),
        "weak_overlay_weight": signal.get("weak_overlay_weight"),
        "gamma_preset": signal.get("gamma_preset"),
        "gamma": signal.get("gamma"),
        "target_exposure": signal.get("target_exposure"),
        "shadow_trigger_index": signal.get("shadow_trigger_index"),
        "pending_shadow_entries": signal.get("pending_shadow_entries"),
        "closed_count": closed.get("count"),
        "closed_positive_bps": closed.get("positive_bps"),
        "closed_negative_bps": closed.get("negative_bps"),
        "closed_r5": closed.get("r5"),
        "closed_r5_ready": closed.get("r5_ready"),
        "closed_now_count": len(closed_now),
        "closed_position_ids": "+".join(closed_position_ids),
        "closed_pnl_bps": closed_pnl_bps,
        "closed_max_exit_lag_us": closed_max_exit_lag_us,
    }


def close(a: Any, b: Any, tolerance: float = 1e-9) -> bool:
    if a is None and b is None:
        return True
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return a == b


def feature_mismatch_count(snapshot: dict[str, Any], signal: dict[str, Any]) -> int:
    decision_frame = snapshot.get("decision_frame") or {}
    if decision_frame:
        pairs = [
            (decision_frame.get("local_ts_us"), signal.get("local_ts_us")),
            (snapshot.get("observed_seq"), signal.get("observed_seq")),
            (decision_frame.get("trade_flow_imbalance"), signal.get("feature_value")),
            (decision_frame.get("trade_window_count"), signal.get("trade_window_count")),
            (decision_frame.get("frames_since_mid_change"), signal.get("frames_since_mid_change")),
            (decision_frame.get("past_event_25_bps"), signal.get("past_event_25_bps")),
        ]
        if signal.get("event_kind") == "shadow_entry":
            inputs = snapshot.get("four_cell_inputs") or {}
            pairs.extend(
                [
                    (inputs.get("cell"), signal.get("cell")),
                    (inputs.get("b_threshold"), signal.get("b_threshold")),
                    (inputs.get("b_frames_ge_threshold"), signal.get("b_frames_ge_q90")),
                ]
            )
        return sum(0 if close(a, b) else 1 for a, b in pairs)
    quote = snapshot.get("quote") or {}
    flow = snapshot.get("trade_flow") or {}
    inputs = snapshot.get("four_cell_inputs") or {}
    pairs = [
        (snapshot.get("local_ts_us"), signal.get("local_ts_us")),
        (snapshot.get("observed_seq"), signal.get("observed_seq")),
        (flow.get("tfi"), signal.get("feature_value")),
        (flow.get("rolling_trades"), signal.get("trade_window_count")),
        (quote.get("frames_since_mid_change"), signal.get("frames_since_mid_change")),
        (quote.get("past_event_25_bps"), signal.get("past_event_25_bps")),
    ]
    if signal.get("event_kind") == "shadow_entry":
        pairs.extend(
            [
                (inputs.get("cell"), signal.get("cell")),
                (inputs.get("b_threshold"), signal.get("b_threshold")),
                (inputs.get("b_frames_ge_threshold"), signal.get("b_frames_ge_q90")),
            ]
        )
    return sum(0 if close(a, b) else 1 for a, b in pairs)


def bool_value(raw: Any) -> bool:
    return str(raw).strip().lower() in {"true", "1", "yes"}


def cell_from_reference(row: dict[str, Any]) -> str:
    a = bool_value(row.get("gate_r_n5"))
    b = bool_value(row.get("gate_frames_q90"))
    if a and b:
        return "11_r5_frames"
    if a:
        return "10_r5_only"
    if b:
        return "01_frames_only"
    return "00_none"


def load_reference_rows(repo_root: Path, dates: list[str]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for day in dates:
        by_date[day] = []
    source_for_date = {day: OOS_0518_REFERENCE for day in dates}
    for name in sorted(set(source_for_date.values())):
        path = repo_root / "date" / name
        if not path.exists():
            continue
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                day = str(row.get("date") or "")
                if day not in by_date or source_for_date[day] != name:
                    continue
                out = dict(row)
                out["cell"] = cell_from_reference(row)
                out["direction_label"] = "long" if float(row.get("direction") or 0.0) > 0.0 else "short"
                out["local_ts_us"] = int(float(row.get("entry_local_timestamp") or 0.0))
                out["reference_file"] = name
                by_date[day].append(out)
    return [row for day in dates for row in by_date[day]]


def summarize(rows: list[dict[str, Any]], *, ts_key: str = "local_ts_us") -> dict[str, Any]:
    if not rows:
        return {
            "entries": 0,
            "membership_counts": {},
            "cell_counts": {},
            "side_counts": {},
            "target_exposure": 0.0,
            "base_exposure": 0.0,
            "feature_mismatches": 0,
        }
    return {
        "entries": len(rows),
        "membership_counts": dict(Counter(str(row.get("membership_set")) for row in rows)),
        "cell_counts": dict(Counter(str(row.get("cell")) for row in rows)),
        "side_counts": dict(Counter(str(row.get("direction_label")) for row in rows)),
        "target_exposure": sum_float(row.get("target_exposure") for row in rows),
        "base_exposure": sum_float(row.get("base_weight") for row in rows),
        "weak_overlay_exposure": sum_float(row.get("weak_overlay_weight") for row in rows),
        "feature_mismatches": int(sum(int(row.get("feature_mismatch_count") or 0) for row in rows)),
        "first_ts_us": min(int(float(row[ts_key])) for row in rows if row.get(ts_key) not in (None, "")),
        "last_ts_us": max(int(float(row[ts_key])) for row in rows if row.get(ts_key) not in (None, "")),
    }


def sum_float(values: Any) -> float:
    total = 0.0
    for value in values:
        try:
            total += float(value)
        except (TypeError, ValueError):
            pass
    return total


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


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    dates = date_range(args.from_date, args.to_date)
    shadow_state_guard = guard_shadow_state_boundary(repo_root, args, dates)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / f"{args.run_prefix}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    runner_summaries: list[dict[str, Any]] = []
    online_entries: list[dict[str, Any]] = []
    online_closes: list[dict[str, Any]] = []
    checkpoint_counts: Counter[str] = Counter()
    if args.mode == "direct":
        if args.decision_clock == "panel" and args.warmup_from_date:
            warmup_dates = date_range(args.warmup_from_date, args.to_date)
            summaries, entries, closes, counts = direct_panel_shadow_range(
                repo_root,
                args,
                warmup_dates,
                set(dates),
                timestamp,
            )
            runner_summaries.extend(summaries)
            online_entries.extend(entries)
            online_closes.extend(closes)
            checkpoint_counts.update(counts)
        else:
            for day in dates:
                summary, entries, closes, counts = direct_shadow_day(repo_root, args, day, timestamp)
                runner_summaries.append(summary)
                online_entries.extend(entries)
                online_closes.extend(closes)
                checkpoint_counts.update(counts)
    elif args.skip_run:
        runner_summaries = [{"run_dir": str(path)} for path in args.run_dir]
    else:
        for day in dates:
            runner_summaries.append(run_shadow_day(repo_root, args, day, timestamp))

    if args.mode == "runner":
        for summary in runner_summaries:
            run_dir = repo_root / str(summary["run_dir"])
            entries, closes, counts = load_run_shadow_events(run_dir)
            for row in entries:
                row["date"] = infer_date_from_run(summary, row)
            for row in closes:
                row["date"] = infer_date_from_run(summary, row)
            online_entries.extend(entries)
            online_closes.extend(closes)
            checkpoint_counts.update(counts)

    reference_rows = load_reference_rows(repo_root, dates)
    reference_by_date = {day: [row for row in reference_rows if row.get("date") == day] for day in dates}
    online_by_date = {day: [row for row in online_entries if row.get("date") == day] for day in dates}
    per_day = {}
    for day in dates:
        online_ts = {int(float(row["local_ts_us"])) for row in online_by_date[day] if row.get("local_ts_us")}
        ref_ts = {int(float(row["local_ts_us"])) for row in reference_by_date[day] if row.get("local_ts_us")}
        online_summary = summarize(online_by_date[day])
        reference_summary = summarize_reference(reference_by_date[day])
        day_ok = (
            online_summary["entries"] == reference_summary["entries"]
            and len(online_ts & ref_ts) == reference_summary["entries"]
            and online_summary["membership_counts"] == reference_summary["membership_counts"]
            and online_summary["cell_counts"] == reference_summary["cell_counts"]
            and online_summary["side_counts"] == reference_summary["side_counts"]
            and online_summary["feature_mismatches"] == 0
        )
        per_day[day] = {
            "ok": day_ok,
            "online": online_summary,
            "reference": reference_summary,
            "exact_timestamp_matches": len(online_ts & ref_ts),
            "online_minus_reference_entries": len(online_by_date[day]) - len(reference_by_date[day]),
        }

    all_ok = all(day["ok"] for day in per_day.values())
    report = {
        "ok": all_ok,
        "run_tag": f"{args.run_prefix}_{timestamp}",
        "guardrail": "runtime_bot_reads_only_canonical_market_stream_research_csv_is_offline_reference",
        "dates": dates,
        "runtime_policy": {
            "mode": args.mode,
            "window_us": args.window_us,
            "frames_threshold": args.frames_threshold,
            "overlay_threshold": args.overlay_threshold,
            "fixed_exit_us": args.fixed_exit_us,
            "gamma_preset": args.gamma_preset,
            "decision_frame_source": args.decision_frame_source,
            "warmup_from_date": args.warmup_from_date,
            "warmup_reference_r5": args.warmup_reference_r5,
            "shadow_state_boundary_guard": shadow_state_guard,
            "r5_rule": "strict online shadow fixed-exit lifecycle; R5 uses closed shadow entries only, positive_bps/abs(negative_bps)",
        },
        "runner_summaries": runner_summaries,
        "checkpoint_counts": dict(checkpoint_counts),
        "online_total": summarize(online_entries),
        "reference_total": summarize_reference(reference_rows),
        "shadow_lifecycle_closes": len(online_closes),
        "per_day": per_day,
        "outputs": {
            "summary_json": str(out_dir / "summary.json"),
            "online_triggers_csv": str(out_dir / "online_triggers.csv"),
            "online_closes_csv": str(out_dir / "online_lifecycle_closes.csv"),
            "reference_csv": str(out_dir / "research_reference.csv"),
        },
    }
    write_csv(out_dir / "online_triggers.csv", online_entries)
    write_csv(out_dir / "online_lifecycle_closes.csv", online_closes)
    write_csv(out_dir / "research_reference.csv", reference_rows)
    (out_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def infer_date_from_run(summary: dict[str, Any], row: dict[str, Any]) -> str:
    source = str(summary.get("source_label") or "")
    for part in source.split(":"):
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            return part
    run_id = str(summary.get("run_id") or row.get("run_id") or "")
    for token in run_id.replace("_", " ").split():
        if len(token) == 8 and token.isdigit():
            return f"{token[:4]}-{token[4:6]}-{token[6:]}"
    return ""


def summarize_reference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "entries": 0,
            "membership_counts": {},
            "cell_counts": {},
            "side_counts": {},
            "base_exposure": 0.0,
            "weak_overlay_exposure": 0.0,
        }
    return {
        "entries": len(rows),
        "membership_counts": dict(Counter(str(row.get("membership_set")) for row in rows)),
        "cell_counts": dict(Counter(str(row.get("cell")) for row in rows)),
        "side_counts": dict(Counter(str(row.get("direction_label")) for row in rows)),
        "base_exposure": sum_float(row.get("base_weight") for row in rows),
        "weak_overlay_exposure": sum_float(row.get("weight") for row in rows),
        "first_ts_us": min(int(float(row["local_ts_us"])) for row in rows if row.get("local_ts_us")),
        "last_ts_us": max(int(float(row["local_ts_us"])) for row in rows if row.get("local_ts_us")),
    }


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Offline parity check for runtime-safe decision_frame_v1.

This diagnostic rebuilds the old fixed L2 event-panel decision clock from
canonical market truth. It is allowed to read legacy fixed panel CSVs only as a
reference; the runtime builder itself lives in the Strategy Bot directory and
does not read research artifacts.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator


BOT_DIR = Path(__file__).resolve().parents[1] / "strategies" / "python" / "ccusdt_tfi_core_idle01"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from decision_frame import DecisionFrameBuilder  # noqa: E402


OOS_PANEL_RUN_TAGS = {
    "2026-05-16": "20260518_ccusdt_fixed_factors_oos_day20260516_v1",
    "2026-05-17": "20260518_ccusdt_fixed_factors_oos_day20260517_v1",
    "2026-05-18": "20260519_ccusdt_fixed_factors_oos_day20260518_v1",
}
US_PER_SECOND = 1_000_000
COMPARE_FIELDS = [
    "local_timestamp",
    "event_index",
    "is_snapshot_batch",
    "factor_eligible",
    "batch_rows",
    "crossed_levels_removed",
    "best_bid_price",
    "best_bid_amount",
    "best_ask_price",
    "best_ask_amount",
    "mid_price",
    "spread_bps",
    "bid_levels",
    "ask_levels",
    "trade_window_count",
    "trade_buy_amount",
    "trade_sell_amount",
    "trade_notional_quote",
    "trade_flow_imbalance",
    "mid_change_prev",
    "quote_change_prev",
    "top_size_change_prev",
    "frames_since_mid_change",
    "past_event_25_bps",
    "fwd_time_60s_bucket",
]
FLOAT_FIELDS = {
    "best_bid_price",
    "best_bid_amount",
    "best_ask_price",
    "best_ask_amount",
    "mid_price",
    "spread_bps",
    "trade_buy_amount",
    "trade_sell_amount",
    "trade_notional_quote",
    "trade_flow_imbalance",
    "frames_since_mid_change",
    "past_event_25_bps",
}
BOOL_FIELDS = {
    "is_snapshot_batch",
    "factor_eligible",
    "mid_change_prev",
    "quote_change_prev",
    "top_size_change_prev",
}
INT_FIELDS = {
    "local_timestamp",
    "event_index",
    "batch_rows",
    "crossed_levels_removed",
    "bid_levels",
    "ask_levels",
    "trade_window_count",
    "fwd_time_60s_bucket",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--run-prefix", default="decision_frame_parity")
    parser.add_argument("--max-mismatches", type=int, default=500)
    parser.add_argument("--float-tol", type=float, default=1e-8)
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


def fixed_panel_paths(repo_root: Path, symbol: str, day: str) -> list[Path]:
    run_tag = OOS_PANEL_RUN_TAGS[day]
    root = (
        repo_root
        / "data"
        / "ccusdt"
        / "v1"
        / "derived"
        / "ccusdt_v1_fixed_event_factor_panel"
        / f"run_tag={run_tag}"
        / f"symbol={symbol}"
        / f"dt={day}"
    )
    paths = sorted(root.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(root)
    return paths


def read_canonical_trades(repo_root: Path, symbol: str, day: str) -> list[dict[str, Any]]:
    path = canonical_path(repo_root, symbol, "trade_event_v1", day)
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["local_ts_us"]))
    return rows


def iter_l2_batches(repo_root: Path, symbol: str, day: str) -> Iterator[list[dict[str, Any]]]:
    path = canonical_path(repo_root, symbol, "l2_level_update_v1", day)
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        batch: list[dict[str, Any]] = []
        current_ts: int | None = None
        for row in reader:
            ts = int(row["local_ts_us"])
            if current_ts is not None and ts != current_ts and batch:
                yield batch
                batch = []
            current_ts = ts
            batch.append(
                {
                    "seq": int(row["seq"]),
                    "exchange_ts_us": int(row["exchange_ts_us"]),
                    "local_ts_us": ts,
                    "is_snapshot": parse_bool(row["is_snapshot"]),
                    "side": row["side"],
                    "price": float(row["price"]),
                    "qty": float(row["qty"]),
                }
            )
        if batch:
            yield batch


def iter_decision_frames(repo_root: Path, symbol: str, day: str) -> Iterator[dict[str, Any]]:
    trades = read_canonical_trades(repo_root, symbol, day)
    trade_pos = 0
    builder = DecisionFrameBuilder()
    for batch in iter_l2_batches(repo_root, symbol, day):
        ts = int(batch[0]["local_ts_us"])
        while trade_pos < len(trades) and int(trades[trade_pos]["local_ts_us"]) <= ts:
            builder.observe_trade(trades[trade_pos])
            trade_pos += 1
        frame = builder.build_from_l2_updates(batch)
        if frame is not None:
            yield frame


class OldPanelLabeler:
    def __init__(self) -> None:
        self.day_start_ts_us: int | None = None
        self.previous_mid: float | None = None
        self.previous_bid: float | None = None
        self.previous_ask: float | None = None
        self.previous_bid_qty: float | None = None
        self.previous_ask_qty: float | None = None
        self.last_mid_change_pos: int | None = None
        self.mid_history: list[float] = []
        self.row_pos = -1

    def add(self, row: dict[str, str]) -> dict[str, Any]:
        self.row_pos += 1
        local_ts_us = int_float(row.get("local_timestamp"))
        if self.day_start_ts_us is None:
            self.day_start_ts_us = local_ts_us
        bid = optional_float(row.get("best_bid_price"))
        ask = optional_float(row.get("best_ask_price"))
        bid_qty = optional_float(row.get("best_bid_amount"))
        ask_qty = optional_float(row.get("best_ask_amount"))
        mid = optional_float(row.get("mid_price"))
        mid_change_prev = (
            False
            if self.previous_mid is None or mid is None
            else abs(mid - self.previous_mid) > 1e-12
        )
        quote_change_prev = (
            False
            if self.previous_bid is None
            or self.previous_ask is None
            or bid is None
            or ask is None
            else abs(bid - self.previous_bid) > 1e-12 or abs(ask - self.previous_ask) > 1e-12
        )
        top_size_change_prev = (
            False
            if self.previous_bid_qty is None
            or self.previous_ask_qty is None
            or bid_qty is None
            or ask_qty is None
            else abs(bid_qty - self.previous_bid_qty) > 1e-12
            or abs(ask_qty - self.previous_ask_qty) > 1e-12
        )
        if mid_change_prev:
            self.last_mid_change_pos = self.row_pos
        frames_since_mid_change = (
            math.inf
            if self.last_mid_change_pos is None
            else float(self.row_pos - self.last_mid_change_pos)
        )
        past_event_25_bps = None
        if mid is not None and mid > 0.0 and len(self.mid_history) >= 25:
            past_mid = self.mid_history[-25]
            if past_mid > 0.0:
                past_event_25_bps = math.log(mid / past_mid) * 10_000.0
        if mid is not None and mid > 0.0:
            self.mid_history.append(mid)
        bucket = (local_ts_us - self.day_start_ts_us) // (60 * US_PER_SECOND)

        out: dict[str, Any] = {}
        for field in COMPARE_FIELDS:
            if field in FLOAT_FIELDS:
                out[field] = optional_float(row.get(field))
            elif field in BOOL_FIELDS:
                out[field] = parse_bool(row.get(field))
            elif field in INT_FIELDS:
                out[field] = int_float(row.get(field))
        out.update(
            {
                "mid_change_prev": mid_change_prev,
                "quote_change_prev": quote_change_prev,
                "top_size_change_prev": top_size_change_prev,
                "frames_since_mid_change": frames_since_mid_change,
                "past_event_25_bps": past_event_25_bps,
                "fwd_time_60s_bucket": int(bucket),
            }
        )
        self.previous_mid = mid
        self.previous_bid = bid
        self.previous_ask = ask
        self.previous_bid_qty = bid_qty
        self.previous_ask_qty = ask_qty
        return out


def iter_old_panel_frames(repo_root: Path, symbol: str, day: str) -> Iterator[dict[str, Any]]:
    labeler = OldPanelLabeler()
    for path in fixed_panel_paths(repo_root, symbol, day):
        with path.open("r", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                yield labeler.add(row)


def compare_day(
    repo_root: Path,
    symbol: str,
    day: str,
    *,
    float_tol: float,
    max_mismatches: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    old_iter = iter_old_panel_frames(repo_root, symbol, day)
    new_iter = iter_decision_frames(repo_root, symbol, day)
    mismatches: list[dict[str, Any]] = []
    field_counts: dict[str, int] = defaultdict(int)
    field_max_abs_diff: dict[str, float] = defaultdict(float)
    rows = 0
    row_mismatch_count = 0
    old_exhausted = False
    new_exhausted = False

    while True:
        try:
            old = next(old_iter)
        except StopIteration:
            old = None
            old_exhausted = True
        try:
            new = next(new_iter)
        except StopIteration:
            new = None
            new_exhausted = True
        if old is None and new is None:
            break
        rows += 1
        if old is None or new is None:
            row_mismatch_count += 1
            if len(mismatches) < max_mismatches:
                mismatches.append(
                    {
                        "date": day,
                        "row": rows,
                        "kind": "row_count_mismatch",
                        "old_present": old is not None,
                        "new_present": new is not None,
                    }
                )
            continue
        bad_fields: list[str] = []
        for field in COMPARE_FIELDS:
            ok, diff = compare_value(old.get(field), new.get(field), field, float_tol)
            if diff is not None:
                field_max_abs_diff[field] = max(field_max_abs_diff[field], abs(diff))
            if not ok:
                field_counts[field] += 1
                bad_fields.append(field)
        if bad_fields:
            row_mismatch_count += 1
            if len(mismatches) < max_mismatches:
                item = {
                    "date": day,
                    "row": rows,
                    "kind": "field_mismatch",
                    "fields": "+".join(bad_fields),
                    "old_local_timestamp": old.get("local_timestamp"),
                    "new_local_timestamp": new.get("local_timestamp"),
                    "old_event_index": old.get("event_index"),
                    "new_event_index": new.get("event_index"),
                }
                for field in bad_fields[:8]:
                    item[f"old_{field}"] = old.get(field)
                    item[f"new_{field}"] = new.get(field)
                mismatches.append(item)

    summary = {
        "date": day,
        "rows_compared": rows,
        "old_exhausted": old_exhausted,
        "new_exhausted": new_exhausted,
        "row_mismatch_count": row_mismatch_count,
        "field_mismatch_counts": dict(sorted(field_counts.items())),
        "field_max_abs_diff": dict(sorted(field_max_abs_diff.items())),
        "ok": row_mismatch_count == 0,
    }
    return summary, mismatches


def compare_value(old: Any, new: Any, field: str, tol: float) -> tuple[bool, float | None]:
    if field in BOOL_FIELDS:
        return bool(old) == bool(new), None
    if field in INT_FIELDS:
        return int(old) == int(new), float(int(new) - int(old))
    left = optional_float(old)
    right = optional_float(new)
    if left is None and right is None:
        return True, None
    if left is None or right is None:
        return False, None
    if math.isinf(left) or math.isinf(right):
        return left == right, None
    diff = right - left
    return abs(diff) <= tol, diff


def optional_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        out = float(raw)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) or math.isinf(out) else None


def int_float(raw: Any) -> int:
    value = optional_float(raw)
    if value is None:
        return 0
    return int(round(value))


def parse_bool(raw: Any) -> bool:
    return str(raw).strip().lower() in {"true", "1", "yes"}


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
    target_dates = date_range(args.from_date, args.to_date)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / f"{args.run_prefix}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    per_day: dict[str, Any] = {}
    all_mismatches: list[dict[str, Any]] = []
    for day in target_dates:
        print(f"decision_frame parity day={day}", flush=True)
        day_summary, mismatches = compare_day(
            repo_root,
            args.symbol,
            day,
            float_tol=args.float_tol,
            max_mismatches=args.max_mismatches,
        )
        per_day[day] = day_summary
        all_mismatches.extend(mismatches)

    ok = all(day["ok"] for day in per_day.values())
    summary = {
        "ok": ok,
        "run_tag": f"{args.run_prefix}_{timestamp}",
        "guardrail": "diagnostic_only_legacy_fixed_panel_reference_not_runtime_input",
        "runtime_builder": str(BOT_DIR / "decision_frame.py"),
        "target_dates": target_dates,
        "symbol": args.symbol,
        "compare_fields": COMPARE_FIELDS,
        "float_tol": args.float_tol,
        "per_day": per_day,
        "totals": {
            "rows_compared": int(sum(day["rows_compared"] for day in per_day.values())),
            "row_mismatch_count": int(sum(day["row_mismatch_count"] for day in per_day.values())),
            "mismatches_written": len(all_mismatches),
        },
        "outputs": {
            "summary_json": str(out_dir / "summary.json"),
            "mismatches_csv": str(out_dir / "decision_frame_mismatches.csv"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(out_dir / "decision_frame_mismatches.csv", all_mismatches)
    print(json.dumps(summary, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

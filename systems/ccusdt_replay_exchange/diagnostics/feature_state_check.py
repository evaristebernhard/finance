#!/usr/bin/env python
"""Check Python online feature state against an independent reference.

The diagnostic replays canonical exchange-visible events in the same merge order
as the runner. It does not read legacy research labels, scored entries, or root
scripts.
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass
class RefTrade:
    local_ts_us: int
    signed_qty: float
    abs_qty: float
    signed_notional: float
    abs_notional: float
    is_buy: bool


class ReferenceFeatureState:
    def __init__(self, window_us: int) -> None:
        self.window_us = window_us
        self.trades: collections.deque[RefTrade] = collections.deque()
        self.signed_qty = 0.0
        self.abs_qty = 0.0
        self.buy_qty = 0.0
        self.sell_qty = 0.0
        self.signed_notional = 0.0
        self.abs_notional = 0.0
        self.buy_count = 0
        self.sell_count = 0
        self.last_mid: float | None = None
        self.last_bid: float | None = None
        self.last_ask: float | None = None
        self.mid_change_bps = 0.0
        self.spread_bps = 0.0
        self.mid_change = 0.0
        self.frames_since_mid_change = 0
        self.l2_batches_seen = 0
        self.last_l2_bid_levels = 0
        self.last_l2_ask_levels = 0
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}

    def trim(self, local_ts_us: int) -> None:
        min_ts = local_ts_us - self.window_us
        while self.trades and self.trades[0].local_ts_us < min_ts:
            old = self.trades.popleft()
            self.signed_qty -= old.signed_qty
            self.abs_qty -= old.abs_qty
            self.signed_notional -= old.signed_notional
            self.abs_notional -= old.abs_notional
            if old.is_buy:
                self.buy_qty -= old.abs_qty
                self.buy_count -= 1
            else:
                self.sell_qty -= old.abs_qty
                self.sell_count -= 1
        for name in (
            "signed_qty",
            "abs_qty",
            "buy_qty",
            "sell_qty",
            "signed_notional",
            "abs_notional",
        ):
            if abs(getattr(self, name)) <= 1e-9:
                setattr(self, name, 0.0)

    def add_trade(self, local_ts_us: int, side: str, qty: float, price: float = 0.0) -> None:
        is_buy = side == "buy"
        signed = qty if is_buy else -qty
        notional = abs(qty * price) if price > 0.0 else 0.0
        signed_notional = notional if is_buy else -notional
        item = RefTrade(local_ts_us, signed, abs(qty), signed_notional, notional, is_buy)
        self.trades.append(item)
        self.signed_qty += item.signed_qty
        self.abs_qty += item.abs_qty
        self.signed_notional += item.signed_notional
        self.abs_notional += item.abs_notional
        if is_buy:
            self.buy_qty += item.abs_qty
            self.buy_count += 1
        else:
            self.sell_qty += item.abs_qty
            self.sell_count += 1
        self.trim(local_ts_us)

    def tfi(self) -> float:
        if self.abs_qty <= 1e-9:
            return 0.0
        return self.signed_qty / self.abs_qty

    def notional_imbalance(self) -> float:
        if self.abs_notional <= 1e-9:
            return 0.0
        return self.signed_notional / self.abs_notional

    def update_quote(self, bid: float, ask: float, mid: float) -> None:
        if bid > 0.0 and ask > 0.0 and mid > 0.0:
            self.spread_bps = (ask - bid) / mid * 10_000.0
        self.mid_change = 0.0 if self.last_mid is None else mid - self.last_mid
        if self.last_mid is None or self.last_mid <= 0.0:
            self.mid_change_bps = 0.0
        else:
            self.mid_change_bps = math.log(mid / self.last_mid) * 10_000.0
        if self.last_mid is None or abs(self.mid_change) > 1e-12:
            self.frames_since_mid_change = 0
        else:
            self.frames_since_mid_change += 1
        self.last_mid = mid
        self.last_bid = bid
        self.last_ask = ask

    def update_l2(self, updates: list[dict[str, Any]]) -> None:
        self.l2_batches_seen += 1
        for update in updates:
            side = update["side"]
            price = float(update["price"])
            qty = float(update["qty"])
            book = self.bids if side == "buy" else self.asks
            if qty <= 0.0:
                book.pop(price, None)
            else:
                book[price] = qty
        self.last_l2_bid_levels = len(self.bids)
        self.last_l2_ask_levels = len(self.asks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--date", required=True)
    parser.add_argument("--window-us", type=int, default=5_000_000)
    parser.add_argument("--closed-window", type=int, default=5)
    parser.add_argument("--include-l2", action="store_true")
    parser.add_argument("--l2-batch-size", type=int, default=1000)
    parser.add_argument("--l2-max-rows", type=int)
    parser.add_argument("--max-events", type=int)
    parser.add_argument("--sample-every", type=int, default=1)
    parser.add_argument("--run-dir", type=Path)
    return parser.parse_args()


def canonical_path(repo_root: Path, symbol: str, dataset: str, date: str) -> Path:
    return (
        repo_root
        / "data"
        / "canonical"
        / "cex"
        / "bullish"
        / symbol
        / dataset
        / f"dt={date}"
        / "part_000001.csv.gz"
    )


def strategy_module(repo_root: Path):
    path = (
        repo_root
        / "systems"
        / "ccusdt_replay_exchange"
        / "strategies"
        / "python"
        / "ccusdt_tfi_core_idle01"
        / "strategy.py"
    )
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("ccusdt_online_tfi_strategy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import strategy module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def open_rows(path: Path) -> Iterator[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with gzip.open(path, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row


def next_or_none(iterator: Iterator[Any]) -> Any | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def quote_iter(path: Path) -> Iterator[dict[str, Any]]:
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


def trade_iter(path: Path) -> Iterator[dict[str, Any]]:
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


def l2_batch_iter(path: Path, batch_size: int, max_rows: int | None) -> Iterator[dict[str, Any]]:
    current_ts: int | None = None
    batch: list[dict[str, Any]] = []
    rows_seen = 0
    for row in open_rows(path):
        if max_rows is not None and rows_seen >= max_rows:
            break
        rows_seen += 1
        local_ts_us = int(row["local_ts_us"])
        update = {
            "local_ts_us": local_ts_us,
            "side": row["side"],
            "price": float(row["price"]),
            "qty": float(row["qty"]),
        }
        if current_ts is None:
            current_ts = local_ts_us
        if local_ts_us != current_ts or len(batch) >= batch_size:
            yield {"kind": "l2", "local_ts_us": current_ts, "updates": batch}
            batch = []
            current_ts = local_ts_us
        batch.append(update)
    if batch and current_ts is not None:
        yield {"kind": "l2", "local_ts_us": current_ts, "updates": batch}


def choose_next(items: list[Any | None]) -> int | None:
    keys: list[tuple[int, tuple[int, int]]] = []
    for idx, item in enumerate(items):
        if item is not None:
            keys.append((idx, (int(item["local_ts_us"]), idx)))
    if not keys:
        return None
    return min(keys, key=lambda pair: pair[1])[0]


def close(a: float, b: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)


def compare_states(event_seq: int, online: Any, ref: ReferenceFeatureState) -> list[str]:
    errors: list[str] = []
    checks = {
        "signed_qty": (online.signed_qty, ref.signed_qty),
        "abs_qty": (online.abs_qty, ref.abs_qty),
        "buy_qty": (online.buy_qty, ref.buy_qty),
        "sell_qty": (online.sell_qty, ref.sell_qty),
        "signed_notional": (online.signed_notional, ref.signed_notional),
        "abs_notional": (online.abs_notional, ref.abs_notional),
        "tfi": (online.tfi(), ref.tfi()),
        "notional_imbalance": (online.notional_imbalance(), ref.notional_imbalance()),
        "spread_bps": (online.spread_bps, ref.spread_bps),
        "mid_change": (online.mid_change, ref.mid_change),
        "mid_change_bps": (online.mid_change_bps, ref.mid_change_bps),
    }
    for name, (left, right) in checks.items():
        if not close(float(left), float(right)):
            errors.append(f"event {event_seq}: {name} mismatch online={left} reference={right}")
    exact = {
        "rolling_trades": (len(online.trades), len(ref.trades)),
        "buy_count": (online.buy_count, ref.buy_count),
        "sell_count": (online.sell_count, ref.sell_count),
        "frames_since_mid_change": (online.frames_since_mid_change, ref.frames_since_mid_change),
        "l2_batches_seen": (online.l2_batches_seen, ref.l2_batches_seen),
        "last_l2_bid_levels": (online.last_l2_bid_levels, ref.last_l2_bid_levels),
        "last_l2_ask_levels": (online.last_l2_ask_levels, ref.last_l2_ask_levels),
    }
    for name, (left, right) in exact.items():
        if int(left) != int(right):
            errors.append(f"event {event_seq}: {name} mismatch online={left} reference={right}")
    return errors


def ref_snapshot(ref: ReferenceFeatureState) -> dict[str, Any]:
    return {
        "quote": {
            "bid": ref.last_bid,
            "ask": ref.last_ask,
            "mid": ref.last_mid,
            "spread_bps": ref.spread_bps,
            "mid_change": ref.mid_change,
            "mid_change_bps": ref.mid_change_bps,
            "frames_since_mid_change": ref.frames_since_mid_change,
        },
        "trade_flow": {
            "rolling_trades": len(ref.trades),
            "buy_count": ref.buy_count,
            "sell_count": ref.sell_count,
            "buy_qty": ref.buy_qty,
            "sell_qty": ref.sell_qty,
            "signed_qty": ref.signed_qty,
            "abs_qty": ref.abs_qty,
            "tfi": ref.tfi(),
            "signed_notional": ref.signed_notional,
            "abs_notional": ref.abs_notional,
            "notional_imbalance": ref.notional_imbalance(),
        },
        "l2": {
            "batches_seen": ref.l2_batches_seen,
            "bid_levels": ref.last_l2_bid_levels,
            "ask_levels": ref.last_l2_ask_levels,
        },
    }


def nested_get(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def compare_feature_snapshot(
    label: str,
    observed_seq: int,
    online_snapshot: dict[str, Any],
    reference: ReferenceFeatureState,
    include_l2: bool,
) -> list[str]:
    errors: list[str] = []
    expected = ref_snapshot(reference)
    float_paths = [
        "quote.bid",
        "quote.ask",
        "quote.mid",
        "quote.spread_bps",
        "quote.mid_change",
        "quote.mid_change_bps",
        "trade_flow.buy_qty",
        "trade_flow.sell_qty",
        "trade_flow.signed_qty",
        "trade_flow.abs_qty",
        "trade_flow.tfi",
        "trade_flow.signed_notional",
        "trade_flow.abs_notional",
        "trade_flow.notional_imbalance",
    ]
    int_paths = [
        "quote.frames_since_mid_change",
        "trade_flow.rolling_trades",
        "trade_flow.buy_count",
        "trade_flow.sell_count",
    ]
    if include_l2:
        int_paths.extend(["l2.batches_seen", "l2.bid_levels", "l2.ask_levels"])

    for path in float_paths:
        left = nested_get(online_snapshot, path)
        right = nested_get(expected, path)
        if left is None and right is None:
            continue
        if left is None or right is None or not close(float(left), float(right), 1e-8):
            errors.append(
                f"{label} observed_seq={observed_seq}: {path} mismatch "
                f"online={left} reference={right}"
            )
    for path in int_paths:
        left = nested_get(online_snapshot, path)
        right = nested_get(expected, path)
        if int(left or 0) != int(right or 0):
            errors.append(
                f"{label} observed_seq={observed_seq}: {path} mismatch "
                f"online={left} reference={right}"
            )
    return errors


def load_run_checkpoints(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "events.ndjson"
    if not path.exists():
        raise FileNotFoundError(path)
    checkpoints: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            event_type = event.get("event_type")
            payload = event.get("payload") or {}
            snapshot = None
            checkpoint_type = event_type
            observed_seq = None
            if event_type == "order_intent":
                snapshot = payload.get("feature_snapshot")
                intent = payload.get("intent") or {}
                observed_seq = intent.get("observed_seq")
            elif event_type == "strategy_feature_checkpoint":
                snapshot = payload.get("feature_snapshot")
                observed_seq = payload.get("observed_seq")
                if isinstance(snapshot, dict):
                    checkpoint_type = snapshot.get("checkpoint") or checkpoint_type
            if isinstance(snapshot, dict):
                if observed_seq is None:
                    observed_seq = snapshot.get("observed_seq")
                if observed_seq is None:
                    continue
                checkpoints.append(
                    {
                        "event_id": event.get("event_id"),
                        "event_type": event_type,
                        "checkpoint": checkpoint_type,
                        "observed_seq": int(observed_seq),
                        "feature_snapshot": snapshot,
                    }
                )
    return checkpoints


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    module = strategy_module(repo_root)
    online = module.OnlineTfiState(window_us=args.window_us, closed_window=args.closed_window)
    ref = ReferenceFeatureState(window_us=args.window_us)

    q_iter = quote_iter(canonical_path(repo_root, args.symbol, "quote_frame_v1", args.date))
    t_iter = trade_iter(canonical_path(repo_root, args.symbol, "trade_event_v1", args.date))
    l_iter = (
        l2_batch_iter(
            canonical_path(repo_root, args.symbol, "l2_level_update_v1", args.date),
            args.l2_batch_size,
            args.l2_max_rows,
        )
        if args.include_l2
        else iter(())
    )

    next_items: list[Any | None] = [
        next_or_none(q_iter),
        next_or_none(t_iter),
        next_or_none(l_iter),
    ]
    events_seen = 0
    kind_counts = {"quote": 0, "trade": 0, "l2": 0}
    errors: list[str] = []
    checkpoints = load_run_checkpoints(args.run_dir) if args.run_dir else []
    checkpoints = sorted(
        checkpoints,
        key=lambda item: (
            int((item.get("feature_snapshot") or {}).get("local_ts_us") or 0),
            int(item["observed_seq"]),
            int(item.get("event_id") or 0),
        ),
    )
    checkpoint_idx = 0
    checkpoint_checks = 0
    checkpoint_type_counts: dict[str, int] = collections.Counter()

    while True:
        choice = choose_next(next_items)
        if choice is None:
            break
        item = next_items[choice]
        assert item is not None
        local_ts_us = int(item["local_ts_us"])
        while checkpoint_idx < len(checkpoints):
            checkpoint_item = checkpoints[checkpoint_idx]
            snapshot = checkpoint_item["feature_snapshot"]
            target_local_ts_us = int(snapshot.get("local_ts_us") or 0)
            if target_local_ts_us >= local_ts_us:
                break
            checkpoint_checks += 1
            checkpoint_type = str(checkpoint_item["checkpoint"])
            checkpoint_type_counts[checkpoint_type] = checkpoint_type_counts.get(checkpoint_type, 0) + 1
            errors.extend(
                compare_feature_snapshot(
                    f"run_checkpoint event_id={checkpoint_item['event_id']} type={checkpoint_type}",
                    int(checkpoint_item["observed_seq"]),
                    snapshot,
                    ref,
                    args.include_l2,
                )
            )
            checkpoint_idx += 1
            if errors:
                break
        if errors:
            break
        events_seen += 1
        kind = item["kind"]
        kind_counts[kind] += 1

        if kind == "quote":
            quote = item["quote"]
            online.update_quote(quote)
            online.trim(local_ts_us)
            ref.update_quote(quote["bid"], quote["ask"], quote["mid"])
            ref.trim(local_ts_us)
            next_items[choice] = next_or_none(q_iter)
        elif kind == "trade":
            trade = item["trade"]
            online.add_trade(trade["local_ts_us"], trade["side"], trade["qty"], trade["price"])
            online.trim(local_ts_us)
            ref.add_trade(trade["local_ts_us"], trade["side"], trade["qty"], trade["price"])
            ref.trim(local_ts_us)
            next_items[choice] = next_or_none(t_iter)
        elif kind == "l2":
            updates = item["updates"]
            ref.update_l2(updates)
            online.update_l2(
                {
                    "book": {
                        "bid_levels": ref.last_l2_bid_levels,
                        "ask_levels": ref.last_l2_ask_levels,
                    }
                }
            )
            next_items[choice] = next_or_none(l_iter)

        if args.sample_every > 0 and events_seen % args.sample_every == 0:
            errors.extend(compare_states(events_seen, online, ref))
            if errors:
                break
        if args.max_events is not None and events_seen >= args.max_events:
            break
        if errors:
            break

    if not errors:
        while checkpoint_idx < len(checkpoints):
            checkpoint_item = checkpoints[checkpoint_idx]
            snapshot = checkpoint_item["feature_snapshot"]
            checkpoint_checks += 1
            checkpoint_type = str(checkpoint_item["checkpoint"])
            checkpoint_type_counts[checkpoint_type] = checkpoint_type_counts.get(checkpoint_type, 0) + 1
            errors.extend(
                compare_feature_snapshot(
                    f"run_checkpoint event_id={checkpoint_item['event_id']} type={checkpoint_type}",
                    int(checkpoint_item["observed_seq"]),
                    snapshot,
                    ref,
                    args.include_l2,
                )
            )
            checkpoint_idx += 1
            if errors:
                break
    if not errors:
        errors.extend(compare_states(events_seen, online, ref))

    result = {
        "ok": not errors,
        "date": args.date,
        "events_seen": events_seen,
        "kind_counts": kind_counts,
        "window_us": args.window_us,
        "include_l2": args.include_l2,
        "l2_max_rows": args.l2_max_rows,
        "run_dir": None if args.run_dir is None else str(args.run_dir),
        "run_checkpoints_seen": len(checkpoints),
        "run_checkpoint_checks": checkpoint_checks,
        "run_checkpoint_types": dict(checkpoint_type_counts),
        "final_features": {
            "tfi": online.tfi(),
            "signed_qty": online.signed_qty,
            "abs_qty": online.abs_qty,
            "buy_qty": online.buy_qty,
            "sell_qty": online.sell_qty,
            "notional_imbalance": online.notional_imbalance(),
            "rolling_trades": len(online.trades),
            "spread_bps": online.spread_bps,
            "mid_change": online.mid_change,
            "mid_change_bps": online.mid_change_bps,
            "frames_since_mid_change": online.frames_since_mid_change,
            "l2_batches_seen": online.l2_batches_seen,
            "last_l2_bid_levels": online.last_l2_bid_levels,
            "last_l2_ask_levels": online.last_l2_ask_levels,
        },
        "errors": errors[:20],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

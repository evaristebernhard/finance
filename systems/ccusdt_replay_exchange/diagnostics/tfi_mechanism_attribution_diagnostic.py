#!/usr/bin/env python
"""Attribute legacy TFI entries to L2 market mechanisms.

Research-only diagnostic. It explains existing TFI entries through
market-mechanism evidence built from canonical decision frames, quotes, trades,
and L2 updates. Future labels are computed only for attribution and veto
research; they must not enter Runner/Bot/Monitor runtime.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd


SCHEMA_ID = "ccusdt_tfi_mechanism_attribution_v0_1"
EPS = 1e-12
PRICE_SCALE = 100_000_000
US_PER_SEC = 1_000_000

DECISION_ROOT = Path("data/canonical_parquet/cex/bullish")
CANONICAL_ROOT = Path("data/canonical/cex/bullish")
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/tfi_mechanism_attribution")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/strategy/v1-tfi-mechanism-attribution-20260603.md")
DEFAULT_BASELINE = Path(
    "systems/ccusdt_replay_exchange/runs/experiments/"
    "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521"
)


@dataclass(frozen=True)
class Thresholds:
    source_date: str
    fallback: bool
    values: dict[str, dict[str, float]]


class QuoteFrameIndex:
    def __init__(self, rows: list[dict[str, float | int]]) -> None:
        if not rows:
            raise ValueError("quote_frame_v1 index is empty")
        self.rows = rows
        self.ts = np.array([int(row["local_ts_us"]) for row in rows], dtype=np.int64)
        self.bid = np.array([float(row["bid_px"]) for row in rows], dtype=float)
        self.ask = np.array([float(row["ask_px"]) for row in rows], dtype=float)
        self.mid = np.array([float(row["mid_px"]) for row in rows], dtype=float)

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteFrameIndex":
        rows: list[dict[str, float | int]] = []
        path = canonical_path(repo_root, symbol, "quote_frame_v1", day)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                ts = int_float(raw.get("local_ts_us"))
                bid = optional_float(raw.get("bid_px"))
                ask = optional_float(raw.get("ask_px"))
                mid = optional_float(raw.get("mid_px"))
                if ts <= 0 or bid is None or ask is None or bid <= 0.0 or ask <= 0.0:
                    continue
                rows.append(
                    {
                        "local_ts_us": ts,
                        "bid_px": bid,
                        "ask_px": ask,
                        "mid_px": mid if mid is not None and mid > 0.0 else 0.5 * (bid + ask),
                    }
                )
        return cls(rows)

    def index_at_or_before(self, local_ts_us: int) -> int:
        return max(0, int(np.searchsorted(self.ts, int(local_ts_us), side="right") - 1))

    def labels(self, local_ts_us: int, side_sign: int) -> dict[str, Any]:
        entry_idx = self.index_at_or_before(local_ts_us)
        idx20 = self.index_at_or_before(local_ts_us + 20 * US_PER_SEC)
        idx60 = self.index_at_or_before(local_ts_us + 60 * US_PER_SEC)
        entry_bid = float(self.bid[entry_idx])
        entry_ask = float(self.ask[entry_idx])
        entry_mid = float(self.mid[entry_idx])
        exit20_mid = float(self.mid[idx20])
        exit60_bid = float(self.bid[idx60])
        exit60_ask = float(self.ask[idx60])
        exit60_mid = float(self.mid[idx60])
        mid20 = side_sign * 10_000.0 * math.log(exit20_mid / entry_mid) if entry_mid > 0.0 else math.nan
        mid60 = side_sign * 10_000.0 * math.log(exit60_mid / entry_mid) if entry_mid > 0.0 else math.nan
        if side_sign > 0 and entry_ask > 0.0 and exit60_bid > 0.0:
            exec60 = 10_000.0 * math.log(exit60_bid / entry_ask)
        elif side_sign < 0 and entry_bid > 0.0 and exit60_ask > 0.0:
            exec60 = 10_000.0 * math.log(entry_bid / exit60_ask)
        else:
            exec60 = math.nan
        return {
            "label_entry_bid": entry_bid,
            "label_entry_ask": entry_ask,
            "label_entry_mid": entry_mid,
            "label_exit60_bid": exit60_bid,
            "label_exit60_ask": exit60_ask,
            "label_exit60_mid": exit60_mid,
            "mid_return_20s_bps": mid20,
            "mid_return_60s_bps": mid60,
            "top_of_book_executable_60s_bps": exec60,
            "label_valid": bool(idx60 > entry_idx),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--max-rows-per-day", type=int, default=0, help="Optional early-row cap for smoke runs.")
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--run-id")
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days: list[str] = []
    while cur <= last:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def previous_day(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def canonical_path(repo_root: Path, symbol: str, dataset: str, day: str) -> Path:
    return repo_root / CANONICAL_ROOT / symbol / dataset / f"dt={day}" / "part_000001.csv.gz"


def decision_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "part_000001.parquet"


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def int_float(value: Any) -> int:
    out = optional_float(value)
    return int(out) if out is not None else 0


def price_key(price: float) -> int:
    return int(round(float(price) * PRICE_SCALE))


def key_price(key: int) -> float:
    return float(key) / PRICE_SCALE


def side_norm(side: str) -> str:
    raw = str(side or "").lower()
    return "buy" if raw in {"buy", "bid", "b"} else "sell"


def format_float(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}f}"


def read_trades(repo_root: Path, symbol: str, day: str) -> list[dict[str, Any]]:
    path = canonical_path(repo_root, symbol, "trade_event_v1", day)
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            ts = int_float(raw.get("local_ts_us"))
            qty = optional_float(raw.get("qty")) or 0.0
            price = optional_float(raw.get("price")) or 0.0
            if ts <= 0 or qty <= 0.0 or price <= 0.0:
                continue
            side = side_norm(raw.get("side", ""))
            rows.append({"local_ts_us": ts, "side": side, "price": price, "qty": qty})
    rows.sort(key=lambda row: int(row["local_ts_us"]))
    return rows


def iter_l2_batches(repo_root: Path, symbol: str, day: str, max_rows: int = 0) -> Iterator[list[dict[str, Any]]]:
    path = canonical_path(repo_root, symbol, "l2_level_update_v1", day)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        batch: list[dict[str, Any]] = []
        current_ts: int | None = None
        seen = 0
        for raw in reader:
            if max_rows > 0 and seen >= max_rows:
                break
            ts = int_float(raw.get("local_ts_us"))
            if current_ts is not None and ts != current_ts and batch:
                yield batch
                batch = []
            current_ts = ts
            batch.append(
                {
                    "seq": int_float(raw.get("seq")),
                    "exchange_ts_us": int_float(raw.get("exchange_ts_us")),
                    "local_ts_us": ts,
                    "is_snapshot": str(raw.get("is_snapshot", "")).lower() == "true",
                    "side": side_norm(raw.get("side", "")),
                    "price": optional_float(raw.get("price")) or 0.0,
                    "qty": max(0.0, optional_float(raw.get("qty")) or 0.0),
                }
            )
            seen += 1
        if batch:
            yield batch


def top_keys(book_side: dict[int, float], side: str, k: int = 5) -> list[int]:
    keys = sorted(book_side, reverse=(side == "buy"))
    return keys[:k]


def l5_stats(book: dict[str, dict[int, float]]) -> dict[str, float]:
    bids = top_keys(book["buy"], "buy", 5)
    asks = top_keys(book["sell"], "sell", 5)
    bid1 = bids[0] if bids else None
    ask1 = asks[0] if asks else None
    bid_px = key_price(bid1) if bid1 is not None else math.nan
    ask_px = key_price(ask1) if ask1 is not None else math.nan
    bid_qty = float(book["buy"].get(bid1, 0.0)) if bid1 is not None else 0.0
    ask_qty = float(book["sell"].get(ask1, 0.0)) if ask1 is not None else 0.0
    mid = 0.5 * (bid_px + ask_px) if bid_px > 0.0 and ask_px > 0.0 else math.nan
    spread_bps = (ask_px - bid_px) / mid * 10_000.0 if mid > 0.0 else math.nan
    bid_l5_qty = sum(float(book["buy"].get(key, 0.0)) for key in bids)
    ask_l5_qty = sum(float(book["sell"].get(key, 0.0)) for key in asks)
    depth_imb = (bid_l5_qty - ask_l5_qty) / (bid_l5_qty + ask_l5_qty + EPS)
    microprice = (
        (ask_px * bid_qty + bid_px * ask_qty) / (bid_qty + ask_qty + EPS)
        if bid_px > 0.0 and ask_px > 0.0 and (bid_qty + ask_qty) > 0.0
        else math.nan
    )
    micro_offset = 10_000.0 * math.log(microprice / mid) if microprice > 0.0 and mid > 0.0 else math.nan
    return {
        "best_bid_price": bid_px,
        "best_ask_price": ask_px,
        "best_bid_amount": bid_qty,
        "best_ask_amount": ask_qty,
        "bid_l5_qty": bid_l5_qty,
        "ask_l5_qty": ask_l5_qty,
        "mid_price": mid,
        "spread_bps": spread_bps,
        "depth_imbalance_l5": depth_imb,
        "microprice_offset_bps": micro_offset,
    }


def build_l2_event_state(repo_root: Path, symbol: str, day: str, max_rows: int = 0) -> pd.DataFrame:
    trades = read_trades(repo_root, symbol, day)
    trade_pos = 0
    pending: dict[tuple[str, int], float] = defaultdict(float)
    book: dict[str, dict[int, float]] = {"buy": {}, "sell": {}}
    rows: list[dict[str, Any]] = []
    update_count = 0
    started = time.time()

    for batch in iter_l2_batches(repo_root, symbol, day, max_rows):
        if not batch:
            continue
        ts = int(batch[0]["local_ts_us"])
        while trade_pos < len(trades) and int(trades[trade_pos]["local_ts_us"]) <= ts:
            trade = trades[trade_pos]
            book_side = "sell" if trade["side"] == "buy" else "buy"
            pending[(book_side, price_key(float(trade["price"])))] += float(trade["qty"])
            trade_pos += 1
        is_snapshot_batch = any(bool(row["is_snapshot"]) for row in batch)
        if is_snapshot_batch:
            book = {"buy": {}, "sell": {}}
            pending.clear()
        batch_add = 0.0
        batch_cancel = 0.0
        batch_consumed = 0.0
        batch_bid_add = 0.0
        batch_ask_add = 0.0
        batch_bid_cancel = 0.0
        batch_ask_cancel = 0.0
        batch_bid_consumed = 0.0
        batch_ask_consumed = 0.0
        first_seq = int(batch[0]["seq"])
        last_seq = int(batch[-1]["seq"])
        exchange_ts_us = int(batch[-1]["exchange_ts_us"])
        for update in batch:
            side = str(update["side"])
            key = price_key(float(update["price"]))
            new_qty = float(update["qty"])
            old_qty = float(book[side].get(key, 0.0))
            delta = new_qty - old_qty
            add_qty = 0.0
            cancel_qty = 0.0
            consumed_qty = 0.0
            if delta < -EPS:
                decrease = -delta
                pending_key = (side, key)
                pending_qty = float(pending.get(pending_key, 0.0))
                consumed_qty = min(decrease, pending_qty)
                if consumed_qty > 0.0:
                    pending[pending_key] = max(0.0, pending_qty - consumed_qty)
                cancel_qty = max(0.0, decrease - consumed_qty)
            elif delta > EPS:
                add_qty = delta
            if new_qty <= EPS:
                book[side].pop(key, None)
            else:
                book[side][key] = new_qty
            is_bid = side == "buy"
            batch_add += add_qty
            batch_cancel += cancel_qty
            batch_consumed += consumed_qty
            batch_bid_add += add_qty if is_bid else 0.0
            batch_ask_add += add_qty if not is_bid else 0.0
            batch_bid_cancel += cancel_qty if is_bid else 0.0
            batch_ask_cancel += cancel_qty if not is_bid else 0.0
            batch_bid_consumed += consumed_qty if is_bid else 0.0
            batch_ask_consumed += consumed_qty if not is_bid else 0.0
            update_count += 1
        stats = l5_stats(book)
        rows.append(
            {
                "date": day,
                "first_seq": first_seq,
                "last_seq": last_seq,
                "exchange_ts_us": exchange_ts_us,
                "local_ts_us": ts,
                "event_type": "l2_snapshot" if is_snapshot_batch else "l2_update_batch",
                "update_count": len(batch),
                "add_qty": batch_add,
                "cancel_qty": batch_cancel,
                "trade_consumed_qty": batch_consumed,
                "bid_add_qty": batch_bid_add,
                "ask_add_qty": batch_ask_add,
                "bid_cancel_qty": batch_bid_cancel,
                "ask_cancel_qty": batch_ask_cancel,
                "bid_trade_consumed_qty": batch_bid_consumed,
                "ask_trade_consumed_qty": batch_ask_consumed,
                **stats,
            }
        )
        if update_count and update_count % 5_000_000 < len(batch):
            elapsed = max(1e-6, time.time() - started)
            rate = update_count / elapsed
            print(
                f"[tfi_mechanism] {day} L2 updates={update_count:,} "
                f"event_state_rows={len(rows):,} rate={rate:,.0f}/s",
                flush=True,
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["local_ts_us", "last_seq"], inplace=True)
        out.reset_index(drop=True, inplace=True)
    return out


def load_decision_frames(repo_root: Path, symbol: str, day: str, max_rows: int = 0) -> pd.DataFrame:
    path = decision_path(repo_root, symbol, day)
    columns = [
        "local_ts_us",
        "event_index",
        "factor_eligible",
        "best_bid_price",
        "best_bid_amount",
        "best_ask_price",
        "best_ask_amount",
        "mid_price",
        "spread_bps",
        "trade_window_count",
        "trade_buy_amount",
        "trade_sell_amount",
        "trade_flow_imbalance",
        "frames_since_mid_change",
        "past_event_25_bps",
        "fwd_time_60s_bucket",
    ]
    df = pd.read_parquet(path, columns=[col for col in columns if col])
    df = df[df["factor_eligible"].fillna(False)].copy()
    df["date"] = day
    if max_rows > 0 and len(df) > max_rows:
        stride = max(1, int(math.ceil(len(df) / max_rows)))
        df = df.iloc[::stride].head(max_rows).copy()
    return df.sort_values("local_ts_us").reset_index(drop=True)


def trade_prefix(trades: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    ts = np.array([int(row["local_ts_us"]) for row in trades], dtype=np.int64)
    buy = np.array([float(row["qty"]) if row["side"] == "buy" else 0.0 for row in trades], dtype=float)
    sell = np.array([float(row["qty"]) if row["side"] == "sell" else 0.0 for row in trades], dtype=float)
    return {
        "ts": ts,
        "buy": np.concatenate([[0.0], np.cumsum(buy)]),
        "sell": np.concatenate([[0.0], np.cumsum(sell)]),
        "count": np.arange(len(ts) + 1, dtype=float),
    }


def event_prefix(events: pd.DataFrame) -> dict[str, Any]:
    cols = [
        "bid_add_qty",
        "ask_add_qty",
        "bid_cancel_qty",
        "ask_cancel_qty",
        "bid_trade_consumed_qty",
        "ask_trade_consumed_qty",
    ]
    out: dict[str, Any] = {"ts": events["local_ts_us"].to_numpy(dtype=np.int64) if not events.empty else np.array([], dtype=np.int64)}
    for col in cols:
        values = events[col].to_numpy(dtype=float) if col in events else np.array([], dtype=float)
        out[col] = np.concatenate([[0.0], np.cumsum(values)])
    return out


def prefix_sum(prefix: dict[str, Any], col: str, start_ts: int, end_ts: int) -> float:
    ts = prefix["ts"]
    if len(ts) == 0:
        return 0.0
    left = int(np.searchsorted(ts, int(start_ts), side="left"))
    right = int(np.searchsorted(ts, int(end_ts), side="right"))
    arr = prefix[col]
    return float(arr[right] - arr[left])


def decision_mid_at_or_before(dec_ts: np.ndarray, dec_mid: np.ndarray, ts: int) -> float:
    idx = int(np.searchsorted(dec_ts, int(ts), side="right") - 1)
    if idx < 0:
        idx = 0
    return float(dec_mid[idx])


def build_mechanism_frames(
    repo_root: Path,
    symbol: str,
    day: str,
    decisions: pd.DataFrame,
    l2_events: pd.DataFrame,
) -> pd.DataFrame:
    trades = read_trades(repo_root, symbol, day)
    tprefix = trade_prefix(trades)
    eprefix = event_prefix(l2_events)
    dec_ts = decisions["local_ts_us"].to_numpy(dtype=np.int64)
    dec_mid = decisions["mid_price"].to_numpy(dtype=float)
    rows: list[dict[str, Any]] = []
    for row in decisions.itertuples(index=False):
        ts = int(row.local_ts_us)
        out = {
            "date": day,
            "local_ts_us": ts,
            "event_index": int(getattr(row, "event_index", 0) or 0),
            "entry_bid": float(getattr(row, "best_bid_price", math.nan)),
            "entry_ask": float(getattr(row, "best_ask_price", math.nan)),
            "entry_mid": float(getattr(row, "mid_price", math.nan)),
            "entry_spread_bps": float(getattr(row, "spread_bps", math.nan)),
            "decision_tfi": float(getattr(row, "trade_flow_imbalance", 0.0) or 0.0),
            "trade_window_count": int(getattr(row, "trade_window_count", 0) or 0),
            "frames_since_mid_change": float(getattr(row, "frames_since_mid_change", math.nan)),
            "past_event_25_bps": float(getattr(row, "past_event_25_bps", math.nan)),
        }
        for window_ms in (50, 200, 1000, 5000):
            left = ts - window_ms * 1000
            buy = prefix_sum(tprefix, "buy", left, ts)
            sell = prefix_sum(tprefix, "sell", left, ts)
            count = prefix_sum(tprefix, "count", left, ts)
            total = buy + sell
            out[f"buy_qty_{window_ms}ms"] = buy
            out[f"sell_qty_{window_ms}ms"] = sell
            out[f"trade_count_{window_ms}ms"] = count
            out[f"tfi_{window_ms}ms"] = (buy - sell) / (total + EPS)
        for window_ms in (200, 1000):
            left = ts - window_ms * 1000
            for col in (
                "bid_add_qty",
                "ask_add_qty",
                "bid_cancel_qty",
                "ask_cancel_qty",
                "bid_trade_consumed_qty",
                "ask_trade_consumed_qty",
            ):
                out[f"{col}_{window_ms}ms"] = prefix_sum(eprefix, col, left, ts)
            start_mid = decision_mid_at_or_before(dec_ts, dec_mid, left)
            current_mid = out["entry_mid"]
            mid_move_bps = 10_000.0 * math.log(current_mid / start_mid) if current_mid > 0.0 and start_mid > 0.0 else 0.0
            signed_qty = out[f"buy_qty_{window_ms}ms"] - out[f"sell_qty_{window_ms}ms"]
            out[f"mid_move_bps_{window_ms}ms"] = mid_move_bps
            out[f"price_impact_efficiency_{window_ms}ms"] = (
                math.copysign(mid_move_bps, signed_qty) / (abs(signed_qty) + EPS)
                if abs(signed_qty) > EPS
                else 0.0
            )
        bid_amount = float(getattr(row, "best_bid_amount", 0.0) or 0.0)
        ask_amount = float(getattr(row, "best_ask_amount", 0.0) or 0.0)
        bid = out["entry_bid"]
        ask = out["entry_ask"]
        mid = out["entry_mid"]
        micro = (ask * bid_amount + bid * ask_amount) / (bid_amount + ask_amount + EPS) if bid > 0 and ask > 0 else math.nan
        out["microprice_offset_bps"] = 10_000.0 * math.log(micro / mid) if micro > 0.0 and mid > 0.0 else 0.0
        out["depth_imbalance_l1"] = (bid_amount - ask_amount) / (bid_amount + ask_amount + EPS)
        out["long_sweep_cost_proxy_bps"] = 0.5 * out["entry_spread_bps"]
        out["short_sweep_cost_proxy_bps"] = 0.5 * out["entry_spread_bps"]
        rows.append(out)
    return pd.DataFrame(rows)


def quantile_thresholds(frame: pd.DataFrame, source_date: str, fallback: bool) -> Thresholds:
    columns = [
        "entry_spread_bps",
        "frames_since_mid_change",
        "buy_qty_200ms",
        "sell_qty_200ms",
        "bid_cancel_qty_200ms",
        "ask_cancel_qty_200ms",
        "bid_add_qty_200ms",
        "ask_add_qty_200ms",
        "bid_trade_consumed_qty_200ms",
        "ask_trade_consumed_qty_200ms",
        "price_impact_efficiency_200ms",
        "microprice_offset_bps",
    ]
    values: dict[str, dict[str, float]] = {}
    for col in columns:
        if col not in frame or frame.empty:
            values[col] = {"q20": 0.0, "q50": 0.0, "q70": 0.0, "q80": 0.0}
            continue
        series = pd.to_numeric(frame[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if series.empty:
            values[col] = {"q20": 0.0, "q50": 0.0, "q70": 0.0, "q80": 0.0}
        else:
            values[col] = {
                "q20": float(series.quantile(0.20)),
                "q50": float(series.quantile(0.50)),
                "q70": float(series.quantile(0.70)),
                "q80": float(series.quantile(0.80)),
            }
    return Thresholds(source_date=source_date, fallback=fallback, values=values)


def high(value: float, q70: float, q80: float) -> float:
    if not math.isfinite(value):
        return 0.0
    denom = abs(q80 - q70)
    if denom <= EPS:
        return 1.0 if value >= q70 else 0.0
    return float(np.clip((value - q70) / denom, 0.0, 1.0))


def low(value: float, q20: float, q50: float) -> float:
    if not math.isfinite(value):
        return 0.0
    denom = abs(q50 - q20)
    if denom <= EPS:
        return 1.0 if value <= q50 else 0.0
    return float(np.clip((q50 - value) / denom, 0.0, 1.0))


def avg(*values: float) -> float:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    return float(sum(vals) / len(vals)) if vals else 0.0


def score_mechanisms(frame: pd.DataFrame, thresholds: Thresholds) -> pd.DataFrame:
    if frame.empty:
        return frame
    q = thresholds.values
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        d = row._asdict()
        spread_score = low(float(d["entry_spread_bps"]), q["entry_spread_bps"]["q20"], q["entry_spread_bps"]["q50"])
        frames_score = high(float(d["frames_since_mid_change"]), q["frames_since_mid_change"]["q70"], q["frames_since_mid_change"]["q80"])
        micro = float(d["microprice_offset_bps"])
        micro_long = high(micro, q["microprice_offset_bps"]["q70"], q["microprice_offset_bps"]["q80"])
        micro_short = high(-micro, -q["microprice_offset_bps"]["q20"], -q["microprice_offset_bps"]["q50"])
        buy_vol = high(float(d["buy_qty_200ms"]), q["buy_qty_200ms"]["q70"], q["buy_qty_200ms"]["q80"])
        sell_vol = high(float(d["sell_qty_200ms"]), q["sell_qty_200ms"]["q70"], q["sell_qty_200ms"]["q80"])
        ask_consumed = high(float(d["ask_trade_consumed_qty_200ms"]), q["ask_trade_consumed_qty_200ms"]["q70"], q["ask_trade_consumed_qty_200ms"]["q80"])
        bid_consumed = high(float(d["bid_trade_consumed_qty_200ms"]), q["bid_trade_consumed_qty_200ms"]["q70"], q["bid_trade_consumed_qty_200ms"]["q80"])
        ask_refill = high(float(d["ask_add_qty_200ms"]), q["ask_add_qty_200ms"]["q70"], q["ask_add_qty_200ms"]["q80"])
        bid_refill = high(float(d["bid_add_qty_200ms"]), q["bid_add_qty_200ms"]["q70"], q["bid_add_qty_200ms"]["q80"])
        ask_pull = high(float(d["ask_cancel_qty_200ms"]), q["ask_cancel_qty_200ms"]["q70"], q["ask_cancel_qty_200ms"]["q80"])
        bid_pull = high(float(d["bid_cancel_qty_200ms"]), q["bid_cancel_qty_200ms"]["q70"], q["bid_cancel_qty_200ms"]["q80"])
        impact = float(d["mid_move_bps_200ms"])
        up_response = high(impact, 0.0, max(0.1, abs(q["entry_spread_bps"]["q50"])))
        down_response = high(-impact, 0.0, max(0.1, abs(q["entry_spread_bps"]["q50"])))
        tfi_200 = float(d["tfi_200ms"])
        tfi_long = max(0.0, tfi_200)
        tfi_short = max(0.0, -tfi_200)

        continuation_long = avg(tfi_long, buy_vol, ask_consumed, 1.0 - ask_refill, up_response, spread_score)
        continuation_short = avg(tfi_short, sell_vol, bid_consumed, 1.0 - bid_refill, down_response, spread_score)
        trap_long = avg(tfi_short, bid_pull, bid_refill, 1.0 - down_response, micro_long, spread_score)
        trap_short = avg(tfi_long, ask_pull, ask_refill, 1.0 - up_response, micro_short, spread_score)
        absorption_long = avg(tfi_short, sell_vol, bid_refill, 1.0 - down_response, micro_long, spread_score)
        absorption_short = avg(tfi_long, buy_vol, ask_refill, 1.0 - up_response, micro_short, spread_score)
        release_long = avg(frames_score, tfi_long, ask_consumed, 1.0 - ask_refill, micro_long, spread_score)
        release_short = avg(frames_score, tfi_short, bid_consumed, 1.0 - bid_refill, micro_short, spread_score)

        d.update(
            {
                "continuation_long_score": continuation_long,
                "continuation_short_score": continuation_short,
                "trap_long_score": trap_long,
                "trap_short_score": trap_short,
                "absorption_long_score": absorption_long,
                "absorption_short_score": absorption_short,
                "release_long_score": release_long,
                "release_short_score": release_short,
                "execution_quality_long_score": spread_score,
                "execution_quality_short_score": spread_score,
                "threshold_source_date": thresholds.source_date,
                "threshold_fallback_same_day": thresholds.fallback,
                "runtime_status": "research_only_l2_mechanism_attribution",
            }
        )
        rows.append(d)
    return pd.DataFrame(rows)


def attach_mechanisms_to_entries(
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    mechanism: pd.DataFrame,
    quote_books: dict[str, QuoteFrameIndex],
) -> pd.DataFrame:
    if entries.empty:
        return entries
    frames = mechanism.sort_values(["date", "local_ts_us"]).copy()
    parts: list[pd.DataFrame] = []
    for day, g in entries.groupby("date", sort=True):
        left = g.sort_values("entry_ts_us").copy()
        right = frames[frames["date"] == str(day)].sort_values("local_ts_us").copy()
        if right.empty:
            left["mechanism_match_missing"] = True
            parts.append(left)
            continue
        merged = pd.merge_asof(
            left,
            right,
            left_on="entry_ts_us",
            right_on="local_ts_us",
            direction="backward",
            suffixes=("", "_mechanism"),
        )
        merged["mechanism_match_missing"] = merged["local_ts_us"].isna()
        parts.append(merged)
    out = pd.concat(parts, ignore_index=True) if parts else entries.copy()
    if not exits.empty:
        keep = [
            "date",
            "shadow_position_id",
            "raw_bps_mid_fixed60",
            "raw_bps",
            "net_bps_after_cost",
            "net_weighted_bps",
            "exit_ts_us",
            "exit_profile",
        ]
        out = out.merge(exits[[col for col in keep if col in exits.columns]], on=["date", "shadow_position_id"], how="left")
    labels: list[dict[str, Any]] = []
    for row in out.itertuples(index=False):
        day = str(getattr(row, "date"))
        side_sign = int(getattr(row, "direction", 0) or 0)
        qbook = quote_books.get(day)
        labels.append(qbook.labels(int(getattr(row, "entry_ts_us")), side_sign) if qbook else {})
    label_df = pd.DataFrame(labels)
    if not label_df.empty:
        for col in label_df.columns:
            out[col] = label_df[col]
    out["mechanism_label"] = out.apply(classify_entry, axis=1)
    out["primary_reason"] = out.apply(primary_reason, axis=1)
    return out


def classify_entry(row: pd.Series) -> str:
    side = int(row.get("direction") or 0)
    actual = float(row.get("actual_exposure") or 0.0)
    if actual <= EPS:
        if not bool(row.get("admission_accepted", True)):
            return "not_actual_admission_reject"
        return "not_actual_capacity_skip"
    exec_score = float(row.get("execution_quality_long_score" if side > 0 else "execution_quality_short_score") or 0.0)
    exec60 = float(row.get("top_of_book_executable_60s_bps") or row.get("net_bps_after_cost") or 0.0)
    if exec_score < 0.35 or (exec60 <= 0.0 and float(row.get("mid_minus_executable_bps") or 0.0) > 0.0):
        return "execution_cost_failure"
    if side < 0 and float(row.get("trap_long_score") or 0.0) >= 0.60:
        return "withdrawal_trap_like"
    if side > 0 and float(row.get("trap_short_score") or 0.0) >= 0.60:
        return "withdrawal_trap_like"
    if side < 0 and float(row.get("absorption_long_score") or 0.0) >= 0.60:
        return "absorption_reversal_like"
    if side > 0 and float(row.get("absorption_short_score") or 0.0) >= 0.60:
        return "absorption_reversal_like"
    cont = float(row.get("continuation_long_score" if side > 0 else "continuation_short_score") or 0.0)
    rel = float(row.get("release_long_score" if side > 0 else "release_short_score") or 0.0)
    if cont >= 0.60:
        return "flow_continuation"
    if rel >= 0.60:
        return "stale_release"
    return "unclassified"


def primary_reason(row: pd.Series) -> str:
    side = int(row.get("direction") or 0)
    if side > 0:
        scores = {
            "continuation_long": row.get("continuation_long_score", 0.0),
            "trap_short_veto": row.get("trap_short_score", 0.0),
            "absorption_short_veto": row.get("absorption_short_score", 0.0),
            "release_long": row.get("release_long_score", 0.0),
            "execution_quality_long": row.get("execution_quality_long_score", 0.0),
        }
    else:
        scores = {
            "continuation_short": row.get("continuation_short_score", 0.0),
            "trap_long_veto": row.get("trap_long_score", 0.0),
            "absorption_long_veto": row.get("absorption_long_score", 0.0),
            "release_short": row.get("release_short_score", 0.0),
            "execution_quality_short": row.get("execution_quality_short_score", 0.0),
        }
    key, value = max(scores.items(), key=lambda item: float(item[1] or 0.0))
    return f"{key}={float(value or 0.0):.3f}"


def summarize_mechanisms(panel: pd.DataFrame) -> list[dict[str, Any]]:
    if panel.empty:
        return []
    actual = panel[pd.to_numeric(panel["actual_exposure"], errors="coerce").fillna(0.0) > EPS].copy()
    rows: list[dict[str, Any]] = []
    for label, g in actual.groupby("mechanism_label", sort=True):
        exec_col = pd.to_numeric(g["top_of_book_executable_60s_bps"], errors="coerce")
        mid_col = pd.to_numeric(g["mid_return_60s_bps"], errors="coerce")
        weighted = pd.to_numeric(g.get("net_weighted_bps", pd.Series(index=g.index)), errors="coerce")
        rows.append(
            {
                "mechanism_label": label,
                "n": int(len(g)),
                "mean_exec60_bps": float(exec_col.mean()),
                "median_exec60_bps": float(exec_col.median()),
                "mean_mid60_bps": float(mid_col.mean()),
                "hit_rate_exec60": float((exec_col > 0.0).mean()),
                "net_weighted_bps": float(weighted.fillna(0.0).sum()),
                "mean_actual_exposure": float(pd.to_numeric(g["actual_exposure"], errors="coerce").mean()),
            }
        )
    return rows


def summarize_by_day(panel: pd.DataFrame) -> list[dict[str, Any]]:
    actual = panel[pd.to_numeric(panel["actual_exposure"], errors="coerce").fillna(0.0) > EPS].copy()
    rows: list[dict[str, Any]] = []
    for (day, label), g in actual.groupby(["date", "mechanism_label"], sort=True):
        exec_col = pd.to_numeric(g["top_of_book_executable_60s_bps"], errors="coerce")
        rows.append(
            {
                "date": day,
                "mechanism_label": label,
                "n": int(len(g)),
                "mean_exec60_bps": float(exec_col.mean()),
                "hit_rate_exec60": float((exec_col > 0.0).mean()),
                "net_weighted_bps": float(pd.to_numeric(g.get("net_weighted_bps", pd.Series(index=g.index)), errors="coerce").fillna(0.0).sum()),
            }
        )
    return rows


def win_loss_breakdown(panel: pd.DataFrame) -> list[dict[str, Any]]:
    actual = panel[pd.to_numeric(panel["actual_exposure"], errors="coerce").fillna(0.0) > EPS].copy()
    if actual.empty:
        return []
    actual["outcome_bucket"] = np.where(pd.to_numeric(actual["top_of_book_executable_60s_bps"], errors="coerce") > 0.0, "win", "loss")
    rows: list[dict[str, Any]] = []
    for (bucket, label), g in actual.groupby(["outcome_bucket", "mechanism_label"], sort=True):
        rows.append(
            {
                "outcome_bucket": bucket,
                "mechanism_label": label,
                "n": int(len(g)),
                "share": float(len(g) / max(1, len(actual))),
                "mean_exec60_bps": float(pd.to_numeric(g["top_of_book_executable_60s_bps"], errors="coerce").mean()),
                "net_weighted_bps": float(pd.to_numeric(g.get("net_weighted_bps", pd.Series(index=g.index)), errors="coerce").fillna(0.0).sum()),
            }
        )
    return rows


def candidate_veto_rules(panel: pd.DataFrame) -> list[dict[str, Any]]:
    actual = panel[pd.to_numeric(panel["actual_exposure"], errors="coerce").fillna(0.0) > EPS].copy()
    specs = [
        ("legacy_tfi_short_trap_long_veto", (actual["direction"] < 0) & (pd.to_numeric(actual["trap_long_score"], errors="coerce") >= 0.60)),
        ("legacy_tfi_short_absorption_long_veto", (actual["direction"] < 0) & (pd.to_numeric(actual["absorption_long_score"], errors="coerce") >= 0.60)),
        ("legacy_tfi_long_trap_short_veto", (actual["direction"] > 0) & (pd.to_numeric(actual["trap_short_score"], errors="coerce") >= 0.60)),
        ("legacy_tfi_long_absorption_short_veto", (actual["direction"] > 0) & (pd.to_numeric(actual["absorption_short_score"], errors="coerce") >= 0.60)),
        ("execution_quality_bad_veto", pd.to_numeric(actual["execution_quality_long_score"], errors="coerce").fillna(0.0).where(actual["direction"] > 0, pd.to_numeric(actual["execution_quality_short_score"], errors="coerce").fillna(0.0)) < 0.35),
    ]
    rows: list[dict[str, Any]] = []
    for rule_id, mask in specs:
        g = actual[mask].copy()
        if g.empty:
            rows.append({"rule_id": rule_id, "n": 0, "status": "no_candidates"})
            continue
        exec_col = pd.to_numeric(g["top_of_book_executable_60s_bps"], errors="coerce")
        net_removed = float(pd.to_numeric(g.get("net_weighted_bps", pd.Series(index=g.index)), errors="coerce").fillna(0.0).sum())
        mean_exec = float(exec_col.mean())
        if mean_exec < 0.0 and net_removed < 0.0 and len(g) >= 5:
            status = "candidate_veto_promising"
        elif mean_exec >= 0.0 or net_removed >= 0.0:
            status = "candidate_veto_not_supported_in_this_window"
        else:
            status = "candidate_veto_watch_only"
        rows.append(
            {
                "rule_id": rule_id,
                "n": int(len(g)),
                "mean_exec60_bps": mean_exec,
                "hit_rate_exec60": float((exec_col > 0.0).mean()),
                "net_weighted_bps_removed_if_vetoed": net_removed,
                "estimated_net_delta_if_vetoed": -net_removed,
                "status": status,
            }
        )
    return rows


def markdown_table(rows: list[dict[str, Any]], columns: list[str], limit: int = 20) -> str:
    if not rows:
        return "_No rows._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows[:limit]:
        values = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                value = format_float(value)
            values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(path: Path, summary: dict[str, Any], mech_rows: list[dict[str, Any]], breakdown: list[dict[str, Any]], veto_rows: list[dict[str, Any]]) -> None:
    top_mech = sorted(mech_rows, key=lambda row: float(row.get("net_weighted_bps") or 0.0), reverse=True)
    promising_veto = [row for row in veto_rows if row.get("status") == "candidate_veto_promising"]
    lines = [
        "# CCUSDT TFI Mechanism Attribution Diagnostic",
        "",
        f"Status: `{summary['schema_id']}`.",
        "",
        "Boundary: research-only. Inputs are `decision_frame_v1`, `quote_frame_v1`, `trade_event_v1`, and `l2_level_update_v1`; labels are diagnostic-only and must not enter Runner/Bot runtime.",
        "",
        "This is an attribution audit, not a strategy mutation. It explains the current legacy TFI entries with L2 mechanism evidence and only emits possible veto hypotheses for later isolated tests.",
        "",
        "## Setup",
        "",
        f"- symbol: `{summary['symbol']}`",
        f"- dates: `{summary['from_date']}..{summary['to_date']}`",
        f"- baseline entries: `{summary['baseline_entry_rows']}`",
        f"- actual attributed entries: `{summary['actual_attributed_entries']}`",
        f"- L2 event-state rows: `{summary['l2_event_state_rows']}`",
        f"- mechanism-frame rows: `{summary['mechanism_frame_rows']}`",
        f"- output: `{summary['out_dir']}`",
        "",
        "## How To Read This",
        "",
        "- `mechanism_label` is the dominant explanation for an existing TFI entry, not a new entry rule.",
        "- `top_of_book_executable_60s_bps` uses taker entry/exit quotes; `mid_return_60s_bps` is shown only to expose spread-cost mirages.",
        "- `net_weighted_bps_removed_if_vetoed` is the baseline contribution of rows matching that candidate. If it is positive, vetoing those rows would have removed profit in this window.",
        "- The L2 event state is built by processing every L2 update but storing one compressed row per `local_ts_us` batch, with add/cancel/trade-consumed quantities summed inside the batch.",
        "",
        "## Mechanism Summary",
        "",
        markdown_table(top_mech, ["mechanism_label", "n", "mean_exec60_bps", "mean_mid60_bps", "hit_rate_exec60", "net_weighted_bps"]),
        "",
        "## Win/Loss Breakdown",
        "",
        markdown_table(breakdown, ["outcome_bucket", "mechanism_label", "n", "share", "mean_exec60_bps", "net_weighted_bps"]),
        "",
        "## Candidate Veto Rules",
        "",
        markdown_table(veto_rows, ["rule_id", "n", "mean_exec60_bps", "hit_rate_exec60", "net_weighted_bps_removed_if_vetoed", "estimated_net_delta_if_vetoed", "status"]),
        "",
        "## Interpretation",
        "",
        "- This diagnostic attributes the old TFI entries; it does not create new strategy entries.",
        f"- Promising veto rules in this run: `{len(promising_veto)}`. A zero value means the first pass did not find a mechanism bucket that can be safely removed on this evidence alone.",
        "- Veto rows are candidates only. They need isolated follow-up tests before any runtime policy change.",
        "- In this window, several trap/absorption/execution-quality buckets still have positive aggregate contribution, so they are better treated as attribution buckets than immediate filters.",
        "- `R5` remains a risk/sizing memory; it is not used here to explain the current L2 mechanism.",
        "",
        "## Next Isolated Tests",
        "",
        "1. Test exactly one veto at a time against the same baseline entry set.",
        "2. Require improvement in executable return, not only mid return.",
        "3. Reject any veto that removes positive weighted contribution on two or more days.",
        "4. Only after a stable veto exists should it be considered for a fast strategy profile; independent L2 entry is a later problem.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def safe_to_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    start = time.perf_counter()
    args = parse_args()
    repo_root = args.repo_root.resolve()
    days = date_range(args.from_date, args.to_date)
    run_id = args.run_id or f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_v0_1"
    out_dir = (args.out_dir or (repo_root / DEFAULT_OUT_ROOT / run_id)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    l2_parts: list[pd.DataFrame] = []
    mech_raw_by_day: dict[str, pd.DataFrame] = {}
    quote_books: dict[str, QuoteFrameIndex] = {}
    input_rows: dict[str, dict[str, int]] = {}
    for day in days:
        print(f"[tfi_mechanism] build {day}", flush=True)
        quote_books[day] = QuoteFrameIndex.load(repo_root, args.symbol, day)
        decisions = load_decision_frames(repo_root, args.symbol, day, args.max_rows_per_day)
        l2_state = build_l2_event_state(repo_root, args.symbol, day, args.max_rows_per_day)
        mechanism_raw = build_mechanism_frames(repo_root, args.symbol, day, decisions, l2_state)
        l2_parts.append(l2_state)
        mech_raw_by_day[day] = mechanism_raw
        input_rows[day] = {
            "decision_frames": int(len(decisions)),
            "l2_event_state_rows": int(len(l2_state)),
            "mechanism_frames": int(len(mechanism_raw)),
        }

    scored_parts: list[pd.DataFrame] = []
    threshold_manifest: dict[str, Any] = {}
    for day in days:
        prev = previous_day(day)
        prior_frame = mech_raw_by_day.get(prev)
        fallback = prior_frame is None or prior_frame.empty
        source_frame = mech_raw_by_day[day] if fallback else prior_frame
        source_date = day if fallback else prev
        thresholds = quantile_thresholds(source_frame, source_date, fallback)
        threshold_manifest[day] = {"source_date": thresholds.source_date, "fallback_same_day": thresholds.fallback}
        scored_parts.append(score_mechanisms(mech_raw_by_day[day], thresholds))

    l2_all = pd.concat(l2_parts, ignore_index=True) if l2_parts else pd.DataFrame()
    mechanism_all = pd.concat(scored_parts, ignore_index=True) if scored_parts else pd.DataFrame()
    safe_to_parquet(l2_all, out_dir / "l2_event_state.parquet")
    safe_to_parquet(mechanism_all, out_dir / "mechanism_frame.parquet")

    entries_path = repo_root / args.baseline_run_dir / "entries.parquet"
    exits_path = repo_root / args.baseline_run_dir / "exits.parquet"
    entries = pd.read_parquet(entries_path)
    exits = pd.read_parquet(exits_path) if exits_path.exists() else pd.DataFrame()
    entries = entries[entries["date"].astype(str).isin(days)].copy()
    exits = exits[exits["date"].astype(str).isin(days)].copy() if not exits.empty else exits
    attribution = attach_mechanisms_to_entries(entries, exits, mechanism_all, quote_books)
    safe_to_parquet(attribution, out_dir / "legacy_tfi_entry_attribution.parquet")

    mech_rows = summarize_mechanisms(attribution)
    by_day_rows = summarize_by_day(attribution)
    breakdown_rows = win_loss_breakdown(attribution)
    veto_rows = candidate_veto_rules(attribution)
    pd.DataFrame(mech_rows).to_csv(out_dir / "mechanism_summary.csv", index=False)
    pd.DataFrame(by_day_rows).to_csv(out_dir / "mechanism_by_day.csv", index=False)
    pd.DataFrame(breakdown_rows).to_csv(out_dir / "win_loss_mechanism_breakdown.csv", index=False)
    pd.DataFrame(veto_rows).to_csv(out_dir / "candidate_veto_rules.csv", index=False)

    report_path = (repo_root / args.report_path).resolve()
    actual_entries = attribution[pd.to_numeric(attribution["actual_exposure"], errors="coerce").fillna(0.0) > EPS]
    baseline_summary = read_json(repo_root / args.baseline_run_dir / "summary.json")
    summary = {
        "schema_id": SCHEMA_ID,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "out_dir": str(out_dir.relative_to(repo_root) if out_dir.is_relative_to(repo_root) else out_dir),
        "report_path": str(report_path.relative_to(repo_root) if report_path.is_relative_to(repo_root) else report_path),
        "baseline_run_dir": str(args.baseline_run_dir),
        "baseline_run_id": baseline_summary.get("run_id"),
        "baseline_entry_rows": int(len(entries)),
        "actual_attributed_entries": int(len(actual_entries)),
        "l2_event_state_rows": int(len(l2_all)),
        "mechanism_frame_rows": int(len(mechanism_all)),
        "input_rows_by_day": input_rows,
        "threshold_manifest": threshold_manifest,
        "outputs": {
            "l2_event_state": str(out_dir / "l2_event_state.parquet"),
            "mechanism_frame": str(out_dir / "mechanism_frame.parquet"),
            "legacy_tfi_entry_attribution": str(out_dir / "legacy_tfi_entry_attribution.parquet"),
            "mechanism_summary": str(out_dir / "mechanism_summary.csv"),
            "mechanism_by_day": str(out_dir / "mechanism_by_day.csv"),
            "win_loss_mechanism_breakdown": str(out_dir / "win_loss_mechanism_breakdown.csv"),
            "candidate_veto_rules": str(out_dir / "candidate_veto_rules.csv"),
            "report": str(report_path),
        },
        "boundary": "research-only; no Runner/Bot/Monitor changes; future labels are diagnostic-only",
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(report_path, summary, mech_rows, breakdown_rows, veto_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

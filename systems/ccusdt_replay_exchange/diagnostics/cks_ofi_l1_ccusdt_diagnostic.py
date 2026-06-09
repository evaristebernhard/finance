#!/usr/bin/env python
"""Validate Cont-Kukanov-Stoikov L1 OFI on CCUSDT.

Research-only diagnostic. It reconstructs original best-level OFI from
canonical L2 updates, aligns OFI windows to decision frames, and evaluates OFI
against mid and top-of-book taker executable labels. Future labels are
diagnostic only and must not enter Runner/Bot/Monitor runtime.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd


SCHEMA_ID = "ccusdt_cks_l1_ofi_diagnostic_v0_1"
EPS = 1e-12
PRICE_SCALE = 100_000_000
US_PER_SEC = 1_000_000

CANONICAL_ROOT = Path("data/canonical/cex/bullish")
DECISION_ROOT = Path("data/canonical_parquet/cex/bullish")
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/cks_ofi_l1_diagnostic")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/factors/v1-cks-l1-ofi-ccusdt-diagnostic-20260603.md")
DEFAULT_BASELINE = Path(
    "systems/ccusdt_replay_exchange/runs/experiments/"
    "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521"
)


@dataclass(frozen=True)
class DayThreshold:
    source_date: str
    fallback_same_day: bool
    ofi_abs_q70: float
    ofi_abs_q80: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--windows-ms", default="50,200,1000,5000")
    parser.add_argument("--horizons-sec", default="1,5,10,20,60")
    parser.add_argument("--executable-horizons-sec", default="5,20,60")
    parser.add_argument("--max-rows-per-day", type=int, default=0)
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--run-id")
    return parser.parse_args()


def parse_ints(value: str) -> list[int]:
    out = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    if not out:
        raise ValueError(f"expected at least one integer in {value!r}")
    return out


def date_range(start: str, end: str) -> list[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    out: list[str] = []
    while cur <= last:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


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


def key_price(key: int | None) -> float:
    return float(key) / PRICE_SCALE if key is not None else math.nan


def side_norm(side: str) -> str:
    raw = str(side or "").lower()
    return "buy" if raw in {"buy", "bid", "b"} else "sell"


def format_float(value: Any, digits: int = 4) -> str:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(out):
        return ""
    return f"{out:.{digits}f}"


class QuoteFrameIndex:
    def __init__(self, rows: list[dict[str, float | int]]) -> None:
        if not rows:
            raise ValueError("quote_frame_v1 index is empty")
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

    def index_at_or_before(self, local_ts_us: np.ndarray | int) -> np.ndarray | int:
        idx = np.searchsorted(self.ts, local_ts_us, side="right") - 1
        return np.maximum(idx, 0)

    def labels_for(self, local_ts_us: np.ndarray, mid_horizons: list[int], exec_horizons: list[int]) -> pd.DataFrame:
        ts = np.asarray(local_ts_us, dtype=np.int64)
        entry_idx = self.index_at_or_before(ts)
        entry_bid = self.bid[entry_idx]
        entry_ask = self.ask[entry_idx]
        entry_mid = self.mid[entry_idx]
        out: dict[str, Any] = {
            "label_entry_bid": entry_bid,
            "label_entry_ask": entry_ask,
            "label_entry_mid": entry_mid,
            "label_valid": np.ones(len(ts), dtype=bool),
        }
        for horizon in mid_horizons:
            exit_idx = self.index_at_or_before(ts + horizon * US_PER_SEC)
            exit_mid = self.mid[exit_idx]
            out[f"raw_mid_{horizon}s_bps"] = np.where(
                (entry_mid > 0.0) & (exit_mid > 0.0),
                10_000.0 * np.log(exit_mid / entry_mid),
                np.nan,
            )
            out["label_valid"] &= exit_idx > entry_idx
        for horizon in exec_horizons:
            exit_idx = self.index_at_or_before(ts + horizon * US_PER_SEC)
            exit_bid = self.bid[exit_idx]
            exit_ask = self.ask[exit_idx]
            out[f"long_exec_{horizon}s_bps"] = np.where(
                (entry_ask > 0.0) & (exit_bid > 0.0),
                10_000.0 * np.log(exit_bid / entry_ask),
                np.nan,
            )
            out[f"short_exec_{horizon}s_bps"] = np.where(
                (entry_bid > 0.0) & (exit_ask > 0.0),
                10_000.0 * np.log(entry_bid / exit_ask),
                np.nan,
            )
            out["label_valid"] &= exit_idx > entry_idx
        return pd.DataFrame(out)

    def mid_at_or_before(self, local_ts_us: np.ndarray) -> np.ndarray:
        return self.mid[self.index_at_or_before(np.asarray(local_ts_us, dtype=np.int64))]


def read_trades(repo_root: Path, symbol: str, day: str) -> list[dict[str, Any]]:
    path = canonical_path(repo_root, symbol, "trade_event_v1", day)
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            ts = int_float(raw.get("local_ts_us"))
            price = optional_float(raw.get("price")) or 0.0
            qty = optional_float(raw.get("qty")) or 0.0
            if ts <= 0 or price <= 0.0 or qty <= 0.0:
                continue
            rows.append({"local_ts_us": ts, "side": side_norm(raw.get("side", "")), "price": price, "qty": qty})
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
    return sorted(book_side, reverse=(side == "buy"))[:k]


def book_stats(book: dict[str, dict[int, float]]) -> dict[str, float | int | None]:
    bids = top_keys(book["buy"], "buy", 5)
    asks = top_keys(book["sell"], "sell", 5)
    bid_key = bids[0] if bids else None
    ask_key = asks[0] if asks else None
    bid_px = key_price(bid_key)
    ask_px = key_price(ask_key)
    bid_qty = float(book["buy"].get(bid_key, 0.0)) if bid_key is not None else 0.0
    ask_qty = float(book["sell"].get(ask_key, 0.0)) if ask_key is not None else 0.0
    mid = 0.5 * (bid_px + ask_px) if bid_px > 0.0 and ask_px > 0.0 else math.nan
    spread_bps = (ask_px - bid_px) / mid * 10_000.0 if mid > 0.0 else math.nan
    bid_l5_qty = sum(float(book["buy"].get(key, 0.0)) for key in bids)
    ask_l5_qty = sum(float(book["sell"].get(key, 0.0)) for key in asks)
    return {
        "bid_key": bid_key,
        "ask_key": ask_key,
        "best_bid_price": bid_px,
        "best_ask_price": ask_px,
        "best_bid_amount": bid_qty,
        "best_ask_amount": ask_qty,
        "mid_price": mid,
        "spread_bps": spread_bps,
        "bid_l5_qty": bid_l5_qty,
        "ask_l5_qty": ask_l5_qty,
    }


def cks_ofi(prev: dict[str, float | int | None], cur: dict[str, float | int | None]) -> float:
    pb0 = float(prev["best_bid_price"])
    qb0 = float(prev["best_bid_amount"])
    pa0 = float(prev["best_ask_price"])
    qa0 = float(prev["best_ask_amount"])
    pb1 = float(cur["best_bid_price"])
    qb1 = float(cur["best_bid_amount"])
    pa1 = float(cur["best_ask_price"])
    qa1 = float(cur["best_ask_amount"])
    if not all(math.isfinite(v) and v > 0.0 for v in (pb0, pa0, pb1, pa1)):
        return 0.0
    return (
        (qb1 if pb1 >= pb0 else 0.0)
        - (qb0 if pb1 <= pb0 else 0.0)
        - (qa1 if pa1 <= pa0 else 0.0)
        + (qa0 if pa1 >= pa0 else 0.0)
    )


def cks_quote_move(prev: dict[str, float | int | None], cur: dict[str, float | int | None]) -> float:
    pb0 = float(prev["best_bid_price"])
    qb0 = float(prev["best_bid_amount"])
    pa0 = float(prev["best_ask_price"])
    qa0 = float(prev["best_ask_amount"])
    pb1 = float(cur["best_bid_price"])
    qb1 = float(cur["best_bid_amount"])
    pa1 = float(cur["best_ask_price"])
    qa1 = float(cur["best_ask_amount"])
    if not all(math.isfinite(v) and v > 0.0 for v in (pb0, pa0, pb1, pa1)):
        return 0.0
    out = 0.0
    if pb1 > pb0:
        out += qb1
    elif pb1 < pb0:
        out -= qb0
    if pa1 < pa0:
        out -= qa1
    elif pa1 > pa0:
        out += qa0
    return out


def build_ofi_event_frame(repo_root: Path, symbol: str, day: str, max_rows: int = 0) -> pd.DataFrame:
    trades = read_trades(repo_root, symbol, day)
    trade_pos = 0
    pending: dict[tuple[str, int], float] = defaultdict(float)
    book: dict[str, dict[int, float]] = {"buy": {}, "sell": {}}
    rows: list[dict[str, Any]] = []
    update_count = 0
    started = time.time()

    prev_completed = book_stats(book)
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

        before_batch = book_stats(book)
        add_by_key: dict[int, float] = defaultdict(float)
        cancel_by_key: dict[int, float] = defaultdict(float)
        consume_by_key: dict[int, float] = defaultdict(float)
        total_add = 0.0
        total_cancel = 0.0
        total_consume = 0.0
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

            if side == "buy":
                add_pressure = add_qty
                cancel_pressure = -cancel_qty
                consume_pressure = -consumed_qty
            else:
                add_pressure = -add_qty
                cancel_pressure = cancel_qty
                consume_pressure = consumed_qty
            if not is_snapshot_batch:
                total_add += add_pressure
                total_cancel += cancel_pressure
                total_consume += consume_pressure
                add_by_key[key] += add_pressure
                cancel_by_key[key] += cancel_pressure
                consume_by_key[key] += consume_pressure
            update_count += 1

        cur_completed = book_stats(book)
        l1_keys = {
            before_batch.get("bid_key"),
            before_batch.get("ask_key"),
            cur_completed.get("bid_key"),
            cur_completed.get("ask_key"),
        }
        l1_keys.discard(None)
        l1_add = sum(float(add_by_key.get(int(key), 0.0)) for key in l1_keys)
        l1_cancel = sum(float(cancel_by_key.get(int(key), 0.0)) for key in l1_keys)
        l1_consume = sum(float(consume_by_key.get(int(key), 0.0)) for key in l1_keys)
        raw = cks_ofi(prev_completed, cur_completed)
        quote_move = cks_quote_move(prev_completed, cur_completed)
        mid0 = float(prev_completed["mid_price"])
        mid1 = float(cur_completed["mid_price"])
        mid_move = 10_000.0 * math.log(mid1 / mid0) if mid0 > 0.0 and mid1 > 0.0 else math.nan
        depth = float(cur_completed["best_bid_amount"]) + float(cur_completed["best_ask_amount"])
        notional_depth = depth * float(cur_completed["mid_price"]) if float(cur_completed["mid_price"]) > 0.0 else math.nan
        l5_base = prev_completed if is_snapshot_batch else before_batch
        l5 = (float(cur_completed["bid_l5_qty"]) - float(l5_base["bid_l5_qty"])) - (
            float(cur_completed["ask_l5_qty"]) - float(l5_base["ask_l5_qty"])
        )
        residual = raw - l1_add - l1_cancel - l1_consume - quote_move
        rows.append(
            {
                "date": day,
                "local_ts_us": ts,
                "exchange_ts_us": exchange_ts_us,
                "first_seq": first_seq,
                "last_seq": last_seq,
                "update_count": len(batch),
                "is_snapshot_batch": bool(is_snapshot_batch),
                "channel_confidence": "snapshot_rebuild_no_event_channel" if is_snapshot_batch else "incremental_event_channel",
                "ofi_l1_raw_event": raw,
                "ofi_l1_depth_norm_event": raw / (depth + EPS),
                "ofi_l1_notional_norm_event": raw / (notional_depth + EPS) if notional_depth > 0.0 else 0.0,
                "ofi_l1_sign_event": int(np.sign(raw)),
                "ofi_add_l1_event": l1_add,
                "ofi_cancel_l1_event": l1_cancel,
                "ofi_consume_l1_event": l1_consume,
                "ofi_quote_move_l1_event": quote_move,
                "ofi_residual_l1_event": residual,
                "ofi_l5_research_only_event": l5,
                "ofi_add_all_event": total_add,
                "ofi_cancel_all_event": total_cancel,
                "ofi_consume_all_event": total_consume,
                "same_window_mid_move_bps_event": mid_move,
                "best_bid_price": float(cur_completed["best_bid_price"]),
                "best_bid_amount": float(cur_completed["best_bid_amount"]),
                "best_ask_price": float(cur_completed["best_ask_price"]),
                "best_ask_amount": float(cur_completed["best_ask_amount"]),
                "mid_price": float(cur_completed["mid_price"]),
                "spread_bps": float(cur_completed["spread_bps"]),
                "bid_l5_qty": float(cur_completed["bid_l5_qty"]),
                "ask_l5_qty": float(cur_completed["ask_l5_qty"]),
            }
        )
        prev_completed = cur_completed
        if update_count and update_count % 5_000_000 < len(batch):
            elapsed = max(1e-6, time.time() - started)
            print(
                f"[cks_ofi] {day} L2 updates={update_count:,} "
                f"event_rows={len(rows):,} rate={update_count / elapsed:,.0f}/s",
                flush=True,
            )

    out = pd.DataFrame(rows)
    if not out.empty:
        out.sort_values(["local_ts_us", "last_seq"], inplace=True)
        out.reset_index(drop=True, inplace=True)
        event_std = float(pd.to_numeric(out["ofi_l1_raw_event"], errors="coerce").std(ddof=0) or 0.0)
        event_mean = float(pd.to_numeric(out["ofi_l1_raw_event"], errors="coerce").mean() or 0.0)
        out["ofi_l1_z_event"] = (out["ofi_l1_raw_event"] - event_mean) / (event_std + EPS)
    return out


def load_decisions(repo_root: Path, symbol: str, day: str, max_rows: int = 0) -> pd.DataFrame:
    path = decision_path(repo_root, symbol, day)
    cols = [
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
    ]
    df = pd.read_parquet(path, columns=cols)
    df = df[df["factor_eligible"].fillna(False)].copy()
    df["date"] = day
    if max_rows > 0 and len(df) > max_rows:
        stride = max(1, int(math.ceil(len(df) / max_rows)))
        df = df.iloc[::stride].head(max_rows).copy()
    return df.sort_values("local_ts_us").reset_index(drop=True)


def prefix_frame(events: pd.DataFrame) -> dict[str, Any]:
    cols = [
        "ofi_l1_raw_event",
        "ofi_l1_depth_norm_event",
        "ofi_l1_notional_norm_event",
        "ofi_add_l1_event",
        "ofi_cancel_l1_event",
        "ofi_consume_l1_event",
        "ofi_quote_move_l1_event",
        "ofi_residual_l1_event",
        "ofi_l5_research_only_event",
        "same_window_mid_move_bps_event",
    ]
    out: dict[str, Any] = {"ts": events["local_ts_us"].to_numpy(dtype=np.int64)}
    for col in cols:
        values = pd.to_numeric(events[col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        out[col] = np.concatenate([[0.0], np.cumsum(values)])
    return out


def window_sum(prefix: dict[str, Any], col: str, ts: np.ndarray, window_us: int) -> np.ndarray:
    event_ts = prefix["ts"]
    left = np.searchsorted(event_ts, ts - window_us, side="left")
    right = np.searchsorted(event_ts, ts, side="right")
    arr = prefix[col]
    return arr[right] - arr[left]


def add_day_window_zscores(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    out["ofi_l1_z"] = 0.0
    for (_, window_ms), idx in out.groupby(["date", "window_ms"], sort=False).groups.items():
        values = pd.to_numeric(out.loc[idx, "ofi_l1_raw"], errors="coerce").fillna(0.0)
        out.loc[idx, "ofi_l1_z"] = (values - float(values.mean())) / (float(values.std(ddof=0)) + EPS)
    return out


def build_decision_panel(
    decisions: pd.DataFrame,
    events: pd.DataFrame,
    quotes: QuoteFrameIndex,
    windows_ms: list[int],
    mid_horizons: list[int],
    exec_horizons: list[int],
) -> pd.DataFrame:
    if decisions.empty or events.empty:
        return pd.DataFrame()
    prefix = prefix_frame(events)
    ts = decisions["local_ts_us"].to_numpy(dtype=np.int64)
    label_df = quotes.labels_for(ts, mid_horizons, exec_horizons)
    parts: list[pd.DataFrame] = []
    for window_ms in windows_ms:
        window_us = window_ms * 1000
        left_mid = quotes.mid_at_or_before(ts - window_us)
        cur_mid = pd.to_numeric(decisions["mid_price"], errors="coerce").to_numpy(dtype=float)
        same_window_mid = np.where(
            (left_mid > 0.0) & (cur_mid > 0.0),
            10_000.0 * np.log(cur_mid / left_mid),
            np.nan,
        )
        raw = window_sum(prefix, "ofi_l1_raw_event", ts, window_us)
        depth_norm = window_sum(prefix, "ofi_l1_depth_norm_event", ts, window_us)
        notional_norm = window_sum(prefix, "ofi_l1_notional_norm_event", ts, window_us)
        part = pd.DataFrame(
            {
                "date": decisions["date"].astype(str).to_numpy(),
                "local_ts_us": ts,
                "event_index": pd.to_numeric(decisions["event_index"], errors="coerce").fillna(0).to_numpy(dtype=np.int64),
                "window_ms": window_ms,
                "ofi_l1_raw": raw,
                "ofi_l1_depth_norm": depth_norm,
                "ofi_l1_notional_norm": notional_norm,
                "ofi_l1_sign": np.sign(raw).astype(int),
                "ofi_add_l1": window_sum(prefix, "ofi_add_l1_event", ts, window_us),
                "ofi_cancel_l1": window_sum(prefix, "ofi_cancel_l1_event", ts, window_us),
                "ofi_consume_l1": window_sum(prefix, "ofi_consume_l1_event", ts, window_us),
                "ofi_quote_move_l1": window_sum(prefix, "ofi_quote_move_l1_event", ts, window_us),
                "ofi_residual_l1": window_sum(prefix, "ofi_residual_l1_event", ts, window_us),
                "ofi_l5_research_only": window_sum(prefix, "ofi_l5_research_only_event", ts, window_us),
                "same_window_mid_move_bps": same_window_mid,
                "same_window_event_mid_move_bps": window_sum(prefix, "same_window_mid_move_bps_event", ts, window_us),
                "tfi": pd.to_numeric(decisions["trade_flow_imbalance"], errors="coerce").fillna(0.0).to_numpy(dtype=float),
                "trade_window_count": pd.to_numeric(decisions["trade_window_count"], errors="coerce").fillna(0.0).to_numpy(dtype=float),
                "entry_bid": pd.to_numeric(decisions["best_bid_price"], errors="coerce").to_numpy(dtype=float),
                "entry_ask": pd.to_numeric(decisions["best_ask_price"], errors="coerce").to_numpy(dtype=float),
                "entry_mid": pd.to_numeric(decisions["mid_price"], errors="coerce").to_numpy(dtype=float),
                "entry_spread_bps": pd.to_numeric(decisions["spread_bps"], errors="coerce").to_numpy(dtype=float),
                "frames_since_mid_change": pd.to_numeric(decisions["frames_since_mid_change"], errors="coerce").to_numpy(dtype=float),
                "past_event_25_bps": pd.to_numeric(decisions["past_event_25_bps"], errors="coerce").to_numpy(dtype=float),
            }
        )
        part = pd.concat([part.reset_index(drop=True), label_df.reset_index(drop=True)], axis=1)
        parts.append(part)
    out = pd.concat(parts, ignore_index=True)
    out = add_day_window_zscores(out)
    return out.replace([np.inf, -np.inf], np.nan)


def spearman(x: pd.Series, y: pd.Series) -> float:
    tmp = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    if len(tmp) < 5 or tmp["x"].nunique() < 2 or tmp["y"].nunique() < 2:
        return math.nan
    return float(tmp["x"].rank().corr(tmp["y"].rank()))


def directional_exec(row: pd.DataFrame, factor: str, horizon: int) -> pd.Series:
    values = pd.to_numeric(row[factor], errors="coerce").fillna(0.0)
    long_exec = pd.to_numeric(row[f"long_exec_{horizon}s_bps"], errors="coerce")
    short_exec = pd.to_numeric(row[f"short_exec_{horizon}s_bps"], errors="coerce")
    return pd.Series(np.where(values >= 0.0, long_exec, short_exec), index=row.index)


def summarize_factor(panel: pd.DataFrame, factor: str, factor_class: str, horizon: int = 60) -> dict[str, Any]:
    df = panel[[factor, f"raw_mid_{horizon}s_bps", f"long_exec_{horizon}s_bps", f"short_exec_{horizon}s_bps", "date"]].copy()
    df[factor] = pd.to_numeric(df[factor], errors="coerce")
    df = df.dropna(subset=[factor, f"raw_mid_{horizon}s_bps"])
    if len(df) < 20 or df[factor].nunique() < 5:
        return {
            "factor": factor,
            "factor_class": factor_class,
            "n": int(len(df)),
            "status": "not_supported_insufficient_variation",
        }
    q20 = float(df[factor].quantile(0.20))
    q80 = float(df[factor].quantile(0.80))
    top = df[df[factor] >= q80].copy()
    bottom = df[df[factor] <= q20].copy()
    top_mid = pd.to_numeric(top[f"raw_mid_{horizon}s_bps"], errors="coerce")
    bottom_mid = pd.to_numeric(bottom[f"raw_mid_{horizon}s_bps"], errors="coerce")
    top_exec = pd.to_numeric(top[f"long_exec_{horizon}s_bps"], errors="coerce")
    bottom_exec = pd.to_numeric(bottom[f"short_exec_{horizon}s_bps"], errors="coerce")
    selected_exec = pd.concat([top_exec, bottom_exec], ignore_index=True)
    top_bottom_mid = float(top_mid.mean() - bottom_mid.mean())
    top_bottom_exec = float(selected_exec.mean())
    selected_mid = pd.concat([top_mid, -bottom_mid], ignore_index=True)
    spread_gap = float(selected_mid.mean() - selected_exec.mean())
    day_signs: list[bool] = []
    for _, g in df.groupby("date", sort=True):
        tq20 = float(g[factor].quantile(0.20))
        tq80 = float(g[factor].quantile(0.80))
        gt = g[g[factor] >= tq80]
        gb = g[g[factor] <= tq20]
        if len(gt) + len(gb) < 10:
            continue
        day_exec = pd.concat(
            [
                pd.to_numeric(gt[f"long_exec_{horizon}s_bps"], errors="coerce"),
                pd.to_numeric(gb[f"short_exec_{horizon}s_bps"], errors="coerce"),
            ]
        ).mean()
        day_signs.append(bool(day_exec > 0.0))
    spearman_mid = spearman(df[factor], df[f"raw_mid_{horizon}s_bps"])
    signed_exec = directional_exec(df, factor, horizon)
    spearman_exec = spearman(df[factor].abs(), signed_exec)
    if top_bottom_exec > 0.25 and len(day_signs) > 0 and sum(day_signs) / len(day_signs) >= 0.67:
        status = "executable_valid"
    elif top_bottom_mid > 0.25 and top_bottom_exec <= 0.0:
        status = "spread_cost_mirage"
    elif top_bottom_mid > 0.25:
        status = "predictive_mid_valid"
    elif abs(spearman_mid) >= 0.03:
        status = "explanatory_valid"
    else:
        status = "not_supported"
    return {
        "factor": factor,
        "factor_class": factor_class,
        "horizon_sec": horizon,
        "n": int(len(df)),
        "spearman_mid": spearman_mid,
        "spearman_exec": spearman_exec,
        "top_bottom_mid_bps": top_bottom_mid,
        "top_bottom_exec_bps": top_bottom_exec,
        "hit_rate_exec": float((selected_exec > 0.0).mean()),
        "daily_sign_rate": float(sum(day_signs) / len(day_signs)) if day_signs else math.nan,
        "mid_minus_exec_bps": spread_gap,
        "spread_cost_mirage": bool(top_bottom_mid > 0.25 and top_bottom_exec <= 0.0),
        "status": status,
    }


def summarize_by_day(panel: pd.DataFrame, factor: str = "ofi_l1_depth_norm", horizon: int = 60) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (day, window_ms), g in panel.groupby(["date", "window_ms"], sort=True):
        row = summarize_factor(g, factor, "cks_l1_ofi", horizon)
        row["date"] = day
        row["window_ms"] = int(window_ms)
        rows.append(row)
    return rows


def tfi_ofi_cell(row: pd.Series, ofi_threshold: float) -> str:
    tfi = float(row.get("tfi") or 0.0)
    ofi = float(row.get("ofi_l1_depth_norm") or 0.0)
    tfi_strong = abs(tfi) >= 0.999
    ofi_strong = abs(ofi) >= ofi_threshold if ofi_threshold > EPS else abs(ofi) > EPS
    if tfi_strong and ofi_strong and np.sign(tfi) == np.sign(ofi):
        return "TFI_aligned_OFI"
    if tfi_strong and ofi_strong and np.sign(tfi) != np.sign(ofi):
        return "TFI_against_OFI"
    if abs(tfi) < 0.25 and ofi_strong:
        return "OFI_only_quote_pressure"
    if tfi_strong and abs(ofi) < 0.25 * max(ofi_threshold, EPS):
        return "TFI_only_active_pressure"
    if (not tfi_strong) and ofi_strong:
        return "TFI_weak_OFI_strong"
    if tfi_strong and not ofi_strong:
        return "TFI_strong_OFI_weak"
    return "weak_or_mixed"


def thresholds_for(day: str, raw_by_day: dict[str, pd.DataFrame]) -> DayThreshold:
    prev = previous_day(day)
    source = raw_by_day.get(prev)
    fallback = source is None or source.empty
    if fallback:
        source = raw_by_day[day]
        source_date = day
    else:
        source_date = prev
    values = pd.to_numeric(source["ofi_l1_depth_norm"], errors="coerce").abs().replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return DayThreshold(source_date, fallback, 0.0, 0.0)
    return DayThreshold(source_date, fallback, float(values.quantile(0.70)), float(values.quantile(0.80)))


def summarize_tfi_ofi_cells(panel: pd.DataFrame, horizon: int = 60) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (window_ms, cell), g in panel.groupby(["window_ms", "tfi_ofi_cell"], sort=True):
        ofi = pd.to_numeric(g["ofi_l1_depth_norm"], errors="coerce").fillna(0.0)
        side = np.sign(np.where(ofi.abs() > 0.0, ofi, pd.to_numeric(g["tfi"], errors="coerce").fillna(0.0)))
        raw_mid = pd.to_numeric(g[f"raw_mid_{horizon}s_bps"], errors="coerce")
        long_exec = pd.to_numeric(g[f"long_exec_{horizon}s_bps"], errors="coerce")
        short_exec = pd.to_numeric(g[f"short_exec_{horizon}s_bps"], errors="coerce")
        signed_mid = pd.Series(side, index=g.index) * raw_mid
        signed_exec = pd.Series(np.where(side >= 0, long_exec, short_exec), index=g.index)
        day_means = []
        for _, dg in g.groupby("date", sort=True):
            dofi = pd.to_numeric(dg["ofi_l1_depth_norm"], errors="coerce").fillna(0.0)
            dside = np.sign(np.where(dofi.abs() > 0.0, dofi, pd.to_numeric(dg["tfi"], errors="coerce").fillna(0.0)))
            dexec = pd.Series(
                np.where(
                    dside >= 0,
                    pd.to_numeric(dg[f"long_exec_{horizon}s_bps"], errors="coerce"),
                    pd.to_numeric(dg[f"short_exec_{horizon}s_bps"], errors="coerce"),
                )
            )
            day_means.append(float(dexec.mean()))
        rows.append(
            {
                "window_ms": int(window_ms),
                "tfi_ofi_cell": cell,
                "n": int(len(g)),
                "mean_mid60_bps": float(signed_mid.mean()),
                "mean_exec60_bps": float(signed_exec.mean()),
                "hit_rate_exec60": float((signed_exec > 0.0).mean()),
                "worst_day_exec60_bps": float(min(day_means)) if day_means else math.nan,
                "daily_sign_rate": float(sum(v > 0.0 for v in day_means) / len(day_means)) if day_means else math.nan,
            }
        )
    return rows


def summarize_channels(panel: pd.DataFrame, horizon: int = 60) -> list[dict[str, Any]]:
    specs = [
        ("ofi_l1_raw", "total"),
        ("ofi_add_l1", "add"),
        ("ofi_cancel_l1", "cancel"),
        ("ofi_consume_l1", "consume"),
        ("ofi_quote_move_l1", "quote_move"),
        ("ofi_residual_l1", "residual"),
        ("ofi_l5_research_only", "l5_research_only"),
    ]
    rows: list[dict[str, Any]] = []
    for factor, klass in specs:
        for window_ms, g in panel.groupby("window_ms", sort=True):
            row = summarize_factor(g, factor, klass, horizon)
            row["window_ms"] = int(window_ms)
            rows.append(row)
    return rows


def candidate_rules(cell_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    mapping = {
        "TFI_aligned_OFI": "confirmation_candidate",
        "TFI_against_OFI": "veto_candidate",
        "TFI_weak_OFI_strong": "independent_entry_watchlist",
        "OFI_only_quote_pressure": "independent_entry_watchlist",
        "TFI_strong_OFI_weak": "tfi_only_control",
    }
    for row in cell_rows:
        cell = str(row.get("tfi_ofi_cell"))
        if cell not in mapping:
            continue
        mean_exec = float(row.get("mean_exec60_bps") or 0.0)
        mean_mid = float(row.get("mean_mid60_bps") or 0.0)
        status = mapping[cell]
        if mean_mid > 0.0 and mean_exec <= 0.0:
            status = "spread_cost_mirage"
        elif status == "veto_candidate" and mean_exec >= 0.0:
            status = "veto_not_supported"
        elif status in {"confirmation_candidate", "independent_entry_watchlist", "tfi_only_control"} and mean_exec <= 0.0:
            status = "not_supported_executable_negative"
        out.append(
            {
                "rule_id": f"{cell}_w{int(row.get('window_ms') or 0)}",
                "window_ms": int(row.get("window_ms") or 0),
                "cell": cell,
                "n": int(row.get("n") or 0),
                "mean_mid60_bps": mean_mid,
                "mean_exec60_bps": mean_exec,
                "hit_rate_exec60": float(row.get("hit_rate_exec60") or 0.0),
                "status": status,
                "runtime_action": "none_research_only",
            }
        )
    return out


def attach_legacy_entries(
    panel: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    horizon: int = 60,
    primary_window_ms: int = 1000,
) -> pd.DataFrame:
    if panel.empty or entries.empty:
        return pd.DataFrame()
    p = panel[panel["window_ms"] == primary_window_ms].copy()
    if p.empty:
        p = panel.copy()
    parts: list[pd.DataFrame] = []
    for day, g in entries.groupby("date", sort=True):
        left = g.sort_values("entry_ts_us").copy()
        right = p[p["date"] == str(day)].sort_values("local_ts_us").copy()
        if right.empty:
            continue
        merged = pd.merge_asof(
            left,
            right,
            left_on="entry_ts_us",
            right_on="local_ts_us",
            direction="backward",
            suffixes=("", "_ofi"),
        )
        parts.append(merged)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not exits.empty and not out.empty and "shadow_position_id" in out.columns:
        exit_cols = [
            col
            for col in [
                "date",
                "shadow_position_id",
                "exit_ts_us",
                "raw_bps_mid_fixed60",
                "net_bps_after_cost",
                "net_weighted_bps",
            ]
            if col in exits.columns
        ]
        out = out.merge(exits[exit_cols], on=["date", "shadow_position_id"], how="left", suffixes=("", "_baseline_exit"))
    if not out.empty:
        direction = pd.to_numeric(out.get("direction", out.get("side", 0)), errors="coerce").fillna(0.0)
        ofi = pd.to_numeric(out["ofi_l1_depth_norm"], errors="coerce").fillna(0.0)
        out["ofi_aligns_legacy_side"] = np.sign(direction) == np.sign(ofi)
        out["ofi_directional_exec60_bps"] = np.where(
            ofi >= 0.0,
            pd.to_numeric(out[f"long_exec_{horizon}s_bps"], errors="coerce"),
            pd.to_numeric(out[f"short_exec_{horizon}s_bps"], errors="coerce"),
        )
    return out


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def safe_to_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


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


def write_report(
    path: Path,
    summary: dict[str, Any],
    factor_rows: list[dict[str, Any]],
    cell_rows: list[dict[str, Any]],
    channel_rows: list[dict[str, Any]],
    rule_rows: list[dict[str, Any]],
) -> None:
    top_factors = sorted(factor_rows, key=lambda row: float(row.get("top_bottom_exec_bps") or -999.0), reverse=True)
    primary = [row for row in top_factors if row.get("factor") == "ofi_l1_depth_norm" and int(row.get("window_ms") or 0) == 1000]
    primary_status = primary[0].get("status") if primary else "missing"
    lines = [
        "# CCUSDT CKS-L1 OFI Diagnostic",
        "",
        f"Status: `{summary['schema_id']}`.",
        "",
        "Boundary: research-only. The diagnostic reads canonical quote/decision/trade/L2 data and optional baseline entries only for overlay; labels are diagnostic-only and must not enter Runner/Bot runtime.",
        "",
        "## Core Formula",
        "",
        "For completed best bid/ask states before and after an L2 event batch:",
        "",
        "```text",
        "e_n = 1{P_B[n] >= P_B[n-1]} q_B[n]",
        "    - 1{P_B[n] <= P_B[n-1]} q_B[n-1]",
        "    - 1{P_A[n] <= P_A[n-1]} q_A[n]",
        "    + 1{P_A[n] >= P_A[n-1]} q_A[n-1]",
        "```",
        "",
        "Positive OFI means best-bid demand strengthened or best-ask supply weakened. Negative OFI means the opposite.",
        "",
        "## Setup",
        "",
        f"- symbol: `{summary['symbol']}`",
        f"- dates: `{summary['from_date']}..{summary['to_date']}`",
        f"- event rows: `{summary['ofi_event_rows']}`",
        f"- decision panel rows: `{summary['ofi_decision_rows']}`",
        f"- output: `{summary['out_dir']}`",
        f"- primary 1s OFI status: `{primary_status}`",
        "",
        "## Factor Summary",
        "",
        markdown_table(
            top_factors,
            [
                "window_ms",
                "factor",
                "factor_class",
                "n",
                "spearman_mid",
                "spearman_exec",
                "top_bottom_mid_bps",
                "top_bottom_exec_bps",
                "daily_sign_rate",
                "status",
            ],
            limit=24,
        ),
        "",
        "## OFI vs TFI Cells",
        "",
        markdown_table(
            sorted(cell_rows, key=lambda row: (int(row.get("window_ms") or 0), str(row.get("tfi_ofi_cell")))),
            ["window_ms", "tfi_ofi_cell", "n", "mean_mid60_bps", "mean_exec60_bps", "hit_rate_exec60", "worst_day_exec60_bps"],
            limit=40,
        ),
        "",
        "## Channel Summary",
        "",
        markdown_table(
            sorted(channel_rows, key=lambda row: float(row.get("top_bottom_exec_bps") or -999.0), reverse=True),
            ["window_ms", "factor", "factor_class", "top_bottom_mid_bps", "top_bottom_exec_bps", "status"],
            limit=28,
        ),
        "",
        "## Candidate Rules",
        "",
        markdown_table(rule_rows, ["rule_id", "n", "mean_mid60_bps", "mean_exec60_bps", "status", "runtime_action"], limit=32),
        "",
        "## Interpretation Rules",
        "",
        "- `explanatory_valid` means OFI describes same/near-window price movement; it is not enough for trading.",
        "- `predictive_mid_valid` means mid labels improve before crossing cost.",
        "- `executable_valid` means top-of-book taker labels also survive.",
        "- `spread_cost_mirage` means mid improves but crossing destroys the result.",
        "- `confirmation_candidate` / `veto_candidate` / `independent_entry_watchlist` are research labels only.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    started = time.perf_counter()
    args = parse_args()
    repo_root = args.repo_root.resolve()
    days = date_range(args.from_date, args.to_date)
    windows_ms = parse_ints(args.windows_ms)
    mid_horizons = parse_ints(args.horizons_sec)
    exec_horizons = parse_ints(args.executable_horizons_sec)
    run_id = args.run_id or f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_v0_1"
    out_dir = (args.out_dir or (repo_root / DEFAULT_OUT_ROOT / run_id)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    quote_by_day: dict[str, QuoteFrameIndex] = {}
    event_by_day: dict[str, pd.DataFrame] = {}
    panel_parts: list[pd.DataFrame] = []
    input_rows: dict[str, dict[str, int]] = {}
    for day in days:
        print(f"[cks_ofi] build {day}", flush=True)
        quotes = QuoteFrameIndex.load(repo_root, args.symbol, day)
        quote_by_day[day] = quotes
        events = build_ofi_event_frame(repo_root, args.symbol, day, args.max_rows_per_day)
        decisions = load_decisions(repo_root, args.symbol, day, args.max_rows_per_day)
        panel = build_decision_panel(decisions, events, quotes, windows_ms, mid_horizons, exec_horizons)
        event_by_day[day] = events
        panel_parts.append(panel)
        input_rows[day] = {
            "ofi_event_rows": int(len(events)),
            "decision_rows": int(len(decisions)),
            "ofi_decision_rows": int(len(panel)),
        }

    ofi_events = pd.concat(list(event_by_day.values()), ignore_index=True) if event_by_day else pd.DataFrame()
    ofi_panel = pd.concat(panel_parts, ignore_index=True) if panel_parts else pd.DataFrame()

    threshold_manifest: dict[str, Any] = {}
    if not ofi_panel.empty:
        scored_parts: list[pd.DataFrame] = []
        raw_panel_by_day = {day: ofi_panel[ofi_panel["date"] == day] for day in days}
        for day in days:
            threshold = thresholds_for(day, raw_panel_by_day)
            threshold_manifest[day] = {
                "source_date": threshold.source_date,
                "fallback_same_day": threshold.fallback_same_day,
                "ofi_abs_q70": threshold.ofi_abs_q70,
                "ofi_abs_q80": threshold.ofi_abs_q80,
            }
            part = raw_panel_by_day[day].copy()
            part["ofi_abs_q70_source"] = threshold.ofi_abs_q70
            part["ofi_abs_q80_source"] = threshold.ofi_abs_q80
            part["tfi_ofi_cell"] = part.apply(lambda row: tfi_ofi_cell(row, threshold.ofi_abs_q70), axis=1)
            scored_parts.append(part)
        ofi_panel = pd.concat(scored_parts, ignore_index=True)

    safe_to_parquet(ofi_events, out_dir / "ofi_event_frame.parquet")
    safe_to_parquet(ofi_panel, out_dir / "ofi_decision_panel.parquet")

    factor_rows: list[dict[str, Any]] = []
    for factor, klass in [
        ("ofi_l1_raw", "cks_l1_total"),
        ("ofi_l1_depth_norm", "cks_l1_total"),
        ("ofi_l1_notional_norm", "cks_l1_total"),
        ("ofi_l1_z", "cks_l1_total"),
        ("ofi_l5_research_only", "l5_research_only"),
    ]:
        for window_ms, g in ofi_panel.groupby("window_ms", sort=True):
            row = summarize_factor(g, factor, klass, 60)
            row["window_ms"] = int(window_ms)
            factor_rows.append(row)
    by_day_rows = summarize_by_day(ofi_panel, "ofi_l1_depth_norm", 60)
    cell_rows = summarize_tfi_ofi_cells(ofi_panel, 60)
    channel_rows = summarize_channels(ofi_panel, 60)
    rule_rows = candidate_rules(cell_rows)

    pd.DataFrame(factor_rows).to_csv(out_dir / "ofi_factor_summary.csv", index=False)
    pd.DataFrame(by_day_rows).to_csv(out_dir / "ofi_by_day.csv", index=False)
    pd.DataFrame(cell_rows).to_csv(out_dir / "ofi_vs_tfi_cells.csv", index=False)
    pd.DataFrame(channel_rows).to_csv(out_dir / "ofi_channel_summary.csv", index=False)
    pd.DataFrame(rule_rows).to_csv(out_dir / "candidate_ofi_rules.csv", index=False)

    overlay = pd.DataFrame()
    entries_path = repo_root / args.baseline_run_dir / "entries.parquet"
    exits_path = repo_root / args.baseline_run_dir / "exits.parquet"
    if entries_path.exists():
        entries = pd.read_parquet(entries_path)
        entries = entries[entries["date"].astype(str).isin(days)].copy()
        exits = pd.read_parquet(exits_path) if exits_path.exists() else pd.DataFrame()
        exits = exits[exits["date"].astype(str).isin(days)].copy() if not exits.empty else exits
        overlay = attach_legacy_entries(ofi_panel, entries, exits, horizon=60, primary_window_ms=1000)
    overlay.to_csv(out_dir / "ofi_legacy_tfi_entry_overlay.csv", index=False)

    report_path = (repo_root / args.report_path).resolve()
    summary = {
        "schema_id": SCHEMA_ID,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "windows_ms": windows_ms,
        "mid_horizons_sec": mid_horizons,
        "executable_horizons_sec": exec_horizons,
        "out_dir": str(out_dir.relative_to(repo_root) if out_dir.is_relative_to(repo_root) else out_dir),
        "report_path": str(report_path.relative_to(repo_root) if report_path.is_relative_to(repo_root) else report_path),
        "input_rows_by_day": input_rows,
        "threshold_manifest": threshold_manifest,
        "ofi_event_rows": int(len(ofi_events)),
        "ofi_decision_rows": int(len(ofi_panel)),
        "legacy_overlay_rows": int(len(overlay)),
        "outputs": {
            "ofi_event_frame": str(out_dir / "ofi_event_frame.parquet"),
            "ofi_decision_panel": str(out_dir / "ofi_decision_panel.parquet"),
            "ofi_factor_summary": str(out_dir / "ofi_factor_summary.csv"),
            "ofi_by_day": str(out_dir / "ofi_by_day.csv"),
            "ofi_vs_tfi_cells": str(out_dir / "ofi_vs_tfi_cells.csv"),
            "ofi_channel_summary": str(out_dir / "ofi_channel_summary.csv"),
            "ofi_legacy_tfi_entry_overlay": str(out_dir / "ofi_legacy_tfi_entry_overlay.csv"),
            "candidate_ofi_rules": str(out_dir / "candidate_ofi_rules.csv"),
            "report": str(report_path),
        },
        "boundary": "research-only; no Runner/Bot/Monitor changes; labels are diagnostic-only",
        "elapsed_wall_ms": int((time.perf_counter() - started) * 1000),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(report_path, summary, factor_rows, cell_rows, channel_rows, rule_rows)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()

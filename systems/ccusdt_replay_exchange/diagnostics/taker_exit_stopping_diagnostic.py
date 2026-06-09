#!/usr/bin/env python
"""Offline taker-exit stopping diagnostic for q70 CCUSDT profiles.

This is a mathematical diagnostic, not a runtime policy. It uses future path
information to decompose the stopping problem:

    taker_net(t) = mid_alpha(t) - entry_cross - exit_cross(t)

The output is meant to explain where fixed/managed exits lose edge under
top-of-book taker execution, especially whether the loss is alpha decay or
unfriendly exit spread.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


RUN_ROOT = Path("systems/ccusdt_replay_exchange/runs")
EXPERIMENT_ROOT = RUN_ROOT / "experiments"
QUOTE_FRAME_ROOT = Path("data/canonical/cex/bullish")
DEFAULT_FAST_RUN = "fast_adm_q70_idle01_g1_peakguard_taker_quoteidx_v1_20260516_18_20260521"
DEFAULT_FIXED_RUN = "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_v2_20260516_18_20260521"
DEFAULT_STRICT_TOTALS = RUN_ROOT / "q70_strict_taker_first_cut_20260516_18_20260521" / "totals.csv"
DEFAULT_HORIZONS = [1, 2, 3, 5, 10, 15, 20, 30, 45, 60]
EPS = 1e-12
OFFLINE_LABEL_COLUMNS = {
    "fixed60_taker_net_bps",
    "fixed60_delta_from_now_bps",
    "alpha_decay_to_60_bps",
    "oracle_best_net_bps",
    "oracle_best_exit_sec",
    "best_future_net_bps",
    "best_future_exit_sec",
    "best_future_net_gain_bps",
    "spread_blocked_exit",
}
PANEL_KEY_COLUMNS = {
    "date",
    "shadow_position_id",
    "entry_ts_us",
    "state_ts_us",
    "target_horizon_sec",
}


@dataclass(frozen=True)
class Quote:
    seq: int
    exchange_ts_us: int
    local_ts_us: int
    bid: float
    ask: float
    mid: float
    spread_bps: float


@dataclass(frozen=True)
class Trade:
    local_ts_us: int
    side: str
    price: float
    qty: float
    notional_quote: float


class QuoteIndex:
    def __init__(self, quotes: list[Quote]) -> None:
        if not quotes:
            raise ValueError("empty quote index")
        self.quotes = quotes
        self.local_ts = [quote.local_ts_us for quote in quotes]

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteIndex":
        path = repo_root / QUOTE_FRAME_ROOT / symbol / "quote_frame_v1" / f"dt={day}" / "part_000001.csv.gz"
        quotes: list[Quote] = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                bid = optional_float(row.get("bid_px"))
                ask = optional_float(row.get("ask_px"))
                if bid is None or ask is None or bid <= 0.0 or ask <= 0.0:
                    continue
                mid = optional_float(row.get("mid_px"))
                if mid is None or mid <= 0.0:
                    mid = 0.5 * (bid + ask)
                spread_bps = optional_float(row.get("spread_bps"))
                if spread_bps is None:
                    spread_bps = math.log(ask / bid) * 10_000.0
                quotes.append(
                    Quote(
                        seq=int(row.get("seq") or len(quotes)),
                        exchange_ts_us=int(row.get("exchange_ts_us") or 0),
                        local_ts_us=int(row.get("local_ts_us") or 0),
                        bid=bid,
                        ask=ask,
                        mid=mid,
                        spread_bps=spread_bps,
                    )
                )
        return cls(quotes)

    def at_or_before(self, local_ts_us: int) -> Quote:
        idx = bisect.bisect_right(self.local_ts, int(local_ts_us)) - 1
        if idx < 0:
            idx = 0
        return self.quotes[idx]

    def at_or_after(self, local_ts_us: int) -> Quote:
        idx = bisect.bisect_left(self.local_ts, int(local_ts_us))
        if idx >= len(self.quotes):
            idx = len(self.quotes) - 1
        return self.quotes[idx]

    def slice_between(self, start_us: int, end_us: int) -> list[Quote]:
        left = bisect.bisect_left(self.local_ts, int(start_us))
        right = bisect.bisect_right(self.local_ts, int(end_us))
        return self.quotes[left:right]


class TradeIndex:
    def __init__(self, trades: list[Trade]) -> None:
        self.trades = trades
        self.local_ts = [trade.local_ts_us for trade in trades]
        self.buy_qty_prefix = [0.0]
        self.sell_qty_prefix = [0.0]
        self.buy_notional_prefix = [0.0]
        self.sell_notional_prefix = [0.0]
        self.buy_count_prefix = [0]
        self.sell_count_prefix = [0]
        for trade in trades:
            is_buy = trade.side == "buy"
            is_sell = trade.side == "sell"
            self.buy_qty_prefix.append(self.buy_qty_prefix[-1] + (trade.qty if is_buy else 0.0))
            self.sell_qty_prefix.append(self.sell_qty_prefix[-1] + (trade.qty if is_sell else 0.0))
            self.buy_notional_prefix.append(
                self.buy_notional_prefix[-1] + (trade.notional_quote if is_buy else 0.0)
            )
            self.sell_notional_prefix.append(
                self.sell_notional_prefix[-1] + (trade.notional_quote if is_sell else 0.0)
            )
            self.buy_count_prefix.append(self.buy_count_prefix[-1] + (1 if is_buy else 0))
            self.sell_count_prefix.append(self.sell_count_prefix[-1] + (1 if is_sell else 0))

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "TradeIndex":
        path = repo_root / QUOTE_FRAME_ROOT / symbol / "trade_event_v1" / f"dt={day}" / "part_000001.csv.gz"
        trades: list[Trade] = []
        if not path.exists():
            return cls(trades)
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                local_ts_us = int(row.get("local_ts_us") or 0)
                price = optional_float(row.get("price"))
                qty = optional_float(row.get("qty"))
                if local_ts_us <= 0 or price is None or qty is None:
                    continue
                notional = optional_float(row.get("notional_quote"))
                trades.append(
                    Trade(
                        local_ts_us=local_ts_us,
                        side=str(row.get("side") or "").lower(),
                        price=price,
                        qty=qty,
                        notional_quote=notional if notional is not None else price * qty,
                    )
                )
        return cls(trades)

    def stats_between(self, start_us: int, end_us: int, direction: int) -> dict[str, float]:
        left = bisect.bisect_right(self.local_ts, int(start_us))
        right = bisect.bisect_right(self.local_ts, int(end_us))
        buy_qty = self.buy_qty_prefix[right] - self.buy_qty_prefix[left]
        sell_qty = self.sell_qty_prefix[right] - self.sell_qty_prefix[left]
        buy_notional = self.buy_notional_prefix[right] - self.buy_notional_prefix[left]
        sell_notional = self.sell_notional_prefix[right] - self.sell_notional_prefix[left]
        buy_count = self.buy_count_prefix[right] - self.buy_count_prefix[left]
        sell_count = self.sell_count_prefix[right] - self.sell_count_prefix[left]
        if direction >= 0:
            same_qty, opposite_qty = buy_qty, sell_qty
            same_notional, opposite_notional = buy_notional, sell_notional
            same_count, opposite_count = buy_count, sell_count
        else:
            same_qty, opposite_qty = sell_qty, buy_qty
            same_notional, opposite_notional = sell_notional, buy_notional
            same_count, opposite_count = sell_count, buy_count
        total_qty = buy_qty + sell_qty
        total_notional = buy_notional + sell_notional
        return {
            "trade_count_since_entry": float(buy_count + sell_count),
            "same_side_trade_count": float(same_count),
            "opposite_side_trade_count": float(opposite_count),
            "same_side_qty": same_qty,
            "opposite_side_qty": opposite_qty,
            "same_minus_opposite_qty": same_qty - opposite_qty,
            "same_side_notional": same_notional,
            "opposite_side_notional": opposite_notional,
            "same_minus_opposite_notional": same_notional - opposite_notional,
            "trade_qty_imbalance": (same_qty - opposite_qty) / total_qty if total_qty > EPS else 0.0,
            "trade_notional_imbalance": (
                (same_notional - opposite_notional) / total_notional if total_notional > EPS else 0.0
            ),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--fast-run-id", default=DEFAULT_FAST_RUN)
    parser.add_argument("--fixed-run-id", default=DEFAULT_FIXED_RUN)
    parser.add_argument("--strict-totals-csv", type=Path, default=DEFAULT_STRICT_TOTALS)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--horizons-sec", default=",".join(str(item) for item in DEFAULT_HORIZONS))
    parser.add_argument("--oracle-max-sec", type=float, default=60.0)
    parser.add_argument("--min-oracle-sec", type=float, default=1.0)
    parser.add_argument("--actual-only", action="store_true", default=True)
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out: list[str] = []
    while current <= right:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def side_direction(side: str, direction: Any) -> int:
    if str(side).lower() == "buy":
        return 1
    if str(side).lower() == "sell":
        return -1
    raw = int(numeric(direction))
    return 1 if raw >= 0 else -1


def decompose_taker(side: str, direction: Any, entry: Quote, exit_quote: Quote) -> dict[str, float]:
    d = side_direction(side, direction)
    if d > 0:
        mid_alpha = math.log(exit_quote.mid / entry.mid) * 10_000.0
        entry_cross = math.log(entry.ask / entry.mid) * 10_000.0
        exit_cross = math.log(exit_quote.mid / exit_quote.bid) * 10_000.0
        taker_net = math.log(exit_quote.bid / entry.ask) * 10_000.0
    else:
        mid_alpha = math.log(entry.mid / exit_quote.mid) * 10_000.0
        entry_cross = math.log(entry.mid / entry.bid) * 10_000.0
        exit_cross = math.log(exit_quote.ask / exit_quote.mid) * 10_000.0
        taker_net = math.log(entry.bid / exit_quote.ask) * 10_000.0
    return {
        "mid_alpha_bps": mid_alpha,
        "entry_cross_bps": entry_cross,
        "exit_cross_bps": exit_cross,
        "total_cross_bps": entry_cross + exit_cross,
        "taker_net_bps": taker_net,
        "identity_error_bps": taker_net - (mid_alpha - entry_cross - exit_cross),
    }


def signal_entry_execution_cost_bps(side: str, signal_mid: float | None, entry: Quote) -> float:
    """Entry fill cost relative to the strategy signal mark, not quote midpoint.

    This reconciles the first-principles quote decomposition with the existing
    fast-vs-strict reports, which mark entry execution against the strategy's
    decision-frame mid. The quote-truth entry crossing cost is always positive;
    this signal-mark cost can be negative when the signal mid is stale relative
    to the executable top of book.
    """
    if signal_mid is None or signal_mid <= 0.0:
        return math.nan
    if str(side).lower() == "buy":
        return math.log(entry.ask / signal_mid) * 10_000.0
    return math.log(signal_mid / entry.bid) * 10_000.0


def quantile(values: list[float], q: float) -> float:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        return math.nan
    if len(clean) == 1:
        return clean[0]
    pos = (len(clean) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return clean[lo]
    frac = pos - lo
    return clean[lo] * (1.0 - frac) + clean[hi] * frac


def summarize_group(rows: list[dict[str, Any]], *, key_fields: dict[str, Any]) -> dict[str, Any]:
    exposure = sum(numeric(row["actual_exposure"]) for row in rows)
    weighted = lambda field: sum(numeric(row["actual_exposure"]) * numeric(row[field]) for row in rows)
    exit_cross = [numeric(row["exit_cross_bps"]) for row in rows]
    taker = [numeric(row["taker_net_bps"]) for row in rows]
    out = dict(key_fields)
    out.update(
        {
            "entries": len(rows),
            "actual_exposure": exposure,
            "weighted_mid_alpha_bps": weighted("mid_alpha_bps"),
            "weighted_entry_cross_bps": weighted("entry_cross_bps"),
            "weighted_signal_entry_execution_cost_bps": weighted(
                "signal_entry_execution_cost_bps"
            ),
            "weighted_signal_entry_basis_bps": weighted("signal_entry_basis_bps"),
            "weighted_exit_cross_bps": weighted("exit_cross_bps"),
            "weighted_total_cross_bps": weighted("total_cross_bps"),
            "weighted_taker_net_bps": weighted("taker_net_bps"),
            "mean_taker_net_bps": (sum(taker) / len(taker)) if taker else math.nan,
            "median_taker_net_bps": quantile(taker, 0.50),
            "mean_signal_entry_execution_cost_bps": (
                sum(numeric(row["signal_entry_execution_cost_bps"]) for row in rows) / len(rows)
                if rows
                else math.nan
            ),
            "mean_exit_cross_bps": (sum(exit_cross) / len(exit_cross)) if exit_cross else math.nan,
            "median_exit_cross_bps": quantile(exit_cross, 0.50),
            "p90_exit_cross_bps": quantile(exit_cross, 0.90),
            "p95_exit_cross_bps": quantile(exit_cross, 0.95),
            "wide_exit_cross_gt_1bps": sum(1 for row in rows if numeric(row["exit_cross_bps"]) > 1.0),
            "wide_exit_cross_gt_2bps": sum(1 for row in rows if numeric(row["exit_cross_bps"]) > 2.0),
            "negative_taker_net_count": sum(1 for row in rows if numeric(row["taker_net_bps"]) < 0.0),
        }
    )
    return out


def weighted_sum(rows: list[dict[str, Any]], value_field: str, weight_field: str = "actual_exposure") -> float:
    return sum(numeric(row.get(weight_field)) * numeric(row.get(value_field)) for row in rows)


def entry_id(row: dict[str, Any]) -> int:
    return int(numeric(row.get("shadow_position_id")))


def quote_mid_alpha_since(prev: Quote, current: Quote, direction: int) -> float:
    if prev.mid <= 0.0 or current.mid <= 0.0:
        return 0.0
    return direction * math.log(current.mid / prev.mid) * 10_000.0


def build_previsible_rows_for_entry(
    *,
    entry: dict[str, Any],
    quote_index: QuoteIndex,
    trade_index: TradeIndex,
    horizons: list[float],
    oracle_max_sec: float,
    min_oracle_sec: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    day = str(entry["date"])
    position_id = entry_id(entry)
    entry_ts = int(entry["entry_ts_us"])
    side = str(entry.get("side") or "")
    direction = side_direction(side, entry.get("direction"))
    actual = numeric(entry.get("actual_exposure"))
    signal_mid = optional_float(entry.get("entry_mid"))
    stored_entry_cross = optional_float(entry.get("entry_cross_bps"))
    entry_quote = quote_index.at_or_before(entry_ts)
    signal_entry_cost = signal_entry_execution_cost_bps(side, signal_mid, entry_quote)
    fixed60_quote = quote_index.at_or_before(entry_ts + 60_000_000)
    fixed60_dec = decompose_taker(side, direction, entry_quote, fixed60_quote)
    signal_basis = signal_entry_cost - fixed60_dec["entry_cross_bps"]

    path_quotes = quote_index.slice_between(entry_ts, entry_ts + int(oracle_max_sec * 1_000_000))
    if not path_quotes or path_quotes[-1].local_ts_us < fixed60_quote.local_ts_us:
        path_quotes.append(fixed60_quote)
    path_decisions: list[tuple[Quote, dict[str, float]]] = [
        (quote, decompose_taker(side, direction, entry_quote, quote)) for quote in path_quotes
    ]
    if not path_decisions:
        path_decisions = [(fixed60_quote, fixed60_dec)]

    min_oracle_ts = entry_ts + int(min_oracle_sec * 1_000_000)
    oracle_eligible = [
        item for item in path_decisions if item[0].local_ts_us >= min_oracle_ts
    ] or path_decisions
    best_quote, best_dec = max(oracle_eligible, key=lambda item: item[1]["taker_net_bps"])
    best_mid_quote, best_mid_dec = max(oracle_eligible, key=lambda item: item[1]["mid_alpha_bps"])
    fixed60_net = fixed60_dec["taker_net_bps"]
    fixed60_mid_alpha = fixed60_dec["mid_alpha_bps"]

    states: list[dict[str, Any]] = []
    for horizon in horizons:
        target_ts = entry_ts + int(horizon * 1_000_000)
        current_quote = quote_index.at_or_before(target_ts)
        current_dec = decompose_taker(side, direction, entry_quote, current_quote)
        elapsed_sec = max(0.0, (current_quote.local_ts_us - entry_ts) / 1_000_000.0)
        history = [
            (quote, dec)
            for quote, dec in path_decisions
            if quote.local_ts_us <= current_quote.local_ts_us
        ]
        if not history:
            history = [(current_quote, current_dec)]
        running_high = max(dec["taker_net_bps"] for _, dec in history)
        running_low = min(dec["taker_net_bps"] for _, dec in history)
        drawdown = running_high - current_dec["taker_net_bps"]
        runup_from_low = current_dec["taker_net_bps"] - running_low
        previous_5s_quote = quote_index.at_or_before(current_quote.local_ts_us - 5_000_000)
        previous_2s_quote = quote_index.at_or_before(current_quote.local_ts_us - 2_000_000)
        recent_5s = quote_mid_alpha_since(previous_5s_quote, current_quote, direction)
        recent_2s = quote_mid_alpha_since(previous_2s_quote, current_quote, direction)
        trade_all = trade_index.stats_between(entry_ts, current_quote.local_ts_us, direction)
        trade_5s = trade_index.stats_between(current_quote.local_ts_us - 5_000_000, current_quote.local_ts_us, direction)

        future = [
            (quote, dec)
            for quote, dec in path_decisions
            if quote.local_ts_us > current_quote.local_ts_us
        ]
        if future:
            future_best_quote, future_best_dec = max(future, key=lambda item: item[1]["taker_net_bps"])
        else:
            future_best_quote, future_best_dec = current_quote, current_dec
        row = {
            "date": day,
            "shadow_position_id": position_id,
            "entry_ts_us": entry_ts,
            "state_ts_us": current_quote.local_ts_us,
            "target_horizon_sec": horizon,
            "age_sec": elapsed_sec,
            "side": side,
            "direction": direction,
            "cell": entry.get("cell"),
            "membership_set": entry.get("membership_set"),
            "capacity_source": entry.get("capacity_source"),
            "actual_exposure": actual,
            "entry_quote_seq": entry_quote.seq,
            "state_quote_seq": current_quote.seq,
            "entry_mid_quote": entry_quote.mid,
            "state_mid_quote": current_quote.mid,
            "state_bid": current_quote.bid,
            "state_ask": current_quote.ask,
            "state_spread_bps": current_quote.spread_bps,
            "entry_cross_bps": current_dec["entry_cross_bps"],
            "signal_entry_mid": signal_mid,
            "signal_entry_execution_cost_bps": signal_entry_cost,
            "stored_admission_entry_cross_bps": stored_entry_cross,
            "signal_entry_basis_bps": signal_basis,
            "current_mid_alpha_bps": current_dec["mid_alpha_bps"],
            "current_taker_net_bps": current_dec["taker_net_bps"],
            "current_exit_cross_bps": current_dec["exit_cross_bps"],
            "current_total_cross_bps": current_dec["total_cross_bps"],
            "running_high_taker_net_bps": running_high,
            "running_low_taker_net_bps": running_low,
            "drawdown_from_high_bps": drawdown,
            "runup_from_low_bps": runup_from_low,
            "mid_alpha_per_sec_bps": current_dec["mid_alpha_bps"] / elapsed_sec if elapsed_sec > EPS else 0.0,
            "recent_mid_alpha_2s_bps": recent_2s,
            "recent_mid_alpha_5s_bps": recent_5s,
            "fixed60_taker_net_bps": fixed60_net,
            "fixed60_delta_from_now_bps": fixed60_net - current_dec["taker_net_bps"],
            "alpha_decay_to_60_bps": current_dec["mid_alpha_bps"] - fixed60_mid_alpha,
            "oracle_best_net_bps": best_dec["taker_net_bps"],
            "oracle_best_exit_sec": (best_quote.local_ts_us - entry_ts) / 1_000_000.0,
            "best_future_net_bps": future_best_dec["taker_net_bps"],
            "best_future_exit_sec": (future_best_quote.local_ts_us - entry_ts) / 1_000_000.0,
            "best_future_net_gain_bps": future_best_dec["taker_net_bps"] - current_dec["taker_net_bps"],
            "spread_blocked_exit": current_dec["mid_alpha_bps"] > 0.0 and current_dec["taker_net_bps"] < 0.0,
            "l2_state_available": False,
        }
        for key, value in trade_all.items():
            row[key] = value
        for key, value in trade_5s.items():
            row[f"recent5s_{key}"] = value
        states.append(row)

    oracle_row = {
        "date": day,
        "shadow_position_id": position_id,
        "entry_ts_us": entry_ts,
        "side": side,
        "direction": direction,
        "cell": entry.get("cell"),
        "membership_set": entry.get("membership_set"),
        "capacity_source": entry.get("capacity_source"),
        "actual_exposure": actual,
        "entry_cross_bps": fixed60_dec["entry_cross_bps"],
        "signal_entry_mid": signal_mid,
        "signal_entry_execution_cost_bps": signal_entry_cost,
        "stored_admission_entry_cross_bps": stored_entry_cross,
        "signal_entry_basis_bps": signal_basis,
        "net_60_bps": fixed60_net,
        "mid_alpha_60_bps": fixed60_mid_alpha,
        "exit_cross_60_bps": fixed60_dec["exit_cross_bps"],
        "best_net_bps": best_dec["taker_net_bps"],
        "best_net_sec": (best_quote.local_ts_us - entry_ts) / 1_000_000.0,
        "best_net_mid_alpha_bps": best_dec["mid_alpha_bps"],
        "best_net_exit_cross_bps": best_dec["exit_cross_bps"],
        "oracle_gain_vs_60_bps": best_dec["taker_net_bps"] - fixed60_net,
        "weighted_oracle_gain_vs_60_bps": actual * (best_dec["taker_net_bps"] - fixed60_net),
        "best_mid_alpha_bps": best_mid_dec["mid_alpha_bps"],
        "best_mid_sec": (best_mid_quote.local_ts_us - entry_ts) / 1_000_000.0,
        "best_mid_taker_net_bps": best_mid_dec["taker_net_bps"],
        "best_mid_exit_cross_bps": best_mid_dec["exit_cross_bps"],
        "mid_decay_best_to_60_bps": best_mid_dec["mid_alpha_bps"] - fixed60_mid_alpha,
        "taker_loss_best_mid_to_best_net_bps": best_dec["taker_net_bps"] - best_mid_dec["taker_net_bps"],
        "alpha_positive_but_taker_negative_60": fixed60_mid_alpha > 0.0 and fixed60_net < 0.0,
        "exit_cross_60_gt_mid_alpha_60": fixed60_dec["exit_cross_bps"] > fixed60_mid_alpha,
    }
    return states, oracle_row


def summarize_oracle(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exposure = sum(numeric(row["actual_exposure"]) for row in rows)
    oracle_gain = sum(numeric(row["weighted_oracle_gain_vs_60_bps"]) for row in rows)
    alpha_positive_taker_negative = [
        row for row in rows if bool(row["alpha_positive_but_taker_negative_60"])
    ]
    exit_cross_gt_alpha = [row for row in rows if bool(row["exit_cross_60_gt_mid_alpha_60"])]
    return {
        "entries": len(rows),
        "actual_exposure": exposure,
        "weighted_fixed60_taker_net_bps": weighted_sum(rows, "net_60_bps"),
        "weighted_oracle_best_net_bps": weighted_sum(rows, "best_net_bps"),
        "weighted_oracle_gain_vs_60_bps": oracle_gain,
        "gain_per_exposure_bps": oracle_gain / exposure if exposure > EPS else math.nan,
        "median_best_net_sec": quantile([numeric(row["best_net_sec"]) for row in rows], 0.50),
        "p25_best_net_sec": quantile([numeric(row["best_net_sec"]) for row in rows], 0.25),
        "p75_best_net_sec": quantile([numeric(row["best_net_sec"]) for row in rows], 0.75),
        "median_best_mid_sec": quantile([numeric(row["best_mid_sec"]) for row in rows], 0.50),
        "weighted_mid_decay_best_to_60_bps": weighted_sum(rows, "mid_decay_best_to_60_bps"),
        "alpha_positive_but_taker_negative_60_count": len(alpha_positive_taker_negative),
        "alpha_positive_but_taker_negative_60_exposure": sum(
            numeric(row["actual_exposure"]) for row in alpha_positive_taker_negative
        ),
        "exit_cross_60_gt_mid_alpha_60_count": len(exit_cross_gt_alpha),
        "exit_cross_60_gt_mid_alpha_60_exposure": sum(
            numeric(row["actual_exposure"]) for row in exit_cross_gt_alpha
        ),
    }


def summarize_oracle_groups(rows: list[dict[str, Any]], group_fields: list[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in group_fields)
        groups.setdefault(key, []).append(row)
    out: list[dict[str, Any]] = []
    for key, group in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
        item = {field: value for field, value in zip(group_fields, key)}
        item.update(summarize_oracle(group))
        out.append(item)
    return out


def panel_by_position(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(entry_id(row), []).append(row)
    for group in out.values():
        group.sort(key=lambda row: numeric(row["target_horizon_sec"]))
    return out


def split_runtime_state_and_labels(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runtime_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []
    for row in rows:
        runtime_rows.append({key: value for key, value in row.items() if key not in OFFLINE_LABEL_COLUMNS})
        label_rows.append(
            {
                key: value
                for key, value in row.items()
                if key in PANEL_KEY_COLUMNS or key in OFFLINE_LABEL_COLUMNS
            }
        )
    return runtime_rows, label_rows


def rule_triggers(row: dict[str, Any], params: dict[str, float]) -> bool:
    high = numeric(row["running_high_taker_net_bps"])
    drawdown = numeric(row["drawdown_from_high_bps"])
    exit_cross = numeric(row["current_exit_cross_bps"])
    recent_5s = numeric(row["recent_mid_alpha_5s_bps"])
    if (
        high >= params["h"]
        and drawdown >= max(params["d0"], params["rho"] * max(high, 0.0))
        and exit_cross <= params["q_exit"]
    ):
        return True
    emergency_decay = params.get("emergency_decay", 999.0)
    if emergency_decay < 900.0:
        return (
            high >= params["h"]
            and drawdown >= params["emergency_d"]
            and recent_5s <= -emergency_decay
            and exit_cross <= params["q_exit"] + params["q_emergency_add"]
        )
    return False


def evaluate_stopping_rule(
    by_pos: dict[int, list[dict[str, Any]]],
    *,
    params: dict[str, float] | None,
    days: set[str] | None = None,
    name: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for group in by_pos.values():
        if not group:
            continue
        day = str(group[0]["date"])
        if days is not None and day not in days:
            continue
        fixed = max(group, key=lambda row: numeric(row["target_horizon_sec"]))
        chosen = fixed
        reason = "fixed60"
        if params is not None:
            for row in group:
                if numeric(row["target_horizon_sec"]) >= 60.0:
                    break
                if rule_triggers(row, params):
                    chosen = row
                    reason = "stopping_rule"
                    break
        actual = numeric(chosen["actual_exposure"])
        net = numeric(chosen["current_taker_net_bps"])
        fixed_net = numeric(fixed["current_taker_net_bps"])
        oracle = numeric(chosen["oracle_best_net_bps"])
        rows.append(
            {
                "date": day,
                "shadow_position_id": chosen["shadow_position_id"],
                "exit_reason": reason,
                "exit_sec": chosen["target_horizon_sec"],
                "actual_exposure": actual,
                "net_bps": net,
                "fixed60_net_bps": fixed_net,
                "oracle_best_net_bps": oracle,
                "weighted_net_bps": actual * net,
                "weighted_fixed60_net_bps": actual * fixed_net,
                "weighted_oracle_best_net_bps": actual * oracle,
                "weighted_saved_vs_60_bps": actual * max(0.0, net - fixed_net),
                "weighted_overcut_vs_60_bps": actual * max(0.0, fixed_net - net),
                "weighted_missed_vs_oracle_bps": actual * max(0.0, oracle - net),
                "exit_cross_bps": chosen["current_exit_cross_bps"],
                "spread_bps": chosen["state_spread_bps"],
            }
        )
    total = sum(numeric(row["weighted_net_bps"]) for row in rows)
    fixed_total = sum(numeric(row["weighted_fixed60_net_bps"]) for row in rows)
    oracle_total = sum(numeric(row["weighted_oracle_best_net_bps"]) for row in rows)
    day_totals: dict[str, float] = {}
    for row in rows:
        day_totals[str(row["date"])] = day_totals.get(str(row["date"]), 0.0) + numeric(
            row["weighted_net_bps"]
        )
    capture_den = oracle_total - fixed_total
    return {
        "name": name,
        "entries": len(rows),
        "actual_exposure": sum(numeric(row["actual_exposure"]) for row in rows),
        "weighted_net_bps": total,
        "weighted_fixed60_net_bps": fixed_total,
        "weighted_oracle_best_net_bps": oracle_total,
        "delta_vs_fixed60_bps": total - fixed_total,
        "oracle_gap_bps": oracle_total - total,
        "oracle_capture_ratio_vs_fixed60": (
            (total - fixed_total) / capture_den if abs(capture_den) > EPS else math.nan
        ),
        "triggered_exits": sum(1 for row in rows if row["exit_reason"] == "stopping_rule"),
        "avg_exit_sec": (
            sum(numeric(row["exit_sec"]) for row in rows) / len(rows) if rows else math.nan
        ),
        "weighted_saved_vs_60_bps": sum(numeric(row["weighted_saved_vs_60_bps"]) for row in rows),
        "weighted_overcut_vs_60_bps": sum(
            numeric(row["weighted_overcut_vs_60_bps"]) for row in rows
        ),
        "weighted_missed_vs_oracle_bps": sum(
            numeric(row["weighted_missed_vs_oracle_bps"]) for row in rows
        ),
        "mean_exit_cross_bps": (
            sum(numeric(row["exit_cross_bps"]) for row in rows) / len(rows) if rows else math.nan
        ),
        "worst_day_net_bps": min(day_totals.values()) if day_totals else math.nan,
        "positive_days": sum(1 for value in day_totals.values() if value > 0.0),
        "days": len(day_totals),
        "params_json": json.dumps(params, sort_keys=True) if params is not None else "{}",
    }


def candidate_params() -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for h in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]:
        for d0 in [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]:
            for rho in [0.25, 0.35, 0.50, 0.65]:
                for q_exit in [0.75, 1.0, 1.25, 1.5, 2.0]:
                    for emergency_decay in [999.0, 4.0, 6.0, 8.0]:
                        out.append(
                            {
                                "h": h,
                                "d0": d0,
                                "rho": rho,
                                "q_exit": q_exit,
                                "emergency_decay": emergency_decay,
                                "emergency_d": max(2.0 * d0, 6.0),
                                "q_emergency_add": 0.75,
                            }
                        )
    return out


def walk_forward_search(panel_rows: list[dict[str, Any]], days: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_pos = panel_by_position(panel_rows)
    candidates = candidate_params()
    folds: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    for idx, test_day in enumerate(days):
        train_days = set(days[:idx])
        if not train_days:
            continue
        test_days = {test_day}
        scored: list[tuple[tuple[float, float, float], dict[str, Any], dict[str, float]]] = []
        for params in candidates:
            train = evaluate_stopping_rule(by_pos, params=params, days=train_days, name="candidate_train")
            score = (
                numeric(train["weighted_net_bps"]),
                numeric(train["worst_day_net_bps"]),
                -numeric(train["triggered_exits"]),
            )
            scored.append((score, train, params))
        scored.sort(key=lambda item: item[0], reverse=True)
        best_train = scored[0][1]
        best_params = scored[0][2]
        for rank, (_, train, params) in enumerate(scored[:20], start=1):
            row = dict(train)
            row["rank"] = rank
            row["test_day"] = test_day
            row["train_days"] = ",".join(sorted(train_days))
            row["params_json"] = json.dumps(params, sort_keys=True)
            top_rows.append(row)
        test = evaluate_stopping_rule(by_pos, params=best_params, days=test_days, name="wf_stopping_rule_v1")
        fixed = evaluate_stopping_rule(by_pos, params=None, days=test_days, name="fixed60_panel_baseline")
        fold = {
            "fold": len(folds) + 1,
            "train_days": ",".join(sorted(train_days)),
            "test_day": test_day,
            "selected_params_json": json.dumps(best_params, sort_keys=True),
            "train_weighted_net_bps": best_train["weighted_net_bps"],
            "train_delta_vs_fixed60_bps": best_train["delta_vs_fixed60_bps"],
            "train_capture_ratio": best_train["oracle_capture_ratio_vs_fixed60"],
            "test_weighted_net_bps": test["weighted_net_bps"],
            "test_fixed60_net_bps": fixed["weighted_net_bps"],
            "test_oracle_best_net_bps": fixed["weighted_oracle_best_net_bps"],
            "test_entries": test["entries"],
            "test_actual_exposure": test["actual_exposure"],
            "test_delta_vs_fixed60_bps": test["delta_vs_fixed60_bps"],
            "test_oracle_gap_bps": test["oracle_gap_bps"],
            "test_capture_ratio": test["oracle_capture_ratio_vs_fixed60"],
            "test_triggered_exits": test["triggered_exits"],
            "test_avg_exit_sec": test["avg_exit_sec"],
            "test_worst_day_net_bps": test["worst_day_net_bps"],
            "test_weighted_saved_vs_60_bps": test["weighted_saved_vs_60_bps"],
            "test_weighted_overcut_vs_60_bps": test["weighted_overcut_vs_60_bps"],
            "test_weighted_missed_vs_oracle_bps": test["weighted_missed_vs_oracle_bps"],
            "test_mean_exit_cross_bps": test["mean_exit_cross_bps"],
        }
        folds.append(fold)
    return folds, top_rows


def params_by_date_from_folds(folds: list[dict[str, Any]]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for fold in folds:
        raw = fold.get("selected_params_json")
        if not raw:
            continue
        params[str(fold["test_day"])] = json.loads(str(raw))
    return {
        "schema_id": "ccusdt_stopping_rule_params_by_date_v1",
        "exit_profile": "stopping_rule_v1",
        "training_protocol": "walk_forward_prior_dates_only",
        "fallback_for_missing_date": "fixed60_taker",
        "params_by_date": params,
    }

def load_entries(repo_root: Path, fast_run_id: str, from_date: str, to_date: str, actual_only: bool) -> list[dict[str, Any]]:
    path = repo_root / EXPERIMENT_ROOT / fast_run_id / "entries.parquet"
    table = pq.read_table(path)
    df = table.to_pandas()
    mask = (df["date"] >= from_date) & (df["date"] <= to_date)
    if actual_only:
        mask = mask & (df["actual_exposure"] > EPS)
    df = df[mask].copy()
    return df.to_dict("records")


def load_exit_compare(repo_root: Path, fixed_run_id: str, fast_run_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label, run_id in [("fixed60_taker", fixed_run_id), ("peakguard_taker_v1", fast_run_id)]:
        path = repo_root / EXPERIMENT_ROOT / run_id / "exits.parquet"
        df = pq.read_table(path).to_pandas()
        traded = df[df["actual_exposure"] > EPS]
        exposure = float(traded["actual_exposure"].sum())
        out.append(
            {
                "fast_exit_profile": label,
                "entries": int(len(df)),
                "traded_entries": int(len(traded)),
                "actual_exposure": exposure,
                "fast_weighted_taker_net_bps": float(traded["net_weighted_bps"].sum()),
                "fast_weighted_mid_fixed60_bps": float((traded["actual_exposure"] * traded["raw_bps_mid_fixed60"]).sum()),
                "release_drawdown_exits": int((traded["exit_reason"] == "release_drawdown").sum()),
                "fixed_60s_exits": int((traded["exit_reason"] == "fixed_60s").sum()),
                "zero_actual_rows": int((df["actual_exposure"] <= EPS).sum()),
            }
        )
    return out


def strict_rows(path: Path, profile: str = "idle01_g1") -> list[dict[str, Any]]:
    rows = [row for row in read_csv_rows(path) if row.get("profile") == profile]
    return rows


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = args.out_dir if args.out_dir.is_absolute() else repo_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    horizons = [float(item.strip()) for item in args.horizons_sec.split(",") if item.strip()]
    days = date_range(args.from_date, args.to_date)
    quotes = {day: QuoteIndex.load(repo_root, args.symbol, day) for day in days}
    trades = {day: TradeIndex.load(repo_root, args.symbol, day) for day in days}
    entries = load_entries(repo_root, args.fast_run_id, args.from_date, args.to_date, args.actual_only)

    stopping_panel_rows: list[dict[str, Any]] = []
    oracle_rows: list[dict[str, Any]] = []
    for entry in entries:
        day = str(entry["date"])
        states, oracle = build_previsible_rows_for_entry(
            entry=entry,
            quote_index=quotes[day],
            trade_index=trades[day],
            horizons=horizons,
            oracle_max_sec=args.oracle_max_sec,
            min_oracle_sec=args.min_oracle_sec,
        )
        stopping_panel_rows.extend(states)
        oracle_rows.append(oracle)

    horizon_summary: list[dict[str, Any]] = []
    for horizon in horizons:
        rows = [
            {
                **row,
                "horizon_sec": row["target_horizon_sec"],
                "mid_alpha_bps": row["current_mid_alpha_bps"],
                "exit_cross_bps": row["current_exit_cross_bps"],
                "total_cross_bps": row["current_total_cross_bps"],
                "taker_net_bps": row["current_taker_net_bps"],
            }
            for row in stopping_panel_rows
            if abs(numeric(row["target_horizon_sec"]) - horizon) < 1e-9
        ]
        horizon_summary.append(summarize_group(rows, key_fields={"horizon_sec": horizon}))

    daily_horizon_summary: list[dict[str, Any]] = []
    for day in days:
        for horizon in horizons:
            rows = [
                {
                    **row,
                    "horizon_sec": row["target_horizon_sec"],
                    "mid_alpha_bps": row["current_mid_alpha_bps"],
                    "exit_cross_bps": row["current_exit_cross_bps"],
                    "total_cross_bps": row["current_total_cross_bps"],
                    "taker_net_bps": row["current_taker_net_bps"],
                }
                for row in stopping_panel_rows
                if row["date"] == day and abs(numeric(row["target_horizon_sec"]) - horizon) < 1e-9
            ]
            daily_horizon_summary.append(summarize_group(rows, key_fields={"date": day, "horizon_sec": horizon}))

    by_cell_horizon_summary: list[dict[str, Any]] = []
    cells = sorted({str(row["cell"]) for row in stopping_panel_rows})
    for cell in cells:
        for horizon in horizons:
            rows = [
                {
                    **row,
                    "horizon_sec": row["target_horizon_sec"],
                    "mid_alpha_bps": row["current_mid_alpha_bps"],
                    "exit_cross_bps": row["current_exit_cross_bps"],
                    "total_cross_bps": row["current_total_cross_bps"],
                    "taker_net_bps": row["current_taker_net_bps"],
                }
                for row in stopping_panel_rows
                if str(row["cell"]) == cell and abs(numeric(row["target_horizon_sec"]) - horizon) < 1e-9
            ]
            by_cell_horizon_summary.append(
                summarize_group(rows, key_fields={"cell": cell, "horizon_sec": horizon})
            )

    oracle_summary = summarize_oracle(oracle_rows)
    label_summary_by_day = summarize_oracle_groups(oracle_rows, ["date"])
    label_summary_by_cell = summarize_oracle_groups(oracle_rows, ["cell"])
    label_summary_by_day_cell = summarize_oracle_groups(oracle_rows, ["date", "cell"])
    wf_folds, wf_top = walk_forward_search(stopping_panel_rows, days)
    stopping_params_by_date = params_by_date_from_folds(wf_folds)
    by_pos = panel_by_position(stopping_panel_rows)
    panel_fixed_compare = evaluate_stopping_rule(by_pos, params=None, days=None, name="fixed60_panel_baseline")
    if wf_folds:
        wf_total = {
            "name": "wf_stopping_rule_v1_oos_folds_only",
            "entries": sum(numeric(fold["test_entries"]) for fold in wf_folds),
            "actual_exposure": sum(numeric(fold["test_actual_exposure"]) for fold in wf_folds),
            "weighted_net_bps": sum(numeric(fold["test_weighted_net_bps"]) for fold in wf_folds),
            "weighted_fixed60_net_bps": sum(numeric(fold["test_fixed60_net_bps"]) for fold in wf_folds),
            "weighted_oracle_best_net_bps": sum(numeric(fold["test_oracle_best_net_bps"]) for fold in wf_folds),
            "delta_vs_fixed60_bps": sum(numeric(fold["test_delta_vs_fixed60_bps"]) for fold in wf_folds),
            "oracle_gap_bps": sum(numeric(fold["test_oracle_gap_bps"]) for fold in wf_folds),
            "triggered_exits": sum(numeric(fold["test_triggered_exits"]) for fold in wf_folds),
            "weighted_saved_vs_60_bps": sum(
                numeric(fold["test_weighted_saved_vs_60_bps"]) for fold in wf_folds
            ),
            "weighted_overcut_vs_60_bps": sum(
                numeric(fold["test_weighted_overcut_vs_60_bps"]) for fold in wf_folds
            ),
            "weighted_missed_vs_oracle_bps": sum(
                numeric(fold["test_weighted_missed_vs_oracle_bps"]) for fold in wf_folds
            ),
            "avg_exit_sec": (
                sum(numeric(fold["test_avg_exit_sec"]) * numeric(fold["test_entries"]) for fold in wf_folds)
                / sum(numeric(fold["test_entries"]) for fold in wf_folds)
            ),
            "mean_exit_cross_bps": (
                sum(numeric(fold["test_mean_exit_cross_bps"]) * numeric(fold["test_entries"]) for fold in wf_folds)
                / sum(numeric(fold["test_entries"]) for fold in wf_folds)
            ),
            "worst_day_net_bps": min(numeric(fold["test_worst_day_net_bps"]) for fold in wf_folds),
            "positive_days": sum(1 for fold in wf_folds if numeric(fold["test_worst_day_net_bps"]) > 0.0),
            "days": len(wf_folds),
        }
        den = wf_total["weighted_oracle_best_net_bps"] - wf_total["weighted_fixed60_net_bps"]
        wf_total["oracle_capture_ratio_vs_fixed60"] = (
            wf_total["delta_vs_fixed60_bps"] / den if abs(den) > EPS else math.nan
        )
    else:
        wf_total = {"name": "wf_stopping_rule_v1_oos_folds_only", "entries": 0}
    rule_compare = [panel_fixed_compare, wf_total]
    runtime_state_rows, stopping_label_rows = split_runtime_state_and_labels(stopping_panel_rows)

    exit_compare = load_exit_compare(repo_root, args.fixed_run_id, args.fast_run_id)
    strict_compare = strict_rows(
        args.strict_totals_csv if args.strict_totals_csv.is_absolute() else repo_root / args.strict_totals_csv
    )

    write_csv(out_dir / "horizon_surface.csv", horizon_summary)
    write_csv(out_dir / "daily_horizon_surface.csv", daily_horizon_summary)
    write_csv(out_dir / "cell_horizon_surface.csv", by_cell_horizon_summary)
    write_csv(out_dir / "oracle_stopping_entries.csv", oracle_rows)
    write_csv(out_dir / "label_summary_by_day.csv", label_summary_by_day)
    write_csv(out_dir / "label_summary_by_cell.csv", label_summary_by_cell)
    write_csv(out_dir / "label_summary_by_day_cell.csv", label_summary_by_day_cell)
    write_csv(out_dir / "walk_forward_thresholds.csv", wf_folds)
    write_csv(out_dir / "walk_forward_train_top20.csv", wf_top)
    write_csv(out_dir / "stopping_rule_compare.csv", rule_compare)
    write_csv(out_dir / "stopping_labels.csv", stopping_label_rows)
    write_csv(out_dir / "exit_profile_compare_fast.csv", exit_compare)
    write_csv(out_dir / "strict_profile_totals.csv", strict_compare)
    pq.write_table(pa.Table.from_pylist(runtime_state_rows), out_dir / "stopping_panel.parquet")
    pq.write_table(pa.Table.from_pylist(stopping_label_rows), out_dir / "stopping_labels.parquet")
    pq.write_table(pa.Table.from_pylist(oracle_rows), out_dir / "oracle_stopping_entries.parquet")
    with (out_dir / "label_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "overall": oracle_summary,
                "by_day": label_summary_by_day,
                "by_cell": label_summary_by_cell,
                "by_day_cell": label_summary_by_day_cell,
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    with (out_dir / "stopping_rule_params_by_date.json").open("w", encoding="utf-8") as handle:
        json.dump(stopping_params_by_date, handle, indent=2, sort_keys=True)
        handle.write("\n")

    best_horizon = max(horizon_summary, key=lambda row: numeric(row["weighted_taker_net_bps"]))
    horizon_60 = next(row for row in horizon_summary if abs(numeric(row["horizon_sec"]) - 60.0) < 1e-9)
    summary = {
        "schema_id": "ccusdt_taker_exit_stopping_diagnostic_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "fast_run_id": args.fast_run_id,
        "fixed_run_id": args.fixed_run_id,
        "scope": "actual_exposure_only" if args.actual_only else "all_entries",
        "identity": "taker_net(t)=mid_alpha(t)-entry_cross-exit_cross(t)",
        "horizons_sec": horizons,
        "best_fixed_horizon_by_weighted_taker_net": best_horizon,
        "horizon_60": horizon_60,
        "oracle_summary": oracle_summary,
        "walk_forward_summary": wf_total,
        "rule_compare": rule_compare,
        "exit_profile_compare_fast": exit_compare,
        "strict_profile_totals": strict_compare,
        "outputs": {
            "stopping_panel_parquet": str(out_dir / "stopping_panel.parquet"),
            "stopping_labels_parquet": str(out_dir / "stopping_labels.parquet"),
            "stopping_labels_csv": str(out_dir / "stopping_labels.csv"),
            "label_summary_json": str(out_dir / "label_summary.json"),
            "label_summary_by_day_csv": str(out_dir / "label_summary_by_day.csv"),
            "label_summary_by_cell_csv": str(out_dir / "label_summary_by_cell.csv"),
            "label_summary_by_day_cell_csv": str(out_dir / "label_summary_by_day_cell.csv"),
            "walk_forward_thresholds_csv": str(out_dir / "walk_forward_thresholds.csv"),
            "walk_forward_train_top20_csv": str(out_dir / "walk_forward_train_top20.csv"),
            "stopping_rule_compare_csv": str(out_dir / "stopping_rule_compare.csv"),
            "stopping_rule_params_by_date_json": str(out_dir / "stopping_rule_params_by_date.json"),
            "horizon_surface_csv": str(out_dir / "horizon_surface.csv"),
            "daily_horizon_surface_csv": str(out_dir / "daily_horizon_surface.csv"),
            "cell_horizon_surface_csv": str(out_dir / "cell_horizon_surface.csv"),
            "oracle_stopping_entries_csv": str(out_dir / "oracle_stopping_entries.csv"),
            "oracle_stopping_entries_parquet": str(out_dir / "oracle_stopping_entries.parquet"),
            "exit_profile_compare_fast_csv": str(out_dir / "exit_profile_compare_fast.csv"),
            "strict_profile_totals_csv": str(out_dir / "strict_profile_totals.csv"),
        },
        "runtime_safety_note": (
            "This diagnostic uses future path observations as offline labels. "
            "stopping_panel.parquet contains only runtime-safe state fields. stopping_labels.parquet "
            "contains fixed60/oracle/future labels and must not be exposed to the Strategy Bot runtime."
        ),
        "runtime_safe_columns": sorted(runtime_state_rows[0].keys()) if runtime_state_rows else [],
        "offline_label_columns": sorted(OFFLINE_LABEL_COLUMNS),
        "strict_stopping_rule_status": (
            "stopping_rule_v1 is evaluated here as a fast/previsible diagnostic only; Bot/Runner "
            "panel_sparse strict implementation is still required before promotion."
        ),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

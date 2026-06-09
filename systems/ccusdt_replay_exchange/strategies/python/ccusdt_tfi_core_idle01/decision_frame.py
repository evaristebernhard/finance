"""Runtime-safe decision_frame_v1 builder for the CCUSDT strategy bot.

The old research strategy evaluated on the fixed L2 event-panel clock, not on
every quote or trade. This module reconstructs that panel-equivalent clock from
exchange-visible L2 updates plus trades. It does not read legacy panels,
research labels, scored entries, or PnL files.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from typing import Any, Iterable


EPS = 1e-12
PRICE_SCALE = 1_000_000_000.0
US_PER_SECOND = 1_000_000
BUILDER_VERSION = "decision_frame_builder_v1.1_market_derived_cache"

CACHE_FIELDS = [
    "schema_id",
    "runtime_safe",
    "observed_seq",
    "exchange_ts_us",
    "local_ts_us",
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
    "mid",
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


@dataclass
class DecisionTrade:
    local_ts_us: int
    side: str
    price: float
    qty: float


class DecisionL2Book:
    def __init__(self) -> None:
        self.bids: dict[int, float] = {}
        self.asks: dict[int, float] = {}

    @staticmethod
    def price_key(price: float) -> int:
        return int(round(float(price) * PRICE_SCALE))

    @staticmethod
    def key_price(key: int) -> float:
        return float(key) / PRICE_SCALE

    def clear(self) -> None:
        self.bids.clear()
        self.asks.clear()

    def set_level(self, side: str, price: float, qty: float) -> None:
        key = self.price_key(price)
        levels = self.bids if side == "buy" else self.asks
        if qty <= 0.0:
            levels.pop(key, None)
        else:
            levels[key] = float(qty)

    def replace_from_snapshot(self, updates: Iterable[dict[str, Any]]) -> None:
        self.clear()
        for update in updates:
            self.set_level(
                normalize_side(update.get("side")),
                float(update.get("price") or 0.0),
                float(update.get("qty") or update.get("amount") or 0.0),
            )

    def cleanup_crossed(self, updated_side: str) -> int:
        removed = 0
        while self.bids and self.asks:
            best_bid = max(self.bids)
            best_ask = min(self.asks)
            if best_bid < best_ask:
                break
            if updated_side == "buy":
                self.asks.pop(best_ask, None)
            else:
                self.bids.pop(best_bid, None)
            removed += 1
        return removed

    def top(self) -> tuple[float | None, float | None, float | None, float | None]:
        bid_key = max(self.bids) if self.bids else None
        ask_key = min(self.asks) if self.asks else None
        bid = self.key_price(bid_key) if bid_key is not None else None
        ask = self.key_price(ask_key) if ask_key is not None else None
        bid_qty = self.bids.get(bid_key) if bid_key is not None else None
        ask_qty = self.asks.get(ask_key) if ask_key is not None else None
        return bid, bid_qty, ask, ask_qty

    def is_crossed(self) -> bool:
        return bool(self.bids and self.asks and max(self.bids) >= min(self.asks))


class DecisionFrameBuilder:
    """Build fixed-panel-equivalent frames from public stream events."""

    def __init__(
        self,
        *,
        trade_window_us: int = 2_000_000,
        bucket_us: int = 60_000_000,
    ) -> None:
        self.trade_window_us = int(trade_window_us)
        self.bucket_us = int(bucket_us)
        self.book = DecisionL2Book()
        self.trades: collections.deque[DecisionTrade] = collections.deque()
        self.seen_snapshot = False
        self.event_index = 0
        self.day_start_ts_us: int | None = None
        self.previous_mid: float | None = None
        self.previous_bid: float | None = None
        self.previous_ask: float | None = None
        self.previous_bid_qty: float | None = None
        self.previous_ask_qty: float | None = None
        self.last_mid_change_index: int | None = None
        self.mid_history: collections.deque[float] = collections.deque(maxlen=25)

    def observe_trade(self, trade: dict[str, Any], fallback_local_ts_us: int | None = None) -> None:
        local_ts_us = int(trade.get("local_ts_us") or fallback_local_ts_us or 0)
        side = normalize_side(trade.get("side"))
        price = float(trade.get("price") or 0.0)
        qty = max(0.0, float(trade.get("qty") or trade.get("amount") or 0.0))
        self.trades.append(DecisionTrade(local_ts_us, side, price, qty))

    def build_from_l2_payload(
        self,
        payload: dict[str, Any],
        *,
        observed_seq: int | None = None,
        fallback_local_ts_us: int | None = None,
    ) -> dict[str, Any] | None:
        updates = normalize_l2_updates(payload)
        return self.build_from_l2_updates(
            updates,
            observed_seq=observed_seq,
            fallback_local_ts_us=fallback_local_ts_us,
        )

    def build_from_l2_updates(
        self,
        updates: list[dict[str, Any]],
        *,
        observed_seq: int | None = None,
        fallback_local_ts_us: int | None = None,
    ) -> dict[str, Any] | None:
        if not updates:
            return None
        local_ts_us = int(updates[0].get("local_ts_us") or fallback_local_ts_us or 0)
        exchange_ts_us = int(updates[0].get("exchange_ts_us") or local_ts_us)
        snapshot_batch = any(bool(update.get("is_snapshot")) for update in updates)
        if not self.seen_snapshot and not snapshot_batch:
            return None

        before_has_book = bool(self.book.bids and self.book.asks)
        crossed_removed = 0
        if snapshot_batch:
            self.seen_snapshot = True
            self.book.replace_from_snapshot(updates)
        else:
            last_side = normalize_side(updates[0].get("side"))
            for update in updates:
                last_side = normalize_side(update.get("side"))
                self.book.set_level(
                    last_side,
                    float(update.get("price") or 0.0),
                    float(update.get("qty") or update.get("amount") or 0.0),
                )
            crossed_removed = self.book.cleanup_crossed(last_side)

        self.event_index += 1
        if self.day_start_ts_us is None:
            self.day_start_ts_us = local_ts_us

        self._trim_trades(local_ts_us)
        bid, bid_qty, ask, ask_qty = self.book.top()
        mid = (bid + ask) * 0.5 if bid is not None and ask is not None else None
        spread_bps = (
            (ask - bid) / mid * 10_000.0
            if bid is not None and ask is not None and mid is not None and mid > EPS
            else None
        )
        crossed_after_cleanup = self.book.is_crossed()
        factor_eligible = (
            mid is not None
            and not crossed_after_cleanup
            and crossed_removed == 0
            and (not snapshot_batch or before_has_book)
        )
        trade_count, buy_qty, sell_qty, notional = self._trade_window_stats(local_ts_us)
        tfi = (
            (buy_qty - sell_qty) / (buy_qty + sell_qty)
            if buy_qty + sell_qty > EPS
            else None
        )

        mid_change_prev = (
            False
            if self.previous_mid is None or mid is None
            else abs(mid - self.previous_mid) > EPS
        )
        quote_change_prev = (
            False
            if self.previous_bid is None
            or self.previous_ask is None
            or bid is None
            or ask is None
            else abs(bid - self.previous_bid) > EPS or abs(ask - self.previous_ask) > EPS
        )
        top_size_change_prev = (
            False
            if self.previous_bid_qty is None
            or self.previous_ask_qty is None
            or bid_qty is None
            or ask_qty is None
            else abs(bid_qty - self.previous_bid_qty) > EPS
            or abs(ask_qty - self.previous_ask_qty) > EPS
        )
        if mid_change_prev:
            self.last_mid_change_index = self.event_index - 1
        frames_since_mid_change = (
            math.inf
            if self.last_mid_change_index is None
            else float((self.event_index - 1) - self.last_mid_change_index)
        )

        past_event_25_bps = None
        if mid is not None and mid > EPS and len(self.mid_history) >= 25:
            past_mid = self.mid_history[0]
            if past_mid > EPS:
                past_event_25_bps = math.log(mid / past_mid) * 10_000.0
        if mid is not None and mid > EPS:
            self.mid_history.append(mid)

        bucket = (local_ts_us - self.day_start_ts_us) // max(1, self.bucket_us)
        frame = {
            "schema_id": "decision_frame_v1",
            "runtime_safe": True,
            "observed_seq": observed_seq,
            "exchange_ts_us": exchange_ts_us,
            "local_ts_us": local_ts_us,
            "local_timestamp": local_ts_us,
            "event_index": self.event_index,
            "is_snapshot_batch": snapshot_batch,
            "factor_eligible": factor_eligible,
            "batch_rows": len(updates),
            "crossed_levels_removed": crossed_removed,
            "best_bid_price": bid,
            "best_bid_amount": bid_qty,
            "best_ask_price": ask,
            "best_ask_amount": ask_qty,
            "mid_price": mid,
            "mid": mid,
            "spread_bps": spread_bps,
            "bid_levels": len(self.book.bids),
            "ask_levels": len(self.book.asks),
            "trade_window_count": trade_count,
            "trade_buy_amount": buy_qty,
            "trade_sell_amount": sell_qty,
            "trade_notional_quote": notional,
            "trade_flow_imbalance": tfi,
            "mid_change_prev": mid_change_prev,
            "quote_change_prev": quote_change_prev,
            "top_size_change_prev": top_size_change_prev,
            "frames_since_mid_change": frames_since_mid_change,
            "past_event_25_bps": past_event_25_bps,
            "fwd_time_60s_bucket": int(bucket),
        }

        self.previous_mid = mid
        self.previous_bid = bid
        self.previous_ask = ask
        self.previous_bid_qty = bid_qty
        self.previous_ask_qty = ask_qty
        return frame

    def _trim_trades(self, local_ts_us: int) -> None:
        min_ts = local_ts_us - self.trade_window_us
        while self.trades and self.trades[0].local_ts_us < min_ts:
            self.trades.popleft()

    def _trade_window_stats(self, local_ts_us: int) -> tuple[int, float, float, float]:
        count = 0
        buy_qty = 0.0
        sell_qty = 0.0
        notional = 0.0
        for trade in self.trades:
            if trade.local_ts_us > local_ts_us:
                break
            count += 1
            notional += trade.price * trade.qty
            if trade.side == "buy":
                buy_qty += trade.qty
            elif trade.side == "sell":
                sell_qty += trade.qty
        return count, buy_qty, sell_qty, notional


def normalize_side(raw: Any) -> str:
    if raw == 1:
        return "buy"
    if raw == -1:
        return "sell"
    side = str(raw or "").strip().lower()
    if side in {"buy", "bid", "b", "1"}:
        return "buy"
    if side in {"sell", "ask", "a", "-1"}:
        return "sell"
    return side


def normalize_l2_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    updates = payload.get("updates")
    if updates:
        return list(updates)
    compact = payload.get("updates_compact") or []
    out: list[dict[str, Any]] = []
    for item in compact:
        if isinstance(item, dict):
            out.append(item)
            continue
        if not isinstance(item, (list, tuple)) or len(item) < 7:
            continue
        out.append(
            {
                "seq": item[0],
                "exchange_ts_us": item[1],
                "local_ts_us": item[2],
                "is_snapshot": bool(item[3]),
                "side": item[4],
                "price": item[5],
                "qty": item[6],
            }
        )
    return out

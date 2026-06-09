"""Runtime-safe online feature state for the CCUSDT strategy bot.

This module is deliberately self-contained. It consumes only exchange-visible
public/private stream messages and does not read research labels, scored
entries, PnL path files, or root scripts.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from typing import Any


EPS = 1e-9


@dataclass
class RollingTrade:
    local_ts_us: int
    signed_qty: float
    abs_qty: float
    signed_notional: float
    abs_notional: float
    is_buy: bool


class ClosedOutcomeState:
    """Pretrade-safe closed-cycle outcome memory.

    The old four-cell research uses an R5-style state that must only depend on
    entries already closed before the current decision. This class exposes that
    shape without inventing labels: it updates only from private fills that close
    a live bot position.
    """

    def __init__(self, window: int = 5) -> None:
        self.window = max(1, int(window))
        self.outcomes_bps: collections.deque[float] = collections.deque()

    def add(self, pnl_bps: float) -> None:
        if not math.isfinite(pnl_bps):
            return
        self.outcomes_bps.append(float(pnl_bps))
        while len(self.outcomes_bps) > self.window:
            self.outcomes_bps.popleft()

    @property
    def positives(self) -> int:
        return sum(1 for value in self.outcomes_bps if value > 0.0)

    @property
    def negatives(self) -> int:
        return sum(1 for value in self.outcomes_bps if value < 0.0)

    @property
    def positive_bps(self) -> float:
        return sum(value for value in self.outcomes_bps if value > 0.0)

    @property
    def negative_bps(self) -> float:
        return sum(value for value in self.outcomes_bps if value < 0.0)

    @property
    def total(self) -> int:
        return len(self.outcomes_bps)

    @property
    def delta(self) -> int:
        return self.positives - self.negatives

    @property
    def energy(self) -> int:
        return self.positives + self.negatives

    @property
    def ratio(self) -> float | None:
        negative_abs = abs(self.negative_bps)
        if negative_abs <= EPS:
            return None
        return self.positive_bps / negative_abs

    @property
    def z(self) -> float:
        return (self.positive_bps + self.negative_bps) / math.sqrt(
            abs(self.positive_bps) + abs(self.negative_bps) + EPS
        )

    def snapshot(self) -> dict[str, Any]:
        ratio = self.ratio
        ratio_is_infinite = ratio is not None and math.isinf(ratio)
        return {
            "window": self.window,
            "count": self.total,
            "positive": self.positives,
            "negative": self.negatives,
            "positive_bps": self.positive_bps,
            "negative_bps": self.negative_bps,
            "positive_abs_bps": self.positive_bps,
            "negative_abs_bps": abs(self.negative_bps),
            "delta": self.delta,
            "energy": self.energy,
            "r5": None if ratio_is_infinite else ratio,
            "r5_infinite": ratio_is_infinite,
            "r5_ready": self.total >= self.window,
            "r5_gt_1": None if ratio is None else ratio > 1.0,
            "z": self.z,
            "latest_pnl_bps": None if not self.outcomes_bps else self.outcomes_bps[-1],
        }


class OnlineFeatureState:
    def __init__(self, window_us: int, closed_window: int = 5) -> None:
        self.window_us = int(window_us)
        self.trades: collections.deque[RollingTrade] = collections.deque()
        self.signed_qty = 0.0
        self.abs_qty = 0.0
        self.buy_qty = 0.0
        self.sell_qty = 0.0
        self.signed_notional = 0.0
        self.abs_notional = 0.0
        self.buy_count = 0
        self.sell_count = 0

        self.position_qty = 0.0
        self.avg_entry_price: float | None = None
        self.pending_client_order_id: str | None = None
        self.orders_sent = 0
        self.last_order_local_ts_us: int | None = None
        self.last_heartbeat_local_ts_us: int | None = None

        self.last_seq: int | None = None
        self.last_local_ts_us: int | None = None
        self.last_quote_seq: int | None = None
        self.last_mid: float | None = None
        self.last_bid: float | None = None
        self.last_ask: float | None = None
        self.mid_history: collections.deque[float] = collections.deque()
        self.past_event_25_bps: float | None = None
        self.spread_bps = 0.0
        self.mid_change = 0.0
        self.mid_change_bps = 0.0
        self.frames_since_mid_change = 0

        self.l2_batches_seen = 0
        self.last_l2_bid_levels = 0
        self.last_l2_ask_levels = 0
        self.last_l2_best_bid: float | None = None
        self.last_l2_best_ask: float | None = None

        self.closed = ClosedOutcomeState(closed_window)

    def observe_envelope(self, message: dict[str, Any]) -> None:
        if message.get("seq") is not None:
            self.last_seq = int(message["seq"])
        if message.get("local_ts_us") is not None:
            self.last_local_ts_us = int(message["local_ts_us"])
        if message.get("quote_seq") is not None:
            self.last_quote_seq = int(message["quote_seq"])

    def add_trade(self, local_ts_us: int, side: str, qty: float, price: float = 0.0) -> None:
        is_buy = side == "buy"
        signed = qty if is_buy else -qty
        notional = abs(qty * price) if price > 0.0 else 0.0
        signed_notional = notional if is_buy else -notional
        item = RollingTrade(
            local_ts_us=local_ts_us,
            signed_qty=signed,
            abs_qty=abs(qty),
            signed_notional=signed_notional,
            abs_notional=notional,
            is_buy=is_buy,
        )
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
        self.clean_small_flow()

    def clean_small_flow(self) -> None:
        for name in (
            "signed_qty",
            "abs_qty",
            "buy_qty",
            "sell_qty",
            "signed_notional",
            "abs_notional",
        ):
            if abs(getattr(self, name)) <= EPS:
                setattr(self, name, 0.0)

    def tfi(self) -> float:
        if self.abs_qty <= EPS:
            return 0.0
        return self.signed_qty / self.abs_qty

    def notional_imbalance(self) -> float:
        if self.abs_notional <= EPS:
            return 0.0
        return self.signed_notional / self.abs_notional

    def update_quote(self, quote: dict[str, Any]) -> None:
        bid = float(quote.get("bid") or quote.get("bid_px") or 0.0)
        ask = float(quote.get("ask") or quote.get("ask_px") or 0.0)
        mid = float(quote.get("mid") or quote.get("mid_px") or ((bid + ask) * 0.5))
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
        if mid > 0.0:
            self.mid_history.append(mid)
            if len(self.mid_history) > 26:
                self.mid_history.popleft()
            if len(self.mid_history) >= 26:
                past_mid = self.mid_history[0]
                self.past_event_25_bps = (
                    math.log(mid / past_mid) * 10_000.0 if past_mid > 0.0 else None
                )
            else:
                self.past_event_25_bps = None

    def update_l2(self, payload: dict[str, Any]) -> None:
        self.l2_batches_seen += 1
        book = payload.get("book") or {}
        self.last_l2_bid_levels = int(book.get("bid_levels") or self.last_l2_bid_levels)
        self.last_l2_ask_levels = int(book.get("ask_levels") or self.last_l2_ask_levels)
        if book.get("best_bid") is not None:
            self.last_l2_best_bid = float(book["best_bid"])
        if book.get("best_ask") is not None:
            self.last_l2_best_ask = float(book["best_ask"])

    def update_private(self, message_type: str, payload: dict[str, Any]) -> None:
        if message_type == "account_snapshot":
            account = payload.get("account") or {}
            self.position_qty = float(account.get("position_qty") or 0.0)
        elif message_type == "fill":
            self.pending_client_order_id = None
            fill = payload.get("fill") or {}
            self.apply_fill(
                side=str(fill.get("side") or ""),
                qty=float(fill.get("qty") or 0.0),
                price=float(fill.get("price") or 0.0),
            )
        elif message_type == "order_reject":
            self.pending_client_order_id = None

    def apply_fill(self, side: str, qty: float, price: float) -> None:
        if qty <= 0.0 or price <= 0.0:
            return
        signed = qty if side == "buy" else -qty
        old_pos = self.position_qty
        old_avg = self.avg_entry_price

        if abs(old_pos) <= EPS or old_pos * signed > 0.0:
            new_pos = old_pos + signed
            old_notional = abs(old_pos) * (old_avg or price)
            new_notional = old_notional + qty * price
            self.position_qty = new_pos
            self.avg_entry_price = new_notional / abs(new_pos) if abs(new_pos) > EPS else None
            return

        closed_qty = min(abs(old_pos), qty)
        if old_avg is not None and old_avg > 0.0:
            if old_pos > 0.0 and side == "sell":
                self.closed.add(math.log(price / old_avg) * 10_000.0)
            elif old_pos < 0.0 and side == "buy":
                self.closed.add(math.log(old_avg / price) * 10_000.0)

        residual = qty - closed_qty
        if residual <= EPS:
            self.position_qty = old_pos + signed
            if abs(self.position_qty) <= EPS:
                self.position_qty = 0.0
                self.avg_entry_price = None
            return

        self.position_qty = residual if side == "buy" else -residual
        self.avg_entry_price = price

    def feature_reason(self) -> str:
        return (
            f"tfi={self.tfi():.6f} spread_bps={self.spread_bps:.6f} "
            f"mid_change={self.mid_change:.10f} "
            f"frames_since_mid_change={self.frames_since_mid_change} "
            f"trades={len(self.trades)} abs_qty={self.abs_qty:.6f} "
            f"trade_imbalance={self.tfi():.6f} l2_batches={self.l2_batches_seen}"
        )

    def snapshot(
        self,
        observed_seq: int | None,
        local_ts_us: int | None,
        checkpoint: str,
    ) -> dict[str, Any]:
        closed = self.closed.snapshot()
        return {
            "schema_id": "ccusdt_online_feature_snapshot_v1",
            "runtime_safe": True,
            "checkpoint": checkpoint,
            "observed_seq": observed_seq,
            "local_ts_us": local_ts_us,
            "window_us": self.window_us,
            "quote": {
                "quote_seq": self.last_quote_seq,
                "bid": self.last_bid,
                "ask": self.last_ask,
                "mid": self.last_mid,
                "spread_bps": self.spread_bps,
                "mid_change": self.mid_change,
                "mid_change_bps": self.mid_change_bps,
                "frames_since_mid_change": self.frames_since_mid_change,
                "past_event_25_bps": self.past_event_25_bps,
            },
            "trade_flow": {
                "rolling_trades": len(self.trades),
                "buy_count": self.buy_count,
                "sell_count": self.sell_count,
                "buy_qty": self.buy_qty,
                "sell_qty": self.sell_qty,
                "signed_qty": self.signed_qty,
                "abs_qty": self.abs_qty,
                "tfi": self.tfi(),
                "signed_notional": self.signed_notional,
                "abs_notional": self.abs_notional,
                "notional_imbalance": self.notional_imbalance(),
            },
            "l2": {
                "batches_seen": self.l2_batches_seen,
                "bid_levels": self.last_l2_bid_levels,
                "ask_levels": self.last_l2_ask_levels,
                "best_bid": self.last_l2_best_bid,
                "best_ask": self.last_l2_best_ask,
            },
            "closed_outcomes": closed,
            "four_cell_inputs": {
                "a_r5_gt_1": closed["r5_gt_1"],
                "r5": closed["r5"],
                "r5_ready": closed["r5_ready"],
                "b_frames_since_mid_change": self.frames_since_mid_change,
                "b_threshold": None,
                "b_frames_ge_threshold": None,
            },
            "private_state": {
                "position_qty": self.position_qty,
                "avg_entry_price": self.avg_entry_price,
                "pending_client_order_id": self.pending_client_order_id,
                "orders_sent": self.orders_sent,
            },
        }


# Backward-compatible name used by existing diagnostics and scripts.
OnlineTfiState = OnlineFeatureState

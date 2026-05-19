"""Online TFI skeleton for the CCUSDT replay exchange stream.

The strategy intentionally reads only stdin NDJSON exchange-style events. It
does not import research scripts and does not read scored entries or labels.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from dataclasses import dataclass


@dataclass
class RollingTrade:
    local_ts_us: int
    signed_qty: float
    abs_qty: float


class OnlineTfiState:
    def __init__(self, window_us: int) -> None:
        self.window_us = window_us
        self.trades: collections.deque[RollingTrade] = collections.deque()
        self.signed_qty = 0.0
        self.abs_qty = 0.0
        self.position_qty = 0.0
        self.pending_client_order_id: str | None = None
        self.orders_sent = 0
        self.last_order_local_ts_us: int | None = None

    def add_trade(self, local_ts_us: int, side: str, qty: float) -> None:
        signed = qty if side == "buy" else -qty
        item = RollingTrade(local_ts_us=local_ts_us, signed_qty=signed, abs_qty=abs(qty))
        self.trades.append(item)
        self.signed_qty += item.signed_qty
        self.abs_qty += item.abs_qty
        self.trim(local_ts_us)

    def trim(self, local_ts_us: int) -> None:
        min_ts = local_ts_us - self.window_us
        while self.trades and self.trades[0].local_ts_us < min_ts:
            old = self.trades.popleft()
            self.signed_qty -= old.signed_qty
            self.abs_qty -= old.abs_qty

    def tfi(self) -> float:
        if self.abs_qty <= 0.0:
            return 0.0
        return self.signed_qty / self.abs_qty

    def update_private(self, message_type: str, payload: dict) -> None:
        if message_type == "account_snapshot":
            account = payload.get("account") or {}
            self.position_qty = float(account.get("position_qty") or 0.0)
        elif message_type == "fill":
            self.pending_client_order_id = None
            fill = payload.get("fill") or {}
            side = fill.get("side")
            qty = float(fill.get("qty") or 0.0)
            if side == "buy":
                self.position_qty += qty
            elif side == "sell":
                self.position_qty -= qty
        elif message_type == "order_reject":
            self.pending_client_order_id = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qty", type=float, default=10.0)
    parser.add_argument("--window-us", type=int, default=5_000_000)
    parser.add_argument("--tfi-threshold", type=float, default=0.8)
    parser.add_argument("--min-trades", type=int, default=3)
    parser.add_argument("--min-qty", type=float, default=0.0)
    parser.add_argument("--cooldown-us", type=int, default=30_000_000)
    parser.add_argument("--max-orders", type=int, default=1)
    return parser.parse_args()


def heartbeat(observed_seq: int | None, reason: str = "heartbeat") -> dict:
    out: dict = {"type": "heartbeat", "reason": reason}
    if observed_seq is not None:
        out["observed_seq"] = observed_seq
    return out


def hold(observed_seq: int | None, reason: str) -> dict:
    out: dict = {"type": "hold", "reason": reason}
    if observed_seq is not None:
        out["observed_seq"] = observed_seq
    return out


def submit_order(
    observed_seq: int,
    side: str,
    qty: float,
    client_order_id: str,
    reason: str,
) -> dict:
    return {
        "type": "submit_order",
        "observed_seq": observed_seq,
        "side": side,
        "kind": "market",
        "qty": qty,
        "tif": "ioc",
        "reduce_only": False,
        "client_order_id": client_order_id,
        "reason": reason,
    }


def maybe_decide(message: dict, state: OnlineTfiState, args: argparse.Namespace) -> dict:
    message_type = message.get("type")
    observed_seq = message.get("observed_seq")
    local_ts_us = int(message.get("local_ts_us") or 0)
    payload = message.get("payload") or {}

    if message_type == "market_trade":
        trade = payload.get("trade") or {}
        state.add_trade(
            local_ts_us=int(trade.get("local_ts_us") or local_ts_us),
            side=str(trade.get("side") or ""),
            qty=float(trade.get("qty") or 0.0),
        )
    elif message_type in {"account_snapshot", "order_reject", "fill"}:
        state.update_private(message_type, payload)
        return heartbeat(observed_seq, f"private_{message_type}_seen")
    elif message_type in {"session_start", "session_end", "order_ack"}:
        return heartbeat(observed_seq, f"{message_type}_seen")
    elif message_type == "market_l2_update":
        return heartbeat(observed_seq, "l2_seen")
    elif message_type != "market_quote":
        return heartbeat(observed_seq, f"ignored_{message_type}")

    state.trim(local_ts_us)
    current_tfi = state.tfi()
    flat = abs(state.position_qty) < 1e-9
    enough_cooldown = (
        state.last_order_local_ts_us is None
        or local_ts_us - state.last_order_local_ts_us >= args.cooldown_us
    )
    can_send = (
        observed_seq is not None
        and state.pending_client_order_id is None
        and flat
        and state.orders_sent < args.max_orders
        and enough_cooldown
        and len(state.trades) >= args.min_trades
        and state.abs_qty >= args.min_qty
        and abs(current_tfi) >= args.tfi_threshold
    )
    if not can_send:
        return hold(
            observed_seq,
            "tfi_wait "
            f"tfi={current_tfi:.6f} trades={len(state.trades)} "
            f"abs_qty={state.abs_qty:.6f} flat={flat}",
        )

    side = "buy" if current_tfi > 0 else "sell"
    client_order_id = f"online-tfi-{observed_seq}-{state.orders_sent + 1}"
    state.pending_client_order_id = client_order_id
    state.orders_sent += 1
    state.last_order_local_ts_us = local_ts_us
    return submit_order(
        observed_seq=int(observed_seq),
        side=side,
        qty=args.qty,
        client_order_id=client_order_id,
        reason=f"online_tfi_threshold tfi={current_tfi:.6f}",
    )


def main() -> None:
    args = parse_args()
    state = OnlineTfiState(window_us=args.window_us)
    for raw_line in sys.stdin:
        try:
            message = json.loads(raw_line)
            response = maybe_decide(message, state, args)
        except Exception as exc:  # Keep stdout protocol alive; diagnostics go to stderr.
            print(f"strategy_error: {exc}", file=sys.stderr, flush=True)
            response = heartbeat(None, "strategy_error")
        print(json.dumps(response, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()

"""Independent TCP Strategy Bot for the local CCUSDT runner server.

This process connects to Runner public/private NDJSON streams, maintains the
same online feature state as the stdin strategy, and sends sparse intents to the
Runner order ingress socket. It reads only exchange-visible events.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import socket
import sys
import threading
import time
from types import SimpleNamespace

from shadow_policy import add_shadow_args, build_shadow_policy
from strategy import OnlineTfiState, maybe_decide


def parse_addr(raw: str) -> tuple[str, int]:
    host, port = raw.rsplit(":", 1)
    return host, int(port)


def connect_with_retry(addr: str, label: str, timeout_s: float) -> socket.socket:
    host, port = parse_addr(addr)
    deadline = time.monotonic() + timeout_s
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            sock = socket.create_connection((host, port), timeout=1.0)
            sock.settimeout(None)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return sock
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    raise RuntimeError(f"could not connect {label} at {addr}: {last_error}")


def reader_thread(sock: socket.socket, channel: str, out: queue.Queue[dict]) -> None:
    with sock, sock.makefile("r", encoding="utf-8", newline="\n") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"tcp_bot_json_error channel={channel}: {exc}", file=sys.stderr, flush=True)
                continue
            message["_tcp_channel"] = channel
            out.put(message)


def send_order(sock: socket.socket, message: dict) -> None:
    raw = json.dumps(json_safe(message), separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    sock.sendall(raw)


def json_safe(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-addr", default="127.0.0.1:8801")
    parser.add_argument("--private-addr", default="127.0.0.1:8802")
    parser.add_argument("--order-addr", default="127.0.0.1:8803")
    parser.add_argument("--connect-timeout-s", type=float, default=10.0)
    parser.add_argument("--idle-timeout-s", type=float, default=30.0)
    parser.add_argument("--qty", type=float, default=10.0)
    parser.add_argument("--window-us", type=int, default=5_000_000)
    parser.add_argument("--closed-window", type=int, default=5)
    parser.add_argument("--tfi-threshold", type=float, default=0.8)
    parser.add_argument("--min-trades", type=int, default=3)
    parser.add_argument("--min-qty", type=float, default=0.0)
    parser.add_argument("--cooldown-us", type=int, default=30_000_000)
    parser.add_argument("--max-orders", type=int, default=1)
    parser.add_argument("--heartbeat-interval-us", type=int, default=10_000_000)
    add_shadow_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    events: queue.Queue[dict] = queue.Queue()
    public_sock = connect_with_retry(args.public_addr, "public", args.connect_timeout_s)
    private_sock = connect_with_retry(args.private_addr, "private", args.connect_timeout_s)
    order_sock = connect_with_retry(args.order_addr, "order", args.connect_timeout_s)

    threading.Thread(target=reader_thread, args=(public_sock, "public", events), daemon=True).start()
    threading.Thread(target=reader_thread, args=(private_sock, "private", events), daemon=True).start()

    state = OnlineTfiState(window_us=args.window_us, closed_window=args.closed_window)
    strategy_args = SimpleNamespace(
        qty=args.qty,
        window_us=args.window_us,
        closed_window=args.closed_window,
        tfi_threshold=args.tfi_threshold,
        min_trades=args.min_trades,
        min_qty=args.min_qty,
        cooldown_us=args.cooldown_us,
        max_orders=args.max_orders,
        sparse_output=True,
        heartbeat_interval_us=args.heartbeat_interval_us,
        shadow_four_cell=args.shadow_four_cell,
        shadow_frames_threshold=args.shadow_frames_threshold,
        shadow_overlay_threshold=args.shadow_overlay_threshold,
        shadow_r5_threshold=args.shadow_r5_threshold,
        shadow_bucket_us=args.shadow_bucket_us,
        shadow_fixed_exit_us=args.shadow_fixed_exit_us,
        shadow_gamma_preset=args.shadow_gamma_preset,
        shadow_max_triggers=args.shadow_max_triggers,
        shadow_trade_entries=False,
        shadow_trade_exits=False,
        shadow_entry_notional=1.0,
    )
    shadow_policy = build_shadow_policy(strategy_args)

    processed = 0
    sent = 0
    session_done = False
    with order_sock:
        while not session_done:
            try:
                message = events.get(timeout=args.idle_timeout_s)
            except queue.Empty:
                print("tcp_bot_idle_timeout", file=sys.stderr, flush=True)
                break
            processed += 1
            response = maybe_decide(message, state, strategy_args, shadow_policy)
            if response is not None:
                send_order(order_sock, response)
                sent += 1
            if message.get("type") == "session_end":
                session_done = True

    print(
        json.dumps(
            {
                "ok": True,
                "processed": processed,
                "sent": sent,
                "orders_sent": state.orders_sent,
                "position_qty": state.position_qty,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

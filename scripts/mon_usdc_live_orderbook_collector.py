#!/usr/bin/env python3
"""
Live MONUSDT USD-M futures order-book collector.

Default mode uses Binance futures WebSocket partial top-20 depth, bookTicker,
and aggTrade streams. Strict L2 mode uses a REST depth snapshot plus the
diff-depth stream to maintain a local MONUSDT top-1000 book with continuity
checks.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import json
import math
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp


DEFAULT_DATA_ROOT = Path("data/mon_usdc/v1")
DEFAULT_SYMBOL = "MONUSDT"
DEFAULT_REST_BASES = (
    "https://fapi.binance.com",
)


class SequenceGap(RuntimeError):
    pass


@dataclass
class TradeAgg:
    count: int = 0
    taker_buy_quote: float = 0.0
    taker_sell_quote: float = 0.0
    max_trade_quote: float = 0.0

    def add(self, price: float, qty: float, buyer_maker: bool) -> None:
        quote = price * qty
        self.count += 1
        self.max_trade_quote = max(self.max_trade_quote, quote)
        if buyer_maker:
            self.taker_sell_quote += quote
        else:
            self.taker_buy_quote += quote


@dataclass
class BookState:
    mode: str = "partial_top20"
    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)
    bid_map: dict[float, float] = field(default_factory=dict)
    ask_map: dict[float, float] = field(default_factory=dict)
    book_bid: float | None = None
    book_bid_qty: float | None = None
    book_ask: float | None = None
    book_ask_qty: float | None = None
    last_depth_event_ms: int | None = None
    last_book_ticker_event_ms: int | None = None
    last_update_id: int | None = None
    last_pu: int | None = None
    snapshot_last_update_id: int | None = None
    strict_l2_ready: bool = False
    resync_count: int = 0
    sequence_gaps: int = 0
    depth_update_count: int = 0
    book_ticker_count: int = 0


class RotatingJsonlGzWriter:
    def __init__(self, root: Path, symbol: str, run_tag: str, chunk_seconds: int) -> None:
        self.root = root
        self.symbol = symbol.lower()
        self.run_tag = run_tag
        self.chunk_seconds = chunk_seconds
        self.chunk_start: int | None = None
        self.handle: gzip.GzipFile | None = None
        self.path: Path | None = None
        self.parts: list[str] = []

    def write(self, received_ms: int, payload: dict[str, Any]) -> None:
        second = received_ms // 1000
        chunk_start = second - second % self.chunk_seconds
        if chunk_start != self.chunk_start:
            self.rotate(chunk_start)
        assert self.handle is not None
        row = {
            "local_received_ms": received_ms,
            "local_received_utc": utc_from_ms(received_ms),
            "payload": payload,
        }
        self.handle.write((json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8"))

    def rotate(self, chunk_start: int) -> None:
        self.close()
        dt = datetime.fromtimestamp(chunk_start, tz=timezone.utc)
        directory = (
            self.root
            / "raw"
            / "binance_live_orderbook_events"
            / f"dt={dt:%Y-%m-%d}"
            / f"hour={dt:%H}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (
            f"{self.symbol}_live_orderbook_{self.run_tag}_{dt:%Y%m%dT%H%M%SZ}.jsonl.gz"
        )
        self.path = path
        self.chunk_start = chunk_start
        self.handle = gzip.open(path, "ab")
        self.parts.append(str(path).replace("\\", "/"))

    def flush(self) -> None:
        if self.handle is not None:
            self.handle.flush()

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


class SnapshotWriter:
    def __init__(self, root: Path, symbol: str, run_tag: str) -> None:
        self.root = root
        self.symbol = symbol.lower()
        self.run_tag = run_tag
        self.path: Path | None = None
        self.parts: list[str] = []

    def write(self, snapshot: dict[str, Any]) -> Path:
        now = int(time.time())
        dt = datetime.fromtimestamp(now, tz=timezone.utc)
        last_update_id = snapshot.get("lastUpdateId", "unknown")
        directory = (
            self.root
            / "raw"
            / "binance_live_orderbook_snapshots"
            / f"dt={dt:%Y-%m-%d}"
            / f"hour={dt:%H}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (
            f"{self.symbol}_snapshot_{self.run_tag}_{dt:%Y%m%dT%H%M%SZ}_{last_update_id}.json.gz"
        )
        row = {
            "local_received_ms": int(time.time() * 1000),
            "local_received_utc": utc_from_seconds(now),
            "snapshot": snapshot,
        }
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(row, handle, separators=(",", ":"))
            handle.write("\n")
        self.path = path
        self.parts.append(str(path).replace("\\", "/"))
        return path


class HourlyFeatureWriter:
    FIELDNAMES = [
        "run_tag",
        "mode",
        "symbol",
        "second_timestamp",
        "second_utc",
        "book_event_ms",
        "book_ticker_event_ms",
        "last_update_id",
        "snapshot_last_update_id",
        "strict_l2_ready",
        "resync_count",
        "book_levels_bid",
        "book_levels_ask",
        "best_bid",
        "best_bid_qty",
        "best_ask",
        "best_ask_qty",
        "mid_price",
        "spread_bps",
        "microprice",
        "bid_notional_top5",
        "ask_notional_top5",
        "wobi_top5",
        "bid_notional_top20",
        "ask_notional_top20",
        "wobi_top20",
        "bid_notional_top100",
        "ask_notional_top100",
        "wobi_top100",
        "bid_notional_top500",
        "ask_notional_top500",
        "wobi_top500",
        "bid_notional_top1000",
        "ask_notional_top1000",
        "wobi_top1000",
        "depth_slope_bid",
        "depth_slope_ask",
        "depth_slope_bid_top100",
        "depth_slope_ask_top100",
        "depth_slope_bid_top1000",
        "depth_slope_ask_top1000",
        "trade_count",
        "taker_buy_quote",
        "taker_sell_quote",
        "trade_imbalance",
        "max_trade_quote",
        "sweep_intensity",
        "depth_update_count",
        "book_ticker_count",
        "sequence_gaps",
        "diagnostic_status",
    ]

    def __init__(self, root: Path, symbol: str, run_tag: str) -> None:
        self.root = root
        self.symbol = symbol.upper()
        self.symbol_lc = symbol.lower()
        self.run_tag = run_tag
        self.hour: str | None = None
        self.handle: Any = None
        self.writer: csv.DictWriter[str] | None = None
        self.parts: list[str] = []

    def write(self, second: int, book: BookState, trade: TradeAgg) -> None:
        dt = datetime.fromtimestamp(second, tz=timezone.utc)
        hour = dt.strftime("%Y-%m-%dT%H")
        if hour != self.hour:
            self.rotate(dt)
        assert self.writer is not None
        row = build_feature_row(self.run_tag, self.symbol, second, book, trade)
        self.writer.writerow(row)

    def rotate(self, dt: datetime) -> None:
        self.close()
        directory = (
            self.root
            / "derived"
            / "mon_usdc_live_orderbook_features_1s"
            / f"dt={dt:%Y-%m-%d}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (
            f"{self.symbol_lc}_live_orderbook_features_1s_{self.run_tag}_{dt:%Y%m%dT%HZ}.csv"
        )
        exists = path.exists() and path.stat().st_size > 0
        self.handle = path.open("a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.handle, fieldnames=self.FIELDNAMES)
        if not exists:
            self.writer.writeheader()
        self.hour = dt.strftime("%Y-%m-%dT%H")
        self.parts.append(str(path).replace("\\", "/"))

    def flush(self) -> None:
        if self.handle is not None:
            self.handle.flush()

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
        self.handle = None
        self.writer = None


def build_feature_row(
    run_tag: str, symbol: str, second: int, book: BookState, trade: TradeAgg
) -> dict[str, Any]:
    best_bid, best_bid_qty = top_price_qty(book.bids, reverse=True)
    best_ask, best_ask_qty = top_price_qty(book.asks, reverse=False)
    if book.book_bid is not None:
        best_bid, best_bid_qty = book.book_bid, book.book_bid_qty
    if book.book_ask is not None:
        best_ask, best_ask_qty = book.book_ask, book.book_ask_qty

    mid = None
    spread_bps = None
    microprice = None
    if positive(best_bid) and positive(best_ask):
        mid = (best_bid + best_ask) / 2.0
        spread_bps = 10000.0 * (best_ask - best_bid) / mid if mid > 0 else None
        if positive(best_bid_qty) and positive(best_ask_qty):
            microprice = (best_ask * best_bid_qty + best_bid * best_ask_qty) / (
                best_bid_qty + best_ask_qty
            )

    bid5 = side_notional(book.bids[:5])
    ask5 = side_notional(book.asks[:5])
    bid20 = side_notional(book.bids[:20])
    ask20 = side_notional(book.asks[:20])
    bid100 = side_notional(book.bids[:100])
    ask100 = side_notional(book.asks[:100])
    bid500 = side_notional(book.bids[:500])
    ask500 = side_notional(book.asks[:500])
    bid1000 = side_notional(book.bids[:1000])
    ask1000 = side_notional(book.asks[:1000])
    total_quote = trade.taker_buy_quote + trade.taker_sell_quote
    status = []
    if not book.bids or not book.asks:
        status.append("missing_book")
    if best_bid is not None and best_ask is not None and best_bid >= best_ask:
        status.append("crossed_or_locked")
    if book.mode == "strict_l2" and not book.strict_l2_ready:
        status.append("strict_l2_not_ready")
    if book.sequence_gaps:
        status.append("sequence_gap")
    if not status:
        status.append("ok")

    return {
        "run_tag": run_tag,
        "mode": book.mode,
        "symbol": symbol,
        "second_timestamp": second,
        "second_utc": utc_from_seconds(second),
        "book_event_ms": book.last_depth_event_ms,
        "book_ticker_event_ms": book.last_book_ticker_event_ms,
        "last_update_id": book.last_update_id,
        "snapshot_last_update_id": book.snapshot_last_update_id,
        "strict_l2_ready": str(book.strict_l2_ready).lower(),
        "resync_count": book.resync_count,
        "book_levels_bid": len(book.bids),
        "book_levels_ask": len(book.asks),
        "best_bid": fmt(best_bid),
        "best_bid_qty": fmt(best_bid_qty),
        "best_ask": fmt(best_ask),
        "best_ask_qty": fmt(best_ask_qty),
        "mid_price": fmt(mid),
        "spread_bps": fmt(spread_bps),
        "microprice": fmt(microprice),
        "bid_notional_top5": fmt(bid5),
        "ask_notional_top5": fmt(ask5),
        "wobi_top5": fmt(safe_div(bid5 - ask5, bid5 + ask5)),
        "bid_notional_top20": fmt(bid20),
        "ask_notional_top20": fmt(ask20),
        "wobi_top20": fmt(safe_div(bid20 - ask20, bid20 + ask20)),
        "bid_notional_top100": fmt(bid100),
        "ask_notional_top100": fmt(ask100),
        "wobi_top100": fmt(safe_div(bid100 - ask100, bid100 + ask100)),
        "bid_notional_top500": fmt(bid500),
        "ask_notional_top500": fmt(ask500),
        "wobi_top500": fmt(safe_div(bid500 - ask500, bid500 + ask500)),
        "bid_notional_top1000": fmt(bid1000),
        "ask_notional_top1000": fmt(ask1000),
        "wobi_top1000": fmt(safe_div(bid1000 - ask1000, bid1000 + ask1000)),
        "depth_slope_bid": fmt(safe_div(bid20 - bid5, 15.0)),
        "depth_slope_ask": fmt(safe_div(ask20 - ask5, 15.0)),
        "depth_slope_bid_top100": fmt(safe_div(bid100 - bid20, 80.0)),
        "depth_slope_ask_top100": fmt(safe_div(ask100 - ask20, 80.0)),
        "depth_slope_bid_top1000": fmt(safe_div(bid1000 - bid100, 900.0)),
        "depth_slope_ask_top1000": fmt(safe_div(ask1000 - ask100, 900.0)),
        "trade_count": trade.count,
        "taker_buy_quote": fmt(trade.taker_buy_quote),
        "taker_sell_quote": fmt(trade.taker_sell_quote),
        "trade_imbalance": fmt(safe_div(trade.taker_buy_quote - trade.taker_sell_quote, total_quote)),
        "max_trade_quote": fmt(trade.max_trade_quote),
        "sweep_intensity": fmt(safe_div(trade.max_trade_quote, total_quote)),
        "depth_update_count": book.depth_update_count,
        "book_ticker_count": book.book_ticker_count,
        "sequence_gaps": book.sequence_gaps,
        "diagnostic_status": "|".join(status),
    }


def update_book_from_depth20(book: BookState, data: dict[str, Any]) -> None:
    previous_u = book.last_update_id
    pu = to_int(data.get("pu"))
    u = to_int(data.get("u"))
    if previous_u is not None and pu is not None and pu != previous_u:
        book.sequence_gaps += 1
    book.last_pu = pu
    book.last_update_id = u
    book.last_depth_event_ms = to_int(data.get("E")) or to_int(data.get("T"))
    book.bids = sorted(parse_levels(data.get("b", [])), key=lambda x: x[0], reverse=True)[:20]
    book.asks = sorted(parse_levels(data.get("a", [])), key=lambda x: x[0])[:20]
    book.depth_update_count += 1


def apply_snapshot(book: BookState, snapshot: dict[str, Any]) -> None:
    last_update_id = to_int(snapshot.get("lastUpdateId"))
    if last_update_id is None:
        raise RuntimeError("snapshot missing lastUpdateId")
    bids = parse_levels(snapshot.get("bids", []))
    asks = parse_levels(snapshot.get("asks", []))
    if not bids or not asks:
        raise RuntimeError("snapshot missing bids/asks")
    book.mode = "strict_l2"
    book.bid_map = {price: qty for price, qty in bids if qty > 0.0}
    book.ask_map = {price: qty for price, qty in asks if qty > 0.0}
    book.snapshot_last_update_id = last_update_id
    book.last_update_id = last_update_id
    book.last_pu = None
    book.strict_l2_ready = False
    refresh_strict_levels(book)


def update_book_from_diff(book: BookState, data: dict[str, Any]) -> bool:
    first_update_id = to_int(data.get("U"))
    final_update_id = to_int(data.get("u"))
    previous_update_id = to_int(data.get("pu"))
    if first_update_id is None or final_update_id is None:
        return False
    snapshot_id = book.snapshot_last_update_id
    if snapshot_id is None:
        raise SequenceGap("strict L2 diff arrived before snapshot")
    if final_update_id < snapshot_id:
        return False
    if not book.strict_l2_ready:
        if not (first_update_id <= snapshot_id <= final_update_id):
            raise SequenceGap(
                f"first strict diff does not bridge snapshot: U={first_update_id} "
                f"u={final_update_id} snapshot={snapshot_id}"
            )
        apply_diff_levels(book, data)
        book.strict_l2_ready = True
    else:
        if previous_update_id != book.last_update_id:
            raise SequenceGap(
                f"strict L2 pu gap: pu={previous_update_id} previous_u={book.last_update_id}"
            )
        apply_diff_levels(book, data)
    book.last_pu = previous_update_id
    book.last_update_id = final_update_id
    book.last_depth_event_ms = to_int(data.get("E")) or to_int(data.get("T"))
    book.depth_update_count += 1
    return True


def apply_diff_levels(book: BookState, data: dict[str, Any]) -> None:
    for price, qty in parse_levels(data.get("b", [])):
        if qty == 0.0:
            book.bid_map.pop(price, None)
        else:
            book.bid_map[price] = qty
    for price, qty in parse_levels(data.get("a", [])):
        if qty == 0.0:
            book.ask_map.pop(price, None)
        else:
            book.ask_map[price] = qty
    refresh_strict_levels(book)


def refresh_strict_levels(book: BookState) -> None:
    book.bids = sorted(book.bid_map.items(), key=lambda item: item[0], reverse=True)[:1000]
    book.asks = sorted(book.ask_map.items(), key=lambda item: item[0])[:1000]


def update_book_from_book_ticker(book: BookState, data: dict[str, Any]) -> None:
    book.book_bid = to_float(data.get("b"))
    book.book_bid_qty = to_float(data.get("B"))
    book.book_ask = to_float(data.get("a"))
    book.book_ask_qty = to_float(data.get("A"))
    book.last_book_ticker_event_ms = to_int(data.get("E")) or to_int(data.get("T"))
    book.book_ticker_count += 1


def update_trade_agg(trades_by_second: dict[int, TradeAgg], data: dict[str, Any]) -> None:
    event_ms = to_int(data.get("E")) or to_int(data.get("T"))
    if event_ms is None:
        return
    price = to_float(data.get("p"))
    qty = to_float(data.get("q"))
    if not positive(price) or not positive(qty):
        return
    buyer_maker = bool(data.get("m"))
    second = event_ms // 1000
    trades_by_second.setdefault(second, TradeAgg()).add(price, qty, buyer_maker)


async def probe_rest_snapshot(args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    timeout = aiohttp.ClientTimeout(total=args.rest_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        for base in args.rest_bases:
            url = f"{base.rstrip('/')}/fapi/v1/depth"
            result: dict[str, Any] = {"base": base}
            try:
                async with session.get(
                    url,
                    params={"symbol": args.symbol.upper(), "limit": str(args.snapshot_limit)},
                    proxy=args.proxy,
                    headers={"User-Agent": "mon-usdc-live-orderbook-collector"},
                ) as response:
                    text = await response.text()
                    result["status"] = response.status
                    result["content_length"] = len(text)
                    if response.status == 200:
                        payload = json.loads(text)
                        result["lastUpdateId"] = payload.get("lastUpdateId")
                        result["bids"] = len(payload.get("bids", []))
                        result["asks"] = len(payload.get("asks", []))
                    else:
                        result["body_prefix"] = text[:220]
            except Exception as exc:  # noqa: BLE001
                result["error"] = f"{type(exc).__name__}: {exc}"
            results.append(result)
    return results


async def fetch_depth_snapshot(
    session: aiohttp.ClientSession, args: argparse.Namespace
) -> tuple[dict[str, Any], dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for base in args.rest_bases:
        url = f"{base.rstrip('/')}/fapi/v1/depth"
        try:
            async with session.get(
                url,
                params={"symbol": args.symbol.upper(), "limit": str(args.snapshot_limit)},
                proxy=args.proxy,
                headers={"User-Agent": "mon-usdc-live-orderbook-collector"},
            ) as response:
                text = await response.text()
                if response.status == 200:
                    payload = json.loads(text)
                    return payload, {
                        "base": base,
                        "status": response.status,
                        "lastUpdateId": payload.get("lastUpdateId"),
                        "bids": len(payload.get("bids", [])),
                        "asks": len(payload.get("asks", [])),
                    }
                errors.append(
                    {
                        "base": base,
                        "status": response.status,
                        "content_length": len(text),
                        "body_prefix": text[:220],
                    }
                )
        except Exception as exc:  # noqa: BLE001
            errors.append({"base": base, "error": f"{type(exc).__name__}: {exc}"})
    raise RuntimeError(f"no usable REST depth snapshot: {errors}")


async def bootstrap_strict_l2(
    ws: aiohttp.ClientWebSocketResponse,
    session: aiohttp.ClientSession,
    args: argparse.Namespace,
    raw_writer: RotatingJsonlGzWriter,
    snapshot_writer: SnapshotWriter,
    book: BookState,
    trades_by_second: dict[int, TradeAgg],
    counters: dict[str, Any],
) -> None:
    buffered: list[dict[str, Any]] = []
    snapshot_task = asyncio.create_task(fetch_depth_snapshot(session, args))
    while not snapshot_task.done():
        try:
            msg = await ws.receive(timeout=0.25)
        except asyncio.TimeoutError:
            continue
        if msg.type == aiohttp.WSMsgType.TEXT:
            now_ms = int(time.time() * 1000)
            payload = json.loads(msg.data)
            raw_writer.write(now_ms, payload)
            buffered.append(payload)
            counters["messages"] += 1
            counters["last_event_utc"] = utc_from_ms(now_ms)
        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            raise RuntimeError("websocket closed during strict L2 bootstrap")

    snapshot, snapshot_status = await snapshot_task
    snapshot_writer.write(snapshot)
    apply_snapshot(book, snapshot)
    counters["snapshot_status"] = snapshot_status
    counters["snapshot_last_update_id"] = book.snapshot_last_update_id
    counters["strict_l2_ready"] = False

    for payload in buffered:
        handle_strict_payload(payload, book, trades_by_second, counters)

    if not book.strict_l2_ready:
        deadline = time.time() + args.bootstrap_timeout_seconds
        while time.time() < deadline:
            msg = await ws.receive(timeout=1.0)
            if msg.type == aiohttp.WSMsgType.TEXT:
                now_ms = int(time.time() * 1000)
                payload = json.loads(msg.data)
                raw_writer.write(now_ms, payload)
                counters["messages"] += 1
                counters["last_event_utc"] = utc_from_ms(now_ms)
                handle_strict_payload(payload, book, trades_by_second, counters)
                if book.strict_l2_ready:
                    break
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                raise RuntimeError("websocket closed before strict L2 became ready")
    if not book.strict_l2_ready:
        raise RuntimeError("strict L2 bootstrap timed out before first bridging diff")


def rest_probe_ok(rest_probe: list[dict[str, Any]]) -> bool:
    return any(result.get("status") == 200 and result.get("lastUpdateId") for result in rest_probe)


def should_fallback_to_partial(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "rest depth snapshot" in text
        or "snapshot" in text
        or "bootstrap timed out" in text
        or "websocket closed during strict l2 bootstrap" in text
        or "websocket closed before strict l2 became ready" in text
    )


def build_websocket_url(args: argparse.Namespace) -> str:
    if args.ws_url:
        return args.ws_url
    if args.mode == "strict_l2":
        streams = [
            f"{args.symbol.lower()}@depth@100ms",
            f"{args.symbol.lower()}@bookTicker",
            f"{args.symbol.lower()}@aggTrade",
        ]
    else:
        streams = [
            f"{args.symbol.lower()}@depth20@100ms",
            f"{args.symbol.lower()}@bookTicker",
            f"{args.symbol.lower()}@aggTrade",
        ]
    if args.include_mark_price:
        streams.append(f"{args.symbol.lower()}@markPrice@1s")
    return f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"


async def collect_forever(args: argparse.Namespace) -> int:
    stop_event = asyncio.Event()
    started_at = time.time()

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: request_stop())

    data_root = args.data_root
    data_root.mkdir(parents=True, exist_ok=True)
    run_tag = args.run_tag
    raw_writer = RotatingJsonlGzWriter(data_root, args.symbol, run_tag, args.raw_chunk_seconds)
    snapshot_writer = SnapshotWriter(data_root, args.symbol, run_tag)
    feature_writer = HourlyFeatureWriter(data_root, args.symbol, run_tag)
    checkpoint_path = (
        data_root
        / "_checkpoints"
        / f"mon_usdc_live_orderbook_{args.symbol.upper()}_{run_tag}.json"
    )
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    rest_probe = await probe_rest_snapshot(args) if args.probe_rest_snapshot else []
    fallback_note = ""
    if (
        args.mode == "strict_l2"
        and args.fallback_partial_on_rest_failure
        and rest_probe
        and not rest_probe_ok(rest_probe)
    ):
        args.mode = "partial_top20"
        fallback_note = "initial REST snapshot probe failed; fell back to partial_top20"
    write_checkpoint(
        checkpoint_path,
        args,
        run_tag,
        rest_probe,
        raw_writer,
        snapshot_writer,
        feature_writer,
        counters={"status": "starting", "fallback_note": fallback_note},
    )

    book = BookState(mode=args.mode)
    trades_by_second: dict[int, TradeAgg] = {}
    last_feature_second: int | None = None
    counters = {
        "status": "running",
        "messages": 0,
        "depth20_messages": 0,
        "depth_diff_messages": 0,
        "depth_diff_dropped": 0,
        "book_ticker_messages": 0,
        "agg_trade_messages": 0,
        "other_messages": 0,
        "features_written": 0,
        "reconnects": 0,
        "resync_count": 0,
        "sequence_gaps": 0,
        "strict_l2_ready": False,
        "snapshot_last_update_id": None,
        "snapshot_status": {},
        "last_update_id": None,
        "last_event_utc": "",
        "last_error": "",
        "fallback_note": fallback_note,
    }
    last_checkpoint_at = time.time()

    try:
        while not stop_event.is_set():
            if args.max_runtime_seconds > 0 and time.time() - started_at >= args.max_runtime_seconds:
                stop_event.set()
                break
            counters["reconnects"] += 1
            try:
                url = build_websocket_url(args)
                timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60)
                async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
                    async with session.ws_connect(
                        url,
                        heartbeat=args.heartbeat_seconds,
                        receive_timeout=args.receive_timeout_seconds,
                        proxy=args.proxy,
                        compress=0,
                    ) as ws:
                        counters["status"] = "connected"
                        counters["last_error"] = ""
                        write_checkpoint(
                            checkpoint_path,
                            args,
                            run_tag,
                            rest_probe,
                            raw_writer,
                            snapshot_writer,
                            feature_writer,
                            counters,
                        )
                        if args.mode == "strict_l2":
                            await bootstrap_strict_l2(
                                ws,
                                session,
                                args,
                                raw_writer,
                                snapshot_writer,
                                book,
                                trades_by_second,
                                counters,
                            )
                            write_checkpoint(
                                checkpoint_path,
                                args,
                                run_tag,
                                rest_probe,
                                raw_writer,
                                snapshot_writer,
                                feature_writer,
                                counters,
                            )
                        async for msg in ws:
                            if stop_event.is_set():
                                break
                            if (
                                args.max_runtime_seconds > 0
                                and time.time() - started_at >= args.max_runtime_seconds
                            ):
                                stop_event.set()
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                now_ms = int(time.time() * 1000)
                                payload = json.loads(msg.data)
                                raw_writer.write(now_ms, payload)
                                if args.mode == "strict_l2":
                                    handle_strict_payload(payload, book, trades_by_second, counters)
                                else:
                                    handle_stream_payload(payload, book, trades_by_second, counters)
                                counters["messages"] += 1
                                counters["last_event_utc"] = utc_from_ms(now_ms)
                                last_feature_second = flush_due_features(
                                    feature_writer,
                                    book,
                                    trades_by_second,
                                    last_feature_second,
                                    int(time.time()),
                                    args.feature_lag_seconds,
                                    counters,
                                )
                                if counters["messages"] % args.checkpoint_interval_messages == 0:
                                    raw_writer.flush()
                                    feature_writer.flush()
                                    write_checkpoint(
                                        checkpoint_path,
                                        args,
                                        run_tag,
                                        rest_probe,
                                        raw_writer,
                                        snapshot_writer,
                                        feature_writer,
                                        counters,
                                    )
                                    last_checkpoint_at = time.time()
                                elif time.time() - last_checkpoint_at >= args.checkpoint_interval_seconds:
                                    raw_writer.flush()
                                    feature_writer.flush()
                                    write_checkpoint(
                                        checkpoint_path,
                                        args,
                                        run_tag,
                                        rest_probe,
                                        raw_writer,
                                        snapshot_writer,
                                        feature_writer,
                                        counters,
                                    )
                                    last_checkpoint_at = time.time()
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except SequenceGap as exc:
                book.sequence_gaps += 1
                book.resync_count += 1
                counters["sequence_gaps"] = book.sequence_gaps
                counters["resync_count"] = book.resync_count
                counters["strict_l2_ready"] = False
                book.strict_l2_ready = False
                counters["status"] = "resyncing"
                counters["last_error"] = f"{type(exc).__name__}: {exc}"
                write_checkpoint(
                    checkpoint_path,
                    args,
                    run_tag,
                    rest_probe,
                    raw_writer,
                    snapshot_writer,
                    feature_writer,
                    counters,
                )
                await asyncio.sleep(args.reconnect_delay_seconds)
            except Exception as exc:  # noqa: BLE001
                if (
                    args.mode == "strict_l2"
                    and args.fallback_partial_on_rest_failure
                    and should_fallback_to_partial(exc)
                ):
                    args.mode = "partial_top20"
                    book = BookState(mode=args.mode)
                    counters["fallback_note"] = (
                        "strict_l2 bootstrap failed; fell back to partial_top20"
                    )
                counters["status"] = "reconnecting"
                counters["last_error"] = f"{type(exc).__name__}: {exc}"
                if args.mode == "strict_l2":
                    book.resync_count += 1
                    counters["resync_count"] = book.resync_count
                    counters["strict_l2_ready"] = False
                write_checkpoint(
                    checkpoint_path,
                    args,
                    run_tag,
                    rest_probe,
                    raw_writer,
                    snapshot_writer,
                    feature_writer,
                    counters,
                )
                await asyncio.sleep(args.reconnect_delay_seconds)
    finally:
        now_sec = int(time.time())
        flush_due_features(
            feature_writer,
            book,
            trades_by_second,
            last_feature_second,
            now_sec,
            0,
            counters,
        )
        raw_writer.flush()
        feature_writer.flush()
        raw_writer.close()
        feature_writer.close()
        counters["status"] = "stopped"
        write_checkpoint(
            checkpoint_path,
            args,
            run_tag,
            rest_probe,
            raw_writer,
            snapshot_writer,
            feature_writer,
            counters,
        )
    return 0


def handle_stream_payload(
    payload: dict[str, Any],
    book: BookState,
    trades_by_second: dict[int, TradeAgg],
    counters: dict[str, Any],
) -> None:
    data = payload.get("data", payload)
    stream = str(payload.get("stream", ""))
    event = data.get("e")
    if "depth20" in stream or event == "depthUpdate":
        update_book_from_depth20(book, data)
        counters["depth20_messages"] += 1
    elif "bookTicker" in stream or event == "bookTicker":
        update_book_from_book_ticker(book, data)
        counters["book_ticker_messages"] += 1
    elif "aggTrade" in stream or event == "aggTrade":
        update_trade_agg(trades_by_second, data)
        counters["agg_trade_messages"] += 1
    else:
        counters["other_messages"] += 1


def handle_strict_payload(
    payload: dict[str, Any],
    book: BookState,
    trades_by_second: dict[int, TradeAgg],
    counters: dict[str, Any],
) -> None:
    data = payload.get("data", payload)
    stream = str(payload.get("stream", ""))
    event = data.get("e")
    if "depth@" in stream or event == "depthUpdate":
        applied = update_book_from_diff(book, data)
        if applied:
            counters["depth_diff_messages"] += 1
        else:
            counters["depth_diff_dropped"] += 1
        counters["strict_l2_ready"] = book.strict_l2_ready
        counters["snapshot_last_update_id"] = book.snapshot_last_update_id
        counters["last_update_id"] = book.last_update_id
    elif "bookTicker" in stream or event == "bookTicker":
        update_book_from_book_ticker(book, data)
        counters["book_ticker_messages"] += 1
    elif "aggTrade" in stream or event == "aggTrade":
        update_trade_agg(trades_by_second, data)
        counters["agg_trade_messages"] += 1
    else:
        counters["other_messages"] += 1


def flush_due_features(
    writer: HourlyFeatureWriter,
    book: BookState,
    trades_by_second: dict[int, TradeAgg],
    last_feature_second: int | None,
    now_second: int,
    lag_seconds: int,
    counters: dict[str, Any],
) -> int | None:
    cutoff = now_second - lag_seconds
    if last_feature_second is None:
        if book.last_depth_event_ms is None:
            return None
        last_feature_second = book.last_depth_event_ms // 1000 - 1
    while last_feature_second + 1 <= cutoff:
        second = last_feature_second + 1
        trade = trades_by_second.pop(second, TradeAgg())
        writer.write(second, book, trade)
        counters["features_written"] += 1
        last_feature_second = second
    return last_feature_second


def write_checkpoint(
    path: Path,
    args: argparse.Namespace,
    run_tag: str,
    rest_probe: list[dict[str, Any]],
    raw_writer: RotatingJsonlGzWriter,
    snapshot_writer: SnapshotWriter,
    feature_writer: HourlyFeatureWriter,
    counters: dict[str, Any],
) -> None:
    if args.mode == "strict_l2":
        notes = [
            "Strict L2 mode uses REST /fapi/v1/depth plus diff depth stream.",
            "If pu continuity breaks, the collector resyncs instead of marking a fake continuous book.",
            "Raw snapshots are written separately from raw WebSocket events.",
        ]
    else:
        notes = [
            "Partial top20 mode is a live top-20 view, not strict full L2.",
            "Use --mode strict_l2 when REST depth snapshot is reachable.",
        ]
    value = {
        "collector": "mon_usdc_live_orderbook_collector",
        "run_tag": run_tag,
        "symbol": args.symbol.upper(),
        "mode": args.mode,
        "updated_at_utc": utc_from_seconds(int(time.time())),
        "pid": os.getpid(),
        "websocket_url_shape": "wss://fstream.binance.com/stream?...",
        "rest_snapshot_probe": rest_probe,
        "raw_current_part": str(raw_writer.path).replace("\\", "/") if raw_writer.path else "",
        "raw_parts_seen": raw_writer.parts[-10:],
        "snapshot_current_part": (
            str(snapshot_writer.path).replace("\\", "/") if snapshot_writer.path else ""
        ),
        "snapshot_parts_seen": snapshot_writer.parts[-10:],
        "feature_parts_seen": feature_writer.parts[-10:],
        "counters": counters,
        "notes": notes,
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def parse_levels(values: Any) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for level in values or []:
        if len(level) < 2:
            continue
        price = to_float(level[0])
        qty = to_float(level[1])
        if positive(price) and qty is not None and qty >= 0.0:
            out.append((price, qty))
    return out


def top_price_qty(levels: list[tuple[float, float]], reverse: bool) -> tuple[float | None, float | None]:
    if not levels:
        return None, None
    ordered = sorted(levels, key=lambda item: item[0], reverse=reverse)
    return ordered[0]


def side_notional(levels: list[tuple[float, float]]) -> float:
    return sum(price * qty for price, qty in levels if price > 0 and qty > 0)


def safe_div(numerator: float, denominator: float) -> float | None:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def to_float(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.12g}"
    return str(value)


def utc_from_seconds(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def utc_from_ms(timestamp_ms: int) -> str:
    return utc_from_seconds(timestamp_ms // 1000)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a 24/7 Binance USD-M MONUSDT live order-book collector."
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--mode",
        choices=["partial_top20", "strict_l2"],
        default="partial_top20",
        help="Use partial top20 stream or strict REST snapshot + diff-depth L2 reconstruction.",
    )
    parser.add_argument(
        "--run-tag",
        default="live_orderbook_v1",
        help="Stable tag used in raw/derived output filenames.",
    )
    parser.add_argument("--ws-url", default="")
    parser.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "")
    parser.add_argument("--rest-bases", nargs="*", default=list(DEFAULT_REST_BASES))
    parser.add_argument("--snapshot-limit", type=int, default=1000)
    parser.add_argument("--rest-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--bootstrap-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--probe-rest-snapshot", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--fallback-partial-on-rest-failure",
        action="store_true",
        help="Explicitly downgrade strict_l2 to partial_top20 if REST/bootstrap cannot build a book.",
    )
    parser.add_argument("--include-mark-price", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--raw-chunk-seconds", type=int, default=300)
    parser.add_argument("--feature-lag-seconds", type=int, default=2)
    parser.add_argument("--heartbeat-seconds", type=float, default=20.0)
    parser.add_argument("--receive-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--reconnect-delay-seconds", type=float, default=5.0)
    parser.add_argument("--checkpoint-interval-messages", type=int, default=5000)
    parser.add_argument("--checkpoint-interval-seconds", type=float, default=30.0)
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=0.0,
        help="Optional finite runtime for smoke tests. Zero means run forever.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(collect_forever(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

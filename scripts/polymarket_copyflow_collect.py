#!/usr/bin/env python3
"""Polymarket CopyFlow forward collector.

Read-only collector for public Polymarket data. It stores recent trades,
tracked wallet activity, market metadata, and CLOB book snapshots in SQLite so
later replays can use historical book VWAP instead of next-trade proxies.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA_BASE = "https://data-api.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("output/polymarket_copyflow_forward")


def now_ts() -> int:
    return int(time.time())


def iso_utc(ts: int | float | None = None) -> str:
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def http_get_json(base: str, path: str, params: dict[str, Any] | None, timeout: float) -> Any:
    query = ""
    if params:
        query = "?" + urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    req = Request(
        base.rstrip("/") + "/" + path.lstrip("/") + query,
        headers={"User-Agent": "finance-chain-polymarket-copyflow-collector/0.1"},
        method="GET",
    )
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable http_get_json state")


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def sorted_levels(levels: list[dict[str, Any]], side: str) -> list[tuple[float, float]]:
    parsed: list[tuple[float, float]] = []
    for row in levels or []:
        price = safe_float(row.get("price"))
        size = safe_float(row.get("size"))
        if price is None or size is None or price <= 0 or size <= 0:
            continue
        parsed.append((price, size))
    reverse = side == "bid"
    return sorted(parsed, key=lambda x: x[0], reverse=reverse)


def trade_identity(row: dict[str, Any]) -> str:
    parts = [
        row.get("transactionHash"),
        row.get("proxyWallet"),
        row.get("asset"),
        row.get("side"),
        row.get("price"),
        row.get("size"),
        row.get("timestamp"),
    ]
    return "|".join(str(x or "") for x in parts)


class CopyflowStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def count_rows(self, table: str) -> int:
        if table not in {"trades_raw", "wallet_activity_raw", "markets_raw", "asset_books", "asset_book_levels", "tracked_wallets", "collector_state"}:
            raise ValueError(f"unknown table: {table}")
        with self.connect() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def upsert_trades(self, rows: list[dict[str, Any]], ingest_ts: int, source: str) -> int:
        inserted = 0
        with self.connect() as conn:
            for row in rows:
                identity = trade_identity(row)
                ts = safe_int(row.get("timestamp"))
                price = safe_float(row.get("price"))
                size = safe_float(row.get("size"))
                wallet = str(row.get("proxyWallet") or "").lower()
                asset = str(row.get("asset") or "")
                condition_id = str(row.get("conditionId") or "").lower()
                side = str(row.get("side") or "").upper()
                if not wallet or not asset or not condition_id or ts is None or price is None or size is None:
                    continue
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO trades_raw(
                        trade_identity, source, ingest_ts, timestamp, wallet, asset,
                        condition_id, side, price, size, outcome, title, slug,
                        event_slug, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identity,
                        source,
                        ingest_ts,
                        ts,
                        wallet,
                        asset,
                        condition_id,
                        side,
                        price,
                        size,
                        str(row.get("outcome") or ""),
                        str(row.get("title") or ""),
                        str(row.get("slug") or ""),
                        str(row.get("eventSlug") or ""),
                        json.dumps(row, ensure_ascii=False, sort_keys=True),
                    ),
                )
                if cur.rowcount:
                    inserted += 1
        return inserted

    def upsert_wallet_activity(self, wallet: str, rows: list[dict[str, Any]], ingest_ts: int) -> int:
        inserted = self.upsert_trades(rows, ingest_ts, source="wallet_activity")
        with self.connect() as conn:
            for row in rows:
                identity = trade_identity(row)
                conn.execute(
                    "INSERT OR IGNORE INTO wallet_activity_raw(wallet, trade_identity, ingest_ts, raw_json) VALUES (?, ?, ?, ?)",
                    (wallet.lower(), identity, ingest_ts, json.dumps(row, ensure_ascii=False, sort_keys=True)),
                )
        return inserted

    def upsert_markets(self, events: list[dict[str, Any]], ingest_ts: int) -> int:
        inserted = 0
        with self.connect() as conn:
            for event in events:
                event_id = str(event.get("id") or "")
                event_title = str(event.get("title") or "")
                event_slug = str(event.get("slug") or "")
                for market in event.get("markets") or []:
                    market_id = str(market.get("id") or "")
                    condition_id = str(market.get("conditionId") or "").lower()
                    token_ids = parse_json_list(market.get("clobTokenIds"))
                    outcomes = parse_json_list(market.get("outcomes"))
                    cur = conn.execute(
                        """
                        INSERT OR REPLACE INTO markets_raw(
                            market_id, condition_id, event_id, event_title, event_slug,
                            question, slug, end_date, clob_token_ids, outcomes,
                            ingest_ts, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            market_id,
                            condition_id,
                            event_id,
                            event_title,
                            event_slug,
                            str(market.get("question") or ""),
                            str(market.get("slug") or ""),
                            str(market.get("endDate") or market.get("endDateIso") or ""),
                            json.dumps(token_ids, ensure_ascii=False),
                            json.dumps(outcomes, ensure_ascii=False),
                            ingest_ts,
                            json.dumps(market, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                    if cur.rowcount:
                        inserted += 1
        return inserted

    def insert_book_snapshot(self, asset: str, book: dict[str, Any], ingest_ts: int) -> int:
        bids = sorted_levels(book.get("bids") or [], "bid")
        asks = sorted_levels(book.get("asks") or [], "ask")
        best_bid = bids[0][0] if bids else None
        best_ask = asks[0][0] if asks else None
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO asset_books(asset, ingest_ts, best_bid, best_ask, raw_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (asset, ingest_ts, best_bid, best_ask, json.dumps(book, ensure_ascii=False, sort_keys=True)),
            )
            book_id = int(cur.lastrowid)
            for side, levels in (("bid", bids), ("ask", asks)):
                for level_index, (price, size) in enumerate(levels):
                    conn.execute(
                        """
                        INSERT INTO asset_book_levels(book_id, asset, ingest_ts, side, level_index, price, size)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (book_id, asset, ingest_ts, side, level_index, price, size),
                    )
        return book_id

    def latest_book_for_asset(self, asset: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM asset_books WHERE asset = ? ORDER BY ingest_ts DESC, id DESC LIMIT 1",
                (asset,),
            ).fetchone()
            return dict(row) if row is not None else None

    def set_tracked_wallets(self, wallets: list[str], reason: str, ingest_ts: int) -> int:
        count = 0
        with self.connect() as conn:
            for wallet in wallets:
                wallet = wallet.strip().lower()
                if not wallet:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO tracked_wallets(wallet, reason, updated_ts) VALUES (?, ?, ?)",
                    (wallet, reason, ingest_ts),
                )
                count += 1
        return count

    def tracked_wallets(self, limit: int) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT wallet FROM tracked_wallets ORDER BY updated_ts DESC, wallet LIMIT ?",
                (limit,),
            ).fetchall()
            return [str(row[0]) for row in rows]

    def candidate_assets(self, limit: int) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT asset, COUNT(*) AS n, MAX(timestamp) AS last_ts
                FROM trades_raw
                WHERE side = 'BUY'
                GROUP BY asset
                ORDER BY last_ts DESC, n DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [str(row[0]) for row in rows]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_identity TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    ingest_ts INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    wallet TEXT NOT NULL,
    asset TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    outcome TEXT,
    title TEXT,
    slug TEXT,
    event_slug TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_raw_ts ON trades_raw(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_raw_wallet ON trades_raw(wallet, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_raw_asset ON trades_raw(asset, timestamp);

CREATE TABLE IF NOT EXISTS wallet_activity_raw (
    wallet TEXT NOT NULL,
    trade_identity TEXT NOT NULL,
    ingest_ts INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY(wallet, trade_identity)
);

CREATE TABLE IF NOT EXISTS markets_raw (
    market_id TEXT,
    condition_id TEXT PRIMARY KEY,
    event_id TEXT,
    event_title TEXT,
    event_slug TEXT,
    question TEXT,
    slug TEXT,
    end_date TEXT,
    clob_token_ids TEXT,
    outcomes TEXT,
    ingest_ts INTEGER NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    ingest_ts INTEGER NOT NULL,
    best_bid REAL,
    best_ask REAL,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_asset_books_asset_ts ON asset_books(asset, ingest_ts);

CREATE TABLE IF NOT EXISTS asset_book_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    asset TEXT NOT NULL,
    ingest_ts INTEGER NOT NULL,
    side TEXT NOT NULL,
    level_index INTEGER NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    FOREIGN KEY(book_id) REFERENCES asset_books(id)
);
CREATE INDEX IF NOT EXISTS idx_asset_book_levels_book_side ON asset_book_levels(book_id, side, level_index);

CREATE TABLE IF NOT EXISTS tracked_wallets (
    wallet TEXT PRIMARY KEY,
    reason TEXT,
    updated_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS collector_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_ts INTEGER NOT NULL
);
"""


def fetch_recent_trades(limit: int, timeout: float) -> list[dict[str, Any]]:
    body = http_get_json(DATA_BASE, "/trades", {"limit": limit, "takerOnly": "true"}, timeout)
    return body if isinstance(body, list) else []


def fetch_wallet_activity(wallet: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    body = http_get_json(
        DATA_BASE,
        "/activity",
        {"user": wallet, "type": "TRADE", "limit": min(limit, 500), "sortDirection": "DESC", "sortBy": "TIMESTAMP"},
        timeout,
    )
    return body if isinstance(body, list) else []


def fetch_events(limit: int, timeout: float) -> list[dict[str, Any]]:
    body = http_get_json(
        GAMMA_BASE,
        "/events",
        {"limit": limit, "active": "true", "closed": "false", "order": "volume24hr", "ascending": "false"},
        timeout,
    )
    return body if isinstance(body, list) else []


def fetch_book(asset: str, timeout: float) -> dict[str, Any]:
    body = http_get_json(CLOB_BASE, "/book", {"token_id": asset}, timeout)
    return body if isinstance(body, dict) else {}


def collect_once(args: argparse.Namespace) -> dict[str, Any]:
    db_path = args.db_path if args.db_path.is_absolute() else REPO_ROOT / args.db_path
    store = CopyflowStore(db_path)
    store.initialize()
    ingest_ts = now_ts()
    summary: dict[str, Any] = {"ingest_ts": ingest_ts, "db_path": str(db_path)}

    recent = fetch_recent_trades(args.recent_trade_limit, args.http_timeout)
    summary["recent_trades_inserted"] = store.upsert_trades(recent, ingest_ts, "recent")

    wallets = [w.strip().lower() for w in args.wallet if w.strip()]
    if args.seed_wallets_from_recent > 0:
        wallet_counts: dict[str, int] = {}
        for row in recent:
            wallet = str(row.get("proxyWallet") or "").lower()
            if wallet:
                wallet_counts[wallet] = wallet_counts.get(wallet, 0) + 1
        wallets.extend([w for w, _ in sorted(wallet_counts.items(), key=lambda kv: kv[1], reverse=True)[: args.seed_wallets_from_recent]])
    if wallets:
        store.set_tracked_wallets(list(dict.fromkeys(wallets)), "cli_or_recent", ingest_ts)
    tracked = store.tracked_wallets(args.wallet_limit)
    wallet_inserted = 0
    for wallet in tracked:
        try:
            rows = fetch_wallet_activity(wallet, args.wallet_activity_limit, args.http_timeout)
        except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError):
            rows = []
        wallet_inserted += store.upsert_wallet_activity(wallet, rows, ingest_ts)
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000.0)
    summary["tracked_wallets"] = len(tracked)
    summary["wallet_activity_inserted"] = wallet_inserted

    if args.gamma_event_limit > 0:
        events = fetch_events(args.gamma_event_limit, args.http_timeout)
        summary["markets_upserted"] = store.upsert_markets(events, ingest_ts)

    assets = [a.strip() for a in args.asset if a.strip()]
    if args.book_asset_limit > 0:
        assets.extend(store.candidate_assets(args.book_asset_limit))
    assets = list(dict.fromkeys(assets))[: args.book_asset_limit or len(assets)]
    book_ok = 0
    book_errors = 0
    for asset in assets:
        try:
            book = fetch_book(asset, args.http_timeout)
            store.insert_book_snapshot(asset, book, ingest_ts)
            book_ok += 1
        except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError):
            book_errors += 1
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000.0)
    summary["book_snapshots_inserted"] = book_ok
    summary["book_errors"] = book_errors
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect public Polymarket CopyFlow data into SQLite.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_OUTPUT_DIR / "polymarket_copyflow.sqlite")
    parser.add_argument("--recent-trade-limit", type=int, default=500)
    parser.add_argument("--wallet", action="append", default=[])
    parser.add_argument("--seed-wallets-from-recent", type=int, default=20)
    parser.add_argument("--wallet-limit", type=int, default=50)
    parser.add_argument("--wallet-activity-limit", type=int, default=100)
    parser.add_argument("--gamma-event-limit", type=int, default=80)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--book-asset-limit", type=int, default=80)
    parser.add_argument("--http-timeout", type=float, default=20.0)
    parser.add_argument("--sleep-ms", type=int, default=40)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = CopyflowStore(Path(tmp) / "test.sqlite")
        store.initialize()
        row = {
            "transactionHash": "tx",
            "proxyWallet": "0xA",
            "asset": "asset",
            "conditionId": "cond",
            "side": "BUY",
            "price": "0.4",
            "size": "5",
            "timestamp": "100",
        }
        assert store.upsert_trades([row], 101, "recent") == 1
        assert store.upsert_trades([row], 102, "recent") == 0
        assert store.count_rows("trades_raw") == 1
        book_id = store.insert_book_snapshot("asset", {"bids": [{"price": "0.39", "size": "10"}], "asks": [{"price": "0.41", "size": "10"}]}, 103)
        assert book_id == 1
        assert store.latest_book_for_asset("asset")["best_ask"] == 0.41
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    iterations = args.iterations if args.loop else 1
    n = 0
    while True:
        n += 1
        summary = collect_once(args)
        print(json.dumps({"generated_at_utc": iso_utc(), **summary}, ensure_ascii=False, sort_keys=True))
        if not args.loop or (iterations > 0 and n >= iterations):
            break
        time.sleep(max(args.interval_seconds, 1.0))


if __name__ == "__main__":
    main()

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS asset_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    ingest_ts INTEGER NOT NULL,
    best_bid REAL,
    best_ask REAL
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
"""


@dataclass(frozen=True)
class BookSnapshot:
    book_id: int
    asset: str
    ingest_ts: int
    best_bid: float | None
    best_ask: float | None


@dataclass(frozen=True)
class BookFill:
    ok: bool
    reason: str
    asset: str
    side: str
    target_ts: int
    book_id: int | None = None
    book_ts: int | None = None
    book_age_seconds: int | None = None
    avg_price: float | None = None
    shares: float = 0.0
    notional_usd: float = 0.0
    levels_used: int = 0
    best_price: float | None = None


class BookSnapshotStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)

    @classmethod
    def create_in_memory(cls) -> "BookSnapshotStore":
        return cls(sqlite3.connect(":memory:"))

    @classmethod
    def open_path(cls, db_path: str) -> "BookSnapshotStore":
        return cls(sqlite3.connect(db_path))

    def insert_snapshot(self, asset: str, ingest_ts: int, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> int:
        bids = sorted(list(bids), key=lambda x: x[0], reverse=True)
        asks = sorted(list(asks), key=lambda x: x[0])
        cur = self.conn.execute(
            "INSERT INTO asset_books(asset, ingest_ts, best_bid, best_ask) VALUES (?, ?, ?, ?)",
            (asset, ingest_ts, bids[0][0] if bids else None, asks[0][0] if asks else None),
        )
        book_id = int(cur.lastrowid)
        for side, levels in (("bid", bids), ("ask", asks)):
            for idx, (price, size) in enumerate(levels):
                self.conn.execute(
                    "INSERT INTO asset_book_levels(book_id, asset, ingest_ts, side, level_index, price, size) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (book_id, asset, ingest_ts, side, idx, price, size),
                )
        self.conn.commit()
        return book_id

    def nearest_snapshot(self, asset: str, target_ts: int) -> BookSnapshot | None:
        row = self.conn.execute(
            """
            SELECT id, asset, ingest_ts, best_bid, best_ask
            FROM asset_books
            WHERE asset = ?
            ORDER BY ABS(ingest_ts - ?) ASC, ingest_ts DESC, id DESC
            LIMIT 1
            """,
            (asset, target_ts),
        ).fetchone()
        if row is None:
            return None
        return BookSnapshot(int(row["id"]), str(row["asset"]), int(row["ingest_ts"]), row["best_bid"], row["best_ask"])

    def levels(self, book_id: int, side: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM asset_book_levels WHERE book_id = ? AND side = ? ORDER BY level_index ASC",
                (book_id, side),
            ).fetchall()
        )


def _vwap(levels: Iterable[sqlite3.Row], notional_usd: float) -> tuple[bool, float | None, float, int]:
    remaining = notional_usd
    shares = 0.0
    levels_used = 0
    for row in levels:
        price = float(row["price"])
        size = float(row["size"])
        if price <= 0 or size <= 0:
            continue
        capacity = price * size
        take = min(remaining, capacity)
        if take <= 0:
            continue
        shares += take / price
        remaining -= take
        levels_used += 1
        if remaining <= 1e-9:
            break
    if remaining > 1e-9 or shares <= 0:
        return False, None, shares, levels_used
    return True, notional_usd / shares, shares, levels_used


def vwap_fill_from_snapshot(store: BookSnapshotStore, asset: str, target_ts: int, side: str, notional_usd: float, max_book_age_seconds: int) -> BookFill:
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    book = store.nearest_snapshot(asset, target_ts)
    if book is None:
        return BookFill(False, "no_book", asset, side, target_ts)
    age = abs(book.ingest_ts - target_ts)
    if age > max_book_age_seconds:
        return BookFill(False, "no_fresh_book", asset, side, target_ts, book.book_id, book.ingest_ts, age)
    book_side = "ask" if side == "buy" else "bid"
    levels = store.levels(book.book_id, book_side)
    if not levels:
        return BookFill(False, "no_levels", asset, side, target_ts, book.book_id, book.ingest_ts, age)
    ok, avg_price, shares, levels_used = _vwap(levels, notional_usd)
    best_price = float(levels[0]["price"]) if levels else None
    if not ok or avg_price is None:
        return BookFill(False, "insufficient_depth", asset, side, target_ts, book.book_id, book.ingest_ts, age, None, shares, notional_usd, levels_used, best_price)
    return BookFill(True, "ok", asset, side, target_ts, book.book_id, book.ingest_ts, age, avg_price, shares, notional_usd, levels_used, best_price)

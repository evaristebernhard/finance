#!/usr/bin/env python3
"""Replay Polymarket CopyFlow signals with historical CLOB book VWAP.

This upgrades delayed-copy evaluation from next-trade proxy prices to book
snapshots collected by `polymarket_copyflow_collect.py`.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("output/polymarket_copyflow_forward/polymarket_copyflow.sqlite")


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


def iso_ts(ts: int | float | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS asset_books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    ingest_ts INTEGER NOT NULL,
    best_bid REAL,
    best_ask REAL,
    raw_json TEXT NOT NULL DEFAULT '{}'
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


def initialize_schema(db_path: Path | str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA_SQL)


def insert_test_book(
    db_path: Path | str,
    asset: str,
    snapshot_ts: int,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> int:
    initialize_schema(db_path)
    bids = sorted(bids, key=lambda x: x[0], reverse=True)
    asks = sorted(asks, key=lambda x: x[0])
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO asset_books(asset, ingest_ts, best_bid, best_ask, raw_json) VALUES (?, ?, ?, ?, ?)",
            (asset, snapshot_ts, bids[0][0] if bids else None, asks[0][0] if asks else None, "{}"),
        )
        book_id = int(cur.lastrowid)
        for side, levels in (("bid", bids), ("ask", asks)):
            for idx, (price, size) in enumerate(levels):
                conn.execute(
                    "INSERT INTO asset_book_levels(book_id, asset, ingest_ts, side, level_index, price, size) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (book_id, asset, snapshot_ts, side, idx, price, size),
                )
    return book_id


def nearest_book(conn: sqlite3.Connection, asset: str, target_ts: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *, ABS(ingest_ts - ?) AS age
        FROM asset_books
        WHERE asset = ?
        ORDER BY ABS(ingest_ts - ?) ASC, ingest_ts DESC, id DESC
        LIMIT 1
        """,
        (target_ts, asset, target_ts),
    ).fetchone()


def vwap_from_levels(levels: list[sqlite3.Row], notional_usd: float) -> tuple[bool, float | None, float, int]:
    remaining = notional_usd
    shares = 0.0
    levels_used = 0
    for row in levels:
        price = float(row["price"])
        size = float(row["size"])
        if price <= 0 or size <= 0:
            continue
        level_notional = price * size
        take_notional = min(remaining, level_notional)
        if take_notional <= 0:
            continue
        shares += take_notional / price
        remaining -= take_notional
        levels_used += 1
        if remaining <= 1e-9:
            break
    if remaining > 1e-9 or shares <= 0:
        return False, None, shares, levels_used
    return True, notional_usd / shares, shares, levels_used


def vwap_fill_from_book(
    db_path: Path | str,
    asset: str,
    target_ts: int,
    side: str,
    notional_usd: float,
    max_book_age_seconds: int,
) -> BookFill:
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    book_side = "ask" if side == "buy" else "bid"
    with connect(db_path) as conn:
        book = nearest_book(conn, asset, target_ts)
        if book is None:
            return BookFill(False, "no_book", asset, side, target_ts)
        age = abs(int(book["ingest_ts"]) - target_ts)
        if age > max_book_age_seconds:
            return BookFill(False, "no_fresh_book", asset, side, target_ts, int(book["id"]), int(book["ingest_ts"]), age)
        levels = conn.execute(
            "SELECT * FROM asset_book_levels WHERE book_id = ? AND side = ? ORDER BY level_index ASC",
            (int(book["id"]), book_side),
        ).fetchall()
        if not levels:
            return BookFill(False, "no_levels", asset, side, target_ts, int(book["id"]), int(book["ingest_ts"]), age)
        ok, avg_price, shares, levels_used = vwap_from_levels(levels, notional_usd)
        if not ok or avg_price is None:
            return BookFill(False, "insufficient_depth", asset, side, target_ts, int(book["id"]), int(book["ingest_ts"]), age, None, shares, notional_usd, levels_used, float(levels[0]["price"]))
        return BookFill(True, "ok", asset, side, target_ts, int(book["id"]), int(book["ingest_ts"]), age, avg_price, shares, notional_usd, levels_used, float(levels[0]["price"]))


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def replay_signals(
    db_path: Path | str,
    signals: list[dict[str, Any]],
    entry_delay_seconds: int,
    exit_delay_seconds: int,
    stake_usd: float,
    max_book_age_seconds: int,
    category: str = "all",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, row in enumerate(sorted(signals, key=lambda r: safe_int(r.get("timestamp")) or 0)):
        signal_ts = safe_int(row.get("timestamp"))
        asset = str(row.get("asset") or "")
        row_category = str(row.get("category") or "")
        if category != "all" and row_category != category:
            continue
        if signal_ts is None or not asset:
            skipped.append({"row_index": index, "reason": "missing_signal_ts_or_asset", **row})
            continue
        entry_ts = signal_ts + entry_delay_seconds
        exit_ts = signal_ts + exit_delay_seconds
        entry = vwap_fill_from_book(db_path, asset, entry_ts, "buy", stake_usd, max_book_age_seconds)
        if not entry.ok or entry.avg_price is None:
            skipped.append({"row_index": index, "reason": f"entry_{entry.reason}", "asset": asset, "signal_ts": signal_ts})
            continue
        exit_notional = entry.shares * entry.avg_price
        exit_fill = vwap_fill_from_book(db_path, asset, exit_ts, "sell", exit_notional, max_book_age_seconds)
        if not exit_fill.ok or exit_fill.avg_price is None:
            skipped.append({"row_index": index, "reason": f"exit_{exit_fill.reason}", "asset": asset, "signal_ts": signal_ts})
            continue
        pnl = entry.shares * (exit_fill.avg_price - entry.avg_price)
        ledger.append(
            {
                "row_index": index,
                "wallet": row.get("wallet", ""),
                "asset": asset,
                "condition_id": row.get("condition_id", ""),
                "category": row_category,
                "title": row.get("title", ""),
                "signal_ts": signal_ts,
                "signal_time_utc": iso_ts(signal_ts),
                "entry_ts": entry_ts,
                "entry_time_utc": iso_ts(entry_ts),
                "exit_ts": exit_ts,
                "exit_time_utc": iso_ts(exit_ts),
                "stake_usd": stake_usd,
                "shares": entry.shares,
                "entry_avg_price": entry.avg_price,
                "exit_avg_price": exit_fill.avg_price,
                "entry_book_id": entry.book_id,
                "exit_book_id": exit_fill.book_id,
                "entry_book_age_seconds": entry.book_age_seconds,
                "exit_book_age_seconds": exit_fill.book_age_seconds,
                "entry_levels_used": entry.levels_used,
                "exit_levels_used": exit_fill.levels_used,
                "pnl_usd": pnl,
                "roi_on_stake": pnl / stake_usd if stake_usd else 0.0,
            }
        )
    return ledger, skipped


def summarize(ledger: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [float(row["pnl_usd"]) for row in ledger]
    total = sum(pnl)
    wins = sum(1 for x in pnl if x > 0)
    deployed = sum(float(row.get("stake_usd") or 0.0) for row in ledger)
    gross_profit = sum(x for x in pnl if x > 0)
    gross_loss = -sum(x for x in pnl if x < 0)
    skip_counts: dict[str, int] = {}
    for row in skipped:
        reason = str(row.get("reason") or "unknown")
        skip_counts[reason] = skip_counts.get(reason, 0) + 1
    return {
        "closed_paper_trades": len(ledger),
        "skipped_signals": len(skipped),
        "deployed_notional_usd": deployed,
        "net_pnl_usd": total,
        "roi_on_deployed": total / deployed if deployed else 0.0,
        "win_rate": wins / len(ledger) if ledger else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "skip_counts": skip_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay CopyFlow signals with historical CLOB VWAP snapshots.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--signals-csv", type=Path, default=Path("output/polymarket_wallet_factor_probe_deep_20260608/trade_edges.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/polymarket_copyflow_book_replay"))
    parser.add_argument("--entry-delay-seconds", type=int, default=30)
    parser.add_argument("--exit-delay-seconds", type=int, default=300)
    parser.add_argument("--stake-usd", type=float, default=100.0)
    parser.add_argument("--max-book-age-seconds", type=int, default=30)
    parser.add_argument("--category", default="all")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "test.sqlite"
        initialize_schema(db)
        insert_test_book(db, "asset", 1030, bids=[(0.55, 1000)], asks=[(0.50, 1000)])
        fill = vwap_fill_from_book(db, "asset", 1030, "buy", 100, 1)
        assert fill.ok and fill.avg_price == 0.50
        ledger, skipped = replay_signals(db, [{"timestamp": "1000", "asset": "asset"}], 30, 30, 100, 1)
        assert len(ledger) == 1 and not skipped
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    db_path = args.db_path if args.db_path.is_absolute() else REPO_ROOT / args.db_path
    signals_csv = args.signals_csv if args.signals_csv.is_absolute() else REPO_ROOT / args.signals_csv
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    signals = read_csv_rows(signals_csv)
    ledger, skipped = replay_signals(
        db_path,
        signals,
        args.entry_delay_seconds,
        args.exit_delay_seconds,
        args.stake_usd,
        args.max_book_age_seconds,
        args.category,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "paper_ledger.csv", ledger)
    write_csv(output_dir / "skipped_signals.csv", skipped)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "signals_csv": str(signals_csv),
        "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        **summarize(ledger, skipped),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()

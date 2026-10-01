from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scripts.polymarket.execution.book_store import BookSnapshotStore, vwap_fill_from_snapshot


def iso_ts(ts: int | float | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()


def replay_signals_with_store(
    store: BookSnapshotStore,
    signals: list[dict[str, Any]],
    entry_delay_seconds: int,
    exit_delay_seconds: int,
    stake_usd: float,
    max_book_age_seconds: int,
    category: str = "all",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    rows = sorted(signals, key=lambda r: int(float(str(r.get("timestamp") or 0))))
    for index, row in enumerate(rows):
        signal_ts = int(float(str(row.get("timestamp") or 0))) if row.get("timestamp") not in (None, "") else None
        asset = str(row.get("asset") or "")
        row_category = str(row.get("category") or "")
        if category != "all" and row_category != category:
            continue
        if signal_ts is None or not asset:
            skipped.append({"row_index": index, "reason": "missing_signal_ts_or_asset", **row})
            continue
        entry_ts = signal_ts + entry_delay_seconds
        exit_ts = signal_ts + exit_delay_seconds
        entry = vwap_fill_from_snapshot(store, asset, entry_ts, "buy", stake_usd, max_book_age_seconds)
        if not entry.ok or entry.avg_price is None:
            skipped.append({"row_index": index, "reason": f"entry_{entry.reason}", "asset": asset, "signal_ts": signal_ts})
            continue
        exit_fill = vwap_fill_from_snapshot(store, asset, exit_ts, "sell", entry.shares * entry.avg_price, max_book_age_seconds)
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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.polymarket.execution.book_store import BookSnapshotStore, vwap_fill_from_snapshot


def test_book_store_persists_snapshots_and_finds_nearest():
    store = BookSnapshotStore.create_in_memory()
    store.insert_snapshot("asset1", 1000, bids=[(0.49, 100.0)], asks=[(0.50, 100.0), (0.51, 100.0)])
    store.insert_snapshot("asset1", 1200, bids=[(0.55, 100.0)], asks=[(0.56, 100.0)])

    snap = store.nearest_snapshot("asset1", 1180)
    assert snap is not None
    assert snap.ingest_ts == 1200
    assert snap.best_bid == 0.55
    assert snap.best_ask == 0.56


def test_vwap_fill_from_snapshot_consumes_depth_and_rejects_stale_book():
    store = BookSnapshotStore.create_in_memory()
    store.insert_snapshot("asset1", 1000, bids=[(0.49, 100.0)], asks=[(0.50, 100.0), (0.51, 100.0)])

    fill = vwap_fill_from_snapshot(store, "asset1", 1000, "buy", 50.0, max_book_age_seconds=5)
    assert fill.ok is True
    assert round(fill.avg_price, 6) == 0.50
    assert fill.levels_used == 1

    stale = vwap_fill_from_snapshot(store, "asset1", 2000, "buy", 50.0, max_book_age_seconds=5)
    assert stale.ok is False
    assert stale.reason == "no_fresh_book"

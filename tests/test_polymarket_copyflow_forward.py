import importlib.util
import sys
from pathlib import Path


def load_script(name: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_collector_dedupes_trades_and_persists_book_snapshots(tmp_path):
    collector = load_script("polymarket_copyflow_collect")
    db_path = tmp_path / "copyflow.sqlite"
    db = collector.CopyflowStore(db_path)
    db.initialize()

    trade = {
        "transactionHash": "tx1",
        "proxyWallet": "0xABC",
        "asset": "asset1",
        "conditionId": "cond1",
        "side": "BUY",
        "price": "0.42",
        "size": "10",
        "timestamp": "1700000000",
        "title": "Bitcoin Up or Down",
        "slug": "btc-up-down",
        "eventSlug": "btc-event",
        "outcome": "Up",
    }
    inserted_1 = db.upsert_trades([trade], ingest_ts=1700000005, source="recent")
    inserted_2 = db.upsert_trades([dict(trade)], ingest_ts=1700000006, source="wallet_activity")

    assert inserted_1 == 1
    assert inserted_2 == 0
    assert db.count_rows("trades_raw") == 1

    book = {
        "market": "asset1",
        "asset_id": "asset1",
        "bids": [{"price": "0.40", "size": "50"}],
        "asks": [{"price": "0.43", "size": "30"}, {"price": "0.45", "size": "80"}],
    }
    book_id = db.insert_book_snapshot("asset1", book, ingest_ts=1700000010)
    assert book_id > 0
    assert db.count_rows("asset_books") == 1
    assert db.count_rows("asset_book_levels") == 3

    row = db.latest_book_for_asset("asset1")
    assert row is not None
    assert row["best_ask"] == 0.43
    assert row["best_bid"] == 0.40


def test_book_replay_uses_nearest_snapshot_and_ask_bid_vwap(tmp_path):
    replay = load_script("polymarket_copyflow_book_replay")
    db_path = tmp_path / "copyflow.sqlite"
    replay.initialize_schema(db_path)

    replay.insert_test_book(
        db_path,
        asset="asset1",
        snapshot_ts=1030,
        bids=[(0.52, 100.0), (0.51, 100.0)],
        asks=[(0.55, 100.0), (0.56, 100.0)],
    )
    replay.insert_test_book(
        db_path,
        asset="asset1",
        snapshot_ts=1300,
        bids=[(0.60, 50.0), (0.58, 200.0)],
        asks=[(0.62, 100.0)],
    )

    entry = replay.vwap_fill_from_book(db_path, "asset1", target_ts=1030, side="buy", notional_usd=110.0, max_book_age_seconds=5)
    exit_ = replay.vwap_fill_from_book(db_path, "asset1", target_ts=1300, side="sell", notional_usd=110.0, max_book_age_seconds=5)

    assert entry.ok is True
    assert round(entry.avg_price, 6) == round(110.0 / (55.0 / 0.55 + 55.0 / 0.56), 6)
    assert exit_.ok is True
    assert round(exit_.avg_price, 6) == round(110.0 / (30.0 / 0.60 + 80.0 / 0.58), 6)

    missing = replay.vwap_fill_from_book(db_path, "asset1", target_ts=2000, side="buy", notional_usd=10.0, max_book_age_seconds=5)
    assert missing.ok is False
    assert missing.reason == "no_fresh_book"


def test_book_replay_converts_copyflow_signal_to_closed_ledger(tmp_path):
    replay = load_script("polymarket_copyflow_book_replay")
    db_path = tmp_path / "copyflow.sqlite"
    replay.initialize_schema(db_path)
    replay.insert_test_book(db_path, "asset1", 1030, bids=[(0.49, 1000)], asks=[(0.50, 1000)])
    replay.insert_test_book(db_path, "asset1", 1300, bids=[(0.57, 1000)], asks=[(0.58, 1000)])

    signals = [
        {
            "timestamp": "1000",
            "wallet": "0xa",
            "asset": "asset1",
            "condition_id": "cond1",
            "category": "crypto",
            "title": "Synthetic",
            "entry_price": "0.48",
            "edge_30s_cents": "1.0",
            "edge_300s_cents": "2.0",
        }
    ]
    ledger, skipped = replay.replay_signals(
        db_path,
        signals,
        entry_delay_seconds=30,
        exit_delay_seconds=300,
        stake_usd=100.0,
        max_book_age_seconds=5,
    )

    assert not skipped
    assert len(ledger) == 1
    assert ledger[0]["entry_avg_price"] == 0.50
    assert ledger[0]["exit_avg_price"] == 0.57
    assert round(ledger[0]["pnl_usd"], 6) == 14.0

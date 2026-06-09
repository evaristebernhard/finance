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


def row(slug, outcome, lookback, pnl, edge, prob, avg=0.5):
    return {
        "event_id": "e1",
        "event_title": "Bitcoin above ___",
        "event_slug": "btc-above",
        "market_id": slug + "-m",
        "question": "Will Bitcoin be above K?",
        "slug": slug,
        "symbol": "BTCUSDT",
        "kind": "above_close",
        "outcome": outcome,
        "token_id": slug + outcome,
        "settle_time_utc": "2026-06-10T16:00:00+00:00",
        "minutes_to_settle": "120",
        "binance_price": "63000",
        "model_threshold": "64000",
        "stdev_logret_1m": "0.001",
        "vol_lookback_minutes": str(lookback),
        "model_prob": str(prob),
        "fee_rate": "0.07",
        "target_notional_usd": "100",
        "book_ok": "True",
        "best_ask": str(avg),
        "avg_price": str(avg),
        "shares": str(100 / avg),
        "fee_usd": "0.5",
        "available_notional_usd": "10000",
        "expected_profit_usd": str(pnl),
        "roi_on_cost": str(pnl / 100),
        "edge_cents": str(edge),
        "candidate": "True",
        "book_error": "",
    }


def test_ensemble_requires_all_lookbacks_positive_and_reports_robust_min():
    ens = load_script("polymarket_binance_close_ensemble")
    rows = [
        row("btc-64k", "No", 60, 9.0, 6.0, 0.80),
        row("btc-64k", "No", 180, 2.0, 1.5, 0.74),
        row("btc-64k", "No", 360, 1.0, 0.7, 0.71),
        row("btc-62k", "Yes", 60, 6.0, 5.0, 0.96),
        row("btc-62k", "Yes", 180, 1.0, 0.8, 0.92),
        row("btc-62k", "Yes", 360, -1.0, -0.5, 0.89),
    ]

    out = ens.build_ensemble_rows(rows, required_lookbacks=[60, 180, 360], min_robust_pnl=0.5, min_robust_edge_cents=0.25)

    assert len(out) == 2
    robust = {r["slug"]: r for r in out}
    assert robust["btc-64k"]["all_lookbacks_positive"] is True
    assert robust["btc-64k"]["ensemble_candidate"] is True
    assert robust["btc-64k"]["robust_min_expected_profit_usd"] == 1.0
    assert robust["btc-64k"]["robust_min_edge_cents"] == 0.7
    assert robust["btc-62k"]["all_lookbacks_positive"] is False
    assert robust["btc-62k"]["ensemble_candidate"] is False


def test_ensemble_rejects_missing_lookback_and_extreme_probability_when_requested():
    ens = load_script("polymarket_binance_close_ensemble")
    rows = [
        row("btc-58k", "Yes", 60, 1.0, 1.0, 0.9999),
        row("btc-58k", "Yes", 180, 1.0, 1.0, 0.9998),
        # missing 360
        row("eth-1600", "Yes", 60, 1.0, 1.0, 0.9999),
        row("eth-1600", "Yes", 180, 1.0, 1.0, 0.9998),
        row("eth-1600", "Yes", 360, 1.0, 1.0, 0.9997),
    ]

    out = ens.build_ensemble_rows(
        rows,
        required_lookbacks=[60, 180, 360],
        min_robust_pnl=0.5,
        min_robust_edge_cents=0.25,
        min_probability=0.01,
        max_probability=0.99,
    )
    by_slug = {r["slug"]: r for r in out}

    assert by_slug["btc-58k"]["has_all_required_lookbacks"] is False
    assert by_slug["btc-58k"]["ensemble_candidate"] is False
    assert by_slug["eth-1600"]["has_all_required_lookbacks"] is True
    assert by_slug["eth-1600"]["probability_extreme"] is True
    assert by_slug["eth-1600"]["ensemble_candidate"] is False

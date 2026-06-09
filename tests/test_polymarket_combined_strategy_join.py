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


def ev_row(token="tok1", candidate=True):
    return {
        "event_id": "e1",
        "event_title": "Bitcoin above ___",
        "slug": "btc-64k",
        "question": "Will Bitcoin be above 64000?",
        "symbol": "BTCUSDT",
        "outcome": "No",
        "token_id": token,
        "ensemble_candidate": str(candidate),
        "robust_min_expected_profit_usd": "4.0",
        "robust_min_edge_cents": "3.0",
        "min_model_prob": "0.76",
        "max_model_prob": "0.82",
        "avg_price": "0.72",
        "available_notional_usd": "10000",
        "minutes_to_settle": "500",
    }


def follow_row(token="tok1", outcome="No", score=12.0):
    return {
        "timestamp_utc": "2026-06-09T07:00:00+00:00",
        "wallet": "0xabc",
        "category": "crypto",
        "outcome": outcome,
        "asset": token,
        "wallet_copy_edge_5m_cents": "4.5",
        "wallet_delay_robust_edge_cents": "2.0",
        "wallet_copyable_score": "8.0",
        "market_suitability_score": "0.7",
        "liquidity_adjusted_copy_edge": "3.0",
        "follow_score": str(score),
        "one_hit_wonder_penalty": "0.3",
        "spread_cents": "1.0",
        "ask_depth_usd": "5000",
        "crowd_exit_risk": "0.2",
        "rule_ambiguity_score": "1.0",
        "trade_proxy_edge_300s_cents": "1.5",
    }


def test_combined_candidates_join_ev_wallet_momentum_microstructure():
    mod = load_script("polymarket_combined_strategy_join")
    rows = mod.build_combined_candidates(
        ev_rows=[ev_row()],
        follow_rows=[follow_row(), follow_row(score=3.0)],
        min_combined_score=0,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["token_id"] == "tok1"
    assert row["smart_flow_count"] == 2
    assert row["smart_flow_same_side_count"] == 2
    assert row["smart_flow_score"] > 0
    assert row["momentum_score"] > 0
    assert row["microstructure_score"] > 0
    assert row["combined_score"] > row["ev_score"]
    assert row["reject_reason"] == ""


def test_combined_candidates_penalize_opposite_flow_and_non_ev():
    mod = load_script("polymarket_combined_strategy_join")
    rows = mod.build_combined_candidates(
        ev_rows=[ev_row("tok1", candidate=True), ev_row("tok2", candidate=False)],
        follow_rows=[follow_row("tok1", outcome="Yes", score=20.0), follow_row("tok2", outcome="No", score=20.0)],
        min_combined_score=0,
    )
    by_token = {r["token_id"]: r for r in rows}

    assert by_token["tok1"]["smart_flow_opposite_count"] == 1
    assert by_token["tok1"]["smart_flow_score"] < 0
    assert "opposite_smart_flow" in by_token["tok1"]["reject_reason"]
    assert by_token["tok2"]["ensemble_candidate"] is False
    assert "not_ensemble_candidate" in by_token["tok2"]["reject_reason"]

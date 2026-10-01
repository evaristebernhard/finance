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


def ev_row(token="tok-threshold", candidate=True):
    return {
        "event_id": "e1",
        "event_title": "Bitcoin above ___",
        "slug": "btc-64k",
        "question": "Will the price of Bitcoin be above $64,000 on June 9?",
        "symbol": "BTCUSDT",
        "outcome": "Yes",
        "token_id": token,
        "ensemble_candidate": str(candidate),
        "robust_min_expected_profit_usd": "4.0",
        "robust_min_edge_cents": "3.0",
        "min_model_prob": "0.76",
        "max_model_prob": "0.82",
        "avg_price": "0.72",
        "available_notional_usd": "10000",
        "minutes_to_settle": "500",
        "claim_family": "threshold",
        "claim_id": "BTCUSDT:threshold:64000:yes",
        "direction": "bullish",
        "settle_time_utc": "2026-06-09T16:00:00+00:00",
    }


def follow_row(token="tok-updown", outcome="Up", score=12.0):
    return {
        "timestamp_utc": "2026-06-09T07:00:00+00:00",
        "wallet": "0xabc",
        "category": "crypto",
        "outcome": outcome,
        "asset": token,
        "question": "Bitcoin Up or Down - June 9, 3:20PM-3:25PM ET",
        "underlying": "BTCUSDT",
        "claim_family": "up_down_window",
        "claim_id": "BTCUSDT:updown:2026-06-09T19:20:00Z:up",
        "direction": "bullish",
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


def test_combined_candidates_support_claim_join_mode():
    mod = load_script("polymarket_combined_strategy_join")
    rows = mod.build_combined_candidates(
        ev_rows=[ev_row()],
        follow_rows=[follow_row()],
        min_combined_score=0,
        join_mode="claim",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["join_mode"] == "claim"
    assert row["smart_flow_same_side_count"] == 1
    assert row["smart_flow_score"] > 0
    assert row["reject_reason"] == ""

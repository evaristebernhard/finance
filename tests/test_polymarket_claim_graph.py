import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.polymarket.claims.claim_graph import build_claim_edges
from scripts.polymarket.claims.claim_mapper import map_market_to_claim


def test_claim_mapper_parses_threshold_market():
    claim = map_market_to_claim(
        {
            "market_id": "m1",
            "condition_id": "c1",
            "token_id": "t1",
            "question": "Will the price of Bitcoin be above $64,000 on June 9?",
            "description": 'Resolves based on the final "close" price on Binance at settlement.',
            "endDate": "2026-06-09T16:00:00Z",
            "outcome": "Yes",
        }
    )

    assert claim["family"] == "threshold"
    assert claim["underlying"] == "BTCUSDT"
    assert claim["direction"] == "bullish"
    assert claim["threshold"] == 64000.0
    assert claim["claim_id"]


def test_claim_mapper_parses_up_down_market():
    claim = map_market_to_claim(
        {
            "market_id": "m2",
            "condition_id": "c2",
            "token_id": "t2",
            "question": "Bitcoin Up or Down - June 9, 3:20PM-3:25PM ET",
            "description": "A short-horizon Up or Down market on Bitcoin.",
            "endDate": "2026-06-09T19:25:00Z",
            "outcome": "Up",
        }
    )

    assert claim["family"] == "up_down_window"
    assert claim["underlying"] == "BTCUSDT"
    assert claim["direction"] == "bullish"


def test_claim_graph_builds_threshold_implication_and_directional_support():
    threshold_low = map_market_to_claim(
        {
            "market_id": "m1",
            "condition_id": "c1",
            "token_id": "t1",
            "question": "Will the price of Bitcoin be above $64,000 on June 9?",
            "description": 'Resolves based on the final "close" price on Binance at settlement.',
            "endDate": "2026-06-09T16:00:00Z",
            "outcome": "Yes",
        }
    )
    threshold_high = map_market_to_claim(
        {
            "market_id": "m2",
            "condition_id": "c2",
            "token_id": "t2",
            "question": "Will the price of Bitcoin be above $66,000 on June 9?",
            "description": 'Resolves based on the final "close" price on Binance at settlement.',
            "endDate": "2026-06-09T16:00:00Z",
            "outcome": "Yes",
        }
    )
    up_only = map_market_to_claim(
        {
            "market_id": "m3",
            "condition_id": "c3",
            "token_id": "t3",
            "question": "Bitcoin Up or Down - June 9, 3:20PM-3:25PM ET",
            "description": "A short-horizon Up or Down market on Bitcoin.",
            "endDate": "2026-06-09T19:25:00Z",
            "outcome": "Up",
        }
    )

    edges = build_claim_edges([threshold_low, threshold_high, up_only])

    implication = [e for e in edges if e["edge_type"] == "implies"]
    support = [e for e in edges if e["edge_type"] == "directional_support"]

    assert any(
        e["src_claim_id"] == threshold_high["claim_id"]
        and e["dst_claim_id"] == threshold_low["claim_id"]
        for e in implication
    )
    assert any(
        e["src_claim_id"] == up_only["claim_id"]
        and e["dst_claim_id"] == threshold_low["claim_id"]
        for e in support
    )

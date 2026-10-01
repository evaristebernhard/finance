from __future__ import annotations

from typing import Any

from scripts.polymarket.claims.claim_mapper import map_market_to_claim


def flow_matches_ev_claim(ev_row: dict[str, Any], flow_row: dict[str, Any], join_mode: str = "claim") -> bool:
    if join_mode == "token":
        return str(flow_row.get("asset") or flow_row.get("token_id") or "") == str(ev_row.get("token_id") or "")

    ev_claim = map_market_to_claim(ev_row)
    flow_claim = map_market_to_claim(flow_row)
    if ev_claim["claim_id"] == flow_claim["claim_id"]:
        return True
    if ev_claim.get("underlying") != flow_claim.get("underlying"):
        return False
    if ev_claim.get("direction") != flow_claim.get("direction"):
        return False
    return True


def group_follow_rows_for_ev(ev_rows: list[dict[str, Any]], follow_rows: list[dict[str, Any]], join_mode: str = "claim") -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ev in ev_rows:
        key = str(ev.get("token_id") or ev.get("claim_id") or "")
        grouped[key] = [row for row in follow_rows if flow_matches_ev_claim(ev, row, join_mode=join_mode)]
    return grouped
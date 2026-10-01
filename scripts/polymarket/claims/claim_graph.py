from __future__ import annotations

from typing import Any


def _edge(src: dict[str, Any], dst: dict[str, Any], edge_type: str, weight: float, strict: bool, reason: str) -> dict[str, Any]:
    return {
        "src_claim_id": src.get("claim_id", ""),
        "dst_claim_id": dst.get("claim_id", ""),
        "edge_type": edge_type,
        "weight": weight,
        "strict": strict,
        "reason": reason,
    }


def build_claim_edges(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for src in claims:
        for dst in claims:
            if src is dst:
                continue
            if src.get("underlying") != dst.get("underlying"):
                continue

            if (
                src.get("family") == "threshold"
                and dst.get("family") == "threshold"
                and src.get("direction") == dst.get("direction") == "bullish"
            ):
                src_threshold = src.get("threshold")
                dst_threshold = dst.get("threshold")
                if isinstance(src_threshold, (int, float)) and isinstance(dst_threshold, (int, float)) and src_threshold > dst_threshold:
                    edges.append(_edge(src, dst, "implies", 1.0, True, "higher bullish threshold implies lower bullish threshold"))

            if (
                src.get("family") == "up_down_window"
                and dst.get("direction") == src.get("direction")
                and dst.get("family") == "threshold"
            ):
                edges.append(_edge(src, dst, "directional_support", 0.35, False, "short-horizon directional flow supports same-direction threshold claim"))
    return edges

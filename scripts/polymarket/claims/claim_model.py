from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimNode:
    claim_id: str
    underlying: str
    family: str
    direction: str
    token_id: str = ""
    market_id: str = ""
    condition_id: str = ""


@dataclass(frozen=True)
class ClaimEdge:
    src_claim_id: str
    dst_claim_id: str
    edge_type: str
    weight: float
    strict: bool
    reason: str

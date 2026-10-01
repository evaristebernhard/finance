from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any


SYMBOL_BY_TEXT = {
    "bitcoin": "BTCUSDT",
    "btc": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "eth": "ETHUSDT",
    "solana": "SOLUSDT",
    "sol": "SOLUSDT",
    "xrp": "XRPUSDT",
    "dogecoin": "DOGEUSDT",
    "doge": "DOGEUSDT",
}


def infer_underlying(*texts: str) -> str:
    blob = " ".join(texts).lower()
    for key, symbol in SYMBOL_BY_TEXT.items():
        if re.search(rf"\b{re.escape(key)}\b", blob):
            return symbol
    return "UNKNOWN"


def parse_ts(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _stable_claim_id(parts: list[str]) -> str:
    clean = [str(x).strip().lower().replace(" ", "_") for x in parts if str(x).strip()]
    text = ":".join(clean)
    if len(text) <= 120:
        return text
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return text[:100] + ":" + digest


def map_market_to_claim(row: dict[str, Any]) -> dict[str, Any]:
    question = str(row.get("question") or row.get("title") or "")
    description = str(row.get("description") or "")
    outcome = str(row.get("outcome") or "")
    underlying = str(row.get("underlying") or infer_underlying(question, description))
    settle_ts = parse_ts(str(row.get("settle_time_utc") or row.get("endDate") or row.get("end_date") or ""))
    ql = question.lower()
    ol = outcome.lower()

    family = "binary_generic"
    direction = "neutral"
    threshold = None
    lower_bound = None
    upper_bound = None

    threshold_match = re.search(r"above\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?)", ql)
    if threshold_match:
        family = "threshold"
        threshold = float(threshold_match.group(1).replace(",", ""))
        direction = "bullish" if ol in {"yes", "up"} else "bearish"
    elif "up or down" in ql:
        family = "up_down_window"
        if ol in {"up", "yes"}:
            direction = "bullish"
        elif ol in {"down", "no"}:
            direction = "bearish"
        else:
            direction = "neutral"
    elif "between" in ql:
        between = re.search(r"between\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?)\s+and\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?)", ql)
        if between:
            family = "range_bucket"
            lower_bound = float(between.group(1).replace(",", ""))
            upper_bound = float(between.group(2).replace(",", ""))

    claim_id = str(row.get("claim_id") or "")
    if not claim_id:
        key_parts = [underlying, family, outcome]
        if threshold is not None:
            key_parts.append(str(int(threshold) if threshold.is_integer() else threshold))
        if lower_bound is not None:
            key_parts.append(str(lower_bound))
        if upper_bound is not None:
            key_parts.append(str(upper_bound))
        if settle_ts is not None:
            key_parts.append(str(settle_ts))
        claim_id = _stable_claim_id(key_parts)

    return {
        "claim_id": claim_id,
        "market_id": str(row.get("market_id") or ""),
        "condition_id": str(row.get("condition_id") or ""),
        "token_id": str(row.get("token_id") or row.get("asset") or ""),
        "question": question,
        "description": description,
        "outcome": outcome,
        "underlying": underlying,
        "family": family,
        "claim_family": family,
        "direction": direction,
        "settle_ts": settle_ts,
        "threshold": threshold,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "rule_ambiguity_score": float(row.get("rule_ambiguity_score") or 0.0),
        "mapped_at_utc": datetime.now(timezone.utc).isoformat(),
    }

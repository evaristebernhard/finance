"""Read-only Polymarket NegRisk basket arbitrage scanner.

The scanner looks for multi-outcome events where exactly one YES outcome should
resolve. It estimates the cost of buying one YES share in every outcome using
live CLOB asks, includes the current Polymarket taker-fee formula, and reports
whether an all-YES basket has positive fee-adjusted edge.

It never signs, submits, or prepares live orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
REPO_ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-12


TAKER_FEE_RATES = {
    "crypto": 0.07,
    "sports": 0.03,
    "finance": 0.04,
    "politics": 0.04,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "mentions": 0.04,
    "tech": 0.04,
    "geopolitics": 0.0,
    "other": 0.05,
}


@dataclass
class BasketLeg:
    market_id: str
    condition_id: str
    token_id: str
    question: str
    outcome_label: str
    gamma_yes_price: float | None
    gamma_best_ask: float | None
    fee_rate: float
    book_best_ask: float | None = None
    target_avg_price: float | None = None
    target_cost_usd: float | None = None
    target_fee_usd: float | None = None
    target_ok: bool = False
    available_shares: float = 0.0
    book_error: str = ""


@dataclass
class BasketEvent:
    event_id: str
    title: str
    slug: str
    category: str
    fee_rate: float
    neg_risk_evidence: str
    detail_market_count: int = 0
    has_other_market: bool = False
    has_active_other_leg: bool = False
    executable_exhaustive: bool = False
    legs: list[BasketLeg] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/polymarket_negrisk_basket_arbitrage_scan"),
    )
    parser.add_argument("--event-limit", type=int, default=80)
    parser.add_argument("--candidate-limit", type=int, default=30)
    parser.add_argument("--book-event-limit", type=int, default=10)
    parser.add_argument("--min-markets", type=int, default=3)
    parser.add_argument("--max-markets-per-event", type=int, default=100)
    parser.add_argument("--target-payout-usd", type=float, default=100.0)
    parser.add_argument("--min-gamma-edge-cents", type=float, default=-10.0)
    parser.add_argument("--min-book-edge-cents", type=float, default=0.0)
    parser.add_argument("--include-heuristic-events", action="store_true")
    parser.add_argument("--query", default="")
    parser.add_argument("--http-timeout", type=float, default=20.0)
    parser.add_argument("--sleep-ms", type=int, default=60)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def http_get_json(base: str, path: str, params: dict[str, Any] | None, timeout: float) -> Any:
    query = ""
    if params:
        query = "?" + urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    req = Request(
        base.rstrip("/") + "/" + path.lstrip("/") + query,
        headers={"User-Agent": "finance-chain-polymarket-negrisk-scan/0.1"},
        method="GET",
    )
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable http_get_json state")


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def classify_category(*texts: str) -> str:
    text = " ".join(t for t in texts if t).lower()
    if any(x in text for x in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol ", "xrp", "crypto", "binance"]):
        return "crypto"
    if any(x in text for x in ["world cup", "nba", "nfl", "mlb", "ufc", "tennis", "fifa", "sports", "match", "game"]):
        return "sports"
    if any(x in text for x in ["election", "trump", "biden", "senate", "congress", "president", "politics"]):
        return "politics"
    if any(x in text for x in ["iran", "israel", "russia", "ukraine", "war", "ceasefire", "missile", "geopolitics"]):
        return "geopolitics"
    if any(x in text for x in ["fed", "cpi", "gdp", "unemployment", "inflation", "rate cut", "economy"]):
        return "economics"
    if any(x in text for x in ["stock", "nasdaq", "s&p", "spx", "treasury", "finance"]):
        return "finance"
    if any(x in text for x in ["rain", "temperature", "weather", "hurricane", "snow"]):
        return "weather"
    if any(x in text for x in ["openai", "apple", "google", "nvidia", "tesla", "ai", "tech"]):
        return "tech"
    if any(x in text for x in ["movie", "grammy", "oscar", "album", "culture"]):
        return "culture"
    if "mentions" in text:
        return "mentions"
    return "other"


def is_likely_exhaustive_event(event: dict[str, Any], markets: list[dict[str, Any]]) -> tuple[bool, str]:
    if event.get("negRisk") is True or event.get("enableNegRisk") is True:
        return True, "event_negRisk"
    if markets and sum(1 for m in markets if m.get("negRisk") is True) >= max(1, len(markets) // 2):
        return True, "market_negRisk_majority"
    text = " ".join(
        [
            str(event.get("title") or ""),
            str(event.get("slug") or ""),
            str(event.get("description") or ""),
            " ".join(str(m.get("groupItemTitle") or m.get("question") or "") for m in markets[:20]),
        ]
    ).lower()
    heuristic_needles = [
        "winner",
        "nominee",
        "nomination",
        "price of",
        "price?",
        "what price",
        "which team",
        "who will win",
        "between",
        "greater than",
        "less than",
        ">",
        "<",
    ]
    if any(needle in text for needle in heuristic_needles):
        return True, "heuristic_exhaustive_candidate"
    return False, "not_exhaustive"


def is_other_market(market: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(market.get("groupItemTitle") or ""),
            str(market.get("question") or ""),
            str(market.get("slug") or ""),
        ]
    ).lower()
    return text.strip() == "other" or "another person" in text or "any other" in text


def taker_fee_for_fill(shares: float, price: float, fee_rate: float) -> float:
    return shares * fee_rate * price * (1.0 - price)


def sorted_asks(levels: list[dict[str, Any]]) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for level in levels:
        price = safe_float(level.get("price"))
        size = safe_float(level.get("size"))
        if price is None or size is None or price <= 0 or size <= 0:
            continue
        out.append({"price": price, "size": size})
    out.sort(key=lambda x: x["price"])
    return out


def consume_asks_for_shares(
    levels: list[dict[str, Any]],
    shares: float,
    fee_rate: float,
) -> dict[str, float | bool | None]:
    remaining = shares
    cost = 0.0
    fee = 0.0
    available = 0.0
    best_ask = None
    for level in sorted_asks(levels):
        if best_ask is None:
            best_ask = level["price"]
        available += level["size"]
        if remaining <= EPS:
            continue
        take = min(remaining, level["size"])
        cost += take * level["price"]
        fee += taker_fee_for_fill(take, level["price"], fee_rate)
        remaining -= take
    ok = remaining <= EPS
    avg = cost / shares if ok and shares > EPS else None
    return {
        "ok": ok,
        "best_ask": best_ask,
        "available_shares": available,
        "avg_price": avg,
        "cost_usd": cost if ok else None,
        "fee_usd": fee if ok else None,
    }


def gamma_yes_price(market: dict[str, Any]) -> float | None:
    best_ask = safe_float(market.get("bestAsk"))
    if best_ask is not None and 0.0 < best_ask < 1.0:
        return best_ask
    outcome_prices = parse_json_list(market.get("outcomePrices"))
    if outcome_prices:
        price = safe_float(outcome_prices[0])
        if price is not None and 0.0 <= price <= 1.0:
            return price
    return None


def parse_fee_schedule(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def market_fee_rate(market: dict[str, Any], fallback_fee_rate: float) -> float:
    if market.get("feesEnabled") is False:
        return 0.0
    schedule = parse_fee_schedule(market.get("feeSchedule"))
    schedule_rate = safe_float(schedule.get("rate"))
    if schedule_rate is not None and schedule_rate >= 0:
        return schedule_rate
    return fallback_fee_rate


def market_to_leg(market: dict[str, Any], fallback_fee_rate: float) -> BasketLeg | None:
    if market.get("closed") is True or market.get("active") is False:
        return None
    if market.get("enableOrderBook") is False:
        return None
    condition_id = str(market.get("conditionId") or "").lower()
    market_id = str(market.get("id") or condition_id)
    token_ids = [str(x) for x in parse_json_list(market.get("clobTokenIds"))]
    if not condition_id or not token_ids:
        return None
    price = gamma_yes_price(market)
    return BasketLeg(
        market_id=market_id,
        condition_id=condition_id,
        token_id=token_ids[0],
        question=str(market.get("question") or ""),
        outcome_label=str(market.get("groupItemTitle") or market.get("question") or ""),
        gamma_yes_price=price,
        gamma_best_ask=safe_float(market.get("bestAsk")),
        fee_rate=market_fee_rate(market, fallback_fee_rate),
    )


def fetch_events(limit: int, timeout: float) -> list[dict[str, Any]]:
    return http_get_json(
        GAMMA_BASE,
        "/events",
        {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        },
        timeout,
    )


def fetch_event_detail(event: dict[str, Any], timeout: float) -> dict[str, Any]:
    slug = str(event.get("slug") or "")
    if not slug:
        return event
    try:
        rows = http_get_json(GAMMA_BASE, "/events", {"slug": slug}, timeout)
    except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError):
        return event
    if isinstance(rows, list) and rows:
        detail = rows[0]
        if isinstance(detail, dict) and len(detail.get("markets") or []) >= len(event.get("markets") or []):
            return detail
    return event


def build_candidate_events(args: argparse.Namespace) -> list[BasketEvent]:
    events = fetch_events(args.event_limit, args.http_timeout)
    candidates: list[BasketEvent] = []
    query = args.query.lower().strip()
    for event in events:
        markets = [m for m in (event.get("markets") or []) if isinstance(m, dict)]
        if query:
            blob = " ".join([str(event.get("title") or ""), str(event.get("slug") or ""), str(event.get("description") or "")]).lower()
            if query not in blob:
                continue
        is_exhaustive, evidence = is_likely_exhaustive_event(event, markets)
        if not is_exhaustive:
            continue
        if evidence == "heuristic_exhaustive_candidate" and not args.include_heuristic_events:
            continue
        cumulative_markets = safe_float(event.get("cumulativeMarkets"))
        if cumulative_markets is not None and cumulative_markets > len(markets):
            event = fetch_event_detail(event, args.http_timeout)
            markets = [m for m in (event.get("markets") or []) if isinstance(m, dict)]
            is_exhaustive, evidence = is_likely_exhaustive_event(event, markets)
        category = classify_category(
            str(event.get("title") or ""),
            str(event.get("slug") or ""),
            str(event.get("description") or ""),
            " ".join(str(t.get("label") or t.get("slug") or "") for t in (event.get("tags") or []) if isinstance(t, dict)),
        )
        fee_rate = TAKER_FEE_RATES.get(category, TAKER_FEE_RATES["other"])
        legs = [leg for leg in (market_to_leg(m, fee_rate) for m in markets) if leg is not None]
        if len(legs) < args.min_markets or len(legs) > args.max_markets_per_event:
            continue
        other_markets = [m for m in markets if is_other_market(m)]
        other_conditions = {str(m.get("conditionId") or "").lower() for m in other_markets}
        has_active_other_leg = any(leg.condition_id in other_conditions for leg in legs)
        executable_exhaustive = not other_markets or has_active_other_leg
        gamma_prices = [leg.gamma_yes_price for leg in legs]
        if any(price is None for price in gamma_prices):
            continue
        gamma_cost = sum(float(price) for price in gamma_prices if price is not None)
        gamma_fee = sum(taker_fee_for_fill(1.0, float(leg.gamma_yes_price or 0.0), leg.fee_rate) for leg in legs)
        gamma_edge_cents = (1.0 - gamma_cost - gamma_fee) * 100.0
        if gamma_edge_cents < args.min_gamma_edge_cents:
            continue
        candidates.append(
            BasketEvent(
                event_id=str(event.get("id") or ""),
                title=str(event.get("title") or ""),
                slug=str(event.get("slug") or ""),
                category=category,
                fee_rate=fee_rate,
                neg_risk_evidence=evidence,
                detail_market_count=len(markets),
                has_other_market=bool(other_markets),
                has_active_other_leg=has_active_other_leg,
                executable_exhaustive=executable_exhaustive,
                legs=legs,
            )
        )
    candidates.sort(key=lambda event: gamma_edge_cents_for_event(event), reverse=True)
    return candidates[: args.candidate_limit]


def gamma_edge_cents_for_event(event: BasketEvent) -> float:
    prices = [leg.gamma_yes_price for leg in event.legs if leg.gamma_yes_price is not None]
    if len(prices) != len(event.legs):
        return -1e9
    cost = sum(prices)
    fee = sum(taker_fee_for_fill(1.0, float(leg.gamma_yes_price or 0.0), leg.fee_rate) for leg in event.legs)
    return (1.0 - cost - fee) * 100.0


def collect_book_for_leg(leg: BasketLeg, target_shares: float, timeout: float) -> None:
    try:
        book = http_get_json(CLOB_BASE, "/book", {"token_id": leg.token_id}, timeout)
        asks = book.get("asks") or []
        consumed = consume_asks_for_shares(asks, target_shares, leg.fee_rate)
        leg.book_best_ask = consumed.get("best_ask") if isinstance(consumed.get("best_ask"), float) else None
        leg.target_avg_price = consumed.get("avg_price") if isinstance(consumed.get("avg_price"), float) else None
        leg.target_cost_usd = consumed.get("cost_usd") if isinstance(consumed.get("cost_usd"), float) else None
        leg.target_fee_usd = consumed.get("fee_usd") if isinstance(consumed.get("fee_usd"), float) else None
        leg.target_ok = consumed.get("ok") is True
        available = consumed.get("available_shares")
        leg.available_shares = float(available) if isinstance(available, (int, float)) else 0.0
    except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
        leg.book_error = type(exc).__name__


def analyze_live_books(events: list[BasketEvent], args: argparse.Namespace) -> None:
    target_shares = args.target_payout_usd
    for event in events[: args.book_event_limit]:
        for leg in event.legs:
            collect_book_for_leg(leg, target_shares, args.http_timeout)
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)


def event_summary_row(event: BasketEvent, target_payout_usd: float) -> dict[str, Any]:
    gamma_cost = sum(float(leg.gamma_yes_price or 0.0) for leg in event.legs)
    gamma_fee = sum(taker_fee_for_fill(1.0, float(leg.gamma_yes_price or 0.0), leg.fee_rate) for leg in event.legs)
    gamma_edge = 1.0 - gamma_cost - gamma_fee

    book_legs = [leg for leg in event.legs if leg.target_ok and leg.target_cost_usd is not None and leg.target_fee_usd is not None]
    book_complete = len(book_legs) == len(event.legs)
    book_cost = sum(float(leg.target_cost_usd or 0.0) for leg in event.legs) if book_complete else None
    book_fee = sum(float(leg.target_fee_usd or 0.0) for leg in event.legs) if book_complete else None
    book_profit = target_payout_usd - book_cost - book_fee if book_cost is not None and book_fee is not None else None
    book_edge_cents = (book_profit / target_payout_usd) * 100.0 if book_profit is not None and target_payout_usd > EPS else None
    tradable_candidate = (
        event.executable_exhaustive
        and book_complete
        and book_profit is not None
        and book_profit >= 0.0
    )
    best_ask_sum = None
    if all(leg.book_best_ask is not None for leg in event.legs):
        best_ask_sum = sum(float(leg.book_best_ask or 0.0) for leg in event.legs)
    min_available = min((leg.available_shares for leg in event.legs), default=0.0)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "event_id": event.event_id,
        "title": event.title,
        "slug": event.slug,
        "category": event.category,
        "fee_rate": event.fee_rate,
        "min_leg_fee_rate": min((leg.fee_rate for leg in event.legs), default=event.fee_rate),
        "max_leg_fee_rate": max((leg.fee_rate for leg in event.legs), default=event.fee_rate),
        "neg_risk_evidence": event.neg_risk_evidence,
        "num_outcomes": len(event.legs),
        "detail_market_count": event.detail_market_count,
        "has_other_market": event.has_other_market,
        "has_active_other_leg": event.has_active_other_leg,
        "executable_exhaustive": event.executable_exhaustive,
        "gamma_cost_per_set": gamma_cost,
        "gamma_fee_per_set": gamma_fee,
        "gamma_edge_cents": gamma_edge * 100.0,
        "book_complete": book_complete,
        "book_best_ask_sum": best_ask_sum,
        "target_payout_usd": target_payout_usd,
        "target_total_cost_usd": book_cost,
        "target_total_fee_usd": book_fee,
        "target_profit_usd": book_profit,
        "target_edge_cents": book_edge_cents,
        "tradable_candidate": tradable_candidate,
        "min_available_shares": min_available,
        "book_error_count": sum(1 for leg in event.legs if leg.book_error),
    }


def leg_rows(event: BasketEvent) -> list[dict[str, Any]]:
    rows = []
    for leg in event.legs:
        rows.append(
            {
                "event_id": event.event_id,
                "event_title": event.title,
                "category": event.category,
                "event_fee_rate_fallback": event.fee_rate,
                "leg_fee_rate": leg.fee_rate,
                "market_id": leg.market_id,
                "condition_id": leg.condition_id,
                "token_id": leg.token_id,
                "outcome_label": leg.outcome_label,
                "question": leg.question,
                "gamma_yes_price": leg.gamma_yes_price,
                "gamma_best_ask": leg.gamma_best_ask,
                "book_best_ask": leg.book_best_ask,
                "target_avg_price": leg.target_avg_price,
                "target_cost_usd": leg.target_cost_usd,
                "target_fee_usd": leg.target_fee_usd,
                "target_ok": leg.target_ok,
                "available_shares": leg.available_shares,
                "book_error": leg.book_error,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def write_summary_md(path: Path, rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    def fmt(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    positive = [row for row in rows if (safe_float(row.get("target_profit_usd")) or -1e9) >= 0]
    tradable_positive = [
        row
        for row in rows
        if row.get("tradable_candidate") is True and (safe_float(row.get("target_profit_usd")) or -1e9) >= 0
    ]
    lines = [
        "# Polymarket NegRisk Basket Arbitrage Scan",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Read-only scan. No orders are signed or submitted.",
        "",
        "## Fee Model",
        "",
        "Polymarket taker fee is estimated as:",
        "",
        "```text",
        "fee = shares * feeRate * price * (1 - price)",
        "```",
        "",
        "The scan uses category fee rates from current Polymarket docs and treats makers as zero-fee only if live execution is later changed to maker orders.",
        "",
        "## Counts",
        "",
        f"- Candidate events: {len(rows)}",
        f"- Live book events requested: {args.book_event_limit}",
        f"- Target payout per basket: {args.target_payout_usd}",
        f"- Fee-adjusted non-negative live subsets: {len(positive)}",
        f"- Executable exhaustive fee-adjusted candidates: {len(tradable_positive)}",
        "",
        "## Top Events",
        "",
        "| rank | category | outcomes | detail_n | exhaustive | tradable | gamma_edge_c | target_profit | target_edge_c | min_shares | evidence | title |",
        "|---:|---|---:|---:|---|---|---:|---:|---:|---:|---|---|",
    ]
    for idx, row in enumerate(rows[:20], start=1):
        lines.append(
            "| {idx} | {category} | {n} | {detail_n} | {exhaustive} | {tradable} | {gamma} | {profit} | {edge} | {shares} | {evidence} | {title} |".format(
                idx=idx,
                category=row.get("category", ""),
                n=row.get("num_outcomes", ""),
                detail_n=row.get("detail_market_count", ""),
                exhaustive=row.get("executable_exhaustive", ""),
                tradable=row.get("tradable_candidate", ""),
                gamma=fmt(safe_float(row.get("gamma_edge_cents"))),
                profit=fmt(safe_float(row.get("target_profit_usd"))),
                edge=fmt(safe_float(row.get("target_edge_cents"))),
                shares=fmt(safe_float(row.get("min_available_shares"))),
                evidence=row.get("neg_risk_evidence", ""),
                title=str(row.get("title", ""))[:80].replace("|", "/"),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def self_test() -> None:
    asks_a = [{"price": "0.40", "size": "50"}, {"price": "0.41", "size": "100"}]
    asks_b = [{"price": "0.55", "size": "200"}]
    a = consume_asks_for_shares(asks_a, 100, 0.0)
    b = consume_asks_for_shares(asks_b, 100, 0.0)
    assert a["ok"] is True
    assert b["ok"] is True
    assert round(float(a["avg_price"]), 4) == 0.405
    cost = float(a["cost_usd"]) + float(b["cost_usd"])
    assert round(cost, 4) == 95.5
    fee = taker_fee_for_fill(100, 0.5, 0.07)
    assert round(fee, 4) == 1.75
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return

    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    candidates = build_candidate_events(args)
    analyze_live_books(candidates, args)
    rows = [event_summary_row(event, args.target_payout_usd) for event in candidates]
    rows.sort(
        key=lambda row: (
            row.get("tradable_candidate") is True,
            safe_float(row.get("target_profit_usd")) or -1e9,
            safe_float(row.get("gamma_edge_cents")) or -1e9,
        ),
        reverse=True,
    )
    leg_detail_rows = [row for event in candidates for row in leg_rows(event)]
    write_csv(output_dir / "event_baskets.csv", rows)
    write_csv(output_dir / "basket_legs.csv", leg_detail_rows)
    write_json(
        output_dir / "summary.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            "candidate_count": len(candidates),
            "top_events": rows[:20],
        },
    )
    write_summary_md(output_dir / "summary.md", rows, args)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
